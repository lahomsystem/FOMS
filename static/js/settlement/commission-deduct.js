/**
 * 정산 대시보드 · 탭 "영업 수수료" — 차감 작은 창(설계서 §2.1-5 · §10).
 *
 * 차감 칸(합계)을 누르면 그 줄 · 그 프리랜서 몫의 차감 목록과 [취소], 아래에 금액 · 사유 넣기 칸이 뜬다.
 * - 넣기: 기존 `POST /api/orders/<id>/settlement/issue` — 부서는 영업(SALES), 사람은 고른 프리랜서로 고정.
 *   금액은 음수로 보낸다(완료 화면 모달 · 실무 탭과 같은 본문 모양).
 * - 취소: `POST /api/orders/<id>/settlement/deductions/<차감 id>/void` `{reason}` — 지우지 않고 취소 표시.
 * 어느 쪽이든 끝나면 창을 닫고 표를 다시 읽는다(차감 · 수수료 · 합계가 서버 계산으로 한꺼번에 맞는다).
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  function els(ctx) {
    var d = ctx.els.dialog;
    return {
      title: d.querySelector('[data-settlement-cm-ded-title]'),
      sub: d.querySelector('[data-settlement-cm-ded-sub]'),
      list: d.querySelector('[data-settlement-cm-ded-list]'),
      none: d.querySelector('[data-settlement-cm-ded-none]'),
      amount: d.querySelector('[data-settlement-cm-ded-amount]'),
      reason: d.querySelector('[data-settlement-cm-ded-reason]'),
      msg: d.querySelector('[data-settlement-cm-ded-msg]'),
      add: d.querySelector('[data-settlement-cm-ded-add]'),
    };
  }

  function say(ctx, text) {
    var e = els(ctx);
    e.msg.textContent = text || '';
    C.hide(e.msg, !text);
  }

  function freelancerName(ctx) {
    var id = String(ctx.state.userId);
    var hit = (ctx.state.freelancers || []).filter(function (f) { return String(f.user_id) === id; })[0];
    return hit ? hit.match_name : '';
  }

  function close(ctx) {
    var d = ctx.els.dialog;
    ctx.state.dedOrderId = null;
    if (typeof d.close === 'function' && d.open) d.close();
    else d.removeAttribute('open');
  }

  function open(ctx, orderId) {
    var row = C.rowOf(ctx, orderId);
    var d = ctx.els.dialog;
    if (!row || !d) return;
    var e = els(ctx);
    ctx.state.dedOrderId = String(orderId);
    e.title.textContent = (row.customer_name || '-') + ' 차감';
    e.sub.textContent = freelancerName(ctx) + ' 님 수수료에서 빠져요.';
    e.list.textContent = '';
    (row.deductions || []).forEach(function (ded) {
      var li = C.el('li', '');
      li.appendChild(C.el('span', 's-cm-ded-amount', C.won(ded.amount) + '원'));
      li.appendChild(C.el('span', 's-cm-ded-reason', ded.reason || ''));
      var btn = C.el('button', 's-ops-btn s-ops-btn--xs', '취소');
      btn.type = 'button';
      btn.setAttribute('data-settlement-cm-ded-void', String(ded.id || ''));
      li.appendChild(btn);
      e.list.appendChild(li);
    });
    C.hide(e.none, (row.deductions || []).length > 0);
    e.amount.value = '';
    e.reason.value = '';
    say(ctx, '');
    if (typeof d.showModal === 'function') d.showModal();
    else d.setAttribute('open', '');
    e.amount.focus();
  }

  function setBusy(ctx, busy) {
    ctx.state.dedBusy = busy;
    ctx.els.dialog.querySelectorAll('button').forEach(function (b) { b.disabled = busy; });
  }

  async function send(ctx, url, payload, done) {
    if (ctx.state.dedBusy) return;
    setBusy(ctx, true);
    try {
      await C.request('POST', url, payload);
      close(ctx);
      C.notice(ctx, done, false);
      C.load(ctx);
    } catch (err) {
      say(ctx, err.message);
    } finally {
      setBusy(ctx, false);
    }
  }

  function addDeduction(ctx) {
    var e = els(ctx);
    var amount = C.parseWon(e.amount.value);
    var reason = String(e.reason.value || '').trim();
    if (!amount || isNaN(amount)) { say(ctx, '금액을 숫자로 적어 주세요.'); e.amount.focus(); return; }
    if (!reason) { say(ctx, '사유를 적어 주세요.'); e.reason.focus(); return; }
    var orderId = ctx.state.dedOrderId;
    send(ctx, ctx.urls.order + encodeURIComponent(orderId) + '/settlement/issue', {
      department: 'SALES',
      amount: -Math.abs(amount),
      reason: reason,
      charge_to_user_id: Number(ctx.state.userId),
    }, '차감을 넣었어요.');
  }

  function voidDeduction(ctx, dedId) {
    if (!dedId) return;
    var reason = window.prompt('취소 사유를 적어 주세요.');
    if (reason === null) return;
    reason = String(reason).trim();
    if (!reason) { say(ctx, '취소 사유를 적어 주세요.'); return; }
    var orderId = ctx.state.dedOrderId;
    send(ctx, ctx.urls.order + encodeURIComponent(orderId) + '/settlement/deductions/'
      + encodeURIComponent(dedId) + '/void', { reason: reason }, '차감을 취소했어요.');
  }

  /** 차감 창 배선 — 루트 안 클릭 위임 하나(창도 루트 안에 있다). */
  C.bindDeduct = function (ctx) {
    if (!ctx.els.dialog) return;
    ctx.root.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t.closest || !ctx.root.contains(t)) return;
      var opener = t.closest('[data-settlement-cm-ded]');
      if (opener) { open(ctx, opener.getAttribute('data-settlement-cm-ded')); return; }
      if (t.closest('[data-settlement-cm-ded-close]')) { close(ctx); return; }
      if (t.closest('[data-settlement-cm-ded-add]')) { addDeduction(ctx); return; }
      var voider = t.closest('[data-settlement-cm-ded-void]');
      if (voider) voidDeduction(ctx, voider.getAttribute('data-settlement-cm-ded-void'));
    });
    ctx.els.dialog.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && !ev.isComposing && ev.target.tagName === 'INPUT') {
        ev.preventDefault();
        addDeduction(ctx);
      }
    });
  };

  C.deduct = true;
  if (typeof C.mountAll === 'function') C.mountAll();
})();
