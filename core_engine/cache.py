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

MAX_CACHE_TTL_SECONDS = 3 * 24 * 60 * 60  # 3 days hard cap


def _normalize_ttl(ttl_seconds: int, default_seconds: int) -> int:
    try:
        value = int(ttl_seconds)
    except Exception:
        value = int(default_seconds)
    if value <= 0:
        value = int(default_seconds)
    return min(value, MAX_CACHE_TTL_SECONDS)


class InMemoryCache:
    def __init__(
            self,
            agent_cache_ttl_seconds: int = 3600,
            evaluation_cache_ttl_seconds: int = 3600,
            temp_result_ttl_seconds: int = 60,
    ) -> None:
        self._lock = threading.Lock()
        self._agent_cache: Dict[str, Dict[str, object]] = {}
        self._evaluation_cache: Dict[str, Dict[str, object]] = {}
        self._temp_results: Dict[str, Dict[str, object]] = {}
        self._task_results: Dict[str, Dict[str, object]] = {}
        self._agent_cache_ttl_seconds = _normalize_ttl(agent_cache_ttl_seconds, 3600)
        self._evaluation_cache_ttl_seconds = _normalize_ttl(evaluation_cache_ttl_seconds, 3600)
        self._temp_result_ttl_seconds = _normalize_ttl(temp_result_ttl_seconds, 60)

    @staticmethod
    def _hash(payload: Dict[str, object]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def agent_key(
            self,
            provider: str,
            model: str,
            prompt: str,
            behavior_signature: str = "",
            agent_name: str = "",
    ) -> str:
        return self._hash(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "behavior_signature": behavior_signature,
                "agent_name": agent_name,
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
            wrapper = self._agent_cache.get(key)
            if wrapper is None:
                return None
            if float(wrapper.get("expires_at", 0)) < time.time():
                self._agent_cache.pop(key, None)
                return None
            return wrapper.get("value")  # type: ignore[return-value]

    def set_agent(self, key: str, value: Dict[str, object]) -> None:
        expires_at = time.time() + self._agent_cache_ttl_seconds
        with self._lock:
            self._agent_cache[key] = {"value": value, "expires_at": expires_at}

    def get_evaluation(self, key: str) -> Optional[Dict[str, object]]:
        with self._lock:
            wrapper = self._evaluation_cache.get(key)
            if wrapper is None:
                return None
            if float(wrapper.get("expires_at", 0)) < time.time():
                self._evaluation_cache.pop(key, None)
                return None
            return wrapper.get("value")  # type: ignore[return-value]

    def set_evaluation(self, key: str, value: Dict[str, object]) -> None:
        expires_at = time.time() + self._evaluation_cache_ttl_seconds
        with self._lock:
            self._evaluation_cache[key] = {"value": value, "expires_at": expires_at}

    def set_task_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 600) -> None:
        expires_at = time.time() + _normalize_ttl(ttl_seconds, 600)
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
        chosen_ttl = _normalize_ttl(ttl_seconds, self._temp_result_ttl_seconds)
        expires_at = time.time() + chosen_ttl
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
    def __init__(
            self,
            redis_url: str = "redis://localhost:6379/0",
            agent_cache_ttl_seconds: int = 3600,
            evaluation_cache_ttl_seconds: int = 3600,
            temp_result_ttl_seconds: int = 60,
    ) -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.redis_client.ping()
        self.agent_cache_ttl_seconds = _normalize_ttl(agent_cache_ttl_seconds, 3600)
        self.evaluation_cache_ttl_seconds = _normalize_ttl(evaluation_cache_ttl_seconds, 3600)
        self.temp_result_ttl_seconds = _normalize_ttl(temp_result_ttl_seconds, 60)

    @staticmethod
    def _hash(payload: Dict[str, object]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def agent_key(
            self,
            provider: str,
            model: str,
            prompt: str,
            behavior_signature: str = "",
            agent_name: str = "",
    ) -> str:
        return f"agent:cache:{self._hash({'provider': provider, 'model': model, 'prompt': prompt, 'behavior_signature': behavior_signature, 'agent_name': agent_name})}"

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
        self.redis_client.setex(key, self.agent_cache_ttl_seconds, json.dumps(value))

    def get_evaluation(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(key)
        return json.loads(value) if value else None

    def set_evaluation(self, key: str, value: Dict[str, object]) -> None:
        self.redis_client.setex(key, self.evaluation_cache_ttl_seconds, json.dumps(value))

    def set_task_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 600) -> None:
        self.redis_client.setex(
            f"task:result:{key}",
            _normalize_ttl(ttl_seconds, 600),
            json.dumps(value),
        )

    def get_task_result(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(f"task:result:{key}")
        return json.loads(value) if value else None

    def set_temp_result(self, key: str, value: Dict[str, object], ttl_seconds: int = 60) -> None:
        self.redis_client.setex(
            f"temp:result:{key}",
            _normalize_ttl(ttl_seconds, self.temp_result_ttl_seconds),
            json.dumps(value),
        )

    def get_temp_result(self, key: str) -> Optional[Dict[str, object]]:
        value = self.redis_client.get(f"temp:result:{key}")
        return json.loads(value) if value else None


GLOBAL_CACHE = None


def init_cache(
        redis_url: str = "redis://localhost:6379/0",
        agent_cache_ttl_seconds: int = 3600,
        evaluation_cache_ttl_seconds: int = 3600,
        temp_result_ttl_seconds: int = 60,
):
    """Initialize global cache, preferring Redis with in-memory fallback."""
    global GLOBAL_CACHE
    if redis is not None:
        try:
            GLOBAL_CACHE = RedisCache(
                redis_url=redis_url,
                agent_cache_ttl_seconds=agent_cache_ttl_seconds,
                evaluation_cache_ttl_seconds=evaluation_cache_ttl_seconds,
                temp_result_ttl_seconds=temp_result_ttl_seconds,
            )
            return GLOBAL_CACHE
        except Exception:
            pass
    GLOBAL_CACHE = InMemoryCache(
        agent_cache_ttl_seconds=agent_cache_ttl_seconds,
        evaluation_cache_ttl_seconds=evaluation_cache_ttl_seconds,
        temp_result_ttl_seconds=temp_result_ttl_seconds,
    )
    return GLOBAL_CACHE


def get_cache():
    global GLOBAL_CACHE
    if GLOBAL_CACHE is None:
        GLOBAL_CACHE = InMemoryCache()
    return GLOBAL_CACHE
