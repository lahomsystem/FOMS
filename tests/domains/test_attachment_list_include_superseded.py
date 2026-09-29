"""R4 — ERP 내부 첨부 탭에서만 교체된 옛 도면이 '교체됨' 으로 보인다(2c-2, 설계서 §8 기본안).

목록 API ``GET /api/orders/<id>/attachments`` 는 기본으로 옛 도면을 뺀다(생산·시공 '도면' 탭과
같은 GET). ``?include_superseded=1`` 을 붙이면 옛 도면 행도 돌려주고 각 항목에 ``is_superseded``
를 싣는다. 휴지통(``include_deleted``)과 달리 관리 권한은 요구하지 않는다(삭제가 아니라 교체).

정적 계약: ERP 내부 첨부 탭 JS 두 곳(주문 수정 화면 ``erp-order-shared.js``, 대시보드 첨부 창
``erp-dashboard-attachments.js``)만 인자를 붙이고, 생산·시공 도면 탭과 세 대시보드가 같이 쓰는
상세 펼침(``order-detail-fragment.js``)에는 없다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, User

_ROOT = Path(__file__).resolve().parents[2]
PIN = "20260929h"


def _seed() -> tuple[int, dict[str, str]]:
    """v1 → v2 교체 + 확정. 첨부: 옛 v1·현재 v2·첨부 탭 도면·실측 사진."""
    order = Order(received_date="2026-09-29", customer_name="교체표시", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="PRODUCTION", is_erp_order=True,
                  structured_data={})
    db_session.add(order)
    db_session.flush()
    oid = order.id
    keys = {
        "v1": f"orders/{oid}/drawing_wizard/exports/v1.png",
        "v2": f"orders/{oid}/drawing_wizard/exports/v2.png",
        "sketch": f"orders/{oid}/drawing/sketch.png",
        "measure": f"orders/{oid}/measurement/m.jpg",
    }
    cats = {"v1": "drawing", "v2": "drawing", "sketch": "drawing", "measure": "measurement"}
    for name, key in keys.items():
        db_session.add(OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1],
                                       file_type="image", category=cats[name], storage_key=key))
    v1, v2 = {"key": keys["v1"], "filename": "v1.png"}, {"key": keys["v2"], "filename": "v2.png"}
    order.structured_data = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_status": "CONFIRMED",
        "drawing_current_files": [v2],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "files": [v1], "previous_current_files": []},
            {"action": "TRANSFER", "files": [v2], "previous_current_files": [v1]},
            {"action": "CONFIRM_RECEIPT", "files": [v2]},
        ],
    }
    db_session.commit()
    return oid, keys


def _login(client, *, role: str, team: str, username: str) -> None:
    user = User(username=username, password=generate_password_hash("pass"), role=role,
                team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _get(client, url: str) -> list[dict]:
    res = client.get(url)
    body = res.get_json()
    assert res.status_code == 200 and body["success"] is True, body
    return body["attachments"]


def test_default_list_still_hides_superseded(client):
    """인자 없으면 지금처럼 숨김, is_superseded 키도 싣지 않는다(응답 모양 무변경)."""
    oid, keys = _seed()
    _login(client, role="ADMIN", team="SALES", username="r4_admin_default")

    items = _get(client, f"/api/orders/{oid}/attachments")

    assert {a["storage_key"] for a in items} == {keys["v2"], keys["sketch"], keys["measure"]}
    assert all("is_superseded" not in a for a in items)


def test_include_superseded_returns_old_drawing_marked(client):
    """인자 있으면 옛 도면 1개가 늘고 그 행만 is_superseded=True."""
    oid, keys = _seed()
    _login(client, role="ADMIN", team="SALES", username="r4_admin_opt_in")

    items = _get(client, f"/api/orders/{oid}/attachments?include_superseded=1")

    marks = {a["storage_key"]: a["is_superseded"] for a in items}
    assert marks == {keys["v1"]: True, keys["v2"]: False, keys["sketch"]: False,
                     keys["measure"]: False}

    drawing = _get(client, f"/api/orders/{oid}/attachments?include_superseded=1&category=drawing")
    assert {a["storage_key"] for a in drawing} == {keys["v1"], keys["v2"], keys["sketch"]}


def test_include_superseded_needs_no_manage_permission(client):
    """휴지통과 달리 목록을 볼 수 있는 사람이면 누구나(관리 권한 없는 직원도 200)."""
    oid, keys = _seed()
    _login(client, role="STAFF", team="PRODUCTION", username="r4_staff")

    assert client.get(f"/api/orders/{oid}/attachments?include_deleted=1").status_code == 403
    items = _get(client, f"/api/orders/{oid}/attachments?include_superseded=1")
    assert keys["v1"] in {a["storage_key"] for a in items}


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", [
    "static/js/orders/erp-order-shared.js",
    "static/js/orders/dashboard/erp-dashboard-attachments.js",
])
def test_internal_attachment_tabs_opt_in(rel):
    """ERP 내부 첨부 탭 두 곳만 인자를 붙이고 is_superseded 로 흐린 표시를 건다."""
    text = _read(rel)
    assert "/attachments?include_superseded=1" in text
    assert "is_superseded" in text


@pytest.mark.parametrize("rel", [
    "templates/production/partials/scripts.html",
    "static/js/construction/dashboard.js",
    "static/js/orders/order-detail-fragment.js",
    "foms/api/share.py",
])
def test_production_construction_customer_paths_never_opt_in(rel):
    """생산·시공 도면 탭, 세 대시보드 공용 상세 펼침, 고객 공유는 계속 숨김(인자 없음)."""
    assert "include_superseded" not in _read(rel)


def test_superseded_style_lives_in_css_file_not_inline():
    """'교체됨' 표시는 erp-pro.css 클래스다(인라인 스타일 금지)."""
    css = _read("static/css/foundation/erp-pro.css")
    for cls in (".erp-attachment-card--superseded", ".erp-attachment-tile--superseded",
                ".erp-attachment-superseded-badge"):
        assert cls in css
    for rel in ("static/js/orders/erp-order-shared.js",
                "static/js/orders/dashboard/erp-dashboard-core.js"):
        badge = re.search(r'<span class="erp-attachment-superseded-badge"[^>]*>', _read(rel))
        assert badge and "style=" not in badge.group(0)


def test_changed_assets_are_pinned():
    """바뀐 자산마다 새 핀 — 부모 번들(entry·layout·erp-pro.css)까지 연쇄로."""
    entry = _read("static/js/orders/erp-dashboard-entry.js")
    assert f"erp-dashboard-attachments.js?v={PIN}" in entry
    assert f"erp-dashboard-core.js?v={PIN}" in entry
    assert f"erp-dashboard-entry.js') }}}}?v={PIN}" in _read("templates/partials/shared/layout_scripts.html")
    assert f"erp-order-shared.js') }}}}?v={PIN}" in _read("templates/orders/partials/erp_order_js.html")
    assert f"erp-pro.css') }}}}?v={PIN}" in _read("templates/partials/shared/layout_head.html")
