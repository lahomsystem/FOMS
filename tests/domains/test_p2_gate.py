"""P2 completion gate — HTMX through orientation (PR P2-01~08)."""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


def test_p2_01_htmx_vendor_contract() -> None:
    layout = (ROOT / "templates/partials/shared/htmx_layout.html").read_text(encoding="utf-8")
    assert "js/vendor/htmx.min.js" in layout
    assert (ROOT / "static/js/vendor/htmx.min.js").exists()
    fragment = (ROOT / "foms/api/fragment.py").read_text(encoding="utf-8")
    assert "X-FOMS-Fragment" in fragment


def test_p2_02_alpine_vendor_and_toast() -> None:
    alpine = (ROOT / "templates/partials/shared/alpine_layout.html").read_text(encoding="utf-8")
    assert "js/vendor/alpine.min.js" in alpine
    assert (ROOT / "static/js/vendor/alpine.min.js").exists()
    toast = (ROOT / "templates/partials/shared/foms_alpine_toast.html").read_text(encoding="utf-8")
    assert "$store.fomsToast" in toast
    store = (ROOT / "static/js/foms/alpine-store.js").read_text(encoding="utf-8")
    assert "fomsShowToast" in store
    bundle = (ROOT / "templates/partials/shared/foms_p2_surface_bundle.html").read_text(encoding="utf-8")
    assert "alpine_layout.html" in bundle


def test_p2_03_offline_sw_and_api() -> None:
    assert (ROOT / "static/sw.js").exists()
    assert (ROOT / "static/js/foms/sync.js").exists()
    sync = (ROOT / "static/js/foms/sync.js").read_text(encoding="utf-8")
    assert "fomsOfflineQueueWrite" in sync
    assert "fomsOfflineEnqueueRequest" in sync
    inline = (ROOT / "static/js/foms/inline-edit.js").read_text(encoding="utf-8")
    assert "fomsOfflineEnqueueRequest" in inline
    offline = (ROOT / "foms/api/foms_offline.py").read_text(encoding="utf-8")
    assert "/queue" in offline


def test_p2_mobile_queue_attachment_preview_bundle() -> None:
    bundle = (
        ROOT / "templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html"
    ).read_text(encoding="utf-8")
    p2 = (ROOT / "templates/partials/shared/foms_p2_surface_bundle.html").read_text(
        encoding="utf-8"
    )
    card = (
        ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html"
    ).read_text(encoding="utf-8")
    assert "erp-attachment-preview-open.js" in bundle
    assert "attachment-preview-zoom.js" in bundle
    assert "foms_mobile_queue_attachment_preview_bundle.html" in p2
    assert "data-foms-erp-attachment-preview-gallery" in card
    assert "data-foms-lightbox-gallery" not in card


def test_mobile_queue_attachment_preview_open_is_shell_swap_idempotent() -> None:
    """The app shell is included in ERP fragments, so this script can be re-evaluated."""
    js = (ROOT / "static/js/foms/erp-attachment-preview-open.js").read_text(
        encoding="utf-8"
    )
    guard = "window.__FOMS_ERP_ATTACHMENT_PREVIEW_OPEN_BOUND"

    assert guard in js
    assert js.index(guard) < js.index('document.body.addEventListener("htmx:afterSwap"')
    assert js.index(guard) < js.index('document.addEventListener("foms:main-content-swapped"')


def test_p2_04_lightbox_assets() -> None:
    js = (ROOT / "static/js/foms/lightbox.js").read_text(encoding="utf-8")
    assert "data-foms-lightbox-gallery" in js
    assert "FomsLightbox" in js
    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card.html").read_text(encoding="utf-8")
    assert "data-foms-lightbox-src" in card


def test_p2_05_voice_input_script() -> None:
    voice = (ROOT / "static/js/foms/voice-input.js").read_text(encoding="utf-8")
    assert "ko-KR" in voice
    assert "foms-search-input" in voice


def test_p2_06_manifest_and_head() -> None:
    manifest = (ROOT / "static/manifest.json").read_text(encoding="utf-8")
    assert '"display": "standalone"' in manifest
    assert "foms-icon-192.png" in manifest
    assert "foms-icon-512.png" in manifest
    head = (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    assert "manifest.json" in head
    assert "apple-touch-icon" in head
    assert "foms-icon-180.png" in head
    assert "apple-mobile-web-app-capable" in head
    assert "mobile-web-app-capable" in head
    a2hs = (ROOT / "static/js/foms/a2hs-prompt.js").read_text(encoding="utf-8")
    assert "beforeinstallprompt" in a2hs
    assert 'register("/static/sw.js"' in a2hs


def test_p2_07_swipe_and_haptic() -> None:
    swipe = (ROOT / "static/js/foms/swipe-actions.js").read_text(encoding="utf-8")
    assert "data-foms-swipe-card" in swipe
    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card.html").read_text(encoding="utf-8")
    assert "data-foms-swipe-action" in card
    haptic = (ROOT / "static/js/foms/haptic.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in haptic


def test_p2_08_orientation_overlay_removed() -> None:
    """T1: the P2-08 orientation overlay blanked portrait tablets and was removed.

    The split is now orientation-independent (the 72+360+detail grid fits the whole
    992–1365.98 band in both portrait and landscape). Guard that the band-aid stays
    gone and is not referenced, and that the detail pane auto-populates so no tablet
    size shows an empty placeholder.
    """
    assert not (ROOT / "static/js/foms/orientation-layout.js").exists()
    assert not (ROOT / "static/css/foundation/foms-orientation-layout.css").exists()

    split = (ROOT / "templates/partials/shared/foms_split_shell.html").read_text(encoding="utf-8")
    assert "orientation-layout.js" not in split

    surfaces = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(encoding="utf-8")
    assert "foms-orientation-layout.css" not in surfaces

    bundle = (ROOT / "templates/partials/shared/foms_p2_surface_bundle.html").read_text(encoding="utf-8")
    assert "orientation-layout.js" not in bundle

    # No orientation gate may hide the split columns (the original blank-screen cause).
    split_css = (ROOT / "static/css/foundation/foms-split-view.css").read_text(encoding="utf-8")
    assert "orientation: portrait" not in split_css

    # Detail pane auto-selects on load (covers the wide empty-detail case).
    shell_js = (ROOT / "static/js/foms/split-shell.js").read_text(encoding="utf-8")
    assert "selectInitial" in shell_js
    assert "offsetParent" in shell_js


def test_p2_offline_sw_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from foms.services.feature_flags import env_bool

    monkeypatch.delenv("FOMS_OFFLINE_SW_ENABLED", raising=False)
    assert env_bool("FOMS_OFFLINE_SW_ENABLED") is False


def test_p2_offline_queue_api(client, app) -> None:
    from db import db_session
    from models import Order, User

    with app.app_context():
        user = User(
            username="p2_offline_user",
            password=generate_password_hash("pass"),
            role="ADMIN",
            name="Offline",
        )
        db_session.add(user)
        db_session.add(
            Order(
                received_date="2026-05-30",
                customer_name="OfflineQ",
                phone="010",
                address="Seoul",
                product="P",
            )
        )
        db_session.commit()
        uid = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid

    response = client.get("/api/foms/offline/queue")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert len(payload["data"]) >= 1
