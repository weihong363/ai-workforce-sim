"""Backward-compatible task runner exports with patch-friendly bridges."""

from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional

from api.services.task_runner import benchmark as _bench
from api.services.task_runner import core as _core

# Re-export frequently patched dependencies for backward-compat tests.
create_run = _core.create_run
persist_asset = _core.persist_asset
persist_workflow_steps = _core.persist_workflow_steps
update_run_status = _core.update_run_status
ModuleFacade = _core.ModuleFacade
resolve_module_name = _core.resolve_module_name

RUN_RUNTIME_STATE = _core.RUN_RUNTIME_STATE
init_runtime_run = _core.init_runtime_run
mark_runtime_failed = _core.mark_runtime_failed
get_runtime_run = _core.get_runtime_run

_normalize_semantic_text = _core._normalize_semantic_text
_semantic_patterns_for_constraint = _core._semantic_patterns_for_constraint
_contains_semantic_match = _core._contains_semantic_match
_missing_reason_from_constraint = _core._missing_reason_from_constraint
_assess_constraints = _core._assess_constraints
_merge_agent_profiles = _core._merge_agent_profiles
_build_comparison_fields = _core._build_comparison_fields
_constraint_adherence_score = _core._constraint_adherence_score
_estimate_agent_task_fit = _core._estimate_agent_task_fit
_build_player_feedback = _core._build_player_feedback
_build_semantic_analysis = _core._build_semantic_analysis
_output_preview = _core._output_preview
_task_cache_key = _core._task_cache_key

_build_player_friendly_row = _bench._build_player_friendly_row
_build_benchmark_advice = _bench._build_benchmark_advice


def _sync_core_patches() -> None:
    # Keep monkeypatch behavior stable for legacy tests/callers that patch api.run_task.*
    _core.create_run = create_run
    _core.persist_asset = persist_asset
    _core.persist_workflow_steps = persist_workflow_steps
    _core.update_run_status = update_run_status
    _core.ModuleFacade = ModuleFacade
    _core.resolve_module_name = resolve_module_name


def _sync_benchmark_patches() -> None:
    _bench.ModuleFacade = ModuleFacade
    _bench.resolve_module_name = resolve_module_name
    _bench.run_task = run_task


def run_task(
    task_id: str,
    module_name: Optional[str] = None,
    agent_overrides: Optional[Dict[str, Dict[str, object]]] = None,
    run_id_override: Optional[str] = None,
    user_id: Optional[str] = None,
    instructions: Optional[str] = None,
    model_overrides: Optional[Dict[str, str]] = None,
    task_definition_override: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    _sync_core_patches()
    return _core.run_task(
        task_id=task_id,
        module_name=module_name,
        agent_overrides=agent_overrides,
        run_id_override=run_id_override,
        user_id=user_id,
        instructions=instructions,
        model_overrides=model_overrides,
        task_definition_override=task_definition_override,
    )


def benchmark_models(
    task_id: str,
    agent_level: str,
        models: List[str],
    module_name: Optional[str] = None,
) -> Dict[str, object]:
    _sync_benchmark_patches()
    return _bench.benchmark_models(
        task_id=task_id,
        agent_level=agent_level,
        models=models,
        module_name=module_name,
    )


def benchmark_matrix(
    task_id: str,
    module_name: Optional[str] = None,
    agent_levels: Optional[List[str]] = None,
    models: Optional[List[str]] = None,
    user_instruction_variants: Optional[Dict[str, str]] = None,
    repeats: int = 1,
    task_definition: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    _sync_benchmark_patches()
    return _bench.benchmark_matrix(
        task_id=task_id,
        module_name=module_name,
        agent_levels=agent_levels,
        models=models,
        user_instruction_variants=user_instruction_variants,
        repeats=repeats,
        task_definition=task_definition,
    )


def tuning_parameter_scan(
    task_id: str,
    module_name: Optional[str] = None,
    clarity_penalty_weights: Optional[List[float]] = None,
    constraint_penalty_weights: Optional[List[float]] = None,
    reward_multipliers: Optional[List[float]] = None,
    models: Optional[List[str]] = None,
) -> Dict[str, object]:
    _sync_benchmark_patches()
    return _bench.tuning_parameter_scan(
        task_id=task_id,
        module_name=module_name,
        clarity_penalty_weights=clarity_penalty_weights,
        constraint_penalty_weights=constraint_penalty_weights,
        reward_multipliers=reward_multipliers,
        models=models,
    )


def run_junior_vs_senior_comparison(task_id: str, module_name: Optional[str] = None) -> Dict[str, object]:
    _sync_benchmark_patches()
    return _bench.run_junior_vs_senior_comparison(task_id=task_id, module_name=module_name)


def debug_compare_agents(task_id: str, module_name: Optional[str] = None) -> Dict[str, object]:
    _sync_benchmark_patches()
    return _bench.debug_compare_agents(task_id=task_id, module_name=module_name)


__all__ = [
    "RUN_RUNTIME_STATE",
    "create_run",
    "persist_asset",
    "persist_workflow_steps",
    "update_run_status",
    "ModuleFacade",
    "resolve_module_name",
    "init_runtime_run",
    "mark_runtime_failed",
    "run_task",
    "get_runtime_run",
    "benchmark_models",
    "benchmark_matrix",
    "tuning_parameter_scan",
    "run_junior_vs_senior_comparison",
    "debug_compare_agents",
    "_normalize_semantic_text",
    "_semantic_patterns_for_constraint",
    "_contains_semantic_match",
    "_missing_reason_from_constraint",
    "_assess_constraints",
    "_merge_agent_profiles",
    "_build_comparison_fields",
    "_constraint_adherence_score",
    "_estimate_agent_task_fit",
    "_build_player_feedback",
    "_build_semantic_analysis",
    "_output_preview",
    "_task_cache_key",
    "_build_player_friendly_row",
    "_build_benchmark_advice",
]


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "tsk_assess_a_city_launch_for_d9bbd92d"
    module = sys.argv[2] if len(sys.argv) > 2 else None
    mode = sys.argv[3] if len(sys.argv) > 3 else "single"
    if mode == "compare":
        output = run_junior_vs_senior_comparison(task, module)
    else:
        output = run_task(task, module)
    print(json.dumps(output, indent=2))

