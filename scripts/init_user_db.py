#!/usr/bin/env python3
"""Initialize user database schema."""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from core_engine.user_store import init_user_db

# Load environment
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:difyai123456@localhost:5432/dify")

def main():
    """Initialize user database."""
    print("=" * 60)
    print("Initializing User Database")
    print("=" * 60)
    print(f"\nDatabase URL: {DATABASE_URL}")
    
    try:
        # Initialize user database
        init_user_db(DATABASE_URL)
        
        print("\n✅ User database initialized successfully!")
        print("\nCreated tables:")
        print("  - users (with username index)")
        print("\nUser table schema:")
        print("  - id (TEXT, PRIMARY KEY)")
        print("  - username (TEXT, UNIQUE NOT NULL)")
        print("  - wallet_balance (REAL, DEFAULT 120.0)")
        print("  - tutorial_completed (BOOLEAN, DEFAULT FALSE)")
        print("  - owned_agents_json (TEXT)")
        print("  - tutorial_progress_json (TEXT)")
        print("  - task_history_json (TEXT)")
        print("  - created_at (TEXT)")
        print("  - updated_at (TEXT)")
        
    except Exception as e:
        print(f"\n❌ Error initializing database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
