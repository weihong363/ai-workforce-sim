"""Thin API entry point for running one task end-to-end."""

import json
import random
import re
import time
from copy import deepcopy
from typing import Dict, Optional, List

import structlog

from core_engine.agent_controller import AgentController
from core_engine.asset_serializer import serialize_asset
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.evaluation_adapter import evaluate_workflow
from core_engine.logging_utils import log_event
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import resolve_module_name
from core_engine.result_store import (
    create_run,
    persist_asset,
    persist_workflow_steps,
    update_run_status,
)
from core_engine.tuning import get_effective_tuning
from core_engine.workflow_runner import run_sequential_workflow

RUN_RUNTIME_STATE: Dict[str, Dict[str, object]] = {}
OUTPUT_PREVIEW_CHARS = 280


def _normalize_semantic_text(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("-", " ")
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _semantic_patterns_for_constraint(token: str) -> List[str]:
    key = str(token or "").strip().lower()
    patterns = [key]

    def add(values: List[str]) -> None:
        for v in values:
            if v not in patterns:
                patterns.append(v)

    if (
            "target customer" in key
            or "customer segment" in key
            or "target user" in key
            or "audience" in key
    ):
        add(
            [
                "target customer",
                "customer segment",
                "user segment",
                "target",
                "targeting",
                "target audience",
                "urban professionals",
                "white collar",
                "white-collar",
                "office worker",
                "professional",
                "白领",
                "上班族",
            ]
        )
    if "timeline" in key or "milestone" in key or "schedule" in key:
        add(["timeline", "milestone", "roadmap", "phase", "3-month", "3 month", "three month", "三个月", "里程碑"])
    if "pricing" in key:
        add(["pricing", "price", "pricing plan", "收费", "定价", "价格"])
    if "risk" in key:
        add(["risk", "risks include", "risk factors", "risk factor", "mitigation", "uncertainty", "风险", "风控"])
    if "budget" in key:
        add(["budget", "budget cap", "cost cap", "预算", "成本上限"])

    return patterns


def _contains_semantic_match(text: str, token: str) -> bool:
    lower = _normalize_semantic_text(text)
    patterns = _semantic_patterns_for_constraint(token)
    for p in patterns:
        raw = str(p)
        if not raw:
            continue
        if any("\u4e00" <= ch <= "\u9fff" for ch in raw):
            if raw in lower:
                return True
            continue
        normalized = _normalize_semantic_text(raw)
        if not normalized:
            continue
        if re.search(rf"\b{re.escape(normalized)}\b", lower):
            return True
    return False


def _missing_reason_from_constraint(token: str) -> str:
    key = str(token or "").strip().lower()
    if "target customer" in key or "customer segment" in key:
        return "missing target customer"
    if "timeline" in key or "milestone" in key:
        return "missing milestones"
    if "pricing" in key:
        return "missing pricing"
    if "risk" in key:
        return "missing risk analysis"
    if "budget" in key:
        return "missing budget information"
    return f"missing constraint: {token}"


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

        if not _contains_semantic_match(lower_text, token_lower):
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


def _fixed_agent_cost_total(
        workflow_steps: List[str],
        agent_profiles: Dict[str, Dict[str, object]],
) -> float:
    total = 0.0
    for name in workflow_steps or []:
        profile = agent_profiles.get(str(name), {})
        if not isinstance(profile, dict):
            continue
        total += float(profile.get("fixed_run_cost", 0.0) or 0.0)
    return round(total, 8)


def _build_comparison_fields(result: Dict[str, object], cost_per_1k_tokens: float) -> Dict[str, object]:
    workflow_results = result.get("workflow_results", [])
    final_output = workflow_results[-1]["output"] if workflow_results else ""
    deviation_detected = any(
        str(step.get("output", "")).startswith("DEVIATED_FROM_INSTRUCTIONS:")
        for step in workflow_results
    )
    missed_constraints = sum(
        int(str(step.get("output", "")).startswith("DEVIATED_FROM_INSTRUCTIONS:"))
        for step in workflow_results
    )
    constraint_assessment = result.get("constraint_assessment", {})
    missed_constraints += int(constraint_assessment.get("missed_constraints", 0) or 0)
    if bool(constraint_assessment.get("json_error", False)):
        deviation_detected = True
    token_usage = {
        "prompt_tokens": sum(int(step.get("token_usage", {}).get("prompt_tokens", 0)) for step in workflow_results),
        "completion_tokens": sum(
            int(step.get("token_usage", {}).get("completion_tokens", 0)) for step in workflow_results),
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


def _constraint_adherence_score(total_constraints: int, missed_constraints: int) -> float:
    if total_constraints <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - (float(missed_constraints) / float(total_constraints))))


def _difficulty_target_score(task_config: Dict[str, object]) -> float:
    diff = str(task_config.get("difficulty", "medium")).lower()
    if diff == "easy":
        return 0.35
    if diff == "hard":
        return 0.85
    return 0.60


def _agent_level_score(level: str) -> float:
    lv = str(level or "mid").lower()
    if lv == "junior":
        return 0.35
    if lv == "senior":
        return 0.85
    return 0.60


def _estimate_agent_task_fit(
        task_config: Dict[str, object],
        workflow_steps: List[str],
        agent_profiles: Dict[str, Dict[str, object]],
) -> float:
    if not workflow_steps:
        return 1.0
    target = _difficulty_target_score(task_config)
    scores = []
    for name in workflow_steps:
        profile = agent_profiles.get(str(name), {})
        scores.append(_agent_level_score(str(profile.get("level", "mid"))))
    avg_score = sum(scores) / max(1, len(scores))
    fit = 1.0 - abs(avg_score - target)
    return round(max(0.0, min(1.0, fit)), 4)


def _build_player_feedback(
        final_score: float,
        clarity_score: float,
        failed_rules: List[str],
        additional_reasons: Optional[List[str]] = None,
) -> Dict[str, object]:
    reasons: List[str] = []
    if clarity_score < 0.4:
        reasons.append("instruction too vague")
    for rule in failed_rules:
        reasons.append(_missing_reason_from_constraint(rule))
    for reason in (additional_reasons or []):
        if reason:
            reasons.append(str(reason))
    if not reasons and final_score < 70.0:
        reasons.append("output quality below threshold")

    seen = set()
    deduped = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            deduped.append(reason)

    success = final_score >= 70.0 and len(deduped) == 0
    return {"success": success, "failure_reasons": deduped}


def _build_semantic_analysis(
        clarity_score: float,
        constraints: List[str],
        failed_rules: List[str],
) -> Dict[str, object]:
    misses_norm = {str(x).strip().lower() for x in (failed_rules or [])}
    matched = []
    missed = []
    for item in constraints or []:
        token = str(item).strip()
        if not token:
            continue
        if token.lower() in misses_norm:
            missed.append(token)
        else:
            matched.append(token)
    return {
        "clarity_score": float(clarity_score),
        "constraint_matches": {
            "matched": matched,
            "missed": missed,
            "matched_count": len(matched),
            "missed_count": len(missed),
        },
        "match_method": "rule_based_semantic_v1",
    }


def _output_preview(text: str, limit: int = OUTPUT_PREVIEW_CHARS) -> Dict[str, object]:
    raw = str(text or "")
    truncated = len(raw) > limit
    return {
        "raw_output_preview": raw[:limit] + (" ..." if truncated else ""),
        "full_output_length": len(raw),
        "truncated_for_display": truncated,
        "stored_full_output": True,
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
        selected_agent_name: Optional[str] = None,
        tuning_snapshot: Optional[Dict[str, object]] = None,
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
        "selected_agent_name": str(selected_agent_name or ""),
        "tuning": tuning_snapshot or {},
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def run_task(
        task_id: str,
        module_name: Optional[str] = None,
        agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
        run_id_override: Optional[str] = None,
        user_id: Optional[str] = None,
        instructions: Optional[str] = None,
        selected_agent_name: Optional[str] = None,
        model_overrides: Optional[Dict[str, str]] = None,
        task_definition_override: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    settings = get_settings()
    effective_settings = deepcopy(settings)
    tuning = get_effective_tuning(settings)
    trait_weights = tuning.get("agent_trait_weights", {})
    effective_settings.obedience_weight = float(trait_weights.get("obedience", effective_settings.obedience_weight))
    effective_settings.initiative_weight = float(trait_weights.get("initiative", effective_settings.initiative_weight))
    effective_settings.effort_weight = float(trait_weights.get("effort", effective_settings.effort_weight))
    token_budget = tuning.get("token_budget", {})
    effective_settings.task_token_budget_multiplier = float(
        token_budget.get("task_multiplier", effective_settings.task_token_budget_multiplier))
    effective_settings.agent_token_budget_multiplier = float(
        token_budget.get("agent_multiplier", effective_settings.agent_token_budget_multiplier))
    if model_overrides:
        effective_settings.model_for_purpose.update({k: v for k, v in model_overrides.items() if v})
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    logger = structlog.get_logger(__name__)
    preloaded_facade: Optional[ModuleFacade] = None
    preloaded_task_config: Optional[Dict[str, object]] = None
    preloaded_all_tasks: Optional[Dict[str, Dict[str, object]]] = None

    # Initialize Redis cache if not already initialized
    from core_engine.cache import GLOBAL_CACHE, init_cache
    if GLOBAL_CACHE is None:
        init_cache(
            settings.redis_url,
            agent_cache_ttl_seconds=settings.agent_cache_ttl_seconds,
            evaluation_cache_ttl_seconds=settings.evaluation_cache_ttl_seconds,
            temp_result_ttl_seconds=settings.temp_result_ttl_seconds,
        )
        logger.info("[run_task] Initialized Redis cache", redis_url=settings.redis_url)
    from core_engine.cache import get_cache
    cache = get_cache()

    # Pre-validate task/module before persisting run records.
    preloaded_facade = ModuleFacade.from_name(selected_module)
    normalize_task = getattr(preloaded_facade.tasks, "normalize_task", None)
    if isinstance(task_definition_override, dict) and task_definition_override:
        preloaded_task_config = dict(task_definition_override)
        if callable(normalize_task):
            preloaded_task_config = normalize_task(task_id, preloaded_task_config)
        preloaded_all_tasks = {task_id: dict(preloaded_task_config)}
    else:
        preloaded_task_config = preloaded_facade.get_task(task_id)
        if callable(normalize_task):
            preloaded_task_config = normalize_task(task_id, dict(preloaded_task_config))
        preloaded_all_tasks = preloaded_facade.list_tasks() or {task_id: dict(preloaded_task_config)}

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
        facade = preloaded_facade or ModuleFacade.from_name(selected_module)
        workflow_results = []

        normalize_task = getattr(facade.tasks, "normalize_task", None)
        task_config = dict(preloaded_task_config or {})
        all_tasks = dict(preloaded_all_tasks or {task_id: task_config})
        task_config["constraints"] = list(
            task_config.get("required_constraints", task_config.get("constraints", [])) or []
        )
        task_config["reward"] = float(task_config.get("base_reward", task_config.get("reward", 0.0)) or 0.0)
        task_config["cost_estimate"] = float(
            task_config.get("estimated_cost", task_config.get("cost_estimate", 0.0)) or 0.0
        )
        task_config["is_tutorial"] = bool(task_config.get("tutorial_only", task_config.get("is_tutorial", False)))
        configured_workflow = task_config.get("workflow")
        if isinstance(configured_workflow, list) and configured_workflow:
            workflow_steps = [str(name) for name in configured_workflow if str(name).strip()]
        else:
            default_agent = str(selected_agent_name or "operator").strip() or "operator"
            workflow_steps = [default_agent]
        task_input = str(task_config["input"])
        instruction_text = str(instructions or "").strip()
        if instruction_text:
            task_input = f"{task_input}\nPlayer Instructions:\n{instruction_text}"
        raw_task_budget = int(task_config.get("max_total_tokens", 0) or 0)
        max_total_tokens = int(raw_task_budget * settings.task_token_budget_multiplier)
        agent_profiles = _merge_agent_profiles(getattr(facade.agents, "AGENTS", {}), None)
        build_default_overrides = getattr(facade.agents, "build_default_workflow_overrides", None)
        if callable(build_default_overrides):
            agent_profiles = _merge_agent_profiles(
                agent_profiles,
                build_default_overrides(list(workflow_steps)),
            )
        agent_profiles = _merge_agent_profiles(agent_profiles, agent_overrides)
        task_config["_agent_task_fit_score"] = _estimate_agent_task_fit(task_config, list(workflow_steps),
                                                                        agent_profiles)
        progression_context: Optional[Dict[str, object]] = None
        clarity_score = 0.0

        if user_id:
            progress = facade.progression
            user_snapshot = progress.get_user(user_id)
            owned_agents = list(user_snapshot.get("owned_agents", []) or [])

            selected_preset = str(selected_agent_name or "").strip().lower()
            if selected_preset:
                selected_bindings = [
                    item for item in owned_agents
                    if isinstance(item, dict) and str(item.get("preset", "")).strip().lower() == selected_preset
                ]
                if not selected_bindings:
                    raise ExecutionError(
                        "invalid_agent_selection",
                        f"Selected agent '{selected_preset}' is not bound to user.",
                        {"user_id": user_id, "task_id": task_id, "agent_name": selected_preset},
                    )
                owned_agents = selected_bindings

            build_user_overrides = getattr(facade.agents, "build_user_workflow_overrides", None)
            if callable(build_user_overrides):
                user_selection_overrides = build_user_overrides(
                    owned_agents,
                    list(workflow_steps),
                )
                agent_profiles = _merge_agent_profiles(agent_profiles, user_selection_overrides)
                task_config["_agent_task_fit_score"] = _estimate_agent_task_fit(
                    task_config, list(workflow_steps), agent_profiles
                )

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

            model_cost_estimate = progress.estimate_task_cost(task_config)
            fixed_agent_cost_estimate = _fixed_agent_cost_total(list(workflow_steps), agent_profiles)
            cost_estimate = round(float(model_cost_estimate) + float(fixed_agent_cost_estimate), 8)
            try:
                charge_info = progress.charge_task_cost(user_id=user_id, task_id=task_id, cost=cost_estimate)
            except ValueError as exc:
                current_wallet = float(progress.get_user(user_id).get("wallet_balance", 0.0))
                raise ExecutionError(
                    "insufficient_wallet",
                    str(exc),
                    {
                        "user_id": user_id,
                        "task_id": task_id,
                        "required_cost": cost_estimate,
                        "available_balance": current_wallet,
                    },
                ) from exc
            clarity_score = progress.score_prompt_clarity(instructions or "", task_config)

            progression_context = {
                "user_id": user_id,
                "clarity_score": clarity_score,
                "cost_spent": float(charge_info["cost_spent"]),
                "estimated_model_cost": float(model_cost_estimate),
                "estimated_fixed_agent_cost": float(fixed_agent_cost_estimate),
                "wallet_before": float(charge_info.get("wallet_before", 0.0) or 0.0),
                "all_tasks": all_tasks,
            }
        else:
            # Deterministic and lightweight behavior signal even without user progression updates.
            try:
                progression = facade.progression
                clarity_score = float(progression.score_prompt_clarity(instructions or "", task_config))
            except Exception:
                clarity_score = 0.0
        for profile in agent_profiles.values():
            if isinstance(profile, dict):
                profile["clarity_score"] = float(clarity_score)
                level_key = str(profile.get("level", "mid")).lower()
                level_delay_factor = 1.0
                if level_key == "junior":
                    level_delay_factor = 1.2
                elif level_key == "senior":
                    level_delay_factor = 0.55
                profile["artificial_delay_ms"] = int(
                    float(profile.get("artificial_delay_ms", 0) or 0)
                    * level_delay_factor
                    * float(
                        tuning.get("artificial_delay_multiplier", 1.0))
                )
                profile["cost_weight"] = float(profile.get("cost_weight", 1.0) or 1.0) * float(
                    tuning.get("cost_weight_multiplier", 1.0)
                )

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
            selected_agent_name=selected_agent_name,
            tuning_snapshot=tuning,
        )
        cached_exists = cache.get_task_result(request_cache_key) is not None
        if cached_exists:
            log_event(
                logger,
                "task_result_cache_hit",
                task_id=task_id,
                run_id=run_id,
                module_name=selected_module,
            )
            delay_min = min(settings.task_cache_delay_min_ms, settings.task_cache_delay_max_ms)
            delay_max = max(settings.task_cache_delay_min_ms, settings.task_cache_delay_max_ms)
            wait_seconds = random.uniform(delay_min / 1000.0, delay_max / 1000.0)
            time.sleep(wait_seconds)
            cached_result = cache.get_task_result(request_cache_key)
            if cached_result is not None:
                cached = deepcopy(cached_result)
                cached.setdefault("storage", {})
                cached["storage"]["run_id"] = run_id
                persist_workflow_steps(
                    run_id=run_id,
                    workflow_results=cached.get("workflow_results", []),
                    database_url=settings.database_url,
                )
                asset_payload = cached.get("asset", {})
                persisted_asset_id = persist_asset(
                    run_id=run_id,
                    asset=asset_payload if isinstance(asset_payload, dict) else {"asset_type": "business_plan",
                                                                                 "payload": {}},
                    database_url=settings.database_url,
                )
                cached["storage"]["asset_id"] = persisted_asset_id
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
                        wallet_before=float(progression_context.get("wallet_before", 0.0) or 0.0),
                        clarity_score=float(progression_context["clarity_score"]),
                        evaluation_score=float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0),
                        missed_constraints=int(comparison.get("missed_constraints", 0) or 0),
                    )
                    cached["player_result"] = player_result
                    existing_feedback = cached.get("player_feedback", {}) if isinstance(cached.get("player_feedback"),
                                                                                        dict) else {}
                    existing_reasons = list(existing_feedback.get("failure_reasons", []) or [])
                    merged_reasons = existing_reasons + list(player_result.get("failure_reasons", []) or [])
                    cached["player_feedback"] = _build_player_feedback(
                        final_score=float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0),
                        clarity_score=float(progression_context.get("clarity_score", 0.0) or 0.0),
                        failed_rules=list(cached.get("constraint_assessment", {}).get("failed_rules", []) or []),
                        additional_reasons=merged_reasons,
                    )
                if "semantic_analysis" not in cached:
                    constraints_cached = list(task_config.get("constraints", []) or [])
                    failed_cached = list(cached.get("constraint_assessment", {}).get("failed_rules", []) or [])
                    cached["semantic_analysis"] = _build_semantic_analysis(
                        clarity_score=float(clarity_score),
                        constraints=constraints_cached,
                        failed_rules=failed_cached,
                    )
                if "score_breakdown" not in cached:
                    score_now = float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0)
                    cached["score_breakdown"] = {
                        "base_score": score_now,
                        "penalties": {"constraint_penalty": 0, "clarity_penalty": 0, "vague_penalty": 0,
                                      "total_penalties": 0},
                        "rewards": {"adherence_bonus": 0, "total_rewards": 0},
                        "final_score": score_now,
                    }
                if "penalties" not in cached:
                    cached["penalties"] = dict(cached.get("score_breakdown", {}).get("penalties", {}))
                cached["effective_parameters"] = tuning
                workflow_results_cached = cached.get("workflow_results", []) if isinstance(
                    cached.get("workflow_results"), list) else []
                total_tokens_cached = int(
                    sum(int(step.get("token_usage", {}).get("total_tokens", 0) or 0) for step in workflow_results_cached
                        if isinstance(step, dict))
                )
                total_latency_cached = int(
                    sum(int(step.get("latency_ms", 0) or 0) for step in workflow_results_cached if
                        isinstance(step, dict))
                )
                comparison_fields = cached.get("comparison_fields", {}) if isinstance(cached.get("comparison_fields"),
                                                                                      dict) else {}
                missed_constraints_cached = int(comparison_fields.get("missed_constraints", 0) or 0)
                total_constraints_cached = len(task_config.get("constraints", []) or [])
                adherence_cached = _constraint_adherence_score(total_constraints_cached, missed_constraints_cached)
                deviation_cached = bool(comparison_fields.get("deviation_detected", False))
                update_run_status(
                    run_id=run_id,
                    status="success",
                    database_url=settings.database_url,
                    final_score=float(cached.get("evaluation", {}).get("final_score", 0.0) or 0.0),
                    total_cost=float(cached.get("total_cost", 0.0) or 0.0),
                    total_tokens=total_tokens_cached,
                    total_latency_ms=total_latency_cached,
                    clarity_score=float(clarity_score),
                    deviation_detected=deviation_cached,
                    constraint_adherence_score=adherence_cached,
                    error_message=None,
                )
                cached["observability"] = {
                    "run_id": run_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "status": "success",
                    "total_cost": float(cached.get("total_cost", 0.0) or 0.0),
                    "total_tokens": total_tokens_cached,
                    "total_latency_ms": total_latency_cached,
                    "clarity_score": float(clarity_score),
                    "deviation_detected": deviation_cached,
                    "constraint_adherence_score": adherence_cached,
                }
                cached["cache_reused"] = True
                cached["cache_wait_seconds"] = round(wait_seconds, 4)
                RUN_RUNTIME_STATE[run_id]["status"] = "success"
                RUN_RUNTIME_STATE[run_id]["result"] = cached
                return cached
        else:
            log_event(
                logger,
                "task_result_cache_miss",
                task_id=task_id,
                run_id=run_id,
                module_name=selected_module,
            )

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
        if not workflow_results:
            raise ExecutionError(
                "invalid_model_output",
                "No workflow output produced.",
                {"run_id": run_id, "task_id": task_id},
            )
        for idx, step in enumerate(workflow_results):
            output_text = str(step.get("output", "") or "").strip()
            if not output_text:
                raise ExecutionError(
                    "invalid_model_output",
                    f"Empty model output at step {idx}.",
                    {"run_id": run_id, "task_id": task_id, "step_index": idx},
                )

        # Detect per-task total token budget overflow, but keep full outputs for persistence/evaluation.
        if max_total_tokens > 0:
            running_tokens = 0
            for step in workflow_results:
                step_tokens = int(step.get("token_usage", {}).get("total_tokens", 0))
                running_tokens += step_tokens
                if running_tokens > max_total_tokens:
                    step["budget_action"] = step.get("budget_action") or "task_total_budget_truncated"
                    step["task_budget_exceeded"] = True

        for step in workflow_results:
            step["latency_ms"] = int(float(step.get("result_delay_seconds", 0.0) or 0.0) * 1000)
            if "agent_level" not in step:
                profile = agent_profiles.get(str(step.get("agent_name", "")), {})
                step["agent_level"] = str(profile.get("level", "mid"))
            profile = agent_profiles.get(str(step.get("agent_name", "")), {})
            fixed_cost = float(profile.get("fixed_run_cost", 0.0) or 0.0) if isinstance(profile, dict) else 0.0
            step["fixed_agent_cost"] = round(fixed_cost, 8)
            step["cost"] = round(float(step.get("cost", 0.0) or 0.0) + fixed_cost, 8)

        total_cost = round(sum(float(step.get("cost", 0.0)) for step in workflow_results), 8)
        total_tokens = int(
            sum(int(step.get("token_usage", {}).get("total_tokens", 0) or 0) for step in workflow_results))
        total_latency_ms = int(sum(int(step.get("latency_ms", 0) or 0) for step in workflow_results))
        RUN_RUNTIME_STATE[run_id]["total_cost"] = total_cost
        persist_workflow_steps(run_id=run_id, workflow_results=workflow_results, database_url=settings.database_url)

        try:
            evaluation_payload = evaluate_workflow(
                evaluation_module=facade.evaluation,
                workflow_results=workflow_results,
                module_name=selected_module,
                enable_cache=settings.enable_evaluation_cache,
                logger=logger,
            )
        except Exception as eval_exc:
            raise ExecutionError(
                "evaluation_failed",
                f"Evaluation failed: {eval_exc}",
                {"run_id": run_id, "task_id": task_id},
            ) from eval_exc
        evaluation = evaluation_payload["result"]
        final_output = workflow_results[-1]["output"] if workflow_results else ""
        constraint_assessment = _assess_constraints(final_output, task_config.get("constraints", []))
        if bool(constraint_assessment.get("json_error", False)) and any(
                str(rule).strip().lower() == "json_only" for rule in (task_config.get("constraints", []) or [])
        ):
            raise ExecutionError(
                "parsing_failed",
                "Model output parsing failed for required JSON format.",
                {"run_id": run_id, "task_id": task_id},
            )
        total_constraints = len(task_config.get("constraints", []) or [])
        clarity_penalty = int(round(max(0.0, 0.55 - float(clarity_score)) * max(1, total_constraints) * 2.0))
        if clarity_penalty > 0:
            raw_missed = int(constraint_assessment.get("missed_constraints", 0) or 0)
            adjusted_missed = min(max(1, total_constraints), raw_missed + clarity_penalty)
            constraint_assessment["missed_constraints"] = adjusted_missed
            failed_rules = constraint_assessment.get("failed_rules")
            if not isinstance(failed_rules, list):
                failed_rules = []
            if "clarity_penalty" not in failed_rules:
                failed_rules.append("clarity_penalty")
            constraint_assessment["failed_rules"] = failed_rules
            constraint_assessment["clarity_penalty_applied"] = clarity_penalty
        if bool(task_config.get("strict_constraints", False)):
            penalty = int(constraint_assessment.get("missed_constraints", 0) or 0) * 10
            original = float(evaluation.get("final_score", 0.0) or 0.0)
            evaluation["final_score"] = round(max(0.0, original - penalty), 2)
            metrics = evaluation.setdefault("metrics", {})
            metrics["constraint_penalty"] = penalty
            metrics["constraints_missed"] = int(constraint_assessment.get("missed_constraints", 0) or 0)
            metrics["failed_constraints"] = list(constraint_assessment.get("failed_rules", []))
        # Always apply constraint penalty so score reflects real output quality.
        base_score_before_tuning = float(evaluation.get("final_score", 0.0) or 0.0)
        universal_missed = int(constraint_assessment.get("missed_constraints", 0) or 0)
        constraint_adherence = _constraint_adherence_score(total_constraints, universal_missed)
        constraint_penalty_weight = float(tuning.get("constraint_penalty_weight", 16.0))
        clarity_penalty_weight = float(tuning.get("clarity_penalty_weight", 34.0))
        reward_multiplier = float(tuning.get("reward_multiplier", 1.0))
        universal_penalty = int(round(universal_missed * constraint_penalty_weight))
        clarity_score_penalty = int(round(max(0.0, 0.55 - float(clarity_score)) * clarity_penalty_weight))
        vague_instruction_penalty = int(round(max(0.0, 0.45 - float(clarity_score)) * (clarity_penalty_weight * 0.7)))
        adherence_bonus = int(round(max(0.0, constraint_adherence - 0.70) * 22.0 * reward_multiplier))
        if universal_penalty > 0:
            original_score = float(evaluation.get("final_score", 0.0) or 0.0)
            evaluation["final_score"] = round(max(0.0, original_score - universal_penalty), 2)
        if clarity_score_penalty > 0:
            original_score = float(evaluation.get("final_score", 0.0) or 0.0)
            evaluation["final_score"] = round(max(0.0, original_score - clarity_score_penalty), 2)
        if vague_instruction_penalty > 0:
            original_score = float(evaluation.get("final_score", 0.0) or 0.0)
            evaluation["final_score"] = round(max(0.0, original_score - vague_instruction_penalty), 2)
        if adherence_bonus > 0:
            original_score = float(evaluation.get("final_score", 0.0) or 0.0)
            evaluation["final_score"] = round(min(100.0, original_score + adherence_bonus), 2)
        metrics = evaluation.setdefault("metrics", {})
        metrics["constraints_missed"] = universal_missed
        metrics["failed_constraints"] = list(constraint_assessment.get("failed_rules", []))
        metrics["constraint_penalty"] = int(metrics.get("constraint_penalty", 0) or 0) + universal_penalty
        metrics["clarity_penalty"] = clarity_score_penalty
        metrics["vague_penalty"] = vague_instruction_penalty
        metrics["adherence_bonus"] = adherence_bonus
        missed_constraints = int(constraint_assessment.get("missed_constraints", 0) or 0)
        constraint_adherence = _constraint_adherence_score(total_constraints, missed_constraints)
        deviation_detected = bool(any(
            str(step.get("output", "")).startswith("DEVIATED_FROM_INSTRUCTIONS:")
            for step in workflow_results
        )) or bool(constraint_assessment.get("json_error", False))
        log_event(
            logger,
            "evaluation_result",
            task_id=task_id,
            run_id=run_id,
            final_score=evaluation.get("final_score"),
            cache_hit=bool(evaluation_payload.get("cache_hit", False)),
            missed_constraints=missed_constraints,
            constraint_adherence_score=round(constraint_adherence, 4),
            clarity_score=round(float(clarity_score), 4),
        )

        final_score_after_tuning = float(evaluation.get("final_score", 0.0) or 0.0)
        penalties = {
            "constraint_penalty": int(universal_penalty),
            "clarity_penalty": int(clarity_score_penalty),
            "vague_penalty": int(vague_instruction_penalty),
            "total_penalties": int(universal_penalty + clarity_score_penalty + vague_instruction_penalty),
        }
        rewards = {
            "adherence_bonus": int(adherence_bonus),
            "total_rewards": int(adherence_bonus),
        }
        score_breakdown = {
            "base_score": round(base_score_before_tuning, 2),
            "penalties": penalties,
            "rewards": rewards,
            "final_score": round(final_score_after_tuning, 2),
        }

        semantic_analysis = _build_semantic_analysis(
            clarity_score=float(clarity_score),
            constraints=list(task_config.get("constraints", []) or []),
            failed_rules=list(constraint_assessment.get("failed_rules", []) or []),
        )

        asset_payload = facade.asset_transform.to_asset(workflow_results, evaluation)
        if isinstance(asset_payload, dict):
            debug_payload = asset_payload.get("debug")
            if not isinstance(debug_payload, dict):
                debug_payload = {}
            debug_payload["semantic_analysis"] = semantic_analysis
            asset_payload["debug"] = debug_payload
        asset = serialize_asset(asset_type="business_plan", payload=asset_payload)
        asset_id = persist_asset(run_id=run_id, asset=asset, database_url=settings.database_url)
        log_event(logger, "asset_created", task_id=task_id, run_id=run_id, asset_id=asset_id,
                  asset_type=asset["asset_type"])

        affinity_updates = {}
        if hasattr(facade.agents, "update_affinity"):
            affinity_updates = facade.agents.update_affinity(workflow_results, run_success=True)

        update_run_status(
            run_id=run_id,
            status="success",
            database_url=settings.database_url,
            final_score=evaluation.get("final_score"),
            total_cost=total_cost,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            clarity_score=clarity_score,
            deviation_detected=deviation_detected,
            constraint_adherence_score=constraint_adherence,
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
            "status": "success",
            "total_cost": total_cost,
            "affinity_updates": affinity_updates,
            "constraint_assessment": constraint_assessment,
            "task_constraints": list(task_config.get("constraints", []) or []),
            "semantic_analysis": semantic_analysis,
            "score_breakdown": score_breakdown,
            "penalties": penalties,
            "effective_parameters": tuning,
            "player_feedback": _build_player_feedback(
                final_score=float(evaluation.get("final_score", 0.0) or 0.0),
                clarity_score=float(clarity_score),
                failed_rules=list(constraint_assessment.get("failed_rules", [])),
            ),
            "observability": {
                "run_id": run_id,
                "user_id": user_id,
                "task_id": task_id,
                "status": "success",
                "total_cost": total_cost,
                "total_tokens": total_tokens,
                "total_latency_ms": total_latency_ms,
                "clarity_score": clarity_score,
                "deviation_detected": deviation_detected,
                "constraint_adherence_score": constraint_adherence,
            },
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
                wallet_before=float(progression_context.get("wallet_before", 0.0) or 0.0),
                clarity_score=float(progression_context["clarity_score"]),
                evaluation_score=float(evaluation.get("final_score", 0.0) or 0.0),
                missed_constraints=int(result["comparison_fields"].get("missed_constraints", 0) or 0),
            )
            result["player_result"] = player_result
            result["player_feedback"] = _build_player_feedback(
                final_score=float(evaluation.get("final_score", 0.0) or 0.0),
                clarity_score=float(clarity_score),
                failed_rules=list(constraint_assessment.get("failed_rules", [])),
                additional_reasons=list(player_result.get("failure_reasons", []) or []),
            )
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
            status="success",
        )
        RUN_RUNTIME_STATE[run_id]["status"] = "success"
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
                    wallet_before=float(progression_ctx.get("wallet_before", 0.0) or 0.0),
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
        if isinstance(exc, TimeoutError):
            RUN_RUNTIME_STATE[run_id]["error_reason"] = "timeout"
        elif isinstance(exc, ExecutionError):
            RUN_RUNTIME_STATE[run_id]["error_reason"] = exc.code
        else:
            RUN_RUNTIME_STATE[run_id]["error_reason"] = "run_failed"
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
