# Integration gaps: frontend (P1) vs backend (P2)

Audited from branch `backend` at commit `6ec6ca2` ("Add approve and reject endpoints for recovery plans"), 22 Oct 2026.
`docs/CONTRACTS.md` and `fixtures/demo/*.json` on `backend` are identical to the copies on `p1-frontend`.

## How to run the backend locally
- Python **3.13** is required (`pyproject.toml`, `.python-version`). The project uses **uv**.
- From `src/backend`: `uv sync`, then `uv run python -m app.db.seed` (creates `orbyte.db` and loads `fixtures/demo/seed.json`), then `uv run uvicorn app.main:app --reload --port 8000`.
- `main.py` doesn't create tables, so **the seed must run before first start**. Re-running the seed **resets the whole demo** (it drops all tables).
- No CORS middleware. The frontend uses the Vite dev proxy (`/api` → `http://localhost:8000`), so this is fine for development.

## Endpoint status (CONTRACTS.md §7)

| Endpoint | Built? | Differences / notes | What the UI does |
|---|---|---|---|
| GET `/api/v1/health` | ✅ (extra) | Not in the contract. Returns `{"status":"ok"}` | Use it for the "backend connected" badge |
| GET `/jobs`, `/resources`, `/dependencies`, `/deliveries` | ✅ | `{"items": [...]}` as specified | Real |
| GET `/suppliers` | ✅ | Embeds `offerings`, as specified | Real |
| GET `/dashboard` | ❌ | — | Hybrid: **compose it client-side** from `/jobs` + `/disruptions` + `/disruptions/{id}/recovery-plans` |
| POST `/disruptions/extract` | ❌ | Depends on P5. ⚠️ The contract request is `{message}` only, but the demo WhatsApp message never names the supplier (it arrives from Maju's number). **Agreed request: `{message, from_contact}`**, where `from_contact` matches `Supplier.contact_reference` (e.g. `whatsapp:maju-rental (synthetic)`). **Ask P5/P2** to accept it | Mock (keyword rules plus `from_contact` lookup; sends `{message, from_contact}`) |
| POST `/disruptions` | ✅ partly | Returns 201 `{disruption, incident, validation_errors}`. **No duplicate detection** (no 409 `DUPLICATE_DISRUPTION`). `validation_errors` is always `[]`. Status is always `received`, never `needs_clarification`. `client_request_id` is accepted but ignored | Real; the duplicate demo stays mock-only until P2 adds it |
| GET `/disruptions`, `/disruptions/{id}` | ✅ | — | Real |
| POST `/disruptions/{id}/analyze` | ✅ (stub) | Returns `expected_impact.json` for **any** incident (P3's engine not wired in yet). Allowed from status `received` | Real |
| GET `/disruptions/{id}/impact` | ✅ | 404 if not analyzed yet | Real |
| POST / GET `/disruptions/{id}/recovery-plans` | ✅ (stub) | Returns the 3 fixture plans with **new IDs** (`RP-001…` numbering continues across disruptions). POST returns **201** and needs status `analyzed` (else 409) | Real. **Never hard-code `RP-001`**; use the IDs returned |
| GET `/disruptions/{id}/explanation` | ❌ | Depends on P5 | Mock: template text assembled from the real plans (labelled "Demo only"); it never sets a status |
| GET `/recovery-plans/{id}` | ✅ | — | Real |
| PUT `/recovery-plans/{id}` (edit → new version) | ❌ | — | Mock, labelled "Demo only". Replays the fixture edit (20 → 10 chairs → infeasible, `QUANTITY_SUFFICIENT`, short 10); any other edit returns `needs_confirmation` ("Mock mode cannot validate this edit"). ⚠️ In hybrid mode the edited version exists only in the mock: reads, approve and reject of that plan are answered by the mock too (the real backend would return 409 stale version) |
| POST `/recovery-plans/{id}/revalidate` | ❌ | — | Mock ("Demo only"): returns the plan with a fresh `validated_at`; no validation is computed |
| POST `/recovery-plans/{id}/approve` | ✅ | Body `{plan_version, comments}`. Returns **201** `Approval`. 403 non-owner, 409 wrong version, 409 already decided, 409 infeasible. **`needs_confirmation` CAN be approved** (matches §10 decision #2). Sets the disruption to `decided` | Real |
| POST `/recovery-plans/{id}/reject` | ✅ | Same as approve | Real |
| POST `/recovery-plans/{id}/request-info` | ✅ | Allowed on `proposed` and `more_info_requested` plans; owner only (403 is logged as `approval_denied`) | Real (mock only in `mock` mode). A plan that asked for info can still be approved or rejected |
| POST `/recovery-plans/{id}/drafts`, POST `/drafts/{id}/approve` | ❌ | Depends on P5 | Mock |
| GET `/disruptions/{id}/activity-log` | ✅ | Entries `{id (LOG-0001), disruption_id, plan_id, actor_id, activity_type, details, created_at}` | Real. In hybrid mode, demo-only events (edits, drafts, mock decisions) are added on top and flagged "Demo only" |

## Cross-cutting differences

1. **Error format ≠ §8 (still).** The backend returns RFC 9457 Problem Details with an added `code`: `{type, title, status, detail, instance, code, errors?}`. §8 says `{"error": {code, message, details, request_id}}`. → The frontend parser accepts **both** shapes. 422 `errors[].loc` is mapped to form fields.
2. **Error `code` is now sent (done by P2).** The UI uses it and no longer guesses from the detail text. Differences from §8: **401 is `UNAUTHORIZED`** (§8 says `UNAUTHENTICATED`), and "plan already decided" is `INVALID_STATE_TRANSITION` (409; there is no `PLAN_ALREADY_DECIDED`). The UI reads the plan status from the detail text only to word the message ("Someone has already approved this plan"). The duplicate 409 (`DUPLICATE_DISRUPTION`) names the existing disruption only inside `detail`, not as a field.
3. **Auth:** header `X-User-Id` (`U-01` owner, `U-02` staff). A missing or unknown user gets **401** (not in the contract), but only on endpoints that need a user (currently approve and reject). Read endpoints such as `/jobs` work with no header (verified 22 Oct 2026). → The UI always sends the header from the user switcher and handles 401.
4. **IDs** are generated by counting rows (`D-001`, `RP-004`…), so they change after a reseed. Don't hard-code them.
5. **Plan validation timestamps:** `validation.validated_at` is missing in the fixture plans (the type allows it). The UI shows it only when present.
6. **Timestamps** are returned in UTC. The UI converts them to `Asia/Kuala_Lumpur` for display.

## Asks for P2 (priority order)
1. `approval_denied` log entries only record `{role}`. Please also record the attempted action (`approve` / `reject` / `request-info`) in `details`, so the log can say "Hafiz tried to approve…" exactly.
2. `PUT /recovery-plans/{id}` and `/revalidate`, for the edit demo (needs P4's `validate_plan`). Until then the frontend mocks them ("Demo only").
3. Optional: `GET /dashboard` (the frontend composes it from `/jobs`, `/disruptions` and `/recovery-plans`).
4. Duplicate 409: add the existing disruption id as a field (e.g. `existing_id`) so the UI can link to it.
5. Later, with P5: `/disruptions/extract`, `/explanation`, `/drafts` and `/drafts/{id}/approve`.

**Still mocked (see `src/mocks/missing-endpoints.ts`):** extract, explanation, PUT edit, revalidate, drafts, draft approve. **Now real:** activity-log, request-info, duplicate-report 409, error `code`, auto-seed on startup.
