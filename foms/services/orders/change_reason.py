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

import logging
from typing import Any, Iterable, Mapping

from foms.services.orders.order_field_change_writer import path_template_of
from foms.services.orders.structured_diff import (
    SENSITIVE_ITEM_OPS,
    SENSITIVE_ITEM_TEMPLATE,
    SENSITIVE_PATH_TEMPLATES,
)

logger = logging.getLogger(__name__)

__all__ = [
    "REASON_CODES",
    "REASON_LABELS",
    "REASON_NOTE_LIMIT",
    "REASON_OTHER",
    "REASON_UNSPECIFIED",
    "is_reason_required",
    "normalize_reason",
    "reason_label",
]

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


def is_reason_required(changes: Iterable[Mapping[str, Any]]) -> bool:
    """이 저장이 변경 사유를 물어야 하는지 판정한다.

    :data:`~foms.services.orders.structured_diff.SENSITIVE_PATH_TEMPLATES` 에 걸리는 변경이
    하나라도 있으면 참이다. 품목 경로는 인덱스를 지운 템플릿으로 대조하므로 품목 번호가
    밀려도 판정이 흔들리지 않는다(ORDER-DIFF-01 의 ``path_template`` 과 같은 열쇠).

    :param changes: ``diff_structured`` 결과의 ``changes`` 목록.
    :return: 사유를 물어야 하면 ``True``.
    """
    for change in changes or ():
        path = str((change or {}).get("path") or "")
        if not path:
            continue
        template = path_template_of(path)
        if template in SENSITIVE_PATH_TEMPLATES:
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
