#!/usr/bin/env python3
"""Initialize output database schema (workflow_runs/workflow_steps/assets).

This script defaults to the `workforce` database and can optionally seed
lightweight demo rows for local inspection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Add project root to import path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core_engine.result_store import init_db  # noqa: E402


DEFAULT_DATABASE_URL = "postgresql://postgres:difyai123456@localhost:5432/workforce"


def _normalize_database_url(database_url: str, db_name: str) -> str:
    parsed = urlparse(database_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    path = f"/{db_name}"
    return urlunparse((
        parsed.scheme or "postgresql",
        parsed.netloc,
        path,
        parsed.params,
        urlencode(query),
        parsed.fragment,
    ))


def _extract_db_info(database_url: str) -> dict[str, object]:
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/") if parsed.path else "postgres",
    }


def _seed_demo_data(database_url: str) -> None:
    conn_info = _extract_db_info(database_url)
    conn = psycopg2.connect(
        host=conn_info["host"],
        port=conn_info["port"],
        user=conn_info["user"],
        password=conn_info["password"],
        database=conn_info["database"],
    )
    conn.autocommit = False
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("DELETE FROM assets")
        cursor.execute("DELETE FROM workflow_steps")
        cursor.execute("DELETE FROM workflow_runs")

        cursor.execute(
            """
            INSERT INTO workflow_runs (
                id, task_id, module_name, final_score, total_cost, status,
                error_message, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "test_run_001",
                "launch_coffee_subscription",
                "business_sim",
                95.5,
                0.002,
                "completed",
                None,
                "2026-03-27T10:00:00+00:00",
                "2026-03-27T10:00:03+00:00",
            ),
        )

        token_usage = {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180}
        cursor.execute(
            """
            INSERT INTO workflow_steps (
                id, run_id, step_index, agent_name, prompt, output, provider, model,
                token_usage_json, cost, cache_hit, effective_attributes_json,
                affinity_before, affinity_after, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "step_001_1",
                "test_run_001",
                0,
                "market_analyst",
                "Analyze launch potential.",
                "Strong demand in tier-1 cities.",
                "mock",
                "mvp-default",
                json.dumps(token_usage, ensure_ascii=True),
                0.001,
                0,
                json.dumps({}, ensure_ascii=True),
                None,
                None,
                "2026-03-27T10:00:01+00:00",
            ),
        )

        cursor.execute(
            """
            INSERT INTO assets (id, run_id, asset_type, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                "asset_001",
                "test_run_001",
                "business_plan",
                json.dumps({"summary": "Launch in tier-1 cities"}, ensure_ascii=True),
                "2026-03-27T10:00:03+00:00",
            ),
        )

        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _verify_tables(database_url: str) -> list[str]:
    conn_info = _extract_db_info(database_url)
    conn = psycopg2.connect(
        host=conn_info["host"],
        port=conn_info["port"],
        user=conn_info["user"],
        password=conn_info["password"],
        database=conn_info["database"],
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('workflow_runs', 'workflow_steps', 'assets')
            ORDER BY table_name
            """
        )
        rows = cursor.fetchall() or []
        return [str(r["table_name"]) for r in rows]
    finally:
        cursor.close()
        conn.close()


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Initialize output DB schema.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="PostgreSQL connection URL."
    )
    parser.add_argument(
        "--db-name",
        default="workforce",
        help="Target database name. Default: workforce"
    )
    parser.add_argument(
        "--with-test-data",
        action="store_true",
        help="Also insert minimal demo rows after schema init."
    )
    args = parser.parse_args()

    target_url = _normalize_database_url(args.database_url, args.db_name)
    db_info = _extract_db_info(target_url)

    print("=" * 60)
    print("Initializing Output Database")
    print("=" * 60)
    print(f"Host: {db_info['host']}:{db_info['port']}")
    print(f"Database: {db_info['database']}")
    print(f"User: {db_info['user']}")

    init_db(target_url)
    print("\n✅ Output schema initialized")

    if args.with_test_data:
        _seed_demo_data(target_url)
        print("✅ Demo test data inserted")

    existing = _verify_tables(target_url)
    print("\nTables in public schema:")
    for name in existing:
        print(f"  - {name}")

    expected = {"workflow_runs", "workflow_steps", "assets"}
    if set(existing) != expected:
        missing = expected - set(existing)
        if missing:
            raise RuntimeError(f"Missing expected tables: {sorted(missing)}")

    print("\n✅ Done")


if __name__ == "__main__":
    main()
