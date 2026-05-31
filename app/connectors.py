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

from abc import ABC, abstractmethod
from datetime import date as date_cls
from datetime import datetime

from app import db
from app.scheduling import available_slots, day_bounds

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


def get_connector(tenant: dict | None) -> ClinicConnector:
    """Resolve the connector for a tenant. For now always NativeConnector; later this
    dispatches on tenant['connector_type'] (cliniko, google_calendar, fhir, …)."""
    tenant_id = (tenant or {}).get("id") or 0
    # Future: ctype = (tenant or {}).get("connector_type") -> build the right adapter.
    return NativeConnector(tenant_id)
