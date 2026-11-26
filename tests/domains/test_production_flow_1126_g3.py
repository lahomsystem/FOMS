"""생산 태블릿 작은 흐름 고침 둘(사장님 결정 2026-11-26).

① 작업 시트에서 보류 사유 줄을 공정 칸 바로 위로(보류 중이고 사유가 있을 때만).
② [바뀐 것] 탭의 [확인했어요]는 화면을 다시 읽지 않고 그 줄만 지운다(다른 화면은 지금처럼 다시 읽기).
"""
from __future__ import annotations

from pathlib import Path

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from tests.domains.test_production_sheet_page import SHEET_URL, _make_user, _seed_order

ROOT = Path(__file__).resolve().parents[2]


def _scroll(html: str) -> str:
    return html.split('class="foms-prod-page__side-scroll"', 1)[1].split('class="foms-prod-page__foot"', 1)[0]


def test_보류_중이고_사유가_있으면_보류_사유가_공정_칸_바로_위(client) -> None:
    _make_user(client, "g3_hold_on", "PRODUCTION")
    order = _seed_order()
    sd = dict(order.structured_data)
    sd["production"] = {**sd["production"], "hold": {"active": True, "reason": "자재 기다림", "at": now_utc_naive().isoformat()}}
    order.structured_data = sd
    db_session.commit()
    scroll = _scroll(client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True))
    hold = scroll.find("보류 · <strong>자재 기다림</strong>")
    steps = scroll.find('aria-label="공정"')
    assert 0 <= hold < steps
    between = scroll[hold:steps]
    assert "<section" in between and between.count("<section") == 1  # 보류 줄 다음 첫 상자가 공정(<section 의 시작 글자만 걸림)
    assert scroll.count("보류 · <strong>") == 1  # 아래 자리에 한 번 더 그리지 않는다


def test_보류가_아니면_공정이_맨_위_그대로(client) -> None:
    _make_user(client, "g3_hold_off", "PRODUCTION")
    order = _seed_order()
    scroll = _scroll(client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True))
    assert "callout--hold" not in scroll
    assert scroll[: scroll.find('aria-label="공정"')].count("<section") == 1


def test_보류_사유가_없으면_줄을_그리지_않는다(client) -> None:
    _make_user(client, "g3_hold_noreason", "PRODUCTION")
    order = _seed_order()
    sd = dict(order.structured_data)
    sd["production"] = {**sd["production"], "hold": {"active": True, "reason": "", "at": now_utc_naive().isoformat()}}
    order.structured_data = sd
    db_session.commit()
    scroll = _scroll(client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True))
    assert "callout--hold" not in scroll


def test_보류_줄은_마크업_순서로_옮겼다_CSS_order_아님() -> None:
    tpl = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    assert tpl.index("callout--hold") < tpl.index('aria-label="공정"') < tpl.index('aria-label="변경 알림"')
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    import re
    assert not re.search(r"(?<![\w-])order\s*:", css)
