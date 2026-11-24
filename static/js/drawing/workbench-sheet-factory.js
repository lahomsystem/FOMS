/**
 * 도면 작업실 실행판 — 장의 공장 고르기(설계서 docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md §8-5).
 *
 * - '현재 버전' 타일마다 [1공장 | 2공장](직접 올린 파일도) · 목록 머리 "1공장 3장 · 2공장 2장"(2공장 장이 있을 때만).
 * - 전달 창 보낼 시트 칸: 시트마다 [1공장 | 2공장] · 한 줄 "보낼 도면 5장 — 1공장 3장 · 2공장 2장"(고른 시트에 2공장이 있을 때만).
 * - 누르면 POST /api/orders/<id>/drawing/sheet-factory 로 바로 저장(sheet-factory.js). 생산에 내려간 장이면 서버가 물어 와
 *   확인 창을, 막히면 서버 글 그대로 창에 보이고 고르기는 원래 값으로 둔다.
 * - 저장되면 주문 버전이 +1 — 같은 화면이 If-Match 로 쓰는 값(data-mutation-version, 확정 뒤 제품 취소 창)을 응답 값으로 맞춘다.
 * 고르는 칸은 서버가 도면팀 누구나 · 관리자에게만 그린다. 조각 화면이 다시 실행해도 한 번만 묶는다.
 */
(function () {
  'use strict';
  if (window.__DW_SHEET_FACTORY_BOUND) return;
  window.__DW_SHEET_FACTORY_BOUND = true;

  var SEL = '[data-dsf-sel]';
  var busy = false;

  function SF() { return window.FomsSheetFactory; }
  function pressed(group) {
    var on = group.querySelector('[data-fac][aria-pressed="true"]');
    return on ? Number(on.getAttribute('data-fac')) : 1;
  }
  function setPressed(group, factory) {
    Array.prototype.forEach.call(group.querySelectorAll('[data-fac]'), function (btn) {
      btn.setAttribute('aria-pressed', Number(btn.getAttribute('data-fac')) === factory ? 'true' : 'false');
    });
  }
  function setBusy(on) {
    busy = on;
    Array.prototype.forEach.call(document.querySelectorAll(SEL + ' [data-fac]'), function (btn) { btn.disabled = on; });
  }

  function countText(counts) {
    var parts = [];
    if (counts[1]) parts.push('1공장 ' + counts[1] + '장');
    if (counts[2]) parts.push('2공장 ' + counts[2] + '장');
    return parts.join(' · ');
  }

  /** '현재 버전' 머리 줄 — 타일의 고른 값으로 다시 센다(2공장이 없으면 숨김 = 지금 모습). */
  function syncSplit() {
    var el = document.querySelector('[data-dsf-split]');
    if (!el) return;
    var counts = { 1: 0, 2: 0 };
    Array.prototype.forEach.call(document.querySelectorAll(SEL + '[data-key]'), function (g) { counts[pressed(g)] += 1; });
    el.textContent = ' · ' + countText(counts);
    el.hidden = !counts[2];
  }

  /** 전달 창 한 줄 — 골라 둔(체크된) 시트만 센다. */
  function syncSend() {
    var el = document.querySelector('[data-dsf-send]');
    if (!el) return;
    var counts = { 1: 0, 2: 0 };
    var total = 0;
    Array.prototype.forEach.call(document.querySelectorAll('.dw-pending-checkbox'), function (box) {
      if (!box.checked) return;
      var col = box.closest('.col-6') || box.parentNode;
      var group = col && col.querySelector(SEL);
      var chip = col && col.querySelector('.dsf-chip');
      counts[group ? pressed(group) : (chip ? 2 : 1)] += 1;
      total += 1;
    });
    el.textContent = '보낼 도면 ' + total + '장 — ' + countText(counts);
    el.hidden = !counts[2];
  }

  /** 서버가 돌려준 표(2공장만 열쇠)로 화면의 모든 고르는 칸을 맞춘다 — 같은 시트가 타일과 보낼 칸에 같이 있어도. */
  function applyTables(data) {
    var byKey = data.factory_by_key || {};
    var bySheet = data.factory_by_sheet || {};
    Array.prototype.forEach.call(document.querySelectorAll(SEL), function (g) {
      var key = g.getAttribute('data-key');
      var sid = g.getAttribute('data-sheet-id');
      setPressed(g, Number(key ? byKey[key] : bySheet[sid]) === 2 ? 2 : 1);
    });
    syncSplit();
    syncSend();
  }

  /** 같은 화면에서 If-Match 로 보내는 주문 버전(확정 뒤 제품 취소 창 drawing-item-cancel.js)을 새 값으로. */
  function syncVersion(orderId, version) {
    if (version == null || version === '') return;
    Array.prototype.forEach.call(document.querySelectorAll('[data-mutation-version]'), function (el) {
      if (String(el.getAttribute('data-order-id') || '') === String(orderId)) el.setAttribute('data-mutation-version', String(version));
    });
  }

  function send(group, to, btn) {
    var item = group.getAttribute('data-key') ? { key: group.getAttribute('data-key') } : { sheet_id: group.getAttribute('data-sheet-id') };
    item.factory = to;
    var orderId = group.getAttribute('data-order-id');
    SF().move({
      orderId: orderId, item: item, to: to, sub: group.getAttribute('data-label') || '', anchor: group,
      // 기다리는 동안 단추가 잠겨 초점이 빠진다 — 끝나면 누른 단추로 돌려놓는다
      before: function (on) { setBusy(on); if (!on && btn && btn.focus) btn.focus(); },
      after: function (res) { syncVersion(orderId, res.data.mutation_version); applyTables(res.data); }
    });
  }

  function onClick(ev) {
    var btn = ev.target.closest ? ev.target.closest(SEL + ' [data-fac]') : null;
    if (!btn || busy || !SF()) return;
    var group = btn.closest(SEL);
    var to = Number(btn.getAttribute('data-fac'));
    if (pressed(group) === to) return;
    ev.preventDefault();
    send(group, to, btn);
  }

  document.addEventListener('click', onClick);
  // 보낼 시트 체크 · [전체 해제]가 바뀌면 한 줄을 다시 센다(전체 해제는 체크를 코드로 바꿔 change 가 안 난다 — 누른 뒤 센다).
  document.addEventListener('change', function (ev) {
    if (ev.target && ev.target.classList && ev.target.classList.contains('dw-pending-checkbox')) syncSend();
  });
  document.addEventListener('click', function (ev) {
    if (ev.target && ev.target.closest && ev.target.closest('#dw-pending-select-toggle')) window.setTimeout(syncSend, 0);
  });
})();
