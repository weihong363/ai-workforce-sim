"""Thin API entry point for running one task end-to-end."""

import json
import sys
import uuid
from copy import deepcopy
from typing import Dict, Optional

from core_engine.agent_controller import AgentController
from core_engine.asset_serializer import serialize_asset
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.evaluation_adapter import evaluate_workflow
from core_engine.logging_utils import log_event, setup_logging
from core_engine.module_loader import load_module, resolve_module_name
from core_engine.result_store import (
    create_run,
    persist_asset,
    persist_workflow_steps,
    update_run_status,
)
from core_engine.workflow_runner import run_sequential_workflow


def _merge_agent_profiles(
    base_profiles: Dict[str, Dict[str, object]],
    overrides: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, Dict[str, object]]:
    merged = deepcopy(base_profiles)
    for agent_name, patch in (overrides or {}).items():
        if agent_name not in merged:
            merged[agent_name] = {}
        merged[agent_name].update(patch)
    return merged


def _build_comparison_fields(result: Dict[str, object], cost_per_1k_tokens: float) -> Dict[str, object]:
    workflow_results = result.get("workflow_results", [])
    final_output = workflow_results[-1]["output"] if workflow_results else ""
    deviation_detected = any(
        str(step.get("output", "")).startswith("DEVIATED_FROM_INSTRUCTIONS:")
        for step in workflow_results
    )
    missed_constraints = sum(
        int("...[TRUNCATED]" in str(step.get("output", ""))) + int(
            str(step.get("output", "")).startswith("DEVIATED_FROM_INSTRUCTIONS:")
        )
        for step in workflow_results
    )
    token_usage = {
        "prompt_tokens": sum(int(step.get("token_usage", {}).get("prompt_tokens", 0)) for step in workflow_results),
        "completion_tokens": sum(int(step.get("token_usage", {}).get("completion_tokens", 0)) for step in workflow_results),
        "total_tokens": sum(int(step.get("token_usage", {}).get("total_tokens", 0)) for step in workflow_results),
    }
    cost = round((token_usage["total_tokens"] / 1000.0) * cost_per_1k_tokens, 8)
    return {
        "output_length": len(final_output),
        "missed_constraints": missed_constraints,
        "deviation_detected": deviation_detected,
        "final_score": result.get("evaluation", {}).get("final_score"),
        "token_usage": token_usage,
        "cost": cost,
    }


def run_task(
    task_name: str,
    module_name: Optional[str] = None,
    agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, object]:
    settings = get_settings()
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    logger = setup_logging()

    # Initialize Redis cache if not already initialized
    from core_engine.cache import GLOBAL_CACHE, init_cache
    if GLOBAL_CACHE is None:
        init_cache(settings.redis_url)
        logger.info(f"[run_task] Initialized Redis cache: {settings.redis_url}")

    persistence_enabled = True
    try:
        run_id = create_run(task_name=task_name, module_name=selected_module, database_url=settings.database_url)
    except Exception as exc:
        persistence_enabled = False
        run_id = f"ephemeral_{uuid.uuid4().hex}"
        log_event(logger, "persistence_unavailable", reason=str(exc), run_id=run_id)
    log_event(logger, "run_start", task_name=task_name, module_name=selected_module, run_id=run_id)

    try:
        if persistence_enabled:
            update_run_status(run_id=run_id, status="running", database_url=settings.database_url)
        module = load_module(selected_module)
        workflow_results = []

        task_config = module["tasks"].get_task(task_name)
        workflow_steps = task_config["workflow"]
        task_input = task_config["input"]
        agent_profiles = _merge_agent_profiles(getattr(module["agents"], "AGENTS", {}), agent_overrides)

        controller = AgentController(
            settings=settings,
            purpose="task",
            max_concurrency=settings.llm_max_concurrency,
            retry_attempts=settings.provider_retry_attempts,
            enable_agent_cache=settings.enable_agent_cache,
            logger=logger,
        )
        workflow_results = run_sequential_workflow(
            workflow_steps=workflow_steps,
            task_input=task_input,
            agent_controller=controller,
            agent_profiles=agent_profiles,
            logger=logger,
        )
        if persistence_enabled:
            persist_workflow_steps(run_id=run_id, workflow_results=workflow_results, database_url=settings.database_url)

        evaluation_payload = evaluate_workflow(
            evaluation_module=module["evaluation"],
            workflow_results=workflow_results,
            module_name=selected_module,
            enable_cache=settings.enable_evaluation_cache,
            logger=logger,
        )
        evaluation = evaluation_payload["result"]
        log_event(
            logger,
            "evaluation_result",
            task_name=task_name,
            run_id=run_id,
            final_score=evaluation.get("final_score"),
            cache_hit=bool(evaluation_payload.get("cache_hit", False)),
        )

        asset_payload = module["asset_transform"].to_asset(workflow_results, evaluation)
        asset = serialize_asset(asset_type="business_plan", payload=asset_payload)
        if persistence_enabled:
            asset_id = persist_asset(run_id=run_id, asset=asset, database_url=settings.database_url)
        else:
            asset_id = f"ephemeral_asset_{uuid.uuid4().hex}"
        log_event(logger, "asset_created", task_name=task_name, run_id=run_id, asset_id=asset_id, asset_type=asset["asset_type"])

        affinity_updates = {}
        if hasattr(module["agents"], "update_affinity"):
            affinity_updates = module["agents"].update_affinity(workflow_results, run_success=True)

        if persistence_enabled:
            update_run_status(
                run_id=run_id,
                status="completed",
                database_url=settings.database_url,
                final_score=evaluation.get("final_score"),
                error_message=None,
            )

        result = {
            "task_name": task_name,
            "module_name": selected_module,
            "workflow_results": workflow_results,
            "evaluation": evaluation,
            "evaluation_cache_hit": bool(evaluation_payload.get("cache_hit", False)),
            "asset": asset,
            "storage": {"run_id": run_id, "asset_id": asset_id, "persisted": persistence_enabled},
            "status": "completed",
            "affinity_updates": affinity_updates,
        }
        result["comparison_fields"] = _build_comparison_fields(
            result=result,
            cost_per_1k_tokens=settings.llm_cost_per_1k_tokens_usd,
        )

        log_event(
            logger,
            "run_end",
            task_name=task_name,
            module_name=selected_module,
            run_id=run_id,
            asset_id=asset_id,
            status="completed",
        )
        return result
    except Exception as exc:
        try:
            if "module" in locals() and hasattr(module["agents"], "update_affinity"):
                module["agents"].update_affinity(locals().get("workflow_results", []), run_success=False)
        except Exception:
            pass
        if persistence_enabled:
            update_run_status(
                run_id=run_id,
                status="failed",
                database_url=settings.database_url,
                error_message=str(exc),
            )
        log_event(
            logger,
            "run_end",
            task_name=task_name,
            module_name=selected_module,
            run_id=run_id,
            status="failed",
            error=str(exc),
        )
        if isinstance(exc, ExecutionError):
            details = dict(exc.details)
            details.setdefault("run_id", run_id)
            raise ExecutionError(exc.code, exc.message, details) from exc
        raise ExecutionError("run_failed", str(exc), {"run_id": run_id}) from exc


def run_junior_vs_senior_comparison(task_name: str, module_name: Optional[str] = None) -> Dict[str, object]:
    settings = get_settings()
    selected_module = resolve_module_name(module_name, settings.active_game_module)

    junior_template = {
        "obedience": 0.82,
        "initiative": 0.30,
        "effort": 0.35,
        "affinity": 0.55,
        "skill": 0.45,
        "overtime_willingness": 0.65,
    }
    senior_template = {
        "obedience": 0.42,
        "initiative": 0.80,
        "effort": 0.75,
        "affinity": 0.55,
        "skill": 0.82,
        "overtime_willingness": 0.35,
    }

    module = load_module(selected_module)
    agent_names = list(getattr(module["agents"], "AGENTS", {}).keys())
    junior_overrides = {name: dict(junior_template) for name in agent_names}
    senior_overrides = {name: dict(senior_template) for name in agent_names}

    junior_run = run_task(task_name=task_name, module_name=selected_module, agent_overrides=junior_overrides)
    senior_run = run_task(task_name=task_name, module_name=selected_module, agent_overrides=senior_overrides)

    return {
        "task_name": task_name,
        "module_name": selected_module,
        "provider": settings.get_provider("task"),
        "model": settings.get_model("task"),
        "junior": junior_run["comparison_fields"],
        "senior": senior_run["comparison_fields"],
        "junior_run_id": junior_run["storage"]["run_id"],
        "senior_run_id": senior_run["storage"]["run_id"],
    }


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "launch_coffee_subscription"
    module = sys.argv[2] if len(sys.argv) > 2 else None
    mode = sys.argv[3] if len(sys.argv) > 3 else "single"
    if mode == "compare":
        output = run_junior_vs_senior_comparison(task, module)
    else:
        output = run_task(task, module)
    print(json.dumps(output, indent=2))
