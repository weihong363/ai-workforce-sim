"""User management API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CheckUsernameResponse,
    RegisterUserRequest,
    RegisterUserResponse,
)

router = APIRouter(prefix="/users", tags=["users"])

# Specific routes first (before parameterized routes)
@router.post("/register", response_model=RegisterUserResponse)
def register_user(request: RegisterUserRequest) -> dict:
    """Register a new user with username.
    
    Generates a unique user_id using snowflake algorithm.
    """
    import structlog
    
    logger = structlog.get_logger(__name__)
    
    try:
        from core_engine.snowflake import generate_user_id
        from game_modules.business_sim.progression import (
            check_username_exists,
            init_user,
        )
        
        # Check if username already exists
        if check_username_exists(request.username):
            logger.warning("Username registration failed - already exists", username=request.username)
            raise HTTPException(
                status_code=400,
                detail=f"Username '{request.username}' already exists"
            )
        
        # Generate unique user ID
        user_id = generate_user_id()
        logger.info("Generated user ID", user_id=user_id, username=request.username)
        
        # Create user
        user_data = init_user(user_id=user_id, username=request.username)
        logger.info("User registered successfully", user_id=user_id, username=request.username)
        
        return {
            "user_id": user_data["user_id"],
            "username": user_data["username"],
            "wallet_balance": user_data["wallet_balance"],
            "created_at": user_data["created_at"],
        }
    except HTTPException:
        raise
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
        from game_modules.business_sim.progression import check_username_exists
        
        is_available = not check_username_exists(username)
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
        from game_modules.business_sim.progression import get_user_by_username
        
        user_data = get_user_by_username(username)
        if user_data is None:
            logger.warning("User not found by username", username=username)
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        logger.info("User retrieved by username", username=username)
        return user_data
    except HTTPException:
        raise
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
        from game_modules.business_sim.progression import get_user
        
        user_data = get_user(user_id)
        logger.info("User retrieved by ID", user_id=user_id)
        return user_data
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
def get_task_board(user_id: str, module_name: Optional[str] = None) -> dict:
    """Get user's task board."""
    from fastapi import Depends
    
    from core_engine.config import get_settings
    from core_engine.module_loader import load_module
    from game_modules.business_sim.progression import list_task_board
    
    settings = get_settings()
    selected_module = module_name or settings.active_game_module
    
    if selected_module != "business_sim":
        raise HTTPException(
            status_code=400,
            detail="Task board progression is only available for business_sim."
        )
    
    try:
        module = load_module(selected_module)
        task_definitions = (
            module["tasks"].list_tasks()
            if callable(getattr(module["tasks"], "list_tasks", None))
            else {}
        )
        board = list_task_board(user_id=user_id, task_definitions=task_definitions)
        return {"user_id": user_id, "module_name": selected_module, **board}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
