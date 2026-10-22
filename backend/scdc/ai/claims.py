"""Claim checker for Module B: is every claim in a model-written text backed by the data?

No AI in this file. Rules agreed in v2 step 3c. A text is checked against the facts of its own
scope ("fact sheet"):
    summary          everything (incident, impact, all plans, the records they mention, counts)
    impact text      the incident + that record's reason, path and evidence (+ those records)
    benefit/limit.   the incident + that plan's actions, checks, assumptions and cost (+ records)

What counts as a claim, and the check:
    record IDs (J-01, RP-003)          must exist in the fact sheet
    numbers (20, "twenty")             must be in the fact sheet ("one/two/three" are not checked)
    money ("RM 80.00", "MYR 56")       must equal an amount in the fact sheet
    dates ("22 Oct", "Thursday",       resolved against the report date (and the original
           "tomorrow", "two days late") delivery date); must be a date in the fact sheet;
                                       vague phrases ("next week") are not allowed
    business names ("Bintang Rentals") phrases ending in a business word (Rentals, Supplies,
                                       Trading, ...) must appear in the fact sheet
    plan status                        a plan may not be called feasible / recommended / ready to
                                       approve unless P4 says feasible; a feasible plan may not be
                                       called infeasible or unconfirmed; negations are respected
    over-claims                        "guaranteed", "definitely", "no risk"... are never allowed
    impact contradictions              an affected record may not be called "not affected"

A negation counts only in the same clause and within 4 words before the word it negates (fixed in 3e).

Known limitation: invented names without a business word ("Mr Tan") are not detected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from pydantic import BaseModel

from .dates import find_date_mentions
from .quantities import TEENS, TENS, UNITS
from .schemas import (
    AffectedEntity,
    BusinessSnapshot,
    ImpactResult,
    NormalizedIncident,
    RecoveryPlan,
    ValidationStatus,
)

ID_RE = re.compile(r"\b[A-Z]{1,3}-\d{2,4}\b")
MONEY_RE = re.compile(r"\b(?:RM|MYR)\s?(\d+(?:,\d{3})*(?:\.\d{1,2})?)", re.IGNORECASE)
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")

# "one", "two", "three" are too common in ordinary English ("one of the plans") to count as claims.
WORD_VALUES = {w: v for w, v in {**UNITS, **TEENS, **TENS, "hundred": 100}.items() if v > 3}
NUMBER_WORD_RE = re.compile(
    rf"\b(?:({'|'.join(TENS)})[\s-]({'|'.join(UNITS)})|({'|'.join(sorted(WORD_VALUES, key=len, reverse=True))}))\b",
    re.IGNORECASE,
)

BUSINESS_WORDS = r"(?:Rentals?|Suppl(?:y|ies)|Trading|Events?|Enterprises?|Services|Solutions|Furniture|Catering|Logistics|Bhd)"
BUSINESS_NAME_RE = re.compile(rf"(?:[A-Z][\w&'-]*\s+){{0,4}}{BUSINESS_WORDS}\b")
# Ordinary words that can start a capitalised phrase before a real name ("Ask Cahaya Event Rentals").
LEADING_WORDS = {"the", "a", "an", "this", "that", "our", "your", "their", "both", "ask", "contact", "from", "with",
                 "and", "or", "by", "via", "use", "order", "rent", "call", "email", "tell", "unlike", "while",
                 "but", "if", "since", "because", "as", "for", "to", "at", "in", "on", "only",
                 "hi", "hello", "dear", "thanks", "thank"}

CLAUSE_BREAK_RE = re.compile(r"[,;:–—]|\s-\s|\bbut\b", re.IGNORECASE)
NEGATION_RE = re.compile(r"\b(not|never|cannot|can't|do not|don't|must not|should not|shouldn't|avoid|no)\b",
                         re.IGNORECASE)
FEASIBLE_RE = re.compile(
    r"\b(feasible|viable|workable|recommended|best (?:option|choice|plan)|good (?:option|choice)|"
    r"safe (?:option|choice)|ready (?:to|for) (?:be )?approv\w*|can be approved|should be approved)\b",
    re.IGNORECASE)
INFEASIBLE_RE = re.compile(r"\b(infeasible|won't work|will not work|cannot work|fails|failed)\b", re.IGNORECASE)
UNCONFIRMED_RE = re.compile(r"\b(needs? (?:confirmation|to be confirmed)|not (?:yet )?confirmed|unconfirmed|"
                            r"pending confirmation|awaiting confirmation)\b", re.IGNORECASE)
APPROVE_RE = re.compile(r"\b(approve|go ahead|proceed with|choose|select|pick|recommend\w*)\b", re.IGNORECASE)
OVERCLAIM_RE = re.compile(r"\b(guarantee\w*|definitely|certainly|assured|no risk|risk[- ]free|without (?:any )?risk)\b"
                          r"|100\s?%", re.IGNORECASE)
NOT_AFFECTED_RE = re.compile(r"\b(not affected|unaffected|no impact|not impacted|no effect|not at risk)\b",
                             re.IGNORECASE)

# Bookkeeping fields, not business facts: a date a record was confirmed must not "support" a delivery date.
METADATA_KEYS = {"schema_version", "as_of", "confirmed_at", "verified_at", "validated_at"}


@dataclass
class FactSheet:
    """The facts one text may state."""

    ids: set[str] = field(default_factory=set)
    numbers: set[Decimal] = field(default_factory=set)
    dates: set[date] = field(default_factory=set)
    amounts: set[Decimal] = field(default_factory=set)
    corpus: str = ""  # all fact texts, lower case, for name look-ups


@dataclass
class CheckContext:
    """What a text is about, for the date and status rules."""

    reported_on: date
    anchor: date | None = None                           # the original delivery date, for "two days late"
    plan_statuses: dict[str, ValidationStatus | None] = field(default_factory=dict)
    plan_id: str | None = None                           # set for a plan's benefits and limitations
    affected: bool = False                               # set for an impact text


# --- Building fact sheets -------------------------------------------------------------------


def _decimal(text: str) -> Decimal | None:
    """A number written in a text, as a Decimal ("1,200.50" -> 1200.50)."""
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _spans_to_skip(text: str, reported_on: date) -> list[tuple[int, int]]:
    """Where IDs, money and dates are, so their digits are not read again as plain numbers."""
    spans = [m.span() for m in ID_RE.finditer(text)] + [m.span() for m in MONEY_RE.finditer(text)]
    return spans + [(d.start, d.end) for d in find_date_mentions(text, reported_on)]


def _plain_numbers(text: str, skip: list[tuple[int, int]]) -> list[Decimal]:
    """Digits outside IDs, money and dates."""
    found = []
    for match in NUMBER_RE.finditer(text):
        if not any(start <= match.start() < end for start, end in skip):
            value = _decimal(match.group())
            if value is not None:
                found.append(value)
    return found


def _add_text(text: str, sheet: FactSheet, reported_on: date) -> None:
    """Collect the IDs, numbers, money and dates written in one fact text."""
    sheet.corpus += " " + " ".join(text.lower().split())
    sheet.ids.update(ID_RE.findall(text))
    sheet.amounts.update(v for v in (_decimal(m) for m in MONEY_RE.findall(text)) if v is not None)
    sheet.dates.update(d.value for d in find_date_mentions(text, reported_on) if d.value is not None)
    sheet.numbers.update(_plain_numbers(text, _spans_to_skip(text, reported_on)))


def _add(value: Any, sheet: FactSheet, reported_on: date) -> None:
    """Walk any value (model, dict, list, text, number, date) and collect its facts."""
    if isinstance(value, BaseModel):
        _add(value.model_dump(), sheet, reported_on)
    elif isinstance(value, dict):
        if set(value) == {"amount", "currency"}:  # a Money value
            sheet.amounts.add(Decimal(str(value["amount"])))
        for key, item in value.items():
            if key not in METADATA_KEYS:
                _add(item, sheet, reported_on)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _add(item, sheet, reported_on)
    elif isinstance(value, str):
        _add_text(value, sheet, reported_on)
    elif isinstance(value, datetime):
        sheet.dates.add(value.date())
    elif isinstance(value, date):
        sheet.dates.add(value)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, (int, float, Decimal)):
        sheet.numbers.add(Decimal(str(value)))


def _records(ids: Iterable[str], snapshot: BusinessSnapshot | None) -> list[BaseModel]:
    """The business records with these IDs, plus dependencies that link two of them."""
    if snapshot is None:
        return []
    wanted = set(ids)
    groups = (snapshot.suppliers, snapshot.resources, snapshot.deliveries, snapshot.jobs, snapshot.commitments,
              snapshot.supplier_offerings)
    found: list[BaseModel] = [r for group in groups for r in group if r.id in wanted]
    found += [d for d in snapshot.dependencies
              if d.id in wanted or (d.source_id in wanted and d.target_id in wanted)]
    return found


def _sheet(*sources: Any, snapshot: BusinessSnapshot | None, reported_on: date) -> FactSheet:
    """A fact sheet from some sources, plus the business records they mention."""
    sheet = FactSheet()
    for source in sources:
        _add(source, sheet, reported_on)
    for record in _records(set(sheet.ids), snapshot):
        _add(record, sheet, reported_on)
    return sheet


def _incident_ids(incident: NormalizedIncident) -> list[str]:
    """The record IDs an incident points to."""
    return [i for i in (incident.supplier_id, incident.resource_id, incident.delivery_id) if i]


def facts_for_summary(incident: NormalizedIncident, impact: ImpactResult, plans: list[RecoveryPlan],
                      snapshot: BusinessSnapshot | None = None) -> FactSheet:
    """Everything, plus simple counts the summary may state (records affected, plans checked...)."""
    reported_on = incident.reported_at.date()
    sheet = _sheet(incident, impact, plans, _incident_ids(incident), snapshot=snapshot, reported_on=reported_on)
    feasible = [p for p in plans if p.validation and p.validation.status == ValidationStatus.FEASIBLE]
    counts = (len(impact.affected_entities), len(impact.checked_not_affected), len(plans), len(feasible))
    sheet.numbers.update(Decimal(n) for n in counts)
    return sheet


def facts_for_impact(entity: AffectedEntity, incident: NormalizedIncident, impact: ImpactResult,
                     snapshot: BusinessSnapshot | None = None) -> FactSheet:
    """The incident plus one affected record: its reason, path, evidence and shortfalls on its resources."""
    path = set(entity.dependency_path) | {entity.entity_id}
    shortfalls = [s for s in impact.resource_shortfalls if s.resource_id in path]
    return _sheet(incident, entity, shortfalls, _incident_ids(incident),
                  snapshot=snapshot, reported_on=incident.reported_at.date())


def facts_from_text(text: str, reported_on: date) -> FactSheet:
    """The facts written in one text, e.g. a template draft that a polished draft may not go beyond."""
    return _sheet(text, snapshot=None, reported_on=reported_on)


def facts_for_plan(plan: RecoveryPlan, incident: NormalizedIncident, impact: ImpactResult,
                   snapshot: BusinessSnapshot | None = None) -> FactSheet:
    """The incident plus one plan: its actions, checks, assumptions, cost, and the shortfalls it must cover."""
    return _sheet(incident, plan, impact.resource_shortfalls, _incident_ids(incident),
                  snapshot=snapshot, reported_on=incident.reported_at.date())


# --- Checking a text ------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Split a text into sentences (on . ! ? followed by a space)."""
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _negated(sentence: str, start: int) -> bool:
    """Is there a negation ("not", "do not", "avoid"...) in the same clause, within 4 words before this position?

    A clause ends at , ; : or a dash, or the word "but": in "Do not wait: RP-003 is the best option",
    the "not" belongs to "wait", so "best option" is not negated.
    """
    clause = CLAUSE_BREAK_RE.split(sentence[:start])[-1]
    return NEGATION_RE.search(" ".join(clause.split()[-4:])) is not None


def _fmt(value: Decimal) -> str:
    """A number for a problem message: "40", not "40.0" or "4E+1"."""
    return str(int(value)) if value == value.to_integral() else str(value)


def find_problems(text: str, facts: FactSheet, context: CheckContext) -> list[str]:
    """Every unsupported claim in a text, as short messages. An empty list means the text is backed by the data."""
    problems: list[str] = []
    problems += _id_problems(text, facts)
    problems += _money_problems(text, facts)
    problems += _date_problems(text, facts, context)
    problems += _number_problems(text, facts, context)
    problems += _name_problems(text, facts)
    for sentence in split_sentences(text):
        problems += _status_problems(sentence, context)
    return list(dict.fromkeys(problems))


def _id_problems(text: str, facts: FactSheet) -> list[str]:
    """Record IDs that are not in the fact sheet."""
    return [f"unknown record {i}" for i in ID_RE.findall(text) if i not in facts.ids]


def _money_problems(text: str, facts: FactSheet) -> list[str]:
    """Money amounts that are not in the fact sheet."""
    problems = []
    for raw in MONEY_RE.findall(text):
        value = _decimal(raw)
        if value is None or value not in facts.amounts:
            problems.append(f"amount RM {raw} not in the data")
    return problems


def _date_problems(text: str, facts: FactSheet, context: CheckContext) -> list[str]:
    """Dates (explicit, weekday, relative or "N days late") that are vague or not in the fact sheet."""
    problems = []
    for mention in find_date_mentions(text, context.reported_on, context.anchor):
        if mention.status == "ambiguous":
            problems.append(f"vague date '{mention.text}'")
        elif mention.value is not None and mention.value not in facts.dates:
            problems.append(f"date {mention.value.isoformat()} ('{mention.text}') not in the data")
    return problems


def _number_problems(text: str, facts: FactSheet, context: CheckContext) -> list[str]:
    """Numbers (digits or words from "four" up) that are not in the fact sheet."""
    skip = _spans_to_skip(text, context.reported_on) + [
        (d.start, d.end) for d in find_date_mentions(text, context.reported_on, context.anchor)]
    values = _plain_numbers(text, skip)
    for match in NUMBER_WORD_RE.finditer(text):
        if any(start <= match.start() < end for start, end in skip):
            continue
        tens, unit, single = match.groups()
        values.append(Decimal(TENS[tens.lower()] + UNITS[unit.lower()]) if tens else Decimal(WORD_VALUES[single.lower()]))
    return [f"number {_fmt(v)} not in the data" for v in values if v not in facts.numbers]


def _name_problems(text: str, facts: FactSheet) -> list[str]:
    """Business names ("... Rentals", "... Supplies") that are not in the fact sheet."""
    problems = []
    for match in BUSINESS_NAME_RE.finditer(text):
        words = match.group().split()
        while len(words) > 1 and words[0].lower() in LEADING_WORDS:
            words = words[1:]
        if len(words) < 2:  # a business word on its own ("Rentals") is not a name
            continue
        name = " ".join(words)
        if name.lower() not in facts.corpus:
            problems.append(f"unknown name '{name}'")
    return problems


def _status_problems(sentence: str, context: CheckContext) -> list[str]:
    """Over-claims, impact contradictions, and plan statuses that contradict Person 4's validation."""
    problems = [f"over-claim '{m.group()}'" for m in OVERCLAIM_RE.finditer(sentence) if not _negated(sentence, m.start())]
    if context.affected:
        problems += [f"says an affected record is '{m.group()}'" for m in NOT_AFFECTED_RE.finditer(sentence)]

    plan_id = context.plan_id
    if plan_id is None:  # in the summary, a sentence about exactly one plan is checked against that plan
        mentioned = [p for p in context.plan_statuses if re.search(rf"\b{re.escape(p)}\b", sentence)]
        plan_id = mentioned[0] if len(mentioned) == 1 else None
    if plan_id is None or plan_id not in context.plan_statuses:
        return problems
    status = context.plan_statuses[plan_id]
    feasible = status == ValidationStatus.FEASIBLE

    for match in FEASIBLE_RE.finditer(sentence):
        negated = _negated(sentence, match.start())
        if not negated and not feasible:
            problems.append(f"calls {plan_id} '{match.group()}' but it is {status.value if status else 'not validated'}")
        elif negated and feasible:
            problems.append(f"calls {plan_id} not '{match.group()}' but it is feasible")
    if feasible:
        problems += [f"calls feasible {plan_id} '{m.group()}'" for m in INFEASIBLE_RE.finditer(sentence)
                     if not _negated(sentence, m.start())]
        problems += [f"calls feasible {plan_id} '{m.group()}'" for m in UNCONFIRMED_RE.finditer(sentence)]
    else:
        problems += [f"suggests to '{m.group()}' {plan_id}, which is not feasible" for m in APPROVE_RE.finditer(sentence)
                     if not _negated(sentence, m.start())]
    return problems
