/* 생산 파트 도면 카드 — 다른 사람 표시 받아 오기. 설계서 §15.6 끝 '다른 사람 표시 받아 오기' · §15.4 GET 줄, P15-7.
 * 화면이 보이고(document.visibilityState) 연결돼 있을 때만 30초마다 GET /api/production/part-marks?order_ids=…&since=…
 * → since 뒤 바뀐 표시 줄만 받아 바뀐 카드만 그 자리에서 고친다(칸 숫자도 같이 — 고치기는 parts.js 의 window.FomsPartsCards).
 * since 는 서버 시각만 쓴다: 첫 값 = 서버가 그린 시각(data-pp-since), 그다음 = 응답의 server_time. 기기 시계는 쓰지 않는다.
 * 내 확인 창에 있거나 저장 중인 카드는 건너뛴다(그 판은 since 를 옮기지 않아 다음 번에 다시 받는다).
 * 읽기 전용 직원도 싣는다(보기만 — 이 파일엔 쓰기 요청이 없다). 셸 조각 교체로 다시 실행된다(11-14): 화면마다 한 번
 * (window.__FOMS_PROD_PARTS_BOUND.sync = 지금 화면), 30초 타이머는 문서에 한 번(.syncTimer) 달고 지금 화면의 받기(.syncTick)를 부른다.
 * 화면이 문서에서 빠지면(다른 탭으로 셸 이동) 받지 않는다. 날을 받아 끼운 장의 카드도 화면 안이라 같이 받는다.
 * 2026-11-23: 받은 줄의 맡은 때 · 바뀐 기록 칸도 카드에 싣는다(고치기가 그린다). 까닭 말풍선이 열린 카드도 건너뛴다(held).
 * 2공장(2026-11-23 §4-13): 남의 공장 카드([data-pp-elsewhere] — 누름 없음)도 같이 받아 글 한 줄 · 다른 파트 줄만 고친다.
 * 2026-11-25 multi-holder: 받은 줄에 작업하는 사람 칸(mark.crew — 이름 줄 · 내 몫, 서버 글)이 실린다. 같은 표시인지는 사람 · 완료 표지(sig)까지 견준다.
 * 2026-11-26(비평 C06): 응답의 주문마다 지금 막힘(data.blocks — 보류 · 도면 고치는 중 · 생산 단계 아님, 서버 sync_blocks)으로 그 주문 카드를
 * 이미 있는 막힘 칸으로 다시 그린다(그 장만 막힘이 먼저 · 풀리면 단추가 돌아온다 — FomsPartsCards.block). 받을 때마다 'foms:prod-parts-synced'
 * 를 쏴 머리 줄 받은 때 글 · 점(foms-production-home.js)을 새로 한다. 거절(409 보류 · 고치는 중 · 생산 단계 아님)이면 parts.js 가 바로 부른다
 * (syncTick(true) — 그때는 확인 창에 걸린 카드도 막힘으로, 30초 받아 오기는 표시 줄처럼 건너뛴다).
 * 2026-11-28 흐름(설계서 production-my-steps-flow §3-2 · §3-4): 카드 파트는 카드 data-part(파트가 섞인 '내 공정' · '작업 중' — 없으면 판 파트) —
 * 다른 파트 줄의 변화가 이 카드를 덮지 않게 장(key) + 파트로 맞춘다. data-pp-orders(내 카드가 빠진 날짜 판 · '내 공정')의 주문도 같이 묻고,
 * 고친 카드 · 화면에 카드가 없는 줄은 flow.js(bound.flowSynced · flowOrphan)에 알린다 — "내 것이 됐다 / 아니게 됐다"면 그 화면을 다시 받는다. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var holder = root && root.querySelector('[data-pp-since]');
  if (!root || !holder) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.sync === root) { return; }
  bound.sync = root;

  var SYNC_URL = '/api/production/part-marks';
  var SYNC_EVERY_MS = 30000; // 30초 — 한 태블릿 시간당 120번(한도 1,200 의 10%)
  var MAX_IDS = 300; // 서버 상한과 같다(넘으면 나눠 부른다)
  var since = holder.getAttribute('data-pp-since') || '';
  var running = false;

  function safeJsonParse(value, fallback) {
    try {
      var text = String(value || '').trim();
      return text ? JSON.parse(text) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function toArr(list) { return [].slice.call(list || []); }
  var cfg = safeJsonParse(holder.getAttribute('data-foms-parts-config'), {}) || {};

  function canSync() {
    return document.visibilityState === 'visible' && navigator.onLine !== false && !!since && document.contains(root);
  }
  function orderIds() {
    var seen = {};
    var ids = [];
    function add(id) { if (id && !seen[id]) { seen[id] = true; ids.push(id); } }
    toArr(root.querySelectorAll('[data-pp-card], [data-pp-elsewhere]')).forEach(function (card) { add(card.getAttribute('data-order-id')); });
    toArr(root.querySelectorAll('[data-pp-orders]')).forEach(function (n) { (n.getAttribute('data-pp-orders') || '').split(' ').forEach(add); });
    return ids;
  }
  function chunks(ids) {
    var out = [];
    for (var i = 0; i < ids.length; i += MAX_IDS) { out.push(ids.slice(i, i + MAX_IDS)); }
    return out;
  }

  // 한 묶음 받기 — 성공이면 data({marks, blocks, server_time}), 아니면 null(그 판은 버리고 since 를 그대로 둔다)
  function fetchChunk(ids, from) {
    var url = SYNC_URL + '?order_ids=' + ids.join(',') + '&since=' + encodeURIComponent(from);
    try {
      return fetch(url, { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (body) {
          var data = body && body.success === true ? body.data : null;
          return data && Array.isArray(data.marks) && typeof data.server_time === 'string' ? data : null;
        })
        .catch(function () { return null; });
    } catch (e) {
      return Promise.resolve(null);
    }
  }

  // 화면 카드가 이미 그 표시면 건너뛴다(내가 쓴 줄 · 겹쳐 받은 줄) — 같이 작업하는 사람 · 사람마다 완료(sig)까지
  function sameMark(card, mark) {
    var cr = mark.crew || {};
    var seen = safeJsonParse(card.getAttribute('data-pp-crew'), {}) || {};
    return card.getAttribute('data-state') === (mark.state || 'none') &&
      card.getAttribute('data-picked-name') === (mark.picked_by_name || '') &&
      card.getAttribute('data-done-name') === (mark.done_by_name || '') &&
      (seen.sig || '') === (cr.sig || '') && (seen.me || 'none') === (cr.me || 'none');
  }
  // 다른 파트 한 줄의 낱말 하나(낱말 · 색은 서버가 준 word · tone — 화면이 다시 짓지 않는다)
  function setOther(card, mark) {
    var span = card.querySelector('[data-pp-other="' + mark.part + '"]');
    if (!span || !mark.tone || span.classList.contains('pp-w-' + mark.tone)) { return false; }
    var label = span.querySelector('i');
    span.className = 'fph-by pp-w-' + mark.tone;
    span.textContent = '';
    if (label) { span.appendChild(label); }
    span.appendChild(document.createTextNode(' ' + (mark.word || '')));
    return true;
  }
  // 남의 공장 카드의 글 한 줄 — 서버 factory_scope.elsewhere_line 과 같은 글("이시영 · 김재단 작업 중" · "엣지 완료 · 최가은" · "기본 · 김재단" ·
  // "미정"). 이름 줄은 서버가 준 mark.crew(who · done)만 쓴다(multi-holder §8-2 16)
  function elsewhereLine(m) {
    var cr = m.crew || {};
    var who = cr.who || m.picked_by_name;
    if (m.state === 'need') { return who ? who + ' 작업 중' : '작업 중'; }
    if (m.state !== 'done' && m.state !== 'basic') { return '미정'; }
    var head = m.state === 'done' ? (cfg.label || '') + ' 완료' : (cfg.basic || {}).word || '기본'; // 조립 판 = "조립 없음"(서버 설정 글)
    var done = (m.state === 'done' && cr.done) || m.done_by_name;
    return done ? head + ' · ' + done : head;
  }
  function applyElsewhere(mark) {
    toArr(root.querySelectorAll('[data-pp-elsewhere][data-order-id="' + mark.order_id + '"]')).forEach(function (card) {
      if (card.getAttribute('data-key') !== mark.drawing_key) { return; }
      var text = card.querySelector('[data-pp-elsewhere-text]');
      if (mark.part !== cfg.part) { setOther(card, mark); } else if (text) { text.textContent = elsewhereLine(mark); }
    });
  }
  // 받은 줄 → 바뀐 카드만 고친다. 건너뛴 카드가 있으면 false(since 를 옮기지 않는다)
  function applyMarks(marks) {
    var cards = window.FomsPartsCards;
    if (!cards) { return false; }
    var complete = true;
    marks.forEach(function (mark) {
      applyElsewhere(mark);
      var found = cards.find(mark.order_id, mark.drawing_key);
      if (!found.length && bound.flowOrphan) { bound.flowOrphan(mark); }
      found.forEach(function (card) {
        if (cards.held(card)) { complete = false; return; }
        if (mark.part !== (card.getAttribute('data-part') || cfg.part)) {
          if (setOther(card, mark)) {
            if (window.FomsPartsClaim) { window.FomsPartsClaim.recheck(card); } // 검수 판: 앞 파트가 다 완료되면 저절로 열림(§4-6)
            document.dispatchEvent(new CustomEvent('foms:part-card-updated', { detail: { key: mark.drawing_key } }));
          }
          return;
        }
        if (!sameMark(card, mark)) { cards.apply(card, mark); if (bound.flowSynced) { bound.flowSynced(card, mark); } }
      });
    });
    return complete;
  }

  // 주문마다 지금 막힘 → 그 주문 카드(그 장만 막힘 keys 가 먼저, 없으면 주문 통째 all, 둘 다 없으면 막힘을 걷는다). 확인 창 · 저장 중 ·
  // 말풍선 카드는 표시 줄처럼 건너뛰고 false(그 판은 since 를 안 옮겨 다음 번에 다시). force = 거절(409) 바로 뒤 — 저장이 끝난 카드라 그린다
  function applyBlocks(blocks, force) {
    var cards = window.FomsPartsCards;
    if (!cards || !cards.block) { return true; }
    var complete = true;
    Object.keys(blocks).forEach(function (id) {
      var b = blocks[id] || {};
      cards.find(id).forEach(function (card) {
        if (!force && cards.held(card)) { complete = false; return; }
        cards.block(card, (b.keys || {})[card.getAttribute('data-key')] || b.all || null);
      });
    });
    return complete;
  }

  function tick(force) {
    if (running || !canSync()) { return; }
    var ids = orderIds();
    if (!ids.length) { return; }
    running = true;
    var from = since;
    Promise.all(chunks(ids).map(function (part) { return fetchChunk(part, from); })).then(function (results) {
      if (results.some(function (r) { return !r; })) { return; } // 하나라도 못 받으면 다음 번에 같은 since 로
      var marks = [];
      var blocks = {};
      var next = results[0].server_time;
      results.forEach(function (r) {
        marks = marks.concat(r.marks);
        Object.keys(r.blocks || {}).forEach(function (id) { blocks[id] = r.blocks[id]; });
        if (r.server_time < next) { next = r.server_time; } // 나눠 받으면 가장 이른 서버 시각부터 다음에
      });
      var settled = applyBlocks(blocks, force === true); // 막힘 먼저 — 받은 표시를 그릴 때 새 막힘을 읽는다
      if (applyMarks(marks) && settled) { since = next; }
      document.dispatchEvent(new CustomEvent('foms:prod-parts-synced'));
    }).then(function () { running = false; }, function () { running = false; });
  }

  bound.syncTick = tick;
  if (!bound.syncTimer) {
    bound.syncTimer = window.setInterval(function () { if (bound.syncTick) { bound.syncTick(); } }, SYNC_EVERY_MS);
  }
})();
