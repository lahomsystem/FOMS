"""생산 파트 도면 카드 읽기 모델 — 설계서 §15.6 '오른쪽 장' · D48 · D56 · D57(P15-3, 라우트에는 아직 잇지 않는다).

입력은 지금 날짜 탭이 이미 만든 날짜 묶음(:func:`foms.services.production_home_days.production_home_days` 의 ``panes``)
이다 — 그날 생산 단계 주문 묶음(``make_rows`` · 만들 것 줄 순서)과 '도면·컨펌 기다림'(``wait_rows``) · 제작 완료
(``done_rows``)를 그대로 다시 쓴다. 여기서 더하는 쿼리는 표시 줄 읽기 **한 번**(``order_id IN (그날들 생산 주문)``)뿐이고
카드 수와 무관하다.

* 카드 = 확정 도면 한 장(:func:`resolve_final_drawing_files` 의 항목, 순서 = 도면 번호).
* 내 파트 상태 · 작업하는/완료한 사람 이름 줄(여러 명 — 2026-11-25 multi-holder, :mod:`part_card_crew`) · 다른 파트 한 줄 낱말
  (재단: 완료 · 기본 · 중 · 안 봄, 그 밖: 완료 · 중 · 아직).
* 칸 숫자: 파트 계정 = 내 것(작업 필요 = 내 몫이 작업 중인 장, 완료 = 내 몫을 완료한 장 — "재단 1/2 완료"도, 재단은 + 기본),
  관리자 · 대신 · 읽기 전용 = 그 파트 전체. 재단의 '안 본 장' 수도 센다. 숫자는 늘 읽은 줄 전부에서 센다(캡과 무관).
* 여러 파트 계정(2026-11-23 §4-12, P2): 판 머리에서 내 파트 사이를 고른다(``pick`` · 주소 ``?part=``), 다른 파트 한 줄에서
  내 파트이고 내 몫이 작업 중인 장은 "내 작업". 파트 하나인 계정은 고르기 없이 지금 그대로.
* 바뀐 도면(D56): 같은 ``sheet_id`` 의 옛 key 줄이 있으면 짝을 짓는다. 시트 신원이 없는 직접 올린 파일은 짝이 없다.
* 한 장 카드 200장 캡 — 넘친 수를 함께 돌려준다(조용히 자르지 않는다).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_confirm_partial import file_item_uids, item_ref
from foms.services.orders.drawing_factory import sheet_factory
from foms.services.orders.drawing_fix import blocked, file_successor
from foms.services.orders.drawing_fix_requests import board_request_options, can_request_people
from foms.services.production.part_access import (
    VIEW_ADMIN,
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
from foms.services.production import mark_crew as mc
from foms.services.production.factory_scope import board_factory, elsewhere_head, elsewhere_info, other_factories, scene_on
from foms.services.production.part_card_crew import card_crew
from foms.services.production.part_card_state import claim_notes, hand_cell, inspect_block, order_block, sort_rank
from foms.services.production.part_mark_notes import actor_name
from foms.services.production.part_mark_rules import MarkSnapshot, mark_payload
from foms.services.production.change_tag import change_tag
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

#: 다른 파트 한 줄 낱말(D51 — 색은 ``tone`` 으로 화면이 고른다). '끝' → '완료'(2026-11-25 multi-holder K4).
_CUT_WORDS = {"done": "완료", "basic": "기본", "need": "작업 중", "none": "미정"}
_OTHER_WORDS = {"done": "완료", "need": "작업 중", "none": "미정"}
#: 여러 파트 계정(2026-11-23 §4-12 '더함')의 다른 파트 한 줄 — 그 파트도 내 파트이고 내 몫이 작업 중인 장은 "엣지 내 작업"
#: (multi-holder §8-2 10). 파트 하나인 계정 · 관리자 · 대신에게는 생기지 않는다(다른 파트가 내 파트가 아니다).
MINE_TONE = "mine"
MINE_WORD = "내 작업"

MarkIndex = dict[tuple[int, str, str], Any]
SheetIndex = dict[tuple[int, str], list[Any]]


def other_part_word(part: str, state_key: str, mine: bool = False) -> dict[str, str]:
    """다른 파트 한 줄의 낱말 하나.

    Args:
        part: 파트 key.
        state_key: none · need · basic · done.
        mine: 그 파트가 보는 사람의 파트이고 담당이 보는 사람인지(여러 파트 계정만 — :func:`mine_other` ).

    Returns:
        ``{part, label, word, tone}`` — 재단은 완료 · 기본 · 작업 중 · 미정, 그 밖은 완료 · 작업 중 · 미정(D57: 안 고름 = 미정).
        ``mine`` 이고 작업 필요(need)이면 "내 작업"(tone ``mine``).
    """
    if mine and state_key == "need":
        return {"part": part, "label": PRODUCTION_PART_LABELS[part], "word": MINE_WORD, "tone": MINE_TONE}
    words = _CUT_WORDS if part == PART_CUT else _OTHER_WORDS
    tone = state_key if state_key in words else "none"
    return {"part": part, "label": PRODUCTION_PART_LABELS[part], "word": words[tone], "tone": tone}


def mine_other(row: Any, part: str, viewer_id: Any, viewer_parts: tuple[str, ...]) -> bool:
    """다른 파트 한 줄에서 "내 작업"으로 적을지 — 그 파트가 보는 사람의 파트이고 보는 사람 몫이 작업 중(작업하는 사람 목록).

    Args:
        row: 그 파트 표시 줄(없으면 None).
        part: 파트 key.
        viewer_id: 보는 사람 id.
        viewer_parts: 보는 사람의 파트들(:func:`~foms.services.production.part_access.own_parts`).

    Returns:
        셋이 맞으면 True(상태는 :func:`other_part_word` 가 본다).
    """
    return (part in viewer_parts and row is not None and viewer_id is not None
            and mc.share_of(mc.crew_of(row), viewer_id) == mc.SHARE_HELD)


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
        ``({(order_id, key, part): 줄}, {(order_id, sheet_id): [줄…]})`` — 둘째는 시트 신원이 있는 줄 + 모든 줄을 ``file:<key>``
        자리에도(파일 도면 이어받기 짝 — 설계서 2026-11-25 §3-5, 시트 id 에는 ``:`` 가 없어 겹치지 않는다).
    """
    by_slot: MarkIndex = {}
    by_sheet: SheetIndex = {}
    for row in marks:
        by_slot[(int(row.order_id), str(row.drawing_key), str(row.part))] = row
        by_sheet.setdefault((int(row.order_id), f"file:{row.drawing_key}"), []).append(row)
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


def _prev_name(snap: MarkSnapshot) -> str:
    """옛 판 줄의 이름 칸 글(목록에서 — 둘까지 + "외 n", 칸 글이라 '명' 없음): 완료 = 완료한 사람, 그 밖 = 작업하는 사람, 사람 없는 줄 = 한 명짜리 칸."""
    done = mc.done_names(snap.crew) if snap.seen_key == "done" else []
    return mc.name_line(done or mc.names(snap.crew)) or (snap.done_by_name or snap.picked_by_name or "").strip()


def _prev_word(row: Any) -> str:
    """옛 판 표시 한 줄의 낱말 — '재단 완료(김재단)' · '기본(박재단)' · '재단 중(이시영 · 김재단 외 1)'(칸 글 — multi-holder Q17 · Q20)."""
    label = PRODUCTION_PART_LABELS.get(str(row.part), "")
    snap = MarkSnapshot.from_row(row)
    if snap.seen_key == "done":
        return f"{label} 완료({_prev_name(snap) or '-'})"
    if snap.seen_key == "basic":
        return f"기본({row.done_by_name or '-'})"
    return f"{label} 중({_prev_name(snap) or '-'})"


def replaced_info(order_id: int, entry: dict[str, Any], current_keys: set[str], by_sheet: SheetIndex,
                  part: str, successor: str = "") -> Optional[dict[str, Any]]:
    """바뀐 도면 짝(D56) — 같은 시트 신원의 옛 key 줄이 있으면 전 판 진행을 붙인다.

    Args:
        order_id: 주문 id.
        entry: 지금 확정 도면 항목(``sheet_id`` 가 없으면 ``successor`` 로만 짝 — 직접 올린 파일).
        current_keys: 그 주문 지금 확정 도면 key 집합.
        by_sheet: :func:`index_marks` 의 시트 신원 사전.
        part: 보고 있는 파트.
        successor: 파일 도면이 이어받은 옛 key(``drawing_fix.file_successor`` — 설계서 2026-11-25 §3-5, 없으면 빈 글).

    Returns:
        ``{label, prev:{part:{state, name}}}`` 또는 None. ``label`` 은 보는 파트의 전 판 진행(없으면 '바뀐 도면').
    """
    slot = str(entry.get("sheet_id") or "") or (f"file:{successor}" if successor else "")
    if not slot:
        return None
    old = [r for r in by_sheet.get((order_id, slot), []) if str(r.drawing_key) not in current_keys]
    if not old:
        return None
    latest: dict[str, Any] = {}
    # 같은 시각(일괄 기본 한 번 · 거친 시계 눈금)이면 id 큰 줄이 나중 — 표시 줄 쿼리는 ORDER BY 가 없어 줄 차례에 기대면 흔들린다.
    for row in sorted(old, key=lambda r: (r.updated_at is not None, r.updated_at, getattr(r, "id", None) or 0)):
        if row.state != MARK_STATE_NONE:
            latest[str(row.part)] = row
    snaps = {key: MarkSnapshot.from_row(r) for key, r in latest.items()}
    prev = {key: {"state": s.seen_key, "name": _prev_name(s) or None} for key, s in snaps.items()}
    mine = latest.get(part)
    label = f"바뀐 도면 · 전 판 {_prev_word(mine)}" if mine is not None else "바뀐 도면"
    return {"label": label, "prev": prev}


def _other_words(order_id: int, key: str, part: str, marks: MarkIndex, hands: dict[str, Any],
                 ctx: dict[str, Any]) -> list[dict[str, str]]:
    """다른 파트 한 줄 — 표시 줄 낱말. 손으로 체크한 파트(카드 안 씀)는 그 파트 모든 장이 완료라 '완료'(B5′).
    여러 파트 계정이 그 파트도 작업 중이면 "내 작업"(§4-12)."""
    words = []
    for other in PRODUCTION_PART_KEYS:
        if other == part:
            continue
        row = marks.get((order_id, key, other))
        state = "done" if hands.get(other) else MarkSnapshot.from_row(row).seen_key
        words.append(other_part_word(other, state, mine_other(row, other, ctx["user_id"], ctx["own_parts"])))
    return words


def _card_state(row: dict[str, Any], entry: dict[str, Any], snap: MarkSnapshot, ctx: dict[str, Any]) -> dict[str, Any]:
    """3판 칸 — 손 체크 · 막힘 · 밤 넘김 · 바뀐 기록 · 내 작업 꼬리 · 첫 카드(§4-6 · §4-8 · §4-9 · §4-11) + 작업하는 사람 칸
    (내 몫 · 칸 소속 · 배지 — :func:`~foms.services.production.part_card_crew.card_crew`, multi-holder §8).

    막힘은 그 장 단위(2026-11-25 설계서 §3-3) — 주문 통째(보류 · 도면 고치는 중)는 모든 장, 도면별 막힘은 그 장만(같은 모양 · 같은 글).
    """
    order_id, part, key = int(row["id"]), ctx["part"], entry["key"]
    sd = row.get("structured_data") or {}
    marks = ctx["order_marks"].get(order_id, [])
    hands = ctx["hands"][order_id]
    hand = hands.get(part)
    state = "hand" if hand else snap.seen_key
    crew = card_crew(snap, state, ctx)
    picked_by_me = crew["picked_by_me"]
    card_block = ctx["blocks"][order_id] or order_block(row, entry, fix=ctx["fix"][order_id])  # 쿼리 0(이미 든 주문 JSON)
    block = None
    if state in ("none", "need"):
        block = card_block or (inspect_block(sd, marks, key) if part == PART_INSPECT else None)
    # 주문 막힘(보류 · 도면 고치는 중)은 상태와 상관없이 카드에 싣는다 — 완료 · 기본 카드를 되돌린 뒤 JS 가 그리는 칸이
    # 서버가 그리는 칸(막힌 칸 · [시작 취소][막힌 칸])과 같게(검수 전 막힘은 JS 가 다른 파트 줄로 다시 본다)
    notes = claim_notes(snap, ctx["today"], mine=picked_by_me and ctx["writable"], crew_tag=(crew["crew"] or {}).get("tag", ""))
    mark = mark_payload(snap) if snap.seen_key != "none" else {}
    notes.update(picked_day=mark.get("picked_day"), picked_at=mark.get("picked_at"), handed_from_name=snap.handed_from_name,
                 handed_at=mark.get("handed_at"))
    return {"state": state, "hand": hand, "block": block, "order_block": card_block, **crew,
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
        ctx: ``{part, mine, writable, user_id, today, by_sheet, current_keys, order_marks, hands, blocks, fix}``.

    Returns:
        카드 dict(주문 · 장 key · 도면 n/N · 품목 · 내 파트 상태 · 이름 · 배지 · 칸 소속 · 다른 파트 · 바뀐 도면) + 3판 칸
        (``hand`` 손 체크 · ``block`` 막힘 · ``held_note`` · ``tag`` · ``mine_row`` · ``first_card`` · ``picked_by_user_id``) +
        작업하는 사람 칸(``crew`` — 이름 줄 · 내 몫, :func:`~foms.services.production.part_card_crew.card_crew`).
        손으로 체크한 파트의 장은 ``state`` 가 ``hand``(완료로 셈 — 파트 계정 '완료' 칸에는 안 셈, §4-2 '판 숫자').
    """
    order_id, key, part = int(row["id"]), entry["key"], ctx["part"]
    snap = MarkSnapshot.from_row(marks.get((order_id, key, part)))
    extra = _card_state(row, entry, snap, ctx)
    item_label, item_spec = card_item_text(row.get("structured_data") or {}, entry, row)
    return {
        "order_id": order_id, "customer_name": row.get("customer_name") or "-", "has_changes": bool(row.get("has_changes")), "chg_text": change_tag(row.get("home_alerts")),
        # 시공일 표(home_date_macros.fph_due) — 행이 이미 가진 값 그대로(새 읽기 없음, 사용자 11-21 "아주 중요한 정보")
        "day_label": row.get("day_label") or "", "day_sub": row.get("day_sub") or "", "day_is_today": bool(row.get("day_is_today")),
        "ship_mark": row.get("ship_mark"),  # 상차 · 희망일 표(사장님 2026-11-25) — 시공일 표 옆
        "key": key, "filename": entry.get("filename") or "", "view_url": entry.get("view_url") or "",
        "is_image": is_part_thumb_image(entry),
        "sheet_id": entry.get("sheet_id"), "order_pos": position[0], "no": position[1], "of": position[2],
        "item_label": item_label, "item_spec": item_spec,
        "picked_by_name": snap.picked_by_name, "done_by_name": snap.done_by_name, "picked_by_user_id": snap.picked_by_user_id,
        "others": _other_words(order_id, key, part, marks, ctx["hands"][order_id], ctx),
        "replaced": replaced_info(order_id, entry, ctx["current_keys"][order_id], ctx["by_sheet"], part,
                                  file_successor(row.get("structured_data")).get(key, "")),
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
        "unseen": bulk_count(cards),  # '안 본 도면 N장' = [남은 N장 모두 기본] 숫자(막힌 장 뺌, 사장님 2026-11-26)
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
    elsewhere: list[dict[str, Any]] = []
    no_drawing: list[dict[str, Any]] = []
    # 2공장(§4-13): 남의 공장 장만 있는 줄(elsewhere_rows)도 카드로 — 남의 공장 카드는 판 뒤 묶음(누름 없음 · 숫자 밖)
    for order_pos, row in enumerate([*(pane.get("make_rows") or []), *(pane.get("elsewhere_rows") or [])]):
        files = ctx["files"][int(row["id"])]
        if not files:
            no_drawing.append(row)  # 생산 단계인데 확정 도면 0장 — '도면 없음' 으로 기다림 묶음에
            continue
        sd = row.get("structured_data") or {}
        for index, entry in enumerate(files):
            card = build_card(row, entry, (order_pos, index + 1, len(files)), marks, ctx)
            factory = sheet_factory(sd, entry) if ctx["scene"] else ctx["factory"]
            if factory != ctx["factory"]:  # 남의 공장 글 이름 = 작업하는 사람 목록(이미 읽은 줄 — multi-holder Q20)
                card["elsewhere"] = elsewhere_info(card, ctx["part"], factory, marks.get((int(row["id"]), entry["key"], ctx["part"])))
                elsewhere.append(card)
            else:
                cards.append(card)
    cards = sort_cards(cards, ctx["part"])
    elsewhere = sorted(elsewhere, key=lambda c: (c["order_pos"], c["no"]))
    wait_rows = list(pane.get("wait_rows") or [])
    return {
        "key": pane.get("key"),
        "cards": cards[:PART_BOARD_CARD_CAP],
        "hidden": max(0, len(cards) - PART_BOARD_CARD_CAP),
        "counts": card_counts(cards),
        "bulk": bulk_count(cards),
        "elsewhere": elsewhere[:PART_BOARD_CARD_CAP],
        "elsewhere_head": elsewhere_head(other_factories(ctx["factory"])[0], len(elsewhere)) if elsewhere else "",
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
                     today: Optional[datetime.date] = None, factory: Any = None) -> Optional[dict[str, Any]]:
    """그날들(날짜 탭 ``panes`` 전부)의 파트 도면 카드 판. 쿼리는 표시 줄 읽기 한 번만 더한다.

    Args:
        db: 세션.
        user: 보는 사람.
        days: :func:`production_home_days` 결과(``panes`` 를 쓴다).
        part: 고른 파트(``?part=``). 관리자 · 대신 · 읽기 전용은 네 파트 중, 파트 계정은 내 파트일 때만(아니면 내 첫 파트).
        marks: 이미 읽은 그 주문들 표시 줄(넘기면 다시 읽지 않는다 — 칸 아래 이름과 같은 줄, 쿼리 0).
        today: KST 오늘(시험용, 없으면 지금) — "어제부터" 판정.
        factory: 관리자가 고른 공장(``?factory=``, 3단계) — 그 밖 사람은 계정 공장.

    Returns:
        ``{mode, part, part_label, parts, pick, url_part, writable, mine, cap, factory, scene, factory_pick, url_factory,
        panes:{key: 장 판}}`` 또는 None(볼 수 없는 사람). 2공장 그림이 켜지면 장 판마다 ``elsewhere``(남의 공장 카드) ·
        ``elsewhere_head`` 가 차고, 칸 숫자는 내 공장 카드만 센다.
    """
    mode, board_part = resolve_board_part(user, part)
    if board_part is None:
        return None
    panes = list(days.get("panes") or [])
    rows = [row for pane in panes for row in [*(pane.get("make_rows") or []), *(pane.get("elsewhere_rows") or [])]]
    files = {int(row["id"]): resolve_final_drawing_files(row.get("structured_data") or {}) for row in rows}
    if marks is None:
        marks = fetch_part_marks(db, (oid for oid, entries in files.items() if entries))
    by_slot, by_sheet = index_marks(marks)
    order_marks = _order_marks(marks)
    factory = board_factory(user, factory)
    scene = scene_on((r.get("structured_data") or {} for r in days.get("all_rows") or rows), factory)
    writable = board_part in writable_parts(user)
    parts = board_parts(mode, user)
    pick = mode == VIEW_PART and len(parts) > 1
    ctx = {
        "part": board_part, "mine": mode == VIEW_PART, "writable": writable, "user_id": getattr(user, "id", None),
        "viewer_name": actor_name(user), "factory": factory, "scene": scene,
        "own_parts": own_parts(user),
        "files": files, "today": today or get_today_kst(), "order_marks": order_marks,
        "by_sheet": by_sheet, "current_keys": {oid: {e["key"] for e in entries} for oid, entries in files.items()},
        "blocks": {int(row["id"]): order_block(row) for row in rows},  # 주문 통째(보류 · 도면 고치는 중)
        "fix": {int(row["id"]): blocked(row.get("structured_data") or {}) for row in rows},  # 도면별 막힘(2026-11-25 §3-3, 쿼리 0)
        "req": board_request_options(user, rows),  # [도면 수정 요청] 창 고르기(2026-11-25 §2-4 · N3 — 생산 단계 주문, 쿼리 0)
        "hands": {int(row["id"]): {p: hand_cell(row.get("structured_data") or {}, order_marks.get(int(row["id"]), []), p)
                                   for p in PRODUCTION_PART_KEYS} for row in rows},
    }
    return {
        "mode": mode, "part": board_part, "part_label": PRODUCTION_PART_LABELS[board_part],
        # 고를 파트 · 여러 파트 고르기(파트 계정 둘 이상) · 주소에 실을 파트(파트 하나인 계정의 날짜 탭은 지금처럼 안 실음)
        "parts": parts, "pick": pick, "url_part": board_part if (mode != VIEW_PART or pick) else None,
        "writable": writable, "mine": ctx["mine"], "cap": PART_BOARD_CARD_CAP,
        # 2공장(§4-13 · §19 열한째): 보는 공장 · 관리자 판 머리 공장 고르기(2공장 그림이 켜졌을 때만) · 주소에 실을 공장
        "factory": factory, "scene": scene, "factory_pick": scene and mode == VIEW_ADMIN, "req_opts": ctx["req"],
        "can_request": can_request_people(user),  # [도면 수정 요청] 창을 둘 사람(관리자 · 반장 · 파트 계정 — 날 조각 판도 같은 창)
        "url_factory": factory if scene and mode == VIEW_ADMIN else None,
        "panes": {pane.get("key"): build_pane_board(pane, by_slot, ctx) for pane in panes},
    }
