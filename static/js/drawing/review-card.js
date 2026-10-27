/**
 * 도면 마법사 — AI 도면팀원 검수 메모 카드(화면 오른쪽 아래, V1 · V2 공용 — 둘 다 같은 [저장] 단추를 쓴다).
 *
 * 설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A1
 * - [저장] · [일괄 저장] 뒤 메모가 있을 때만 뜬다. 메모는 시트를 바꾸지 않는다.
 *   [보기] = 그 그림 · 칸을 골라 보여 준다(다른 시트 메모면 그 시트로 간다).
 *   [끄기] = 그 시트에서 그 메모를 다시 띄우지 않는다(끈 수는 학습 요약이 센다).
 * - 카드는 [닫기] · Esc(카드 안에서) · 다음 [저장] 때까지 그대로 둔다. 일하는 손을 막지 않게 포커스는 가져가지 않는다.
 * - 알림(가운데 아래)과 겹치지 않게 오른쪽 아래(wizard.css .dws-review-card).
 *
 * window.FomsReviewCard = { show(groups, on), hide(), isOpen(), count() }
 *   groups : [{ sheetId, sheetName, memos: [memo] }] — memo 는 review-memo.js check 결과
 *   on     : { look(sheetId, memo), off(sheetId, memo) }
 */
(function () {
  'use strict';
  if (window.FomsReviewCard) { return; }

  var card = null, list = null, sub = null, on = {}, groups = [];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }

  function button(text, cls, title) {
    var b = el('button', 'dws-btn ' + cls, text);
    b.type = 'button';
    if (title) { b.title = title; }
    return b;
  }

  function live() { return groups.filter(function (g) { return g.memos.length > 0; }); }

  function count() { return live().reduce(function (n, g) { return n + g.memos.length; }, 0); }

  /** [보기]로 보여 줄 것이 있는 메모만 단추를 단다. */
  function canLook(m) { return (m.ids && m.ids.length > 0) || !!m.field || m.rule === 'bom'; }

  function build() {
    card = el('section', 'dws-review-card');
    card.setAttribute('role', 'region');
    card.setAttribute('aria-label', 'AI 도면팀원 검수 메모');
    card.hidden = true;
    var head = el('div', 'dws-review-head');
    head.appendChild(el('span', 'dws-review-avatar', 'AI'));
    var title = el('div', 'dws-review-title');
    title.appendChild(el('strong', 'dws-review-name', 'AI 도면팀원'));
    sub = el('span', 'dws-review-sub');
    sub.setAttribute('aria-live', 'polite');
    title.appendChild(sub);
    head.appendChild(title);
    var close = el('button', 'dws-review-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', '검수 메모 닫기');
    close.addEventListener('click', hide);
    head.appendChild(close);
    card.appendChild(head);
    list = el('ul', 'dws-review-list');
    card.appendChild(list);
    card.appendChild(el('p', 'dws-review-foot', '메모는 시트를 바꾸지 않아요. 맞지 않는 메모는 [끄기]를 눌러 주세요.'));
    card.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.stopPropagation(); hide(); } });
    document.body.appendChild(card);
  }

  function item(g, m) {
    var li = el('li', 'dws-review-item');
    li.appendChild(el('span', 'dws-review-text', m.text));
    var acts = el('span', 'dws-review-acts');
    if (canLook(m)) {
      var look = button('보기', 'dws-review-look');
      look.addEventListener('click', function () { if (on.look) { on.look(g.sheetId, m); } });
      acts.appendChild(look);
    }
    var off = button('끄기', 'dws-review-off', '이 시트에서 이 메모를 다시 띄우지 않아요');
    off.addEventListener('click', function () {
      g.memos = g.memos.filter(function (x) { return x !== m; });
      if (on.off) { on.off(g.sheetId, m); }
      if (count()) { render(); } else { hide(); }
    });
    acts.appendChild(off);
    li.appendChild(acts);
    return li;
  }

  function render() {
    var shown = live(), many = shown.length > 1;
    while (list.firstChild) { list.removeChild(list.firstChild); }
    sub.textContent = '검수 메모 ' + count() + '개' + (many ? '' : ' · ' + (shown[0].sheetName || '도면'));
    shown.forEach(function (g) {
      if (many) { list.appendChild(el('li', 'dws-review-sheet', g.sheetName || '도면')); }
      g.memos.forEach(function (m) { list.appendChild(item(g, m)); });
    });
  }

  function show(next, handlers) {
    groups = (next || []).map(function (g) { return { sheetId: g.sheetId, sheetName: g.sheetName, memos: (g.memos || []).slice() }; });
    on = handlers || {};
    if (!count()) { hide(); return; }
    if (!card) { build(); }
    render();
    card.hidden = false;
  }

  function hide() {
    groups = [];
    if (card) { card.hidden = true; }
  }

  function isOpen() { return !!card && !card.hidden; }

  window.FomsReviewCard = { show: show, hide: hide, isOpen: isOpen, count: count };
})();
