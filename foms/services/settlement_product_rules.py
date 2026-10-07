"""정산 "제품별 매출" 탭의 품목 분류 규칙 — 품명 원문 → 제품군(family)·시리즈(series).

품목(``structured_data.items[].product_name``)은 영업이 손으로 적는 자유 문자열이다. 이 모듈은
그 문자열을 화면이 묶어 보여 줄 제품군·시리즈 코드로 바꾼다. 규칙은 운영 데이터(2026-10-07
ERP 품목 전량)로 검증한 정본(``settle-prod-rules-reference.py``)을 **순서·낱말 그대로** 옮긴
것이다. 규칙을 고칠 때는 아래 순서의 이유를 먼저 읽어라 — 순서가 곧 판정이다.

정규화:

- :func:`normalize_name` — NFC 정규화 + 공백 전부 제거 + 소문자. 띄어쓰기 변형("무몰딩 붙박이장"·
  "무몰딩붙박이장")을 같은 이름으로 본다.
- ``_core`` — 치수(``120cm``·``3.5m``)와 맨 끝 괄호 하나를 지운 몸통. 낱말 판정은 대부분 몸통으로
  한다(괄호 안 메모가 제품군을 바꾸지 않게).

제품군 판정 순서와 이유:

1. **미입력** — 빈 이름·"발주방 등록 전"·"외 N건" 은 품목이 아니라 자리표시다.
2. **비용 품목 먼저**(철거·배송·양중·할인 …) — "붙박이장 철거"처럼 제품 낱말이 같이 있어도
   돈의 성격은 부대비용이다. 제품 판정보다 앞서야 제품 매출이 부풀지 않는다.
3. **냉장고 리폼은 원문으로 판정** — 리폼 표시는 대개 맨 끝 괄호("냉장고장(리폼)")에 있어 몸통에서
   지워진다. 그래서 '냉장고'는 몸통, '리폼'은 원문(정규화본)에서 찾는다.
4. 부엌·신발장·홈카페·TV월·행거 — 고유 낱말이 있는 제품군.
5. **도어는 좁은 규칙** — '도어'는 "투도어 붙박이장"처럼 붙박이장 이름 안에도 흔히 들어간다.
   공틀이거나, 교체·설치이거나, 도어로 시작·끝나거나, "도어+"·"도어2장" 일 때만 도어로 본다.
6. **수납장류는 옷장 낱말이 없을 때만** — "시스템 붙박이장"·"서랍 옷장"은 옷장이다. 옷장 낱말이
   하나도 없고 수납 낱말이 있을 때만 수납장으로 보고, 끝이 '슬라이딩'이면 슬라이딩 옷장이다.
7. 슬라이딩(미닫이) — 여닫이 판정보다 먼저 본다.
8. **무몰딩을 몰딩보다 먼저** — '무몰딩' 안에 '몰딩'이 들어 있어 순서를 바꾸면 무몰딩이 전부
   몰딩으로 간다.
9. 옷장 낱말만 있는 여닫이 → 기본 여닫이. 그 밖의 '추가' 는 부대비용, 시리즈+숫자 모델명
   (스와니·루나·모카)은 슬라이딩, "…장" 으로 끝나는 이름은 기본 여닫이, 나머지는 기타.

시리즈는 원문(NFC)에서 :data:`SERIES_RULES` 순서대로 첫 일치를 고른다. 'LED' 만 대소문자를
가리지 않는다. 어느 것도 아니면 :data:`SERIES_BASIC` 이다.

이 모듈은 순수 함수만 둔다 — DB·Flask 를 import 하지 않는다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

__all__ = [
    "FAMILIES",
    "FAMILY_CODES",
    "SERIES",
    "SERIES_BASIC",
    "SERIES_CODES",
    "SERIES_RULES",
    "family",
    "normalize_name",
    "series",
]

#: 제품군 (코드, 화면 라벨) — **이 순서가 화면 표시 순서**다.
FAMILIES: tuple[tuple[str, str], ...] = (
    ("NOMOLD_SWING", "무몰딩 여닫이"),
    ("MOLD_SWING", "몰딩 여닫이"),
    ("SWING", "여닫이 붙박이장(기본)"),
    ("SLIDING", "슬라이딩 붙박이장"),
    ("KITCHEN", "부엌가구"),
    ("REFRIG", "냉장고장"),
    ("REFRIG_REFORM", "냉장고장 리폼"),
    ("TV_WALL", "TV월플렉스"),
    ("HOMECAFE", "홈카페·홈바장"),
    ("SHOE", "신발장·현관장"),
    ("HANGER", "시스템행거"),
    ("STORAGE", "수납장·책장·기타 맞춤장"),
    ("DOOR", "도어·공틀"),
    ("EXTRA", "철거·부대비용"),
    ("PLACEHOLDER", "미입력"),
    ("OTHER", "기타"),
)
FAMILY_CODES: tuple[str, ...] = tuple(code for code, _ in FAMILIES)

#: 시리즈 (코드, 화면 라벨, 찾는 낱말들) — **앞에서부터 첫 일치**가 이긴다.
SERIES_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("LORA", "로라", ("로라",)),
    ("BOTTEGA", "보테가", ("보테가",)),
    ("LUNA", "루나", ("루나",)),
    ("HABAN", "하반", ("하반",)),
    ("MONTA", "몬타", ("몬타",)),
    ("IRIS", "이리스", ("이리스",)),
    ("MONET", "모네", ("모네",)),
    ("LIRA", "리라·린다", ("리라", "린다")),
    ("HAUD", "하우드", ("하우드",)),
    ("MOCHA", "모카", ("모카",)),
    ("JENA", "제나", ("제나",)),
    ("MAGAZINE", "매거진", ("매거진",)),
    ("SWANY", "스와니", ("스와니",)),
    ("VANILLA", "바닐라", ("바닐라",)),
    ("ARA", "아라", ("아라",)),
    ("PRIMO", "프리모", ("프리모",)),
    ("CONVERTIBLE", "컨버터블", ("컨버터블",)),
    ("LUMI", "루미", ("루미",)),
    ("WINDOW", "윈도우 맞춤", ("윈도우",)),
    ("ROUND", "라운드", ("라운드",)),
    ("LED", "LED", ("LED",)),
)
#: 어느 시리즈에도 안 걸린 품목(시리즈 이름이 없는 기본 제품).
SERIES_BASIC = "BASIC"
_SERIES_BASIC_LABEL = "기본"
#: 시리즈 (코드, 라벨) — 규칙 순서 전부 + 기본이 마지막. 화면 표시 순서다.
SERIES: tuple[tuple[str, str], ...] = (
    *((code, label) for code, label, _ in SERIES_RULES),
    (SERIES_BASIC, _SERIES_BASIC_LABEL),
)
SERIES_CODES: tuple[str, ...] = tuple(code for code, _ in SERIES)

#: 옷장(붙박이장) 낱말 — 하나라도 있으면 수납장으로 보지 않는다.
_WARDROBE_WORDS = ("붙박이", "여닫이", "적층장", "침대", "자녀방", "드레스룸", "옷장", "벽박이")
#: 수납장·책장·기타 맞춤장 낱말.
_STORAGE_WORDS = (
    "수납", "파우더", "화장대", "책장", "미드웨이", "시스템", "베란다장", "선반", "팬트리", "펜트리",
    "틈새장", "장식장", "서랍", "상부장", "하부장", "책상", "사선장", "하프장", "복도장", "다용도",
    "유리도어장", "벤치", "체스트",
)
#: 비용 품목 낱말 — 제품 낱말보다 먼저 본다.
_FEE_WORDS = (
    "철거", "배송", "운반", "양중", "출장", "설치비", "폐기", "추가금", "할인",
    "권역", "운임", "도로비", "공임", "부자재", "이전설치", "이전시공", "해체시공", "재시공", "보양",
)
_KITCHEN_WORDS = ("부엌", "주방", "상하부장", "아일랜드", "싱크")

_WHITESPACE_RE = re.compile(r"\s+")
#: 치수 표기(숫자+단위). 뒤에 영문자가 이어지면 단위가 아니다("3mmx" 같은 모델명 보호).
_SIZE_RE = re.compile(r"\d+(\.\d+)?(cm|mm|m)(?![a-z])")
#: 맨 끝 괄호 하나(중첩 없는 것).
_TRAILING_PAREN_RE = re.compile(r"\([^()]*\)$")
#: "외", "외3", "외 3건" 같은 자리표시(정규화 뒤라 공백이 없다).
_PLACEHOLDER_OTHERS_RE = re.compile(r"외\d*(건)?")
#: 시리즈 모델명 + 숫자(스와니1200 등) — 슬라이딩 시리즈다.
_SLIDING_MODEL_RE = re.compile(r"(스와니|루나|모카)\d")
#: "…장" 으로 끝나거나 "장외"·"장3" 처럼 이어지는 이름.
_CABINET_SUFFIX_RE = re.compile(r"장(외|\d|$)")


def normalize_name(name: Any) -> str:
    """품명 원문 → 판정용 정규화본(NFC + 공백 전부 제거 + 소문자).

    Args:
        name: 품명 원문(None·숫자도 받는다).

    Returns:
        정규화한 문자열(없으면 빈 문자열).
    """
    return _WHITESPACE_RE.sub("", unicodedata.normalize("NFC", str(name or ""))).lower()


def _core(normalized: str) -> str:
    """정규화본에서 치수와 맨 끝 괄호를 지운 몸통."""
    body = _SIZE_RE.sub("", normalized)
    return _TRAILING_PAREN_RE.sub("", body)


def _is_door(body: str) -> bool:
    """도어·공틀 판정(좁은 규칙 — 모듈 docstring 5번)."""
    if "공틀" in body:
        return True
    if "도어" not in body:
        return False
    return ("교체" in body or "설치" in body or body.endswith("도어")
            or body.startswith("도어") or "도어+" in body or "도어2장" in body)


def family(name: Any) -> str:
    """품명 원문 → 제품군 코드(:data:`FAMILY_CODES` 중 하나).

    판정 순서는 모듈 docstring 의 1~9번이다. 순서를 바꾸면 판정이 바뀐다.

    Args:
        name: 품명 원문.

    Returns:
        제품군 코드.
    """
    full = normalize_name(name)
    body = _core(full)
    if not full or "발주방등록전" in full or _PLACEHOLDER_OTHERS_RE.fullmatch(full):
        return "PLACEHOLDER"
    if any(word in body for word in _FEE_WORDS):
        return "EXTRA"
    # 리폼 표시는 맨 끝 괄호에 있어 몸통에서 지워진다 — 원문(정규화본)으로 본다.
    if "냉장고" in body and "리폼" in full:
        return "REFRIG_REFORM"
    if "냉장고" in body:
        return "REFRIG"
    if any(word in body for word in _KITCHEN_WORDS):
        return "KITCHEN"
    if "신발장" in body or "현관" in body:
        return "SHOE"
    if "홈카페" in body or "홈바" in body:
        return "HOMECAFE"
    if "tv월" in body or "월플렉스" in body:
        return "TV_WALL"
    if "행거" in body:
        return "HANGER"
    if _is_door(body):
        return "DOOR"
    if (not any(word in body for word in _WARDROBE_WORDS)
            and any(word in body for word in _STORAGE_WORDS)
            and not body.endswith("슬라이딩")):
        return "STORAGE"
    if "슬라이딩" in body or "미닫이" in body or "슬라이드" in body:
        return "SLIDING"
    # '무몰딩' 안에 '몰딩'이 들어 있다 — 무몰딩을 먼저 본다.
    if "무몰딩" in body:
        return "NOMOLD_SWING"
    if "몰딩" in body:
        return "MOLD_SWING"
    if any(word in body for word in _WARDROBE_WORDS):
        return "SWING"
    if "추가" in body:
        return "EXTRA"
    if _SLIDING_MODEL_RE.match(body):
        return "SLIDING"
    if _CABINET_SUFFIX_RE.search(body):
        return "SWING"
    return "OTHER"


def series(name: Any) -> str:
    """품명 원문 → 시리즈 코드(:data:`SERIES_CODES` 중 하나).

    원문(NFC)에서 :data:`SERIES_RULES` 순서대로 첫 일치를 고른다. 'LED' 만 대소문자를 가리지
    않는다(영문 표기가 섞여 들어온다).

    Args:
        name: 품명 원문.

    Returns:
        시리즈 코드. 어느 것도 아니면 :data:`SERIES_BASIC`.
    """
    raw = unicodedata.normalize("NFC", str(name or ""))
    upper = raw.upper()
    for code, _label, words in SERIES_RULES:
        if any((word in upper) if word == "LED" else (word in raw) for word in words):
            return code
    return SERIES_BASIC
