"""실측·물류 보드 '완료' 버튼의 경로·차단 판정 (STATE-CONTROLS-02 / C-B1·C-B2).

메인 파이프라인 주문의 최종 완료는 ``POST /api/orders/<id>/cs/complete`` 한 길만 쓴다.
보드의 ``update_order_field(status=COMPLETED)`` 우회로는 quest·보류·AS 게이트를 통째로
건너뛰었기 때문에 이번 계약에서 막힌다(:func:`rejects_completed_field_write`).

이 모듈은 **읽기 전용 판정만** 한다 — 추가 DB 쿼리 0회(전부 structured_data 파생)이고
어떤 값도 쓰지 않는다. 화면(매크로)과 서버(field_update)가 **같은 술어**를 부르므로
'거부당할 버튼' 과 '버튼 없는 막다른 길' 이 둘 다 0이 된다.

:mod:`foms.services.measurement.drawing_transfer_cta` 와 같은 모양의 CTA 빌더다.
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_permissions import can_edit_erp
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.erp_policy_quests import check_quest_approvals_complete
from foms.services.orders.state_axes import (
    read_as_status,
    read_hold,
    read_main_stage,
    read_state_axes,
)

__all__ = [
    "COMPLETE_LABEL",
    "COMPLETE_CONFIRM",
    "CS_PATH_MESSAGE",
    "TERMINAL_STATUSES",
    "complete_block_reason",
    "build_complete_ctas",
    "rejects_completed_field_write",
    "use_cs_complete_response_body",
]


COMPLETE_LABEL = "완료"
COMPLETE_CONFIRM = "이 주문을 완료 처리할까요? 완료된 주문 섹션으로 이동합니다."

#: CS 단계인데도 옛 우회로(field_update)로 들어온 요청에 주는 안내.
CS_PATH_MESSAGE = (
    "이 주문은 CS 단계입니다. 완료는 [완료] 버튼(CS 완료)으로만 처리합니다. "
    "화면을 새로고침한 뒤 다시 눌러 주세요."
)

#: 이미 끝난 축(완료·AS 계열·삭제). 이 행에는 완료 버튼을 그리지 않는다.
TERMINAL_STATUSES = ("COMPLETED", "AS", "AS_RECEIVED", "AS_COMPLETED", "DELETED")

#: AS 축이 열려 있는 상태(cs/complete 의 AS_ACTIVE 게이트와 같은 잣대).
OPEN_AS_STATUSES = ("RECEIVED", "IN_PROGRESS")

_NO_PERMISSION_MESSAGE = (
    "완료 처리 권한이 없습니다. CS·영업팀 또는 관리자만 완료할 수 있습니다."
)


#: 막힌 사유별 "갈 곳" 링크 문구. 사유마다 가는 화면이 다르므로 문구도 달라야 한다.
BLOCKED_LINK_LABELS = {
    "QUEST_INCOMPLETE": "승인하러 가기",
    "HOLD_ACTIVE": "보류 풀러 가기",
    "AS_ACTIVE": "AS 보러 가기",
}


def _deeplink(endpoint: str, fallback: str, **params) -> str:
    """``url_for`` 로 딥링크를 만들고, 요청 컨텍스트 밖이면 고정 경로로 폴백한다.

    좁은 예외만 받는다 — 앱 컨텍스트 밖(RuntimeError)과 라우트 미등록(BuildError)
    두 경우에만 폴백하고, 그 밖의 오류는 그대로 올린다.
    """
    try:
        from flask import url_for
        from werkzeug.routing import BuildError

        return url_for(endpoint, **params)
    except (RuntimeError, BuildError):
        return fallback


def _quest_deeplink(order_id: Any) -> str:
    """주문 상세 퀘스트 칸 딥링크(승인 버튼이 있는 곳)."""
    return _deeplink(
        "erp_dashboard.erp_dashboard",
        f"/erp/dashboard?focus_order={order_id}&open_quest=true",
        focus_order=order_id, open_quest="true",
    )


def _order_deeplink(order_id: Any) -> str:
    """주문 상세 딥링크(보류 해제를 여기서 한다)."""
    return _deeplink(
        "erp_dashboard.erp_dashboard",
        f"/erp/dashboard?focus_order={order_id}",
        focus_order=order_id,
    )


def _as_deeplink(order_id: Any) -> str:
    """AS 대시보드 딥링크(진행 중인 AS 를 여기서 끝낸다)."""
    return _deeplink(
        "erp_as_page.erp_as_dashboard",
        f"/erp/as?focus_order={order_id}",
        focus_order=order_id,
    )


def _cs_quest_missing_teams(sd: dict) -> Optional[list]:
    """CS quest 가 있고 미승인이면 남은 팀 목록, 아니면 None.

    CS quest 자체가 없는 주문은 게이트하지 않는다 — 라우트(cs/complete ``_cs_quest_block``)
    가 lock-out 방지로 통과시키는 길과 같아야 한다.
    """
    quests = sd.get("quests")
    if not isinstance(quests, list) or not quests:
        return None
    if not any(isinstance(q, dict) and q.get("stage") in ("CS",) for q in quests):
        return None
    complete, missing = check_quest_approvals_complete(sd, "CS")
    if complete:
        return None
    return list(missing or [])


def complete_block_reason(order: Any, user: Any):
    """완료를 막는 첫 사유 ``(code, message, href)``. 막을 게 없으면 None.

    판정 순서는 라우트(:mod:`foms.api.cs.complete`)의 게이트와 1:1이다 —
    권한 → main stage CS → CS quest 승인 → 보류 → AS. 순서가 어긋나면 화면이
    서버와 다른 이유를 말하게 된다.

    Args:
        order: 대상 Order(추가 조회 없이 structured_data 만 읽는다).
        user: 현재 사용자.

    Returns:
        ``(code, message, href)`` 또는 None. ``href`` 는 사용자가 **직접 풀 수 있는**
        사유(quest 미승인·보류·AS 진행)에 채운다 — 막다른 길 0.
    """
    if not can_edit_erp(user):
        return ("NO_PERMISSION", _NO_PERMISSION_MESSAGE, "")

    stage = read_main_stage(order)
    if stage != "CS":
        label = STAGE_LABELS.get(stage or "", stage or "이전")
        return (
            "STAGE_NOT_CS",
            f"아직 {label} 단계라 완료할 수 없습니다. 시공까지 끝내면 CS 단계에서 "
            "완료할 수 있습니다. 주문 상세의 퀘스트 칸에서 다음 단계를 진행하세요.",
            "",
        )

    sd = getattr(order, "structured_data", None)
    sd = sd if isinstance(sd, dict) else {}
    missing = _cs_quest_missing_teams(sd)
    if missing is not None:
        teams = ", ".join(str(team) for team in missing) or "확인 필요"
        return (
            "QUEST_INCOMPLETE",
            f"CS 필수 승인이 남아 완료할 수 없습니다. 남은 팀: {teams}. "
            "대시보드 퀘스트 칸에서 승인하세요.",
            _quest_deeplink(getattr(order, "id", "")),
        )

    order_id = getattr(order, "id", "")
    if read_hold(order) == "HELD":
        return ("HOLD_ACTIVE", "보류 중인 주문은 완료할 수 없습니다. 보류를 먼저 풀어 주세요.",
                _order_deeplink(order_id))

    if read_as_status(order) in OPEN_AS_STATUSES:
        return ("AS_ACTIVE", "진행 중인 AS 가 있어 완료할 수 없습니다. AS 를 먼저 끝내 주세요.",
                _as_deeplink(order_id))

    return None


def rejects_completed_field_write(order: Any, value: Any) -> bool:
    """``update_order_field(status=COMPLETED)`` 를 막아야 하는 주문인가.

    넷을 모두 만족할 때만 True 다. **다른 축 상태 쓰기는 아예 들어오지 않는다** —
    value 가 ``COMPLETED`` 가 아니면 첫 줄에서 끊기므로 SCHEDULED·MEASURED·
    SHIPPED_PENDING·AS_RECEIVED 같은 보드/AS 축 저장은 그대로 지나간다.

    Args:
        order: 대상 Order. value: 요청이 쓰려는 status 값.

    Returns:
        거부 대상이면 True.
    """
    if str(value or "").strip() != "COMPLETED":
        return False
    if not is_erp_order_record(order):
        # 비ERP 레거시 주문은 메인 파이프라인 밖이라 기존 동작을 유지한다.
        return False
    if read_state_axes(order).deleted != "NONE":
        # 삭제 축은 DELETE 소관 — 오탐 금지.
        return False
    stage = read_main_stage(order)
    if stage is None:
        # stage 가 AS_*/미지 = 메인 축 판독 불가 → 기존 동작.
        return False
    if stage == "COMPLETED":
        # 이미 완료 = no-op.
        return False
    return True


def _hidden() -> dict:
    """숨김 항목의 정본 형태(키 7개 고정)."""
    return {
        "visible": False,
        "enabled": False,
        "endpoint": "field_update",
        "label": "",
        "confirm": "",
        "blocked_reason": "",
        "blocked_href": "",
        "blocked_link_label": "",
    }


def _legacy_cta() -> dict:
    """옛 경로를 그대로 쓰는 항목(비ERP·삭제축·stage 판독 불가·이미 완료)."""
    return {
        "visible": True,
        "enabled": True,
        "endpoint": "field_update",
        "label": COMPLETE_LABEL,
        "confirm": COMPLETE_CONFIRM,
        "blocked_reason": "",
        "blocked_href": "",
        "blocked_link_label": "",
    }


def _build_one(order: Any, current_user: Any) -> dict:
    """주문 1건의 완료 CTA. 서버가 실제로 밟는 길과 1:1 순서로 판정한다."""
    if str(getattr(order, "status", "") or "") in TERMINAL_STATUSES:
        return _hidden()

    # field_update 가 막지 않는 행은 화면도 옛 경로 그대로 둔다(잣대 일치).
    if not rejects_completed_field_write(order, "COMPLETED"):
        return _legacy_cta()

    blocked = complete_block_reason(order, current_user)
    endpoint = "cs_complete" if read_main_stage(order) == "CS" else "field_update"
    return {
        "visible": True,
        "enabled": blocked is None,
        "endpoint": endpoint,
        "label": COMPLETE_LABEL,
        "confirm": COMPLETE_CONFIRM,
        "blocked_reason": "" if blocked is None else blocked[1],
        "blocked_href": "" if blocked is None else blocked[2],
        # 링크 문구는 사유마다 다르다(승인/보류/AS) — 화면이 고르지 않고 서버가 준다.
        "blocked_link_label": "" if blocked is None else BLOCKED_LINK_LABELS.get(blocked[0], ""),
    }


def use_cs_complete_response_body(order: Any, user: Any) -> dict:
    """옛 경로(update_order_field·update_order_status)가 돌려줄 409 본문.

    완료 술어와 문구를 이 모듈 한 곳에서만 만들기 위해 라우트 2종이 이 함수를 공유한다.
    막는 사유가 따로 없으면(= cs/complete 로 가면 바로 완료되는 주문) 경로 안내를 준다.

    Args:
        order: 대상 Order. user: 현재 사용자.

    Returns:
        ``{'success', 'code', 'message', 'stage', 'reason_code'}`` dict.
    """
    blocked = complete_block_reason(order, user)
    code, message, _href = blocked if blocked else ("USE_CS_COMPLETE", CS_PATH_MESSAGE, "")
    return {
        "success": False,
        "code": "USE_CS_COMPLETE",
        "message": message,
        "stage": read_main_stage(order),
        "reason_code": code,
    }


def build_complete_ctas(orders, current_user) -> dict:
    """주문 id → 완료 CTA dict(7키 고정).

    모든 주문에 항목이 하나씩 있다(숨김도 항목은 있다). 추가 DB 쿼리는 0회다.

    Args:
        orders: 라우트가 이미 로드한 Order 목록(재조회하지 않는다).
        current_user: 현재 로그인 사용자(없으면 권한 사유로 막힌다).

    Returns:
        ``{order.id: cta dict}``.
    """
    return {order.id: _build_one(order, current_user) for order in (orders or [])}
