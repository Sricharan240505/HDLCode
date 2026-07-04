"""
db.py — lightweight SQLite persistence for users and submissions.
No auth beyond a username (this is a personal/small-group judge tool, not a
public multi-tenant service — see README for notes on hardening if you need that).
"""
import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "hdlcode.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            problem_id TEXT NOT NULL,
            status TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS solved (
            username TEXT NOT NULL,
            problem_id TEXT NOT NULL,
            solved_at TEXT NOT NULL,
            PRIMARY KEY (username, problem_id)
        )
    """)
    conn.commit()
    conn.close()


def record_submission(username: str, problem_id: str, status: str, code: str):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO submissions (username, problem_id, status, code, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, problem_id, status, code, now),
    )
    if status == "PASS":
        c.execute(
            "INSERT OR IGNORE INTO solved (username, problem_id, solved_at) VALUES (?, ?, ?)",
            (username, problem_id, now),
        )
    conn.commit()
    conn.close()


def get_solved_problem_ids(username: str) -> set:
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute("SELECT problem_id FROM solved WHERE username = ?", (username,)).fetchall()
    conn.close()
    return {r["problem_id"] for r in rows}


def get_submission_history(username: str, problem_id: str = None, limit: int = 20):
    conn = get_conn()
    c = conn.cursor()
    if problem_id:
        rows = c.execute(
            "SELECT * FROM submissions WHERE username = ? AND problem_id = ? ORDER BY id DESC LIMIT ?",
            (username, problem_id, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM submissions WHERE username = ? ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()
    conn.close()
    return rows


def get_leaderboard(limit: int = 50):
    conn = get_conn()
    c = conn.cursor()
    rows = c.execute("""
        SELECT username, COUNT(DISTINCT problem_id) as solved_count
        FROM solved
        GROUP BY username
        ORDER BY solved_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------- users / auth

def username_exists(username: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None


def email_exists(email: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row is not None


def create_user(username: str, email: str, password_hash: str, salt: str):
    conn = get_conn()
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO users (username, email, password_hash, salt, created_at, must_change_password) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (username, email, password_hash, salt, now),
    )
    conn.commit()
    conn.close()


def get_user(username: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row


def get_user_by_email(email: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def update_password(username: str, password_hash: str, salt: str, must_change: bool = False):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ?, must_change_password = ? WHERE username = ?",
        (password_hash, salt, 1 if must_change else 0, username),
    )
    conn.commit()
    conn.close()


def rename_user(old_username: str, new_username: str):
    """Renames a user and cascades the change to submissions/solved (they're keyed by username)."""
    conn = get_conn()
    conn.execute("UPDATE users SET username = ? WHERE username = ?", (new_username, old_username))
    conn.execute("UPDATE submissions SET username = ? WHERE username = ?", (new_username, old_username))
    conn.execute("UPDATE solved SET username = ? WHERE username = ?", (new_username, old_username))
    conn.commit()
    conn.close()


def get_user_stats(username: str) -> dict:
    conn = get_conn()
    solved_count = conn.execute(
        "SELECT COUNT(DISTINCT problem_id) as c FROM solved WHERE username = ?", (username,)
    ).fetchone()["c"]
    submission_count = conn.execute(
        "SELECT COUNT(*) as c FROM submissions WHERE username = ?", (username,)
    ).fetchone()["c"]
    conn.close()
    return {"solved_count": solved_count, "submission_count": submission_count}
