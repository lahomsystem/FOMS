/**
 * 새 승인 대기 화면 공용 부품(설계서 2026-11-14-foms-graft 5.3 · 5.4 · 판 ⑥ · ⑫) — FOMS_DS_INBOX_KIT.
 *
 * 화면 값(뿌리 [data-ds-inbox] 의 data-* 를 한 번만 읽음) · 아이콘 · 단추 · 알림 줄 · 카드 조각(머리 · 바뀌는 칸 표 · 이유 ·
 * 자세히 보기 · 걸린 자동 검사 · 등급 B 확인 칸). 옛 brain-inbox-card.js 와 같은 차례 · 같은 판정(brain-review-view.js)을
 * 디자인 시스템 class(.f-* · .fb-*)로 새로 그린다(옛 DOM 스크립트는 싣지 않는다). 글은 textContent 만 · 인라인 스타일 없음.
 * 결정 단추는 data-ds-act 로 표시하고 누름은 ds-inbox-act.js 가 받는다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var review = window.FOMS_BRAIN_REVIEW;
  var iv = window.FOMS_DS_INBOX_VIEW;
  if (!dom || !review || !iv) return;
  var el = dom.el;
  var memo = null;

  /** 화면 값(한 번만 읽는다) — 뿌리 [data-ds-inbox] 의 data-*. */
  function ctx() {
    if (memo) return memo;
    var root = document.querySelector('[data-ds-inbox]');
    if (!root) return null;
    var attr = function (name) { return root.getAttribute(name) || ''; };
    memo = { root: root, view: attr('data-ds-inbox-view') || 'inbox', isAdmin: attr('data-is-admin') === '1',
             display: dom.safeJsonParse(attr('data-display'), {}), actions: dom.safeJsonParse(attr('data-actions'), []),
             wideBins: attr('data-wide-bins').split(' ').filter(Boolean),  // ''.split(' ') = [''] 함정(F27)
             urls: { inbox: attr('data-inbox-url'), proposals: attr('data-proposals-url'), bulk: attr('data-bulk-url'),
                     recheck: attr('data-recheck-url'), recheckConfirm: attr('data-recheck-confirm-url'),
                     releases: attr('data-releases-url'), page: attr('data-page-url'), itemBase: attr('data-item-base') } };
    return memo;
  }

  function icon(name, extra) {
    return el('span', { cls: 'f-i i-' + name + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  /** 단추 — cls 는 더할 class, act 는 data-ds-act, iconName 은 앞 아이콘. */
  function button(text, act, cls, iconName) {
    var b = el('button', { cls: 'f-btn' + (cls ? ' ' + cls : ''), attrs: { type: 'button', 'data-ds-act': act || null } });
    if (iconName) b.appendChild(icon(iconName));
    b.appendChild(document.createTextNode(text));
    return b;
  }

  function statusLine(attr) {
    var attrs = { role: 'status', 'aria-live': 'polite' };
    attrs[attr || 'data-ds-prop-status'] = '1';
    return el('p', { cls: 'fb-status', attrs: attrs });
  }

  function typeTag(ctxv, card, href) {
    var node = el(href ? 'a' : 'span', { cls: 'f-type', attrs: { href: href } });
    node.appendChild(icon('lightbulb'));
    node.appendChild(document.createTextNode(iv.typeLabel(ctxv.display, card.type)));
    return node;
  }

  function headOf(card, c) {
    var head = el('div', { cls: 'f-row f-gap4' });
    var href = card.exists ? view.itemHref(c.urls.itemBase, card.key) : null;
    head.appendChild(typeTag(c, card, href));
    head.appendChild(el(href ? 'a' : 'span', { cls: 'f-strong', text: card.title || card.name, attrs: { href: href } }));
    if (card.main.ai) head.appendChild(el('span', { cls: 'f-ai-mark', text: 'AI 제안' }));
    if (card.main.rollback_of !== null && card.main.rollback_of !== undefined) {
      head.appendChild(el('span', { cls: 'f-tag f-tag-minimal', text: '되돌리기' }));
    }
    return head;
  }

  function isEmpty(value) {
    return value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length) ||
      (typeof value === 'object' && !Array.isArray(value) && !Object.keys(value).length);
  }

  /** 사람이 볼 필요 없는 칸 — 근거 종류 · 위치 · 세부 칸, 새로 만들 때의 기본값 칸(옛 카드와 같음). */
  var MACHINE_FIELDS = ['evidence_kind', 'evidence_ref', 'payload'];
  var CREATE_DEFAULTS = ['status', 'visibility', 'checked_at', 'confidence'];

  function shownFields(prop) {
    return (prop.fields || []).filter(function (row) {
      return MACHINE_FIELDS.indexOf(row.field) < 0 && !(prop.op === 'create' && CREATE_DEFAULTS.indexOf(row.field) >= 0);
    });
  }

  /** 바뀌는 칸 표 — 지금 값이 모두 비었으면 '지금' 칸을 뺀다. */
  function diffTable(prop, c) {
    var fields = shownFields(prop);
    var rows = review.diffRows(fields, c.display);
    var withBefore = fields.some(function (row) { return !isEmpty(row.before); });
    var table = el('table', { cls: 'f-table f-table-compact fb-diff' });
    table.appendChild(el('caption', { cls: 'f-sr', text: '바뀌는 칸' }));
    var titles = withBefore ? ['칸', '지금', '승인하면'] : ['칸', '내용'];
    table.appendChild(el('thead', { children: [el('tr', { children: titles.map(function (t) {
      return el('th', { text: t, attrs: { scope: 'col' } });
    }) })] }));
    var body = el('tbody');
    rows.forEach(function (row) {
      var after = el('td', { cls: 'f-strong fb-diff__after', text: row.after });
      if (row.proposed !== null) after.appendChild(el('span', { cls: 'f-small f-muted fb-diff__was', text: '처음 제안: ' + row.proposed }));
      var cells = [el('th', { cls: 'f-muted', text: row.label, attrs: { scope: 'row' } })];
      if (withBefore) cells.push(el('td', { cls: 'f-muted', text: row.before }));
      cells.push(after);
      body.appendChild(el('tr', { children: cells }));
    });
    table.appendChild(body);
    return el('div', { cls: 'f-section fb-diff-wrap', children: [table] });
  }

  /** 이유 글 — 끝의 기록용 꼬리('(… 결정 D…)')는 화면에서 뺀다(데이터에는 남음). */
  function reasonText(prop) {
    return String(prop.reason || '').replace(/^자료 계획 — /, '')
      .replace(/\s*\((?:[^()]*결정[^()]*|D\d+(?:\s*·\s*D\d+)*)\)\s*$/, '');
  }

  function reasonLine(prop) {
    return el('p', { children: [el('span', { cls: 'f-strong', text: prop.ai ? 'AI 가 낸 이유 · ' : '이유 · ' }),
                                 el('span', { text: reasonText(prop) })] });
  }

  /** 사람이 읽을 근거만 — 'xxx:' 머리 근거 자리와 '…@v3' 판은 기계 근거라 안 보인다(바깥 https:// 는 보인다). */
  var MACHINE_REF = /^[a-z][a-z0-9_]*:(?!\/\/)|@v\d+$/;

  function photoChips(prop) {
    var row = el('div', { cls: 'f-row f-gap4' });
    prop.photos.forEach(function (ref, i) {
      var href = review.evidenceHref(ref);
      var chip = el(href ? 'a' : 'span', { cls: 'f-chip', attrs: { href: href, target: href ? '_blank' : null,
                                                                    rel: href ? 'noopener' : null } });
      chip.appendChild(icon('camera'));
      chip.appendChild(document.createTextNode('사진 ' + (i + 1)));
      row.appendChild(chip);
    });
    return row;
  }

  /** '자세히 보기' 안 — 사진 · 사람 근거 · 비슷한 사례 · 함께 닿는 지식(있을 때만) · 누가 언제. */
  function detailBits(prop, card, c, primary) {
    var box = el('div', { cls: 'f-col f-gap4' });
    if (prop.photos.length) box.appendChild(photoChips(prop));
    var refs = prop.evidence.filter(function (ref) { return !MACHINE_REF.test(ref); });
    if (refs.length) {
      var list = el('ul', { cls: 'f-col f-gap4 f-small' });
      refs.forEach(function (ref) { list.appendChild(el('li', { text: ref })); });
      box.appendChild(list);
    }
    if (primary && card.similar && card.similar.count) box.appendChild(el('p', { cls: 'f-small', text: review.similarText(card.similar) }));
    if (primary && card.touches && card.touches.total) {
      box.appendChild(el('p', { cls: 'f-small', text: review.touchText(card.touches, card.copies, c.display) }));
    }
    box.appendChild(el('p', { cls: 'f-small f-muted', text: [prop.proposer, prop.created_at,
      prop.visible_to ? '볼 수 있는 사람 ' + prop.visible_to : ''].filter(Boolean).join(' · ') }));
    return box;
  }

  /** 걸린 자동 검사만(통과 · 아직은 안 보인다). 없으면 null. */
  function gates(prop, c) {
    var failed = review.gateRows(prop.gates, c.display).filter(function (gate) { return gate.cls === 'is-fail'; });
    if (!failed.length) return null;
    var row = el('div', { cls: 'f-row f-gap4', attrs: { role: 'list', 'aria-label': '자동 검사에서 걸린 것' } });
    failed.forEach(function (gate) {
      row.appendChild(el('span', { cls: 'f-tag f-tag-minimal f-tag-danger', text: gate.label + ' ' + gate.text,
                                   attrs: { role: 'listitem' } }));
    });
    return row;
  }

  /** 등급 B 확인 칸 — 글 칸 · 40자 넘는 값은 값을 다시 붙이지 않는다(바로 위 표에 있다). */
  function confirmBox(prop, c) {
    var row = (prop.fields || []).filter(function (r) { return r.field === prop.confirm.field; })[0];
    var label = (row && row.label) || (c.display.fields || {})[prop.confirm.field] || '바뀌는 값';
    var shown = review.valueText(prop.confirm.field, prop.confirm.value, c.display);
    var isLong = prop.confirm.field === 'text' || String(shown).length > 40;
    return el('label', { cls: 'f-check fb-confirm', children: [el('input', { attrs: { type: 'checkbox', 'data-ds-confirm': '1' } }),
      el('span', { text: label + ' 확인했어요' + (isLong ? '' : ': ' + shown) })] });
  }

  window.FOMS_DS_INBOX_KIT = { ctx: ctx, icon: icon, button: button, statusLine: statusLine, typeTag: typeTag,
                               headOf: headOf, diffTable: diffTable, reasonLine: reasonLine, reasonText: reasonText,
                               detailBits: detailBits, gates: gates, confirmBox: confirmBox, MACHINE_REF: MACHINE_REF };
})();
