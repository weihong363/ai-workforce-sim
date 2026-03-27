"""User database persistence layer."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor


def _get_connection(database_url: str):
    """Get PostgreSQL database connection."""
    parsed = urlparse(database_url)
    conn = psycopg2.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/") if parsed.path else "postgres"
    )
    conn.autocommit = False
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_user_db(database_url: str) -> None:
    """Initialize user database schema."""
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                wallet_balance REAL NOT NULL DEFAULT 120.0,
                tutorial_completed BOOLEAN NOT NULL DEFAULT FALSE,
                owned_agents_json TEXT NOT NULL DEFAULT '[]',
                tutorial_progress_json TEXT NOT NULL DEFAULT '{}',
                task_history_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Add index on username for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username 
            ON users(username)
        """)
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def create_user(
    user_id: str,
    username: str,
    database_url: str,
    wallet_balance: float = 120.0,
) -> Dict[str, object]:
    """Create a new user."""
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            INSERT INTO users (
                id, username, wallet_balance, tutorial_completed,
                owned_agents_json, tutorial_progress_json, task_history_json,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            username,
            wallet_balance,
            False,
            '[{"agent_id": "junior_001", "preset": "junior_worker", "level": "junior"}]',
            '{"completed_tasks": []}',
            '[]',
            now,
            now
        ))
        conn.commit()
        
        return {
            "user_id": user_id,
            "username": username,
            "wallet_balance": wallet_balance,
            "created_at": now,
        }
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id: str, database_url: str) -> Optional[Dict[str, object]]:
    """Get user by ID."""
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM users WHERE id = %s
        """, (user_id,))
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        return {
            "user_id": row["id"],
            "username": row["username"],
            "wallet_balance": float(row["wallet_balance"]),
            "tutorial_completed": bool(row["tutorial_completed"]),
            "owned_agents": eval(row["owned_agents_json"]),
            "tutorial_progress": eval(row["tutorial_progress_json"]),
            "task_history": eval(row["task_history_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        cursor.close()
        conn.close()


def get_user_by_username(username: str, database_url: str) -> Optional[Dict[str, object]]:
    """Get user by username."""
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM users WHERE username = %s
        """, (username,))
        
        row = cursor.fetchone()
        if row is None:
            return None
        
        return {
            "user_id": row["id"],
            "username": row["username"],
            "wallet_balance": float(row["wallet_balance"]),
            "tutorial_completed": bool(row["tutorial_completed"]),
            "owned_agents": eval(row["owned_agents_json"]),
            "tutorial_progress": eval(row["tutorial_progress_json"]),
            "task_history": eval(row["task_history_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        cursor.close()
        conn.close()


def check_username_exists(username: str, database_url: str) -> bool:
    """Check if username already exists."""
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT 1 FROM users WHERE username = %s LIMIT 1
        """, (username,))
        
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


def update_user_wallet(
    user_id: str,
    wallet_balance: float,
    database_url: str,
) -> None:
    """Update user wallet balance."""
    now = _utc_now_iso()
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            UPDATE users
            SET wallet_balance = %s, updated_at = %s
            WHERE id = %s
        """, (wallet_balance, now, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def add_task_to_history(
    user_id: str,
    task_record: Dict[str, object],
    database_url: str,
) -> None:
    """Add a task record to user's history."""
    import json
    
    conn = _get_connection(database_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get current history
        cursor.execute("""
            SELECT task_history_json FROM users WHERE id = %s
        """, (user_id,))
        
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"User {user_id} not found")
        
        # Parse current history, add new record, and update
        current_history = eval(row["task_history_json"])
        current_history.append(task_record)
        
        now = _utc_now_iso()
        cursor.execute("""
            UPDATE users
            SET task_history_json = %s, updated_at = %s
            WHERE id = %s
        """, (json.dumps(current_history), now, user_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
