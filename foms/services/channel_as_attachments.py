"""AS PUSH 첨부 선정 (AS-FRESH-01 T6).

AS PUSH 는 한 주문의 ``category='as'`` 첨부를 **전량** 실어 보냈다. 그래서 3개월 전 1차
AS 사진과 방금 올린 사진이 한 메시지에 섞였고(혼입), 상한 20장을 오래된 것부터 채우는
정렬이라 첨부가 21장을 넘는 순간 **방금 올린 사진이 아예 빠졌다**(최신 탈락).

여기서 "이번 건의 최신 첨부"를 결정한다. 판정 순서는 3단이며 위에서부터 적중하면 멈춘다:

1. **현재 회차** — 첨부가 ``as_log_id`` 로 기록에 결합돼 있고 그 기록이 현재 회차 소속.
   (결합 컬럼은 AS-FRESH-01 T1 에서 들어온다. 그 전에는 이 단이 항상 비어 2단으로 내려간다.)
2. **미발송분** — 마지막 PUSH 에 실린 첨부 id 최대값보다 큰 id. 첨부 id 는 단조 증가라
   "그 뒤에 올라온 것"과 동치다.
3. **최신 N장** — 위 둘이 다 비면(구주문 최초 PUSH) 최신부터 상한만큼.

**시각(created_at) 비교를 쓰지 않는다.** ``OrderAttachment.created_at`` default 는
``datetime.datetime.now``(naive **local**)이고 push ``sent_at`` 은 UTC ISO 다. 두 값을 비교하면
로컬 dev 에서 9시간 skew 가 난다. 델타 판정은 **id 단조성**으로만 한다.
"""

from __future__ import annotations

from typing import Any

from foms.services.channel_policy import MAX_MANUAL_ATTACHMENTS
from foms.services.orders.as_log import current_as_round

__all__ = [
    "last_pushed_max_attachment_id",
    "select_as_push_attachments",
]


def _attachment_id(attachment: Any) -> int:
    """첨부 id 를 int 로 읽는다(없거나 비정상이면 0)."""
    try:
        return int(getattr(attachment, "id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def last_pushed_max_attachment_id(prev_push: Any) -> int:
    """직전 AS PUSH 에 실린 첨부 id 최대값. 이력이 없으면 0.

    ``max_attachment_id`` 가 정본이고, 그 값이 없는 구이력에서는 ``attachment_ids`` 로
    폴백한다(둘 다 AS-FRESH-01 T9 부터 기록된다).

    Args:
        prev_push: ``structured_data['channeltalk_push_as']`` (dict 가 아니면 무시).

    Returns:
        첨부 id 최대값(없으면 0).
    """
    if not isinstance(prev_push, dict):
        return 0
    raw_max = prev_push.get("max_attachment_id")
    if isinstance(raw_max, int) and raw_max > 0:
        return raw_max
    ids = prev_push.get("attachment_ids")
    if isinstance(ids, list):
        numeric = [int(i) for i in ids if isinstance(i, int)]
        if numeric:
            return max(numeric)
    return 0


def _round_by_log_id(sd: Any) -> dict[str, int]:
    """as_log 항목 id → 소속 회차. 삭제 항목은 제외하고, round 없는 구항목은 1회차."""
    entries = ((sd or {}).get("shipment") or {}).get("as_log")
    out: dict[str, int] = {}
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("deleted") is True:
            continue
        log_id = str(entry.get("id") or "")
        if not log_id:
            continue
        raw_round = entry.get("round")
        out[log_id] = raw_round if isinstance(raw_round, int) and raw_round >= 1 else 1
    return out


def select_as_push_attachments(
    sd: Any,
    attachments: list[Any],
    prev_push: Any = None,
    *,
    limit: int = MAX_MANUAL_ATTACHMENTS,
) -> list[Any]:
    """AS PUSH 로 보낼 첨부를 고른다(모듈 docstring 의 3단 규칙).

    Args:
        sd: 주문 structured_data.
        attachments: 그 주문의 ``category='as'`` 첨부(순서 무관).
        prev_push: ``structured_data['channeltalk_push_as']`` 직전 이력.
        limit: 전송 상한(기본 = 채널톡 수동 push 정책 상한).

    Returns:
        선정된 첨부를 **id 오름차순**(업로드 순)으로. 상한 초과 시 남는 쪽은 **최신**이다.
    """
    items = [a for a in attachments if getattr(a, "storage_key", None)]
    if not items:
        return []

    rounds = _round_by_log_id(sd)
    current_round = current_as_round(sd or {})
    picked = [
        a for a in items
        if rounds.get(str(getattr(a, "as_log_id", None) or "")) == current_round
    ]
    if not picked:
        last_id = last_pushed_max_attachment_id(prev_push)
        picked = [a for a in items if _attachment_id(a) > last_id]
    if not picked:
        picked = list(items)

    # 최신 우선으로 자른 뒤 업로드 순으로 되돌린다 — 절단이 최신을 버리지 않게.
    picked.sort(key=_attachment_id, reverse=True)
    return sorted(picked[: max(0, limit)], key=_attachment_id)
