"""출고 패킹을 공장마다 — 줄 만들기 · 읽기 · 쓰기 규칙(설계서 2026-11-23 '승인 때 고친 것' 6 ② ③). 순수 함수(쿼리 0).

자료는 지금과 같은 ``structured_data.shipment.packing`` 하나다(칸 셋만 더함)::

    {"items": [...줄 상태...], "updated_at", "departed_at", "departed_by_name",      # 지금 그대로
     "layout": "factory",                                                            # 새 — 공장 꼴로 저장했음
     "factory_loaded": {"1": {"at", "by_name", "by_user_id", "keys": [...]}, ...}}   # 새 — 공장마다 상차 완료(누가 · 언제)

* **공장 꼴** = 지금 2공장 장이 있는 주문, 또는 공장 꼴로 저장한 적이 있는 주문(``layout``). 그 밖(1공장뿐)은 지금 목록(제품마다
  "본체 패널 · 도어 · 철물" 3줄) 그대로 — 이 모듈은 그 길에 손대지 않는다.
* **공장 꼴 줄** = 공장마다 [지금 확정 도면 장마다 한 줄("도면 1 붙박이장" — 이어진 품목 이름, 없으면 파일 이름) · "철물 · 기타" 한 줄
  · 손으로 더한 줄]. 열쇠는 장의 신원(``sheet:<시트 id>``, 직접 올린 파일 ``file:<저장 key>``) · ``hardware:<공장>`` · ``custom_…``.
  장의 공장은 읽을 때 ``drawing_factory.sheet_factory`` 로 계산한다 — 장을 옮기면 체크도 같이 옮겨 간다. 손으로 더한 줄은 ``factory``
  칸(없으면 1공장).
* **줄 상태를 지우지 않는다.** 지금 장에 없는 줄(빠진 장 · 옛 제품 줄)은 안 보일 뿐 ``items`` 에 남는다 — 장이 돌아오면 체크도 돌아온다.
  옛 꼴로 체크한 제품 줄이 있는 주문에 2공장 장이 생기면 그 줄들은 공장 꼴 목록에 없다 → 화면에 "다시 체크" 안내(:func:`legacy_count`).
* **상차 완료(공장 f)** 가 살아 있음 — 출발 보고 전: ``factory_loaded[f]`` 가 있고 지금 f 줄 열쇠 ⊆ 저장한 ``keys`` **그리고** f 줄이
  지금 모두 체크됐고 그 체크가 모두 상차 완료 시각 이전(누락 신고는 안 따짐 — 옛 출발 보고 문과 같게). 새 줄(새 장 · 더한 줄)이 오거나
  누가 체크를 풀면 풀리고, 다시 체크만 해서는 안 살아난다 — [N공장 상차 완료]를 다시 눌러야 한다(안 실린 줄이 있는데 출발 보고가
  찍히지 않게). 출발 보고 뒤: 적어 둔 기록이 있으면 그대로 산 것(새 줄 · 체크 풀기로 다시
  안 풀림 — 출발 뒤 단추가 다시 켜지지 않는다). 읽기는 저장값을 고치지 않는다(풀려도 기록은 남고, 다시 누르면 덮는다).
  있는 공장이 모두 상차 완료되는 순간 출발 보고(``departed_at`` · ``departed_by_name``)가 처리된다. 상차 완료 · 출발 보고 모두 취소
  길은 없다(지금과 같다). 이미 산 상차 완료 · 이미 한 출발 보고를 다시 보내면 아무것도 안 바꾼다(``changed`` False).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Optional

from foms.services.orders.drawing_confirm_partial import file_item_uids, item_ref
from foms.services.orders.drawing_factory import current_factories, has_second_factory
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.production.factory_constants import DEFAULT_FACTORY, FACTORIES, factory_label, normalize_factory
from foms.services.shipment.packing_access import FACTORY_FORBIDDEN_CODE, factory_forbidden_message

LAYOUT_KEY = "layout"
LAYOUT_FACTORY = "factory"
LOADED_KEY = "factory_loaded"
HARDWARE_LABEL = "철물 · 기타"
_HW = "hardware:"
_CUSTOM = "custom_"
_STATE_KEYS = ("checked", "at", "by_name", "issue", "issue_at", "issue_by_name")
_LEGACY_KEY = re.compile(r"^item\d+_(?:body|door|hardware)$")

NOT_ALL_CHECKED_MESSAGE = "전 항목 체크 후 출발 보고"  # 지금 글 그대로(출발 보고 문)


class PackingRefusal(Exception):
    """패킹 쓰기를 거절하는 까닭(상태 · 코드 · 글) — API 가 되감은 뒤 응답으로 바꾼다."""

    def __init__(self, status: int, code: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


# --------------------------------------------------------------------------- #
# 읽기
# --------------------------------------------------------------------------- #
def stored_packing(sd: Any) -> Optional[dict[str, Any]]:
    """저장된 패킹(items 가 목록인 것만) — 없으면 None."""
    shipment = sd.get("shipment") if isinstance(sd, dict) else None
    packing = shipment.get("packing") if isinstance(shipment, dict) else None
    if isinstance(packing, dict) and isinstance(packing.get("items"), list):
        return packing
    return None


def is_factory_layout(sd: Any) -> bool:
    """공장 꼴인가 — 지금 2공장 장이 있거나 공장 꼴로 저장한 적이 있다. 아니면 지금 목록 그대로."""
    if not isinstance(sd, dict):
        return False
    if has_second_factory(sd):
        return True
    packing = stored_packing(sd)
    return bool(packing and packing.get(LAYOUT_KEY) == LAYOUT_FACTORY)


def _factory_of(raw: Any) -> int:
    return raw if raw in FACTORIES and not isinstance(raw, bool) else DEFAULT_FACTORY


def _line(key: str, label: str, factory: int, kind: str, row: Any, qty: Any = 1) -> dict[str, Any]:
    line = {"key": key, "label": label, "qty": qty, "checked": False, "at": None, "by_name": None, "issue": None,
            "factory": factory, "kind": kind}
    if isinstance(row, dict):
        for name in _STATE_KEYS:
            if name in row:
                line[name] = row[name]
        line["checked"] = bool(line["checked"])
    return line


def _doc_label(sd: dict[str, Any], entry: dict[str, Any], index: int, refs: dict[str, dict[str, Any]]) -> str:
    names = [str((refs.get(uid) or {}).get("product_name") or (refs.get(uid) or {}).get("name") or "").strip()
             for uid in file_item_uids(sd, entry)]
    names = [n for n in names if n]
    tail = ", ".join(names) if names else str(entry.get("filename") or "").strip()
    return f"도면 {index} {tail}".strip()


def factory_lines(sd: Any) -> list[dict[str, Any]]:
    """공장 꼴 줄 전부(공장 순 → 도면 장 · 철물 · 더한 줄) — 저장 상태를 열쇠로 얹는다. 쿼리 0."""
    sd = sd if isinstance(sd, dict) else {}
    packing = stored_packing(sd) or {}
    stored = [r for r in packing.get("items") or [] if isinstance(r, dict) and r.get("key")]
    rows = {str(r["key"]): r for r in stored}
    items = sd.get("items") if isinstance(sd.get("items"), list) else []
    refs = {item_ref(items, i): it for i, it in enumerate(items) if isinstance(it, dict)}
    docs: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, (entry, factory) in enumerate(current_factories(sd), 1):
        sid = clean_sheet_id(entry.get("sheet_id"))
        if sid:
            seen[sid] = seen.get(sid, 0) + 1
            key = f"sheet:{sid}" if seen[sid] == 1 else f"sheet:{sid}:{seen[sid]}"
        else:
            key = f"file:{entry['key']}"
        docs.append(_line(key, _doc_label(sd, entry, index, refs), factory, "sheet", rows.get(key)))
    customs = [_line(str(r["key"]), str(r.get("label") or ""), _factory_of(r.get("factory")), "custom", r, r.get("qty") or 1)
               for r in stored if str(r["key"]).startswith(_CUSTOM)]
    present = [f for f in FACTORIES if any(l["factory"] == f for l in docs + customs)] or [DEFAULT_FACTORY]
    out: list[dict[str, Any]] = []
    for f in present:
        out += [l for l in docs if l["factory"] == f]
        out.append(_line(f"{_HW}{f}", HARDWARE_LABEL, f, "hardware", rows.get(f"{_HW}{f}")))
        out += [l for l in customs if l["factory"] == f]
    return out


def _when(raw: Any) -> Optional[datetime.datetime]:
    try:
        at = datetime.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)


def _loaded_alive(packing: dict[str, Any], factory: int, lines: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """그 공장 상차 완료 기록이 살아 있으면 그 기록 — 출발 뒤면 기록만 있으면, 출발 전이면 열쇠 ⊆ 기록 · 줄 모두 체크 · 그 체크가
    모두 기록 시각 이전일 때만(풀었다 다시 체크한 줄이 있으면 다시 눌러야 한다). 저장값은 고치지 않는다."""
    record = (packing.get(LOADED_KEY) or {}).get(str(factory)) if isinstance(packing.get(LOADED_KEY), dict) else None
    if not isinstance(record, dict):
        return None
    if packing.get("departed_at"):
        return record
    current = {l["key"] for l in lines}
    saved = {str(k) for k in record.get("keys") or [] if isinstance(k, str)}
    if not current or not current <= saved or not all(l["checked"] for l in lines):
        return None
    loaded_at = _when(record.get("at"))
    if loaded_at is not None and any((_when(l.get("at")) or loaded_at) > loaded_at for l in lines):
        return None
    return record


def factory_groups(sd: Any, lines: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """공장마다 묶음 — ``{factory, label, lines, checked, total, loaded}``(loaded = 살아 있는 상차 완료 기록 또는 None)."""
    lines = factory_lines(sd) if lines is None else lines
    packing = stored_packing(sd) or {}
    groups = []
    for f in FACTORIES:
        own = [l for l in lines if l["factory"] == f]
        if not own:
            continue
        record = _loaded_alive(packing, f, own)
        groups.append({"factory": f, "label": factory_label(f), "lines": own,
                       "checked": sum(1 for l in own if l["checked"]), "total": len(own),
                       "loaded": {"at": record.get("at"), "by_name": record.get("by_name")} if record else None})
    return groups


def legacy_count(sd: Any) -> int:
    """옛 꼴(제품 3줄)로 체크 · 누락 신고한 줄 수 — 공장 꼴 목록에는 없는 줄(출발 보고 전에만 화면 안내)."""
    packing = stored_packing(sd) or {}
    if packing.get("departed_at"):
        return 0
    return sum(1 for r in packing.get("items") or []
               if isinstance(r, dict) and _LEGACY_KEY.match(str(r.get("key") or "")) and (r.get("checked") or r.get("issue")))


def factory_payload(sd: Any, user_factories: tuple[int, ...]) -> dict[str, Any]:
    """API 응답 data(공장 꼴) — 지금 응답 칸(items · checked_count · issues_count · total · persisted · departed_*) + 묶음 칸."""
    lines = factory_lines(sd)
    groups = factory_groups(sd, lines)
    packing = stored_packing(sd)
    can = [g["factory"] for g in groups if g["factory"] in user_factories]
    return {
        "items": lines,
        "checked_count": sum(1 for l in lines if l["checked"]),
        "issues_count": sum(1 for l in lines if l.get("issue")),
        "total": len(lines),
        "persisted": packing is not None,
        "departed_at": (packing or {}).get("departed_at"),
        "departed_by_name": (packing or {}).get("departed_by_name"),
        "layout": LAYOUT_FACTORY,
        "groups": [{k: g[k] for k in ("factory", "label", "checked", "total", "loaded")} | {"can_check": g["factory"] in can}
                   for g in groups],
        "can_check": can,
        "legacy_count": legacy_count(sd),
    }


def packing_glance(sd: Any) -> Optional[dict[str, Any]]:
    """공장 꼴 주문의 카드 글 재료 — 공장 꼴이 아니면 None(지금 글 그대로).

    Returns:
        ``{text, present, departed, groups}`` — text = "1공장 3/4 · 2공장 0/3"(공장이 하나면 "3/4"), present = 저장한 패킹이 있음
        (지금 카드가 숫자를 붙이는 조건과 같다).
    """
    if not is_factory_layout(sd):
        return None
    groups = factory_groups(sd)
    if len(groups) > 1:
        text = " · ".join(f"{g['label']} {g['checked']}/{g['total']}" for g in groups)
    else:
        text = f"{sum(g['checked'] for g in groups)}/{sum(g['total'] for g in groups)}"
    packing = stored_packing(sd)
    return {"text": text, "present": packing is not None, "departed": bool((packing or {}).get("departed_at")),
            "groups": len(groups)}


# --------------------------------------------------------------------------- #
# 쓰기 — 부르는 쪽이 잠근 행의 deepcopy 를 넘기고(재대입 · flag_modified · 이벤트는 부르는 쪽)
# --------------------------------------------------------------------------- #
def _require(factory: int, mine: tuple[int, ...]) -> None:
    if factory not in mine:
        raise PackingRefusal(403, FACTORY_FORBIDDEN_CODE, factory_forbidden_message(factory, mine), {"factory": factory})


def require_first_factory(mine: tuple[int, ...]) -> None:
    """지금 목록(1공장뿐인 주문) 쓰기 — 모든 줄이 1공장 몫이다(2공장 생산팀 계정은 못 씀)."""
    _require(DEFAULT_FACTORY, mine)


def _add_factory(raw: Any, present: list[int], mine: tuple[int, ...]) -> int:
    try:
        factory = normalize_factory(raw)
    except ValueError:
        raise PackingRefusal(400, "BAD_REQUEST", "공장 값이 올바르지 않아요.") from None
    if factory is not None:
        if factory not in present:
            raise PackingRefusal(400, "BAD_REQUEST", "공장 값이 올바르지 않아요.")
        _require(factory, mine)
        return factory
    choices = [f for f in present if f in mine]
    if len(choices) == 1:
        return choices[0]
    if not choices:
        _require(present[0], mine)
    raise PackingRefusal(400, "PACKING_FACTORY_REQUIRED", "어느 공장 줄인지 골라 주세요.")


def _record(packing: dict[str, Any], group: dict[str, Any], *, by_name: str, user_id: Any, now_iso: str) -> None:
    loaded = packing.get(LOADED_KEY) if isinstance(packing.get(LOADED_KEY), dict) else {}
    loaded[str(group["factory"])] = {"at": now_iso, "by_name": by_name, "by_user_id": user_id,
                                     "keys": [l["key"] for l in group["lines"]]}
    packing[LOADED_KEY] = loaded


def apply_factory_write(sd: dict[str, Any], *, updates: Any, add: Optional[dict[str, Any]], loaded: Optional[int],
                        departed: bool, mine: tuple[int, ...], by_name: str, user_id: Any, now_iso: str,
                        new_key: str) -> dict[str, Any]:
    """공장 꼴 패킹 쓰기(제자리) — 체크 · 누락 신고 · 줄 더하기 · 공장 상차 완료 · (옛 단추) 출발 보고.

    Args:
        sd: 잠근 주문 ``structured_data`` 의 사본.
        updates: ``[{key, checked?, issue?}]``(모양은 API 가 봤다). 지금 목록에 없는 열쇠는 지금처럼 건너뛴다.
        add: ``{label, qty, factory?}`` 또는 None(label 은 API 가 다듬었다).
        loaded: 상차 완료할 공장(1 · 2) 또는 None.
        departed: 옛 [상차 완료 → 출발 보고] 단추(남은 공장을 모두 상차 완료로 — 모든 줄 체크가 문).
        mine: 이 사람이 체크할 수 있는 공장(``packing_access.packing_factories``).
        by_name · user_id · now_iso: 누가 · 언제. new_key: 더한 줄 열쇠.

    Returns:
        ``{event_type, changed, factory?, factories?}`` — PACKING_UPDATED · PACKING_FACTORY_LOADED · PACKING_DEPARTED. ``changed``
        False = 이미 산 상차 완료 · 이미 한 출발 보고를 다시 보냈고 그 밖에 바꾼 것도 없음(부르는 쪽은 쓰지 않고 되감는다).

    Raises:
        PackingRefusal: 남의 공장 줄(403) · 공장 값(400) · 그 공장 줄이 다 체크 안 됨(400) · 출발 보고 문(400).
    """
    shipment = sd.get("shipment") if isinstance(sd.get("shipment"), dict) else {}
    sd["shipment"] = shipment
    packing = stored_packing(sd)
    if packing is None:
        packing = {"items": [], "updated_at": None}
        shipment["packing"] = packing
    packing[LAYOUT_KEY] = LAYOUT_FACTORY
    items = packing["items"]
    rows = {str(r.get("key")): r for r in items if isinstance(r, dict)}
    view = {l["key"]: l for l in factory_lines(sd)}
    changed = bool(add)
    for upd in updates or []:
        line = view.get(upd.get("key")) if isinstance(upd, dict) else None
        if line is None:
            continue
        _require(line["factory"], mine)
        changed = True
        row = rows.get(line["key"])
        if row is None:
            row = {"key": line["key"], "label": line["label"], "qty": 1, "checked": False, "at": None, "by_name": None,
                   "issue": None}
            items.append(row)
            rows[line["key"]] = row
        if "checked" in upd:
            checked = bool(upd.get("checked"))
            row.update(checked=checked, at=now_iso if checked else None, by_name=by_name if checked else None)
        if "issue" in upd:
            value = upd.get("issue")
            if value in (None, ""):
                row.update(issue=None, issue_at=None, issue_by_name=None)
            else:
                row.update(issue=value, issue_at=now_iso, issue_by_name=by_name)
    if add:
        present = sorted({l["factory"] for l in view.values()})
        factory = _add_factory(add.get("factory"), present, mine)
        items.append({"key": new_key, "label": add["label"], "qty": add["qty"], "checked": False, "at": None,
                      "by_name": None, "issue": None, "factory": factory})
    packing["updated_at"] = now_iso
    groups = factory_groups(sd)
    result: dict[str, Any] = {"event_type": "PACKING_UPDATED"}
    if loaded is not None:
        group = next((g for g in groups if g["factory"] == loaded), None)
        if group is None:
            raise PackingRefusal(400, "BAD_REQUEST", f"이 주문에는 {factory_label(loaded)} 줄이 없어요.")
        _require(loaded, mine)
        if group["loaded"] is None:  # 이미 산 상차 완료면 다시 안 적는다(시각 · 이름 · 열쇠 · 이벤트 그대로)
            if group["checked"] < group["total"]:
                raise PackingRefusal(400, "PACKING_FACTORY_NOT_READY",
                                     f"{factory_label(loaded)} 줄을 모두 체크해야 상차 완료할 수 있어요.", {"factory": loaded})
            _record(packing, group, by_name=by_name, user_id=user_id, now_iso=now_iso)
            changed = True
            result = {"event_type": "PACKING_FACTORY_LOADED", "factory": loaded}
            groups = factory_groups(sd)
            if not packing.get("departed_at") and all(g["loaded"] for g in groups):
                packing["departed_at"], packing["departed_by_name"] = now_iso, by_name
                result = {"event_type": "PACKING_DEPARTED", "factory": loaded, "factories": [g["factory"] for g in groups]}
    if departed and not packing.get("departed_at"):  # 공장 꼴은 이미 출발 보고했으면 아무것도 안 바꾼다(옛 꼴 길은 지금처럼 다시 적음)
        total = sum(g["total"] for g in groups)
        if total == 0 or sum(g["checked"] for g in groups) < total:
            raise PackingRefusal(400, "PACKING_NOT_ALL_CHECKED", NOT_ALL_CHECKED_MESSAGE)
        for group in groups:
            if not group["loaded"]:
                _require(group["factory"], mine)
                _record(packing, group, by_name=by_name, user_id=user_id, now_iso=now_iso)
        packing["departed_at"], packing["departed_by_name"] = now_iso, by_name
        changed = True
        result = {"event_type": "PACKING_DEPARTED", "factories": [g["factory"] for g in groups]}
    return {**result, "changed": changed}


def strip_client_packing_state(sd: Any) -> list[str]:
    """손님 쪽이 보낸 ``structured_data`` 에서 패킹 자료(``shipment.packing``)를 뺀다(제자리) — 패킹 API 만 쓴다.

    주문 만들기(``order_create._prepare_structured``) · 초안 자동 저장(``erp_orders_structured.api_erp_draft_autosave``)처럼 손님 쪽
    JSON 을 통째로 저장하는 길이 부른다(``drawing_factory.strip_client_factory_state`` 와 같은 꼴). 폼 저장(PUT structured)은
    ``structured_form_projection.SERVER_LOCKED_SUBKEYS["shipment"]`` 잠금이 서버 값을 지킨다.

    Returns:
        뺀 경로(없으면 빈 목록).
    """
    shipment = sd.get("shipment") if isinstance(sd, dict) else None
    if isinstance(shipment, dict) and shipment.pop("packing", None) is not None:
        return ["shipment.packing"]
    return []
