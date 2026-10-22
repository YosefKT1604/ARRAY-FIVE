"""Module C: draft supplier and customer messages for an approved plan.

    draft_messages(plan, incident, snapshot, *, adapter=None) -> list[DraftMessage]

Steps (agreed in v2 step 4c):
1. The plan must be approved, else DraftNotAllowedError (the only error this module raises).
2. Code writes the template drafts (`drafts_template.py`).
3. The model polishes each draft, seeing only the draft text (no business records).
4. The polished text is used only if it passes every check; otherwise that draft keeps the template text:
     - every placeholder kept exactly, and no new placeholder;
     - no fact beyond the template's (claim checker, with the template text as the fact sheet);
     - a question stays a question (the template asks with "?", so must the polish);
     - no new commitment words ("confirmed", "guaranteed", "booked"...) unless the template has them.
Drafts are never sent; status stays "draft" until the owner approves one through P2's API.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from .adapter import ModelAdapter, ModelError, ModelOutputError, NoModelAdapter, call_model
from .claims import CheckContext, facts_from_text, find_problems
from .drafts_template import placeholders_in, template_drafts
from .prompts import build_draft_request
from .schemas import BusinessSnapshot, DraftMessage, NormalizedIncident, PlanStatus, RawDraft, RecoveryPlan

COMMITMENT_RE = re.compile(
    r"\b(confirmed|guarantee\w*|promis\w*|definitely|certainly|for sure|booked|reserved|"
    r"has been (?:moved|rescheduled|ordered|arranged)|is (?:moved|rescheduled|ordered|arranged))\b",
    re.IGNORECASE)


class DraftNotAllowedError(Exception):
    """Drafts were requested for a plan the owner has not approved."""


def draft_messages(
    plan: RecoveryPlan,
    incident: NormalizedIncident,
    snapshot: BusinessSnapshot,
    *,
    adapter: ModelAdapter | None = None,
) -> list[DraftMessage]:
    """The drafts for an approved plan: polished by the model where the polish passes every check.

    `adapter=None` means no model: the template drafts are returned. Model failures never raise.
    """
    if plan.status != PlanStatus.APPROVED:
        raise DraftNotAllowedError(f"Plan {plan.id} is '{plan.status.value}'; drafts are only made for approved plans.")
    adapter = adapter or NoModelAdapter()
    return [polish(draft, incident, adapter) for draft in template_drafts(plan, incident, snapshot)]


def polish(draft: DraftMessage, incident: NormalizedIncident, adapter: ModelAdapter) -> DraftMessage:
    """Ask the model to polish one draft; keep the template text if the call fails or the polish fails a check."""
    try:
        response = call_model(adapter, build_draft_request(draft))
        try:
            body = RawDraft.model_validate_json(response.text).body
        except ValidationError as error:
            raise ModelOutputError(f"Invalid draft reply: {error.error_count()} problem(s)") from error
    except ModelError:
        return draft
    if draft_problems(body, draft.body, incident):
        return draft
    return draft.model_copy(update={"body": body, "generated_by": f"model:{response.model}"})


def draft_problems(polished: str, template: str, incident: NormalizedIncident) -> list[str]:
    """Every reason the polished text may not replace the template text (empty list = it may)."""
    problems: list[str] = []
    kept, wanted = placeholders_in(polished), placeholders_in(template)
    problems += [f"placeholder [{p}] missing" for p in wanted if f"[{p}]" not in polished]
    problems += [f"new placeholder [{p}]" for p in kept if p not in wanted]

    reported_on = incident.reported_at.date()
    problems += find_problems(polished, facts_from_text(template, reported_on), CheckContext(reported_on))

    if "?" in template and "?" not in polished:
        problems.append("the request is no longer a question")
    allowed = {m.lower() for m in COMMITMENT_RE.findall(template)}
    problems += [f"new commitment '{m}'" for m in COMMITMENT_RE.findall(polished) if m.lower() not in allowed]
    return list(dict.fromkeys(problems))
