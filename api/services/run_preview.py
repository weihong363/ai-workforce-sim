"""Helpers for response-safe run preview formatting."""

from __future__ import annotations

OUTPUT_PREVIEW_CHARS = 280


def preview_text(value: object, limit: int = OUTPUT_PREVIEW_CHARS) -> tuple[str, bool, int]:
    raw = str(value or "")
    truncated = len(raw) > limit
    return (raw[:limit] + (" ..." if truncated else ""), truncated, len(raw))


def with_output_previews(run_payload: dict) -> dict:
    payload = dict(run_payload)
    steps = payload.get("workflow_steps", [])
    if not isinstance(steps, list):
        return payload
    rewritten = []
    for step in steps:
        if not isinstance(step, dict):
            rewritten.append(step)
            continue
        copied = dict(step)
        preview, truncated, full_len = preview_text(copied.get("output", ""))
        copied["output"] = preview
        copied["raw_output_preview"] = preview
        copied["full_output_length"] = full_len
        copied["truncated_for_display"] = truncated
        copied["stored_full_output"] = True
        rewritten.append(copied)
    payload["workflow_steps"] = rewritten
    return payload
