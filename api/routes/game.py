"""Game lifecycle endpoints."""

from fastapi import APIRouter, HTTPException

from api.schemas import GameStartRequest, GameStartResponse
from core_engine.module_facade import ModuleFacade
from core_engine.module_loader import ModuleLoadError

router = APIRouter(tags=["game"])


@router.post(
    "/game/start",
    response_model=GameStartResponse,
    summary="Start Game Session",
    description="Initialize or resume gameplay session state for an existing registered user.",
)
def game_start_route(request: GameStartRequest) -> dict:
    try:
        facade = ModuleFacade.from_name()
        progression = facade.progression
        start_fn = getattr(progression, "start_game", None)
        if not callable(start_fn):
            raise RuntimeError("Progression start_game is unavailable.")
        payload = start_fn(user_id=request.user_id, username=request.username)
        if not isinstance(payload, dict):
            raise RuntimeError("Progression start_game returned invalid payload.")
        return payload
    except ModuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if "User not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
