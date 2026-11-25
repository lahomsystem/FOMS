"""통째 작업에서 막힌 도면만 빼고 처리 — 화면 JS(Node) 쪽(설계서 2026-11-25 §2-4 · D1 검토 판결 B · C · 둘째 판 2).

서버가 그린 진짜 조각 위에서 생산 화면 JS 를 Node(가짜 DOM ``tests/support/production_fake_dom.js``)로 돌려, 서버 자료가 창 · 알림까지
가는지 본다(글자 찾기가 아니라 함수 실행). 쓰기 쪽 · 서버 판정은 ``test_production_step_expand.py``.

* '내 공정' 폰 줄 확인 창 본문 "이 주문의 도면 3장 중 2장이 재단 완료로 처리돼요. 도면 2는 고치는 중이라 빼요."
* 풀어 쓴 [끝] 뒤: 폰 · PC 줄은 알림 "도면 3장 중 2장을 …" + 줄은 그 자리에서 "도면 2 고치는 중"(다시 받기 0), 가로 판은 [되돌리기] 없이
  알림 글만 — 둘 다 [되돌리기]와 같은 8초 시계로 지운다.
* PC 공정 칸 창 [모두 완료 처리] 확인 창이 서버 ``fix`` 로 새 본문(막힌 도면 없는 주문은 지금 글).

되돌리면 실패: 확인 창이 지금 글 · 알림이 "끝냈어요" · 되돌리기가 남음 · 알림이 안 지워짐 · PC 창이 fix 를 버림. 이름은 지어낸 값.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from foms.services.production.pc_view import EDIT_COOKIE
from tests.domains.test_production_my_steps_confirm import NODE_CHECK, PHONE
from tests.domains.test_production_step_expand import ASK, DONE, PC, _fixing
from tests.support.production_home_step_panel_seed import HOME, SHELL, TABLET, add_order, get_html, set_cookies
from tests.support.production_home_step_panel_seed import login as home_login
from tests.support.production_part_claim_seed import check_step, login, make_user

ROOT = Path(__file__).resolve().parents[2]
FAKE_DOM = (ROOT / "tests/support/production_fake_dom.js").as_posix()


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _node(tmp_path, script: str, *args: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    path = tmp_path / "check.js"
    path.write_text(script, encoding="utf-8")
    proc = subprocess.run([node, str(path), *args], capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


def test_node_my_steps_row_dialog_shows_the_new_body(client, cohort, tmp_path):
    ready = add_order("가짜고침집", 1, pngs=3).id
    _fixing(ready, 1)
    bare = add_order("가짜빈집", 2, pngs=0).id
    home_login(client)
    set_cookies(client, PHONE)
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    path = tmp_path / "row.html"
    path.write_text(page, encoding="utf-8")
    want = {"mode": "row", "first": ready, "bare": bare, "key": "cut", "title": "재단 완료할까요?", "text": ASK}
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    proc = subprocess.run([node, str(NODE_CHECK), str(path), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


_RUN = """
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const { fakeDom } = require(%(dom)s);
const D = fakeDom();
const body = D.parse(fs.readFileSync(process.argv[2], 'utf8'));
const answer = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const calls = { fetch: [], reload: 0, replace: [] };
const document = { body, readyState: 'complete', referrer: '', querySelector: (s) => body.querySelector(s),
  querySelectorAll: (s) => body.querySelectorAll(s), getElementById: (id) => body.querySelector('#' + id),
  createElement: (t) => D.makeEl(t.toLowerCase()), addEventListener(t, f) { (D.docListeners[t] = D.docListeners[t] || []).push(f); },
  removeEventListener() {}, contains: (n) => body.contains(n), dispatchEvent() { return true; }, importNode: (n) => n };
const slow = []; // 5초 넘는 시계(알림 · 되돌리기 8초 · 다시 받기 10초)는 잡아 두고 시험이 부른다
const later = (f, ms) => (ms >= 5000 ? (slow.push({ f, ms }), 0) : setTimeout(f, ms));
const ctx = { console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout: later,
  clearTimeout, setInterval: () => 0, clearInterval() {}, document, navigator: { onLine: true }, performance: { timeOrigin: Date.now() },
  location: { href: 'http://127.0.0.1/erp/production/home?tab=steps', origin: 'http://127.0.0.1', pathname: '/erp/production/home',
    search: '?tab=steps', reload() { calls.reload += 1; }, replace(u) { calls.replace.push(u); }, assign(u) { calls.replace.push(u); } },
  history: { state: null, replaceState() {} }, localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  fetch: (url, opts) => { calls.fetch.push({ url, method: (opts || {}).method || 'GET' });
    const hit = Object.keys(answer).find((k) => url.indexOf(k) === 0);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(hit ? answer[hit] : { success: true, data: { items: [] } }) }); },
  ERPUtils: { safeJsonParse: (v, fb) => { try { return JSON.parse(v); } catch (e) { return fb; } } } };
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
const home = body.querySelector('[data-foms-prod-home]');
if (home) { home.style = { setProperty() {} }; }
const flush = () => new Promise((r) => setImmediate(r));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
JSON.parse(process.argv[4]).forEach((rel) => vm.runInContext(fs.readFileSync(rel, 'utf8'), ctx, { filename: rel }));
const $ = (s) => body.querySelector(s);
const dlg = () => $('[data-foms-sheet-confirm]');
(async () => {
%(steps)s
  console.log('OK');
  process.exit(0);
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
"""


def _run_js(tmp_path, page: str, answer: dict, scripts: list[str], steps: str) -> None:
    (tmp_path / "page.html").write_text(page, encoding="utf-8")
    (tmp_path / "answer.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
    script = _RUN % {"dom": json.dumps(FAKE_DOM), "steps": steps}
    _node(tmp_path, script, str(tmp_path / "page.html"), str(tmp_path / "answer.json"), json.dumps(scripts))


def test_node_row_finish_after_expand_shows_the_done_words_keeps_the_row_and_no_undo(client, cohort, tmp_path):
    """판결 B — 폰 · PC 줄 [끝]: 서버 글 재료로 알림 "도면 3장 중 2장을 …", 줄은 그 자리에서 [끝] → "도면 2 고치는 중"(다시 받기 0)."""
    ready = add_order("가짜고침집", 1, pngs=3).id
    _fixing(ready, 1)
    home_login(client)
    set_cookies(client, PHONE)
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    answer = check_step(client, ready, "cut", True).get_json()  # 진짜 응답(같은 주문 — 화면은 누르기 전 조각)
    steps = f"""
  const btn = $('[data-foms-home-step-done][data-order-id="{ready}"]');
  btn.click(); await flush(); await flush();
  assert.ok(!dlg().hidden);
  assert.strictEqual(dlg().querySelector('[data-foms-sheet-confirm-body]').textContent, {json.dumps(ASK, ensure_ascii=False)});
  await sleep(450);
  dlg().querySelector('[data-foms-sheet-confirm-yes]').click(); await flush(); await flush(); await flush();
  assert.strictEqual(calls.fetch.filter((c) => c.method === 'POST').length, 1);
  assert.strictEqual($('[data-foms-home-status]').textContent, {json.dumps(DONE, ensure_ascii=False)});
  assert.strictEqual(calls.reload, 0, '줄은 그 자리 — 다시 받기 없음');
  const row = $('[data-foms-home-qrow="{ready}"]');
  assert.ok(!row.querySelector('[data-foms-home-step-done]') && row.classList.contains('is-revise'));
  assert.strictEqual(row.querySelector('.fph-qr__hold').textContent, '도면 2 고치는 중');
  const clock = slow.filter((t) => t.ms === 8000);
  assert.strictEqual(clock.length, 1, '알림 글 시계 = 8초(되돌리기와 같다)');
  clock[0].f();
  assert.strictEqual($('[data-foms-home-status]').textContent, '', '8초 뒤 알림 글을 지운다');
"""
    _run_js(tmp_path, page, {f"/api/orders/{ready}/production/steps": answer},
            ["static/js/production/foms-production-home.js", "static/js/production/foms-production-sheet-parts.js"], steps)


def test_node_panel_finish_after_expand_has_no_undo_and_says_what_was_done(client, cohort, tmp_path):
    """판결 B — 가로 판 [<공정> 완료]: 8초 [되돌리기] 없음 · 상태 줄 "{이름} {공정} 완료" 대신 알림 글."""
    ready = add_order("가짜고침집", 1, pngs=3).id
    nxt = add_order("가짜다음집", 2, pngs=0).id
    _fixing(ready, 1)
    home_login(client)
    set_cookies(client, TABLET)
    page = get_html(client, f"{HOME}?tab=steps&order={ready}&view=fragment", SHELL)
    answer = check_step(client, ready, "cut", True).get_json()
    steps = f"""
  const fin = $('[data-foms-step-pane="{ready}"]').querySelector('[data-foms-step-finish]');
  fin.click(); await flush(); await flush();
  assert.strictEqual(dlg().querySelector('[data-foms-sheet-confirm-body]').textContent, {json.dumps(ASK, ensure_ascii=False)});
  await sleep(450);
  dlg().querySelector('[data-foms-sheet-confirm-yes]').click(); await flush(); await flush(); await flush();
  const status = $('[data-foms-home-status]');
  assert.strictEqual(status.textContent, {json.dumps(DONE, ensure_ascii=False)});
  assert.ok(!status.querySelector('[data-foms-step-undo]') && !status.classList.contains('is-undo'), '되돌리기 없음');
  assert.ok(calls.replace.length === 1 && calls.replace[0].indexOf('order={nxt}') > 0, '다음 손님으로');
  const clock = slow.filter((t) => t.ms > 7000 && t.ms <= 8000);
  assert.strictEqual(clock.length, 1, '알림 글도 되돌리기와 같은 8초 시계');
  clock[0].f();
  assert.strictEqual(status.textContent, '', '8초 뒤 알림 글을 지운다');
"""
    scripts = ["static/js/production/foms-production-home-steppane.js", "static/js/production/foms-production-home-steps.js",
               "static/js/production/foms-production-home.js", "static/js/production/foms-production-sheet-parts.js"]
    _run_js(tmp_path, page, {f"/api/orders/{ready}/production/steps": answer}, scripts, steps)


def test_node_pc_window_all_button_asks_with_the_new_body(client, cohort, tmp_path):
    """판결 C — PC 공정 칸 창 [모두 완료 처리]: 서버 자료 fix 가 확인 창까지 간다(막힌 도면 없는 주문은 지금 글). PC 로 연 작업 시트에서."""
    ready, plain = add_order("가짜고침집", 1, pngs=3).id, add_order("가짜도면집", 2, pngs=3).id
    _fixing(ready, 1)
    login(client, make_user("가짜관리", team="CS", role="ADMIN"))
    set_cookies(client, PC)
    client.set_cookie(EDIT_COOKIE, str(int(time.time())), domain="localhost", path="/erp/production")
    scripts = ["static/js/production/foms-production-sheet-parts.js", "static/js/production/foms-production-pc-sheet-write.js",
               "static/js/production/foms-production-pc-sheet.js"]
    for oid, text in ((ready, ASK), (plain, "이 주문의 도면 3장이 모두 재단 완료로 처리돼요.")):
        page = get_html(client, f"/erp/production/sheet/{oid}")
        answer = {f"/api/production/part-sheet?order_id={oid}&part=cut":
                  client.get(f"/api/production/part-sheet?order_id={oid}&part=cut").get_json()}
        assert ("fix" in answer[next(iter(answer))]["data"]) is (oid == ready)
        steps = f"""
  ctx.FomsPcSheet.open($('[data-foms-pc-sheet="cut"]'));
  await flush(); await flush(); await flush();
  const all = $('[data-foms-pc-sheet-act="all"]');
  assert.ok(all, '[모두 작업] 단추');
  all.click(); await flush(); await flush();
  assert.ok(!dlg().hidden);
  assert.strictEqual(dlg().querySelector('[data-foms-sheet-confirm-body]').textContent, {json.dumps(text, ensure_ascii=False)});
"""
        (tmp_path / str(oid)).mkdir()
        _run_js(tmp_path / str(oid), page, answer, scripts, steps)
