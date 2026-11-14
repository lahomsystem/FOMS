/**
 * 승인 대기 AI 할 일 제안 카드 부품(T8 · 판 ⑥ · ⑫ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.6 · 5.5) —
 * window.FOMS_DS_INBOX_ERP_CARD.
 *
 * - PC 카드: AI 직원 표시 · 제목 · 때 · 근거 칩 · 칸 · 전 → 후 · [승인] · [자세히] · [거절](누르면 까닭 칩 한 줄).
 *   mode 'link' 이면 [승인] 대신 [주문에서 처리](주문 화면으로). 실패한 제안은 [다시], 제안 뒤 주문이 바뀌었으면 알림 한 줄.
 * - 폰 카드: 'ERP 할 일' 꼬리표 · AI 직원 · 때 · 제목 · 전 → 후 · 근거 칩 하나 · [승인](phone_ok 인 run 할 일만 — 나머지는
 *   'PC 에서 볼 것'). 제목을 누르면 옆 창(폰에서는 화면을 덮는다)이 열린다.
 * 결정 단추는 data-erp-act 로 표시하고 누름은 ds-inbox-erp.js 가 받는다. 글은 textContent 만 · 인라인 스타일 없음.
 * brain-dom.js 는 이 파일보다 늦게 실리므로(문서 차례) 요소 도우미는 부를 때 찾는다.
 */
(function () {
  'use strict';

  var EVIDENCE_ICONS = { brain: 'lightbulb', order: 'cube', cs_turn: 'chat', visit: 'calendar' };
  var AGENT_ICONS = { cs: 'chat', schedule: 'calendar', ops: 'predictive-analysis' };
  var BASE_CHANGED = '제안 뒤 주문이 바뀌었어요 — 다시 봐 주세요';
  var FAILED_LINE = '지난번에 실행하지 못했어요 — 다시 승인할 수 있어요';

  function el(tag, opts) {
    return window.FOMS_BRAIN_DOM.el(tag, opts);
  }

  function icon(name, extra) {
    return el('span', { cls: 'f-i i-' + name + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  /** 단추 — act 는 data-erp-act, cls 는 더할 class, iconName 은 앞 아이콘. */
  function button(text, act, cls, iconName) {
    var b = el('button', { cls: 'f-btn' + (cls ? ' ' + cls : ''), attrs: { type: 'button', 'data-erp-act': act || null } });
    if (iconName) b.appendChild(icon(iconName));
    b.appendChild(document.createTextNode(text));
    return b;
  }

  /** AI 직원 표시(아이콘 + 이름). */
  function mark(card) {
    var node = el('span', { cls: 'f-ai-mark' });
    node.appendChild(icon(AGENT_ICONS[card.agent] || 'predictive-analysis'));
    node.appendChild(document.createTextNode(card.agent_label || 'AI'));
    return node;
  }

  /** 근거 칩 하나 — 주소가 있으면 링크. */
  function chip(item, extra) {
    var node = el(item.href ? 'a' : 'span', { cls: 'f-chip' + (extra ? ' ' + extra : ''), attrs: { href: item.href || null } });
    node.appendChild(icon(EVIDENCE_ICONS[item.kind] || 'document'));
    node.appendChild(document.createTextNode(item.label || ''));
    return node;
  }

  /** 'YYYY-MM-DD HH:MM' → 오늘이면 시각, 아니면 'MM-DD'. */
  function whenText(createdAt, today) {
    var m = /^(\d{4}-(\d{2}-\d{2})) (\d{2}:\d{2})/.exec(String(createdAt || ''));
    if (!m) return '';
    return m[1] === today ? m[3] : m[2];
  }

  function todayText() {
    var d = new Date();
    var two = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate());
  }

  /** 폰에서 [승인] 할 수 있나 — phone_ok 인 run 할 일만(설계서 5.5). */
  function phoneOk(card) {
    return !!card.phone_ok && card.mode === 'run';
  }

  /** 거절 까닭 칩 한 줄 — codes 는 [{value, label}]. */
  function rejectBox(codes) {
    var box = el('div', { cls: 'f-row f-gap4', attrs: { role: 'group', 'aria-label': '거절 까닭' } });
    (codes || []).forEach(function (code) {
      var b = button(code.label, 'reject', 'f-btn-small f-btn-outlined');
      b.setAttribute('data-erp-code', code.value);
      box.appendChild(b);
    });
    return box;
  }

  function statusLine() {
    return el('p', { cls: 'fb-status', attrs: { role: 'status', 'aria-live': 'polite', 'data-erp-card-status': '1' } });
  }

  /** 승인 단추 자리 — run 이면 [승인]([다시]), link 면 [주문에서 처리], 사람만이면 없음. */
  function decideNode(card, cls) {
    if (card.mode === 'link') {
      var go = el('a', { cls: 'f-btn f-btn-primary' + (cls ? ' ' + cls : ''), attrs: { href: card.order_href || null } });
      go.appendChild(icon('share'));
      go.appendChild(document.createTextNode('주문에서 처리'));
      return go;
    }
    if (card.mode !== 'run') return null;
    return button(card.status === 'failed' ? '다시' : '승인', 'approve', 'f-btn-primary' + (cls ? ' ' + cls : ''), 'tick');
  }

  function notes(card) {
    var out = [];
    if (card.base_changed) out.push(el('p', { cls: 'f-small fb-erp-warn', text: BASE_CHANGED }));
    if (card.status === 'failed') out.push(el('p', { cls: 'f-small fb-erp-warn', text: FAILED_LINE }));
    return out;
  }

  /** PC 카드 — li.f-ai-card(판 ⑥ 'AI 할 일 제안' 한 장). ctx = {rejectCodes, today, selected}. */
  function pcCard(card, ctx) {
    var li = el('li', { cls: 'f-ai-card is-proposal fb-erp-card' + (ctx.selected === card.id ? ' is-selected' : ''),
                        attrs: { 'data-erp-card': card.id } });
    li.appendChild(el('div', { cls: 'f-row', children: [mark(card), el('span', { cls: 'f-strong', text: card.title }),
      el('span', { cls: 'f-small f-muted f-push f-num', text: whenText(card.created_at, ctx.today) })] }));
    if ((card.evidence || []).length) {
      var row = el('div', { cls: 'f-row f-gap4', children: [el('span', { cls: 'f-small f-muted fb-erp-why', text: '근거' })] });
      card.evidence.forEach(function (item) { row.appendChild(chip(item)); });
      li.appendChild(row);
    }
    notes(card).forEach(function (n) { li.appendChild(n); });
    var acts = el('span', { cls: 'f-row f-push', children: [decideNode(card, 'f-btn-small'),
      button('자세히', 'open', 'f-btn-small'), button('거절', 'reject-open', 'f-btn-small f-btn-minimal')] });
    li.appendChild(el('div', { cls: 'f-row', children: [el('span', { cls: 'f-small f-muted', text: card.field }),
      el('span', { cls: 'f-muted', text: card.before }), icon('arrow-right', 'f-i-muted'),
      el('span', { cls: 'f-sr', text: '에서' }), el('span', { cls: 'f-strong', text: card.after }), acts] }));
    var reject = rejectBox(ctx.rejectCodes);
    reject.setAttribute('data-erp-reject-box', '1');
    reject.hidden = true;
    li.appendChild(reject);
    li.appendChild(statusLine());
    return li;
  }

  /** 폰 카드 — 승인 대기 폰 목록([data-ds-phone-list])에 넣는 한 장(판 ⑫). */
  function phoneCard(card, ctx) {
    var li = el('li', { cls: 'f-card f-card-e1 f-col fb-phone-card fb-erp-phone',
                        attrs: { 'data-erp-card': card.id, 'data-ds-inbox-erp-card': '1' } });
    var tag = el('span', { cls: 'f-tag f-tag-minimal f-tag-primary', children: [icon('flash'), el('span', { text: 'ERP 할 일' })] });
    li.appendChild(el('div', { cls: 'f-row f-between', children: [el('div', { cls: 'f-row f-gap4', children: [tag, mark(card)] }),
      el('span', { cls: 'f-small f-muted f-num', text: whenText(card.created_at, ctx.today) })] }));
    li.appendChild(el('button', { cls: 'fb-phone-card__title f-strong', text: card.title,
                                  attrs: { type: 'button', 'data-erp-act': 'open' } }));
    li.appendChild(el('div', { cls: 'f-row-nw f-small fb-phone-change', children: [
      el('span', { cls: 'f-muted f-ellipsis', text: card.before }), icon('arrow-right', 'f-i-muted'),
      el('span', { cls: 'f-sr', text: '에서' }), el('span', { cls: 'f-strong f-ellipsis', text: card.after })] }));
    notes(card).forEach(function (n) { li.appendChild(n); });
    var foot = el('div', { cls: 'f-row-nw' });
    if ((card.evidence || []).length) foot.appendChild(chip(card.evidence[0], 'f-ellipsis'));
    var decide = phoneOk(card) ? decideNode(card, 'f-push fb-phone-approve') : null;
    foot.appendChild(decide || el('span', { cls: 'f-small f-muted f-push', text: 'PC 에서 볼 것' }));
    li.appendChild(foot);
    li.appendChild(statusLine());
    return li;
  }

  window.FOMS_DS_INBOX_ERP_CARD = { pcCard: pcCard, phoneCard: phoneCard, phoneOk: phoneOk, rejectBox: rejectBox,
                                    button: button, icon: icon, mark: mark, chip: chip, whenText: whenText,
                                    todayText: todayText, statusLine: statusLine, decideNode: decideNode,
                                    BASE_CHANGED: BASE_CHANGED };
})();
