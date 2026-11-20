"""완료 확인 창의 한 줄이 화면마다 실리는지 (묶음 B, 설계서 5.3 · 결정 M13).

서버가 줄 · 카드 · 시트 뿌리에 글을 그리고(``data-remaining-construction`` / ``data-production-split-note``),
확인 글을 만드는 곳이 주문 번호로 찾아 덧붙인다. 새 끝점 · 새 JS 파일은 없다. 막지 않는다.

화면마다 "시공일 둘인 주문에는 있고, 같은 화면의 시공일 하나인 주문에는 없다"를 같이 본다(대조군).
이름 · 주소는 지어낸 것.
"""
from __future__ import annotations

import datetime
import itertools
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.services.datetime_kst import get_today_kst
from models import Order, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]
SHELL = {"X-FOMS-ERP-SHELL": "1"}
_seq = itertools.count(1)

REMAIN_ATTR = "data-remaining-construction"
SPLIT_ATTR = "data-production-split-note"


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _day(offset: int) -> datetime.date:
    return get_today_kst() + datetime.timedelta(days=offset)


def _md(day: datetime.date) -> str:
    return f"{day.month}/{day.day}"


FIRST, SECOND = _day(0), _day(12)
TWO_DATES = f"{FIRST.isoformat()}, {SECOND.isoformat()}"
REMAIN_TEXT = f"{_md(SECOND)} 시공이 남아 있어요"
SPLIT_TEXT = f"시공일이 {_md(FIRST)} · {_md(SECOND)} 두 번이에요. 제품이 모두 제작됐나요?"


def _order(customer: str, cons_text: str, *, stage: str, with_run: bool = False,
           started: bool = False) -> int:
    workflow: dict = {"stage": stage}
    if started:
        workflow["history"] = [{"note": "시공 시작"}]
    sd = {
        "parties": {"manager": {"name": "가짜영업"}, "customer": {"name": customer, "phone": "010-0000-0000"}},
        "workflow": workflow,
        "schedule": {"construction": {"date": cons_text}},
        "items": [{"product_name": "가짜장", "spec_width": "1200", "quantity": 1}],
        "site": {"address_full": "가짜시 가짜구 시공로 1"},
        "shipment": {"construction_workers": ["가짜시공"]},
    }
    order = Order(received_date=FIRST.isoformat(), customer_name=customer, phone="010-0000-0000",
                  address="가짜시 가짜구 시공로 1", product="가짜장", status=stage, manager_name="가짜영업",
                  is_erp_order=True, structured_data=sd, erp_stage_code=stage)
    db_session.add(order)
    db_session.commit()
    if with_run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return order.id


def _login(client, monkeypatch, *, v2: bool) -> User:
    n = next(_seq)
    user = User(username=f"hint_surface_{n}", password=generate_password_hash("x"), role="ADMIN", team="CS",
                name=f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    if v2:
        monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def _hints(client, **cookies: str) -> None:
    for name, value in cookies.items():
        client.set_cookie(name, value, domain="localhost")


PC = {"foms_ptr": "fine", "foms_vw": "wide"}
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow"}
TABLET = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}


def _get(client, url: str) -> str:
    resp = client.get(url, headers=SHELL)
    assert resp.status_code == 200, (url, resp.status_code)
    return resp.get_data(as_text=True)


def _root_tags(html: str, oid: int, marker: str) -> list[str]:
    """그 주문의 줄 · 카드 뿌리 여는 태그들(``marker`` 가 든 것만)."""
    tags = re.findall(r'<[a-z]+\b[^<>]*data-order-id="%d"[^<>]*>' % oid, html)
    return [tag for tag in tags if marker in tag]


def _assert_hint(html: str, *, marker: str, attr: str, text: str, with_hint: int, control: int) -> None:
    """``marker`` 뿌리에서 시공일 둘인 주문은 ``attr`` 글이 있고, 하나인 주문은 속성이 없다."""
    hit = _root_tags(html, with_hint, marker)
    assert hit, f"{marker}: 시공일 둘인 주문의 뿌리가 화면에 없다"
    assert all(f'{attr}="{text}"' in tag for tag in hit), hit
    ctl = _root_tags(html, control, marker)
    assert ctl, f"{marker}: 대조군 주문의 뿌리가 화면에 없다(대조군은 같은 화면 안에서 고른다)"
    assert all(attr not in tag for tag in ctl), ctl


# --- [시공 완료] ---------------------------------------------------------------

def _seed_construction() -> tuple[int, int]:
    two = _order("가짜둘", TWO_DATES, stage="CONSTRUCTION", started=True)
    one = _order("가짜하나", FIRST.isoformat(), stage="CONSTRUCTION", started=True)
    return two, one


def test_construction_pc_table_row_carries_remaining_note(client, monkeypatch):
    """PC 시공 대시보드 표 — 줄 뿌리에 남은 시공 한 줄, 확인 창에 그 글이 들어갈 자리."""
    _login(client, monkeypatch, v2=False)
    two, one = _seed_construction()
    # 시공일이 둘이어도 모두 지났으면 남은 시공이 없다 — 기준은 날짜 수가 아니라 "오늘보다 뒤".
    past = _order("가짜지남", f"{_day(-12).isoformat()}, {_day(-5).isoformat()}", stage="CONSTRUCTION", started=True)
    _hints(client, **PC)
    html = _get(client, "/erp/construction/dashboard")
    _assert_hint(html, marker='class="erp-main-row"', attr=REMAIN_ATTR, text=REMAIN_TEXT, with_hint=two, control=one)
    past_rows = _root_tags(html, past, 'class="erp-main-row"')
    assert past_rows and all(REMAIN_ATTR not in tag for tag in past_rows), past_rows
    assert 'id="erp-cons-complete-remaining"' in html
    assert SPLIT_ATTR not in html                     # 시공 화면에는 제작 완료 글이 안 실린다


def test_construction_phone_card_carries_remaining_note(client, monkeypatch):
    """휴대폰 시공 목록 카드 — 카드 뿌리에 한 줄, [완료 준비] 바닥 시트에 그 글이 들어갈 자리."""
    _login(client, monkeypatch, v2=True)
    two, one = _seed_construction()
    _hints(client, **PHONE)
    html = _get(client, "/erp/construction/dashboard")
    _assert_hint(html, marker="foms-queue-card-v2", attr=REMAIN_ATTR, text=REMAIN_TEXT, with_hint=two, control=one)
    assert "data-foms-cgate-remaining" in html
    assert 'id="erp-cons-complete-remaining"' in html   # 폰의 [시공 완료]는 PC 와 같은 창이다


def test_construction_tablet_workmode_card_carries_remaining_note(client, monkeypatch):
    """태블릿 시공 작업 모드 — 왼쪽 집 카드 뿌리에 한 줄(같은 날 · 같은 시공자의 대조군에는 없음)."""
    _login(client, monkeypatch, v2=True)
    two, one = _seed_construction()
    _hints(client, **TABLET)
    html = _get(client, f"/erp/construction/dashboard?focus_order={two}&date={FIRST.isoformat()}")
    _assert_hint(html, marker="foms-cwork-card", attr=REMAIN_ATTR, text=REMAIN_TEXT, with_hint=two, control=one)
    assert "data-foms-cgate-remaining" in html


# --- [제작 완료] ---------------------------------------------------------------

def _seed_production() -> tuple[int, int]:
    two = _order("가짜둘", TWO_DATES, stage="PRODUCTION", with_run=True)
    one = _order("가짜하나", FIRST.isoformat(), stage="PRODUCTION", with_run=True)
    return two, one


def test_production_pc_table_row_carries_split_note(client, monkeypatch):
    """PC 생산 대시보드 표 — 줄 뿌리에 [제작 완료] 글."""
    _login(client, monkeypatch, v2=False)
    two, one = _seed_production()
    _hints(client, **PC)
    html = _get(client, "/erp/production/dashboard")
    _assert_hint(html, marker='class="erp-main-row"', attr=SPLIT_ATTR, text=SPLIT_TEXT, with_hint=two, control=one)
    assert REMAIN_ATTR not in html                    # 제작 완료에는 "남은 시공" 글을 쓰지 않는다(늘 뜬다)


def test_production_phone_card_carries_split_note(client, monkeypatch):
    """휴대폰 생산 목록 카드 — 공용 카드 뿌리에 [제작 완료] 글."""
    _login(client, monkeypatch, v2=True)
    two, one = _seed_production()
    _hints(client, **PHONE)
    html = _get(client, "/erp/production/dashboard")
    _assert_hint(html, marker="foms-queue-card-v2", attr=SPLIT_ATTR, text=SPLIT_TEXT, with_hint=two, control=one)


def test_production_tablet_kanban_card_carries_split_note(client, monkeypatch):
    """태블릿 생산 칸반 — 카드 뿌리에 [제작 완료] 글."""
    _login(client, monkeypatch, v2=True)
    two, one = _seed_production()
    _hints(client, **TABLET)
    html = _get(client, "/erp/production/dashboard")
    _assert_hint(html, marker="foms-kanban-card", attr=SPLIT_ATTR, text=SPLIT_TEXT, with_hint=two, control=one)


def test_production_side_sheet_and_sheet_page_carry_split_note(client, monkeypatch):
    """생산 옆 시트 · 전체 화면 시트 — 시트 뿌리에 [제작 완료] 글(대조군 시트에는 없음)."""
    _login(client, monkeypatch, v2=False)
    two, one = _seed_production()
    for url, marker in (("/erp/production/tablet-sheet/{id}", 'class="foms-prod-sheet"'),
                        ("/erp/production/sheet/{id}", "data-foms-prod-sheet-page")):
        with_hint = client.get(url.format(id=two)).get_data(as_text=True)
        control = client.get(url.format(id=one)).get_data(as_text=True)
        hit = _root_tags(with_hint, two, marker)
        assert hit and all(f'{SPLIT_ATTR}="{SPLIT_TEXT}"' in tag for tag in hit), (url, hit)
        ctl = _root_tags(control, one, marker)
        assert ctl and all(SPLIT_ATTR not in tag for tag in ctl), (url, ctl)
        assert ">제작 완료<" in with_hint and ">제작 완료<" in control   # 둘 다 단추는 있다


# --- 확인 글을 만드는 JS 가 그 글을 읽는가 -------------------------------------------

def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_construction_confirm_builders_read_the_row_note():
    """시공 완료 창 · 완료 준비 시트가 줄 · 카드 뿌리의 글을 주문 번호로 찾아 보인다."""
    lookup = """document.querySelector('[data-remaining-construction][data-order-id="' + orderId + '"]')"""
    dash = _read("static/js/construction/dashboard.js")
    opener = dash[dash.index("function completeConstruction(orderId)"):]
    opener = opener[:opener.index("modal.show()")]
    assert lookup in dash
    assert "erp-cons-complete-remaining" in opener and "remainingConstructionNote(orderId)" in opener
    assert "classList.toggle('d-none', !remaining)" in opener      # 글이 없으면 줄을 숨긴다

    gate = _read("static/js/construction/foms-complete-gate.js")
    open_sheet = gate[gate.index("function openSheet(orderId)"):gate.index("window.openCompleteGate = openSheet")]
    assert lookup in open_sheet and "[data-foms-cgate-remaining]" in open_sheet
    assert "remainEl.hidden = !remainText" in open_sheet

    modal = _read("templates/construction/partials/modals.html")
    assert 'id="erp-cons-complete-remaining"' in modal
    line = next(ln for ln in modal.splitlines() if "erp-cons-complete-remaining" in ln)
    assert "style=" not in line and "d-none" in line               # 인라인 스타일 없이 기본은 숨김
    sheet = _read("templates/construction/partials/complete_gate_sheet.html")
    line = next(ln for ln in sheet.splitlines() if "data-foms-cgate-remaining" in ln)
    assert "style=" not in line and " hidden" in line


@pytest.mark.parametrize("rel", [
    "templates/production/partials/scripts.html",
    "static/js/foms/tablet-production-kanban.js",
    "static/js/foms/tablet-domain-sheets.js",
])
def test_production_confirm_builders_append_the_split_note(rel):
    """[제작 완료] 확인 글 셋 모두 뿌리의 글을 찾아 뒤에 붙인다 — 기존 글은 그대로 둔다."""
    src = _read(rel)
    assert '[data-production-split-note][data-order-id="' in src
    assert "function productionSplitNote(orderId)" in src
    assert "productionSplitNote(orderId)" in src.replace("function productionSplitNote(orderId)", "")
    assert "제작을 완료하시겠습니까" in src


def test_production_split_note_is_only_added_to_complete_action():
    """칸반의 [제작 시작] · [수정 제작] 확인 글에는 붙이지 않는다(대조군)."""
    src = _read("static/js/foms/tablet-production-kanban.js")
    assert 'spec.confirm + (action === "complete" ? productionSplitNote(orderId) : "")' in src


def test_no_new_endpoint_or_js_file_for_the_hint():
    """새 끝점 · 새 JS 파일 없이 기존 확인 창에만 붙는다."""
    assert not list((ROOT / "static" / "js").rglob("*remaining-construction*"))
    for rel in ("foms/api/construction/orders.py", "foms/api/production/orders.py"):
        assert "remaining_construction" not in _read(rel) and "production_split_note" not in _read(rel)
