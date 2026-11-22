"""작업 시트 — 눌러도 아무 일이 없던 회색 단추가 까닭을 알린다(2026-11-22 터치 점검 P2).

사장님 "단추가 갑자기 안 먹는다": 검수 전 [제작 완료]가 진짜 ``disabled`` 라 누르면 아무 일도, 요청도 없었다.
규칙(공정 4칸을 다 켜야 제작 완료 — 서버 ``production_complete_ready`` 도 막는다)과 회색 꼴은 그대로 두고, 진짜 disabled 를 빼고
``aria-disabled="true"`` 만 남겨 누르면 상태 줄에 남은 공정을 알린다(요청 0). 같은 꼴: 파트 계정의 잠긴 공정 칸.
쓰기 길 · 회색/파랑 판정은 ``test_production_sheet_page.py`` · ``test_production_complete_inspect_screens.py``.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.production_home_step_panel_seed import TABLET, add_order, get_html, login, set_cookies

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_sheet_tap_explains_node_checks.js"
LABELS = ["재단", "엣지", "조립", "검수"]


def _run(tmp_path, html: str, want: dict) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    page = tmp_path / "sheet.html"
    page.write_text(html, encoding="utf-8")
    proc = subprocess.run([node, str(NODE_CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


@pytest.mark.parametrize("done", [("cut",), ("cut", "edge")])
def test_회색_제작_완료를_누르면_남은_공정을_알리고_요청은_없다_4칸이면_파랑_Node(client, tmp_path, done) -> None:
    login(client)
    order = add_order("가람집", 1, done=done)
    set_cookies(client, TABLET)
    html = get_html(client, f"/erp/production/sheet/{order.id}")
    btn = re.search(r'<button [^>]*data-foms-sheet-complete[^>]*>', html).group(0)
    assert 'aria-disabled="true"' in btn and " disabled" not in btn and "foms-prod-page__btn--off" in btn
    _run(tmp_path, html, {"mode": "complete", "order": order.id, "labels": LABELS, "done": list(done)})


def test_파트_계정의_잠긴_공정_칸을_누르면_잠금_글_요청은_없다_Node(client, tmp_path) -> None:
    login(client, "김재단", part="cut")
    order = add_order("가람집", 1, done=("cut",))
    set_cookies(client, TABLET)
    html = get_html(client, f"/erp/production/sheet/{order.id}")
    cells = re.findall(r'<button [^>]*data-foms-sheet-step="\w+"[^>]*>', html)
    assert len(cells) == 4 and all('aria-disabled="true"' in c and " disabled" not in c and "is-locked" in c for c in cells)
    _run(tmp_path, html, {"mode": "locked", "order": order.id, "note": "공정은 도면 카드에서 체크해요"})


def test_시트_JS_는_aria_disabled_로_막고_진짜_disabled_를_쓰지_않는다() -> None:
    js = (ROOT / "static/js/production/foms-production-sheet-page.js").read_text(encoding="utf-8")
    assert "completeBtn.disabled = !ready" not in js and "completeBtn.setAttribute('aria-disabled', 'true')" in js
    assert "e.stopPropagation();" in js and "completeBlockedText()" in js and len(js.splitlines()) <= 300
    for rel in ("templates/production/sheet.html", "templates/production/partials/tablet_sheet.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "disabled aria-disabled" not in text, rel
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    assert ".is-locked:disabled" not in css and '.foms-prod-page__step.is-locked[aria-disabled="true"]' in css
