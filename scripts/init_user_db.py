#!/usr/bin/env python3
"""Rebuild database schema for workforce (destructive, no backward compatibility)."""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from core_engine.bootstrap import rebuild_storage_destructive
from core_engine.config import get_settings

# Load environment
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:difyai123456@localhost:5432/workforce")


def main() -> None:
    print("=" * 60)
    print("Rebuilding Workforce Database (Destructive)")
    print("=" * 60)
    print(f"\nDatabase URL: {DATABASE_URL}")

    try:
        settings = get_settings()
        stats = rebuild_storage_destructive(
            database_url=DATABASE_URL,
            module_name=settings.active_game_module,
        )

        print("\n✅ Database rebuilt successfully!")
        print("\nCreated tables:")
        print("  - users")
        print("  - user_events")
        print("  - user_state_projection")
        print("  - user_agents")
        print("  - user_tutorial_progress")
        print("  - workflow_runs")
        print("  - workflow_steps")
        print("  - assets")
        print("  - game_tasks")
        print("  - agents")
        print("\nKey schema changes:")
        print("  - users table no longer stores progression JSON columns")
        print("  - task_name renamed to task_id in workflow_runs/game_tasks")
        print("  - timestamps are TIMESTAMPTZ")
        print("  - payload/config columns are JSONB")
        print(f"  - seeded_tasks: {int(stats.get('seeded_tasks', 0))}")
    except Exception as exc:
        print(f"\n❌ Error rebuilding database: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
