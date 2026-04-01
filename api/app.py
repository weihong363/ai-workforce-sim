"""FastAPI application wiring and lifecycle setup."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.agents import router as agents_router
from api.routes.debug import router as debug_router
from api.routes.game import router as game_router
from api.routes.pages import router as pages_router
from api.routes.runs import router as runs_router
from api.routes.system import router as system_router
from api.routes.tasks import router as tasks_router
from api.routes.users import router as users_router
from core_engine.bootstrap import validate_runtime_storage
from core_engine.config import get_settings
from core_engine.logging_utils import setup_logging

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize logging
setup_logging(level="INFO", json_format=True)


def _redact_db_url(database_url: str) -> str:
    try:
        parsed = urlparse(database_url)
        if not parsed.scheme:
            return "<unset>"
        netloc = parsed.netloc
        if "@" in netloc:
            credentials, host = netloc.rsplit("@", 1)
            username = credentials.split(":", 1)[0] if credentials else ""
            redacted_credentials = f"{username}:***" if username else "***"
            netloc = f"{redacted_credentials}@{host}"
        return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
    except Exception:
        return "<redacted>"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events.

    Startup validates storage readiness only (read-only); it does not create
    schema or seed data. Use scripts/bootstrap_storage.py explicitly.
    """
    settings = get_settings()

    setup_logging(level="INFO", json_format=True)
    logger = structlog.get_logger(__name__)
    app.state.database_initialized = False
    app.state.user_database_initialized = False
    app.state.agent_database_initialized = False
    app.state.cache_initialized = False

    logger.info("[API] Validating runtime storage", database_url=_redact_db_url(settings.database_url))
    try:
        stats = validate_runtime_storage(
            database_url=settings.database_url,
            module_name=settings.active_game_module,
        )
        app.state.database_initialized = bool(stats.get("database_initialized", False))
        app.state.user_database_initialized = bool(stats.get("user_database_initialized", False))
        app.state.agent_database_initialized = bool(stats.get("agent_database_initialized", False))
        app.state.task_catalog_initialized = bool(stats.get("task_catalog_initialized", False))
        if app.state.database_initialized and app.state.user_database_initialized and app.state.task_catalog_initialized:
            logger.info(
                "[API] Runtime storage validation passed",
                module_name=settings.active_game_module,
                seeded_tasks=int(stats.get("seeded_tasks", 0)),
            )
        else:
            logger.warning(
                "[API] Runtime storage not ready; run scripts/bootstrap_storage.py or scripts/init_user_db.py",
                module_name=settings.active_game_module,
                details=stats,
            )
    except Exception as exc:
        app.state.database_initialized = False
        app.state.user_database_initialized = False
        app.state.agent_database_initialized = False
        app.state.task_catalog_initialized = False
        logger.warning("[API] Runtime storage validation failed; continuing in degraded mode", error=str(exc))

    logger.info("[API] Initializing Redis cache", redis_url=settings.redis_url)
    from core_engine.cache import init_cache

    try:
        init_cache(
            settings.redis_url,
            agent_cache_ttl_seconds=settings.agent_cache_ttl_seconds,
            evaluation_cache_ttl_seconds=settings.evaluation_cache_ttl_seconds,
            temp_result_ttl_seconds=settings.temp_result_ttl_seconds,
        )
        app.state.cache_initialized = True
        logger.info("[API] Redis cache initialized successfully")
    except Exception as exc:
        logger.warning("[API] Redis cache initialization failed; continuing with in-memory cache", error=str(exc))

    yield


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

app.include_router(system_router)
app.include_router(pages_router)
app.include_router(game_router)
app.include_router(tasks_router)
app.include_router(agents_router)
app.include_router(runs_router)
app.include_router(debug_router)
app.include_router(users_router)
