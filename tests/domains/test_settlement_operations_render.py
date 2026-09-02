"""SETTLE-TABS-01: 정산 대시보드 **실무(경리·수금) 탭** 화면 계약 테스트.

행 API(`GET /api/settlement/rows`)의 응답 계약·권한·PII 는
`tests/domains/test_settlement_rows*.py` 가 이미 덮는다. **이 파일은 그걸 중복하지 않는다.**
여기서 잠그는 것은 "그 응답을 받아 그리는 화면이 놓치면 조용히 망가지는 것들"이다.

1. **과입금 칸** — 잔금은 0 에서 잘린다. 이 칸이 없으면 "돌려줄 돈이 있다"는 사실이 화면에서
   통째로 사라진다(CEO L-1 회귀). 목업에는 없던 칸이라 **이식하다 빠지기 가장 쉬운 자리**다.
2. **금액 미상과 0 의 구분** — `shipping_price`/`deposit`/`balance` 는 `null` 일 수 있다(운영
   191건). 0 으로 그리면 화면이 거짓말한다.
3. **부서 라벨 하드코딩 금지** — 청구 폼의 귀속 부서는 서버 상수
   (`SETTLEMENT_DEPARTMENT_OPTIONS`)가 SSOT 다. 화면이 목록을 들고 있으면 서버 허용 집합
   (`SETTLEMENT_DEPARTMENTS`)과 두 벌이 되어 조용히 갈린다 — 요약 탭이 단계 라벨을
   하드코딩하지 않는 것과 같은 이유이고, 그쪽에도 같은 계약 테스트가 있다.
4. **요약 탭과의 선택자 충돌** — 이 마크업은 요약 탭과 **같은 루트 안**에 들어간다.
   `dashboard.js` 의 `collectEls()` 는 루트 전체를 `querySelector` 로 훑으므로 같은 이름을
   쓰면 서로의 노드를 잡는다. 상태 노드도 마찬가지라, 요약 탭의 `showState()` 를 빌려 쓰면
   **숨은 pane 안에서** 로딩/실패가 켜져 사용자는 아무것도 못 본다.
5. **목업 잔재** — 목업에는 근거 데이터가 없는 카드(수금 예정 시리즈·채널 수수료 대사·마감
   잠금·연체 알림)가 "미구현" 배지와 함께 들어 있었다. 남으면 없는 기능을 있는 것처럼 보여준다.
6. **무음 실패 금지** — fetch 실패는 사람이 읽는 사유와 재시도 버튼이 **이 탭 안에** 떠야 한다.
7. **자산 캐시 핀 / defer / 외부 CDN 0 / 인라인 스타일 금지** — 저장소 절대 규칙.

**검사 층위(의도적으로 둘)**
- *렌더*: 파셜을 실제로 렌더해서 나오는 HTML 을 본다. 이 파셜은 아직 셸에 include 되지 않아
  (셸 파일은 다른 작업이 소유한다) 페이지 GET 으로는 볼 수 없다 — 그래서 `render_template`
  으로 직접 렌더한다. 단독 렌더는 `UndefinedError` 함정도 같이 잡는다.
- *소스 리터럴*: 템플릿/CSS/JS 파일을 읽어 문자열을 확인한다(`tests/domains` 관례).
  JS 는 서버 렌더에 안 나오므로 이쪽으로만 잡을 수 있다.

**배선 테스트는 "걸려 있으면 옳아야 한다" 형태다.** include 와 자산 태그는 셸 템플릿
(`settlement_dashboard_body.html`)에 들어가는데 그 파일은 이 작업의 소유가 아니다. 그래서
"아직 안 걸림"으로 red 를 내지 않되, **걸리는 순간부터** 핀·defer·중복을 실제로 잡는다.

docs/ 는 읽지 않는다(CI-DOCSCOPE-01) — 목업 HTML 도 docs/ 아래라 이 파일은 열지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import render_template

_ROOT = Path(__file__).resolve().parents[2]

#: 이 작업이 소유한 산출물 3종. 계약 검사는 **이 표면 안에서만** 한다.
BODY_TEMPLATE = "templates/cs/partials/settlement_operations_body.html"
CSS_ASSET = "css/settlement/settlement-operations.css"
JS_ASSET = "js/settlement/operations.js"

_STATIC_ASSETS = (CSS_ASSET, JS_ASSET)
_ALL_SOURCES = (BODY_TEMPLATE,) + tuple(f"static/{a}" for a in _STATIC_ASSETS)

#: 셸이 include 를 걸어야 하는 대상(배선 테스트가 이 이름으로 판정한다).
_TEMPLATE_NAME = "cs/partials/settlement_operations_body.html"
#: 셸 템플릿 — **이 작업은 편집하지 않는다.** 배선 여부와 공통 핀만 읽는다.
_SHELL_TEMPLATE = "templates/cs/partials/settlement_dashboard_body.html"
#: 이 화면과 **한 몸으로 움직이는** 요약 탭 자산. 공통 핀을 여기서 읽어 온다.
_SIBLING_CSS_ASSET = "css/settlement/settlement-dashboard.css"

#: 목업 잔재. "예정" 은 목업이 미구현 카드에 달아 둔 배지였다 —
#: 수금 예정 시리즈 · 채널 수수료 자동 대사 · 월 마감 잠금 · 연체 알림톡이 전부 그 배지를 달고 있었고
#: 넷 다 근거 데이터/발송 배선이 시스템에 없어 이 화면에서 통째로 뺐다.
_MOCKUP_LEFTOVERS = ("MOCKUP", "예정", "가정치", "해피콜")

#: 서버 상수에서 온 귀속 부서 **코드**. 화면이 이 목록을 들고 있으면 서버와 두 벌이 된다.
#: 라벨은 "고객"·"영업" 처럼 화면 다른 곳(컬럼 머리글 등)에도 자연스럽게 나오는 말이 섞여 있어
#: 리터럴 부재로 검사하면 거짓 red 가 난다 — 그래서 **코드 + 라벨 중 이 화면에 나올 이유가 없는
#: 것**만 리터럴로 막고, "옵션이 실제로 컨텍스트에서 온다"는 사실은 렌더 테스트가 증명한다.
_DEPARTMENT_CODES = ("SALES", "DRAWING", "PRODUCTION", "CONSTRUCTION", "CUSTOMER")
_DEPARTMENT_ONLY_LABELS = ("도면", "공장(생산)", "시공팀")

#: 렌더 시점에 반드시 있어야 하는 앵커. JS 가 채우기 전에도 자리가 있어야 한다 —
#: fetch 가 실패해도 "빈 카드"가 아니라 "무엇이 비었는지"가 보여야 하기 때문이다.
_REQUIRED_ANCHORS = {
    "루트": 'data-foms-settlement-ops="1"',
    "행 API URL": "data-rows-url=",
    "KPI 스트립": "data-settlement-ops-kpis",
    "aging 막대 호스트": "data-settlement-ops-aging",
    "aging 빈 상태": 'data-settlement-ops-empty="aging"',
    "그리드": 'id="foms-settle-ops-grid"',
    "행 tbody": "data-settlement-ops-rows",
    "행 빈 상태": 'data-settlement-ops-empty="rows"',
    "합계 각주": "data-settlement-ops-foot",
    "번호 페이저": "data-settlement-ops-pager",
    "로딩 표시": "data-settlement-ops-loading",
    "실패 표시": "data-settlement-ops-error",
    "실패 사유": "data-settlement-ops-error-detail",
    "재시도 버튼": "data-settlement-ops-retry",
    "실행 결과 안내": "data-settlement-ops-notice",
    "CSV 버튼": "data-settlement-ops-csv",
    "청구 폼": "data-settlement-ops-issue-form",
    "청구 폼 부서": "data-settlement-ops-issue-department",
    "청구 폼 금액": "data-settlement-ops-issue-amount",
    "청구 폼 사유": "data-settlement-ops-issue-reason",
    "청구 폼 제출": "data-settlement-ops-issue-submit",
    "aging 해제 칩 자리": "data-settlement-ops-bucket-chip",
}

#: 칩 3묶음 — 값이 그대로 API 파라미터가 된다(`period`/`settlement`/`channel`).
_FILTER_GROUPS = {
    "period": ("all", "7", "30", "31"),
    "settlement": ("all", "pending", "issued"),
    "channel": ("all", "일반", "NAVER"),
}

#: 그리드 컬럼 머리글(순서 포함). 과입금이 7번째라는 것까지 계약이다 — 목업에 없던 칸이라
#: "있긴 한데 맨 끝에 밀린" 형태로 흐려지는 것을 막는다.
#:
#: **11번째 칸이 "정산상태"가 아니라 "차감청구"다**(v1.1 T13 개명). 이 칸은 **내부 차감청구**
#: (부서 귀속 차감) 발행 여부이고, 12번째로 들어오는 "네이버 정산"은 **외부 채널의 정산**이다.
#: 둘 다 "정산"이라 불리면 경리가 남의 축을 보고 판단한다. 화면 문자열만 바꾸고 계약 키
#: (`data-settlement-ops-filter="settlement"` · 칩 값 `all/pending/issued` · 배지 라벨
#: "청구완료"/"대기" · 버튼 "정산 청구")는 그대로다 — 그쪽은 API 파라미터다.
_GRID_HEADERS_BASE = (
    "고객", "채널", "완료일", "출고가", "예약금", "잔금", "과입금",
    "경과일", "현금영수증", "차감청구", "액션",
)

#: 채널 정산 열람 권한자에게만 나오는 12칸. "네이버 정산"은 "차감청구" **바로 뒤**,
#: "액션" **바로 앞**이다 — 내부/외부 두 정산 축을 나란히 읽게 붙이되, "액션은 언제나 마지막
#: 칸"이라는 기존 성질은 지킨다.
_GRID_HEADERS_WITH_CHANNEL = (
    "고객", "채널", "완료일", "출고가", "예약금", "잔금", "과입금",
    "경과일", "현금영수증", "차감청구", "네이버 정산", "액션",
)

#: 요약 탭(dashboard.js `collectEls`)이 루트 전체에서 `querySelector` 로 찾는 이름들.
#: 이 파셜이 같은 이름을 쓰면 요약 탭 JS 가 실무 탭 노드를 잡거나 그 반대가 된다.
_SUMMARY_TAB_SELECTORS = (
    "data-settlement-loading",
    "data-settlement-error",
    "data-settlement-denied",
    "data-settlement-grid",
    "data-settlement-empty=",
    "data-settlement-retry",
    "data-settlement-granularity",
    "data-settlement-compare",
    "data-settlement-cumulative",
    "data-settlement-kpi=",
    "data-settlement-stage",
    "data-settlement-range",
    "data-settlement-stamp",
    'class="s-filterbar"',
    'class="s-foot"',
    'class="s-tabs"',
)

#: 전역을 덮어쓰는 bare 선택자. 이 CSS 는 ERP 공용 문서에 얹히므로 여기서 `body`/`:root`/`*`
#: 를 건드리면 **다른 화면까지** 색·폰트·박스모델이 바뀐다.
_BARE_GLOBAL_SELECTOR_RE = re.compile(r"(?m)^\s*(:root|html|body|\*)\s*(?:,|\{)")

#: 자산 참조 뒤 `?v=` 핀. 기존 관례와 같은 형태를 받는다
#: (`test_settlement_dashboard_render.py:146`).
_PIN_SUFFIX = r"['\"\s\}\)]*\?v=([A-Za-z0-9._-]+)"

#: 외부 호스트 참조. `www.w3.org` 만 예외 — 인라인 SVG 의 네임스페이스 URI 는 네트워크
#: 요청이 아니라 식별자다.
_EXTERNAL_URL_RE = re.compile(r"https?://(?!www\.w3\.org[/\"'])[^\s\"'<>()]+")

_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(.*?)\1[^>]*>", re.I | re.S)
_STYLE_ATTR_RE = re.compile(r"\bstyle\s*=\s*['\"]")

#: 저장소 전역 핀 스캔 제외 목록(기존 관례와 동일).
_PIN_SCAN_EXCLUDE = {".git", "node_modules", ".superpowers", "docs"}

#: 렌더 테스트가 넘기는 sentinel 부서 목록. 실제 코드/라벨과 겹치지 않는 값이라,
#: 이 값이 렌더 결과에 나오면 옵션이 **컨텍스트에서 왔다**는 증거가 된다.
_SENTINEL_DEPARTMENTS = [("ZZ_SENTINEL_A", "센티넬가"), ("ZZ_SENTINEL_B", "센티넬나")]


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _read(rel: str) -> str:
    """저장소 상대 경로 파일을 읽는다. 없으면 사람이 읽는 red 로 죽인다.

    Args:
        rel: 저장소 루트 기준 상대 경로.

    Returns:
        파일 내용.
    """
    path = _ROOT / rel
    assert path.exists(), f"실무 탭 산출물이 없다: {rel}"
    return path.read_text(encoding="utf-8", errors="ignore")


_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.S)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
#: 줄 **처음**에 오는 `//` 만 지운다. 문자열 안의 `//` 까지 지우면 외부 호스트 참조가
#: 검사에서 사라진다 — 가드가 스스로 눈을 가리는 셈이라 하지 않는다.
_JS_LINE_COMMENT_RE = re.compile(r"(?m)^\s*//.*$")


def _strip_comments(text: str) -> str:
    """주석(Jinja/HTML/JS)을 걷어낸 사본을 돌려준다(금지 패턴 검사 전처리).

    규칙을 **설명하는 주석**이 그 규칙 위반으로 잡히는 거짓 red 를 막는다.

    Args:
        text: 원문.

    Returns:
        주석이 제거된 문자열.
    """
    text = _JINJA_COMMENT_RE.sub(" ", text)
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _JS_BLOCK_COMMENT_RE.sub(" ", text)
    return _JS_LINE_COMMENT_RE.sub(" ", text)


def _read_code(rel: str) -> str:
    """파일을 읽고 주석을 제거한 본문을 돌려준다."""
    return _strip_comments(_read(rel))


def _render(app, **context) -> str:
    """실무 탭 파셜을 **단독으로** 렌더한다.

    셸(`settlement_dashboard_body.html`)은 이 작업의 소유가 아니라 아직 include 가 없다.
    페이지 GET 으로는 이 마크업을 볼 수 없으므로 파셜을 직접 렌더한다 — 덤으로 파셜 단독
    렌더 시 `UndefinedError` 가 나는 함정(매크로/변수 기본값 누락)까지 같이 잡는다.

    Args:
        app: Flask 앱 fixture.
        **context: 템플릿 컨텍스트(예: `department_options`).

    Returns:
        렌더된 HTML.
    """
    with app.test_request_context("/erp/settlement"):
        return render_template(_TEMPLATE_NAME, **context)


def _pins_for(asset: str, text: str) -> set[str]:
    """`text` 안에서 `asset` 에 붙은 `?v=` 핀 값을 모두 모은다."""
    return set(re.compile(re.escape(asset) + _PIN_SUFFIX).findall(text))


def _repo_pin_scan_sources() -> list[Path]:
    """핀 일치 검사용 저장소 파일 목록(기존 관례와 동일한 제외 규칙)."""
    return [
        p
        for ext in ("*.html", "*.js", "*.py")
        for p in _ROOT.glob(f"**/{ext}")
        if not any(part in _PIN_SCAN_EXCLUDE for part in p.parts)
    ]


def _shell_is_wired() -> bool:
    """셸 템플릿이 이 파셜을 include 했는지(배선 완료 여부)."""
    path = _ROOT / _SHELL_TEMPLATE
    return path.exists() and _TEMPLATE_NAME in _strip_comments(
        path.read_text(encoding="utf-8", errors="ignore")
    )


def _settlement_common_pin() -> str | None:
    """정산 화면의 **현재 공통 핀**을 요약 탭 CSS 링크에서 읽는다.

    핀 값을 이 파일에 리터럴로 박으면, 요약 탭이 CSS 를 고쳐 핀을 범프하는 순간 이 테스트가
    **옛 값을 강요하는 거짓 계약**이 된다(실제로 작성 중에 `c` → `d` 로 한 번 움직였다).
    잠글 것은 값 자체가 아니라 "같은 화면의 자산은 한 핀으로 함께 움직인다"는 성질이다.

    Returns:
        핀 문자열. 셸에서 못 읽으면 None(그때는 핀 유일성만 검사한다).
    """
    path = _ROOT / _SHELL_TEMPLATE
    if not path.exists():
        return None
    pins = _pins_for(_SIBLING_CSS_ASSET, path.read_text(encoding="utf-8", errors="ignore"))
    return pins.pop() if len(pins) == 1 else None


# ==========================================================================
# 계약 0 — 산출물 실재
# ==========================================================================
@pytest.mark.parametrize("rel", _ALL_SOURCES)
def test_operations_sources_exist_and_are_not_empty(rel):
    """템플릿·CSS·JS 3종이 실재하고 빈 파일이 아니다.

    경로가 흔들리면 include·서비스워커 캐시 키·핀 계약이 전부 따로 논다.
    """
    assert len(_read(rel).strip()) > 200, f"{rel} 가 사실상 비어 있다"


# ==========================================================================
# 계약 1 — 렌더 앵커 (JS 가 채우기 전에도 자리가 있어야 한다)
# ==========================================================================
@pytest.mark.parametrize("name,anchor", sorted(_REQUIRED_ANCHORS.items()))
def test_rendered_partial_carries_every_anchor(app, name, anchor):
    """렌더 결과가 계약 앵커를 전부 갖는다(그리드·필터·페이저·상태·실행 폼)."""
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    assert anchor in html, f"{name} 앵커가 없다: {anchor}"


def test_rendered_partial_survives_missing_context(app):
    """컨텍스트 없이 단독 렌더해도 죽지 않는다(파셜 단독 렌더 `UndefinedError` 함정).

    `department_options` 는 뷰가 넘기는 값이라 없을 수 있다. 없을 때 예외로 죽으면 셸
    전체가 500 이 된다 — 조용히 비는 것도, 죽는 것도 답이 아니라 **말해야** 한다(아래 테스트).
    """
    html = _render(app)

    assert 'id="foms-settle-ops-grid"' in html


@pytest.mark.parametrize("key,values", sorted(_FILTER_GROUPS.items()))
def test_filter_chip_groups_render_every_api_value(app, key, values):
    """칩 3묶음이 각각 API 파라미터 값 전부를 낸다.

    칩 값이 그대로 `period`/`settlement`/`channel` 파라미터가 된다. 하나라도 빠지면 사용자가
    그 조건을 화면에서 만들 수 없다(예: '31일 이상'이 없으면 장기 미수를 못 좁힌다).
    """
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    assert f'data-settlement-ops-filter="{key}"' in html, key
    for value in values:
        assert f'data-settlement-ops-value="{value}"' in html, (key, value)


def test_filter_chips_use_aria_pressed_for_selection(app):
    """칩 선택 상태를 `aria-pressed` 로 말한다(색만으로 말하지 않는다)."""
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    pressed = re.findall(r'data-settlement-ops-value="([^"]+)"[^>]*aria-pressed="true"', html)
    assert pressed == ["all", "all", "all"], pressed


# ==========================================================================
# 계약 2 — 과입금 칸 (이 화면이 절대 잃으면 안 되는 것)
# ==========================================================================
def test_grid_has_the_overpaid_column(app):
    """그리드에 **과입금** 칸이 있다.

    잔금은 0 에서 잘린다(`_balance_after_payments`). 넘친 금액을 따로 내지 않으면
    "돌려줄 돈이 있다"는 사실이 화면에서 통째로 사라진다 — 목업에 없던 칸이라 이식하다
    빠지기 가장 쉬운 자리다(CEO L-1).
    """
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    assert "과입금" in html, "과입금 칸이 없다"


def test_grid_headers_are_complete_and_in_contract_order(app):
    """게이트 없는 렌더의 머리글 11칸이 계약 순서대로 있다(과입금이 잔금 바로 옆이다).

    과입금을 맨 끝으로 밀면 "잔금 옆의 짝"이라는 의미가 사라져 스캔에서 놓친다.

    파셜을 단독으로 렌더하면 `can_view_channel_settlement` 는 Undefined = falsy 다.
    그 성질을 그대로 "권한 없는 사용자" 케이스의 계약으로 쓴다(§5.2).
    """
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    headers = re.findall(r"<th\b[^>]*>\s*([^<]+?)\s*</th>", html)
    assert headers == list(_GRID_HEADERS_BASE), headers


def test_grid_gains_the_channel_column_only_for_gated_actors(app):
    """회계 게이트를 통과한 렌더에만 12번째 칸 "네이버 정산"이 생긴다.

    위치까지 계약이다 — "액션" 뒤로 밀리면 "액션은 마지막 칸"이라는 기존 성질이 깨지고,
    "차감청구" 에서 떨어지면 내부/외부 두 정산 축을 나란히 읽는다는 배치 근거가 사라진다.
    """
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS,
                   can_view_channel_settlement=True)

    headers = re.findall(r"<th\b[^>]*>\s*([^<]+?)\s*</th>", html)
    assert headers == list(_GRID_HEADERS_WITH_CHANNEL), headers


def test_channel_column_markup_is_absent_for_denied_actors(app):
    """권한이 없으면 `<th>` 도 서버 표식도 **마크업 자체가 없다**(§6).

    클라에서 감추는 방식은 쓰지 않는다 — 실무 탭 행 API 는 CS·영업에게도 200 이라
    "감춤"은 개발자 도구 한 번이면 뚫린다. 없는 것이 유일한 방어다.
    """
    denied = _render(app, department_options=_SENTINEL_DEPARTMENTS,
                     can_view_channel_settlement=False)
    allowed = _render(app, department_options=_SENTINEL_DEPARTMENTS,
                      can_view_channel_settlement=True)

    assert "네이버 정산" not in denied
    assert "data-settlement-ops-channel-col" not in denied
    assert "네이버 정산" in allowed
    assert "data-settlement-ops-channel-col" in allowed



def test_js_renders_overpaid_only_when_non_zero():
    """JS 가 과입금 0 을 값으로 그리지 않는다(0 이 숫자로 보이면 신호가 죽는다)."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "overpaid" in js, "과입금 필드를 JS 가 읽지 않는다"
    assert re.search(r"row\.overpaid\s*\|\|\s*0\)\s*>\s*0", js), (
        "과입금을 0 초과일 때만 값으로 내는 분기가 없다"
    )


def test_js_distinguishes_unknown_amount_from_zero():
    """`null`(금액 미상)을 0 이 아니라 "—" 로 그린다.

    운영에 출고가 미산출 191건이 있다. 0 으로 그리면 "무료 시공"처럼 읽힌다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    money = re.search(r"function money\(([^)]*)\)\s*\{([^}]*)\}", js)
    assert money, "금액 포맷 함수를 찾지 못했다"
    assert "null" in money.group(2), f"미상을 null 로 구분하지 않는다: {money.group(2)}"
    assert "—" in js, "미상 표기(—)가 없다"


# ==========================================================================
# 계약 3 — 부서 라벨 하드코딩 금지 (서버 SSOT)
# ==========================================================================
@pytest.mark.parametrize("rel", _ALL_SOURCES)
def test_department_codes_are_not_hardcoded_in_surface(rel):
    """귀속 부서 **코드**를 화면이 들고 있지 않다.

    코드 SSOT 는 `foms.api.cs.dashboard.SETTLEMENT_DEPARTMENTS`, 라벨 SSOT 는
    `foms.web.cs.completion_dashboard.SETTLEMENT_DEPARTMENT_OPTIONS` 다. 화면이 목록을
    복제하면 서버 허용 집합이 바뀔 때 조용히 갈리고, 없는 부서로 보내 400 이 난다.
    """
    source = _read(rel)

    for code in _DEPARTMENT_CODES:
        assert code not in source, f"{rel}: 부서 코드 하드코딩 {code}"


@pytest.mark.parametrize("rel", _ALL_SOURCES)
def test_department_only_labels_are_not_hardcoded_in_surface(rel):
    """부서 라벨 중 **이 화면에 나올 이유가 없는 것**이 리터럴로 없다.

    "고객"·"영업" 은 컬럼 머리글 등 다른 맥락에도 자연스럽게 나오는 말이라 리터럴 부재로
    검사하면 거짓 red 가 난다. 옵션이 실제로 서버에서 온다는 사실은 아래 렌더 테스트가
    sentinel 값으로 증명한다.
    """
    source = _read(rel)

    for label in _DEPARTMENT_ONLY_LABELS:
        assert label not in source, f"{rel}: 부서 라벨 하드코딩 {label}"


def test_department_options_come_from_the_render_context(app):
    """부서 `<option>` 이 컨텍스트에서 온다 — sentinel 값이 그대로 렌더된다."""
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    for code, label in _SENTINEL_DEPARTMENTS:
        assert f'value="{code}"' in html, code
        assert label in html, label


def test_missing_department_options_are_reported_not_swallowed(app):
    """부서 목록이 안 넘어오면 폼이 **조용히 비는 대신 그 사실을 말한다**(무음 실패 금지).

    뷰가 `department_options` 를 안 넘기면 select 가 빈 채로 남는다. 그 상태로 두면
    사용자는 "부서가 원래 없나 보다" 하고 넘어가고, 청구는 영원히 400 이 난다.
    """
    with_options = _render(app, department_options=_SENTINEL_DEPARTMENTS)
    without = _render(app, department_options=[])

    assert "data-settlement-ops-department-missing" in without
    assert "data-settlement-ops-department-missing" not in with_options
    block_start = without.find("data-settlement-ops-department-missing")
    assert re.search(r"[가-힣]{2,}", without[block_start:block_start + 400]), (
        "안내 문구가 사람이 읽는 한글이 아니다"
    )


# ==========================================================================
# 계약 4 — 목업 잔재 부재
# ==========================================================================
@pytest.mark.parametrize("phrase", _MOCKUP_LEFTOVERS)
def test_rendered_partial_has_no_mockup_leftovers(app, phrase):
    """렌더 결과에 목업 잔재 문구가 없다.

    "예정" 은 목업이 미구현 카드에 달아 둔 배지다 — 수금 예정 시리즈 · 채널 수수료 자동 대사 ·
    월 마감 잠금 · 연체 알림톡. 넷 다 근거 데이터/발송 배선이 시스템에 없어 이 화면에서 뺐다.
    한 글자라도 남으면 없는 기능을 있는 것처럼 보여준다.
    """
    html = _strip_comments(_render(app, department_options=_SENTINEL_DEPARTMENTS))

    assert phrase not in html, f"목업 잔재 '{phrase}' 가 렌더에 남아 있다"


@pytest.mark.parametrize("phrase", _MOCKUP_LEFTOVERS)
def test_sources_have_no_mockup_leftovers(phrase):
    """소스에도 남아 있지 않다 — `{% if %}` 뒤에 숨은 잔재까지 잡는다."""
    for rel in _ALL_SOURCES:
        assert phrase not in _read_code(rel), f"{rel}: 목업 잔재 '{phrase}'"


def test_no_unbacked_teaser_features_are_rendered(app):
    """근거 없는 미래 기능 UI 를 그리지 않는다(버튼만 있고 아무 일도 안 하는 자리 금지)."""
    html = _strip_comments(_render(app, department_options=_SENTINEL_DEPARTMENTS))

    for phrase in ("마감 잠금", "알림톡", "수수료"):
        assert phrase not in html, f"근거 없는 기능 UI 가 남아 있다: {phrase}"


# ==========================================================================
# 계약 5 — 저장소 절대 규칙 (인라인 스타일 / tojson / 외부 CDN / .alert)
# ==========================================================================
def test_template_has_no_inline_style_attribute_or_block():
    """템플릿에 `style="` 속성도 `<style>` 블록도 없다(프로젝트 절대 규칙).

    폭·색 같은 동적 값은 CSS 커스텀 프로퍼티로만 넘긴다(`--s-ops-bar-pct` 패턴).
    """
    source = _read_code(BODY_TEMPLATE)

    assert not _STYLE_ATTR_RE.findall(source), "인라인 style 속성"
    assert "<style" not in source.lower(), "인라인 <style> 블록"


def test_rendered_partial_has_no_inline_style_attribute(app):
    """렌더 결과에도 인라인 style 이 없다(Jinja 로 조립해 넣는 경로까지 막는다)."""
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    assert not _STYLE_ATTR_RE.findall(html), "렌더 결과에 인라인 style 속성"


def test_template_does_not_inline_parse_jinja_json():
    """`JSON.parse('{{ ... }}')`·`|tojson` 직접 파싱이 없다.

    따옴표/개행이 섞인 값 하나로 스크립트 블록 전체가 SyntaxError 로 죽는다.
    초기 페이로드는 `data-*` 속성으로 넘긴다(`data-rows-url` 이 그 형태다).
    """
    source = _read_code(BODY_TEMPLATE)

    assert "JSON.parse('{{" not in source
    assert 'JSON.parse("{{' not in source
    assert not re.search(r"\|\s*tojson", source), "|tojson 직접 사용"


@pytest.mark.parametrize("rel", _ALL_SOURCES)
def test_sources_reference_no_external_host(rel):
    """템플릿·CSS·JS 어디에도 외부 호스트 참조가 없다(perf G2).

    전역 G2 가드는 **동기 `<script>` 태그만** 보므로 `<link>`·`@import`·JS 안의
    `fetch('https://...')` 는 사각이다. 여기서 표면 단위로 전부 막는다.
    """
    hits = _EXTERNAL_URL_RE.findall(_read_code(rel))

    assert not hits, f"{rel}: 외부 호스트 참조 {hits[:5]}"


def test_no_chart_library_or_jquery_globals():
    """차트 라이브러리·jQuery 전역에 기대지 않는다(자체 DOM/CSS 렌더)."""
    js = _read_code(f"static/{JS_ASSET}")

    for banned in (r"new\s+Chart\s*\(", r"\bd3\.select\b", r"\becharts\.",
                   r"\bHighcharts\.", r"\$\(", r"\bjQuery\b"):
        assert not re.search(banned, js), f"금지 전역 사용 흔적: {banned}"


def test_persistent_notices_are_not_autodismissed_alerts():
    """상시 안내를 Bootstrap `.alert` 로 만들지 않는다(5초 뒤 자동으로 닫힌다).

    부득이 쓴다면 `data-foms-no-autodismiss` 가 함께 있어야 한다
    (project_alert_autodismiss_trap). 이 화면은 `.s-state`/`.s-empty` 어휘를 쓴다.
    """
    body = _read_code(BODY_TEMPLATE)

    for match in re.finditer(r'class="[^"]*\balert\b[^"]*"', body):
        tag_start = body.rfind("<", 0, match.start())
        tag_end = body.find(">", match.end())
        tag = body[tag_start:tag_end + 1]
        assert "data-foms-no-autodismiss" in tag, f"자동닫힘 .alert: {tag[:160]}"
    assert "s-state" in body and "s-empty" in body, "상태/빈 상태 어휘를 쓰지 않는다"


def test_css_is_namespaced_and_touches_no_global_selector():
    """CSS 가 `.foms-settle` 아래로 네임스페이스돼 있고 전역 선택자를 안 건든다.

    목업의 `.panel`/`.chip`/`.grid`/`.btn` 맨이름을 그대로 쓰면 Bootstrap 5·`erp-pro.css`
    와 정면충돌한다. 네임스페이스만으로는 못 막아서 **이름 자체**를 `s-ops-` 로 갈랐다.
    """
    css = _read_code(f"static/{CSS_ASSET}")

    assert "foms-settle" in css, ".foms-settle 네임스페이스가 없다"
    bare = _BARE_GLOBAL_SELECTOR_RE.findall(css)
    assert not bare, f"전역 bare 선택자 {sorted(set(bare))}"
    selectors = re.findall(r"(?m)^\.([A-Za-z][\w-]*)", css)
    assert set(selectors) <= {"foms-settle"}, f"루트 밖 선택자 {sorted(set(selectors))}"


# ==========================================================================
# 계약 6 — 요약 탭과의 선택자 충돌 금지
# ==========================================================================
@pytest.mark.parametrize("selector", _SUMMARY_TAB_SELECTORS)
def test_surface_does_not_reuse_summary_tab_selectors(selector):
    """요약 탭이 루트 전체에서 찾는 이름을 재사용하지 않는다.

    두 탭은 **같은 루트(`#foms-settlement-root`) 안**에 산다. `dashboard.js` 의
    `collectEls()` 는 `root.querySelector(...)` 로 훑으므로 같은 이름을 쓰면 요약 탭 JS 가
    실무 탭 노드를 잡거나 그 반대가 된다. 특히 상태 노드가 그렇다 — 요약 탭의 로딩/실패는
    요약 pane **안에** 있어서, 실무 탭이 그것을 켜면 숨은 pane 안에서 켜져 사용자는
    아무것도 못 본다. `class="s-filterbar"` 는 문서에 1개여야 한다는 별도 계약도 있다.

    주석은 걷어내고 본다 — **규칙을 설명하는 주석**이 그 규칙 위반으로 잡히는 거짓 red 를
    막기 위해서다(요약 탭 계약 테스트가 같은 이유로 같은 전처리를 쓴다).
    """
    for rel in _ALL_SOURCES:
        assert selector not in _read_code(rel), f"{rel}: 요약 탭 선택자 재사용 {selector}"


def test_ops_tab_owns_its_own_loading_and_error_nodes(app):
    """로딩·실패가 **서로 다른 노드**로, 재시도까지 갖춰 이 탭 안에 있다.

    무음 실패 금지다 — 느리거나 죽은 fetch 는 사람이 읽는 사유와 재시도 버튼으로 드러나야 한다.
    """
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)

    positions = {
        key: html.find(_REQUIRED_ANCHORS[key])
        for key in ("로딩 표시", "실패 표시", "재시도 버튼")
    }
    assert all(p >= 0 for p in positions.values()), positions
    assert len(set(positions.values())) == 3, positions
    start = html.find(_REQUIRED_ANCHORS["실패 표시"])
    assert re.search(r"[가-힣]{2,}", html[start:start + 500]), "실패 안내가 한글 문구가 아니다"


def test_failure_hides_the_stale_kpi_and_aging_numbers():
    """실패하면 KPI 스트립과 aging 막대도 함께 감춘다.

    셋 다 같은 응답에서 나온다. 목록만 실패로 바꾸고 위 숫자를 남기면 "미수 624건"이 지금
    조건의 값인 양 실패 문구 옆에 계속 서 있다 — 실화면 스크린샷에서 실제로 그랬다
    (2026-08-31). 로딩 중에는 남긴다: 곧 교체될 값이고 로딩 문구가 그 사실을 말한다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    show = re.search(r"function showState\(ctx, kind, detail\)\s*\{(.*?)\n  \}", js, re.S)
    assert show, "showState() 를 찾지 못했다"
    body = show.group(1)
    assert re.search(r"toggle\(ctx\.els\.kpis,\s*kind === 'error'\)", body), body[:400]
    assert re.search(r"toggle\(ctx\.els\.agingPanel,\s*kind === 'error'\)", body), body[:400]


def test_navigation_clears_a_stale_action_notice():
    """칩·막대·페이지로 화면을 옮기면 직전 실행 결과 안내를 지운다.

    실행 직후의 재조회에서는 지우지 않는다 — "확인했습니다"가 곧바로 덮여 사라지면
    아무 일도 안 한 것처럼 보인다. 지우는 자리는 **사용자 이동**뿐이다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    for fn in ("applyFilter", "toggleBucket"):
        block = re.search(rf"function {fn}\(ctx[^)]*\)\s*\{{(.*?)\n  \}}", js, re.S)
        assert block, f"{fn}() 를 찾지 못했다"
        assert "clearNotice(ctx)" in block.group(1), f"{fn}: 낡은 안내를 안 지운다"
    load = re.search(r"async function loadRows\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    assert load and "clearNotice(ctx)" not in load.group(1), (
        "loadRows 가 안내를 지운다 — 실행 직후 재조회에서 성공 문구가 사라진다"
    )


def test_js_owns_its_own_state_switching():
    """JS 가 자기 상태 노드만 만진다 — 요약 탭 `showState()` 를 흉내 내지 않는다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "settlement-ops-loading" in js or "settlementOpsLoading" in js
    assert "settlement-ops-error" in js or "settlementOpsError" in js
    assert "data-settlement-loading" not in js, "요약 탭 로딩 노드를 건드린다"
    assert "data-settlement-denied" not in js, "요약 탭 권한거부 노드를 건드린다"


# ==========================================================================
# 계약 7 — fetch 규율 (try/catch + success 검증 + 파라미터 전량)
# ==========================================================================
def test_js_guards_fetch_with_try_catch_and_success_check():
    """fetch 가 try/catch + `success` 검증을 거친다.

    세션 만료 시 HTML 302 가 오면 `res.json()` 이 던진다. catch 가 없으면 화면이 영원히
    로딩 상태로 남고 아무 메시지도 안 뜬다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert "fetch(" in js
    assert re.search(r"\btry\s*\{", js), "try 블록이 없다"
    assert re.search(r"\bcatch\s*\(", js), "catch 블록이 없다"
    assert re.search(r"\.success\s*!==\s*true", js), "data.success 검증이 없다"


@pytest.mark.parametrize("param", ["period", "settlement", "channel", "aging", "page"])
def test_js_sends_every_api_filter_param(param):
    """행 API 의 파라미터 5종을 전부 싣는다 — 칩/막대/페이저가 서버 필터로 이어진다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert f"'{param}='" in js or f'"{param}="' in js, f"{param} 파라미터를 안 보낸다"


@pytest.mark.parametrize(
    "key",
    ["rows", "totals", "total_count", "total_pages", "aging_options", "aging_summary",
     "filters", "as_of"],
)
def test_js_binds_every_api_response_key(key):
    """응답의 최상위 키를 실제로 참조한다(조용한 누락 차단).

    특히 `aging_options` 를 안 읽으면 버킷 라벨을 화면이 지어내게 된다 — 버킷 정의는
    서버 계약(`AGING_BUCKETS`)이다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert key in js, f"응답 키 '{key}' 를 JS 가 쓰지 않는다"


@pytest.mark.parametrize(
    "field",
    ["order_id", "customer_name", "channel_label", "completion_date", "shipping_price",
     "deposit", "deposit_confirmed", "balance", "overpaid", "paid", "receivable",
     "elapsed_days", "aging", "cash_receipt_state", "settlement_issued"],
)
def test_js_binds_every_exposed_row_field(field):
    """행 표면이 내주는 필드를 화면이 전부 쓴다.

    서버가 노출 계약을 좁혀 가며 고른 필드다. 화면이 안 쓰면 그 사실(예약금 확인 여부·
    과입금·현금영수증 상태)이 사용자에게 도달하지 않는다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert field in js, f"행 필드 '{field}' 를 JS 가 쓰지 않는다"


def test_js_uses_channel_label_not_raw_code():
    """채널은 `channel_label` 로 표시한다 — 원본 코드는 화면에 "NAVER" 로 뜬다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "channel_label" in js
    assert '"NAVER"' not in js and "'NAVER'" not in js, "채널 코드를 JS 가 들고 있다"


def test_js_does_not_hardcode_aging_bucket_codes_or_labels():
    """aging 버킷 코드·라벨을 화면이 들고 있지 않다 — 서버 `aging_options` 가 SSOT 다."""
    js = _read_code(f"static/{JS_ASSET}")

    for code in ("LE7", "D8_30", "D31_60", "D61_90", "D91_PLUS"):
        assert code not in js, f"aging 버킷 코드 하드코딩: {code}"
    assert "aging_options" in js, "서버 버킷 목록을 읽지 않는다"


def test_js_does_not_call_the_aggregates_api():
    """집계 API 를 부르지 않는다 — 한 화면에 데이터 소스는 하나다.

    같은 숫자가 두 계산 경로로 갈리면 조용히 어긋나고, 어느 쪽이 맞는지 화면만 봐서는 모른다.
    """
    js = _read_code(f"static/{JS_ASSET}")
    body = _read_code(BODY_TEMPLATE)

    assert "aggregates" not in js, "실무 탭이 집계 API 를 부른다"
    assert "aggregates" not in body, "실무 탭 마크업이 집계 API URL 을 싣는다"


# ==========================================================================
# 계약 8 — 실행 버튼 2종 (성격이 다르다)
# ==========================================================================
def test_payment_confirm_button_is_one_click_with_the_right_payload():
    """[입금 확인] 은 `{type: 'balance', confirmed: true}` 원클릭이다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "payment-confirm" in js, "입금 확인 엔드포인트가 없다"
    assert re.search(r"type:\s*'balance'", js), "type: 'balance' 를 안 보낸다"
    assert re.search(r"confirmed:\s*true", js), "confirmed: true 를 안 보낸다"
    assert "입금 확인" in js, "버튼 라벨이 없다"


def test_settlement_issue_sends_all_three_required_fields():
    """[정산 청구] 는 `department`·`amount`·`reason` **셋 다** 보낸다.

    셋 중 하나라도 없으면 서버가 400 을 준다(`foms/api/cs/dashboard.py:285-295`). 목업은
    원클릭처럼 그려 놨지만 실제로는 폼이 필요하다 — 그래서 두 버튼은 대칭이 아니다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert "settlement/issue" in js, "정산 청구 엔드포인트가 없다"
    post = re.search(r"settlementIssueUrl\(orderId\),\s*\{(.*?)\}", js, re.S)
    assert post, "정산 청구 payload 를 찾지 못했다"
    for field in ("department", "amount", "reason"):
        assert field in post.group(1), f"payload 에 {field} 가 없다: {post.group(1)}"
    assert "정산 청구" in js, "버튼 라벨이 없다"


def test_settlement_issue_validates_before_sending():
    """세 값이 비면 서버 400 왕복 대신 화면이 먼저 사람 말로 말한다."""
    js = _read_code(f"static/{JS_ASSET}")

    submit = re.search(r"async function submitIssue\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    assert submit, "submitIssue() 를 찾지 못했다"
    body = submit.group(1)
    assert body.count("notice(ctx, 'error'") >= 3, "세 항목 각각의 안내가 없다"


def test_mutations_are_same_origin_session_auth_without_csrf_header():
    """실행 호출이 `credentials: 'same-origin'` 세션 인증이고 CSRF 헤더를 쓰지 않는다.

    기존 호출부(`static/js/orders/erp-order-shared.js:2893`)와 같은 형태다 — 여기만 헤더를
    붙이면 서버가 기대하지 않는 값이 되고, 반대로 credentials 를 빠뜨리면 401 이 난다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    post = re.search(r"async function postJson\([^)]*\)\s*\{(.*?)\n  \}", js, re.S)
    assert post, "postJson() 을 찾지 못했다"
    assert "same-origin" in post.group(1), post.group(1)[:300]
    assert "X-CSRFToken" not in js, "CSRF 헤더를 붙였다"


def test_mutation_success_refreshes_the_row_data():
    """실행 성공 후 목록을 다시 읽는다 — 화면의 금액이 서버와 갈리지 않게."""
    js = _read_code(f"static/{JS_ASSET}")

    for fn in ("confirmBalance", "submitIssue"):
        block = re.search(rf"async function {fn}\(ctx[^)]*\)\s*\{{(.*?)\n  \}}", js, re.S)
        assert block, f"{fn}() 를 찾지 못했다"
        assert "loadRows(ctx)" in block.group(1), f"{fn}: 성공 후 재조회가 없다"


# ==========================================================================
# 계약 9 — 페이지네이션 (번호 페이저, 무한스크롤 금지)
# ==========================================================================
def test_pagination_is_a_numbered_pager_not_infinite_scroll():
    """번호 페이저를 쓴다 — 무한스크롤·sentinel 배선이 없다(스펙 §13.3-3)."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "total_pages" in js and "aria-current" in js, "번호 페이저 배선이 없다"
    for banned in ("IntersectionObserver", "sentinel", "infinite"):
        assert banned not in js, f"무한스크롤 흔적: {banned}"


def test_footer_reports_the_true_total_count():
    """각주가 페이지 건수가 아니라 **조건 전체 건수**를 말한다.

    캡/페이지로 자른 수를 전체인 양 말하면 "전사 미수가 60건" 으로 읽힌다
    (project_dashboard_cap_before_python_filter 와 같은 계열의 오해).
    """
    js = _read_code(f"static/{JS_ASSET}")

    foot = re.search(r"function renderFoot\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    assert foot, "renderFoot() 를 찾지 못했다"
    assert "total_count" in foot.group(1), foot.group(1)[:300]


# ==========================================================================
# 계약 10 — CSV (화면에 있는 것만, 그 사실을 이름이 말한다)
# ==========================================================================
def test_csv_export_is_labelled_as_current_page_only(app):
    """CSV 버튼·파일명·안내가 "현재 페이지"임을 말한다.

    조건 전체를 담으려면 페이지 수만큼 왕복해야 해서 서버 파일 엔드포인트 없이는 정직하지
    않다. 화면에 없는 것을 파일에 넣지 않고, 파일에 무엇이 들었는지 이름이 말한다.
    """
    html = _render(app, department_options=_SENTINEL_DEPARTMENTS)
    js = _read_code(f"static/{JS_ASSET}")

    assert "현재 페이지" in html, "CSV 버튼이 범위를 말하지 않는다"
    assert "현재 페이지" in js, "파일명/안내가 범위를 말하지 않는다"
    assert "과입금" in js, "CSV 에 과입금 칸이 없다"


def test_csv_quotes_cells_that_contain_separators():
    """고객명에 쉼표·따옴표가 있어도 칸이 밀리지 않는다."""
    js = _read_code(f"static/{JS_ASSET}")

    cell = re.search(r"function csvCell\([^)]*\)\s*\{(.*?)\n  \}", js, re.S)
    assert cell, "csvCell() 을 찾지 못했다"
    assert '""' in cell.group(1), f"따옴표 이스케이프가 없다: {cell.group(1)}"


# ==========================================================================
# 계약 11 — 프래그먼트 재진입 (perf G4) + 탭 활성화 지연 로드
# ==========================================================================
def test_js_has_singleton_init_guard():
    """전역 초기화 싱글톤 가드가 있다.

    셸 스왑 때 `DOMContentLoaded` 는 다시 안 뜨고 스크립트 본문만 재실행된다. 가드가 없으면
    전역 listener 가 스왑마다 쌓인다. 이름 형식은 perf 가드 탐지기가 인식하는 것을 쓴다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert re.search(
        r"window\.__[A-Za-z0-9_$]*(?:BOUND|INIT|INITIALIZED|LOADED|MOUNTED)", js
    ), "window.__*_BOUND 류 싱글톤 가드가 없다"


def test_js_reinitializes_on_fragment_swap_and_marks_mount():
    """스왑 이벤트로 재초기화하고, 루트당 1회만 마운트한다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "foms:erp-shell-fragment-swapped" in js, "프래그먼트 스왑 재init 훅이 없다"
    assert "settlementOpsMounted" in js, "마운트 멱등 표식이 없다"


def test_js_binds_listeners_inside_the_root_not_on_document():
    """클릭 리스너를 `document` 가 아니라 루트 안쪽에 위임한다(perf G4).

    document 에 달면 스왑마다 전역 리스너가 쌓인다. 싱글톤 가드는 스왑 이벤트 전용이다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    bind = re.search(r"function bindControls\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    assert bind, "bindControls() 를 찾지 못했다"
    assert re.search(r"ctx\.root\.addEventListener\(\s*['\"]click['\"]", bind.group(1))
    assert not re.search(r"document\.addEventListener\(\s*['\"](click|keydown)['\"]", js), (
        "클릭 리스너를 document 에 달았다 — 스왑마다 누적된다"
    )


def test_first_load_is_deferred_until_the_ops_tab_is_active():
    """첫 조회를 탭이 열릴 때로 미루고, 그 신호로 **셸이 이미 쓰는 루트 속성**을 읽는다.

    셸은 탭 전환 이벤트를 쏘지 않는다(`dashboard.js` 에 `dispatchEvent` 가 없다). CSS 가 이미
    SSOT 로 쓰는 `data-settlement-active-tab` 을 그대로 관찰한다 — 두 번째 신호를 발명하면
    한쪽만 고치는 회귀가 난다.
    """
    js = _read_code(f"static/{JS_ASSET}")

    watch = re.search(r"function watchTabActivation\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    assert watch, "watchTabActivation() 을 찾지 못했다"
    assert "data-settlement-active-tab" in watch.group(1), watch.group(1)[:300]
    assert "MutationObserver" in watch.group(1), "탭 활성화 관찰이 없다"
    assert "ensureLoaded(ctx)" in watch.group(1), "활성화 시 첫 조회가 없다"


def test_aging_bar_uses_css_width_not_measured_svg():
    """aging 막대를 폭 측정(SVG)이 아니라 **CSS 퍼센트 폭**으로 그린다.

    숨은 pane 은 `clientWidth === 0` 이라 그 사이에 그린 SVG 는 빈 그림으로 남고 다음
    리사이즈까지 스스로 낫지 않는다. 퍼센트 폭은 보이는 시점에 계산되므로 그 함정이 없다.
    """
    js = _read_code(f"static/{JS_ASSET}")
    css = _read_code(f"static/{CSS_ASSET}")

    assert "clientWidth" not in js, "폭 측정에 의존한다 — 숨은 pane 에서 빈 막대가 된다"
    assert "--s-ops-bar-pct" in js and "--s-ops-bar-pct" in css, "퍼센트 폭 토큰 배선이 없다"


def test_zero_bucket_draws_no_bar_at_all():
    """값이 0 인 aging 구간은 막대를 **아예 그리지 않는다**.

    막대에는 아주 작은 값도 보이게 하는 최소 폭(`min-width: 3px`)이 있다. 그 상태로 0 을
    그리면 "적지만 있다"는 거짓 신호가 된다 — 실화면에서 기간을 '7일 이내'로 좁혔더니 값이
    0 인 네 구간이 전부 3px 막대로 남는 것을 실측했다(2026-08-31). 요약 탭 aging 차트도
    같은 이유로 같은 계약을 갖는다.
    """
    js = _read_code(f"static/{JS_ASSET}")
    css = _read_code(f"static/{CSS_ASSET}")

    guard = re.search(r"if\s*\(\(bucket\.amount\s*\|\|\s*0\)\s*>\s*0\)\s*\{(.*?)\n      \}", js, re.S)
    assert guard, "0 구간의 막대를 건너뛰는 가드가 없다"
    assert "s-ops-aging-bar" in guard.group(1), "막대 생성이 그 가드 안에 있지 않다"
    assert re.search(r"\.s-ops-aging-bar\s*\{[^}]*min-width", css), (
        "양수 막대의 최소 폭 보장이 없다(가드의 전제)"
    )


# ==========================================================================
# 계약 12 — 셸 배선 (걸려 있으면 옳아야 한다)
# ==========================================================================
# include 와 자산 태그는 셸 템플릿에 들어가는데 그 파일은 이 작업의 소유가 아니다.
# "아직 안 걸림"으로 red 를 내지 않되, **걸리는 순간부터** 실제 게이트가 된다.
@pytest.mark.parametrize("asset", _STATIC_ASSETS)
def test_asset_pins_are_single_repo_wide_and_match_the_screen(asset):
    """자산 하나당 `?v=` 핀이 저장소 전역에서 **하나**이고, 요약 탭 자산과 **같은 값**이다.

    두 곳에서 다른 핀을 걸면 어느 한쪽이 항상 stale 을 만든다(서비스워커 staticCacheFirst).
    기대값을 리터럴로 박지 않고 요약 탭 CSS 의 현재 핀을 읽어 비교한다 — 정산 화면 자산은
    한 핀으로 함께 움직이는 것이 계약이고, 값 자체는 배포마다 바뀐다.
    아직 배선 전이면 핀이 0 개다 — 그때는 "갈리지 않았다"만 확인한다.
    """
    pattern = re.compile(re.escape(asset) + _PIN_SUFFIX)
    pins = {
        pin
        for path in _repo_pin_scan_sources()
        for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
    }
    common = _settlement_common_pin()

    assert len(pins) <= 1, f"{asset}: 핀이 갈렸다 {sorted(pins)}"
    if pins and common:
        assert pins == {common}, (
            f"{asset}: 핀 {sorted(pins)} 이 정산 화면 공통 핀 {common!r} 과 다르다"
        )


@pytest.mark.skipif(not _shell_is_wired(), reason="셸 include 는 다른 작업이 건다(배선 후 활성)")
def test_wired_shell_includes_the_partial_once_with_pinned_deferred_assets():
    """배선되면: include 1회 + CSS/JS 핀 + `<script defer>` 가 함께 있어야 한다.

    셸에 include 만 넣고 자산 태그를 빠뜨리면 "스타일도 기능도 없는 화면"이 된다
    (project_page_scope_script_v3_shell_gap 과 같은 계열). defer 가 빠지면 ERP 탭 전체가
    느려진다(perf G1).
    """
    shell = _strip_comments(_read(_SHELL_TEMPLATE))
    common = _settlement_common_pin()

    assert shell.count(_TEMPLATE_NAME) == 1, "include 가 없거나 중복이다"
    assert common, "요약 탭 CSS 의 공통 핀을 읽지 못했다"
    for asset in _STATIC_ASSETS:
        assert asset in shell, f"{asset} 링크가 셸에 없다"
        assert _pins_for(asset, shell) == {common}, f"{asset} 핀이 공통 핀 {common!r} 과 다르다"
    tag = next(
        (m.group(0) for m in _SCRIPT_TAG_RE.finditer(shell) if JS_ASSET in m.group(0)),
        None,
    )
    assert tag, f"{JS_ASSET} script 태그가 없다"
    assert re.search(r"\bdefer\b", tag), tag


@pytest.mark.skipif(not _shell_is_wired(), reason="셸 include 는 다른 작업이 건다(배선 후 활성)")
def test_wired_shell_puts_the_partial_inside_the_ops_mount():
    """배선되면: include 가 실무 탭 마운트 **안쪽**이어야 한다.

    pane 자체와 `role`/`aria-*`/`hidden` 배선은 셸 소유다. 마운트 밖에 넣으면 요약 탭에서도
    이 화면이 그대로 보인다 — 탭을 나눈 의미가 사라진다.
    """
    shell = _strip_comments(_read(_SHELL_TEMPLATE))

    mount_at = shell.find('id="foms-settle-ops-mount"')
    analytics_at = shell.find('id="foms-settle-pane-analytics"')
    include_at = shell.find(_TEMPLATE_NAME)
    assert 0 <= mount_at < include_at, "include 가 실무 탭 마운트보다 앞에 있다"
    assert analytics_at < 0 or include_at < analytics_at, "include 가 분석 pane 으로 넘어갔다"


# ==========================================================================
# 계약 12 — aging 막대는 **목록과 같은 응답**으로 그린다 (P1 성능 개선)
#
# 예전 화면은 구간마다 `aging=<code>` 로 5번 더 물었다. 한 요청이 모집단 전량 스캔이라
# 스코프를 한 번 바꿀 때마다 같은 스캔이 6번 돌았다(2026-08-31 운영 실측: 막대까지 2.9초).
# 되돌아가는 것을 막는 계약이다 — 조회 호출부는 **하나**여야 한다.
# ==========================================================================
def test_js_draws_the_aging_strip_from_the_list_response():
    """서버가 함께 낸 `aging_summary` 로 막대를 그린다."""
    js = _read_code(f"static/{JS_ASSET}")

    assert "aging_summary" in js, "구간 합계를 응답에서 읽지 않는다"


def test_js_has_exactly_one_read_call_site():
    """조회 호출부가 하나다 — 구간마다 따로 묻는 루프가 되살아나면 red.

    호출부가 늘어나는 것 자체가 회귀 신호다(스코프 변경 1회 = 모집단 전량 스캔 1회).
    """
    js = _read_code(f"static/{JS_ASSET}")

    assert js.count("getJson(") == 2, (
        "조회 호출부가 하나가 아니다(정의 1 + 호출 1 이 정상) — 구간별 반복 조회 의심"
    )
    assert "loadBuckets" not in js, "구간별 조회 루프가 남아 있다"


def test_render_all_includes_the_aging_strip():
    """`renderAll` 이 막대까지 다시 그린다 — 목록만 갱신되고 막대가 옛 스코프로 남으면 안 된다."""
    js = _read_code(f"static/{JS_ASSET}")

    body = re.search(r"function renderAll\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    assert body, "renderAll 을 찾지 못했다"
    assert "renderAging(" in body.group(1), "renderAll 이 aging 막대를 안 그린다"
