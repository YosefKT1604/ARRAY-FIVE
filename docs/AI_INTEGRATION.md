# SCDC AI module: integration guide

The AI module (`backend/scdc/ai/`, Person 5) turns supplier messages into draft incidents, explains impact and
recovery plans in plain language, and drafts supplier/customer messages. It is written for the backend
(Person 2), and summarises the safety design for anyone reviewing the project.

**The rule behind every part:** the AI may *read* and *word* things, never *decide* them. Deterministic code
checks every model output against the business data. Nothing the model writes is shown as a fact unless it is
backed by the data, and every module works with no model at all.

## 1. Quick start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"        # no AI library needed
.\.venv\Scripts\python.exe -m pytest -q                       # 355 tests, no network, no API key
```

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
from `scdc/ai/schemas.py` (local copies of `docs/CONTRACTS.md`; see section 9).

## 2. Where it fits in the workflow

```
message ──► extract_incident ──► owner confirms form ──► validate ──► analyze_impact (P3)
                                                                         │
            draft_messages ◄── owner approves a plan ◄── explain ◄── plans + validation (P4)
```

| Function | Called when | Returns | Model calls |
|---|---|---|---|
| `extract_incident` | a supplier message arrives (optional step; the form also works alone) | `ExtractionResult`: a form **prefill**, never a confirmed incident | 1 |
| `explain` | after P4 has validated and ranked the plans | `Explanation` (CONTRACTS §6.6) | 1 |
| `draft_messages` | after the owner **approves** a plan | `list[DraftMessage]` (CONTRACTS §6.7) | 1 per message |

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
| `sender: str \| None` | **new, optional**: the sender's contact reference (e.g. `"whatsapp:maju-rental (synthetic)"`). If it equals a supplier's `contact_reference`, it identifies or confirms the supplier |
| `from_number`, `contact_name` | **new, optional**: the sender's phone and the owner's saved name for it (as in `IncomingMessage`) |
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
| `snapshot` | **new, optional**: business records, so texts can say "Cahaya Event Rentals (S-02)" instead of "S-02" |

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

Drafts are **never sent** by the system. IDs are numbered `DM-001`, `DM-002`... per call; renumber when storing
if needed.

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

- **Where to set them:** on a PC in `backend/.env` (git-ignored; copy `backend/.env.example`); on Replit in
  **Secrets**. Real environment variables win over `.env`. An invalid setting raises `AIConfigError` at start-up.
- **Live provider:** LiteLLM, optional extra `pip install -e ".[llm]"`, pinned **exactly** to `litellm==1.100.5`
  (versions 1.82.7 and 1.82.8 were compromised on PyPI in March 2026; upgrade only deliberately). LiteLLM is
  imported only on the first real call; if it cannot load, the module falls back as if the model were down.
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
3. Install with `pip install -e ".[llm]"` (the pinned LiteLLM).
4. Run the live check there (`python -m scdc.ai.eval.live`, to be added at deployment), which reports
   real-model accuracy, false alarms, latency and tokens.

The integration's key is expected to work only inside the Repl, so live runs happen there; locally the app runs
without a model (or with a developer's own key in `backend/.env`).

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

From `backend/`:

| Command | What it checks |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` | 355 unit and evaluation tests; no network, no key |
| `.\.venv\Scripts\python.exe -m scdc.ai.eval.extraction` | 24 message cases (incl. WhatsApp contact details), rules-only and with a scripted model: field accuracy, **wrong values filled (must be 0)** |
| `.\.venv\Scripts\python.exe -m scdc.ai.eval.explanation` | 20 scripted model replies with planted false claims: **leaks (must be 0)**, false alarms |
| `.\.venv\Scripts\python.exe -m scdc.ai.eval.drafts` | 18 scripted polishes: **leaks (must be 0)**, placeholders, approval |

Datasets: `fixtures/ai/`. Results and method: `docs/AI_EVALUATION.md`.

## 9. Integration with Person 2: what to align

The AI module currently uses **local copies** of the shared shapes (`scdc/ai/schemas.py`). At integration these
are swapped for imports from P2's `contracts` package. Known differences:

| Topic | AI module | P2 (`src/backend/contracts/`) | Proposal |
|---|---|---|---|
| Draft incident | `DraftIncident`: every field may be blank (type, description, reported_at too) | `NormalizedIncident` requires `type`, `description`, `reported_at` | keep a separate draft shape for prefill; only the confirmed form becomes a `NormalizedIncident` |
| `ExtractionResult` | defined here (§6.2) | not defined | P5 owns it; P2 imports it |
| Extra keys | inputs ignore unknown keys, outputs forbid them | everything forbids extra keys | fine either way; inputs must then match exactly |
| Money in JSON | 2-decimal string, `"80.00"`, rounding half up | `Decimal`, format not fixed (§10.4) | agree on `"80.00"` |
| Layout | `backend/scdc/ai/`, imports `scdc.ai...` | `src/backend/`, imports `contracts...`, Python ≥ 3.13, uv | move `scdc/ai` under P2's layout; change imports only |

New optional inputs that need P2's agreement:
- **`Supplier.phone`** (optional): the supplier's WhatsApp number, so a message can be matched by number.
- `extract_from_message(IncomingMessage(...))`: pass the WhatsApp number and the owner's saved contact name
  (or `extract_incident(..., sender=..., from_number=..., contact_name=...)`).
- `explain(..., snapshot=...)`: pass the snapshot so explanations use names.
- **Alias learning (later):** when the owner resolves an `unmatched` supplier or item (e.g. "Mr Tan" → Bintang
  Rentals), the app could ask "Remember 'Mr Tan' as Bintang Rentals?" and save it to that record's `aliases`.
  The AI module already reads `aliases`; saving is a database write, so it belongs to P2. No model training.

## 10. Known limitations

- **English only** (dates, numbers, keywords, claim checker). Malay messages mostly fall back to "unresolved".
- **Invented names are only detected with a business word** ("Bintang Rentals" yes, "Mr Tan" no).
- **Negation is detected by nearby words** (same clause, within 4 words); unusual phrasing can still fool it.
  When it errs towards rejecting, the template text is shown (safe).
- **Strict JSON:** a reply wrapped in a code block is rejected; provider JSON mode is requested to avoid this.
- **No live-model numbers yet:** all evaluations use scripted model replies. The live check runs on Replit at
  deployment (section 6, "Deployment on Replit").
- **Importing LiteLLM needs internet the first time** (tokenizer download); without it, the model counts as
  unavailable and the fallbacks are used.
