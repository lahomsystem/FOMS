"""도면 마법사 자동 채움 defaults (서버 계산 SSOT).

도면 작업실 "도면 마법사" 페이지가 저장 상태 없이 최초 로드될 때 주문
``structured_data`` 로부터 폼 셀 기본값을 계산한다. 설계서
``docs/specs/2026-07-06-drawing-wizard_SPEC.md`` §4 매핑표가 계약이다.

모든 값은 문자열이며(``checks`` 제외), None은 항상 빈 문자열로 정규화한다.
'상담'(ERP 폼 placeholder)은 빈칸으로 처리한다.
"""

from __future__ import annotations

from typing import Any

from foms.services.erp_display import _normalize_date_to_yyyymmdd
from foms.services.erp_template_filters import (
    format_phone_filter,
    item_spec_w300_display,
)

__all__ = ["build_wizard_defaults"]

_CONSULT_PLACEHOLDER = "상담"

# 헤더 체크박스 8키 (설계서 §5). 기본값은 전부 False.
_WIZARD_CHECK_KEYS = (
    "d_site",
    "d_double",
    "d_order",
    "p_prod",
    "p_glass",
    "p_light",
    "p_handle",
    "p_etc",
)


def _as_str(value: Any) -> str:
    """None은 빈 문자열로, 그 외는 ``str()`` 로 강제 변환한다."""
    return "" if value is None else str(value)


def _consult_strip(value: Any) -> str:
    """'상담' placeholder(공백 strip 후 정확 일치)는 빈칸으로, 그 외는 문자열로 반환."""
    text = _as_str(value)
    return "" if text.strip() == _CONSULT_PLACEHOLDER else text


def _extract_items(sd: dict[str, Any]) -> list[dict[str, Any]]:
    """structured_data에서 제품 항목 리스트를 정규화 추출한다(erp_product_items 규칙)."""
    raw = sd.get("items") or sd.get("products") or sd.get("product_items") or []
    if isinstance(raw, dict):
        raw = [raw]
    return [item for item in list(raw) if isinstance(item, dict)]


def _join_product_names(items: list[dict[str, Any]]) -> str:
    """비어 있지 않은 제품명을 ' / ' 로 조인한다."""
    names = []
    for item in items:
        name = _as_str(item.get("product_name")).strip()
        if name:
            names.append(name)
    return " / ".join(names)


def _site_spec(item: dict[str, Any]) -> str:
    """width×depth×height(셋 다 있을 때), 아니면 ``spec`` 원문(없으면 빈칸)."""
    width = item.get("width") or item.get("spec_width")
    depth = item.get("depth") or item.get("spec_depth")
    height = item.get("height") or item.get("spec_height")
    if width and depth and height:
        return f"{width}×{depth}×{height}"
    return _as_str(item.get("spec"))


def _spec_w300(items: list[dict[str, Any]]) -> str:
    """items[0]의 시공 자수(W합/300) 표시값. 없으면 빈칸, 숫자는 ``str()`` 캐스팅."""
    if not items:
        return ""
    value = item_spec_w300_display(items[0])
    if value is None or value == "":
        return ""
    return str(value)


def _misc(item: dict[str, Any]) -> str:
    """misc 값('상담'→빈칸), 비어 있으면 ``option_detail`` 로 폴백한다."""
    misc = _consult_strip(item.get("misc"))
    return misc or _consult_strip(item.get("option_detail"))


def _korean_month_day(yyyymmdd: str) -> str:
    """'YYYY-MM-DD'를 'M월 D일'로 변환한다. 파싱 실패 시 원문 그대로."""
    parts = yyyymmdd.split("-")
    if len(parts) == 3:
        try:
            return f"{int(parts[1])}월 {int(parts[2])}일"
        except (TypeError, ValueError):
            return yyyymmdd
    return yyyymmdd


def _resolve_construction_dates(order: Any, sd: dict[str, Any]) -> list[str]:
    """워크벤치 ``_resolve_construction_date_display`` 규칙으로 정규화된 시공일 리스트."""
    raw = ((sd.get("schedule") or {}).get("construction") or {}).get("date")
    if raw:
        if isinstance(raw, str):
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            dates = [value for value in (_normalize_date_to_yyyymmdd(p) for p in parts) if value]
            if dates:
                return dates
        else:
            single = _normalize_date_to_yyyymmdd(raw)
            if single:
                return [single]
    fallback = _normalize_date_to_yyyymmdd(getattr(order, "erp_construction_date", None))
    return [fallback] if fallback else []


def _format_construction_date(order: Any, sd: dict[str, Any]) -> str:
    """정규화된 시공일 리스트를 'M월 D일' 한글 표기로 변환해 ', ' 로 조인한다."""
    return ", ".join(_korean_month_day(d) for d in _resolve_construction_dates(order, sd))


def _resolve_logo(manager_name: str) -> str:
    """도면 양식 로고 키: 발주사명에 '라홈' 포함 → 'lahom', 그 외 전부 → 'haud'.

    하우드/미지정/기타 발주사는 모두 하우드 로고를 쓴다('없음' 상태 폐지).
    전달 라우팅 규칙과 별개로, 도면 양식 로고는 라홈만 라홈 로고이고 나머지는
    전부 하우드 로고로 렌더한다.
    """
    if "라홈" in manager_name:
        return "lahom"
    return "haud"


def build_wizard_defaults(order: Any, sd: dict[str, Any], current_user: Any) -> dict[str, Any]:
    """주문 데이터로 도면 마법사 폼 기본값(자동 채움)을 계산한다.

    저장된 마법사 상태가 없을 때 최초 로드에서 폼 셀을 채우는 서버 계산
    SSOT다. 설계서 §4 매핑을 그대로 구현한다.

    Args:
        order: Order ORM 인스턴스(``erp_construction_date`` / ``manager_name`` 참조).
        sd: 이미 dict로 정규화된 ``structured_data``.
        current_user: 현재 사용자(User) 또는 None. ``drew`` 기본값에 사용.

    Returns:
        폼 키→값(str) dict. ``checks`` 만 ``dict[str, bool]``.
    """
    sd = sd if isinstance(sd, dict) else {}
    parties = sd.get("parties") or {}
    customer = parties.get("customer") or {}
    manager = parties.get("manager") or {}
    site = sd.get("site") or {}
    items = _extract_items(sd)
    item0 = items[0] if items else {}

    sales_manager = _as_str(manager.get("name")) or _as_str(getattr(order, "manager_name", None))
    phone_raw = customer.get("phone")

    return {
        "construction_date": _format_construction_date(order, sd),
        "customer_name": _as_str(customer.get("name")),
        "phone": _as_str(format_phone_filter(phone_raw)) if phone_raw else "",
        "address": _as_str(site.get("address_full")) or _as_str(site.get("address_main")),
        "product_name": _join_product_names(items),
        "color": _consult_strip(item0.get("color")),
        "site_spec": _site_spec(item0),
        "spec_w300": _spec_w300(items),
        "handle": _consult_strip(item0.get("handle")),
        "drawer": _consult_strip(item0.get("internal")),
        "misc": _misc(item0),
        "sales_manager": sales_manager,
        "manager_phone": _as_str(manager.get("phone")) or "-",
        "logo": _resolve_logo(sales_manager),
        "drew": _as_str(getattr(current_user, "name", None)),
        "page_no": "-",
        "checks": {key: False for key in _WIZARD_CHECK_KEYS},
    }
