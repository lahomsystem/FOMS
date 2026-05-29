"""Fixtures for Playwright visual regression (P0-00D)."""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

BASELINE_DIR = Path(__file__).parent / "baseline"
VISUAL_ADMIN_USERNAME = "visual_admin"
VISUAL_ADMIN_PASSWORD = "visualpass"
VISUAL_SERVER_HOST = "127.0.0.1"
VISUAL_SERVER_PORT = 5001
PIXEL_DIFF_THRESHOLD = 0.001

pytest_plugins = ("pytest_playwright",)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --update-snapshots for baseline refresh."""
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Write captured PNGs to tests/visual/baseline/",
    )


@pytest.fixture(scope="session")
def update_snapshots(request: pytest.FixtureRequest) -> bool:
    """True when baseline PNGs should be regenerated."""
    return bool(request.config.getoption("--update-snapshots"))


def compute_pixel_diff_ratio(baseline_path: Path, actual_path: Path) -> float:
    """
    Return fraction of pixels that differ between two PNGs (RGB compare).

    Args:
        baseline_path: Expected PNG path.
        actual_path: Captured PNG path.

    Returns:
        Ratio in [0, 1] of differing pixels.
    """
    baseline = Image.open(baseline_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    if baseline.size != actual.size:
        raise AssertionError(
            f"Screenshot size mismatch: baseline={baseline.size}, actual={actual.size}"
        )

    width, height = baseline.size
    baseline_px = baseline.load()
    actual_px = actual.load()
    diff_count = 0
    for y in range(height):
        for x in range(width):
            if baseline_px[x, y] != actual_px[x, y]:
                diff_count += 1
    return diff_count / (width * height)


def compare_or_update_screenshot(
    screenshot_path: Path,
    baseline_name: str,
    *,
    update_snapshots: bool,
    threshold: float = PIXEL_DIFF_THRESHOLD,
) -> float:
    """
    Save or compare a screenshot against tests/visual/baseline.

    Args:
        screenshot_path: Fresh capture written by Playwright.
        baseline_name: Baseline filename (e.g. orders_320_light.png).
        update_snapshots: When True, overwrite baseline.
        threshold: Max allowed pixel diff ratio.

    Returns:
        Pixel diff ratio (0.0 when baseline was created/updated).
    """
    baseline_path = BASELINE_DIR / baseline_name
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    if update_snapshots or not baseline_path.exists():
        baseline_path.write_bytes(screenshot_path.read_bytes())
        screenshot_path.unlink(missing_ok=True)
        return 0.0

    ratio = compute_pixel_diff_ratio(baseline_path, screenshot_path)
    screenshot_path.unlink(missing_ok=True)
    if ratio > threshold:
        pytest.fail(
            f"{baseline_name}: pixel diff ratio {ratio:.6f} exceeds threshold {threshold}"
        )
    return ratio


def _wait_for_server(base_url: str, timeout_s: float = 10.0) -> None:
    """Poll until the live Flask server responds."""
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/login", timeout=1.0) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Visual live server did not start: {last_error}")


@pytest.fixture(scope="session")
def visual_live_server() -> str:
    """
    Seed file-backed SQLite and run Flask on port 5001 in a background thread.

    Requires DATABASE_URL=file-backed sqlite (not :memory:) before app import.
    """
    db_url = __import__("os").environ.get("DATABASE_URL", "")
    if ":memory:" in db_url:
        pytest.fail(
            "Visual tests require file-backed SQLite. "
            "Set DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite"
        )

    from app import app as flask_app
    from db import Base, db_session, engine
    from models import User

    import foms.persistence.designer.models  # noqa: F401

    flask_app.config["TESTING"] = True
    Base.metadata.create_all(bind=engine)

    existing = db_session.query(User).filter_by(username=VISUAL_ADMIN_USERNAME).first()
    if existing is None:
        db_session.add(
            User(
                username=VISUAL_ADMIN_USERNAME,
                password=generate_password_hash(VISUAL_ADMIN_PASSWORD),
                role="admin",
                name="Visual Admin",
                is_active=True,
            )
        )
        db_session.commit()

    server = make_server(
        VISUAL_SERVER_HOST,
        VISUAL_SERVER_PORT,
        flask_app,
        threaded=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://{VISUAL_SERVER_HOST}:{VISUAL_SERVER_PORT}"
    try:
        _wait_for_server(base_url)
        yield base_url
    finally:
        server.shutdown()
        thread.join(timeout=5.0)
        db_session.remove()


@pytest.fixture
def dark_mode_page(page):
    """Playwright page with Bootstrap dark theme forced via data-bs-theme."""
    page.add_init_script(
        "document.documentElement.setAttribute('data-bs-theme', 'dark')"
    )
    return page
