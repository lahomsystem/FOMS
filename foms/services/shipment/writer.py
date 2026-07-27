"""per-order 출고 설정(non-assignment) canonical writer (SHIPMENT-WRITER-01).

``api_erp_shipment_update`` (per-order shipment settings) 의 정본 스키마/정규화 로직이다.
exact non-assignment schema ``{site_extra, construction_time, vehicle, trip}`` 만 쓰고,
``site_extra`` color 는 고정 enum 으로 제약한다. ``construction_workers``/도면·측정
담당자 등 assignment/crew 이름 배열은 이 command 소관이 **아니므로 쓰지 않는다**
(crew IDs via ``SET_INSTALLATION_CREW`` command · auth assignment via ASSIGNMENT command).
목적은 name-array/auth direct write 제거다. AS 방문/일정은 as_cycle_service 소관이라
여기서 기록하지 않는다(AS info direct write 없음).

report §2.2 UPDATE_SHIPMENT_SETTINGS 계약: ``site_extra`` 최대 20개 exact ``{text,color}``,
text 500자, color ∈ 8-enum, 나머지 string 200자. 프론트 재배선을 피하기 위해 스키마 밖
키(assignment/crew 이름·미지 키)와 enum 밖 color 는 **422 로 거부하지 않고 저장에서
배제/기본색 정규화**한다(= 임의 필드/색을 persist 하지 않는 "거부"). 엄격 422 는 DATA-01
client 정리(해당 path 전송 제거) 이후로 미룬다.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

#: site_extra color 고정 enum (report §2.2). 이 밖의 값은 저장 전 기본색으로 정규화한다.
SITE_EXTRA_COLORS: tuple[str, ...] = (
    "black", "red", "blue", "green", "orange", "purple", "brown", "navy",
)
DEFAULT_SITE_EXTRA_COLOR = "black"

SITE_EXTRA_MAX = 20
SITE_EXTRA_TEXT_MAX = 500
SETTINGS_STRING_MAX = 200

#: 이 command 가 쓰는 exact non-assignment 스키마 키.
ALLOWED_SETTINGS_KEYS: tuple[str, ...] = ("site_extra", "construction_time", "vehicle", "trip")

#: 이 command 가 쓰지 않는 assignment/crew 이름 키(name-array/auth direct write 금지 대상).
#: payload 에 있어도 저장하지 않는다(crew IDs via SET_INSTALLATION_CREW · auth via ASSIGNMENT).
NON_SETTINGS_ASSIGNMENT_KEYS: tuple[str, ...] = (
    "construction_workers", "drawing_manager", "drawing_managers",
    "measurement_manager", "measurement_managers",
)


def _normalize_color(value: Any) -> str:
    """site_extra color 를 고정 enum 으로 정규화한다(enum 밖은 기본색).

    Args:
        value: payload 의 color 값(hex·미지 문자열 포함 가능).

    Returns:
        :data:`SITE_EXTRA_COLORS` 중 하나(enum 밖이면 :data:`DEFAULT_SITE_EXTRA_COLOR`).
    """
    color = str(value or "").strip().lower()
    return color if color in SITE_EXTRA_COLORS else DEFAULT_SITE_EXTRA_COLOR


def _normalize_site_extra(raw: Any) -> List[Dict[str, str]]:
    """site_extra 를 exact ``{text,color}`` 로 정규화한다(최대 20개·color enum·text 500자).

    항목은 ``{text,color}`` dict 또는 순수 문자열을 허용한다. 빈 text 는 제거하고,
    color 는 enum 으로 강제하며, 20개를 넘으면 잘라낸다.

    Args:
        raw: payload 의 ``site_extra`` (list 가 아니면 빈 결과).

    Returns:
        정규화된 ``{text,color}`` 리스트(최대 20개).
    """
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()[:SITE_EXTRA_TEXT_MAX]
            color = _normalize_color(item.get("color"))
        else:
            text = str(item or "").strip()[:SITE_EXTRA_TEXT_MAX]
            color = DEFAULT_SITE_EXTRA_COLOR
        if text:
            out.append({"text": text, "color": color})
        if len(out) >= SITE_EXTRA_MAX:
            break
    return out


def build_shipment_settings_patch(payload: Any) -> Dict[str, Any]:
    """payload 에서 exact non-assignment 설정만 골라 정규화한 patch 를 만든다.

    ``site_extra``/``construction_time``/``vehicle``/``trip`` 중 **존재하는 키만**
    정규화해 돌려준다. assignment/crew 이름 키와 미지 키는 무시한다(name-array/auth
    direct write 제거). 존재하지 않는 키는 patch 에 없으므로 기존 서버 값이 보존된다.

    Args:
        payload: 요청 JSON. dict 가 아니면 빈 patch.

    Returns:
        ``{field: normalized_value}`` patch(존재하는 allowed 키만).
    """
    if not isinstance(payload, dict):
        return {}
    patch: Dict[str, Any] = {}
    if "site_extra" in payload:
        patch["site_extra"] = _normalize_site_extra(payload.get("site_extra"))
    for key in ("construction_time", "vehicle", "trip"):
        if key in payload:
            patch[key] = str(payload.get(key) or "").strip()[:SETTINGS_STRING_MAX]
    return patch


def apply_shipment_settings(structured_data: Any, payload: Any) -> Dict[str, Any]:
    """structured_data 의 shipment 블록에 non-assignment 설정 patch 를 적용한다.

    ``structured_data`` 를 deepcopy 하여 ``shipment`` 블록에 정규화된 설정만 병합해
    돌려준다(원본 미변경). ``construction_workers`` 등 assignment/crew projection 은
    건드리지 않는다(변경은 crew/assignment command).

    Args:
        structured_data: 대상 Order 의 ``structured_data`` (dict/None).
        payload: 요청 JSON.

    Returns:
        설정이 반영된 새 ``structured_data`` dict.
    """
    sd = copy.deepcopy(structured_data if isinstance(structured_data, dict) else {})
    shipment = sd.get("shipment")
    if not isinstance(shipment, dict):
        shipment = {}
        sd["shipment"] = shipment
    for key, value in build_shipment_settings_patch(payload).items():
        shipment[key] = value
    return sd


__all__ = [
    "SITE_EXTRA_COLORS", "DEFAULT_SITE_EXTRA_COLOR", "SITE_EXTRA_MAX",
    "SITE_EXTRA_TEXT_MAX", "SETTINGS_STRING_MAX", "ALLOWED_SETTINGS_KEYS",
    "NON_SETTINGS_ASSIGNMENT_KEYS",
    "build_shipment_settings_patch", "apply_shipment_settings",
]
