import sqlite3
from contextlib import contextmanager
from datetime import datetime

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_user TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    message TEXT NOT NULL,
    intent TEXT,
    needs_human INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(wa_user, created_at);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_user TEXT NOT NULL,
    patient_name TEXT,
    doctor TEXT,
    service TEXT,
    requested_datetime TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_messages(processed_at);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def log_message(wa_user: str, direction: str, message: str, intent: str | None = None, needs_human: bool = False):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (wa_user, direction, message, intent, needs_human, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (wa_user, direction, message, intent, int(needs_human), datetime.utcnow().isoformat()),
        )


def recent_history(wa_user: str, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT direction, message FROM conversations WHERE wa_user = ? ORDER BY id DESC LIMIT ?",
            (wa_user, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def save_appointment(wa_user: str, patient_name: str | None, doctor: str | None, service: str | None,
                     requested_datetime: str | None, notes: str | None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO appointments
               (wa_user, patient_name, doctor, service, requested_datetime, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (wa_user, patient_name, doctor, service, requested_datetime, notes,
             datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_conversations(limit: int = 100) -> list[dict]:
    """Distinct wa_users with last message and counts."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT wa_user,
                      MAX(created_at) AS last_at,
                      COUNT(*) AS msg_count,
                      MAX(CASE WHEN needs_human = 1 THEN 1 ELSE 0 END) AS needs_human,
                      (SELECT message FROM conversations c2
                       WHERE c2.wa_user = c.wa_user ORDER BY id DESC LIMIT 1) AS last_message,
                      (SELECT direction FROM conversations c3
                       WHERE c3.wa_user = c.wa_user ORDER BY id DESC LIMIT 1) AS last_direction
               FROM conversations c
               GROUP BY wa_user
               ORDER BY last_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def conversation_thread(wa_user: str, limit: int = 200) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, direction, message, intent, needs_human, created_at
               FROM conversations WHERE wa_user = ?
               ORDER BY id ASC LIMIT ?""",
            (wa_user, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_appointments(status: str | None = None, limit: int = 200) -> list[dict]:
    sql = ("SELECT id, wa_user, patient_name, doctor, service, requested_datetime, status, notes, created_at "
           "FROM appointments")
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def set_appointment_status(appointment_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE appointments SET status = ? WHERE id = ?",
            (status, appointment_id),
        )


def claim_message_id(message_id: str) -> bool:
    """Returns True if this is the first time we're seeing the message_id, False if duplicate.
    Atomic via INSERT OR IGNORE — safe under concurrent webhook calls."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id, processed_at) VALUES (?, ?)",
            (message_id, datetime.utcnow().isoformat()),
        )
        return cur.rowcount > 0


def prune_processed_messages(older_than_hours: int = 24) -> int:
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=older_than_hours)).isoformat()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM processed_messages WHERE processed_at < ?", (cutoff,))
        return cur.rowcount


def stats() -> dict:
    with get_conn() as conn:
        msgs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        users = conn.execute("SELECT COUNT(DISTINCT wa_user) FROM conversations").fetchone()[0]
        appts = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE status = 'pending'"
        ).fetchone()[0]
        needs_human = conn.execute(
            "SELECT COUNT(DISTINCT wa_user) FROM conversations WHERE needs_human = 1"
        ).fetchone()[0]
    return {"messages": msgs, "users": users, "appointments": appts,
            "pending_appointments": pending, "needs_human_users": needs_human}
