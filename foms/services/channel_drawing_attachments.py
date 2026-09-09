"""도면방 PUSH 첨부 선정.

``category='drawing'`` 첨부를 전량 실어 보내면 옛 도면이 함께 나간다 — 도면을 전달할
때마다 그 파일들의 category 가 'drawing' 으로 표시되므로 1차·2차 전달본이 첨부 테이블에
그대로 쌓여 있기 때문이다(AS-FRESH-01 이 AS 에서 겪은 혼입과 같은 모양).

그래서 도면방 PUSH 는 **현재 전달본**(``structured_data['drawing_current_files']``)의
storage key 집합과 교집합만 보낸다. AS 선택자와 달리 회차·id 단조성 판정은 없다 —
현재 전달본 목록 자체가 정본이고, 그 **순서가 곧 도면 번호**다(화면의 "최신 전달본
(번호순)" = 채널톡 dto.files 순서). 상한을 넘으면 **뒤쪽**을 버린다.
"""

from __future__ import annotations

from typing import Any

from foms.services.channel_policy import MAX_MANUAL_ATTACHMENTS

__all__ = ["current_drawing_storage_keys", "select_drawing_room_push_attachments"]


def _attachment_id(attachment: Any) -> int:
    """첨부 id 를 int 로 읽는다(없거나 비정상이면 0)."""
    try:
        return int(getattr(attachment, "id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def current_drawing_storage_keys(order: Any) -> list[str]:
    """현재 전달본 도면의 storage key 를 전달 순서대로 돌려준다.

    엔트리 모양의 정본은 ``materialize_transfer_attachments``
    (:mod:`foms.services.orders.drawing_transfer`)가 만드는
    ``{key, filename, view_url, download_url}`` 이다. 키 이름은 ``storage_key`` 가 아니라
    **``key``** 다 — 여기서 틀리면 교집합이 항상 비어 늘 0장이 된다.

    Args:
        order: 대상 주문. ``structured_data`` 가 dict 가 아니면 빈 목록.

    Returns:
        전달 순서를 유지한 storage key 목록(빈 값 제외, 중복은 첫 등장만).
    """
    sd = getattr(order, "structured_data", None)
    entries = sd.get("drawing_current_files") if isinstance(sd, dict) else None
    if not isinstance(entries, list):
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def select_drawing_room_push_attachments(order: Any, attachments: list[Any]) -> list[Any]:
    """도면방 PUSH 로 보낼 첨부를 고른다(현재 전달본과의 교집합).

    Args:
        order: 대상 주문(현재 전달본 key 를 읽는다).
        attachments: 그 주문의 ``category='drawing'`` 첨부(순서 무관).

    Returns:
        ``drawing_current_files`` 순서대로 정렬된 첨부. ``storage_key`` 가 없는 행은
        제외하고, 같은 key 를 가진 행이 여럿이면 id 가 가장 작은 하나만 남긴다.
        상한(``MAX_MANUAL_ATTACHMENTS``)은 **앞에서** 자른다 — 도면 번호 순서가 뜻을
        가지므로 뒤가 아니라 앞을 지킨다.
    """
    keys = current_drawing_storage_keys(order)
    if not keys:
        return []
    wanted = set(keys)
    by_key: dict[str, Any] = {}
    for att in attachments or []:
        storage_key = str(getattr(att, "storage_key", None) or "").strip()
        if not storage_key or storage_key not in wanted:
            continue
        current = by_key.get(storage_key)
        if current is None or _attachment_id(att) < _attachment_id(current):
            by_key[storage_key] = att
    picked = [by_key[key] for key in keys if key in by_key]
    return picked[:MAX_MANUAL_ATTACHMENTS]
