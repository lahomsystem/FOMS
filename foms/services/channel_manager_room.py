"""담당자 개인 도면방(채널톡 그룹) 매핑 — 등록값 정규화와 주문 담당자 해석.

도면방 PUSH 는 공용 도면방과 **주문 담당자의 개인 도면방**에 함께 나간다. 담당자
목록의 정본은 ``users`` 다(운영 확인: 대상자가 전부 계정으로 있고 출고설정
``measurement_manager`` 는 비어 있다). 그래서 방 번호는 사용자 관리 화면에서
``users.channel_drawing_group_id`` 에 등록한다.

매칭 축은 ``orders.manager_name`` → ``users.name`` 완전일치(앞뒤 공백 제거)다.
자유 입력이라 표기가 어긋나면 못 찾는데, 그때는 조용히 넘기지 않고 공용방만
보냈다고 호출부가 알린다.

겸직 함정: 같은 이름으로 계정이 둘 이상일 수 있다(운영 실측 — 이시영이 관리자
계정과 담당자 계정을 함께 쓴다). 등록된 방 번호가 **전부 같으면** 겸직이므로 그
방으로 보내고, 서로 **다르면** 어느 쪽인지 알 수 없으므로 개인방을 건너뛴다.
"""
from __future__ import annotations

import re
from typing import Any

from foms.services.channel_policy import is_retired_channel_group_id

__all__ = [
    "ManagerRoomLookup",
    "normalize_channel_group_id",
    "resolve_manager_room",
]

# 사용자가 붙여 넣는 채널톡 방 주소. 예:
# https://channel.works/haud/team-chat/groups/567922
_GROUP_URL_RE = re.compile(r"/groups/(\d+)")
_DIGITS_RE = re.compile(r"^\d+$")


class ManagerRoomLookup:
    """담당자 개인방 해석 결과.

    속성:
        group_id: 보낼 개인방 그룹 id. 없으면 ``None``.
        manager_name: 판정에 쓴 담당자 이름(빈 담당자면 ``""``).
        reason: ``group_id`` 가 없을 때의 사유 코드 —
            ``no_manager``(담당자 미입력) / ``no_user``(같은 이름 계정 없음) /
            ``not_registered``(계정은 있으나 방 미등록) /
            ``ambiguous``(같은 이름 계정들이 서로 다른 방을 가리킴).
            보낼 방을 찾았으면 ``None``.
        message: 화면에 그대로 띄울 한글 안내(보낼 방을 찾았으면 ``None``).
    """

    __slots__ = ("group_id", "manager_name", "reason", "message")

    def __init__(
        self,
        group_id: str | None,
        manager_name: str,
        reason: str | None = None,
        message: str | None = None,
    ) -> None:
        self.group_id = group_id
        self.manager_name = manager_name
        self.reason = reason
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의
        return (
            f"ManagerRoomLookup(group_id={self.group_id!r}, "
            f"manager_name={self.manager_name!r}, reason={self.reason!r})"
        )


def normalize_channel_group_id(raw: Any) -> str:
    """사용자 입력을 채널톡 그룹 id 숫자 문자열로 정규화한다.

    방 주소를 통째로 붙여 넣는 편이 자연스러워서 URL 과 숫자를 모두 받는다.

    파라미터:
        raw: 입력값. 숫자 문자열, 방 URL, ``None`` 중 무엇이든 받는다.
    반환: 숫자만 남긴 그룹 id. 비었거나 해석할 수 없으면 빈 문자열.
    예외:
        ValueError: 형식은 맞으나 폐기된 그룹 id 일 때(등록을 막는다).
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    matched = _GROUP_URL_RE.search(text)
    if matched:
        group_id = matched.group(1)
    elif _DIGITS_RE.match(text):
        group_id = text
    else:
        return ""
    if is_retired_channel_group_id(group_id):
        raise ValueError(f"폐기된 채널톡 그룹입니다: {group_id}")
    return group_id


def resolve_manager_room(db, order: Any) -> ManagerRoomLookup:
    """주문 담당자의 개인 도면방을 찾는다.

    파라미터:
        db: 요청 스코프 세션.
        order: 담당자 이름(``manager_name``)을 가진 주문.
    반환: :class:`ManagerRoomLookup`. 못 찾은 사유는 화면 안내 문구까지 담는다.
    """
    from models import User  # 순환 import 회피 — 서비스가 모델을 끌어오지 않는다

    manager_name = str(getattr(order, "manager_name", None) or "").strip()
    if not manager_name:
        return ManagerRoomLookup(
            None, "", "no_manager", "주문에 담당자가 없어 담당자 개인방은 보내지 않았습니다."
        )

    candidates = [
        user
        for user in db.query(User).filter(User.name.isnot(None)).all()
        if str(user.name or "").strip() == manager_name
    ]
    if not candidates:
        return ManagerRoomLookup(
            None,
            manager_name,
            "no_user",
            f"담당자 '{manager_name}' 의 사용자 계정이 없어 담당자 개인방은 보내지 않았습니다.",
        )

    registered = {
        str(user.channel_drawing_group_id or "").strip()
        for user in candidates
        if str(user.channel_drawing_group_id or "").strip()
    }
    if not registered:
        return ManagerRoomLookup(
            None,
            manager_name,
            "not_registered",
            f"담당자 '{manager_name}' 의 개인 도면방이 등록되어 있지 않아 도면방에만 보냈습니다.",
        )
    if len(registered) > 1:
        # 겸직이면 같은 방을 가리킨다. 서로 다르면 어느 쪽인지 우리가 정할 일이 아니다.
        return ManagerRoomLookup(
            None,
            manager_name,
            "ambiguous",
            (
                f"담당자 '{manager_name}' 이름의 계정이 서로 다른 개인 도면방을 가리켜 "
                "담당자 개인방은 보내지 않았습니다. 사용자 관리에서 방 번호를 맞춰주세요."
            ),
        )
    return ManagerRoomLookup(registered.pop(), manager_name)
