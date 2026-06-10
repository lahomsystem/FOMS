"""P0-02 — drawing workbench mobile card thumb + filter offcanvas."""

from datetime import date
from unittest.mock import MagicMock

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.drawing_workbench_display import (
    drawing_thumb_enabled,
    resolve_row_thumbnail_url,
)
from models import Order, User


def _login_drawing_admin(client):
    user = User(
        username="drawing_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="DRAWING",
        name="Drawing Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _drawing_order(structured_data=None):
    sd = {
        "parties": {"customer": {"name": "모바일 도면 고객"}, "manager": {"name": "담당A"}},
        "workflow": {"stage": "DRAWING"},
        "drawing": {"status": "IN_PROGRESS"},
        "drawing_current_files": [
            {
                "key": "drawings/test-plan.png",
                "filename": "test-plan.png",
                "view_url": "/api/files/view/drawings/test-plan.png",
            }
        ],
        "drawing_transfer_history": [],
        "drawing_assignees": [],
    }
    if structured_data:
        sd.update(structured_data)
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="모바일 도면",
        phone="010-1111-2222",
        address="Seoul",
        product="북박이",
        status="DRAWING",
        manager_name="담당A",
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _multi_drawing_order():
    return _drawing_order(
        {
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "drawing_current_files": [
                {
                    "key": "drawings/living.png",
                    "filename": "living.png",
                    "view_url": "/api/files/view/drawings/living.png",
                },
                {
                    "key": "drawings/kitchen.png",
                    "filename": "kitchen.png",
                    "view_url": "/api/files/view/drawings/kitchen.png",
                },
            ],
            "drawing_transfer_history": [
                {
                    "action": "TRANSFER",
                    "at": "2026-06-01 10:00:00",
                    "by_user_name": "도면팀A",
                    "note": "1차 전달",
                    "files": [],
                },
                {
                    "action": "REQUEST_REVISION",
                    "at": "2026-06-02 11:00:00",
                    "by_user_name": "영업A",
                    "note": "2번 높이 수정",
                    "target_drawing_keys": ["drawings/kitchen.png"],
                    "target_drawing_numbers": [2],
                    "target_drawing_number": 2,
                },
            ],
        }
    )


def test_drawing_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_DRAWING_THUMB_ENABLED", raising=False)
    assert drawing_thumb_enabled() is False
    assert drawing_thumb_enabled(mobile_v2_active=True) is True
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    assert drawing_thumb_enabled() is True
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "false")
    assert drawing_thumb_enabled(mobile_v2_active=True) is False


def test_resolve_row_thumbnail_prefers_view_url(monkeypatch):
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    db = MagicMock()
    files = [{"key": "k1.png", "filename": "k1.png", "view_url": "/api/files/view/k1.png"}]
    assert resolve_row_thumbnail_url(1, files, db) == "/api/files/view/k1.png"
    db.query.assert_not_called()


def test_resolve_row_thumbnail_uses_attachment_thumb_key(monkeypatch):
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    attachment = MagicMock()
    attachment.thumbnail_key = "thumbs/k1.png"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = attachment
    files = [{"key": "k1.png", "filename": "k1.png"}]
    url = resolve_row_thumbnail_url(42, files, db)
    assert url == "/api/files/view/thumbs/k1.png"


def test_drawing_workbench_mobile_markup_with_v2_and_thumb(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-drawing-mobile-controls" in body
    assert "erp-drawing-mobile-filter-drawer" in body
    assert "foms-drawing-mobile-dashboard" in body
    assert "foms-drawing-queue-card__thumb" in body
    assert "erp-drawing-mobile-list" in body
    assert "foms-mobile-surfaces.css" in body
    assert "foms-drawing-mobile-v2" not in body
    assert "erp-pro-card__header--filter d-none d-lg-block" in body


def test_drawing_workbench_thumb_hidden_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "false")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-queue-card__thumb" not in body


def test_drawing_workbench_mobile_single_list_my_first(client, monkeypatch):
    """무한스크롤 단일 리스트 + '내 차례' 서버 우선정렬. 목업 §5.2 '내 차례/상대 차례' 그룹 구분 노출."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-queue" in body
    assert "data-foms-mobile-queue-scroll" in body
    assert "foms-drawing-queue-card__turn" in body  # 카드별 차례 표시 유지
    # 목업 프레임 A: my_todo 우선정렬 단일 리스트에 '내 차례/상대 차례' 그룹 헤더를 얹는다.
    assert "foms-drawing-queue__group" in body
    assert ("내 차례" in body) or ("상대 차례" in body)


def test_drawing_workbench_mobile_infinite_scroll_pagination(client, monkeypatch):
    """회귀: per_page=25 도면 모바일 큐가 25건에서 멈추지 않고 무한스크롤 청크로 이어진다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    for _ in range(30):
        _drawing_order()

    page1 = client.get("/erp/drawing-workbench")
    assert page1.status_code == 200
    body = page1.get_data(as_text=True)
    assert "data-foms-mobile-queue-scroll" in body
    assert 'data-total-pages="2"' in body
    assert 'data-next-page="2"' in body
    assert "data-foms-mobile-queue-sentinel" in body

    chunk = client.get("/erp/drawing-workbench?mobile_chunk=1&page=2")
    assert chunk.status_code == 200
    chunk_body = chunk.get_data(as_text=True)
    assert "data-foms-mobile-queue-chunk" in chunk_body
    assert 'data-next-page="0"' in chunk_body
    assert "data-foms-mobile-queue-scroll" not in chunk_body


def test_drawing_workbench_multi_file_detail_opens_mobile_list(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="list"' in body
    assert "foms-drawing-sheet-list" in body
    assert "living.png" in body
    assert "kitchen.png" in body


def test_drawing_workbench_valid_drawing_key_opens_mobile_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?drawing_key=drawings/kitchen.png")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="detail"' in body
    assert "foms-drawing-handoff-detail" in body
    assert "도면 2 / 2" in body
    assert "data-selected-drawing-key=\"drawings/kitchen.png\"" in body


def test_drawing_workbench_invalid_drawing_key_returns_mobile_list_notice(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?drawing_key=missing")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="list"' in body
    assert "선택한 도면을 찾을 수 없습니다." in body


def test_drawing_workbench_single_file_invalid_key_normalizes_to_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?drawing_key=missing")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="detail"' in body
    assert 'data-selected-drawing-key="drawings/test-plan.png"' in body
    assert "foms-drawing-handoff-detail" in body


def test_drawing_workbench_target_deeplink_prefers_mobile_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?target_no=2")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="detail"' in body
    assert "도면 2 / 2" in body
    assert "foms-drawing-thread__msg" in body


def test_drawing_workbench_non_cohort_keeps_legacy_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    _login_drawing_admin(client)
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-handoff" not in body
    assert "도면 작업실 실행판" in body
