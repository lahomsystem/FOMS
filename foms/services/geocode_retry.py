"""지오코딩 재시도 정책 SSOT (GEO-RETRY-01).

``geocode_status`` 4상태와 "지금 다시 시도해도 되는가" 판정을 한 곳에 둔다. 이 판정이
세 곳에 흩어져 있던 시절의 결함(2026-09-01 조사):

* :mod:`foms.api.erp_map` — ``not stored_geocode_status`` 라 ``failed`` 를 **영구 제외**.
* :mod:`foms.api.measurement.map` — ``failed`` 24시간 백오프(유일한 구제책).
* :mod:`foms.services.geocode_candidates` — 스윕은 ``include_failed=False`` 로 돌아 제외.

그래서 일시적 네트워크 사고로 ``failed`` 가 된 주문은 사람이 손대기 전까지 영원히 좌표를
못 받았다(운영 실패 11건 전부 주소는 멀쩡했다).

상태 규약
    ``success``
        좌표 있음.
    ``pending``
        큐에 있거나 **일시 오류로 중단됨**. :data:`PENDING_RETRY_INTERVAL` 뒤 재시도.
    ``failed``
        사유 불명(이 규약 이전에 쌓인 레거시 실패 포함). :data:`FAILED_RETRY_INTERVAL`
        뒤 재시도 — 무한 배제하지 않는다.
    ``address_error``
        카카오가 "그런 주소 없음"이라고 답한 건. **자동 재시도 없음**(쿼터 낭비).
        사람이 주소를 고치면 write 경로(``reset_order_geocode_on_address_change``)가
        ``pending`` 으로 되돌리므로 자동으로 대상에 복귀한다.

화면은 3상태(success/pending/failed)만 안다. :func:`canonicalize_status` 가
``address_error`` 를 ``failed`` 로 접어 기존 "주소 오류 - 수정 필요" 배지를 그대로 쓴다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

__all__ = [
    "FAILURE_TRANSIENT",
    "FAILURE_PERMANENT",
    "STATUS_SUCCESS",
    "STATUS_PENDING",
    "STATUS_FAILED",
    "STATUS_ADDRESS_ERROR",
    "PENDING_RETRY_INTERVAL",
    "FAILED_RETRY_INTERVAL",
    "canonicalize_status",
    "should_retry_geocode",
]

#: 다시 부르면 될 실패(네트워크·쿼터·인증·서버 오류·응답 파싱 실패).
#:
#: 변환기(:mod:`foms.services.common.address_converter`)가 이 값을 돌려주고 저장단
#: (:func:`foms.services.geocode_helpers.apply_geocode_to_order`)이 상태를 가른다.
#: 상수를 이 가벼운 모듈에 두는 이유: 저장단이 실패 종류를 알기 위해 변환기 모듈(requests +
#: ``scripts/ops`` 동적 로딩)을 import 시점에 끌어오지 않게 하기 위함이다.
FAILURE_TRANSIENT = "transient"
#: 다시 불러도 같은 답이 오는 실패(주소가 조회되지 않음 / 좌표가 한국 밖).
FAILURE_PERMANENT = "permanent"

#: 좌표 획득 성공.
STATUS_SUCCESS = "success"
#: 큐 대기 또는 일시 오류로 보류.
STATUS_PENDING = "pending"
#: 사유 불명 실패(레거시 포함) — 백오프 뒤 재시도.
STATUS_FAILED = "failed"
#: 주소 자체가 조회되지 않는 건 — 자동 재시도 없음.
STATUS_ADDRESS_ERROR = "address_error"

#: ``pending`` 을 다시 집기까지의 최소 간격.
#:
#: 운영 실측상 변환은 건당 약 2.9초이고 RQ 워커는 동시성 1이다. 배치 50건이면 소진에
#: 약 145초가 걸리므로, 그보다 짧은 간격으로 다시 집으면 같은 주문이 큐에 겹쳐 쌓인다.
#: 600초 = 최악 소진 시간의 약 4배 여유(스윕 :data:`PENDING_RETRY_SECONDS` 와 같은 값).
PENDING_RETRY_INTERVAL = datetime.timedelta(seconds=600)

#: ``failed`` 를 다시 집기까지의 최소 간격.
#:
#: 사유 불명 실패는 되풀이 호출로 카카오 쿼터를 태울 수 있으니 하루 1회로 묶는다.
#: (실측 실패 27건 x 최대 14요청 = 하루 400요청 미만.) 진짜 주소 오류는
#: :data:`STATUS_ADDRESS_ERROR` 로 따로 표시돼 여기 들어오지 않는다.
FAILED_RETRY_INTERVAL = datetime.timedelta(hours=24)


def canonicalize_status(status: Optional[str]) -> Optional[str]:
    """저장 상태를 화면이 아는 3상태로 접는다.

    Args:
        status: DB ``geocode_status`` 원본 값(``None`` 가능).

    Returns:
        ``address_error`` 는 ``failed`` 로, 그 밖의 값은 그대로. 화면 배지·필터가
        새 상태값을 모르는 채 "상태 없음"으로 렌더되는 것을 막는다.

    >>> canonicalize_status('address_error')
    'failed'
    >>> canonicalize_status('pending')
    'pending'
    """
    if status == STATUS_ADDRESS_ERROR:
        return STATUS_FAILED
    return status


def should_retry_geocode(order: Any, *, now: datetime.datetime) -> bool:
    """좌표 없는 주문을 **지금** 다시 지오코딩 큐에 넣어도 되는지 판정한다.

    Args:
        order: 좌표가 없고 주소는 있는 Order(``geocode_status``·``geocoded_at`` 를 읽는다).
        now: 백오프 판정 기준 시각(naive UTC — ``geocoded_at`` 저장 규약과 같은 축).

    Returns:
        ``address_error`` 면 False(영구 — 주소가 고쳐지면 write 경로가 pending 으로
        되돌린다). ``pending``/``failed`` 는 마지막 시도(:attr:`geocoded_at`)로부터 각
        백오프가 지났을 때만 True(시도 시각이 없으면 True — 시각 불명은 오래된 것으로
        본다). 그 밖(NULL=미시도, success-but-no-coords)은 즉시 True.
    """
    status = getattr(order, "geocode_status", None)
    if status == STATUS_ADDRESS_ERROR:
        return False
    if status == STATUS_PENDING:
        return _older_than(order, now=now, interval=PENDING_RETRY_INTERVAL)
    if status == STATUS_FAILED:
        return _older_than(order, now=now, interval=FAILED_RETRY_INTERVAL)
    return True


def _older_than(order: Any, *, now: datetime.datetime, interval: datetime.timedelta) -> bool:
    """마지막 시도가 ``interval`` 보다 오래됐는지(시각 미기록이면 True)."""
    last_attempt = getattr(order, "geocoded_at", None)
    if last_attempt is None:
        return True
    return (now - last_attempt) >= interval
