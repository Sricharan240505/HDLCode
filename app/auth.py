"""
auth.py — signup/login for HDLCode.

Signup flow:
  1. User provides a desired username + their email.
  2. We generate a temporary password (username + 3 random digits), hash it
     (PBKDF2-HMAC-SHA256, salted, 100k iterations — not reversible, unlike
     storing the plain password), and store the hash.
  3. We email the plaintext temp password to the address they gave us.
  4. On first login, the user is required to set their own password.

This means the plaintext password exists only transiently (in memory, in the
outgoing email) — it is never written to disk.
"""
import hashlib
import os
import re
import secrets
import smtplib
from email.mime.text import MIMEText

import streamlit as st

import db

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username or ""))


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def generate_temp_password(username: str) -> str:
    suffix = f"{secrets.randbelow(1000):03d}"
    return f"{username}{suffix}"


def hash_password(password: str, salt: str = None) -> tuple:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    computed, _ = hash_password(password, salt)
    return secrets.compare_digest(computed, password_hash)


def _smtp_config():
    """Reads SMTP settings from Streamlit secrets. Returns None if not configured."""
    try:
        cfg = st.secrets["smtp"]
        required = ["host", "port", "user", "password", "from_email"]
        if all(k in cfg for k in required):
            return cfg
    except Exception:
        pass
    return None


def send_password_email(to_email: str, username: str, temp_password: str) -> tuple:
    """
    Returns (sent: bool, mode: str). mode is 'smtp' if actually emailed,
    or 'local_fallback' if no SMTP is configured (dev/local use only —
    the caller should display the password on-screen in that case).
    """
    cfg = _smtp_config()
    if cfg is None:
        return False, "local_fallback"

    body = (
        f"Welcome to HDLCode, {username}!\n\n"
        f"Your temporary password is: {temp_password}\n\n"
        f"Log in and you'll be asked to set your own password immediately.\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = "Your HDLCode temporary password"
    msg["From"] = cfg["from_email"]
    msg["To"] = to_email

    try:
        with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=10) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_email"], [to_email], msg.as_string())
        return True, "smtp"
    except Exception as e:
        st.warning(f"Email send failed ({e}); falling back to on-screen display.")
        return False, "local_fallback"


def signup(username: str, email: str) -> dict:
    """Returns {'ok': bool, 'error': str|None, 'temp_password': str|None, 'email_sent': bool}"""
    if not valid_username(username):
        return {"ok": False, "error": "Username must be 3-20 characters: letters, numbers, underscore only."}
    if not valid_email(email):
        return {"ok": False, "error": "Please enter a valid email address."}
    if db.username_exists(username):
        return {"ok": False, "error": "That username is already taken."}
    if db.email_exists(email):
        return {"ok": False, "error": "An account with that email already exists."}

    temp_password = generate_temp_password(username)
    password_hash, salt = hash_password(temp_password)
    db.create_user(username, email, password_hash, salt)

    sent, mode = send_password_email(email, username, temp_password)
    return {
        "ok": True,
        "error": None,
        "temp_password": temp_password if mode == "local_fallback" else None,
        "email_sent": sent,
    }


def login(username: str, password: str) -> dict:
    user = db.get_user(username)
    if user is None:
        return {"ok": False, "error": "No account with that username."}
    if not verify_password(password, user["password_hash"], user["salt"]):
        return {"ok": False, "error": "Incorrect password."}
    return {"ok": True, "error": None, "must_change_password": bool(user["must_change_password"])}


def change_password(username: str, new_password: str) -> dict:
    if len(new_password) < 6:
        return {"ok": False, "error": "Password must be at least 6 characters."}
    password_hash, salt = hash_password(new_password)
    db.update_password(username, password_hash, salt, must_change=False)
    return {"ok": True, "error": None}
