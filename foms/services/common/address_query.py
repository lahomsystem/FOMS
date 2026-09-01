"""주소 검색어 전처리 SSOT (GEO-QUERY-01).

지도 화면의 주소 검색 모달(:mod:`foms.api.address`)과 실제 지오코딩 파이프라인
(:class:`foms.services.common.address_converter.FOMSAddressConverter`)이 **같은**
전처리를 쓰도록 한 곳에 모은다.

두 벌로 갈라져 있던 시절의 결함: 동호수 제거 정규식이 모두 앞 공백(``\\s+``)을
요구해서, 공백 없이 붙여 저장된 주소(예: ``오산역금강펜테리움1103-301``)는
후보가 원본 1개뿐이었고 모달 검색도 워커 변환도 똑같이 0건이었다. 여기서는
구분자 공백을 선택적(``\\s*``)으로 만들어 붙여쓴 주소도 동호수를 떼어낸다.

`지번 <https://ko.wikipedia.org/wiki/지번>`_ 오탐을 막기 위해 ``NNN-NNN`` 패턴은
**양쪽 모두 3자리 이상**일 때만 제거한다(``2287-15`` 같은 지번은 보존).
"""
from __future__ import annotations

import re

#: 도로명 + 건물번호까지만 남기는 패턴. 여기서는 공백을 필수로 둔다 — 선택적으로
#: 바꾸면 건물명에 포함된 '로/길' 뒤 숫자를 도로명으로 오인한다.
#:
#: 끝의 부정 전방탐색이 `번길` 절단을 막는다(2026-09-01). 이것이 없으면
#: ``판교로 256번길 25`` 가 ``판교로 256`` 으로 잘리는데 **서로 다른 도로**다. 잘린 값은
#: 카카오에서 좌표가 나오므로 실패가 아니라 **엉뚱한 좌표로 성공**한다 — 지도 핀이 수백
#: m~수 km 어긋난 채 정상으로 보인다(실패보다 나쁘다). 백트래킹으로 ``.*?`` 가 자라
#: ``…번길 25`` 를 통째로 잡는다. ``(?!\d)`` 를 함께 두는 이유: 이것이 없으면 백트래킹이
#: 숫자를 잘라(``123`` → ``12``) 전방탐색을 우회해 더 나쁜 절단을 만든다.
_ROAD_RE = re.compile(r"(.*?(?:대로|로|길)\s+\d+(?:-\d+)?)(?!\d)(?![가-힣]{0,4}길)")

#: "101동 1502호" — 앞 공백 선택적(붙여쓴 주소 대응).
_DONG_HO_RE = re.compile(r"\s*\d+동\s*\d+호?\s*$")

#: "1103-301" 동호수. 양쪽 3자리 이상일 때만(지번 오탐 방지), 앞 공백 선택적.
_NUM_DASH_RE = re.compile(r"\s*\d{3,}-\d{3,}\s*$")

#: "1103호" 처럼 호수만 붙은 꼬리.
_HO_ONLY_RE = re.compile(r"\s*\d+호\s*$")


def strip_detail(query: str) -> str:
    """주소 문자열에서 동호수·상세주소 꼬리를 제거하고 핵심부만 반환한다.

    :param query: 원본 주소/검색어.
    :return: 상세주소가 제거된 문자열(제거할 것이 없으면 입력을 그대로).

    >>> strip_detail("오산역금강펜테리움1103-301")
    '오산역금강펜테리움'
    >>> strip_detail("경기 의왕시 시청로 42 108-1701")
    '경기 의왕시 시청로 42'
    >>> strip_detail("동패동 2287-15")
    '동패동 2287-15'
    >>> strip_detail("경기 성남시 분당구 판교로 256번길 25 (삼평동)")
    '경기 성남시 분당구 판교로 256번길 25'
    """
    if not query:
        return query

    text = query.strip()

    # 1) 쉼표 뒤 상세주소 제거
    if "," in text:
        text = text.split(",")[0].strip()

    # 2) 도로명 + 건물번호까지만
    road_match = _ROAD_RE.match(text)
    if road_match:
        stripped = road_match.group(1).strip()
        if stripped != text:
            return stripped

    # 3) 동호수 꼬리 제거(순차 적용 — "…101동 1502호" 와 "…1103-301" 둘 다 커버)
    for pattern in (_DONG_HO_RE, _NUM_DASH_RE, _HO_ONLY_RE):
        cleaned = pattern.sub("", text).strip()
        if cleaned and cleaned != text:
            return cleaned

    return text


def query_variants(query: str) -> list[str]:
    """검색/지오코딩에 시도할 후보 목록을 우선순위 순으로 반환한다.

    순서: 원본 → 상세주소 제거 → 마지막 토큰 제거 → 공백 제거 변형.

    :param query: 원본 주소/검색어.
    :return: 중복이 제거된 후보 문자열 목록(빈 입력이면 빈 목록).

    >>> query_variants("오산역금강펜테리움1103-301")
    ['오산역금강펜테리움1103-301', '오산역금강펜테리움']
    """
    seen: set[str] = set()
    variants: list[str] = []

    def add(value: str) -> None:
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            variants.append(value)

    add(query)
    stripped = strip_detail(query or "")
    add(stripped)

    # 마지막 토큰(단지명 일부·동호수 잔재) 제거 버전
    tokens = stripped.split()
    if len(tokens) >= 2:
        add(" ".join(tokens[:-1]))

    # 공백 제거 (한글 건물명 붙여쓰기 대응)
    add(re.sub(r"\s+", "", query or ""))
    add(re.sub(r"\s+", "", stripped))

    return variants
