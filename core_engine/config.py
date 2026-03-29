"""Runtime configuration loaded from environment variables.

This module keeps provider/model routing vendor-agnostic while preserving
backward compatibility with legacy env keys.
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Mapping, Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    active_game_module: str
    database_url: Optional[str]
    redis_url: str

    llm_max_concurrency: int
    provider_retry_attempts: int
    enable_agent_cache: bool
    enable_evaluation_cache: bool
    llm_cost_per_1k_tokens_usd: float
    task_result_cache_ttl_seconds: int
    task_cache_delay_min_ms: int
    task_cache_delay_max_ms: int
    obedience_weight: float
    initiative_weight: float
    effort_weight: float
    clarity_impact_weight: float
    task_token_budget_multiplier: float
    agent_token_budget_multiplier: float
    agent_cost_weight_overrides: Dict[str, float]

    provider_connections: Dict[str, Dict[str, object]]
    provider_for_purpose: Dict[str, str]
    fallback_provider_for_purpose: Dict[str, Optional[str]]

    model_for_purpose: Dict[str, str]
    fallback_model_for_purpose: Dict[str, Optional[str]]

    @property
    def llm_provider(self) -> str:
        return self.get_provider("task")

    @property
    def llm_model(self) -> str:
        return self.get_model("task")

    @property
    def use_mock_provider(self) -> bool:
        # Legacy compatibility flag.
        return self.llm_provider == "mock"

    def get_provider(self, purpose: str) -> str:
        return self.provider_for_purpose.get(purpose, self.provider_for_purpose.get("task", "mock"))

    def get_fallback_provider(self, purpose: str) -> Optional[str]:
        return self.fallback_provider_for_purpose.get(purpose, self.fallback_provider_for_purpose.get("task"))

    def get_model(self, purpose: str) -> str:
        return self.model_for_purpose.get(purpose, self.model_for_purpose.get("task", "mvp-default"))

    def get_fallback_model(self, purpose: str) -> Optional[str]:
        return self.fallback_model_for_purpose.get(purpose, self.fallback_model_for_purpose.get("task"))

    def get_model_for_role(self, purpose: str, agent_level: str) -> str:
        level = (agent_level or "").lower()
        if purpose == "evaluation":
            return self.model_for_purpose.get("evaluation", self.get_model("task"))
        if level == "junior":
            return self.model_for_purpose.get("task_junior", self.get_model("task"))
        if level == "mid":
            return self.model_for_purpose.get("task_mid", self.get_model("task"))
        if level == "senior":
            return self.model_for_purpose.get("task_senior", self.get_model("task"))
        return self.get_model("task")


DEFAULT_PROVIDER_CONNECTIONS = {
    "mock": {"type": "mock"},
    "openai": {
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "timeout_seconds": 30,
    },
    "siliconflow": {
        "type": "openai_compatible",
        "base_url": "https://api.siliconflow.com/v1",
        "api_key_env": "PROVIDER_SILICONFLOW_API_KEY",
        "timeout_seconds": 30,
    },
}


def _to_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _to_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _positive_float(value: Optional[str], default: float) -> float:
    parsed = _to_float(value, default)
    return parsed if parsed > 0 else default


def _json_or_default(raw: Optional[str], default: Mapping[str, object]) -> Dict[str, object]:
    if not raw:
        return dict(default)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return dict(default)
    if not isinstance(value, dict):
        return dict(default)
    return value


def _load_env_file() -> None:
    """Load .env file lazily (only once)."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)


def _apply_provider_env_overrides(connections: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    """Apply environment variable overrides to provider connections.
    
    Environment variables follow the pattern: PROVIDER_{NAME}_{FIELD}
    Example: PROVIDER_OPENAI_API_KEY, PROVIDER_ANTHROPIC_BASE_URL
    
    Args:
        connections: Provider connection configurations from JSON or defaults
        
    Returns:
        New dictionary with environment overrides applied
    """
    result = {}
    for provider_name, cfg in connections.items():
        if not isinstance(cfg, dict):
            continue
            
        # Create a new dict to avoid mutating input
        provider_config = dict(cfg)
        
        # Build env var prefix (handle special characters in provider name)
        prefix = provider_name.upper().replace("-", "_").replace(".", "_")
        
        # Apply all supported overrides using a field mapping
        override_fields = {
            "api_key": f"PROVIDER_{prefix}_API_KEY",
            "base_url": f"PROVIDER_{prefix}_BASE_URL",
            "timeout_seconds": f"PROVIDER_{prefix}_TIMEOUT_SECONDS",
        }
        
        for field_name, env_var in override_fields.items():
            value = os.getenv(env_var)
            if value:
                if field_name == "timeout_seconds":
                    try:
                        provider_config[field_name] = float(value)
                    except ValueError:
                        pass  # Keep original value if parsing fails
                else:
                    provider_config[field_name] = value
        
        result[provider_name] = provider_config
    
    return result


@lru_cache(maxsize=None)
def get_settings(force_reload: bool = False) -> Settings:
    """Get application settings with caching support.
    
    Settings are loaded lazily on first access and cached for subsequent calls.
    This avoids repeated file I/O and environment variable lookups.
    
    Args:
        force_reload: If True, bypass cache and reload from environment.
                     Note: This requires calling cache_clear() first.
        
    Returns:
        Settings instance with current configuration
    """
    # Lazy load .env file (only happens once due to lru_cache)
    _load_env_file()
    
    # Load connections from JSON or use defaults
    raw_connections = _json_or_default(
        os.getenv("PROVIDER_CONNECTIONS_JSON"),
        DEFAULT_PROVIDER_CONNECTIONS,
    )
    
    # Filter valid dicts and apply environment overrides
    connections = _apply_provider_env_overrides(raw_connections)

    # Vendor-agnostic routing keys.
    default_provider = os.getenv("DEFAULT_PROVIDER")
    provider_for_task = os.getenv(
        "PROVIDER_FOR_TASK",
        default_provider or os.getenv("LLM_PROVIDER", "mock"),
    )
    provider_for_evaluation = os.getenv("PROVIDER_FOR_EVALUATION", provider_for_task)
    fallback_provider = os.getenv("FALLBACK_PROVIDER") or os.getenv("LLM_FALLBACK_PROVIDER")

    model_for_task = os.getenv("MODEL_FOR_TASK", os.getenv("LLM_MODEL", "mvp-default"))
    model_for_evaluation = os.getenv("MODEL_FOR_EVALUATION", model_for_task)
    model_task_junior = os.getenv("MODEL_TASK_JUNIOR", model_for_task)
    model_task_mid = os.getenv("MODEL_TASK_MID", model_for_task)
    model_task_senior = os.getenv("MODEL_TASK_SENIOR", model_for_task)
    model_evaluator = os.getenv("MODEL_EVALUATOR", model_for_evaluation)
    fallback_model = os.getenv("FALLBACK_MODEL") or os.getenv("LLM_FALLBACK_MODEL")

    return Settings(
        active_game_module=os.getenv("ACTIVE_GAME_MODULE", "business_sim"),
        database_url=os.getenv("DATABASE_URL"),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        llm_max_concurrency=_to_int(os.getenv("LLM_MAX_CONCURRENCY"), 2),
        provider_retry_attempts=_to_int(os.getenv("PROVIDER_RETRY_ATTEMPTS"), 2),
        enable_agent_cache=_to_bool(os.getenv("ENABLE_AGENT_CACHE"), default=True),
        enable_evaluation_cache=_to_bool(os.getenv("ENABLE_EVALUATION_CACHE"), default=True),
        llm_cost_per_1k_tokens_usd=_to_float(os.getenv("LLM_COST_PER_1K_TOKENS_USD"), 0.0),
        task_result_cache_ttl_seconds=_to_int(os.getenv("TASK_RESULT_CACHE_TTL_SECONDS"), 600),
        task_cache_delay_min_ms=_to_int(os.getenv("TASK_CACHE_DELAY_MIN_MS"), 60),
        task_cache_delay_max_ms=_to_int(os.getenv("TASK_CACHE_DELAY_MAX_MS"), 180),
        obedience_weight=_to_float(os.getenv("OBEDIENCE_WEIGHT"), 1.0),
        initiative_weight=_to_float(os.getenv("INITIATIVE_WEIGHT"), 1.0),
        effort_weight=_to_float(os.getenv("EFFORT_WEIGHT"), 1.0),
        clarity_impact_weight=_to_float(os.getenv("CLARITY_IMPACT_WEIGHT"), 0.35),
        task_token_budget_multiplier=_positive_float(os.getenv("TASK_TOKEN_BUDGET_MULTIPLIER"), 1.0),
        agent_token_budget_multiplier=_positive_float(os.getenv("AGENT_TOKEN_BUDGET_MULTIPLIER"), 1.0),
        agent_cost_weight_overrides={
            str(k): float(v)
            for k, v in _json_or_default(os.getenv("AGENT_COST_WEIGHT_JSON"), {}).items()
            if isinstance(v, (int, float))
        },
        provider_connections=connections,
        provider_for_purpose={
            "task": provider_for_task,
            "evaluation": provider_for_evaluation,
        },
        fallback_provider_for_purpose={
            "task": fallback_provider,
            "evaluation": fallback_provider,
        },
        model_for_purpose={
            "task": model_for_task,
            "task_junior": model_task_junior,
            "task_mid": model_task_mid,
            "task_senior": model_task_senior,
            "evaluation": model_evaluator,
        },
        fallback_model_for_purpose={
            "task": fallback_model,
            "evaluation": fallback_model,
        },
    )
