"""계산기 설정 읽기(읽기만) — 제품 목록 · 추가 옵션 목록 · 저장 시각(= 가격 확인 날).

플랜 C10-6 · 설계서 17.4(원장 V10-2 · R10-25). 정본은 계산기 DB 설정 한 줄(``WDCalculatorProductSettings`` id 1 —
``foms/api/wdcalculator/blueprint.py`` 의 ``load_products`` 가 읽는 그 줄)이다. 줄이 없거나 칸이 비었을 때만 처음 채우기 파일
(``data/products.json`` · ``data/additional_options.json``)을 쓰고, 그때는 확인 날이 없다(= '확인 필요').

- **확인 날**: 설정 줄의 ``updated_at``(제품 · 옵션 · 비고 · 프리셋 중 무엇을 저장해도 바뀐다 — 화면에서 저장한 날을 '확인'으로
  본다). :data:`FRESH_DAYS` 일이 지나면 :meth:`Catalog.needs_check` — 계산기 금액은 손님 글에 바로 쓰지 않는다(설계서 7.1 · 17.4).
- **세션**: Flask 요청 밖(WORKER — 감시 루프 · 빠른 길)에서도 읽게 짧은 세션을 따로 열고 닫는다(``get_wdcalculator_db`` 는 앱
  컨텍스트 ``g`` 가 있어야 한다). 값을 쓰지 않는다.
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from foms.services.wdcalculator.pricing import BRAND_LAHOM, product_brand

logger = logging.getLogger(__name__)

__all__ = ["FRESH_DAYS", "Catalog", "read_catalog"]

#: 가격 확인 날에서 이만큼(일) 지나면 '확인 필요'(설계서 7.1 의 5 — 지식 문서 가격 규칙을 계산기 쪽으로, 원장 R10-25).
FRESH_DAYS = 14
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SEED_PRODUCTS_PATH = os.path.join(_ROOT, "data", "products.json")
SEED_OPTIONS_PATH = os.path.join(_ROOT, "data", "additional_options.json")


@dataclass(frozen=True)
class Catalog:
    """계산기 설정 묶음(읽기 전용 사본). ``saved_at`` 은 UTC naive(설정 줄 저장 시각) — 처음 채우기 파일이면 ``None``."""

    products: tuple[dict[str, Any], ...]
    option_categories: tuple[dict[str, Any], ...]
    saved_at: Optional[datetime.datetime]
    from_seed: bool = False

    def products_of(self, brand: str = BRAND_LAHOM) -> tuple[dict[str, Any], ...]:
        """그 브랜드 제품(목록 순서) — 브랜드 칸, 없으면 이름으로 가른다(:func:`.pricing.product_brand`)."""
        return tuple(p for p in self.products if isinstance(p, dict) and product_brand(p) == brand)

    def age_days(self, now_utc: datetime.datetime) -> Optional[float]:
        """확인 날부터 지금까지 지난 날 수(확인 날이 없으면 ``None``)."""
        if self.saved_at is None:
            return None
        return (now_utc - self.saved_at).total_seconds() / 86400

    def needs_check(self, now_utc: datetime.datetime) -> bool:
        """'확인 필요'인가 — 확인 날이 없거나(처음 채우기 파일) :data:`FRESH_DAYS` 일을 넘김."""
        age = self.age_days(now_utc)
        return age is None or age > FRESH_DAYS


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
        saved_at = row.updated_at if row is not None else None
    finally:
        if own:
            session.close()
    from_seed = products is None
    if products is None:
        products, saved_at = _seed(SEED_PRODUCTS_PATH, "products"), None
    if options is None:
        options = _seed(SEED_OPTIONS_PATH, "categories")
    return Catalog(tuple(p for p in products if isinstance(p, dict)),
                   tuple(c for c in options if isinstance(c, dict)), saved_at, from_seed)
