#!/usr/bin/env python3
"""Minimal local demo flow for playable MVP.

Usage:
  python scripts/demo_playable_flow.py --base-url http://127.0.0.1:8000 --user-id usr_demo_001
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib import error, parse, request


def _http_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc


def _pick_first_task(tasks_payload: dict) -> str:
    available = tasks_payload.get("available", [])
    if not isinstance(available, list) or not available:
        raise RuntimeError("No available tasks found.")
    first = available[0] if isinstance(available[0], dict) else {}
    task_id = str(first.get("task_id", "")).strip()
    if not task_id:
        raise RuntimeError("Available task has no task_id.")
    return task_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Run minimal playable API flow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--user-id", default="usr_demo_001", help="Demo player ID")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    user_id = args.user_id

    print("1) Register or reuse user")
    username = user_id.replace("usr_", "").replace("_", "")
    try:
        reg_payload = _http_json("POST", f"{base_url}/users/register", {"username": username or "demo_player"})
        user_id = str(reg_payload.get("user_id", user_id))
        print(json.dumps(reg_payload, ensure_ascii=False, indent=2))
    except Exception:
        by_name = _http_json("GET", f"{base_url}/users/by-username/{parse.quote(username or 'demo_player')}")
        user_id = str(by_name.get("user_id", user_id))
        print(json.dumps(by_name, ensure_ascii=False, indent=2))

    print("\n2) Start game")
    start_payload = _http_json("POST", f"{base_url}/game/start", {"user_id": user_id})
    print(json.dumps(start_payload, ensure_ascii=False, indent=2))

    print("\n3) Fetch tasks")
    query = parse.urlencode({"user_id": user_id})
    tasks_payload = _http_json("GET", f"{base_url}/tasks?{query}")
    print(json.dumps(tasks_payload, ensure_ascii=False, indent=2))

    task_id = _pick_first_task(tasks_payload)
    print(f"\n4) Run task: {task_id}")
    run_payload = _http_json(
        "POST",
        f"{base_url}/run-task",
        {
            "task_id": task_id,
            "user_id": user_id,
            "instructions": "Define target customer, pricing, timeline, budget, and key risk.",
        },
    )
    print(json.dumps(run_payload, ensure_ascii=False, indent=2))

    print("\n5) Fetch tasks again")
    tasks_after = _http_json("GET", f"{base_url}/tasks?{query}")
    print(json.dumps(tasks_after, ensure_ascii=False, indent=2))

    print("\nDemo flow completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
