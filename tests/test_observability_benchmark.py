import time

from fastapi.testclient import TestClient

import api.app as app_module
import api.routes.debug as debug_routes
import api.run_task as run_task_module
from core_engine.agent_controller import AgentController
from core_engine.config import get_settings


def _patch_persistence(monkeypatch) -> None:
    monkeypatch.setattr(run_task_module, "create_run", lambda *args, **kwargs: "run_obs_test_001")
    monkeypatch.setattr(run_task_module, "update_run_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_workflow_steps", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_task_module, "persist_asset", lambda *args, **kwargs: "asset_obs_test_001")
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("PROVIDER_FOR_EVALUATION", "mock")
    monkeypatch.setenv("MODEL_FOR_TASK", "mvp-default")
    monkeypatch.setenv("MODEL_FOR_EVALUATION", "mvp-default")
    monkeypatch.setenv("MODEL_TASK_JUNIOR", "mvp-default")
    monkeypatch.setenv("MODEL_TASK_MID", "mvp-default")
    monkeypatch.setenv("MODEL_TASK_SENIOR", "mvp-default")
    monkeypatch.setenv("MODEL_EVALUATOR", "mvp-default")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setenv("ENABLE_EVALUATION_CACHE", "false")
    get_settings.cache_clear()
    import game_modules.business_sim.tasks as task_module

    seed_tasks = task_module.get_seed_tasks()
    monkeypatch.setattr(task_module, "list_tasks", lambda: seed_tasks)

    def _get_task(name: str):
        if name not in seed_tasks:
            raise ValueError(f"Unknown task: {name}")
        return seed_tasks[name]

    monkeypatch.setattr(task_module, "get_task", _get_task)


def test_benchmark_matrix_output_structure(monkeypatch) -> None:
    class _Agents:
        AGENTS = {"planner": {}, "writer": {}}

    class _Facade:
        agents = _Agents()

    monkeypatch.setattr(run_task_module.ModuleFacade, "from_name", lambda *_a, **_k: _Facade())
    monkeypatch.setattr(
        run_task_module,
        "run_task",
        lambda *args, **kwargs: {
            "storage": {"run_id": "run_fake"},
            "comparison_fields": {
                "output_length": 120,
                "missed_constraints": 1,
                "deviation_detected": False,
                "final_score": 87.5,
                "token_usage": {"prompt_tokens": 100, "completion_tokens": 221, "total_tokens": 321},
                "cost": 0.1234,
            },
            "workflow_results": [{"output": "sample output"}],
            "constraint_assessment": {"failed_rules": ["risk"]},
            "task_constraints": ["pricing", "risk"],
            "observability": {"clarity_score": 0.8},
            "score_breakdown": {"base_score": 82.0, "final_score": 70.0},
            "penalties": {"constraint_penalty": 12},
            "effective_parameters": {"constraint_penalty_weight": 16.0},
        },
    )

    payload = run_task_module.benchmark_matrix(
        task_id="tsk_assess_a_city_launch_for_d9bbd92d",
        module_name="business_sim",
        agent_levels=["junior"],
        models=["bench-model-x"],
        user_instruction_variants={"vague": "do it", "clear": "A B C constraints"},
        repeats=2,
    )

    assert payload["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"
    assert len(payload["runs"]) == 4
    run_item = payload["runs"][0]
    assert set(run_item.keys()) == {
        "agent_level",
        "model",
        "instruction_variant",
        "repeat_index",
        "run_id",
        "prompt_length",
        "raw_output",
        "raw_output_preview",
        "full_output_length",
        "truncated_for_display",
        "stored_full_output",
        "constraint_hits",
        "constraint_misses",
        "clarity_score",
        "score_breakdown",
        "penalties",
        "effective_parameters",
        "metrics",
    }
    assert run_item["raw_output"] == "sample output"
    assert run_item["raw_output_preview"] == "sample output"
    assert run_item["full_output_length"] == len("sample output")
    assert run_item["stored_full_output"] is True
    assert run_item["constraint_hits"] == ["pricing"]
    assert run_item["constraint_misses"] == ["risk"]
    assert run_item["score_breakdown"]["final_score"] == 70.0
    assert run_item["penalties"]["constraint_penalty"] == 12
    assert run_item["effective_parameters"]["constraint_penalty_weight"] == 16.0
    assert set(run_item["metrics"].keys()) == {
        "output_length",
        "missed_constraints",
        "deviation_detected",
        "final_score",
        "token_usage",
        "cost",
        "latency_ms",
    }
    agg = payload["aggregates"][0]["metrics"]
    for field in ("output_length", "missed_constraints", "final_score", "token_usage", "cost", "latency_ms"):
        assert set(agg[field].keys()) == {"avg", "min", "max"}


def test_observability_fields_exist_in_run_result(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    result = run_task_module.run_task("tsk_assess_a_city_launch_for_d9bbd92d")

    obs = result["observability"]
    assert obs["run_id"] == "run_obs_test_001"
    assert obs["status"] == "success"
    assert isinstance(obs["total_tokens"], int)
    assert isinstance(obs["total_latency_ms"], int)
    assert "clarity_score" in obs
    assert "deviation_detected" in obs
    assert "constraint_adherence_score" in obs
    assert "score_breakdown" in result
    assert "penalties" in result
    assert "effective_parameters" in result

    first_step = result["workflow_results"][0]
    assert "agent_level" in first_step
    assert "latency_ms" in first_step
    assert "cache_hit" in first_step
    assert isinstance(first_step.get("effective_attributes", {}), dict)


def test_parameter_change_affects_behavior(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    monkeypatch.setenv("PROVIDER_FOR_TASK", "mock")
    monkeypatch.setenv("MODEL_FOR_TASK", "mvp-default")
    monkeypatch.setenv("ENABLE_AGENT_CACHE", "false")
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    monkeypatch.setattr("core_engine.agent_controller.random.uniform", lambda _a, _b: 0.0)

    monkeypatch.setenv("OBEDIENCE_WEIGHT", "1.0")
    get_settings.cache_clear()
    ctrl_default = AgentController(settings=get_settings(), purpose="task", enable_agent_cache=False)
    out_default = ctrl_default.run_agent(
        "planner",
        "task",
        agent_profile={"level": "mid", "obedience": 0.6, "initiative": 0.8, "effort": 1.0, "affinity": 0.5},
    )

    monkeypatch.setenv("OBEDIENCE_WEIGHT", "0.1")
    get_settings.cache_clear()
    ctrl_low_ob = AgentController(settings=get_settings(), purpose="task", enable_agent_cache=False)
    out_low_ob = ctrl_low_ob.run_agent(
        "planner",
        "task",
        agent_profile={"level": "mid", "obedience": 0.6, "initiative": 0.8, "effort": 1.0, "affinity": 0.5},
    )

    assert not str(out_default["output"]).startswith("DEVIATED_FROM_INSTRUCTIONS:")
    assert str(out_low_ob["output"]).startswith("DEVIATED_FROM_INSTRUCTIONS:")


def test_debug_run_endpoint_structure(monkeypatch) -> None:
    monkeypatch.setattr(
        debug_routes,
        "get_run",
        lambda *_a, **_k: {
            "run_id": "run_001",
            "user_id": "usr_001",
            "task_id": "tsk_assess_a_city_launch_for_d9bbd92d",
            "status": "completed",
            "total_cost": 0.15,
            "total_tokens": 300,
            "total_latency_ms": 120,
            "final_score": 85.0,
            "clarity_score": 0.8,
            "deviation_detected": False,
            "constraint_adherence_score": 1.0,
            "workflow_steps": [
                {
                    "agent_name": "planner",
                    "provider": "mock",
                    "model": "mvp-default",
                    "cost": 0.15,
                    "latency_ms": 120,
                    "token_usage": {"total_tokens": 300},
                    "effective_attributes": {"obedience": 0.6, "initiative": 0.7, "effort": 0.8, "affinity": 0.5},
                }
            ],
        },
    )

    with TestClient(app_module.app) as client:
        resp = client.get("/debug/run/run_001")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"run_summary", "steps", "agent_effects", "cost_breakdown", "behavior_analysis"}
    assert data["run_summary"]["run_id"] == "run_001"
    assert "planner" in data["agent_effects"]
    assert "by_model" in data["cost_breakdown"]
    assert "raw_output_preview" in data["steps"][0]
    assert "full_output_length" in data["steps"][0]
    assert "stored_full_output" in data["steps"][0]


def test_benchmark_matrix_endpoint_structure(monkeypatch) -> None:
    monkeypatch.setattr(
        run_task_module,
        "benchmark_matrix",
        lambda **kwargs: {"task_id": kwargs["task_id"], "runs": [], "aggregates": []},
    )
    with TestClient(app_module.app) as client:
        resp = client.post(
            "/debug/benchmark",
            json={
                "task_id": "tsk_assess_a_city_launch_for_d9bbd92d",
                "agent_levels": ["junior", "mid"],
                "models": ["mvp-default"],
                "user_instruction_variants": {"vague": "x", "clear": "y"},
                "repeats": 2,
            },
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"
    assert "runs" in payload
    assert "aggregates" in payload


def test_tuning_scan_endpoint_structure(monkeypatch) -> None:
    monkeypatch.setattr(
        debug_routes,
        "tuning_parameter_scan",
        lambda **kwargs: {
            "task_id": kwargs["task_id"],
            "top_configs": [{"rank_score": 1.2}],
            "results_ranked": [{"rank_score": 1.2}],
        },
    )
    with TestClient(app_module.app) as client:
        resp = client.post(
            "/debug/tuning-scan",
            json={
                "task_id": "tsk_assess_a_city_launch_for_d9bbd92d",
                "clarity_penalty_weights": [30, 40],
                "constraint_penalty_weights": [14, 20],
                "reward_multipliers": [0.9, 1.1],
            },
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"
    assert "top_configs" in payload
    assert "results_ranked" in payload


def test_debug_tuning_get_and_patch(monkeypatch) -> None:
    monkeypatch.setenv("OBEDIENCE_WEIGHT", "1.0")
    monkeypatch.setenv("INITIATIVE_WEIGHT", "1.0")
    monkeypatch.setenv("EFFORT_WEIGHT", "1.0")
    monkeypatch.setenv("TASK_TOKEN_BUDGET_MULTIPLIER", "1.0")
    monkeypatch.setenv("AGENT_TOKEN_BUDGET_MULTIPLIER", "1.0")
    get_settings.cache_clear()

    with TestClient(app_module.app) as client:
        get_resp = client.get("/debug/tuning")
        assert get_resp.status_code == 200
        assert "effective_parameters" in get_resp.json()

        patch_resp = client.patch(
            "/debug/tuning",
            json={
                "constraint_penalty_weight": 22.0,
                "clarity_penalty_weight": 40.0,
                "reward_multiplier": 1.4,
                "agent_trait_weights": {"obedience": 0.9},
                "token_budget": {"agent_multiplier": 1.2},
            },
        )
        assert patch_resp.status_code == 200
        effective = patch_resp.json()["effective_parameters"]
        assert effective["constraint_penalty_weight"] == 22.0
        assert effective["clarity_penalty_weight"] == 40.0
        assert effective["reward_multiplier"] == 1.4
        assert effective["agent_trait_weights"]["obedience"] == 0.9
        assert effective["token_budget"]["agent_multiplier"] == 1.2


def test_clear_vs_vague_produces_measurable_difference(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    monkeypatch.setattr("core_engine.agent_controller.random.uniform", lambda _a, _b: 0.0)

    vague = run_task_module.run_task(
        "tsk_assess_a_city_launch_for_d9bbd92d",
        instructions="make it better",
    )
    clear = run_task_module.run_task(
        "tsk_assess_a_city_launch_for_d9bbd92d",
        instructions="Target customer: white collar. Budget: 50000. Timeline: 3 months. Must include pricing and risk.",
    )

    vague_missed = int(vague["comparison_fields"]["missed_constraints"])
    clear_missed = int(clear["comparison_fields"]["missed_constraints"])
    vague_clarity = float(vague["observability"]["clarity_score"])
    clear_clarity = float(clear["observability"]["clarity_score"])

    assert clear_clarity > vague_clarity
    assert clear_missed <= vague_missed


def test_junior_vs_senior_output_is_visibly_different(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    monkeypatch.setattr("core_engine.agent_controller.random.uniform", lambda _a, _b: 0.0)

    junior = run_task_module.run_task(
        "tsk_assess_a_city_launch_for_d9bbd92d",
        agent_overrides={
            "market_analyst": {"level": "junior", "obedience": 0.7, "initiative": 0.35, "effort": 0.5},
            "strategy_writer": {"level": "junior", "obedience": 0.7, "initiative": 0.35, "effort": 0.5},
        },
        instructions="Target customer and pricing required.",
    )
    senior = run_task_module.run_task(
        "tsk_assess_a_city_launch_for_d9bbd92d",
        agent_overrides={
            "market_analyst": {"level": "senior", "obedience": 0.5, "initiative": 0.8, "effort": 0.85},
            "strategy_writer": {"level": "senior", "obedience": 0.5, "initiative": 0.8, "effort": 0.85},
        },
        instructions="Target customer and pricing required.",
    )

    junior_out = str(junior["workflow_results"][-1]["output"])
    senior_out = str(senior["workflow_results"][-1]["output"])
    assert "Quick take:" in junior_out
    assert "Summary:" in senior_out
    assert "Plan:" in senior_out


def test_missed_constraints_reduce_final_score(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    result = run_task_module.run_task("tsk_assess_a_city_launch_for_d9bbd92d", instructions="just do it")
    missed = int(result["comparison_fields"]["missed_constraints"])
    score = float(result["evaluation"]["final_score"])
    if missed > 0:
        assert score < 100.0


def test_semantic_constraint_match_supports_equivalents() -> None:
    text = "目标客户是白领，上线计划为3-month setup，包含分阶段里程碑。"
    constraints = ["target customer", "milestone"]
    assessed = run_task_module._assess_constraints(text, constraints)
    assert int(assessed["missed_constraints"]) == 0
    assert list(assessed["failed_rules"]) == []


def test_player_feedback_contains_failure_reasons() -> None:
    feedback = run_task_module._build_player_feedback(
        final_score=52.0,
        clarity_score=0.2,
        failed_rules=["target customer", "timeline"],
    )
    assert feedback["success"] is False
    assert "instruction too vague" in feedback["failure_reasons"]
    assert "missing target customer" in feedback["failure_reasons"]
    assert "missing milestones" in feedback["failure_reasons"]


def test_semantic_constraint_match_detects_risk_variants() -> None:
    text = "Key risk factors are churn and logistics delay; risks include supply volatility."
    assessed = run_task_module._assess_constraints(text, ["risk"])
    assert int(assessed["missed_constraints"]) == 0


def test_semantic_constraint_match_detects_target_customer_variants() -> None:
    text = "We are targeting urban professionals and white-collar commuters."
    assessed = run_task_module._assess_constraints(text, ["target customer"])
    assert int(assessed["missed_constraints"]) == 0


def test_junior_clear_instruction_improves_constraint_hits(monkeypatch) -> None:
    _patch_persistence(monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    monkeypatch.setattr("core_engine.agent_controller.random.uniform", lambda _a, _b: 0.0)

    junior_overrides = {
        "market_analyst": {"level": "junior", "obedience": 0.75, "initiative": 0.35, "effort": 0.55},
        "strategy_writer": {"level": "junior", "obedience": 0.75, "initiative": 0.35, "effort": 0.55},
    }
    vague = run_task_module.run_task(
        "tsk_assess_a_city_launch_for_d9bbd92d",
        agent_overrides=junior_overrides,
        instructions="do a plan",
    )
    clear = run_task_module.run_task(
        "tsk_assess_a_city_launch_for_d9bbd92d",
        agent_overrides=junior_overrides,
        instructions="Targeting urban professionals, include pricing and risk factors.",
    )
    assert int(clear["comparison_fields"]["missed_constraints"]) <= int(vague["comparison_fields"]["missed_constraints"])
