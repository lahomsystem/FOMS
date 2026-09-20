"""실측 보드 [완료] 버튼의 경로 일원화 계약 (C-B1·C-B2, 2026-09-20).

화면 잣대 == 서버 잣대를 고정한다.

* 메인 파이프라인 ERP 주문의 완료는 ``POST /api/orders/<id>/cs/complete`` 한 길뿐이다.
* 화면이 켜 주는(enabled) 버튼은 서버가 200 을 준다 — 거부당할 버튼 0.
* 화면이 끄는(disabled) 버튼은 사유와 함께 갈 곳을 준다 — 막다른 길 0.
* 다른 축(비ERP·AS 계열)은 옛 경로 그대로다 — 오탐 0.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from foms.services.orders.complete_path_policy import (
    build_complete_ctas,
    complete_block_reason,
    rejects_completed_field_write,
)


def _make_user(username: str, *, role: str = "STAFF", team: str | None = "CS") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(stage_code: str, *, status: str | None = None, is_erp: bool = True,
                structured_data: dict | None = None) -> Order:
    sd: dict = {"workflow": {"stage": stage_code}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage_code
    order = Order(received_date="2026-09-01", customer_name="완료 고객", phone="010-7777-8888",
                  address="Seoul", product="붙박이장", status=status or stage_code,
                  manager_name="Bob", is_erp_order=is_erp,
                  structured_data=sd if is_erp else None,
                  erp_stage_code=stage_code if is_erp else None)
    db_session.add(order)
    db_session.commit()
    return order


def _cs_quest(approved: bool) -> dict:
    return {"quests": [{"stage": "CS", "status": "OPEN", "required_approvals": ["CS"],
                        "team_approvals": {"CS": {"approved": approved, "approved_by": None,
                                                  "approved_at": None}}}]}


def _cta(order: Order, user: User) -> dict:
    return build_complete_ctas([order], user)[order.id]


# --------------------------------------------------------------------------- #
# 1. CS 단계 주문은 정식 경로 버튼을 켠다
# --------------------------------------------------------------------------- #
def test_cs_stage_order_gets_enabled_cs_complete_button(app):
    """CS 단계 ERP 주문 → endpoint 가 cs_complete 이고 버튼이 켜진다."""
    user = _make_user("cta_cs_ok")
    order = _make_order("CS", structured_data=_cs_quest(approved=True))

    cta = _cta(order, user)
    assert cta["visible"] is True
    assert cta["enabled"] is True
    assert cta["endpoint"] == "cs_complete"
    assert cta["blocked_reason"] == ""
    assert complete_block_reason(order, user) is None


# --------------------------------------------------------------------------- #
# 2. CS 필수 승인이 남으면 사유 + 갈 곳
# --------------------------------------------------------------------------- #
def test_cs_quest_incomplete_blocks_with_reason_and_link(app):
    """CS quest 미승인 → 꺼진 버튼 + 남은 팀 문구 + 승인 화면 링크(막다른 길 0)."""
    user = _make_user("cta_cs_quest")
    order = _make_order("CS", structured_data=_cs_quest(approved=False))

    cta = _cta(order, user)
    assert cta["visible"] is True
    assert cta["enabled"] is False
    assert "CS" in cta["blocked_reason"]
    assert "승인" in cta["blocked_reason"]
    assert cta["blocked_href"], "승인하러 갈 링크가 비어 있으면 막다른 길이다"
    assert f"focus_order={order.id}" in cta["blocked_href"]


# --------------------------------------------------------------------------- #
# 3. 아직 CS 전이면 단계 이름을 말한다
# --------------------------------------------------------------------------- #
def test_construction_stage_order_is_blocked_and_says_construction(app):
    """시공 단계 주문 → 꺼진 버튼이고 문구가 '시공' 단계를 말한다."""
    user = _make_user("cta_const")
    order = _make_order("CONSTRUCTION", status="SCHEDULED")

    cta = _cta(order, user)
    assert cta["enabled"] is False
    assert "시공" in cta["blocked_reason"]
    assert cta["blocked_href"] == ""


# --------------------------------------------------------------------------- #
# 4. 대조군 — 다른 축은 건드리지 않는다
# --------------------------------------------------------------------------- #
def test_non_erp_order_keeps_legacy_field_update_path(app):
    """비ERP 레거시 주문 → 옛 field_update 경로 그대로 켜진 버튼."""
    user = _make_user("cta_legacy")
    order = _make_order("SCHEDULED", status="SCHEDULED", is_erp=False)

    cta = _cta(order, user)
    assert cta["visible"] is True
    assert cta["enabled"] is True
    assert cta["endpoint"] == "field_update"
    assert rejects_completed_field_write(order, "COMPLETED") is False


def test_as_received_order_hides_complete_button(app):
    """AS 접수 주문 → 완료 버튼 자체를 그리지 않는다(AS 는 AS 컨트롤 소관)."""
    user = _make_user("cta_as")
    order = _make_order("CS", status="AS_RECEIVED")

    assert _cta(order, user)["visible"] is False


def test_other_axis_writes_are_not_rejected(app):
    """보드/AS 축 값 쓰기는 거부 술어에 들어오지도 않는다(오탐 0)."""
    order = _make_order("CONSTRUCTION", status="SCHEDULED")
    for value in ("SCHEDULED", "MEASURED", "SHIPPED_PENDING", "AS_RECEIVED", "AS_COMPLETED"):
        assert rejects_completed_field_write(order, value) is False, value
    assert rejects_completed_field_write(order, "COMPLETED") is True


# --------------------------------------------------------------------------- #
# 5. 화면 잣대 == 서버 잣대
# --------------------------------------------------------------------------- #
def test_enabled_button_actually_completes_on_server(client):
    """켜진 버튼이 가리키는 그 요청이 실제로 200 이고 주문이 완료된다."""
    user = _make_user("cta_e2e_ok")
    _login(client, user)
    order = _make_order("CS", structured_data=_cs_quest(approved=True))
    oid = order.id
    assert _cta(order, user)["enabled"] is True

    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_stage_code == "COMPLETED"


def test_disabled_button_request_is_rejected_with_same_code(client):
    """꺼진 버튼의 주문에 옛 경로로 밀어 넣으면 409 USE_CS_COMPLETE 로 막힌다."""
    user = _make_user("cta_e2e_block")
    _login(client, user)
    order = _make_order("CONSTRUCTION", status="SCHEDULED")
    oid = order.id
    assert _cta(order, user)["enabled"] is False

    resp = client.post("/api/update_order_field",
                       json={"order_id": oid, "field": "status", "value": "COMPLETED"})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "USE_CS_COMPLETE"
    db_session.expire_all()
    assert db_session.get(Order, oid).status == "SCHEDULED"


# --------------------------------------------------------------------------- #
# 6. 완료로 가는 옛 경로 세 곳이 모두 같은 답을 낸다
# --------------------------------------------------------------------------- #
def _cs_blocked_order() -> Order:
    """CS 단계이지만 CS 필수 승인이 남은 주문(세 라우트가 모두 막아야 하는 모집단)."""
    return _make_order("CS", structured_data=_cs_quest(approved=False))


def test_세_라우트_모두_CS_승인_전_완료를_거부한다(client):
    """field_update·update_order_status·bulk_update_order_status 가 같은 코드로 막는다."""
    user = _make_user("cta_three_routes")
    _login(client, user)
    oid = _cs_blocked_order().id

    single_field = client.post("/api/update_order_field",
                               json={"order_id": oid, "field": "status", "value": "COMPLETED"})
    assert single_field.status_code == 409, single_field.get_data(as_text=True)
    assert single_field.get_json()["code"] == "USE_CS_COMPLETE"
    assert "승인" in single_field.get_json()["message"]

    single_status = client.post("/api/update_order_status",
                                json={"order_id": oid, "status": "COMPLETED"})
    assert single_status.status_code == 409, single_status.get_data(as_text=True)
    body = single_status.get_json()
    assert body["code"] == "USE_CS_COMPLETE"
    assert body["stage"] == "CS"
    assert "승인" in body["message"]

    bulk = client.post("/api/bulk_update_order_status",
                       json={"order_ids": [oid], "status": "COMPLETED"})
    assert bulk.status_code == 200, bulk.get_data(as_text=True)
    bulk_body = bulk.get_json()
    assert bulk_body["blocked_use_cs_complete"] == [oid]
    assert bulk_body["updated"] == 0

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.status != "COMPLETED"
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "CS"


def test_대조군_같은_주문의_다른_축_값은_세_라우트에서_그대로_저장된다(client):
    """음성 대조군 — COMPLETED 가 아닌 값은 거부 술어에 들어오지도 않는다(오탐 0)."""
    user = _make_user("cta_three_routes_control", role="ADMIN")
    _login(client, user)
    oid = _cs_blocked_order().id

    field_res = client.post("/api/update_order_field",
                            json={"order_id": oid, "field": "status", "value": "SCHEDULED"})
    assert field_res.status_code == 200, field_res.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, oid).status == "SCHEDULED"

    status_res = client.post("/api/update_order_status",
                             json={"order_id": oid, "status": "SHIPPED_PENDING"})
    assert status_res.status_code == 200, status_res.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, oid).status == "SHIPPED_PENDING"

    bulk_res = client.post("/api/bulk_update_order_status",
                           json={"order_ids": [oid], "status": "SCHEDULED"})
    assert bulk_res.status_code == 200, bulk_res.get_data(as_text=True)
    assert bulk_res.get_json()["updated"] == 1
    assert bulk_res.get_json()["blocked_use_cs_complete"] == []


# --------------------------------------------------------------------------- #
# 7. 평면 미러가 뒤처진 주문 — 화면 CTA 와 서버가 같은 축을 본다
# --------------------------------------------------------------------------- #
def test_평면_미러가_뒤처져도_화면과_서버가_같은_답을_낸다(client):
    """erp_stage_code 는 시공인데 canonical 축은 CS 인 주문 → 화면도 서버도 완료 가능."""
    user = _make_user("cta_axis_drift")
    _login(client, user)
    order = _make_order("CS", structured_data=_cs_quest(approved=True))
    order.erp_stage_code = "CONSTRUCTION"  # 평면 미러만 뒤처진 상태를 만든다
    db_session.commit()
    oid = order.id

    assert _cta(order, user)["enabled"] is True
    resp = client.post(f"/api/orders/{oid}/cs/complete", json={})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, oid).erp_stage_code == "COMPLETED"


# --------------------------------------------------------------------------- #
# 8. 막다른 길 0 — 보류·AS 도 갈 곳을 준다
# --------------------------------------------------------------------------- #
def test_보류_주문은_주문_상세로_가는_길을_준다(app):
    """보류 차단 → 보류를 풀 수 있는 주문 상세 딥링크."""
    user = _make_user("cta_hold")
    sd = {**_cs_quest(approved=True), "workflow": {"stage": "CS", "hold": {"active": True}}}
    order = _make_order("CS", structured_data=sd)

    code, message, href = complete_block_reason(order, user)
    assert code == "HOLD_ACTIVE"
    assert "보류" in message
    assert f"focus_order={order.id}" in href


def test_AS_진행_주문은_AS_화면으로_가는_길을_준다(app):
    """AS 차단 → AS 대시보드 딥링크."""
    user = _make_user("cta_as_open")
    sd = {**_cs_quest(approved=True),
          "as_lifecycle": {"current_cycle_id": "c1", "cycles": [{"cycle_id": "c1"}]}}
    order = _make_order("CS", structured_data=sd)

    code, message, href = complete_block_reason(order, user)
    assert code == "AS_ACTIVE"
    assert "AS" in message
    assert "/erp/as" in href


# --------------------------------------------------------------------------- #
# 9. 막힌 버튼은 사유를 눈에 보이는 글자로 낸다(태블릿에서 title 은 안 뜬다)
# --------------------------------------------------------------------------- #
def _render_complete_control(cta) -> str:
    import app as app_module

    tmpl = app_module.app.jinja_env.get_template("partials/shared/status_select_options.html")
    return str(tmpl.module.complete_order_control(4552, "CS", cta))


def test_막힌_완료_버튼은_사유를_텍스트_노드로_보여_준다():
    """title 뿐 아니라 실제 글자로도 사유가 나오고, 갈 곳 링크 문구는 사유에 맞는다."""
    cta = {
        "visible": True, "enabled": False, "endpoint": "cs_complete", "label": "완료",
        "confirm": "", "blocked_reason": "CS 필수 승인이 남아 완료할 수 없습니다.",
        "blocked_href": "/erp/dashboard?focus_order=4552&open_quest=true",
        "blocked_link_label": "승인하러 가기",
    }
    html = _render_complete_control(cta)
    assert 'class="foms-complete-blocked-reason"' in html
    assert "CS 필수 승인이 남아 완료할 수 없습니다." in html.split('class="foms-complete-blocked-reason"')[1]
    assert "승인하러 가기" in html
    assert "style=" not in html  # 인라인 style 금지


def test_보류_차단은_보류_문구의_링크를_단다():
    """링크 문구는 서버가 준 사유별 문구를 그대로 쓴다(승인 화면이 아닌 곳으로 보낸다)."""
    cta = {
        "visible": True, "enabled": False, "endpoint": "cs_complete", "label": "완료",
        "confirm": "", "blocked_reason": "보류 중인 주문은 완료할 수 없습니다.",
        "blocked_href": "/erp/dashboard?focus_order=4552",
        "blocked_link_label": "보류 풀러 가기",
    }
    html = _render_complete_control(cta)
    assert "보류 풀러 가기" in html
    assert "승인하러 가기" not in html


def test_태블릿_보드_실화면에_사유와_갈_곳이_함께_렌더된다(client):
    """지방(태블릿) 대시보드 실제 응답에 사유 글자와 승인 링크가 같이 나온다.

    매크로 단위가 아니라 실화면으로 확인한다 — 호출부가 cta 를 안 넘기면 매크로만
    고쳐도 화면은 그대로이기 때문이다.
    """
    user = _make_user("cta_regional", role="ADMIN")
    _login(client, user)
    order = Order(
        received_date="2026-09-01", customer_name="지방 완료 고객", phone="010-7777-8888",
        address="강원", product="붙박이장", status="SCHEDULED", manager_name="Bob",
        is_erp_order=True, is_regional=True, erp_stage_code="CS",
        structured_data={"workflow": {"stage": "CS"}, **_cs_quest(approved=False)},
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    body = client.get("/regional_dashboard").get_data(as_text=True)
    assert "지방 완료 고객" in body
    assert '<span class="foms-complete-blocked-reason">' in body
    assert "CS 필수 승인이 남아 완료할 수 없습니다" in body
    assert "js-complete-blocked-link" in body
    assert f"focus_order={order_id}" in body
