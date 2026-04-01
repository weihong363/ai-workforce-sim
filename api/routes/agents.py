"""Agent management endpoints (admin CRUD)."""

from fastapi import APIRouter, HTTPException, Path

from api.schemas import AgentCreateRequest, AgentLineupRequest, AgentUpdateRequest, AgentUserBindRequest
from core_engine import user_store
from core_engine.agent_store import create_agent, delete_agent, get_agent, list_agents, update_agent
from core_engine.config import get_settings
from core_engine.id_generator import generate_id
from core_engine.module_facade import ModuleFacade

router = APIRouter(tags=["agents"])


@router.get(
    "/agents/choices",
    summary="List Selectable Agents",
    description="Return playable junior agent cards with visible attributes and hidden-trait hint.",
)
def list_selectable_agent_choices_route() -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        chooser = getattr(facade.agents, "list_selectable_agents", None)
        if not callable(chooser):
            raise RuntimeError("Active module does not expose selectable agent cards.")
        return {
            "module_name": settings.active_game_module,
            "hint": "Each worker also has hidden tendencies you will discover through use.",
            "agents": chooser(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/agents/admin",
    summary="Admin List Agents",
    description="List all agent definitions for the active game module.",
)
def admin_list_agents_route() -> dict:
    settings = get_settings()
    try:
        items = list_agents(settings.database_url, settings.active_game_module)
        return {
            "module_name": settings.active_game_module,
            "total_agents": len(items),
            "agents": items,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/agents/admin/{agent_name}",
    summary="Admin Get Agent",
    description="Get one agent definition by agent name.",
)
def admin_get_agent_route(
        agent_name: str = Path(..., min_length=1, description="Agent name")
) -> dict:
    settings = get_settings()
    try:
        item = get_agent(settings.database_url, settings.active_game_module, agent_name)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
        return {
            "module_name": settings.active_game_module,
            "agent": item,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/agents/admin",
    summary="Admin Create Agent",
    description="Create one new agent definition. Backend generates ULID-based record ID.",
)
def admin_create_agent_route(request: AgentCreateRequest) -> dict:
    settings = get_settings()
    try:
        created = create_agent(
            database_url=settings.database_url,
            module_name=settings.active_game_module,
            agent_name=request.agent_name,
            profile=request.profile.model_dump(exclude_none=True),
            source=request.source,
        )
        return {
            "module_name": settings.active_game_module,
            "agent": created,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put(
    "/agents/admin/{agent_name}",
    summary="Admin Update Agent",
    description="Update an existing agent definition by agent name.",
)
def admin_update_agent_route(
        request: AgentUpdateRequest,
        agent_name: str = Path(..., min_length=1, description="Agent name"),
) -> dict:
    settings = get_settings()
    try:
        updated = update_agent(
            database_url=settings.database_url,
            module_name=settings.active_game_module,
            agent_name=agent_name,
            profile=request.profile.model_dump(exclude_none=True),
            source=request.source,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
        return {
            "module_name": settings.active_game_module,
            "agent": updated,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete(
    "/agents/admin/{agent_name}",
    summary="Admin Delete Agent",
    description="Delete an agent definition by agent name.",
)
def admin_delete_agent_route(
        agent_name: str = Path(..., min_length=1, description="Agent name")
) -> dict:
    settings = get_settings()
    try:
        deleted = delete_agent(settings.database_url, settings.active_game_module, agent_name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found.")
        return {
            "module_name": settings.active_game_module,
            "agent_name": agent_name,
            "deleted": True,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/agents/users/{user_id}",
    summary="List User Agent Bindings",
    description="List all agent bindings owned by one user.",
)
def list_user_agent_bindings_route(
        user_id: str = Path(..., min_length=1, description="User ID")
) -> dict:
    settings = get_settings()
    try:
        user = user_store.get_user_by_id(user_id, settings.database_url, module_name=settings.active_game_module)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
        return {
            "module_name": settings.active_game_module,
            "user_id": user_id,
            "owned_agents": list(user.get("owned_agents", []) or []),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/agents/users/{user_id}/lineup",
    summary="Set User Agent Lineup",
    description="Set exactly two active playable agents for the user.",
)
def set_user_agent_lineup_route(
        request: AgentLineupRequest,
        user_id: str = Path(..., min_length=1, description="User ID"),
) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        chooser = getattr(facade.agents, "list_selectable_agents", None)
        if not callable(chooser):
            raise RuntimeError("Active module does not expose selectable agent cards.")
        cards = chooser()
        card_map = {
            str(item.get("agent_name", "")).strip().lower(): item
            for item in cards
            if isinstance(item, dict) and str(item.get("agent_name", "")).strip()
        }
        names = [str(item).strip().lower() for item in request.agent_names]
        if len(names) != 2 or len(set(names)) != 2:
            raise ValueError("Exactly two distinct agents must be selected.")
        unknown = [name for name in names if name not in card_map]
        if unknown:
            raise ValueError(f"Unknown selectable agents: {unknown}")
        lineup_payload = []
        for name in names:
            lineup_payload.append(
                {
                    "agent_id": generate_id("uagt"),
                    "preset": name,
                    "level": "junior",
                    "status": "active",
                    "affinity": 0.5,
                }
            )
        stored = user_store.set_user_agent_lineup(
            user_id=user_id,
            database_url=settings.database_url,
            module_name=settings.active_game_module,
            lineup_agents=lineup_payload,
        )
        return {
            "module_name": settings.active_game_module,
            "user_id": user_id,
            "lineup": stored,
        }
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/agents/users/{user_id}/bind",
    summary="Bind Agent To User",
    description="Bind one catalog agent to a user.",
)
def bind_agent_to_user_route(
        request: AgentUserBindRequest,
        user_id: str = Path(..., min_length=1, description="User ID"),
) -> dict:
    settings = get_settings()
    try:
        binding = user_store.bind_agent_to_user(
            user_id=user_id,
            database_url=settings.database_url,
            module_name=settings.active_game_module,
            agent_name=request.agent_name,
            status=request.status,
        )
        return {
            "module_name": settings.active_game_module,
            "user_id": user_id,
            "binding": binding,
        }
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete(
    "/agents/users/{user_id}/bind/{agent_id}",
    summary="Unbind Agent From User",
    description="Remove one bound agent from a user by binding agent_id.",
)
def unbind_agent_from_user_route(
        user_id: str = Path(..., min_length=1, description="User ID"),
        agent_id: str = Path(..., min_length=1, description="User binding agent ID"),
) -> dict:
    settings = get_settings()
    try:
        result = user_store.unbind_agent_from_user(
            user_id=user_id,
            database_url=settings.database_url,
            module_name=settings.active_game_module,
            agent_id=agent_id,
        )
        return {
            "module_name": settings.active_game_module,
            "user_id": user_id,
            **result,
        }
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
