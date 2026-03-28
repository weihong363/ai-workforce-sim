#!/usr/bin/env python3
"""Rebuild database schema for workforce (destructive, no backward compatibility)."""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from core_engine.result_store import rebuild_db as rebuild_output_db
from core_engine.task_store import rebuild_task_db
from core_engine.user_store import rebuild_user_db
from core_engine.agent_store import rebuild_agent_db, seed_module_agents
from core_engine.module_facade import ModuleFacade
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
        # Rebuild output/task schema first, then user schema.
        rebuild_output_db(DATABASE_URL)
        rebuild_task_db(DATABASE_URL)
        rebuild_user_db(DATABASE_URL)
        rebuild_agent_db(DATABASE_URL)
        settings = get_settings()
        facade = ModuleFacade.from_name(settings.active_game_module)
        seed_module_agents(DATABASE_URL, settings.active_game_module, getattr(facade.agents, "AGENTS", {}))

        print("\n✅ Database rebuilt successfully!")
        print("\nCreated tables:")
        print("  - users")
        print("  - user_events")
        print("  - user_state_projection")
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
    except Exception as exc:
        print(f"\n❌ Error rebuilding database: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
