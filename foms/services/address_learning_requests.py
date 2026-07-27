"""주소 교정 학습 child 저장 — policy/rate/audit (DATA-MEASUREMENT-01).

구 ``FOMSAddressConverter.add_learning_data`` 는 로그인만 하면 누구든 무제한으로
in-memory/파일 학습 사전을 오염시킬 수 있었다(감사 불가·rate 없음). 이 모듈은 학습 교정을
:class:`~models.AddressLearningRequest` durable child 행으로 기록하고 세 가지를 강제한다.

* **audit**: ``requested_by_user_id``·``created_at`` 로 누가/언제 교정했는지 남긴다.
* **rate**: 사용자별 최근 창(``_RATE_WINDOW``) row 수가 ``_RATE_MAX`` 이상이면 거부한다
  (무제한 all-STAFF 쓰기 차단).
* **outbox**: 행 id 를 ``ADDRESS_LEARNING`` outbox side-effect 로 예약해 실제 학습 적용을
  worker 로 비동기화한다(business tx 안에서 원자 insert).

호출자가 ``session.commit()`` 을 소유한다 — rate 초과/검증 실패는 insert 전에 예외로 나가고
commit 이 일어나지 않는다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.sidefx_outbox import enqueue_side_effect
from models import AddressLearningRequest, DomainSideEffectOutbox

__all__ = [
    "AddressLearningError",
    "AddressLearningRateLimited",
    "ADDRESS_LEARNING_APPLY_EFFECT",
    "record_address_learning_request",
]

#: 사용자별 rate 창·상한 (무제한 쓰기 차단). 창 안 요청 수가 상한 이상이면 거부.
_RATE_WINDOW = datetime.timedelta(hours=1)
_RATE_MAX = 60
#: outbox effect_type — worker 가 학습 사전에 교정을 반영한다(하류 handler).
ADDRESS_LEARNING_APPLY_EFFECT = "ADDRESS_LEARNING_APPLY"


class AddressLearningError(ValueError):
    """학습 요청 입력 검증 실패(빈 주소 등) — 400 매핑."""


class AddressLearningRateLimited(RuntimeError):
    """사용자별 rate 창 상한 초과 — 429 매핑(무제한 all-STAFF 쓰기 거부)."""


def _recent_count(session: Session, user_id: Optional[int], since: datetime.datetime) -> int:
    """``user_id`` 가 ``since`` 이후 만든 학습 요청 수(rate 판정용)."""
    if user_id is None:
        return 0
    return (
        session.query(AddressLearningRequest)
        .filter(
            AddressLearningRequest.requested_by_user_id == user_id,
            AddressLearningRequest.created_at >= since,
        )
        .count()
    )


def record_address_learning_request(
    session: Session,
    *,
    original_address: str,
    corrected_address: str,
    lat: Optional[float],
    lng: Optional[float],
    requested_by_user_id: Optional[int],
    now: Optional[datetime.datetime] = None,
) -> AddressLearningRequest:
    """학습 교정을 audit child 로 기록하고 적용 side-effect 를 예약한다(rate 강제).

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        original_address: 틀린 원 주소(비어 있으면 거부).
        corrected_address: 정답 주소(비어 있으면 거부).
        lat: 교정 위도(선택). None 허용.
        lng: 교정 경도(선택). None 허용.
        requested_by_user_id: 요청 주체 user id(audit·rate scope). None 이면 rate 미적용.
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        flush 된 :class:`~models.AddressLearningRequest` (id 채워짐; 커밋은 호출자).

    Raises:
        AddressLearningError: original/corrected 가 빈 문자열.
        AddressLearningRateLimited: 사용자별 rate 창 상한 초과.
    """
    original = (original_address or "").strip()
    corrected = (corrected_address or "").strip()
    if not original or not corrected:
        raise AddressLearningError("원 주소와 교정 주소가 모두 필요합니다.")

    now = now or now_utc_naive()
    if _recent_count(session, requested_by_user_id, now - _RATE_WINDOW) >= _RATE_MAX:
        raise AddressLearningRateLimited(
            f"주소 학습 요청이 너무 많습니다(시간당 {_RATE_MAX}건 제한)."
        )

    row = AddressLearningRequest(
        original_address=original,
        corrected_address=corrected,
        lat=lat,
        lng=lng,
        requested_by_user_id=requested_by_user_id,
        created_at=now,
    )
    session.add(row)
    session.flush()  # row.id 확보(outbox source_id 참조)

    enqueue_side_effect(
        session,
        source_domain="ADDRESS_LEARNING",
        source_id=row.id,
        effect_type=ADDRESS_LEARNING_APPLY_EFFECT,
        payload={
            "address_learning_request_id": row.id,
            "original_address": original,
            "corrected_address": corrected,
            "lat": lat,
            "lng": lng,
        },
        dedupe_key=f"{ADDRESS_LEARNING_APPLY_EFFECT}:{row.id}",
        now=now,
    )
    return row
