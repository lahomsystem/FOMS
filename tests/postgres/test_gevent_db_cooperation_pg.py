"""PG lane: under the app's gevent patch, concurrent DB waits overlap instead of queueing.

The web server is ``gunicorn -k gevent`` (``start.sh``): one worker serves many requests on
greenlets, so a DB call that blocks the whole process would make every other request wait.
Today ``app.py`` installs psycogreen for psycopg2; psycopg 3 detects gevent by itself but
only if it is imported **after** the monkey patch (it picks its wait function at import,
``psycopg/waiting.py``). This test measures the real ``app.py`` patch block, so it stays
valid across the driver switch (docs/plans/2026-09-28-psycopg3-migration-plan.md step 2).

8 connections x ``pg_sleep(0.5)``: overlapping ≈ 0.5s, serialized ≈ 4s. The ``no-patch``
negative control must serialize — otherwise the timing could not tell the two apart.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = Path(__file__).with_name("gevent_db_probe.py")
SERIAL_SECONDS = 8 * 0.5
OVERLAP_CEILING = 2.0
SERIAL_FLOOR = 0.8 * SERIAL_SECONDS


def _probe_elapsed(mode: str, dsn: str) -> float:
    env = dict(os.environ, FOMS_PROBE_DSN=dsn)
    env.pop("SERVER_SOFTWARE", None)
    env.pop("GUNICORN_CMD_ARGS", None)
    result = subprocess.run(
        [sys.executable, str(PROBE), mode],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("ELAPSED "))
    return float(line.split()[1])


@pytest.fixture(scope="module")
def probe_dsn(pg_admin_url) -> str:
    return pg_admin_url.render_as_string(hide_password=False)


def test_without_gevent_patch_db_waits_serialize(probe_dsn) -> None:
    """Negative control: no monkey patch → greenlets queue behind each DB wait."""
    assert _probe_elapsed("no-patch", probe_dsn) >= SERIAL_FLOOR


def test_app_gevent_patch_lets_db_waits_overlap(probe_dsn) -> None:
    """The real app.py patch block makes DB waits cooperative."""
    assert _probe_elapsed("app-patch", probe_dsn) < OVERLAP_CEILING
