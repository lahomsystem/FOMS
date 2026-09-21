"""워크플로 단계 강제 변경(역행·건너뛰기) SSOT.

structured PUT 가드·status API 잠금·override API가 동일 rank/mode를 쓴다.
단계 변경은 status/workflow.stage 만 건드리고 도면·이관 이력은 보존한다.

정책: 이 모듈의 :func:`apply_stage_override` 는 **메인 파이프라인 전용**이다.
AS 3종·DELETED 목표(ADMIN-OVERRIDE-01)는 각자 축 서비스가 처리하며
(:mod:`foms.api.orders.stage_override_targets`), 여기서는 목표 분류에 쓰는 상수·판정
(:data:`OVERRIDE_TARGET_CODES`·:data:`AS_TARGET_TO_AXIS`·:func:`normalize_override_target`)만 둔다.
from 이 AS/레거시면 → 메인으로의 jump 는 운영 복구용으로 허용한다.
"""

from __future__ import annotations

import datetime
from foms.services.datetime_kst import now_utc_naive
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_policy_constants import STAGE_LABELS, STAGE_NAME_TO_CODE
from models import Order, OrderEvent

# 메인 파이프라인만 (AS_*/DELETED/레거시 제외). structured PUT 가드와 동일.
STAGE_FORWARD_RANK: dict[str, int] = {
    "RECEIVED": 0,
    "주문접수": 0,
    "MEASURE": 1,
    "실측": 1,
    "DRAWING": 2,
    "도면": 2,
    "CONFIRM": 3,
    "고객컨펌": 3,
    "PRODUCTION": 4,
    "생산": 4,
    "CONSTRUCTION": 5,
    "시공": 5,
    "CS": 6,
    "COMPLETED": 7,
    "완료": 7,
}

MAIN_PIPELINE_CODES: tuple[str, ...] = (
    "RECEIVED",
    "MEASURE",
    "DRAWING",
    "CONFIRM",
    "PRODUCTION",
    "CONSTRUCTION",
    "CS",
    "COMPLETED",
)

#: 강제 변경이 갈 수 있는 목표 전부(ADMIN-OVERRIDE-01). 메인 8단계는 기존 그대로이고,
#: AS 3종·DELETED 는 **ADMIN + admin_override** 가 있어야 하며 raw stage 쓰기가 아니라
#: 각 축 서비스(as_cycle_service·trash_mirror)를 태운다.
OVERRIDE_TARGET_CODES: tuple[str, ...] = MAIN_PIPELINE_CODES + (
    "AS_RECEIVED",
    "AS",
    "AS_COMPLETED",
    "DELETED",
)

#: 강제 변경 목표 코드 → AS 축(state_axes.read_as_status) 값.
AS_TARGET_TO_AXIS: dict[str, str] = {
    "AS_RECEIVED": "RECEIVED",
    "AS": "IN_PROGRESS",
    "AS_COMPLETED": "COMPLETED",
}

OVERRIDE_ALLOWED_ROLES: frozenset[str] = frozenset({"ADMIN", "MANAGER"})
OVERRIDE_BLOCK_MESSAGE = (
    "단계 역행/건너뛰기는 「단계 강제 변경」에서 사유·확인 후 진행하세요."
)

#: AS overlay 상태 집합. AS 대시보드(미완료/완료 탭)는 이 status 로만 주문을 찾으므로,
#: 메인 파이프라인 코드(COMPLETED 등)로 덮어쓰면 AS 접수·기록이 살아 있어도 목록에서
#: 사라진다(2026-08-14 운영 사고: 일괄 완료처리 55건이 AS 대시보드에서 증발).
AS_OVERLAY_STATUSES: frozenset[str] = frozenset({"AS", "AS_RECEIVED", "AS_COMPLETED"})

AS_OVERLAY_BLOCK_MESSAGE = (
    "AS 접수/완료 상태 주문은 일괄 변경에서 제외했습니다. "
    "AS 대시보드에서 사라지므로 정말 바꾸려면 주문별로 진행하세요."
)


def as_overlay_status(order: Order) -> str:
    """주문이 AS overlay 상태면 그 status 코드, 아니면 빈 문자열.

    ``workflow.stage`` 가 아니라 **``order.status``** 를 본다 — AS 접수된 주문의
    workflow.stage 는 MEASURE 등 메인 코드로 남아 있어(두 축 분리) stage 만 보면
    AS overlay 를 놓친다.

    Args:
        order: 대상 주문(ORM 또는 status 속성을 가진 객체).

    Returns:
        ``'AS'``/``'AS_RECEIVED'``/``'AS_COMPLETED'`` 중 하나, 아니면 ``''``.
    """
    status = str(getattr(order, "status", None) or "").strip()
    return status if status in AS_OVERLAY_STATUSES else ""


def stage_forward_rank(raw: Any) -> int:
    """workflow.stage / status 전방 순위. 메인 파이프라인 외·미지 = -1."""
    text = str(raw or "").strip()
    if not text:
        return -1
    if text in STAGE_FORWARD_RANK:
        return STAGE_FORWARD_RANK[text]
    mapped = STAGE_NAME_TO_CODE.get(text)
    if mapped and mapped in STAGE_FORWARD_RANK:
        return STAGE_FORWARD_RANK[mapped]
    if text in STAGE_LABELS and text in STAGE_FORWARD_RANK:
        return STAGE_FORWARD_RANK[text]
    return -1


def normalize_main_stage(raw: Any) -> Optional[str]:
    """메인 파이프라인 코드로 정규화. 불가하면 None."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text in MAIN_PIPELINE_CODES:
        return text
    mapped = STAGE_NAME_TO_CODE.get(text)
    if mapped in MAIN_PIPELINE_CODES:
        return mapped
    if text in STAGE_FORWARD_RANK:
        # 한글 라벨 키 → 코드
        for code in MAIN_PIPELINE_CODES:
            if STAGE_FORWARD_RANK.get(code) == STAGE_FORWARD_RANK[text]:
                return code
    return None


def normalize_override_target(raw: Any) -> Optional[str]:
    """강제 변경 목표를 :data:`OVERRIDE_TARGET_CODES` 코드로 정규화한다. 불가하면 None.

    AS 3종·DELETED 는 대문자 코드 그대로만 받고(한글 별칭 없음), 메인 8단계는 기존
    :func:`normalize_main_stage` 가 한글 라벨까지 받아 준다.

    Args:
        raw: 요청의 ``to_stage`` 원값.

    Returns:
        목표 코드, 알 수 없으면 None.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper in AS_TARGET_TO_AXIS or upper == "DELETED":
        return upper
    return normalize_main_stage(text)


def classify_stage_move(from_stage: Any, to_stage: Any) -> str:
    """이동 모드: same | advance | regress | skip | jump."""
    from_code = normalize_main_stage(from_stage)
    to_code = normalize_main_stage(to_stage)
    if from_code and to_code and from_code == to_code:
        return "same"
    from_rank = stage_forward_rank(from_stage if from_code is None else from_code)
    to_rank = stage_forward_rank(to_stage if to_code is None else to_code)
    if from_rank < 0 or to_rank < 0:
        return "jump"
    if to_rank < from_rank:
        return "regress"
    if to_rank == from_rank + 1:
        return "advance"
    if to_rank > from_rank + 1:
        return "skip"
    return "same"


def requires_privileged_override(from_stage: Any, to_stage: Any) -> bool:
    """ERP 메인 파이프라인끼리 역행·비인접 전진이면 True.

    한쪽이라도 메인 파이프라인 밖(AS_*/레거시)이면 False — 기존 status API 유지.
    """
    from_code = normalize_main_stage(from_stage)
    to_code = normalize_main_stage(to_stage)
    if from_code is None or to_code is None:
        return False
    mode = classify_stage_move(from_code, to_code)
    return mode in ("regress", "skip", "jump")


def current_stage_for_order(order: Order) -> str:
    """ERP면 workflow.stage 우선, 없으면 order.status."""
    status = str(getattr(order, "status", None) or "").strip()
    if not is_erp_order_record(order):
        return status
    sd = getattr(order, "structured_data", None)
    if isinstance(sd, dict):
        wf = sd.get("workflow")
        if isinstance(wf, dict):
            stage = str(wf.get("stage") or "").strip()
            if stage:
                return stage
    return status


def structured_measurement_date(sd: Any) -> str:
    """``schedule.measurement.date`` 원문을 공백 제거해 반환한다(없으면 빈 문자열).

    Args:
        sd: 대상 structured_data(딕셔너리가 아니면 빈 문자열).

    Returns:
        실측일 문자열, 없으면 ``''``.
    """
    if not isinstance(sd, dict):
        return ""
    schedule = sd.get("schedule")
    measurement = schedule.get("measurement") if isinstance(schedule, dict) else None
    if not isinstance(measurement, dict):
        return ""
    return str(measurement.get("date") or "").strip()


def override_pins_stage(sd: Any, stage: str) -> bool:
    """명시적 override 가 지금 단계를 고정하고 있는지 판정한다.

    ``apply_stage_override`` 가 남긴 ``workflow.stage_override`` 표식이
    (1) 지금 단계와 같은 단계를 가리키고 (2) 그때의 실측일 상황이 지금과 같을 때만 참이다.
    단계가 그 뒤로 움직였거나 실측일이 바뀌었으면 표식은 무효다(자동 동기화 재개).

    Args:
        sd: 대상 structured_data.
        stage: 지금 단계 코드(정규화된 메인 파이프라인 코드).

    Returns:
        자동 단계 동기화를 건너뛰어야 하면 True.
    """
    if not isinstance(sd, dict):
        return False
    workflow = sd.get("workflow")
    marker = workflow.get("stage_override") if isinstance(workflow, dict) else None
    if not isinstance(marker, dict):
        return False
    if normalize_main_stage(marker.get("stage")) != normalize_main_stage(stage):
        return False
    return str(marker.get("measurement_date") or "").strip() == structured_measurement_date(sd)


def _reopen_completed_stage_quest(
    sd: dict[str, Any], to_code: str, from_code: str, reason: str, at: str
) -> Optional[str]:
    """되돌아간 단계의 COMPLETED quest 1건을 다시 OPEN 으로 돌린다(regress 전용).

    quest 를 그대로 두면 화면은 완료 배지만 그리고 승인 버튼이 없어 막다른 길이 된다
    (2026-09-20 스테이징 #4382). quest.stage 는 코드('MEASURE')와 한글 라벨('실측') 두 가지로
    저장돼 있어 둘 다 별칭으로 본다. 같은 단계 COMPLETED 가 여럿이면 표시 SSOT
    (erp_quest_display) 와 같은 정렬 키로 가장 최근 1건만 되돌린다.

    ``sd`` 는 셸 복사본이라 ``sd["quests"]`` 는 ORM 원본 리스트를 가리킨다 — 원본 리스트·원본
    quest dict 를 제자리에서 바꾸지 않고 새 리스트·새 dict 를 만들어 재대입한다.

    :param sd: 셸 복사된 structured_data(호출자가 ``dict(sd)`` 로 만든 것).
    :param to_code: 되돌아간 단계 코드.
    :param from_code: 떠나온 단계 코드(흔적으로 남긴다).
    :param reason: 강제 변경 사유.
    :param at: 단계 변경 시각(isoformat).
    :returns: 되돌린 quest 의 단계 코드(``to_code``). 되돌린 게 없으면 None.
    """
    aliases = {to_code, STAGE_LABELS.get(to_code, "")} - {""}
    quests = list(sd.get("quests") or [])
    candidates = [
        (i, q) for i, q in enumerate(quests)
        if isinstance(q, dict) and q.get("stage") in aliases
        and str(q.get("status") or "").upper() == "COMPLETED"
    ]
    if not candidates:
        return None
    index, quest = max(
        candidates,
        key=lambda item: str(
            item[1].get("completed_at") or item[1].get("updated_at")
            or item[1].get("created_at") or "1970-01-01T00:00:00"
        ),
    )
    new_quest = {k: v for k, v in quest.items() if k != "completed_at"}
    new_quest.update(
        status="OPEN",
        assignee_approval={},
        team_approvals={},
        updated_at=at,
        reopened_by_override={"at": at, "from_stage": from_code, "reason": reason},
    )
    quests[index] = new_quest
    sd["quests"] = quests
    return to_code


def apply_stage_override(
    *,
    order: Order,
    to_stage: str,
    reason: str,
    user_id: Any,
    db: Any,
) -> dict[str, Any]:
    """status + workflow.stage 만 변경하고 STAGE_OVERRIDE 이벤트를 남긴다.

    _handle_stage_transition 부수효과는 호출하지 않는다. 단, regress 는 되돌아간 단계의
    COMPLETED quest 1건을 OPEN 으로 돌린다(:func:`_reopen_completed_stage_quest`) — 그대로 두면
    승인 버튼 없는 완료 배지만 남아 막다른 길이 된다. advance/skip/jump 는 quest 를 건드리지 않는다.
    drawing_transfer_history 등 운영 JSON은 건드리지 않는다.

    :returns: {from, to, mode, reason, from_status[, as_overlay_cleared][, quest_reopened]}
    :raises ValueError: 검증 실패(메시지 한글)
    """
    to_code = normalize_main_stage(to_stage)
    if to_code is None or to_code not in MAIN_PIPELINE_CODES:
        raise ValueError(
            "메인 파이프라인 단계만 강제 변경할 수 있습니다. "
            "(AS·삭제는 관리자 권한이 필요합니다.)"
        )

    reason_clean = str(reason or "").strip()
    if not reason_clean:
        raise ValueError("사유를 입력하세요.")

    from_raw = current_stage_for_order(order)
    from_code = normalize_main_stage(from_raw) or str(from_raw or "").strip()
    mode = classify_stage_move(from_code, to_code)
    if mode == "same":
        raise ValueError("현재와 동일한 단계로는 변경할 수 없습니다.")

    # 덮어쓰기 전 **실제 status** 를 잡아 payload 에 싣는다. from(=workflow.stage) 만
    # 남기면 AS overlay(AS_RECEIVED 등)가 흔적 없이 사라져 사고 후 복구 근거가 없다
    # (2026-08-14: payload from 이 MEASURE 라 AS 상태를 이벤트로 되짚을 수 없었다).
    status_before = str(getattr(order, "status", None) or "").strip()
    overlay_cleared = as_overlay_status(order)
    quest_reopened: Optional[str] = None

    order.status = to_code

    if is_erp_order_record(order):
        sd = getattr(order, "structured_data", None)
        if not isinstance(sd, dict):
            sd = {}
        else:
            # 셸 복사 — 중첩 리스트(이력)는 같은 참조 유지(리셋 금지)
            sd = dict(sd)
        wf_raw = sd.get("workflow")
        workflow = dict(wf_raw) if isinstance(wf_raw, dict) else {}
        stage_changed_at = now_utc_naive().isoformat()
        workflow["stage"] = to_code
        workflow["stage_updated_at"] = stage_changed_at
        # 명시적 override 는 이후 폼 저장의 실측일 자동 전진(RECEIVED→MEASURE)이 되돌리지
        # 못하게 표식을 남긴다. 자동 전진은 "실측일이 있으면"이라는 상태 조건이라 저장할
        # 때마다 다시 성립해, 표식이 없으면 사용자가 건 역행이 매 저장마다 취소됐다.
        workflow["stage_override"] = {
            "at": stage_changed_at,
            "stage": to_code,
            "measurement_date": structured_measurement_date(sd),
        }
        if mode == "regress":
            quest_reopened = _reopen_completed_stage_quest(
                sd, to_code, from_code, reason_clean, stage_changed_at
            )
        sd["workflow"] = workflow
        order.structured_data = sd
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)

    payload = {
        "from": from_code,
        "to": to_code,
        "mode": mode,
        "reason": reason_clean,
        "manual": True,
        "from_status": status_before,
    }
    if overlay_cleared:
        payload["as_overlay_cleared"] = overlay_cleared
    if quest_reopened:
        payload["quest_reopened"] = quest_reopened
    db.add(
        OrderEvent(
            order_id=order.id,
            event_type="STAGE_OVERRIDE",
            payload=payload,
            created_by_user_id=user_id,
        )
    )
    return payload


__all__ = [
    "AS_OVERLAY_BLOCK_MESSAGE",
    "AS_OVERLAY_STATUSES",
    "AS_TARGET_TO_AXIS",
    "MAIN_PIPELINE_CODES",
    "OVERRIDE_TARGET_CODES",
    "normalize_override_target",
    "OVERRIDE_ALLOWED_ROLES",
    "OVERRIDE_BLOCK_MESSAGE",
    "override_pins_stage",
    "structured_measurement_date",
    "STAGE_FORWARD_RANK",
    "apply_stage_override",
    "as_overlay_status",
    "classify_stage_move",
    "current_stage_for_order",
    "normalize_main_stage",
    "requires_privileged_override",
    "stage_forward_rank",
]
