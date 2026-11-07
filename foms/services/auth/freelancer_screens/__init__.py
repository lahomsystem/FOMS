"""프리랜서에게 여는 화면 묶음(판 화면 · 그 화면이 부르는 조각 · API) — 묶음마다 이 폴더에 파일 하나.

사용자 결정(2026-11-07): 프리랜서도 회사 소속 때와 같은 화면을 쓰되 **주문은 자기 것만** 보인다. 판 화면은 하나씩
"자기 주문만" 거르기를 넣고 시험으로 확인한 뒤 여기 파일로 연다 — 문지기(:mod:`foms.services.auth.freelancer_scope`)
가 이 폴더의 모든 파일을 모아 허용 목록 · 방법 제한 · 주문 번호 표에 더한다(파일끼리 서로 건드리지 않는다).

파일마다 둘 수 있는 이름(없으면 빈 값):

* ``ALLOWED_ENDPOINTS``: frozenset[str] — 여는 endpoint.
* ``METHOD_LIMITS``: dict[str, frozenset[str]] — 일부 방법만 여는 endpoint.
* ``ORDER_VIEW_ARGS``: dict[str, tuple[str, ...]] — URL 인자 중 주문 번호(남의 주문이면 404).
* ``ORDER_QUERY_ARGS``: dict[str, tuple[str, ...]] — query string 중 주문 번호.

파일은 데이터만 둔다 — :mod:`foms.services.auth.freelancer_scope` 를 import 하지 않는다(순환).
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any

ALLOWED_ENDPOINTS: frozenset[str] = frozenset()
METHOD_LIMITS: dict[str, frozenset[str]] = {}
ORDER_VIEW_ARGS: dict[str, tuple[str, ...]] = {}
ORDER_QUERY_ARGS: dict[str, tuple[str, ...]] = {}
#: 모은 파일 이름(시험 · 진단용).
MODULES: tuple[str, ...] = ()


def _merge(module: Any) -> None:
    global ALLOWED_ENDPOINTS, METHOD_LIMITS, ORDER_VIEW_ARGS, ORDER_QUERY_ARGS
    ALLOWED_ENDPOINTS = ALLOWED_ENDPOINTS | frozenset(getattr(module, "ALLOWED_ENDPOINTS", frozenset()))
    METHOD_LIMITS = {**METHOD_LIMITS, **dict(getattr(module, "METHOD_LIMITS", {}))}
    ORDER_VIEW_ARGS = {**ORDER_VIEW_ARGS, **dict(getattr(module, "ORDER_VIEW_ARGS", {}))}
    ORDER_QUERY_ARGS = {**ORDER_QUERY_ARGS, **dict(getattr(module, "ORDER_QUERY_ARGS", {}))}


for _info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
    if _info.name.startswith("_"):
        continue
    _merge(importlib.import_module(f"{__name__}.{_info.name}"))
    MODULES = MODULES + (_info.name,)
