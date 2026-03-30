"""Backward-compatible wrapper around ULID-based ID generation.

Deprecated: keep this module only to avoid breaking old imports.
"""

from __future__ import annotations

from core_engine.id_generator import generate_id, generate_user_id


class Snowflake:
    """Compatibility shim for legacy Snowflake usage."""

    def __init__(self, machine_id: int = 0) -> None:
        self.machine_id = machine_id

    def generate(self) -> int:
        # Keep return type compatibility for old call sites needing int.
        token = generate_id()
        return int(token.replace("-", "")[:16], 16)

    def generate_string(self) -> str:
        return generate_id()


def get_snowflake(machine_id: int = 0) -> Snowflake:
    return Snowflake(machine_id=machine_id)

