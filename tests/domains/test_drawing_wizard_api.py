"""도면 마법사 API 계약 테스트 (GET/PUT/asset).

기존 도면 워크벤치/structured PUT 테스트의 픽스처 관행을 따른다:
``db_session`` 직접 생성 + ``client.session_transaction()`` 로그인.
"""

import io
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


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
