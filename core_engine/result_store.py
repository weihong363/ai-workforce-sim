"""PostgreSQL-backed persistence for workflow runs, steps, and assets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

from core_engine.id_generator import generate_asset_id, generate_run_id, generate_step_id, normalize_id


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


def init_db(database_url: str) -> None:
    """Initialize PostgreSQL database schema."""
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                module_name TEXT NOT NULL,
                final_score REAL,
                total_cost REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                step_index INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                output TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                cache_hit INTEGER NOT NULL DEFAULT 0,
                effective_effort REAL,
                effective_obedience REAL,
                effective_initiative REAL,
                effective_affinity REAL,
                affinity_before REAL,
                affinity_after REAL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                asset_type TEXT NOT NULL,
                payload_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_module_name ON workflow_runs(module_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_steps_run_id ON workflow_steps(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assets_run_id ON assets(run_id)")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def rebuild_db(database_url: str) -> None:
    """Drop and recreate output schema tables."""
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("DROP TABLE IF EXISTS assets")
        cursor.execute("DROP TABLE IF EXISTS workflow_steps")
        cursor.execute("DROP TABLE IF EXISTS workflow_runs")
        cursor.execute("DROP TABLE IF EXISTS runs")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    init_db(database_url)


def create_run(task_id: str, module_name: str, database_url: str) -> str:
    init_db(database_url)
    run_id = generate_run_id()
    task_id = normalize_id(task_id, "task_id")
    module_name = normalize_id(module_name, "module_name")
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            INSERT INTO workflow_runs (id, task_id, module_name, final_score, total_cost, status, error_message, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, task_id, module_name, None, 0.0, "pending", None, now, now),
        )
        conn.commit()
        return run_id
    finally:
        cursor.close()
        conn.close()


def update_run_status(
    run_id: str,
    status: str,
    database_url: str,
    final_score: Optional[float] = None,
    total_cost: Optional[float] = None,
    error_message: Optional[str] = None,
) -> None:
    run_id = normalize_id(run_id, "run_id")
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            UPDATE workflow_runs
            SET status = %s,
                final_score = COALESCE(%s, final_score),
                total_cost = COALESCE(%s, total_cost),
                error_message = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (status, final_score, total_cost, error_message, now, run_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def persist_workflow_steps(run_id: str, workflow_results: List[Dict[str, object]], database_url: str) -> None:
    run_id = normalize_id(run_id, "run_id")
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        for index, step in enumerate(workflow_results):
            token_usage = step.get("token_usage") if isinstance(step.get("token_usage"), dict) else {}
            effective = step.get("effective_attributes") if isinstance(step.get("effective_attributes"), dict) else {}
            cursor.execute(
                """
                INSERT INTO workflow_steps (
                    id, run_id, step_index, agent_name, prompt, output,
                    provider, model,
                    prompt_tokens, completion_tokens, total_tokens,
                    cost, cache_hit,
                    effective_effort, effective_obedience, effective_initiative, effective_affinity,
                    affinity_before, affinity_after, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    generate_step_id(),
                    run_id,
                    index,
                    step.get("agent_name", ""),
                    step.get("prompt", ""),
                    step.get("output", ""),
                    step.get("provider", ""),
                    step.get("model", ""),
                    int(token_usage.get("prompt_tokens", 0) or 0),
                    int(token_usage.get("completion_tokens", 0) or 0),
                    int(token_usage.get("total_tokens", 0) or 0),
                    float(step.get("cost", 0.0) or 0.0),
                    1 if bool(step.get("cache_hit", False)) else 0,
                    float(effective.get("effort", 0.0) or 0.0) if effective.get("effort") is not None else None,
                    float(effective.get("obedience", 0.0) or 0.0) if effective.get("obedience") is not None else None,
                    float(effective.get("initiative", 0.0) or 0.0) if effective.get("initiative") is not None else None,
                    float(effective.get("affinity", 0.0) or 0.0) if effective.get("affinity") is not None else None,
                    step.get("affinity_before"),
                    step.get("affinity_after"),
                    now,
                ),
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def persist_asset(run_id: str, asset: Dict[str, object], database_url: str) -> str:
    run_id = normalize_id(run_id, "run_id")
    asset_id = generate_asset_id()
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            INSERT INTO assets (id, run_id, asset_type, payload_json, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            """,
            (
                asset_id,
                run_id,
                str(asset.get("asset_type", "unknown")),
                json.dumps(asset.get("payload", {}), ensure_ascii=True),
                now,
            ),
        )
        conn.commit()
        return asset_id
    finally:
        cursor.close()
        conn.close()


def get_run(run_id: str, database_url: str) -> Optional[Dict[str, object]]:
    run_id = normalize_id(run_id, "run_id")
    init_db(database_url)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT id, task_id, module_name, final_score, total_cost, status, error_message, created_at, updated_at
            FROM workflow_runs WHERE id = %s
            """,
            (run_id,),
        )
        run_row = cursor.fetchone()
        if run_row is None:
            return None

        cursor.execute(
            """
            SELECT step_index, agent_name, prompt, output, provider, model,
                   prompt_tokens, completion_tokens, total_tokens,
                   cost, cache_hit,
                   effective_effort, effective_obedience, effective_initiative, effective_affinity,
                   affinity_before, affinity_after, created_at
            FROM workflow_steps
            WHERE run_id = %s
            ORDER BY step_index ASC
            """,
            (run_id,),
        )
        steps_rows = cursor.fetchall() or []

        cursor.execute(
            """
            SELECT id, asset_type, created_at
            FROM assets
            WHERE run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        )
        asset_rows = cursor.fetchall() or []

        steps: List[Dict[str, object]] = []
        for row in steps_rows:
            steps.append(
                {
                    "step_index": row["step_index"],
                    "agent_name": row["agent_name"],
                    "prompt": row["prompt"],
                    "output": row["output"],
                    "provider": row["provider"],
                    "model": row["model"],
                    "token_usage": {
                        "prompt_tokens": int(row.get("prompt_tokens") or 0),
                        "completion_tokens": int(row.get("completion_tokens") or 0),
                        "total_tokens": int(row.get("total_tokens") or 0),
                    },
                    "cost": float(row["cost"] or 0.0),
                    "cache_hit": bool(row["cache_hit"]),
                    "effective_attributes": {
                        "effort": row.get("effective_effort"),
                        "obedience": row.get("effective_obedience"),
                        "initiative": row.get("effective_initiative"),
                        "affinity": row.get("effective_affinity"),
                    },
                    "affinity_before": row["affinity_before"],
                    "affinity_after": row["affinity_after"],
                    "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                }
            )

        assets: List[Dict[str, object]] = [
            {
                "asset_id": row["id"],
                "asset_type": row["asset_type"],
                "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            }
            for row in asset_rows
        ]

        return {
            "run_id": run_row["id"],
            "task_id": run_row["task_id"],
            "module_name": run_row["module_name"],
            "final_score": run_row["final_score"],
            "total_cost": float(run_row["total_cost"] or 0.0),
            "status": run_row["status"],
            "error_message": run_row["error_message"],
            "created_at": run_row["created_at"].isoformat() if hasattr(run_row["created_at"], "isoformat") else str(run_row["created_at"]),
            "updated_at": run_row["updated_at"].isoformat() if hasattr(run_row["updated_at"], "isoformat") else str(run_row["updated_at"]),
            "workflow_steps": steps,
            "assets": assets,
        }
    finally:
        cursor.close()
        conn.close()


def get_asset(asset_id: str, database_url: str) -> Optional[Dict[str, object]]:
    asset_id = normalize_id(asset_id, "asset_id")
    init_db(database_url)
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT id, run_id, asset_type, payload_json, created_at
            FROM assets
            WHERE id = %s
            """,
            (asset_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        payload = row.get("payload_json")
        if not isinstance(payload, dict):
            try:
                payload = json.loads(str(payload or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError):
                payload = {}

        return {
            "asset_id": row["id"],
            "run_id": row["run_id"],
            "asset_type": row["asset_type"],
            "payload": payload,
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        }
    finally:
        cursor.close()
        conn.close()
