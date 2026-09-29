"""S2 — 도면 탭 보내기 JS 4개의 정적 계약(설계서 2026-09-29 §3.6 · §6 핀 · Q5).

동작은 test_drawing_customer_js_behavior.py 가 Node 로 돌려 본다. 여기는 바꾸기 쉬운 규약만 문다:
구문 · jQuery 금지 · fetch 는 try 안 · data.success 검증 · 토큰을 저장소에 안 씀 · C14(대시보드로 안 감) ·
싣는 자리(v2 조건 블록 밖 defer) · 크기 래칫 300 · 본문↔핀 자물쇠 · 서버 상수와 같은 값.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DETAIL = ROOT / "templates/drawing/partials/workbench_detail_body.html"
JS_FILES = {
    "send": "static/js/foms/drawing-customer-send.js",
    "ok": "static/js/foms/drawing-customer-ok.js",
    "edit": "static/js/foms/drawing-revision-edit.js",
    "urgent": "static/js/foms/drawing-urgent-call-pc.js",
}

# 본문 ↔ 핀 자물쇠(test_drawing_mobile_asset_pin_freshness.ASSET_PIN_LOCK 와 같은 규칙).
# 자산 본문을 고쳤다면 핀을 새 값으로 올리고 이 표의 (해시, 핀)을 함께 갱신한다 —
# ?v= 붙은 정적 자산은 24시간 캐시돼 핀을 안 올리면 기기가 옛 JS 를 쓴다.
JS_PIN_LOCK = {
    "static/js/foms/drawing-customer-send.js": ("3a626f85a177", "20260929n"),
    "static/js/foms/drawing-customer-ok.js": ("624445c27786", "20260930b"),
    "static/js/foms/drawing-revision-edit.js": ("43d3ee5cb418", "20260930b"),
    "static/js/foms/drawing-urgent-call-pc.js": ("eccfa5cb1e85", "20260929n"),
}


def _read(rel: str | Path) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _sha12(rel: str) -> str:
    text = _read(rel).replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _inline_script() -> str:
    body = _read(DETAIL)
    start = body.index("<script>\n  (function () {")
    return body[start:body.index("</script>", start)]


@pytest.mark.parametrize("name", sorted(JS_FILES))
def test_node_check(name):
    node = shutil.which("node")
    assert node, "node must be on PATH for JS syntax checks"
    proc = subprocess.run([node, "--check", str(ROOT / JS_FILES[name])], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr or proc.stdout


@pytest.mark.parametrize("name", sorted(JS_FILES))
def test_conventions(name):
    text = _read(JS_FILES[name])
    assert "jQuery" not in text and not re.search(r"(?<![\w.])\$\(", text), "jQuery 금지"
    assert 'style="' not in text, "인라인 스타일 금지(ratchet)"
    assert re.search(r"if \(window\.__FOMS_[A-Z_]+_BOUND\) return;", text), "document 위임 + 한 번만 등록"
    assert ".success" in text, "응답 data.success 검증"
    for storage in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
        assert storage not in text, f"{storage} 금지(토큰 원문은 메모리에만)"
    # C14: 확정·컨펌 뒤 ERP 대시보드로 보내지 않는다(도면 탭에 머문다).
    assert "/erp/dashboard?focus_order=" not in text and "open_quest" not in text
    assert len(text.splitlines()) <= 300, "JS 300줄 래칫"


def _fetch_outside_try(text: str) -> list[int]:
    """`fetch(` 가 try 블록 밖에 있으면 그 줄 번호. 중괄호 쌓기로 try 블록 안인지 본다."""
    stack: list[bool] = []
    bad: list[int] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            before = text[:i].rstrip()
            stack.append(before.endswith("try"))
        elif ch == "}":
            if stack:
                stack.pop()
        elif text.startswith("fetch(", i) and not any(stack):
            bad.append(text.count("\n", 0, i) + 1)
        i += 1
    return bad


@pytest.mark.parametrize("name", sorted(JS_FILES))
def test_every_fetch_is_inside_try(name):
    assert _fetch_outside_try(_read(JS_FILES[name])) == []


def test_fetch_scanner_catches_bare_fetch():
    """음성 대조: 스캐너가 try 밖 fetch 를 실제로 잡는다."""
    assert _fetch_outside_try("async function a() {\n  await fetch('/x');\n}") == [2]
    assert _fetch_outside_try("async function a() {\n  try { await fetch('/x'); } catch (_) {}\n}") == []


def test_send_rules_live_where_spec_says():
    text = _read(JS_FILES["send"])
    pre = re.search(r"PRE_SEND_FAIL = \[([^\]]+)\]", text).group(1)
    for code in ("400", "404", "409", "410", "503"):
        assert code in pre
    assert "'/api/share/revoke/'" in text
    assert "source_screen: 'drawing_tab'" in text
    assert "body.to_phone = ov.phone" in text  # 번호 바꾸기는 이번 발송에만(Q5-②)
    assert "window.FomsCustomerSend = { savePhone: savePhone }" in text
    assert "'parties.customer.phone'" in text and "/structured/fields" in text


def test_ok_rules():
    text = _read(JS_FILES["ok"])
    for needle in ("auto_transitioned", "ALREADY_TRANSITIONED", "all_approved", "/erp/drawing-workbench/",
                   "new_stage === 'CONFIRM'", "window.fomsDrawingRevisionExtras", "idempotency_key"):
        assert needle in text, needle
    assert not re.search(r"FomsAdminOverride\.\w+\(", text)  # 관리자 뚫기는 붙이지 않는다


def test_edit_limit_matches_server_and_contract_route():
    from foms.services.orders.drawing_revision_files import MAX_REVISION_FILES

    text = _read(JS_FILES["edit"])
    assert f"MAX_REVISION_FILES = {MAX_REVISION_FILES}" in text
    assert "/request-revision/edit" in text and "target_file_keys" in text
    assert "safeJsonParse" in text and "textContent" in text


def test_pc_urgent_does_not_hijack_mobile_sheet_opener():
    """PC 창은 [data-dw-urgent-call] 만 연다 — 모바일 [data-foms-urgent-call] 위임 처리와 겹치지 않게."""
    text = _read(JS_FILES["urgent"])
    assert "closest('[data-dw-urgent-call]')" in text
    assert "closest('[data-foms-urgent-call]')" not in text
    assert "/urgent-targets" in text and "/urgent-mention" in text and "FOMSNotificationWrite" in text
    assert "Number.isInteger" in text and "textContent" in text


def test_scripts_are_deferred_outside_v2_block_with_pin():
    body = _read(DETAIL)
    v2_start = body.index("{% if erp_mobile_v2_enabled %}\n<script")
    for rel, (_hash, pin) in JS_PIN_LOCK.items():
        name = rel.split("/")[-1]
        tag = re.search(r"<script[^>]*" + re.escape(name) + r"[^>]*>", body).group(0)
        assert re.search(r"\bdefer\b", tag), tag
        assert f"{name}') }}}}?v={pin}" in tag, tag
        assert body.index(tag) < v2_start, f"{name} 는 v2 조건 블록 밖이어야 PC 에서도 시트가 동작한다"


def test_js_body_and_pin_move_together():
    body = _read(DETAIL)
    for rel, (expected_hash, expected_pin) in JS_PIN_LOCK.items():
        name = rel.split("/")[-1]
        pins = re.findall(re.escape(name) + r"'\)\s*\}\}\?v=([0-9a-z]+)", body)
        assert pins == [expected_pin], f"{rel} 핀: {pins}"
        assert _sha12(rel) == expected_hash, (
            f"{rel} 본문이 바뀌었다(표={expected_hash}, 실제={_sha12(rel)}). 핀을 새 값으로 올리고 JS_PIN_LOCK 을 갱신하라."
        )


def test_inline_script_c14_and_extras_guard():
    inline = _inline_script()
    assert "/erp/dashboard?focus_order=" not in inline and "open_quest" not in inline
    assert "async function confirmReceipt" not in inline
    assert "typeof window.fomsDrawingRevisionExtras === 'function'" in inline
