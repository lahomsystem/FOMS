/**
 * 새 승인 대기 화면 — PC 지식 고침 카드 하나(설계서 2026-11-14-foms-graft 5.4 · 판 ⑥ · 옛 brain-inbox-card.js 와 같은 차례).
 *
 * 머리 → 승인의 뜻 → 기준 판 바뀜 경고 → (② 문장 · 금액) 바뀌는 칸 → 이유 → 자세히 보기 → 걸린 자동 검사 → 등급 B 확인 →
 * 고칠 칸(처음엔 숨김) → 결정 단추(승인 · 고쳐서 승인 · 거절 · 나중에 — 판정은 review.actionsFor) → 거절 까닭 칩(처음엔
 * 숨김 · ③ 질문 답 까닭은 뺀다) → 알림 줄 → 같은 지식에 붙은 제안. 단추 이름은 이름 있는 액션 목록에서(review.actionLabel).
 * 글은 textContent 만 · 인라인 스타일 없음. 누름은 ds-inbox-act.js 가 받는다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var review = window.FOMS_BRAIN_REVIEW;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !review || !kit) return;
  var el = dom.el;
  /** ③ 질문 카드의 답 까닭 — 보통 거절 칩에는 안 보인다(ds-inbox-question.js 와 같은 값). */
  var ANSWER_CODES = ['knowledge_right', 'outside_right', 'both_right'];

  /** 고칠 칸 하나 — 자료형(속성 틀)에 맞는 입력(글 · 날짜 · 수 · 고르기 · 쉼표 목록). 고르기 글은 이름표(값은 그대로). */
  function editInput(row, display) {
    var kind = row.datatype || 'text';
    var input;
    if (kind === 'enum') {
      input = el('select', { cls: 'f-select', attrs: { 'data-ds-edit': row.field } });
      [''].concat(row.choices || []).forEach(function (choice) {
        input.appendChild(el('option', { text: choice ? review.valueText(row.field, choice, display) : '(없음)',
                                         attrs: { value: choice } }));
      });
    } else {
      var type = { date: 'date', int: 'number', number: 'number' }[kind] || (row.field === 'text' ? null : 'text');
      input = el(row.field === 'text' ? 'textarea' : 'input', { cls: 'f-input', attrs: {
        'data-ds-edit': row.field, rows: row.field === 'text' ? 4 : null, type: type, step: kind === 'number' ? 'any' : null } });
    }
    var after = row.after;
    input.value = after === null || after === undefined ? '' : (Array.isArray(after) ? after.join(', ') : String(after));
    return input;
  }

  function editBox(prop, c) {
    var box = el('div', { cls: 'f-col fb-edit', attrs: { 'data-ds-edit-box': '1' } });
    box.hidden = true;
    var labels = {};
    var rows = review.editRows(prop);  // 바꾼 칸 + 바꾸지 않은 내용 칸(D177)
    review.diffRows(rows, c.display).forEach(function (r) { labels[r.field] = r.label; });
    rows.forEach(function (row) {
      box.appendChild(el('label', { cls: 'f-field', children: [
        el('span', { cls: 'f-label', text: labels[row.field] + (row.unit ? '(' + row.unit + ')' : '') + ' — 고친 값' }),
        editInput(row, c.display)] }));
    });
    return box;
  }

  function rejectChips(c) {
    var box = el('div', { cls: 'f-col f-gap4', attrs: { 'data-ds-reject-box': '1' } });
    box.hidden = true;
    box.appendChild(el('span', { cls: 'f-h6', text: '거절 — 까닭 하나 누르면 끝' }));
    var row = el('div', { cls: 'f-row f-gap4', attrs: { role: 'group', 'aria-label': '거절 까닭' } });
    review.actionChoices(c.actions, 'reject', 'code').filter(function (choice) {
      return ANSWER_CODES.indexOf(choice.value) < 0;
    }).forEach(function (choice) {
      var chip = kit.button(choice.label, 'reject-code', 'f-btn-small f-btn-outlined');
      chip.setAttribute('data-reject-code', choice.value);
      row.appendChild(chip);
    });
    box.appendChild(row);
    return box;
  }

  /** 결정 단추 줄 — PC 판정(review.actionsFor(prop, false)). */
  function actions(prop, c) {
    var allowed = review.actionsFor(prop, false);
    var bar = el('div', { cls: 'f-actions' });
    if (allowed.apply) bar.appendChild(kit.button(review.actionLabel(c.actions, 'apply'), 'apply', 'f-btn-primary', 'tick'));
    if (allowed.edit) {
      var start = kit.button(review.actionLabel(c.actions, 'edit_apply'), 'edit', '', 'edit');
      bar.appendChild(start);
      var save = kit.button('고친 값으로 승인', 'edit-apply', 'f-btn-primary', 'tick');
      save.hidden = true;
      bar.appendChild(save);
    }
    if (allowed.reject) bar.appendChild(kit.button(review.actionLabel(c.actions, 'reject'), 'reject', 'f-btn-minimal', 'cross'));
    if (allowed.later) bar.appendChild(kit.button('나중에', 'later', 'f-btn-minimal', 'time'));
    var wrap = el('div', { cls: 'f-col', children: [bar] });
    if (allowed.reject) wrap.appendChild(rejectChips(c));
    return wrap;
  }

  /** 계산기 금액 한 줄(값을 볼 수 없는 사람에게는 이름만). */
  function priceLine(price) {
    if (price.exists === false) return '금액: 견적 계산기에서 이 옵션을 찾지 못했어요 — 계산기 이름을 확인해 주세요.';
    var value = price.hidden ? '(금액은 가격 재량이 있는 사람만 보여요)' : '지금 ' + (price.value || '값 없음');
    return "금액: 견적 계산기 '" + (price.label || '') + "' — " + value;
  }

  /** ② 문장 카드 — AI · 직원이 알게 될 글 · 금액 줄. */
  function sentenceBlock(prop) {
    var box = el('div', { cls: 'f-col f-gap4' });
    if (prop.sentence) {
      box.appendChild(el('span', { cls: 'f-h6', text: 'AI · 직원이 알게 될 내용' }));
      box.appendChild(el('p', { cls: 'f-quote', text: prop.sentence }));
    }
    var prices = prop.prices || [];
    prices.forEach(function (price) { box.appendChild(el('p', { cls: 'f-small', text: priceLine(price) })); });
    if (prices.length) box.appendChild(el('p', { cls: 'f-help', text: '계산기 값을 바꾸면 같이 바뀌어요.' }));
    return box;
  }

  /** 제안 하나(카드의 첫 제안 또는 붙은 제안). */
  function proposal(prop, card, c, primary) {
    var box = el('div', { cls: 'f-col fb-prop' + (primary ? '' : ' fb-prop--attached'),
                          attrs: { 'data-change-id': prop.id, 'data-shown-at': Math.round(window.performance.now()) } });
    if (!primary) box.appendChild(el('p', { cls: 'f-strong', text: review.summary({ main: prop, type: card.type, name: card.name }, c.display) }));
    if (primary && prop.meaning) box.appendChild(el('p', { cls: 'f-small f-muted', text: prop.meaning }));
    var warn = review.conflictText(prop);
    if (warn) {
      box.appendChild(el('div', { cls: 'f-callout f-callout-warning', attrs: { role: 'note' },
                                  children: [kit.icon('warning-sign'), el('span', { text: warn })] }));
    }
    var sentence = primary && card.bin === 'content';  // ② 문장 카드
    var names = primary && (card.bin === 'names' || card.bin === 'mark');  // 묶음 줄이 이유를 대신한다
    box.appendChild(sentence ? sentenceBlock(prop) : kit.diffTable(prop, c));
    if (!names) box.appendChild(kit.reasonLine(prop));
    var detail = el('details', { cls: 'fb-drawer' });
    detail.appendChild(el('summary', { cls: 'f-small', text: '자세히 보기' }));
    if (sentence) detail.appendChild(kit.diffTable(prop, c));
    detail.appendChild(kit.detailBits(prop, card, c, primary));
    box.appendChild(detail);
    var failed = kit.gates(prop, c);
    if (failed) box.appendChild(failed);
    if (prop.confirm && !(prop.base && prop.base.changed)) box.appendChild(kit.confirmBox(prop, c));
    box.appendChild(editBox(prop, c));
    box.appendChild(actions(prop, c));
    box.appendChild(kit.statusLine());
    return box;
  }

  /** 카드 하나 — li(data-card-id). */
  function build(card, c) {
    var li = el('li', { cls: 'f-card f-card-compact f-col fb-icard', attrs: { 'data-card-id': card.id } });
    li.appendChild(kit.headOf(card, c));
    li.appendChild(proposal(card.main, card, c, true));
    if (card.attached.length) {
      var more = el('details', { cls: 'fb-drawer' });
      more.appendChild(el('summary', { cls: 'f-small', text: '같은 지식에 붙은 제안 ' + card.attached.length + '개' }));
      card.attached.forEach(function (prop) { more.appendChild(proposal(prop, card, c, false)); });
      li.appendChild(more);
    }
    return li;
  }

  window.FOMS_DS_INBOX_CARD = { build: build, rejectChips: rejectChips };
})();
