"""도면 마법사 V2 — 화면 갈래(쿠키 · ?ui=) · V2 템플릿 요소 · 엔진 연결 계약.

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 · §2 · §6
- 같은 라우트가 ?ui=v1|v2 → 쿠키 dws_ui → v1 순으로 갈래를 고른다(지금 쓰는 사람 화면은 그대로 V1).
- V2 아래 띠는 V1 양식과 같은 폼 칸 이름을 쓴다(자동 채움 · 편집이 그대로 돈다).
- wizard.js 는 V2 일 때 V1 표 엔진 · V1 자동 배치를 돌리지 않고 window.FomsWizardCore 로 V2 모듈과 잇는다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
V2_FORM = (ROOT / "templates/drawing/partials/wizard_v2_form.html").read_text(encoding="utf-8")
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
V2_SCRIPTS = ["v2-slots.js", "v2-pack.js", "v2-layout.js", "v2-plan.js", "v2-paper.js", "v2-notes.js", "v2-left.js",
              "v2-right.js", "v2-chrome.js", "v2-shell.js"]


def _login(client, username, role="ADMIN", team="DRAWING"):
    user = User(username=username, password=generate_password_hash("x"), role=role, team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order():
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="브이투", phone="010-1111-2222",
                  address="대구", product="붙박이장", status="DRAWING", manager_name="영업", is_erp_order=True,
                  structured_data={"parties": {"customer": {"name": "브이투"}}})
    db_session.add(order)
    db_session.commit()
    return order.id


def _page(client, oid, query="", cookie=None):
    if cookie is not None:
        client.set_cookie("dws_ui", cookie, path="/erp/drawing-workbench")
    res = client.get(f"/erp/drawing-workbench/{oid}/wizard{query}")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    marker = '<script id="drawing-wizard-config" type="application/json">'
    start = body.index(marker) + len(marker)
    return body, json.loads(body[start:body.index("</script>", start)])


def test_default_is_v1_with_switch_button(client):
    _login(client, "v2ui_a")
    body, cfg = _page(client, _order())
    assert cfg["ui"] == "v1" and 'data-ui="v1"' in body
    assert 'class="dws-v2' not in body and 'id="dws-v2-left"' not in body and "v2-shell.js" not in body
    assert 'class="dws-header"' in body                         # V1 양식 그대로
    assert 'data-dws-ui-switch="v2"' in body and "wizard-ui-switch.js" in body


def test_cookie_and_query_pick_v2_and_v1(client):
    _login(client, "v2ui_b")
    oid = _order()
    body, cfg = _page(client, oid, cookie="v2")
    assert cfg["ui"] == "v2" and 'class="dws-v2 dws-v2-auto"' in body
    body1, cfg1 = _page(client, oid, query="?ui=v1")             # 주소가 쿠키보다 먼저
    assert cfg1["ui"] == "v1" and 'id="dws-v2-left"' not in body1
    _, cfg2 = _page(client, oid, cookie="v9")                     # 모르는 값 = v1
    assert cfg2["ui"] == "v1"
    _, cfg3 = _page(client, oid, query="?ui=v2", cookie="v1")
    assert cfg3["ui"] == "v2"


def test_v2_page_has_layout_regions_scripts_and_form(client):
    _login(client, "v2ui_c")
    body, _ = _page(client, _order(), query="?ui=v2")
    for el_id in ["dws-v2-left", "dws-v2-right", "dws-v2-slots", "dws-v2-badges", "dws-v2-banner", "dws-v2-drop", "dws-v2-zoom",
                  "dws-v2-cards", "dws-v2-unsorted", "dws-v2-kind", "dws-v2-templates", "dws-v2-seen", "dws-v2-toggles",
                  "dws-v2-relayout", "dws-v2-more", "dws-v2-more-menu", "dws-v2-tabstatus", "dws-v2-pagetotal", "dws-logo-cell"]:
        assert f'id="{el_id}"' in body, el_id
    assert 'data-v2-mode="auto"' in body and 'data-v2-mode="free"' in body
    assert 'data-dws-ui-switch="v1"' in body
    assert "wizard-v2.css" in body and 'class="dws-header"' not in body
    pos = [body.index(f"js/drawing/{name}") for name in V2_SCRIPTS]
    assert pos == sorted(pos) and body.index("js/drawing/wizard.js") < pos[0]   # 엔진 → 계산 → 화면 → 잇기(v2-shell 마지막)
    for menu_for in ["dws-btn-save-all", "dws-btn-export-all", "dws-btn-version-history", "dws-btn-autofill", "dws-btn-calc",
                     "dws-btn-export-png"]:
        assert f'data-v2-for="{menu_for}"' in body and f'id="{menu_for}"' in body   # ⋯ 메뉴는 원래 단추를 눌러 준다


def test_v2_form_keeps_every_v1_form_key_and_check():
    v1_form = TPL[TPL.index('<div class="dws-form" id="dws-form">'):TPL.index("{% endif %}", TPL.index('<div class="dws-form" id="dws-form">'))]
    keys = lambda s: sorted(set(re.findall(r'data-dws-form-key="([a-z_0-9]+)"', s)))
    checks = lambda s: sorted(set(re.findall(r'data-dws-check="([a-z_]+)"', s)))
    assert keys(V2_FORM) == keys(v1_form)
    assert checks(V2_FORM) == checks(v1_form)
    assert "style=" not in V2_FORM


def test_wizard_js_bridges_v2_without_v1_layout_engines():
    assert "var UI = CONFIG.ui === 'v2' ? 'v2' : 'v1';" in JS
    init = JS[JS.index("  function init() {"):]
    assert init.index("if (UI === 'v1') {") < init.index("cacheLayoutEls();") < init.index("exposeCore();") < init.index("load();")
    arrange = JS[JS.index("  function autoArrangeImages("):]
    assert arrange.index("if (UI === 'v2') { emitCore('arrange'") < arrange.index("partArrangePlan(s)")
    batch = JS[JS.index("  function finishPartBatch("):JS.index("  function finishPartBatch(") + 900]
    assert "if (UI === 'v2') {" in batch and "emitCore('batch'" in batch
    assert "if (s.form && s.form.v2_layout) { delete s.form.v2_layout; }" in JS   # V1 배치가 다시 놓으면 칸 머리 숨김
    for ev in ["'change'", "'render'", "'sheet'", "'loaded'", "'labels'", "'added'"]:
        assert "emitCore(" + ev in JS, ev
    core = JS[JS.index("  function exposeCore() {"):JS.index("emitCore('ready'")]
    for api in ["sheet:", "recordUndo:", "markDirty:", "redraw:", "items:", "baseline:", "split:", "importPhoto:", "setPartLabel:",
                "addFiles:", "select:", "normalize:", "rid:", "save:", "editing:"]:
        assert api in core, api


def test_empty_saved_state_keeps_server_updated_at_as_base():
    """시트를 다 지우고 저장한 주문 — 다시 열어 처음 저장할 때 409(다른 사용자가 먼저 저장)로 막히지 않게 서버 시각을 기준으로 둔다."""
    load = JS[JS.index("  function load() {"):JS.index("  function handleConflict(")]
    empty = load[load.index("state = { v: 1, sheets: [] };"):]
    assert empty.index("baseUpdatedAt = (d.state && d.state.updated_at) || null;") < 200
