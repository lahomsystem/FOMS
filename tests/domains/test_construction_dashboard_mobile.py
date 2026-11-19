"""P0-04: ERP construction dashboard mobile card (v1.1 badge + drawing/measurement thumbs)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction_dashboard_display import (
    construction_stage_badge_modifier,
    construction_thumb_enabled,
    enrich_construction_mobile_rows,
)
from models import Order, OrderAttachment, User


def _login_as_admin(client):
    user = User(
        username="erp_construction_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CONSTRUCTION",
        name="ERP Construction Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_construction_order(**kwargs):
    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    sd = kwargs.pop("structured_data", {}) or {}
    workflow = sd.get("workflow") or {}
    if "stage" not in workflow:
        workflow = {**workflow, "stage": kwargs.pop("workflow_stage", "CONSTRUCTION")}
    sd["workflow"] = workflow
    order = Order(
        received_date=today,
        customer_name=kwargs.get("customer_name", "시공 모바일 고객"),
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이장",
        status=kwargs.get("status", "CONSTRUCTION"),
        manager_name=kwargs.get("manager_name", "Bob"),
        is_erp_order=True,
        # 운영 진실 정렬: 단계 SQL 필터가 flat erp_stage_code(index)를 읽으므로
        # workflow.stage와 동일 값을 명시 세팅(안 하면 시공 탭 필터가 걸러 오탐).
        erp_stage_code=workflow.get("stage"),
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_construction_stage_badge_modifier_completed():
    assert construction_stage_badge_modifier("시공완료") == "--completed"


def test_construction_stage_badge_modifier_in_progress():
    assert construction_stage_badge_modifier("시공중") == "--construction"
    assert construction_stage_badge_modifier("시공대기") == "--construction"


def test_construction_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", raising=False)
    assert construction_thumb_enabled() is False
    assert construction_thumb_enabled(mobile_v2_active=True) is True
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    assert construction_thumb_enabled() is True


@patch("foms.services.construction_dashboard_display.build_file_view_url", return_value="/files/const-thumb")
def test_enrich_construction_mobile_rows_from_structured_files(mock_url, monkeypatch):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    rows = [
        {
            "id": 99,
            "stage": "시공중",
            "structured_data": {
                "drawing_current_files": [
                    {"key": "drawings/a.png", "filename": "a.png"},
                ]
            },
        }
    ]
    enrich_construction_mobile_rows(rows, MagicMock())

    assert rows[0]["stage_badge_modifier"] == "--construction"
    assert rows[0]["construction_thumb_active"] is True
    assert rows[0]["thumbnail_url"] == "/files/const-thumb"
    assert rows[0]["attachment_previews"] == ["/files/const-thumb"]
    mock_url.assert_called_once_with("drawings/a.png")


def test_enrich_construction_mobile_rows_skips_thumb_when_disabled(monkeypatch):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    rows = [{"id": 1, "stage": "시공완료", "structured_data": {}}]
    enrich_construction_mobile_rows(rows, MagicMock())

    assert rows[0]["stage_badge_modifier"] == "--completed"
    assert rows[0]["construction_thumb_active"] is False
    assert rows[0]["thumbnail_url"] is None
    assert rows[0]["attachment_previews"] == []


@patch("foms.services.construction_dashboard_display.build_file_view_url", return_value="/files/att-thumb")
def test_enrich_construction_mobile_rows_attachment_fallback(mock_url, monkeypatch, app):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    order = _create_construction_order()
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="measure.jpg",
            file_type="image",
            category="measurement",
            file_size=10,
            storage_key="const/measure.jpg",
        )
    )
    db_session.commit()

    rows = [{"id": order.id, "stage": "시공대기", "structured_data": {}}]
    enrich_construction_mobile_rows(rows, db_session)

    assert rows[0]["thumbnail_url"] == "/files/att-thumb"
    assert rows[0]["attachment_preview_items"][0]["view"] == "/files/att-thumb"
    assert mock_url.call_count >= 1


@patch("foms.services.construction_dashboard_display.build_file_view_url", side_effect=lambda key: f"/files/{key}")
def test_enrich_construction_mobile_rows_drawing_only_excludes_measurement(mock_url, monkeypatch, app):
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    order = _create_construction_order()
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="measure.jpg",
            file_type="image",
            category="measurement",
            file_size=10,
            storage_key="const/measure.jpg",
        )
    )
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="draw.png",
            file_type="image",
            category="drawing",
            file_size=10,
            storage_key="const/draw.png",
            thumbnail_key="const/draw-thumb.png",
        )
    )
    db_session.commit()

    rows = [{"id": order.id, "stage": "시공대기", "structured_data": {}, "attachments_count": 99}]
    enrich_construction_mobile_rows(rows, db_session, drawing_only=True)

    assert rows[0]["drawing_preview_only"] is True
    assert rows[0]["attachments_count"] == 1
    assert len(rows[0]["attachment_preview_items"]) == 1
    assert rows[0]["attachment_preview_items"][0]["view"] == "/files/const/draw.png"
    assert rows[0]["attachment_preview_items"][0]["thumb"] == "/files/const/draw-thumb.png"
    assert rows[0]["attachment_preview_items"][0]["label"] == "draw.png"


def test_construction_dashboard_mobile_wiring_contract():
    root = Path(__file__).resolve().parents[2]
    queue_src = (root / "templates/construction/partials/mobile_queue.html").read_text(
        encoding="utf-8"
    )
    pc_grid = (root / "templates/construction/partials/filters_grid.html").read_text(
        encoding="utf-8"
    )
    macro_src = (root / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(
        encoding="utf-8"
    )

    # 모바일 큐는 queue-card-v2 + PC식 번호 페이저(무한스크롤 아님).
    assert "render_queue_card_v2" in queue_src
    assert "--construction" in queue_src
    assert "render_mobile_pager" in queue_src
    assert "data-foms-mobile-queue-scroll" not in queue_src
    assert "data-foms-mobile-queue-sentinel" not in queue_src
    # v2 카드는 badge override(modifier)를 stage 배지에 반영한다.
    assert "foms-stage-badge{{ badge_mod }}" in macro_src
    assert "data-foms-erp-attachment-preview-gallery" in macro_src
    assert "data-foms-erp-attachment-view-url" in macro_src
    assert "data-foms-lightbox-gallery" not in macro_src
    assert "attachment_preview_items" in macro_src
    assert "_visible_thumbs = 5" in macro_src
    # 시공 대시보드는 역할 무관 도면 전용 미리보기.
    dash_src = (root / "foms/web/construction/dashboard.py").read_text(encoding="utf-8")
    assert "drawing_only=True" in dash_src
    assert "drawing_only=bool(is_construction)" not in dash_src
    # PC workflow baseline: 시공완료는 사진 재업로드와 AS 액션이 병존한다.
    assert 'data-action="reuploadConstructionPhotos"' in pc_grid
    assert 'data-action="openAsAcceptModal"' in pc_grid
    assert 'data-action="openAsReuploadModal"' in pc_grid
    # Mobile must preserve the same critical action set.
    assert "'reuploadConstructionPhotos'" in queue_src
    assert "'openAsAcceptModal'" in queue_src
    assert "'openAsReuploadModal'" in queue_src
    assert "task_actions=task_actions" in queue_src


def _login_plain_admin(client):
    """mine_only 강제(CONSTRUCTION 팀)를 피하려고 팀 없는 ADMIN으로 로그인."""
    user = User(
        username="erp_construction_pager_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team=None,
        name="ERP Construction Pager Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def test_construction_mobile_queue_numbered_pagination(client, monkeypatch):
    """회귀: 시공 모바일 큐가 50건 초과 시 하단 PC식 번호 페이저로 페이지 이동.

    증상: 무한스크롤은 앞으로만 로딩되고 이전 페이지로 못 돌아감 → 번호 페이저로 교체.
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    for i in range(60):
        db_session.add(
            Order(
                received_date=today,
                customer_name=f"시공 페이저 {i}",
                phone="010-0000-0000",
                address="Seoul",
                product="붙박이장",
                status="CONSTRUCTION",
                manager_name="Bob",
                is_erp_order=True,
                # 운영 진실: 시공 리스트 스코프가 flat erp_stage_code(index)를 읽으므로
                # workflow.stage와 동일 값을 명시 세팅(안 하면 스코프가 전부 걸러 오탐).
                erp_stage_code="CONSTRUCTION",
                structured_data={"workflow": {"stage": "CONSTRUCTION"}},
            )
        )
    db_session.commit()

    # 페이지 1: 번호 페이저(2페이지 링크) + 첫 50건, 무한스크롤 배선 없음
    page1 = client.get("/erp/construction/dashboard")
    assert page1.status_code == 200
    body = page1.get_data(as_text=True)
    assert "foms-mobile-pager" in body
    assert "page=2" in body
    assert "data-foms-mobile-queue-scroll" not in body
    assert "data-foms-mobile-queue-sentinel" not in body
    assert "50 / 전체 60건" in body

    # 페이지 2 직접 접근 → 나머지 10건, 페이저로 1페이지 복귀 가능
    page2 = client.get("/erp/construction/dashboard?page=2")
    assert page2.status_code == 200
    body2 = page2.get_data(as_text=True)
    assert "foms-mobile-pager" in body2
    assert "60 / 전체 60건" in body2
    assert 'aria-current="page"' in body2  # 현재 페이지(2) 표시
    assert "page=1" in body2  # 1페이지로 돌아가는 링크


def test_construction_default_browse_scopes_to_construction_over_newer_noncon(client, monkeypatch):
    """회귀: 최근 접수(비시공) 활성 주문이 1페이지를 채워도 시공 주문이 board에 보여야 한다.

    근본버그: 단계 미선택 기본 뷰가 전체 60일 활성 리스트(모든 단계)의 newest-50 위에서
    페이지네이션 → 시공 주문이 더 최근 생성된 접수 주문에 밀려 1페이지 밖으로 나가고
    display 필터가 페이지 안에서 살릴 게 없어 board가 0건이 됐다. 시공 단계 SQL 선스코프로
    페이지네이션이 시공 주문 위에서 동작하도록 근본 차단한다.
    """
    import datetime

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    base = datetime.datetime(2026, 6, 1, 9, 0, 0)

    # 오래된 시공 주문(생성 이른) — newest-50 밖으로 밀릴 대상.
    con = Order(
        received_date=today,
        customer_name="시공 스코프 대상",
        phone="010-7777-8888",
        address="Seoul",
        product="붙박이장",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        erp_stage_code="CONSTRUCTION",
        created_at=base,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "시공 스코프 대상"}},
        },
    )
    db_session.add(con)
    db_session.commit()
    con_id = con.id

    # 최근 접수(비시공) 활성 주문 55건 — 더 최근 created_at 으로 1페이지(50)를 가득 채운다.
    for i in range(55):
        db_session.add(
            Order(
                received_date=today,
                customer_name=f"최근 접수 {i}",
                phone="010-0000-0000",
                address="Seoul",
                product="붙박이장",
                status="RECEIVED",
                manager_name="Bob",
                is_erp_order=True,
                erp_stage_code="RECEIVED",
                created_at=base + datetime.timedelta(minutes=i + 1),
                structured_data={"workflow": {"stage": "RECEIVED"}},
            )
        )
    db_session.commit()

    resp = client.get("/erp/construction/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 시공 스코프 선적용 → 최근 접수 55건이 1페이지를 채워도 시공 주문이 board에 보인다.
    assert "시공 스코프 대상" in body, "기본 뷰에서 시공 주문이 페이지네이션에 밀려 사라짐(회귀)"
    assert f'data-order-id="{con_id}"' in body or f"#{con_id}" in body
    # 비시공(RECEIVED)은 시공 대시보드 리스트에 노출되지 않는다.
    assert "최근 접수 0" not in body


def test_construction_dashboard_renders_v11_badge(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    # CONSTRUCTION team forces mine_only; manager must match logged-in user (dashboard.py L50-58).
    _create_construction_order(
        customer_name="시공 v11 배지",
        manager_name=user.name,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION", "history": [{"note": "시공 시작"}]},
            "parties": {"manager": {"name": user.name}},
        },
    )

    response = client.get("/erp/construction/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-erp-mobile-v2="true"' in body
    assert "foms-stage-badge foms-stage-badge--construction" in body
    assert "erp-construction-mobile-card__thumb-grid" not in body


def test_construction_mobile_completed_renders_reupload_as_and_edit(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "false")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    _create_construction_order(
        customer_name="시공완료 모바일 고객",
        structured_data={"workflow": {"stage": "COMPLETED"}},
    )

    response = client.get("/erp/construction/dashboard")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-action="reuploadConstructionPhotos"' in body
    assert 'data-action="openAsAcceptModal"' in body
    assert "?open=erp-order" in body


def test_construction_dashboard_search_q_and_focus_outside_browse_window(client, monkeypatch):
    """Search deep-link: q SQL filter + focus_order PK must not depend on browse limit(300)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    target = Order(
        received_date="2024-01-01",
        customer_name="ERP Order",
        phone="010-5555-6666",
        address="Gapyeong",
        product="인테리어",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "소마디자인(가평)", "phone": "010-5555-6666"}},
            "site": {"address_full": "경기 가평"},
        },
    )
    db_session.add(target)
    db_session.commit()
    target_id = target.id

    for i in range(320):
        db_session.add(
            Order(
                received_date=today,
                customer_name=f"최근 시공 {i}",
                phone="010-0000-0000",
                address="Seoul",
                product="붙박이장",
                status="CONSTRUCTION",
                manager_name="Bob",
                is_erp_order=True,
                structured_data={"workflow": {"stage": "CONSTRUCTION"}},
            )
        )
    db_session.commit()

    browse = client.get("/erp/construction/dashboard")
    assert browse.status_code == 200
    browse_body = browse.get_data(as_text=True)
    assert "소마디자인(가평)" not in browse_body

    searched = client.get(f"/erp/construction/dashboard?q=소마&focus_order={target_id}")
    assert searched.status_code == 200
    body = searched.get_data(as_text=True)
    assert "소마디자인(가평)" in body
    assert f'data-order-id="{target_id}"' in body or f"#{target_id}" in body
    assert "0 / 전체 0건" not in body


def test_construction_dashboard_focus_order_with_q_excludes_sibling_matches(client, monkeypatch):
    """focus_order deep link must not also show other orders matching q=."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    from datetime import date

    today = date.today().strftime("%Y-%m-%d")
    focus = Order(
        received_date="2024-01-01",
        customer_name="ERP Order",
        phone="010-3377-5193",
        address="Gapyeong",
        product="인테리어",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "소마디자인(가평)", "phone": "010-3377-5193"}},
            "site": {"address_full": "경기 가평"},
        },
    )
    sibling = Order(
        received_date="2024-02-01",
        customer_name="ERP Order",
        phone="010-3377-5193",
        address="Anyang",
        product="인테리어",
        status="CONSTRUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CONSTRUCTION"},
            "parties": {"customer": {"name": "소마디자인", "phone": "010-3377-5193"}},
            "site": {"address_full": "경기 안양"},
        },
    )
    db_session.add(focus)
    db_session.add(sibling)
    db_session.commit()
    focus_id = focus.id
    sibling_id = sibling.id

    db_session.add(
        Order(
            received_date=today,
            customer_name="최근 시공",
            phone="010-0000-0000",
            address="Seoul",
            product="붙박이장",
            status="CONSTRUCTION",
            manager_name="Bob",
            is_erp_order=True,
            structured_data={"workflow": {"stage": "CONSTRUCTION"}},
        )
    )
    db_session.commit()

    resp = client.get(f"/erp/construction/dashboard?q=소마&focus_order={focus_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "소마디자인(가평)" in body
    assert f'data-order-id="{focus_id}"' in body or f"#{focus_id}" in body
    assert f'data-order-id="{sibling_id}"' not in body


@patch("foms.services.construction_dashboard_display.build_file_view_url", side_effect=lambda key: f"/files/{key}")
def test_construction_team_mobile_card_renders_drawing_lightbox(mock_url, client, monkeypatch):
    """시공팀 모바일 카드: 도면만 썸네일 + lightbox gallery 바인딩."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_CONSTRUCTION_THUMB_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    order = _create_construction_order(
        customer_name="도면 라이트박스",
        manager_name=user.name,
        structured_data={
            "workflow": {"stage": "COMPLETED"},
            "parties": {"manager": {"name": user.name}},
            "shipment": {"construction_workers": [user.name]},
            "drawing_current_files": [
                {"key": "orders/1/drawing/plan.png", "filename": "plan.png"},
            ],
        },
    )
    db_session.add(
        OrderAttachment(
            order_id=order.id,
            filename="site.jpg",
            file_type="image",
            category="construction",
            file_size=10,
            storage_key="const/site.jpg",
        )
    )
    db_session.commit()

    response = client.get("/erp/construction/dashboard?stage=시공완료")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="erpAttachmentPreviewModal"' in body
    assert 'data-foms-erp-attachment-preview-gallery' in body
    assert 'data-foms-erp-attachment-view-url="/files/orders/1/drawing/plan.png"' in body
    assert 'erp-attachment-preview-open.js' in body
    assert 'attachment-preview-zoom.js' in body
    assert "/files/const/site.jpg" not in body
    assert 'aria-label="도면' in body


def test_construction_shell_fragment_includes_page_local_css(client, monkeypatch):
    """FOUC 가드: 셸 fragment에도 시공 page-local CSS link가 실려야 한다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))

    root = Path(__file__).resolve().parents[2]
    dash = (root / "templates/construction/dashboard.html").read_text(encoding="utf-8")
    frag_src = (
        root / "templates/construction/partials/dashboard_fragment.html"
    ).read_text(encoding="utf-8")
    for token in (
        "foms-construction-mobile-card.css') }}?v=20261119b",
        "foms-v2-domain-heroes.css') }}?v=20261109f",
        "foms-complete-gate.css') }}?v=20261109a",
        "foms-packing.css') }}?v=20261109f",
    ):
        assert token in dash
        assert token in frag_src

    full = client.get("/erp/construction/dashboard").get_data(as_text=True)
    assert "foms-v2-domain-heroes.css" in full
    assert "foms-complete-gate.css" in full
    assert "foms-packing.css" in full
    assert "foms-construction-mobile-card.css" in full

    frag_resp = client.get(
        "/erp/construction/dashboard?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert frag_resp.status_code == 200
    frag = frag_resp.get_data(as_text=True)
    assert "foms-v2-domain-heroes.css" in frag
    assert "foms-complete-gate.css" in frag
    assert "foms-packing.css" in frag
    assert "foms-construction-mobile-card.css" in frag
    assert "v=20261109a" in frag  # 화면 크기 배율 보정(2026-11-09)으로 complete-gate · packing 핀을 함께 올렸다
    # 화면 밖 카드 미루기(2026-11-19)로 카드 CSS 에 첫 핀을 달았다 — 기기 캐시의 옛 CSS 를 끊는다.
    assert "foms-construction-mobile-card.css?v=20261119b" in full
    assert "foms-construction-mobile-card.css?v=20261119b" in frag
    assert "<html" not in frag.lower()


# --- 폰 시공 탭 교체 비용(2026-11-19): 화면 밖 카드 미루기 · 모바일 표면 x-ignore · 사유 시트 한 벌 ---------------

_CONS_PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}
_CONS_VIEWS = [
    ("phone", _CONS_PHONE),
    ("tablet-landscape", {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}),
    ("big-tablet-portrait", {"foms_ptr": "coarse", "foms_vw": "tall", "foms_scr": "1366"}),
    ("mouse-pc", {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}),
    ("narrow-mouse-window", {"foms_ptr": "fine", "foms_vw": "narrow", "foms_scr": "1920"}),
    ("no-cookies", {}),
]
_CONS_SECTION = '<section class="foms-shell-body foms-mobile-v2-dashboard erp-construction-mobile-v2"'
_ALPINE_RE = (
    r'\s(?:x-(?:data|show|text|init|model|on:|bind|cloak|transition|if|for|effect|html|ref|teleport|id)\b'
    r'|@[a-z][a-z-]*[.=:]|:(?:class|style|[a-z-]+)=)'
)


def _cons_setup(client, monkeypatch, cookies: dict[str, str]) -> None:
    """팀 없는 관리자 + 시공 대기 · 시공 중 가짜 주문 둘(카드 · 시공 단추가 그려지게) + 화면 쿠키."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_plain_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _create_construction_order(customer_name="가짜고객 시공가")
    _create_construction_order(
        customer_name="가짜고객 시공나",
        structured_data={"workflow": {"stage": "CONSTRUCTION", "history": [{"note": "시공 시작"}]}},
    )
    for name, value in cookies.items():
        client.set_cookie(name, value, domain="localhost")


def _cons_render(client, fragment: bool) -> str:
    if fragment:
        resp = client.get("/erp/construction/dashboard?view=fragment", headers={"X-FOMS-ERP-SHELL": "1"})
    else:
        resp = client.get("/erp/construction/dashboard")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _cons_section_span(body: str) -> tuple[int, int]:
    """모바일 표면 section 의 시작 · 끝(짝 맞춘 </section> 뒤) 위치."""
    import re

    start = body.index(_CONS_SECTION)
    depth = 0
    for m in re.finditer(r"<(/?)section\b[^>]*>", body[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return start, start + m.end()
    raise AssertionError("모바일 표면 section 이 안 닫혔다")


def test_construction_mobile_first_screen_cards_are_never_deferred() -> None:
    """화면 밖 카드 미루기(content-visibility:auto)는 폰(터치 + 992 미만 창)에서만, 앞 4장을 빼고 건다(2026-11-19).

    출고 · AS 선례(같은 이름 시험): 크롬은 화면 안 판정 전까지 첫 카드도 임시 크기로 배치해 실제 크기와 다르면 판정 뒤
    단추가 뛴다. 시공 카드는 목록의 직속 자식 article 이라 그 본체에 건다. 임시 크기는 실측 카드 내용 상자 높이 근처여야
    문서 높이 · 뒤로 가기 굴림 복원이 안 어긋난다(카드 바깥 높이 358 을 넣었더니 문서 1.8% · 굴림 22px 어긋남).
    """
    import re

    root = Path(__file__).resolve().parents[2]
    css = (root / "static/css/components/foms-construction-mobile-card.css").read_text(encoding="utf-8")
    media = "@media (max-width: 991.98px) and (pointer: coarse) {"
    assert css.count(media) == 1
    block = css.split(media, 1)[1].split("\n}\n", 1)[0]
    card = "body.erp-mobile-v2-layout .erp-construction-mobile-v2 .foms-mobile-queue-list > .foms-queue-card-v2 {"
    assert card in block, "카드 미루기 규칙이 폰 범위 @media 밖에 있다"
    body = block.split(card, 1)[1].split("}", 1)[0]
    assert "content-visibility: auto" in body
    size = re.search(r"contain-intrinsic-size: auto (\d+)px", body)
    assert size and 320 <= int(size.group(1)) <= 357, body
    first = re.search(
        r"body\.erp-mobile-v2-layout \.erp-construction-mobile-v2 \.foms-mobile-queue-list > "
        r"\.foms-queue-card-v2:nth-of-type\(-n\+(\d+)\) \{([^}]*)\}",
        block,
    )
    assert first, "첫 화면 카드를 미루지 않는 규칙이 없다"
    assert int(first.group(1)) >= 4 and "content-visibility: visible" in first.group(2)
    assert "content-visibility" not in css.replace(block, ""), "폰 범위 밖에 미루기 규칙이 있다"
    # 카드가 목록의 직속 자식 article 이어야 위 선택자가 맞는다(사이에 껍데기가 끼면 규칙이 조용히 빗나간다).
    queue = (root / "templates/construction/partials/mobile_queue.html").read_text(encoding="utf-8")
    assert '<div class="erp-mobile-queue-section__list foms-mobile-queue-list">\n      {% for o in orders %}' in queue
    macro = (root / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(encoding="utf-8")
    assert '<article class="queue-card foms-queue-card-v2"' in macro


def test_construction_x_ignore_is_on_mobile_surface_not_on_screen_root(client, monkeypatch) -> None:
    """폰 시공: x-ignore 는 모바일 표면(section)에만 — 화면 뿌리에 걸면 그 안 Alpine 토스트 호스트가 죽는다(AS 2026-11-18 사고,
    test_as_dashboard_mobile.py::test_as_x_ignore_is_on_list_containers_not_on_screen_root). 표면 안(필터 · 큐 · 카드 · 쪽 넘김 ·
    패킹 시트 모두)에는 Alpine 지시어가 하나도 없어야 한다 — 있으면 x-ignore 가 그 기능을 죽인다."""
    import re

    _cons_setup(client, monkeypatch, _CONS_PHONE)
    body = _cons_render(client, fragment=True)
    assert body.count("x-ignore") == 1
    assert _CONS_SECTION + " x-ignore" in body, "폰 시공 모바일 표면에 x-ignore 가 없다"
    start, end = _cons_section_span(body)
    assert "erp-construction-mobile-v2" in body[start:end] and "foms-queue-card-v2" in body[start:end]
    inside = [m.group(0) for m in re.finditer(_ALPINE_RE, body[start:end])]
    assert inside == [], f"x-ignore 표면 안에 Alpine 지시어가 있다: {inside[:5]}"
    root = re.search(r'<div class="erp-pro[^"]*"[^>]*>', body)
    assert root and "x-ignore" not in root.group(0)
    if 'id="foms-alpine-toast-root"' in body:
        toast = body.index('id="foms-alpine-toast-root"')
        assert not (start <= toast < end), "토스트 호스트가 x-ignore 표면 안에 있다"


@pytest.mark.parametrize(("tag", "cookies"), _CONS_VIEWS[1:], ids=[v[0] for v in _CONS_VIEWS[1:]])
def test_construction_wide_or_unknown_views_have_no_x_ignore(client, monkeypatch, tag, cookies) -> None:
    """대조군(태블릿 · PC · 좁힌 마우스 창 · 쿠키 없음): x-ignore 없음 — 폰 밖 화면은 한 글자도 안 바뀐다."""
    _cons_setup(client, monkeypatch, cookies)
    for fragment in (False, True):
        body = _cons_render(client, fragment)
        assert "x-ignore" not in body, (tag, fragment)


@pytest.mark.parametrize("fragment", [False, True], ids=["full", "fragment"])
@pytest.mark.parametrize(("tag", "cookies"), _CONS_VIEWS, ids=[v[0] for v in _CONS_VIEWS])
def test_construction_reason_sheet_set_renders_exactly_once(client, monkeypatch, tag, cookies, fragment) -> None:
    """관리자 강제 진행 재시도 세트(사유 시트 + foms-reason-sheet.js + foms-admin-override.js)는 어느 화면 · 어느 길에서나 정확히
    한 벌(2026-11-19). 폰에선 모바일 큐 파샬과 scripts.html 이 한 벌씩 내 두 벌이었다(같은 id 두 개 · 스왑마다 두 번 실행).
    빠지면 재시도가 무음 실패하므로 0 도 안 된다. CSS 핀은 최신 하나."""
    import re

    _cons_setup(client, monkeypatch, cookies)
    body = _cons_render(client, fragment)
    assert len(re.findall(r"\sdata-foms-reason-sheet(?![\w-])", body)) == 1, tag
    assert body.count('id="foms-reason-sheet-title"') == 1, tag
    assert body.count("js/foms/foms-reason-sheet.js") == 1, tag
    assert body.count("js/foms/foms-admin-override.js") == 1, tag
    assert body.count("css/components/foms-reason-sheet.css") == 1, tag
    assert "css/components/foms-reason-sheet.css?v=20261109a" in body, tag
