"""[수정하기] '왜 고쳤나요(자세히)' · 사진 배선(설계서 17.6.1 (b) · (f) 시험 3 · 8 · 9) — 이 파일은 일부러 이미 있던 모듈만
불러온다(고치기 전 코드에서도 모아져 '빨강'이 무엇인지 보이게).

요청 크기 manifest(1MiB 기본 상한에 안 걸림) · 밤 지우기 배선(--apply) · 화면(칸 자리 · 스크립트 핀 · 인라인 스타일 없음) ·
JS 규칙(300줄 · innerHTML · jQuery 없음 · fetch 검사 · 세 길 · 보낸 뒤에만 올림) · 순수 함수 node 시험(꼴 · 15MB · 개수 · 줄이기).
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.platform.request_limits import resolve_body_cap
from tools.cron.nightly import NIGHTLY_STEPS

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "static/js/cs-agent/edit-detail.js"
SEND_SCRIPT = ROOT / "static/js/cs-agent/send-screen.js"
TEMPLATE = ROOT / "templates/cs/cs_agent_send.html"
_MIB = 1024 * 1024


def test_the_photo_route_has_its_own_body_cap_above_one_mib():
    cap = resolve_body_cap("/api/cs-agent/turns/7/edit-photos")
    assert cap is not None and cap.category == "cs_edit_photo" and cap.max_body_bytes > 5 * _MIB
    assert resolve_body_cap("/api/cs-agent/turns/7/edit-detail").max_body_bytes <= _MIB  # 글은 기본 상한 그대로


def test_a_three_mib_photo_post_is_not_cut_at_one_mib(client):
    big = client.post("/api/cs-agent/turns/7/edit-photos", content_type="multipart/form-data",
                      data={"photo": (io.BytesIO(b"\xff\xd8" + b"\x00" * (3 * _MIB)), "a.jpg"), "no_personal": "1"})
    assert big.status_code == 401  # 413 이 아니라 핸들러까지 왔다(로그인 안 함)


def test_the_ninety_day_purge_runs_every_night_for_real():
    steps = {step.script: step.args for step in NIGHTLY_STEPS}
    assert "--apply" in steps.get("tools/cron/purge_cs_edit_photos.py", ())
    assert (ROOT / "tools/cron/purge_cs_edit_photos.py").is_file()


def test_the_edit_screen_places_the_section_under_the_reason_and_pins_the_scripts():
    html = TEMPLATE.read_text(encoding="utf-8")
    order = [html.index(n) for n in ('data-cs-send-reason', 'data-cs-detail', 'data-cs-rewrite-note',
                                     'data-cs-detail-status', 'data-cs-send-go')]
    assert order == sorted(order)
    assert "edit-detail.js') }}?v=" in html and html.count("defer></script>") == 2
    assert 'accept="image/jpeg,image/png,image/webp" multiple' in html and "<details" in html
    assert "|tojson|forceescape" in html and 'style="' not in html and "onclick" not in html
    assert "send-screen.js') }}?v=20261102b" in html and "erp-pro.css') }}?v=20261102b" in html
    css = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    for rule in (".cs-detail {", ".cs-detail__drop.is-over {", ".cs-detail__thumb {", ".cs-detail__status--warning {"):
        assert rule in css, rule


def test_the_script_follows_the_frontend_rules_and_uploads_only_after_send():
    script = SCRIPT.read_text(encoding="utf-8")
    assert len(script.splitlines()) <= 300
    assert ".innerHTML" not in script and "jQuery" not in script and "$(" not in script and ".style." not in script
    assert "payload.success === true" in script and script.count("try {") >= 3 and "__FOMS_CS_EDIT_DETAIL_BOUND" in script
    for needle in ("'paste'", "'drop'", "'change'", "URL.createObjectURL", "'cs-send:sent'", "safeJsonParse",
                   "textContent", "new FormData()", "method: 'DELETE'"):
        assert needle in script, needle
    send = SEND_SCRIPT.read_text(encoding="utf-8")
    assert "new CustomEvent('cs-send:sent')" in send and "closest('[data-cs-detail]')" in send
    assert len(send.splitlines()) < 300


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_node_check_passes_for_both_scripts():
    for path in (SCRIPT, SEND_SCRIPT):
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, timeout=60)


def _node(expr: str):
    script = ("global.window={};global.document={querySelector(){return null}};"
              f"require({json.dumps(str(SCRIPT))});"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_admit_takes_only_jpeg_png_webp_under_fifteen_mib_and_five_photos():
    m = "window.FOMS_CS_EDIT_DETAIL.admit"
    lim = "{maxPhotos:5}"
    got = _node(f"[{m}({{type:'image/jpeg',size:100}},0,{lim}),{m}({{type:'image/webp',size:100}},4,{lim}),"
                f"{m}({{type:'image/png',size:100}},5,{lim}),{m}({{type:'image/heic',size:100}},0,{lim}),"
                f"{m}({{type:'application/pdf',size:100}},0,{lim}),{m}({{type:'image/gif',size:100}},0,{lim}),"
                f"{m}({{type:'',size:100}},0,{lim}),{m}({{type:'image/jpeg',size:15*1024*1024+1}},0,{lim}),"
                f"{m}({{type:'image/jpeg',size:15*1024*1024}},0,{lim}),{m}({{type:'image/jpeg',size:0}},0,{lim})]")
    assert got == ["", "", "photo_full", "photo_format", "photo_format", "photo_format", "photo_format",
                   "photo_source", "", "photo_empty"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_shrinking_keeps_the_ratio_under_the_long_edge_and_picks_the_output_type():
    m = "window.FOMS_CS_EDIT_DETAIL"
    sizes, types, body = _node(f"[[{m}.fitBox(4032,3024,2048),{m}.fitBox(1000,3000,2048),{m}.fitBox(800,600,2048)],"
                               f"[{m}.outType(true),{m}.outType(false)],"
                               f"{m}.photoBody({{type:'image/png',noPersonal:true}})]")
    assert sizes == [{"width": 2048, "height": 1536}, {"width": 683, "height": 2048}, {"width": 800, "height": 600}]
    assert types == ["image/png", "image/jpeg"]
    assert body == {"field": "photo", "name": "photo.png", "no_personal": "1"}
