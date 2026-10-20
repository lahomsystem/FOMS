/**
 * PARTNER-FOMS 5-1: 협력사 새 주문 · 접수 확인 중 주문 화면의 입력 도우미 — 우리 주문 화면과 같은 모양.
 *
 * - 제품명 ▾: 우리 고르기 창(erp-spec-picker.js 의 ErpSpecPicker.openSingle)으로 우리 제품 목록 이름을 고른다.
 *   이름 목록은 서버가 [data-pp-product-names] 에 이름만 싣는다(단가 없음). 직접 입력도 그대로 된다.
 * - 주소 찾기: 우리 PC 주소 검색 창과 같은 칸(검색어 · 상세주소 · 결과 · 입력), 우리 서버 카카오 검색(/api/address/search).
 *   창 여닫기는 partner-shell.js(data-pp-sheet-open · data-pp-sheet-close · Esc).
 * 설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.4 · §17
 */
(function () {
  'use strict';

  function readNames() {
    var el = document.querySelector('[data-pp-product-names]');
    if (!el) return [];
    try {
      var list = JSON.parse(el.getAttribute('data-pp-product-names') || '[]');
      return Array.isArray(list) ? list.filter(function (n) { return typeof n === 'string' && n; }) : [];
    } catch (_) {
      return [];
    }
  }

  function bindProductPick(names) {
    var items = names.map(function (n) { return { value: n, text: n }; });
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-pp-product-pick]');
      if (!btn) return;
      ev.preventDefault();
      var wrap = btn.closest('.erp-calc-field');
      var input = wrap && wrap.querySelector('[data-k="product_name"]');
      if (!input || !window.ErpSpecPicker) return;
      window.ErpSpecPicker.openSingle({
        title: '제품 선택',
        anchor: wrap,
        current: input.value,
        topItems: items,
        onPick: function (value) {
          input.value = value;
          // partner-items-rail.js 가 왼쪽 목록 이름을 다시 그린다.
          input.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
    });
  }

  function resultRow(r, onPick) {
    var base = r.road_address_name || r.address_name || '-';
    var main = r.building_name ? base + ', ' + r.building_name : base;
    var sub = [r.building_name, r.region_3depth_name].filter(Boolean).join(' · ');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'list-group-item list-group-item-action';
    var title = document.createElement('div');
    title.className = 'fw-semibold';
    title.textContent = main;
    btn.appendChild(title);
    if (sub) {
      var note = document.createElement('div');
      note.className = 'small text-muted';
      note.textContent = sub;
      btn.appendChild(note);
    }
    btn.addEventListener('click', function () { onPick(btn, main); });
    return btn;
  }

  function bindAddress(modal) {
    var url = modal.getAttribute('data-pp-address-url');
    var target = document.getElementById(modal.getAttribute('data-pp-address-target'));
    var query = modal.querySelector('[data-pp-address-query]');
    var detail = modal.querySelector('[data-pp-address-detail]');
    var status = modal.querySelector('[data-pp-address-status]');
    var results = modal.querySelector('[data-pp-address-results]');
    var picked = '';
    if (!target || !query || !results) return;

    function pick(btn, value) {
      picked = value;
      Array.prototype.forEach.call(results.querySelectorAll('.list-group-item'), function (el) {
        el.classList.toggle('active', el === btn);
      });
    }

    async function search() {
      var q = query.value.trim();
      if (!q) return;
      picked = '';
      status.textContent = '검색 중…';
      results.innerHTML = '';
      try {
        var res = await fetch(url + '?' + new URLSearchParams({ q: q, size: '10' }).toString(), { credentials: 'same-origin' });
        var data = await res.json();
        if (!data || !data.success) {
          status.textContent = (data && data.message) || '주소를 찾지 못했습니다. 잠시 뒤 다시 해 주세요.';
          return;
        }
        var list = data.results || [];
        status.textContent = list.length
          ? list.length + '건 찾았습니다. 주소를 고르고 상세주소를 넣은 뒤 "입력"을 눌러 주세요.'
          : '찾은 주소가 없습니다. 검색어를 바꿔 보세요.';
        list.forEach(function (r) { results.appendChild(resultRow(r, pick)); });
      } catch (_) {
        status.textContent = '주소를 찾지 못했습니다. 잠시 뒤 다시 해 주세요.';
      }
    }

    function apply() {
      var more = detail ? detail.value.trim() : '';
      var full = picked ? (more ? picked + ' ' + more : picked) : more;
      if (!full) {
        status.textContent = '주소를 고르거나 상세주소를 넣어 주세요.';
        return;
      }
      target.value = full;
      target.dispatchEvent(new Event('input', { bubbles: true }));
      if (window.PartnerShell) window.PartnerShell.close(modal);
    }

    document.addEventListener('click', function (ev) {
      if (!ev.target.closest('[data-pp-sheet-open="' + modal.id + '"]')) return;
      picked = '';
      query.value = target.value;
      if (detail) detail.value = '';
      status.textContent = '';
      results.innerHTML = '';
      // partner-shell.js 가 창을 연 뒤 첫 칸(닫기 단추)에 둔 포커스를 검색어로 옮긴다.
      window.setTimeout(function () { query.focus(); }, 0);
    });
    // 창 바깥(어두운 곳)을 누르면 닫는다.
    modal.addEventListener('click', function (ev) {
      if (ev.target === modal && window.PartnerShell) window.PartnerShell.close(modal);
    });
    modal.querySelector('[data-pp-address-search]').addEventListener('click', search);
    modal.querySelector('[data-pp-address-apply]').addEventListener('click', apply);
    query.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter') return;
      ev.preventDefault();
      search();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var names = readNames();
    if (names.length) bindProductPick(names);
    var modal = document.querySelector('[data-pp-address]');
    if (modal) bindAddress(modal);
  });
})();
