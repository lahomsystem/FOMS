"""워크벤치 계약 테스트가 마크업을 **속성 순서에 안 묶이게** 읽는 도구.

**왜 이 모듈이 있는가**: v3 계약 테스트는 오랫동안 ``'id="wb-dispatch" disabled' in body``
처럼 **속성 두 개가 그 순서로 붙어 있어야만** 통과하는 단언을 썼다. 그래서 템플릿에
``data-*`` 하나를 끼우거나 ``class`` 를 옮기기만 해도 기능은 멀쩡한 채로 red 가 났고,
반대로 템플릿에는 "속성 순서를 지킬 것"이라는 주석이 생겨 **마크업이 테스트에 인질로**
잡혔다. 여기 함수들은 id 로 여는 태그를 통째로 잡고 **그 태그 안에서** 속성을 보므로,
속성이 id 앞에 오든 뒤에 오든 같은 것을 잰다.

붙는 힘은 오히려 세진다: 부분문자열 단언은 요소가 통째로 사라져도 "없으니 통과"로
조용히 green 이 됐지만, 여기서는 요소가 없으면 :class:`AssertionError` 로 터진다.

세 파일(``test_naver_workbench`` · ``..._relation`` · ``..._v3_contract``)이 함께 쓰므로
한 곳에 둔다. ``conftest.py`` 보다 먼저 로드돼도 안전하도록 **순수 문자열 함수만** 둔다 —
여기서 ``db`` 나 앱을 import 하면 엔진이 conftest 의 가드보다 먼저 묶인다(2026-08-23
로컬 DB 드롭 사고의 경로다).
"""

from __future__ import annotations

import re

__all__ = ["open_tag", "has_attribute", "is_disabled"]


def open_tag(html: str, element_id: str) -> str:
    """``id="…"`` 를 가진 요소의 **여는 태그 하나**를 통째로 돌려준다(속성 순서 무관).

    id 가 나온 자리에서 앞쪽 ``<`` 까지 되짚고, 뒤로는 **따옴표 밖의** ``>`` 까지 끊는다.
    그래서 id 가 첫 속성이든 마지막 속성이든 같은 태그가 잡히고, 속성값 안에 ``>`` 가
    들어와도(``title="a > b"``) 태그가 중간에서 잘리지 않는다 — 옛 방식
    (``split('id="…"')[1].split(">")[0]``)은 그 두 경우에 조용히 틀린 조각을 돌려줬다.

    **전제**: 속성값 안에 ``<`` 는 없다. 여는 태그의 시작을 "가장 가까운 앞쪽 ``<``"
    로 되짚기 때문이다. 지금 워크벤치 템플릿에는 그런 값이 없다. 생긴다면 이 함수가
    태그를 짧게 잘라 조용히 틀리므로, 그때는 앞쪽 되짚기도 따옴표를 세도록 고쳐야 한다.
    """
    needle = f'id="{element_id}"'
    at = html.find(needle)
    if at < 0:
        raise AssertionError(f'마크업에 id="{element_id}" 인 요소가 없다')
    start = html.rfind("<", 0, at)
    if start < 0:
        raise AssertionError(f'id="{element_id}" 앞에 여는 `<` 가 없다')

    quote = ""
    for pos in range(start, len(html)):
        char = html[pos]
        if quote:
            if char == quote:
                quote = ""
        elif char in ('"', "'"):
            quote = char
        elif char == ">":
            return html[start:pos + 1]
    raise AssertionError(f'id="{element_id}" 의 여는 태그가 닫히지 않았다')


def _attribute_names(tag: str) -> str:
    """따옴표 안(속성 **값**)을 지운 태그 — 속성 이름과 태그 이름만 남는다.

    값을 안 지우면 ``title="… 발송처리가 disabled …"`` 같은 글자에 속는다.
    """
    kept: list[str] = []
    quote = ""
    for char in tag:
        if quote:
            if char == quote:
                quote = ""
                kept.append(" ")  # 값을 지운 자리에 경계를 남긴다
            continue
        if char in ('"', "'"):
            quote = char
            continue
        kept.append(char)
    return "".join(kept)


def has_attribute(html: str, element_id: str, attribute: str) -> bool:
    """그 요소의 여는 태그에 그 **속성이 실제로 붙어 있는가**(값은 안 본다).

    속성 **값** 안의 같은 글자에도, 이름이 겹치는 다른 속성(``data-disabled-reason``)
    에도 안 속는다 — 이름 토큰이 통째로 일치할 때만 참이다.
    """
    names = _attribute_names(open_tag(html, element_id))
    return re.search(rf"(?<![\w-]){re.escape(attribute)}(?![\w-])", names) is not None


def is_disabled(html: str, element_id: str) -> bool:
    """그 버튼이 **서버 렌더 시점에** 잠겨 있는가(``disabled`` 속성).

    잠금 판정은 워크벤치의 핵심 계약이다(불가역 호출은 잠긴 집에서 못 나간다).
    요소 자체가 없으면 참·거짓 대신 터진다 — "버튼이 사라져서 통과"는 답이 아니다.
    """
    return has_attribute(html, element_id, "disabled")
