"""PostgreSQL-backed agent catalog persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, List
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

from core_engine.id_generator import generate_id, normalize_id


def _get_connection(database_url: str):
    parsed = urlparse(database_url)
    conn = psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/") if parsed.path else "postgres",
    )
    conn.autocommit = False
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_agent_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                module_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                description TEXT,
                level TEXT NOT NULL,
                skill REAL,
                overtime_willingness REAL,
                max_output_tokens INTEGER,
                cost_weight REAL,
                artificial_delay_ms INTEGER,
                obedience REAL,
                initiative REAL,
                effort REAL,
                affinity REAL,
                source TEXT NOT NULL DEFAULT 'module_seed',
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                UNIQUE(module_name, agent_name)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agents_module_name
            ON agents(module_name)
            """
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def rebuild_agent_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("DROP TABLE IF EXISTS agents")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    init_agent_db(database_url)


def seed_module_agents(database_url: str, module_name: str, agents: Dict[str, Dict[str, object]]) -> None:
    init_agent_db(database_url)
    module_name = normalize_id(module_name, "module_name")
    now = _utc_now_iso()

    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        for agent_name, profile in (agents or {}).items():
            name = normalize_id(str(agent_name), "agent_name")
            payload = profile if isinstance(profile, dict) else {}
            cursor.execute(
                """
                INSERT INTO agents (
                    id, module_name, agent_name, description, level,
                    skill, overtime_willingness, max_output_tokens,
                    cost_weight, artificial_delay_ms,
                    obedience, initiative, effort, affinity,
                    source, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (module_name, agent_name) DO UPDATE SET
                    description = EXCLUDED.description,
                    level = EXCLUDED.level,
                    skill = EXCLUDED.skill,
                    overtime_willingness = EXCLUDED.overtime_willingness,
                    max_output_tokens = EXCLUDED.max_output_tokens,
                    cost_weight = EXCLUDED.cost_weight,
                    artificial_delay_ms = EXCLUDED.artificial_delay_ms,
                    obedience = EXCLUDED.obedience,
                    initiative = EXCLUDED.initiative,
                    effort = EXCLUDED.effort,
                    affinity = EXCLUDED.affinity,
                    source = EXCLUDED.source,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    generate_id("agt"),
                    module_name,
                    name,
                    str(payload.get("description") or "") or None,
                    str(payload.get("level") or "junior"),
                    float(payload.get("skill", 0.0) or 0.0),
                    float(payload.get("overtime_willingness", 0.0) or 0.0),
                    int(payload.get("max_output_tokens", 0) or 0),
                    float(payload.get("cost_weight", 0.0) or 0.0),
                    int(payload.get("artificial_delay_ms", 0) or 0),
                    float(payload.get("obedience", 0.0) or 0.0),
                    float(payload.get("initiative", 0.0) or 0.0),
                    float(payload.get("effort", 0.0) or 0.0),
                    float(payload.get("affinity", 0.0) or 0.0),
                    "module_seed",
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _normalize_agent_payload(agent_name: str, profile: Dict[str, object], source: str) -> Dict[str, object]:
    name = normalize_id(str(agent_name), "agent_name")
    payload = dict(profile or {})
    level = str(payload.get("level") or "junior").strip().lower()
    if level not in {"junior", "mid", "senior"}:
        raise ValueError("agent level must be one of: junior, mid, senior")
    max_output_tokens = int(payload.get("max_output_tokens", 0) or 0)
    if max_output_tokens < 0:
        raise ValueError("max_output_tokens must be >= 0")
    artificial_delay_ms = int(payload.get("artificial_delay_ms", 0) or 0)
    if artificial_delay_ms < 0:
        raise ValueError("artificial_delay_ms must be >= 0")
    source_text = str(source or "manual").strip() or "manual"

    def _as_float(key: str, default: float = 0.0) -> float:
        return float(payload.get(key, default) or default)

    return {
        "agent_name": name,
        "description": (str(payload.get("description") or "").strip() or None),
        "level": level,
        "skill": _as_float("skill", 0.0),
        "overtime_willingness": _as_float("overtime_willingness", 0.0),
        "max_output_tokens": max_output_tokens,
        "cost_weight": _as_float("cost_weight", 0.0),
        "artificial_delay_ms": artificial_delay_ms,
        "obedience": _as_float("obedience", 0.0),
        "initiative": _as_float("initiative", 0.0),
        "effort": _as_float("effort", 0.0),
        "affinity": _as_float("affinity", 0.0),
        "source": source_text,
    }


def _row_to_agent_dict(row: Dict[str, object]) -> Dict[str, object]:
    return {
        "id": str(row.get("id", "")),
        "module_name": str(row.get("module_name", "")),
        "agent_name": str(row.get("agent_name", "")),
        "description": str(row.get("description", "") or ""),
        "level": str(row.get("level", "junior")),
        "skill": float(row.get("skill", 0.0) or 0.0),
        "overtime_willingness": float(row.get("overtime_willingness", 0.0) or 0.0),
        "max_output_tokens": int(row.get("max_output_tokens", 0) or 0),
        "cost_weight": float(row.get("cost_weight", 0.0) or 0.0),
        "artificial_delay_ms": int(row.get("artificial_delay_ms", 0) or 0),
        "obedience": float(row.get("obedience", 0.0) or 0.0),
        "initiative": float(row.get("initiative", 0.0) or 0.0),
        "effort": float(row.get("effort", 0.0) or 0.0),
        "affinity": float(row.get("affinity", 0.0) or 0.0),
        "source": str(row.get("source", "manual") or "manual"),
        "created_at": str(row.get("created_at", "")),
        "updated_at": str(row.get("updated_at", "")),
    }


def list_agents(database_url: str, module_name: str) -> List[Dict[str, object]]:
    module_name = normalize_id(module_name, "module_name")
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT *
            FROM agents
            WHERE module_name = %s
            ORDER BY agent_name ASC
            """,
            (module_name,),
        )
        rows = cursor.fetchall() or []
        return [_row_to_agent_dict(row) for row in rows]
    finally:
        cursor.close()
        conn.close()


def get_agent(database_url: str, module_name: str, agent_name: str) -> Optional[Dict[str, object]]:
    module_name = normalize_id(module_name, "module_name")
    agent_name = normalize_id(agent_name, "agent_name")
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT *
            FROM agents
            WHERE module_name = %s AND agent_name = %s
            LIMIT 1
            """,
            (module_name, agent_name),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_agent_dict(row)
    finally:
        cursor.close()
        conn.close()


def create_agent(
        database_url: str,
        module_name: str,
        agent_name: str,
        profile: Dict[str, object],
        source: str = "manual",
) -> Dict[str, object]:
    module_name = normalize_id(module_name, "module_name")
    normalized = _normalize_agent_payload(agent_name, profile, source)
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT 1 FROM agents
            WHERE module_name = %s AND agent_name = %s
            LIMIT 1
            """,
            (module_name, normalized["agent_name"]),
        )
        if cursor.fetchone() is not None:
            raise ValueError(f"Agent '{normalized['agent_name']}' already exists")

        cursor.execute(
            """
            INSERT INTO agents (
                id, module_name, agent_name, description, level,
                skill, overtime_willingness, max_output_tokens,
                cost_weight, artificial_delay_ms,
                obedience, initiative, effort, affinity,
                source, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                generate_id("agt"),
                module_name,
                normalized["agent_name"],
                normalized["description"],
                normalized["level"],
                normalized["skill"],
                normalized["overtime_willingness"],
                normalized["max_output_tokens"],
                normalized["cost_weight"],
                normalized["artificial_delay_ms"],
                normalized["obedience"],
                normalized["initiative"],
                normalized["effort"],
                normalized["affinity"],
                normalized["source"],
                now,
                now,
            ),
        )
        row = cursor.fetchone()
        conn.commit()
        if row is None:
            raise ValueError("Failed to create agent")
        return _row_to_agent_dict(row)
    finally:
        cursor.close()
        conn.close()


def update_agent(
        database_url: str,
        module_name: str,
        agent_name: str,
        profile: Dict[str, object],
        source: str = "manual",
) -> Optional[Dict[str, object]]:
    module_name = normalize_id(module_name, "module_name")
    normalized = _normalize_agent_payload(agent_name, profile, source)
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            UPDATE agents
            SET description = %s,
                level = %s,
                skill = %s,
                overtime_willingness = %s,
                max_output_tokens = %s,
                cost_weight = %s,
                artificial_delay_ms = %s,
                obedience = %s,
                initiative = %s,
                effort = %s,
                affinity = %s,
                source = %s,
                updated_at = %s
            WHERE module_name = %s AND agent_name = %s
            RETURNING *
            """,
            (
                normalized["description"],
                normalized["level"],
                normalized["skill"],
                normalized["overtime_willingness"],
                normalized["max_output_tokens"],
                normalized["cost_weight"],
                normalized["artificial_delay_ms"],
                normalized["obedience"],
                normalized["initiative"],
                normalized["effort"],
                normalized["affinity"],
                normalized["source"],
                now,
                module_name,
                normalized["agent_name"],
            ),
        )
        row = cursor.fetchone()
        conn.commit()
        if row is None:
            return None
        return _row_to_agent_dict(row)
    finally:
        cursor.close()
        conn.close()


def delete_agent(database_url: str, module_name: str, agent_name: str) -> bool:
    module_name = normalize_id(module_name, "module_name")
    agent_name = normalize_id(agent_name, "agent_name")
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            DELETE FROM agents
            WHERE module_name = %s AND agent_name = %s
            """,
            (module_name, agent_name),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        return bool(deleted)
    finally:
        cursor.close()
        conn.close()
