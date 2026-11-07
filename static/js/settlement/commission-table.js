/**
 * 정산 대시보드 · 탭 "영업 수수료" — 표 그리기(줄 · 합계 줄 · 비슷한 이름 경고).
 *
 * 칸 순서는 회계팀 엑셀과 같다(설계서 §2.1-2): 시공일 · 고객명 · 품목 · 거래구분 · 출고가 · 시공비 · 차감 ·
 * 요율 · 수수료, 줄 끝에 "본인 수정" 표시. 합계 줄은 표 맨 위 한 줄이고 화면이 가진 줄로 다시 센다 —
 * 시공비를 넣어 줄 하나만 바꿔 그려도 합계가 같이 맞는다(서버 summary 와 같은 규칙: DONE 만 더한다).
 * 서버 문자열은 전부 textContent 로 넣는다.
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  var ORDER_URL = '/erp/orders/';

  function td(cls, text) { return C.el('td', cls, text); }

  function orderLink(orderId, name) {
    var a = C.el('a', 's-cm-cust', name || '-');
    a.href = ORDER_URL + encodeURIComponent(orderId);
    return a;
  }

  function numberInput(field, value, label) {
    var input = C.el('input', field === 'rate_override_bp' ? 's-cm-input s-cm-input--rate' : 's-cm-input');
    input.type = 'text';
    input.inputMode = field === 'rate_override_bp' ? 'decimal' : 'numeric';
    input.autocomplete = 'off';
    input.setAttribute('data-settlement-cm-input', field);
    input.setAttribute('aria-label', label);
    input.defaultValue = value;   // 다시 그릴 때 "아직 저장 안 된 글자" 판정 기준
    input.value = value;
    return input;
  }

  /** 입력 칸에 보일 값 — 시공비는 쉼표, 요율은 %. 저장 뒤 다시 그릴 때도 같은 함수다. */
  C.inputText = function (row, field) {
    if (field === 'rate_override_bp') return C.ratePct(row.rate_override_bp);
    return row.install_cost === null || row.install_cost === undefined ? '' : C.won(row.install_cost);
  };

  /** 칸 글자가 줄의 저장값과 같은 값인지(쉼표 · % 표기 차이는 무시). */
  C.sameAsSaved = function (row, field, text) {
    var saved = field === 'rate_override_bp' ? row.rate_override_bp : row.install_cost;
    var typed = field === 'rate_override_bp' ? C.parseRateBp(text) : C.parseWon(text);
    return (saved === null || saved === undefined) ? typed === null : typed === Number(saved);
  };

  function commissionCell(row) {
    var cell = td('s-ops-num');
    if (row.state === 'DONE') {
      cell.textContent = C.won(row.commission);
    } else if (row.state === 'FORECAST') {
      cell.className += ' s-cm-forecast';
      cell.textContent = row.commission === null || row.commission === undefined
        ? C.STATE_LABELS.FORECAST : C.STATE_LABELS.FORECAST + ' ' + C.won(row.commission);
    } else {
      cell.className += ' s-cm-wait';
      cell.textContent = C.STATE_LABELS[row.state] || '';
    }
    return cell;
  }

  function rateCell(row, editable) {
    var cell = td('s-ops-num');
    if (row.deal_type === 'MANUAL' && editable) {
      cell.appendChild(numberInput('rate_override_bp', C.inputText(row, 'rate_override_bp'), '요율(%)'));
      cell.appendChild(document.createTextNode(' %'));
    } else if (row.rate_bp !== null && row.rate_bp !== undefined) {
      cell.textContent = C.ratePct(row.rate_bp) + '%';
    } else {
      cell.className += ' s-cm-dim';
      cell.textContent = '—';
    }
    return cell;
  }

  function selfEditCell(row) {
    var cell = td('');
    var edits = row.self_edits || [];
    if (!edits.length) return cell;
    var box = C.el('details', 's-cm-self');
    box.appendChild(C.el('summary', '', '본인 수정'));
    var list = C.el('ul', '');
    edits.forEach(function (edit) {
      var what = C.SELF_EDIT_LABELS[edit.field] || '값을';
      list.appendChild(C.el('li', '', what + ' ' + C.shortDay(edit.at) + '에 바꿨어요'));
    });
    box.appendChild(list);
    cell.appendChild(box);
    return cell;
  }

  /** 줄 하나. 시공 완료 기준일 때만 입력 칸 · 차감 버튼이 있다(실측일 기준은 읽기만). */
  C.rowEl = function (ctx, row) {
    var editable = ctx.state.basis === 'completion';
    var tr = C.el('tr', '');
    tr.setAttribute('data-settlement-cm-row', String(row.order_id));
    tr.appendChild(td('', (editable ? row.construction_date : row.measurement_date) || '—'));
    var cust = td('');
    cust.appendChild(orderLink(row.order_id, row.customer_name));
    tr.appendChild(cust);
    var product = td('s-cm-product', row.product_summary || '—');
    if (row.product_summary) product.title = row.product_summary;
    tr.appendChild(product);
    tr.appendChild(td('', C.DEAL_LABELS[row.deal_type] || ''));
    tr.appendChild(td('s-ops-num', C.won(row.shipping_price)));

    var cost = td('s-ops-num');
    cost.setAttribute('data-settlement-cm-cell', 'install_cost');
    if (editable) cost.appendChild(numberInput('install_cost', C.inputText(row, 'install_cost'), '시공비'));
    else cost.textContent = C.won(row.install_cost);
    tr.appendChild(cost);

    var ded = td('s-ops-num');
    if (editable) {
      var btn = C.el('button', 's-cm-ded-btn', C.won(row.deduction_total || 0));
      btn.type = 'button';
      btn.setAttribute('data-settlement-cm-ded', String(row.order_id));
      btn.setAttribute('aria-label', '차감 보기 · 넣기');
      ded.appendChild(btn);
    } else {
      ded.textContent = C.won(row.deduction_total || 0);
    }
    tr.appendChild(ded);

    var rate = rateCell(row, editable);
    rate.setAttribute('data-settlement-cm-cell', 'rate_override_bp');
    tr.appendChild(rate);
    tr.appendChild(commissionCell(row));
    tr.appendChild(selfEditCell(row));
    return tr;
  };

  /** 화면이 가진 줄로 합계를 다시 센다(서버 `_summary` 와 같은 규칙). */
  function summarize(rows) {
    var counts = { WAIT_COST: 0, WAIT_RATE: 0, FORECAST: 0 };
    var total = 0;
    rows.forEach(function (row) {
      if (row.state === 'DONE') total += Number(row.commission) || 0;
      else if (Object.prototype.hasOwnProperty.call(counts, row.state)) counts[row.state] += 1;
    });
    return { total: total, counts: counts };
  }

  C.renderTotal = function (ctx) {
    var host = ctx.els.total;
    if (!host) return;
    host.textContent = '';
    var sum = summarize(ctx.state.rows);
    var tr = C.el('tr', '');
    var label = C.el('td', '', '합계');
    label.colSpan = 8;
    var waits = ['WAIT_COST', 'WAIT_RATE', 'FORECAST']
      .filter(function (key) { return sum.counts[key] > 0; })
      .map(function (key) { return C.STATE_LABELS[key] + ' ' + sum.counts[key] + '건'; });
    if (waits.length) label.appendChild(C.el('span', 's-cm-total-wait', waits.join(' · ')));
    tr.appendChild(label);
    tr.appendChild(td('s-ops-num', C.won(sum.total)));
    tr.appendChild(td(''));
    host.appendChild(tr);
  };

  C.renderNear = function (ctx, nearMisses) {
    var list = nearMisses || [];
    C.hide(ctx.els.near, !list.length);
    if (!list.length) return;
    ctx.els.nearText.textContent = '담당자 이름이 프리랜서와 비슷하지만 다른 주문이 ' + list.length + '건 있어요';
    ctx.els.nearList.textContent = '';
    list.forEach(function (item) {
      var li = C.el('li', '');
      li.appendChild(orderLink(item.order_id, item.customer_name));
      li.appendChild(document.createTextNode(' — 적힌 이름 ' + (item.name_seen || '')));
      ctx.els.nearList.appendChild(li);
    });
  };

  /** 표 전체를 다시 그린다(조회 직후). */
  C.renderRows = function (ctx) {
    var body = ctx.els.rows;
    body.textContent = '';
    ctx.state.rows.forEach(function (row) { body.appendChild(C.rowEl(ctx, row)); });
    C.renderTotal(ctx);
  };

  /**
   * 줄 하나만 바꿔 그린다(저장 · 409 뒤). 그 줄에 커서가 있으면 같은 칸으로 되돌리고, 아직 저장 안 된
   * 글자가 있으면 지우지 않는다 — 빨리 치는 사람의 입력이 다시 그리기에 먹히지 않게.
   */
  C.replaceRow = function (ctx, row) {
    var id = String(row.order_id);
    var rows = ctx.state.rows;
    for (var i = 0; i < rows.length; i += 1) {
      if (String(rows[i].order_id) === id) { rows[i] = row; break; }
    }
    var old = ctx.els.rows.querySelector('[data-settlement-cm-row="' + id + '"]');
    if (old) {
      var active = document.activeElement;
      var keep = null;
      if (active && old.contains(active) && active.hasAttribute('data-settlement-cm-input')) {
        var field = active.getAttribute('data-settlement-cm-input');
        keep = { field: field, value: active.value, dirty: active.value !== active.defaultValue };
      }
      var fresh = C.rowEl(ctx, row);
      old.parentNode.replaceChild(fresh, old);
      if (keep) {
        var input = fresh.querySelector('[data-settlement-cm-input="' + keep.field + '"]');
        if (input) {
          if (keep.dirty && !C.sameAsSaved(row, keep.field, keep.value)) input.value = keep.value;
          input.focus();
        }
      }
    }
    C.renderTotal(ctx);
  };

  C.table = true;
  if (typeof C.mountAll === 'function') C.mountAll();
})();
