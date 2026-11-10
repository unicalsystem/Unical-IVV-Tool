"""Authentication service (isolated so it can later be replaced by proper user management).

Passwords are stored only as salted PBKDF2-HMAC-SHA256 hashes. The prototype
account is created on first start from PROTOTYPE_ACCOUNT; its password is hashed
before it reaches the database. Replace / disable this account before any
production use.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from database.db_manager import DatabaseManager

log = logging.getLogger(__name__)

# Development / demonstration only (as per requirement). Hashed on first run.
PROTOTYPE_ACCOUNT = {"username": "admin", "password": "admin@123", "full_name": "Administrator", "role": "admin"}


@dataclass(frozen=True)
class UserSession:
    username: str
    full_name: str
    role: str
    login_at: str


@dataclass(frozen=True)
class AuthResult:
    success: bool
    message: str
    session: UserSession | None = None


def hash_password(password: str, salt_hex: str | None = None, iterations: int = 240_000) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex(), salt.hex()


class AuthenticationService:
    GENERIC_FAIL = "Invalid username or password."

    def __init__(self, db: DatabaseManager, max_failed: int = 5, lockout_minutes: int = 15, iterations: int = 240_000):
        self.db = db
        self.max_failed = max_failed
        self.lockout = timedelta(minutes=lockout_minutes)
        self.iterations = iterations

    def ensure_prototype_account(self) -> None:
        if self.db.get_user(PROTOTYPE_ACCOUNT["username"]) is None:
            pw_hash, salt = hash_password(PROTOTYPE_ACCOUNT["password"], iterations=self.iterations)
            self.db.create_user(PROTOTYPE_ACCOUNT["username"], PROTOTYPE_ACCOUNT["full_name"], PROTOTYPE_ACCOUNT["role"],
                                pw_hash, salt, self.iterations)
            self.db.audit("system", "USER_CREATED", "Prototype admin account created (hashed password)")
            log.warning("Prototype admin account created - replace before production use")

    def authenticate(self, username: str, password: str) -> AuthResult:
        username = (username or "").strip()
        if not username or not password:
            return AuthResult(False, "Please enter both username and password.")
        if len(username) > 64 or len(password) > 256:
            return AuthResult(False, self.GENERIC_FAIL)

        user = self.db.get_user(username)
        if user is None or not user["is_active"]:
            self.db.audit(username, "LOGIN_FAILED", "unknown or inactive user")
            return AuthResult(False, self.GENERIC_FAIL)

        now = datetime.now(timezone.utc)
        if user["locked_until"]:
            locked_until = datetime.fromisoformat(user["locked_until"])
            if locked_until > now:
                mins = max(1, int((locked_until - now).total_seconds() // 60) + 1)
                return AuthResult(False, f"Account locked after repeated failed attempts. Try again in about {mins} minute(s).")

        candidate, _ = hash_password(password, user["password_salt"], int(user["hash_iterations"]))
        if not hmac.compare_digest(candidate, user["password_hash"]):
            lock = None
            if int(user["failed_attempts"]) + 1 >= self.max_failed:
                lock = (now + self.lockout).isoformat(timespec="seconds")
            self.db.record_login_failure(user["username"], lock)
            self.db.audit(user["username"], "LOGIN_FAILED", "wrong password" + (" - account locked" if lock else ""))
            return AuthResult(False, self.GENERIC_FAIL)

        self.db.record_login_success(user["username"])
        self.db.audit(user["username"], "LOGIN", "successful login")
        session = UserSession(user["username"], user["full_name"], user["role"], now.isoformat(timespec="seconds"))
        return AuthResult(True, "Login successful.", session)

    def logout(self, session: UserSession | None) -> None:
        if session:
            self.db.audit(session.username, "LOGOUT", "")
