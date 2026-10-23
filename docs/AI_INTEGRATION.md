# SCDC AI module: integration guide

The AI module (`src/backend/scdc/ai/`, Person 5) turns supplier messages into draft incidents, explains impact
and recovery plans in plain language, and drafts supplier/customer messages. It runs inside Person 2's backend
behind four HTTP endpoints (section 2), and this guide also summarises the safety design for anyone reviewing
the project.

**The rule behind every part:** the AI may *read* and *word* things, never *decide* them. Deterministic code
checks every model output against the business data. Nothing the model writes is shown as a fact unless it is
backed by the data, and every module works with no model at all.

## 1. Quick start

From the repository root (Windows PowerShell; the root `README.md` also shows the `uv` way):

```powershell
py -3.13 -m venv src\backend\.venv
.\src\backend\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest   # no AI library needed
.\src\backend\.venv\Scripts\python.exe -m pytest -q    # 496 backend tests (377 for this module); no network, no key
```

Inside the backend, `app/services/ai.py` calls the module; other Python code can call it directly:

```python
from scdc.ai.config import get_adapter
from scdc.ai.extraction import extract_from_message, extract_incident
from scdc.ai.explanation import explain
from scdc.ai.drafts import draft_messages, DraftNotAllowedError

adapter = get_adapter()            # once at start-up; reads SCDC_AI_* settings (section 6)

result = extract_from_message(incoming, snapshot, adapter=adapter)      # a WhatsApp message (IncomingMessage)
result = extract_incident(message_text, snapshot, reported_at, adapter=adapter)   # just a text
explanation = explain(incident, impact, plans, snapshot=snapshot, adapter=adapter)
drafts = draft_messages(approved_plan, incident, snapshot, adapter=adapter)
```

All three are pure functions: no database, no HTTP, no global state. Inputs and outputs are Pydantic models
from `scdc/ai/schemas.py` (the module's own copies of the `docs/CONTRACTS.md` shapes; P2's `contracts` objects
are converted by `scdc/ai/bridge.py`, see section 9).

## 2. Where it fits in the workflow

```
message ──► extract_incident ──► owner confirms form ──► validate ──► analyze_impact (P3)
                                                                         │
            draft_messages ◄── owner approves a plan ◄── explain ◄── plans + validation (P4)
```

| Function | Endpoint (base `/api/v1`) | Returns | Model calls |
|---|---|---|---|
| `extract_incident` | `POST /disruptions/extract`: a supplier message arrives (optional step; the form also works alone) | `ExtractionResult`: a form **prefill**, never a confirmed incident | 1 |
| `explain` | `GET /disruptions/{id}/explanation`: after the plans are made | `Explanation` (CONTRACTS §6.6) | 1 |
| `draft_messages` | `POST /recovery-plans/{id}/drafts`: after the owner **approves** a plan | `list[DraftMessage]` (CONTRACTS §6.7) | 1 per message |

### HTTP endpoints

Code: `app/routers/ai.py` (endpoints) and `app/services/ai.py` (snapshot, conversion, storage, activity log).
Every endpoint works without a model; errors use P2's format (Problem Details with a `code`).

| Endpoint | Request | Response | Errors and rules |
|---|---|---|---|
| `POST /disruptions/extract` | `{"message": "...", "from_contact": "whatsapp:maju-rental (synthetic)"}` (`from_contact` optional) | `ExtractionResult` | Stores nothing. `from_contact` is matched against `Supplier.contact_reference`. "Tomorrow"/"Friday" are read from the report time (`SCDC_DEMO_NOW` if set, else now in Malaysia) |
| `GET /disruptions/{id}/explanation` | — | `Explanation` | 404 unknown disruption; 409 `INVALID_STATE_TRANSITION` before analysis; 200 once analyzed, also before plans exist. Built fresh on each request |
| `POST /recovery-plans/{id}/drafts` | — (optional `X-User-Id`, for the log) | 201 `{"items": [DraftMessage]}` | 404 unknown plan; 409 `INVALID_STATE_TRANSITION` unless the plan is `approved`. Drafts are stored (`draft_messages` table); asking again returns the same drafts. Logged as `draft_created` |
| `POST /drafts/{id}/approve` | header `X-User-Id` | `DraftMessage` with `status: "approved"` | 401 no or unknown user; 403 not the owner; 404 unknown draft. Approving twice is fine. Logged as `draft_approved`. **Nothing is ever sent** |

## 3. The functions

### `extract_from_message(incoming, snapshot, *, adapter=None) -> ExtractionResult`

For a message as it arrives on WhatsApp. `IncomingMessage` carries everything the channel gives:

| Field | Meaning |
|---|---|
| `text` | the message |
| `received_at` | when it arrived (becomes the report time) |
| `from_number` | the sender's phone, any format: `+60 12-345 6789`, `012-345 6789` and `60123456789` are the same number (Malaysia by default) |
| `contact_name` | the name **the business owner saved** for that number in their WhatsApp contacts, e.g. `"Ali Maju Rental"` (not the sender's own profile name) |
| `from_contact` | optional contact reference, e.g. `"whatsapp:maju-rental (synthetic)"` (the demo's `supplier_message` fits as is) |

The phone number is matched to a supplier's `phone` (**new optional field**, see section 9) and the saved
name to supplier names and aliases (exact, alias or whole word; a close spelling is only a suggestion). If
they point to one supplier, it fills or confirms the supplier; if they point to different suppliers, or the
message names a different supplier, the supplier is left blank as `conflicting` with both suggested. Contact
details are **never sent to the model**. It then works exactly like `extract_incident` below.

### `extract_incident(message, snapshot, reported_at, *, sender=None, from_number=None, contact_name=None, adapter=None) -> ExtractionResult`

| Argument | Meaning |
|---|---|
| `message: str` | the supplier's message, English |
| `snapshot: BusinessSnapshot` | the business records (suppliers, resources, deliveries...) used to resolve names to IDs |
| `reported_at: datetime` | when the message arrived (with time zone); "tomorrow", "Friday" are resolved from it |
| `sender: str \| None` | optional (an addition to CONTRACTS §5; the endpoint's `from_contact`): the sender's contact reference (e.g. `"whatsapp:maju-rental (synthetic)"`). If it equals a supplier's `contact_reference`, it identifies or confirms the supplier |
| `from_number`, `contact_name` | optional (an addition to CONTRACTS §5): the sender's phone and the owner's saved name for it (as in `IncomingMessage`) |
| `adapter` | from `get_adapter()`; `None` = no model (rules only) |

How it works: a rule-based reader and the model both read the message; code combines the two readings field
by field, maps names to IDs, finds the delivery, and checks plausibility (new date after the original date and
not before the report, quantity no larger than the delivery, new date within 60 days). **The model alone can
never fill a field.** An empty message skips the model.

Example (`"Hi, Maju here. The 20 chairs will come next week."`, sent from Maju's contact, no model):

```json
{
  "draft_incident": {
    "type": null, "source": "message", "supplier_id": "S-01", "resource_id": "R-01", "delivery_id": "DL-01",
    "quantity_affected": 20, "original_arrival_date": "2026-10-21", "new_arrival_date": null,
    "description": "Maju Rental Supplies reports that 20 folding chairs will be late (originally due 2026-10-21); new arrival date not confirmed.",
    "reported_at": "2026-10-20T10:15:00+08:00",
    "unresolved_fields": ["...same as below..."]
  },
  "field_evidence": {
    "supplier_id": "found in the message (no AI used); confirmed by sender contact whatsapp:maju-rental (synthetic)",
    "original_arrival_date": "delivery DL-01 due date",
    "delivery_id": "open delivery for this supplier and item"
  },
  "unresolved_fields": [
    {"field": "type", "reason": "missing", "raw_value": null, "candidates": [],
     "note": "could not tell whether items are late or not coming"},
    {"field": "new_arrival_date", "reason": "ambiguous", "raw_value": null, "candidates": [],
     "note": "'next week': vague timing"}
  ],
  "needs_clarification": true,
  "clarification_questions": ["Please confirm the new arrival date: 'next week': vague timing."],
  "generated_by": "template",
  "fallback_used": true,
  "warnings": ["AI model unavailable; the message was read by the rules only."]
}
```

**Never store an `ExtractionResult` as a validated incident.** Show `draft_incident` in the form, highlight
`unresolved_fields` with their `candidates` as suggestions, and let the owner confirm. The confirmed form
becomes the `NormalizedIncident`.

### `explain(incident, impact, plans, *, snapshot=None, adapter=None) -> Explanation`

| Argument | Meaning |
|---|---|
| `incident: NormalizedIncident` | the confirmed incident |
| `impact: ImpactResult` | P3's analysis |
| `plans: list[RecoveryPlan]` | P4's plans **with** their `validation` filled |
| `snapshot` | optional (an addition to CONTRACTS §5; the endpoint always passes it): business records, so texts can say "Cahaya Event Rentals (S-02)" instead of "S-02" |

How it works: code always builds a complete template explanation from the data. The model writes its own
version from the facts; each item (summary, one impact text, one benefit, one limitation) is checked by the
claim checker (section 5) and replaced by the template's item if it fails. `validation_status` is **copied**
from P4, missing confirmations and next steps are **always code-written**, and a non-feasible plan is never
offered for approval.

Example (template, demo data; lists shortened):

```json
{
  "disruption_id": "D-001",
  "summary": "Maju Rental Supplies (S-01) will deliver 20 folding chairs late: originally due 21 Oct, now expected 23 Oct. This affects 5 record(s): R-01, J-01, J-02, CM-01, CM-02. Checked and not affected: J-03, CM-03. 3 recovery plan(s) were checked; feasible: RP-001.",
  "impact_explanations": [
    {"entity_id": "J-01", "text": "Confirmed: Aisyah & Daniel wedding reception (J-01): Shared chair pool short by 20 on 2026-10-22; J-01 requires 50."}
  ],
  "plan_comparisons": [
    {"plan_id": "RP-002", "validation_status": "infeasible",
     "benefits": ["S-03 confirmed 60 available.", "Estimated cost: RM 56.00."],
     "limitations": ["Fails: 3-day lead time; earliest arrival 2026-10-23.", "Fails: 2026-10-23 is after 2026-10-22."]}
  ],
  "missing_confirmations": ["RP-003: confirm that S-01 can expedite the remaining 20 chairs to 2026-10-21."],
  "next_steps": ["Review RP-001 and approve or reject it.",
                 "RP-003 needs confirmation first; it must be validated again before it can be approved.",
                 "Do not use RP-002 as it stands: it failed validation."],
  "generated_by": "template",
  "fallback_used": true,
  "unsupported_claims_removed": 0
}
```

**UI rule (CONTRACTS §6.6):** label the explanation as AI-generated when `generated_by` starts with `model:`.
If no model text survived the checks, `generated_by` is `"template"`.

### `draft_messages(plan, incident, snapshot, *, adapter=None) -> list[DraftMessage]`

Only for plans with `status == "approved"`; otherwise it raises **`DraftNotAllowedError`** (the API should
already refuse with 409). One message per outside-facing action:

| Action | Message |
|---|---|
| `source_alternative_supplier` | to the new supplier: an order request asking them to confirm availability and price |
| `contact_supplier` | to that supplier: the request, always phrased as a question |
| `reschedule_job` | to the job's customer: the new date is **proposed, never promised** |
| `use_spare_inventory`, `reallocate_resource`, `split_allocation` | none (internal) |

Unknown details become placeholders such as `[DELIVERY_ADDRESS]`, `[CUSTOMER_NAME]`, `[YOUR_NAME]`, listed in
`placeholders` so the UI can highlight them. The model may only polish the wording; the polish is used only if
it keeps every placeholder, adds none, states no fact beyond the template's, keeps a question a question, and
adds no commitment words ("confirmed", "guaranteed", "booked"...).

```json
{
  "id": "DM-001", "plan_id": "RP-001", "recipient_type": "supplier", "recipient_id": "S-02",
  "body": "Hi Cahaya Event Rentals,\n\nWe would like to rent 20 folding chairs for delivery on 21 Oct 2026 to [DELIVERY_ADDRESS]. Our estimate for this order is RM 80.00 in total. Could you please confirm the availability and the final price?\n\nThank you,\n[YOUR_NAME]\nSeri Kenanga Events (fictional)",
  "placeholders": ["DELIVERY_ADDRESS", "YOUR_NAME"],
  "status": "draft", "generated_by": "template"
}
```

Drafts are **never sent** by the system. The function numbers each call's drafts `DM-001`, `DM-002`...; the
backend renumbers them when storing, so IDs are unique across the database.

## 4. Uncertainty handling (no confidence scores)

The module does not output confidence numbers. A value is either **filled** (backed by the message and the
records) or **blank with a reason and suggestions**. Reasons (`UnresolvedReason`):

| Reason | Meaning | Example |
|---|---|---|
| `missing` | the message does not say | no quantity given |
| `ambiguous` | it could mean several things | "next week", "next Friday", two items named |
| `unmatched` | it names something not in the records | "Bintang Rentals" |
| `conflicting` | the message, the model, the sender or the records disagree | "three days late" vs "Friday"; model says 40, rules say 20 |
| `unverified` | only the model found it, or it failed a plausibility check | a date 3 months away |

`field_evidence` says where each filled value came from. `needs_clarification` is true when a material field
(supplier, item, quantity, new date) is blank; `clarification_questions` are ready to show.

## 5. Validation of model output

| Layer | What it does |
|---|---|
| Schema | every reply must be exactly one JSON object of the module's shape (`RawExtraction`, `RawExplanation`, `RawDraft`); unknown keys or wrong types reject the **whole** reply |
| Extraction checks | names → IDs via the records; combination table (model alone never fills a field); date / quantity plausibility |
| Claim checker (`claims.py`) | for explanations and drafts: every record ID, number, money amount, date (incl. "Thursday", "tomorrow", "two days late") and business name must be in the facts of *that* item; a plan may not be called feasible / recommended / approvable unless P4 says feasible (negation-aware); no "guaranteed", "no risk"...; an affected record may not be called "not affected" |

A failed reply never raises: it becomes a fallback (section 7).

## 6. Configuration and cost

| Setting | Default | Meaning |
|---|---|---|
| `SCDC_AI_PROVIDER` | `none` | `none` = no model (rules and templates only) or `litellm` |
| `SCDC_AI_MODEL` | | e.g. `anthropic/claude-haiku-5-5` (any LiteLLM model name) |
| `SCDC_AI_API_BASE` | | optional address, e.g. a Replit AI integration's base URL |
| `SCDC_AI_API_KEY` | | optional key; if empty, the provider's usual variable is used (e.g. `ANTHROPIC_API_KEY`) |
| `SCDC_AI_TIMEOUT_S` | 20 | seconds before a call is abandoned |
| `SCDC_AI_MAX_TOKENS` | 1500 | output token limit per call |
| `SCDC_DEMO_NOW` | | optional fixed "now" with an offset, e.g. `2026-10-20T08:00:00+08:00` (the demo day). Used as the report time for extraction, and by the backend for a new disruption's `reported_at` and the snapshot date the impact engine measures from. Empty = the real clock. Audit times (activity log, approvals) always stay real |

- **Where to set them:** on a PC in `src/backend/.env` (git-ignored; copy `src/backend/.env.example`); on Replit
  in **Secrets**. Real environment variables win over `.env`. An invalid setting raises `AIConfigError`.
- **Live provider:** LiteLLM, declared as the optional `llm` group in `src/backend/pyproject.toml` and pinned
  **exactly** to `litellm==1.100.5` (versions 1.82.7 and 1.82.8 were compromised on PyPI in March 2026; upgrade
  only deliberately). Install with `uv sync --extra llm`, or with pip: `pip install "litellm==1.100.5"`. LiteLLM
  is imported only on the first real call; if it cannot load, the module falls back as if the model were down.
- **Cost:** about 1 call per message, 1 per explanation, 1 per draft. Output is capped by
  `SCDC_AI_MAX_TOKENS` (extraction requests ask for at most 600, drafts 500). Every `ModelResponse` carries
  `input_tokens` / `output_tokens` for tracking. No retries (`num_retries=0`).
- **Privacy:** extraction sends only the message and the report date; drafts send only the draft text;
  explanations send the incident, impact and plan facts plus record names, never contact details.

### Deployment on Replit (planned)

The app will be deployed on Replit once all parts are finished, and the live model is planned to come through
**Replit's AI integration** (Claude, billed through Replit; no separate Anthropic key needed).

1. In the Repl, enable the AI integration and note the base URL and key variables it provides.
2. In **Secrets**, set `SCDC_AI_PROVIDER=litellm`, `SCDC_AI_MODEL` (a Claude model it offers), and
   `SCDC_AI_API_BASE` and `SCDC_AI_API_KEY` from those values.
3. Install the pinned LiteLLM: `uv sync --extra llm` (or `pip install "litellm==1.100.5"`).
4. Run the live check there (`python -m scdc.ai.eval.live`, to be added at deployment), which reports
   real-model accuracy, false alarms, latency and tokens.

The integration's key is expected to work only inside the Repl, so live runs happen there; locally the app runs
without a model (or with a developer's own key in `src/backend/.env`).

*To confirm at deployment:* the exact variable names, the models offered, and whether JSON mode
(`response_format`) is passed through.

## 7. Fallback behaviour

The app never depends on a model being available.

| Situation | Extraction | Explanation | Drafts |
|---|---|---|---|
| `SCDC_AI_PROVIDER=none`, no key, LiteLLM missing | rule-based reading | template explanation | template drafts |
| timeout, network or auth error | rules + warning | template | template (per draft) |
| reply is not valid JSON / wrong shape | rules + warning | template | template (per draft) |
| reply valid but some content unsupported | field left blank + suggestion | that item replaced by the template's; `unsupported_claims_removed` counts it | that draft keeps the template text |

Fallback results are marked `generated_by: "template"` and (where the shape has it) `fallback_used: true`.
The only errors raised on purpose are `DraftNotAllowedError` (plan not approved) and `AIConfigError` (bad settings).

## 8. Testing and evaluation

From the repository root. The evaluation commands need the backend folder on Python's path first:
`$env:PYTHONPATH = "src/backend"`.

| Command | What it checks |
|---|---|
| `.\src\backend\.venv\Scripts\python.exe -m pytest -q tests/ai` | 377 unit, endpoint and evaluation tests for this module (`-m pytest -q` alone runs all 496 backend tests); no network, no key |
| `.\src\backend\.venv\Scripts\python.exe -m scdc.ai.eval.extraction` | 24 message cases (incl. WhatsApp contact details), rules-only and with a scripted model: field accuracy, **wrong values filled (must be 0)** |
| `.\src\backend\.venv\Scripts\python.exe -m scdc.ai.eval.explanation` | 20 scripted model replies with planted false claims: **leaks (must be 0)**, false alarms |
| `.\src\backend\.venv\Scripts\python.exe -m scdc.ai.eval.drafts` | 18 scripted polishes: **leaks (must be 0)**, placeholders, approval |

Datasets: `fixtures/ai/`. Results and method: `docs/AI_EVALUATION.md`. The endpoint tests
(`tests/ai/test_endpoints.py`, `tests/ai/test_bridge.py`) run against P2's app with the demo data, and always
replace the model with `NoModelAdapter`, so a key in `.env` can never be used by a test.

## 9. How it is integrated

The module lives in P2's backend (`src/backend/scdc/ai/`, tests in `tests/ai/`, datasets in `fixtures/ai/`)
next to P2's `app/` and `contracts/` and P3's `impact_engine/`.

- **Two sets of shapes, one bridge.** The module keeps its own models (`scdc/ai/schemas.py`): inputs ignore
  unknown keys, outputs forbid them, and a `DraftIncident` may leave every field blank. P2's `contracts` objects
  are converted by `scdc/ai/bridge.py` (`ai_snapshot`, `ai_incident`, `ai_impact`, `ai_plans`) through their JSON
  form. Where P2's contracts allow `None` in text fields (supplier notes, job description, unresolved notes),
  the module reads `""`; a numeric `raw_value` is read as text.
- **Outputs need no conversion.** P2 has no extraction, explanation or draft types, so the endpoints return
  `ExtractionResult`, `Explanation` and `DraftMessage` as they are.
- **Model choice per request.** The adapter is a FastAPI dependency (`get_ai_adapter`), read once from the
  settings; tests replace it.
- **Contract changes made at integration** (P2's `contracts/impact.py`, mirrored here): an `unresolved` affected
  entity has `severity: null`; `ImpactResult` gained the optional `analysis_status` and `data_issues` from P3's
  engine. A failed analysis returns 422 and stores nothing.
- **Demo clock:** `SCDC_DEMO_NOW` (section 6); `app/services/clock.py` gives P2's code the same "now".

Still open:
- **`Supplier.phone`** is not in P2's model or database yet, so matching a message by the sender's phone number
  (`from_number`, `IncomingMessage`) has nothing to compare against. Matching by `from_contact` /
  `contact_reference` and by the owner's saved contact name works.
- **Money in JSON:** the module writes `"80.00"` (2 decimals, rounding half up); P2's format is not fixed
  (CONTRACTS §10.4).
- **Alias learning (later):** when the owner resolves an `unmatched` supplier or item (e.g. "Mr Tan" → Bintang
  Rentals), the app could ask "Remember 'Mr Tan' as Bintang Rentals?" and save it to that record's `aliases`.
  The AI module already reads `aliases`; saving is a database write, so it belongs to P2. No model training.

## 10. Known limitations

- **English only** (dates, numbers, keywords, claim checker). Malay messages mostly fall back to "unresolved".
- **Invented names are only detected with a business word** ("Bintang Rentals" yes, "Mr Tan" no).
- **Phone-number matching is idle** until P2 adds `Supplier.phone` (section 9).
- **Negation is detected by nearby words** (same clause, within 4 words); unusual phrasing can still fool it.
  When it errs towards rejecting, the template text is shown (safe).
- **Strict JSON:** a reply wrapped in a code block is rejected; provider JSON mode is requested to avoid this.
- **No live-model numbers yet:** all evaluations use scripted model replies. The live check runs on Replit at
  deployment (section 6, "Deployment on Replit").
- **Importing LiteLLM needs internet the first time** (tokenizer download); without it, the model counts as
  unavailable and the fallbacks are used.
