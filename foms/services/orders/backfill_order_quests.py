"""QUEST-BACKFILL-00 — SAFE 주문 quest 단일성 정규화 backfill.

:mod:`~foms.services.orders.audit_order_quests` 가 ``SAFE`` 로 분류한 주문만
canonical 단일 quest 로 정규화한다. 정규화 = 위반 stage 의 approval-0 active 중복을
**terminal(SUPERSEDED) 처리**해 stage당 active quest 를 1개로 만드는 것뿐이다:

* survivor quest 는 **전혀 건드리지 않는다**(approval 보존).
* superseded 대상은 SAFE 정의상 approval 이 0 이므로, status/transitions/updated_at 만
  바꾸고 어떤 approval 필드(team_approvals·assignee_approval·required_approvals)도
  삭제/변경하지 않는다 → "기존 approval 삭제/변경 0" 불변식.
* lazy-create 없음: quest 를 새로 만들지 않는다. GET/approve 복구 금지 계약과 정합.

대량 apply 는 BACKFILL 공용 인프라 :mod:`foms.services.security.backfill.runs`
(lease/heartbeat/checkpoint/coverage/STOPPED_DRIFT)로 wrap 한다 — batch 별 business write +
checkpoint + heartbeat 를 한 tx 로 묶고, source fingerprint drift 면 write 전에 정지한다.
apply 는 active OPS approval(BACKFILL_APPLY seq≥1)이 선행돼야 하며(운영은
``consume_backfill_apply`` 로 소비), 이 모듈은 그 활성화를 ``activate_approval`` 훅으로 주입받는다.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.audit_order_quests import (
    PACKET_ID,
    PHASE,
    AuditReport,
    OrderQuestAudit,
    StageResolution,
    audit_orders,
    _quests_source_sha,
)
from foms.services.security.backfill import runs

SUPERSEDE_REASON = "QUEST_BACKFILL_SINGLENESS"


# --------------------------------------------------------------------------- #
# pure normalization
# --------------------------------------------------------------------------- #
def apply_resolutions_to_sd(
    structured_data: Dict[str, Any],
    resolutions: Sequence[StageResolution],
    *,
    now_iso: str,
) -> Tuple[Dict[str, Any], int]:
    """SAFE plan 을 적용한 새 structured_data 와 supersede 한 quest 수를 반환한다(순수).

    survivor 는 무변경. superseded 대상만 terminal 처리(approval 필드 무변경). 원본은
    복사(``copy.deepcopy``)해 건드리지 않는다 — 호출자가 flag_modified 로 커밋한다.

    Args:
        structured_data: 원본 주문 structured_data.
        resolutions: 해당 주문의 stage별 정규화 plan.
        now_iso: transition/updated_at 타임스탬프(ISO 문자열).

    Returns:
        (새 structured_data, superseded quest 수).
    """
    new_sd = copy.deepcopy(structured_data or {})
    quests = new_sd.get("quests")
    if not isinstance(quests, list):
        return new_sd, 0

    superseded_count = 0
    for resolution in resolutions:
        for idx in resolution.superseded_indexes:
            if not (0 <= idx < len(quests)) or not isinstance(quests[idx], dict):
                continue
            quest = quests[idx]
            quest["status"] = "SUPERSEDED"
            transitions = quest.get("transitions")
            if not isinstance(transitions, list):
                transitions = []
            transitions.append(
                {"to": "SUPERSEDED", "at": now_iso, "reason": SUPERSEDE_REASON}
            )
            quest["transitions"] = transitions
            quest["updated_at"] = now_iso
            superseded_count += 1
    return new_sd, superseded_count


# --------------------------------------------------------------------------- #
# runs.py-wrapped apply driver
# --------------------------------------------------------------------------- #
@dataclass
class BackfillReport:
    """backfill apply 결과 요약."""

    run_id: str = ""
    state: str = ""
    total_rows: int = 0
    completed_rows: int = 0
    superseded_quests: int = 0
    batches: int = 0
    stopped_drift: bool = False


def _iso(now: datetime.datetime) -> str:
    return now.isoformat()


def _chunks(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _batch_fingerprint(pairs: List[Tuple[int, str]]) -> str:
    """(order_id, source_sha) 목록의 결정적 fingerprint(batch drift 비교용)."""
    payload = json.dumps(sorted(pairs), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _live_source_sha(session: Session, order_id: int) -> str:
    """현재 DB 의 주문 quests 소스 fingerprint(audit 시점 대비 drift 감지)."""
    from models import Order

    sd = session.query(Order.structured_data).filter(Order.id == order_id).scalar()
    raw = sd.get("quests") if isinstance(sd, dict) else None
    return _quests_source_sha(raw)


def _apply_batch_write(
    session: Session, batch: List[OrderQuestAudit], now_iso: str, report: BackfillReport
) -> None:
    """batch 내 SAFE 주문에 정규화를 적용(runs.write_batch 의 business write 콜백)."""
    from models import Order

    for audit in batch:
        order = session.get(Order, audit.order_id)
        if order is None:
            continue
        new_sd, superseded = apply_resolutions_to_sd(
            order.structured_data or {}, audit.resolutions, now_iso=now_iso
        )
        order.structured_data = new_sd
        flag_modified(order, "structured_data")
        report.superseded_quests += superseded


def run_backfill(
    session: Session,
    *,
    db_instance_id: str,
    owner_identity: str,
    audit: Optional[AuditReport] = None,
    batch_size: int = 100,
    now: Optional[datetime.datetime] = None,
    activate_approval: Optional[Callable[[Session, Any], None]] = None,
) -> BackfillReport:
    """SAFE 주문을 BACKFILL 인프라로 wrap 해 정규화하고 coverage 100% 로 DONE 처리한다.

    Args:
        session: SQLAlchemy Session(호출자가 batch 마다 commit).
        db_instance_id: run identity 의 target DB 식별자.
        owner_identity: lease owner 식별자(원문 저장 안 됨 — hash 만).
        audit: 미리 계산한 audit(없으면 read-only 로 새로 audit).
        batch_size: batch 당 주문 수.
        now: 결정적 타임스탬프(테스트 주입용).
        activate_approval: ensure_run 직후 approval seq≥1 을 활성화하는 훅(운영은
            ``consume_backfill_apply``; 없으면 seq<1 이라 acquire_lease 가 거부).

    Returns:
        BackfillReport — run 상태·coverage·supersede 수.
    """
    now = now or now_utc_naive()
    now_iso = _iso(now)
    audit = audit or audit_orders(session)
    safe = list(audit.safe_audits)

    run = runs.ensure_run(
        session,
        packet_id=PACKET_ID,
        phase=PHASE,
        db_instance_id=db_instance_id,
        manifest_sha256=audit.manifest_sha256(),
        mapping_sha256=audit.mapping_sha256(),
        total_rows=len(safe),
        now=now,
    )
    run_id = run.run_id
    if activate_approval is not None:
        activate_approval(session, run)
    session.flush()

    report = BackfillReport(run_id=run_id, total_rows=len(safe))
    raw_token, _ = runs.new_lease_token()
    runs.acquire_lease(
        session,
        run_id,
        owner_identity_hash=runs.owner_hash(owner_identity),
        raw_token=raw_token,
        now=now,
    )
    session.commit()

    for seq, batch in enumerate(_chunks(safe, batch_size), start=1):
        expected_fp = _batch_fingerprint([(a.order_id, a.source_sha) for a in batch])
        live_fp = _batch_fingerprint(
            [(a.order_id, _live_source_sha(session, a.order_id)) for a in batch]
        )
        checkpoint = hashlib.sha256(
            f"{run_id}:{seq}:{sorted(a.order_id for a in batch)}".encode("utf-8")
        ).hexdigest()
        outcome = runs.write_batch(
            session,
            run_id,
            raw_token=raw_token,
            expected_fingerprint=expected_fp,
            live_fingerprint=live_fp,
            batch_business_write=lambda s, b=batch: _apply_batch_write(s, b, now_iso, report),
            completed_delta=len(batch),
            batch_seq=seq,
            checkpoint_sha256=checkpoint,
            now=now,
        )
        session.commit()
        report.batches += 1
        if outcome.stopped_drift:
            report.stopped_drift = True
            report.state = "STOPPED_DRIFT"
            report.completed_rows = outcome.completed_rows
            return report

    completed = runs.complete_run(session, run_id, raw_token=raw_token, now=now)
    session.commit()
    report.state = completed.state
    report.completed_rows = completed.completed_rows or 0
    return report


__all__ = [
    "SUPERSEDE_REASON",
    "BackfillReport",
    "apply_resolutions_to_sd",
    "run_backfill",
]
