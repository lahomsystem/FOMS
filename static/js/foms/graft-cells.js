/**
 * 접목판 분홍 칸 채우기(설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 6절 · 판 ② ③ ④) — layout_scripts.html 이 칸 스위치가
 * 하나라도 전역으로 켜졌을 때만 싣는다.
 *
 * 템플릿은 빈 자리만 그린다(모두 hidden — 미리 그려 두는 조각에 사람마다 다른 값을 넣지 않는다):
 * - [data-graft-badge="pc|tablet"] 위 아이콘 줄 · 태블릿 레일의 회사 지식(+ [data-graft-count] 승인 대기 수 — 0 이면 수만 숨김)
 * - [data-graft-tile] 폰 '처리 대기'의 AI 제안 승인 대기 칸(수 + 할 일 이름 — 0 이면 칸째 숨김)
 * - [data-graft-slot="<주문 번호>"][data-graft-cell] '현재 작업' 칸 · 폰 목록 줄의 AI 제안 칩
 * 사람마다의 켬(on.pc · tablet · mobile)과 수는 GET /api/erp-actions/badge 한 번, 칩은 보이는 주문 번호를 모아
 * GET /api/erp-actions/open 한 번(100개씩)으로 채운다. 조각이 갈아 끼워지면(ERP 셸 · 폰 목록 더 읽기 · 태블릿 상세) 새 자리만
 * 다시 훑는다 — 이미 물은 주문은 다시 묻지 않는다.
 * - 태블릿 상세 'AI 제안' 상자([data-graft-box] — 서버가 그림): [승인] POST /approve · [거절] 까닭 칩 한 번 → POST /reject.
 * 볼 수 없는 사람(404) · 로그인 안 함(401)이면 아무것도 보이지 않는다. 글은 textContent 만 · 인라인 스타일 없음 ·
 * 전역 듣개는 한 번만(window.__FOMS_GRAFT_CELLS_BOUND).
 */
(function () {
  'use strict';

  if (window.__FOMS_GRAFT_CELLS_BOUND) return;
  window.__FOMS_GRAFT_CELLS_BOUND = true;

  var API = '/api/erp-actions';
  var INBOX = '/brain?tab=inbox';
  var CHUNK = 100;
  var SLOT_SEL = '[data-graft-badge], [data-graft-tile], [data-graft-slot]';
  var badge = null;          // GET /badge 답(data) — 한 번만
  var badgeAsk = null;       // 묻는 중인 약속
  var known = {};            // 주문 번호 → /open 답 칸(없으면 null)
  var asking = {};           // 묻는 중인 주문 번호
  var scanTimer = 0;

  /** JSON 요청 — {ok, status, data, error}. 네트워크 · 꼴 오류도 정한 모양으로. */
  async function request(url, init) {
    try {
      var res = await fetch(url, Object.assign({ credentials: 'same-origin', headers: { Accept: 'application/json' } }, init || {}));
      var body = null;
      try { body = await res.json(); } catch (parseError) { return { ok: false, status: res.status, data: null, error: '답을 읽지 못했어요.' }; }
      if (!body || body.success !== true) {
        return { ok: false, status: res.status, data: (body && body.data) || null, error: (body && body.error) || '처리하지 못했어요.' };
      }
      return { ok: true, status: res.status, data: body.data, error: null };
    } catch (networkError) {
      return { ok: false, status: 0, data: null, error: '연결이 끊겼어요. 잠시 뒤 다시 해 주세요.' };
    }
  }

  function postJson(url, payload) {
    return request(url, { method: 'POST', body: JSON.stringify(payload || {}),
                          headers: { Accept: 'application/json', 'Content-Type': 'application/json' } });
  }

  function all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function on(cell) {
    return !!(badge && badge.on && badge.on[cell]);
  }

  function countText(n) {
    return n > 99 ? '99+' : String(n);
  }

  function setText(node, text) {
    if (node && node.textContent !== text) node.textContent = text;
  }

  /** 위 아이콘 · 레일(켜진 사람에게 아이콘, 수는 0 보다 클 때만) · 폰 칸(AI 제안이 0 이면 숨김). */
  function paintBadges() {
    if (!badge) return;
    var total = Math.max(0, Number(badge.total) || 0);
    var actions = Math.max(0, Number(badge.actions) || 0);
    all('[data-graft-badge]').forEach(function (node) {
      node.hidden = !on(node.getAttribute('data-graft-badge'));
      var count = node.querySelector('[data-graft-count]');
      if (count) { setText(count, countText(total)); count.hidden = total < 1; }
      var link = node.matches('a') ? node : node.querySelector('a');
      if (link) link.setAttribute('aria-label', '회사 지식 승인 대기 ' + total);
    });
    all('[data-graft-tile]').forEach(function (node) {
      node.hidden = !on('mobile') || actions < 1;
      setText(node.querySelector('[data-graft-count]'), countText(actions));
      setText(node.querySelector('[data-graft-labels]'), (badge.labels || []).join(' · '));
    });
  }

  async function loadBadge() {
    if (badge) return badge;
    if (!badgeAsk) {
      badgeAsk = request(API + '/badge').then(function (res) {
        badge = res.ok && res.data ? res.data : { on: {}, actions: 0, total: 0, labels: [] };
        return badge;
      });
    }
    return badgeAsk;
  }

  /** 칩 하나 채우기 — 제안이 없으면 숨긴 채. */
  function paintSlot(node) {
    var id = node.getAttribute('data-graft-slot');
    if (!Object.prototype.hasOwnProperty.call(known, id)) return;
    node.setAttribute('data-graft-done', '1');
    var item = known[id];
    if (!item) { node.hidden = true; return; }
    node.textContent = '';
    var mark = document.createElement('i');
    mark.className = 'fas fa-robot foms-graft-chip__icon';
    mark.setAttribute('aria-hidden', 'true');
    node.appendChild(mark);
    node.appendChild(document.createTextNode('AI 제안 · ' + (item.label || '')));
    node.setAttribute('href', INBOX + '&proposal=' + encodeURIComponent(item.id));
    node.setAttribute('title', (item.agent_label || 'AI') + ' 제안 — 승인 대기에서 보기');
    node.setAttribute('data-foms-erp-no-shell', '');
    node.setAttribute('data-gnav-ignore', '1');
    node.hidden = false;
  }

  /** 아직 안 채운 칩 자리. */
  function waiting() {
    return all('[data-graft-slot]').filter(function (node) { return !node.hasAttribute('data-graft-done'); });
  }

  /** 켜진 칸의 아직 안 채운 칩 — 모르는 주문 번호만 모아 100개씩 한 번. */
  async function fillSlots() {
    var slots = waiting().filter(function (node) {
      return on(node.getAttribute('data-graft-cell') || 'pc') && /^\d+$/.test(node.getAttribute('data-graft-slot') || '');
    });
    var ids = [];
    slots.forEach(function (node) {
      var id = node.getAttribute('data-graft-slot');
      if (!Object.prototype.hasOwnProperty.call(known, id) && !asking[id] && ids.indexOf(id) < 0) ids.push(id);
    });
    for (var i = 0; i < ids.length; i += CHUNK) {
      var part = ids.slice(i, i + CHUNK);
      part.forEach(function (id) { asking[id] = true; });
      var res = await request(API + '/open?order_ids=' + part.join(','));
      var items = (res.ok && res.data && res.data.items) || {};
      part.forEach(function (id) { known[id] = items[id] || null; delete asking[id]; });
    }
    waiting().forEach(paintSlot);
  }

  async function scan() {
    if (!document.querySelector(SLOT_SEL)) return;  // 자리가 없는 화면이면 묻지도 않는다
    await loadBadge();
    paintBadges();
    if (on('pc') || on('tablet') || on('mobile')) await fillSlots();
  }

  function scanSoon() {
    if (scanTimer) return;
    scanTimer = window.setTimeout(function () { scanTimer = 0; scan(); }, 150);
  }

  // ── 태블릿 상세 'AI 제안' 상자 ────────────────────────────────────────
  function boxStatus(box, text, isError) {
    var line = box.querySelector('[data-graft-status]');
    if (!line) return;
    line.textContent = text || '';
    line.classList.toggle('is-error', !!isError);
  }

  /** 결정이 끝난 상자 — 단추를 거두고, 그 주문 칩도 다시 묻게 한다. */
  function settled(box, text) {
    all('[data-graft-act], .foms-graft-box__acts a', box).forEach(function (b) { b.hidden = true; });
    var reasons = box.querySelector('[data-graft-reasons]');
    if (reasons) reasons.hidden = true;
    boxStatus(box, text, false);
    all('[data-graft-slot][data-graft-done]').forEach(function (node) {
      var item = known[node.getAttribute('data-graft-slot')];
      if (item && String(item.id) === box.getAttribute('data-graft-box')) { node.hidden = true; }
    });
    badge = null;
    badgeAsk = null;
    scanSoon();
  }

  async function approve(box, button) {
    var base = box.getAttribute('data-graft-base');
    button.disabled = true;
    boxStatus(box, '승인하는 중…', false);
    var res = await postJson(API + '/proposals/' + box.getAttribute('data-graft-box') + '/approve',
                             { base_version: /^\d+$/.test(base || '') ? Number(base) : null });
    button.disabled = false;
    if (res.ok) { settled(box, (res.data && res.data.message) || '승인했어요 — 실행됐어요.'); return; }
    var code = res.data && res.data.code;
    if (code === 'ACTION_BASE_CHANGED') { button.hidden = true; boxStatus(box, '제안 뒤 주문이 바뀌었어요 — 다시 봐 주세요', true); return; }
    if (code === 'ACTION_NOT_OPEN') { settled(box, res.error); return; }
    boxStatus(box, (res.data && res.data.reason) || res.error, true);
  }

  async function reject(box, button) {
    button.disabled = true;
    var res = await postJson(API + '/proposals/' + box.getAttribute('data-graft-box') + '/reject',
                             { code: button.getAttribute('data-graft-code') });
    button.disabled = false;
    if (res.ok) { settled(box, '거절했어요 — 같은 제안은 다시 오지 않아요.'); return; }
    boxStatus(box, res.error, true);
  }

  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest ? event.target.closest('[data-graft-act]') : null;
    var box = button ? button.closest('[data-graft-box]') : null;
    if (!box || button.disabled) return;
    event.preventDefault();
    event.stopPropagation();  // 상세 시트 · 줄 누름으로 번지지 않게
    var act = button.getAttribute('data-graft-act');
    if (act === 'approve') { approve(box, button); return; }
    if (act === 'reject') { reject(box, button); return; }
    if (act === 'reject-open') {
      var reasons = box.querySelector('[data-graft-reasons]');
      if (reasons) reasons.hidden = !reasons.hidden;
      button.setAttribute('aria-expanded', reasons && !reasons.hidden ? 'true' : 'false');
    }
  });

  // ── 다시 훑기: ERP 셸 조각 · 폰 목록 더 읽기 · 태블릿 상세 ────────────────
  document.addEventListener('foms:erp-shell-fragment-swapped', scanSoon);
  document.addEventListener('foms:main-content-swapped', scanSoon);
  function bringsSlot(node) {
    return node.nodeType === 1 && (node.matches(SLOT_SEL) || !!node.querySelector(SLOT_SEL));
  }

  if (window.MutationObserver) {  // 새 자리를 가져온 조각만 — 칸에 글을 쓰는 것으로는 다시 돌지 않는다
    new window.MutationObserver(function (records) {
      for (var i = 0; i < records.length; i += 1) {
        if (Array.prototype.some.call(records[i].addedNodes || [], bringsSlot)) { scanSoon(); return; }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  window.FOMS_GRAFT_CELLS = { scan: scan };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan, { once: true });
  else scan();
})();
