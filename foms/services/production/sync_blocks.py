"""도면 카드 판의 주문 막힘 — 30초 받아 오기 · 제작 완료 뒤 카드 칸(비평 C06 · C09).

받아 오기(``GET /api/production/part-marks``)는 표시 줄과 같이 주문마다 **지금** 막힘을 싣고, 판 JS 는 카드를 이미 있는 막힌 칸으로
다시 그린다(그사이 보류 · 도면 고치는 중 · 제작 완료가 돼도 30초 안에 — 누르면 늘 거절되던 칸을 없앤다).

* 생산 단계 주문: 판이 그릴 때와 같은 :func:`~foms.services.production.part_card_state.order_block` — 보류 · 도면 고치는 중(주문 통째는
  ``all``, 생산 단계 도면별 막힘은 그 장만 ``keys``).
* 생산 단계가 아닌 주문(제작 완료 뒤 등 — 카드 쓰기는 모든 누름이 409 ``NOT_IN_PRODUCTION``): 단계 칸 하나(``all``) — 글 = 첫 화면 단계 글
  ("제작 완료" · "컨펌 기다림"), 까닭 = 그 거절 글 그대로. 생산 단계 판정은 카드 쓰기(``part_mark_write.check_order``)와 같은 함수.

계산은 순수(쿼리 0)이고, 받아 오기는 :func:`cached_blocks` 로 부른다(검토 고침 — 운영 생산 단계 53건 · 주문 JSON 평균 19KB · 최대 93KB 를
태블릿마다 30초마다 읽던 길을 뺀다). 캐시 = 프로세스 안 LRU(:data:`CACHE_SIZE` 칸), 열쇠 = (주문 id, ``mutation_version``, ``status``,
``erp_stage_code``) — 주문 쓰기 엔진(REV-00)이 버전을 올리면 열쇠가 바뀌어 그 주문만 다시 읽는다. 버전을 안 올리는 쓰기 길이 있어도
수명(:data:`CACHE_TTL_SECONDS`) 안에 맞춰진다. 평소 받아 오기 = 주문 JSON 0, 바뀐 주문만 한 번 더 읽는다.
gevent · 여러 프로세스: 캐시는 프로세스(워커)마다 따로이고 값은 같은 주문 JSON 의 순수 계산이라 어느 워커가 답해도 같다 — 칸 읽기 · 쓰기는
``threading.Lock``(gevent 는 몽키패치로 협조 잠금) 아래에서만 하고, 주문 읽기(I/O)는 잠금 밖에서 한다.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_fix import blocked
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.part_card_state import BLOCK_HOLD, order_block
from foms.services.production.part_mark_write import NOT_IN_PRODUCTION_MESSAGE
from foms.services.production_home_read_model import production_home_stage

#: 생산 단계가 아닌 주문의 막힘 코드 — 카드 쓰기 거절과 같은 코드(판 JS 는 이 코드면 모든 칸을 막는다).
NOT_IN_PRODUCTION = "NOT_IN_PRODUCTION"
#: 시공 단계(제작 완료) 칸은 완료 칸 색(``pp-st-done``), 그 밖 단계는 보류 칸 색.
_DONE_KIND = "done"
_PRODUCTION = "PRODUCTION"
_CONSTRUCTION = "CONSTRUCTION"
#: 제작 완료 칸을 눌렀을 때 글(사장님 2026-11-26).
DONE_WHY = "제작 완료된 주문이에요. 되돌리려면 작업 시트에서 [완료 취소]를 눌러 주세요."


def stage_block(stage: Optional[str]) -> dict[str, str]:
    """생산 단계가 아닌 주문의 카드 칸 — 글 = 첫 화면 단계 글(시공 단계 = "제작 완료").

    까닭 글: 시공 단계(제작 완료) = :data:`DONE_WHY`(사장님 2026-11-26 — 방금 완료한 사람에게 "생산 단계 주문이 아니에요"는 어색),
    그 밖 단계 = 카드 쓰기 거절 글 그대로. 서버 거절(409) 글은 안 바꾼다.
    """
    done = stage == _CONSTRUCTION
    return {"kind": _DONE_KIND if done else BLOCK_HOLD, "text": production_home_stage(stage, True, [], False)[0],
            "why": DONE_WHY if done else NOT_IN_PRODUCTION_MESSAGE, "code": NOT_IN_PRODUCTION}


#: 제작 완료(시공 단계) 칸 — 판 설정에 실어 제작 완료 성공 응답 때 판 JS 가 그 주문 카드에 그린다(C09).
DONE_BLOCK = stage_block(_CONSTRUCTION)


def _hold_on(sd: dict[str, Any]) -> bool:
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    hold = production.get("hold") if isinstance(production.get("hold"), dict) else {}
    return bool(hold.get("active"))


def order_sync_block(sd: Any, status: Any = None, flat_stage: Any = None) -> dict[str, Any]:
    """주문 하나의 지금 막힘 ``{all, keys}`` — ``all`` = 주문 통째 칸(없으면 None), ``keys`` = 그 장만 막힌 장 key → 칸.

    Args:
        sd: 주문 ``structured_data``.
        status: 주문 ``status``(단계 판정의 옛 값 — ``read_main_stage``).
        flat_stage: 주문 ``erp_stage_code``(단계를 못 읽는 옛 주문의 칸 글에만).
    """
    sd = sd if isinstance(sd, dict) else {}
    stage = read_main_stage(SimpleNamespace(structured_data=sd, status=status, is_erp_order=True))
    if stage != _PRODUCTION:
        return {"all": stage_block(stage or flat_stage), "keys": {}}
    row = {"hold_active": _hold_on(sd), "structured_data": sd}
    whole = order_block(row)
    if whole is not None:
        return {"all": whole, "keys": {}}
    fix = blocked(sd)
    keys = {}
    for entry in resolve_final_drawing_files(sd):
        block = order_block(row, entry, fix=fix)
        if block is not None:
            keys[entry["key"]] = block
    return {"all": None, "keys": keys}


#: 캐시 칸 수(LRU — 넘치면 가장 오래 안 쓴 것부터 버린다). 주문 한 칸이 1KB 안쪽이라 2,000칸 ≈ 2MB 안.
CACHE_SIZE = 2000
#: 캐시 수명(초) — 버전을 안 올리는 쓰기 길이 있어도 이 안에 맞춰진다.
CACHE_TTL_SECONDS = 300.0
_cache: "OrderedDict[tuple[Any, ...], tuple[dict[str, Any], float]]" = OrderedDict()
_lock = threading.Lock()
_clock = time.monotonic  # 시험이 바꿔 끼운다(수명 지남)


def _key(order_id: Any, head: tuple[Any, Any, Any]) -> tuple[Any, ...]:
    version, status, flat_stage = head
    return int(order_id), int(version or 0), status, flat_stage


def cached_blocks(heads: dict[int, tuple[Any, Any, Any]],
                  load: Callable[[list[int]], dict[int, Any]]) -> dict[str, dict[str, Any]]:
    """주문마다 지금 막힘 — 캐시에 있으면 그것, 없거나 수명이 지났으면 그 주문들만 ``load`` 로 주문 JSON 을 읽어 계산해 넣는다.

    Args:
        heads: 주문 id → (``mutation_version``, ``status``, ``erp_stage_code``) — 받아 오기 쿼리가 이미 읽은 값.
        load: 주문 id 목록 → ``{주문 id: structured_data}``(부르는 쪽의 쿼리 한 번 — 캐시가 다 맞으면 부르지 않는다).

    Returns:
        ``{주문 id 글: {all, keys}}``(:func:`order_sync_block` 값).
    """
    now = _clock()
    out: dict[str, dict[str, Any]] = {}
    missing: list[int] = []
    with _lock:
        for oid, head in heads.items():
            hit = _cache.get(_key(oid, head))
            if hit is not None and now - hit[1] < CACHE_TTL_SECONDS:
                _cache.move_to_end(_key(oid, head))
                out[str(oid)] = hit[0]
            else:
                missing.append(int(oid))
    if not missing:
        return out
    sds = load(missing)
    fresh = {oid: order_sync_block(sds.get(oid), heads[oid][1], heads[oid][2]) for oid in missing}
    with _lock:
        for oid, block in fresh.items():
            _cache[_key(oid, heads[oid])] = (block, now)
            _cache.move_to_end(_key(oid, heads[oid]))
            out[str(oid)] = block
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return out


def clear_sync_cache(order_ids: Optional[Iterable[int]] = None) -> None:
    """캐시를 비운다(``order_ids`` 를 주면 그 주문 칸만) — 시험이 시험마다 부른다(주문 번호가 시험마다 다시 쓰인다)."""
    with _lock:
        if order_ids is None:
            _cache.clear()
            return
        drop = {int(i) for i in order_ids}
        for key in [k for k in _cache if k[0] in drop]:
            del _cache[key]


__all__ = ["CACHE_SIZE", "CACHE_TTL_SECONDS", "DONE_BLOCK", "DONE_WHY", "NOT_IN_PRODUCTION", "cached_blocks", "clear_sync_cache",
           "order_sync_block", "stage_block"]
