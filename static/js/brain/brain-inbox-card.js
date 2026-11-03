/**
 * 제안함 카드 그리기(HAUD master brain 설계서 7.5 화면 4 · 승인 흐름) — 카드 하나의 DOM 만 만든다(글은 textContent 만 ·
 * 인라인 스타일 없음). 결정 단추는 data-brain-act 로 표시하고 누름은 brain-inbox.js 가 받는다.
 *
 * 차례: 머리(유형 칩 · 한글 이름 · 사람/AI · 동작) → 한 줄 요약 → 기준 판 바뀜 경고 → 승인의 뜻 → 칸별 전 → 후 →
 * 사람 까닭 · 사진 먼저, AI 까닭 다음 → 근거 서랍(근거 id 만) → 비슷한 사례 · 함께 닿는 항목 → 걸린 자동 검사(문제일 때만 —
 * 설계서 7.9) → 등급 B 확인 →
 * 고쳐 넣기 칸(처음엔 숨김) → 결정 단추(휴대폰은 칸 하나 넣기 · PC 에서 볼게요만) → 같은 항목에 붙은 제안.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var review = window.FOMS_BRAIN_REVIEW;
  if (!dom || !review) return;
  var el = dom.el;

  function button(text, act, extra) {
    return el('button', { cls: 'brain-btn' + (extra ? ' ' + extra : ''), text: text,
                          attrs: { type: 'button', 'data-brain-act': act } });
  }

  /** 단추 이름은 이름 있는 액션 목록에서(7.7 — 같은 목록이 API · 도구를 낸다). */
  function label(ctx, name) {
    return review.actionLabel(ctx.actions, name);
  }

  function headOf(card, ctx) {
    var head = el('div', { cls: 'brain-icard__head' });
    var href = card.exists ? view.itemHref(ctx.itemBase, card.key) : null;
    head.appendChild(dom.typeChip(ctx.display, card.type, href));
    head.appendChild(el(href ? 'a' : 'span', { cls: 'brain-icard__name', text: card.title || card.name,
                                               attrs: { href: href } }));
    var main = card.main;
    head.appendChild(el('span', { cls: 'brain-badge ' + (main.ai ? 'brain-badge--ai' : 'brain-badge--human'),
                                  text: main.ai ? 'AI 제안' : '사람 제안' }));
    if (main.rollback_of !== null && main.rollback_of !== undefined) {
      head.appendChild(el('span', { cls: 'brain-badge', text: '되돌리기' }));
    }
    return head;
  }

  function diffTable(prop, ctx) {
    var rows = review.diffRows(prop.fields, ctx.display);
    var table = el('table', { cls: 'brain-diff' });
    table.appendChild(el('caption', { cls: 'visually-hidden', text: '칸별 지금 값과 제안 값' }));
    var head = el('tr', { children: [el('th', { text: '칸', attrs: { scope: 'col' } }),
                                     el('th', { text: '지금', attrs: { scope: 'col' } }),
                                     el('th', { text: '제안', attrs: { scope: 'col' } })] });
    table.appendChild(el('thead', { children: [head] }));
    var body = el('tbody');
    rows.forEach(function (row) {
      var after = el('td', { cls: 'brain-diff__after', text: row.after });
      if (row.proposed !== null) after.appendChild(el('span', { cls: 'brain-diff__proposed', text: '처음 제안: ' + row.proposed }));
      body.appendChild(el('tr', { children: [el('th', { text: row.label, attrs: { scope: 'row' } }),
                                             el('td', { cls: 'brain-diff__before', text: row.before }), after] }));
    });
    table.appendChild(body);
    return el('div', { cls: 'brain-table-wrap', children: [table] });
  }

  function photoChips(prop) {
    var list = el('ul', { cls: 'brain-prop__photos' });
    prop.photos.forEach(function (ref, i) {
      var href = review.evidenceHref(ref);
      list.appendChild(el('li', { children: [el(href ? 'a' : 'span', {
        cls: 'brain-chip', text: '사진 ' + (i + 1), attrs: { href: href, target: href ? '_blank' : null, rel: href ? 'noopener' : null } })] }));
    });
    return list;
  }

  function reasons(prop) {
    var box = el('div', { cls: 'brain-prop__reasons' });
    var reasonBlock = el('p', { cls: 'brain-prop__reason', children: [
      el('strong', { text: prop.ai ? 'AI가 제안한 까닭 · ' : '제안한 까닭 · ' }), el('span', { text: prop.reason }),
      el('span', { cls: 'brain-empty', text: ' — ' + prop.proposer + (prop.created_at ? ' · ' + prop.created_at : '') })] });
    if (!prop.ai) box.appendChild(reasonBlock);
    if (prop.photos.length) box.appendChild(photoChips(prop));
    if (prop.ai) box.appendChild(reasonBlock);
    var drawer = el('details', { cls: 'brain-prop__drawer' });
    drawer.appendChild(el('summary', { text: '근거 ' + prop.evidence.length + '개' }));
    var list = el('ul');
    prop.evidence.forEach(function (ref) { list.appendChild(el('li', { cls: 'brain-prop__ref', text: ref })); });
    if (!prop.evidence.length) list.appendChild(el('li', { cls: 'brain-empty', text: '적힌 근거가 없어요' }));
    drawer.appendChild(list);
    box.appendChild(drawer);
    return box;
  }

  /** 걸린 자동 검사만(통과 · 아직 안 돌림은 안 보인다 — 설계서 7.9). 걸린 것이 없으면 ``null``. */
  function gates(prop, ctx) {
    var failed = review.gateRows(prop.gates, ctx.display).filter(function (gate) { return gate.cls === 'is-fail'; });
    if (!failed.length) return null;
    var list = el('ul', { cls: 'brain-gates', attrs: { 'aria-label': '자동 검사에서 걸린 것' } });
    failed.forEach(function (gate) {
      list.appendChild(el('li', { cls: 'brain-gate ' + gate.cls, text: gate.label + ' ' + gate.text }));
    });
    return list;
  }

  function confirmBox(prop, ctx) {
    var row = (prop.fields || []).filter(function (r) { return r.field === prop.confirm.field; })[0];
    var label = (row && row.label) || (ctx.display.fields || {})[prop.confirm.field] || '바뀌는 값';
    var input = el('input', { attrs: { type: 'checkbox', 'data-brain-confirm': '1' } });
    var shown = review.valueText(prop.confirm.field, prop.confirm.value, ctx.display);  // 보이는 글만 이름으로(보내는 값은 그대로)
    return el('label', { cls: 'brain-prop__confirm', children: [input, el('span', {
      text: '중요한 값이에요 — 직접 보고 맞는지 확인했어요 · ' + label + ': ' + shown })] });
  }

  /** 고칠 칸 하나 — 자료형(속성 틀)에 맞는 입력(글 · 날짜 · 수 · 고르기 · 쉼표 목록). */
  function editInput(row) {
    var kind = row.datatype || 'text';
    var input;
    if (kind === 'enum') {
      input = el('select', { cls: 'form-select form-select-sm', attrs: { 'data-brain-edit': row.field } });
      [''].concat(row.choices || []).forEach(function (choice) {
        input.appendChild(el('option', { text: choice || '(없음)', attrs: { value: choice } }));
      });
    } else {
      var type = { date: 'date', int: 'number', number: 'number' }[kind] || (row.field === 'text' ? null : 'text');
      input = el(row.field === 'text' ? 'textarea' : 'input', {
        cls: 'form-control form-control-sm', attrs: { 'data-brain-edit': row.field, rows: row.field === 'text' ? 4 : null,
                                                      type: type, step: kind === 'number' ? 'any' : null } });
    }
    var after = row.after;
    input.value = after === null || after === undefined ? '' : (Array.isArray(after) ? after.join(', ') : String(after));
    return input;
  }

  function editBox(prop, ctx) {
    var box = el('div', { cls: 'brain-prop__edit', attrs: { 'data-brain-edit-box': '1' } });
    box.hidden = true;
    var labels = {};
    review.diffRows(prop.fields, ctx.display).forEach(function (r) { labels[r.field] = r.label; });
    prop.fields.filter(function (r) { return review.editableFields(prop).indexOf(r.field) >= 0; }).forEach(function (row) {
      box.appendChild(el('label', { cls: 'brain-propose__field', children: [
        el('span', { text: labels[row.field] + (row.unit ? '(' + row.unit + ')' : '') + ' — 고친 값' }), editInput(row)] }));
    });
    return box;
  }

  function rejectChips(ctx) {
    var row = el('div', { cls: 'brain-prop__chips', attrs: { 'data-brain-reject-box': '1', role: 'group',
                                                                 'aria-label': '거절 까닭' } });
    row.hidden = true;
    var answers = (window.FOMS_BRAIN_INBOX_QUESTION || { codes: [] }).codes;  // ③ 질문 답 까닭은 보통 거절 칩에 안 보인다
    review.actionChoices(ctx.actions, 'reject', 'code').filter(function (choice) {
      return answers.indexOf(choice.value) < 0;
    }).forEach(function (choice) {
      var chip = button(choice.label, 'reject-code', 'brain-chip-btn');
      chip.setAttribute('data-reject-code', choice.value);
      row.appendChild(chip);
    });
    return row;
  }

  function actions(prop, ctx, phone) {
    var allowed = review.actionsFor(prop, phone);
    var bar = el('div', { cls: 'brain-prop__actions' });
    if (allowed.apply) bar.appendChild(button(label(ctx, 'apply'), 'apply', 'brain-btn--primary'));
    if (allowed.edit) bar.appendChild(button(label(ctx, 'edit_apply'), 'edit'));
    if (allowed.edit) {
      var save = button('고친 값으로 승인', 'edit-apply', 'brain-btn--primary');
      save.hidden = true;
      bar.appendChild(save);
    }
    if (allowed.reject) bar.appendChild(button(label(ctx, 'reject'), 'reject'));
    if (allowed.later) bar.appendChild(button(phone ? 'PC 에서 볼게요' : '나중에', 'later'));
    var wrap = el('div', { children: [bar] });
    if (allowed.reject) wrap.appendChild(rejectChips(ctx));
    if (allowed.hint) wrap.appendChild(el('p', { cls: 'brain-prop__hint', text: '이 제안은 PC 에서 결정해요(칸이 여럿이거나 새 항목 · 은퇴 · 지우기 · 링크).' }));
    return wrap;
  }

  /** 계산기 금액 한 줄(값을 볼 수 없는 사람에게는 이름만). */
  function priceLine(price) {
    if (price.exists === false) return '금액: 견적 계산기에서 이 옵션을 찾지 못했어요 — 계산기 이름을 확인해 주세요.';
    var value = price.hidden ? '(금액은 가격 재량이 있는 사람만 보여요)' : '지금 ' + (price.value || '값 없음');
    return "금액: 견적 계산기 '" + (price.label || '') + "' — " + value;
  }

  /** ② 문장 카드 — AI와 직원이 알게 될 글 · 금액 줄 · 제안한 까닭(시안 화면 3). */
  function sentenceBlock(prop) {
    var box = el('div', { cls: 'brain-prop__reasons' });
    if (prop.sentence) {
      box.appendChild(el('p', { cls: 'brain-prop__meaning', text: 'AI와 직원이 이렇게 알게 돼요' }));
      box.appendChild(el('p', { cls: 'brain-icard__summary', text: '“' + prop.sentence + '”' }));
    }
    var prices = prop.prices || [];
    prices.forEach(function (price) { box.appendChild(el('p', { cls: 'brain-prop__fact', text: priceLine(price) })); });
    if (prices.length) box.appendChild(el('p', { cls: 'brain-empty', text: '계산기 값을 바꾸면 이 지식도 같이 바뀌어요.' }));
    box.appendChild(el('p', { cls: 'brain-prop__reason', children: [el('strong', { text: '제안한 까닭 · ' }),
                                                                     el('span', { text: prop.reason })] }));
    return box;
  }

  /** 카드 밑 한 줄 — 볼 수 있는 사람 · 자동 검사. */
  function footer(prop) {
    var failed = (prop.gates || []).filter(function (g) { return g.value === 'fail'; }).length;
    return (prop.visible_to ? '볼 수 있는 사람: ' + prop.visible_to + ' · ' : '') +
      '자동 검사: ' + (failed ? '걸린 것 ' + failed + '개(위에 적었어요)' : '문제 없음');
  }

  /** 제안 하나(카드의 첫 제안 또는 붙은 제안). */
  function proposal(prop, card, ctx, phone, primary) {
    var box = el('div', { cls: 'brain-prop' + (primary ? '' : ' brain-prop--attached'),
                          attrs: { 'data-change-id': prop.id, 'data-shown-at': Math.round(window.performance.now()) } });
    if (!primary) box.appendChild(el('p', { cls: 'brain-prop__sub', text: review.summary({ main: prop, type: card.type, name: card.name }, ctx.display) }));
    var warn = review.conflictText(prop);
    if (warn) box.appendChild(el('p', { cls: 'brain-prop__warn', text: warn, attrs: { role: 'note' } }));
    var sentence = primary && card.bin === 'content';  // ② 문장 카드 — 칸 표 · 근거는 '자세히 보기' 안(설계서 7.9)
    var detail = sentence ? el('details', { cls: 'brain-prop__drawer' }) : box;
    if (sentence) {
      box.appendChild(sentenceBlock(prop));
      detail.appendChild(el('summary', { text: '자세히 보기 (바뀌는 칸 · 근거 · 수정 기록)' }));
    }
    if (primary) detail.appendChild(el('p', { cls: 'brain-prop__meaning', text: '승인의 뜻 — ' + prop.meaning }));
    detail.appendChild(diffTable(prop, ctx));
    detail.appendChild(reasons(prop));
    if (primary) {
      detail.appendChild(el('p', { cls: 'brain-prop__fact', text: review.similarText(card.similar) }));
      detail.appendChild(el('p', { cls: 'brain-prop__fact', text: review.touchText(card.touches, card.copies, ctx.display) }));
    }
    if (sentence) box.appendChild(detail);
    var failed = gates(prop, ctx);
    if (failed) box.appendChild(failed);
    if (prop.confirm && !(prop.base && prop.base.changed)) box.appendChild(confirmBox(prop, ctx));
    if (!phone) box.appendChild(editBox(prop, ctx));
    box.appendChild(actions(prop, ctx, phone));
    if (sentence) box.appendChild(el('p', { cls: 'brain-empty', text: footer(prop) }));
    box.appendChild(el('p', { cls: 'brain-status-line', attrs: { 'data-brain-prop-status': '1', role: 'status', 'aria-live': 'polite' } }));
    return box;
  }

  /** 카드 하나 — li. */
  function build(card, ctx, phone) {
    var li = el('li', { cls: 'brain-icard brain-type--' + card.type, attrs: { 'data-card-id': card.id } });
    li.appendChild(headOf(card, ctx));
    li.appendChild(el('p', { cls: 'brain-icard__summary', text: review.summary(card, ctx.display) }));
    li.appendChild(proposal(card.main, card, ctx, phone, true));
    if (card.attached.length) {
      var more = el('details', { cls: 'brain-icard__attached' });
      more.appendChild(el('summary', { text: '같은 항목에 붙은 제안 ' + card.attached.length + '건' }));
      card.attached.forEach(function (prop) { more.appendChild(proposal(prop, card, ctx, phone, false)); });
      li.appendChild(more);
    }
    return li;
  }

  window.FOMS_BRAIN_INBOX_CARD = { build: build };
})();
