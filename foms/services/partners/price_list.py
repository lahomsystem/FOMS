"""협력사 단가표 판 — 불러오기 · 검사 · 판 저장(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.1 · §5.1).

단가표(``sheet``)는 사용자가 쓰던 "통합 단가표" HTML 모양을 그대로 받는다: 카테고리마다 왼쪽/오른쪽 · 제목 ·
열 제목 · 칸 종류(text · price) · 줄(칸 목록). 한 줄에 품목이 하나(이름 · 금액) 또는 둘(이름 · 금액 · 이름 · 금액)
있고, 품목마다 계산 정보를 붙인다::

    {"key": "r12", "name_col": 0, "price_col": 1, "role": "product" | "option",
     "unit": "자", "kind": "ja", "cond": {...}, "partner_label": "", "pick_names": [...],
     "for_products": [...], "pickable": true}

- ``key`` 는 판이 바뀌어도 이어지는 줄 열쇠다. 새 판은 옛 판 열쇠를 그대로 쓰고, 지운 줄은 ``retired`` 에 남긴다
  (옛 선택 · 옛 명세서가 끊기지 않게 — 설계서 §10).
- 이름 · 금액은 칸(``cells``)에만 있다. 금액이 빈칸 · 0 이면 기본 포함(명세서 줄 없이 비고에만 — 설계서 §4).
- 불러오기는 화면에 띄우기만 한다. "저장"해야 새 판(ACTIVE)이 되고 옛 판은 RETIRED 가 된다.

금액 계산은 :mod:`foms.services.partners.statement_calc` 한 곳이다. 단가 숫자는 DB 에만 둔다(저장소 공개).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Optional

from sqlalchemy import func

from models import PartnerOrg, PartnerPriceList

#: 계산 방법(설계서 §3.1). 기본 포함은 값(빈칸 · 0)으로만 판정하므로 따로 두지 않는다.
KINDS = ("ja", "meter", "band", "over", "count", "fixed")
UNITS = ("자", "m", "개", "짝", "통", "단", "식")
ROLES = ("product", "option")
DIMS = ("width", "depth")

DEFAULT_RULES = {"ja_decimals": 1, "meter_decimals": 1}

MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_ITEMS = 600
MAX_TEXT = 200
MAX_NAMES = 30

_DATA_RE = re.compile(r'<script[^>]*\bid=["\']data["\'][^>]*>(.*?)</script>', re.S | re.I)
_KEY_RE = re.compile(r"^r(\d+)$")


class PriceListError(ValueError):
    """사용자에게 그대로 보일 단가표 오류(글 목록)."""

    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


class PriceListConflict(PriceListError):
    """다른 사람이 먼저 새 판을 저장했다(열어 둔 판이 지금 판이 아니다)."""


# --------------------------------------------------------------------------
# 칸 · 이름 정리
# --------------------------------------------------------------------------
def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()[:limit]


def _price(value: Any) -> Optional[int]:
    """금액 칸 → 원(정수). 빈칸은 None. 쉼표 · 원 글자는 뗀다. 음수 · 소수 · 글자는 오류."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PriceListError("금액 칸에 숫자가 아닌 값이 있습니다.")
    if isinstance(value, (int, float)):
        if float(value) != int(value) or value < 0:
            raise PriceListError(f"금액은 0 이상 원 단위 정수여야 합니다: {value}")
        return int(value)
    cleaned = re.sub(r"[,\s원]", "", str(value))
    if cleaned == "":
        return None
    if not cleaned.isdigit():
        raise PriceListError(f"금액 칸에 숫자가 아닌 값이 있습니다: {_text(value, 40)}")
    return int(cleaned)


def _cell(value: Any) -> Any:
    """칸 값 — 정수 금액은 정수로, 나머지는 글자로(소수 금액은 글자로 남아 검사에서 걸린다)."""
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _text(value)


def item_name(row: dict[str, Any], item: dict[str, Any]) -> str:
    cells = row.get("cells") or []
    col = item.get("name_col", 0)
    return _text(cells[col]) if 0 <= col < len(cells) else ""


def item_price(row: dict[str, Any], item: dict[str, Any]) -> Optional[int]:
    cells = row.get("cells") or []
    col = item.get("price_col", 1)
    return _price(cells[col]) if 0 <= col < len(cells) else None


def iter_items(sheet: dict[str, Any]):
    """``(category, row, item)`` 를 차례대로."""
    for category in sheet.get("categories") or []:
        for row in category.get("rows") or []:
            for item in row.get("items") or []:
                yield category, row, item


# --------------------------------------------------------------------------
# 불러오기(단가표 HTML 의 <script id="data">) — 화면에 띄울 판 초안만 만든다
# --------------------------------------------------------------------------
_BAND_MAX = (
    (re.compile(r"\(폭\s*(\d+)\s*mm\s*이하\)"), "depth", None),
    (re.compile(r"\(폭\s*(\d+)\s*~\s*(\d+)\s*mm\)"), "depth", "range"),
    (re.compile(r"\(폭\s*(\d+)\s*mm\s*이상\)"), "depth", "min"),
    (re.compile(r"\(W\s*(\d+)\s*기준\)"), "width", None),
    (re.compile(r"\((\d+)\s*이하\)"), "width", None),
    (re.compile(r"(\d+)\s*이하$"), "width", None),
)


def _band_cond(name: str) -> Optional[dict[str, Any]]:
    for pattern, dim, shape in _BAND_MAX:
        match = pattern.search(name)
        if not match:
            continue
        group = _text(name[:match.start()].rstrip(" /(")) or name
        if shape == "range":
            return {"dim": dim, "min": int(match.group(1)), "max": int(match.group(2)), "group": group}
        if shape == "min":
            return {"dim": dim, "min": int(match.group(1)) + 1, "group": group}
        return {"dim": dim, "max": int(match.group(1)), "group": group}
    return None


def infer_item(name: str, *, in_base: bool) -> dict[str, Any]:
    """불러올 때 붙이는 기본 계산 정보(관리 화면에서 고친다). 이름 글자 규칙은 불러오기 기본값에만 쓴다."""
    meta: dict[str, Any] = {"role": "product" if in_base else "option", "unit": "개", "kind": "count",
                            "cond": {}, "partner_label": "", "pick_names": [name], "for_products": [],
                            "pickable": True}
    band = _band_cond(name)
    if "1m 당" in name:
        meta.update(kind="meter", unit="m")
    elif "100mm 당" in name:
        meta.update(kind="over", cond={"per": 100})
    elif band:
        meta.update(kind="band", cond=band)
        if band["dim"] == "width":
            meta["role"] = "product"
    elif in_base and re.search(r"\(\d단\)", name):
        meta.update(kind="fixed")
    elif in_base:
        meta.update(kind="ja", unit="자")
    elif "도어" in name:
        meta["unit"] = "짝"
    elif "통 추가" in name or "통당" in name:
        meta["unit"] = "통"
    if name.startswith("TYPE ") or "통 추가" in name:
        meta["pickable"] = False
    return meta


def _fill_band_mins(sheet: dict[str, Any]) -> None:
    """같은 묶음 구간 줄은 앞 줄 최대 + 1 이 다음 줄 최소(불러오기 기본값)."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for _cat, _row, item in iter_items(sheet):
        cond = item.get("cond") or {}
        if item.get("kind") == "band" and cond.get("max") is not None:
            groups.setdefault((cond.get("group", ""), cond.get("dim", "")), []).append(cond)
    for conds in groups.values():
        conds.sort(key=lambda c: c["max"])
        previous = None
        for cond in conds:
            if "min" not in cond and previous is not None:
                cond["min"] = previous + 1
            previous = cond["max"]


def sheet_from_source(categories: list[dict[str, Any]], *, brand: str,
                      reuse_keys: Optional[dict[str, str]] = None, seq: int = 0) -> dict[str, Any]:
    """단가표 HTML 한 브랜드의 카테고리 목록 → 판 초안. ``reuse_keys`` = 이름 → 지금 판 열쇠(같은 이름은 같은 줄)."""
    reuse = dict(reuse_keys or {})
    used: set[str] = set()
    out = {"schema": 1, "brand": _text(brand, 20), "categories": [], "retired": [], "seq": seq}
    for raw in categories:
        types = [str(t) for t in (raw.get("types") or [])]
        title = _text(raw.get("title"), 60)
        in_base = str(raw.get("kind")) in ("base", "custom") or "기본 제품" in title
        category = {
            "id": _text(raw.get("id"), 20), "side": "right" if raw.get("side") == "right" else "left",
            "title": title, "headers": [_text(h, 60) for h in raw.get("headers") or []], "types": types,
            "layout": {k: raw.get(k) for k in ("kind", "rowCells", "categoryWidths", "rowWidths") if k in raw},
            "rows": [],
        }
        for cells in raw.get("rows") or []:
            row = {"cells": [_cell(c) for c in (cells or [])], "items": []}
            for col, kind in enumerate(types[:len(row["cells"])]):
                if kind != "text" or col + 1 >= len(types) or types[col + 1] != "price":
                    continue
                name = _text(row["cells"][col])
                if not name:
                    continue
                key = reuse.get(name)
                if not key or key in used:
                    out["seq"] += 1
                    key = f"r{out['seq']}"
                used.add(key)
                row["items"].append({"key": key, "name_col": col, "price_col": col + 1,
                                     **infer_item(name, in_base=in_base)})
            category["rows"].append(row)
        out["categories"].append(category)
    _fill_band_mins(out)
    return out


def parse_source_html(html: str) -> dict[str, list[dict[str, Any]]]:
    """단가표 HTML → ``{브랜드: 카테고리 목록}``. 자료 칸이 없거나 깨졌으면 오류."""
    if not isinstance(html, str) or not html.strip():
        raise PriceListError("단가표 HTML 파일을 골라 주세요.")
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise PriceListError("파일이 너무 큽니다(5MB 까지).")
    match = _DATA_RE.search(html)
    if not match:
        raise PriceListError("이 파일에서 단가를 찾지 못했습니다. 통합 단가표 편집기로 저장한 파일인지 확인해 주세요.")
    try:
        data = json.loads(match.group(1))
    except (TypeError, ValueError) as exc:
        raise PriceListError("단가표 HTML 의 단가 자료가 깨져 있습니다.") from exc
    brands = data.get("brands") if isinstance(data, dict) else None
    if not isinstance(brands, dict) or not brands:
        raise PriceListError("단가표 HTML 에 브랜드 자료가 없습니다.")
    return {str(k): v for k, v in brands.items() if isinstance(v, list)}


def import_sheets(html: str, *, current: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """불러오기 — 브랜드마다 판 초안(저장 안 함). 지금 판이 있으면 같은 이름 줄은 같은 열쇠를 쓴다."""
    reuse: dict[str, str] = {}
    seq = 0
    if current:
        seq = int(current.get("seq") or 0)
        for _cat, row, item in iter_items(current):
            reuse.setdefault(item_name(row, item), item["key"])
        for old in current.get("retired") or []:
            reuse.setdefault(_text(old.get("name")), old.get("key"))
    sheets = {brand: sheet_from_source(cats, brand=brand, reuse_keys=reuse, seq=seq)
              for brand, cats in parse_source_html(html).items()}
    return {"brands": list(sheets), "sheets": sheets}


# --------------------------------------------------------------------------
# 검사 · 정리(저장 전 — 화면이 보낸 판을 서버가 다시 만든다)
# --------------------------------------------------------------------------
def _names(values: Any) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, list) else []:
        name = _text(value, 60)
        if name and name not in out:
            out.append(name)
    return out[:MAX_NAMES]


def _cond(kind: str, raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    cond: dict[str, Any] = {}
    if kind == "band":
        cond["dim"] = raw.get("dim") if raw.get("dim") in DIMS else "width"
        for bound in ("min", "max"):
            if raw.get(bound) not in (None, ""):
                cond[bound] = int(raw[bound])
        if raw.get("group"):
            cond["group"] = _text(raw["group"], 60)
        if raw.get("over_key"):
            cond["over_key"] = _text(raw["over_key"], 20)
    elif kind == "over":
        cond["per"] = int(raw.get("per") or 100)
    return cond


def _clean_item(raw: dict[str, Any], ncells: int, errors: list[str]) -> Optional[dict[str, Any]]:
    key = _text(raw.get("key"), 20)
    kind = raw.get("kind") if raw.get("kind") in KINDS else None
    unit = raw.get("unit") if raw.get("unit") in UNITS else None
    try:
        name_col, price_col = int(raw.get("name_col", 0)), int(raw.get("price_col", 1))
    except (TypeError, ValueError):
        name_col = price_col = -1
    if not _KEY_RE.match(key) or kind is None or unit is None or not (0 <= name_col < ncells and 0 <= price_col < ncells):
        errors.append("계산 정보가 잘못된 줄이 있습니다. 화면을 새로 고친 뒤 다시 해 주세요.")
        return None
    try:
        cond = _cond(kind, raw.get("cond"))
    except (TypeError, ValueError):
        errors.append("크기 구간 · 넘친 만큼의 mm 값은 숫자로 적어 주세요.")
        return None
    return {"key": key, "name_col": name_col, "price_col": price_col,
            "role": raw.get("role") if raw.get("role") in ROLES else "option",
            "unit": unit, "kind": kind, "cond": cond, "partner_label": _text(raw.get("partner_label"), 60),
            "pick_names": _names(raw.get("pick_names")), "for_products": _names(raw.get("for_products")),
            "pickable": bool(raw.get("pickable", True))}


def _check_names(sheet: dict[str, Any], errors: list[str]) -> None:
    """고르는 이름은 한 줄만(같은 구간 묶음은 예외) · '이 제품일 때만'은 있는 제품 이름이어야 한다."""
    owners: dict[tuple[str, str], set[str]] = {}
    products: set[str] = set()
    for _cat, row, item in iter_items(sheet):
        if not item["pickable"]:
            continue
        group = item["cond"].get("group") if item["kind"] == "band" else None
        for name in item["pick_names"] or [item["partner_label"] or item_name(row, item)]:
            owners.setdefault((item["role"], name), set()).add(f"band:{group}" if group else item["key"])
            if item["role"] == "product":
                products.add(name)
    for (role, name), keys in owners.items():
        if len(keys) > 1:
            errors.append(f"고르는 이름이 여러 줄에 겹칩니다: {name} — 한 줄에만 두세요.")
    for _cat, row, item in iter_items(sheet):
        for name in item["for_products"]:
            if name not in products:
                errors.append(f"{item_name(row, item)}: '이 제품일 때만 보임'에 없는 제품 이름이 있습니다 — {name}")


def clean_sheet(raw: Any) -> dict[str, Any]:
    """화면이 보낸 판 → 저장할 판. 모양 · 금액 · 계산 정보를 다시 만들고 틀린 곳은 글 목록으로 막는다."""
    if not isinstance(raw, dict) or not isinstance(raw.get("categories"), list) or not raw["categories"]:
        raise PriceListError("단가표가 비어 있습니다.")
    errors: list[str] = []
    keys: set[str] = set()
    out = {"schema": 1, "brand": _text(raw.get("brand"), 20), "categories": [], "retired": [], "seq": 0}
    count = 0
    for cat in raw["categories"]:
        cat = cat if isinstance(cat, dict) else {}
        types = [t if t in ("text", "price") else "text" for t in (cat.get("types") or [])]
        category = {"id": _text(cat.get("id"), 20), "side": "right" if cat.get("side") == "right" else "left",
                    "title": _text(cat.get("title"), 60), "headers": [_text(h, 60) for h in cat.get("headers") or []],
                    "types": types, "layout": cat.get("layout") if isinstance(cat.get("layout"), dict) else {},
                    "rows": []}
        for row in cat.get("rows") or []:
            row = row if isinstance(row, dict) else {}
            cells = [_cell(c) for c in row.get("cells") or []]
            clean = {"cells": cells, "items": []}
            for raw_item in row.get("items") or []:
                item = _clean_item(raw_item if isinstance(raw_item, dict) else {}, len(cells), errors)
                if item is None:
                    continue
                if item["key"] in keys:
                    errors.append("같은 줄이 두 번 들어갔습니다. 화면을 새로 고친 뒤 다시 해 주세요.")
                keys.add(item["key"])
                try:
                    price = item_price(clean, item)
                    cells[item["price_col"]] = "" if price is None else price
                except PriceListError as exc:
                    where = item_name(clean, item) or f"'{category['title'] or '단가표'}'의 이름 빈 품목"
                    errors.extend(f"{where}: {e}" for e in exc.errors)
                if not item_name(clean, item):
                    errors.append(f"'{category['title'] or '단가표'}'에 이름이 빈 품목이 있습니다. 이름을 적거나 줄을 빼 주세요.")
                clean["items"].append(item)
                count += 1
            category["rows"].append(clean)
        out["categories"].append(category)
    if count > MAX_ITEMS:
        errors.append(f"품목이 너무 많습니다({MAX_ITEMS}개까지).")
    # 지운 줄(retired)은 화면 값을 믿지 않고 저장 때 옛 판에서 다시 만든다(save_price_list · _retire_missing).
    out["seq"] = max([int(raw.get("seq") or 0)] + [int(_KEY_RE.match(k).group(1)) for k in keys])
    _check_names(out, errors)
    if errors:
        raise PriceListError(list(dict.fromkeys(errors))[:30])  # 같은 글은 한 번만
    return out


# --------------------------------------------------------------------------
# 판 읽기 · 저장
# --------------------------------------------------------------------------
def active_price_list(db, org_id: int) -> Optional[PartnerPriceList]:
    return (db.query(PartnerPriceList)
            .filter(PartnerPriceList.partner_org_id == org_id, PartnerPriceList.status == "ACTIVE")
            .first())


def list_versions(db, org_id: int) -> list[PartnerPriceList]:
    return (db.query(PartnerPriceList).filter(PartnerPriceList.partner_org_id == org_id)
            .order_by(PartnerPriceList.version.desc()).all())


def _retire_missing(new_sheet: dict[str, Any], old_sheet: dict[str, Any]) -> None:
    """옛 판에 있던 줄이 새 판에 없으면 ``retired`` 에 이름 · 금액 · 계산 정보를 남긴다(옛 선택이 끊기지 않게)."""
    present = {item["key"] for _c, _r, item in iter_items(new_sheet)} | {o["key"] for o in new_sheet["retired"]}
    for _cat, row, item in iter_items(old_sheet):
        if item["key"] not in present:
            try:
                price = item_price(row, item)
            except PriceListError:
                price = None
            new_sheet["retired"].append({**item, "name": item_name(row, item), "price": price, "pickable": False})
            present.add(item["key"])
    for old in old_sheet.get("retired") or []:
        if old.get("key") not in present:
            new_sheet["retired"].append(old)
            present.add(old.get("key"))
    new_sheet["seq"] = max(int(new_sheet.get("seq") or 0), int(old_sheet.get("seq") or 0))


def save_price_list(db, org_id: int, raw_sheet: Any, *, label: Any, effective_from: Any,
                    base_id: Optional[int], user_id: Optional[int]) -> PartnerPriceList:
    """새 판 저장 — 지금 판은 RETIRED, 새 판이 ACTIVE. 커밋은 부르는 쪽이 한다.

    ``base_id`` = 화면이 열어 둔 지금 판 id(없으면 None). 그 사이 다른 사람이 저장했으면 :class:`PriceListConflict`.
    """
    label_text = _text(label, 40)
    if not label_text:
        raise PriceListError("판 이름을 적어 주세요(예: 11월판).")
    try:
        start = dt.date.fromisoformat(str(effective_from or ""))
    except ValueError as exc:
        raise PriceListError("적용 시작일을 골라 주세요.") from exc
    org = db.query(PartnerOrg).filter(PartnerOrg.id == org_id).with_for_update().first()
    if org is None:
        raise PriceListError("협력사를 찾을 수 없습니다.")
    sheet = clean_sheet(raw_sheet)
    current = active_price_list(db, org_id)
    if (current.id if current else None) != (int(base_id) if base_id else None):
        raise PriceListConflict("그사이 다른 사람이 새 판을 저장했습니다. 화면을 새로 고친 뒤 다시 고쳐 주세요.")
    if current is not None:
        _retire_missing(sheet, current.sheet or {})
        current.status = "RETIRED"
        db.flush()
    last = db.query(func.max(PartnerPriceList.version)).filter(PartnerPriceList.partner_org_id == org_id).scalar()
    row = PartnerPriceList(partner_org_id=org_id, version=int(last or 0) + 1, label=label_text,
                           effective_from=start, status="ACTIVE", sheet=sheet,
                           rules=dict((current.rules if current else None) or DEFAULT_RULES), created_by=user_id)
    db.add(row)
    db.flush()
    return row


def version_summary(row: PartnerPriceList, names: Optional[dict[int, str]] = None) -> dict[str, Any]:
    return {"id": row.id, "version": row.version, "label": row.label, "status": row.status,
            "effective_from": row.effective_from.isoformat() if row.effective_from else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by": (names or {}).get(row.created_by)}
