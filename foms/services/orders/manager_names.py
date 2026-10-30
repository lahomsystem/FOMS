"""주문 담당자 여러 명(MULTI-MGR-01, 2026-10-30).

담당자는 ``structured_data["parties"]["manager"]`` 에 두 칸으로 산다.

- ``name``  : **대표 담당자**(첫 번째 뱃지). ``orders.manager_name`` 컬럼도 이 값이다.
  실측 달력 색·담당자별 묶음·정산 줄·영업 owner 자동 배정처럼 "한 명"이 필요한 곳은
  이 값을 그대로 쓴다(사용자 결정 2026-10-30: 정산은 대표 1명에게만).
- ``names`` : 전체 명단(대표가 맨 앞). "내 주문" 거르기·권한·알림·채널톡 담당자 방처럼
  "이 사람이 담당자인가"를 묻는 곳과 화면 표시는 이 명단을 쓴다.

``name`` 만 쓰는 옛 경로(인라인 담당자 수정·옛 편집 폼·네이버 자동 채움)가 남아 있으므로
읽을 때 두 칸이 어긋나면 ``name`` 을 믿는다: ``name`` 이 명단에 있으면 맨 앞으로 올리고,
없으면 명단은 낡은 것이라 ``name`` 만 본다.

옛 한 칸 여러 이름(운영 실측 2026-10-30, 30건 남짓): ``"김의종, 백재현"``·``"최진호/한용희"``·
``"안중훈(1번), 백재현(2번)"``. ``name`` 칸 하나를 읽을 때는 쉼표·빗금·줄바꿈으로 나눈다 —
이런 주문은 다음 저장 때 ``name``=첫 사람·``names``=전체로 정리된다.
"""

from __future__ import annotations

from typing import Any

MANAGER_NAMES_SEPARATOR = ", "

_SEPARATORS = ",\n"
_LEGACY_SEPARATORS = ",/\n"


def _split_outside_parens(text: str, separators: str) -> list[str]:
    """괄호 밖의 구분자에서만 나눈다 — ``"백재현(2번, 3번)"`` 은 한 사람이다(운영 #5579 실측)."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if depth == 0 and ch in separators:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def normalize_name_list(value: Any) -> list[str]:
    """이름 목록을 앞뒤 공백 없는 중복 없는 문자열 목록으로 만든다.

    Args:
        value: 목록(문자열·``{"name": ...}`` 원소) 또는 쉼표·줄바꿈으로 나뉜 문자열.

    Returns:
        입력 순서를 지킨 이름 목록.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_items: list[Any] = list(value)
    else:
        raw_items = _split_outside_parens(str(value), _SEPARATORS)
    names: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            item = item.get("name") or item.get("text") or item.get("value") or ""
        name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _legacy_names(value: Any) -> list[str]:
    """대표 칸 값 하나를 이름 목록으로 나눈다(옛 한 칸 여러 이름 꼴 포함)."""
    if value is None or isinstance(value, (dict, list, tuple)):
        return []
    return normalize_name_list(_split_outside_parens(str(value), _LEGACY_SEPARATORS))


def order_manager_names(structured_data: Any, fallback: Any = None) -> list[str]:
    """주문의 담당자 전체 명단(대표가 맨 앞)을 돌려준다.

    Args:
        structured_data: 주문 structured_data(None·비 dict 허용).
        fallback: sd 에 담당자가 없을 때 쓸 값(보통 ``orders.manager_name`` 컬럼).

    Returns:
        담당자 이름 목록. 없으면 빈 목록.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    parties = sd.get("parties") if isinstance(sd.get("parties"), dict) else {}
    manager = parties.get("manager")
    if isinstance(manager, dict):
        primary_list = _legacy_names(manager.get("name"))
        names = normalize_name_list(manager.get("names"))
    else:
        primary_list = _legacy_names(manager)
        names = []
    if primary_list:
        primary = primary_list[0]
        if len(primary_list) == 1 and primary in names:
            names.remove(primary)
            names.insert(0, primary)
        else:
            names = primary_list
    if not names:
        names = _legacy_names(fallback)
    return names


def order_manager_label(structured_data: Any, fallback: Any = None) -> str:
    """화면·메시지에 쓸 담당자 표시 문자열(``"김의종, 한용희"``)."""
    return MANAGER_NAMES_SEPARATOR.join(order_manager_names(structured_data, fallback))


def order_manager_match_names(structured_data: Any, fallback: Any = None) -> set[str]:
    """권한·"내 주문" 대조용 담당자 이름(소문자, 완전 일치용)."""
    return {name.lower() for name in order_manager_names(structured_data, fallback)}


def normalize_manager_party(structured_data: Any) -> None:
    """저장 직전 ``parties.manager`` 를 ``name``=대표·``names``=명단 꼴로 맞춘다.

    ``name`` 이 늘 정본이다. 새 폼은 ``name = names[0]`` 을 함께 보내고, 옛 경로는
    ``name`` 만 바꾼다(병합 저장이라 낡은 ``names`` 가 남는다) — 그래서 :func:`order_manager_names`
    규칙(명단에 대표가 없으면 명단을 버린다)으로 정리하면 두 경우가 모두 맞다. ``name`` 을
    비우면 명단도 비운다. 호출자가 넘긴 dict 를 그 자리에서 고친다(호출자는 이미 deepcopy
    한 사본을 넘긴다).

    Args:
        structured_data: 저장할 structured_data 사본.
    """
    if not isinstance(structured_data, dict):
        return
    parties = structured_data.get("parties")
    if not isinstance(parties, dict):
        return
    manager = parties.get("manager")
    if not isinstance(manager, dict):
        return
    names = order_manager_names(structured_data) if str(manager.get("name") or "").strip() else []
    manager["name"] = names[0] if names else ""
    if len(names) > 1:
        manager["names"] = names
    else:
        manager.pop("names", None)


def manager_label_from_parties(parties: Any) -> str:
    """``structured_data["parties"]`` 만 들고 있는 빌더용 :func:`order_manager_label`."""
    return order_manager_label({"parties": parties} if isinstance(parties, dict) else {})


def manager_label_filter(row: Any) -> str:
    """Jinja ``|manager_label`` — 행(ORM 주문·DTO·dict)의 담당자 전체 표시 문자열.

    ``structured_data`` 를 가진 행은 명단을 읽고, 없는 DTO 는 ``manager_name`` 을 그대로 쓴다
    (DTO 빌더가 이미 전체 표시 문자열을 넣는다). 값이 없으면 빈 문자열이라
    ``{{ r|manager_label or '-' }}`` 로 쓴다.
    """
    if row is None:
        return ""
    if isinstance(row, dict):
        sd = row.get("structured_data")
        fallback = row.get("manager_name")
    else:
        sd = getattr(row, "structured_data", None)
        fallback = getattr(row, "manager_name", None)
    if isinstance(sd, dict) and sd:
        label = order_manager_label(sd)
        if label:
            return label
    return str(fallback or "").strip()


__all__ = [
    "MANAGER_NAMES_SEPARATOR",
    "manager_label_filter",
    "manager_label_from_parties",
    "normalize_manager_party",
    "normalize_name_list",
    "order_manager_label",
    "order_manager_match_names",
    "order_manager_names",
]
