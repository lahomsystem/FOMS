"""생산 태블릿 화면 비평 '바로 맞출 것'(갈래 나) + 꾸밈 결함 셋(C04 · C05 · C08) 고침 — CSS · 글 계약(2026-11-26).

화면 꼴은 그대로, 색 값 · 규칙 · 글 한 줄만 맞춘 것을 못 박는다. 실화면 전 · 후(1176×626 글자 100 · 110 · 120 · 150%, 800×1280 밝게 ·
어둡게, PC 1440×900 80%)는 스크래치패드 crit/fix_b 의 before_ · after_ 그림과 m/*.json.
- C12 읽기 기준: 흐린 글 · 빨강 글 4.5 이상, 보조 단추 · 빈 공정 칸 테두리 3 이상(실제 계산), 탭 숫자 · 줄 흐림(opacity) 없음.
- C13 누름 칸: 세로 태블릿 글자 손잡이 44px, 작업 시트 종 폭이 안 줄어듦. C05 어두운 설정에서도 제목 글 색. C15 [도면 수정 요청] 낮춤.
- C16 같은 상태 한 색: 보류 = 도면 칸 보류, 기다림 = 연두(무채색 금지), 주말 빨강 없음. C04 · C34 · C33 글자 배율 · 이름 줄.
- C08 누른 뒤 알림 줄은 터치 화면 아래 붙박이(PC · '내 공정' 판 밖). C35 안 쓰는 규칙 · 정의 안 된 색 · vh · 틀 인라인 style.
- 글: 금지어 '카드' 0(C17) · 띄어쓰기 · 겹말(C21) · 남의 공장 칩 겹말(C29).
"""
from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path

from tests.domains.test_production_selfclaim_css import _block, _css, _rule, _tokens
from tests.support.color_contrast import contrast_ratio, hex_rgb, pair_distances

ROOT = Path(__file__).resolve().parents[2]
TABLET = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def _code(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


# ── C12 읽기 기준 ─────────────────────────────────────────────────────────────

def test_흐린_글_빨강_글은_모든_바탕에서_4_5_테두리는_3_이상() -> None:
    tok = _tokens("home.css", "parts.css", "pc.css", "sheet.css")
    assert (tok["--fph-text3"], tok["--fph-danger"], tok["--fph-line2"], tok["--fph-warn-50"]) == ("#626a76", "#b91c1c", "#7f8794", "#fffbeb")
    # 작업 시트 · PC 도 같은 값(화면마다 회색 · 빨강이 다르지 않게) — PC 빨강 글은 이미 따로(--fpc-danger-ink = 같은 #b91c1c)
    assert (tok["--fpp-text3"], tok["--fpp-danger"], tok["--fpp-line2"]) == ("#626a76", "#b91c1c", "#7f8794")
    assert (tok["--fpc-text3"], tok["--fpc-line2"], tok["--fpc-danger-ink"]) == ("#626a76", "#7f8794", "#b91c1c")
    backs = ["--fph-surface", "--fph-bg", "--fph-raised", "--fph-brand-50", "--fph-danger-50", "--fph-warn-50"]
    for fg in ("--fph-text3", "--fph-danger"):
        for bg in backs:
            assert contrast_ratio(hex_rgb(tok[fg]), hex_rgb(tok[bg])) >= 4.5, (fg, bg)
    # 기다림 칸(연두) 위 빨강 '담당 없음' · 까닭 글
    for fg in ("--fph-danger", "--fph-why", "--fph-text2", "--fph-wait-700"):
        assert contrast_ratio(hex_rgb(tok[fg]), hex_rgb(tok["--fph-wait-50"])) >= 4.5, fg
    # 빨강 바탕 흰 글(바뀐 것 수 · 위 줄 종 배지)
    assert contrast_ratio((255, 255, 255), hex_rgb(tok["--fph-danger"])) >= 4.5
    # 그림 요소(보조 단추 · 빈 공정 칸 테두리)는 흰 · 회색 · 연남색 바탕에서 3 이상 — 옛 #c1c7d0 은 흰 바탕 1.70
    for bg in ("--fph-surface", "--fph-bg", "--fph-raised", "--fph-brand-50"):
        assert contrast_ratio(hex_rgb(tok["--fph-line2"]), hex_rgb(tok[bg])) >= 3, bg
    for name in ("home.css", "sheet.css", "pc.css"):
        tokens_block = _code(_css(name)).split("}", 1)[0]
        assert "#6b7380" not in tokens_block and "#c1c7d0" not in tokens_block and "#dc2626;" not in tokens_block.replace("--fpc-danger: #dc2626;", ""), name


def test_탭_숫자_줄_흐림은_없고_흰_글_대비는_4_5() -> None:
    home = _css("home.css")
    assert "opacity" not in _rule(home, ".foms-prod-home__tab small")
    tablet = _block(home, TABLET)
    navnum = _rule(tablet, ".foms-prod-home__navtab.is-on small")
    assert "opacity" not in navnum and "color: inherit" in navnum
    tok = _tokens("home.css")
    assert contrast_ratio((255, 255, 255), hex_rgb(tok["--fph-brand"])) >= 4.5  # 고른 탭(남색 칠) 위 흰 숫자
    # 보류 · 도면 고치는 중 줄: 통째 흐림(.7 — 글 2.73 ~ 3.67) 대신 바탕색, 줄 안 글은 그 바탕에서 4.5 이상
    dim = _rule(home, ".fph-qr.is-hold")
    assert "opacity" not in dim and "background: var(--fph-warn-50)" in dim
    assert ".fph-qr.is-hold, .fph-qr.is-revise {" in home
    for fg in ("--fph-text3", "--fph-text2", "--fph-brand-dark", "--fph-text", "--fph-danger"):
        assert contrast_ratio(hex_rgb(tok[fg]), hex_rgb(tok["--fph-warn-50"])) >= 4.5, fg
    # 정의 안 된 색 이름(--fph-warn-50 은 fallback 으로만 쓰였다)이 이제 토큰 — fallback 꼴은 남지 않는다
    assert "var(--fph-warn-50, " not in home


# ── C13 누름 칸 · C05 제목 · C15 [도면 수정 요청] ─────────────────────────────────

def test_세로_태블릿_글자_손잡이_44_시트_종_폭_고정() -> None:
    home = _css("home.css")
    portrait = _block(home, "@media (min-width: 600px) and (max-width: 991.98px) and (pointer: coarse)")
    assert "height: 44px" in _rule(portrait, ".foms-prod-home .foms-fs__btn")
    assert "width: 44px" in _rule(portrait, ".foms-prod-home .foms-fs__btn")
    assert "min-width: 60px" in _rule(portrait, ".foms-prod-home .foms-fs__now")
    assert "gap: 8px" in _rule(portrait, ".foms-prod-home .foms-fs")
    # '÷ 배율' 규칙은 가로 태블릿 덩이 밖으로 새지 않는다(test_tablet_touch_targets_zoom.py) — 세로 덩이는 고정 44px
    assert "--foms-ui-zoom" not in portrait
    assert "flex-shrink: 0" in _rule(_css("sheet.css"), ".foms-prod-page__btn.foms-prod-page__bell")


def test_어두운_설정에서도_제목_글_색() -> None:
    assert "color: var(--fph-text)" in _rule(_css("home.css"), ".foms-prod-home__title")
    assert "color: var(--fpp-text)" in _rule(_css("sheet.css"), ".foms-prod-page__title")


def test_도면_수정_요청은_보조_단추_꼴_할_일_단추와_틈() -> None:
    parts = _css("parts.css")
    req = _rule(parts, ".pp-card .pp-req")
    assert "var(--fph-brand" not in req and "color: var(--fph-text2)" in req and "font-weight: 700" in req
    tablet = _block(parts, TABLET)
    assert "margin-bottom: max(5px, calc(12px / var(--foms-ui-zoom, 1) - 7px))" in _rule(tablet, ".pp-card .pp-req")


# ── C16 같은 상태 한 색 ───────────────────────────────────────────────────────

def test_보류는_화면마다_도면_칸_보류_색() -> None:
    home, parts, sheet = _css("home.css"), _css("parts.css"), _css("sheet.css")
    # 토큰은 첫 화면 파일 하나(도면 판 파일은 판이 있을 때만 실린다 — '내 공정' 은 판이 없다)
    for k, v in (("--fph-hold-50", "#fed7aa"), ("--fph-hold-300", "#fb923c"), ("--fph-hold-700", "#9a3412")):
        assert f"{k}: {v};" in home and f"{k}:" not in _code(parts), k
    for k, v in (("--fpp-hold-50", "#fed7aa"), ("--fpp-hold-300", "#fb923c"), ("--fpp-hold-700", "#9a3412")):
        assert f"{k}: {v};" in sheet, k
    for sel in (".fph-qr__hold", ".fph-qr__holdtag"):
        body = _rule(home, sel)
        assert "background: var(--fph-hold-50)" in body and "color: var(--fph-hold-700)" in body, sel
    for sel in (".fph-sp__hold", ".fph-sp__act.is-on"):
        body = _rule(home, sel)
        assert "var(--fph-hold-300)" in body and "var(--fph-hold-50)" in body and "var(--fph-hold-700)" in body, sel
    badge = _rule(sheet, ".foms-prod-page__badge--hold")
    assert "background: var(--fpp-hold-50)" in badge and "color: var(--fpp-hold-700)" in badge
    assert "var(--fpp-hold-50)" in _rule(sheet, ".foms-prod-page__btn.is-active")
    tok = _tokens("home.css", "sheet.css")
    assert contrast_ratio(hex_rgb(tok["--fph-hold-700"]), hex_rgb(tok["--fph-hold-50"])) >= 4.5  # 옛 흰 글 주황 배지 3.19
    assert contrast_ratio(hex_rgb(tok["--fpp-hold-700"]), hex_rgb(tok["--fpp-hold-50"])) >= 4.5


def test_끝_자리_막힘_둘은_보류_색을_안_쓴다() -> None:
    """'내 공정' [끝] 자리 막힘(비평 갈래 가 C02 · C03) — 도면 칸을 쓴 주문(is-cards)은 도면 판 '엣지 · 조립 미완료' 노랑,
    장이 모두 남의 공장(is-elsewhere)은 도면 판 남의 공장 칸(흰 바탕 · 회색 테두리) · 줄은 공장 색 점선. 보류 색은 보류 · 도면 고치는 중에만."""
    home, pc = _css("home.css"), _css("pc.css")
    tok = _tokens("home.css", "pc.css")
    for k, v in (("--fph-pre-50", "#fef08a"), ("--fph-pre-300", "#eab308"), ("--fph-pre-700", "#713f12")):
        assert f"{k}: {v};" in home and f"{k}:" not in _code(_css("parts.css")), k  # 판 없는 '내 공정' 도 싣는 첫 화면 파일로
        assert tok[k.replace("fph", "fpc")] == v, k  # PC 는 자기 접두사 같은 값
    blocks = {sel: _rule(home, sel) for sel in (".fph-qr__hold.is-cards", ".fph-qr__holdtag.is-cards", ".fph-qr__hold.is-elsewhere",
                                                ".fph-qr__holdtag.is-elsewhere", ".fph-sp__hold.is-cards", ".fph-sp__hold.is-elsewhere")}
    blocks.update({sel: _rule(pc, sel) for sel in (".fpc-hold.is-cards", ".fpc-hold.is-elsewhere")})
    for sel, body in blocks.items():
        assert "hold" not in body, sel  # --fph-hold-* · --fpc-hold* 를 덮어 쓴다(보류 색이 남지 않음)
        assert "background" in body or sel.startswith(".fpc-hold.is-elsewhere"), sel  # PC 남의 공장은 원래 흰 바탕 그대로
    for sel in (".fph-qr__hold.is-cards", ".fph-sp__hold.is-cards", ".fpc-hold.is-cards"):
        assert "pre-50)" in blocks[sel] and "pre-700)" in blocks[sel] and "text-decoration: none" in blocks[sel], sel  # 링크 밑줄 없음
        assert "outline: 3px solid" in _rule(home if sel.startswith(".fph") else pc, sel + ":focus-visible"), sel
    assert "min-height: 44px" in blocks[".fph-qr__hold.is-cards"]  # 세로 · 폰 줄 끝 누름 칸(전 40px)
    for sel in (".fph-qr__hold.is-elsewhere", ".fph-sp__hold.is-elsewhere"):
        assert "var(--fph-surface)" in blocks[sel] and "var(--fph-line2)" in blocks[sel], sel
    assert "border: 2px dashed" in _rule(home, ".fph-qr.is-elsewhere")
    assert "var(--foms-fac2-line)" in _rule(home, ".fph-qr.is-elsewhere:has(.foms-fac--2)")
    assert "var(--fph-danger)" in _rule(home, ".fph-qr.is-elsewhere.is-chg")
    # 글 대비 — 노랑 칸 · 흰 칸 위 글 4.5 이상
    assert contrast_ratio(hex_rgb(tok["--fph-pre-700"]), hex_rgb(tok["--fph-pre-50"])) >= 4.5
    assert contrast_ratio(hex_rgb(tok["--fph-text"]), hex_rgb(tok["--fph-surface"])) >= 4.5
    # 템플릿은 class 이름만 — 꼴 이름은 step_block.kind 그대로(도면 칸 = cards)
    steps = _read("templates/production/partials/home_steps.html")
    panel = _read("templates/production/partials/home_step_panel.html")
    macros = _read("templates/production/partials/home_pc_macros.html")
    assert '<a class="fph-qr__hold is-cards"' in steps and '<span class="fph-qr__hold is-{{ r.step_block.kind }}"' in steps
    assert '<span class="fph-qr__holdtag is-{{ r.step_block.kind }}">' in steps
    assert '<a class="fph-sp__hold is-cards"' in panel and '<div class="fph-sp__hold is-{{ p.step_block.kind }}">' in panel
    assert '<a class="fpc-hold is-cards"' in macros and '<span class="fpc-hold is-{{ r.step_block.kind }}"' in macros


def test_기다림은_연두_주말은_빨강_아님_받은함_파랑_하나() -> None:
    home = _css("home.css")
    wait = _rule(home, ".fph-wi.has-why")
    for prop in ("background: var(--fph-wait-50)", "border-color: var(--fph-wait-300)", "color: var(--fph-wait-700)"):
        assert prop in wait, prop
    assert "color: var(--fph-wait-700)" in _rule(home, ".fph-wi.has-why > small")
    assert "fill: var(--fph-wait-300)" in _rule(home, ".fph-sd__bar rect.is-x")
    # 띠 막대 조각 넷(완료 · 만드는 중 · 제작 대기 · 기다림)은 짝마다 정상 10 · 색약 6 이상, 기다림도 무채색이 아니다
    tok = _tokens("home.css")
    seg = {"f": tok["--fph-ok"], "p": tok["--fph-brand"], "w": "#f59e0b", "x": tok["--fph-wait-300"]}
    assert "fill: #f59e0b" in _rule(home, ".fph-sd__bar rect.is-w")
    for a, b in combinations(seg, 2):
        normal, deu, pro = pair_distances(hex_rgb(seg[a]), hex_rgb(seg[b]))
        assert normal >= 10 and deu >= 6 and pro >= 6, (a, b, round(normal, 1), round(deu, 1), round(pro, 1))
    # 주말: 빨강('늦음 · 바뀜' 빨강과 같았다) 대신 굵은 요일 글
    code = _code(home)
    assert ".fph-sd.is-wk .fph-sd__d b" not in code
    assert "font-weight: 800" in _rule(home, ".fph-sd.is-wk .fph-sd__d small")
    assert "#2563eb" not in code and "color: var(--fph-brand-dark)" in _rule(home, ".fph-al__list li.is-drawing")


# ── C04 · C34 · C33 글자 배율 · 이름 줄 ─────────────────────────────────────────

def test_글자를_키운_판은_도면_둘씩_넓은_판은_이름_줄_한_줄() -> None:
    parts = _css("parts.css")
    wide = _block(parts, "@media (min-width: 992px)")
    two = _block(wide, "@container fph-pane (max-width: calc(38rem - 0.02px))")
    assert ".pp-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in two
    one = _block(wide, "@container fph-pane (min-width: 30rem)")
    assert ".pp-card .pp-ln { flex-wrap: nowrap; }" in one
    # 작업 필요 칸(그림 왼쪽 큰 도면)은 늘 한 줄 — 더 센 선택자(0,2,0)가 컨테이너 규칙(0,1,0)을 이긴다
    assert ".pp-grid.is-need { grid-template-columns: minmax(0, 1fr); }" in parts
    # 1176×626 실측 판 칸 너비(rem): 100% 46 · 110% 39.9 → 셋, 120% 34.8 · 150% 24.6 → 둘. 이름 줄은 130%(30.5) 까지 한 줄
    for wrem, cols in ((46, 3), (39.9, 3), (34.8, 2), (30.5, 2), (24.6, 2)):
        assert (2 if wrem < 38 else 3) == cols, wrem
    # 넓은 판의 nowrap 은 지금 꺾임 규칙(11-21) 뒤라 같은 특이도에서 이긴다
    assert parts.index(".pp-card .pp-ln { flex-wrap: wrap; row-gap: 0; }") < parts.index(".pp-card .pp-ln { flex-wrap: nowrap; }")
    dlg = _rule(parts, ".foms-prod-home .pp-modal.pp-rq .foms-prod-change-modal__dialog")
    assert "calc(640px * var(--foms-fs, 1))" in dlg and "calc(100vw / var(--foms-ui-zoom, 1) - 32px)" in dlg


def test_날짜_장_긴_이름은_두_줄까지() -> None:
    home = _css("home.css")
    nm = _rule(home, ".fph-dr .fph-dr__nm > b")
    assert "-webkit-line-clamp: 2" in nm and "white-space: normal" in nm and "word-break: keep-all" in nm
    assert "flex-wrap: wrap" in _rule(home, ".fph-dr .fph-dr__nm")
    # 도면 카드 이름 줄(.pp-card .fph-dr__nm)은 이 규칙 밖 — 선택자가 날짜 장 줄(.fph-dr)로 묶여 있다
    assert not re.search(r"(?m)^\.fph-dr__nm > b \{[^}]*line-clamp", home)


# ── C08 알림 줄 ──────────────────────────────────────────────────────────────

def test_누른_뒤_알림_줄은_터치_화면_아래_붙박이() -> None:
    home = _css("home.css")
    touch = _block(home, "@media (pointer: coarse)")
    fixed = _rule(touch, ".foms-prod-home:not(.fph-has-sp) > .foms-prod-home__status:not(:empty)")
    for prop in ("position: fixed", "bottom: calc(16px + var(--foms-safe-area-bottom, 0px))", "z-index: 1068", "margin: 0 auto"):
        assert prop in fixed, prop
    assert "background: var(--fph-surface)" in _rule(touch, ".foms-prod-home:not(.fph-has-sp) > .foms-prod-home__status:not(:empty):not(.is-undo)")
    assert "padding-bottom: 72px" in _rule(touch, ".foms-prod-home:not(.fph-has-sp):has(> .foms-prod-home__status:not(:empty))")
    narrow = _block(home, "@media (max-width: 991.98px) and (pointer: coarse)")
    assert "var(--foms-shell-bottom-nav-h, 72px)" in _rule(narrow, ".foms-prod-home:not(.fph-has-sp) > .foms-prod-home__status:not(:empty)")
    # 터치 덩이 밖(PC 마우스)에는 붙박이 규칙이 없다 — 덩이를 빼면 position: fixed 가 남지 않는다
    outside = home.replace(touch, "")
    assert ".foms-prod-home__status:not(:empty) { position: fixed" not in outside
    # '내 공정' 판 [되돌리기] 띠(왼쪽 목록 바닥)는 그대로
    assert "body.erp-mobile-v2-layout .fph-has-sp > .foms-prod-home__status.is-undo { position: absolute;" in home


# ── C35 치우기 ───────────────────────────────────────────────────────────────

def test_안_쓰는_규칙_화면_높이_틀_인라인_style() -> None:
    home, parts, sheet = _code(_css("home.css")), _code(_css("parts.css")), _code(_css("sheet.css"))
    for sel in (".foms-prod-home__sp ", ".foms-prod-home__btn--ghost", ".fph-pane__g--next"):
        assert sel not in home, sel
    assert ".pp-tag.is-defect" not in parts
    # 화면 높이 vh 는 '100dvh ÷ 화면 크기 배율' 꼴만
    for name, code in (("home.css", home), ("sheet.css", sheet)):
        assert not re.search(r"(?<![d\w])\d+vh\b", code), name
    assert "min-height: calc(60dvh / var(--foms-ui-zoom, 1))" in home
    assert "max-height: calc(44dvh / var(--foms-ui-zoom, 1))" in sheet
    layout = _read("templates/production/layout.html")
    assert 'style="' not in layout and "data-foms-layout-frame" in layout and "foms-layout-frame" in layout
    assert 'class="{% if erp_mobile_v2_enabled and request.path.startswith(\'/erp\') %}erp-mobile-v2-layout{% endif %}"' in layout
    pro = _read("static/css/foundation/erp-pro.css")
    frame = _rule(pro, "body[data-foms-layout-frame]")
    for prop in ("width: 100% !important", "max-width: 100% !important", "margin: 0 !important", "padding: 0 !important"):
        assert prop in frame, prop
    assert "padding-left: 0 !important" in _rule(pro, "body[data-foms-layout-frame] .container-fluid.foms-layout-frame")
    head = _read("templates/partials/shared/layout_head.html")
    pin = head.split("erp-pro.css') }}?v=", 1)[1].split('"', 1)[0]
    assert pin == "20261121q"  # 틀 규칙을 더하며 올림 — 부르는 곳(공용 머리 · 협력사 틀) 모두 같은 값
    assert f"erp-pro.css') }}}}?v={pin}" in _read("templates/partner/layout.html")


# ── 글: C17 · C21 · C29 ─────────────────────────────────────────────────────

def _visible_template_text(src: str) -> str:
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)(?<![:'\"])//.*$", "", src)


def test_화면_글에_카드가_없다() -> None:
    """금지어 '카드'(사람이 보는 낱말은 '도면') — 생산 템플릿 · 생산 JS 문자열 · 파트 계정 거절 글."""
    hits = []
    for p in sorted((ROOT / "templates/production").rglob("*.html")):
        if "카드" in _visible_template_text(p.read_text(encoding="utf-8")):
            hits.append(str(p.relative_to(ROOT)))
    for p in sorted((ROOT / "static/js/production").glob("*.js")):
        code = re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)
        code = re.sub(r"(?m)(?<![:'\"])//.*$", "", code)
        if re.search(r"'[^'\n]*카드[^'\n]*'|\"[^\"\n]*카드[^\"\n]*\"", code):
            hits.append(str(p.relative_to(ROOT)))
    assert not hits, hits
    from foms.services.production.part_access import PART_ACCOUNT_STEPS_MESSAGE

    assert PART_ACCOUNT_STEPS_MESSAGE == "공정은 도면에서 작업해요"
    assert ">도면으로 보기<svg" in _read("templates/production/partials/home_day_pane.html")
    parts = _read("templates/production/partials/home_parts.html")
    assert "도면이 오면 여기 나와요</small>" in parts and '<p class="pp-rotate">도면은 태블릿을 가로로 두면 보여요.</p>' in parts
    assert "|| '공정은 도면에서 작업해요', 'bad');" in _read("static/js/production/foms-production-sheet-page.js")


def test_띄어쓰기_겹말() -> None:
    assert "<span data-foms-home-sync-at></span>에 받은 것이에요." in _read("templates/production/partials/home_body.html")
    assert "hidden>그날을 받는 중이에요…</p>" in _read("templates/production/partials/home_date.html")
    assert "'이 주문은 그사이 다른 공정으로 옮겨졌어요." in _read("static/js/production/foms-production-home-steppane.js")
    from foms.services.production.part_mark_gates import PART_USES_CARDS_MESSAGE
    from foms.services.production.part_progress import CARDS_LEFT_MESSAGE

    assert PART_USES_CARDS_MESSAGE.startswith("도면 {left}장이 미완료예요.")
    assert CARDS_LEFT_MESSAGE == "미완료가 있어요"
    assert "'미완료가 있어요 — ' + left.join(' · ')" in _read("static/js/production/foms-production-sheet-parts.js")
    assert '에 미완료가 있어요 — {left}"' in _read("foms/services/production/factory_home.py")
    for rel in ("foms/services/production/part_mark_gates.py", "foms/services/production/part_progress.py",
                "foms/services/production/factory_home.py", "static/js/production/foms-production-sheet-parts.js"):
        code = re.sub(r'""".*?"""', "", _read(rel), flags=re.S)
        assert not re.search(r"""["'][^"'\n]*아직 미완료[^"'\n]*["']""", code), rel


def test_남의_공장_칩은_공장_이름만() -> None:
    """칩 "2공장 작업" + 글 "박엣지 작업 중" = '작업' 두 번(여러 명 같이 작업 뒤) — 칩은 공장 이름 하나."""
    from foms.services.production.factory_scope import elsewhere_info

    info = elsewhere_info({"state": "need", "picked_by_name": "가짜엣지"}, "edge", 2)
    assert info["chip"] == "2공장" and info["text"] == "가짜엣지 작업 중"
    assert info["chip"].count("작업") + info["text"].count("작업") == 1
