"""출고 패킹 공장마다 — 권한 표 · 화면 자리 · JS/CSS 계약(설계서 2026-11-23 '승인 때 고친 것' 6 ① ④ ⑤, 3단계 ⑦ B). 지어낸 이름.

권한(한 곳 ``packing_access``): 지금 팀(출고 · CS · 영업 · 시공) · 관리자 · 매니저 그대로 + 생산팀 파트 계정 · 반장(자기 공장 줄만).
화면: 폰 출고 카드 · 시공 폰 첫 카드 · 생산 작업 시트 [패킹](끼울 조각) — 2공장 장이 섞인 주문만 새 단추(data-foms-pf-trigger) · 새 모양/움직임
파일, 1공장뿐이면 지금 단추 · 지금 응답 그대로. 폰 · 시공 태블릿 글 "패킹/포장 1공장 3/4 · 2공장 0/3".

되돌리면 실패: 생산 보기만 계정이 체크 · 2공장 계정이 1공장 줄 체크 · 1공장뿐인 응답에 새 파일이 실림 · 새 모듈이 옛 모듈 표식을 씀 ·
조각이 쿼리를 더함.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import g, render_template_string
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.construction.tablet_first import _packing_fields
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.shipment.packing_access import (
    can_view_packing,
    can_write_packing,
    packing_factories,
    single_factory_can_check,
)
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/shipment/foms-packing-factory.js"
VIEW_JS = ROOT / "static/js/shipment/foms-packing-factory-view.js"
CSS = ROOT / "static/css/components/foms-packing-factory.css"
SHELL = {"X-FOMS-ERP-SHELL": "1"}
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "390"}
_seq = itertools.count(1)


def _p(role="STAFF", team=None, *, parts=None, lead=False, factory=None, active=True, partner=None):
    return SimpleNamespace(id=next(_seq), role=role, team=team, is_active=active, partner_org_id=partner, name="가짜",
                           production_part=(parts or [None])[0], production_parts=parts, production_lead=lead,
                           production_factory=factory)


@pytest.mark.parametrize("person,write,view,factories", [
    (_p("ADMIN", "CS"), True, True, (1, 2)),
    (_p("ADMIN", "PRODUCTION", factory=2), True, True, (1, 2)),
    # 사장님 2026-11-25 "패킹 체크는 생산 · 시공 · 관리자만" — 출고 · CS · 영업 · 다른 팀 매니저는 쓰기 True → False(전판 값은 줄 끝)
    (_p("MANAGER", "DRAWING"), False, False, ()),  # 전: True · True(GET 은 3단계 전처럼 다시 못 엶)
    (_p("MANAGER", None), False, False, ()),  # 팀 없는 매니저 — 전: True · True
    # 생산팀은 직원 · 매니저 모두 파트 계정 · 반장만 쓴다(사장님 규칙 — 역할과 무관, 2026-11-25 고침)
    (_p("MANAGER", "PRODUCTION"), False, False, ()),  # 파트도 반장도 아님 = 보기만 생산팀 직원과 같음(전: True · True · (1,))
    (_p("MANAGER", "PRODUCTION", parts=["cut"]), True, True, (1,)),  # 파트 있는 매니저 — 자기 공장 몫
    (_p("MANAGER", "PRODUCTION", parts=["edge"], factory=2), True, True, (2,)),
    (_p("MANAGER", "PRODUCTION", lead=True, factory=2), True, True, (2,)),  # 반장 매니저
    (_p("MANAGER", "CONSTRUCTION"), True, True, (1, 2)),
    (_p("MANAGER", "SHIPMENT"), False, True, ()),  # 보기만(전: True)
    (_p("MANAGER", "CS"), False, True, ()),
    (_p("STAFF", "SHIPMENT"), False, True, ()),  # 보기만(전: True)
    (_p("STAFF", "CONSTRUCTION"), True, True, (1, 2)),
    (_p("STAFF", "CS"), False, True, ()),  # 보기만(전: True)
    (_p("STAFF", "SALES"), False, True, ()),  # 보기만(전: True) — 켜진 프리랜서도 영업팀이라 같음
    (_p("STAFF", "ACCOUNTING"), False, True, ()),  # CS 별칭 — 보기만(전: True)
    (_p("STAFF", "PRODUCTION", parts=["cut"]), True, True, (1,)),  # 새로 — 파트 계정
    (_p("STAFF", "PRODUCTION", parts=["edge"], factory=2), True, True, (2,)),
    (_p("STAFF", "PRODUCTION", lead=True, factory=2), True, True, (2,)),  # 새로 — 반장
    (_p("STAFF", "PRODUCTION"), False, False, ()),  # 파트도 반장도 아닌 생산팀(보기만)
    (_p("VIEWER", "SHIPMENT"), False, True, ()),  # 예전 읽기 문 그대로
    (_p("VIEWER", "PRODUCTION", parts=["cut"]), False, False, ()),
    (_p("STAFF", "DRAWING"), False, False, ()),
    (_p("STAFF", "SHIPMENT", active=False), False, False, ()),
    (_p("STAFF", "SHIPMENT", partner=7), False, False, ()),
    (None, False, False, ()),
])
def test_permission_table(person, write, view, factories):
    assert can_write_packing(person) is write
    assert can_view_packing(person) is view
    assert packing_factories(person) == factories


@pytest.mark.parametrize("person,allowed", [
    (_p("STAFF", "PRODUCTION", parts=["cut"]), True),
    (_p("STAFF", "PRODUCTION", lead=True), True),
    (_p("STAFF", "PRODUCTION"), False),
    (_p("STAFF", "CONSTRUCTION"), True),
    (_p("MANAGER", "CONSTRUCTION"), True),
    (_p("MANAGER", "PRODUCTION"), False),  # 파트도 반장도 아닌 생산팀 매니저(전: True)
    (_p("MANAGER", "PRODUCTION", parts=["cut"]), True),
    (_p("MANAGER", "PRODUCTION", lead=True), True),
    (_p("ADMIN", None), True),
    (_p("VIEWER", "SHIPMENT"), False),
    (_p("STAFF", "DRAWING"), False),
    (_p("STAFF", "SHIPMENT"), False),  # 2026-11-25 부터(전: True)
    (_p("STAFF", "CS"), False),
    (_p("STAFF", "SALES"), False),
    (_p("MANAGER", "SHIPMENT"), False),
    (_p("MANAGER", "DRAWING"), False),
])
def test_policy_gate_is_the_same_function(person, allowed):
    """정책 PACKING_WRITE 문지기 = can_write_packing(앞문 · 핸들러 · 화면이 한 함수)."""
    assert POLICY_REGISTRY["PACKING_WRITE"].gate == "foms.services.shipment.packing_access:can_write_packing"
    assert evaluate_policy(POLICY_REGISTRY["PACKING_WRITE"], person).allowed is allowed


@pytest.mark.parametrize("person,can_check", [
    (_p("ADMIN", None), [1]),
    (_p("STAFF", "CONSTRUCTION"), [1]),
    (_p("MANAGER", "CONSTRUCTION"), [1]),
    (_p("STAFF", "PRODUCTION", parts=["cut"]), [1]),  # 1공장 파트 계정 — 옛 꼴 줄은 모두 1공장 몫
    (_p("MANAGER", "PRODUCTION", lead=True), [1]),
    (_p("STAFF", "PRODUCTION", parts=["edge"], factory=2), []),  # 2공장 생산 계정 = 옛 꼴은 보기만
    (_p("MANAGER", "PRODUCTION", lead=True, factory=2), []),
    (_p("MANAGER", "PRODUCTION"), []),
    (_p("STAFF", "SHIPMENT"), []),  # 보기만(출고 · CS · 영업)
    (_p("MANAGER", "SHIPMENT"), []),
    (_p("STAFF", "CS"), []),
    (_p("STAFF", "SALES"), []),
    (_p("VIEWER", "SHIPMENT"), []),
    (None, []),
])
def test_single_factory_can_check_table(person, can_check):
    """옛 꼴(1공장뿐) 응답 can_check — 저장 문(require_first_factory: 1공장 몫)과 같은 판정, 공장 꼴 can_check 와 같은 뜻."""
    assert single_factory_can_check(person) == can_check
    assert (1 in packing_factories(person)) is bool(can_check)


# --------------------------------------------------------------------------- #
# 화면 자리
# --------------------------------------------------------------------------- #
def _sd(code: str, today: str, *, f2: bool, packing=None) -> dict:
    files = [{"key": f"orders/x/drawing/{code}_{j}.png", "filename": f"{code}-{j}.png", "sheet_id": f"{code}-s{j}"} for j in range(5)]
    sd = {"workflow": {"stage": "CONSTRUCTION"}, "drawing_current_files": files, "items": [{"product_name": "붙박이장"}],
          "schedule": {"construction": {"date": today}}, "shipment": {"construction_workers": ["김시공"]},
          "parties": {"customer": {"name": code}}, "site": {"address_full": "가짜시 가짜로 1"}}
    if f2:
        sd["drawing_factory"] = {"sheets": {f"{code}-s3": 2, f"{code}-s4": 2}, "files": {}}
    if packing is not None:
        sd["shipment"]["packing"] = packing
    return sd


def _order(code: str, *, f2: bool, packing=None) -> int:
    today = get_today_kst().isoformat()
    o = Order(received_date=today, customer_name=code, phone="010-0000-0000", address="가짜시 가짜로 1", product="붙박이장",
              status="CONSTRUCTION", manager_name="가짜영업", is_erp_order=True, erp_stage_code="CONSTRUCTION",
              structured_data=_sd(code, today, f2=f2, packing=packing), scheduled_date=today, erp_construction_date=today)
    db_session.add(o)
    db_session.flush()
    db_session.add(OrderScheduleDate(order_id=o.id, kind="construction", date=today, source="beta_schedule"))
    db_session.commit()
    return o.id


def _login(client, monkeypatch, *, role="ADMIN", team="CS", **extra) -> User:
    u = User(username=f"pfs-{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name="김시공", is_active=True)
    for k, v in extra.items():
        setattr(u, k, v)
    db_session.add(u)
    db_session.commit()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(u.id))
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role
    for k, v in PHONE.items():
        client.set_cookie(k, v, domain="localhost")
    return u


def _checked_f1(code: str, **extra) -> dict:
    """공장 꼴로 저장한 패킹 — 1공장 도면 1 한 줄만 체크."""
    return {"items": [{"key": f"sheet:{code}-s0", "label": "도면 1", "qty": 1, "checked": True, "at": None, "by_name": "김시공",
                       "issue": None}], "updated_at": None, "layout": "factory", **extra}


def test_phone_cards_swap_trigger_only_for_mixed_and_load_assets_once(client, monkeypatch):
    _login(client, monkeypatch)
    mixed = _order("pm", f2=True, packing=_checked_f1("pm"))
    plain = _order("pp", f2=False)
    html = client.get("/erp/shipment?view=fragment", headers=SHELL).get_data(as_text=True)
    assert html.count("data-foms-pf-trigger") == 1 and html.count("foms-packing-factory.js?v=") == 1
    assert html.count("foms-packing-factory-view.js?v=") == 1 and html.count("foms-packing-factory.css?v=") == 1
    card = html.split(f'data-order-id="{mixed}">', 1)[1].split("</button>", 1)[0]
    # 공장 이름은 공장 칩(사장님 2026-11-24 식별성 — 거르개 factory_chips · JS facText 가 같은 꼴), 글은 그대로
    assert ('<span data-pf-label>패킹 <em class="foms-fac foms-fac--1">1공장</em> 1/4 · '
            '<em class="foms-fac foms-fac--2">2공장</em> 0/3</span>') in card
    plain_btn = html.split(f'data-order-id="{plain}">', 1)[0].rsplit("<button", 1)[1]
    assert "data-foms-packing-trigger" in plain_btn and "data-foms-pf-trigger" not in plain_btn


def test_phone_card_shows_departed_after_auto_depart(client, monkeypatch):
    _login(client, monkeypatch)
    oid = _order("pd", f2=True, packing=_checked_f1("pd", departed_at="2026-11-24T00:40:00+00:00", departed_by_name="김시공"))
    html = client.get("/erp/shipment?view=fragment", headers=SHELL).get_data(as_text=True)
    card = html.split(f'data-order-id="{oid}">', 1)[1].split("</button>", 1)[0]
    assert '<span class="foms-packing-departed-label" data-pf-label>출발 보고됨</span>' in card


def test_plain_day_has_no_factory_packing_trace(client, monkeypatch):
    _login(client, monkeypatch)
    _order("pq", f2=False)
    for url in ("/erp/shipment?view=fragment", "/erp/construction/dashboard?view=fragment"):
        html = client.get(url, headers=SHELL).get_data(as_text=True)
        for token in ("foms-packing-factory", "data-foms-pf-trigger", "data-pf-label"):
            assert token not in html, (url, token)


def test_construction_hero_and_tablet_text(client, monkeypatch):
    _login(client, monkeypatch, role="STAFF", team="CONSTRUCTION")
    oid = _order("pc", f2=True, packing=_checked_f1("pc"))
    html = client.get("/erp/construction/dashboard?view=fragment", headers=SHELL).get_data(as_text=True)
    hero = html.split('aria-label="오늘 배차 첫 현장"', 1)[1].split("현장 상세", 1)[0]
    assert "data-foms-pf-trigger" in hero and f'data-order-id="{oid}"' in hero
    assert html.count("foms-packing-factory.js?v=") == 1
    assert _packing_fields(db_session.get(Order, oid).structured_data) == ("포장 1공장 1/4 · 2공장 0/3", "split")


# --------------------------------------------------------------------------- #
# 생산 작업 시트 [패킹] — 조각(packing_prod_entry.html)과 그 조각을 끼운 작업 시트(sheet.html [보류] 뒤 한 줄)
# --------------------------------------------------------------------------- #
_INCLUDE = "{% include 'shipment/partials/packing_prod_entry.html' %}"


def _render_entry(app, user_kw: dict, oid: int) -> tuple[str, int]:
    user = User(username=f"pfe-{next(_seq)}", password="x", is_active=True, name="가짜생산", **user_kw)
    db_session.add(user)
    db_session.commit()
    with app.test_request_context("/erp/production/sheet/1"):
        db_session.refresh(user)  # 요청 앞단(_set_current_user)이 읽어 둔 사용자 행과 같게
        g.current_user = user
        held = db_session.query(Order).filter(Order.id == oid).one()  # 라우트가 읽어 둔 행(identity map — 라우트 지역 변수가 붙든다)
        def _render(source: str) -> tuple[str, int]:
            n = {"q": 0}

            def _count(*_a, **_k):
                n["q"] += 1

            event.listen(engine, "before_cursor_execute", _count)
            try:
                return render_template_string(source, order=SimpleNamespace(id=oid)), n["q"]
            finally:
                event.remove(engine, "before_cursor_execute", _count)

        _render("")  # 데우기 — 앱 문맥 처리기(관리자 전용 등)가 요청마다 한 번 읽는 몫은 페이지 몫
        _empty, base = _render("")  # 조각이 더하는 것만 센다
        html, total = _render(_INCLUDE)
        assert held.id == oid
    return html, total - base


@pytest.mark.parametrize("who,mixed,expect", [
    ({"role": "STAFF", "team": "PRODUCTION", "production_lead": True, "production_factory": 2}, True, "pf"),
    ({"role": "STAFF", "team": "PRODUCTION", "production_lead": True, "production_factory": 2}, False, None),  # 1공장뿐 — 내 공장 줄 없음
    ({"role": "STAFF", "team": "PRODUCTION", "production_parts": ["cut"], "production_part": "cut"}, False, "old"),
    ({"role": "STAFF", "team": "PRODUCTION", "production_parts": ["cut"], "production_part": "cut"}, True, "pf"),
    ({"role": "STAFF", "team": "PRODUCTION"}, True, None),  # 보기만 생산팀
    ({"role": "ADMIN", "team": "CS"}, False, "old"),
])
def test_production_sheet_entry(app, who, mixed, expect):
    oid = _order(f"ps{next(_seq)}", f2=mixed)
    html, queries = _render_entry(app, who, oid)
    assert queries == 0, html
    if expect is None:
        assert html.strip() == ""
        return
    assert 'class="foms-prod-page__btn foms-pk-prod"' in html and "data-foms-packing-sheet" in html
    assert ("data-foms-pf-trigger" in html) is (expect == "pf") and ("data-foms-packing-trigger" in html) is (expect == "old")
    assert html.count("foms-packing-factory.js?v=") == 1 and html.count("js/shipment/foms-packing.js") == 1


# --------------------------------------------------------------------------- #
# JS · CSS 계약
# --------------------------------------------------------------------------- #
def test_js_size_and_safety_contracts():
    js, view = JS.read_text(encoding="utf-8"), VIEW_JS.read_text(encoding="utf-8")
    for src in (js, view):
        assert len(src.splitlines()) < 300
        assert "jQuery" not in src and "$(" not in src and "alert(" not in src and "innerHTML" not in src
        # 옛 모듈이 듣는 표식을 쓰지 않는다(옛 리스너가 남의 주문으로 보내던 겹침 방지)
        for old in ("data-foms-packing-check", "data-foms-packing-issue-chip", "data-foms-packing-issue-toggle",
                    "data-foms-packing-add", "[data-foms-packing-depart]", "'data-foms-packing-depart'"):
            assert old not in src, old
    assert "if (window.__FOMS_PF_BOUND) return;" in js
    assert "!res.ok || !data.success" in js and "catch (err)" in js
    for token in ("FOMS_ERP_SHELL", "navigateByShell", "location.reload", "location.href ="):
        assert token not in js  # 제출이 셸 GET 을 부르지 않는다
    assert "form.dataset.submitting === '1'" in js  # submit 1회 = POST 1
    assert re.search(r"closest\('\[data-foms-packing-trigger\]'\)\) \{ leave\(\); return; \}", js)  # 옛 단추 → 옛 목록으로
    assert "}, true);" in js  # 캡처 단계(옛 모듈 bubble 보다 먼저)
    assert "'한 번 더 탭해 확정'" in js  # 지금 출발 보고 단추와 같은 두 번 눌러 확정


def test_css_contracts():
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
    assert "!important" not in css and "style=" not in css
    for m in re.finditer(r"font-size:\s*([^;]+);", css):
        assert re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", m.group(1).strip()), m.group(1)
    assert ".foms-packing-sheet.is-pf .offcanvas-body > :not(.foms-pf)" in css
    # 공장 색은 공장 칩 한 곳(@import components/foms-factory-chip.css) — 옛 2공장 청록 값을 따로 두지 않는다
    assert css.lstrip().startswith('@import url("foms-factory-chip.css?v=') and "#0f6b63" not in css and "#0d9488" not in css
    assert re.search(r"\.foms-pf__main \{[^}]*min-height: 44px", css)
    assert re.search(r"\.foms-pf__acts \.foms-packing-depart \{[^}]*min-height: 48px", css)


def test_construction_first_screen_wraps_split_packing_text(app):
    """시공 탭 첫 화면 '출고' 칸 — 공장 둘로 나뉜 포장 글만 상태 split(두 줄 모양) · 모양 파일 실을지(has_packing_split)."""
    from foms.services.construction import tablet_first as tf

    mixed = _order(f"pt{next(_seq)}", f2=True, packing=_checked_f1("x"))
    plain = _order(f"pt{next(_seq)}", f2=False)
    admin = User(username=f"pft-{next(_seq)}", password="x", role="ADMIN", team="CS", name="가짜관리", is_active=True)
    db_session.add(admin)
    db_session.commit()
    first = tf.build_tablet_first(db_session, user=admin, mine_only=False, worker_settings=[], worker="", today=get_today_kst())
    rows = {r["id"]: r for s in first["sections"] for g in s["groups"] for r in g["rows"]}
    assert rows[mixed]["packing_state"] == "split" and rows[mixed]["packing_text"] == "포장 1공장 0/4 · 2공장 0/3"
    assert rows[plain]["packing_state"] != "split" and first["has_packing_split"] is True
    body = (ROOT / "templates/construction/partials/tablet_first_body.html").read_text(encoding="utf-8")
    assert "{% set F = cons_tablet.first %}{% if F.has_packing_split %}" in body
    css = (ROOT / "static/css/components/foms-packing-factory.css").read_text(encoding="utf-8")
    assert ".foms-cons-row__c span.is-split {" in css


@pytest.mark.parametrize("who,mixed,expect", [
    ({"team": "PRODUCTION", "production_lead": True, "production_factory": 2}, True, "pf"),
    ({"team": "PRODUCTION", "production_lead": True, "production_factory": 2}, False, None),
    ({"team": "PRODUCTION", "production_parts": ["cut"], "production_part": "cut"}, False, "old"),
    ({"team": "PRODUCTION", "production_lead": True}, False, "old"),
    ({"team": "PRODUCTION"}, True, None),  # 파트도 반장도 아닌 생산팀 — 쓰기 단추 줄은 있어도 [패킹]은 없음
])
def test_tablet_work_sheet_third_button(client, monkeypatch, who, mixed, expect):
    """실제 작업 시트(태블릿 쿠키) — [불량 알리기] [보류] 뒤 세 번째 칸이 조각의 판정대로만 나온다."""
    _login(client, monkeypatch, role="STAFF", **who)
    for k, v in {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1176"}.items():
        client.set_cookie(k, v, domain="localhost")
    oid = _order(f"pw{next(_seq)}", f2=mixed)
    html = client.get(f"/erp/production/sheet/{oid}").get_data(as_text=True)
    pair = html.split('<div class="foms-prod-page__pair">', 1)[1].split('<div class="foms-prod-page__chips"', 1)[0]
    assert pair.count('<button type="button" class="foms-prod-page__btn') == (2 if expect is None else 3)
    assert ("data-foms-pf-trigger" in pair) is (expect == "pf") and ("data-foms-packing-trigger" in pair) is (expect == "old")
    if expect is None:
        assert "foms-packing-sheet" not in html and "foms-packing-factory" not in html
