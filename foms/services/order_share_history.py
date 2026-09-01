"""고객이 실제로 본 계약서 내용 원장 — 적재·조회 (SHARE-HIST-00).

스펙: docs/specs/2026-09-01-share-contract-view-history-design.md

공유 계약서가 라이브 반영으로 바뀌면서(2026-09-01) 같은 링크가 늘 최신 주문 값을 렌더한다.
그 대가로 **고객이 그날 본 계약서**가 남지 않는데, 법적 효력 문구가 있는 문서라 분쟁 시
제시할 근거가 필요하다. 이 모듈이 그 공백을 메운다 — 열람 시점에 렌더된 dict 를 그대로,
**내용이 바뀐 순간에만** 한 행씩 쌓는다.

commit 은 하지 않는다(``order_share.record_view`` 와 같은 규약 — 호출자 소관).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import OrderShareSnapshot

__all__ = [
    'SOURCE_LIVE', 'SOURCE_STORED', 'HISTORY_KINDS',
    'canonical_json', 'content_hash', 'record_snapshot_view',
    'latest_row', 'list_rows', 'summarize',
]

#: 라이브 재구성본 / 발급 시점 폴백본. 폴백으로 뜬 화면도 고객이 본 화면이라 똑같이 남기되
#: 구별은 해 둔다(분쟁 때 "왜 옛 금액이 떴나"의 답이 여기에 있다).
SOURCE_LIVE = 'live'
SOURCE_STORED = 'stored'

#: 계약 내용이 있는 종류만 남긴다 — ``drawing`` 은 도면 파일 목록이라 대상이 아니다.
HISTORY_KINDS = ('estimate', 'bundle')

#: 목록 API 가 한 번에 돌려주는 최대 행 수(원장은 무제한으로 쌓인다 — 화면만 자른다).
LIST_LIMIT = 50


def canonical_json(snapshot: Mapping[str, Any]) -> str:
    """중복 판정용 정규 직렬화 — 키 순서·공백에 흔들리지 않는 표현을 만든다.

    :param snapshot: 렌더된 계약서 dict.
    :return: 정규 JSON 문자열.
    """
    return json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), default=str)


def content_hash(snapshot: Mapping[str, Any]) -> str:
    """계약서 내용의 sha256 hex — 같은 내용이면 같은 값.

    :param snapshot: 렌더된 계약서 dict.
    :return: 64자 hex 문자열.
    """
    return hashlib.sha256(canonical_json(snapshot).encode('utf-8')).hexdigest()


def latest_row(session: Session, share_token_id: int) -> Optional[OrderShareSnapshot]:
    """그 링크의 가장 최근 열람 원장 행(없으면 ``None``).

    중복 판정은 **최신 행과만** 한다. 전체에서 같은 해시를 찾으면 금액이 A→B→A 로
    되돌아갔을 때 세 번째 상태가 첫 행에 흡수돼 시간축이 무너진다.

    :param session: DB 세션.
    :param share_token_id: 공유 토큰 id.
    :return: 최신 행 또는 ``None``.
    """
    return (
        session.query(OrderShareSnapshot)
        .filter(OrderShareSnapshot.share_token_id == int(share_token_id))
        .order_by(OrderShareSnapshot.id.desc())
        .first()
    )


def record_snapshot_view(
    session: Session,
    row: Any,
    snapshot: Mapping[str, Any],
    *,
    source: str = SOURCE_LIVE,
) -> Optional[OrderShareSnapshot]:
    """열람 1회를 원장에 반영한다 — 내용이 바뀐 순간에만 새 행을 만든다.

    최신 행과 내용이 같으면 ``last_viewed_at``/``view_count`` 만 갱신한다(무한 증식 방지).
    commit 은 하지 않는다.

    :param session: DB 세션.
    :param row: 공유 토큰 행(``OrderShareToken``).
    :param snapshot: 화면에 렌더된 계약서 dict.
    :param source: ``SOURCE_LIVE`` 또는 ``SOURCE_STORED``.
    :return: 새로 만든 행, 갱신한 기존 행, 또는 대상 아님이면 ``None``.
    """
    kind = getattr(row, 'kind', None)
    if kind not in HISTORY_KINDS:
        return None
    if not isinstance(snapshot, Mapping) or not snapshot:
        return None

    digest = content_hash(snapshot)
    now = now_utc_naive()
    latest = latest_row(session, int(row.id))
    if latest is not None and latest.content_hash == digest:
        latest.last_viewed_at = now
        latest.view_count = (latest.view_count or 0) + 1
        return latest

    created = OrderShareSnapshot(
        share_token_id=int(row.id),
        order_id=int(row.order_id),
        kind=str(kind),
        content_hash=digest,
        snapshot=dict(snapshot),
        source=(source if source in (SOURCE_LIVE, SOURCE_STORED) else SOURCE_LIVE),
        first_viewed_at=now,
        last_viewed_at=now,
        view_count=1,
    )
    session.add(created)
    return created


def list_rows(session: Session, share_token_id: int, *,
              limit: int = LIST_LIMIT) -> list[OrderShareSnapshot]:
    """그 링크의 열람 원장(최신순).

    :param session: DB 세션.
    :param share_token_id: 공유 토큰 id.
    :param limit: 최대 행 수.
    :return: 원장 행 목록.
    """
    return (
        session.query(OrderShareSnapshot)
        .filter(OrderShareSnapshot.share_token_id == int(share_token_id))
        .order_by(OrderShareSnapshot.id.desc())
        .limit(int(limit))
        .all()
    )


def summarize(snapshot: Any) -> dict[str, Any]:
    """목록 화면용 금액 요약 — 스냅샷 원문은 목록 응답에 싣지 않는다(응답 비대).

    :param snapshot: 저장된 계약서 dict.
    :return: 요약 dict(스냅샷이 dict 가 아니면 0 으로 채운 형태).
    """
    snap = snapshot if isinstance(snapshot, Mapping) else {}
    items = snap.get('items')
    return {
        'issued_date': snap.get('issued_date') or '',
        'items_count': len(items) if isinstance(items, list) else 0,
        'items_subtotal': int(snap.get('items_subtotal') or 0),
        'shipping_price': int(snap.get('shipping_price') or 0),
        'deposit_amount': int(snap.get('deposit_amount') or 0),
        'balance_amount': int(snap.get('balance_amount') or 0),
    }
