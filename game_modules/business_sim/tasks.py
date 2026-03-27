"""Task definitions for business_sim."""

TASKS = {
    "tutorial_define_goal": {
        "input": "Draft a very short launch brief for a neighborhood coffee subscription pilot.",
        "workflow": ["market_analyst"],
        "max_total_tokens": 120,
        "is_tutorial": True,
        "tutorial_order": 1,
        "reward": 14.0,
        "difficulty": "easy",
        "cost_estimate": 3.5,
        "constraints": ["target customer", "budget", "timeline"],
    },
    "tutorial_add_constraints": {
        "input": "Write execution constraints for the pilot and a simple go/no-go rule.",
        "workflow": ["market_analyst", "strategy_writer"],
        "max_total_tokens": 180,
        "is_tutorial": True,
        "tutorial_order": 2,
        "reward": 18.0,
        "difficulty": "easy",
        "cost_estimate": 4.5,
        "constraints": ["budget cap", "success metric", "risk"],
    },
    "launch_coffee_subscription": {
        "input": "Assess if we should launch a coffee subscription in one city.",
        "workflow": ["market_analyst", "strategy_writer"],
        "max_total_tokens": 320,
        "is_tutorial": False,
        "reward": 36.0,
        "difficulty": "medium",
        "cost_estimate": 8.0,
        "constraints": ["target customer", "pricing", "risk"],
    },
    "pilot_b2b_lunch_catering": {
        "input": "Assess if we should pilot a B2B lunch catering plan for local offices.",
        "workflow": ["market_analyst", "strategy_writer"],
        "max_total_tokens": 320,
        "is_tutorial": False,
        "reward": 42.0,
        "difficulty": "medium",
        "cost_estimate": 9.5,
        "constraints": ["customer segment", "unit economics", "timeline"],
    },
}


def get_task(task_name: str) -> dict:
    if task_name not in TASKS:
        raise ValueError(f"Unknown task: {task_name}")
    return TASKS[task_name]


def list_tasks() -> dict:
    return TASKS
