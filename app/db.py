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
    doctor      TEXT NOT NULL,
    service     TEXT NOT NULL,
    start_at    TIMESTAMPTZ NOT NULL,
    end_at      TIMESTAMPTZ NOT NULL,
    status      TEXT NOT NULL DEFAULT 'confirmed'
                CHECK (status IN ('confirmed', 'cancelled', 'completed', 'no_show')),
    notes       TEXT,
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

CREATE TABLE IF NOT EXISTS tenant_usage (
    tenant_id   BIGINT NOT NULL REFERENCES tenants(id),
    period      TEXT NOT NULL,           -- 'YYYY-MM'
    text_count  INTEGER NOT NULL DEFAULT 0,
    voice_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, period)
);

ALTER TABLE patients      ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
ALTER TABLE appointments  ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
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
                intent: str | None = None, needs_human: bool = False) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (tenant_id, wa_user, direction, message, intent, needs_human) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_id, wa_user, direction, message, intent, needs_human),
        )


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


def create_appointment(tenant_id: int, wa_user: str, patient_name: str | None, doctor: str,
                       service: str, start_at: datetime, end_at: datetime,
                       notes: str | None = None) -> dict:
    """Atomically book a slot. Returns the new row, or {'conflict': True} if the
    doctor is already booked in an overlapping window (within this tenant)."""
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
                "(tenant_id, wa_user, patient_name, doctor, service, start_at, end_at, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (tenant_id, wa_user, patient_name, doctor, service, start_at, end_at, notes),
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


def get_appointment(tenant_id: int, appointment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE tenant_id = %s AND id = %s",
            (tenant_id, appointment_id),
        ).fetchone()


def set_appointment_status(tenant_id: int, appointment_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET status = %s, updated_at = now() "
            "WHERE tenant_id = %s AND id = %s",
            (status, tenant_id, appointment_id),
        )


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


# --- Admin queries ---

def list_conversations(limit: int = 100, tenant_id: int | None = None) -> list[dict]:
    # When scoped to a clinic, the correlated subqueries must also filter by tenant,
    # or a shared phone would leak another clinic's last message/intent.
    if tenant_id is not None:
        sub = "AND c2.tenant_id = %s"
        sub3 = "AND c3.tenant_id = %s"
        sub4 = "AND c4.tenant_id = %s"
        where = "WHERE c.tenant_id = %s"
        params: tuple = (tenant_id, tenant_id, tenant_id, tenant_id, limit)
    else:
        sub = sub3 = sub4 = where = ""
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
                          AND c4.intent IS NOT NULL ORDER BY id DESC LIMIT 1) AS last_intent
               FROM conversations c {where}
               GROUP BY c.wa_user
               ORDER BY last_at DESC
               LIMIT %s""",
            params,
        ).fetchall()
    return rows


def conversation_thread(wa_user: str, limit: int = 200,
                        tenant_id: int | None = None) -> list[dict]:
    sql = ("SELECT id, direction, message, intent, needs_human, created_at "
           "FROM conversations WHERE wa_user = %s")
    params: tuple = (wa_user,)
    if tenant_id is not None:
        sql += " AND tenant_id = %s"
        params += (tenant_id,)
    sql += " ORDER BY id ASC LIMIT %s"
    with get_conn() as conn:
        rows = conn.execute(sql, params + (limit,)).fetchall()
    return rows


def list_appointments(status: str | None = None, limit: int = 200,
                      tenant_id: int | None = None) -> list[dict]:
    sql = ("SELECT id, wa_user, patient_name, doctor, service, start_at, end_at, "
           "status, notes, created_at FROM appointments")
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
    from psycopg.types.json import Json
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenants SET name = %s, wa_phone_number_id = %s, wa_access_token = %s, "
            "timezone = %s, clinic_data = COALESCE(%s, clinic_data) WHERE id = %s",
            (name, wa_phone_number_id or None, wa_access_token or None, timezone,
             Json(clinic_data) if clinic_data is not None else None, tenant_id),
        )


def get_tenant(tenant_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tenants WHERE id = %s", (tenant_id,)).fetchone()


def get_tenant_by_username(username: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tenants WHERE staff_username = %s", (username,)
        ).fetchone()


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
