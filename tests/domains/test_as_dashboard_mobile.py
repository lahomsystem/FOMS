"""P0-03: ERP AS dashboard mobile card audit (v1.1 badge, sticky controls, thumbnails)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.as_dashboard_display import (
    as_stage_badge_modifier,
    as_thumb_enabled,
    batch_resolve_as_thumbnail_urls,
)
from models import Order, OrderAttachment, User


def _login_as_admin(client):
    user = User(
        username="erp_as_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="ERP AS Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_as_order(**kwargs):
    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    shipment = {"as_content": "<div>내용</div>"}
    shipment_extra = kwargs.pop("shipment_extra", None)
    if shipment_extra:
        shipment.update(shipment_extra)
    order = Order(
        received_date=today,
        customer_name=kwargs.get("customer_name", "AS 모바일 고객"),
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=kwargs.get("status", "AS_RECEIVED"),
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        structured_data={"shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_dashboard_focus_order_with_q_shows_single_card(client, app):
    """Search deep-link: focus_order must not list all q= matches for same customer name."""
    with app.app_context():
        user = _login_as_admin(client)
        from datetime import date

        today = date.today().strftime("%Y-%m-%d")
        focus = Order(
            received_date=today,
            customer_name="소마디자인",
            phone="010-3377-5193",
            address="Seoul Gangnam",
            product="주방",
            status="AS_COMPLETED",
            manager_name="Alice",
            as_received_date=today,
            as_completed_date=today,
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "소마디자인", "phone": "010-3377-5193"}},
                "site": {"address_full": "Seoul Gangnam"},
                "shipment": {"as_content": "<div>강남</div>"},
            },
        )
        sibling = Order(
            received_date=today,
            customer_name="소마디자인",
            phone="010-3377-5193",
            address="Gyeonggi Anyang",
            product="주방",
            status="AS_COMPLETED",
            manager_name="Alice",
            as_received_date=today,
            as_completed_date=today,
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "소마디자인", "phone": "010-3377-5193"}},
                "site": {"address_full": "Gyeonggi Anyang"},
                "shipment": {"as_content": "<div>안양</div>"},
            },
        )
        db_session.add(focus)
        db_session.add(sibling)
        db_session.commit()
        focus_id = focus.id
        sibling_id = sibling.id

        broad = client.get("/erp/as?tab=completed&q=소마")
        assert broad.status_code == 200
        broad_body = broad.get_data(as_text=True)
        assert broad_body.count("소마디자인") >= 2

        focused = client.get(f"/erp/as?tab=completed&q=소마&focus_order={focus_id}")
        assert focused.status_code == 200
        body = focused.get_data(as_text=True)
        assert f'data-order-id="{focus_id}"' in body
        assert f'data-order-id="{sibling_id}"' not in body


def test_as_stage_badge_modifier_completed():
    assert as_stage_badge_modifier(status="AS_COMPLETED", as_pending=False) == "--completed"


def test_as_stage_badge_modifier_cs_pending():
    assert as_stage_badge_modifier(status="AS_RECEIVED", as_pending=True) == "--cs"


def test_as_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_AS_THUMB_ENABLED", raising=False)
    assert as_thumb_enabled() is False
    assert as_thumb_enabled(mobile_v2_active=True) is True
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "true")
    assert as_thumb_enabled() is True


def test_batch_resolve_as_thumbnail_urls_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "false")
    assert batch_resolve_as_thumbnail_urls([1, 2], db_session) == {}


@patch("foms.services.as_dashboard_display.build_file_view_url", return_value="/files/as-thumb")
def test_batch_resolve_as_thumbnail_urls_first_as_image(mock_url, monkeypatch, app):
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "true")
    order = _create_as_order()
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="note.pdf",
            file_type="document",
            category="as",
            file_size=1,
            storage_key="as/doc.pdf",
        )
    )
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="photo.jpg",
            file_type="image",
            category="as",
            file_size=2,
            storage_key="as/photo.jpg",
        )
    )
    db_session.commit()

    urls = batch_resolve_as_thumbnail_urls([order.id], db_session)

    assert urls == {order.id: "/files/as-thumb"}
    mock_url.assert_called_once_with("as/photo.jpg")


def test_as_dashboard_mobile_v2_wiring_contract():
    root = Path(__file__).resolve().parents[2]
    body_src = (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    card_src = (root / "templates/cs/partials/as_mobile_order_card.html").read_text(encoding="utf-8")
    css_src = (root / "static/css/components/foms-as-mobile-card.css").read_text(encoding="utf-8")

    # 카드 CSS 링크는 body 파셜에 있어야 fast-tab 프래그먼트(head 없음)에도 실려 FOUC가 없다
    assert "foms-as-mobile-card.css" in body_src
    assert "erp-as-mobile-list__sticky" in body_src
    assert "foms-mobile-v2-tab-notice" not in body_src
    assert "모바일 홈 대시보드 v2" not in body_src
    # 카드 마크업은 공용 단일 카드 파티얼로 이동(SSOT)
    assert "foms-stage-badge{{ r.stage_badge_modifier }}" in card_src
    assert "erp-as-mobile-card__thumb" in card_src
    assert "erp-as-mobile-card__contact-row" in card_src
    assert "erp-as-mobile-card__action--pending" in card_src
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css_src
    assert "grid-template-columns: minmax(0, 1fr)" in css_src
    assert "min-width: 0;" in css_src
    # PC식 번호 페이저(무한스크롤 아님)
    assert "render_mobile_pager" in body_src
    assert "as_mobile_order_card.html" in body_src
    assert "erp-as-mobile-card__date--received erp-pro-order-card__row" not in card_src
    assert "data-foms-mobile-queue-scroll" not in body_src
    assert "data-foms-mobile-queue-sentinel" not in body_src
    assert body_src.count("as_mobile_controls.html") == 1


def test_as_record_input_is_explicit_save_only():
    """T10: AS 기록 입력은 자동저장이 아니라 명시 저장(버튼/단축키)만이다.

    구 계약은 contenteditable 2탭의 blur autosave(`flushAsContentIfNeeded`)였다. 타임라인
    quick-add 는 append-only 로그라 blur 로 조용히 append 되면 오타 한 번이 영구 기록이 된다 —
    submit(버튼) 또는 Ctrl/⌘+Enter 로만 전송되어야 한다.
    """
    root = Path(__file__).resolve().parents[2]
    # Batch 5: inline JS가 static/js/cs/as-dashboard.js로 이동 → 표면(템플릿+모듈) 합본 검사
    body_src = (
        (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
        + "\n"
        + (root / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    )
    # 구 자동저장 경로(디바운스·blur flush·재배선) 전부 제거
    for retired in ("scheduleAsContentSave", "flushAsContentIfNeeded", "bindAsContentAutosaveInputs"):
        assert retired not in body_src, retired
    # 신규: 명시 submit + IME 안전 단축키만
    assert "submitQuickAdd(form)" in body_src
    assert "'submit'" in body_src
    assert "e.key === 'Enter'" in body_src
    # 전송 진입점은 두 곳(submit 위임 · 단축키)뿐이다
    assert body_src.count("submitQuickAdd(") == 3  # 정의 1 + 호출 2


def test_as_dashboard_mobile_renders_cards_without_scroll(client, monkeypatch):
    """모바일 v2 AS 큐는 카드 렌더 + 무한스크롤 배선 없음(번호 페이저 사용)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _create_as_order(customer_name="페이저 AS")

    resp = client.get("/erp/as?tab=incomplete")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "erp-as-mobile-card" in body  # 카드 실제 렌더
    assert "data-foms-mobile-queue-scroll" not in body
    assert "data-foms-mobile-queue-sentinel" not in body


def test_as_dashboard_renders_mobile_v2_markup(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = _create_as_order(customer_name="모바일 v2 AS")
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="as.jpg",
            file_type="image",
            category="as",
            file_size=100,
            storage_key="as/as.jpg",
        )
    )
    db_session.commit()

    with patch(
        "foms.services.as_dashboard_display.build_file_view_url",
        return_value="/files/as-view",
    ):
        response = client.get("/erp/as?tab=incomplete")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-erp-mobile-v2="true"' in body
    assert "erp-as-mobile-list__sticky" in body
    assert "erp-as-mobile-controls" in body
    assert "foms-stage-badge foms-stage-badge--cs" in body
    assert "erp-as-mobile-card__thumb" in body
    assert "/files/as-view" in body


def test_as_dashboard_hides_thumb_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_AS_THUMB_ENABLED", "false")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    _create_as_order(customer_name="썸네일 off")

    response = client.get("/erp/as?tab=incomplete")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-as-mobile-list__sticky" in body
    assert "erp-as-mobile-card__thumb" not in body


def _create_bucket_order(name, *, pending=False, visit=None):
    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    sd = {"shipment": {"as_content": "<div>n</div>", "as_pending": pending}}
    if visit:
        sd["schedule"] = {"as_visit": {"date": visit}}
    order = Order(
        received_date=today,
        customer_name=name,
        phone="010-0000-0000",
        address="Seoul",
        product="x",
        status="AS_RECEIVED",
        manager_name="M",
        as_received_date=today,
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_as_dashboard_bucket_filter_narrows_list(client):
    """stats 버킷 필터: ?bucket=pending|visit_confirmed|unassigned가 목록을 좁힌다.
    잘못된 bucket은 무시(전체 미완료). 버킷은 mutually exclusive."""
    from datetime import date

    _login_as_admin(client)
    today = date.today().strftime("%Y-%m-%d")
    _create_bucket_order("미결고객", pending=True, visit=today)         # pending
    _create_bucket_order("방문확정고객", pending=False, visit=today)     # visit_confirmed
    _create_bucket_order("미정고객", pending=False, visit=None)          # unassigned

    def body(url):
        resp = client.get(url)
        assert resp.status_code == 200
        return resp.get_data(as_text=True)

    b_all = body("/erp/as?tab=incomplete")
    assert "미결고객" in b_all and "방문확정고객" in b_all and "미정고객" in b_all

    b_pending = body("/erp/as?tab=incomplete&bucket=pending")
    assert "미결고객" in b_pending
    assert "방문확정고객" not in b_pending and "미정고객" not in b_pending

    b_visit = body("/erp/as?tab=incomplete&bucket=visit_confirmed")
    assert "방문확정고객" in b_visit
    assert "미결고객" not in b_visit and "미정고객" not in b_visit

    b_unassigned = body("/erp/as?tab=incomplete&bucket=unassigned")
    assert "미정고객" in b_unassigned
    assert "미결고객" not in b_unassigned and "방문확정고객" not in b_unassigned

    # 잘못된 bucket → 필터 무시(전체)
    b_bad = body("/erp/as?tab=incomplete&bucket=zzz")
    assert "미결고객" in b_bad and "방문확정고객" in b_bad and "미정고객" in b_bad

    # 버킷은 미완료 탭에서만 적용(완료 탭에선 무시)
    b_completed = body("/erp/as?tab=completed&bucket=pending")
    assert "미결고객" not in b_completed  # 완료 탭엔 미완료 건 없음


def test_as_fast_tab_fragment_includes_card_css(client, monkeypatch):
    """FOUC 가드: fast-tab 프래그먼트 응답(head 없음)에도 카드 CSS가 실려야
    탭 첫 진입에서 카드가 원시(미스타일)로 뜨지 않는다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _create_as_order(customer_name="프래그먼트 AS")

    full = client.get("/erp/as?tab=incomplete").get_data(as_text=True)
    assert "foms-as-mobile-card.css" in full

    frag_resp = client.get(
        "/erp/as?tab=incomplete&view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert frag_resp.status_code == 200
    frag = frag_resp.get_data(as_text=True)
    assert "foms-as-mobile-card.css" in frag  # 프래그먼트에도 카드 CSS 동반(FOUC 방지)
    assert "<html" not in frag.lower()  # 전체 문서가 아닌 부분 스왑이어야
