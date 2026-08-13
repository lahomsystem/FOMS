"""AS 내용 sanitize + structured_data 무손실 로드 유틸."""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from typing import Any

from bs4 import BeautifulSoup, Comment

# sanitize 메모이제이션 한도. 4096칸 × 입력 8KB 상한 = 최악 수십 MB 이내로 묶인다.
_SANITIZE_CACHE_SIZE = 4096
_SANITIZE_CACHE_MAX_INPUT = 8192

__all__ = [
    "sanitize_as_content_html",
    "as_content_html_to_text",
    "combined_as_content_text",
    "load_structured_data_dict_or_raise",
]

_ALLOWED_RICH_TAGS = {
    'b', 'strong', 'i', 'em', 'u', 's',
    'br', 'div', 'p', 'span', 'font',
    'ul', 'ol', 'li',
}

# 뒤에 `>`가 하나도 없는 `<` = 끝까지 닫히지 않는 조각.
# ponytail: `<div title="a>b` 처럼 따옴표 안의 `>`로 위장한 미종결 태그는 이 규칙이 못 잡는다.
# 실입력(사용자가 친 `<`, 잘린 붙여넣기)은 전부 커버되며, 완전 커버는 토크나이저가 필요하다.
_DANGLING_LT_RE = re.compile(r'<(?=[^>]*$)')

_COLOR_ALIASES = {
    'red': 'red',
    '#ff0000': 'red',
    'rgb(255,0,0)': 'red',
    'rgb(255,0,0,1)': 'red',
    'blue': 'blue',
    '#0000ff': 'blue',
    'rgb(0,0,255)': 'blue',
    'rgb(0,0,255,1)': 'blue',
    'black': 'black',
    '#000000': 'black',
    'rgb(0,0,0)': 'black',
    'rgb(0,0,0,1)': 'black',
}


def _normalize_color(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r'\s+', '', str(value).strip().lower())
    return _COLOR_ALIASES.get(normalized)


def _extract_style_color(style_value: Any) -> str | None:
    if not style_value:
        return None
    for declaration in str(style_value).split(';'):
        if ':' not in declaration:
            continue
        name, raw_value = declaration.split(':', 1)
        if name.strip().lower() != 'color':
            continue
        color = _normalize_color(raw_value)
        if color:
            return color
    return None


def sanitize_as_content_html(value: Any) -> str:
    """AS 내용 rich HTML을 최소 허용 포맷만 남기고 정리.

    같은 입력 문자열은 항상 같은 결과를 내는 순수 함수라 프로세스 로컬 LRU로
    메모이즈한다(:func:`_sanitize_as_content_html_cached`). AS 대시보드는 한 요청에
    행 100개 × 2필드를 정리하는데 저장된 내용은 거의 안 바뀌므로, 웜 상태에서
    BeautifulSoup 파싱이 사실상 사라진다(2026-08-13 스테이징 실측 rd_sanitize 18ms).
    """
    raw_html = '' if value is None else str(value)
    if not raw_html.strip():
        return ''
    if len(raw_html) <= _SANITIZE_CACHE_MAX_INPUT:
        return _sanitize_as_content_html_cached(raw_html)
    # 비정상적으로 큰 입력은 캐시에 담지 않는다 — LRU 4096칸이 메모리를 삼키지 않게.
    return _sanitize_as_content_html_uncached(raw_html)


def _sanitize_as_content_html_uncached(raw_html: str) -> str:
    """sanitize 본체(캐시 없음). ``raw_html`` 은 비어있지 않은 문자열."""
    # html.parser의 EOF 미종결 태그 처리는 Python 패치 버전마다 다르다
    # (3.12.10=데이터로 유지 / 3.12.13=태그로 취급 → 허용 태그가 아니면 통째 소실 = 사용자 텍스트 유실).
    # 파서에 넘기기 전에 닫히지 않는 `<` 조각을 이스케이프해 런타임 무관 동일 입력을 만든다.
    soup = BeautifulSoup(_DANGLING_LT_RE.sub('&lt;', raw_html), 'html.parser')
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in list(soup.find_all(True)):
        name = (tag.name or '').lower()
        if name not in _ALLOWED_RICH_TAGS:
            if tag.contents:
                tag.unwrap()
            else:
                tag.decompose()
            continue

        if name == 'font':
            color = _normalize_color(tag.get('color')) or _extract_style_color(tag.get('style'))
            tag.attrs = {}
            if color:
                tag['color'] = color
            else:
                tag.unwrap()
            continue

        if name == 'span':
            color = _extract_style_color(tag.get('style')) or _normalize_color(tag.get('color'))
            tag.attrs = {}
            if color:
                tag['style'] = f'color: {color};'
            else:
                tag.unwrap()
            continue

        tag.attrs = {}

    root = soup.body or soup
    # decode_contents()는 minimal formatter로 텍스트 노드의 `<`/`&`를 이스케이프한다.
    # str(child) 조합은 top-level NavigableString을 원문 그대로 흘려 미종결 태그
    # (`hi <img src=x onerror=...`)가 살아남았고, 렌더 측 |safe + 뒤따르는 마크업이
    # 태그를 완성해 실행됐다. 허용 태그는 이미 attrs가 정리된 Tag라 그대로 보존된다.
    return root.decode_contents().strip()


@lru_cache(maxsize=_SANITIZE_CACHE_SIZE)
def _sanitize_as_content_html_cached(raw_html: str) -> str:
    """LRU 메모이즈된 sanitize. 순수 함수라 프로세스 로컬 캐시가 안전하다."""
    return _sanitize_as_content_html_uncached(raw_html)


def as_content_html_to_text(value: Any, *, already_sanitized: bool = False) -> str:
    """AS 내용 rich HTML → plain text 요약(블록·`<br>` 경계를 개행으로 보존).

    Args:
        value: AS 내용 HTML(원본 또는 이미 sanitize를 통과한 값).
        already_sanitized: True면 sanitize 단계를 건너뛴다. as_log 항목 `text`처럼
            저장 시점에 이미 sanitize된 값을 대시보드 행 루프에서 다시 파싱하지 않기
            위한 경로다(행당 BeautifulSoup 파싱 2회 → 1회).

    Returns:
        공백이 정규화된 plain text. 내용이 없으면 빈 문자열.
    """
    sanitized = str(value or '') if already_sanitized else sanitize_as_content_html(value)
    if not sanitized:
        return ''

    if already_sanitized and '<' not in sanitized and '&' not in sanitized:
        # quick-add 로 쌓이는 기록 대부분은 태그도 엔티티도 없는 평문이다. 파싱해도
        # get_text()가 입력을 그대로 돌려주므로 BeautifulSoup 자체를 건너뛴다.
        # 이미 sanitize된 값에서만 안전하다 — 원본은 `<`가 없어도 이스케이프 대상일 수 있다.
        raw_text = sanitized
    else:
        soup = BeautifulSoup(sanitized, 'html.parser')
        for br in soup.find_all('br'):
            br.replace_with('\n')
        for tag_name in ('div', 'p', 'li'):
            for tag in soup.find_all(tag_name):
                tag.insert_after('\n')
        raw_text = soup.get_text('', strip=False)

    lines = []
    for line in raw_text.splitlines():
        normalized = re.sub(r'\s+', ' ', line).strip()
        if normalized:
            lines.append(normalized)
    return '\n'.join(lines)


def combined_as_content_text(
    structured_data: dict[str, Any] | None,
    *,
    notes_fallback: str = "",
) -> str:
    """AS 탭1·탭2(+ notes 폴백) plain text — 출고·완료 대시보드 공통 SSOT."""
    sd = structured_data if isinstance(structured_data, dict) else {}
    shipment = sd.get("shipment") or {}
    if not isinstance(shipment, dict):
        return ""

    parts = [as_content_html_to_text(shipment.get("as_content"))]
    if "as_content_2" in shipment:
        parts.append(as_content_html_to_text(shipment.get("as_content_2")))
    elif notes_fallback:
        parts.append(as_content_html_to_text(notes_fallback))
    return "\n\n".join(part for part in parts if part)


def load_structured_data_dict_or_raise(raw_value: Any) -> dict[str, Any]:
    """기존 structured_data를 무손실로 dict로 로드. 불가하면 예외."""
    if raw_value is None:
        return {}
    if isinstance(raw_value, dict):
        return copy.deepcopy(raw_value)
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return {}
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError('structured_data가 객체(JSON dict)가 아닙니다.')
    raise ValueError(f'structured_data 형식이 지원되지 않습니다: {type(raw_value).__name__}')
