/* 생산 파트 도면 카드 — 취소 창 미리 안내 + "창에 보인 대로만 된다"(사장님 2026-11-27, 설계서 2026-11-23 §4-8 덧붙임 · 덧붙임 둘).
 * 창 글 · 창 그리기(foms-production-parts-modal.js — FomsPartsModal) 뒤, 쓰기(foms-production-parts.js) 앞에 싣는다. FomsPartsModal 에 셋을 붙인다:
 *   cancelLine(pending, p, bodyFor) — [<파트> 시작 취소] · [<파트> 완료 취소] · [기본 취소] 창과 반장 고르기 창을 열 때 그 취소로 제작 시작도 같이
 *     취소되는지 서버에 묻고(GET cancel-preview — 한 장 쓰기를 쓰기 직전까지 그대로 돌린 답 run_cancelled) 참일 때만 첫 도면 줄 자리에 한 줄.
 *   seenCancel(pending, body) — 쓰기 몸에 "그 단추에 대해 창이 보여 준 것"을 싣는다(seen_cancel — 줄에 불린 단추만 true, 줄 없이 열린 창 ·
 *     답이 거짓 · 3초 넘김 · 답 실패는 모두 false). 서버는 실제 결과가 그와 다르면 아무것도 바꾸지 않고 409 CANCEL_NOTICE_STALE 로 멈춘다.
 *   staleCancel(pending, code, text) — 그 409 를 받으면 창을 닫지 않고 서버 글을 창 오류 줄에 보인 뒤 다시 물어 줄을 새 답으로 바꾼다(없어지거나
 *     나타남). 다시 묻는 동안만 실행을 잠근다. 저절로 다시 보내지 않는다(사람이 한 번 더 누르면 새로 본 값으로 나간다).
 * 판정은 서버만 한다 — 여기는 누름 이름(release · 고르기 창의 remove · 완료 취소/기본 취소 undo)만 고르고 조건은 적지 않는다.
 * 요청은 읽기(GET) 하나뿐이다. 쓰기는 foms-production-parts.js 의 send() 하나. 셸 조각 교체로 다시 실행된다 — 화면마다 한 번(.cancel). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var M = window.FomsPartsModal;
  if (!root || !M || !root.querySelector('[data-pp-modal]')) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.cancel === root) { return; }
  bound.cancel = root;

  // ── 취소 창 한 줄(사장님 2026-11-27 "창에도 미리 알리기" · "여기도 미리 알리기") — 그 취소로 제작 시작도 같이 취소될 때만, 첫 도면 줄과 같은 자리 ──
  // 창에 있는 취소 누름마다 묻고 참인 누름이 있으면 줄을 넣는다. 답이 올 때까지 실행을 잠그고(ASK_MS 뒤엔 줄 없이 연다) 늦은 답은 버린다.
  // 고르기 창은 어느 단추인지 말한다("[오재단 시작 취소]를 누르면 …" — 단추 글은 늘 '취소'로 끝나 토씨는 '를').
  var CANCEL_LINE = '이 주문에서 시작한 도면이 이것뿐이라 제작 시작도 같이 취소돼요.';
  var UNDO_LINE = '이 주문에서 작업한 도면이 이것뿐이라 제작 시작도 같이 취소돼요.';
  var ASKS = ['release', 'remove', 'undo'];
  var ASK_URL = '/api/production/part-marks/cancel-preview';
  var ASK_MS = 3000;
  var STALE = 'CANCEL_NOTICE_STALE'; // 창에 보인 것과 실제가 달라 서버가 멈춘 거절(409)
  function ask(body) {
    var qs = Object.keys(body).map(function (k) { return k + '=' + encodeURIComponent(body[k] == null ? '' : body[k]); }).join('&');
    try {
      return fetch(ASK_URL + '?' + qs, { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) { return !!(data && data.success === true && data.data && data.data.run_cancelled === true); })
        .catch(function () { return false; });
    } catch (e) { return Promise.resolve(false); }
  }
  function keyOf(action, target) { return action + ':' + (target == null ? '' : target); } // 고르기 창은 단추마다 따로(누름 + 고른 사람)
  function lineOf(st, hits) {
    if (!hits.length) { return ''; }
    return st.single ? (hits[0][0] === 'undo' ? UNDO_LINE : CANCEL_LINE)
      : hits.map(function (c) { return '[' + c[1] + ']'; }).join(' · ') + '를 누르면 제작 시작도 같이 취소돼요.';
  }
  // 한 번 묻기 — again = 거절(409) 뒤 다시 묻기(줄을 새 답으로 바꾼다 — 없으면 지운다). 창 글이 바뀌거나 닫히면(M.turn) 답을 버린다
  function round(pending, again) {
    var st = pending.cancel;
    var mine = M.turn();
    var open = true;
    function settle(hits) { // hits = 서버가 참이라 답한 누름
      if (!open || mine !== M.turn()) { return; }
      open = false;
      pending.locked = false;
      M.runBtn().removeAttribute('aria-disabled');
      st.seen = {};
      hits.forEach(function (c) { st.seen[keyOf(c[0], c[3])] = true; }); // 줄에 불린 단추만 '보였다'
      if (hits.length || again) { M.setText('[data-pp-modal-body]', lineOf(st, hits)); }
    }
    pending.locked = true;
    M.runBtn().setAttribute('aria-disabled', 'true');
    window.setTimeout(function () { settle([]); }, ASK_MS);
    Promise.all(st.asks.map(function (c) { return ask(st.bodyFor(c[0], c[3])); }))
      .then(function (list) { settle(st.asks.filter(function (c, i) { return list[i]; })); });
  }
  function cancelLine(pending, p, bodyFor) {
    var asks = (p.choices || [[pending.action, '', '', p.target]]).filter(function (c) { return ASKS.indexOf(c[0]) >= 0; });
    if (!asks.length) { return; }
    pending.cancel = { asks: asks, bodyFor: bodyFor, single: !p.choices, seen: {} };
    round(pending, false);
  }

  // ── 창에 보인 대로만 된다(사장님 2026-11-27 "설계대로 만들기") ──
  // 물은 창의 취소 누름에만 값을 싣는다(미리 보기 질의 · 다른 누름 · 다른 화면은 값 없음 — 서버가 지금 그대로 처리한다)
  function seenCancel(pending, body) {
    var st = pending.cancel;
    if (st && ASKS.indexOf(body.action) >= 0) { body.seen_cancel = st.seen[keyOf(body.action, body.target_user_id)] === true; }
  }
  // 거절(409 CANCEL_NOTICE_STALE) → 창 그대로 + 서버 글(다른 거절과 같은 오류 줄) + 다시 묻기. 받았으면 true(쓰는 쪽이 창을 [닫기] 하나로 바꾸지 않는다)
  function staleCancel(pending, code, text) {
    if (code !== STALE || !pending.cancel) { return false; }
    M.error(text);
    round(pending, true);
    return true;
  }

  M.cancelLine = cancelLine;
  M.seenCancel = seenCancel;
  M.staleCancel = staleCancel;
})();
