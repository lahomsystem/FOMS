/**
 * 도면 작업실 상세 '공장 진행' 칸 — [수정 시작] · [수정 취소](설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-2 · N1 · N2, D3).
 *
 * - 누르면 확인 창 하나: 시작 = 제목 "수정 시작" · 본문(서버가 data-confirm 에 실은 글) · [취소] [수정 시작],
 *   취소 = 제목 "수정 취소" · 본문 · [닫기] [수정 취소]. 본문 조사(을/를)는 서버가 정한다(drawing_fix_marks.confirm_text).
 * - 확인하면 POST /api/orders/<id>/drawing/fix/start|stop {targets: [{sheet_id} | {key}]} — fetch 는 try/catch, data.success 로 판정.
 *   되면 화면을 다시 읽는다(빨간 줄 · 단추 · 주문 버전이 서버 값으로). 안 되면 서버 글을 칸 아래 한 줄에.
 * - 창은 <dialog>(맨 위 층) — 모양은 D2 보내기 전 확인 창과 같은 dfx-dialog(workbench-fix.css).
 * - ERP 셸 조각이 다시 실행해도 한 번만 묶는다(G4 — window.__DW_DRAWING_FIX_BOUND).
 */
(function () {
  'use strict';
  if (window.__DW_DRAWING_FIX_BOUND) { return; }
  window.__DW_DRAWING_FIX_BOUND = true;

  var FAIL = '저장하지 못했어요. 잠시 뒤 다시 해 주세요.';
  var WORDS = {
    start: { title: '수정 시작', cancel: '취소', go: '수정 시작' },
    stop: { title: '수정 취소', cancel: '닫기', go: '수정 취소' }
  };
  var busy = false;

  function node(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (text) { el.textContent = text; }
    return el;
  }

  /** 확인 창 — 확인하면 true. <dialog> 가 없는 옛 브라우저는 window.confirm. */
  function ask(act, body) {
    var words = WORDS[act];
    var dialog = node('dialog', 'dfx-dialog dwp-dialog');
    if (typeof dialog.showModal !== 'function') {
      return Promise.resolve(window.confirm(body));
    }
    dialog.setAttribute('aria-label', words.title);
    dialog.appendChild(node('div', 'dfx-dialog__head', words.title));
    var main = node('div', 'dfx-dialog__body');
    main.appendChild(node('p', 'dwp-dialog__text', body));
    dialog.appendChild(main);
    var foot = node('div', 'dfx-dialog__foot');
    var cancel = node('button', 'dfx-btn dfx-btn--cancel', words.cancel);
    var go = node('button', 'dfx-btn ' + (act === 'stop' ? 'dwp-btn--stop' : 'dfx-btn--go'), words.go);
    cancel.type = 'button';
    go.type = 'button';
    foot.appendChild(cancel);
    foot.appendChild(go);
    dialog.appendChild(foot);
    document.body.appendChild(dialog);
    return new Promise(function (resolve) {
      var answer = false;
      cancel.addEventListener('click', function () { dialog.close(); });
      go.addEventListener('click', function () { answer = true; dialog.close(); });
      dialog.addEventListener('close', function () {
        dialog.remove();
        resolve(answer);
      });
      dialog.showModal();
      go.focus();
    });
  }

  async function post(orderId, act, target) {
    var data = null;
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/drawing/fix/' + act, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ targets: [target] })
      });
      try { data = await res.json(); } catch (_) { data = null; }
    } catch (e) {
      console.warn('[drawing-fix] post', e);
      return { ok: false, message: FAIL };
    }
    if (data && data.success === true) { return { ok: true }; }
    return { ok: false, message: (data && data.error) || FAIL };
  }

  function showError(panel, message) {
    var el = panel && panel.querySelector('[data-dwp-error]');
    if (!el) { return; }
    el.textContent = message || '';
    el.hidden = !message;
  }

  function onClick(ev) {
    var btn = ev.target.closest ? ev.target.closest('[data-dwp] [data-dwp-act]') : null;
    if (!btn || busy) { return; }
    ev.preventDefault();
    var panel = btn.closest('[data-dwp]');
    var act = btn.getAttribute('data-dwp-act') === 'stop' ? 'stop' : 'start';
    var sheetId = btn.getAttribute('data-sheet-id') || '';
    var target = sheetId ? { sheet_id: sheetId } : { key: btn.getAttribute('data-key') || '' };
    showError(panel, '');
    ask(act, btn.getAttribute('data-confirm') || '').then(function (ok) {
      if (!ok) { return null; }
      busy = true;
      btn.disabled = true;
      return post(panel.getAttribute('data-order-id'), act, target).then(function (res) {
        if (res.ok) {
          window.location.reload();
          return;
        }
        busy = false;
        btn.disabled = false;
        showError(panel, res.message);
      });
    });
  }

  document.addEventListener('click', onClick);
})();
