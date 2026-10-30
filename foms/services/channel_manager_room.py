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

담당자 여럿: 담당자 칸에 ``김의종, 백재현``·``최진호/한용희``·``안중훈(1번), 백재현(2번)``
처럼 여러 이름을 적는다(운영 실측 2026-10-30, 30건 남짓). 칸 전체가 한 계정 이름과
맞지 않으면 괄호 속을 지우고 쉼표·빗금으로 나눠 **사람마다** 방을 찾아 모두 보낸다.
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
# 담당자 칸의 여러 이름 구분자(쉼표·빗금)와 이름 뒤 메모 괄호(``(1번)``·``(라운즈)``).
_NAME_SPLIT_RE = re.compile(r"[,/]")
_NAME_NOTE_RE = re.compile(r"\([^)]*\)")


class ManagerRoomLookup:
    """담당자 개인방 해석 결과.

    속성:
        group_id: 보낼 개인방 그룹 id. 없으면 ``None``.
        manager_name: 판정에 쓴 담당자 이름(빈 담당자면 ``""``).
        group_ids: 보낼 개인방 전부(담당자 여럿이면 여럿, 중복 없음). ``group_id`` 는
            그 첫 번째다.
        reason: 못 보내는 담당자가 있을 때의 사유 코드 —
            ``dormant``(아무도 개인방을 등록하지 않음 = 기능 미사용) /
            ``no_manager``(담당자 미입력) / ``no_user``(같은 이름 계정 없음) /
            ``not_registered``(계정은 있으나 방 미등록) /
            ``ambiguous``(같은 이름 계정들이 서로 다른 방을 가리킴) /
            ``partial``(담당자 여럿 중 일부만 방을 찾음).
            모두 찾았으면 ``None``.
        message: 화면에 그대로 띄울 한글 안내(모두 찾았으면 ``None``).
        missing_users: 계정을 못 찾은 담당자 이름들 — 도면팀이 담당자 칸만 고치면
            풀리는 문제라 보내기 전에 확인받는 근거다.
    """

    __slots__ = ("group_id", "group_ids", "manager_name", "reason", "message", "missing_users")

    def __init__(
        self,
        group_id: str | None,
        manager_name: str,
        reason: str | None = None,
        message: str | None = None,
        *,
        group_ids: tuple[str, ...] | None = None,
        missing_users: tuple[str, ...] = (),
    ) -> None:
        self.group_ids = tuple(group_ids) if group_ids is not None else ((group_id,) if group_id else ())
        self.group_id = self.group_ids[0] if self.group_ids else None
        self.manager_name = manager_name
        self.reason = reason
        self.message = message
        self.missing_users = tuple(missing_users)

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의
        return (
            f"ManagerRoomLookup(group_ids={self.group_ids!r}, "
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
    users = db.query(User).filter(User.name.isnot(None)).all()

    # 아무도 개인방을 등록하지 않았으면 기능을 안 쓰는 상태다. 그때는 "미등록" 을
    # 매번 알리지 않는다 — 공용 도면방만 보내던 예전 화면 그대로다. 한 명이라도
    # 등록하는 순간 아래 사유 안내가 스스로 살아난다.
    feature_in_use = any(str(u.channel_drawing_group_id or "").strip() for u in users)
    if not feature_in_use:
        return ManagerRoomLookup(None, manager_name, "dormant", None)

    if not manager_name:
        return ManagerRoomLookup(
            None, "", "no_manager", "주문에 담당자가 없어 담당자 개인방은 보내지 않았습니다."
        )

    whole_name_matches = any(str(u.name or "").strip() == manager_name for u in users)
    names = [manager_name] if whole_name_matches else _split_manager_names(manager_name)
    if len(names) <= 1:
        return _resolve_single(users, names[0] if names else manager_name, manager_name)
    return _resolve_several(users, names, manager_name)


def _split_manager_names(manager_name: str) -> list[str]:
    """담당자 칸을 사람 이름 목록으로 나눈다 — 괄호 메모를 지우고 쉼표·빗금으로 자른다."""
    names: list[str] = []
    for part in _NAME_SPLIT_RE.split(_NAME_NOTE_RE.sub("", manager_name)):
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def _room_of(users: list, name: str) -> tuple[str | None, str | None]:
    """이름 하나의 개인방을 찾는다. 반환 ``(group_id, 실패 사유)`` — 둘 중 하나만 채워진다."""
    candidates = [user for user in users if str(user.name or "").strip() == name]
    if not candidates:
        return None, "no_user"
    registered = {
        str(user.channel_drawing_group_id or "").strip()
        for user in candidates
        if str(user.channel_drawing_group_id or "").strip()
    }
    if not registered:
        return None, "not_registered"
    if len(registered) > 1:
        # 겸직이면 같은 방을 가리킨다. 서로 다르면 어느 쪽인지 우리가 정할 일이 아니다.
        return None, "ambiguous"
    return registered.pop(), None


def _resolve_single(users: list, name: str, manager_name: str) -> ManagerRoomLookup:
    """담당자 한 명 — 사유별 안내 문구를 그대로 돌려준다."""
    group_id, reason = _room_of(users, name)
    if group_id:
        return ManagerRoomLookup(group_id, manager_name)
    if reason == "no_user":
        return ManagerRoomLookup(
            None,
            manager_name,
            "no_user",
            f"담당자 '{manager_name}' 의 사용자 계정이 없어 담당자 개인방은 보내지 않았습니다.",
            missing_users=(name,),
        )
    if reason == "not_registered":
        return ManagerRoomLookup(
            None,
            manager_name,
            "not_registered",
            f"담당자 '{manager_name}' 의 개인 도면방이 등록되어 있지 않아 도면방에만 보냈습니다.",
        )
    return ManagerRoomLookup(
        None,
        manager_name,
        "ambiguous",
        (
            f"담당자 '{manager_name}' 이름의 계정이 서로 다른 개인 도면방을 가리켜 "
            "담당자 개인방은 보내지 않았습니다. 사용자 관리에서 방 번호를 맞춰주세요."
        ),
    )


_SEVERAL_REASON_TEXT = {
    "no_user": "사용자 계정 없음",
    "not_registered": "개인 도면방 미등록",
    "ambiguous": "같은 이름 계정의 방이 서로 다름",
}


def _resolve_several(users: list, names: list[str], manager_name: str) -> ManagerRoomLookup:
    """담당자 여럿 — 찾은 사람 방은 모두 보내고, 못 찾은 사람은 이름별로 알린다."""
    group_ids: list[str] = []
    failures: list[tuple[str, str]] = []
    for name in names:
        group_id, reason = _room_of(users, name)
        if group_id:
            if group_id not in group_ids:
                group_ids.append(group_id)
        else:
            failures.append((name, reason or "no_user"))
    missing_users = tuple(name for name, reason in failures if reason == "no_user")
    if not failures:
        return ManagerRoomLookup(None, manager_name, group_ids=tuple(group_ids))
    detail = ", ".join(f"{name}({_SEVERAL_REASON_TEXT[reason]})" for name, reason in failures)
    if not group_ids:
        reason = "no_user" if missing_users else failures[0][1]
        message = f"담당자 '{manager_name}' 중 개인방을 찾은 사람이 없어 도면방에만 보냈습니다 — {detail}."
    else:
        reason = "partial"
        message = f"담당자 '{manager_name}' 중 일부는 개인방으로 보내지 않았습니다 — {detail}."
    return ManagerRoomLookup(
        None,
        manager_name,
        reason,
        message,
        group_ids=tuple(group_ids),
        missing_users=missing_users,
    )
