import datetime
from types import SimpleNamespace

import foms.services.estimate_service as estimate_service
from foms.services.orders.estimate_defaults import (
    ESTIMATE_COMPANY_INFO,
    ESTIMATE_COMPANY_INFO_FACTORY2,
    ESTIMATE_PAYMENT_INFO,
    ESTIMATE_PAYMENT_INFO_FACTORY2,
    resolve_estimate_company_info,
    resolve_estimate_payment_info,
)


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


def test_estimate_payment_info_has_multi_accounts_and_legacy_single_fields():
    """GDM: 견적 기본 결제정보는 accounts[] + 단일 bank/account/holder 하위 호환을 유지한다."""
    assert "accounts" in ESTIMATE_PAYMENT_INFO
    assert len(ESTIMATE_PAYMENT_INFO["accounts"]) >= 2
    for acc in ESTIMATE_PAYMENT_INFO["accounts"]:
        assert acc.get("bank")
        assert acc.get("holder")
    assert ESTIMATE_PAYMENT_INFO.get("bank")
    assert ESTIMATE_PAYMENT_INFO.get("account")
    assert ESTIMATE_PAYMENT_INFO.get("holder")
    assert ESTIMATE_PAYMENT_INFO.get("notice")


def test_estimate_company_info_factory2_fields():
    """2공장 공급자 정보는 라홈시스템 상호·대표·등록번호·소재지를 사용한다."""
    assert ESTIMATE_COMPANY_INFO_FACTORY2["name"] == "라홈시스템"
    assert ESTIMATE_COMPANY_INFO_FACTORY2["ceo"] == "김은지"
    assert ESTIMATE_COMPANY_INFO_FACTORY2["business_number"] == "446-08-03252"
    assert ESTIMATE_COMPANY_INFO_FACTORY2["address"] == "경기도 김포시 대곶면 마로 194번길 62-24"


def test_resolve_estimate_company_info_switches_by_factory2_flag():
    default_ci = resolve_estimate_company_info(False)
    factory2_ci = resolve_estimate_company_info(True)
    assert default_ci["name"] == ESTIMATE_COMPANY_INFO["name"]
    assert factory2_ci["name"] == "라홈시스템"
    assert factory2_ci is not default_ci


def test_estimate_payment_info_factory2_single_account():
    """2공장 결제정보는 기업은행 단일 계좌(김은지 라홈시스템)만 포함한다."""
    assert len(ESTIMATE_PAYMENT_INFO_FACTORY2["accounts"]) == 1
    acc = ESTIMATE_PAYMENT_INFO_FACTORY2["accounts"][0]
    assert acc["bank"] == "기업은행"
    assert acc["account"] == "461-091619-01-010"
    assert acc["holder"] == "김은지 라홈시스템"


def test_resolve_estimate_payment_info_switches_by_factory2_flag():
    default_pi = resolve_estimate_payment_info(False)
    factory2_pi = resolve_estimate_payment_info(True)
    assert default_pi["accounts"][0]["account"] == "461-082990-04-011"
    assert factory2_pi["accounts"][0]["account"] == "461-091619-01-010"
    assert factory2_pi is not default_pi


def test_is_factory2_order_reads_structured_flags():
    assert estimate_service.is_factory2_order({}) is False
    assert estimate_service.is_factory2_order({"flags": {"factory2": True}}) is True
    assert estimate_service.is_factory2_order({"flags": {"factory2": "on"}}) is True


def test_extract_estimate_data_from_order_includes_factory2_flag():
    order = SimpleNamespace(
        customer_name="",
        phone="",
        address="",
        manager_name="",
        structured_data={
            "parties": {"customer": {}, "manager": {}, "orderer": {"name": "라홈"}},
            "flags": {"factory2": True},
            "items": [],
        },
    )
    data = estimate_service.extract_estimate_data_from_order(order)
    assert data["factory2"] is True


def test_create_estimate_uses_factory2_payment_info(monkeypatch):
    db = _FakeCreateDb()
    factory2_payment = resolve_estimate_payment_info(True)
    order = SimpleNamespace(
        id=88,
        customer_name="고객",
        phone="010",
        address="주소",
        manager_name="매니저",
        structured_data={"items": [], "flags": {"factory2": True}},
    )

    monkeypatch.setattr(estimate_service, "OrderEstimate", _FakeEstimate)
    monkeypatch.setattr(estimate_service, "generate_estimate_number", lambda db, date: "20260701_1")

    estimate = estimate_service.create_estimate(db, order)

    assert estimate.payment_info["accounts"][0]["account"] == "461-091619-01-010"
    assert estimate.payment_info is not factory2_payment


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
    assert data["final_amount"] == 900000


def test_extract_estimate_data_applies_discount_to_balance():
    order = SimpleNamespace(
        customer_name="c",
        phone="p",
        address="a",
        manager_name="m",
        structured_data={
            "parties": {"customer": {"name": "홍길동"}, "orderer": {"name": "라홈"}},
            "payment": {"deposit": 100000, "discount": 50000},
            "items": [{"product_name": "붙박이장", "price": 500000}],
        },
    )

    data = estimate_service.extract_estimate_data_from_order(order)

    assert data["total_amount"] == 500000
    assert data["deposit_amount"] == 100000
    assert data["discount_amount"] == 50000
    assert data["balance_amount"] == 350000
    assert data["final_amount"] == 350000


def test_extract_estimate_data_merges_manual_rows_without_total_by_default():
    order = SimpleNamespace(
        customer_name="c",
        phone="p",
        address="a",
        manager_name="m",
        structured_data={
            "parties": {"customer": {"name": "홍길동"}, "orderer": {"name": "라홈"}},
            "items": [
                {"product_name": "책장", "price": 100000},
                {"product_name": "수납장", "price": 200000},
            ],
            "estimate_preview": {
                "manual_rows": [
                    {
                        "id": "mr_1",
                        "after_index": 0,
                        "product_name": "현장 메모",
                        "spec": "추가 확인",
                        "color": "상담",
                        "quantity": "1",
                        "amount": "50,000",
                    }
                ]
            },
        },
    )

    data = estimate_service.extract_estimate_data_from_order(order)

    assert [item["product_name"] for item in data["items"]] == ["책장", "현장 메모", "수납장"]
    manual_item = data["items"][1]
    assert manual_item["source"] == "manual"
    assert manual_item["manual_row_id"] == "mr_1"
    assert manual_item["amount"] == 50000
    assert manual_item["affects_total"] is False
    assert data["estimate_preview"]["manual_rows"][0]["amount_value"] == 50000
    assert data["total_amount"] == 300000
    assert data["balance_amount"] == 300000


def test_extract_estimate_data_can_apply_manual_rows_to_total():
    order = SimpleNamespace(
        customer_name="c",
        phone="p",
        address="a",
        manager_name="m",
        structured_data={
            "parties": {"customer": {"name": "홍길동"}, "orderer": {"name": "라홈"}},
            "payment": {"deposit": 100000},
            "items": [{"product_name": "책장", "price": 300000}],
            "estimate_preview": {
                "manual_rows": [
                    {
                        "id": "mr_2",
                        "after_index": 0,
                        "product_name": "추가 선반",
                        "quantity": "1",
                        "amount": "80,000원",
                        "affects_total": True,
                    }
                ]
            },
        },
    )

    data = estimate_service.extract_estimate_data_from_order(order)

    assert data["items"][1]["source"] == "manual"
    assert data["items"][1]["amount_raw"] == "80,000원"
    assert data["total_amount"] == 380000
    assert data["balance_amount"] == 280000
    assert data["final_amount"] == 280000


def test_extract_estimate_data_accepts_modern_payment_and_legacy_payments_deposit():
    base_order = {
        "customer_name": "fallback customer",
        "phone": "01000000000",
        "address": "fallback address",
        "manager_name": "fallback manager",
    }
    shared_structured = {
        "parties": {"customer": {"name": "홍길동"}, "orderer": {"name": "라홈"}},
        "items": [{"product_name": "붙박이장", "price": 300000}],
    }

    modern_order = SimpleNamespace(
        **base_order,
        structured_data={
            **shared_structured,
            "payment": {"deposit": "150,000원"},
            "payments": {"deposit": {"amount": 100000}},
        },
    )
    legacy_order = SimpleNamespace(
        **base_order,
        structured_data={
            **shared_structured,
            "payment": {"deposit_confirmed": True},
            "payments": {"deposit": {"amount": "100,000원"}},
        },
    )

    modern_data = estimate_service.extract_estimate_data_from_order(modern_order)
    legacy_data = estimate_service.extract_estimate_data_from_order(legacy_order)

    assert modern_data["deposit_amount"] == 150000
    assert modern_data["balance_amount"] == 150000
    assert modern_data["final_amount"] == 150000
    assert legacy_data["deposit_amount"] == 100000
    assert legacy_data["balance_amount"] == 200000
    assert legacy_data["final_amount"] == 200000


def test_extract_estimate_data_overrides_manager_phone_from_measurement_settings(monkeypatch):
    """계약서 담당자 이름이 출고 설정 실측담당자와 일치하면 연락처를 설정값으로 채운다."""

    def fake_load():
        return {
            "measurement_manager": [
                {"name": "담당자", "sort_order": 1, "phone": "010-9999-8888"},
            ]
        }

    monkeypatch.setattr(
        "foms.services.erp_shipment_settings.load_erp_shipment_settings",
        fake_load,
    )

    order = SimpleNamespace(
        customer_name="c",
        phone="p",
        address="a",
        manager_name="ignored",
        structured_data={
            "parties": {
                "customer": {"name": "홍길동", "phone": "01011112222"},
                "manager": {"name": "담당자", "phone": "01033334444"},
                "orderer": {"name": "기타"},
            },
            "site": {"address_full": "주소"},
            "schedule": {"construction": {"date": "2026-04-30"}},
            "payment": {"deposit": {"amount": 0}},
            "items": [],
        },
    )

    data = estimate_service.extract_estimate_data_from_order(order)

    assert data["manager_name"] == "담당자"
    assert data["manager_phone"] == "010-9999-8888"


def test_create_estimate_applies_overrides_and_uses_deep_copied_payment_info(monkeypatch):
    import copy

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
    monkeypatch.setattr(
        estimate_service,
        "resolve_estimate_payment_info",
        lambda factory2=False: copy.deepcopy(payment_info_template),
    )

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


def test_extract_estimate_data_exposes_free_input_lines_between_subtotal_and_deposit():
    order = SimpleNamespace(
        customer_name="c",
        phone="p",
        address="a",
        manager_name="m",
        structured_data={
            "parties": {"customer": {"name": "홍길동"}, "orderer": {"name": "라홈"}},
            "payment": {"deposit": 100000, "free_input": "운반비 : 30,000\n세금 : 10,000"},
            "totals": {"free_input_amount": 40000},
            "items": [{"product_name": "붙박이장", "price": 500000, "quantity": 1}],
        },
    )

    data = estimate_service.extract_estimate_data_from_order(order)

    assert data["items_subtotal"] == 500000
    assert data["free_input_amount"] == 40000
    assert data["total_amount"] == 540000
    assert data["free_input_lines"] == [
        {"label": "운반비", "amount": 30000},
        {"label": "세금", "amount": 10000},
    ]
    assert data["deposit_amount"] == 100000
    assert data["balance_amount"] == 440000
