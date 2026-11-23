"""생산 파트 도면 카드 읽기 모델 — 설계서 §15.6 '오른쪽 장' · D48 · D56 · D57(P15-3, 라우트에는 아직 잇지 않는다).

입력은 지금 날짜 탭이 이미 만든 날짜 묶음(:func:`foms.services.production_home_days.production_home_days` 의 ``panes``)
이다 — 그날 생산 단계 주문 묶음(``make_rows`` · 만들 것 줄 순서)과 '도면·컨펌 기다림'(``wait_rows``) · 제작 완료
(``done_rows``)를 그대로 다시 쓴다. 여기서 더하는 쿼리는 표시 줄 읽기 **한 번**(``order_id IN (그날들 생산 주문)``)뿐이고
카드 수와 무관하다.

* 카드 = 확정 도면 한 장(:func:`resolve_final_drawing_files` 의 항목, 순서 = 도면 번호).
* 내 파트 상태 · 맡은/끝낸 사람 이름 · 다른 파트 한 줄 낱말(재단: 끝 · 기본 · 중 · 안 봄, 그 밖: 끝 · 중 · 아직).
* 칸 숫자: 파트 계정 = 내 것(작업 필요 = 내가 맡은 장, 완료 = 내가 끝낸 장 — 재단은 끝 + 기본), 관리자 · 대신 · 읽기 전용 =
  그 파트 전체. 재단의 '안 본 장' 수도 센다. 숫자는 늘 읽은 줄 전부에서 센다(캡과 무관).
* 여러 파트 계정(2026-11-23 §4-12, P2): 판 머리에서 내 파트 사이를 고른다(``pick`` · 주소 ``?part=``), 다른 파트 한 줄에서
  내 파트이고 내가 담당인 장은 "내 담당". 파트 하나인 계정은 고르기 없이 지금 그대로.
* 바뀐 도면(D56): 같은 ``sheet_id`` 의 옛 key 줄이 있으면 짝을 짓는다. 시트 신원이 없는 직접 올린 파일은 짝이 없다.
* 한 장 카드 200장 캡 — 넘친 수를 함께 돌려준다(조용히 자르지 않는다).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_confirm_partial import file_item_uids, item_ref
from foms.services.production.part_access import (
    VIEW_NONE,
    VIEW_PART,
    own_parts,
    part_account_parts,
    part_view_mode,
    writable_parts,
)
from foms.services.production.part_constants import (
    MARK_STATE_NONE,
    PART_CUT,
    PART_INSPECT,
    PRODUCTION_PART_KEYS,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.part_card_state import claim_notes, hand_cell, inspect_block, order_block, sort_rank
from foms.services.production.part_mark_rules import MarkSnapshot, mark_payload
from foms.services.production_dashboard_display import _production_spec_display
from models import ProductionPartMark

#: 한 장(날짜 하나)에 그리는 카드 상한 — 넘친 수는 ``hidden`` 으로 알린다(§15.6 안전 캡).
PART_BOARD_CARD_CAP = 200

#: 카드 작은 그림을 만들 수 있는 확장자(작은 그림 길 ``foms/web/production/part_thumb.py`` 와 카드가 같은 판정을 쓴다).
#: 그 밖(PDF 등)은 카드에 파일 표 + 누르면 파일 열기(§15.6 '크게 보기').
PART_THUMB_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

#: 30초 받아 오기(P15-7)의 서버 시각 되감기(초). 표시 줄 ``updated_at`` 은 쓰는 쪽이 commit **전에** 찍으므로, 받아 오기가
#: 그 사이에 돌면 아직 안 보이는 줄의 시각이 다음 ``since`` 보다 앞서 영영 빠진다. 커서를 이만큼 되감아 겹쳐 받는다
#: (겹친 줄은 화면이 같은 상태면 건너뛴다).
PART_SYNC_OVERLAP_SECONDS = 15

#: 다른 파트 한 줄 낱말(D51 — 낱말은 그대로, 색은 ``tone`` 으로 화면이 고른다).
_CUT_WORDS = {"done": "끝", "basic": "기본", "need": "중", "none": "안 봄"}
_OTHER_WORDS = {"done": "끝", "need": "중", "none": "아직"}
#: 여러 파트 계정(2026-11-23 §4-12 '더함')의 다른 파트 한 줄 — 그 파트도 내 파트이고 내가 담당인 장은 "엣지 내 담당".
#: 파트 하나인 계정 · 관리자 · 대신에게는 생기지 않는다(다른 파트가 내 파트가 아니다).
MINE_TONE = "mine"
MINE_WORD = "내 담당"

MarkIndex = dict[tuple[int, str, str], Any]
SheetIndex = dict[tuple[int, str], list[Any]]


def other_part_word(part: str, state_key: str, mine: bool = False) -> dict[str, str]:
    """다른 파트 한 줄의 낱말 하나.

    Args:
        part: 파트 key.
        state_key: none · need · basic · done.
        mine: 그 파트가 보는 사람의 파트이고 담당이 보는 사람인지(여러 파트 계정만 — :func:`mine_other` ).

    Returns:
        ``{part, label, word, tone}`` — 재단은 끝 · 기본 · 중 · 안 봄, 그 밖은 끝 · 중 · 아직(D57: 안 고름 = 아직).
        ``mine`` 이고 담당 중(need)이면 "내 담당"(tone ``mine``).
    """
    if mine and state_key == "need":
        return {"part": part, "label": PRODUCTION_PART_LABELS[part], "word": MINE_WORD, "tone": MINE_TONE}
    words = _CUT_WORDS if part == PART_CUT else _OTHER_WORDS
    tone = state_key if state_key in words else "none"
    return {"part": part, "label": PRODUCTION_PART_LABELS[part], "word": words[tone], "tone": tone}


def mine_other(row: Any, part: str, viewer_id: Any, viewer_parts: tuple[str, ...]) -> bool:
    """다른 파트 한 줄에서 "내 담당"으로 적을지 — 그 파트가 보는 사람의 파트이고 표시 줄 담당이 보는 사람.

    Args:
        row: 그 파트 표시 줄(없으면 None).
        part: 파트 key.
        viewer_id: 보는 사람 id.
        viewer_parts: 보는 사람의 파트들(:func:`~foms.services.production.part_access.own_parts`).

    Returns:
        셋이 맞으면 True(상태는 :func:`other_part_word` 가 본다).
    """
    return (part in viewer_parts and row is not None and viewer_id is not None
            and getattr(row, "picked_by_user_id", None) == viewer_id)


def part_sync_cursor(now: Optional[datetime.datetime] = None) -> str:
    """30초 받아 오기의 다음 ``since`` — 서버 시각(UTC naive)에서 :data:`PART_SYNC_OVERLAP_SECONDS` 를 뺀 ISO 글.

    화면이 그릴 때(첫 ``since``, ``data-pp-since``)와 ``GET /api/production/part-marks`` 응답(``server_time``)이 같이 쓴다.
    기기 시계는 쓰지 않는다(어긋난 태블릿 시계가 남의 표시를 빠뜨리지 않게).

    Args:
        now: 기준 시각(시험용, 없으면 지금).

    Returns:
        ``YYYY-MM-DDTHH:MM:SS.ffffff`` 꼴 글.
    """
    base = now or now_utc_naive()
    return (base - datetime.timedelta(seconds=PART_SYNC_OVERLAP_SECONDS)).isoformat(timespec="microseconds")


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
    # 같은 시각(일괄 기본 한 번 · 거친 시계 눈금)이면 id 큰 줄이 나중 — 표시 줄 쿼리는 ORDER BY 가 없어 줄 차례에 기대면 흔들린다.
    for row in sorted(old, key=lambda r: (r.updated_at is not None, r.updated_at, getattr(r, "id", None) or 0)):
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


def _other_words(order_id: int, key: str, part: str, marks: MarkIndex, hands: dict[str, Any],
                 ctx: dict[str, Any]) -> list[dict[str, str]]:
    """다른 파트 한 줄 — 표시 줄 낱말. 손으로 체크한 파트(카드 안 씀)는 그 파트 모든 장이 완료라 '끝'(B5′).
    여러 파트 계정이 그 파트도 담당이면 "내 담당"(§4-12)."""
    words = []
    for other in PRODUCTION_PART_KEYS:
        if other == part:
            continue
        row = marks.get((order_id, key, other))
        state = "done" if hands.get(other) else MarkSnapshot.from_row(row).seen_key
        words.append(other_part_word(other, state, mine_other(row, other, ctx["user_id"], ctx["own_parts"])))
    return words


def _card_state(row: dict[str, Any], key: str, snap: MarkSnapshot, ctx: dict[str, Any]) -> dict[str, Any]:
    """3판 칸 — 손 체크 · 막힘 · 밤 넘김 · 바뀐 기록 · 내 담당 꼬리 · 첫 카드(§4-6 · §4-8 · §4-9 · §4-11)."""
    order_id, part, me = int(row["id"]), ctx["part"], ctx["user_id"]
    sd = row.get("structured_data") or {}
    marks = ctx["order_marks"].get(order_id, [])
    hands = ctx["hands"][order_id]
    hand = hands.get(part)
    state = "hand" if hand else snap.seen_key
    picked_by_me = snap.picked_by_user_id is not None and snap.picked_by_user_id == me
    block = None
    if state in ("none", "need"):
        block = ctx["blocks"][order_id] or (inspect_block(sd, marks, key) if part == PART_INSPECT else None)
    # 주문 막힘(보류 · 도면 고치는 중)은 상태와 상관없이 카드에 싣는다 — 완료 · 기본 카드를 되돌린 뒤 JS 가 그리는 칸이
    # 서버가 그리는 칸(막힌 칸 · [맡기 취소][막힌 칸])과 같게(검수 전 막힘은 JS 가 다른 파트 줄로 다시 본다)
    notes = claim_notes(snap, ctx["today"], mine=picked_by_me and ctx["writable"])
    mark = mark_payload(snap) if snap.seen_key != "none" else {}
    notes.update(picked_day=mark.get("picked_day"), picked_at=mark.get("picked_at"), handed_from_name=snap.handed_from_name,
                 handed_at=mark.get("handed_at"))
    return {"state": state, "hand": hand, "block": block, "order_block": ctx["blocks"][order_id], "picked_by_me": picked_by_me,
            "mine_row": state == "need" and picked_by_me and ctx["writable"],
            "first_card": not row.get("home_has_run"), "hand_parts": sorted(p for p, h in hands.items() if h), **notes}


def build_card(row: dict[str, Any], entry: dict[str, Any], position: tuple[int, int, int], marks: MarkIndex,
               ctx: dict[str, Any]) -> dict[str, Any]:
    """카드 한 장(확정 도면 한 장) 자료.

    Args:
        row: 첫 화면 행(생산 단계 주문).
        entry: 확정 도면 항목.
        position: ``(주문 순서, 장 번호 1부터, 장 수)``.
        marks: :func:`index_marks` 의 자리 사전.
        ctx: ``{part, mine, writable, user_id, today, by_sheet, current_keys, order_marks, hands, blocks}``.

    Returns:
        카드 dict(주문 · 장 key · 도면 n/N · 품목 · 내 파트 상태 · 이름 · 배지 · 칸 소속 · 다른 파트 · 바뀐 도면) + 3판 칸
        (``hand`` 손 체크 · ``block`` 막힘 · ``held_note`` · ``tag`` · ``mine_row`` · ``first_card`` · ``picked_by_user_id``).
        손으로 체크한 파트의 장은 ``state`` 가 ``hand``(완료로 셈 — 파트 계정 '완료' 칸에는 안 셈, §4-2 '판 숫자').
    """
    order_id, key, part, me = int(row["id"]), entry["key"], ctx["part"], ctx["user_id"]
    snap = MarkSnapshot.from_row(marks.get((order_id, key, part)))
    extra = _card_state(row, key, snap, ctx)
    state = extra["state"]
    picked_by_me = extra["picked_by_me"]
    done_by_me = snap.done_by_user_id is not None and snap.done_by_user_id == me
    item_label, item_spec = card_item_text(row.get("structured_data") or {}, entry, row)
    finished = state in ("done", "basic")
    return {
        "order_id": order_id, "customer_name": row.get("customer_name") or "-", "has_changes": bool(row.get("has_changes")),
        # 시공일 표(home_date_macros.fph_due) — 행이 이미 가진 값 그대로(새 읽기 없음, 사용자 11-21 "아주 중요한 정보")
        "day_label": row.get("day_label") or "", "day_sub": row.get("day_sub") or "", "day_is_today": bool(row.get("day_is_today")),
        "key": key, "filename": entry.get("filename") or "", "view_url": entry.get("view_url") or "",
        "is_image": is_part_thumb_image(entry),
        "sheet_id": entry.get("sheet_id"), "order_pos": position[0], "no": position[1], "of": position[2],
        "item_label": item_label, "item_spec": item_spec,
        "picked_by_name": snap.picked_by_name, "done_by_name": snap.done_by_name,
        "picked_by_user_id": snap.picked_by_user_id, "done_by_me": done_by_me,
        "taken_by_other": state == "need" and not picked_by_me,
        "badge": _badge(state, ctx["mine"], picked_by_me),
        "in_need": state == "need" and (picked_by_me or not ctx["mine"]),
        "in_done": (finished and (done_by_me or not ctx["mine"])) or (state == "hand" and not ctx["mine"]),
        "others": _other_words(order_id, key, part, marks, ctx["hands"][order_id], ctx),
        "replaced": replaced_info(order_id, entry, ctx["current_keys"][order_id], ctx["by_sheet"], part),
        **extra,
    }


def sort_cards(cards: list[dict[str, Any]], part: str) -> list[dict[str, Any]]:
    """카드 순서 — 모든 파트 남은 일 앞 · 완료 뒤(설계서 2026-11-23 §8-1 '판 순서', :func:`sort_rank`), 묶음 안은 주문 · 장 번호 순.

    재단 · 엣지 · 조립 = 미정 → 담당 → 완료, 검수 = 검수 할 수 있음 → 담당 → 검수 전 → 완료. 주문 순서는 만들 것 줄 순서
    (``order_pos``) 그대로다.
    """
    return sorted(cards, key=lambda c: (sort_rank(c, part), c["order_pos"], c["no"]))


def card_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    """칸 숫자 — 전체 도면 · 작업 필요 · 완료 · 안 본(안 고른) 장. 캡과 무관하게 모든 카드에서 센다."""
    return {
        "all": len(cards),
        "need": sum(1 for c in cards if c["in_need"]),
        "done": sum(1 for c in cards if c["in_done"]),
        "unseen": sum(1 for c in cards if c["state"] == "none"),
    }


def bulk_count(cards: list[dict[str, Any]]) -> int:
    """[남은 N장 모두 기본] 숫자 — 막힌(보류 · 도면 고치는 중) 안 본 장은 빼고 센다. 창이 여는 목록과 같은 기준(parts.js bulkable)."""
    return sum(1 for c in cards if c["state"] == "none" and not c.get("order_block"))


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
        "bulk": bulk_count(cards),
        "orders_total": int(pane.get("total") or 0),
        "drawn_orders": len(pane.get("make_rows") or []) - len(no_drawing),
        "wait_rows": wait_rows,
        "no_drawing_rows": no_drawing,
        "wait_count": len(wait_rows) + len(no_drawing),
        "done_count": len(pane.get("done_rows") or []),
    }


def resolve_board_part(user: Any, requested: Any) -> tuple[str, Optional[str]]:
    """보기 모드와 볼 파트 — 파트 계정은 고른 파트가 내 파트일 때만 그 파트, 아니면 내 첫 파트(정의 순서, 2026-11-23 §4-12).
    관리자 · 대신 · 읽기 전용은 고른 파트(모르면 재단).

    Returns:
        ``(모드, 파트 key)`` — 볼 수 없는 사람은 ``("none", None)``.
    """
    mode = part_view_mode(user)
    if mode == VIEW_NONE:
        return mode, None
    text = str(requested or "").strip().lower()
    if mode == VIEW_PART:
        mine = part_account_parts(user)
        return mode, text if text in mine else mine[0]
    return mode, text if text in PRODUCTION_PART_KEYS else PART_CUT


def board_parts(mode: str, user: Any) -> list[dict[str, str]]:
    """판 머리에서 고를 파트 — 관리자 · 대신 · 읽기 전용 = 네 파트(지금 ``pp-parts``), 파트 계정 = 내 파트들(둘 이상일 때만 고르기)."""
    keys = part_account_parts(user) if mode == VIEW_PART else PRODUCTION_PART_KEYS
    return [{"key": key, "label": PRODUCTION_PART_LABELS[key]} for key in keys]


def _order_marks(marks: Iterable[Any]) -> dict[int, list[Any]]:
    out: dict[int, list[Any]] = {}
    for row in marks:
        out.setdefault(int(row.order_id), []).append(row)
    return out


def build_part_board(db: Any, user: Any, days: dict[str, Any], *, part: Any = None, marks: Optional[list[Any]] = None,
                     today: Optional[datetime.date] = None) -> Optional[dict[str, Any]]:
    """그날들(날짜 탭 ``panes`` 전부)의 파트 도면 카드 판. 쿼리는 표시 줄 읽기 한 번만 더한다.

    Args:
        db: 세션.
        user: 보는 사람.
        days: :func:`production_home_days` 결과(``panes`` 를 쓴다).
        part: 고른 파트(``?part=``). 관리자 · 대신 · 읽기 전용은 네 파트 중, 파트 계정은 내 파트일 때만(아니면 내 첫 파트).
        marks: 이미 읽은 그 주문들 표시 줄(넘기면 다시 읽지 않는다 — 칸 아래 이름과 같은 줄, 쿼리 0).
        today: KST 오늘(시험용, 없으면 지금) — "어제부터" 판정.

    Returns:
        ``{mode, part, part_label, parts, pick, url_part, writable, mine, cap, panes:{key: 장 판}}`` 또는 None(볼 수 없는 사람).
    """
    mode, board_part = resolve_board_part(user, part)
    if board_part is None:
        return None
    panes = list(days.get("panes") or [])
    rows = [row for pane in panes for row in (pane.get("make_rows") or [])]
    files = {int(row["id"]): resolve_final_drawing_files(row.get("structured_data") or {}) for row in rows}
    if marks is None:
        marks = fetch_part_marks(db, (oid for oid, entries in files.items() if entries))
    by_slot, by_sheet = index_marks(marks)
    order_marks = _order_marks(marks)
    writable = board_part in writable_parts(user)
    parts = board_parts(mode, user)
    pick = mode == VIEW_PART and len(parts) > 1
    ctx = {
        "part": board_part, "mine": mode == VIEW_PART, "writable": writable, "user_id": getattr(user, "id", None),
        "own_parts": own_parts(user),
        "files": files, "today": today or get_today_kst(), "order_marks": order_marks,
        "by_sheet": by_sheet, "current_keys": {oid: {e["key"] for e in entries} for oid, entries in files.items()},
        "blocks": {int(row["id"]): order_block(row) for row in rows},
        "hands": {int(row["id"]): {p: hand_cell(row.get("structured_data") or {}, order_marks.get(int(row["id"]), []), p)
                                   for p in PRODUCTION_PART_KEYS} for row in rows},
    }
    return {
        "mode": mode, "part": board_part, "part_label": PRODUCTION_PART_LABELS[board_part],
        # 고를 파트 · 여러 파트 고르기(파트 계정 둘 이상) · 주소에 실을 파트(파트 하나인 계정의 날짜 탭은 지금처럼 안 실음)
        "parts": parts, "pick": pick, "url_part": board_part if (mode != VIEW_PART or pick) else None,
        "writable": writable, "mine": ctx["mine"], "cap": PART_BOARD_CARD_CAP,
        "panes": {pane.get("key"): build_pane_board(pane, by_slot, ctx) for pane in panes},
    }
