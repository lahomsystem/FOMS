"""제품마다 시공 끝 — 화면 계약(설계서 docs/specs/2026-11-21-item-construction-done_SPEC.md 6절 · N2 · N3 · N9).

고정하는 것(스위치 켬 + 나눠 시공하는 주문에서만 바뀌고, 그 밖은 지금과 같다):
- 방문 열림 판정(workflow.history 의 "시공 시작" · "부분 시공 끝 …") · 상태 글 "부분 시공 · 남은 11/17".
- 시공 표시 단계: [오늘 시공 끝]으로 방문이 닫히면 "시공대기"(다음 방문은 [시공 시작]부터).
- PC · 폰 시공 목록에 나눠 시공 생산 단계 주문(남은 제품 · 오늘 이후 시공일)이 "생산 · 부분 시공"으로 든다(쿼리 +1 이하).
- 태블릿 상세: 나눠 시공 생산 단계 집에 [시공 시작] 단추 + "생산 중 — 먼저 시공하는 제품만 기록해요".
- 태블릿 첫 화면 줄: 끝난 제품 이름 뒤 " · 끝".
- 주문 화면 제품 줄 자료(#erp-items[data-item-construction-done]) · [되돌리기] 권한.
- 새 JS 두 파일이 300줄 래칫 아래이고 화면에 실린다.
대조군은 같은 자료 안에서 고른다(나눠 시공 아님 · 스위치 끔). 이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import datetime
import itertools
import json
import re
from pathlib import Path

import pytest
from flask import render_template
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.common import dashboard_cache as dc
from foms.services.construction import tablet_first as tf
from foms.services.construction_dashboard_display import build_construction_row_dtos
from foms.services.datetime_kst import get_today_kst
from foms.services.orders import item_construction_view as icv
from foms.services.orders.board_state_display import build_board_state, construction_display_stage
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]
URL = "/erp/construction/dashboard"
SHELL = {"X-FOMS-ERP-SHELL": "1"}
FLAG = "FOMS_ITEM_CONSTRUCTION_DONE_ENABLED"
UID_A = "11111111-1111-4111-8111-111111111111"
UID_B = "22222222-2222-4222-8222-222222222222"
_seq = itertools.count(1)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv(FLAG, raising=False)  # 기본 켜짐
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _d(n: int = 0) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _label(day: str) -> str:
    d = datetime.date.fromisoformat(day)
    return f"{d.month}/{d.day}"


def _split_sd(*, stage: str = "PRODUCTION", done: bool = True, history: list | None = None,
              first: str | None = None, last: str | None = None) -> dict:
    """제품 둘(부엌가구 · 화장대), 마지막 시공일이 다른 주문. done 이면 부엌가구에 '시공 끝'."""
    first = first or _d(-3)
    last = last or _d(5)
    sd = {
        "workflow": {"stage": stage, "history": history or []},
        "parties": {"customer": {"name": "가짜고객"}, "manager": {"name": "가짜영업"}},
        "site": {"address_full": "가짜시 가짜구 시공로 1"},
        "schedule": {"construction": {"date": f"{first},{last}"}},
        "items": [
            {"uid": UID_A, "product_name": "부엌가구", "construction_date": first},
            {"uid": UID_B, "product_name": "화장대", "construction_date": last},
        ],
    }
    if done:
        sd["item_construction_done"] = {UID_A: {"date": first, "at": first + "T17:40:00+09:00", "by_user_id": 1,
                                                "by_name": "가짜기사", "source": "visit", "attempt_id": None}}
    return sd


def _plain_sd(*, stage: str = "PRODUCTION") -> dict:
    """대조군 — 이틀 연속 시공(제품 칸 날짜 없음): 나눠 시공이 아니다."""
    return {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "가짜대조"}},
        "site": {"address_full": "가짜시 가짜구 시공로 2"},
        "schedule": {"construction": {"date": f"{_d(1)},{_d(2)}"}},
        "items": [{"uid": UID_A, "product_name": "부엌가구"}, {"uid": UID_B, "product_name": "화장대"}],
    }


_START = {"note": "시공 시작", "stage": "CONSTRUCTION"}
_PARTIAL = {"note": "부분 시공 끝 (부엌가구) — 남은 시공 11/17", "stage": "PRODUCTION"}


class _Row:
    def __init__(self, stage: str, sd: dict, oid: int = 1):
        self.id = oid
        self.erp_stage_code = stage
        self.structured_data = sd
        self.is_self_measurement = False
        self.is_erp_order = True


# ── 순수 판정 ───────────────────────────────────────────────────────────────

def test_visit_open_and_closed_by_history() -> None:
    assert not icv.visit_open({}) and not icv.partial_visit_closed({})
    opened = _split_sd(history=[_START])
    assert icv.visit_open(opened) and not icv.partial_visit_closed(opened)
    closed = _split_sd(history=[_START, _PARTIAL])
    assert not icv.visit_open(closed) and icv.partial_visit_closed(closed)
    again = _split_sd(history=[_START, _PARTIAL, _START])  # 다음 방문 [시공 시작]
    assert icv.visit_open(again) and not icv.partial_visit_closed(again)


def test_partial_board_label_only_when_partial_and_no_open_visit(monkeypatch) -> None:
    closed = _split_sd(stage="CONSTRUCTION", history=[_START, _PARTIAL])
    assert icv.partial_board_label(closed) == f"부분 시공 · 남은 {_label(_d(5))}"
    assert icv.partial_board_label(_split_sd(stage="CONSTRUCTION", history=[_START, _PARTIAL, _START])) is None
    assert icv.partial_board_label(_split_sd(done=False)) is None  # '시공 끝' 없음
    assert icv.partial_board_label(_plain_sd()) is None
    monkeypatch.setenv(FLAG, "0")
    assert icv.partial_board_label(closed) is None


def test_construction_display_stage_waits_after_partial_visit(monkeypatch) -> None:
    order = _Row("CONSTRUCTION", {})
    closed = _split_sd(stage="CONSTRUCTION", history=[_START, _PARTIAL])
    assert construction_display_stage(order, closed) == "시공대기"
    assert construction_display_stage(order, _split_sd(stage="CONSTRUCTION", history=[_START])) == "시공중"
    monkeypatch.setenv(FLAG, "0")  # 끄면 지금과 같다
    assert construction_display_stage(order, closed) == "시공중"


def test_board_state_text(monkeypatch) -> None:
    order = _Row("CONSTRUCTION", {})
    closed = _split_sd(stage="CONSTRUCTION", history=[_START, _PARTIAL])
    assert build_board_state(order, closed, "CONSTRUCTION")["label"] == f"부분 시공 · 남은 {_label(_d(5))}"
    assert build_board_state(order, _split_sd(stage="CONSTRUCTION", history=[_START]), "CONSTRUCTION")["label"] == "시공중"
    plain = _plain_sd(stage="CONSTRUCTION")
    plain["workflow"]["history"] = [_START]
    assert build_board_state(order, plain, "CONSTRUCTION")["label"] == "시공중"
    monkeypatch.setenv(FLAG, "0")
    assert build_board_state(order, closed, "CONSTRUCTION")["label"] == "시공중"


def test_production_split_listed() -> None:
    assert icv.production_split_listed(_Row("PRODUCTION", {}), _split_sd())
    assert not icv.production_split_listed(_Row("CONSTRUCTION", {}), _split_sd())  # 생산 단계만
    assert not icv.production_split_listed(_Row("PRODUCTION", {}), _plain_sd())
    gone = _split_sd(first=_d(-9), last=_d(-2))  # 남은 제품 시공일이 지났다
    assert not icv.production_split_listed(_Row("PRODUCTION", {}), gone)


def test_annotate_split_rows_production_row_gets_buttons(monkeypatch) -> None:
    rows = [{"stage": "생산중", "structured_data": _split_sd(), "tablet_note": "아직 생산 중이에요"},
            {"stage": "생산중", "structured_data": _plain_sd(), "tablet_note": "아직 생산 중이에요"},
            {"stage": "시공대기", "structured_data": _split_sd(stage="CONSTRUCTION", history=[_START, _PARTIAL])}]
    plain_before = dict(rows[1])
    icv.annotate_split_rows(rows, visit_date=_d(0))
    assert rows[0]["stage"] == "시공대기" and rows[0]["stage_text"] == icv.SPLIT_PRODUCTION_STAGE_TEXT
    assert rows[0]["split_production_note"] == "생산 중 — 먼저 시공하는 제품만 기록해요" and "tablet_note" not in rows[0]
    assert rows[0]["item_done_visit_date"] == _d(0)
    assert rows[1] == plain_before  # 나눠 시공 아님 — 손대지 않는다
    assert rows[2]["stage"] == "시공대기" and rows[2]["stage_text"].startswith("부분 시공 · 남은 ")

    opened = [{"stage": "생산중", "structured_data": _split_sd(history=[_START])}]
    icv.annotate_split_rows(opened)
    assert opened[0]["stage"] == "시공중"

    monkeypatch.setenv(FLAG, "0")
    off = [{"stage": "생산중", "structured_data": _split_sd(), "tablet_note": "아직 생산 중이에요"}]
    snap = json.dumps(off, sort_keys=True)
    icv.annotate_split_rows(off)
    assert json.dumps(off, sort_keys=True) == snap


def test_row_dtos_keep_split_production_only_when_listed(monkeypatch) -> None:
    monkeypatch.setattr("foms.services.construction_dashboard_display.build_measurement_manager_phone_map", dict)
    split, plain = _Row("PRODUCTION", _split_sd(), 1), _Row("PRODUCTION", _plain_sd(), 2)
    rows = build_construction_row_dtos([split, plain], {}, "")
    assert [r["id"] for r in rows] == [1] and rows[0]["stage"] == "생산중"
    monkeypatch.setenv(FLAG, "0")
    assert build_construction_row_dtos([split, plain], {}, "") == []


def test_tablet_first_product_text_marks_done_items(monkeypatch) -> None:
    class _R:
        def __init__(self, sd):
            self.structured_data = sd
            self.shipment_visible_items = sd["items"]
            self.product = "가짜장"

    assert tf._product_text(_R(_split_sd())) == "부엌가구 · 끝, 화장대"
    assert tf._product_text(_R(_split_sd(done=False))) == "부엌가구 외 1"  # 대조군: 지금 글 그대로
    monkeypatch.setenv(FLAG, "0")
    assert tf._product_text(_R(_split_sd())) == "부엌가구 외 1"


@pytest.mark.parametrize("role,team,stage,can", [
    ("ADMIN", None, "PRODUCTION", True), ("MANAGER", "SALES", "CONSTRUCTION", True),
    ("STAFF", "CS", "PRODUCTION", True), ("STAFF", "SALES", "PRODUCTION", False),
    ("VIEWER", "CS", "PRODUCTION", False), ("ADMIN", None, "CS", False),
])
def test_order_item_done_view_permissions(role, team, stage, can) -> None:
    order = _Row(stage, _split_sd(stage=stage), 7)
    user = User(role=role, team=team)
    view = icv.order_item_done_view(order, user)
    assert view["order_id"] == 7 and view["can_undo"] is can
    assert view["records"] == [{"uid": UID_A, "name": "부엌가구", "label": f"{_label(_d(-3))} 시공 끝"}]


def test_order_item_done_view_none_for_controls(monkeypatch) -> None:
    admin = User(role="ADMIN")
    assert icv.order_item_done_view(_Row("PRODUCTION", _split_sd(done=False)), admin) is None
    assert icv.order_item_done_view(_Row("PRODUCTION", _plain_sd()), admin) is None
    monkeypatch.setenv(FLAG, "0")
    assert icv.order_item_done_view(_Row("PRODUCTION", _split_sd()), admin) is None


# ── 화면(서버 렌더) ──────────────────────────────────────────────────────────

def _order(sd: dict, stage: str, days: list[str]) -> int:
    order = Order(received_date=_d(-10), customer_name="가짜고객", phone="010-0000-0000", address="가짜시 1",
                  product="가짜장", status=stage, manager_name="가짜영업", is_erp_order=True,
                  structured_data=sd, erp_stage_code=stage)
    db_session.add(order)
    db_session.flush()
    for day in days:
        if not db_session.query(OrderScheduleDate).filter_by(order_id=order.id, kind="construction", date=day).first():
            db_session.add(OrderScheduleDate(order_id=order.id, kind="construction", date=day, source="beta_schedule"))
    db_session.commit()
    return order.id


def _login(client, *, role: str = "ADMIN", team: str | None = "CS") -> User:
    n = next(_seq)
    user = User(username=f"ms2_e3_{n}", password=generate_password_hash("x"), role=role, team=team,
                name=f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


_PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
_PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}
_PHONE_UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"}


def _cookies(client, cookies: dict[str, str]) -> None:
    for name, value in cookies.items():
        client.set_cookie(name, value, domain="localhost")


def _count(fn):
    box = {"n": 0}

    def _before(*_a):
        box["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), box["n"]
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def test_pc_list_includes_split_production_order(client, monkeypatch) -> None:
    _login(client)
    _cookies(client, _PC)
    split = _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    plain = _order(_plain_sd(), "PRODUCTION", [_d(1), _d(2)])
    single = _order(_split_sd(done=False, first=_d(4), last=_d(4)), "PRODUCTION", [_d(4)])
    cons = _order(_plain_sd(stage="CONSTRUCTION"), "CONSTRUCTION", [_d(1), _d(2)])  # 켜고 끄고 늘 보이는 줄
    client.get(URL, headers=SHELL)  # warmup
    dc.reset_dashboard_cache_runtime_for_tests()

    (resp, q_on) = _count(lambda: client.get(URL, headers=SHELL))
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    row = body[body.index(f'<tr class="erp-main-row" data-order-id="{split}"'):]
    row = row[:row.index("</tr>")]
    assert ">생산 · 부분 시공</span>" in row and 'data-action="startConstruction"' in row
    for oid in (plain, single):  # 대조군: 나눠 시공 아님 · 시공일 하나
        assert f'data-order-id="{oid}"' not in body

    monkeypatch.setenv(FLAG, "0")
    dc.reset_dashboard_cache_runtime_for_tests()
    (resp_off, q_off) = _count(lambda: client.get(URL, headers=SHELL))
    off = resp_off.get_data(as_text=True)
    assert f'data-order-id="{split}"' not in off and "생산 · 부분 시공" not in off
    assert f'data-order-id="{cons}"' in off and f'data-order-id="{cons}"' in body
    assert q_on - q_off <= 1, (q_on, q_off)  # 켜면 후보 쿼리 하나만 더


def test_pc_list_query_count_flat_with_more_split_orders(client) -> None:
    _login(client)
    _cookies(client, _PC)
    _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    client.get(URL, headers=SHELL)  # warmup
    dc.reset_dashboard_cache_runtime_for_tests()
    _, small = _count(lambda: client.get(URL, headers=SHELL))
    for _ in range(6):
        _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    dc.reset_dashboard_cache_runtime_for_tests()
    resp, big = _count(lambda: client.get(URL, headers=SHELL))
    assert resp.get_data(as_text=True).count("생산 · 부분 시공") == 7
    assert big - small <= 2, (small, big)


def test_phone_queue_card_says_split_production(client, monkeypatch) -> None:
    user = _login(client)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _cookies(client, _PHONE)
    split = _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    plain = _order(_plain_sd(), "PRODUCTION", [_d(1), _d(2)])
    body = client.get(URL, headers=_PHONE_UA).get_data(as_text=True)
    card = body[body.index(f'data-order-id="{split}" data-workflow-stage'):]
    card = card[:card.index("</article>")]
    assert "생산 · 부분 시공" in card and 'data-action="startConstruction"' in card
    assert f'data-order-id="{plain}" data-workflow-stage' not in body


def _workmode(app, rows: list[dict]) -> str:
    with app.test_request_context("/erp/construction/dashboard"):
        return render_template("construction/partials/tablet_workmode_body.html", orders=rows,
                               cons_tablet={"mode": "detail", "detail": {"date": _d(0), "focus_id": rows[0]["id"]}},
                               can_act_construction=True, today_iso=_d(0), erp_mine_only=False, filters={})


def _dto(oid: int, sd: dict, stage: str = "생산중") -> dict:
    return {"id": oid, "structured_data": sd, "stage": stage, "customer_name": "가짜고객", "address": "가짜시 1",
            "construction_date": sd["schedule"]["construction"]["date"], "phone": "-", "attachment_preview_items": [],
            "tablet_note": "아직 생산 중이에요"}


def test_tablet_detail_draws_buttons_for_split_production(app) -> None:
    split, plain = _dto(1, _split_sd()), _dto(2, _plain_sd())
    icv.annotate_split_rows([split, plain], visit_date=_d(0))
    html = _workmode(app, [split, plain])
    panel = html[html.index('data-cwork-panel="1"'):html.index('data-cwork-panel="2"')]
    assert "생산 중 — 먼저 시공하는 제품만 기록해요" in panel and 'data-action="startConstruction"' in panel
    assert "data-cwork-fail" in panel and "아직 생산 중이에요" not in panel
    card = html[html.index('class="foms-cwork-card is-active"'):]
    assert f'data-visit-date="{_d(0)}"' in card[:card.index("</button>")] and "생산 · 부분 시공" in card
    other = html[html.index('data-cwork-panel="2"'):]
    other = other[:other.index('class="foms-cwork-viewer__empty"')]
    assert "아직 생산 중이에요" in other and 'data-action="startConstruction"' not in other  # 대조군
    assert "data-visit-date" not in html[html.index('data-order-id="2"'):html.index('data-order-id="2"') + 400]
    assert "style=" not in panel


def test_order_screen_items_carry_done_records_only_for_split(client, monkeypatch) -> None:
    _login(client, team="CS")
    split = _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    plain = _order(_plain_sd(), "PRODUCTION", [_d(1), _d(2)])
    html = client.get(f"/edit/{split}").get_data(as_text=True)
    m = re.search(r"<div id=\"erp-items\" data-item-construction-done='([^']+)'></div>", html)
    assert m, "제품 줄 자료가 없다"
    cfg = json.loads(m.group(1).replace("&#34;", '"'))
    assert cfg["order_id"] == split and cfg["can_undo"] is True and cfg["records"][0]["uid"] == UID_A
    assert "erp-item-construction-done.js" in html
    assert '<div id="erp-items"></div>' in client.get(f"/edit/{plain}").get_data(as_text=True)  # 대조군 그대로
    monkeypatch.setenv(FLAG, "0")
    assert "data-item-construction-done" not in client.get(f"/edit/{split}").get_data(as_text=True)


# ── 자산 ────────────────────────────────────────────────────────────────────

def test_new_js_files_under_ratchet_and_wired() -> None:
    for rel in ("static/js/construction/foms-visit-items.js", "static/js/orders/erp-item-construction-done.js"):
        assert len((ROOT / rel).read_text(encoding="utf-8").splitlines()) < 300, rel
    body = (ROOT / "templates/construction/partials/dashboard_body.html").read_text(encoding="utf-8")
    assert "js/construction/foms-visit-items.js') }}?v=" in body
    gate = (ROOT / "static/js/construction/foms-complete-gate.js").read_text(encoding="utf-8")
    dash = (ROOT / "static/js/construction/dashboard.js").read_text(encoding="utf-8")
    for js in (gate, dash):
        assert "done_item_uids" in js and "FomsVisitItems" in js
    shared = (ROOT / "static/js/construction/foms-visit-items.js").read_text(encoding="utf-8")
    assert "/construction/visit-items?date=" in shared and "오늘 시공 끝 — 남은 제품 " in shared
    assert "시공 남음" in shared
    css = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    block = css[css.index(".foms-visit-items {"):]
    assert "font-size: calc(" in block and not re.search(r"font-size:\s*\d+px", block)


# ── 교차 검수 고침(E3-1 ~ E3-7) ─────────────────────────────────────────────

def test_js_dom_checks_swap_block_retry_and_body() -> None:
    """가짜 DOM 위에서: 조각 교체 뒤 주문 B 줄에 글 · 옛 지켜보기 끊음(E3-1), 사유 200자(E3-3),
    체크 0개 끔 · 못 읽음 [다시 읽기](E3-5), 몸에 done_item_uids · visit_date(E3-2)."""
    import shutil
    import subprocess

    node = shutil.which("node")
    assert node, "node must be on PATH"
    proc = subprocess.run([node, str(ROOT / "tests/support/item_construction_dom_node_checks.js")], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 0 and "ITEM_DONE_DOM_OK" in proc.stdout, proc.stdout + proc.stderr


def test_complete_windows_send_visit_date_and_pc_lead_text() -> None:
    gate = (ROOT / "static/js/construction/foms-complete-gate.js").read_text(encoding="utf-8")
    dash = (ROOT / "static/js/construction/dashboard.js").read_text(encoding="utf-8")
    for js in (gate, dash):
        assert "FomsVisitItems.extendBody(" in js and ".blocked(" in js
    shared = (ROOT / "static/js/construction/foms-visit-items.js").read_text(encoding="utf-8")
    assert "body.visit_date = visitDate(orderId)" in shared
    modal = (ROOT / "templates/construction/partials/modals.html").read_text(encoding="utf-8")
    assert '<p class="mb-3" data-cons-complete-lead>시공을 완료하시겠습니까? (상태가 완료(AS대기)로 변경됩니다)</p>' in modal
    assert "주문은 지금 단계에 그대로 남아요" in dash and "leavesRemaining(modalEl)" in dash


@pytest.mark.parametrize("role,team,can", [
    ("ADMIN", None, True), ("MANAGER", "SALES", True), ("STAFF", "CS", True), ("STAFF", "ACCOUNTING", True),
    ("STAFF", "SALES", False), ("STAFF", "CONSTRUCTION", False), ("VIEWER", "CS", False),
])
def test_undo_visibility_uses_policy_when_registered(monkeypatch, role, team, can) -> None:
    """정책 칸(ITEM_CONSTRUCTION_DONE_UNDO)이 있으면 그 판정, 없으면 같은 뜻의 손 판정 — 두 길이 같은 답(E3-4)."""
    from foms.services.orders import order_mutation_policy as omp

    user = User(role=role, team=team, is_active=True)
    order = _Row("CONSTRUCTION", _split_sd(stage="CONSTRUCTION"), 9)
    registry = dict(omp.POLICY_REGISTRY)
    registry.pop(icv.UNDO_POLICY_NAME, None)
    monkeypatch.setattr(icv, "POLICY_REGISTRY", registry)
    assert icv.order_item_done_view(order, user)["can_undo"] is can  # 손 판정
    registry[icv.UNDO_POLICY_NAME] = omp._p(icv.UNDO_POLICY_NAME, teams=("CS",), description="시험용")
    assert icv.order_item_done_view(order, user)["can_undo"] is can  # 정책 판정


def test_stage_chips_and_summary_count_split_production(client) -> None:
    """시공대기 칩 목록 · 숫자판에도 나눠 시공 생산 단계 주문이 든다, 시공완료 칩에는 안 든다(E3-6)."""
    from foms.services.construction_read_model import (
        apply_construction_list_scope_filter,
        compute_construction_kpis_and_badges,
    )

    _login(client)
    _cookies(client, _PC)
    split = _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    cons = _order(_plain_sd(stage="CONSTRUCTION"), "CONSTRUCTION", [_d(1), _d(2)])
    wait = client.get(URL + "?stage=시공대기", headers=SHELL).get_data(as_text=True)
    assert f'data-order-id="{split}"' in wait and f'data-order-id="{cons}"' in wait
    assert f'data-visit-date="{_d(0)}"' in wait[wait.index(f'<tr class="erp-main-row" data-order-id="{split}"'):][:400]
    assert f'<tr class="erp-main-row" data-order-id="{split}"' not in client.get(URL + "?stage=시공중", headers=SHELL).get_data(as_text=True)
    assert f'data-order-id="{split}"' not in client.get(URL + "?stage=시공완료", headers=SHELL).get_data(as_text=True)

    base = db_session.query(Order).filter(Order.is_erp_order.is_(True))
    stats, _ = compute_construction_kpis_and_badges(apply_construction_list_scope_filter(base, "", [split]), [split])
    plain_stats, _ = compute_construction_kpis_and_badges(apply_construction_list_scope_filter(base, ""))
    assert stats["시공대기"]["count"] == plain_stats["시공대기"]["count"] + 1


def test_stage_chip_query_count_flat(client) -> None:
    _login(client)
    _cookies(client, _PC)
    _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    client.get(URL + "?stage=시공대기", headers=SHELL)  # warmup
    dc.reset_dashboard_cache_runtime_for_tests()
    _, small = _count(lambda: client.get(URL + "?stage=시공대기", headers=SHELL))
    for _ in range(6):
        _order(_split_sd(), "PRODUCTION", [_d(-3), _d(5)])
    dc.reset_dashboard_cache_runtime_for_tests()
    resp, big = _count(lambda: client.get(URL + "?stage=시공대기", headers=SHELL))
    assert resp.get_data(as_text=True).count("생산 · 부분 시공") == 7
    assert big - small <= 2, (small, big)
