"""담당자 개인 도면방 매핑 계약 — 입력 정규화와 담당자 해석.

도면방 PUSH 는 공용 도면방과 **주문 담당자의 개인 도면방**에 함께 나간다. 그 매칭이
틀리면 남의 방에 도면이 간다. 그래서 다음을 계약으로 고정한다.

* 방 주소를 통째로 붙여 넣어도 숫자만 남긴다(사용자가 실제로 하는 입력).
* 폐기된 그룹 id 는 등록 자체를 거부한다.
* 담당자 미입력·계정 없음·방 미등록은 각각 다른 사유로 구분해 안내한다(조용히 넘기지 않는다).
* 겸직(같은 이름 계정 여럿)은 등록된 방이 **전부 같을 때만** 보낸다 — 서로 다르면 건너뛴다.
  운영 실측: 이시영이 관리자 계정과 담당자 계정을 함께 쓴다.
"""
from __future__ import annotations

import pytest

from foms.services.channel_manager_room import (
    normalize_channel_group_id,
    resolve_manager_room,
)


class _FakeUser:
    """이름과 개인방만 가진 사용자 대역."""

    def __init__(self, name: str, group_id: str | None) -> None:
        self.name = name
        self.channel_drawing_group_id = group_id


class _FakeOrder:
    """담당자 이름만 가진 주문 대역."""

    def __init__(self, manager_name: str | None) -> None:
        self.manager_name = manager_name


class _FakeQuery:
    def __init__(self, users: list[_FakeUser]) -> None:
        self._users = users

    def filter(self, *_args, **_kwargs) -> "_FakeQuery":
        return self

    def all(self) -> list[_FakeUser]:
        return list(self._users)


class _FakeDb:
    def __init__(self, users: list[_FakeUser]) -> None:
        self._users = users

    def query(self, *_args, **_kwargs) -> _FakeQuery:
        return _FakeQuery(self._users)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("567922", "567922"),
        ("  567922  ", "567922"),
        ("https://channel.works/haud/team-chat/groups/567922", "567922"),
        ("channel.works/haud/team-chat/groups/477146", "477146"),
        ("", ""),
        (None, ""),
        ("그룹 없음", ""),
    ],
)
def test_normalize_accepts_number_and_room_url(raw, expected) -> None:
    """숫자와 방 주소를 모두 받아 숫자만 남긴다."""
    assert normalize_channel_group_id(raw) == expected


def test_normalize_rejects_retired_group(monkeypatch) -> None:
    """폐기된 그룹은 등록 단계에서 막는다 — 보낼 때 터지면 늦다."""
    monkeypatch.setattr(
        "foms.services.channel_manager_room.is_retired_channel_group_id",
        lambda gid: str(gid) == "111111",
    )
    with pytest.raises(ValueError):
        normalize_channel_group_id("111111")


def test_registered_manager_resolves_to_room() -> None:
    """담당자 이름이 사용자 이름과 맞으면 그 사람 방으로 간다."""
    db = _FakeDb([_FakeUser("강민경", "567925"), _FakeUser("한용희", "567922")])
    lookup = resolve_manager_room(db, _FakeOrder("강민경"))
    assert lookup.group_id == "567925"
    assert lookup.reason is None
    assert lookup.message is None


def test_manager_name_is_trimmed_on_both_sides() -> None:
    """앞뒤 공백은 매칭을 막지 않는다(운영 데이터에 공백 얼룩이 있다)."""
    db = _FakeDb([_FakeUser(" 채수민", "567930")])
    assert resolve_manager_room(db, _FakeOrder("채수민 ")).group_id == "567930"


def test_dual_role_same_room_still_sends() -> None:
    """겸직이라 계정이 둘이어도 같은 방이면 보낸다(이시영 = 관리자 + 담당자)."""
    db = _FakeDb([_FakeUser("이시영", "477146"), _FakeUser("이시영", "477146")])
    lookup = resolve_manager_room(db, _FakeOrder("이시영"))
    assert lookup.group_id == "477146"
    assert lookup.reason is None


def test_conflicting_rooms_are_skipped_not_guessed() -> None:
    """같은 이름 계정이 서로 다른 방을 가리키면 우리가 고르지 않는다."""
    db = _FakeDb([_FakeUser("김세연", "567931"), _FakeUser("김세연", "567932")])
    lookup = resolve_manager_room(db, _FakeOrder("김세연"))
    assert lookup.group_id is None
    assert lookup.reason == "ambiguous"
    assert "사용자 관리" in lookup.message


@pytest.mark.parametrize(
    "manager, users, reason",
    [
        ("", [_FakeUser("강민경", "567925")], "no_manager"),
        (None, [_FakeUser("강민경", "567925")], "no_manager"),
        ("명창욱", [_FakeUser("강민경", "567925")], "no_user"),
        ("강민경", [_FakeUser("강민경", None), _FakeUser("한용희", "567922")], "not_registered"),
        ("강민경", [_FakeUser("강민경", "   "), _FakeUser("한용희", "567922")], "not_registered"),
    ],
)
def test_missing_room_reports_a_distinct_reason(manager, users, reason) -> None:
    """못 보낸 사유는 뭉뚱그리지 않는다 — 화면이 다음 할 일을 말해야 한다."""
    lookup = resolve_manager_room(_FakeDb(users), _FakeOrder(manager))
    assert lookup.group_id is None
    assert lookup.reason == reason
    assert lookup.message, "사유만 있고 안내 문구가 없다"


@pytest.mark.parametrize(
    "users",
    [
        [],
        [_FakeUser("강민경", None), _FakeUser("한용희", "")],
        [_FakeUser("강민경", "   ")],
    ],
)
def test_dormant_when_nobody_registered_a_room(users) -> None:
    """아무도 방을 등록하지 않았으면 조용하다 — 공용방만 보내던 예전 화면 그대로.

    운영 결정(2026-09-10): 개인방을 공개 그룹으로 바꾸면 검색이 번잡해져 일단
    공용 도면방만 쓴다. 그 상태에서 "미등록" 을 매번 알리면 소음이다.
    """
    lookup = resolve_manager_room(_FakeDb(users), _FakeOrder("강민경"))
    assert lookup.group_id is None
    assert lookup.reason == "dormant"
    assert lookup.message is None, "기능을 안 쓰는 상태인데 화면에 무언가를 띄운다"


def test_one_registration_wakes_the_reasons_back_up() -> None:
    """한 명이라도 등록하면 나머지 담당자의 미등록 안내가 스스로 살아난다."""
    users = [_FakeUser("한용희", "567922"), _FakeUser("강민경", None)]
    lookup = resolve_manager_room(_FakeDb(users), _FakeOrder("강민경"))
    assert lookup.reason == "not_registered"
    assert lookup.message
