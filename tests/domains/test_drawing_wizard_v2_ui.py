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
V2_SCRIPTS = ["v2-slots.js", "v2-pack.js", "v2-hero.js", "v2-layout.js", "v2-plan.js", "v2-paper.js", "v2-notes.js", "v2-left.js",
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
                  "dws-v2-relayout", "dws-v2-rearrange", "dws-v2-unpin", "dws-v2-more", "dws-v2-more-menu", "dws-v2-tabstatus",
                  "dws-v2-pagetotal", "dws-logo-cell"]:
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


def test_v2_relabel_releases_pin_and_remembers_ai_slot_guess():
    """사람이 종류를 고르면 손으로 옮긴 고정을 풀어 새 칸으로(자동 배치 모드) · AI 칸 짐작은 폼 v2_ai 에 · 칸 이름은 제품 이름이 아니다."""
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    wire = shell[shell.index("core.on('labels'"):]
    assert wire.index("rememberGuess(d)") < wire.index("release(d.ids || [d.id], mode === 'auto')") < wire.index("scheduleArrange('labels')")
    rel = shell[shell.index("  function release("):shell.index("  function pickTemplate(")]
    assert "if (unpin && o.part && !o.locked && S.moved(o)) { o.part.arr = [o.x, o.y, o.w, o.h]; }" in rel
    remember = shell[shell.index("  function rememberGuess("):shell.index("  function release(")]
    assert "p.label === '미분류' && p.src === 'ai' && code && d.famConf >= core.threshold()" in remember
    for name in ("v2-paper.js", "v2-left.js"):
        src = (ROOT / "static/js/drawing" / name).read_text(encoding="utf-8")
        assert "product_name" not in src and "FomsV2Slots.title(" in src, name


def _fn(src: str, head: str, size: int = 1600) -> str:
    start = src.index(head)
    return src[start:start + size]


def test_engine_emits_removed_copies_and_trim_for_v2_rearrange():
    """스테이징 주문 4385(2026-10-27): 지우기 · 사본 · 자르기도 V2 가 알아야 다시 놓는다(V1 은 듣는 곳이 없다)."""
    delete = _fn(JS, "  function deleteSelected() {", 900)
    assert delete.index("recordUndo();") < delete.index("markDirty();") < delete.index("emitCore('removed', { ids: ids, images: images });")
    copy = _fn(JS, "  function freshCopy(o) {", 300)
    assert "if (o.type === 'image' && o.part && o.part.arr) { delete o.part.arr; }" in copy   # 사본은 처음부터 고정이 아니다
    for head in ("  function pasteClipObjects() {", "  function duplicateSelectedInPlace() {"):
        body = _fn(JS, head, 1300)
        assert "freshCopy(JSON.parse(JSON.stringify(" in body and "emitCopiesAdded(ids);" in body, head
    trim = _fn(JS, "  function trimSelectedImage() {", 2700)
    assert "tol = window.FomsV2Slots ? window.FomsV2Slots.MOVE_TOL : 1;" in trim             # V2 고정 판정과 같은 허용 폭
    assert trim.index("var laid =") < trim.index("if (laid) { cur.part.arr = [cur.x, cur.y, cur.w, cur.h]; }")
    assert "emitCore('trimmed', { id: cur.id });" in trim
    events = JS[JS.index("[8] V2 화면 연결"):JS.index("  function emitCore(name, data) {")]
    assert "removed(" in events and "trimmed(" in events


def test_v2_shell_rearranges_after_delete_mode_click_and_late_labels():
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    wire = shell[shell.index("  function wire() {"):shell.index("  function init() {")]
    assert "core.on('removed'" in wire and "scheduleArrange('removed')" in wire and "core.on('trimmed'" in wire
    assert "batched[d.id]" in wire                                          # 묶음 배치 뒤 늦게 온 AI 이름표
    arrange = shell[shell.index("  function arrange(reason, opts) {"):shell.index("  function scheduleArrange(")]
    assert arrange.index("FomsV2Plan.diff(") < arrange.index("if (d.any && o.undo) { core.recordUndo(); }")   # 헛 되돌리기 없음
    assert "arrange(fromUser ? 'mode' : 'open'" in shell
    chrome = (ROOT / "static/js/drawing/v2-chrome.js").read_text(encoding="utf-8")
    assert "api.setMode(b.getAttribute('data-v2-mode'), true)" in chrome and "arrangeText: arrangeText" in chrome


def test_v2_assets_pinned_after_rearrange_fix():
    for asset in ("css/contexts/drawing/wizard-v2.css", "js/drawing/wizard.js", "js/drawing/v2-slots.js", "js/drawing/v2-layout.js",
                  "js/drawing/v2-plan.js", "js/drawing/v2-paper.js", "js/drawing/v2-right.js", "js/drawing/v2-chrome.js",
                  "js/drawing/v2-shell.js"):
        assert any(f"{asset}') }}}}?v={v}" in TPL for v in ("20261027d", "20261027e", "20261027f", "20261028a")), asset
    right = (ROOT / "templates/drawing/partials/wizard_v2_right.html").read_text(encoding="utf-8")
    assert right.index('class="dws-v2-right-body"') < right.index('class="dws-v2-right-foot"')   # 바닥은 굴러가는 몸통 밖(늘 보임)
    assert "style=" not in right and 'id="dws-v2-rearrange"' in TPL


def test_engine_emits_moved_after_drag_or_resize_and_v2_rearranges_around_it():
    """사용자 보고(2026-10-28, 스테이징 주문 4385): 메인을 키우면 나머지가 저절로 맞춰져야 하는데 겹쳤다 —
    끌기 · 크기 바꾸기 · 돌리기를 마치면 코어가 moved 를 알리고, V2 자동 배치 모드가 고정이 된 그 그림을 비켜 다시 놓는다."""
    for head in ("    node.on('dragend', function () {", "    node.on('transformend', function () {"):
        line = JS[JS.index(head):JS.index("\n", JS.index(head))]
        assert line.index("commitNode(node);") < line.index("emitMoved([node]);"), head
    multi_drag = _fn(JS, "    transformer.on('dragend', function () {", 500)
    assert multi_drag.index("selectedNodes().forEach(commitNode);") < multi_drag.index("emitMoved(selectedNodes());")
    multi_tf = _fn(JS, "    transformer.on('transformend', function () {", 420)
    assert multi_tf.index("nodes.forEach(commitNode);") < multi_tf.index("emitMoved(nodes);")
    emit = _fn(JS, "  function emitMoved(nodes) {", 400)
    assert "o.type === 'image'" in emit and "emitCore('moved', { ids: ids });" in emit   # 글자 · 도형만 옮긴 것은 알리지 않는다
    assert "dragging: function () { return !!dragActive; }" in JS
    events = JS[JS.index("[8] V2 화면 연결"):JS.index("  function emitCore(name, data) {")]
    assert "moved(" in events
    shell = (ROOT / "static/js/drawing/v2-shell.js").read_text(encoding="utf-8")
    wire = shell[shell.index("  function wire() {"):shell.index("  function init() {")]
    assert "core.on('moved'" in wire and "scheduleArrange('moved')" in wire and "S.isFixed(o, settings)" in wire
    assert "settings.lockMoved" in wire and "laidNow()" in wire
    assert "if (core.editing() || core.dragging()) { scheduleArrange(reason); return; }" in shell
    assert "if (reason !== 'moved') { core.select([]); }" in shell
    chrome = (ROOT / "static/js/drawing/v2-chrome.js").read_text(encoding="utf-8")
    assert "moved: 1 }" in chrome and "옮긴 그림을 비켜 나머지" in chrome

