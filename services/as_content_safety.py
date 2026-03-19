"""AS 내용 sanitize + structured_data 무손실 로드 유틸."""

from __future__ import annotations

import copy
import json
import re

from bs4 import BeautifulSoup, Comment


_ALLOWED_RICH_TAGS = {
    'b', 'strong', 'i', 'em', 'u', 's',
    'br', 'div', 'p', 'span', 'font',
    'ul', 'ol', 'li',
}

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


def _normalize_color(value):
    if value is None:
        return None
    normalized = re.sub(r'\s+', '', str(value).strip().lower())
    return _COLOR_ALIASES.get(normalized)


def _extract_style_color(style_value):
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


def sanitize_as_content_html(value):
    """AS 내용 rich HTML을 최소 허용 포맷만 남기고 정리."""
    raw_html = '' if value is None else str(value)
    if not raw_html.strip():
        return ''

    soup = BeautifulSoup(raw_html, 'html.parser')
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
    return ''.join(str(child) for child in root.contents).strip()


def as_content_html_to_text(value):
    """출고 대시보드용 AS 내용 plain text 요약."""
    sanitized = sanitize_as_content_html(value)
    if not sanitized:
        return ''

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


def load_structured_data_dict_or_raise(raw_value):
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
