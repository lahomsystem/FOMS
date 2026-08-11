/*
 * 시공 대시보드 인라인 스크립트 외부화 (2026-08-11).
 * 예전엔 construction/partials/scripts.html 이 이 코드를 프래그먼트 HTML 안에
 * 통째로 실어 탭 전환마다 재전송했다(프래그먼트 raw 1.27MB 중 인라인 script 327KB).
 * erp-shell 의 activateScripts 는 src 스크립트도 노드 교체로 재실행하므로
 * (static/js/runtime/erp-shell.js), "swap 마다 재실행" 계약은 그대로 유지된다.
 * 서버 값(use_direct_upload)만 body 의 data-* 로 받는다.
 */
  // ═══════════════════════════════════════════════════════════════
  // Zone 1: 유틸리티 및 전역 설정
  // ═══════════════════════════════════════════════════════════════

  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  function esc(v) {
    if (v == null) return '';
    return String(escapeHtml(v)).replace(/`/g, '\\`').replace(/\$/g, '\\$');
  }

  function escAttr(s) {
    return String(s || '').replace(/'/g, "\\'");
  }

  function formatScheduleDateTimeDisplay(dateStr, timeStr) {
    const d = dateStr != null ? String(dateStr).trim() : '';
    const t = timeStr != null ? String(timeStr).trim() : '';
    if (!d || d === '-') return '-';
    return t ? d + ' ' + t : d;
  }

  function safeJsonParse(val, fb) {
    try {
      var s = String(val || '').trim();
      if (!s) return fb || {};
      var o = JSON.parse(s);
      return (o && typeof o === 'object' && !Array.isArray(o)) ? o : (fb || {});
    } catch (_) {
      return fb || {};
    }
  }

  var _cfg = document.getElementById('erp-dashboard-config');
  var TEAM_LABELS = _cfg ? safeJsonParse(_cfg.getAttribute('data-team-labels'), {}) : {};
  var STAGE_LABELS = _cfg ? safeJsonParse(_cfg.getAttribute('data-stage-labels'), {}) : {};
  var CURRENT_USER_ID = _cfg ? (parseInt(_cfg.getAttribute('data-current-user-id'), 10) || null) : null;

  function label(map, code, fallback = '-') {
    if (!code) return fallback;
    return map[code] || code;
  }

  async function safeJsonFetch(url, fallback) {
    const r = await fetch(url);
    const ct = r.headers.get('content-type') || '';
    if (!r.ok || !ct.includes('application/json')) {
      if (!r.ok) console.warn('Order detail API non-OK:', url, r.status);
      return fallback;
    }
    try {
      return await r.json();
    } catch (e) {
      console.error('JSON parse error for', url, e);
      return fallback;
    }
  }

  var __orderDetailPayloadCache = {};

  function getPreloadedOrderDetailPayload(orderId) {
    if (__orderDetailPayloadCache[orderId]) {
      return __orderDetailPayloadCache[orderId];
    }

    const payloadEl = document.getElementById(`order-detail-preload-${orderId}`);
    if (!payloadEl) {
      return null;
    }

    try {
      const payload = JSON.parse(payloadEl.textContent || '{}');
      __orderDetailPayloadCache[orderId] = payload;
      return payload;
    } catch (e) {
      console.warn('Order detail preload parse error:', orderId, e);
      return null;
    }
  }

  async function patchConstructionDetailAttachments(orderId, gen) {
    const container = document.getElementById(`order-detail-content-${orderId}`);
    if (!container || !container.isConnected) return;

    try {
      const attachments = await safeJsonFetch(`/api/orders/${orderId}/attachments`, { success: false, attachments: [] });
      if (__constructionDetailLoadGen[orderId] !== gen) return;
      if (!container.isConnected) return;

      const aList = parseAttachmentsPayload(attachments);
      __attachmentsCache[orderId] = aList;
      __attachmentsCacheAt[orderId] = Date.now();

      const countEl = document.getElementById(`order-detail-attachments-count-${orderId}`);
      const slotEl = document.getElementById(`order-detail-attachments-slot-${orderId}`);
      if (countEl && countEl.isConnected) countEl.textContent = `${aList.length}개`;
      if (slotEl && slotEl.isConnected) {
        slotEl.innerHTML = aList.length > 0 ? buildMainAttachThumbsHtml(orderId, aList) : '<div class="text-muted small mt-2">첨부 없음</div>';
      }

      container.dataset.loaded = '1';
      container.dataset.attachPhase = 'done';
      delete container.dataset.shellLoaded;
      delete container.dataset.attachError;
    } catch (e) {
      if (__constructionDetailLoadGen[orderId] !== gen) return;
      console.warn('construction 첨부 로드 실패:', orderId, e);
      const slotEl = document.getElementById(`order-detail-attachments-slot-${orderId}`);
      if (slotEl && slotEl.isConnected) {
        slotEl.innerHTML = '<div class="text-danger small">첨부를 불러오지 못했습니다. 다시 펼쳐 재시도할 수 있습니다.</div>';
      }
      container.dataset.attachPhase = 'error';
      container.dataset.attachError = '1';
    }
  }

  var __selectedOrderId = null;
  var __attachmentsCache = {};
  var __attachmentsCacheAt = {};
  var __constructionDetailLoadGen = {};
  var __currentAttachmentList = [];
  var __currentAttachmentIndex = 0;
  var __activeAttachmentCategory = 'measurement';
  var __attachmentsByCategory = {
    measurement: [],
    drawing: [],
    construction: [],
    as: []
  };

  function invalidateConstructionOrderDetailAttachments(orderId) {
    if (!orderId || typeof window.invalidateOrderDetailRuntimeState !== 'function') return;
    window.invalidateOrderDetailRuntimeState(orderId, {
      cache: __attachmentsCache,
      cacheAt: __attachmentsCacheAt,
      loadGen: __constructionDetailLoadGen,
      containerPrefix: 'order-detail-content-'
    });
  }
  window.invalidateConstructionOrderDetailAttachments = invalidateConstructionOrderDetailAttachments;

  // ═══════════════════════════════════════════════════════════════
  // Zone 2: 첨부파일 뷰어 및 줌
  // ═══════════════════════════════════════════════════════════════

  var ATTACHMENT_CATEGORY_META = {
    measurement: { label: '실측', icon: 'fa-ruler-combined' },
    drawing: { label: '도면', icon: 'fa-drafting-compass' },
    construction: { label: '시공', icon: 'fa-hammer' },
    as: { label: 'AS', icon: 'fa-wrench' }
  };

  function normalizeAttachmentCategory(category) {
    const c = String(category || '').trim().toLowerCase();
    if (c === 'drawing' || c === 'construction' || c === 'as') return c;
    return 'measurement';
  }

  function attachmentCanDelete(a) {
    return !!(a && a.can_delete === true);
  }

  function getAttachmentCategoryLabel(category) {
    const key = normalizeAttachmentCategory(category);
    return (ATTACHMENT_CATEGORY_META[key] || ATTACHMENT_CATEGORY_META.measurement).label;
  }

  function renderAttachmentCategoryTabs() {
    const tabsEl = document.getElementById('erp-attachments-category-tabs');
    if (!tabsEl) return;
    const keys = ['measurement', 'drawing', 'construction', 'as'];
    tabsEl.innerHTML = keys.map((key) => {
      const meta = ATTACHMENT_CATEGORY_META[key];
      const count = (__attachmentsByCategory[key] || []).length;
      const isActive = key === __activeAttachmentCategory;
      const activeCls = isActive ? 'btn-primary' : 'btn-outline-primary';
      return `
<button type="button" class="btn btn-sm ${activeCls}" onclick="selectAttachmentCategory('${key}')">
  <i class="fas ${meta.icon}"></i> ${meta.label}
  <span class="badge ${isActive ? 'bg-light text-dark' : 'bg-primary text-white'} ms-1">${count}</span>
</button>
`;
    }).join('');
  }

  function renderAttachmentCategoryGallery() {
    const galleryEl = document.getElementById('erp-attachments-category-gallery');
    if (!galleryEl) return;
    const list = __attachmentsByCategory[__activeAttachmentCategory] || [];
    if (!list.length) {
      galleryEl.innerHTML = `
<div class="col-12">
  <div class="text-muted small p-3 border rounded bg-light">
    ${getAttachmentCategoryLabel(__activeAttachmentCategory)} 카테고리에 첨부 파일이 없습니다.
  </div>
</div>
`;
      return;
    }

    galleryEl.innerHTML = list.map((a, index) => {
      const name = esc(a.filename || '');
      const type = a.file_type || 'file';
      const thumb = esc(a.thumbnail_view_url || a.view_url || '#');
      const viewUrl = esc(a.view_url || '#');
      const downloadUrl = esc(a.download_url || '#');

      const mediaHtml = (type === 'video')
        ? `<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">
  <video src="${viewUrl}" controls preload="metadata" style="width:100%;height:100%;"></video>
</div>`
        : `<img src="${thumb}" alt="${name}" class="img-fluid rounded"
  style="max-height: 180px; object-fit: contain; width:100%; cursor: zoom-in; background:#fff; padding:4px;"
  onclick="openAttachmentFromCategory('${__activeAttachmentCategory}', ` + index + `)">`;

      return `
<div class="col-md-4 col-sm-6 col-12">
  <div class="card h-100">
    <div class="card-body p-2">
      ${mediaHtml}
      <div class="d-flex justify-content-between align-items-center mt-2">
        <div class="small text-truncate" title="${name}" style="max-width: 70%;">${name}</div>
        <div class="btn-group btn-group-sm">
          <button class="btn btn-outline-secondary" type="button" title="미리보기"
            onclick="openAttachmentFromCategory('${__activeAttachmentCategory}', ` + index + `)">
            <i class="fas fa-eye"></i>
          </button>
          <a class="btn btn-outline-primary" href="${downloadUrl}" title="다운로드" target="_blank" rel="noopener">
            <i class="fas fa-download"></i>
          </a>
          ${attachmentCanDelete(a) ? `
          <button class="btn btn-outline-danger" type="button" title="삭제"
            onclick="deleteAttachmentFromCategory('${__activeAttachmentCategory}', ` + index + `, '${a.id}')">
            <i class="fas fa-trash"></i>
          </button>` : ''}
        </div>
      </div>
    </div>
  </div>
</div>
`;
    }).join('');
  }

  function selectAttachmentCategory(category) {
    __activeAttachmentCategory = normalizeAttachmentCategory(category);
    renderAttachmentCategoryTabs();
    renderAttachmentCategoryGallery();
  }

  function openAttachmentFromCategory(category, index) {
    const key = normalizeAttachmentCategory(category);
    const list = __attachmentsByCategory[key] || [];
    if (!list.length) return;
    __activeAttachmentCategory = key;
    __currentAttachmentList = list;
    showAttachmentAtIndex(index);
  }

  async function deleteAttachmentFromCategory(category, index, attachmentId) {
    const orderId = __selectedOrderId;
    const key = normalizeAttachmentCategory(category);
    const list = __attachmentsByCategory[key] || [];
    const attachment = list[index] || {};
    const id = attachmentId || attachment.id;
    if (!orderId || !id) return;
    if (!attachmentCanDelete(attachment)) {
      alert('첨부파일 삭제 권한이 없습니다.');
      return;
    }
    if (!confirm('첨부 파일을 삭제하시겠습니까?')) return;
    try {
      const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/attachments/' + encodeURIComponent(id), {
        method: 'DELETE'
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        alert((data && data.message) || '첨부 파일 삭제에 실패했습니다.');
        return;
      }
      invalidateConstructionOrderDetailAttachments(orderId);
      await openAttachmentsPreview(orderId, key);
    } catch (err) {
      console.error('Attachment delete error:', err);
      alert('첨부 파일 삭제 중 오류가 발생했습니다.');
    }
  }
  window.deleteAttachmentFromCategory = deleteAttachmentFromCategory;

  async function openAttachmentsPreview(orderId, initialCategory = 'measurement') {
    try {
      __selectedOrderId = orderId;
      let aList = null;
      if (__attachmentsCache[orderId]) {
        aList = __attachmentsCache[orderId];
        } else {
          const res = await fetch(`/api/orders/${orderId}/attachments`);
          const data = await res.json();
          aList = (data && data.attachments) || [];
          __attachmentsCache[orderId] = aList;
          __attachmentsCacheAt[orderId] = Date.now();
        }

      if (aList.length > 0) {
        __attachmentsByCategory = { measurement: [], drawing: [], construction: [], as: [] };
        aList.forEach((a) => {
          const key = normalizeAttachmentCategory(a.category);
          const normalized = Object.assign({}, a, { category: key });
          if (!__attachmentsByCategory[key]) __attachmentsByCategory[key] = [];
          __attachmentsByCategory[key].push(normalized);
        });

        let targetCategory = normalizeAttachmentCategory(initialCategory);
        const targetList = __attachmentsByCategory[targetCategory] || [];
        if (!targetList.length) {
          if (__attachmentsByCategory.drawing.length) targetCategory = 'drawing';
          else if (__attachmentsByCategory.measurement.length) targetCategory = 'measurement';
          else if (__attachmentsByCategory.construction.length) targetCategory = 'construction';
        }
        __activeAttachmentCategory = targetCategory;

        renderAttachmentCategoryTabs();
        renderAttachmentCategoryGallery();
        const modalEl = document.getElementById('erpAttachmentsCategoryModal');
        if (modalEl) {
          const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
          modal.show();
        }
      } else {
        alert('첨부 파일이 없습니다.');
      }
    } catch (err) {
      console.error('첨부 파일 로드 실패:', err);
      alert('첨부 파일을 불러올 수 없습니다.');
    }
  }

  function showAttachmentAtIndex(index) {
    if (!__currentAttachmentList || index < 0 || index >= __currentAttachmentList.length) {
      return;
    }
    __currentAttachmentIndex = index;
    const a = __currentAttachmentList[index];
    if (typeof window.fomsOpenAttachmentPreviewFromRecord === 'function') {
      window.fomsOpenAttachmentPreviewFromRecord(a, __currentAttachmentList, index);
      return;
    }
    if (window.GlobalImageViewer) {
      window.GlobalImageViewer.open(__currentAttachmentList, index);
    } else {
      console.error('GlobalImageViewer not found');
      alert('이미지 뷰어를 불러올 수 없습니다.');
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Zone 3: 공통 업로드 엔진
  // ═══════════════════════════════════════════════════════════════

  async function executeBatchUpload(orderId, files, category, ui) {
    const { statusEl, progressWrap, progressBar } = ui;
    const totalFiles = files.length;
    if (statusEl) statusEl.textContent = `이미지 최적화 중... (0/${totalFiles})`;
    if (progressWrap) progressWrap.classList.remove('d-none');
    if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }

    // 서버 플래그는 설정 마운트의 data-* 로 받는다(외부 .js 는 Jinja 보간 불가).
    // 마운트는 scripts.html 이 이 스크립트 바로 앞에 렌더한다(swap 마다 갱신).
    const _cfgEl = document.getElementById('foms-construction-config');
    const isDirectUploadEnabled =
      !!_cfgEl && _cfgEl.getAttribute('data-foms-direct-upload') === 'true';
    const result = await window.fomsUploadOrderAttachmentsBatch({
      orderId: orderId,
      files: Array.from(files || []),
      folder: `orders/${orderId}/attachments`,
      category: category,
      useDirectUpload: isDirectUploadEnabled,
      onPrepareProgress: function (info) {
        if (statusEl) statusEl.textContent = `이미지 최적화 중... (${info.done}/${info.total})`;
      },
      onUploadProgress: function (info) {
        const pct = Math.round((info.done / totalFiles) * 100);
        if (progressBar) { progressBar.style.width = pct + '%'; progressBar.textContent = pct + '%'; }
        if (statusEl) statusEl.textContent = `업로드 중... (${Math.round(info.done)}/${info.total})`;
      }
    });

    return { ok: result.ok, total: result.total };
  }

  // ═══════════════════════════════════════════════════════════════
  // Zone 4: 시공 / AS 비즈니스 로직
  // ═══════════════════════════════════════════════════════════════

  async function startConstruction(orderId) {
    if (!confirm('시공을 시작하시겠습니까? (로그가 기록됩니다)')) return;
    try {
      const res = await fetch(`/api/orders/${orderId}/construction/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (data.success) {
        alert(data.message);
        window.location.reload();
      } else {
        alert('오류: ' + data.message);
      }
    } catch (err) {
      console.error('Construction start error:', err);
      alert('처리 중 오류가 발생했습니다.');
    }
  }

  function completeConstruction(orderId) {
    const orderIdInput = document.getElementById('erp-cons-complete-order-id');
    if (orderIdInput) orderIdInput.value = orderId;
    const fileInput = document.getElementById('erp-cons-complete-input');
    if (fileInput) fileInput.value = '';
    const statusEl = document.getElementById('erp-cons-complete-status');
    if (statusEl) statusEl.innerHTML = '';
    const progressWrap = document.getElementById('erp-cons-complete-progress');
    if (progressWrap) progressWrap.classList.add('d-none');
    const modalEl = document.getElementById('erpConstructionCompleteModal');
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  function reuploadConstructionPhotos(orderId) {
    const orderIdInput = document.getElementById('erp-cons-reupload-order-id');
    if (orderIdInput) orderIdInput.value = orderId;
    const fileInput = document.getElementById('erp-cons-reupload-input');
    if (fileInput) fileInput.value = '';
    const statusEl = document.getElementById('erp-cons-reupload-status');
    if (statusEl) statusEl.textContent = '';
    const progressWrap = document.getElementById('erp-cons-reupload-progress');
    if (progressWrap) progressWrap.classList.add('d-none');
    const modalEl = document.getElementById('erpConstructionReuploadModal');
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  function openAsAcceptModal(orderId) {
    const orderIdInput = document.getElementById('erp-cons-as-order-id');
    if (orderIdInput) orderIdInput.value = orderId;
    const reuploadInput = document.getElementById('erp-cons-as-reupload-mode');
    if (reuploadInput) reuploadInput.value = '0';
    const fileInput = document.getElementById('erp-cons-as-input');
    if (fileInput) fileInput.value = '';
    const asContentEl = document.getElementById('erp-cons-as-content');
    if (asContentEl) asContentEl.value = '';
    const statusEl = document.getElementById('erp-cons-as-status');
    if (statusEl) statusEl.textContent = '';
    const progressWrap = document.getElementById('erp-cons-as-progress');
    if (progressWrap) progressWrap.classList.add('d-none');
    const modalEl = document.getElementById('erpConstructionAsAcceptModal');
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  function openAsReuploadModal(orderId) {
    const orderIdInput = document.getElementById('erp-cons-as-order-id');
    if (orderIdInput) orderIdInput.value = orderId;
    const reuploadInput = document.getElementById('erp-cons-as-reupload-mode');
    if (reuploadInput) reuploadInput.value = '1';
    const fileInput = document.getElementById('erp-cons-as-input');
    if (fileInput) fileInput.value = '';
    const asContentEl = document.getElementById('erp-cons-as-content');
    if (asContentEl) asContentEl.value = '';
    const statusEl = document.getElementById('erp-cons-as-status');
    if (statusEl) statusEl.textContent = '본인이 올린 AS 사진만 삭제 후 새 사진을 업로드합니다.';
    const progressWrap = document.getElementById('erp-cons-as-progress');
    if (progressWrap) progressWrap.classList.add('d-none');
    const modalEl = document.getElementById('erpConstructionAsAcceptModal');
    if (modalEl) {
      const modal = new bootstrap.Modal(modalEl);
      modal.show();
    }
  }

  // fragment 재실행-안전(가드 G4): document 위임은 싱글톤 가드로 1회만 배선(swap마다 누적 방지).
  // 핸들러는 요소·함수를 이벤트 시점에 조회(closest + window[action])하므로 stale 참조 없음.
  (function () {
    if (window.__FOMS_CONSTR_ACTION_CLICK_BOUND) return;
    window.__FOMS_CONSTR_ACTION_CLICK_BOUND = true;
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.erp-construction-action');
      if (!btn) return;
      var orderId = btn.getAttribute('data-order-id');
      var action = btn.getAttribute('data-action');
      if (!orderId || !action) return;
      var fn = window[action];
      if (typeof fn === 'function') fn(orderId);
    });
  })();

  async function submitConstructionComplete() {
    const orderId = document.getElementById('erp-cons-complete-order-id').value;
    if (!orderId) return;
    const input = document.getElementById('erp-cons-complete-input');
    const statusEl = document.getElementById('erp-cons-complete-status');
    const progressWrap = document.getElementById('erp-cons-complete-progress');
    const progressBar = document.getElementById('erp-cons-complete-progress-bar');
    const completeBtn = document.getElementById('erp-cons-complete-btn');

    const files = (input && input.files) ? Array.from(input.files) : [];
    const hasFiles = files.length > 0;

    if (completeBtn) completeBtn.disabled = true;

    if (hasFiles) {
      const result = await executeBatchUpload(orderId, files, 'construction', { statusEl, progressWrap, progressBar });
      if (result.ok < result.total) {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">일부 파일 업로드에 실패했습니다. 다시 시도해주세요.</span>';
        if (completeBtn) completeBtn.disabled = false;
        return;
      }
      if (statusEl) statusEl.innerHTML = `<span class="text-success">${result.ok}개 사진 업로드 완료! 상태 변경 중...</span>`;
    } else {
      if (statusEl) statusEl.textContent = '사진 업로드 없이 상태 변경 중...';
    }

    const noteEl = document.getElementById('erp-cons-complete-note');
    const noteValue = (noteEl && noteEl.value) ? String(noteEl.value).trim() : '';

    try {
      const res = await fetch(`/api/orders/${orderId}/construction/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completion_note: noteValue })
      });
      const data = await res.json();
      if (data.success) {
        const modalEl = document.getElementById('erpConstructionCompleteModal');
        if (modalEl) {
          const modal = bootstrap.Modal.getInstance(modalEl);
          if (modal) modal.hide();
        }
        window.location.href = '/erp/construction/dashboard';
      } else {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">오류: ' + esc(data.message) + '</span>';
        if (completeBtn) completeBtn.disabled = false;
      }
    } catch (err) {
      console.error('Construction complete error:', err);
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">처리 중 오류가 발생했습니다.</span>';
      if (completeBtn) completeBtn.disabled = false;
    }
  }

  async function submitConstructionReupload() {
    const orderId = document.getElementById('erp-cons-reupload-order-id').value;
    if (!orderId) return;
    const input = document.getElementById('erp-cons-reupload-input');
    const statusEl = document.getElementById('erp-cons-reupload-status');
    const progressWrap = document.getElementById('erp-cons-reupload-progress');
    const progressBar = document.getElementById('erp-cons-reupload-progress-bar');
    const reuploadBtn = document.getElementById('erp-cons-reupload-btn');
    const files = (input && input.files) ? Array.from(input.files) : [];
    if (files.length === 0) {
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">새 사진을 선택해주세요.</span>';
      return;
    }
    if (reuploadBtn) reuploadBtn.disabled = true;
    if (statusEl) statusEl.textContent = '기존 시공 이미지 삭제 중...';

    try {
      const listRes = await fetch(`/api/orders/${orderId}/attachments?category=construction`);
      const listData = await listRes.json();
      if (listData.success && listData.attachments && listData.attachments.length > 0) {
        const toDelete = listData.attachments.filter(function (a) { return a && a.id && attachmentCanDelete(a); });
        const deleteResults = await Promise.all(toDelete.map(function (att) {
          return fetch('/api/orders/' + orderId + '/attachments/' + att.id, { method: 'DELETE' });
        }));
        const failed = deleteResults.filter(function (res) { return !res.ok; });
        if (failed.length > 0) {
          if (statusEl) statusEl.innerHTML = '<span class="text-danger">삭제 권한이 없는 파일이 있어 재업로드를 중단했습니다.</span>';
          if (reuploadBtn) reuploadBtn.disabled = false;
          return;
        }
      }

      const result = await executeBatchUpload(orderId, files, 'construction', { statusEl, progressWrap, progressBar });
      if (result.ok < result.total) {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">일부 파일 업로드에 실패했습니다. 다시 시도해주세요.</span>';
        if (reuploadBtn) reuploadBtn.disabled = false;
        return;
      }
      if (statusEl) statusEl.innerHTML = `<span class="text-success">기존 이미지 삭제 후 ${result.ok}개 사진 재업로드 완료.</span>`;
      const modalEl = document.getElementById('erpConstructionReuploadModal');
      if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      }
      window.location.reload();
    } catch (err) {
      console.error('Reupload error:', err);
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">처리 중 오류가 발생했습니다.</span>';
      if (reuploadBtn) reuploadBtn.disabled = false;
    }
  }

  async function submitAsAccept() {
    const orderId = document.getElementById('erp-cons-as-order-id').value;
    if (!orderId) return;
    const reuploadInput = document.getElementById('erp-cons-as-reupload-mode');
    const isReupload = reuploadInput && reuploadInput.value === '1';
    const input = document.getElementById('erp-cons-as-input');
    const statusEl = document.getElementById('erp-cons-as-status');
    const progressWrap = document.getElementById('erp-cons-as-progress');
    const progressBar = document.getElementById('erp-cons-as-progress-bar');
    const asBtn = document.getElementById('erp-cons-as-btn');
    const files = (input && input.files) ? Array.from(input.files) : [];
    if (files.length === 0) {
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">AS 사진을 선택해주세요.</span>';
      return;
    }
    if (asBtn) asBtn.disabled = true;

    if (isReupload && CURRENT_USER_ID != null) {
      if (statusEl) statusEl.textContent = '본인 AS 사진 삭제 중...';
      try {
        const listRes = await fetch(`/api/orders/${orderId}/attachments?category=as`);
        const listData = await listRes.json();
        if (listData.success && listData.attachments && listData.attachments.length > 0) {
          const toDelete = listData.attachments.filter(function (a) {
            return a && a.id && attachmentCanDelete(a);
          });
          const deleteResults = await Promise.all(toDelete.map(function (att) {
            return fetch('/api/orders/' + orderId + '/attachments/' + att.id, { method: 'DELETE' });
          }));
          const failed = deleteResults.filter(function (res) { return !res.ok; });
          if (failed.length > 0) {
            if (statusEl) statusEl.innerHTML = '<span class="text-danger">삭제 권한이 없는 AS 파일이 있어 재업로드를 중단했습니다.</span>';
            if (asBtn) asBtn.disabled = false;
            return;
          }
        }
        if (reuploadInput) reuploadInput.value = '0';
      } catch (e) {
        console.error('AS reupload delete own error:', e);
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">기존 AS 사진 삭제 중 오류가 발생했습니다.</span>';
        if (asBtn) asBtn.disabled = false;
        return;
      }
    }

    try {
      const result = await executeBatchUpload(orderId, files, 'as', { statusEl, progressWrap, progressBar });
      if (result.ok < result.total) {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">일부 파일 업로드에 실패했습니다. 다시 시도해주세요.</span>';
        if (asBtn) asBtn.disabled = false;
        return;
      }

      if (statusEl) statusEl.textContent = 'AS 접수 등록 중...';
      const asContentEl = document.getElementById('erp-cons-as-content');
      const asContent = (asContentEl && asContentEl.value) ? asContentEl.value.trim() : '';
      const registerRes = await fetch(`/api/orders/${orderId}/as/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          as_content: asContent,
          source_screen: 'erp_construction_dashboard'
        })
      });
      const registerData = await registerRes.json();
      if (!registerData.success) {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">접수 등록 실패: ' + (registerData.message || '알 수 없음') + '</span>';
        if (asBtn) asBtn.disabled = false;
        return;
      }
      if (statusEl) statusEl.innerHTML = '<span class="text-success">AS 접수 등록 완료. (접수일·상태 반영)</span>';
      const modalEl = document.getElementById('erpConstructionAsAcceptModal');
      if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      }
      window.location.reload();
    } catch (err) {
      console.error('AS accept upload error:', err);
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">처리 중 오류가 발생했습니다.</span>';
      if (asBtn) asBtn.disabled = false;
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Zone 5: 제품/퀘스트/UI 렌더링
  // ═══════════════════════════════════════════════════════════════

  function renderBadges(alerts) {
    const a = alerts || {};
    const out = [];
    if (a.urgent) out.push('<span class="badge bg-danger me-1">긴급</span>');
    if (a.drawing_overdue) out.push('<span class="badge bg-danger me-1">도면48h</span>');
    if (a.measurement_d4) out.push('<span class="badge bg-warning text-dark me-1">실측D-4</span>');
    if (a.construction_d3) out.push('<span class="badge bg-warning text-dark me-1">시공D-3</span>');
    if (a.production_d2) out.push('<span class="badge bg-warning text-dark me-1">생산D-2</span>');
    return out.join('') || '<span class="text-muted small">경보 없음</span>';
  }

  async function approveQuestTeam(orderId, team) {
    try {
      const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team: team })
      });
      const data = await res.json();

      if (!data.success) {
        alert('승인 실패: ' + (data.message || data.error || '알 수 없는 오류'));
        return;
      }

      if (data.auto_transitioned && data.next_stage) {
        const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
        alert('✅ 모든 팀 승인 완료! 다음 단계(' + nextStageLabel + ')로 자동 전환되었습니다.');
      } else if (data.all_approved) {
        alert('✅ 모든 팀 승인 완료!');
      } else {
        const missingTeams = data.missing_teams.map(t => label(TEAM_LABELS, t, t)).join(', ');
        alert('승인 완료. 남은 팀: ' + missingTeams);
      }

      await loadQuestDetail(orderId);
      window.location.reload();
    } catch (err) {
      console.error('승인 실패:', err);
      alert('승인 중 오류가 발생했습니다.');
    }
  }

  async function loadQuestDetail(orderId) {
    try {
      const res = await fetch(`/api/orders/${orderId}/quest`);
      const data = await res.json();
      if (data.error) {
        console.error('Quest 로드 실패:', data.error);
        return;
      }
      const questContainer = document.querySelector(`#quest-collapse-${orderId} #quest-approvals-${orderId}`);
      if (questContainer) {
        const quest = data.quest || {};
        const requiredTeams = quest.required_approvals || [];
        const teamApprovalsRaw = quest.team_approvals || {};

        let html = '';
        for (const team of requiredTeams) {
          const approvalData = teamApprovalsRaw[team];
          let approved = false;
          if (typeof approvalData === 'object' && approvalData !== null) {
            approved = approvalData.approved === true;
          } else {
            approved = Boolean(approvalData);
          }
          const teamLabel = label(TEAM_LABELS, team, team);
          html += `<div class="mb-2">`;
          html += `<span class="fw-semibold" style="font-size: 1rem;">${esc(teamLabel)}</span>`;
          if (approved) {
            html += `<span class="badge bg-success ms-2" style="font-size: 1rem; padding: 0.4em 0.7em;">승인완료</span>`;
          } else {
            const teamEsc = escapeHtml(team).replace(/'/g, "\\'");
            const onclickVal = "approveQuestTeam(" + orderId + ", '" + teamEsc + "')";
            html += '<button class="btn btn-primary fw-semibold ms-2" onclick="' + onclickVal + '" style="font-size: 1rem; padding: 0.4rem 0.75rem;">승인</button>';
          }
          html += `</div>`;
        }
        questContainer.innerHTML = html;
      }
    } catch (err) {
      console.error('Quest 상세 로드 실패:', err);
    }
  }

  async function loadOrderDetail(orderId) {
    const container = document.getElementById(`order-detail-content-${orderId}`);
    if (!container) return;
    if (container.dataset.loaded === '1') return;
    if (container.dataset.shellLoaded === '1' && container.dataset.attachPhase === 'loading') return;
    if (container.dataset.shellLoaded === '1' && container.dataset.attachPhase === 'error') {
      const retryGen = (__constructionDetailLoadGen[orderId] || 0) + 1;
      __constructionDetailLoadGen[orderId] = retryGen;
      container.dataset.attachPhase = 'loading';
      delete container.dataset.attachError;
      await patchConstructionDetailAttachments(orderId, retryGen);
      return;
    }

    const gen = (__constructionDetailLoadGen[orderId] || 0) + 1;
    __constructionDetailLoadGen[orderId] = gen;

    try {
      const preloaded = getPreloadedOrderDetailPayload(orderId);
      let structured = null;
      let attachmentsPending = true;
      let preloadedAttachmentsPayload = null;

      if (preloaded && preloaded.success) {
        structured = preloaded;
        if (preloaded.attachments !== undefined) {
          attachmentsPending = false;
          preloadedAttachmentsPayload = preloaded.attachments;
        }
      } else {
        container.innerHTML = '<div class="text-muted small">로딩 중...</div>';
        structured = await safeJsonFetch(`/api/orders/${orderId}/structured`, { success: false, structured_data: {} });
      }

      if (!structured || !structured.success) {
        container.innerHTML = '<div class="text-danger small">상세 정보를 불러올 수 없습니다. 새로고침 후 다시 시도하세요.</div>';
        return;
      }

      const sd = (structured && structured.structured_data) || {};
      const customer = (((sd.parties || {}).customer || {}).name) || '-';
      const orderer = (((sd.parties || {}).orderer || {}).name) || '-';
      const phone = (((sd.parties || {}).customer || {}).phone) || '-';
      const site = sd.site || {};
      const addressFull = site.address_full || '';
      const addressMain = site.address_main || '';
      const addressDetail = site.address_detail || '';
      const address = addressFull || (addressMain && addressDetail ? `${addressMain} ${addressDetail}`.trim() : addressMain) || addressDetail || '-';
      const notes = sd.notes || {};
      const addressNote = (notes.address_note || '').trim();
      const phoneNote = (notes.phone_note || '').trim();
      const measureNote = (notes.measurement_note || '').trim();
      const measure = formatScheduleDateTimeDisplay(
        (((sd.schedule || {}).measurement || {}).date) || '',
        (((sd.schedule || {}).measurement || {}).time) || ''
      );
      const construct = formatScheduleDateTimeDisplay(
        (((sd.schedule || {}).construction || {}).date) || '',
        (((sd.schedule || {}).construction || {}).time) || ''
      );
      const manager = (((sd.parties || {}).manager || {}).name) || '-';
      const stage = (((sd.workflow || {}).stage)) || '-';
      const hist = (sd.workflow || {}).history || [];
      const is_started = hist.some(h => String(h.note || '').trim() === '시공 시작');
      let displayStage = '';
      if (stage === 'CONSTRUCTION' || stage === '시공') {
        displayStage = is_started ? '시공중' : '시공대기';
      } else if (stage === 'CS' || stage === 'COMPLETED' || stage === '완료' || stage === 'AS_WAIT') {
        displayStage = '시공완료';
      } else if (stage === 'CONSTRUCTING') {
        displayStage = '시공중';
      } else {
        displayStage = stage;
      }
      const urgent = ((sd.flags || {}).urgent) || false;

      const STAGE_TO_TEAM = {
        'RECEIVED': 'CS',
        'MEASURE': 'SALES',
        'DRAWING': 'DRAWING',
        'CONFIRM': 'SALES',
        'PRODUCTION': 'PRODUCTION',
        'CONSTRUCTION': 'CONSTRUCTION',
        'CS': 'CS',
        'COMPLETED': 'CS',
        'AS': 'CS'
      };
      let ownerTeam = STAGE_TO_TEAM[stage] || '-';
      if (stage === 'MEASURE' || stage === 'CONFIRM') {
        const ordererName = (((sd.parties || {}).orderer || {}).name || '').trim();
        if (ordererName && ordererName.includes('라홈')) {
          ownerTeam = 'CS';
        }
      }

      const items = (sd.items || []) || [];
      let itemsHtml = '';
      if (items.length > 0) {
        let gridHtml = '<div class="erp-product-items-grid mt-3">';
        items.forEach(item => {
          let specW = item.spec_width || '';
          let specD = item.spec_depth || '';
          let specH = item.spec_height || '';
          if (!specW && !specD && !specH && item.spec) {
            const specStr = String(item.spec || '').trim();
            const parts = specStr.split(/[xX*×]/).map(s => s.trim());
            if (parts.length >= 3) { specW = parts[0]; specD = parts[1]; specH = parts[2]; }
            else if (parts.length === 2) { specW = parts[0]; specD = parts[1]; }
            else if (parts.length === 1) { specW = parts[0]; }
          }
          const specParts = [];
          if (specW && specW !== '-') specParts.push(`W:${specW}`);
          if (specD && specD !== '-') specParts.push(`D:${specD}`);
          if (specH && specH !== '-') specParts.push(`H:${specH}`);
          const specCombined = specParts.length > 0 ? specParts.join(' × ') : '-';
          const priceText = item.price ? item.price.toLocaleString('ko-KR') + '원' : '-';

          const safeValue = (val) => {
            if (val === null || val === undefined || val === '') return '-';
            return String(val).trim() || '-';
          };

          gridHtml += `<div class="erp-product-items-card">
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">제품명:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.product_name || item.name))}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">규격:</span>
          <span class="erp-product-items-value">${esc(specCombined)}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">내부:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.internal))}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">색상:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.color))}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">옵션:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.option_detail || item.options))}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">손잡이:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.handle))}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">기타:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.misc))}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">추가 입력:</span>
          <span class="erp-product-items-value">${esc(safeValue(item.extra_input)).replace(/\n/g, '<br>')}</span>
        </div>
        <div class="erp-product-items-row">
          <span class="erp-product-items-label">금액:</span>
          <span class="erp-product-items-value">${esc(priceText)}</span>
        </div>
      </div>`;
        });
        gridHtml += '</div>';
        itemsHtml = gridHtml;
      } else {
        itemsHtml = '<div class="text-muted mt-3" style="font-size: 1rem;">제품 항목 없음</div>';
      }

      let aList = [];
      if (!attachmentsPending && preloadedAttachmentsPayload !== null) {
        aList = parseAttachmentsPayload(
          Array.isArray(preloadedAttachmentsPayload)
            ? { success: true, attachments: preloadedAttachmentsPayload }
            : preloadedAttachmentsPayload
        );
      }
      __attachmentsCache[orderId] = attachmentsPending ? [] : aList;
      if (!attachmentsPending) __attachmentsCacheAt[orderId] = Date.now();

      let attachmentsHtml = '';
      if (attachmentsPending) {
        attachmentsHtml = '<div class="order-detail-attach-loading gap-2 text-muted small py-2"><span class="spinner-border spinner-border-sm" role="status"></span><span class="visually-hidden">불러오는 중</span>불러오는 중…</div>';
      } else if (aList.length > 0) {
        attachmentsHtml = buildMainAttachThumbsHtml(orderId, aList);
      } else {
        attachmentsHtml = '<div class="text-muted small mt-2">첨부 없음</div>';
      }

      const isMobile = window.innerWidth <= 992;
      const basicInfoHtml = isMobile ? '' : `
      <div class="col-md-6">
        <div class="card">
          <div class="card-body">
            <h5 class="card-title fw-bold"><i class="fas fa-info-circle text-primary"></i> 기본 정보</h5>
            <div class="erp-detail-text">
              <div class="mb-3"><strong class="erp-detail-label">고객명:</strong> <span class="erp-detail-value">${esc(customer)}</span></div>
              <div class="mb-3"><strong class="erp-detail-label">발주사:</strong> <span class="erp-detail-value">${esc(orderer)}</span></div>
              <div class="mb-3"><strong class="erp-detail-label">연락처:</strong> <span class="erp-detail-value">${esc(phone)}</span></div>
              <div class="mb-3"><strong class="erp-detail-label">주소:</strong> <span class="erp-detail-value">${esc(address)}</span></div>
              <div class="mb-3"><strong class="erp-detail-label">담당자:</strong> <span class="erp-detail-value">${esc(manager)}</span></div>
            </div>
          </div>
        </div>
      </div>`;

      const notesHtml = [
        `<div class="mb-3"><strong class="erp-detail-label">연락특이:</strong> <span class="erp-detail-value">${esc(phoneNote) || '-'}</span></div>`,
        `<div class="mb-3"><strong class="erp-detail-label">주소특이:</strong> <span class="erp-detail-value">${esc(addressNote) || '-'}</span></div>`,
        `<div class="mb-3"><strong class="erp-detail-label">실측특이:</strong> <span class="erp-detail-value">${esc(measureNote) || '-'}</span></div>`
      ].join('');

      const scheduleHtml = `
      <div class="${isMobile ? 'col-12' : 'col-md-6'}">
        <div class="card">
          <div class="card-body">
            <h5 class="card-title fw-bold"><i class="fas fa-calendar text-primary"></i> 일정 및 특이사항</h5>
            <div class="erp-detail-text">
              ${isMobile ? '' : `<div class="mb-3"><strong class="erp-detail-label">실측일:</strong> <span class="erp-detail-value">${esc(measure)}</span></div>
              <div class="mb-3"><strong class="erp-detail-label">시공일:</strong> <span class="erp-detail-value">${esc(construct)}</span></div>`}
              ${notesHtml}
            </div>
          </div>
        </div>
      </div>`;

      container.innerHTML = `
      <div class="row g-3 erp-order-detail">
        ${basicInfoHtml}
        ${scheduleHtml}
        <div class="col-12">
          <div class="card">
            <div class="card-body">
              <h5 class="card-title fw-bold mb-3"><i class="fas fa-box text-primary"></i> 제품 항목</h5>
              ${itemsHtml}
            </div>
          </div>
        </div>
        <div class="col-12">
          <div class="card">
            <div class="card-body">
              <h5 class="card-title fw-bold mb-3"><i class="fas fa-paperclip text-primary"></i> 첨부 파일 <span class="badge bg-secondary" style="font-size: 1rem;" id="order-detail-attachments-count-${orderId}">${attachmentsPending ? '…' : `${aList.length}개`}</span></h5>
              <div id="order-detail-attachments-slot-${orderId}">${attachmentsHtml}</div>
            </div>
          </div>
        </div>
      </div>
    `;
      if (attachmentsPending) {
        container.dataset.shellLoaded = '1';
        container.dataset.attachPhase = 'loading';
        await patchConstructionDetailAttachments(orderId, gen);
      } else {
        container.dataset.loaded = '1';
        container.dataset.attachPhase = 'done';
        delete container.dataset.shellLoaded;
        delete container.dataset.attachError;
      }

    } catch (err) {
      console.error('주문 상세 로드 실패:', err);
      container.innerHTML = '<div class="text-danger small">로드 실패: ' + escapeHtml(err.message) + '</div>';
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Zone 6: 이벤트 리스너 (fragment 재실행-안전 배선, 가드 G4)
  // ═══════════════════════════════════════════════════════════════
  // erp-shell 이 메인 콘텐츠 루트 를 swap 하면 이 인라인 스크립트가 재실행된다. 그 시점엔
  // DOMContentLoaded 가 이미 발화 완료라 콜백으로 감싸면 fragment 진입 시 콜백이 영원히
  // 실행되지 않는다(→ 필터/상세/승인/알림 배선 전부 사망). 즉시 실행 IIFE 로 전환하되,
  // (1) 메인 콘텐츠 루트 내부 요소(매 swap 새 노드)는 per-swap 으로 재바인딩하고,
  // (2) document/body/window 위임·폴링은 __FOMS_CONSTR_SCRIPTS_BOUND 싱글톤으로 1회만 배선한다.
  //     scripts.html 는 dashboard_body 최하단(모든 대상 요소 뒤)에 include 되므로 즉시 실행
  //     시점에 per-swap 대상 요소가 이미 존재한다(readyState 가드 불필요).

  (() => {
    // ── per-swap 구역: 매 재실행 안전(요소가 swap 마다 교체되므로 재바인딩이 정답) ──
    // 브리핑 보드 등에서 focus_order 파라미터로 진입 시 해당 주문 행으로 스크롤 및 하이라이트
    (() => {
      const urlParams = new URLSearchParams(window.location.search);
      const focusOrder = urlParams.get('focus_order');
      if (focusOrder) {
        setTimeout(() => {
          const row = document.querySelector('.erp-main-row[data-order-id="' + focusOrder + '"]');
          if (row) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('table-info');
            setTimeout(() => row.classList.remove('table-info'), 2500);
          }
        }, 500);
      }
    })();

    const form = document.getElementById('erp-filters-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        const qInput = this.querySelector('input[name="q"]');
        if (qInput && qInput.value.trim() !== '') {
          const stageSelect = this.querySelector('select[name="stage"]');
          if (stageSelect) stageSelect.value = '';
          const teamSelect = this.querySelector('select[name="team"]');
          if (teamSelect) teamSelect.value = '';
        }

        const url = new URL(window.location.href);
        const currentAlertType = url.searchParams.get('alert_type');
        if (currentAlertType) {
          let alertTypeInput = this.querySelector('input[name="alert_type"]');
          if (!alertTypeInput) {
            alertTypeInput = document.createElement('input');
            alertTypeInput.type = 'hidden';
            alertTypeInput.name = 'alert_type';
            this.appendChild(alertTypeInput);
          }
          alertTypeInput.value = currentAlertType;
        }
      });
    }

    document.querySelectorAll('.collapse[id^="order-detail-collapse-"]').forEach(collapseEl => {
      collapseEl.addEventListener('shown.bs.collapse', async function () {
        const orderId = this.id.replace('order-detail-collapse-', '');

        const alignDetailUnderNavbar = () => {
          const nav = document.querySelector('nav.navbar');
          const navHeight = nav ? nav.offsetHeight : 56;
          const titleEl = this.querySelector('.erp-order-detail-title') || this;
          const targetTop = window.scrollY + titleEl.getBoundingClientRect().top - navHeight - 8;
          window.scrollTo({ top: Math.max(0, targetTop), behavior: 'auto' });
        };

        alignDetailUnderNavbar();
        await loadOrderDetail(parseInt(orderId, 10));
        requestAnimationFrame(alignDetailUnderNavbar);
        setTimeout(alignDetailUnderNavbar, 120);
      });
    });

    const applyFilter = (name, value) => {
      if (!form) return;

      const singleFilterNames = ['stage', 'alert_type', 'urgent', 'has_alert', 'team', 'q'];
      singleFilterNames.forEach(fieldName => {
        if (fieldName !== name) {
          let existingInput = form.querySelector(`[name="${fieldName}"]`);
          if (existingInput) {
            if (existingInput.type === 'checkbox') existingInput.checked = false;
            else existingInput.value = '';
          }
        }
      });

      let input = form.querySelector(`[name="${name}"]`);
      if (!input) {
        input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        form.appendChild(input);
      }

      const current = input.value || '';
      const next = value || '';
      input.value = (current === next) ? '' : next;
      form.submit();
    };

    document.querySelectorAll('.erp-pro-pipeline__stage[data-stage]').forEach(el => {
      const handler = () => applyFilter('stage', el.dataset.stage || '');
      el.addEventListener('click', handler);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handler();
        }
      });
    });

    document.querySelectorAll('.erp-pro-alert[data-alert-type]').forEach(el => {
      const handler = () => applyFilter('alert_type', el.dataset.alertType || '');
      el.addEventListener('click', handler);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handler();
        }
      });
    });

    // ── once-only 구역: document/body/window 위임·폴링은 싱글톤 가드로 1회만 배선 ──
    // 요소 참조를 이벤트 시점에 조회(e.target.closest / 핸들러 내부 lookup)하므로 swap 후에도
    // stale 되지 않는다. per-swap 배선(위쪽)은 이 return 이전에 매 실행 완료된다.
    if (window.__FOMS_CONSTR_SCRIPTS_BOUND) return;
    window.__FOMS_CONSTR_SCRIPTS_BOUND = true;

    document.body.addEventListener('click', function (e) {
      const approveBtn = e.target.closest('.erp-btn-approve-team');
      if (approveBtn) {
        const orderId = approveBtn.dataset.orderId;
        const team = approveBtn.dataset.team;
        if (typeof approveQuestTeam === 'function') {
          approveQuestTeam(Number(orderId), team);
        } else {
          console.warn('approveQuestTeam is not defined');
        }
      }

      const attBtn = e.target.closest('.erp-btn-attachments-preview');
      if (attBtn) {
        const orderId = attBtn.dataset.orderId;
        if (typeof openAttachmentsPreview === 'function') {
          openAttachmentsPreview(Number(orderId));
        }
      }
    });

    if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.subscribe === 'function') {
      window.FOMSNotificationBadge.subscribe('erp-construction-page-badge', renderNotificationBadge);
      window.FOMSNotificationBadge.startPolling();
    }
  })();

  // ═══════════════════════════════════════════════════════════════
  // Zone 7: 알림(Notification) 시스템
  // ═══════════════════════════════════════════════════════════════

  var notificationPanelOpen = false;

  function renderNotificationBadge(count) {
    const badge = document.getElementById('notification-badge');
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : count;
      badge.style.display = 'block';
    } else {
      badge.style.display = 'none';
    }
  }

  async function loadNotificationBadge(force) {
    if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.refresh === 'function') {
      return window.FOMSNotificationBadge.refresh({ force: !!force, reason: 'erp-construction' });
    }
  }

  async function loadNotifications() {
    const list = document.getElementById('notification-list');
    try {
      const res = await fetch('/erp/api/notifications?limit=20');
      if (!res.ok) {
        if (res.status === 429 && list) {
          list.innerHTML = '<div class="notification-empty">요청이 많아 잠시 후 다시 시도해 주세요.</div>';
        }
        return;
      }
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        if (list) list.innerHTML = '<div class="notification-empty">알림을 불러올 수 없습니다.</div>';
        return;
      }
      const data = await res.json();

      if (!data.success || !data.notifications || data.notifications.length === 0) {
        list.innerHTML = '<div class="notification-empty">알림이 없습니다.</div>';
        return;
      }

      list.innerHTML = data.notifications.map(n => {
        const safe = (v) => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return '<div class="notification-item ' + (n.is_read ? '' : 'notification-item--unread') + '" data-notification-id="' + n.id + '" data-order-id="' + (n.order_id || '') + '" data-notification-type="' + safe(n.notification_type) + '" data-deep-tab="' + safe(n.deep_tab) + '" data-deep-event-id="' + safe(n.deep_event_id) + '" data-deep-target-no="' + safe(n.deep_target_no) + '" role="button" tabindex="0">' +
          '<div class="notification-item__header">' +
          '<span class="notification-item__title">' + escapeHtml(n.title) + '</span>' +
          '<span class="notification-item__time">' + formatNotificationTime(n.created_at) + '</span>' +
          '</div>' +
          '<div class="notification-item__message">' + escapeHtml(n.message) + '</div>' +
          '<div class="notification-item__target">' +
          (n.target_manager_name ? '담당: ' + escapeHtml(n.target_manager_name) : (n.target_team ? '팀: ' + escapeHtml(n.target_team) : '')) +
          '</div></div>';
      }).join('');
    } catch (e) {
      console.error('Load notifications error:', e);
    }
  }

  (function () {
    // fragment 재실행-안전(가드 G4): body 위임은 1회만 배선. 알림 item 은 이벤트 시점
    // closest 조회, handleNotificationClick 은 호출 시점 전역 해석이라 stale 참조 없음.
    if (window.__FOMS_CONSTR_NOTIF_LIST_CLICK_BOUND) return;
    window.__FOMS_CONSTR_NOTIF_LIST_CLICK_BOUND = true;
    document.body.addEventListener('click', function (ev) {
      var item = ev.target.closest('#notification-list .notification-item[data-notification-id]');
      if (!item) return;
      ev.preventDefault();
      var id = parseInt(item.getAttribute('data-notification-id'), 10);
      var orderId = parseInt(item.getAttribute('data-order-id'), 10) || null;
      handleNotificationClick(id, orderId, item.getAttribute('data-notification-type') || '', item.getAttribute('data-deep-tab') || '', item.getAttribute('data-deep-event-id') || '', item.getAttribute('data-deep-target-no') || '');
    });
  })();

  function toggleNotificationPanel() {
    const panel = document.getElementById('notification-panel');
    notificationPanelOpen = !notificationPanelOpen;
    panel.style.display = notificationPanelOpen ? 'block' : 'none';
    if (notificationPanelOpen) {
      loadNotifications();
    }
  }

  async function handleNotificationClick(notificationId, orderId, notificationType, deepTab, deepEventId, deepTargetNo) {
    try {
      await window.FOMSNotificationWrite.fetch(`/erp/api/notifications/${notificationId}/read`, { method: 'POST' });
      loadNotificationBadge(true);

      if (orderId) {
        if (notificationType === 'DRAWING_TRANSFERRED' || notificationType === 'DRAWING_REVISION') {
          const tab = deepTab || (notificationType === 'DRAWING_REVISION' ? 'requests' : 'timeline');
          let url = `/erp/drawing-workbench/${orderId}?tab=${encodeURIComponent(tab)}`;
          if (deepEventId) url += `&event_id=${encodeURIComponent(deepEventId)}`;
          if (deepTargetNo) url += `&target_no=${encodeURIComponent(deepTargetNo)}`;
          window.location.href = url;
        } else {
          window.location.href = `/edit/${orderId}`;
        }
      }
    } catch (e) {
      console.error('Notification click error:', e);
    }
  }

  async function markAllNotificationsRead() {
    try {
      const res = await window.FOMSNotificationWrite.fetch('/erp/api/notifications/read-all', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        loadNotificationBadge(true);
        loadNotifications();
      }
    } catch (e) {
      console.error('Mark all read error:', e);
    }
  }

  function formatNotificationTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr.replace(' ', 'T'));
    const now = new Date();
    const diff = (now - date) / 1000;

    if (diff < 60) return '방금';
    if (diff < 3600) return Math.floor(diff / 60) + '분 전';
    if (diff < 86400) return Math.floor(diff / 3600) + '시간 전';
    if (diff < 604800) return Math.floor(diff / 86400) + '일 전';

    return dateStr.split(' ')[0];
  }

  // fragment 재실행-안전(가드 G4): document 위임은 1회만 배선. panel/btn 은 이벤트 시점에
  // 조회하며, 영속 리스너는 다른 탭 swap 후에도 살아있으므로 요소 부재(null) 방어가 필수다.
  (function () {
    if (window.__FOMS_CONSTR_NOTIF_OUTSIDE_CLICK_BOUND) return;
    window.__FOMS_CONSTR_NOTIF_OUTSIDE_CLICK_BOUND = true;
    document.addEventListener('click', function (e) {
      const panel = document.getElementById('notification-panel');
      const btn = document.getElementById('notification-btn');
      if (!panel || !btn) return;
      if (notificationPanelOpen && !panel.contains(e.target) && !btn.contains(e.target)) {
        toggleNotificationPanel();
      }
    });
  })();
