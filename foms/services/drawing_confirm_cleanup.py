"""수령 확정 때의 도면 목록 확정 + 교체된 옛 도면 행을 화면 목록에서 빼는 규칙.

2026-09-29 사용자 결정 — **수령 확정은 파일을 지우지 않는다.** 첨부 탭 '도면' 업로드,
교체된 옛 도면, 수정요청 참고사진 모두 스토리지와 ``OrderAttachment`` 에 남는다. 확정이
정하는 것은 ``drawing_current_files``(현재 도면 목록)와 ``CONFIRM_RECEIPT.files`` 뿐이다.
예전 정리 로직은 전달 이력의 **모든** 항목 files 를 삭제 후보로 모아 수정요청 참고사진·
첨부 탭 업로드까지 지웠고(C8·C8(a)·M6), 스토리지 삭제가 DB 커밋보다 먼저라 커밋이 실패해도
파일만 사라졌다(C8(b)). 전달 API 는 "옛 파일은 타임라인이 참조하므로 안 지운다"고 했는데
확정이 그 파일을 지워 이력 링크가 깨졌다(M15).

확정본은 전달 API(``perform_drawing_transfer``)가 전달할 때마다 이미 계산해 둔
``drawing_current_files`` 를 **그대로** 쓴다. 이력으로 다시 계산하지 않는다 — 이력에는 전달
API 가 판단에 쓴 입력(클라이언트 ``is_retransfer`` 값, 전달 시점의 도면 상태)이 다 남지 않아
다시 풀면 전달 때와 다른 답이 나온다. C8-X 가 그 예다: 대상 없는 재전달은
``mode='REPLACE'``·대상 None 으로 기록되는데(전달 API 는 현재본을 [수정본] 으로 바꿈) 재계산은
그것을 "맨 뒤에 추가"로 풀어 옛 도면을 되살렸다. 영업이 화면에서 보고 확정한 목록이 곧 확정본이다.

옛 도면 행이 남으므로 ``category='drawing'`` 첨부를 보여 주는 곳은 **교체된 옛 도면**
(전달 이력 TRANSFER·CONFIRM_RECEIPT 에 올랐지만 지금 ``drawing_current_files`` 에 없는 key)
행을 빼야 한다(:func:`superseded_drawing_keys`). 이 규칙을 쓰는 화면에서 교체된 옛 도면은
확정 전·뒤 모두 빠진다(확정 전 "1차·2차 섞여 보임"도 사라진다). 예외: 전달 이력에 한 번도
오르지 않은 도면 행(첨부 탭 '도면' 업로드, 그리고 M10 때문에 전달에 실패한 전달 모달 업로드
orders/<id>/attachments/)은 예전에는 확정 때 지워졌지만 이제 확정 뒤에도 보인다 — 원장 1차
리뷰 R1, 2차 M10 에서 정한다. 옛 도면 파일은 전달 이력(작업실 타임라인·비교 탭·창구 이력)
링크로 계속 열린다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import and_, func, inspect as sa_inspect, or_
from sqlalchemy.orm.util import identity_key

from models import Order, OrderAttachment

__all__ = [
    "discount_superseded_drawing_rows",
    "drop_superseded_drawing_rows",
    "exclude_superseded_drawing_rows",
    "finalize_drawing_files_on_confirm",
    "is_superseded_drawing_row",
    "load_structured_data_by_order",
    "resolve_final_drawing_files",
    "superseded_drawing_keys",
    "superseded_drawing_row_counts",
]

#: 도면 교체를 판정할 전달 이력 항목과 그 안의 파일 목록 필드. 수정요청(REQUEST_REVISION)의
#: files 는 영업이 올린 참고사진이라 도면 교체와 무관하다 — 넣지 않는다.
_DRAWING_HISTORY_FIELDS: dict[str, tuple[str, ...]] = {
    "TRANSFER": ("files", "previous_current_files"),
    "CONFIRM_RECEIPT": ("files",),
}

_DRAWING_CATEGORY = "drawing"


def _file_key(entry: Any) -> str:
    """도면 파일 dict 의 storage key(없으면 빈 문자열)."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("key") or "").strip()


def _normalize_file_entry(entry: dict[str, Any]) -> dict[str, str]:
    """structured_data 에 저장할 도면 파일 항목 모양으로 맞춘다."""
    key = _file_key(entry)
    filename = (entry.get("filename") or key.rsplit("/", 1)[-1]).strip()
    return {
        "key": key,
        "filename": filename,
        # 저장 URL 은 믿지 않는다(SPEC §4.3.4 — 검증 없이 저장된 옛 값). key 로만 만든다.
        "view_url": f"/api/files/view/{key}" if key else "",
        "download_url": f"/api/files/download/{key}" if key else "",
    }


def resolve_final_drawing_files(structured_data: Any) -> list[dict[str, str]]:
    """확정본 도면 목록 — 전달 API 가 이미 계산해 둔 ``drawing_current_files`` 를 정규화만 한다.

    생산 시트 썸네일(``foms/web/production/dashboard.py``)도 이 함수를 쓴다. 확정 목록과 같은
    답이어야 생산이 영업이 확정한 도면을 본다.

    Args:
        structured_data: 주문 ``structured_data``(dict 가 아니면 빈 목록).

    Returns:
        key 가 있는 항목만, 저장 순서(=도면 번호) 그대로.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    return [
        _normalize_file_entry(f)
        for f in (sd.get("drawing_current_files") or [])
        if _file_key(f)
    ]


def superseded_drawing_keys(structured_data: Any) -> frozenset[str]:
    """교체된 옛 도면의 storage key 집합.

    전달 이력 TRANSFER 의 ``files``·``previous_current_files`` 와 CONFIRM_RECEIPT 의 ``files``
    에 한 번이라도 올랐지만 지금 ``drawing_current_files`` 에 없는 key 다. 전달 취소된 전달은
    이력에서 빠지므로(``cancel-transfer``) 여기에도 안 잡힌다.

    Args:
        structured_data: 주문 ``structured_data``(dict 가 아니면 빈 집합).

    Returns:
        화면 목록에서 빼야 할 key 집합.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    current = {_file_key(f) for f in (sd.get("drawing_current_files") or [])}
    transferred: set[str] = set()
    for item in sd.get("drawing_transfer_history") or []:
        if not isinstance(item, dict):
            continue
        fields = _DRAWING_HISTORY_FIELDS.get(str(item.get("action") or "").upper(), ())
        for field in fields:
            for entry in item.get(field) or []:
                key = _file_key(entry)
                if key:
                    transferred.add(key)
    return frozenset(transferred - current)


def is_superseded_drawing_row(row: Any, keys: frozenset[str]) -> bool:
    """첨부 행이 교체된 옛 도면인가 — ``category='drawing'`` 이고 key 가 ``keys`` 에 있다."""
    category = str(getattr(row, "category", "") or "").strip().lower()
    storage_key = str(getattr(row, "storage_key", "") or "").strip()
    return category == _DRAWING_CATEGORY and storage_key in keys


def _superseded_row_clause(structured_data_by_order: Mapping[int, Any]) -> Any:
    """``도면 AND 주문별 옛 key`` SQL 조건 — 옛 key 가 있는 주문이 없으면 None."""
    per_order = []
    for order_id, sd in structured_data_by_order.items():
        keys = superseded_drawing_keys(sd)
        if keys:
            per_order.append(and_(
                OrderAttachment.order_id == int(order_id),
                OrderAttachment.storage_key.in_(sorted(keys)),
            ))
    if not per_order:
        return None
    return and_(func.lower(OrderAttachment.category) == _DRAWING_CATEGORY, or_(*per_order))


def exclude_superseded_drawing_rows(query: Any, structured_data_by_order: Mapping[int, Any]) -> Any:
    """``OrderAttachment`` 쿼리에서 교체된 옛 도면 행을 SQL 로 뺀다(개수·limit 이 정확하다).

    Args:
        query: ``OrderAttachment`` 컬럼을 거르는 쿼리.
        structured_data_by_order: ``{order_id: structured_data}`` — 쿼리에 걸린 주문들.

    Returns:
        뺄 행이 없으면 받은 쿼리 그대로, 있으면 ``NOT (도면 AND 주문별 옛 key)`` 를 건 쿼리.
    """
    clause = _superseded_row_clause(structured_data_by_order)
    if clause is None:
        return query
    # category·storage_key 는 NOT NULL 이라 NOT(...) 이 NULL 로 새지 않는다.
    return query.filter(~clause)


def superseded_drawing_row_counts(db: Any, structured_data_by_order: Mapping[int, Any]) -> dict[int, int]:
    """주문별로 살아 있는 교체된 옛 도면 행 수(R3 — 개수 쿼리가 목록과 같은 수를 내게).

    옛 key 가 있는 주문만 모아 ``GROUP BY order_id`` 쿼리 1회. 옛 key 가 없으면 쿼리 0회.
    ORM 조회라 전역 tombstone 필터(``deleted_at IS NULL``)를 받는다.

    Args:
        db: SQLAlchemy 세션.
        structured_data_by_order: ``{order_id: structured_data}``.

    Returns:
        ``{order_id: 옛 도면 행 수}`` — 0 인 주문은 빠진다.
    """
    clause = _superseded_row_clause(structured_data_by_order)
    if clause is None:
        return {}
    rows = (
        db.query(OrderAttachment.order_id, func.count(OrderAttachment.id))
        .filter(clause)
        .group_by(OrderAttachment.order_id)
        .all()
    )
    return {int(oid): int(cnt or 0) for oid, cnt in rows}


def discount_superseded_drawing_rows(
    db: Any, counts: dict[int, int], structured_data_by_order: Mapping[int, Any]
) -> dict[int, int]:
    """전체 첨부 개수 ``counts`` 에서 옛 도면 행 수를 뺀다(제자리 수정 후 같은 dict 반환).

    생산·시공 raw SQL·주문 대시보드 ORM·모바일 단건 개수(R3 네 곳)가 기존 카운트 뒤에 부른다.
    0 이 되면 키를 지운다(원래 GROUP BY 결과처럼 "행 없음").
    """
    for oid, n in superseded_drawing_row_counts(db, structured_data_by_order).items():
        left = int(counts.get(oid, 0)) - n
        if left > 0:
            counts[oid] = left
        else:
            counts.pop(oid, None)
    return counts


def load_structured_data_by_order(db: Any, order_ids: Iterable[int]) -> dict[int, Any]:
    """주문들의 ``structured_data`` — 이 세션에 이미 올라온 주문은 다시 읽지 않는다.

    대시보드 호출자는 같은 요청에서 주문을 이미 읽었다. identity map 의 행을 그대로 쓰고,
    없거나 structured_data 가 아직 안 읽힌 주문만 ``in_`` 한 번으로 읽는다(N+1 없음).

    Args:
        db: SQLAlchemy 세션.
        order_ids: 대상 주문 id.

    Returns:
        ``{order_id: structured_data}`` — 없는 주문은 빠진다.
    """
    out: dict[int, Any] = {}
    missing: list[int] = []
    for oid in sorted({int(o) for o in order_ids if o}):
        loaded = db.identity_map.get(identity_key(Order, oid))
        if isinstance(loaded, Order) and "structured_data" not in sa_inspect(loaded).unloaded:
            out[oid] = loaded.structured_data
        else:
            missing.append(oid)
    if missing:
        rows = (
            db.query(Order.id, Order.structured_data)
            .filter(Order.id.in_(missing))
            .all()
        )
        out.update({int(oid): sd for oid, sd in rows})
    return out


def drop_superseded_drawing_rows(
    db: Any,
    rows: Iterable[Any],
    *,
    structured_data_by_order: Mapping[int, Any] | None = None,
) -> list[Any]:
    """이미 읽은 첨부 행 목록에서 교체된 옛 도면 행을 뺀다(순서 유지).

    도면 행이 있는 주문만 판정한다. ``structured_data_by_order`` 에 없는 주문의 structured_data
    는 :func:`load_structured_data_by_order` 로 한 번에 읽는다.

    Args:
        db: SQLAlchemy 세션(모자란 structured_data 를 읽을 때만 쓴다).
        rows: ``order_id``·``category``·``storage_key`` 를 가진 첨부 행.
        structured_data_by_order: 호출자가 이미 가진 ``{order_id: structured_data}``.

    Returns:
        옛 도면 행을 뺀 목록.
    """
    rows = list(rows)
    drawing_order_ids = {
        int(r.order_id) for r in rows
        if str(getattr(r, "category", "") or "").strip().lower() == _DRAWING_CATEGORY
    }
    if not drawing_order_ids:
        return rows
    known = dict(structured_data_by_order or {})
    missing = drawing_order_ids - set(known)
    if missing:
        known.update(load_structured_data_by_order(db, missing))
    keys_by_order = {oid: superseded_drawing_keys(known.get(oid)) for oid in drawing_order_ids}
    return [
        r for r in rows
        if not is_superseded_drawing_row(r, keys_by_order.get(int(r.order_id), frozenset()))
    ]


def finalize_drawing_files_on_confirm(
    db: Any,
    order_id: int,
    structured_data: dict[str, Any],
) -> tuple[list[dict[str, str]], int]:
    """수령 확정본을 ``structured_data['drawing_current_files']`` 에 쓴다. 아무것도 지우지 않는다.

    Args:
        db: 호출자 계약 유지용(확정은 DB 행을 건드리지 않는다).
        order_id: 호출자 계약 유지용.
        structured_data: 주문 ``structured_data``(제자리에서 고친다).

    Returns:
        ``(확정본, 0)``. 두 번째 값은 호출자(``erp_orders_draftsman.py`` 수령 확정 라우트)가
        받아 두는 삭제 수다 — 확정은 더 이상 지우지 않으므로 늘 0 이다.
    """
    del db, order_id
    final_files = resolve_final_drawing_files(structured_data)
    structured_data["drawing_current_files"] = final_files
    return final_files, 0
