"""Runtime configuration loaded from environment variables.

This module keeps provider/model routing vendor-agnostic while preserving
backward compatibility with legacy env keys.
"""

import json
import os
from dataclasses import dataclass
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


DEFAULT_PROVIDER_CONNECTIONS = {
    "mock": {"type": "mock"},
    "openai": {
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
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
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)


def get_settings() -> Settings:
    _load_env_file()

    connections = _json_or_default(
        os.getenv("PROVIDER_CONNECTIONS_JSON"),
        DEFAULT_PROVIDER_CONNECTIONS,
    )

    # Vendor-agnostic routing keys.
    provider_for_task = os.getenv("PROVIDER_FOR_TASK", os.getenv("LLM_PROVIDER", "mock"))
    provider_for_evaluation = os.getenv("PROVIDER_FOR_EVALUATION", provider_for_task)
    fallback_provider = os.getenv("FALLBACK_PROVIDER") or os.getenv("LLM_FALLBACK_PROVIDER")

    model_for_task = os.getenv("MODEL_FOR_TASK", os.getenv("LLM_MODEL", "mvp-default"))
    model_for_evaluation = os.getenv("MODEL_FOR_EVALUATION", model_for_task)
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
        provider_connections={k: dict(v) for k, v in connections.items() if isinstance(v, dict)},
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
            "evaluation": model_for_evaluation,
        },
        fallback_model_for_purpose={
            "task": fallback_model,
            "evaluation": fallback_model,
        },
    )
