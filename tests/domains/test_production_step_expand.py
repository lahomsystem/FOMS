"""통째 작업에서 막힌 도면만 빼고 처리(사장님 답 "고치는 도면만 빼고 처리" — 설계서 2026-11-25 §3-6 ① · C4).

반장 · 관리자가 카드를 한 장도 안 쓴 파트의 공정 칸을 켤 때 그 주문에 도면별로 막힌 장이 1장 이상이면 칸은 켜지 않고, 막히지 않은
지금 도면마다 그 파트 표시 줄을 ``DONE``(완료한 사람 = 누른 사람)으로 **한 문장**에 쓴다(이미 끝 · 기본 줄은 그대로). 그 파트는 그 순간
'카드를 쓴 파트'가 되어 칸은 동기화가 맞춘다(막힌 장이 남아 꺼짐 → 그 장 새 판이 완료되면 저절로 켜짐). 응답 ``data.expanded``
(``part · done_n · total_n · skipped_numbers · note``) · 이벤트 ``PRODUCTION_STEP_CHECKED``(``via: 'step_expand'`` · ``expanded_keys``).
반장은 자기 공장 장만(``factory_gate`` 와 같은 규칙). 쓸 수 있는 장이 모두 막히면 통째 막힘과 같은 409. 막힌 장이 없으면 지금 그대로(칸만 켬).
확인 창(작업 시트 · '내 공정' [끝] · PC 창): 본문만 새 글 "이 주문의 도면 3장 중 2장이 재단 완료로 처리돼요. 도면 2는 고치는 중이라 빼요."

되돌리면 실패: 막힌 장까지 완료됨 · 칸이 켜짐 · 기본 줄을 완료로 덮음 · 남의 공장 장을 씀 · 장마다 INSERT · 막힌 장 없는 주문까지 풀어 씀.
대조군: 막힌 장 없는 주문 · 카드를 쓴 파트 · 주문 통째 막힘은 지금 규칙 그대로. 이름은 지어낸 값, 날짜는 오늘(KST)에서 센다.
"""
from __future__ import annotations

import copy
import html as html_lib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from db import db_session, engine
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders import drawing_fix as fx
from foms.services.production.part_mark_gates import DRAWING_REVISING, PART_USES_CARDS, REVISING_MESSAGE
from foms.services.production.part_steps_sync import VIA_STEP_EXPAND, expand_hand_step
from models import Order, ProductionPartMark
from tests.domains.test_production_my_steps_confirm import NODE_CHECK, PHONE
from tests.support.production_factory_seed import factory_user, mixed_order, put_mark
from tests.support.production_home_step_panel_seed import HOME, SHELL, TABLET, add_order, get_html, set_cookies
from tests.support.production_home_step_panel_seed import login as home_login
from tests.support.production_part_claim_seed import (
    check_step,
    code,
    events,
    finish,
    fresh,
    login,
    make_order,
    make_user,
    step,
)

FIX = {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}
TEXT = "이 주문의 도면 3장 중 2장이 재단 완료로 처리돼요. 도면 2는 고치는 중이라 빼요."


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


def _marks(oid: int) -> dict[tuple[str, str], ProductionPartMark]:
    db_session.expire_all()
    return {(m.drawing_key, m.part): m for m in db_session.query(ProductionPartMark).filter_by(order_id=oid)}


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


def test_whole_step_skips_the_blocked_drawing_and_writes_the_rest_in_one_statement(client):
    seed = make_order(3)
    _fixing(seed.id, 1)
    boss = make_user("가짜반장", lead=True)
    login(client, boss)
    info = client.get(f"/api/orders/{seed.id}/production/steps").get_json()["data"]
    assert info["fix"] == {"done": 2, "numbers": [2], "tail": "도면 2는 고치는 중이라 빼요."} and info["sheets"] == 3
    assert fx.expand_confirm_body(info["sheets"], info["fix"]["done"], "재단", info["fix"]["numbers"]) == TEXT
    version = fresh(seed.id).mutation_version
    res, inserts = _insert_count(lambda: check_step(client, seed.id, "cut", True))
    body = res.get_json()
    assert res.status_code == 200 and inserts == 1, body  # 장 수와 무관하게 한 문장(N+1 없음)
    data = body["data"]
    assert data["expanded"] == {"part": "cut", "done_n": 2, "total_n": 3, "skipped_numbers": [2], "note": "도면 2/3 · 1장 미완료"}
    assert data["parts"]["cut"]["uses_cards"] is True and data["parts"]["cut"]["left_n"] == 1 and data["fix"]["done"] == 2
    assert next(s for s in data["steps"] if s["key"] == "cut")["done"] is False and step(seed.id, "cut")["done"] is False
    marks = _marks(seed.id)
    for j in (0, 2):
        m = marks[(seed.keys[j], "cut")]
        assert (m.state, m.done_by_name, m.done_by_user_id, m.updated_by_user_id) == ("DONE", "가짜반장", boss.id, boss.id)
        assert m.sheet_id == fresh(seed.id).structured_data["drawing_current_files"][j]["sheet_id"]
    assert (seed.keys[1], "cut") not in marks  # 막힌 장은 할 일로 남는다
    ev = [e for e in events(seed.id, "PRODUCTION_STEP_CHECKED") if (e.payload or {}).get("via") == VIA_STEP_EXPAND]
    assert len(ev) == 1 and ev[0].payload["expanded_keys"] == [seed.keys[0], seed.keys[2]] and ev[0].payload["done"] is True
    assert ev[0].payload["by_name"] == "가짜반장" and ev[0].payload["skipped_numbers"] == [2]
    assert fresh(seed.id).mutation_version == version + 1
    # 막힘이 풀린 뒤 그 장을 완료하면 칸이 저절로 켜진다(동기화 — 지금 규칙)
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    sd.pop("drawing_fix")
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    login(client, make_user("가짜재단", part="cut"))
    assert finish(client, seed, 1, "cut").status_code == 200
    assert step(seed.id, "cut")["done"] is True


def test_without_a_blocked_drawing_the_cell_turns_on_like_today(client):
    seed = make_order(3)
    login(client, make_user("가짜반장", lead=True))
    assert "fix" not in client.get(f"/api/orders/{seed.id}/production/steps").get_json()["data"]
    res = check_step(client, seed.id, "cut", True)
    data = res.get_json()["data"]
    assert res.status_code == 200 and "expanded" not in data and "fix" not in data
    assert step(seed.id, "cut")["done"] is True and _marks(seed.id) == {}  # 칸만 켬 · 표시 줄 0


def test_expand_never_overwrites_finished_rows_and_keeps_the_holder(client):
    seed = make_order(3)
    kim, park = factory_user("김재단", part="cut"), factory_user("박재단", part="cut")
    put_mark(seed, 0, "cut", "BASIC", kim)
    put_mark(seed, 1, "cut", "NEED", park)
    sd = fresh(seed.id).structured_data
    put_mark(seed, 2, "cut", "DONE", kim)  # 읽은 뒤 그사이 누가 끝냈어도(장 3 DONE) 한 문장이 덮지 않는다 — 장 3 줄을 뺀 낡은 읽기
    db_session.expire_all()
    marks = [m for m in db_session.query(ProductionPartMark).filter_by(order_id=seed.id) if m.drawing_key != seed.keys[2]]
    written = expand_hand_step(db_session, sd, marks, "cut", order_id=seed.id, exclude_keys=(), by_user_id=None,
                               by_name="박반장", at=now_utc_naive(), updated_by_user_id=None)
    db_session.commit()
    assert [v["drawing_key"] for v in written] == [seed.keys[1], seed.keys[2]]  # 기본 장은 쓰지 않는다
    rows = _marks(seed.id)
    basic, need, done = (rows[(seed.keys[j], "cut")] for j in range(3))
    assert (basic.state, basic.done_by_name) == ("BASIC", "김재단")  # 재단 기본 그대로(설계서 §12)
    assert (need.state, need.picked_by_name, need.done_by_name) == ("DONE", "박재단", "박반장")  # 맡은 사람은 남는다
    assert (done.state, done.done_by_name) == ("DONE", "김재단")  # 이미 끝 = 덮지 않음(WHERE)


def test_all_writable_drawings_blocked_is_refused_like_the_whole_block(client):
    seed = make_order(1)
    _fixing(seed.id, 0)
    login(client, make_user("가짜반장", lead=True))
    before = (fresh(seed.id).mutation_version, _marks(seed.id))
    res = check_step(client, seed.id, "cut", True)
    body = res.get_json()
    assert res.status_code == 409 and code(res) == DRAWING_REVISING and body["error"] == REVISING_MESSAGE
    assert body["data"]["numbers"] == [1] and body["data"]["part"] == "cut"
    assert (fresh(seed.id).mutation_version, _marks(seed.id)) == before and step(seed.id, "cut")["done"] is False


def test_factory_lead_writes_only_own_factory_drawings(client):
    seed = mixed_order(4, f2=(2, 3))  # 도면 3 · 4 = 2공장
    _fixing(seed.id, 0)  # 도면 1(1공장) 고치는 중
    login(client, factory_user("가짜반장", lead=True))
    info = client.get(f"/api/orders/{seed.id}/production/steps").get_json()["data"]
    assert info["fix"] == {"done": 1, "numbers": [1], "tail": "도면 1은 고치는 중이라 빼요."}
    res = check_step(client, seed.id, "edge", True)
    assert res.status_code == 200 and res.get_json()["data"]["expanded"]["done_n"] == 1
    assert set(_marks(seed.id)) == {(seed.keys[1], "edge")}  # 남의 공장(2공장) 장은 쓰지 않는다
    other = mixed_order(4, f2=(2, 3))
    _fixing(other.id, 0)
    login(client, make_user("가짜관리", team="CS", role="ADMIN"))
    assert check_step(client, other.id, "edge", True).get_json()["data"]["expanded"]["done_n"] == 3  # 관리자는 두 공장


def test_card_parts_hold_and_whole_block_keep_today_rules(client):
    boss = make_user("가짜반장", lead=True)
    used = make_order(3)
    _fixing(used.id, 1)
    put_mark(used, 0, "cut", "NEED", factory_user("김재단", part="cut"))
    login(client, boss)
    assert code(check_step(client, used.id, "cut", True)) == PART_USES_CARDS  # 카드를 쓴 파트는 지금 규칙
    whole = make_order(3, extra={"drawing_status": "RETURNED"})
    assert code(check_step(client, whole.id, "cut", True)) == DRAWING_REVISING and _marks(whole.id) == {}  # 통째는 지금처럼 막음
    on = make_order(3, steps_done=("cut",))
    _fixing(on.id, 1)
    assert check_step(client, on.id, "cut", True).status_code == 200 and _marks(on.id) == {}  # 이미 켠 칸은 풀어 쓰지 않는다


# --------------------------------------------------------------------------- #
# 확인 창 자료 · 글(작업 시트 · '내 공정' [끝] · PC 창)
# --------------------------------------------------------------------------- #
CONFIRM_ATTR = re.compile(r'data-foms-sheet-parts="([^"]+)"')


def _confirm(fragment: str) -> dict:
    return json.loads(html_lib.unescape(CONFIRM_ATTR.search(fragment).group(1)))


def _drawn(name: str, off: int, *, fixing: bool) -> int:
    oid = add_order(name, off, pngs=3).id
    if fixing:
        _fixing(oid, 1)
    return oid


def test_work_sheet_and_my_steps_rows_carry_the_new_body_only_when_blocked(client, cohort):
    blocked, plain = _drawn("가짜고침집", 1, fixing=True), _drawn("가짜도면집", 2, fixing=False)
    home_login(client)
    set_cookies(client, TABLET)
    sheet = get_html(client, f"/erp/production/sheet/{blocked}")
    data = _confirm(sheet.split('aria-label="공정"', 1)[1])
    assert data["fix"] == {"done": 2, "numbers": [2], "tail": "도면 2는 고치는 중이라 빼요."} and data["sheets"] == 3
    assert ">도면 2 고치는 중<" in sheet  # 작업 시트 배지(통째는 지금 글 "도면 수정 중")
    assert "fix" not in _confirm(get_html(client, f"/erp/production/sheet/{plain}").split('aria-label="공정"', 1)[1])
    page = get_html(client, HOME + "?tab=steps")
    rows = {oid: page.split(f'data-foms-home-qrow="{oid}"', 1)[1].split('data-foms-home-qrow="', 1)[0]
            for oid in (blocked, plain)}
    assert _confirm(rows[blocked])["fix"]["done"] == 2 and "data-foms-home-step-done" in rows[blocked]  # [끝]은 그대로
    assert '<span class="fph-qr__holdtag">도면 2 고치는 중</span>' in rows[blocked]
    assert "fix" not in _confirm(rows[plain]) and "holdtag" not in rows[plain]  # 대조군: 지금 자료 · 화면 그대로


def test_node_my_steps_row_dialog_shows_the_new_body(client, cohort, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    blocked = _drawn("가짜고침집", 1, fixing=True)
    bare = add_order("가짜빈집", 2, pngs=0).id
    home_login(client)
    set_cookies(client, PHONE)
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    path = tmp_path / "row.html"
    path.write_text(page, encoding="utf-8")
    want = {"mode": "row", "first": blocked, "bare": bare, "key": "cut", "title": "재단을 작업 완료로 처리할까요?", "text": TEXT}
    proc = subprocess.run([node, str(NODE_CHECK), str(path), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


def test_sheet_parts_js_builds_the_body_from_server_words_only():
    src = (Path(__file__).resolve().parents[2] / "static/js/production/foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert len(src.splitlines()) <= 300
    assert "'장 중 ' + fix.done + '장이 ' + label + ' 완료로 처리돼요. ' + fix.tail" in src  # 뒤 문장(조사 포함)은 서버 글
    assert "'장이 모두 ' + label + ' 완료로 처리돼요.'" in src  # 막힌 도면 없으면 지금 글 그대로
    assert "고치는 중이라 빼요'" not in src and "ask(LABELS[key] || key, info.sheets, btn, go, no, info.fix);" in src
