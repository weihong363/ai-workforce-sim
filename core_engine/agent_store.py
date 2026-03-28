"""PostgreSQL-backed agent catalog persistence."""

from __future__ import annotations

import json
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
                profile_json JSONB NOT NULL,
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
                INSERT INTO agents (id, module_name, agent_name, profile_json, source, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (module_name, agent_name) DO UPDATE SET
                    profile_json = EXCLUDED.profile_json,
                    source = EXCLUDED.source,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    generate_id("agt"),
                    module_name,
                    name,
                    json.dumps(payload, ensure_ascii=True),
                    "module_seed",
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
