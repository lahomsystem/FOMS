"""카카오 알림톡 v1 — 실측 예약 확정 템플릿의 변수 빌더·자격 판정.

발송(Solapi)·멱등 outbox·이력 기록은 이 모듈 범위 밖(T2)이며, 여기 있는 함수는
전부 순수 함수다(외부 호출·DB 접근 없음).
"""

from __future__ import annotations

import re
from typing import Any

from foms.services.erp_display import erp_deposit_amount_from_structured
from foms.services.order_date_sync import _normalize_date_str

__all__ = [
    "ALIMTALK_TEMPLATE_MEASURE",
    "ALIMTALK_MAX_BODY_LEN",
    "normalize_measure_schedule",
    "build_dedupe_key",
    "extract_valid_phone",
    "build_variables",
    "render_preview",
]

#: 심사 제출 확정본(스펙 §5). 제출 후 수정 불가 — 문자열 변경 금지.
ALIMTALK_TEMPLATE_MEASURE = """안녕하세요 #{고객명} 고객님, 실측 예약이 정상적으로 완료되었습니다.
일정 변경이 있을 경우 아래 문의하기 버튼으로 미리 연락 부탁드립니다.

실측일 : #{실측일}
시  간 : #{실측시간}

고객명 : #{고객명}
발주사 : #{발주사}
시공일 : #{시공일}
주  소 : #{주소}
연락처 : #{연락처}

#{품목내역}

예약금(선금) : #{예약금}"""

#: 치환 후 본문 하드 상한(스펙 §5).
ALIMTALK_MAX_BODY_LEN = 1000

#: 알림톡 변수는 비울 수 없어 빈값은 폴백 문구로 채운다(스펙 §5).
_CONSULT = "상담"
_UNDECIDED = "미정"
_DEFAULT_ORDERER = "라홈"

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE_SPLIT_RE = re.compile(r"[/,;\n]")

#: `#{품목내역}` 블록 6줄. 값 후보 키는 앞에서부터 먼저 채워진 것을 쓴다.
_ITEM_FIELD_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("제품명", ("product_name",)),
    ("내 부", ("internal",)),
    ("색 상", ("color",)),
    ("옵 션", ("option_detail", "option")),
    ("손잡이", ("handle",)),
    ("기 타", ("misc",)),
)


def _node(sd: Any, *keys: str) -> dict[str, Any]:
    """중첩 dict를 안전하게 따라간다. 경로 중간이 dict가 아니면 빈 dict."""
    current = sd
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _valid_dates(raw: Any) -> list[str]:
    """콤마 다중 일자를 ``YYYY-MM-DD``로 정규화한다(정렬·중복제거, 실패 토큰 제외)."""
    normalized: set[str] = set()
    for token in str(raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        candidate = str(_normalize_date_str(token) or "")
        if _ISO_DATE_RE.match(candidate):
            normalized.add(candidate)
    return sorted(normalized)


def _korean_dates(raw: Any) -> str:
    """``YYYY-MM-DD`` 목록을 ``8월 14일, 8월 15일`` 표기로. 유효 0건이면 '상담'."""
    dates = _valid_dates(raw)
    if not dates:
        return _CONSULT
    return ", ".join(f"{int(d[5:7])}월 {int(d[8:10])}일" for d in dates)


def normalize_measure_schedule(sd: dict | None) -> tuple[str, str] | None:
    """실측 일정을 canonical 형태로 만든다.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``(dates, time)`` — dates는 정렬·중복제거된 ``YYYY-MM-DD``의 ``|`` 결합,
        time은 strip한 원문. 유효 날짜 0건이면 ``None``(발송 미자격).
    """
    measure = _node(sd, "schedule", "measurement")
    dates = _valid_dates(measure.get("date"))
    if not dates:
        return None
    return "|".join(dates), str(measure.get("time") or "").strip()


def build_dedupe_key(order_id: int, sd: dict | None) -> str | None:
    """자동 발송 멱등키를 만든다.

    Args:
        order_id: 주문 id.
        sd: 주문 structured_data.

    Returns:
        ``alimtalk:measure:{order_id}:{dates}:{time}``. 미자격이면 ``None``.
    """
    schedule = normalize_measure_schedule(sd)
    if schedule is None:
        return None
    dates, time = schedule
    return f"alimtalk:measure:{order_id}:{dates}:{time}"


def extract_valid_phone(sd: dict | None) -> str | None:
    """고객 휴대폰 번호를 숫자만 남겨 추출한다.

    Args:
        sd: 주문 structured_data.

    Returns:
        10~11자리이고 ``01``로 시작하는 첫 번째 토큰(숫자만). 없으면 ``None``.
    """
    raw = _node(sd, "parties", "customer").get("phone")
    for token in _PHONE_SPLIT_RE.split(str(raw or "")):
        digits = re.sub(r"\D", "", token)
        if 10 <= len(digits) <= 11 and digits.startswith("01"):
            return digits
    return None


def _item_block(item: dict[str, Any]) -> str:
    """품목 1건을 6줄 블록으로 만든다(빈 필드는 '상담')."""
    lines: list[str] = []
    for label, keys in _ITEM_FIELD_LABELS:
        value = ""
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                break
        lines.append(f"{label} : {value or _CONSULT}")
    return "\n".join(lines)


def _items_text(items: Any) -> str:
    """품목 블록들을 빈 줄로 이어 붙인다. 품목이 없으면 '상담'."""
    blocks = [_item_block(it) for it in items if isinstance(it, dict)] if isinstance(items, list) else []
    return "\n\n".join(blocks) if blocks else _CONSULT


def _substitute(variables: dict[str, str]) -> str:
    """템플릿에 변수를 로컬 치환한다(Solapi 서버 렌더와 동일 규칙)."""
    text = ALIMTALK_TEMPLATE_MEASURE
    for name, value in variables.items():
        text = text.replace(name, value)
    return text


def _shrink_items(variables: dict[str, str], items: Any) -> None:
    """품목내역을 '첫 품목 블록 + 외 N건'으로 축약한다(길이 초과 1차 대응)."""
    blocks = [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []
    if len(blocks) > 1:
        variables["#{품목내역}"] = f"{_item_block(blocks[0])}\n외 {len(blocks) - 1}건"


def _enforce_length(variables: dict[str, str]) -> None:
    """치환 결과가 상한을 넘으면 가장 긴 변수부터 잘라 하드 가드를 만족시킨다."""
    for _ in range(len(variables)):
        excess = len(_substitute(variables)) - ALIMTALK_MAX_BODY_LEN
        if excess <= 0:
            return
        key = max(variables, key=lambda name: len(variables[name]))
        keep = len(variables[key]) - excess - 1
        variables[key] = variables[key][:keep] + "…" if keep > 0 else _CONSULT


def build_variables(sd: dict | None) -> dict[str, str]:
    """알림톡 템플릿 변수 dict를 만든다.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``{'#{고객명}': '임다슬', ...}`` — 키는 중괄호 포함 변수명. 빈값은 폴백 문구로
        채워지며, 치환 후 길이가 ``ALIMTALK_MAX_BODY_LEN``을 넘지 않도록 축약된다.
    """
    customer = _node(sd, "parties", "customer")
    measure = _node(sd, "schedule", "measurement")
    site = _node(sd, "site")
    items = sd.get("items") if isinstance(sd, dict) else None
    deposit = erp_deposit_amount_from_structured(sd if isinstance(sd, dict) else {})

    variables = {
        "#{고객명}": str(customer.get("name") or "").strip() or _CONSULT,
        "#{실측일}": _korean_dates(measure.get("date")),
        "#{실측시간}": str(measure.get("time") or "").strip() or _UNDECIDED,
        "#{발주사}": str(_node(sd, "parties", "orderer").get("name") or "").strip() or _DEFAULT_ORDERER,
        "#{시공일}": _korean_dates(_node(sd, "schedule", "construction").get("date")),
        "#{주소}": str(site.get("address_full") or site.get("address_main") or "").strip() or _CONSULT,
        "#{연락처}": str(customer.get("phone") or "").strip() or _CONSULT,
        "#{품목내역}": _items_text(items),
        "#{예약금}": f"{deposit:,}원" if deposit is not None else _CONSULT,
    }

    if len(_substitute(variables)) > ALIMTALK_MAX_BODY_LEN:
        _shrink_items(variables, items)
    _enforce_length(variables)
    return variables


def render_preview(sd: dict | None) -> str:
    """저장본 sd로 알림톡 본문을 로컬 치환한 미리보기 텍스트를 만든다.

    Args:
        sd: 주문 structured_data.

    Returns:
        변수 치환이 끝난 본문(길이 ``ALIMTALK_MAX_BODY_LEN`` 이하 보장).
    """
    return _substitute(build_variables(sd))
