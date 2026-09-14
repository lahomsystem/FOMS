"""네이버 수집·주문 대조 — DB 를 거치는 계약 (GAP-01).

스냅샷 모양(중첩·평평)·ERP 전화 대조·뷰 조립처럼 **질의를 타야만** 확인되는
것만 여기 둔다. 값만으로 갈리는 분류 분기는 ``test_naver_order_gap.py`` 가 덮는다.
두 파일이 픽스처를 공유하므로 헤더는 같은 모양이다.
"""


from __future__ import annotations

from pathlib import Path

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import STATE_KEY
from foms.services.integrations.naver_commerce.constants import (
    ADDON_PRODUCT_CLASS,
    CHANNEL,
)
from foms.services.integrations.naver_commerce.order_gap import (
    GAP_ATTACHABLE,
    GAP_BUCKETS,
    GAP_CLOSED,
    GAP_EXTRA,
    GAP_LABELS,
    GAP_MISSING,
    GAP_ROW_KEYS,
    GAP_UNDECIDED,
    build_order_gap_view,
    classify_gap_row,
    list_order_gap,
    mask_name,
    summarize_order_gap,
)
from models import ExternalOrderLink, Order

ROOT = Path(__file__).resolve().parents[2]

GAP_PANE = "templates/admin/partials/naver_gap_pane.html"

#: 화면이 절대 말하면 안 되는 단정. 전화 대조는 휴리스틱이라 양쪽으로 틀린다.
FORBIDDEN_WORDS = ("빠진 주문", "누락", "확정된 미생성", "반드시")

#: 상단 안내 한 줄. 글자까지 계약이다.
REQUIRED_NOTICE = "전화 대조로 짚은 후보입니다 — 확정된 수가 아닙니다."

_SEQ = [0]


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


def _uid() -> str:
    _SEQ[0] += 1
    return f"gap-{_SEQ[0]}"


# --------------------------------------------------------------------------- #
# 헬퍼
# --------------------------------------------------------------------------- #

def _fields(**over) -> dict:
    """살아있는 본품 한 벌(=GAP_MISSING/ATTACHABLE 후보)을 기본값으로."""
    base = {
        "product_class": "조합형옵션상품",
        "product_name": "붙박이장",
        "order_status": "PURCHASE_DECIDED",
        "claim_status": "",
        "amount": 500000,
        "relation": "NEW",
        "phone_digits": "01033334444",
    }
    base.update(over)
    return base


def _snapshot(*, nested: bool, product_class: str, product_name: str,
              order_status: str, claim_status: str | None, amount,
              external_id: str) -> dict:
    product_order = {
        "productOrderId": external_id,
        "productClass": product_class,
        "productName": product_name,
        "productOrderStatus": order_status,
        "totalPaymentAmount": amount,
    }
    if claim_status is not None:
        product_order["claimStatus"] = claim_status
    if not nested:
        # 평평한 모양 — 배치 조회에서 이렇게 온다(mapping.unwrap_detail).
        flat = dict(product_order)
        flat["orderId"] = "N-" + external_id
        return flat
    return {"order": {"orderId": "N-" + external_id, "ordererName": "김주문"},
            "productOrder": product_order}


def _link(*, nested: bool = True,
          product_class: str = "조합형옵션상품",
          product_name: str = "붙박이장",
          order_status: str = "PURCHASE_DECIDED",
          claim_status: str | None = None,
          amount=500000,
          relation: str = "NEW",
          recipient_name: str = "이수취",
          phone: str | None = "01033334444",
          triage_state: dict | None = None,
          order: Order | None = None) -> ExternalOrderLink:
    external_id = f"PO-{_uid()}"
    link = ExternalOrderLink(
        channel=CHANNEL,
        external_id=external_id,
        sync_status="COLLECTED",
        relation=relation,
        order_id=order.id if order is not None else None,
        recipient_name=recipient_name,
        recipient_phone_digits=phone,
        triage_state=triage_state,
        raw_snapshot=_snapshot(nested=nested, product_class=product_class,
                               product_name=product_name,
                               order_status=order_status,
                               claim_status=claim_status, amount=amount,
                               external_id=external_id),
    )
    db_session.add(link)
    db_session.commit()
    return link


def _order(*, phone_digits: str, trashed: bool = False) -> Order:
    order = Order(customer_name="테스트고객", phone="010-3333-4444", address="서울",
                  product="붙박이장", options="", received_date="2026-09-01",
                  status="DELETED" if trashed else "RECEIVED",
                  is_erp_order=False, structured_data={},
                  erp_phone_digits=phone_digits)
    if trashed:
        import datetime

        order.deleted_at = datetime.datetime(2026, 9, 2, 0, 0, 0)
    db_session.add(order)
    db_session.commit()
    return order


def _bucket_of(link_ids) -> dict[int, str]:
    """link_id → 버킷. 칸마다 목록을 받아 뒤집는다(전수 확인용)."""
    wanted = set(link_ids)
    found: dict[int, str] = {}
    for name in GAP_BUCKETS:
        for row in list_order_gap(db_session, bucket=name, limit=1000):
            if row["link_id"] in wanted:
                found[row["link_id"]] = row["bucket"]
    return found


# --------------------------------------------------------------------------- #
# 3. DB 투영 — 중첩·평평 두 모양
# --------------------------------------------------------------------------- #

def test_nested_and_flat_snapshots_land_in_same_bucket(db):
    """한 모양만 읽으면 여기서 red 다(조용한 0건)."""
    nested = _link(nested=True)
    flat = _link(nested=False)

    got = _bucket_of([nested.id, flat.id])

    assert got.get(nested.id) == GAP_MISSING
    assert got.get(flat.id) == GAP_MISSING, "평평한 snapshot 을 못 읽었다"


def test_flat_snapshot_extra_line_is_extra(db):
    """평평한 모양에서도 부가 라인 판정이 산다."""
    link = _link(nested=False, product_name="추가결제")

    assert _bucket_of([link.id]).get(link.id) == GAP_EXTRA


def test_empty_claim_status_falls_through_to_triage_state(db):
    """빈 문자열 함정 — nullif 없이 coalesce 하면 여기서 red 다.

    ``productOrder.claimStatus`` 가 ``""`` 이면 ``coalesce`` 는 빈 문자열을
    이긴 값으로 돌려주고, 뒤 후보(``triage_state.claim_sync.last_status``)를
    영영 못 본다.
    """
    link = _link(order_status="PAYED", claim_status="",
                 triage_state={STATE_KEY: {"last_status": "CANCEL_DONE"}})

    assert _bucket_of([link.id]).get(link.id) == GAP_CLOSED


def test_root_level_claim_status_is_read(db):
    """중첩 안에 claimStatus 가 없으면 뿌리를 본다."""
    link = _link(order_status="PAYED", claim_status=None)
    snapshot = dict(link.raw_snapshot)
    snapshot["claimStatus"] = "RETURN_DONE"
    link.raw_snapshot = snapshot
    db_session.commit()

    assert _bucket_of([link.id]).get(link.id) == GAP_CLOSED


# --------------------------------------------------------------------------- #
# 4. 붙이기 대상 분기 (전화 대조)
# --------------------------------------------------------------------------- #

def test_matching_erp_order_moves_row_to_attachable(db):
    link = _link(phone="01055556666")
    assert _bucket_of([link.id]).get(link.id) == GAP_MISSING

    _order(phone_digits="01055556666")

    assert _bucket_of([link.id]).get(link.id) == GAP_ATTACHABLE


def test_trashed_erp_order_still_counts_as_attachable(db):
    """휴지통 주문도 '존재했다'는 근거다 — 빼면 '주문 없음' 이 부풀어 오른다."""
    link = _link(phone="01077778888")
    _order(phone_digits="01077778888", trashed=True)

    assert _bucket_of([link.id]).get(link.id) == GAP_ATTACHABLE


def test_other_phone_does_not_attach(db):
    """음성 대조군 — 다른 전화의 주문은 붙이기 후보가 아니다."""
    link = _link(phone="01099990000")
    _order(phone_digits="01011112222")

    assert _bucket_of([link.id]).get(link.id) == GAP_MISSING


def test_linked_rows_are_out_of_scope(db):
    """이미 주문이 붙은 수집분은 모집단이 아니다."""
    order = _order(phone_digits="01012340000")
    link = _link(order=order)

    assert _bucket_of([link.id]) == {}


# --------------------------------------------------------------------------- #
# 5. 뷰 계약
# --------------------------------------------------------------------------- #

def test_bucket_counts_sum_to_total_and_scanned(db):
    """행이 조용히 사라지면 red 다."""
    _link()
    _link(order_status="CANCELED")
    _link(product_name="추가결제")
    _link(order_status="DELIVERING")
    _link(amount=0)

    view = build_order_gap_view(db_session)

    assert view["truncated"] is False
    assert sum(b["count"] for b in view["buckets"].values()) == view["total"]
    assert view["total"] == view["scanned"]
    assert view["total"] >= 5


def test_buckets_cover_every_name_even_when_empty(db):
    _link()

    view = build_order_gap_view(db_session)

    assert set(view["buckets"]) == set(GAP_BUCKETS)
    for name, cell in view["buckets"].items():
        assert cell["label"] == GAP_LABELS[name]["label"]
        assert cell["note"] == GAP_LABELS[name]["note"]
        assert isinstance(cell["count"], int)
        assert isinstance(cell["amount"], int)


def test_unknown_bucket_falls_back_to_missing(db):
    _link()

    view = build_order_gap_view(db_session, bucket="주소를손으로고침")

    assert view["bucket"] == GAP_MISSING


def test_limit_zero_returns_counts_only(db):
    _link()

    view = build_order_gap_view(db_session, limit=0)

    assert view["rows"] == []
    assert view["has_more"] is False
    assert view["total"] >= 1


def test_summarize_is_counts_only_wrapper(db):
    _link()

    assert summarize_order_gap(db_session)["rows"] == []


def test_offset_paging_walks_rows_without_repeating(db):
    made = [_link().id for _ in range(3)]

    first = build_order_gap_view(db_session, bucket=GAP_MISSING, limit=2, offset=0)
    second = build_order_gap_view(db_session, bucket=GAP_MISSING, limit=2, offset=2)

    assert len(first["rows"]) == 2
    assert first["has_more"] is True
    seen = [row["link_id"] for row in first["rows"] + second["rows"]]
    assert len(seen) == len(set(seen))
    assert set(made) <= set(seen)


def test_negative_offset_and_limit_are_clamped(db):
    _link()

    view = build_order_gap_view(db_session, limit=-5, offset=-3)

    assert view["limit"] == 0
    assert view["offset"] == 0
    assert view["rows"] == []


def test_view_reports_cap(db):
    assert build_order_gap_view(db_session, limit=0)["cap"] > 0


# --------------------------------------------------------------------------- #
# 6. 개인정보
# --------------------------------------------------------------------------- #

def test_row_keys_are_exhaustive_and_carry_no_contact(db):
    phone = "01044445555"
    _link(phone=phone, recipient_name="남궁민수")

    rows = list_order_gap(db_session, bucket=GAP_MISSING, limit=50)

    assert rows, "행이 나와야 한다"
    for row in rows:
        assert set(row) == set(GAP_ROW_KEYS), "행 키가 계약 밖이다"
        for value in row.values():
            assert phone not in str(value), "전화가 행에 실렸다"
            assert "서울" not in str(value), "주소가 행에 실렸다"


def test_recipient_name_leaves_masked_only(db):
    _link(recipient_name="남궁민수", phone="01066667777")

    rows = list_order_gap(db_session, bucket=GAP_MISSING, limit=50)
    names = {row["recipient_name_masked"] for row in rows}

    assert "남**수" in names
    assert "남궁민수" not in names


def test_claim_label_is_human_readable(db):
    link = _link(order_status="PAYED", claim_status="CANCEL_DONE")

    rows = list_order_gap(db_session, bucket=GAP_CLOSED, limit=50)
    row = next(r for r in rows if r["link_id"] == link.id)

    assert row["claim_label"] == "취소 완료"
    assert row["naver_status"] == "PAYED"


def test_row_scalars_have_declared_types(db):
    _link()

    row = list_order_gap(db_session, bucket=GAP_MISSING, limit=1)[0]

    assert isinstance(row["link_id"], int)
    assert isinstance(row["payment_amount"], int)
    assert row["payment_amount"] > 0
    assert isinstance(row["collected_date"], str)
    assert len(row["collected_date"]) == len("2026-09-14")


# --------------------------------------------------------------------------- #
# 7. 계약 — 네이버 HTTP 부재
# --------------------------------------------------------------------------- #

def test_module_never_imports_naver_http_client():
    """WORKER 단일 출구 계약 — 이 모듈은 DB 만 읽는다."""
    source = (ROOT / "foms/services/integrations/naver_commerce/order_gap.py"
              ).read_text(encoding="utf-8")

    assert "import requests" not in source
    assert "naver_commerce.client" not in source
    assert "import client" not in source
    assert "from .client" not in source


def test_module_does_not_hardcode_production_counts():
    """운영 실측치를 코드에 박으면 화면이 서버가 센 수를 안 낸다."""
    source = (ROOT / "foms/services/integrations/naver_commerce/order_gap.py"
              ).read_text(encoding="utf-8")

    for number in ("1,080", "227건", "444건", "93건"):
        assert number not in source


# --------------------------------------------------------------------------- #
# 8. 화면 문구 계약 (파셜은 W3 소유 — 없으면 skip)
# --------------------------------------------------------------------------- #

def _gap_pane_text() -> str:
    return (ROOT / GAP_PANE).read_text(encoding="utf-8")


pane_required = pytest.mark.skipif(
    not (ROOT / GAP_PANE).exists(),
    reason=f"{GAP_PANE} 아직 없음(W3 소유) — 통합 검증 시점에는 반드시 돈다",
)


@pane_required
def test_gap_pane_has_no_overclaiming_words():
    text = _gap_pane_text()

    for word in FORBIDDEN_WORDS:
        assert word not in text, f"단정 표현 '{word}' 가 화면에 있다"


@pane_required
def test_gap_pane_carries_the_candidate_notice():
    assert REQUIRED_NOTICE in _gap_pane_text()


@pane_required
def test_gap_pane_does_not_hardcode_bucket_labels():
    """라벨 SSOT 는 GAP_LABELS 하나다."""
    text = _gap_pane_text()

    for entry in GAP_LABELS.values():
        assert entry["label"] not in text, "한글 라벨이 템플릿에 박혀 있다"
