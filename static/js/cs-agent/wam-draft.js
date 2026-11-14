/**
 * 채널톡 안 작은 창(WAM) — AI 초안 [보내기] · [수정하기](설계서 17.2.2 · 사장님 11-05 "보내기 누르면 바로 · 수정하기는 채널톡 모달").
 *
 * 채널톡이 이 화면을 자기 주소로 거쳐 열고 다리(window.ChannelIOWam)를 넣어 준다. 단추에 단 값(차례 번호 · 할 일)과 상담 id 는
 * getWamData 로 받고, 서버 일은 모두 서명 함수(cs.draft.get · send · discard)로 한다 — 누른 사람은 채널톡이 서명한 상담원이다.
 *
 * - [보내기]로 열리면: 바로 보낸다 → '보냈어요' 1초 뒤 닫힘. 확인이 필요하면 까닭 + [그래도 보내기] · [고치기].
 * - [수정하기]로 열리면: 보낼 답을 글 칸에 넣고 고친 까닭 칩 · [보내기] · [버리기].
 * 글은 textContent · value 로만 넣는다. 서버로 가는 주소는 없다(함수만).
 * 접목 두 줄(근거 칩 · 할 일 제안 줄 — 설계서 2026-11-14-foms-graft 3.9)은 wam-graft.js 가 그린다. 상담 관리 칸이 켜졌을 때만
 * 실리고, 이 파일은 그 다리(window.FOMS_WAM_GRAFT)에 함수 답 · 보낼 값만 넘긴다(없으면 지금 그대로).
 */
(function () {
  'use strict';

  var root = document.getElementById('cs-wam');
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var status = $('cs-wam-status');
  var notes = $('cs-wam-notes');
  var editBox = $('cs-wam-edit');
  var text = $('cs-wam-text');
  var chips = $('cs-wam-reasons');
  var detailBox = $('cs-wam-detail-box');
  var detail = $('cs-wam-detail');
  var buttons = {
    send: $('cs-wam-send'), confirm: $('cs-wam-confirm'), toEdit: $('cs-wam-to-edit'),
    retry: $('cs-wam-retry'), discard: $('cs-wam-discard')
  };
  var wam = window.ChannelIOWam;
  var graft = window.FOMS_WAM_GRAFT || null; // 접목 두 줄(wam-graft.js — 상담 관리 칸 켬일 때만 실린다)
  var HEIGHT = { small: 220, edit: 470, detail: 580 };
  var SENT_CLOSE_MS = 1000;

  var state = { turn: null, chat: null, appId: '', editing: false, reason: null, confirm: null, busy: false };

  function say(message) { status.textContent = message; }

  function close() {
    try { if (wam && typeof wam.close === 'function') wam.close(); } catch (e) { /* 닫기를 못 해도 화면은 그대로 */ }
  }

  function size(height) {
    try { wam.setSize({ height: height }); } catch (e) { /* 크기를 못 바꿔도 계속 */ }
  }

  function read(key) {
    try { return wam.getWamData(key); } catch (e) { return undefined; }
  }

  function arg(key) {
    var args = read('wamArgs');
    return args && typeof args === 'object' && args[key] !== undefined ? args[key] : read(key);
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
    if (detail) detail.disabled = on;
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

  function afterSend(result) {
    lock(false);
    state.confirm = null;
    if (!result) {
      say('채널톡과 연결이 잠깐 끊겼어요. 다시 눌러 주세요.');
      list([]);
      show(state.editing ? ['send', 'discard'] : ['retry', 'toEdit']);
      return;
    }
    say(result.message || '');
    if (result.code === 'sent' || result.code === 'discarded') {
      list([]);
      show([]);
      if (editBox) editBox.hidden = true;
      var done = graft ? graft.after(result, SENT_CLOSE_MS) : { px: 0, wait: SENT_CLOSE_MS };
      size(HEIGHT.small + done.px);
      if (done.wait) window.setTimeout(close, done.wait);
      return;
    }
    list(reasonsOf(result));
    if (result.code === 'needs_confirm') {
      state.confirm = typeof result.confirm === 'string' ? result.confirm : null;
      show(state.editing ? ['confirm', 'send', 'discard'] : ['confirm', 'toEdit']);
    } else if (['blocked', 'memo_missing', 'detail_private', 'bad_request'].indexOf(result.code) >= 0) {
      show(state.editing ? ['send', 'discard'] : ['toEdit']);
    } else if (['failed', 'read_failed', 'db_error'].indexOf(result.code) >= 0) {
      show(state.editing ? ['send', 'discard'] : ['retry', 'toEdit']);
    } else {
      show(state.editing ? ['discard'] : []);
    }
  }

  function send(withConfirm) {
    if (state.busy) return;
    var params = { mode: 'as_is' };
    if (state.editing) {
      var body = (text.value || '').trim();
      if (!body) { say('보낼 글을 넣어 주세요.'); return; }
      params = { mode: 'edited', text: body };
      if (state.reason) params.edit_reason = state.reason;
      var why = detailBox && !detailBox.hidden ? (detail.value || '').trim() : '';
      if (why) params.edit_detail = why;
    }
    if (withConfirm && state.confirm) params.confirm = state.confirm;
    var picked = graft ? graft.params() : {};
    Object.keys(picked).forEach(function (key) { params[key] = picked[key]; });
    lock(true);
    say('보내는 중이에요.');
    show([]);
    call('cs.draft.send', params).then(afterSend);
  }

  function pick(code, chip) {
    state.reason = state.reason === code ? null : code;
    Array.prototype.forEach.call(chips.querySelectorAll('button'), function (other) {
      other.setAttribute('aria-pressed', String(other === chip && state.reason === code));
    });
  }

  function fillReasons(items) {
    chips.textContent = '';
    (items || []).forEach(function (item) {
      if (!Array.isArray(item) || item.length < 2) return;
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'cs-wam__chip';
      chip.setAttribute('aria-pressed', 'false');
      chip.textContent = String(item[1]);
      chip.addEventListener('click', function () { pick(String(item[0]), chip); });
      chips.appendChild(chip);
    });
  }

  function edit() {
    if (state.busy) return;
    state.editing = true;
    state.confirm = null;
    lock(true);
    say('보낼 답을 불러오는 중이에요.');
    show([]);
    call('cs.draft.get', {}).then(function (result) {
      lock(false);
      if (!result || !result.ok) {
        say(result ? result.message : '채널톡과 연결이 잠깐 끊겼어요. 닫고 다시 열어 주세요.');
        return;
      }
      if (result.blocked) {
        say(result.blocked);
        return;
      }
      var withDetail = Boolean(result.detail && detailBox);
      if (detailBox) detailBox.hidden = !withDetail;
      if (withDetail && result.max_detail) detail.maxLength = result.max_detail;
      size((withDetail ? HEIGHT.detail : HEIGHT.edit) + (graft ? graft.fill(result) : 0));
      editBox.hidden = false;
      text.maxLength = result.max_text || 1000;
      text.value = result.draft || '';
      fillReasons(result.edit_reasons);
      list(result.fresh_note ? [result.fresh_note] : []);
      say(result.draft ? '고친 뒤 보내기를 눌러 주세요.' : '초안 메모를 못 찾았어요. 보낼 글을 넣어 주세요.');
      show(['send', 'discard']);
      text.focus();
    });
  }

  function discard() {
    if (state.busy) return;
    lock(true);
    say('버리는 중이에요.');
    call('cs.draft.discard', {}).then(afterSend);
  }

  // 채널톡 작은 창에는 닫기 단추가 없다 — 화면이 직접 단다(사장님 11-05 "창을 삭제하는 버튼이 없네").
  var closeButton = $('cs-wam-close');
  if (closeButton) closeButton.addEventListener('click', close);
  if (!wam || typeof wam.callFunction !== 'function') {
    say('채널톡 밖에서 열었어요. 채널톡 메모의 단추로 열어 주세요.');
    return;
  }
  size(HEIGHT.small);
  var turn = parseInt(arg('turn'), 10);
  var chat = read('chatId');
  state.turn = turn > 0 ? turn : null;
  state.chat = typeof chat === 'string' && chat ? chat : null;
  state.appId = String(root.getAttribute('data-app-id') || read('appId') || '');
  if (!state.turn || !state.chat || !state.appId) {
    say('어느 초안인지 알 수 없어요. 메모의 단추로 다시 열어 주세요.');
    return;
  }
  // 넘김 메모 [배우기] · [흘리기] 단추로 열렸으면 wam-handoff.js 가 맡는다(초안 보내기를 부르지 않는다).
  if (arg('mode') === 'learn' || arg('mode') === 'skip') return;
  buttons.send.addEventListener('click', function () { send(false); });
  buttons.confirm.addEventListener('click', function () { send(true); });
  buttons.retry.addEventListener('click', function () { send(false); });
  buttons.toEdit.addEventListener('click', edit);
  buttons.discard.addEventListener('click', discard);
  if (arg('mode') === 'edit') edit();
  else if (graft && graft.holdSend) {
    graft.hold({ call: call, send: function () { send(false); }, size: size, say: say, show: show, small: HEIGHT.small });
  } else send(false);
}());
