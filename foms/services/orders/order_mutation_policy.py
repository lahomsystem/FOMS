"""주문 mutation 권한 정책 SSOT + 공용 route 가드 (AUTH-01, §2.1 역할·팀 권한 정본).

§2.1 authorization 정본을 **모든 cookie-auth state-changing route 에 실제 enforce** 한다.
이 모듈은 두 부분으로 구성된다.

1. **정책 SSOT**(:data:`POLICY_REGISTRY`): 각 ``policy_id`` 의 허용 role/team,
   order assignment 요구, VIEWER deny/ancillary 여부를 **데이터로** 선언한다. 평가 순서
   (§2.1)는 :func:`evaluate_policy` 한 곳에 고정한다::

       authentication
         → role hard deny (VIEWER)
         → domain/team capability
         → order assignment/participation
         → command-specific state predicate   (← business state 는 STATE packet 몫;
                                                   AUTH-01 은 권한 게이트만)
         → ADMIN/MANAGER emergency override

2. **route 가드**(:func:`enforce_order_mutation_policy`): before_request 훅으로 요청
   endpoint 를 ``docs/harness/foms_order_mutation_policy_manifest.json`` (URL-map
   inventory)에서 policy_id 로 조회해 :func:`evaluate_policy` 를 적용한다. ``/api``·
   ``/erp/api`` 권한 실패는 **403 JSON**(redirect 0 — P1-13/P1-18), HTML page 실패는
   redirect 를 허용한다. manifest 미등재 endpoint 는 static gate 가 red 로 잡는다
   (:mod:`tests.domains.test_auth_enforcement`).

가드는 :func:`_policy_active` (config ``AUTH_POLICY_ENABLED``, 미지정 시 ``not TESTING``)
로 켜진다. WRITE-GUARD-01 과 같은 관례라 기존 테스트(``TESTING=True``)는 무회귀로 통과하고
enforcement 전용 테스트만 명시로 활성화한다.

**경계(AUTH-01)**: business state 전이 로직을 바꾸지 않는다. JSONB 이름 배열이 아니라
ASSIGNMENT-00 ``order_assignments`` user-ID row(:func:`active_assignee_ids`)만 assignment
판정에 쓴다. UI 은닉은 같은 policy_id 로 하되 backend 권한을 대체하지 않는다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from flask import Flask, g, jsonify, redirect, request, session

# --------------------------------------------------------------------------- #
# 팀/역할 상수
# --------------------------------------------------------------------------- #
#: MEASURE→SALES 정규화 (§2.1 line 148 (a)/(b)): legacy pseudo-team ``MEASURE`` 는
#: capability 판정에서 SALES 로 정규화한다. team=MEASURE 를 무권한으로 방치하지 않는다.
_TEAM_NORMALIZE = {"MEASURE": "SALES"}

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: §2.1 line 155: role hard deny 의 exact ancillary 예외 9종. VIEWER 도 자기
#: notification/subscription/room/urgent-call 에만 이 allowlist 를 쓸 수 있고, 각 route 가
#: owner/membership/order scope 를 재검사한다(AUTH-01 은 게이트만; owner 재검사는 route).
ANCILLARY_ALLOWLIST = frozenset({
    "MARK_OWN_NOTIFICATION_READ",
    "ARCHIVE_OWN_NOTIFICATION",
    "ACK_OWN_NOTIFICATION",
    "CREATE_OWN_PUSH_SUBSCRIPTION",
    "DELETE_OWN_PUSH_SUBSCRIPTION",
    "MARK_ROOM_READ",
    "SEND_CHAT_MESSAGE",
    "UPLOAD_CHAT_ATTACHMENT",
    "SEND_URGENT_CALL",
})


# --------------------------------------------------------------------------- #
# 정책 데이터 모델
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Policy:
    """한 command-group 의 권한 정책(§2.1 데이터).

    Attributes:
        policy_id: 정책 식별자(route manifest·UI 은닉이 공유).
        teams: STAFF 가 team capability 로 통과하는 팀 tuple. ``"*"`` 면 모든 STAFF 팀,
            빈 tuple 이면 **team 만으로는 STAFF 통과 불가**(master 등 role-only 정책).
            비교 전 :data:`_TEAM_NORMALIZE` 로 MEASURE→SALES 정규화한다.
        assignment: ``"DRAWING"|"CONSTRUCTION"|"SALES"`` 면 해당 domain 의 active
            assignment 를 요구한다(조건부: active row 가 있으면 assignee 만, 없으면
            team capability 로 폴백 — §2.1 line 249 backfill 미완 시 lock-out 방지).
        viewer: True 면 VIEWER 허용(ancillary/pure-calc/self). 기본 False = VIEWER hard deny.
        manager_ok: MANAGER 통과 여부. False 면 ADMIN 전용(account/ops 관리).
        anonymous: True 면 미인증도 통과(login/register — pre-auth).
        description: 근거 메모.
    """

    policy_id: str
    teams: Any = ()  # tuple[str, ...] | "*"
    assignment: Optional[str] = None
    viewer: bool = False
    manager_ok: bool = True
    anonymous: bool = False
    description: str = ""


def _p(policy_id: str, **kw: Any) -> Policy:
    return Policy(policy_id=policy_id, **kw)


#: §2.1 정책 SSOT. policy_id → :class:`Policy`. route manifest 가 이 키를 참조한다.
POLICY_REGISTRY: dict[str, Policy] = {
    # --- 계정/세션/관리 (§2.1 account) --------------------------------------
    "ACCOUNT_ANON": _p("ACCOUNT_ANON", anonymous=True, viewer=True, teams="*",
                       description="login/register — pre-auth anonymous account bootstrap."),
    "ACCOUNT_SELF": _p("ACCOUNT_SELF", viewer=True, teams="*",
                       description="logout/profile/switch-back — authenticated self."),
    "ACCOUNT_ADMIN": _p("ACCOUNT_ADMIN", teams=(), manager_ok=False,
                        description="ADMIN 사용자 CRUD/impersonation — ADMIN 전용."),
    "ADMIN_OPS": _p("ADMIN_OPS", teams=(), manager_ok=False,
                    description="ops approval review / admin menu — ADMIN 전용."),

    # --- 금융 (§2.1 line 153, P0-3) -----------------------------------------
    "FINANCE_MUTATION": _p("FINANCE_MUTATION", teams=("CS", "SALES", "ACCOUNTING"),
                           description="settlement/cash/payment-confirm — ADMIN/MANAGER 또는 STAFF+CS/SALES/ACCOUNTING. VIEWER deny(P0-3)."),
    # read-only 지만 전사 매출·미수 총액을 노출하므로 금융 집합과 같은 게이트를 쓴다
    # (SETTLE-DASH-01 §5). GET 은 before_request 가드를 안 타므로 집행은 핸들러 내부다.
    # 2026-09-02(NAVER-SETTLE-01): 회계팀 STAFF 도 정산 대시보드 페이지·수금 확인을 써야
    # 네이버 정산 탭에 닿는다 → 두 정책의 teams 를 함께 확장한다(집합 동일 계약 유지).
    "SETTLEMENT_DASHBOARD_READ": _p("SETTLEMENT_DASHBOARD_READ", teams=("CS", "SALES", "ACCOUNTING"),
                                    description="정산 대시보드 열람(read-only) — FINANCE_MUTATION 과 동일 집합. VIEWER deny."),
    # 채널(네이버) 정산 탭은 위 집합보다 **더 좁다**. MANAGER 는 엔진에서 팀보다 먼저
    # 통과하므로 "ADMIN + 회계팀"을 manager_ok 로는 표현할 수 없다 — 정본 판정은
    # settlement_channel_access.can_view_channel_settlement 이고 여기 등재는
    # manifest·가드 pre-filter 전용이다.
    "SETTLEMENT_CHANNEL_READ": _p("SETTLEMENT_CHANNEL_READ", teams=("ACCOUNTING",),
                                  description="채널(네이버) 정산 탭·API 열람 — 정본 판정은 settlement_channel_access.can_view_channel_settlement (ADMIN, 또는 team=ACCOUNTING 인 MANAGER/STAFF). 엔진 등록은 manifest·가드 전용."),
    "SETTLEMENT_CHANNEL_SYNC": _p("SETTLEMENT_CHANNEL_SYNC", teams=("ACCOUNTING",),
                                  description="채널 정산 '지금 동기화' enqueue — READ 와 같은 판정, 핸들러가 게이트 함수로 재검사."),

    # --- 주문 form/estimate/일반 (CS/SALES team-wide) -----------------------
    "ERP_EDIT": _p("ERP_EDIT", teams=("CS", "SALES"),
                   description="주문 form/finance-외 CS·SALES command(call-log/cs-complete/confirm/AS/estimate/measurement/address/gateway). MEASURE→SALES."),

    # --- 일반 STAFF 업무(전 팀 열람+쓰기, 현행 role_required STAFF) ----------
    "STAFF_MUTATION": _p("STAFF_MUTATION", teams="*",
                         description="structured/field/status/regional/quest/task/draft/blueprint/attachment/queue 등 전 STAFF 팀 업무. VIEWER deny."),

    # --- 생산 (§2.1 line 164, P0-9) -----------------------------------------
    "PRODUCTION_EDIT": _p("PRODUCTION_EDIT", teams=("CS", "SALES", "PRODUCTION"),
                          description="production start/complete/rework/steps/defect/hold/ack — CS/SALES/PRODUCTION team-wide(P0-9 역전 수정). 전이는 STATE-PROD-01."),

    # --- 시공 (§2.1 line 165) -----------------------------------------------
    "CONSTRUCTION_EDIT": _p("CONSTRUCTION_EDIT", teams=("CS", "SALES", "CONSTRUCTION"),
                            description="AS register 등 시공 team-wide(assignment 미요구)."),
    "CONSTRUCTION_ASSIGNED": _p("CONSTRUCTION_ASSIGNED", teams=("CS", "SALES", "CONSTRUCTION"),
                                assignment="CONSTRUCTION",
                                description="construction start/evidence/complete/fail — 배정된 CONSTRUCTION user ID(§2.1 line 168). backfill 전이면 team 폴백."),
    "PACKING_WRITE": _p("PACKING_WRITE", teams=("CS", "SALES", "SHIPMENT", "CONSTRUCTION"),
                        description="packing write — SHIPMENT team-wide + assigned CONSTRUCTION(§2.1 packing 분리)."),

    # --- 도면 (§2.1 line 166-168) -------------------------------------------
    "DRAWING_ASSIGNED": _p("DRAWING_ASSIGNED", teams=("DRAWING",), assignment="DRAWING",
                           description="drawing wizard/transfer/revision/ack — DRAWING + explicit assignee ID(§2.1). backfill 전이면 team 폴백."),
    "DRAWING_TEAM": _p("DRAWING_TEAM", teams=("DRAWING",),
                       description="drawing preset(global) — DRAWING team + Admin(WIZ-PRESET-01)."),

    # --- 출고/물류 (§2.1 line 165, STAFF/SHIPMENT) --------------------------
    "SHIPMENT_EDIT": _p("SHIPMENT_EDIT", teams=("CS", "SALES", "SHIPMENT"),
                        description="shipment per-order update/AS-recommendation — CS/SALES/SHIPMENT team-wide."),
    "SHIPMENT_REFERENCE": _p("SHIPMENT_REFERENCE", teams=("SHIPMENT",),
                             description="shipment reference lists 설정(UPDATE_SHIPMENT_REFERENCE_LISTS) — STAFF+SHIPMENT 또는 ADMIN/MANAGER(SHIPMENT-REFERENCE-01). CS/SALES·VIEWER deny."),

    # --- 관리(MANAGER+/ADMIN) -----------------------------------------------
    "MANAGER_MUTATION": _p("MANAGER_MUTATION", teams=(),
                           description="bulk delete/restore — ADMIN/MANAGER."),
    "ADMIN_MUTATION": _p("ADMIN_MUTATION", teams=(), manager_ok=False,
                         description="permanent delete — ADMIN 전용."),

    # --- WDC (§2.1 line 154) ------------------------------------------------
    "WDC_CALCULATE": _p("WDC_CALCULATE", teams="*", viewer=True,
                        description="WDC calculate — 로그인 사용자 pure calc, DB 무변경. VIEWER 허용."),
    "WDC_ESTIMATE": _p("WDC_ESTIMATE", teams=("CS", "SALES"),
                       description="WDC estimate save/match/unmatch/sync — ADMIN/MANAGER 또는 STAFF+CS/SALES."),
    "MASTER_MUTATION": _p("MASTER_MUTATION", teams=(),
                          description="product/category/notes/spec-preset master — ADMIN/MANAGER(WDC-AUTH-01). VIEWER·STAFF deny."),

    # --- 채팅 room lifecycle (§2.1 line 156) --------------------------------
    "CHAT_ROOM": _p("CHAT_ROOM", teams="*",
                    description="chat room create/manage — ADMIN/MANAGER 또는 STAFF. VIEWER admin deny."),

    # --- 자기-scope 푸시 telemetry (self, VIEWER 허용, 업무 mutation 아님) ---
    "OWN_PUSH_SELF": _p("OWN_PUSH_SELF", teams="*", viewer=True,
                        description="자기 push test/event 기록 — self telemetry(§2.1 '자기 subscription/notification' 취지). Order business 아님."),

    # --- ancillary allowlist 9종 (§2.1 line 155, VIEWER 허용, owner 재검사는 route) ---
    "MARK_OWN_NOTIFICATION_READ": _p("MARK_OWN_NOTIFICATION_READ", teams="*", viewer=True,
                                     description="자기 notification read — ancillary."),
    "ARCHIVE_OWN_NOTIFICATION": _p("ARCHIVE_OWN_NOTIFICATION", teams="*", viewer=True,
                                   description="자기 notification archive/delete — ancillary."),
    "ACK_OWN_NOTIFICATION": _p("ACK_OWN_NOTIFICATION", teams="*", viewer=True,
                              description="자기 notification ack — ancillary."),
    "CREATE_OWN_PUSH_SUBSCRIPTION": _p("CREATE_OWN_PUSH_SUBSCRIPTION", teams="*", viewer=True,
                                       description="자기 push subscription create/delete — ancillary."),
    "DELETE_OWN_PUSH_SUBSCRIPTION": _p("DELETE_OWN_PUSH_SUBSCRIPTION", teams="*", viewer=True,
                                       description="자기 push subscription delete — ancillary(subscribe endpoint 공유)."),
    "MARK_ROOM_READ": _p("MARK_ROOM_READ", teams="*", viewer=True,
                         description="active member room mark-read — ancillary."),
    "SEND_CHAT_MESSAGE": _p("SEND_CHAT_MESSAGE", teams="*", viewer=True,
                            description="active member 메시지 전송 — ancillary."),
    "UPLOAD_CHAT_ATTACHMENT": _p("UPLOAD_CHAT_ATTACHMENT", teams="*", viewer=True,
                                 description="chat 첨부 업로드 — ancillary."),
    "SEND_URGENT_CALL": _p("SEND_URGENT_CALL", teams="*", viewer=True,
                           description="read-scope Order urgent call — ancillary(participant/target/rate 재검사는 route)."),
}


# --------------------------------------------------------------------------- #
# 평가 결과
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Decision:
    """정책 평가 결과."""

    allowed: bool
    status: int = 200
    code: str = "OK"
    reason: str = ""


_ALLOW = Decision(allowed=True)


def normalize_team(team: Optional[str]) -> str:
    """team 문자열을 정규화(trim·upper·MEASURE→SALES)."""
    t = (team or "").strip().upper()
    return _TEAM_NORMALIZE.get(t, t)


def evaluate_policy(
    policy: Policy,
    user: Any,
    *,
    active_assignee_ids: Optional[list[int]] = None,
) -> Decision:
    """§2.1 평가 순서로 정책을 판정한다(business state predicate 제외).

    Args:
        policy: 대상 :class:`Policy`.
        user: 현재 사용자(``None`` 이면 미인증). ``role``/``team``/``id`` 를 읽는다.
        active_assignee_ids: policy.assignment domain 의 현재 active 배정 user_id.
            ``None`` 이면 assignment 미조회(caller 가 order 없음/불필요로 판단). 빈 list 는
            "조회했으나 배정 0" — team capability 로 폴백한다(backfill 미완 lock-out 방지).

    Returns:
        :class:`Decision`. 거부는 401(AUTH_REQUIRED)/403(FORBIDDEN).
    """
    # 1. authentication
    if user is None:
        if policy.anonymous:
            return _ALLOW
        return Decision(False, 401, "AUTH_REQUIRED", "로그인이 필요합니다.")

    role = (getattr(user, "role", None) or "").strip().upper()

    # 2. role hard deny (VIEWER)
    if role == "VIEWER":
        if policy.viewer:
            return _ALLOW
        return Decision(False, 403, "FORBIDDEN", "조회 전용 계정은 이 작업을 할 수 없습니다.")

    # anonymous 정책은 인증 사용자도 통과(login 페이지 재방문 등)
    if policy.anonymous:
        return _ALLOW

    # 3. ADMIN/MANAGER override (정상 command 는 reason 불요; bypass reason 은 STATE 몫)
    if role == "ADMIN":
        return _ALLOW
    if role == "MANAGER":
        if policy.manager_ok:
            return _ALLOW
        return Decision(False, 403, "FORBIDDEN", "관리자 전용 작업입니다.")

    # 4. STAFF domain/team capability
    if role != "STAFF":
        return Decision(False, 403, "FORBIDDEN", "권한이 없습니다.")
    team = normalize_team(getattr(user, "team", None))
    if policy.teams == "*":
        pass  # 모든 STAFF 팀 허용
    elif not policy.teams:
        return Decision(False, 403, "FORBIDDEN", "이 작업 권한이 없는 팀입니다.")
    elif team not in policy.teams:
        return Decision(False, 403, "FORBIDDEN", "이 작업 권한이 없는 팀입니다.")

    # 5. order assignment/participation (ID-row 기반, JSONB 이름 미사용)
    if policy.assignment and active_assignee_ids is not None:
        if active_assignee_ids:  # 배정 존재 → assignee 만(§2.1 line 167 '이름 비교 금지')
            uid = _int_or_none(getattr(user, "id", None))
            if uid is None or uid not in active_assignee_ids:
                return Decision(False, 403, "FORBIDDEN", "이 주문에 배정된 담당자만 가능합니다.")
        # 배정 0(backfill 미완) → team capability 로 이미 통과(폴백)

    return _ALLOW


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def user_can_read_order(user: Any, order: Any = None) -> bool:
    """일반 Order detail(``@login_required``)과 동일한 canonical read scope.

    §2.1 line 144: 인증된 active FOMS 사용자는 team·assignment 와 무관하게 모든 Order 를
    조회할 수 있다(VIEWER 포함, GET/HEAD 조회 허용). 이 함수는 그 read 판정의 단일
    chokepoint 이며, manager-mapped Channel quick action 등 cookie-auth 밖 surface 도
    PII 조회 **전에** 재사용한다(CHANNEL-AUTH-01).

    Args:
        user: 조회 주체. ``None``(미인증) 또는 비활성 계정은 거부한다.
        order: 대상 Order. 현재 정책은 order-무관 전역 read 이므로 미사용이나, 향후
            per-order read scope 확장 지점으로 시그니처에 유지한다.

    Returns:
        조회 허용이면 True. 미인증/비활성/role 부재는 False.
    """
    if user is None:
        return False
    if getattr(user, "is_active", None) is False:
        return False
    role = (getattr(user, "role", None) or "").strip().upper()
    return bool(role)


# --------------------------------------------------------------------------- #
# route → policy_id manifest (URL-map inventory)
# --------------------------------------------------------------------------- #
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_MANIFEST_PATH = os.path.join(
    _REPO_ROOT, "docs", "harness", "foms_order_mutation_policy_manifest.json"
)

#: register 시 채워지는 endpoint → policy_id (``"__EXEMPT__"`` 포함).
_ROUTE_POLICY: dict[str, str] = {}

#: manifest 미등재 endpoint 의 런타임 fail-safe 정책(static gate 가 미등재를 red 로 잡으므로
#: 정상 배포에선 도달하지 않지만, 도달 시 VIEWER deny + STAFF 허용으로 보수적 처리).
_FALLBACK_POLICY = POLICY_REGISTRY["STAFF_MUTATION"]

_EXEMPT = "__EXEMPT__"


def load_policy_manifest() -> dict[str, Any]:
    """route→policy_id manifest(JSON)를 로드.

    Returns:
        manifest dict(``routes`` 등).

    Raises:
        OSError: 파일 부재.
        ValueError: JSON 파싱 실패.
    """
    with open(_MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def policy_id_for_endpoint(endpoint: Optional[str]) -> Optional[str]:
    """endpoint 의 policy_id 를 반환(exempt 는 ``"__EXEMPT__"``, 미등재는 ``None``)."""
    if not endpoint:
        return None
    return _ROUTE_POLICY.get(endpoint)


# --------------------------------------------------------------------------- #
# UI policy context (같은 policy_id 로 control 숨김; backend 대체 아님)
# --------------------------------------------------------------------------- #
def user_can(policy_id: str, user: Any, *, active_assignee_ids: Optional[list[int]] = None) -> bool:
    """UI 은닉용: 사용자가 policy_id command 를 (assignment 무관) 수행 가능한지.

    같은 policy_id 로 backend guard 와 UI 를 일치시킨다(§2.1 line 150). assignment 는
    order 별이라 기본 미조회(control 노출 판정용); 실제 enforcement 는 backend 가 한다.

    Args:
        policy_id: :data:`POLICY_REGISTRY` 키.
        user: 현재 사용자.
        active_assignee_ids: 넘기면 assignment 까지 반영.

    Returns:
        허용 예상이면 True. 미등록 policy_id 는 False(fail-safe).
    """
    policy = POLICY_REGISTRY.get(policy_id)
    if policy is None:
        return False
    return evaluate_policy(policy, user, active_assignee_ids=active_assignee_ids).allowed


# --------------------------------------------------------------------------- #
# before_request 가드
# --------------------------------------------------------------------------- #
def _policy_active() -> bool:
    """이 요청에서 정책 가드를 적용할지(config ``AUTH_POLICY_ENABLED``, 미지정=``not TESTING``)."""
    from flask import current_app

    cfg = current_app.config
    if "AUTH_POLICY_ENABLED" in cfg:
        return bool(cfg["AUTH_POLICY_ENABLED"])
    return not cfg.get("TESTING", False)


def _is_json_namespace(path: str) -> bool:
    """``/api``·``/erp/api`` namespace 여부(권한 실패 시 403 JSON, redirect 0 — P1-13/18)."""
    return path.startswith("/api/") or path.startswith("/erp/api/") or path == "/api"


def _current_user() -> Any:
    """현재 요청의 사용자. ``g.current_user`` 가 있으면 그걸 쓰고, 없을 때만 조회한다.

    ``_set_current_user`` before_request(``foms/platform/http.py``)가 요청마다 이미
    같은 행을 읽어 ``g.current_user`` 에 넣는다. 여기서 다시 조회하면 **같은 요청 안에서
    users 를 두 번 읽는다** — ``policy_can`` 이 공용 서브내비에 실리면서 그 중복이
    ERP 페이지 전 표면의 렌더 비용이 됐다.

    Returns:
        User 또는 None(미인증·세션 없음).
    """
    from foms.web.auth import get_user_by_id

    user = getattr(g, "current_user", None)
    if user is not None:
        return user
    return get_user_by_id(session.get("user_id"))


def _order_id_from_request() -> Optional[int]:
    """route view_args 에서 order_id 추출(assignment 조회용)."""
    args = request.view_args or {}
    return _int_or_none(args.get("order_id"))


def _active_ids_for(policy: Policy) -> Optional[list[int]]:
    """policy.assignment domain 의 active 배정 ID(없으면 ``None``)."""
    if not policy.assignment:
        return None
    order_id = _order_id_from_request()
    if order_id is None:
        return None
    from db import db_session
    from foms.services.orders.assignment import active_assignee_ids

    # 배정 조회 실패는 삼키지 않는다(auth 경로 fail-open 금지 — §4). 존재하지 않는 order 는
    # active_assignee_ids 가 예외 없이 [] 를 반환하므로 team capability 폴백이 자연히 적용된다.
    return active_assignee_ids(db_session, order_id, policy.assignment)


def _deny_response(decision: Decision) -> Any:
    """거부 응답: JSON namespace 는 JSON, HTML 은 redirect(§2.1 line 149)."""
    _audit(decision)
    if _is_json_namespace(request.path):
        resp = jsonify({
            "success": False,
            "data": None,
            # 이관 호환: error(문자열)+message 동시 제공(readApiError 대비).
            "error": decision.reason,
            "message": decision.reason,
            "code": decision.code,
        })
        resp.status_code = decision.status
        resp.headers["X-Auth-Policy"] = "denied"
        return resp
    # HTML page: redirect 허용
    if decision.status == 401:
        return redirect("/login")
    return redirect("/")


def _audit(decision: Decision) -> None:
    """거부 사유를 앱 로거 + ``security_logs`` 에 기록(request context 내 호출).

    로거는 기존대로 유지하고, DB 감사는 **독립 커밋 헬퍼**를 쓴다 — 이 경로는 handler
    실행 전 403 이라 본 트랜잭션 commit 이 없어(스펙 §3-3) 동승 insert 는 소실된다.
    dedupe 는 헬퍼가 (user or IP, endpoint, action) 60초 창으로 처리한다.
    """
    from flask import current_app

    from foms.services.audit_writer import record_access_denied

    user_id = _int_or_none(session.get("user_id"))
    current_app.logger.warning(
        "auth-policy blocked: endpoint=%s code=%s path=%s user=%s",
        request.endpoint, decision.code, request.path, user_id,
    )
    record_access_denied(
        f"권한 거부(주문 정책): {request.method} {request.path} "
        f"endpoint={request.endpoint} code={decision.code}",
        user_id=user_id,
        ip=request.remote_addr,
        endpoint=request.endpoint,
        action=f"policy:{decision.code}",
        # T8 구조화: 자유 텍스트 파싱 없이 "어느 endpoint 가 왜 막았나"를 SQL 로 묻는다.
        structured_action="ACCESS_DENIED",
        detail={"endpoint": request.endpoint, "reason": decision.code},
    )


def enforce_order_mutation_policy() -> Any:
    """공용 before_request 가드: state-changing route 의 §2.1 정책 enforce.

    non-mutating method, 가드 비활성(테스트), 미라우팅(``endpoint is None``), exempt
    endpoint 는 통과시킨다. 그 외는 manifest 의 policy_id(미등재는 fail-safe fallback)로
    :func:`evaluate_policy` 를 적용하고, 거부 시 handler 실행 전에 403(JSON)/redirect(HTML)
    을 반환한다(DB/상태 변화 0).

    Returns:
        차단 시 응답, 통과 시 ``None``.
    """
    if request.method not in _WRITE_METHODS:
        return None
    if not _policy_active():
        return None
    endpoint = request.endpoint
    if endpoint is None:  # 404/미라우팅
        return None
    policy_id = _ROUTE_POLICY.get(endpoint)
    if policy_id == _EXEMPT:
        return None
    policy = POLICY_REGISTRY.get(policy_id, _FALLBACK_POLICY) if policy_id else _FALLBACK_POLICY

    user = _current_user()
    decision = evaluate_policy(policy, user, active_assignee_ids=_active_ids_for(policy))
    if not decision.allowed:
        return _deny_response(decision)
    return None


def register_order_mutation_policy(app: Flask) -> None:
    """앱에 정책 가드를 배선한다(app_factory 에서 1회 호출).

    startup 에 manifest 를 로드해 endpoint→policy_id 를 확정하고 before_request 가드와
    ``policy_can`` template helper 를 등록한다. manifest 부재/파손은 여기서 예외를 일으켜
    앱 부팅을 막는다(per-request 로 조용히 degrade 하지 않음).

    Args:
        app: 대상 Flask 앱.
    """
    global _ROUTE_POLICY
    manifest = load_policy_manifest()
    mapping: dict[str, str] = {}
    for ep, meta in manifest.get("routes", {}).items():
        if not isinstance(meta, dict):
            continue
        if meta.get("mode") == "exempt":
            mapping[ep] = _EXEMPT
        else:
            mapping[ep] = meta["policy_id"]
    _ROUTE_POLICY = mapping
    app.before_request(enforce_order_mutation_policy)
    app.context_processor(lambda: {"policy_can": _template_policy_can})


def _template_policy_can(policy_id: str) -> bool:
    """template context: 현재 세션 사용자가 policy_id command 를 할 수 있는지(UI 은닉)."""
    return user_can(policy_id, _current_user())


__all__ = [
    "Policy", "Decision", "POLICY_REGISTRY", "ANCILLARY_ALLOWLIST",
    "evaluate_policy", "normalize_team", "user_can", "user_can_read_order",
    "load_policy_manifest", "policy_id_for_endpoint",
    "enforce_order_mutation_policy", "register_order_mutation_policy",
]
