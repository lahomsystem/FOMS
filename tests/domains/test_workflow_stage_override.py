"""워크플로 단계 강제 변경(역행·건너뛰기) — Spec 2026-07-15."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.services.orders.stage_override import (
    OVERRIDE_BLOCK_MESSAGE,
    classify_stage_move,
    requires_privileged_override,
)


def _login(client, username: str, role: str = "ADMIN") -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=f"{username}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_erp_order(*, status: str = "DRAWING", hist: list | None = None) -> Order:
    hist = hist if hist is not None else [
        {"action": "ERP_ORDER_CHANGED", "note": "치수", "at": "2026-07-15 10:00:00"}
    ]
    order = Order(
        received_date="2026-07-01",
        customer_name="override-고객",
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Mgr",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": status},
            "drawing_transfer_history": hist,
            "drawing": {"status": "IN_PROGRESS"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_classify_and_requires_override_unit():
    assert classify_stage_move("DRAWING", "MEASURE") == "regress"
    assert classify_stage_move("MEASURE", "CONFIRM") == "skip"
    assert classify_stage_move("MEASURE", "DRAWING") == "advance"
    assert classify_stage_move("DRAWING", "DRAWING") == "same"
    assert requires_privileged_override("DRAWING", "MEASURE") is True
    assert requires_privileged_override("MEASURE", "CONFIRM") is True
    assert requires_privileged_override("MEASURE", "DRAWING") is False
    assert requires_privileged_override("DRAWING", "AS_RECEIVED") is False


def test_override_api_manager_regress_preserves_history(client):
    user = _login(client, "ov_mgr", role="MANAGER")
    user_id = user.id
    order = _make_erp_order(status="DRAWING")
    order_id = order.id
    hist_len = len(order.structured_data["drawing_transfer_history"])

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "실측 재방문 — 치수 오류 확인",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["mode"] == "regress"
    assert data["data"]["to"] == "MEASURE"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "MEASURE"
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"
    assert len(saved.structured_data["drawing_transfer_history"]) == hist_len
    assert saved.structured_data["drawing"]["status"] == "IN_PROGRESS"

    ev = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "STAGE_OVERRIDE")
        .all()
    )
    assert len(ev) == 1
    assert ev[0].payload["reason"].startswith("실측 재방문")
    assert ev[0].created_by_user_id == user_id


def test_override_api_staff_forbidden(client):
    _login(client, "ov_staff", role="STAFF")
    order_id = _make_erp_order(status="DRAWING").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "실측 재방문 — 치수 오류 확인",
            "confirm": True,
        },
    )
    assert resp.status_code == 403


def test_override_api_requires_confirm_and_reason(client):
    _login(client, "ov_admin", role="ADMIN")
    order_id = _make_erp_order(status="DRAWING").id

    r1 = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "충분한 사유입니다", "confirm": False},
    )
    assert r1.status_code == 400

    r2 = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "  ", "confirm": True},
    )
    assert r2.status_code == 400

    r3 = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "DRAWING", "reason": "충분한 사유입니다", "confirm": True},
    )
    assert r3.status_code == 400  # same stage


def test_override_api_accepts_short_reason(client):
    """강제 변경 사유는 비어 있지 않으면 글자 수 하한이 없다."""
    _login(client, "ov_short_ok", role="ADMIN")
    order_id = _make_erp_order(status="DRAWING").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={"to_stage": "MEASURE", "reason": "짧음", "confirm": True},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["to"] == "MEASURE"


def test_override_api_skip_forward(client):
    _login(client, "ov_skip", role="ADMIN")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "CONFIRM",
            "reason": "실측 생략 — 고객 셀프 치수 확정",
            "confirm": True,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["mode"] == "skip"


def test_update_order_status_blocks_regress(client):
    _login(client, "ov_block", role="ADMIN")
    order_id = _make_erp_order(status="DRAWING").id
    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "MEASURE"},
    )
    assert resp.status_code == 403
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")


def test_update_order_status_allows_adjacent_advance(client):
    _login(client, "ov_adv", role="STAFF")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "DRAWING"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_bulk_blocks_only_override_required(client):
    _login(client, "ov_bulk2", role="MANAGER")
    regress_id = _make_erp_order(status="DRAWING").id
    advance_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/bulk_update_order_status",
        json={"order_ids": [regress_id, advance_id], "status": "MEASURE"},
    )
    # regress: DRAWING→MEASURE blocked; same MEASURE→MEASURE updated
    data = resp.get_json()
    assert regress_id in data.get("blocked_override_required", [])
    assert data["updated"] >= 1


def test_update_order_field_status_blocks_skip(client):
    _login(client, "ov_field", role="STAFF")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field": "status", "value": "CONFIRM"},
    )
    assert resp.status_code == 403


def test_update_order_status_blocks_skip(client):
    """인접이 아닌 전진(MEASURE→CONFIRM)도 status API 403."""
    _login(client, "ov_skip_block", role="ADMIN")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/update_order_status",
        json={"order_id": order_id, "status": "CONFIRM"},
    )
    assert resp.status_code == 403
    assert OVERRIDE_BLOCK_MESSAGE in (resp.get_json() or {}).get("message", "")


def test_override_rejects_as_and_deleted_targets(client):
    """목표 단계 AS_*/DELETED 는 override 타깃 불가(기존 AS/삭제 API 유지)."""
    _login(client, "ov_as_tgt", role="ADMIN")
    order_id = _make_erp_order(status="DRAWING").id
    for bad in ("AS_RECEIVED", "AS_COMPLETED", "AS", "DELETED"):
        resp = client.post(
            f"/api/orders/{order_id}/workflow/stage-override",
            json={
                "to_stage": bad,
                "reason": "잘못된 목표 단계 검증용 사유",
                "confirm": True,
            },
        )
        assert resp.status_code == 400, bad
        assert resp.get_json()["success"] is False


def test_override_from_as_to_main_allowed(client):
    """정책(감리#3): AS→메인 파이프라인 강제 복귀는 운영상 허용(jump)."""
    _login(client, "ov_as_from", role="MANAGER")
    order = _make_erp_order(status="AS_RECEIVED")
    order_id = order.id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "AS 오접수 정정 — 실측 단계로 복귀",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["to"] == "MEASURE"
    assert data["mode"] == "jump"


def test_override_does_not_mutate_quests(client):
    """강제 변경은 quest/_handle_stage_transition 부수효과 없음 — quests JSON 불변."""
    from sqlalchemy.orm.attributes import flag_modified

    _login(client, "ov_quest", role="ADMIN")
    order = _make_erp_order(status="DRAWING")
    quests = {"DRAWING": {"items": [{"id": "q1", "status": "pending"}]}}
    sd = dict(order.structured_data or {})
    sd["quests"] = quests
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    order_id = order.id

    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "퀘스트 불변 검증 — 도면→실측",
            "confirm": True,
        },
    )
    assert resp.status_code == 200
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data.get("quests") == quests
    # STAGE_CHANGED(quest 경로) 없이 STAGE_OVERRIDE 만
    types = [
        e.event_type
        for e in db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).all()
    ]
    assert "STAGE_OVERRIDE" in types
    assert "STAGE_CHANGED" not in types


def test_bulk_override_skip_two_orders(client):
    """선택 2건 건너뛰기 → 일괄 STAGE_OVERRIDE, 사유 공유."""
    _login(client, "ov_bulk_ok", role="MANAGER")
    first_id = _make_erp_order(status="MEASURE").id
    second_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [first_id, second_id],
            "to_stage": "CONFIRM",
            "reason": "실측 생략 — 셀프 치수 확정 일괄",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["updated"] == 2
    assert data["to"] == "CONFIRM"
    db_session.expire_all()
    assert db_session.get(Order, first_id).status == "CONFIRM"
    assert db_session.get(Order, second_id).status == "CONFIRM"
    events = (
        db_session.query(OrderEvent)
        .filter(
            OrderEvent.event_type == "STAGE_OVERRIDE",
            OrderEvent.order_id.in_([first_id, second_id]),
        )
        .all()
    )
    assert len(events) == 2


def test_bulk_override_staff_forbidden(client):
    """STAFF 일괄 강제 변경 → 403."""
    _login(client, "ov_bulk_staff", role="STAFF")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [order_id],
            "to_stage": "CONFIRM",
            "reason": "충분한 사유입니다",
            "confirm": True,
        },
    )
    assert resp.status_code == 403
    db_session.expire_all()
    assert db_session.get(Order, order_id).status == "MEASURE"


def test_bulk_override_skips_same_updates_rest(client):
    """동일 단계는 건너뛰고 나머지 건만 강제 변경."""
    _login(client, "ov_bulk_same", role="ADMIN")
    same_id = _make_erp_order(status="CONFIRM").id
    skip_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [same_id, skip_id],
            "to_stage": "CONFIRM",
            "reason": "혼합 선택 일괄 강제 변경",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["updated"] == 1
    assert same_id in data["skipped_same"]
    db_session.expire_all()
    assert db_session.get(Order, same_id).status == "CONFIRM"
    assert db_session.get(Order, skip_id).status == "CONFIRM"


def test_bulk_override_requires_confirm(client):
    """일괄 강제 변경도 confirm true 필수."""
    _login(client, "ov_bulk_c", role="ADMIN")
    order_id = _make_erp_order(status="MEASURE").id
    resp = client.post(
        "/api/orders/workflow/stage-override/bulk",
        json={
            "order_ids": [order_id],
            "to_stage": "CONFIRM",
            "reason": "충분한 사유입니다",
            "confirm": False,
        },
    )
    assert resp.status_code == 400


def test_override_completed_to_past_manager(client):
    """COMPLETED → 과거 단계: MANAGER+사유 허용(스펙 B)."""
    _login(client, "ov_done", role="MANAGER")
    order_id = _make_erp_order(status="COMPLETED").id
    resp = client.post(
        f"/api/orders/{order_id}/workflow/stage-override",
        json={
            "to_stage": "MEASURE",
            "reason": "완료 오처리 복구 — 실측 재진행",
            "confirm": True,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["mode"] == "regress"
    assert resp.get_json()["data"]["to"] == "MEASURE"


def test_js_contract_defer_and_api_path():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    assert "__FOMS_STAGE_OVERRIDE_BOUND" in js
    assert "/workflow/stage-override" in js
    assert "/workflow/stage-override/bulk" in js
    assert "needsOverride" in js
    assert "interceptBulkStatusChange" in js
    assert "hide.bs.modal" in js
    assert "settlePendingCancel" in js or "onCancel" in js
    assert "confirmForceMove" in js
    assert "noteCurrentStage" in js
    assert "사유를 입력하세요." in js
    assert "reason.length < 8" not in js
    assert "8자 이상" not in js

    dash = (root / "static/js/orders/dashboard/erp-dashboard-detail-dom.js").read_text(
        encoding="utf-8"
    )
    assert "interceptBulkStatusChange" in dash

    erp_js = (root / "templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    assert "erp-stage-override.js" in erp_js
    assert "defer" in erp_js
    assert "erp_stage_override_modal.html" in erp_js


def test_guard_base_is_saved_server_stage_not_form_preview():
    """미저장 폼 미리보기가 아니라 **저장된** 단계를 base 로 override 를 건다.

    회귀: 새 주문(서버 RECEIVED)에서 폼 단계를 실측으로 바꿔 본 뒤 다시 주문접수를
    고르면, 클라가 저장값(RECEIVED)이 아닌 미리보기(MEASURE)를 base 로 삼아
    RECEIVED→RECEIVED override 를 보냈고 서버가 ``same`` 으로 400 을 냈다.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    assert "noteServerStage" in js
    assert "var _serverStage" in js
    # change 가드가 저장값을 base 로 쓰고, 저장값 복귀는 서버 호출 없이 통과시킨다.
    assert "var saved = String(_serverStage || '').trim();" in js
    assert "if (saved && next === saved) {" in js

    shared = (root / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    # GET /structured 재조회 + 저장 성공 두 지점에서 저장 단계를 갱신한다.
    assert shared.count("FOMS_STAGE_OVERRIDE.noteServerStage(") == 2


def test_override_error_box_is_exempt_from_alert_autodismiss():
    """실패 메시지 상자가 전역 5초 .alert 자동닫힘에 지워지면 안 된다(무반응 오인)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    html = (
        root / "templates/orders/partials/erp_stage_override_modal.html"
    ).read_text(encoding="utf-8")
    marker = 'id="erp-stage-override-error"'
    assert marker in html
    block = html[html.index(marker) - 200 : html.index(marker) + 200]
    assert "data-foms-no-autodismiss" in block
