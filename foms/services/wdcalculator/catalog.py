"""계산기 설정 읽기(읽기만) — 제품 목록 · 추가 옵션 목록.

플랜 C10-6 · 설계서 17.4(원장 V10-2). 정본은 계산기 DB 설정 한 줄(``WDCalculatorProductSettings`` id 1 —
``foms/api/wdcalculator/blueprint.py`` 의 ``load_products`` 가 읽는 그 줄)이다. 줄이 없거나 칸이 비었을 때만 처음 채우기 파일
(``data/products.json`` · ``data/additional_options.json``)을 쓴다(``from_seed``).

- **확인 날은 여기서 정하지 않는다**: 설정 줄의 ``updated_at`` 은 비고 · 프리셋 저장에도 바뀌고 DB 시간대에 기대므로 쓰지
  않는다(검수 R17-5 · R17-8). 확인 날은 CS 쪽 값 지문 기록(:mod:`foms.services.cs_agent.quote_check` — 사장님 결정 D74)이다.
- **세션**: Flask 요청 밖(WORKER — 감시 루프 · 빠른 길)에서도 읽게 짧은 세션을 따로 열고 닫는다(``get_wdcalculator_db`` 는 앱
  컨텍스트 ``g`` 가 있어야 한다). 값을 쓰지 않는다.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from foms.services.wdcalculator.pricing import BRAND_LAHOM, product_brand

logger = logging.getLogger(__name__)

__all__ = ["Catalog", "read_catalog"]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SEED_PRODUCTS_PATH = os.path.join(_ROOT, "data", "products.json")
SEED_OPTIONS_PATH = os.path.join(_ROOT, "data", "additional_options.json")


@dataclass(frozen=True)
class Catalog:
    """계산기 설정 묶음(읽기 전용 사본). ``from_seed`` 면 계산기 설정 줄이 없어 처음 채우기 파일을 읽었다."""

    products: tuple[dict[str, Any], ...]
    option_categories: tuple[dict[str, Any], ...]
    from_seed: bool = False

    def products_of(self, brand: str = BRAND_LAHOM) -> tuple[dict[str, Any], ...]:
        """그 브랜드 제품(목록 순서) — 브랜드 칸, 없으면 이름으로 가른다(:func:`.pricing.product_brand`)."""
        return tuple(p for p in self.products if isinstance(p, dict) and product_brand(p) == brand)


def _seed(path: str, key: str) -> list[Any]:
    """처음 채우기 파일의 목록(못 읽으면 빈 목록)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle).get(key, [])
    except (OSError, ValueError, AttributeError):
        logger.warning("[계산기 설정] 처음 채우기 파일을 못 읽었다 path=%s", os.path.basename(path))
        return []
    return value if isinstance(value, list) else []


def _session() -> Any:
    """계산기 DB 짧은 세션(가져올 때 엔진을 묶지 않으려고 부를 때 만든다)."""
    from sqlalchemy.orm import Session

    from wdcalculator_db import wd_calculator_engine

    return Session(bind=wd_calculator_engine)


def read_catalog(session: Any = None) -> Catalog:
    """계산기 설정을 읽는다(쓰지 않는다). ``session`` 을 안 주면 짧은 세션을 열어 읽고 닫는다.

    Raises:
        SQLAlchemyError: 계산기 DB 를 못 읽음 — 부르는 쪽은 견적 계산을 넣지 않는다(예전 그대로).
    """
    from wdcalculator_models import WDCalculatorProductSettings

    own = session is None
    session = _session() if own else session
    try:
        row = session.get(WDCalculatorProductSettings, 1)
        products = copy.deepcopy(row.products) if row is not None and row.products is not None else None
        options = (copy.deepcopy(row.additional_options)
                   if row is not None and row.additional_options is not None else None)
    finally:
        if own:
            session.close()
    from_seed = products is None
    if products is None:
        products = _seed(SEED_PRODUCTS_PATH, "products")
    if options is None:
        options = _seed(SEED_OPTIONS_PATH, "categories")
    return Catalog(tuple(p for p in products if isinstance(p, dict)),
                   tuple(c for c in options if isinstance(c, dict)), from_seed)
