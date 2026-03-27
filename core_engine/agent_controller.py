"""Agent controller for prompt building and provider-routed model calls."""

import json
import random
import threading
import time
import uuid
from typing import Dict, Optional

import structlog
from core_engine.agent_behavior import apply_behavior_to_output, compute_effective_attributes
from core_engine.cache import get_cache
from core_engine.config import Settings
from core_engine.errors import ExecutionError
from core_engine.logging_utils import log_event
from core_engine.providers import build_provider


class AgentController:
    """Routes all agent calls through one controlled interface."""

    _semaphore_pool = {}
    _pool_lock = threading.Lock()

    def __init__(
        self,
        settings: Settings,
        llm_client: Optional[object] = None,
        purpose: str = "task",
        max_concurrency: int = 2,
        retry_attempts: int = 2,
        enable_agent_cache: bool = True,
        logger: object = None,
    ) -> None:
        self.settings = settings
        self.purpose = purpose
        self.model_name = settings.get_model(purpose)
        self.fallback_model_name = settings.get_fallback_model(purpose) or self.model_name
        self.provider_name = settings.get_provider(purpose)
        self.fallback_provider_name = settings.get_fallback_provider(purpose) or self.provider_name
        self.retry_attempts = max(1, retry_attempts)
        self.enable_agent_cache = enable_agent_cache
        self.logger = logger
        self.provider = build_provider(
            provider_name=self.provider_name,
            provider_connections=settings.provider_connections,
            llm_client=llm_client,
        )
        try:
            self.fallback_provider = build_provider(
                provider_name=self.fallback_provider_name,
                provider_connections=settings.provider_connections,
                llm_client=llm_client,
            )
        except ExecutionError:
            # Graceful fallback if optional fallback provider is not configured.
            self.fallback_provider_name = self.provider_name
            self.fallback_model_name = self.model_name
            self.fallback_provider = self.provider
        self._semaphore = self._get_semaphore(max_concurrency)

    @classmethod
    def _get_semaphore(cls, max_concurrency: int) -> threading.Semaphore:
        key = max(1, max_concurrency)
        with cls._pool_lock:
            if key not in cls._semaphore_pool:
                cls._semaphore_pool[key] = threading.Semaphore(key)
            return cls._semaphore_pool[key]

    def build_prompt(self, agent_name: str, task_input: str, previous_output: str) -> str:
        return (
            f"Agent: {agent_name}\n"
            f"Task Input: {task_input}\n"
            f"Previous Output: {previous_output or 'None'}\n"
            "Produce a short business-focused response."
        )

    @staticmethod
    def _result_delay_range_seconds(profile: Dict[str, object]) -> tuple[float, float]:
        level = str(profile.get("level", "")).lower()
        if level == "junior":
            return (0.08, 0.22)
        if level == "senior":
            return (0.02, 0.08)
        return (0.04, 0.12)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(str(text).split()))

    @staticmethod
    def _truncate_to_token_limit(text: str, max_tokens: int) -> str:
        words = str(text).split()
        if len(words) <= max_tokens:
            return str(text)
        return " ".join(words[:max_tokens]) + " ...[TRUNCATED]"

    def _call_provider_with_retry(self, prompt: str, model_name: str) -> Dict[str, object]:
        return self._call_single_provider_with_retry(
            provider=self.provider,
            model_name=model_name,
            prompt=prompt,
            retry_attempts=self.retry_attempts,
        )

    def _call_single_provider_with_retry(
        self,
        provider: object,
        model_name: str,
        prompt: str,
        retry_attempts: int,
    ) -> Dict[str, object]:
        last_exception = None
        for attempt in range(1, retry_attempts + 1):
            try:
                with self._semaphore:
                    response = provider.complete(prompt, model_name)
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "provider_call",
                        provider=response.get("provider"),
                        model=response.get("model"),
                        attempt=attempt,
                        token_usage=response.get("token_usage", {}),
                    )
                return response
            except Exception as exc:  # pragma: no cover - narrow behavior tested via retry
                last_exception = exc
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "provider_call_failed",
                        provider=getattr(provider, "provider_name", "unknown"),
                        model=model_name,
                        attempt=attempt,
                        error=str(exc),
                    )
                if attempt < retry_attempts:
                    time.sleep(0.02)

        raise ExecutionError(
            "provider_call_failed",
            "Provider call failed after retries.",
            {
                "provider": getattr(provider, "provider_name", "unknown"),
                "model": model_name,
                "attempts": retry_attempts,
                "last_error": str(last_exception) if last_exception else "unknown",
            },
        )

    def run_agent(
        self,
        agent_name: str,
        task_input: str,
        previous_output: str = "",
        agent_profile: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        profile = agent_profile or {}
        effective = compute_effective_attributes(profile)
        affinity_before = effective["affinity"]
        prompt = self.build_prompt(agent_name, task_input, previous_output)
        provider_name = getattr(self.provider, "provider_name", "unknown")
        model_name = self.settings.get_model_for_role(self.purpose, str(profile.get("level", "mid")))
        cache = get_cache()
        behavior_signature = json.dumps(effective, sort_keys=True)

        cache_key = cache.agent_key(
            provider=provider_name,
            model=model_name,
            prompt=prompt,
            behavior_signature=behavior_signature,
        )
        if self.enable_agent_cache:
            cached = cache.get_agent(cache_key)
            if cached is not None:
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "agent_cache_hit",
                        agent_name=agent_name,
                        provider=provider_name,
                        model=model_name,
                    )
                return {
                    "agent_name": agent_name,
                    "prompt": prompt,
                    "output": apply_behavior_to_output(str(cached["output"]), effective),
                    "provider": cached["provider"],
                    "model": cached["model"],
                    "token_usage": cached["token_usage"],
                    "effective_attributes": effective,
                    "affinity_before": affinity_before,
                    "cache_hit": True,
                }
            if self.logger is not None:
                log_event(
                    self.logger,
                    "agent_cache_miss",
                    agent_name=agent_name,
                    provider=provider_name,
                    model=model_name,
                )

        try:
            response = self._call_provider_with_retry(prompt, model_name=model_name)
        except ExecutionError as primary_error:
            if self.fallback_provider_name != self.provider_name or self.fallback_model_name != self.model_name:
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "provider_fallback",
                        purpose=self.purpose,
                        from_provider=self.provider_name,
                        from_model=model_name,
                        to_provider=self.fallback_provider_name,
                        to_model=self.fallback_model_name,
                    )
                response = self._call_single_provider_with_retry(
                    provider=self.fallback_provider,
                    model_name=self.fallback_model_name,
                    prompt=prompt,
                    retry_attempts=self.retry_attempts,
                )
                provider_name = str(response.get("provider", self.fallback_provider_name))
                model_name = str(response.get("model", self.fallback_model_name))
            else:
                raise primary_error
        record = {
            "output": response.get("output", ""),
            "provider": response.get("provider", provider_name),
            "model": response.get("model", model_name),
            "token_usage": response.get("token_usage", {}),
        }

        # Enforce per-agent output token limit.
        max_output_tokens = int(profile.get("max_output_tokens", 0) or 0)
        budget_action = None
        if max_output_tokens > 0:
            current_tokens = self._estimate_tokens(record["output"])
            if current_tokens > max_output_tokens:
                record["output"] = self._truncate_to_token_limit(record["output"], max_output_tokens)
                record["token_usage"]["completion_tokens"] = self._estimate_tokens(record["output"])
                record["token_usage"]["total_tokens"] = int(record["token_usage"].get("prompt_tokens", 0)) + int(
                    record["token_usage"]["completion_tokens"]
                )
                budget_action = "truncated_output"

        # Store result temporarily in cache, then return after a randomized delay.
        # Junior agents use a wider/slower delay band than senior agents.
        temp_key = uuid.uuid4().hex
        cache.set_temp_result(temp_key, record, ttl_seconds=60)
        delay_min, delay_max = self._result_delay_range_seconds(profile)
        wait_seconds = random.uniform(delay_min, delay_max)
        artificial_delay_ms = int(profile.get("artificial_delay_ms", 0) or 0)
        total_wait_seconds = wait_seconds + (artificial_delay_ms / 1000.0)
        time.sleep(total_wait_seconds)
        delayed_record = cache.get_temp_result(temp_key) or record

        step_tokens = int(delayed_record.get("token_usage", {}).get("total_tokens", 0))
        cost_weight = float(profile.get("cost_weight", 1.0) or 1.0)
        step_cost = round((step_tokens / 1000.0) * self.settings.llm_cost_per_1k_tokens_usd * cost_weight, 8)

        if self.enable_agent_cache:
            active_cache_key = cache.agent_key(
                provider=delayed_record["provider"],
                model=delayed_record["model"],
                prompt=prompt,
                behavior_signature=behavior_signature,
            )
            cache.set_agent(active_cache_key, delayed_record)

        return {
            "agent_name": agent_name,
            "prompt": prompt,
            "output": apply_behavior_to_output(str(delayed_record["output"]), effective),
            "provider": delayed_record["provider"],
            "model": delayed_record["model"],
            "token_usage": delayed_record["token_usage"],
            "effective_attributes": effective,
            "affinity_before": affinity_before,
            "result_delay_seconds": round(total_wait_seconds, 4),
            "budget_action": budget_action,
            "cost": step_cost,
            "cache_hit": False,
        }
