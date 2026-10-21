/**
 * PARTNER-FOMS 3-1: 협력사 주문 화면 — 탭(주문 · 도면 · 완공 사진)과 접수 확인 중 품목 저장.
 *
 * 서버 계약: PUT /api/partner/orders/<id>/items (JSON {items}) → {success, data:{order_id, item_count, uids}, error}
 *            PUT /api/partner/orders/<id>/info (JSON 고객 · 주소 · 실측 · 희망 시공일, §18) → {success, data, error}
 *            품목 사진은 저장 뒤 POST /api/partner/orders/<id>/files 에 item_index 를 붙여 올린다(partner-portal.js).
 * 단계 버튼(아래 고정 줄)의 data-pp-goto-tab 은 해당 탭을 연다.
 * 설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.3 · §4-4 · §12
 */
(function () {
  'use strict';

  function showTab(name) {
    var found = false;
    Array.prototype.forEach.call(document.querySelectorAll('[data-pp-tab-panel]'), function (panel) {
      var on = panel.getAttribute('data-pp-tab-panel') === name;
      panel.hidden = !on;
      found = found || on;
    });
    if (!found) return;
    Array.prototype.forEach.call(document.querySelectorAll('[data-pp-tab]'), function (btn) {
      var on = btn.getAttribute('data-pp-tab') === name;
      btn.classList.toggle('active', on);
      btn.classList.toggle('is-active', on);  // 휴대폰 칩 줄 탭(우리 foms-chip)
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
  }

  function bindTabs() {
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-pp-tab], [data-pp-goto-tab]');
      if (!btn || btn.disabled) return;
      var name = btn.getAttribute('data-pp-tab') || btn.getAttribute('data-pp-goto-tab');
      showTab(name);
      if (btn.hasAttribute('data-pp-goto-tab')) {
        var panel = document.querySelector('[data-pp-tab-panel="' + name + '"]');
        if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
    var hash = (window.location.hash || '').replace('#', '');
    var first = document.querySelector('[data-pp-tabs]');
    showTab(document.querySelector('[data-pp-tab-panel="' + hash + '"]') ? hash : (first && first.getAttribute('data-pp-tabs')) || 'order');
  }

  async function putJson(url, body) {
    var resp = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'same-origin',
    });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) throw new Error((data && data.error) || '저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
    return data.data;
  }

  function bindItemsSave(button) {
    var container = document.querySelector('[data-pp-items]');
    var portal = window.PartnerPortal;
    if (!container || !window.PartnerItems || !portal) return;
    window.PartnerItems.init(container, document.querySelectorAll('[data-pp-add-item]'));
    var busy = false;
    button.addEventListener('click', async function () {
      if (busy) return;
      var collected = window.PartnerItems.collect(container);
      if (!collected.items.length) { portal.setStatus('제품명을 넣은 제품 항목이 하나 이상 있어야 합니다.', true); return; }
      if (collected.orphanPhotos) { portal.setStatus('제품명이 없는 항목에 고른 사진이 있습니다. 제품명을 넣어 주세요.', true); return; }
      if (!window.confirm('품목을 이대로 저장할까요? 저희 담당자에게 고친 내용이 알려집니다.')) return;
      busy = true;
      button.disabled = true;
      portal.setStatus('저장하는 중…');
      try {
        await putJson(button.getAttribute('data-pp-items-url'), { items: collected.items });
        var failed = await portal.uploadFiles(document.createElement('form'), button.getAttribute('data-pp-upload-url'), collected.photoJobs);
        if (failed.length) window.alert('품목은 저장됐지만 일부 사진을 올리지 못했습니다.\n\n' + failed.join('\n'));
        window.location.reload();
      } catch (err) {
        portal.setStatus(err.message, true);
        busy = false;
        button.disabled = false;
      }
    });
  }

  var INFO_KEYS = ['customer_name', 'customer_phone', 'address', 'measured_on', 'measured_time'];
  var REQUEST_KEYS = ['requested_construction_date', 'requested_construction_time'];

  /** "정보 저장": 고칠 수 있는 묶음(접수 확인 중 정보 · 희망 시공일)의 칸만 보낸다 — 서버가 다시 판정한다. */
  function bindInfoSave(box) {
    var groups = (box.getAttribute('data-pp-info-groups') || '').split(' ');
    var status = box.querySelector('[data-pp-info-status]');
    var button = box.querySelector('[data-pp-info-save]');
    var keys = (groups.indexOf('info') !== -1 ? INFO_KEYS : []).concat(groups.indexOf('request') !== -1 ? REQUEST_KEYS : []);
    function show(text, isError) {
      status.textContent = text;
      status.classList.toggle('pp-status--error', !!isError);
    }
    button.addEventListener('click', async function () {
      var body = {};
      keys.forEach(function (key) {
        var el = document.querySelector('[data-pp-info-key="' + key + '"]');
        if (el) body[key] = el.value.trim();
      });
      if (groups.indexOf('info') !== -1 && (!body.customer_name || !body.customer_phone || !body.address)) {
        show('고객 이름 · 연락처 · 현장 주소를 넣어 주세요.', true);
        return;
      }
      button.disabled = true;
      show('저장하는 중…');
      try {
        await putJson(box.getAttribute('data-pp-info-url'), body);
        show('저장했습니다.');
        window.location.reload();
      } catch (err) {
        show(err.message, true);
        button.disabled = false;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    bindTabs();
    var info = document.querySelector('[data-pp-info]');
    if (info) bindInfoSave(info);
    var save = document.querySelector('[data-pp-items-url]');
    if (save) bindItemsSave(save);
  });
})();
