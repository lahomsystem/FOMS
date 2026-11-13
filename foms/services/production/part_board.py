"""생산 파트 도면 카드 읽기 모델 — 설계서 §15.6 '오른쪽 장' · D48 · D56 · D57(P15-3, 라우트에는 아직 잇지 않는다).

입력은 지금 날짜 탭이 이미 만든 날짜 묶음(:func:`foms.services.production_home_days.production_home_days` 의 ``panes``)
이다 — 그날 생산 단계 주문 묶음(``make_rows`` · 만들 것 줄 순서)과 '도면·컨펌 기다림'(``wait_rows``) · 제작 완료
(``done_rows``)를 그대로 다시 쓴다. 여기서 더하는 쿼리는 표시 줄 읽기 **한 번**(``order_id IN (그날들 생산 주문)``)뿐이고
카드 수와 무관하다.

* 카드 = 확정 도면 한 장(:func:`resolve_final_drawing_files` 의 항목, 순서 = 도면 번호).
* 내 파트 상태 · 맡은/끝낸 사람 이름 · 다른 파트 한 줄 낱말(재단: 끝 · 기본 · 중 · 안 봄, 그 밖: 끝 · 중 · 아직).
* 칸 숫자: 파트 계정 = 내 것(작업 필요 = 내가 맡은 장, 완료 = 내가 끝낸 장 — 재단은 끝 + 기본), 관리자 · 읽기 전용 =
  그 파트 전체. 재단의 '안 본 장' 수도 센다. 숫자는 늘 읽은 줄 전부에서 센다(캡과 무관).
* 바뀐 도면(D56): 같은 ``sheet_id`` 의 옛 key 줄이 있으면 짝을 짓는다. 시트 신원이 없는 직접 올린 파일은 짝이 없다.
* 한 장 카드 200장 캡 — 넘친 수를 함께 돌려준다(조용히 자르지 않는다).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_confirm_partial import file_item_uids, item_ref
from foms.services.production.part_access import (
    VIEW_NONE,
    VIEW_PART,
    part_account_part,
    part_view_mode,
    writable_parts,
)
from foms.services.production.part_constants import (
    MARK_STATE_NONE,
    PART_CUT,
    PRODUCTION_PART_DEFS,
    PRODUCTION_PART_KEYS,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.part_mark_rules import MarkSnapshot
from foms.services.production_dashboard_display import _production_spec_display
from models import ProductionPartMark

#: 한 장(날짜 하나)에 그리는 카드 상한 — 넘친 수는 ``hidden`` 으로 알린다(§15.6 안전 캡).
PART_BOARD_CARD_CAP = 200

#: 카드 작은 그림을 만들 수 있는 확장자(작은 그림 길 ``foms/web/production/part_thumb.py`` 와 카드가 같은 판정을 쓴다).
#: 그 밖(PDF 등)은 카드에 파일 표 + 누르면 파일 열기(§15.6 '크게 보기').
PART_THUMB_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

#: 다른 파트 한 줄 낱말(D51 — 낱말은 그대로, 색은 ``tone`` 으로 화면이 고른다).
_CUT_WORDS = {"done": "끝", "basic": "기본", "need": "중", "none": "안 봄"}
_OTHER_WORDS = {"done": "끝", "need": "중", "none": "아직"}

MarkIndex = dict[tuple[int, str, str], Any]
SheetIndex = dict[tuple[int, str], list[Any]]


def other_part_word(part: str, state_key: str) -> dict[str, str]:
    """다른 파트 한 줄의 낱말 하나.

    Args:
        part: 파트 key.
        state_key: none · need · basic · done.

    Returns:
        ``{part, label, word, tone}`` — 재단은 끝 · 기본 · 중 · 안 봄, 그 밖은 끝 · 중 · 아직(D57: 안 고름 = 아직).
    """
    words = _CUT_WORDS if part == PART_CUT else _OTHER_WORDS
    tone = state_key if state_key in words else "none"
    return {"part": part, "label": PRODUCTION_PART_LABELS[part], "word": words[tone], "tone": tone}


def is_part_thumb_image(entry: dict[str, Any]) -> bool:
    """확정 도면 한 장이 작은 그림을 만들 수 있는 그림 파일인지(저장소 key 확장자, 없으면 파일 이름).

    Args:
        entry: 확정 도면 항목(``key`` · ``filename``).

    Returns:
        :data:`PART_THUMB_IMAGE_EXTS` 중 하나로 끝나면 True.
    """
    for name in (entry.get("key"), entry.get("filename")):
        text = str(name or "").strip().lower()
        if "." in text.rsplit("/", 1)[-1]:
            return text.endswith(PART_THUMB_IMAGE_EXTS)
    return False


def fetch_part_marks(db: Any, order_ids: Iterable[int]) -> list[Any]:
    """그날들 생산 주문의 표시 줄 전부 — 쿼리 한 번(주문이 없으면 0번).

    Args:
        db: 세션.
        order_ids: 주문 id 들.

    Returns:
        ``ProductionPartMark`` 줄 목록(네 파트 모두 — 다른 파트 한 줄에 쓴다).
    """
    ids = sorted({int(i) for i in order_ids})
    if not ids:
        return []
    return db.query(ProductionPartMark).filter(ProductionPartMark.order_id.in_(ids)).all()


def index_marks(marks: Iterable[Any]) -> tuple[MarkIndex, SheetIndex]:
    """표시 줄 → (장 · 파트 자리 사전, 시트 신원 사전).

    Returns:
        ``({(order_id, key, part): 줄}, {(order_id, sheet_id): [줄…]})`` — 둘째는 시트 신원이 있는 줄만.
    """
    by_slot: MarkIndex = {}
    by_sheet: SheetIndex = {}
    for row in marks:
        by_slot[(int(row.order_id), str(row.drawing_key), str(row.part))] = row
        if row.sheet_id:
            by_sheet.setdefault((int(row.order_id), str(row.sheet_id)), []).append(row)
    return by_slot, by_sheet


def card_item_text(sd: dict[str, Any], entry: dict[str, Any], row: dict[str, Any]) -> tuple[str, str]:
    """카드 품목 글 — ``item_uids``(없으면 마법사 시트)로 이은 품목 이름 + 첫 품목 치수, 못 이으면 지금 큰 줄 글.

    Args:
        sd: 주문 structured_data.
        entry: 확정 도면 항목.
        row: 첫 화면 행(``v3_product_label`` · ``v3_spec_display``).

    Returns:
        ``(품목 이름, 치수)``.
    """
    items = sd.get("items") if isinstance(sd.get("items"), list) else []
    refs = {item_ref(items, i): it for i, it in enumerate(items) if isinstance(it, dict)}
    linked = [refs[uid] for uid in file_item_uids(sd, entry) if uid in refs]
    names = [str(it.get("product_name") or it.get("name") or "").strip() for it in linked]
    names = [name for name in names if name]
    if names:
        return ", ".join(names), _production_spec_display(linked[0])
    return str(row.get("v3_product_label") or ""), str(row.get("v3_spec_display") or "")


def _prev_word(row: Any) -> str:
    """옛 판 표시 한 줄의 낱말 — '재단 끝(김재단)' · '기본(박재단)' · '재단 중(박재단)'."""
    label = PRODUCTION_PART_LABELS.get(str(row.part), "")
    state = MarkSnapshot.from_row(row).seen_key
    if state == "done":
        return f"{label} 끝({row.done_by_name or '-'})"
    if state == "basic":
        return f"기본({row.done_by_name or '-'})"
    return f"{label} 중({row.picked_by_name or '-'})"


def replaced_info(order_id: int, entry: dict[str, Any], current_keys: set[str], by_sheet: SheetIndex,
                  part: str) -> Optional[dict[str, Any]]:
    """바뀐 도면 짝(D56) — 같은 시트 신원의 옛 key 줄이 있으면 전 판 진행을 붙인다.

    Args:
        order_id: 주문 id.
        entry: 지금 확정 도면 항목(``sheet_id`` 가 없으면 짝 없음 — 직접 올린 파일).
        current_keys: 그 주문 지금 확정 도면 key 집합.
        by_sheet: :func:`index_marks` 의 시트 신원 사전.
        part: 보고 있는 파트.

    Returns:
        ``{label, prev:{part:{state, name}}}`` 또는 None. ``label`` 은 보는 파트의 전 판 진행(없으면 '바뀐 도면').
    """
    sheet_id = str(entry.get("sheet_id") or "")
    if not sheet_id:
        return None
    old = [r for r in by_sheet.get((order_id, sheet_id), []) if str(r.drawing_key) not in current_keys]
    if not old:
        return None
    latest: dict[str, Any] = {}
    for row in sorted(old, key=lambda r: (r.updated_at is not None, r.updated_at)):
        if row.state != MARK_STATE_NONE:
            latest[str(row.part)] = row
    prev = {key: {"state": MarkSnapshot.from_row(r).seen_key, "name": r.done_by_name or r.picked_by_name}
            for key, r in latest.items()}
    mine = latest.get(part)
    label = f"바뀐 도면 · 전 판 {_prev_word(mine)}" if mine is not None else "바뀐 도면"
    return {"label": label, "prev": prev}


def _badge(state: str, mine_mode: bool, picked_by_me: bool) -> Optional[str]:
    """내 파트 배지 — 안 봄 · 안 고름은 배지 없음(D52 무채색 배지 금지). 파트 계정에게 남이 맡은 장은 '맡음'."""
    if state == "need":
        return "taken" if mine_mode and not picked_by_me else "need"
    return state if state in ("done", "basic") else None


def build_card(row: dict[str, Any], entry: dict[str, Any], position: tuple[int, int, int], marks: MarkIndex,
               ctx: dict[str, Any]) -> dict[str, Any]:
    """카드 한 장(확정 도면 한 장) 자료.

    Args:
        row: 첫 화면 행(생산 단계 주문).
        entry: 확정 도면 항목.
        position: ``(주문 순서, 장 번호 1부터, 장 수)``.
        marks: :func:`index_marks` 의 자리 사전.
        ctx: ``{part, mine, user_id, by_sheet, current_keys}``.

    Returns:
        카드 dict(주문 · 장 key · 도면 n/N · 품목 · 내 파트 상태 · 이름 · 배지 · 칸 소속 · 다른 파트 · 바뀐 도면).
    """
    order_id, key, part, me = int(row["id"]), entry["key"], ctx["part"], ctx["user_id"]
    snap = MarkSnapshot.from_row(marks.get((order_id, key, part)))
    state = snap.seen_key
    picked_by_me = snap.picked_by_user_id is not None and snap.picked_by_user_id == me
    done_by_me = snap.done_by_user_id is not None and snap.done_by_user_id == me
    item_label, item_spec = card_item_text(row.get("structured_data") or {}, entry, row)
    others = [other_part_word(p, MarkSnapshot.from_row(marks.get((order_id, key, p))).seen_key)
              for p in PRODUCTION_PART_KEYS if p != part]
    finished = state in ("done", "basic")
    return {
        "order_id": order_id, "customer_name": row.get("customer_name") or "-", "has_changes": bool(row.get("has_changes")),
        "key": key, "filename": entry.get("filename") or "", "view_url": entry.get("view_url") or "",
        "is_image": is_part_thumb_image(entry),
        "sheet_id": entry.get("sheet_id"), "order_pos": position[0], "no": position[1], "of": position[2],
        "item_label": item_label, "item_spec": item_spec, "state": state,
        "picked_by_name": snap.picked_by_name, "done_by_name": snap.done_by_name,
        "picked_by_me": picked_by_me, "done_by_me": done_by_me,
        "taken_by_other": state == "need" and not picked_by_me,
        "badge": _badge(state, ctx["mine"], picked_by_me),
        "in_need": state == "need" and (picked_by_me or not ctx["mine"]),
        "in_done": finished and (done_by_me or not ctx["mine"]),
        "others": others,
        "replaced": replaced_info(order_id, entry, ctx["current_keys"][order_id], ctx["by_sheet"], part),
    }


def sort_cards(cards: list[dict[str, Any]], part: str) -> list[dict[str, Any]]:
    """카드 순서 — 재단은 안 본 장 먼저, 그다음 주문 · 장 번호 순. 그 밖 파트는 주문 · 장 번호 순.

    주문 순서는 만들 것 줄 순서(``order_pos``) 그대로다.
    """
    if part == PART_CUT:
        return sorted(cards, key=lambda c: (0 if c["state"] == "none" else 1, c["order_pos"], c["no"]))
    return sorted(cards, key=lambda c: (c["order_pos"], c["no"]))


def card_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    """칸 숫자 — 전체 도면 · 작업 필요 · 완료 · 안 본(안 고른) 장. 캡과 무관하게 모든 카드에서 센다."""
    return {
        "all": len(cards),
        "need": sum(1 for c in cards if c["in_need"]),
        "done": sum(1 for c in cards if c["in_done"]),
        "unseen": sum(1 for c in cards if c["state"] == "none"),
    }


def build_pane_board(pane: dict[str, Any], marks: MarkIndex, ctx: dict[str, Any]) -> dict[str, Any]:
    """날짜 한 장의 파트 판 — 카드 · 칸 숫자 · 캡 · 기다림 · 제작 완료 수.

    Args:
        pane: 날짜 묶음 한 장(``make_rows`` · ``wait_rows`` · ``done_rows`` · ``total``).
        marks: 자리 사전.
        ctx: :func:`build_card` 와 같은 맥락.

    Returns:
        ``{key, cards, hidden, counts, orders_total, drawn_orders, wait_rows, no_drawing_rows, wait_count, done_count}``.
    """
    cards: list[dict[str, Any]] = []
    no_drawing: list[dict[str, Any]] = []
    for order_pos, row in enumerate(pane.get("make_rows") or []):
        files = ctx["files"][int(row["id"])]
        if not files:
            no_drawing.append(row)  # 생산 단계인데 확정 도면 0장 — '도면 없음' 으로 기다림 묶음에
            continue
        for index, entry in enumerate(files):
            cards.append(build_card(row, entry, (order_pos, index + 1, len(files)), marks, ctx))
    cards = sort_cards(cards, ctx["part"])
    wait_rows = list(pane.get("wait_rows") or [])
    return {
        "key": pane.get("key"),
        "cards": cards[:PART_BOARD_CARD_CAP],
        "hidden": max(0, len(cards) - PART_BOARD_CARD_CAP),
        "counts": card_counts(cards),
        "orders_total": int(pane.get("total") or 0),
        "drawn_orders": len(pane.get("make_rows") or []) - len(no_drawing),
        "wait_rows": wait_rows,
        "no_drawing_rows": no_drawing,
        "wait_count": len(wait_rows) + len(no_drawing),
        "done_count": len(pane.get("done_rows") or []),
    }


def resolve_board_part(user: Any, requested: Any) -> tuple[str, Optional[str]]:
    """보기 모드와 볼 파트 — 파트 계정은 늘 자기 파트, 관리자 · 읽기 전용은 고른 파트(모르면 재단).

    Returns:
        ``(모드, 파트 key)`` — 볼 수 없는 사람은 ``("none", None)``.
    """
    mode = part_view_mode(user)
    if mode == VIEW_NONE:
        return mode, None
    if mode == VIEW_PART:
        return mode, part_account_part(user)
    text = str(requested or "").strip().lower()
    return mode, text if text in PRODUCTION_PART_KEYS else PART_CUT


def build_part_board(db: Any, user: Any, days: dict[str, Any], *, part: Any = None) -> Optional[dict[str, Any]]:
    """그날들(날짜 탭 ``panes`` 전부)의 파트 도면 카드 판. 쿼리는 표시 줄 읽기 한 번만 더한다.

    Args:
        db: 세션.
        user: 보는 사람.
        days: :func:`production_home_days` 결과(``panes`` 를 쓴다).
        part: 관리자 · 읽기 전용이 고른 파트(``?part=``). 파트 계정은 무시하고 자기 파트.

    Returns:
        ``{mode, part, part_label, parts, writable, mine, cap, panes:{key: 장 판}}`` 또는 None(볼 수 없는 사람).
    """
    mode, board_part = resolve_board_part(user, part)
    if board_part is None:
        return None
    panes = list(days.get("panes") or [])
    rows = [row for pane in panes for row in (pane.get("make_rows") or [])]
    files = {int(row["id"]): resolve_final_drawing_files(row.get("structured_data") or {}) for row in rows}
    by_slot, by_sheet = index_marks(fetch_part_marks(db, (oid for oid, entries in files.items() if entries)))
    ctx = {
        "part": board_part, "mine": mode == VIEW_PART, "user_id": getattr(user, "id", None), "files": files,
        "by_sheet": by_sheet, "current_keys": {oid: {e["key"] for e in entries} for oid, entries in files.items()},
    }
    return {
        "mode": mode, "part": board_part, "part_label": PRODUCTION_PART_LABELS[board_part],
        "parts": [{"key": key, "label": label} for key, label in PRODUCTION_PART_DEFS],
        "writable": board_part in writable_parts(user), "mine": ctx["mine"], "cap": PART_BOARD_CARD_CAP,
        "panes": {pane.get("key"): build_pane_board(pane, by_slot, ctx) for pane in panes},
    }
