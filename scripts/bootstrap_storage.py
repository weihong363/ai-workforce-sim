#!/usr/bin/env python3
"""Initialize database schema and baseline seed data (non-destructive)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from core_engine.bootstrap import initialize_runtime_storage  # noqa: E402
from core_engine.config import get_settings  # noqa: E402


def main() -> None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:difyai123456@localhost:5432/workforce")
    settings = get_settings()
    stats = initialize_runtime_storage(database_url=database_url, module_name=settings.active_game_module)
    print("✅ storage initialized")
    print(f"module={settings.active_game_module}")
    print(f"seeded_tasks={int(stats.get('seeded_tasks', 0))}")


if __name__ == "__main__":
    main()
