#!/usr/bin/env python3
"""Test user registration and username system."""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core_engine.snowflake import generate_user_id
from game_modules.business_sim.progression import (
    check_username_exists,
    get_user_by_username,
    init_user,
)


def test_snowflake():
    """Test snowflake ID generation."""
    print("=" * 60)
    print("1. Testing Snowflake ID Generation")
    print("=" * 60)
    
    id1 = generate_user_id()
    id2 = generate_user_id()
    
    print(f"Generated ID 1: {id1}")
    print(f"Generated ID 2: {id2}")
    print(f"IDs are unique: {id1 != id2}")
    print(f"ID is numeric: {id1.isdigit()}")
    print(f"ID length: {len(id1)} digits")
    print()


def test_username_uniqueness():
    """Test username uniqueness checking."""
    print("=" * 60)
    print("2. Testing Username Uniqueness")
    print("=" * 60)
    
    # Test with a test username
    test_username = f"test_user_{generate_user_id()[-4:]}"
    
    # Check if available (should be False for new user)
    is_available = not check_username_exists(test_username)
    print(f"Username '{test_username}' available: {is_available}")
    
    # Create user
    user_id = generate_user_id()
    user_data = init_user(user_id=user_id, username=test_username)
    print(f"Created user: {user_data['username']} (ID: {user_data['user_id']})")
    
    # Check again - should exist now
    is_available_after = not check_username_exists(test_username)
    print(f"Username '{test_username}' available after creation: {is_available_after}")
    print()


def test_get_user_by_username():
    """Test retrieving user by username."""
    print("=" * 60)
    print("3. Testing Get User by Username")
    print("=" * 60)
    
    # Create another user
    test_username = f"alice_{generate_user_id()[-4:]}"
    user_id = generate_user_id()
    
    user_data = init_user(user_id=user_id, username=test_username)
    print(f"Created user: {test_username}")
    
    # Retrieve by username
    retrieved = get_user_by_username(test_username)
    if retrieved:
        print(f"✓ Successfully retrieved user by username")
        print(f"  User ID: {retrieved['user_id']}")
        print(f"  Wallet: ${retrieved['wallet_balance']}")
        print(f"  Created: {retrieved['created_at']}")
    else:
        print(f"✗ Failed to retrieve user by username")
    print()


def test_duplicate_prevention():
    """Test that duplicate usernames are prevented."""
    print("=" * 60)
    print("4. Testing Duplicate Username Prevention")
    print("=" * 60)
    
    # Create first user
    bob_username = f"bob_{generate_user_id()[-4:]}"
    bob_id = generate_user_id()
    init_user(user_id=bob_id, username=bob_username)
    print(f"Created first user: {bob_username}")
    
    # Try to create second user with same username
    try:
        charlie_id = generate_user_id()
        init_user(user_id=charlie_id, username=bob_username)
        print(f"✗ ERROR: Duplicate username was allowed!")
    except ValueError as e:
        print(f"✓ Correctly prevented duplicate username")
        print(f"  Error message: {e}")
    print()


if __name__ == "__main__":
    print("\n🚀 User System Test\n")
    
    test_snowflake()
    test_username_uniqueness()
    test_get_user_by_username()
    test_duplicate_prevention()
    
    print("=" * 60)
    print("✅ All Tests Complete!")
    print("=" * 60)
    print("\nKey Features:")
    print("  • Distributed unique ID generation (Snowflake)")
    print("  • Username uniqueness enforcement")
    print("  • User lookup by username")
    print("  • Duplicate prevention")
    print()
