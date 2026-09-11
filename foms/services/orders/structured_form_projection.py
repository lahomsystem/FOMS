"""ERP 주문 structured_data 폼 저장 정본 projection (DATA-01).

structured PUT 이 클라이언트 폼 payload 를 그대로 신뢰해 JSONB 를 통째로 교체하던 것을,
서버 권위(server-authoritative) projection 으로 대체한다. 세 가지 불변식을 강제한다.

1. **partial allowlist**: 폼이 **새로 도입**할 수 있는 최상위 키만 클라이언트가 만들 수 있다
   (:data:`FORM_INTRODUCED_KEYS`). 그 외 임의 키는, old_sd 에 이미 존재하지 않는 한
   무시(strip)한다 — 클라이언트가 미지의 top-level 키를 JSONB 에 주입하지 못한다.
2. **provenance 보존(client overwrite 금지)**: 파서가 심은 provenance(raw/schema/
   confidence 계열, :data:`PROVENANCE_KEYS`)는 서버 소유다. old_sd 에 이미 있으면
   클라이언트 값으로 덮어쓰지 않는다(old-wins). 없을 때만 bootstrap 으로 수용한다.
3. **server pricing/totals**: 금액/합계(``totals``)는 클라이언트 제공 값을 무시하고
   items[].price·payment(자유입력/할인/예약금) authoritative source 로 재계산한다.
   출고가(shipping_price) = max(0, 품목합 + 배송 - 할인). 저장 ``totals.items_total`` 은
   품목 price 합만(재정의 금지) — [[project_shipping_price_grand_total]].

이 모듈은 순수 함수만 담는다(DB/세션 없음). 저장 route(:mod:`foms.api.erp_orders_structured`)
가 old_sd 운영상태 병합·요청 검증 뒤 이 projection 을 적용하고, REV-00
``execute_order_mutation`` 으로 If-Match·version·PG race 를 한 tx 에 원자화한다.
"""
from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 파서·서버가 심는 provenance 최상위 키. 클라이언트 폼은 이 값을 덮어쓸 수 없다(old-wins).
#: ``order_text_parser.parse_order_text`` 출력의 최상위 provenance 와 동일 집합이다.
PROVENANCE_KEYS = frozenset({
    "entity_type",
    "schema_version",
    "parsed_at",
    "confidence",
    "raw",
    "header_raw",
})

#: 폼이 **새로 도입**할 수 있는 최상위 키(partial allowlist). old_sd 에 이미 존재하는 키는
#: (운영 상태·레거시 포함) 호출자가 별도 보존하므로 이 집합에 없어도 유지된다 — 이 집합은
#: "클라이언트가 처음 만들 수 있는 키"의 상한이다. 이 집합·old_sd 어디에도 없는 임의 키는
#: strip 된다.
FORM_INTRODUCED_KEYS = frozenset(PROVENANCE_KEYS | {
    "totals",
    "parties",
    "site",
    "schedule",
    "notes",
    "workflow",
    "flags",
    "payment",
    "payments",
    "items",
    "shipment",
    "meta",
})

#: 폼 저장 경로가 **의도적으로** 제거하는 유일한 최상위 키. 정본은
#: ``foms.api.erp_orders_structured._force_preserve_as_lifecycle`` 의
#: ``structured_data.pop("as_lifecycle", None)``(erp_orders_structured.py:519) 이며,
#: 서버값이 dict 가 아닐 때 폼이 보낸 stale 스냅샷을 떨어뜨린다. 아래
#: :func:`preserve_non_form_keys` 의 "빠진 옛 키 복원" 규칙이 이 키를 되살리면 그 pop 이
#: 무효가 되므로 예외로 둔다. 2026-09-11 실측: 폼 저장 경로의 최상위 키 제거는 이 한 곳뿐이다
#: (``grep -n "structured_data.pop\|del structured_data" foms/api/erp_orders_structured.py``).
SERVER_OWNED_REMOVABLE_KEYS = frozenset({"as_lifecycle"})


def preserve_non_form_keys(old_sd: dict, structured_data: dict) -> list[str]:
    """폼이 안 보낸 서버 소유 최상위 키를 old_sd 에서 되살린다(in-place). 복원 키를 반환한다.

    :func:`enforce_form_allowlist` 의 **대칭짝**이다 — 저쪽은 "클라이언트가 새 키를 못 만들게"
    하고, 이쪽은 "클라이언트가 남의 키를 못 지우게" 한다. allowlist 는 들어온 dict 에서 낯선
    키를 걷어낼 뿐 **빠진 옛 키를 되살리지 않으므로**, 폼이 렌더하지도 보내지도 않는 서버 소유
    키는 지금까지 "보존 목록에 이름을 적어야만" 살아남았다.

    2026-09-10 주문 5177: 영업 담당자의 전체 폼 저장 1회가
    ``structured_data['drawing_wizard']`` 를 통째로 지웠다(도면 시트 2장의 ``objects`` 와
    ``pending``·``versions``). 그 키만 ``_OPERATIONAL_TOP_LEVEL_KEYS`` 에 빠져 있었고, 폼이
    애초에 보내지 않는 키라 strip 목록에도 안 남아 **경고 로그조차 없었다**. 감사 원장에는
    ``change_count 0`` 으로 기록됐다. 같은 계열 사고는 ``source``·``naver``·``pricing``·
    ``alimtalk_measurement``·``schedule.as_visit`` 에 이어 여섯 번째였다. 그래서 목록 등재가
    아니라 **기본값 자체를 "비-폼 키는 보존"으로 뒤집는다**.

    복원 대상: old_sd 의 최상위 키 중 :data:`FORM_INTRODUCED_KEYS` 에도
    :data:`SERVER_OWNED_REMOVABLE_KEYS` 에도 없고, ``structured_data`` 에 없는 키.
    폼이 값을 보낸 키는 건드리지 않으므로 정상 편집(값 비우기 포함)을 막지 않는다.

    Args:
        old_sd: 저장 전 서버 structured_data(복원 원본).
        structured_data: in-place 로 복원될 projection 대상 dict.

    Returns:
        복원된 최상위 키 이름 목록(빈 목록이면 잃을 뻔한 키 없음).
    """
    if not isinstance(structured_data, dict) or not isinstance(old_sd, dict):
        return []
    restored = [
        key
        for key in list(old_sd.keys())
        if key not in FORM_INTRODUCED_KEYS
        and key not in SERVER_OWNED_REMOVABLE_KEYS
        and key not in structured_data
    ]
    for key in restored:
        structured_data[key] = copy.deepcopy(old_sd[key])
    if restored:
        logger.warning(
            "[DATA-01] restored server-owned structured keys dropped by form payload: %s",
            restored,
        )
    return restored


def enforce_form_allowlist(structured_data: dict, old_sd: dict) -> list[str]:
    """임의 최상위 키를 strip 한다(partial allowlist). strip 된 키 목록을 반환한다.

    허용 규칙: 키가 :data:`FORM_INTRODUCED_KEYS` 에 있거나 old_sd 에 이미 존재하면 유지한다.
    그 외(클라이언트가 처음 도입한 미지의 키)는 제거한다. old_sd 의 레거시 키는 이미 존재하므로
    보존된다.

    Args:
        structured_data: in-place 로 strip 될 projection 대상 dict.
        old_sd: 저장 전 서버 structured_data(레거시 키 보존 판정용).

    Returns:
        strip 된 최상위 키 이름 목록(빈 목록이면 임의 키 없음).
    """
    if not isinstance(structured_data, dict):
        return []
    existing = old_sd if isinstance(old_sd, dict) else {}
    stripped = [
        key
        for key in list(structured_data.keys())
        if key not in FORM_INTRODUCED_KEYS and key not in existing
    ]
    for key in stripped:
        del structured_data[key]
    if stripped:
        logger.warning("[DATA-01] stripped non-allowlisted structured keys: %s", stripped)
    return stripped


def lock_provenance(old_sd: dict, structured_data: dict) -> None:
    """provenance 최상위 키를 서버 소유로 고정한다(client overwrite 금지, in-place).

    old_sd 에 provenance 키가 존재하면 그 값을 복원한다(클라이언트가 보낸 값 무시). old_sd 에
    없으면 클라이언트 값을 그대로 둔다(신규 주문 bootstrap — 기존 동작 회귀 방지).

    Args:
        old_sd: 저장 전 서버 structured_data(provenance 원본).
        structured_data: in-place 로 provenance 가 잠길 projection 대상 dict.
    """
    if not isinstance(structured_data, dict):
        return
    existing = old_sd if isinstance(old_sd, dict) else {}
    for key in PROVENANCE_KEYS:
        if key in existing:
            structured_data[key] = copy.deepcopy(existing[key])


def _coerce_item_price(item: Any) -> int:
    """items[].price 를 원화 정수로 정규화(erp_display 와 동일 규칙)."""
    from foms.services.erp_display import _erp_coerce_item_price_krw

    return _erp_coerce_item_price_krw(item)


def recompute_totals(structured_data: dict) -> dict:
    """금액/합계를 서버 authoritative source 로 재계산한다(클라이언트 totals 무시, in-place).

    입력 소스: ``items[].price``(품목합), ``payment.free_input``(배송/자유입력),
    ``payment.discount``(할인), ``payment.deposit``(예약금). 클라이언트가 보낸 ``totals`` 는
    폐기하고 재계산한다. 출고가(shipping_price) = ``max(0, 품목합 + 배송 - 할인)``. 저장
    ``totals.items_total`` 은 품목 price 합만 담는다(재정의 금지) —
    [[project_shipping_price_grand_total]].

    Args:
        structured_data: in-place 로 ``totals`` 가 재계산될 dict.

    Returns:
        재계산된 ``totals`` dict(호출자 편의).
    """
    if not isinstance(structured_data, dict):
        return {}
    # 클라이언트 totals 폐기 후 authoritative source(payment/items)만 읽게 한다.
    structured_data.pop("totals", None)

    # 순환 import 방지 위해 함수 지역 import(erp_display 헬퍼도 estimate_service 를 지역 import).
    from foms.services.erp_display import erp_deposit_amount_from_structured
    from foms.services.estimate_service import (
        _extract_discount_amount,
        _extract_free_input_amount,
    )

    items = structured_data.get("items")
    items_total = 0
    if isinstance(items, list):
        items_total = sum(
            _coerce_item_price(it) for it in items if isinstance(it, dict)
        )
    free_input = int(_extract_free_input_amount(structured_data) or 0)
    discount = int(_extract_discount_amount(structured_data) or 0)
    deposit = int(erp_deposit_amount_from_structured(structured_data) or 0)
    contract_total = int(items_total) + free_input
    balance = max(0, contract_total - deposit - discount)
    totals = {
        "items_total": int(items_total),
        "free_input_amount": free_input,
        "contract_total": contract_total,
        "deposit_amount": deposit,
        "discount_amount": discount,
        "balance_amount": balance,
        "final_amount": balance,
        "shipping_price": max(0, contract_total - discount),
    }
    structured_data["totals"] = totals
    return totals


def project_structured_form(old_sd: dict, structured_data: dict) -> list[str]:
    """폼 payload 를 정본 structured_data 로 projection 한다(in-place). strip 키를 반환한다.

    호출 전제: 호출자가 이미 old_sd 운영상태 병합
    (``_preserve_operational_structured_state``)을 끝낸 ``structured_data`` 를 넘긴다. 이
    함수는 그 위에 (0) 비-폼 키 복원 → (1) allowlist strip → (2) provenance lock →
    (3) server pricing 을 순서대로 적용한다.

    (0)은 :func:`preserve_non_form_keys` 다 — 폼이 보내지 않은 서버 소유 최상위 키를 old_sd
    에서 되살린다. allowlist 앞에 둬야 복원된 키가 "old_sd 에 이미 있는 키"로 판정돼 그대로
    통과한다. 반환 시그니처는 바꾸지 않는다(호출자·기존 테스트가 strip 목록에 기댄다).

    Args:
        old_sd: 저장 전 서버 structured_data.
        structured_data: in-place 로 projection 될 dict.

    Returns:
        allowlist 로 strip 된 최상위 키 목록.
    """
    preserve_non_form_keys(old_sd, structured_data)
    stripped = enforce_form_allowlist(structured_data, old_sd)
    lock_provenance(old_sd, structured_data)
    recompute_totals(structured_data)
    return stripped


__all__ = [
    "PROVENANCE_KEYS",
    "FORM_INTRODUCED_KEYS",
    "SERVER_OWNED_REMOVABLE_KEYS",
    "preserve_non_form_keys",
    "enforce_form_allowlist",
    "lock_provenance",
    "recompute_totals",
    "project_structured_form",
]
