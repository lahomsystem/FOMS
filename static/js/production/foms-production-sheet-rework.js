/* 생산 작업 시트 — [수정 제작] 고르기 창(설계서 docs/specs/2026-11-28-production-flow-three_SPEC.md §2-2, 사장님 답 6 "다시 할 칸 고르기").
 * 창 조각 = templates/production/partials/sheet_rework_pick.html([data-foms-rework-pick] = drawings · steps — 제작 완료 단계 · 반장 · 관리자 화면에만 있다).
 * tablet-domain-sheets.js 의 productionRework 가 부른다(window.FomsSheetRework). 이 파일은 요청을 보내지 않는다.
 *  · ask(btn, go): 고르기 창을 연다. 줄을 누르면 골라지고(aria-pressed) 다시 누르면 풀린다 · 여러 개. 0개면 [다음] 잠김 + 아래 한 줄.
 *      남의 공장 도면(aria-disabled)은 안 골라지고 누르면 서버가 실어 준 글만. [다음] → go(몸, 사유 창 한 줄) — 몸 = {keys:[…]} 또는 {steps:[…]}.
 *      창 조각이 없는 화면이면 false(부른 쪽이 지금 길로 — 서버가 "다시 만들 도면을 골라 주세요. …"로 답한다).
 *  · note(text): 공용 사유 창([data-foms-reason-sheet] — 다른 화면도 쓴다, 안 바꾼다)에 한 줄을 끼운다. 그 창이 닫히면 저절로 뺀다.
 *  · done(orderId, text): 저장 응답 글("수정 제작을 시작했어요. 도면 2장을 다시 만들어요.")을 다시 받은 화면의 상태 줄에 한 번 보인다.
 * 연 뒤 GUARD_MS 안 누름은 버린다(두 번 누름이 줄을 고르거나 다음 창의 [수정 제작]까지 누르지 않게). Esc · 바깥 · [닫기] = 아무 것도 안 함. */
(function () {
  'use strict';

  var GUARD_MS = 400;
  var NOTICE_KEY = 'foms_sheet_rework_notice';
  var PART_ALL = '재단 · 엣지 · 조립 · 검수';
  var S = window.__FOMS_SHEET_REWORK = window.__FOMS_SHEET_REWORK || { box: null, go: null, opener: null, at: 0, handoff: 0 };

  function toArr(list) { return [].slice.call(list || []); }
  function rows(box) { return toArr(box.querySelectorAll('[data-foms-rework-item]')); }
  function picked(box) { return rows(box).filter(function (r) { return r.getAttribute('aria-pressed') === 'true'; }); }
  function objectWord(text) { // "조립 · 검수" + 를 · "재단" + 을 — 마지막 글자 받침
    var c = text.charCodeAt(text.length - 1) - 0xAC00;
    return text + (c >= 0 && c < 11172 && c % 28 === 0 ? '를' : '을');
  }
  function say(box, text) {
    var msg = box.querySelector('[data-foms-rework-msg]');
    if (msg) { msg.textContent = text || ''; msg.hidden = !text; }
  }
  function sync(box) {
    var n = picked(box).length;
    var next = box.querySelector('[data-foms-rework-next]');
    var hint = box.querySelector('[data-foms-rework-hint]');
    if (next) { next.disabled = n === 0; }
    if (hint) { hint.hidden = n > 0; }
  }
  function close(focusBack) {
    var box = S.box;
    S.box = null;
    S.go = null;
    if (!box) { return; }
    box.hidden = true;
    box.setAttribute('aria-hidden', 'true');
    if (focusBack && S.opener && document.contains(S.opener)) { S.opener.focus(); }
  }
  function result(box) {
    var items = picked(box);
    var words = items.map(function (r) { return r.getAttribute('data-foms-rework-word') || ''; });
    var keys = items.map(function (r) { return r.getAttribute('data-foms-rework-item'); });
    if (box.getAttribute('data-foms-rework-pick') === 'steps') {
      return { body: { steps: keys }, note: objectWord(words.join(' · ')) + ' 다시 해요. 그 공정만 미완료로 돌아가요.' };
    }
    return { body: { keys: keys },
      note: '도면 ' + words.join(' · ') + '번(' + items.length + '장)을 다시 만들어요. ' + PART_ALL + '가 모두 미정으로 돌아가요.' };
  }
  function ask(btn, go) {
    var scope = (btn && btn.closest && btn.closest('[data-foms-prod-sheet-page]')) || document;
    var box = scope.querySelector('[data-foms-rework-pick]');
    if (!box || typeof go !== 'function') { return false; }
    if (!box.hidden) { return true; } // 떠 있는 창 위 누름은 버린다
    rows(box).forEach(function (r) { r.setAttribute('aria-pressed', 'false'); });
    say(box, '');
    sync(box);
    S.box = box;
    S.go = go;
    S.opener = btn || null;
    S.at = Date.now();
    box.hidden = false;
    box.setAttribute('aria-hidden', 'false');
    var first = rows(box).filter(function (r) { return r.getAttribute('aria-disabled') !== 'true'; })[0] || box.querySelector('[data-foms-rework-close].foms-btn');
    if (first) { first.focus(); }
    return true;
  }
  function drop(node) { if (node && node.parentNode) { node.parentNode.removeChild(node); } }
  function note(text) {
    var sheet = document.querySelector('[data-foms-reason-sheet]');
    if (!sheet) { return; }
    var line = sheet.querySelector('[data-foms-rework-note]');
    if (!text) { drop(line); return; }
    if (!line) {
      line = document.createElement('p');
      line.className = 'fpp-rwk-note';
      line.setAttribute('data-foms-rework-note', '');
      var field = sheet.querySelector('.foms-reason-sheet__field');
      if (!field || !field.parentNode) { return; }
      field.parentNode.insertBefore(line, field);
    }
    line.textContent = text;
    if (sheet.__fomsReworkWatch || typeof MutationObserver !== 'function') { return; }
    sheet.__fomsReworkWatch = new MutationObserver(function () { // 사유 창이 닫히면 한 줄을 뺀다(보류 · 제작 시작 취소 · 관리자 사유 창에 남지 않게)
      if (sheet.hidden) { drop(sheet.querySelector('[data-foms-rework-note]')); }
    });
    sheet.__fomsReworkWatch.observe(sheet, { attributes: true, attributeFilter: ['hidden'] });
  }
  function done(orderId, text) {
    if (!text) { return; }
    try { window.sessionStorage.setItem(NOTICE_KEY, JSON.stringify({ id: String(orderId), text: String(text) })); } catch (e) { /* 저장 못 하면 알림 없이 다시 받는다 */ }
  }
  function showNotice() {
    var raw = null;
    try { raw = window.sessionStorage.getItem(NOTICE_KEY); window.sessionStorage.removeItem(NOTICE_KEY); } catch (e) { return; }
    var saved = null;
    try { saved = raw ? JSON.parse(raw) : null; } catch (e2) { saved = null; }
    var page = document.querySelector('[data-foms-prod-sheet-page]');
    var line = page && page.querySelector('[data-foms-sheet-status]');
    if (!saved || !line || String(saved.id) !== String(page.getAttribute('data-order-id'))) { return; }
    line.textContent = saved.text;
    line.classList.remove('is-bad');
    line.classList.add('is-ok');
  }

  S.api = { close: close, result: result, sync: sync, say: say };
  if (!S.bound) {
    S.bound = true;
    document.addEventListener('click', function (e) { // 넘긴 바로 뒤 사유 창 누름(두 번 누름)은 버린다 — 사유 창 리스너보다 먼저
      var t = e.target;
      if (Date.now() - S.handoff < GUARD_MS && t && t.closest && t.closest('[data-foms-reason-sheet]')) { e.stopPropagation(); e.preventDefault(); }
    }, true);
    document.addEventListener('click', function (e) {
      var t = e.target;
      var box = S.box;
      if (!box || box.hidden || !t || typeof t.closest !== 'function' || !box.contains(t)) { return; }
      if (Date.now() - S.at < GUARD_MS) { return; }
      if (t.closest('[data-foms-rework-close]')) { S.api.close(true); return; }
      var row = t.closest('[data-foms-rework-item]');
      if (row) {
        if (row.getAttribute('aria-disabled') === 'true') { S.api.say(box, row.getAttribute('data-foms-rework-why') || ''); return; }
        row.setAttribute('aria-pressed', row.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
        S.api.say(box, '');
        S.api.sync(box);
        return;
      }
      var next = t.closest('[data-foms-rework-next]');
      if (!next || next.disabled) { return; }
      var out = S.api.result(box);
      var go = S.go;
      S.api.close(false);
      S.handoff = Date.now();
      if (go) { go(out.body, out.note); }
    });
    document.addEventListener('keydown', function (e) {
      var box = S.box;
      if (!box || box.hidden || !document.contains(box)) { return; } // 조각 교체로 떠난 창은 키를 가두지 않는다
      if (e.key === 'Escape') { S.api.close(true); return; }
      if (e.key !== 'Tab') { return; }
      var stops = toArr(box.querySelectorAll('button')).filter(function (b) { return !b.disabled; });
      if (!stops.length) { return; }
      var i = stops.indexOf(document.activeElement);
      e.preventDefault();
      stops[(i + (e.shiftKey ? -1 : 1) + stops.length) % stops.length].focus();
    });
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', showNotice); } else { showNotice(); }
  window.FomsSheetRework = { ask: ask, note: note, done: done };
})();
