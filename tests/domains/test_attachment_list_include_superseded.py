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


def test_superseded_rows_carry_no_delete_until_2b(client):
    """2b(옛 도면은 행만 휴지통·파일 보존) 전에는 옛 도면 행에 삭제 권한을 싣지 않는다(리뷰 P2).

    지금 삭제 API 는 휴지통 뒤 7일 purge 를 예약해 전달 이력 링크·비교 탭이 쓰는 파일을 지운다.
    R4 전에는 옛 도면 행이 화면에 없어 이 길이 닫혀 있었다 — 관리자라도 옛 도면 행은 can_delete=False.
    """
    oid, keys = _seed()
    _login(client, role="ADMIN", team="SALES", username="r4_admin_delete")

    items = _get(client, f"/api/orders/{oid}/attachments?include_superseded=1")

    can_delete = {a["storage_key"]: a["can_delete"] for a in items}
    assert can_delete[keys["v1"]] is False
    assert can_delete[keys["v2"]] is True and can_delete[keys["sketch"]] is True


def test_include_superseded_needs_no_manage_permission(client):
    """휴지통과 달리 목록을 볼 수 있는 사람이면 누구나(관리 권한 없는 직원도 200)."""
    oid, keys = _seed()
    _login(client, role="STAFF", team="PRODUCTION", username="r4_staff")

    assert client.get(f"/api/orders/{oid}/attachments?include_deleted=1").status_code == 403
    items = _get(client, f"/api/orders/{oid}/attachments?include_superseded=1")
    assert keys["v1"] in {a["storage_key"] for a in items}


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_order_edit_attachment_tab_shows_final_drawings_only():
    """주문 화면 첨부 탭은 옛 도면을 받지 않는다(2026-09-30 사용자 결정 — 최종 도면만).

    주문 대시보드 첨부 창은 페이지 표시가 있을 때만 인자를 붙이는 장치를 남겨 두지만, 그 표시를
    뺐으므로 역시 숨긴다(test_attachment_superseded_page_scope.py 가 실제 렌더로 고정).
    """
    assert "include_superseded=1" not in _read("static/js/orders/erp-order-shared.js")


@pytest.mark.parametrize("rel", [
    "templates/production/partials/scripts.html",
    "static/js/construction/dashboard.js",
    "static/js/orders/order-detail-fragment.js",
    "foms/api/share.py",
])
def test_production_construction_customer_paths_never_opt_in(rel):
    """생산·시공 도면 탭, 세 대시보드 공용 상세 펼침, 고객 공유는 계속 숨김(인자 없음).

    이 정적 검사만으로는 생산·시공에 함께 실리는 ERP 번들 경로를 못 잡는다 — 그 경로는
    test_attachment_superseded_page_scope.py 가 실제 렌더 + node VM 으로 고정한다.
    """
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
    # 뒤 작업이 정당하게 올린다(2026-10-04 도면 최종본 순서로 20261004a) — "이 작업 핀보다 오래되지 않았다".
    att_pin = entry.split("erp-dashboard-attachments.js?v=", 1)[1].split("'", 1)[0]
    assert att_pin >= PIN, att_pin
    assert f"erp-dashboard-core.js?v={PIN}" in entry
    # 리뷰 P1 수정: 첨부 미리보기 클릭을 페이지마다 한 번만(detail-dom·시공 dashboard.js 도 바뀜).
    # erp-pro.css 는 이후 board_state 줄로 20260930c, 2b 까지 합친 detail-dom·entry 는 20260929l.
    assert "erp-dashboard-detail-dom.js?v=20261001a" in entry
    assert f"js/construction/dashboard.js') }}}}?v={PIN}" in _read("templates/construction/partials/scripts.html")
    entry_pin = _read("templates/partials/shared/layout_scripts.html").split(
        "erp-dashboard-entry.js') }}?v=", 1)[1].split('"', 1)[0]
    assert entry_pin >= "20261002p", entry_pin
    # erp-order-shared.js 는 asset_url(내용 해시) 시범 — 손 핀 없이 파일이 바뀌면 URL 이 저절로 바뀐다.
    assert "asset_url('js/orders/erp-order-shared.js')" in _read("templates/orders/partials/erp_order_js.html")
    # erp-pro.css 핀은 뒤 작업이 정당하게 올린다(2026-10-02 토큰 @import 제거로 20261002t) —
    # 리터럴 대신 "이 작업 핀보다 오래되지 않았다"로 본다(핀은 YYYYMMDD+접미사라 문자열 비교=시간 비교).
    erp_pro_pin = _read("templates/partials/shared/layout_head.html").split("erp-pro.css') }}?v=", 1)[1].split('"', 1)[0]
    assert erp_pro_pin >= "20261001d", erp_pro_pin
