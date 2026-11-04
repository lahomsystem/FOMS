/**
 * '승인 대기' 첫 화면 네 묶음(HAUD master brain 설계서 7.9 · 사장님 11-03 "사용법이 너무 어려워") — 제안 카드를 서버가 정한
 * 묶음(card.bin)으로 세고, 묶음마다 한 줄(이름 · 수 · 하는 일 · 걸리는 시간 · 열기)을 그린다. 글은 textContent 만 · 인라인
 * 스타일 없음. 누름(열기 · 돌아가기)은 brain-inbox.js 가 받는다 — 이 파일은 그리기와 거르기만.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  if (!dom) return;
  var el = dom.el;

  /** 화면 차례 · 글(시안 그대로). secs = 한 장에 드는 어림 초(걸리는 시간 한 줄에만 쓴다). */
  var BINS = [
    { key: 'names', title: '① 한글 이름 붙이기',
      line: '영어 이름을 한글로 바꾸고 비슷한 말을 붙여요. 글 · 금액은 그대로예요.', secs: 10 },
    { key: 'content', title: '② 새로 들어가거나 바뀌는 지식',
      line: '새로 들어가거나 바뀌는 내용이에요. 맞는지만 봐 주세요.', secs: 25 },
    { key: 'decide', title: '③ 사장님이 정해 주실 것',
      line: '두 곳에 다르게 적힌 내용이에요. 맞는 쪽을 골라 주세요.', secs: 40 },
    { key: 'mark', title: '④ 같은 값이 적힌 곳 표시',
      line: '같은 값이 적힌 곳을 표시만 해요. 글 · 금액은 그대로예요.', secs: 5 }
  ];
  var KEYS = BINS.map(function (bin) { return bin.key; });

  /** 카드의 묶음 — 모르는 값은 ②(한 장씩 보는 쪽)로. */
  function binOf(card) {
    return KEYS.indexOf(card && card.bin) >= 0 ? card.bin : 'content';
  }

  function counts(cards) {
    var out = {};
    KEYS.forEach(function (key) { out[key] = 0; });
    (cards || []).forEach(function (card) { out[binOf(card)] += 1; });
    return out;
  }

  function minutes(n, secs) {
    return Math.max(1, Math.round((n * secs) / 60));
  }

  function find(key) {
    for (var i = 0; i < BINS.length; i += 1) if (BINS[i].key === key) return BINS[i];
    return null;
  }

  /** 첫 화면 — 카드가 있는 묶음만 한 줄씩. */
  function renderOverview(list, cards) {
    dom.clear(list);
    var n = counts(cards);
    BINS.forEach(function (bin) {
      if (!n[bin.key]) return;
      var li = el('li', { cls: 'brain-icard brain-inbox__bin', attrs: { 'data-bin': bin.key } });
      li.appendChild(el('div', { cls: 'brain-icard__head', children: [
        el('span', { cls: 'brain-icard__name', text: bin.title + ' · ' + n[bin.key] + '개' })] }));
      li.appendChild(el('p', { cls: 'brain-icard__summary', text: bin.line }));
      var open = el('button', { cls: 'brain-btn brain-btn--primary', text: '열기',
                                attrs: { type: 'button', 'data-brain-bin-open': bin.key } });
      li.appendChild(el('div', { cls: 'brain-prop__actions', children: [
        open, el('span', { cls: 'brain-empty', text: '약 ' + minutes(n[bin.key], bin.secs) + '분' })] }));
      list.appendChild(li);
    });
  }

  function inBin(cards, key) {
    return (cards || []).filter(function (card) { return binOf(card) === key; });
  }

  function title(key, n) {
    var bin = find(key);
    return bin ? bin.title + ' · ' + n + '개' : '';
  }

  window.FOMS_BRAIN_INBOX_BINS = { counts: counts, renderOverview: renderOverview, inBin: inBin, title: title,
                                   keys: KEYS.slice() };
})();
