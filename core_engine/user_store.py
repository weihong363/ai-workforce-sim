"""User persistence with event sourcing + projection tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

from core_engine.config import get_settings
from core_engine.id_generator import generate_id, normalize_id

DEFAULT_STARTING_WALLET = 120.0
DEFAULT_OWNED_AGENTS = [{"agent_id": "junior_001", "preset": "junior_worker", "level": "junior"}]


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _normalize_username(username: str) -> str:
    normalized = str(username or "").strip()
    if not normalized:
        raise ValueError("username cannot be empty")
    if len(normalized) > 64:
        raise ValueError("username is too long (max 64)")
    return normalized


def _active_module_name(module_name: Optional[str]) -> str:
    selected = module_name or get_settings().active_game_module
    return normalize_id(selected, "module_name")


def _list_or_default(value: object, default: List[object]) -> List[object]:
    return value if isinstance(value, list) else list(default)


def _apply_event_to_projection(
    projection: Dict[str, object],
    event_type: str,
    payload: Dict[str, object],
) -> Dict[str, object]:
    updated = dict(projection)
    if event_type == "user_initialized":
        updated["wallet_balance"] = float(payload.get("wallet_balance", updated.get("wallet_balance", DEFAULT_STARTING_WALLET)))
        owned = payload.get("owned_agents", updated.get("owned_agents", DEFAULT_OWNED_AGENTS))
        updated["owned_agents"] = owned if isinstance(owned, list) else list(DEFAULT_OWNED_AGENTS)
        completed = payload.get("completed_tutorial_tasks", [])
        updated["completed_tutorial_tasks"] = completed if isinstance(completed, list) else []
        updated["tutorial_completed"] = bool(payload.get("tutorial_completed", False))
    elif event_type == "task_charged":
        updated["wallet_balance"] = float(payload.get("wallet_after_cost", updated.get("wallet_balance", DEFAULT_STARTING_WALLET)))
    elif event_type == "task_finished":
        updated["wallet_balance"] = float(payload.get("wallet_after", updated.get("wallet_balance", DEFAULT_STARTING_WALLET)))
        completed = payload.get("completed_tutorial_tasks")
        if isinstance(completed, list):
            updated["completed_tutorial_tasks"] = completed
        updated["tutorial_completed"] = bool(payload.get("tutorial_completed", updated.get("tutorial_completed", False)))
    return updated


def init_user_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                module_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_version INTEGER NOT NULL DEFAULT 1,
                run_id TEXT,
                task_id TEXT,
                payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_state_projection (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                module_name TEXT NOT NULL,
                wallet_balance DOUBLE PRECISION NOT NULL DEFAULT 120.0,
                tutorial_completed BOOLEAN NOT NULL DEFAULT FALSE,
                completed_tutorial_tasks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                owned_agents_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                last_event_id TEXT,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, module_name)
            )
            """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_events_user_module_created_at
            ON user_events(user_id, module_name, created_at DESC)
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_events_run_id ON user_events(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_events_event_type ON user_events(event_type)")

        conn.commit()
    finally:
        cursor.close()
        conn.close()


def rebuild_user_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("DROP TABLE IF EXISTS user_events")
        cursor.execute("DROP TABLE IF EXISTS user_state_projection")
        cursor.execute("DROP TABLE IF EXISTS users")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    init_user_db(database_url)


def _ensure_projection(cursor, user_id: str, module_name: str, now: datetime) -> None:
    cursor.execute(
        """
        INSERT INTO user_state_projection (
            user_id, module_name, wallet_balance, tutorial_completed,
            completed_tutorial_tasks_json, owned_agents_json, last_event_id, updated_at
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        ON CONFLICT (user_id, module_name) DO NOTHING
        """,
        (
            user_id,
            module_name,
            DEFAULT_STARTING_WALLET,
            False,
            json.dumps([], ensure_ascii=True),
            json.dumps(DEFAULT_OWNED_AGENTS, ensure_ascii=True),
            None,
            now,
        ),
    )


def create_user(
    user_id: str,
    username: str,
    database_url: str,
    wallet_balance: float = DEFAULT_STARTING_WALLET,
    module_name: Optional[str] = None,
) -> Dict[str, object]:
    user_id = normalize_id(user_id, "user_id")
    username = _normalize_username(username)
    selected_module = _active_module_name(module_name)
    now = _utc_now()

    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            INSERT INTO users (id, username, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, username, now, now),
        )

        cursor.execute(
            """
            INSERT INTO user_state_projection (
                user_id, module_name, wallet_balance, tutorial_completed,
                completed_tutorial_tasks_json, owned_agents_json, last_event_id, updated_at
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """,
            (
                user_id,
                selected_module,
                float(wallet_balance),
                False,
                json.dumps([], ensure_ascii=True),
                json.dumps(DEFAULT_OWNED_AGENTS, ensure_ascii=True),
                None,
                now,
            ),
        )

        event_id = generate_id("uev")
        cursor.execute(
            """
            INSERT INTO user_events (
                id, user_id, module_name, event_type, event_version,
                run_id, task_id, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                event_id,
                user_id,
                selected_module,
                "user_initialized",
                1,
                None,
                None,
                json.dumps(
                    {
                        "wallet_balance": float(wallet_balance),
                        "owned_agents": DEFAULT_OWNED_AGENTS,
                        "completed_tutorial_tasks": [],
                        "tutorial_completed": False,
                    },
                    ensure_ascii=True,
                ),
                now,
            ),
        )

        cursor.execute(
            """
            UPDATE user_state_projection
            SET last_event_id = %s, updated_at = %s
            WHERE user_id = %s AND module_name = %s
            """,
            (event_id, now, user_id, selected_module),
        )

        conn.commit()
        return {
            "user_id": user_id,
            "username": username,
            "wallet_balance": float(wallet_balance),
            "created_at": now.isoformat(),
        }
    finally:
        cursor.close()
        conn.close()


def check_username_exists(username: str, database_url: str) -> bool:
    username = _normalize_username(username)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT 1 FROM users WHERE username = %s LIMIT 1", (username,))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


def _build_user_row(user_row: Dict[str, object], projection_row: Optional[Dict[str, object]], task_history: List[Dict[str, object]]) -> Dict[str, object]:
    projection = projection_row or {}
    completed = projection.get("completed_tutorial_tasks_json")
    owned = projection.get("owned_agents_json")
    return {
        "user_id": user_row["id"],
        "username": user_row["username"],
        "wallet_balance": float(projection.get("wallet_balance", DEFAULT_STARTING_WALLET)),
        "tutorial_completed": bool(projection.get("tutorial_completed", False)),
        "owned_agents": _list_or_default(owned, DEFAULT_OWNED_AGENTS),
        "tutorial_progress": {"completed_tasks": _list_or_default(completed, [])},
        "task_history": task_history,
        "created_at": user_row["created_at"].isoformat() if hasattr(user_row["created_at"], "isoformat") else str(user_row["created_at"]),
        "updated_at": (projection.get("updated_at") or user_row["updated_at"]).isoformat()
        if hasattr(projection.get("updated_at") or user_row["updated_at"], "isoformat")
        else str(projection.get("updated_at") or user_row["updated_at"]),
    }


def get_user_projection(
    user_id: str,
    database_url: str,
    module_name: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    user_id = normalize_id(user_id, "user_id")
    selected_module = _active_module_name(module_name)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT user_id, module_name, wallet_balance, tutorial_completed,
                   completed_tutorial_tasks_json, owned_agents_json,
                   last_event_id, updated_at
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_id, selected_module),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "user_id": row["user_id"],
            "module_name": row["module_name"],
            "wallet_balance": float(row["wallet_balance"]),
            "tutorial_completed": bool(row["tutorial_completed"]),
            "completed_tutorial_tasks": _list_or_default(row.get("completed_tutorial_tasks_json"), []),
            "owned_agents": _list_or_default(row.get("owned_agents_json"), DEFAULT_OWNED_AGENTS),
            "last_event_id": row.get("last_event_id"),
            "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
        }
    finally:
        cursor.close()
        conn.close()


def list_user_events(
    user_id: str,
    database_url: str,
    module_name: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, object]]:
    user_id = normalize_id(user_id, "user_id")
    selected_module = _active_module_name(module_name)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if event_type:
            cursor.execute(
                """
                SELECT id, user_id, module_name, event_type, event_version,
                       run_id, task_id, payload_json, created_at
                FROM user_events
                WHERE user_id = %s AND module_name = %s AND event_type = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (user_id, selected_module, event_type, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, user_id, module_name, event_type, event_version,
                       run_id, task_id, payload_json, created_at
                FROM user_events
                WHERE user_id = %s AND module_name = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (user_id, selected_module, limit),
            )
        rows = cursor.fetchall() or []
        output: List[Dict[str, object]] = []
        for row in rows:
            created_at = row["created_at"]
            output.append(
                {
                    "event_id": row["id"],
                    "user_id": row["user_id"],
                    "module_name": row["module_name"],
                    "event_type": row["event_type"],
                    "event_version": int(row["event_version"]),
                    "run_id": row.get("run_id"),
                    "task_id": row.get("task_id"),
                    "payload": row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {},
                    "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
                }
            )
        return output
    finally:
        cursor.close()
        conn.close()


def append_user_event(
    user_id: str,
    database_url: str,
    module_name: Optional[str],
    event_type: str,
    payload: Dict[str, object],
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    event_version: int = 1,
) -> Dict[str, object]:
    user_id = normalize_id(user_id, "user_id")
    selected_module = _active_module_name(module_name)
    event_type = normalize_id(event_type, "event_type", max_length=64)
    now = _utc_now()

    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"User {user_id} not found")

        _ensure_projection(cursor, user_id, selected_module, now)

        cursor.execute(
            """
            SELECT wallet_balance, tutorial_completed,
                   completed_tutorial_tasks_json, owned_agents_json,
                   last_event_id, updated_at
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_id, selected_module),
        )
        current = cursor.fetchone() or {}
        current_projection = {
            "wallet_balance": float(current.get("wallet_balance", DEFAULT_STARTING_WALLET)),
            "tutorial_completed": bool(current.get("tutorial_completed", False)),
            "completed_tutorial_tasks": _list_or_default(current.get("completed_tutorial_tasks_json"), []),
            "owned_agents": _list_or_default(current.get("owned_agents_json"), DEFAULT_OWNED_AGENTS),
        }
        updated_projection = _apply_event_to_projection(current_projection, event_type, payload)

        event_id = generate_id("uev")
        cursor.execute(
            """
            INSERT INTO user_events (
                id, user_id, module_name, event_type, event_version,
                run_id, task_id, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                event_id,
                user_id,
                selected_module,
                event_type,
                event_version,
                normalize_id(run_id, "run_id") if run_id else None,
                normalize_id(task_id, "task_id") if task_id else None,
                json.dumps(payload or {}, ensure_ascii=True),
                now,
            ),
        )

        cursor.execute(
            """
            UPDATE user_state_projection
            SET wallet_balance = %s,
                tutorial_completed = %s,
                completed_tutorial_tasks_json = %s::jsonb,
                owned_agents_json = %s::jsonb,
                last_event_id = %s,
                updated_at = %s
            WHERE user_id = %s AND module_name = %s
            """,
            (
                float(updated_projection.get("wallet_balance", DEFAULT_STARTING_WALLET)),
                bool(updated_projection.get("tutorial_completed", False)),
                json.dumps(_list_or_default(updated_projection.get("completed_tutorial_tasks"), []), ensure_ascii=True),
                json.dumps(_list_or_default(updated_projection.get("owned_agents"), DEFAULT_OWNED_AGENTS), ensure_ascii=True),
                event_id,
                now,
                user_id,
                selected_module,
            ),
        )
        cursor.execute("UPDATE users SET updated_at = %s WHERE id = %s", (now, user_id))
        conn.commit()
        return {
            "event_id": event_id,
            "user_id": user_id,
            "module_name": selected_module,
            "event_type": event_type,
            "payload": payload,
            "created_at": now.isoformat(),
        }
    finally:
        cursor.close()
        conn.close()


def _task_history_from_events(events: List[Dict[str, object]]) -> List[Dict[str, object]]:
    history: List[Dict[str, object]] = []
    for event in events:
        payload = event.get("payload")
        if isinstance(payload, dict):
            history.append(dict(payload))
    return history


def get_user_by_id(
    user_id: str,
    database_url: str,
    module_name: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    user_id = normalize_id(user_id, "user_id")
    selected_module = _active_module_name(module_name)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT id, username, created_at, updated_at FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()
        if user_row is None:
            return None

        cursor.execute(
            """
            SELECT wallet_balance, tutorial_completed,
                   completed_tutorial_tasks_json, owned_agents_json, updated_at
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_id, selected_module),
        )
        projection_row = cursor.fetchone()

        task_history_events = list_user_events(
            user_id=user_id,
            database_url=database_url,
            module_name=selected_module,
            event_type="task_finished",
            limit=1000,
        )
        return _build_user_row(user_row, projection_row, _task_history_from_events(task_history_events))
    finally:
        cursor.close()
        conn.close()


def get_user_by_username(
    username: str,
    database_url: str,
    module_name: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    username = _normalize_username(username)
    selected_module = _active_module_name(module_name)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT id, username, created_at, updated_at FROM users WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        if user_row is None:
            return None

        cursor.execute(
            """
            SELECT wallet_balance, tutorial_completed,
                   completed_tutorial_tasks_json, owned_agents_json, updated_at
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_row["id"], selected_module),
        )
        projection_row = cursor.fetchone()

        task_history_events = list_user_events(
            user_id=str(user_row["id"]),
            database_url=database_url,
            module_name=selected_module,
            event_type="task_finished",
            limit=1000,
        )
        return _build_user_row(user_row, projection_row, _task_history_from_events(task_history_events))
    finally:
        cursor.close()
        conn.close()


def upsert_user_state(user: Dict[str, object], database_url: str) -> Dict[str, object]:
    user_id = normalize_id(str(user["user_id"]), "user_id")
    username = _normalize_username(str(user.get("username") or user_id))
    selected_module = _active_module_name(str(user.get("module_name") or "") or None)
    now = _utc_now()

    wallet_balance = float(user.get("wallet_balance", DEFAULT_STARTING_WALLET))
    tutorial_completed = bool(user.get("tutorial_completed", False))
    tutorial_progress_raw = user.get("tutorial_progress", {})
    tutorial_progress = tutorial_progress_raw if isinstance(tutorial_progress_raw, dict) else {}
    completed_tasks = tutorial_progress.get("completed_tasks") if isinstance(tutorial_progress, dict) else []
    completed_tasks = completed_tasks if isinstance(completed_tasks, list) else []
    owned_agents = user.get("owned_agents") if isinstance(user.get("owned_agents"), list) else list(DEFAULT_OWNED_AGENTS)

    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            INSERT INTO users (id, username, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                username = EXCLUDED.username,
                updated_at = EXCLUDED.updated_at
            """,
            (user_id, username, now, now),
        )

        cursor.execute(
            """
            INSERT INTO user_state_projection (
                user_id, module_name, wallet_balance, tutorial_completed,
                completed_tutorial_tasks_json, owned_agents_json, last_event_id, updated_at
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (user_id, module_name) DO UPDATE SET
                wallet_balance = EXCLUDED.wallet_balance,
                tutorial_completed = EXCLUDED.tutorial_completed,
                completed_tutorial_tasks_json = EXCLUDED.completed_tutorial_tasks_json,
                owned_agents_json = EXCLUDED.owned_agents_json,
                updated_at = EXCLUDED.updated_at
            """,
            (
                user_id,
                selected_module,
                wallet_balance,
                tutorial_completed,
                json.dumps(completed_tasks, ensure_ascii=True),
                json.dumps(owned_agents, ensure_ascii=True),
                None,
                now,
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    stored = dict(user)
    stored["user_id"] = user_id
    stored["username"] = username
    stored["wallet_balance"] = wallet_balance
    stored["tutorial_completed"] = tutorial_completed
    stored["owned_agents"] = owned_agents
    stored["tutorial_progress"] = {"completed_tasks": completed_tasks}
    stored["updated_at"] = now.isoformat()
    return stored


def update_user_wallet(user_id: str, wallet_balance: float, database_url: str) -> None:
    user = get_user_by_id(user_id, database_url)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    user["wallet_balance"] = float(wallet_balance)
    upsert_user_state(user, database_url)


def add_task_to_history(user_id: str, task_record: Dict[str, object], database_url: str) -> None:
    append_user_event(
        user_id=user_id,
        database_url=database_url,
        module_name=None,
        event_type="task_finished",
        payload=dict(task_record),
        run_id=str(task_record.get("run_id")) if task_record.get("run_id") else None,
        task_id=str(task_record.get("task_id")) if task_record.get("task_id") else None,
    )
