"""상차 줄 다섯 자리(설계서 2026-11-23 §4-15 · §8-8, 3단계 ⑦ A) — 출고 탭 하루치 출고표 · PC 표 · 폰 카드 · 출고 옆 시트 머리 · 시공 탭 첫 화면.

글은 ``drawing_factory.load_split`` 하나다(그 함수 표는 ``test_drawing_sheet_factory_rules.py``). 여기서는 자리와 "없으면 한 글자도 안
나옴"을 고정한다 — 출고 조각 압축 크기 예산이 27바이트밖에 안 남아, 2공장 장이 없는 날의 응답은 바탕과 같아야 한다.
쿼리는 0 더함(이미 든 주문 JSON). 협력사 출고 탭에는 안 나온다. 이름은 모두 지어낸 값이다.

되돌리면 실패: 상차 줄을 1공장뿐인 주문에 그림 · 2공장 줄이 없는데 상차 모양 파일을 실음 · 자리 하나를 빠뜨림 · 쿼리를 더함.
"""
from __future__ import annotations

import datetime
import itertools
from pathlib import Path

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.construction import tablet_first as tf
from foms.services.datetime_kst import get_today_kst
from foms.services.shipment_dashboard_display import shipment_load_text
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]
SHELL = {"X-FOMS-ERP-SHELL": "1"}
CSS_FILE = "css/components/foms-load-split.css"
MIXED_TEXT = "상차 1공장 2장 · 2공장 1장"
#: 화면 글 = 같은 글의 공장 이름만 공장 칩(사장님 2026-11-24 식별성 — 거르개 factory_chips, 모양은 foms-factory-chip.css 를 @import)
F1 = '<em class="foms-fac foms-fac--1">1공장</em>'
F2 = '<em class="foms-fac foms-fac--2">2공장</em>'
#: 공장 몫마다 한 덩이(2026-11-24 검토 6 — 거르개 factory_line_chips, 줄이 갈리면 " · " 를 CSS 가 가린다). 글은 그대로.
SEP = '<span class="foms-fac-sep"> · </span>'
MIXED_HTML = ('<span class="foms-fac-line"><span class="foms-fac-line__in"><span class="foms-fac-seg">상차 '
              f'<span class="foms-fac-nw">{F1} 2장</span></span><span class="foms-fac-seg">{SEP}'
              f'<span class="foms-fac-nw">{F2} 1장</span></span></span></span>')
PHONE_HTML = MIXED_HTML.replace('<span class="foms-fac-seg">상차 ', '<span class="foms-fac-seg">')
_seq = itertools.count(1)


def _sd(name: str, today: str, *, f2: bool, stage: str = "CONSTRUCTION", code: str = "") -> dict:
    code = code or f"o{next(_seq)}"  # 시트 신원은 영문 · 숫자만(clean_sheet_id)
    files = [{"key": f"orders/x/drawing/{code}_{j}.png", "filename": f"{name}-{j}.png", "sheet_id": f"{code}-s{j}"}
             for j in range(3)]
    sd = {"workflow": {"stage": stage}, "drawing_current_files": files,
          "parties": {"customer": {"name": name}, "orderer": {"name": "가짜 인테리어"}},
          "schedule": {"construction": {"date": today}}, "shipment": {"construction_workers": ["가짜기사"]},
          "items": [{"product_name": "붙박이장", "spec_width": "2400"}], "site": {"address_full": "가짜시 가짜로 1"}}
    if f2:
        sd["drawing_factory"] = {"sheets": {f"{code}-s2": 2}, "files": {}, "at": "2026-11-24T00:00:00+00:00",
                                 "by_name": "오가람"}
    return sd


def _order(name: str, *, f2: bool, stage: str = "CONSTRUCTION") -> int:
    today = get_today_kst().isoformat()
    o = Order(received_date=today, customer_name=name, phone="010-0000-0000", address="가짜시 가짜로 1", product="붙박이장",
              status=stage, manager_name="가짜영업", is_erp_order=True, structured_data=_sd(name, today, f2=f2, stage=stage),
              erp_stage_code=stage, scheduled_date=today, erp_construction_date=today)
    db_session.add(o)
    db_session.flush()
    db_session.add(OrderScheduleDate(order_id=o.id, kind="construction", date=today, source="beta_schedule"))
    db_session.commit()
    return o.id


def _login(client, monkeypatch, username: str = "load-admin", role: str = "ADMIN", team: str = "CS") -> None:
    user = User(username=username, password=generate_password_hash("x"), role=role, team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _fragment(client, cookies: dict[str, str] | None = None) -> str:
    for k, v in (cookies or {}).items():
        client.set_cookie(k, v, domain="localhost")
    res = client.get("/erp/shipment?view=fragment", headers=SHELL)
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_load_text_only_for_mixed_orders():
    today = get_today_kst().isoformat()
    assert shipment_load_text(_sd("평범", today, f2=False)) is None
    assert shipment_load_text({}) is None and shipment_load_text(None) is None
    assert shipment_load_text(_sd("섞임", today, f2=True)) == MIXED_TEXT
    # 생산 중이면 안 끝난 공장에 "(제작 중)"(공장 완료 표지 없음 → 두 공장 모두)
    assert shipment_load_text(_sd("섞임", today, f2=True, stage="PRODUCTION")) == "상차 1공장 2장(제작 중) · 2공장 1장(제작 중)"


def test_shipment_fragment_draws_load_split_in_grid_pc_and_phone(client, monkeypatch):
    """쿠키 없음(모든 표면) — 하루치 출고표 표식 · PC 표 작은 줄 · 폰 dl 한 줄, 모양 파일은 한 번. 1공장 주문 줄에는 없다."""
    _login(client, monkeypatch)
    mixed = _order("가짜섞임", f2=True)
    plain = _order("가짜평범", f2=False)
    html = _fragment(client)
    assert html.count(CSS_FILE) == 1
    assert html.count(f'data-ship-load>{MIXED_HTML}</span>') == 1  # 하루치 출고표 고객 칸
    assert html.count(f'<div class="small foms-load-split" data-shipment-load>{MIXED_HTML}</div>') == 1  # PC 표 고객 칸
    assert html.count(f'<dt>상차</dt><dd class="foms-load-split" data-shipment-load>{PHONE_HTML}</dd>') == 1  # 폰 카드
    grid_plain = html.split(f'id="shipment-tgrid-row-{plain}"', 1)[1].split("</tr>", 1)[0]
    assert "foms-load-split" not in grid_plain
    grid_mixed = html.split(f'id="shipment-tgrid-row-{mixed}"', 1)[1].split("</tr>", 1)[0]
    assert "data-ship-load" in grid_mixed


@pytest.mark.parametrize("cookies", [
    {},
    {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"},
    {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"},
    {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"},
])
def test_no_mixed_order_no_trace_in_fragment(client, monkeypatch, cookies):
    """2공장 장이 없는 날 — 상차 글 · 표식 · 모양 파일 한 글자도 없음(바이트 예산 · 바탕과 같은 응답)."""
    _login(client, monkeypatch, username=f"load-none-{cookies.get('foms_vw', 'all')}-{cookies.get('foms_ptr', '')}")
    _order("가짜평범1", f2=False)
    _order("가짜평범2", f2=False)
    html = _fragment(client, cookies)
    for token in ("foms-load-split", "data-ship-load", "data-shipment-load", "load_split", "상차 1공장", "<dt>상차</dt>", "foms-fac"):
        assert token not in html, token


def test_side_sheet_head_line_only_for_mixed(client, monkeypatch):
    _login(client, monkeypatch, username="load-sheet")
    mixed = _order("가짜시트섞임", f2=True)
    plain = _order("가짜시트평범", f2=False)
    m = client.get(f"/erp/shipment/tablet-sheet/{mixed}").get_data(as_text=True)
    p = client.get(f"/erp/shipment/tablet-sheet/{plain}").get_data(as_text=True)
    assert f'<div class="foms-ship-sheet__count foms-load-split" data-ship-load>{MIXED_HTML}</div>' in m
    assert m.count(CSS_FILE) == 1
    assert "foms-load-split" not in p and "상차 1공장" not in p and "foms-fac" not in p


def test_construction_first_screen_row_and_css_gate(app):
    """시공 탭 첫 화면(시공자 본인) — 줄 값 load_text · 모양 파일 실을지(has_load_split). 1공장뿐이면 None · False."""
    _order("가짜시공섞임", f2=True)
    plain = _order("가짜시공평범", f2=False)
    admin = User(username="load-cons", password="x", role="ADMIN", team="CS", name="가짜관리", is_active=True)
    db_session.add(admin)
    db_session.commit()
    first = tf.build_tablet_first(db_session, user=admin, mine_only=False, worker_settings=[], worker="",
                                  today=get_today_kst())
    rows = {r["id"]: r for s in first["sections"] for g in s["groups"] for r in g["rows"]}
    assert rows[plain]["load_text"] is None
    assert [r["load_text"] for r in rows.values() if r["load_text"]] == [MIXED_TEXT]
    assert first["has_load_split"] is True
    db_session.query(Order).filter(Order.id != plain).delete()
    db_session.commit()
    again = tf.build_tablet_first(db_session, user=admin, mine_only=False, worker_settings=[], worker="",
                                  today=get_today_kst())
    assert again["has_load_split"] is False


def test_templates_gate_every_spot_with_no_output_when_absent():
    """다섯 자리 · 모양 파일이 모두 조건 안에 있고, 조건 밖에 새 공백 · 빈 칸이 없다(구조 시험)."""
    grid = (ROOT / "templates/shipment/partials/tablet_ship_grid.html").read_text(encoding="utf-8")
    assert ("{%- if r.shipment_load_text is defined and r.shipment_load_text %}<span class=\"foms-tablet-shipgrid__flag "
            "foms-load-split\" data-ship-load>{{ r.shipment_load_text | factory_line_chips }}</span>{% endif %}") in grid
    main = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert "{% endif %}{% if r.shipment_load_text is defined and r.shipment_load_text %}<div class=\"small foms-load-split\"" in main
    assert "{% if rows|selectattr('shipment_load_text')|first is defined %}" in main
    phone = (ROOT / "templates/shipment/partials/shipment_mobile_queue.html").read_text(encoding="utf-8")
    assert "</div>{% if meta.load_text %}" in phone
    sheet = (ROOT / "templates/shipment/partials/tablet_sheet.html").read_text(encoding="utf-8")
    assert "{% if load_text %}" in sheet
    cons = (ROOT / "templates/construction/partials/tablet_first_body.html").read_text(encoding="utf-8")
    assert "{%- endmacro %}{% if F.has_load_split %}" in cons
    assert "{% if r.load_text %}<small class=\"foms-load-split\" data-cons-load>{{ r.load_text | factory_line_chips }}</small>" in cons


def test_partner_shipment_tab_has_no_load_split():
    """협력사는 상차하지 않는다 — 협력사 출고 탭 줄 · 템플릿에 상차 줄이 없다."""
    from foms.services.partners import shipment_board

    src = Path(shipment_board.__file__).read_text(encoding="utf-8")
    assert "load_split" not in src and "shipment_load_text" not in src
    for tpl in (ROOT / "templates").rglob("*.html"):
        if "partner" in tpl.as_posix():
            text = tpl.read_text(encoding="utf-8")
            assert "load_split" not in text and "load_text" not in text, tpl


def test_css_font_sizes_scale_and_no_achromatic():
    import re

    css = re.sub(r"/\*.*?\*/", "", (ROOT / "static" / CSS_FILE).read_text(encoding="utf-8"), flags=re.S)
    for m in re.finditer(r"font-size:\s*([^;]+);", css):
        # 새 px 글자는 배율 꼴만, 시공 칸 조각은 놓인 칸 글자 그대로(inherit — 칸 span 14px 묶음 밖으로)
        assert re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)|inherit", m.group(1).strip()), m.group(1)
    # 공장 색은 공장 칩 한 곳(@import) — 이 파일은 공장 색을 따로 두지 않는다(옛 2공장 청록 #0f6b63 · #0d9488 은 '완료' 초록과 가까웠다)
    assert css.lstrip().startswith('@import url("foms-factory-chip.css?v=') and "#0f6b63" not in css and "#0d9488" not in css
    for grey in ("#6b7280", "#9ca3af", "#e5e7eb", "gray", "grey"):
        assert grey not in css.lower()


def _count(fn) -> int:
    n = {"q": 0}

    def _before(*_a, **_k):
        n["q"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return n["q"]


def test_queries_unchanged_with_mixed_orders(client, monkeypatch):
    """같은 줄 수에서 2공장 장이 섞여도 출고 조각 쿼리 수가 같다(이미 든 주문 JSON 만 읽음)."""
    _login(client, monkeypatch, username="load-q")
    ids = [_order(f"가짜쿼리{i}", f2=False) for i in range(3)]
    _fragment(client)  # 데우기(설정 · 캐시)
    base = _count(lambda: _fragment(client))
    for oid in ids:
        o = db_session.get(Order, oid)
        sd = dict(o.structured_data)
        sd["drawing_factory"] = {"sheets": {sd["drawing_current_files"][2]["sheet_id"]: 2}, "files": {}}
        o.structured_data = sd
    db_session.commit()
    from foms.services.common.dashboard_cache import invalidate_all_dashboard_slice_caches

    invalidate_all_dashboard_slice_caches()
    _fragment(client)
    mixed = _count(lambda: _fragment(client))
    assert mixed == base, (base, mixed)


def test_load_split_cost_is_constant_time_for_plain_rows():
    """2공장 표가 없는 주문은 확정 도면 목록도 안 훑는다(조각 시간 예산 — has_second_factory 가 표부터 본다)."""
    today = get_today_kst().isoformat()
    sd = _sd("가짜", today, f2=False)
    sd["drawing_current_files"] = None  # 훑으면 깨질 모양이어도
    assert shipment_load_text(sd) is None
    assert datetime.date.fromisoformat(today)
