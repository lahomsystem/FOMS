"""typed-domain side-effect outbox repository (SIDEFX-00).

domain side-effect(notification·cache·geocode·storage-delete·provider call)를 business
transaction 과 원자적으로 기록하는 typed outbox 의 **repository 계층**이다. 실제 side
effect 를 수행하지 않는다 — producer(각 도메인 write)·consumer(worker delivery/expiry/
retention loop)는 하류(SIDEFX-WORKER-01·CHANNEL-WRITER-01·URGENT-CALL-01 등) 몫이다.

여기서는 두 가지만 책임진다:

* :func:`enqueue_side_effect` — business tx 안에서 outbox 행 1개를 원자 insert. source_domain
  에 맞는 FK 컬럼 **하나만** 채워 one-of matrix 를 앱 계층에서 보장하고, DB CHECK/FK 가
  mismatch/orphan 을 backstop 한다. 호출자가 ``session.commit()`` 을 소유하므로 business
  tx rollback 시 outbox insert 도 함께 rollback 된다(원자성).
* :func:`purge_retention` — terminal 행(DONE completed_at>30d, DEAD dead_at>180d)만 batch
  삭제하는 retention 라이브러리 함수. PENDING/PROCESSING 은 절대 삭제하지 않고 source
  business row 도 건드리지 않는다. daily scheduler/CLI(SIDEFX-RETENTION-01)가 이 함수를
  반복 호출한다.

queue pickup·lease 획득/만료 reclaim·DEAD 전이 같은 consumer mechanics 는 worker 소관이며,
스키마(ix_dseo_queue / ix_dseo_lease_expiry 인덱스, status/lease 컬럼)가 그것을 지탱한다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN, DomainSideEffectOutbox

# retention 보존기간(§5.2 line 994: SUCCESS 30일, DEAD 180일).
DONE_RETENTION = datetime.timedelta(days=30)
DEAD_RETENTION = datetime.timedelta(days=180)


class SideEffectValidationError(ValueError):
    """source_domain/payload shape 위반(호출 시점 거부 — DB CHECK 도달 이전)."""


def enqueue_side_effect(
    session: Session,
    *,
    source_domain: str,
    source_id: int,
    effect_type: str,
    payload: dict[str, Any],
    dedupe_key: Optional[str] = None,
    provider_idempotency_key: Optional[str] = None,
    schema_version: int = 1,
    source_generation: Optional[int] = None,
    available_at: Optional[datetime.datetime] = None,
    now: Optional[datetime.datetime] = None,
) -> DomainSideEffectOutbox:
    """business tx 안에서 typed side-effect outbox 행 1개를 원자 insert 한다.

    ``source_domain`` 에 대응하는 FK 컬럼 **하나만** ``source_id`` 로 채우고 나머지 FK 는
    None 으로 둔다(one-of matrix 앱 보장). ``session.flush()`` 로 unique(dedupe)/CHECK/FK
    위반을 **호출자 tx 안에서 즉시** 노출한다 — 커밋은 호출자가 소유하므로 business tx 가
    rollback 되면 이 insert 도 rollback 된다.

    Args:
        session: business transaction 세션(호출자 소유, 커밋 미수행).
        source_domain: :data:`models.DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN` 의 7 도메인 중 하나.
        source_id: 그 도메인의 source child row id(자기 FK 컬럼에 저장). None 금지.
        effect_type: side effect 종류(예: NOTIFICATION/CACHE_INVALIDATE/GEOCODE/
            STORAGE_DELETE). dedupe unique 의 첫 축.
        payload: worker 가 소비할 JSON object(반드시 dict).
        dedupe_key: 중복 억제 키. 지정 시 ``(effect_type, dedupe_key)`` unique 로 중복
            outbox 행을 거부한다. None 이면 dedupe 하지 않는다.
        provider_idempotency_key: consumer 가 외부 provider 로 보낼 idempotency key(선택).
        schema_version: payload 스키마 버전(기본 1).
        source_generation: source 의 generation(cache family 등, 선택).
        available_at: pickup 가능 시각(기본 now — 즉시). 지연 예약 시 미래 시각.
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        flush 된 :class:`~models.DomainSideEffectOutbox` (id 채워짐; 커밋은 호출자).

    Raises:
        SideEffectValidationError: 알 수 없는 source_domain, source_id None, 비 dict payload.
        sqlalchemy.exc.IntegrityError: dedupe 중복, one-of CHECK 위반, orphan FK
            (실 FK 도메인: ORDER_EVENT/NOTIFICATION_EVENT/CHAT_ATTACHMENT).
    """
    if source_domain not in DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN:
        raise SideEffectValidationError(
            f"unknown source_domain {source_domain!r}; expected one of "
            f"{sorted(DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN)}."
        )
    if source_id is None:
        raise SideEffectValidationError("source_id must not be None.")
    if not isinstance(payload, dict):
        raise SideEffectValidationError("payload must be a JSON object (dict).")
    now = now or now_utc_naive()

    fk_column = DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN[source_domain]
    row = DomainSideEffectOutbox(
        source_domain=source_domain,
        effect_type=effect_type,
        payload=payload,
        schema_version=schema_version,
        source_generation=source_generation,
        provider_idempotency_key=provider_idempotency_key,
        dedupe_key=dedupe_key,
        status="PENDING",
        attempts=0,
        available_at=available_at or now,
        created_at=now,
    )
    setattr(row, fk_column, source_id)
    session.add(row)
    session.flush()  # dedupe/CHECK/FK 위반을 호출자 tx 안에서 즉시 노출(원자성 유지)
    return row


def _delete_batch(session: Session, *conditions, limit: int) -> int:
    """조건에 맞는 outbox 행을 최대 ``limit`` 개 keyset 삭제하고 삭제 수를 반환한다."""
    ids = [
        r.id
        for r in session.query(DomainSideEffectOutbox.id)
        .filter(*conditions)
        .limit(limit)
        .all()
    ]
    if not ids:
        return 0
    session.query(DomainSideEffectOutbox).filter(
        DomainSideEffectOutbox.id.in_(ids)
    ).delete(synchronize_session=False)
    return len(ids)


def purge_retention(
    session: Session,
    *,
    now: Optional[datetime.datetime] = None,
    done_retention: datetime.timedelta = DONE_RETENTION,
    dead_retention: datetime.timedelta = DEAD_RETENTION,
    limit: int = 1000,
) -> dict[str, int]:
    """보존기간 경과 terminal 행만 batch 삭제한다(DONE 30d / DEAD 180d).

    PENDING/PROCESSING 는 삭제 대상이 아니며 source business row 도 건드리지 않는다(outbox
    행만 삭제). 호출자가 ``session.commit()`` 을 소유한다. 대량 삭제는 ``limit`` 배치로
    나뉘므로 SIDEFX-RETENTION-01 CLI 가 0 반환까지 반복 호출한다.

    Args:
        session: 세션(호출자 소유, 커밋 미수행).
        now: 기준 시각(기본 now_utc_naive()).
        done_retention: DONE 보존기간(기본 30일). completed_at 이 이보다 오래면 삭제.
        dead_retention: DEAD 보존기간(기본 180일). dead_at 이 이보다 오래면 삭제.
        limit: 상태별 배치 삭제 상한(기본 1000).

    Returns:
        ``{"done_purged": <int>, "dead_purged": <int>}`` — 이번 호출 삭제 수.
    """
    now = now or now_utc_naive()
    done_cutoff = now - done_retention
    dead_cutoff = now - dead_retention

    done_purged = _delete_batch(
        session,
        DomainSideEffectOutbox.status == "DONE",
        DomainSideEffectOutbox.completed_at.isnot(None),
        DomainSideEffectOutbox.completed_at < done_cutoff,
        limit=limit,
    )
    dead_purged = _delete_batch(
        session,
        DomainSideEffectOutbox.status == "DEAD",
        DomainSideEffectOutbox.dead_at.isnot(None),
        DomainSideEffectOutbox.dead_at < dead_cutoff,
        limit=limit,
    )
    return {"done_purged": done_purged, "dead_purged": dead_purged}
