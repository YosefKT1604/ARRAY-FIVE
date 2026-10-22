"""Tests for the AI settings and the LiteLLM adapter. A fake `completion` is used: no network, no key, no LiteLLM import."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scdc.ai.adapter import ModelOutputError, ModelRequest, ModelTimeoutError, ModelUnavailableError, NoModelAdapter, call_model
from scdc.ai.config import AIConfig, AIConfigError, get_adapter
from scdc.ai.extraction import extract_incident
from scdc.ai.litellm_adapter import LiteLLMAdapter
from scdc.ai.schemas import RawExtraction

from .conftest import DEMO_MESSAGE

REPORTED_AT = datetime(2026, 10, 20, 10, 15, tzinfo=timezone(timedelta(hours=8)))


def fake_response(text, prompt_tokens=120, completion_tokens=40):
    """An object shaped like LiteLLM's response."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
                           usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens))


class FakeCompletion:
    """Stands in for litellm.completion: records the arguments and returns (or raises) a scripted result."""

    def __init__(self, result):
        """Store what to return or raise."""
        self.result = result
        self.calls = []

    def __call__(self, **arguments):
        """Record the call; raise the result if it is an exception, else return it."""
        self.calls.append(arguments)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def request():
    """A small request, as a module would build it."""
    return ModelRequest(task="extract_incident", system="Rules...", user='{"message": "hi"}',
                        response_schema=RawExtraction.model_json_schema(), max_output_tokens=600)


# --- Settings ----------------------------------------------------------------------------------


def test_default_is_no_model():
    """With no settings, the provider is 'none' and every module uses its fallback."""
    config = AIConfig.from_env({})
    assert config.provider == "none" and isinstance(get_adapter(config), NoModelAdapter)


def test_litellm_settings():
    """All settings are read; the key is never shown in the config's text form."""
    config = AIConfig.from_env({"SCDC_AI_PROVIDER": "LiteLLM", "SCDC_AI_MODEL": " anthropic/claude-haiku-5-5 ",
                                "SCDC_AI_API_BASE": "https://example.invalid/v1", "SCDC_AI_API_KEY": "secret-123",
                                "SCDC_AI_TIMEOUT_S": "15", "SCDC_AI_MAX_TOKENS": "800"})
    assert (config.provider, config.model, config.timeout_s, config.max_output_tokens) == (
        "litellm", "anthropic/claude-haiku-5-5", 15.0, 800)
    assert "secret-123" not in repr(config)
    adapter = get_adapter(config)
    assert isinstance(adapter, LiteLLMAdapter) and adapter.name == "anthropic/claude-haiku-5-5"
    assert "secret-123" not in repr(adapter)


def test_invalid_settings_fail_loudly():
    """An unknown provider, or litellm without a model, is a configuration error at start-up."""
    with pytest.raises(AIConfigError):
        AIConfig.from_env({"SCDC_AI_PROVIDER": "openai-direct"})
    with pytest.raises(AIConfigError):
        AIConfig.from_env({"SCDC_AI_PROVIDER": "litellm"})


def test_dotenv_file_and_environment(tmp_path, monkeypatch):
    """The .env file is read without changing os.environ; a real environment variable wins over it."""
    dotenv = tmp_path / ".env"
    dotenv.write_text("SCDC_AI_PROVIDER=litellm\nSCDC_AI_MODEL=anthropic/claude-haiku-5-5\nSCDC_AI_TIMEOUT_S=30\n")
    monkeypatch.delenv("SCDC_AI_PROVIDER", raising=False)
    monkeypatch.delenv("SCDC_AI_MODEL", raising=False)
    monkeypatch.setenv("SCDC_AI_TIMEOUT_S", "12")
    config = AIConfig.from_env(dotenv_path=dotenv)
    assert (config.provider, config.model, config.timeout_s) == ("litellm", "anthropic/claude-haiku-5-5", 12.0)
    assert "SCDC_AI_MODEL" not in __import__("os").environ


# --- The adapter -----------------------------------------------------------------------------------


def test_call_arguments():
    """Timeout, no retries, the token limit, JSON schema mode, base URL and key are all passed."""
    fake = FakeCompletion(fake_response('{"flags": []}'))
    adapter = LiteLLMAdapter("anthropic/claude-haiku-5-5", api_base="https://example.invalid/v1", api_key="k",
                             timeout_s=15, max_output_tokens=500, completion=fake)
    adapter.complete(request())
    args = fake.calls[0]
    assert args["model"] == "anthropic/claude-haiku-5-5" and args["timeout"] == 15 and args["num_retries"] == 0
    assert args["max_tokens"] == 500 and args["temperature"] == 0.0
    assert args["messages"] == [{"role": "system", "content": "Rules..."}, {"role": "user", "content": '{"message": "hi"}'}]
    assert args["response_format"]["type"] == "json_schema"
    assert args["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert (args["api_base"], args["api_key"]) == ("https://example.invalid/v1", "k")


def test_no_base_or_key_means_provider_defaults():
    """Without a base URL or key, LiteLLM is left to use the provider's usual address and key variable."""
    fake = FakeCompletion(fake_response("{}"))
    LiteLLMAdapter("anthropic/claude-haiku-5-5", completion=fake).complete(request())
    assert "api_base" not in fake.calls[0] and "api_key" not in fake.calls[0]


def test_reply_text_and_usage():
    """The reply text, model name, token counts and a latency come back in a ModelResponse."""
    adapter = LiteLLMAdapter("anthropic/claude-haiku-5-5", completion=FakeCompletion(fake_response('{"a": 1}', 300, 50)))
    response = adapter.complete(request())
    assert (response.text, response.model, response.input_tokens, response.output_tokens) == (
        '{"a": 1}', "anthropic/claude-haiku-5-5", 300, 50)
    assert response.latency_ms >= 1


@pytest.mark.parametrize("error, expected", [
    (type("Timeout", (Exception,), {})("slow"), ModelTimeoutError),
    (TimeoutError("slow"), ModelTimeoutError),
    (type("AuthenticationError", (Exception,), {})("bad key"), ModelUnavailableError),
    (ConnectionError("no network"), ModelUnavailableError),
])
def test_errors_become_model_errors(error, expected):
    """Timeouts become ModelTimeoutError; anything else (bad key, no network) ModelUnavailableError."""
    adapter = LiteLLMAdapter("anthropic/claude-haiku-5-5", completion=FakeCompletion(error))
    with pytest.raises(expected):
        call_model(adapter, request())


@pytest.mark.parametrize("response", [fake_response(None), fake_response("   "), SimpleNamespace(choices=[])])
def test_empty_or_odd_reply_is_an_output_error(response):
    """No text, or an unexpected response shape, is a ModelOutputError."""
    with pytest.raises(ModelOutputError):
        LiteLLMAdapter("m", completion=FakeCompletion(response)).complete(request())


def test_module_end_to_end_with_the_adapter(snapshot):
    """extract_incident() works through the LiteLLM adapter exactly as with the mock."""
    reading = {"disruption_type": "supplier_delay", "supplier_name": None, "resource_name": "chairs",
               "quantity_affected": 20, "original_arrival_date": "2026-10-21", "new_arrival_date": "2026-10-23",
               "flags": []}
    adapter = LiteLLMAdapter("anthropic/claude-haiku-5-5", completion=FakeCompletion(fake_response(json.dumps(reading))))
    result = extract_incident(DEMO_MESSAGE, snapshot, REPORTED_AT, sender="whatsapp:maju-rental (synthetic)",
                              adapter=adapter)
    assert result.generated_by == "model:anthropic/claude-haiku-5-5" and not result.fallback_used
    assert result.unresolved_fields == []
