"""M5 — 수정요청 ``files`` 입력 계약과 창구 업로드 완료 key 검사(2b, SPEC §4.3.2·4.3.3).

예전에는 ``request-revision`` 이 클라이언트 ``files`` 를 검증 없이 저장했다(남의 주문 key·
``javascript:`` URL 이 이력에 들어가고, 수정요청 취소가 그 key 를 R2 에서 지웠다 — 프로브 P2·P2b).
이제 이 주문 ``drawing_gateway/`` 정본 key 만 저장되고 나머지는 400 ``INVALID_REVISION_FILE``.
**files 키가 없거나 null 이면 지금처럼 빈 목록으로 200** 이다(태블릿 도면 검토 화면은
``{note, target_drawing_keys}`` 만 보낸다).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
import foms.api.drawing.erp_orders_revision as revision_api
from db import db_session
from models import Order, User

SALES = "영업M5"


class _Storage:
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.deleted_keys: list[str] = []

    def object_exists(self, key):
        return key in self.existing

    def get_file_type(self, filename):
        return "image" if filename.lower().endswith((".png", ".jpg")) else "file"

    def delete_file(self, key):
        self.deleted_keys.append(key)
        return True


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)


def _user(username, *, role="MANAGER", team="SALES", name=SALES):
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


def _login(client, who):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = who["id"], who["username"], who["role"]


def _order():
    """도면 1장을 전달한(TRANSFERRED) 주문 — 수정요청을 받을 수 있는 상태."""
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="M5고객",
                  phone="010-5", address="서울", product="붙박이장", status="DRAWING",
                  manager_name=SALES, is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.commit()
    v1 = f"orders/{order.id}/drawing_wizard/exports/v1.png"
    order.structured_data = {
        "parties": {"customer": {"name": "M5고객"}, "manager": {"name": SALES}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "TRANSFERRED",
        "drawing_current_files": [{"key": v1, "filename": "v1.png"}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "at": "2026-09-29 01:00:00", "files": [{"key": v1}],
             "previous_current_files": []},
        ],
    }
    db_session.commit()
    return order.id, v1


def _sd(oid):
    db_session.expire_all()
    return dict(db_session.get(Order, oid).structured_data or {})


def _revision_entries(sd):
    return [h for h in sd.get("drawing_transfer_history") or [] if h.get("action") == "REQUEST_REVISION"]


def _gw(oid, name="20260929_101010_ab12cd34_ref.jpg"):
    return f"orders/{oid}/drawing_gateway/revisions/{name}"


def _assert_rejected(res, oid):
    assert res.status_code == 400, res.get_data(as_text=True)
    body = res.get_json()
    assert body["success"] is False
    assert body["code"] == "INVALID_REVISION_FILE"
    assert "참고 파일 경로가 올바르지 않습니다" in body["message"]
    sd = _sd(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert _revision_entries(sd) == [], "거절된 요청이 이력에 저장됐다"


def test_foreign_order_key_is_rejected_and_not_saved(client, quiet):
    """프로브 P2 — 남의 주문 도면 key 를 참고 파일로 보내면 400, 저장 0."""
    sales = _user("m5_sales_a")
    oid, _ = _order()
    other, other_v1 = _order()
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/request-revision",
                      json={"note": "x", "files": [{"key": other_v1, "filename": "b1.png"}]})
    _assert_rejected(res, oid)


def test_own_current_drawing_key_is_rejected(client, quiet):
    """프로브 P2b — 자기 현재 도면(drawing_wizard/) key 도 참고 파일이 아니다 → 400."""
    sales = _user("m5_sales_b")
    oid, v1 = _order()
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/request-revision",
                      json={"note": "x", "files": [{"key": v1, "filename": "v1.png"}]})
    _assert_rejected(res, oid)


@pytest.mark.parametrize("shape", ["traversal", "absolute", "backslash", "korean", "spaces", "no_key"])
def test_malformed_keys_are_rejected(client, quiet, shape):
    sales = _user(f"m5_sales_{shape}")
    oid, _ = _order()
    bad = {
        "traversal": f"orders/{oid}/drawing_gateway/../measurement/x.jpg",
        "absolute": f"/orders/{oid}/drawing_gateway/revisions/x.jpg",
        "backslash": f"orders\\{oid}\\drawing_gateway\\revisions\\x.jpg",
        "korean": f"orders/{oid}/drawing_gateway/revisions/한글사진.jpg",
        "spaces": f" {_gw(oid)} ",
        "no_key": None,
    }[shape]
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/request-revision",
                      json={"note": "x", "files": [{"key": bad, "filename": "x.jpg"}]})
    _assert_rejected(res, oid)


def test_files_that_is_not_a_list_is_rejected(client, quiet):
    sales = _user("m5_sales_str")
    oid, _ = _order()
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/request-revision",
                      json={"note": "x", "files": _gw(oid)})
    _assert_rejected(res, oid)


def test_too_many_files_are_rejected(client, quiet):
    sales = _user("m5_sales_many")
    oid, _ = _order()
    _login(client, sales)
    files = [{"key": _gw(oid, f"20260929_1010{i:02d}_ab12cd34_r.jpg")} for i in range(21)]
    res = client.post(f"/api/orders/{oid}/request-revision", json={"note": "x", "files": files})
    assert res.status_code == 400, res.get_data(as_text=True)
    body = res.get_json()
    assert body["success"] is False and body["code"] == "INVALID_REVISION_FILE"
    # 개수 초과는 경로 오류 문구가 아니라 실제 이유를 알려 준다(2b 리뷰 P3).
    assert "20개까지" in body["message"]
    assert "경로가 올바르지 않습니다" not in body["message"]
    sd = _sd(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert _revision_entries(sd) == []


def _function_body(text, start_marker):
    start = text.index(start_marker)
    return text[start:start + 2500]


def test_screens_block_too_many_revision_files_before_upload():
    """PC 작업실·ERP 상세 수정요청은 파일을 R2 에 올리기 전에 20개 상한을 막는다(고아 파일 방지)."""
    from foms.services.orders.drawing_revision_files import MAX_REVISION_FILES

    root = Path(__file__).resolve().parents[2]
    pc = (root / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")
    erp = (root / "static/js/orders/dashboard/erp-dashboard-drawing.js").read_text(encoding="utf-8")
    for text, marker in ((pc, "async function submitRevision()"),
                         (erp, "async function submitDrawingRevision()")):
        assert f"MAX_REVISION_FILES = {MAX_REVISION_FILES}" in text
        body = _function_body(text, marker)
        guard = body.index("files.length > MAX_REVISION_FILES")
        assert guard < body.index("uploadRevisionGatewayFiles("), marker
    pc_change = _function_body(pc, "window.handleRevisionFilesChange")
    assert "MAX_REVISION_FILES" in pc_change[:600]
    entry = (root / "static/js/orders/erp-dashboard-entry.js").read_text(encoding="utf-8")
    assert "erp-dashboard-drawing.js?v=20261004a" in entry


def test_valid_gateway_key_is_saved_with_server_built_urls(client, quiet):
    """정상 gateway key → 200. 보낸 ``javascript:`` URL·file_type 은 버리고 서버가 key 로 만든다."""
    sales = _user("m5_sales_ok")
    oid, _ = _order()
    key = _gw(oid)
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/request-revision", json={
        "note": "손잡이",
        "files": [{"key": key, "filename": "  ref.jpg  ", "file_type": "script",
                   "view_url": "javascript:alert(1)", "download_url": "https://evil.example/x"}],
    })
    assert res.status_code == 200, res.get_data(as_text=True)
    entry = _revision_entries(_sd(oid))[-1]
    assert entry["files"] == [{
        "key": key,
        "filename": "ref.jpg",
        "file_type": "image",
        "view_url": f"/api/files/view/{key}",
        "download_url": f"/api/files/download/{key}",
    }]
    assert entry["files_count"] == 1
    assert "javascript:" not in str(entry) and "evil.example" not in str(entry)


@pytest.mark.parametrize("body", [
    {"note": "태블릿 요청"},                              # files 키 없음(태블릿 도면 검토 화면)
    {"note": "태블릿 요청", "files": None},
])
def test_tablet_body_without_files_still_succeeds(client, quiet, body):
    """태블릿 회귀 — files 가 없거나 null 이면 지금처럼 빈 목록으로 200."""
    sales = _user(f"m5_tablet_{'none' if 'files' in body else 'missing'}")
    oid, v1 = _order()
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/request-revision",
                      json={**body, "target_drawing_keys": [v1]})
    assert res.status_code == 200, res.get_data(as_text=True)
    entry = _revision_entries(_sd(oid))[-1]
    assert entry["files"] == [] and entry["files_count"] == 0


# --------------------------------------------------------------------------- gateway/complete


@pytest.mark.parametrize("bad", ["prefix", "traversal", "other_folder"])
def test_gateway_complete_rejects_non_canonical_keys(client, monkeypatch, bad):
    """부분 문자열 검사 우회(``foo/orders/<id>/drawing_gateway/…``)·traversal 은 400."""
    sales = _user(f"m5_gw_{bad}")
    oid, _ = _order()
    key = {
        "prefix": f"foo/orders/{oid}/drawing_gateway/x.png",
        "traversal": f"orders/{oid}/drawing_gateway/../measurement/x",
        "other_folder": f"orders/{oid}/measurement/drawing_gateway/x.png",
    }[bad]
    storage = _Storage(existing={key})
    monkeypatch.setattr(drawing_routes, "get_storage", lambda: storage)
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/drawing-gateway/complete",
                      json={"key": key, "filename": "x.png"})
    assert res.status_code == 400, res.get_data(as_text=True)
    assert res.get_json()["success"] is False


def test_gateway_complete_accepts_canonical_key(client, monkeypatch):
    sales = _user("m5_gw_ok")
    oid, _ = _order()
    key = _gw(oid, "20260929_101010_ab12cd34_ok.png")
    storage = _Storage(existing={key})
    monkeypatch.setattr(drawing_routes, "get_storage", lambda: storage)
    _login(client, sales)
    res = client.post(f"/api/orders/{oid}/drawing-gateway/complete",
                      json={"key": key, "filename": "ok.png"})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["file"]["view_url"] == f"/api/files/view/{key}"
