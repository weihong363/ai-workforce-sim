"""Provider abstractions and registry for vendor-agnostic routing."""

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Dict, Optional

from core_engine.errors import ExecutionError


class BaseProvider:
    provider_name = "base"

    def complete(self, prompt: str, model: str) -> Dict[str, object]:
        raise NotImplementedError


class MockProvider(BaseProvider):
    provider_name = "mock"

    def complete(self, prompt: str, model: str) -> Dict[str, object]:
        text = f"MOCK_LLM_RESPONSE: {prompt.splitlines()[0]}"
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(text.split()))
        return {
            "output": text,
            "model": model,
            "provider": self.provider_name,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


class OpenAICompatibleProvider(BaseProvider):
    """Generic provider for OpenAI-compatible Chat Completions APIs."""

    provider_name = "openai_compatible"

    def __init__(self, provider_name: str, api_key: Optional[str], base_url: str, timeout_seconds: float = 30.0) -> None:
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str, model: str) -> Dict[str, object]:
        if not self.api_key:
            raise ExecutionError(
                "provider_error",
                f"API key is required for provider '{self.provider_name}'.",
            )

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ExecutionError(
                "provider_error",
                "Provider HTTP error.",
                {"provider": self.provider_name, "status_code": exc.code, "response": detail},
            ) from exc
        except urllib.error.URLError as exc:
            raise ExecutionError(
                "provider_error",
                "Provider network error.",
                {"provider": self.provider_name, "error": str(exc)},
            ) from exc

        output = ""
        if body.get("choices"):
            message = body["choices"][0].get("message", {})
            output = str(message.get("content", "")).strip()
        if not output:
            raise ExecutionError(
                "provider_error",
                "Provider returned empty output.",
                {"provider": self.provider_name, "response": body},
            )

        usage = body.get("usage", {}) or {}
        prompt_tokens = int(usage.get("prompt_tokens") or max(1, len(prompt.split())))
        completion_tokens = int(usage.get("completion_tokens") or max(1, len(output.split())))
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))

        return {
            "output": output,
            "model": model,
            "provider": self.provider_name,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }


class AdapterProvider(BaseProvider):
    """Adapts external clients exposing complete(prompt)."""

    provider_name = "adapter"

    def __init__(self, client: object) -> None:
        self.client = client

    def complete(self, prompt: str, model: str) -> Dict[str, object]:
        if not hasattr(self.client, "complete"):
            raise ExecutionError("provider_error", "Injected provider client must implement complete(prompt).")
        text = self.client.complete(prompt)
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(str(text).split()))
        return {
            "output": str(text),
            "model": model,
            "provider": self.provider_name,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


ProviderFactory = Callable[[str, Dict[str, object]], BaseProvider]


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: Dict[str, ProviderFactory] = {}

    def register(self, provider_type: str, factory: ProviderFactory) -> None:
        self._factories[provider_type] = factory

    def create(self, provider_name: str, provider_config: Dict[str, object]) -> BaseProvider:
        provider_type = str(provider_config.get("type", "")).strip()
        if not provider_type:
            raise ExecutionError(
                "provider_error",
                f"Provider '{provider_name}' is missing required 'type' in connection config.",
            )
        if provider_type not in self._factories:
            raise ExecutionError(
                "provider_error",
                f"Provider type '{provider_type}' is not registered.",
                {"provider": provider_name},
            )
        return self._factories[provider_type](provider_name, provider_config)


def _mock_factory(provider_name: str, provider_config: Dict[str, object]) -> BaseProvider:
    return MockProvider()


def _openai_compatible_factory(provider_name: str, provider_config: Dict[str, object]) -> BaseProvider:
    api_key_env = str(provider_config.get("api_key_env", "OPENAI_API_KEY"))
    api_key = provider_config.get("api_key") or os.getenv(api_key_env)
    base_url = str(provider_config.get("base_url", "https://api.openai.com/v1"))
    timeout_seconds = float(provider_config.get("timeout_seconds", 30))
    return OpenAICompatibleProvider(
        provider_name=provider_name,
        api_key=str(api_key) if api_key else None,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


DEFAULT_PROVIDER_REGISTRY = ProviderRegistry()
DEFAULT_PROVIDER_REGISTRY.register("mock", _mock_factory)
DEFAULT_PROVIDER_REGISTRY.register("openai_compatible", _openai_compatible_factory)


def build_provider(
    provider_name: str,
    provider_connections: Dict[str, Dict[str, object]],
    llm_client: Optional[object] = None,
    registry: Optional[ProviderRegistry] = None,
) -> BaseProvider:
    if llm_client is not None:
        return AdapterProvider(llm_client)

    connection = provider_connections.get(provider_name)
    if connection is None:
        raise ExecutionError(
            "provider_error",
            f"Provider '{provider_name}' is not configured in provider connections.",
        )

    active_registry = registry or DEFAULT_PROVIDER_REGISTRY
    return active_registry.create(provider_name, connection)
