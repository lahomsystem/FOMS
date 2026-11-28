"""생산 현장 알람 거는 함수 — **빈 틀**(설계서 2026-11-28 생산 현장 알람 §6-2 약속 3 · 흐름 셋 §4-3 약속 3).

쓰기 자리들은 이 모듈의 함수만 부른다. 지금은 넷 다 바로 돌아온다(쿼리 0 · 예외 0 · 줄 0) — 몸(스위치 읽기 · 받는 사람
정하기 · 줄 만들기 · 보내기)은 알람 서버 일꾼이 채운다. 이름 · 인자는 약속이라 바꾸지 않는다.

부르는 때(약속):

* ``note_mark`` · ``note`` 는 **커밋 전** — 세션 주머니(``db.info['floor_alarm']``)에 적기만 한다(쿼리 0).
* ``flush`` 는 **커밋 바로 뒤** — 적어 둔 것을 읽어 줄을 만들고(자기 커밋) 보낸 뒤 주머니를 비운다.
* 되감은 길에서는 ``flush`` 를 부르지 않는다.
* 넷 다 예외를 밖으로 내지 않고, 스위치가 꺼져 있으면 바로 돌아온다.
"""

from __future__ import annotations

from typing import Any


def enabled() -> bool:
    """알람 스위치가 켜졌는지 — 읽는 곳은 여기 하나.

    지금은 늘 False 다. 스위치(환경 변수 ``FOMS_PRODUCTION_FLOOR_ALARM``) 읽기는 알람 서버 일꾼이 채운다.

    Returns:
        켜졌으면 True.
    """
    return False


def note_mark(db: Any, actor: Any, req: Any, data: Any) -> None:
    """표시 쓰기 전용 — ``mark_one`` 결과를 받은 바로 뒤, **커밋 전**에 부른다.

    세션 주머니에 적기만 한다(쿼리 0 · 예외 없음). 약속 1(``gave``) · 2(``holders_before``)를 읽는다.

    Args:
        db: 그 요청의 DB 세션.
        actor: 누른 사람.
        req: 표시 쓰기 요청.
        data: ``mark_one`` 결과.
    """
    return None


def note(db: Any, kind: str, order_id: Any, actor: Any, **material: Any) -> None:
    """그 밖 쓰기 자리 — **커밋 전**에 부른다. 세션 주머니에 적기만 한다(쿼리 0 · 예외 없음).

    Args:
        db: 그 요청의 DB 세션.
        kind: 알람 종류(약속 4 — ``hold`` · ``defect`` · ``rework`` · ``drawing_replaced`` …).
        order_id: 주문 id.
        actor: 한 사람.
        **material: 종류마다의 재료(약속 4 — ``reason`` · ``drawing_keys`` · ``detail`` …).
    """
    return None


def flush(db: Any) -> None:
    """**커밋 바로 뒤**에 부른다 — 적어 둔 것을 알람 줄로 만들어 보내고 주머니를 비운다(자기 커밋 · 예외 없음).

    되감은 길에서는 부르지 않는다.

    Args:
        db: 그 요청의 DB 세션.
    """
    return None
