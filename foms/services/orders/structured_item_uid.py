"""주문 품목 안정 식별자 — ``structured_data['items'][].uid`` (ORDER-ITEM-UID).

``structured_data['items']`` 는 위치 인덱스 배열이라, 품목을 중간에 끼우면 **뒤 품목 전부가
바뀐 것처럼** 기록됐다(ORDER-DIFF-00 의 알려진 한계). 품목마다 서버가 발급한 ``uid`` 를 달아
변경 비교가 위치가 아니라 identity 로 짝짓게 한다.

**:mod:`foms.services.orders.item_identity` 와 무엇이 다른가**: 그쪽(ITEM-ID-00)은
``OrderItemIdentity`` 테이블에 **(주문, 슬롯 인덱스) 기준**으로 UUID 를 발급해 첨부·일정을
묶는다 — 키가 여전히 위치다. 여기 uid 는 **품목 payload 안에 실려 폼을 왕복**하므로 품목이
움직여도 따라간다. 지금은 두 식별자 공간이 공존하며(용도가 다르다), 통합은 ITEM-ID-00 본체의
몫이다 — 첨부/일정 결합을 옮기는 backfill 이 함께 필요하기 때문이다.

**서버가 소유한다**: 클라이언트가 보낸 ``uid`` 는 *이미 이 주문에 있던 값*일 때만 인정한다.
임의 문자열을 주입해 남의 품목 이력에 붙이거나, 같은 uid 를 여러 품목에 달아 이력을 뒤섞는
것을 막는다(``lock_provenance`` 와 같은 철학).

**uid 를 모르는 입력 경로**(태블릿 실측 폼·도면 마법사 등)는 uid 없이 보낸다. 그때는
**위치로 물려받는다** — 그러지 않고 새로 발급하면 저장 한 번에 "전 품목 삭제 후 재생성"이
기록된다. 물려받기는 오늘과 같은 정확도(위치 기준)이고, uid 를 왕복시키는 경로만 더 정확해진다.
"""

from __future__ import annotations

import uuid
from typing import Any

__all__ = ["ITEM_UID_KEY", "ensure_item_uids", "item_uid_of"]

#: 품목 dict 안의 식별자 키.
ITEM_UID_KEY = "uid"

#: uid 형식 검사 — 서버가 발급한 UUID4 문자열만 인정한다(길이가 다르면 위조/오염으로 본다).
_UID_LENGTH = 36


def _items_of(document: Any) -> list[dict[str, Any]]:
    """``structured_data['items']`` 를 dict 목록으로 본다(형식이 아니면 빈 목록).

    :param document: ``structured_data``.
    :return: 품목 dict 목록(원본 참조 — 호출부가 in-place 로 고친다).
    """
    if not isinstance(document, dict):
        return []
    items = document.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def item_uid_of(item: Any) -> str | None:
    """품목의 uid 를 꺼낸다(형식이 아니면 ``None``).

    :param item: 품목 dict.
    :return: uid 문자열 또는 ``None``.
    """
    if not isinstance(item, dict):
        return None
    value = item.get(ITEM_UID_KEY)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if len(value) == _UID_LENGTH else None


def ensure_item_uids(old_sd: Any, new_sd: Any) -> int:
    """저장될 문서의 모든 품목에 안정 uid 를 보장한다(in-place).

    **2패스여야 한다.** 위치 상속을 먼저 돌리면, 맨 앞에 끼운 새 품목이 0번 자리의 옛 uid 를
    가로채고 정작 그 uid 를 들고 온 품목은 새 값을 받는다 — 삽입 1건이 "앞 품목이 바뀌고 뒤에
    하나 추가됨"으로 기록된다(정확히 uid 로 없애려던 그 오해다).

    1. **1패스** — 클라이언트가 보낸 uid 중 *이 주문에 이미 있던* 값을 먼저 확정한다.
    2. **2패스** — 남은 품목에 **같은 위치의 옛 uid** 중 아직 안 쓰인 것을 물려준다
       (uid 를 모르는 입력 경로 보호).
    3. 그래도 없으면 새로 발급한다(신규 품목).

    :param old_sd: 저장 전 ``structured_data``.
    :param new_sd: 저장될 ``structured_data``(여기 품목에 uid 가 채워진다).
    :return: 새로 발급한 uid 개수(0 이면 전부 기존 값 유지).
    """
    new_items = _items_of(new_sd)
    if not new_items:
        return 0

    old_items = _items_of(old_sd)
    known: set[str] = {uid for uid in (item_uid_of(item) for item in old_items) if uid}
    by_position = [item_uid_of(item) for item in old_items]

    used: set[str] = set()
    settled: list[str | None] = [None] * len(new_items)

    # 1패스: 클라이언트가 정당하게 들고 온 uid 를 먼저 확정한다(위치 상속보다 우선).
    for index, item in enumerate(new_items):
        claimed = item_uid_of(item)
        if claimed and claimed in known and claimed not in used:
            used.add(claimed)
            settled[index] = claimed

    # 2패스: 남은 자리에 같은 위치의 옛 uid → 없으면 새 발급.
    issued = 0
    for index, item in enumerate(new_items):
        if settled[index]:
            item[ITEM_UID_KEY] = settled[index]
            continue

        inherited = by_position[index] if index < len(by_position) else None
        if inherited and inherited not in used:
            used.add(inherited)
            item[ITEM_UID_KEY] = inherited
            continue

        fresh = str(uuid.uuid4())
        used.add(fresh)
        item[ITEM_UID_KEY] = fresh
        issued += 1
    return issued
