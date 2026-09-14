"""네이버 수집분 ↔ ERP 주문 대조 — 질의와 화면 뷰 (GAP-01).

네이버 HTTP 를 내지 않는다(WORKER 단일 출구 계약). DB 만 읽는다 —
``client`` 모듈을 import 하지 않는다.

이 모듈이 답하는 질문은 하나다: "네이버에서 돈이 들어왔는데 ERP 에 주문이
안 만들어진 건이 있나?"

SQL 은 모집단 좁히기와 스칼라 투영만 하고, **분류는**
:mod:`foms.services.integrations.naver_commerce.order_gap_rules` 의 순수
함수가 한다. 판정에 쓰는 다섯 스칼라 중 주문 상태·클레임 상태·결제 금액은
``external_order_links`` 의 **사본 컬럼**(NVMIRROR-01)에서 먼저 읽는다. 그
컬럼은 뜨거운 경로가 ``raw_snapshot``(JSONB) 을 detoast 하지 않게 하려고
만들어 둔 것이라 여기서도 그걸 먼저 본다. 사본이 비어 있는 옛 행에서만
스냅샷으로 떨어지고, 그 JSON 은 중첩·평평 두 모양으로 오므로 둘 다 본다
(``mapping.unwrap_detail``·``claim_watch`` 의 SQL 투영과 같은 규약).
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, Integer

from foms.services.datetime_kst import format_datetime_kst
from foms.services.integrations.naver_commerce.claim_watch import STATE_KEY
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import CLAIM_STATUS_LABELS
from foms.services.integrations.naver_commerce.order_gap_rules import (
    CLOSED_ORDER_STATUSES,
    EXTRA_PRODUCT_NAMES,
    GAP_ATTACHABLE,
    GAP_BUCKETS,
    GAP_CLOSED,
    GAP_EXTRA,
    GAP_LABELS,
    GAP_MISSING,
    GAP_PAGE_SIZE,
    _PHONE_CHUNK,
    GAP_ROW_KEYS,
    GAP_SCAN_CAP,
    GAP_UNDECIDED,
    MAIN_PRODUCT_CLASSES,
    _chunks,
    _text,
    _to_int,
    classify_gap_row,
    mask_name,
)
from models import ExternalOrderLink, Order

#: 재수출 — 라우트·템플릿·테스트가 이 모듈 하나만 보면 되게 한다.
__all__ = [
    "GAP_ATTACHABLE", "GAP_BUCKETS", "GAP_CLOSED", "GAP_EXTRA", "GAP_LABELS",
    "GAP_MISSING", "GAP_PAGE_SIZE", "GAP_ROW_KEYS", "GAP_SCAN_CAP",
    "GAP_UNDECIDED", "build_order_gap_view", "classify_gap_row",
    "list_order_gap", "mask_name", "summarize_order_gap",
]



# --------------------------------------------------------------------------- #
# raw_snapshot 투영식
# --------------------------------------------------------------------------- #

_PO = ExternalOrderLink.raw_snapshot["productOrder"]
_ROOT = ExternalOrderLink.raw_snapshot
_ORD = ExternalOrderLink.raw_snapshot["order"]


def _pair(key: str):
    """중첩(``productOrder.<key>``) → 평평(``<key>``) 순으로 첫 값.

    ``mapping.unwrap_detail`` 과 같은 규약이다. 한 모양만 읽으면 조용히 0건이
    된다(``claim_watch`` 가 SQL 에서 같은 일을 한다).
    """
    return func.coalesce(func.nullif(_PO[key].as_string(), ""),
                         func.nullif(_ROOT[key].as_string(), ""))


PROJ_PRODUCT_CLASS = _pair("productClass")
PROJ_PRODUCT_NAME = _pair("productName")
# 사본 컬럼(NVMIRROR-01) 우선. 뜨거운 경로가 JSONB 를 detoast 하지 않게 두려고
# 만들어 둔 컬럼이라 여기서도 그걸 먼저 읽는다. 비어 있는 옛 행만 스냅샷으로 떨어진다.
PROJ_ORDER_STATUS = func.coalesce(
    func.nullif(ExternalOrderLink.product_order_status, ""),
    _pair("productOrderStatus"),
)
PROJ_AMOUNT = func.coalesce(
    ExternalOrderLink.payment_amount,
    func.cast(_pair("totalPaymentAmount"), Integer),
)

# 클레임은 네 자리를 본다. ``nullif`` 없이 ``coalesce`` 하면 **빈 문자열이
# 이겨서** 뒤 후보를 영영 못 본다 — "claimStatus 는 NULL 이 아니라 빈 문자열"
# 함정의 진짜 모양이다.
PROJ_CLAIM_STATUS = func.coalesce(
    func.nullif(ExternalOrderLink.claim_status, ""),
    func.nullif(_PO["claimStatus"].as_string(), ""),
    func.nullif(_ROOT["claimStatus"].as_string(), ""),
    func.nullif(_ORD["claimStatus"].as_string(), ""),
    func.nullif(
        ExternalOrderLink.triage_state[STATE_KEY]["last_status"].as_string(), ""),
)




# --------------------------------------------------------------------------- #
# DB 읽기
# --------------------------------------------------------------------------- #

def _scan_links(db) -> list[Any]:
    """미연결 수집분을 최신순으로 훑는다 — 쿼리 1회.

    ``raw_snapshot`` 을 통째로 끌어오지 않는다. 1,900행 × 수 KB = 수십 MB 다
    (``claim_watch`` 가 같은 이유로 스칼라 투영을 쓴다).

    **인덱스 사실.** ``order_id IS NULL`` 부분 인덱스 3벌이 있다
    (``ix_external_order_link_match_recipient_phone`` 등, models.py:3618-3625 —
    ``(channel, recipient_phone_digits) WHERE order_id IS NULL``). 이 질의는
    그 인덱스를 **탈 수 있지만 보장되지 않는다**: ``ORDER BY id DESC`` 가
    붙어 플래너가 다른 경로를 고를 수 있고, 그때는 ``external_order_links``
    전체 Seq Scan 이다. 이번에 새 인덱스를 만들지 않는다 — ① 관리자 전용 탭
    진입 시에만 돈다 ② 모집단이 작다(운영 미연결 1,899행) ③ ``LIMIT`` 이
    걸려 있다. 나중에 느려지면 **여기가 첫 자리다.**

    ``sync_status`` 는 투영만 하고 분류 축으로 쓰지 않는다. ``order_id`` 는
    주문을 하드 삭제하면 ``SET NULL`` 이 되므로(models.py 의 ``ondelete``),
    ``LINKED`` 인데 ``order_id`` 가 빈 행이 이론상 이 모집단에 섞인다. 실측
    시점 모집단은 전량 ``COLLECTED`` 라 오늘은 0건이다 — 하드 삭제가 실제로
    생기면 이 값을 축으로 올려 "한 번도 안 만든 건" 과 갈라야 한다.
    """
    return (
        db.query(
            ExternalOrderLink.id,
            ExternalOrderLink.external_order_no,
            ExternalOrderLink.created_at,
            ExternalOrderLink.sync_status,
            ExternalOrderLink.relation,
            ExternalOrderLink.recipient_name,
            ExternalOrderLink.recipient_phone_digits,
            PROJ_PRODUCT_CLASS, PROJ_PRODUCT_NAME,
            PROJ_ORDER_STATUS, PROJ_CLAIM_STATUS, PROJ_AMOUNT,
        )
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.order_id.is_(None))
        .order_by(ExternalOrderLink.id.desc())
        .limit(GAP_SCAN_CAP + 1)     # +1 = 상한에 닿았는지 알기 위한 한 행
        .all()
    )


def _erp_phone_hits(db, digits: Iterable[str]) -> set[str]:
    """주어진 전화 숫자열 중 **ERP 주문이 있는 것**만 돌려준다.

    · ``Order.erp_phone_digits`` 는 인덱스가 있다(models.py:108 ``index=True``).
    · ``active_including_trashed_filter()`` 를 쓴다(``active_filter()`` 아니다).
      "존재했다는 사실 자체가 근거인" 자리라고 models.py:176-185 가 명시하고,
      네이버 붙이기 후보(2026-09-07)가 같은 선택을 했다. 휴지통 주문을 빼면
      "주문 없음" 이 부풀어 오른다.
    · **이름 축은 쓰지 않는다.** ``Order.customer_name`` 에 인덱스가 없어
      ``in_()`` 이 Seq Scan 이 되고, 동명이인 오탐이 붙는다. 그래서 이 대조는
      전화 하나로만 짚는 **휴리스틱**이다 — 전화가 다르게 적힌 주문은 못
      찾고, 같은 고객의 다른 주문이 걸리면 붙일 짝이 아닌데도 잡힌다.
      화면이 "후보" 라고만 말하는 이유다.
    """
    wanted = sorted({d for d in (_text(x).strip() for x in digits) if d})
    found: set[str] = set()
    for chunk in _chunks(wanted, _PHONE_CHUNK):
        rows = (db.query(Order.erp_phone_digits)
                  .filter(Order.erp_phone_digits.in_(list(chunk)),
                          Order.active_including_trashed_filter())
                  .distinct()
                  .limit(len(chunk))
                  .all())
        found |= {_text(value) for (value,) in rows if value}
    return found


def _row_fields(row: Any) -> dict:
    """스캔 행 → :func:`classify_gap_row` 가 받는 dict."""
    return {
        "product_class": _text(row[7]),
        "product_name": _text(row[8]),
        "order_status": _text(row[9]),
        "claim_status": _text(row[10]),
        "amount": row[11],
        "relation": _text(row[4]),
        "phone_digits": _text(row[6]),
    }


def _row_dict(row: Any, fields: dict, bucket: str) -> dict:
    """화면에 내는 행 dict.

    **개인정보 절대 규칙**: ``recipient_phone_digits``·``orderer_phone_digits``·
    주소·``raw_snapshot`` 원문을 넣지 않는다. 전화는 판정에만 쓰고 버린다.
    이름은 항상 :func:`mask_name` 을 거친다 — 원문이 이 dict 를 떠나면 안 된다.
    """
    claim_status = _text(fields.get("claim_status")).strip()
    claim_label = ""
    if claim_status:
        claim_label = CLAIM_STATUS_LABELS.get(claim_status.upper(), claim_status)
    return {
        "link_id": int(row[0]),
        "external_order_no": _text(row[1]),
        "collected_date": format_datetime_kst(row[2], "%Y-%m-%d") or "",
        "product_name": _text(fields.get("product_name")),
        "payment_amount": _to_int(fields.get("amount")),
        "recipient_name_masked": mask_name(row[5]),
        "naver_status": _text(fields.get("order_status")),
        "claim_label": claim_label,
        "bucket": bucket,
    }


def _normalize_bucket(bucket: Any) -> str:
    """주소를 손으로 고쳐도 화면이 안 죽게, 모르는 값은 ``missing`` 으로."""
    text = _text(bucket).strip()
    return text if text in GAP_BUCKETS else GAP_MISSING


def _normalize_int(value: Any) -> int:
    """음수·정수 아닌 값은 0 으로 떨어뜨린다."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


# --------------------------------------------------------------------------- #
# 공개 API
# --------------------------------------------------------------------------- #

def build_order_gap_view(db, *, bucket: str = GAP_MISSING,
                         limit: int = GAP_PAGE_SIZE,
                         offset: int = 0) -> dict:
    """대조 화면이 쓰는 **단일 진입점** — 스캔 1회로 집계와 목록을 함께 낸다.

    쿼리 예산: 모집단 1회 + ``ceil(고유 전화수/500)`` 회. 고유 전화수는 아직
    재 본 적이 없다 — 미연결 1,899행 기준으로 2회에서 5회 사이다. "항상 2회" 로
    읽지 마라.

    Args:
        db: SQLAlchemy 세션.
        bucket: 목록으로 볼 칸. :data:`GAP_BUCKETS` 밖이면 :data:`GAP_MISSING`.
        limit: 목록 길이. ``0`` 이면 집계만 돌고 ``rows`` 는 빈 목록이다.
        offset: 목록 시작 위치.

    Returns:
        ::

            {
              "buckets": {              # GAP_BUCKETS 전수. 비어도 칸은 남는다.
                 "<bucket>": {"count": int, "amount": int,
                              "label": str, "note": str},
                 ...
              },
              "total": int,             # 분류된 행 수 == 버킷 count 합
              "scanned": int,           # 실제로 읽은 행 수
              "truncated": bool,        # GAP_SCAN_CAP 에 닿았나
              "cap": int,               # GAP_SCAN_CAP
              "bucket": str,            # 지금 보는 칸(정규화된 값)
              "rows": list[dict],       # GAP_ROW_KEYS 가 전수다
              "offset": int, "limit": int, "has_more": bool,
            }
    """
    view_bucket = _normalize_bucket(bucket)
    page_limit = _normalize_int(limit)
    page_offset = _normalize_int(offset)

    scanned_rows = _scan_links(db)
    truncated = len(scanned_rows) > GAP_SCAN_CAP
    if truncated:
        scanned_rows = scanned_rows[:GAP_SCAN_CAP]

    phone_hits = _erp_phone_hits(db, (row[6] for row in scanned_rows))

    buckets = {
        name: {
            "count": 0,
            "amount": 0,
            "label": GAP_LABELS[name]["label"],
            "note": GAP_LABELS[name]["note"],
        }
        for name in GAP_BUCKETS
    }

    total = 0
    selected: list[tuple[Any, dict]] = []
    for row in scanned_rows:
        fields = _row_fields(row)
        phone = fields["phone_digits"].strip()
        name = classify_gap_row(
            fields, has_erp_order=bool(phone) and phone in phone_hits)
        buckets[name]["count"] += 1
        buckets[name]["amount"] += _to_int(fields.get("amount"))
        total += 1
        if name == view_bucket:
            selected.append((row, fields))

    page: list[dict] = []
    has_more = False
    if page_limit:
        window = selected[page_offset:page_offset + page_limit]
        page = [_row_dict(row, fields, view_bucket) for row, fields in window]
        has_more = len(selected) > page_offset + page_limit

    return {
        "buckets": buckets,
        "total": total,
        "scanned": len(scanned_rows),
        "truncated": truncated,
        "cap": GAP_SCAN_CAP,
        "bucket": view_bucket,
        "rows": page,
        "offset": page_offset,
        "limit": page_limit,
        "has_more": has_more,
    }


def summarize_order_gap(db) -> dict:
    """집계만. :func:`build_order_gap_view` 의 ``limit=0`` 래퍼다."""
    return build_order_gap_view(db, limit=0)


def list_order_gap(db, *, bucket: str, limit: int = GAP_PAGE_SIZE,
                   offset: int = 0) -> list[dict]:
    """행 목록만. ``build_order_gap_view(...)["rows"]`` 의 얇은 래퍼다."""
    return build_order_gap_view(db, bucket=bucket, limit=limit,
                                offset=offset)["rows"]


__all__ = [
    "GAP_ATTACHABLE",
    "GAP_BUCKETS",
    "GAP_CLOSED",
    "GAP_EXTRA",
    "GAP_LABELS",
    "GAP_MISSING",
    "GAP_PAGE_SIZE",
    "GAP_ROW_KEYS",
    "GAP_SCAN_CAP",
    "GAP_UNDECIDED",
    "build_order_gap_view",
    "classify_gap_row",
    "list_order_gap",
    "mask_name",
    "summarize_order_gap",
]
