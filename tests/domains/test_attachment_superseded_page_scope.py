"""R4 범위 — 교체된 옛 도면은 **주문 대시보드와 주문 수정 화면**에서만 보인다(2c-2 리뷰 P1·P2·P3).

왜(리뷰 P1): 생산·시공 대시보드에도 ERP 대시보드 번들(erp-dashboard-entry.js)이 실린다. 루트가 둘 다
``.erp-dashboard`` 라서다. 번들의 최상위 ``openAttachmentsPreview`` 가 생산 쪽 인라인 함수를 덮어쓰고,
시공은 같은 클릭에 두 처리기가 함께 돈다. 그래서 JS 전역 함수가 늘 ``include_superseded=1`` 을 붙이면
설계서 §4.9·§8 이 "지금처럼 숨김" 이라 한 생산·시공 첨부 창에 옛 도면이 샌다.

고정하는 것:
  - 옛 도면 표시 여부는 **페이지가** 켠다: 주문 대시보드 루트에만 ``data-attachments-show-superseded="1"``.
    생산·시공 페이지를 실제로 렌더해 표시가 없음을 단언한다.
  - 첨부 창 함수는 그 표시가 있을 때만 인자를 붙인다(node VM 으로 실제 실행 — 생산식 전역 함수를 먼저
    정의한 뒤 번들을 평가해 덮어쓰기 상황을 그대로 재현).
  - 첨부 미리보기 클릭 처리기는 페이지마다 하나만 돈다(생산·시공 페이지에서는 ERP 쪽 위임이 비킨다).
  - 전체화면 뷰어 넘김 목록은 누른 첨부와 같은 무리(현재 / 교체됨)만 담는다 — 뷰어에는 '교체됨' 표시가
    없으니 표시 없이 옛 도면으로 넘어가지 않게 한다(P3).
  - 2b(옛 도면 행만 휴지통·파일 보존) 전에는 옛 도면 행에 삭제 권한을 싣지 않는다(P2).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]
ATTACH_JS = ROOT / "static/js/orders/dashboard/erp-dashboard-attachments.js"
CORE_JS = ROOT / "static/js/orders/dashboard/erp-dashboard-core.js"
DETAIL_DOM_JS = ROOT / "static/js/orders/dashboard/erp-dashboard-detail-dom.js"
SHARED_JS = ROOT / "static/js/orders/erp-order-shared.js"
MARKER = 'data-attachments-show-superseded="1"'
_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="node 미설치")


@pytest.fixture(autouse=True)
def _reset_dashboard_cache_runtime():
    from foms.services.common import dashboard_cache as dc

    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> None:
    user = User(username="r4_scope_admin", password=generate_password_hash("x"), role="ADMIN",
                team="CS", name="R4 범위", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _page(client, path: str) -> str:
    res = client.get(path)
    assert res.status_code == 200, path
    return res.get_data(as_text=True)


def test_no_dashboard_root_opts_in(client, monkeypatch):
    """실제 렌더: 어느 대시보드에도 표시가 없다 — ERP 화면은 최종 도면만(2026-09-30 사용자 결정).

    생산·시공은 ERP 번들을 싣지만 표시가 없다. 주문 대시보드도 표시를 뺐다.
    """
    monkeypatch.delenv("REDIS_URL", raising=False)
    _login_admin(client)

    orders = _page(client, "/erp/dashboard")
    assert "erp-dashboard-orders" in orders
    assert "data-attachments-show-superseded" not in orders

    for path, root_cls in (("/erp/production/dashboard", "erp-dashboard-production"),
                           ("/erp/construction/dashboard", "erp-construction-dashboard")):
        html = _page(client, path)
        assert root_cls in html, path
        assert "erp-dashboard-entry.js" in html, path  # 번들은 실린다 — 그래서 페이지 표시로 가른다
        assert "data-attachments-show-superseded" not in html, path


_PREVIEW_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const [src, marker] = process.argv.slice(1);
const calls = [];
const ctx = {
  console, Date, JSON, Object, String, Number, Array, Promise, setTimeout,
  __attachmentsCache: {}, __attachmentsCacheAt: {}, __attachmentsByCategory: {},
  __activeAttachmentCategory: 'measurement',
  normalizeAttachmentCategory: (c) => String(c || 'measurement'),
  renderAttachmentCategoryTabs: () => {}, renderAttachmentCategoryGallery: () => {},
  showErpToast: () => {},
  bootstrap: { Modal: { getOrCreateInstance: () => ({ show: () => {} }) } },
  fetch: async (url) => {
    calls.push(url);
    return { json: async () => ({ success: true, attachments: [
      { id: 1, category: 'drawing', file_type: 'image', is_superseded: true },
      { id: 2, category: 'drawing', file_type: 'image', is_superseded: false },
    ] }) };
  },
};
ctx.window = ctx;
ctx.document = {
  querySelector: (sel) => (marker === '1' && sel.indexOf('data-attachments-show-superseded') >= 0 ? {} : null),
  getElementById: () => null,
};
vm.createContext(ctx);
// 생산 대시보드 인라인 스크립트처럼 전역 함수를 먼저 두고, 번들을 나중에 평가한다(덮어쓰기 재현).
vm.runInContext("async function openAttachmentsPreview(orderId) { fetch('/production-inline/' + orderId); }", ctx);
vm.runInContext(fs.readFileSync(src, 'utf8'), ctx);
(async () => {
  await ctx.openAttachmentsPreview(7, 'drawing');
  const drawing = (ctx.__attachmentsByCategory.drawing || []).map((a) => a.id);
  process.stdout.write(JSON.stringify({ calls, drawing, cache: (ctx.__attachmentsCache[7] || []).map((a) => a.id) }));
})();
"""


def _run_preview(marker: str) -> dict:
    proc = subprocess.run([_NODE, "-e", _PREVIEW_HARNESS, str(ATTACH_JS), marker],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@needs_node
def test_preview_without_page_marker_never_asks_for_superseded():
    """생산·시공(표시 없음): 덮어쓴 전역 함수도 인자를 붙이지 않는다."""
    out = _run_preview("0")
    assert out["calls"] == ["/api/orders/7/attachments"]


@needs_node
def test_preview_with_page_marker_asks_for_superseded_and_keeps_cache_clean():
    """주문 대시보드(표시 있음): 인자를 붙이고, 옛 도면은 뒤로, 공용 캐시에는 옛 도면을 넣지 않는다."""
    out = _run_preview("1")
    assert out["calls"] == ["/api/orders/7/attachments?include_superseded=1"]
    assert out["drawing"] == [2, 1]
    assert out["cache"] == [2]


def _extract_function(src: str, name: str) -> str:
    """``function <name>(`` 선언을 중괄호 짝으로 잘라 낸다(테스트 전용 소형 추출기)."""
    start = src.index(f"function {name}(")
    depth, i = 0, src.index("{", start)
    while True:
        ch = src[i]
        depth += ch == "{"
        depth -= ch == "}"
        i += 1
        if depth == 0:
            return src[start:i]


_VIEWER_HARNESS = r"""
const vm = require('vm');
const [fnSrc, clicked] = process.argv.slice(1);
let opened = null;
const ctx = { String, Number, Array, Object };
ctx.__attachmentsByCategory = { drawing: [
  { id: 1, is_superseded: false }, { id: 2, is_superseded: false },
  { id: 3, is_superseded: true }, { id: 4, is_superseded: true },
] };
ctx.normalizeAttachmentCategory = (c) => c;
ctx.showAttachmentAtIndex = (i) => { opened = { ids: ctx.__currentAttachmentList.map((a) => a.id), index: i }; };
vm.createContext(ctx);
vm.runInContext(fnSrc, ctx);
ctx.openAttachmentFromCategory('drawing', Number(clicked));
process.stdout.write(JSON.stringify(opened));
"""


def _run_viewer(clicked: int) -> dict:
    src = CORE_JS.read_text(encoding="utf-8")
    fn_src = "\n".join(_extract_function(src, n) for n in ("openAttachmentFromCategory",)
                       ) + "\nvar __currentAttachmentList = []; var __activeAttachmentCategory = '';"
    proc = subprocess.run([_NODE, "-e", _VIEWER_HARNESS, fn_src, str(clicked)],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@needs_node
def test_dashboard_viewer_keeps_current_and_superseded_apart():
    """현재 도면을 누르면 현재끼리만, 옛 도면을 누르면 옛 도면끼리만 넘긴다(누른 것이 시작점)."""
    assert _run_viewer(1) == {"ids": [1, 2], "index": 1}
    assert _run_viewer(3) == {"ids": [3, 4], "index": 1}


def test_order_edit_viewer_groups_by_superseded():
    """주문 수정 화면 뷰어 묶음도 누른 첨부와 같은 무리만 담는다."""
    fn = _extract_function(SHARED_JS.read_text(encoding="utf-8"), "erpBuildAttachmentFullscreenPayload")
    assert "is_superseded" in fn


def test_attachment_preview_click_handled_once_per_page():
    """생산·시공 페이지에서는 ERP 쪽 위임이 비키고, 두 페이지 처리기는 자기 페이지에서만 돈다."""
    detail = DETAIL_DOM_JS.read_text(encoding="utf-8")
    branch = detail[detail.index("closest('.erp-btn-attachments-preview')"):]
    branch = branch[:branch.index("openAttachmentsPreview(Number(orderId))")]
    assert ".erp-dashboard-production" in branch and ".erp-construction-dashboard" in branch

    prod = (ROOT / "templates/production/partials/scripts.html").read_text(encoding="utf-8")
    prod_branch = prod[prod.index("closest('.erp-btn-attachments-preview')"):]
    assert ".erp-dashboard-production" in prod_branch[:prod_branch.index("openAttachmentsPreview(")]

    constr = (ROOT / "static/js/construction/dashboard.js").read_text(encoding="utf-8")
    constr_branch = constr[constr.index("closest('.erp-btn-attachments-preview')"):]
    assert ".erp-construction-dashboard" in constr_branch[:constr_branch.index("openAttachmentsPreview(")]


def test_preview_modal_caption_marks_superseded():
    """주문 수정 화면 미리보기 창 캡션에도 '교체됨' 배지가 붙는다."""
    fn = _extract_function(SHARED_JS.read_text(encoding="utf-8"), "erpOpenAttachmentPreview")
    assert len(re.findall(r"erpSupersededBadgeHtml\(a\)", fn)) >= 2
