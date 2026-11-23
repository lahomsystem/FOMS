"""생산 첫 화면 · 파트 카드 — 시안 맞춤(2026-11-21 사용자 "목업대로", 조사 보고 상위 5 · 6 · 8 · 작은 것).

① 위 탭: 테두리 상자 + 고른 탭 남색 칠(시안 안 3 .seg) ② 글자 손잡이 44px(장갑 D5) — 생산 첫 화면 · 가로 태블릿만
③ [다시 받기] 돌림 그림 — 가로 태블릿만 ④ 파트 카드 이름이 글자 150% 에서 한 글자로 줄지 않게 ⑤ 작업 필요 칸 [재단 완료] 카드 바닥.
세로 · 폰 · PC 는 규칙 밖(미디어쿼리)이라 그대로 — 실화면 대조는 스크래치패드 prod_mockup_fix/sheet.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME_CSS = ROOT / "static/css/contexts/production/home.css"
PARTS_CSS = ROOT / "static/css/contexts/production/parts.css"
ZOOM_CSS = ROOT / "static/css/components/foms-ui-zoom.css"
TABLET = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"


def _tablet_blocks(css: str) -> list[str]:
    return [part.split("\n}\n", 1)[0] for part in css.replace("\r\n", "\n").split(TABLET)[1:]]


def _last_tablet_block() -> str:
    return _tablet_blocks(HOME_CSS.read_text(encoding="utf-8"))[-1]


def test_위_탭은_테두리_상자와_남색_칠_가로_태블릿만() -> None:
    block = _last_tablet_block()
    assert ".foms-prod-home__nav { gap: 0; padding: 0; border: 1px solid var(--fph-line2); border-radius: 10px; background: var(--fph-surface); }" in block
    assert "border-right: 1px solid var(--fph-line2)" in block.split(".foms-prod-home__navtab {", 1)[1].split("}", 1)[0]
    assert re.search(r"\.foms-prod-home__navtab\.is-on, [^{]*\{ background: var\(--fph-brand\); color: #fff; box-shadow: none; \}", block)
    # 밖(PC · 세로)의 탭 꼴은 그대로 — 쟁반 + 흰 알약
    css = HOME_CSS.read_text(encoding="utf-8")
    assert ".foms-prod-home__navtab.is-on { background: var(--fph-surface); color: var(--fph-brand-dark); box-shadow: 0 1px 2px rgba(0, 0, 0, .08); }" in css
    assert ".foms-prod-home__nav { display: flex; gap: 4px; padding: 4px; border-radius: 12px; background: var(--fph-bg); }" in css


def test_글자_손잡이_44px_은_생산_첫_화면_가로_태블릿만() -> None:
    block = _last_tablet_block()
    rules = re.findall(r"^\s*([^{}\n]*\.foms-fs[^{]*)\{", block, re.M)
    assert rules and all(all(sel.strip().startswith(".foms-prod-home ") for sel in r.split(",")) for r in rules), rules
    assert ".foms-prod-home .foms-fs__btn, .foms-prod-home .foms-fs__now { height: 44px; min-width: 44px;" in block
    assert ".foms-prod-home .foms-fs__btn { width: 44px; }" in block and ".foms-prod-home .foms-fs { gap: 0; height: 44px;" in block
    # 손잡이 글자는 배율을 따르지 않는다(공용 조각 규칙) — 여기서 글자 크기를 바꾸지 않는다
    assert not re.search(r"\.foms-fs[^{]*\{[^}]*font-size", block)
    # 공용 조각(다른 화면 손잡이)은 30px 그대로, 생산 CSS 밖에서 44px 손잡이 규칙 없음
    zoom = ZOOM_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.foms-fs__btn,\s*\.foms-fs__now \{\s*height: 30px;", zoom)
    assert re.search(r"\.foms-fs__btn \{\s*width: 30px;", zoom)
    other = [p for p in (ROOT / "static/css").rglob("*.css") if p != HOME_CSS and "foms-fs__btn" in p.read_text(encoding="utf-8", errors="ignore")]
    # (시공 첫 화면은 예전부터 자기 손잡이 꼴이 따로 있다 — 이번에 더한 파일 없음)
    assert sorted(p.relative_to(ROOT).as_posix() for p in other) == [
        "static/css/components/foms-ui-zoom.css", "static/css/contexts/construction/tablet-first.css"]
    # home.css 는 생산 첫 화면(home_styles.html)만 싣는다
    users = [p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*.html") if "production/home.css" in p.read_text(encoding="utf-8")]
    assert users == ["templates/production/partials/home_styles.html"]


def test_다시_받기_돌림_그림은_가로_태블릿에서만_보인다() -> None:
    body = (ROOT / "templates/production/partials/home_body.html").read_text(encoding="utf-8")
    assert '<svg class="foms-prod-home__btn-ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10a9 9 0 1 1 3 7"/><path d="M3 4v6h6"/></svg>다시 받기</a>' in body
    css = HOME_CSS.read_text(encoding="utf-8")
    assert ".foms-prod-home__btn-ic { display: none; }" in css
    assert ".foms-prod-home__btn-ic { display: block;" in _last_tablet_block()


def test_파트_카드_이름은_도면_n_N_을_다음_줄로_보내고_재단_완료는_바닥에() -> None:
    css = PARTS_CSS.read_text(encoding="utf-8")
    assert ".pp-card .pp-ln { flex-wrap: wrap; row-gap: 0; }" in css
    assert ".pp-card .pp-ln .fph-dr__nm { flex: 0 1 auto; }" in css
    assert "grid-template-rows: repeat(4, min-content) 1fr;" in css
    assert ".pp-grid.is-need .pp-img { grid-column: 1; grid-row: 1 / -1;" in css
    assert ".pp-grid.is-need .pp-actbox { grid-row: 5; align-self: end; }" in css
    # 작업 필요 카드의 오른쪽 글 줄(이름 줄 링크 · 시공 줄 · 품목 · 바뀐 도면 · 다른 파트) 뒤 = 단추 칸. 2026-11-23 §8-1 · CSS 계약:
    # 이름 줄 = 작업 시트 링크(a.pp-ln.pp-sheetlink), 시공일 표는 늘 .pp-duerow 로 감싼다(카드 키 그대로 — 감싸기 전에도 같은 자리의 줄).
    tpl = (ROOT / "templates/production/partials/home_parts.html").read_text(encoding="utf-8")
    card = tpl.split("<article", 1)[1].split("</article>", 1)[0]
    kids = re.findall(r"^\s{8}(<(?:div|span|button|a)[^>]*class=\"([^\"]+)\"|\{% if c\.replaced %\})", card, re.M)
    assert [k[1].split("{%")[0] or "replaced" for k in kids] == [
        "pp-img", "pp-img pp-file", "pp-ln pp-sheetlink", "pp-duerow", "fph-dr__pr pp-item", "replaced", "fph-dr__by pp-by",
        "pp-actbox"]
