/**
 * 새 물어보기 화면(판 ⑨ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.7 · 5.4) 그리기 도구 — 물음 한 칸 · 답 카드 ·
 * '이 답이 읽은 것' 옆 창. 받은 값 → DOM 만(요청 · 상태는 ds-ask.js).
 *
 * - 답 카드: 물어보기 AI 표 · 모름 / ERP 읽기 꼬리표 · 걸린 시간 · 답 글 · (일정 바꾸기 질문이면) '방문 옮기기는 승인 대기로 가요' ·
 *   (모름이면) 물어볼 곳 상자 · 근거 칩(주문 · 방문 + 회사 지식 — 카드를 열 수 있는 사람만 링크) · 확인 중 지식 · 답이 맞을 가능성 ·
 *   근거 확신 · 도움 됨 · 도움 안 됨 · 틀림(+ 무엇이 틀렸나 · 지식 고치기 링크).
 * - 답 판정은 brain-ask-view.js(옛 화면과 한 벌), 화면 값은 ds-ask-view.js. 글은 textContent 만(brain-dom.js el).
 * window.FOMS_DS_ASK_TURN.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_ASK_VIEW;
  var dv = window.FOMS_DS_ASK_VIEW;
  if (!dom || !view || !dv) return;
  var el = dom.el;

  /** 디자인 시스템 아이콘(장식). */
  function icon(name, extra) {
    return el('span', { cls: 'f-i i-' + name + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  function tag(t, extra) {
    if (!t) return null;
    var cls = 'f-tag' + (t.minimal ? ' f-tag-minimal' : '') + (t.tone ? ' f-tag-' + t.tone : '') + (extra ? ' ' + extra : '');
    return el('span', { cls: cls, children: [t.icon ? icon(t.icon) : null, document.createTextNode(t.text)] });
  }

  function small(text, extra) {
    return el('span', { cls: 'f-small f-muted' + (extra ? ' ' + extra : ''), text: text });
  }

  /** 물음 한 칸(오른쪽) — 내가 쓴 글 그대로 + 이름 · 때 · 가린 곳 수. */
  function questionNode(question, line) {
    return el('div', { cls: 'f-col f-gap4 fb-ask-q', children: [
      el('div', { cls: 'f-card f-card-compact fb-ask-q__text', text: question }), small(line)] });
  }

  function knowledgeChip(c) {
    var node = el(c.href ? 'a' : 'span', { cls: 'f-chip', attrs: { href: c.href, title: c.meta || null } });
    node.appendChild(icon('properties'));
    node.appendChild(document.createTextNode(c.name));
    if (c.meta) node.appendChild(el('span', { cls: 'fb-chip-meta', text: ' · ' + c.meta }));
    return node;
  }

  function evidenceRow(data, v) {
    var chips = dv.erpChips(data).map(function (c) {
      return el('span', { cls: 'f-chip', children: [icon(c.icon), document.createTextNode(c.text)] });
    }).concat(v.chips.map(knowledgeChip));
    if (!chips.length) return null;
    return el('div', { cls: 'f-row f-gap4', children: [small('근거')].concat(chips) });
  }

  function fixPanel(id, v) {
    var label = 'ds-ask-fix-' + id;
    return el('div', { cls: 'f-col f-gap4 fb-ask-fix', attrs: { hidden: 'hidden', 'data-fix': '1' }, children: [
      el('label', { cls: 'f-label', text: '무엇이 틀렸나요?', attrs: { for: label } }),
      el('textarea', { cls: 'f-input', attrs: { id: label, maxlength: '500', rows: '2', 'data-fix-note': '1' } }),
      el('div', { cls: 'f-row', children: [
        el('button', { cls: 'f-btn f-btn-primary f-btn-small', text: '틀림 보내기', attrs: { type: 'button', 'data-fix-send': '1' } }),
        v.fixLink ? el('a', { cls: 'f-btn f-btn-small', text: '지식 고치기', attrs: { href: v.fixLink } }) : null] })] });
  }

  function feedbackButtons(v) {
    var icons = { helpful: 'tick', wrong: 'warning-sign' };
    return el('span', { cls: 'f-row f-gap4 f-push', children: v.feedback.map(function (f) {
      return el('button', { cls: 'f-btn f-btn-small' + (f.value === 'helpful' ? '' : ' f-btn-minimal'),
                            attrs: { type: 'button', 'data-feedback': f.value },
                            children: [icons[f.value] ? icon(icons[f.value]) : null, document.createTextNode(f.label)] });
    }) });
  }

  function certaintyRow(data, v, display) {
    var row = el('div', { cls: 'f-row' });
    var sure = dv.certaintyTag(data);
    if (sure) {
      row.appendChild(small('답이 맞을 가능성'));
      row.appendChild(tag({ text: sure.text, tone: sure.tone, minimal: true }));
    }
    var basis = [];
    if (!data.unknown && data.confidence) {
      basis.push('근거: ' + (((display || {}).confidences || {})[data.confidence] || data.confidence));
    }
    if (dv.erpChips(data).length) basis.push('주문 · 방문은 읽기만 했어요');
    if (basis.length) row.appendChild(small(basis.join(' · ')));
    row.appendChild(feedbackButtons(v));
    return row;
  }

  /** 답 카드 — data = POST /api/brain/chat/ask 의 data. opts: {display, items, elapsed(ms)}. */
  function answerNode(data, opts) {
    var v = view.answerView(data, opts.display, opts.items);
    var erpAnswer = !data.unknown && data.kind === 'erp';
    var card = el('article', { cls: 'f-ai-card fb-ask-a' + (erpAnswer ? ' is-proposal' : '') + (data.unknown ? ' is-unknown' : ''),
                               attrs: { 'aria-label': data.unknown ? '답 — 모름' : '답', 'data-question': data.id,
                                        'data-question-id': data.id } });
    var head = el('div', { cls: 'f-row', children: [
      el('span', { cls: 'f-ai-mark', children: [icon('predictive-analysis'), document.createTextNode('물어보기 AI')] }),
      tag(dv.kindTag(data))] });
    head.appendChild(small([dv.clockOf(), dv.secsLabel(opts.elapsed)].filter(Boolean).join(' · '), 'f-push'));
    card.appendChild(head);
    card.appendChild(el('div', { cls: 'f-quote', text: v.text }));
    if (data.erp && data.erp.change_asked) {
      card.appendChild(el('div', { cls: 'f-row-nw f-small f-muted', attrs: { 'data-ds-ask-change': '1' },
                                   children: [icon('lock'), document.createTextNode('방문 옮기기는 승인 대기로 가요')] }));
    }
    if (data.unknown) {
      card.appendChild(el('div', { cls: 'f-callout', attrs: { 'data-ds-ask-team': '1', hidden: 'hidden' }, children: [
        icon('people'), el('div', { cls: 'f-grow', children: [el('div', { cls: 'f-callout-title', text: '물어볼 곳' }),
                                                              el('span', { attrs: { 'data-ds-ask-team-label': '1' } })] })] }));
    }
    var evidence = evidenceRow(data, v);
    if (evidence) card.appendChild(evidence);
    if (v.checks) card.appendChild(el('div', { cls: 'f-row-nw f-small f-muted', children: [icon('time'), document.createTextNode(v.checks)] }));
    card.appendChild(certaintyRow(data, v, opts.display));
    card.appendChild(fixPanel(data.id, v));
    card.appendChild(el('p', { cls: 'fb-status', attrs: { 'data-feedback-status': '1', role: 'status' } }));
    return card;
  }

  /** 모름 답의 물어볼 곳(내 질문 목록이 준 이름 — 없으면 상자를 숨긴 채). */
  function setTeam(card, label) {
    var box = card && card.querySelector('[data-ds-ask-team]');
    if (!box || !label) return;
    box.querySelector('[data-ds-ask-team-label]').textContent = label;
    box.hidden = false;
  }

  function visitNode(v) {
    return el('div', { cls: 'f-visit', children: [
      el('span', { cls: 'f-visit-kind', children: [el('span', { cls: 'f-tag st-' + v.st, text: v.label }),
                                                   document.createTextNode([v.day, v.time].filter(Boolean).join(' '))] }),
      el('span', { cls: 'f-muted', text: v.state })] });
  }

  function toolNode(t) {
    return el('li', { cls: 'f-row-nw', attrs: { title: t.label || null }, children: [
      icon('small-tick', 'f-i-success'), el('span', { cls: 'f-mono', text: t.name }),
      small(t.what, 'f-grow'), small(t.secs, 'f-num')] });
  }

  /** 옆 창 몸 채우기 — rv = FOMS_DS_ASK_VIEW.readView(erp). */
  function fillRead(body, rv) {
    dom.clear(body);
    var kv = el('dl', { cls: 'f-kv', children: [
      el('dt', { text: '상태' }), el('dd', { children: [tag({ text: rv.stage.text, tone: rv.stage.tone })] }),
      el('dt', { text: '품목' }), el('dd', { text: rv.products || '없음' })] });
    if (rv.manager) {
      kv.appendChild(el('dt', { text: '담당 영업' }));
      kv.appendChild(el('dd', { text: rv.manager }));
    }
    if (rv.masked) {
      kv.appendChild(el('dt', { text: rv.masked }));
      kv.appendChild(el('dd', { children: [el('span', { cls: 'f-lock f-small', children: [
        icon('lock'), document.createTextNode(' 가려서 안 받음')] })] }));
    }
    body.appendChild(el('div', { cls: 'f-col f-gap4', children: [
      el('div', { cls: 'f-row f-gap4', children: [
        el('span', { cls: 'f-type', children: [icon('cube'), document.createTextNode('ERP 물건 · 주문')] }),
        tag({ text: '새로 붙음', tone: 'primary', minimal: true })] }),
      el('h2', { cls: 'f-h5', text: rv.title })] }));
    body.appendChild(kv);
    body.appendChild(el('section', { cls: 'f-col', attrs: { 'aria-label': '방문' }, children: [
      el('h3', { cls: 'f-h6', text: '방문 ' + rv.visits.length })].concat(
      rv.visits.length ? rv.visits.map(visitNode) : [small('잡힌 방문이 없어요.')]) }));
    if (rv.tools.length) {
      body.appendChild(el('section', { cls: 'f-col', attrs: { 'aria-label': '쓴 도구' }, children: [
        el('h3', { cls: 'f-h6', text: '쓴 도구' }), el('ol', { cls: 'f-col f-gap4', children: rv.tools.map(toolNode) })] }));
    }
    body.appendChild(el('div', { cls: 'f-callout f-callout-primary', children: [icon('lock'), el('div', {
      cls: 'f-small', text: "주문 · 방문은 읽기만 해요. 일정을 바꾸려면 '방문 옮기기' 할 일 제안이 승인 대기로 가요." })] }));
  }

  window.FOMS_DS_ASK_TURN = { icon: icon, questionNode: questionNode, answerNode: answerNode, setTeam: setTeam,
                              fillRead: fillRead };
})();
