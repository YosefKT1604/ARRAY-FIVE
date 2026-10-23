"""Settings that choose the AI model, read from environment variables (and an optional .env file).

    SCDC_AI_PROVIDER     none (default: no model, every module uses its template / rules) | litellm
    SCDC_AI_MODEL        the model for LiteLLM, e.g. "anthropic/claude-haiku-5-5"
    SCDC_AI_API_BASE     optional address to send requests to (e.g. a Replit AI integration's base URL)
    SCDC_AI_API_KEY      optional key; if empty, LiteLLM uses the provider's usual variable (ANTHROPIC_API_KEY)
    SCDC_AI_TIMEOUT_S    seconds before a call is abandoned (default 20)
    SCDC_AI_MAX_TOKENS   upper limit on output tokens per call (default 1500)
    SCDC_DEMO_NOW        optional fixed "now" for the demo, with an offset, e.g. "2026-10-20T10:15:00+08:00";
                         messages are read as if received then. Empty (default) = the real clock.

On a PC, put these in `src/backend/.env` (git-ignored). On Replit, put them in Secrets. Real environment
variables win over the .env file. The default is "none", so the whole app works without any key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .adapter import ModelAdapter, NoModelAdapter

DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"   # src/backend/.env
PROVIDERS = ("none", "litellm")


class AIConfigError(ValueError):
    """The AI settings are invalid (e.g. an unknown provider, or litellm without a model)."""


@dataclass(frozen=True)
class AIConfig:
    """Which model to use and how long / how much it may take."""

    provider: str = "none"
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = field(default=None, repr=False)   # never printed
    timeout_s: float = 20.0
    max_output_tokens: int = 1500

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, dotenv_path: Path | None = DOTENV_PATH) -> "AIConfig":
        """Read the SCDC_AI_* settings: from `env` if given, else from the .env file and the real environment."""
        values = _settings(env, dotenv_path)

        def get(name: str) -> str | None:
            """One setting, with surrounding spaces removed; None if missing or empty."""
            value = (values.get(name) or "").strip()
            return value or None

        provider = (get("SCDC_AI_PROVIDER") or "none").lower()
        if provider not in PROVIDERS:
            raise AIConfigError(f"SCDC_AI_PROVIDER must be one of {', '.join(PROVIDERS)}, not '{provider}'.")
        config = cls(
            provider=provider,
            model=get("SCDC_AI_MODEL"),
            api_base=get("SCDC_AI_API_BASE"),
            api_key=get("SCDC_AI_API_KEY"),
            timeout_s=float(get("SCDC_AI_TIMEOUT_S") or 20),
            max_output_tokens=int(get("SCDC_AI_MAX_TOKENS") or 1500),
        )
        if config.provider == "litellm" and not config.model:
            raise AIConfigError("SCDC_AI_PROVIDER=litellm needs SCDC_AI_MODEL, e.g. anthropic/claude-haiku-5-5.")
        return config


def demo_now(env: Mapping[str, str] | None = None, *, dotenv_path: Path | None = DOTENV_PATH) -> datetime | None:
    """The fixed demo time from SCDC_DEMO_NOW, or None when it is not set (use the real clock).

    The value must be an ISO date and time with an offset ("2026-10-20T10:15:00+08:00"): without the
    offset it is unclear which day it is in Malaysia, so that is rejected like any other bad value.
    """
    raw = (_settings(env, dotenv_path).get("SCDC_DEMO_NOW") or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        raise AIConfigError(f"SCDC_DEMO_NOW must be like 2026-10-20T10:15:00+08:00, not '{raw}'.") from None
    if value.tzinfo is None:
        raise AIConfigError(f"SCDC_DEMO_NOW needs a time zone offset, e.g. '{raw}+08:00'.")
    return value


def _settings(env: Mapping[str, str] | None, dotenv_path: Path | None) -> dict[str, str]:
    """All settings: `env` if given, else the .env file overlaid by the real environment (which wins)."""
    return dict(env) if env is not None else {**_read_dotenv(dotenv_path), **os.environ}


def _read_dotenv(path: Path | None) -> dict[str, str]:
    """The settings in a .env file, without changing os.environ. Empty if there is no file or no python-dotenv."""
    if path is None or not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values  # installed with the `llm` extra (LiteLLM depends on it)
    except ImportError:
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def get_adapter(config: AIConfig | None = None) -> ModelAdapter:
    """The adapter the settings ask for. Call once at start-up and pass it to the modules as `adapter=`."""
    config = config or AIConfig.from_env()
    if config.provider == "litellm":
        from .litellm_adapter import LiteLLMAdapter
        return LiteLLMAdapter(config.model, api_base=config.api_base, api_key=config.api_key,
                              timeout_s=config.timeout_s, max_output_tokens=config.max_output_tokens)
    return NoModelAdapter()
