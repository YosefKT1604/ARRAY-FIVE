"""The adapter: the single place where an AI model plugs into the system.

Modules (extraction, explanation, drafts) never talk to a provider directly. They build a
`ModelRequest` and call `call_model(adapter, request)`. An adapter is any object with a `name`
and a `complete(request) -> ModelResponse` method, so providers can be swapped without
touching the modules.

Each adapter is responsible for its own timeout (e.g. passing it to the provider's SDK).
`call_model` guarantees that every failure, even a crash inside an adapter, comes out as a
`ModelError`, so callers only need `except ModelError:` to switch to their fallback.

Adapters in this file need no network and no API key:
- `NoModelAdapter`: always unavailable, so every module uses its deterministic fallback.
- `MockAdapter`: replays scripted replies or errors, for tests.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Literal, Mapping, Protocol, Union

from pydantic import BaseModel

AITask = Literal["extract_incident", "explain", "draft_message"]


# --- Errors -------------------------------------------------------------------


class ModelError(Exception):
    """Base class for every model failure. Catch this to fall back to deterministic logic."""


class ModelUnavailableError(ModelError):
    """No provider is configured, or the provider could not be reached."""


class ModelTimeoutError(ModelError):
    """The provider did not answer within the adapter's timeout."""


class ModelOutputError(ModelError):
    """The provider answered, but the reply cannot be used (wrong type, invalid JSON, wrong schema)."""


# --- Request and response ---------------------------------------------------------


class ModelRequest(BaseModel):
    """Everything an adapter needs to make one model call."""

    task: AITask
    system: str                      # instructions for the model
    user: str                        # the data: message text, facts, draft...
    response_schema: dict[str, Any]  # JSON schema the reply must match
    fixture_key: str | None = None   # lets MockAdapter pick a canned reply in tests
    max_output_tokens: int = 1024
    temperature: float = 0.0         # 0 = as repeatable as possible


class ModelResponse(BaseModel):
    """The raw reply from a provider. Each module parses and validates `text` itself."""

    text: str
    model: str                       # e.g. "mock" or a provider model name; used in generated_by
    latency_ms: int = 0
    input_tokens: int | None = None  # for cost tracking, when the provider reports it
    output_tokens: int | None = None


class ModelAdapter(Protocol):
    """The interface every provider implements. Any object with these members counts."""

    name: str

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Send one request to the model and return its reply, or raise a ModelError."""
        ...


# --- Adapters that need no model ---------------------------------------------------


class NoModelAdapter:
    """Used when no AI provider is configured. Every call reports the model as unavailable."""

    name = "none"

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Always raise ModelUnavailableError, so the caller uses its deterministic fallback."""
        raise ModelUnavailableError("No AI provider configured.")


ScriptedReply = Union[str, dict, list, Exception, Callable[[ModelRequest], Any]]


class MockAdapter:
    """Replays scripted replies, for tests and offline demos. Records every request in `calls`.

    `replies` maps a key to a reply. For each request it tries, in order: the request's
    `fixture_key`, then the task name, then "*". A reply can be:
      - a string: returned as the model's text (it may be deliberately broken, e.g. not JSON);
      - a dict or list: turned into JSON text;
      - an exception instance: raised, e.g. ModelTimeoutError() to simulate a timeout;
      - a function taking the request: called, and its result handled as above.
    If no key matches, it raises ModelUnavailableError.
    """

    def __init__(self, replies: Mapping[str, ScriptedReply] | None = None, name: str = "mock") -> None:
        """Store the scripted replies and start with an empty call log."""
        self.replies: dict[str, ScriptedReply] = dict(replies or {})
        self.name = name
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Find the scripted reply for this request, then return it or raise it."""
        self.calls.append(request)
        reply = self._find_reply(request)
        if callable(reply) and not isinstance(reply, Exception):
            reply = reply(request)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return ModelResponse(text=text, model=self.name)

    def _find_reply(self, request: ModelRequest) -> ScriptedReply:
        """Look up the reply by fixture_key, then task name, then "*"."""
        for key in (request.fixture_key, request.task, "*"):
            if key is not None and key in self.replies:
                return self.replies[key]
        raise ModelUnavailableError(f"MockAdapter has no reply for task={request.task} key={request.fixture_key!r}.")


# --- The one way modules reach a model ------------------------------------------------


def call_model(adapter: ModelAdapter, request: ModelRequest) -> ModelResponse:
    """Call an adapter and make sure every failure comes out as a ModelError.

    - ModelErrors raised by the adapter (unavailable, timeout, bad output) pass through unchanged.
    - Any other exception (network error, SDK bug) becomes ModelUnavailableError.
    - A reply that is not a ModelResponse becomes ModelOutputError.
    - Latency is measured here if the adapter did not report it.
    """
    started = time.perf_counter()
    try:
        response = adapter.complete(request)
    except ModelError:
        raise
    except Exception as exc:
        raise ModelUnavailableError(f"Model call failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(response, ModelResponse):
        raise ModelOutputError(f"Adapter returned {type(response).__name__}, not a ModelResponse.")
    if not response.latency_ms:
        response = response.model_copy(update={"latency_ms": int((time.perf_counter() - started) * 1000)})
    return response
