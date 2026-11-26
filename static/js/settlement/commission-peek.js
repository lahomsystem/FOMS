/**
 * 정산 대시보드 · 탭 "영업 수수료" — 도면 판 · 거래구분 합계(2026-11-26).
 *
 * - 품목 옆 [도면]을 누르면 표 오른쪽에 그 주문의 **확정된 최종 도면**(줄의 `drawings`)이 열린다. 회계팀이
 *   도면을 보며 요율을 정한다. 도면 그림이나 [크게]를 누르면 공용 사진 보기 창(`GlobalImageViewer`)으로 뜬다.
 * - 판 아래 요율 칸은 **표의 요율 칸에 값을 옮겨 change 를 일으킬 뿐**이다 — 저장 · 줄 세우기 · 409 는
 *   commission-edit.js 한 곳이 맡는다(저장 길을 두 벌로 만들지 않는다).
 * - 판이 열려 있는 동안 거래구분 · 시공비 · 차감 칸은 접힌다(CSS `.s-cm-split--open .s-cm-fold`).
 * - 표 위 합계: 거래구분마다 수수료 합(합계 줄과 같이 DONE 만) · 비율 셋(건수 · 출고가 · 수수료).
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  var DEALS = ['LAHOM', 'HAUD', 'PERSONAL', 'MANUAL'];
  var IMAGE_RE = /\.(png|jpe?g|gif|webp|bmp)$/i;

  function els(ctx) {
    if (ctx.peekEls) return ctx.peekEls;
    var q = function (name) { return ctx.root.querySelector('[data-settlement-cm-' + name + ']'); };
    ctx.peekEls = {
      mix: q('mix'), split: q('split'), peek: q('peek'), name: q('peek-name'), sub: q('peek-sub'),
      sheets: q('peek-sheets'), paper: q('peek-paper'), price: q('peek-price'), cost: q('peek-cost'),
      rate: q('peek-rate'), fee: q('peek-fee'), prev: q('peek-prev'), next: q('peek-next'),
    };
    return ctx.peekEls;
  }

  function drawingsOf(row) { return row && Array.isArray(row.drawings) ? row.drawings : []; }
  function currentRow(ctx) { return ctx.state.peekId ? C.rowOf(ctx, ctx.state.peekId) : null; }
  function pct(part, whole) { return whole > 0 ? Math.round(part / whole * 100) : 0; }

  /** 품목 칸의 [도면] 단추 — 확정 도면이 없으면 null(단추 없음). */
  C.peekButton = function (row) {
    var count = drawingsOf(row).length;
    if (!count) return null;
    var btn = C.el('button', 's-cm-peek-btn', count > 1 ? '도면 ' + count : '도면');
    btn.type = 'button';
    btn.setAttribute('data-settlement-cm-peek-open', String(row.order_id));
    btn.setAttribute('aria-label', (row.customer_name || '') + ' 도면 보기');
    return btn;
  };

  /* ═══════════════ 거래구분 합계 ═══════════════ */

  C.renderMix = function (ctx) {
    var host = els(ctx).mix;
    if (!host) return;
    var rows = ctx.state.rows;
    host.textContent = '';
    C.hide(host, !rows.length);
    if (!rows.length) return;
    var sums = {};
    var all = { count: rows.length, price: 0, fee: 0 };
    DEALS.forEach(function (key) { sums[key] = { count: 0, price: 0, fee: 0, wait: 0 }; });
    rows.forEach(function (row) {
      var s = sums[row.deal_type];
      if (!s) return;
      var price = Number(row.shipping_price) || 0;
      var fee = row.state === 'DONE' ? Number(row.commission) || 0 : 0;   // 합계 줄과 같은 규칙
      s.count += 1; s.price += price; s.fee += fee;
      if (row.state === 'WAIT_RATE' || row.state === 'WAIT_COST') s.wait += 1;
      all.price += price; all.fee += fee;
    });
    var bar = C.el('div', 's-cm-mix-bar');
    var cells = C.el('div', 's-cm-mix-cells');
    DEALS.forEach(function (key) {
      var s = sums[key];
      var seg = C.el('span', 's-cm-mix-seg s-cm-mix--' + key);
      seg.style.flexGrow = String(s.price);
      if (s.price > 0) bar.appendChild(seg);
      var cell = C.el('div', 's-cm-mix-cell');
      var head = C.el('small', '');
      head.appendChild(C.el('i', 's-cm-mix-dot s-cm-mix--' + key));
      head.appendChild(document.createTextNode(C.DEAL_LABELS[key]));
      cell.appendChild(head);
      cell.appendChild(C.el('b', '', C.won(s.fee) + '원'));
      var sub = C.el('span', 's-cm-mix-sub', '건수 ' + s.count + '건 ' + pct(s.count, all.count) + '% · 출고가 '
        + pct(s.price, all.price) + '% · 수수료 ' + pct(s.fee, all.fee) + '%');
      if (s.wait) sub.appendChild(C.el('em', '', ' · 미정 ' + s.wait + '건'));
      cell.appendChild(sub);
      cells.appendChild(cell);
    });
    host.appendChild(bar);
    host.appendChild(cells);
  };

  /* ═══════════════ 도면 판 ═══════════════ */

  function viewerFiles(row) {
    return drawingsOf(row).map(function (d) {
      return { view_url: d.view_url, download_url: d.download_url, filename: d.filename, key: d.key };
    });
  }

  function openBig(ctx) {
    var row = currentRow(ctx);
    var list = drawingsOf(row);
    var at = Math.min(ctx.state.peekSheet || 0, list.length - 1);
    if (!list.length) return;
    var viewer = window.GlobalImageViewer;
    if (viewer && typeof viewer.open === 'function') viewer.open(viewerFiles(row), at);
    else window.open(list[at].view_url, '_blank', 'noopener');
  }

  function renderSheet(ctx) {
    var e = els(ctx);
    var list = drawingsOf(currentRow(ctx));
    var at = Math.min(ctx.state.peekSheet || 0, Math.max(list.length - 1, 0));
    e.sheets.textContent = '';
    e.paper.textContent = '';
    C.hide(e.sheets, list.length < 2);
    list.forEach(function (d, i) {
      var chip = C.el('button', 's-ops-chip', '도면 ' + (i + 1));
      chip.type = 'button';
      chip.title = d.filename || '';
      chip.setAttribute('aria-pressed', String(i === at));
      chip.setAttribute('data-settlement-cm-peek-sheet', String(i));
      e.sheets.appendChild(chip);
    });
    if (!list.length) {
      e.paper.appendChild(C.el('p', 's-cm-peek-none', '확정된 도면이 없어요.'));
      return;
    }
    var d = list[at];
    if (d.is_image || IMAGE_RE.test(d.filename || '')) {
      var img = C.el('img', 's-cm-peek-img');
      img.src = d.view_url;
      img.alt = d.filename || '도면';
      img.title = '누르면 큰 창으로 떠요';
      img.setAttribute('data-settlement-cm-peek-big', '1');
      e.paper.appendChild(img);
    } else {
      var link = C.el('a', 's-ops-btn', (d.filename || '도면') + ' 열기');
      link.href = d.view_url;
      link.target = '_blank';
      link.rel = 'noopener';
      e.paper.appendChild(link);
    }
  }

  /** 다음 "요율 정해 주세요" 줄(지금 줄 뒤에서). 없으면 null. */
  function nextWaiting(ctx) {
    var rows = ctx.state.rows;
    var at = rows.indexOf(currentRow(ctx));
    for (var i = at + 1; i < rows.length; i += 1) if (rows[i].state === 'WAIT_RATE') return rows[i];
    return null;
  }

  function tableRateInput(ctx, row) {
    var tr = ctx.els.rows.querySelector('[data-settlement-cm-row="' + String(row.order_id) + '"]');
    return tr && tr.querySelector('[data-settlement-cm-input="rate_override_bp"]');
  }

  function renderDecide(ctx) {
    var e = els(ctx);
    var row = currentRow(ctx);
    if (!row) return;
    e.price.textContent = C.won(row.shipping_price);
    e.cost.textContent = C.won(row.install_cost);
    var typing = e.rate.querySelector('input');
    if (!(typing && typing === document.activeElement)) {   // 치는 중인 칸은 다시 그리지 않는다
      e.rate.textContent = '';
      if (row.deal_type === 'MANUAL' && ctx.state.basis === 'completion') {
        var input = C.el('input', 's-cm-input s-cm-input--rate');
        input.type = 'text';
        input.inputMode = 'decimal';
        input.autocomplete = 'off';
        input.value = C.ratePct(row.rate_override_bp);
        input.setAttribute('aria-label', '요율(%)');
        input.setAttribute('data-settlement-cm-peek-rate-input', String(row.order_id));   // 어느 주문의 칸인지 칸이 든다
        e.rate.appendChild(input);
        e.rate.appendChild(document.createTextNode(' %'));
      } else {
        e.rate.appendChild(C.el('b', '', row.rate_bp === null || row.rate_bp === undefined ? '—' : C.ratePct(row.rate_bp) + '%'));
      }
    }
    var done = row.state === 'DONE';
    e.fee.textContent = done ? C.won(row.commission) : (C.STATE_LABELS[row.state] || '')
      + (row.state === 'FORECAST' && row.commission != null ? ' ' + C.won(row.commission) : '');
    e.fee.classList.toggle('s-cm-wait', !done && row.state !== 'FORECAST');
    e.prev.disabled = ctx.state.rows.indexOf(row) <= 0;
    e.next.disabled = !nextWaiting(ctx);
  }

  function markRow(ctx) {
    var id = String(ctx.state.peekId || '');
    Array.prototype.forEach.call(ctx.els.rows.querySelectorAll('[data-settlement-cm-row]'), function (tr) {
      tr.classList.toggle('s-cm-row--on', !!id && tr.getAttribute('data-settlement-cm-row') === id);
    });
  }

  C.peekOpen = function (ctx, orderId, focusRate) {
    var e = els(ctx);
    var row = C.rowOf(ctx, orderId);
    if (!row || !e.peek) return;
    var wasOpen = !!ctx.state.peekId;
    ctx.state.peekId = String(orderId);
    ctx.state.peekSheet = 0;
    e.split.classList.add('s-cm-split--open');
    C.hide(e.peek, false);
    e.name.textContent = row.customer_name || '';
    e.sub.textContent = [row.construction_date ? row.construction_date + ' 시공' : '', row.product_summary || '']
      .filter(Boolean).join(' · ');
    e.rate.textContent = '';
    markRow(ctx);
    renderSheet(ctx);
    if (wasOpen) renderDecide(ctx); else C.renderTotal(ctx);   // 합계 줄 칸 수가 바뀐다(→ peekSync → renderDecide)
    var input = e.rate.querySelector('input');
    if (focusRate && input) { input.focus(); input.select(); }
  };

  C.peekClose = function (ctx) {
    var e = els(ctx);
    if (!ctx.state.peekId || !e.peek) return;
    ctx.state.peekId = null;
    e.split.classList.remove('s-cm-split--open');
    C.hide(e.peek, true);
    markRow(ctx);
    C.renderTotal(ctx);
  };

  /** 줄이 바뀐 뒤(저장 · 다시 조회) 열린 판을 맞춘다. 그 주문이 표에서 빠졌으면 닫는다. */
  C.peekSync = function (ctx) {
    C.renderMix(ctx);
    if (!ctx.state.peekId) return;
    if (!currentRow(ctx)) { C.peekClose(ctx); return; }
    renderDecide(ctx);
  };

  /**
   * 판의 요율 값을 표 칸으로 옮겨 저장을 일으킨다(저장은 commission-edit.js). 주문은 **칸이 든 번호**로 찾는다 —
   * Enter 로 다음 주문으로 넘어간 뒤 옛 칸의 change 가 늦게 와도 새 주문에 그 값이 들어가지 않는다.
   */
  function commitRate(ctx, input) {
    var row = C.rowOf(ctx, input.getAttribute('data-settlement-cm-peek-rate-input'));
    var target = row && tableRateInput(ctx, row);
    if (!target || target.value === input.value) return;
    target.value = input.value;
    target.dispatchEvent(new Event('change', { bubbles: true }));
  }

  C.bindPeek = function (ctx) {
    ctx.root.addEventListener('click', function (e) {
      var hit = function (name) { return e.target.closest && e.target.closest('[data-settlement-cm-' + name + ']'); };
      var open = hit('peek-open');
      if (open) { C.peekOpen(ctx, open.getAttribute('data-settlement-cm-peek-open'), true); return; }
      if (!ctx.state.peekId) return;
      var sheet = hit('peek-sheet');
      if (sheet) { ctx.state.peekSheet = Number(sheet.getAttribute('data-settlement-cm-peek-sheet')) || 0; renderSheet(ctx); return; }
      if (hit('peek-big')) { openBig(ctx); return; }
      if (hit('peek-close')) { C.peekClose(ctx); return; }
      var rows = ctx.state.rows;
      if (hit('peek-prev')) {
        var before = rows[rows.indexOf(currentRow(ctx)) - 1];
        if (before) C.peekOpen(ctx, before.order_id, true);
        return;
      }
      if (hit('peek-next')) {
        var after = nextWaiting(ctx);
        if (after) C.peekOpen(ctx, after.order_id, true);
      }
    });
    ctx.root.addEventListener('change', function (e) {
      if (e.target.hasAttribute && e.target.hasAttribute('data-settlement-cm-peek-rate-input')) commitRate(ctx, e.target);
    });
    ctx.root.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.isComposing) return;
      if (!(e.target.hasAttribute && e.target.hasAttribute('data-settlement-cm-peek-rate-input'))) return;
      e.preventDefault();
      commitRate(ctx, e.target);
      var after = nextWaiting(ctx);
      if (after) C.peekOpen(ctx, after.order_id, true);
    });
  };

  C.peek = true;
  if (typeof C.mountAll === 'function') C.mountAll();
})();
