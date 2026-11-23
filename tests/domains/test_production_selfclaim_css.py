"""파트 맡기 고침 P1 — CSS 계약(설계서 docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md §8-9 · §10 · §14).

새 칸 · 새 클래스에만 걸리는 규칙을 못 박는다(지금 화면은 새 클래스를 안 내보내 그대로 — 전 · 후 그림은 스크래치패드 p1).
- 토큰 값 · 상태 색 짝(ΔE2000 ≥ 10 정상 · ≥ 6 녹색맹 · 적색맹 흉내) · 글 대비 ≥ 4.5 · 무채색 상태 없음.
- 날짜 줄 칸 아래 이름: 15px × 배율 · 칸 76px × 배율 · 숨김 셋(폰 · 세로 / 두 줄 꼴 / 한 줄 꼴 문턱 이름 16자).
- PC 칸 둘째 줄 · 작업 시트 새 글 · 확인 창 새 톤.
- 옮기지 말 것(M6): content-visibility: visible · 목업 접두사 · --mk-z · !important · P2 · P3 규칙.
"""
from __future__ import annotations

import colorsys
import re
from itertools import combinations
from pathlib import Path

from tests.support.color_contrast import contrast_ratio, hex_rgb, pair_distances

ROOT = Path(__file__).resolve().parents[2]
CSS_DIR = ROOT / "static/css/contexts/production"
PIN = "20261123v"
#: P2(2026-11-23 §4-12 여러 파트 고르기 · 다른 파트 줄 '내 담당')가 parts.css 만 다시 올렸다.
PARTS_PIN = "20261124a"


def _css(name: str) -> str:
    return (CSS_DIR / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def _tokens(*names: str) -> dict[str, str]:
    """파일들의 --토큰: 값 (var() 는 한 번 풀어 hex 로)."""
    raw: dict[str, str] = {}
    for name in names:
        raw.update(dict(re.findall(r"(--f(?:ph|pc|pp)-[a-z0-9-]+):\s*([^;]+);", _css(name))))
    out = {}
    for k, v in raw.items():
        m = re.fullmatch(r"var\((--[a-z0-9-]+)\)", v.strip())
        out[k] = raw.get(m.group(1), v).strip() if m else v.strip()
    return out


def _rule(css: str, selector: str) -> str:
    """선택자 목록(쉼표로 나눔)에 selector 가 그대로 들어 있는 규칙 몸통 — 모두 이어 붙인 것(주석은 지우고 본다)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = [m.group(2) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
             if selector in [x.strip() for x in m.group(1).split(",")]]
    assert found, selector
    return "\n".join(found)


def _block(css: str, head: str) -> str:
    """head 로 시작하는 덩이(@media · @container) 몸통 — 괄호 짝 맞춤. 같은 머리가 여럿이면 이어 붙인다."""
    out = []
    for m in re.finditer(re.escape(head) + r"\s*\{", css):
        depth, i = 1, m.end()
        while depth and i < len(css):
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end():i - 1])
    assert out, head
    return "\n".join(out)


NEW_TOKENS = {
    # parts.css — 막힌 칸 셋 · 남의 담당 누른 색 · 창 '지금' 줄 · 까닭 말풍선 · 아침 칩 테두리 · 맡기 취소(= 기본 파랑)
    "--fph-hold-50": "#fed7aa", "--fph-hold-300": "#fb923c", "--fph-hold-700": "#9a3412",
    "--fph-revise-50": "#fca5a5", "--fph-revise-300": "#ef4444", "--fph-revise-700": "#7f1d1d",
    "--fph-pre-50": "#fef08a", "--fph-pre-300": "#eab308", "--fph-pre-700": "#713f12",
    "--fph-taken-10": "#fdf2f8", "--fph-taken-100": "#e6bccd", "--fph-note-50": "#fff7ed", "--fph-note-700": "#7c2d12",
    "--fph-old-line": "#c2410c", "--fph-release-700": "#075985",
    # home.css — 어제부터 · 칸 아래 이름
    "--fph-old-50": "#ffedd5", "--fph-old-300": "#fdba74", "--fph-old-700": "#9a3412",
    "--fph-holder": "#4b525d", "--fph-holder-done": "#4a55b8", "--fph-holder-none": "#6b7380",
    # pc.css · sheet.css — 같은 값, 자기 접두사
    "--fpc-old-700": "#9a3412",
    "--fpp-ok-dark": "#047857", "--fpp-warn-soft": "#fcd34d", "--fpp-taken-10": "#fdf2f8", "--fpp-taken-50": "#eecbda",
    "--fpp-taken-700": "#7a3f5c",
}


def test_새_토큰_값() -> None:
    tok = _tokens("home.css", "parts.css", "pc.css", "sheet.css")
    assert {k: tok.get(k) for k in NEW_TOKENS} == NEW_TOKENS
    # 있는 색과 같은 값은 토큰을 가리킨다(설계서 §10 '새 토큰')
    parts, home = _css("parts.css"), _css("home.css")
    assert "--fph-release-700: var(--fph-basic-700);" in parts
    for line in ("--fph-holder: var(--fph-text2);", "--fph-holder-done: var(--fph-brand-dark);", "--fph-holder-none: var(--fph-text3);",
                 "--fph-step-w: calc(76px * var(--foms-fs, 1));"):
        assert line in home, line
    # 1공장 · 남의 공장 토큰은 이번(P1)에 없다 — P3
    assert "--fph-fac" not in parts + home


def test_상태_색_짝은_정상_10_색약_6_이상이고_무채색이_없다() -> None:
    """같은 단추 자리(카드 actbox)에 서는 상태 바탕 일곱 — 지금 넷(내 담당 · 남의 담당 · 완료 · 기본) + 새 셋(보류 · 도면 고치는 중 · 검수 미완료)
    + 흰 단추([내가 엣지]). 어제부터 칩(아침 칩)은 설계서 §8-9 짝(남의 담당 · 내 담당)만 — 보류 · 완료와는 같은 자리에 안 선다."""
    tok = _tokens("home.css", "parts.css")
    slot = {k: hex_rgb(tok[k]) for k in ("--fph-need-50", "--fph-taken-50", "--fph-done-50", "--fph-basic-50",
                                          "--fph-hold-50", "--fph-revise-50", "--fph-pre-50", "--fph-surface")}
    new = {"--fph-hold-50", "--fph-revise-50", "--fph-pre-50"}
    for a, b in combinations(slot, 2):
        if not ({a, b} & new):
            continue
        normal, deu, pro = pair_distances(slot[a], slot[b])
        assert normal >= 10 and deu >= 6 and pro >= 6, (a, b, round(normal, 1), round(deu, 1), round(pro, 1))
    for other in ("--fph-taken-50", "--fph-need-50"):
        normal, deu, pro = pair_distances(hex_rgb(tok["--fph-old-50"]), hex_rgb(tok[other]))
        assert normal >= 10 and deu >= 6 and pro >= 6, ("--fph-old-50", other)
    # 창 실행 단추: 맡기 취소(파랑) ↔ 맡기 · 담당 바꾸기 · 대신 완료(관리자 고르기 한 줄)
    run = {k: hex_rgb(tok[k]) for k in ("--fph-release-700", "--fph-brand-dark", "--fph-taken-700", "--fph-done-700")}
    for a, b in combinations(run, 2):
        normal, deu, pro = pair_distances(run[a], run[b])
        assert normal >= 10 and deu >= 6 and pro >= 6, (a, b, round(normal, 1), round(deu, 1), round(pro, 1))
    # 무채색 상태 금지(D52) — 새 바탕은 모두 채도 0.3 이상
    for k in ("--fph-hold-50", "--fph-revise-50", "--fph-pre-50", "--fph-old-50", "--fph-note-50", "--fph-taken-10", "--fph-taken-100"):
        r, g, b = hex_rgb(tok[k])
        assert colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[2] >= 0.3, k


def test_새_글_대비는_4_5_이상() -> None:
    tok = _tokens("home.css", "parts.css", "pc.css", "sheet.css")
    white = "#ffffff"
    pairs = [
        ("--fph-hold-700", "--fph-hold-50"), ("--fph-revise-700", "--fph-revise-50"), ("--fph-pre-700", "--fph-pre-50"),
        ("--fph-old-700", "--fph-old-50"), ("--fph-old-700", "--fph-hold-50"),  # 아침 칩 · 누른 칩
        ("--fph-note-700", "--fph-note-50"),  # 까닭 말풍선
        ("--fph-taken-700", "--fph-taken-50"), ("--fph-taken-700", "--fph-taken-100"),  # 남의 담당 칸 · 누른 칸
        ("--fph-taken-700", "--fph-taken-10"), ("--fph-dw-late", "--fph-danger-50"),  # 창 '지금' 줄 · 진 경합 상자
        ("--fph-done-800", "--fph-done-50"),  # 손 체크 칸 '작업 시트'
        ("--fpc-text2", "--fpc-brand-50"), ("--fpc-old-700", "--fpc-brand-50"),  # PC '지금' 칸 미정 · 밤 넘김
        ("--fpp-amber-text", "--fpp-warn-50"), ("--fpp-taken-700", "--fpp-taken-10"), ("--fpp-text", "--fpp-taken-10"),
    ]
    for fg, bg in pairs:
        assert contrast_ratio(hex_rgb(tok[fg]), hex_rgb(tok[bg])) >= 4.5, (fg, bg)
    on_white = ["--fph-holder", "--fph-holder-done", "--fph-holder-none", "--fph-old-700", "--fph-why", "--fph-need-700",
                "--fph-taken-700", "--fph-dw-late", "--fpc-old-700", "--fpp-ok-dark", "--fpp-text2", "--fpp-amber-text"]
    for fg in on_white:
        assert contrast_ratio(hex_rgb(tok[fg]), hex_rgb(white)) >= 4.5, fg
    for bg in ("--fph-release-700", "--fph-taken-700"):  # 흰 글 실행 단추
        assert contrast_ratio(hex_rgb(white), hex_rgb(tok[bg])) >= 4.5, bg
    # 아침 칩 테두리는 칩 바탕 · 판 바탕에서 3:1 이상(경계)
    for bg in ("--fph-old-50", "--fph-bg", "--fph-surface"):
        assert contrast_ratio(hex_rgb(tok["--fph-old-line"]), hex_rgb(tok[bg])) >= 3, bg


def test_날짜_줄_칸_아래_이름과_숨김_셋() -> None:
    home = _css("home.css")
    assert ".fph-dr__steps.has-hd .fph-dr__st { width: var(--fph-step-w); }" in home
    hd = _rule(home, ".fph-dr__hd")
    assert "font-size: calc(15px * var(--foms-fs, 1))" in hd and "white-space: nowrap" in hd
    assert "overflow: hidden; text-overflow: ellipsis" in _rule(home, ".fph-dr__hd b")  # 이름만 말줄임
    assert "flex-shrink: 0" in _rule(home, ".fph-dr__hd span")  # 꼬리(' 외 n' · ' 바뀜')는 안 줄임
    assert "color: var(--fph-holder-done)" in _rule(home, ".fph-dr__hd.is-done")
    assert "color: var(--fph-holder-none)" in _rule(home, ".fph-dr__hd.is-none")
    assert "color: var(--fph-old-700)" in _rule(home, ".fph-dr__hd.is-old")
    assert "font-size: calc(15px * var(--foms-fs, 1))" in _rule(home, ".fph-dr .fph-dr__sg small.is-miss")
    hide = (".fph-dr__hd { display: none; }", ".fph-dr__steps.has-hd { gap: 6px; }", ".fph-dr__steps.has-hd .fph-dr__st { width: auto; }")
    wide = _block(home, "@media (min-width: 992px)")
    one = _block(wide, "@container fph-pane (max-width: calc(190px + 4 * 4.75rem + 25.75rem - 0.02px))")  # 이름 16자(지휘 판정 11-23)
    two = _block(wide, "@container fph-pane (max-width: calc(196px + 4 * max(34px, 1.5rem) + 20.75rem - 0.02px))")  # 두 줄 꼴 문턱 그대로
    phone = _block(home, "@media (max-width: 991.98px)")
    for body in (one, phone):
        for line in hide:
            assert line in body, line
    # 두 줄 꼴 덩이는 자리만 바꾼다(11-14 규칙) — 이름 줄 숨김은 한 줄 꼴 문턱 덩이가 하고, 그 문턱이 어느 글자 배율에서나 더 넓다
    assert "display: none" not in two

    def _px(expr: str, fs: float) -> float:
        py = re.sub(r"(\d+(?:\.\d+)?)rem", lambda m: f"({m.group(1)}*{16 * fs})", expr)
        return eval(py.replace("px", ""), {"max": max})  # noqa: S307 — 이 시험의 고정 식

    for fs in (1, 1.2, 1.3, 1.4, 1.5):
        assert _px("190px + 4 * 4.75rem + 25.75rem", fs) > _px("196px + 4 * max(34px, 1.5rem) + 20.75rem", fs), fs
    assert abs(_px("190px + 4 * 4.75rem + 25.75rem", 1) - (128 + 36 + 12 + 2 + 12 + 4 * 76 + 92 + 16 * 20)) < 0.01  # 이름 16자
    # 숨김 덩이는 기본 규칙보다 뒤(같은 특이도 — 뒤가 이긴다)
    assert home.index(".fph-dr__steps.has-hd .fph-dr__st { width: var(--fph-step-w); }") < home.index("@container fph-pane (max-width: calc(190px")
    # 12자 문턱(20.75rem 짜리 190px 식)은 쓰지 않는다
    assert "calc(190px + 4 * 4.75rem + 20.75rem" not in home
    # 자리표시 키(F2): 한 줄 꼴 84 · 두 줄 꼴 · 폰 140(× 배율)
    assert "contain-intrinsic-size: auto calc(84px * var(--foms-fs, 1));" in _rule(home, ".fph-dr")
    assert "contain-intrinsic-size: auto calc(140px * var(--foms-fs, 1))" in two and "contain-intrinsic-size: auto calc(140px * var(--foms-fs, 1))" in phone


def test_카드_새_칸() -> None:
    parts = _css("parts.css")
    # 막힌 칸 셋 — 바탕 · 테두리 · 글 토큰, hover 되돌림(F5)
    for kind in ("hold", "revise", "pre"):
        rule = _rule(parts, f".fph-wi.pp-st-{kind}")
        for prop in (f"background: var(--fph-{kind}-50)", f"border-color: var(--fph-{kind}-300)", f"color: var(--fph-{kind}-700)"):
            assert prop in rule, (kind, prop)
        assert f"color: var(--fph-{kind}-700)" in _rule(parts, f".fph-wi.pp-st-{kind}:hover")
    # 내 담당 한 층 — 짝 끝 단추 56px, 그 밖 끝 단추 72px 그대로
    assert "min-height: 56px" in _rule(parts, ".foms-prod-home .pp-fin.fph-qr__done.is-pair")
    assert "min-height: 72px" in _rule(parts, ".foms-prod-home .pp-fin.fph-qr__done")
    # 이름 줄 링크 — 밑줄은 이름만, 누름 칸은 ::after
    assert "text-decoration: none" in _rule(parts, ".pp-sheetlink") and 'content: ""' in _rule(parts, ".pp-sheetlink::after")
    # 까닭 말풍선은 떠 있다(카드 키 그대로, F16)
    assert "position: absolute" in _rule(parts, ".pp-why") and "position: relative" in _rule(parts, ".pp-actbox")
    # 창: 몸 글 · 새 톤 · 진 경합 — .foms-prod-home .pp-modal 아래(0,3,0)
    for sel in (".foms-prod-home .pp-modal .pp-mbody", ".foms-prod-home .pp-modal .pp-al--taken", ".foms-prod-home .pp-modal .pp-al--release",
                ".foms-prod-home .pp-modal .pp-al--now", ".foms-prod-home .pp-modal.is-lost .pp-merr",
                ".foms-prod-home .pp-modal .pp-mgo--taken", ".foms-prod-home .pp-modal .pp-mgo--release", ".foms-prod-home .pp-modal .pp-mchoices"):
        _rule(parts, sel)
    assert "word-break: keep-all" in _rule(parts, ".pp-merr")
    assert "background: var(--fph-release-700)" in _rule(parts, ".foms-prod-home .pp-modal .pp-mgo--release")
    # 아침 칩 · 작은 창
    assert "background: var(--fph-old-50)" in _rule(parts, ".pp-mchip") and "position: absolute" in _rule(parts, ".pp-mpop")
    assert "text-decoration: none" in _rule(parts, ".pp-mpop a")  # Bootstrap 밑줄(F7)
    assert ".pp-card { content-visibility: auto; contain-intrinsic-size: auto 344px; }" in parts


def test_PC_칸_둘째_줄은_has_hd_일_때만_늘_보이고_꼬리는_안_줄인다() -> None:
    pc = _css("pc.css")
    m = _rule(pc, ".fpc-steps.has-hd .fpc-s__m")
    assert "display: flex" in m and "font-size: calc(13px * var(--foms-fs, 1))" in m and "white-space: nowrap" in m
    assert "text-overflow: ellipsis" in _rule(pc, ".fpc-s__m > b") and "flex-shrink: 0" in _rule(pc, ".fpc-s__m > span")
    assert "color: var(--fpc-text2)" in _rule(pc, ".fpc-s.is-now .fpc-s__m.is-none")  # F9
    # 지금 칸 글은 그대로 — 평소 숨김, 아주 넓을 때만(1,500px)
    assert ".fpc-s__m { display: none;" in pc and ".fpc-s__m { display: block; }" in pc
    assert ".fpc-s { height: 56px;" in pc


def test_작업_시트_새_글() -> None:
    sheet = _css("sheet.css")
    note = _rule(sheet, ".foms-prod-page__step small.fpp-note")
    assert "font-size: calc(15px * var(--foms-fs, 1))" in note and "white-space: normal" in note
    assert "color: var(--fpp-amber-text)" in _rule(sheet, ".foms-prod-page__step small.fpp-note.is-miss")
    assert "color: var(--fpp-ok-dark)" in _rule(sheet, ".foms-prod-page__step small.fpp-note.is-ok")
    for sel in (".fpp-stepmsg", ".fpp-why", ".fpp-loglink", ".fpp-log li", ".fpp-log li.is-miss"):
        _rule(sheet, sel)
    # 새 규칙은 옆 시트(.foms-prod-sheet) 칸 옆 글 규칙보다 뒤 — 두 꼴 모두 같은 모양
    assert sheet.index(".foms-prod-page__step small.fpp-note") > sheet.index(".foms-prod-sheet .foms-prod-page__step small")
    sizes = re.findall(r"font-size:\s*([^;}]+)", sheet.split("파트 맡기 고침", 1)[1])
    assert sizes and all(re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", s.strip()) for s in sizes), sizes


def test_옮기지_말_것() -> None:
    """설계서 §10 M6 — 목업 그림틀 · 미루기 끄기 · 목업 접두사 · !important · 창 토큰 다시 적기, 그리고 P2 · P3 규칙."""
    files = {n: _css(n) for n in ("home.css", "parts.css", "pc.css", "sheet.css")}
    for name, css in files.items():
        code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        # !important 는 늘리지 않는다(home.css 의 1곳은 전부터 있던 것)
        assert code.count("!important") == {"home.css": 1}.get(name, 0), name
        assert not re.search(r"\.v[23]-|--mk-z|\.fz\b|\.fz[12]\b", code), name
        for p3 in (".fph-fac", ".is-elsewhere", ".pp-elsewhere-note", ".pp-otherg", ".pp-partpick", ".pp-parts--fac", ".is-split"):
            assert p3 not in code, (name, p3)
        for old in (".pp-st-wait", ".pp-fin2", ".pp-facs", ".pp-mgo--free", ".pp-al--free", "is-otherfac"):
            assert old not in code, (name, old)
    parts_code = re.sub(r"/\*.*?\*/", "", files["parts.css"], flags=re.S)
    assert "content-visibility: visible" not in parts_code  # 카드 미루기는 그대로(11-14)
    assert ".fph-dr:nth-of-type(-n+10) { content-visibility: visible; }" in files["home.css"]  # 있던 앞 10줄 규칙만
    assert files["home.css"].count("content-visibility: visible") == 1
    # 창 안에서 토큰을 다시 적지 않는다(실앱 창은 .foms-prod-home 안)
    assert not re.search(r"\.pp-modal[^{]*\{[^}]*--fph-[a-z0-9-]+\s*:", parts_code)


def test_네_파일_핀() -> None:
    styles = (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")
    for name, pin in (("home.css", PIN), ("parts.css", PARTS_PIN), ("pc.css", PIN)):
        assert f"production/{name}') }}}}?v={pin}" in styles, name
    for rel in ("templates/production/sheet.html", "templates/production/partials/tablet_kanban_body.html"):
        assert f"production/sheet.css') }}}}?v={PIN}" in (ROOT / rel).read_text(encoding="utf-8"), rel
    assert f"production/pc.css') }}}}?v={PIN}" in (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
