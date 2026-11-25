"""생산 넘어간 주문의 도면 수정 D1 — 자료 · 막힘 판정(도면별)(설계서 2026-11-25 §3-2 · §3-3 · §3-7 · §3-8 · §4-3 · C3 · C5).

* 열쇠 = ``sheet:<시트 id>`` 또는 ``file:<저장 key>``(``drawing_fix.fix_ident`` 하나 — 공장 꼴 패킹 줄 열쇠와 같은 꼴).
* 통째 = 지금 그대로(TRANSFERRED · 대상을 못 고른 RETURNED · 고객컨펌 단계 요청 · 지금 도면 전부를 가리킨 요청). 도면별 = 생산 · 시공
  단계에서 대상을 고른 영업 요청(``target_idents`` · 옛 줄은 ``target_drawing_keys`` 를 그때 풂) ∪ ``drawing_fix.fixing`` ∪ 열린 공장 요청.
* 막는 문: 도면 누름(그 장만) · 도면 판 · PC 창 줄(그 장만) · [제작 완료](막힌 도면 하나라도) · [N공장 완료](그 공장 · 마지막이면 하나라도) ·
  공장 꼴 패킹 줄(체크 · 풀기 모두 409, 출발 보고 뒤는 그대로). [제작 시작] · [수정 제작] · 배지 시작 막힘은 통째만, ERP 보드 단계 칸은
  영업 요청이 걸려 있으면 지금처럼 "도면 수정 중"(판결 F). 관리자 뚫기 그대로.
* ``drawing_fix`` 는 서버 소유 — 폼 저장 · 초안 자동 저장 · 주문 만들기가 못 덮는다.

되돌리면 실패: 대상 1장 요청이 주문 통째를 막음 · 고객컨펌 단계 요청이 도면별 · 막힌 도면이 있는데 제작 완료 200 · 남의 공장 막힘으로 내
공장 완료가 막힘 · 막힌 패킹 줄 체크 200 · 폼 저장이 ``drawing_fix`` 를 지움. 대조군: 막힌 도면 없는 주문 · 다른 장 · 1공장뿐 패킹.
이름은 모두 지어낸 값이다. 날짜는 오늘(KST)에서 센다.
"""
from __future__ import annotations

import copy
import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders import drawing_fix as fx
from foms.services.orders.board_state_display import build_board_state
from foms.services.orders.confirm_drawing_gate import (
    drawing_revision_in_progress,
    production_drawing_badge,
    production_start_block,
    revision_in_flight_block,
    revision_status_block,
)
from foms.services.orders.drawing_factory import strip_client_factory_state
from foms.services.orders.order_create import _prepare_structured
from foms.services.orders.structured_form_projection import SERVER_LOCKED_KEYS, lock_server_owned_keys
from foms.services.production.part_card_state import order_block
from foms.services.production.part_mark_gates import DRAWING_REVISING, REVISING_MESSAGE, order_gate
from foms.services.production.pc_sheet import build_part_sheet
from foms.services.production_drawing_gate_display import attach_production_drawing_gate
from foms.services.production_home_read_model import production_home_step_queues
from foms.services.shipment import packing_factory as pf
from models import Order, User
from tests.support.production_factory_seed import mixed_order, set_factory_done
from tests.support.production_part_claim_seed import code, fresh, login, make_order, make_user, mark
from tests.support.production_steps_seed import mark_order_inspected

FIX = {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}


def _files(n: int, direct: int = 0) -> list[dict]:
    files = [{"key": f"orders/9/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"s{j}"} for j in range(n)]
    return files + [{"key": f"orders/9/up{j}.pdf", "filename": f"up{j}.pdf"} for j in range(direct)]


def _sd(n: int = 3, *, stage: str = "PRODUCTION", status: str = "CONFIRMED", targets=None, idents=None, fixing=(),
        requests=(), factory2=(), direct: int = 0) -> dict:
    """주문 JSON — ``targets`` = 영업 요청 대상 장 번호(0부터), ``fixing`` = 고치는 중인 장 번호(0부터)."""
    files = _files(n, direct)
    sd = {"workflow": {"stage": stage}, "drawing_status": status, "drawing_current_files": files}
    if targets is not None:
        line = {"action": "REQUEST_REVISION", "note": "치수", "target_drawing_keys": [files[j]["key"] for j in targets] or None}
        if idents is not None:
            line["target_idents"] = idents
        sd["drawing_transfer_history"] = [{"action": "TRANSFER", "files": files}, line]
    fix: dict = {}
    if fixing:
        fix["fixing"] = {fx.fix_ident(files[j]): dict(FIX, no=j + 1) for j in fixing}
    if requests:
        fix["requests"] = list(requests)
    if fix:
        sd["drawing_fix"] = fix
    if factory2:
        sd["drawing_factory"] = {"sheets": {f"s{j}": 2 for j in factory2}, "files": {}}
    return sd


def _patch(oid: int, **top) -> None:
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd.update(top)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _fixing(oid: int, *indexes: int) -> None:
    """도면팀 [수정 시작]을 자료로 직접 심는다(N1 은 D3 몫 — 이 묶음은 읽기만)."""
    files = fresh(oid).structured_data["drawing_current_files"]
    _patch(oid, drawing_fix={"fixing": {fx.fix_ident(files[j]): dict(FIX, no=j + 1) for j in indexes}})


# --------------------------------------------------------------------------- #
# 열쇠 · 통째 / 도면별
# --------------------------------------------------------------------------- #
def test_ident_is_sheet_then_file_and_matches_packing_line_keys():
    assert fx.fix_ident({"sheet_id": "s1", "key": "k"}) == "sheet:s1"
    assert fx.fix_ident({"key": " orders/9/up.pdf "}) == "file:orders/9/up.pdf"
    assert fx.fix_ident({"sheet_id": "모양 다름!", "key": "k"}) == "file:k"  # 시트 신원 모양이 다르면 파일 열쇠
    assert fx.fix_ident({}) == "" and fx.fix_ident(None) == ""
    sd = _sd(3, direct=1, factory2=(2,))
    assert [key for key, _e, _f in pf.doc_line_keys(sd)] == [fx.fix_ident(e) for e in resolve_final_drawing_files(sd)]
    assert fx.idents_for_keys(sd, ["orders/9/d2.png", "없는.png", "orders/9/up0.pdf"]) == ["sheet:s2", "file:orders/9/up0.pdf"]


def test_production_sales_request_blocks_only_the_requested_drawing():
    for stage in ("PRODUCTION", "생산", "CONSTRUCTION"):
        sd = _sd(3, stage=stage, status="RETURNED", targets=[1], idents=["sheet:s1"])
        block = fx.blocked(sd)
        assert (block.whole, block.idents, block.why) == (False, frozenset({"sheet:s1"}), {"sheet:s1": ("sales",)})
        assert drawing_revision_in_progress(sd) is False and revision_in_flight_block(sd) is None  # '통째'만 뜻한다
        assert production_drawing_badge(sd) is None
    assert production_start_block("PRODUCTION", sd) is None  # [제작 시작]은 통째만(답 2 "나머지는 계속 작업")
    files = sd["drawing_current_files"]
    assert [row["no"] for row in fx.blocked_entries(sd)] == [2] and fx.per_drawing_numbers(sd) == [2]
    assert fx.drawing_blocked(sd, files[1]) and not fx.drawing_blocked(sd, files[0])
    gate = order_gate(sd, "take", files[1])
    assert (gate.status, gate.code, gate.message, gate.extra) == (409, DRAWING_REVISING, REVISING_MESSAGE, {"numbers": [2]})
    assert order_gate(sd, "take", files[0]) is None and order_gate(sd, "done", files[2]) is None  # 다른 장은 계속 작업
    assert order_gate(sd, "undo", files[1]) is None and order_gate(sd, "release", files[1]) is None  # 완료 취소 · 맡기 취소는 된다
    assert order_gate(sd, "take") is None  # 장을 안 주면 통째만 본다


@pytest.mark.parametrize("sd", [
    _sd(3, stage="CONFIRM", status="RETURNED", targets=[1], idents=["sheet:s1"]),  # 고객컨펌 단계는 지금처럼 통째
    _sd(3, stage="고객컨펌", status="RETURNED", targets=[1]),
    _sd(3, status="RETURNED", targets=[]),  # 대상 없는 요청
    _sd(3, status="RETURNED", targets=[0, 1, 2]),  # 지금 도면 전부 = 안 고른 요청과 같다
    _sd(1, status="RETURNED", targets=[0]),  # 도면 1장 주문(서버가 그 장을 저절로 고른다)
    _sd(3, status="RETURNED"),  # 요청 줄이 없는 옛 자료
    _sd(3, status="TRANSFERRED", targets=[1]),  # 옛 자료 — 지금 그대로
], ids=["confirm-stage", "confirm-korean", "no-target", "all-targets", "one-drawing", "no-line", "transferred"])
def test_whole_block_stays_exactly_like_today(sd):
    block = fx.blocked(sd)
    assert block.whole is True and drawing_revision_in_progress(sd) is True
    assert block.idents == frozenset()  # 이 경우들에는 도면별 까닭(고치는 중 · 공장 요청)이 없다 — 대상 고른 영업 요청도 통째로 돌아간다
    gate = order_gate(sd, "take", sd["drawing_current_files"][0])
    assert (gate.code, gate.message, gate.extra) == (DRAWING_REVISING, REVISING_MESSAGE, {})  # 지금 거절 꼴 그대로(numbers 없음)
    assert fx.per_drawing_numbers(sd) == [] and fx.complete_blocked(sd) and fx.factory_has_blocked(sd, 1)


def test_old_request_line_resolves_keys_now_and_unresolvable_is_whole():
    old = _sd(3, status="RETURNED", targets=[2])  # target_idents 없는 옛 줄 → 지금 도면으로 푼다
    assert fx.blocked(old).idents == {"sheet:s2"} and fx.blocked(old).whole is False
    direct = _sd(2, status="RETURNED", targets=[2], direct=1)  # 직접 올린 파일 = 파일 열쇠
    assert fx.blocked(direct).idents == {"file:orders/9/up0.pdf"}
    gone = _sd(3, status="RETURNED", targets=[1])
    gone["drawing_transfer_history"][-1]["target_drawing_keys"] = ["orders/9/지금은없음.png"]
    assert fx.blocked(gone).whole is True and fx.blocked(gone).idents == frozenset()  # 못 풀면 통째
    single = _sd(3, status="RETURNED")
    single["drawing_transfer_history"] = [{"action": "REQUEST_REVISION", "target_drawing_key": "orders/9/d0.png"}]
    assert fx.blocked(single).idents == {"sheet:s0"}  # 옛 단일 칸도 푼다
    stored = _sd(3, status="RETURNED", targets=[1], idents=["sheet:s1"])
    assert fx.sales_request_idents(stored) == {"sheet:s1"}


def test_fixing_and_open_factory_requests_block_only_in_production_and_construction():
    open_req = {"id": "fr_1", "from": "factory", "targets": ["sheet:s2"], "state": "open"}
    sd = _sd(3, status="RETURNED", targets=[0], fixing=(0, 1), requests=[open_req, dict(open_req, id="fr_2", targets=["sheet:s1"],
                                                                                       state="rejected")])
    block = fx.blocked(sd)
    assert block.idents == {"sheet:s0", "sheet:s1", "sheet:s2"}
    assert block.why == {"sheet:s0": ("sales", "fixing"), "sheet:s1": ("fixing",), "sheet:s2": ("factory",)}
    done = _sd(3, requests=[dict(open_req, state="done")])
    assert fx.blocked(done) == fx.Block(False)  # 반영 · 반려된 요청은 막지 않는다
    for stage in ("CONFIRM", "DRAWING", "CS"):  # 생산 · 시공 단계가 아니면 도면별은 안 본다(강제 단계 변경 뒤 남은 자료)
        stale = _sd(3, stage=stage, fixing=(1,), requests=[open_req])
        assert fx.blocked(stale) == fx.Block(False) and order_gate(stale, "take", stale["drawing_current_files"][1]) is None
    assert fx.blocked(_sd(3, stage="CONSTRUCTION", fixing=(1,))).idents == {"sheet:s1"}


def test_factory_scoped_judgment_for_factory_done_and_complete():
    sd = _sd(4, factory2=(2, 3), fixing=(2,))  # 도면 3 = 2공장, 고치는 중
    assert fx.factory_has_blocked(sd, 2) and not fx.factory_has_blocked(sd, 1)
    assert fx.per_drawing_numbers(sd, factory=2) == [3] and fx.per_drawing_numbers(sd, factory=1) == []
    assert fx.complete_blocked(sd)
    assert fx.factory_complete_blocked(sd, 1, final=False) is False  # 남의 공장 막힘으로 내 공장 완료가 막히지 않는다
    assert fx.factory_complete_blocked(sd, 1, final=True) is True  # 마지막 공장 = 주문 제작 완료 — 하나라도 막히면
    free = _sd(4, factory2=(2, 3))
    assert not fx.complete_blocked(free) and not fx.factory_has_blocked(free, 2)


def test_new_words_and_particles():
    assert [fx.number_topic(n) for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12)] == list("은는은는는은은은는은는")
    assert fx.fixing_label([2]) == "도면 2 고치는 중" and fx.fixing_label([2, 3]) == "도면 2 · 3 고치는 중"
    assert fx.skip_tail([2]) == "도면 2는 고치는 중이라 빼요." and fx.skip_tail([2, 3]) == "도면 2 · 3은 고치는 중이라 빼요."
    assert fx.expand_confirm_body(5, 4, "재단", [2]) == "이 주문의 도면 5장 중 4장이 재단 완료로 처리돼요. 도면 2는 고치는 중이라 빼요."


# --------------------------------------------------------------------------- #
# 화면 판정(쿼리 0 — 이미 든 주문 JSON)
# --------------------------------------------------------------------------- #
def test_board_pc_rows_queue_row_and_badge_mark_only_that_drawing():
    sd = _sd(3, status="RETURNED", targets=[1])
    files = sd["drawing_current_files"]
    row = {"id": 7, "structured_data": sd}
    assert order_block(row) is None  # 주문 통째 막힘 없음(공정 줄 · PC 창 머리)
    assert order_block(row, files[1]) == {"kind": "revise", "text": "도면 고치는 중", "why": REVISING_MESSAGE, "code": DRAWING_REVISING}
    assert order_block(row, files[0]) is None and order_block(row, files[2], fix=fx.blocked(sd)) is None
    sheet = build_part_sheet(sd, [], "cut", hold_active=False)
    assert [r["block"]["text"] if r["block"] else None for r in sheet["rows"]] == [None, "도면 고치는 중", None]
    assert [r["act"] for r in sheet["rows"]] == ["check", None, "check"]
    assert sheet["all"] is True  # 도면별이면 [모두 작업]이 보인다(같은 API 가 막힌 장을 빼고 처리)
    whole = _sd(3, status="RETURNED")
    assert build_part_sheet(whole, [], "cut", hold_active=False)["all"] is False  # 대조군: 통째면 지금처럼 숨김
    steps = [{"key": k, "label": k, "done": False, "now": k == "cut"} for k in ("cut", "edge", "assemble", "inspect")]
    rows = [{"id": i, "home_view": "prod", "home_has_run": True, "raw_stage": "PRODUCTION", "home_steps": steps,
             "structured_data": {**s, "production": {"steps": steps}}} for i, s in ((1, sd), (2, whole), (3, _sd(3)))]
    cut = production_home_step_queues(rows)["queues"][0]["rows"]  # 표시 줄 없이(쿼리 0) — 도면별은 [끝] 그대로, 통째만 지금 막힘
    assert [(r["revise_block"] or {}).get("text") for r in cut] == [None, "도면 고치는 중", None]
    assert all("fix_note" not in r for r in cut)  # 판에 싣기만 하고 안 그리던 칸은 없앴다(판결 D)
    board = [{"id": i, "stage": "제작중"} for i in (1, 2, 3)]
    attach_production_drawing_gate(None, board, {i: SimpleNamespace(structured_data=s, erp_stage_code="PRODUCTION")
                                                 for i, s in ((1, sd), (2, whole), (3, _sd(3)))})
    assert board[0]["drawing_badge"] == {"label": "도면 2 고치는 중", "title": REVISING_MESSAGE, "drawing_status": "RETURNED"}
    assert board[1]["drawing_badge"]["label"] == "도면 수정 중" and board[2]["drawing_badge"] is None  # 통째는 지금 글


# --------------------------------------------------------------------------- #
# C3 · 쓰기 문(API)
# --------------------------------------------------------------------------- #
@pytest.fixture
def quiet(monkeypatch):
    """폰 알림 · 실시간 알림을 끈다(발송 없음)."""
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification", lambda *a, **k: None)
    monkeypatch.setattr("foms.api.drawing.erp_orders_revision.emit_erp_notification_to_users", lambda *a, **k: None)


def test_request_revision_writes_target_idents_and_blocks_only_that_card(client, quiet):
    seed = make_order(3, extra={"drawing_status": "CONFIRMED"})
    sids = [f["sheet_id"] for f in fresh(seed.id).structured_data["drawing_current_files"]]
    admin = make_user("가짜관리", team="CS", role="ADMIN")
    login(client, admin)
    res = client.post(f"/api/orders/{seed.id}/request-revision", json={"note": "측판 길이", "target_drawing_keys": [seed.keys[1]]})
    assert res.status_code == 200, res.get_json()
    sd = fresh(seed.id).structured_data
    line = sd["drawing_transfer_history"][-1]
    assert sd["drawing_status"] == "RETURNED" and line["target_idents"] == [f"sheet:{sids[1]}"]
    assert line["target_drawing_numbers"] == [2]  # 지금 칸은 그대로
    login(client, make_user("가짜재단", part="cut"))
    blocked = mark(client, seed, 1, "cut", "take", "none")
    assert blocked.status_code == 409 and code(blocked) == DRAWING_REVISING and blocked.get_json()["data"]["numbers"] == [2]
    assert blocked.get_json()["error"] == REVISING_MESSAGE
    assert mark(client, seed, 0, "cut", "take", "none").status_code == 200  # 다른 장은 계속 작업(답 2)
    login(client, admin)  # 요청 고치기로 대상이 바뀌면 열쇠도 같이 바뀐다
    edit = client.post(f"/api/orders/{seed.id}/request-revision/edit", json={"target_drawing_keys": [seed.keys[2]]})
    assert edit.status_code == 200, edit.get_json()
    assert fresh(seed.id).structured_data["drawing_transfer_history"][-1]["target_idents"] == [f"sheet:{sids[2]}"]
    login(client, make_user("가짜재단둘", part="cut"))
    assert mark(client, seed, 1, "cut", "take", "none").status_code == 200
    assert code(mark(client, seed, 2, "cut", "take", "none")) == DRAWING_REVISING


def test_request_in_confirm_stage_still_blocks_the_whole_order(client, quiet):
    seed = make_order(3, extra={"drawing_status": "CONFIRMED", "workflow": {"stage": "CONFIRM"}})
    login(client, make_user("가짜관리", team="CS", role="ADMIN"))
    assert client.post(f"/api/orders/{seed.id}/request-revision",
                       json={"note": "문 위치", "target_drawing_keys": [seed.keys[1]]}).status_code == 200
    sd = fresh(seed.id).structured_data
    assert sd["drawing_transfer_history"][-1]["target_idents"]  # 적어는 둔다 — 판정은 단계가 생산 · 시공일 때만 도면별
    assert drawing_revision_in_progress(sd) is True and fx.blocked(sd).idents == frozenset()


def test_complete_is_refused_while_any_drawing_is_blocked_and_admin_punch_stays(client):
    seed = make_order(3)
    mark_order_inspected(seed.id)
    _fixing(seed.id, 1)
    boss = make_user("가짜반장", lead=True)
    login(client, boss)
    before = (fresh(seed.id).erp_stage_code, fresh(seed.id).mutation_version)
    res = client.post(f"/api/orders/{seed.id}/production/complete", json={})
    body = res.get_json()
    assert res.status_code == 409 and body["code"] == DRAWING_REVISING and body["numbers"] == [2]
    assert body["message"] == REVISING_MESSAGE and (fresh(seed.id).erp_stage_code, fresh(seed.id).mutation_version) == before
    login(client, make_user("가짜관리", team="CS", role="ADMIN"))
    punched = client.post(f"/api/orders/{seed.id}/production/complete",
                          json={"admin_override": True, "override_reason": "시험 — 도면 고치는 중 건너뜀"})
    assert punched.status_code == 200 and fresh(seed.id).erp_stage_code == "CONSTRUCTION"  # 관리자 뚫기 그대로
    free = make_order(3)
    mark_order_inspected(free.id)
    login(client, boss)
    assert client.post(f"/api/orders/{free.id}/production/complete", json={}).status_code == 200  # 대조군


def test_factory_done_is_refused_only_for_the_factory_with_a_blocked_drawing(client):
    admin = make_user("가짜관리", team="CS", role="ADMIN")
    seed = mixed_order(4, f2=(2, 3))  # 도면 3 · 4 = 2공장
    mark_order_inspected(seed.id)
    _fixing(seed.id, 2)  # 도면 3(2공장) 고치는 중
    login(client, admin)
    res = client.post(f"/api/orders/{seed.id}/production/factory-done", json={"factory": 2, "done": True})
    body = res.get_json()
    assert res.status_code == 409 and body["data"]["code"] == DRAWING_REVISING and body["data"]["numbers"] == [3]
    assert body["error"] == REVISING_MESSAGE
    ok = client.post(f"/api/orders/{seed.id}/production/factory-done", json={"factory": 1, "done": True})
    assert ok.status_code == 200 and ok.get_json()["data"]["final"] is False  # 남의 공장 막힘으로 내 공장은 안 막힌다
    last = mixed_order(4, f2=(2, 3))
    mark_order_inspected(last.id)
    set_factory_done(last.id, 2, last.keys[2:])
    _fixing(last.id, 0)  # 이미 완료한 2공장이 아니라 1공장 도면 1 — 1공장이 마지막(= 주문 제작 완료)
    refused = client.post(f"/api/orders/{last.id}/production/factory-done", json={"factory": 1, "done": True})
    assert refused.status_code == 409 and refused.get_json()["data"]["numbers"] == [1]
    _patch(last.id, drawing_fix={})
    final = client.post(f"/api/orders/{last.id}/production/factory-done", json={"factory": 1, "done": True})
    assert final.status_code == 200 and final.get_json()["data"]["final"] is True  # 대조군: 막힘이 풀리면 마지막 공장 완료


# --------------------------------------------------------------------------- #
# C5 패킹 · 풀기 함수
# --------------------------------------------------------------------------- #
def _packing_order(*, f2=(2,)) -> int:
    today = get_today_kst().isoformat()
    sd = _sd(3, stage="CONSTRUCTION", fixing=(1,), factory2=f2)
    sd["items"] = [{"product_name": "가짜장"}]
    order = Order(received_date=today, customer_name="가짜고객", phone="010-0000-0000", address="가짜시", product="가짜장",
                  status="CONSTRUCTION", scheduled_date=today, is_erp_order=True, erp_stage_code="CONSTRUCTION",
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id


def _admin(client) -> None:
    user = User(username=f"fx-admin-{datetime.datetime.now().timestamp()}", password=generate_password_hash("x"), role="ADMIN",
                team="CS", name="가짜관리", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = user.id, user.username, user.role


def test_packing_line_of_a_blocked_drawing_is_refused_both_ways(client):
    _admin(client)
    oid = _packing_order()
    url = f"/api/erp/shipment/packing/{oid}"
    keys = [i["key"] for i in client.get(url).get_json()["data"]["items"]]
    assert keys[:2] == ["sheet:s0", "sheet:s1"]
    for on in (True, False):
        res = client.post(url, json={"updates": [{"key": "sheet:s1", "checked": on}]})
        body = res.get_json()
        assert res.status_code == 409 and body["data"]["code"] == DRAWING_REVISING and body["data"]["numbers"] == [2]
        assert body["error"] == REVISING_MESSAGE
    assert "packing" not in (fresh(oid).structured_data.get("shipment") or {})  # 아무것도 안 씀
    assert client.post(url, json={"updates": [{"key": "sheet:s0", "checked": True}]}).status_code == 200  # 다른 장 줄은 된다
    assert client.post(url, json={"updates": [{"key": "hardware:1", "checked": True}]}).status_code == 200
    single = _packing_order(f2=())  # 1공장뿐 주문 = 제품마다 3줄 — 도면 줄이 없어 그대로
    assert client.post(f"/api/erp/shipment/packing/{single}",
                       json={"updates": [{"key": "item0_body", "checked": True}]}).status_code == 200


def test_release_packing_checks_clears_changed_drawing_lines_until_departure():
    def sd(departed=None):
        items = [{"key": k, "checked": True, "at": "2026-11-25T01:00:00+00:00", "by_name": "김시공"}
                 for k in ("sheet:s1", "sheet:s1:2", "sheet:s0", "file:orders/9/up0.pdf", "hardware:1")]
        return {"shipment": {"packing": {"items": items, "layout": "factory", "departed_at": departed}}}

    data = sd()
    assert pf.release_packing_checks(data, ["sheet:s1", "file:orders/9/up0.pdf"]) == ["sheet:s1", "sheet:s1:2",
                                                                                     "file:orders/9/up0.pdf"]
    items = {i["key"]: i for i in data["shipment"]["packing"]["items"]}
    assert items["sheet:s1"] == {"key": "sheet:s1", "checked": False, "at": None, "by_name": None}
    assert items["sheet:s0"]["checked"] and items["hardware:1"]["checked"]  # 안 바뀐 장 · 철물 줄은 그대로
    gone = sd(departed="2026-11-25T02:00:00+00:00")
    assert pf.release_packing_checks(gone, ["sheet:s1"]) == [] and gone == sd(departed="2026-11-25T02:00:00+00:00")
    assert pf.release_packing_checks({}, ["sheet:s1"]) == [] and pf.release_packing_checks(sd(), []) == []


# --------------------------------------------------------------------------- #
# §3-8 잠금 칸
# --------------------------------------------------------------------------- #
SERVER_FIX = {"fixing": {"sheet:s1": FIX}, "requests": [], "log": [{"act": "start", "idents": ["sheet:s1"], "numbers": [2],
                                                                   "by_name": "김도면", "at": FIX["at"]}]}


def test_form_save_draft_and_create_cannot_write_drawing_fix(client):
    assert "drawing_fix" in SERVER_LOCKED_KEYS
    stale = {"drawing_fix": {"fixing": {}}, "notes": "폼 값"}
    assert lock_server_owned_keys({"drawing_fix": SERVER_FIX}, stale) == ["drawing_fix"] and stale["drawing_fix"] == SERVER_FIX
    planted = {"drawing_fix": {"fixing": {"sheet:x": FIX}}}
    assert lock_server_owned_keys({}, planted) == ["drawing_fix"] and "drawing_fix" not in planted  # 폼이 새로 심지 못함
    raw = {"drawing_fix": SERVER_FIX, "drawing_factory": {"sheets": {}}, "items": []}
    assert strip_client_factory_state(raw) == ["drawing_factory", "drawing_fix"] and raw == {"items": []}
    made = _prepare_structured({"drawing_fix": SERVER_FIX}, 1, datetime.datetime.combine(get_today_kst(), datetime.time()))
    assert "drawing_fix" not in made
    seed = make_order(3, extra={"drawing_fix": SERVER_FIX, "parties": {"customer": {"name": "가짜고객", "phone": "010-0000-0000"}},
                                "site": {"address_full": "가짜시 1"}, "items": [{"product_name": "가짜장", "spec_width": "2400"}]})
    _admin(client)
    snap = client.get(f"/api/orders/{seed.id}/structured").get_json()["structured_data"]
    snap["drawing_fix"] = {"fixing": {}}
    snap["notes"] = "특이사항 고침"
    res = client.put(f"/api/orders/{seed.id}/structured", json={"structured_data": snap})
    assert res.status_code == 200, res.get_json()
    saved = fresh(seed.id).structured_data
    assert saved["drawing_fix"] == SERVER_FIX and saved["notes"] == "특이사항 고침"
    auto = client.post("/api/orders/erp/draft/autosave", json={"structured_data": {
        "parties": {"customer": {"name": "가짜초안", "phone": "010-1111-2222"}}, "items": [{"product_name": "가짜장"}],
        "drawing_fix": SERVER_FIX}})
    assert auto.status_code == 200 and "drawing_fix" not in fresh(auto.get_json()["order_id"]).structured_data


# --------------------------------------------------------------------------- #
# 판결 F · H · D 판정
# --------------------------------------------------------------------------- #
def test_erp_board_still_says_revising_while_a_sales_request_is_open(app):
    """판결 F — ERP 보드 단계 칸은 영업 요청이 걸려 있는 동안 지금처럼 "도면 수정 중 · 도면 작업실 열기"(대상이 몇 장이든)."""
    viewer = SimpleNamespace(id=1, role="ADMIN", team=None)
    with app.test_request_context():
        for sd in (_sd(3, status="RETURNED", targets=[1]), _sd(3, status="RETURNED"), _sd(3, status="TRANSFERRED")):
            state = build_board_state(SimpleNamespace(id=7), sd, "PRODUCTION", viewer=viewer)
            assert (state["tone"], state["title"], state["link_label"]) == ("warn", "도면 수정 중" if sd["drawing_status"] == "RETURNED"
                                                                           else "새 도면 확정 필요", "도면 작업실 열기")
            assert revision_status_block(sd) is not None
        targeted = _sd(3, status="RETURNED", targets=[1])
        assert revision_in_flight_block(targeted) is None  # [제작 시작] · [수정 제작] 문은 지금 구현 그대로(통째만)
        quiet = build_board_state(SimpleNamespace(id=7), _sd(3, fixing=(1,)), "PRODUCTION", viewer=viewer)
        assert quiet["tone"] == "soft" and quiet["link_label"] == "생산 화면 열기"  # 대조군: 영업 요청 없음(고치는 중만) = 지금 그대로


def test_left_only_blocked_numbers_decide_the_finish_slot():
    sd = _sd(3, fixing=(1,))
    assert fx.blocked_left_numbers(sd, ["orders/9/d1.png"]) == [2]  # 남은 장 = 고치는 도면뿐
    assert fx.blocked_left_numbers(sd, ["orders/9/d0.png", "orders/9/d1.png"]) == []  # 처리할 장이 있다 → [끝]
    assert fx.blocked_left_numbers(sd, []) == []  # 남은 장 없음
    assert fx.blocked_left_numbers(_sd(3, status="RETURNED"), ["orders/9/d1.png"]) == []  # 통째는 지금 막힘이 맡는다
    assert fx.blocked_left_numbers(_sd(3), ["orders/9/d1.png"]) == []  # 대조군: 막힘 없음


def test_packing_after_departure_is_not_refused_and_one_predicate_decides(client):
    _admin(client)
    oid = _packing_order()
    url = f"/api/erp/shipment/packing/{oid}"
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["shipment"] = {"packing": {"items": [{"key": "sheet:s1", "checked": True, "at": "2026-11-25T01:00:00+00:00",
                                             "by_name": "김시공"}], "layout": "factory",
                                  "departed_at": "2026-11-25T02:00:00+00:00", "departed_by_name": "김시공"}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    res = client.post(url, json={"updates": [{"key": "sheet:s1", "checked": False}]})
    assert res.status_code == 200, res.get_json()  # 출발 보고 뒤는 그대로(사장님 답 Q10) — 막힌 줄도 409 없음
    whole = _sd(3, stage="CONSTRUCTION", status="RETURNED", factory2=(2,))
    block = fx.blocked(whole)
    assert all(pf.line_revising(block, e) for e in whole["drawing_current_files"])  # 지금: 통째도 도면 줄을 막는다(술어 한 곳)
    assert pf.line_revising(fx.blocked(_sd(3, fixing=(1,))), _files(3)[1]) and not pf.line_revising(fx.blocked(_sd(3)), _files(3)[1])
