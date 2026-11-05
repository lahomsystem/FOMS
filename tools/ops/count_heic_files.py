"""이미 저장된 아이폰 원본(HEIC/HEIF) 파일 수 세기 — 읽기 전용 (SPEC docs/specs/2026-11-04-heic-to-jpeg_SPEC.md §4 결정 4).

새로 올리는 HEIC 는 서버가 JPEG 로 바꾼다. 이 스크립트는 그 전에 쌓인 HEIC 가 몇 개인지만 센다.
바꿀지 말지는 이 숫자를 보고 사용자가 정한다. **쓰기는 하지 않는다.**

센다:

* ``order_attachments`` — 살아 있는 첨부(``deleted_at IS NULL``) 중 이름이 ``.heic``/``.heif`` 인 행.
  분류(category)별 개수와 합계 크기.
* ``orders.structured_data`` — 협력사 도면 수정 요청 사진처럼 첨부 행 없이 JSON 에만 key 가 있는 HEIC.
  주문 수와 key 수.

사용법::

    python tools/ops/count_heic_files.py           # 사람이 읽는 요약
    python tools/ops/count_heic_files.py --json    # JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import Text, cast, func, or_  # noqa: E402

from models import Order, OrderAttachment  # noqa: E402

_HEIC_KEY_RE = re.compile(r'"([^"]+\.(?:heic|heif))"', re.IGNORECASE)


def count_attachments(session: Any) -> dict[str, Any]:
    """살아 있는 첨부 중 HEIC/HEIF 행을 분류별로 센다."""
    name = func.lower(OrderAttachment.filename)
    rows = (
        session.query(OrderAttachment.category, func.count(OrderAttachment.id), func.coalesce(func.sum(OrderAttachment.file_size), 0))
        .filter(OrderAttachment.deleted_at.is_(None))
        .filter(or_(name.like("%.heic"), name.like("%.heif")))
        .group_by(OrderAttachment.category)
        .all()
    )
    by_category = {str(cat): {"count": int(n), "bytes": int(size or 0)} for cat, n, size in rows}
    return {
        "by_category": by_category,
        "total": sum(v["count"] for v in by_category.values()),
        "total_bytes": sum(v["bytes"] for v in by_category.values()),
    }


def count_structured_keys(session: Any, attachment_keys: set[str]) -> dict[str, Any]:
    """주문 JSON 안에만 있는 HEIC key(첨부 행이 없는 것)를 센다."""
    text = cast(Order.structured_data, Text)
    orders = 0
    keys: set[str] = set()
    q = (
        session.query(Order.id, Order.structured_data)
        .filter(Order.deleted_at.is_(None))
        .filter(or_(func.lower(text).like("%.heic%"), func.lower(text).like("%.heif%")))
    )
    for _oid, sd in q.yield_per(200):
        found = {k for k in _HEIC_KEY_RE.findall(json.dumps(sd, ensure_ascii=False)) if "/" in k}
        found -= attachment_keys
        if found:
            orders += 1
            keys |= found
    return {"orders": orders, "keys": len(keys)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="저장된 HEIC/HEIF 파일 수 세기(읽기 전용)")
    parser.add_argument("--json", action="store_true", help="JSON 으로 출력")
    args = parser.parse_args(argv)

    from sqlalchemy.orm import sessionmaker

    from db import engine

    session = sessionmaker(bind=engine)()
    try:
        attachments = count_attachments(session)
        name = func.lower(OrderAttachment.storage_key)
        attachment_keys = {
            k for (k,) in session.query(OrderAttachment.storage_key)
            .filter(or_(name.like("%.heic"), name.like("%.heif")))
            .all()
        }
        structured = count_structured_keys(session, attachment_keys)
    finally:
        session.rollback()
        session.close()

    result = {"attachments": attachments, "structured_only": structured}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"첨부 HEIC: {attachments['total']}개 ({attachments['total_bytes'] / 1024 / 1024:.1f}MB)")
    for cat, v in sorted(attachments["by_category"].items()):
        print(f"  - {cat}: {v['count']}개")
    print(f"주문 기록에만 있는 HEIC(협력사 수정 요청 사진 등): 주문 {structured['orders']}건, 파일 {structured['keys']}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
