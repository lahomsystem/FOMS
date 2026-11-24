"""관리자 사유 창이 생산 화면에서 안 뜨던 것(2026-11-25 스테이징 실측) — 근본 원인을 고친 시험.

``erp-dashboard-core.js`` 의 ``fomsSyncErpDashboardUserGlobals`` 가 첫 ``.erp-dashboard`` 요소의 ``data-user-*`` 로 ``MY_ID`` ·
``MY_TEAM`` · ``MY_NAME`` · ``MY_ROLE`` 을 다시 썼다 — 속성을 싣는 곳은 주문 대시보드뿐이라 나머지 ``/erp/`` 화면(생산 첫 화면 ·
작업 시트 · 옛 생산 보드 · 시공 · 완료 · 정산 · 이력 · 협력사 거래명세서)에서 레이아웃이 서버에서 심은 ``MY_ROLE`` 을 빈 값으로 덮어
``foms-admin-override.js`` 의 ``canOverride()`` 가 거짓이었다.

규칙은 ``MY_ROLE`` 하나에만: 속성이 있으면 그 값(주문 대시보드 — 글자 그대로 같다), 없으면 이미 있는 값(레이아웃), 아무도 안 심었으면
빈 값. ``MY_ID`` · ``MY_TEAM`` · ``MY_NAME`` 은 레이아웃이 심지 않는 값이라 지금 그대로(속성이 없으면 빈 값) — 주문 대시보드에서 셸
이동으로 온 사람과 처음부터 그 화면을 연 사람의 화면이 갈리지 않게(도면팀 [담당자 지정] · [도면 전달]이 이동 경로에 따라 보이지 않게).
생산 첫 화면에는 사유 창 세트를 싣지 않는다(부르는 단추가 없다 — 작업 시트만).

되돌리면 실패: 속성 없는 화면에서 MY_ROLE 이 빈 값 · 셸 이동으로 남은 팀 값이 살아 있음.
날짜는 쓰지 않는다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests.support.production_home_step_panel_seed import HOME, TABLET, add_order, get_html, login, set_cookies

ROOT = Path(__file__).resolve().parents[2]
CORE_JS = ROOT / "static/js/orders/dashboard/erp-dashboard-core.js"
OVERRIDE = "js/foms/foms-admin-override.js?v="
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}

_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('window.fomsSyncErpDashboardUserGlobals = function');
const body = src.slice(start, src.indexOf('\n        };', start) + 11);
function run(attrs, preset) {
  const el = attrs === null ? null : {
    hasAttribute: (k) => Object.prototype.hasOwnProperty.call(attrs, k),
    getAttribute: (k) => (Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null),
  };
  const ctx = Object.assign({ document: { querySelector: () => el } }, preset);
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(body + '\nwindow.fomsSyncErpDashboardUserGlobals();', ctx);
  return { MY_ID: ctx.MY_ID, MY_TEAM: ctx.MY_TEAM, MY_NAME: ctx.MY_NAME, MY_ROLE: ctx.MY_ROLE };
}
const full = { 'data-user-id': '7', 'data-user-team': 'SALES', 'data-user-name': '가짜영업', 'data-user-role': 'MANAGER' };
console.log(JSON.stringify({
  no_attr_keeps_layout_role: run({}, { MY_ROLE: 'ADMIN' }),
  no_attr_nothing_set: run({}, {}),
  after_shell_move: run({}, { MY_ROLE: 'MANAGER', MY_ID: '5', MY_TEAM: 'DRAWING', MY_NAME: '가짜도면' }),
  attrs_win: run(full, { MY_ROLE: 'ADMIN', MY_TEAM: 'CS' }),
  empty_attr_is_empty: run({ 'data-user-role': '' }, { MY_ROLE: 'ADMIN' }),
  no_root_untouched: run(null, { MY_ROLE: 'ADMIN' }),
}));
"""


def test_sync_keeps_only_the_layout_role_and_resets_the_rest_like_before(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    harness = tmp_path / "sync_check.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    proc = subprocess.run([node, str(harness), str(CORE_JS)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    # 속성 없는 화면(생산 · 시공 …): 레이아웃이 심은 역할이 산다 · 아무도 안 심은 값은 지금처럼 빈 값
    assert got["no_attr_keeps_layout_role"] == {"MY_ID": "", "MY_TEAM": "", "MY_NAME": "", "MY_ROLE": "ADMIN"}
    assert got["no_attr_nothing_set"] == {"MY_ID": "", "MY_TEAM": "", "MY_NAME": "", "MY_ROLE": ""}
    # 주문 대시보드에서 셸 이동으로 온 화면: 팀 · 번호 · 이름은 지금처럼 비운다(처음 연 화면과 같다) — 역할만 산다
    assert got["after_shell_move"] == {"MY_ID": "", "MY_TEAM": "", "MY_NAME": "", "MY_ROLE": "MANAGER"}
    # 주문 대시보드(속성 있음): 속성 값이 이긴다 — 빈 속성은 빈 값(고치기 전과 글자 그대로 같다)
    assert got["attrs_win"] == {"MY_ID": "7", "MY_TEAM": "SALES", "MY_NAME": "가짜영업", "MY_ROLE": "MANAGER"}
    assert got["empty_attr_is_empty"] == {"MY_ID": "", "MY_TEAM": "", "MY_NAME": "", "MY_ROLE": ""}
    assert got["no_root_untouched"] == {"MY_ROLE": "ADMIN"}  # 루트가 없으면 아무것도 안 만진다(지금 그대로)


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def test_work_sheet_carries_the_retry_set_for_writers_and_home_does_not(client, cohort):
    """사유 창 세트는 부르는 단추가 있는 작업 시트에만(쓰는 사람 · PC 는 [고치기]) — 생산 첫 화면은 지금처럼 싣지 않는다."""
    order = add_order("가짜사유창", 1)
    login(client, "가짜관리", team="CS", role="ADMIN")
    sheet = f"/erp/production/sheet/{order.id}"
    set_cookies(client, TABLET)
    assert get_html(client, sheet).count(OVERRIDE) == 1
    for tab in ("date", "steps", "all", "changes"):
        assert OVERRIDE not in get_html(client, f"{HOME}?tab={tab}"), tab
    set_cookies(client, PC)  # PC [고치기] 끔 = 보기 전용
    assert OVERRIDE not in get_html(client, sheet)
    client.set_cookie("foms_prod_edit", str(int(time.time())), domain="localhost", path="/erp/production")
    assert get_html(client, sheet).count(OVERRIDE) == 1  # [고치기] 켬


def test_only_admin_can_open_the_reason_sheet():
    """사유 창은 관리자만(canOverride = MY_ROLE ADMIN, 서버가 심는 역할) — 반장 · 파트는 지금처럼 거절 글만."""
    js = (ROOT / "static/js/foms/foms-admin-override.js").read_text(encoding="utf-8")
    assert "return String(window.MY_ROLE || '').toUpperCase() === 'ADMIN';" in js
    layout = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "window.MY_ROLE = window.MY_ROLE || {{ (current_user.role" in layout
