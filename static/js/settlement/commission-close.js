/**
 * 정산 대시보드 · 탭 "영업 수수료" — 달 마감 · 마감 기록(설계서 §2.1-7 · §2.1-8 · §8 — 플랜 T10).
 *
 * - [마감](위 줄, 시공 완료 기준에서만 보임) → `GET /closings/preview` 로 확인 창을 채운다(줄 수 · 조정 N건 · 합 ±X원
 *   (T12 §8.2) · 합계 · 세금 · 실지급, 시공비 · 요율을 기다리는 줄은 다음 마감으로 넘어간다는 말과 조정하지 않는
 *   주문(지워짐 · 단계 되돌림 · 시공비 빈칸) 한 줄). 서버가 `can_close: false` 면
 *   `block_reason` 을 보이고 [마감하기]를 끈다. [마감하기] → `POST /closings` → 표(마감된 줄이 빠진다)와 기록을 다시 읽는다.
 * - 마감 기록(표 아래): 달 · 줄 수 · 합계 · 실지급 · 상태 · [내려받기](CSV 링크) · [지급 완료](마감만, 확인 창) ·
 *   [마감 취소](가장 최근 마감이 아직 마감 상태일 때만, 이유 입력). 끝나면 기록을 다시 읽는다.
 * 서버 문자열은 textContent 로만 넣는다. 쓰기 요청의 CSRF 헤더는 공용 fetch 래퍼가 싣는다(WRITE-GUARD-01).
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  var STATUS_LABELS = { CLOSED: '마감', PAID: '지급 완료' };

  function q(ctx, sel) { return ctx.root.querySelector(sel); }

  function dialogEls(ctx) {
    var d = q(ctx, '[data-settlement-cm-close-dialog]');
    if (!d) return null;
    return {
      dialog: d,
      title: d.querySelector('[data-settlement-cm-close-title]'),
      sum: d.querySelector('[data-settlement-cm-close-sum]'),
      waiting: d.querySelector('[data-settlement-cm-close-waiting]'),
      msg: d.querySelector('[data-settlement-cm-close-msg]'),
      confirm: d.querySelector('[data-settlement-cm-close-confirm]'),
    };
  }

  function say(e, text) {
    e.msg.textContent = text || '';
    C.hide(e.msg, !text);
  }

  function freelancerName(ctx) {
    var id = String(ctx.state.userId);
    var hit = (ctx.state.freelancers || []).filter(function (f) { return String(f.user_id) === id; })[0];
    return hit ? hit.match_name : '';
  }

  /** 마감 버튼은 지급 기준(시공 완료)에서만 보인다. commission.js 의 syncControls 가 부른다. */
  C.syncClose = function (ctx) {
    var btn = q(ctx, '[data-settlement-cm-close-open]');
    C.hide(btn, ctx.state.basis !== 'completion');
  };

  /* ═══════════════ 확인 창 ═══════════════ */

  function sumRow(list, label, value) {
    list.appendChild(C.el('dt', '', label));
    list.appendChild(C.el('dd', '', value));
  }

  /** 조정 합 — 더하면 "+6,000", 빼면 "−6,000". */
  function signedWon(v) {
    var n = Number(v) || 0;
    return (n > 0 ? '+' : n < 0 ? '−' : '') + C.won(Math.abs(n));
  }

  /** 조정하지 않는 주문을 까닭별로 센 한 문장. 없으면 빈 글. */
  function skippedText(list) {
    var order = [];
    var counts = {};
    (list || []).forEach(function (s) {
      var key = s.reason_text || '다시 셀 수 없는 주문';
      if (!counts[key]) { counts[key] = 0; order.push(key); }
      counts[key] += 1;
    });
    if (!order.length) return '';
    return order.map(function (k) { return k + ' ' + counts[k] + '건'; }).join(' · ') + '은 조정하지 않아요.';
  }

  function fillPreview(e, data) {
    var t = data.totals || {};
    e.sum.textContent = '';
    sumRow(e.sum, '줄 수', (data.lines || []).length + '줄');
    if (data.adjust_count) sumRow(e.sum, '조정', data.adjust_count + '건 · 합 ' + signedWon(data.adjust_total) + '원');
    sumRow(e.sum, '합계', C.won(t.gross) + '원');
    if (data.tax_type === 'WITHHOLD_3_3') {
      sumRow(e.sum, '소득세', C.won(t.tax_income) + '원');
      sumRow(e.sum, '지방소득세', C.won(t.tax_local) + '원');
    } else if (data.tax_type === 'VAT_10') {
      sumRow(e.sum, '부가세', C.won(t.vat) + '원');
    }
    sumRow(e.sum, '실지급', C.won(t.net) + '원');
    var counts = data.waiting_counts || {};
    var parts = [];
    if (counts.WAIT_COST) parts.push('시공비 기다리는 ' + counts.WAIT_COST + '건');
    if (counts.WAIT_RATE) parts.push('요율 정할 ' + counts.WAIT_RATE + '건');
    var notes = [];
    if (parts.length) notes.push(parts.join(' · ') + '은 다음 마감으로 넘어가요.');
    var skipped = skippedText(data.adjust_skipped);
    if (skipped) notes.push(skipped);
    e.waiting.textContent = notes.join(' ');
    C.hide(e.waiting, !notes.length);
    if (!data.can_close) say(e, data.block_reason || '이 달은 마감할 수 없어요.');
    e.confirm.disabled = !data.can_close;
  }

  async function openDialog(ctx) {
    var e = dialogEls(ctx);
    var s = ctx.state;
    if (!e || !s.userId || !C.monthOk(s.month)) return;
    e.title.textContent = freelancerName(ctx) + ' ' + s.month + ' 마감';
    e.sum.textContent = '';
    e.waiting.textContent = '불러오는 중이에요.';
    C.hide(e.waiting, false);
    e.confirm.disabled = true;
    say(e, '');
    if (typeof e.dialog.showModal === 'function') e.dialog.showModal();
    else e.dialog.setAttribute('open', '');
    var query = new URLSearchParams({ user_id: String(s.userId), month: s.month });
    try {
      var body = await C.request('GET', ctx.urls.closings + '/preview?' + query.toString());
      fillPreview(e, body.data || {});
    } catch (err) {
      C.hide(e.waiting, true);
      say(e, err.message);
    }
  }

  function closeDialog(ctx) {
    var e = dialogEls(ctx);
    if (!e) return;
    if (typeof e.dialog.close === 'function' && e.dialog.open) e.dialog.close();
    else e.dialog.removeAttribute('open');
  }

  async function confirmClose(ctx) {
    var e = dialogEls(ctx);
    if (!e || e.confirm.disabled) return;
    var s = ctx.state;
    e.confirm.disabled = true;
    try {
      await C.request('POST', ctx.urls.closings, { user_id: Number(s.userId), month: s.month });
      closeDialog(ctx);
      C.notice(ctx, s.month + ' 마감했어요.', false);
      s.rows = [];
      C.load(ctx);
      C.loadClosings(ctx);
    } catch (err) {
      say(e, err.message);
      e.confirm.disabled = false;
    }
  }

  /* ═══════════════ 마감 기록 ═══════════════ */

  function actionButton(text, attr, id) {
    var btn = C.el('button', 's-ops-btn s-ops-btn--xs', text);
    btn.type = 'button';
    btn.setAttribute(attr, String(id));
    return btn;
  }

  function closingRow(ctx, item, isLatest) {
    var tr = C.el('tr', '');
    tr.appendChild(C.el('td', '', item.month));
    tr.appendChild(C.el('td', 's-ops-num', String(item.line_count || 0)));
    tr.appendChild(C.el('td', 's-ops-num', C.won(item.gross)));
    tr.appendChild(C.el('td', 's-ops-num', C.won(item.net)));
    var paid = item.status === 'PAID';
    var state = C.el('td', paid ? 's-cm-paid' : '', STATUS_LABELS[item.status] || item.status || '');
    if (paid && item.paid_at) state.appendChild(C.el('span', 's-cm-dim', ' ' + C.shortDay(item.paid_at)));
    tr.appendChild(state);
    var actions = C.el('td', 's-cm-closing-actions');
    var link = C.el('a', 's-ops-btn s-ops-btn--xs', '내려받기');
    link.href = ctx.urls.exportCsv + '?' + new URLSearchParams({ user_id: String(item.user_id), month: item.month });
    link.setAttribute('download', '');
    actions.appendChild(link);
    if (!paid) actions.appendChild(actionButton('지급 완료', 'data-settlement-cm-closing-paid', item.id));
    if (!paid && isLatest) actions.appendChild(actionButton('마감 취소', 'data-settlement-cm-closing-cancel', item.id));
    tr.appendChild(actions);
    return tr;
  }

  function closingOf(ctx, id) {
    return (ctx.state.closings || []).filter(function (c) { return String(c.id) === String(id); })[0] || null;
  }

  /** 고른 프리랜서의 마감 기록을 다시 읽는다(최근 달 먼저 — 서버 순서 그대로). */
  C.loadClosings = async function (ctx) {
    var box = q(ctx, '[data-settlement-cm-closings]');
    var s = ctx.state;
    if (!box || !s.userId) return;
    var seq = s.closingSeq = (s.closingSeq || 0) + 1;
    var tbody = q(ctx, '[data-settlement-cm-closings-rows]');
    var empty = q(ctx, '[data-settlement-cm-closings-empty]');
    var wrap = q(ctx, '[data-settlement-cm-closings-wrap]');
    try {
      var body = await C.request('GET', ctx.urls.closings + '?' + new URLSearchParams({ user_id: String(s.userId) }));
      if (seq !== s.closingSeq) return;
      s.closings = Array.isArray((body.data || {}).closings) ? body.data.closings : [];
      tbody.textContent = '';
      s.closings.forEach(function (item, i) { tbody.appendChild(closingRow(ctx, item, i === 0)); });
      empty.textContent = '아직 마감한 달이 없어요.';
      C.hide(empty, s.closings.length > 0);
      C.hide(wrap, !s.closings.length);
      C.hide(box, false);
    } catch (err) {
      if (seq !== s.closingSeq) return;
      empty.textContent = err.message;
      C.hide(empty, false);
      C.hide(wrap, true);
      C.hide(box, false);
    }
  };

  async function markPaid(ctx, id) {
    var item = closingOf(ctx, id);
    if (!item || !window.confirm(item.month + ' 지급 완료로 바꿀까요? 바꾼 뒤에는 마감을 취소할 수 없어요.')) return;
    try {
      await C.request('POST', ctx.urls.closings + '/' + encodeURIComponent(id) + '/paid');
      C.notice(ctx, item.month + ' 지급 완료로 바꿨어요.', false);
    } catch (err) {
      C.notice(ctx, err.message, true);
    }
    C.loadClosings(ctx);
  }

  async function cancelClosing(ctx, id) {
    var item = closingOf(ctx, id);
    if (!item) return;
    var reason = window.prompt(item.month + ' 마감을 취소하는 이유를 적어 주세요.');
    if (reason === null) return;
    reason = String(reason).trim();
    if (!reason) { C.notice(ctx, '취소 이유를 적어 주세요.', true); return; }
    try {
      await C.request('DELETE', ctx.urls.closings + '/' + encodeURIComponent(id), { reason: reason });
      C.notice(ctx, item.month + ' 마감을 취소했어요.', false);
      ctx.state.rows = [];
      C.load(ctx);
    } catch (err) {
      C.notice(ctx, err.message, true);
    }
    C.loadClosings(ctx);
  }

  /** 마감 배선 — 루트 안 클릭 위임 하나(확인 창 · 기록 표도 루트 안에 있다). */
  C.bindClose = function (ctx) {
    ctx.root.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t.closest || !ctx.root.contains(t)) return;
      if (t.closest('[data-settlement-cm-close-open]')) { openDialog(ctx); return; }
      if (t.closest('[data-settlement-cm-close-cancel]')) { closeDialog(ctx); return; }
      if (t.closest('[data-settlement-cm-close-confirm]')) { confirmClose(ctx); return; }
      var paid = t.closest('[data-settlement-cm-closing-paid]');
      if (paid) { markPaid(ctx, paid.getAttribute('data-settlement-cm-closing-paid')); return; }
      var cancel = t.closest('[data-settlement-cm-closing-cancel]');
      if (cancel) cancelClosing(ctx, cancel.getAttribute('data-settlement-cm-closing-cancel'));
    });
  };

  C.closing = true;
  if (typeof C.mountAll === 'function') C.mountAll();
})();
