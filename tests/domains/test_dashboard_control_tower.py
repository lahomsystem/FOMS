"""컨트롤 타워 준비도/잔금 분류기 계약 테스트 (DB 불필요, 순수 함수)."""

from foms.services.orders import dashboard_control_tower as ct


class _Order:
    """경량 Order 스텁 (flat 컬럼 + structured_data만 노출)."""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.erp_stage_code = kw.get("erp_stage_code")
        self.manager_name = kw.get("manager_name")
        self.structured_data = kw.get("structured_data")


def test_to_int_parses_money_strings():
    assert ct._to_int("1,410,000원") == 1410000
    assert ct._to_int(5000) == 5000
    assert ct._to_int("  300000 ") == 300000


def test_to_int_rejects_invalid():
    assert ct._to_int(None) is None
    assert ct._to_int("없음") is None
    assert ct._to_int(True) is None  # bool은 금액이 아님


def test_balance_remaining_prefers_explicit_fields():
    assert ct._balance_remaining({"pricing": {"balance": "1,410,000"}}) == 1410000
    assert ct._balance_remaining({"totals": {"balance": 50000}}) == 50000


def test_balance_remaining_none_when_unknown():
    assert ct._balance_remaining({}) is None
    assert ct._balance_remaining({"pricing": {}, "totals": {}}) is None


def test_measure_readiness_warns_when_unassigned():
    state, label = ct._measure_readiness(_Order(structured_data={}), {})
    assert state == "warn" and label == "담당 미배정"


def test_measure_readiness_ok_by_manager_or_ids():
    assert ct._measure_readiness(_Order(manager_name="한용희"), {})[0] == "ok"
    sd = {"assignments": {"sales_assignee_user_ids": [7]}}
    assert ct._measure_readiness(_Order(), sd)[0] == "ok"


def test_construction_readiness_risk_when_not_yet_shipped():
    # 시공일인데 아직 생산/컨펌 단계 → 출고 미확인(위험)
    for code in ("PRODUCTION", "CONFIRM", "DRAWING", "RECEIVED"):
        state, label = ct._construction_readiness(_Order(erp_stage_code=code), {})
        assert state == "risk" and label == "출고 미확인"


def test_construction_readiness_ok_when_installed_and_paid():
    state, label = ct._construction_readiness(_Order(erp_stage_code="CONSTRUCTION"), {})
    assert state == "ok" and label == "준비완료"


def test_construction_readiness_warns_on_outstanding_balance():
    sd = {"pricing": {"balance": 100000}}
    state, label = ct._construction_readiness(_Order(erp_stage_code="CONSTRUCTION", structured_data=sd), sd)
    assert state == "warn" and label == "잔금 미수"


def test_risk_group_shape():
    g = ct._risk_group("k", "🔨", "red", "t", "why", 3, {"stage": "시공"})
    assert g["key"] == "k" and g["tone"] == "red" and g["count"] == 3
    assert g["filter"] == {"stage": "시공"}
