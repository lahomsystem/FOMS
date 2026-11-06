"""정산 차감의 "유효" 판정 정본(설계서 FCOMM-01 §10.1 · D13).

차감 기록은 ``structured_data.settlement.deductions[]`` 한 곳에만 있다. 차감은 지우지 않고
취소 표시(``voided_at``)를 붙인다(§10.2) — 그래서 차감을 읽는 곳이 모두 같은 판정을 써야
"취소한 차감이 어느 화면에선 아직 청구됨으로 보이는" 일이 없다. 읽는 곳(완료 화면 ·
정산 실무 탭 · 정산 집계 · 수수료 계산)은 전부 이 모듈의 함수만 쓴다.

유효한 차감 = dict 이고 ``voided_at`` 이 비어 있다. 모양이 틀린 원소(글자 · 숫자)는 차감이 아니다.
"""
from __future__ import annotations

from typing import Any


def is_valid_deduction(entry: Any) -> bool:
    """차감 한 건이 유효한지 — dict 이고 취소 표시(``voided_at``)가 없다.

    Args:
        entry: ``settlement.deductions[]`` 원소(아무 모양이나 올 수 있다).

    Returns:
        유효하면 True.
    """
    return isinstance(entry, dict) and not entry.get("voided_at")


def settlement_valid_deductions(settlement: Any) -> list[dict]:
    """정산 묶음(``sd["settlement"]``)에서 유효한 차감만 원래 순서대로.

    Args:
        settlement: ``structured_data["settlement"]`` 값(dict 가 아니면 빈 목록).

    Returns:
        유효한 차감 dict 목록.
    """
    if not isinstance(settlement, dict):
        return []
    deductions = settlement.get("deductions")
    if not isinstance(deductions, list):
        return []
    return [entry for entry in deductions if is_valid_deduction(entry)]


def valid_deductions(sd: Any) -> list[dict]:
    """주문 ``structured_data`` 에서 유효한 차감만(칸이 없거나 모양이 틀리면 빈 목록).

    Args:
        sd: 주문 structured_data.

    Returns:
        유효한 차감 dict 목록.
    """
    return settlement_valid_deductions(sd.get("settlement") if isinstance(sd, dict) else None)


def has_valid_deduction(settlement: Any) -> bool:
    """유효한 차감이 하나라도 있는지 — 화면의 "청구됨" 표시 판정.

    Args:
        settlement: ``structured_data["settlement"]`` 값.

    Returns:
        하나라도 있으면 True.
    """
    return bool(settlement_valid_deductions(settlement))


__all__ = [
    "has_valid_deduction",
    "is_valid_deduction",
    "settlement_valid_deductions",
    "valid_deductions",
]
