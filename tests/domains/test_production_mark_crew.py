"""여러 명이 같이 작업 — 목록 순수 함수 · 판정 · 줄 값 · 마이그레이션(설계서 2026-11-25 multi-holder §4 · §5 · §7-3 · §11 M1).

DB 없이 :mod:`foms.services.production.mark_crew`(목록) · :mod:`~foms.services.production.part_mark_decide`(판정) ·
:func:`~foms.services.production.part_mark_rules.next_mark_values`(줄 값)를 본다. 이름은 모두 지어낸 값이다.

되돌리면 실패: 요약(모두 완료 = DONE) 빼기 · NULL 목록을 요약 칸에서 안 풀기 · 어긋난 목록을 믿기 · 받은 목록 고치기 ·
"외 n" 셈 틀리기 · take → join 넘김 빼기 · 본인 몫만 되돌리기 빼기 · 완료 뒤 시작 취소 받기 · 대신 완료가 반장을 목록에 넣기.
대조군: 한 명짜리 옛 줄은 지금과 같은 모습 · 사람 없는 줄(기본 · 풀어 쓴 완료)은 지금 규칙.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from foms.services.production import mark_crew as mc
from foms.services.production.part_holders import part_holder
from foms.services.production.part_mark_gates import inspect_gate
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_rules import (
    MARK_COLUMNS,
    MarkSnapshot,
    mark_payload,
    next_mark_values,
)
from models import ProductionPartMark

ROOT = pathlib.Path(__file__).resolve().parents[2]
T0 = datetime.datetime(2026, 11, 24, 23, 10)
T1 = T0 + datetime.timedelta(minutes=50)
T2 = T0 + datetime.timedelta(hours=3)
LEE, KIM, PARK, BOSS = 31, 44, 45, 90


def _m(uid, name, at=T0, done_at=None, done_uid=None, done_name=None):
    return mc.member(uid, name, mc.to_iso(at), done_at=mc.to_iso(done_at) if done_at else None,
                     done_uid=done_uid, done_name=done_name)


def _done(uid, name, at=T0, when=T1, by=None, by_name=None):
    return _m(uid, name, at, done_at=when, done_uid=by or uid, done_name=by_name or name)


def _row(crew=None, **fields):
    """표시 줄 모습 — 목록을 주면 요약 칸을 목록에서 채운다(새 코드가 쓴 줄)."""
    base = {column: None for column in MARK_COLUMNS}
    base.update(state="NONE", updated_at=T0)
    if crew is not None:
        base.update(mc.summarize(crew) or {}, holders=crew)
    base.update(fields)
    return SimpleNamespace(**base)


def _decide(row, action, seen, me, *, admin=False, name=None, **extra):
    return decide_mark(MarkSnapshot.from_row(row), action=action, seen=seen, actor_id=me, admin=admin,
                       actor_name=name or f"사람{me}", now=T2, label="재단", **extra)


# --------------------------------------------------------------------------- #
# 요약 · 읽기 정규화(§4-2 · §4-3)
# --------------------------------------------------------------------------- #
def test_summarize_need_done_and_empty():
    assert mc.summarize([]) is None  # 사람 없는 줄 — 상태는 부르는 쪽(기본 · 풀어 쓴 완료 · 안 봄)
    one_left = mc.summarize([_done(LEE, "이시영"), _m(KIM, "김재단", T1)])
    assert (one_left["state"], one_left["picked_by_user_id"], one_left["done_by_user_id"]) == ("NEED", LEE, None)
    assert one_left["picked_at"] == T0
    both = mc.summarize([_done(LEE, "이시영", when=T2), _done(KIM, "김재단", T1, when=T1)])
    assert (both["state"], both["picked_by_name"], both["done_by_name"], both["done_at"]) == ("DONE", "이시영", "이시영", T2)


def test_crew_of_null_column_unfolds_from_summary_columns():
    """옛 한 명짜리 줄(목록 NULL) = 요약 칸에서 푼다 — NEED · DONE + 담당, 그 밖 빈 목록(Q18 ②)."""
    need = _row(state="NEED", picked_by_user_id=LEE, picked_by_name="이시영", picked_at=T0)
    assert [(m["uid"], m["name"], mc.is_done(m)) for m in mc.crew_of(need)] == [(LEE, "이시영", False)]
    done = _row(state="DONE", picked_by_user_id=LEE, picked_by_name="이시영", picked_at=T0, done_by_user_id=BOSS,
                done_by_name="박반장", done_at=T1)
    item = mc.crew_of(done)[0]
    assert mc.is_done(item) and (item["done_uid"], item["done_name"]) == (BOSS, "박반장")
    for state, fields in (("BASIC", {"done_by_name": "김재단"}), ("DONE", {"done_by_name": "박반장"}), ("NONE", {})):
        assert mc.crew_of(_row(state=state, **fields)) == []  # 기본 · 사람 없는 완료 · 안 봄
    assert mc.crew_of(None) == []


def test_crew_of_mismatched_list_loses_to_summary_columns():
    """목록의 요약 ≠ 줄의 요약 칸 = 옛 코드가 마지막으로 쓴 줄 → 요약 칸이 이긴다(§4-3)."""
    crew = [_m(LEE, "이시영"), _m(KIM, "김재단", T1)]
    fresh = _row(crew)
    assert [m["uid"] for m in mc.crew_of(fresh)] == [LEE, KIM]
    taken_over = _row(crew, picked_by_user_id=PARK, picked_by_name="박재단")  # 옛 코드가 담당 바꾸기를 씀
    assert [m["uid"] for m in mc.crew_of(taken_over)] == [PARK]
    released = _row(crew, state="NONE", picked_by_user_id=None, picked_by_name=None)  # 옛 코드가 맡기 취소를 씀
    assert mc.crew_of(released) == []


def test_list_functions_return_new_lists_and_leave_input_alone():
    crew = [_m(LEE, "이시영")]
    snapshot = [dict(m) for m in crew]
    joined = mc.join(crew, KIM, "김재단", T1)
    assert [m["uid"] for m in joined] == [LEE, KIM] and mc.join(joined, KIM, "김재단", T2) == joined  # 두 번 = 그대로
    finished = mc.finish(joined, KIM, by_uid=KIM, by_name="김재단", now=T2)
    assert [mc.share_of(finished, u) for u in (LEE, KIM, PARK)] == ["held", "done", "none"]
    proxied = mc.finish_rest(finished, by_uid=BOSS, by_name="박반장", now=T2)
    assert mc.find(proxied, BOSS) is None and mc.done_names(proxied) == ["박반장", "김재단"]  # 반장은 목록에 안 들어감
    assert [mc.share_of(mc.unfinish(proxied, [KIM]), u) for u in (LEE, KIM)] == ["done", "held"]
    assert [m["uid"] for m in mc.leave(joined, LEE)] == [KIM]
    swapped = mc.swap(joined, LEE, PARK, "박재단", T2)
    assert [m["uid"] for m in swapped] == [PARK, KIM] and swapped[0]["at"] == mc.to_iso(T2)  # 자리 그대로
    assert crew == snapshot  # 받은 목록은 그대로(깊은 사본)


def test_name_line_two_then_others_count():
    assert mc.name_line(["이시영"]) == "이시영"
    assert mc.name_line(["이시영", "김재단"]) == "이시영 · 김재단"
    assert mc.name_line(["이시영", "김재단", "박재단"]) == "이시영 · 김재단 외 1"
    assert mc.name_line(["이시영", "김재단", "박재단", "최재단", "정재단"]) == "이시영 · 김재단 외 3"
    assert mc.name_line([]) == ""


def test_date_row_cell_counts_co_workers_in_others():
    """날짜 줄 칸 아래 = 시작한 때 이른 사람 + "외 n"(같이 작업하는 사람도 센다 — §8-2 29 "이시영 외 2")."""
    sd = {"drawing_current_files": [{"key": "k0"}, {"key": "k1"}], "production": {"steps": []}}
    marks = [_row([_m(LEE, "이시영"), _m(KIM, "김재단", T1)], drawing_key="k0", part="cut"),
             _row([_m(PARK, "박재단", T2)], drawing_key="k1", part="cut")]
    cell = part_holder(sd, marks, "cut", {"key": "cut"}, T2.date())
    assert (cell["kind"], cell["name"], cell["tail"]) == ("held", "이시영", "외 2")
    assert "이시영 작업 중" in cell["aria"] and "함께 하는 사람 김재단, 박재단" in cell["aria"]


# --------------------------------------------------------------------------- #
# 판정(§5 · §7-3)
# --------------------------------------------------------------------------- #
def test_late_take_switches_to_join_with_notice():
    row = _row([_m(LEE, "이시영")])
    decision = _decide(row, "take", "none", KIM, name="김재단")
    assert (decision.kind, decision.action, decision.target, decision.joined_late) == ("apply", "join", "NEED", True)
    assert decision.notice == "이시영이 먼저 시작했어요."
    assert [m["uid"] for m in decision.crew] == [LEE, KIM]
    two = _row([_m(LEE, "이시영"), _m(PARK, "최재단", T1)])
    assert _decide(two, "take", "none", KIM).notice == "이시영 · 최재단이 먼저 시작했어요."
    assert _decide(row, "take", "none", LEE).kind == "same"  # 이미 목록에 있음 = 멱등


def test_take_on_done_or_basic_is_not_switched():
    done = _row([_done(LEE, "이시영")])
    refused = _decide(done, "take", "none", KIM)
    assert (refused.kind, refused.message) == ("conflict", "이시영이 먼저 완료했어요")
    basic = _row(state="BASIC", done_by_user_id=LEE, done_by_name="이시영")
    assert _decide(basic, "take", "none", KIM).message == "이시영이 먼저 기본으로 했어요"


def test_join_on_emptied_row_becomes_take_without_notice():
    emptied = _row(state="NONE")
    decision = _decide(emptied, "join", "need", KIM, name="김재단")
    assert (decision.kind, decision.action, decision.joined_late, decision.notice) == ("apply", "take", False, "")
    done = _decide(_row([_done(LEE, "이시영")]), "join", "need", KIM)
    assert (decision.kind, done.kind, done.code, done.status) == ("apply", "refuse", "JOIN_DONE", 409)


def test_done_waits_for_everyone():
    row = _row([_m(LEE, "이시영"), _m(KIM, "김재단", T1)])
    first = _decide(row, "done", "need", LEE)
    assert (first.target, mc.share_of(first.crew, LEE)) == ("NEED", "done")
    second = _decide(_row(list(first.crew)), "done", "need", KIM)
    assert second.target == "DONE"
    stranger = _decide(row, "done", "need", PARK)  # 목록 밖 파트 계정 — 지금 경합 그대로
    assert (stranger.kind, stranger.message) == ("conflict", "이시영 · 김재단이 먼저 시작했어요.")
    proxy = _decide(row, "done", "need", BOSS, admin=True, name="박반장")  # 대신 완료(Q15)
    assert (proxy.target, proxy.override, mc.find(proxy.crew, BOSS)) == ("DONE", True, None)


def test_undo_own_share_only_and_lead_proxy():
    row = _row([_done(LEE, "이시영"), _done(KIM, "김재단")])
    mine = _decide(row, "undo", "done", KIM)
    assert (mine.target, [mc.share_of(mine.crew, u) for u in (LEE, KIM)]) == ("NEED", ["done", "held"])
    half = _row([_done(LEE, "이시영"), _m(KIM, "김재단")])
    other = _decide(half, "undo", "need", KIM, seen_me="held")  # 내 몫은 작업 중인데 남의 완료를 되돌림(Q3)
    assert (other.kind, other.code, other.status) == ("forbidden", "UNDO_NOT_MINE", 403)
    assert other.message == "내가 완료한 것만 되돌릴 수 있어요. 이시영이 완료한 것은 이시영에게 말해 주세요."
    assert _decide(half, "undo", "need", PARK).code == "UNDO_NOT_MINE"  # 목록 밖 파트 계정도
    assert _decide(half, "undo", "need", KIM, seen_me="done").kind == "same"  # 내 되돌리기를 다시 보냄 = 멱등
    lead = _decide(row, "undo", "done", BOSS, admin=True)  # 반장 대신 되돌리기(판결 3 — 남김)
    assert (lead.target, lead.override) == ("NEED", True)


def test_release_rules():
    row = _row([_m(LEE, "이시영"), _done(KIM, "김재단")])
    left = _decide(row, "release", "need", LEE)
    assert (left.target, left.target_name) == ("DONE", "이시영")  # 남은 사람 모두 완료 = 저절로 완료(Q6)
    after_done = _decide(row, "release", "need", KIM)
    assert (after_done.code, after_done.message) == (
        "RELEASE_AFTER_DONE", "[재단 완료]를 누른 도면은 시작을 취소할 수 없어요. 먼저 [되돌리기]를 눌러 주세요.")
    assert _decide(row, "release", "need", PARK).code == "RELEASE_NOT_HOLDER"
    alone = _decide(_row([_m(LEE, "이시영")]), "release", "need", LEE)
    assert (alone.target, alone.crew) == ("NONE", ())


def test_remove_and_takeover_targets():
    row = _row([_m(LEE, "이시영"), _m(KIM, "김재단", T1)])
    assert _decide(row, "remove", "need", PARK, target_uid=KIM).code == "REMOVE_FORBIDDEN"
    assert _decide(row, "remove", "need", BOSS, admin=True).code == "TARGET_REQUIRED"
    gone = _decide(row, "remove", "need", BOSS, admin=True, target_uid=PARK)
    assert (gone.code, gone.status, gone.target_uid) == ("TARGET_GONE", 409, PARK)
    removed = _decide(row, "remove", "need", BOSS, admin=True, target_uid=KIM)
    assert ([m["uid"] for m in removed.crew], removed.target_name) == ([LEE], "김재단")
    need_pick = _decide(row, "takeover", "need", PARK)
    assert (need_pick.code, need_pick.status, need_pick.message) == ("TARGET_REQUIRED", 400, "누구와 바꿀지 골라 주세요.")
    half = _row([_done(LEE, "이시영"), _m(KIM, "김재단", T1)])
    one_left = _decide(half, "takeover", "need", PARK, name="박재단")  # 고를 사람이 하나 = 고르기 없이(판결 4)
    assert ([m["uid"] for m in one_left.crew], one_left.target_name) == ([LEE, PARK], "김재단")
    assert _decide(half, "takeover", "need", PARK, target_uid=LEE).code == "TARGET_DONE"


def test_check_is_start_plus_done_or_proxy():
    empty = _decide(_row(state="NONE"), "check", "none", BOSS, admin=True, name="박반장")
    assert (empty.target, [m["uid"] for m in empty.crew], empty.proxied) == ("DONE", [BOSS], False)
    busy = _decide(_row([_m(LEE, "이시영")]), "check", "none", BOSS, admin=True)  # 그사이 남이 시작 = 대신 완료(판결 2)
    assert (busy.target, busy.proxied, mc.find(busy.crew, BOSS)) == ("DONE", True, None)
    assert _decide(_row([_done(LEE, "이시영")]), "check", "need", BOSS, admin=True).kind == "same"


def test_seen_me_mismatch_is_conflict_and_old_screen_seen_by_still_compares():
    row = _row([_m(LEE, "이시영"), _m(KIM, "김재단", T1)])
    assert _decide(row, "done", "need", KIM, seen_me="none").kind == "conflict"
    assert _decide(row, "done", "need", KIM, seen_me="held").kind == "apply"
    assert _decide(row, "done", "need", KIM, seen_by=LEE).kind == "apply"  # 옛 화면 = 첫 사람 id
    assert _decide(row, "done", "need", KIM, seen_by=PARK).kind == "conflict"


def test_five_people_have_no_limit():
    crew = [_m(100 + j, f"재단{j}") for j in range(5)]
    decision = _decide(_row(crew), "join", "need", KIM)
    assert decision.kind == "apply" and len(decision.crew) == 6  # 인원 상한 없음(Q9)


def test_one_finished_inspector_blocks_earlier_part_undo_gate():
    """검수 줄에서 완료를 누른 사람이 한 명이라도 있으면 앞 파트 되돌리기를 막는다(사장님 2026-11-25) — 0명이면 된다."""
    def gate(crew=None, **fields):
        marks = [_row(crew, drawing_key="k", part="inspect", **fields)]
        return inspect_gate({}, marks, "k", "cut", "undo")

    half = gate([_m(LEE, "윤검수"), _done(KIM, "강검수")])
    assert (half.code, half.extra["inspected_by"]) == ("INSPECT_DONE_FIRST", "강검수")
    assert gate([_m(LEE, "윤검수"), _m(KIM, "강검수")]) is None  # 시작만 = 된다(음성 대조군)
    assert gate([_done(LEE, "윤검수"), _done(KIM, "강검수")]).extra["inspected_by"] == "윤검수 · 강검수"
    assert gate(state="DONE", done_by_name="박반장").code == "INSPECT_DONE_FIRST"  # 사람 없는 검수 완료(풀어 쓴 완료)
    assert inspect_gate({}, [_row([_done(KIM, "강검수")], drawing_key="k", part="inspect")], "k", "inspect", "undo") is None


# --------------------------------------------------------------------------- #
# 줄 값 · 응답 자료
# --------------------------------------------------------------------------- #
def test_next_values_keep_summary_and_handover_rules():
    row = _row([_m(LEE, "이시영")], handed_from_name="박엣지", handed_at=T0)
    decision = _decide(row, "join", "need", KIM, name="김재단")
    values = next_mark_values(row, order_id=1, drawing_key="k", part="cut", sheet_id=None, target=decision.target,
                              actor_id=KIM, actor_name="김재단", now=T2, action=decision.action, decision=decision)
    assert (values["state"], values["picked_by_user_id"], values["handed_from_name"]) == ("NEED", LEE, "박엣지")
    assert [m["uid"] for m in values["holders"]] == [LEE, KIM]
    release = _decide(_row(values["holders"], handed_from_name="박엣지"), "release", "need", KIM)
    after = next_mark_values(row, order_id=1, drawing_key="k", part="cut", sheet_id=None, target=release.target,
                             actor_id=KIM, actor_name="김재단", now=T2, action=release.action, decision=release)
    assert (after["handed_from_name"], [m["uid"] for m in after["holders"]]) == (None, [LEE])  # 시작 취소는 지운다


def test_basic_and_person_less_done_keep_todays_columns():
    basic = _decide(_row(state="NONE"), "basic", "none", KIM, name="김재단")
    values = next_mark_values(None, order_id=1, drawing_key="k", part="cut", sheet_id=None, target=basic.target,
                              actor_id=KIM, actor_name="김재단", now=T2, action="basic", decision=basic)
    assert (values["state"], values["done_by_name"], values["picked_by_name"], values["holders"]) == ("BASIC", "김재단", None, [])
    expanded = next_mark_values(None, order_id=1, drawing_key="k", part="cut", sheet_id=None, target="DONE",
                                actor_id=BOSS, actor_name="박반장", now=T2, action="done")  # 풀어 쓰기(결정 없음)
    assert (expanded["state"], expanded["done_by_name"], expanded["holders"]) == ("DONE", "박반장", [])


def test_payload_adds_holders_and_counts_and_keeps_one_person_columns():
    payload = mark_payload(_row([_done(LEE, "이시영"), _m(KIM, "김재단", T1)]))
    assert (payload["state"], payload["picked_by_name"], payload["holder_n"], payload["done_n"]) == ("need", "이시영", 2, 1)
    assert [(h["user_id"], h["done"], h["done_name"]) for h in payload["holders"]] == [(LEE, True, "이시영"), (KIM, False, None)]
    assert payload["holders"][0]["picked_day"] == "2026-11-25"  # KST 날(23:10 UTC = 다음 날 08:10 KST)
    old = mark_payload(_row(state="NEED", picked_by_user_id=LEE, picked_by_name="이시영", picked_at=T0))
    assert (old["holder_n"], old["holders"][0]["name"]) == (1, "이시영")  # 옛 줄도 같은 꼴


# --------------------------------------------------------------------------- #
# 마이그레이션 prodpart_02_holders — 빈 SQLite 에서 올렸다 내린다(PG 왕복은 tests/postgres/test_migration_chain.py)
# --------------------------------------------------------------------------- #
def _migration():
    spec = importlib.util.spec_from_file_location("prodpart_02_unit", ROOT / "migrations" / "versions" / "prodpart_02_holders.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_holders_migration_chains_after_lead_unfill_and_round_trips_on_sqlite():
    module = _migration()
    assert (module.revision, module.down_revision) == ("prodpart_02_holders", "prodlead_02")
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        conn.execute(text("CREATE TABLE production_part_marks (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, state VARCHAR(8))"))
        conn.execute(text("INSERT INTO production_part_marks (order_id, state) VALUES (1, 'NEED')"))
        module.upgrade()
        cols = {c["name"]: c for c in inspect(conn).get_columns("production_part_marks")}
        assert cols["holders"]["nullable"]
        assert conn.execute(text("SELECT holders FROM production_part_marks")).scalar() is None  # 옛 줄은 채우지 않는다
        module.downgrade()
        assert {c["name"] for c in inspect(conn).get_columns("production_part_marks")} == {"id", "order_id", "state"}
        module.upgrade()  # 다시 올려도 된다
        assert "holders" in {c["name"] for c in inspect(conn).get_columns("production_part_marks")}


def test_holders_column_matches_model_ddl():
    column = ProductionPartMark.__table__.c.holders
    assert column.nullable is True and column.server_default is None and column.index is not True
    assert type(column.type).__name__ == type(_migration().JSON_TYPE).__name__ == "JSON"
    assert column.type.none_as_null is True  # 파이썬 None = SQL NULL(옛 줄 판정)
