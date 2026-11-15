/**
 * 새 승인 대기 화면(설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.3 · 5.4 · 판 ⑥ · ⑫) 순수 계산 — DOM 을 만지지 않는다.
 *
 * 묶음 여섯(차례 · 글 · 한 장 어림 초는 옛 brain-inbox-bins.js 와 같은 값 — 짧은 이름만 왼쪽 길잡이용으로 더함) · 묶음 줄 ·
 * 빈 묶음 한 줄 · 숫자 띠(오늘 결정할 것 · 어림 · AI 할 일 제안 · 지식 고침) · 첫 장 미리 보기 글 · 주소의 묶음 · 폰 나누기 ·
 * 'PC 에서 볼 것' 요약 · 때 글 · 등급 A 한꺼번에 대상. 승인 · 한꺼번에 판정은 brain-review-view.js 의 함수(actionsFor ·
 * bulkIds)를 인자로 받아 부른다(같은 판정을 새로 쓰지 않는다).
 * window.FOMS_DS_INBOX_VIEW 로 내놓고 node 에서는 module.exports — tests/domains/test_brain_ds_inbox_js.py.
 */
(function (root) {
  'use strict';

  /** 화면 차례 · 글. secs = 한 장에 드는 어림 초(어림 분에만 쓴다). */
  var BINS = [
    { key: 'names', title: '① 한글 이름 붙이기', short: '① 한글 이름 붙이기',
      line: '영어 이름을 한글로 바꾸고 비슷한 말을 붙여요. 글 · 금액은 그대로예요.', secs: 10 },
    { key: 'content', title: '② 새로 들어가거나 바뀌는 지식', short: '② 새로 · 바뀌는 지식',
      line: '새로 들어가거나 바뀌는 내용이에요. 맞는지만 봐 주세요.', secs: 25 },
    { key: 'decide', title: '③ 사장님이 정해 주실 것', short: '③ 사장님이 정할 것',
      line: '두 곳에 다르게 적힌 내용이에요. 맞는 쪽을 골라 주세요.', secs: 40 },
    { key: 'mark', title: '④ 같은 값이 적힌 곳 표시', short: '④ 같은 값 표시',
      line: '같은 값이 적힌 곳을 표시만 해요. 글 · 금액은 그대로예요.', secs: 5 },
    { key: 'calc', title: '⑤ 계산기 제품 · 옵션', short: '⑤ 계산기 제품 · 옵션',
      line: '견적 계산기 제품 · 옵션을 지식에 넣어요. 금액은 계산기를 가리키기만 해요.', secs: 5 },
    { key: 'rules', title: '⑥ 규칙 잇기', short: '⑥ 규칙 잇기',
      line: '정책 · 가격 규칙이 어느 제품 · 옵션, 어느 공정 단계에 걸리는지 이어요. 글 · 금액은 그대로예요.', secs: 5 }
  ];
  var KEYS = BINS.map(function (bin) { return bin.key; });
  /** '나중에 볼 것' 보기 — 묶음이 아니라 이 화면에서 접어 둔 카드(서버 쓰기 없음). */
  var LATER = 'later';
  /** AI 할 일 제안 한 장 어림 초(T8 이 수만 알려 준다 — setCount('actions', n)). */
  var ACTION_SECS = 20;
  /** ⑤ 줄 차례 — 브랜드(라홈 → 하우드 → 공통) → 이름. */
  var BRAND_ORDER = ['LAHOM', 'HAUD', 'COMMON'];

  function find(key) {
    for (var i = 0; i < BINS.length; i += 1) if (BINS[i].key === key) return BINS[i];
    return null;
  }

  /** 카드의 묶음 — 모르는 값은 ②(한 장씩 보는 쪽)로. */
  function binOf(card) {
    return KEYS.indexOf(card && card.bin) >= 0 ? card.bin : 'content';
  }

  /** 어림 분 — 0장이면 0, 아니면 1분 이상. */
  function minutes(n, secs) {
    var count = Math.max(0, Number(n) || 0);
    return count ? Math.max(1, Math.round((count * secs) / 60)) : 0;
  }

  function counts(cards) {
    var out = {};
    KEYS.forEach(function (key) { out[key] = 0; });
    (cards || []).forEach(function (card) { out[binOf(card)] += 1; });
    return out;
  }

  function linkText(card, end) {
    var link = (card.main && card.main.link) || {};
    return String(link[end + '_label'] || link[end] || '');
  }

  function brandRank(card) {
    var i = BRAND_ORDER.indexOf(card.brand);
    return i < 0 ? BRAND_ORDER.length : i;
  }

  /** 묶음 안 카드(⑤ 브랜드 → 이름 · ⑥ 규칙 → 걸리는 것 차례, 나머지는 서버 차례 그대로). */
  function inBin(cards, key) {
    var out = (cards || []).filter(function (card) { return binOf(card) === key; });
    if (key === 'rules') {
      return out.slice().sort(function (a, b) {
        return linkText(a, 'from').localeCompare(linkText(b, 'from'), 'ko') ||
          linkText(a, 'to').localeCompare(linkText(b, 'to'), 'ko');
      });
    }
    if (key !== 'calc') return out;
    return out.slice().sort(function (a, b) {
      return (brandRank(a) - brandRank(b)) || String(a.title || a.name).localeCompare(String(b.title || b.name), 'ko');
    });
  }

  function typeLabel(display, type) {
    var t = display && display.types && display.types[type];
    return t ? t.label : String(type || '');
  }

  /** 첫 장 미리 보기 — 연결은 '시작 → 끝', 그 밖은 '유형 — 제목'(새로 만들면 '(새로)'). */
  function peekText(card, display) {
    if (!card) return '';
    var main = card.main || {};
    if (main.link) return linkText(card, 'from') + ' → ' + linkText(card, 'to');
    return typeLabel(display, card.type) + ' — ' + (card.title || card.name || '') + (main.op === 'create' ? ' (새로)' : '');
  }

  /** 묶음 줄 — 카드가 있는 묶음만, 화면 차례로 [{key, title, n, line, mins, peek}]. */
  function binRows(cards, display) {
    var n = counts(cards);
    return BINS.filter(function (bin) { return n[bin.key] > 0; }).map(function (bin) {
      return { key: bin.key, title: bin.title, n: n[bin.key], line: bin.line, mins: minutes(n[bin.key], bin.secs),
               peek: peekText(inBin(cards, bin.key)[0], display) };
    });
  }

  /** 빈 묶음 한 줄 — 카드가 하나도 없거나 빈 묶음이 없으면 빈 글. */
  function emptyLine(cards) {
    var n = counts(cards);
    if (!(cards || []).length) return '';
    var empty = BINS.filter(function (bin) { return !n[bin.key]; }).map(function (bin) { return bin.title; });
    return empty.length ? empty.join(' · ') + ' 은 지금 없어요' : '';
  }

  /** 숫자 띠 — 어림은 묶음 줄 어림의 합 + AI 할 일 제안 어림(사람이 줄을 더해 보는 값과 같게). */
  function stripTotals(cards, actions) {
    var knowledge = (cards || []).length;
    var act = Math.max(0, Math.floor(Number(actions) || 0));
    var mins = binRows(cards, null).reduce(function (sum, row) { return sum + row.mins; }, 0) + minutes(act, ACTION_SECS);
    return { today: knowledge + act, minutes: mins, knowledge: knowledge, actions: act };
  }

  /** 주소의 묶음(?bin=names|…|rules|later — F07) — 아니면 빈 글(목록으로). */
  function fromQuery(search) {
    var match = /[?&]bin=([a-z]+)(?:&|$)/.exec(String(search || ''));
    return match && (KEYS.indexOf(match[1]) >= 0 || match[1] === LATER) ? match[1] : '';
  }

  /** 연 묶음을 적은 주소 — 닫으면 bin 이 빠진다. */
  function addressFor(page, bin) {
    return String(page || '') + '?tab=inbox' + (bin ? '&bin=' + bin : '');
  }

  /** 폰 나누기 — 폰에서 승인할 수 있는 카드(③ 질문은 폰에서도 정한다)와 'PC 에서 볼 것'(접어 둔 카드 포함 — F05). */
  function phoneSplit(cards, deferred, review) {
    var out = { phone: [], pc: [] };
    (cards || []).forEach(function (card) {
      var ok = binOf(card) === 'decide' || review.actionsFor(card.main, true).apply;
      (ok && !(deferred || {})[card.id] ? out.phone : out.pc).push(card);
    });
    return out;
  }

  /** 'PC 에서 볼 것' 요약 — 유형 이름(연결은 '연결')마다 수, 처음 나온 차례로. */
  function pcSummary(cards, display) {
    var order = [];
    var n = {};
    (cards || []).forEach(function (card) {
      var label = card.main && card.main.link ? '연결' : typeLabel(display, card.type);
      if (!n[label]) { n[label] = 0; order.push(label); }
      n[label] += 1;
    });
    return order.map(function (label) { return label + ' ' + n[label]; }).join(' · ');
  }

  /** 때 글 — 오늘이면 'HH:MM', 아니면 'MM-DD'(created_at 은 'YYYY-MM-DD HH:MM'). */
  function whenText(createdAt, today) {
    var match = /^(\d{4}-(\d{2}-\d{2})) (\d{2}:\d{2})/.exec(String(createdAt || ''));
    if (!match) return '';
    return match[1] === today ? match[3] : match[2];
  }

  /** 등급 A 한꺼번에 대상 — 연 묶음이면 그 묶음(표 묶음 · ③ · 나중에 보기는 없음), 목록이면 표 묶음과 ③ 을 뺀 카드. */
  function bulkScope(cards, bin, wide, deferred, review) {
    var tables = wide || [];
    if (bin && (tables.indexOf(bin) >= 0 || bin === 'decide' || bin === LATER)) return [];
    var pool = bin ? inBin(cards, bin) : (cards || []).filter(function (card) {
      return tables.indexOf(binOf(card)) < 0 && binOf(card) !== 'decide';
    });
    return review.bulkIds(pool.filter(function (card) { return !(deferred || {})[card.id]; }));
  }

  /** '체크한 줄 승인' 확인 창 글 — 한 번 누름에 여러 줄이 바로 바뀐다(F24). */
  function confirmTableText(n) {
    return '체크한 ' + n + '줄을 승인할까요? 승인하면 바로 바뀌어요(수정 기록은 남아요).';
  }

  /** 한꺼번에 승인 결과 글. */
  function doneText(done, failed) {
    return '승인 ' + done + '개' + (failed ? ' · 못 함 ' + failed + '개(카드로 하나씩 봐 주세요)' : '');
  }

  var api = { BINS: BINS, KEYS: KEYS, LATER: LATER, ACTION_SECS: ACTION_SECS, find: find, binOf: binOf, minutes: minutes,
              counts: counts, inBin: inBin, typeLabel: typeLabel, peekText: peekText, binRows: binRows, emptyLine: emptyLine,
              stripTotals: stripTotals, fromQuery: fromQuery, addressFor: addressFor, phoneSplit: phoneSplit,
              pcSummary: pcSummary, whenText: whenText, bulkScope: bulkScope, confirmTableText: confirmTableText,
              doneText: doneText };
  root.FOMS_DS_INBOX_VIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
