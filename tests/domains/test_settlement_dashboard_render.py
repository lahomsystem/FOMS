"""SETTLE-DASH-01 M3: 정산 대시보드 **화면** 계약 테스트 (TDD, red→green).

M2(`test_settlement_dashboard_api.py`)가 권한 매트릭스·403·API 응답 형식을 이미 덮는다.
**이 파일은 그걸 중복하지 않는다.** 여기서 잠그는 것은 "허용 사용자가 실제로 받는 HTML 과
그 화면이 싣는 자산"이다 — 즉 M3 가 목업을 이식하면서 **놓치면 조용히 망가지는 것들**:

1. **자산 캐시 핀(`?v=`)** — 서비스워커가 static 을 cache-first 로 잡는다. 핀이 없거나
   저장소 안에서 갈라지면 배포해도 실기기가 옛 CSS/JS 를 계속 실행한다
   (project_sw_stale_js_version_bump). 검사 방식은 기존 관례를 그대로 쓴다
   (`tests/domains/test_as_dashboard_schedule_link_render.py:231-246`).
2. **렌더 차단 스크립트(perf G1)** — `<script src>` 에 `defer` 가 빠지면 ERP 탭 전체가 느려진다.
3. **외부 CDN 참조(perf G2)** — 차트는 자체 인라인 SVG 여야 한다. CDN 한 줄이 붙는 순간
   네트워크 stall 이 렌더 차단이 된다. G2 의 전역 가드는 **동기 `<script>` 만** 본다 —
   `<link>`·`@import`·JS 내부 fetch 는 사각이라 여기서 표면 단위로 막는다.
4. **인라인 스타일 / `JSON.parse('{{ ... |tojson }}')`** — 프로젝트 절대 규칙.
5. **목업 잔재** — 목업에는 시스템에 없는 데이터로 그린 카드가 있었다(월 매출 목표 미터,
   현금흐름 예측, MOCKUP 배지, 가정치 각주, 실재하지 않는 '해피콜' 단계 라벨). 스펙 §7 이
   전부 제거를 지시했다. 이식하다 남으면 **없는 숫자를 있는 것처럼 보여주는** 화면이 된다.
6. **권한 부제 오표기** — 목업 헤더는 "ADMIN·MANAGER 전용"이라고 적었지만 실제 허용 집합은
   CS/영업 STAFF 를 포함한다(AUTH-FINANCE-01). 화면이 거짓말을 하면 CS 담당자가
   "나는 못 보는 화면"으로 오해한다.
7. **암묵 drop 금지 표기** — 운영 실데이터에 완료일 미상 85건(4,410만원)·aging 미상 23건이
   있다. 집계에서 빠진 건을 화면이 말하지 않으면 **합계가 조용히 틀린 화면**이 된다.
8. **빈 상태** — 운영 `settlement_status` 는 **현재 전부 0** 이다(청구완료 0, 현금영수증 0,
   부서 차감 5종 전부 0). 0 을 차트로 그리면 빈 원/빈 막대가 나오고 사용자는 "고장"으로 읽는다.
   이 파일은 그 0 이 실제 모양이라는 것까지 실데이터 시드로 증명한다.

**검사 층위(의도적으로 둘)**
- *렌더*: 허용 사용자로 실제 GET 해서 나오는 HTML 을 본다. 템플릿이 include 되지 않거나
  `{% if %}` 로 통째 꺼지는 회귀는 소스 검사로는 안 잡힌다.
- *소스 리터럴*: 템플릿/CSS/JS 파일을 읽어 문자열을 확인한다(`tests/domains` 관례 —
  `test_as_dashboard_schedule_link_render.py:185-229`, `test_page_local_defer_contract.py`).
  JS 는 서버 렌더에 안 나오므로 이쪽으로만 잡을 수 있다.

**프래그먼트로 보는 이유**: 목업 잔재 문구 검사는 `?view=fragment` + `X-FOMS-ERP-SHELL: 1`
응답(정산 화면이 소유한 마크업)만 본다. 전체 문서에는 공용
`templates/partials/shared/layout_scripts.html:1719` 의 "예정된 일정이 없습니다" 가 섞여 들어와
정산과 무관한 거짓 red 가 난다. 프래그먼트에는 정산 body + `erp_sub_nav.html` 만 들어오고
둘 다 금지 문구를 갖고 있지 않다(작성 시점 실측).

테스트 데이터 규율: 존재하지 않는 FK id 를 만들지 않는다 — 실제 `Order` 를 시드한다
(SQLite 는 FK 를 강제하지 않아 로컬만 통과하고 PG 레인에서 터진다). docs/ 는 읽지 않는다
(CI-DOCSCOPE-01) — 목업 HTML 도 docs/ 아래라 이 파일은 열지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# --- 권한 actor · 로그인 헬퍼 SSOT 재사용 --------------------------------------
# 복제 금지: AUTH-FINANCE-01 이 확정한 허용 actor 와 사용자 생성/로그인 헬퍼를 그대로 쓴다.
from tests.domains.test_auth_finance import (  # noqa: E402
    _ALLOWED_ACTORS,
    _login,
    _make_user,
)

# --- M1 집계 시드 헬퍼 재사용 ---------------------------------------------------
from tests.domains.test_settlement_aggregation import _money, _seed_order  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]

PAGE_URL = "/erp/settlement"
API_URL = "/api/settlement/aggregates"

#: ERP 셸 프래그먼트 요청 계약(`foms/services/common/erp_navigation_contract.py:86-93`).
#: 헤더가 없으면 전체 문서가 와서 "정산 화면이 소유한 마크업"만 보려던 검사가 통째로 어긋난다.
_SHELL_HEADERS = {"X-FOMS-ERP-SHELL": "1"}
_FRAGMENT_URL = f"{PAGE_URL}?view=fragment"

#: M3 가 만드는 화면 소스 4종. 계약 검사(외부 CDN·금지 패턴)는 **이 표면 안에서만** 한다.
BODY_TEMPLATE = "templates/cs/partials/settlement_dashboard_body.html"
FULL_TEMPLATE = "templates/cs/settlement_dashboard.html"
CSS_ASSET = "css/settlement/settlement-dashboard.css"
JS_ASSET = "js/settlement/dashboard.js"

_TEMPLATE_SOURCES = (BODY_TEMPLATE, FULL_TEMPLATE)
_STATIC_ASSETS = (CSS_ASSET, JS_ASSET)
_ALL_SETTLEMENT_SOURCES = _TEMPLATE_SOURCES + tuple(f"static/{a}" for a in _STATIC_ASSETS)

#: 스펙 §7 이 목업에서 **빼라고 한** 것들의 흔적. 하나라도 남으면 화면이 없는 데이터를
#: 있는 것처럼 보여준다.
#:   "MOCKUP"  — 목업 배지
#:   "예정"    — 월 매출 목표 미터 / 현금흐름 30일 예측에 붙어 있던 미구현 배지
#:   "해피콜"  — 정산 단계 집합에 없는 라벨(라벨은 API `stages[].label` 을 그대로 쓴다)
#:   "가정치"  — 목업 각주
_MOCKUP_LEFTOVERS = ("MOCKUP", "예정", "해피콜", "가정치")

#: 화면이 **서버 렌더 시점에** 갖고 있어야 하는 앵커. JS 가 채우기 전에도 자리가 있어야
#: 한다 — fetch 가 실패해도 "빈 카드"가 아니라 "무엇이 비었는지"가 보여야 하기 때문이다.
#: 목록은 M3 구현자(F1)와 **착수 전에 합의한 계약**이다 — 테스트가 앵커를 발명하면 영구 red 가
#: 되고, 구현이 앵커를 발명하면 계약이 사문이 된다.
_REQUIRED_ANCHORS = {
    "완료일 미상 각주(암묵 drop 금지)": "data-settlement-unknown-completion",
    "aging 미상 표기": "data-settlement-aging-unknown",
    "정산 처리 현황 빈 상태": 'data-settlement-empty="settlement_status"',
    "aging 빈 상태": 'data-settlement-empty="aging"',
    "채널 빈 상태": 'data-settlement-empty="channels"',
    "단계 빈 상태": 'data-settlement-empty="stages"',
    "fetch 실패 표시": "data-settlement-error",
    "권한 거부 표시(403 전용)": "data-settlement-denied",
    "로딩 표시": "data-settlement-loading",
    "granularity 토글(일)": 'data-settlement-granularity="day"',
    "granularity 토글(주)": 'data-settlement-granularity="week"',
    "granularity 토글(월)": 'data-settlement-granularity="month"',
    "전월 비교 토글": "data-settlement-compare",
    "누적 보기 토글": "data-settlement-cumulative",
    "탭(요약)": 'data-settlement-tab="summary"',
    "탭(실무)": 'data-settlement-tab="ops"',
    "탭(분석)": 'data-settlement-tab="analytics"',
}

#: JS 가 차트/표를 마운트하는 호스트 id(서버 렌더). 목업의 `#kpis`·`#stages`·`#tt` 같은
#: 일반 id 를 그대로 쓰면 공용 ERP 문서 안에서 다른 화면과 충돌한다 — 접두어를 계약으로 박는다.
_SECTION_HOST_IDS = (
    "foms-settlement-root",
    "foms-settle-kpis",
    "foms-settle-main-chart",
    "foms-settle-main-table",
    "foms-settle-aging-chart",
    "foms-settle-stages",
    "foms-settle-channel-bar",
    "foms-settle-channel-legend",
    "foms-settle-settle-status",
    "foms-settle-tooltip",
)

#: 스텁(M2)이 이미 심어 둔 루트 계약. M3 이식이 통째로 갈아엎으면서 지우면 JS 가 화면을
#: 못 찾고 API URL 도 잃는다.
_ROOT_ANCHORS = ('data-foms-settlement-dashboard="1"', "data-aggregates-url=")

#: 목업 CSS 를 네임스페이스한 루트 클래스. 목업의 `.card`/`.grid`/`.badge`/`.legend` 는
#: Bootstrap 5·erp-pro.css 와 정면충돌한다.
_CSS_NAMESPACE_CLASS = "foms-settle"

#: 전역을 덮어쓰는 bare 선택자. 정산 CSS 는 ERP 공용 문서에 얹히므로 여기서 `body`/`:root`/`*`
#: 를 건드리면 **다른 화면까지** 색·폰트·박스모델이 바뀐다.
_BARE_GLOBAL_SELECTOR_RE = re.compile(r"(?m)^\s*(:root|html|body|\*)\s*(?:,|\{)")

#: 자산 참조 뒤 `?v=` 핀을 뽑는다. `filename='...css') }}?v=20260831a` 처럼 사이에
#: 따옴표/괄호/중괄호/공백만 끼는 기존 관례를 그대로 받는다
#: (test_as_dashboard_schedule_link_render.py:240).
_PIN_SUFFIX = r"['\"\s\}\)]*\?v=([A-Za-z0-9._-]+)"

#: 외부 호스트 참조. `www.w3.org` 만 예외다 — 인라인 SVG 의 `xmlns`/`xlink` 네임스페이스
#: URI 는 네트워크 요청이 아니라 식별자다(그것까지 막으면 SVG 를 못 그린다).
_EXTERNAL_URL_RE = re.compile(r"https?://(?!www\.w3\.org[/\"'])[^\s\"'<>()]+")

_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(.*?)\1[^>]*>", re.I | re.S)
_STYLE_ATTR_RE = re.compile(r"\bstyle\s*=\s*['\"]")

#: 탭 셸 계약(SETTLE-TABS-01). `(탭 키, 버튼 id, pane id, 눈에 보이는 라벨)` 4쌍이 한 줄에
#: 모여 있어야 "버튼은 고쳤는데 pane 은 안 고친" 반쪽 변경이 red 로 드러난다. 라벨은 사용자가
#: 이 화면을 부르는 이름이라 계약이다 — 문서·인수인계가 전부 이 이름으로 지칭한다.
_TABS = (
    ("summary", "foms-settle-tab-summary", "foms-settle-pane-summary", "요약"),
    ("ops", "foms-settle-tab-ops", "foms-settle-pane-ops", "실무"),
    ("analytics", "foms-settle-tab-analytics", "foms-settle-pane-analytics", "분석"),
    ("channel", "foms-settle-tab-channel", "foms-settle-pane-channel", "네이버 정산"),
)
_DEFAULT_TAB = "summary"

#: 탭 4(채널·네이버 정산)는 **ADMIN·회계팀만** 본다(NAVER-SETTLE-01 §1). 서버가 마크업째
#: 빼므로 그 밖의 허용 사용자에게는 탭이 3개다. 두 수를 따로 못박아, 게이트가 조용히
#: 열리거나(전원 4탭) 조용히 닫히는(ADMIN 도 3탭) 회귀를 양쪽에서 잡는다.
_TABS_WITHOUT_CHANNEL = tuple(t for t in _TABS if t[0] != "channel")
_CHANNEL_TAB_ID = "foms-settle-tab-channel"
_CHANNEL_PANE_ID = "foms-settle-pane-channel"

#: 탭 2·3 을 채울 작업이 **안쪽만** 건드려야 하는 자리. 셸이 소유한 pane 의 `role`/`aria-*`/
#: `hidden` 배선과 내용물의 경계를 여기서 못박는다.
_TAB_MOUNT_IDS = ("foms-settle-ops-mount", "foms-settle-analytics-mount")

_TAB_BUTTON_RE = re.compile(r"<button\b[^>]*\brole=\"tab\"[^>]*>(.*?)</button>", re.S)
_TAB_PANEL_RE = re.compile(r"<div\b[^>]*\brole=\"tabpanel\"[^>]*>", re.S)
#: bare `hidden` 속성. `s-hidden` 클래스와 헷갈리지 않게 앞에 공백을 요구한다.
_HIDDEN_ATTR_RE = re.compile(r"\shidden(\s|/?>)")

#: 저장소 전역 핀 스캔 대상(기존 관례와 동일한 제외 목록).
_PIN_SCAN_EXCLUDE = {".git", "node_modules", ".superpowers", "docs"}


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _read(rel: str) -> str:
    """저장소 상대 경로 파일을 읽는다. 없으면 **사람이 읽는 red** 로 죽인다.

    Args:
        rel: 저장소 루트 기준 상대 경로.

    Returns:
        파일 내용.
    """
    path = _ROOT / rel
    assert path.exists(), f"M3 산출물이 없다: {rel}"
    return path.read_text(encoding="utf-8", errors="ignore")


#: Jinja/HTML/JS 주석. 금지 **패턴** 검사는 "코드가 무엇을 하는가"를 봐야 하므로 주석은
#: 걷어낸다 — M2 스텁의 `{# ... JSON.parse('{{ ... |tojson }}') 금지 #}` 처럼 **규칙을
#: 설명하는 주석**이 그 규칙 위반으로 잡히는 거짓 red 를 막는다(실제로 그렇게 red 가 났다).
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.S)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
#: 줄 **처음**에 오는 `//` 만 지운다. `'https://...'` 같은 문자열 안의 `//` 까지 지우면
#: 외부 호스트 참조가 검사에서 사라진다 — 가드가 스스로 눈을 가리는 셈이라 하지 않는다.
_JS_LINE_COMMENT_RE = re.compile(r"(?m)^\s*//.*$")


def _strip_comments(text: str) -> str:
    """주석(Jinja/HTML/JS)을 걷어낸 사본을 돌려준다(금지 패턴 검사 전처리)."""
    text = _JINJA_COMMENT_RE.sub(" ", text)
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _JS_BLOCK_COMMENT_RE.sub(" ", text)
    return _JS_LINE_COMMENT_RE.sub(" ", text)


def _read_code(rel: str) -> str:
    """파일을 읽고 주석을 제거한 본문을 돌려준다."""
    return _strip_comments(_read(rel))


def _login_allowed(client, role: str = "ADMIN", team: str | None = None):
    """정산 열람이 허용된 사용자로 로그인한다(기본 ADMIN)."""
    _login(client, _make_user(role=role, team=team))


def _cut_balanced_div(text: str, needle: str) -> str:
    """`needle` 을 담은 `<div>` 요소를 **짝이 맞는 닫는 태그까지** 통째로 걷어낸다.

    비탐욕 정규식으로는 첫 `</div>` 에서 끊겨 안쪽 자식이 남는다 — 그러면 "제외했다"고
    믿는 검사가 사실은 절반만 제외한 채 통과한다.

    Args:
        text: 대상 HTML/템플릿 원문.
        needle: 대상 요소의 여는 태그 안에 있는 문자열(보통 `id="..."`).

    Returns:
        해당 요소가 제거된 사본. `needle` 이 없으면 원문 그대로.
    """
    at = text.find(needle)
    if at < 0:
        return text
    start = text.rfind("<div", 0, at)
    if start < 0:
        return text
    depth = 0
    i = start
    while i < len(text):
        if text.startswith("<div", i):
            depth += 1
            i += 4
            continue
        if text.startswith("</div>", i):
            depth -= 1
            i += 6
            if depth == 0:
                return text[:start] + " " + text[i:]
            continue
        i += 1
    return text[:start]


def _without_channel_surface(text: str) -> str:
    """탭 4(채널·네이버 정산)가 소유한 마크업을 걷어낸 사본을 돌려준다.

    채널 표면에는 "정산 **예정**일" 이 정당하게 나온다 — 네이버 정산 API 의
    ``settleExpectDate`` 축을 가리키는 도메인 용어이지 목업이 미구현 카드에 달아 둔
    "예정" 배지가 아니다. 목업 잔재 검사를 채널 표면에까지 적용하면 **맞는 화면을 틀렸다고
    말하는** 계약이 되므로 이 표면만 덜어내고 본다. 대신 채널 표면 안에서 "예정" 이
    "정산 예정일" 이외의 자리에 쓰이지 않는다는 것은
    ``tests/domains/test_settlement_channel_render.py`` 가 따로 못박는다 — 검사를 없앤 게
    아니라 소유를 옮긴 것이다.

    Args:
        text: 렌더 HTML 또는 템플릿 원문.

    Returns:
        채널 탭 버튼과 채널 pane 이 제거된 사본.
    """
    out = re.sub(
        r'<button\s[^>]*\sid="%s".*?</button>' % re.escape(_CHANNEL_TAB_ID),
        " ",
        text,
        flags=re.S,
    )
    return _cut_balanced_div(out, f'id="{_CHANNEL_PANE_ID}"')


def _fragment_html(client) -> str:
    """ERP 셸 **프래그먼트**로 정산 화면을 받아 온다(정산이 소유한 마크업만).

    Args:
        client: Flask test client (로그인 완료 상태여야 한다).

    Returns:
        렌더된 HTML 본문.
    """
    resp = client.get(_FRAGMENT_URL, headers=_SHELL_HEADERS)
    assert resp.status_code == 200, (resp.status_code, resp.get_data(as_text=True)[:400])
    return resp.get_data(as_text=True)


def _full_html(client) -> str:
    """직접 GET(새로고침) 경로의 **전체 문서**를 받아 온다."""
    resp = client.get(PAGE_URL)
    assert resp.status_code == 200, (resp.status_code, resp.get_data(as_text=True)[:400])
    return resp.get_data(as_text=True)


def _script_tag_containing(html: str, needle: str) -> str:
    """`needle` 을 포함하는 `<script src>` 태그 원문을 잘라낸다.

    Args:
        html: 검사 대상 HTML/템플릿 원문.
        needle: 태그 안에 있어야 하는 문자열(보통 자산 경로).

    Returns:
        매칭된 `<script ...>` 태그 문자열.

    Raises:
        AssertionError: 해당 스크립트 태그가 없을 때.
    """
    for match in _SCRIPT_TAG_RE.finditer(html):
        if needle in match.group(0):
            return match.group(0)
    raise AssertionError(f"script 태그를 찾지 못했다: {needle}")


def _pins_for(asset: str, text: str) -> set[str]:
    """`text` 안에서 `asset` 에 붙은 `?v=` 핀 값을 모두 모은다."""
    return set(re.compile(re.escape(asset) + _PIN_SUFFIX).findall(text))


def _attr(tag: str, name: str) -> str | None:
    """열린 태그 문자열에서 속성 값을 뽑는다(없으면 None)."""
    match = re.search(rf'\b{re.escape(name)}\s*=\s*"([^"]*)"', tag)
    return match.group(1) if match else None


def _tab_buttons(html: str) -> list[tuple[str, str]]:
    """`role="tab"` 버튼을 문서 순서대로 `(열린 태그, 안쪽 내용)` 으로 돌려준다."""
    found = []
    for match in _TAB_BUTTON_RE.finditer(html):
        whole = match.group(0)
        found.append((whole[: whole.index(">") + 1], match.group(1)))
    return found


def _tab_panels(html: str) -> list[str]:
    """`role="tabpanel"` 요소의 열린 태그를 문서 순서대로 돌려준다."""
    return [match.group(0) for match in _TAB_PANEL_RE.finditer(html)]


def _js_function_body(js: str, name: str) -> str:
    """`function <name>(...) { ... }` 의 본문을 중괄호 균형으로 잘라낸다.

    문자열 매칭이 아니라 **함수 단위**로 보기 위한 헬퍼다. "파일 어딘가에 그 단어가 있다"
    수준의 검사는 리팩터에 무력하고, 정작 잘못된 자리에 배선해도 green 이 난다.
    주석은 `_read_code` 가 이미 걷어낸 상태를 전제한다(주석 속 중괄호로 어긋나지 않게).

    Args:
        js: 주석이 제거된 JS 원문.
        name: 함수 이름.

    Returns:
        중괄호 안쪽 본문 문자열.

    Raises:
        AssertionError: 함수 정의나 닫는 중괄호를 찾지 못했을 때.
    """
    start = js.find(f"function {name}(")
    assert start >= 0, f"{name}() 정의를 찾지 못했다"
    open_at = js.find("{", start)
    depth = 0
    for i in range(open_at, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[open_at + 1:i]
    raise AssertionError(f"{name}() 본문이 닫히지 않았다")


def _repo_pin_scan_sources() -> list[Path]:
    """핀 일치 검사용 저장소 파일 목록(기존 관례와 동일한 제외 규칙)."""
    return [
        p
        for ext in ("*.html", "*.js", "*.py")
        for p in _ROOT.glob(f"**/{ext}")
        if not any(part in _PIN_SCAN_EXCLUDE for part in p.parts)
    ]


# ==========================================================================
# 계약 10 — 산출물 실재
# ==========================================================================
@pytest.mark.parametrize("rel", [f"static/{CSS_ASSET}", f"static/{JS_ASSET}"])
def test_settlement_assets_exist(rel):
    """전용 CSS/JS 가 스펙이 정한 경로에 실재한다.

    경로가 흔들리면 템플릿 링크·서비스워커 캐시 키·핀 계약이 전부 따로 논다.
    `templates/settlement/`·`foms/web/settlement/` 는 닫힌집합이라 금지지만
    `static/css/settlement/`·`static/js/settlement/` 는 새로 만들어도 된다(브리프 §5.9).
    """
    assert (_ROOT / rel).exists(), f"{rel} 가 없다"


@pytest.mark.parametrize("rel", [f"static/{CSS_ASSET}", f"static/{JS_ASSET}"])
def test_settlement_assets_are_not_empty(rel):
    """자산이 빈 파일이 아니다 — 링크만 걸고 내용이 없으면 화면은 그대로 스텁이다."""
    assert len(_read(rel).strip()) > 200, f"{rel} 가 사실상 비어 있다"


# ==========================================================================
# 계약 1 — 자산 캐시 핀 (`?v=`)
# ==========================================================================
@pytest.mark.parametrize("asset", _STATIC_ASSETS)
def test_settlement_assets_are_pinned_in_template(asset):
    """템플릿의 CSS/JS 링크에 `?v=` 핀이 붙어 있다.

    서비스워커가 static 을 cache-first 로 잡으므로 핀이 없으면 배포해도 실기기가 옛 자산을
    계속 쓴다(project_sw_stale_js_version_bump). 형식은 기존 관례 그대로
    (`templates/cs/partials/as_dashboard_body.html:18-21,629-632`).
    """
    source = "".join(_read_code(rel) for rel in _TEMPLATE_SOURCES)

    assert asset in source, f"{asset} 링크가 정산 템플릿에 없다"
    pins = _pins_for(asset, source)
    assert pins, f"{asset} 링크에 ?v= 핀이 없다"


@pytest.mark.parametrize("asset", _STATIC_ASSETS)
def test_settlement_asset_pins_are_single_repo_wide(asset):
    """자산 하나당 `?v=` 핀이 저장소 전역에서 **정확히 하나**다.

    두 곳에서 다른 핀을 걸면 어느 한쪽이 항상 stale 을 만든다. 검사 방식은 기존 핀 계약
    (`test_as_dashboard_schedule_link_render.py:231-246`)과 동일하다.
    """
    pattern = re.compile(re.escape(asset) + _PIN_SUFFIX)
    pins = {
        pin
        for path in _repo_pin_scan_sources()
        for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
    }

    assert len(pins) == 1, f"{asset}: 핀 불일치/부재 {sorted(pins)}"


@pytest.mark.parametrize("asset", _STATIC_ASSETS)
def test_rendered_fragment_carries_pinned_assets(client, app, asset):
    """실제 렌더된 프래그먼트 HTML 에도 핀이 붙은 링크가 실린다.

    템플릿 소스에만 있고 렌더에 안 나오는 경우(조건부 include 로 꺼짐)를 잡는다.
    프래그먼트에도 실려야 한다 — 첫 진입이 셸 탭 스왑이면 head 가 없어서 FOUC 가 난다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert asset in html, f"{asset} 링크가 프래그먼트 렌더에 없다"
    assert _pins_for(asset, html), f"{asset} 렌더 링크에 ?v= 핀이 없다"


def test_full_document_render_also_carries_pinned_assets(client, app):
    """새로고침(전체 문서) 경로에서도 두 자산이 핀과 함께 실린다."""
    _login_allowed(client)

    html = _full_html(client)

    for asset in _STATIC_ASSETS:
        assert asset in html, f"{asset} 링크가 전체 문서 렌더에 없다"
        assert _pins_for(asset, html), f"{asset} 전체 문서 링크에 ?v= 핀이 없다"


# ==========================================================================
# 계약 2 — defer (perf G1)
# ==========================================================================
def test_dashboard_script_tag_is_deferred_in_template():
    """정산 JS `<script>` 에 `defer` 가 있다(렌더 차단 금지, perf G1).

    전역 가드(`tests/performance/test_perf_regression_guard.py::
    test_no_new_render_blocking_scripts`)도 같은 것을 보지만, 그쪽은 **allowlist 에
    항목을 추가하면 통과한다.** 이 화면에 한해서는 예외를 허용하지 않는다.
    """
    source = "".join(_read_code(rel) for rel in _TEMPLATE_SOURCES)

    tag = _script_tag_containing(source, JS_ASSET)
    assert re.search(r"\bdefer\b", tag), tag


def test_dashboard_script_tag_is_deferred_in_rendered_fragment(client, app):
    """렌더 결과의 `<script>` 태그에도 `defer` 가 살아 있다."""
    _login_allowed(client)

    tag = _script_tag_containing(_fragment_html(client), JS_ASSET)

    assert re.search(r"\bdefer\b", tag), tag


def test_settlement_surface_adds_no_synchronous_script():
    """정산 표면이 추가한 `<script src>` 는 전부 defer/async/module 이다.

    자기 자산 하나만 보는 게 아니라 **이 화면이 새로 들이는 모든 스크립트**를 본다 —
    차트 라이브러리를 몰래 하나 더 붙이는 회귀를 같이 막는다.
    """
    for rel in _TEMPLATE_SOURCES:
        for match in _SCRIPT_TAG_RE.finditer(_read_code(rel)):
            tag = match.group(0)
            deferred = re.search(r"\bdefer\b|\basync\b|type\s*=\s*['\"]module['\"]", tag)
            assert deferred, f"{rel}: 렌더 차단 스크립트 {tag}"


# ==========================================================================
# 계약 3 — 외부 CDN 0 (perf G2)
# ==========================================================================
@pytest.mark.parametrize("rel", _ALL_SETTLEMENT_SOURCES)
def test_settlement_sources_reference_no_external_host(rel):
    """템플릿·CSS·JS 어디에도 외부 호스트 참조가 없다(perf G2).

    차트는 자체 인라인 SVG 다 — 차트 라이브러리 CDN 도입 금지. 전역 G2 가드는 **동기
    `<script>` 태그만** 보므로 `<link>`·`@import`·JS 안의 `fetch('https://...')` 는
    사각이다. 여기서 표면 단위로 전부 막는다.

    예외는 `www.w3.org` 뿐 — 인라인 SVG 의 `xmlns`/`xlink` 는 네트워크 요청이 아니라
    네임스페이스 식별자다.
    """
    hits = _EXTERNAL_URL_RE.findall(_read_code(rel))

    assert not hits, f"{rel}: 외부 호스트 참조 {hits[:5]}"


def test_no_chart_library_globals_in_dashboard_js():
    """차트 라이브러리 전역(Chart.js·D3·ECharts 등)에 기대지 않는다 — 자체 SVG 렌더.

    self-host 로 들여와도 마찬가지다: 외부 URL 검사만으로는 `static/js/vendor/` 에 복사해 둔
    라이브러리를 못 잡는다. 전역 사용 흔적 자체를 막는다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    for banned in (r"new\s+Chart\s*\(", r"\bd3\.select\b", r"\becharts\.", r"\bHighcharts\.",
                   r"new\s+ApexCharts\s*\("):
        assert not re.search(banned, js), f"차트 라이브러리 사용 흔적: {banned}"
    assert "createElementNS" in js or "<svg" in js, "자체 SVG 렌더 흔적이 없다"


# ==========================================================================
# 계약 4 — 인라인 스타일 금지
# ==========================================================================
@pytest.mark.parametrize("rel", _TEMPLATE_SOURCES)
def test_settlement_templates_have_no_inline_style_attribute(rel):
    """정산 템플릿에 `style="` 속성이 없다(프로젝트 절대 규칙).

    공용 `cs/layout.html` 은 body/컨테이너에 옛 인라인 스타일을 갖고 있다(레거시). 그래서
    렌더 결과 전체가 아니라 **M3 가 소유한 템플릿 파일**만 본다 — 남의 빚으로 red 를 내지
    않으면서 새 빚은 확실히 막는다.
    """
    hits = _STYLE_ATTR_RE.findall(_read_code(rel))

    assert not hits, f"{rel}: 인라인 style 속성 {len(hits)}개"


@pytest.mark.parametrize("rel", _TEMPLATE_SOURCES)
def test_settlement_templates_have_no_inline_style_block(rel):
    """`<style>` 블록도 없다 — 목업 `<style>` 은 CSS 파일로 통째 이식돼야 한다."""
    assert "<style" not in _read_code(rel).lower(), f"{rel}: 인라인 <style> 블록"


# ==========================================================================
# 계약 5 — 금지 패턴 (Jinja→JS 직접 파싱)
# ==========================================================================
@pytest.mark.parametrize("rel", _TEMPLATE_SOURCES)
def test_settlement_templates_do_not_inline_parse_jinja_json(rel):
    """`JSON.parse('{{ ... }}')`·`|tojson` 직접 파싱이 없다.

    따옴표/개행이 섞인 값 하나로 스크립트 블록 전체가 SyntaxError 로 죽는다. 초기 페이로드는
    `data-*` 속성으로 넘긴다(스텁의 `data-aggregates-url` 이 그 형태다).
    """
    source = _read_code(rel)

    assert "JSON.parse('{{" not in source
    assert 'JSON.parse("{{' not in source
    assert not re.search(r"\|\s*tojson", source), f"{rel}: |tojson 직접 사용"


@pytest.mark.parametrize("host_id", _SECTION_HOST_IDS)
def test_section_host_ids_are_server_rendered(client, app, host_id):
    """JS 마운트 지점이 서버 렌더 마크업에 있다(스크립트가 만들어 내지 않는다).

    JS 가 컨테이너까지 만들면 fetch 실패 시 카드 자체가 사라져 "화면이 안 뜬다"가 되고,
    셸 스왑 재init 도 붙을 곳을 잃는다. 접두어(`foms-settle*`)가 계약인 이유는 상수 주석 참조.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert f'id="{host_id}"' in html, host_id


def test_generic_mockup_ids_are_not_reused(client, app):
    """목업의 일반 id(`#kpis`·`#tt`)를 그대로 쓰지 않는다 — 공용 ERP 문서에서 충돌한다."""
    _login_allowed(client)

    html = _fragment_html(client)

    for generic in ('id="kpis"', 'id="tt"', 'id="stages"', 'id="chart"'):
        assert generic not in html, f"충돌 위험 id 재사용: {generic}"


def test_dashboard_js_marks_mount_idempotently():
    """JS 가 마운트 멱등 표식을 남긴다 — 스왑/재실행에 두 번 그리지 않는다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "settlement-mounted" in js or "settlementMounted" in js, (
        "마운트 멱등 표식(data-settlement-mounted)이 없다"
    )


def test_settlement_css_is_namespaced_and_touches_no_global_selector():
    """정산 CSS 가 루트 클래스 아래로 네임스페이스돼 있고 전역 선택자를 안 건든다.

    목업 `<style>` 을 그대로 이식하면 `.card`/`.grid`/`.badge`/`.legend` 와 `:root` 토큰이
    Bootstrap 5·`erp-pro.css` 를 덮어써서 **다른 ERP 화면까지** 무너진다. 이 화면은 공용
    문서 안에 얹히는 조각이라는 것이 계약이다.
    """
    css = _read_code(f"static/{CSS_ASSET}")

    assert _CSS_NAMESPACE_CLASS in css, f".{_CSS_NAMESPACE_CLASS} 네임스페이스가 없다"
    bare = _BARE_GLOBAL_SELECTOR_RE.findall(css)
    assert not bare, f"전역 bare 선택자 {sorted(set(bare))} — .{_CSS_NAMESPACE_CLASS} 아래로 넣어라"


def test_root_keeps_data_attribute_contract(client, app):
    """루트 요소가 `data-foms-settlement-dashboard` + `data-aggregates-url` 을 유지한다.

    JS 가 화면을 찾는 훅이자 API URL 전달 수단이다(하드코딩 URL 금지). M3 이식이 스텁
    마크업을 통째로 갈아엎으면서 지우는 회귀를 잡는다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    for anchor in _ROOT_ANCHORS:
        assert anchor in html, anchor
    assert API_URL in html, "집계 API URL 이 마크업에 실려야 한다"


# ==========================================================================
# 계약 6 — 목업 잔재 부재 (스펙 §7)
# ==========================================================================
@pytest.mark.parametrize("phrase", _MOCKUP_LEFTOVERS)
def test_rendered_fragment_has_no_mockup_leftovers(client, app, phrase):
    """렌더된 정산 프래그먼트에 목업 잔재 문구가 없다.

    - "MOCKUP"/"가정치": 목업 배지·각주.
    - "예정": 월 매출 목표 미터·현금흐름 30일 예측에 붙어 있던 미구현 배지. 두 카드는
      근거 데이터가 시스템에 아예 없어서 스펙 §7 이 제거를 지시했다.
    - "해피콜": 정산 단계 집합에 없는 라벨. 단계 라벨은 API `stages[].label` 을 그대로
      써야 한다(하드코딩 금지).

    프래그먼트만 보는 이유는 모듈 docstring 참조(전체 문서에는 공용 layout_scripts 의
    "예정된 일정이 없습니다" 가 섞인다).

    채널(네이버 정산) 탭 표면은 덜어내고 본다 — 사유는 `_without_channel_surface` 참조
    (그 표면의 "정산 예정일" 은 네이버 API 축 이름이지 목업 배지가 아니다).
    """
    _login_allowed(client)

    html = _without_channel_surface(_strip_comments(_fragment_html(client)))

    assert phrase not in html, f"목업 잔재 '{phrase}' 가 렌더에 남아 있다"


@pytest.mark.parametrize("phrase", _MOCKUP_LEFTOVERS)
def test_settlement_sources_have_no_mockup_leftovers(phrase):
    """소스에도 남아 있지 않다 — `{% if %}` 뒤에 숨은 잔재까지 잡는다.

    렌더 검사는 "지금 이 조건에서 안 보인다"만 말한다. 조건이 바뀌면 되살아나므로
    템플릿·JS 소스 자체에서 리터럴을 없앤다.
    """
    for rel in (*_TEMPLATE_SOURCES, f"static/{JS_ASSET}"):
        assert phrase not in _without_channel_surface(_read_code(rel)), (
            f"{rel}: 목업 잔재 '{phrase}'"
        )


# ==========================================================================
# 계약 7 — 권한 부제 교정
# ==========================================================================
def test_header_subtitle_does_not_claim_admin_manager_only(client, app):
    """헤더 부제가 "ADMIN·MANAGER 전용" 이라고 쓰지 않는다.

    실제 허용 집합은 ADMIN·MANAGER **+ STAFF(CS)·STAFF(SALES)** 다(AUTH-FINANCE-01,
    `test_settlement_dashboard_api.py::test_settlement_policy_fields_match_finance`).
    목업 문구를 그대로 이식하면 화면이 자기 권한을 잘못 말한다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert not re.search(r"ADMIN[^<>]{0,40}전용", html), "ADMIN 한정 표기가 남아 있다"
    assert not re.search(r"MANAGER[^<>]{0,40}전용", html), "MANAGER 한정 표기가 남아 있다"


def test_permission_note_names_the_full_allowed_set(client, app):
    """권한을 언급한다면 허용 집합 전체를 말한다 — CS/영업을 빼놓지 않는다.

    권한 문구를 아예 안 쓰는 것도 허용한다(부제 자체가 선택). 다만 "ADMIN"/"MANAGER" 를
    적어 놓고 CS·영업만 누락하는 **반쪽 표기**는 목업 오표기의 잔재이므로 red 다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    if "ADMIN" in html or "MANAGER" in html:
        assert ("CS" in html) or ("영업" in html), "허용 집합에서 CS/영업이 누락됐다"


# ==========================================================================
# 계약 8 — 암묵 drop 금지 표기 (완료일 미상 / aging 미상)
# ==========================================================================
def test_unknown_completion_anchor_is_server_rendered(client, app):
    """완료일 미상(`unknown_completion`)을 표기할 자리가 서버 렌더에 존재한다.

    운영 실데이터에 85건 44,109,370원이 있다. 이 건들은 기간 버킷 어디에도 안 들어가므로
    화면이 말하지 않으면 **합계가 조용히 틀린다**(project_dashboard_cap_before_python_filter
    와 같은 계열의 사고). 앵커는 JS 가 채우기 전에도 있어야 한다 — fetch 가 실패했을 때
    "빈 카드"가 아니라 "무엇이 비었는지"가 보여야 한다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert _REQUIRED_ANCHORS["완료일 미상 각주(암묵 drop 금지)"] in html


def test_aging_unknown_anchor_is_server_rendered(client, app):
    """aging 미상(`aging_unknown`, 운영 23건 31,839,170원)도 별도 표기 자리가 있다."""
    _login_allowed(client)

    html = _fragment_html(client)

    assert _REQUIRED_ANCHORS["aging 미상 표기"] in html


def test_dashboard_js_binds_every_api_key():
    """JS 가 API 응답의 **모든 최상위 키**를 실제로 참조한다(조용한 누락 차단).

    특히 `unknown_completion`·`aging_unknown` 을 안 읽으면 앵커만 있고 영원히 비어 있는
    각주가 된다 — 화면상으로는 "미상 0건"과 구별되지 않아 아무도 못 알아챈다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    for key in (
        "kpi",
        "buckets",
        "prev_buckets",
        "aging",
        "aging_unknown",
        "channels",
        "settlement_status",
        "stages",
        "unknown_completion",
        "overpaid_total",
    ):
        assert key in js, f"API 키 '{key}' 를 JS 가 쓰지 않는다"


def test_seeded_unknown_completion_is_reported_by_api(client, app):
    """완료일 없는 실제 주문을 시드하면 API 가 그 건을 `unknown_completion` 으로 돌려준다.

    화면 각주가 **실제로 채울 값이 있는 자리**임을 데이터로 증명한다(존재하지 않는 FK 를
    쓰지 않고 실 Order 행을 만든다). 여기가 0 이면 각주 앵커 테스트는 의미가 없어진다.
    """
    _seed_order(completion=None, sd=_money(items_total=1_234_000, deposit=0))
    _login_allowed(client)

    body = client.get(f"{API_URL}?month_from=2026-08&month_to=2026-08").get_json()

    unknown = body["data"]["unknown_completion"]
    assert unknown["count"] >= 1, unknown
    assert unknown["amount"] >= 1_234_000, unknown


# ==========================================================================
# 계약 9 — 빈 상태 (정산 처리 현황이 전부 0)
# ==========================================================================
def test_settlement_status_empty_state_anchor_is_server_rendered(client, app):
    """정산 처리 현황 카드에 빈 상태 앵커가 서버 렌더로 존재한다.

    운영 실데이터가 **현재 전부 0** 이다. 0 을 도넛/막대로 그리면 빈 원이 나오고 사용자는
    고장으로 읽는다. 빈 상태는 JS 가 켜기 전에도 마크업에 있어야 한다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert _REQUIRED_ANCHORS["정산 처리 현황 빈 상태"] in html


def test_settlement_status_empty_state_has_human_readable_text(client, app):
    """빈 상태 자리에 사람이 읽는 한글 안내가 들어 있다(빈 div 로 때우지 않는다)."""
    _login_allowed(client)

    html = _fragment_html(client)

    marker = _REQUIRED_ANCHORS["정산 처리 현황 빈 상태"]
    start = html.find(marker)
    assert start >= 0, marker
    block = html[start:start + 600]
    assert re.search(r"[가-힣]{2,}", block), f"빈 상태 안내 문구가 없다: {block[:200]!r}"


def test_empty_state_notice_is_not_an_autodismissed_alert():
    """빈 상태·상시 안내를 `.alert` 로 만들지 않는다(5초 뒤 자동으로 닫힌다).

    부득이 `.alert` 를 쓴다면 `data-foms-no-autodismiss` 가 함께 있어야 한다
    (project_alert_autodismiss_trap).
    """
    body = _read_code(BODY_TEMPLATE)

    for match in re.finditer(r'class="[^"]*\balert\b[^"]*"', body):
        tag_start = body.rfind("<", 0, match.start())
        tag_end = body.find(">", match.end())
        tag = body[tag_start:tag_end + 1]
        assert "data-foms-no-autodismiss" in tag, f"자동닫힘 .alert: {tag[:160]}"


def test_operational_settlement_status_really_is_all_zero(client, app):
    """정산 blob 없는 평범한 완료 주문만 있으면 `settlement_status` 는 전부 0 이다.

    빈 상태가 **예외 처리가 아니라 현재의 정상 모양**임을 실데이터 시드로 못박는다.
    (`pending_count` 만 모집단 크기를 따라 올라간다 — 그건 "청구 안 된 건 수"라서 0 이
    아니어도 카드의 나머지가 전부 0 이면 빈 상태로 그려야 한다.)
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=3_000_000, deposit=1_000_000))
    _seed_order(completion="2026-08-11", sd=_money(items_total=2_000_000, deposit=2_000_000))
    _login_allowed(client)

    status = client.get(
        f"{API_URL}?month_from=2026-08&month_to=2026-08"
    ).get_json()["data"]["settlement_status"]

    assert status["issued_count"] == 0, status
    assert status["cash_receipt_requested"] == 0, status
    assert status["cash_receipt_issued"] == 0, status
    assert status["as_billing_paid_count"] == 0, status
    assert status["as_billing_paid_amount"] == 0, status
    assert status["deductions_by_department"], "부서 목록 자체는 있어야 한다(5종 고정)"
    for dept in status["deductions_by_department"]:
        assert dept["amount"] == 0 and dept["count"] == 0, dept
    assert status["pending_count"] == 2, status


def test_dashboard_js_toggles_empty_state_on_all_zero():
    """JS 가 "전부 0" 을 감지해 빈 상태를 켜는 분기를 갖고 있다.

    앵커만 있고 JS 가 영원히 숨겨 두면 실데이터(전부 0)에서 빈 카드가 그대로 남는다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert "settlement-empty" in js or "settlementEmpty" in js, (
        "JS 가 빈 상태 앵커를 조작하지 않는다"
    )


# ==========================================================================
# 필터바 (스펙 §7 / 브리프 §6)
# ==========================================================================
@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_filter_bar_exposes_all_granularities(client, app, granularity):
    """일/주/월 토글 3개가 렌더된다 — 서버 재버킷 재조회의 진입점."""
    _login_allowed(client)

    html = _fragment_html(client)

    assert f'data-settlement-granularity="{granularity}"' in html


def test_filter_bar_exposes_compare_and_cumulative_toggles(client, app):
    """전월 비교선·누적 보기 토글이 렌더된다.

    비교선은 `prev_buckets` 를 같은 축에 겹쳐 그리고(서버 데이터), 누적은 클라이언트
    누산이라 재조회가 없다 — 두 동작의 앵커가 다르다는 것까지 계약이다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert _REQUIRED_ANCHORS["전월 비교 토글"] in html
    assert _REQUIRED_ANCHORS["누적 보기 토글"] in html


def test_granularity_change_refetches_with_server_param():
    """granularity 토글이 **서버 재조회**를 건다(클라 재버킷 금지).

    주/월 버킷 규칙은 M1 서버가 SSOT 다. 클라가 일 버킷을 스스로 합치면 주 경계·타임존
    규칙이 두 벌이 되어 조용히 갈린다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert "granularity" in js
    assert "month_from" in js and "month_to" in js, "재조회가 범위 파라미터를 실어야 한다"


# ==========================================================================
# 차트 렌더 불변식 — 정적 검사가 원래 못 보던 축(M3 구현 중 jsdom 하네스가 실제로 잡은 2건)
# ==========================================================================
def test_prev_buckets_can_be_shorter_than_buckets(client, app):
    """전월 비교 시리즈는 현재 시리즈보다 **짧을 수 있다** — 달력이 그렇게 만든다.

    2026-08 은 6주에 걸치고 2026-07 은 5주다. 서버는 각 달의 실제 주 수만큼 버킷을 내므로
    `buckets`(6) 와 `prev_buckets`(5) 의 길이가 다르다. 목업 렌더러는 비교 시리즈 길이를
    그대로 축 길이로 썼기 때문에 이 상태에서 축이 밀린다.

    이 테스트는 **그 위험이 실재한다는 사실 자체**를 고정한다. 나중에 누가 M1 에서
    `prev_buckets` 를 패딩해 길이를 맞추기로 하면 여기가 red 가 나고, 그때 화면의 길이
    가드를 지워도 되는지 의식적으로 판단하게 된다(조용히 전제가 바뀌는 것을 막는다).
    월을 고정 리터럴로 쓰므로 오늘 날짜와 무관하게 결정적이다.
    """
    _seed_order(completion="2026-08-03", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion="2026-08-31", sd=_money(items_total=1_000_000, deposit=0))
    _seed_order(completion="2026-07-01", sd=_money(items_total=1_000_000, deposit=0))
    _login_allowed(client)

    data = client.get(
        f"{API_URL}?month_from=2026-08&month_to=2026-08&granularity=week"
    ).get_json()["data"]

    assert len(data["buckets"]) == 6, [b["key"] for b in data["buckets"]]
    assert len(data["prev_buckets"]) == 5, [b["key"] for b in data["prev_buckets"]]
    assert len(data["buckets"]) != len(data["prev_buckets"]), (
        "길이가 같아졌다면 화면의 비교 시리즈 길이 가드를 지워도 되는지 재검토하라"
    )


def test_dashboard_js_bounds_comparison_series_to_axis_groups():
    """비교 라인을 그릴 때 **축 그룹 수까지만** 그린다(시리즈가 더 길어도 넘지 않는다).

    `prev_buckets` 가 `buckets` 보다 길거나 짧을 수 있으므로(위 테스트가 그 사실을 고정),
    루프 상한이 시리즈 길이 하나뿐이면 점이 축 밖으로 나가거나 축이 밀린다.
    리팩터로 이 루프를 다시 쓸 때 **두 상한을 함께 두는 성질**을 유지하라 — 변수 이름은
    자유롭게 바꿔도 된다(이 검사는 조건식의 구성만 본다).
    """
    body = _js_function_body(_read_code(f"static/{JS_ASSET}"), "columnChart")

    # 루프 본문에 `if (...) {}` 가 끼어도 어긋나지 않게, `pts.push` 앞의 마지막 `for(...)`
    # 헤더를 잡는다(본문을 정규식으로 넘겨짚지 않는다).
    push_at = body.find("pts.push")
    assert push_at > 0, "비교 라인 점을 만드는 pts.push 를 찾지 못했다"
    headers = list(re.finditer(r"for\s*\(([^)]*)\)", body[:push_at]))
    assert headers, "비교 라인 점을 만드는 루프를 찾지 못했다"
    condition = headers[-1].group(1)
    assert "values.length" in condition, condition
    assert re.search(r"<\s*g\b", condition), (
        f"루프 상한에 축 그룹 수(g)가 없다 — 시리즈 길이만 보면 축을 넘는다: {condition}"
    )


def test_dashboard_js_draws_no_series_bar_for_zero_value():
    """값이 0 이면 **시리즈 색 막대는** 그리지 않는다 — 0 을 매출색으로 칠하면 거짓 표기다.

    목업은 모든 막대에 최소 높이(1.5px)를 줬다. 서열 차트(aging)에서는 그 하한이
    "적지만 있다"는 거짓 신호를 만든다 — 운영 aging 은 `D91_PLUS` 6억 대 나머지 수백만이라
    가장 크게 왜곡되는 자리다. 그래서 0 은 시리즈 색으로 그리지 않고, 양수는 최소 높이를
    보장한다. 시계열 차트만 `zeroFloor` 로 **중립색 baseline 스텁**을 켠다(아래 테스트).
    """
    js = _read_code(f"static/{JS_ASSET}")

    height = re.search(r"\bbh\s*=\s*([^;]+);", js)
    assert height, "막대 높이 계산을 찾지 못했다"
    assert re.search(r">\s*0\s*\?", height.group(1)), (
        f"0 값을 걸러내는 삼항 가드가 없다: {height.group(1)}"
    )
    assert re.search(r"Math\.max\(\s*[1-9]", height.group(1)), (
        f"양수 막대의 최소 높이 보장이 없다: {height.group(1)}"
    )
    assert re.search(r"if\s*\(\s*bh\s*>\s*0\s*\)", js), (
        "높이 0 일 때 시리즈 색 path 를 건너뛰는 가드가 없다"
    )


def test_zero_floor_stub_is_opt_in_and_neutral_colored():
    """시계열 차트만 0 버킷에 중립색 baseline 스텁을 깐다(`zeroFloor`).

    스텁이 없으면 완료 0건인 날의 칸이 SVG 에서 통째로 사라진다. 운영처럼 완료가 드문
    달에는 31칸 중 대부분이 비어 막대의 리듬이 무너지고, 전폭을 잇는 전월 비교 라인만
    남아 **막대 차트가 라인 차트로 읽힌다**(사용자 지적, 2026-08-31).

    스텁 색은 시리즈 색이 아니라 `--s-zero-bar` 다 — 매출 0 을 매출색으로 칠하지 않는다.
    옵트인이라 aging 카드의 0 억제 계약은 그대로 유지된다.
    """
    js = _read_code(f"static/{JS_ASSET}")
    css = _read_code(f"static/{CSS_ASSET}")

    assert re.search(r"else\s+if\s*\(\s*cfg\.zeroFloor\s*\)", js), (
        "0 버킷 baseline 스텁이 cfg.zeroFloor 옵트인으로 갈려 있지 않다"
    )
    stub = re.search(r"else\s+if\s*\(\s*cfg\.zeroFloor\s*\)\s*\{([^}]*)\}", js)
    assert stub and "--s-zero-bar" in stub.group(1), (
        f"스텁이 중립 토큰(--s-zero-bar)을 쓰지 않는다: {stub.group(1) if stub else None}"
    )
    assert "--s-zero-bar:" in css, "--s-zero-bar 토큰 선언이 CSS 에 없다"

    # aging 은 켜지 않는다 — 켜면 위 테스트가 지키는 거짓 신호 방지가 무너진다.
    aging = re.search(r"columnChart\(ctx,\s*host,\s*\{[^}]*?twoLineX:\s*true.*?\}\);", js, re.S)
    assert aging, "aging 차트 호출을 찾지 못했다"
    assert "zeroFloor" not in aging.group(0), "aging 차트에 zeroFloor 가 켜져 있다"


# ==========================================================================
# fetch 무음 실패 금지 (브리프 §5.6)
# ==========================================================================
def test_error_anchor_is_server_rendered(client, app):
    """fetch 실패를 사람이 읽게 표시할 자리가 마크업에 있다(무음 실패 금지)."""
    _login_allowed(client)

    html = _fragment_html(client)

    assert _REQUIRED_ANCHORS["fetch 실패 표시"] in html


def test_error_denied_and_loading_are_three_distinct_nodes(client, app):
    """실패·권한거부·로딩이 **서로 다른 노드**다 — 한 자리에 세 상태를 욱여넣지 않는다.

    403 은 "서버 오류"가 아니라 "당신은 이 화면을 못 본다"이고, 로딩은 실패가 아니다.
    한 노드를 돌려 쓰면 fetch 실패 문구가 로딩 중에 잠깐 번쩍이거나, 권한 거부가
    "일시적 오류, 새로고침하세요"로 표시돼 사용자가 무한히 재시도한다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    for key in ("fetch 실패 표시", "권한 거부 표시(403 전용)", "로딩 표시"):
        assert _REQUIRED_ANCHORS[key] in html, key
    # 같은 요소에 두 상태를 겹쳐 달지 않았는지 — 각 앵커가 서로 다른 태그에 있어야 한다.
    positions = {
        key: html.find(_REQUIRED_ANCHORS[key])
        for key in ("fetch 실패 표시", "권한 거부 표시(403 전용)", "로딩 표시")
    }
    assert len(set(positions.values())) == 3, positions


def test_dashboard_js_distinguishes_403_from_generic_error():
    """JS 가 403 을 일반 오류와 분리해 처리한다(권한 거부 전용 문구)."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "403" in js, "403 분기가 없다"
    assert "settlement-denied" in js or "settlementDenied" in js, (
        "권한 거부 앵커를 JS 가 건드리지 않는다"
    )


def test_stage_labels_are_not_hardcoded_in_surface():
    """단계 라벨을 화면이 하드코딩하지 않는다 — API `stages[].label` 을 그대로 쓴다.

    목업은 존재하지 않는 '해피콜' 단계를 그려 놓았다. 라벨 SSOT 는 서버(`STAGE_LABELS`)다.
    화면이 자기 목록을 들고 있으면 단계가 바뀔 때 두 벌이 조용히 갈린다.
    """
    js = _read_code(f"static/{JS_ASSET}")
    body = _read_code(BODY_TEMPLATE)

    # 서버 단계 코드를 키로 한 라벨 사전을 클라가 들고 있으면 안 된다.
    for code in ("RECEIVED", "HAPPYCALL", "MEASURE", "DRAWING", "PRODUCTION", "CONSTRUCTION"):
        assert code not in js, f"JS 가 단계 코드 목록을 들고 있다: {code}"
    assert "해피콜" not in js and "해피콜" not in body
    assert "label" in js, "stages[].label 을 읽는 흔적이 없다"


def test_dashboard_js_guards_fetch_with_try_catch_and_success_check():
    """fetch 가 try/catch + `success` 검증을 거친다.

    세션 만료 시 HTML 302 가 오면 `res.json()` 이 던진다. catch 없이 두면 화면이 영원히
    로딩 상태로 남고 아무 메시지도 안 뜬다(P1-13/P1-18 불변식).
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert "fetch(" in js, "집계 API fetch 가 없다"
    assert re.search(r"\btry\s*\{", js), "try 블록이 없다"
    assert re.search(r"\bcatch\s*\(", js), "catch 블록이 없다"
    assert re.search(r"\.success\b|\['success'\]|\[\"success\"\]", js), (
        "data.success 검증이 없다"
    )
    assert "settlement-error" in js or "settlementError" in js, (
        "실패를 표시할 앵커를 JS 가 건드리지 않는다"
    )


# ==========================================================================
# 프래그먼트 재진입 (perf G4 / 브리프 §5.7)
# ==========================================================================
def test_dashboard_js_has_singleton_init_guard():
    """전역 초기화 싱글톤 가드가 있다.

    이 화면은 ERP 셸 프래그먼트로도 들어온다. 스왑 때 `DOMContentLoaded` 는 다시 안 뜨고
    스크립트 본문만 재실행되므로, 가드가 없으면 전역 listener 가 스왑마다 쌓인다.
    이름 형식은 perf 가드의 탐지기(`tools/perf/perf_scan.py:279-285`)와 같은 것을 요구한다 —
    거기서 인식되지 않으면 G4 가 이 파일을 baseline 에 등재하라고 요구하게 된다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert re.search(
        r"window\.__[A-Za-z0-9_$]*(?:BOUND|INIT|INITIALIZED|LOADED|MOUNTED)", js
    ), "window.__*_BOUND 류 싱글톤 가드가 없다"


def test_dashboard_js_reinitializes_on_fragment_swap():
    """셸 프래그먼트 스왑 이벤트로 재초기화한다 — 탭을 다시 열면 화면이 다시 그려져야 한다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "foms:erp-shell-fragment-swapped" in js, (
        "프래그먼트 스왑 재init 훅이 없다(탭 재진입 시 빈 화면)"
    )


# ==========================================================================
# 계약 12 — 탭 3종 셸 (SETTLE-TABS-01)
# ==========================================================================
# 이 화면은 **한 라우트 · 한 화면**을 유지한 채 요약(경영진) · 실무(경리·수금) · 분석으로
# 갈린다. 새 메뉴도 새 URL 도 만들지 않는 것이 전제라, 셸이 무너지면 세 화면이 통째로
# 사라진다. 여기서 잠그는 것은 **접근성 배선**(role/aria 짝)과 **폭 0 함정**(숨은 pane 에서
# 그린 차트는 빈 SVG 가 된다) 두 축이다.
def test_tab_bar_renders_four_tabs_with_expected_wiring(client, app):
    """ADMIN 에게 탭이 정확히 4개이고, 각 버튼이 진짜 `<button role="tab">` 로 aria 배선을 갖췄다.

    `<div>` 에 클릭 핸들러를 다는 방식은 키보드·스크린리더에서 통째로 사라진다.
    버튼 순서·id·라벨까지 고정하는 이유는 `_TABS` 주석 참조. 4번째(채널·네이버 정산)는
    ADMIN·회계팀 전용이라 기본 로그인(ADMIN)에서만 이 수가 나온다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert 'role="tablist"' in html, "tablist 컨테이너가 없다"
    tabs = _tab_buttons(html)
    assert len(tabs) == 4, [tag for tag, _ in tabs]
    for (key, tab_id, pane_id, label), (tag, inner) in zip(_TABS, tabs):
        assert _attr(tag, "id") == tab_id, tag
        assert _attr(tag, "data-settlement-tab") == key, tag
        assert _attr(tag, "aria-controls") == pane_id, tag
        assert _attr(tag, "aria-selected") in ("true", "false"), tag
        assert label in inner, (label, inner)


def test_settlement_page_is_closed_outside_accounting(client, app):
    """회계팀·관리자가 아니면 정산 화면 자체가 403 이다(사용자 결정 2026-09-03).

    그 전에는 STAFF+CS 가 요약·실무·분석 3탭을 봤고 채널 탭만 더 좁았다. 지금은 화면
    전체가 회계 축이라, 여기서 200 이 나오면 전사 매출·미수 총액이 다시 열린 것이다.
    감추기(`hidden`/CSS)가 아니라 **서버가 안 그리는 것**까지 계약이다.
    """
    _login_allowed(client, role="STAFF", team="CS")

    resp = client.get(_FRAGMENT_URL, headers=_SHELL_HEADERS)

    assert resp.status_code == 403, resp.status_code
    html = resp.get_data(as_text=True)
    for needle in (
        _CHANNEL_TAB_ID,
        _CHANNEL_PANE_ID,
        "settlement-channel.css",
        "settlement/channel.js",
        'id="foms-settlement-root"',
    ):
        assert needle not in html, f"정산 마크업/자산이 회계팀 밖으로 샜다: {needle}"


def test_summary_tab_is_the_default_selected_tab(client, app):
    """기본 선택은 요약 탭 하나뿐이고, 나머지 pane 은 `hidden` 으로 닫혀 있다.

    서버 렌더 시점에 이미 정해져 있어야 한다 — JS 가 켜기 전에 세 pane 이 한꺼번에 보이면
    화면이 3배 길이로 번쩍인 뒤 접힌다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    selected = [
        _attr(tag, "data-settlement-tab")
        for tag, _ in _tab_buttons(html)
        if _attr(tag, "aria-selected") == "true"
    ]
    assert selected == [_DEFAULT_TAB], selected
    root_tag = re.search(r'<div\b[^>]*id="foms-settlement-root"[^>]*>', html)
    assert root_tag, "루트 태그를 찾지 못했다"
    assert _attr(root_tag.group(0), "data-settlement-active-tab") == _DEFAULT_TAB, root_tag.group(0)
    for (key, _tab_id, pane_id, _label), tag in zip(_TABS, _tab_panels(html)):
        assert _attr(tag, "id") == pane_id, tag
        assert bool(_HIDDEN_ATTR_RE.search(tag)) is (key != _DEFAULT_TAB), tag


def test_every_tab_has_a_matching_tabpanel(client, app):
    """탭 ↔ pane 이 id/`aria-controls`/`aria-labelledby` 로 **양방향** 1:1 이다.

    한쪽만 고치면 스크린리더가 엉뚱한 영역을 읽거나 "이름 없는 탭 패널"이 된다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    panels = _tab_panels(html)
    assert len(panels) == 4, panels
    for (key, tab_id, pane_id, _label), tag in zip(_TABS, panels):
        assert _attr(tag, "id") == pane_id, tag
        assert _attr(tag, "data-settlement-pane") == key, tag
        assert _attr(tag, "aria-labelledby") == tab_id, tag
    controls = {_attr(tag, "aria-controls") for tag, _ in _tab_buttons(html)}
    assert controls == {_attr(tag, "id") for tag in panels}, controls


def test_tab_bar_sits_above_the_filter_bar_and_carries_the_meta(client, app):
    """탭바가 필터바보다 위에 오고, 권한 부제·기준 시각은 탭줄 **안**(오른쪽 메타)에 산다.

    2026-09-02 폭·높이 개편: 별도 `.s-strip` 한 줄(40px)을 없애고 탭줄 오른쪽으로 합쳤다 —
    크롬이 본문 시작을 400px 아래로 밀던 문제. 스트립이 되살아나면 그 줄이 다시 생긴다.
    기준 시각 훅(`data-settlement-stamp`)은 JS `collectEls()` 배선이라 이름을 못 바꾼다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    tablist_at = html.index('role="tablist"')
    filterbar_at = html.index('class="s-filterbar"')
    assert tablist_at < filterbar_at, "탭바가 필터바 아래로 내려갔다"
    assert 'class="s-strip"' not in html, "옛 스트립 줄이 되살아났다 — 탭줄 메타로 합쳐라"
    meta_at = html.index('class="s-tabs-meta"')
    stamp_at = html.index("data-settlement-stamp")
    assert tablist_at < meta_at < stamp_at < filterbar_at, "권한 부제·기준 시각이 탭줄 메타 밖에 있다"


def test_focus_mode_controls_are_wired_but_are_not_tabs(client, app):
    """집중 모드 버튼·복귀 바가 있고, 둘 다 탭(role=tab / data-settlement-tab)이 아니다.

    탭으로 잡히면 ←→ 순회와 activateTab 이 집중 모드 버튼을 4번째 탭으로 삼는다.
    JS 쪽은 `[data-settlement-focus]`·`[data-settlement-focus-exit]` 를 클릭 위임으로 받고
    Esc 는 전역 리스너 1회 배선이다(setFocusMode).
    """
    _login_allowed(client)

    html = _fragment_html(client)
    js = _read_code(f"static/{JS_ASSET}")

    focus_tag = re.search(r"<button\b[^>]*data-settlement-focus\b[^>]*>", html)
    assert focus_tag, "집중 모드 버튼이 없다"
    assert 'role="tab"' not in focus_tag.group(0), focus_tag.group(0)
    assert "data-settlement-tab" not in focus_tag.group(0), focus_tag.group(0)
    assert "data-settlement-focus-exit" in html, "집중 모드 복귀 버튼이 없다"
    assert html.index("data-settlement-focusbar") < html.index('role="tablist"'), "복귀 바는 탭줄 위에 온다"
    for hook in ("data-settlement-focus", "data-settlement-focus-exit", "foms-settle-focus", "Escape"):
        assert hook in js, f"JS 가 '{hook}' 를 배선하지 않는다"


def test_summary_pane_owns_the_existing_screen(client, app):
    """요약 전용 화면(그리드 · 각주)이 통째로 요약 pane **안에** 들어갔다.

    하나라도 pane 밖에 남으면 실무 탭에서도 그 조각이 그대로 보인다 — 탭을 나눈 의미가
    사라지고, 화면이 "정산 요약 수치를 늘 달고 다니는 실무 화면"이 된다.

    상태 3종(로딩·실패·권한거부)은 **의도적으로 예외**다: 집계 fetch 는 요약·분석이
    공유하는 하나의 요청이라 그 결과 표시도 pane 밖 공유물이다
    (`test_shared_state_nodes_live_outside_every_pane` 가 그 자리를 따로 잠근다).
    """
    _login_allowed(client)

    html = _fragment_html(client)

    block = html[html.index('id="foms-settle-pane-summary"'):html.index('id="foms-settle-pane-ops"')]
    for anchor in (
        "data-settlement-grid",
        'id="foms-settle-kpis"',
        'id="foms-settle-main-chart"',
        'class="s-foot"',
    ):
        assert anchor in block, f"요약 pane 밖에 남았다: {anchor}"
    # 툴팁은 반대로 pane **밖**이어야 한다 — position:fixed 라 탭마다 복제하면 안 된다.
    assert 'id="foms-settle-tooltip"' not in block
    assert html.index('id="foms-settle-tooltip"') > html.index('id="foms-settle-pane-analytics"')


def test_shared_state_nodes_live_outside_every_pane(client, app):
    """로딩·실패·권한거부 3종이 pane **밖**(루트 직속)에 있다 — 어느 탭에서도 보이게.

    집계 fetch 는 요약·분석 두 탭이 공유하는 **하나의** 요청이다. 이 노드들이 요약 pane
    안에 있으면, 분석 탭을 보는 중에 fetch 가 실패해도 실패 문구가 `display:none` 인 pane
    안에서 켜져 **분석 탭은 아무 설명 없이 빈 화면**이 된다 — 이 저장소가 금지하는 무음
    실패다(브리프 §5.6). 자리는 필터바 아래 · 첫 pane 위여야 한다(읽는 순서 = 발생 순서).
    """
    _login_allowed(client)

    html = _fragment_html(client)

    first_pane = html.index('id="foms-settle-pane-summary"')
    filterbar = html.index('class="s-filterbar"')
    for key in ("로딩 표시", "fetch 실패 표시", "권한 거부 표시(403 전용)"):
        at = html.find(_REQUIRED_ANCHORS[key])
        assert at >= 0, key
        assert filterbar < at < first_pane, f"{key} 가 pane 안(또는 필터바 위)에 있다: {at}"
    # 재시도 버튼도 같이 나와야 한다 — 실패 문구만 보이고 되돌릴 길이 없으면 막다른 길이다.
    assert html.find("data-settlement-retry") < first_pane


def test_non_ready_states_hide_both_period_tab_grids():
    """ready 가 아닌 동안에는 요약 그리드와 분석 그리드를 **둘 다** 감춘다.

    상태 노드를 pane 밖으로 옮긴 것만으로는 반쪽이다 — 분석 그리드를 그대로 두면 실패
    화면 위에 값 없는 빈 카드 6장이 같이 보인다("고장" 과 구분되지 않는다).
    """
    js = _read_code(f"static/{JS_ASSET}")

    body = _js_function_body(js, "showState")
    for els in ("ctx.els.grid", "ctx.els.analyticsGrid"):
        assert re.search(
            r"toggle\(\s*%s\s*,\s*kind\s*!==\s*['\"]ready['\"]\s*\)" % re.escape(els), body
        ), f"{els} 를 ready 기준으로 감추지 않는다: {body[:400]}"


@pytest.mark.parametrize("mount_id", _TAB_MOUNT_IDS)
def test_empty_tabs_expose_a_named_mount_point(client, app, mount_id):
    """탭 2·3 이 이름 있는 마운트 지점을 서버 렌더로 갖는다.

    내용을 채우는 쪽이 pane 자체(`role`/`aria-*`/`hidden`)를 건드리지 않고 **안쪽만**
    바꾸도록 경계를 마크업으로 준다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert f'id="{mount_id}"' in html, mount_id
    block = html[html.index(f'id="{mount_id}"'):]
    assert re.search(r"[가-힣]{2,}", block[:600]), "자리표시 안내 문구가 없다"


def test_filter_bar_is_shared_by_period_tabs_and_not_duplicated(client, app):
    """필터바는 pane **밖에 한 벌만** 있다(탭별 복제 금지).

    기간 스코프는 요약·분석이 공유하는 하나의 상태다. 복제하면 `aria-pressed` 짝이 두 벌이
    되어 탭을 오갈 때 조용히 갈리고, JS 의 `.s-filterbar`·`granButtons` 단일 배선도 깨진다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert html.count('class="s-filterbar"') == 1, "필터바가 여러 벌이다"
    for anchor in (
        'data-settlement-granularity="day"',
        'data-settlement-granularity="week"',
        'data-settlement-granularity="month"',
        "data-settlement-compare",
        "data-settlement-cumulative",
    ):
        assert html.count(anchor) == 1, f"{anchor} 가 {html.count(anchor)}개 — 복제됐다"
    assert html.index('class="s-filterbar"') < html.index('id="foms-settle-pane-summary"'), (
        "필터바가 요약 pane 안에 들어갔다 — 분석 탭에서 기간 필터가 사라진다"
    )


def test_filter_bar_is_hidden_on_the_ops_tab_only():
    """실무 탭에서만 필터바가 CSS 로 감춰진다(요약·분석은 그대로 쓴다).

    감추는 수단이 `s-hidden` 이 아니라 루트 속성 선택자인 것까지 계약이다 — `s-hidden` 은
    `showState()` 의 권한거부 분기가 쓰는 자리라, 겹쳐 쓰면 403 이 풀릴 때 탭 상태까지
    되돌아간다.
    """
    css = _read_code(f"static/{CSS_ASSET}")

    rule = re.search(r'\[data-settlement-active-tab="ops"\][^{]*\.s-filterbar\s*\{([^}]*)\}', css)
    assert rule, "실무 탭에서 필터바를 감추는 규칙이 없다"
    assert re.search(r"display\s*:\s*none", rule.group(1)), rule.group(1)
    for other in ("summary", "analytics"):
        assert not re.search(
            r'\[data-settlement-active-tab="%s"\][^{]*\.s-filterbar\s*\{[^}]*display\s*:\s*none' % other,
            css,
        ), f"{other} 탭에서도 필터바를 감추고 있다"
    assert re.search(r"\.s-pane\[hidden\]\s*\{[^}]*display\s*:\s*none", css), (
        "비활성 pane 을 감추는 규칙이 없다"
    )


def test_tab_activation_rerenders_charts_through_the_resize_render_path():
    """탭 활성화가 **리사이즈와 같은 렌더 경로**로 차트를 다시 그린다.

    숨은 pane 은 `display:none` 이라 안쪽 차트 호스트의 `clientWidth` 가 0 이고, 렌더러가
    `host.clientWidth || 400` 으로 폴백한다 — 그 사이에 그려진 차트는 **빈 차트가 아니라
    400px 로 눌린 차트**라서 눈에 덜 띈 채 그대로 남는다(폴백이 안 걸리는 좁은 폭에서는
    `pw <= 0` 조기반환으로 호스트가 비워진다). 어느 쪽이든 다음 리사이즈 전까지 스스로
    낫지 않는다. 실측: 분석 탭에서 창을 줄인 뒤 요약 탭으로 돌아오면 재렌더가 없을 때
    `svg width=400` vs 카드 폭 1006 이었다(2026-08-31, dev 5011 · 시드 707건).

    검사는 문자열 산탄이 아니라 **함수 단위**로 본다: `activateTab()` 이 (a) pane 의
    `hidden` 을 뒤집고 (b) 데이터가 있을 때 `renderAll(ctx)` 를 부르며, (c) 리사이즈 경로도
    같은 `renderAll` 을 쓴다 — 렌더 진입점이 두 벌로 갈라지면 한쪽만 고치는 회귀가 난다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    activate = _js_function_body(js, "activateTab")
    assert re.search(r"\.hidden\s*=", activate), f"pane 표시 전환이 없다: {activate[:200]}"
    assert "aria-selected" in activate, "선택 상태를 aria-selected 로 말하지 않는다"
    assert re.search(r"state\.data", activate), "데이터 없이 그리려 든다(빈 렌더)"
    assert re.search(r"renderAll\(\s*ctx\s*\)", activate), (
        "탭 활성화가 차트를 되그리지 않는다 — 숨은 pane 폭 0 때문에 빈 차트가 남는다"
    )
    resize = _js_function_body(js, "renderMountedRoots")
    assert re.search(r"renderAll\(\s*ctx\s*\)", resize), resize
    assert "renderMountedRoots" in _js_function_body(js, "onResize"), (
        "리사이즈와 탭 전환의 렌더 경로가 갈렸다"
    )


def test_arrow_keys_move_between_tabs_without_global_listeners():
    """←/→ 로 탭을 이동한다 — 그리고 그 배선이 루트 **안쪽** 위임이다.

    tablist 표준 키보드 패턴이다. 동시에 perf G4 규율이기도 하다: `document` 에 탭
    리스너를 달면 프래그먼트 스왑마다 전역 리스너가 쌓인다(이 파일의 싱글톤 가드는
    스왑 이벤트·resize 전용이다).
    """
    js = _read_code(f"static/{JS_ASSET}")

    keydown = _js_function_body(js, "onTabKeydown")
    assert "ArrowLeft" in js and "ArrowRight" in js, "좌우 화살표 이동이 없다"
    assert "activateTab(" in keydown, keydown[:200]
    assert "preventDefault" in keydown, "화살표 기본 동작(스크롤)을 막지 않는다"
    bind = _js_function_body(js, "bindControls")
    assert "onTabKeydown" in bind, "키보드 배선이 루트 위임 밖에 있다"
    assert re.search(r"ctx\.root\.addEventListener\(\s*['\"]keydown['\"]", bind), bind[:300]
    assert not re.search(r"document\.addEventListener\(\s*['\"](click|keydown)['\"]", js), (
        "탭/클릭 리스너를 document 에 달았다 — 스왑마다 누적된다(perf G4)"
    )


def test_tab_state_is_established_inside_the_per_root_mount():
    """탭 초기화가 `mount()` 안에서 일어난다 — 프래그먼트 스왑 재진입 규율과 같은 자리.

    셸이 루트를 통째로 갈아끼우면 탭 배선도 같이 사라진다. 기존 마운트 경로
    (`data-settlement-mounted` 표식 → `mountAll()`)를 그대로 타야 스왑 후에도 탭이 산다 —
    별도 전역 초기화를 만들면 그 경로만 스왑에서 빠진다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    mount_body = _js_function_body(js, "mount")
    assert "activateTab(" in mount_body, "마운트가 탭 초기 상태를 세우지 않는다"
    assert "bindControls(" in mount_body, mount_body[:200]
    assert "settlementMounted" in mount_body, "마운트 멱등 표식이 mount() 안에 없다"


# ==========================================================================
# 계약 11 — 허용 사용자 전원이 같은 화면을 받는다
# ==========================================================================
@pytest.mark.parametrize(
    "role,team", [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")]
)
def test_allowed_actors_receive_every_anchor(client, app, role, team):
    """허용 3종 actor(관리자·회계팀) 전원이 계약 앵커를 **전부** 갖춘 화면을 받는다.

    403 매트릭스는 M2(`test_settlement_dashboard_api.py`)가 덮으므로 중복하지 않는다.
    여기서 잡는 것은 "권한은 통과했는데 화면 일부가 역할별로 빠지는" 회귀다 — 정산 화면은
    역할별 분기가 없어야 한다(같은 집계를 같은 모양으로 본다).
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=300_000))
    _login(client, _make_user(role=role, team=team))

    html = _fragment_html(client)

    missing = [name for name, anchor in _REQUIRED_ANCHORS.items() if anchor not in html]
    assert not missing, (role, team, missing)


# ==========================================================================
# 계약 13 — 탭 3 · 분석 화면 (SETTLE-TABS-01 T3)
# ==========================================================================
# 분석 탭은 요약과 **같은 한 번의 fetch** 를 다른 축으로 본다. 여기서 잠그는 것은 네 가지다:
#   (a) 마운트가 실제로 채워졌는가(자리표시 <p> 가 남으면 "준비 중" 화면이 배포된다),
#   (b) 담당자 카드의 **키 부재 안전성**(STAFF payload 는 키가 통째로 없다),
#   (c) 라벨 SSOT(단계·부서 이름을 화면이 들고 있으면 안 된다),
#   (d) 집계 막대 램프가 **단건 출고가 램프와 다른 축**인가.
def _analytics_block(html: str) -> str:
    """분석 마운트 안쪽 마크업만 잘라낸다(다음 pane 또는 툴팁 앞까지).

    끝을 툴팁 하나로만 잡으면 분석 pane **뒤에 붙는 새 pane** 까지 "분석 탭 마크업"으로
    삼는다 — 실제로 탭 4(채널·네이버 정산)를 붙이자 그 pane 의 원장 버튼("수수료")이
    분석 탭 제외 계약을 red 로 만들었다. 경계는 분석 pane 이 끝나는 자리다.
    """
    start = html.index('id="foms-settle-analytics-mount"')
    ends = [
        at
        for at in (html.find(f'id="{_CHANNEL_PANE_ID}"'), html.find('id="foms-settle-tooltip"'))
        if at > start
    ]
    assert ends, "분석 블록의 끝을 찾지 못했다"
    return html[start:min(ends)]


#: 분석 탭 카드가 서버 렌더로 갖고 있어야 하는 앵커. 카드가 통째로 빠지는 회귀를 잡는다.
_ANALYTICS_ANCHORS = {
    "KPI 4종 호스트": 'id="foms-settle-an-kpis"',
    "채널 비교 막대": 'id="foms-settle-an-channel-bar"',
    "채널 비교 표": 'id="foms-settle-an-channel-table"',
    "담당자별 카드(권한 게이트)": "data-settlement-manager-card",
    "담당자별 막대": 'id="foms-settle-an-managers"',
    "단계별 막대": 'id="foms-settle-an-stages"',
    "부서별 차감 막대": 'id="foms-settle-an-deductions"',
    "수금 구성 상자": 'id="foms-settle-an-collect"',
    "미수 aging 막대": 'id="foms-settle-an-aging"',
    "AS 3분할": 'id="foms-settle-an-as"',
    "분석 그리드(상태 전환 대상)": "data-settlement-analytics-grid",
}

#: 목업이 그렸지만 **근거 데이터가 없어** 빼기로 한 것들(브리프 "제외 — 만들지도 속이지도 마라").
#:   연체 위험 스코어  — 근거 데이터 없음 + 행 단위(집계 전용 엔드포인트가 실어선 안 된다)
#:   팀 스코프        — 주문에 영업팀 축이 없다(`erp_owner_team_code` 는 워크플로 팀)
#:   수수료           — 네이버 수수료율 데이터가 없다
_EXCLUDED_MOCKUP_CARDS = ("연체 위험", "팀 스코프", "수수료")

#: 목업이 담당자·단계 카드에 박아 둔 **고정** 금액구간 범례. 실데이터에 맞지 않는 숫자라
#: 그대로 옮기면 색과 글자가 서로 다른 말을 한다(범례는 실제 경계에서 생성해야 한다).
_MOCKUP_FIXED_RAMP_LABELS = ("1,999만", "2,000~3,499만", "3,500~4,999만", "5,000만~")


def test_analytics_mount_is_populated_not_a_placeholder(client, app):
    """분석 마운트에 자리표시 문구가 아니라 실제 카드가 들어 있다."""
    _login_allowed(client)

    html = _fragment_html(client)
    block = _analytics_block(html)

    assert "s-pane-placeholder" not in block, "분석 탭에 '준비 중' 자리표시가 남아 있다"
    assert "분석 화면은 준비 중입니다" not in html
    # 실무 탭 자리표시는 아직 남아 있어도 된다(다른 작업 몫) — 분석만 본다.
    assert 'id="foms-settle-analytics-mount"' in html


@pytest.mark.parametrize("name,anchor", sorted(_ANALYTICS_ANCHORS.items()))
def test_analytics_cards_are_server_rendered(client, app, name, anchor):
    """분석 카드 앵커가 **서버 렌더** 마크업에 있다(JS 가 카드를 만들어 내지 않는다).

    JS 가 카드까지 만들면 fetch 실패 때 카드가 통째로 사라져 "화면이 안 뜬다" 가 된다.
    """
    _login_allowed(client)

    block = _analytics_block(_fragment_html(client))

    assert anchor in block, f"{name}: {anchor}"


def test_analytics_cards_carry_human_readable_titles(client, app):
    """카드마다 사람이 읽는 제목이 있다 — 값이 채워지기 전에도 무엇이 빈 칸인지 보인다."""
    _login_allowed(client)

    block = _analytics_block(_fragment_html(client))

    for title in ("채널 비교", "담당자별 매출", "단계별 파이프라인 금액",
                  "부서별 정산 차감", "수금 · 미수 현황", "AS · 정산 처리 현황"):
        assert title in block, title


def test_analytics_manager_card_guards_on_key_presence():
    """담당자 카드가 **키 부재**(STAFF payload)를 안전하게 처리한다.

    서버는 권한 밖 사용자에게 `managers`/`managers_total` 키를 **payload 에서 뺀다**
    (SPEC §13.6, `test_settlement_dashboard_api.py::test_manager_breakdown_is_stripped...`).
    그래서 화면이 만나는 것은 "값 0" 이 아니라 "키 없음" 이다 — 세 가지가 전부 필요하다:
      1) 키 존재 여부로 판정할 것(`data.managers.length` 로 바로 들어가면 던진다),
      2) 빈 카드가 아니라 **카드째** 감출 것,
      3) 그 뒤 코드가 실행되지 않도록 조기 반환할 것(뒷 카드까지 죽이지 않는다).
    """
    js = _read_code(f"static/{JS_ASSET}")

    body = _js_function_body(js, "renderAnalyticsManagers")
    assert "hasOwnProperty" in body, f"키 존재 판정이 없다: {body[:300]}"
    assert re.search(r"toggle\(\s*card\s*,", body), "카드째 감추지 않는다"
    guard = re.search(r"if\s*\(\s*!\s*granted\s*\)\s*return", body)
    assert guard, "권한 없음일 때 조기 반환이 없다"
    # 카드 자체를 감추기 **전에** managers 를 파고들지 않는다.
    assert body.index("hasOwnProperty") < body.index("data.managers"), body[:400]


def test_analytics_manager_card_is_hidden_until_data_grants_it(client, app):
    """서버 렌더 시점의 담당자 카드는 **감춰진 상태**로 나온다(fail-closed).

    JS 가 데이터를 받아 권한을 확인한 뒤에만 연다. 반대로 만들면(기본 노출 → 나중에 숨김)
    STAFF 화면에 빈 실적 카드가 한 번 번쩍인 뒤 사라진다.
    """
    _login_allowed(client)

    block = _analytics_block(_fragment_html(client))

    card = re.search(r'<div\b[^>]*data-settlement-manager-card[^>]*>', block)
    assert card, "담당자 카드 태그를 찾지 못했다"
    assert "s-hidden" in card.group(0), card.group(0)


def test_staff_payload_really_omits_the_manager_keys(client, app):
    """STAFF 응답에 `managers` 키가 실제로 **없다** — 화면 가드가 지키는 상황이 실재한다.

    가드만 있고 상황이 없으면 그 가드는 영영 검증되지 않는다(음성 대조군으로 ADMIN 을 같이
    본다 — ADMIN 에는 키가 있어야 가드가 카드를 여는 쪽도 살아 있음이 증명된다).
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=2_000_000, deposit=0))

    _login(client, _make_user(role="STAFF", team="ACCOUNTING"))
    staff = client.get(f"{API_URL}?month_from=2026-08&month_to=2026-08").get_json()["data"]
    assert "managers" not in staff and "managers_total" not in staff, sorted(staff)

    _login(client, _make_user(role="ADMIN"))
    admin = client.get(f"{API_URL}?month_from=2026-08&month_to=2026-08").get_json()["data"]
    assert admin["managers"], "대조군 실패 — ADMIN 에게도 담당자별 매출이 없다"
    assert admin["managers_total"]["count"] >= 1, admin["managers_total"]


def test_analytics_stage_and_department_labels_come_from_the_api():
    """단계·부서 라벨을 분석 화면이 하드코딩하지 않는다(SSOT = API `label`).

    목업의 부서 이름·순서는 실제(`SETTLEMENT_DEPARTMENT_OPTIONS`)와 다르고, 단계에는
    실재하지 않는 항목까지 있었다. 두 벌이 되면 서버가 바뀌어도 화면만 옛 이름을 말한다.
    """
    js = _read_code(f"static/{JS_ASSET}")
    block = _analytics_block(_read_code(BODY_TEMPLATE))
    # 검사는 **분석 렌더 함수 본문**으로 좁힌다. 'AS접수' 같은 문자열은 단계 라벨이면서
    # 동시에 정산 모집단 **상태** 이름이라(요약 KPI 부제가 그 뜻으로 쓴다) 파일 전체
    # 문자열 검사로는 뜻을 구분할 수 없다 — 단계 카드가 자기 목록을 들었는지만 본다.
    renderers = "".join(
        _js_function_body(js, name)
        for name in ("renderAnalyticsStages", "renderAnalyticsDeductions", "renderBarList")
    )

    # 부서 라벨 5종(= SETTLEMENT_DEPARTMENT_OPTIONS)이 코드에 리터럴로 있으면 안 된다.
    for label in ("도면", "공장(생산)", "시공팀", "고객"):
        assert label not in js, f"JS 가 부서 라벨을 들고 있다: {label}"
        assert label not in block, f"분석 마크업이 부서 라벨을 들고 있다: {label}"
    # 단계 라벨/코드도 마찬가지(요약 탭 계약과 같은 규율).
    for label in ("주문접수", "AS접수", "AS_RECEIVED", "RECEIVED"):
        assert label not in renderers, f"분석 렌더가 단계 라벨/코드를 들고 있다: {label}"
        assert label not in block, f"분석 마크업이 단계 라벨/코드를 들고 있다: {label}"
    assert "st.label" in renderers and "d.label" in renderers, "API label 을 읽는 흔적이 없다"


def test_aggregate_bar_ramp_is_a_separate_scale_from_single_order_edges():
    """집계 막대(담당자·단계)의 금액 램프가 **단건 출고가 램프와 다른 축**이다.

    `BUCKET_EDGES = [450, 700, 900]`(만원)은 **주문 한 건**의 출고가에 맞춘 경계다. 담당자
    합계·단계 합계는 자릿수가 한 단계 커서(실측 dev 시드: 담당자 7명 1,120만~1,808만) 같은
    경계를 재사용하면 **모든 막대가 최상단 색**이 된다 — 램프가 아무것도 말하지 않는 상태로
    조용히 통과한다. 그래서 (a) 별도 경계 함수가 있고 (b) 그 함수가 BUCKET_EDGES 를 안 쓰며
    (c) 범례 문구가 그 경계에서 **생성**된다(고정 문구면 색과 글자가 갈린다).
    """
    js = _read_code(f"static/{JS_ASSET}")

    edges = _js_function_body(js, "aggEdges")
    color = _js_function_body(js, "aggColor")
    legend = _js_function_body(js, "renderRampLegend")
    assert "BUCKET_EDGES" not in edges, f"단건 램프 경계를 그대로 쓴다: {edges}"
    assert "BUCKET_EDGES" not in color, f"단건 램프 경계를 그대로 쓴다: {color}"
    assert "AGG_RAMP_QUARTILES" in edges, edges
    # 범례는 경계 배열에서 문구를 만든다(하드코딩 라벨 금지).
    assert "edges[0]" in legend and "edges[2]" in legend, legend[:300]
    assert "BUCKET_LABELS" not in legend, "단건 램프 범례를 재사용한다"
    for fixed in _MOCKUP_FIXED_RAMP_LABELS:
        assert fixed not in js, f"목업 고정 범례가 남아 있다: {fixed}"
    # 두 램프가 실제로 다른 상수여야 한다(같은 배열을 가리키면 이름만 다른 것).
    assert re.search(r"var\s+AGG_RAMP_QUARTILES\s*=\s*\[", js), "집계 램프 경계 상수가 없다"
    assert re.search(r"var\s+BUCKET_EDGES\s*=\s*\[\s*450", js), "단건 램프 경계가 바뀌었다"


def test_analytics_kpi_deltas_come_from_prev_totals():
    """분석 KPI 4장의 증감이 서버가 준 `prev_totals` 에서 나온다(화면 추정 금지).

    이전 기간 스칼라를 화면이 다시 만들면(예: prev_buckets 재집계) 서버 합계와 조용히
    갈린다 — 특히 부서 차감은 버킷에 아예 없어서 만들어 낼 수조차 없다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    body = _js_function_body(js, "renderAnalyticsKpis")
    assert "prev_totals" in body, body[:300]
    assert "prev_buckets" not in body, "이전 구간을 버킷에서 다시 만든다"
    for key in ("revenue", "completed_count", "avg_shipping_price", "deduction_total"):
        assert key in body, f"prev_totals.{key} 를 안 쓴다"
    assert "deltaOf(" in body, "기존 델타 헬퍼를 재사용하지 않는다"


def test_analytics_reads_the_new_aggregate_keys():
    """분석 탭이 M2 확장 키를 실제로 읽는다 — 앵커만 있고 영원히 비는 카드를 막는다."""
    js = _read_code(f"static/{JS_ASSET}")

    for key in (
        "prev_totals",
        "managers",
        "managers_total",
        "collected_deposit",
        "collected_balance",
        "as_total_count",
        "as_billing_free_count",
        "as_billing_undecided_count",
    ):
        assert key in js, f"분석 탭이 API 키 '{key}' 를 안 쓴다"


def test_channel_average_guards_against_zero_count():
    """채널 '건당 평균' 이 0 건에서 나누지 않는다.

    `_build_channels` 는 데이터가 없어도 '일반' 행을 **항상** 낸다(0건 0원). 가드가 없으면
    NaN/Infinity 가 그대로 화면에 찍힌다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    body = _js_function_body(js, "renderAnalyticsChannels")
    assert re.search(r"count\s*>\s*0\s*\?", body), f"0건 가드가 없다: {body[-800:]}"
    assert "'—'" in body or '"—"' in body, "정의되지 않은 평균을 사람이 읽는 기호로 말하지 않는다"


def test_analytics_renders_through_the_single_render_entry_point():
    """분석 렌더가 `renderAll()` 안에 등록돼 있다(두 번째 진입점 금지).

    탭 활성화·리사이즈가 전부 renderAll 로 들어온다 — 분석만 따로 부르는 경로를 만들면
    그 경로만 재렌더에서 빠져 폭·기간 변경이 한쪽에만 반영된다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    render_all = _js_function_body(js, "renderAll")
    assert re.search(r"renderAnalytics\(\s*ctx\s*\)", render_all), render_all
    # 분석 전용 부트스트랩/리스너를 따로 만들지 않았는지 — 마운트도 한 곳이다.
    assert not re.search(r"document\.addEventListener\(\s*['\"]DOMContentLoaded['\"]\s*,\s*renderAnalytics", js)


def test_analytics_pane_does_not_duplicate_the_filter_bar(client, app):
    """분석 pane 안에 기간 필터 컨트롤 복제본이 없다(필터바는 화면 전체에 한 벌).

    `test_filter_bar_is_shared_by_period_tabs_and_not_duplicated` 가 문서 전체 개수를 세고,
    이 테스트는 **분석 pane 안쪽**을 따로 본다 — 카드 헤드에 '주별/월별' 같은 미니 토글을
    슬쩍 넣는 회귀가 개수 검사만으로는 잡히지 않기 때문이다.
    """
    _login_allowed(client)

    html = _fragment_html(client)
    block = _analytics_block(html)

    assert html.count('class="s-filterbar"') == 1, "필터바가 여러 벌이다"
    for anchor in (
        "s-filterbar",
        "data-settlement-granularity",
        "data-settlement-compare",
        "data-settlement-cumulative",
    ):
        assert anchor not in block, f"분석 pane 이 기간 컨트롤을 복제했다: {anchor}"


@pytest.mark.parametrize("phrase", _EXCLUDED_MOCKUP_CARDS)
def test_analytics_omits_the_cards_without_backing_data(client, app, phrase):
    """근거 데이터가 없어 빼기로 한 목업 카드가 분석 탭에 없다.

    연체 위험 스코어는 데이터가 없을 뿐 아니라 **행 단위**다 — 집계 전용 엔드포인트가
    행을 싣기 시작하면 노출 계약이 통째로 무너진다.
    """
    _login_allowed(client)

    block = _strip_comments(_analytics_block(_fragment_html(client)))

    assert phrase not in block, f"제외 대상이 분석 탭에 남아 있다: {phrase}"
    assert phrase not in _strip_comments(_read(f"static/{JS_ASSET}"))


def test_analytics_does_not_reintroduce_the_false_scope_note(client, app):
    """목업의 거짓 문구("모든 카드가 같은 기간 스코프")를 분석 탭이 되살리지 않는다.

    실구현에서 미수·aging 은 기간 무관이고 단계 카드는 현재 시점 스냅샷이다. 템플릿이 이미
    교정 문구를 달고 있으므로, 분석 카드가 자기 부제로 다시 거짓말하면 안 된다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    assert "모든 카드가 같은 기간 스코프" not in html
    # 교정 문구는 그대로 살아 있어야 한다(지우고 통과시키는 회귀 방지).
    assert "기간과 무관한 전체 집계" in html


def test_analytics_collection_is_labelled_as_an_approximation(client, app):
    """수금 카드가 스스로 **근사치**임을 말한다 — 실제 입금일 시계열이 아니다.

    입금 확인 토글 기반이라 '완료월 귀속' 이라는 전제가 붙어야 회계가 이 숫자를 입금
    실적으로 오독하지 않는다.
    """
    _login_allowed(client)

    block = _analytics_block(_fragment_html(client))

    assert "근사" in block, "수금액의 근사 성격 표기가 없다"
    assert "완료월" in block, "완료월 귀속이라는 전제 표기가 없다"


def test_analytics_bars_use_css_custom_properties_for_width():
    """막대 폭을 인라인 style 문자열이 아니라 CSS 커스텀 프로퍼티로 넣는다(저장소 규칙).

    동시에 이것이 **폭 0 함정 밖**이라는 근거다 — 퍼센트 폭이라 호스트 `clientWidth` 를
    읽지 않으므로 숨은 pane 에서 그려도 눌리지 않는다(SVG 차트와 다른 점).
    """
    js = _read_code(f"static/{JS_ASSET}")
    css = _read_code(f"static/{CSS_ASSET}")

    body = _js_function_body(js, "renderBarList")
    assert "--s-bar-pct" in body, body[:300]
    assert not re.search(r"\.style\.width\s*=", body), "폭을 인라인 style 로 넣는다"
    assert not re.search(r"clientWidth", body), "막대가 호스트 폭을 읽는다(폭 0 함정에 들어간다)"
    assert re.search(r"\.s-bbar\s*\{[^}]*var\(--s-bar-pct", css), "CSS 가 변수를 소비하지 않는다"


# ==========================================================================
# 분석 탭 매출 추이 카드 — 목업 v3 의 span8 메인 카드(사용자 결정 2026-08-31)
# ==========================================================================
def test_analytics_tab_carries_the_trend_card(client, app):
    """분석 탭에도 매출 추이 카드가 있다.

    목업 v3 에서 가장 큰 카드다. 요약 탭이 같은 데이터를 그린다는 이유로 뺐다가
    사용자 결정으로 되살렸다 — 분석 화면만 보는 사람이 추세를 보려고 탭을 옮기지
    않아도 되어야 한다.
    """
    _login_allowed(client)

    html = _fragment_html(client)

    for anchor in (
        'id="foms-settle-an-trend-card"',
        'id="foms-settle-an-main-chart"',
        'id="foms-settle-an-main-legend"',
        'id="foms-settle-an-main-table"',
        "data-settlement-an-main-sub",
        'data-settlement-empty="an_buckets"',
        "data-settlement-an-unknown-completion",
    ):
        assert anchor in html, f"분석 탭 추이 카드 앵커가 없다: {anchor}"


def test_trend_chart_is_one_function_called_with_two_element_sets():
    """추이 차트는 **복제가 아니라 같은 함수의 두 번째 호출**이다.

    렌더 코드를 두 벌로 복사하면 한쪽만 고치는 회귀가 난다. 그래서 `renderMainChart`
    는 호스트 묶음(`els`)을 인자로 받고, 요약·분석이 그 묶음만 바꿔 같은 함수를 부른다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert re.search(r"function\s+renderMainChart\s*\(\s*ctx\s*,\s*els\s*\)", js), (
        "renderMainChart 가 호스트 묶음을 인자로 받지 않는다 — 복제 구조로 되돌아갔다"
    )
    calls = re.findall(r"renderMainChart\(\s*ctx\s*,\s*ctx\.els\.(\w+)\s*\)", js)
    assert "mainEls" in calls and "anMainEls" in calls, (
        f"요약·분석 두 묶음으로 부르지 않는다: {calls}"
    )
    # 두 번째 정의(복사본)가 생기면 red.
    assert len(re.findall(r"function\s+renderMainChart\b", js)) == 1, (
        "renderMainChart 정의가 둘이다 — 복제됐다"
    )


def test_analytics_table_wrapper_is_scoped_to_its_own_card():
    """`.s-tblv` 가 이제 문서에 둘이다 — 카드 안으로 스코프해서 잡아야 한다.

    루트 `querySelector('.s-tblv')` 로 잡으면 분석 카드의 빈 상태 전환이 **요약 카드의**
    표를 토글한다(조용한 오작동이라 눈으로 못 잡는다).
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert ".s-card--main .s-tblv" in js, "요약 표 래퍼가 카드 안으로 스코프되지 않았다"
    assert "#foms-settle-an-trend-card .s-tblv" in js, "분석 표 래퍼가 카드 안으로 스코프되지 않았다"
    assert not re.search(r"q\(\s*'\.s-tblv'\s*\)", js), (
        "스코프 없는 `.s-tblv` 선택이 남아 있다"
    )


# ==========================================================================
# 비교 라인이 축을 끌고 올라가는 문제 (스테이징 실화면 지적 2026-08-31)
# ==========================================================================
def test_comparison_line_cannot_dominate_the_axis():
    """전월의 큰 하루 하나가 y축 상한을 잡아 당월 막대를 납작하게 만들지 못한다.

    목업은 `max(barMax, lineMax)` 로 충분했다 — 두 시리즈가 비슷한 규모의 가정치였기
    때문이다. 실데이터에서는 전월 스파이크 하나가 축을 끌어올려 **당월 막대 전체**가
    눌린다(스테이징 2026-08 실측: 라인 2,200만 → 축 3,000만 → 막대 전부 눌림).
    막대가 주 마크이므로 라인이 축을 올릴 수 있는 한도를 둔다.
    """
    body = _js_function_body(_read_code(f"static/{JS_ASSET}"), "columnChart")

    assert "LINE_HEADROOM" in body, (
        "축 상한이 비교 라인 최댓값을 그대로 받는다 — 막대가 눌리는 것을 막는 한도가 없다"
    )
    assert re.search(r"Math\.min\(\s*lineMax\s*,\s*barMax\s*\*\s*LINE_HEADROOM\s*\)", body), (
        "라인 최댓값을 막대 기준 배수로 제한하는 식이 없다"
    )
    assert re.search(r"Math\.max\(\s*barMax\s*,", body), (
        "막대 최댓값이 축 상한의 하한이 아니다 — 막대가 잘릴 수 있다"
    )


def test_clipped_comparison_points_are_marked_not_silently_flattened():
    """축을 넘는 비교 구간은 상단에 고정하되 **표식을 남긴다**.

    잘라놓고 아무 말도 안 하면 그 구간이 "축 상한과 같았다"로 읽힌다 — 눌림을 고치려다
    새 거짓말을 만드는 셈이다. 툴팁은 축이 아니라 원본 값을 읽으므로 숫자는 그대로 나온다.
    """
    body = _js_function_body(_read_code(f"static/{JS_ASSET}"), "columnChart")
    css = _read_code(f"static/{CSS_ASSET}")

    assert re.search(r"if\s*\(\s*lv\s*>\s*sc\.top\s*\)", body), "축을 넘는 값을 감지하지 않는다"
    assert "s-clip-mark" in body, "축을 넘어간 구간 표식을 그리지 않는다"
    assert "s-clip-mark" in css, "표식 CSS 규칙이 없다"
    assert "<title>" in body, "표식에 접근 가능한 설명(title)이 없다"
