"""The live model adapter, through LiteLLM (one library for Claude, GPT, Gemini, local models...).

Provider-neutral: the model name, an optional base URL (e.g. Replit's AI integration) and an optional
key come from the settings (`config.py`). Agreed in v2 step 5:
- this adapter passes the timeout to LiteLLM itself, and never retries (num_retries=0);
- it asks the provider for JSON matching the module's schema (response_format), and the modules still
  validate every reply strictly;
- LiteLLM is imported only when a call is made, so tests and model-less runs never need it or the network.
  Importing it can fail (not installed, no internet): that counts as "model unavailable", so the module
  falls back to its template or rules.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from .adapter import ModelOutputError, ModelRequest, ModelResponse, ModelTimeoutError, ModelUnavailableError

# Exception class names (from LiteLLM, httpx, openai) that mean the call took too long.
TIMEOUT_ERRORS = {"Timeout", "APITimeoutError", "ReadTimeout", "ConnectTimeout", "TimeoutError", "TimeoutException"}


def _load_completion() -> Callable[..., Any]:
    """Import LiteLLM's `completion` function, with remote downloads and debug output turned off."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # do not fetch the price list from GitHub
    try:
        import litellm
    except ImportError as error:
        raise ModelUnavailableError("LiteLLM is not installed: pip install -e .[llm]") from error
    except Exception as error:  # e.g. no internet for its first-time tokenizer download
        raise ModelUnavailableError(f"LiteLLM could not start: {type(error).__name__}: {error}") from error
    litellm.suppress_debug_info = True
    return litellm.completion


class LiteLLMAdapter:
    """Calls a real model through LiteLLM. `completion` can be replaced in tests (no network)."""

    def __init__(
        self,
        model: str,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 20.0,
        max_output_tokens: int = 1500,
        completion: Callable[..., Any] | None = None,
    ) -> None:
        """Remember the settings; LiteLLM itself is loaded on the first call."""
        self.name = model
        self.api_base = api_base
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.max_output_tokens = max_output_tokens
        self._completion = completion

    def __repr__(self) -> str:
        """Show the settings, never the key."""
        return f"LiteLLMAdapter(model={self.name!r}, api_base={self.api_base!r}, timeout_s={self.timeout_s})"

    def call_arguments(self, request: ModelRequest) -> dict[str, Any]:
        """The arguments for litellm.completion(): messages, limits, timeout, no retries, JSON schema."""
        arguments: dict[str, Any] = {
            "model": self.name,
            "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
            "temperature": request.temperature,
            "max_tokens": min(request.max_output_tokens, self.max_output_tokens),
            "timeout": self.timeout_s,
            "num_retries": 0,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": request.task, "schema": request.response_schema}},
            "drop_params": True,  # a provider without JSON mode still answers; our validation still applies
        }
        if self.api_base:
            arguments["api_base"] = self.api_base
        if self._api_key:
            arguments["api_key"] = self._api_key
        return arguments

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Send one request; return the reply text with timing and token counts, or raise a ModelError."""
        completion = self._completion or _load_completion()
        started = time.perf_counter()
        try:
            response = completion(**self.call_arguments(request))
        except Exception as error:
            if type(error).__name__ in TIMEOUT_ERRORS or isinstance(error, TimeoutError):
                raise ModelTimeoutError(f"{self.name} did not answer within {self.timeout_s}s") from error
            raise ModelUnavailableError(f"{self.name} call failed: {type(error).__name__}: {error}") from error

        try:
            text = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as error:
            raise ModelOutputError(f"{self.name} returned an unexpected response shape") from error
        if not isinstance(text, str) or not text.strip():
            raise ModelOutputError(f"{self.name} returned no text")
        usage = getattr(response, "usage", None)
        return ModelResponse(
            text=text,
            model=self.name,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )
