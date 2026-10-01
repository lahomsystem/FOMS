"""긴급 호출 공용 창 JS(static/js/foms/urgent-call.js)를 Node 로 실제 실행한다(SPEC 2026-10-01 §4 · §6).

문자열 존재가 아니라 동작을 본다: 어떤 요청을 어떤 본문으로 보냈나 · 버튼 글자·잠김 · 주문 줄 상태.
- 주문 미리 고르기(버튼 data-order-id) → 보낼 때 order_id 가 실린다. × 로 빼면 order_id 가 없다.
- 맨 위 줄 ⚡ 는 대시보드에서 펼쳐 둔 주문 상세를 미리 고른다.
- 버튼 글자 3상태: 받을 사람을 골라 주세요 → 사유를 적어 주세요 → ○○에게 보내기.
- 주문 검색은 통합 검색(group=all)을 2글자부터 부르고, 결과를 누르면 그 주문이 골라진다.
"""

from __future__ import annotations

from tests.support.drawing_customer_js_harness import run_js

JS = "static/js/foms/urgent-call.js"

DOM = r"""
const root = makeEl({ id: 'fomsUrgentCallModal' });
const el = {
  picked: makeEl({ cls: ['d-none'] }), add: makeEl({}), search: makeEl({ cls: ['d-none'] }),
  label: makeEl({}), q: makeEl({ attrs: { 'data-foms-urgent-order-q': '' } }), results: makeEl({}),
  teams: makeEl({}), people: makeEl({}), message: makeEl({ attrs: { 'data-foms-urgent-message': '' } }),
  error: makeEl({ cls: ['d-none'] }), send: makeEl({ disabled: true, cls: ['btn-secondary'] }),
  clear: makeEl({}), addBtn: null,
};
Object.assign(root._sel, {
  '[data-foms-urgent-order-picked]': el.picked, '[data-foms-urgent-order-add]': el.add,
  '[data-foms-urgent-order-search]': el.search, '[data-foms-urgent-order-label]': el.label,
  '[data-foms-urgent-order-q]': el.q, '[data-foms-urgent-order-results]': el.results,
  '[data-foms-urgent-teams]': el.teams, '[data-foms-urgent-people]': el.people,
  '[data-foms-urgent-message]': el.message, '[data-foms-urgent-error]': el.error,
  '[data-foms-urgent-send]': el.send,
});
el.message._closest['#fomsUrgentCallModal'] = root;
el.q._closest['#fomsUrgentCallModal'] = root;
el.send._closest['[data-foms-urgent-send]'] = el.send; root._inside.push(el.send);
el.clear._closest['[data-foms-urgent-order-clear]'] = el.clear; root._inside.push(el.clear);
el.add._closest['[data-foms-urgent-order-add]'] = el.add; root._inside.push(el.add);
const posts = [];
window.FOMSNotificationWrite = { fetch: async function (url, opts) {
  posts.push([url, JSON.parse(opts.body)]);
  return Resp(200, { success: true, message: '구범진님에게 긴급 호출을 보냈습니다.' });
} };
route('/erp/api/urgent-targets', function () { return Resp(200, { success: true, targets: [
  { id: 20, name: '김세연', team: 'CS', team_label: 'CS(라홈팀/하우드팀)', role: 'MANAGER' },
  { id: 52, name: '구범진', team: 'DRAWING', team_label: '도면팀', role: 'STAFF' },
  { id: 42, name: '김한비', team: 'DRAWING', team_label: '도면팀', role: 'STAFF' },
  { id: 9, name: '팀없음', team: null, team_label: '기타', role: 'STAFF' }] }); });
route('/api/foms/search', function (url) { return Resp(200, { success: true, data: {
  customer: [{ order_id: 4491, title: 'CLAUDE-TEST', phone: '010-0000-0000', address: '서울', stage_label: '주문접수' }],
  order: [{ order_id: 4491, title: '#4491 · CLAUDE-TEST' }, { order_id: 4465, title: '#4465 · CLAUDE-TEST-2', stage_label: '도면' }],
  drawing: [] } }); });
function teamButtons() { return el.teams.children.map(function (b) { return [b.getAttribute('data-foms-urgent-team'), b.textContent, b.className.indexOf('btn-dark') !== -1]; }); }
function clickRendered(node, sel) { node._closest[sel] = node; root._inside.push(node); fire('click', node); }
// 가짜 DOM 은 textContent='' 로 children 을 비우지 않는다 — 다시 그린 최신 버튼(마지막 것)을 본다.
function person(id) { return el.people.children.filter(function (b) { return b.getAttribute('data-foms-urgent-target') === String(id); }).pop(); }
"""


def test_order_button_prefills_order_team_message_and_sends_with_order_id():
    driver = DOM + r"""
loadSources();
const opener = makeEl({ attrs: { 'data-order-id': '4491', 'data-urgent-order-label': '#4491 CLAUDE-TEST',
  'data-urgent-team': 'DRAWING', 'data-urgent-message': '확인 부탁' } });
opener._closest['[data-foms-urgent-call]'] = opener;
fire('click', opener); await flush();
const s0 = { label: el.label.textContent, pickedShown: !hidden(el.picked), addShown: !hidden(el.add),
  teams: teamButtons().slice(-3), people: el.people.children.map(function (b) { return b.textContent; }).slice(-2),
  send: el.send.textContent, locked: el.send.disabled };
clickRendered(person(52), '[data-foms-urgent-target]');
const s1 = { send: el.send.textContent, locked: el.send.disabled, danger: el.send.classList.contains('btn-danger'),
  selected: person(52).className.indexOf('is-selected') !== -1, pressed: person(52).getAttribute('aria-pressed') };
fire('click', el.send); await flush();
out({ s0: s0, s1: s1, posts: posts });
"""
    r = run_js([JS], driver)
    assert [c["url"] for c in r["calls"]] == ["/erp/api/urgent-targets"]  # 라벨을 실었으니 검색 안 함
    assert r["s0"] == {
        "label": "#4491 CLAUDE-TEST", "pickedShown": True, "addShown": False,
        "teams": [["CS", "CS", False], ["DRAWING", "도면", True], ["_ETC", "기타", False]],
        "people": ["구범진", "김한비"],
        "send": "받을 사람을 골라 주세요", "locked": True,
    }
    assert r["s1"] == {"send": "구범진에게 보내기", "locked": False, "danger": True, "selected": True, "pressed": "true"}
    assert r["posts"] == [["/erp/api/urgent-call", {"target_user_id": 52, "message": "확인 부탁", "order_id": 4491}]]
    assert ["hide", "fomsUrgentCallModal"] in r["modalOps"]
    assert r["toasts"] == ["구범진님에게 긴급 호출을 보냈습니다."]


def test_clearing_order_sends_without_order_id_and_message_gates_send():
    driver = DOM + r"""
loadSources();
window.fomsUrgentCall.open({ orderId: '4491', orderLabel: '#4491 CLAUDE-TEST' }); await flush();
fire('click', el.clear);
const afterClear = { pickedShown: !hidden(el.picked), addShown: !hidden(el.add) };
clickRendered(el.teams.children[1], '[data-foms-urgent-team]');
clickRendered(person(42), '[data-foms-urgent-target]');
const noReason = { send: el.send.textContent, locked: el.send.disabled };
el.message.value = '  지금 와 주세요 '; fire('input', el.message);
const ready = el.send.textContent;
fire('click', el.send); await flush();
out({ afterClear: afterClear, noReason: noReason, ready: ready, posts: posts });
"""
    r = run_js([JS], driver)
    assert r["afterClear"] == {"pickedShown": False, "addShown": True}
    assert r["noReason"] == {"send": "사유를 적어 주세요", "locked": True}
    assert r["ready"] == "김한비에게 보내기"
    assert r["posts"] == [["/erp/api/urgent-call", {"target_user_id": 42, "message": "지금 와 주세요"}]]


def test_header_bolt_prefills_expanded_dashboard_order_and_resolves_label():
    driver = DOM + r"""
globalSel['.collapse.show[id^="order-detail-collapse-"]'] = makeEl({ id: 'order-detail-collapse-4491' });
loadSources();
const bolt = makeEl({}); bolt._closest['[data-foms-urgent-open]'] = bolt;
fire('click', bolt); await flush();
out({ label: el.label.textContent, pickedShown: !hidden(el.picked) });
"""
    r = run_js([JS], driver)
    urls = [c["url"] for c in r["calls"]]
    assert "/api/foms/search?group=all&q=4491" in urls  # 고객명을 몰라 번호로 찾아 채운다
    assert r["label"] == "#4491 CLAUDE-TEST"
    assert r["pickedShown"] is True


def test_header_bolt_without_context_opens_with_no_order():
    driver = DOM + r"""
loadSources();
const bolt = makeEl({}); bolt._closest['[data-foms-urgent-open]'] = bolt;
fire('click', bolt); await flush();
out({ pickedShown: !hidden(el.picked), addShown: !hidden(el.add) });
"""
    r = run_js([JS], driver)
    assert r["pickedShown"] is False and r["addShown"] is True
    assert [c["url"] for c in r["calls"]] == ["/erp/api/urgent-targets"]


def test_order_search_waits_for_two_chars_then_picks_hit():
    driver = DOM + r"""
loadSources();
window.fomsUrgentCall.open({}); await flush();
fire('click', el.add);
const searchShown = !hidden(el.search);
el.q.value = '0'; fire('input', el.q);
await new Promise(function (r) { setTimeout(r, 260); }); await flush();
const afterOne = calls.filter(function (c) { return c.url.indexOf('/api/foms/search') !== -1; }).length;
el.q.value = '0000'; fire('input', el.q);
await new Promise(function (r) { setTimeout(r, 260); }); await flush();
const hits = el.results.children.map(function (b) { return [b.getAttribute('data-foms-urgent-order-hit'), b.getAttribute('data-order-label')]; });
clickRendered(el.results.children[1], '[data-foms-urgent-order-hit]');
out({ searchShown: searchShown, afterOne: afterOne, hits: hits, label: el.label.textContent, pickedShown: !hidden(el.picked) });
"""
    r = run_js([JS], driver)
    assert r["searchShown"] is True
    assert r["afterOne"] == 0  # 한 글자는 검색하지 않는다
    assert "/api/foms/search?group=all&q=0000" in [c["url"] for c in r["calls"]]
    # customer·order 버킷을 합치고 같은 주문은 한 번만.
    assert r["hits"] == [["4491", "#4491 CLAUDE-TEST"], ["4465", "#4465 CLAUDE-TEST-2"]]
    assert r["label"] == "#4465 CLAUDE-TEST-2" and r["pickedShown"] is True


def test_server_error_stays_open_and_shows_message():
    driver = DOM + r"""
window.FOMSNotificationWrite = { fetch: async function () {
  return Resp(429, { success: false, message: '긴급 호출은 주문당 시간당 5회까지만 보낼 수 있습니다.' }); } };
loadSources();
window.fomsUrgentCall.open({ orderId: '4491', orderLabel: '#4491 X', message: '급해요' }); await flush();
clickRendered(el.teams.children[0], '[data-foms-urgent-team]');
clickRendered(person(20), '[data-foms-urgent-target]');
fire('click', el.send); await flush();
out({ error: el.error.textContent, errorShown: !hidden(el.error), locked: el.send.disabled });
"""
    r = run_js([JS], driver)
    assert r["error"] == "긴급 호출은 주문당 시간당 5회까지만 보낼 수 있습니다."
    assert r["errorShown"] is True and r["locked"] is False  # 다시 누를 수 있다
    assert ["hide", "fomsUrgentCallModal"] not in r["modalOps"]
