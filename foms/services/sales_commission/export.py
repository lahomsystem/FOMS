"""프리랜서 영업 수수료 마감 내려받기 CSV(설계서 FCOMM-01 §2.1-8 · §9 · J2 — 플랜 T10).

마감(``CLOSED``) · 지급 완료(``PAID``) 스냅샷만 파일로 만든다 — 파일 숫자가 실제로 준 돈과 같아야 해서다.
계산은 하지 않는다. 마감 때 굳힌 줄 · 합계 · 세금(:func:`foms.services.sales_commission.closing.closing_payload`)을
그대로 옮긴다.

- 표 계산 프로그램에서 한글이 깨지지 않게 첫 줄에 UTF-8 BOM, 줄바꿈은 CRLF(정산 채널 CSV 선례
  ``foms/services/settlement_channel_export.py``). 새 의존성 없음 — 표준 :mod:`csv` 만 쓴다.
- 금액은 쉼표 없는 정수, 날짜는 ``YYYY-MM-DD``. 요율은 % 숫자("4" · "4.5").
- 칸 순서는 회계팀 표와 같다: 시공 달 · 고객명 · 품목 · 거래구분 · 출고가 · 시공비 · 차감 · 요율(%) · 수수료 · 구분.
  스냅샷 줄은 시공일 대신 시공 완료 달을 갖고 있어 첫 칸이 "시공 달"이다.
- 줄 아래 빈 줄 하나 뒤에 요약: 합계 · (세금 방식에 맞는) 세금 줄 · 실지급 · 마감 상태 · 마감일 · 지급일.
  요약 값은 수수료 칸 아래에 둔다(합계가 수수료 열 맨 아래에 오도록).
- 사람이 적은 글(고객명 · 품목)이 ``=`` · ``+`` · ``@`` 등으로 시작하면 앞에 ``'`` 를 붙여 식으로 읽히지 않게 한다.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from foms.services.sales_commission import calc

__all__ = ["DEAL_LABELS", "HEADERS", "build_closing_csv", "export_filename"]

DEAL_LABELS = {
    calc.DEAL_LAHOM: "라홈",
    calc.DEAL_HAUD: "하우드",
    calc.DEAL_PERSONAL: "개인영업",
    calc.DEAL_MANUAL: "회계팀 지정",
}
KIND_LABELS = {"NORMAL": "정상", "ADJUST": "조정"}
STATUS_LABELS = {"CLOSED": "마감", "PAID": "지급 완료"}
HEADERS = ("시공 달", "고객명 · 품목", "거래구분", "출고가", "시공비", "차감", "요율(%)", "수수료", "구분")

_BOM = "﻿"
_CRLF = "\r\n"
_VALUE_COL = HEADERS.index("수수료")
_FORMULA_HEADS = ("=", "+", "@", "\t", "\r")


def _money(value: Any) -> str:
    try:
        return str(int(value or 0))
    except (TypeError, ValueError):
        return ""


def _percent(bp: Any) -> str:
    """basis point → % 숫자 글자. 400 → "4", 450 → "4.5", 425 → "4.25"."""
    try:
        number = int(bp)
    except (TypeError, ValueError):
        return ""
    return f"{number / 100:.2f}".rstrip("0").rstrip(".")


def _text(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_HEADS) or (text.startswith("-") and len(text) > 1):
        return "'" + text
    return text


def _day(value: Any) -> str:
    """``"2030-04-10 14:03"`` → ``"2030-04-10"``. 비었으면 빈 칸."""
    return str(value or "")[:10]


def _summary_row(label: str, value: str) -> list[str]:
    row = [""] * len(HEADERS)
    row[0] = label
    row[_VALUE_COL] = value
    return row


def _line_row(line: dict[str, Any]) -> list[str]:
    return [
        str(line.get("completion_month") or ""),
        _text(line.get("label") or "-"),
        DEAL_LABELS.get(line.get("deal_type"), str(line.get("deal_type") or "")),
        _money(line.get("shipping_price")),
        _money(line.get("install_cost")),
        _money(line.get("deduction_total")),
        _percent(line.get("rate_bp")),
        _money(line.get("commission")),
        KIND_LABELS.get(line.get("kind"), str(line.get("kind") or "")),
    ]


def _tax_rows(closing: dict[str, Any]) -> list[list[str]]:
    tax_type = closing.get("tax_type")
    if tax_type == calc.TAX_WITHHOLD_3_3:
        return [_summary_row("소득세", _money(closing.get("tax_income"))),
                _summary_row("지방소득세", _money(closing.get("tax_local")))]
    if tax_type == calc.TAX_VAT_10:
        return [_summary_row("부가세", _money(closing.get("vat")))]
    return []


def build_closing_csv(closing: dict[str, Any]) -> str:
    """마감 한 건(:func:`closing_payload` 모양, ``lines`` 포함) → CSV 글 전체(BOM 포함, CRLF).

    Args:
        closing: ``{month, status, gross, tax_income, tax_local, vat, net, tax_type, closed_at, paid_at, lines[]}``.

    Returns:
        BOM 으로 시작하고 줄마다 CRLF 로 끝나는 CSV 글.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=_CRLF)
    writer.writerow(HEADERS)
    for line in closing.get("lines") or []:
        if isinstance(line, dict):
            writer.writerow(_line_row(line))
    writer.writerow([])
    writer.writerow(_summary_row("합계", _money(closing.get("gross"))))
    for row in _tax_rows(closing):
        writer.writerow(row)
    writer.writerow(_summary_row("실지급", _money(closing.get("net"))))
    status = closing.get("status")
    writer.writerow(_summary_row("마감 상태", STATUS_LABELS.get(status, str(status or ""))))
    writer.writerow(_summary_row("마감일", _day(closing.get("closed_at"))))
    if status == "PAID":
        writer.writerow(_summary_row("지급일", _day(closing.get("paid_at"))))
    return _BOM + buffer.getvalue()


def export_filename(user_id: int, month: str) -> str:
    """ASCII 파일 이름 — ``sales-commission-<user_id>-<YYYY-MM>.csv``."""
    return f"sales-commission-{int(user_id)}-{month}.csv"
