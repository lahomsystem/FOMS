"""STORED-XSS-01 — 저장형/DOM XSS sink 일괄 봉쇄 회귀 가드.

P0-19/P0-20/P0-21/P0-23: 저장/조회된 신뢰 불가 데이터(SecurityLog.message 내 공개
username, Order.options, 자기수정 User.name, 현재 Order.customer_name)가 raw
HTML/JS sink(`|safe`, `<br>` 주입, template-literal innerHTML, inline onclick)로
흘러 실행되던 경로를 출력 인코딩으로 봉쇄한다.

이 테스트는 (1) 취약 패턴을 정적으로 금지(red→green: 수정 전 존재하던 패턴이면 실패)
하고 (2) hostile 입력이 실제로 중화됨을 증명하며 (3) 정상 기능(주문 링크·줄바꿈·
이름 표시)이 유지됨을 확인한다. sink manifest 100% 열거도 함께 검증한다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

TEMPLATES = ROOT / "templates"
STATIC_JS = ROOT / "static" / "js"

SECURITY_LOGS = TEMPLATES / "admin" / "security_logs.html"
ORDERS_INDEX = TEMPLATES / "orders" / "index.html"
CHANGE_LOGS = TEMPLATES / "admin" / "change_logs.html"
WORKBENCH_BODY = TEMPLATES / "drawing" / "partials" / "workbench_detail_body.html"
LISTING_PY = ROOT / "foms" / "web" / "orders" / "listing.py"

# P0-21 checkbox-list sink 파일(User.name/team → innerHTML 이었던 곳)
USER_LIST_FILES = [
    STATIC_JS / "drawing" / "workbench-dashboard.js",
    STATIC_JS / "orders" / "dashboard" / "erp-dashboard-drawing.js",
    STATIC_JS / "orders" / "dashboard" / "erp-dashboard-detail-dom.js",
    WORKBENCH_BODY,
]
MODIFIED_STANDALONE_JS = [
    STATIC_JS / "drawing" / "workbench-dashboard.js",
    STATIC_JS / "orders" / "dashboard" / "erp-dashboard-drawing.js",
    STATIC_JS / "orders" / "dashboard" / "erp-dashboard-detail-dom.js",
]

HOSTILE_PAYLOADS = [
    "</script><script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for STORED-XSS-01 JS syntax checks"
    return node


def _node_check_source(node: str, source: str, label: str) -> None:
    """임시 파일 없이 stdin 으로 JS 구문 검사."""
    proc = subprocess.run(
        [node, "--check", "-"],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"{label} node --check 실패:\n{proc.stderr or proc.stdout}"


# --------------------------------------------------------------------------- #
# P0-19: SecurityLog message order_link 필터 escape-first
# --------------------------------------------------------------------------- #

def test_order_link_filter_escapes_hostile_message(app) -> None:
    """order_link 필터는 message 원문을 escape 하여 실행 가능한 마크업 0."""
    from foms.web.orders.listing import order_link_filter

    with app.test_request_context():
        for payload in HOSTILE_PAYLOADS:
            message = f"로그인 실패: 사용자 {payload} (계정 없음)"
            rendered = str(order_link_filter(message))
            # 실행 가능한 태그가 살아남지 않는다: 원문의 '<' 는 escape 되어
            # &lt; 로만 등장(라이브 <script>/<img>/<svg> 태그 0).
            assert "<script" not in rendered.lower(), rendered
            assert "<img" not in rendered.lower(), rendered
            assert "<svg" not in rendered.lower(), rendered
            # payload 의 '<' 가 있으면 반드시 escape 되어 보존(삭제 금지).
            if "<" in payload:
                assert "&lt;" in rendered, rendered


def test_order_link_filter_keeps_legit_order_link(app) -> None:
    """정상 '주문 #<digits>' 는 여전히 서버 생성 <a> 링크로 렌더."""
    from foms.web.orders.listing import order_link_filter

    with app.test_request_context():
        rendered = str(order_link_filter("주문 #123 상태 변경"))
        assert "<a href=" in rendered, rendered
        assert "주문 #123" in rendered, rendered
        # 숫자 링크 인자만 사용 — 링크 텍스트에 스크립트 없음.
        assert "<script" not in rendered.lower(), rendered


def test_order_link_filter_is_escape_first_static() -> None:
    """회귀 가드: 필터 구현이 escape 를 거친다(raw Markup(re.sub(s)) 금지)."""
    src = _read(LISTING_PY)
    m = re.search(r"def order_link_filter\(.*?\n(?:    .*\n|\n)+", src)
    assert m, "order_link_filter 정의를 찾지 못했습니다"
    body = m.group(0)
    assert "escape(" in body, "order_link_filter 가 escape-first 가 아님"
    # 원문 s 를 escape 없이 그대로 Markup(re.sub(..., s)) 하는 취약 패턴 금지.
    assert not re.search(r"re\.sub\([^)]*,\s*s\)", body), "raw s 를 escape 없이 linkify"


def test_security_logs_template_routes_message_through_order_link() -> None:
    """message 는 반드시 order_link 필터를 거친다(raw message|safe 금지)."""
    text = _read(SECURITY_LOGS)
    assert "| order_link" in text, "security_logs 가 order_link 를 사용하지 않음"
    # message 를 order_link 없이 바로 |safe 하는 sink 금지.
    assert not re.search(r"message\s*\|\s*safe", text), "raw message|safe sink 잔존"


# --------------------------------------------------------------------------- #
# P0-20: 주문 목록 options 요약 autoescape
# --------------------------------------------------------------------------- #

def test_order_index_no_safe_on_options_summary() -> None:
    text = _read(ORDERS_INDEX)
    assert not re.search(r"summary_content\s*\|\s*safe", text), "summary_content|safe sink 잔존"


def test_order_index_online_summary_no_br_safe() -> None:
    text = _read(ORDERS_INDEX)
    assert "replace('\\n', '<br>')" not in text, "online summary <br>|safe sink 잔존"
    assert not re.search(r"replace\(\s*'\\n'\s*,\s*'<br>'\s*\)", text), "<br> 주입 잔존"


def test_order_index_online_summary_pre_line_css() -> None:
    """<br> 대신 CSS pre-line 으로 줄바꿈(기능 유지)."""
    text = _read(ORDERS_INDEX)
    assert "options-online-summary" in text, "online summary 클래스 누락"
    assert re.search(r"\.options-online-summary\s*\{[^}]*white-space:\s*pre-line", text), (
        "pre-line 줄바꿈 CSS 누락"
    )


def test_jinja_autoescape_neutralises_hostile_options(app) -> None:
    """autoescape 가 hostile 옵션 문자열을 중화."""
    for payload in HOSTILE_PAYLOADS:
        rendered = app.jinja_env.from_string(
            "<span>{{ summary_content }}</span>"
        ).render(summary_content=payload)
        assert "<script" not in rendered.lower(), rendered
        assert "<img" not in rendered.lower(), rendered
        assert "<svg" not in rendered.lower(), rendered
        if "<" in payload:
            assert "&lt;" in rendered, rendered


# --------------------------------------------------------------------------- #
# P0-21: User.name/team → DOM node/textContent (innerHTML 문자열 주입 금지)
# --------------------------------------------------------------------------- #

# detail-dom 은 대형 template-literal + escapeHtml 규약(별도 gate); checkbox 목록
# 파일은 DOM node 전용이므로 concat/template-literal 주입을 전면 금지한다.
CHECKBOX_LIST_FILES = [
    STATIC_JS / "drawing" / "workbench-dashboard.js",
    STATIC_JS / "orders" / "dashboard" / "erp-dashboard-drawing.js",
    WORKBENCH_BODY,
]


def test_no_user_field_in_js_innerHTML() -> None:
    """4개 파일에서 User.name/team 이 innerHTML 로 주입되지 않는다."""
    offenders: list[str] = []
    for path in USER_LIST_FILES:
        text = _read(path)
        # template-literal 주입 잔존 금지(모든 파일).
        for pat in (r"\$\{u\.name\}", r"\$\{u\.team\}"):
            if re.search(pat, text):
                offenders.append(f"{path.name}: {pat}")
        # 한 라인에 innerHTML 과 user 필드 동시 등장 금지.
        for i, line in enumerate(text.splitlines(), 1):
            if "innerHTML" in line and re.search(r"u\.name|u\.team|customer_name", line):
                offenders.append(f"{path.name}:{i} innerHTML+user field")
    # checkbox 목록 파일은 문자열 concat 주입('<strong>' + u.name)도 금지.
    for path in CHECKBOX_LIST_FILES:
        text = _read(path)
        for pat in (r"\+\s*u\.name\b", r"\+\s*u\.team\b"):
            if re.search(pat, text):
                offenders.append(f"{path.name}: concat {pat}")
    assert not offenders, "innerHTML 사용자 필드 주입 잔존: " + "; ".join(offenders)


def test_detail_dom_assignee_names_escaped() -> None:
    """detail-dom 의 assigneeNames(User.name join)은 escapeHtml 로 인코딩."""
    text = _read(STATIC_JS / "orders" / "dashboard" / "erp-dashboard-detail-dom.js")
    assert re.search(r"assigneeNames\s*=\s*escapeHtml\(", text), (
        "assigneeNames 가 escapeHtml 로 인코딩되지 않음"
    )


def test_user_list_files_use_dom_textcontent() -> None:
    """checkbox 목록 파일은 DOM node 렌더러 + textContent + 정수 id allowlist 사용."""
    for path in (
        STATIC_JS / "drawing" / "workbench-dashboard.js",
        STATIC_JS / "orders" / "dashboard" / "erp-dashboard-drawing.js",
        WORKBENCH_BODY,
    ):
        text = _read(path)
        assert "textContent" in text, f"{path.name}: textContent 미사용"
        assert "Number.isInteger" in text, f"{path.name}: 정수 id allowlist 누락"


# --------------------------------------------------------------------------- #
# P0-23: 변경이력 카드 createElement/textContent + addEventListener
# --------------------------------------------------------------------------- #

def test_change_logs_no_inline_onclick() -> None:
    """change_logs 에 inline onclick 속성 0 (addEventListener 사용)."""
    text = _read(CHANGE_LOGS)
    assert "onclick=" not in text, "inline onclick 속성 잔존"


def test_change_logs_no_raw_customer_name_innerHTML() -> None:
    """hostile customer_name 이 raw innerHTML 로 렌더되지 않는다."""
    text = _read(CHANGE_LOGS)
    assert "${event.customer_name}" not in text, "raw customer_name innerHTML 주입 잔존"
    # 카드 렌더는 createElement + textContent 로 전환됨.
    assert "createElement" in text and "textContent" in text, "DOM 빌드 전환 누락"
    assert "addEventListener" in text, "되돌리기 버튼 addEventListener 누락"


def test_change_logs_customer_name_via_textcontent() -> None:
    """customer_name 은 링크 textContent 로 안전 렌더."""
    text = _read(CHANGE_LOGS)
    assert re.search(r"\.textContent\s*=\s*event\.customer_name", text), (
        "customer_name textContent 바인딩 누락"
    )


# --------------------------------------------------------------------------- #
# JS 구문 검사 (node --check)
# --------------------------------------------------------------------------- #

def test_modified_js_node_check() -> None:
    node = _node()
    for path in MODIFIED_STANDALONE_JS:
        proc = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, f"{path.name} node --check 실패:\n{proc.stderr or proc.stdout}"


def _extract_scripts(text: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", text, flags=re.DOTALL)


def test_change_logs_inline_js_node_check() -> None:
    """change_logs 인라인 JS(Jinja-free)가 파싱된다."""
    node = _node()
    scripts = _extract_scripts(_read(CHANGE_LOGS))
    assert scripts, "change_logs 에 <script> 블록이 없음"
    for idx, src in enumerate(scripts):
        assert "{{" not in src and "{%" not in src, "인라인 JS 에 Jinja 잔존(구문검사 불가)"
        _node_check_source(node, src, f"change_logs script[{idx}]")


# --------------------------------------------------------------------------- #
# sink manifest 100% 열거
# --------------------------------------------------------------------------- #

def test_sink_manifest_enumerates_all_targets() -> None:
    manifest_path = ROOT / "docs" / "harness" / "foms_untrusted_dom_sinks.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    sinks = data["sinks"]
    # 각 sink 는 필수 필드를 모두 가진다.
    for s in sinks:
        for field in ("id", "path", "symbol", "source_field", "disposition", "test"):
            assert s.get(field), f"manifest sink {s.get('id')} 에 {field} 누락"

    paths = {s["path"] for s in sinks}
    required_paths = {
        "foms/web/orders/listing.py",
        "templates/admin/security_logs.html",
        "foms/web/auth/routes.py",
        "templates/orders/index.html",
        "static/js/drawing/workbench-dashboard.js",
        "static/js/orders/dashboard/erp-dashboard-drawing.js",
        "static/js/orders/dashboard/erp-dashboard-detail-dom.js",
        "templates/drawing/partials/workbench_detail_body.html",
        "templates/admin/change_logs.html",
        "foms/api/events.py",
    }
    missing = required_paths - paths
    assert not missing, f"manifest 에 미열거된 sink 경로: {missing}"

    # 열거된 파일 경로는 실제 존재해야 한다.
    for p in paths:
        assert (ROOT / p).exists(), f"manifest 경로 미존재: {p}"
