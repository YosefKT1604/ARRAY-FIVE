"""Module A: turn a supplier's message into a draft incident.

    extract_incident(message, snapshot, reported_at, *, sender=None, adapter=None) -> ExtractionResult

Steps: the rules always read the message; the model reads it too if an adapter is given; any model
failure (unavailable, timeout, invalid reply) means the rules' reading is used alone, with a warning,
and no retry. `combine()` then decides what to trust and runs the checks.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import ValidationError

from .adapter import ModelAdapter, ModelError, ModelOutputError, ModelTimeoutError, NoModelAdapter, call_model
from .combine import combine
from .prompts import build_extraction_request
from .rules import rule_based_extract
from .schemas import BusinessSnapshot, ExtractionResult, RawExtraction

EMPTY_MESSAGE_WARNING = "The message is empty."
FALLBACK_WARNINGS = {
    ModelTimeoutError: "The AI model did not answer in time; the message was read by the rules only.",
    ModelOutputError: "The AI model's reply could not be used; the message was read by the rules only.",
}
UNAVAILABLE_WARNING = "AI model unavailable; the message was read by the rules only."


def extract_incident(
    message: str,
    snapshot: BusinessSnapshot,
    reported_at: datetime,
    *,
    sender: str | None = None,
    adapter: ModelAdapter | None = None,
) -> ExtractionResult:
    """Read the message with the rules and (if available) the model, then combine and check the readings.

    `adapter=None` means no model: the rules' reading is used. An empty message skips the model.
    """
    reported_on = reported_at.date()
    rules = rule_based_extract(message, snapshot, reported_on)

    if not message.strip():
        return combine(rules, None, snapshot, reported_at, sender=sender, warnings=[EMPTY_MESSAGE_WARNING])

    try:
        model, model_name = read_with_model(message, reported_on, adapter or NoModelAdapter())
    except ModelError as error:
        warning = FALLBACK_WARNINGS.get(type(error), UNAVAILABLE_WARNING)
        return combine(rules, None, snapshot, reported_at, sender=sender, warnings=[warning])

    return combine(rules, model, snapshot, reported_at, sender=sender, generated_by=f"model:{model_name}")


def read_with_model(message: str, reported_on: date, adapter: ModelAdapter) -> tuple[RawExtraction, str]:
    """Ask the model to read the message; return its validated reading and the model's name.

    The reply must be exactly one JSON object matching RawExtraction; anything else raises ModelOutputError.
    """
    response = call_model(adapter, build_extraction_request(message, reported_on))
    try:
        return RawExtraction.model_validate_json(response.text), response.model
    except ValidationError as error:
        raise ModelOutputError(f"Invalid extraction reply: {error.error_count()} problem(s)") from error
