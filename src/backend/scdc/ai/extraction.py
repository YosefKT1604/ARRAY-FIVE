"""Module A: turn a supplier's message into a draft incident.

    extract_from_message(incoming, snapshot, *, adapter=None) -> ExtractionResult      (a WhatsApp message)
    extract_incident(message, snapshot, reported_at, *, sender=None, from_number=None, contact_name=None,
                     adapter=None) -> ExtractionResult

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
from .schemas import BusinessSnapshot, ExtractionResult, IncomingMessage, RawExtraction

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
    from_number: str | None = None,
    contact_name: str | None = None,
    adapter: ModelAdapter | None = None,
) -> ExtractionResult:
    """Read the message with the rules and (if available) the model, then combine and check the readings.

    The sender's contact details (`sender` contact reference, `from_number`, `contact_name` = the owner's
    saved name for the number) help identify the supplier; they are never sent to the model.
    `adapter=None` means no model: the rules' reading is used. An empty message skips the model.
    """
    reported_on = reported_at.date()
    rules = rule_based_extract(message, snapshot, reported_on)
    contact = {"sender": sender, "from_number": from_number, "contact_name": contact_name}

    if not message.strip():
        return combine(rules, None, snapshot, reported_at, **contact, warnings=[EMPTY_MESSAGE_WARNING])

    try:
        model, model_name = read_with_model(message, reported_on, adapter or NoModelAdapter())
    except ModelError as error:
        warning = FALLBACK_WARNINGS.get(type(error), UNAVAILABLE_WARNING)
        return combine(rules, None, snapshot, reported_at, **contact, warnings=[warning])

    return combine(rules, model, snapshot, reported_at, **contact, generated_by=f"model:{model_name}")


def extract_from_message(
    incoming: IncomingMessage,
    snapshot: BusinessSnapshot,
    *,
    adapter: ModelAdapter | None = None,
) -> ExtractionResult:
    """Extract from a message as it arrived: its text, time, sender's number and the owner's saved contact name."""
    return extract_incident(incoming.text, snapshot, incoming.received_at, sender=incoming.from_contact,
                            from_number=incoming.from_number, contact_name=incoming.contact_name, adapter=adapter)


def read_with_model(message: str, reported_on: date, adapter: ModelAdapter) -> tuple[RawExtraction, str]:
    """Ask the model to read the message; return its validated reading and the model's name.

    The reply must be exactly one JSON object matching RawExtraction; anything else raises ModelOutputError.
    """
    response = call_model(adapter, build_extraction_request(message, reported_on))
    try:
        return RawExtraction.model_validate_json(response.text), response.model
    except ValidationError as error:
        raise ModelOutputError(f"Invalid extraction reply: {error.error_count()} problem(s)") from error
