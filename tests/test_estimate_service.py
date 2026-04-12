import datetime
from types import SimpleNamespace

import foms.services.estimate_service as estimate_service


class _FakeColumn:
    def __init__(self, name: str):
        self.name = name

    def like(self, pattern: str):
        return ("like", self.name, pattern)


class _FakeOrderEstimateModel:
    estimate_number = _FakeColumn("estimate_number")


class _FakeEstimateQuery:
    def __init__(self, existing_rows):
        self.existing_rows = existing_rows
        self.criteria = []

    def filter(self, criterion):
        self.criteria.append(criterion)
        return self

    def all(self):
        return self.existing_rows


class _FakeEstimateNumberDb:
    def __init__(self, existing_rows):
        self.existing_rows = existing_rows

    def query(self, target):
        return _FakeEstimateQuery(self.existing_rows)


class _FakeCreateDb:
    def __init__(self):
        self.added = []
        self.flush_calls = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_calls += 1


class _FakeEstimate:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_generate_estimate_number_skips_invalid_suffixes_and_increments_max(monkeypatch):
    monkeypatch.setattr(estimate_service, "OrderEstimate", _FakeOrderEstimateModel)
    db = _FakeEstimateNumberDb(
        [
            ("20260410_1",),
            ("20260410_9",),
            ("20260410_bad",),
            ("20260410_3",),
        ]
    )

    result = estimate_service.generate_estimate_number(db, "2026-04-10")

    assert result == "20260410_10"


def test_extract_estimate_data_from_order_formats_spec_rows_and_payments():
    order = SimpleNamespace(
        customer_name="fallback customer",
        phone="01000000000",
        address="fallback address",
        manager_name="fallback manager",
        structured_data={
            "parties": {
                "customer": {"name": "홍길동", "phone": "01011112222"},
                "manager": {"name": "담당자", "phone": "01033334444"},
                "orderer": {"name": "라홈 본사"},
            },
            "site": {"address_full": "서울시 강남구 테스트로 1"},
            "schedule": {"construction": {"date": "2026-04-30"}},
            "payment": {"deposit": {"amount": 100000}},
            "items": [
                {
                    "product_name": "붙박이장",
                    "spec_rows": [
                        {"spec_width": "3000", "spec_depth": "600", "spec_height": "2300"},
                        {"w": "3100", "d": "650", "h": "2350"},
                    ],
                    "color": "화이트",
                    "option_detail": "서랍 추가",
                    "quantity": 2,
                    "price": 500000,
                }
            ],
        },
    )

    data = estimate_service.extract_estimate_data_from_order(order)

    assert data["customer_name"] == "홍길동"
    assert data["customer_phone"] == "01011112222"
    assert data["site_address"] == "서울시 강남구 테스트로 1"
    assert data["construction_date"] == "2026-04-30"
    assert data["manager_name"] == "담당자"
    assert data["manager_phone"] == "01033334444"
    assert data["is_lahom"] is True
    assert data["items"] == [
        {
            "product_name": "붙박이장",
            "spec": "3000x600x2300\n3100x650x2350",
            "color": "화이트",
            "option_detail": "서랍 추가",
            "quantity": 2,
            "unit_price": 500000,
            "amount": 1000000,
        }
    ]
    assert data["total_amount"] == 1000000
    assert data["deposit_amount"] == 100000
    assert data["balance_amount"] == 900000


def test_create_estimate_applies_overrides_and_uses_deep_copied_payment_info(monkeypatch):
    db = _FakeCreateDb()
    payment_info_template = {"bank": "테스트은행", "account": ["111-222"]}
    order = SimpleNamespace(
        id=77,
        customer_name="원본 고객",
        phone="01012341234",
        address="원본 주소",
        manager_name="원본 매니저",
        structured_data={"items": []},
    )

    monkeypatch.setattr(estimate_service, "OrderEstimate", _FakeEstimate)
    monkeypatch.setattr(estimate_service, "generate_estimate_number", lambda db, date: "20260410_7")
    monkeypatch.setattr(estimate_service, "ESTIMATE_PAYMENT_INFO", payment_info_template)

    estimate = estimate_service.create_estimate(
        db,
        order,
        override_data={
            "estimate_date": "2026-04-10",
            "customer_name": "수정 고객",
            "items": [{"amount": 300000}, {"amount": 200000}],
            "deposit_amount": 900000,
            "notes": "메모",
        },
        created_by_user_id=5,
    )

    assert estimate.estimate_number == "20260410_7"
    assert estimate.customer_name == "수정 고객"
    assert estimate.total_amount == 500000
    assert estimate.deposit_amount == 900000
    assert estimate.balance_amount == 0
    assert estimate.notes == "메모"
    assert estimate.created_by_user_id == 5
    assert estimate.status == "DRAFT"
    assert estimate.payment_info == payment_info_template
    assert estimate.payment_info is not payment_info_template
    assert db.added == [estimate]
    assert db.flush_calls == 1


def test_update_estimate_recalculates_totals_and_marks_items_modified(monkeypatch):
    flagged = []
    estimate = SimpleNamespace(
        estimate_number="20260410_1",
        items=[{"amount": 100000}],
        total_amount=100000,
        deposit_amount=10000,
        balance_amount=90000,
        updated_at=None,
    )

    monkeypatch.setattr(estimate_service, "flag_modified", lambda obj, field: flagged.append((obj, field)))

    updated = estimate_service.update_estimate(
        db=None,
        estimate=estimate,
        update_data={
            "items": [{"amount": 400000}, {"amount": 50000}],
            "deposit_amount": 70000,
            "notes": "수정 메모",
        },
    )

    assert updated.items == [{"amount": 400000}, {"amount": 50000}]
    assert updated.total_amount == 450000
    assert updated.deposit_amount == 70000
    assert updated.balance_amount == 380000
    assert updated.notes == "수정 메모"
    assert isinstance(updated.updated_at, datetime.datetime)
    assert flagged == [(estimate, "items")]
