"""F6: 정산 대시보드 **글자 크기 조절 모듈** 계약 테스트.

정산 화면(요약·실무·분석·네이버 정산 탭)에 네이버 워크벤치와 같은 글자 크기 조절기
(−/현재 배율/+)를 얹는다. 조절기는 화면 하나에 **1벌**이고 배율은 **한 변수(`--s-fs`)**로
흐른다. 이 파일은 그 이식이 **놓치면 조용히 망가지는 것**만 잠근다:

1. **조절기 위치·개수** — 셸 탭줄(`.s-tabs`) 안, 집중 모드 버튼 뒤·메타 앞에 1벌. pane
   파셜(실무·채널)에 들어가면 프래그먼트 스왑 뒤 조절기가 두 벌이 되고, 탭으로 잡히면
   (`role="tab"`/`data-settlement-tab`) ←→ 순회와 activateTab 이 조절기를 5번째 탭으로 삼는다.
2. **CSS 전량 배율** — 3 파일의 모든 `font-size: Npx` 가 `calc(Npx * var(--s-fs, 1))` 로
   바뀌어야 한다. 한 규칙이라도 고정 px 로 남으면 "키웠는데 저기만 작다"가 된다. 예외는
   조절기 자신뿐(조절기가 같이 커지면 손이 따라간다). 폴백 `, 1` 이 빠지면 변수가 없는
   문맥(파셜 단독 렌더·다른 셸)에서 글자가 통째로 사라진다.
3. **JS 배선** — 상수는 `mount` 보다 위(var 호이스팅은 선언만 끌어올리고 대입은 안 따라온다 —
   워크벤치에서 실제로 막혔다), 클릭은 **기존 루트 위임** 한 곳, 복원은 `mount(root)` 안.
   전역(document/window) 리스너는 **하나도 늘지 않는다** — 프래그먼트 스왑마다 스크립트가
   재실행되므로 하나 붙이면 스왑 횟수만큼 누적된다(perf G4).
4. **조절기 블록 위생** — 목업 잔재 낱말·인라인 style·Jinja 값 금지(저장소 절대 규칙).
5. **자산 핀 사슬** — 자산 6개의 핀이 각 사슬(셸 4·채널 2) 안에서 한 값. CSS/JS 를 고쳤는데
   핀이 갈리면 실기기가 옛 자산을 실행한다(서비스워커 cache-first).

**단정 원칙**: 이름·구조·개수만 단정한다. 핀 리터럴·조절기 px 값처럼 **자주 바뀌는 값**은
단정하지 않는다(값을 못 박으면 다음 범프마다 이 파일이 red 가 되어 계약이 사문이 된다).
문서 디렉토리는 읽지 않는다(CI-DOCSCOPE-01).

헬퍼는 요약 탭 렌더 계약(`test_settlement_dashboard_render.py`)과 채널 렌더 계약
(`test_settlement_channel_render.py`)의 것을 **import 해서** 쓴다 — 복제하면 프래그먼트
헤더·핀 추출 규칙이 갈려 "전체 페이지가 와서 검사가 통째로 어긋나는" 함정을 탄다.
"""

from __future__ import annotations

import re

import pytest

# --- 요약 탭 렌더 계약의 헬퍼·자산 이름 재사용(복제 금지) ----------------------------
from tests.domains.test_settlement_dashboard_render import (  # noqa: E402
    _MOCKUP_LEFTOVERS,
    _fragment_html,
    _login_allowed,
    _pins_for,
    _PIN_SUFFIX,
    _read,
    _read_code,
    _strip_comments,
)
from tests.domains.test_settlement_dashboard_render import CSS_ASSET as SUMMARY_CSS  # noqa: E402
from tests.domains.test_settlement_dashboard_render import JS_ASSET as SUMMARY_JS  # noqa: E402

# --- 채널 탭: 파셜 단독 렌더 + 자산 이름 ---------------------------------------------
from tests.domains.test_settlement_channel_render import _render as _render_channel_partial  # noqa: E402
from tests.domains.test_settlement_channel_render import CSS_ASSET as CHANNEL_CSS  # noqa: E402
from tests.domains.test_settlement_channel_render import JS_ASSET as CHANNEL_JS  # noqa: E402

# --- 실무 탭: 파셜 소스 + 자산 이름 ---------------------------------------------------
from tests.domains.test_settlement_operations_render import BODY_TEMPLATE as OPS_TEMPLATE  # noqa: E402
from tests.domains.test_settlement_operations_render import CSS_ASSET as OPS_CSS  # noqa: E402
from tests.domains.test_settlement_operations_render import JS_ASSET as OPS_JS  # noqa: E402

#: 조절기가 사는 셸(탭줄·pane·자산 링크의 소유자).
SHELL_TEMPLATE = "templates/cs/partials/settlement_dashboard_body.html"
#: 조절기 동작(상수·함수·위임 분기·복원)이 사는 스크립트.
DASH_JS = "static/js/settlement/dashboard.js"
#: 배율이 흘러야 하는 CSS 전부 — 정산 화면 네 탭이 이 셋으로 그려진다.
CSS_FILES = (
    "static/css/settlement/settlement-dashboard.css",
    "static/css/settlement/settlement-operations.css",
    "static/css/settlement/settlement-channel.css",
)

#: 조절기 훅 3종 + 그룹 훅. id 가 아니라 `data-settlement-*` 인 이유: 프래그먼트 스왑으로
#: 같은 문서에 루트가 잠깐 두 벌 살 수 있어 id 는 충돌한다(이 셸의 기존 관례).
FS_GROUP = "data-settlement-fs"
FS_DOWN = 'data-settlement-fs-step="-1"'
FS_UP = 'data-settlement-fs-step="1"'
FS_NOW = "data-settlement-fs-now"
#: 그룹 훅만 세는 정규식 — `count("data-settlement-fs")` 는 -step/-now 까지 4 로 센다.
_FS_GROUP_RE = re.compile(r"\bdata-settlement-fs(?=[\s>])")
#: 집중 모드 **버튼**만 — `data-settlement-focusbar`(탭줄 위 복귀 바)·`-focus-exit` 를 빼고 본다.
_FOCUS_BUTTON_RE = re.compile(r"\bdata-settlement-focus(?=[\s>])")

#: JS 계약 리터럴. 단계·저장 키는 워크벤치와 같은 모양(사용자가 두 화면을 오간다).
FONT_STEPS_LITERAL = "var FONT_STEPS = [1, 1.15, 1.3, 1.5]"
FONT_KEY_LITERAL = "var FONT_KEY = 'foms.settlement.fontScale'"
#: 배율 변수. 루트 1곳에만 선언하고 나머지 두 CSS 는 상속으로 받는다.
CSS_VAR = "--s-fs"
#: 조절기 자신의 클래스 접두어 — 고정 px 예외 판정 기준(선택자에 이 문자열이 있으면 예외).
CONTROL_CLASS_PREFIX = ".s-fs__"
#: 조절기 블록의 여는 태그(블록 추출 기준).
_CONTROL_OPEN = '<span class="s-fs"'

#: 전역 리스너 수(기존 계약과 같은 수). document 3 = swap 2종 + DOMContentLoaded,
#: window 2 = resize + Esc(keydown). 조절기는 네이티브 `<button>` 의 Enter/Space → click
#: 위임으로 충분해 keydown 을 새로 붙이지 않는다.
DOCUMENT_LISTENERS = 3
WINDOW_LISTENERS = 2

#: 변환된 규칙의 정확한 모양. 폴백 `, 1` 까지 계약이다.
_SCALED_FONT_SIZE_RE = re.compile(r"font-size:\s*calc\([\d.]+px \* var\(--s-fs, 1\)\)")

#: 고정 px 글자 크기(규칙 단위 검사용). `calc(` 로 시작하면 여기 안 걸린다.
_FIXED_FONT_SIZE_RE = re.compile(r"font-size:\s*[\d.]+px")
#: `font:` 축약형에 px 가 섞이면 배율을 우회한다(`font: inherit` 은 px 가 없어 무관).
_FONT_SHORTHAND_PX_RE = re.compile(r"font:\s*[^;]*\dpx")
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _at(text: str, needle: str, what: str) -> int:
    """`needle` 의 위치를 돌려준다. 없으면 **사람이 읽는 red** 로 죽인다(`ValueError` 대신).

    Args:
        text: 검사 대상 원문.
        needle: 찾을 리터럴.
        what: 실패 메시지에 붙일 설명.

    Returns:
        첫 출현 인덱스.
    """
    idx = text.find(needle)
    assert idx >= 0, f"{what}: '{needle}' 가 없다"
    return idx


def _control_block(text: str) -> str:
    """조절기 블록(`<span class="s-fs"` ~ 두 번째 `</button>` 뒤 첫 `</span>`)을 잘라낸다.

    렌더 HTML 과 템플릿 소스 양쪽에 같은 방법을 써서 "렌더는 맞는데 소스에 숨은 것" 과
    "소스는 맞는데 `{% if %}` 로 꺼진 것" 을 같은 눈으로 본다.

    Args:
        text: 렌더 HTML 또는 템플릿 원문.

    Returns:
        조절기 블록 문자열.
    """
    start = text.find(_CONTROL_OPEN)
    assert start >= 0, f"조절기 블록이 없다: {_CONTROL_OPEN}"
    cursor = start
    for _ in range(2):
        cursor = text.find("</button>", cursor)
        assert cursor >= 0, "조절기 블록에 버튼(−/+)이 둘 있어야 한다"
        cursor += len("</button>")
    end = text.find("</span>", cursor)
    assert end >= 0, "조절기 블록의 닫는 </span> 이 없다"
    return text[start:end + len("</span>")]


def _css_rules(rel: str) -> list[str]:
    """CSS 를 주석 제거 후 **규칙 단위**(`}` 분할)로 돌려준다.

    선언이 아니라 규칙 단위로 보는 이유: 고정 px 이 **어느 선택자 안**에 있는지가 판정 기준이다
    (조절기 자신만 예외).
    """
    css = _CSS_COMMENT_RE.sub(" ", _read(rel))
    return css.split("}")


def _rule_selector(rule: str) -> str:
    """규칙 조각에서 선언 블록 앞부분(선택자 — `@media` 안이면 그 prelude 포함)을 돌려준다."""
    return rule.rsplit("{", 1)[0]


def _rule_label(rule: str) -> str:
    """실패 메시지용 선택자 한 줄(마지막 줄)."""
    lines = _rule_selector(rule).strip().splitlines()
    return lines[-1].strip() if lines else rule.strip()[:80]


# ==========================================================================
# 계약 1 — 조절기는 셸 탭줄에 1벌, 탭이 아니다, pane 파셜에는 없다
# ==========================================================================
def test_font_size_control_is_on_the_shell_once(client, app):
    """조절기 훅 3종이 셸 프래그먼트 렌더에 **정확히 1벌**, 탭줄 안 정해진 자리에 있다.

    자리 계약: `role="tablist"` < 집중 모드 버튼 < 조절기 < `.s-tabs-meta`. 집중 모드는 루트
    **밖** 크롬만 접고 탭줄은 남으므로 조절기를 집중 모드 바에 복제하지 않는다(1벌이 계약).
    """
    _login_allowed(client)

    html = _strip_comments(_fragment_html(client))

    assert html.count(FS_DOWN) == 1, html.count(FS_DOWN)
    assert html.count(FS_UP) == 1, html.count(FS_UP)
    assert html.count(FS_NOW) == 1, html.count(FS_NOW)
    assert len(_FS_GROUP_RE.findall(html)) == 1, _FS_GROUP_RE.findall(html)

    tablist_at = _at(html, 'role="tablist"', "탭줄")
    focus_btn = _FOCUS_BUTTON_RE.search(html)
    assert focus_btn, "집중 모드 버튼이 없다"
    control_at = _at(html, FS_DOWN, "조절기")
    meta_at = _at(html, 'class="s-tabs-meta"', "탭줄 메타")
    assert tablist_at < focus_btn.start() < control_at < meta_at, (
        tablist_at, focus_btn.start(), control_at, meta_at)

    block = _control_block(html)
    # 탭으로 잡히면 ←→ 순회·activateTab 이 조절기를 탭으로 삼는다.
    assert 'role="tab"' not in block, block
    assert "data-settlement-tab" not in block, block
    # id 는 프래그먼트 스왑 중 두 벌이 될 수 있다 — 훅은 data-* 뿐.
    assert re.search(r"\bid=", block) is None, block
    # 전역 `.btn { padding !important }` 함정 — 좁은 칸에서 글자가 세로로 쪼개진다.
    assert re.search(r'class="[^"]*\bbtn\b', block) is None, block
    assert block.count('type="button"') == 2, block
    assert 'aria-live="polite"' in block, block
    assert 'aria-label="글자 크기"' in block, block
    # 초기 라벨은 백분율 텍스트 그대로(별도 문장 없음 — 워크벤치와 동일).
    assert ">100%<" in block, block


def test_font_size_control_is_absent_from_pane_partials(app):
    """실무·채널 pane 파셜에는 조절기가 **없다** — 셸에만 산다.

    파셜에 들어가면 pane 을 갈아 끼울 때마다 조절기가 두 벌이 되고, 탭을 옮기면 조절기가
    사라진다(워크벤치 계약과 같은 이유).
    """
    channel_html = _render_channel_partial(app)
    assert FS_GROUP not in channel_html, "채널 파셜 렌더에 조절기 훅이 있다"

    ops_src = _read_code(OPS_TEMPLATE)
    assert FS_GROUP not in ops_src, "실무 파셜 소스에 조절기 훅이 있다"


# ==========================================================================
# 계약 2 — CSS 전량이 배율을 문다(조절기 자신만 예외), 토큰은 루트 1곳, 폴백 필수
# ==========================================================================
@pytest.mark.parametrize("rel", CSS_FILES)
def test_every_settlement_font_size_follows_the_scale(rel):
    """이 파일의 모든 글자 크기 규칙이 `--s-fs` 배율을 따른다(조절기 자신만 고정 px).

    `@media`·`@container` 안의 규칙도 포함한다 — 좁은 폭 규칙만 고정 px 로 남으면 좁은 화면에서만
    버튼이 안 먹는다. `font:` 축약형에 px 를 섞는 우회도 막는다.
    """
    offenders = []
    for rule in _css_rules(rel):
        has_fixed = _FIXED_FONT_SIZE_RE.search(rule) or _FONT_SHORTHAND_PX_RE.search(rule)
        if not has_fixed:
            continue
        if CONTROL_CLASS_PREFIX in _rule_selector(rule):   # 조절기 자신만 예외
            continue
        offenders.append(_rule_label(rule))

    assert not offenders, f"{rel}: 배율을 안 따르는 글자 크기 규칙 {offenders}"


@pytest.mark.parametrize("rel", CSS_FILES)
def test_scaled_font_size_rules_cover_the_screen(rel):
    """변환된 규칙(`calc(Npx * var(--s-fs, 1))`)이 파일마다 실제로 남아 있다.

    "고정 px 0" 만 보면 `font-size` 선언을 통째로 지운 회귀도 통과한다 — 변환된 모양이
    있어야 한다. 수치 하한은 두지 않는다(리뷰 R2): 중복 선택자 통합 같은 정당한 CSS 정리가
    거짓 red 를 내면 안 되고, "몇 곳" 은 계약이 아니라 그때그때의 사실이다.
    """
    found = _SCALED_FONT_SIZE_RE.findall(_CSS_COMMENT_RE.sub(" ", _read(rel)))

    assert found, f"{rel}: 배율을 무는 font-size 규칙이 하나도 없다"


def test_scale_token_is_declared_on_the_root():
    """`--s-fs: 1` 은 요약 CSS 의 `.foms-settle {` 루트 블록 **한 곳**에만 있다.

    실무·채널 CSS 는 상속으로 받는다 — 세 곳에 선언하면 어느 하나가 조용히 다른 값을 갖는다.
    """
    css = _CSS_COMMENT_RE.sub(" ", _read(CSS_FILES[0]))
    root_at = _at(css, ".foms-settle {", "루트 토큰 블록")
    root_block = css[root_at:_at(css[root_at:], "}", "루트 블록 닫힘") + root_at]

    assert f"{CSS_VAR}: 1;" in root_block, root_block

    for rel in CSS_FILES[1:]:
        assert f"{CSS_VAR}:" not in _CSS_COMMENT_RE.sub(" ", _read(rel)), (
            f"{rel}: 배율 토큰은 루트 1곳에만 선언한다(상속이 계약)")


@pytest.mark.parametrize("rel", CSS_FILES)
def test_scale_var_always_has_a_fallback(rel):
    """`var(--s-fs)` 단독(폴백 없음)은 0 — 변수가 없는 문맥에서 글자가 통째로 사라진다."""
    css = _CSS_COMMENT_RE.sub(" ", _read(rel))

    assert f"var({CSS_VAR})" not in css, f"{rel}: 폴백 없는 var({CSS_VAR}) 가 있다"


def test_control_keeps_fixed_px_for_itself():
    """조절기 자신(`.s-fs__btn`·`.s-fs__now`)은 고정 px 다 — 값은 단정하지 않는다.

    조절기가 같이 커지면 손이 따라가고, 150% 에서 탭줄 높이를 밀어 올린다.
    """
    found = {".s-fs__btn": False, ".s-fs__now": False}
    for rule in _css_rules(CSS_FILES[0]):
        selector = _rule_selector(rule)
        body = rule.rsplit("{", 1)[-1]
        if not _FIXED_FONT_SIZE_RE.search(body):   # 계약 2 와 같은 판정식(소수 px 포함, 리뷰 R5)
            continue
        for cls in found:
            if cls in selector:
                found[cls] = True

    missing = [cls for cls, ok in found.items() if not ok]
    assert not missing, f"조절기 고정 px 규칙이 없다: {missing}"


# ==========================================================================
# 계약 3 — JS 배선: 상수·함수·위임 분기·복원, 전역 리스너 불변
# ==========================================================================
def test_font_scale_constants_and_functions_exist():
    """단계·저장 키·함수 4개·CSS 변수·라벨 훅이 **코드**(주석 아님)에 있고, 상수는 `mount` 위다.

    `var` 는 선언만 끌어올려지고 대입은 안 따라온다 — defer 스크립트라 `mountAll()` 이 곧바로
    돌므로 상수가 아래에 있으면 첫 복원이 `undefined` 를 읽는다(워크벤치에서 실제로 막혔다).
    """
    js = _read_code(DASH_JS)

    for needle in (
        FONT_STEPS_LITERAL,
        FONT_KEY_LITERAL,
        "function readFontScale(",
        "function currentFontScale(root)",
        "function applyFontScale(root, scale)",
        "function stepFontScale(root, dir)",
        f"'{CSS_VAR}'",
        f"[{FS_NOW}]",
        "localStorage.getItem(FONT_KEY)",
        "localStorage.setItem(FONT_KEY",
    ):
        assert needle in js, f"dashboard.js 에 '{needle}' 가 없다"

    assert _at(js, "var FONT_STEPS", "단계 상수") < _at(js, "function mount(root)", "mount"), (
        "FONT_STEPS 는 mount(root) 보다 위에 있어야 한다(var 호이스팅 함정)")


def test_font_scale_is_wired_through_the_existing_delegation():
    """클릭은 `bindControls` 의 **기존 루트 위임** 안, 복원은 `mount(root)` 안이다.

    별도 리스너를 만들면 루트 밖(전역)에 붙거나 스왑마다 누적된다. 위임 분기와 복원 호출이
    각각 정해진 함수 구간 안에 있어야 "어디선가 되긴 한다" 가 아니라 이 셸의 규율을 따른다.
    """
    js = _read_code(DASH_JS)

    bind_at = _at(js, "function bindControls(", "위임 함수")
    collect_at = _at(js, "function collectEls(", "위임 함수 끝 경계")
    assert bind_at < collect_at, (bind_at, collect_at)
    delegation = js[bind_at:collect_at]
    assert "'[data-settlement-fs-step]'" in delegation, "위임 리스너에 조절기 분기가 없다"
    assert "stepFontScale(ctx.root" in delegation, "조절기 분기가 stepFontScale(ctx.root, …) 를 안 부른다"

    mount_at = _at(js, "function mount(root)", "mount")
    all_at = _at(js, "function mountAll()", "mountAll")
    assert mount_at < all_at, (mount_at, all_at)
    assert "applyFontScale(root, readFontScale())" in js[mount_at:all_at], (
        "mount(root) 가 저장된 배율을 복원하지 않는다")


def test_dashboard_js_registers_no_new_global_listener():
    """전역 리스너는 document 3 · window 2 **그대로**다.

    프래그먼트 스왑마다 `<script src>` 가 재실행된다 — 새 전역 리스너 하나가 스왑 횟수만큼
    누적된다(perf G4). 조절기는 네이티브 `<button>` 이라 Enter/Space 가 click 으로 오므로
    keydown 을 새로 붙일 이유가 없다.
    """
    js = _read_code(DASH_JS)

    assert js.count("document.addEventListener") == DOCUMENT_LISTENERS, js.count(
        "document.addEventListener")
    assert js.count("window.addEventListener") == WINDOW_LISTENERS, js.count(
        "window.addEventListener")


# ==========================================================================
# 계약 4 — 템플릿 조절기 블록 위생
# ==========================================================================
def test_control_block_has_no_forbidden_markup():
    """셸 소스의 조절기 블록에 목업 잔재 낱말·인라인 style·Jinja 값이 없다.

    목업 잔재 낱말은 **주석까지 포함해** 원문에서 본다(요약/실무 표면의 금지 낱말이 주석에
    남아 있으면 다음 이식 때 되살아난다). style/Jinja 는 주석 제거본에서 본다 — 규칙을 설명하는
    주석이 그 규칙 위반으로 잡히는 거짓 red 를 막는다.
    """
    raw_block = _control_block(_read(SHELL_TEMPLATE))
    for phrase in _MOCKUP_LEFTOVERS:
        assert phrase not in raw_block, f"조절기 블록에 목업 잔재 '{phrase}'"

    block = _control_block(_read_code(SHELL_TEMPLATE))
    assert re.search(r"\bstyle\s*=", block) is None, block
    assert "{{" not in block, block
    assert "{%" not in block, block


# ==========================================================================
# 계약 5 — 자산 핀은 사슬마다 한 값(리터럴은 단정하지 않는다)
# ==========================================================================
def test_shell_pins_are_single_per_chain():
    """셸의 자산 6개 각각 핀이 정확히 1개, 셸 사슬 4개는 한 값, 채널 사슬 2개는 한 값이다.

    두 사슬 사이의 관계와 핀 리터럴은 단정하지 않는다 — 값은 범프마다 바뀌고, 사슬은 소유
    작업이 달라 따로 움직인다. 저장소 전역 단일값은 기존 렌더 계약이 이미 잡는다.
    """
    shell = _read(SHELL_TEMPLATE)

    shell_chain = (SUMMARY_CSS, SUMMARY_JS, OPS_CSS, OPS_JS)
    channel_chain = (CHANNEL_CSS, CHANNEL_JS)

    per_asset = {asset: _pins_for(asset, shell) for asset in shell_chain + channel_chain}
    for asset, pins in per_asset.items():
        assert len(pins) == 1, f"{asset}: 셸 안 핀 값이 하나가 아니다 {sorted(pins)}"
        # 값 집합(set)만 보면 같은 핀으로 두 번 실린 링크(태그 중복)를 못 본다(리뷰 R1) — 출현 횟수도 센다.
        hits = re.compile(re.escape(asset) + _PIN_SUFFIX).findall(shell)
        assert len(hits) == 1, f"{asset}: 셸 안 링크가 {len(hits)}번 실렸다"

    shell_pins = set().union(*(per_asset[a] for a in shell_chain))
    assert len(shell_pins) == 1, f"셸 사슬 핀이 갈렸다 {sorted(shell_pins)}"

    channel_pins = set().union(*(per_asset[a] for a in channel_chain))
    assert len(channel_pins) == 1, f"채널 사슬 핀이 갈렸다 {sorted(channel_pins)}"
