"""Evaluation adapter delegates scoring to the game module."""

from typing import Dict, List

from core_engine.cache import get_cache
from core_engine.logging_utils import log_event


def evaluate_workflow(
    evaluation_module: object,
    workflow_results: List[Dict[str, str]],
    module_name: str = "unknown",
    enable_cache: bool = True,
    logger: object = None,
) -> Dict[str, object]:
    cache = get_cache()
    cache_key = cache.evaluation_key(module_name=module_name, workflow_results=workflow_results)
    if enable_cache:
        cached = cache.get_evaluation(cache_key)
        if cached is not None:
            if logger is not None:
                log_event(logger, "evaluation_cache_hit", module_name=module_name)
            return {"result": cached, "cache_hit": True}
        if logger is not None:
            log_event(logger, "evaluation_cache_miss", module_name=module_name)

    result = evaluation_module.evaluate(workflow_results)
    if enable_cache:
        cache.set_evaluation(cache_key, result)
    return {"result": result, "cache_hit": False}
