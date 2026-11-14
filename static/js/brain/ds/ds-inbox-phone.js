/**
 * 새 승인 대기 화면 — 폰(640px 아래 · 판 ⑫ · 설계서 2026-11-14-foms-graft 5.5).
 *
 * - '폰에서 승인 n': 칸 하나 고침 카드(지금 규칙 — review.actionsFor(prop, true).apply)와 ③ 질문 카드. 목록 [data-ds-phone-list] 은
 *   T8(AI 할 일 제안)도 카드를 넣는다 — 이 파일은 제 카드([data-ds-inbox-own])만 지우고 다시 넣는다. 수 · 'n개 더 보기'(처음
 *   세 장)는 목록의 모든 카드로 센다(MutationObserver — 남이 넣어도 맞춘다).
 * - 카드를 누르면 이유 · 근거 · 거절 까닭 칩 · 'PC 에서 볼게요'가 열린다(설계서 5.5 — 거절은 PC 와 같은 판정 actionsFor(prop, false)).
 * - 'PC 에서 볼 것 n': 폰에서 승인할 수 없는 카드(F05 — 처음부터 접힘)와 'PC 에서 볼게요'로 접은 카드. 누르면 펼친다.
 * 등급 B 확인 칸은 폰 카드에도 있다(서버가 다시 본다). 글은 textContent 만 · 인라인 스타일 없음.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var review = window.FOMS_BRAIN_REVIEW;
  var iv = window.FOMS_DS_INBOX_VIEW;
  var kit = window.FOMS_DS_INBOX_KIT;
  var cardKit = window.FOMS_DS_INBOX_CARD;
  var questionKit = window.FOMS_DS_INBOX_QUESTION;
  if (!dom || !review || !iv || !kit || !cardKit) return;
  var el = dom.el;
  var FIRST = 3;
  var PC_HINT = '이 제안은 PC 에서 결정해요(칸이 여럿이거나 새 지식 · 은퇴 · 지우기 · 연결).';
  var expanded = false;

  function today() {
    var d = new Date();
    var two = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate());
  }

  function who(prop) {
    if (prop.ai) return el('span', { cls: 'f-ai-mark', text: prop.proposer || 'AI' });
    return el('span', { cls: 'f-row f-gap4 f-small', children: [kit.icon('person', 'f-i-muted'), el('span', { text: prop.proposer || '' })] });
  }

  function titleText(card, c) {
    var prop = card.main;
    if (prop.link) return review.summary(card, c.display);
    var rows = review.diffRows(prop.fields, c.display);
    return [iv.typeLabel(c.display, card.type), card.title || card.name, rows.length === 1 ? rows[0].label : '']
      .filter(Boolean).join(' · ');
  }

  function changeRow(prop, c) {
    var rows = review.diffRows(prop.fields, c.display);
    if (rows.length !== 1) return null;
    return el('div', { cls: 'f-row-nw f-small fb-phone-change', children: [el('span', { cls: 'f-muted f-ellipsis', text: rows[0].before }),
      kit.icon('arrow-right', 'f-i-muted'), el('span', { cls: 'f-sr', text: '에서' }),
      el('span', { cls: 'f-strong f-ellipsis', text: rows[0].after })] });
  }

  function evidenceChip(card) {
    if (card.similar && card.similar.count) {
      return el('span', { cls: 'f-chip f-ellipsis', children: [kit.icon('folder-close'), el('span', { text: '사례 ' + card.similar.count + '건' })] });
    }
    return null;
  }

  /** 펼침 칸 — 이유 · 근거 · (PC 에서 볼 것이면 안내) · 거절 까닭 칩 · PC 에서 볼게요. */
  function moreBox(card, c, canApply) {
    var prop = card.main;
    var box = el('div', { cls: 'f-col fb-phone-more', attrs: { 'data-ds-phone-more-box': '1' } });
    box.hidden = true;
    var warn = review.conflictText(prop);
    if (warn) box.appendChild(el('div', { cls: 'f-callout f-callout-warning', children: [kit.icon('warning-sign'), el('span', { text: warn })] }));
    if (!canApply && !warn) box.appendChild(el('p', { cls: 'f-help', text: PC_HINT }));
    box.appendChild(kit.reasonLine(prop));
    box.appendChild(kit.detailBits(prop, card, c, true));
    var failed = kit.gates(prop, c);
    if (failed) box.appendChild(failed);
    if (review.actionsFor(prop, false).reject) {
      var reject = cardKit.rejectChips(c);
      reject.hidden = false;
      box.appendChild(reject);
    }
    if (canApply) box.appendChild(el('div', { cls: 'f-actions', children: [kit.button('PC 에서 볼게요', 'later', 'f-btn-minimal', 'time')] }));
    return box;
  }

  /** 폰 카드 하나 — canApply 면 [승인](칸 하나 고침), 아니면 펼침만. */
  function build(card, c, canApply) {
    var prop = card.main;
    var li = el('li', { cls: 'f-card f-card-e1 f-col fb-phone-card', attrs: { 'data-card-id': card.id, 'data-ds-inbox-own': '1' } });
    var box = el('div', { cls: 'f-col fb-prop', attrs: { 'data-change-id': prop.id, 'data-shown-at': Math.round(window.performance.now()) } });
    var tag = el('span', { cls: 'f-tag f-tag-minimal', children: [kit.icon(canApply ? 'edit' : 'applications'),
      el('span', { text: canApply ? '한 칸 고침' : iv.typeLabel(c.display, card.type) })] });
    box.appendChild(el('div', { cls: 'f-row f-between', children: [el('div', { cls: 'f-row f-gap4', children: [tag, who(prop)] }),
      el('span', { cls: 'f-small f-muted f-num', text: iv.whenText(prop.created_at, today()) })] }));
    box.appendChild(el('button', { cls: 'fb-phone-card__title f-strong', text: titleText(card, c),
                                   attrs: { type: 'button', 'aria-expanded': 'false', 'data-ds-phone-toggle': '1' } }));
    var change = changeRow(prop, c);
    if (change) box.appendChild(change);
    if (canApply && prop.confirm) box.appendChild(kit.confirmBox(prop, c));
    var foot = el('div', { cls: 'f-row-nw' });
    var chip = evidenceChip(card);
    if (chip) foot.appendChild(chip);
    if (canApply) foot.appendChild(kit.button(review.actionLabel(c.actions, 'apply'), 'apply', 'f-btn-primary f-push fb-phone-approve', 'tick'));
    if (foot.firstChild) box.appendChild(foot);
    box.appendChild(moreBox(card, c, canApply));
    box.appendChild(kit.statusLine());
    li.appendChild(box);
    return li;
  }

  /** 카드를 누르면(단추 · 링크 · 입력 칸 말고) 펼침 칸을 열고 닫는다. */
  function toggle(target) {
    var card = target.closest('.fb-phone-card');
    if (!card) return false;
    var title = card.querySelector('[data-ds-phone-toggle]');
    if (target.closest('a, input, select, textarea, label') || (target.closest('button') && target.closest('button') !== title)) return false;
    var more = card.querySelector('[data-ds-phone-more-box]');
    if (!more) return false;
    more.hidden = !more.hidden;
    if (title) title.setAttribute('aria-expanded', more.hidden ? 'false' : 'true');
    return true;
  }

  function parts() {
    var section = document.querySelector('[data-ds-inbox-phone]') || document.body;
    return { list: section.querySelector('[data-ds-phone-list]'), count: section.querySelector('[data-ds-phone-count]'),
             more: section.querySelector('[data-ds-phone-more]'), pcToggle: section.querySelector('[data-ds-phone-pc-toggle]'),
             pcList: section.querySelector('[data-ds-phone-pc-list]'), pcTitle: section.querySelector('[data-ds-phone-pc-title]'),
             pcSub: section.querySelector('[data-ds-phone-pc-sub]') };
  }

  /** 수 · 접기 — 목록의 모든 카드(T8 것 포함)로 센다. */
  function fold() {
    var p = parts();
    if (!p.list) return;
    var items = Array.prototype.slice.call(p.list.children);
    items.forEach(function (node, i) { node.hidden = !expanded && i >= FIRST; });
    if (p.count) p.count.textContent = String(items.length);
    if (p.more) {
      p.more.hidden = expanded || items.length <= FIRST;
      p.more.textContent = '';
      p.more.appendChild(document.createTextNode((items.length - FIRST) + '개 더 보기'));
      p.more.appendChild(kit.icon('chevron-down'));
    }
  }

  /** 카드 하나 — ③ 은 질문 카드(폰에서도 답한다), 그 밖은 폰 카드. 이 파일이 넣은 표시(data-ds-inbox-own)를 붙인다. */
  function node(card, c, canApply) {
    var out = iv.binOf(card) === 'decide' && questionKit ? questionKit.build(card) : build(card, c, canApply);
    out.setAttribute('data-ds-inbox-own', '1');
    return out;
  }

  /** 폰 그리기 — split = iv.phoneSplit(…) 결과. */
  function render(split, c) {
    var p = parts();
    if (!p.list) return;
    Array.prototype.slice.call(p.list.querySelectorAll('[data-ds-inbox-own]')).forEach(function (n) { p.list.removeChild(n); });
    split.phone.forEach(function (card) { p.list.appendChild(node(card, c, true)); });
    if (p.pcList) {
      dom.clear(p.pcList);
      split.pc.forEach(function (card) {
        var folded = node(card, c, false);
        Array.prototype.slice.call(folded.querySelectorAll('[data-ds-act="later"]')).forEach(function (b) { b.hidden = true; });
        p.pcList.appendChild(folded);
      });
    }
    if (p.pcToggle) p.pcToggle.hidden = !split.pc.length;
    if (p.pcList && !split.pc.length) p.pcList.hidden = true;
    if (p.pcTitle) p.pcTitle.textContent = 'PC 에서 볼 것 ' + split.pc.length;
    if (p.pcSub) p.pcSub.textContent = '칸이 여럿이거나 새 지식 · 은퇴 · 지우기 · 연결이에요 — ' + iv.pcSummary(split.pc, c.display);
    fold();
  }

  /** 누름 — 더 보기 · PC 에서 볼 것 펼치기 · 카드 펼치기. 받았으면 true. */
  function onClick(target) {
    var p = parts();
    if (p.more && target.closest('[data-ds-phone-more]') === p.more) { expanded = true; fold(); return true; }
    if (p.pcToggle && target.closest('[data-ds-phone-pc-toggle]') === p.pcToggle) {
      p.pcList.hidden = !p.pcList.hidden;
      p.pcToggle.setAttribute('aria-expanded', p.pcList.hidden ? 'false' : 'true');
      return true;
    }
    return toggle(target);
  }

  function watch() {
    var p = parts();
    if (p.list && window.MutationObserver) new window.MutationObserver(fold).observe(p.list, { childList: true });
  }

  window.FOMS_DS_INBOX_PHONE = { render: render, onClick: onClick, fold: fold, watch: watch };
})();
