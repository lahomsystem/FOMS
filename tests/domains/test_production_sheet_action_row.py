"""작업 시트 아래 단추 줄(사장님 2026-11-24 "CSS 정렬 안맞음" — 섞인 주문 [제작 취소] [1공장 완료 취소] [제작 완료 — 검수까지 끝나면 눌러요]).

원인(바탕 4a7bf8587): 단추 줄 ``.foms-prod-page__acts`` 가 한 줄 고정(flex · 줄 넘김 없음)이고 단추는 ``white-space: nowrap`` 인데
[제작 완료] 안의 회색 안내 글만 ``white-space: normal`` 이라 셋이 서면 그 글 혼자 줄어 낱말마다 꺾였다(122px 로 길어짐) —
[제작 취소]만 작은 글자(16px · 56px) · 테두리 없는 꼴이라 높이 · 글 기준선 · 상자 모양이 셋 다 달랐다.

고침(CSS 만, HTML 은 한 글자도 그대로): 줄에 서는 단추는 같은 높이(64px) · 같은 글 크기(20px × 배율) · 같은 상자(1px 테두리 · 12px 모서리),
안내 글은 단추 안 둘째 줄 한 줄(nowrap), 다 안 들어가면 단추째 다음 줄로(넘침 0). 실화면 잰 값은 스크래치패드 p3e(drive.py).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "static/css/contexts/production/sheet.css"


def _rules(selector: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", SHEET.read_text(encoding="utf-8"), flags=re.S)
    found = [m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
             if selector in [x.strip() for x in m.group(1).split(",")]]
    assert found, selector
    return "\n".join(found)


def test_row_wraps_instead_of_squeezing_the_hint():
    row = _rules(".foms-prod-page__acts")
    assert "flex-wrap: wrap" in row and "align-items: stretch" in row
    hint = _rules(".foms-prod-page__off-hint")
    assert "white-space: nowrap" in hint and "white-space: normal" not in hint  # 낱말마다 꺾이지 않는다
    two = _rules(".foms-prod-page__acts > .foms-prod-page__btn:has(> .foms-prod-page__off-hint:not([hidden]))")
    assert "flex-direction: column" in two  # 안내 글 = 단추 안 둘째 줄 한 줄


def test_every_button_in_the_row_has_the_same_box_and_text_size():
    btn = _rules(".foms-prod-page__acts > .foms-prod-page__btn")
    for prop in ("min-height: 64px", "border-radius: 12px", "font-size: calc(20px * var(--foms-fs, 1))", "flex: 1 1 auto"):
        assert prop in btn, prop
    ghost = _rules(".foms-prod-page__acts > .foms-prod-page__btn--ghost")
    assert "border-color: var(--fpp-line2)" in ghost  # [제작 취소] · [N공장 완료 취소]도 보이는 상자(테두리 없는 글 단추 아님)


def test_markup_is_unchanged_one_hint_inside_the_complete_button():
    tpl = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    assert tpl.count('<span class="foms-prod-page__off-hint" data-foms-sheet-complete-hint') == 1
    assert '<button type="button" class="foms-prod-page__btn foms-prod-page__btn--ghost" data-tablet-sheet-action="production-cancel"' in tpl
    assert "style=" not in tpl
