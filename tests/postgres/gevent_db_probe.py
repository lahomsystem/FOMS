"""Probe: do concurrent DB waits overlap under the app's gevent patch? (run as a child process)

Usage: ``python tests/postgres/gevent_db_probe.py <mode>`` with ``FOMS_PROBE_DSN`` set.

* ``app-patch`` — executes the **real** gevent patch block from ``app.py`` (the top-level
  ``if`` on ``SERVER_SOFTWARE``) with ``SERVER_SOFTWARE=gunicorn/probe``, without importing
  the app. Whatever DB cooperation that block installs (psycogreen today, nothing for
  psycopg 3 which detects gevent itself) is what gets measured.
* ``no-patch`` — negative control: greenlets without any monkey-patching. DB waits must
  serialize, which proves the timing can tell cooperative from blocking.

Opens ``PROBE_CONNECTIONS`` connections through the canonical driver
(``postgres_dbapi_connect``), runs ``SELECT pg_sleep(PROBE_SLEEP_SECONDS)`` on each from its
own greenlet and prints ``ELAPSED <seconds>``. It must stay a separate process: monkey
patching cannot be undone inside the pytest process.
"""

from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_CONNECTIONS = 8
PROBE_SLEEP_SECONDS = 0.5


def _run_app_gevent_patch_block() -> None:
    """Execute app.py's top-level ``if ...SERVER_SOFTWARE...:`` block exactly as written."""
    os.environ["SERVER_SOFTWARE"] = "gunicorn/probe"
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    block = next(
        node for node in tree.body
        if isinstance(node, ast.If) and "SERVER_SOFTWARE" in ast.unparse(node.test)
    )
    code = compile(ast.Module(body=[block], type_ignores=[]), str(ROOT / "app.py"), "exec")
    exec(code, {"os": os, "__name__": "app_gevent_patch_probe"})  # noqa: S102


def main(mode: str) -> None:
    if mode == "app-patch":
        _run_app_gevent_patch_block()
    elif mode != "no-patch":
        raise SystemExit(f"unknown mode {mode!r}")

    sys.path.insert(0, str(ROOT))
    import gevent

    from foms.services.db_url_resolver import (
        postgres_dbapi_connect,
        postgresql_connect_kwargs_from_url,
    )

    kwargs = postgresql_connect_kwargs_from_url(os.environ["FOMS_PROBE_DSN"])
    connections = [postgres_dbapi_connect(kwargs) for _ in range(PROBE_CONNECTIONS)]

    def wait_on_db(connection) -> None:
        cursor = connection.cursor()
        cursor.execute(f"SELECT pg_sleep({PROBE_SLEEP_SECONDS})")
        cursor.fetchall()

    try:
        started = time.monotonic()
        gevent.joinall([gevent.spawn(wait_on_db, c) for c in connections], raise_error=True)
        print(f"ELAPSED {time.monotonic() - started:.3f}")
    finally:
        for connection in connections:
            connection.close()


if __name__ == "__main__":
    main(sys.argv[1])
