"""Module C, deterministic part: template draft messages for an approved plan.

One message per action that involves someone outside the business (agreed in v2 step 4):
    source_alternative_supplier   -> the new supplier: order request, asking them to confirm
    contact_supplier              -> that supplier: the request, phrased as a question
    reschedule_job                -> the job's customer: the new date is proposed, never promised
    use_spare_inventory, reallocate_resource, split_allocation -> internal, no message

Anything the data does not have becomes a placeholder in square brackets, e.g. [DELIVERY_ADDRESS],
and is listed (without brackets) in `placeholders`. Drafts are never sent; the owner reviews them.
"""

from __future__ import annotations

import re
from datetime import date

from .dates import find_date_mentions
from .explanation_template import MONTHS, fmt_money
from .schemas import ActionType, BusinessSnapshot, DraftMessage, NormalizedIncident, RecipientType, RecoveryAction, RecoveryPlan

PLACEHOLDER_RE = re.compile(r"\[([A-Z][A-Z_]*)\]")


def _as_date(value: date | str | None) -> date | None:
    """A date from an action parameter ("2026-10-21" or a date), or None."""
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return value


def long_date(value: date | str | None) -> str:
    """A date for a message, e.g. "21 Oct 2026"; a placeholder if unknown."""
    value = _as_date(value)
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}" if value else "[DATE]"


def placeholders_in(body: str) -> list[str]:
    """The placeholder names in a text, in order, without duplicates ("[DELIVERY_ADDRESS]" -> "DELIVERY_ADDRESS")."""
    return list(dict.fromkeys(PLACEHOLDER_RE.findall(body)))


# --- Looking up names ----------------------------------------------------------------------


def _supplier_name(supplier_id: str | None, snapshot: BusinessSnapshot) -> str:
    """The supplier's name, or a placeholder."""
    return next((s.name for s in snapshot.suppliers if s.id == supplier_id), "[SUPPLIER_NAME]")


def _items(quantity: int | None, resource_id: str | None, snapshot: BusinessSnapshot) -> str:
    """"20 folding chairs", with placeholders for anything unknown."""
    resource = next((r for r in snapshot.resources if r.id == resource_id), None)
    name = resource.name.lower() if resource else "[ITEM_NAME]"
    return f"{quantity if quantity else '[QUANTITY]'} {name}"


def _signature(snapshot: BusinessSnapshot) -> str:
    """The closing lines: the owner's name (a placeholder) and the business name."""
    return f"Thank you,\n[YOUR_NAME]\n{snapshot.business.name}"


# --- One template per action type ----------------------------------------------------------------


def _order_request(action: RecoveryAction, plan: RecoveryPlan, snapshot: BusinessSnapshot) -> str:
    """source_alternative_supplier: ask the new supplier to confirm an order."""
    p = action.parameters
    body = (f"Hi {_supplier_name(p.get('supplier_id'), snapshot)},\n\n"
            f"We would like to rent {_items(p.get('quantity'), p.get('resource_id'), snapshot)} "
            f"for delivery on {long_date(p.get('expected_arrival_date'))} to [DELIVERY_ADDRESS].")
    if plan.estimated_cost is not None and len(plan.actions) == 1:
        body += f" Our estimate for this order is {fmt_money(plan.estimated_cost)} in total."
    body += " Could you please confirm the availability and the final price?\n\n"
    return body + _signature(snapshot)


def _supplier_request(action: RecoveryAction, incident: NormalizedIncident, snapshot: BusinessSnapshot) -> str:
    """contact_supplier: ask the supplier for something; never state it as agreed."""
    p = action.parameters
    body = f"Hi {_supplier_name(p.get('supplier_id'), snapshot)},\n\n"
    if incident.supplier_id == p.get("supplier_id") and incident.new_arrival_date:
        body += (f"Thank you for letting us know that {_items(incident.quantity_affected, incident.resource_id, snapshot)} "
                 f"will now arrive on {long_date(incident.new_arrival_date)}. ")
    request = str(p.get("request") or "[REQUEST]").strip().rstrip(".")
    body += f"Could you please {request[0].lower() + request[1:]}?"
    requested = _as_date(p.get("requested_date"))
    mentioned = {m.value for m in find_date_mentions(request, incident.reported_at.date())}
    if requested and requested not in mentioned:  # say the date only if the request does not already
        body += f" We would need them by {long_date(requested)}."
    body += " Please let us know whether this is possible.\n\n"
    return body + _signature(snapshot)


def _reschedule_request(action: RecoveryAction, snapshot: BusinessSnapshot) -> str:
    """reschedule_job: propose a new date to the customer; never promise it."""
    p = action.parameters
    job = next((j for j in snapshot.jobs if j.id == p.get("job_id")), None)
    what = f"{job.name} on {long_date(job.event_date)}" if job else "[EVENT] on [DATE]"
    body = (f"Dear [CUSTOMER_NAME],\n\n"
            f"We are writing about {what}. Because of a delay from one of our suppliers, we would like to ask "
            f"whether {long_date(p.get('new_date'))} would work for you instead. "
            f"We are sorry for the inconvenience. Please let us know what suits you.\n\n")
    return body + _signature(snapshot)


def _customer_of(action: RecoveryAction, snapshot: BusinessSnapshot) -> str | None:
    """The customer reference of the job an action reschedules."""
    job = next((j for j in snapshot.jobs if j.id == action.parameters.get("job_id")), None)
    return job.customer_ref if job else None


# --- Public function ----------------------------------------------------------------------------------


def template_drafts(plan: RecoveryPlan, incident: NormalizedIncident, snapshot: BusinessSnapshot) -> list[DraftMessage]:
    """The template drafts for a plan: one per supplier- or customer-facing action, in action order.

    Does not check that the plan is approved; `draft_messages()` (step 4c) does.
    """
    drafts: list[DraftMessage] = []
    for action in plan.actions:
        if action.action_type == ActionType.SOURCE_ALTERNATIVE_SUPPLIER:
            recipient = (RecipientType.SUPPLIER, action.parameters.get("supplier_id"))
            body = _order_request(action, plan, snapshot)
        elif action.action_type == ActionType.CONTACT_SUPPLIER:
            recipient = (RecipientType.SUPPLIER, action.parameters.get("supplier_id"))
            body = _supplier_request(action, incident, snapshot)
        elif action.action_type == ActionType.RESCHEDULE_JOB:
            recipient = (RecipientType.CUSTOMER, _customer_of(action, snapshot))
            body = _reschedule_request(action, snapshot)
        else:
            continue  # internal actions need no message
        drafts.append(DraftMessage(
            id=f"DM-{len(drafts) + 1:03d}", plan_id=plan.id, recipient_type=recipient[0], recipient_id=recipient[1],
            body=body, placeholders=placeholders_in(body), generated_by="template"))
    return drafts
