"""User persistence with event sourcing + normalized projection tables."""

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
DEFAULT_OWNED_AGENTS = [{"agent_id": "junior_001", "preset": "junior_worker", "level": "junior", "affinity": 0.5}]


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
                last_event_id TEXT,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, module_name)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_agents (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                module_name TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                preset TEXT,
                level TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                affinity DOUBLE PRECISION,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, module_name, agent_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tutorial_progress (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                module_name TEXT NOT NULL,
                task_id TEXT NOT NULL,
                completed_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, module_name, task_id)
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_agents_user_module ON user_agents(user_id, module_name)")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_tutorial_progress_user_module
            ON user_tutorial_progress(user_id, module_name)
            """
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def rebuild_user_db(database_url: str) -> None:
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("DROP TABLE IF EXISTS user_tutorial_progress")
        cursor.execute("DROP TABLE IF EXISTS user_agents")
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
        INSERT INTO user_state_projection (user_id, module_name, wallet_balance, tutorial_completed, last_event_id, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, module_name) DO NOTHING
        """,
        (user_id, module_name, DEFAULT_STARTING_WALLET, False, None, now),
    )


def _replace_user_agents(cursor, user_id: str, module_name: str, owned_agents: List[Dict[str, object]], now: datetime) -> None:
    def _catalog_affinity_for(item: Dict[str, object]) -> Optional[float]:
        candidates: List[str] = []
        for key in ("agent_name", "preset", "agent_id"):
            raw = item.get(key)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                candidates.append(text)

        for name in candidates:
            cursor.execute(
                """
                SELECT affinity
                FROM agents
                WHERE module_name = %s AND agent_name = %s
                LIMIT 1
                """,
                (module_name, name),
            )
            row = cursor.fetchone()
            if row is not None and row.get("affinity") is not None:
                return float(row["affinity"])

        level = str(item.get("level") or "").strip()
        if level:
            cursor.execute(
                """
                SELECT affinity
                FROM agents
                WHERE module_name = %s AND level = %s
                ORDER BY agent_name ASC
                LIMIT 1
                """,
                (module_name, level),
            )
            row = cursor.fetchone()
            if row is not None and row.get("affinity") is not None:
                return float(row["affinity"])

        return None

    cursor.execute("DELETE FROM user_agents WHERE user_id = %s AND module_name = %s", (user_id, module_name))
    for item in owned_agents:
        if not isinstance(item, dict):
            continue
        agent_id = normalize_id(str(item.get("agent_id") or "agent_unknown"), "agent_id")
        preset = str(item.get("preset") or "") or None
        level = str(item.get("level") or "junior")
        status = str(item.get("status") or "active")
        affinity_raw = item.get("affinity")
        if isinstance(affinity_raw, (int, float)):
            affinity = float(affinity_raw)
        else:
            affinity = _catalog_affinity_for(item)
            if affinity is None:
                affinity = 0.5
        cursor.execute(
            """
            INSERT INTO user_agents (
                user_id, module_name, agent_id, preset, level, status, affinity, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, module_name, agent_id, preset, level, status, affinity, now, now),
        )


def _replace_tutorial_completed_tasks(cursor, user_id: str, module_name: str, task_ids: List[str], now: datetime) -> None:
    cursor.execute("DELETE FROM user_tutorial_progress WHERE user_id = %s AND module_name = %s", (user_id, module_name))
    for task_id in task_ids:
        normalized = normalize_id(str(task_id), "task_id")
        cursor.execute(
            """
            INSERT INTO user_tutorial_progress (user_id, module_name, task_id, completed_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, module_name, task_id) DO UPDATE SET completed_at = EXCLUDED.completed_at
            """,
            (user_id, module_name, normalized, now),
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
            INSERT INTO user_state_projection (user_id, module_name, wallet_balance, tutorial_completed, last_event_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, selected_module, float(wallet_balance), False, None, now),
        )

        _replace_user_agents(cursor, user_id, selected_module, list(DEFAULT_OWNED_AGENTS), now)

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


def _build_user_row(
    user_row: Dict[str, object],
    projection_row: Optional[Dict[str, object]],
    task_history: List[Dict[str, object]],
    owned_agents: List[Dict[str, object]],
    completed_tasks: List[str],
) -> Dict[str, object]:
    projection = projection_row or {}
    tasks_completed_count = len(task_history) if isinstance(task_history, list) else 0
    return {
        "user_id": user_row["id"],
        "username": user_row["username"],
        "wallet_balance": float(projection.get("wallet_balance", DEFAULT_STARTING_WALLET)),
        "tutorial_completed": bool(projection.get("tutorial_completed", False)),
        "tasks_completed_count": int(tasks_completed_count),
        "owned_agents": owned_agents,
        "tutorial_progress": {"completed_tasks": completed_tasks},
        "task_history": task_history,
        "created_at": user_row["created_at"].isoformat() if hasattr(user_row["created_at"], "isoformat") else str(user_row["created_at"]),
        "updated_at": (projection.get("updated_at") or user_row["updated_at"]).isoformat()
        if hasattr((projection.get("updated_at") or user_row["updated_at"]), "isoformat")
        else str(projection.get("updated_at") or user_row["updated_at"]),
    }


def _fetch_user_agents(cursor, user_id: str, module_name: str) -> List[Dict[str, object]]:
    cursor.execute(
        """
        SELECT agent_id, preset, level, status, affinity
        FROM user_agents
        WHERE user_id = %s AND module_name = %s
        ORDER BY agent_id ASC
        """,
        (user_id, module_name),
    )
    rows = cursor.fetchall() or []
    output: List[Dict[str, object]] = []
    for row in rows:
        item = {
            "agent_id": row["agent_id"],
            "level": row["level"],
            "status": row["status"],
        }
        if row.get("preset") is not None:
            item["preset"] = row["preset"]
        if row.get("affinity") is not None:
            item["affinity"] = float(row["affinity"])
        output.append(item)
    return output


def _fetch_completed_tutorial_tasks(cursor, user_id: str, module_name: str) -> List[str]:
    cursor.execute(
        """
        SELECT task_id
        FROM user_tutorial_progress
        WHERE user_id = %s AND module_name = %s
        ORDER BY completed_at ASC
        """,
        (user_id, module_name),
    )
    return [str(row["task_id"]) for row in (cursor.fetchall() or [])]


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
            "completed_tutorial_tasks": _fetch_completed_tutorial_tasks(cursor, user_id, selected_module),
            "owned_agents": _fetch_user_agents(cursor, user_id, selected_module),
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
            payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
            output.append(
                {
                    "event_id": row["id"],
                    "user_id": row["user_id"],
                    "module_name": row["module_name"],
                    "event_type": row["event_type"],
                    "event_version": int(row["event_version"]),
                    "run_id": row.get("run_id"),
                    "task_id": row.get("task_id"),
                    "payload": payload,
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
            SELECT wallet_balance, tutorial_completed
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_id, selected_module),
        )
        current = cursor.fetchone() or {}
        wallet_balance = float(current.get("wallet_balance", DEFAULT_STARTING_WALLET))
        tutorial_completed = bool(current.get("tutorial_completed", False))

        if event_type == "task_charged":
            wallet_balance = float(payload.get("wallet_after_cost", wallet_balance))
        elif event_type == "task_finished":
            wallet_balance = float(payload.get("wallet_after", wallet_balance))
            tutorial_completed = bool(payload.get("tutorial_completed", tutorial_completed))
            completed = payload.get("completed_tutorial_tasks")
            if isinstance(completed, list):
                _replace_tutorial_completed_tasks(cursor, user_id, selected_module, [str(x) for x in completed], now)
        elif event_type == "user_initialized":
            wallet_balance = float(payload.get("wallet_balance", wallet_balance))
            agents = payload.get("owned_agents")
            if isinstance(agents, list):
                _replace_user_agents(cursor, user_id, selected_module, agents, now)
            completed = payload.get("completed_tutorial_tasks")
            if isinstance(completed, list):
                _replace_tutorial_completed_tasks(cursor, user_id, selected_module, [str(x) for x in completed], now)
            tutorial_completed = bool(payload.get("tutorial_completed", tutorial_completed))

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
                last_event_id = %s,
                updated_at = %s
            WHERE user_id = %s AND module_name = %s
            """,
            (wallet_balance, tutorial_completed, event_id, now, user_id, selected_module),
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
            SELECT wallet_balance, tutorial_completed, updated_at
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_id, selected_module),
        )
        projection_row = cursor.fetchone()

        owned_agents = _fetch_user_agents(cursor, user_id, selected_module)
        if not owned_agents:
            owned_agents = list(DEFAULT_OWNED_AGENTS)
        completed_tasks = _fetch_completed_tutorial_tasks(cursor, user_id, selected_module)

        task_history_events = list_user_events(
            user_id=user_id,
            database_url=database_url,
            module_name=selected_module,
            event_type="task_finished",
            limit=1000,
        )
        return _build_user_row(
            user_row,
            projection_row,
            _task_history_from_events(task_history_events),
            owned_agents,
            completed_tasks,
        )
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
            SELECT wallet_balance, tutorial_completed, updated_at
            FROM user_state_projection
            WHERE user_id = %s AND module_name = %s
            LIMIT 1
            """,
            (user_row["id"], selected_module),
        )
        projection_row = cursor.fetchone()

        owned_agents = _fetch_user_agents(cursor, str(user_row["id"]), selected_module)
        if not owned_agents:
            owned_agents = list(DEFAULT_OWNED_AGENTS)
        completed_tasks = _fetch_completed_tutorial_tasks(cursor, str(user_row["id"]), selected_module)

        task_history_events = list_user_events(
            user_id=str(user_row["id"]),
            database_url=database_url,
            module_name=selected_module,
            event_type="task_finished",
            limit=1000,
        )
        return _build_user_row(
            user_row,
            projection_row,
            _task_history_from_events(task_history_events),
            owned_agents,
            completed_tasks,
        )
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
    completed_tasks_raw = tutorial_progress.get("completed_tasks") if isinstance(tutorial_progress, dict) else []
    completed_tasks = [str(x) for x in completed_tasks_raw] if isinstance(completed_tasks_raw, list) else []

    owned_agents_raw = user.get("owned_agents")
    owned_agents = owned_agents_raw if isinstance(owned_agents_raw, list) else list(DEFAULT_OWNED_AGENTS)

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
            INSERT INTO user_state_projection (user_id, module_name, wallet_balance, tutorial_completed, last_event_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, module_name) DO UPDATE SET
                wallet_balance = EXCLUDED.wallet_balance,
                tutorial_completed = EXCLUDED.tutorial_completed,
                updated_at = EXCLUDED.updated_at
            """,
            (user_id, selected_module, wallet_balance, tutorial_completed, None, now),
        )

        _replace_user_agents(cursor, user_id, selected_module, owned_agents, now)
        _replace_tutorial_completed_tasks(cursor, user_id, selected_module, completed_tasks, now)
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


def bind_agent_to_user(
        user_id: str,
        database_url: str,
        module_name: Optional[str],
        agent_name: str,
        status: str = "active",
) -> Dict[str, object]:
    selected_module = _active_module_name(module_name)
    normalized_user_id = normalize_id(user_id, "user_id")
    normalized_agent_name = normalize_id(agent_name, "agent_name")
    normalized_status = normalize_id(status or "active", "status", max_length=32)

    user = get_user_by_id(normalized_user_id, database_url, module_name=selected_module)
    if user is None:
        raise ValueError(f"User {normalized_user_id} not found")

    from core_engine.agent_store import get_agent  # local import to avoid cycle

    catalog_agent = get_agent(database_url, selected_module, normalized_agent_name)
    if catalog_agent is None:
        raise ValueError(f"Agent '{normalized_agent_name}' not found in module '{selected_module}'")

    owned_agents = list(user.get("owned_agents", []) or [])
    for item in owned_agents:
        if not isinstance(item, dict):
            continue
        if str(item.get("preset", "")) == normalized_agent_name:
            raise ValueError(f"Agent '{normalized_agent_name}' already bound to user")

    new_binding = {
        "agent_id": generate_id("uagt"),
        "preset": normalized_agent_name,
        "level": str(catalog_agent.get("level", "junior") or "junior"),
        "status": normalized_status,
        "affinity": float(catalog_agent.get("affinity", 0.5) or 0.5),
    }
    owned_agents.append(new_binding)
    user["owned_agents"] = owned_agents
    upsert_user_state(user, database_url)
    return new_binding


def unbind_agent_from_user(
        user_id: str,
        database_url: str,
        module_name: Optional[str],
        agent_id: str,
) -> Dict[str, object]:
    selected_module = _active_module_name(module_name)
    normalized_user_id = normalize_id(user_id, "user_id")
    normalized_agent_id = normalize_id(agent_id, "agent_id")

    user = get_user_by_id(normalized_user_id, database_url, module_name=selected_module)
    if user is None:
        raise ValueError(f"User {normalized_user_id} not found")

    owned_agents = list(user.get("owned_agents", []) or [])
    remaining = [item for item in owned_agents if str(item.get("agent_id", "")) != normalized_agent_id]
    if len(remaining) == len(owned_agents):
        raise ValueError(f"Agent binding '{normalized_agent_id}' not found for user")
    if not remaining:
        raise ValueError("User must keep at least one bound agent")

    user["owned_agents"] = remaining
    upsert_user_state(user, database_url)
    return {"agent_id": normalized_agent_id, "deleted": True}
