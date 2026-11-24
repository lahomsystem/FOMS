"""장의 공장 지정 API(설계서 2026-11-23 §4-13 · §5-1 · §6-3 · §7, 3단계 ③) — 권한 · 막음 · 쓰기 · 기록 · 서버 소유 · 마법사 GET.

``POST /api/orders/<id>/drawing/sheet-factory``. 순수 규칙은 ``test_drawing_sheet_factory_rules.py``. 이름은 모두 지어낸 값이다.

되돌리면 실패: 생산팀 MANAGER 가 앞문을 지나 바꿈 · 도면 담당이 아닌 도면팀을 막음 · 담당 없는 주문을 막음 · 맡은 장을 옮김 · 같은 값에
버전 +1 · 하나 막혔는데 나머지를 씀 · 이벤트 · 감사 없음 · 거절 감사 없음 · 폼 저장 · 만들기 길이 공장을 바꿈 · 마법사 GET 에 공장 없음 ·
생산 전 단계에서 표시 줄을 읽음.
대조군: 1공장으로 되돌리면 줄을 지운다 · 생산 단계 아무도 손 안 댄 장은 옮겨진다.
"""
from __future__ import annotations

import json
from itertools import count

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.orders.order_create import create_order
from foms.services.orders.structured_form_projection import lock_server_owned_keys
from models import Order, ProductionPartMark, SecurityLog, User
from tests.support.production_part_claim_seed import Seed, code, events, fresh, login, make_order, patch_sd

_seq = count(1)


def _user(*, team: str | None = "DRAWING", role: str = "STAFF", name: str = "오가람") -> User:
    user = User(username=f"sf_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(n: int = 3, *, stage: str = "PRODUCTION", assignee: int | None = None, **extra) -> Seed:
    sd_extra = {"workflow": {"stage": stage}, **extra}
    if assignee is not None:
        sd_extra["assignments"] = {"drawing_assignee_user_ids": [assignee]}
    return make_order(n, extra=sd_extra)


def _sheets(seed: Seed) -> list[str]:
    return [f["sheet_id"] for f in fresh(seed.id).structured_data["drawing_current_files"]]


def _set(client, seed: Seed, items, **body):
    return client.post(f"/api/orders/{seed.id}/drawing/sheet-factory", json={"items": items, **body})


def _mark(seed: Seed, j: int, part: str, state: str, name: str) -> None:
    finished = state in ("DONE", "BASIC")
    db_session.add(ProductionPartMark(order_id=seed.id, drawing_key=seed.keys[j], part=part, state=state,
                                      picked_by_name=None if state == "BASIC" else name, done_by_name=name if finished else None))
    db_session.commit()


@pytest.fixture
def policy_on(app):
    """이 시험 동안만 정책 가드(매니페스트 · before_request)를 켠다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


# --------------------------------------------------------------------------- #
# 권한 — 도면팀 누구나 + 관리자(§5-1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("team", "role", "ok"), [
    ("CS", "ADMIN", True), ("DRAWING", "STAFF", True), ("DRAWING", "MANAGER", True),
    ("PRODUCTION", "STAFF", False), ("PRODUCTION", "MANAGER", False), ("CS", "STAFF", False), ("SALES", "STAFF", False),
    ("DRAWING", "VIEWER", False),
])
def test_drawing_team_anyone_and_admin_can_set_others_get_403(client, team, role, ok):
    owner = _user(name="장미래")
    seed = _order(assignee=owner.id)  # 지정 도면 담당은 장미래 — 오가람은 담당이 아니다
    login(client, _user(team=team, role=role))
    resp = _set(client, seed, [{"sheet_id": _sheets(seed)[1], "factory": 2}])
    if ok:
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["data"]["factory_by_sheet"] == {_sheets(seed)[1]: 2}
    else:
        assert resp.status_code == 403 and code(resp) == "FACTORY_DRAWING_ONLY"
        assert resp.get_json()["error"] == "공장은 도면팀이나 관리자만 지정할 수 있어요."
        assert "drawing_factory" not in fresh(seed.id).structured_data


def test_order_without_drawing_assignee_is_fine(client):
    seed = _order()
    login(client, _user())
    assert _set(client, seed, [{"key": seed.keys[0], "factory": 2}]).status_code == 200


def test_policy_guard_on_production_staff_denied_at_front_manager_by_handler(client, policy_on):
    seed = _order()
    login(client, _user(team="PRODUCTION"))
    front = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}])
    assert front.status_code == 403 and front.headers.get("X-Auth-Policy") == "denied"
    login(client, _user(team="PRODUCTION", role="MANAGER"))  # 앞문은 MANAGER 를 팀과 상관없이 지나보낸다
    handler = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}])
    assert handler.status_code == 403 and code(handler) == "FACTORY_DRAWING_ONLY" and handler.headers.get("X-Auth-Policy") is None
    login(client, _user())
    assert _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}]).status_code == 200
    db_session.expire_all()
    refused = db_session.query(SecurityLog).filter_by(action="DRAWING_SHEET_FACTORY_REFUSED", target_id=seed.id).all()
    assert len(refused) == 1 and "공장은 도면팀이나 관리자만" in refused[0].message


# --------------------------------------------------------------------------- #
# 언제 옮기나(§4-13 표)
# --------------------------------------------------------------------------- #
def test_untouched_sheet_moves_after_production_and_writes_event_audit_and_version(client):
    seed = _order()
    _mark(seed, 0, "cut", "NONE", "김재단")  # 맡았다 취소한 장(NONE 만) = 일이 시작 안 된 장
    before = fresh(seed.id).mutation_version
    login(client, _user())
    resp = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}], idempotency_key="k-1")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["factory_by_key"] == {seed.keys[0]: 2}
    assert [(c["index"], c["from"], c["to"]) for c in data["changed"]] == [(1, 1, 2)]
    order = fresh(seed.id)
    assert order.mutation_version == before + 1
    table = order.structured_data["drawing_factory"]
    assert table["sheets"] == {_sheets(seed)[0]: 2} and table["files"] == {} and table["by_name"] == "오가람"
    [ev] = events(seed.id, "DRAWING_SHEET_FACTORY_CHANGED")
    assert ev.payload["by_name"] == "오가람" and ev.payload["stage"] == "PRODUCTION" and ev.payload["changes"][0]["to"] == 2
    log = db_session.query(SecurityLog).filter_by(action="DRAWING_SHEET_FACTORY_CHANGED", target_id=seed.id).one()
    assert log.message.endswith("— 도면 공장 지정: 도면 1/3 1공장 → 2공장"), log.message
    again = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}], idempotency_key="k-1")  # 같은 key 다시
    assert again.status_code == 200 and fresh(seed.id).mutation_version == before + 1
    back = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 1}])  # 대조군: 1공장으로 되돌리면 줄을 지운다
    assert back.status_code == 200 and fresh(seed.id).structured_data["drawing_factory"]["sheets"] == {}


def test_same_value_writes_nothing(client):
    seed = _order()
    before = fresh(seed.id).mutation_version
    login(client, _user())
    resp = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 1}])
    assert resp.status_code == 200 and resp.get_json()["data"] == {"factory_by_sheet": {}, "factory_by_key": {}, "changed": []}
    order = fresh(seed.id)
    assert order.mutation_version == before and "drawing_factory" not in order.structured_data
    assert events(seed.id, "DRAWING_SHEET_FACTORY_CHANGED") == []


@pytest.mark.parametrize(("state", "part", "message"), [
    ("DONE", "cut", "2공장으로 옮길 수 없어요 — 1공장에서 김재단이 재단을 이미 완료한 장이에요. 이미 완료한 장은 옮기지 않아요."),
    ("NEED", "edge", "2공장으로 옮길 수 없어요 — 1공장 김재단이 엣지 담당이에요. 김재단에게 맡기 취소를 부탁한 뒤 다시 해 주세요."),
])
def test_started_sheet_is_refused_and_nothing_changes_even_with_other_items(client, state, part, message):
    seed = _order()
    _mark(seed, 1, part, state, "김재단")
    before = fresh(seed.id).mutation_version
    login(client, _user())
    resp = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}, {"sheet_id": _sheets(seed)[1], "factory": 2}])
    assert resp.status_code == 409 and code(resp) == "SHEET_HAS_WORK" and resp.get_json()["error"] == message
    blocked = resp.get_json()["data"]["blocked"]
    assert [(b["key"], b["kind"], b["part"], b["name"]) for b in blocked] == [
        (seed.keys[1], "done" if state == "DONE" else "held", part, "김재단")]
    order = fresh(seed.id)
    assert order.mutation_version == before and "drawing_factory" not in order.structured_data  # 하나라도 막히면 모두 안 바꿈
    refused = db_session.query(SecurityLog).filter_by(action="DRAWING_SHEET_FACTORY_REFUSED", target_id=seed.id).all()
    assert len(refused) == 1 and refused[0].detail["reason"] == message and refused[0].detail["code"] == "SHEET_HAS_WORK"


def test_finished_factory_and_done_order_and_unknown_sheet_are_refused(client):
    login(client, _user())
    seed = _order()
    patch_sd(seed.id, factory_done={"2": {"keys": [seed.keys[2]], "at": "2026-11-24T07:10:00", "by_name": "강검수"}})
    order = fresh(seed.id)
    sd = dict(order.structured_data, drawing_factory={"sheets": {_sheets(seed)[2]: 2}, "files": {}})
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    done = _set(client, seed, [{"sheet_id": _sheets(seed)[0], "factory": 2}])
    assert done.status_code == 409 and code(done) == "FACTORY_DONE"
    assert done.get_json()["error"] == "2공장은 강검수가 11/24 16:10에 제작 완료했어요. 옮기려면 2공장 완료부터 취소해 주세요."
    late = _order(stage="CONSTRUCTION")
    resp = _set(client, late, [{"sheet_id": _sheets(late)[0], "factory": 2}])
    assert resp.status_code == 409 and code(resp) == "ORDER_DONE" and resp.get_json()["error"] == "이미 제작 완료한 주문이에요."
    unknown = _set(client, late, [{"sheet_id": "no-such-sheet", "factory": 2}])
    assert unknown.status_code == 409 and code(unknown) == "DRAWING_NOT_CURRENT"


@pytest.mark.parametrize("body", [{}, {"items": []}, {"items": [{"sheet_id": "x", "factory": 3}]},
                                  {"items": [{"factory": 2}]}, {"items": [{"sheet_id": "x", "factory": True}]}])
def test_bad_body_is_400(client, body):
    seed = _order()
    login(client, _user())
    resp = client.post(f"/api/orders/{seed.id}/drawing/sheet-factory", json=body)
    assert resp.status_code == 400 and code(resp) == "BAD_REQUEST"


def _count_mark_reads(fn) -> int:
    seen: list[str] = []

    def _before(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT") and "production_part_marks" in statement:
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return len(seen)


def test_marks_are_read_once_in_production_and_never_before(client):
    login(client, _user())
    early, prod = _order(stage="DRAWING"), _order()
    assert _count_mark_reads(lambda: _set(client, early, [{"sheet_id": _sheets(early)[0], "factory": 2}])) == 0
    assert _count_mark_reads(lambda: _set(client, prod, [{"sheet_id": s, "factory": 2} for s in _sheets(prod)])) == 1


# --------------------------------------------------------------------------- #
# 서버 소유 — 폼 저장 · 만들기 길이 못 바꾼다 · 마법사 GET 이 읽어 준다
# --------------------------------------------------------------------------- #
def test_form_save_and_create_paths_cannot_write_drawing_factory():
    old = {"drawing_factory": {"sheets": {"s1": 2}}}
    form = {"drawing_factory": {"sheets": {"s1": 1, "s2": 2}}}
    assert lock_server_owned_keys(old, form) == ["drawing_factory"] and form["drawing_factory"] == {"sheets": {"s1": 2}}
    blank: dict = {"drawing_factory": {"sheets": {"s9": 2}}}
    assert lock_server_owned_keys({}, blank) == ["drawing_factory"] and "drawing_factory" not in blank
    owner = _user(team="SALES", name="최유나")
    order = create_order(db_session, actor_user_id=owner.id, owner_user_id=owner.id, is_erp_order=True,
                         order_fields=dict(received_date="2026-11-24", customer_name="가짜", phone="010-0000-0000",
                                           address="가짜시", product="가짜장", status="RECEIVED"),
                         structured_data={"drawing_factory": {"sheets": {"s1": 2}}, "parties": {"customer": {"name": "가짜"}}})
    db_session.commit()
    assert "drawing_factory" not in db_session.get(Order, order.id).structured_data


def test_add_order_form_json_cannot_carry_drawing_factory(client):
    login(client, _user(team="SALES", name="한영업"))
    sd = {"parties": {"customer": {"name": "가짜폼", "phone": "010-1111-2222"}}, "site": {"address_full": "가짜시 1"},
          "items": [{"product_name": "가짜장"}], "drawing_factory": {"sheets": {"s1": 2}}}
    resp = client.post("/add", data={"create_mode": "ERP_ORDER", "structured_data_json": json.dumps(sd, ensure_ascii=False)})
    assert resp.status_code in (302, 303), resp.status_code
    db_session.expire_all()
    order = db_session.query(Order).filter(Order.customer_name == "가짜폼").one()
    assert "drawing_factory" not in order.structured_data


def test_wizard_get_carries_second_factory_sheets_only(client):
    login(client, _user())
    seed = _order(drawing_wizard={"sheets": [{"id": "w-new", "name": "새 시트"}]})
    plain = client.get(f"/api/orders/{seed.id}/drawing-wizard").get_json()["data"]
    assert plain["factory_by_sheet"] == {}
    assert _set(client, seed, [{"sheet_id": "w-new", "factory": 2}]).status_code == 200  # 안 보낸 시트도 된다
    got = client.get(f"/api/orders/{seed.id}/drawing-wizard").get_json()["data"]
    assert got["factory_by_sheet"] == {"w-new": 2} and got["state"] == fresh(seed.id).structured_data["drawing_wizard"]
