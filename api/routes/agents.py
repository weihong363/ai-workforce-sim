"""Agent management endpoints (admin CRUD)."""

from copy import deepcopy

from fastapi import APIRouter, HTTPException, Path, Query

from api.schemas import AgentCreateRequest, AgentLineupRequest, AgentUpdateRequest, AgentUserBindRequest
from core_engine import user_store
from core_engine.agent_store import create_agent, delete_agent, get_agent, list_agents, update_agent
from core_engine.config import get_settings
from core_engine.id_generator import generate_id
from core_engine.module_facade import ModuleFacade

router = APIRouter(tags=["agents"])

_ZH_AGENT_COPY: dict[str, dict[str, object]] = {
    "operator": {
        "name": "执行型员工",
        "role_label": "稳健执行者",
        "description": "严格按指令执行，很稳定，但很少超出预期。",
        "player_feel": "基础任务很稳，冲高分能力较弱。",
        "strengths": ["高服从", "高稳定"],
        "weaknesses": ["创意较低", "潜力较低"],
        "cost_level": "中",
    },
    "maverick": {
        "name": "创意型员工",
        "role_label": "高风险创意者",
        "description": "指令清晰时可出彩，指令模糊时容易跑偏。",
        "player_feel": "目标清晰时很强，目标不清时风险高。",
        "strengths": ["高创意", "高潜力"],
        "weaknesses": ["服从较低", "稳定较低"],
        "cost_level": "中",
    },
    "slacker": {
        "name": "节约型员工",
        "role_label": "低成本波动型",
        "description": "成本低，但执行中容易漏细节和跑题。",
        "player_feel": "省钱场景可用，约束严格时风险高。",
        "strengths": ["低成本", "有一定创意"],
        "weaknesses": ["勤勉较低", "稳定较低"],
        "cost_level": "低",
    },
}


def _normalize_lang(lang: str) -> str:
    value = str(lang or "").strip().lower()
    return "zh" if value.startswith("zh") else "en"


def _localize_agent_cards(cards: list[dict], lang: str) -> list[dict]:
    if _normalize_lang(lang) != "zh":
        return cards
    output: list[dict] = []
    for item in cards:
        if not isinstance(item, dict):
            continue
        card = deepcopy(item)
        key = str(card.get("agent_name", "")).strip().lower()
        overlay = _ZH_AGENT_COPY.get(key, {})
        for field in ("name", "role_label", "description", "player_feel", "cost_level"):
            value = overlay.get(field)
            if isinstance(value, str) and value.strip():
                card[field] = value
        for field in ("strengths", "weaknesses"):
            value = overlay.get(field)
            if isinstance(value, list):
                card[field] = [str(x) for x in value]
        output.append(card)
    return output


@router.get(
    "/agents/choices",
    summary="List Selectable Agents",
    description="Return playable junior agent cards with visible attributes and hidden-trait hint.",
)
def list_selectable_agent_choices_route(
        lang: str = Query("en", description="Response language, e.g. en / zh-CN")) -> dict:
    settings = get_settings()
    try:
        facade = ModuleFacade.from_name(settings.active_game_module)
        chooser = getattr(facade.agents, "list_selectable_agents", None)
        if not callable(chooser):
            raise RuntimeError("Active module does not expose selectable agent cards.")
        normalized_lang = _normalize_lang(lang)
        hint = (
            "每位员工还有隐藏倾向，需要在实战中逐步发现。"
            if normalized_lang == "zh"
            else "Each worker also has hidden tendencies you will discover through use."
        )
        cards_raw = chooser()
        cards = cards_raw if isinstance(cards_raw, list) else []
        return {
            "module_name": settings.active_game_module,
            "lang": "zh-CN" if normalized_lang == "zh" else "en-US",
            "hint": hint,
            "agents": _localize_agent_cards(cards, normalized_lang),
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
