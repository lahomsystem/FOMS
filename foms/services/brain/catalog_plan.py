"""견적 계산기 정본 → 제품 라인 · 옵션 자료 계획(설계서 2026-11-12 온톨로지 4절 1 · 사장님 D179 · D180).

계산기 제품마다 제품 라인, 옵션 묶음의 옵션마다 옵션 항목을 :mod:`.plan_proposals` 의 ``new_items`` 꼴로 만든다. 그 계획을
:func:`.plan_proposals.file_plan` 이 **만들기 제안**으로 넣고(반영 없음 — 사람이 제품 묶음별로 승인), 반영 뒤 다음 차례에 정본 링크
``value_from`` → ``calc:product/<id>`` · ``calc:option/<묶음 id>:<옵션 id>`` 가 들어간다.

- **금액은 싣지 않는다**(D179) — 값은 계산기 하나가 정본이고 회사 지식은 가리키기만 한다. 계획에는 id · 이름 · 값 단위 · 값 방식
  (기본 포함 / 추가)만. 그래서 이 계획은 저장소 밖에 둘 까닭이 없지만, 운영 계산기 이름이 실리므로 파일로 남기지 않고 메모리에서
  바로 넣는다(:mod:`scripts.maintenance.brain_catalog_proposals`).
- 키: 제품 라인 ``product_line/<브랜드 소문자>-<계산기 id>`` · 옵션 ``option/<묶음 id>-<옵션 id>``(옵션은 두 브랜드 공통 — 계산기
  옵션 묶음이 브랜드를 나누지 않는다). 계산기 이름이 바뀌어도 키는 그대로(이름은 대표 이름표).
- 브랜드는 계산기와 같은 판정(:func:`foms.services.wdcalculator.pricing.product_brand`).
"""

from __future__ import annotations

from typing import Any, Mapping

from foms.services.wdcalculator.pricing import product_brand

__all__ = ["PLAN_SCHEMA", "catalog_plan"]

PLAN_SCHEMA = "calc_catalog_plan/1"
#: 계산기 값 방식(``pricing_type``) → 제품 라인 값 단위(:data:`.schemas.PRICE_UNITS`).
_PRICE_UNITS = {"30cm": "30cm", "1m": "1m"}
_NAME_MAX = 60


def _name(value: Any) -> str:
    """계산기 이름 — 앞뒤 빈칸 · 탭을 걷고 안쪽 겹친 빈칸을 하나로(이름표 칸 상한까지)."""
    return " ".join(str(value or "").split())[:_NAME_MAX]


def _product(product: Mapping[str, Any]) -> dict[str, Any] | None:
    pid, name = product.get("id"), _name(product.get("name"))
    if pid is None or not name:
        return None
    brand = product_brand(product)
    props = {"price_unit": _PRICE_UNITS[product["pricing_type"]]} if product.get("pricing_type") in _PRICE_UNITS else {}
    return {"type": "product_line", "key": f"product_line/{brand.lower()}-{pid}", "brand": brand, "pref_label": name,
            "text": f"{name} — 견적 계산기 제품(값은 계산기가 정본)", "props": props,
            "value_from_hint": [f"calc:product/{pid}"], "why": "견적 계산기 제품에서 만든 제품 라인 D179"}


def _option(category: Mapping[str, Any], option: Mapping[str, Any]) -> dict[str, Any] | None:
    cid, oid = category.get("id"), option.get("id")
    cat, name = _name(category.get("name")), _name(option.get("name"))
    if cid is None or oid is None or not name:
        return None
    price = option.get("price")
    kind = "included" if isinstance(price, (int, float)) and not isinstance(price, bool) and price == 0 else "extra"
    label = f"{cat} {name}".strip()[:_NAME_MAX] if cat and cat not in name else name
    return {"type": "option", "key": f"option/{cid}-{oid}", "pref_label": label,
            "text": f"{cat} > {name} — 견적 계산기 옵션(값은 계산기가 정본)" if cat else
                    f"{name} — 견적 계산기 옵션(값은 계산기가 정본)",
            "props": {"category": cat, "price_kind": kind, "option_kind": "part"},
            "value_from_hint": [f"calc:option/{cid}:{oid}"], "why": "견적 계산기 옵션에서 만든 옵션 D179"}


def catalog_plan(catalog: Any) -> dict[str, Any]:
    """계산기 정본(:class:`foms.services.wdcalculator.catalog.Catalog`) → 자료 계획(``new_items`` 만). 금액 칸 없음."""
    rows: list[dict[str, Any]] = []
    for product in catalog.products or ():
        if isinstance(product, Mapping) and (made := _product(product)) is not None:
            rows.append(made)
    for category in catalog.option_categories or ():
        if not isinstance(category, Mapping):
            continue
        for option in category.get("options") or ():
            if isinstance(option, Mapping) and (made := _option(category, option)) is not None:
                rows.append(made)
    return {"schema": PLAN_SCHEMA, "items": [], "conflicts": [], "new_items": rows}
