"""System-level endpoints."""

from fastapi import APIRouter, Request

from core_engine.config import get_settings

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    summary="Health Check",
    description="Return API/module/provider/storage readiness status for local runtime.",
)
def health(request: Request) -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "active_game_module": settings.active_game_module,
        "use_mock_provider": settings.use_mock_provider,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "redis_url": settings.redis_url,
        "database_initialized": bool(getattr(request.app.state, "database_initialized", False)),
        "user_database_initialized": bool(getattr(request.app.state, "user_database_initialized", False)),
        "agent_database_initialized": bool(getattr(request.app.state, "agent_database_initialized", False)),
        "task_catalog_initialized": bool(getattr(request.app.state, "task_catalog_initialized", False)),
        "cache_initialized": bool(getattr(request.app.state, "cache_initialized", False)),
    }
