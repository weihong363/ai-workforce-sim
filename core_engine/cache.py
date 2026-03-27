"""Cache layer for agent outputs and evaluation results.

Uses Redis when available, with automatic in-memory fallback.
"""

import hashlib
import json
import threading
import time
from typing import Dict, Optional

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None


class InMemoryCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agent_cache: Dict[str, Dict[str, object]] = {}
        self._evaluation_cache: Dict[str, Dict[str, object]] = {}
        self._temp_results: Dict[str, Dict[str, object]] = {}
        self._task_results: Dict[str, Dict[str, object]] = {}

    @staticmethod
    def _hash(payload: Dict[str, object]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def agent_key(self, provider: str, model: str, prompt: str, behavior_signature: str = "") -> str:
        return self._hash(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "behavior_signature": behavior_signature,
            }
        )

    def evaluation_key(self, module_name: str, workflow_results: list) -> str:
        stable_steps = [
            {
                "agent_name": step.get("agent_name"),
                "output": step.get("output"),
                "provider": step.get("provider"),
                "model": step.get("model"),
            }
            for step in workflow_results
        ]
        return self._hash({"module_name": module_name, "workflow_results": stable_steps})

    def get_agent(self, key: str) -> Optional[Dict[str, object]]:
        with self._lock:
            return self._agent_cache.get(key)

    def set_agent(self, key: str, value: Dict[str, object]) -> None:
        with self._lock:
            self._agent_cache[key] = value

    def get_evaluation(self, key: str) -> Optional[Dict[str, object]]:
        with self._lock:
            return self._evaluation_cache.get(key)

    def set_evaluation(self, key: str, value: Dict[str, object]) -> None:
        with self._lock:
            self._evaluation_cache[key] = value

    def set_task_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 600) -> None:
        expires_at = time.time() + max(1, ttl_seconds)
        with self._lock:
            self._task_results[key] = {"value": value, "expires_at": expires_at}

    def get_task_result(self, key: str) -> Optional[Dict[str, object]]:
        with self._lock:
            wrapper = self._task_results.get(key)
            if wrapper is None:
                return None
            if float(wrapper.get("expires_at", 0)) < time.time():
                self._task_results.pop(key, None)
                return None
            return wrapper.get("value")  # type: ignore[return-value]

    def set_temp_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 60) -> None:
        expires_at = time.time() + max(1, ttl_seconds)
        with self._lock:
            self._temp_results[key] = {"value": value, "expires_at": expires_at}

    def get_temp_result(self, key: str) -> Optional[Dict[str, object]]:
        with self._lock:
            wrapper = self._temp_results.get(key)
            if wrapper is None:
                return None
            if float(wrapper.get("expires_at", 0)) < time.time():
                self._temp_results.pop(key, None)
                return None
            return wrapper.get("value")  # type: ignore[return-value]


class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.redis_client.ping()

    @staticmethod
    def _hash(payload: Dict[str, object]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def agent_key(self, provider: str, model: str, prompt: str, behavior_signature: str = "") -> str:
        return f"agent:cache:{self._hash({'provider': provider, 'model': model, 'prompt': prompt, 'behavior_signature': behavior_signature})}"

    def evaluation_key(self, module_name: str, workflow_results: list) -> str:
        stable_steps = [
            {
                "agent_name": step.get("agent_name"),
                "output": step.get("output"),
                "provider": step.get("provider"),
                "model": step.get("model"),
            }
            for step in workflow_results
        ]
        return f"evaluation:cache:{self._hash({'module_name': module_name, 'workflow_results': stable_steps})}"

    def get_agent(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(key)
        return json.loads(value) if value else None

    def set_agent(self, key: str, value: Dict[str, object]) -> None:
        self.redis_client.set(key, json.dumps(value))

    def get_evaluation(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(key)
        return json.loads(value) if value else None

    def set_evaluation(self, key: str, value: Dict[str, object]) -> None:
        self.redis_client.set(key, json.dumps(value))

    def set_task_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 600) -> None:
        self.redis_client.setex(f"task:result:{key}", max(1, ttl_seconds), json.dumps(value))

    def get_task_result(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(f"task:result:{key}")
        return json.loads(value) if value else None

    def set_temp_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 60) -> None:
        self.redis_client.setex(f"temp:result:{key}", max(1, ttl_seconds), json.dumps(value))

    def get_temp_result(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(f"temp:result:{key}")
        return json.loads(value) if value else None


GLOBAL_CACHE = None


def init_cache(redis_url: str = "redis://localhost:6379/0"):
    """Initialize global cache, preferring Redis with in-memory fallback."""
    global GLOBAL_CACHE
    if redis is not None:
        try:
            GLOBAL_CACHE = RedisCache(redis_url)
            return GLOBAL_CACHE
        except Exception:
            pass
    GLOBAL_CACHE = InMemoryCache()
    return GLOBAL_CACHE


def get_cache():
    global GLOBAL_CACHE
    if GLOBAL_CACHE is None:
        GLOBAL_CACHE = InMemoryCache()
    return GLOBAL_CACHE
