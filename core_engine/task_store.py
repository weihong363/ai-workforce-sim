"""PostgreSQL-backed task catalog for game modules."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

from core_engine.id_generator import generate_task_record_id, normalize_id


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


def init_task_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_tasks (
                id TEXT PRIMARY KEY,
                module_name TEXT NOT NULL,
                task_id TEXT NOT NULL,
                task_config_json JSONB NOT NULL,
                source TEXT NOT NULL DEFAULT 'seed',
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                UNIQUE(module_name, task_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_game_tasks_module_name
            ON game_tasks(module_name)
            """
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def rebuild_task_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("DROP TABLE IF EXISTS game_tasks")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    init_task_db(database_url)


def upsert_task(
    database_url: str,
    module_name: str,
    task_id: str,
    task_config: Dict[str, object],
    source: str = "seed",
) -> None:
    module_name = normalize_id(module_name, "module_name")
    task_id = normalize_id(task_id, "task_id")
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            INSERT INTO game_tasks (id, module_name, task_id, task_config_json, source, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_name, task_id) DO UPDATE SET
                task_config_json = EXCLUDED.task_config_json,
                source = EXCLUDED.source,
                updated_at = EXCLUDED.updated_at
            """,
            (
                generate_task_record_id(),
                module_name,
                task_id,
                json.dumps(task_config, ensure_ascii=True),
                source,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def seed_tasks(database_url: str, module_name: str, tasks: Iterable[Dict[str, object]]) -> None:
    module_name = normalize_id(module_name, "module_name")
    for item in tasks:
        task_id = str(item["task_id"])
        task_config = dict(item["task_config"])
        source = str(item.get("source", "seed"))
        upsert_task(database_url, module_name, task_id, task_config, source)


def list_tasks(database_url: str, module_name: str) -> Dict[str, Dict[str, object]]:
    module_name = normalize_id(module_name, "module_name")
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT task_id, task_config_json
            FROM game_tasks
            WHERE module_name = %s
            ORDER BY task_id ASC
            """,
            (module_name,),
        )
        rows = cursor.fetchall() or []
        result: Dict[str, Dict[str, object]] = {}
        for row in rows:
            raw = row["task_config_json"]
            parsed = raw if isinstance(raw, dict) else None
            if parsed is None:
                try:
                    parsed = json.loads(str(raw or "{}"))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
            if isinstance(parsed, dict):
                result[str(row["task_id"])] = parsed
        return result
    finally:
        cursor.close()
        conn.close()


def get_task(database_url: str, module_name: str, task_id: str) -> Optional[Dict[str, object]]:
    module_name = normalize_id(module_name, "module_name")
    task_id = normalize_id(task_id, "task_id")
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT task_config_json
            FROM game_tasks
            WHERE module_name = %s AND task_id = %s
            LIMIT 1
            """,
            (module_name, task_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        raw = row["task_config_json"]
        parsed = raw if isinstance(raw, dict) else None
        if parsed is None:
            try:
                parsed = json.loads(str(raw or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
        return parsed if isinstance(parsed, dict) else None
    finally:
        cursor.close()
        conn.close()
