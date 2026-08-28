"""후보 표의 **판정 근거 2열** — R-1 (2026-08-25).

담당자가 재결제/추가결제를 가르려면 두 가지를 알아야 한다.

* **② 그 주문에 붙은 네이버 결제가 취소됐는가** — 취소됐으면 재결제, 살아 있으면 추가결제.
* **③ 금액이 얼마나 차이 나는가** — 비슷·크면 재결제, 훨씬 작으면 차액 결제.

지금까지 화면은 링크 **개수**(`naver_link_count`)만 냈다. 담당자는 이 둘을 확인하려고
네이버를 따로 열었다. 스테이징 실데이터 4건(주문 4462·4466·4467·4485)이 전부 이 신호로
갈렸다.

금액은 **집 전체끼리** 견준다. 네이버는 본품과 옵션을 각각 다른 상품주문으로 주므로 대표
1건끼리 견주면 항상 작게 나온다(실사례: 대표만 보면 1,022,900 vs 실제 집 합계 1,610,780).
"""
from db import db_session
from models import ExternalOrderLink, Order

from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.order_candidates import (
    find_order_candidates,
    household_amount,
)


def _snapshot(*, order_no: str, amount: int, claim_status: str = "",
              tel: str = "010-5555-1234", name: str = "김후보") -> dict:
    """상품주문 상세 1건(원본 모양 그대로)."""
    product_order = {
        "productOrderId": f"PO-{order_no}-{amount}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": name, "tel1": tel,
                            "baseAddress": "서울 강남구 테헤란로 1",
                            "detailedAddress": "101호"},
    }
    if claim_status:
        product_order["claimStatus"] = claim_status
    return {"order": {"orderId": order_no, "ordererName": name, "ordererTel": tel},
            "productOrder": product_order}


def _link(session, *, order_no: str, amount: int, claim_status: str = "",
          order_id: int | None = None, external_id: str | None = None,
          tel: str = "010-5555-1234") -> ExternalOrderLink:
    snapshot = _snapshot(order_no=order_no, amount=amount, claim_status=claim_status, tel=tel)
    link = ExternalOrderLink(
        channel=CHANNEL,
        external_id=external_id or f"PO-{order_no}-{amount}",
        external_order_no=order_no,
        raw_snapshot=snapshot,
        group_key=group_key_text(snapshot),
        sync_status="LINKED" if order_id else "COLLECTED",
        order_id=order_id,
    )
    session.add(link)
    session.flush()
    return link


def _order(session, *, name: str = "김후보", tel: str = "010-5555-1234") -> Order:
    order = Order(customer_name=name, phone=tel, erp_phone_digits=tel.replace("-", ""),
                  address="서울 강남구 테헤란로 1 101호", product="붙박이장",
                  received_date="2026-08-14", status="RECEIVED", payment_amount=0)
    session.add(order)
    session.flush()
    return order


def test_household_amount_sums_the_whole_household(app):
    """금액은 집 전체 합이다 — 대표 1건만 보면 항상 작다."""
    lead = _link(db_session, order_no="N-CAND-A", amount=1_022_900)
    _link(db_session, order_no="N-CAND-A", amount=400_000, external_id="PO-A-2")
    _link(db_session, order_no="N-CAND-A", amount=187_880, external_id="PO-A-3")

    assert household_amount(db_session, lead) == 1_610_780


def test_all_canceled_old_payment_reads_as_repay_signal(app):
    """옛 결제가 전부 취소 **확정**이면 `전부 취소 완료` — 재결제 신호."""
    order = _order(db_session)
    _link(db_session, order_no="N-OLD", amount=1_191_900, claim_status="CANCEL_DONE",
          order_id=int(order.id))
    new_link = _link(db_session, order_no="N-NEW", amount=1_610_780, external_id="PO-NEW-1")

    candidates = find_order_candidates(db_session, new_link)

    assert candidates, "전화가 같은데 후보가 없다"
    row = candidates[0]
    assert row["order_id"] == int(order.id)
    assert row["naver_claim_code"] == "all_done"
    assert row["naver_claim_label"] == "전부 취소 완료"
    assert row["naver_canceled_count"] == 1
    assert row["naver_pending_count"] == 0
    assert row["naver_alive_count"] == 0


def test_living_old_payment_reads_as_addon_signal(app):
    """옛 결제가 살아 있으면 `살아 있음` — 추가결제 신호."""
    order = _order(db_session, tel="010-5555-2222")
    _link(db_session, order_no="N-LIVE", amount=1_191_900, order_id=int(order.id),
          tel="010-5555-2222")
    new_link = _link(db_session, order_no="N-ADDON", amount=17_880,
                     external_id="PO-ADDON-1", tel="010-5555-2222")

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_label"] == "살아 있음"
    assert row["naver_alive_count"] == 1
    assert row["naver_canceled_count"] == 0


def test_partial_cancel_is_neither(app):
    """일부만 취소면 `일부 취소` — 사람이 봐야 한다고 말한다(단정 금지)."""
    order = _order(db_session, tel="010-5555-3333")
    _link(db_session, order_no="N-PART", amount=500_000, claim_status="CANCEL_DONE",
          order_id=int(order.id), external_id="PO-PART-1", tel="010-5555-3333")
    _link(db_session, order_no="N-PART", amount=300_000, order_id=int(order.id),
          external_id="PO-PART-2", tel="010-5555-3333")
    new_link = _link(db_session, order_no="N-PART-NEW", amount=800_000,
                     external_id="PO-PART-NEW", tel="010-5555-3333")

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_label"] == "일부 취소"
    assert row["naver_canceled_count"] == 1
    assert row["naver_alive_count"] == 1


def test_amount_comparison_uses_household_totals(app):
    """금액은 집 합계끼리 견준다 — 증액 재결제(+418,880)가 화면에 그대로 나와야 한다."""
    order = _order(db_session, tel="010-5555-4444")
    _link(db_session, order_no="N-OLD2", amount=1_021_900, claim_status="CANCEL_DONE",
          order_id=int(order.id), external_id="PO-OLD2-1", tel="010-5555-4444")
    _link(db_session, order_no="N-OLD2", amount=170_000, claim_status="CANCEL_DONE",
          order_id=int(order.id), external_id="PO-OLD2-2", tel="010-5555-4444")

    new_lead = _link(db_session, order_no="N-NEW2", amount=1_022_900,
                     external_id="PO-NEW2-1", tel="010-5555-4444")
    _link(db_session, order_no="N-NEW2", amount=587_880, external_id="PO-NEW2-2",
          tel="010-5555-4444")

    row = find_order_candidates(db_session, new_lead)[0]

    assert row["naver_amount_total"] == 1_191_900, "옛 집 합계"
    assert row["new_amount_total"] == 1_610_780, "새 집 합계 — 대표 1건이 아니다"
    assert row["amount_delta"] == 418_880


def test_candidate_without_naver_links_says_nothing(app):
    """ERP 수기 주문이면 네이버 근거가 없다 — 빈 라벨로 둔다(0 건으로 단정하지 않는다)."""
    order = _order(db_session, tel="010-5555-5555")
    new_link = _link(db_session, order_no="N-SOLO2", amount=100_000,
                     external_id="PO-SOLO2", tel="010-5555-5555")

    row = find_order_candidates(db_session, new_link)[0]

    assert row["order_id"] == int(order.id)
    assert row["naver_link_count"] == 0
    assert row["naver_claim_label"] == ""
    assert row["naver_amount_total"] == 0


def test_pane_template_renders_both_evidence_columns():
    """상세 템플릿이 두 열을 실제로 낸다 — payload 만 늘리고 화면이 안 쓰면 무의미하다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    markup = (root / "templates/admin/partials/naver_workbench_pane.html").read_text(encoding="utf-8")

    assert "네이버 옛 결제" in markup
    assert "금액 견주기" in markup
    assert "재결제 신호" in markup and "추가결제 신호" in markup
    assert "cand.amount_delta" in markup


# --------------------------------------------------------------------------- #
# 고객이 쓴 사유 원문 (2026-08-26) — 판정이 실제로 일어나는 자리까지 올린다
# --------------------------------------------------------------------------- #


def _cancel_link(session, *, order_no: str, amount: int, reason: str,
                 order_id: int, external_id: str,
                 tel: str = "010-5555-1234") -> ExternalOrderLink:
    """취소된 옛 상품주문 1건 — 고객이 쓴 사유 원문을 달고 있다."""
    link = _link(session, order_no=order_no, amount=amount, claim_status="CANCEL_DONE",
                 order_id=order_id, external_id=external_id, tel=tel)
    snapshot = dict(link.raw_snapshot)
    snapshot["cancel"] = {"claimStatus": "CANCEL_DONE", "cancelReason": "CHANGE_MIND",
                          "cancelDetailedReason": reason}
    link.raw_snapshot = snapshot
    session.flush()
    return link


def test_candidate_carries_the_customers_own_cancel_reason(app):
    """후보 표가 **왜 취소했는지**를 고객의 문장 그대로 들고 온다.

    라벨(`전부 취소`)은 무엇이 일어났는지만 말한다. 재결제냐 추가결제냐를 가르는 답은
    사유 원문에 있다 — 스테이징 실데이터의 `일시불 재결제 예정` 이 바로 그 답이었고,
    담당자는 이 한 줄을 보려고 판매자센터를 따로 열고 있었다.
    """
    order = _order(db_session, tel="010-6001-0001")
    _cancel_link(db_session, order_no="N-RSN", amount=500_000, reason="일시불 재결제 예정",
                 order_id=int(order.id), external_id="PO-RSN-1", tel="010-6001-0001")
    new_link = _link(db_session, order_no="N-RSN-NEW", amount=600_000,
                     external_id="PO-RSN-NEW", tel="010-6001-0001")

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_label"] == "전부 취소 완료"
    assert row["naver_cancel_reasons"] == ["일시불 재결제 예정"]


def test_same_sentence_from_main_and_option_is_said_once(app):
    """본품·옵션이 같은 문장을 각각 들고 와도 표에는 한 번만 나온다."""
    order = _order(db_session, tel="010-6002-0002")
    for idx in range(3):
        _cancel_link(db_session, order_no="N-DUP", amount=100_000 + idx, reason="취소 재결제",
                     order_id=int(order.id), external_id=f"PO-DUP-{idx}", tel="010-6002-0002")
    new_link = _link(db_session, order_no="N-DUP-NEW", amount=400_000,
                     external_id="PO-DUP-NEW", tel="010-6002-0002")

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_cancel_reasons"] == ["취소 재결제"]


def test_different_sentences_are_all_kept(app):
    """서로 다른 문장은 **하나도 버리지 않는다** — 어느 쪽이 판정 근거인지는 사람이 고른다."""
    order = _order(db_session, tel="010-6003-0003")
    _cancel_link(db_session, order_no="N-MIX", amount=100_000, reason="재결제",
                 order_id=int(order.id), external_id="PO-MIX-1", tel="010-6003-0003")
    _cancel_link(db_session, order_no="N-MIX", amount=200_000,
                 reason="사이즈 재측정후 주문할께요", order_id=int(order.id),
                 external_id="PO-MIX-2", tel="010-6003-0003")
    new_link = _link(db_session, order_no="N-MIX-NEW", amount=300_000,
                     external_id="PO-MIX-NEW", tel="010-6003-0003")

    row = find_order_candidates(db_session, new_link)[0]

    assert sorted(row["naver_cancel_reasons"]) == sorted(["재결제", "사이즈 재측정후 주문할께요"])


def test_alive_household_says_nothing_about_reasons(app):
    """살아 있는 옛 집에는 사유가 없다 — 빈 목록이지 빈 칸 하나가 아니다."""
    order = _order(db_session, tel="010-6004-0004")
    _link(db_session, order_no="N-NORSN", amount=300_000, order_id=int(order.id),
          external_id="PO-NORSN-1", tel="010-6004-0004")
    new_link = _link(db_session, order_no="N-NORSN-NEW", amount=50_000,
                     external_id="PO-NORSN-NEW", tel="010-6004-0004")

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_cancel_reasons"] == []
