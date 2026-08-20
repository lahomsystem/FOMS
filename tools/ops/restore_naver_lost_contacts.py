"""네이버 수집 주문에서 폼 저장이 지운 연락처 복구 (1회성 + 재실행 안전).

배경: ``ec6b22a9`` 이전의 ERP 폼 저장은 ``structured_data['parties']`` 를 통째로
대입했다. 편집 폼은 ``customer.name/phone`` · ``orderer.name`` · ``manager.name`` 만
렌더하므로, 폼이 모르는 키는 주문을 한 번 열어 저장하는 것만으로 사라졌다:

* ``parties.orderer.phone`` — 대리주문 주문자 번호(해피콜 대상 판단용)
* ``parties.customer.phone2`` — 보조 연락처(수집 47건 중 6건)

원본은 남아 있다. ``ExternalOrderLink.raw_snapshot`` 이 네이버 응답 그대로를 보관하고,
``mapping.build_structured_data`` 가 그 응답에서 같은 값을 순수 함수로 다시 만든다.
이 스크립트는 스냅샷을 정본으로 삼아 **비어 있는 키만** 되채운다.

복구 규칙(안전 우선):

* 현재 값이 비어 있고 스냅샷 값이 있을 때만 채운다. 값이 이미 있으면 다르더라도
  건드리지 않는다 — 사람이 고쳐 넣은 번호를 스냅샷이 덮으면 그게 새 유실이다.
* ``orderer.name`` 은 복구 대상이 아니다. ERP 에서 ``parties.orderer.name`` 은
  **발주사**(라홈/하우드)를 뜻하고 폼의 발주사 셀렉트가 그 자리에 쓴다. 수집이 같은
  자리에 주문자 이름을 넣어 두 뜻이 겹쳐 있는 상태라, 이름까지 되살리면 사람이 고른
  발주사를 스크립트가 되돌리게 된다. 이름 축 정리는 별건이다.
* 삭제된 주문(``status == 'DELETED'`` 또는 ``deleted_at``)은 건너뛴다.
* 멱등: 한 번 채우면 다음 실행은 값이 있으므로 ``restored=0`` 이 정상이다.

기본은 dry-run(집계·목록만, 쓰기 없음). 실제로 쓰려면 ``--execute`` 를 명시한다.
전화번호는 기본 마스킹해서 출력한다(스냅샷은 관리자 전용 개인정보다). 실제 값 확인이
필요하면 ``--reveal``.

사용법::

    # 무엇이 비어 있는지만 본다 (기본, 아무것도 쓰지 않음)
    python tools/ops/restore_naver_lost_contacts.py --dry-run

    # 실제로 되채운다
    python tools/ops/restore_naver_lost_contacts.py --execute

    # 재실행(멱등성 확인) — restored=0 이어야 정상
    python tools/ops/restore_naver_lost_contacts.py --dry-run
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
from foms.services.integrations.naver_commerce.mapping import (  # noqa: E402
    build_structured_data,
)
from models import ExternalOrderLink, Order  # noqa: E402

#: 되채우는 키 — (parties 하위 그룹, 필드). 폼이 렌더하지 않아 유실된 자리만 담는다.
#: ``orderer.name``/``customer.name``/``customer.phone`` 은 폼이 렌더하므로 제외한다
#: (빈 값도 사람이 '보낸 값'이라 스크립트가 뒤집으면 안 된다).
RESTORE_KEYS: tuple[tuple[str, str], ...] = (
    ("orderer", "phone"),
    ("customer", "phone2"),
)

DEFAULT_BATCH_SIZE = 200


def _text(value: Any) -> str:
    """None/비문자열/공백을 빈 문자열로 정규화한다."""
    if value is None:
        return ""
    return str(value).strip()


def _group(parties: Any, name: str) -> dict:
    """``parties[name]`` 을 dict 로 반환한다(형식이 아니면 빈 dict)."""
    if not isinstance(parties, dict):
        return {}
    group = parties.get(name)
    return group if isinstance(group, dict) else {}


def plan_parties_restore(current_parties: Any, snapshot_parties: Any) -> dict[str, str]:
    """되채울 값을 계산한다(순수 함수 — DB·쓰기 없음).

    Args:
        current_parties: 주문의 현재 ``structured_data['parties']``.
        snapshot_parties: 스냅샷을 다시 매핑해서 얻은 ``parties``(정본).

    Returns:
        ``{"orderer.phone": "010-...", ...}`` — 지금 비어 있고 스냅샷에는 값이 있는
        키만 담는다. 채울 게 없으면 빈 dict.
    """
    plan: dict[str, str] = {}
    for group_name, field in RESTORE_KEYS:
        wanted = _text(_group(snapshot_parties, group_name).get(field))
        if not wanted:
            continue
        if _text(_group(current_parties, group_name).get(field)):
            continue
        plan[f"{group_name}.{field}"] = wanted
    return plan


def apply_parties_restore(structured_data: Any, plan: dict[str, str]) -> dict:
    """``plan`` 을 반영한 새 ``structured_data`` 를 만든다(원본 불변, deepcopy).

    Args:
        structured_data: 주문의 현재 structured_data.
        plan: :func:`plan_parties_restore` 결과.

    Returns:
        복구값이 들어간 새 dict. 호출부가 ``order.structured_data`` 에 대입하고
        ``flag_modified`` 를 부른다.
    """
    new_sd = copy.deepcopy(structured_data) if isinstance(structured_data, dict) else {}
    parties = new_sd.get("parties")
    if not isinstance(parties, dict):
        parties = {}
        new_sd["parties"] = parties
    for dotted, value in plan.items():
        group_name, field = dotted.split(".", 1)
        group = parties.get(group_name)
        if not isinstance(group, dict):
            group = {}
            parties[group_name] = group
        group[field] = value
    return new_sd


def mask_phone(value: str) -> str:
    """가운데 자리를 가린 전화번호(``010-****-1403``). 형식이 낯설면 뒤 4자리만 남긴다."""
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 7:
        return "***"
    parts = value.split("-")
    if len(parts) == 3:
        return f"{parts[0]}-{'*' * len(parts[1])}-{parts[2]}"
    return f"{digits[:3]}-****-{digits[-4:]}"


def _is_gone(order: Order | None) -> bool:
    """주문이 없거나 삭제됐으면 True."""
    return order is None or order.status == "DELETED" or order.deleted_at is not None


def _snapshot_parties(link: ExternalOrderLink) -> tuple[dict | None, str | None]:
    """링크의 ``raw_snapshot`` 을 다시 매핑해 ``parties`` 를 얻는다.

    Returns:
        ``(parties, skip_reason)``. 스냅샷이 없거나 매핑이 깨지면 ``(None, 사유)``.
    """
    snapshot = link.raw_snapshot
    if not isinstance(snapshot, dict) or not snapshot:
        return None, "no_snapshot"
    try:
        mapped = build_structured_data(snapshot)
    except Exception:  # 스냅샷 형식이 매핑 기대와 다르면 이 링크만 건너뛴다.
        return None, "snapshot_unmappable"
    parties = mapped.get("parties")
    if not isinstance(parties, dict):
        return None, "snapshot_unmappable"
    return parties, None


def run_restore(
    session: Session,
    *,
    execute: bool = False,
    order_ids: list[int] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """수집 링크를 순회하며 비어 있는 연락처를 스냅샷 값으로 되채운다.

    Args:
        session: SQLAlchemy 세션.
        execute: True 면 실제로 커밋한다. False(기본)면 아무것도 쓰지 않는다.
        order_ids: 주면 그 주문들만 대상으로 한다(없으면 전체 수집분).
        batch_size: 이 개수만큼 주문을 고칠 때마다 중간 커밋.

    Returns:
        ``{"mode", "links_scanned", "orders_touched", "restored", "changes", "skipped"}``.
        ``changes`` 는 ``{"order_id", "link_id", "key", "value"}`` 목록(값은 원문).
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
        plan = plan_parties_restore(current_sd.get("parties"), snapshot_parties)
        if not plan:
            skipped["nothing_missing"] += 1
            continue

        for dotted, value in plan.items():
            changes.append(
                {"order_id": order.id, "link_id": link.id, "key": f"parties.{dotted}",
                 "value": value}
            )

        # dry-run 에서도 같은 값을 메모리에 반영해 둔다. 한 주문에 링크가 여럿일 때
        # (ADDON/REPAY) 두 번째 링크가 같은 자리를 또 대상으로 세지 않게 하기 위함이다.
        order.structured_data = apply_parties_restore(current_sd, plan)
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
        "restored": len(changes),
        "changes": changes,
        "skipped": dict(skipped),
    }


def format_report(result: dict[str, Any], *, reveal: bool = False) -> str:
    """사람이 읽는 보고서 문자열. 전화번호는 ``reveal`` 이 아니면 마스킹한다."""
    lines = [
        f"mode={result['mode']} links_scanned={result['links_scanned']} "
        f"orders_touched={result['orders_touched']} restored={result['restored']}",
    ]
    for change in result["changes"]:
        value = change["value"] if reveal else mask_phone(change["value"])
        lines.append(
            f"  order {change['order_id']:>6}  link {change['link_id']:>4}  "
            f"{change['key']:<28} {value}"
        )
    if result["skipped"]:
        lines.append(f"  skipped: {json.dumps(result['skipped'], ensure_ascii=False)}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱 — 기본 dry-run, ``--execute`` 로만 실제 쓰기."""
    parser = argparse.ArgumentParser(
        description="Restore naver-ingested contacts that form saves dropped "
        "(default: dry-run)."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Explicit dry-run alias (default behavior)."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually write values. Without this, count only."
    )
    parser.add_argument(
        "--order-id", type=int, action="append", dest="order_ids",
        help="Limit to these order ids (repeatable).",
    )
    parser.add_argument(
        "--reveal", action="store_true", help="Print unmasked phone numbers.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점. 성공 0, 예외는 그대로 올린다(무음 실패 금지)."""
    args = _parse_args(argv)
    session = sessionmaker(bind=engine)()
    try:
        result = run_restore(
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
                change["value"] = mask_phone(change["value"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result, reveal=args.reveal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
