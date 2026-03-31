"""User management API endpoints."""

from fastapi import APIRouter, HTTPException, Path

from api.schemas import (
    CheckUsernameResponse,
    RegisterUserRequest,
    RegisterUserResponse,
)
from core_engine.id_generator import generate_user_id
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import ModuleLoadError
import structlog

router = APIRouter(prefix="/users", tags=["users"])
logger = structlog.get_logger(__name__)

# Specific routes first (before parameterized routes)
@router.post(
    "/register",
    response_model=RegisterUserResponse,
    summary="Register User",
    description="Register a new gameplay user with unique username and backend-generated user ID.",
)
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


@router.get(
    "/check-username/{username}",
    response_model=CheckUsernameResponse,
    summary="Check Username Availability",
    description="Check whether a username is available for registration.",
)
def check_username(username: str = Path(..., min_length=1, description="Username to check")) -> dict:
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


@router.get(
    "/by-username/{username}",
    summary="Get User By Username",
    description="Fetch user profile/progression snapshot by username.",
)
def get_user_by_username(username: str = Path(..., min_length=1, description="Username")) -> dict:
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


@router.get(
    "/{user_id}",
    summary="Get User By ID",
    description="Fetch user profile/progression snapshot by user ID.",
)
def get_user(user_id: str = Path(..., min_length=1, description="User ID")) -> dict:
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
