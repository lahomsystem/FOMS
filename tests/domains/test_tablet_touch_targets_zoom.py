"""가로 터치 태블릿 누름 칸 — 화면 크기 80 · 90 · 100% 모두 보이는 44px (2026-11-22 터치 점검).

화면 크기(html zoom = --foms-ui-zoom)는 손잡이 · 단추까지 같이 줄여, 44px 칸이 80% 에서 35px, 30px 칸은 24px 로 보였다.
고친 칸은 크기를 '44px ÷ 배율'(calc(44px / var(--foms-ui-zoom, 1)))로 잡는다. 이 규칙은 가로 터치 태블릿
(@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)) 안에만 있어야 한다 — PC(마우스)는
사장님이 80% 로 쓰는데 글자 · 단추가 바뀌면 안 되고, 폰(<992px)도 그대로다.
실화면 측정(1176×626 터치 · 80/90/100% · 글자 150%, PC 1440×900 · 폰 390×844 전후 대조)은 스크래치패드 touch_fix/targets.
2차(같은 날): 80% 에서 보이는 35 ~ 43px 이던 칸(줄 높이 40 · 48 · 56, 위 줄 단추, 검색 칸 · 고르기, AS 세 칸, 날짜 띠 등)도
같은 방법으로 44px. 100% 에서 원래 44px 넘던 칸(48 · 50 · 52px)은 max() 로 지켜 100% 화면은 그대로이고, 이웃 칸 사이를
넓히는 규칙은 화면 크기 100% 미만(html[data-foms-ui-zoom^="0."])에서만 켠다. 실측은 스크래치패드 touch_fix/targets2.
3차(2026-11-23): 준비물에 쪽 넘김 · 기준 일정 바뀜 칩이 없어 놓친 것 — 대시보드 · 이력 쪽 넘김, 완료 [이전] · [다음],
AS 쪽 넘김, AS 배너 바로 가기 칩(알약은 그대로, 투명 누름 칸 ::after 만 44px). 원래 칸 사이가 100% 에서도 8px 미만이라
100% 는 8px, 100% 미만은 '8px ÷ 배율'. 실측은 스크래치패드 touch_fix/targets3.
4차(2026-11-23): 실데이터에만 뜨는 것 — 출고 시공일 변경 배너 칩(투명 누름 칸 ::after) · 고객 칸 [확인](칸 자체를 키움) ·
위 줄 [협력사 희망 N], 실측 화면 네이버 발송처리 띠 머리 · 작은 단추. 띠 안 주문 링크는 줄 간격(보이는 17px)이 좁아
44px 누름 칸이 이웃과 겹치므로 손대지 않았다. 실측은 스크래치패드 touch_fix/targets4.
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
    # 2차(2026-11-22) — 80% 에서 보이는 35 ~ 43px 이던 칸
    "measure": "static/css/foundation/foms-tablet-measurement.css",
    "cwork": "static/css/foundation/foms-tablet-construction.css",
    "side_sheet": "static/css/components/foms-tablet-side-sheet.css",
    "strip": "static/css/components/foms-tablet-day-strip.css",
    "day_sheet": "static/css/contexts/shipment/tablet-day-sheet.css",
    "ship_cols": "static/css/contexts/shipment/shipment-dashboard-columns.css",
    # 4차(2026-11-23) — 출고 시공일 변경 배너 칩
    "ship_extras": "static/css/contexts/shipment/dashboard-table-extras.css",
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


# ── 2차 ────────────────────────────────────────────────────────────────────────────────────
ZOOM_LT_100 = 'html[data-foms-ui-zoom^="0."]'
ZOOM_LT_100_BODY = 'body.erp-mobile-v2-layout:is(html[data-foms-ui-zoom^="0."] > body)'


def _decl(text: str, selector: str) -> str:
    """선택자 목록(쉼표로 나눔)에 selector 가 그대로 들어 있는 규칙 몸통 — 모두 이어 붙인 것."""
    found = [m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text)
             if selector in [x.strip() for x in m.group(1).split(",")]]
    assert found, selector
    return "\n".join(found)


def test_2차_밀도_위_줄_거르기_옆_시트() -> None:
    land = _tablet_text("landscape")
    d = _decl(land, "body.erp-mobile-v2-layout .foms-density-toggle__btn")
    assert f"min-width: {TAP}" in d and f"min-height: {TAP}" in d
    assert GAP in _decl(land, f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-density-toggle")
    for sel in ("body.erp-mobile-v2-layout .foms-tdash-pcbar__btn", "body.erp-mobile-v2-layout .foms-tdash-pcbar__create",
                "body.erp-mobile-v2-layout .erp-dashboard-filters .form-control", "body.erp-mobile-v2-layout .erp-dashboard-filters .form-select",
                "body.erp-mobile-v2-layout #erp-filters-form .input-group .btn-primary",
                "body.erp-mobile-v2-layout #erp-filters-form .btn-outline-secondary", ".foms-tsheet-foot__btn"):
        assert f"min-height: {TAP}" in _decl(land, sel), sel
    add = _decl(land, ".foms-tsheet-attach-add")
    assert f"width: max(60px, {TAP})" in add and f"height: max(46px, {TAP})" in add


def test_2차_실측_원래_48_52_칸은_max_로_지킨다() -> None:
    m = _tablet_text("measure")
    pre = "body.erp-mobile-v2-layout .erp-measurement-dashboard "
    for sel in ("foms-tablet-measure-list__search-input", "foms-tablet-measure-list__foot .foms-btn", "foms-tmf-tab", "foms-tmf__chip",
                "foms-tmf__spec-add", "foms-tmf__uploadcat", "foms-tmf__acc-summary", "foms-tmf__check", "foms-tmf__convo-actions .foms-btn"):
        assert f"min-height: {TAP}" in _decl(m, pre + "." + sel), sel
    assert f"min-height: max(48px, {TAP})" in _decl(m, pre + ".foms-tmf__finput")
    assert f"min-height: max(var(--foms-touch-target-min, 32px), {TAP})" in _decl(m, pre + ".foms-tablet-measure-chip")
    for sel in ("foms-tmf__input", "foms-tablet-measure-context__btn", "foms-tablet-measure-actions__btn"):
        assert f"min-height: max(52px, {TAP})" in _decl(m, pre + "." + sel), sel
    assert f"height: max(52px, {TAP})" in _decl(m, pre + ".foms-tmf__num")


def test_2차_도면_카드_크기_세_칸은_100퍼센트_미만에서만_떼고_원_주문_링크는_투명_누름_칸() -> None:
    t = _tablet_text("drawing")
    size = _decl(t, "body.erp-mobile-v2-layout .foms-drawing-workshop__size")
    assert f"min-width: {TAP}" in size and f"min-height: {TAP}" in size
    sizes = _decl(t, f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-drawing-workshop__sizes")
    assert GAP in sizes and "overflow: visible" in sizes
    active = _decl(t, f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-drawing-workshop__size.is-active")
    assert "background: var(--foms-interactive-primary)" in active
    assert f"min-width: {TAP}" in _decl(t, "body.erp-mobile-v2-layout .foms-drawing-workshop__btn")
    for sel in ("foms-drawing-workshop__sort", "foms-drawing-workshop__search", "foms-drawing-sheet__btn"):
        assert f"min-height: {TAP}" in _decl(t, "body.erp-mobile-v2-layout ." + sel), sel
    link = _decl(t, "body.erp-mobile-v2-layout .foms-drawing-sheet__order-link::after")
    assert "content: ''" in link and f"height: {TAP}" in link and f"width: max(100%, {TAP})" in link


def test_2차_AS_시공_완료_옆_시트_이력() -> None:
    a = _tablet_text("as")
    for sel in ("foms-as-compare-subtab", "foms-as-compare-pcbar__cta", "foms-as-compare-btn"):
        assert f"min-height: {TAP}" in _decl(a, "body.erp-mobile-v2-layout .erp-as-dashboard ." + sel), sel
    assert GAP in _decl(a, f"{ZOOM_LT_100} body.erp-mobile-v2-layout .erp-as-dashboard .foms-as-compare-subtabs")
    c = _tablet_text("cons")
    for sel in ("foms-cons-first__btn", "foms-cons-pop__item", "foms-cons-pop__input", "foms-cons-pop__go", "foms-cwork-back__link"):
        assert f"min-height: {TAP}" in _decl(c, "body.erp-mobile-v2-layout ." + sel), sel
    assert GAP in _decl(c, f"{ZOOM_LT_100_BODY} .foms-cons-pop__menu")
    w = _tablet_text("cwork")
    floor44 = f"min-height: max(var(--foms-touch-target-comfortable), {TAP})"
    assert floor44 in _decl(w, "body.erp-mobile-v2-layout .foms-cwork-btn")
    assert floor44 in _decl(w, "body.erp-mobile-v2-layout .foms-cwork-memo")
    # 주 단추(48px)는 기본 단추 규칙 뒤에 있어 48px 바닥을 지킨다
    assert w.rindex("body.erp-mobile-v2-layout .foms-cwork-btn--primary") > w.rindex("body.erp-mobile-v2-layout .foms-cwork-btn,")
    assert f"min-height: max(var(--foms-touch-target-min), {TAP})" in _decl(w, "body.erp-mobile-v2-layout .foms-cwork-btn--primary")
    g = _tablet_text("completion")
    for sel in ("foms-completion-grid__excel", 'foms-completion-grid__filterbar input[type="search"]',
                "foms-completion-grid__filterbar select", "foms-completion-grid__apply", "foms-completion-grid__reset",
                "foms-completion-sheet__field .form-control:not(textarea)"):
        assert f"min-height: {TAP}" in _decl(g, "body.erp-mobile-v2-layout ." + sel), sel
    close = _decl(_tablet_text("side_sheet"), ".foms-tablet-sheet__close")
    assert f"width: {TAP}" in close and f"height: {TAP}" in close
    h = _tablet_text("history")
    assert f"min-height: {TAP}" in _decl(h, "body.erp-mobile-v2-layout .erp-history-mobile-shell .erp-pro-filters-form .form-control")


def test_2차_출고_시공_날짜_띠와_출고_위_줄() -> None:
    s = _tablet_text("strip")
    assert f"height: max(50px, {TAP})" in _decl(s, "body.erp-mobile-v2-layout .foms-ship-day")
    nav = _decl(s, "body.erp-mobile-v2-layout .foms-ship-days__nav")
    assert f"flex-basis: max(44px, {TAP})" in nav and f"height: max(50px, {TAP})" in nav
    track = _decl(s, f"{ZOOM_LT_100_BODY} .foms-ship-days__track")
    assert f"gap: {GAP}" in track and f"width: calc(var(--ship-day-w) * 7 + {GAP} * 6)" in track
    cols = _tablet_text("ship_cols")
    assert f"min-height: {TAP}" in _decl(cols, "body.erp-mobile-v2-layout .foms-ship-pcbar__btn")
    assert f"min-width: max(52px, {TAP})" in _decl(cols, "body.erp-mobile-v2-layout .foms-ship-more__go")
    assert f"min-height: max(48px, {TAP})" in _decl(cols, "body.erp-mobile-v2-layout .foms-ship-more__item")
    go = _decl(cols, "body.erp-mobile-v2-layout .foms-ship-pcbar__filter-go")
    assert f"width: {TAP}" in go and f"height: {TAP}" in go
    d = _tablet_text("day_sheet")
    assert f"min-height: {TAP}" in _decl(d, "body.erp-mobile-v2-layout .foms-tablet-shipgrid__addas")
    assert f"width: {TAP}" in _decl(d, "body.erp-mobile-v2-layout .foms-ship-names__close")
    # 표 줄 안 시공자 칸은 줄 높이에 묶여 있어 이번에 키우지 않았다(줄 높이 결정은 사장님 몫)
    assert "var(--foms-ui-zoom" not in _decl(d, "body.erp-mobile-v2-layout .foms-tablet-shipgrid__wbtn")


def test_2차_이웃_띄움_넓히기는_100퍼센트_미만에서만() -> None:
    """2차가 더한 '보이는 8px' 띄움은 모두 화면 크기 100% 미만 문지기 안 — 100% 화면은 전과 같다(1차 글자 손잡이 규칙은 뺀다)."""
    pairs = [("landscape", f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-tdash-pcbar__actions"),
             ("measure", f"{ZOOM_LT_100} body.erp-mobile-v2-layout .erp-measurement-dashboard .foms-tmf-tabs"),
             ("drawing", f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-drawing-workshop__tools"),
             ("as", f"{ZOOM_LT_100} body.erp-mobile-v2-layout .erp-as-dashboard .foms-as-compare-foot-secondary"),
             ("cwork", f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-cwork-links"),
             ("ship_cols", f"{ZOOM_LT_100} body.erp-mobile-v2-layout .foms-ship-pcbar__actions"),
             ("cons", f"{ZOOM_LT_100_BODY} .foms-cons-pop__row"),
             ("day_sheet", f"{ZOOM_LT_100_BODY} .foms-ship-names__foot")]
    for key, sel in pairs:
        assert f"gap: {GAP}" in _decl(_tablet_text(key), sel), (key, sel)
    filters = _decl(_tablet_text("landscape"), f"{ZOOM_LT_100} body.erp-mobile-v2-layout #erp-filters-form")
    assert f"gap: {GAP} !important" in filters
    for key in ("landscape", "drawing", "as", "cons", "strip", "measure", "cwork", "ship_cols", "day_sheet"):
        css = _strip_comments(_css(key))
        for m in re.finditer(r"([^{}]+)\{([^{}]*gap: calc\(8px / var\(--foms-ui-zoom, 1\)\)[^{}]*)\}", css):
            sel = " ".join(m.group(1).split())
            if "foms-fs" in sel:
                continue
            assert ZOOM_LT_100 in sel, (key, sel)


def test_2차_바뀐_파일_핀은_20261122w() -> None:
    bundle = (ROOT / "static/css/foundation/foms-tablet-bundle.css").read_text(encoding="utf-8")
    # 랜드스케이프 · 완료 · AS 대조 셋은 3차가, 실측은 4차가 다시 올렸다(아래 3 · 4차 핀 시험) — 나머지 셋은 2차 핀 그대로.
    for f in ("../components/foms-tablet-side-sheet.css",
              "foms-tablet-drawing-gallery.css", "foms-tablet-construction.css"):
        assert f'@import url("{f}?v=20261122w")' in bundle, f
    assert "foms-tablet-bundle.css') }}?v=20261123b" in (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    ship = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    cons = (ROOT / "templates/construction/partials/styles.html").read_text(encoding="utf-8")
    # 출고 열 · 하루치 출고표 시트는 4차가 다시 올렸다(아래 4차 핀 시험).
    assert "foms-tablet-day-strip.css') }}?v=20261122w" in ship
    assert "foms-tablet-day-strip.css') }}?v=20261122w" in cons and "tablet-first.css') }}?v=20261122w" in cons
    hist = (ROOT / "templates/orders/partials/history_dashboard_body.html").read_text(encoding="utf-8")
    assert "history-tablet.css') }}?v=20261122w" in hist


# ── 3차 ────────────────────────────────────────────────────────────────────────────────────
def test_3차_대시보드_이력_쪽_넘김_44_겹침_없이_칸_사이_8() -> None:
    land = _tablet_text("landscape")
    link = _decl(land, ".foms-tablet-workqueue-wrap .pagination .page-link")
    assert f"min-width: {TAP}" in link and f"min-height: {TAP}" in link and "margin-left: 0" in link
    assert "gap: 8px" in _decl(land, ".foms-tablet-workqueue-wrap .pagination")
    assert f"gap: {GAP}" in _decl(land, f"{ZOOM_LT_100} .foms-tablet-workqueue-wrap .pagination")
    # 태블릿 밖 바탕 규칙(44px 고정 · 4px 띄움)은 그대로 — 태블릿 규칙이 같은 선택자로 파일 뒤에서 이긴다
    css = _strip_comments(_css("landscape"))
    assert re.search(r"(?m)^\.foms-tablet-workqueue-wrap \.pagination \.page-link \{\s*min-width: var\(--foms-touch-target-comfortable, 44px\);", css)
    base = css.rindex("min-width: var(--foms-touch-target-comfortable, 44px)")
    assert base < css.rindex("margin-left: 0;"), "태블릿 쪽 넘김 규칙이 바탕 규칙보다 뒤에 있어야 이긴다"


def test_3차_완료_이전_다음_44() -> None:
    link = _decl(_tablet_text("completion"), "body.erp-mobile-v2-layout .foms-completion-grid__page-link")
    assert f"min-width: {TAP}" in link and f"min-height: {TAP}" in link


def test_3차_AS_바로_가기_칩은_투명_누름_칸만_44_알약은_그대로() -> None:
    a = _tablet_text("as")
    pre = "body.erp-mobile-v2-layout .erp-as-dashboard "
    hit = _decl(a, pre + "a.as-drift-chip::after")
    assert "content: ''" in hit and "position: absolute" in hit and f"height: {TAP}" in hit
    assert "left: 0" in hit and "right: 0" in hit and "translateY(-50%)" in hit
    assert "position: relative" in _decl(a, pre + "a.as-drift-chip")
    # 칩 자체(알약) 높이 · 안쪽 여백은 건드리지 않는다 — 배너가 커져 목록이 밀리지 않게
    bodies = re.findall(r"a\.as-drift-chip\s*\{([^}]*)\}", a)
    assert bodies
    for body in bodies:
        assert "height" not in body and "padding" not in body, body
    chips = _decl(a, pre + ".as-schedule-drift-banner__chips")
    assert "column-gap: 8px" in chips and "row-gap: calc(52px / var(--foms-ui-zoom, 1) - 24px)" in chips
    assert f"column-gap: {GAP}" in _decl(a, f"{ZOOM_LT_100} {pre}.as-schedule-drift-banner__chips")
    # 칩 갈래(ref_moved · both_moved …)는 모두 공통 클래스 as-drift-chip 을 단다 — 갈래별 규칙이 없어도 다 덮인다
    macro = (ROOT / "templates/cs/partials/as_card_macros.html").read_text(encoding="utf-8")
    assert '<a class="as-drift-chip as-drift-chip--{{ chip.state }}' in macro


def test_3차_AS_쪽_넘김_44_낱개_알약_칸_사이_8() -> None:
    a = _tablet_text("as")
    pre = "body.erp-mobile-v2-layout .erp-as-dashboard "
    link = _decl(a, pre + ".pagination .page-link")
    assert f"min-width: {TAP}" in link and f"min-height: {TAP}" in link and "margin-left: 0" in link
    assert "border-radius: var(--bs-pagination-border-radius)" in link
    assert "gap: 8px" in _decl(a, pre + ".pagination")
    assert f"gap: {GAP}" in _decl(a, f"{ZOOM_LT_100} {pre}.pagination")


def test_3차_바뀐_파일_핀은_20261123a() -> None:
    bundle = (ROOT / "static/css/foundation/foms-tablet-bundle.css").read_text(encoding="utf-8")
    for f in ("foms-tablet-landscape.css", "foms-tablet-completion-grid.css", "foms-tablet-as-compare.css"):
        assert f'@import url("{f}?v=20261123a")' in bundle, f
    assert "foms-tablet-bundle.css') }}?v=20261123b" in (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")


# ── 4차 ────────────────────────────────────────────────────────────────────────────────────
def test_4차_출고_시공일_변경_칩은_투명_누름_칸만_44_알약은_그대로() -> None:
    t = _tablet_text("ship_extras")
    hit = _decl(t, "body.erp-mobile-v2-layout a.erp-ship-change-chip--tablet::after")
    assert "content: ''" in hit and "position: absolute" in hit and f"height: {TAP}" in hit
    assert "left: 0" in hit and "right: 0" in hit and "translateY(-50%)" in hit
    assert "position: relative" in _decl(t, "body.erp-mobile-v2-layout a.erp-ship-change-chip--tablet")
    # 알약 자체(높이 · 여백)는 건드리지 않는다 — 배너가 커져 표가 밀리지 않게
    for body in re.findall(r"erp-ship-change-chip--tablet\s*\{([^}]*)\}", t):
        assert "height" not in body and "padding" not in body, body
    chips = _decl(t, "body.erp-mobile-v2-layout .erp-ship-change-banner__chips")
    assert "column-gap: 8px" in chips and "row-gap: calc(52px / var(--foms-ui-zoom, 1) - 27px)" in chips
    assert f"column-gap: {GAP}" in _decl(t, f"{ZOOM_LT_100} body.erp-mobile-v2-layout .erp-ship-change-banner__chips")
    # 태블릿에서 보이는 칩은 --tablet 갈래(PC 칩은 같은 블록에서 숨김) — 매크로가 두 갈래를 낸다
    macro = (ROOT / "templates/shipment/partials/shipment_change_macros.html").read_text(encoding="utf-8")
    assert "'erp-ship-change-chip--tablet'" in macro
    assert "display: none" in _decl(t, "body.erp-mobile-v2-layout .erp-ship-change-chip--pc")


def test_4차_출고_확인_단추와_협력사_희망_알약은_칸_자체를_키운다() -> None:
    ack = _decl(_tablet_text("day_sheet"), "body.erp-mobile-v2-layout .foms-tablet-shipgrid__customer .erp-ship-change__ack")
    assert f"min-width: {TAP}" in ack and f"min-height: {TAP}" in ack and "display: inline-flex" in ack
    assert "margin-bottom: calc(4px / var(--foms-ui-zoom, 1))" in ack  # 마지막 줄 아래 [＋ 날짜 없는 AS] 와 보이는 8px 이상
    # 고객 칸은 overflow: hidden — 투명 누름 칸은 잘리므로 쓰지 않는다
    assert "overflow: hidden" in _decl(_tablet_text("day_sheet"), "body.erp-mobile-v2-layout .foms-tablet-shipgrid__row > td")
    prb = _decl(_tablet_text("ship_cols"), "body.erp-mobile-v2-layout .foms-ship-pcbar__prb")
    assert f"min-height: max(var(--foms-touch-target-comfortable, 44px), {TAP})" in prb


def test_4차_실측_네이버_발송처리_띠_머리와_작은_단추() -> None:
    m = _tablet_text("measure")
    pre = "body.erp-mobile-v2-layout .erp-measurement-dashboard .erp-naver-dispatch"
    assert f"min-height: {TAP}" in _decl(m, pre + " > summary")
    btn = _decl(m, pre + " .btn-sm")
    assert f"min-height: {TAP}" in btn and "display: inline-flex" in btn and "align-items: center" in btn
    # 띠 마크업(실측 화면 · 태블릿에서도 보이는 데스크톱 래퍼 안)이 그 클래스를 그대로 쓴다
    strip = (ROOT / "templates/measurement/partials/naver_dispatch_strip.html").read_text(encoding="utf-8")
    assert '<details class="alert' in strip and "erp-naver-dispatch" in strip and '<summary class="fw-semibold">' in strip
    assert 'class="btn btn-sm btn-primary"' in strip and 'class="btn btn-sm btn-outline-danger mt-1"' in strip
    # 띠 안 주문 링크(li > a)는 줄 간격이 좁아 이번에 키우지 않았다 — 실수로 넓히는 규칙이 생기면 보고와 어긋난다
    assert "erp-naver-dispatch li" not in m


def test_4차_바뀐_파일_핀은_20261123b() -> None:
    bundle = (ROOT / "static/css/foundation/foms-tablet-bundle.css").read_text(encoding="utf-8")
    assert '@import url("foms-tablet-measurement.css?v=20261123b")' in bundle
    assert "foms-tablet-bundle.css') }}?v=20261123b" in (ROOT / "templates/partials/shared/layout_head.html").read_text(encoding="utf-8")
    ship = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    for f in ("shipment-dashboard-columns.css", "tablet-day-sheet.css"):
        assert f + "') }}?v=20261123b" in ship, f
    # dashboard-table-extras.css 는 같은 날 PC 카드 모양(칸 세로 선을 인라인에서 옮김)으로 한 번 더 올랐다.
    assert "dashboard-table-extras.css') }}?v=20261123c" in ship
