"""Authentication tests (requirement section 16 - Authentication Testing)."""
import sqlite3

from core.authentication import PROTOTYPE_ACCOUNT, hash_password


def test_valid_credentials(auth):
    r = auth.authenticate("admin", "admin@123")
    assert r.success and r.session.username == "admin" and r.session.role == "admin"


def test_username_is_case_insensitive_and_trimmed(auth):
    assert auth.authenticate("  Admin ", "admin@123").success


def test_invalid_username(auth):
    r = auth.authenticate("someone", "admin@123")
    assert not r.success and r.message == auth.GENERIC_FAIL


def test_invalid_password(auth):
    r = auth.authenticate("admin", "wrong")
    assert not r.success and r.message == auth.GENERIC_FAIL


def test_empty_credentials(auth):
    for u, p in (("", ""), ("admin", ""), ("", "admin@123"), ("   ", "x")):
        r = auth.authenticate(u, p)
        assert not r.success and "enter both" in r.message


def test_password_not_stored_in_plain_text(db, auth):
    with sqlite3.connect(db.db_path) as conn:
        dump = "\n".join(conn.iterdump())
    assert PROTOTYPE_ACCOUNT["password"] not in dump
    user = db.get_user("admin")
    assert len(user["password_hash"]) == 64 and len(user["password_salt"]) == 32


def test_hash_uses_random_salt():
    h1, s1 = hash_password("same", iterations=1000)
    h2, s2 = hash_password("same", iterations=1000)
    assert s1 != s2 and h1 != h2


def test_lockout_after_repeated_failures(auth):
    for _ in range(3):
        assert not auth.authenticate("admin", "bad").success
    r = auth.authenticate("admin", "admin@123")  # correct password but locked
    assert not r.success and "locked" in r.message.lower()


def test_failures_reset_after_success(db, auth):
    auth.authenticate("admin", "bad")
    auth.authenticate("admin", "bad")
    assert auth.authenticate("admin", "admin@123").success
    assert db.get_user("admin")["failed_attempts"] == 0


def test_prototype_account_created_once(db, auth):
    auth.ensure_prototype_account()
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_login_events_audited(db, auth):
    auth.authenticate("admin", "bad")
    auth.authenticate("admin", "admin@123")
    events = [a["event"] for a in db.recent_activity(10)]
    assert "LOGIN" in events and "LOGIN_FAILED" in events


def test_overlong_input_rejected(auth):
    assert not auth.authenticate("a" * 65, "x").success
    assert not auth.authenticate("admin", "x" * 300).success
