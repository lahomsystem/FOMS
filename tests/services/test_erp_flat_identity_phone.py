"""flat audit 의 신원 phone drift 분류 (2026-10-06 #4147 대시보드 검색 오탐).

2026-09-02 이전 저장분은 정본 고객 전화를 바꿔도 flat ``phone`` 에 옛 번호가 남았다.
대시보드 검색은 ``Order.phone ILIKE`` 도 보므로 옛 번호 뒷자리로 엉뚱한 주문이 걸린다.
"""
from foms.services.orders import erp_flat_audit as fa
from foms.services.orders.erp_flat_audit import CLEAN, SAFE, classify_order


class _Order:
    def __init__(self, *, structured_data, phone, status=None):
        self.id = 1
        self.is_erp_order = True
        self.structured_data = structured_data
        self.phone = phone
        self.status = status
        for column in fa.DERIVED_COLUMNS:
            setattr(self, column, None)


def _phone_order(flat_phone, sd_phone, *, status=None):
    sd = {"parties": {"customer": {"phone": sd_phone}}}
    order = _Order(structured_data=sd, phone=flat_phone, status=status)
    for column, value in fa._expected_flat_values(order, sd).items():
        setattr(order, column, value)  # 파생 컬럼은 맞춰 두고 phone 만 본다
    return order


def test_stale_identity_phone_is_safe():
    result = classify_order(_phone_order("010-5210-6485", "010-5100-8886"))
    assert result.classification == SAFE
    assert result.drift_columns == ("phone",)


def test_identity_phone_not_drift_when_same_digits_or_multi_phone():
    assert classify_order(_phone_order("01051008886", "010-5100-8886")).classification == CLEAN
    # 다전화 정본 안에 옛 번호가 들어 있으면 같은 사람 — 덮지 않는다.
    multi = _phone_order("010-1111-2222", "010-1111-2222 / 010-3333-4444")
    assert classify_order(multi).classification == CLEAN


def test_identity_phone_placeholder_or_deleted_not_drift():
    assert classify_order(_phone_order("010-5210-6485", "000-0000-0000")).classification == CLEAN
    deleted = _phone_order("000-0000-0000", "010-3377-0412", status="DELETED")
    assert classify_order(deleted).classification == CLEAN


def test_backfill_resync_applies_identity_phone():
    """백필 재동기도 저장 경로와 같은 규칙으로 phone 을 맞춘다."""
    from foms.services.orders import erp_flat_backfill as fb

    order = _phone_order("010-5210-6485", "010-5100-8886")

    class _Session:
        def get(self, _model, _order_id):
            return order

    report = fb.BackfillReport()
    fb._resync_batch(_Session(), [1], report)
    assert order.phone == "010-5100-8886"
    assert report.resynced_orders == 1
