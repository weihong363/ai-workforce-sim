def test_run_task_end_to_end(test_run_data) -> None:
    """Test run_task end-to-end using JSON test data."""
    result = test_run_data["result"]

    assert result["task_id"] == "tsk_assess_a_city_launch_for_d9bbd92d"
    assert result["module_name"] == "business_sim"
    
    workflow_results = result["workflow_results"]
    assert len(workflow_results) == 2
    assert workflow_results[0]["agent_name"] == "operator"
    assert workflow_results[1]["agent_name"] == "maverick"
    assert workflow_results[0]["output"].startswith("MOCK_LLM_RESPONSE:")
    
    evaluation = result["evaluation"]
    assert evaluation["final_score"] == 100.0
    
    asset = result["asset"]
    assert asset["asset_type"] == "business_plan"
    assert asset["payload"]["score"] == 100.0
    assert asset["payload"]["steps"] == ["operator", "maverick"]
