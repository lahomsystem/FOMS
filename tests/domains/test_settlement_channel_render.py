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
    PAGE_URL,
    _FRAGMENT_URL,
    _SHELL_HEADERS,
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
#: 2026-09-03 F9 — R1(축 셀렉트를 원장 줄로 이동)·C1(전환 뒤 셀렉트 되맞춤)·C2(창 밖으로
#: 밀린 행 수 문구)로 채널 CSS·JS 를 함께 고쳤다(핀 사슬 동반 이동: f → g).
#: 2026-09-03 F10 T1 — 검색어 `q` 를 원장 짝 판정 안으로 넣느라 채널 JS 를 고쳤다(g → h).
#: 2026-09-04 F10 MINOR-2 — 안내 줄이 설명 부제와 같은 모양이던 것을 경고 수식자로 갈랐다
#: (JS 클래스 + CSS 규칙 1개, h → i).
#: 2026-09-05 CFO 후속 — 라벨 6개·예외 머리(모집단 중 표시 수)·미매칭 금액/aging·전기 구간 라벨
#: (JS 만, i → 20260905a).
#: 2026-09-06 CFO 백로그 2차 — 보류 창 안 부호별 합·누적 잔액(B-02)·stale 문구/FAILED 헤더(F-01·F-08)·
#: SYNC_FAILED 배지(F-04)·버킷 일부 완료(N-02)·워터폴 2줄 라벨(G-07)·그룹 min-width(G-08a)
#: (JS + CSS, 직전 핀 → 20260906a).
#: 2026-09-06 CFO 백로그 3차 — 503 문구(F-02)·확정 구간 부제(B-01)·AMOUNT_DIFF 배지(D-03)·실무 탭 금액
#: 두 원값 병기 CSS(D-03)(JS + CSS, 20260906a → 20260906b; 셸 4줄도 operations.js 변경으로 20260906b).
#: 2026-09-08 동기화 진행 표시 — 워커가 남기는 진행을 2초마다 읽어 막대로 그린다
#: (JS + CSS + 파셜 앵커, 20260906b → 20260908a; 셸 5줄 동반 이동).
#: 2026-09-08 시각·대기창 수정 — 화면 시각이 UTC 로 9시간 어긋나던 것을 서울 시각으로,
#: 60초 확인 창이 실측 62초를 못 담아 성공해도 실패 문구가 뜨던 것을 150초로
#: (JS 만, 20260908a → 20260908c; 셸 6줄 동반 이동).
_CHANNEL_PIN = "20260908c"

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
    # v1.1 T14 — CSV 내보내기 드롭다운. 앵커만 서버가 내고 항목·안내는 `channel.js` 가 그린다.
    "CSV 내보내기": 'id="foms-settle-ch-export"',
}

#: v1.1 T12 — 요약 탭 크로스 스트립 앵커. **이 파셜이 아니라 셸 템플릿**에 산다(요약 pane
#: 안이라서). 그래서 파셜 렌더 계약(`_REQUIRED_ANCHORS`)이 아니라 셸 소스 계약으로 본다.
_STRIP_ANCHOR_ID = 'id="foms-settle-ch-strip"'
_STRIP_HOOK = "data-settlement-ch-strip"

#: `channel.js` 안에서 스트립이 사는 구간의 배너 표식(사이를 잘라 문구 계약을 본다).
_STRIP_SECTION_START = "12-B. 요약 탭 크로스 스트립"
_STRIP_SECTION_END = "13. 마운트"
#: CSV 내보내기 구간의 배너 표식.
_EXPORT_SECTION_START = "CSV 내보내기 드롭다운(T14)"
_EXPORT_SECTION_END = "6. 렌더 — S-bar · S1 KPI"

#: 이 파일이 등록해도 되는 전역(document) 리스너 수. 프래그먼트 스왑마다 스크립트가 다시
#: 실행되므로 싱글톤 뒤 3개(swap 2종 + DOMContentLoaded)가 계약이다 — v1.1 이 두 번째 마운트
#: 축(스트립)을 만들면서 네 번째를 붙이면 스왑마다 리스너가 누적된다(perf G4).
_DOCUMENT_LISTENERS = 3

_HANGUL_RE = re.compile(r"[가-힣]")

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
    # v1.1 T12 — 스트립 앵커는 **요약 pane 안**에 있어 채널 pane 을 통째로 빼도 남을 수
    # 있는 자리다. 여기 등재해 두면 게이트 밖 사용자에게 앵커가 0 이라는 사실을 권한
    # 테스트가 자동으로 못 박는다(회계 축의 존재 자체가 새어 나가지 않는다).
    _STRIP_HOOK,
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
def test_denied_actor_gets_no_channel_markup_because_page_is_closed(client, app, needle):
    """STAFF+CS 는 2026-09-03 부터 정산 화면 자체가 403 이라 채널 마크업도 **0** 이다.

    감추기가 아니라 서버가 아예 안 그리는 것까지가 계약이다 — 감추기만 하면 개발자
    도구로 그대로 보이고, 자산 링크가 남으면 회계 전용 화면의 구조가 노출된다.
    """
    _login_allowed(client, role="STAFF", team="CS")

    resp = client.get(_FRAGMENT_URL, headers=_SHELL_HEADERS)

    assert resp.status_code == 403, resp.status_code
    assert needle not in resp.get_data(as_text=True), needle


def test_non_accounting_staff_cannot_open_the_settlement_dashboard(client, app):
    """정산 대시보드는 회계팀·관리자 전용이다(사용자 결정 2026-09-03).

    그 전에는 CS/영업도 요약 탭을 봤다. 이 테스트가 red 로 잡는 것은 그 시절 권한으로
    되돌아가는 회귀다 — 전사 매출·미수 총액이 다시 전 팀에 열린다.
    """
    _login_allowed(client, role="STAFF", team="CS")

    fragment = client.get(_FRAGMENT_URL, headers=_SHELL_HEADERS)
    page = client.get(PAGE_URL)

    assert fragment.status_code == 403, fragment.status_code
    assert page.status_code == 403, page.status_code
    assert 'id="foms-settlement-root"' not in page.get_data(as_text=True)


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


# ==========================================================================
# 계약 6 — v1.1 T12: 요약 탭 크로스 스트립 앵커(셸 소유)
# ==========================================================================
def _shell_strip_gate() -> tuple[str, str]:
    """셸 템플릿에서 스트립 앵커를 감싼 권한 게이트 블록을 잘라 돌려준다.

    Returns:
        ``(주석 제거한 셸 전문, 게이트 블록 본문)``. 앵커가 없으면 사람이 읽는 red.
    """
    shell = _strip_comments(_read(_SHELL_TEMPLATE))
    at = shell.find(_STRIP_ANCHOR_ID)
    assert at >= 0, (
        "셸 템플릿에 크로스 스트립 앵커가 없다 — 총괄이 넣을 hunk 다: "
        f"{_STRIP_ANCHOR_ID}"
    )
    gate_at = shell.rfind("{% if can_view_channel_settlement %}", 0, at)
    endif_at = shell.find("{% endif %}", at)
    assert gate_at >= 0 and endif_at > at, "스트립 앵커가 권한 게이트 밖에 있다"
    assert "{% endif %}" not in shell[gate_at:at], "스트립 앵커가 권한 게이트 밖에 있다"
    return shell, shell[gate_at:endif_at]


def test_shell_carries_the_strip_anchor_behind_the_gate():
    """스트립 앵커가 셸에 **한 번**, 권한 `{% if %}` 안에 있다.

    스트립은 요약 pane 안(`.s-grid`)에 살기 때문에 채널 파셜이 아니라 셸이 소유한다.
    게이트 밖에 두면 회계 축의 존재 자체가 CS·영업 담당 화면에 노출된다 —
    이 저장소의 클라 숨김 금지 원칙에 따라 마크업째 없어야 한다.
    """
    shell, _block = _shell_strip_gate()

    assert shell.count(_STRIP_ANCHOR_ID) == 1, "스트립 앵커가 없거나 중복이다"
    assert shell.count(_STRIP_HOOK) >= 1, "스트립 훅 속성이 없다"


def test_shell_strip_anchor_carries_no_korean_text():
    """스트립 앵커 블록에 **한글 문구가 0건**이다 — 이건 계약이다.

    요약 탭 목업 스캔(`test_settlement_dashboard_render.py` `_MOCKUP_LEFTOVERS`)은
    "예정" 을 금지하고, 채널 표면을 덜어내는 `_without_channel_surface()` 는 **채널 탭
    버튼과 채널 pane 만** 덜어낸다. 스트립은 요약 pane 안이라 그 면제를 못 받는다 —
    서버 렌더로 "정산 예정"이 박히는 순간 그 스캔이 즉시 red 다.
    그래서 값·문구는 전부 `channel.js`(스캔 대상 밖) 소유이고 서버는 빈 앵커만 낸다.
    """
    _shell, block = _shell_strip_gate()

    found = _HANGUL_RE.findall(block)
    assert not found, f"스트립 앵커 블록에 한글 문구가 있다: {''.join(found)[:40]}"


def test_shell_strip_anchor_starts_hidden():
    """앵커는 `hidden` 으로 시작한다 — 값을 받기 전에 빈 줄이 자리를 차지하지 않는다."""
    _shell, block = _shell_strip_gate()

    assert re.search(r"\shidden(\s|/?>)", block), block[:200]


# ==========================================================================
# 계약 7 — v1.1: `channel.js` 소스 계약 (§5.1-⑥)
# ==========================================================================
def _js_section(start: str, end: str) -> str:
    """`channel.js` 에서 배너 표식 사이 구간을 잘라 **주석을 걷어낸** 본문을 돌려준다.

    Args:
        start: 시작 배너에 들어 있는 문자열.
        end: 다음 배너에 들어 있는 문자열.

    Returns:
        그 구간의 코드(주석 제거).
    """
    source = _read(f"static/{JS_ASSET}")
    start_at = source.find(start)
    assert start_at >= 0, f"channel.js 에 '{start}' 구간 배너가 없다"
    end_at = source.find(end, start_at)
    assert end_at > start_at, f"channel.js 에 '{end}' 구간 배너가 없다"
    # 두 표식은 배너 **주석 안**에 있다. 여는 `/*` 까지 되감아야 `_strip_comments()` 가 그
    # 배너를 주석으로 알아보고 걷어낸다 — 안 되감으면 규칙을 설명하는 주석 문장이 그 규칙
    # 위반으로 잡히는 거짓 red 가 난다.
    at = source.rfind("/*", 0, start_at)
    to = source.rfind("/*", start_at, end_at)
    return _strip_comments(source[at if at >= 0 else start_at:to if to > start_at else end_at])


def test_channel_js_registers_no_new_document_listener():
    """전역(document) 리스너는 **3개 그대로**다(swap 2종 + DOMContentLoaded).

    v1.1 은 두 번째 마운트 축(스트립)을 만들지만 새 전역 리스너를 붙이지 않는다 —
    프래그먼트 스왑마다 `<script src>` 가 재실행되므로 네 번째를 붙이면 스왑 횟수만큼
    리스너가 누적된다(perf G4). 스트립도 기존 `mountAll()` 을 그대로 탄다.
    """
    source = _read_code(f"static/{JS_ASSET}")

    assert source.count("document.addEventListener") == _DOCUMENT_LISTENERS, source.count(
        "document.addEventListener")


def test_strip_is_mounted_from_the_existing_mount_all():
    """스트립 마운트가 `mountAll()` **안**에 있다(별도 부트스트랩을 만들지 않는다)."""
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find("function mountAll()")
    assert at >= 0, "mountAll() 이 없다"
    body = source[at:source.find("\n  }", at)]

    assert "STRIP_SELECTOR" in body, "mountAll() 이 스트립 호스트를 돌지 않는다"
    assert "mountStrip" in body, "mountAll() 이 mountStrip 을 부르지 않는다"


def test_strip_copy_never_says_sales():
    """스트립 문구에 **"매출" 이 0건**이다(ceo-2 §B-3 지시 — 전부 "정산").

    요약 탭 5타일은 완료일 축의 **매출 인식**을 말하고 이 줄은 정산 예정일 축의 **정산**을
    말한다. 한 화면에서 두 낱말을 섞으면 어느 쪽이 매출인지 사람이 다시 헷갈린다.
    """
    assert "매출" not in _js_section(_STRIP_SECTION_START, _STRIP_SECTION_END)


def test_strip_opens_the_channel_tab_through_the_existing_tab_button():
    """스트립 버튼은 **기존 탭 버튼을 누른다** — 새 탭 API 를 만들지 않는다.

    `dashboard.js` 를 한 글자도 고치지 않는다는 것이 T12 의 완료 기준이다.
    """
    section = _js_section(_STRIP_SECTION_START, _STRIP_SECTION_END)

    assert 'data-settlement-tab="' in section, "탭 버튼 선택자가 없다"
    assert ".click()" in section, "탭 버튼을 누르지 않는다"


def test_strip_failure_is_silent_and_stays_hidden():
    """스트립 fetch 실패는 요약 탭에 배너를 띄우지 않는다(보조 정보이므로 무음이 옳다).

    실패했을 때 `showState(...,'error')` 를 부르면 **채널 탭의** 상태 노드가 숨은 pane
    안에서 켜져 사용자는 아무것도 못 본 채 화면만 반쯤 죽는다. 대신 아무것도 안 그린다 —
    0 을 그리지 않는 것이 핵심이다(결측을 0 으로 말하지 않는 계약 D-10).
    """
    section = _js_section(_STRIP_SECTION_START, _STRIP_SECTION_END)

    assert "showState" not in section, "스트립이 채널 탭 상태 노드를 만진다"
    assert ".catch(" in section, "실패 경로가 없다"


# ==========================================================================
# 계약 8 — v1.1 T14: CSV 내보내기 드롭다운 소스 계약
# ==========================================================================
def test_export_menu_navigates_instead_of_building_a_blob():
    """항목은 **링크**다 — `blob:` 다운로드는 인앱 웹뷰에서 막힌다(프로젝트 함정).

    `operations.js` 의 현재-페이지 CSV 는 blob 을 쓰지만 그 코드가 스스로 "서버에 파일
    엔드포인트가 생기기 전에는 정직하지 않다"고 적어 두었다. 이 드롭다운이 그 엔드포인트다.
    """
    section = _js_section(_EXPORT_SECTION_START, _EXPORT_SECTION_END)

    assert "createObjectURL" not in section, "blob 다운로드를 만들고 있다"
    assert "item.href" in section, "항목이 링크가 아니다"


def test_export_menu_offers_every_kind_from_the_kernel():
    """드롭다운이 커널의 CSV 5종을 전부 낸다(화면에서만 감춘 종류가 없다)."""
    from foms.services.settlement_channel_export import EXPORT_KINDS

    source = _read_code(f"static/{JS_ASSET}")

    for kind in EXPORT_KINDS:
        assert f"'{kind}'" in source, f"드롭다운에 {kind} 항목이 없다"


def test_export_url_carries_the_current_filter_bar():
    """내려받기 URL 이 지금 화면의 채널·기간·기준일을 그대로 싣는다.

    화면에서 좁혀 놓고 내려받은 파일이 전체 기간이면 그 파일은 다른 질문의 답이다.
    """
    section = _js_section(_EXPORT_SECTION_START, _EXPORT_SECTION_END)

    for param in ("kind=", "channel=", "from=", "to=", "basis="):
        assert param in section, f"내려받기 URL 에 {param} 가 없다"


# ==========================================================================
# 계약 v1.2 — F1 미연결 2갈래 배지 · F2 보류·한도 펼침 상세
# ==========================================================================
def test_exception_badge_knows_both_unmatched_kinds():
    """예외 배지가 `UNMATCHED`(워크벤치 대기)와 `UNLINKED`(수집 전 주문)를 **다른 색**으로 낸다.

    두 갈래는 조치하는 사람과 화면이 다르다(워크벤치 vs 수집 운영). 한 색이면 표에서
    갈래가 있다는 사실이 사라진다. 색 클래스는 CSS 에도 있어야 한다(없으면 조용히 회색).
    """
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find("function excKindClass")
    assert at >= 0, "excKindClass 가 없다"
    body = source[at:source.find("\n  }", at)]
    css = _read_code(f"static/{CSS_ASSET}")

    assert "'UNMATCHED'" in body and "'UNLINKED'" in body
    assert "return 'info'" in body, "UNLINKED 에 별도 색 클래스가 없다"
    assert ".s-ch-badge--info" in css, "CSS 에 info 배지 색이 없다"


def test_holdback_kpi_tile_toggles_a_detail_panel_without_a_document_listener():
    """"보류·한도" 타일이 버튼(role/aria-expanded)이고 `[data-settlement-ch-holdback-detail]` 패널을 펼친다.

    리스너는 타일 자신에만 붙는다 — 전역 리스너 수 계약(`_DOCUMENT_LISTENERS`)은 별도
    테스트가 잠근다. 키보드(Enter/Space)로도 열려야 한다(마우스 전용 펼침 금지).
    """
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find("function bindKpiToggle")
    assert at >= 0, "bindKpiToggle 이 없다"
    body = source[at:source.find("\n  }", at)]

    assert "'role', 'button'" in body and "'aria-expanded'" in body and "'tabindex', '0'" in body
    assert "e.key === 'Enter'" in body and "e.key === ' '" in body
    assert "function renderHoldbackDetail" in source
    assert "data-settlement-ch-holdback-detail" in source
    assert "holdbackOpen" in source, "펼침 상태가 ctx.state 에 없다(재렌더마다 닫힌다)"


def test_holdback_detail_table_shows_both_naver_columns_and_a_total_row():
    """상세 표가 payHoldbackAmount·settlementLimitAmount 두 열과 합계(tfoot)를 낸다.

    -1.2억 의 원인 추적이 이 표의 목적이다 — 두 열을 합쳐 하나로 내면 어느 축의 보류인지
    다시 못 가른다. 합계는 서버 `total` 을 그리기만 한다(화면 재계산 금지).
    """
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find("function renderHoldbackDetail")
    body = source[at:source.find("\n  }", at)]

    assert "'pay_holdback'" in body and "'settlement_limit'" in body
    assert "el('tfoot')" in body and "block.total" in body
    assert "'정산 예정일'" in body


# ==========================================================================
# 계약 — 기준일 셀렉트(2026-09-03): 위쪽 축 라벨은 예정일 고정, 원장 축은 원장 머리가 말한다
# ==========================================================================
def test_axis_note_and_daily_head_never_follow_the_basis_select():
    """축 안내문·일별 차트 제목에 `basis_label` 을 찍지 않는다.

    KPI·일별 차트·워터폴은 셀렉트와 무관하게 늘 정산 예정일이다. 거기에 선택 라벨을 찍으면
    "완료일 기준 · 매출 인식(완료일)과 다릅니다" 같은 자기모순이 난다(스테이징 실측).
    """
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find("function syncControls(")
    body = source[at:source.find("\n  }", at)]
    assert "basis_label" not in body, "축 안내문이 셀렉트 라벨을 따라간다"
    assert "정산 예정일 기준 · 매출 인식(완료일)과 다릅니다" in body

    at = source.find("function renderDaily(")
    body = source[at:source.find("\n  }", at)]
    assert "basis_label" not in body, "일별 차트 제목이 셀렉트 라벨을 따라간다"
    assert "'정산 예정일 기준 · 취소·환급은 0선 아래로 그립니다'" in body


def test_ledger_axis_is_locked_per_ledger_kind_and_announced():
    """원장마다 있는 축만 고를 수 있고(옵션 disabled), 표 머리가 실제 적용 축·되돌림·제외 건수를 말한다."""
    source = _read_code(f"static/{JS_ASSET}")

    assert "var LEDGER_BASES" in source
    for kind in ("case:", "commission:", "vat_case:"):
        assert kind in source[source.find("var LEDGER_BASES"):source.find("var LEDGER_BASES") + 400]
    assert "opt.disabled = allowed.indexOf(opt.value) < 0" in source
    assert "function renderLedgerAxisNote(" in source
    assert "axis.supported === false" in source and "axis.excluded" in source
    # 행 그룹 축은 서버가 확정한 축(ledger.axis.basis)을 쓴다 — 선택값과 어긋나면 그룹이 빈다.
    assert "rowDateOf(row, kind, ledgerAxisBasis(ledger, ctx))" in source


# ==========================================================================
# 계약 — F8 적재 안 된 구간 받아오기 (2026-09-03)
# ==========================================================================
def test_backfill_banner_is_wired_through_the_existing_sync_path():
    """배너·버튼 훅이 있고, 버튼은 기존 `requestSync` 에 시작일을 넘기며, 폴링만 길어진다(10분).

    새 전역 리스너·새 fetch 경로를 만들지 않는다 — 소급 적재는 워커가 창을 쪼개 받아오므로 화면은
    큐에 부탁하고 rev 를 기다리기만 한다. 버튼 없는 자동 적재는 계약 밖(넓은 구간 오선택 = 수백 호출).
    """
    source = _read_code(f"static/{JS_ASSET}")
    css = _read_code(f"static/{CSS_ASSET}")

    assert "function renderBackfillBanner(" in source
    assert "'data-settlement-ch-backfill'" in source and "'data-settlement-ch-backfill-btn'" in source
    assert "requestSync(ctx, backfillBtn.getAttribute('data-from')" in source
    assert "var POLL_MAX_TRIES_BACKFILL = 60" in source
    assert "startRevPoll(ctx, backfillFrom ? POLL_MAX_TRIES_BACKFILL : POLL_MAX_TRIES)" in source
    assert "from < sync.coverage_from" in source, "배너 조건(요청 시작일 < 적재 시작일)이 없다"
    assert ".s-ch-backfill" in css and ".alert" not in css
    assert source.count("document.addEventListener") == _DOCUMENT_LISTENERS


# ==========================================================================
# 계약 — F9 (2026-09-03): 축 셀렉트 이동(R1) · 전환 뒤 되맞춤(C1) · 밀린 행 수(C2) ·
#                          구매자명(R5) · 정산내역 시트 항목(R5c)
# ==========================================================================
def _element_block(html: str, anchor: str) -> str:
    """렌더 결과에서 `anchor` 를 가진 최상위 `<div>` 블록만 잘라 돌려준다.

    두 줄(기간 바 · 원장 스위처)이 **서로 무엇을 갖고 무엇을 안 갖는지**를 보려면 문서
    전체가 아니라 블록 단위로 봐야 한다. 최상위 블록은 두 칸 들여쓰기로 닫힌다.

    Args:
        html: 파셜 렌더 결과.
        anchor: 블록을 특정하는 속성 문자열(예: `id="foms-settle-ch-bar"`).

    Returns:
        여는 `<div` 부터 그 블록의 닫는 태그 직전까지.
    """
    at = html.find(anchor)
    assert at >= 0, f"렌더에 {anchor} 가 없다"
    start = html.rfind("<div", 0, at)
    assert start >= 0, f"{anchor} 를 감싼 <div> 를 찾지 못했다"
    end = html.find("\n  </div>", start)
    assert end > start, f"{anchor} 블록의 끝을 찾지 못했다"
    return html[start:end]


def _js_function(name: str) -> str:
    """`channel.js` 함수 하나의 본문(주석 제거)을 돌려준다.

    닫는 중괄호가 두 칸 들여쓰기(`\\n  }`)라는 이 파일의 관례를 이용한다 — 이 파일의
    기존 계약 테스트들이 쓰던 슬라이스와 같은 규칙이다. 주석을 걷어내는 이유는
    **음성 대조군**(옛 코드가 남았는가) 검사가 그 코드를 설명하는 주석에 걸리지 않게
    하기 위해서다.

    Args:
        name: 함수 이름.

    Returns:
        `function <name>(` 부터 함수가 닫히기 직전까지의 코드.
    """
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find(f"function {name}(")
    assert at >= 0, f"channel.js 에 {name} 가 없다"
    end = source.find("\n  }", at)
    assert end > at, f"channel.js 의 {name} 끝을 찾지 못했다"
    return source[at:end]


def test_basis_select_moved_into_the_ledger_switch_row(app):
    """축 셀렉트가 **원장 스위처 줄**에 있고 기간 바에는 없다(R1).

    그 축은 아래 원장 표에만 걸린다 — 기간 바에 두면 위쪽 KPI·차트·워터폴까지 따라 바뀌는
    것처럼 읽힌다(2026-09-03 실측). 앵커는 여전히 **서버 렌더 시점**에 있어야 한다
    (`_REQUIRED_ANCHORS`) — JS 로 만들면 fetch 가 죽었을 때 줄이 통째로 사라진다.

    음성 대조군: 옛 자리(기간 바)에 남아 있으면 red. 셀렉트가 둘이면 `collectEls()` 가
    첫 번째만 잡아 사용자가 만지는 쪽과 코드가 읽는 쪽이 갈린다.
    """
    html = _render(app)

    switch = _element_block(html, 'id="foms-settle-ch-ledger-switch"')
    bar = _element_block(html, 'id="foms-settle-ch-bar"')

    assert "data-settlement-ch-switch-tools" in switch, "축 셀렉트 자리가 원장 줄에 없다"
    assert "data-settlement-ch-basis" in switch, "축 셀렉트가 원장 줄에 없다"
    assert "표 날짜 축" in switch, "새 라벨이 없다"
    assert "data-settlement-ch-basis" not in bar, "옛 자리(기간 바)에 축 셀렉트가 남아 있다"


def test_switch_tools_hide_in_the_exceptions_view():
    """예외 뷰에서는 축 셀렉트를 감춘다 — 예외 큐는 날짜 축이 없는 목록이다.

    고를 수는 있는데 표가 안 바뀌면 사용자는 그것을 고장으로 읽는다.
    """
    body = _js_function("renderSwitch")

    assert "data-settlement-ch-switch-tools" in body, "renderSwitch 가 축 셀렉트 자리를 모른다"
    assert "'exceptions'" in body, "예외 뷰 조건이 없다"
    assert "setHidden(tools" in body, "감추기 배선이 없다"


def test_switch_ledger_leaves_the_axis_to_the_server():
    """원장을 바꿀 때 축은 **건드리지 않는다** — 되돌림 정본은 서버 `_ledger_axis` 하나다.

    클라가 요청 전에 되맞추면 `supported=false` 가 영영 안 와서 "이 표에는 「결제일」 축이
    없어 정산 예정일 기준으로 보여 줍니다" 안내가 사라진다(F7 이 잡은 '조용한 되돌림' 재발).

    음성 대조군: `switchLedger` 본문에 `ctx.state.basis` 가 **한 글자라도** 나오면 red.
    유형·검색 초기화는 그대로 남아야 한다(원장이 바뀌면 코드 체계가 통째로 바뀐다).
    """
    body = _js_function("switchLedger")

    assert "ctx.state.basis" not in body, "클라가 축을 미리 되맞추고 있다(서버 되돌림이 가려진다)"
    assert "ctx.state.type = ''" in body, "유형 필터 초기화가 사라졌다"
    assert "ctx.state.q = ''" in body, "검색어 초기화가 사라졌다"


def test_select_adopts_the_server_effective_axis():
    """셀렉트 값은 **서버가 표에 실제로 건 축**(`ledger.axis.basis`)을 채택한다(C1).

    최상위 `data.basis` 는 요청 echo 라 되돌림 전 값이 온다 — 그걸 채택하면 셀렉트가 표와
    다른 축을 가리킨 채로 남는다.
    """
    body = _js_function("adoptServerState")

    assert "data.ledger.axis.basis" in body, "실효 축 채택이 없다"
    assert "state.basis = axisBasis" in body, "채택 결과를 상태에 안 넣는다"


def test_rollback_sentence_names_the_requested_axis():
    """되돌림 문장의 「X」 는 셀렉트 현재값이 아니라 **요청한 축**이다(C1).

    셀렉트가 이제 실효 축을 보이므로 `selectedOptions` 를 읽으면 "「정산 예정일」 축이 없어
    정산 예정일 기준으로 보여 줍니다" 라는 자기모순이 난다.

    음성 대조군: 옛 버그 소스(`selectedOptions`)가 이 함수에 남아 있으면 red.
    """
    body = _js_function("renderLedgerAxisNote")

    assert 'option[value="' in body, "요청 축의 옵션 라벨을 찾지 않는다"
    assert "ctx.state.data.basis" in body, "요청 echo 를 읽지 않는다"
    assert "selectedOptions" not in body, "옛 버그 소스(selectedOptions)가 남아 있다"


def test_axis_note_says_how_many_rows_left_the_window():
    """축을 바꿔 조회 창 밖으로 밀려난 행 수를 표 머리가 말한다(C2).

    `excluded`(축 날짜가 아예 없는 행)와는 **다른 수**다 — 둘은 서로소라 합쳐 세지 않는다.
    서버가 키를 아직 안 주면(구버전 응답) 문장은 조용히 빠진다(falsy 판정).
    """
    body = _js_function("renderLedgerAxisNote")

    assert "axis.shifted_out" in body, "밀린 행 수를 읽지 않는다"
    assert "건은 이 기간 표에 없습니다" in body, "밀린 행 문구가 없다"
    assert "axis.excluded" in body, "제외 행 문구가 사라졌다(두 수는 서로 다른 사실이다)"


def test_case_columns_put_the_purchaser_before_the_product_name():
    """건별 표에 `구매자명` 열이 있고 `상품명` **왼쪽**에 온다(R5b).

    열 순서는 회계 담당자가 눈으로 훑는 순서다 — 사람 이름이 상품명 뒤로 밀리면 못 찾는다.
    """
    source = _read_code(f"static/{JS_ASSET}")
    at = source.find("var COLUMNS = {")
    assert at >= 0, "COLUMNS 가 없다"
    end = source.find("commission: [", at)
    assert end > at, "COLUMNS.case 블록의 끝을 찾지 못했다"
    block = source[at:end]

    assert "{ key: 'purchaser_name', label: '구매자명', type: 'text' }" in block
    assert block.index("'purchaser_name'") < block.index("'product_name'"), "구매자명이 상품명 뒤에 있다"


def test_search_placeholder_names_the_purchaser():
    """검색창이 구매자명도 본다고 말한다(R5a) — 서버 검색 필드와 화면 안내가 갈리면 안 된다.

    음성 대조군: 옛 문구(`주문번호 · 상품주문번호 검색`)가 남아 있으면 red. 남으면 사용자는
    이름으로 찾을 수 있다는 사실을 영영 모른다.
    """
    source = _read_code(f"static/{JS_ASSET}")

    assert "'주문번호 · 상품주문번호 · 구매자명 검색'" in source, "새 placeholder 가 없다"
    assert "'주문번호·상품주문번호·구매자명 검색'" in source, "새 aria-label 이 없다"
    assert "'주문번호 · 상품주문번호 검색'" not in source, "옛 placeholder 가 남아 있다"
    assert "'주문번호·상품주문번호 검색'" not in source, "옛 aria-label 이 남아 있다"


def test_export_menu_offers_the_settlement_sheet():
    """내려받기 메뉴에 회계 제출용 `settle_case_sheet` 항목이 있고 유형 필터가 실린다(R5c).

    `typeOf` 없이 두면 `exportUrl` 의 짝 판정(`exportKindOfLedger(...) === spec.kind`)이 영영
    안 맞아 건별 원장에서 고른 유형 필터가 이 파일에는 실리지 않는다.

    표 계산 프로그램 이름(영문 낱말)은 코드·주석 어디에도 쓰지 않는다 — 이 저장소는 그
    낱말을 `foms/` 전역에서 금지하고, 화면 자산도 같은 규율을 따른다.
    """
    source = _read_code(f"static/{JS_ASSET}")
    section = _js_section(_EXPORT_SECTION_START, _EXPORT_SECTION_END)

    assert "kind: 'settle_case_sheet'" in source, "시트 항목이 없다"
    assert "typeOf: 'settle_case'" in source, "유형 필터 짝이 없다"
    assert "(spec.typeOf || spec.kind)" in section, "exportUrl 이 typeOf 를 안 본다"
    lowered = _read(f"static/{JS_ASSET}").lower()
    assert "xlsx" not in lowered and "excel" not in lowered


# ==========================================================================
# 계약 v1.3 — F10 T1: 검색어도 원장 짝 판정을 받는다
# ==========================================================================
def test_export_url_pairs_the_search_term_with_the_ledger():
    """검색어 `q` 가 유형 필터와 **같은 짝 판정**을 받는다(F10 T1-a).

    수수료 원장에서 주문번호로 좁혀 둔 채 건별 파일을 받으면 그 문자열이 건별 3필드에
    걸려 화면과 다른 행 집합이 내려갔다. 판정 기준은 `ctx.state.typeKind`(유형을 고른
    시점의 원장)가 아니라 **지금 실린 원장**(`currentLedgerParam`)이다 — `switchLedger`
    가 원장 전환 때 `type` 과 `q` 를 함께 비우므로 그 하나면 충분하다.

    양성: `exportUrl` 이 한 판정(`carries`)으로 두 조건을 싣는다.
    음성 대조군: 옛 무조건 분기와 옛 판정 기준(`typeKind`)이 그 함수에 남아 있으면 red.
    """
    export_url = _js_function("exportUrl")
    helper = _js_function("exportCarriesFilters")

    assert "carries && ctx.state.q" in export_url, "검색어가 짝 판정을 안 받는다"
    assert "carries && ctx.state.type" in export_url, "유형 필터가 짝 판정을 안 받는다"
    assert "if (spec.filters && ctx.state.q)" not in export_url, "옛 무조건 분기가 남아 있다"
    assert "typeKind" not in export_url, "옛 판정 기준(typeKind)이 남아 있다"
    assert "currentLedgerParam(ctx)" in helper, "판정이 지금 실린 원장을 안 본다"
    assert "(spec.typeOf || spec.kind)" in helper, "판정이 항목 종류를 안 본다"


def test_export_menu_says_when_the_search_term_is_dropped():
    """검색어가 이 항목에 안 실릴 때 메뉴가 **그 사실을 말한다**(F10 T1-b).

    조용히 빼면 사용자는 좁혀 놓은 조건이 그대로 실린 줄 안다. 문구는 부제 클래스에
    경고 수식자(`s-ch-export-sub--warn`)를 더해 붙인다 — 설명 부제와 같은 모양이면
    사람이 둘을 못 가려낸다(F10 리뷰 MINOR-2). 검색어 값 자체는 되쓰지 않는다 — 긴
    입력이 메뉴를 밀어낸다.

    음성 대조군: 안내 줄이 수식자 없는 맨 부제 클래스로 붙어 있으면 red(색 구분이
    사라진 옛 모양). 같은 본문에 `innerHTML` 이나 `createObjectURL` 이 있어도 red
    (문구를 붙이려다 마크업 주입이나 blob 내려받기로 새지 않았는가).
    """
    body = _js_function("renderExportMenu")
    css = _read(f"static/{CSS_ASSET}")

    assert "'지금 검색어는 이 표에 안 실립니다(원장이 다릅니다)'" in body, "안내 문구가 없다"
    assert "'s-ch-export-sub s-ch-export-sub--warn'" in body, "안내 줄에 경고 수식자가 없다"
    # 음성 대조군: 수식자 없는 맨 부제 클래스로 안내를 붙이면 설명 줄과 구분이 안 된다.
    assert not re.search(r"'s-ch-export-sub',\s*'지금 검색어는", body), (
        "안내 줄이 설명 부제와 같은 모양이다"
    )
    assert ".s-ch-export-sub--warn {" in css, "경고 수식자 CSS 규칙이 없다"
    assert "ctx.state.q && spec.filters && !exportCarriesFilters(ctx, spec)" in body, "안내 게이트가 없다"
    # 음성 대조군: 조건을 안 받는 일자 단위 표(filters:false)에는 '원장이 다르다' 사유가 거짓이라 안 붙어야 한다.
    assert "ctx.state.q && !exportCarriesFilters(ctx, spec)" not in body, "일자 단위 표에도 안내가 붙는다"
    assert "innerHTML" not in body, "마크업을 주입하고 있다"
    assert "createObjectURL" not in body, "blob 내려받기를 만들고 있다"

# ==========================================================================
# 계약 — CFO 후속(2026-09-05): 라벨 6개 · 예외 머리 모집단 · 미매칭 금액/aging · 전기 구간 라벨
# ==========================================================================
def test_waterfall_says_the_total_is_settled_plus_unpaid():
    """워터폴 단계 목록 아래에 "정산 금액 = 정산 완료액 + 미입금 정산액" 한 줄(A-01).

    마지막 단계 "정산 금액"은 완료액 타일과 **다른 수**다(완료분 + 미입금분). 낱말은 타일
    라벨(`미입금 정산액`)과 같아야 한다 — 화면에 없는 라벨을 가리키면 G-03 류 결함이 다시 생긴다.
    """
    body = _js_function("renderWaterfall")

    assert "'정산 금액 = 정산 완료액 + 미입금 정산액'" in body, "워터폴 정의 줄이 없다"


def test_unpaid_tile_says_the_unassigned_method_amount():
    """미입금 타일 부제가 "입금 방식 미정 X" 를 말한다(A-03).

    계좌·충전금 어느 쪽에도 안 실리는 행(`settle_method_type` 빈 값)이 있으면 두 조각을 더해도
    타일 값이 안 나온다 — 그 차액을 화면이 말해야 회계팀이 손으로 뺄 필요가 없다. 값은 서버
    `kpi.expected_unassigned_amount`(저장값 합) 그대로다.
    """
    body = _js_function("renderKpis")

    assert "입금 방식 미정 " in body, "입금 방식 미정 문구가 없다"
    assert "kpi.expected_unassigned_amount" in body, "서버 값(expected_unassigned_amount)을 안 읽는다"


def test_settled_tile_subtitle_matches_the_kernel_definition():
    """완료액 타일 부제가 커널 정의(정산 예정일 창 안 · 완료 처리된 행의 정산 금액)를 말한다(G-01).

    음성 대조군: 옛 부제 `통장 입금 완료분 · 정산 완료일 기준` 은 축(완료일)과 범위(통장)를
    둘 다 틀리게 말했다 — 소스에서 사라져야 한다.
    """
    body = _js_function("renderKpis")

    assert "'정산 예정일 창 안 · 완료 처리된 행의 정산 금액(계좌+충전금)'" in body, "새 부제가 없다"
    assert "'통장 입금 완료분 · 정산 완료일 기준'" not in body, "옛 부제가 남아 있다"


def test_unpaid_tile_is_labelled_unpaid_not_expected():
    """"정산 예정액" 타일이 "미입금 정산액"으로 불리고, 건별 「정산 예정 금액」과 다르다고 말한다(G-03).

    일별 축 미완료 행의 `settle_amount` 합인데 "예정"이라 부르면 건별 `settle_expect_amount`
    (수수료 차감 후·보류 전)와 같은 수로 읽힌다. 상태 훅 `key: 'expected'` 는 CSS·상태가 쓰므로
    **유지**한다(라벨만 바뀐다).

    음성 대조군: 옛 라벨 `label: '정산 예정액'` 이 남아 있으면 red.
    """
    body = _js_function("renderKpis")

    assert "label: '미입금 정산액'" in body, "새 라벨이 없다"
    assert "'일별 정산 금액 중 미완료분 · 건별 「정산 예정 금액」과 다름'" in body, "부제 앞부분이 없다"
    assert "label: '정산 예정액'" not in body, "옛 라벨이 남아 있다"
    assert "key: 'expected'" in body, "상태 훅 key 가 바뀌었다(CSS·상태가 깨진다)"


def test_reconcile_banner_names_the_compared_field():
    """대사 배너가 어떤 금액을 대사했는지(결제 정산 금액 paySettleAmount) 말한다(G-04).

    필드명이 없으면 "대사 일치"를 입금액 대사로 읽는다 — 실제로는 적재 검증이다. 문구는
    대사 줄(`s-ch-recon-line`) 안에 있어야 하고, "대사 대상 없음" 분기에는 넣지 않는다.
    """
    body = _js_function("renderReconcile")

    assert "'결제 정산 금액(paySettleAmount) 기준'" in body, "대사 필드명 문구가 없다"
    line_at = body.find("var line = el('div', 's-ch-recon-line')")
    assert line_at >= 0, "대사 줄이 없다"
    assert body.find("'결제 정산 금액(paySettleAmount) 기준'") > line_at, "문구가 대사 줄 밖에 있다"
    empty_block = body[: body.find("var ok = diff === 0")]
    assert "paySettleAmount" not in empty_block, "대사 대상 없음 분기에 필드명이 붙었다"


def test_ledger_head_carries_server_totals_and_the_amount_definition():
    """원장 머리가 서버 `ledger.totals`(같은 필터의 SUM/COUNT)를 한 줄로 말하고, 건별 표에는
    원장 금액과 KPI 완료액이 왜 다른지 한 문장을 붙인다(C-02).

    합계 라벨은 서버 `totals.amount_label` 이다 — 수수료·부가세 표에서 "정산 예정 금액"이라고
    거짓말하지 않게. 음성 대조군: `sumBy(` 로 이 페이지의 행을 더해 만들면 red(재계산 금지 D-4,
    "이 기간 합계"가 아니라 "이 페이지 합계"가 된다).
    """
    body = _js_function("renderLedgerAxisNote")

    assert "'이 축·이 기간 합계 '" in body, "합계 줄이 없다"
    assert "'건 · Σ'" in body, "합계 줄의 금액 조각이 없다"
    assert "totals.amount_label" in body, "합계 라벨을 서버 값으로 안 쓴다"
    assert "'원장 금액 = 정산 예정 금액(수수료 차감 후·보류 전), KPI 정산 완료액 = 보류 반영 후 실입금'" in body, (
        "원장 금액 정의 문장이 없다"
    )
    assert "ledger.totals" in body, "서버 totals 를 안 읽는다"
    assert "sumBy(" not in body, "화면이 합계를 다시 계산한다"


def test_exception_head_says_shown_of_total_and_badge_reads_the_population():
    """예외 표 첫 줄이 "예외 N건 중 M건 표시(갈래별 상한 50)" 이고, 원장 스위처 배지는
    상한 적용 **전** 모집단(`exception_totals.total`)을 읽는다(D-02).

    음성 대조군: 배지가 `(data.exceptions || []).length` 를 세면 갈래별 상한에 잘린 수가
    "예외 전량"으로 읽힌다(실측 65 vs 526). 옛 문장 `표에는 갈래마다 최근 것부터 상한까지만
    실립니다` 는 첫 줄이 대신 말하므로 소스에서 사라져야 한다.
    """
    exceptions = _js_function("renderExceptions")
    switch = _js_function("renderSwitch")
    source = _read_code(f"static/{JS_ASSET}")

    assert "'건 중 '" in exceptions, "N건 중 문구가 없다"
    assert "'건 표시(갈래별 상한 '" in exceptions, "상한 문구가 없다"
    assert "data.exception_totals" in exceptions, "모집단(exception_totals)을 안 읽는다"
    assert "data.exception_cap" in exceptions, "상한 값(exception_cap)을 안 읽는다"
    assert "exception_totals" in switch, "배지가 모집단을 안 읽는다"
    assert ".length" not in switch, "배지가 표시 행 수를 세고 있다"
    assert "상한까지만 실립니다" not in source, "옛 문장이 남아 있다"


def test_match_tile_and_exception_head_carry_unmatched_amount_and_aging():
    """매칭률 타일 부제와 예외 표 머리가 미연결 **금액**과 예정일 경과 구간을 말한다(D-01).

    건수 3개만으로는 "붙지 않은 돈이 얼마이고 얼마나 오래됐나"를 알 수 없다(운영 실측 14.8억,
    90일+ 9.8억). 값은 전부 서버 `kpi.unmatched_amount`·`unmatched_settled_amount`·
    `unmatched_aging`(저장값 부호합) 그대로이고, 구간 조각은 `agingText` 한 헬퍼로 찍는다.
    """
    kpis = _js_function("renderKpis")
    exceptions = _js_function("renderExceptions")
    source = _read_code(f"static/{JS_ASSET}")

    assert "'(90일+ '" in kpis, "타일 부제에 90일+ 조각이 없다"
    assert "kpi.unmatched_amount" in kpis, "타일 부제가 미연결 금액을 안 읽는다"
    assert "'정산 예정일 경과 · 30일 미만 '" in exceptions, "aging 줄이 없다"
    assert "kpi.unmatched_aging" in exceptions, "aging 구간을 안 읽는다"
    assert "kpi.unmatched_settled_amount" in exceptions, "완료분을 안 읽는다"
    assert "function agingText(" in source, "agingText 헬퍼가 없다"
    for bucket in ("lt30", "d30_59", "d60_89", "d90_plus", "future"):
        assert f"agingText(aging.{bucket})" in exceptions, f"구간 {bucket} 이 빠졌다"


def test_delta_label_names_the_previous_range():
    """KPI 델타 라벨과 일별 차트 범례가 전기 **구간**(MM-DD~MM-DD)을 말한다(C-01).

    "전기"가 달력 전월인지 같은 일수 직전 구간인지는 서버가 정한다(`range.prev`). 라벨이
    구간을 안 적으면 월 보고에 다른 구간의 델타가 실린다. 구간은 화면이 다시 계산하지 않고
    `prevRangeLabel(data.range)` 한 헬퍼가 서버 값을 읽는다(구버전 응답이면 그냥 '전기').

    음성 대조군: 옛 고정 리터럴 `' 전기 대비'`·`'전기 비교(정산 금액)'` 이 남아 있으면 red.
    """
    source = _read_code(f"static/{JS_ASSET}")
    helper = _js_function("prevRangeLabel")
    kpis = _js_function("renderKpis")
    daily = _js_function("renderDaily")
    tile = _js_function("appendKpi")

    assert "function prevRangeLabel(" in source, "prevRangeLabel 헬퍼가 없다"
    assert "'전기('" in helper, "헬퍼가 구간 라벨을 안 만든다"
    assert "range.prev" in helper, "헬퍼가 서버 range.prev 를 안 읽는다"
    assert "prevRangeLabel(data.range)" in kpis, "KPI 가 구간 라벨을 안 만든다"
    assert "prevRangeLabel(data.range)" in daily, "범례가 구간 라벨을 안 만든다"
    assert "' 대비'" in tile, "델타 라벨 접미가 없다"
    assert "spec.prevLabel" in tile, "타일이 구간 라벨을 안 받는다"
    assert "' 전기 대비'" not in tile, "옛 고정 라벨이 남아 있다"
    assert "'전기 비교(정산 금액)'" not in daily, "옛 범례 리터럴이 남아 있다"


# ==========================================================================
# 계약 — CFO 백로그 2차(2026-09-06): 보류 부호별 합·누적 잔액 · stale/FAILED 헤더 · SYNC_FAILED 배지 ·
#        워터폴 2줄 라벨 · 그룹 min-width · 버킷 일부 완료
# 문구는 **소스 리터럴**로 본다(서버 응답 키 이름은 설계 정본 §1 — API 계약은 BE 테스트가 잠근다).
# ==========================================================================
def test_holdback_tile_says_window_held_and_released():
    """"보류·한도" 타일 부제가 창 안 보류(음수) 합과 해제(양수) 합을 따로 말한다(B-02).

    타일 값은 두 부호가 상계된 순증감이라 발생액도 잔액도 아니다. 값은 서버 `holdback.window`
    (저장값 부호별 합) 그대로이고, 변수 이름은 전역을 가리는 `window` 가 아니다.
    """
    kpis = _js_function("renderKpis")

    assert "'지급 보류 + 정산 한도 초과분 · 창 안 보류 '" in kpis, "창 안 보류 조각이 없다"
    assert "' · 해제 '" in kpis, "해제 조각이 없다"
    assert "holdback.window" in kpis, "서버 window 블록을 안 읽는다"
    assert ".held.amount" in kpis and ".released.amount" in kpis, "서버 held/released 금액을 안 읽는다"
    assert "var window" not in kpis, "전역 window 를 가리는 변수명이다"


def test_holdback_detail_head_says_the_cumulative_balance_and_sign_rows():
    """상세 패널 머리에 적재 구간 전체 누적 잔액 한 줄, tfoot 에 부호별 합 두 줄(B-02).

    누적 잔액은 조회 창과 무관한 서버 `holdback.balance`(전 기간 부호별 합 + since/until)라
    **빈 목록 검사보다 앞**에 있어야 한다 — 창 밖 해제가 잔액에만 반영되는 것이 이 항목의 핵심이다.
    tfoot 두 줄의 값 원천은 서버 `window.held`/`window.released` 만이다(화면 합산 금지).
    """
    body = _js_function("renderHoldbackDetail")

    assert "'적재 구간 전체 누적 잔액 '" in body, "누적 잔액 줄이 없다"
    assert "'(보류 '" in body, "누적 잔액의 보류 조각이 없다"
    assert "'보류(음수) 합'" in body and "'해제(양수) 합'" in body, "부호별 합 줄이 없다"
    assert "block.balance" in body, "서버 balance 를 안 읽는다"
    assert ".since" in body and ".until" in body, "적재 구간(since~until)을 안 찍는다"
    assert body.find("block.balance") < body.find("block.rows.length"), "누적 잔액 줄이 빈 목록 검사 뒤에 있다"
    assert "block.window" in body, "부호별 합의 원천이 서버 window 가 아니다"
    assert ".held" in body and ".released" in body, "서버 held/released 를 안 읽는다"
    assert "el('tfoot')" in body and "block.total" in body, "기존 합계 줄 계약이 깨졌다"


def test_stale_sentence_names_the_schedule_and_reads_the_server_threshold():
    """stale 문장이 "예정 실행(매일 05:30)을 넘겼습니다" 를 말하고 임계값은 서버 값을 읽는다(F-01).

    "N시간 넘게" 만으로는 N 이 왜 비정상인지 읽히지 않는다. 숫자는 `sync.stale_after_hours` 에서
    오므로 서버 상수(28)가 바뀌어도 화면이 갈리지 않는다. 음성 대조군: 옛 고정 문장 "36시간 넘게
    갱신되지 않았습니다" 는 소스 어디에도 없다.
    """
    helper = _js_function("staleSentence")
    sync = _js_function("renderSync")
    source = _read_code(f"static/{JS_ASSET}")

    assert "'갱신되지 않았습니다 — 예정 실행(매일 05:30)을 넘겼습니다. 아래 숫자는 그 시점의 값입니다.'" in helper
    assert "sync.stale_after_hours" in helper, "임계값을 서버에서 안 읽는다"
    assert "'시간 넘게 '" in helper, "N시간 조각이 없다"
    assert "staleSentence(sync)" in sync, "헤더가 stale 문장 헬퍼를 안 쓴다"
    assert "36시간 넘게 갱신되지 않았습니다" not in source, "옛 고정 문장이 남아 있다"


def test_sync_header_has_a_failed_mode_that_stale_cannot_hide():
    """동기화 헤더에 FAILED 모드가 있고 우선순위는 never > failed > stale > ok 다(F-08).

    성공이 한 번도 없이 실패만 쌓이면 옛 코드는 stale 문구로 실패를 덮었다. FAILED 머리는
    마지막 실행 시각과 서버 `sync.last_error` 를 말하고, 성공이 없으면 "성공한 실행이 아직 없습니다"
    로 아래 숫자가 비었거나 부분 적재일 수 있음을 말한다. 점 색은 CSS 에도 있어야 한다.
    """
    body = _js_function("renderSync")
    css = _read_code(f"static/{CSS_ASSET}")

    assert "sync.failed ? 'failed'" in body, "failed 모드가 없다"
    assert body.find("sync.never ?") < body.find("sync.failed ?") < body.find("sync.stale ?"), "모드 우선순위가 다르다"
    assert "'동기화 실패 — '" in body and "' · 오류: '" in body, "FAILED 머리 문구가 없다"
    assert "sync.last_error" in body, "서버 오류 문구를 안 읽는다"
    assert "'성공한 실행이 아직 없습니다 — 아래 숫자는 비어 있거나 부분 적재일 수 있습니다.'" in body
    assert "'마지막 성공 '" in body, "성공이 있을 때의 부제가 없다"
    assert ".s-ch-dot--failed" in css, "CSS 에 failed 점 색이 없다"


def test_exception_badge_knows_sync_failed_as_danger():
    """예외 배지가 `SYNC_FAILED` 를 **첫 분기**에서 danger 색으로 낸다(F-04).

    동기화 실패는 "화면 전체가 옛 값"이라는 신호라 보류(hold)·경고(warn)와 갈려야 조치 순서가
    읽힌다. 색 클래스는 CSS 에도 있어야 한다(없으면 조용히 회색).
    """
    body = _js_function("excKindClass")
    css = _read_code(f"static/{CSS_ASSET}")

    assert "'SYNC_FAILED'" in body and "return 'danger'" in body, "SYNC_FAILED 분기가 없다"
    assert body.find("'SYNC_FAILED'") < body.find("'UNMATCHED'"), "SYNC_FAILED 가 첫 분기가 아니다"
    assert ".s-ch-badge--danger" in css, "CSS 에 danger 배지 색이 없다"


def test_waterfall_labels_wrap_into_two_tspans_instead_of_slicing():
    """워터폴 X축 라벨이 6자 절단 대신 `<tspan>` 1~2줄로 그려진다(G-07·G-08).

    "지급 보류·한도" 가 "지급보류·한" 으로 잘려 이웃 라벨과 겹쳤다. `splitStepLabel` 이 '·' 우선,
    없으면 첫 공백에서 줄을 가르고 절단은 하지 않는다. 음성 대조군: `slice(0, 6)`·`shortStepLabel`·
    `short:` 항목이 소스에 남아 있지 않다. SVG 문자열 조립에는 `esc()` 를 쓴다.
    """
    source = _read_code(f"static/{JS_ASSET}")
    chart = _js_function("waterfallChart")
    waterfall = _js_function("renderWaterfall")
    helper = _js_function("splitStepLabel")

    assert "function splitStepLabel(" in source, "splitStepLabel 헬퍼가 없다"
    assert "'<tspan x=\"'" in chart, "축 라벨이 tspan 으로 안 그려진다"
    assert "splitStepLabel(step.item.label)" in chart, "차트가 줄 나눔 헬퍼를 안 쓴다"
    assert "esc(line)" in chart, "tspan 본문을 이스케이프하지 않는다"
    assert "'·'" in helper, "'·' 에서 줄을 가르지 않는다"
    assert "slice(0, 6)" not in source, "6자 절단이 남아 있다"
    assert "function shortStepLabel" not in source, "shortStepLabel 이 남아 있다"
    assert "short:" not in waterfall, "renderWaterfall 이 short 항목을 만든다"


def test_ledger_group_has_min_width_zero_so_the_grid_cannot_overflow():
    """`.foms-settle .s-ch-group` 에 `min-width: 0` 이 있다(G-08a).

    grid 아이템 기본 `min-width: auto` 가 min-content(150% 배율에서 1650px)로 부풀어
    `.s-ch-ledger-body` 격자를 뚫고 본문 가로 스크롤을 만들었다. 표는 이미 `.s-ch-tablewrap`
    (overflow-x: auto) 안이라 그룹이 줄어들 수만 있으면 스크롤이 표 안에 머문다.
    """
    css = _read_code(f"static/{CSS_ASSET}")

    assert re.search(r"\.foms-settle \.s-ch-group\s*\{[^}]*min-width:\s*0", css), "s-ch-group 에 min-width: 0 이 없다"


def test_bucket_tooltip_says_partly_settled_when_mixed():
    """일별 차트 툴팁 제목이 완료·미완료가 섞인 버킷을 "일부 완료(완료 X · 미입금 Y)" 로 말한다(N-02).

    월/주 버킷(또는 하루 2행)에 "정산 예정" 을 찍으면 거짓이다. 두 금액은 서버 버킷의
    `settled_amount`·`expected_amount`(저장값 합) 그대로이고, 화면은 더하거나 나누지 않는다.
    음성 대조군: `renderDaily` 안에 옛 `completed ? ' (정산 완료)' : ' (정산 예정)'` 삼항이 없다.
    """
    helper = _js_function("bucketStateText")
    daily = _js_function("renderDaily")

    assert "' (일부 완료 — 완료 '" in helper and "' · 미입금 '" in helper, "일부 완료 문구가 없다"
    assert "row.settled_amount" in helper and "row.expected_amount" in helper, "서버 두 금액을 안 읽는다"
    assert "' (정산 완료)'" in helper and "' (정산 예정)'" in helper, "완료/예정 접미가 헬퍼에 없다"
    assert "bucketStateText(daily[i])" in daily, "툴팁 제목이 헬퍼를 안 쓴다"
    assert "' (정산 예정)'" not in daily, "renderDaily 에 옛 삼항이 남아 있다"


def test_bucket_mixed_predicate_only_needs_a_settled_share():
    """섞임 판정은 **완료분이 있는가**만 본다 — 미입금이 ₩0 이어도 "일부 완료" 다(리뷰 Q-05).

    완료 행들 + `settle_amount` 0 인 미완료 행(그날 정산이 통째로 보류된 날)이 섞인 달은
    `completed=False`·`expected_amount=0` 이라, 옛 술어 `settled && expected` 는 그 달을 "(정산 예정)" 으로
    찍었다 — 전부 이미 입금된 돈인데도. 미입금 ₩0 은 사실이므로 그대로 찍는다.
    음성 대조군: 옛 술어(두 금액 모두 0 아님)가 헬퍼에 남아 있지 않다.
    """
    helper = _js_function("bucketStateText")

    assert "row.settled_amount !== 0" in helper, "섞임 술어가 완료분 유무를 안 본다"
    assert "isNum(row.settled_amount)" in helper, "완료분 결측(null)과 0 을 가르지 않는다"
    assert "row.settled_amount && row.expected_amount" not in helper, "옛 섞임 술어(둘 다 0 아님)가 남아 있다"


# ==========================================================================
# 계약 — CFO 백로그 3차 (2026-09-06): 503 문구(F-02) · AMOUNT_DIFF 배지(D-03) · 확정 구간 부제(B-01)
# ==========================================================================
def test_sync_unavailable_503_goes_to_the_state_line_with_the_fixed_wording():
    """동기화 POST 가 503 이면 헤더 상태줄에 고정 문구 "지금은 동기화할 수 없습니다(큐 연결 불가)" 를 낸다(F-02).

    큐 부재·Redis 장애를 옛 코드는 200 `queued=False` 로 받아 "이미 대기 중" 이라고 말했다.
    이제 서버가 3상태(queued/duplicate/unavailable)를 503 으로 가르므로 화면은 `err.status` 로
    그 갈래를 읽는다. 문구는 `.alert` 가 아니라 `notice()` → `renderSync()` 의 상태줄
    (`[data-settlement-ch-sync-state]`)로 간다 — `.alert` 는 5초 뒤 자동으로 닫힌다.
    """
    sync = _js_function("requestSync")
    post = _js_function("postJson")
    note = _js_function("notice")
    source = _read_code(f"static/{JS_ASSET}")

    assert "err.status = res" in post, "postJson 이 실패 err 에 HTTP 상태를 안 싣는다"
    assert "err.status === 503" in sync and "SYNC_UNAVAILABLE_TEXT" in sync, "503 갈래가 없다"
    assert sync.find("} catch") < sync.find("err.status === 503"), "503 판정이 catch 블록 밖이다"
    assert re.search(r"notice\(ctx,\s*\w+\s*\?\s*SYNC_UNAVAILABLE_TEXT", sync), "503 문구가 상태줄(notice)로 가지 않는다"
    assert "var SYNC_UNAVAILABLE_TEXT = '지금은 동기화할 수 없습니다(큐 연결 불가)';" in source
    assert "renderSync(ctx)" in note, "notice 가 헤더 상태줄을 안 그린다"
    assert "동기화 큐가 아직 준비되지 않았습니다" not in source, "옛 별도 503 문구가 JS 에 있다"


def test_duplicate_wording_only_follows_queued_false():
    """"이미 대기 중인 동기화가 있습니다" 는 소스에 **한 번**, `requestSync` 의 try 블록(200 `queued=false`) 안에만 있다(F-02).

    503 은 `postJson` 이 던지므로 catch 로 가고 이 분기에 닿지 않는다 — 그 구조가 곧
    "duplicate 에만" 계약이다. 문구가 catch 나 다른 함수로 새면 큐 장애가 다시 "누가 이미
    돌리고 있다" 로 읽힌다.
    """
    needle = "이미 대기 중인 동기화가 있습니다"
    source = _read_code(f"static/{JS_ASSET}")
    body = _js_function("requestSync")

    assert source.count(needle) == 1, f"문구가 {source.count(needle)}회 있다"
    at = body.find(needle)
    assert at > 0, "문구가 requestSync 안에 없다"
    assert body.find("try {") < body.find("var queued =") < at < body.find("} catch"), (
        "문구가 try 블록(queued 판정 뒤) 안이 아니다")


def test_exception_badge_knows_amount_diff():
    """예외 배지가 `AMOUNT_DIFF`(정산액≠출고가, D-03)를 합계 불일치와 같은 warn 색으로 낸다.

    둘 다 "사람이 대조할 것" 이라 같은 색이 맞다 — 보류(hold) 기본색으로 떨어지면 조치 대상이
    묶인 돈 사이에 섞여 안 보인다. 색 클래스는 CSS 에도 있어야 한다.
    """
    body = _js_function("excKindClass")
    css = _read_code(f"static/{CSS_ASSET}")

    line = next((ln for ln in body.splitlines() if "'AMOUNT_DIFF'" in ln), None)
    assert line, "AMOUNT_DIFF 분기가 없다"
    assert "return 'warn'" in line, f"AMOUNT_DIFF 가 warn 이 아니다: {line.strip()}"
    assert ".s-ch-badge--warn" in css, "CSS 에 warn 배지 색이 없다"


def test_final_before_line_carries_the_correction_note():
    """"확정 구간 ~YYYY-MM-DD" 줄 바로 뒤에 부제 "(이 날짜 이전 정정은 [이 구간 받아오기]로만 반영 · 매월 1일 자동 백필)" 이 붙는다(B-01).

    확정 구간은 네이버가 준 것이 아니라 FOMS 의 30일 가정이다 — 그 이전 날짜의 네이버 정정은
    일반 동기화가 다시 읽지 않아 백필 없이는 영원히 안 들어온다. 부제는 그 리스크와 해법(수동
    [이 구간 받아오기] · 워커의 매월 1일 자동 백필)을 같은 줄에서 말한다. 알려진 한계: 서버 `sync`
    블록이 스위치 상태를 내지 않아 부제는 기본값(켜짐)을 전제한다.
    """
    body = _js_function("syncLines")
    source = _read_code(f"static/{JS_ASSET}")
    css = _read_code(f"static/{CSS_ASSET}")

    assert "'확정 구간 ~'" in body and "FINAL_BEFORE_NOTE" in body, "확정 구간 줄 또는 부제가 없다"
    assert body.find("'확정 구간 ~'") < body.find("FINAL_BEFORE_NOTE"), "부제가 확정 구간 줄 앞에 있다"
    assert re.search(r"el\('span',\s*'s-ch-sync-note',\s*FINAL_BEFORE_NOTE\)", body), "부제가 s-ch-sync-note 클래스로 안 그려진다"
    assert ("var FINAL_BEFORE_NOTE = '(이 날짜 이전 정정은 [이 구간 받아오기]로만 반영 · 매월 1일 자동 백필)';"
            in source), "부제 리터럴이 계약과 다르다"
    assert re.search(r"\.foms-settle \.s-ch-sync-note\s*\{[^}]*flex-basis:\s*100%", css), (
        "CSS 에 s-ch-sync-note 가 없거나 줄바꿈 규칙이 없다")


# --------------------------------------------------------------------------- #
# 동기화 진행 표시 (2026-09-08)
# --------------------------------------------------------------------------- #

def test_progress_anchor_and_api_are_on_the_root(app):
    """진행 조회 주소는 루트의 data 속성이 정본이다 — JS 리터럴이 유일 출처면 갈린다."""
    html = _render(app)
    assert 'data-settlement-ch-progress-api="/api/settlement/channel/sync/progress"' in html


def test_sync_starts_progress_polling_next_to_the_rev_poll(app):
    """요청 직후부터 진행을 읽는다. rev 폴링만 두면 60초 동안 화면이 아무 말도 못 한다."""
    sync = _js_function("requestSync")
    assert "startProgressPoll(ctx)" in sync, "요청 뒤 진행 폴링을 시작하지 않는다"
    assert sync.find("startProgressPoll(ctx)") < sync.find("startRevPoll(ctx"), \
        "진행 폴링이 rev 폴링보다 먼저 시작돼야 첫 2초가 안 비어 보인다"


def test_progress_poll_is_stopped_with_the_rev_poll(app):
    """폴링이 남으면 화면을 떠난 뒤에도 2초마다 서버를 두드린다."""
    stop = _js_function("stopRevPoll")
    assert "stopProgressPoll(ctx)" in stop
    source = _read_code(f"static/{JS_ASSET}")
    assert "window.clearTimeout(ctx.progressTimer);" in source, \
        "스왑으로 떨어져 나간 루트의 진행 타이머를 정리하지 않는다"


def test_failed_run_says_why_on_the_state_line(app):
    """실패 사유를 진행 폴링이 말한다 — rev 는 실패해도 안 바뀌어 화면이 조용히 끝난다.

    2026-09-08 실제로 이 구멍에 빠졌다: 운영 실행 28·29·30 이 전부 FAILED 였는데 화면은
    "최대 1분간 반영을 확인합니다" 만 내고 조용히 끝나, 사용자는 같은 버튼을 계속 눌렀다.
    """
    poll = _js_function("startProgressPoll")
    text = _js_function("syncFailureText")
    assert "notice(ctx, syncFailureText(data), true)" in poll, "실패 사유가 상태줄로 안 간다"
    assert "data.status !== 'OK'" in poll, "성공이 아닌 종료를 실패로 안 가른다"
    assert "ABORTED_QUOTA" in text, "쿼터 중단을 실패와 같은 문장으로 말하면 안 된다"


def test_progress_bar_width_goes_through_a_custom_property(app):
    """폭은 인라인 style 이 아니라 커스텀 프로퍼티로 넘긴다(이 저장소의 규율)."""
    node = _js_function("progressNode")
    assert "setProperty('--s-ch-prog'" in node
    assert ".style.width" not in node, "인라인 style 로 폭을 주면 안 된다"
    css = _read(f"static/{CSS_ASSET}")
    assert "--s-ch-prog" in css and ".s-ch-prog-fill" in css
    assert "prefers-reduced-motion" in css, "움직임 축소 설정을 무시하면 안 된다"


def test_progress_bar_is_indeterminate_when_the_denominator_is_unknown(app):
    """분모를 모르면 퍼센트를 지어내지 않는다 — 없는 사실을 말하지 않는 이 화면의 규율."""
    node = _js_function("progressNode")
    assert "s-ch-prog--indeterminate" in node
    assert "'워커가 시작하기를 기다리는 중입니다'" in node


def test_stamp_is_rendered_in_seoul_time_not_raw_utc(app):
    """서버 값은 naive UTC 다 — 그대로 찍으면 화면 시각이 9시간 어긋난다.

    2026-09-08 실측: 오후 3시 14분(KST)에 끝난 동기화가 `06:14` 로 떴다. 바로 아래
    `hoursSince` 는 `Z` 를 붙여 UTC 로 정확히 세므로 `06:14 (방금 전)` 이라는 자기모순이
    났고, 사용자는 화면이 멈춘 줄 알았다. 두 함수가 같은 규약을 읽어야 한다.
    """
    stamp = _js_function("fmtStamp")
    assert "Asia/Seoul" in stamp, "서울 시각으로 안 바꾼다"
    assert "+ 'Z'" in stamp, "naive 문자열을 UTC 로 안 읽는다 — 브라우저 로컬로 해석된다"
    since = _js_function("hoursSince")
    assert "+ 'Z'" in since, "상대시간과 절대시각이 다른 규약을 읽으면 또 어긋난다"


def test_rev_poll_window_outlasts_the_measured_run(app):
    """확인 창이 실제 소요보다 짧으면 성공해도 매번 실패 문구가 뜬다.

    운영 실측 소요는 62초(호출 93회)인데 창이 60초였다 — 2~3초 차이로 항상 넘겼다.
    그 문구는 사실이 아니라 창의 그림자였다.
    """
    source = _read_code(f"static/{JS_ASSET}")
    match = re.search(r"var POLL_MAX_TRIES = (\d+);", source)
    assert match, "폴링 한도 상수를 못 찾았다"
    tries = int(match.group(1))
    interval = int(re.search(r"var POLL_INTERVAL_MS = (\d+);", source).group(1))
    assert tries * interval >= 120000, (
        f"확인 창이 {tries * interval / 1000:.0f}초다 — 실측 62초짜리 실행을 담기에 빠듯하다"
    )


def test_success_closes_the_wait_without_waiting_for_rev(app):
    """끝난 것을 아는 쪽(진행 폴링)이 마감한다 — rev 창이 닫히기를 기다리지 않는다."""
    poll = _js_function("startProgressPoll")
    assert "reloadAfterSync(ctx)" in poll, "성공으로 끝났는데 진행 폴링이 마감하지 않는다"
    reload_fn = _js_function("reloadAfterSync")
    assert "adoptServerState(ctx, data)" in reload_fn and "stopRevPoll(ctx)" in reload_fn
