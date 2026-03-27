#!/usr/bin/env python3
"""Test user API error handling."""

from fastapi.testclient import TestClient
from api.app import app

def main():
    client = TestClient(app)
    
    print('=' * 60)
    print('Testing User API Error Handling')
    print('=' * 60)
    print()
    
    # Test 1: Wrong HTTP method
    print('1. GET /users/register (wrong method, should be POST)')
    response = client.get('/users/register')
    print(f'   Status Code: {response.status_code}')
    print(f'   Response: {response.json()}')
    print()
    
    # Test 2: Duplicate username
    print('2. POST /users/register with duplicate username')
    response = client.post('/users/register', json={'username': 'testuser123'})
    print(f'   Status Code: {response.status_code}')
    print(f'   Response: {response.json()}')
    print()
    
    # Test 3: Non-existent user
    print('3. GET /users/by-username/nonexistent')
    response = client.get('/users/by-username/nonexistent')
    print(f'   Status Code: {response.status_code}')
    print(f'   Response: {response.json()}')
    print()
    
    # Test 4: Valid registration
    print('4. POST /users/register with new username')
    response = client.post('/users/register', json={'username': 'newuser789'})
    print(f'   Status Code: {response.status_code}')
    if response.status_code == 200:
        data = response.json()
        print(f'   ✓ User created: {data["username"]} (ID: {data["user_id"]})')
    else:
        print(f'   ✗ Error: {response.json()}')
    print()
    
    print('=' * 60)
    print('Tests Complete!')
    print('=' * 60)

if __name__ == '__main__':
    main()
