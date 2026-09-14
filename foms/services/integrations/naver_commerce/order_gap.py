"""네이버 수집분 ↔ ERP 주문 대조 — 읽기 전용 (GAP-01).

네이버 HTTP 를 내지 않는다(WORKER 단일 출구 계약). DB 만 읽는다 —
``client`` 모듈을 import 하지 않는다.

이 모듈이 답하는 질문은 하나다: "네이버에서 돈이 들어왔는데 ERP 에 주문이
안 만들어진 건이 있나?"

순진한 답(``order_id IS NULL AND relation='NEW'``)은 틀린다. ``relation`` 은
추가·재결제 축을 전부 가르지 못한다 — 상품명이 그대로 ``추가결제`` 인 행이
``NEW`` 로 들어와 있다. 그래서 판정은 ``raw_snapshot`` 에서 뽑은 스칼라
다섯 개(상품 구분·상품명·주문 상태·클레임 상태·결제 금액)로 한다.

**왜 SQL 술어가 아니라 "SQL 투영 + 파이썬 분류" 인가**

``external_order_links`` 에는 ``product_order_status``·``claim_status``·
``payment_amount`` **사본 컬럼이 있다**(NVMIRROR-01). 그 셋을 먼저 읽고,
값이 비어 있는 옛 행에서만 ``raw_snapshot`` 으로 떨어진다(models.py:3542-3630). 셋 다
``raw_snapshot``(JSONB) 안에 있고, 그 JSON 은 중첩·평평 두 모양으로 온다
(``mapping.unwrap_detail``, ``claim_watch`` 의 SQL 투영이 같은 일을 한다).

그래서 SQL 은 모집단 좁히기와 스칼라 투영만 하고, 분류는 파이썬 순수
함수가 한다. 그래야 SQLite 테스트 레인에서 방언 차이 없이 전 분기를
덮을 수 있다.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Sequence

from sqlalchemy import func, Integer

from foms.services.datetime_kst import format_datetime_kst
from foms.services.integrations.naver_commerce.claim_watch import STATE_KEY
from foms.services.integrations.naver_commerce.constants import (
    ADDON_PRODUCT_CLASS,
    CHANNEL,
)
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_PHASE_DONE,
    CLAIM_PHASES,
    CLAIM_STATUS_LABELS,
)
from models import ExternalOrderLink, Order

# --------------------------------------------------------------------------- #
# 버킷 상수
# --------------------------------------------------------------------------- #

GAP_MISSING = "missing"
GAP_ATTACHABLE = "attachable"
GAP_EXTRA = "extra"
GAP_CLOSED = "closed"
GAP_UNDECIDED = "undecided"

#: 화면이 도는 순서이자 테스트가 세는 전수. 이 순서대로 칩이 뜬다.
GAP_BUCKETS = (GAP_MISSING, GAP_ATTACHABLE, GAP_EXTRA, GAP_CLOSED,
               GAP_UNDECIDED)

#: 칸 이름과 설명의 SSOT. 템플릿에 한글을 박지 않는다 —
#: 문구 계약 테스트가 여기 하나만 보면 되게.
GAP_LABELS: dict[str, dict[str, str]] = {
    GAP_MISSING: {
        "label": "주문 없음(확인 필요)",
        "note": "같은 전화의 ERP 주문을 못 찾았습니다. 전화가 다르게 적힌 주문은 여기로 옵니다.",
    },
    GAP_ATTACHABLE: {
        "label": "주문 있음 · 링크만 없음",
        "note": "같은 전화의 ERP 주문이 있습니다. 같은 주문인지는 사람이 확인합니다.",
    },
    GAP_EXTRA: {
        "label": "부가·재결제 라인",
        "note": "추가구성상품·추가결제·재결제입니다. 새 주문이 아닙니다.",
    },
    GAP_CLOSED: {
        "label": "취소·반품 확정",
        "note": "네이버가 확정했습니다. 붙일 짝이 아닙니다.",
    },
    GAP_UNDECIDED: {
        "label": "판정 보류",
        "note": "아직 진행 중이거나 우리가 모르는 모양입니다. 사람이 봐야 합니다.",
    },
}

#: 본품으로 인정하는 네이버 ``productClass`` 값. 두 값의 출처가 다르다 —
#: ``조합형옵션상품`` 은 2026-08-14 실측(constants 의 ``ADDON_PRODUCT_CLASS``
#: 주석이 같은 날을 적는다), ``단일상품`` 은 2026-09-14 대조 실측에서 나왔다.
MAIN_PRODUCT_CLASSES = frozenset({"조합형옵션상품", "단일상품"})

#: 상품명만으로 부가 라인임이 드러나는 값. ``relation`` 이 ``NEW`` 인 채로
#: 들어오는 추가결제 라인을 여기서 잡는다.
EXTRA_PRODUCT_NAMES = frozenset({"추가결제"})

#: 네이버 ``productOrderStatus`` 자체가 종결인 값.
CLOSED_ORDER_STATUSES = frozenset({"CANCELED", "RETURNED"})

#: 모집단 상한. 운영 미연결 1,899행 기준 여유 2.6배다.
GAP_SCAN_CAP = 5000

#: 한 화면에 그리는 행 수.
GAP_PAGE_SIZE = 200

#: 전화 대조 ``IN`` 절 한 묶음 크기.
_PHONE_CHUNK = 500

#: 행 dict 의 키 전수. 여기 없는 키를 더하면 개인정보가 새는 자리가 된다.
GAP_ROW_KEYS = ("link_id", "external_order_no", "collected_date", "product_name",
                "payment_amount", "recipient_name_masked", "naver_status",
                "claim_label", "bucket")

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
# 작은 도우미
# --------------------------------------------------------------------------- #

def _text(value: Any) -> str:
    """스칼라를 문자열로. ``None`` 은 빈 문자열."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _to_int(value: Any) -> int:
    """결제 금액을 정수로. 못 읽으면 0(화면이 죽지 않게)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _text(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def _chunks(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def mask_name(name: str | None) -> str:
    """수취인 이름 마스킹. 빈 값이면 빈 문자열.

    1자 ``*`` · 2자 ``홍*`` · 3자 이상 ``홍*동``(가운데 전부 ``*``).
    """
    text = _text(name).strip()
    if not text:
        return ""
    if len(text) == 1:
        return "*"
    if len(text) == 2:
        return text[0] + "*"
    return text[0] + "*" * (len(text) - 2) + text[-1]


# --------------------------------------------------------------------------- #
# 분류 — DB 를 안 만지는 순수 함수
# --------------------------------------------------------------------------- #

def classify_gap_row(fields: dict, *, has_erp_order: bool) -> str:
    """행 하나를 버킷 이름으로 가른다 — DB 를 안 만지는 순수 함수.

    위에서부터 첫 일치다. 순서가 뜻이다: 종결이 먼저, 부가가 그다음,
    그러고도 살아 있는 본품만 붙이기 축(전화 대조)을 탄다.

    "claimStatus 가 비어 있지 않은가" 한 비트 판정은 쓰지 않는다. 그 판정이
    2026-08-28 운영 사고(link 79 / 주문 #4998 — 승인 전 취소가 '취소 완료' 로
    표기되고 그게 폐기 버튼의 허가증이 됐다)의 원인이라고 ``mapping`` 이
    못박아 두었다. 종결은 ``CLAIM_PHASES`` 가 ``done`` 이라고 말할 때만이다.

    Args:
        fields: ``product_class``·``product_name``·``order_status``·
            ``claim_status``·``amount``·``relation``·``phone_digits`` 키를
            가진 dict. 값은 전부 이미 뽑힌 스칼라다(문자열/정수).
        has_erp_order: 같은 전화의 ERP 주문이 있는가.

    Returns:
        :data:`GAP_BUCKETS` 중 하나.
    """
    order_status = _text(fields.get("order_status")).strip().upper()
    claim_status = _text(fields.get("claim_status")).strip()
    claim_upper = claim_status.upper()
    product_class = _text(fields.get("product_class")).strip()
    product_name = _text(fields.get("product_name")).strip()
    relation = _text(fields.get("relation")).strip().upper()
    amount = _to_int(fields.get("amount"))
    phone_digits = _text(fields.get("phone_digits")).strip()

    # 1. 종결 — 네이버가 확정한 것만.
    if order_status in CLOSED_ORDER_STATUSES:
        return GAP_CLOSED
    if claim_upper and CLAIM_PHASES.get(claim_upper) == CLAIM_PHASE_DONE:
        return GAP_CLOSED

    # 2. 부가·재결제. relation 은 이 축을 **전부**는 못 가르지만, 값이
    #    ADDON/REPAY 인 행은 정의상 부가다. 이 조건은 EXTRA 만 넓히고
    #    MISSING 을 절대 부풀리지 않는다.
    if (product_class == ADDON_PRODUCT_CLASS
            or product_name in EXTRA_PRODUCT_NAMES
            or relation in ("ADDON", "REPAY")):
        return GAP_EXTRA

    # 3. 살아있는 본품 — 네 조건을 전부 만족할 때만.
    if (order_status == "PURCHASE_DECIDED"
            and claim_status == ""
            and product_class in MAIN_PRODUCT_CLASSES
            and amount > 0):
        if not phone_digits:
            # 짚을 축이 아예 없다. 조용히 attachable 로 보내면 거짓말이 된다.
            return GAP_MISSING
        return GAP_ATTACHABLE if has_erp_order else GAP_MISSING

    # 4. 나머지 전부. 이 칸이 없으면 행이 조용히 사라진다 —
    #    배송 중(DELIVERING)·요청 단계 클레임(CANCEL_REQUEST)·거부된
    #    클레임(CANCEL_REJECT)·금액 0·모르는 productClass 가 여기로 온다.
    return GAP_UNDECIDED


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
