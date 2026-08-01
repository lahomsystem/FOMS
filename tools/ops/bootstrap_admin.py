"""STARTUP-ADMIN-01 — explicit admin bootstrap CLI (operator maintenance).

App startup no longer auto-creates the ``admin`` account. Operators run this
CLI explicitly when a fresh database needs its first admin user:

    python tools/ops/bootstrap_admin.py

The password is read from an interactive, non-echoing terminal prompt
(``getpass``) — never argv, never an environment variable, and never
written to stdout/log. It is hashed immediately and the plaintext is
discarded. If an ``admin`` user already exists, the CLI exits idempotently
without touching the row (no password reset, no duplicate creation).
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db import db_session, init_db  # noqa: E402
from models import User  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

ADMIN_USERNAME = "admin"


def _prompt_password() -> str:
    """Read the new admin password from a secure, non-echoing terminal prompt.

    :return: the confirmed plaintext password (caller hashes it immediately).
    :raises SystemExit: when the prompt is blank or the confirmation mismatches.
    """
    password = getpass.getpass("New admin password: ")
    confirm = getpass.getpass("Confirm admin password: ")
    if not password.strip():
        raise SystemExit("[REFUSED] password must not be blank.")
    if password != confirm:
        raise SystemExit("[REFUSED] passwords do not match.")
    return password


def bootstrap_admin(
    session: Session, password_prompt: Callable[[], str] = _prompt_password
) -> bool:
    """Create the ``admin`` user when missing; idempotent no-op when it exists.

    :param session: SQLAlchemy session bound to the target database.
    :param password_prompt: callable returning the new admin password
        (defaults to the secure terminal prompt; tests inject a fake).
    :return: ``True`` when a new admin row was created, ``False`` when an
        admin already existed and nothing changed.
    """
    existing = session.query(User).filter_by(username=ADMIN_USERNAME).first()
    if existing:
        print("[BOOTSTRAP-ADMIN] Admin user already exists; no changes made.")
        return False

    password = password_prompt()
    admin = User(
        username=ADMIN_USERNAME,
        password=generate_password_hash(password),
        name="관리자",
        role="ADMIN",
        is_active=True,
    )
    session.add(admin)
    session.commit()
    print("[BOOTSTRAP-ADMIN] Admin user created.")
    return True


def main() -> int:
    """CLI entrypoint: explicit-only admin bootstrap. Never prints the password."""
    init_db()
    try:
        bootstrap_admin(db_session)
    except SystemExit:
        db_session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced via bounded operator exit code
        db_session.rollback()
        print(f"[BOOTSTRAP-ADMIN] Failed: {exc}")
        return 1
    finally:
        db_session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
