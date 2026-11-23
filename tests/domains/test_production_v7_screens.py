"""생산 화면 7판 — 화면 시험(설계서 docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md §5 · §6 · §7 · §10).

순수 규칙은 ``test_production_drawing_arrival.py``. 여기는 실제 응답 HTML: 파트 계정 기다림 묶음이 카드 위(§5-3), PC 장 순서 ·
기다림 줄 까닭 한 줄 · 늦음 색이 도면 마감(§6 · §7), 내 공정 안내 · 지난 시공 빨강(§5-4), 바뀐 것 회귀(§5-5), 찾기 묶음 머리 ·
순서 · 까닭 줄(§5-6), 작업 시트 도면 칸 글(§5-7). 큰 시험 파일(500줄 래칫) 옆에 따로 둔다. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import re

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from models import Order, OrderEvent
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
    # 상태 칸은 마감 대비 늦음만, 까닭은 ③ 칸에 한 번(사장님 "같은 말은 한 번", 2026-11-22 §7 고침)
    assert re.search(r"<small>늦음 — 도면 마감 \d+일 지남</small>", row) and row.count("도면 고치는 중") == 1
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
    import re
    for size in re.findall(r"font-size:\s*([^;]+);", block):
        assert re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", size.strip()), size
    assert "style=" not in (ROOT / "templates/production/partials/home_date_macros.html").read_text(encoding="utf-8")


def test_PC_여러_시공일_기다림_줄_늦음은_띠와_같은_날(client, cohort) -> None:
    """§4-6: 납작 칸 = 열흘 뒤(띠 · 장: 마감 여유), 다른 제품 날 = 내일(PC ① 칸 '가장 가까운 날'). 늦음 색은 띠와 같은 날로 —
    ① 칸은 그대로 가까운 날 + 외 1(PC 설계서 §6-3 결정 5)."""
    flat = (get_today_kst() + datetime.timedelta(days=10)).isoformat()
    near = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    order = _wait_order("가여럿", 10, drawing_assignees=[{"id": 1, "name": "장가짜"}],
                        items=[{"product_name": "붙박이장", "construction_date": near}])
    oid = order.id
    _login(client, "admin")
    set_cookies(client, PC)
    pane = get_html(client, HOME + f"?view=day&day={flat}")
    head = pane.split(f'data-foms-home-dayrow="{oid}"', 1)[0].rsplit("<div ", 1)[1]
    row = pane.split(f'data-foms-home-dayrow="{oid}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert "is-late" not in head and "is-tight" not in head and "늦음" not in row  # 가까운 날로 셌다면 늦음
    assert "<small>외 1</small>" in row  # ① 칸은 그대로 가까운 날 + 외 n
    strip = get_html(client, HOME)
    assert "마감 지남" not in strip.split(f'data-foms-home-daybtn="{flat}"')[1].split("</a>")[0]


def test_내_공정_안내에_도면_마감_지난_집_수_줄_시공_칸은_지난_날이면_빨강(client, cohort) -> None:
    """§5-4: 셈 = 안 내려옴 · 시공일 ≥ 오늘 · 마감 < 오늘(시공일이 이미 지난 옛 주문은 안 셈). 줄 시공 칸 is-past + 'n일 지남'."""
    from tests.domains.test_production_home_tabs import _add_order, _make_user

    _make_user(client, "v7_steps", "PRODUCTION")
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    old = _add_order("PRODUCTION", "지난집", -3, steps_done=("cut",), with_run=True)  # 엣지 줄 · 시공 3일 지남
    _add_order("PRODUCTION", "앞날집", 4, with_run=True)
    _add_order("DRAWING", "늦은도면", 1)  # 내일 시공 = 마감 지남 → 셈
    _add_order("CONFIRM", "옛날컨펌", -2)  # 시공일 지남 → 안 셈
    _add_order("DRAWING", "여유도면", 12)  # 마감 전 → 안 셈
    html = client.get(HOME + "?tab=steps").get_data(as_text=True)
    assert "제작 대기 <b>0</b>건 · 도면 마감 지난 집 <b>1</b>건 · 검수까지 끝난 것 <b>0</b>건" in html
    edge = html.split('data-foms-home-stepq="edge"')[1].split('data-foms-home-stepq="assemble"')[0]
    row = edge.split(f'data-foms-home-qrow="{old.id}"')[1].split("</div>\n  ")[0]
    assert '<span class="fph-qr__due is-past">시공<b>' in row and "<small>3일 지남</small></span>" in row
    cut = html.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0]
    assert 'class="fph-qr__due">시공<b>' in cut and "is-past" not in cut.split("fph-q__nextlist")[0]
    # PC 안내 글도 같은 셈
    set_cookies(client, PC)
    assert "도면 마감 지난 집 <b>1</b>건" in get_html(client, HOME + "?tab=steps")


def test_바뀐_것은_컨펌_단계_시공일_변경을_안_치고_생산_진입_뒤만_친다(client) -> None:
    """§5-5 회귀(목업 '류하은'): 코드는 그대로 — D20(만들 주문만) · D22(생산 진입 바닥선)가 이미 그렇다."""
    from tests.domains.test_production_home_changes import _order as _changed_order
    from tests.domains.test_production_home_tabs import _make_user

    _make_user(client, "v7_changes", "PRODUCTION")
    order = _changed_order("CONFIRM", "류하은", 5)  # 단계 진입 20일 전 — 창은 그때부터(바닥선은 생산 진입 뒤에만)
    db_session.add(OrderEvent(order_id=order.id, event_type="CONSTRUCTION_DATE_CHANGED",
                              payload={"from": "2026-11-28", "to": "2026-11-30"},
                              created_at=now_utc_naive() - datetime.timedelta(hours=3)))
    db_session.commit()
    zero = ">바뀐 것 <small>0</small></a>"
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert zero in html and "data-foms-home-inbox=" not in html
    # 생산으로 내려옴(고객 컨펌 → 생산) — 그 앞 변경은 여전히 안 친다(D22 바닥선). 요청 뒤라 주문을 다시 읽는다
    order = db_session.get(Order, order.id)
    sd = dict(order.structured_data)
    sd["workflow"] = {"stage": "PRODUCTION"}
    order.structured_data, order.erp_stage_code, order.status = sd, "PRODUCTION", "PRODUCTION"
    db_session.add(OrderEvent(order_id=order.id, event_type="CUSTOMER_CONFIRMED", payload={"from": "CONFIRM", "to": "PRODUCTION"},
                              created_at=now_utc_naive() - datetime.timedelta(hours=2)))
    db_session.commit()
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert zero in html and "data-foms-home-inbox=" not in html
    # 생산 진입 뒤 바뀌면 1
    db_session.add(OrderEvent(order_id=order.id, event_type="CONSTRUCTION_DATE_CHANGED",
                              payload={"from": "2026-11-30", "to": "2026-12-01"},
                              created_at=now_utc_naive() - datetime.timedelta(hours=1)))
    db_session.commit()
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert '>바뀐 것 <small class="is-hot">1</small></a>' in html and html.count("data-foms-home-inbox=") == 1 and "류하은" in html


def test_찾기_묶음_머리_도면_글_순서_기다림_줄_까닭(client, cohort) -> None:
    """§5-6: 머리 = 날짜 · 건수 · 바뀜 뒤 도면 한 줄(띠와 같은 글 · 색), 순서 = 기다림 → 생산 → 제작 완료(같은 칸 안 지금 순서),
    기다림 줄 셋째 줄 = 까닭 · 담당(주소 찾기는 data-q 에 그대로). PC 찾기도 같은 머리 · 순서."""
    from tests.domains.test_production_home_tabs import _add_order, _make_user

    _make_user(client, "v7_all", "PRODUCTION")
    done = _add_order("CONSTRUCTION", "가완료", 1)
    made = _add_order("PRODUCTION", "나생산", 1, with_run=True)
    wait = _add_order("DRAWING", "다도면", 1, manager="박가짜")
    html = client.get(HOME + "?tab=all").get_data(as_text=True)
    key = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    grp = html.split(f'data-foms-home-grp="{key}"')[1].split("data-foms-home-grp=")[0]
    assert '<span class="fph-dwst is-late">도면 2/3 마감 지남</span>' in grp.split("</button>")[0]
    assert grp.index(f"/sheet/{wait.id}") < grp.index(f"/sheet/{made.id}") < grp.index(f"/sheet/{done.id}")
    job = grp.split(f"/sheet/{wait.id}")[1].split("</a>")[0]
    assert '<span class="foms-prod-home__pr is-why"><b class="is-none">담당 없음</b> · <span>영업 박가짜</span></span>' in job
    assert "다도면 사는 곳" in job.split('data-q="')[1].split('"')[0]  # 주소로 찾기는 그대로
    made_job = grp.split(f"/sheet/{made.id}")[1].split("</a>")[0]
    assert "나생산 사는 곳" in made_job and "is-why" not in made_job  # 내려온 줄은 주소 그대로
    set_cookies(client, PC)
    pc = get_html(client, HOME + "?tab=all")
    pgrp = pc.split(f'data-foms-home-grp="{key}"')[1].split("data-foms-home-grp=")[0]
    assert '<span class="fph-dwst is-late">도면 2/3 마감 지남</span>' in pgrp.split("</button>")[0]
    order = [pgrp.index(f'data-foms-home-dayrow="{o.id}"') for o in (wait, made, done)]
    assert order == sorted(order)


def _sheet_order(name: str, stage: str, off: int, *, files: int = 0, **sd_extra) -> Order:
    day = (get_today_kst() + datetime.timedelta(days=off)).isoformat()
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": name}, "manager": {"name": "이가짜"}},
          "schedule": {"construction": {"date": day}}, "items": [{"product_name": "붙박이장"}],
          "drawing_current_files": [{"key": f"orders/x/{name}{j}.png", "filename": f"{name}{j}.png",
                                     "view_url": f"/files/view/{name}{j}.png"} for j in range(files)], **sd_extra}
    order = Order(received_date=day, customer_name=name, phone="010-0000-0000", address="가짜시", product="장", status=stage,
                  is_erp_order=True, erp_stage_code=stage, erp_construction_date=day, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def test_작업_시트_안_내려온_주문은_도면_칸에_까닭_담당_마감(client, cohort) -> None:
    """§5-7: 그림이 없으면 빈 자리 글을 바꾸고, 그림이 있으면(영업 확인 · 고객 컨펌) 그림 위 띠로 같은 글. 내려온 주문은 그대로.
    '알림 보냄' 줄은 P3 자리라 지금은 안 그린다."""
    from tests.domains.test_production_home_tabs import _make_user

    _make_user(client, "v7_sheet", "PRODUCTION")
    fix = _sheet_order("가고침", "DRAWING", 1, drawing_status="RETURNED", drawing_assignees=[{"id": 1, "name": "장가짜"}])
    sales = _sheet_order("나확인", "DRAWING", 12, files=2, drawing_status="TRANSFERRED",
                         drawing_assignees=[{"id": 1, "name": "장가짜"}])
    nobody = _sheet_order("다없음", "CONFIRM", 1, drawing_status="PENDING")
    made = _sheet_order("라생산", "PRODUCTION", 1)
    fix, sales, nobody, made = fix.id, sales.id, nobody.id, made.id  # 요청마다 세션이 닫혀 객체가 떨어진다 — 번호만 쓴다
    body = client.get(f"/erp/production/sheet/{fix}").get_data(as_text=True)
    box = body.split('class="foms-prod-page__nodwg is-wait" data-foms-sheet-dwwait>')[1].split("</div>")[0]
    assert box.startswith('<b>도면이 아직 안 내려왔어요</b><span>도면 고치는 중 · 도면 장가짜 · 영업 이가짜</span><span class="is-late">마감 ')
    assert "지났어요</span>" in box and "<small>" not in box and "알림 보냄" not in body
    assert "도면 전달본이 아직 없어요." not in body
    body = client.get(f"/erp/production/sheet/{sales}").get_data(as_text=True)
    band = body.split('class="foms-prod-page__dwband" data-foms-sheet-dwwait>')[1].split("</div>")[0]
    assert "<span>영업 확인 기다림 · 도면 장가짜 · 영업 이가짜</span><span>마감 " in band  # 여유 = 색 없음
    assert "data-foms-sheet-dwg-main" in body  # 그림은 그대로
    body = client.get(f"/erp/production/sheet/{nobody}").get_data(as_text=True)
    assert '<span><em class="is-none">담당 없음</em> · 영업 이가짜</span>' in body
    body = client.get(f"/erp/production/sheet/{made}").get_data(as_text=True)
    assert "data-foms-sheet-dwwait" not in body and "도면 전달본이 아직 없어요." in body
    # PC 시트도 같은 템플릿
    set_cookies(client, PC)
    assert "data-foms-sheet-dwwait" in get_html(client, f"/erp/production/sheet/{fix}")


def test_작업_시트_도면_칸_글은_쿼리를_늘리지_않는다(client, cohort) -> None:
    """§8 표: 작업 시트는 P3(알림 기록 읽기) 전까지 쿼리 그대로 — 안 내려온 주문 · 내려온 주문 같은 수."""
    from sqlalchemy import event

    from db import engine
    from tests.domains.test_production_home_tabs import _make_user

    _make_user(client, "v7_sheet_qc", "PRODUCTION")
    wait = _sheet_order("가기다림", "DRAWING", 3, drawing_assignees=[{"id": 1, "name": "장가짜"}]).id
    made = _sheet_order("나생산", "PRODUCTION", 3).id
    counts = {}
    for name, oid in (("wait", wait), ("made", made)):
        client.get(f"/erp/production/sheet/{oid}")
        seen = {"q": 0}

        def _before(*_a, **_k):
            seen["q"] += 1

        event.listen(engine, "before_cursor_execute", _before)
        try:
            assert client.get(f"/erp/production/sheet/{oid}").status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        counts[name] = seen["q"]
    assert counts["wait"] == counts["made"], counts


def _css_token(css: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}});", css)
    assert m, name
    return m.group(1).lower()


#: 도면 마감 상태 색 — 2026-11-22 실화면 검토 뒤 값. 바꾸려면 아래 거리 · 대비 규칙을 다시 재고 이 표와 같이 고친다.
DEADLINE_TOKENS = {"--fph-dw-late": "#b91c1c", "--fph-dw-soon": "#68550d", "--fph-dw-ok": "#047857", "--fph-brand-dark": "#4a55b8"}
DARK_TOKENS = {"--fpp-dw-late-on-dark": "#fca5a5", "--fpp-dw-soon-on-dark": "#fcd34d"}


def test_도면_마감_색_넷은_짝마다_정상_10_색약_6_이상이고_글_대비_4_5_이상() -> None:
    """상태 색 규칙(ΔE2000 ≥ 10 정상 · ≥ 6 녹색맹 · 적색맹 흉내, 글 대비 ≥ 4.5)을 값과 함께 못 박는다(소스 계약).
    목업 빠듯 주황 #b45309 는 늦음 빨강과 녹색맹 흉내 5.8 이라 실화면에서 같은 빨강으로 읽혔다(2026-11-22)."""
    from itertools import combinations

    from tests.support.color_contrast import blend, contrast_ratio, hex_rgb, pair_distances

    home = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    sheet = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    parts = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    assert {k: _css_token(home, k) for k in DEADLINE_TOKENS} == DEADLINE_TOKENS
    assert {k: _css_token(sheet, k) for k in DARK_TOKENS} == DARK_TOKENS
    colors = {k: hex_rgb(v) for k, v in DEADLINE_TOKENS.items()}
    for a, b in combinations(colors, 2):
        normal, deu, pro = pair_distances(colors[a], colors[b])
        assert normal >= 10 and deu >= 6 and pro >= 6, (a, b, round(normal, 1), round(deu, 1), round(pro, 1))
    # 글이 놓이는 바탕: 띠 흰 · 고른 띠 줄 · 장 · 찾기 바탕(넷 다). 칩(여러 날 장의 '마감 M/D' — 기다림 칸 · 파트 기다림 칩)은
    # 주문 하나의 상태(늦음 · 빠듯 · 여유)만 놓인다 — '다 옴' 은 줄 · 묶음 글에만 있다.
    wide = [_css_token(home, k) for k in ("--fph-surface", "--fph-brand-50", "--fph-bg")]
    chips = [_css_token(home, "--fph-raised"), _css_token(parts, "--fph-wait-50")]
    for name, rgb in colors.items():
        for back in wide + (chips if name != "--fph-dw-ok" else []):
            assert contrast_ratio(rgb, hex_rgb(back)) >= 4.5, (name, back)
    # 어두운 도면 칸(작업 시트): 늦음 · 빠듯 · 그 밖(흰 글 85%) 짝 거리, 칸 · 띠 바탕 대비
    dwg = hex_rgb(_css_token(sheet, "--fpp-dwg"))
    band = blend((0, 0, 0), 0.28, dwg)
    dark = {k: hex_rgb(v) for k, v in DARK_TOKENS.items()}
    dark["plain"] = blend((255, 255, 255), 0.85, dwg)
    for a, b in combinations(dark, 2):
        normal, deu, pro = pair_distances(dark[a], dark[b])
        assert normal >= 10 and deu >= 6 and pro >= 6, (a, b, round(normal, 1), round(deu, 1), round(pro, 1))
    for name, rgb in dark.items():
        assert contrast_ratio(rgb, dwg) >= 4.5 and contrast_ratio(rgb, band) >= 4.5, name
    assert "#fdba74" not in sheet and "#b45309" not in home  # 옛 빠듯 색이 돌아오면 실패
