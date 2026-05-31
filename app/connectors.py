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


def get_connector(tenant: dict | None) -> ClinicConnector:
    """Resolve the connector for a tenant from clinic_data.connector.type. Falls back to
    NativeConnector (our DB) for unconfigured tenants or if a connector fails to initialise."""
    tenant_id = (tenant or {}).get("id") or 0
    conf = ((tenant or {}).get("clinic_data") or {}).get("connector") or {}
    if conf.get("type") == "google_calendar":
        try:
            return GoogleCalendarConnector(tenant_id, conf, _build_google_client(conf))
        except Exception:  # noqa: BLE001 — a misconfigured connector must not break bookings
            log.exception("google connector init failed for tenant %s; using native", tenant_id)
    return NativeConnector(tenant_id)
