/**
 * 승인 대기 옆 창 '제안 자세히'(T8 · 판 ⑥ 오른쪽 — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.3 · 3.6) —
 * window.FOMS_DS_INBOX_ERP_ASIDE.
 *
 * 차례: 머리(AI 직원 · 닫기) · 할 일 꼬리표 · 제목 · 때 · 이유 · 근거 · 바뀌는 칸 표 · 승인하면 차례로(API 의 steps 그대로 —
 * 시공 팀 · 인원 글은 서버도 이 파일도 만들지 않는다, D211) · 2주 승인율 · 넣을 값 칸(고쳐서 승인) · 사유 · [승인] [고쳐서 승인]
 * [나중에] · 거절 까닭 칩. mode 'link' 면 [승인] 대신 [주문에서 처리]. 폰에서 승인할 수 없는 할 일은 폰에서 결정 단추 대신 안내.
 * 넣을 값 꼴: date · time_slot · choice · masked_text · users(여러 명 고르기 — 목록은 params[].choices) · flag(켜고 끄기).
 * 꼭 있어야 하는 값이 비면 [승인]이 눌리지 않는다(도면 담당 맡기기는 사람을 고른 뒤에만). 글은 textContent 만 · 인라인 스타일 없음
 * (승인율 막대 너비만 style.setProperty).
 */
(function () {
  'use strict';

  var OPTIONAL_KINDS = ['time_slot', 'flag'];
  var NOTICE_HEAD = '손님 알림톡';  // 손님에게 나가는 알림톡 줄의 머리(서버 views.NOTICE_HEAD 와 같은 글)

  function kit() {
    return window.FOMS_DS_INBOX_ERP_CARD;
  }

  function el(tag, opts) {
    return window.FOMS_BRAIN_DOM.el(tag, opts);
  }

  function block(title, children) {
    return el('div', { cls: 'f-col f-gap4', children: [el('span', { cls: 'f-h6', text: title })].concat(children) });
  }

  function isEmpty(value) {
    return value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length);
  }

  /** 꼭 있어야 하나 — API 가 required 를 주면 그 값, 아니면 시간대 · 켜고 끄기 말고는 꼭. */
  function required(param) {
    return param.required !== undefined ? !!param.required : OPTIONAL_KINDS.indexOf(param.kind) < 0;
  }

  function head(d) {
    var close = kit().button('', 'close', 'f-btn-minimal f-btn-small f-push', 'cross');
    close.setAttribute('aria-label', '옆 창 닫기');
    return el('div', { cls: 'f-aside-head', children: [kit().mark(d), el('span', { cls: 'f-section-title', text: '제안 자세히' }), close] });
  }

  function title(d, today) {
    var type = el('span', { cls: 'f-type', children: [kit().icon('flash'), el('span', { text: 'ERP 할 일 · ' + d.action_label })] });
    var at = String(d.created_at || '');
    var when = [at.slice(0, 10) === today ? '오늘 ' + at.slice(11, 16) : at, d.source_label].filter(Boolean).join(' · ');
    return el('div', { cls: 'f-col f-gap4', children: [el('span', { cls: 'f-row f-gap4', children: [type,
      el('span', { cls: 'f-tag f-tag-minimal f-tag-primary', text: '새로 붙음' })] }),
      el('h2', { cls: 'f-h5', text: d.title }), el('span', { cls: 'f-small f-muted', text: when })] });
  }

  function changes(d) {
    var body = el('tbody');
    (d.changes || []).forEach(function (row) {
      body.appendChild(el('tr', { children: [el('th', { cls: 'f-td-nw f-muted', text: row.field, attrs: { scope: 'row' } }),
        el('td', { cls: 'f-td-nw', text: row.before }), el('td', { cls: 'f-strong', text: row.after })] }));
    });
    var head = el('thead', { children: [el('tr', { children: ['칸', '지금', '승인하면'].map(function (t) {
      return el('th', { text: t, attrs: { scope: 'col' } });
    }) })] });
    return el('div', { cls: 'f-section fb-erp-diff', children: [el('table', { cls: 'f-table f-table-compact', children: [head, body] })] });
  }

  function steps(d) {
    var list = el('ol', { cls: 'f-col f-gap4 f-small' });
    (d.steps || []).forEach(function (text, i) {
      list.appendChild(el('li', { cls: 'f-row-nw', children: [el('span', { cls: 'f-tag f-tag-minimal f-tag-round', text: i + 1 }),
        el('span', { text: text })] }));
    });
    var why = el('span', { cls: 'f-why fb-erp-why-line', children: [kit().icon('automatic-updates'),
      el('span', { text: '승인하면 지금 FOMS 의 그 기능이 그대로 돌아요 · 할 일 기록에 남아요' })] });
    return block('승인하면 차례로', [list, why]);
  }

  function rate(d) {
    var r = d.rate || {};
    var pct = r.pct === null || r.pct === undefined ? null : Number(r.pct);
    var bar = el('span', { cls: 'f-progress f-progress-success', attrs: { role: 'img', 'aria-label': '승인율 ' + (pct === null ? '없음' : pct + '%') } });
    var fill = el('span');
    if (pct !== null) fill.style.setProperty('width', Math.max(0, Math.min(100, pct)) + '%');
    bar.appendChild(fill);
    bar.hidden = pct === null;
    return el('div', { cls: 'f-card f-card-compact f-col', children: [el('div', { cls: 'f-row', children: [
      el('span', { cls: 'f-small', text: (d.agent_label || 'AI') + ' · ' + d.action_label + ' ' + (r.days || 14) + '일 승인율' }),
      el('span', { cls: 'f-strong f-num f-push', text: pct === null ? '아직 결정 없음' : pct + '%' })] }), bar] });
  }

  function control(p, today) {
    var attrs = { 'data-erp-param': p.name, 'data-erp-kind': p.kind, 'aria-label': p.label };
    if (p.kind === 'users') {
      var group = el('div', { cls: 'f-col f-gap4', attrs: attrs });
      var picked = Array.isArray(p.value) ? p.value.map(String) : [];
      (p.choices || []).forEach(function (c) {
        var box = el('input', { attrs: { type: 'checkbox', value: c.value } });
        box.checked = picked.indexOf(String(c.value)) >= 0;
        group.appendChild(el('label', { cls: 'f-check', children: [box, el('span', { text: c.label })] }));
      });
      if (!(p.choices || []).length) group.appendChild(el('span', { cls: 'f-help', text: '고를 사람이 없어요.' }));
      return group;
    }
    if (p.kind === 'flag') {
      var flag = el('input', { attrs: Object.assign({ type: 'checkbox' }, attrs) });
      flag.checked = !!p.value;
      return el('label', { cls: 'f-check', children: [flag, el('span', { text: p.label })] });
    }
    if (p.kind === 'time_slot' || p.kind === 'choice') {
      var select = el('select', { cls: 'f-select', attrs: attrs });
      (p.choices || []).forEach(function (c) {
        var opt = el('option', { text: c.label, attrs: { value: c.value } });
        opt.selected = String(c.value) === String(p.value || '');
        select.appendChild(opt);
      });
      return select;
    }
    var input = el('input', { cls: 'f-input', attrs: Object.assign({ type: p.kind === 'date' ? 'date' : 'text',
      min: p.kind === 'date' ? today : null, maxlength: p.kind === 'date' ? null : 500 }, attrs) });
    input.value = p.value === null || p.value === undefined ? '' : String(p.value);
    return input;
  }

  function form(d, today, open) {
    var box = el('div', { cls: 'f-col fb-erp-form', attrs: { 'data-erp-form': '1' } });
    (d.params || []).forEach(function (p) {
      var field = control(p, today);
      box.appendChild(p.kind === 'flag' ? field : el('label', { cls: 'f-col f-gap4', children: [
        el('span', { cls: 'f-label', text: p.label + (required(p) ? ' *' : '') }), field] }));
    });
    box.appendChild(kit().button('이 값으로 승인', 'approve-edit', 'f-btn-primary', 'tick'));
    box.hidden = !open;
    return box;
  }

  function reasonBox(d) {
    var cr = d.change_reason || {};
    if (!cr.required) return null;
    var select = el('select', { cls: 'f-select', attrs: { 'data-erp-reason': 'code', 'aria-label': '바꾸는 까닭' } });
    select.appendChild(el('option', { text: '까닭을 골라 주세요', attrs: { value: '' } }));
    (cr.codes || []).forEach(function (c) { select.appendChild(el('option', { text: c.label, attrs: { value: c.value } })); });
    var note = el('input', { cls: 'f-input', attrs: { type: 'text', maxlength: 200, 'data-erp-reason': 'note', 'aria-label': '까닭 메모' } });
    return block('바꾸는 까닭(변경 기록에 남아요)', [select, note]);
  }

  /** 옆 창 내용 — d 는 GET /proposals/<번호> 답, ctx = {rejectCodes, today, phone}. */
  function build(d, ctx) {
    var node = el('div', { cls: 'f-col fb-erp-aside', attrs: { 'data-erp-aside': d.id } });
    node.appendChild(head(d));
    var body = el('div', { cls: 'f-aside-body', children: [title(d, ctx.today)] });
    if (d.reason) body.appendChild(block('이유', [el('p', { text: d.reason })]));
    if ((d.evidence || []).length) {
      body.appendChild(block('근거', [el('div', { cls: 'f-row f-gap4', children: d.evidence.map(function (e) { return kit().chip(e); }) })]));
    }
    if (d.base_changed) body.appendChild(el('p', { cls: 'f-small fb-erp-warn', text: kit().BASE_CHANGED }));
    body.appendChild(block('바뀌는 칸', [changes(d)]));
    if ((d.steps || []).length) body.appendChild(steps(d));
    body.appendChild(rate(d));
    body.appendChild(decide(d, ctx));
    node.appendChild(body);
    refresh(node, d);
    return node;
  }

  function decide(d, ctx) {
    var col = el('div', { cls: 'f-col' });
    var phoneBlocked = ctx.phone && !kit().phoneOk(d);
    var needs = missingParams(d, null).length > 0;
    if (d.mode === 'run' && !phoneBlocked) col.appendChild(form(d, ctx.today, needs));
    var reason = d.mode === 'run' && !phoneBlocked ? reasonBox(d) : null;
    if (reason) col.appendChild(reason);
    col.appendChild(el('p', { cls: 'f-help', attrs: { 'data-erp-missing': '1' } }));
    var row = el('div', { cls: 'f-row' });
    if (phoneBlocked) {
      row.appendChild(el('p', { cls: 'f-help', text: '이 제안은 PC 에서 승인해요.' }));
    } else {
      var main = kit().decideNode(d, '');
      if (main) row.appendChild(main);
      if (d.mode === 'run' && (d.params || []).length) row.appendChild(kit().button('고쳐서 승인', 'edit', '', 'edit'));
    }
    row.appendChild(kit().button('나중에', 'snooze', 'f-btn-minimal', 'time'));
    col.appendChild(row);
    col.appendChild(el('span', { cls: 'f-h6 fb-erp-reject-title', text: '거절 — 까닭 하나 누르면 끝' }));
    col.appendChild(kit().rejectBox(ctx.rejectCodes));
    col.appendChild(el('span', { cls: 'f-help', text: '거절 까닭은 ' + (d.agent_label || 'AI') + ' 가 다음 제안에 배워요. 같은 제안이 다시 오지 않아요.' }));
    col.appendChild(kit().statusLine());
    return col;
  }

  /** 칸 하나의 지금 값(꼴대로). node 가 없으면 제안 값. */
  function valueOf(node, p) {
    var field = node ? node.querySelector('[data-erp-param="' + p.name + '"]') : null;
    if (!field) return p.value;
    if (p.kind === 'users') {
      return Array.prototype.slice.call(field.querySelectorAll('input')).filter(function (b) { return b.checked; })
        .map(function (b) { return Number(b.getAttribute('value')); });
    }
    if (p.kind === 'flag') return !!field.checked;
    return String(field.value || '').trim();
  }

  function missingParams(d, node) {
    return (d.params || []).filter(function (p) { return required(p) && isEmpty(valueOf(node, p)); });
  }

  /** 견주기용 값 — 꼴마다 같은 모양(켜고 끄기는 참 · 거짓, 사람은 번호 글 목록, 그 밖은 글). */
  function same(p, value) {
    if (p.kind === 'flag') return String(!!value);
    if (p.kind === 'users') return (Array.isArray(value) ? value : []).map(String).sort().join(',');
    return value === null || value === undefined ? '' : String(value);
  }

  /** 고친 값만 — 처음 값과 다른 칸. */
  function edits(node, d) {
    var out = {};
    (d.params || []).forEach(function (p) {
      var now = valueOf(node, p);
      if (same(p, now) !== same(p, p.value)) out[p.name] = now;
    });
    return out;
  }

  function reason(node) {
    var code = node.querySelector('[data-erp-reason="code"]');
    var note = node.querySelector('[data-erp-reason="note"]');
    return { code: code ? code.value : '', note: note ? note.value.trim() : '', asked: !!code };
  }

  /** 꼭 있는 값 · 까닭이 비면 [승인]을 막고 무엇이 비었는지 한 줄. */
  function refresh(node, d) {
    var gaps = missingParams(d, node).map(function (p) { return p.label; });
    var r = reason(node);
    if (r.asked && !r.code) gaps.push('바꾸는 까닭');
    Array.prototype.slice.call(node.querySelectorAll('[data-erp-act="approve"], [data-erp-act="approve-edit"]')).forEach(function (b) {
      b.disabled = gaps.length > 0;
    });
    var line = node.querySelector('[data-erp-missing]');
    if (line) line.textContent = gaps.length ? '넣어야 승인할 수 있어요: ' + gaps.join(' · ') : '';
  }

  function showForm(node) {
    var box = node.querySelector('[data-erp-form]');
    if (box) box.hidden = false;
    return box;
  }

  /** 승인하면 손님에게 나가는데 카드 칸에는 안 보이는 알림톡 줄('승인하면 차례로' — 지금 주문으로 계산한 steps) — 없으면 ''.
   *  알림톡 보내기 할 일은 카드 칸이 곧 알림톡이라 ''. 서버 정본은 views.hidden_notice(같은 머리 글로 가른다). */
  function notice(d) {
    if (String(d.field || '').indexOf(NOTICE_HEAD) === 0) return '';
    return (d.steps || []).filter(function (t) { return String(t).indexOf(NOTICE_HEAD) === 0; })[0] || '';
  }

  window.FOMS_DS_INBOX_ERP_ASIDE = { build: build, edits: edits, reason: reason, refresh: refresh, showForm: showForm,
                                     notice: notice, missing: function (d) { return missingParams(d, null).length > 0; } };
})();
