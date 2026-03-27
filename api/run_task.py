"""Thin API entry point for running one task end-to-end."""

import json
import random
import sys
import time
import uuid
from copy import deepcopy
from typing import Dict, Optional

import structlog
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


RUN_RUNTIME_STATE: Dict[str, Dict[str, object]] = {}


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


def _task_cache_key(
    task_name: str,
    module_name: str,
    provider_name: str,
    model_name: str,
    task_input: str,
    task_config: Dict[str, object],
    cost_rate: float,
    agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
) -> str:
    payload = {
        "task_name": task_name,
        "module_name": module_name,
        "provider": provider_name,
        "model": model_name,
        "task_input": task_input,
        "task_config": task_config,
        "cost_rate": cost_rate,
        "agent_overrides": agent_overrides or {},
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def run_task(
    task_name: str,
    module_name: Optional[str] = None,
    agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
    run_id_override: Optional[str] = None,
    user_id: Optional[str] = None,
    instructions: Optional[str] = None,
) -> Dict[str, object]:
    settings = get_settings()
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    logger = structlog.get_logger(__name__)

    # Initialize Redis cache if not already initialized
    from core_engine.cache import GLOBAL_CACHE, init_cache
    if GLOBAL_CACHE is None:
        init_cache(settings.redis_url)
        logger.info("[run_task] Initialized Redis cache", redis_url=settings.redis_url)
    from core_engine.cache import get_cache
    cache = get_cache()

    persistence_enabled = True
    if run_id_override:
        run_id = run_id_override
        if str(run_id_override).startswith("ephemeral_"):
            persistence_enabled = False
    else:
        try:
            run_id = create_run(task_name=task_name, module_name=selected_module, database_url=settings.database_url)
        except Exception as exc:
            persistence_enabled = False
            run_id = f"ephemeral_{uuid.uuid4().hex}"
            log_event(logger, "persistence_unavailable", reason=str(exc), run_id=run_id)
    log_event(logger, "run_start", task_name=task_name, module_name=selected_module, run_id=run_id)
    RUN_RUNTIME_STATE[run_id] = {
        "run_id": run_id,
        "task_name": task_name,
        "module_name": selected_module,
        "status": "pending",
        "workflow_steps": [],
        "total_cost": 0.0,
    }

    try:
        if persistence_enabled:
            update_run_status(run_id=run_id, status="running", database_url=settings.database_url)
        RUN_RUNTIME_STATE[run_id]["status"] = "running"
        module = load_module(selected_module)
        workflow_results = []

        task_config = module["tasks"].get_task(task_name)
        all_tasks = (
            module["tasks"].list_tasks()
            if callable(getattr(module["tasks"], "list_tasks", None))
            else {task_name: task_config}
        )
        workflow_steps = task_config["workflow"]
        task_input = str(task_config["input"])
        max_total_tokens = int(task_config.get("max_total_tokens", 0) or 0)
        agent_profiles = _merge_agent_profiles(getattr(module["agents"], "AGENTS", {}), agent_overrides)
        progression_context: Optional[Dict[str, object]] = None

        if selected_module == "business_sim" and user_id:
            from game_modules.business_sim import progression as progress

            task_allowed, block_reason = progress.tutorial_allows_task(
                user_id=user_id,
                task_name=task_name,
                task_definitions=all_tasks,
            )
            if not task_allowed:
                raise ExecutionError(
                    "task_locked",
                    block_reason,
                    {"user_id": user_id, "task_name": task_name},
                )

            cost_estimate = progress.estimate_task_cost(task_config)
            try:
                charge_info = progress.charge_task_cost(user_id=user_id, task_name=task_name, cost=cost_estimate)
            except ValueError as exc:
                raise ExecutionError(
                    "insufficient_wallet",
                    str(exc),
                    {"user_id": user_id, "task_name": task_name, "required_cost": cost_estimate},
                ) from exc
            clarity_score = progress.score_prompt_clarity(instructions or "", task_config)

            if instructions:
                task_input = f"{task_input}\nPlayer Instructions:\n{instructions}"

            progression_context = {
                "user_id": user_id,
                "clarity_score": clarity_score,
                "cost_spent": float(charge_info["cost_spent"]),
                "all_tasks": all_tasks,
            }

        request_cache_key = _task_cache_key(
            task_name=task_name,
            module_name=selected_module,
            provider_name=settings.get_provider("task"),
            model_name=settings.get_model("task"),
            task_input=task_input,
            task_config=task_config,
            cost_rate=settings.llm_cost_per_1k_tokens_usd,
            agent_overrides=agent_overrides,
        )
        cached_exists = cache.get_task_result(request_cache_key) is not None
        if cached_exists:
            delay_min = min(settings.task_cache_delay_min_ms, settings.task_cache_delay_max_ms)
            delay_max = max(settings.task_cache_delay_min_ms, settings.task_cache_delay_max_ms)
            wait_seconds = random.uniform(delay_min / 1000.0, delay_max / 1000.0)
            time.sleep(wait_seconds)
            cached_result = cache.get_task_result(request_cache_key)
            if cached_result is not None:
                cached = deepcopy(cached_result)
                if run_id_override:
                    cached.setdefault("storage", {})
                    cached["storage"]["run_id"] = run_id_override
                if progression_context:
                    from game_modules.business_sim import progression as progress

                    enriched_cfg = dict(task_config)
                    enriched_cfg["_all_tasks"] = progression_context["all_tasks"]
                    comparison = cached.get("comparison_fields", {})
                    player_result = progress.finalize_task_result(
                        user_id=str(progression_context["user_id"]),
                        task_name=task_name,
                        task_config=enriched_cfg,
                        run_id=str(cached.get("storage", {}).get("run_id", run_id)),
                        cost_spent=float(progression_context["cost_spent"]),
                        clarity_score=float(progression_context["clarity_score"]),
                        evaluation_score=float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0),
                        missed_constraints=int(comparison.get("missed_constraints", 0) or 0),
                    )
                    cached["player_result"] = player_result
                if persistence_enabled:
                    update_run_status(
                        run_id=run_id,
                        status="completed",
                        database_url=settings.database_url,
                        final_score=float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0),
                        total_cost=float(cached.get("total_cost", 0.0) or 0.0),
                        error_message=None,
                    )
                cached["cache_reused"] = True
                cached["cache_wait_seconds"] = round(wait_seconds, 4)
                return cached

        controller = AgentController(
            settings=settings,
            purpose="task",
            max_concurrency=settings.llm_max_concurrency,
            retry_attempts=settings.provider_retry_attempts,
            enable_agent_cache=settings.enable_agent_cache,
            logger=logger,
        )
        def _on_step(step_index: int, step_result: Dict[str, object]) -> None:
            RUN_RUNTIME_STATE[run_id]["workflow_steps"].append({"step_index": step_index, **step_result})

        workflow_results = run_sequential_workflow(
            workflow_steps=workflow_steps,
            task_input=task_input,
            agent_controller=controller,
            agent_profiles=agent_profiles,
            on_step=_on_step,
            logger=logger,
        )

        # Enforce per-task total token budget with truncation fallback.
        if max_total_tokens > 0:
            running_tokens = 0
            for step in workflow_results:
                step_tokens = int(step.get("token_usage", {}).get("total_tokens", 0))
                running_tokens += step_tokens
                if running_tokens > max_total_tokens:
                    output_words = str(step.get("output", "")).split()
                    overflow = running_tokens - max_total_tokens
                    trimmed_size = max(1, len(output_words) - overflow)
                    step["output"] = " ".join(output_words[:trimmed_size]) + " ...[TRUNCATED]"
                    step["budget_action"] = step.get("budget_action") or "task_total_budget_truncated"
                    step["token_usage"]["completion_tokens"] = max(1, len(str(step["output"]).split()))
                    step["token_usage"]["total_tokens"] = int(step["token_usage"].get("prompt_tokens", 0)) + int(
                        step["token_usage"]["completion_tokens"]
                    )
                    running_tokens = max_total_tokens

        total_cost = round(sum(float(step.get("cost", 0.0)) for step in workflow_results), 8)
        RUN_RUNTIME_STATE[run_id]["total_cost"] = total_cost
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
                total_cost=total_cost,
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
            "total_cost": total_cost,
            "affinity_updates": affinity_updates,
        }
        result["comparison_fields"] = _build_comparison_fields(
            result=result,
            cost_per_1k_tokens=settings.llm_cost_per_1k_tokens_usd,
        )
        if progression_context:
            from game_modules.business_sim import progression as progress

            enriched_cfg = dict(task_config)
            enriched_cfg["_all_tasks"] = progression_context["all_tasks"]
            player_result = progress.finalize_task_result(
                user_id=str(progression_context["user_id"]),
                task_name=task_name,
                task_config=enriched_cfg,
                run_id=run_id,
                cost_spent=float(progression_context["cost_spent"]),
                clarity_score=float(progression_context["clarity_score"]),
                evaluation_score=float(evaluation.get("final_score", 0.0) or 0.0),
                missed_constraints=int(result["comparison_fields"].get("missed_constraints", 0) or 0),
            )
            result["player_result"] = player_result
        cache.set_task_result(
            request_cache_key,
            deepcopy(result),
            ttl_seconds=settings.task_result_cache_ttl_seconds,
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
        RUN_RUNTIME_STATE[run_id]["status"] = "completed"
        RUN_RUNTIME_STATE[run_id]["result"] = result
        return result
    except Exception as exc:
        progression_ctx = locals().get("progression_context")
        if progression_ctx:
            try:
                from game_modules.business_sim import progression as progress

                failed_cfg = dict(locals().get("task_config", {}))
                failed_cfg["_all_tasks"] = progression_ctx.get("all_tasks", {})
                progress.finalize_task_result(
                    user_id=str(progression_ctx["user_id"]),
                    task_name=task_name,
                    task_config=failed_cfg,
                    run_id=run_id,
                    cost_spent=float(progression_ctx["cost_spent"]),
                    clarity_score=float(progression_ctx["clarity_score"]),
                    evaluation_score=0.0,
                    missed_constraints=1,
                )
            except Exception:
                pass
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
        RUN_RUNTIME_STATE[run_id]["status"] = "failed"
        RUN_RUNTIME_STATE[run_id]["error"] = str(exc)
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


def get_runtime_run(run_id: str) -> Optional[Dict[str, object]]:
    return RUN_RUNTIME_STATE.get(run_id)


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


def debug_compare_agents(task_name: str, module_name: Optional[str] = None) -> Dict[str, object]:
    comparison = run_junior_vs_senior_comparison(task_name=task_name, module_name=module_name)

    def _extract(level: str, run_payload: Dict[str, object]) -> Dict[str, object]:
        steps = run_payload.get("workflow_results", [])
        final_step = steps[-1] if steps else {}
        token_usage = {
            "total_tokens": sum(int(s.get("token_usage", {}).get("total_tokens", 0)) for s in steps),
            "prompt_tokens": sum(int(s.get("token_usage", {}).get("prompt_tokens", 0)) for s in steps),
            "completion_tokens": sum(int(s.get("token_usage", {}).get("completion_tokens", 0)) for s in steps),
        }
        return {
            "agent_level": level,
            "effective_traits": final_step.get("effective_attributes", {}),
            "output_summary": {
                "length": comparison[level]["output_length"],
                "missed_constraints": comparison[level]["missed_constraints"],
                "deviation_detected": comparison[level]["deviation_detected"],
            },
            "evaluation": run_payload.get("evaluation", {}),
            "token_usage": token_usage,
            "cost": run_payload.get("total_cost", 0.0),
            "latency_ms": int(sum(float(s.get("result_delay_seconds", 0.0)) for s in steps) * 1000),
        }

    # rerun once to extract step-level details for each profile
    settings = get_settings()
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    module = load_module(selected_module)
    agent_names = list(getattr(module["agents"], "AGENTS", {}).keys())
    junior_overrides = {name: {"level": "junior", "obedience": 0.82, "initiative": 0.30, "effort": 0.35} for name in agent_names}
    senior_overrides = {name: {"level": "senior", "obedience": 0.42, "initiative": 0.80, "effort": 0.75} for name in agent_names}
    junior_run = run_task(task_name=task_name, module_name=selected_module, agent_overrides=junior_overrides)
    senior_run = run_task(task_name=task_name, module_name=selected_module, agent_overrides=senior_overrides)

    return {
        "task_name": task_name,
        "module_name": selected_module,
        "results": [
            _extract("junior", junior_run),
            _extract("senior", senior_run),
        ],
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
