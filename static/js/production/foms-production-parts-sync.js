/* 생산 파트 도면 카드 — 다른 사람 표시 받아 오기. 설계서 §15.6 끝 '다른 사람 표시 받아 오기' · §15.4 GET 줄, P15-7.
 * 화면이 보이고(document.visibilityState) 연결돼 있을 때만 30초마다 GET /api/production/part-marks?order_ids=…&since=…
 * → since 뒤 바뀐 표시 줄만 받아 바뀐 카드만 그 자리에서 고친다(칸 숫자도 같이 — 고치기는 parts.js 의 window.FomsPartsCards).
 * since 는 서버 시각만 쓴다: 첫 값 = 서버가 그린 시각(data-pp-since), 그다음 = 응답의 server_time. 기기 시계는 쓰지 않는다.
 * 내 확인 창에 있거나 저장 중인 카드는 건너뛴다(그 판은 since 를 옮기지 않아 다음 번에 다시 받는다).
 * 읽기 전용 직원도 싣는다(보기만 — 이 파일엔 쓰기 요청이 없다). 셸 조각 교체로 다시 실행된다(11-14): 화면마다 한 번
 * (window.__FOMS_PROD_PARTS_BOUND.sync = 지금 화면), 30초 타이머는 문서에 한 번(.syncTimer) 달고 지금 화면의 받기(.syncTick)를 부른다.
 * 화면이 문서에서 빠지면(다른 탭으로 셸 이동) 받지 않는다. 날을 받아 끼운 장의 카드도 화면 안이라 같이 받는다. */
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
    toArr(root.querySelectorAll('[data-pp-card]')).forEach(function (card) {
      var id = card.getAttribute('data-order-id');
      if (id && !seen[id]) { seen[id] = true; ids.push(id); }
    });
    return ids;
  }
  function chunks(ids) {
    var out = [];
    for (var i = 0; i < ids.length; i += MAX_IDS) { out.push(ids.slice(i, i + MAX_IDS)); }
    return out;
  }

  // 한 묶음 받기 — 성공이면 data({marks, server_time}), 아니면 null(그 판은 버리고 since 를 그대로 둔다)
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

  // 화면 카드가 이미 그 표시면 건너뛴다(내가 쓴 줄 · 겹쳐 받은 줄)
  function sameMark(card, mark) {
    var me = String(cfg.me_id);
    var pickedMe = mark.picked_by_user_id != null && String(mark.picked_by_user_id) === me ? '1' : '0';
    var doneMe = mark.done_by_user_id != null && String(mark.done_by_user_id) === me ? '1' : '0';
    return card.getAttribute('data-state') === (mark.state || 'none') &&
      card.getAttribute('data-picked-name') === (mark.picked_by_name || '') &&
      card.getAttribute('data-done-name') === (mark.done_by_name || '') &&
      card.getAttribute('data-picked-me') === pickedMe && card.getAttribute('data-done-me') === doneMe;
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
  // 받은 줄 → 바뀐 카드만 고친다. 건너뛴 카드가 있으면 false(since 를 옮기지 않는다)
  function applyMarks(marks) {
    var cards = window.FomsPartsCards;
    if (!cards) { return false; }
    var complete = true;
    marks.forEach(function (mark) {
      cards.find(mark.order_id, mark.drawing_key).forEach(function (card) {
        if (cards.held(card)) { complete = false; return; }
        if (mark.part !== cfg.part) {
          if (setOther(card, mark)) {
            document.dispatchEvent(new CustomEvent('foms:part-card-updated', { detail: { key: mark.drawing_key } }));
          }
          return;
        }
        if (!sameMark(card, mark)) { cards.apply(card, mark); }
      });
    });
    return complete;
  }

  function tick() {
    if (running || !canSync()) { return; }
    var ids = orderIds();
    if (!ids.length) { return; }
    running = true;
    var from = since;
    Promise.all(chunks(ids).map(function (part) { return fetchChunk(part, from); })).then(function (results) {
      if (results.some(function (r) { return !r; })) { return; } // 하나라도 못 받으면 다음 번에 같은 since 로
      var marks = [];
      var next = results[0].server_time;
      results.forEach(function (r) {
        marks = marks.concat(r.marks);
        if (r.server_time < next) { next = r.server_time; } // 나눠 받으면 가장 이른 서버 시각부터 다음에
      });
      if (applyMarks(marks)) { since = next; }
    }).then(function () { running = false; }, function () { running = false; });
  }

  bound.syncTick = tick;
  if (!bound.syncTimer) {
    bound.syncTimer = window.setInterval(function () { if (bound.syncTick) { bound.syncTick(); } }, SYNC_EVERY_MS);
  }
})();
