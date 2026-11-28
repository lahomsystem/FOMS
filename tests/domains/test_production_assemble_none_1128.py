"""조립할 것 없는 도면 — [조립 없음](설계서 2026-11-28 흐름 셋 §3 · §5).

사장님 2026-11-28: 단추 이름 = "조립 없음" · 엣지에도 필요한가 = "조립만". 재단 [기본]의 상태 ``BASIC`` 을 조립으로 넓혔다(따로 만들지
않는다) — 끝났는지 판정이 한 함수(``mark_finished``)라 검수 열림 · 제작 완료 · "조립 2/3" · 공정 칸이 같이 맞는다. 글은 조립 말로
("조립 없음" · 다른 파트 줄 "없음"), DB 제약은 "재단 · 조립만"(마이그레이션 ``prodpart_03_basic_parts``).

되돌리면 실패: 조립 ``basic`` 을 400 으로 막기 · 조립 없음 도면에서 검수가 안 열리기 · 제작 완료 판정이 조립 없음을 미완료로 세기 ·
조립 글에 "기본"이 남기 · 엣지 · 검수에 ``BASIC`` 줄이 들어가기 · 마이그레이션 내림이 조립 없음 줄 때문에 실패하기.
대조군: 재단 글 · 재단 쓰기는 한 글자도 안 바뀐다 · 엣지 · 검수는 지금처럼 400 · 조립 미정이면 검수 409.
화면(템플릿 · 판 JS)은 ``test_production_assemble_none_screen_1128.py``. 이름은 모두 지어낸 값이다(최조립 · 한검수 · 박반장 …).
"""
from __future__ import annotations

import datetime
import importlib.util
import io
import pathlib
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from db import db_session, engine
from foms.services.production import part_constants as pc
from foms.services.production.factory_scope import elsewhere_line
from foms.services.production.part_board import _prev_word, other_part_word
from foms.services.production.part_holders import part_holder
from foms.services.production.part_progress import complete_state, mark_finished, part_progress
from foms.services.production.pc_sheet import state_word
from foms.services.production.sheet_step_lines import step_line
from models import ProductionPartMark, SecurityLog
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
    step,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations" / "versions"
PREVIEW = "/api/production/part-marks/cancel-preview"


def _audit(oid: int | None) -> str:
    db_session.expire_all()
    return (db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=oid)
            .order_by(SecurityLog.id.desc()).first().message)


def _rows(oid: int) -> list[ProductionPartMark]:
    db_session.expire_all()
    return db_session.query(ProductionPartMark).filter_by(order_id=oid).all()


def _count(fn):
    seen = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), seen["n"]
    finally:
        event.remove(engine, "before_cursor_execute", _before)


# --------------------------------------------------------------------------- #
# 낱말 한 곳 · 끝났는지 판정
# --------------------------------------------------------------------------- #
def test_words_come_from_one_table_and_cut_words_are_unchanged():
    assert pc.BASIC_ALLOWED_PARTS == ("cut", "assemble") and pc.BASIC_ALLOWED_PART == "cut"
    assert (pc.basic_word("cut"), pc.basic_word("cut", short=True)) == ("기본", "기본")
    assert (pc.basic_word("assemble"), pc.basic_word("assemble", short=True)) == ("조립 없음", "없음")
    assert pc.basic_word("edge") == "기본" and pc.basic_word(None) == "기본"  # 그 처리가 없는 파트는 지금 글(쓰일 길이 없다)
    assert pc.basic_view("cut") == {"word": "기본", "short": "기본", "toward": "기본으로", "ask": "기본으로 처리할까요?", "undo": "기본 취소",
                                    "undo_ask": "기본을 취소할까요?", "unseen": "안 본 도면"}
    assert pc.basic_view("assemble") == {"word": "조립 없음", "short": "없음", "toward": "조립 없음으로", "ask": "조립할 것이 없는 도면인가요?",
                                         "undo": "조립 없음 취소", "undo_ask": "조립 없음을 취소할까요?", "unseen": "미정 도면"}
    assert pc.basic_view("edge") is None and pc.basic_view("inspect") is None  # 사장님 "조립만"
    assert mark_finished("assemble", "BASIC") is True and mark_finished("edge", "BASIC") is False
    assert other_part_word("assemble", "basic") == {"part": "assemble", "label": "조립", "word": "없음", "tone": "basic"}
    assert other_part_word("cut", "basic")["word"] == "기본" and other_part_word("edge", "basic")["word"] == "미정"
    assert elsewhere_line("assemble", "basic", picked=None, done="최조립") == "조립 없음 · 최조립"
    assert elsewhere_line("cut", "basic", picked=None, done="김재단") == "기본 · 김재단"
    assert (state_word("assemble", "basic", None), state_word("cut", "basic", None)) == ("조립 없음", "기본")  # PC 도면 목록 창 상태 칸
    old = SimpleNamespace(part="assemble", state="BASIC", done_by_name="최조립", picked_by_name=None, picked_by_user_id=None,
                          done_by_user_id=7, updated_by_user_id=7)
    assert _prev_word(old) == "조립 없음(최조립)"  # 바뀐 도면의 전 판 글


# --------------------------------------------------------------------------- #
# 쓰기 API — 한 장
# --------------------------------------------------------------------------- #
def test_assemble_account_marks_none_and_cancels_it(client):
    order = make_order(2)
    choi = make_user("최조립", part="assemble")
    login(client, choi)
    resp = mark(client, order, 0, "assemble", "basic", "none")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert (data["changed"], data["mark"]["state"], data["mark"]["done_by_name"], data["mark"]["holders"]) == (True, "basic", "최조립", [])
    saved = row(order.id, order.keys[0], "assemble")
    assert (saved.state, saved.done_by_user_id, saved.done_by_name, saved.picked_by_user_id) == ("BASIC", choi.id, "최조립", None)
    assert _audit(order.id).endswith("조립 안 고름 → 조립 없음")
    again = mark(client, order, 0, "assemble", "basic", "none")
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False  # 같은 사람이 두 번 = 멱등
    undo = mark(client, order, 0, "assemble", "undo", "basic")
    assert undo.status_code == 200 and row(order.id, order.keys[0], "assemble").state == "NONE"
    assert _audit(order.id).endswith("조립 조립 없음 → 안 고름")
    items = client.get(f"{HISTORY}?order_id={order.id}&part=assemble").get_json()["data"]["items"]
    assert [(i["kind"], i["word"], i["by_name"]) for i in items] == [("basic", "조립 없음", "최조립"), ("undo", "조립 없음 취소", "최조립")]


def test_edge_and_inspect_have_no_such_press_and_cut_is_unchanged(client):
    order = make_order(1)
    login(client, make_user("박반장", lead=True))
    for part in ("edge", "inspect"):
        resp = mark(client, order, 0, part, "basic", "none")
        assert (resp.status_code, code(resp), resp.get_json()["error"]) == (400, "BASIC_NOT_ALLOWED", "이 파트에는 없는 처리예요."), part
        bulk = client.post(BULK, json={"part": part, "seen": "none", "items": [{"order_id": order.id, "drawing_key": order.keys[0]}]})
        assert (bulk.status_code, code(bulk)) == (400, "BASIC_NOT_ALLOWED"), part
    assert _rows(order.id) == []
    login(client, make_user("김재단", part="cut"))  # 대조군 — 재단 기본은 글 · 줄 · 기록 낱말이 그대로
    assert mark(client, order, 0, "cut", "basic", "none").status_code == 200
    assert "생산 파트 작업: 재단 안 봄 → 기본" in _audit(order.id)
    assert mark(client, order, 0, "cut", "undo", "basic").status_code == 200
    items = client.get(f"{HISTORY}?order_id={order.id}&part=cut").get_json()["data"]["items"]
    assert [(i["kind"], i["word"]) for i in items if i["kind"] in ("basic", "undo")] == [("basic", None), ("undo", None)]  # 재단은 화면 낱말 표 그대로


def test_cancel_rules_and_refusal_words_say_assemble_none(client):
    order = make_order(3)
    choi, oh, lead = make_user("최조립", part="assemble"), make_user("오조립", part="assemble"), make_user("박반장", lead=True)
    login(client, choi)
    for j in (0, 1):
        assert mark(client, order, j, "assemble", "basic", "none").status_code == 200
    login(client, oh)
    late = mark(client, order, 0, "assemble", "take", "none")  # 같은 '미정' 화면을 보고 늦게 누름
    assert (late.status_code, code(late), late.get_json()["error"]) == (409, "MARK_CONFLICT", "최조립이 먼저 조립 없음으로 했어요")
    stale = mark(client, order, 0, "assemble", "release", "need", seen_me="held")
    assert stale.get_json()["error"] == "그사이 최조립이 조립 없음으로 했어요. 더 할 일은 없어요."
    theirs = mark(client, order, 0, "assemble", "undo", "basic")  # 남의 것 취소 — 파트 계정은 못 한다
    assert (theirs.status_code, code(theirs), theirs.get_json()["error"]) == (409, "MARK_CONFLICT", "최조립이 먼저 조립 없음으로 했어요")
    login(client, lead)  # 반장 · 관리자는 된다(재단 기본과 같은 규칙)
    assert mark(client, order, 0, "assemble", "undo", "basic").status_code == 200
    assert _audit(order.id).endswith("조립 조립 없음 → 안 고름 (대신 처리)")
    for who, part in ((make_user("김재단", part="cut"), "cut"), (make_user("박엣지", part="edge"), "edge")):
        login(client, who)
        assert finish(client, order, 1, part).status_code == 200
    login(client, make_user("한검수", part="inspect"))
    assert finish(client, order, 1, "inspect").status_code == 200  # 도면 2 = 조립 없음 → 검수 완료
    login(client, choi)
    blocked = mark(client, order, 1, "assemble", "undo", "basic")
    assert (blocked.status_code, code(blocked)) == (409, "INSPECT_DONE_FIRST")
    assert blocked.get_json()["error"] == ("한검수가 이 장 검수를 완료했어요. 조립 없음을 취소하려면 한검수에게 검수 완료부터 취소해 달라고 해 주세요.")
    patch_sd(order.id, hold={"active": True, "reason": "자재 기다림"})
    assert code(mark(client, order, 2, "assemble", "basic", "none")) == "HOLD_ACTIVE"  # 보류는 지금 문 그대로


# --------------------------------------------------------------------------- #
# 이어지는 판정 — 검수 열림 · 제작 완료 · "조립 2/3" · 공정 칸 · 제작 시작
# --------------------------------------------------------------------------- #
def test_none_opens_inspect_and_counts_for_completion(client):
    order = make_order(1)
    people = {p: make_user(n, part=p) for p, n in (("cut", "김재단"), ("edge", "박엣지"), ("assemble", "최조립"), ("inspect", "한검수"))}
    for part in ("cut", "edge"):
        login(client, people[part])
        assert finish(client, order, 0, part).status_code == 200
    login(client, people["inspect"])
    early = mark(client, order, 0, "inspect", "take", "none")  # 대조군 — 조립이 미정이면 검수는 기다린다
    assert (early.status_code, code(early)) == (409, "INSPECT_NOT_READY")
    assert early.get_json()["error"] == "아직 검수할 수 없어요. 조립(담당 미정)이 미완료예요. 완료되면 검수할 수 있어요."
    login(client, people["assemble"])
    none = mark(client, order, 0, "assemble", "basic", "none").get_json()["data"]
    assert none["order_step"] == {"order_id": order.id, "key": "assemble", "done": True}  # 공정 칸도 같이 켜진다
    assert (step(order.id, "assemble")["done"], step(order.id, "assemble")["by_name"]) == (True, "최조립")
    login(client, people["inspect"])
    assert mark(client, order, 0, "inspect", "take", "none").status_code == 200
    done = mark(client, order, 0, "inspect", "done", "need").get_json()["data"]
    assert done["order_ready"] == {"order_id": order.id}  # "제작 완료할까요?"
    sd, marks = fresh(order.id).structured_data, _rows(order.id)
    assert complete_state(sd, marks)["ready"] is True
    assert client.post(f"/api/orders/{order.id}/production/complete", json={}).status_code == 200


def test_progress_lines_count_none_as_finished():
    today = datetime.date(2026, 11, 28)
    sd = {"drawing_current_files": [{"key": f"k{j}", "sheet_id": f"s{j}"} for j in range(3)], "production": {"steps": []}}

    def mk(key, state, name=None):
        return SimpleNamespace(order_id=1, drawing_key=key, part="assemble", state=state, picked_by_user_id=None, picked_by_name=None,
                               picked_at=None, done_by_user_id=7 if name else None, done_by_name=name,
                               done_at=datetime.datetime(2026, 11, 28, 0, 40) if name else None, updated_by_user_id=7,
                               updated_at=None, handed_from_name=None, handed_at=None, holders=None, sheet_id=None)

    two = [mk("k0", "DONE", "오조립"), mk("k1", "BASIC", "최조립")]
    progress = part_progress(sd, two, "assemble")
    assert (progress["done_n"], progress["total_n"], progress["done"]) == (2, 3, False)  # "조립 2/3"(완료 1 + 조립 없음 1)
    assert step_line(sd, two, "assemble", today)["text"] == "조립 2/3 완료 · 조립 없음 1장 · 미정"
    full = [mk("k0", "BASIC", "최조립"), mk("k1", "BASIC", "최조립"), mk("k2", "DONE", "오조립")]
    line = step_line(sd, full, "assemble", today)
    assert line["done"] is True and line["text"].startswith("조립 완료 · 조립 없음 2장 · 오조립 ")
    cell = part_holder(sd, [mk(f"k{j}", "BASIC", "최조립") for j in range(3)], "assemble", {}, today)  # 날짜 줄 조립 칸 — 모두 조립 없음
    assert (cell["kind"], cell["name"], cell["aria"]) == ("done", "최조립", "조립 완료 · 최조립")  # 칸 아래 이름 = 누른 사람(재단 기본과 같다)
    cut = [SimpleNamespace(**{**vars(mk(f"k{j}", "BASIC", "김재단")), "part": "cut"}) for j in range(3)]
    assert step_line(sd, cut, "cut", today)["text"].startswith("재단 완료 · 기본 3장")  # 대조군 — 재단 글 그대로
    edge = [SimpleNamespace(**{**vars(mk("k0", "BASIC", "박엣지")), "part": "edge"})]  # 생길 길이 없는 값 — 끝으로 세지 않는다
    assert part_progress(sd, edge, "edge")["done_n"] == 0


def test_first_press_starts_production_and_its_cancel_rolls_it_back(client):
    order = make_order(2, run=False)
    choi = make_user("최조립", part="assemble")
    login(client, choi)
    first = mark(client, order, 0, "assemble", "basic", "none").get_json()["data"]
    assert first["run_started"] is True and current_runs(order.id) == 1
    assert _audit(order.id).endswith("조립 안 고름 → 조립 없음 · 제작 시작")
    query = {"order_id": order.id, "drawing_key": order.keys[0], "part": "assemble", "action": "undo", "seen": "basic", "seen_me": "none"}
    assert client.get(PREVIEW, query_string=query).get_json()["data"] == {"run_cancelled": True}  # 창에 미리 알린다
    undone = mark(client, order, 0, "assemble", "undo", "basic", seen_me="none", seen_cancel=True).get_json()["data"]
    assert undone["run_cancelled"] is True and current_runs(order.id) == 0


# --------------------------------------------------------------------------- #
# 일괄 — [남은 N장 모두 조립 없음]
# --------------------------------------------------------------------------- #
def test_bulk_none_is_partial_and_costs_what_cut_costs(client):
    order = make_order(4)
    choi, oh = make_user("최조립", part="assemble"), make_user("오조립", part="assemble")
    login(client, oh)
    assert mark(client, order, 3, "assemble", "take", "none").status_code == 200  # 도면 4 는 오조립이 작업 중
    login(client, choi)
    items = [{"order_id": order.id, "drawing_key": k} for k in order.keys]
    data = client.post(BULK, json={"part": "assemble", "seen": "none", "items": items}).get_json()["data"]
    assert [(a["part"], a["state"], a["changed"]) for a in data["applied"]] == [("assemble", "basic", True)] * 3
    assert [(s["reason"], s["error"], s["mark"]["part"]) for s in data["skipped"]] == [("MARK_CONFLICT", "오조립이 먼저 시작했어요.", "assemble")]
    assert [r.state for r in sorted(_rows(order.id), key=lambda r: r.drawing_key)] == ["BASIC", "BASIC", "BASIC", "NEED"]
    assert _audit(order.id).endswith("조립 없음 3장")
    assert all(e.payload["part"] == "assemble" for e in events(order.id, "PRODUCTION_PART_MARKED"))
    bad = client.post(BULK, json={"part": "assemble", "seen": "need", "items": items})
    assert (code(bad), bad.get_json()["error"]) == ("BAD_REQUEST", "안 본 도면만 한 번에 조립 없음으로 할 수 있어요.")

    def _bulk(part: str, who):
        orders = [make_order(6) for _ in range(3)]
        login(client, who)
        body = {"part": part, "seen": "none", "items": [{"order_id": o.id, "drawing_key": o.keys[j]} for o in orders for j in range(5)]}
        client.get(f"{HISTORY}?order_id={orders[0].id}")  # warmup(로그인 사용자 읽기 등)
        resp, n = _count(lambda: client.post(BULK, json=body))
        assert len(resp.get_json()["data"]["applied"]) == 15
        return n

    assert _bulk("assemble", choi) == _bulk("cut", make_user("김재단", part="cut"))  # 쿼리 수는 재단 일괄과 같다(장 수와 무관)
    db_session.expire_all()
    many = [m.message for m in db_session.query(SecurityLog).filter(SecurityLog.message.like("주문 3건 — %")).order_by(SecurityLog.id)]
    assert many[-2:] == ["주문 3건 — 생산 파트 작업: 조립 없음 15장", "주문 3건 — 생산 파트 작업: 재단 기본 15장"]  # 감사는 요청마다 한 줄


# --------------------------------------------------------------------------- #
# DB — 모델 제약 · 마이그레이션(메모리 SQLite 왕복 + PG 가 받을 글)
# --------------------------------------------------------------------------- #
def _module(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_unit", VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_lets_assemble_none_in_and_keeps_edge_inspect_out(app):
    order = make_order(1)
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[0], part="assemble", state="BASIC"))
    db_session.commit()
    for part in ("edge", "inspect"):
        db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[0], part=part, state="BASIC"))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()
    checks = {c.name: str(c.sqltext) for c in ProductionPartMark.__table__.constraints if c.name and "basic" in c.name}
    module = _module("prodpart_03_basic_parts")
    assert checks == {module.NEW_CHECK: module.NEW_CHECK_SQL} == {
        "ck_production_part_marks_basic_part": "state <> 'BASIC' OR part IN ('cut', 'assemble')"}


def test_migration_chains_after_holders_and_stays_one_head():
    module = _module("prodpart_03_basic_parts")
    assert (module.revision, module.down_revision) == ("prodpart_03_basic_parts", "prodpart_02_holders")
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    assert ScriptDirectory.from_config(config).get_heads() == ["prodpart_03_basic_parts"]
    assert "import models" not in (VERSIONS / "prodpart_03_basic_parts.py").read_text(encoding="utf-8")  # 상수 동결


def _old_table(op, m00) -> None:
    """``prodpart_00`` 이 만든 표 그대로(사용자 CHECK ALTER 는 SQLite 가 못 받아 표 만들기만 같은 글로)."""
    op.create_table(
        m00.TABLE,
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drawing_key", sa.String(length=500), nullable=False),
        sa.Column("sheet_id", sa.String(length=64), nullable=True),
        sa.Column("part", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=8), nullable=False),
        *[m00._user_fk_column(name) for name in ("picked_by_user_id", "done_by_user_id", "updated_by_user_id")],
        *[sa.Column(name, sa.String(length=120), nullable=True) for name in ("picked_by_name", "done_by_name")],
        *[sa.Column(name, sa.DateTime(), nullable=True) for name in ("picked_at", "done_at")],
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "drawing_key", "part", name=m00.MARKS_UNIQUE),
        sa.CheckConstraint(m00.MARKS_PART_CHECK_SQL, name=m00.MARKS_PART_CHECK),
        sa.CheckConstraint(m00.MARKS_STATE_CHECK_SQL, name=m00.MARKS_STATE_CHECK),
        sa.CheckConstraint(m00.MARKS_BASIC_CHECK_SQL, name=m00.MARKS_BASIC_CHECK),
    )


def test_migration_round_trip_on_sqlite_and_postgres_sql():
    m00, m01, m02, m03 = (_module(n) for n in ("prodpart_00_production_part_marks", "prodpart_01_handover", "prodpart_02_holders",
                                                "prodpart_03_basic_parts"))
    insert = "INSERT INTO production_part_marks (order_id, drawing_key, part, state, done_by_name) VALUES (1, :key, :part, 'BASIC', :who)"

    def checks(conn) -> dict:
        return {c["name"]: c["sqltext"] for c in inspect(conn).get_check_constraints(m00.TABLE)}

    def refused(conn, part: str) -> bool:
        try:
            with conn.begin_nested():
                conn.execute(text(insert), {"key": f"x-{part}", "part": part, "who": None})
        except IntegrityError:
            return True
        return False

    lite = create_engine("sqlite://")
    with lite.begin() as conn, Operations.context(MigrationContext.configure(conn)) as op:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO orders VALUES (1)"))
        _old_table(op, m00)
        m01.upgrade()
        m02.upgrade()
        columns = [(c["name"], str(c["type"]), c["nullable"]) for c in inspect(conn).get_columns(m00.TABLE)]
        conn.execute(text(insert), {"key": "a", "part": "cut", "who": "김재단"})
        assert refused(conn, "assemble") is True  # 옛 제약 = 재단만
        m03.upgrade()
        assert checks(conn) == {m03.NEW_CHECK: m03.NEW_CHECK_SQL, m00.MARKS_PART_CHECK: m00.MARKS_PART_CHECK_SQL,
                                m00.MARKS_STATE_CHECK: m00.MARKS_STATE_CHECK_SQL}
        conn.execute(text(insert), {"key": "a", "part": "assemble", "who": "최조립"})  # 조립 없음 줄이 들어간다
        assert [refused(conn, part) for part in ("edge", "inspect")] == [True, True]  # 사장님 "조립만" — DB 도 지킨다
        assert [(c["name"], str(c["type"]), c["nullable"]) for c in inspect(conn).get_columns(m00.TABLE)] == columns  # 칸 그대로
        assert [u["name"] for u in inspect(conn).get_unique_constraints(m00.TABLE)] == [m00.MARKS_UNIQUE]
        assert len(inspect(conn).get_foreign_keys(m00.TABLE)) == 4
        m03.downgrade()  # 조립 없음 줄이 있어도 내려간다 — 그 줄은 완료로(끝난 것은 끝난 채)
        assert checks(conn)[m00.MARKS_BASIC_CHECK] == m00.MARKS_BASIC_CHECK_SQL and m03.NEW_CHECK not in checks(conn)
        assert conn.execute(text("SELECT part, state, done_by_name FROM production_part_marks ORDER BY part")).all() == [
            ("assemble", "DONE", "최조립"), ("cut", "BASIC", "김재단")]
        assert refused(conn, "assemble") is True
        m03.upgrade()  # 다시 올려도 된다
        assert m03.NEW_CHECK in checks(conn)
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        m03.upgrade()
        m03.downgrade()
    assert [line for line in buffer.getvalue().splitlines() if line.strip()] == [
        "ALTER TABLE production_part_marks DROP CONSTRAINT ck_production_part_marks_basic_cut;",
        "ALTER TABLE production_part_marks ADD CONSTRAINT ck_production_part_marks_basic_part CHECK (state <> 'BASIC' OR part IN ('cut', 'assemble'));",
        "UPDATE production_part_marks SET state = 'DONE' WHERE state = 'BASIC' AND part <> 'cut';",
        "ALTER TABLE production_part_marks DROP CONSTRAINT ck_production_part_marks_basic_part;",
        "ALTER TABLE production_part_marks ADD CONSTRAINT ck_production_part_marks_basic_cut CHECK (state <> 'BASIC' OR part = 'cut');",
    ]
