"""주문 변경 사유 판정·정규화 계약 (ORDER-REASON-00).

여기서 고정하는 것: "무엇이 중요 변경인가"의 경계(너무 넓으면 직원이 아무 값이나 고르고,
너무 좁으면 분쟁 축이 빈다), 품목 번호와 무관한 판정, 목록 밖 코드 거부.

정본: docs/specs/2026-08-13-order-change-reason_SPEC.md
"""

import pytest

from foms.services.orders.change_reason import (
    REASON_CODES,
    REASON_NOTE_LIMIT,
    REASON_OTHER,
    REASON_UNSPECIFIED,
    is_material_amount_change,
    is_reason_required,
    normalize_reason,
    reason_label,
)
from foms.services.orders.structured_diff import diff_structured


def _change(path, op="set"):
    return {"path": path, "before": "1", "after": "2", "op": op}


def test_amount_input_change_requires_reason():
    """금액은 분쟁 1순위 축이다 — 단 **입력 경로**로 본다."""
    assert is_reason_required([_change("payment.deposit")]) is True
    assert is_reason_required([_change("payment.discount")]) is True
    assert is_reason_required([_change("items.0.price")]) is True


def test_derived_totals_alone_do_not_require_reason():
    """``totals.*`` 는 서버가 매 저장마다 재계산하는 파생값이다.

    저장된 totals 가 낡은 주문(=운영에 흔하다)에서 전화번호만 고쳐도 재계산 차이가 생기는데,
    그것까지 "금액 변경"으로 보면 사유 창이 아무 때나 뜬다(2026-08-13 실측으로 확인).
    진짜 금액 변경은 그 값을 만든 입력 경로가 함께 바뀌므로 놓치지 않는다.
    """
    derived = [
        _change("totals.items_total"),
        _change("totals.final_amount"),
        _change("totals.balance_amount"),
        _change("totals.shipping_price"),
    ]
    assert is_reason_required(derived) is False
    assert is_reason_required(derived + [_change("items.0.price")]) is True


def test_axis_scope_is_narrow():
    """묻는 축은 시공일·금액·제품 세부·단계뿐이다(사용자 결정 2026-08-14).

    실측일·AS 방문일은 **일부러** 뺐다. 축을 넓히면 사유 창이 아무 때나 떠서 직원이 목록에서
    아무거나 고르게 된다.
    """
    assert is_reason_required([_change("schedule.measurement.date")]) is False
    assert is_reason_required([_change("schedule.as_visit.date")]) is False
    assert is_reason_required([_change("schedule.construction.time")], stage="CONFIRM") is True


def test_stage_move_is_asked_again():
    """단계 이동(취소·보류 포함)은 축으로 되살렸다 — "왜 취소했나"가 분쟁 1순위 질문이다.

    다만 FOMS 의 주문 취소는 구조화 저장이 아니라 휴지통 이동(``ORDER_SOFT_DELETED``)이라
    여기서 잡히는 것은 저장으로 일어나는 단계 이동뿐이다.
    """
    assert is_reason_required([_change("workflow.stage")]) is True


def test_item_detail_change_requires_reason():
    """제품 세부 내역(규격·색상·손잡이·옵션)은 사유 대상이다."""
    for field in ("spec", "spec_width", "color", "handle", "option_detail", "product_name"):
        assert is_reason_required([_change(f"items.0.{field}")]) is True, field
    assert is_reason_required([_change("items.0.internal")]) is False   # 내부 메모는 제품 사양이 아니다


def test_item_price_requires_reason_regardless_of_index():
    """품목 번호가 밀려도 판정은 같다 — 템플릿(``items.*.price``)으로 대조한다."""
    assert is_reason_required([_change("items.0.price")]) is True
    assert is_reason_required([_change("items.7.price")]) is True


def test_item_removal_asked_but_addition_is_not():
    """있던 품목이 빠지는 것은 변경, 새로 다는 것은 최초 입력이다."""
    assert is_reason_required([_change("items.2", op="remove")]) is True
    assert is_reason_required([_change("items.3", op="add")]) is False


def test_first_entry_is_not_a_change():
    """빈칸을 처음 채우는 입력은 묻지 않는다 (사용자 결정 2026-08-14).

    접수 직후 규격·금액을 채우는 것까지 사유를 물으면 신규 주문 한 건에 창이 여러 번 뜨고,
    정작 분쟁이 나는 **재조정**과 구별되지 않는다.
    """
    first_entry = [
        {"path": "items.0.price", "before": None, "after": "500000", "op": "add"},
        {"path": "items.0.spec", "before": "", "after": "W1200", "op": "set"},
        {"path": "schedule.construction.date", "before": None, "after": "2026-08-27", "op": "add"},
    ]
    assert is_reason_required(first_entry, stage="CONFIRM") is False

    edited = [{"path": "items.0.spec", "before": "W1200", "after": "W1500", "op": "set"}]
    assert is_reason_required(edited) is True


def test_non_sensitive_changes_do_not_require_reason():
    """연락처·주소·비고만 바뀐 저장은 묻지 않는다(모든 저장마다 물으면 기록이 소음이 된다)."""
    changes = [
        _change("parties.customer.phone"),
        _change("site.address_detail"),
        _change("notes"),
        _change("flags.urgent"),
    ]
    assert is_reason_required(changes) is False


def test_empty_diff_does_not_require_reason():
    assert is_reason_required([]) is False
    assert is_reason_required(None) is False


def test_required_judgement_runs_on_real_diff_output():
    """실제 ``diff_structured`` 출력 형태로도 판정된다(경로 문법이 어긋나면 여기서 깨진다)."""
    old = {"items": [{"product_name": "장", "price": "500000"}]}
    new = {"items": [{"product_name": "장", "price": "620000"}]}

    result = diff_structured(old, new, max_changes=-1)

    assert [change["path"] for change in result.changes] == ["items.0.price"]
    assert is_reason_required(result.changes) is True


def test_normalize_rejects_unknown_code():
    """목록 밖 코드를 허용하면 목록으로 받은 의미(집계)가 사라진다."""
    with pytest.raises(ValueError):
        normalize_reason("made_up", "")


def test_normalize_rejects_unspecified_as_user_input():
    """``unspecified`` 는 서버 집계 키다 — 사용자가 고를 수 있는 값이 아니다."""
    with pytest.raises(ValueError):
        normalize_reason(REASON_UNSPECIFIED, "")


def test_other_requires_note():
    with pytest.raises(ValueError):
        normalize_reason(REASON_OTHER, "   ")

    code, note = normalize_reason(REASON_OTHER, " 창고 재고 소진 ")
    assert (code, note) == (REASON_OTHER, "창고 재고 소진")


def test_note_is_clipped_to_column_limit():
    """컬럼 상한 초과로 감사 쓰기가 실패해 저장 트랜잭션을 죽이는 일이 없어야 한다."""
    _, note = normalize_reason(REASON_OTHER, "가" * (REASON_NOTE_LIMIT + 50))
    assert len(note) == REASON_NOTE_LIMIT


def test_listed_codes_have_labels():
    """화면 노출 코드는 전부 라벨이 있어야 한다(라벨 없는 코드는 화면에 코드가 그대로 뜬다)."""
    for code in REASON_CODES:
        assert reason_label(code) != code
    assert reason_label(None) == reason_label(REASON_UNSPECIFIED)


# ---------------------------------------------------------------------------
# 금액 임계 — "바뀌었나"가 아니라 "크게 바뀌었나" (사용자 결정 2026-08-13)
# ---------------------------------------------------------------------------

def _amount(before, after, path="items.0.price"):
    return {"path": path, "before": before, "after": after, "op": "set"}


def test_small_amount_change_does_not_require_reason():
    """50만원짜리의 2만원(4%) 조정은 묻지 않는다 — 잔돈까지 물으면 창이 아무 때나 뜬다."""
    assert is_reason_required([_amount("500000", "520000")]) is False
    assert is_reason_required([_amount("1,000,000", "1,030,000")]) is False


def test_absolute_threshold_triggers():
    """5만원 이상 움직이면 비율과 무관하게 묻는다."""
    assert is_reason_required([_amount("1000000", "1060000")]) is True
    assert is_reason_required([_amount("500000", "450000")]) is True     # 인하도 같다


def test_ratio_threshold_triggers_on_small_base():
    """작은 금액에서는 5% 가 5만원보다 먼저 걸린다."""
    assert is_reason_required([_amount("10000", "11000")]) is True
    assert is_material_amount_change({"before": "10000", "after": "10100"}) is False


def test_unreadable_amount_is_treated_as_material():
    """숫자로 못 읽는 값은 묻는 쪽으로 — 감사에서 "몰라서 안 물었다"는 변명이 안 된다."""
    assert is_material_amount_change({"before": "협의", "after": "미정"}) is True


def test_payment_inputs_use_the_same_threshold():
    """계약금·할인도 금액 축이라 같은 기준을 쓴다."""
    assert is_reason_required([_amount("300000", "310000", path="payment.deposit")]) is False
    assert is_reason_required([_amount("300000", "380000", path="payment.deposit")]) is True


def test_schedule_has_no_threshold():
    """일정은 하루만 밀려도 분쟁 축이다 — 임계 없이 묻는다."""
    assert is_reason_required([{
        "path": "schedule.construction.date", "before": "2026-08-20",
        "after": "2026-08-21", "op": "set",
    }]) is True


# ---------------------------------------------------------------------------
# 시공 일정 — 확정(고객 컨펌) 이후에만 묻는다 (사용자 결정 2026-08-13)
# ---------------------------------------------------------------------------

def _construction(path="schedule.construction.date"):
    return {"path": path, "before": "2026-08-20", "after": "2026-08-27", "op": "set"}


def test_construction_date_before_confirm_is_not_asked():
    """접수·실측·도면 단계의 시공일은 아직 "잡는 중"이라 바뀌는 게 정상이다."""
    for stage in ("RECEIVED", "MEASURE", "DRAWING"):
        assert is_reason_required([_construction()], stage=stage) is False


def test_construction_date_after_confirm_is_asked():
    """고객 컨펌 뒤의 시공일은 고객과 약속된 날짜다 — 바꾸면 사유가 남아야 한다."""
    for stage in ("CONFIRM", "PRODUCTION", "CONSTRUCTION", "COMPLETED"):
        assert is_reason_required([_construction()], stage=stage) is True

    assert is_reason_required([_construction("items.0.construction_date")], stage="CONFIRM") is True


def test_unknown_stage_falls_back_to_asking():
    """단계를 못 읽었다는 이유로 기록이 비면 안 된다 — 모르면 묻는다."""
    assert is_reason_required([_construction()]) is True
    assert is_reason_required([_construction()], stage="") is True


def test_measurement_schedule_is_out_of_scope():
    """실측일은 축에서 빠졌다 — 단계와 무관하게 묻지 않는다(사용자 결정 2026-08-14)."""
    change = {"path": "schedule.measurement.date", "before": "2026-08-14",
              "after": "2026-08-16", "op": "set"}
    assert is_reason_required([change], stage="RECEIVED") is False
    assert is_reason_required([change], stage="CONFIRM") is False
