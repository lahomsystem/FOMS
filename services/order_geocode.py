"""
주소 변경 시 지오코딩 초기화·ERP Beta structured_data.site 정합 (2026-03-15 이후).
commit/queue는 caller가 성공 경계에서 처리.
"""
from __future__ import annotations

import copy
from typing import Any, MutableMapping

from sqlalchemy.orm.attributes import flag_modified


def apply_erp_beta_site_address_to_sd(sd: MutableMapping[str, Any], flat_address: str) -> bool:
    """
    클래식 주소 한 필드(order.address)를 ERP Beta 표시 단일 소스(structured_data.site)에 반영.

    apply_erp_display_fields 등이 site.address_full / address_main을 우선하므로,
    컬럼만 갱신되고 JSONB가 남으면 대시보드에 구주소가 보인다. 상세(detail)는 과거 잔여로
    main+detail 조합 오염을 막기 위해 비운다.

    Args:
        sd: structured_data 루트 dict (in-place 수정).
        flat_address: Order.address 컬럼과 동일하게 쓸 문자열.

    Returns:
        site 관련 필드가 실제로 바뀌었으면 True.
    """
    addr = (flat_address or "").strip()
    raw_site = sd.get("site")
    if isinstance(raw_site, MutableMapping):
        site = raw_site
    else:
        site = {}
        sd["site"] = site

    old_full = str(site.get("address_full") or "").strip()
    old_main = str(site.get("address_main") or "").strip()
    old_detail = str(site.get("address_detail") or "").strip()

    if addr:
        if old_full == addr and old_main == addr and not old_detail:
            return False
        site["address_full"] = addr
        site["address_main"] = addr
        site["address_detail"] = ""
    else:
        if not old_full and not old_main and not old_detail:
            return False
        site["address_full"] = ""
        site["address_main"] = ""
        site["address_detail"] = ""

    return True


def reset_order_geocode_on_address_change(order, new_address: str) -> str:
    """
    주소 수정 시 lat/lng 초기화 및 geocode_status=pending 설정.
    빈 문자열(공백만 포함)도 유효한 변경으로 반영한다.
    db.commit(), enqueue_geocode_order_address()는 호출하지 않음.

    Args:
        order: Order 모델 인스턴스
        new_address: 새 주소 문자열

    Returns:
        정규화된 주소 문자열 (저장된 값, 빈 문자열 가능)
    """
    addr = (new_address or "").strip()

    if order.is_erp_beta and order.structured_data is not None:
        sd = copy.deepcopy(order.structured_data or {})
        if isinstance(sd, dict):
            apply_erp_beta_site_address_to_sd(sd, addr)
            order.structured_data = sd
            flag_modified(order, "structured_data")

    order.address = addr  # ERP Beta / 비 Beta 공통으로 DB 컬럼 동기화

    order.lat = None
    order.lng = None
    order.geocode_status = "pending"

    return addr


def clear_order_geocode_coords(order) -> None:
    """지오코딩 재실행이 필요할 때 좌표·상태만 초기화 (JSONB는 건드리지 않음)."""
    order.lat = None
    order.lng = None
    order.geocode_status = "pending"
