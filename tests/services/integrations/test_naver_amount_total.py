"""상품주문 표의 **금액 합계** (2026-09-02 사용자 요구).

항목별 금액은 나오는데 총액이 없어서, 집이 3~6건씩 오는 화면에서 담당자가 매번
암산했다. 합계는 표에 찍힌 `금액` 열(상품주문별 ``totalPaymentAmount``)을 그대로 더한
값이다 — 화면에 없는 축을 새로 만들지 않는다.

두 가지를 못박는다.

1. **한 행이라도 금액을 못 읽었으면 숫자를 내지 않는다.** 부분 합계를 전체인 양 말하면
   결제 대조가 조용히 틀어진다(쿠폰 합계와 같은 규율).
2. **부분취소가 섞이면 잔여 합계도 낸다.** 위에 찍힌 금액은 클레임이 걸려도 안 줄어드는
   원래 값이라, 합계만 내면 "지금 얼마 남았나"를 화면이 말하지 못한다.
"""
import pathlib

from foms.web.admin.naver_ingest import _amount_summary

PANE_TEMPLATE = pathlib.Path("templates/admin/partials/naver_workbench_pane.html")
DETAIL_TEMPLATE = pathlib.Path("templates/admin/partials/naver_workbench_detail.html")


def _row(amount, quantity=1, partial=None):
    return {"amount": amount, "quantity": quantity, "partial_cancel": partial or {}}


def test_amount_total_sums_visible_column():
    """합계·수량 합계는 행 값의 단순 합이다(실화면 3건 표본)."""
    summary = _amount_summary([_row(748200, 8), _row(38040, 12), _row(60000, 1)])

    assert summary["known"] is True
    assert summary["total"] == 846240
    assert summary["quantity_total"] == 21
    assert summary["has_remain"] is False


def test_amount_total_unknown_when_any_row_amount_missing():
    """금액을 못 읽은 행이 하나라도 있으면 합계를 **말하지 않는다**."""
    summary = _amount_summary([_row(748200, 8), _row(None, 1)])

    assert summary["known"] is False


def test_amount_total_reports_remain_when_partially_cancelled():
    """부분취소가 섞이면 잔여 합계를 따로 낸다(안 깎인 행은 원래 금액으로 센다)."""
    summary = _amount_summary([
        _row(50000, 2, {"amount_partial": True, "remain_amount": 20000}),
        _row(30000, 1),
    ])

    assert summary["has_remain"] is True
    assert summary["total"] == 80000
    assert summary["remain_total"] == 50000


def test_amount_total_empty_household_says_unknown():
    """행이 없으면 합계도 없다 — 0 원이라고 단정하지 않는다."""
    assert _amount_summary([])["known"] is False


def test_both_surfaces_render_the_total_row():
    """pane 과 이력 상세가 **같은 값**(amount_summary)으로 합계 줄을 낸다."""
    for path in (PANE_TEMPLATE, DETAIL_TEMPLATE):
        markup = path.read_text(encoding="utf-8")
        assert "wb-cmp__total" in markup, path
        assert "amount_summary.total" in markup, path
        assert "amount_summary.known" in markup, path
