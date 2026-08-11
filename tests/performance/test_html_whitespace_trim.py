"""HTML 줄 앞 들여쓰기 트림 계약 (전송량·압축 CPU 절감).

렌더 결과가 바뀌면 안 되는 곳(``pre``/``textarea``/``script``/``style``)은 바이트
단위로 보존하고, 그 밖의 들여쓰기만 사라져야 한다. 줄바꿈은 남긴다 — 인라인
요소 사이 공백 역할을 계속해야 "가</span> <span>나"가 붙어 보이지 않는다.
"""

from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common.html_whitespace import (
    MIN_TRIM_BYTES,
    trim_html_indentation,
)
from models import User


def _login_erp_admin(client):
    """ERP 화면 응답을 받기 위한 최소 ADMIN 세션."""
    user = User(
        username="ws_trim_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="WS Trim Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def test_indentation_removed_outside_protected_regions():
    """줄 앞 공백/탭은 사라지고 줄바꿈은 남는다."""
    body = b"<div>\n    <span>A</span>\n\t<span>B</span>\n</div>"
    assert trim_html_indentation(body) == b"<div>\n<span>A</span>\n<span>B</span>\n</div>"


def test_inline_spacing_survives_as_newline():
    """인라인 요소 사이 간격은 줄바꿈으로 유지된다(붙어 보이면 회귀)."""
    out = trim_html_indentation("<p>\n  <b>가</b>\n  <b>나</b>\n</p>".encode())
    assert b"</b>\n<b>" in out


def test_pre_and_textarea_bytes_are_untouched():
    """공백이 렌더되는 영역은 원문 그대로."""
    body = (
        b"<div>\n    <pre>\n    keep   this\n      indent\n</pre>\n"
        b"    <textarea>\n      raw  text\n</textarea>\n</div>"
    )
    out = trim_html_indentation(body)
    assert b"<pre>\n    keep   this\n      indent\n</pre>" in out
    assert b"<textarea>\n      raw  text\n</textarea>" in out
    assert b"<div>\n<pre>" in out  # 보호 구역 밖은 트림됨


def test_script_and_style_bodies_are_untouched():
    """여러 줄 템플릿 리터럴 등 들여쓰기가 출력에 섞이는 코드를 보호한다."""
    body = (
        b"<div>\n    <script>\n      const t = `\n        <li>x</li>\n      `;\n    </script>\n"
        b"    <style>\n      .a { color: red; }\n    </style>\n</div>"
    )
    out = trim_html_indentation(body)
    assert b"<script>\n      const t = `\n        <li>x</li>\n      `;\n    </script>" in out
    assert b"<style>\n      .a { color: red; }\n    </style>" in out


def test_multiple_protected_regions_keep_order_and_content():
    """보호 구역이 여러 개여도 순서·내용이 보존된다."""
    body = b"\n  <script>a</script>\n  <p>\n    x\n  </p>\n  <script>b</script>\n"
    out = trim_html_indentation(body)
    assert out == b"\n<script>a</script>\n<p>\nx\n</p>\n<script>b</script>\n"


def test_unclosed_protected_tag_falls_back_to_original_tail():
    """닫는 태그가 없으면 남은 구간을 손대지 않는다(안전 측 폴백)."""
    body = b"<div>\n  <script>\n    never closed\n"
    out = trim_html_indentation(body)
    assert out.endswith(b"<script>\n    never closed\n")


def test_dashboard_response_has_no_leading_indentation(client):
    """실제 응답에서 보호 구역 밖 들여쓰기가 사라진다(훅 배선 계약)."""
    _login_erp_admin(client)
    response = client.get("/erp/dashboard")
    assert response.status_code == 200
    body = response.get_data()
    assert len(body) > MIN_TRIM_BYTES
    stripped = re.sub(
        rb"<(pre|textarea|script|style)\b[^>]*>.*?</\1\s*>", b"", body, flags=re.S | re.I
    )
    assert not re.search(rb"\n[ \t]+", stripped)
