"""Postgres data layer (psycopg3 + sync connection pool).

All functions are synchronous and pool-backed. The async webhook calls them via
`asyncio.to_thread`; the agent loop already runs in a worker thread, so its tool
handlers call these directly. This keeps a single, simple DB surface.
"""
import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL, DB_POOL_MAX, DB_POOL_MIN

log = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS patients (
    id          BIGSERIAL PRIMARY KEY,
    wa_user     TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id          BIGSERIAL PRIMARY KEY,
    wa_user     TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    message     TEXT NOT NULL,
    intent      TEXT,
    needs_human BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(wa_user, created_at);

CREATE TABLE IF NOT EXISTS appointments (
    id          BIGSERIAL PRIMARY KEY,
    wa_user     TEXT NOT NULL,
    patient_name TEXT,
    phone       TEXT,
    doctor      TEXT NOT NULL,
    service     TEXT NOT NULL,
    start_at    TIMESTAMPTZ NOT NULL,
    end_at      TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL DEFAULT 'confirmed'
                CHECK (status IN ('confirmed', 'cancelled', 'completed', 'no_show')),
    notes       TEXT,
    extra       JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_appt_doctor_time ON appointments(doctor, start_at);
CREATE INDEX IF NOT EXISTS idx_appt_user ON appointments(wa_user, start_at);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_messages(processed_at);

-- One row per no-show: tracks the recovery outreach (notify -> follow-up -> inactive),
-- the patient's chosen outcome, the reason they missed, and a risk snapshot.
CREATE TABLE IF NOT EXISTS no_show_followups (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      BIGINT,
    appointment_id BIGINT NOT NULL UNIQUE,
    wa_user        TEXT NOT NULL,
    stage          TEXT NOT NULL DEFAULT 'detected'
                   CHECK (stage IN ('detected', 'notified', 'followed_up', 'resolved', 'inactive')),
    outcome        TEXT,    -- reschedule | call | cancel
    reason         TEXT,    -- forgot | busy | emergency | price | other_clinic | other
    risk_score     INTEGER,
    risk_band      TEXT,
    notified_at    TIMESTAMPTZ,
    followup_at    TIMESTAMPTZ,
    resolved_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_noshow_tenant_stage ON no_show_followups(tenant_id, stage);
CREATE INDEX IF NOT EXISTS idx_noshow_tenant_created ON no_show_followups(tenant_id, created_at DESC);

-- Cached AI analysis of a conversation: a receptionist-style summary plus a Hot/Warm/Cold
-- lead score. One row per (tenant, patient); rebuilt when the message count changes.
CREATE TABLE IF NOT EXISTS conversation_analysis (
    tenant_id              BIGINT NOT NULL,
    wa_user                TEXT NOT NULL,
    customer_name          TEXT,
    requested_service      TEXT,
    appointment_preference TEXT,
    urgency                TEXT,    -- low | medium | high
    sentiment              TEXT,    -- positive | neutral | negative
    next_action            TEXT,
    lead_band              TEXT,    -- hot | warm | cold
    lead_score             INTEGER, -- 0-100
    lead_rationale         TEXT,
    message_count          INTEGER NOT NULL DEFAULT 0,
    source                 TEXT NOT NULL DEFAULT 'ai',   -- ai | heuristic (LLM fallback)
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, wa_user)
);

-- Idempotency log for the scheduled insights digest: one row per (tenant, kind) holding
-- the last date a digest was sent, so a restart or a 30-min tick can't double-send.
CREATE TABLE IF NOT EXISTS digest_log (
    tenant_id BIGINT NOT NULL,
    kind      TEXT NOT NULL,    -- day | week
    sent_on   DATE NOT NULL,
    PRIMARY KEY (tenant_id, kind)
);

-- Post-visit reputation management: one review request per completed appointment, with
-- the 1-5 star rating the patient replies with.
CREATE TABLE IF NOT EXISTS reviews (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      BIGINT,
    appointment_id BIGINT UNIQUE,
    wa_user        TEXT NOT NULL,
    rating         INTEGER,    -- 1-5, null until the patient responds
    comment        TEXT,
    stage          TEXT NOT NULL DEFAULT 'requested',  -- requested | done
    requested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_tenant ON reviews(tenant_id, created_at DESC);

-- --- Multi-tenant SaaS: plans, tenants, usage metering ---
CREATE TABLE IF NOT EXISTS plans (
    id                   BIGSERIAL PRIMARY KEY,
    name                 TEXT UNIQUE NOT NULL,
    monthly_text_quota   INTEGER,    -- NULL = unlimited
    voice_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
    monthly_voice_quota  INTEGER,    -- NULL = unlimited (when voice_enabled)
    features             JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_trial             BOOLEAN NOT NULL DEFAULT FALSE,
    trial_days           INTEGER,
    price_sar            NUMERIC,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenants (
    id                 BIGSERIAL PRIMARY KEY,
    name               TEXT NOT NULL,
    slug               TEXT UNIQUE NOT NULL,
    wa_phone_number_id TEXT UNIQUE,
    wa_access_token    TEXT,
    clinic_data        JSONB,
    staff_username     TEXT,
    staff_password_hash TEXT,
    plan_id            BIGINT REFERENCES plans(id),
    status             TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'suspended', 'expired')),
    trial_ends_at      TIMESTAMPTZ,
    timezone           TEXT NOT NULL DEFAULT 'Asia/Riyadh',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_events (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT,
    level       TEXT NOT NULL DEFAULT 'error',   -- error | warning | info
    category    TEXT NOT NULL,                    -- llm | whatsapp | tool | agent | transcription | quota | escalation
    message     TEXT NOT NULL,
    detail      TEXT,
    wa_user     TEXT,
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_events_open ON system_events(resolved, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_tenant ON system_events(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tenant_usage (
    tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
    period      TEXT NOT NULL,           -- 'YYYY-MM'
    text_count  INTEGER NOT NULL DEFAULT 0,
    voice_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, period)
);

ALTER TABLE patients      ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
-- 'text' | 'voice' — lets analytics distinguish transcribed voice notes from typed messages.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'text';
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS extra JSONB;
-- No-show prediction snapshot + extra-reminder bookkeeping.
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS risk_score INTEGER;
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS risk_band TEXT;
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS reminded_at TIMESTAMPTZ;
ALTER TABLE tenants       ADD COLUMN IF NOT EXISTS wa_access_token TEXT;
ALTER TABLE tenants       ADD COLUMN IF NOT EXISTS clinic_data JSONB;
ALTER TABLE tenants       ADD COLUMN IF NOT EXISTS staff_username TEXT;
ALTER TABLE tenants       ADD COLUMN IF NOT EXISTS staff_password_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_staff_username ON tenants(staff_username);
CREATE INDEX IF NOT EXISTS idx_conv_tenant ON conversations(tenant_id, created_at);
-- A patient phone is unique per clinic, not globally (two clinics may share a patient).
ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_wa_user_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_patients_tenant_wa ON patients(tenant_id, wa_user);
"""

# (name, text_quota, voice_enabled, voice_quota, is_trial, trial_days, price_sar)
DEFAULT_PLANS = [
    ("Trial", 50, False, None, True, 14, 0),
    ("Basic", 1000, False, None, False, None, 199),
    ("Pro", 5000, True, 500, False, None, 499),
    ("Unlimited", None, True, None, False, None, 999),
]

_pool: ConnectionPool | None = None


def init_db() -> None:
    """Open the connection pool and apply the schema. Idempotent."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=DB_POOL_MIN,
            max_size=DB_POOL_MAX,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        _pool.wait()
        log.info("DB pool opened (min=%s max=%s)", DB_POOL_MIN, DB_POOL_MAX)
    with get_conn() as conn:
        conn.execute(DDL)
    seed_tenancy()
    log.info("DB schema ready")


def seed_tenancy() -> None:
    """Create default plans and the first tenant (the current clinic) if absent,
    then backfill tenant_id on any legacy rows. Idempotent."""
    from psycopg.types.json import Json

    from app.config import CLINIC_DATA, TIMEZONE, WA_PHONE_NUMBER_ID

    clinic_name = CLINIC_DATA.get("clinic", {}).get("name", "Clinic")
    with get_conn() as conn:
        for name, tq, ve, vq, tr, td, price in DEFAULT_PLANS:
            conn.execute(
                "INSERT INTO plans (name, monthly_text_quota, voice_enabled, "
                "monthly_voice_quota, is_trial, trial_days, price_sar) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
                (name, tq, ve, vq, tr, td, price),
            )
        row = conn.execute("SELECT id FROM tenants WHERE slug = 'default'").fetchone()
        if not row:
            plan = conn.execute("SELECT id FROM plans WHERE name = 'Unlimited'").fetchone()
            row = conn.execute(
                "INSERT INTO tenants (name, slug, wa_phone_number_id, clinic_data, "
                "plan_id, status, timezone) "
                "VALUES (%s, 'default', %s, %s, %s, 'active', %s) RETURNING id",
                (clinic_name, WA_PHONE_NUMBER_ID, Json(CLINIC_DATA),
                 plan["id"] if plan else None, TIMEZONE),
            ).fetchone()
            log.info("Seeded default tenant '%s' (id=%s)", clinic_name, row["id"])
        tid = row["id"]
        # Backfill clinic_data on the default tenant if it predates the column. Leave
        # wa_access_token NULL so the default tenant always uses the live env token.
        conn.execute(
            "UPDATE tenants SET clinic_data = %s WHERE slug = 'default' AND clinic_data IS NULL",
            (Json(CLINIC_DATA),))
        for table in ("patients", "conversations", "appointments"):
            conn.execute(
                f"UPDATE {table} SET tenant_id = %s WHERE tenant_id IS NULL", (tid,)
            )


def close_db() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn():
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db() first")
    with _pool.connection() as conn:
        yield conn


def ping() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        log.exception("DB ping failed")
        return False


# --- Messages / conversations ---

def log_message(tenant_id: int, wa_user: str, direction: str, message: str,
                intent: str | None = None, needs_human: bool = False,
                source: str = "text") -> int:
    """Insert a message and return its id (so the caller can backfill the detected
    intent onto an inbound row once the agent has classified the turn)."""
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO conversations (tenant_id, wa_user, direction, message, intent, "
            "needs_human, source) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, wa_user, direction, message, intent, needs_human, source),
        ).fetchone()["id"]


def set_message_intent(message_id: int, intent: str | None) -> None:
    """Backfill the detected intent on a message (used to tag the inbound voice/text
    note with the turn's classification for analytics)."""
    if not message_id or not intent:
        return
    with get_conn() as conn:
        conn.execute("UPDATE conversations SET intent = %s WHERE id = %s", (intent, message_id))


def recent_history(tenant_id: int, wa_user: str, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT direction, message FROM conversations "
            "WHERE tenant_id = %s AND wa_user = %s ORDER BY id DESC LIMIT %s",
            (tenant_id, wa_user, limit),
        ).fetchall()
    return list(reversed(rows))


def claim_message_id(message_id: str) -> bool:
    """True the first time we see message_id, False on duplicate (idempotent webhooks)."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO processed_messages (message_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (message_id,),
        )
        return cur.rowcount > 0


def prune_processed_messages(older_than_hours: int = 24) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM processed_messages "
            "WHERE processed_at < now() - make_interval(hours => %s)",
            (older_than_hours,),
        )
        return cur.rowcount


# --- Patients ---

def upsert_patient(tenant_id: int, wa_user: str, name: str | None) -> None:
    with get_conn() as conn:
        if name:
            conn.execute(
                "INSERT INTO patients (tenant_id, wa_user, name) VALUES (%s, %s, %s) "
                "ON CONFLICT (tenant_id, wa_user) DO UPDATE SET "
                "name = EXCLUDED.name, updated_at = now()",
                (tenant_id, wa_user, name),
            )
        else:
            conn.execute(
                "INSERT INTO patients (tenant_id, wa_user) VALUES (%s, %s) "
                "ON CONFLICT (tenant_id, wa_user) DO NOTHING",
                (tenant_id, wa_user),
            )


def get_patient_name(tenant_id: int, wa_user: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM patients WHERE tenant_id = %s AND wa_user = %s",
            (tenant_id, wa_user),
        ).fetchone()
    return row["name"] if row else None


# --- Appointments ---

def booked_intervals(tenant_id: int, doctor: str, day_start: datetime,
                     day_end: datetime) -> list[tuple]:
    """(start_at, end_at) of active appointments for a doctor within [day_start, day_end)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT start_at, end_at FROM appointments "
            "WHERE tenant_id = %s AND doctor = %s AND status = 'confirmed' "
            "AND start_at < %s AND end_at > %s ORDER BY start_at",
            (tenant_id, doctor, day_end, day_start),
        ).fetchall()
    return [(r["start_at"], r["end_at"]) for r in rows]


def create_appointment(tenant_id: int, wa_user: str, patient_name: str | None,
                       phone: str | None, doctor: str, service: str, start_at: datetime,
                       end_at: datetime, notes: str | None = None,
                       extra: dict | None = None) -> dict:
    """Atomically book a slot. Returns the new row, or {'conflict': True} if the
    doctor is already booked in an overlapping window (within this tenant)."""
    from psycopg.types.json import Json
    with get_conn() as conn:
        with conn.transaction():
            clash = conn.execute(
                "SELECT id FROM appointments WHERE tenant_id = %s AND doctor = %s "
                "AND status = 'confirmed' AND start_at < %s AND end_at > %s FOR UPDATE",
                (tenant_id, doctor, end_at, start_at),
            ).fetchone()
            if clash:
                return {"conflict": True}
            row = conn.execute(
                "INSERT INTO appointments "
                "(tenant_id, wa_user, patient_name, phone, doctor, service, start_at, end_at, "
                "notes, extra) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (tenant_id, wa_user, patient_name, phone, doctor, service, start_at, end_at,
                 notes, Json(extra) if extra else None),
            ).fetchone()
    return row


def upcoming_appointments(tenant_id: int, wa_user: str, now: datetime,
                          limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM appointments WHERE tenant_id = %s AND wa_user = %s "
            "AND status = 'confirmed' AND end_at >= %s ORDER BY start_at ASC LIMIT %s",
            (tenant_id, wa_user, now, limit),
        ).fetchall()
    return rows


def recent_appointments_for_user(tenant_id: int, wa_user: str, limit: int = 3) -> list[dict]:
    """A returning patient's most recent appointments (any status), newest first — so the
    AI can recall 'your last visit was with Dr. X' and offer to rebook."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT doctor, service, start_at, status FROM appointments "
            "WHERE tenant_id = %s AND wa_user = %s ORDER BY start_at DESC LIMIT %s",
            (tenant_id, wa_user, limit),
        ).fetchall()


def has_appointment(tenant_id: int, wa_user: str) -> bool:
    """Whether this patient has ever booked (any status) — a strong lead signal."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM appointments WHERE tenant_id = %s AND wa_user = %s LIMIT 1",
            (tenant_id, wa_user),
        ).fetchone() is not None


def get_appointment(tenant_id: int, appointment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE tenant_id = %s AND id = %s",
            (tenant_id, appointment_id),
        ).fetchone()


def get_appointment_by_id(appointment_id: int) -> dict | None:
    """Fetch an appointment without tenant scoping — used by the super-admin dashboard
    (which sees all tenants) to read details before a status change."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE id = %s", (appointment_id,)
        ).fetchone()


def set_appointment_status(tenant_id: int, appointment_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET status = %s, updated_at = now() "
            "WHERE tenant_id = %s AND id = %s",
            (status, tenant_id, appointment_id),
        )


def record_event(level: str, category: str, message: str, *, detail: str | None = None,
                 tenant_id: int | None = None, wa_user: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO system_events (tenant_id, level, category, message, detail, wa_user) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_id, level, category, message, (detail or "")[:2000], wa_user),
        )


def list_events(resolved: bool | None = None, level: str | None = None,
                tenant_id: int | None = None, limit: int = 200) -> list[dict]:
    clauses, params = [], []
    if tenant_id is not None:
        clauses.append("tenant_id = %s")
        params.append(tenant_id)
    if resolved is not None:
        clauses.append("resolved = %s")
        params.append(resolved)
    if level:
        clauses.append("level = %s")
        params.append(level)
    sql = "SELECT * FROM system_events"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def resolve_event(event_id: int, tenant_id: int | None = None) -> None:
    with get_conn() as conn:
        if tenant_id is None:
            conn.execute(
                "UPDATE system_events SET resolved = TRUE, resolved_at = now() WHERE id = %s",
                (event_id,))
        else:
            conn.execute(
                "UPDATE system_events SET resolved = TRUE, resolved_at = now() "
                "WHERE id = %s AND tenant_id = %s", (event_id, tenant_id))


def prune_resolved_events(older_than_days: int = 30) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM system_events WHERE resolved = TRUE "
            "AND resolved_at < now() - make_interval(days => %s)",
            (older_than_days,),
        )
        return cur.rowcount


def unresolved_event_count(tenant_id: int | None = None) -> int:
    where = "WHERE resolved = FALSE"
    params: tuple = ()
    if tenant_id is not None:
        where += " AND tenant_id = %s"
        params = (tenant_id,)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT COUNT(*) AS n FROM system_events {where}", params).fetchone()["n"]


def admin_set_appointment_status(appointment_id: int, status: str) -> None:
    """Super-admin status change by id (not tenant-scoped) — used by the dashboard."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET status = %s, updated_at = now() WHERE id = %s",
            (status, appointment_id),
        )


def reschedule(tenant_id: int, appointment_id: int, start_at: datetime,
               end_at: datetime) -> dict:
    """Move an appointment to a new window if free. Returns updated row or {'conflict': True}."""
    with get_conn() as conn:
        with conn.transaction():
            appt = conn.execute(
                "SELECT * FROM appointments WHERE tenant_id = %s AND id = %s FOR UPDATE",
                (tenant_id, appointment_id),
            ).fetchone()
            if not appt:
                return {"not_found": True}
            clash = conn.execute(
                "SELECT id FROM appointments WHERE tenant_id = %s AND doctor = %s "
                "AND status = 'confirmed' AND id <> %s AND start_at < %s AND end_at > %s FOR UPDATE",
                (tenant_id, appt["doctor"], appointment_id, end_at, start_at),
            ).fetchone()
            if clash:
                return {"conflict": True}
            row = conn.execute(
                "UPDATE appointments SET start_at = %s, end_at = %s, "
                "status = 'confirmed', updated_at = now() WHERE id = %s RETURNING *",
                (start_at, end_at, appointment_id),
            ).fetchone()
    return row


# --- No-shows & risk prediction ---

# A patient who replied since `ts` should no longer get automated nagging.
_NO_INBOUND_SINCE = (
    "NOT EXISTS (SELECT 1 FROM conversations c WHERE c.tenant_id = f.tenant_id "
    "AND c.wa_user = f.wa_user AND c.direction = 'in' AND c.created_at > %s)"
)


def all_active_tenants() -> list[dict]:
    """Every active tenant's WhatsApp creds, timezone and clinic data — the sweep
    needs these to message patients on the right number per clinic."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, slug, wa_phone_number_id, wa_access_token, timezone, clinic_data "
            "FROM tenants WHERE status = 'active'"
        ).fetchall()


def patient_history_stats(tenant_id: int, wa_user: str,
                          exclude_appointment_id: int | None = None) -> dict:
    """Counts that feed the no-show risk score: prior no-shows, cancellations and
    completed visits for this patient at this clinic."""
    sql = ("SELECT "
           "COUNT(*) FILTER (WHERE status = 'no_show')   AS no_shows, "
           "COUNT(*) FILTER (WHERE status = 'cancelled') AS cancellations, "
           "COUNT(*) FILTER (WHERE status = 'completed') AS completed "
           "FROM appointments WHERE tenant_id = %s AND wa_user = %s")
    params: tuple = (tenant_id, wa_user)
    if exclude_appointment_id is not None:
        sql += " AND id <> %s"
        params += (exclude_appointment_id,)
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
    return {"no_shows": row["no_shows"], "cancellations": row["cancellations"],
            "completed": row["completed"]}


def set_appointment_risk(tenant_id: int, appointment_id: int, score: int, band: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET risk_score = %s, risk_band = %s WHERE tenant_id = %s AND id = %s",
            (score, band, tenant_id, appointment_id),
        )


def find_no_shows(cutoff: datetime) -> list[dict]:
    """Confirmed appointments whose end time passed (before `cutoff`) and that don't
    yet have a no-show record — i.e. the patient never checked in. Across all tenants."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT a.* FROM appointments a "
            "LEFT JOIN no_show_followups f ON f.appointment_id = a.id "
            "WHERE a.status = 'confirmed' AND a.end_at < %s AND f.id IS NULL "
            "ORDER BY a.end_at ASC LIMIT 200",
            (cutoff,),
        ).fetchall()


def mark_no_show(tenant_id: int, appointment_id: int, wa_user: str,
                 risk_score: int | None, risk_band: str | None) -> dict | None:
    """Atomically flip an appointment to no_show and open its follow-up record.
    Returns the new follow-up row, or None if one already exists (raced)."""
    with get_conn() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE appointments SET status = 'no_show', updated_at = now() "
                "WHERE tenant_id = %s AND id = %s AND status = 'confirmed'",
                (tenant_id, appointment_id),
            )
            return conn.execute(
                "INSERT INTO no_show_followups "
                "(tenant_id, appointment_id, wa_user, risk_score, risk_band) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (appointment_id) DO NOTHING "
                "RETURNING *",
                (tenant_id, appointment_id, wa_user, risk_score, risk_band),
            ).fetchone()


def open_no_show_followup(tenant_id: int, wa_user: str) -> dict | None:
    """The patient's most recent unresolved no-show outreach, with the missed
    appointment's details — so the agent can handle their reply in context."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT f.id, f.appointment_id, f.stage, a.doctor, a.service, a.start_at "
            "FROM no_show_followups f JOIN appointments a ON a.id = f.appointment_id "
            "WHERE f.tenant_id = %s AND f.wa_user = %s "
            "AND f.stage IN ('detected', 'notified', 'followed_up') "
            "ORDER BY f.created_at DESC LIMIT 1",
            (tenant_id, wa_user),
        ).fetchone()


def set_followup_stage(followup_id: int, stage: str, *, stamp: str | None = None) -> None:
    """Advance a follow-up's stage. `stamp` optionally sets notified_at/followup_at/
    resolved_at to now() in the same write."""
    cols = "stage = %s, updated_at = now()"
    params: list = [stage]
    if stamp in ("notified_at", "followup_at", "resolved_at"):
        cols += f", {stamp} = now()"
    params.append(followup_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE no_show_followups SET {cols} WHERE id = %s", tuple(params))


def followups_due_followup(cutoff: datetime) -> list[dict]:
    """Notified > cutoff ago with no patient reply since — send the day-later nudge."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT f.*, a.doctor, a.service, a.start_at FROM no_show_followups f "
            "JOIN appointments a ON a.id = f.appointment_id "
            "WHERE f.stage = 'notified' AND f.notified_at < %s AND "
            + _NO_INBOUND_SINCE.replace("%s", "f.notified_at"),
            (cutoff,),
        ).fetchall()


def followups_due_inactive(cutoff: datetime) -> list[dict]:
    """Followed-up > cutoff ago, still silent — the lead goes inactive."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT f.* FROM no_show_followups f "
            "WHERE f.stage = 'followed_up' AND f.followup_at < %s AND "
            + _NO_INBOUND_SINCE.replace("%s", "f.followup_at"),
            (cutoff,),
        ).fetchall()


def record_no_show_response(tenant_id: int, appointment_id: int,
                            outcome: str | None = None, reason: str | None = None) -> bool:
    """Store the patient's chosen outcome and/or stated reason on the follow-up and
    resolve it. Only fills fields that are provided. Returns True if a row matched."""
    # Build SET clauses and params in the SAME order so the placeholders line up.
    sets, params = [], []
    if outcome:
        sets.append("outcome = %s")
        params.append(outcome)
    if reason:
        sets.append("reason = %s")
        params.append(reason)
    sets += ["stage = 'resolved'", "resolved_at = now()", "updated_at = now()"]
    params += [tenant_id, appointment_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE no_show_followups SET {', '.join(sets)} "
            "WHERE tenant_id = %s AND appointment_id = %s AND stage <> 'inactive'",
            tuple(params),
        )
        return cur.rowcount > 0


def resolve_followup_for_appointment(tenant_id: int, appointment_id: int,
                                     outcome: str) -> None:
    """Auto-close a no-show follow-up when the patient reschedules/cancels via a tool,
    so analytics capture the outcome even if the model didn't log it explicitly.
    Never overwrites an outcome already set by record_no_show_response."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE no_show_followups SET outcome = COALESCE(outcome, %s), "
            "stage = 'resolved', resolved_at = now(), updated_at = now() "
            "WHERE tenant_id = %s AND appointment_id = %s "
            "AND stage IN ('detected', 'notified', 'followed_up')",
            (outcome, tenant_id, appointment_id),
        )


def unscored_upcoming_appointments(now: datetime, limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE status = 'confirmed' "
            "AND start_at > %s AND risk_score IS NULL ORDER BY start_at ASC LIMIT %s",
            (now, limit),
        ).fetchall()


def high_risk_reminders_due(now: datetime, until: datetime) -> list[dict]:
    """High-risk confirmed appointments starting soon that haven't had the extra
    reminder yet — the premium predictor's preventive nudge."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE status = 'confirmed' AND risk_band = 'high' "
            "AND reminded_at IS NULL AND start_at > %s AND start_at <= %s "
            "ORDER BY start_at ASC LIMIT 200",
            (now, until),
        ).fetchall()


def upcoming_reminders_due(now: datetime, until: datetime) -> list[dict]:
    """ALL confirmed appointments starting within the window that haven't had a
    pre-appointment confirmation yet — the universal 'will you attend?' nudge."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE status = 'confirmed' "
            "AND reminded_at IS NULL AND start_at > %s AND start_at <= %s "
            "ORDER BY start_at ASC LIMIT 500",
            (now, until),
        ).fetchall()


def mark_reminded(tenant_id: int, appointment_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET reminded_at = now() WHERE tenant_id = %s AND id = %s",
            (tenant_id, appointment_id),
        )


# --- No-show dashboard ---

def get_followup(followup_id: int, tenant_id: int | None = None) -> dict | None:
    sql = ("SELECT f.*, a.doctor, a.service, a.start_at, a.patient_name "
           "FROM no_show_followups f JOIN appointments a ON a.id = f.appointment_id "
           "WHERE f.id = %s")
    params: tuple = (followup_id,)
    if tenant_id is not None:
        sql += " AND f.tenant_id = %s"
        params += (tenant_id,)
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()


def list_no_show_followups(tenant_id: int | None = None, limit: int = 200) -> list[dict]:
    sql = ("SELECT f.id, f.appointment_id, f.wa_user, f.stage, f.outcome, f.reason, "
           "f.risk_score, f.risk_band, f.created_at, f.notified_at, "
           "a.doctor, a.service, a.start_at, a.patient_name "
           "FROM no_show_followups f JOIN appointments a ON a.id = f.appointment_id")
    params: list = []
    if tenant_id is not None:
        sql += " WHERE f.tenant_id = %s"
        params.append(tenant_id)
    sql += " ORDER BY f.created_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def no_show_count_since(since: datetime, tenant_id: int | None = None) -> int:
    where = "WHERE created_at >= %s"
    params: list = [since]
    if tenant_id is not None:
        where += " AND tenant_id = %s"
        params.append(tenant_id)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT COUNT(*) AS n FROM no_show_followups {where}", tuple(params)
        ).fetchone()["n"]


def no_show_reason_breakdown(since: datetime, tenant_id: int | None = None) -> list[dict]:
    where = "WHERE created_at >= %s AND reason IS NOT NULL"
    params: list = [since]
    if tenant_id is not None:
        where += " AND tenant_id = %s"
        params.append(tenant_id)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT reason, COUNT(*) AS n FROM no_show_followups {where} "
            "GROUP BY reason ORDER BY n DESC", tuple(params)
        ).fetchall()


def risk_band_counts(tenant_id: int | None = None) -> dict:
    """How many upcoming confirmed appointments fall in each risk band — the
    predictor overview on the dashboard."""
    where = "WHERE status = 'confirmed' AND start_at > now() AND risk_band IS NOT NULL"
    params: tuple = ()
    if tenant_id is not None:
        where += " AND tenant_id = %s"
        params = (tenant_id,)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT risk_band, COUNT(*) AS n FROM appointments {where} GROUP BY risk_band",
            params,
        ).fetchall()
    out = {"low": 0, "medium": 0, "high": 0}
    for r in rows:
        if r["risk_band"] in out:
            out[r["risk_band"]] = r["n"]
    return out


# --- Admin queries ---

def list_conversations(limit: int = 100, tenant_id: int | None = None) -> list[dict]:
    # When scoped to a clinic, the correlated subqueries must also filter by tenant,
    # or a shared phone would leak another clinic's last message/intent.
    if tenant_id is not None:
        sub = "AND c2.tenant_id = %s"
        sub3 = "AND c3.tenant_id = %s"
        sub4 = "AND c4.tenant_id = %s"
        sub5 = "AND ca.tenant_id = %s"
        where = "WHERE c.tenant_id = %s"
        params: tuple = (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, limit)
    else:
        sub = sub3 = sub4 = sub5 = where = ""
        params = (limit,)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT c.wa_user,
                      MAX(c.created_at) AS last_at,
                      COUNT(*) AS msg_count,
                      bool_or(c.needs_human) AS needs_human,
                      (SELECT message FROM conversations c2
                        WHERE c2.wa_user = c.wa_user {sub} ORDER BY id DESC LIMIT 1) AS last_message,
                      (SELECT direction FROM conversations c3
                        WHERE c3.wa_user = c.wa_user {sub3} ORDER BY id DESC LIMIT 1) AS last_direction,
                      (SELECT intent FROM conversations c4
                        WHERE c4.wa_user = c.wa_user {sub4} AND c4.direction = 'out'
                          AND c4.intent IS NOT NULL ORDER BY id DESC LIMIT 1) AS last_intent,
                      (SELECT lead_band FROM conversation_analysis ca
                        WHERE ca.wa_user = c.wa_user {sub5} LIMIT 1) AS lead_band
               FROM conversations c {where}
               GROUP BY c.wa_user
               ORDER BY last_at DESC
               LIMIT %s""",
            params,
        ).fetchall()
    return rows


def tenant_id_for_user(wa_user: str) -> int | None:
    """The tenant of a patient's most recent message — lets the super-admin view build
    tenant-scoped analysis for a conversation it isn't itself scoped to."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM conversations WHERE wa_user = %s ORDER BY id DESC LIMIT 1",
            (wa_user,),
        ).fetchone()
    return row["tenant_id"] if row else None


def conversation_thread(wa_user: str, limit: int = 200,
                        tenant_id: int | None = None) -> list[dict]:
    # Take the MOST RECENT `limit` messages (newest first), then flip to chronological
    # order for display. A plain "ORDER BY id ASC LIMIT" returns the OLDEST messages, which
    # hides recent activity once a thread exceeds the limit.
    inner = ("SELECT id, direction, message, intent, needs_human, source, created_at "
             "FROM conversations WHERE wa_user = %s")
    params: tuple = (wa_user,)
    if tenant_id is not None:
        inner += " AND tenant_id = %s"
        params += (tenant_id,)
    inner += " ORDER BY id DESC LIMIT %s"
    sql = f"SELECT * FROM ({inner}) recent ORDER BY id ASC"
    with get_conn() as conn:
        rows = conn.execute(sql, params + (limit,)).fetchall()
    return rows


def list_appointments(status: str | None = None, limit: int = 200,
                      tenant_id: int | None = None) -> list[dict]:
    sql = ("SELECT id, wa_user, patient_name, phone, doctor, service, start_at, end_at, "
           "status, notes, extra, risk_score, risk_band, created_at FROM appointments")
    clauses, params = [], []
    if tenant_id is not None:
        clauses.append("tenant_id = %s")
        params.append(tenant_id)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY start_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return rows


def stats(tenant_id: int | None = None) -> dict:
    w = "WHERE tenant_id = %s" if tenant_id is not None else ""
    wa = "AND tenant_id = %s" if tenant_id is not None else ""
    p = (tenant_id,) if tenant_id is not None else ()
    with get_conn() as conn:
        msgs = conn.execute(f"SELECT COUNT(*) AS n FROM conversations {w}", p).fetchone()["n"]
        users = conn.execute(
            f"SELECT COUNT(DISTINCT wa_user) AS n FROM conversations {w}", p).fetchone()["n"]
        appts = conn.execute(
            f"SELECT COUNT(*) AS n FROM appointments WHERE status = 'confirmed' {wa}", p
        ).fetchone()["n"]
        upcoming = conn.execute(
            f"SELECT COUNT(*) AS n FROM appointments "
            f"WHERE status = 'confirmed' AND start_at >= now() {wa}", p
        ).fetchone()["n"]
        needs_human = conn.execute(
            f"SELECT COUNT(DISTINCT wa_user) AS n FROM conversations WHERE needs_human = TRUE {wa}", p
        ).fetchone()["n"]
    return {"messages": msgs, "users": users, "appointments": appts,
            "upcoming_appointments": upcoming, "needs_human_users": needs_human}


# --- Conversation analysis (AI summary + lead score) ---

def message_count(tenant_id: int, wa_user: str) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM conversations WHERE tenant_id = %s AND wa_user = %s",
            (tenant_id, wa_user),
        ).fetchone()["n"]


def get_conversation_analysis(tenant_id: int, wa_user: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM conversation_analysis WHERE tenant_id = %s AND wa_user = %s",
            (tenant_id, wa_user),
        ).fetchone()


def upsert_conversation_analysis(tenant_id: int, wa_user: str, data: dict,
                                 msg_count: int, source: str = "ai") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_analysis "
            "(tenant_id, wa_user, customer_name, requested_service, appointment_preference, "
            " urgency, sentiment, next_action, lead_band, lead_score, lead_rationale, "
            " message_count, source, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now()) "
            "ON CONFLICT (tenant_id, wa_user) DO UPDATE SET "
            "customer_name = EXCLUDED.customer_name, "
            "requested_service = EXCLUDED.requested_service, "
            "appointment_preference = EXCLUDED.appointment_preference, "
            "urgency = EXCLUDED.urgency, sentiment = EXCLUDED.sentiment, "
            "next_action = EXCLUDED.next_action, lead_band = EXCLUDED.lead_band, "
            "lead_score = EXCLUDED.lead_score, lead_rationale = EXCLUDED.lead_rationale, "
            "message_count = EXCLUDED.message_count, source = EXCLUDED.source, "
            "updated_at = now()",
            (tenant_id, wa_user, data.get("customer_name"), data.get("requested_service"),
             data.get("appointment_preference"), data.get("urgency"), data.get("sentiment"),
             data.get("next_action"), data.get("lead_band"), data.get("lead_score"),
             data.get("lead_rationale"), msg_count, source),
        )


def claim_digest(tenant_id: int, kind: str, on_date) -> bool:
    """Atomically claim today's digest for (tenant, kind). True the first time for a
    given date, False if it was already sent — prevents double-sends across ticks/restarts."""
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO digest_log (tenant_id, kind, sent_on) VALUES (%s, %s, %s) "
            "ON CONFLICT (tenant_id, kind) DO UPDATE SET sent_on = EXCLUDED.sent_on "
            "WHERE digest_log.sent_on < EXCLUDED.sent_on RETURNING tenant_id",
            (tenant_id, kind, on_date),
        ).fetchone()
    return row is not None


def lead_band_counts(tenant_id: int | None = None) -> dict:
    where = ""
    params: tuple = ()
    if tenant_id is not None:
        where = "WHERE tenant_id = %s"
        params = (tenant_id,)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT lead_band, COUNT(*) AS n FROM conversation_analysis {where} "
            "GROUP BY lead_band", params,
        ).fetchall()
    out = {"hot": 0, "warm": 0, "cold": 0}
    for r in rows:
        if r["lead_band"] in out:
            out[r["lead_band"]] = r["n"]
    return out


# --- Reviews (post-visit reputation management) ---

def create_review_request(tenant_id: int, appointment_id: int, wa_user: str) -> dict | None:
    """Open a review request for a completed appointment. Returns the row, or None if one
    already exists (so we don't re-ask)."""
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO reviews (tenant_id, appointment_id, wa_user) VALUES (%s, %s, %s) "
            "ON CONFLICT (appointment_id) DO NOTHING RETURNING *",
            (tenant_id, appointment_id, wa_user),
        ).fetchone()


def open_review_request(tenant_id: int, wa_user: str) -> dict | None:
    """The patient's most recent un-answered review request, with the visit details — so
    the agent can interpret a 1-5 reply as that visit's rating."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT r.id, r.appointment_id, a.doctor, a.service FROM reviews r "
            "JOIN appointments a ON a.id = r.appointment_id "
            "WHERE r.tenant_id = %s AND r.wa_user = %s AND r.stage = 'requested' "
            "ORDER BY r.created_at DESC LIMIT 1",
            (tenant_id, wa_user),
        ).fetchone()


def record_review(tenant_id: int, appointment_id: int, rating: int,
                  comment: str | None = None) -> bool:
    """Store a 1-5 rating (+ optional comment) and close the request. Returns True if a
    pending request matched."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE reviews SET rating = %s, comment = COALESCE(%s, comment), "
            "stage = 'done', responded_at = now() "
            "WHERE tenant_id = %s AND appointment_id = %s AND stage = 'requested'",
            (rating, comment, tenant_id, appointment_id),
        )
        return cur.rowcount > 0


def list_reviews(tenant_id: int | None = None, limit: int = 200) -> list[dict]:
    sql = ("SELECT r.id, r.wa_user, r.rating, r.comment, r.stage, r.responded_at, "
           "r.created_at, a.doctor, a.service, a.patient_name "
           "FROM reviews r JOIN appointments a ON a.id = r.appointment_id")
    params: list = []
    if tenant_id is not None:
        sql += " WHERE r.tenant_id = %s"
        params.append(tenant_id)
    sql += " ORDER BY r.created_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def review_stats(tenant_id: int | None = None) -> dict:
    where = ""
    params: tuple = ()
    if tenant_id is not None:
        where = "WHERE tenant_id = %s"
        params = (tenant_id,)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE stage = 'done') AS responded, "
            "COUNT(*) AS requested, "
            "AVG(rating) FILTER (WHERE rating IS NOT NULL) AS avg_rating "
            f"FROM reviews {where}", params,
        ).fetchone()
    avg = float(row["avg_rating"]) if row["avg_rating"] is not None else None
    return {"responded": row["responded"], "requested": row["requested"],
            "avg_rating": round(avg, 1) if avg is not None else None}


# --- Business insights (deterministic aggregates over a [since, until) window) ---

def insight_message_stats(tenant_id: int | None, since: datetime, until: datetime) -> dict:
    w, p = _scope_window(tenant_id, since, until)
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS messages, "
            "COUNT(*) FILTER (WHERE direction='in') AS inbound, "
            "COUNT(*) FILTER (WHERE direction='in' AND source='voice') AS voice_inbound, "
            "COUNT(DISTINCT wa_user) AS users "
            f"FROM conversations {w}", p,
        ).fetchone()


def insight_intent_counts(tenant_id: int | None, since: datetime, until: datetime) -> list[dict]:
    w, p = _scope_window(tenant_id, since, until)
    with get_conn() as conn:
        return conn.execute(
            "SELECT intent, COUNT(*) AS n FROM conversations "
            f"{w} AND direction='out' AND intent IS NOT NULL "
            "GROUP BY intent ORDER BY n DESC", p,
        ).fetchall()


def insight_peak_hours(tenant_id: int | None, since: datetime, until: datetime,
                       tz: str = "Asia/Riyadh") -> list[dict]:
    w, p = _scope_window(tenant_id, since, until)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE %s)::int AS hour, "
            "COUNT(*) AS n FROM conversations "
            f"{w} AND direction='in' GROUP BY hour ORDER BY n DESC",
            (tz, *p),
        ).fetchall()


def insight_conversion(tenant_id: int | None, since: datetime, until: datetime) -> dict:
    w, p = _scope_window(tenant_id, since, until)
    wa, pa = _scope_window(tenant_id, since, until, col="created_at")
    with get_conn() as conn:
        messaged = conn.execute(
            f"SELECT COUNT(DISTINCT wa_user) AS n FROM conversations {w}", p,
        ).fetchone()["n"]
        booked = conn.execute(
            f"SELECT COUNT(DISTINCT wa_user) AS n FROM appointments {wa}", pa,
        ).fetchone()["n"]
    rate = round(booked / messaged * 100) if messaged else 0
    return {"users_messaged": messaged, "users_booked": booked, "conversion_pct": rate}


def insight_top_doctors(tenant_id: int | None, since: datetime, until: datetime) -> list[dict]:
    """Most-requested doctors by bookings made in the window."""
    w, p = _scope_window(tenant_id, since, until, col="created_at")
    with get_conn() as conn:
        return conn.execute(
            f"SELECT doctor, COUNT(*) AS n FROM appointments {w} "
            "GROUP BY doctor ORDER BY n DESC LIMIT 5", p,
        ).fetchall()


def sentiment_counts(tenant_id: int | None = None) -> dict:
    """Conversation sentiment mix — negative is the clinic's 'complaints / at-risk' signal."""
    where = ""
    params: tuple = ()
    if tenant_id is not None:
        where = "WHERE tenant_id = %s"
        params = (tenant_id,)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT sentiment, COUNT(*) AS n FROM conversation_analysis {where} "
            "GROUP BY sentiment", params,
        ).fetchall()
    out = {"positive": 0, "neutral": 0, "negative": 0}
    for r in rows:
        if r["sentiment"] in out:
            out[r["sentiment"]] = r["n"]
    return out


def insight_handover_users(tenant_id: int | None, since: datetime, until: datetime) -> int:
    w, p = _scope_window(tenant_id, since, until)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT COUNT(DISTINCT wa_user) AS n FROM conversations {w} AND needs_human = TRUE",
            p,
        ).fetchone()["n"]


def _scope_window(tenant_id: int | None, since: datetime, until: datetime,
                  col: str = "created_at") -> tuple[str, tuple]:
    """WHERE clause + params for a tenant-scoped time window. Always starts with WHERE
    and ends open (callers may append `AND ...`)."""
    clauses = [f"{col} >= %s", f"{col} < %s"]
    params: list = [since, until]
    if tenant_id is not None:
        clauses.append("tenant_id = %s")
        params.append(tenant_id)
    return "WHERE " + " AND ".join(clauses), tuple(params)


# --- Tenancy / plans / usage ---

_TENANT_SELECT = (
    "SELECT t.*, p.name AS plan_name, p.monthly_text_quota, p.voice_enabled, "
    "p.monthly_voice_quota, p.is_trial, p.trial_days "
    "FROM tenants t LEFT JOIN plans p ON p.id = t.plan_id "
)


def get_tenant_by_phone(phone_number_id: str | None) -> dict | None:
    if not phone_number_id:
        return None
    with get_conn() as conn:
        return conn.execute(
            _TENANT_SELECT + "WHERE t.wa_phone_number_id = %s", (phone_number_id,)
        ).fetchone()


def get_default_tenant() -> dict | None:
    with get_conn() as conn:
        return conn.execute(_TENANT_SELECT + "WHERE t.slug = 'default'").fetchone()


def incr_usage(tenant_id: int, period: str, *, text: int = 0, voice: int = 0) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tenant_usage (tenant_id, period, text_count, voice_count) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, period) DO UPDATE SET "
            "text_count = tenant_usage.text_count + EXCLUDED.text_count, "
            "voice_count = tenant_usage.voice_count + EXCLUDED.voice_count",
            (tenant_id, period, text, voice),
        )


def get_usage(tenant_id: int, period: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT text_count, voice_count FROM tenant_usage "
            "WHERE tenant_id = %s AND period = %s",
            (tenant_id, period),
        ).fetchone()
    return row or {"text_count": 0, "voice_count": 0}


def list_plans() -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM plans ORDER BY COALESCE(price_sar, 0)").fetchall()


def upsert_plan(name: str, monthly_text_quota, voice_enabled: bool,
                monthly_voice_quota, is_trial: bool, trial_days, price_sar) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO plans (name, monthly_text_quota, voice_enabled, monthly_voice_quota, "
            "is_trial, trial_days, price_sar) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (name) DO UPDATE SET "
            "monthly_text_quota = EXCLUDED.monthly_text_quota, "
            "voice_enabled = EXCLUDED.voice_enabled, "
            "monthly_voice_quota = EXCLUDED.monthly_voice_quota, "
            "is_trial = EXCLUDED.is_trial, trial_days = EXCLUDED.trial_days, "
            "price_sar = EXCLUDED.price_sar",
            (name, monthly_text_quota, voice_enabled, monthly_voice_quota,
             is_trial, trial_days, price_sar),
        )


def list_tenants(period: str) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT t.id, t.name, t.slug, t.status, t.wa_phone_number_id, "
            "       p.name AS plan_name, p.monthly_text_quota, p.voice_enabled, "
            "       p.monthly_voice_quota, "
            "       COALESCE(u.text_count, 0) AS text_count, "
            "       COALESCE(u.voice_count, 0) AS voice_count "
            "FROM tenants t LEFT JOIN plans p ON p.id = t.plan_id "
            "LEFT JOIN tenant_usage u ON u.tenant_id = t.id AND u.period = %s "
            "ORDER BY t.id",
            (period,),
        ).fetchall()


def set_tenant_plan(tenant_id: int, plan_id: int) -> None:
    """Assign a plan. For trial plans, start the trial clock (now + trial_days);
    otherwise clear any trial expiry."""
    with get_conn() as conn:
        plan = conn.execute(
            "SELECT is_trial, trial_days FROM plans WHERE id = %s", (plan_id,)
        ).fetchone()
        if plan and plan["is_trial"] and plan["trial_days"]:
            conn.execute(
                "UPDATE tenants SET plan_id = %s, "
                "trial_ends_at = now() + make_interval(days => %s) WHERE id = %s",
                (plan_id, plan["trial_days"], tenant_id),
            )
        else:
            conn.execute(
                "UPDATE tenants SET plan_id = %s, trial_ends_at = NULL WHERE id = %s",
                (plan_id, tenant_id),
            )


def set_tenant_status(tenant_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE tenants SET status = %s WHERE id = %s", (status, tenant_id))


def create_tenant(name: str, slug: str, wa_phone_number_id: str | None, plan_id: int | None,
                  timezone: str, wa_access_token: str | None, clinic_data: dict | None) -> int:
    from psycopg.types.json import Json
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO tenants (name, slug, wa_phone_number_id, wa_access_token, "
            "clinic_data, plan_id, status, timezone) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'active', %s) RETURNING id",
            (name, slug, wa_phone_number_id or None, wa_access_token or None,
             Json(clinic_data) if clinic_data is not None else None, plan_id, timezone),
        ).fetchone()
    return row["id"]


def update_tenant_config(tenant_id: int, *, name: str, wa_phone_number_id: str | None,
                         wa_access_token: str | None, timezone: str,
                         clinic_data: dict | None) -> None:
    # clinic_data is a jsonb column; COALESCE needs both branches the SAME type, and
    # there's no implicit json->jsonb cast — so the parameter must be Jsonb, not Json,
    # or "COALESCE($5, clinic_data)" raises CannotCoerce (jsonb vs json).
    from psycopg.types.json import Jsonb
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenants SET name = %s, wa_phone_number_id = %s, wa_access_token = %s, "
            "timezone = %s, clinic_data = COALESCE(%s, clinic_data) WHERE id = %s",
            (name, wa_phone_number_id or None, wa_access_token or None, timezone,
             Jsonb(clinic_data) if clinic_data is not None else None, tenant_id),
        )


def get_tenant(tenant_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tenants WHERE id = %s", (tenant_id,)).fetchone()


def get_tenant_by_username(username: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tenants WHERE staff_username = %s", (username,)
        ).fetchone()


def staff_username_taken(username: str | None, exclude_tenant_id: int | None = None) -> bool:
    """True if another tenant already owns this staff login username (it's UNIQUE).
    `exclude_tenant_id` lets a clinic keep its own username when editing itself."""
    if not username:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM tenants WHERE staff_username = %s", (username,)
        ).fetchone()
    return bool(row and row["id"] != exclude_tenant_id)


def set_tenant_credentials(tenant_id: int, username: str | None,
                           password_hash: str | None) -> None:
    """Set/clear a clinic's staff login. Password hash is only updated when provided."""
    with get_conn() as conn:
        if password_hash is not None:
            conn.execute(
                "UPDATE tenants SET staff_username = %s, staff_password_hash = %s WHERE id = %s",
                (username or None, password_hash, tenant_id),
            )
        else:
            conn.execute("UPDATE tenants SET staff_username = %s WHERE id = %s",
                         (username or None, tenant_id))
