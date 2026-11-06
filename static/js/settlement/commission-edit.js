/**
 * 정산 대시보드 · 탭 "영업 수수료" — 시공비 · 회계팀 지정 요율 자동 저장(설계서 §2.1-3 · §2.1-4).
 *
 * - 칸을 떠나거나(change) Enter 를 누르면 그 칸만 `PUT /api/sales-commission/inputs/<주문>` 으로 보낸다.
 *   Enter 는 다음 줄의 같은 칸으로 커서를 옮긴다(엑셀처럼 위에서 아래로 넣는다).
 * - **주문마다 줄을 세운다**(선례 static/js/shipment/shipment-dashboard.js 의 저장 줄). 같은 주문의 두 칸을
 *   빨리 고치면 요청이 겹쳐 내 앞 요청의 version 으로 409 가 난다 — 그래서 한 주문의 요청은 하나씩만
 *   날리고, 그동안 들어온 값은 모아 두었다가 앞 요청이 돌려준 새 version 으로 이어 보낸다.
 * - 성공하면 서버가 다시 계산한 줄(`data.row`)로 그 줄만 바꿔 그린다. 실패하면 그 칸만 빨갛게 하고
 *   이유를 위 줄에 적는다. 409 면 서버가 준 지금 값(`data.current`)으로 줄을 바꾸고 알린다.
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  var INSTALL_COST_MAX = 1000000000000;   // 서버 INSTALL_COST_MAX 와 같다
  var BAD_VALUE = {
    install_cost: '시공비는 숫자만 적어 주세요.',
    rate_override_bp: '요율은 4 또는 3.5 처럼 % 숫자로 적어 주세요.',
  };

  /** 위 줄 한 줄 안내. 빈 글자면 닫는다. */
  C.notice = function (ctx, text, isError) {
    var node = ctx.els.msg;
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('s-cm-msg--error', !!isError);
    C.hide(node, !text);
  };

  function rowOf(ctx, orderId) {
    var id = String(orderId);
    return ctx.state.rows.filter(function (row) { return String(row.order_id) === id; })[0] || null;
  }
  C.rowOf = rowOf;

  function savedValue(row, field) {
    var v = row ? row[field] : null;
    return v === undefined ? null : v;
  }

  /** 칸 표시 — kind: 'saving' | 'error' | null. 다시 그린 줄은 표시가 없는 새 칸이다. */
  function markCell(ctx, orderId, field, kind) {
    var tr = ctx.els.rows.querySelector('[data-settlement-cm-row="' + String(orderId) + '"]');
    var cell = tr && tr.querySelector('[data-settlement-cm-cell="' + field + '"]');
    if (!cell) return;
    cell.classList.toggle('s-cm-cell--saving', kind === 'saving');
    cell.classList.toggle('s-cm-cell--error', kind === 'error');
    var input = cell.querySelector('[data-settlement-cm-input]');
    if (input) {
      if (kind === 'error') input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
    }
  }

  function queueOf(ctx, orderId) {
    var key = String(orderId);
    if (!ctx.queue[key]) ctx.queue[key] = { pending: false, next: null, sent: {} };
    return ctx.queue[key];
  }

  async function run(ctx, orderId) {
    var q = queueOf(ctx, orderId);
    if (q.pending || !q.next) return;
    var payload = q.next;
    var fields = Object.keys(payload);
    var row = rowOf(ctx, orderId);
    q.next = null;
    q.pending = true;
    payload.version = row ? Number(row.input_version) || 0 : 0;
    try {
      var body = await C.request('PUT', ctx.urls.input + encodeURIComponent(orderId), payload);
      var data = body.data || {};
      if (data.row && ctx.state.basis === 'completion') {
        C.replaceRow(ctx, data.row);
      } else if (row && data.input) {
        row.input_version = data.input.version;   // 줄이 대상에서 빠졌어도 다음 요청 version 은 맞춘다
        C.load(ctx);
      }
      if (q.next === null) C.notice(ctx, '', false);
    } catch (err) {
      if (err.status === 409) {
        q.next = null;    // 낡은 화면에서 모은 값은 버린다
        q.sent = {};
        var current = err.body && err.body.data && err.body.data.current;
        if (current) C.replaceRow(ctx, current);
        else C.load(ctx);
        C.notice(ctx, C.STALE_MESSAGE, true);
      } else {
        fields.forEach(function (field) {
          delete q.sent[field];   // 같은 값으로 다시 시도할 수 있게
          markCell(ctx, orderId, field, 'error');
        });
        C.notice(ctx, err.message, true);
      }
    } finally {
      q.pending = false;
      if (q.next) run(ctx, orderId);
    }
  }

  /** 칸 값 하나를 줄에 넣는다. 바뀐 게 없으면(저장값 · 마지막으로 보낸 값과 같으면) 보내지 않는다. */
  function commit(ctx, input) {
    var tr = input.closest('[data-settlement-cm-row]');
    if (!tr) return;
    var orderId = tr.getAttribute('data-settlement-cm-row');
    var field = input.getAttribute('data-settlement-cm-input');
    var value = field === 'rate_override_bp' ? C.parseRateBp(input.value) : C.parseWon(input.value);
    if (typeof value === 'number' && (isNaN(value) || value > INSTALL_COST_MAX)) {
      markCell(ctx, orderId, field, 'error');
      C.notice(ctx, BAD_VALUE[field], true);
      return;
    }
    var q = queueOf(ctx, orderId);
    var last = Object.prototype.hasOwnProperty.call(q.sent, field)
      ? q.sent[field] : savedValue(rowOf(ctx, orderId), field);
    if (value === last) {
      markCell(ctx, orderId, field, null);
      return;
    }
    q.sent[field] = value;
    q.next = q.next || {};
    q.next[field] = value;
    markCell(ctx, orderId, field, 'saving');
    run(ctx, orderId);
  }

  /** 다음 줄의 같은 칸(없으면 그대로). */
  function focusNext(ctx, input) {
    var field = input.getAttribute('data-settlement-cm-input');
    var all = Array.prototype.slice.call(
      ctx.els.rows.querySelectorAll('[data-settlement-cm-input="' + field + '"]'));
    var next = all[all.indexOf(input) + 1];
    if (next) {
      next.focus();
      next.select();
    }
  }

  /** 입력 칸 배선 — 루트 안 위임 하나씩(줄을 다시 그려도 리스너가 늘지 않는다). */
  C.bindEdit = function (ctx) {
    ctx.root.addEventListener('change', function (e) {
      var input = e.target.closest && e.target.closest('[data-settlement-cm-input]');
      if (input && ctx.root.contains(input)) commit(ctx, input);
    });
    ctx.root.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.isComposing) return;
      var input = e.target.closest && e.target.closest('[data-settlement-cm-input]');
      if (!input || !ctx.root.contains(input)) return;
      e.preventDefault();
      commit(ctx, input);
      focusNext(ctx, input);
    });
  };

  C.edit = true;
  if (typeof C.mountAll === 'function') C.mountAll();
})();
