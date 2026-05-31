# Clinic connector layer

The agent never talks to an appointment backend directly. It goes through a per-tenant
`ClinicConnector` (`app/connectors.py`). Today every tenant uses `NativeConnector` (our
Postgres is the system of record); the layer exists so a tenant can instead be backed by
Cliniko, Google Calendar, a custom ERP, a dental PMS, or a hospital HIS without touching the
agent or the booking tools.

## The seam

The five booking tools (`check_availability`, `book_appointment`, `get_my_appointments`,
`reschedule_appointment`, `cancel_appointment`) call `ctx.connector` for **appointment store +
availability**:

```
available_slots(doctor, on, duration_min, now) -> [datetime]
create_appointment(...) -> row | {"conflict": True}
upcoming_appointments(wa_user, now) -> [row]
get_appointment(id) -> row | None
reschedule(id, start, end) -> row | {"conflict"/"not_found": True}
set_status(id, status) -> None
capabilities() -> {read_availability, create, reschedule, cancel, list}
```

Everything else stays local on purpose — patient records, no-show risk, lead scoring,
reviews, insights — so the AI features keep working **regardless of the backend**. That local
data is the "mirror" referenced below and the actual product moat.

## System-of-record strategies

| Strategy | Use when | Cost |
|---|---|---|
| Native (our DB = SoR) | clinic has no system | none — today's mode |
| External = SoR, thin client | clinic insists their PMS rules | latency, their downtime, AI loses data |
| You = SoR, push out | calendar you fully own | double-booking with walk-ins |
| **Hybrid: external SoR + local mirror** | **integrated tenants (default)** | mirror drift → reconcile via webhook/poll |

Recommended default for integrated tenants is **hybrid**: the external system owns
availability/bookings (no double-booking), we keep a write-through mirror so analytics survive.

## Backends & feasibility

- **No system** → Native (ideal).
- **Calendar-only** (Google/Outlook) → OAuth + FreeBusy + Events; map 1 calendar per doctor.
- **Open cloud PMS** (Cliniko, Dentrix Ascend, OpenDental API) → full two-way + webhooks.
- **Closed / on-prem PMS** → fallback ladder: calendar export → integration engine/HL7 →
  edge agent → CSV import → native + human-in-the-loop. (Avoid scraping.)
- **Hospital HIS** (Epic/Cerner/local) → FHIR R4 (`Slot`/`Appointment`) or HL7v2 SIU via an
  integration engine; often read-availability + request-to-book (staff confirms), not direct write.

## Hard problems (and reused patterns)

- **Idempotency / dedup** of inbound connector webhooks → reuse `claim_message_id` /
  `processed_messages`.
- **Resilience** → mirror the LLM circuit-breaker: connector breaker open ⇒ degrade to
  request-to-book + `escalate_to_human`; never tell the patient "booked" without success.
- **Double-booking race** → re-validate at write time / trust the backend's conflict response.
- **Secrets/PHI** → connector credentials must be encrypted at rest (not in `clinic_data`
  JSONB plaintext, which is also a pre-existing gap for `wa_access_token`); BAA/DPA apply.
- **Mapping** → per-tenant maps of their services↔ours and providers↔our doctors.

## Phasing

0. **(done)** Extract `ClinicConnector` + `NativeConnector`; route tools through `ctx.connector`. Behavior-identical.
1. **(done)** Google Calendar — hybrid (Google free/busy + events, local mirror). See config below.
2. **(done)** Cliniko — hybrid (busy overlay + bookings via REST, local mirror). See config below.
3. Custom ERP via a generic webhook/REST adapter + config-driven mapping.
4. FHIR (hospital + modern dental); closed/on-prem via edge agent or calendar fallback.

`get_connector(tenant)` dispatches on `clinic_data.connector.type`.

## Google Calendar connector config

Platform OAuth app creds in env: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`.
Per-tenant, in `clinic_data.connector`:

```json
{
  "type": "google_calendar",
  "refresh_token": "<tenant's OAuth refresh token>",
  "timezone": "Asia/Riyadh",
  "calendars": { "Dr. Khalid Al-Otaibi": "<calendarId>", "Dr. Sara Al-Subaie": "<calendarId>" },
  "default_calendar": "<optional fallback calendarId>"
}
```

Behaviour: working hours come from each doctor's `available_hours` in `clinic_data`; Google
free/busy removes booked times; bookings are written as calendar events **and** mirrored to
our `appointments` table (with `external_id` = event id) so analytics keep working. A
calendar write failure never loses the booking (mirror is authoritative for the patient).

> Live I/O (`GoogleCalendarClient`) needs the tenant's Google authorization and is not
> covered by tests — verify against a real calendar. The refresh token is a secret and must
> not live in plaintext `clinic_data` in production (encrypt at rest / use a secret store).

## Cliniko connector config

Per-tenant, in `clinic_data.connector`:

```json
{
  "type": "cliniko",
  "api_key": "<cliniko api key, e.g. MS0x...-au4>",
  "user_agent": "Your Clinic (you@clinic.com)",
  "business_id": "<businessId>",
  "practitioners": { "Dr. Khalid Al-Otaibi": "<practitionerId>" },
  "appointment_types": { "Dental Checkup": "<appointmentTypeId>" }
}
```

Behaviour: availability = doctor's `available_hours` (clinic_data) minus Cliniko's existing
bookings for that practitioner (busy overlay); bookings find/create a Cliniko patient and
create an `individual_appointment`, mirrored locally (`external_id` = Cliniko id).
Reschedule/cancel propagate to Cliniko; a Cliniko failure keeps the local booking.

> Live I/O (`ClinikoClient`): API-key Basic auth, shard from the key suffix, required
> User-Agent. The `api_key` is a secret (same storage caveat as above). Endpoint/field
> names follow Cliniko v1 — **verify against current Cliniko API docs** before go-live;
> the connector *logic* is tested with a fake, the HTTP client is not.


