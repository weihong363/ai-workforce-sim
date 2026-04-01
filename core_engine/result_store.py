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
                user_id TEXT,
                task_id TEXT NOT NULL,
                module_name TEXT NOT NULL,
                final_score REAL,
                total_cost REAL,
                total_tokens INTEGER,
                total_latency_ms INTEGER,
                clarity_score REAL,
                deviation_detected BOOLEAN,
                constraint_adherence_score REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        cursor.execute("COMMENT ON TABLE workflow_runs IS 'Top-level execution run records for each task invocation.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.id IS 'Primary run identifier (ULID-like text).'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.user_id IS 'End user identifier associated with the run (nullable).'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.task_id IS 'Logical task id from tasks catalog.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.module_name IS 'Game module namespace used by this run.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.final_score IS 'Final evaluation score for the run.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.total_cost IS 'Total model cost in USD aggregated from workflow steps.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.total_tokens IS 'Total token usage aggregated from workflow steps.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.total_latency_ms IS 'Total latency in milliseconds aggregated from workflow steps.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.clarity_score IS 'Prompt clarity heuristic score for this run.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.deviation_detected IS 'Whether instruction deviation was detected in this run.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.constraint_adherence_score IS 'Constraint adherence ratio in [0,1].'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.status IS 'Run lifecycle status: pending/running/success/failed.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.error_message IS 'Failure detail when status is failed.'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.created_at IS 'Run creation timestamp (UTC).'")
        cursor.execute("COMMENT ON COLUMN workflow_runs.updated_at IS 'Last run update timestamp (UTC).'")
        # Idempotent schema upgrade for existing databases.
        cursor.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS user_id TEXT")
        cursor.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS total_tokens INTEGER")
        cursor.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS total_latency_ms INTEGER")
        cursor.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS clarity_score REAL")
        cursor.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS deviation_detected BOOLEAN")
        cursor.execute("ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS constraint_adherence_score REAL")

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
                agent_level TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                latency_ms INTEGER,
                cache_hit INTEGER NOT NULL DEFAULT 0,
                effective_effort REAL,
                effective_obedience REAL,
                effective_initiative REAL,
                affinity_before REAL,
                affinity_after REAL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        cursor.execute("COMMENT ON TABLE workflow_steps IS 'Per-step execution records for each workflow run.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.id IS 'Primary workflow step identifier (ULID-like text).'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.run_id IS 'Parent run id in workflow_runs.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.step_index IS 'Zero-based index of the step in workflow order.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.agent_name IS 'Agent role/preset name for this step.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.prompt IS 'Final prompt sent to model provider for this step.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.output IS 'Full raw model output for this step (not pre-truncated).'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.provider IS 'Provider used for this step (including fallback provider).'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.model IS 'Concrete model used for this step.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.agent_level IS 'Agent level (junior/mid/senior) effective at execution time.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.prompt_tokens IS 'Prompt token count reported by provider.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.completion_tokens IS 'Completion token count reported by provider.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.total_tokens IS 'Total token count reported by provider.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.cost IS 'Step-level cost in USD after cost-weighting.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.latency_ms IS 'Step-level latency in milliseconds.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.cache_hit IS '1 if step output served from cache, else 0.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.effective_effort IS 'Runtime effective effort after weights and modifiers.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.effective_obedience IS 'Runtime effective obedience after weights and modifiers.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.effective_initiative IS 'Runtime effective initiative after weights and modifiers.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.affinity_before IS 'Agent affinity value before this step execution.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.affinity_after IS 'Agent affinity value after this step execution.'")
        cursor.execute("COMMENT ON COLUMN workflow_steps.created_at IS 'Step record creation timestamp (UTC).'")
        # Idempotent schema upgrade for existing databases.
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS agent_level TEXT")
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS latency_ms INTEGER")
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS effective_effort REAL")
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS effective_obedience REAL")
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS effective_initiative REAL")
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS affinity_before REAL")
        cursor.execute("ALTER TABLE workflow_steps ADD COLUMN IF NOT EXISTS affinity_after REAL")
        cursor.execute("ALTER TABLE workflow_steps DROP COLUMN IF EXISTS effective_affinity")

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
        cursor.execute("COMMENT ON TABLE assets IS 'Materialized outputs generated from workflow runs.'")
        cursor.execute("COMMENT ON COLUMN assets.id IS 'Primary asset identifier (ULID-like text).'")
        cursor.execute("COMMENT ON COLUMN assets.run_id IS 'Parent run id in workflow_runs.'")
        cursor.execute("COMMENT ON COLUMN assets.asset_type IS 'Asset type label (e.g., business_plan).'")
        cursor.execute("COMMENT ON COLUMN assets.payload_json IS 'JSONB payload including result content and debug metadata.'")
        cursor.execute("COMMENT ON COLUMN assets.created_at IS 'Asset creation timestamp (UTC).'")

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


def create_run(task_id: str, module_name: str, database_url: str, user_id: Optional[str] = None) -> str:
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
            INSERT INTO workflow_runs (
                id, user_id, task_id, module_name, final_score, total_cost,
                total_tokens, total_latency_ms, clarity_score, deviation_detected, constraint_adherence_score,
                status, error_message, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, user_id, task_id, module_name, None, 0.0, 0, 0, None, None, None, "pending", None, now, now),
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
    total_tokens: Optional[int] = None,
    total_latency_ms: Optional[int] = None,
    clarity_score: Optional[float] = None,
    deviation_detected: Optional[bool] = None,
    constraint_adherence_score: Optional[float] = None,
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
                total_tokens = COALESCE(%s, total_tokens),
                total_latency_ms = COALESCE(%s, total_latency_ms),
                clarity_score = COALESCE(%s, clarity_score),
                deviation_detected = COALESCE(%s, deviation_detected),
                constraint_adherence_score = COALESCE(%s, constraint_adherence_score),
                error_message = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (
                status,
                final_score,
                total_cost,
                total_tokens,
                total_latency_ms,
                clarity_score,
                deviation_detected,
                constraint_adherence_score,
                error_message,
                now,
                run_id,
            ),
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
                    provider, model, agent_level,
                    prompt_tokens, completion_tokens, total_tokens,
                    cost, latency_ms, cache_hit,
                    effective_effort, effective_obedience, effective_initiative,
                    affinity_before, affinity_after, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    generate_step_id(),
                    run_id,
                    index,
                    step.get("agent_name", ""),
                    step.get("prompt", ""),
                    step.get("raw_output", step.get("output", "")),
                    step.get("provider", ""),
                    step.get("model", ""),
                    step.get("agent_level"),
                    int(token_usage.get("prompt_tokens", 0) or 0),
                    int(token_usage.get("completion_tokens", 0) or 0),
                    int(token_usage.get("total_tokens", 0) or 0),
                    float(step.get("cost", 0.0) or 0.0),
                    int(float(step.get("latency_ms", 0) or 0)),
                    1 if bool(step.get("cache_hit", False)) else 0,
                    float(effective.get("effort", 0.0) or 0.0) if effective.get("effort") is not None else None,
                    float(effective.get("obedience", 0.0) or 0.0) if effective.get("obedience") is not None else None,
                    float(effective.get("initiative", 0.0) or 0.0) if effective.get("initiative") is not None else None,
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
            SELECT id, user_id, task_id, module_name, final_score, total_cost, total_tokens, total_latency_ms,
                   clarity_score, deviation_detected, constraint_adherence_score,
                   status, error_message, created_at, updated_at
            FROM workflow_runs WHERE id = %s
            """,
            (run_id,),
        )
        run_row = cursor.fetchone()
        if run_row is None:
            return None

        cursor.execute(
            """
            SELECT step_index, agent_name, prompt, output, provider, model, agent_level,
                   prompt_tokens, completion_tokens, total_tokens,
                   cost, latency_ms, cache_hit,
                   effective_effort, effective_obedience, effective_initiative,
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
            SELECT id, asset_type, payload_json, created_at
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
                    "agent_level": row.get("agent_level"),
                    "token_usage": {
                        "prompt_tokens": int(row.get("prompt_tokens") or 0),
                        "completion_tokens": int(row.get("completion_tokens") or 0),
                        "total_tokens": int(row.get("total_tokens") or 0),
                    },
                    "cost": float(row["cost"] or 0.0),
                    "latency_ms": int(row.get("latency_ms") or 0),
                    "cache_hit": bool(row["cache_hit"]),
                    "effective_attributes": {
                        "effort": row.get("effective_effort"),
                        "obedience": row.get("effective_obedience"),
                        "initiative": row.get("effective_initiative"),
                        "affinity": row.get("affinity_before"),
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

        semantic_analysis: Optional[Dict[str, object]] = None
        for row in asset_rows:
            payload = row.get("payload_json")
            if not isinstance(payload, dict):
                continue
            debug_block = payload.get("debug")
            if not isinstance(debug_block, dict):
                continue
            semantic_block = debug_block.get("semantic_analysis")
            if isinstance(semantic_block, dict):
                semantic_analysis = semantic_block
                break

        return {
            "run_id": run_row["id"],
            "task_id": run_row["task_id"],
            "user_id": run_row.get("user_id"),
            "module_name": run_row["module_name"],
            "final_score": run_row["final_score"],
            "total_cost": float(run_row["total_cost"] or 0.0),
            "total_tokens": int(run_row.get("total_tokens") or 0),
            "total_latency_ms": int(run_row.get("total_latency_ms") or 0),
            "clarity_score": run_row.get("clarity_score"),
            "deviation_detected": bool(run_row["deviation_detected"]) if run_row.get("deviation_detected") is not None else None,
            "constraint_adherence_score": run_row.get("constraint_adherence_score"),
            "status": run_row["status"],
            "error_message": run_row["error_message"],
            "created_at": run_row["created_at"].isoformat() if hasattr(run_row["created_at"], "isoformat") else str(run_row["created_at"]),
            "updated_at": run_row["updated_at"].isoformat() if hasattr(run_row["updated_at"], "isoformat") else str(run_row["updated_at"]),
            "workflow_steps": steps,
            "assets": assets,
            "semantic_analysis": semantic_analysis or {},
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
