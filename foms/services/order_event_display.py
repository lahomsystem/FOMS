"""Order event display SSOT — Korean labels for timeline and change logs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_policy import STAGE_LABELS, STAGE_NAME_TO_CODE

__all__ = [
    "TEAM_LABELS",
    "translate_target_to_korean",
    "translate_event_type_to_korean",
    "translate_reason_to_korean",
    "translate_value_to_korean",
    "translate_stage_code",
    "translate_payload_field",
    "generate_change_description",
    "format_timeline_meta",
    "format_timeline_description",
]

TEAM_LABELS: dict[str, str] = {
    "CS": "상담팀",
    "SALES": "영업팀",
    "MEASURE": "실측팀",
    "DRAWING": "도면팀",
    "PRODUCTION": "생산팀",
    "CONSTRUCTION": "시공팀",
    "SHIPMENT": "출고팀",
}

_STAGE_EVENT_TYPES = frozenset(
    {"STAGE_CHANGED", "STAGE_AUTO_TRANSITIONED", "STAGE_MANUAL_OVERRIDE"}
)

_EMPTY_DISPLAY_VALUES = frozenset({"", "none", "null"})

_DRAWING_STATUS_MAP: dict[str, str] = {
    # ERP uppercase codes (payload / structured_data)
    "PENDING": "작업중",
    "WAITING": "대기",
    "IN_PROGRESS": "진행중",
    "TRANSFERRED": "확정 대기",
    "RETURNED": "수정 요청됨",
    "CONFIRMED": "완료",
    "DONE": "완료",
    # Legacy lowercase codes
    "pending": "대기중",
    "sent": "전달됨",
    "confirmed": "확인완료",
    "revision_requested": "수정요청",
}

_APPROVAL_STATUS_MAP: dict[str, str] = {
    "not_approved": "미승인",
    "approved": "승인됨",
    "pending": "대기중",
    "rejected": "반려됨",
}

_APPROVAL_EVENT_TYPES = frozenset({"QUEST_APPROVAL_CHANGED", "QUEST_ASSIGNEE_APPROVED"})
_ASSIGNEE_EVENT_TYPES = frozenset({"DRAWING_ASSIGNEE_SET", "ASSIGNMENT_CHANGED", "manager_changed"})


def _is_empty_display_value(value: Any) -> bool:
    """True when value is None, blank, or a string sentinel like 'None'."""
    if value in (None, ""):
        return True
    return str(value).strip().lower() in _EMPTY_DISPLAY_VALUES


def _lookup_status_map(value: Any, mapping: dict[str, str]) -> str:
    """Case-insensitive lookup for coded status strings."""
    text = str(value).strip()
    if not text:
        return ""
    return (
        mapping.get(text)
        or mapping.get(text.upper())
        or mapping.get(text.lower())
        or text
    )


def _translate_drawing_status(value: Any) -> str:
    """Drawing status code → Korean label (aligned with erp_display._drawing_status_label)."""
    return _lookup_status_map(value, _DRAWING_STATUS_MAP)


def _translate_approval_status(value: Any) -> str:
    """Quest approval code → Korean label."""
    if isinstance(value, bool):
        return "승인됨" if value else "미승인"
    if isinstance(value, dict):
        if value.get("approved"):
            return f"승인됨 ({value.get('approved_by_name', '담당자')})"
        return "미승인"
    return _lookup_status_map(value, _APPROVAL_STATUS_MAP)


def _empty_transition_label(event_type: str) -> str:
    """Label for null/empty before or after in timeline transitions."""
    return "없음"


def translate_target_to_korean(target: str) -> str:
    """영어 타겟을 한글로 변환."""
    target_map = {
        "workflow.stage": "진행 단계",
        "workflow.current_quest": "현재 퀘스트",
        "quests": "퀘스트",
        "quest.team_approvals": "팀 승인",
        "quest.assignee_approval": "담당자 승인",
        "assignments.drawing_assignee_user_ids": "도면 담당자",
        "drawings.status": "도면 상태",
        "production.completed": "생산 완료",
        "construction.completed": "시공 완료",
        "cs.completed": "CS 완료",
        "as.status": "AS 상태",
    }
    return target_map.get(target, target)


def translate_event_type_to_korean(event_type: str | None) -> str:
    """이벤트 타입 영문 코드를 한글 라벨로 변환."""
    labels = {
        "QUEST_APPROVAL_CHANGED": "퀘스트 승인",
        "QUEST_ASSIGNEE_APPROVED": "담당자 승인",
        "QUEST_CREATED": "퀘스트 생성",
        "QUEST_UPDATED": "퀘스트 수정",
        "QUEST_COMPLETED": "퀘스트 완료",
        "STAGE_CHANGED": "단계 변경",
        "STAGE_AUTO_TRANSITIONED": "단계 자동 전환",
        "STAGE_MANUAL_OVERRIDE": "단계 수동 변경",
        "DRAWING_STATUS_CHANGED": "도면 상태 변경",
        "DRAWING_ASSIGNEE_SET": "도면 담당자 지정",
        "DRAWING_SENT": "도면 전달",
        "DRAWING_CONFIRMED": "도면 확인",
        "DRAWING_REVISION_REQUESTED": "도면 수정 요청",
        "PRODUCTION_STARTED": "생산 시작",
        "PRODUCTION_COMPLETED": "생산 완료",
        "PRODUCTION_DELAYED": "생산 지연",
        "CONSTRUCTION_STARTED": "시공 시작",
        "CONSTRUCTION_COMPLETED": "시공 완료",
        "CONSTRUCTION_SCHEDULED": "시공 예약",
        "CS_STARTED": "CS 시작",
        "CS_COMPLETED": "CS 완료",
        "CS_ISSUE_REPORTED": "CS 이슈 보고",
        "AS_STARTED": "AS 시작",
        "AS_COMPLETED": "AS 완료",
        "AS_RECEIVED": "AS 접수",
        "MEASUREMENT_SCHEDULED": "실측 예약",
        "MEASUREMENT_COMPLETED": "실측 완료",
        "MEASUREMENT_DATE_CHANGED": "실측 일정 변경",
        "MEASUREMENT_TIME_CHANGED": "실측 시간 변경",
        "CONSTRUCTION_DATE_CHANGED": "시공 일정 변경",
        "OWNER_TEAM_CHANGED": "담당팀 변경",
        "AS_RECOMMENDATION_APPLIED": "AS 권고 적용",
        "AS_RECOMMENDATION_CANCELLED": "AS 권고 취소",
        "SETTLEMENT_ISSUE_RAISED": "정산 이슈 등록",
        "SHIPMENT_SCHEDULED": "출고 예정",
        "SHIPMENT_COMPLETED": "출고 완료",
        "CHANGE_REVERTED": "변경 되돌림",
        "ORDER_CREATED": "주문 생성",
        "ORDER_DRAFT_CREATED": "임시 주문 생성",
        "ORDER_UPDATED": "주문 수정",
        "ORDER_DELETED": "주문 삭제",
        "ASSIGNMENT_CHANGED": "담당자 변경",
        "STATUS_CHANGED": "상태 변경",
        "FIELD_UPDATED": "필드 수정",
        "ALIMTALK_SENT": "알림톡 발송",
        "ALIMTALK_FAILED": "알림톡 실패",
        "COMMENT_ADDED": "메모 추가",
        "ATTACHMENT_ADDED": "첨부파일 추가",
        "ATTACHMENT_DELETED": "첨부파일 삭제",
        "ATTACHMENT_META_UPDATED": "첨부파일 정보 수정",
        "ATTACHMENT_RESTORED": "첨부파일 복구",
        "URGENT_CHANGED": "긴급 여부 변경",
        "PAYMENT_CHANGED": "금액 변경",
        # 네이버 수집분 붙이기·되돌리기 (스펙 2026-08-24 R3 = 08-19 §7 Q3 안 B).
        # 여기서 빼면 화면에 영문 코드가 아니라 아래 기본값 "기타 변경"이 뜬다 — 조용히
        # 다른 미등재 이벤트와 섞여 구분이 안 되므로 타입 추가 시 반드시 함께 등재한다.
        "NAVER_ORDER_ATTACHED": "네이버 수집분 연결",
        "NAVER_ORDER_DETACHED": "네이버 수집분 연결 해제",
        # 반품 거부(T8-S3). 워크벤치를 안 여는 담당자가 나중에 맥락을 읽는 자리다 —
        # 왜 이 주문의 반품이 안 받아들여졌는지는 주문 이력에만 남는다.
        "NAVER_RETURN_REJECTED": "네이버 반품 거부",
        # 승인 2종(T9). 거부만 이력에 남고 **환불은 안 남는 장부**가 되지 않게 함께 등재한다
        # — 돈이 나간 사실이 워크벤치 밖에서 읽히지 않으면 나중에 아무도 설명을 못 한다.
        "NAVER_CANCEL_APPROVED": "네이버 취소 승인",
        "NAVER_RETURN_APPROVED": "네이버 반품 승인",
        "manager_changed": "담당자 변경",
        "order_updated": "주문 수정",
    }
    key = (event_type or "").strip()
    return labels.get(key, "기타 변경")


def translate_reason_to_korean(
    reason: str,
    event_type: str = "",
    payload: dict[str, Any] | None = None,
) -> str:
    """시스템 reason 코드를 사람이 이해하기 쉬운 한글로 변환."""
    payload = payload or {}
    raw = str(reason or "").strip()
    if not raw:
        raw = str(payload.get("override_reason") or "").strip()
    if not raw and event_type == "STAGE_AUTO_TRANSITIONED":
        raw = "quest_approvals_complete"

    if not raw:
        return ""

    reason_map = {
        "quest_approvals_complete": "퀘스트 승인 조건이 충족되어 자동 전환되었습니다.",
        "all_approvals_complete": "모든 승인 조건이 충족되었습니다.",
        "auto_transition_rule_matched": "자동 단계 전환 규칙에 따라 처리되었습니다.",
        "manager_override": "관리자 권한으로 예외 처리되었습니다.",
        "emergency_override": "긴급 권한으로 예외 처리되었습니다.",
        "manual_update": "담당자가 수동으로 변경했습니다.",
    }
    if raw in reason_map:
        return reason_map[raw]

    if "_" in raw and raw.islower():
        return raw.replace("_", " ")
    return raw


def translate_stage_code(value: Any) -> str:
    """Stage code or Korean stage name → display label via STAGE_LABELS."""
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    code = STAGE_NAME_TO_CODE.get(text, text)
    return STAGE_LABELS.get(code, text)


def translate_payload_field(event_type: str, field: str, value: Any) -> str:
    """Translate a timeline payload field (to/from/before/after) for display."""
    if _is_empty_display_value(value):
        if event_type in _ASSIGNEE_EVENT_TYPES or event_type in _APPROVAL_EVENT_TYPES:
            return _empty_transition_label(event_type)
        return ""

    if event_type in _STAGE_EVENT_TYPES and field in ("to", "from", "before", "after"):
        return translate_stage_code(value)

    if event_type == "OWNER_TEAM_CHANGED" and field in ("to", "from"):
        team_key = str(value).strip()
        return TEAM_LABELS.get(team_key, team_key)

    if event_type == "URGENT_CHANGED" and field in ("to", "from"):
        if isinstance(value, bool):
            return "긴급" if value else "일반"
        lowered = str(value).strip().lower()
        if lowered in ("true", "1", "yes"):
            return "긴급"
        if lowered in ("false", "0", "no"):
            return "일반"

    if event_type in _APPROVAL_EVENT_TYPES and field in ("to", "from", "before", "after"):
        return _translate_approval_status(value)

    if event_type in _ASSIGNEE_EVENT_TYPES and field in ("to", "from", "before", "after"):
        return str(value).strip()

    if event_type == "DRAWING_STATUS_CHANGED" and field in ("to", "from", "before", "after"):
        return _translate_drawing_status(value)

    if event_type in ("MEASUREMENT_DATE_CHANGED", "CONSTRUCTION_DATE_CHANGED"):
        return str(value).strip()

    return str(value).strip()


def translate_value_to_korean(target: str, value: Any) -> str:
    """값을 한글로 변환."""
    if _is_empty_display_value(value):
        return "없음"

    if isinstance(value, bool):
        return "완료" if value else "미완료"

    target_lower = target.lower()

    if "stage" in target_lower:
        return translate_stage_code(value)

    if "approval" in target_lower:
        return _translate_approval_status(value)

    if "assignee" in target_lower:
        return str(value).strip()

    if "drawing" in target_lower and "status" in target_lower:
        return _translate_drawing_status(value)

    return str(value)


def _describe_naver_link_change(event_type: str, payload: dict[str, Any]) -> str:
    """네이버 수집분 연결·해제를 "무엇이 얼마" 문장으로 만든다 (스펙 2026-08-24 R3).

    08-19 §3.3 이 약속한 문장이다. 없으면 변경 로그 행이 기본값 "변경 이력"으로 떨어져
    무엇이 붙었는지 사람이 알 수 없다.

    Args:
        event_type: ``NAVER_ORDER_ATTACHED`` 또는 ``NAVER_ORDER_DETACHED``.
        payload: 이벤트 payload(``relation``·``external_order_no``·
            ``product_order_count``·``amount_total``).

    Returns:
        사람이 읽는 한 문장.
    """
    relation = str(payload.get("relation") or "").strip()
    relation_kr = {"ADDON": "추가결제", "REPAY": "재결제"}.get(relation, "수집분")
    order_no = str(payload.get("external_order_no") or "").strip()
    try:
        count = int(payload.get("product_order_count") or 0)
        amount = int(payload.get("amount_total") or 0)
    except (TypeError, ValueError):
        count, amount = 0, 0
    head = f"네이버 {relation_kr}"
    if order_no:
        head = f"{head} 주문 {order_no}"
    tail = ("을 이 주문에 연결했습니다" if event_type == "NAVER_ORDER_ATTACHED"
            else "의 연결을 해제했습니다")
    return f"{head} {count}건 · {amount:,}원{tail}"


def _describe_naver_return_reject(payload: dict[str, Any]) -> str:
    """반품 거부를 "몇 건에 무슨 말을 보냈나" 문장으로 만든다 (T8-S3).

    **보낸 문장을 그대로 싣는다.** 요약하면 이 줄이 쓸모를 잃는다 — 나중에 분쟁이 오면
    필요한 것은 "거부했다"가 아니라 **구매자가 받은 그 문장**이다.

    Args:
        payload: 이벤트 payload(``reason``·``external_order_no``·``product_order_count``).

    Returns:
        사람이 읽는 한 문장.
    """
    order_no = str(payload.get("external_order_no") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    try:
        count = int(payload.get("product_order_count") or 0)
    except (TypeError, ValueError):
        count = 0
    head = "네이버 반품 요청을 거부했습니다"
    if order_no:
        head = f"네이버 주문 {order_no} 의 반품 요청을 거부했습니다"
    if count:
        head = f"{head} ({count}건)"
    return f"{head} — 보낸 문장: “{reason}”" if reason else head


def _describe_naver_claim_approve(event_type: str, payload: dict[str, Any]) -> str:
    """취소·반품 **승인**을 "몇 건에 얼마가 환불됐나" 문장으로 만든다 (T9).

    거부(:func:`_describe_naver_return_reject`)와 짝이다. 거부는 보낸 **문장**이 핵심이고
    승인은 **돈이 나갔다**는 사실이 핵심이라, 싣는 값이 다르다 — 승인에는 구매자에게 가는
    문장 자체가 없다(네이버 규격이 본문을 받지 않는다).

    Args:
        event_type: ``NAVER_CANCEL_APPROVED`` 또는 ``NAVER_RETURN_APPROVED``.
        payload: 이벤트 payload(``external_order_no``·``product_order_count``).

    Returns:
        사람이 읽는 한 문장.
    """
    kind = "취소" if event_type == "NAVER_CANCEL_APPROVED" else "반품"
    order_no = str(payload.get("external_order_no") or "").strip()
    try:
        count = int(payload.get("product_order_count") or 0)
    except (TypeError, ValueError):
        count = 0
    head = f"네이버 {kind} 요청을 승인했습니다"
    if order_no:
        head = f"네이버 주문 {order_no} 의 {kind} 요청을 승인했습니다"
    if count:
        head = f"{head} ({count}건)"
    return f"{head} — 환불이 확정됩니다"


def generate_change_description(
    event_type: str,
    target_kr: str,
    before_kr: str,
    after_kr: str,
    payload: dict[str, Any] | None,
) -> str:
    """이벤트 타입에 따라 이해하기 쉬운 설명 생성."""
    payload = payload or {}

    if event_type == "QUEST_APPROVAL_CHANGED":
        team = payload.get("team", "")
        team_kr = TEAM_LABELS.get(team, team)
        return f"{team_kr}이 퀘스트를 승인했습니다"

    if event_type == "QUEST_ASSIGNEE_APPROVED":
        approved_by = payload.get("approved_by_name", "담당자")
        quest_title = payload.get("quest_title", "")
        return f"{approved_by}님이 '{quest_title}' 퀘스트를 승인했습니다"

    if event_type == "STAGE_CHANGED":
        return f"진행 단계를 '{before_kr}'에서 '{after_kr}'로 변경했습니다"

    if event_type == "STAGE_AUTO_TRANSITIONED":
        return f"퀘스트 완료로 인해 단계가 '{before_kr}'에서 '{after_kr}'로 자동 전환되었습니다"

    if event_type == "DRAWING_ASSIGNEE_SET":
        assignees = payload.get("assignee_names", [])
        if not assignees:
            after_raw = payload.get("after")
            if isinstance(after_raw, str):
                assignees = [
                    x.strip()
                    for x in after_raw.split(",")
                    if x.strip() and x.strip().lower() != "none"
                ]
        if assignees:
            return f"도면 담당자를 {', '.join(assignees)}님으로 지정했습니다"
        return "도면 담당자를 지정했습니다"

    if event_type == "DRAWING_STATUS_CHANGED":
        return f"도면 상태를 '{before_kr}'에서 '{after_kr}'로 변경했습니다"

    if event_type == "PRODUCTION_COMPLETED":
        return "생산을 완료 처리했습니다"
    if event_type == "PRODUCTION_STARTED":
        return "생산을 시작했습니다"
    if event_type == "CONSTRUCTION_COMPLETED":
        return "시공을 완료 처리했습니다"
    if event_type == "CONSTRUCTION_STARTED":
        return "시공을 시작했습니다"
    if event_type == "CS_COMPLETED":
        return "CS를 완료 처리했습니다"
    if event_type == "CS_STARTED":
        return "CS를 시작했습니다"
    if event_type == "AS_STARTED":
        return "AS를 시작했습니다"
    if event_type == "AS_COMPLETED":
        return "AS를 완료 처리했습니다"
    if event_type == "AS_RECEIVED":
        return "AS를 접수했습니다"
    if event_type == "MEASUREMENT_SCHEDULED":
        return "실측 일정을 등록했습니다"
    if event_type == "MEASUREMENT_COMPLETED":
        return "실측을 완료했습니다"
    if event_type == "MEASUREMENT_DATE_CHANGED":
        return "실측 일정을 변경했습니다"
    if event_type == "CONSTRUCTION_DATE_CHANGED":
        return "시공 일정을 변경했습니다"
    if event_type == "OWNER_TEAM_CHANGED":
        to_team = translate_payload_field(event_type, "to", payload.get("to"))
        return f"담당팀을 '{to_team}'(으)로 변경했습니다" if to_team else "담당팀을 변경했습니다"
    if event_type == "SETTLEMENT_ISSUE_RAISED":
        return "정산 이슈를 등록했습니다"
    if event_type == "AS_RECOMMENDATION_APPLIED":
        return "AS 권고를 적용했습니다"
    if event_type == "AS_RECOMMENDATION_CANCELLED":
        return "AS 권고를 취소했습니다"
    if event_type == "SHIPMENT_SCHEDULED":
        return "출고 일정을 등록했습니다"
    if event_type == "SHIPMENT_COMPLETED":
        return "출고를 완료했습니다"

    if event_type in ("NAVER_ORDER_ATTACHED", "NAVER_ORDER_DETACHED"):
        return _describe_naver_link_change(event_type, payload)

    if event_type == "NAVER_RETURN_REJECTED":
        return _describe_naver_return_reject(payload)

    if event_type in ("NAVER_CANCEL_APPROVED", "NAVER_RETURN_APPROVED"):
        return _describe_naver_claim_approve(event_type, payload)

    if event_type == "CHANGE_REVERTED":
        return f"이전 변경사항을 되돌렸습니다 ({translate_target_to_korean(payload.get('target', ''))})"

    if event_type == "ORDER_CREATED":
        return "주문을 생성했습니다"
    if event_type == "ORDER_DRAFT_CREATED":
        return "임시 주문(초안)을 생성했습니다"
    if event_type in ("ORDER_UPDATED", "order_updated"):
        return "주문 정보를 수정했습니다"
    if event_type == "ORDER_DELETED":
        return "주문을 삭제했습니다"
    if event_type in ("ASSIGNMENT_CHANGED", "manager_changed"):
        return "담당자를 변경했습니다"
    if event_type == "URGENT_CHANGED":
        return "긴급 여부를 변경했습니다"

    if target_kr and before_kr and after_kr:
        return f"{target_kr}를 '{before_kr}'에서 '{after_kr}'로 변경했습니다"
    if target_kr:
        return f"{target_kr} 변경"
    return "변경 이력"


def _resolve_payload_transition(
    event_type: str,
    payload: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Extract from/to (or before/after) with Korean labels when applicable."""
    from_key = "from" if "from" in payload else "before"
    to_key = "to" if "to" in payload else "after"
    from_present = from_key in payload
    to_present = to_key in payload
    from_raw = payload.get(from_key)
    to_raw = payload.get(to_key)

    if not from_present:
        from_label: str | None = None
    elif _is_empty_display_value(from_raw):
        from_label = _empty_transition_label(event_type)
    else:
        from_label = translate_payload_field(event_type, from_key, from_raw) or None

    if not to_present:
        to_label: str | None = None
    elif _is_empty_display_value(to_raw):
        to_label = _empty_transition_label(event_type)
    else:
        to_label = translate_payload_field(event_type, to_key, to_raw) or None

    return from_label, to_label


def format_timeline_meta(
    event_type: str,
    payload: dict[str, Any],
    *,
    actor_name: str | None = None,
    created_at: datetime | None = None,
) -> str:
    """Human-readable meta line for mobile/WAM timeline rows."""
    parts: list[str] = []
    if actor_name:
        parts.append(actor_name)
    if created_at:
        parts.append(format_datetime_kst(created_at, "%Y-%m-%d %H:%M"))

    from_label, to_label = _resolve_payload_transition(event_type, payload)
    if from_label and to_label:
        parts.append(f"{from_label} → {to_label}")
    elif to_label:
        parts.append(to_label)
    elif from_label:
        parts.append(from_label)

    return " · ".join(p for p in parts if p)


def format_timeline_description(event_type: str, payload: dict[str, Any]) -> str:
    """WAM-style from → to description with Korean field values."""
    from_label, to_label = _resolve_payload_transition(event_type, payload)
    if from_label or to_label:
        left = from_label or "-"
        right = to_label or "-"
        return f"{left} -> {right}"

    for key in ("message", "summary", "reason", "status", "value"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return translate_event_type_to_korean(event_type)
