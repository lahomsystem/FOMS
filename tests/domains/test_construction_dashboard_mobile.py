"""P0-04: ERP construction dashboard mobile card (v1.1 badge + drawing/measurement thumbs)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
                {"key": "drawings/plan.png", "filename": "plan.png"},
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
    assert 'data-foms-erp-attachment-view-url="/files/drawings/plan.png"' in body
    assert 'erp-attachment-preview-open.js' in body
    assert 'attachment-preview-zoom.js' in body
    assert "/files/const/site.jpg" not in body
    assert 'aria-label="도면' in body
