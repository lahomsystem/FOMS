"""가로 터치 태블릿 누름 칸 — 화면 크기 80 · 90 · 100% 모두 보이는 44px (2026-11-22 터치 점검).

화면 크기(html zoom = --foms-ui-zoom)는 손잡이 · 단추까지 같이 줄여, 44px 칸이 80% 에서 35px, 30px 칸은 24px 로 보였다.
고친 칸은 크기를 '44px ÷ 배율'(calc(44px / var(--foms-ui-zoom, 1)))로 잡는다. 이 규칙은 가로 터치 태블릿
(@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)) 안에만 있어야 한다 — PC(마우스)는
사장님이 80% 로 쓰는데 글자 · 단추가 바뀌면 안 되고, 폰(<992px)도 그대로다.
실화면 측정(1176×626 터치 · 80/90/100% · 글자 150%, PC 1440×900 · 폰 390×844 전후 대조)은 스크래치패드 touch_fix/targets.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLET = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
TAP = "calc(44px / var(--foms-ui-zoom, 1))"
GAP = "calc(8px / var(--foms-ui-zoom, 1))"

FILES = {
    "rail": "static/css/foundation/foms-tablet-rail.css",
    "zoom": "static/css/components/foms-ui-zoom.css",
    "cons": "static/css/contexts/construction/tablet-first.css",
    "home": "static/css/contexts/production/home.css",
    "notif": "static/css/components/foms-notification-center.css",
    "reason": "static/css/components/foms-reason-sheet.css",
    "kanban": "static/css/foundation/foms-tablet-production-kanban.css",
    "grid": "static/css/contexts/orders/dashboard-grid.css",
    "landscape": "static/css/foundation/foms-tablet-landscape.css",
    "as": "static/css/foundation/foms-tablet-as-compare.css",
    "as_card": "static/css/components/foms-as-mobile-card.css",
    "completion": "static/css/foundation/foms-tablet-completion-grid.css",
    "drawing": "static/css/foundation/foms-tablet-drawing-gallery.css",
    "cgate": "static/css/components/foms-complete-gate.css",
    "history": "static/css/contexts/history/history-tablet.css",
}


def _css(key: str) -> str:
    return (ROOT / FILES[key]).read_text(encoding="utf-8").replace("\r\n", "\n")


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), css, flags=re.S)


def _tablet_spans(css: str) -> list[tuple[int, int]]:
    """가로 터치 태블릿 @media 블록의 [시작, 끝) — 괄호 짝 맞춤."""
    spans = []
    for m in re.finditer(re.escape(TABLET) + r"\s*\{", css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        spans.append((m.start(), i))
    return spans


def _tablet_text(key: str) -> str:
    css = _strip_comments(_css(key))
    return "\n".join(css[a:b] for a, b in _tablet_spans(css))


def _rule(text: str, selector: str) -> str:
    """선택자로 시작하는 규칙 몸통(마지막 것 — 이번에 덧붙인 규칙은 파일 끝에 있다)."""
    found = re.findall(r"(?<![\w-])" + re.escape(selector) + r"\s*\{([^}]*)\}", text)
    assert found, selector
    return found[-1]


def test_배율_나눔_누름_칸은_가로_터치_태블릿_안에만_있다() -> None:
    """'÷ 배율' 누름 칸 규칙이 미디어쿼리 밖으로 새면 PC(80%) 단추가 커진다 — 파일마다 모두 블록 안이어야 한다."""
    for key in FILES:
        css = _strip_comments(_css(key))
        spans = _tablet_spans(css)
        hits = [m.start() for m in re.finditer(r"calc\((?:44|8|50)px / var\(--foms-ui-zoom, 1\)\)", css)]
        assert hits, key
        outside = [css[max(0, h - 80):h + 40] for h in hits if not any(a <= h < b for a, b in spans)]
        assert not outside, (key, outside)


def test_레일_화면_크기_손잡이_빼기_더하기_44_숫자는_보여_주기만() -> None:
    t = _tablet_text("rail")
    btn = _rule(t, ".foms-tablet-rail .foms-ui-zoom--rail .foms-ui-zoom__btn")
    assert f"height: {TAP}" in btn and "width: 100%" in btn
    assert "width: calc(max(44px, " + TAP + ") + 4px)" in _rule(t, ".foms-tablet-rail .foms-ui-zoom--rail")
    now = _rule(t, ".foms-tablet-rail .foms-ui-zoom--rail .foms-ui-zoom__now")
    assert "pointer-events: none" in now
    # 손잡이 밖(공용) 모양은 그대로 — 레일 30px · 숫자 20px 규칙이 남아 있다(가로 태블릿이 아닌 곳의 바탕)
    css = _css("rail")
    assert re.search(r"\.foms-ui-zoom--rail \.foms-ui-zoom__btn \{\s*width: 44px;\s*height: 30px;", css)
    assert re.search(r"\.foms-ui-zoom--rail \.foms-ui-zoom__now \{\s*width: 44px;\s*height: 20px;", css)
    # 되돌리기 동작 자체(ui-zoom.js · 조각 data-foms-ui-zoom-reset)는 그대로 — PC 막대 · 폰 서랍에서 쓴다
    assert "data-foms-ui-zoom-reset" in (ROOT / "templates/partials/shared/foms_ui_zoom_control.html").read_text(encoding="utf-8")
    assert "hasAttribute('data-foms-ui-zoom-reset')" in (ROOT / "static/js/foms/ui-zoom.js").read_text(encoding="utf-8")


def test_레일_아바타_누름_칸_44_원은_그대로_80퍼센트에선_F_숨기고_칸_사이_0() -> None:
    t = _tablet_text("rail")
    av = _rule(t, ".foms-tablet-rail:has(> .foms-tablet-rail__menu) > a.foms-tablet-rail__avatar[href]")
    assert f"width: max(40px, {TAP})" in av and f"height: max(40px, {TAP})" in av
    assert "background-clip: content-box" in av
    assert "margin: calc(8px / var(--foms-ui-zoom, 1)) 0" in av
    assert "display: none" in _rule(t, 'html[data-foms-ui-zoom^="0."] .foms-tablet-rail__brand')
    assert re.search(r'html\[data-foms-ui-zoom\^="0\."\] \.foms-tablet-rail,\s*html\[data-foms-ui-zoom\^="0\."\] \.foms-tablet-rail__menu \{\s*gap: 0;', t)
    # 접목판 아바타 여백 규칙(0,4,0)보다 특이도가 높아야 이긴다 — [href] 가 그 몫
    assert ".foms-tablet-rail:has(> .foms-graft-rail:not([hidden])) .foms-tablet-rail__avatar {" in (
        ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    # 생산 첫 화면 레일 숨김(계산기 · 회사 지식 · 알림)은 그대로
    home = _css("home")
    assert 'body:has(.foms-prod-home-page) .foms-tablet-rail > .foms-tablet-rail__notify { display: none; }' in home


def test_글자_손잡이_세_곳_모두_44_칸_사이_8() -> None:
    z = _tablet_text("zoom")
    assert GAP in _rule(z, ".foms-fs")
    assert f"width: {TAP}" in _rule(z, ".foms-fs__btn {".rstrip(" {"))
    assert re.search(r"\.foms-fs__btn,\s*\.foms-fs__now \{\s*height: " + re.escape(TAP), z)
    assert "min-width: calc(50px / var(--foms-ui-zoom, 1))" in z
    c = _tablet_text("cons")
    assert f"body.erp-mobile-v2-layout .foms-cons-first__tools .foms-fs {{ gap: {GAP}; }}" in c
    assert f"body.erp-mobile-v2-layout .foms-cons-first__tools .foms-fs__btn {{ width: {TAP}; }}" in c
    h = _tablet_text("home")
    assert f".foms-prod-home .foms-fs {{ height: auto; gap: {GAP}; }}" in h
    assert f".foms-prod-home .foms-fs__btn, .foms-prod-home .foms-fs__now {{ height: {TAP}; }}" in h
    assert f".foms-prod-home .foms-fs__now {{ min-width: max(60px, {TAP}); }}" in h


def test_알림_사유_그림_보기_닫기와_화살표() -> None:
    n = _tablet_text("notif")
    close = _rule(n, ".erp-mobile-notif-sheet__actions .btn-close")
    assert f"width: {TAP}" in close and f"height: {TAP}" in close and "box-sizing: border-box" in close
    assert f"min-height: {TAP}" in _rule(n, ".erp-mobile-notif-sheet__action")
    assert GAP in _rule(n, ".erp-mobile-notif-sheet__actions")
    r = _tablet_text("reason")
    assert f"min-width: {TAP}" in _rule(r, ".foms-reason-sheet__close") and f"min-height: {TAP}" in _rule(r, ".foms-reason-sheet__close")
    v = _rule(_tablet_text("zoom"), "#global-image-viewer .global-viewer-nav")
    assert f"width: {TAP}" in v and f"height: {TAP}" in v


def test_생산_보드_KPI_와_도면_카드로_보기() -> None:
    k = _tablet_text("kanban")
    assert f"min-height: {TAP}" in _rule(k, "body.erp-mobile-v2-layout .tablet-prod-board .erp-pro-alert[data-tablet-prod-kpi]")
    assert GAP in _rule(k, "body.erp-mobile-v2-layout .tablet-prod-board .erp-pro-alerts")
    assert f".fph-pane__cards {{ min-height: {TAP}; }}" in _tablet_text("home")


def test_대시보드_AS_완료_도면_이력_서명_옆_시트() -> None:
    assert f"min-height: {TAP}" in _rule(_tablet_text("grid"), ".erp-col-sort")
    land = _tablet_text("landscape")
    lab = _rule(land, "body.erp-mobile-v2-layout .erp-dashboard-filters .form-check-label")
    assert f"min-height: {TAP}" in lab and "margin-left: calc(-24px - .25rem)" in lab and "padding-left: calc(24px + .25rem)" in lab
    assert GAP in _rule(land, "body.erp-mobile-v2-layout .erp-dashboard-filters .form-check:last-child .form-check-label")
    # 이력 [검색]: history-tablet.css 의 'min-height: 0'(같은 특이도) 뒤에 있어야 이긴다
    hist = _tablet_text("history")
    assert hist.rindex(f"min-height: {TAP}") > hist.rindex("min-height: 0;")
    assert "display: inline-flex" in _rule(land, ".foms-tablet-sheet__retry")
    a = _tablet_text("as")
    idx = _rule(a, "body.erp-mobile-v2-layout .erp-as-dashboard a.foms-as-compare-card__id::after")
    assert f"height: {TAP}" in idx and "content: ''" in idx
    assert f"min-height: {TAP}" in _rule(a, "body.erp-mobile-v2-layout .erp-as-dashboard .foms-as-compare-visit__link")
    assert f"min-height: {TAP}" in _rule(a, "body.erp-mobile-v2-layout .erp-as-dashboard .foms-as-compare-search__input")
    hint = _rule(_tablet_text("as_card"), ".as-timeline-hint__dismiss::after")
    assert f"width: {TAP}" in hint and f"height: {TAP}" in hint
    assert f"min-height: {TAP}" in _rule(_tablet_text("completion"), "body.erp-mobile-v2-layout .foms-completion-grid__check")
    assert f"min-height: {TAP}" in _rule(_tablet_text("drawing"), "body.erp-mobile-v2-layout .foms-drawing-workshop__check")
    g = _tablet_text("cgate")
    assert GAP in _rule(g, ".foms-cgate-sign__actions") and f"min-height: {TAP}" in _rule(g, ".foms-cgate-sign__actions .foms-btn")


def test_새_px_글자_크기는_더하지_않았다() -> None:
    """누름 칸만 키운다 — 글자 크기는 손대지 않는다(새 font-size px 는 calc(Npx * var(--foms-fs, 1)) 규칙)."""
    for key in FILES:
        t = _tablet_text(key)
        for body in re.findall(r"\{([^{}]*" + re.escape("var(--foms-ui-zoom, 1)") + r"[^{}]*)\}", t):
            assert "font-size" not in body, (key, body)
