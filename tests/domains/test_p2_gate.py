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


def test_sw_never_intercepts_cross_origin() -> None:
    """SW fetch 핸들러는 교차 출처 요청을 가로채지 않는다(이미지 분기보다 먼저 반환).

    회귀 방지 근거(2026-07-21 실측): 교차 출처 no-cors 응답은 opaque(status 0)라
    staticNetwork 가 transient 오류로 분류 → 400ms+800ms backoff 재시도(+1.2초/요청),
    response.ok=false 라 cache.put 도 안 돼 영구 미캐시. 카카오 지도 타일이 이 경로에
    걸려 타일당 37ms→1243ms(33배)가 됐고 확대·축소마다 전량 재발생했다.
    """
    sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")
    guard = "url.origin !== self.location.origin"
    assert guard in sw, "교차 출처 가드가 sw.js 에서 사라졌다"
    image_branch = 'if (/\\.(png|jpg|jpeg|webp|gif)(\\?|$)/i.test(url.pathname))'
    assert image_branch in sw
    assert sw.index(guard) < sw.index(image_branch), (
        "교차 출처 가드는 이미지 stale-while-revalidate 분기보다 앞서야 한다"
    )


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
    assert "attach-thumb--gallery-only" in card
    assert "_visible_thumbs = 5" in card
    assert "preview_items[:3]" not in card
    assert "data-foms-erp-attachment-preview-more" in card
    assert "foms-queue-card-v2.css?v=20260722c" in (
        ROOT / "static/css/foundation/foms-mobile-surfaces.css"
    ).read_text(encoding="utf-8")
    assert "attach-thumb--gallery-only" in (
        ROOT / "static/css/components/foms-queue-card-v2.css"
    ).read_text(encoding="utf-8")
    assert "data-foms-lightbox-gallery" not in card


def test_mobile_queue_attachment_preview_open_is_shell_swap_idempotent() -> None:
    """The app shell is included in ERP fragments, so this script can be re-evaluated."""
    js = (ROOT / "static/js/foms/erp-attachment-preview-open.js").read_text(
        encoding="utf-8"
    )
    guard = "window.__FOMS_ERP_ATTACHMENT_PREVIEW_OPEN_BOUND"

    assert guard in js
    assert "data-foms-erp-attachment-preview-more" in js
    assert "openGalleryAt" in js
    assert js.index(guard) < js.index('document.body.addEventListener("htmx:afterSwap"')
    assert js.index(guard) < js.index('document.addEventListener("foms:main-content-swapped"')


def test_p2_04_lightbox_assets() -> None:
    js = (ROOT / "static/js/foms/lightbox.js").read_text(encoding="utf-8")
    assert "data-foms-lightbox-gallery" in js
    assert "FomsLightbox" in js


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
    # SW 등록 SSOT(Phase 3B): a2hs 는 직접 register 대신 sync.js 의 helper 를 경유하고,
    # navigator.serviceWorker.register("/static/sw.js") 호출은 sync.js 한 곳에만 있다.
    assert "fomsRegisterServiceWorker" in a2hs
    sync_js = (ROOT / "static/js/foms/sync.js").read_text(encoding="utf-8")
    assert 'register("/static/sw.js"' in sync_js


def test_p2_07_haptic() -> None:
    """Queue swipe actions were removed (STATE-CONTROLS-01: orphan caller-0 route);
    haptic.js itself is still wired into foms_p2_surface_bundle.html / wizard_shell.html."""
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
