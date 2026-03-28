"""Unified ID generation using ULID as the primary strategy.

This keeps IDs lexicographically sortable by creation time and avoids
custom Snowflake implementations in project logic.
"""

from __future__ import annotations

import re
import uuid

try:
    import ulid  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    ulid = None

ID_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9:_-]+$")


def _new_ulid() -> str:
    if ulid is None:
        return uuid.uuid4().hex
    return str(ulid.new())


def generate_id(prefix: str | None = None) -> str:
    base = _new_ulid()
    if not prefix:
        return base
    return f"{prefix}_{base}"


def normalize_id(value: str, field_name: str = "id", max_length: int = 128) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} is too long (max {max_length})")
    if not ID_SAFE_PATTERN.match(normalized):
        raise ValueError(f"{field_name} contains unsafe characters")
    return normalized


def generate_user_id() -> str:
    return generate_id("usr")


def generate_run_id() -> str:
    return generate_id("run")


def generate_step_id() -> str:
    return generate_id("step")


def generate_asset_id() -> str:
    return generate_id("asset")


def generate_task_record_id() -> str:
    return generate_id("task")
