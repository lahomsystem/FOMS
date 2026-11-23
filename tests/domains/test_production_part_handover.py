"""파트 카드 쓰기 — 맡기 취소 · 담당 바꾸기(B2 · B12) · 보류 · 도면 고치는 중(B4) · 첫 카드 제작 시작(B6) · 바뀐 기록 목록.

설계서 2026-11-23-production-self-claim-and-factory2 §4-5 · §4-6 · §4-8 · §4-11 · §6-4 · §7(P1).

경합은 주문 행 잠금이 줄을 세운다 — SQLite 레인은 ``FOR UPDATE`` 를 무시하므로 여기서는 **줄 선 차례**(먼저 온 쓰기가 끝난
뒤 늦은 화면이 보내는 쓰기)를 시험한다: 담당 바꾸기 ↔ 완료 · 맡기 취소 ↔ 담당 바꾸기 · 둘이 같은 장 담당 바꾸기 · 멱등 다시 보냄.

되돌리면 실패: 맡기 취소 · 담당 바꾸기 길 빼기 · 바뀐 기록 칸을 안 쓰거나 맡기 취소에 남기기 · 두 번째 바꾸기가 첫 담당을 남기기 ·
``seen_by`` 를 안 견주기 · 남의 장 맡기 취소 받기 · 보류 중 맡기 받기 · 보류 중 맡기 취소 막기 · 첫 카드에 제작 시작 안 하기 ·
두 번째 카드에 회차 또 열기 · 이벤트 이름 스냅샷 빼기 · 바뀐 기록 목록 권한 빼기.
대조군: 지금 누름의 경합 글("박재단이 먼저 맡았어요") · ``seen_by`` 없이 보내는 지금 화면 · 제작 중 주문의 맡기(회차 그대로).
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, text

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from models import PartnerOrg, ProductionPartMark, SecurityLog
from tests.support.production_part_claim_seed import (
    BULK,
    HISTORY,
    code,
    current_runs,
    events,
    finish,
    fresh,
    login,
    make_order,
    make_user,
    mark,
    patch_sd,
    row,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _count(fn):
    seen = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), seen["n"]
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _held(client, order, j: int = 0):
    """박엣지가 맡은 장(엣지) — (박엣지, 주문)."""
    park = make_user("박엣지", part="edge")
    login(client, park)
    assert mark(client, order, j, "edge", "take", "none").status_code == 200
    return park


# --------------------------------------------------------------------------- #
# 맡기 취소(release)
# --------------------------------------------------------------------------- #
def test_release_clears_holder_and_records_event(client):
    order = make_order(2)
    park = _held(client, order)
    resp = mark(client, order, 0, "edge", "release", "need", seen_by=park.id)
    assert resp.status_code == 200 and resp.get_json()["data"]["mark"]["state"] == "none"
    saved = row(order.id, order.keys[0], "edge")
    assert (saved.state, saved.picked_by_name, saved.picked_at, saved.handed_from_name) == ("NONE", None, None, None)
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["action"], payload["from"], payload["to"], payload["by_name"]) == ("release", "NEED", "NONE", "박엣지")
    log = db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).all()[-1]
    assert "엣지 맡기 취소 (박엣지)" in log.message
    again = mark(client, order, 0, "edge", "release", "need", seen_by=park.id)  # 멱등
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False


def test_release_of_someone_elses_sheet_is_admin_only(client):
    order = make_order(1)
    _held(client, order)
    login(client, make_user("김엣지", part="edge"))
    denied = mark(client, order, 0, "edge", "release", "need")
    assert denied.status_code == 403 and code(denied) == "RELEASE_NOT_HOLDER"
    login(client, make_user("관리", team="CS", role="ADMIN"))
    assert mark(client, order, 0, "edge", "release", "need").status_code == 200
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["override"], payload["holder_name"], payload["by_name"]) == (True, "박엣지", "관리")


# --------------------------------------------------------------------------- #
# 담당 바꾸기(takeover) · 바뀐 기록 칸
# --------------------------------------------------------------------------- #
def test_takeover_records_handover_and_survives_done_and_undo(client):
    order = make_order(1)
    park = _held(client, order)
    kim = make_user("김민준", part="edge")
    login(client, kim)
    assert code(mark(client, order, 0, "edge", "takeover", "need")) == "BAD_REQUEST"  # seen_by 는 꼭
    resp = mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    data = resp.get_json()["data"]
    assert resp.status_code == 200 and data["mark"]["picked_by_name"] == "김민준"
    assert data["mark"]["handed_from_name"] == "박엣지" and data["mark"]["handed_at"].endswith("+00:00")
    saved = row(order.id, order.keys[0], "edge")
    assert (saved.picked_by_user_id, saved.handed_from_name) == (kim.id, "박엣지") and saved.handed_at is not None
    payload = events(order.id, "PRODUCTION_PART_MARKED")[-1].payload
    assert (payload["action"], payload["from_user_id"], payload["from_name"], payload["by_name"]) == (
        "takeover", park.id, "박엣지", "김민준")
    log = db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).all()[-1]
    assert "엣지 담당 바꿈 (박엣지 → 김민준)" in log.message
    assert mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id).get_json()["data"]["changed"] is False
    assert mark(client, order, 0, "edge", "done", "need", seen_by=kim.id).status_code == 200
    assert row(order.id, order.keys[0], "edge").handed_from_name == "박엣지"  # 완료로 가도 남는다
    assert mark(client, order, 0, "edge", "undo", "done").status_code == 200
    assert row(order.id, order.keys[0], "edge").handed_from_name == "박엣지"  # 완료 취소도 남는다
    assert mark(client, order, 0, "edge", "release", "need").status_code == 200
    assert row(order.id, order.keys[0], "edge").handed_from_name is None  # 맡기 취소는 지운다


def test_second_takeover_keeps_only_the_immediate_previous_holder(client):
    order = make_order(1)
    park = _held(client, order)
    kim = make_user("김민준", part="edge")
    login(client, kim)
    mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    login(client, make_user("최가은", part="edge"))
    assert mark(client, order, 0, "edge", "takeover", "need", seen_by=kim.id).status_code == 200
    assert row(order.id, order.keys[0], "edge").handed_from_name == "김민준"


# --------------------------------------------------------------------------- #
# 경합(줄 선 차례) · 지금 화면 대조군
# --------------------------------------------------------------------------- #
def test_takeover_then_late_done_from_old_holder(client):
    order = make_order(1)
    park = _held(client, order)
    login(client, make_user("김민준", part="edge"))
    mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    login(client, park)
    late = mark(client, order, 0, "edge", "done", "need", seen_by=park.id)
    assert late.status_code == 409 and code(late) == "MARK_CONFLICT"
    assert late.get_json()["error"] == "그사이 김민준으로 담당이 바뀌었어요. 이 장은 이제 김민준이 해요."
    assert late.get_json()["data"]["mark"]["picked_by_name"] == "김민준"
    legacy = mark(client, order, 0, "edge", "done", "need")  # 대조군: seen_by 없는 지금 화면 = 지금 글
    assert code(legacy) == "MARK_CONFLICT" and legacy.get_json()["error"] == "김민준이 먼저 맡았어요"


def test_done_then_late_takeover(client):
    order = make_order(1)
    park = _held(client, order)
    assert mark(client, order, 0, "edge", "done", "need").status_code == 200
    login(client, make_user("김민준", part="edge"))
    late = mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    assert code(late) == "MARK_CONFLICT" and late.get_json()["error"] == "그사이 박엣지가 완료했어요. 더 할 일은 없어요."


def test_release_then_late_takeover_and_two_takeovers(client):
    order = make_order(2)
    park = _held(client, order, 0)
    mark(client, order, 1, "edge", "take", "none")
    mark(client, order, 0, "edge", "release", "need")
    login(client, make_user("김민준", part="edge"))
    late = mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    assert late.get_json()["error"] == "그사이 맡기가 취소됐어요. 지금은 담당 미정이에요."
    assert mark(client, order, 1, "edge", "takeover", "need", seen_by=park.id).status_code == 200  # 먼저 온 바꾸기
    login(client, make_user("최가은", part="edge"))
    second = mark(client, order, 1, "edge", "takeover", "need", seen_by=park.id)  # 같은 화면을 본 늦은 바꾸기
    assert code(second) == "MARK_CONFLICT" and "김민준으로 담당이 바뀌었어요" in second.get_json()["error"]
    assert row(order.id, order.keys[1], "edge").picked_by_name == "김민준"


# --------------------------------------------------------------------------- #
# 보류 · 도면 고치는 중(B4)
# --------------------------------------------------------------------------- #
def test_hold_and_revision_block_cards_but_allow_release_and_undo(client):
    order = make_order(4)
    login(client, make_user("김재단", part="cut"))
    finish(client, order, 0, "cut")
    mark(client, order, 1, "cut", "take", "none")
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})
    held = mark(client, order, 2, "cut", "take", "none")
    assert held.status_code == 409 and code(held) == "HOLD_ACTIVE"
    assert held.get_json()["error"] == "보류된 주문이라 지금은 못 눌러요. 보류가 풀리면 다시 돼요."
    assert code(mark(client, order, 1, "cut", "done", "need")) == "HOLD_ACTIVE"
    assert mark(client, order, 1, "cut", "release", "need").status_code == 200  # 맡기 취소는 된다
    assert mark(client, order, 0, "cut", "undo", "done").status_code == 200  # 완료 취소도 된다
    bulk = client.post(BULK, json={"part": "cut", "seen": "none", "items": [{"order_id": order.id,
                                                                             "drawing_key": order.keys[3]}]})
    assert bulk.get_json()["data"]["skipped"][0]["reason"] == "HOLD_ACTIVE"
    patch_sd(order.id, hold={"active": False})
    order_sd = fresh(order.id).structured_data
    order_sd["drawing_status"] = "RETURNED"
    from sqlalchemy.orm.attributes import flag_modified
    live = fresh(order.id)
    live.structured_data = order_sd
    flag_modified(live, "structured_data")
    db_session.commit()
    revising = mark(client, order, 2, "cut", "take", "none")
    assert code(revising) == "DRAWING_REVISING"
    assert revising.get_json()["error"] == "도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요."


# --------------------------------------------------------------------------- #
# 첫 카드 = 제작 시작(B6)
# --------------------------------------------------------------------------- #
#: 실측(2026-11-23, SQLite 레인): 제작대기 주문 첫 맡기 = 18 — 지금 한 장 쓰기 6 + 회차 찾기 1 + 주문 쓰기 한 번
#: (잠금 · structured_data 저장 훅 · 주문 UPDATE · 영수증 · 읽기 자원 · 회차 · 이벤트 · 감사 INSERT). 상한 = 실측 + 30% 남짓.
FIRST_TAKE_CAP = 23
#: 제작 중 주문의 맡기 = 한 장 쓰기 6 + 회차 찾기 1(§12 "맡기 +1").
TAKE_CAP = 8


def test_first_card_starts_production_once(client):
    order = make_order(2, run=False)
    login(client, make_user("김재단", part="cut"))
    version = fresh(order.id).mutation_version
    resp, n_first = _count(lambda: mark(client, order, 0, "cut", "take", "none"))
    assert resp.status_code == 200 and resp.get_json()["data"]["run_started"] is True
    assert n_first <= FIRST_TAKE_CAP, n_first
    assert current_runs(order.id) == 1 and fresh(order.id).mutation_version == version + 1
    started = events(order.id, "PRODUCTION_STARTED")
    assert len(started) == 1 and started[0].payload["via"] == "part_marks" and started[0].payload["run_started"] is True
    assert fresh(order.id).structured_data["workflow"]["history"][-1]["note"] == "제작 시작 (도면 카드 첫 맡기)"
    audit = db_session.query(SecurityLog).filter_by(action="PRODUCTION_STARTED", target_id=order.id).one()
    assert "도면 카드 첫 맡기" in audit.message and audit.detail["via"] == "part_marks"
    second, n_take = _count(lambda: mark(client, order, 1, "cut", "take", "none"))
    assert second.get_json()["data"]["run_started"] is False and n_take <= TAKE_CAP, n_take
    assert current_runs(order.id) == 1 and fresh(order.id).mutation_version == version + 1  # 회차 · 버전 그대로
    mark(client, order, 0, "cut", "release", "need")
    mark(client, order, 1, "cut", "release", "need")
    assert current_runs(order.id) == 1  # 맡기를 모두 취소해도 제작 중 그대로(되돌리기는 [제작 취소])


def test_bulk_basic_starts_each_waiting_order_in_one_write(client):
    waiting, running = [make_order(2, run=False) for _ in range(2)], make_order(2)
    login(client, make_user("김재단", part="cut"))
    items = [{"order_id": o.id, "drawing_key": o.keys[0]} for o in (*waiting, running)]
    data = client.post(BULK, json={"part": "cut", "seen": "none", "items": items}).get_json()["data"]
    assert sorted(data["run_started"]) == sorted(o.id for o in waiting)
    assert [current_runs(o.id) for o in (*waiting, running)] == [1, 1, 1]
    assert [len(events(o.id, "PRODUCTION_STARTED")) for o in (*waiting, running)] == [1, 1, 0]
    log = db_session.query(SecurityLog).filter(SecurityLog.message.like("주문 3건 — %")).one()
    assert log.message.endswith("재단 기본 3장 · 제작 시작 2건")


def test_done_and_release_never_start_production(client):
    """제작 시작은 맡기 · 기본 · 담당 바꾸기 · 일괄 기본만 — 옛 맡음(회차 없는 주문)을 완료 · 맡기 취소해도 그대로."""
    order = make_order(2, run=False)
    cut = make_user("김재단", part="cut")
    now = now_utc_naive()
    for key in order.keys:
        db_session.add(ProductionPartMark(order_id=order.id, drawing_key=key, part="cut", state="NEED",
                                          picked_by_user_id=cut.id, picked_by_name="김재단", picked_at=now,
                                          updated_at=now))
    db_session.commit()
    login(client, cut)
    assert mark(client, order, 0, "cut", "done", "need").get_json()["data"]["run_started"] is False
    assert mark(client, order, 1, "cut", "release", "need").get_json()["data"]["run_started"] is False
    assert current_runs(order.id) == 0
    login(client, make_user("박재단", part="cut"))
    took = mark(client, order, 1, "cut", "take", "none")
    assert took.get_json()["data"]["run_started"] is True and current_runs(order.id) == 1


# --------------------------------------------------------------------------- #
# 표시 줄 모양 · 30초 받아 오기
# --------------------------------------------------------------------------- #
def test_mark_payload_adds_picked_day_and_handover_fields(client):
    order = make_order(1)
    park = _held(client, order)
    login(client, make_user("김민준", part="edge"))
    mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    since = (now_utc_naive() - datetime.timedelta(hours=1)).isoformat()
    marks = client.get("/api/production/part-marks", query_string={"order_ids": str(order.id), "since": since})
    got = marks.get_json()["data"]["marks"][0]
    assert got["picked_day"] == get_today_kst().isoformat() and got["picked_at"].endswith("+00:00")
    assert got["handed_from_name"] == "박엣지" and got["handed_at"]
    for key in ("state", "picked_by_name", "done_by_name", "picked_by_user_id", "done_by_user_id", "word", "tone"):
        assert key in got  # 지금 칸은 그대로


# --------------------------------------------------------------------------- #
# 바뀐 기록 목록 GET /api/production/part-history
# --------------------------------------------------------------------------- #
#: 실측(2026-11-23, SQLite 레인): 로그인 사용자 1 + 이벤트 1(새 이벤트만) · + 이름 1(이름 없는 옛 이벤트). 상한 = 설계서 ≤ 2 + 사용자.
HISTORY_CAP_NEW = 2
HISTORY_CAP_OLD = 3


def test_history_lists_events_with_names_and_filters(client):
    order = make_order(2)
    park = _held(client, order)
    kim = make_user("김민준", part="edge")
    login(client, kim)
    mark(client, order, 0, "edge", "takeover", "need", seen_by=park.id)
    mark(client, order, 0, "edge", "done", "need")
    finish(client, order, 1, "edge")  # 2/2 끝 → 공정 칸 동기화 이벤트(카드)
    login(client, make_user("상담", team="CS"))  # 생산 화면을 보는 직원은 읽는다
    resp, n_new = _count(lambda: client.get(HISTORY, query_string={"order_id": order.id, "part": "edge"}))
    items = resp.get_json()["data"]["items"]
    assert resp.status_code == 200 and n_new <= HISTORY_CAP_NEW, n_new
    assert [(i["kind"], i["by_name"]) for i in items] == [
        ("take", "박엣지"), ("takeover", "김민준"), ("done", "김민준"), ("take", "김민준"), ("done", "김민준"),
        ("step_on", "김민준")]
    assert items[1]["from_name"] == "박엣지" and items[-1]["via"] == "part_marks" and items[0]["at"].endswith("+00:00")
    one = client.get(HISTORY, query_string={"order_id": order.id, "key": order.keys[0]}).get_json()["data"]["items"]
    assert [i["kind"] for i in one] == ["take", "takeover", "done"]  # 장을 거르면 그 장 카드 이벤트만
    sheet = client.get(HISTORY, query_string={"order_id": order.id, "sheet_id": f"{order.keys[1][:-7]}-s1"})
    assert [i["kind"] for i in sheet.get_json()["data"]["items"]] == ["take", "done"]


def test_history_resolves_names_of_old_events_in_one_query(client):
    order = make_order(1)
    login(client, make_user("박반장"))
    client.post(f"/api/orders/{order.id}/production/steps", json={"key": "cut", "done": True})
    for ev in events(order.id, "PRODUCTION_STEP_CHECKED"):  # 3판 전 이벤트 꼴(이름 없음)
        ev.payload = {k: v for k, v in ev.payload.items() if k != "by_name"}
    db_session.commit()
    resp, n_old = _count(lambda: client.get(HISTORY, query_string={"order_id": order.id}))
    assert n_old <= HISTORY_CAP_OLD, n_old
    assert [(i["kind"], i["by_name"], i["via"]) for i in resp.get_json()["data"]["items"]] == [
        ("step_on", "박반장", "sheet")]


def test_history_permissions_and_bad_queries(client):
    order = make_order(1)
    org = PartnerOrg(name="가짜협력사")
    db_session.add(org)
    db_session.commit()
    login(client, make_user("협력직원", team=None, role="PARTNER", partner_org_id=org.id))
    assert client.get(HISTORY, query_string={"order_id": order.id}).status_code == 403
    login(client, make_user("팀없음", team=None))
    assert client.get(HISTORY, query_string={"order_id": order.id}).status_code == 403
    login(client, make_user("가짜생산"))
    for bad in ({"order_id": "x"}, {}, {"order_id": order.id, "part": "paint"}):
        assert client.get(HISTORY, query_string=bad).status_code == 400, bad
    assert client.get(HISTORY, query_string={"order_id": 987654}).get_json()["data"]["items"] == []


# --------------------------------------------------------------------------- #
# 마이그레이션 prodpart_01_handover — 빈 SQLite 에서 실제로 올렸다 내린다(PG 왕복은 tests/postgres/test_migration_chain.py)
# --------------------------------------------------------------------------- #
def _migration():
    spec = importlib.util.spec_from_file_location(
        "prodpart_01_unit", ROOT / "migrations" / "versions" / "prodpart_01_handover.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_handover_migration_upgrade_then_downgrade_on_empty_sqlite():
    module = _migration()
    assert (module.revision, module.down_revision) == ("prodpart_01_handover", "aistaff_00")
    sqlite = create_engine("sqlite://")
    with sqlite.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        conn.execute(text("CREATE TABLE production_part_marks (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL)"))
        module.upgrade()
        cols = {c["name"]: c for c in inspect(conn).get_columns("production_part_marks")}
        assert cols["handed_from_name"]["nullable"] and cols["handed_at"]["nullable"]
        conn.execute(text("INSERT INTO production_part_marks (order_id) VALUES (1)"))  # 기존 줄은 NULL 그대로
        assert conn.execute(text("SELECT handed_from_name, handed_at FROM production_part_marks")).one() == (None, None)
        module.downgrade()
        assert set(c["name"] for c in inspect(conn).get_columns("production_part_marks")) == {"id", "order_id"}


def test_handover_columns_match_model_ddl():
    module = _migration()
    table = ProductionPartMark.__table__
    for name, type_ in module.COLUMNS:
        column = table.c[name]
        assert column.nullable is True and column.server_default is None and column.index is not True
        assert type(column.type) is type(type_) and getattr(column.type, "length", None) == getattr(type_, "length", None)
