"""네이버 수집 파이프라인 — 변경분 조회 → 필터 → 상세 → 주문 생성 (NAVER-INGEST-01 §3.3).

**WORKER 프로세스 전용**이다. web 에서 부르면 커머스API센터에 등록되지 않은 IP 라 차단된다
(IP 슬롯 3개를 WORKER 가 전부 쓴다 — 스펙 §3.1). web 의 "지금 수집" 은 rq enqueue 만 한다.

멱등 규칙(두 겹):

1. 조회 전 ``ExternalOrderLink`` 에 이미 있는 ``productOrderId`` 를 걸러낸다(호출 절약).
2. 그래도 동시 실행이 겹치면 ``UNIQUE (channel, external_id)`` 가 DB 에서 막는다. 그때는
   실패가 아니라 **정상 skip** 으로 센다. 앱 선체크만으로는 체크와 INSERT 사이 창을 못 막는다.

매핑 실패는 주문을 만들지 않는다. 링크 행만 ``PENDING_REVIEW`` 로 남기고 사람이 관리 화면에서
확인한다(쓰레기 주문 생성 방지 — 스펙 §5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.integrations.naver_commerce.constants import (
    ACTOR_USERNAME as _ACTOR_USERNAME,
    CHANNEL as _CHANNEL,
    OWNER_USERNAME as _OWNER_USERNAME,
)
from foms.services.integrations.naver_commerce.mapping import (
    NaverMappingError,
    extract_external_id,
    is_collectible,
    map_detail,
)
from foms.services.orders.order_create import create_order
from foms.services.orders.order_mutation_policy import normalize_team
from models import ExternalOrderLink, User

logger = logging.getLogger(__name__)

# 상수 정본은 constants.py 다(의존성 없는 모듈). web 화면도 같은 값을 알아야 하는데 이 모듈을
# import 하면 web 이 수집 파이프라인을 끌어오게 되어 WORKER 단일 출구 계약이 흐려진다.
CHANNEL = _CHANNEL
ACTOR_USERNAME = _ACTOR_USERNAME
OWNER_USERNAME = _OWNER_USERNAME


class IngestAccountError(RuntimeError):
    """수집용 시스템 계정이 없거나 정책에 맞지 않는다 — 수집을 시작하지 않는다."""


@dataclass
class SyncResult:
    """한 번의 수집 실행 결과(운영 로그·관리 화면 표시용)."""

    changed: int = 0            # 변경분 이벤트 총건수
    candidates: int = 0         # 그중 결제완료(PAYED) 후보
    fetched: int = 0            # 상세를 실제로 받아온 건수
    created: int = 0            # 주문을 만든 건수
    skipped: int = 0            # 이미 수집된 건(멱등 skip)
    pending_review: int = 0     # 매핑 실패로 보류한 건
    order_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON 출력용 dict(runner --json 이 그대로 찍는다)."""
        return {
            "changed": self.changed,
            "candidates": self.candidates,
            "fetched": self.fetched,
            "created": self.created,
            "skipped": self.skipped,
            "pending_review": self.pending_review,
            "order_ids": list(self.order_ids),
            "errors": list(self.errors),
        }


def resolve_ingest_accounts(session: Session) -> tuple[int, int]:
    """actor(봇)·owner(미배정 보류함) user id 를 확정한다.

    owner 는 ``create_order`` 의 owner 계약(활성 SALES)을 그대로 만족해야 한다. 아니면
    수집을 시작하지 않는다 — 계정이 잘못된 채로 돌면 주문이 엉뚱한 사람에게 배정된다.

    Args:
        session: DB 세션.

    Returns:
        ``(actor_user_id, owner_user_id)``.

    Raises:
        IngestAccountError: 계정 부재·비활성·비SALES owner.
    """
    actor = session.query(User).filter(User.username == ACTOR_USERNAME).first()
    owner = session.query(User).filter(User.username == OWNER_USERNAME).first()
    if actor is None:
        raise IngestAccountError(f"수집 actor 계정이 없다: {ACTOR_USERNAME} (T0 선행 작업)")
    if owner is None:
        raise IngestAccountError(f"미배정 보류함 계정이 없다: {OWNER_USERNAME} (T0 선행 작업)")
    if not owner.is_active or normalize_team(owner.team) != "SALES":
        raise IngestAccountError(
            f"{OWNER_USERNAME} 는 활성 SALES 여야 한다(현재 active={owner.is_active}, team={owner.team})."
        )
    return (int(actor.id), int(owner.id))


def existing_external_ids(session: Session, external_ids: list[str]) -> set[str]:
    """이미 링크된 ``productOrderId`` 집합을 배치 조회로 구한다(N+1 금지)."""
    if not external_ids:
        return set()
    rows = (
        session.query(ExternalOrderLink.external_id)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.external_id.in_(external_ids),
        )
        .all()
    )
    return {row[0] for row in rows}


def _record_pending(session: Session, *, external_id: str, detail: dict, reason: str) -> None:
    """매핑 실패 건을 주문 없이 보류 링크로 남긴다(원본 보존)."""
    _order, product_order, _shipping = _safe_unwrap(detail)
    session.add(
        ExternalOrderLink(
            channel=CHANNEL,
            external_id=external_id,
            order_id=None,
            external_order_no=str((_order or {}).get("orderId") or "") or None,
            raw_snapshot=detail,
            sync_status="PENDING_REVIEW",
            failure_reason=reason[:2000],
        )
    )
    session.flush()


def _safe_unwrap(detail: dict) -> tuple[dict, dict, dict]:
    """매핑 모듈의 unwrap 을 쓰되 실패해도 흐름을 막지 않는다."""
    from foms.services.integrations.naver_commerce.mapping import unwrap_detail

    try:
        return unwrap_detail(detail)
    except Exception as exc:  # noqa: BLE001 - 보류 기록 경로라 실패해도 진행한다
        logger.warning("[NAVER] 상세 unwrap 실패(보류 기록은 계속): %s", exc, exc_info=True)
        return ({}, {}, {})


def ingest_detail(
    session: Session, detail: dict, *, actor_user_id: int, owner_user_id: int,
    today: str, now: Optional[datetime] = None,
) -> str:
    """상세 1건을 주문 + 링크로 반영한다. 결과 코드를 돌려준다.

    ``create_order()`` 를 경유하므로 mutation_version·owner 배정·``ORDER_CREATED`` 이벤트·
    quest seed·GEOCODE outbox 예약이 함께 붙는다(raw ``Order(...)`` 금지 — ORDER-CREATE-01).
    **좌표는 주입하지 않는다** — 기존 주문과 똑같이 지오코딩한다.

    Args:
        session: 호출자 소유 세션(커밋은 호출자).
        detail: 상품주문 상세 1건.
        actor_user_id: 봇 계정 id(이벤트 author).
        owner_user_id: 미배정 보류함 계정 id.
        today: 접수일 대체값.
        now: 테스트용 시각 주입.

    Returns:
        ``"created"`` / ``"skipped"`` / ``"pending_review"``.
    """
    external_id = extract_external_id(detail)
    if not external_id:
        # 멱등 키가 없으면 링크 행조차 만들 수 없다(UNIQUE 키의 절반이 빈다).
        raise NaverMappingError("productOrderId 가 없어 링크를 만들 수 없다")

    try:
        _external_id, order_fields, structured = map_detail(detail, today=today)
    except NaverMappingError as exc:
        _record_pending(session, external_id=external_id, detail=detail, reason=str(exc))
        return "pending_review"

    order_no = str((_safe_unwrap(detail)[0] or {}).get("orderId") or "") or None
    savepoint = session.begin_nested()
    try:
        order = create_order(
            session,
            actor_user_id=actor_user_id,
            owner_user_id=owner_user_id,
            order_fields=order_fields,
            structured_data=structured,
            is_erp_order=True,
            now=now or now_utc_naive(),
        )
        session.add(
            ExternalOrderLink(
                channel=CHANNEL,
                external_id=external_id,
                order_id=order.id,
                external_order_no=order_no,
                raw_snapshot=detail,
                sync_status="LINKED",
            )
        )
        session.flush()
        savepoint.commit()
    except IntegrityError:
        # UNIQUE (channel, external_id) — 동시 실행이 먼저 만든 것. 실패가 아니라 skip.
        savepoint.rollback()
        logger.info("[NAVER] 중복 수집 차단(UNIQUE) — productOrderId=%s", external_id)
        return "skipped"
    return "created"


def sync_naver_orders(
    session: Session, *, client: Any, start: datetime, end: datetime,
    actor_user_id: Optional[int] = None, owner_user_id: Optional[int] = None,
    dry_run: bool = False, now: Optional[datetime] = None,
) -> SyncResult:
    """한 구간을 수집한다(호출자가 commit 을 소유한다).

    Args:
        session: DB 세션.
        client: :class:`~foms.services.integrations.naver_commerce.client.NaverCommerceClient`.
        start: 구간 시작(워터마크).
        end: 구간 끝(보통 지금).
        actor_user_id: 미지정이면 :func:`resolve_ingest_accounts` 로 확정.
        owner_user_id: 미지정이면 :func:`resolve_ingest_accounts` 로 확정.
        dry_run: True 면 조회까지만 하고 주문·링크를 만들지 않는다.
        now: 테스트용 시각 주입.

    Returns:
        :class:`SyncResult` 집계.
    """
    result = SyncResult()
    changed = client.get_last_changed_statuses(start, end)
    result.changed = len(changed)

    candidate_ids: list[str] = []
    seen: set[str] = set()
    for entry in changed:
        if not is_collectible(entry):
            continue
        external_id = str((entry or {}).get("productOrderId") or "")
        if external_id and external_id not in seen:
            seen.add(external_id)
            candidate_ids.append(external_id)
    result.candidates = len(candidate_ids)

    already = existing_external_ids(session, candidate_ids)
    result.skipped += len(already)
    fresh_ids = [oid for oid in candidate_ids if oid not in already]
    if not fresh_ids:
        return result

    details = client.get_product_orders(fresh_ids)
    result.fetched = len(details)
    if dry_run:
        logger.info("[NAVER] dry-run — 상세 %d건 조회, 주문 생성 없음", len(details))
        return result

    if actor_user_id is None or owner_user_id is None:
        actor_user_id, owner_user_id = resolve_ingest_accounts(session)

    today = get_today_kst().strftime("%Y-%m-%d")
    for detail in details:
        try:
            outcome = ingest_detail(
                session, detail, actor_user_id=actor_user_id,
                owner_user_id=owner_user_id, today=today, now=now,
            )
        except NaverMappingError as exc:
            result.errors.append(str(exc))
            continue
        if outcome == "created":
            result.created += 1
            link = (
                session.query(ExternalOrderLink)
                .filter(ExternalOrderLink.channel == CHANNEL,
                        ExternalOrderLink.external_id == extract_external_id(detail))
                .first()
            )
            if link and link.order_id:
                result.order_ids.append(int(link.order_id))
        elif outcome == "skipped":
            result.skipped += 1
        else:
            result.pending_review += 1
    return result


def run_sweep(
    session: Session, *, client: Any = None, dry_run: bool = False,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """워터마크 구간을 1회 수집하고 결과 dict 를 돌려준다(러너·rq job 공용 진입점).

    성공하면 워터마크를 구간 끝으로 전진시키고, 실패하면 **전진시키지 않고** 사유만
    기록한다 — 다음 실행이 같은 구간을 다시 훑는다(유실 방지). 커밋은 이 함수가 한다
    (러너/워커가 tx 를 소유하지 않는 단발 실행이라).

    Args:
        session: DB 세션.
        client: 미지정이면 환경변수로 클라이언트를 만든다(WORKER 전용).
        dry_run: True 면 조회까지만 하고 아무것도 만들지 않으며 워터마크도 안 움직인다.
        now: 테스트용 시각 주입(KST aware).

    Returns:
        집계 dict(``window`` 구간 + :meth:`SyncResult.as_dict`).
    """
    from foms.services.integrations.naver_commerce import watermark as wm
    from foms.services.integrations.naver_commerce.client import KST, NaverCommerceClient

    current = now or datetime.now(KST)
    start, end = wm.resolve_window(session, now=current)
    payload: dict[str, Any] = {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "dry_run": bool(dry_run),
    }
    if start >= end:
        payload.update(SyncResult().as_dict())
        payload["note"] = "구간 없음(워터마크가 최신)"
        return payload

    client = client if client is not None else NaverCommerceClient()
    try:
        result = sync_naver_orders(session, client=client, start=start, end=end,
                                   dry_run=dry_run)
    except Exception as exc:
        session.rollback()
        wm.record_failure(session, error=str(exc), now=current)
        session.commit()
        payload.update(SyncResult().as_dict())
        payload["failed"] = str(exc)
        raise
    payload.update(result.as_dict())
    if not dry_run:
        wm.advance(session, success_to=end, summary=result.as_dict(), now=current)
        payload["expiry_alert"] = _check_app_expiry(session, current)
    session.commit()
    return payload


def _check_app_expiry(session: Session, current: datetime) -> Optional[int]:
    """앱 인증 만료 임박 알림을 태운다. 여기서 나는 오류가 수집을 되돌리면 안 된다.

    수집은 이미 성공했고 워터마크도 전진했다. 부가 알림 실패로 예외를 올리면 호출자가
    tx 를 롤백해 **성공한 수집이 통째로 사라진다** — 부가 기능이 본체를 죽이는 구조는 금지.
    """
    from foms.services.integrations.naver_commerce import app_expiry

    try:
        return app_expiry.check_and_notify(session, today=current.date(), now=now_utc_naive())
    except Exception as exc:  # noqa: BLE001 - 부가 알림 실패가 수집을 되돌리지 않게
        logger.warning("[NAVER] 앱 만료 알림 실패(수집은 유지): %s", exc, exc_info=True)
        return None


__all__ = [
    "ACTOR_USERNAME",
    "CHANNEL",
    "OWNER_USERNAME",
    "IngestAccountError",
    "SyncResult",
    "existing_external_ids",
    "ingest_detail",
    "resolve_ingest_accounts",
    "run_sweep",
    "sync_naver_orders",
]
