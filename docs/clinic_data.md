# Clinic data

Every tenant carries a `clinic_data` JSON document (Postgres `tenants.clinic_data`, JSONB).
It is the **single source of truth** for everything the assistant tells patients — who the
clinic is, what it offers, which doctors work which days, the booking rules, the FAQs — plus
an optional `connector` block that points the booking tools at an external backend.

The agent (`app/prompts.py`) and the booking tools (`app/tools.py`) read this document
directly. The schema is enforced by `app/clinic_schema.py` and edited on the clinic's
**Edit** page (`/admin/tenants/{id}/edit`).

## Schema

```jsonc
{
  "clinic": {                         // REQUIRED object
    "name": "Al-Shifa Family Clinic", // REQUIRED — the assistant's identity
    "address": "Olaya St, Riyadh",
    "phone": "+966-11-234-5678",
    "whatsapp": "+966-50-123-4567",
    "email": "info@clinic.sa",
    "website": "https://clinic.sa",
    "languages": ["Arabic", "English"]
  },

  "services": [                        // list; the assistant quotes price + sets slot length
    { "name": "Dental Checkup",        // REQUIRED
      "price_sar": 250,                // REQUIRED — number
      "duration_min": 30 }             // REQUIRED — whole minutes, sets the booking slot
  ],

  "doctors": [
    { "name": "Dr. Khalid Al-Otaibi",  // REQUIRED
      "specialty": "General Physician",// REQUIRED
      "available_days": ["Sunday","Monday"], // REQUIRED — weekday names
      "available_hours": "5:00 PM - 9:00 PM",// REQUIRED — drives the slot calendar
      "qualifications": "MBBS, SBFM",
      "languages": ["Arabic","English"] }
  ],

  "appointment_policy": {
    "booking_lead_time_hours": 2,      // earliest a patient may book from "now"
    "cancellation_notice_hours": 4,
    "walk_ins_accepted": true,
    "walk_in_note": "Walk-ins welcome; booked patients take priority.",
    "payment_methods": ["Cash","Card","mada","Apple Pay"]
  },

  "faqs": [ { "q": "Do you accept insurance?", "a": "Yes, Bupa, Tawuniya, …" } ],

  // ---- pass-through sections (edited via Advanced JSON; preserved untouched) ----
  "branches":   [ { "name": "...", "city": "Riyadh", "district": "...", "address": "...", "phone": "...", "hours": "..." } ],
  "timings":    { "sunday": "9 AM - 11 PM", "...": "...", "notes": "..." },
  "booking_fields": [ { "key": "insurance", "label": "Insurance provider", "required": false, "options": ["Bupa","Tawuniya"] } ],
  "emergency_guidance": "For chest pain … call 997.",
  "connector":  { "type": "google_calendar | cliniko | custom_erp | fhir", "...": "see docs/connectors.md" }
}
```

**Required fields are required because the tools index them directly** — `s["price_sar"]`,
`d["specialty"]`, `d["available_days"]`, `f["q"]`. A missing one is not a soft degradation;
it raises mid-conversation on a live tool call. That is why the save path validates.

### Validation (`app/clinic_schema.py`)

- `normalize(data)` — best-effort coercion, never raises: numeric strings → numbers
  (`"250"`→`250`), comma-strings → lists (`"Sun, Mon"`→`["Sunday","Monday"]`), weekday
  casing fixed, `"true"`→`true`, fully-empty rows dropped. Unknown/pass-through keys kept.
- `validate(data)` — `(errors, warnings)`. **Errors block the save** (required field
  missing, a type the normalizer couldn't coerce like `price_sar: "free"`). **Warnings never
  block** (no services yet, duplicate names, unrecognised weekday).
- `validate_and_normalize(data)` — the save path's single entry point.

## Management (Edit page)

**Hybrid editor.** Guided forms for `clinic / services / doctors / appointment_policy /
faqs` (add/remove rows, typed inputs, weekday checkboxes) **plus** an `Advanced: raw JSON`
panel. Both bind to one submitted `clinic_data` field: the guided forms write the JSON
continuously; closing the Advanced panel re-syncs the forms from manual edits; whichever
editor is visible at submit wins. The server validates regardless of which path was used —
the UI cannot bypass the schema. The `connector` block is managed on its own Connector page
(structured + secrets encrypted at rest) and is preserved here as pass-through.

## Storage tradeoffs (why one JSONB document)

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **One JSONB doc (current)** | one read per request, atomic edit, trivially multi-tenant, schema can evolve without migrations | no DB-level constraints → **must validate in app**; no cross-tenant queries on services | ✅ chosen — a clinic's config is small and read whole every turn |
| Relational tables (services, doctors, …) | FK integrity, query "all clinics offering X" | many joins per turn, a migration per field, heavier multi-tenant | overkill until we need cross-tenant analytics on catalog data |
| Per-field columns | typed, indexable | rigid; every clinic differs (branches, intake fields) | no — the shape is genuinely variable |

Consequence of JSONB: **validation is the integrity layer**. We validate on **write** (reject
at save) rather than on read, so a bad document can never reach a live conversation, and the
hot path stays a single decode.

### Other deliberate choices
- **Validate on save, not on read.** The agent path never pays validation cost and never has
  to handle a half-valid doc — it was rejected at the door.
- **Normalize-then-store.** We persist the cleaned form, so downstream code sees numbers not
  `"250"`, lists not `"Sun,Mon"`. Loose hand-edited JSON still imports.
- **Pass-through over allow-list.** Unknown keys survive a guided-editor round-trip, so the
  Connector page, `booking_fields`, and future sections don't get clobbered.
- **Warnings ≠ errors.** A brand-new clinic with no doctors yet must be saveable; the agent
  simply has nothing to offer until they're added. Blocking that would be wrong.

## Real-world scenarios

- **New clinic, nothing entered yet.** `clinic.name` is the only hard requirement; empty
  `services`/`doctors` save with warnings. The assistant answers general questions and says
  it can't book until a doctor is added. Fill in over time.
- **Receptionist adds a service** (non-technical). Guided editor → *+ Add service* → name,
  price, minutes → Save. No JSON seen. A price typed as text is rejected with
  `services[i].price_sar: must be a number`, not silently dropped.
- **Bulk import of an existing clinic.** Paste the whole document into *Advanced JSON*; it's
  normalized (string prices coerced, weekdays fixed) and validated on save.
- **Multi-branch group** (Riyadh + Jeddah). `branches[]` (pass-through) feeds the `find_branch`
  tool to route patients by city/district; per-doctor `available_days`/`available_hours` drive
  each doctor's slots regardless of branch.
- **Doctor changes their schedule.** Edit that doctor's weekday checkboxes / hours; the slot
  calendar (`check_availability`) reflects it immediately — no booking-engine change.
- **Insurance / parking / refill questions.** Put them in `faqs`; the `get_faqs` tool serves
  them verbatim so the assistant never invents a policy.
- **Connector-backed clinic** (Cliniko/Calendar/FHIR). Availability and bookings come from the
  external system, but `services`, `doctors`, `faqs`, and `appointment_policy` still live here
  — that local data is what keeps the AI features (no-show risk, insights, reviews) working.
  See [connectors.md](connectors.md).
- **Required intake fields** (e.g. insurance provider, national ID). Add `booking_fields[]`
  (pass-through); `book_appointment` enforces required ones and validates `options` before
  confirming.
- **A malformed paste** (`service` instead of `services`, trailing comma, price `"free"`).
  Save is rejected with a precise field list; nothing is persisted; the patient-facing config
  is never left in a broken state.

## Tests

`tests/test_clinic_schema.py` covers required-field errors, coercion, empty-row dropping,
pass-through preservation, warnings, and that the shipped `app/clinic_data.json` satisfies its
own schema. The admin save path (validate-on-save, warnings surfaced) is covered alongside the
tenant-edit tests.
