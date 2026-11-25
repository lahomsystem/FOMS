"""작업 시트 아래 단추 줄(사장님 2026-11-24 "CSS 정렬 안맞음" — 섞인 주문 [제작 취소] [1공장 완료 취소] [제작 완료 — 검수까지 끝나면 눌러요]).

원인(바탕 4a7bf8587): 단추 줄 ``.foms-prod-page__acts`` 가 한 줄 고정이고 단추는 ``white-space: nowrap`` 인데 [제작 완료] 안의 안내 글만
줄어들 수 있어 셋이 서면 낱말마다 꺾였다(122px). [제작 취소]만 16px · 56px · 테두리 없는 꼴이라 높이 · 기준선 · 상자가 셋 다 달랐다.

여기서는 CSS 를 작은 캐스케이드로 풀어 "이긴 값"을 잰다(글자열이 있는지만 보지 않는다 — 규칙 순서 · 특이도가 바뀌면 실패):
- 줄의 회색(ghost) 단추: 평소 = 보이는 상자(흰 바탕 · 선), :hover · :focus-visible = 연한 남색 바탕 · 남색 선(검토 2 — 덮이지 않음).
- 줄에 서는 단추 = 64px · 20px × 배율 · 12px 모서리. 안내 글 = 낱말 사이에서만 꺾임(폰 360 · 글자 130% 넘침 0, 검토 3).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "static/css/contexts/production/sheet.css"
BTN = {"foms-prod-page__btn", "foms-prod-page__btn--ghost"}
ROW = {"foms-prod-page__acts"}


def _rules() -> list[tuple[str, str]]:
    """맨 위 규칙(@media 밖)만 — 단추 줄 규칙은 모두 맨 위에 있다."""
    css = re.sub(r"/\*.*?\*/", "", SHEET.read_text(encoding="utf-8"), flags=re.S)
    out, depth, start = [], 0, 0
    for m in re.finditer(r"[{}]", css):
        if m.group() == "{":
            if depth == 0:
                head = css[start:m.start()].strip()
                body_start = m.end()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                if not head.startswith("@"):
                    out.append((head, css[body_start:m.start()]))
                start = m.end()
    return out


def _compound(comp: str, classes: set[str], states: set[str]) -> int | None:
    """한 덩이(.a.b:hover) — 맞으면 특이도(클래스 + 가상 클래스 수), 안 맞으면 None. 그 밖 꼴(:not · :has · *)은 안 맞음으로 본다."""
    m = re.fullmatch(r"((?:\.[\w-]+)+)((?::[\w-]+)*)", comp)
    if not m:
        return None
    cls = set(re.findall(r"\.([\w-]+)", m.group(1)))
    pseudo = re.findall(r":([\w-]+)", m.group(2))
    if not cls <= classes or not all(p in states for p in pseudo):
        return None
    return len(re.findall(r"\.[\w-]+", m.group(1))) + len(pseudo)


def _won(prop: str, states: set[str]) -> str:
    """줄 안 회색 단추(.foms-prod-page__acts > .foms-prod-page__btn.foms-prod-page__btn--ghost)의 ``prop`` 이긴 값."""
    best = (-1, -1, "")
    for order, (head, body) in enumerate(_rules()):
        val = re.search(r"(?:^|;)\s*" + re.escape(prop) + r":\s*([^;]+)", body)
        if not val:
            continue
        for sel in head.split(","):
            parts = [p for p in re.split(r"\s*>\s*|\s+", sel.strip()) if p]
            if len(parts) == 1:
                spec = _compound(parts[0], BTN, states)
            elif len(parts) == 2:
                a, b = _compound(parts[0], ROW, set()), _compound(parts[1], BTN, states)
                spec = None if a is None or b is None else a + b
            else:
                spec = None
            if spec is not None and (spec, order) >= best[:2]:
                best = (spec, order, val.group(1).strip())
    return best[2]


def test_ghost_buttons_in_the_row_are_boxes_and_keep_hover_and_keyboard_focus():
    assert _won("background", set()) == "var(--fpp-surface)" and _won("border-color", set()) == "var(--fpp-line2)"
    for state in ("hover", "focus-visible"):  # 줄 규칙(0,2,0)이 단추 공통 :hover · :focus-visible(0,2,0)보다 뒤라 덮던 것
        assert _won("background", {state}) == "var(--fpp-brand-50)", state
        assert _won("border-color", {state}) == "var(--fpp-brand)", state
        assert _won("color", {state}) == "var(--fpp-brand-dark)", state


def test_every_button_in_the_row_has_the_same_box_and_text_size():
    assert _won("min-height", set()) == "64px" and _won("border-radius", set()) == "12px"
    assert _won("font-size", set()) == "calc(20px * var(--foms-fs, 1))"
    rows = dict(_rules())
    assert "flex-wrap: wrap" in rows[".foms-prod-page__acts"]
    two = rows[".foms-prod-page__acts > .foms-prod-page__btn:has(> .foms-prod-page__off-hint:not([hidden]))"]
    assert "flex-direction: column" in two  # 안내 글 = 단추 안 둘째 줄


def test_hint_wraps_only_between_words():
    hint = dict(_rules())[".foms-prod-page__off-hint"]
    assert "word-break: keep-all" in hint and "white-space: normal" in hint and "nowrap" not in hint
    # 992px 아래 덩이의 겹친 flex-wrap 은 지웠다(맨 위 규칙 하나)
    assert SHEET.read_text(encoding="utf-8").count(".foms-prod-page__acts { flex-wrap: wrap; }") == 0


def test_markup_is_unchanged_one_hint_inside_the_complete_button():
    tpl = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    assert tpl.count('<span class="foms-prod-page__off-hint" data-foms-sheet-complete-hint') == 1
    assert '<button type="button" class="foms-prod-page__btn foms-prod-page__btn--ghost" data-tablet-sheet-action="production-cancel"' in tpl
    assert "style=" not in tpl
