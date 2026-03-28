"""User management API endpoints."""

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CheckUsernameResponse,
    RegisterUserRequest,
    RegisterUserResponse,
)
from core_engine.config import get_settings
from core_engine.id_generator import generate_user_id
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import ModuleLoadError
import structlog

router = APIRouter(prefix="/users", tags=["users"])
logger = structlog.get_logger(__name__)

def _task_catalog_to_list(task_definitions: dict) -> list:
    """Convert task definition map into a stable, API-friendly list."""
    if not isinstance(task_definitions, dict):
        return []
    task_items = [{"task_id": name, **cfg} for name, cfg in task_definitions.items()]
    task_items.sort(
        key=lambda item: (
            0 if bool(item.get("is_tutorial", False)) else 1,
            int(item.get("tutorial_order", 9999)),
            str(item.get("task_id", "")),
        )
    )
    return task_items


def _list_or_empty(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _build_task_board_payload(user_id: str) -> dict:
    settings = get_settings()
    selected_module = settings.active_game_module
    facade = ModuleFacade.from_name(selected_module)

    task_definitions_raw = facade.list_tasks() if callable(getattr(facade, "list_tasks", None)) else {}
    task_definitions = task_definitions_raw if isinstance(task_definitions_raw, dict) else {}
    all_tasks = _task_catalog_to_list(task_definitions)

    progression = getattr(facade, "progression", None)
    board_raw = (
        progression.list_task_board(user_id=user_id, task_definitions=task_definitions)
        if progression is not None and callable(getattr(progression, "list_task_board", None))
        else {}
    )
    board = board_raw if isinstance(board_raw, dict) else {}

    tutorial_tasks = _list_or_empty(board.get("tutorial_tasks"))
    normal_tasks = _list_or_empty(board.get("normal_tasks"))
    available_tasks = _list_or_empty(board.get("available_tasks"))
    tasks = _list_or_empty(board.get("tasks")) or available_tasks

    payload = dict(board)
    payload.update(
        {
            "user_id": user_id,
            "module_name": selected_module,
            "locked": bool(board.get("locked", False)),
            "all_tasks": all_tasks,
            "tutorial_tasks": tutorial_tasks,
            "normal_tasks": normal_tasks,
            "available_tasks": available_tasks,
            "tasks": tasks,
        }
    )
    return payload

# Specific routes first (before parameterized routes)
@router.post("/register", response_model=RegisterUserResponse)
def register_user(request: RegisterUserRequest) -> dict:
    """Register a new user with username.

    Generates a unique user_id using ULID.
    """
    import structlog

    logger = structlog.get_logger(__name__)

    try:
        facade = ModuleFacade.from_name()
        progression = facade.progression
        if progression is None:
            raise RuntimeError("Progression component is unavailable.")

        # Check if username already exists
        if progression.check_username_exists(request.username):
            logger.warning("Username registration failed - already exists", username=request.username)
            raise HTTPException(
                status_code=400,
                detail=f"Username '{request.username}' already exists"
            )

        # Generate unique user ID
        user_id = generate_user_id()
        logger.info("Generated user ID", user_id=user_id, username=request.username)

        # Create user
        user_data = progression.init_user(user_id=user_id, username=request.username)
        if not isinstance(user_data, dict):
            raise RuntimeError("Progression init_user returned empty payload.")
        logger.info("User registered successfully", user_id=user_id, username=request.username)

        return {
            "user_id": user_data["user_id"],
            "username": user_data["username"],
            "wallet_balance": user_data["wallet_balance"],
            "created_at": user_data["created_at"],
        }
    except HTTPException:
        raise
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("User registration failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        ) from exc


@router.get("/check-username/{username}", response_model=CheckUsernameResponse)
def check_username(username: str) -> dict:
    """Check if a username is available."""
    import structlog

    logger = structlog.get_logger(__name__)

    try:
        facade = ModuleFacade.from_name()
        progression = facade.progression
        if progression is None:
            raise RuntimeError("Progression component is unavailable.")

        is_available = not progression.check_username_exists(username)
        logger.debug("Username check", username=username, available=is_available)
        return {
            "username": username,
            "available": is_available
        }
    except Exception as exc:
        logger.error("Username check failed", username=username, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        ) from exc


@router.get("/by-username/{username}")
def get_user_by_username(username: str) -> dict:
    """Get user data by username."""
    import structlog

    logger = structlog.get_logger(__name__)

    try:
        facade = ModuleFacade.from_name()
        progression = facade.progression
        if progression is None:
            raise RuntimeError("Progression component is unavailable.")

        user_data = progression.get_user_by_username(username)
        if user_data is None:
            logger.warning("User not found by username", username=username)
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")

        logger.info("User retrieved by username", username=username)
        return user_data
    except HTTPException:
        raise
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Get user by username failed", username=username, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        ) from exc


@router.get("/{user_id}")
def get_user(user_id: str) -> dict:
    """Get user data by ID."""
    import structlog

    logger = structlog.get_logger(__name__)

    try:
        facade = ModuleFacade.from_name()
        progression = facade.progression
        if progression is None:
            raise RuntimeError("Progression component is unavailable.")
        user_data = progression.get_user(user_id)
        if user_data is None:
            raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
        logger.info("User retrieved by ID", user_id=user_id)
        return user_data
    except HTTPException:
        raise
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Get user by ID failed", user_id=user_id, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        ) from exc


@router.get("/{user_id}/task-board")
def get_task_board(user_id: str) -> dict:
    """Get user's task board."""
    try:
        return _build_task_board_payload(user_id=user_id)
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Get task board failed", user_id=user_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.get("/{user_id}/tasks")
def get_all_tasks_for_user(user_id: str) -> dict:
    """Get full task catalog plus currently available tasks for a user."""
    try:
        board = _build_task_board_payload(user_id=user_id)
        return {
            "user_id": board["user_id"],
            "module_name": board["module_name"],
            "locked": board["locked"],
            "all_tasks": board["all_tasks"],
            "available_tasks": board["available_tasks"],
            "tutorial_tasks": board["tutorial_tasks"],
            "normal_tasks": board["normal_tasks"],
        }
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Get all tasks failed", user_id=user_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
