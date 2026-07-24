"""SECRET-02 — deployed-environment credential presence fail-fast.

Replaces the retired ``tests/qa_deploy_test.py`` deploy check (DESIGNER-RETIRE-01)
with a focused gate: on a deployed environment (Railway / production), verify the
credential env vars the app actually needs are present, and fail-fast (non-zero
exit) if any required one is missing.

Only *presence* is checked and only variable *names* are ever printed — credential
values are never read into output or logs. Conditional requirements are gated on
the same feature flags the app uses:

- Always: ``SECRET_KEY``, ``KAKAO_REST_API_KEY``, and a database URL
  (``DATABASE_URL`` or the full ``PG*`` set that ``db_url_resolver`` composes it from).
- Web push (``FOMS_WEB_PUSH_ENABLED`` truthy): ``VAPID_PRIVATE_KEY``, ``VAPID_PUBLIC_KEY``.
- R2 storage (``STORAGE_TYPE=r2``): ``R2_ENDPOINT`` or ``R2_ACCOUNT_ID``,
  ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY``, ``R2_BUCKET_NAME``.

Off a deployed environment the check is a no-op (exit 0) unless ``--force`` is
passed, since local dev intentionally relies on fallbacks.
"""

from __future__ import annotations

import argparse
import sys
from typing import Mapping

_TRUTHY = frozenset({"true", "1", "yes", "y", "on"})


def is_deployed(env: Mapping[str, str]) -> bool:
    """Return whether we are running in a deployed (Railway/production) env.

    Mirrors the signals used by ``app_factory`` / ``storage``.

    Args:
        env: Environment mapping.

    Returns:
        True on Railway or when ``FLASK_ENV`` is ``production``.
    """
    if (env.get("FLASK_ENV") or "").strip().lower() == "production":
        return True
    return bool((env.get("RAILWAY_ENVIRONMENT") or "").strip())


def _truthy(env: Mapping[str, str], key: str) -> bool:
    return (env.get(key) or "").strip().lower() in _TRUTHY


def _present(env: Mapping[str, str], key: str) -> bool:
    return bool((env.get(key) or "").strip())


def missing_secrets(env: Mapping[str, str]) -> list[str]:
    """Return the names of required-but-absent credential env vars.

    Values are never inspected beyond presence. The returned list contains
    variable names (and, for the DB requirement, the accepted alternatives) only.

    Args:
        env: Environment mapping to check.

    Returns:
        Sorted list of missing requirement labels (empty when all present).
    """
    missing: list[str] = []

    # Always required.
    for key in ("SECRET_KEY", "KAKAO_REST_API_KEY"):
        if not _present(env, key):
            missing.append(key)

    # Database: DATABASE_URL, or the PG* set that db_url_resolver composes it from.
    pg_complete = all(_present(env, k) for k in ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE"))
    if not _present(env, "DATABASE_URL") and not pg_complete:
        missing.append("DATABASE_URL (or PGHOST/PGUSER/PGPASSWORD/PGDATABASE)")

    # Web push (feature-flag conditional).
    if _truthy(env, "FOMS_WEB_PUSH_ENABLED"):
        for key in ("VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY"):
            if not _present(env, key):
                missing.append(key)

    # R2 object storage (only when explicitly selected).
    if (env.get("STORAGE_TYPE") or "").strip().lower() == "r2":
        if not (_present(env, "R2_ENDPOINT") or _present(env, "R2_ACCOUNT_ID")):
            missing.append("R2_ENDPOINT (or R2_ACCOUNT_ID)")
        for key in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
            if not _present(env, key):
                missing.append(key)

    return missing


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """CLI: fail-fast (exit 1) when a deployed env is missing required credentials.

    Prints requirement names only; never a credential value.

    Args:
        argv: CLI args (defaults to ``sys.argv``).
        env: Environment mapping (defaults to ``os.environ``).

    Returns:
        Process exit code (0 = ok/skipped, 1 = missing required secrets).
    """
    parser = argparse.ArgumentParser(description="SECRET-02 deploy credential presence gate")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the check even off a deployed environment.",
    )
    args = parser.parse_args(argv)

    import os

    e: Mapping[str, str] = env if env is not None else os.environ

    if not is_deployed(e) and not args.force:
        print("[SECRET-02] not a deployed environment - deploy secret check skipped (use --force to run)")
        return 0

    missing = missing_secrets(e)
    if missing:
        print("[SECRET-02] FAIL - required deploy credential(s) missing:")
        for name in missing:
            print(f"  - {name}")
        print("Set the above in the deploy environment (Railway) before serving traffic.")
        return 1
    print("[SECRET-02] OK - all required deploy credentials present (presence-only check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
