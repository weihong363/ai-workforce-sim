"""Centralized storage bootstrap (schema + seed), kept outside business modules."""

from __future__ import annotations

from urllib.parse import urlparse
from typing import Dict

import psycopg2

from core_engine.agent_store import init_agent_db, rebuild_agent_db, seed_module_agents
from core_engine.module_facade import ModuleFacade
from core_engine.result_store import init_db, rebuild_db as rebuild_output_db
from core_engine.task_store import init_task_db, rebuild_task_db, seed_tasks
from core_engine.user_store import init_user_db, rebuild_user_db


def _seed_module_tasks(database_url: str, module_name: str) -> int:
    facade = ModuleFacade.from_name(module_name)
    seed_getter = getattr(facade.tasks, "get_seed_tasks", None)
    if not callable(seed_getter):
        return 0
    task_map = seed_getter() or {}
    rows = []
    for task_id, cfg in task_map.items():
        if not isinstance(cfg, dict):
            continue
        rows.append({"task_id": str(task_id), "task_config": dict(cfg), "source": "seed"})
    if not rows:
        return 0
    seed_tasks(database_url, module_name, rows)
    return len(rows)


def initialize_runtime_storage(database_url: str, module_name: str) -> Dict[str, int]:
    """Create required tables and seed baseline data for active module."""
    init_db(database_url)
    init_task_db(database_url)
    init_user_db(database_url)
    init_agent_db(database_url)

    facade = ModuleFacade.from_name(module_name)
    seed_module_agents(database_url, module_name, getattr(facade.agents, "AGENTS", {}))
    seeded_tasks = _seed_module_tasks(database_url, module_name)
    return {"seeded_tasks": seeded_tasks}


def rebuild_storage_destructive(database_url: str, module_name: str) -> Dict[str, int]:
    """Drop/rebuild core tables and reseed baseline data."""
    rebuild_output_db(database_url)
    rebuild_task_db(database_url)
    rebuild_user_db(database_url)
    rebuild_agent_db(database_url)
    facade = ModuleFacade.from_name(module_name)
    seed_module_agents(database_url, module_name, getattr(facade.agents, "AGENTS", {}))
    seeded_tasks = _seed_module_tasks(database_url, module_name)
    return {"seeded_tasks": seeded_tasks}


def _is_postgres_url(database_url: str) -> bool:
    scheme = str(urlparse(database_url).scheme or "").lower()
    return scheme.startswith("postgres")


def _connect_postgres(database_url: str):
    parsed = urlparse(database_url)
    conn = psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/") if parsed.path else "postgres",
    )
    return conn


def validate_runtime_storage(database_url: str, module_name: str) -> Dict[str, object]:
    """Read-only validation for runtime storage readiness (no DDL/DML)."""
    if not _is_postgres_url(database_url):
        return {
            "database_initialized": False,
            "user_database_initialized": False,
            "agent_database_initialized": False,
            "task_catalog_initialized": False,
            "seeded_tasks": 0,
            "error": "Only PostgreSQL is supported for runtime validation.",
        }

    required_output_tables = {"workflow_runs", "workflow_steps", "assets"}
    required_user_tables = {"users", "user_events", "user_state_projection", "user_agents", "user_tutorial_progress"}
    required_agent_tables = {"agents"}
    required_task_tables = {"game_tasks"}

    conn = _connect_postgres(database_url)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        existing = {str(row[0]) for row in (cursor.fetchall() or [])}
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM game_tasks
            WHERE module_name = %s
            """,
            (module_name,),
        )
        seeded_tasks = int((cursor.fetchone() or [0])[0] or 0)
    except Exception as exc:
        return {
            "database_initialized": False,
            "user_database_initialized": False,
            "agent_database_initialized": False,
            "task_catalog_initialized": False,
            "seeded_tasks": 0,
            "error": str(exc),
        }
    finally:
        cursor.close()
        conn.close()

    output_ready = required_output_tables.issubset(existing)
    user_ready = required_user_tables.issubset(existing)
    agent_ready = required_agent_tables.issubset(existing)
    task_ready = required_task_tables.issubset(existing) and seeded_tasks > 0

    return {
        "database_initialized": bool(output_ready),
        "user_database_initialized": bool(user_ready),
        "agent_database_initialized": bool(agent_ready),
        "task_catalog_initialized": bool(task_ready),
        "seeded_tasks": seeded_tasks,
        "error": None,
    }
