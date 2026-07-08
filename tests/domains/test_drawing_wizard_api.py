"""도면 마법사 API 계약 테스트 (GET/PUT/asset).

기존 도면 워크벤치/structured PUT 테스트의 픽스처 관행을 따른다:
``db_session`` 직접 생성 + ``client.session_transaction()`` 로그인.
"""

import copy
import io
import json
from datetime import date

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import Notification, Order, OrderAttachment, User


def _login(client, *, username, role, team):
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _login_participant_admin(client, username="wizard-admin"):
    return _login(client, username=username, role="ADMIN", team="DRAWING")


def _login_non_participant(client, username="wizard-viewer"):
    return _login(client, username=username, role="STAFF", team="CS")


def _erp_order(structured_data=None):
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="서으뜸",
        phone="010-1111-2222",
        address="대구",
        product="붙박이장",
        status="DRAWING",
        manager_name="하우드 김성일",
        is_erp_order=True,
        structured_data=structured_data
        or {
            "parties": {
                "customer": {"name": "서으뜸", "phone": "01092639140"},
                "manager": {"name": "하우드 김성일"},
            },
            "items": [{"product_name": "여닫이장", "color": "클린화이트"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _valid_state(order_id):
    return {
        "v": 1,
        "sheets": [
            {
                "id": "s-1",
                "name": "도면 1",
                "form": {"customer_name": "서으뜸", "checks": {"d_site": True}},
                "objects": [
                    {
                        "id": "o-1",
                        "type": "text",
                        "x": 100,
                        "y": 100,
                        "w": 200,
                        "text": "[SR] 60*2440",
                        "size": 20,
                        "color": "#000000",
                        "bold": False,
                        "align": "left",
                    },
                    {
                        "id": "o-2",
                        "type": "image",
                        "x": 90,
                        "y": 420,
                        "w": 620,
                        "h": 360,
                        "key": f"orders/{order_id}/drawing_wizard/assets/x.png",
                        "natural_w": 1240,
                        "natural_h": 720,
                    },
                ],
            }
        ],
    }


def test_get_wizard_returns_defaults_and_null_state(client):
    user = _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(f"/api/orders/{order_id}/drawing-wizard")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["order_id"] == order_id
    assert data["data"]["state"] is None
    assert data["data"]["can_save"] is True
    assert data["data"]["drew_default"] == user.name
    assert data["data"]["defaults"]["customer_name"] == "서으뜸"
    assert data["data"]["defaults"]["logo"] == "haud"


def test_get_wizard_non_participant_read_only(client):
    order = _erp_order()
    order_id = order.id
    _login_non_participant(client)

    resp = client.get(f"/api/orders/{order_id}/drawing-wizard")

    assert resp.status_code == 200
    assert resp.get_json()["data"]["can_save"] is False


def test_put_then_get_round_trips_state(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    put_resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _valid_state(order_id), "base_updated_at": None},
    )
    assert put_resp.status_code == 200, put_resp.get_json()
    updated_at = put_resp.get_json()["data"]["updated_at"]
    assert updated_at

    get_resp = client.get(f"/api/orders/{order_id}/drawing-wizard")
    state = get_resp.get_json()["data"]["state"]
    assert state is not None
    assert state["v"] == 1
    assert state["updated_at"] == updated_at
    assert state["sheets"][0]["name"] == "도면 1"


def test_put_rejects_non_participant(client):
    order = _erp_order()
    order_id = order.id
    _login_non_participant(client)

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _valid_state(order_id), "base_updated_at": None},
    )

    assert resp.status_code == 403


def test_put_rejects_oversized_state(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    big_text = "A" * 2000
    objects = [
        {
            "id": f"o-{i}",
            "type": "text",
            "x": 10,
            "y": 10,
            "w": 100,
            "text": big_text,
            "size": 14,
            "color": "#000000",
            "bold": False,
            "align": "left",
        }
        for i in range(40)
    ]
    state = {"v": 1, "sheets": [{"id": "s-1", "name": "S", "form": {}, "objects": objects}]}

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": None},
    )

    assert resp.status_code == 400
    assert "64KB" in resp.get_json()["message"]


def test_put_rejects_foreign_order_image_key(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    state = _valid_state(order_id)
    state["sheets"][0]["objects"][1]["key"] = (
        f"orders/{order_id + 999}/drawing_wizard/assets/x.png"
    )

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": None},
    )

    assert resp.status_code == 400


def test_put_rejects_data_uri_image_key(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    state = _valid_state(order_id)
    state["sheets"][0]["objects"][1]["key"] = "data:image/png;base64,AAAA"

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": None},
    )

    assert resp.status_code == 400


def test_put_conflict_when_base_updated_at_is_stale(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    first = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _valid_state(order_id), "base_updated_at": None},
    )
    assert first.status_code == 200

    conflict = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _valid_state(order_id), "base_updated_at": None},
    )

    assert conflict.status_code == 409
    body = conflict.get_json()
    assert body["error"] == "conflict"
    assert body["server_updated_at"]


def test_asset_rejects_non_image_extension(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/asset",
        data={"file": (io.BytesIO(b"x"), "notes.txt")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400


def test_asset_upload_returns_key_and_view_url(client, monkeypatch):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    class DummyStorage:
        def upload_file(self, file_obj, filename, folder):
            return {"success": True, "key": f"{folder}/{filename}"}

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: DummyStorage())

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/asset",
        data={"file": (io.BytesIO(b"fakeimg"), "plan.png")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    expected_key = f"orders/{order_id}/drawing_wizard/assets/plan.png"
    assert data["key"] == expected_key
    assert data["view_url"] == f"/api/files/view/{expected_key}"
    assert data["filename"] == "plan.png"


def test_asset_raw_returns_bytes_with_mimetype(client, monkeypatch):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    key = f"orders/{order_id}/drawing_wizard/assets/plan.png"
    payload = b"\x89PNG\r\n\x1a\nFAKE-PNG-BYTES"

    class DummyStorage:
        def read_file_bytes(self, k):
            return payload if k == key else None

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: DummyStorage())

    resp = client.get(
        f"/api/orders/{order_id}/drawing-wizard/asset-raw",
        query_string={"key": key},
    )

    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == payload
    assert "private" in resp.headers.get("Cache-Control", "")


def test_asset_raw_rejects_foreign_order_prefix(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(
        f"/api/orders/{order_id}/drawing-wizard/asset-raw",
        query_string={"key": f"orders/{order_id + 999}/drawing_wizard/assets/x.png"},
    )

    assert resp.status_code == 400


def test_asset_raw_missing_file_returns_404(client, monkeypatch):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    class DummyStorage:
        def read_file_bytes(self, k):
            return None

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: DummyStorage())

    resp = client.get(
        f"/api/orders/{order_id}/drawing-wizard/asset-raw",
        query_string={"key": f"orders/{order_id}/drawing_wizard/assets/missing.png"},
    )

    assert resp.status_code == 404


def test_asset_raw_requires_login(client):
    resp = client.get(
        "/api/orders/1/drawing-wizard/asset-raw",
        query_string={"key": "orders/1/drawing_wizard/assets/x.png"},
    )

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# v2 Konva 주석 엔진 — 신규 도형 타입(rect/ellipse/arrow/line) + rotation 검증
# ---------------------------------------------------------------------------


def _state_with_objects(objects):
    return {
        "v": 1,
        "sheets": [{"id": "s-1", "name": "도면 1", "form": {}, "objects": objects}],
    }


def _put_state(client, order_id, objects):
    return client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _state_with_objects(objects), "base_updated_at": None},
    )


def test_put_then_get_round_trips_shape_objects(client):
    """rect/ellipse/arrow/line 신규 타입 각 1건 정상 저장 왕복(rotation/points/stroke 보존)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    objects = [
        {
            "id": "o-rect",
            "type": "rect",
            "x": 100,
            "y": 120,
            "w": 200,
            "h": 90,
            "stroke": "#000000",
            "strokeWidth": 2,
            "rotation": 15,
        },
        {
            "id": "o-ell",
            "type": "ellipse",
            "x": 400,
            "y": 200,
            "w": 160,
            "h": 120,
            "stroke": "#1c62d6",
            "strokeWidth": 1,
            "rotation": 0,
        },
        {
            "id": "o-arr",
            "type": "arrow",
            "points": [50, 60, 300, 320],
            "stroke": "#e03131",
            "strokeWidth": 3,
            "rotation": 0,
        },
        {
            "id": "o-line",
            "type": "line",
            "points": [10, 20, 400, 20],
            "stroke": "#000000",
            "strokeWidth": 2,
        },
    ]

    put_resp = _put_state(client, order_id, objects)
    assert put_resp.status_code == 200, put_resp.get_json()

    state = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    saved = state["sheets"][0]["objects"]
    assert [o["type"] for o in saved] == ["rect", "ellipse", "arrow", "line"]
    assert saved[0]["strokeWidth"] == 2
    assert saved[0]["rotation"] == 15
    assert saved[1]["stroke"] == "#1c62d6"
    assert saved[2]["points"] == [50, 60, 300, 320]
    assert saved[3]["points"] == [10, 20, 400, 20]


def test_put_rejects_invalid_shape_stroke_width(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = {
        "id": "o-1",
        "type": "rect",
        "x": 10,
        "y": 10,
        "w": 50,
        "h": 50,
        "stroke": "#000000",
        "strokeWidth": 5,
    }

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_rejects_line_with_three_points(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = {
        "id": "o-1",
        "type": "arrow",
        "points": [10, 20, 30],
        "stroke": "#000000",
        "strokeWidth": 2,
    }

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_rejects_unsupported_object_type(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = {"id": "o-1", "type": "star", "x": 10, "y": 10, "w": 50, "h": 50}

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_rejects_non_numeric_rotation(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = {
        "id": "o-1",
        "type": "rect",
        "x": 10,
        "y": 10,
        "w": 50,
        "h": 50,
        "stroke": "#000000",
        "strokeWidth": 2,
        "rotation": "90",
    }

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 표 레이아웃(열/행 폭 조절) + 표 글자 크기 승격 값(form.layout / form.cell_font)
# ---------------------------------------------------------------------------


def _state_with_form(form):
    return {
        "v": 1,
        "sheets": [{"id": "s-1", "name": "도면 1", "form": form, "objects": []}],
    }


def test_put_then_get_round_trips_form_layout_and_cell_font(client):
    """form.layout(cols/addr/rows) + cell_font 정상 저장 왕복(값 보존)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    layout = {
        "cols": [130, 220, 320, 410, 730, 830, 1230, 1335],
        "addr": 95,
        "rows": [925, 950, 975],
    }
    form = {"customer_name": "서으뜸", "checks": {}, "layout": layout, "cell_font": 20}

    put_resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _state_with_form(form), "base_updated_at": None},
    )
    assert put_resp.status_code == 200, put_resp.get_json()

    saved = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    saved_form = saved["sheets"][0]["form"]
    assert saved_form["layout"] == layout
    assert saved_form["cell_font"] == 20


def test_put_rejects_non_numeric_layout_cols(client):
    """layout.cols 에 문자가 섞이면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    form = {"layout": {"cols": ["x", 220, 320], "addr": 95, "rows": [925, 950, 975]}}

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _state_with_form(form), "base_updated_at": None},
    )

    assert resp.status_code == 400


def test_put_rejects_out_of_range_cell_font(client):
    """cell_font 가 허용 범위(10~28)를 벗어나면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _state_with_form({"cell_font": 99}), "base_updated_at": None},
    )

    assert resp.status_code == 400


def test_put_then_get_round_trips_layout_top(client):
    """form.layout.top(하단 표 상단선 이동) 정상 저장 왕복(값 보존)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    layout = {
        "cols": [130, 220, 320, 410, 730, 830, 1230, 1335],
        "addr": 95,
        "rows": [925, 950, 975],
        "top": 760,
    }
    form = {"customer_name": "서으뜸", "checks": {}, "layout": layout, "cell_font": 18}

    put_resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _state_with_form(form), "base_updated_at": None},
    )
    assert put_resp.status_code == 200, put_resp.get_json()

    saved = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    saved_form = saved["sheets"][0]["form"]
    assert saved_form["layout"]["top"] == 760
    assert saved_form["layout"] == layout


def test_put_rejects_out_of_range_layout_top(client):
    """layout.top 이 허용 범위(100~980)를 벗어나면(top=50) 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    form = {"layout": {"cols": [130, 220, 320], "rows": [925, 950, 975], "top": 50}}

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _state_with_form(form), "base_updated_at": None},
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 텍스트 리치 편집 — 글자 단위 스타일 런(runs) 검증
# ---------------------------------------------------------------------------


def _text_obj(text, runs=None, **overrides):
    obj = {
        "id": "o-txt",
        "type": "text",
        "x": 100,
        "y": 100,
        "w": 200,
        "text": text,
        "size": 20,
        "color": "#000000",
        "bold": False,
        "align": "left",
    }
    obj.update(overrides)
    if runs is not None:
        obj["runs"] = runs
    return obj


def test_put_then_get_round_trips_text_runs(client):
    """글자 단위 색상/굵기 런이 있는 텍스트가 정상 저장 왕복(runs 보존)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    runs = [
        {"t": "1420", "c": "#e03131", "b": False},
        {"t": " EP", "c": "#000000", "b": True},
    ]
    obj = _text_obj("1420 EP", runs=runs)

    put_resp = _put_state(client, order_id, [obj])
    assert put_resp.status_code == 200, put_resp.get_json()

    state = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    saved = state["sheets"][0]["objects"][0]
    assert saved["runs"] == runs
    assert saved["text"] == "1420 EP"


def test_put_rejects_runs_text_mismatch(client):
    """런 t 를 이은 문자열이 text 와 다르면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = _text_obj(
        "1420 EP",
        runs=[
            {"t": "1420", "c": "#e03131", "b": False},
            {"t": " XX", "c": "#000000", "b": False},
        ],
    )

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_rejects_too_many_runs(client):
    """런 개수가 60개를 초과하면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    runs = [{"t": "a", "c": "#000000", "b": False} for _ in range(61)]
    obj = _text_obj("a" * 61, runs=runs)

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_rejects_invalid_run_color(client):
    """런 색상이 #rrggbb 형식이 아니면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = _text_obj(
        "hi",
        runs=[{"t": "hi", "c": "red", "b": False}],
    )

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_rejects_run_non_bool_bold(client):
    """런 굵기(b)가 불리언이 아니면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = _text_obj(
        "hi",
        runs=[{"t": "hi", "c": "#000000", "b": "yes"}],
    )

    resp = _put_state(client, order_id, [obj])

    assert resp.status_code == 400


def test_put_accepts_text_without_runs_backward_compat(client):
    """runs 없는 기존 단색 텍스트는 그대로 통과(하위호환)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    obj = _text_obj("단색 텍스트", color="#1c62d6", bold=True)

    put_resp = _put_state(client, order_id, [obj])
    assert put_resp.status_code == 200, put_resp.get_json()

    state = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    saved = state["sheets"][0]["objects"][0]
    assert "runs" not in saved
    assert saved["color"] == "#1c62d6"


# ---------------------------------------------------------------------------
# 도면 마법사 사용자 프리셋 — 전역 SystemSetting(도면팀 공유) sanitize + API 왕복
# ---------------------------------------------------------------------------

from foms.services.drawing_wizard_presets import (  # noqa: E402
    MAX_LABEL_LEN,
    MAX_PRESETS,
    MAX_TEXT_LEN,
    sanitize_wizard_presets,
)

PRESETS_ENDPOINT = "/api/orders/drawing-wizard/presets"


def _login_preset_denied(client, username="preset-denied"):
    """프리셋 관리 권한이 없는 사용자(비-ADMIN·비-DRAWING·비-편집팀)."""
    return _login(client, username=username, role="STAFF", team="PRODUCTION")


def test_sanitize_wizard_presets_trims_and_drops_invalid():
    raw = [
        {"label": "  SR 컷  ", "text": "  [SR] 60*2440  "},
        {"label": "무본문", "text": "   "},  # 본문 없음 → 제거
        "not-a-dict",  # 비-딕트 → 제거
        {"label": 123, "text": "숫자라벨"},  # 라벨 비문자열 → 제거
        {"text": "라벨없음"},  # 라벨 없음 → 본문 첫 줄로 자동 라벨
    ]
    cleaned = sanitize_wizard_presets(raw)
    assert cleaned == [
        {"label": "SR 컷", "text": "[SR] 60*2440"},
        {"label": "라벨없음", "text": "라벨없음"},
    ]


def test_sanitize_wizard_presets_enforces_length_and_count_caps():
    over_label = {"label": "L" * (MAX_LABEL_LEN + 1), "text": "본문"}
    over_text = {"label": "라벨", "text": "T" * (MAX_TEXT_LEN + 1)}
    assert sanitize_wizard_presets([over_label]) == []
    assert sanitize_wizard_presets([over_text]) == []

    many = [{"label": f"L{i}", "text": f"본문{i}"} for i in range(MAX_PRESETS + 10)]
    assert len(sanitize_wizard_presets(many)) == MAX_PRESETS


def test_sanitize_wizard_presets_non_list_returns_empty():
    assert sanitize_wizard_presets(None) == []
    assert sanitize_wizard_presets("x") == []
    assert sanitize_wizard_presets({"label": "a", "text": "b"}) == []


def test_presets_get_empty_initially(client):
    _login_participant_admin(client)

    resp = client.get(PRESETS_ENDPOINT)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["presets"] == []


def test_presets_post_then_get_round_trips_globally(client):
    _login_participant_admin(client)

    post_resp = client.post(
        PRESETS_ENDPOINT,
        json={"presets": [{"label": "테스트컷", "text": "[SR] 테스트컷"}]},
    )
    assert post_resp.status_code == 200, post_resp.get_json()
    assert post_resp.get_json()["data"]["presets"] == [
        {"label": "테스트컷", "text": "[SR] 테스트컷"}
    ]

    # 전역 저장 → 다른 사용자 세션에서도 동일 목록 조회
    _login_non_participant(client, username="preset-viewer")
    get_resp = client.get(PRESETS_ENDPOINT)
    assert get_resp.status_code == 200
    assert get_resp.get_json()["data"]["presets"] == [
        {"label": "테스트컷", "text": "[SR] 테스트컷"}
    ]


def test_presets_post_sanitizes_before_save(client):
    _login_participant_admin(client)

    resp = client.post(
        PRESETS_ENDPOINT,
        json={
            "presets": [
                {"label": "  좋은라벨  ", "text": "  유효본문  "},
                {"label": "빈본문", "text": "   "},
                {"label": "L" * (MAX_LABEL_LEN + 1), "text": "라벨초과"},
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["data"]["presets"] == [{"label": "좋은라벨", "text": "유효본문"}]


def test_presets_post_rejects_non_list_body(client):
    _login_participant_admin(client)

    resp = client.post(PRESETS_ENDPOINT, json={"presets": "nope"})

    assert resp.status_code == 400


def test_presets_post_rejects_unprivileged_user(client):
    _login_preset_denied(client)

    resp = client.post(
        PRESETS_ENDPOINT,
        json={"presets": [{"label": "x", "text": "y"}]},
    )

    assert resp.status_code == 403


def test_presets_get_requires_login(client):
    resp = client.get(PRESETS_ENDPOINT)

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# 제품별 도면 시트 — 좌측 제품 리스트 · ?item 제품별 defaults · 시트 승격 값
# ---------------------------------------------------------------------------


def test_get_wizard_returns_products_list(client):
    """GET 응답 data.products = [{index, name, spec, price}] (규격 W×D×H / price int·null)."""
    _login_participant_admin(client)
    order = _erp_order(
        structured_data={
            "parties": {"customer": {"name": "서으뜸"}},
            "items": [
                {
                    "product_name": "여닫이장",
                    "color": "화이트",
                    "width": "3500",
                    "depth": "620",
                    "height": "2300",
                    "price": "1200000",
                },
                {"product_name": "수납장", "spec": "현장실측"},
            ],
        }
    )
    order_id = order.id

    resp = client.get(f"/api/orders/{order_id}/drawing-wizard")

    assert resp.status_code == 200
    products = resp.get_json()["data"]["products"]
    assert len(products) == 2
    assert products[0] == {
        "index": 0,
        "name": "여닫이장",
        "spec": "3500×620×2300",
        "price": 1200000,
    }
    assert products[1]["index"] == 1
    assert products[1]["name"] == "수납장"
    assert products[1]["spec"] == "현장실측"
    assert products[1]["price"] is None


def test_get_wizard_item_query_returns_that_products_defaults(client):
    """?item=N → 해당 제품 한 건 기준 defaults(product_name도 단일), 미지정은 전체 조인."""
    _login_participant_admin(client)
    order = _erp_order(
        structured_data={
            "parties": {"customer": {"name": "서으뜸"}},
            "items": [
                {"product_name": "장A", "color": "화이트"},
                {"product_name": "장B", "color": "블랙"},
            ],
        }
    )
    order_id = order.id

    resp = client.get(f"/api/orders/{order_id}/drawing-wizard?item=1")
    assert resp.status_code == 200
    d = resp.get_json()["data"]["defaults"]
    assert d["product_name"] == "장B"
    assert d["color"] == "블랙"

    resp0 = client.get(f"/api/orders/{order_id}/drawing-wizard")
    assert resp0.get_json()["data"]["defaults"]["product_name"] == "장A / 장B"


def test_put_then_get_round_trips_sheet_product_index_and_attachment_id(client):
    """시트 승격 값(product_index/attachment_id) 정상 저장 왕복(값 보존)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    state = {
        "v": 1,
        "sheets": [
            {
                "id": "s-1",
                "name": "장B",
                "form": {},
                "objects": [],
                "product_index": 1,
                "attachment_id": 42,
            }
        ],
    }

    put_resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": None},
    )
    assert put_resp.status_code == 200, put_resp.get_json()

    saved = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    sheet = saved["sheets"][0]
    assert sheet["product_index"] == 1
    assert sheet["attachment_id"] == 42


def test_put_rejects_out_of_range_product_index(client):
    """product_index 가 0~199 범위를 벗어나면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    state = {
        "v": 1,
        "sheets": [{"id": "s-1", "name": "S", "form": {}, "objects": [], "product_index": 999}],
    }

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": None},
    )

    assert resp.status_code == 400


def test_put_rejects_non_int_attachment_id(client):
    """attachment_id 가 정수가 아니면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    state = {
        "v": 1,
        "sheets": [{"id": "s-1", "name": "S", "form": {}, "objects": [], "attachment_id": "x"}],
    }

    resp = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": state, "base_updated_at": None},
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 시트 PNG 저장 — '전달 대기함'(drawing_wizard.pending) 보관 (OrderAttachment 미생성)
# ---------------------------------------------------------------------------


def _png_file(name="도면_고객_1_장1.png", body=b"\x89PNG\r\n\x1a\nFAKE"):
    return (io.BytesIO(body), name)


def test_sheet_png_stores_pending_without_attachment(client, monkeypatch):
    """sheet-png 저장 = pending 기록 + OrderAttachment(category='drawing') 미생성."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    class DummyStorage:
        def upload_file(self, file_obj, filename, folder):
            return {"success": True, "key": f"{folder}/{filename}"}

        def delete_file(self, key):
            return True

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: DummyStorage())

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/sheet-png",
        data={"file": _png_file(), "sheet_id": "s-1", "sheet_name": "도면 1"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    key = data["key"]
    assert key.startswith(f"orders/{order_id}/drawing_wizard/exports/")
    assert "attachment_id" not in data  # 도면 탭 첨부 식별자 없음(분리)

    # 도면 탭(OrderAttachment category='drawing')은 만들어지지 않는다.
    db_session.expire_all()
    assert (
        db_session.query(OrderAttachment)
        .filter_by(order_id=order_id, category="drawing")
        .count()
        == 0
    )

    # pending 목록에 기록된다.
    pending = client.get(
        f"/api/orders/{order_id}/drawing-wizard/pending"
    ).get_json()["data"]["pending"]
    assert len(pending) == 1
    assert pending[0]["sheet_id"] == "s-1"
    assert pending[0]["key"] == key
    assert pending[0]["sheet_name"] == "도면 1"
    assert pending[0]["at"]


def test_sheet_png_replace_same_sheet_overwrites_and_deletes_old(client, monkeypatch):
    """같은 sheet_id 재저장 → pending 1건 유지, key 갱신, 구 R2 파일 삭제."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    uploads = {"n": 0}
    deleted = []

    class DummyStorage:
        def upload_file(self, file_obj, filename, folder):
            uploads["n"] += 1
            return {"success": True, "key": f"{folder}/{uploads['n']}_{filename}"}

        def delete_file(self, key):
            deleted.append(key)
            return True

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: DummyStorage())

    resp1 = client.post(
        f"/api/orders/{order_id}/drawing-wizard/sheet-png",
        data={"file": _png_file(), "sheet_id": "s-1"},
        content_type="multipart/form-data",
    )
    key1 = resp1.get_json()["data"]["key"]

    resp2 = client.post(
        f"/api/orders/{order_id}/drawing-wizard/sheet-png",
        data={"file": _png_file(body=b"\x89PNG\r\n\x1a\nEDIT"), "sheet_id": "s-1"},
        content_type="multipart/form-data",
    )
    key2 = resp2.get_json()["data"]["key"]
    assert key2 != key1

    pending = client.get(
        f"/api/orders/{order_id}/drawing-wizard/pending"
    ).get_json()["data"]["pending"]
    assert len(pending) == 1          # 같은 시트 → 1건 유지(덮어씀)
    assert pending[0]["key"] == key2  # 최신 key
    assert key1 in deleted            # 구 파일 삭제


def test_sheet_png_rejects_non_participant(client):
    order = _erp_order()
    order_id = order.id
    _login_non_participant(client)

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/sheet-png",
        data={"file": _png_file(), "sheet_id": "s-1"},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 403


def test_sheet_png_rejects_non_png_extension(client):
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/sheet-png",
        data={"file": (io.BytesIO(b"x"), "plan.jpg"), "sheet_id": "s-1"},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400


def test_sheet_png_requires_login(client):
    resp = client.post(
        "/api/orders/1/drawing-wizard/sheet-png",
        data={"file": _png_file(), "sheet_id": "s-1"},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# 실측 사진 사이드 참조 — GET measure_photos 구조 + import-attachment(복사 삽입)
# ---------------------------------------------------------------------------


def _measure_attachment(order_id, filename, storage_key, *, category="measurement",
                        item_index=None, thumbnail_key=None):
    att = OrderAttachment(
        order_id=order_id,
        filename=filename,
        file_type="image",
        category=category,
        item_index=item_index,
        storage_key=storage_key,
        thumbnail_key=thumbnail_key,
    )
    db_session.add(att)
    db_session.commit()
    return att


def test_get_wizard_returns_measure_photos(client):
    """GET data.measure_photos = [{key, filename, item_index(null=공통), thumb_url}].

    제품 범위 밖 item_index 는 공통(None)으로 정규화되고, thumb_url 은 thumbnail_key 우선.
    """
    _login_participant_admin(client)
    order = _erp_order(
        structured_data={
            "parties": {"customer": {"name": "서으뜸"}},
            "items": [{"product_name": "장A"}, {"product_name": "장B"}],
        }
    )
    order_id = order.id
    _measure_attachment(
        order_id, "m0.jpg", f"orders/{order_id}/measurement/m0.jpg",
        item_index=0, thumbnail_key=f"orders/{order_id}/measurement/thumb_m0.jpg",
    )
    # item_index=9 는 제품(2개) 범위 밖 → 공통(None)으로 정규화, 썸네일 없으면 storage_key.
    _measure_attachment(
        order_id, "mc.jpg", f"orders/{order_id}/measurement/mc.jpg",
        category="photo", item_index=9,
    )

    resp = client.get(f"/api/orders/{order_id}/drawing-wizard")
    assert resp.status_code == 200
    photos = resp.get_json()["data"]["measure_photos"]
    assert len(photos) == 2
    by_key = {p["key"]: p for p in photos}
    m0 = by_key[f"orders/{order_id}/measurement/m0.jpg"]
    assert m0["item_index"] == 0
    assert m0["filename"] == "m0.jpg"
    assert m0["thumb_url"] == f"/api/files/view/orders/{order_id}/measurement/thumb_m0.jpg"
    mc = by_key[f"orders/{order_id}/measurement/mc.jpg"]
    assert mc["item_index"] is None
    assert mc["thumb_url"] == f"/api/files/view/orders/{order_id}/measurement/mc.jpg"


def test_import_attachment_copies_measure_photo(client, monkeypatch):
    """실측 첨부 key → drawing_wizard/assets 로 복사, 새 key 반환·원본 첨부 불변."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    src_key = f"orders/{order_id}/measurement/site.png"
    _measure_attachment(order_id, "site.png", src_key, item_index=0)

    class DummyStorage:
        def read_file_bytes(self, k):
            return b"\x89PNG\r\n\x1a\nFAKE" if k == src_key else None

        def upload_file(self, file_obj, filename, folder):
            return {"success": True, "key": f"{folder}/{filename}"}

    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: DummyStorage())

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/import-attachment",
        json={"key": src_key},
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    new_key = f"orders/{order_id}/drawing_wizard/assets/site.png"
    assert data["key"] == new_key
    assert data["view_url"] == f"/api/files/view/{new_key}"

    # 실측 원본 첨부는 그대로(행·storage_key 불변).
    db_session.expire_all()
    rows = db_session.query(OrderAttachment).filter_by(order_id=order_id).all()
    assert len(rows) == 1
    assert rows[0].storage_key == src_key


def test_import_attachment_rejects_foreign_order_key(client):
    """현재 주문의 실측 첨부에 없는 key(타 주문)면 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/import-attachment",
        json={"key": f"orders/{order_id + 999}/measurement/x.png"},
    )

    assert resp.status_code == 400


def test_import_attachment_rejects_non_measure_category(client):
    """key 는 존재하지만 category 가 실측 3종이 아니면(예: drawing) 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    key = f"orders/{order_id}/drawing/plan.png"
    _measure_attachment(order_id, "plan.png", key, category="drawing")

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/import-attachment",
        json={"key": key},
    )

    assert resp.status_code == 400


def test_import_attachment_rejects_non_participant(client):
    """비참여자는 실측 첨부가 존재해도 403."""
    order = _erp_order()
    order_id = order.id
    key = f"orders/{order_id}/measurement/site.png"
    _measure_attachment(order_id, "site.png", key, item_index=0)
    _login_non_participant(client)

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/import-attachment",
        json={"key": key},
    )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 버전 이력 — 전달 시점 시트 스냅샷 저장/목록/내용/30캡/PUT 보존/권한
# ---------------------------------------------------------------------------

_VERSION_SHEET = {"id": "s-1", "name": "도면 1", "form": {}, "objects": []}


class _CapturingStorage:
    """업로드 바이트를 key별로 보관해 read_file_bytes 로 돌려주는 테스트용 스토리지."""

    def __init__(self):
        self.store = {}
        self.deleted = []
        self.folders = []

    def upload_file(self, file_obj, filename, folder):
        self.folders.append(folder)
        self.store[f"{folder}/{filename}"] = file_obj.read()
        return {"success": True, "key": f"{folder}/{filename}"}

    def read_file_bytes(self, key):
        return self.store.get(key)

    def delete_file(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)
        return True


def _snapshot(client, order_id, sheet=None, sheet_id="s-1", sheet_name="도면 1"):
    return client.post(
        f"/api/orders/{order_id}/drawing-wizard/version-snapshot",
        json={"sheet": sheet or _VERSION_SHEET, "sheet_id": sheet_id, "sheet_name": sheet_name},
    )


def test_version_snapshot_uploads_and_appends_pointer(client, monkeypatch):
    """스냅샷 = 시트 JSON 업로드(versions 폴더) + sd.drawing_wizard.versions 포인터 append."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    resp = _snapshot(client, order_id)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["v"] == 1
    assert storage.folders == [f"orders/{order_id}/drawing_wizard/versions"]

    expected_key = f"orders/{order_id}/drawing_wizard/versions/v1_s-1.json"
    assert json.loads(storage.store[expected_key]) == _VERSION_SHEET

    versions = client.get(
        f"/api/orders/{order_id}/drawing-wizard/versions"
    ).get_json()["data"]["versions"]
    assert len(versions) == 1
    ptr = versions[0]
    assert ptr["v"] == 1
    assert ptr["sheet_name"] == "도면 1"
    assert ptr["key"] == expected_key
    assert ptr["by_name"]  # 작성자 기록됨
    assert ptr["at"]       # 시각 기록됨


def test_version_content_returns_snapshot_sheet(client, monkeypatch):
    """version-content 는 스냅샷 파일(시트 JSON)을 그대로 반환한다."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    sheet = {"id": "s-1", "name": "도면 1", "form": {"customer_name": "서으뜸"}, "objects": []}
    _snapshot(client, order_id, sheet=sheet)

    key = f"orders/{order_id}/drawing_wizard/versions/v1_s-1.json"
    resp = client.get(
        f"/api/orders/{order_id}/drawing-wizard/version-content",
        query_string={"key": key},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["sheet"] == sheet


def test_version_content_rejects_foreign_prefix(client):
    """versions 접두사 밖 key(assets 등)는 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = client.get(
        f"/api/orders/{order_id}/drawing-wizard/version-content",
        query_string={"key": f"orders/{order_id}/drawing_wizard/assets/x.png"},
    )

    assert resp.status_code == 400


def test_version_snapshot_caps_at_30_and_deletes_oldest(client, monkeypatch):
    """포인터 30개 초과 시 가장 오래된 것부터 포인터·R2 파일 제거."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    for _ in range(32):
        assert _snapshot(client, order_id).status_code == 200

    versions = client.get(
        f"/api/orders/{order_id}/drawing-wizard/versions"
    ).get_json()["data"]["versions"]
    assert len(versions) == 30
    assert [v["v"] for v in versions] == list(range(3, 33))  # v1·v2 밀려남
    assert storage.deleted == [
        f"orders/{order_id}/drawing_wizard/versions/v1_s-1.json",
        f"orders/{order_id}/drawing_wizard/versions/v2_s-1.json",
    ]


def test_put_preserves_server_versions(client, monkeypatch):
    """versions 없는 state 로 PUT 해도 서버 보존 versions 는 유지된다(클라 삭제 사고 차단)."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id
    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    first = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _valid_state(order_id), "base_updated_at": None},
    )
    assert first.status_code == 200
    base = first.get_json()["data"]["updated_at"]

    assert _snapshot(client, order_id).status_code == 200

    # 스냅샷은 updated_at 을 건드리지 않으므로 base 로 재저장해도 409 아님.
    second = client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json={"state": _valid_state(order_id), "base_updated_at": base},
    )
    assert second.status_code == 200, second.get_json()

    versions = client.get(
        f"/api/orders/{order_id}/drawing-wizard/versions"
    ).get_json()["data"]["versions"]
    assert len(versions) == 1
    assert versions[0]["v"] == 1


def test_version_snapshot_rejects_invalid_sheet(client):
    """스냅샷 시트가 스키마 위반이면(문자열 아닌 id) 업로드 전 400."""
    _login_participant_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = _snapshot(client, order_id, sheet={"id": 123, "name": "x", "form": {}, "objects": []})

    assert resp.status_code == 400


def test_version_snapshot_rejects_non_participant(client):
    """비참여자는 스냅샷 저장 403."""
    order = _erp_order()
    order_id = order.id
    _login_non_participant(client)

    resp = _snapshot(client, order_id)

    assert resp.status_code == 403


def test_versions_get_requires_login(client):
    resp = client.get("/api/orders/1/drawing-wizard/versions")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# 전달 대기 → 담당자 일괄 전달 (transfer-pending) + transfer-drawing 회귀
# ---------------------------------------------------------------------------


def _order_with_assignee(user_id, *, extra=None):
    """도면 담당자(drawing_assignee_user_ids)를 지정한 ERP 주문(매니저=하우드 → HAUDD 팀)."""
    sd = {
        "parties": {
            "customer": {"name": "서으뜸"},
            "manager": {"name": "하우드 김성일"},
        },
        "assignments": {"drawing_assignee_user_ids": [user_id]},
    }
    if extra:
        sd.update(extra)
    return _erp_order(structured_data=sd)


def _seed_pending(order):
    """order.structured_data.drawing_wizard 에 pending 1건 + 대응 시트를 심는다."""
    order_id = order.id
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"] = {
        "v": 1,
        "sheets": [{"id": "s-1", "name": "도면 1", "form": {}, "objects": []}],
        "pending": {
            "s-1": {
                "key": f"orders/{order_id}/drawing_wizard/exports/1_a.png",
                "filename": "도면_a.png",
                "at": "2026-07-07 10:00",
                "sheet_name": "도면 1",
            }
        },
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def test_transfer_pending_transfers_and_clears(client, monkeypatch):
    """transfer-pending = pending → drawing_current_files/status=TRANSFERRED + 알림 + pending 비움 + 스냅샷."""
    user = _login_participant_admin(client)
    order = _order_with_assignee(user.id)
    order_id = order.id
    _seed_pending(order)

    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/transfer-pending",
        json={"note": "확인 부탁", "mode": "APPEND"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["count"] == 1

    db_session.expire_all()
    sd = db_session.query(Order).filter_by(id=order_id).first().structured_data
    files = sd.get("drawing_current_files") or []
    assert len(files) == 1
    assert files[0]["key"] == f"orders/{order_id}/drawing_wizard/exports/1_a.png"
    assert sd.get("drawing_status") == "TRANSFERRED"
    # pending 비워짐, 버전 스냅샷 1건 기록.
    assert (sd.get("drawing_wizard") or {}).get("pending") == {}
    assert len((sd.get("drawing_wizard") or {}).get("versions") or []) == 1
    # 담당자 알림 생성.
    assert (
        db_session.query(Notification)
        .filter_by(order_id=order_id, notification_type="DRAWING_TRANSFERRED")
        .count()
        >= 1
    )
    # pending 목록도 빈다.
    pending = client.get(
        f"/api/orders/{order_id}/drawing-wizard/pending"
    ).get_json()["data"]["pending"]
    assert pending == []


def test_transfer_pending_empty_returns_400(client):
    """대기 도면이 없으면 400."""
    user = _login_participant_admin(client)
    order = _order_with_assignee(user.id)
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/transfer-pending",
        json={"note": ""},
    )
    assert resp.status_code == 400
    assert "대기" in resp.get_json()["message"]


def test_transfer_pending_rejects_non_participant(client):
    """비참여자는 403(pending 유무 이전에 권한 게이트)."""
    order = _erp_order()
    order_id = order.id
    _login_non_participant(client)

    resp = client.post(
        f"/api/orders/{order_id}/drawing-wizard/transfer-pending",
        json={},
    )
    assert resp.status_code == 403


def test_transfer_drawing_endpoint_regression(client):
    """공용 함수 추출 후 transfer-drawing 엔드포인트 동작 불변(files/status/history)."""
    user = _login_participant_admin(client)
    order = _order_with_assignee(user.id)
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={
            "note": "1차 전달",
            "mode": "APPEND",
            "files": [
                {"key": f"orders/{order_id}/drawing_gateway/revisions/a.png", "filename": "a.png"}
            ],
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    sd = db_session.query(Order).filter_by(id=order_id).first().structured_data
    assert sd.get("drawing_status") == "TRANSFERRED"
    assert len(sd.get("drawing_current_files") or []) == 1
    hist = sd.get("drawing_transfer_history") or []
    assert hist and hist[-1]["action"] == "TRANSFER"


def test_transfer_drawing_requires_assignee_regression(client):
    """도면 담당자 미지정이면 transfer-drawing 400(추출 후에도 동일 게이트)."""
    _login_participant_admin(client)
    order = _erp_order()  # assignments 없음
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={
            "note": "x",
            "files": [{"key": f"orders/{order_id}/x/a.png", "filename": "a.png"}],
        },
    )
    assert resp.status_code == 400
    assert "담당자" in resp.get_json()["message"]


def test_transfer_drawing_merges_pending_sheet_ids(client, monkeypatch):
    """transfer-drawing + pending_sheet_ids = 저장된 대기 도면을 재업로드 없이 병합 전달 +
    그 시트만 버전 스냅샷 저장 + pending 제거."""
    user = _login_participant_admin(client)
    order = _order_with_assignee(user.id)
    order_id = order.id
    _seed_pending(order)

    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    resp = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={
            "note": "대기 포함",
            "mode": "APPEND",
            "files": [],
            "pending_sheet_ids": ["s-1"],
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["success"] is True

    db_session.expire_all()
    sd = db_session.query(Order).filter_by(id=order_id).first().structured_data
    files = sd.get("drawing_current_files") or []
    assert any(
        f.get("key") == f"orders/{order_id}/drawing_wizard/exports/1_a.png" for f in files
    )
    assert sd.get("drawing_status") == "TRANSFERRED"
    # 해당 시트 pending 제거 + 버전 스냅샷 1건.
    assert (sd.get("drawing_wizard") or {}).get("pending") == {}
    assert len((sd.get("drawing_wizard") or {}).get("versions") or []) == 1
    # pending 목록도 빈다.
    pending = client.get(
        f"/api/orders/{order_id}/drawing-wizard/pending"
    ).get_json()["data"]["pending"]
    assert pending == []


def test_transfer_drawing_merges_pending_and_manual(client, monkeypatch):
    """저장된 대기 도면 + 직접 파일을 한 번의 전달로 함께 반영(단일 히스토리)."""
    user = _login_participant_admin(client)
    order = _order_with_assignee(user.id)
    order_id = order.id
    _seed_pending(order)

    storage = _CapturingStorage()
    monkeypatch.setattr("foms.api.drawing.wizard.get_storage", lambda: storage)

    resp = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={
            "note": "혼합",
            "mode": "APPEND",
            "files": [
                {"key": f"orders/{order_id}/drawing_gateway/revisions/m.png", "filename": "m.png"}
            ],
            "pending_sheet_ids": ["s-1"],
        },
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    sd = db_session.query(Order).filter_by(id=order_id).first().structured_data
    keys = {f.get("key") for f in (sd.get("drawing_current_files") or [])}
    assert f"orders/{order_id}/drawing_wizard/exports/1_a.png" in keys
    assert f"orders/{order_id}/drawing_gateway/revisions/m.png" in keys
    assert (sd.get("drawing_wizard") or {}).get("pending") == {}
    # 전달 이력은 1건(단일 전달로 병합).
    hist = [h for h in (sd.get("drawing_transfer_history") or []) if h.get("action") == "TRANSFER"]
    assert len(hist) == 1
    assert hist[-1]["files_count"] == 2


def test_transfer_drawing_without_pending_unchanged(client):
    """pending_sheet_ids 미전달 시 기존 manual-only 동작 100% 불변(회귀 가드)."""
    user = _login_participant_admin(client)
    order = _order_with_assignee(user.id)
    order_id = order.id
    _seed_pending(order)

    resp = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={
            "note": "수동만",
            "mode": "APPEND",
            "files": [
                {"key": f"orders/{order_id}/drawing_gateway/revisions/a.png", "filename": "a.png"}
            ],
        },
    )
    assert resp.status_code == 200, resp.get_json()

    db_session.expire_all()
    sd = db_session.query(Order).filter_by(id=order_id).first().structured_data
    keys = {f.get("key") for f in (sd.get("drawing_current_files") or [])}
    # 수동 파일만 반영, pending 은 그대로 유지(스냅샷·제거 없음).
    assert keys == {f"orders/{order_id}/drawing_gateway/revisions/a.png"}
    assert set((sd.get("drawing_wizard") or {}).get("pending") or {}) == {"s-1"}
