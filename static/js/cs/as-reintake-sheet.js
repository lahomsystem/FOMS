/**
 * AS 재접수 바텀시트 배선 (모바일 v2 카드 · 목업 2-B).
 *
 * 완료된 AS 카드의 [data-as-reintake-open] 탭 → templates/cs/partials/as_reintake_sheet.html
 * 의 offcanvas 를 열고, 증상/재발/(사무실 전용)비용/사진을 받아
 * POST /api/orders/<id>/as/register 로 보낸다. 새 URL 도 새 업로드 경로도 만들지 않는다 —
 * 첨부는 기존 window.fomsUploadOrderAttachmentsBatch(category='as' + as_log_id) 를 재사용한다.
 *
 * as_dashboard_body.html 에서 defer 로 실린다. erp-shell 의 fast-tab fragment 스왑은
 * 스크립트를 매번 재실행하므로 파일 전체가 싱글턴 가드 뒤에 있고, 리스너는 document 위임이다
 * (perf guard G4 idempotent).
 */
(function () {
  'use strict';
  if (window.__FOMS_AS_REINTAKE_SHEET_BOUND) return;
  window.__FOMS_AS_REINTAKE_SHEET_BOUND = true;

  var SHEET_ID = 'erp-as-reintake-sheet';
  var state = { orderId: null, nextCycleNo: 0, files: [], submitting: false };

  function sheetEl() { return document.getElementById(SHEET_ID); }
  function q(selector) {
    var root = sheetEl();
    return root ? root.querySelector(selector) : null;
  }

  /** 대시보드 공용 토스트(#saveToast) 재사용 — 없으면 모바일 셸 토스트로 떨어진다. */
  function toast(message, isError) {
    var el = document.getElementById('saveToast');
    var msgEl = document.getElementById('toastMessage');
    if (el && msgEl && window.bootstrap && window.bootstrap.Toast) {
      msgEl.textContent = message;
      el.classList.remove('bg-success', 'bg-danger');
      el.classList.add(isError ? 'bg-danger' : 'bg-success');
      window.bootstrap.Toast.getOrCreateInstance(el, { delay: 2600 }).show();
      return;
    }
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(message);
      return;
    }
    window.alert(message);
  }

  function setStatus(message, isError) {
    var el = q('[data-as-reintake-status]');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('is-error', !!isError);
    el.hidden = !message;
  }

  /**
   * 지난 건 요약 줄들을 만든다. 값이 없는 조각은 통째로 뺀다(추정 금지 — 봉인 안 된
   * 옛 건은 완료일·비용이 아예 없다).
   */
  function buildPrevLines(data) {
    var lines = [];
    var unknown = data.prevUnknown === '1';
    var ordinal = parseInt(data.prevOrdinal || '0', 10) || 0;
    var head = unknown ? '이력 시작 전' : (ordinal > 0 ? ordinal + '번째 AS' : '');
    var when = [];
    if (unknown) {
      when.push('접수일 불명');
    } else if (data.prevReceived) {
      when.push(data.prevReceived + ' 접수');
    }
    if (data.prevCompleted) when.push(data.prevCompleted + ' 완료');
    if (head || when.length) lines.push([head, when.join(' · ')].filter(Boolean).join(' · '));
    if (data.prevBilling) lines.push('비용 ' + data.prevBilling);
    return lines;
  }

  function fillPrev(data) {
    var box = q('[data-as-reintake-prev]');
    var body = q('[data-as-reintake-prev-body]');
    if (!box || !body) return;
    var lines = buildPrevLines(data);
    body.textContent = '';
    if (!lines.length) {
      box.hidden = true;
      box.open = false;
      return;
    }
    lines.forEach(function (line) {
      var row = document.createElement('div');
      row.className = 'erp-as-reintake-sheet__prev-line';
      row.textContent = line;
      body.appendChild(row);
    });
    box.hidden = false;
    box.open = false;
  }

  function resetForm() {
    state.files = [];
    var content = q('[data-as-reintake-content]');
    if (content) content.value = '';
    var recur = q('[data-as-reintake-recurrence]');
    if (recur) recur.checked = false;
    var files = q('[data-as-reintake-files]');
    if (files) files.value = '';
    var count = q('[data-as-reintake-photo-count]');
    if (count) count.textContent = '0장';
    var amountWrap = q('[data-as-reintake-amount-wrap]');
    if (amountWrap) amountWrap.hidden = true;
    var amount = q('[data-as-reintake-amount]');
    if (amount) amount.value = '';
    var root = sheetEl();
    if (root) {
      root.querySelectorAll('[data-as-reintake-billing]').forEach(function (btn) {
        btn.classList.toggle('is-on', btn.getAttribute('data-as-reintake-billing') === 'free');
      });
    }
    setStatus('');
  }

  function openSheet(btn) {
    var root = sheetEl();
    if (!root || !window.bootstrap || !window.bootstrap.Offcanvas) return;
    var data = btn.dataset;
    state.orderId = data.orderId || null;
    state.nextCycleNo = parseInt(data.asNextCycleNo || '0', 10) || 0;
    resetForm();

    var titleEl = q('[data-as-reintake-title]');
    if (titleEl) {
      titleEl.textContent = state.nextCycleNo > 1
        ? state.nextCycleNo + '번째 AS 접수'
        : 'AS 접수';
    }
    var subEl = q('[data-as-reintake-sub]');
    if (subEl) {
      var name = (data.asCustomerName || '').trim();
      subEl.textContent = '주문 #' + (state.orderId || '') + (name ? ' · ' + name : '');
    }
    fillPrev(data);
    window.bootstrap.Offcanvas.getOrCreateInstance(root).show();
    var content = q('[data-as-reintake-content]');
    if (content) {
      // iOS 는 offcanvas 애니메이션 중 focus 하면 캐럿이 화면 밖으로 튄다 → 전이 후에.
      window.setTimeout(function () { content.focus(); }, 320);
    }
  }

  function closeSheet() {
    var root = sheetEl();
    if (!root || !window.bootstrap || !window.bootstrap.Offcanvas) return;
    var instance = window.bootstrap.Offcanvas.getInstance(root);
    if (instance) instance.hide();
  }

  function selectedBillingType() {
    var on = q('[data-as-reintake-billing].is-on');
    return on ? on.getAttribute('data-as-reintake-billing') : '';
  }

  /** 재접수 성공 뒤 이동할 대시보드 URL(미완료 탭 + 그 주문으로 포커스). */
  function incompleteTabUrl(orderId) {
    var current = new URLSearchParams(window.location.search);
    var params = new URLSearchParams();
    ['sort_dir', 'mine', 'billing', 'q'].forEach(function (key) {
      var value = current.get(key);
      if (value) params.set(key, value);
    });
    params.set('tab', 'incomplete');
    params.set('status', 'AS_RECEIVED');
    params.set('focus_order', String(orderId));
    return '/erp/as?' + params.toString();
  }

  /**
   * 접수 기록에 사진을 결합한다. 업로드만 실패해도 접수는 되돌리지 않는다 —
   * as_log 는 append-only 라 롤백이 흔적을 남기고, 사용자가 쓴 증상이 사라지는 쪽이 더 나쁘다.
   */
  async function uploadPhotos(orderId, receptionLogId) {
    if (!state.files.length) return;
    if (typeof window.fomsUploadOrderAttachmentsBatch !== 'function') {
      toast('사진 업로드 모듈을 불러오지 못했습니다. 접수는 저장됐어요.', true);
      return;
    }
    var files = state.files;
    var result = await window.fomsUploadOrderAttachmentsBatch({
      orderId: orderId,
      files: files,
      folder: 'orders/' + orderId + '/attachments',
      category: 'as',
      asLogId: receptionLogId || null,
      sortOrders: files.map(function (_file, index) { return index; }),
      useDirectUpload: true,
      onUploadProgress: function (info) {
        setStatus('사진 올리는 중... (' + Math.round(info.done) + '/' + info.total + ')');
      },
    });
    if (result && result.ok !== result.total) {
      toast('사진 ' + (result.total - result.ok) + '장 업로드 실패 — 접수는 저장됐어요.', true);
    }
  }

  async function submit() {
    if (state.submitting || !state.orderId) return;
    var contentEl = q('[data-as-reintake-content]');
    var content = contentEl ? contentEl.value.trim() : '';
    if (!content) {
      setStatus('이번에 생긴 문제를 적어주세요.', true);
      if (contentEl) contentEl.focus();
      return;
    }
    var payload = { as_content: content, source_screen: 'erp_as_dashboard_mobile' };
    var recur = q('[data-as-reintake-recurrence]');
    if (recur && recur.checked) payload.recurrence = true;
    var billingType = selectedBillingType();
    if (billingType) {
      payload.billing_type = billingType;
      if (billingType === 'paid') {
        var amountEl = q('[data-as-reintake-amount]');
        var amount = amountEl ? parseInt(amountEl.value, 10) : NaN;
        if (!isNaN(amount) && amount > 0) payload.amount = amount;
      }
    }

    var submitBtn = q('[data-as-reintake-submit]');
    state.submitting = true;
    if (submitBtn) submitBtn.disabled = true;
    setStatus('접수하는 중...');
    var orderId = state.orderId;
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      var data = await res.json();
      if (!data || !data.success) {
        throw new Error((data && data.message) || 'AS 접수에 실패했습니다.');
      }
      await uploadPhotos(orderId, data.reception_log_id);
      closeSheet();
      var cycleNo = parseInt(data.cycle_no, 10) || 0;
      toast(data.is_new_cycle && cycleNo > 1
        ? cycleNo + '번째 AS로 접수했어요.'
        : 'AS 접수 내용을 저장했어요.');
      window.location.href = incompleteTabUrl(orderId);
    } catch (err) {
      var message = (err && err.message) ? err.message : '네트워크 오류가 발생했습니다.';
      setStatus(message, true);
      toast(message, true);
    } finally {
      state.submitting = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  document.addEventListener('click', function (e) {
    var target = e.target;
    if (!target || !target.closest) return;

    var opener = target.closest('[data-as-reintake-open]');
    if (opener) {
      e.preventDefault();
      openSheet(opener);
      return;
    }
    if (!target.closest('#' + SHEET_ID)) return;

    var seg = target.closest('[data-as-reintake-billing]');
    if (seg) {
      e.preventDefault();
      var root = sheetEl();
      if (root) {
        root.querySelectorAll('[data-as-reintake-billing]').forEach(function (btn) {
          btn.classList.toggle('is-on', btn === seg);
        });
      }
      var wrap = q('[data-as-reintake-amount-wrap]');
      if (wrap) wrap.hidden = seg.getAttribute('data-as-reintake-billing') !== 'paid';
      return;
    }

    if (target.closest('[data-as-reintake-photo]')) {
      e.preventDefault();
      var filesInput = q('[data-as-reintake-files]');
      if (filesInput) filesInput.click();
      return;
    }

    if (target.closest('[data-as-reintake-submit]')) {
      e.preventDefault();
      submit();
    }
  });

  document.addEventListener('change', function (e) {
    var input = e.target && e.target.closest && e.target.closest('[data-as-reintake-files]');
    if (!input) return;
    state.files = input.files ? Array.prototype.slice.call(input.files) : [];
    var count = q('[data-as-reintake-photo-count]');
    if (count) count.textContent = state.files.length + '장';
  });
}());
