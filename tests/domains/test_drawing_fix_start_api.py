"""생산 넘어간 주문의 도면 수정 D3 — [수정 시작] · [수정 취소] API(설계서 2026-11-25 §4-1 · §4-2 · N1 · N2 · §6).

* 누가(§4-1): 도면팀 STAFF · MANAGER · 지정 담당 · 관리자 = 됨(취소는 누가 시작했든), 영업 · 반장 · 파트 계정 · 보기만 · 생산팀 MANAGER =
  403 ``FIX_FORBIDDEN``("도면 수정은 도면팀이나 관리자만 표시할 수 있어요.").
* 언제: [수정 시작]은 생산 단계만 — 시공 대기 · 그 밖 단계 409 ``FIX_STAGE``. 지금 도면에 없는 장 409 ``FIX_NOT_CURRENT``.
* 쓰기: 주문 JSON ``drawing_fix.fixing`` · ``log``(최근 50줄) · 버전 +1 · ``OrderEvent`` · 감사. 멱등 — 이미 그 상태면 200 ``changed:false``
  (버전 · 이벤트 · 감사 0).
* 뜻: 시작하면 D1 막힘 판정이 그 도면만 막고(나머지는 그대로), 취소하면 풀린다. 공장 '바뀐 것'에 한 줄씩("도면 고치는 중" ·
  "도면 수정 취소" — 폰 알림 없음).

되돌리면 실패: 영업 · 반장이 표시 200 · 시공 대기 [수정 시작] 200 · 같은 장 두 번 누름에 버전 +2 · 시작이 주문 통째를 막음 · '바뀐 것'에 줄
없음 · 폰 알림 생김. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.orders import drawing_fix as fx
from foms.services.orders.drawing_fix_marks import FIX_STARTED_EVENT, FIX_STOPPED_EVENT, confirm_text
from foms.services.production_change_alerts import collect_production_change_alerts
from models import Notification, Order, OrderEvent, SecurityLog
from tests.support.drawing_fix_workbench_seed import key, login, make_order, patch, people, sd_of

ALLOWED = ("staff", "manager", "assignee", "admin")
REFUSED = ("sales", "lead", "part", "viewer", "prod_manager")
FORBIDDEN = "도면 수정은 도면팀이나 관리자만 표시할 수 있어요."


@pytest.fixture
def who():
    return people()


def _start(client, oid: int, *sheets: str):
    return client.post(f"/api/orders/{oid}/drawing/fix/start", json={"targets": [{"sheet_id": s} for s in sheets]})


def _stop(client, oid: int, *sheets: str):
    return client.post(f"/api/orders/{oid}/drawing/fix/stop", json={"targets": [{"sheet_id": s} for s in sheets]})


def _code(res) -> str | None:
    return ((res.get_json() or {}).get("data") or {}).get("code")


def _version(oid: int) -> int:
    db_session.expire_all()
    return int(db_session.get(Order, oid).mutation_version or 0)


def _events(oid: int, event_type: str) -> list[OrderEvent]:
    db_session.expire_all()
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=event_type).all()


# --- 누가(§4-1) -----------------------------------------------------------------


@pytest.mark.parametrize("name", ALLOWED)
def test_drawing_team_assignee_and_admin_can_start_and_stop(client, who, name):
    oid = make_order(assignees=(who.assignee.id,))
    login(client, getattr(who, name))
    res = _start(client, oid, "s1")
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["changed"] is True and [(r["no"], r["ident"], r["by_name"]) for r in data["fixing"]] == [
        (2, "sheet:s1", getattr(who, name).name)]
    assert data["mutation_version"] == _version(oid)
    res = _stop(client, oid, "s1")
    assert res.status_code == 200 and res.get_json()["data"]["changed"] is True and res.get_json()["data"]["fixing"] == []


@pytest.mark.parametrize("name", REFUSED)
def test_sales_lead_part_viewer_and_production_manager_are_refused(client, who, name):
    oid = make_order()
    before = _version(oid)
    login(client, getattr(who, name))
    for res in (_start(client, oid, "s1"), _stop(client, oid, "s1")):
        assert res.status_code == 403 and _code(res) == "FIX_FORBIDDEN"
        assert res.get_json()["error"] == FORBIDDEN and res.get_json()["success"] is False
    sd = sd_of(oid)
    assert "drawing_fix" not in sd and _version(oid) == before and not _events(oid, FIX_STARTED_EVENT)


def test_anyone_in_drawing_team_stops_what_another_started(client, who):
    oid = make_order()
    login(client, who.staff)
    assert _start(client, oid, "s1").status_code == 200
    login(client, who.manager)
    res = _stop(client, oid, "s1")
    assert res.status_code == 200 and res.get_json()["data"]["changed"] is True
    log = sd_of(oid)["drawing_fix"]["log"]
    assert [(row["act"], row["by_name"], row["numbers"], row["idents"]) for row in log] == [
        ("start", "김도면", [2], ["sheet:s1"]), ("stop", "오도면", [2], ["sheet:s1"])]


# --- 언제 · 무엇(§4-2) ------------------------------------------------------------


@pytest.mark.parametrize("stage", ["CONSTRUCTION", "CONFIRM", "DRAWING"])
def test_start_only_in_production_stage(client, who, stage):
    oid = make_order(stage=stage)
    login(client, who.staff)
    res = _start(client, oid, "s1")
    assert res.status_code == 409 and _code(res) == "FIX_STAGE"
    assert res.get_json()["error"] == "생산 중인 주문만 수정 시작을 표시할 수 있어요."
    assert "drawing_fix" not in sd_of(oid)


@pytest.mark.parametrize("targets", [[{"sheet_id": "gone"}], [{"key": "orders/1/x.png"}], [], None, [{"sheet_id": "s1"}, {"sheet_id": "gone"}]])
def test_drawing_not_in_current_files_is_refused_and_nothing_written(client, who, targets):
    oid = make_order()
    login(client, who.staff)
    res = client.post(f"/api/orders/{oid}/drawing/fix/start", json={"targets": targets})
    assert res.status_code == 409 and _code(res) == "FIX_NOT_CURRENT"
    assert res.get_json()["error"] == "지금 도면에 없는 장이에요. 화면을 다시 열어 주세요."
    assert "drawing_fix" not in sd_of(oid)


def test_key_target_resolves_to_the_sheet_ident(client, who):
    oid = make_order()
    login(client, who.staff)
    res = client.post(f"/api/orders/{oid}/drawing/fix/start", json={"targets": [{"key": key(oid, "s2")}]})
    assert res.status_code == 200 and list(sd_of(oid)["drawing_fix"]["fixing"]) == ["sheet:s2"]


def test_missing_order_is_404(client, who):
    login(client, who.staff)
    assert _start(client, 999_999, "s1").status_code == 404


# --- 멱등 · 이벤트 · 감사 · log ---------------------------------------------------


def test_same_press_twice_writes_once(client, who):
    oid = make_order()
    login(client, who.staff)
    first = _start(client, oid, "s1")
    version = _version(oid)
    again = _start(client, oid, "s1")
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    assert again.get_json()["data"]["mutation_version"] == version == _version(oid)
    assert first.get_json()["data"]["fixing"] == again.get_json()["data"]["fixing"]
    assert len(_events(oid, FIX_STARTED_EVENT)) == 1 and len(sd_of(oid)["drawing_fix"]["log"]) == 1
    none = _stop(client, oid, "s2")                                      # 고치는 중이 아닌 장 취소 = 바뀐 것 없음
    assert none.status_code == 200 and none.get_json()["data"]["changed"] is False and not _events(oid, FIX_STOPPED_EVENT)


def test_event_audit_and_no_phone_notification(client, who):
    oid = make_order()
    login(client, who.staff)
    before = db_session.query(Notification).count()
    assert _start(client, oid, "s1", "s2").status_code == 200
    [event] = _events(oid, FIX_STARTED_EVENT)
    assert event.payload == {"numbers": [2, 3], "idents": ["sheet:s1", "sheet:s2"], "by_name": "김도면"}
    assert event.created_by_user_id == who.staff.id
    audit = db_session.query(SecurityLog).filter_by(action=FIX_STARTED_EVENT, target_id=oid).one()
    assert audit.user_id == who.staff.id and "도면 고치는 중" in audit.message and "도면 2 · 3" in audit.message
    assert _stop(client, oid, "s2").status_code == 200
    [stopped] = _events(oid, FIX_STOPPED_EVENT)
    assert stopped.payload["numbers"] == [3] and db_session.query(SecurityLog).filter_by(action=FIX_STOPPED_EVENT).count() == 1
    assert db_session.query(Notification).count() == before                 # 폰 · 종 알림 없음(§9 답 Q9)


def test_log_keeps_last_fifty_lines(client, who):
    old = [{"act": "done", "idents": [], "numbers": [], "by_name": "옛사람", "at": f"z{j}"} for j in range(60)]
    oid = make_order(extra={"drawing_fix": {"fixing": {}, "log": old}})
    login(client, who.staff)
    assert _start(client, oid, "s0").status_code == 200
    log = sd_of(oid)["drawing_fix"]["log"]
    assert len(log) == 50 and log[-1]["act"] == "start" and log[0]["at"] == "z11"


# --- 뜻: 그 도면만 막힘 · 풀림 · '바뀐 것' ------------------------------------------


def test_start_blocks_only_that_drawing_and_stop_releases(client, who):
    oid = make_order(4)
    login(client, who.staff)
    assert _start(client, oid, "s1").status_code == 200
    sd = sd_of(oid)
    block = fx.blocked(sd)
    assert block.whole is False and block.idents == frozenset({"sheet:s1"}) and block.why["sheet:s1"] == ("fixing",)
    files = sd["drawing_current_files"]
    assert [fx.drawing_blocked(sd, f) for f in files] == [False, True, False, False]
    assert [row["no"] for row in fx.blocked_entries(sd)] == [2]
    assert _stop(client, oid, "s1").status_code == 200
    sd = sd_of(oid)
    assert fx.blocked(sd).idents == frozenset() and not any(fx.drawing_blocked(sd, f) for f in sd["drawing_current_files"])


def test_production_changes_tab_gets_one_line_each(client, who):
    oid = make_order()
    login(client, who.staff)
    assert _start(client, oid, "s1").status_code == 200
    login(client, who.manager)
    assert _stop(client, oid, "s1").status_code == 200
    db_session.expire_all()
    result = collect_production_change_alerts(db_session, [db_session.get(Order, oid)], None)[oid]
    lines = [(a["label"], a["detail"], a["by_name"], a["kind"]) for a in result["alerts"] if a["label"].startswith("도면 ")]
    assert lines == [("도면 고치는 중", "도면 2", "김도면", "drawing"), ("도면 수정 취소", "도면 2", "오도면", "drawing")]
    assert all(isinstance(a["by_id"], int) for a in result["alerts"])


def test_confirm_texts_and_particles():
    assert confirm_text([2], starting=True) == "도면 2를 고치는 중으로 표시할까요? 공장에서 도면 2만 작업이 막혀요."
    assert confirm_text([3], starting=True) == "도면 3을 고치는 중으로 표시할까요? 공장에서 도면 3만 작업이 막혀요."
    assert confirm_text([2], starting=False) == "도면 2 수정을 취소할까요? 공장에서 도면 2를 다시 작업할 수 있어요."
    assert confirm_text([10], starting=False) == "도면 10 수정을 취소할까요? 공장에서 도면 10을 다시 작업할 수 있어요."


def test_server_owned_field_survives_other_requests_and_unknown_shape(client, who):
    """옛 ``drawing_fix`` 모양(요청만 있음)도 쓰기가 받아들이고 요청은 그대로 둔다(D4 몫 — 읽기만)."""
    request = {"id": "fr_1", "from": "factory", "targets": ["sheet:s2"], "numbers": [3], "state": "open", "by_name": "박반장",
               "at": "2026-11-25T01:00:00Z"}
    oid = make_order()
    patch(oid, drawing_fix={"requests": [request]})
    login(client, who.staff)
    assert _start(client, oid, "s0").status_code == 200
    table = sd_of(oid)["drawing_fix"]
    assert table["requests"] == [request] and list(table["fixing"]) == ["sheet:s0"]
    assert fx.blocked(sd_of(oid)).idents == frozenset({"sheet:s0", "sheet:s2"})


# --- 매니페스트 · 앞문 정책 -------------------------------------------------------


def test_routes_are_in_both_manifests_as_drawing_team_guard():
    from foms.services.orders.order_mutation_policy import load_policy_manifest
    from foms.services.request_write_guard import load_write_guard_manifest

    policy, guard = load_policy_manifest()["routes"], load_write_guard_manifest()["routes"]
    for act in ("start", "stop"):
        endpoint = f"erp_orders_drawing_fix.api_drawing_fix_{act}"
        rule = f"/api/orders/<int:order_id>/drawing/fix/{act}"
        assert policy[endpoint] == {"mode": "guard", "policy_id": "DRAWING_TEAM", "rule": rule}
        assert guard[endpoint] == {"mode": "guard", "rule": rule}


@pytest.fixture
def policy_on(app):
    """이 시험 동안만 앞문 정책 가드를 켠다(test_auth_enforcement 와 같은 꼴)."""
    previous = app.config.get("AUTH_POLICY_ENABLED")
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    app.config["AUTH_POLICY_ENABLED"] = previous


def test_front_policy_lets_drawing_team_through_and_handler_stops_production_manager(client, who, policy_on):
    """앞문(DRAWING_TEAM)은 MANAGER 를 팀과 상관없이 지나보낸다 — 생산팀 MANAGER 는 처리기가 403 FIX_FORBIDDEN 으로 막는다."""
    oid = make_order()
    login(client, who.staff)
    assert _start(client, oid, "s1").status_code == 200
    login(client, who.prod_manager)
    res = _stop(client, oid, "s1")
    assert res.status_code == 403 and _code(res) == "FIX_FORBIDDEN"
    login(client, who.sales)
    assert _stop(client, oid, "s1").status_code == 403                  # 앞문 또는 처리기 — 어느 쪽이든 막힘
    assert list(sd_of(oid)["drawing_fix"]["fixing"]) == ["sheet:s1"]
