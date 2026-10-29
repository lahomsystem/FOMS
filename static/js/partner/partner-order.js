/**
 * PARTNER-FOMS 3-1: 협력사 주문 화면 — 탭(주문 · 도면 · 완공 사진)과 접수 확인 중 품목 저장.
 *
 * 서버 계약: PUT /api/partner/orders/<id>/items (JSON {items}) → {success, data:{order_id, item_count, uids}, error}
 *            PUT /api/partner/orders/<id>/info (JSON 고객 · 주소 · 실측 · 희망 시공일, §18) → {success, data, error}
 *            PATCH /api/partner/orders/<id>/attachments/<aid> (JSON {item_index: 번호 | null}, 5-3 보낸 사진 제품 연결 · 해제)
 *            품목 사진은 저장 뒤 POST /api/partner/orders/<id>/files 에 item_index 를 붙여 올린다(partner-portal.js).
 * 단계 버튼(아래 고정 줄)의 data-pp-goto-tab 은 해당 탭을 연다.
 * 설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.3 · §4-4 · §12
 */
(function () {
  'use strict';

  // 서버 오류는 문자열 또는 {code, message}(본문 크기 · 내부 오류 공통 봉투) — 둘 다 글로 보인다.
  function errorText(data) {
    var err = data && data.error;
    if (err && typeof err === 'object') return err.message || '';
    return err || '';
  }

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
    if (!data || !data.success) throw new Error(errorText(data) || '저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
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
        // 새 주문처럼 저장하면 바로 목록으로(사용자 2026-10-28).
        window.location.href = button.getAttribute('data-pp-list-url');
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
        // 새로고침하지 않는다 — 품목 칸에 고르고 아직 안 보낸 사진 · 고친 품목이 사라지지 않게. 칸에는 이미 새 값이 있다.
        show('저장했습니다.');
      } catch (err) {
        show(err.message, true);
      }
      button.disabled = false;
    });
  }

  /** 고르고 아직 안 보낸 사진이 있으면 새로고침 전에 묻는다(사진 칸 파일은 브라우저에만 있다). */
  function hasStagedPhotos() {
    return Array.prototype.some.call(document.querySelectorAll('[data-pp-photo-zone]'), function (z) {
      return z._ppFiles && z._ppFiles.length;
    });
  }

  /** 5-3: 보낸 실측 사진을 제품에 연결(고르기) · 공통으로(단추). 서버가 접수 확인 중 · 자기 사진인지 다시 판정한다. */
  function bindAttachmentLinks() {
    var root = document.getElementById('ppAttUrl');
    if (!root) return;
    var portal = window.PartnerPortal;
    async function link(id, itemIndex, control) {
      if (hasStagedPhotos() && !window.confirm('고르고 아직 보내지 않은 사진이 있습니다. 계속하면 다시 골라야 합니다. 계속할까요?')) {
        if (control.tagName === 'SELECT') control.value = '';
        return;
      }
      control.disabled = true;
      try {
        var url = root.getAttribute('data-url').replace(/\/0$/, '/' + id);
        var resp = await fetch(url, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_index: itemIndex }), credentials: 'same-origin' });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!data || !data.success) throw new Error(errorText(data) || '사진 자리를 바꾸지 못했습니다.');
        window.location.reload();
      } catch (err) {
        if (portal) portal.setStatus(err.message, true);
        control.disabled = false;
      }
    }
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-pp-att-unlink]');
      if (btn) link(btn.getAttribute('data-pp-att-unlink'), null, btn);
    });
    document.addEventListener('change', function (ev) {
      var select = ev.target.closest('[data-pp-att-link]');
      if (select && select.value !== '') link(select.getAttribute('data-pp-att-link'), parseInt(select.value, 10), select);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    bindTabs();
    bindAttachmentLinks();
    var info = document.querySelector('[data-pp-info]');
    if (info) bindInfoSave(info);
    var save = document.querySelector('[data-pp-items-url]');
    if (save) bindItemsSave(save);
  });
})();
