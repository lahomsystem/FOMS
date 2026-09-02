"""실측방 채널톡 PUSH 본문 조립 (서버 SSOT — PC 변환 텍스트의 서버 미러).

PC 주문 폼의 실측 PUSH 본문은 클라이언트 DOM 리더 ``erpGenerateConversionText``
(:file:`static/js/orders/erp-order-shared.js`)가 만든다. 모바일 주문등록 마법사에는
그 DOM(``#erp-*``)이 없고 주문 행도 아직 없으므로 클라이언트가 같은 본문을 만들 수 없다.
JS 사본을 한 벌 더 두면 같은 주문이 화면에 따라 다른 문구로 나가는 드리프트가 나므로,
:mod:`foms.services.channel_as_message` 선례처럼 **서버가 sd 하나로 단독 조립**한다.

입력은 DOM 이 아니라 주문 ``structured_data``(초안이면
:func:`foms.api.erp_order_draft._draft_payload_to_structured` 의 반환값)다.

포맷(PC 변환 텍스트와 동일 — 라벨의 공백까지 같다)::

    ★★                      ← flags.factory2 일 때만
    실측일 : 8월 14일
    시   간 : 오후 2시

    고객명 : 홍길동
    발주사 : 라홈
    시공일 : 상담
    주  소 : 서울시 ...
    연락처 : 010-0000-0000

    1.
    제품명 : 붙박이장
    규 격 : 2400*600*2400
    항목 견적 : 1,200,000원

    담당자 : 문정현

    출고가 : 1,200,000원
    예약금(선금) : 200,000원
    잔금 : 1,000,000원

값이 빈 줄은 통째로 생략한다(PC 와 동일 — 빈 라벨 줄이 발주방에 나가지 않게).
"""

from __future__ import annotations

import re
from typing import Any

# _append_line 은 erpAppendConversionTextLine 의 서버 미러다. AS PUSH 조립기가 이미 같은
# 규칙으로 갖고 있어 두 벌을 두지 않고 재사용한다(드리프트 방지 — 브리프 §8).
from foms.services.channel_as_message import _append_line, format_schedule_date_korean
from foms.services.erp_display import (
    erp_deposit_amount_from_structured,
    erp_shipping_price_from_structured,
)

__all__ = ["build_measure_push_text"]

_DEFAULT_ORDERER = "라홈"
_NO_CONSTRUCTION_DATE = "상담"
_BALANCE_CONFIRMED_SUFFIX = "(결제 완)"
_FREE_INPUT_SUFFIX = "(총견적 포함)"
_TRAILING_NEWLINES_RE = re.compile(r"\n+$")
_FREE_INPUT_LABEL_RE = re.compile(r"^(.+?)[:：]\s*(.+)$")
_TRUTHY_STRINGS = frozenset({"true", "1", "yes", "on"})
#: PC 가 노트를 담는 dict 키. sd['notes'] 는 마법사·구주문에서 **문자열**일 수 있으므로
#: (project memory: structured_data notes 는 문자열이 canonical) 형 검사 후에만 읽는다.
_NOTE_KEYS = ("measurement_note", "construction_note", "address_note", "phone_note")


# ---------------------------------------------------------------------------
# 값 읽기 helper (클라이언트 헬퍼의 서버 미러)
# ---------------------------------------------------------------------------


def _node(container: Any, *keys: str) -> dict:
    """중첩 dict 를 안전하게 따라간다(중간이 dict 가 아니면 빈 dict)."""
    node = container if isinstance(container, dict) else {}
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return {}
    return node


def _text(value: Any) -> str:
    """표시값을 문자열로 정규화한다(None → 빈 문자열, 앞뒤 공백 제거)."""
    return str(value or "").strip()


def _bool_flag(value: Any) -> bool:
    """체크박스 계열 값을 bool 로 읽는다(``_erpBoolConfirmed`` 미러)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return False


def _coerce_amount(value: Any) -> int:
    """금액 값을 원 단위 정수로 만든다(``erpCoerceAmount`` 미러).

    문자열은 숫자만 추려 읽는다(``1,200,000원`` → ``1200000``). 음수·비유한 수는 0.

    Args:
        value: 숫자·숫자 문자열·``{'amount': ...}`` 형태의 금액 값.

    Returns:
        0 이상의 정수 금액.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, dict):
        return _coerce_amount(value.get("amount") or value.get("raw") or 0)
    if isinstance(value, (int, float)):
        return int(round(value)) if value > 0 else 0
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else 0


def _format_money(amount: int) -> str:
    """``1200000`` → ``1,200,000원`` (``erpFormatMoneyKRW`` 미러)."""
    return f"{amount:,}원"


def _notes_map(sd: dict) -> dict[str, str]:
    """``sd['notes']`` 에서 특이사항 4종을 읽는다(문자열 notes 는 빈 dict).

    Args:
        sd: 주문 structured_data.

    Returns:
        ``{'measurement_note': ..., ...}`` — 없는 키는 빈 문자열.
    """
    notes = sd.get("notes")
    if not isinstance(notes, dict):
        return {key: "" for key in _NOTE_KEYS}
    return {key: _text(notes.get(key)) for key in _NOTE_KEYS}


# ---------------------------------------------------------------------------
# 줄 조립 helper
# ---------------------------------------------------------------------------


def _append_money_line(text: str, label: str, amount: Any, suffix: str = "") -> str:
    """``label : 1,200,000원`` 한 줄을 덧붙인다(0원 이하면 줄 자체를 생략).

    ``erpAppendConversionMoneyLine`` 의 서버 미러다.

    Args:
        text: 지금까지 조립된 본문.
        label: 줄 라벨(예: ``출고가``).
        amount: 금액 값(문자열·숫자 모두 허용).
        suffix: 금액 뒤에 붙일 꼬리표(예: ``(결제 완)``).

    Returns:
        줄이 덧붙은 본문.
    """
    value = _coerce_amount(amount)
    if value <= 0:
        return text
    return f"{text}{label} : {_format_money(value)}{suffix}\n"


def _append_extra_input_line(text: str, value: Any) -> str:
    """품목 추가 입력 블록(``추가 입력 : ...``)을 덧붙인다.

    ``erpAppendConversionExtraInputLine`` 의 서버 미러 — 첫 줄에만 라벨을 달고
    나머지 줄은 라벨 없이 이어 붙인다.

    Args:
        text: 지금까지 조립된 품목 블록.
        value: 추가 입력 원문(여러 줄 허용).

    Returns:
        블록이 덧붙은 본문.
    """
    raw = _text(value)
    if not raw:
        return text
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first = lines[0].strip()
    if not first:
        return text
    out = f"{text}추가 입력 : {first}\n"
    for line in lines[1:]:
        stripped = line.strip()
        if stripped:
            out += f"{stripped}\n"
    return out


def _format_free_input_line(line: str) -> str:
    """자유입력 한 줄을 표시용으로 정규화한다(``erpFormatFreeInputForConversionLine`` 미러).

    ``배송비:50000`` → ``배송비 : 50,000원``. 금액으로 읽히지 않으면 원문을 지키는데,
    사용자가 적은 자유 문구(예: ``현장 협의``)를 숫자 추출로 뭉개지 않기 위해서다.

    Args:
        line: 자유입력 한 줄.

    Returns:
        정규화된 한 줄(빈 줄이면 빈 문자열).
    """
    trimmed = line.strip()
    if not trimmed:
        return ""
    match = _FREE_INPUT_LABEL_RE.match(trimmed)
    if match:
        label = match.group(1).strip()
        amount_part = match.group(2).strip()
        if amount_part.endswith("원"):
            return f"{label} : {amount_part}"
        amount = _coerce_amount(amount_part)
        return f"{label} : {_format_money(amount)}" if amount > 0 else trimmed
    if trimmed.endswith("원"):
        return trimmed
    amount = _coerce_amount(trimmed)
    return _format_money(amount) if amount > 0 else trimmed


def _append_free_input_block(text: str, value: Any) -> str:
    """자유입력 블록을 덧붙인다(각 줄 끝에 ``(총견적 포함)``).

    ``erpAppendConversionFreeInputBlock`` 의 서버 미러.

    Args:
        text: 지금까지 조립된 본문.
        value: ``payment.free_input`` 원문(여러 줄 허용).

    Returns:
        블록이 덧붙은 본문(자유입력이 없으면 원본 그대로).
    """
    raw = _text(value).replace("\r\n", "\n").replace("\r", "\n")
    if not raw:
        return text
    lines = [_format_free_input_line(line) for line in raw.split("\n")]
    kept = [f"{line}{_FREE_INPUT_SUFFIX}" for line in lines if line]
    if not kept:
        return text
    return text + "\n".join(kept) + "\n"


# ---------------------------------------------------------------------------
# 블록 조립
# ---------------------------------------------------------------------------


def _header_block(sd: dict) -> str:
    """실측 블록 + 고객/현장 블록을 조립한다(PC 헤더와 동일 순서).

    Args:
        sd: 주문 structured_data.

    Returns:
        헤더 본문(비어 있으면 빈 문자열).
    """
    notes = _notes_map(sd)
    measure = _node(sd, "schedule", "measurement")
    construction = _node(sd, "schedule", "construction")
    customer = _node(sd, "parties", "customer")
    site = _node(sd, "site")

    text = "★★\n" if _bool_flag(_node(sd, "flags").get("factory2")) else ""
    text = _append_line(text, "실측일", format_schedule_date_korean(measure.get("date")))
    text = _append_line(text, "시   간", _text(measure.get("time")))
    text = _append_line(text, "실측 특이사항", notes["measurement_note"])
    if text:
        text += "\n"
    text = _append_line(text, "고객명", _text(customer.get("name")))
    text = _append_line(
        text, "발주사", _text(_node(sd, "parties", "orderer").get("name")) or _DEFAULT_ORDERER
    )
    construction_date = format_schedule_date_korean(construction.get("date")) or _NO_CONSTRUCTION_DATE
    text = _append_line(text, "시공일", construction_date)
    text = _append_line(text, "시공 특이사항", notes["construction_note"])
    text = _append_line(text, "시공시간", _text(construction.get("time")))
    text = _append_line(
        text, "주  소", _text(site.get("address_full")) or _text(site.get("address_main"))
    )
    text = _append_line(text, "주소 특이사항", notes["address_note"])
    text = _append_line(text, "연락처", _text(customer.get("phone")))
    text = _append_line(text, "연락처 특이사항", notes["phone_note"])
    if text and not text.endswith("\n\n"):
        text += "\n"
    return text


def _spec_label(item: dict) -> str:
    """품목 규격 표시값을 만든다.

    저장된 ``spec`` 문자열을 우선한다(사용자가 직접 적은 규격을 spec_rows 로 덮지
    않기 위해서 — PC 의 ``rawSpec || specParts`` 와 같은 우선순위). 없으면
    ``spec_rows[]`` 를 ``w*d*h`` 로 조립해 ``, `` 로 잇는다(빈 축은 제외).

    Args:
        item: structured_data.items 의 한 항목.

    Returns:
        ``2400*600*2400, 900*600*2400`` 형태의 표시값(없으면 빈 문자열).
    """
    raw_spec = _text(item.get("spec"))
    if raw_spec:
        return raw_spec
    rows = item.get("spec_rows")
    if not isinstance(rows, list):
        return ""
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        axes = [
            _text(row.get("spec_width")),
            _text(row.get("spec_depth")),
            _text(row.get("spec_height")),
        ]
        joined = "*".join(axis for axis in axes if axis)
        if joined:
            parts.append(joined)
    return ", ".join(parts)


def _item_block(item: dict) -> str:
    """품목 1건 블록을 조립한다(값 없는 줄은 생략, 전부 비면 빈 문자열).

    Args:
        item: structured_data.items 의 한 항목.

    Returns:
        품목 블록(끝에 개행 1개 포함) 또는 빈 문자열.
    """
    block = ""
    block = _append_line(block, "제품명", _text(item.get("product_name")))
    block = _append_line(block, "규 격", _spec_label(item))
    block = _append_line(block, "내 부", _text(item.get("internal")))
    block = _append_line(block, "색 상", _text(item.get("color")))
    block = _append_line(block, "옵 션", _text(item.get("option_detail")))
    block = _append_line(block, "손잡이", _text(item.get("handle")))
    block = _append_line(block, "기 타", _text(item.get("misc")))
    block = _append_money_line(block, "항목 견적", item.get("price"))
    return _append_extra_input_line(block, item.get("extra_input"))


def _items_block(text: str, sd: dict) -> str:
    """품목 블록들을 덧붙인다(품목이 2건 이상이면 ``1.``/``2.`` 번호 줄).

    번호 판정 모수는 **전체 품목 수**다 — 빈 품목이 섞여 있어도 PC 와 같은 기준을
    쓰기 위해서(``rows.length``), 실제 출력 순번만 보이는 품목으로 센다.

    Args:
        text: 지금까지 조립된 본문.
        sd: 주문 structured_data.

    Returns:
        품목 블록이 덧붙은 본문.
    """
    items = sd.get("items")
    if not isinstance(items, list) or not items:
        return text
    item_count = len(items)
    visible = 0
    for raw in items:
        block = _item_block(raw) if isinstance(raw, dict) else ""
        if not block:
            continue
        visible += 1
        if item_count >= 2:
            text += f"{visible}.\n"
        text += block + "\n"
    return text


def _shipping_price(sd: dict, totals: dict) -> int:
    """출고가(품목합 + 자유입력 − 할인). ``totals.shipping_price`` 를 우선한다."""
    direct = _coerce_amount(totals.get("shipping_price"))
    if direct > 0:
        return direct
    derived = erp_shipping_price_from_structured(sd)
    return int(derived) if derived else 0


def _deposit_amount(sd: dict, totals: dict) -> int:
    """예약금(선금). ``totals.deposit_amount`` 를 우선하고 ``payment.deposit`` 로 폴백."""
    direct = _coerce_amount(totals.get("deposit_amount"))
    if direct > 0:
        return direct
    stored = erp_deposit_amount_from_structured(sd)
    return int(stored) if stored else 0


def _final_amount(totals: dict, shipping: int, deposit: int) -> int:
    """잔금. 저장된 ``final_amount``/``balance_amount`` 를 우선하고 없으면 파생한다."""
    for key in ("final_amount", "balance_amount"):
        if key in totals:
            return _coerce_amount(totals.get(key))
    return max(0, shipping - deposit)


def _footer_block(text: str, sd: dict) -> str:
    """담당자 + 금액 푸터를 덧붙인다(PC 푸터와 동일 순서·조건).

    Args:
        text: 헤더·품목까지 조립된 본문.
        sd: 주문 structured_data.

    Returns:
        푸터가 덧붙은 본문.
    """
    payment = _node(sd, "payment")
    totals = _node(sd, "totals")
    shipping = _shipping_price(sd, totals)
    deposit = _deposit_amount(sd, totals)
    final_amount = _final_amount(totals, shipping, deposit)

    footer_start = len(text)
    text = _append_line(text, "담당자", _text(_node(sd, "parties", "manager").get("name")))
    if len(text) > footer_start:
        text += "\n"
    text = _append_money_line(text, "출고가", shipping)
    text = _append_money_line(text, "예약금(선금)", deposit)
    text = _append_free_input_block(text, _free_input_text(sd))
    suffix = _BALANCE_CONFIRMED_SUFFIX if _bool_flag(payment.get("balance_confirmed")) else ""
    text = _append_money_line(text, "잔금", final_amount, suffix)
    text = _append_line(text, "잔금메모", _text(payment.get("balance_note")))
    cash_receipt = _text(payment.get("cash_receipt"))
    if cash_receipt and final_amount > 0:
        text += "\n"
    return _append_line(text, "현금영수증", cash_receipt)


def _free_input_text(sd: dict) -> str:
    """자유입력 원문을 읽는다(``payment.free_input`` / 구주문 ``payments`` 폴백)."""
    # estimate_service 는 모델 계층을 끌고 오므로 함수 지역에서 import 한다
    # (erp_display 가 같은 이유로 쓰는 패턴 — 모듈 로드 시 순환 import 방지).
    from foms.services.estimate_service import _extract_free_input_text

    return _extract_free_input_text(sd)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def build_measure_push_text(sd: dict) -> str:
    """실측방 채널톡 PUSH 본문을 sd 로 조립한다(PC ``erpGenerateConversionText`` 서버 미러).

    초안(주문 등록 전) 발송도 **본문이 PC 와 완전히 같아야 한다**(사용자 결정 2026-09-02).
    초안임을 알리는 머리말은 붙이지 않는다 — 실측방이 받는 글의 모양이 어디서 보냈느냐에
    따라 달라지면 읽는 쪽이 두 벌을 익혀야 한다.

    Args:
        sd: 주문 structured_data(초안이면 ``_draft_payload_to_structured`` 결과).

    Returns:
        전송 본문. 빈 sd 라도 기본값 두 줄(``발주사 : 라홈``·``시공일 : 상담``)은 남는다 —
        PC 변환 텍스트가 빈 폼에서 내는 결과와 같다(호출자는 "값 없음"을 이 본문이 아니라
        일정·연락처 같은 자격 조건으로 판정해야 한다).
    """
    data = sd if isinstance(sd, dict) else {}
    text = _header_block(data)
    text = _items_block(text, data)
    text = _footer_block(text, data)
    return _TRAILING_NEWLINES_RE.sub("", text)
