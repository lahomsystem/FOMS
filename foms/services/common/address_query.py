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


#: 시/도 접두 — 긴 표기부터 본다(``서울특별시`` 를 ``서울`` 로 먼저 자르면 ``특별시`` 가 남는다).
#: 사람이 ERP 에 입력한 주소는 시/도를 통째로 생략하는 일이 흔하고(운영 180일 주문 2289건 중
#: 646건), 네이버는 ``baseAddress`` 에 늘 공식 전체 표기를 준다. 두 계보를 견주려면
#: 이 층을 양쪽에서 걷어내야 한다.
_SIDO_PREFIXES: tuple[str, ...] = (
    "서울특별시", "서울시", "서울",
    "부산광역시", "부산시", "부산",
    "대구광역시", "대구시", "대구",
    "인천광역시", "인천시", "인천",
    "광주광역시", "광주시", "광주",
    "대전광역시", "대전시", "대전",
    "울산광역시", "울산시", "울산",
    "세종특별자치시", "세종시", "세종",
    "경기도", "경기",
    "강원특별자치도", "강원도", "강원",
    "충청북도", "충북", "충청남도", "충남",
    "전북특별자치도", "전라북도", "전북", "전라남도", "전남",
    "경상북도", "경북", "경상남도", "경남",
    "제주특별자치도", "제주도", "제주",
)

#: 공백 없이 붙여 쓴 주소에서도 잘라도 되는 **공식 전체 표기** 꼬리. ``서울시`` 는 여기
#: 없다 — ``서울시청로`` 처럼 낱말 한가운데를 자를 수 있어 공백이 있을 때만 자른다.
_SIDO_FULL_SUFFIXES: tuple[str, ...] = ("특별시", "광역시", "특별자치시", "특별자치도", "도")

#: 괄호부(``(석관동, 두산아파트)``) — 네이버 도로명 주소가 법정동·건물명을 여기에 담는다.
#: 안에 쉼표가 들어 있어 ``strip_detail`` 의 쉼표 절단보다 **먼저** 걷어내야 한다.
_PAREN_RE = re.compile(r"\([^)]*\)")

#: 닫히지 않은 괄호 꼬리(수집 원문이 잘려 온 경우).
_OPEN_PAREN_TAIL_RE = re.compile(r"\(.*$")

#: 매칭 키에 남길 문자 — 한글·영숫자만. 공백·쉼표·하이픈 표기 차이를 흡수한다.
_KEY_NOISE_RE = re.compile(r"[^0-9A-Za-z가-힣]")

#: 매칭 키 최소 길이. 이보다 짧으면 ``성북구`` 같은 행정구역 한 층이라 사람을 특정하지 못한다.
MATCH_KEY_MIN_LEN = 6


def strip_sido(address: str) -> str:
    """주소 앞의 시/도 표기를 걷어낸다(없으면 입력 그대로).

    :param address: 주소 문자열.
    :return: 시/도 접두가 제거된 문자열.

    >>> strip_sido("서울특별시 성북구 화랑로48길 16")
    '성북구 화랑로48길 16'
    >>> strip_sido("성북구 화랑로48길 16")
    '성북구 화랑로48길 16'
    """
    text = (address or "").strip()
    for sido in _SIDO_PREFIXES:
        if not text.startswith(sido):
            continue
        tail = text[len(sido):]
        # 공백이 뒤따르면 확실한 시/도 층이다. 공백이 없으면 ``서울시청로`` 처럼 낱말
        # 한가운데를 자를 수 있으므로, 접두가 **공식 전체 표기**(``서울특별시``·``경기도``)
        # 일 때만 붙여쓴 주소로 보고 자른다.
        if tail[:1].isspace():
            return tail.lstrip()
        if tail and sido.endswith(_SIDO_FULL_SUFFIXES):
            return tail
    return text


def match_key(address: str) -> str:
    """두 계보의 주소를 견줄 수 있게 **매칭 키** 하나로 접는다 (NAVER-MATCH-01).

    네이버가 주는 공식 전체 주소(``서울특별시 성북구 화랑로48길 16 (석관동, 두산아파트)
    110동 2403호``)와 사람이 ERP 에 친 축약형(``성북구 화랑로48길 16, 두산아파트 110동
    2403호``)은 **같은 집인데 글자가 다르다**. 앞부분 몇 글자를 그대로 견주면
    (구 구현: 앞 10자 ``startswith``) 시/도 한 층 차이로 통째로 어긋난다 — 운영 링크
    243건 대조에서 수령인명이 정확히 맞는 224건 중 119건만 통과했다.

    접는 순서: 괄호부 제거 → 시/도 제거 → :func:`strip_detail`(쉼표 뒤·도로명+건물번호
    ·동호수) → 한글/영숫자만 남기기.

    :param address: 주소 문자열(네이버 원문이든 ERP 입력이든).
    :return: 매칭 키. 키가 :data:`MATCH_KEY_MIN_LEN` 미만이거나 숫자(건물번호·지번)가
        없으면 **빈 문자열** — 행정구역 한 층만 남은 키로 견주면 남남이 같은 집이 된다.

    >>> match_key("서울특별시 성북구 화랑로48길 16 (석관동, 두산아파트) 110동 2403호")
    '성북구화랑로48길16'
    >>> match_key("성북구 화랑로48길 16, 두산아파트 110동 2403호")
    '성북구화랑로48길16'
    >>> match_key("서울 성북구")
    ''
    """
    text = (address or "").strip()
    if not text:
        return ""
    text = _PAREN_RE.sub(" ", text)
    text = _OPEN_PAREN_TAIL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = strip_sido(text)
    text = strip_detail(text)
    key = _KEY_NOISE_RE.sub("", text)
    if len(key) < MATCH_KEY_MIN_LEN:
        return ""
    if not any(ch.isdigit() for ch in key):
        return ""
    return key
