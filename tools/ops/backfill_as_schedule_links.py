"""AS 일정 매칭 링크 백필 — 출고 AS 추천 기적용분 (1회성).

문제: 출고 대시보드 "AS 일정추천" → `추가` 로 AS 방문일을 잡은 기존 건들은
출고 쪽에만 스냅샷이 남았다(``sd.shipment.recommendations[]``,
``foms/services/shipment/as_recommendation.py:156-193``). AS 쪽
``structured_data.schedule.as_visit.schedule_link`` 가 비어 있어, 그 기준
출고건의 시공일이 나중에 바뀌어도 드리프트 감지(``as_schedule_link.evaluate_drift``)
가 과거 데이터를 보지 못한다. 이 스크립트는 그 누락된 AS 쪽 링크를 채운다.

대상 조회는 무인덱스 JSONB 컨테인먼트가 아니라 ``OrderEvent.event_type``
(인덱스, ``models.py:776``) 이 ``AS_RECOMMENDATION_APPLIED`` 인 행의
``order_id``(=출고 주문 id) 집합으로 좁힌다. 각 출고 주문의
``sd.shipment.recommendations[]`` 항목마다 AS 주문을 읽어, 링크가 아직
없으면(``read_link(as_sd) is None``) 채운다.

건너뛰고 집계하는 경우:
- AS 주문이 없거나 ``DELETED`` (``status == "DELETED"`` 또는 ``deleted_at`` 존재)
- ``applied_visit_date`` 가 비어 있음
- 이미 링크가 존재함(멱등성의 핵심 — 재실행 시 0건이어야 정상)

기본은 ``--dry-run``(집계만, 쓰기 없음). 실제로 쓰려면 ``--execute`` 를 명시한다.
JSONB 쓰기는 프로젝트 규칙대로 ``copy.deepcopy`` + ``flag_modified`` 를 쓰고,
대량 실행 시 트랜잭션이 커지지 않도록 ``--batch-size``(기본 200) 링크마다
중간 커밋한다.

DB 세션은 Flask ``app`` 을 임포트하지 않고 ``db.engine`` 으로 직접 만든다
(``tools/ops/backfill_erp_flat_columns.py`` 선례 — 전체 app 초기화 없이
가볍게 뜨는 유지보수 CLI 패턴).

사용법::

    # 집계만 (기본, 아무것도 쓰지 않음)
    python tools/ops/backfill_as_schedule_links.py --dry-run

    # 실제로 링크를 채운다
    python tools/ops/backfill_as_schedule_links.py --execute

    # 재실행(멱등성 확인) — written=0 이어야 정상
    python tools/ops/backfill_as_schedule_links.py --dry-run
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from db import engine  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.orders.as_schedule_link import (  # noqa: E402
    SOURCE_SHIPMENT,
    read_link,
    write_link,
)
from models import Order, OrderEvent  # noqa: E402

EVENT_TYPE = "AS_RECOMMENDATION_APPLIED"
DEFAULT_BATCH_SIZE = 200


def _is_gone(order: Order | None) -> bool:
    """AS 주문이 없거나 삭제됐으면 True(``as_recommendation.py`` 의 동일 판정 이식)."""
    return order is None or order.status == "DELETED" or order.deleted_at is not None


def _parse_applied_at(raw: Any) -> datetime:
    """``entry['applied_at']``(ISO 문자열) 파싱. 없거나 형식이 틀리면 ``now_utc_naive()``."""
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return now_utc_naive()


def _shipment_order_ids_with_applied_event(session: Session) -> list[int]:
    """``OrderEvent.event_type`` 인덱스로 후보 출고 주문 id 를 좁힌다(JSONB 스캔 없음)."""
    rows = (
        session.query(OrderEvent.order_id)
        .filter(OrderEvent.event_type == EVENT_TYPE)
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


def _resolve_entry_target(
    session: Session, entry: dict[str, Any], linked_this_run: set[int]
) -> tuple[str | None, Order | None, dict | None, int | None, Any]:
    """스냅샷 entry 하나를 검사한다.

    Returns:
        ``(skip_reason, as_order, as_sd, as_order_id, applied_visit_date)``.
        ``skip_reason`` 이 None 이면 쓰기 대상(``as_order``/``as_sd`` 유효).
        skip 인 경우 ``as_order``/``as_sd`` 는 None 일 수 있다.
    """
    try:
        as_order_id = int(entry.get("as_order_id"))
    except (TypeError, ValueError):
        return "invalid_as_order_id", None, None, None, None

    applied_visit_date = entry.get("applied_visit_date")
    if not applied_visit_date:
        return "no_applied_visit_date", None, None, as_order_id, None
    if as_order_id in linked_this_run:
        return "already_linked", None, None, as_order_id, applied_visit_date

    as_order = session.query(Order).filter(Order.id == as_order_id).first()
    if _is_gone(as_order):
        return "as_order_gone", None, None, as_order_id, applied_visit_date

    as_sd = as_order.structured_data if isinstance(as_order.structured_data, dict) else {}
    if read_link(as_sd) is not None:
        return "already_linked", None, None, as_order_id, applied_visit_date

    return None, as_order, as_sd, as_order_id, applied_visit_date


def _write_backfill_link(
    as_order: Order, as_sd: dict, *, ship_id: int, entry: dict[str, Any], applied_visit_date: Any
) -> None:
    """실제 링크를 기록한다(``--execute`` 일 때만 호출). ``copy.deepcopy`` + ``flag_modified``."""
    new_sd = copy.deepcopy(as_sd)
    write_link(
        new_sd,
        ref_order_id=ship_id,
        ref_date=str(applied_visit_date),
        source=SOURCE_SHIPMENT,
        user_id=entry.get("applied_by_user_id"),
        user_name="",
        now=_parse_applied_at(entry.get("applied_at")),
    )
    as_order.structured_data = new_sd
    flag_modified(as_order, "structured_data")


def _shipment_recommendations(ship: Order) -> list:
    """``ship.structured_data.shipment.recommendations`` 리스트(형식이 아니면 빈 리스트)."""
    sd = ship.structured_data if isinstance(ship.structured_data, dict) else {}
    recs = (sd.get("shipment") or {}).get("recommendations")
    return recs if isinstance(recs, list) else []


def _process_entry(
    session: Session, ship_id: int, entry: dict[str, Any], linked_this_run: set[int], *,
    execute: bool,
) -> str | None:
    """entry 하나를 검사하고, 대상이면(``execute`` 일 때) 즉시 기록한다.

    Returns:
        skip 사유 문자열, 또는 기록(대상으로 확정)했으면 None.
    """
    reason, as_order, as_sd, as_order_id, applied_visit_date = _resolve_entry_target(
        session, entry, linked_this_run
    )
    if reason is not None:
        return reason
    if execute:
        _write_backfill_link(
            as_order, as_sd, ship_id=ship_id, entry=entry, applied_visit_date=applied_visit_date,
        )
    linked_this_run.add(as_order_id)
    return None


def run_backfill(
    session: Session, *, execute: bool = False, batch_size: int = DEFAULT_BATCH_SIZE
) -> dict[str, Any]:
    """출고 스냅샷(``sd.shipment.recommendations[]``)을 순회해 AS 쪽 ``schedule_link`` 를 채운다.

    Args:
        session: SQLAlchemy 세션(Flask ``db_session`` 또는 독립 세션 모두 가능).
        execute: True 면 실제로 커밋한다. False(기본)면 아무것도 쓰지 않는다(dry-run).
        batch_size: 이 개수만큼 링크를 쓸 때마다 중간 커밋(대량 실행 시 tx 크기 제한).

    Returns:
        ``{"mode", "candidates", "entries_scanned", "written", "skipped"}``(``skipped`` 는
        사유별 건수 dict).
    """
    skipped: Counter[str] = Counter()
    written = 0
    entries_scanned = 0
    since_commit = 0
    linked_this_run: set[int] = set()

    ship_ids = _shipment_order_ids_with_applied_event(session)
    ships = session.query(Order).filter(Order.id.in_(ship_ids)).all() if ship_ids else []

    for ship in ships:
        for entry in _shipment_recommendations(ship):
            if not isinstance(entry, dict):
                continue
            entries_scanned += 1
            reason = _process_entry(session, ship.id, entry, linked_this_run, execute=execute)
            if reason is not None:
                skipped[reason] += 1
                continue
            written += 1
            since_commit += 1
            if execute and since_commit >= batch_size:
                session.commit()
                since_commit = 0

    session.commit() if execute else session.rollback()

    return {
        "mode": "execute" if execute else "dry-run",
        "candidates": len(ships),
        "entries_scanned": entries_scanned,
        "written": written,
        "skipped": dict(skipped),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱 — 기본 dry-run, ``--execute`` 로만 실제 쓰기."""
    parser = argparse.ArgumentParser(
        description="Backfill AS-side schedule_link for already-applied shipment "
        "AS recommendations (default: dry-run)."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Explicit dry-run alias (default behavior)."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually write links. Without this, count only."
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Exit 0 on success, 1 on error/misuse."""
    args = _parse_args(argv)
    if args.dry_run and args.execute:
        print("[ERROR] --dry-run and --execute are mutually exclusive")
        return 1

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        summary = run_backfill(session, execute=args.execute, batch_size=args.batch_size)
    finally:
        session.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
