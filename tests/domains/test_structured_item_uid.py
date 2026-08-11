"""품목 안정 식별자 계약 (ORDER-ITEM-UID).

uid 가 흔들리면 변경 이력이 "전 품목 삭제 후 재생성"으로 보인다 — 기능이 조용히 쓸모없어지는
실패 방식이라, 여기서 고정하는 것은 **불변성**과 **위조 차단** 두 가지다.
"""

import uuid

from foms.services.orders.structured_item_uid import ensure_item_uids, item_uid_of


def _doc(items):
    return {"items": items}


def test_missing_uids_are_issued():
    """uid 가 없는 문서는 모든 품목이 uid 를 받는다."""
    document = _doc([{"product_name": "붙박이장"}, {"product_name": "수납장"}])

    issued = ensure_item_uids({}, document)

    uids = [item_uid_of(item) for item in document["items"]]
    assert issued == 2
    assert all(uids)
    assert len(set(uids)) == 2
    for value in uids:
        uuid.UUID(value)  # 형식이 UUID 여야 한다(형식 검사가 곧 위조 판정 기준이다)


def test_uid_is_stable_across_saves():
    """다시 저장해도 uid 는 그대로다 — 재발급되면 이력이 매 저장 끊긴다."""
    old = _doc([{"product_name": "붙박이장"}])
    ensure_item_uids({}, old)
    first = item_uid_of(old["items"][0])

    new = _doc([{"uid": first, "product_name": "붙박이장", "price": "500000"}])
    issued = ensure_item_uids(old, new)

    assert issued == 0
    assert item_uid_of(new["items"][0]) == first


def test_unknown_uid_from_client_is_rejected():
    """이 주문에 없던 uid 는 인정하지 않는다(남의 품목 이력에 붙이기 차단)."""
    old = _doc([{"product_name": "붙박이장"}])
    ensure_item_uids({}, old)
    stolen = str(uuid.uuid4())

    new = _doc([{"uid": stolen, "product_name": "붙박이장"}])
    ensure_item_uids(old, new)

    # 위치로 물려받은 원래 uid 여야 한다 — 클라이언트가 보낸 값이 아니다.
    assert item_uid_of(new["items"][0]) == item_uid_of(old["items"][0])
    assert item_uid_of(new["items"][0]) != stolen


def test_duplicate_uid_is_reissued():
    """같은 uid 를 두 품목에 달아 보내면 뒤쪽은 새로 발급한다(이력 뒤섞임 차단)."""
    old = _doc([{"product_name": "붙박이장"}])
    ensure_item_uids({}, old)
    original = item_uid_of(old["items"][0])

    new = _doc([
        {"uid": original, "product_name": "붙박이장"},
        {"uid": original, "product_name": "복제본"},
    ])
    issued = ensure_item_uids(old, new)

    first, second = (item_uid_of(item) for item in new["items"])
    assert first == original
    assert second != original
    assert issued == 1


def test_uidless_client_inherits_by_position():
    """uid 를 모르는 입력 경로(태블릿·마법사)는 위치로 물려받는다.

    새로 발급해 버리면 저장 한 번이 "전 품목 삭제 후 재생성"으로 기록된다 — 오늘보다 나빠진다.
    """
    old = _doc([{"product_name": "붙박이장"}, {"product_name": "수납장"}])
    ensure_item_uids({}, old)
    old_uids = [item_uid_of(item) for item in old["items"]]

    new = _doc([{"product_name": "붙박이장"}, {"product_name": "수납장", "price": "100000"}])
    issued = ensure_item_uids(old, new)

    assert issued == 0
    assert [item_uid_of(item) for item in new["items"]] == old_uids


def test_new_item_gets_fresh_uid_without_stealing():
    """품목이 늘면 새것만 발급받고 기존 uid 는 그대로다."""
    old = _doc([{"product_name": "붙박이장"}])
    ensure_item_uids({}, old)
    original = item_uid_of(old["items"][0])

    new = _doc([{"uid": original, "product_name": "붙박이장"}, {"product_name": "신규"}])
    issued = ensure_item_uids(old, new)

    assert issued == 1
    assert item_uid_of(new["items"][0]) == original
    assert item_uid_of(new["items"][1]) != original


def test_non_list_items_are_tolerated():
    """구조가 깨진 문서가 와도 저장 경로를 죽이지 않는다."""
    assert ensure_item_uids({}, {"items": "깨짐"}) == 0
    assert ensure_item_uids(None, None) == 0


def test_client_uid_wins_over_positional_inheritance():
    """맨 앞에 새 품목을 끼워도 기존 품목이 자기 uid 를 지킨다.

    위치 상속을 먼저 돌리면 새 품목이 0번 자리의 옛 uid 를 가로채고, 정작 그 uid 를 들고 온
    품목은 새 값을 받는다 — 삽입 1건이 "앞 품목이 바뀌고 뒤에 하나 추가됨"으로 기록된다.
    (2026-08-11 구현 중 실제로 잡힌 버그.)
    """
    old = _doc([{"product_name": "붙박이장"}])
    ensure_item_uids({}, old)
    original = item_uid_of(old["items"][0])

    new = _doc([
        {"product_name": "수납장"},                             # 새 품목(uid 없음)
        {"uid": original, "product_name": "붙박이장"},           # 기존 품목(uid 보유)
    ])
    issued = ensure_item_uids(old, new)

    assert item_uid_of(new["items"][1]) == original
    assert item_uid_of(new["items"][0]) != original
    assert issued == 1
