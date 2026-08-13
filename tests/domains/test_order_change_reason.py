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


def test_schedule_change_requires_reason():
    """일정 변경도 사유 대상 — 누가 옮겼는지가 아니라 왜 옮겼는지가 분쟁에서 쓰인다."""
    assert is_reason_required([_change("schedule.measurement.date")]) is True
    assert is_reason_required([_change("schedule.construction.time")]) is True


def test_stage_change_requires_reason():
    """단계 이동(취소 포함)."""
    assert is_reason_required([_change("workflow.stage")]) is True


def test_item_price_requires_reason_regardless_of_index():
    """품목 번호가 밀려도 판정은 같다 — 템플릿(``items.*.price``)으로 대조한다."""
    assert is_reason_required([_change("items.0.price")]) is True
    assert is_reason_required([_change("items.7.price")]) is True


def test_item_composition_change_requires_reason():
    """품목이 통째로 들고 나면 ``add``/``remove`` 1건으로만 남아 단가 경로에 안 걸린다."""
    assert is_reason_required([_change("items.2", op="remove")]) is True
    assert is_reason_required([_change("items.3", op="add")]) is True


def test_non_sensitive_changes_do_not_require_reason():
    """연락처·주소·비고만 바뀐 저장은 묻지 않는다(모든 저장마다 물으면 기록이 소음이 된다)."""
    changes = [
        _change("parties.customer.phone"),
        _change("site.address_detail"),
        _change("notes"),
        _change("items.0.color"),
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
