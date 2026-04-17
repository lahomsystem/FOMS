"""
EPT-B8: obtain staging ``session_staging`` cookie via POST /login (no DevTools copy).

Reads credentials only from environment (never from argv — avoids shell history leaks):

  FOMS_STAGING_BASE_URL   — origin, default https://lahom-dev.up.railway.app
  FOMS_STAGING_USERNAME   — staging user id
  FOMS_STAGING_PASSWORD   — staging password

PowerShell (repo root):

  $env:FOMS_STAGING_USERNAME = '...'
  $env:FOMS_STAGING_PASSWORD = '...'
  python tools/harness/ept_b8_staging_session_from_login.py

On success, prints one line to stdout: ``session_staging=<token>`` (suitable for
``FOMS_STAGING_COOKIE``). Errors go to stderr; exit 2 = missing env, 3 = auth/network failure.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

DEFAULT_BASE = "https://lahom-dev.up.railway.app"
COOKIE_NAME = "session_staging"
# Some edge/WAF stacks behave better with a real browser UA than a custom token.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _cookie_header_value(session: requests.Session) -> str | None:
    """Build ``name=value`` for SESSION_COOKIE_NAME if present in jar."""
    for c in session.cookies:
        if c.name == COOKIE_NAME:
            return f"{c.name}={c.value}"
    return None


def fetch_session_cookie(
    base: str,
    username: str,
    password: str,
    *,
    next_path: str = "/erp/dashboard",
    timeout: float = 120.0,
) -> tuple[str, requests.Response]:
    """
    GET /login then POST credentials; return (Cookie header fragment, last response).

    Raises:
        RuntimeError: on missing cookie or obvious login failure.
    """
    origin = base.rstrip("/")
    login_url = f"{origin}/login"
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    r0 = session.get(login_url, params={"next": next_path}, timeout=timeout)
    r0.raise_for_status()

    r1 = session.post(
        login_url,
        data={"username": username, "password": password, "next": next_path},
        allow_redirects=True,
        timeout=timeout,
    )

    cookie = _cookie_header_value(session)
    if not cookie:
        jar_names = [c.name for c in session.cookies]
        hint = _login_failure_hint(r1, jar_names)
        raise RuntimeError(
            "No session_staging cookie after POST /login — wrong credentials, "
            "inactive user, or unexpected HTML response.\n"
            f"{hint}"
        )

    final = (r1.url or "").replace("\\", "/")
    if "/login" in final and "next=" in final:
        raise RuntimeError("Still on /login after POST — credentials rejected or CSRF issue.")

    return cookie, r1


def _login_failure_hint(resp: requests.Response, jar_names: list[str]) -> str:
    """Non-secret diagnostics for stderr (helps distinguish wrong username vs infra)."""
    lines = [
        f"  http_status={resp.status_code}",
        f"  final_url={resp.url}",
        f"  cookie_names_in_jar={jar_names or '(none)'}",
    ]
    text = (resp.text or "")[:2000]
    if 'name="username"' in text and 'name="password"' in text:
        lines.append(
            "  hint: Response still contains the login <form> — login did not succeed. "
            "FOMS uses User.username (로그인 ID), not email, unless your username is the email."
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch FOMS staging session_staging cookie via /login POST."
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("FOMS_STAGING_BASE_URL", DEFAULT_BASE).strip(),
        help="Staging origin (no trailing slash)",
    )
    parser.add_argument(
        "--next",
        default="/erp/dashboard",
        help="next= path for login redirect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON {\"cookie\": \"session_staging=...\"} to stdout",
    )
    args = parser.parse_args()

    user = os.environ.get("FOMS_STAGING_USERNAME", "").strip()
    password = os.environ.get("FOMS_STAGING_PASSWORD", "")

    if not user or not password:
        print(
            "ERROR: Set FOMS_STAGING_USERNAME and FOMS_STAGING_PASSWORD (env only).",
            file=sys.stderr,
        )
        return 2

    try:
        cookie, _ = fetch_session_cookie(
            args.base, user, password, next_path=args.next
        )
    except requests.RequestException as exc:
        print(f"ERROR: HTTP failure: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    if args.json:
        import json

        print(json.dumps({"cookie": cookie}, ensure_ascii=False))
    else:
        print(cookie)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
