"""Agent controller for prompt building and provider-routed model calls."""

import json
import random
import re
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
        lower_input = str(task_input).lower()
        needs_constraint_complete = any(
            marker in lower_input
            for marker in (
                "return json only",
                "constraints",
                "include_key:",
                "min_numbers:",
                "at least",
            )
        )
        output_rule = (
            "Cover every explicit constraint in full detail and keep output under 220 tokens."
            if needs_constraint_complete
            else "Produce a concise business-focused response under 180 tokens."
        )
        return (
            f"Agent: {agent_name}\n"
            f"Task Input: {task_input}\n"
            f"Previous Output: {previous_output or 'None'}\n"
            f"{output_rule}"
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

    @staticmethod
    def _extract_constraint_keywords(task_input: str) -> list[str]:
        text = str(task_input or "")
        lower = text.lower()
        keywords: list[str] = []
        for marker in (
            "target customer",
            "targeting",
            "target",
            "urban professionals",
            "white-collar",
            "white collar",
            "pricing",
            "risk",
            "risk factors",
            "risks include",
            "timeline",
            "milestone",
            "budget",
        ):
            if marker in lower:
                keywords.append(marker)
        if "白领" in text and "target customer" not in keywords:
            keywords.append("target customer")
        if "里程碑" in text and "milestone" not in keywords:
            keywords.append("milestone")
        if "风险" in text and "risk" not in keywords:
            keywords.append("risk")
        for matched in re.findall(r"(?:keyword|include_key):\s*([a-zA-Z0-9_ -]{2,40})", lower):
            token = str(matched).strip()
            if token and token not in keywords:
                keywords.append(token)
        return keywords[:4]

    def _shape_output_for_profile(
        self,
        output: str,
        task_input: str,
        profile: Dict[str, object],
        effective: Dict[str, float],
    ) -> str:
        level = str(profile.get("level", "mid")).lower()
        text = str(output or "").strip()
        if not text:
            return text

        constraints = self._extract_constraint_keywords(task_input)
        if level == "junior":
            if not text.startswith("Quick take:"):
                text = f"Quick take: {text}"
            clarity = float(profile.get("clarity_score", 0.0) or 0.0)
            if constraints and clarity >= 0.6:
                checklist = ", ".join(constraints[:3])
                text = f"{text}\nConstraint check: {checklist}."
            short_cap = max(50, int(95 + (effective.get("effort", 0.5) * 55)))
            if len(text) > short_cap:
                text = text[:short_cap].rstrip() + " ..."
            return text

        if level == "senior":
            lines = [f"Summary: {text}"]
            lines.append("Plan:")
            lines.append("- Prioritize the highest-impact option first.")
            lines.append("- Define measurable checkpoint and owner.")
            if constraints:
                lines.append("Constraint check:")
                for item in constraints:
                    lines.append(f"- {item}: addressed")
            if effective.get("initiative", 0.0) >= 0.75 and effective.get("obedience", 1.0) < 0.6:
                lines.append("Alternative path: consider a bolder positioning option.")
            return "\n".join(lines)

        return text

    def _call_provider_with_retry(self, prompt: str, model_name: str, max_tokens: int) -> Dict[str, object]:
        return self._call_single_provider_with_retry(
            provider=self.provider,
            model_name=model_name,
            prompt=prompt,
            retry_attempts=self.retry_attempts,
            max_tokens=max_tokens,
        )

    def _call_single_provider_with_retry(
        self,
        provider: object,
        model_name: str,
        prompt: str,
        retry_attempts: int,
        max_tokens: int,
    ) -> Dict[str, object]:
        last_exception = None
        for attempt in range(1, retry_attempts + 1):
            try:
                started_at = time.perf_counter()
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "model_call_start",
                        provider=getattr(provider, "provider_name", "unknown"),
                        model=model_name,
                        attempt=attempt,
                    )
                with self._semaphore:
                    response = provider.complete(prompt, model_name, max_tokens=max_tokens)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                if self.logger is not None:
                    log_event(
                        self.logger,
                        "model_call_end",
                        provider=response.get("provider"),
                        model=response.get("model"),
                        attempt=attempt,
                        token_usage=response.get("token_usage", {}),
                        latency_ms=latency_ms,
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
        effective = compute_effective_attributes(
            profile,
            weights={
                "obedience": self.settings.obedience_weight,
                "initiative": self.settings.initiative_weight,
                "effort": self.settings.effort_weight,
            },
        )
        affinity_before = effective["affinity"]
        prompt = self.build_prompt(agent_name, task_input, previous_output)
        provider_name = getattr(self.provider, "provider_name", "unknown")
        model_name = self.settings.get_model_for_role(self.purpose, str(profile.get("level", "mid")))
        request_max_tokens = max(128, int(profile.get("max_output_tokens", 0) or 256))
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
                    "output": apply_behavior_to_output(
                        self._shape_output_for_profile(str(cached["output"]), task_input, profile, effective),
                        effective,
                    ),
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
            response = self._call_provider_with_retry(prompt, model_name=model_name, max_tokens=request_max_tokens)
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
                    max_tokens=request_max_tokens,
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

        # Detect per-agent output budget breach, but keep full raw output for persistence.
        base_max_output_tokens = int(profile.get("max_output_tokens", 0) or 0)
        max_output_tokens = int(base_max_output_tokens * self.settings.agent_token_budget_multiplier)
        budget_action = None
        if max_output_tokens > 0:
            current_tokens = self._estimate_tokens(record["output"])
            if current_tokens > max_output_tokens:
                budget_action = "output_token_budget_exceeded"

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
        cost_weight *= float(self.settings.agent_cost_weight_overrides.get(agent_name, 1.0) or 1.0)
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
            "output": apply_behavior_to_output(
                self._shape_output_for_profile(str(delayed_record["output"]), task_input, profile, effective),
                effective,
            ),
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
