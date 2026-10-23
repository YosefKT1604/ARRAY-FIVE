"""Turn raw JSON-like dicts into a BusinessSnapshot, one record at a time.

A bad record is rejected and reported as a DataIssue; it never crashes the whole
analysis. (Person 2's database layer can build a BusinessSnapshot directly; this
is for fixtures, tests and any raw-row path.)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, TypeAdapter, ValidationError
from datetime import datetime

from .models import (
    BusinessSnapshot,
    Commitment,
    DataIssue,
    Delivery,
    Dependency,
    IssueCode,
    IssueSeverity,
    Job,
    Resource,
    Supplier,
)

_COLLECTIONS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("suppliers", Supplier),
    ("resources", Resource),
    ("deliveries", Delivery),
    ("jobs", Job),
    ("commitments", Commitment),
    ("dependencies", Dependency),
)


def summarise(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'record'}: {err['msg']}" for err in exc.errors()
    )


def snapshot_from_raw(raw: Mapping[str, Any]) -> BusinessSnapshot:
    parsed: dict[str, list[Any]] = {}
    issues: list[DataIssue] = []
    for key, model in _COLLECTIONS:
        parsed[key] = []
        records = raw.get(key) or []
        if not isinstance(records, list):
            issues.append(DataIssue(code=IssueCode.INVALID_RECORD, severity=IssueSeverity.ERROR,
                                    message=f"'{key}' must be a list; ignored."))
            continue
        for index, record in enumerate(records):
            try:
                parsed[key].append(model.model_validate(record))
            except ValidationError as exc:
                rid = record.get("id") if isinstance(record, Mapping) else None
                issues.append(DataIssue(code=IssueCode.INVALID_RECORD, severity=IssueSeverity.ERROR,
                                        entity_id=str(rid) if rid else None,
                                        message=f"{key}[{index}] rejected: {summarise(exc)}"))
    as_of = None
    if raw.get("as_of") is not None:
        try:
            as_of = TypeAdapter(datetime).validate_python(raw["as_of"])
        except ValidationError:
            issues.append(DataIssue(code=IssueCode.INVALID_RECORD, severity=IssueSeverity.ERROR,
                                    message=f"as_of {raw['as_of']!r} is not a valid timestamp."))
    stale = raw.get("missing_or_stale") or []
    return BusinessSnapshot(
        schema_version=str(raw.get("schema_version", "1.0")),
        as_of=as_of,
        missing_or_stale=list(stale) if isinstance(stale, list) else [stale],
        issues=issues,
        **parsed,
    )


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
