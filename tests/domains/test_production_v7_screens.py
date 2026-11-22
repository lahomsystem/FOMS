"""생산 화면 7판 — 화면 시험(설계서 docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md §5 · §6 · §7 · §10).

순수 규칙은 ``test_production_drawing_arrival.py``. 여기는 실제 응답 HTML: 파트 계정 기다림 묶음이 카드 위(§5-3), PC 장 순서 ·
기다림 줄 까닭 한 줄 · 늦음 색이 도면 마감(§6 · §7). 큰 시험 파일(500줄 래칫) 옆에 따로 둔다. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order
from tests.domains.test_production_parts_screen import _get, _login as _part_login, _parts_block, _seed_day, _today_pane, _user
from tests.domains.test_production_pc_viewer import PC, ROOT, _login, _seed
from tests.support.production_home_step_panel_seed import HOME, get_html, set_cookies


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def test_파트_계정_기다림_묶음은_카드_위_머리에_마감_칩에_까닭(client, cohort) -> None:
    """§5-3: 반장 장과 같은 순서(기다림 → 도면 카드 → 제작 완료). 머리에 그날 마감(오늘 시공은 마감이 지나 빨강),
    칩 둘째 줄에 막힌 까닭 · 담당. 제목 · 카드 · 칸 단추는 그대로."""
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    ids = _seed_day(me, park)
    _part_login(client, me)
    block = _parts_block(_today_pane(_get(client, HOME)))
    assert block.index('class="fph-pane__g pp-wait-g"') < block.index("data-pp-grid")
    head = block.split('class="fph-pane__g pp-wait-g"')[1].split("</h3>")[0]
    assert '<small><span class="is-late">마감 ' in head and "지났어요</span> · 도면이 오면 카드로 나와요</small>" in head
    assert f'<a class="fph-wi has-why pp-wait" href="/erp/production/sheet/{ids["wait"]}">' in block
    assert '<span class="fph-wi__why"><b class="is-none">담당 없음</b></span>' in block
    assert block.count("data-pp-card ") == 5  # 카드는 그대로


def _wait_order(name: str, off: int, **sd_extra) -> Order:
    """도면 단계(안 내려온) 주문 — 지어낸 이름."""
    day = (get_today_kst() + datetime.timedelta(days=off)).isoformat()
    sd = {"workflow": {"stage": "DRAWING"}, "parties": {"customer": {"name": name}, "manager": {"name": "이가짜"}},
          "schedule": {"construction": {"date": day}}, "items": [{"product_name": "붙박이장"}], **sd_extra}
    order = Order(received_date=day, customer_name=name, phone="010-0000-0000", address="가짜시", product="장",
                  status="DRAWING", is_erp_order=True, erp_stage_code="DRAWING", erp_construction_date=day, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def test_PC_장은_태블릿과_같은_순서_기다림_줄에_까닭_한_줄_늦음은_도면_마감(client, cohort) -> None:
    """§6 · §7: PC 장 = 태블릿 장과 같은 순서(기다림 → 만들 것 → 제작 완료, 미리 보기 없음) · 같은 제목 글 · 기다림 묶음 머리
    마감, 기다림 줄(pc_mini) ③ 칸 안에 까닭 · 담당 한 줄(칸 · 폭 그대로), 기다림 줄 늦음 · 빠듯 = 도면 마감."""
    _seed()
    late = _wait_order("가늦음", 1, drawing_status="RETURNED", drawing_assignees=[{"id": 1, "name": "장가짜"}])
    _login(client, "admin")
    set_cookies(client, PC)
    key = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    pane = get_html(client, HOME + f"?view=day&day={key}")
    assert pane.index(">도면·컨펌 기다림 1 <small>") < pane.index(">만들 것 2</h3>")  # 가재단(재단 중) · 라대기(제작 대기)
    assert "미리 보기" not in pane and "나엣지" not in pane  # 그날 시공 주문만
    assert '<span class="fph-dwst is-late">도면 2/3 내려옴</span>' in pane
    assert '<small><span class="is-late">마감 ' in pane and "지났어요</span> · 도면이 오면 아래로 내려가요</small>" in pane
    row = pane.split(f'data-foms-home-dayrow="{late.id}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert '<span class="fpc-why"><b>도면 고치는 중</b> · <span>도면 장가짜</span> · <span>영업 이가짜</span></span>' in row
    head = pane.split(f'data-foms-home-dayrow="{late.id}"', 1)[0].rsplit("<div ", 1)[1]
    assert "fpc-r--mini is-late" in head  # 내일 시공 = 마감(어제 이전) 지남
    assert "<small>늦음 — 도면 마감 " in row and "지남, 아직 도면 고치는 중</small>" in row
    # 마감이 아직 먼 기다림 줄은 색 없음(옛 W ≤ 5 표라면 빠듯이었다)
    calm = _wait_order("나여유", 10, drawing_assignees=[{"id": 1, "name": "장가짜"}])
    far = (get_today_kst() + datetime.timedelta(days=10)).isoformat()
    far_pane = get_html(client, HOME + f"?view=day&day={far}")
    head = far_pane.split(f'data-foms-home-dayrow="{calm.id}"', 1)[0].rsplit("<div ", 1)[1]
    assert "is-late" not in head and "is-tight" not in head
    # PC 줄 · 칸 틀은 그대로(여섯 칸 · 네 칸) — 까닭 줄은 ③ 칸 안에만
    css = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    assert ".fpc-why { font-size: calc(14px * var(--foms-fs, 1));" in css and ".fpc-why b.is-none { color: var(--fpc-danger-ink); }" in css


def test_7판_CSS_는_목업_덩이_그대로_글자는_배율을_따르고_무채색이_없다() -> None:
    """§5 '꾸밈': 목업 '7판에서 더한 것' 덩이(색은 토큰) · 새 글자 calc(Npx * var(--foms-fs, 1)) · 상태 색 넷(늦음 · 빠듯 · 다 옴 · 여유)."""
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    block = css.split("/* ── 7판: 도면 내려옴")[1].split("/* ── 내 공정: 곧 올 것")[0]
    for line in (".fph-sd__mid { display: flex; flex-direction: column; justify-content: center; gap: 3px; min-width: 0; }",
                 ".fph-sd__dw.is-late, .fph-dwst.is-late { color: var(--fph-dw-late); }",
                 ".fph-sd__dw.is-soon, .fph-dwst.is-soon { color: var(--fph-dw-soon); }",
                 ".fph-sd__dw.is-ok, .fph-dwst.is-ok { color: var(--fph-dw-ok); }",
                 ".fph-wi__why b.is-none { color: var(--fph-danger); }"):
        assert line in block, line
    assert "--fph-dw-late: #b91c1c;" in css and "--fph-dw-soon: #b45309;" in css and "--fph-dw-ok: #047857;" in css
    import re
    for size in re.findall(r"font-size:\s*([^;]+);", block):
        assert re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", size.strip()), size
    assert "style=" not in (ROOT / "templates/production/partials/home_date_macros.html").read_text(encoding="utf-8")
