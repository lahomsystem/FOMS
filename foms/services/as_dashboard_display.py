"""Display helpers for ERP AS dashboard mobile cards."""

from __future__ import annotations

import datetime
from typing import Any

from foms.api.files import build_file_view_url
from foms.services.feature_flags import env_bool_or_mobile_v2
from foms.services.erp_display import (
    _ensure_dict,
    apply_erp_display_fields_to_orders,
    get_today_kst,
)
from foms.services.as_content_safety import as_content_html_to_text, sanitize_as_content_html
from foms.services.orders.as_log import build_as_timeline_view
from foms.services.orders.as_schedule_link import (
    evaluate_drift,
    read_as_visit_date,
    read_link,
)
from models import Order, OrderAttachment

__all__ = [
    "as_billing_badge_kind",
    "as_billing_state_text",
    "apply_timeline_cell_text",
    "as_stage_badge_modifier",
    "as_thumb_enabled",
    "batch_resolve_as_thumbnail_urls",
    "batch_resolve_as_compare_photos",
    "apply_as_dashboard_row_display_fields",
    "apply_schedule_link_drift_fields",
    "build_schedule_link_drift",
]

_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def as_thumb_enabled(*, mobile_v2_active: bool = False) -> bool:
    """Return whether mobile AS card thumbnails are enabled.

    Args:
        mobile_v2_active: ERP mobile v2 cohort active for current user.

    Returns:
        True when explicit env is truthy, or env unset and ``mobile_v2_active``.
    """
    return env_bool_or_mobile_v2(
        "FOMS_V3_AS_THUMB_ENABLED",
        mobile_v2_active=mobile_v2_active,
    )


def as_stage_badge_modifier(*, status: str, as_pending: bool) -> str:
    """Return v1.1 stage badge CSS modifier for an AS row.

    Args:
        status: Order status code (e.g. ``AS_RECEIVED``, ``AS_COMPLETED``).
        as_pending: Whether the row is marked pending on visit date.

    Returns:
        Modifier suffix such as ``--cs`` or ``--completed``.
    """
    if status == "AS_COMPLETED":
        return "--completed"
    return "--cs"


def _is_image_filename(filename: str | None) -> bool:
    name = (filename or "").strip().lower()
    if not name:
        return False
    return name.endswith(_IMAGE_SUFFIXES)


def _attachment_image_url(attachment: OrderAttachment) -> str | None:
    thumb_key = (attachment.thumbnail_key or "").strip()
    if thumb_key:
        return build_file_view_url(thumb_key)
    storage_key = (attachment.storage_key or "").strip()
    if not storage_key:
        return None
    if (attachment.file_type or "").strip().lower() == "image" or _is_image_filename(
        attachment.filename
    ):
        return build_file_view_url(storage_key)
    return None


def batch_resolve_as_thumbnail_urls(order_ids: list[int], db: Any) -> dict[int, str | None]:
    """Resolve first AS image thumbnail URL per order id.

    Args:
        order_ids: Order primary keys on the current page.
        db: SQLAlchemy session.

    Returns:
        Mapping of order id to view URL (missing keys mean no thumbnail).
    """
    if not as_thumb_enabled() or not order_ids:
        return {}

    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == "as",
        )
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.asc())
        .all()
    )

    urls: dict[int, str | None] = {}
    for attachment in attachments:
        oid = int(attachment.order_id)
        if oid in urls:
            continue
        url = _attachment_image_url(attachment)
        if url:
            urls[oid] = url
    return urls


def _normalize_construction_worker_names(value):
    """Return display-ready construction worker names from legacy or ERP payloads."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or '').replace('\n', ',').split(',')

    workers = []
    for item in raw_values:
        if isinstance(item, dict):
            raw_name = item.get('name') or item.get('text') or item.get('value') or ''
        else:
            raw_name = item
        name = str(raw_name or '').strip()
        if name and name not in workers:
            workers.append(name)
    return workers


def _parse_iso_date(value: Any) -> datetime.date | None:
    """Parse a ``YYYY-MM-DD`` string to a ``date`` (leniently), else return None.

    Args:
        value: 문자열/None (앞 10자를 ISO date 로 해석).

    Returns:
        파싱된 date 또는 파싱 실패/빈 값이면 None.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def _as_visit_dday(as_visit_date: Any, today: datetime.date) -> int | None:
    """Return integer D-day (visit - today) for a ``YYYY-MM-DD`` visit date, else None.

    Args:
        as_visit_date: AS 방문일 문자열(YYYY-MM-DD) 또는 None.
        today: 기준일(get_today_kst() 반환값, KST date).

    Returns:
        방문일까지 남은 일수(음수=지남). 방문일 미설정/파싱 실패면 None.
    """
    visit = _parse_iso_date(as_visit_date)
    if visit is None:
        return None
    return (visit - today).days


def _compare_photo_entry(attachment: OrderAttachment) -> dict[str, str] | None:
    """Return ``{thumb, full, name}`` for an image AS attachment, else None.

    썸네일 키가 있으면 그리드 <img> 용 thumb 로, 전체 이미지 view_url 은 full(뷰어)로 쓴다.
    이미지가 아니면(문서/영상) None → 대조 그리드에서 제외.

    Args:
        attachment: AS 카테고리 OrderAttachment 1건.

    Returns:
        {thumb, full, name} 매핑 또는 이미지가 아니면 None.
    """
    storage_key = (attachment.storage_key or "").strip()
    if not storage_key:
        return None
    is_image = (attachment.file_type or "").strip().lower() == "image" or _is_image_filename(
        attachment.filename
    )
    if not is_image:
        return None
    full_url = build_file_view_url(storage_key)
    thumb_key = (attachment.thumbnail_key or "").strip()
    thumb_url = build_file_view_url(thumb_key) if thumb_key else full_url
    return {"thumb": thumb_url, "full": full_url, "name": (attachment.filename or "AS 사진")}


def batch_resolve_as_compare_photos(rows, db: Any) -> dict[int, dict[str, list]]:
    """주문별 AS 전/후(before/after) 사진 리스트를 배치 해석 (태블릿 대조 표면용).

    AS 사진에는 전/후 구분 스키마가 없다(``OrderAttachment.category == 'as'`` 만 존재).
    따라서 "가능한 데이터"로 매핑한다: AS 이미지 첨부를 ``created_at`` 기준으로
    ``Order.as_completed_date`` 이전이면 '접수 시'(before), 완료일 당일/이후면 '조치 후'(after)로
    나눈다. 완료일이 없으면(미완료 건) 전량 before, after 는 빈 리스트(→ placeholder). 단일
    ``in_()`` 쿼리로 페이지 전체를 해석해 N+1 을 만들지 않는다(batch_resolve_as_thumbnail_urls 정합).

    Args:
        rows: 현재 페이지 Order 리스트(각 ``as_completed_date`` 보유).
        db: SQLAlchemy 세션.

    Returns:
        ``{order_id: {'before': [ {thumb, full, name} ], 'after': [ ... ] }}``.
    """
    order_ids = [r.id for r in rows]
    result: dict[int, dict[str, list]] = {
        oid: {"before": [], "after": []} for oid in order_ids
    }
    if not order_ids:
        return result
    completed_map = {
        r.id: _parse_iso_date(getattr(r, "as_completed_date", None)) for r in rows
    }
    attachments = (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == "as",
        )
        .order_by(OrderAttachment.order_id.asc(), OrderAttachment.created_at.asc())
        .all()
    )
    for attachment in attachments:
        entry = _compare_photo_entry(attachment)
        if entry is None:
            continue
        bucket = result.get(int(attachment.order_id))
        if bucket is None:
            continue
        completed = completed_map.get(int(attachment.order_id))
        created = attachment.created_at.date() if attachment.created_at else None
        if completed is not None and created is not None and created >= completed:
            bucket["after"].append(entry)
        else:
            bucket["before"].append(entry)
    return result


_AS_BILLING_TYPE_LABELS = {'free': '무상', 'paid': '유상', 'undecided': '미정'}


def as_billing_badge_kind(billing: Any) -> str | None:
    """상태 셀 billing 배지 종류. 무상(확정 여부 무관)은 None(무배지).

    목록 렌더와 판정 변경 API 응답이 같은 배지를 그리도록 공개 SSOT다.

    Args:
        billing: ``structured_data.shipment.as_billing`` 값(비 dict면 무상 취급).

    Returns:
        'paid' | 'paid_unconfirmed' | 'undecided' | None.
    """
    b = billing if isinstance(billing, dict) else {}
    btype = str(b.get('type') or 'free').lower()
    if btype == 'paid':
        return 'paid' if b.get('confirmed') is True else 'paid_unconfirmed'
    if btype == 'undecided':
        return 'undecided'
    return None


def as_billing_state_text(billing: Any) -> str:
    """타임라인 헤더의 현재 판정 1줄 표기(서버 렌더와 판정 변경 응답 공용 SSOT).

    Args:
        billing: ``structured_data.shipment.as_billing`` 값(비 dict면 무상 추정).

    Returns:
        '유상 확정 · 150,000원' / '무상 추정' / '미정' 형태의 표기.
    """
    b = billing if isinstance(billing, dict) else {}
    btype = str(b.get('type') or 'free').lower()
    if btype == 'undecided':
        return '미정'
    text = "%s %s" % (
        _AS_BILLING_TYPE_LABELS.get(btype, btype),
        '확정' if b.get('confirmed') is True else '추정',
    )
    amount = b.get('amount')
    if btype == 'paid' and isinstance(amount, int) and amount > 0:
        text = f"{text} · {amount:,}원"
    return text


def _timeline_cell_text(entry: dict[str, Any] | None) -> str:
    """타임라인 항목 → PC 셀 요약용 1줄 plain text.

    템플릿 `striptags`는 태그를 지우기만 해 블록 경계를 잃는다 —
    `<div>1줄</div><div>2줄</div>`이 "1줄2줄"로 붙어 서로 다른 기록이 한 단어가 됐다.
    항목 `text`는 저장 시점에 이미 sanitize를 통과했으므로 재-sanitize 없이 텍스트화한다.

    Args:
        entry: decorate_entry를 통과한 타임라인 항목 dict. None이면 빈 문자열.

    Returns:
        블록 경계가 공백으로 보존된 1줄 텍스트(셀은 text-truncate 1줄 표시).
    """
    if not entry:
        return ''
    return as_content_html_to_text(entry.get('text'), already_sanitized=True).replace('\n', ' ')


def apply_timeline_cell_text(view: dict[str, Any]) -> None:
    """타임라인 뷰에 PC 셀 요약 텍스트 2종(앵커·최근 1건)을 in-place로 채운다.

    행 루프에서 1회만 계산해 템플릿이 그대로 소비한다(hot path 재파싱 금지).

    Args:
        view: build_as_timeline_view 결과 dict.
    """
    anchor = view['reception'] or (view['legacy'][0] if view['legacy'] else None)
    view['cell_anchor_text'] = _timeline_cell_text(anchor)
    view['cell_recent_text'] = _timeline_cell_text(view['stream'][0] if view['stream'] else None)


_DRIFT_WARN_STATES = ("ref_moved", "both_moved")
# 배너 점프 칩 상한. 100행 페이지 전부가 드리프트면 칩 벽이 목록을 밀어내므로 접는다 —
# 접었을 때는 반드시 "외 N건"을 함께 낸다(조용한 절단은 지금의 숫자만 있는 배너보다 나쁘다).
_DRIFT_BANNER_CHIP_LIMIT = 5


def _collect_schedule_link_ref_ids(rows) -> set[int]:
    """행들의 schedule_link 가 참조하는 기준 주문 id 집합을 모은다(중복 제거).

    Args:
        rows: structured_data 가 이미 dict 로 정규화된 Order 리스트.

    Returns:
        ref_order_id 집합(링크 없거나 형식이 이상하면 제외).
    """
    ref_ids: set[int] = set()
    for r in rows:
        link = read_link(r.structured_data)
        ref_id = link.get("ref_order_id") if link else None
        if isinstance(ref_id, int):
            ref_ids.add(ref_id)
    return ref_ids


def _batch_load_ref_schedule_snapshot(ref_ids: set[int], db: Any) -> dict[int, dict[str, Any]]:
    """기준 주문들의 현재 시공일 스냅샷을 단일 in_() 쿼리로 배치 조회 (N+1 금지).

    JSONB 필터 없이 `id, status, deleted_at, erp_construction_date, scheduled_date,
    customer_name` 6개 컬럼만 읽는다(스펙 §3.3·§8 — 무인덱스 JSONB 스캔 금지).
    customer_name 은 배지 표시용(UI 개선: id 대신 고객명 노출) — 별도 쿼리를 만들지 않고
    이미 열려 있는 배치 조회에 컬럼만 추가한다.

    Args:
        ref_ids: 조회할 기준 주문 id 집합.
        db: SQLAlchemy 세션.

    Returns:
        ``{ref_order_id: {"current_date": str|None, "missing": bool,
        "customer_name": str|None}}``. missing=True 는 DELETED 상태이거나
        soft-delete(``deleted_at`` 존재)된 경우. 결과에 없는 id 는 호출측이
        "조회 불가(orphan)"로 처리한다.
    """
    if not ref_ids:
        return {}
    query_rows = (
        db.query(
            Order.id,
            Order.status,
            Order.deleted_at,
            Order.erp_construction_date,
            Order.scheduled_date,
            Order.customer_name,
        )
        .filter(Order.id.in_(ref_ids))
        .all()
    )
    snapshot: dict[int, dict[str, Any]] = {}
    for oid, status, deleted_at, erp_date, sched_date, customer_name in query_rows:
        missing = bool(deleted_at) or str(status or "") == "DELETED"
        snapshot[int(oid)] = {
            "current_date": erp_date or sched_date or None,
            "missing": missing,
            "customer_name": customer_name or None,
        }
    return snapshot


def _short_md(iso_date: Any) -> str:
    """'YYYY-MM-DD' → 'M/D'(0 패딩 없음). 파싱 실패/None 이면 빈 문자열."""
    parsed = _parse_iso_date(iso_date)
    return f"{parsed.month}/{parsed.day}" if parsed else ""


def _ref_label(ref_id: Any, customer_name: Any) -> str:
    """드리프트 배지의 기준 주문 표시명 — 고객명이 있으면 이름, 없으면 '#id' 폴백.

    UI 피드백: id 만 보여주면("기준 #4348") 어떤 주문인지 알아보려면 클릭해 열어야
    했다. 이름이 비어있거나 기준 주문을 못 찾은 경우(고아 링크)엔 이름이 아예 없으므로
    옛 id 표기로 안전하게 폴백해 "기준  8/7" 같은 빈칸을 내지 않는다.

    Args:
        ref_id: 기준 주문 id.
        customer_name: 배치 스냅샷에서 읽은 기준 주문 고객명(없으면 None/빈 문자열).

    Returns:
        고객명(공백 trim) 또는 ``#<id>``.
    """
    name = str(customer_name or "").strip()
    return name if name else f"#{ref_id}"


def _evaluate_link_drift(link, ref_snapshot: dict[int, dict[str, Any]], as_visit_date: Any) -> dict:
    """링크 + 기준 주문 스냅샷 → 표시 필드까지 채운 드리프트 dict (목록·주문 상세 공용 SSOT).

    목록(행 배지)과 주문 상세(상단 배너)가 같은 판정·같은 표기를 내도록 여기 한 곳만
    거친다 — 기준일 해석(erp_construction_date → scheduled_date)과 삭제 판정은
    `_batch_load_ref_schedule_snapshot` 이, 상태 판정은 `evaluate_drift` 가 소유한다.

    Args:
        link: `read_link(sd)` 결과(없으면 None → 상태 `none`).
        ref_snapshot: `_batch_load_ref_schedule_snapshot` 결과(해당 ref 가 없어도 됨).
        as_visit_date: 이 AS 건의 현재 방문일(Da).

    Returns:
        `evaluate_drift` 결과 + 표시 전용 파생 필드
        (`ref_customer_name`/`ref_label`/`ref_date_md`/`ref_current_date_md`).
    """
    ref_info = ref_snapshot.get(link.get("ref_order_id")) if link else None
    drift = evaluate_drift(
        link,
        ref_current_date=(ref_info or {}).get("current_date"),
        as_visit_date=as_visit_date,
        ref_missing=bool(link) and (ref_info is None or bool(ref_info.get("missing"))),
    )
    # 배지 렌더용 표시 필드(매크로가 조립) — id 는 ref_order_id 로 그대로 유지된다
    # (액션 버튼·테스트가 소비하는 값이라 표시만 이름으로 바꾸고 데이터는 안 건드린다).
    drift["ref_customer_name"] = (ref_info or {}).get("customer_name") if link else None
    drift["ref_label"] = _ref_label(drift.get("ref_order_id"), drift.get("ref_customer_name"))
    drift["ref_date_md"] = _short_md(drift.get("ref_date"))
    drift["ref_current_date_md"] = _short_md(drift.get("ref_current_date"))
    return drift


def build_schedule_link_drift(structured_data: Any, db: Any) -> dict:
    """단건 주문의 기준 일정 드리프트 (주문 상세 최상단 배너용).

    목록 경로(`apply_schedule_link_drift_fields`)와 동일한 배치 스냅샷·판정 함수를 쓴다 —
    기준일 해석/삭제 판정을 여기서 다시 구현하지 않는다. 링크가 없으면 DB 조회 자체를
    하지 않으므로 AS 가 아닌 주문 상세에는 쿼리 비용이 0이다.

    Args:
        structured_data: 주문 structured_data(dict 가 아니면 링크 없음으로 취급).
        db: SQLAlchemy 세션.

    Returns:
        `_evaluate_link_drift` 결과. 링크가 없으면 `state == 'none'`(템플릿이 렌더 생략).
    """
    sd = _ensure_dict(structured_data) or {}
    link = read_link(sd) if isinstance(sd, dict) else None
    ref_id = link.get("ref_order_id") if link else None
    ref_snapshot = (
        _batch_load_ref_schedule_snapshot({ref_id}, db) if isinstance(ref_id, int) else {}
    )
    return _evaluate_link_drift(link, ref_snapshot, read_as_visit_date(sd))


def _drift_banner_chip(row: Any, drift: dict) -> dict[str, Any]:
    """경고 상태 행 1건 → 배너 점프 칩 데이터(고객명 · id · 옛 기준일 → 새 기준일).

    칩이 부르는 이름은 **그 AS 건 자신의 고객명**이다(기준 주문 고객명이 아니다) —
    배너는 "어느 AS 를 손봐야 하나"를 답해야 하고, 목록에서 눈으로 찾는 단서도 AS 행의
    고객명이다. 기준 주문 쪽 표기는 행 배지(`ref_label`)가 이미 담당한다.

    Args:
        row: 현재 페이지 Order(고객명·id 소유).
        drift: `_evaluate_link_drift` 결과(M/D 표시 파생 필드 포함).

    Returns:
        템플릿이 그대로 배치하는 dict — `order_id`/`customer_name`/`old_md`/`new_md`/`state`.
        고객명이 비어 있으면 빈 문자열(템플릿이 `#id` 만 낸다).
    """
    return {
        "order_id": int(row.id),
        "customer_name": str(getattr(row, "customer_name", "") or "").strip(),
        "old_md": drift.get("ref_date_md") or "",
        "new_md": drift.get("ref_current_date_md") or "",
        "state": drift.get("state"),
    }


def apply_schedule_link_drift_fields(rows, db: Any) -> dict[str, Any]:
    """행마다 `schedule_link_drift` 를 부착하고, 상단 배너용 요약을 반환한다.

    렌더된 행 집합에 한정해 기준 주문을 `in_()` 1회 배치 조회한다(전체 미완료 AS
    스캔 없음 — 스펙 §8). 읽기 전용: DB write 없음(`resolved` 자동 갱신은 여기서 하지 않는다).
    배너 칩(누가 영향받았나)도 **이 한 번의 루프**에서 함께 모은다 — 재평가·재조회 없음.

    Args:
        rows: structured_data 가 이미 dict 로 정규화되고 `as_visit_date` 가 채워진
            Order 리스트(`apply_erp_display_fields_to_orders` 이후 호출 전제).
        db: SQLAlchemy 세션.

    Returns:
        `{"count": 경고 행 총수, "chips": 상한(_DRIFT_BANNER_CHIP_LIMIT)까지의 칩 리스트,
        "overflow": 칩으로 못 낸 나머지 건수}`. 경고가 없으면 count=0(템플릿이 배너 생략).
    """
    ref_ids = _collect_schedule_link_ref_ids(rows)
    ref_snapshot = _batch_load_ref_schedule_snapshot(ref_ids, db)
    chips: list[dict[str, Any]] = []
    for r in rows:
        drift = _evaluate_link_drift(
            read_link(r.structured_data), ref_snapshot, getattr(r, "as_visit_date", None)
        )
        r.schedule_link_drift = drift
        if drift["state"] in _DRIFT_WARN_STATES:
            chips.append(_drift_banner_chip(r, drift))
    return {
        "count": len(chips),
        "chips": chips[:_DRIFT_BANNER_CHIP_LIMIT],
        "overflow": max(len(chips) - _DRIFT_BANNER_CHIP_LIMIT, 0),
    }


def apply_as_dashboard_row_display_fields(rows, db, *, mobile_v2_active):
    """AS 대시보드 rows에 표시 필드를 in-place 보강 (구 erp_as_dashboard 표시 블록). 동작 보존.

    structured_data 정규화 + ERP 표시 필드 + AS 사진 보유/대기/도면/영업택배 플래그 +
    시공자 목록 + AS 내용 HTML(+notes 폴백) + 썸네일 + 단계 배지 + 기준 일정 드리프트를
    채운다. 캐시 아님. batch_resolve_as_thumbnail_urls / as_thumb_enabled 동작은
    변경하지 않는다.

    Args:
        rows: 현재 페이지 Order 객체 리스트.
        db: SQLAlchemy 세션.
        mobile_v2_active: ERP mobile v2 cohort 활성 여부(썸네일 게이트).

    Returns:
        상단 배너 요약 dict(`apply_schedule_link_drift_fields` 반환값 그대로 —
        `count`/`chips`/`overflow`). 단건 렌더 호출부(카드 상세·타임라인 fragment)는
        배너를 그리지 않으므로 이 값을 버려도 된다.
    """
    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]
    apply_erp_display_fields_to_orders(rows)
    # AS 카테고리 첨부가 있는 주문 ID 집합 (버튼 색상: 있음=파란색, 없음=분홍 파스텔)
    order_ids = [r.id for r in rows]
    as_photo_order_ids = set()
    if order_ids:
        as_with_photos = db.query(OrderAttachment.order_id).filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == 'as'
        ).distinct().all()
        as_photo_order_ids = {x[0] for x in as_with_photos}
    thumb_flag = as_thumb_enabled(mobile_v2_active=mobile_v2_active)
    thumb_urls = batch_resolve_as_thumbnail_urls(order_ids, db) if order_ids else {}
    # 태블릿 가로 대조 표면(전/후 사진)은 코호트(v2/v3)에서만 렌더 → 코호트일 때만 추가 배치 쿼리.
    compare_photos = (
        batch_resolve_as_compare_photos(rows, db)
        if (mobile_v2_active and order_ids)
        else {}
    )
    _today = get_today_kst()
    for r in rows:
        r.has_as_photos = r.id in as_photo_order_ids
        shipment = r.structured_data.get('shipment') or {}
        r.as_pending = shipment.get('as_pending') is True
        _billing = shipment.get('as_billing')
        r.as_billing_badge = as_billing_badge_kind(_billing)
        # 타임라인 헤더(판정 표시 + 변경 버튼)용. 목록엔 안 쓰이지만 세 표면이 같은 행 보강을
        # 거치므로 여기서 한 번만 계산한다(문자열 조립뿐, 신규 쿼리 0).
        r.as_billing_type = str((_billing or {}).get('type') or 'free') if isinstance(_billing, dict) else 'free'
        r.as_billing_state_text = as_billing_state_text(_billing)
        r.has_as_blueprint = shipment.get('as_blueprint') is True
        r.is_sales_delivery = shipment.get('sales_delivery') is True
        r.construction_workers = _normalize_construction_worker_names(
            shipment.get('construction_workers')
        )
        r.construction_workers_text = ', '.join(r.construction_workers)
        # as_content_html은 태블릿 가로 대조 표면(tablet_as_compare_body)이 소비하므로 유지한다.
        # T10: 2번 탭 표시필드(as_content_2_html)와 그 notes 폴백은 퇴역했다 — 탭 에디터가 사라져
        # 소비자가 0이고, 비고는 타임라인 확장/상세의 읽기 전용 '비고' 블록이 직접 렌더한다.
        r.as_content_html = sanitize_as_content_html(shipment.get('as_content'))
        # 타임라인 뷰(셀 요약·확장 fragment 공용). 방금 정리한 두 값을 주입해
        # legacy 앵커용 재-sanitize(행당 BeautifulSoup 파싱 2회)를 없앤다.
        r.as_timeline_view = build_as_timeline_view(
            r.structured_data,
            sanitized=(r.as_content_html, sanitize_as_content_html(shipment.get('as_content_2'))),
        )
        apply_timeline_cell_text(r.as_timeline_view)
        r.as_thumb_enabled = thumb_flag
        r.thumbnail_url = thumb_urls.get(r.id) if thumb_flag else None
        r.stage_badge_modifier = as_stage_badge_modifier(
            status=str(r.status or ""),
            as_pending=bool(r.as_pending),
        )
        r.as_visit_dday = _as_visit_dday(getattr(r, "as_visit_date", None), _today)
        # 방문 시각(태블릿 대조 표면 방문 블록용) — 이미 로드된 structured_data 재소비(신규 쿼리 0).
        # api_as_schedule 가 schedule.as_visit.time 에 저장한다(HH:MM 문자열). 없으면 빈 문자열.
        _schedule = r.structured_data.get("schedule") or {}
        _as_visit_meta = (_schedule.get("as_visit") or {}) if isinstance(_schedule, dict) else {}
        r.as_visit_time = str(_as_visit_meta.get("time") or "").strip()
        _cmp = compare_photos.get(r.id) or {"before": [], "after": []}
        r.as_before_photos = _cmp["before"]
        r.as_after_photos = _cmp["after"]
    return apply_schedule_link_drift_fields(rows, db)
