/* 생산 파트 도면 카드 — 담당 바꾸기 "누구에게 줄까요?" 창(설계서 2026-11-28 흐름 셋 §1-2 · §1-3, 사장님 "누구에게 줄지 고르고").
 * 반장 · 관리자의 고르기 창 [담당 바꾸기 ›]는 바로 실행하지 않고 이 창을 연다(예전엔 묻지 않고 누른 반장이 담당이 됐다).
 *   plan(card, seat) — 창 글. seat = 자리를 내줄 사람 id(고르기 창의 단추 · "누구와 담당을 바꿀까요?"에서 고른 사람), 없으면 아직 작업 중인 한 사람.
 *     안내 한 줄 "김재단이 11/28 08:10부터 작업 중인 도면이에요."(지금 글 — modal.heldSince) · 실행 단추 [담당 바꾸기]는 사람을 고르기 전에는
 *     잠긴다. '나'를 미리 골라 두지 않는다.
 *   load(pending, card) — 창이 열릴 때 한 번 GET /api/production/part-marks/receivers(같은 파트 · 같은 공장 · 켜진 계정 + 나, 이미 든 사람 뺌).
 *     사람 단추 글 · 고르면 보일 바뀔 줄("담당 김재단 → 담당 오재단")은 서버가 준 글 그대로다(이름 줄을 여기서 짓지 않는다). 맨 앞은 늘
 *     '나' — 단추 글 "나 (박반장)". 답이 올 때까지 "받을 사람을 불러오는 중…", 3초 안에 못 받으면 "받을 사람을 못 불러왔어요. 닫고 다시 눌러 주세요."
 *     창 글이 바뀌거나 닫히면(M.turn) 늦은 답은 버린다. 받을 사람이 '나'뿐이면 "이 도면을 받을 수 있는 다른 사람이 없어요."
 * 요청은 읽기(GET) 하나뿐이다. 쓰기는 foms-production-parts.js 의 send() 하나 — 고른 사람은 몸의 to_user_id 로 나간다(사람 단추 data-pp-give).
 * 창 글 · 창 그리기(foms-production-parts-modal.js) · 여러 명 칸(-crew.js) 뒤, 쓰기(-parts.js) 앞에 싣는다. 셸 조각 교체로 다시 실행된다 —
 * 화면마다 한 번(window.__FOMS_PROD_PARTS_BOUND.give). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var board = window.FomsPartsBoard;
  var M = window.FomsPartsModal;
  var modal = root && root.querySelector('[data-pp-modal]');
  if (!root || !board || !M || !modal) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.give === root || board.root !== root) { return; }
  bound.give = root;

  var cfg = board.cfg || {};
  var ME = String(cfg.me_id);
  var ASK_URL = '/api/production/part-marks/receivers';
  var ASK_MS = 3000;
  var WAIT = '받을 사람을 불러오는 중…';
  var FAILED = '받을 사람을 못 불러왔어요. 닫고 다시 눌러 주세요.';
  var ALONE = '이 도면을 받을 수 있는 다른 사람이 없어요.';
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function crewOf(card) { var c = window.FomsPartsCrew; return (c && card && c.of(card)) || {}; }

  // ── 창 글 ──
  function plan(card, seat) {
    var cr = crewOf(card);
    var left = (cr.people || []).filter(function (p) { return !p.done && String(p.uid) !== ME; });
    var from = left.filter(function (p) { return seat != null && String(p.uid) === String(seat); })[0] || (left.length === 1 ? left[0] : null);
    return { title: '누구에게 줄까요?', line: '담당 ' + (cr.who || attr(card, 'data-picked-name') || '미정'), run: '담당 바꾸기', tone: 'taken',
      locked: true, target: from ? from.uid : null, note: from ? M.heldSince(null, from.subj, from.at) : M.heldSince(card) };
  }

  // ── 사람 단추(하나만 고름 — 고르면 parts.js 가 pending.to 에 담고 창(modal.pick)이 바뀔 줄 · 실행 단추를 연다) ──
  function render(people) {
    var box = modal.querySelector('[data-pp-modal-choices]');
    box.textContent = '';
    box.className = 'pp-mchoices pp-mchoices--who pp-mchoices--give';
    box.setAttribute('aria-label', '누구에게 줄지');
    people.forEach(function (p) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'foms-prod-change-modal__btn pp-mbtn pp-mwho';
      b.setAttribute('data-pp-who', String(p.user_id));
      b.setAttribute('data-pp-give', '');
      b.setAttribute('data-pp-line', p.line || '');
      b.setAttribute('aria-pressed', 'false');
      b.textContent = p.me ? '나 (' + p.name + ')' : p.name;
      box.appendChild(b);
    });
    box.hidden = !people.length;
    M.setText('[data-pp-modal-body]', people.some(function (p) { return !p.me; }) ? '' : ALONE);
  }

  // ── 목록 받기 — 창을 열 때 한 번 ──
  function load(pending, card) {
    var mine = M.turn();
    var open = true;
    function settle(people, text) { // 늦은 답 · 닫힌 창 · 글이 바뀐 창은 버린다
      if (!open || mine !== M.turn()) { return; }
      open = false;
      if (people) { render(people); return; }
      M.setText('[data-pp-modal-body]', '');
      M.error(text || FAILED);
    }
    var query = { order_id: attr(card, 'data-order-id'), drawing_key: attr(card, 'data-key'), part: cfg.part || '' };
    if (pending.target != null) { query.target_user_id = pending.target; }
    var qs = Object.keys(query).map(function (k) { return k + '=' + encodeURIComponent(query[k]); }).join('&');
    M.setText('[data-pp-modal-body]', WAIT);
    window.setTimeout(function () { settle(null, FAILED); }, ASK_MS);
    try {
      fetch(ASK_URL + '?' + qs, { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.json().catch(function () { return null; }); })
        .then(function (body) {
          var ok = !!body && body.success === true && !!body.data && Array.isArray(body.data.people);
          settle(ok ? body.data.people : null, body && body.error);
        })
        .catch(function () { settle(null, FAILED); });
    } catch (e) { settle(null, FAILED); }
  }

  window.FomsPartsGive = { plan: plan, load: load };
})();
