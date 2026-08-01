"""SW-01: PII API 캐시 봉쇄 + subject purge + cold-miss timeout 계약.

Service Worker 는 실제 Chrome 에서만 등록되므로(헤드리스 미등록) sw.js 정책은 정적 구조로
검증하고, offline API no-store 헤더는 실제 응답으로 검증한다. 배경: docs/plans/
2026-07-22-foms-full-system-bug-audit-report.md §5.2 SW-01.
"""

from __future__ import annotations

import re
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]
SW = ROOT / "static/sw.js"
SYNC_JS = ROOT / "static/js/foms/sync.js"
LAYOUT_SCRIPTS = ROOT / "templates/partials/shared/layout_scripts.html"
OFFLINE_API = ROOT / "foms/api/foms_offline.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- PII 미캐시(no-store 게이트) ------------------------------------------------


def test_sw_api_cache_respects_no_store() -> None:
    """API 응답이 Cache-Control:no-store 면 CacheStorage 에 저장하지 않는다(PII 봉쇄)."""
    sw = _read(SW)
    assert "responseForbidsStore" in sw
    assert re.search(r"no-store", sw, re.IGNORECASE)
    # cache.put 은 no-store 아님 게이트를 통과할 때만 실행된다.
    assert "!responseForbidsStore(response)" in sw


def test_offline_queue_sends_no_store_header_in_source() -> None:
    """PII 스냅샷 엔드포인트 소스가 no-store 를 실어 캐시 저장을 막는다."""
    offline = _read(OFFLINE_API)
    assert "no-store" in offline
    # 이 응답이 PII(전화/주소)를 담기 때문에 no-store 가 필요하다는 회귀 근거.
    assert "phone" in offline and "address" in offline


def test_offline_queue_response_has_no_store(client, app) -> None:
    """실제 응답 헤더가 no-store 인지 확인(런타임 계약, payload/상태는 무변경)."""
    from db import db_session
    from models import Order, User

    with app.app_context():
        user = User(
            username="sw_pii_user",
            password=generate_password_hash("pass"),
            role="ADMIN",
            name="PII",
        )
        db_session.add(user)
        db_session.add(
            Order(
                received_date="2026-05-30",
                customer_name="PII",
                phone="010",
                address="Seoul",
                product="P",
            )
        )
        db_session.commit()
        uid = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = uid

    resp = client.get("/api/foms/offline/queue")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert "no-store" in resp.headers.get("Cache-Control", "")


# --- subject 변경 purge -------------------------------------------------------


def test_sw_purges_api_cache_on_subject_change() -> None:
    """subject 변경/logout 시 API 캐시를 purge 하는 message 핸들러가 있다."""
    sw = _read(SW)
    assert re.search(r"addEventListener\(\s*['\"]message['\"]", sw)
    assert "foms-subject" in sw
    assert "foms-purge-api-cache" in sw
    assert "purgeApiCaches" in sw
    # -api 로 끝나는 캐시명만 지운다(정적 캐시는 보존).
    assert re.search(r"-api\$", sw)


def test_client_posts_subject_and_layout_exposes_it() -> None:
    """페이지가 현재 subject 를 SW 에 postMessage 하고, layout 이 subject 를 노출한다."""
    sync = _read(SYNC_JS)
    assert "foms-subject" in sync
    assert "postMessage" in sync
    assert "controllerchange" in sync
    # G4: singleton 가드 안에서 바인딩(fragment 재실행 중복 바인딩 금지).
    assert "window.__FOMS_SYNC_BOUND" in sync
    layout = _read(LAYOUT_SCRIPTS)
    assert "foms-sw-config" in layout
    assert "data-foms-subject" in layout


# --- cold miss ≤ timeout(G3) --------------------------------------------------


def test_sw_networkfirst_timeout_settles_on_cold_miss() -> None:
    """network-first 는 timeout 을 갖고, cold miss(캐시 없음)에도 반드시 settle 한다."""
    sw = _read(SW)
    assert "NETWORK_FIRST_TIMEOUT_MS" in sw
    assert "setTimeout" in sw
    # cold miss 폴백: 합성 offline 응답으로 settle(무한 스피너 금지).
    assert "offlineFallbackResponse" in sw
    # timeout 분기가 cached 유무와 무관하게 settle 한다(구: cached 있을 때만 settle 했던 구멍).
    assert re.search(r"settle\(cached\)", sw)


# --- 회귀 가드 -----------------------------------------------------------------


def test_sw_offline_mutation_stays_off() -> None:
    """offline mutation(쓰기 큐 replay)은 SW 에 도입하지 않는다(GET 만 처리)."""
    sw = _read(SW)
    assert 'req.method !== "GET"' in sw
    # SW 소스에 write 큐/IndexedDB replay 흔적이 없다(큐는 client sync.js 의 flag off 기능).
    assert "pending-writes" not in sw


def test_sw_cross_origin_opaque_guard_intact() -> None:
    """교차 출처/opaque 가드 회귀 금지(카카오 타일 backoff 미캐시 사건)."""
    sw = _read(SW)
    guard = "url.origin !== self.location.origin"
    image_branch = "if (/\\.(png|jpg|jpeg|webp|gif)(\\?|$)/i.test(url.pathname))"
    assert guard in sw
    assert sw.index(guard) < sw.index(image_branch)


def test_sw_cache_version_bumped_v10() -> None:
    """PII 봉쇄 배포와 함께 CACHE_VERSION bump(구 v9-api PII 캐시 activate purge)."""
    sw = _read(SW)
    assert 'CACHE_VERSION = "foms-p2-v10"' in sw
