/**
 * 도면 마법사 [저장]·[일괄 저장] → 저장하면서 같이 할 일 고르기 창.
 * 설계서 docs/specs/2026-11-05-wizard-save-send-options_SPEC.md (사용자 결정 2026-11-05).
 *
 * - 칸 두 개: 도면 발송(= 영업에게 전달, 작업실 [전달하기] 와 같은 일) · 도면방 PUSH.
 *   도면방 PUSH 는 전달본만 보내므로 PUSH 를 켜면 발송도 켜지고, 발송을 끄면 PUSH 도 꺼진다.
 * - 처리 순서: 저장(wizard.js save/saveAll 그대로) → 전달(POST /transfer-drawing) → 도면방 PUSH(wizard.js pushDrawingRoom).
 *   앞 단계가 실패하면 뒤 단계는 하지 않는다. 일괄 저장은 한 장이라도 대기함에 못 넣으면 전달하지 않는다.
 * - 한 장 저장 + 전달은 mode 'APPEND' 를 꼭 보낸다 — 비우면 영업 확정 전(TRANSFERRED)에 서버가 전체 교체로 보고
 *   다른 장이 전부 빠진다. APPEND 면 서버의 같은 시트 자리 교체 규칙이 그 시트 옛 판만 바꾼다.
 * - Ctrl+S 는 이 창을 거치지 않는다(wizard.js 단축키가 save() 를 바로 부른다).
 * 권한 · 잠금 · 알림은 기존 서버 경로가 다시 검사한다 — 여기 값(save_send)은 칸을 잠그고 숨기는 화면 표시용이다.
 */
(function () {
  'use strict';

  var root = document.getElementById('dws-root');
  var pop = document.getElementById('dws-savesend');
  if (!root || !pop) { return; }

  var CFG = {};
  try {
    var cfgEl = document.getElementById('drawing-wizard-config');
    CFG = ((cfgEl && JSON.parse(cfgEl.textContent || '{}')) || {}).save_send || {};
  } catch (e) {
    CFG = {};
  }
  var ORDER_ID = parseInt(root.getAttribute('data-order-id'), 10) || 0;
  var STORE_KEY = 'dws.savesend.v1.' + (CFG.user_id || 0);
  var HOTFIX_MSG = '생산·시공 단계라 영업 확인 없이 바로 최종 도면이 되고 생산팀에 알림이 갑니다. 전달 취소로 되돌릴 수 없습니다.\n\n저장하고 전달할까요?';

  var head = document.getElementById('dws-savesend-head');
  var sendBox = pop.querySelector('[data-savesend="send"]');
  var pushBox = pop.querySelector('[data-savesend="push"]');
  var pushRow = pop.querySelector('[data-savesend-row="push"]');
  var lockNote = pop.querySelector('[data-savesend-lock]');
  var goBtn = pop.querySelector('[data-savesend-go]');
  var cancelBtn = pop.querySelector('[data-savesend-cancel]');
  var rememberBox = pop.querySelector('[data-savesend-remember]');
  var kind = 'one';
  var busy = false;

  var canTransfer = CFG.can_transfer === true;
  var isPartner = CFG.is_partner === true;   // 협력사는 채널톡에 없다 — 도면방 PUSH 칸 없음(사용자 11-05)

  function core() { return window.FomsWizardCore || null; }

  function say(msg, opts) {
    var c = core();
    if (c && c.toast) { c.toast(msg, opts); }
  }

  function readChoice() {
    try {
      var v = JSON.parse(window.localStorage.getItem(STORE_KEY) || 'null');
      return v && typeof v === 'object' ? v : null;
    } catch (e) {
      return null;
    }
  }

  function writeChoice() {
    try {
      if (rememberBox.checked) {
        window.localStorage.setItem(STORE_KEY, JSON.stringify({ send: sendBox.checked, push: pushBox.checked }));
      } else {
        window.localStorage.removeItem(STORE_KEY);
      }
    } catch (e) { /* 사생활 보호 모드 — 기억만 못 한다 */ }
  }

  function wantSend() { return canTransfer && sendBox.checked; }
  function wantPush() { return wantSend() && !isPartner && pushBox.checked; }

  /** 칸 규칙(PUSH ⇒ 발송) · 켠 칸 표시 · 아래 단추 글. */
  function sync(changed) {
    if (changed === pushBox && pushBox.checked) { sendBox.checked = true; }
    if (changed === sendBox && !sendBox.checked) { pushBox.checked = false; }
    [sendBox, pushBox].forEach(function (b) {
      b.closest('.dws-savesend-opt').classList.toggle('is-on', b.checked && !b.disabled);
    });
    goBtn.textContent = wantPush() ? '저장 + 전달 + 도면방' : (wantSend() ? '저장 + 전달' : '저장만');
  }

  function applyLocks() {
    sendBox.disabled = !canTransfer;
    pushBox.disabled = !canTransfer;
    lockNote.hidden = canTransfer;
    pushRow.hidden = isPartner;
    if (!canTransfer) { sendBox.checked = false; pushBox.checked = false; }
    if (isPartner) { pushBox.checked = false; }
  }

  /** wizard.js 단추 클릭이 부른다. 창을 열었으면 true(아니면 wizard.js 가 예전처럼 바로 저장한다). */
  function open(which) {
    var c = core();
    if (!c || !c.canSave() || !c.hydrated() || busy) { return false; }
    if (!pop.hidden && kind === which) { close(); return true; }
    kind = which === 'all' ? 'all' : 'one';
    var count = (c.state().sheets || []).length;
    head.textContent = kind === 'all' ? ('모든 시트 저장 (' + count + '장)') : '지금 시트 저장';
    var saved = readChoice();
    sendBox.checked = !!(saved && saved.send);
    pushBox.checked = !!(saved && saved.push);
    rememberBox.checked = true;
    applyLocks();
    sync(null);
    pop.hidden = false;
    goBtn.focus();
    return true;
  }

  function close() { pop.hidden = true; }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (resp) {
      return resp.json().then(
        function (data) { return data || {}; },
        function () { return { success: false, message: '응답을 해석할 수 없습니다. (' + resp.status + ')' }; }
      );
    });
  }

  /** 방금 저장한 시트(들)를 영업에게 전달한다. 성공이면 true. */
  function transfer(sheetIds) {
    var body = { note: '', files: [], pending_sheet_ids: sheetIds, mode: kind === 'one' ? 'APPEND' : '' };
    return postJson('/api/orders/' + ORDER_ID + '/transfer-drawing', body).then(function (data) {
      var c = core();
      if (c && c.refreshPending) { c.refreshPending(); }   // 전달한 시트는 대기함에서 빠진다
      if (data.success === true) { return true; }
      var why = String(data.message || data.error || '전달 실패');
      if (why.indexOf('교체할 도면') >= 0) { why += ' — 작업실 [전달하기] 에서 골라 주세요'; }
      say('저장은 됐어요 · 전달 못 함: ' + why, { error: true });
      return false;
    }, function (err) {
      console.warn('[dws] save-send transfer', err);
      say('저장은 됐어요 · 전달 중 연결이 끊겼어요. 작업실에서 전달 상태를 확인해 주세요.', { error: true });
      return false;
    });
  }

  /** 저장 → (전달) → (도면방 PUSH). */
  function run() {
    var c = core();
    if (!c || busy) { return; }
    var send = wantSend();
    var push = wantPush();
    writeChoice();
    close();
    if (send && CFG.hotfix_stage === true && !window.confirm(HOTFIX_MSG)) { return; }

    var sheets = c.state().sheets || [];
    var cur = c.sheet();
    var ids = kind === 'all'
      ? sheets.map(function (s) { return s.id; })
      : (cur ? [cur.id] : []);
    var saving = kind === 'all'
      ? c.saveAll().then(function (res) {
        if (!res) { return false; }
        if (res.fail && res.fail.length) {
          if (send) { say(res.fail.length + '장을 대기함에 못 넣어서 전달은 하지 않았어요', { error: true }); }
          return false;
        }
        return res.total > 0;
      })
      : c.save().then(function (ok) { return ok === true; });

    if (!send) { return; }
    busy = true;
    saving.then(function (saved) {
      if (!saved || !ids.length) { return false; }
      return transfer(ids).then(function (sent) {
        if (!sent) { return false; }
        if (!push) {
          say('저장했어요 · 영업에게 전달했어요', { key: 'savesend' });
          return true;
        }
        say('저장했어요 · 영업에게 전달했어요 · 도면방에 올리는 중…', { key: 'savesend' });
        return c.pushRoom({ skipConfirm: true });   // 끝 알림은 도면방 PUSH 가 띄운다
      });
    }).catch(function (err) {
      console.warn('[dws] save-send', err);
    }).then(function () { busy = false; });
  }

  sendBox.addEventListener('change', function () { sync(sendBox); });
  pushBox.addEventListener('change', function () { sync(pushBox); });
  goBtn.addEventListener('click', run);
  cancelBtn.addEventListener('click', close);
  pop.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === 'Enter' && e.target && e.target.type === 'checkbox') { e.preventDefault(); run(); }
  });
  // 창 밖을 누르면 닫는다. 창을 연 클릭(단추 · V2 ⋯ 메뉴 '일괄 저장')은 같은 이벤트가 여기까지 올라오므로 건너뛴다.
  document.addEventListener('click', function (e) {
    if (pop.hidden || !e.target || !e.target.closest) { return; }
    if (e.target.closest('#dws-savesend, #dws-btn-save, #dws-btn-save-all, [data-v2-for="dws-btn-save-all"]')) { return; }
    close();
  });

  window.FomsSaveSend = { open: open, close: close };
})();
