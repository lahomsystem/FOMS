/**
 * 채널톡 안 작은 창(WAM) — 넘김 메모 [배우기] · [흘리기](사장님 11-11 "모르면 사람이 직접 보내고, 그 답을 배워 다음 상담에").
 *
 * 같은 작은 창(cs-draft)을 wam-draft.js 와 같이 쓴다. 단추 값의 할 일(mode)이 learn · skip 일 때만 이 파일이 맡는다
 * (wam-draft.js 는 그때 손대지 않는다). 서버 일은 모두 서명 함수(cs.handoff.get · send · skip · unskip)로 한다.
 *
 * - [배우기]로 열리면: AI 가 안 쓴 까닭 · AI 메모(참고만) · 빈 글 칸 → 직원이 쓴 답을 [보내기]. 그사이 손님이 새 글을 썼으면
 *   알리고, 한 번 더 누르면 보낸다(창을 연 때 본 마지막 손님 글 = seen).
 * - [흘리기]로 열리면: 바로 흘린다(배우지 않음) → [배우기로 바꾸기]로 되돌릴 수 있다.
 * 글은 textContent · value 로만 넣는다. 서버로 가는 주소는 없다(함수만).
 */
(function () {
  'use strict';

  var root = document.getElementById('cs-wam');
  var wam = window.ChannelIOWam;
  if (!root || !wam || typeof wam.callFunction !== 'function') return;
  var $ = function (id) { return document.getElementById(id); };

  function read(key) {
    try { return wam.getWamData(key); } catch (e) { return undefined; }
  }

  function arg(key) {
    var args = read('wamArgs');
    return args && typeof args === 'object' && args[key] !== undefined ? args[key] : read(key);
  }

  var mode = arg('mode');
  if (mode !== 'learn' && mode !== 'skip') return;

  var status = $('cs-wam-status');
  var notes = $('cs-wam-notes');
  var editBox = $('cs-wam-edit');
  var text = $('cs-wam-text');
  var reasonLine = $('cs-wam-reason');
  var hintBox = $('cs-wam-hint');
  var hintText = $('cs-wam-hint-text');
  var reasonsBox = $('cs-wam-reasons-box');
  var detailBox = $('cs-wam-detail-box');
  var buttons = {
    send: $('cs-wam-send'), confirm: $('cs-wam-confirm'), skip: $('cs-wam-skip'), unskip: $('cs-wam-unskip'),
    retry: $('cs-wam-retry'), toEdit: $('cs-wam-to-edit'), discard: $('cs-wam-discard')
  };
  var HEIGHT = { small: 220, write: 560 };
  var SENT_CLOSE_MS = 1500;
  var LOST = '채널톡과 연결이 잠깐 끊겼어요. 다시 눌러 주세요.';
  var turn = parseInt(arg('turn'), 10);
  var chat = read('chatId');
  var state = {
    turn: turn > 0 ? turn : null, chat: typeof chat === 'string' && chat ? chat : null,
    appId: String(root.getAttribute('data-app-id') || read('appId') || ''),
    seen: null, confirm: null, busy: false, shownAt: 0
  };

  function say(message) { status.textContent = message || ''; }

  function close() {
    try { if (typeof wam.close === 'function') wam.close(); } catch (e) { /* 닫기를 못 해도 화면은 그대로 */ }
  }

  function size(height) {
    try { wam.setSize({ height: height }); } catch (e) { /* 크기를 못 바꿔도 계속 */ }
  }

  function show(which) {
    Object.keys(buttons).forEach(function (key) {
      if (buttons[key]) buttons[key].hidden = which.indexOf(key) < 0;
    });
  }

  function lock(on) {
    state.busy = on;
    Object.keys(buttons).forEach(function (key) { if (buttons[key]) buttons[key].disabled = on; });
    if (text) text.disabled = on;
  }

  function list(items) {
    notes.textContent = '';
    (items || []).forEach(function (item) {
      var p = document.createElement('p');
      p.className = 'cs-wam__note';
      p.textContent = String(item);
      notes.appendChild(p);
    });
    notes.hidden = !notes.childNodes.length;
  }

  function writing(on) {
    editBox.hidden = !on;
    if (reasonsBox) reasonsBox.hidden = true;  // 넘김 답에는 '고친 까닭'이 없다(AI 초안이 없다)
    if (detailBox) detailBox.hidden = true;  // 직원이 쓴 답 전체를 배운다 — '왜 고쳤나요' 칸이 필요 없다
    if (!on) {
      reasonLine.hidden = true;
      hintBox.hidden = true;
    }
    size(on ? HEIGHT.write : HEIGHT.small);
  }

  // 함수 답은 {result: {...}} 또는 바로 {...} — 채널톡 판에 따라 다를 수 있어 둘 다 받는다. 오류 꼴은 null.
  function call(name, params) {
    var payload = { turn: state.turn, chat: state.chat };
    Object.keys(params || {}).forEach(function (key) { payload[key] = params[key]; });
    return Promise.resolve(wam.callFunction({ appId: state.appId, name: name, params: payload })).then(function (res) {
      if (!res || res.error) return null;
      var result = res.result !== undefined ? res.result : res;
      return result && typeof result === 'object' && typeof result.code === 'string' ? result : null;
    }, function () { return null; });
  }

  function reasonsOf(result) {
    return (result.problems || result.warnings || []).map(function (item) { return item && item.reason; })
      .filter(Boolean);
  }

  // 지금 상태(코드)에 맞는 단추 — 쓰기 · 흘림 · 보냄 · 직원 답함 · 확인 중.
  function settle(result) {
    var code = result.code;
    if (code === 'write') return openWriting(result);
    if (code === 'unskipped_open') return load();
    writing(false);
    list([]);
    if (code === 'is_skipped' || code === 'skipped' || code === 'skipped_learned') show(['unskip']);
    else if (['learn_sent', 'answered', 'unskipped_sent', 'unskipped_desk'].indexOf(code) >= 0) show(['skip']);
    else show([]);
  }

  function openWriting(result) {
    if (typeof result.seen === 'string') state.seen = result.seen;
    if (result.reason) {
      reasonLine.textContent = 'AI가 안 쓴 까닭: ' + result.reason;
      reasonLine.hidden = false;
    }
    hintText.textContent = result.hint || '';
    hintBox.hidden = !result.hint;
    if (result.max_text) text.maxLength = result.max_text;
    text.placeholder = '여기에 답을 써 주세요';
    writing(true);
    list(result.note ? [result.note] : []);
    show(['send', 'skip']);
    state.shownAt = Date.now();
    text.focus();
  }

  function load() {
    lock(true);
    say('불러오는 중이에요.');
    show([]);
    call('cs.handoff.get', {}).then(function (result) {
      lock(false);
      if (!result) { say('채널톡과 연결이 잠깐 끊겼어요. 닫고 다시 열어 주세요.'); return; }
      say(result.message);
      settle(result);
    });
  }

  function afterSend(result) {
    lock(false);
    state.confirm = null;
    if (!result) {
      say(LOST);
      show(['send', 'skip']);
      return;
    }
    say(result.message);
    if (result.code === 'sent') {
      writing(false);
      list([]);
      show([]);
      window.setTimeout(close, SENT_CLOSE_MS);
      return;
    }
    if (result.code === 'new_message') {
      if (typeof result.seen === 'string') state.seen = result.seen;
      list([]);
      show(['send', 'skip']);
    } else if (result.code === 'needs_confirm') {
      state.confirm = typeof result.confirm === 'string' ? result.confirm : null;
      list(reasonsOf(result));
      show(['confirm', 'send', 'skip']);
    } else if (['blocked', 'failed', 'read_failed', 'db_error', 'bad_request'].indexOf(result.code) >= 0) {
      list(reasonsOf(result));
      show(['send', 'skip']);
    } else {
      settle(result);
    }
  }

  function send(withConfirm) {
    if (state.busy) return;
    var body = (text.value || '').trim();
    if (!body) { say('보낼 글을 넣어 주세요.'); return; }
    var params = { text: body, shown_ms: state.shownAt ? Date.now() - state.shownAt : undefined };
    if (state.seen) params.seen = state.seen;
    if (withConfirm && state.confirm) params.confirm = state.confirm;
    lock(true);
    say('보내는 중이에요.');
    show([]);
    call('cs.handoff.send', params).then(afterSend);
  }

  function choose(name, busyText) {
    if (state.busy) return;
    lock(true);
    say(busyText);
    show([]);
    call(name, {}).then(function (result) {
      lock(false);
      if (!result) { say(LOST); show([name === 'cs.handoff.skip' ? 'skip' : 'unskip']); return; }
      say(result.message);
      settle(result);
    });
  }

  size(HEIGHT.small);  // [닫기] 단추는 wam-draft.js 가 이미 단다
  if (!state.turn || !state.chat || !state.appId) {
    say('어느 상담인지 알 수 없어요. 메모의 단추로 다시 열어 주세요.');
    return;
  }
  buttons.send.addEventListener('click', function () { send(false); });
  buttons.confirm.addEventListener('click', function () { send(true); });
  buttons.skip.addEventListener('click', function () { choose('cs.handoff.skip', '흘리는 중이에요.'); });
  buttons.unskip.addEventListener('click', function () { choose('cs.handoff.unskip', '바꾸는 중이에요.'); });
  if (mode === 'skip') choose('cs.handoff.skip', '흘리는 중이에요.');
  else load();
}());
