"""UPLOAD-01: order upload 권한 + 서버 object key 경로 방어 (red→green).

direct(presigned 세션/배치/complete)·multipart 네 업로드 경로가 공유하는 세 방어를 검증한다.

1. **VIEWER 403** — 업로드는 mutation 이므로 조회 전용 계정은 네 경로 모두 거부.
2. **purpose matrix** — 용도(category)별 허용 role/team(AUTH-01 정책 재사용):
     * 도면(drawing): DRAWING team ∪ CS/SALES + ADMIN/MANAGER (그 외 STAFF 거부).
     * 시공/AS(construction/as): CS/SALES/CONSTRUCTION + ADMIN/MANAGER (그 외 거부).
     * 실측/일반(measurement): 전 STAFF (비파괴).
3. **arbitrary folder 0** — 사용자 입력 folder/key 는 완전 정규화 후 화이트리스트로만 통과.
     ``../``·절대경로·비 orders namespace·비화이트리스트 subfolder·타 order key·**prefix-only
     우회(``foo/orders/{id}/...``)** 모두 거부한다. **substring/prefix match 로 종료하지 않는다.**

route 레벨 방어를 직접 검증한다: before_request AUTH-01 가드는 TESTING 에서 off 이므로, 아래
403/400 은 모두 업로드 handler 진입 후 route 게이트가 낸 것이다(direct·multipart 동일).
"""

import io

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAttachment, User


# --------------------------------------------------------------------------
# storage 목 (썸네일·R2 로직은 UPLOAD-01 범위 밖 — 권한·키 경로만 검증)
# --------------------------------------------------------------------------
class DummyStorage:
    storage_type = "r2"

    def __init__(self):
        self.count = 0

    def generate_direct_upload_key(self, filename, folder):
        self.count += 1
        return f"{folder}/{self.count}_{filename}"

    def _get_content_type(self, filename):
        return "image/jpeg"

    def generate_presigned_put_url(self, key, ct, expires_in=900):
        return f"https://r2.example.test/{key}"

    def object_exists(self, key):
        return True

    def get_file_type(self, filename):
        return "image"

    def upload_file(self, file_obj, filename, folder):
        return {"success": True, "key": f"{folder}/{filename}"}


@pytest.fixture(autouse=True)
def _upload_env(app, monkeypatch):
    """storage 목 주입 + before_request 가드 off(route 레벨 방어를 직접 검증)."""
    app.config.pop("AUTH_POLICY_ENABLED", None)
    monkeypatch.setattr("foms.api.files.direct_upload.get_storage", lambda: DummyStorage())
    monkeypatch.setattr("foms.api.files.order_routes.get_storage", lambda: DummyStorage())
    yield


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
_seq = 0


def _make_user(role="STAFF", team=None):
    global _seq
    _seq += 1
    user = User(
        username=f"upl_{role}_{team}_{_seq}",
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{role}-{team}-{_seq}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order():
    order = Order(
        received_date="2026-04-07",
        customer_name="첨부 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={},
        erp_stage_code="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _att_count(order_id):
    db_session.expire_all()
    return db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).count()


# 네 업로드 경로 호출기 --------------------------------------------------------
def _post_multipart(client, oid, category="measurement"):
    return client.post(
        f"/api/orders/{oid}/attachments",
        data={"category": category, "file": (io.BytesIO(b"fake"), "a.jpg")},
        content_type="multipart/form-data",
    )


def _post_session(client, oid, category="attachments", folder=None):
    folder = folder if folder is not None else f"orders/{oid}/{category}"
    return client.post("/api/upload/session", json={"filename": "a.jpg", "size": 100, "folder": folder})


def _post_batch(client, oid, category="attachments", folder=None):
    folder = folder if folder is not None else f"orders/{oid}/{category}"
    return client.post(
        "/api/upload/session/batch",
        json={"folder": folder, "files": [{"filename": "a.jpg", "size": 100}]},
    )


def _post_complete(client, oid, key=None, category="measurement"):
    key = key if key is not None else f"orders/{oid}/{category}/a.jpg"
    return client.post(
        f"/api/orders/{oid}/attachments/complete",
        json={"key": key, "filename": "a.jpg", "category": category, "item_index": 0, "size": 10},
    )


_SURFACES = {
    "multipart": _post_multipart,
    "session": _post_session,
    "batch": _post_batch,
    "complete": _post_complete,
}


# --------------------------------------------------------------------------
# 1. VIEWER 403 — 네 경로 동일 방어 (direct·multipart parity)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("surface", list(_SURFACES))
def test_viewer_denied_all_surfaces(client, surface):
    """VIEWER 는 multipart·direct(session/batch/complete) 모두 403, 첨부 0."""
    _login(client, _make_user(role="VIEWER"))
    oid = _make_order()

    resp = _SURFACES[surface](client, oid)

    assert resp.status_code == 403, (surface, resp.status_code, resp.get_data(as_text=True))
    assert resp.get_json()["success"] is False
    assert _att_count(oid) == 0  # 거부=handler 미실행


# --------------------------------------------------------------------------
# 2. purpose matrix — 용도별 role/team (허용 200 / 그 외 403)
# --------------------------------------------------------------------------
_DRAWING_MATRIX = [
    ("STAFF", "DRAWING", 200),
    ("STAFF", "CS", 200),
    ("STAFF", "SALES", 200),
    ("ADMIN", None, 200),
    ("MANAGER", None, 200),
    ("STAFF", "PRODUCTION", 403),
    ("STAFF", "SHIPMENT", 403),
    ("VIEWER", None, 403),
]

_CONSTRUCTION_MATRIX = [
    ("STAFF", "CONSTRUCTION", 200),
    ("STAFF", "CS", 200),
    ("STAFF", "SALES", 200),
    ("ADMIN", None, 200),
    ("STAFF", "DRAWING", 403),
    ("STAFF", "PRODUCTION", 403),
    ("VIEWER", None, 403),
]


@pytest.mark.parametrize("role,team,expected", _DRAWING_MATRIX)
def test_purpose_matrix_drawing_multipart(client, role, team, expected):
    """도면 업로드: DRAWING/CS/SALES + ADMIN/MANAGER 허용, 그 외 거부."""
    _login(client, _make_user(role=role, team=team))
    oid = _make_order()
    resp = _post_multipart(client, oid, category="drawing")
    assert resp.status_code == expected, (role, team, resp.status_code, resp.get_data(as_text=True))


@pytest.mark.parametrize("role,team,expected", _CONSTRUCTION_MATRIX)
def test_purpose_matrix_construction_multipart(client, role, team, expected):
    """시공 업로드: CS/SALES/CONSTRUCTION + ADMIN/MANAGER 허용, 그 외 거부."""
    _login(client, _make_user(role=role, team=team))
    oid = _make_order()
    resp = _post_multipart(client, oid, category="construction")
    assert resp.status_code == expected, (role, team, resp.status_code, resp.get_data(as_text=True))


def test_purpose_matrix_measurement_all_staff(client):
    """실측/일반 업로드는 전 STAFF 팀 허용(비파괴)."""
    for team in ["PRODUCTION", "DRAWING", "CONSTRUCTION", "SHIPMENT", "CS", "SALES"]:
        _login(client, _make_user(role="STAFF", team=team))
        oid = _make_order()
        resp = _post_multipart(client, oid, category="measurement")
        assert resp.status_code == 200, (team, resp.get_data(as_text=True))


def test_purpose_matrix_direct_session_parity(client):
    """direct 세션도 multipart 와 동일한 용도 게이트(도면=PRODUCTION 거부·DRAWING 허용)."""
    _login(client, _make_user(role="STAFF", team="PRODUCTION"))
    oid = _make_order()
    denied = _post_session(client, oid, category="drawing")
    assert denied.status_code == 403, denied.get_data(as_text=True)

    _login(client, _make_user(role="STAFF", team="DRAWING"))
    oid2 = _make_order()
    allowed = _post_session(client, oid2, category="drawing")
    assert allowed.status_code == 200 and allowed.get_json()["success"] is True


# --------------------------------------------------------------------------
# 3. arbitrary folder 0 — 완전 정규화 + 화이트리스트 (session/batch)
# --------------------------------------------------------------------------
_ARBITRARY_FOLDERS = [
    "../etc/passwd",                       # traversal
    "/etc/passwd",                         # 절대경로
    "orders/1/../2/attachments",           # traversal → 다른 order
    "orders/1/attachments/../../secret",   # 화이트리스트 탈출 traversal
    "orders/1/attachments/..",             # 상위 이동
    "chat/1",                              # 비 orders namespace
    "orders/1/secret",                     # 비화이트리스트 subfolder
    "orders/abc/attachments",              # 비숫자 order id
    "..\\..\\windows",                     # backslash 우회
    "foo/orders/1/attachments",            # prefix-only 우회(orders 가 head 아님)
    "orders//1/attachments",               # 중복 슬래시(비정규)
]


@pytest.mark.parametrize("folder", _ARBITRARY_FOLDERS)
def test_arbitrary_folder_rejected_session(client, folder):
    """ADMIN(최고권한)이라도 arbitrary/traversal folder 는 400 — 경로 방어는 권한과 무관."""
    _login(client, _make_user(role="ADMIN"))
    resp = client.post("/api/upload/session", json={"filename": "a.jpg", "size": 100, "folder": folder})
    assert resp.status_code == 400, (folder, resp.status_code, resp.get_data(as_text=True))


@pytest.mark.parametrize("folder", _ARBITRARY_FOLDERS)
def test_arbitrary_folder_rejected_batch(client, folder):
    """batch 세션도 동일하게 arbitrary/traversal folder 거부(400)."""
    _login(client, _make_user(role="ADMIN"))
    resp = client.post(
        "/api/upload/session/batch",
        json={"folder": folder, "files": [{"filename": "a.jpg", "size": 100}]},
    )
    assert resp.status_code == 400, (folder, resp.status_code, resp.get_data(as_text=True))


def test_nested_whitelisted_folder_allowed(client):
    """정본 다단 folder(orders/{id}/drawing_gateway/revisions)는 CS 가 통과(회귀 가드)."""
    _login(client, _make_user(role="STAFF", team="CS"))
    oid = _make_order()
    resp = _post_session(client, oid, folder=f"orders/{oid}/drawing_gateway/revisions")
    assert resp.status_code == 200 and resp.get_json()["success"] is True


# --------------------------------------------------------------------------
# 3b. arbitrary key + 대상 order 일치 (complete) — prefix-only 종료 금지 증명
# --------------------------------------------------------------------------
def test_complete_rejects_prefix_only_bypass(client):
    """``foo/orders/{oid}/...`` (허용 prefix 를 substring 으로만 품음)는 거부 — 과거 ``in`` 검사 우회."""
    _login(client, _make_user(role="ADMIN"))
    oid = _make_order()
    resp = client.post(
        f"/api/orders/{oid}/attachments/complete",
        json={
            "key": f"foo/orders/{oid}/measurement/a.jpg",
            "filename": "a.jpg",
            "category": "measurement",
            "item_index": 0,
            "size": 10,
        },
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert _att_count(oid) == 0


def test_complete_rejects_other_order_key(client):
    """route order_id 와 다른 order 의 key 는 거부(타 order key)."""
    _login(client, _make_user(role="ADMIN"))
    oid = _make_order()
    other = _make_order()
    resp = client.post(
        f"/api/orders/{oid}/attachments/complete",
        json={
            "key": f"orders/{other}/measurement/a.jpg",
            "filename": "a.jpg",
            "category": "measurement",
            "item_index": 0,
            "size": 10,
        },
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert _att_count(oid) == 0


def test_complete_rejects_traversal_key(client):
    """정규화 후 화이트리스트를 탈출하는 traversal key 는 거부."""
    _login(client, _make_user(role="ADMIN"))
    oid = _make_order()
    resp = client.post(
        f"/api/orders/{oid}/attachments/complete",
        json={
            "key": f"orders/{oid}/measurement/../../secret/a.jpg",
            "filename": "a.jpg",
            "category": "measurement",
            "item_index": 0,
            "size": 10,
        },
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert _att_count(oid) == 0


# --------------------------------------------------------------------------
# 4. happy path — 방어가 정상 업로드를 막지 않음(green 기준선, direct·multipart)
# --------------------------------------------------------------------------
def test_admin_multipart_upload_succeeds(client):
    _login(client, _make_user(role="ADMIN"))
    oid = _make_order()
    resp = _post_multipart(client, oid, category="measurement")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    assert _att_count(oid) == 1


def test_admin_session_then_complete_succeeds(client):
    _login(client, _make_user(role="ADMIN"))
    oid = _make_order()
    sess = _post_session(client, oid, category="attachments")
    assert sess.status_code == 200 and sess.get_json()["success"] is True
    key = sess.get_json()["key"]

    done = client.post(
        f"/api/orders/{oid}/attachments/complete",
        json={"key": key, "filename": "a.jpg", "category": "measurement", "item_index": 0, "size": 10},
    )
    assert done.status_code == 200 and done.get_json()["success"] is True
    assert _att_count(oid) == 1
