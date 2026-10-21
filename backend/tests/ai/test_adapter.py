"""Tests for the adapter interface, the no-model and mock adapters, and call_model."""

from __future__ import annotations

import json

import pytest

from scdc.ai.adapter import (
    MockAdapter,
    ModelError,
    ModelOutputError,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
    NoModelAdapter,
    call_model,
)


def make_request(task: str = "explain", key: str | None = None) -> ModelRequest:
    """Build a minimal request for these tests."""
    return ModelRequest(task=task, system="instructions", user="data", response_schema={}, fixture_key=key)


def test_no_model_adapter_is_always_unavailable():
    """With no provider configured, every call fails with ModelUnavailableError."""
    with pytest.raises(ModelUnavailableError):
        call_model(NoModelAdapter(), make_request())


def test_every_model_error_is_catchable_as_model_error():
    """Callers only need `except ModelError` to catch all three failure kinds."""
    for error in (ModelUnavailableError, ModelTimeoutError, ModelOutputError):
        assert issubclass(error, ModelError)


def test_mock_returns_text_and_dicts_as_json():
    """A string reply comes back as-is; a dict reply comes back as JSON text."""
    adapter = MockAdapter({"explain": "plain text", "extract_incident": {"a": 1}})
    assert call_model(adapter, make_request("explain")).text == "plain text"
    assert json.loads(call_model(adapter, make_request("extract_incident")).text) == {"a": 1}


def test_mock_lookup_order_is_key_then_task_then_star():
    """fixture_key wins over the task name, which wins over the "*" default."""
    adapter = MockAdapter({"D-001": "by key", "explain": "by task", "*": "default"})
    assert call_model(adapter, make_request("explain", "D-001")).text == "by key"
    assert call_model(adapter, make_request("explain", "D-999")).text == "by task"
    assert call_model(adapter, make_request("draft_message")).text == "default"


def test_mock_raises_scripted_errors():
    """An exception in the script is raised, to simulate timeouts and outages."""
    with pytest.raises(ModelTimeoutError):
        call_model(MockAdapter({"*": ModelTimeoutError("too slow")}), make_request())


def test_mock_without_matching_reply_is_unavailable():
    """A request the script does not cover behaves like a missing model."""
    with pytest.raises(ModelUnavailableError):
        call_model(MockAdapter({"explain": "x"}), make_request("draft_message"))


def test_mock_records_calls_and_supports_functions():
    """Replies can be functions of the request, and every request is recorded."""
    def echo(request):
        """Reply with the request's user text, to show replies can depend on the request."""
        return {"echo": request.user}

    adapter = MockAdapter({"*": echo})
    assert json.loads(call_model(adapter, make_request()).text) == {"echo": "data"}
    assert len(adapter.calls) == 1 and adapter.calls[0].task == "explain"


def test_call_model_turns_unexpected_crashes_into_unavailable():
    """A crash inside an adapter (network error, SDK bug) never escapes as a raw exception."""

    class CrashingAdapter:
        """An adapter whose provider SDK raises a non-model error."""

        name = "crashing"

        def complete(self, request):
            """Simulate the network going down."""
            raise ConnectionError("network down")

    with pytest.raises(ModelUnavailableError, match="ConnectionError"):
        call_model(CrashingAdapter(), make_request())


def test_call_model_rejects_wrong_return_type():
    """An adapter that returns something other than a ModelResponse is treated as bad output."""

    class SloppyAdapter:
        """An adapter that returns a plain string by mistake."""

        name = "sloppy"

        def complete(self, request):
            """Return the wrong type."""
            return "just a string"

    with pytest.raises(ModelOutputError):
        call_model(SloppyAdapter(), make_request())


def test_call_model_fills_in_latency():
    """call_model records how long the call took when the adapter did not."""
    response = call_model(MockAdapter({"*": "ok"}), make_request())
    assert isinstance(response, ModelResponse) and response.latency_ms >= 0 and response.model == "mock"
