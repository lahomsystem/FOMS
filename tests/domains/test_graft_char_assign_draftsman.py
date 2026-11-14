"""특성 시험 — 도면 담당 맡기기 ``POST /api/orders/<id>/assign-draftsman`` 의 지금 행동 (T13 · D206).

T14 가 처리기 본체(``foms/api/drawing/erp_orders_draftsman.py`` ``api_order_assign_draftsman``)를 함수로
떼어 낸다. 이 파일을 한 글자도 고치지 않은 채 초록이어야 행동이 같다는 증거다. 장면마다 답 코드 ·
답 값 · 주문 자국(일 기록 · 감사 · 원장 · 알림 · 바깥 일 · 담당 줄 · ``structured_data`` · 납작 칸 ·
``mutation_version``)의 앞뒤 차이 전체를 글자 그대로 견준다(``tests/support/graft_char.py``).

이상해 보여도 지금 행동이면 그대로 못박았다:
* 권한 정본 표 ``order_assignments`` 는 건드리지 않는다 — JSONB 네 곳(담당 번호 · 담당 목록 · 출고 칸 ·
  단계 이력)만 바뀐다. ``mutation_version`` 도 오르지 않는다. 알림 · 바깥 일도 없다.
* 승격 전 초안 · 지운 주문도 막지 않고 맡긴다.
* 역할을 보지 않는다 — 도면팀이면 조회 전용(VIEWER)도 맡긴다(시험 레인). 정책 가드를 켜면 처리기 앞에서 403.
* JSON 이 아닌 본문은 500 이고, 처리기의 글 대신 공용 오류 꼴이 나간다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.api.drawing import erp_orders_draftsman as draftsman_api
from foms.services.orders.drawing_assignee_write import apply_drawing_assignees
from models import OrderAssignment
from tests.support import graft_char as gc

SD = ("assignments", "drawing_assignees", "shipment", "workflow")
FLAT = ("status", "erp_stage_code", "manager_name", "structured_updated_at", "deleted_at")
NO_RIGHT = "도면 담당자 지정 권한이 없습니다. (관리자/도면팀/지정 도면담당자만 가능)"


@pytest.fixture
def out(monkeypatch):
    """바깥 보내기를 가짜로 바꾼다 — 이 길은 아무것도 밖으로 보내지 않아야 한다."""
    return gc.install_fakes(monkeypatch)


def _order(stage: str = "DRAWING", extra: dict | None = None, **cols) -> int:
    """ERP 주문 1건(지어낸 영업 이름)."""
    sd = {"workflow": {"stage": stage}, "parties": {"manager": {"name": "특성 영업"}}}
    sd.update(extra or {})
    return gc.make_order(sd, status=cols.pop("status", stage), erp_stage_code=stage, **cols)


def _assign(client, order_id: int, body=None, *, raw: str | None = None):
    """담당 맡기기를 부르고 (답, 앞뒤 차이, 새 줄)을 돌려준다."""
    before = gc.snapshot(order_id, sd_paths=SD, flat=FLAT)
    url = f"/api/orders/{order_id}/assign-draftsman"
    resp = (client.post(url, data=raw, content_type="text/plain") if raw is not None
            else client.post(url, json=body))
    after = gc.snapshot(order_id, sd_paths=SD, flat=FLAT)
    return resp, gc.delta(before, after), gc.new_rows(before, after)


def _assigned(users: list, actor_name: str, stage: str = "DRAWING", before_ids=None, before_people=None) -> dict:
    """맡기기 한 번이 남기는 자국 전체(대조군도 이 꼴과 견준다)."""
    names = ", ".join(u.name for u in users)
    after_people = sorted(({"id": u.id, "name": u.name, "team": "DRAWING"} for u in users), key=lambda x: x["id"])
    return {
        "events": {"DRAWING_ASSIGNEE_SET": 1}, "audit": {"DRAFTSMAN_ASSIGNED": 1},
        "sd": {
            "assignments": (gc.ABSENT if before_ids is None else {"drawing_assignee_user_ids": before_ids},
                            {"drawing_assignee_user_ids": [u.id for u in users]}),
            "drawing_assignees": (gc.ABSENT if before_people is None else before_people, after_people),
            "shipment": (gc.ABSENT, {"drawing_managers": sorted(u.name for u in users)}),
            "workflow": ({"stage": stage}, {"stage": stage, "history": [
                {"stage": stage, "updated_at": gc.TS, "updated_by": actor_name, "note": f"도면 담당자 지정: {names}"}]}),
        },
    }


def _payload(users: list, *, before="None", before_ids=(), override=False, reason=None) -> dict:
    """DRAWING_ASSIGNEE_SET 일 기록 내용."""
    return {
        "domain": "DRAWING_DOMAIN", "action": "DRAWING_ASSIGNEE_SET", "target": "assignments.drawing_assignee_user_ids",
        "before": before, "after": ", ".join(u.name for u in users), "before_ids": list(before_ids),
        "after_ids": [u.id for u in users], "assignee_names": [u.name for u in users],
        "assignee_user_ids": [u.id for u in users], "change_method": "API", "source_screen": "erp_drawing_dashboard",
        "reason": "도면 담당자 지정", "is_override": override, "override_reason": reason}


def _ok(users: list) -> dict:
    return {"success": True, "message": f"도면 담당자가 지정되었습니다: {', '.join(u.name for u in users)}"}


def _run_admin_one(client):
    admin = gc.make_user("da-admin", role="ADMIN", team="CS")
    drawer = gc.make_user("da-draw1", team="DRAWING")
    gc.login_as(client, admin)
    oid = _order()
    resp, d, rows = _assign(client, oid, {"user_ids": [drawer.id]})
    return admin, drawer, oid, resp, d, rows


def test_관리자가_한_명을_맡기면_JSONB_네_곳과_일_기록_감사만_남고_밖으로는_안_보낸다(client, out):
    admin, drawer, oid, resp, d, rows = _run_admin_one(client)
    assert (resp.status_code, resp.get_json()) == (200, _ok([drawer]))
    assert d == _assigned([drawer], "da-admin 직원")
    assert rows == {
        "events": [("DRAWING_ASSIGNEE_SET", _payload([drawer]))],
        "audit": [("DRAFTSMAN_ASSIGNED", "order", oid, f"주문 #{oid} (특성시험 손님) — 도면 담당자 배정: 1명 배정",
                   {"assignee_user_ids": [drawer.id], "bulk": False,
                    "customer_name": "특성시험 손님", "order_type": "주문"})],
        "outbox": []}
    assert (out.summary(), out.cache) == ({}, [("families", ("drawing", "orders"))])


def test_여러_명으로_바꾸면_앞_담당을_일_기록에_남기고_보낸_순서대로_적는다(client, out):
    gc.login_as(client, gc.make_user("da-admin", role="ADMIN", team="CS"))
    d1, d2 = gc.make_user("da-draw1", team="DRAWING"), gc.make_user("da-draw2", team="DRAWING")
    before_people = [{"id": d1.id, "name": d1.name, "team": "DRAWING"}]
    oid = _order(extra={"assignments": {"drawing_assignee_user_ids": [d1.id]}, "drawing_assignees": before_people})
    resp, d, rows = _assign(client, oid, {"user_ids": [d2.id, d1.id]})
    assert (resp.status_code, resp.get_json()) == (200, _ok([d1, d2]))
    expected = _assigned([d1, d2], "da-admin 직원", before_ids=[d1.id], before_people=before_people)
    expected["sd"]["assignments"] = ({"drawing_assignee_user_ids": [d1.id]}, {"drawing_assignee_user_ids": [d2.id, d1.id]})
    assert d == expected
    payload = _payload([d1, d2], before=d1.name, before_ids=[d1.id])
    payload.update(after_ids=[d2.id, d1.id], assignee_user_ids=[d2.id, d1.id])
    assert rows["events"] == [("DRAWING_ASSIGNEE_SET", payload)]
    assert rows["audit"][0][3] == f"주문 #{oid} (특성시험 손님) — 도면 담당자 배정: 2명 배정"


@pytest.mark.parametrize("who", ["drawing_staff", "current_assignee", "viewer_in_drawing"])
def test_도면팀_지금_담당_도면팀_조회전용은_맡길_수_있다(client, out, who):
    drawer = gc.make_user("da-draw1", team="DRAWING")
    actor = {"drawing_staff": lambda: gc.make_user("da-draw2", team="DRAWING"),
             "current_assignee": lambda: gc.make_user("da-sales", team="SALES"),
             "viewer_in_drawing": lambda: gc.make_user("da-viewer", role="VIEWER", team="DRAWING")}[who]()
    extra = {"assignments": {"drawing_assignee_user_ids": [actor.id]}} if who == "current_assignee" else None
    gc.login_as(client, actor)
    resp, d, _ = _assign(client, _order(extra=extra), {"user_ids": [drawer.id]})
    assert (resp.status_code, resp.get_json()) == (200, _ok([drawer]))
    expected = _assigned([drawer], actor.name, before_ids=[actor.id] if extra else None)
    assert d == expected


def test_매니저_긴급_오버라이드와_사유가_있으면_맡기고_일_기록에_남긴다(client, out):
    drawer = gc.make_user("da-draw1", team="DRAWING")
    mgr = gc.make_user("da-mgr", role="MANAGER", team="SALES")
    gc.login_as(client, mgr)
    resp, d, rows = _assign(client, _order(), {"user_ids": [drawer.id], "emergency_override": True,
                                               "override_reason": "급함"})
    assert (resp.status_code, resp.get_json()) == (200, _ok([drawer]))
    assert d == _assigned([drawer], "da-mgr 직원")
    assert rows["events"] == [("DRAWING_ASSIGNEE_SET", _payload([drawer], override=True, reason="급함"))]


@pytest.mark.parametrize("role, team, body, message", [
    ("STAFF", "SALES", {}, NO_RIGHT),
    ("MANAGER", "SALES", {}, NO_RIGHT + " (긴급 오버라이드가 필요합니다.)"),
    ("MANAGER", "SALES", {"emergency_override": True}, NO_RIGHT + " (긴급 오버라이드가 필요합니다.)"),
    ("STAFF", "SALES", {"emergency_override": True, "override_reason": "급함"}, NO_RIGHT),
])
def test_권한이_없으면_403과_그_글(client, out, role, team, body, message):
    drawer = gc.make_user("da-draw1", team="DRAWING")
    gc.login_as(client, gc.make_user("da-x", role=role, team=team))
    resp, d, _ = _assign(client, _order(), {"user_ids": [drawer.id], **body})
    assert (resp.status_code, resp.get_json()) == (403, {"success": False, "message": message})
    assert d == {}


@pytest.mark.parametrize("case, status, message", [
    ("empty", 400, "담당자를 선택해주세요."),
    ("not_drawing", 400, "도면 담당자는 도면팀 소속만 지정할 수 있습니다. (도면팀이 아닌 사용자: da-sales 직원)"),
    ("inactive", 400, "일부 사용자를 찾을 수 없거나 비활성 계정입니다."),
    ("unknown", 400, "일부 사용자를 찾을 수 없거나 비활성 계정입니다."),
    ("no_order", 404, "주문을 찾을 수 없습니다."),
])
def test_고를_사람이_틀리거나_주문이_없으면_거부하고_아무것도_안_남긴다(client, out, case, status, message):
    gc.login_as(client, gc.make_user("da-admin", role="ADMIN", team="CS"))
    drawer = gc.make_user("da-draw1", team="DRAWING")
    ids = {"empty": [], "not_drawing": [gc.make_user("da-sales", team="SALES").id],
           "inactive": [gc.make_user("da-off", team="DRAWING", active=False).id],
           "unknown": [drawer.id, 4242], "no_order": [drawer.id]}[case]
    oid = 4242 if case == "no_order" else _order()
    resp, d, _ = _assign(client, oid, {"user_ids": ids})
    assert (resp.status_code, resp.get_json()) == (status, {"success": False, "message": message})
    assert d == {}


def test_JSON이_아닌_본문은_500이고_공용_오류_꼴이_나간다(client, out):
    gc.login_as(client, gc.make_user("da-admin", role="ADMIN", team="CS"))
    resp, d, _ = _assign(client, _order(), raw="user_ids=1")
    body = resp.get_json()
    text = "요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    assert resp.status_code == 500 and sorted(body) == ["error", "message", "success"]
    assert (body["success"], body["message"]) == (False, text)
    assert sorted(body["error"]) == ["code", "message", "request_id"] and body["error"]["code"] == "INTERNAL_ERROR"
    assert d == {}


@pytest.mark.parametrize("kind", ["draft", "deleted"])
def test_승격_전_초안과_지운_주문도_막지_않고_맡긴다(client, out, kind):
    gc.login_as(client, gc.make_user("da-admin", role="ADMIN", team="CS"))
    drawer = gc.make_user("da-draw1", team="DRAWING")
    if kind == "draft":
        oid = _order("RECEIVED", extra={"meta": {"draft": True}}, status="DRAFT")
    else:
        oid = _order(deleted_at="2031-01-03 00:00:00")
    resp, d, _ = _assign(client, oid, {"user_ids": [drawer.id]})
    assert (resp.status_code, resp.get_json()) == (200, _ok([drawer]))
    assert d == _assigned([drawer], "da-admin 직원", stage="RECEIVED" if kind == "draft" else "DRAWING")


def test_권한_정본_담당_줄은_그대로_두고_JSONB_만_바꾼다(client, out):
    admin = gc.make_user("da-admin", role="ADMIN", team="CS")
    d1, d2 = gc.make_user("da-draw1", team="DRAWING"), gc.make_user("da-draw2", team="DRAWING")
    oid = _order()
    db_session.add(OrderAssignment(order_id=oid, domain="DRAWING", user_id=d1.id, source="TEAM_REPLACE",
                                   active=True, assigned_by_user_id=admin.id))
    db_session.commit()
    gc.login_as(client, admin)
    resp, d, _ = _assign(client, oid, {"user_ids": [d2.id]})
    assert resp.status_code == 200
    assert d == _assigned([d2], "da-admin 직원")
    assert gc.snapshot(oid)["assignments"] == [("DRAWING", d1.id, True)]


def test_로그인_안_하면_로그인_화면으로_돌려보낸다(client, out):
    oid = _order()
    resp, d, _ = _assign(client, oid, {"user_ids": [1]})
    assert (resp.status_code, resp.headers["Location"]) == (302, f"/login?next=/api/orders/{oid}/assign-draftsman")
    assert d == {}


def test_정책_가드를_켜면_조회_전용은_처리기_앞에서_403(client, out, app, monkeypatch):
    monkeypatch.setitem(app.config, "AUTH_POLICY_ENABLED", True)
    drawer = gc.make_user("da-draw1", team="DRAWING")
    gc.login_as(client, gc.make_user("da-viewer", role="VIEWER", team="DRAWING"))
    resp, d, _ = _assign(client, _order(), {"user_ids": [drawer.id]})
    text = "조회 전용 계정은 이 작업을 할 수 없습니다."
    assert (resp.status_code, resp.get_json()) == (403, {"success": False, "code": "FORBIDDEN", "data": None,
                                                         "error": text, "message": text})
    assert d == {"audit": {"ACCESS_DENIED": 1}}


# --------------------------------------------------------------------------- #
# 대조군 — 옆 효과 하나를 시험 안에서 없애면 같은 견주기가 빨개져야 자국이 못박힌 것이다.
# --------------------------------------------------------------------------- #
def test_대조군_감사_줄을_빼면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(draftsman_api, "_audit_draftsman_assign", lambda *a, **k: None)
    _, drawer, _, resp, d, _ = _run_admin_one(client)
    assert resp.status_code == 200 and d != _assigned([drawer], "da-admin 직원") and "audit" not in d


def test_대조군_단계_이력_한_줄을_빼면_견주기가_빨개진다(client, out, monkeypatch):
    def _no_history(sd, users, **kw):
        result = apply_drawing_assignees(sd, users, **kw)
        sd["workflow"].pop("history", None)
        return result

    monkeypatch.setattr(draftsman_api, "apply_drawing_assignees", _no_history)
    _, drawer, _, resp, d, _ = _run_admin_one(client)
    assert resp.status_code == 200 and d != _assigned([drawer], "da-admin 직원") and "workflow" not in d["sd"]
