"""Thin API entry point for running one task end-to-end."""

import json
import random
import re
import sys
import time
from copy import deepcopy
from typing import Dict, Optional

import structlog
from core_engine.agent_controller import AgentController
from core_engine.asset_serializer import serialize_asset
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.evaluation_adapter import evaluate_workflow
from core_engine.logging_utils import log_event, setup_logging
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import resolve_module_name
from core_engine.result_store import (
    create_run,
    persist_asset,
    persist_workflow_steps,
    update_run_status,
)
from core_engine.workflow_runner import run_sequential_workflow


RUN_RUNTIME_STATE: Dict[str, Dict[str, object]] = {}


def init_runtime_run(run_id: str, task_id: str, module_name: str) -> None:
    """Initialize in-memory run status for polling before worker starts."""
    RUN_RUNTIME_STATE[run_id] = {
        "run_id": run_id,
        "task_id": task_id,
        "module_name": module_name,
        "status": "pending",
        "workflow_steps": [],
        "total_cost": 0.0,
    }


def mark_runtime_failed(run_id: str, error: str, code: str = "run_failed") -> None:
    state = RUN_RUNTIME_STATE.setdefault(run_id, {"run_id": run_id})
    state["status"] = "failed"
    state["error"] = error
    state["error_type"] = code


def _assess_constraints(output_text: str, constraints: list) -> Dict[str, object]:
    text = str(output_text or "")
    lower_text = text.lower()
    parsed_json = None
    json_error = False
    failed_rules: list[str] = []

    for rule in constraints or []:
        token = str(rule).strip()
        if not token:
            continue
        token_lower = token.lower()

        if token_lower == "json_only":
            try:
                parsed_json = json.loads(text)
            except Exception:
                json_error = True
                failed_rules.append(token)
            continue

        if token_lower.startswith("include_key:"):
            key = token.split(":", 1)[1].strip()
            if parsed_json is None and not json_error:
                try:
                    parsed_json = json.loads(text)
                except Exception:
                    json_error = True
            has_key = isinstance(parsed_json, dict) and key in parsed_json
            if not has_key:
                failed_rules.append(token)
            continue

        if token_lower.startswith("min_numbers:"):
            raw_n = token.split(":", 1)[1].strip()
            try:
                need = int(raw_n)
            except ValueError:
                need = 0
            numbers = re.findall(r"\d+(?:\.\d+)?", text)
            if len(numbers) < max(0, need):
                failed_rules.append(token)
            continue

        if token_lower.startswith("keyword:"):
            keyword = token.split(":", 1)[1].strip().lower()
            if keyword and keyword not in lower_text:
                failed_rules.append(token)
            continue

        if token_lower not in lower_text:
            failed_rules.append(token)

    return {
        "missed_constraints": len(failed_rules),
        "failed_rules": failed_rules,
        "json_error": json_error,
    }


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
    constraint_assessment = result.get("constraint_assessment", {})
    missed_constraints += int(constraint_assessment.get("missed_constraints", 0) or 0)
    if bool(constraint_assessment.get("json_error", False)):
        deviation_detected = True
    token_usage = {
        "prompt_tokens": sum(int(step.get("token_usage", {}).get("prompt_tokens", 0)) for step in workflow_results),
        "completion_tokens": sum(int(step.get("token_usage", {}).get("completion_tokens", 0)) for step in workflow_results),
        "total_tokens": sum(int(step.get("token_usage", {}).get("total_tokens", 0)) for step in workflow_results),
    }
    step_cost_sum = round(sum(float(step.get("cost", 0.0)) for step in workflow_results), 8)
    fallback_cost = round((token_usage["total_tokens"] / 1000.0) * cost_per_1k_tokens, 8)
    cost = step_cost_sum if step_cost_sum > 0 else fallback_cost
    return {
        "output_length": len(final_output),
        "missed_constraints": missed_constraints,
        "deviation_detected": deviation_detected,
        "final_score": result.get("evaluation", {}).get("final_score"),
        "token_usage": token_usage,
        "cost": cost,
    }


def _task_cache_key(
    task_id: str,
    module_name: str,
    provider_name: str,
    model_name: str,
    task_input: str,
    task_config: Dict[str, object],
    cost_rate: float,
    model_routing_snapshot: Optional[Dict[str, str]] = None,
    agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
) -> str:
    payload = {
        "task_id": task_id,
        "module_name": module_name,
        "provider": provider_name,
        "model": model_name,
        "task_input": task_input,
        "task_config": task_config,
        "cost_rate": cost_rate,
        "model_routing": model_routing_snapshot or {},
        "agent_overrides": agent_overrides or {},
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def run_task(
    task_id: str,
    module_name: Optional[str] = None,
    agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
    run_id_override: Optional[str] = None,
    user_id: Optional[str] = None,
    instructions: Optional[str] = None,
    model_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    settings = get_settings()
    effective_settings = deepcopy(settings)
    if model_overrides:
        effective_settings.model_for_purpose.update({k: v for k, v in model_overrides.items() if v})
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    logger = structlog.get_logger(__name__)

    # Initialize Redis cache if not already initialized
    from core_engine.cache import GLOBAL_CACHE, init_cache
    if GLOBAL_CACHE is None:
        init_cache(settings.redis_url)
        logger.info("[run_task] Initialized Redis cache", redis_url=settings.redis_url)
    from core_engine.cache import get_cache
    cache = get_cache()

    if run_id_override:
        run_id = run_id_override
    else:
        run_id = create_run(task_id=task_id, module_name=selected_module, database_url=settings.database_url)
    log_event(logger, "run_start", task_id=task_id, module_name=selected_module, run_id=run_id)
    RUN_RUNTIME_STATE[run_id] = {
        "run_id": run_id,
        "task_id": task_id,
        "module_name": selected_module,
        "status": "pending",
        "workflow_steps": [],
        "total_cost": 0.0,
    }

    try:
        update_run_status(run_id=run_id, status="running", database_url=settings.database_url)
        RUN_RUNTIME_STATE[run_id]["status"] = "running"
        facade = ModuleFacade.from_name(selected_module)
        workflow_results = []

        task_config = facade.get_task(task_id)
        all_tasks = facade.list_tasks() or {task_id: task_config}
        workflow_steps = task_config["workflow"]
        task_input = str(task_config["input"])
        max_total_tokens = int(task_config.get("max_total_tokens", 0) or 0)
        agent_profiles = _merge_agent_profiles(getattr(facade.agents, "AGENTS", {}), agent_overrides)
        progression_context: Optional[Dict[str, object]] = None

        if user_id:
            progress = facade.progression

            task_allowed, block_reason = progress.tutorial_allows_task(
                user_id=user_id,
                task_id=task_id,
                task_definitions=all_tasks,
            )
            if not task_allowed:
                raise ExecutionError(
                    "task_locked",
                    block_reason,
                    {"user_id": user_id, "task_id": task_id},
                )

            cost_estimate = progress.estimate_task_cost(task_config)
            try:
                charge_info = progress.charge_task_cost(user_id=user_id, task_id=task_id, cost=cost_estimate)
            except ValueError as exc:
                raise ExecutionError(
                    "insufficient_wallet",
                    str(exc),
                    {"user_id": user_id, "task_id": task_id, "required_cost": cost_estimate},
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
            task_id=task_id,
            module_name=selected_module,
            provider_name=settings.get_provider("task"),
            model_name=effective_settings.get_model("task"),
            task_input=task_input,
            task_config=task_config,
            cost_rate=settings.llm_cost_per_1k_tokens_usd,
            model_routing_snapshot=dict(effective_settings.model_for_purpose),
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
                    progress = facade.progression

                    enriched_cfg = dict(task_config)
                    enriched_cfg["_all_tasks"] = progression_context["all_tasks"]
                    comparison = cached.get("comparison_fields", {})
                    player_result = progress.finalize_task_result(
                        user_id=str(progression_context["user_id"]),
                        task_id=task_id,
                        task_config=enriched_cfg,
                        run_id=str(cached.get("storage", {}).get("run_id", run_id)),
                        cost_spent=float(progression_context["cost_spent"]),
                        clarity_score=float(progression_context["clarity_score"]),
                        evaluation_score=float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0),
                        missed_constraints=int(comparison.get("missed_constraints", 0) or 0),
                    )
                    cached["player_result"] = player_result
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
            settings=effective_settings,
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
        persist_workflow_steps(run_id=run_id, workflow_results=workflow_results, database_url=settings.database_url)

        evaluation_payload = evaluate_workflow(
            evaluation_module=facade.evaluation,
            workflow_results=workflow_results,
            module_name=selected_module,
            enable_cache=settings.enable_evaluation_cache,
            logger=logger,
        )
        evaluation = evaluation_payload["result"]
        final_output = workflow_results[-1]["output"] if workflow_results else ""
        constraint_assessment = _assess_constraints(final_output, task_config.get("constraints", []))
        if bool(task_config.get("strict_constraints", False)):
            penalty = int(constraint_assessment.get("missed_constraints", 0) or 0) * 10
            original = float(evaluation.get("final_score", 0.0) or 0.0)
            evaluation["final_score"] = round(max(0.0, original - penalty), 2)
            metrics = evaluation.setdefault("metrics", {})
            metrics["constraint_penalty"] = penalty
            metrics["constraints_missed"] = int(constraint_assessment.get("missed_constraints", 0) or 0)
            metrics["failed_constraints"] = list(constraint_assessment.get("failed_rules", []))
        log_event(
            logger,
            "evaluation_result",
            task_id=task_id,
            run_id=run_id,
            final_score=evaluation.get("final_score"),
            cache_hit=bool(evaluation_payload.get("cache_hit", False)),
        )

        asset_payload = facade.asset_transform.to_asset(workflow_results, evaluation)
        asset = serialize_asset(asset_type="business_plan", payload=asset_payload)
        asset_id = persist_asset(run_id=run_id, asset=asset, database_url=settings.database_url)
        log_event(logger, "asset_created", task_id=task_id, run_id=run_id, asset_id=asset_id, asset_type=asset["asset_type"])

        affinity_updates = {}
        if hasattr(facade.agents, "update_affinity"):
            affinity_updates = facade.agents.update_affinity(workflow_results, run_success=True)

        update_run_status(
            run_id=run_id,
            status="completed",
            database_url=settings.database_url,
            final_score=evaluation.get("final_score"),
            total_cost=total_cost,
            error_message=None,
        )

        result = {
            "task_id": task_id,
            "module_name": selected_module,
            "workflow_results": workflow_results,
            "evaluation": evaluation,
            "evaluation_cache_hit": bool(evaluation_payload.get("cache_hit", False)),
            "asset": asset,
            "storage": {"run_id": run_id, "asset_id": asset_id, "persisted": True},
            "status": "completed",
            "total_cost": total_cost,
            "affinity_updates": affinity_updates,
            "constraint_assessment": constraint_assessment,
        }
        result["comparison_fields"] = _build_comparison_fields(
            result=result,
            cost_per_1k_tokens=settings.llm_cost_per_1k_tokens_usd,
        )
        if progression_context:
            progress = facade.progression

            enriched_cfg = dict(task_config)
            enriched_cfg["_all_tasks"] = progression_context["all_tasks"]
            player_result = progress.finalize_task_result(
                user_id=str(progression_context["user_id"]),
                task_id=task_id,
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
            task_id=task_id,
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
                progress = facade.progression

                failed_cfg = dict(locals().get("task_config", {}))
                failed_cfg["_all_tasks"] = progression_ctx.get("all_tasks", {})
                progress.finalize_task_result(
                    user_id=str(progression_ctx["user_id"]),
                    task_id=task_id,
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
            if "facade" in locals() and hasattr(facade.agents, "update_affinity"):
                facade.agents.update_affinity(locals().get("workflow_results", []), run_success=False)
        except Exception:
            pass
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
            task_id=task_id,
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


def _to_player_grade(score: float) -> str:
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "E"


def _extract_model_size_b(model_name: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b", str(model_name))
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def _build_player_friendly_row(item: Dict[str, object]) -> Dict[str, object]:
    final_score = float(item.get("final_score", 0.0) or 0.0)
    missed = int(item.get("missed_constraints", 0) or 0)
    deviation = bool(item.get("deviation_detected", False))
    failed_constraints = item.get("failed_constraints", []) or []
    total_rules = max(missed, len(failed_constraints), 1)
    constraint_pass_rate = max(0.0, min(1.0, 1.0 - (missed / total_rules)))
    reliability = max(0.0, final_score - (12.0 if deviation else 0.0))
    player_score = round(max(0.0, min(100.0, reliability * 0.8 + constraint_pass_rate * 20.0)), 1)
    grade = _to_player_grade(player_score)
    verdict = "可用" if player_score >= 70 else ("勉强可用" if player_score >= 50 else "不建议用于生产任务")
    return {
        "player_score": player_score,
        "player_grade": grade,
        "constraint_pass_rate": round(constraint_pass_rate, 2),
        "verdict": verdict,
    }


def _build_benchmark_advice(rows: list[Dict[str, object]]) -> Dict[str, object]:
    if not rows:
        return {"recommended_model": None, "confidence": "low", "anomaly_detected": False, "notes": []}

    sorted_rows = sorted(
        rows,
        key=lambda x: (
            float(x.get("player_score", 0.0)),
            -float(x.get("cost", 0.0)),
            -float(x.get("latency_ms", 0.0)),
        ),
        reverse=True,
    )
    best = sorted_rows[0]
    anomaly_detected = False
    notes: list[str] = []

    for row in rows:
        if row["model"] == best["model"]:
            continue
        best_size = _extract_model_size_b(best["model"])
        row_size = _extract_model_size_b(row["model"])
        if row_size > best_size and float(best.get("player_score", 0.0)) > float(row.get("player_score", 0.0)) + 5.0:
            anomaly_detected = True
            notes.append(
                f"更小模型 {best['model']} 评分显著高于更大模型 {row['model']}，建议重复跑 3-5 次取均值。"
            )

    if anomaly_detected:
        notes.append("当弱模型反超时，优先看约束通过率和稳定性，不要只看单次分数。")
        confidence = "low"
    elif len(rows) >= 2 and abs(float(rows[0].get("player_score", 0.0)) - float(rows[1].get("player_score", 0.0))) < 3:
        notes.append("模型分差很小，建议按成本/延迟优先。")
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "recommended_model": best["model"],
        "confidence": confidence,
        "anomaly_detected": anomaly_detected,
        "notes": notes,
    }


def benchmark_models(
    task_id: str,
    agent_level: str,
    models: list[str],
    module_name: Optional[str] = None,
) -> Dict[str, object]:
    """Benchmark multiple models for one task+agent_level using existing run flow."""
    if not models:
        raise ValueError("models list cannot be empty")

    settings = get_settings()
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    facade = ModuleFacade.from_name(selected_module)
    agent_names = list(getattr(facade.agents, "AGENTS", {}).keys())
    overrides = {name: {"level": agent_level} for name in agent_names}

    benchmark_results = []

    for model_name in models:
        started_at = time.perf_counter()
        run_payload = run_task(
            task_id=task_id,
            module_name=selected_module,
            agent_overrides=overrides,
            model_overrides={f"task_{(agent_level or 'mid').lower()}": model_name},
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        fields = run_payload.get("comparison_fields", {})
        benchmark_results.append(
            {
                "model": model_name,
                "actual_models": sorted({str(s.get("model", "")) for s in run_payload.get("workflow_results", []) if s.get("model")}),
                "actual_providers": sorted({str(s.get("provider", "")) for s in run_payload.get("workflow_results", []) if s.get("provider")}),
                "fallback_detected": any(
                    str(s.get("provider", "")) != settings.get_provider("task")
                    for s in run_payload.get("workflow_results", [])
                ),
                "output_length": fields.get("output_length", 0),
                "missed_constraints": fields.get("missed_constraints", 0),
                "deviation_detected": fields.get("deviation_detected", False),
                "final_score": fields.get("final_score"),
                "token_usage": fields.get("token_usage", {}),
                "cost": fields.get("cost", 0.0),
                "latency_ms": latency_ms,
                "failed_constraints": run_payload.get("constraint_assessment", {}).get("failed_rules", []),
            }
        )
        benchmark_results[-1].update(_build_player_friendly_row(benchmark_results[-1]))

    return {
        "task_id": task_id,
        "module_name": selected_module,
        "agent_level": agent_level,
        "provider": get_settings().get_provider("task"),
        "results": benchmark_results,
        "player_summary": _build_benchmark_advice(benchmark_results),
    }


def run_junior_vs_senior_comparison(task_id: str, module_name: Optional[str] = None) -> Dict[str, object]:
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

    facade = ModuleFacade.from_name(selected_module)
    agent_names = list(getattr(facade.agents, "AGENTS", {}).keys())
    junior_overrides = {name: dict(junior_template) for name in agent_names}
    senior_overrides = {name: dict(senior_template) for name in agent_names}

    junior_run = run_task(task_id=task_id, module_name=selected_module, agent_overrides=junior_overrides)
    senior_run = run_task(task_id=task_id, module_name=selected_module, agent_overrides=senior_overrides)

    return {
        "task_id": task_id,
        "module_name": selected_module,
        "provider": settings.get_provider("task"),
        "model": settings.get_model("task"),
        "junior": junior_run["comparison_fields"],
        "senior": senior_run["comparison_fields"],
        "junior_run_id": junior_run["storage"]["run_id"],
        "senior_run_id": senior_run["storage"]["run_id"],
    }


def debug_compare_agents(task_id: str, module_name: Optional[str] = None) -> Dict[str, object]:
    comparison = run_junior_vs_senior_comparison(task_id=task_id, module_name=module_name)

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
    facade = ModuleFacade.from_name(selected_module)
    agent_names = list(getattr(facade.agents, "AGENTS", {}).keys())
    junior_overrides = {name: {"level": "junior", "obedience": 0.82, "initiative": 0.30, "effort": 0.35} for name in agent_names}
    senior_overrides = {name: {"level": "senior", "obedience": 0.42, "initiative": 0.80, "effort": 0.75} for name in agent_names}
    junior_run = run_task(task_id=task_id, module_name=selected_module, agent_overrides=junior_overrides)
    senior_run = run_task(task_id=task_id, module_name=selected_module, agent_overrides=senior_overrides)

    return {
        "task_id": task_id,
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
