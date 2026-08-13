"""주문 변경 사유 (ORDER-REASON-00).

변경 기록 체인(ORDER-DIFF-00/01/02)은 "무엇이 어떻게 바뀌었나"까지 답한다. 남은 공백이
**"왜"** 다 — 금액·일정 분쟁에서 "고객이 요청한 변경"과 "우리 입력 실수"는 책임 소재가
정반대인데, 값만 남은 원장에서는 똑같이 보인다.

**설계 규칙 3개**

1. **판정은 서버 사후 SSOT** — "이 저장이 사유를 물어야 하나"를 저장 *전에* 클라이언트가
   판정하면 경로 목록이 서버·클라 2벌이 되고, 어긋나는 순간 조용히 안 묻거나 헛묻는다.
   저장은 그대로 성공시키고, 서버가 이미 만든 diff 로 판정해 응답에 실어 보낸다.
2. **저장을 막지 않는다** — 사유 때문에 주문 저장이 실패하면 영업이 멈춘다. 화면이 사유를
   붙이지 않고 지나간 경우는 :data:`REASON_UNSPECIFIED` 로 집계된다(우회율을 나중에 센다).
3. **라벨은 여기서 굽지 않는다** — 원장에는 코드만 넣고 사람 라벨은 읽는 시점에 붙인다
   (라벨을 고치면 과거 기록도 함께 고쳐진다 — ORDER-DIFF-00 과 같은 규칙).

정본: ``docs/specs/2026-08-13-order-change-reason_SPEC.md``
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Iterable, Mapping

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.order_field_change_writer import path_template_of
from foms.services.orders.structured_diff import (
    AMOUNT_PATH_TEMPLATES,
    CONFIRMED_STAGES,
    CONSTRUCTION_SCHEDULE_TEMPLATES,
    SENSITIVE_ITEM_OPS,
    SENSITIVE_ITEM_TEMPLATE,
    SENSITIVE_PATH_TEMPLATES,
)
from models import OrderChangeReason, OrderFieldChange

logger = logging.getLogger(__name__)

__all__ = [
    "AMOUNT_MATERIAL_ABSOLUTE",
    "AMOUNT_MATERIAL_RATIO",
    "REASON_ATTACH_WINDOW",
    "REASON_CODES",
    "REASON_LABELS",
    "REASON_NOTE_LIMIT",
    "REASON_OTHER",
    "REASON_UNSPECIFIED",
    "ReasonAttachError",
    "attach_reason",
    "is_material_amount_change",
    "is_reason_required",
    "normalize_reason",
    "reason_label",
    "reasons_for_change_sets",
]

#: 금액 변경을 "물어볼 만큼 큰 변경"으로 볼 절대 기준(원). 잔돈 조정까지 사유를 물으면
#: 창이 아무 때나 뜨고, 그러면 직원이 목록에서 아무거나 고른다(사용자 결정 2026-08-13).
AMOUNT_MATERIAL_ABSOLUTE = 50_000

#: 같은 판정의 상대 기준. 작은 금액에서는 5% 가 5만원보다 먼저 걸린다(둘 중 하나만 넘으면 된다).
AMOUNT_MATERIAL_RATIO = 0.05

#: 사유를 붙일 수 있는 기간. 감사 기록이라 무한 소급 입력은 허용하지 않는다 —
#: 한참 뒤에 적는 사유는 기억이 아니라 재구성이다.
REASON_ATTACH_WINDOW = datetime.timedelta(hours=24)

#: 메모 컬럼 상한(마이그레이션 ``orderreason_00`` 과 같은 값).
REASON_NOTE_LIMIT = 200

#: 메모가 **필수**인 코드. 나머지는 목록 선택만으로 끝난다.
REASON_OTHER = "other"

#: 화면이 사유를 붙이지 않고 지나간 저장의 집계 키. 사용자가 고를 수 있는 값이 아니다.
REASON_UNSPECIFIED = "unspecified"

#: 사용자가 고르는 사유 코드(순서 = 화면 노출 순서). 자유 입력이 아니라 목록인 이유는
#: "입력 오류 정정이 이번 달 몇 건" 같은 질문이 인덱스를 타야 하기 때문이다(사용자 결정).
REASON_CODES: tuple[str, ...] = (
    "customer_request",
    "site_condition",
    "input_correction",
    "internal_adjustment",
    REASON_OTHER,
)

#: 표시용 라벨(읽는 시점에만 쓴다).
REASON_LABELS: dict[str, str] = {
    "customer_request": "고객 요청",
    "site_condition": "현장 사정",
    "input_correction": "입력 오류 정정",
    "internal_adjustment": "내부 조정",
    REASON_OTHER: "기타",
    REASON_UNSPECIFIED: "사유 미입력",
}


def reason_label(code: str | None) -> str:
    """사유 코드의 사람 라벨을 돌려준다.

    :param code: 사유 코드(``None`` 이면 미입력으로 본다).
    :return: 라벨 문자열(모르는 코드는 코드 그대로 — 기록을 감추지 않는다).
    """
    if not code:
        return REASON_LABELS[REASON_UNSPECIFIED]
    return REASON_LABELS.get(code, str(code))


def _as_amount(value: Any) -> float | None:
    """원장에 실린 금액 문자열을 숫자로 읽는다(읽을 수 없으면 ``None``).

    ``"1,300,000"``·``1300000``·``"130만"`` 같은 값이 섞여 들어온다. 숫자로 못 읽는 값은
    비교하지 않고 **변경으로 인정**한다(모르면 묻는 쪽이 안전하다 — 아래 호출부 참고).

    :param value: 원장 값.
    :return: 숫자 또는 ``None``.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    digits = re.sub(r"[^0-9.\-]", "", str(value))
    if digits in ("", "-", ".", "-."):
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def is_material_amount_change(change: Mapping[str, Any]) -> bool:
    """금액 변경이 사유를 물어야 할 만큼 큰지 판정한다 (ORDER-REASON-00).

    기준은 **절대·상대 둘 중 하나**다: :data:`AMOUNT_MATERIAL_ABSOLUTE` 이상이거나
    이전 값의 :data:`AMOUNT_MATERIAL_RATIO` 이상. 값을 숫자로 못 읽으면 참으로 본다 —
    감사 원장에서 "몰라서 안 물었다"보다 "물었다"가 낫다.

    :param change: ``diff_structured`` 가 만든 변경 dict.
    :return: 사유를 물어야 하면 ``True``.
    """
    before = _as_amount(change.get("before"))
    after = _as_amount(change.get("after"))
    if before is None and after is None:
        return True
    delta = abs((after or 0.0) - (before or 0.0))
    if delta >= AMOUNT_MATERIAL_ABSOLUTE:
        return True
    return bool(before) and delta >= abs(before) * AMOUNT_MATERIAL_RATIO


def is_reason_required(
    changes: Iterable[Mapping[str, Any]],
    *,
    stage: str | None = None,
) -> bool:
    """이 저장이 변경 사유를 물어야 하는지 판정한다.

축은 셋이고 규칙이 서로 다르다:

    * 실측·AS 일정·단계(:data:`~foms.services.orders.structured_diff.SENSITIVE_PATH_TEMPLATES`)
      — 바뀌면 묻는다.
    * **시공 일정** — 고객 컨펌(:data:`~foms.services.orders.structured_diff.CONFIRMED_STAGES`)
      이후에만 묻는다. 접수·실측·도면 단계의 시공일은 아직 잡는 중인 값이라 바뀌는 게 정상이고,
      운영 실측에서 사유 요구의 단일 최대 기여(27%)였다(사용자 결정 2026-08-13).
    * 금액(:data:`~foms.services.orders.structured_diff.AMOUNT_PATH_TEMPLATES`) — **크게**
      바뀌어야 묻는다(:func:`is_material_amount_change`). 잔돈 조정까지 물으면 창이 아무 때나
      뜨고, 그러면 목록에서 아무거나 고르게 된다.
    * 품목 추가·삭제 — 한 건으로만 남아 단가 경로에 안 걸리므로 따로 본다.

    품목 경로는 인덱스를 지운 템플릿으로 대조하므로 품목 번호가 밀려도 판정이 흔들리지
    않는다(ORDER-DIFF-01 의 ``path_template`` 과 같은 열쇠).

    :param changes: ``diff_structured`` 결과의 ``changes`` 목록.
    :param stage: 저장 후 ``workflow.stage``. 모르면(``None``·빈 값) 시공 일정도 묻는 쪽으로 본다 —
        단계를 못 읽었다는 이유로 기록이 비는 것보다 낫다.
    :return: 사유를 물어야 하면 ``True``.
    """
    stage_code = str(stage or "").strip().upper()
    # 빈 값·미상 단계는 "확정된 것으로" 본다 — 못 읽었다는 이유로 기록이 비면 안 된다.
    confirmed = not stage_code or stage_code in CONFIRMED_STAGES
    for change in changes or ():
        path = str((change or {}).get("path") or "")
        if not path:
            continue
        template = path_template_of(path)
        if template in SENSITIVE_PATH_TEMPLATES:
            return True
        # 시공 일정: 고객과 약속이 선 뒤(확정 이후)의 변경만 사유 대상이다.
        if template in CONSTRUCTION_SCHEDULE_TEMPLATES and confirmed:
            return True
        # 금액은 "바뀌었나"가 아니라 "크게 바뀌었나"로 본다(잔돈 조정 제외).
        if template in AMOUNT_PATH_TEMPLATES and is_material_amount_change(change or {}):
            return True
        # 품목 추가·삭제는 필드 변경이 아니라 한 건으로만 남아 items.*.price 에 안 걸린다.
        if template == SENSITIVE_ITEM_TEMPLATE and (change or {}).get("op") in SENSITIVE_ITEM_OPS:
            return True
    return False


def normalize_reason(code: Any, note: Any) -> tuple[str, str | None]:
    """입력받은 사유를 원장에 넣을 형태로 정규화한다.

    :param code: 사유 코드(목록 밖 값은 거부한다 — 집계가 목적이라 자유 코드를 허용하면
        목록으로 받은 의미가 없다).
    :param note: 메모. ``other`` 일 때만 필수이며 :data:`REASON_NOTE_LIMIT` 자로 자른다.
    :return: ``(code, note)``.
    :raises ValueError: 목록 밖 코드이거나 ``other`` 인데 메모가 비었을 때.
    """
    normalized_code = str(code or "").strip()
    if normalized_code not in REASON_CODES:
        raise ValueError("사유 코드가 올바르지 않습니다.")

    normalized_note = str(note or "").strip()[:REASON_NOTE_LIMIT] or None
    if normalized_code == REASON_OTHER and not normalized_note:
        raise ValueError("기타 사유는 메모를 입력해야 합니다.")
    return normalized_code, normalized_note


class ReasonAttachError(Exception):
    """사유 첨부 거절 — ``status`` 로 HTTP 코드를 함께 나른다.

    :param message: 사용자에게 보여줄 한글 사유.
    :param status: 응답 상태 코드(404 없음 · 403 권한 · 409 중복 · 410 기간 만료).
    """

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def attach_reason(
    session: Any,
    *,
    order_id: int,
    change_set_id: str,
    code: str,
    note: str | None,
    actor_user_id: int | None,
    is_admin: bool = False,
) -> OrderChangeReason:
    """저장 1회(change set)에 사유를 붙인다.

    저장 경로와 달리 여기는 **fail-open 이 아니다** — 사유 첨부가 실패했는데 성공한 척하면
    화면이 "기록됐다"고 말하고 원장에는 없다. 거절 사유는 그대로 사용자에게 보인다.

    규칙 4개:

    1. change set 이 **이 주문의 것**이어야 한다(다른 주문 이력에 사유를 심을 수 없다).
    2. 저장 후 :data:`REASON_ATTACH_WINDOW` 안에만 붙일 수 있다.
    3. 본인이 한 저장만. ADMIN 은 전체(대리 입력).
    4. **이미 사유가 있으면 409** — 감사 원장은 덮어쓰지 않는다.

    :param session: 호출부 트랜잭션 세션(여기서 commit 하지 않는다).
    :param order_id: 대상 주문 id.
    :param change_set_id: 저장 1회 묶음 id.
    :param code: 사유 코드(:data:`REASON_CODES`).
    :param note: 메모(``other`` 필수).
    :param actor_user_id: 사유를 적는 사람.
    :param is_admin: ADMIN 여부(타인 저장 대리 입력 허용).
    :return: 만들어진 원장 행(세션에 add 된 상태).
    :raises ValueError: 코드·메모가 규칙에 안 맞을 때.
    :raises ReasonAttachError: 위 규칙 1~4 위반.
    """
    normalized_code, normalized_note = normalize_reason(code, note)

    rows = (
        session.query(OrderFieldChange)
        .filter(OrderFieldChange.change_set_id == str(change_set_id or ""))
        .limit(200)
        .all()  # perf-ok: change set 은 저장 1회분이라 유계
    )
    if not rows or any(row.order_id != int(order_id) for row in rows):
        raise ReasonAttachError("해당 저장 기록을 찾을 수 없습니다.", 404)

    if not is_admin and any(row.actor_user_id != actor_user_id for row in rows):
        raise ReasonAttachError("본인이 저장한 변경에만 사유를 남길 수 있습니다.", 403)

    saved_at = min((row.created_at for row in rows if row.created_at), default=None)
    if saved_at is not None and now_utc_naive() - saved_at > REASON_ATTACH_WINDOW:
        raise ReasonAttachError("사유 입력 기간(24시간)이 지났습니다.", 410)

    existing = (
        session.query(OrderChangeReason)
        .filter(OrderChangeReason.change_set_id == str(change_set_id))
        .first()
    )
    if existing is not None:
        raise ReasonAttachError("이미 사유가 기록된 저장입니다.", 409)

    reason = OrderChangeReason(
        change_set_id=str(change_set_id),
        order_id=int(order_id),
        reason_code=normalized_code,
        reason_note=normalized_note,
        actor_user_id=actor_user_id,
    )
    session.add(reason)
    return reason


def reasons_for_change_sets(session: Any, change_set_ids: Iterable[str]) -> dict[str, dict]:
    """change set 별 사유를 읽기용 dict 로 모은다(이력 탭·감사 화면).

    :param session: 조회 세션.
    :param change_set_ids: 대상 change set id 목록.
    :return: ``{change_set_id: {'code','label','note'}}`` — 사유 없는 묶음은 키가 없다.
    """
    ids = [str(value) for value in change_set_ids if value]
    if not ids:
        return {}
    rows = (
        session.query(OrderChangeReason)
        .filter(OrderChangeReason.change_set_id.in_(ids))
        .all()  # perf-ok: batched by change set id
    )
    return {
        row.change_set_id: {
            'code': row.reason_code,
            'label': reason_label(row.reason_code),
            'note': row.reason_note,
        }
        for row in rows
    }
