"""태블릿 가로 시공 탭 첫 화면 · 상세 모드 화면 계약(설계서 tablet-production-ui §13.3 · §13.6 · P13-3 · P13-4).

모드: 코호트 · coarse · 화면 긴 변 ≥992(쿠키 없으면 참) · focus_order · q 없음 → 첫 화면(3분할 안 그림).
``?focus_order=`` → 상세(3분할, 왼쪽 = 그날 · 그 시공자 집, 칩 대신 돌아가기). ``?q=`` → 찾기.
대조군: 폰(긴 변 844) · 마우스 기기는 지금 그대로. 접수가 오래된 오늘 시공 집이 첫 화면 줄에 나온다.
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
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]
URL = "/erp/construction/dashboard"
SHELL = {"X-FOMS-ERP-SHELL": "1"}
_seq = itertools.count(1)


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _d(n: int = 0) -> str:
    return (get_today_kst() + datetime.timedelta(days=n)).isoformat()


def _order(customer: str, *, day: str | None, stage: str = "CONSTRUCTION", workers: list[str] | None = None,
           created: datetime.datetime | None = None, manager: str = "가짜영업") -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer}, "orderer": {"name": "가짜대리점"}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "1200", "quantity": 1}],
        "site": {"address_full": "가짜시 가짜구 시공로 1"},
        "schedule": {"construction": {"date": day}} if day else {},
        "shipment": {"construction_workers": workers or []},
    }
    order = Order(received_date=_d(), customer_name=customer, phone="010-0000-0000", address="가짜시 가짜구 시공로 1",
                  product="가짜장", status=stage, manager_name=manager, is_erp_order=True, structured_data=sd,
                  erp_stage_code=stage)
    if created is not None:
        order.created_at = created
    db_session.add(order)
    db_session.flush()
    if day:
        db_session.add(OrderScheduleDate(order_id=order.id, kind="construction", date=day, source="beta_schedule"))
    db_session.commit()
    return order.id


def _login(client, monkeypatch, *, role: str = "ADMIN", team: str = "CS", name: str | None = None) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    n = next(_seq)
    user = User(username=f"cons_first_{n}", password=generate_password_hash("x"), role=role, team=team,
                name=name or f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _get(client, query: str = "", **cookies) -> str:
    for key, value in cookies.items():
        client.set_cookie(key, value, domain="localhost")
    resp = client.get(URL + query, headers=SHELL)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _section(body: str, start: str, end: str) -> str:
    i = body.index(start)
    return body[i:body.index(end, i)]


def test_first_mode_replaces_workmode_and_shows_old_received_today_house(client, monkeypatch) -> None:
    """대조군: 오래 전 접수한 오늘 집 + 최근 접수한 먼 날 집 50 — 지금 3분할(최신 50건)엔 없던 집이 첫 화면 줄에 있다."""
    old = _order("가짜오래된고객", day=_d(0), created=datetime.datetime(2020, 1, 1, 9, 0))
    for i in range(50):
        _order(f"가짜최근고객{i}", day=_d(9))
    _login(client, monkeypatch)
    body = _get(client)
    assert "foms-cons-first" in body and "foms-construction-workmode" not in body
    first = _section(body, 'class="foms-cons-first"', "</section>")
    assert len(re.findall(r'<a class="foms-ship-day[ "]', first)) == 14
    assert f'data-order-id="{old}"' in first and "가짜오래된고객" in first
    assert "1집" in first and "50집" in first  # 오늘 버튼 · 9일 뒤 버튼
    assert f"focus_order={old}" in first and f"date={_d(0)}" in first
    assert "data-ship-pop" in first and "data-ship-days-track" in first
    assert "foms-fs" in first  # 글자 손잡이
    assert "style=" not in first
    # 대조군: 같은 자료로 상세 모드(옛 3분할 목록 경로)는 접수 최신 50건만 받는다 — 폰 화면
    phone = _get(client, "", foms_scr="844")
    assert "foms-cons-first" not in phone and "foms-construction-workmode" in phone
    assert f'data-cwork-panel="{old}"' not in phone


def test_fine_pointer_renders_neither_tablet_surface(client, monkeypatch) -> None:
    _order("가짜고객", day=_d(0))
    _login(client, monkeypatch)
    body = _get(client, "", foms_ptr="fine")
    assert "foms-cons-first" not in body and "foms-construction-workmode" not in body
    assert "foms-construction-legacy-queue" in body


def test_zero_day_line_points_to_next_day(client, monkeypatch) -> None:
    nxt = _order("가짜다음고객", day=_d(3))
    _login(client, monkeypatch)
    first = _section(_get(client, f"?date={_d(1)}&worker="), 'class="foms-cons-first"', "</section>")
    assert "시공 없음" in first and "다음 시공" in first and "1집" in first
    assert "미리 보기" in first and f'data-order-id="{nxt}"' in first


def test_detail_mode_left_list_is_that_day_with_back_link(client, monkeypatch) -> None:
    a = _order("가짜에이", day=_d(2), workers=["가짜기사"])
    b = _order("가짜비", day=_d(2), workers=["가짜기사"])
    other = _order("가짜다른날", day=_d(5), workers=["가짜기사"])
    _login(client, monkeypatch)
    body = _get(client, f"?focus_order={b}&date={_d(2)}&worker=")
    assert "foms-cons-first" not in body and "foms-construction-workmode" in body
    wm = _section(body, 'class="foms-construction-workmode"', "</aside>")
    assert "data-cwork-range" not in wm and "data-cwork-back" in wm
    assert f"date={_d(2)}" in wm and "목록" in wm
    assert f'data-order-id="{a}"' in wm and f'data-order-id="{b}"' in wm and f'data-order-id="{other}"' not in wm
    assert re.search(rf'foms-cwork-card is-active"\s+data-order-id="{b}"', wm)


def test_old_deeplink_focus_only_picks_nearest_upcoming_day(client, monkeypatch) -> None:
    oid = _order("가짜딥링크", day=_d(4))
    db_session.add(OrderScheduleDate(order_id=oid, kind="construction", date=_d(-3), source="beta_item"))
    db_session.commit()
    _login(client, monkeypatch)
    wm = _section(_get(client, f"?focus_order={oid}"), 'class="foms-construction-workmode"', "</aside>")
    assert f"date={_d(4)}" in wm and f'data-order-id="{oid}"' in wm


def test_production_house_shows_note_instead_of_start(client, monkeypatch) -> None:
    prod = _order("가짜생산중", day=_d(1), stage="PRODUCTION")
    _login(client, monkeypatch)
    first = _section(_get(client, f"?date={_d(1)}&worker="), 'class="foms-cons-first"', "</section>")
    assert f'data-order-id="{prod}"' in first and "생산중" in first
    body = _get(client, f"?focus_order={prod}&date={_d(1)}")
    panel = _section(body, f'data-cwork-panel="{prod}"', "</section>")
    assert "아직 생산 중이에요" in panel and 'data-action="startConstruction"' not in panel


@pytest.mark.parametrize("team,can", [("SHIPMENT", False), ("CS", True), ("CONSTRUCTION", True)])
def test_detail_buttons_follow_can_act_construction(client, monkeypatch, team, can) -> None:
    """출고팀은 서버가 403 이라 시작 · 완료 단추를 그리지 않는다(되돌리면 실패). 시공팀 · CS 는 그린다."""
    oid = _order("가짜권한", day=_d(0), workers=["가짜시공자"])
    _login(client, monkeypatch, role="STAFF", team=team, name="가짜시공자")
    body = _get(client, f"?focus_order={oid}&date={_d(0)}")
    panel = _section(body, f'data-cwork-panel="{oid}"', "</section>")
    assert ('data-action="startConstruction"' in panel) is can
    assert ("보기만 할 수 있어요" in panel) is (not can)


def test_search_mode_header_and_back_to_first(client, monkeypatch) -> None:
    _order("가짜찾기고객", day=_d(0))
    _login(client, monkeypatch)
    wm = _section(_get(client, "?q=가짜찾기고객"), 'class="foms-construction-workmode"', "</aside>")
    assert "찾기: 가짜찾기고객" in wm and "첫 화면으로" in wm and "data-cwork-range" not in wm


def test_assets_pinned_gated_and_scaled() -> None:
    styles = (ROOT / "templates/construction/partials/styles.html").read_text(encoding="utf-8")
    assert re.search(r"css/contexts/construction/tablet-first\.css'\) \}\}\?v=\d{8}[a-z]", styles)
    css = re.sub(r"/\*.*?\*/", "", (ROOT / "static/css/contexts/construction/tablet-first.css").read_text(encoding="utf-8"), flags=re.S)
    head, _, rest = css.partition("@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {")
    assert re.sub(r"\s+", " ", head).strip() == ".foms-cons-first { display: none; }"
    for block in re.finditer(r"([^{}]+)\{[^{}]*\}", rest):
        for sel in block.group(1).split(","):
            assert sel.strip().startswith("body.erp-mobile-v2-layout"), sel
    for value in re.findall(r"font-size:\s*([^;]+);", css):
        m = re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)", value.strip())
        assert m and int(m.group(1)) >= 13, value
    assert "background: var(--ship-pc" not in css  # 본문 칠 없음(D29) — 띠만
    tpl = (ROOT / "templates/construction/partials/tablet_first_body.html").read_text(encoding="utf-8")
    assert "style=" not in tpl and "금액" not in tpl


def _count_queries(fn) -> int:
    from sqlalchemy import event

    from db import engine

    n = {"n": 0}

    def _on(*_a):
        n["n"] += 1

    event.listen(engine, "before_cursor_execute", _on)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _on)
    return n["n"]


@pytest.mark.parametrize("mode", ["first", "detail"])
def test_query_count_does_not_grow_with_rows(client, monkeypatch, mode) -> None:
    """§13.6 perf: 그날 집이 4 → 12 로 늘어도 첫 화면 · 상세 쿼리 수는 늘지 않는다(차이 ≤2). 줄마다 쿼리 0."""
    ids = [_order(f"가짜측정{i}", day=_d(0), workers=["가짜기사"]) for i in range(4)]
    _login(client, monkeypatch)
    query = "" if mode == "first" else f"?focus_order={ids[0]}&date={_d(0)}"
    _get(client, query)  # 데우기
    dc.reset_dashboard_cache_runtime_for_tests()
    small = _count_queries(lambda: client.get(URL + query, headers=SHELL))
    for i in range(8):
        _order(f"가짜측정추가{i}", day=_d(0), workers=["가짜기사"])
    dc.reset_dashboard_cache_runtime_for_tests()
    big = _count_queries(lambda: client.get(URL + query, headers=SHELL))
    assert big - small <= 2, (small, big)
    # 절대 상한(총괄 판단 11-12, 설계서 §13.4 "넘으면 실측으로 정한다"): 코호트를 켠 지금 방식이 이미 8 이고
    # 첫 화면은 쿼리 A(색인만 · 줄 없음) · B(그날 + 미리 볼 날, 캡 200) 둘을 더해 10. 상세는 그날 B 가 50건 목록을 갈음해 8.
    cap = {"first": 10, "detail": 8}[mode]
    assert big <= cap, (mode, small, big, cap)
