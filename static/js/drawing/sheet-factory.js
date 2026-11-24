/**
 * 도면 장의 공장(1공장 · 2공장) 지정 — 마법사(wizard-factory.js)와 작업실(workbench-sheet-factory.js)이 같이 쓴다.
 * 설계서 docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md §4-13 · §8-5.
 *
 * - post(orderId, items)  POST /api/orders/<id>/drawing/sheet-factory → { ok, data, code, message }
 *   (fetch 는 try/catch, data.success 로 판정. 거절 글은 서버 글 그대로 돌려준다.)
 * - confirmMove(opts)     생산에 이미 내려간 장을 옮기기 전 확인 창 — [그대로] [2공장으로 옮기기]
 * - showBlocked(opts)     옮길 수 없을 때 창 — 서버 글 그대로, [닫기]
 * 지키는 일(누가 · 언제 옮길 수 있나)은 서버가 한다. 이 파일은 화면만 돕는다.
 */
(function () {
  'use strict';
  if (window.FomsSheetFactory) return;

  var FAIL = '저장하지 못했어요. 잠시 뒤 다시 해 주세요.';

  function label(factory) { return Number(factory) === 2 ? '2공장' : '1공장'; }

  function newKey() {
    return 'sf-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  /** 공장 지정 API 한 번 — 하나라도 막히면 서버가 아무것도 안 바꾼다. */
  async function post(orderId, items) {
    var body = { items: items, idempotency_key: newKey() };
    var data = null;
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/drawing/sheet-factory', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body)
      });
      try { data = await res.json(); } catch (_) { data = null; }
    } catch (e) {
      console.warn('[sheet-factory] post', e);
      return { ok: false, code: 'NETWORK', message: FAIL, data: {} };
    }
    if (data && data.success) return { ok: true, data: data.data || {} };
    var extra = (data && data.data) || {};
    return { ok: false, code: extra.code || 'SAVE_FAILED', message: (data && data.error) || FAIL, data: extra };
  }

  /** 열린 Bootstrap 창 안에서 부르면 그 창 안에 둔다 — 그 창의 초점 가두기가 새 창 단추를 빼앗지 않게. */
  function hostFor(anchor) {
    var modal = anchor && anchor.closest ? anchor.closest('.modal.show') : null;
    return modal || document.body;
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  /** 기본 <dialog> 창(showModal) — 초점 가두기 · Esc 닫기 · 맨 위 겹. 마법사는 열린 기본 창이 있으면 캔버스 단축키를 쉰다. */
  function open(opts) {
    var back = document.activeElement;
    var dlg = el('dialog', 'dsf-dialog');
    var id = 'dsf-t-' + Math.random().toString(36).slice(2, 8);
    dlg.setAttribute('aria-labelledby', id);
    if (opts.alert) dlg.setAttribute('role', 'alertdialog');
    var box = el('div', 'dsf-dialog__box');
    var title = el('h2', 'dsf-dialog__title', opts.title);
    title.id = id;
    box.appendChild(title);
    if (opts.sub) box.appendChild(el('p', 'dsf-dialog__sub', opts.sub));
    var body = el('p', 'dsf-dialog__body' + (opts.alert ? ' is-block' : ''), opts.body);
    if (opts.alert) body.setAttribute('role', 'alert');
    box.appendChild(body);
    var foot = el('div', 'dsf-dialog__foot');
    var go = false;
    var buttons = (opts.buttons || []).map(function (b) {
      var btn = el('button', 'dsf-dialog__btn' + (b.go ? ' is-go' : ''), b.text);
      btn.type = 'button';
      btn.addEventListener('click', function () { go = !!b.go; dlg.close(); });
      foot.appendChild(btn);
      return btn;
    });
    box.appendChild(foot);
    dlg.appendChild(box);
    dlg.addEventListener('click', function (ev) { if (ev.target === dlg) dlg.close(); });   // 바깥(뒤 막) 누름 = 그대로
    // Esc 는 이 창만 닫는다 — 뒤의 Bootstrap 창(전달 창)이 같은 Esc 로 함께 닫히지 않게.
    dlg.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') ev.stopPropagation(); });
    dlg.addEventListener('close', function () {
      if (dlg.parentNode) dlg.parentNode.removeChild(dlg);
      if (back && back.focus && document.contains(back)) back.focus();
      if (go && opts.onGo) opts.onGo();
      if (opts.onClose) opts.onClose();
    });
    hostFor(opts.anchor).appendChild(dlg);
    dlg.showModal();
    if (buttons[0]) buttons[0].focus();   // 처음 초점은 안전한 쪽([그대로] · [닫기])
    return dlg;
  }

  /** 생산에 이미 내려간 장 — "2공장으로 옮길까요?" [그대로] [2공장으로 옮기기] (§4-13). */
  function confirmMove(opts) {
    var to = label(opts.to);
    return open({
      title: to + '으로 옮길까요?',
      sub: opts.sub || '',
      body: "생산에 이미 내려간 도면이에요. 옮기면 1공장 · 2공장 화면에 '바뀜'으로 알려요.",
      buttons: [{ text: '그대로' }, { text: to + '으로 옮기기', go: true }],
      onGo: opts.onGo, onClose: opts.onClose, anchor: opts.anchor
    });
  }

  /** 옮길 수 없을 때 — 제목 "2공장으로 옮길 수 없어요", 본문은 서버 글 그대로(앞머리가 제목과 같으면 그 뒤만). */
  function showBlocked(opts) {
    var title = label(opts.to) + '으로 옮길 수 없어요';
    var text = String(opts.message || FAIL);
    var head = title + ' — ';
    return open({
      title: title,
      sub: opts.sub || '',
      body: text.indexOf(head) === 0 ? text.slice(head.length) : text,
      alert: true,
      buttons: [{ text: '닫기' }],
      onClose: opts.onClose, anchor: opts.anchor
    });
  }

  window.FomsSheetFactory = { label: label, post: post, confirmMove: confirmMove, showBlocked: showBlocked };
})();
