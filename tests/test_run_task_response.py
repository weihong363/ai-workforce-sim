from api.services.run_task_response import build_run_task_user_response, suggestions_from_issues


def test_suggestions_are_actionable_and_capped() -> None:
    issues = [
        "missing target customer",
        "missing pricing",
        "missing risk analysis",
        "missing milestones",
    ]
    suggestions = suggestions_from_issues(issues)
    assert len(suggestions) <= 3
    assert any("target customer" in item.lower() for item in suggestions)
    assert any("pricing" in item.lower() for item in suggestions)


def test_user_response_includes_failure_reasons_previous_score_and_delta() -> None:
    response = build_run_task_user_response(
        {
            "storage": {"run_id": "run_001"},
            "evaluation": {"final_score": 69.0},
            "player_result": {
                "success": False,
                "near_miss": True,
                "reward_gained": 0.0,
                "cost_spent": 8.0,
                "wallet_before": 100.0,
                "wallet_after": 92.0,
                "net_result": -8.0,
                "previous_score": 61.0,
                "score_delta": 8.0,
                "explanation": "Almost success: most constraints were met, but a few key points are still missing.",
            },
            "player_feedback": {
                "failure_reasons": ["missing pricing", "missing risk analysis"],
            },
        }
    )
    assert response["run_id"] == "run_001"
    assert response["previous_score"] == 61.0
    assert response["score_delta"] == 8.0
    assert response["message"] == "Almost there!"
    assert response["near_miss"] is True
    assert response["hint"] is not None
    assert len(response["failure_reasons"]) <= 3
    assert any("almost there" in str(x).lower() for x in response["failure_reasons"])
    assert any("pricing strategy" in str(x).lower() for x in response["failure_reasons"])


def test_success_response_includes_reinforcement() -> None:
    response = build_run_task_user_response(
        {
            "storage": {"run_id": "run_002"},
            "evaluation": {"final_score": 90.0},
            "player_result": {
                "success": True,
                "near_miss": False,
                "reward_gained": 20.0,
                "cost_spent": 5.0,
                "wallet_before": 80.0,
                "wallet_after": 95.0,
                "net_result": 15.0,
                "explanation": "Task succeeded with strong execution.",
            },
            "semantic_analysis": {
                "constraint_matches": {"matched": ["target customer", "pricing", "risk"]},
            },
            "player_feedback": {"failure_reasons": []},
        }
    )
    assert response["success"] is True
    assert response["message"] == "Good work!"
    assert len(response["what_you_did_well"]) >= 1
