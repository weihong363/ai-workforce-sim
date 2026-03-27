"""FastAPI routes for running tasks and reading persisted data."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from api.run_task import run_task
from api.schemas import ErrorResponse, RunTaskRequest
from core_engine.config import get_settings
from core_engine.errors import ExecutionError
from core_engine.module_loader import ModuleLoadError
from core_engine.result_store import get_asset, get_run

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
print(f"[API] Loaded environment from: {env_path}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    settings = get_settings()
    from core_engine.result_store import init_db
    
    # Initialize database
    print(f"[API] Initializing database: {settings.database_url}")
    init_db(settings.database_url)
    print(f"[API] Database initialized successfully")
    
    # Initialize Redis cache
    print(f"[API] Initializing Redis cache: {settings.redis_url}")
    from core_engine.cache import init_cache
    init_cache(settings.redis_url)
    print(f"[API] Redis cache initialized successfully")
    
    yield
    # Shutdown (if needed in future)


app = FastAPI(title="AI Workforce Sim MVP API", lifespan=lifespan)


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
        "database_initialized": True,
    }


@app.post("/run-task", responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def run_task_route(request: RunTaskRequest) -> dict:
    try:
        return run_task(task_name=request.task_name, module_name=request.module_name)
    except (ValueError, ModuleLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExecutionError as exc:
        raise HTTPException(status_code=500, detail=exc.to_dict()) from exc


@app.get("/runs/{run_id}", responses={404: {"model": ErrorResponse}})
def get_run_route(run_id: str) -> dict:
    settings = get_settings()
    run = get_run(run_id, settings.database_url)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return run


@app.get("/assets/{asset_id}", responses={404: {"model": ErrorResponse}})
def get_asset_route(asset_id: str) -> dict:
    settings = get_settings()
    asset = get_asset(asset_id, settings.database_url)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found.")
    return asset
