"""Fixtures for Playwright visual regression (P0-00D)."""

from __future__ import annotations

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from tests.postgres_guard import assert_visual_test_database, resolve_sqlite_file_path
from werkzeug.serving import make_server

BASELINE_ROOT = Path(__file__).parent / "baseline"
ARTIFACT_ROOT = Path(__file__).parent / "artifacts"
VISUAL_BASELINE_NAMES: tuple[str, ...] = (
    "orders_320_light.png",
    "orders_320_dark.png",
    "orders_390_light.png",
    "orders_390_dark.png",
    "orders_767_light.png",
    "orders_767_dark.png",
    "erp_v2_390_light.png",
    "erp_v2_390_dark.png",
    "erp_v2_768_light.png",
    "erp_v2_768_dark.png",
    "erp_v2_1280_light.png",
    "erp_v2_1280_dark.png",
)
VISUAL_ADMIN_USERNAME = "visual_admin"
VISUAL_ADMIN_PASSWORD = "visualpass"
VISUAL_SERVER_HOST = "127.0.0.1"
VISUAL_SERVER_PORT = 5001
PIXEL_DIFF_THRESHOLD = float(os.environ.get("VISUAL_PIXEL_DIFF_THRESHOLD", "0.001"))
# Per-channel RGB slack for Linux vs Windows font/AA differences in CI.
COLOR_TOLERANCE = int(os.environ.get("VISUAL_COLOR_TOLERANCE", "24"))


def resolve_baseline_dir() -> Path:
    """
    Return platform-specific baseline directory.

    Linux CI uses baseline/linux (SSOT). Windows dev uses baseline/win32.
    Legacy root baseline/ is not used for compare (PNG must live in subdirs).
    Override with VISUAL_BASELINE_DIR for harness scripts.
    """
    override = os.environ.get("VISUAL_BASELINE_DIR", "").strip()
    if override:
        return Path(override)

    if sys.platform.startswith("linux"):
        platform_dir = BASELINE_ROOT / "linux"
    elif sys.platform == "win32":
        platform_dir = BASELINE_ROOT / "win32"
    elif sys.platform == "darwin":
        platform_dir = BASELINE_ROOT / "darwin"
    else:
        platform_dir = BASELINE_ROOT / sys.platform.replace("/", "_")

    return platform_dir


def missing_baseline_names(baseline_dir: Path | None = None) -> list[str]:
    """Return baseline filenames absent from the platform directory."""
    directory = baseline_dir or resolve_baseline_dir()
    return [name for name in VISUAL_BASELINE_NAMES if not (directory / name).is_file()]


def assert_linux_baselines_ready_for_ci(update_snapshots: bool) -> None:
    """Fail fast on Linux CI when SSOT baselines are not committed yet."""
    if not os.environ.get("CI") or update_snapshots:
        return
    if not sys.platform.startswith("linux"):
        return
    missing = missing_baseline_names()
    if missing:
        pytest.fail(
            "Missing Linux visual baselines under tests/visual/baseline/linux/: "
            f"{', '.join(missing)}. Run workflow "
            "'.github/workflows/visual-baseline-linux.yml' or "
            "pytest tests/visual/ --update-snapshots on Ubuntu, then commit."
        )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --update-snapshots for baseline refresh."""
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Write captured PNGs to the platform baseline dir (linux/ or win32/).",
    )


@pytest.fixture(scope="session")
def update_snapshots(request: pytest.FixtureRequest) -> bool:
    """True when baseline PNGs should be regenerated."""
    return bool(request.config.getoption("--update-snapshots"))


def _crop_to_common_size(
    baseline: Image.Image, actual: Image.Image
) -> tuple[Image.Image, Image.Image]:
    """Crop both images to shared width/height (top-left), tolerating full_page flakes."""
    width = min(baseline.width, actual.width)
    height = min(baseline.height, actual.height)
    if width <= 0 or height <= 0:
        raise AssertionError(
            f"Invalid screenshot size: baseline={baseline.size}, actual={actual.size}"
        )
    if baseline.size != (width, height):
        baseline = baseline.crop((0, 0, width, height))
    if actual.size != (width, height):
        actual = actual.crop((0, 0, width, height))
    return baseline, actual


def _rgb_pixels_differ(
    baseline_rgb: tuple[int, int, int],
    actual_rgb: tuple[int, int, int],
    *,
    tolerance: int,
) -> bool:
    """True when any RGB channel differs by more than tolerance."""
    return any(abs(b - a) > tolerance for b, a in zip(baseline_rgb, actual_rgb))


def compute_pixel_diff_ratio(
    baseline_path: Path,
    actual_path: Path,
    *,
    color_tolerance: int = COLOR_TOLERANCE,
) -> float:
    """
    Return fraction of pixels that differ between two PNGs (RGB compare).

    Args:
        baseline_path: Expected PNG path.
        actual_path: Captured PNG path.
        color_tolerance: Max per-channel delta treated as a match.

    Returns:
        Ratio in [0, 1] of differing pixels.
    """
    baseline = Image.open(baseline_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    baseline, actual = _crop_to_common_size(baseline, actual)

    width, height = baseline.size
    baseline_px = baseline.load()
    actual_px = actual.load()
    diff_count = 0
    for y in range(height):
        for x in range(width):
            if _rgb_pixels_differ(
                baseline_px[x, y], actual_px[x, y], tolerance=color_tolerance
            ):
                diff_count += 1
    return diff_count / (width * height)


@pytest.fixture(scope="session", autouse=True)
def _visual_baseline_gate(update_snapshots: bool) -> None:
    """Ensure Linux CI has committed SSOT PNGs before running captures."""
    assert_linux_baselines_ready_for_ci(update_snapshots)


def _write_diff_artifacts(
    baseline_path: Path,
    actual_path: Path,
    baseline_name: str,
    *,
    ratio: float,
) -> None:
    """Persist actual + diff PNGs for CI artifact upload (not committed)."""
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    stem = baseline_path.stem
    actual_copy = ARTIFACT_ROOT / f"{stem}.actual.png"
    actual_copy.write_bytes(actual_path.read_bytes())

    baseline = Image.open(baseline_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    baseline, actual = _crop_to_common_size(baseline, actual)
    diff = Image.new("RGB", baseline.size)
    diff_px = diff.load()
    baseline_px = baseline.load()
    actual_px = actual.load()
    width, height = baseline.size
    for y in range(height):
        for x in range(width):
            if _rgb_pixels_differ(
                baseline_px[x, y], actual_px[x, y], tolerance=COLOR_TOLERANCE
            ):
                diff_px[x, y] = (255, 0, 0)
            else:
                diff_px[x, y] = baseline_px[x, y]
    diff.save(ARTIFACT_ROOT / f"{stem}.diff.png")
    (ARTIFACT_ROOT / f"{stem}.meta.txt").write_text(
        f"baseline={baseline_name}\nratio={ratio:.6f}\nthreshold={PIXEL_DIFF_THRESHOLD}\n",
        encoding="utf-8",
    )


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
    baseline_dir = resolve_baseline_dir()
    baseline_path = baseline_dir / baseline_name
    baseline_dir.mkdir(parents=True, exist_ok=True)

    if update_snapshots or not baseline_path.exists():
        if not baseline_path.exists() and not update_snapshots and os.environ.get("CI"):
            pytest.fail(
                f"Missing baseline {baseline_name} under {baseline_dir}; "
                "commit PNGs to tests/visual/baseline/linux/ (CI) or win32/ (local)."
            )
        baseline_path.write_bytes(screenshot_path.read_bytes())
        screenshot_path.unlink(missing_ok=True)
        return 0.0

    ratio = compute_pixel_diff_ratio(baseline_path, screenshot_path)
    if ratio > threshold:
        _write_diff_artifacts(
            baseline_path, screenshot_path, baseline_name, ratio=ratio
        )
        screenshot_path.unlink(missing_ok=True)
        pytest.fail(
            f"{baseline_name}: pixel diff ratio {ratio:.6f} exceeds threshold {threshold} "
            f"(see tests/visual/artifacts/)"
        )
    screenshot_path.unlink(missing_ok=True)
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


def _reset_visual_sqlite_file(db_url: str) -> None:
    """
    Remove stale visual SQLite so create_all seeds a full schema.

    Partial schemas from prior runs caused missing `users` and login failures.
    Root tests/conftest.py imports db before this fixture runs; dispose first
    so Windows can delete the file (WinError 32 otherwise).
    PostgreSQL and paths outside tests/visual/ are rejected before any I/O.
    """
    assert_visual_test_database(db_url)
    db_path = resolve_sqlite_file_path(db_url)
    if db_path is None:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)

    from db import Base, db_session, engine

    import foms.persistence.designer.models  # noqa: F401

    db_session.remove()
    engine.dispose()

    if not db_path.exists():
        return

    try:
        db_path.unlink()
    except PermissionError:
        # Last resort on Win32 if another handle still holds the file.
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="session")
def visual_live_server() -> str:
    """
    Seed file-backed SQLite and run Flask on port 5001 in a background thread.

    Feature flags are toggled per test module via autouse monkeypatch fixtures
    (legacy order list vs ERP v2 dashboard).
    """
    db_url = __import__("os").environ.get("DATABASE_URL", "")
    assert_visual_test_database(db_url)
    _reset_visual_sqlite_file(db_url)

    from app import app as flask_app
    from db import Base, db_session, engine
    from models import User

    flask_app.config["TESTING"] = True
    Base.metadata.create_all(bind=engine)

    existing = db_session.query(User).filter_by(username=VISUAL_ADMIN_USERNAME).first()
    if existing is None:
        existing = User(
            username=VISUAL_ADMIN_USERNAME,
            password=generate_password_hash(VISUAL_ADMIN_PASSWORD),
            role="ADMIN",
            name="Visual Admin",
            is_active=True,
        )
        db_session.add(existing)
        db_session.commit()
    else:
        if existing.role != "ADMIN":
            existing.role = "ADMIN"
        db_session.commit()

    os.environ["FOMS_V3_SHELL_COHORT"] = str(existing.id)

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


@pytest.fixture(scope="session")
def visual_cohort_user_id(visual_live_server: str) -> str:
    """Cohort user id seeded by visual_live_server for ERP v2 captures."""
    return os.environ.get("FOMS_V3_SHELL_COHORT", "")


@pytest.fixture(scope="session")
def visual_live_server_legacy(visual_live_server: str) -> str:
    """Alias for legacy order-list captures (env set in test module autouse)."""
    return visual_live_server


@pytest.fixture(scope="session")
def visual_live_server_erp_v2(visual_live_server: str) -> str:
    """Alias for ERP v2 dashboard captures (env set in test module autouse)."""
    return visual_live_server


@pytest.fixture
def dark_mode_page(page):
    """Playwright page with FOMS dark theme forced via data-theme."""
    page.add_init_script(
        "document.documentElement.setAttribute('data-theme', 'dark')"
    )
    return page
