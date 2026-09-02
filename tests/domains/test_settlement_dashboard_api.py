"""SETTLE-DASH-01 M2: 정산 대시보드 권한 매트릭스 + API 응답 계약 테스트 (TDD, red→green).

정산 대시보드는 **금융 지표를 통째로 보여주는 읽기 화면**이다. 그래서 열람 권한이
비용 청구/현금영수증/입금확인(``FINANCE_MUTATION``, AUTH-FINANCE-01 §2.1 line 153)과
**같은 집합**이어야 한다. 이 파일이 red 로 잡아야 하는 것:

1. **권한 매트릭스 이탈** — 허용 4종(ADMIN / MANAGER / STAFF+CS / STAFF+SALES) 밖의
   actor 가 정산 화면·API 를 열거나, 허용 actor 가 막히는 것. actor 목록은 복제하지
   않고 :mod:`tests.domains.test_auth_finance` 의 SSOT 를 **import** 한다 — 두 곳에
   따로 적어 두면 한쪽만 고쳐져 매트릭스가 조용히 갈린다.
2. **집행 지점 누락** — ``enforce_order_mutation_policy`` 의 ``_WRITE_METHODS`` 는
   POST/PUT/PATCH/DELETE 뿐이라 **GET 은 before_request 가드에 도달하지 않는다.**
   따라서 신규 GET 핸들러가 각자 판정해야 하고, 이 파일은 ``AUTH_POLICY_ENABLED`` 를
   켜지 않은 채(=가드 OFF, ``TESTING=True`` 기본) 403 을 요구한다. 가드에 기대는
   구현은 여기서 200 을 내며 즉시 red 가 된다.
3. **정책 등재 오타/드리프트** — ``user_can`` 은 미등록 policy_id 에 조용히 ``False``
   를 준다(어떤 게이트도 오타를 red 로 안 잡는다). 등재 자체와 ``FINANCE_MUTATION``
   과의 판정 일치를 9종 actor 전부에서 대조한다.
4. **응답 형식 이탈** — ``{'success': ..., 'data': ..., 'error': ...}`` 통일 형식,
   M1 집계 스키마 통과(passthrough), 잘못된 파라미터 400, 권한 거부 403.
5. **PII 유출** — 집계 버킷만 내보내야 한다. 주문 행 원본(고객명·연락처)이 응답에
   섞이면 "집계만 보여주니 CS/SALES 에 열어준다"는 권한 설계 전제가 깨진다.
6. **UI 은닉 이탈** — 권한 없는 사용자에게 네비 진입 링크가 보이는 것(backend 가드
   대체가 아니라, 같은 policy_id 로 화면과 백엔드를 일치시키는 계약).

테스트 데이터 규율: 존재하지 않는 FK id 를 쓰지 않는다(SQLite 는 FK 를 강제하지 않아
로컬만 통과하고 PG 레인에서 터진다) — 실제 Order 를 만들고 그 id 를 쓴다. 감사 기록은
**개수로 세지 않는다**: ``record_access_denied`` 의 60초 dedupe 창(user/IP, endpoint,
action) 때문에 개수 단언은 테스트 순서에 의존한다(test_auth_finance line 164-170 에
기록된 함정). 이 파일은 거부의 증거로 status code 와 응답 본문만 본다.
"""

from __future__ import annotations

import json

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.order_mutation_policy import (
    ANCILLARY_ALLOWLIST,
    POLICY_REGISTRY,
    evaluate_policy,
    user_can,
)
from foms.services.settlement_aggregation import aggregate_settlement

# --- 권한 매트릭스 SSOT 재사용 -------------------------------------------------
# 복제 금지: AUTH-FINANCE-01 이 확정한 허용/거부 actor 와 로그인·사용자 생성 헬퍼를
# 그대로 쓴다. 두 파일이 같은 목록을 각자 하드코딩하면 한쪽만 갱신돼 매트릭스가 갈린다.
from tests.domains.test_auth_finance import (  # noqa: E402
    _ALLOWED_ACTORS,
    _DENIED_ACTORS,
    _login,
    _make_user,
)

# --- M1 집계 시드 헬퍼 재사용 ---------------------------------------------------
from tests.domains.test_settlement_aggregation import _money, _seed_order  # noqa: E402

# --------------------------------------------------------------------------
# 대상 표면 — SPEC §5/§6 이 고정한 URL. 둘 다 GET 전용 읽기 라우트다.
# --------------------------------------------------------------------------
PAGE_URL = "/erp/settlement"
API_URL = "/api/settlement/aggregates"

#: (라벨, path, JSON 여부). 권한 매트릭스는 **전 GET 라우트**에 동일하게 걸린다.
_GET_SURFACES = [
    ("page", PAGE_URL, False),
    ("api", API_URL, True),
]
_SURFACE_IDS = [name for name, _, _ in _GET_SURFACES]

#: 정산 열람 정책 id. 라우트·템플릿이 공유해야 하는 문자열(오타 = 조용한 전원 거부).
SETTLEMENT_POLICY_ID = "SETTLEMENT_DASHBOARD_READ"

#: 열람 권한이 같아야 하는 기준 정책(AUTH-FINANCE-01).
FINANCE_POLICY_ID = "FINANCE_MUTATION"

#: `aggregate_settlement` 반환 스키마 최상위 키(M1 docstring + SETTLE-TABS S4 확장).
#: `prev_totals` 는 KPI 델타용 이전 기간 스칼라, `managers`/`managers_total` 은 분석 탭의
#: 담당자별 매출이다. 셋 다 신규 쿼리 없이 이미 읽은 행에서 파생된다.
_M1_DATA_KEYS = {
    "range",
    "kpi",
    "buckets",
    "prev_buckets",
    "prev_totals",
    "aging",
    "aging_unknown",
    "channels",
    "managers",
    "managers_total",
    "settlement_status",
    "stages",
    "unknown_completion",
}

#: 담당자별 매출 = 직원 실적이라 관리자급에게만 내려간다(스펙 §13.6, 사용자 결정).
#: 그 아래 actor 가 받는 키 집합은 이 둘이 빠진 것이다.
_MANAGER_ONLY_DATA_KEYS = {"managers", "managers_total"}
_STAFF_DATA_KEYS = _M1_DATA_KEYS - _MANAGER_ONLY_DATA_KEYS

#: ERP 서브 내비 정본(완료 대시보드 진입 링크가 사는 템플릿). 정산 링크도 여기 붙는다.
_SUB_NAV_TEMPLATE = "partials/shared/erp_sub_nav.html"

#: **정산 이전부터 있던** 플랫폼 가드의 예외 actor.
#: ``foms/platform/http.py::_erp_construction_team_restrict`` (before_request) 는
#: CONSTRUCTION 팀의 ``/erp/*`` **페이지 이동**을 allowlist(shipment/construction/
#: completion/history) 로 제한하고, 그 밖은 출고 대시보드로 302 시킨다. 그래서 이 actor 만
#: 정산 핸들러의 ``abort(403)`` 에 도달하지 못한다 — **거부라는 결과는 동일하다**(정산
#: 화면을 못 본다). 그 가드는 자기 docstring 에서 "페이지 이동 제한이지 인가 경계가
#: 아니다"라고 명시하며 ``/api/``·``/erp/api/`` 를 제외하므로, API 표면에서는 CONSTRUCTION
#: 도 정상적으로 403 JSON 을 받는다(아래 매트릭스가 그걸 증명한다).
#: 이 예외를 **이 actor · 이 표면 하나로** 좁혀 둔다 — 다른 거부 actor 가 302 로 새면 red.
_CONSTRUCTION_PAGE_REDIRECT_ACTOR = ("STAFF", "CONSTRUCTION")
_CONSTRUCTION_HOME_PREFIX = "/erp/shipment"


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _month_key(year: int, month: int) -> str:
    """(연, 월) → "YYYY-MM"."""
    return f"{year:04d}-{month:02d}"


def _default_range() -> tuple[str, str]:
    """API 기본 조회 범위(전월 ~ 이번 달, KST).

    Returns:
        ``(month_from, month_to)``.
    """
    today = get_today_kst()  # date 를 반환한다 — .date() 를 부르지 않는다.
    month_to = _month_key(today.year, today.month)
    if today.month == 1:
        month_from = _month_key(today.year - 1, 12)
    else:
        month_from = _month_key(today.year, today.month - 1)
    return month_from, month_to


def _json_text(payload) -> str:
    """응답 본문을 **한글 그대로** 직렬화한다.

    Flask 는 기본적으로 JSON 을 ASCII 이스케이프(``\\uXXXX``)한다. 원문 바이트에서
    한글을 찾으면 유출이 있어도 통과해 버리므로, 파싱한 뒤 다시 직렬화해서 본다.
    """
    return json.dumps(payload, ensure_ascii=False)


def _render_sub_nav(app, user) -> str:
    """ERP 서브 내비를 해당 사용자 세션으로 렌더한다(``policy_can`` context processor 적용).

    test_auth_finance ``_render_completion_body`` 와 같은 패턴 — 실제 렌더 결과를 봐야
    "정책은 맞는데 템플릿이 안 걸었다"는 회귀를 잡는다.

    Args:
        app: Flask 앱.
        user: 렌더 주체 User.

    Returns:
        렌더된 HTML.
    """
    from flask import render_template, session as flask_session

    with app.test_request_context("/"):
        flask_session["user_id"] = user.id
        return render_template(_SUB_NAV_TEMPLATE, erp_sub_nav_active="settlement")


# ==========================================================================
# 계약 1 — 권한 매트릭스 × 전 GET 라우트
# ==========================================================================
def test_actor_matrix_is_the_finance_matrix():
    """이 파일이 쓰는 actor 목록이 AUTH-FINANCE-01 매트릭스 그대로인지 못박는다.

    import 로 재사용하고 있으니 자동으로 같지만, 원본이 조용히 축소되면 여기 커버리지도
    같이 줄어든다. 구성을 명시로 고정해 그 축소를 red 로 만든다.
    """
    assert _ALLOWED_ACTORS == [
        ("ADMIN", None),
        ("MANAGER", None),
        ("STAFF", "CS"),
        ("STAFF", "SALES"),
    ]
    assert _DENIED_ACTORS == [
        ("VIEWER", None),
        ("STAFF", "PRODUCTION"),
        ("STAFF", "DRAWING"),
        ("STAFF", "CONSTRUCTION"),
        ("STAFF", "SHIPMENT"),
    ]


@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
@pytest.mark.parametrize("name,path,is_json", _GET_SURFACES, ids=_SURFACE_IDS)
def test_settlement_get_allowed_actors(client, app, role, team, name, path, is_json):
    """ADMIN/MANAGER·STAFF+CS/SALES 는 정산 페이지·API 를 200 으로 연다."""
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=300_000))
    _login(client, _make_user(role=role, team=team))

    resp = client.get(path)

    assert resp.status_code == 200, (role, team, path, resp.get_data(as_text=True)[:400])
    if is_json:
        body = resp.get_json()
        assert body["success"] is True, (role, team, body)
        assert body["error"] is None
        assert isinstance(body["data"], dict)


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
@pytest.mark.parametrize("name,path,is_json", _GET_SURFACES, ids=_SURFACE_IDS)
def test_settlement_get_denied_actors(client, app, role, team, name, path, is_json):
    """VIEWER·비 CS/SALES STAFF 는 403 — redirect 로 얼버무리지 않는다.

    GET 은 before_request 정책 가드에 도달하지 않으므로(``_WRITE_METHODS``), 이 403 은
    **핸들러 내부 판정**이 내야 한다. 이 테스트는 ``AUTH_POLICY_ENABLED`` 를 켜지 않는다
    (``TESTING=True`` 기본 = 가드 OFF) — 가드에 기댄 구현은 여기서 200 을 내고 red 다.

    단 하나의 예외가 :data:`_CONSTRUCTION_PAGE_REDIRECT_ACTOR` 다(사유는 그 상수 주석).
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=300_000))
    _login(client, _make_user(role=role, team=team))

    resp = client.get(path)

    if not is_json and (role, team) == _CONSTRUCTION_PAGE_REDIRECT_ACTOR:
        # 정산 핸들러보다 앞선 플랫폼 네비 가드가 먼저 막는다 — 접근 차단은 동일.
        assert resp.status_code == 302, (role, team, path, resp.status_code)
        location = resp.headers.get("Location", "")
        assert location.startswith(_CONSTRUCTION_HOME_PREFIX), (role, team, location)
        assert PAGE_URL not in location, (role, team, location)
        return

    assert resp.status_code == 403, (role, team, path, resp.status_code)
    assert "Location" not in resp.headers, (role, team, path, "거부는 redirect 가 아니라 403")
    if is_json:
        body = resp.get_json()
        assert body["success"] is False, (role, team, body)
        assert body["data"] is None
        assert body["error"], "거부 사유 문자열이 있어야 한다"


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_settlement_api_denied_leaks_no_aggregate(client, app, role, team):
    """거부 응답에는 집계 스키마 조각이 한 톨도 없어야 한다(부분 유출 차단)."""
    _seed_order(completion="2026-08-10", sd=_money(items_total=5_000_000, deposit=1_000_000))
    _login(client, _make_user(role=role, team=team))

    body = client.get(API_URL).get_json()

    assert body["data"] is None
    text = _json_text(body)
    for key in ("kpi", "buckets", "aging", "settlement_status"):
        assert f'"{key}"' not in text, (role, team, key)


def test_construction_team_page_blocked_by_platform_nav_guard_but_api_403(client, app):
    """CONSTRUCTION 팀: 페이지는 플랫폼 네비 가드가(302), API 는 정산 핸들러가(403) 막는다.

    두 경로 모두 "정산 데이터를 못 본다"로 끝나야 한다. 이 테스트가 red 로 잡는 것은
    ``/api/`` 를 네비 가드 제외 목록에서 빼는 회귀다 — 그러면 CONSTRUCTION 의 API 요청이
    403 JSON 대신 HTML 302 를 받아 fetch 가 ``JSON.parse`` 로 죽는다(P1-13/P1-18 불변식,
    벨 알림·웹 푸시가 실제로 그렇게 무음이 됐던 전례가 가드 docstring 에 남아 있다).
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=4_000_000, deposit=1_000_000))
    role, team = _CONSTRUCTION_PAGE_REDIRECT_ACTOR
    _login(client, _make_user(role=role, team=team))

    page = client.get(PAGE_URL)
    assert page.status_code == 302
    assert page.headers.get("Location", "").startswith(_CONSTRUCTION_HOME_PREFIX)

    api = client.get(API_URL)
    assert api.status_code == 403, api.get_data(as_text=True)[:300]
    assert "Location" not in api.headers, "API 거부는 302 가 아니라 403 JSON"
    assert api.get_json()["success"] is False
    assert api.get_json()["data"] is None


# ==========================================================================
# 계약 2 — 미인증
# ==========================================================================
@pytest.mark.parametrize("name,path,is_json", _GET_SURFACES, ids=_SURFACE_IDS)
def test_settlement_get_requires_login(client, app, name, path, is_json):
    """미인증 접근은 로그인 리다이렉트(또는 401) — 절대 200 이 아니다.

    실제 ``@login_required`` 는 flash + ``redirect(url_for('auth.login', next=...))`` 라
    ``/api`` 표면에서도 302 다(실측: ``/api/orders/completion`` → 302 ``/login?next=...``).
    구현이 API 에 401 JSON 을 쓰기로 해도 계약(비인증 차단)은 만족하므로 둘 다 허용한다.
    """
    resp = client.get(path)

    assert resp.status_code in (301, 302, 401), (path, resp.status_code)
    if resp.status_code in (301, 302):
        assert "/login" in resp.headers.get("Location", ""), (path, resp.headers.get("Location"))


# ==========================================================================
# 계약 3 — 정책 등재 자체 (FINANCE_MUTATION 과 동일 집합)
# ==========================================================================
def test_settlement_policy_is_registered():
    """``POLICY_REGISTRY`` 에 정산 열람 정책이 등재돼 있다.

    ``user_can`` 은 미등록 id 에 조용히 False 를 주므로, 등재 누락은 "전원 403" 이라는
    무음 장애로 나타난다. 여기서 먼저 시끄럽게 죽인다.
    """
    assert SETTLEMENT_POLICY_ID in POLICY_REGISTRY
    assert POLICY_REGISTRY[SETTLEMENT_POLICY_ID].policy_id == SETTLEMENT_POLICY_ID


def test_settlement_policy_fields_match_finance():
    """허용 집합 정의(teams·viewer·manager_ok·anonymous·assignment)가 금융과 동일하다."""
    settle = POLICY_REGISTRY[SETTLEMENT_POLICY_ID]
    finance = POLICY_REGISTRY[FINANCE_POLICY_ID]

    # 2026-09-02(NAVER-SETTLE-01): 회계팀(ACCOUNTING) 신설 — 회계팀 STAFF 도 정산 대시보드
    # 페이지·수금 확인을 써야 네이버 정산 탭에 닿는다. **의도된 확장**이고, 두 정책이
    # 계속 같은 집합이라는 계약(이 파일의 존재 이유)은 그대로다.
    assert tuple(settle.teams) == tuple(finance.teams) == ("CS", "SALES", "ACCOUNTING")
    assert settle.viewer is finance.viewer is False, "VIEWER 하드 deny"
    assert settle.manager_ok is finance.manager_ok is True
    assert settle.anonymous is finance.anonymous is False
    assert settle.assignment == finance.assignment is None, "정산 열람은 배정과 무관"


@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS + _DENIED_ACTORS)
def test_settlement_policy_decision_matches_finance(app, role, team):
    """9종 actor 전부에서 두 정책의 ``evaluate_policy`` 판정이 완전히 일치한다.

    필드 비교만으로는 "필드는 같은데 평가가 갈리는" 미래 변경을 못 잡는다. 실제 판정
    결과(allowed/status/code)를 actor 별로 대조하는 쪽이 강한 계약이다.
    """
    user = _make_user(role=role, team=team)
    settle = evaluate_policy(POLICY_REGISTRY[SETTLEMENT_POLICY_ID], user)
    finance = evaluate_policy(POLICY_REGISTRY[FINANCE_POLICY_ID], user)

    assert (settle.allowed, settle.status, settle.code) == (
        finance.allowed,
        finance.status,
        finance.code,
    ), (role, team, settle, finance)
    # 매트릭스 자체도 못박는다 — 둘이 나란히 틀리는 경우를 배제한다.
    assert settle.allowed is ((role, team) in _ALLOWED_ACTORS), (role, team, settle)
    assert user_can(SETTLEMENT_POLICY_ID, user) is settle.allowed


def test_settlement_policy_denies_anonymous_like_finance():
    """미인증(user=None)은 401 — 금융 정책과 동일(anonymous 정책이 아니다)."""
    settle = evaluate_policy(POLICY_REGISTRY[SETTLEMENT_POLICY_ID], None)
    finance = evaluate_policy(POLICY_REGISTRY[FINANCE_POLICY_ID], None)

    assert settle.allowed is False and settle.status == 401
    assert (settle.allowed, settle.status, settle.code) == (
        finance.allowed,
        finance.status,
        finance.code,
    )
    assert user_can(SETTLEMENT_POLICY_ID, None) is False


def test_settlement_policy_not_in_ancillary_allowlist():
    """정산 열람은 ancillary(자기 알림/구독 등 VIEWER 예외) 가 아니다.

    ``ANCILLARY_ALLOWLIST`` 길이 9 는 별도 게이트가 단언한다(§2.1 line 155). 정산이
    실수로 여기 들어가면 VIEWER 가 통과하므로 두 가지를 함께 못박는다.
    """
    assert SETTLEMENT_POLICY_ID not in ANCILLARY_ALLOWLIST
    assert len(ANCILLARY_ALLOWLIST) == 9


# ==========================================================================
# 계약 4 — API 응답 계약
# ==========================================================================
def test_api_success_envelope_and_m1_schema(client, app):
    """성공 응답 = ``{'success': True, 'data': <M1 반환값>, 'error': None}`` 그대로.

    ``data`` 는 M1 집계 결과의 **passthrough** 여야 한다. 라우트가 스키마를 다시 짜거나
    일부만 골라 담으면(집계 규칙 이중화) 여기서 red 가 난다.
    """
    _seed_order(completion="2026-08-10", sd=_money(items_total=2_000_000, deposit=500_000))
    _seed_order(completion="2026-07-03", sd=_money(items_total=1_500_000, deposit=1_500_000))
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(f"{API_URL}?month_from=2026-07&month_to=2026-08&granularity=day")

    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    body = resp.get_json()
    assert set(body) >= {"success", "data", "error"}
    assert body["success"] is True
    assert body["error"] is None

    data = body["data"]
    assert set(data) == _M1_DATA_KEYS, set(data) ^ _M1_DATA_KEYS
    assert data["range"] == {
        "month_from": "2026-07",
        "month_to": "2026-08",
        "granularity": "day",
    }

    expected = aggregate_settlement(
        db_session, month_from="2026-07", month_to="2026-08", granularity="day"
    )
    assert data == json.loads(json.dumps(expected)), "라우트는 M1 결과를 그대로 실어야 한다"


# ==========================================================================
# 담당자별 매출 = 직원 실적. 화면 열람 권한보다 한 단계 좁다(스펙 §13.6).
# ==========================================================================
@pytest.mark.parametrize("role,team", [("ADMIN", None), ("MANAGER", None)])
def test_manager_breakdown_is_served_to_managers(client, app, role, team):
    """관리자급은 담당자별 매출을 받는다."""
    _seed_order(completion="2026-08-05", sd=_money(items_total=2_000_000, deposit=0))
    _login(client, _make_user(role=role, team=team))

    data = client.get(API_URL).get_json()["data"]

    assert _MANAGER_ONLY_DATA_KEYS <= set(data), "관리자급에게 담당자별 매출이 안 갔다"


@pytest.mark.parametrize("team", ["CS", "SALES"])
def test_manager_breakdown_is_stripped_from_payload_for_staff(client, app, team):
    """STAFF 는 정산 화면은 보되 담당자별 매출은 **payload 에서부터** 못 받는다.

    데이터를 다 내려주고 클라이언트에서 감추는 방식은 개발자 도구로 그대로 보인다 —
    이 저장소의 클라 숨김 금지 원칙이라 서버가 키를 지우고 보내는지를 본다.
    """
    _seed_order(
        completion="2026-08-05",
        sd=_money(items_total=2_000_000, deposit=0),
        customer_name="실적노출탐지",
    )
    _login(client, _make_user(role="STAFF", team=team))

    response = client.get(API_URL)
    data = response.get_json()["data"]

    assert response.status_code == 200, "STAFF 는 정산 화면 자체는 볼 수 있어야 한다"
    assert set(data) == _STAFF_DATA_KEYS, (
        f"STAFF payload 키가 계약과 다르다: {set(data) ^ _STAFF_DATA_KEYS}"
    )
    assert "담당자" not in json.dumps(data, ensure_ascii=False), (
        "담당자 이름이 다른 키에 얹혀 새어 나갔다"
    )


def test_api_defaults_to_previous_and_current_month_day_granularity(client, app):
    """파라미터 없이 호출하면 전월~이번 달(KST) · granularity=day."""
    _login(client, _make_user(role="STAFF", team="CS"))

    resp = client.get(API_URL)

    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    month_from, month_to = _default_range()
    assert resp.get_json()["data"]["range"] == {
        "month_from": month_from,
        "month_to": month_to,
        "granularity": "day",
    }


@pytest.mark.parametrize(
    "query,label",
    [
        ("month_from=2026-8&month_to=2026-09", "월 형식(zero-pad 없음)"),
        ("month_from=202608&month_to=2026-09", "월 형식(구분자 없음)"),
        ("month_from=2026-07&month_to=nope", "월 형식(비수치)"),
        ("month_from=2026-08&month_to=2026-07", "범위 역전"),
        ("month_from=2025-01&month_to=2026-01", "13개월 초과"),
        ("month_from=2026-07&month_to=2026-08&granularity=hour", "granularity 미지원"),
    ],
)
def test_api_invalid_params_return_400(client, app, query, label):
    """잘못된 파라미터는 400 + 통일 형식. 500 으로 새거나 조용히 기본값으로 눕지 않는다."""
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(f"{API_URL}?{query}")

    assert resp.status_code == 400, (label, resp.status_code, resp.get_data(as_text=True)[:300])
    body = resp.get_json()
    assert body["success"] is False, (label, body)
    assert body["data"] is None
    assert isinstance(body["error"], str) and body["error"], label


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_api_accepts_all_supported_granularities(client, app, granularity):
    """지원 granularity 3종은 모두 200 이고 range 에 그대로 echo 된다."""
    _seed_order(completion="2026-08-10", sd=_money(items_total=900_000, deposit=100_000))
    _login(client, _make_user(role="STAFF", team="SALES"))

    resp = client.get(f"{API_URL}?month_from=2026-08&month_to=2026-08&granularity={granularity}")

    assert resp.status_code == 200, (granularity, resp.get_data(as_text=True)[:300])
    assert resp.get_json()["data"]["range"]["granularity"] == granularity


def test_api_response_carries_no_order_rows(client, app):
    """응답은 집계 버킷만 — 주문 행 원본(고객명·연락처)이 실리면 안 된다.

    "집계만 보여준다"가 CS/SALES 열람 허용의 전제다. 원본 PII 가 새면 권한 설계가 무너진다.
    Flask 는 JSON 을 ASCII 이스케이프하므로 원문 바이트가 아니라 **파싱 후 재직렬화**한
    문자열에서 찾는다(이스케이프된 한글은 원문 검색으로 못 잡는다).
    """
    marker = "정산유출탐지고객"
    _seed_order(
        completion="2026-08-10",
        sd=_money(items_total=3_000_000, deposit=500_000),
        customer_name=marker,
    )
    _login(client, _make_user(role="ADMIN"))

    body = client.get(f"{API_URL}?month_from=2026-08&month_to=2026-08").get_json()

    text = _json_text(body)
    assert marker not in text, "고객명이 응답에 실렸다"
    assert "010-0000-0000" not in text, "연락처가 응답에 실렸다"


def test_settlement_routes_are_read_only(app):
    """두 라우트가 SPEC URL 그대로 등록되고 **GET 전용**이다.

    쓰기 method 가 붙는 순간 write guard·mutation policy manifest 등재 대상이 되고
    (`tests/domains/test_write_guard.py`·`test_auth_enforcement.py` 의 static gate),
    "읽기 전용 대시보드"라는 설계 전제도 깨진다.
    """
    rules = {
        rule.rule: rule
        for rule in app.url_map.iter_rules()
        if rule.rule in (PAGE_URL, API_URL)
    }

    assert set(rules) == {PAGE_URL, API_URL}, sorted(rules)
    for path, rule in rules.items():
        assert rule.methods <= {"GET", "HEAD", "OPTIONS"}, (path, sorted(rule.methods))


# ==========================================================================
# 계약 5 — UI 은닉 (같은 policy_id 로 네비 진입 링크를 숨긴다)
# ==========================================================================
@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_nav_entry_hidden_for_denied(app, client, role, team):
    """권한 없는 사용자의 ERP 서브 내비에는 정산 대시보드 링크가 없다."""
    html = _render_sub_nav(app, _make_user(role=role, team=team))

    assert PAGE_URL not in html, (role, team)


@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
def test_nav_entry_shown_for_allowed(app, client, role, team):
    """허용 사용자의 ERP 서브 내비에는 정산 대시보드 링크가 있다."""
    html = _render_sub_nav(app, _make_user(role=role, team=team))

    assert PAGE_URL in html, (role, team)
