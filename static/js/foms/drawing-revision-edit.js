/**
 * 도면 탭 '요청 고치기' 창(#dwRevisionEditModal) — 사용자 결정 Q5-③.
 *
 * 도면팀이 반영 체크하기 전의 마지막 수정요청(RETURNED)을 영업이 고친다.
 * POST /api/orders/<id>/request-revision/edit  본문 {note, files, source, received_via, target_file_keys?}
 * - files 는 수정요청 files 계약(2b, drawing_revision_files) 그대로: 남길 기존 항목 + 새로 올린 항목 전체 목록.
 *   새 파일은 작업실 인라인 스크립트의 업로드 경로(window.fomsDrawingUploadRevisionFiles)로 올린다 —
 *   같은 drawing_gateway/revisions 폴더·같은 완료 라우트라 서버 검사를 그대로 통과한다.
 * - 미리 채움 값은 서버가 data-edit-revision(JSON)에 싣는다(customer_send.edit_revision) — safeJsonParse 로 읽는다.
 * - 응답 {success, data: {request}} · 성공이면 요청사항 탭으로 새로고침.
 */
(function () {
  'use strict';
  if (window.__FOMS_DRAWING_REVISION_EDIT_BOUND) return;
  window.__FOMS_DRAWING_REVISION_EDIT_BOUND = true;

  var MODAL_ID = 'dwRevisionEditModal';
  // 서버 drawing_revision_files.MAX_REVISION_FILES 와 같은 값(남길 파일 + 새 파일 합).
  var MAX_REVISION_FILES = 20;
  var prefill = {};
  var busy = false;

  function safeJsonParse(val, fb) {
    try {
      var s = String(val || '').trim();
      if (!s) return fb;
      var o = JSON.parse(s);
      return (o && typeof o === 'object' && !Array.isArray(o)) ? o : fb;
    } catch (_) {
      return fb;
    }
  }
  function q(root, sel) { return root ? root.querySelector(sel) : null; }
  function attr(el, name) { return el ? String(el.getAttribute(name) || '') : ''; }
  function checked(root, name) {
    var el = q(root, 'input[name="' + name + '"]:checked');
    return el ? el.value : '';
  }
  function show(el, text) {
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('d-none', !text);
  }
  function list(v) { return Array.isArray(v) ? v : []; }

  function refreshSource(root) {
    var via = q(root, '[data-edit-via-block]');
    if (via) via.classList.toggle('d-none', checked(root, 'dw-edit-source') !== 'customer');
  }

  /** 지금 붙어 있는 파일 목록 — 이름은 textContent 로만 넣는다(저장 값 신뢰 금지). */
  function renderFiles(root) {
    var box = q(root, '[data-edit-files]');
    if (!box) return;
    box.textContent = '';
    var files = list(prefill.files);
    if (!files.length) {
      box.textContent = '붙어 있는 파일이 없어요.';
      return;
    }
    files.forEach(function (f, i) {
      if (!f || typeof f !== 'object' || !f.key) return;
      var wrap = document.createElement('div');
      wrap.className = 'form-check';
      var input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'form-check-input';
      input.id = 'dw-edit-keep-' + i;
      input.checked = true;
      input.setAttribute('data-edit-keep-index', String(i));
      var lab = document.createElement('label');
      lab.className = 'form-check-label';
      lab.htmlFor = input.id;
      lab.textContent = String(f.filename || f.key);
      wrap.appendChild(input);
      wrap.appendChild(lab);
      box.appendChild(wrap);
    });
  }

  function reset(root) {
    busy = false;
    prefill = safeJsonParse(attr(root, 'data-edit-revision'), {});
    var source = prefill.source === 'customer' ? 'customer' : 'sales';
    var radio = q(root, '#dw-edit-source-' + source);
    if (radio) radio.checked = true;
    Array.prototype.forEach.call(root.querySelectorAll('input[name="dw-edit-via"]'), function (el) {
      el.checked = !!prefill.received_via && el.value === prefill.received_via;
    });
    var targets = list(prefill.target_file_keys).length ? list(prefill.target_file_keys) : list(prefill.target_drawing_keys);
    Array.prototype.forEach.call(root.querySelectorAll('input[name="dw-edit-target"]'), function (el) {
      el.checked = targets.indexOf(el.value) !== -1;
    });
    var note = q(root, '#dw-edit-note');
    if (note) note.value = String(prefill.note || '');
    var fileInput = q(root, '#dw-edit-new-files');
    if (fileInput) fileInput.value = '';
    var btn = q(root, '[data-edit-submit]');
    if (btn) btn.disabled = false;
    show(q(root, '[data-edit-error]'), '');
    renderFiles(root);
    refreshSource(root);
  }

  function keptFiles(root) {
    var files = list(prefill.files);
    var kept = [];
    Array.prototype.forEach.call(root.querySelectorAll('[data-edit-keep-index]'), function (el) {
      var f = files[Number(el.getAttribute('data-edit-keep-index'))];
      if (el.checked && f && f.key) kept.push({ key: f.key, filename: f.filename || '' });
    });
    return kept;
  }

  async function submit(root) {
    if (busy) return;
    var orderId = attr(root, 'data-order-id');
    var errEl = q(root, '[data-edit-error]');
    var btn = q(root, '[data-edit-submit]');
    var note = String((q(root, '#dw-edit-note') || {}).value || '').trim();
    if (!note) { show(errEl, '요청 내용을 적어 주세요.'); return; }
    var targets = Array.prototype.map.call(root.querySelectorAll('input[name="dw-edit-target"]:checked'), function (el) {
      return el.value;
    });
    if (Number(attr(root, 'data-drawing-count')) > 1 && !targets.length) {
      show(errEl, '도면이 2장 이상이면 어느 도면인지 꼭 골라요.');
      return;
    }
    var newFiles = Array.prototype.slice.call((q(root, '#dw-edit-new-files') || {}).files || []);
    var kept = keptFiles(root);
    if (kept.length + newFiles.length > MAX_REVISION_FILES) {
      show(errEl, '사진·파일은 ' + MAX_REVISION_FILES + '개까지 붙일 수 있어요. 줄여 주세요.');
      return;
    }
    if (newFiles.length && typeof window.fomsDrawingUploadRevisionFiles !== 'function') {
      show(errEl, '파일을 올릴 수 없어요 — 화면을 새로고침한 뒤 다시 해 주세요.');
      return;
    }
    busy = true;
    if (btn) btn.disabled = true;
    show(errEl, '');
    try {
      var uploaded = newFiles.length ? await window.fomsDrawingUploadRevisionFiles(newFiles) : [];
      if (newFiles.length && list(uploaded).length !== newFiles.length) {
        throw new Error('일부 파일을 올리지 못했어요. 다시 해 주세요.');
      }
      var source = checked(root, 'dw-edit-source') === 'customer' ? 'customer' : 'sales';
      var body = { note: note, files: kept.concat(list(uploaded)), source: source };
      var via = checked(root, 'dw-edit-via');
      if (source === 'customer' && via) body.received_via = via;
      if (targets.length) body.target_file_keys = targets;
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/request-revision/edit', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(body),
      });
      var data = null;
      try { data = await res.json(); } catch (_) { data = null; }
      if (!data || !data.success) {
        show(errEl, '고치지 못했어요 — ' + ((data && (data.message || data.error)) || ('HTTP ' + res.status)));
        busy = false;
        if (btn) btn.disabled = false;
        return;
      }
      window.location.href = '/erp/drawing-workbench/' + encodeURIComponent(orderId) + '?tab=requests';
    } catch (err) {
      show(errEl, (err && err.message) || '고치는 중 오류가 났어요. 잠시 뒤 다시 해 주세요.');
      busy = false;
      if (btn) btn.disabled = false;
    }
  }

  document.addEventListener('show.bs.modal', function (e) {
    if (e.target && e.target.id === MODAL_ID) reset(e.target);
  });
  document.addEventListener('change', function (e) {
    if (e.target && e.target.name === 'dw-edit-source') refreshSource(document.getElementById(MODAL_ID));
  });
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('[data-edit-submit]') : null;
    if (!t) return;
    e.preventDefault();
    submit(document.getElementById(MODAL_ID));
  });
})();
