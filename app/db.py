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
"""

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
    log.info("DB schema ready")


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

def log_message(wa_user: str, direction: str, message: str,
                intent: str | None = None, needs_human: bool = False) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (wa_user, direction, message, intent, needs_human) "
            "VALUES (%s, %s, %s, %s, %s)",
            (wa_user, direction, message, intent, needs_human),
        )


def recent_history(wa_user: str, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT direction, message FROM conversations WHERE wa_user = %s "
            "ORDER BY id DESC LIMIT %s",
            (wa_user, limit),
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

def upsert_patient(wa_user: str, name: str | None) -> None:
    with get_conn() as conn:
        if name:
            conn.execute(
                "INSERT INTO patients (wa_user, name) VALUES (%s, %s) "
                "ON CONFLICT (wa_user) DO UPDATE SET name = EXCLUDED.name, updated_at = now()",
                (wa_user, name),
            )
        else:
            conn.execute(
                "INSERT INTO patients (wa_user) VALUES (%s) ON CONFLICT DO NOTHING",
                (wa_user,),
            )


def get_patient_name(wa_user: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM patients WHERE wa_user = %s", (wa_user,)
        ).fetchone()
    return row["name"] if row else None


# --- Appointments ---

def booked_intervals(doctor: str, day_start: datetime, day_end: datetime) -> list[tuple]:
    """(start_at, end_at) of active appointments for a doctor within [day_start, day_end)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT start_at, end_at FROM appointments "
            "WHERE doctor = %s AND status = 'confirmed' "
            "AND start_at < %s AND end_at > %s ORDER BY start_at",
            (doctor, day_end, day_start),
        ).fetchall()
    return [(r["start_at"], r["end_at"]) for r in rows]


def create_appointment(wa_user: str, patient_name: str | None, doctor: str, service: str,
                       start_at: datetime, end_at: datetime, notes: str | None = None) -> dict:
    """Atomically book a slot. Returns the new row, or {'conflict': True} if the
    doctor is already booked in an overlapping window."""
    with get_conn() as conn:
        with conn.transaction():
            clash = conn.execute(
                "SELECT id FROM appointments WHERE doctor = %s AND status = 'confirmed' "
                "AND start_at < %s AND end_at > %s FOR UPDATE",
                (doctor, end_at, start_at),
            ).fetchone()
            if clash:
                return {"conflict": True}
            row = conn.execute(
                "INSERT INTO appointments "
                "(wa_user, patient_name, doctor, service, start_at, end_at, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (wa_user, patient_name, doctor, service, start_at, end_at, notes),
            ).fetchone()
    return row


def upcoming_appointments(wa_user: str, now: datetime, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM appointments WHERE wa_user = %s AND status = 'confirmed' "
            "AND end_at >= %s ORDER BY start_at ASC LIMIT %s",
            (wa_user, now, limit),
        ).fetchall()
    return rows


def get_appointment(appointment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM appointments WHERE id = %s", (appointment_id,)
        ).fetchone()


def set_appointment_status(appointment_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET status = %s, updated_at = now() WHERE id = %s",
            (status, appointment_id),
        )


def reschedule(appointment_id: int, start_at: datetime, end_at: datetime) -> dict:
    """Move an appointment to a new window if free. Returns updated row or {'conflict': True}."""
    with get_conn() as conn:
        with conn.transaction():
            appt = conn.execute(
                "SELECT * FROM appointments WHERE id = %s FOR UPDATE", (appointment_id,)
            ).fetchone()
            if not appt:
                return {"not_found": True}
            clash = conn.execute(
                "SELECT id FROM appointments WHERE doctor = %s AND status = 'confirmed' "
                "AND id <> %s AND start_at < %s AND end_at > %s FOR UPDATE",
                (appt["doctor"], appointment_id, end_at, start_at),
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

def list_conversations(limit: int = 100) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.wa_user,
                      MAX(c.created_at) AS last_at,
                      COUNT(*) AS msg_count,
                      bool_or(c.needs_human) AS needs_human,
                      (SELECT message FROM conversations c2
                        WHERE c2.wa_user = c.wa_user ORDER BY id DESC LIMIT 1) AS last_message,
                      (SELECT direction FROM conversations c3
                        WHERE c3.wa_user = c.wa_user ORDER BY id DESC LIMIT 1) AS last_direction,
                      (SELECT intent FROM conversations c4
                        WHERE c4.wa_user = c.wa_user AND c4.direction = 'out'
                          AND c4.intent IS NOT NULL ORDER BY id DESC LIMIT 1) AS last_intent
               FROM conversations c
               GROUP BY c.wa_user
               ORDER BY last_at DESC
               LIMIT %s""",
            (limit,),
        ).fetchall()
    return rows


def conversation_thread(wa_user: str, limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, direction, message, intent, needs_human, created_at "
            "FROM conversations WHERE wa_user = %s ORDER BY id ASC LIMIT %s",
            (wa_user, limit),
        ).fetchall()
    return rows


def list_appointments(status: str | None = None, limit: int = 200) -> list[dict]:
    sql = ("SELECT id, wa_user, patient_name, doctor, service, start_at, end_at, "
           "status, notes, created_at FROM appointments")
    params: tuple = ()
    if status:
        sql += " WHERE status = %s"
        params = (status,)
    sql += " ORDER BY start_at DESC LIMIT %s"
    params = params + (limit,)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return rows


def stats() -> dict:
    with get_conn() as conn:
        msgs = conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
        users = conn.execute("SELECT COUNT(DISTINCT wa_user) AS n FROM conversations").fetchone()["n"]
        appts = conn.execute(
            "SELECT COUNT(*) AS n FROM appointments WHERE status = 'confirmed'"
        ).fetchone()["n"]
        upcoming = conn.execute(
            "SELECT COUNT(*) AS n FROM appointments WHERE status = 'confirmed' AND start_at >= now()"
        ).fetchone()["n"]
        needs_human = conn.execute(
            "SELECT COUNT(DISTINCT wa_user) AS n FROM conversations WHERE needs_human = TRUE"
        ).fetchone()["n"]
    return {"messages": msgs, "users": users, "appointments": appts,
            "upcoming_appointments": upcoming, "needs_human_users": needs_human}
