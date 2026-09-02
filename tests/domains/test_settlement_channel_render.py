"""NAVER-SETTLE-01 §6: 채널(네이버) 정산 **탭 화면** 계약 테스트.

권한 판정 자체는 `test_settlement_channel_access.py` 가, 조회 API 는 별도 파일이 덮는다.
**이 파일은 그걸 중복하지 않는다.** 여기서 잠그는 것은 "그 게이트를 통과한 사람이 실제로
받는 마크업과 그 화면이 싣는 자산"이다 — 즉 이식하다 놓치면 조용히 망가지는 것들:

1. **권한 누출** — 채널 정산은 회계 자료다. 게이트 밖 사용자(정산 화면 자체는 보는
   STAFF+CS)의 응답에 탭·pane·자산 링크가 **한 조각도** 없어야 한다. 감추기(`hidden`/CSS)는
   개발자 도구로 그대로 보이므로 서버가 마크업째 빼는 것까지가 계약이다.
2. **자산 캐시 핀(`?v=`)** — 서비스워커가 static 을 cache-first 로 잡는다. 핀이 없거나
   저장소 안에서 갈라지면 배포해도 실기기가 옛 CSS/JS 를 계속 실행한다
   (project_sw_stale_js_version_bump).
3. **렌더 차단 스크립트(perf G1) / 외부 CDN(perf G2)** — 차트는 자체 인라인 SVG 다.
4. **인라인 스타일 / `|tojson`** — 프로젝트 절대 규칙.
5. **상태 노드 소유** — 세 탭이 **한 루트(`#foms-settlement-root`) 안**에 산다.
   요약 탭 `dashboard.js` 의 `collectEls()` 는 루트 전체를 `querySelector` 로 훑으므로 이름이
   겹치면 서로의 노드를 잡는다. 특히 상태 노드가 그렇다 — 남의 로딩/실패를 켜면 **숨은 pane
   안에서** 켜져 사용자는 아무것도 못 본다.
6. **앵커 전량** — JS 가 채우기 전에도 자리가 있어야 fetch 실패가 "빈 카드"가 아니라
   "무엇이 비었는지"로 보인다.
7. **축 라벨** — 이 화면의 합계는 요약/분석 탭과 **원래 다르다**(정산 예정일 vs 완료일).
   화면이 그 사실을 상시로 말하지 않으면 "숫자가 안 맞는다"는 오해가 반복된다.
8. **"정산" 이라는 맨이름 금지** — 같은 화면에 이미 정산 대시보드가 있다. 수식어 없는
   `정산` 라벨은 어느 정산인지 말하지 못한다.

**검사 층위(의도적으로 둘)** — *렌더*(실제 GET 결과)와 *소스 리터럴*(파일 원문).
`docs/` 는 읽지 않는다(CI-DOCSCOPE-01).

`static/css/settlement/settlement-channel.css`·`static/js/settlement/channel.js` 의 **내용**은
다른 작업(A4)이 소유한다. 이 파일은 자산이 실재하고 링크·핀·defer 가 옳은지까지만 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import render_template

# 프래그먼트 요청 의미론을 그대로 쓰기 위해 요약 탭 계약 테스트의 헬퍼를 재사용한다
# (복제하면 헤더 계약이 갈려 "전체 페이지가 와서 검사가 통째로 어긋나는" 함정을 탄다).
from tests.domains.test_settlement_dashboard_render import (  # noqa: E402
    _fragment_html,
    _login_allowed,
)

_ROOT = Path(__file__).resolve().parents[2]

#: 이 작업이 소유한 마크업.
BODY_TEMPLATE = "templates/cs/partials/settlement_channel_body.html"
#: 셸이 include 를 걸어야 하는 대상.
_TEMPLATE_NAME = "cs/partials/settlement_channel_body.html"
#: 셸 템플릿(탭 버튼·pane·자산 링크가 사는 곳).
_SHELL_TEMPLATE = "templates/cs/partials/settlement_dashboard_body.html"

CSS_ASSET = "css/settlement/settlement-channel.css"
JS_ASSET = "js/settlement/channel.js"
_STATIC_ASSETS = (CSS_ASSET, JS_ASSET)

#: 이 화면 자산의 캐시 핀. **저장소 전역에서 이 값 하나**여야 한다. CSS/JS 를 고치면
#: 셸 템플릿의 두 링크와 이 상수를 **함께** 옮긴다 — 값이 조용히 갈리면 실기기가 옛 자산을
#: 계속 실행한다(서비스워커 staticCacheFirst).
_CHANNEL_PIN = "20260902d"

_CHANNEL_TAB_ID = "foms-settle-tab-channel"
_CHANNEL_PANE_ID = "foms-settle-pane-channel"

#: 상시 축 라벨. 이 화면의 축(정산 예정일)이 요약/분석 탭의 매출 인식 축(완료일)과 다르다는
#: 사실을 늘 말한다 — 두 화면 합계가 안 맞는다는 문의가 반복되는 자리다.
_AXIS_LABEL = "정산 예정일 기준 · 매출 인식(완료일)과 다릅니다"

#: 서버 렌더 시점에 있어야 하는 앵커(계약서 §6 전량).
_REQUIRED_ANCHORS = {
    "루트": 'id="foms-settle-channel-root"',
    "루트 훅": "data-settlement-ch-root",
    "조회 API URL": 'data-settlement-ch-api="/api/settlement/channel"',
    "동기화 API URL": 'data-settlement-ch-sync-api="/api/settlement/channel/sync"',
    "채널 코드": 'data-settlement-ch-channel="NAVER"',
    "S0 동기화 헤더": 'id="foms-settle-ch-sync"',
    "동기화 버튼": "data-settlement-ch-sync-btn",
    "기간 바": 'id="foms-settle-ch-bar"',
    "기준일 셀렉트": "data-settlement-ch-basis",
    "시작일": "data-settlement-ch-from",
    "종료일": "data-settlement-ch-to",
    "집계 단위": "data-settlement-ch-granularity",
    "KPI 호스트": 'id="foms-settle-ch-kpi"',
    "일별 차트 호스트": 'id="foms-settle-ch-daily"',
    "워터폴 호스트": 'id="foms-settle-ch-waterfall"',
    "입금 채널 호스트": 'id="foms-settle-ch-deposit"',
    "대사 배너 호스트": 'id="foms-settle-ch-reconcile"',
    "원장 스위처": 'id="foms-settle-ch-ledger-switch"',
    "원장 호스트": 'id="foms-settle-ch-ledger"',
    "로딩 표시": "data-settlement-ch-loading",
    "실패 표시": "data-settlement-ch-error",
    "빈 상태 표시": "data-settlement-ch-empty",
}

#: 원장 스위처 버튼 값 4종. 하나라도 빠지면 사용자가 그 원장을 화면에서 열 수 없다.
_LEDGER_VALUES = ("case", "commission", "vat", "exceptions")

#: 상태 3종 훅. 서버 렌더 시점엔 셋 다 닫혀 있어야 한다.
_STATE_ANCHORS = (
    "data-settlement-ch-loading",
    "data-settlement-ch-error",
    "data-settlement-ch-empty",
)

#: 요약·실무 탭이 루트 전체에서 `querySelector` 로 찾는 이름들. 재사용하면 서로의 노드를 잡는다.
_OTHER_TAB_SELECTORS = (
    "data-settlement-loading",
    "data-settlement-error",
    "data-settlement-denied",
    "data-settlement-grid",
    "data-settlement-empty=",
    "data-settlement-retry",
    "data-settlement-granularity=",
    "data-settlement-compare",
    "data-settlement-cumulative",
    "data-settlement-kpi=",
    "data-settlement-stage",
    "data-settlement-range",
    "data-settlement-stamp",
    "data-settlement-ops-",
    'class="s-filterbar"',
    'class="s-tabs"',
)

#: 목업 잔재(요약·실무 탭과 같은 어휘). "예정" 은 여기서 **따로** 본다 — 아래 전용 테스트 참조.
_MOCKUP_LEFTOVERS = ("MOCKUP", "가정치", "해피콜")

_EXTERNAL_URL_RE = re.compile(r"https?://(?!www\.w3\.org[/\"'])[^\s\"'<>()]+")
_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(.*?)\1[^>]*>", re.I | re.S)
_STYLE_ATTR_RE = re.compile(r"\bstyle\s*=\s*['\"]")
_PIN_SUFFIX = r"['\"\s\}\)]*\?v=([A-Za-z0-9._-]+)"
_PIN_SCAN_EXCLUDE = {".git", "node_modules", ".superpowers", "docs"}

_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.S)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_JS_LINE_COMMENT_RE = re.compile(r"(?m)^\s*//.*$")


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _read(rel: str) -> str:
    """저장소 상대 경로 파일을 읽는다. 없으면 사람이 읽는 red 로 죽인다."""
    path = _ROOT / rel
    assert path.exists(), f"채널 탭 산출물이 없다: {rel}"
    return path.read_text(encoding="utf-8", errors="ignore")


def _strip_comments(text: str) -> str:
    """주석(Jinja/HTML/JS)을 걷어낸 사본을 돌려준다(금지 패턴 검사 전처리).

    규칙을 **설명하는 주석**이 그 규칙 위반으로 잡히는 거짓 red 를 막는다.
    """
    text = _JINJA_COMMENT_RE.sub(" ", text)
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _JS_BLOCK_COMMENT_RE.sub(" ", text)
    return _JS_LINE_COMMENT_RE.sub(" ", text)


def _read_code(rel: str) -> str:
    """파일을 읽고 주석을 제거한 본문을 돌려준다."""
    return _strip_comments(_read(rel))


def _render(app) -> str:
    """채널 탭 파셜을 **단독으로** 렌더한다.

    파셜 단독 렌더는 `UndefinedError` 함정(매크로/변수 기본값 누락)까지 같이 잡는다 —
    셸이 이 파셜을 `{% if %}` 안에서 include 하므로, 컨텍스트 누락으로 죽으면 화면 전체가
    500 이 된다.
    """
    with app.test_request_context("/erp/settlement"):
        return render_template(_TEMPLATE_NAME)


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


def _channel_surface(html: str) -> str:
    """렌더 결과에서 채널 탭 버튼 + pane 만 잘라낸다(문구 계약을 이 표면 안에서만 본다)."""
    tab = re.search(
        r'<button\s[^>]*\sid="%s".*?</button>' % re.escape(_CHANNEL_TAB_ID), html, re.S
    )
    pane_at = html.find(f'id="{_CHANNEL_PANE_ID}"')
    assert pane_at >= 0, "채널 pane 이 렌더에 없다"
    end = html.find('id="foms-settle-tooltip"', pane_at)
    assert end > pane_at, "채널 pane 의 끝(툴팁)을 찾지 못했다"
    return (tab.group(0) if tab else "") + html[pane_at:end]


# ==========================================================================
# 계약 0 — 산출물 실재
# ==========================================================================
@pytest.mark.parametrize("rel", (BODY_TEMPLATE, f"static/{CSS_ASSET}", f"static/{JS_ASSET}"))
def test_channel_sources_exist_and_are_not_empty(rel):
    """템플릿·CSS·JS 3종이 실재하고 빈 파일이 아니다.

    경로가 흔들리면 include·서비스워커 캐시 키·핀 계약이 전부 따로 논다. CSS/JS 의 **내용**은
    다른 작업(A4)이 채우므로 여기서는 실재와 비어있지 않음까지만 본다 — 분량 계약을 지금
    걸면 아직 안 쓴 파일을 영구 red 로 만든다.
    """
    assert _read(rel).strip(), f"{rel} 가 비어 있다"


# ==========================================================================
# 계약 1 — 앵커 전량 (JS 가 채우기 전에도 자리가 있어야 한다)
# ==========================================================================
@pytest.mark.parametrize("name,anchor", sorted(_REQUIRED_ANCHORS.items()))
def test_rendered_partial_carries_every_anchor(app, name, anchor):
    """파셜 렌더 결과가 계약 앵커를 전부 갖는다."""
    html = _render(app)

    assert anchor in html, f"{name} 앵커가 없다: {anchor}"


@pytest.mark.parametrize("value", _LEDGER_VALUES)
def test_ledger_switch_offers_every_ledger(app, value):
    """원장 스위처가 4종(건별·수수료·부가세·예외)을 전부 낸다."""
    html = _render(app)

    assert f'data-settlement-ch-ledger="{value}"' in html, value


def test_ledger_switch_uses_aria_pressed_for_selection(app):
    """원장 선택 상태를 `aria-pressed` 로 말한다(색만으로 말하지 않는다)."""
    html = _render(app)

    pressed = re.findall(
        r'data-settlement-ch-ledger="([^"]+)"[^>]*aria-pressed="true"', html
    )
    assert pressed == ["case"], pressed


@pytest.mark.parametrize("anchor", _STATE_ANCHORS)
def test_state_nodes_start_closed(app, anchor):
    """상태 3종은 서버 렌더 시점에 닫혀 있다(`hidden`).

    열린 채로 나오면 JS 가 켜기 전에 로딩/실패/빈 상태가 한꺼번에 보인다.
    """
    html = _render(app)

    at = html.find(anchor)
    assert at >= 0, anchor
    tag = html[html.rfind("<", 0, at):html.find(">", at) + 1]
    assert re.search(r"\shidden(\s|/?>)", tag), tag


def test_state_nodes_are_three_distinct_nodes(app):
    """로딩·실패·빈 상태가 **서로 다른 노드**다.

    하나로 합치면 "느린 것"과 "죽은 것"과 "0건인 것"이 같은 화면이 되어 원인을 못 가른다.
    """
    html = _render(app)

    positions = {anchor: html.find(anchor) for anchor in _STATE_ANCHORS}
    assert all(p >= 0 for p in positions.values()), positions
    assert len(set(positions.values())) == 3, positions
    for anchor in _STATE_ANCHORS:
        start = html.find(anchor)
        assert re.search(r"[가-힣]{2,}", html[start:start + 400]), f"{anchor}: 한글 안내가 없다"


# ==========================================================================
# 계약 2 — 상태 노드 소유 (요약·실무 탭과 이름을 나눈다)
# ==========================================================================
@pytest.mark.parametrize("selector", _OTHER_TAB_SELECTORS)
def test_surface_does_not_reuse_other_tab_selectors(selector):
    """요약·실무 탭이 루트 전체에서 찾는 이름을 재사용하지 않는다.

    세 탭은 **같은 루트(`#foms-settlement-root`) 안**에 산다. `collectEls()` 가
    `root.querySelector(...)` 로 훑으므로 같은 이름을 쓰면 서로의 노드를 잡는다.
    """
    assert selector not in _read_code(BODY_TEMPLATE), f"다른 탭 선택자 재사용: {selector}"


def test_every_state_hook_is_channel_prefixed(app):
    """이 파셜이 쓰는 `data-settlement-*` 훅은 **전부** `data-settlement-ch-` 접두어다."""
    html = _render(app)

    hooks = set(re.findall(r"\bdata-settlement-[a-z-]+", html))
    stray = {h for h in hooks if not h.startswith("data-settlement-ch-")}
    assert not stray, f"접두어 밖 훅 {sorted(stray)}"


# ==========================================================================
# 계약 3 — 축 라벨 / 라벨 문구
# ==========================================================================
def test_axis_label_is_permanent_in_the_partial(app):
    """축 라벨이 파셜 렌더에 상시로 있다.

    이 화면의 합계는 요약/분석 탭과 **원래 다르다**(정산 예정일 축 vs 완료일 축).
    화면이 그 사실을 말하지 않으면 "숫자가 안 맞는다"는 오해가 반복된다.
    """
    html = _render(app)

    assert _AXIS_LABEL in html


def test_axis_label_survives_the_page_render(client, app):
    """실제 페이지 렌더(프래그먼트)에도 축 라벨이 실린다 — include 가 꺼지는 회귀를 잡는다."""
    _login_allowed(client)

    assert _AXIS_LABEL in _fragment_html(client)


def test_permanent_notices_are_not_autodismissed_alerts():
    """상시 안내를 Bootstrap `.alert` 로 만들지 않는다(5초 뒤 자동으로 닫힌다).

    부득이 쓴다면 `data-foms-no-autodismiss` 가 함께 있어야 한다
    (project_alert_autodismiss_trap). 축 라벨이 사라지면 이 화면은 자기 축을 잃는다.
    """
    body = _read_code(BODY_TEMPLATE)

    for match in re.finditer(r'class="[^"]*\balert\b[^"]*"', body):
        tag_start = body.rfind("<", 0, match.start())
        tag_end = body.find(">", match.end())
        tag = body[tag_start:tag_end + 1]
        assert "data-foms-no-autodismiss" in tag, f"자동닫힘 .alert: {tag[:160]}"


def test_no_bare_settlement_label_in_the_channel_surface(client, app):
    """수식어 없는 `정산` 라벨을 쓰지 않는다.

    같은 화면에 이미 "정산 대시보드"가 있다. 맨이름 `정산` 은 어느 정산인지 말하지 못한다 —
    탭 이름은 "네이버 정산" 이다.
    """
    _login_allowed(client)

    surface = _strip_comments(_channel_surface(_fragment_html(client)))

    assert ">정산<" not in surface, "수식어 없는 '정산' 라벨이 있다"
    assert "네이버 정산" in surface, "탭 이름이 렌더에 없다"


@pytest.mark.parametrize("phrase", _MOCKUP_LEFTOVERS)
def test_channel_surface_has_no_mockup_leftovers(phrase, app):
    """목업 잔재 문구가 이 표면에도 없다(요약·실무 탭과 같은 규율)."""
    assert phrase not in _read_code(BODY_TEMPLATE), f"목업 잔재 '{phrase}'"
    assert phrase not in _render(app)


def test_the_only_expected_word_is_the_settlement_expect_date(app):
    """"예정" 은 **"정산 예정일"** 자리에서만 쓴다.

    요약·실무 탭은 "예정" 을 목업 잔재(근거 없는 미구현 배지)로 보고 통째로 금지한다.
    이 화면에서만 예외인 이유는 네이버 정산 API 의 축 이름(`settleExpectDate`)이기
    때문이다 — 그 예외가 "아무 데나 예정을 써도 된다"로 번지지 않게 자리를 못박는다.
    요약 탭 계약(`test_settlement_dashboard_render.py::_without_channel_surface`)이 이
    표면을 덜어내고 보는 대신, 그만큼을 여기서 대신 잠근다.
    """
    for text in (_read_code(BODY_TEMPLATE), _strip_comments(_render(app))):
        residue = text.replace("정산 예정일", " ")
        assert "예정" not in residue, "‘정산 예정일’ 밖에서 '예정' 을 쓰고 있다"


# ==========================================================================
# 계약 4 — 권한: 게이트 밖에는 한 조각도 나가지 않는다
# ==========================================================================
_CHANNEL_MARKUP_NEEDLES = (
    _CHANNEL_TAB_ID,
    _CHANNEL_PANE_ID,
    'id="foms-settle-channel-root"',
    "data-settlement-ch-root",
    CSS_ASSET,
    JS_ASSET,
)


@pytest.mark.parametrize("role,team", [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")])
@pytest.mark.parametrize("needle", _CHANNEL_MARKUP_NEEDLES)
def test_allowed_actors_receive_the_channel_surface(client, app, role, team, needle):
    """ADMIN·회계팀(MANAGER/STAFF) 렌더에는 채널 탭·pane·자산이 전부 실린다."""
    _login_allowed(client, role=role, team=team)

    assert needle in _fragment_html(client), (role, team, needle)


@pytest.mark.parametrize("needle", _CHANNEL_MARKUP_NEEDLES)
def test_denied_actor_receives_no_channel_markup_at_all(client, app, needle):
    """STAFF+CS(정산 화면 자체는 보는 사용자) 렌더에는 채널 마크업이 **0** 이다.

    감추기가 아니라 서버가 빼는 것까지가 계약이다 — 감추기만 하면 개발자 도구로 그대로 보이고,
    자산 링크가 남으면 회계 전용 화면의 구조가 그대로 노출된다.
    """
    _login_allowed(client, role="STAFF", team="CS")

    assert needle not in _fragment_html(client), needle


def test_denied_actor_still_sees_the_settlement_dashboard(client, app):
    """게이트가 채널 탭만 닫는다 — 정산 대시보드 자체는 그대로 열린다(과잉 차단 방지)."""
    _login_allowed(client, role="STAFF", team="CS")

    html = _fragment_html(client)

    assert 'id="foms-settlement-root"' in html
    assert 'id="foms-settle-pane-summary"' in html


# ==========================================================================
# 계약 5 — 자산 핀 / defer / 외부 CDN / 인라인 스타일
# ==========================================================================
@pytest.mark.parametrize("asset", _STATIC_ASSETS)
def test_channel_asset_pins_are_single_repo_wide(asset):
    """자산 하나당 `?v=` 핀이 저장소 전역에서 **정확히 하나**이고 계약 값과 같다.

    두 곳에서 다른 핀을 걸면 어느 한쪽이 항상 stale 을 만든다(서비스워커 staticCacheFirst).
    CSS/JS 를 고칠 때는 셸 템플릿의 링크와 :data:`_CHANNEL_PIN` 을 **함께** 옮긴다.
    """
    pattern = re.compile(re.escape(asset) + _PIN_SUFFIX)
    pins = {
        pin
        for path in _repo_pin_scan_sources()
        for pin in pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))
    }

    assert pins == {_CHANNEL_PIN}, f"{asset}: 핀 {sorted(pins)}"


def test_shell_includes_the_partial_once_behind_the_gate():
    """셸이 이 파셜을 **한 번**, 그리고 권한 `{% if %}` 안에서 include 한다."""
    shell = _strip_comments(_read(_SHELL_TEMPLATE))

    assert shell.count(_TEMPLATE_NAME) == 1, "include 가 없거나 중복이다"
    include_at = shell.index(_TEMPLATE_NAME)
    gate_at = shell.rfind("{% if can_view_channel_settlement %}", 0, include_at)
    endif_at = shell.find("{% endif %}", include_at)
    assert gate_at >= 0 and endif_at > include_at, "include 가 권한 게이트 밖에 있다"


@pytest.mark.parametrize("asset", _STATIC_ASSETS)
def test_shell_links_the_asset_behind_the_gate(asset):
    """CSS/JS 링크도 같은 권한 게이트 안에 있다.

    마크업만 빼고 링크를 남기면 게이트 밖 사용자의 브라우저가 회계 화면 자산을 내려받는다.
    """
    shell = _strip_comments(_read(_SHELL_TEMPLATE))

    at = shell.index(asset)
    gate_at = shell.rfind("{% if can_view_channel_settlement %}", 0, at)
    endif_at = shell.find("{% endif %}", at)
    assert gate_at >= 0 and 0 < endif_at, f"{asset} 링크가 권한 게이트 밖에 있다"
    assert "{% endif %}" not in shell[gate_at:at], f"{asset} 링크가 게이트 밖에 있다"


def test_channel_script_tag_is_deferred():
    """채널 JS `<script>` 에 `defer` 가 있다(렌더 차단 금지, perf G1)."""
    shell = _strip_comments(_read(_SHELL_TEMPLATE))

    tag = next((m.group(0) for m in _SCRIPT_TAG_RE.finditer(shell) if JS_ASSET in m.group(0)), None)
    assert tag, f"{JS_ASSET} script 태그가 없다"
    assert re.search(r"\bdefer\b", tag), tag


def test_channel_script_tag_is_deferred_in_the_render(client, app):
    """렌더 결과의 `<script>` 태그에도 `defer` 가 살아 있다."""
    _login_allowed(client)

    html = _fragment_html(client)
    tag = next((m.group(0) for m in _SCRIPT_TAG_RE.finditer(html) if JS_ASSET in m.group(0)), None)

    assert tag, f"{JS_ASSET} script 태그가 렌더에 없다"
    assert re.search(r"\bdefer\b", tag), tag


@pytest.mark.parametrize("rel", (BODY_TEMPLATE, f"static/{CSS_ASSET}", f"static/{JS_ASSET}"))
def test_channel_sources_reference_no_external_host(rel):
    """템플릿·CSS·JS 어디에도 외부 호스트 참조가 없다(perf G2).

    차트는 자체 인라인 SVG 다. 전역 G2 가드는 **동기 `<script>` 태그만** 보므로
    `<link>`·`@import`·JS 안의 `fetch('https://...')` 는 사각이다.
    """
    hits = _EXTERNAL_URL_RE.findall(_read_code(rel))

    assert not hits, f"{rel}: 외부 호스트 참조 {hits[:5]}"


def test_template_has_no_inline_style_attribute_or_block():
    """템플릿에 `style="` 속성도 `<style>` 블록도 없다(프로젝트 절대 규칙)."""
    source = _read_code(BODY_TEMPLATE)

    assert not _STYLE_ATTR_RE.findall(source), "인라인 style 속성"
    assert "<style" not in source.lower(), "인라인 <style> 블록"


def test_rendered_partial_has_no_inline_style_attribute(app):
    """렌더 결과에도 인라인 style 이 없다(Jinja 로 조립해 넣는 경로까지 막는다)."""
    assert not _STYLE_ATTR_RE.findall(_render(app)), "렌더 결과에 인라인 style 속성"


def test_template_does_not_inline_parse_jinja_json():
    """`JSON.parse('{{ ... }}')`·`|tojson` 직접 파싱이 없다 — 초기값은 `data-*` 로 넘긴다."""
    source = _read_code(BODY_TEMPLATE)

    assert "JSON.parse('{{" not in source
    assert 'JSON.parse("{{' not in source
    assert not re.search(r"\|\s*tojson", source), "|tojson 직접 사용"


def test_template_adds_no_script_block_of_its_own():
    """파셜이 자기 `<script>` 블록을 들고 있지 않다.

    이 마크업은 ERP 셸 프래그먼트로 스왑돼 들어온다 — 인라인 스크립트는 스왑마다 다시
    실행되거나(중복 배선) 통째로 빠진다. 동작은 외부 `channel.js` 한 곳이다.
    """
    source = _read_code(BODY_TEMPLATE)

    assert "<script" not in source.lower(), "파셜 안에 <script> 가 있다"
