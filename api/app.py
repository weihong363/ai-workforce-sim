"""FastAPI routes for running tasks and reading persisted data."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

import structlog
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.run_task import (
    benchmark_models,
    debug_compare_agents,
    get_runtime_run,
    init_runtime_run,
    mark_runtime_failed,
    run_task,
)
from api.schemas import BenchmarkRequest, ErrorResponse, RunTaskRequest
from api.users import router as users_router
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.logging_utils import setup_logging
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import ModuleLoadError
from core_engine.result_store import create_run, get_asset, get_run

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize logging
setup_logging(level="INFO", json_format=True)


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
def run_task_route(request: RunTaskRequest, background_tasks: BackgroundTasks) -> dict:
    settings = get_settings()
    try:
        selected_module = settings.active_game_module
        run_id = create_run(
            task_id=request.task_id,
            module_name=selected_module,
            database_url=settings.database_url,
        )
        init_runtime_run(run_id=run_id, task_id=request.task_id, module_name=selected_module)

        def _background_execute() -> None:
            try:
                run_task(
                    task_id=request.task_id,
                    module_name=selected_module,
                    run_id_override=run_id,
                    user_id=request.user_id,
                    instructions=request.instructions,
                )
            except Exception as exc:  # pragma: no cover - defensive background path
                mark_runtime_failed(run_id=run_id, error=str(exc), code=type(exc).__name__)

        background_tasks.add_task(_background_execute)
        return {"run_id": run_id, "status": "pending"}
    except (ValueError, ModuleLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExecutionError as exc:
        status_code = 400 if exc.code in {"task_locked", "insufficient_wallet"} else 500
        raise HTTPException(status_code=status_code, detail=exc.to_dict()) from exc


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
        return merged

    if runtime is not None and runtime.get("result"):
        merged = dict(run)
        runtime_result = runtime.get("result", {})
        if isinstance(runtime_result, dict) and "player_result" in runtime_result:
            merged["player_result"] = runtime_result["player_result"]
        return merged

    return run


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
