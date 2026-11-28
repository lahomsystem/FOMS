"""주문 첨부 목록 '생산 · 바뀌기 전' 글(펜 기록 설계서 2026-11-28 §5-3 · §3-4).

서버(주문 첨부 목록 API ``annotate_production_old``)가 바뀌기 전 '생산' 그림에 ``production_old`` ·
``production_label`` 을 싣는다. 주문 화면(PC 카드 · 폰 칸)은 그 항목의 이름 칸 글 앞에 서버 글을 붙인다.
값이 없으면 지금과 한 글자도 같다(새 배지 · 새 색 · 새 줄 없음).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED_JS = ROOT / "static/js/orders/erp-order-shared.js"
_NODE = shutil.which("node")


def _extract_function(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth, i = 0, src.index("{", start)
    while True:
        ch = src[i]
        depth += ch == "{"
        depth -= ch == "}"
        i += 1
        if depth == 0:
            return src[start:i]


_HARNESS = r"""
const vm = require('vm');
const [fnSrc, casesJson] = process.argv.slice(1);
const ctx = { String, escapeHtml: (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') };
vm.createContext(ctx);
vm.runInContext(fnSrc, ctx);
const out = JSON.parse(casesJson).map((c) => ctx.erpProductionOldName(c.a, c.name));
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_name_text_reads_server_label_only_when_old():
    fn = _extract_function(SHARED_JS.read_text(encoding="utf-8"), "erpProductionOldName")
    cases = [
        {"a": {"category": "production", "production_old": True, "production_label": "생산 · 바뀌기 전"}, "name": "김재단.png"},
        {"a": {"category": "production"}, "name": "박반장.png"},  # 값 없음 = 이름 그대로
        {"a": {"category": "production", "production_old": True}, "name": "정하늘.png"},  # 글 없음 = 이름 그대로
        {"a": {"category": "production", "production_old": False, "production_label": "생산 · 바뀌기 전"}, "name": "a.png"},
        {"a": {"production_old": True, "production_label": "<b>x</b>"}, "name": "b.png"},  # 서버 글은 이스케이프
        {"a": None, "name": "c.png"},
    ]
    proc = subprocess.run([_NODE, "-e", _HARNESS, fn, json.dumps(cases, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [
        "생산 · 바뀌기 전 · 김재단.png", "박반장.png", "정하늘.png", "a.png", "&lt;b&gt;x&lt;/b&gt; · b.png", "c.png",
    ]


def test_pc_card_and_mobile_tile_name_use_label():
    src = SHARED_JS.read_text(encoding="utf-8")
    fn = _extract_function(src, "erpProductionOldName")
    assert "a.production_label" in fn and "escapeHtml(" in fn
    tile = src[src.index("function erpBuildAttachmentTile("):src.index("function erpSupersededBadgeHtml(")]
    assert '<span class="erp-attachment-tile__name">${erpProductionOldName(a, name)}</span>' in tile
    render = _extract_function(src, "erpRenderAttachments")
    assert 'style="max-width: 70%;">${erpProductionOldName(a, name)}</div>' in render
    # 올리는 중 자리표시(파일 객체)는 서버 값이 없어 그대로다.
    assert src.count('<span class="erp-attachment-tile__name">${name}</span>') == 2
