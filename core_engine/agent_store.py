"""PostgreSQL-backed agent catalog persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict
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
