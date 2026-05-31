"""Clinic connector layer — the seam between the AI agent and where appointments truly live.

Today every clinic uses NativeConnector (our Postgres is the system of record). The point
of this layer is that a tenant could instead be backed by Cliniko, a Google Calendar, a
custom ERP, a dental PMS, or a hospital HIS — without changing the agent or the booking
tools. The booking tools call `ctx.connector` for availability + create/reschedule/cancel/
list; everything else (patient records, no-show risk, lead scoring, reviews) stays in our
local DB so the AI features keep working regardless of the backend (see docs/connectors.md).

Connectors are capability-based: not every backend supports every operation, so callers can
check `capabilities()` and degrade (e.g. request-to-book when there's no write API). Native
supports them all.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date as date_cls
from datetime import datetime

from app import db
from app.scheduling import available_slots, day_bounds

log = logging.getLogger(__name__)

# Capability flags a connector may advertise.
READ_AVAILABILITY = "read_availability"
CREATE = "create"
RESCHEDULE = "reschedule"
CANCEL = "cancel"
LIST = "list"


class ClinicConnector(ABC):
    """Appointment store + availability for one tenant. Implementations map our domain
    (doctor, service, slot) onto a backend (our DB, Cliniko, a calendar, …)."""

    @abstractmethod
    def capabilities(self) -> set[str]: ...

    @abstractmethod
    def available_slots(self, doctor: dict, on: date_cls, duration_min: int,
                        now: datetime) -> list[datetime]:
        """Bookable start times for a doctor on a date (already excludes past/lead-time
        and existing bookings)."""

    @abstractmethod
    def create_appointment(self, *, wa_user: str, patient_name: str | None,
                           phone: str | None, doctor: str, service: str,
                           start: datetime, end: datetime,
                           extra: dict | None = None) -> dict:
        """Create a booking. Returns the appointment row, or {'conflict': True} if the
        slot was taken between availability check and write."""

    @abstractmethod
    def upcoming_appointments(self, wa_user: str, now: datetime) -> list[dict]: ...

    @abstractmethod
    def get_appointment(self, appointment_id: int) -> dict | None: ...

    @abstractmethod
    def reschedule(self, appointment_id: int, start: datetime, end: datetime) -> dict:
        """Move a booking. Returns the row, {'conflict': True}, or {'not_found': True}."""

    @abstractmethod
    def set_status(self, appointment_id: int, status: str) -> None: ...


class NativeConnector(ClinicConnector):
    """Our Postgres is the system of record — the default for every tenant. Thin wrapper
    over db + scheduling so the booking tools don't call them directly."""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    def capabilities(self) -> set[str]:
        return {READ_AVAILABILITY, CREATE, RESCHEDULE, CANCEL, LIST}

    def available_slots(self, doctor, on, duration_min, now):
        day_start, day_end = day_bounds(on)
        booked = db.booked_intervals(self.tenant_id, doctor["name"], day_start, day_end)
        return available_slots(doctor, on, duration_min, booked, now)

    def create_appointment(self, *, wa_user, patient_name, phone, doctor, service,
                           start, end, extra=None):
        return db.create_appointment(self.tenant_id, wa_user, patient_name, phone, doctor,
                                     service, start, end, extra=extra)

    def upcoming_appointments(self, wa_user, now):
        return db.upcoming_appointments(self.tenant_id, wa_user, now)

    def get_appointment(self, appointment_id):
        return db.get_appointment(self.tenant_id, appointment_id)

    def reschedule(self, appointment_id, start, end):
        return db.reschedule(self.tenant_id, appointment_id, start, end)

    def set_status(self, appointment_id, status):
        db.set_appointment_status(self.tenant_id, appointment_id, status)


# --- Google Calendar (Phase 1) ---

class CalendarClient(ABC):
    """The narrow I/O boundary a calendar-backed connector needs. Injected so the connector
    logic is testable with a fake; the real impl (GoogleCalendarClient) does live HTTP."""

    @abstractmethod
    def free_busy(self, calendar_id: str, time_min: datetime,
                  time_max: datetime) -> list[tuple[datetime, datetime]]: ...

    @abstractmethod
    def create_event(self, calendar_id: str, summary: str, start: datetime,
                     end: datetime, description: str = "") -> str: ...

    @abstractmethod
    def patch_event(self, calendar_id: str, event_id: str, start: datetime,
                    end: datetime) -> None: ...

    @abstractmethod
    def delete_event(self, calendar_id: str, event_id: str) -> None: ...


class GoogleCalendarConnector(ClinicConnector):
    """Hybrid: Google Calendar owns free/busy (availability) and holds the events, while we
    mirror each appointment locally so the AI features (risk, reviews, insights) keep working.

    Working hours still come from clinic_data (a calendar has no notion of a doctor's shift);
    Google only supplies the BUSY overlay via free/busy. Doctors map to calendars via
    config['calendars'] = {doctor_name: calendar_id}.
    """

    def __init__(self, tenant_id: int, config: dict, client: CalendarClient):
        self.tenant_id = tenant_id
        self.config = config or {}
        self.client = client
        self._cal = {str(k).lower(): v for k, v in (self.config.get("calendars") or {}).items()}

    def capabilities(self) -> set[str]:
        return {READ_AVAILABILITY, CREATE, RESCHEDULE, CANCEL, LIST}

    def _calendar_for(self, doctor_name: str | None) -> str | None:
        return self._cal.get(str(doctor_name or "").lower()) or self.config.get("default_calendar")

    def available_slots(self, doctor, on, duration_min, now):
        cal = self._calendar_for(doctor.get("name"))
        if not cal:
            return []
        day_start, day_end = day_bounds(on)
        busy = self.client.free_busy(cal, day_start, day_end)
        return available_slots(doctor, on, duration_min, busy, now)

    def create_appointment(self, *, wa_user, patient_name, phone, doctor, service,
                           start, end, extra=None):
        # Mirror first: gives us the conflict guard + the row our AI features read. Then
        # write the calendar event (best-effort; a failure leaves the booking intact).
        row = db.create_appointment(self.tenant_id, wa_user, patient_name, phone, doctor,
                                    service, start, end, extra=extra)
        if row.get("conflict"):
            return row
        cal = self._calendar_for(doctor)
        if cal:
            try:
                event_id = self.client.create_event(
                    cal, f"{service} — {patient_name or wa_user}", start, end,
                    f"Booked via WhatsApp ({phone or wa_user})")
                db.set_appointment_external_id(self.tenant_id, row["id"], event_id)
                row = {**row, "external_id": event_id}
            except Exception:  # noqa: BLE001 — never lose the booking on a calendar hiccup
                log.exception("google create_event failed for appt %s (booking kept)", row["id"])
        return row

    def upcoming_appointments(self, wa_user, now):
        return db.upcoming_appointments(self.tenant_id, wa_user, now)

    def get_appointment(self, appointment_id):
        return db.get_appointment(self.tenant_id, appointment_id)

    def reschedule(self, appointment_id, start, end):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if not appt:
            return {"not_found": True}
        cal = self._calendar_for(appt["doctor"])
        if cal and appt.get("external_id"):
            try:
                self.client.patch_event(cal, appt["external_id"], start, end)
            except Exception:  # noqa: BLE001
                log.exception("google patch_event failed for appt %s", appointment_id)
        return db.reschedule(self.tenant_id, appointment_id, start, end)

    def set_status(self, appointment_id, status):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if appt and status == "cancelled" and appt.get("external_id"):
            cal = self._calendar_for(appt["doctor"])
            if cal:
                try:
                    self.client.delete_event(cal, appt["external_id"])
                except Exception:  # noqa: BLE001
                    log.exception("google delete_event failed for appt %s", appointment_id)
        db.set_appointment_status(self.tenant_id, appointment_id, status)


class GoogleCalendarClient(CalendarClient):
    """Live Google Calendar REST client (OAuth2 refresh-token flow). Requires the tenant's
    Google authorization; NOT exercised by tests — verify against a real calendar."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    API = "https://www.googleapis.com/calendar/v3"

    def __init__(self, *, client_id: str, client_secret: str, refresh_token: str,
                 timezone: str = "Asia/Riyadh"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.timezone = timezone
        self._token: str | None = None

    def _access_token(self) -> str:
        import httpx
        r = httpx.post(self.TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.refresh_token, "grant_type": "refresh_token"}, timeout=15)
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json"}

    def ping(self):
        self._access_token()   # a successful token refresh proves the credentials work

    def free_busy(self, calendar_id, time_min, time_max):
        import httpx
        r = httpx.post(f"{self.API}/freeBusy", headers=self._headers(), timeout=15, json={
            "timeMin": time_min.isoformat(), "timeMax": time_max.isoformat(),
            "items": [{"id": calendar_id}]})
        r.raise_for_status()
        busy = r.json()["calendars"][calendar_id].get("busy", [])
        return [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in busy]

    def create_event(self, calendar_id, summary, start, end, description=""):
        import httpx
        r = httpx.post(f"{self.API}/calendars/{calendar_id}/events", headers=self._headers(),
                       timeout=15, json={
                           "summary": summary, "description": description,
                           "start": {"dateTime": start.isoformat(), "timeZone": self.timezone},
                           "end": {"dateTime": end.isoformat(), "timeZone": self.timezone}})
        r.raise_for_status()
        return r.json()["id"]

    def patch_event(self, calendar_id, event_id, start, end):
        import httpx
        r = httpx.patch(f"{self.API}/calendars/{calendar_id}/events/{event_id}",
                        headers=self._headers(), timeout=15, json={
                            "start": {"dateTime": start.isoformat(), "timeZone": self.timezone},
                            "end": {"dateTime": end.isoformat(), "timeZone": self.timezone}})
        r.raise_for_status()

    def delete_event(self, calendar_id, event_id):
        import httpx
        r = httpx.delete(f"{self.API}/calendars/{calendar_id}/events/{event_id}",
                         headers=self._headers(), timeout=15)
        if r.status_code not in (200, 204, 404, 410):   # 404/410 = already gone
            r.raise_for_status()


def _build_google_client(conf: dict) -> CalendarClient:
    """Construct the live Google client from platform OAuth creds + the tenant's refresh
    token. Patched in tests. Raises if creds are missing."""
    from app.config import GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
    if not (GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET and conf.get("refresh_token")):
        raise RuntimeError("Google connector not configured (client id/secret/refresh_token)")
    return GoogleCalendarClient(
        client_id=GOOGLE_OAUTH_CLIENT_ID, client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
        refresh_token=conf["refresh_token"], timezone=conf.get("timezone", "Asia/Riyadh"))


# --- Cliniko (Phase 2) ---

class ClinikoApi(ABC):
    """I/O boundary for Cliniko (a healthcare PMS). Injected so the connector logic is
    testable with a fake; the real impl (ClinikoClient) does live HTTP."""

    @abstractmethod
    def list_busy(self, practitioner_id: str, time_min: datetime,
                  time_max: datetime) -> list[tuple[datetime, datetime]]: ...

    @abstractmethod
    def find_or_create_patient(self, name: str | None, phone: str) -> str: ...

    @abstractmethod
    def create_appointment(self, *, business_id: str, practitioner_id: str,
                           appointment_type_id: str, patient_id: str,
                           start: datetime, end: datetime) -> str: ...

    @abstractmethod
    def update_appointment(self, appointment_id: str, start: datetime, end: datetime) -> None: ...

    @abstractmethod
    def cancel_appointment(self, appointment_id: str) -> None: ...


class ClinikoConnector(ClinicConnector):
    """Hybrid connector for Cliniko: Cliniko holds practitioners/appointment-types/patients
    and the real bookings; we mirror each appointment locally for the AI features.

    Availability is computed as the doctor's working hours (clinic_data) minus Cliniko's
    existing bookings for that practitioner (busy overlay) — consistent with the Google
    connector and keeping the interface stable. (A later refinement could use Cliniko's
    native available_times to also honour breaks/blocked time.)

    config maps our names to Cliniko ids:
      practitioners {doctor_name: id}, appointment_types {service_name: id}, business_id.
    """

    def __init__(self, tenant_id: int, config: dict, client: ClinikoApi):
        self.tenant_id = tenant_id
        self.config = config or {}
        self.client = client
        self._pract = {str(k).lower(): v for k, v in (config.get("practitioners") or {}).items()}
        self._types = {str(k).lower(): v for k, v in (config.get("appointment_types") or {}).items()}
        self.business_id = config.get("business_id")

    def capabilities(self) -> set[str]:
        return {READ_AVAILABILITY, CREATE, RESCHEDULE, CANCEL, LIST}

    def _practitioner(self, doctor_name: str | None) -> str | None:
        return self._pract.get(str(doctor_name or "").lower())

    def _appt_type(self, service_name: str | None) -> str | None:
        return self._types.get(str(service_name or "").lower())

    def available_slots(self, doctor, on, duration_min, now):
        pid = self._practitioner(doctor.get("name"))
        if not pid:
            return []
        day_start, day_end = day_bounds(on)
        busy = self.client.list_busy(pid, day_start, day_end)
        return available_slots(doctor, on, duration_min, busy, now)

    def create_appointment(self, *, wa_user, patient_name, phone, doctor, service,
                           start, end, extra=None):
        row = db.create_appointment(self.tenant_id, wa_user, patient_name, phone, doctor,
                                    service, start, end, extra=extra)
        if row.get("conflict"):
            return row
        pid, atype = self._practitioner(doctor), self._appt_type(service)
        if pid and atype and self.business_id:
            try:
                patient_id = self.client.find_or_create_patient(patient_name, phone or wa_user)
                ext = self.client.create_appointment(
                    business_id=self.business_id, practitioner_id=pid,
                    appointment_type_id=atype, patient_id=patient_id, start=start, end=end)
                db.set_appointment_external_id(self.tenant_id, row["id"], ext)
                row = {**row, "external_id": ext}
            except Exception:  # noqa: BLE001 — keep the booking if Cliniko write fails
                log.exception("cliniko create failed for appt %s (booking kept)", row["id"])
        return row

    def upcoming_appointments(self, wa_user, now):
        return db.upcoming_appointments(self.tenant_id, wa_user, now)

    def get_appointment(self, appointment_id):
        return db.get_appointment(self.tenant_id, appointment_id)

    def reschedule(self, appointment_id, start, end):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if not appt:
            return {"not_found": True}
        if appt.get("external_id"):
            try:
                self.client.update_appointment(appt["external_id"], start, end)
            except Exception:  # noqa: BLE001
                log.exception("cliniko update failed for appt %s", appointment_id)
        return db.reschedule(self.tenant_id, appointment_id, start, end)

    def set_status(self, appointment_id, status):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if appt and status == "cancelled" and appt.get("external_id"):
            try:
                self.client.cancel_appointment(appt["external_id"])
            except Exception:  # noqa: BLE001
                log.exception("cliniko cancel failed for appt %s", appointment_id)
        db.set_appointment_status(self.tenant_id, appointment_id, status)


class ClinikoClient(ClinikoApi):
    """Live Cliniko REST client. API-key Basic auth; the shard is the suffix after the last
    '-' in the key (e.g. '…-au4' -> api.au4.cliniko.com). Cliniko requires a descriptive
    User-Agent with a contact email. NOT exercised by tests — verify field names/endpoints
    against current Cliniko API docs before going live."""

    def __init__(self, *, api_key: str, user_agent: str):
        self.api_key = api_key
        self.user_agent = user_agent
        shard = api_key.rsplit("-", 1)[-1] if "-" in api_key else "au1"
        self.base = f"https://api.{shard}.cliniko.com/v1"

    def _auth(self):
        import base64
        token = base64.b64encode(f"{self.api_key}:".encode()).decode()
        return {"Authorization": f"Basic {token}", "User-Agent": self.user_agent,
                "Accept": "application/json", "Content-Type": "application/json"}

    def ping(self):
        import httpx
        r = httpx.get(f"{self.base}/practitioners", headers=self._auth(), timeout=15,
                      params={"per_page": 1})
        r.raise_for_status()

    def list_busy(self, practitioner_id, time_min, time_max):
        import httpx
        r = httpx.get(f"{self.base}/appointments", headers=self._auth(), timeout=15, params={
            "q[]": [f"practitioner_id:={practitioner_id}",
                    f"starts_at:>={time_min.isoformat()}", f"ends_at:<={time_max.isoformat()}"],
            "per_page": 100})
        r.raise_for_status()
        out = []
        for a in r.json().get("appointments", []):
            if a.get("starts_at") and a.get("ends_at"):
                out.append((datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")),
                            datetime.fromisoformat(a["ends_at"].replace("Z", "+00:00"))))
        return out

    def find_or_create_patient(self, name, phone):
        import httpx
        r = httpx.get(f"{self.base}/patients", headers=self._auth(), timeout=15,
                      params={"q[]": f"phone_number:={phone}", "per_page": 1})
        r.raise_for_status()
        found = r.json().get("patients", [])
        if found:
            return str(found[0]["id"])
        first, _, last = (name or "Patient").partition(" ")
        r = httpx.post(f"{self.base}/patients", headers=self._auth(), timeout=15, json={
            "first_name": first or "Patient", "last_name": last or "(WhatsApp)"})
        r.raise_for_status()
        return str(r.json()["id"])

    def create_appointment(self, *, business_id, practitioner_id, appointment_type_id,
                           patient_id, start, end):
        import httpx
        r = httpx.post(f"{self.base}/individual_appointments", headers=self._auth(), timeout=15,
                       json={"appointment_start": start.isoformat(), "business_id": business_id,
                             "practitioner_id": practitioner_id, "patient_id": patient_id,
                             "appointment_type_id": appointment_type_id})
        r.raise_for_status()
        return str(r.json()["id"])

    def update_appointment(self, appointment_id, start, end):
        import httpx
        r = httpx.patch(f"{self.base}/individual_appointments/{appointment_id}",
                        headers=self._auth(), timeout=15,
                        json={"appointment_start": start.isoformat()})
        r.raise_for_status()

    def cancel_appointment(self, appointment_id):
        import httpx
        r = httpx.delete(f"{self.base}/individual_appointments/{appointment_id}",
                         headers=self._auth(), timeout=15)
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()


def _build_cliniko_client(conf: dict) -> ClinikoApi:
    if not conf.get("api_key"):
        raise RuntimeError("Cliniko connector not configured (api_key)")
    return ClinikoClient(api_key=conf["api_key"],
                         user_agent=conf.get("user_agent", "ClinicAIAssistant (support@example.com)"))


# --- Custom ERP (Phase 3) — config-driven adapter over a small canonical REST contract ---
#
# Rather than a bespoke connector per ERP, the ERP exposes (or a thin shim provides) four
# endpoints speaking a fixed shape; we point GenericErpClient at its base_url + auth:
#   GET    {base}/availability?doctor=&service=&date=YYYY-MM-DD  -> {"slots": ["<ISO start>", …]}
#   POST   {base}/appointments  {external_ref,doctor,service,patient_name,phone,start,end} -> {"id": "…"}
#   PATCH  {base}/appointments/{id}  {start,end}
#   DELETE {base}/appointments/{id}
# The ERP owns availability; we mirror bookings locally for the AI features.

class ErpApi(ABC):
    """I/O boundary for a custom ERP speaking the canonical contract above."""

    @abstractmethod
    def get_availability(self, doctor: str, service: str | None,
                         on: date_cls) -> list[datetime]: ...

    @abstractmethod
    def create_appointment(self, *, external_ref: str, doctor: str, service: str,
                           patient_name: str | None, phone: str,
                           start: datetime, end: datetime) -> str: ...

    @abstractmethod
    def reschedule(self, external_id: str, start: datetime, end: datetime) -> None: ...

    @abstractmethod
    def cancel(self, external_id: str) -> None: ...


class CustomErpConnector(ClinicConnector):
    """Hybrid connector for an arbitrary ERP: the ERP is the availability + booking
    authority (it returns bookable slots directly), we mirror appointments locally so the
    AI features keep working. Doctor/service are passed by name; the ERP maps them itself."""

    def __init__(self, tenant_id: int, config: dict, client: ErpApi):
        self.tenant_id = tenant_id
        self.config = config or {}
        self.client = client

    def capabilities(self) -> set[str]:
        return {READ_AVAILABILITY, CREATE, RESCHEDULE, CANCEL, LIST}

    def available_slots(self, doctor, on, duration_min, now):
        # The ERP returns bookable starts directly; we just drop anything already past.
        slots = self.client.get_availability(doctor.get("name"), None, on)
        return [s for s in slots if s > now]

    def create_appointment(self, *, wa_user, patient_name, phone, doctor, service,
                           start, end, extra=None):
        row = db.create_appointment(self.tenant_id, wa_user, patient_name, phone, doctor,
                                    service, start, end, extra=extra)
        if row.get("conflict"):
            return row
        try:
            ext = self.client.create_appointment(
                external_ref=str(row["id"]), doctor=doctor, service=service,
                patient_name=patient_name, phone=phone or wa_user, start=start, end=end)
            db.set_appointment_external_id(self.tenant_id, row["id"], ext)
            row = {**row, "external_id": ext}
        except Exception:  # noqa: BLE001 — keep the booking if the ERP write fails
            log.exception("ERP create failed for appt %s (booking kept)", row["id"])
        return row

    def upcoming_appointments(self, wa_user, now):
        return db.upcoming_appointments(self.tenant_id, wa_user, now)

    def get_appointment(self, appointment_id):
        return db.get_appointment(self.tenant_id, appointment_id)

    def reschedule(self, appointment_id, start, end):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if not appt:
            return {"not_found": True}
        if appt.get("external_id"):
            try:
                self.client.reschedule(appt["external_id"], start, end)
            except Exception:  # noqa: BLE001
                log.exception("ERP reschedule failed for appt %s", appointment_id)
        return db.reschedule(self.tenant_id, appointment_id, start, end)

    def set_status(self, appointment_id, status):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if appt and status == "cancelled" and appt.get("external_id"):
            try:
                self.client.cancel(appt["external_id"])
            except Exception:  # noqa: BLE001
                log.exception("ERP cancel failed for appt %s", appointment_id)
        db.set_appointment_status(self.tenant_id, appointment_id, status)


class GenericErpClient(ErpApi):
    """Live client for the canonical ERP contract. Auth is config-driven:
    {"type":"bearer","token":…} | {"type":"header","name":…,"value":…} | {"type":"none"}.
    NOT exercised by tests — verify against the ERP's actual shim."""

    def __init__(self, *, base_url: str, auth: dict | None = None):
        self.base = base_url.rstrip("/")
        self.auth = auth or {}

    def _headers(self) -> dict:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        atype = self.auth.get("type")
        if atype == "bearer":
            h["Authorization"] = f"Bearer {self.auth.get('token', '')}"
        elif atype == "header":
            h[self.auth.get("name", "X-API-Key")] = self.auth.get("value", "")
        return h

    def ping(self):
        import httpx
        from datetime import date as _d
        r = httpx.get(f"{self.base}/availability", headers=self._headers(), timeout=15,
                      params={"date": _d.today().isoformat()})
        if r.status_code in (401, 403):
            r.raise_for_status()   # auth problem; other codes just mean "reachable"

    def get_availability(self, doctor, service, on):
        import httpx
        params = {"doctor": doctor, "date": on.isoformat()}
        if service:
            params["service"] = service
        r = httpx.get(f"{self.base}/availability", headers=self._headers(), params=params, timeout=15)
        r.raise_for_status()
        return [datetime.fromisoformat(s.replace("Z", "+00:00"))
                for s in r.json().get("slots", [])]

    def create_appointment(self, *, external_ref, doctor, service, patient_name, phone, start, end):
        import httpx
        r = httpx.post(f"{self.base}/appointments", headers=self._headers(), timeout=15, json={
            "external_ref": external_ref, "doctor": doctor, "service": service,
            "patient_name": patient_name, "phone": phone,
            "start": start.isoformat(), "end": end.isoformat()})
        r.raise_for_status()
        return str(r.json()["id"])

    def reschedule(self, external_id, start, end):
        import httpx
        r = httpx.patch(f"{self.base}/appointments/{external_id}", headers=self._headers(),
                        timeout=15, json={"start": start.isoformat(), "end": end.isoformat()})
        r.raise_for_status()

    def cancel(self, external_id):
        import httpx
        r = httpx.delete(f"{self.base}/appointments/{external_id}", headers=self._headers(), timeout=15)
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()


def _build_erp_client(conf: dict) -> ErpApi:
    if not conf.get("base_url"):
        raise RuntimeError("Custom ERP connector not configured (base_url)")
    return GenericErpClient(base_url=conf["base_url"], auth=conf.get("auth"))


# --- FHIR (Phase 4) — hospital HIS / modern dental via FHIR R4 ---
#
# Availability comes from FHIR `Slot` resources (status=free); bookings are `Appointment`
# resources. Many hospitals only permit request-to-book (Appointment.status="proposed",
# staff confirm in the HIS) rather than a direct "booked" — set config.booking_status.

class FhirApi(ABC):
    """I/O boundary for a FHIR R4 scheduling server."""

    @abstractmethod
    def free_slots(self, schedule_ref: str, time_min: datetime,
                   time_max: datetime) -> list[datetime]: ...

    @abstractmethod
    def find_or_create_patient(self, name: str | None, phone: str) -> str: ...

    @abstractmethod
    def create_appointment(self, *, practitioner_ref: str, patient_ref: str,
                           start: datetime, end: datetime, status: str) -> str: ...

    @abstractmethod
    def update_appointment(self, appointment_id: str, start: datetime, end: datetime) -> None: ...

    @abstractmethod
    def cancel_appointment(self, appointment_id: str) -> None: ...


class FhirConnector(ClinicConnector):
    """Hybrid connector for a FHIR server: the HIS owns slots + appointments, we mirror
    locally. Doctors map to a Schedule (for availability) and a Practitioner (for booking)
    via config. `booking_status` is 'booked' (direct) or 'proposed' (request-to-book)."""

    def __init__(self, tenant_id: int, config: dict, client: FhirApi):
        self.tenant_id = tenant_id
        self.config = config or {}
        self.client = client
        self._sched = {str(k).lower(): v for k, v in (config.get("schedules") or {}).items()}
        self._pract = {str(k).lower(): v for k, v in (config.get("practitioners") or {}).items()}
        self.booking_status = config.get("booking_status", "booked")

    def capabilities(self) -> set[str]:
        return {READ_AVAILABILITY, CREATE, RESCHEDULE, CANCEL, LIST}

    def _schedule(self, doctor_name):
        return self._sched.get(str(doctor_name or "").lower())

    def _practitioner(self, doctor_name):
        return self._pract.get(str(doctor_name or "").lower())

    def available_slots(self, doctor, on, duration_min, now):
        sched = self._schedule(doctor.get("name"))
        if not sched:
            return []
        day_start, day_end = day_bounds(on)
        return [s for s in self.client.free_slots(sched, day_start, day_end) if s > now]

    def create_appointment(self, *, wa_user, patient_name, phone, doctor, service,
                           start, end, extra=None):
        row = db.create_appointment(self.tenant_id, wa_user, patient_name, phone, doctor,
                                    service, start, end, extra=extra)
        if row.get("conflict"):
            return row
        pract = self._practitioner(doctor)
        if pract:
            try:
                patient_ref = self.client.find_or_create_patient(patient_name, phone or wa_user)
                ext = self.client.create_appointment(
                    practitioner_ref=pract, patient_ref=patient_ref, start=start, end=end,
                    status=self.booking_status)
                db.set_appointment_external_id(self.tenant_id, row["id"], ext)
                row = {**row, "external_id": ext, "pending": self.booking_status == "proposed"}
            except Exception:  # noqa: BLE001 — keep the booking if the HIS write fails
                log.exception("FHIR create failed for appt %s (booking kept)", row["id"])
        return row

    def upcoming_appointments(self, wa_user, now):
        return db.upcoming_appointments(self.tenant_id, wa_user, now)

    def get_appointment(self, appointment_id):
        return db.get_appointment(self.tenant_id, appointment_id)

    def reschedule(self, appointment_id, start, end):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if not appt:
            return {"not_found": True}
        if appt.get("external_id"):
            try:
                self.client.update_appointment(appt["external_id"], start, end)
            except Exception:  # noqa: BLE001
                log.exception("FHIR update failed for appt %s", appointment_id)
        return db.reschedule(self.tenant_id, appointment_id, start, end)

    def set_status(self, appointment_id, status):
        appt = db.get_appointment(self.tenant_id, appointment_id)
        if appt and status == "cancelled" and appt.get("external_id"):
            try:
                self.client.cancel_appointment(appt["external_id"])
            except Exception:  # noqa: BLE001
                log.exception("FHIR cancel failed for appt %s", appointment_id)
        db.set_appointment_status(self.tenant_id, appointment_id, status)


class FhirClient(FhirApi):
    """Live FHIR R4 client. Auth is config-driven: {"type":"bearer","token":…} or
    {"type":"client_credentials","token_url":…,"client_id":…,"client_secret":…,"scope":…}.
    NOT exercised by tests; production SMART backend auth often needs a signed JWT assertion
    — verify against your server before go-live."""

    def __init__(self, *, base_url: str, auth: dict | None = None):
        self.base = base_url.rstrip("/")
        self.auth = auth or {}

    def _token(self) -> str:
        if self.auth.get("type") == "bearer":
            return self.auth.get("token", "")
        if self.auth.get("type") == "client_credentials":
            import httpx
            r = httpx.post(self.auth["token_url"], timeout=15, data={
                "grant_type": "client_credentials", "client_id": self.auth["client_id"],
                "client_secret": self.auth.get("client_secret", ""),
                "scope": self.auth.get("scope", "system/Appointment.write system/Slot.read")})
            r.raise_for_status()
            return r.json()["access_token"]
        return ""

    def _headers(self) -> dict:
        h = {"Accept": "application/fhir+json", "Content-Type": "application/fhir+json"}
        tok = self._token()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
        return h

    def ping(self):
        import httpx
        r = httpx.get(f"{self.base}/metadata", headers=self._headers(), timeout=15)
        r.raise_for_status()   # FHIR CapabilityStatement — the standard reachability probe

    def free_slots(self, schedule_ref, time_min, time_max):
        import httpx
        r = httpx.get(f"{self.base}/Slot", headers=self._headers(), timeout=15, params={
            "schedule": schedule_ref, "status": "free",
            "start": [f"ge{time_min.isoformat()}", f"lt{time_max.isoformat()}"]})
        r.raise_for_status()
        out = []
        for e in r.json().get("entry", []):
            start = (e.get("resource") or {}).get("start")
            if start:
                out.append(datetime.fromisoformat(start.replace("Z", "+00:00")))
        return out

    def find_or_create_patient(self, name, phone):
        import httpx
        r = httpx.get(f"{self.base}/Patient", headers=self._headers(), timeout=15,
                      params={"telecom": phone})
        r.raise_for_status()
        entries = r.json().get("entry", [])
        if entries:
            return f"Patient/{entries[0]['resource']['id']}"
        first, _, last = (name or "Patient").partition(" ")
        r = httpx.post(f"{self.base}/Patient", headers=self._headers(), timeout=15, json={
            "resourceType": "Patient", "name": [{"given": [first or "Patient"],
                                                 "family": last or "(WhatsApp)"}],
            "telecom": [{"system": "phone", "value": phone}]})
        r.raise_for_status()
        return f"Patient/{r.json()['id']}"

    def create_appointment(self, *, practitioner_ref, patient_ref, start, end, status):
        import httpx
        r = httpx.post(f"{self.base}/Appointment", headers=self._headers(), timeout=15, json={
            "resourceType": "Appointment", "status": status,
            "start": start.isoformat(), "end": end.isoformat(),
            "participant": [{"actor": {"reference": practitioner_ref}, "status": "accepted"},
                            {"actor": {"reference": patient_ref}, "status": "accepted"}]})
        r.raise_for_status()
        return str(r.json()["id"])

    def update_appointment(self, appointment_id, start, end):
        import httpx
        r = httpx.patch(f"{self.base}/Appointment/{appointment_id}",
                        headers={**self._headers(), "Content-Type": "application/json-patch+json"},
                        timeout=15, json=[
                            {"op": "replace", "path": "/start", "value": start.isoformat()},
                            {"op": "replace", "path": "/end", "value": end.isoformat()}])
        r.raise_for_status()

    def cancel_appointment(self, appointment_id):
        import httpx
        r = httpx.patch(f"{self.base}/Appointment/{appointment_id}",
                        headers={**self._headers(), "Content-Type": "application/json-patch+json"},
                        timeout=15, json=[{"op": "replace", "path": "/status", "value": "cancelled"}])
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()


def _build_fhir_client(conf: dict) -> FhirApi:
    if not conf.get("base_url"):
        raise RuntimeError("FHIR connector not configured (base_url)")
    return FhirClient(base_url=conf["base_url"], auth=conf.get("auth"))


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def apply_inbound_event(tenant_id: int, event: dict) -> str:
    """Reconcile our local mirror from an inbound connector event (staff booked/changed/
    cancelled directly in the external system). Canonical event shape:
      {event: created|updated|cancelled|completed|no_show, external_id, wa_user|phone,
       doctor, service, start, end, patient_name}
    Returns a short status string. Idempotency/dedup is handled by the webhook route."""
    etype = (event.get("event") or "").strip().lower()
    ext = event.get("external_id")
    if not ext:
        return "ignored:no_external_id"
    existing = db.appointment_by_external_id(tenant_id, ext)

    if etype in ("cancelled", "completed", "no_show"):
        if not existing:
            return "ignored:unknown_appointment"
        db.set_appointment_status(tenant_id, existing["id"], etype)
        return f"status:{etype}"

    start, end = _parse_dt(event.get("start")), _parse_dt(event.get("end"))
    if etype in ("updated", "rescheduled"):
        if not existing:
            return "ignored:unknown_appointment"
        if not (start and end):
            return "ignored:bad_times"
        db.update_appointment_times(tenant_id, existing["id"], start, end)
        return "updated"

    if etype in ("created", "booked"):
        if existing:
            if start and end:
                db.update_appointment_times(tenant_id, existing["id"], start, end)
            return "updated"
        wa_user = (event.get("wa_user") or event.get("phone") or "").strip()
        if not (wa_user and start and end):
            return "ignored:incomplete"
        db.create_mirror_appointment(
            tenant_id, ext, wa_user, event.get("patient_name"), event.get("phone") or wa_user,
            event.get("doctor") or "", event.get("service") or "", start, end, "confirmed")
        return "created"

    return "ignored:unknown_event"


def probe(connector: ClinicConnector) -> dict:
    """Test that a connector can actually reach its backend. Returns {ok, detail}. Native is
    always ok; external connectors call their client's ping() (a cheap authenticated read)."""
    if isinstance(connector, NativeConnector):
        return {"ok": True, "detail": "Local database (no external system)"}
    client = getattr(connector, "client", None)
    ping = getattr(client, "ping", None)
    try:
        if callable(ping):
            ping()
        return {"ok": True, "detail": "Connected"}
    except Exception as e:  # noqa: BLE001 — surface the failure to the admin
        return {"ok": False, "detail": str(e)[:300]}


def get_connector(tenant: dict | None) -> ClinicConnector:
    """Resolve the connector for a tenant from clinic_data.connector.type. Falls back to
    NativeConnector (our DB) for unconfigured tenants or if a connector fails to initialise."""
    tenant_id = (tenant or {}).get("id") or 0
    conf = ((tenant or {}).get("clinic_data") or {}).get("connector") or {}
    ctype = conf.get("type")
    try:
        if ctype == "google_calendar":
            return GoogleCalendarConnector(tenant_id, conf, _build_google_client(conf))
        if ctype == "cliniko":
            return ClinikoConnector(tenant_id, conf, _build_cliniko_client(conf))
        if ctype == "custom_erp":
            return CustomErpConnector(tenant_id, conf, _build_erp_client(conf))
        if ctype == "fhir":
            return FhirConnector(tenant_id, conf, _build_fhir_client(conf))
    except Exception:  # noqa: BLE001 — a misconfigured connector must not break bookings
        log.exception("connector '%s' init failed for tenant %s; using native", ctype, tenant_id)
    return NativeConnector(tenant_id)
