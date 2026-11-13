"""생산 파트 표시 쓰기 API(``POST /api/production/part-marks`` · ``/part-marks/basic``) — 설계서 §15.4 · §15.7(P15-4).

대조군: 파트 계정의 자기 파트 쓰기는 200 · 관리자 정책 가드 통과 · 남이 맡지 않은 장은 그대로 · 목록 밖 새 도면은 그대로 ·
표시를 써도 주문 ``mutation_version`` · 공정 칸 그대로(누를 때마다 버전이 오르는 구현이면 실패).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from itertools import count

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderEvent, PartnerOrg, ProductionPartMark, SecurityLog, User

ONE = "/api/production/part-marks"
BULK = "/api/production/part-marks/basic"
_seq = count(1)


@pytest.fixture
def policy_on(app):
    """이 시험 동안만 정책 가드(매니페스트)를 켠다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


@dataclass(frozen=True)
class Person:
    """시드 사용자의 값만(요청 끝에 세션이 닫혀 ORM 객체는 떨어진다)."""

    id: int
    username: str
    role: str


def _user(name: str, *, team: str | None = "PRODUCTION", role: str = "STAFF", part: str | None = None,
          partner_org_id: int | None = None) -> Person:
    user = User(username=f"pm_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part, partner_org_id=partner_org_id)
    db_session.add(user)
    db_session.commit()
    return Person(user.id, user.username, user.role)


def _login(client, user: Person) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


@dataclass(frozen=True)
class Seed:
    """시드 주문의 값만(요청 끝에 세션이 닫혀 ORM 객체는 떨어진다)."""

    id: int
    keys: tuple[str, ...]
    version: int
    sd: dict


def _order(n: int = 3, *, stage: str = "PRODUCTION", prefix: str | None = None) -> Seed:
    prefix = prefix or f"m{next(_seq)}"
    files = [{"key": f"{prefix}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{prefix}-s{j}"} for j in range(n)]
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "파트고객"}}, "drawing_current_files": files,
          "production": {"steps": [{"key": "cut", "label": "재단", "done": False, "at": None, "by_name": None}]}}
    order = Order(received_date=get_today_kst().isoformat(), customer_name="파트고객", phone="010-0000-0000",
                  address="서울", product="거실장", status=stage, is_erp_order=True, erp_stage_code=stage,
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return Seed(order.id, tuple(f["key"] for f in files), order.mutation_version, copy.deepcopy(sd))


def _key(order: Seed, j: int) -> str:
    return order.keys[j]


def _one(client, order: Seed, j: int, part: str, action: str, seen: str, **extra):
    body = {"order_id": order.id, "drawing_key": _key(order, j), "part": part, "action": action, "seen": seen, **extra}
    return client.post(ONE, json=body)


def _row(order: Seed, j: int, part: str) -> ProductionPartMark | None:
    db_session.expire_all()
    return (db_session.query(ProductionPartMark)
            .filter_by(order_id=order.id, drawing_key=_key(order, j), part=part).one_or_none())


def _events(order: Seed) -> list[OrderEvent]:
    return db_session.query(OrderEvent).filter_by(order_id=order.id, event_type="PRODUCTION_PART_MARKED").all()


def _code(resp) -> str:
    return (resp.get_json().get("data") or {}).get("code")


# --------------------------------------------------------------------------- #
# 권한 — 파트 문(D53 · D55)
# --------------------------------------------------------------------------- #
def test_part_account_writes_only_own_part(client):
    order = _order()
    _login(client, _user("김재단", part="cut"))
    forbidden = _one(client, order, 0, "assemble", "take", "none")
    assert forbidden.status_code == 403 and _code(forbidden) == "PART_FORBIDDEN"
    assert forbidden.get_json()["error"] == "자기 파트만 체크할 수 있어요."
    assert _row(order, 0, "assemble") is None
    ok = _one(client, order, 0, "cut", "take", "none")  # 대조군: 자기 파트는 된다
    assert ok.status_code == 200 and ok.get_json()["data"]["mark"]["state"] == "need"


@pytest.mark.parametrize("team,role", [("PRODUCTION", "STAFF"), ("CS", "STAFF"), ("SALES", "STAFF"),
                                       ("CS", "MANAGER"), ("PRODUCTION", "VIEWER")])
def test_accounts_without_part_get_part_required(client, team, role):
    order = _order()
    _login(client, _user("파트없음", team=team, role=role, part="cut" if role == "VIEWER" else None))
    resp = _one(client, order, 0, "cut", "take", "none")
    assert resp.status_code == 403 and _code(resp) == "PART_REQUIRED"
    assert _row(order, 0, "cut") is None


def test_cs_blocked_by_policy_guard_part_account_passes(client, policy_on):
    order = _order()
    _login(client, _user("상담", team="CS"))
    assert _one(client, order, 0, "cut", "take", "none").status_code == 403
    _login(client, _user("김재단", part="cut"))
    assert _one(client, order, 0, "cut", "take", "none").status_code == 200  # 대조군: 생산팀 파트 계정은 가드를 지난다


def test_admin_marks_any_part_and_overrides_someone_elses(client):
    order = _order()
    park = _user("박재단", part="cut")
    admin = _user("관리자", team="CS", role="ADMIN", part="edge")  # 계정 파트가 있어도 무시(D55)
    _login(client, admin)
    for part in ("cut", "edge", "assemble", "inspect"):
        resp = _one(client, order, 1, part, "take", "none")
        assert resp.status_code == 200, (part, resp.get_json())
        assert _row(order, 1, part).picked_by_name == "관리자"

    _login(client, park)
    assert _one(client, order, 0, "cut", "take", "none").status_code == 200
    for action, seen in (("take", "none"), ("done", "need")):
        assert _one(client, order, 2, "cut", action, seen).status_code == 200
    _login(client, admin)
    done = _one(client, order, 0, "cut", "done", "need", override=True)  # 박재단이 맡은 장을 관리자가 끝냄
    assert done.status_code == 200
    row = _row(order, 0, "cut")
    assert (row.state, row.picked_by_name, row.done_by_name) == ("DONE", "박재단", "관리자")
    assert _one(client, order, 2, "cut", "undo", "done").status_code == 200  # 박재단이 끝낸 장 되돌리기
    row = _row(order, 2, "cut")
    assert (row.state, row.picked_by_name, row.done_by_name) == ("NEED", "박재단", None)
    overrides = {(e.payload["key"], e.payload["action"]): e.payload["override"] for e in _events(order)}
    assert overrides[(_key(order, 0), "done")] is True and overrides[(_key(order, 2), "undo")] is True
    assert overrides[(_key(order, 0), "take")] is False  # 대조군: 박재단 자신의 맡기
    log = db_session.query(SecurityLog).filter(SecurityLog.message.like("%관리자 덮어쓰기%")).count()
    assert log == 2


def test_partner_and_freelancer_are_blocked(client, app):
    order = _order()
    org = PartnerOrg(name=f"협력{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    _login(client, _user("협력직원", team=None, role="PARTNER", partner_org_id=org.id))
    assert _one(client, order, 0, "cut", "take", "none").status_code == 403

    fl = _user("프리영업", team="SALES")
    save_freelancer(db_session, fl.id, {"match_name": f"프리{next(_seq)}", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True}, base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    _login(client, fl)
    assert _one(client, order, 0, "cut", "take", "none").status_code == 403
    assert _row(order, 0, "cut") is None


# --------------------------------------------------------------------------- #
# 상태 전이 표
# --------------------------------------------------------------------------- #
def test_cut_transition_table(client):
    order = _order()
    me = _user("김재단", part="cut")
    _login(client, me)
    steps = [(0, "take", "none", "NEED"), (0, "done", "need", "DONE"), (0, "undo", "done", "NEED"),
             (1, "basic", "none", "BASIC"), (1, "undo", "basic", "NONE")]
    for j, action, seen, state in steps:
        resp = _one(client, order, j, "cut", action, seen)
        assert resp.status_code == 200, (action, resp.get_json())
        assert _row(order, j, "cut").state == state
    first, second = _row(order, 0, "cut"), _row(order, 1, "cut")
    assert (first.picked_by_name, first.done_by_name) == ("김재단", None)  # 되돌리면 맡은 사람은 남고 끝낸 사람만 빈다
    assert (second.picked_by_name, second.done_by_name, second.sheet_id) == (None, None, f"{_key(order, 1)[:-7]}-s1")
    assert [e.payload["to"] for e in _events(order)] == ["NEED", "DONE", "NEED", "BASIC", "NONE"]
    log = db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).first()
    assert "생산 파트 체크" in log.message and "재단 안 봄 → 작업 필요" in log.message


def test_other_parts_have_no_basic_and_bad_pairs_are_400(client):
    order = _order()
    _login(client, _user("이조립", part="assemble"))
    basic = _one(client, order, 0, "assemble", "basic", "none")
    assert basic.status_code == 400 and _code(basic) == "BASIC_CUT_ONLY"
    for action, seen, state in (("take", "none", "NEED"), ("done", "need", "DONE"), ("undo", "done", "NEED")):
        assert _one(client, order, 0, "assemble", action, seen).status_code == 200
        assert _row(order, 0, "assemble").state == state
    for action, seen in (("take", "need"), ("done", "none"), ("undo", "need"), ("undo", "none")):
        resp = _one(client, order, 1, "assemble", action, seen)
        assert resp.status_code == 400 and _code(resp) == "BAD_REQUEST", (action, seen)
    assert client.post(ONE, json={"order_id": order.id, "drawing_key": _key(order, 0), "part": "paint",
                                  "action": "take", "seen": "none"}).status_code == 400


# --------------------------------------------------------------------------- #
# 409 셋 · 멱등
# --------------------------------------------------------------------------- #
def test_mark_conflict_names_the_owner(client):
    order = _order()
    _login(client, _user("박재단", part="cut"))
    assert _one(client, order, 0, "cut", "take", "none").status_code == 200
    _login(client, _user("김재단", part="cut"))
    for action, seen in (("take", "none"), ("basic", "none"), ("done", "need")):
        resp = _one(client, order, 0, "cut", action, seen)
        body = resp.get_json()
        assert resp.status_code == 409 and body["data"]["code"] == "MARK_CONFLICT", action
        assert body["error"] == "박재단이 먼저 맡았어요"
        assert body["data"]["mark"]["picked_by_name"] == "박재단" and body["data"]["mark"]["state"] == "need"
    stale = _one(client, order, 1, "cut", "done", "need")  # 화면은 작업 필요로 봤는데 아무도 안 맡은 장
    assert stale.status_code == 409 and _code(stale) == "MARK_CONFLICT"
    assert _row(order, 0, "cut").picked_by_name == "박재단" and len(_events(order)) == 1


def test_drawing_not_current_and_not_in_production(client):
    me = _user("김재단", part="cut")
    _login(client, me)
    order = _order()
    gone = client.post(ONE, json={"order_id": order.id, "drawing_key": "m0/old.png", "part": "cut", "action": "take",
                                  "seen": "none"})
    assert gone.status_code == 409 and _code(gone) == "DRAWING_NOT_CURRENT"
    assert gone.get_json()["error"] == "도면이 바뀌었어요. 다시 받아 주세요."
    waiting = _order(stage="CONFIRM")
    resp = _one(client, waiting, 0, "cut", "take", "none")
    assert resp.status_code == 409 and _code(resp) == "NOT_IN_PRODUCTION"
    missing = client.post(ONE, json={"order_id": 987654, "drawing_key": "x.png", "part": "cut", "action": "take",
                                     "seen": "none"})
    assert missing.status_code == 404 and _code(missing) == "NOT_FOUND"
    assert db_session.query(ProductionPartMark).count() == 0


def test_same_person_same_result_twice_is_one_change(client):
    order = _order()
    _login(client, _user("김재단", part="cut"))
    for action, seen in (("take", "none"), ("done", "need")):
        first = _one(client, order, 0, "cut", action, seen)
        again = _one(client, order, 0, "cut", action, seen)
        assert first.status_code == again.status_code == 200
        assert (first.get_json()["data"]["changed"], again.get_json()["data"]["changed"]) == (True, False)
    assert [e.payload["action"] for e in _events(order)] == ["take", "done"]


def test_marks_do_not_bump_mutation_version_or_touch_steps(client):
    """대조군(§15.7): 표시 쓰기가 공정 칸을 안 바꾸면(3장 중 2장만 끝) 버전 · sd 그대로 — 바뀌는 경우는
    ``test_production_part_steps_sync.py``."""
    order = _order()
    before_version, before_sd = order.version, order.sd
    _login(client, _user("김재단", part="cut"))
    for j in range(2):
        assert _one(client, order, j, "cut", "basic", "none").status_code == 200
    assert client.post(BULK, json={"part": "cut", "seen": "none", "items": [
        {"order_id": order.id, "drawing_key": _key(order, 0)}]}).status_code == 200
    db_session.expire_all()
    fresh = db_session.get(Order, order.id)
    assert fresh.mutation_version == before_version
    assert fresh.structured_data == before_sd


# --------------------------------------------------------------------------- #
# 일괄 기본 — 보낸 목록만 · 일부 성공
# --------------------------------------------------------------------------- #
def test_bulk_changes_only_the_sent_list(client):
    order = _order(3)
    sent = [{"order_id": order.id, "drawing_key": _key(order, j)} for j in range(3)]
    live = db_session.get(Order, order.id)  # 창을 연 뒤 같은 날 새 도면 1장이 붙었다
    sd = copy.deepcopy(live.structured_data)
    sd["drawing_current_files"].append({"key": "late/new.png", "filename": "new.png"})
    live.structured_data = sd
    flag_modified(live, "structured_data")
    db_session.commit()

    _login(client, _user("김재단", part="cut"))
    resp = client.post(BULK, json={"part": "cut", "seen": "none", "items": sent})
    data = resp.get_json()["data"]
    assert resp.status_code == 200 and [a["state"] for a in data["applied"]] == ["basic"] * 3
    assert data["skipped"] == [] and data["order_steps"] == []
    assert db_session.query(ProductionPartMark).filter_by(drawing_key="late/new.png").count() == 0


def test_bulk_partial_success_reports_skipped_with_owner(client):
    order = _order(3)
    other = _order(1, stage="CONFIRM")
    _login(client, _user("박재단", part="cut"))
    assert _one(client, order, 1, "cut", "take", "none").status_code == 200
    _login(client, _user("김재단", part="cut"))
    items = [{"order_id": order.id, "drawing_key": _key(order, j)} for j in range(3)]
    items += [{"order_id": order.id, "drawing_key": "gone.png"}, {"order_id": other.id, "drawing_key": _key(other, 0)},
              {"order_id": 987654, "drawing_key": "x.png"}]
    data = client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]
    assert [a["drawing_key"] for a in data["applied"]] == [_key(order, 0), _key(order, 2)]
    reasons = {s["drawing_key"]: (s["reason"], s["error"]) for s in data["skipped"]}
    assert reasons[_key(order, 1)] == ("MARK_CONFLICT", "박재단이 먼저 맡았어요")
    assert reasons["gone.png"][0] == "DRAWING_NOT_CURRENT"
    assert reasons[_key(other, 0)][0] == "NOT_IN_PRODUCTION" and reasons["x.png"][0] == "NOT_FOUND"
    assert _row(order, 1, "cut").state == "NEED"
    audits = db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).all()
    assert any("재단 기본 2장" in a.message for a in audits)
    none_left = client.post(BULK, json={"part": "cut", "seen": "none", "items": items[3:]})
    assert none_left.status_code == 200 and none_left.get_json()["data"]["applied"] == []  # 전부 실패해도 200


def test_bulk_reuses_row_left_by_undo_and_repeat_is_unchanged(client):
    order = _order(2)
    _login(client, _user("김재단", part="cut"))
    assert _one(client, order, 0, "cut", "basic", "none").status_code == 200
    assert _one(client, order, 0, "cut", "undo", "basic").status_code == 200  # 줄은 NONE 으로 남는다
    items = [{"order_id": order.id, "drawing_key": _key(order, j)} for j in range(2)]
    first = client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]
    assert [(a["state"], a["done_by_name"], a["changed"]) for a in first["applied"]] == [("basic", "김재단", True)] * 2
    assert db_session.query(ProductionPartMark).filter_by(order_id=order.id).count() == 2  # 남은 줄을 고쳐 씀
    again = client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]
    assert [a["changed"] for a in again["applied"]] == [False, False] and again["skipped"] == []
    assert len(_events(order)) == 4  # 기본 · 되돌리기 · 일괄 2장 — 다시 보낸 일괄은 0


def test_bulk_gates_and_limits(client):
    order = _order(1)
    _login(client, _user("최엣지", part="edge"))
    items = [{"order_id": order.id, "drawing_key": _key(order, 0)}]
    assert _code(client.post(BULK, json={"part": "cut", "seen": "none", "items": items})) == "PART_FORBIDDEN"
    assert _code(client.post(BULK, json={"part": "edge", "seen": "none", "items": items})) == "BASIC_CUT_ONLY"
    _login(client, _user("김재단", part="cut"))
    too_many = [{"order_id": order.id, "drawing_key": f"k{j}.png"} for j in range(201)]
    assert _code(client.post(BULK, json={"part": "cut", "seen": "none", "items": too_many})) == "TOO_MANY"
    assert _code(client.post(BULK, json={"part": "cut", "seen": "need", "items": items})) == "BAD_REQUEST"
    assert _row(order, 0, "cut") is None


# --------------------------------------------------------------------------- #
# 쓰기 쿼리 수
# --------------------------------------------------------------------------- #
def _count(fn):
    seen = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, seen["n"]


#: 실측(2026-11-13, SQLite 레인): 한 장 쓰기 = 6(사용자 · 주문 잠금 · 표시 줄 읽기 · 표시 쓰기 · 이벤트 · 감사). 상한 = +30%.
#: 이 계약은 **공정 칸이 안 바뀌는 쓰기**다(P15-6 뒤에도 쿼리를 늘리지 않는다 — 주문마다 끝나지 않은 장을 하나 남긴다).
#: 칸이 바뀌는 쓰기의 상한은 ``test_production_part_steps_sync.py`` 의 ``STEP_CHANGE_*``.
ONE_WRITE_CAP = 7
#: 실측: 일괄 5장 = 6, 50장(주문 10) = 6 — 주문 잠금 · 표시 줄 읽기 한 번씩, 표시 · 이벤트 · 감사 INSERT 는 표마다 한 번.
BULK_DELTA_CAP = 2
BULK_ABS_CAP = 8


def test_write_query_counts(client):
    _login(client, _user("김재단", part="cut"))
    order = _order(2)  # 2장 중 1장만 끝 → 칸 그대로
    _one(client, order, 0, "cut", "take", "none")  # warmup
    resp, n_one = _count(lambda: _one(client, order, 0, "cut", "done", "need"))
    assert resp.status_code == 200 and n_one <= ONE_WRITE_CAP, n_one

    small = [_order(6)]  # 6장 중 5장만 보냄 → 칸 그대로
    big = [_order(6) for _ in range(10)]

    def _items(orders):
        return [{"order_id": o.id, "drawing_key": _key(o, j)} for o in orders for j in range(5)]

    resp_s, q_small = _count(lambda: client.post(BULK, json={"part": "cut", "seen": "none", "items": _items(small)}))
    resp_b, q_big = _count(lambda: client.post(BULK, json={"part": "cut", "seen": "none", "items": _items(big)}))
    assert len(resp_s.get_json()["data"]["applied"]) == 5 and len(resp_b.get_json()["data"]["applied"]) == 50
    assert q_big - q_small <= BULK_DELTA_CAP and q_big <= BULK_ABS_CAP, (q_small, q_big)
    many = db_session.query(SecurityLog).filter(SecurityLog.message.like("주문 10건 — %")).one()  # 감사는 요청마다 한 줄
    assert many.message == "주문 10건 — 생산 파트 체크: 재단 기본 50장" and len(many.detail["orders"]) == 10
