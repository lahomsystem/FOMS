"""'도면 없음' 카드로 일한 뒤 도면이 **처음** 올라올 때 — 한 번 옮기기(설계서 2026-11-28-production-my-steps-flow §3-5 '만드는 꼴' ·
사장님 답 27 "완료 그대로 둠" · 33 "새 도면 2장도 김재단 작업 중" · 35 "손으로 끝낸 것도 똑같이 완료 그대로").

생산 · 시공 단계 바로 반영 전달(``transfer-drawing``)이 0장 → n장으로 바꾸는 같은 tx 에서 미정이 아닌 ``@order`` 줄 · 손 체크 파트를 새 도면
key 마다 같은 파트 줄로 넣고 ``@order`` 줄은 미정으로 돌린다. 되돌리면 실패: 끝낸 재단이 도면이 오자 미완료 · 칸 꺼짐 · 작업 중이던 사람의 내 공정에
새 도면이 없음 · 손 체크 칸이 꺼짐 · 안 건드린 파트에 줄이 생김 · 이벤트 표지 없음 · ``@order`` 작업 중 줄이 남아 한 장 더 셈 · 그 뒤 도면이
다시 바뀌어도 완료로 번짐 · 시공 단계에서 칸 넷이 꺼짐 · 도면이 n → 0장이 된 주문의 켜진 칸이 '도면 없음' 담기로 꺼짐 · 2공장 장에 작업 중이
옮겨짐 · 옮긴 뒤 세션 줄을 만료 안 함 · 바뀐 기록에 "order_card" · '도면 없음' 기록이 "옛 도면" 머리(2026-11-28 ⓑ 검토 1 · 3 · 4 · 6 · 7).
이름은 모두 지어낸 값이다(김재단 · 오재단 · 박엣지 · 최조립 · 한검수 · 박반장 · 김도면).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from db import db_session
from foms.services.production.order_card_carry import VIA_ORDER_CARD
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import complete_ready
from foms.services.production.sheet_parts import sheet_part_extras
from models import Order, ProductionPartMark, User
from tests.domains.test_production_flow_read import _cards, my_steps_of
from tests.support.drawing_fix_transfer_seed import (  # noqa: F401 — quiet · team = 픽스처
    key,
    login as dfx_login,
    make_order,
    marks,
    patch,
    put_mark,
    quiet,
    send,
    team,
)
from tests.support.production_part_claim_seed import HISTORY, ONE, check_step, code, events, login, make_user, step

ORDER = "@order"
PARTS = ("cut", "edge", "assemble", "inspect")
ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_pc_sheet_node_checks.js"


def _post(client, who, oid: int, part: str, action: str, seen: str, *, drawing_key: str = ORDER, **extra):
    login(client, who)
    return client.post(ONE, json={"order_id": oid, "drawing_key": drawing_key, "part": part, "action": action, "seen": seen, **extra})


def _press(client, who, oid: int, part: str, action: str, seen: str, **extra) -> dict:
    resp = _post(client, who, oid, part, action, seen, **extra)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _arrive(client, team, oid: int, sheets: tuple[str, ...] = ("s0", "s1"), **body) -> list[str]:
    dfx_login(client, team.drawer)
    resp = send(client, "drawing", oid, *sheets, **body)
    assert resp.status_code == 200, resp.get_json()
    return [key(oid, f"{s}-v2") for s in sheets]


def _ready(oid: int) -> bool:
    db_session.expire_all()
    return complete_ready(db_session.get(Order, oid).structured_data, order_marks(db_session, oid))


def _carry_events(oid: int) -> list[dict]:
    return [e.payload for e in events(oid, "PRODUCTION_PART_MARKED") if e.payload.get("via") == VIA_ORDER_CARD]


def test_done_order_card_stays_done_on_every_new_drawing(client, quiet, team):
    oid = make_order(0)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    assert step(oid, "cut")["done"] is True
    new = _arrive(client, team, oid)
    rows = marks(oid)
    assert [(rows[(k, "cut")].state, rows[(k, "cut")].done_by_name, rows[(k, "cut")].done_by_user_id) for k in new] == \
        [("DONE", "김재단", kim.id)] * 2
    assert rows[(new[0], "cut")].sheet_id == "s0" and rows[(new[1], "cut")].sheet_id == "s1"
    assert rows[(ORDER, "cut")].state == "NONE"  # 옮긴 @order 줄은 미정(기록으로 남김)
    cut = step(oid, "cut")
    assert cut["done"] is True and cut["by_name"] == "김재단"  # 뒤 공정 칸 맞추기가 돌아도 켜진 채(27번 답)
    copies = [p for p in _carry_events(oid) if p["action"] == "done"]
    assert [(p["key"], p["part"], p["from"], p["to"], p["by_name"]) for p in copies] == [
        (new[0], "cut", "NONE", "DONE", "김재단"), (new[1], "cut", "NONE", "DONE", "김재단")]
    cleared = [p for p in _carry_events(oid) if p["action"] == "order_card"]
    assert [(p["key"], p["from"], p["to"], p["to_keys"]) for p in cleared] == [(ORDER, "DONE", "NONE", new)]


def test_working_order_card_becomes_that_person_working_on_every_new_drawing(client, quiet, team):
    oid = make_order(0)
    kim, oh = make_user("김재단", part="cut"), make_user("오재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, oh, oid, "cut", "join", "need")
    new = _arrive(client, team, oid)
    rows = marks(oid)
    for k in new:
        assert rows[(k, "cut")].state == "NEED" and [m["uid"] for m in rows[(k, "cut")].holders] == [kim.id, oh.id]
    assert rows[(ORDER, "cut")].state == "NONE" and step(oid, "cut")["done"] is False
    mine = _cards(my_steps_of(db_session.get(User, kim.id)))
    assert [(c["key"], c["order_card"]) for c in mine] == [(new[0], False), (new[1], False)]  # 33번 답 — 새 도면 2장이 내 공정에
    # '작업 중 장 수'(공장을 바꾼 사람 안내 등)에 @order 가 한 장 더 안 든다 — NEED 줄은 새 key 둘뿐
    db_session.expire_all()
    held = db_session.query(ProductionPartMark).filter_by(order_id=oid, state="NEED").all()
    assert sorted(m.drawing_key for m in held) == sorted(new)


def test_hand_checked_part_is_written_done_on_new_drawings_and_untouched_parts_stay_open(client, quiet, team):
    oid = make_order(0)
    lead, edge = make_user("박반장", lead=True), make_user("박엣지", part="edge")
    login(client, lead)
    assert check_step(client, oid, "assemble", True).status_code == 200  # 손 체크(35번 답)
    _press(client, edge, oid, "edge", "take", "none")
    _press(client, edge, oid, "edge", "release", "need")  # 맡았다 취소 — 미정 @order 줄은 옮기지 않는다
    new = _arrive(client, team, oid)
    rows = marks(oid)
    assert [(rows[(k, "assemble")].state, rows[(k, "assemble")].done_by_name) for k in new] == [("DONE", "박반장")] * 2
    assert step(oid, "assemble")["done"] is True  # 지금 코드는 여기서 칸을 껐다(expand_hand_parts — 모든 장이 새 장)
    assert not any((k, "edge") in rows for k in new) and not any((k, "cut") in rows for k in new)  # 미정 파트 = 새 도면 미정
    assert step(oid, "edge")["done"] is False and step(oid, "cut")["done"] is False


def test_drawings_changing_again_follow_the_usual_rule(client, quiet, team):
    """옮긴 뒤 그 도면이 다시 바뀌면(key1 → key1′) 지금 규칙 그대로 — 새 장 미정 · 칸 꺼짐(옮기기는 처음 올 때 한 번)."""
    oid = make_order(0)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    new = _arrive(client, team, oid)
    dfx_login(client, team.drawer)
    files = [{"key": key(oid, "s0-v3"), "filename": "s0-v3.png", "sheet_id": "s0"}]
    resp = client.post(f"/api/orders/{oid}/transfer-drawing",
                       json={"note": "상판 깊이 600 → 580", "files": files, "mode": "APPEND", "ack_worked": ["sheet:s0"]})
    assert resp.status_code == 200, resp.get_json()
    rows = marks(oid)
    assert (key(oid, "s0-v3"), "cut") not in rows and rows[(new[1], "cut")].state == "DONE"
    assert step(oid, "cut")["done"] is False
    assert len([p for p in _carry_events(oid) if p["action"] == "done"]) == 2  # 두 번째 전달은 옮기지 않았다


def test_first_drawings_on_an_order_without_order_card_rows_change_nothing_new(client, quiet, team):
    """대조군 — @order 줄도 손 체크도 없는 0장 주문은 지금 그대로(새 줄 0 · 이벤트 0)."""
    oid = make_order(0)
    _arrive(client, team, oid)
    assert [k for k in marks(oid)] == [] and _carry_events(oid) == []


# --------------------------------------------------------------------------- #
# ⓑ 검토 1 — 시공 단계(제작 완료 뒤)에 도면이 처음 와도 옮긴다
# --------------------------------------------------------------------------- #
def _made_by_order_card(client, by_hand: tuple[str, ...] = ()) -> int:
    """'도면 없음' 카드로 네 파트를 끝내(``by_hand`` 파트는 반장 손 체크) 제작 완료한 0장 주문(시공 단계)."""
    oid = make_order(0)
    lead = make_user("박반장", lead=True)
    names = {"cut": "김재단", "edge": "박엣지", "assemble": "최조립", "inspect": "한검수"}
    for part in PARTS:
        if part in by_hand:
            login(client, lead)
            assert check_step(client, oid, part, True).status_code == 200
            continue
        who = make_user(names[part], part=part)
        _press(client, who, oid, part, "take", "none")
        _press(client, who, oid, part, "done", "need")
    login(client, lead)
    assert client.post(f"/api/orders/{oid}/production/complete", json={}).status_code == 200
    assert db_session.get(Order, oid).erp_stage_code == "CONSTRUCTION"
    return oid


def test_first_drawings_in_construction_keep_the_four_order_card_steps_on(client, quiet, team):
    oid = _made_by_order_card(client)
    new = _arrive(client, team, oid, ack_order_made=True)
    rows = marks(oid)
    assert [rows[(k, p)].state for k in new for p in PARTS] == ["DONE"] * 8  # 새 도면 줄 = 완료
    assert all(step(oid, p)["done"] for p in PARTS)  # 지금 코드는 넷 다 껐다(옮기기가 생산 단계만 봤다)
    assert _ready(oid) is True and [rows[(ORDER, p)].state for p in PARTS] == ["NONE"] * 4


def test_hand_checked_part_in_construction_is_written_done_and_its_step_stays_on(client, quiet, team):
    """시공 단계에서도 손 체크 파트를 새 도면 줄(완료)로 풀어 쓴다 — 칸이 켜진 채(나중 수정 제작이 도면별로 고를 수 있게)."""
    oid = _made_by_order_card(client, by_hand=("assemble",))
    new = _arrive(client, team, oid, ack_order_made=True)
    rows = marks(oid)
    assert [(rows[(k, "assemble")].state, rows[(k, "assemble")].done_by_name) for k in new] == [("DONE", "박반장")] * 2
    assert all(step(oid, p)["done"] for p in PARTS) and _ready(oid) is True


# --------------------------------------------------------------------------- #
# ⓑ 검토 3 — 도면이 n → 0장이 된 주문: 옛 판 줄은 '카드를 쓴'에 안 든다
# --------------------------------------------------------------------------- #
def _lit_then_emptied(client) -> int:
    """도면 1장 재단을 김재단이 끝내(칸 켜짐) 뒤 도면 목록을 비운 주문(옛 판 줄만 남은 0장)."""
    oid = make_order(1)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none", drawing_key=key(oid, "s0"))
    _press(client, kim, oid, "cut", "done", "need", drawing_key=key(oid, "s0"))
    assert step(oid, "cut")["done"] is True
    patch(oid, drawing_current_files=[])
    return oid


def test_step_lit_by_an_old_drawing_blocks_the_order_card(client, quiet, team):
    oid = _lit_then_emptied(client)
    resp = _post(client, make_user("오재단", part="cut"), oid, "cut", "take", "none")
    assert resp.status_code == 409 and code(resp) == "STEP_SET_BY_HAND"
    assert resp.get_json()["error"] == "김재단이 작업 시트에서 재단 칸을 작업 완료 처리했어요. 다시 해야 하면 김재단에게 말해 주세요."
    assert step(oid, "cut")["done"] is True and (ORDER, "cut") not in marks(oid)  # 지금 코드는 담기를 받아 칸을 껐다


def test_old_drawing_in_work_then_hand_check_blocks_the_order_card(client, quiet, team):
    oid = make_order(1)
    _press(client, make_user("김재단", part="cut"), oid, "cut", "take", "none", drawing_key=key(oid, "s0"))
    patch(oid, drawing_current_files=[])  # 옛 장 작업 중인 채 0장
    login(client, make_user("박반장", lead=True))
    assert check_step(client, oid, "cut", True).status_code == 200
    resp = _post(client, make_user("오재단", part="cut"), oid, "cut", "take", "none")
    assert resp.status_code == 409 and code(resp) == "STEP_SET_BY_HAND"
    assert step(oid, "cut")["done"] is True and (ORDER, "cut") not in marks(oid)


def test_first_drawings_after_zero_keep_a_step_lit_by_an_old_drawing(client, quiet, team):
    oid = _lit_then_emptied(client)
    new = _arrive(client, team, oid)
    rows = marks(oid)
    assert [(rows[(k, "cut")].state, rows[(k, "cut")].done_by_name) for k in new] == [("DONE", "김재단")] * 2
    assert step(oid, "cut")["done"] is True  # 지금 코드는 옛 판 줄 때문에 손 체크로 안 봐 칸을 껐다


# --------------------------------------------------------------------------- #
# ⓑ 검토 4 — 작업 중은 1공장 장에만, 완료는 모든 장에
# --------------------------------------------------------------------------- #
def test_working_order_card_moves_only_to_first_factory_sheets(client, quiet, team):
    oid = make_order(0)
    kim, edge = make_user("김재단", part="cut"), make_user("박엣지", part="edge")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    _press(client, edge, oid, "edge", "take", "none")
    patch(oid, drawing_factory={"sheets": {"s1": 2}, "files": {}})  # 보내기 전 s1 = 2공장
    new = _arrive(client, team, oid)
    rows = marks(oid)
    assert [rows[(k, "cut")].state for k in new] == ["DONE", "DONE"]  # 완료는 2공장 장에도
    assert rows[(new[0], "edge")].state == "NEED" and (new[1], "edge") not in rows  # 작업 중은 1공장 장(s0)만
    assert rows[(ORDER, "edge")].state == "NONE"
    # 1공장 장이 하나도 없으면 작업 중은 어디에도 안 옮기고 @order 줄만 미정으로
    other = make_order(0)
    _press(client, edge, other, "edge", "take", "none")
    patch(other, drawing_factory={"sheets": {"s0": 2, "s1": 2}, "files": {}})
    new = _arrive(client, team, other)
    rows = marks(other)
    assert not any((k, "edge") in rows for k in new) and rows[(ORDER, "edge")].state == "NONE"


# --------------------------------------------------------------------------- #
# ⓑ 검토 2 (나) — 도면은 있는데 '도면 없음' 카드 줄이 남은 주문의 바로 반영 전달 · ⓑ 검토 7 — 옮긴 뒤 세션 줄 만료(db.expire)
# --------------------------------------------------------------------------- #
def test_leftover_order_card_on_a_hotfix_transfer_carries_and_keeps_steps_on(client, quiet, team):
    """생산 밖에서 도면을 받아 @order 완료 줄이 남은 생산 주문(이번 고침 전에 생긴 꼴) — 도면 1을 고쳐 보내면 그 전달에서 한 번 옮긴다.

    처음 옮기기와 같은 꼴이다: 재단 완료가 지금 도면 둘에 · 손 체크 조립도 지금 도면 둘에 완료(바뀐 도면 포함). 도면 1을 고쳤으므로
    ``worked_refusal`` 이 읽은 표시 줄을 라우트가 칸 맞추기 끝까지 쥔다 — ``carry_order_card`` 의 ``db.expire`` 를 빼면 칸 맞추기가 세션에 든
    도면 2 조립 줄을 옛 '미정'으로 읽어 조립 칸을 끈다(이 시험이 실패한다).
    """
    oid = make_order(2, steps_done=("assemble",))  # 조립 = 반장 손 체크(칸 켜짐)
    put_mark(oid, ORDER, "cut", "DONE", name="김재단")  # 남은 '도면 없음' 카드 완료 줄
    put_mark(oid, key(oid, "s1"), "assemble", "NONE", picked=False, sheet_id="s1")  # 맡았다 취소한 줄(미정)
    new = _arrive(client, team, oid, ("s0",), ack_worked=["sheet:s0"])
    rows = marks(oid)
    now_keys = [new[0], key(oid, "s1")]
    assert [(rows[(k, "cut")].state, rows[(k, "cut")].done_by_name) for k in now_keys] == [("DONE", "김재단")] * 2
    assert [rows[(k, "assemble")].state for k in now_keys] == ["DONE", "DONE"] and rows[(ORDER, "cut")].state == "NONE"
    assert step(oid, "cut")["done"] is True and step(oid, "assemble")["done"] is True


# --------------------------------------------------------------------------- #
# ⓑ 검토 6 — 작업 시트 바뀐 기록
# --------------------------------------------------------------------------- #
def _log(tmp_path: Path, items: list[dict], keys: list[str]) -> list[str]:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    page = tmp_path / "blank.html"
    page.write_text("<html><body></body></html>", encoding="utf-8")
    proc = subprocess.run([node, str(NODE_CHECK), str(page), json.dumps({"log_only": items, "keys": keys}, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["log"]


def _items(client, oid: int) -> list[dict]:
    login(client, make_user("박반장", lead=True))
    return client.get(HISTORY, query_string={"order_id": oid}).get_json()["data"]["items"]


def test_history_heads_the_order_card_as_no_drawing_and_hides_the_clear_line(client, quiet, team, tmp_path):
    oid = make_order(0)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "cut", "take", "none")
    _press(client, kim, oid, "cut", "done", "need")
    db_session.expire_all()
    keys = sheet_part_extras(db_session.get(Order, oid).structured_data, order_marks(db_session, oid))["current_keys"]
    assert keys == [ORDER]  # 0장 + @order 줄 = part_progress.sheet_keys 와 같은 꼴
    lines = _log(tmp_path, [i for i in _items(client, oid) if i["kind"] != "step_on"], keys)
    assert len(lines) == 1 and lines[0].startswith("재단 도면 없음: 김재단 시작 ")  # "옛 도면" 이 아니다
    new = _arrive(client, team, oid)
    items = _items(client, oid)
    assert [i["kind"] for i in items if i["via"] == VIA_ORDER_CARD] == ["done", "done"]  # 미정 돌리기 줄(order_card)은 안 보임
    lines = _log(tmp_path, [i for i in items if i["kind"] != "step_on"], new)
    assert [line.split(":")[0] for line in lines] == ["재단 도면 없음", "재단 도면 1/2", "재단 도면 2/2"]
    assert not any("order_card" in line for line in lines)
