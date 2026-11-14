/**
 * 채널톡 안 작은 창(WAM) 접목 두 줄 — 근거 칩 · 할 일 제안 줄(설계서 2026-11-14-foms-graft 3.9 · 판 ⑤).
 *
 * 상담 관리 칸('근거 줄 보이기' · '할 일 제안 만들기')이 켜졌을 때만 틀(cs_agent_wam.html)이 빈 자리와 이 파일을 싣는다 — 끄면
 * 작은 창은 지금과 같다. 값은 wam-draft.js 가 부르는 서명 함수 답(cs.draft.get 의 evidence · action, cs.draft.send 의 action)뿐이고,
 * 이 파일은 서버를 따로 부르지 않는다. wam-draft.js 와 만나는 다리 하나:
 *
 *   window.FOMS_WAM_GRAFT = {
 *     holdSend,            // 할 일 제안 줄 자리가 있나 — [보내기]로 열려도 줄을 먼저 보이고 고르게 한다
 *     hold(ui),            // ui = { call, send, size, say, show, small } — 제안이 없으면 지금처럼 바로 보낸다
 *     fill(result),        // cs.draft.get 답 → 칩 · 줄을 그리고 더할 높이(px)를 돌려준다
 *     params(),            // [보내기] 값 — { with_action } · { drop_action } · {}
 *     after(result, wait)  // 보낸 뒤 — 할 일 결과 한 줄 → { px, wait }(실패 줄이면 창을 닫지 않는다)
 *   }
 *
 * 글은 textContent 로만 넣는다. 칩 주소는 서버가 준 FOMS 절대 주소(https)일 때만 a(새 창) — 아니면 글만(채널톡이 거쳐 여는 창이라
 * 상대 주소는 채널톡 쪽으로 풀린다).
 */
(function () {
  'use strict';

  if (window.FOMS_WAM_GRAFT) return;
  var $ = function (id) { return document.getElementById(id); };
  var evidenceBox = $('cs-wam-evidence');
  var evidenceLabel = $('cs-wam-evidence-label');
  var chips = $('cs-wam-evidence-chips');
  var actionBox = $('cs-wam-action');
  var actionText = $('cs-wam-action-text');
  var actionRow = $('cs-wam-action-row');
  var hint = $('cs-wam-action-hint');
  var addButton = $('cs-wam-action-add');
  var dropButton = $('cs-wam-action-drop');
  var resultLine = $('cs-wam-action-result');
  var HINTS = { add: '답을 보내면 같이 넣어요', drop: '답을 보내면 이 제안은 빼요' };
  var GAP = 8;
  var state = { id: null, choice: 'add' };

  function heightOf(box) {
    return box && !box.hidden ? box.offsetHeight + GAP : 0;
  }

  function choose(choice) {
    state.choice = choice === 'drop' ? 'drop' : 'add';
    if (addButton) addButton.setAttribute('aria-pressed', String(state.choice === 'add'));
    if (dropButton) dropButton.setAttribute('aria-pressed', String(state.choice === 'drop'));
    if (hint) hint.textContent = HINTS[state.choice];
  }

  function chip(item) {
    var href = item && typeof item.href === 'string' && item.href.indexOf('https://') === 0 ? item.href : '';
    var node = document.createElement(href ? 'a' : 'span');
    node.className = 'cs-wam__ev';
    node.textContent = String(item.label || '');
    if (href) {
      node.href = href;
      node.target = '_blank';
      node.rel = 'noopener noreferrer';
    }
    return node;
  }

  function fillEvidence(items) {
    if (!evidenceBox || !chips) return 0;
    chips.textContent = '';
    var list = Array.isArray(items) ? items.filter(function (item) { return item && item.label; }) : [];
    list.forEach(function (item) { chips.appendChild(chip(item)); });
    if (evidenceLabel) evidenceLabel.textContent = '근거 ' + list.length + ' — 누르면 회사 지식 · 주문이 열려요';
    evidenceBox.hidden = !list.length;
    return heightOf(evidenceBox);
  }

  function fillAction(action) {
    if (!actionBox) return 0;
    var ok = action && typeof action === 'object' && typeof action.id === 'number' && action.id > 0;
    if (!ok) {
      state.id = null;
      actionBox.hidden = true;
      return 0;
    }
    if (state.id !== action.id) choose('add');
    state.id = action.id;
    actionText.textContent = String(action.label || '') + (action.text ? ' — ' + String(action.text) : '');
    if (actionRow) actionRow.hidden = false;
    if (resultLine) resultLine.hidden = true;
    actionBox.hidden = false;
    return heightOf(actionBox);
  }

  function fill(result) {
    var shown = result && result.ok && !result.blocked;
    return fillEvidence(shown ? result.evidence : null) + fillAction(shown ? result.action : null);
  }

  function params() {
    if (!state.id) return {};
    return state.choice === 'drop' ? { drop_action: state.id } : { with_action: state.id };
  }

  // 보낸 뒤 — 근거 칩은 접고, 할 일 줄은 결과 한 줄만 남긴다. 실패 줄이면 창을 닫지 않는다(읽고 닫기).
  function after(result, wait) {
    if (evidenceBox) evidenceBox.hidden = true;
    var act = result && result.action && typeof result.action === 'object' ? result.action : null;
    if (!actionBox || !state.id || !act) {
      if (actionBox) actionBox.hidden = true;
      return { px: 0, wait: wait };
    }
    state.id = null;
    if (actionRow) actionRow.hidden = true;
    resultLine.textContent = String(act.message || '');
    resultLine.hidden = false;
    return { px: heightOf(actionBox), wait: act.ok ? wait * 2 : 0 };
  }

  // [보내기]로 열렸을 때 — 고칠 재료를 한 번 읽어 할 일 줄이 있으면 보이고 기다린다. 없으면(끔 · 막힘 · 못 읽음) 지금처럼 바로 보낸다.
  function hold(ui) {
    ui.call('cs.draft.get', {}).then(function (result) {
      var px = result && result.action ? fill(result) : 0;
      if (!state.id) {
        fill(null);
        ui.send();
        return;
      }
      ui.size(ui.small + px);
      ui.say('할 일 제안이 있어요. 같이 넣을지 고른 뒤 보내기를 눌러 주세요.');
      ui.show(['send', 'toEdit']);
    });
  }

  if (addButton) addButton.addEventListener('click', function () { choose('add'); });
  if (dropButton) dropButton.addEventListener('click', function () { choose('drop'); });

  window.FOMS_WAM_GRAFT = { holdSend: Boolean(actionBox), hold: hold, fill: fill, params: params, after: after };
}());
