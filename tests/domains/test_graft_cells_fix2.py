"""접목판 분홍 칸 점검 2차 고침(11-15) — 칩 자리 · 칩 글 · 폰 머리 · 상세 'AI 제안' 상자 · 상세 아래 단추 줄.

번호는 docs/plans/2026-11-14-foms-graft-plan.md '점검 2차' 절(w4-05 · w4-06 · w4-07 · w4-09 · w4-10 · w4-11 · w4-12 ·
w5-01 · w5-03). 칸 폭(w4-04 · w4-08)과 단계 한 줄(w4-01)은 test_graft_cells.py 의 같은 자리 시험이 지킨다. 지어낸 자료만 ·
바깥으로 보내지 않는다(fetch · 알림톡은 가짜).
"""

from __future__ import annotations

import datetime
import re

import pytest

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_actions.lifecycle import propose
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, User
from tests.domains.test_graft_cells import (  # noqa: F401 — world 는 pytest 고정물(이름으로 찾는다)
    CELLS_JS, NODE, ROOT, _SOLAPI_READY, _day, _ok, _pages, _sheet_box, _switch, run_node, world,
)


def test_pc_chip_sits_right_under_the_task_line_not_under_the_opened_card(world, monkeypatch):
    """점검 2차 w4-10 — '▼ 작업 이름'을 눌러 펼친 큰 카드(collapse)보다 위, 그 줄 바로 아래. 줄마다 칩 자리는 하나."""
    _switch(monkeypatch, "999999", "brain_ui", "actions", "cell_pc")
    pc = _pages(world, monkeypatch)["pc"]
    seen = 0
    for oid in world["orders"]:
        cell = pc[pc.index(f'<tr class="erp-main-row" data-order-id="{oid}"'):]
        cell = cell[cell.index('data-col-key="quest"'):cell.index('data-col-key="customer"')]
        assert cell.count("data-graft-slot=") == 1, oid
        if f'id="quest-collapse-{oid}"' in cell:
            seen += 1
            stack_end = cell.index("</div>", cell.index("erp-grid-quest-stack"))
            assert stack_end < cell.index("foms-graft-chip-slot") < cell.index(f'id="quest-collapse-{oid}"'), oid
    assert seen  # 현재 작업(펼침 카드)이 있는 줄을 적어도 하나 봤다


def test_open_chip_carries_the_value_for_date_proposals(world):
    """점검 2차 w4-09 — 판 NowPC ① 처럼 날짜를 넣는 제안은 칩 값 글('11-21(토) 오전으로 옮기기' 꼴 · 날짜 + 시간대만 D211),
    그 밖은 빈 글(칩은 할 일 이름). '로/으로'는 끝 글자 받침으로 고른다."""
    from foms.services.erp_actions.views import open_for_orders, value_label

    admin = db_session.get(User, world["admin"])
    items = open_for_orders(db_session, admin, world["orders"])
    a, b = world["orders"]
    day = datetime.date.fromisoformat(_day(9))
    weekday = "월화수목금토일"[day.weekday()]
    assert items[a]["value_label"] == f"{day:%m-%d}({weekday}) 오전으로 잡기"  # 시공 잡기 · 오전
    assert items[b]["value_label"] == ""  # 도면 담당 맡기기 — 날짜 없음

    class _Row:  # 받침 · 시간대 갈래(지어낸 값)
        def __init__(self, action, params):
            self.action, self.params = action, params

    assert value_label(_Row("move_measurement", {"date": "2030-11-23"})) == "11-23(토)로 옮기기"
    assert value_label(_Row("move_construction", {"date": "2030-11-21", "time": "오후"})) == "11-21(목) 오후로 옮기기"
    assert value_label(_Row("move_construction", {"date": "2030-11-22", "time": ""})) == "11-22(금)으로 옮기기"
    assert value_label(_Row("schedule_as_visit", {"date": "2030-11-25"})) == "11-25(월)로 옮기기"
    assert value_label(_Row("move_construction", {"date": "", "time": "오전"})) == ""
    assert value_label(_Row("send_measure_alimtalk", {})) == ""


@NODE
def test_chip_text_by_cell_value_on_pc_and_no_head_word_on_the_phone(world, monkeypatch):
    """점검 2차 w4-09 · w4-04 · w5-01 — PC 칩은 값 글이 있으면 값(머리글 'AI 제안 · '는 따로 — 좁은 칸에서 꾸밈이 감춘다),
    태블릿 표는 '제안' 표지(칸 51px), 폰은 머리글 없이 할 일 이름. 읽어 주는 글 · title 에는 온전한 'AI 제안 · <이름>'."""
    a = world["orders"][0]
    first = world["proposals"][0]
    html = "".join(f'<a class="foms-graft-chip" data-graft-slot="{a}" data-graft-cell="{cell}" hidden></a>'
                   for cell in ("pc", "tablet", "mobile"))
    routes = [{"method": "GET", "url": "/api/erp-actions/badge", "replies": [_ok(
                  {"on": {"actions": True, "pc": True, "tablet": True, "mobile": True}, "actions": 1, "knowledge": 0,
                   "total": 1, "labels": ["방문 옮기기(시공)"]})]},
              {"method": "GET", "url": "/api/erp-actions/open", "replies": [_ok({"items": {str(a): {
                  "id": first, "action": "move_construction", "label": "방문 옮기기(시공)", "agent_label": "상담 AI",
                  "can_decide": True, "value_label": "11-21(토) 오전으로 옮기기"}}})]}]
    body = """return api.qa('[data-graft-slot]').map(n => [n.getAttribute('data-graft-cell'), api.text(n),
                     n.getAttribute('aria-label'), n.getAttribute('title'),
                     api.text(n.querySelector('.foms-graft-chip__head'))]);"""
    got = run_node(html, body, scripts=[str(CELLS_JS)], routes=routes)
    tail = " — 상담 AI · 누르면 승인 대기"
    full_pc, full = "AI 제안 · 11-21(토) 오전으로 옮기기", "AI 제안 · 방문 옮기기(시공)"
    assert got == [["pc", full_pc, full_pc, full_pc + tail, "AI 제안 ·"],  # 머리글 칸(api.text 는 앞뒤 빈칸을 떼고 읽는다)
                   ["tablet", "제안", full, full + tail, None],
                   ["mobile", "방문 옮기기(시공)", full, full + tail, None]]


def test_pc_head_word_hides_in_a_narrow_column_and_tablet_mark_fits_46px():
    """점검 2차 w4-09 · w4-04 — PC 머리글은 칸 폭(자리 상자 = 크기 그릇)으로 가른다: 200px 아래 칸이면 감춘다(1440 의 164px),
    사용자 2400 화면(232px)에서는 판처럼 보인다. 태블릿 표지(약 52px)는 46px 칸(110 ~ 130%)에서도 칸 오른쪽 안쪽 여백 10px 를
    더 써서 들고(칸 폭 계산에는 안 낀다) 누르는 겹은 44px."""
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    assert "container-type: inline-size;" in re.search(r"\.foms-graft-chip-slot \{(.*?)\}", css).group(1)
    assert re.search(r"@container \(max-width: 199\.98px\) \{\s*\.foms-graft-chip__head \{ display: none; \}", css)
    mark = css[css.index("body.erp-mobile-v2-layout .foms-tqcell-quest .foms-graft-chip {"):]
    mark = mark[:mark.index("}")]
    assert "padding: 0 4px;" in mark and "gap: 2px;" in mark and "calc(12px * var(--foms-fs, 1))" in mark
    slot = re.search(r"\.foms-tqcell-quest \.foms-graft-chip-slot \{(.*?)\}", css, re.S).group(1)
    assert "min-width: calc(100% + 10px);" in slot and "margin-right: -10px;" in slot  # 칸 오른쪽 여백(12px) 안
    tap = re.search(r"\.foms-tqcell-quest \.foms-graft-chip::after \{(.*?)\}", css, re.S).group(1)
    assert "top: -12px;" in tap and "bottom: -8px;" in tap and "width: max(100%, 44px);" in tap  # 24 + 12 + 8 = 44


def test_phone_chip_takes_only_the_room_left_in_the_card_head():
    """점검 2차 w5-01 — 칩이 붙으면 이력 단추가 둘째 줄로 떨어지고 카드가 30px 길어졌다(max-width 55%). 칩의 바탕 폭은 0 이라
    머리 줄을 넘기지 않고 남는 폭만큼 자라되 제 글 폭을 넘지 않는다(모자라면 글만 말줄임). 어두운 화면 규칙도 있다(w5-03)."""
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    card = re.search(r"\.foms-graft-chip--card \{(.*?)\}", css, re.S).group(1)
    assert "flex: 1 1 0;" in card and "max-width: max-content;" in card and "55%" not in card
    dark = re.search(r"\[data-theme='dark'\] \.foms-graft-chip \{(.*?)\}", css, re.S).group(1)
    assert "--foms-surface-accent" in dark and "--foms-color-brand-300" in dark


def test_tablet_box_head_buttons_and_approve_colour():
    """점검 2차 w4-06 · w4-07 · w4-11 — 머리 한 줄(직원 이름은 꺾지 않음 · 제목은 낱말 사이에서만) · 단추 44px ·
    [승인]은 태블릿 주 단추 남보라(전역 .btn-primary 가 칠하는 변수를 상자 안에서만 바꾼다)."""
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    agent = re.search(r"\.foms-graft-box__agent \{(.*?)\}", css, re.S).group(1)
    title = re.search(r"\.foms-graft-box__title \{(.*?)\}", css, re.S).group(1)
    assert "white-space: nowrap;" in agent and "flex: none;" in agent and "word-break: keep-all;" in title
    btn = css[css.index("body.erp-mobile-v2-layout .foms-graft-box__reason {"):]
    assert "min-height: var(--foms-touch-target-comfortable, 44px);" in btn[:btn.index("}")]
    box = re.search(r"body\.erp-mobile-v2-layout \.foms-graft-box \{(.*?)\}", css, re.S).group(1)
    assert "--brand-primary: var(--foms-interactive-primary, #5a67d8);" in box
    pro = (ROOT / "static/css/foundation/style-pro-max.css").read_text(encoding="utf-8")
    assert re.search(r"\.btn-primary \{\s*background: var\(--brand-primary\) !important;", pro)  # 변수로 칠하는 것 그대로


def test_tablet_box_reads_the_alimtalk_value_as_still_to_send(world, monkeypatch):
    """점검 2차 w4-12 — 알림톡 보내기 제안의 굵은 줄이 '1건 보냄' 하나라 이미 보낸 것처럼 읽혔다 → '승인하면 1건 보내요'.
    승인 대기 카드(앞뒤가 있는 '보낸 적 없음 → 1건 보냄')와 저장된 미리 보기는 그대로다."""
    import foms.services.kakao_alimtalk as kakao
    from foms.persistence.graft.models import ErpActionProposal

    monkeypatch.setattr(kakao, "_solapi_send", lambda **kw: pytest.fail("그리기만 — 보내지 않는다"))
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_tablet")
    for name, value in _SOLAPI_READY:
        monkeypatch.setenv(name, value)
    sd = {"workflow": {"stage": "CONSTRUCTION"}, "parties": {"customer": {"name": "합성손님", "phone": "010-0000-0001"}},
          "schedule": {"construction": {"date": _day(6), "time": "오전"}}}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0001", address="합성 주소",
                  product="합성 품목", status="CONSTRUCTION", is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    row = propose(db_session, action="send_construction_alimtalk", proposed_by="agent:ops", order=order, params={},
                  reason="합성 이유", evidence=[], source_kind="sweep", source_ref="4", level=1, now=now_utc_naive())
    db_session.commit()
    assert row is not None and row.preview[0]["after"] == "1건 보냄"
    box = _sheet_box(world, order.id)
    assert '<span class="foms-graft-box__after">승인하면 1건 보내요</span>' in box and "1건 보냄" not in box
    assert db_session.get(ErpActionProposal, row.id).preview[0]["after"] == "1건 보냄"


def test_sheet_foot_stays_at_the_panel_bottom():
    """점검 2차 w4-05 — 'AI 제안' 상자가 들어가면 아래 단추 줄(전화 · ERP 편집 · 단계로)이 흐름대로 밀려 화면 밖이었다(1176×626 은
    끈 화면에서도) → 패널 아래에 붙는다(sticky · 패널 바탕). 넘치지 않으면 자리 그대로. 바뀐 꾸밈이 기기에 닿게 묶음 핀도 같이."""
    base = (ROOT / "static/css/foundation/foms-tablet-landscape.css").read_text(encoding="utf-8")
    foot = re.search(r"\n\.foms-tsheet-foot \{(.*?)\}", base, re.S).group(1)
    assert "position: sticky;" in foot and "bottom: 0;" in foot and "background: var(--foms-surface-base, #fff);" in foot
    bundle = (ROOT / "static/css/foundation/foms-tablet-bundle.css").read_text(encoding="utf-8")
    assert re.search(r'foms-tablet-landscape\.css\?v=(\w+)', bundle).group(1) != "20261111b"
