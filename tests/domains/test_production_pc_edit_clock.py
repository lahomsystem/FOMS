"""PC [고치기] 켠 시각 — 위 탭을 바꾼 뒤 첫 누름이 아무 일도 안 하던 것(2026-11-22 터치 점검, 원인 커밋 8f37a3e4b).

원인: ``static/js/production/foms-production-edit.js`` 가 흐른 시간을 **문서를 연 때**부터 세어, 셸 조각 교체로 온 새 단추의
서버 시각(``data-foms-prod-edit-now``)에 더했다 → 켠 시각이 앞날 → ``pc_view.edit_cookie_fresh`` 가 ``0 <= age`` 로 거절.
고침: 단추마다 화면에 온 때부터 센다(JS) + 서버는 시계 차 1분까지 받는다(더 먼 앞날은 거절).
설계서 ``docs/specs/2026-11-21-production-pc-viewer_SPEC.md`` §7. 나머지 [고치기] 시험은 ``test_production_pc_viewer.py``.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.production.pc_view import EDIT_CLOCK_SKEW_SECONDS, EDIT_TTL_SECONDS, production_screen_flags

ROOT = Path(__file__).resolve().parents[2]
NOW = 1_795_329_800


class _Req:
    def __init__(self, **cookies):
        self.cookies = cookies


class _Admin:
    role, team, partner_org_id = "ADMIN", "CS", None


def _on(value) -> bool:
    return production_screen_flags(_Admin(), _Req(foms_ptr="fine", foms_prod_edit=str(value)), NOW)["edit_on"]


def test_고치기_쿠키는_시계_차_1분까지_받고_더_먼_앞날과_2시간_지남은_거절() -> None:
    assert EDIT_CLOCK_SKEW_SECONDS == 60
    for value in (NOW, NOW + 1, NOW + 30, NOW + EDIT_CLOCK_SKEW_SECONDS, NOW - EDIT_TTL_SECONDS + 1):
        assert _on(value), value
    # 음성 대조 — 1분 넘게 앞선 값 · 먼 앞날 · 2시간 지남 · 숫자 아님
    for value in (NOW + EDIT_CLOCK_SKEW_SECONDS + 1, NOW + 600, NOW + 3600, NOW - EDIT_TTL_SECONDS, "abc", "-5", ""):
        assert not _on(value), value


def test_고치기_켠_시각은_그_단추가_온_때부터_센다_셸_교체_뒤_첫_누름_Node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    proc = subprocess.run([node, str(ROOT / "tests/support/production_edit_node_checks.js")], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr
    js = (ROOT / "static/js/production/foms-production-edit.js").read_text(encoding="utf-8")
    assert "openedAt" not in js and "foms:erp-shell-fragment-swapped" in js and "new WeakMap()" in js
    assert len(js.splitlines()) <= 300
    check = subprocess.run([node, "--check", str(ROOT / "static/js/production/foms-production-edit.js")], capture_output=True,
                           text=True, timeout=60)
    assert check.returncode == 0, check.stderr
