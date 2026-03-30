"""FastAPI routes for running tasks and reading persisted data."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import AsyncGenerator, Optional

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.run_task import (
    benchmark_models,
    debug_compare_agents,
    get_runtime_run,
    run_task,
    tuning_parameter_scan,
)
from api.schemas import BenchmarkMatrixRequest, BenchmarkRequest, ErrorResponse, RunTaskRequest
from api.schemas import DebugTuningPatchRequest, TuningScanRequest
from api.users import router as users_router
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.logging_utils import setup_logging
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import ModuleLoadError
from core_engine.result_store import get_asset, get_run
from core_engine.tuning import get_effective_tuning, get_tuning_overrides, update_tuning

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize logging
setup_logging(level="INFO", json_format=True)
OUTPUT_PREVIEW_CHARS = 280


def _preview_text(value: object, limit: int = OUTPUT_PREVIEW_CHARS) -> tuple[str, bool, int]:
    raw = str(value or "")
    truncated = len(raw) > limit
    return (raw[:limit] + (" ..." if truncated else ""), truncated, len(raw))


def _with_output_previews(run_payload: dict) -> dict:
    payload = dict(run_payload)
    steps = payload.get("workflow_steps", [])
    if not isinstance(steps, list):
        return payload
    rewritten = []
    for step in steps:
        if not isinstance(step, dict):
            rewritten.append(step)
            continue
        copied = dict(step)
        preview, truncated, full_len = _preview_text(copied.get("output", ""))
        copied["output"] = preview
        copied["raw_output_preview"] = preview
        copied["full_output_length"] = full_len
        copied["truncated_for_display"] = truncated
        copied["stored_full_output"] = True
        rewritten.append(copied)
    payload["workflow_steps"] = rewritten
    return payload


def _suggestions_from_issues(issues: list[str]) -> list[str]:
    suggestions: list[str] = []
    for issue in issues:
        text = str(issue).lower()
        if "vague" in text:
            suggestions.append("Add concrete target customer, budget, timeline, and measurable goals.")
        elif "constraint" in text or "missing" in text:
            suggestions.append("Explicitly include all required constraints in your instruction.")
        elif "timeout" in text:
            suggestions.append("Retry with shorter prompt scope or after checking provider latency.")
        elif "insufficient wallet" in text:
            suggestions.append("Choose a lower-cost task or increase wallet balance before retrying.")
        elif "output" in text:
            suggestions.append("Retry with clearer instructions and explicit expected format.")
    if not suggestions:
        suggestions.append("Retry with clearer and more specific instructions.")
    deduped: list[str] = []
    seen = set()
    for item in suggestions:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _build_run_task_user_response(result: dict) -> dict:
    player_result = result.get("player_result", {}) if isinstance(result, dict) else {}
    player_feedback = result.get("player_feedback", {}) if isinstance(result, dict) else {}
    issues = list(player_feedback.get("failure_reasons", []) or [])
    success = bool(player_result.get("success", False))
    if not success and not issues:
        issues = ["output quality below threshold"]
    summary = str(player_result.get("explanation") or ("Task succeeded." if success else "Task failed."))
    return {
        "success": success,
        "run_id": str(result.get("storage", {}).get("run_id", "")),
        "score": float(result.get("evaluation", {}).get("final_score", 0.0) or 0.0),
        "reward": float(player_result.get("reward_gained", 0.0) or 0.0),
        "cost": float(player_result.get("cost_spent", result.get("total_cost", 0.0)) or 0.0),
        "status": "success" if success else "failed",
        "summary": summary,
        "feedback": {
            "issues": issues,
            "suggestions": _suggestions_from_issues(issues),
        },
    }


def _build_failed_run_task_response(exc: ExecutionError) -> dict:
    details = dict(exc.details or {})
    run_id = str(details.get("run_id", ""))
    summary = str(exc.message or "Run failed.")
    issues = [summary]
    return {
        "success": False,
        "run_id": run_id,
        "score": 0.0,
        "reward": 0.0,
        "cost": 0.0,
        "status": "failed",
        "summary": summary,
        "error_reason": str(exc.code or "run_failed"),
        "feedback": {
            "issues": issues,
            "suggestions": _suggestions_from_issues([str(exc.code or ""), summary]),
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    settings = get_settings()
    from core_engine.result_store import init_db
    from core_engine.user_store import init_user_db
    from core_engine.agent_store import init_agent_db, seed_module_agents
    
    # Initialize databases
    setup_logging(level="INFO", json_format=True)
    logger = structlog.get_logger(__name__)
    app.state.database_initialized = False
    app.state.user_database_initialized = False
    app.state.agent_database_initialized = False
    app.state.cache_initialized = False

    logger.info("[API] Initializing main database", database_url=settings.database_url)
    try:
        init_db(settings.database_url)
        app.state.database_initialized = True
        logger.info("[API] Main database initialized successfully")
    except Exception as exc:
        logger.warning("[API] Main database initialization failed; continuing in degraded mode", error=str(exc))
    
    logger.info("[API] Initializing user database", database_url=settings.database_url)
    try:
        init_user_db(settings.database_url)
        app.state.user_database_initialized = True
        logger.info("[API] User database initialized successfully")
    except Exception as exc:
        logger.warning("[API] User database initialization failed; continuing in degraded mode", error=str(exc))

    logger.info("[API] Initializing agent catalog", database_url=settings.database_url)
    try:
        init_agent_db(settings.database_url)
        app.state.agent_database_initialized = True
        logger.info("[API] Agent catalog initialized successfully")
    except Exception as exc:
        app.state.agent_database_initialized = False
        logger.warning("[API] Agent catalog initialization failed; continuing in degraded mode", error=str(exc))

    if app.state.database_initialized:
        try:
            # Trigger module task catalog bootstrap (table init + seed tasks).
            facade = ModuleFacade.from_name(settings.active_game_module)
            facade.list_tasks()
            if bool(getattr(app.state, "agent_database_initialized", False)):
                seed_module_agents(
                    settings.database_url,
                    settings.active_game_module,
                    getattr(facade.agents, "AGENTS", {}),
                )
            logger.info("[API] Task catalog initialized", module_name=settings.active_game_module)
        except Exception as exc:
            logger.warning("[API] Task catalog initialization failed", error=str(exc))
    
    # Initialize Redis cache
    logger.info("[API] Initializing Redis cache", redis_url=settings.redis_url)
    from core_engine.cache import init_cache
    try:
        init_cache(settings.redis_url)
        app.state.cache_initialized = True
        logger.info("[API] Redis cache initialized successfully")
    except Exception as exc:
        logger.warning("[API] Redis cache initialization failed; continuing with in-memory cache", error=str(exc))
    
    yield
    # Shutdown (if needed in future)


app = FastAPI(title="AI Workforce Sim MVP API", lifespan=lifespan)

# CORS for local frontend development and configurable deployments.
_cors_origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
if _cors_origins_raw == "*":
    _cors_origins = ["*"]
else:
    _cors_origins = [item.strip() for item in _cors_origins_raw.split(",") if item.strip()]
if not _cors_origins:
    _cors_origins = ["*"]
_cors_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include user management routes
app.include_router(users_router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "active_game_module": settings.active_game_module,
        "use_mock_provider": settings.use_mock_provider,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "redis_url": settings.redis_url,
        "database_initialized": bool(getattr(app.state, "database_initialized", False)),
        "user_database_initialized": bool(getattr(app.state, "user_database_initialized", False)),
        "agent_database_initialized": bool(getattr(app.state, "agent_database_initialized", False)),
        "cache_initialized": bool(getattr(app.state, "cache_initialized", False)),
    }


@app.post("/run-task", responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def run_task_route(request: RunTaskRequest) -> dict:
    settings = get_settings()
    try:
        selected_module = settings.active_game_module
        result = run_task(
            task_id=request.task_id,
            module_name=selected_module,
            user_id=request.user_id,
            instructions=request.instructions,
        )
        return _build_run_task_user_response(result)
    except (ValueError, ModuleLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExecutionError as exc:
        if exc.code in {"task_locked", "insufficient_wallet", "invalid_model_output", "evaluation_failed"}:
            return _build_failed_run_task_response(exc)
        raise HTTPException(status_code=500, detail=exc.to_dict()) from exc


@app.get("/runs/{run_id}", responses={404: {"model": ErrorResponse}})
def get_run_route(run_id: str) -> dict:
    settings = get_settings()
    try:
        runtime = get_runtime_run(run_id)
        run = get_run(run_id, settings.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run is None and runtime is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    if run is None:
        return runtime

    if runtime is not None and runtime.get("status") in {"pending", "running"}:
        merged = dict(run)
        merged["status"] = runtime.get("status", run.get("status"))
        merged["workflow_steps"] = runtime.get("workflow_steps", run.get("workflow_steps", []))
        merged["total_cost"] = runtime.get("total_cost", run.get("total_cost", 0.0))
        return _with_output_previews(merged)

    if runtime is not None and runtime.get("result"):
        merged = dict(run)
        runtime_result = runtime.get("result", {})
        if isinstance(runtime_result, dict):
            for key in ("player_result", "score_breakdown", "penalties", "effective_parameters", "semantic_analysis"):
                if key in runtime_result:
                    merged[key] = runtime_result[key]
        return _with_output_previews(merged)

    return _with_output_previews(run)


@app.get("/assets/{asset_id}", responses={404: {"model": ErrorResponse}})
def get_asset_route(asset_id: str) -> dict:
    settings = get_settings()
    try:
        asset = get_asset(asset_id, settings.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found.")
    return asset


@app.get("/debug/compare")
def debug_compare_route(task_id: str) -> dict:
    settings = get_settings()
    try:
        return debug_compare_agents(task_id=task_id, module_name=settings.active_game_module)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/debug/benchmark-models")
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


@app.post("/debug/benchmark")
def benchmark_matrix_route(request: BenchmarkMatrixRequest) -> dict:
    settings = get_settings()
    try:
        from api.run_task import benchmark_matrix

        return benchmark_matrix(
            task_id=request.task_id,
            module_name=settings.active_game_module,
            agent_levels=request.agent_levels,
            models=request.models,
            user_instruction_variants=request.user_instruction_variants,
            repeats=request.repeats,
            task_definition=request.task_definition,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/debug/tuning")
def get_tuning_route() -> dict:
    settings = get_settings()
    return {
        "effective_parameters": get_effective_tuning(settings),
        "overrides": get_tuning_overrides(),
    }


@app.get("/debug/tuning-ui")
def get_tuning_ui_route() -> FileResponse:
    ui_path = Path(__file__).parent / "static" / "tuning-ui.html"
    if not ui_path.exists():
        raise HTTPException(status_code=500, detail="tuning-ui.html not found")
    return FileResponse(path=ui_path, media_type="text/html")


@app.patch("/debug/tuning")
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


@app.post("/debug/tuning-scan")
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


@app.get("/debug/run/{run_id}")
def debug_run_route(run_id: str) -> dict:
    settings = get_settings()
    try:
        run = get_run(run_id, settings.database_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    preview_run = _with_output_previews(run)
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
            {"steps": 0, "cost": 0.0, "tokens": 0, "latency_ms": 0, "avg_traits": {"obedience": 0.0, "initiative": 0.0, "effort": 0.0, "affinity": 0.0}},
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
