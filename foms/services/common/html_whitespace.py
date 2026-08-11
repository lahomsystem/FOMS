"""HTML 응답의 줄 앞 들여쓰기 제거 (전송량·압축 CPU 절감).

Jinja 템플릿이 겹겹이 중첩되면서 줄마다 8~20칸 공백이 붙고, 그게 그대로
전송된다. HTML 은 연속 공백을 한 칸으로 접으므로 **줄바꿈만 남기면 렌더는
동일**하다(줄바꿈 자체가 인라인 요소 사이 공백 역할을 계속한다).

2026-08-11 스테이징 실측(프래그먼트 raw 기준):

    /erp/dashboard              599,098B 중 232,680B (38%)
    /erp/production/dashboard   807,786B 중 240,325B (29%)
    /erp/construction/dashboard 974,719B 중 218,043B (22%)

CPU 도 이득이다 — 시공 프래그먼트 1.3MB 기준 트림 5.6ms 를 쓰고 gzip 이
26ms → 15ms 로 줄어 순감이다(측정: 로컬 CPython 3.12).

``<pre>``·``<textarea>``·``<script>``·``<style>`` 안은 손대지 않는다. 앞의 둘은
공백이 그대로 렌더되고, 뒤의 둘은 여러 줄 템플릿 리터럴처럼 들여쓰기가 출력에
섞이는 코드가 있을 수 있다. 이 보호로 잃는 절감은 위 실측에서 전체의 2% 미만이다.
"""
from __future__ import annotations

import re
from typing import Final

from flask import Flask, Response

# 보호 구역 여는 태그. 닫는 위치는 bytes.find 로 찾는다 — DOTALL 정규식으로
# 1MB 를 역추적 스캔하면 트림 자체보다 비싸진다(측정 4.1ms → 1.5ms).
_OPEN_TAG_RE: Final = re.compile(rb'<(pre|textarea|script|style)\b', re.I)
_INDENT_RE: Final = re.compile(rb'\n[ \t]+')

# 트림을 시도할 최소 크기(B). 작은 응답은 절감이 잡음 수준이라 CPU 만 쓴다.
MIN_TRIM_BYTES: Final = 4096


def trim_html_indentation(body: bytes) -> bytes:
    """줄 앞 들여쓰기만 제거한 HTML 바이트를 돌려준다(보호 구역은 원문 유지).

    Args:
        body: 원본 HTML 바이트.

    Returns:
        줄바꿈은 유지하고 그 뒤 공백/탭만 제거한 바이트. 보호 구역
        (``pre``/``textarea``/``script``/``style``) 내부는 바이트 단위로 동일하다.
    """
    out = bytearray()
    pos = 0
    for match in _OPEN_TAG_RE.finditer(body):
        start = match.start()
        if start < pos:
            continue  # 앞선 보호 구역 내부 — 이미 원문으로 복사됐다
        tag = match.group(1).lower()
        close = body.find(b'</' + tag, match.end())
        if close == -1:
            # 닫는 태그가 없다(잘린 응답 등) → 남은 전부를 원문 그대로 둔다.
            # 열린 script/style 안을 트림하면 코드가 바뀔 수 있어 안전 측으로 뺀다.
            out += _INDENT_RE.sub(b'\n', body[pos:start])
            out += body[start:]
            return bytes(out)
        close = body.find(b'>', close)
        end = len(body) if close == -1 else close + 1
        out += _INDENT_RE.sub(b'\n', body[pos:start])
        out += body[start:end]
        pos = end
    out += _INDENT_RE.sub(b'\n', body[pos:])
    return bytes(out)


def _should_trim(response: Response) -> bool:
    """트림 대상 응답인지 판정 (HTML 200 + 본문 보유 + 미압축)."""
    if response.status_code != 200:
        return False
    if response.direct_passthrough:  # send_file 등 스트리밍
        return False
    if response.headers.get('Content-Encoding'):
        return False
    return (response.headers.get('Content-Type') or '').startswith('text/html')


def install_html_indentation_trimmer(app: Flask) -> None:
    """HTML 들여쓰기 트림 after_request 훅을 앱에 배선한다.

    Flask 는 after_request 를 등록 역순으로 실행하므로 ``Compress(app)`` 뒤에
    등록하면 **압축보다 먼저** 돈다(압축 대상 바이트가 이미 줄어든 상태).

    Args:
        app: 대상 Flask 앱.
    """

    @app.after_request
    def _trim_html_indentation(response: Response) -> Response:  # noqa: ANN202 - Flask 훅
        if not _should_trim(response):
            return response
        body = response.get_data()
        if len(body) < MIN_TRIM_BYTES:
            return response
        trimmed = trim_html_indentation(body)
        if len(trimmed) != len(body):
            response.set_data(trimmed)
        return response
