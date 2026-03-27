import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def test_run_data():
    """Load test run data from JSON file."""
    data_dir = ROOT / "tests" / "data" / "runs"
    data_file = data_dir / "c07eee2f19d0422b8f14e0da369fc184.json"
    
    if not data_file.exists():
        # Create default test data
        test_data = {
            "run_id": "test_run_001",
            "created_at": "2026-03-27T10:00:00+00:00",
            "result": {
                "task_name": "launch_coffee_subscription",
                "module_name": "business_sim",
                "workflow_results": [
                    {
                        "agent_name": "market_analyst",
                        "prompt": "Test prompt 1",
                        "output": "MOCK_LLM_RESPONSE: market_analyst"
                    },
                    {
                        "agent_name": "strategy_writer",
                        "prompt": "Test prompt 2",
                        "output": "MOCK_LLM_RESPONSE: strategy_writer"
                    }
                ],
                "evaluation": {
                    "final_score": 100.0,
                    "metrics": {
                        "completed_steps": 2,
                        "non_empty_outputs": 2
                    }
                },
                "asset": {
                    "asset_type": "business_plan",
                    "payload": {
                        "summary": "MOCK_LLM_RESPONSE: strategy_writer",
                        "score": 100.0,
                        "steps": ["market_analyst", "strategy_writer"]
                    }
                }
            }
        }
        return test_data
    
    with open(data_file, 'r') as f:
        return json.load(f)
