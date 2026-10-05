"""네이버 작업대 **처리 목록**용 축소 스냅샷 (P2-2 ④, 2026-10-02).

처리 탭 목록(:func:`naver_ingest._work_groups` 의 ``display=True``)은 링크 행을
``raw_snapshot`` 째 읽었다 — 2026-10-02 스테이징 1,241행에 출력 5.5MB 였고, 목록이 실제로
읽는 것은 그 절반이 안 된다(``completedClaims``·``takingAddress``·정산 수수료 필드 수십 개는
어떤 목록 함수도 안 읽는다). 여기서는 **목록 판정·표시가 읽는 경로만** 남긴 문서를 SQL 이
조립하게 한다.

규율은 nav 뱃지의 얇은 투영(``naver_ingest._snapshot_projection``)과 같다 — 판정 함수를 두
벌로 만들지 않고 **입력만** 얇게 한다. 그리고 그보다 한 걸음 더 엄격하다. 남긴 경로 안에서는
원본과 **한 글자도** 다르지 않다:

- 남기는 키는 원본에 **있을 때만** 싣는다. 없는 키를 ``null`` 로 채우지 않는다
  (``in``·``_known_int`` 가 "없음"과 "null"을 가른다).
- dict 가 아닌 자리(``null``·배열·문자열)는 원본 그대로 둔다(``unwrap_detail`` 의 평평한
  응답 폴백이 그 모양으로 갈린다).
- 키 순서도 jsonb 정렬 순서(길이 → 바이트) 그대로 낸다 — 파이썬 dict 반복 순서까지 같다.

그래서 "목록 함수가 읽는 경로 ⊆ :data:`LIST_SNAPSHOT_SPEC`" 이기만 하면 목록 결과가 통째
문서와 같다. 그 포함 관계는 추적 계약 테스트(``test_naver_workbench_list_snapshot``)가
실제 목록 경로를 돌려 잡는다 — 새 함수가 여기 없는 경로를 읽으면 그 테스트가 빨개진다.

비용은 옮겨 간다(스테이징 1,241행 실측, 2026-10-02): 출력 5,531kB → 2,751kB, DB 실행
39 → 57ms(원본 풀기는 그대로고 조립이 직렬화보다 비싸다), 파이썬 쪽 JSON 디코드·행 생성은
약 70 → 35ms. 웹 프로세스(gevent)의 CPU 를 DB 쪽 대기로 바꾸는 거래다.

읽는 경로와 읽는 함수(``PO`` = ``unwrap_detail`` 의 상품주문, ``O`` = 주문,
``SH`` = 배송지 — 전부 :mod:`...naver_commerce.mapping`):

- ``O.orderId``·``SH.tel1``·``SH.baseAddress``·``SH.detailedAddress`` — ``group_key``
  (``household_key`` 의 집 키).
- ``SH.name``·``PO.productName``·``PO.productOption``·``PO.quantity``·
  ``PO.totalPaymentAmount``·``PO.productOrderId``·``O.orderDate`` — ``summarize_snapshot``·
  ``_coupon_facts``·``_link_payment_amount``.
- ``PO.appliedCoupons``·``PO.appliedCardPromotion``·``PO.unitPrice``·``PO.optionPrice``·
  ``PO.productDiscountAmount``·``PO.expectedSettlementAmount``·``O.paymentDate``·
  ``O.paymentMeans``·``O.payLocationType`` — ``build_payment_info``(쿠폰 요약).
- ``PO.claimStatus``·``PO.claimType``·``O.claimStatus`` + 클레임 블록 — ``extract_claim``.
- ``PO/O.holdbackStatus``·``PO/O.claimDeliveryFeePayMethod`` + 클레임 블록 —
  ``extract_claim_holdback``(승인·거부 가능 건수).
- ``PO.placeOrderStatus``·``O.placeOrderStatus``·``PO.placeOrderDate``·
  ``PO.shippingDueDate`` — ``extract_place_status``.
- ``delivery``·``PO.delivery``·``O.delivery`` — ``extract_delivery``(네이버 발송 신호).
- ``PO.productClass`` — ``is_addon_detail``(추가구성상품 범위 검사).
- ``PO.productOrderStatus``·최상위 ``productOrderStatus`` — ``fulfillment.is_purchase_decided``
  (사본 컬럼 ``product_order_status`` 가 비었을 때만).

클레임 블록(``cancel``·``returnInfo``·``return``·``exchange``·``currentClaim``·
``beforeClaim``)과 ``delivery``·``shippingAddress``·쿠폰 목록은 **통째로** 남긴다. 블록 안에서
어떤 키를 읽는지는 블록 이름·그릇마다 갈리고(``_claim_blocks``·``_cancel_blocks``·
``_return_blocks``·``extract_claim_holdback``), 2026-10-28 커머스API 공지 #3608 로 블록
모양이 또 바뀐다 — 블록 안까지 자르면 그날 목록만 "클레임 없음"으로 갈린다(R-7 재발).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy import case, cast, func, literal_column, select, true
from sqlalchemy.dialects.postgresql import JSON as PG_JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.util import ClauseAdapter

# 투영 조각은 정산 모집단(`foms.services.settlement_source`)과 같이 쓴다 — 서비스 계층이 이 웹
# 패키지를 import 하지 않게 공용 모듈로 옮겼다. 옛 이름은 그대로 남긴다.
from foms.services.common.jsonb_projection import (
    json_object_absent as _json_object_absent,
    jsonb_key_order as _jsonb_key_order,
    supports_sql_projection,
)
from foms.services.integrations.naver_commerce.mapping import CLAIM_BLOCK_KEYS, RETURN_BLOCK_KEYS
from models import ExternalOrderLink

#: 상품주문(``productOrder``)에서 남기는 키. 값은 통째로 싣는다(배송지·쿠폰 목록 포함).
LIST_PRODUCT_ORDER_KEYS = (
    "productOrderId", "productName", "productOption", "productClass", "productOrderStatus",
    "quantity", "totalPaymentAmount", "unitPrice", "optionPrice", "productDiscountAmount",
    "expectedSettlementAmount", "appliedCoupons", "appliedCardPromotion",
    "claimStatus", "claimType", "placeOrderStatus", "placeOrderDate", "shippingDueDate",
    "shippingAddress", "delivery", "holdbackStatus", "claimDeliveryFeePayMethod",
)

#: 주문(``order``)에서 남기는 키.
LIST_ORDER_KEYS = (
    "orderId", "orderDate", "paymentDate", "paymentMeans", "payLocationType", "claimStatus",
    "placeOrderStatus", "delivery", "holdbackStatus", "claimDeliveryFeePayMethod",
)

#: **통째로** 남기는 최상위 블록. 클레임 블록 이름은 mapping 에서 파생한다 — 손으로 적으면
#: 블록 이름이 늘 때 목록만 갈린다(nav 뱃지 투영이 2026-08-28 R-7 에서 겪은 결함).
LIST_ROOT_WHOLE_KEYS = tuple(dict.fromkeys(
    ("delivery", "shippingAddress")
    + tuple(CLAIM_BLOCK_KEYS) + tuple(RETURN_BLOCK_KEYS)
    + ("currentClaim", "beforeClaim")))

#: 투영 나무. 값이 ``None`` 이면 그 자리를 통째로, dict 면 그 키들만 남긴다.
#:
#: 최상위에 상품주문 키를 **한 번 더** 둔다 — ``productOrder`` 가 dict 가 아닌 평평한 응답은
#: ``unwrap_detail`` 이 원본 자체를 상품주문으로 읽기 때문이다. 중첩 응답에는 그 키들이 원래
#: 없으므로 실리는 것도 없다. ``is_purchase_decided`` 는 중첩 응답에서도 최상위
#: ``productOrderStatus`` 를 함께 본다(``nested or flat``) — 이 줄이 그 자리도 덮는다.
LIST_SNAPSHOT_SPEC: dict[str, Any] = {
    **dict.fromkeys(LIST_PRODUCT_ORDER_KEYS),
    **dict.fromkeys(LIST_ROOT_WHOLE_KEYS),
    "productOrder": dict.fromkeys(LIST_PRODUCT_ORDER_KEYS),
    "order": dict.fromkeys(LIST_ORDER_KEYS),
}

#: 목록 행이 싣는 컬럼. ``raw_snapshot`` 은 여기 없다 — 투영 문서가 마지막 자리에 붙는다.
#: 목록 함수가 읽는 속성 전부다(2026-10-02 스테이징 추적: 아래 12개 중 ``group_key`` 를 뺀
#: 11개 + ``raw_snapshot``). ``product_order_status`` 는 ``is_purchase_decided`` 가
#: ``getattr`` 기본값으로 읽어서, 빠져도 예외가 안 나고 **조용히 스냅샷 폴백**으로 간다 —
#: 그래서 명시적으로 싣는다.
LIST_COLUMNS = (
    ExternalOrderLink.id,
    ExternalOrderLink.external_id,
    ExternalOrderLink.external_order_no,
    ExternalOrderLink.order_id,
    ExternalOrderLink.sync_status,
    ExternalOrderLink.place_order_status,
    ExternalOrderLink.relation,
    ExternalOrderLink.group_key,
    ExternalOrderLink.created_at,
    ExternalOrderLink.triage_state,
    ExternalOrderLink.reviewed_at,
    ExternalOrderLink.product_order_status,
)

#: :class:`ListLink` 의 칸 — ``LIST_COLUMNS`` 순서 + 마지막 자리의 투영 문서.
_LIST_FIELDS = tuple(column.key for column in LIST_COLUMNS) + ("raw_snapshot",)

_KEY_PATTERN = re.compile(r"^[A-Za-z]+$")


class ListLink:
    """처리 목록용 **읽기 전용** 링크 행 — ``raw_snapshot`` 자리에 목록 투영 문서가 들어간다.

    ORM 인스턴스로 만들지 않는 이유는 nav 뱃지의 ``_ThinLink`` 와 같다(세션 식별자 지도):
    같은 요청의 pane 이 ``db.get`` 으로 같은 링크를 열 때 축소 문서가 섞여 들어가면 안 된다.
    평행 객체라 그 접점이 없다 — pane 은 언제나 자기 조회로 통째 원본을 읽는다.
    """

    __slots__ = _LIST_FIELDS

    def __init__(self, *values: Any):
        # ``self.__slots__`` 가 아니라 모듈 상수를 쓴다 — 하위 클래스(계약 테스트의 기록
        # 대역)는 자기 ``__slots__`` 가 비어 있다.
        for name, value in zip(_LIST_FIELDS, values, strict=True):
            setattr(self, name, value)


def project_list_snapshot(raw: Any, spec: Optional[dict[str, Any]] = None) -> Any:
    """원본 스냅샷을 :data:`LIST_SNAPSHOT_SPEC` 대로 줄인다 — SQL 투영의 **파이썬 정본**.

    SQLite 레인(투영 SQL 이 없다)과 PostgreSQL 16 미만에서는 이 함수가 투영을 맡고, PG 레인
    테스트는 SQL 결과가 이 함수 결과와 키 순서까지 같은지 못박는다.

    Args:
        raw: ``ExternalOrderLink.raw_snapshot`` (dict 가 아니면 그대로 돌려준다).
        spec: 투영 나무(기본 :data:`LIST_SNAPSHOT_SPEC`). 계약 테스트의 음성 대조군이
            경로 하나를 뺀 나무를 넘긴다.

    Returns:
        남기는 키만 담은 새 dict(원본 키 순서 유지). 남기는 값은 원본 객체를 그대로 쓴다.
    """
    return _project(raw, LIST_SNAPSHOT_SPEC if spec is None else spec)


def _project(value: Any, spec: Optional[dict[str, Any]]) -> Any:
    """:func:`project_list_snapshot` 의 재귀 본체(``spec`` 이 None 이면 통째)."""
    if spec is None or not isinstance(value, dict):
        return value
    return {key: _project(item, spec[key]) for key, item in value.items() if key in spec}


def _pick(doc: Any, spec: dict[str, Any], prepared: Optional[dict[str, Any]] = None) -> Any:
    """``doc`` 에서 ``spec`` 의 키만 담은 json 객체 식을 만든다.

    Args:
        doc: jsonb 식(dict 라는 것은 호출자가 보장한다).
        spec: 투영 나무의 한 마디.
        prepared: 이미 한 번 꺼내 둔 하위 문서(``productOrder``·``order``) — 키마다 다시
            꺼내면 하위 문서 복사가 키 수만큼 반복된다.

    Returns:
        ``JSON_OBJECT`` 식.
    """
    entries: list[Any] = []
    for key in sorted(spec, key=_jsonb_key_order):
        if not _KEY_PATTERN.match(key):
            raise ValueError(f"투영 키는 영문자만 허용한다: {key!r}")
        value = (prepared or {}).get(key)
        if value is None:
            value = doc[key]
        sub = spec[key]
        if sub is not None:
            value = case((func.jsonb_typeof(value) == "object", _pick(value, sub)),
                         else_=cast(value, PG_JSON))
        entries += [literal_column(f"'{key}'"), value]
    return _json_object_absent(*entries)


def list_snapshot_statement(criteria: tuple, order_by: Optional[tuple] = None,
                            limit: Optional[int] = None) -> Any:
    """목록 행 + 투영 문서를 읽는 PostgreSQL 문장.

    원본은 행마다 **한 번만** 푼다. 투영 식은 원본을 수십 번 참조하는데, TOAST 에 있는
    jsonb 는 참조마다 다시 풀린다 — 원본 컬럼에 바로 걸면 스테이징 1,241행에서 실행
    585~1,050ms 였다(통째 읽기 39ms, 공유 버퍼 적중 24만~33만). 그래서:

    1. 안쪽 조회가 ``raw_snapshot #> '{}'``(원본 그대로를 돌려주는 빈 경로 추출 — 값은
       같고 풀린 사본이 된다)로 한 번 풀고, ``OFFSET 0`` 으로 바깥에 끌려 올라가지 않게 막는다.
    2. ``productOrder``·``order`` 하위 문서도 LATERAL 에서 한 번만 꺼낸다(키마다 꺼내면
       상품주문 복사가 키 수만큼 반복돼 실행이 약 10ms 더 든다).

    Args:
        criteria: WHERE 조건.
        order_by: 정렬식(바깥에서도 같은 순서로 다시 정렬한다 — 안쪽 순서는 보장되지 않는다).
        limit: 조회 상한.

    Returns:
        ``LIST_COLUMNS`` 순서의 컬럼 + ``raw_snapshot``(투영 문서)을 내는 select.
    """
    inner, outer_order = fenced_snapshot_source(LIST_COLUMNS, criteria, order_by, limit,
                                                name="wb_list_src")
    parts = (select(inner.c.r["productOrder"].label("po"), inner.c.r["order"].label("o"))
             .correlate(inner).offset(0).lateral("wb_list_parts"))
    root = _pick(inner.c.r, LIST_SNAPSHOT_SPEC,
                 prepared={"productOrder": parts.c.po, "order": parts.c.o})
    document = case((func.jsonb_typeof(inner.c.r) == "object", root),
                    else_=cast(inner.c.r, PG_JSON))
    statement = (select(*[inner.c[column.key] for column in LIST_COLUMNS],
                        document.label("raw_snapshot"))
                 .select_from(inner.join(parts, true())))
    if outer_order:
        statement = statement.order_by(*outer_order)
    return statement


def fenced_snapshot_source(columns: tuple, criteria: tuple, order_by: Optional[tuple] = None,
                           limit: Optional[int] = None, *, name: str) -> tuple[Any, tuple]:
    """원본 스냅샷을 **행마다 한 번만** 푼 안쪽 조회와, 그 위에서 쓸 정렬식을 만든다.

    ``raw_snapshot #> '{}'`` 는 원본과 같은 값의 풀린 사본이고, ``OFFSET 0`` 울타리가 이
    조회를 바깥으로 끌어올리지 못하게 막는다. 바깥 식이 ``r`` 을 몇 번 참조해도 다시
    풀지 않는다(원본 컬럼에 바로 걸면 참조마다 TOAST 를 다시 푼다).

    Args:
        columns: 함께 읽을 ``ExternalOrderLink`` 컬럼(정렬식이 쓰는 컬럼을 포함해야 한다).
        criteria: WHERE 조건.
        order_by: 정렬식(안쪽은 상한을 위해, 바깥은 결과 순서를 위해 같은 순서로 정렬한다).
        limit: 조회 상한.
        name: 안쪽 조회 별칭.

    Returns:
        ``(안쪽 subquery — 컬럼 + 풀린 원본 r, 바깥용 정렬식 튜플)``.
    """
    detoasted = ExternalOrderLink.raw_snapshot.op("#>", return_type=JSONB)(
        literal_column("'{}'::text[]"))
    inner = select(*columns, detoasted.label("r")).where(*criteria)
    if order_by:
        inner = inner.order_by(*order_by)
    inner = inner.limit(limit).offset(0).subquery(name)
    adapter = ClauseAdapter(inner)
    outer_order = tuple(adapter.traverse(expr) for expr in order_by) if order_by else ()
    return inner, outer_order


def thin_snapshot_statement(columns: tuple, build_document: Any, criteria: tuple,
                            order_by: Optional[tuple] = None,
                            limit: Optional[int] = None) -> Any:
    """얇은 행(nav 뱃지·판정 경로) + 축소 문서를 읽는 PostgreSQL 문장.

    축소 문서 식(``naver_ingest._snapshot_projection``)은 원본을 20번 넘게 참조한다. 원본
    컬럼에 바로 걸면 참조마다 다시 풀려 스테이징 1,241행에서 155~176ms 였다(통째 읽기 39ms).
    :func:`fenced_snapshot_source` 위에서 같은 식을 만들면 행마다 한 번만 푼다.

    Args:
        columns: 얇은 행 컬럼(``naver_ingest._THIN_COLUMNS``).
        build_document: 원본 jsonb 식을 받아 축소 문서 식을 돌려주는 함수.
        criteria: WHERE 조건.
        order_by: 정렬식.
        limit: 조회 상한.

    Returns:
        ``columns`` 순서의 컬럼 + ``raw_snapshot``(축소 문서)을 내는 select.
    """
    inner, outer_order = fenced_snapshot_source(columns, criteria, order_by, limit,
                                                name="wb_thin_src")
    statement = select(*[inner.c[column.key] for column in columns],
                       build_document(inner.c.r).label("raw_snapshot"))
    if outer_order:
        statement = statement.order_by(*outer_order)
    return statement


def fetch_list_links(db: Any, *criteria: Any, order_by: Optional[tuple] = None,
                     limit: Optional[int] = None) -> list[ListLink]:
    """처리 목록용 링크 행을 읽는다 — 술어·정렬·상한은 호출자 그대로, 문서만 얇다.

    Args:
        db: 요청 스코프 DB 세션.
        *criteria: WHERE 조건.
        order_by: 정렬식 튜플(없으면 정렬 없음).
        limit: 조회 상한(없으면 없음).

    Returns:
        :class:`ListLink` 목록.
    """
    if supports_sql_projection(db):
        rows = db.execute(list_snapshot_statement(criteria, order_by, limit)).all()
        return [ListLink(*row) for row in rows]
    query = db.query(*LIST_COLUMNS, ExternalOrderLink.raw_snapshot).filter(*criteria)
    if order_by:
        query = query.order_by(*order_by)
    if limit is not None:
        query = query.limit(limit)
    return [ListLink(*row[:-1], project_list_snapshot(row[-1])) for row in query.all()]
