"""바깥 정본 가리킴(``calc:`` · ``setting:``) — **실재 확인**과 카드의 **지금 값**(설계서 7.7 · 사장님 D105).

brain 은 값을 베끼지 않고 정본 자리를 가리키기만 한다(3.1 규칙 — ``value_from`` 의 끝). 그 자리가 정말 있는지는
제안 때(:func:`foms.services.brain.proposals.propose_link`)와 반영 때(:func:`foms.services.brain.apply.apply_change`) 두 번
본다 — 없는 키를 가리키는 링크는 넣지 않는다(:class:`BrainExternalRefError`). 빼기(링크 끊기)는 보지 않는다(사라진 자리를
가리키는 링크를 끊을 수 있어야 한다).

키 꼴(정본 읽는 길은 이미 있는 것만 쓴다):

- ``calc:product/<제품 id>`` — 견적 계산기 제품(:func:`foms.services.wdcalculator.catalog.read_catalog` · 같은 id 견주기
  :func:`foms.services.wdcalculator.pricing.find_product`).
- ``calc:option/<카테고리 id>:<옵션 id>`` — 계산기 추가 옵션(:func:`foms.services.wdcalculator.pricing.option_rows` 와 같은 id 꼴).
- ``setting:<키>`` — 시스템 설정 한 줄(``system_settings.setting_key``). ``setting:<키>#<칸>`` 은 **칸까지** 본다(값이 JSON
  객체이고 그 칸이 있어야 — 7.8 다음 4). 코드가 처음 값을 둔 규칙 설정(:data:`foms.services.cs_agent.rule_settings.KNOWN_FIELDS`
  — 견적 최소 길이 · 그림 읽기 벽 쪽 값)은 줄이 없어도 처음 값으로 있다.
- ``erp:stage/<값>`` — ERP 주문 단계 정본(:data:`foms.services.orders.erp_policy_constants.STAGE_LABELS` — 키는 소문자,
  대문자로 바꿔 견준다 · 7.8 다음 3).
- 사본 자리(``macro:`` · ``store:`` · ``screen:`` · ``form:`` — ``copy_in`` 의 끝, 7.8 다음 6)는 있음을 확인할 길이 없어 키 꼴만
  본다(:data:`.constants.EXTERNAL_KEY_PATTERNS`). 카드에는 '바깥 사본'과 링크의 마지막 확인 날만.

**카드의 지금 값은 볼 수 있는 사람에게만**(4절 보기 범위): 계산기 값(가격)은 가격 재량 범위(``price`` — 사장님 · ADMIN)를 볼
수 있는 사람만, 설정 값 요약은 관리 범위(``admin``)를 볼 수 있는 사람 **과 그 항목 층의 승인자 팀 MANAGER**(사장님 D109 · D101 —
도면 층의 자재표 설정은 도면팀 팀장)만 본다. 그 밖의 사람에게는 이름 · 있음 여부만 가고 값 칸 자체를 싣지 않는다
(``value_hidden``). 설정 값은 통째가 아니라 짧은 요약(글 앞부분 · 목록 개수 · 칸 이름 몇 개)만 보인다.

계산기 정본은 따로 DB 라 읽는 함수를 바꿔 끼울 수 있다(:func:`catalog_source` — 시험 · 도구). 못 읽으면 제안 · 반영은 막고
(실재를 확인할 수 없으면 넣지 않는다), 카드는 '확인 못 함'으로 보인다.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Callable, Iterable, Iterator, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from foms.services.brain.constants import (
    COPY_EXTERNAL_TYPES, LAYER_APPROVER_TEAMS, SCOPE_ADMIN, SCOPE_PRICE, external_type,
)
from foms.services.brain.errors import BrainExternalRefError
from foms.services.brain.scope import ROLE_MANAGER, Viewer, can_see
from foms.services.cs_agent.rule_settings import KNOWN_FIELDS
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.wdcalculator.catalog import Catalog, read_catalog
from foms.services.wdcalculator.pricing import find_product
from models import SystemSetting

logger = logging.getLogger(__name__)

CALC, SETTING, ERP_STAGE = "calc:", "setting:", "erp:stage/"
FIELD_MARK = "#"
PRODUCT, OPTION = "product/", "option/"
SUMMARY_CHARS, SUMMARY_KEYS = 60, 4
_READERS: list[Callable[[], Catalog]] = [read_catalog]


@contextlib.contextmanager
def catalog_source(reader: Callable[[], Catalog]) -> Iterator[None]:
    """계산기 정본 읽는 함수를 잠시 바꾼다(시험 · 도구 — 운영 길은 :func:`read_catalog`)."""
    _READERS.append(reader)
    try:
        yield
    finally:
        _READERS.remove(reader)


def _catalog() -> Optional[Catalog]:
    """계산기 정본(못 읽으면 ``None`` — 부르는 쪽이 '확인 못 함'으로 다룬다)."""
    try:
        return _READERS[-1]()
    except (SQLAlchemyError, OSError, ValueError):
        logger.warning("[brain 바깥 정본] 계산기 정본을 읽지 못했다")
        return None


def current_catalog() -> Optional[Catalog]:
    """지금 끼운 읽는 함수로 읽은 계산기 정본(못 읽으면 ``None``) — 이름으로 옵션 id 를 찾는 도구(자료 계획 제안)가 쓴다."""
    return _catalog()


def _option(catalog: Catalog, path: str) -> Optional[dict[str, Any]]:
    """``<카테고리 id>:<옵션 id>`` → {"name", "price"}(없으면 ``None``)."""
    category_id, _, option_id = path.partition(":")
    for category in catalog.option_categories:
        if str(category.get("id")) != category_id:
            continue
        for option in category.get("options") or ():
            if isinstance(option, dict) and str(option.get("id")) == option_id:
                return {"name": f"{category.get('name')} > {option.get('name')}", "price": option.get("price")}
    return None


def _calc_entry(catalog: Catalog, ref: str) -> Optional[dict[str, Any]]:
    """``calc:`` 키 → {"name", "values"}(없으면 ``None``). ``values`` 는 가격 칸(보기 범위 안에서만 내보낸다)."""
    path = ref[len(CALC):]
    if path.startswith(PRODUCT) and path[len(PRODUCT):]:
        product = find_product(catalog.products, path[len(PRODUCT):])
        if product is None:
            return None
        values = {k: product.get(k) for k in ("pricing_type", "price_30cm", "price_1cm", "price_1m")
                  if product.get(k) is not None}
        return {"name": str(product.get("name") or ""), "values": values}
    if path.startswith(OPTION) and ":" in path:
        option = _option(catalog, path[len(OPTION):])
        return None if option is None else {"name": option["name"], "values": {"price": option["price"]}}
    return None


def setting_parts(ref: str) -> tuple[str, Optional[str]]:
    """``setting:<키>[#<칸>]`` → (키, 칸 또는 ``None``)."""
    key, mark, field = ref[len(SETTING):].partition(FIELD_MARK)
    return key, (field if mark else None)


def _setting_rows(session: Any, refs: list[str], *, values: bool = False) -> dict[str, Any]:
    """있는 설정 키 → 값(``values`` 가 아니면 칸 이름 목록만 — 값은 내보내지 않는다)."""
    keys = sorted({setting_parts(r)[0] for r in refs})
    if not keys:
        return {}
    rows = session.execute(select(SystemSetting.setting_key, SystemSetting.setting_value)
                           .where(SystemSetting.setting_key.in_(keys))).all()
    return {key: (value if values else sorted(value) if isinstance(value, dict) else []) for key, value in rows}


def _setting_present(ref: str, rows: dict[str, Any]) -> bool:
    """설정 가리킴이 실재하나 — 줄(칸이면 그 칸까지) 또는 코드가 처음 값을 둔 규칙 설정 칸."""
    key, field = setting_parts(ref)
    known = KNOWN_FIELDS.get(key)
    if field is None:
        return key in rows or known is not None
    return field in (rows.get(key) or ()) or (known is not None and field in known)


def stage_code(ref: str) -> Optional[str]:
    """``erp:stage/<값>`` → ERP 단계 정본 코드(없는 값이면 ``None``)."""
    code = ref[len(ERP_STAGE):].upper()
    return code if ref[len(ERP_STAGE):].islower() and code in STAGE_LABELS else None


def missing_refs(session: Any, refs: Iterable[str]) -> tuple[list[str], bool]:
    """없는 바깥 정본 키와 '확인 못 함'(계산기 정본을 못 읽음) — brain 키 · 모르는 머리 · 사본 자리는 견주지 않는다."""
    wanted = [r for r in dict.fromkeys(refs) if external_type(r) is not None]
    settings = [r for r in wanted if r.startswith(SETTING)]
    calcs = [r for r in wanted if r.startswith(CALC)]
    rows = _setting_rows(session, settings)
    missing = [r for r in settings if not _setting_present(r, rows)]
    missing += [r for r in wanted if r.startswith(ERP_STAGE) and stage_code(r) is None]
    if calcs:
        catalog = _catalog()
        if catalog is None:
            return missing + calcs, True
        missing += [r for r in calcs if _calc_entry(catalog, r) is None]
    return missing, False


def require_refs(session: Any, refs: Iterable[str]) -> None:
    """가리킨 바깥 정본 키가 모두 있어야 한다(제안 · 반영 — 링크 더하기).

    Raises:
        BrainExternalRefError: 없는 키가 있거나 계산기 정본을 읽지 못했다.
    """
    missing, unavailable = missing_refs(session, refs)
    if missing:
        raise BrainExternalRefError(missing, unavailable=unavailable)


def _summary(value: Any) -> str:
    """설정 값 짧은 요약(글 앞부분 · 목록 개수 · 칸 이름 몇 개 — 통째로 보이지 않는다)."""
    if isinstance(value, dict):
        names = sorted(str(k)[:20] for k in value)
        more = f" 외 {len(names) - SUMMARY_KEYS}" if len(names) > SUMMARY_KEYS else ""
        return f"칸 {len(names)}개 — {', '.join(names[:SUMMARY_KEYS])}{more}" if names else "빈 칸"
    if isinstance(value, list):
        return f"목록 {len(value)}개"
    text = "" if value is None else str(value)
    return text[:SUMMARY_CHARS] + ("…" if len(text) > SUMMARY_CHARS else "")


_PRICE_LABELS = {"price_30cm": "30cm 값", "price_1cm": "1cm 값", "price_1m": "1m 값", "price": "값"}


def _won(value: Any) -> str:
    """수 → '12,000원'(수가 아니면 글 그대로)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,.0f}원"
    return str(value)


def _calc_value(values: dict[str, Any]) -> str:
    """계산기 가격 칸 → 짧은 글('30cm 단위 · 30cm 값 12,000원 · 1cm 값 400원')."""
    head = [f"{values['pricing_type']} 단위"] if values.get("pricing_type") else []
    return " · ".join(head + [f"{_PRICE_LABELS.get(k, k)} {_won(v)}" for k, v in values.items() if k != "pricing_type"])


def _setting_value(values: dict[str, Any], key: str, field: Optional[str]) -> str:
    """설정 값 요약 — 칸이면 그 칸 값(줄이 없거나 칸이 없으면 코드 처음 값 + '처음 값')."""
    if field is None:
        return _summary(values.get(key))
    stored = values.get(key)
    if isinstance(stored, dict) and field in stored:
        return _summary(stored[field])
    default = KNOWN_FIELDS.get(key, {}).get(field)
    return f"{_summary(default)}(처음 값)" if default is not None else ""


def sees_setting_values(viewer: Viewer, layer: Optional[str]) -> bool:
    """설정 값 요약을 볼 수 있나 — 관리 범위(ADMIN) 또는 그 층 승인자 팀의 켜진 MANAGER(D109 · D101)."""
    if can_see(viewer, SCOPE_ADMIN):
        return True
    team = LAYER_APPROVER_TEAMS.get(layer or "")
    return bool(viewer.internal and viewer.role == ROLE_MANAGER and team is not None and viewer.team == team)


def ref_cards(session: Any, viewer: Viewer, chips: list[dict[str, Any]], *,
              layer: Optional[str] = None) -> list[dict[str, Any]]:
    """카드 바깥 정본 칩에 있음 · 이름 · 지금 값(볼 수 있는 사람만)을 붙인다.

    Args:
        chips: :func:`foms.services.brain.card.external_chips` 결과(``ref`` · ``kind`` · ``ext_type``).
        layer: 그 항목의 층 — 설정 값 요약을 그 층 승인자 팀 MANAGER 에게도 보인다(D109). 계산기 값은 층과 상관없다.

    Returns:
        칩마다 ``exists``(``True`` · ``False`` · 확인 못 하면 ``None``) · ``label`` · ``value`` · ``value_hidden`` ·
        ``copy_ref``(사본 자리 — 있음을 확인하지 않는다).
    """
    refs = [c["ref"] for c in chips]
    calcs = [r for r in refs if r.startswith(CALC)]
    catalog = _catalog() if calcs else None
    settings = [r for r in refs if r.startswith(SETTING)]
    rows = _setting_rows(session, settings)
    see_price, see_admin = can_see(viewer, SCOPE_PRICE), sees_setting_values(viewer, layer)
    values = _setting_rows(session, settings, values=True) if see_admin and rows else {}
    out = []
    for chip in chips:
        ref = chip["ref"]
        card = {**chip, "exists": None, "label": None, "value": None, "value_hidden": False,
                "copy_ref": chip.get("ext_type") in COPY_EXTERNAL_TYPES}
        if ref.startswith(SETTING):
            key, field = setting_parts(ref)
            present = _setting_present(ref, rows)
            card.update(exists=present, label=key if field is None else f"{key} · {field}")
            if present:
                card.update(value=_setting_value(values, key, field) if see_admin else None, value_hidden=not see_admin)
        elif ref.startswith(ERP_STAGE):
            code = stage_code(ref)
            card.update(exists=code is not None, label=STAGE_LABELS.get(code or ""))
        elif ref.startswith(CALC) and catalog is not None:
            entry = _calc_entry(catalog, ref)
            card["exists"] = entry is not None
            if entry is not None:
                card.update(label=entry["name"], value=_calc_value(entry["values"]) if see_price else None,
                            value_hidden=not see_price)
        out.append(card)
    return out
