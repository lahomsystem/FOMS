"""통째 작업에서 막힌 도면만 빼고 처리(사장님 답 "고치는 도면만 빼고 처리" — 설계서 2026-11-25 §3-6 ① · C4 · D1 검토 판결 A ~ E · G).

반장 · 관리자가 카드를 한 장도 안 쓴 파트의 공정 칸을 켤 때 그 주문에 도면별로 막힌 장이 1장 이상이면 칸은 켜지 않고, 막히지 않은
지금 도면 **전부**(공장을 가리지 않음 — 막힌 도면이 없으면 반장 한 번에 두 공장 장이 모두 완료되는 지금 규칙과 같은 범위)를 ``DONE``
으로 **한 문장**에 쓴다(이미 끝 · 기본 줄은 그대로, 같은 key 두 번이어도 줄은 하나). 장마다 카드와 같은 이벤트
``PRODUCTION_PART_MARKED``(``via: 'step_expand'``) · 카드 쓰기와 같은 감사 줄 하나. 공정 칸 이벤트는 동기화가 칸을 정말 켤 때만.
응답 ``data.expanded``(``part · part_label · done_n · total_n · skipped_numbers · tail · hold · note``). 막힌 장뿐이면 409.
화면: 확인 창 본문 "이 주문의 도면 3장 중 2장이 재단 완료로 처리돼요. 도면 2는 고치는 중이라 빼요."(작업 시트 · '내 공정' · PC 창) ·
'내 공정' [끝] 뒤 알림 "도면 3장 중 2장을 재단 완료로 처리했어요. 도면 2는 고치는 중이라 뺐어요."(되돌리기 없음) · 남은 장이 고치는
도면뿐인 공정 줄은 [끝] 자리에 "도면 2 고치는 중"(폰 · 가로 판 · PC 줄, [끝]이 없는 사람도) — 그 줄도 다음 공정 '곧 올 것'에는 남는다.
둘째 판: 알림 글은 [되돌리기]와 같은 8초 시계로 지운다 · 검수 풀어 쓰기는 장마다 카드 검수 문(준비 안 된 장이 있으면 쓰기 0 · 409).

되돌리면 실패: 막힌 장까지 완료 · 칸이 켜짐 · 기본 줄을 덮음 · 누른 사람 공장 장만 씀 · 장마다 INSERT · 칸이 꺼진 채 ``done: True`` 이벤트 ·
되돌리기가 남음 · 다시 누르면 "도면 1장이 미완료예요". 대조군: 막힌 도면 없는 주문은 전과 똑같이(섞인 주문도 1공장 반장 한 번에 칸 켬).
이름은 지어낸 값, 날짜는 오늘(KST)에서 센다.

2026-11-27 사장님 "도면 두 장 이상이면 막기": 확정 도면이 2장 이상인 주문은 공정 칸 켜기 자체가 409 ``STEP_PER_SHEET``(누구든) — 막힌 장을
빼고 풀어 쓰는 통째 작업(①)은 공정 칸 길에서 더는 일어나지 않는다(도면 1장 주문은 막힌 장이 있으면 그 한 장이 막힌 것이라 '도면 고치는 중'
거절). 여기 시험은 그 거절(쓰기 · 이벤트 · 버전 0)을 지키고, 풀어 쓰기 함수 자체(② 도면 고쳐 보냄 길이 부른다)와 남은 장이 고치는 도면뿐인
줄의 [끝] 자리(카드로 만든 같은 상태)는 그대로 지킨다. 본뜻이 통째 완료 자체인 대조군은 도면 1장 주문으로.
"""
from __future__ import annotations

import copy
import html as html_lib
import json
import re
import time

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from db import db_session, engine
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders import drawing_fix as fx
from foms.services.production.part_mark_gates import (
    DRAWING_REVISING,
    PART_USES_CARDS,
    REVISING_MESSAGE,
    STEP_PER_SHEET,
)
from foms.services.production.part_progress import STEP_PER_SHEET_MESSAGE
from foms.services.production.pc_view import EDIT_COOKIE
from foms.services.production import step_expand
from foms.services.production.step_expand import VIA_STEP_EXPAND, expand_hand_step
from models import Order, ProductionPartMark, SecurityLog
from tests.domains.test_production_my_steps_confirm import PHONE
from tests.support.production_factory_seed import factory_user, mixed_order, put_mark
from tests.support.production_home_step_panel_seed import HOME, TABLET, add_order, get_html, set_cookies
from tests.support.production_home_step_panel_seed import login as home_login
from tests.support.production_part_claim_seed import check_step, code, events, finish, fresh, login, make_order, make_user, step
from tests.support.production_steps_read import steps_read

PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
FIX = {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}
ASK = "이 주문의 도면 3장 중 2장이 재단 완료로 처리돼요. 도면 2는 수정 중이라 빼요."
DONE = "도면 3장 중 2장을 재단 완료로 처리했어요. 도면 2는 수정 중이라 뺐어요."


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _fixing(oid: int, *indexes: int) -> None:
    """도면팀 [수정 시작]을 자료로 직접 심는다(N1 은 D3 몫)."""
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_fix"] = {"fixing": {fx.fix_ident(sd["drawing_current_files"][j]): dict(FIX, no=j + 1) for j in indexes}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _unfix(oid: int) -> None:
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd.pop("drawing_fix", None)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _marks(oid: int) -> dict[tuple[str, str], ProductionPartMark]:
    db_session.expire_all()
    return {(m.drawing_key, m.part): m for m in db_session.query(ProductionPartMark).filter_by(order_id=oid)}


def _done_cards(oid: int, *indexes: int, part: str = "cut") -> None:
    """장 ``indexes`` 를 그 파트 카드로 완료해 둔다(옛 풀어 쓰기가 남기던 것과 같은 상태 — 남은 장이 고치는 도면뿐인 줄 만들기)."""
    keys = [f["key"] for f in db_session.get(Order, oid).structured_data["drawing_current_files"]]
    for j in indexes:
        db_session.add(ProductionPartMark(order_id=oid, drawing_key=keys[j], part=part, state="DONE", done_by_name="가짜반장"))
    db_session.commit()


def _refused_per_sheet(res, oid: int, version: int) -> None:
    """도면 여러 장 주문의 통째 켜기 거절 — 409 STEP_PER_SHEET · 글 그대로 · 칸 · 표시 줄 · 이벤트 · 감사 · 버전 0."""
    body = res.get_json()
    assert res.status_code == 409 and body["data"]["code"] == STEP_PER_SHEET and body["error"] == STEP_PER_SHEET_MESSAGE, body
    assert "expanded" not in body["data"] and _marks(oid) == {} and fresh(oid).mutation_version == version
    assert events(oid, "PRODUCTION_PART_MARKED") == [] and events(oid, "PRODUCTION_STEP_CHECKED") == []
    assert _audits(oid, "PRODUCTION_STEP_CHECKED") == [] and _audits(oid, "PRODUCTION_PART_MARKED") == []


def _audits(oid: int, action: str) -> list[SecurityLog]:
    db_session.expire_all()
    return db_session.query(SecurityLog).filter_by(target_id=oid, action=action).all()


def _insert_count(fn):
    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO PRODUCTION_PART_MARKS"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), len(seen)
    finally:
        event.remove(engine, "before_cursor_execute", _before)


# --------------------------------------------------------------------------- #
# 쓰기(C4)
# --------------------------------------------------------------------------- #
def test_control_mixed_order_without_block_turns_on_with_one_first_factory_lead(client):
    """판결 A 대조군이던 것 — 막힌 도면 없는 섞인 주문(도면 3장)도 이제 1공장 반장 한 번에 칸을 못 켠다(사장님 2026-11-27, 409
    STEP_PER_SHEET · 쓰기 0). 도면 0장 주문은 지금처럼 켜진다(표시 줄 0 · 감사 줄 하나 — 옛 대조군 도면 1장은 사장님 2026-11-27 "도면이 주, 작업 시트는 보기" 뒤로 409)."""
    seed = mixed_order(3, f2=(2,))
    login(client, factory_user("일공장반장", lead=True))
    version = fresh(seed.id).mutation_version
    _refused_per_sheet(check_step(client, seed.id, "cut", True), seed.id, version)
    assert step(seed.id, "cut")["done"] is False
    assert code(check_step(client, make_order(1).id, "cut", True)) == STEP_PER_SHEET
    one = make_order(0)
    res = check_step(client, one.id, "cut", True)
    assert res.status_code == 200 and "expanded" not in res.get_json()["data"] and "fix" not in res.get_json()["data"]
    assert step(one.id, "cut")["done"] is True and _marks(one.id) == {}
    assert len(_audits(one.id, "PRODUCTION_STEP_CHECKED")) == 1  # 지금 감사 줄 그대로


def test_whole_step_skips_the_blocked_drawing_marks_each_like_a_card_in_one_statement(client):
    """막힌 도면이 있는 도면 3장 주문 — 확인 창 재료(fix)는 그대로 실리지만 통째 켜기는 거절(풀어 쓰기 0, 사장님 2026-11-27). 막힘이
    풀린 뒤 도면을 한 장씩 완료하면 마지막 장에서 동기화가 칸을 켠다 — 그때만 칸 이벤트 done: True."""
    seed = make_order(3)
    _fixing(seed.id, 1)
    boss = make_user("가짜반장", lead=True)
    login(client, boss)
    info = steps_read(client, seed.id)
    assert info["fix"] == {"done": 2, "numbers": [2], "tail": "도면 2는 수정 중이라 빼요."} and info["sheets"] == 3
    assert info["per_sheet"] == STEP_PER_SHEET_MESSAGE  # 작업 시트가 요청 없이 보이는 글
    assert fx.expand_confirm_body(info["sheets"], info["fix"]["done"], "재단", info["fix"]["numbers"]) == ASK
    assert fx.expand_done_text(3, 2, "재단", [2]) == DONE
    version = fresh(seed.id).mutation_version
    res, inserts = _insert_count(lambda: check_step(client, seed.id, "cut", True))
    _refused_per_sheet(res, seed.id, version)
    assert inserts == 0 and step(seed.id, "cut")["done"] is False
    _unfix(seed.id)
    login(client, make_user("가짜재단", part="cut"))
    for j in range(3):
        assert finish(client, seed, j, "cut").status_code == 200
        assert step(seed.id, "cut")["done"] is (j == 2)  # 마지막 장에서만 칸이 켜진다
    assert [e.payload["done"] for e in events(seed.id, "PRODUCTION_STEP_CHECKED")] == [True]


def test_mixed_order_expands_every_factory_so_the_other_lead_is_not_left_out(client):
    """판결 A 이던 것 — 막힌 도면이 있는 섞인 주문(도면 4장)의 통째 켜기는 두 공장 반장 모두 409 STEP_PER_SHEET(사장님 2026-11-27)."""
    seed = mixed_order(4, f2=(2, 3))  # 도면 3 · 4 = 2공장
    _fixing(seed.id, 0)  # 도면 1(1공장) 고치는 중
    login(client, factory_user("일공장반장", lead=True))
    assert steps_read(client, seed.id)["fix"] == {
        "done": 3, "numbers": [1], "tail": "도면 1은 수정 중이라 빼요."}
    version = fresh(seed.id).mutation_version
    _refused_per_sheet(check_step(client, seed.id, "edge", True), seed.id, version)  # 도면 4장 = 통째 켜기 거절(사장님 2026-11-27)
    login(client, factory_user("이공장반장", factory=2, lead=True))
    _refused_per_sheet(check_step(client, seed.id, "edge", True), seed.id, version)  # 2공장 반장도 같다(누구든)
    left = steps_read(client, seed.id)["parts"]["edge"]
    assert (left["uses_cards"], left["left_n"]) == (False, 4)  # 아무 장도 안 썼다 — 도면 화면에서 한 장씩


def test_expand_keeps_finished_rows_keeps_the_holder_and_writes_each_key_once(client):
    seed = make_order(3)
    kim, park = factory_user("김재단", part="cut"), factory_user("박재단", part="cut")
    put_mark(seed, 0, "cut", "BASIC", kim)
    put_mark(seed, 1, "cut", "NEED", park)
    boss = make_user("가짜반장", lead=True)
    order = fresh(seed.id)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_current_files"].append(dict(sd["drawing_current_files"][2]))  # 같은 key 두 번(판결 G — PG ON CONFLICT 두 번 거절)
    marks = list(db_session.query(ProductionPartMark).filter_by(order_id=seed.id))
    put_mark(seed, 2, "cut", "DONE", kim)  # 읽은 뒤 그사이 누가 끝냄(낡은 읽기) — 한 문장이 덮지 않는다(WHERE)
    writes = expand_hand_step(db_session, order, sd, marks, "cut", exclude_keys=(), user=SimpleUser(boss.id, boss.name))
    db_session.commit()
    assert [w.values["drawing_key"] for w in writes] == [seed.keys[1], seed.keys[2]]  # 기본 장 빼고 · key 마다 하나
    assert writes[0].event["payload"]["override"] is True and writes[0].event["payload"]["holder_name"] == "박재단"  # 남의 담당 = 대신
    rows = _marks(seed.id)
    basic, need, done = (rows[(seed.keys[j], "cut")] for j in range(3))
    assert (basic.state, basic.done_by_name) == ("BASIC", "김재단")  # 재단 기본 그대로(설계서 §12)
    assert (need.state, need.picked_by_name, need.done_by_name) == ("DONE", "박재단", "가짜반장")  # 맡은 사람은 남는다
    assert (done.state, done.done_by_name) == ("DONE", "김재단")  # 이미 끝 = 덮지 않음
    second = expand_hand_step(db_session, order, sd, [], "edge", exclude_keys=(seed.keys[0],), user=SimpleUser(boss.id, boss.name),
                              done_by_name="박반장", done_at=now_utc_naive())  # ② 손 처리 이름 · 칸 시각(D2 가 부르는 꼴)
    db_session.commit()
    assert [w.values["drawing_key"] for w in second] == [seed.keys[1], seed.keys[2]]
    assert _marks(seed.id)[(seed.keys[1], "edge")].done_by_name == "박반장"


class SimpleUser:
    """쓰는 사람(이미 읽은 행의 값만)."""

    def __init__(self, uid: int, name: str) -> None:
        self.id, self.name, self.username = uid, name, name


def test_duplicate_key_order_expands_through_the_api(client, monkeypatch):
    """판결 G 이던 것 — 같은 key 가 지금 도면에 두 번인 주문도 장 수는 줄 수(3)로 세어 통째 켜기 거절(사장님 2026-11-27) — 풀어 쓰는
    문장이 아예 없다. 한 문장의 값 줄 key 마다 하나는 :func:`expand_hand_step` 직접 시험(위)이 지킨다."""
    sent: list[list[str]] = []
    real = step_expand._upsert_marks
    monkeypatch.setattr(step_expand, "_upsert_marks", lambda db, values: (sent.append([v["drawing_key"] for v in values]),
                                                                          real(db, values))[1])
    seed = make_order(2)
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_current_files"] = [sd["drawing_current_files"][0], dict(sd["drawing_current_files"][0]), sd["drawing_current_files"][1]]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    _fixing(seed.id, 2)
    login(client, make_user("가짜반장", lead=True))
    version = fresh(seed.id).mutation_version
    _refused_per_sheet(check_step(client, seed.id, "cut", True), seed.id, version)  # 지금 도면 3줄 = 여러 장(사장님 2026-11-27)
    assert sent == []  # 풀어 쓰기 문장 0(값 줄 key 마다 하나는 expand_hand_step 시험이 지킨다)


def test_only_blocked_drawings_is_refused_like_the_whole_block(client):
    """지금 도면이 모두 막힌 도면 1장 주문 — 옛 답은 풀어 쓸 장이 없어 409 DRAWING_REVISING(numbers [1]). 사장님 2026-11-27 "도면이 주, 작업 시트는 보기" 뒤로는 도면이 있으면
    풀어 쓰기 앞 문(STEP_PER_SHEET)에서 먼저 막힌다(쓰기 0 은 같다 — 풀어 쓰기 길은 이제 안 탄다)."""
    seed = make_order(1)
    _fixing(seed.id, 0)
    login(client, make_user("가짜반장", lead=True))
    before = (fresh(seed.id).mutation_version, _marks(seed.id))
    res = check_step(client, seed.id, "cut", True)
    body = res.get_json()
    assert res.status_code == 409 and code(res) == STEP_PER_SHEET and body["error"] == STEP_PER_SHEET_MESSAGE
    assert body["data"]["part"] == "cut"
    assert (fresh(seed.id).mutation_version, _marks(seed.id)) == before and step(seed.id, "cut")["done"] is False


def test_card_parts_whole_block_and_turned_on_cells_keep_today_rules(client):
    boss = make_user("가짜반장", lead=True)
    used = make_order(3)
    _fixing(used.id, 1)
    put_mark(used, 0, "cut", "NEED", factory_user("김재단", part="cut"))
    login(client, boss)
    assert code(check_step(client, used.id, "cut", True)) == PART_USES_CARDS  # 카드를 쓴 파트는 지금 규칙
    whole = make_order(3, extra={"drawing_status": "RETURNED"})
    assert code(check_step(client, whole.id, "cut", True)) == DRAWING_REVISING and _marks(whole.id) == {}
    on = make_order(3, steps_done=("cut",))
    _fixing(on.id, 1)
    refused = check_step(client, on.id, "cut", True)  # 도면 3장 = 이미 켠 칸도 다시 켜기는 거절, 칸은 그대로(자료를 고치지 않는다)
    assert code(refused) == STEP_PER_SHEET and step(on.id, "cut")["done"] is True and _marks(on.id) == {}
    one = make_order(1, steps_done=("cut",))
    _fixing(one.id, 0)
    refused = check_step(client, one.id, "cut", True)  # 도면 1장도 다시 켜기는 거절(사장님 2026-11-27 "도면이 주, 작업 시트는 보기"), 칸은 그대로 · 풀어 쓰지 않는다
    assert code(refused) == STEP_PER_SHEET and step(one.id, "cut")["done"] is True and _marks(one.id) == {}


def test_inspect_expand_passes_each_drawing_through_the_inspect_gate_or_writes_nothing(client):
    """둘째 판 3 이던 것 — 검수 통째 켜기도 도면 3장 주문이면 준비 여부와 상관없이 409 STEP_PER_SHEET · 쓰기 0(사장님 2026-11-27).
    대조군: 도면 0장 주문의 검수 손 칸은 전과 똑같이(문 없이 칸만 켬 — 옛 대조군 도면 1장은 사장님 2026-11-27 "도면이 주, 작업 시트는 보기" 뒤로 409)."""
    login(client, make_user("가짜반장", lead=True))
    for steps_done in ((), ("cut", "edge", "assemble")):
        many = make_order(3, steps_done=steps_done)
        _fixing(many.id, 1)
        _refused_per_sheet(check_step(client, many.id, "inspect", True), many.id, fresh(many.id).mutation_version)
    plain = make_order(0)
    assert check_step(client, plain.id, "inspect", True).status_code == 200 and step(plain.id, "inspect")["done"] is True
    assert _marks(plain.id) == {}


def test_stuck_row_stays_in_the_next_steps_incoming(client, cohort):
    """둘째 판 1 — 남은 장이 고치는 도면뿐인 재단 줄도 엣지 '곧 올 것'에 남는다(끝난 장은 다음 공정으로 — "나머지는 계속 작업").
    통째 막힘 줄만 지금처럼 빠진다(대조군)."""
    stuck = add_order("가짜끝집", 1, pngs=3).id
    whole = add_order("가짜통째집", 2, pngs=3).id
    _fixing(stuck, 1)
    _done_cards(stuck, 0, 2)  # 남은 장 = 고치는 도면뿐(통째 켜기는 이제 거절 — 카드로 같은 상태)
    order = db_session.get(Order, whole)
    order.structured_data = {**order.structured_data, "drawing_status": "RETURNED"}
    db_session.commit()
    home_login(client)
    set_cookies(client, PHONE)
    page = get_html(client, HOME + "?tab=steps")
    edge = page.split('data-foms-home-stepq="edge"', 1)[1].split('data-foms-home-stepq="', 1)[0]
    assert "가짜끝집" in edge and "가짜통째집" not in edge
    assert '<span class="fph-qr__hold">도면 2 수정 중</span>' in _row(page, stuck)  # 그 줄 자체는 [끝] 자리 막힘 그대로


# --------------------------------------------------------------------------- #
# 공정 줄(판결 D) · 확인 창 자료
# --------------------------------------------------------------------------- #
CONFIRM_ATTR = re.compile(r'data-foms-sheet-parts="([^"]+)"')


def _confirm(fragment: str) -> dict:
    return json.loads(html_lib.unescape(CONFIRM_ATTR.search(fragment).group(1)))


def _row(page: str, oid: int) -> str:
    return page.split(f'data-foms-home-qrow="{oid}"', 1)[1].split('data-foms-home-qrow="', 1)[0]


def _seed_rows(client) -> tuple[int, int, int]:
    """재단 줄 셋 — 남은 장이 고치는 도면뿐인 주문(카드로 2장 완료) · 막힌 도면 있는 도면 3장 주문(아직) · 보통 주문(도면 0장 — 사장님 2026-11-27 "도면이 주, 작업 시트는 보기"
    뒤로 [끝]이 남는 줄)."""
    stuck, ready = (add_order(n, i, pngs=3).id for i, n in enumerate(("가짜끝집", "가짜고침집"), 1))
    plain = add_order("가짜도면집", 3, pngs=0).id
    _fixing(stuck, 1)
    _fixing(ready, 1)
    _done_cards(stuck, 0, 2)
    return stuck, ready, plain


def test_steps_rows_show_fixing_in_the_finish_slot_only_when_nothing_else_is_left(client, cohort):
    stuck, ready, plain = _seed_rows(client)
    home_login(client)  # 반장
    hold = '<span class="fph-qr__hold">도면 2 수정 중</span>'
    for cookies in (PHONE, TABLET):
        set_cookies(client, cookies)
        page = get_html(client, HOME + "?tab=steps")
        assert hold in _row(page, stuck) and "data-foms-home-step-done" not in _row(page, stuck)  # [끝] 자리 · 그 모양
        assert f'fph-qr is-revise" data-foms-home-qrow="{stuck}"' in page
        # 막힌 도면이 있어도 남은 장이 더 있는 도면 3장 주문 = [끝] 대신 여러 장 막힘 칸(사장님 2026-11-27)
        assert "data-foms-home-step-done" not in _row(page, ready) and "재단 0/3 · 3장 미완료" in _row(page, ready)
        assert "data-foms-sheet-parts" not in _row(page, plain) and "fph-qr__hold" not in _row(page, plain)  # 대조군(도면 0장 — 묻지 않음)
        assert "data-foms-home-step-done" in _row(page, plain)
        assert "fph-qr__holdtag\">도면 2 수정 중" not in _row(page, ready)  # 남은 장이 있으면 새 표시 없이 [끝]
    pane = get_html(client, f"{HOME}?tab=steps&order={stuck}")
    assert f'<section class="fph-sp is-revise" data-foms-step-pane="{stuck}"' in pane
    assert f"도면 2 수정 중</b><span>{REVISING_MESSAGE}</span>" in pane  # 가로 판 = 통째와 같은 멈춤 자리
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    client.set_cookie(EDIT_COOKIE, str(int(time.time())), domain="localhost", path="/erp/production")
    pc = get_html(client, HOME + "?tab=steps")
    assert '<span class="fpc-hold">도면 2 수정 중</span>' in _row(pc, stuck) and "data-foms-home-step-done" not in _row(pc, stuck)
    home_login(client, "가짜보기", lead=False)  # [끝]이 없는 사람도 같은 줄
    set_cookies(client, PHONE)
    view = get_html(client, HOME + "?tab=steps")
    assert hold in _row(view, stuck) and "fph-qr__hold" not in _row(view, ready)


def test_work_sheet_and_my_steps_rows_carry_the_new_body_only_when_blocked(client, cohort):
    ready, plain = add_order("가짜고침집", 1, pngs=3).id, add_order("가짜도면집", 2, pngs=3).id
    _fixing(ready, 1)
    home_login(client)
    set_cookies(client, TABLET)
    sheet = get_html(client, f"/erp/production/sheet/{ready}")
    data = _confirm(sheet.split('aria-label="공정"', 1)[1])
    assert data["fix"] == {"done": 2, "numbers": [2], "tail": "도면 2는 수정 중이라 빼요."} and data["sheets"] == 3
    assert ">도면 2 수정 중<" in sheet  # 작업 시트 배지(통째는 지금 글 "도면 수정 중")
    assert "fix" not in _confirm(get_html(client, f"/erp/production/sheet/{plain}").split('aria-label="공정"', 1)[1])
