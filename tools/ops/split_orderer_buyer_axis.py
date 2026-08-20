"""수집 주문의 발주사/주문자 축 분리 백필 — ORDERER-AXIS-01 T2.

ORDERER-AXIS-01 이전에 수집된 주문은 ``parties.orderer`` 에 **사람**(주문자 이름·전화)이
들어 있다. ERP 에서 그 자리는 **발주사**(라홈/하우드)라, 그대로 두면 알림톡 브랜드 프로필·
도면 로고·퀘스트 CS 팀·견적서 양식이 전부 '라홈 아님'으로 갈린다.

이 스크립트가 이미 쌓인 주문을 새 축으로 옮긴다. 정본은 ``ExternalOrderLink.raw_snapshot``
(네이버 원본 응답)이다 — 스냅샷이 말하는 주문자와 현재 값이 같을 때만 "그건 사람이다"라고
판정한다. 사람이 손으로 고른 발주사는 건드리지 않는다.

판정 규칙:

===============================================  ==========================================
현재 상태                                        처리
===============================================  ==========================================
``orderer.name`` == 스냅샷 주문자명              ``buyer.name`` 으로 옮기고 발주사는 라홈
``orderer.name`` 이 비어 있음                    발주사 라홈, ``buyer.name`` = 스냅샷 주문자명
``orderer.name`` 이 그 외 값(사람이 고른 발주사) 그대로 둔다. ``buyer.name`` 만 채운다
``orderer.phone`` == 스냅샷 주문자 전화          ``buyer.phone`` 으로 옮기고 그 자리는 제거
``orderer.phone`` 이 그 외 값                    그대로 둔다(사람이 넣은 값)
===============================================  ==========================================

``buyer`` 에 이미 값이 있으면 덮지 않는다. 기본은 dry-run(집계·목록만), 실제로 쓰려면
``--execute``. 멱등 — 한 번 옮기면 다음 실행은 ``changed=0`` 이다. 전화번호는 기본
마스킹해서 출력한다(``--reveal`` 로 원문).

사용법::

    python tools/ops/split_orderer_buyer_axis.py --dry-run
    python tools/ops/split_orderer_buyer_axis.py --execute
    python tools/ops/split_orderer_buyer_axis.py --dry-run   # 재실행: changed=0
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from db import engine  # noqa: E402
from foms.services.integrations.naver_commerce.constants import (  # noqa: E402
    DEFAULT_ORDERER_NAME,
)
from models import ExternalOrderLink, Order  # noqa: E402
# 스냅샷 재매핑·주문 생사 판정·정규화는 복구 스크립트와 같은 규칙을 써야 한다
# (두 스크립트가 같은 링크 집합을 같은 기준으로 훑는다). 그래서 재구현하지 않고 가져온다.
from tools.ops.restore_naver_lost_contacts import (  # noqa: E402
    _group,
    _is_gone,
    _snapshot_parties,
    _text,
    mask_phone,
)

DEFAULT_BATCH_SIZE = 200

#: 마스킹해서 출력할 키(나머지는 이름이라 원문 그대로 보여준다).
_PHONE_KEYS = ("buyer.phone", "orderer.phone")


def plan_axis_split(current_parties: Any, snapshot_parties: Any) -> dict[str, Any]:
    """축 이동 계획을 계산한다(순수 함수 — DB·쓰기 없음).

    Args:
        current_parties: 주문의 현재 ``structured_data['parties']``.
        snapshot_parties: 스냅샷을 새 매핑으로 다시 만든 ``parties``
            (``orderer.name`` = 라홈, ``buyer`` = 사람).

    Returns:
        ``{"set": {"buyer.name": ..., "orderer.name": ...}, "unset": ["orderer.phone"]}``.
        옮길 게 없으면 두 값 모두 빈 상태.
    """
    person_name = _text(_group(snapshot_parties, "buyer").get("name"))
    person_phone = _text(_group(snapshot_parties, "buyer").get("phone"))
    current_orderer = _group(current_parties, "orderer")
    current_buyer = _group(current_parties, "buyer")

    to_set: dict[str, str] = {}
    to_unset: list[str] = []

    if person_name and not _text(current_buyer.get("name")):
        to_set["buyer.name"] = person_name
    if person_phone and not _text(current_buyer.get("phone")):
        to_set["buyer.phone"] = person_phone

    orderer_name = _text(current_orderer.get("name"))
    # 발주사 자리에 사람 이름이 있거나(스냅샷 주문자와 일치) 비어 있으면 라홈으로 세운다.
    # 그 외 값은 사람이 고른 발주사이므로 손대지 않는다.
    if (not orderer_name or orderer_name == person_name) and orderer_name != DEFAULT_ORDERER_NAME:
        to_set["orderer.name"] = DEFAULT_ORDERER_NAME

    orderer_phone = _text(current_orderer.get("phone"))
    if orderer_phone and orderer_phone == person_phone:
        to_unset.append("orderer.phone")

    return {"set": to_set, "unset": to_unset}


def apply_axis_split(structured_data: Any, plan: dict[str, Any]) -> dict:
    """``plan`` 을 반영한 새 ``structured_data`` 를 만든다(원본 불변, deepcopy).

    Args:
        structured_data: 주문의 현재 structured_data.
        plan: :func:`plan_axis_split` 결과.

    Returns:
        축 이동이 끝난 새 dict.
    """
    new_sd = copy.deepcopy(structured_data) if isinstance(structured_data, dict) else {}
    parties = new_sd.get("parties")
    if not isinstance(parties, dict):
        parties = {}
        new_sd["parties"] = parties

    for dotted, value in plan.get("set", {}).items():
        group_name, field = dotted.split(".", 1)
        group = parties.get(group_name)
        if not isinstance(group, dict):
            group = {}
            parties[group_name] = group
        group[field] = value

    for dotted in plan.get("unset", []):
        group_name, field = dotted.split(".", 1)
        group = parties.get(group_name)
        if isinstance(group, dict):
            group.pop(field, None)
    return new_sd


def run_split(
    session: Session,
    *,
    execute: bool = False,
    order_ids: list[int] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """수집 링크를 순회하며 발주사/주문자 축을 가른다.

    Args:
        session: SQLAlchemy 세션.
        execute: True 면 실제로 커밋한다. False(기본)면 아무것도 쓰지 않는다.
        order_ids: 주면 그 주문들만 대상으로 한다(없으면 전체 수집분).
        batch_size: 이 개수만큼 주문을 고칠 때마다 중간 커밋.

    Returns:
        ``{"mode", "links_scanned", "orders_touched", "changed", "changes", "skipped"}``.
        ``changes`` 는 ``{"order_id", "link_id", "key", "value", "op"}`` 목록
        (``op`` 는 ``set``/``unset``).
    """
    skipped: Counter[str] = Counter()
    changes: list[dict[str, Any]] = []
    touched_orders: set[int] = set()
    since_commit = 0

    query = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.order_id.isnot(None))
        .order_by(ExternalOrderLink.id.asc())
    )
    if order_ids:
        query = query.filter(ExternalOrderLink.order_id.in_(order_ids))
    links = query.all()

    for link in links:
        snapshot_parties, reason = _snapshot_parties(link)
        if reason is not None:
            skipped[reason] += 1
            continue

        order = session.query(Order).filter(Order.id == link.order_id).first()
        if _is_gone(order):
            skipped["order_gone"] += 1
            continue

        current_sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        plan = plan_axis_split(current_sd.get("parties"), snapshot_parties)
        if not plan["set"] and not plan["unset"]:
            skipped["already_split"] += 1
            continue

        for dotted, value in plan["set"].items():
            changes.append({"order_id": order.id, "link_id": link.id,
                            "key": f"parties.{dotted}", "value": value, "op": "set"})
        for dotted in plan["unset"]:
            changes.append({"order_id": order.id, "link_id": link.id,
                            "key": f"parties.{dotted}", "value": "", "op": "unset"})

        # dry-run 에서도 메모리에 반영해 둔다 — 한 주문에 링크가 여럿(ADDON/REPAY)일 때
        # 같은 자리를 두 번 세지 않게 한다.
        order.structured_data = apply_axis_split(current_sd, plan)
        touched_orders.add(order.id)
        if execute:
            flag_modified(order, "structured_data")
            since_commit += 1
            if since_commit >= batch_size:
                session.commit()
                since_commit = 0

    if execute:
        session.commit()
    else:
        session.rollback()

    return {
        "mode": "execute" if execute else "dry-run",
        "links_scanned": len(links),
        "orders_touched": len(touched_orders),
        "changed": len(changes),
        "changes": changes,
        "skipped": dict(skipped),
    }


def format_report(result: dict[str, Any], *, reveal: bool = False) -> str:
    """사람이 읽는 보고서. 전화번호는 ``reveal`` 이 아니면 마스킹한다."""
    lines = [
        f"mode={result['mode']} links_scanned={result['links_scanned']} "
        f"orders_touched={result['orders_touched']} changed={result['changed']}",
    ]
    for change in result["changes"]:
        value = change["value"]
        if value and not reveal and change["key"].endswith(_PHONE_KEYS):
            value = mask_phone(value)
        lines.append(
            f"  order {change['order_id']:>6}  link {change['link_id']:>4}  "
            f"{change['op']:<5} {change['key']:<26} {value}"
        )
    if result["skipped"]:
        lines.append(f"  skipped: {json.dumps(result['skipped'], ensure_ascii=False)}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱 — 기본 dry-run, ``--execute`` 로만 실제 쓰기."""
    parser = argparse.ArgumentParser(
        description="Split naver-ingested parties.orderer into 발주사(orderer) + "
        "사람(buyer) (default: dry-run)."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicit dry-run alias (default behavior).")
    parser.add_argument("--execute", action="store_true",
                        help="Actually write values. Without this, count only.")
    parser.add_argument("--order-id", type=int, action="append", dest="order_ids",
                        help="Limit to these order ids (repeatable).")
    parser.add_argument("--reveal", action="store_true", help="Print unmasked phone numbers.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. 성공 0, 예외는 그대로 올린다(무음 실패 금지)."""
    args = _parse_args(argv)
    session = sessionmaker(bind=engine)()
    try:
        result = run_split(
            session,
            execute=args.execute,
            order_ids=args.order_ids,
            batch_size=args.batch_size,
        )
    finally:
        session.close()

    if args.json:
        if not args.reveal:
            result = copy.deepcopy(result)
            for change in result["changes"]:
                if change["value"] and change["key"].endswith(_PHONE_KEYS):
                    change["value"] = mask_phone(change["value"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result, reveal=args.reveal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
