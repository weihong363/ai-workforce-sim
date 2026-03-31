"""Debug and benchmark endpoints."""

from fastapi import APIRouter, HTTPException, Path, Query

from api.run_task import benchmark_models, debug_compare_agents, tuning_parameter_scan
from api.schemas import BenchmarkMatrixRequest, BenchmarkRequest, DebugTuningPatchRequest, TuningScanRequest
from api.services.run_preview import with_output_previews
from core_engine.config import get_settings
from core_engine.result_store import get_run
from core_engine.tuning import get_effective_tuning, get_tuning_overrides, update_tuning

router = APIRouter(tags=["debug"])


@router.get(
    "/debug/compare",
    summary="Compare Junior vs Senior",
    description="Run the same task with junior/senior presets and return comparison diagnostics.",
)
def debug_compare_route(
        task_id: str = Query(..., min_length=1, description="Task ID used for comparison")
) -> dict:
    settings = get_settings()
    try:
        return debug_compare_agents(task_id=task_id, module_name=settings.active_game_module)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/debug/benchmark-models",
    summary="Benchmark Candidate Models",
    description="Benchmark one task against multiple models for a selected agent level.",
)
def benchmark_models_route(request: BenchmarkRequest) -> dict:
    settings = get_settings()
    try:
        return benchmark_models(
            task_id=request.task_id,
            module_name=settings.active_game_module,
            agent_level=request.agent_level,
            models=request.models,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/debug/benchmark",
    summary="Run Benchmark Matrix",
    description="Run benchmark matrix across levels/instructions/models with optional task override.",
)
def benchmark_matrix_route(request: BenchmarkMatrixRequest) -> dict:
    settings = get_settings()
    try:
        from api.run_task import benchmark_matrix

        return benchmark_matrix(
            task_id=request.task_id,
            module_name=settings.active_game_module,
            agent_levels=request.agent_levels,
            models=request.models,
            user_instruction_variants=request.user_instruction_variants.model_dump(exclude_none=True),
            repeats=request.repeats,
            task_definition=request.task_definition.model_dump(exclude_none=True) if request.task_definition else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/debug/tuning",
    summary="Get Runtime Tuning",
    description="Return effective tuning parameters plus current override patch.",
)
def get_tuning_route() -> dict:
    settings = get_settings()
    return {
        "effective_parameters": get_effective_tuning(settings),
        "overrides": get_tuning_overrides(),
    }


@router.patch(
    "/debug/tuning",
    summary="Patch Runtime Tuning",
    description="Patch runtime tuning values used by scoring/behavior simulation.",
)
def patch_tuning_route(request: DebugTuningPatchRequest) -> dict:
    settings = get_settings()
    patch = {k: v for k, v in request.model_dump(exclude_none=True).items()}
    try:
        effective = update_tuning(patch, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "effective_parameters": effective,
        "overrides": get_tuning_overrides(),
    }


@router.post(
    "/debug/tuning-scan",
    summary="Scan Tuning Parameters",
    description="Run a lightweight parameter scan for tuning values on one task.",
)
def tuning_scan_route(request: TuningScanRequest) -> dict:
    settings = get_settings()
    try:
        return tuning_parameter_scan(
            task_id=request.task_id,
            module_name=settings.active_game_module,
            clarity_penalty_weights=request.clarity_penalty_weights,
            constraint_penalty_weights=request.constraint_penalty_weights,
            reward_multipliers=request.reward_multipliers,
            models=request.models,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/debug/run/{run_id}",
    summary="Get Run Debug Detail",
    description="Return run-level debug detail including step previews and behavior/cost analysis.",
)
def debug_run_route(
        run_id: str = Path(..., min_length=1, description="Run ID")
) -> dict:
    settings = get_settings()
    try:
        run = get_run(run_id, settings.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    preview_run = with_output_previews(run)
    steps = preview_run.get("workflow_steps", []) if isinstance(preview_run.get("workflow_steps"), list) else []
    agent_effects: dict = {}
    cost_breakdown_by_model: dict = {}
    total_step_cost = 0.0
    total_step_tokens = 0
    total_step_latency = 0

    for step in steps:
        if not isinstance(step, dict):
            continue
        agent = str(step.get("agent_name", "unknown"))
        eff = step.get("effective_attributes", {}) if isinstance(step.get("effective_attributes"), dict) else {}
        token_usage = step.get("token_usage", {}) if isinstance(step.get("token_usage"), dict) else {}
        cost = float(step.get("cost", 0.0) or 0.0)
        latency = int(step.get("latency_ms", 0) or 0)
        tokens = int(token_usage.get("total_tokens", 0) or 0)
        total_step_cost += cost
        total_step_tokens += tokens
        total_step_latency += latency

        bucket = agent_effects.setdefault(
            agent,
            {"steps": 0, "cost": 0.0, "tokens": 0, "latency_ms": 0,
             "avg_traits": {"obedience": 0.0, "initiative": 0.0, "effort": 0.0, "affinity": 0.0}},
        )
        bucket["steps"] += 1
        bucket["cost"] += cost
        bucket["tokens"] += tokens
        bucket["latency_ms"] += latency
        for key in ("obedience", "initiative", "effort", "affinity"):
            bucket["avg_traits"][key] += float(eff.get(key, 0.0) or 0.0)

        mk = f"{step.get('provider', 'unknown')}::{step.get('model', 'unknown')}"
        model_bucket = cost_breakdown_by_model.setdefault(mk, {"cost": 0.0, "tokens": 0, "steps": 0})
        model_bucket["cost"] += cost
        model_bucket["tokens"] += tokens
        model_bucket["steps"] += 1

    for _, bucket in agent_effects.items():
        n = max(1, int(bucket["steps"]))
        for key in ("obedience", "initiative", "effort", "affinity"):
            bucket["avg_traits"][key] = round(float(bucket["avg_traits"][key]) / n, 4)
        bucket["cost"] = round(float(bucket["cost"]), 8)

    run_summary = {
        "run_id": run.get("run_id"),
        "user_id": run.get("user_id"),
        "task_id": run.get("task_id"),
        "status": run.get("status"),
        "total_cost": run.get("total_cost"),
        "total_tokens": run.get("total_tokens"),
        "total_latency_ms": run.get("total_latency_ms"),
    }

    behavior_analysis = {
        "clarity_score": run.get("clarity_score"),
        "deviation_detected": run.get("deviation_detected"),
        "constraint_adherence_score": run.get("constraint_adherence_score"),
        "final_score": run.get("final_score"),
        "semantic_analysis": run.get("semantic_analysis", {}),
        "score_breakdown": run.get("score_breakdown", {}),
        "penalties": run.get("penalties", {}),
        "effective_parameters": run.get("effective_parameters", {}),
    }

    cost_breakdown = {
        "total_cost_from_steps": round(total_step_cost, 8),
        "total_tokens_from_steps": total_step_tokens,
        "total_latency_ms_from_steps": total_step_latency,
        "by_model": cost_breakdown_by_model,
    }

    return {
        "run_summary": run_summary,
        "steps": steps,
        "agent_effects": agent_effects,
        "cost_breakdown": cost_breakdown,
        "behavior_analysis": behavior_analysis,
    }
