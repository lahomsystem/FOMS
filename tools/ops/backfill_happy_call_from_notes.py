"""비고가 '부재'·'콜백' 한 단어뿐인 옛 주문을 해피콜 드롭다운 칸으로 옮긴다 — 1회성.

2026-09-29 부터 해피콜 상태(부재·콜백)는 비고 글(``Order.notes``)과 따로
``structured_data['flags']['happy_call']`` 에 저장한다. 실측 모바일 카드(``site_memo``)는
``Order.notes`` 만 읽으므로, 그 전에 비고칸에 손으로 '부재'·'콜백'만 적어 둔 주문은 여전히
실측 화면에 그 글이 보인다. 이 스크립트가 그 몫이다.

대상: 살아 있는 주문 중 ``trim(notes)`` 가 정확히 '부재' 또는 '콜백'인 것. 다른 글과 섞인
비고("고객님 해외 출장 부재 / 카카오톡" 등)는 실측에 필요한 정보라 **건드리지 않는다**.
2026-09-29 운영 실측: 정확히 일치 86건(부재 83·콜백 3, 전부 실측 이후 단계), 섞임 28건.

동작: ``flags.happy_call`` 이 비어 있으면 그 단어를 넣고, ``notes`` 는 비운다(None).
이미 ``happy_call`` 이 있으면 덮지 않고 notes 만 비운다. 재실행하면 ``written=0`` 이어야
정상이다(멱등). 되돌릴 수 있게 옮긴 주문의 id·옛 비고를 결과 JSON 에 그대로 싣는다.

기본은 ``--dry-run``(집계만). 실제로 쓰려면 ``--execute`` 를 명시한다. JSONB 쓰기는
프로젝트 규칙대로 ``copy.deepcopy`` + ``flag_modified`` 를 쓰고 배치마다 중간 커밋한다.

사용법::

    python tools/ops/backfill_happy_call_from_notes.py --dry-run
    python tools/ops/backfill_happy_call_from_notes.py --execute
    python tools/ops/backfill_happy_call_from_notes.py --dry-run   # 재실행: 0건이어야 정상
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from db import engine  # noqa: E402
from models import Order  # noqa: E402

DEFAULT_BATCH_SIZE = 200
#: ``foms.api.erp_orders_structured.HAPPY_CALL_VALUES`` 와 같은 값. 그 모듈을 단독 import 하면
#: 순환 import(foms.web.auth) 로 깨져서 여기 옮겨 적는다 — 테스트가 두 값의 일치를 지킨다.
HAPPY_CALL_VALUES = frozenset({"부재", "콜백"})


def _candidate_order_ids(session: Session) -> list[int]:
    """비고가 정확히 부재·콜백 한 단어인 살아 있는 주문 id(오름차순)."""
    rows = (
        session.query(Order.id)
        .filter(func.trim(Order.notes).in_(sorted(HAPPY_CALL_VALUES)),
                Order.deleted_at.is_(None))
        .order_by(Order.id)
        .all()
    )
    return [int(row[0]) for row in rows]


def run_backfill(session: Session, *, execute: bool = False,
                 batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """비고의 부재·콜백을 ``flags.happy_call`` 로 옮기고 비고를 비운다.

    Returns:
        ``{"candidates", "written", "kept_existing_happy_call", "moved"}``.
        ``moved`` 는 ``[{"id", "old_notes", "stage"}]`` — 되돌리기용 원장이다.
    """
    summary = {"candidates": 0, "written": 0, "kept_existing_happy_call": 0, "moved": []}
    pending = 0
    for order_id in _candidate_order_ids(session):
        summary["candidates"] += 1
        order = session.get(Order, order_id)
        word = (order.notes or "").strip()
        if word not in HAPPY_CALL_VALUES:
            continue
        data = order.structured_data if isinstance(order.structured_data, dict) else {}
        flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}
        if flags.get("happy_call"):
            summary["kept_existing_happy_call"] += 1
        stage = ((data.get("workflow") or {}).get("stage") if isinstance(data.get("workflow"), dict)
                 else None) or order.status
        summary["written"] += 1
        summary["moved"].append({"id": order_id, "old_notes": order.notes, "stage": stage})
        if not execute:
            continue
        updated = copy.deepcopy(data)
        new_flags = updated.get("flags") if isinstance(updated.get("flags"), dict) else {}
        if not new_flags.get("happy_call"):
            new_flags["happy_call"] = word
        updated["flags"] = new_flags
        order.structured_data = updated
        flag_modified(order, "structured_data")
        order.notes = None
        pending += 1
        if pending >= batch_size:
            session.commit()
            pending = 0
    if execute and pending:
        session.commit()
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱 — 기본 dry-run, ``--execute`` 로만 실제 쓰기."""
    parser = argparse.ArgumentParser(
        description="Move notes that are exactly '부재'/'콜백' into flags.happy_call "
                    "(default: dry-run).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicit dry-run alias (default behavior).")
    parser.add_argument("--execute", action="store_true",
                        help="Actually write. Without this, count only.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Exit 0 on success, 1 on misuse."""
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
