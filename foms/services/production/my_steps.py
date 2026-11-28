"""'내 공정' 탭(``?tab=mine``) 읽기 모델 — 파트 계정이 날짜 탭에서 담은 도면 카드 + 오늘 끝낸 카드(설계서
2026-11-28-production-my-steps-flow §3-4 · 사장님 답 3 · 9 · 24 · 29).

* 담는 것: 내 몫이 작업 중인 카드 전부(시공일과 무관 · 같이 작업 포함 — 판 카드 ``mine_row`` 그대로) + **오늘(KST) 내가 끝낸** 카드
  (내 몫 완료 — 같이 작업한 장의 "재단 1/2 완료"도, 반장이 대신 완료한 내 몫도). [기본] · [조립 없음] · 손 체크는 끝낸 것에 안 든다.
* 묶음: 시공일 날짜(판정 기준 출고일 — 가까운 날 먼저, 지난 날이 맨 위, 출고일 없음 맨 뒤) → 그 안에 주문. 묶음 제목은 날짜 탭 장
  제목과 같은 함수(:func:`~foms.services.production_home_read_model.production_home_day`). 여러 파트 계정은 파트를 섞는다(장 번호 · 파트 순).
* 왼쪽 띠: 날짜 탭 띠와 같은 줄(지난 7일 · 날 줄 · 그 뒤) 앞에 '전체 · 모든 날' 한 줄. 줄 숫자 = 그 줄에 드는 내 카드 중 안 끝낸 장.
  카드마다 ``day_key``(그 카드가 선 띠 줄 — 띠 밖 지난 출고일 · 출고일 없음은 빈 글, '전체'에서만 보인다) — 거르기는 화면이 한다.
* 카드 = :func:`~foms.services.production.part_board.build_card` 그 dict + ``part`` · ``part_label`` · ``day_key``. 안 끝낸 카드 200장 캡.
* 남의 공장 장(2공장)은 안 든다 — 날짜 탭 판 뒤 묶음(누름 없음)에 지금처럼 남는다.
* 제작 완료(시공 대기)로 넘어간 주문(:func:`finished_rows`)도 오늘 내가 끝낸 장은 '오늘 끝낸 것'에 KST 자정까지 남는다(사장님 2026-11-28
  "제작 완료돼도 남김") — 같은 카드 · 같은 ``day_key``, 담아 놓은 것 · 띠 숫자에는 안 든다. 도면이 0장이면 '도면 없음' 카드(``@order``).

쿼리 0 — 표시 줄 · 판 맥락은 부르는 쪽(:mod:`foms.web.production.home_flow`)이 만들어 넘긴다.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from foms.services.production import mark_crew as mc
from foms.services.production import part_board as pb
from foms.services.production.order_card import order_entry
from foms.services.production.part_access import part_account_parts
from foms.services.production.part_board_ctx import factory_files, for_part
from foms.services.production.part_constants import MARK_STATE_DONE, PRODUCTION_PART_KEYS, PRODUCTION_PART_LABELS
from foms.services.production.part_holders import kst_day
from foms.services.production.ship_dates import PANE_NONE, PANE_PAST, pane_slots, row_due
from foms.services.production_home_read_model import NO_SHIP_LABEL, production_home_day

#: 왼쪽 띠 맨 위 줄 열쇠 · 글(사장님 답 29 "'전체' 줄을 둠").
STRIP_ALL = "all"
STRIP_ALL_LABEL = "전체"
STRIP_ALL_SUB = "모든 날"
#: 출고일이 없는 묶음 열쇠(날짜 탭 장 열쇠와 같은 값).
NO_DAY_KEY = PANE_NONE
#: 제작 완료(시공 대기) 줄의 보기 키(첫 화면 행 ``home_view`` — ``production_home_stage``).
FINISHED_VIEW = "done"


def finished_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """제작 완료로 넘어간 첫 화면 행(시공 대기) — 오늘 끝낸 장만 '오늘 끝낸 것'에 남긴다(카드는 생산 단계 행에서만 담는다)."""
    return [row for row in rows if row.get("home_view") == FINISHED_VIEW]


def strip_key(row: dict[str, Any], today: datetime.date) -> str:
    """카드가 서는 띠 줄 열쇠 — 날짜 탭에서 그 주문이 선 첫 장(:func:`~foms.services.production.ship_dates.pane_slots`).
    띠 밖(지난 출고일 · 출고일 없음)은 빈 글."""
    key = pane_slots(row, today)[0][0]
    return "" if key in (PANE_PAST, PANE_NONE) else key


def _done_at(mark: Any, user_id: Any) -> Optional[datetime.datetime]:
    """그 장 · 그 파트에서 내 몫을 완료한 때(UTC naive) — 작업하는 사람 목록의 내 칸, 목록이 없는 옛 완료 줄은 줄의 완료 칸.
    내 몫이 아직이거나 내 것이 아니거나 기본 · 조립 없음이면 None."""
    people = mc.crew_of(mark)
    item = mc.find(people, user_id)
    if item is not None:
        return mc.from_iso(item.get("done_at")) if mc.is_done(item) else None
    if not people and str(mark.state or "") == MARK_STATE_DONE and user_id is not None and mark.done_by_user_id == user_id:
        return getattr(mark, "done_at", None) or getattr(mark, "updated_at", None)
    return None


def _sorted_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """묶음 순서 — 판정 기준 출고일 빠른 순(지난 날이 맨 위) · 출고일 없음 맨 뒤 · 같은 날은 주문 번호 순."""
    def key(row: dict[str, Any]) -> tuple[int, datetime.date, int]:
        day = row_due(row)
        return (0, day, int(row["id"])) if day else (1, datetime.date.min, int(row["id"]))
    return sorted(rows, key=key)


def _tag(card: dict[str, Any], part: str, day_key: str) -> dict[str, Any]:
    card.update(part=part, part_label=PRODUCTION_PART_LABELS[part], day_key=day_key)
    return card


def _group_head(row: dict[str, Any], today: datetime.date) -> tuple[str, str]:
    """(묶음 열쇠, 제목) — 'YYYY-MM-DD' · "12/1 (화)"(오늘 · 내일은 앞말 붙음 — 날짜 탭 장 제목과 같다), 출고일 없음은 ('none', '출고일 없음')."""
    day = row_due(row)
    if day is None:
        return NO_DAY_KEY, NO_SHIP_LABEL
    return day.isoformat(), production_home_day(day, today)["label"]


def group_days(cards: list[dict[str, Any]], heads: dict[int, tuple[str, str]]) -> list[dict[str, Any]]:
    """정렬된 카드 → 날짜 묶음 ``[{key, title, day_key, count, orders: [{id, name, count, cards}]}]``(이어진 같은 날 · 같은 주문을 묶는다)."""
    days: list[dict[str, Any]] = []
    for card in cards:
        key, title = heads[int(card["order_id"])]
        if not days or days[-1]["key"] != key:
            days.append({"key": key, "title": title, "day_key": card["day_key"], "count": 0, "orders": []})
        orders = days[-1]["orders"]
        if not orders or orders[-1]["id"] != card["order_id"]:
            orders.append({"id": card["order_id"], "name": card["customer_name"], "count": 0, "cards": []})
        orders[-1]["cards"].append(card)
        orders[-1]["count"] += 1
        days[-1]["count"] += 1
    return days


def build_my_steps(user: Any, rows: list[dict[str, Any]], ctx: dict[str, Any], strip: list[dict[str, Any]], *,
                   today: datetime.date, cap: Optional[int] = None,
                   finished: Iterable[dict[str, Any]] = ()) -> Optional[dict[str, Any]]:
    """'내 공정' 탭 재료.

    Args:
        user: 보는 사람(파트 계정 — 아니면 None 을 돌려준다).
        rows: 카드를 만들 줄(:func:`~foms.services.production.part_board_ctx.card_rows`).
        ctx: 판 맥락(:func:`~foms.services.production.part_board_ctx.board_ctx`, 모드 = 파트 계정) — ``rows`` + ``finished`` 로 만든 것.
        strip: 날짜 탭 띠 줄(:func:`~foms.services.production_home_days.production_home_days` 의 ``strip``).
        today: KST 오늘 — 띠 줄 · '오늘 끝낸 것' 판정.
        cap: 안 끝낸 카드 상한(없으면 판과 같은 :data:`~part_board.PART_BOARD_CARD_CAP`).
        finished: 제작 완료로 넘어간 줄(:func:`finished_rows`) — 오늘 내가 끝낸 장만 ``done`` 에 든다(담아 놓은 것 · 띠 숫자 밖).
            도면이 0장이면 '도면 없음' 카드 한 장(``@order``)으로 본다(생산 단계 행만 받는 ``row_files`` 대신).

    Returns:
        ``{strip: [{key, label, sub, count}], days: [{key, title, day_key, count, orders: [{id, name, count, cards}]}],
        done: [카드], hidden, done_hidden}`` — ``strip[0]`` = ``{key: 'all', label: '전체', sub: '모든 날', count: 전체 장수}``,
        ``done`` = 늦게 끝낸 것부터, ``hidden`` = 캡에 밀린 안 끝낸 장 수, ``done_hidden`` = 캡에 밀린 끝낸 장 수.
    """
    parts = [p for p in PRODUCTION_PART_KEYS if p in part_account_parts(user)]
    if not parts:
        return None
    cap = pb.PART_BOARD_CARD_CAP if cap is None else cap
    uid = getattr(user, "id", None)
    slots = ctx["slots"]
    part_ctx = {part: for_part(ctx, user, part) for part in parts}
    active: list[dict[str, Any]] = []
    done: list[tuple[datetime.datetime, dict[str, Any]]] = []
    heads: dict[int, tuple[str, str]] = {}
    lines = [*((row, False) for row in _sorted_rows(rows)), *((row, True) for row in _sorted_rows(finished))]
    for pos, (row, gone) in enumerate(lines):
        oid = int(row["id"])
        files = ctx["files"].get(oid) or ([order_entry()] if gone else [])  # 제작 완료 0장 줄 = '도면 없음' 카드(@order 줄이 있을 때만 선다)
        day_key = strip_key(row, today)
        for no, entry in factory_files(row, files, factory=ctx["factory"], scene=ctx["scene"]):
            for part in parts:
                mark = slots.get((oid, str(entry["key"]), part))
                if mark is None:
                    continue
                held = mc.share_of(mc.crew_of(mark), uid) == mc.SHARE_HELD and not gone  # 제작 완료 줄은 담아 놓은 것이 없다
                when = _done_at(mark, uid) if not held else None
                if not held and (when is None or kst_day(when) != today):
                    continue  # 내 것도 아니고 오늘 끝낸 것도 아님 — 카드를 안 만든다(쿼리 0 · 계산만 아낀다)
                card = _tag(pb.build_card(row, entry, (pos, no, len(files)), slots, part_ctx[part]), part, day_key)
                heads.setdefault(oid, _group_head(row, today))
                if card["mine_row"] and not gone:
                    active.append(card)
                elif when is not None and card["done_by_me"] and card["state"] in ("done", "need"):
                    done.append((when, card))
    done.sort(key=lambda item: (item[0], -int(item[1]["order_id"]), -int(item[1]["no"])), reverse=True)
    shown = active[:cap]
    line = [{"key": STRIP_ALL, "label": STRIP_ALL_LABEL, "sub": STRIP_ALL_SUB, "count": len(active)}]
    line += [{"key": d["key"], "label": d["label"], "sub": d["sub"], "count": sum(1 for c in active if c["day_key"] == d["key"])}
             for d in strip]
    return {"strip": line, "days": group_days(shown, heads), "done": [card for _when, card in done[:cap]],
            "hidden": len(active) - len(shown), "done_hidden": max(0, len(done) - cap)}


__all__ = ["FINISHED_VIEW", "NO_DAY_KEY", "STRIP_ALL", "build_my_steps", "finished_rows", "group_days", "strip_key"]
