"""Benchmark/debug utilities for task runner."""

from __future__ import annotations

from copy import deepcopy
from statistics import mean, pstdev
from typing import Dict, List, Optional
import time
import re

from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import resolve_module_name
from core_engine.tuning import get_tuning_overrides, set_tuning_overrides

from api.services.task_runner.core import _output_preview, run_task


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
        try:
            run_payload = run_task(
                task_id=task_id,
                module_name=selected_module,
                agent_overrides=overrides,
                model_overrides={f"task_{(agent_level or 'mid').lower()}": model_name},
            )
        except ExecutionError as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            failed_constraints = ["json_only"] if str(exc.code) == "parsing_failed" else []
            benchmark_results.append(
                {
                    "model": model_name,
                    "actual_models": [],
                    "actual_providers": [settings.get_provider("task")],
                    "fallback_detected": False,
                    "output_length": 0,
                    "missed_constraints": len(failed_constraints) or 1,
                    "deviation_detected": bool(failed_constraints),
                    "final_score": 0.0,
                    "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "cost": 0.0,
                    "latency_ms": latency_ms,
                    "failed_constraints": failed_constraints,
                    "error_reason": str(exc.code),
                }
            )
            benchmark_results[-1].update(_build_player_friendly_row(benchmark_results[-1]))
            continue
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        fields = run_payload.get("comparison_fields", {})
        benchmark_results.append(
            {
                "model": model_name,
                "actual_models": sorted(
                    {str(s.get("model", "")) for s in run_payload.get("workflow_results", []) if s.get("model")}),
                "actual_providers": sorted(
                    {str(s.get("provider", "")) for s in run_payload.get("workflow_results", []) if s.get("provider")}),
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


def benchmark_matrix(
        task_id: str,
        module_name: Optional[str] = None,
        agent_levels: Optional[List[str]] = None,
        models: Optional[List[str]] = None,
        user_instruction_variants: Optional[Dict[str, str]] = None,
        repeats: int = 1,
        task_definition: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Reusable benchmark matrix for observability/tuning."""
    settings = get_settings()
    if task_definition is not None and not bool(settings.allow_debug_task_definition_override):
        raise ValueError(
            "task_definition override is disabled. Use task_id-based benchmark for production-consistent results."
        )
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    facade = ModuleFacade.from_name(selected_module)
    levels = [str(x).lower() for x in (agent_levels or ["junior", "mid", "senior"])]
    levels = [x for x in levels if x in {"junior", "mid", "senior"}] or ["mid"]
    repeats = max(1, int(repeats or 1))
    variants = user_instruction_variants or {
        "vague": "Make it good.",
        "clear": """The target user is a white-collar worker, with a budget of 50,000 yuan, 
        and it will be launched in 3 months, and there must be pricing and risk control.""",
    }

    model_candidates = [str(m) for m in (models or []) if str(m).strip()]
    if not model_candidates:
        model_candidates = sorted({settings.get_model_for_role("task", level) for level in levels})

    agent_names = list(getattr(facade.agents, "AGENTS", {}).keys())

    runs: List[Dict[str, object]] = []
    for level in levels:
        overrides = {name: {"level": level} for name in agent_names}
        for model_name in model_candidates:
            for variant_name, instruction in variants.items():
                for idx in range(repeats):
                    started_at = time.perf_counter()
                    try:
                        payload = run_task(
                            task_id=task_id,
                            module_name=selected_module,
                            agent_overrides=overrides,
                            model_overrides={f"task_{level}": model_name},
                            instructions=str(instruction or ""),
                            task_definition_override=task_definition,
                        )
                    except ExecutionError:
                        payload = {"storage": {"run_id": ""}, "comparison_fields": {}, "workflow_results": []}
                    latency_ms = int((time.perf_counter() - started_at) * 1000)
                    fields = payload.get("comparison_fields", {})
                    token_usage = fields.get("token_usage", {}) if isinstance(fields.get("token_usage"), dict) else {}
                    workflow_steps = payload.get("workflow_results", [])
                    final_output = str(workflow_steps[-1].get("output", "")) if isinstance(workflow_steps,
                                                                                           list) and workflow_steps else ""
                    assessment = payload.get("constraint_assessment", {})
                    failed_rules = list(assessment.get("failed_rules", [])) if isinstance(assessment, dict) else []
                    constraints = list(payload.get("task_constraints", [])) if isinstance(
                        payload.get("task_constraints"), list) else []
                    misses_norm = {str(x).strip().lower() for x in failed_rules}
                    constraint_hits = [c for c in constraints if str(c).strip().lower() not in misses_norm]
                    run_item = {
                        "agent_level": level,
                        "model": model_name,
                        "instruction_variant": str(variant_name),
                        "repeat_index": idx + 1,
                        "run_id": str(payload.get("storage", {}).get("run_id", "")),
                        "prompt_length": len(str(instruction or "")),
                        "raw_output": final_output,
                        "constraint_hits": constraint_hits,
                        "constraint_misses": failed_rules,
                        "clarity_score": float(payload.get("observability", {}).get("clarity_score", 0.0) or 0.0),
                        "score_breakdown": payload.get("score_breakdown", {}),
                        "penalties": payload.get("penalties", {}),
                        "effective_parameters": payload.get("effective_parameters", {}),
                        "metrics": {
                            "output_length": int(fields.get("output_length", 0) or 0),
                            "missed_constraints": int(fields.get("missed_constraints", 0) or 0),
                            "deviation_detected": bool(fields.get("deviation_detected", False)),
                            "final_score": float(fields.get("final_score", 0.0) or 0.0),
                            "token_usage": {
                                "prompt_tokens": int(token_usage.get("prompt_tokens", 0) or 0),
                                "completion_tokens": int(token_usage.get("completion_tokens", 0) or 0),
                                "total_tokens": int(token_usage.get("total_tokens", 0) or 0),
                            },
                            "cost": float(fields.get("cost", 0.0) or 0.0),
                            "latency_ms": latency_ms,
                        },
                    }
                    run_item.update(_output_preview(final_output))
                    runs.append(run_item)

    grouped: Dict[tuple, List[Dict[str, object]]] = {}
    for item in runs:
        key = (item["agent_level"], item["model"], item["instruction_variant"])
        grouped.setdefault(key, []).append(item["metrics"])

    aggregates: List[Dict[str, object]] = []
    for (level, model, variant), items in grouped.items():
        def vals(name: str) -> List[float]:
            return [float(x.get(name, 0.0) or 0.0) for x in items]

        output_lengths = vals("output_length")
        missed = vals("missed_constraints")
        final_scores = vals("final_score")
        tokens = [float(x.get("token_usage", {}).get("total_tokens", 0.0) or 0.0) for x in items]
        costs = vals("cost")
        latency = vals("latency_ms")
        deviations = [1.0 if bool(x.get("deviation_detected", False)) else 0.0 for x in items]

        def _agg(values: List[float]) -> Dict[str, float]:
            return {
                "avg": round(sum(values) / max(1, len(values)), 4),
                "min": round(min(values), 4) if values else 0.0,
                "max": round(max(values), 4) if values else 0.0,
            }

        aggregates.append(
            {
                "agent_level": level,
                "model": model,
                "instruction_variant": variant,
                "metrics": {
                    "output_length": _agg(output_lengths),
                    "missed_constraints": _agg(missed),
                    "deviation_detected_rate": _agg(deviations),
                    "final_score": _agg(final_scores),
                    "token_usage": _agg(tokens),
                    "cost": _agg(costs),
                    "latency_ms": _agg(latency),
                },
            }
        )

    return {
        "task_id": task_id,
        "module_name": selected_module,
        "runs": runs,
        "aggregates": aggregates,
    }


def tuning_parameter_scan(
        task_id: str,
        module_name: Optional[str] = None,
        clarity_penalty_weights: Optional[List[float]] = None,
        constraint_penalty_weights: Optional[List[float]] = None,
        reward_multipliers: Optional[List[float]] = None,
        models: Optional[List[str]] = None,
) -> Dict[str, object]:
    settings = get_settings()
    selected_module = resolve_module_name(module_name, settings.active_game_module)
    original_overrides = get_tuning_overrides()

    clarity_values = [float(x) for x in (clarity_penalty_weights or [28.0, 34.0, 40.0])]
    constraint_values = [float(x) for x in (constraint_penalty_weights or [12.0, 16.0, 20.0])]
    reward_values = [float(x) for x in (reward_multipliers or [0.9, 1.0, 1.1])]

    variants = {
        "vague": "Make a quick plan.",
        "clear": "Targeting urban professionals and white-collar users. Include pricing, risk factors, and milestones.",
    }
    ranked: List[Dict[str, object]] = []

    try:
        for clarity_w in clarity_values:
            for constraint_w in constraint_values:
                for reward_m in reward_values:
                    patched = deepcopy(original_overrides)
                    patched.update(
                        {
                            "clarity_penalty_weight": clarity_w,
                            "constraint_penalty_weight": constraint_w,
                            "reward_multiplier": reward_m,
                        }
                    )
                    effective = set_tuning_overrides(patched, settings)
                    bench = benchmark_matrix(
                        task_id=task_id,
                        module_name=selected_module,
                        agent_levels=["junior", "senior"],
                        models=models,
                        user_instruction_variants=variants,
                        repeats=3,
                    )
                    runs = bench.get("runs", []) if isinstance(bench.get("runs"), list) else []
                    grouped: Dict[tuple[str, str], List[float]] = {}
                    all_scores: List[float] = []
                    for item in runs:
                        level = str(item.get("agent_level", "mid"))
                        variant = str(item.get("instruction_variant", "vague"))
                        score = float(item.get("metrics", {}).get("final_score", 0.0) or 0.0)
                        grouped.setdefault((level, variant), []).append(score)
                        all_scores.append(score)

                    def avg(level: str, variant: str) -> float:
                        vals = grouped.get((level, variant), [])
                        return float(mean(vals)) if vals else 0.0

                    junior_vague = avg("junior", "vague")
                    junior_clear = avg("junior", "clear")
                    senior_vague = avg("senior", "vague")
                    senior_clear = avg("senior", "clear")

                    clarity_gap_junior = junior_clear - junior_vague
                    clarity_gap_senior = senior_clear - senior_vague
                    clarity_gap_strength = (clarity_gap_junior + clarity_gap_senior) / 2.0
                    agent_gap_vague = senior_vague - junior_vague
                    agent_gap_clear = senior_clear - junior_clear
                    agent_gap_strength = (agent_gap_vague + agent_gap_clear) / 2.0
                    score_min = min(all_scores) if all_scores else 0.0
                    score_max = max(all_scores) if all_scores else 0.0
                    score_std = float(pstdev(all_scores)) if len(all_scores) > 1 else 0.0
                    score_range = score_max - score_min

                    rank_score = round(
                        (clarity_gap_strength * 0.5)
                        + (agent_gap_strength * 0.4)
                        + (score_range * 0.1),
                        4,
                    )
                    ranked.append(
                        {
                            "rank_score": rank_score,
                            "parameters": {
                                "clarity_penalty_weight": clarity_w,
                                "constraint_penalty_weight": constraint_w,
                                "reward_multiplier": reward_m,
                            },
                            "effective_parameters": effective,
                            "average_scores": {
                                "junior": {"vague": round(junior_vague, 2), "clear": round(junior_clear, 2)},
                                "senior": {"vague": round(senior_vague, 2), "clear": round(senior_clear, 2)},
                            },
                            "clarity_gaps": {
                                "junior": round(clarity_gap_junior, 2),
                                "senior": round(clarity_gap_senior, 2),
                                "strength": round(clarity_gap_strength, 2),
                            },
                            "senior_vs_junior_gaps": {
                                "vague": round(agent_gap_vague, 2),
                                "clear": round(agent_gap_clear, 2),
                                "strength": round(agent_gap_strength, 2),
                            },
                            "score_distribution": {
                                "min": round(score_min, 2),
                                "max": round(score_max, 2),
                                "range": round(score_range, 2),
                                "stddev": round(score_std, 2),
                            },
                        }
                    )
    finally:
        set_tuning_overrides(original_overrides, settings)

    ranked.sort(key=lambda item: float(item.get("rank_score", 0.0) or 0.0), reverse=True)
    return {
        "task_id": task_id,
        "module_name": selected_module,
        "fixed_setup": {
            "agent_levels": ["junior", "senior"],
            "instruction_variants": ["vague", "clear"],
            "repeats": 3,
        },
        "scan_space": {
            "clarity_penalty_weight": clarity_values,
            "constraint_penalty_weight": constraint_values,
            "reward_multiplier": reward_values,
        },
        "top_configs": ranked[:3],
        "results_ranked": ranked,
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
    junior_overrides = {name: {"level": "junior", "obedience": 0.82, "initiative": 0.30, "effort": 0.35} for name in
                        agent_names}
    senior_overrides = {name: {"level": "senior", "obedience": 0.42, "initiative": 0.80, "effort": 0.75} for name in
                        agent_names}
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
