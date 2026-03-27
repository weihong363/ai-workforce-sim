"""Task definitions for business_sim."""

TASKS = {
    "launch_coffee_subscription": {
        "input": "Assess if we should launch a coffee subscription in one city.",
        "workflow": ["market_analyst", "strategy_writer"],
    },
    "pilot_b2b_lunch_catering": {
        "input": "Assess if we should pilot a B2B lunch catering plan for local offices.",
        "workflow": ["market_analyst", "strategy_writer"],
    },
}


def get_task(task_name: str) -> dict:
    if task_name not in TASKS:
        raise ValueError(f"Unknown task: {task_name}")
    return TASKS[task_name]
