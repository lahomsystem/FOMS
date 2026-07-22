/**
 * ERP 단계 강제 변경 (역행·건너뛰기) — Spec 2026-07-15
 * defer + fragment 재실행 idempotent (window.__FOMS_STAGE_OVERRIDE_BOUND)
 */
(function () {
  'use strict';

  var RANK = {
    RECEIVED: 0,
    MEASURE: 1,
    DRAWING: 2,
    CONFIRM: 3,
    PRODUCTION: 4,
    CONSTRUCTION: 5,
    CS: 6,
    COMPLETED: 7
  };

  var LABELS = {
    RECEIVED: '주문접수',
    MEASURE: '실측',
    DRAWING: '도면',
    CONFIRM: '고객컨펌',
    PRODUCTION: '생산',
    CONSTRUCTION: '시공',
    CS: 'CS',
    COMPLETED: '완료'
  };

  var BLOCK_MSG =
    '단계 역행/건너뛰기는 「단계 강제 변경」에서 사유·확인 후 진행하세요.';

  function rankOf(code) {
    var c = String(code || '').trim();
    return Object.prototype.hasOwnProperty.call(RANK, c) ? RANK[c] : -1;
  }

  function classifyMove(from, to) {
    var fr = rankOf(from);
    var tr = rankOf(to);
    if (!from || !to || String(from) === String(to)) return 'same';
    if (fr < 0 || tr < 0) return 'jump';
    if (tr < fr) return 'regress';
    if (tr === fr + 1) return 'advance';
    if (tr > fr + 1) return 'skip';
    return 'same';
  }

  function needsOverride(from, to) {
    var mode = classifyMove(from, to);
    return mode === 'regress' || mode === 'skip' || mode === 'jump';
  }

  function modeHint(mode) {
    if (mode === 'regress') return '역행 — 사유·확인 필수';
    if (mode === 'skip') return '단계 건너뛰기 — 사유·확인 필수';
    if (mode === 'advance') return '인접 전진 (일반 경로도 가능)';
    if (mode === 'jump') return '특수 이동 — 사유·확인 필수';
    return '';
  }

  function resolveOrderId(explicit) {
    if (explicit) return Number(explicit);
    var cfg = document.getElementById('erp-order-config');
    if (cfg && cfg.dataset.orderId) return Number(cfg.dataset.orderId);
    var card = document.querySelector('[data-erp-order-id]');
    if (card && card.getAttribute('data-erp-order-id')) {
      return Number(card.getAttribute('data-erp-order-id'));
    }
    return 0;
  }

  function canOverride() {
    var modal = document.getElementById('erpStageOverrideModal');
    if (modal && modal.getAttribute('data-can-stage-override') === '1') return true;
    var role = String(window.MY_ROLE || '').toUpperCase();
    return role === 'ADMIN' || role === 'MANAGER';
  }

  function currentStageFromUi() {
    var el = document.getElementById('erp-workflow-stage');
    if (el && el.value) return String(el.value).trim();
    return '';
  }

  function showError(msg) {
    var box = document.getElementById('erp-stage-override-error');
    if (!box) return;
    box.textContent = msg || '';
    box.classList.toggle('d-none', !msg);
  }

  function syncModeHint() {
    var fromEl = document.getElementById('erp-stage-override-from');
    var toEl = document.getElementById('erp-stage-override-to');
    var hint = document.getElementById('erp-stage-override-mode-hint');
    if (!fromEl || !toEl || !hint) return;
    var from = fromEl.getAttribute('data-stage-code') || '';
    var to = toEl.value;
    var mode = classifyMove(from, to);
    hint.textContent = modeHint(mode);
  }

  var _pending = null;
  var _modalHideWired = false;

  function settlePendingCancel() {
    var pending = _pending;
    if (!pending) return;
    _pending = null;
    if (pending.opts && typeof pending.opts.onCancel === 'function') {
      try {
        pending.opts.onCancel();
      } catch (e) { /* ignore */ }
    }
    if (typeof pending.reject === 'function') {
      pending.reject(new Error('cancelled'));
    }
  }

  function openModal(opts) {
    opts = opts || {};
    if (!canOverride()) {
      window.alert(BLOCK_MSG);
      return Promise.reject(new Error('forbidden'));
    }
    var orderId = resolveOrderId(opts.orderId);
    if (!orderId) {
      window.alert('저장 후 주문번호가 생긴 뒤 단계 강제 변경을 사용할 수 있습니다.');
      return Promise.reject(new Error('no-order'));
    }
    var from = String(opts.fromStage || currentStageFromUi() || '').trim();
    var to = String(opts.toStage || '').trim();

    var fromEl = document.getElementById('erp-stage-override-from');
    var toEl = document.getElementById('erp-stage-override-to');
    var reasonEl = document.getElementById('erp-stage-override-reason');
    var confirmEl = document.getElementById('erp-stage-override-confirm');
    var modalEl = document.getElementById('erpStageOverrideModal');
    if (!modalEl || !fromEl || !toEl) {
      window.alert('단계 강제 변경 UI를 찾을 수 없습니다.');
      return Promise.reject(new Error('no-ui'));
    }

    fromEl.textContent = (LABELS[from] || from || '—') + (from ? ' (' + from + ')' : '');
    fromEl.setAttribute('data-stage-code', from);
    if (to && Object.prototype.hasOwnProperty.call(RANK, to)) {
      toEl.value = to;
    }
    if (reasonEl) reasonEl.value = '';
    if (confirmEl) confirmEl.checked = false;
    showError('');
    syncModeHint();

    return new Promise(function (resolve, reject) {
      // 이전 미완료 pending 있으면 취소로 정리(드롭다운 revert)
      settlePendingCancel();
      _pending = {
        orderId: orderId,
        resolve: resolve,
        reject: reject,
        opts: opts,
        fromStage: from,
        toStage: to
      };
      if (window.bootstrap && window.bootstrap.Modal) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      } else {
        modalEl.classList.add('show');
        modalEl.style.display = 'block';
      }
    });
  }

  function closeModal() {
    var modalEl = document.getElementById('erpStageOverrideModal');
    if (!modalEl) return;
    if (window.bootstrap && window.bootstrap.Modal) {
      var inst = window.bootstrap.Modal.getInstance(modalEl);
      if (inst) inst.hide();
    } else {
      modalEl.classList.remove('show');
      modalEl.style.display = 'none';
      // bootstrap 없으면 hide 이벤트 없음 → 수동 정리 불필요(성공 시 _pending 이미 null)
    }
  }

  function submitOverride() {
    if (!_pending) return;
    var toEl = document.getElementById('erp-stage-override-to');
    var reasonEl = document.getElementById('erp-stage-override-reason');
    var confirmEl = document.getElementById('erp-stage-override-confirm');
    var to = toEl ? toEl.value : '';
    var reason = reasonEl ? String(reasonEl.value || '').trim() : '';
    var confirm = confirmEl ? confirmEl.checked : false;
    if (!to) {
      showError('목표 단계를 선택하세요.');
      return;
    }
    if (reason.length < 8) {
      showError('사유는 8자 이상 입력하세요.');
      return;
    }
    if (!confirm) {
      showError('확인 체크가 필요합니다.');
      return;
    }
    var orderId = _pending.orderId;
    var btn = document.getElementById('erp-stage-override-submit');
    if (btn) btn.disabled = true;
    showError('');

    fetch('/api/orders/' + orderId + '/workflow/stage-override', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ to_stage: to, reason: reason, confirm: true })
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, status: r.status, data: data };
        });
      })
      .then(function (res) {
        if (!res.data || !res.data.success) {
          showError((res.data && (res.data.error || res.data.message)) || '변경 실패');
          return;
        }
        var stageEl = document.getElementById('erp-workflow-stage');
        if (stageEl) stageEl.value = to;
        if (window.__erpLastStructuredData && typeof window.__erpLastStructuredData === 'object') {
          window.__erpLastStructuredData.workflow =
            window.__erpLastStructuredData.workflow || {};
          window.__erpLastStructuredData.workflow.stage = to;
        }
        var pending = _pending;
        _pending = null; // hide.bs.modal 이 cancel로 취급하지 않도록 선제 클리어
        closeModal();
        if (pending && pending.resolve) pending.resolve(res.data);
        if (pending && pending.opts && typeof pending.opts.onSuccess === 'function') {
          pending.opts.onSuccess(res.data);
        } else if (!pending || !pending.opts || !pending.opts.skipReload) {
          window.location.reload();
        }
      })
      .catch(function () {
        showError('서버 통신 오류');
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  function wireUi() {
    var openBtns = document.querySelectorAll('[data-erp-stage-override-open]');
    openBtns.forEach(function (btn) {
      if (btn.getAttribute('data-bound') === '1') return;
      btn.setAttribute('data-bound', '1');
      if (!canOverride()) {
        btn.classList.add('d-none');
        return;
      }
      btn.classList.remove('d-none');
      btn.addEventListener('click', function () {
        openModal({ orderId: btn.getAttribute('data-order-id') || null });
      });
    });

    var toEl = document.getElementById('erp-stage-override-to');
    if (toEl && toEl.getAttribute('data-bound') !== '1') {
      toEl.setAttribute('data-bound', '1');
      toEl.addEventListener('change', syncModeHint);
    }
    var submit = document.getElementById('erp-stage-override-submit');
    if (submit && submit.getAttribute('data-bound') !== '1') {
      submit.setAttribute('data-bound', '1');
      submit.addEventListener('click', submitOverride);
    }

    var modalEl = document.getElementById('erpStageOverrideModal');
    if (modalEl && !_modalHideWired) {
      _modalHideWired = true;
      // 취소/ESC/배경 클릭 → pending 정리 + 드롭다운 원복(onCancel/onDone false)
      modalEl.addEventListener('hide.bs.modal', function () {
        if (_pending) settlePendingCancel();
      });
    }

    var stageEl = document.getElementById('erp-workflow-stage');
    if (stageEl && stageEl.getAttribute('data-override-guard') !== '1') {
      stageEl.setAttribute('data-override-guard', '1');
      var lastOk = stageEl.value;
      stageEl.addEventListener('focus', function () {
        lastOk = stageEl.value;
      });
      stageEl.addEventListener('change', function () {
        var next = stageEl.value;
        // AS 경로는 기존 asReceiveModal 이 담당
        if (next === 'AS_RECEIVED' || next === 'AS_COMPLETED' || next === 'AS') {
          lastOk = next;
          return;
        }
        if (needsOverride(lastOk, next)) {
          stageEl.value = lastOk;
          if (canOverride()) {
            openModal({ fromStage: lastOk, toStage: next, skipReload: false });
          } else {
            window.alert(BLOCK_MSG);
          }
          return;
        }
        lastOk = next;
      });
    }
  }

  /**
   * 대시보드 status-dropdown 용: 역행/스킵이면 override 모달, 아니면 false.
   * @returns {boolean} true면 호출측이 일반 update_order_status 를 건너뛴다.
   */
  function interceptStatusChange(orderId, fromStatus, toStatus, onDone) {
    if (!needsOverride(fromStatus, toStatus)) return false;
    if (!canOverride()) {
      window.alert(BLOCK_MSG);
      if (typeof onDone === 'function') onDone(false);
      return true;
    }
    openModal({
      orderId: orderId,
      fromStage: fromStatus,
      toStage: toStatus,
      skipReload: true,
      onSuccess: function () {
        if (typeof onDone === 'function') onDone(true);
        else window.location.reload();
      },
      onCancel: function () {
        if (typeof onDone === 'function') onDone(false);
      }
    }).catch(function (err) {
      // hide.bs.modal 취소는 onCancel 으로 이미 처리. 그 외 early reject 만.
      if (err && String(err.message || '') === 'cancelled') return;
      if (typeof onDone === 'function') onDone(false);
    });
    return true;
  }

  window.FOMS_STAGE_OVERRIDE = {
    RANK: RANK,
    LABELS: LABELS,
    BLOCK_MSG: BLOCK_MSG,
    classifyMove: classifyMove,
    needsOverride: needsOverride,
    canOverride: canOverride,
    openModal: openModal,
    interceptStatusChange: interceptStatusChange,
    wireUi: wireUi
  };

  function boot() {
    wireUi();
  }

  if (!window.__FOMS_STAGE_OVERRIDE_BOUND) {
    window.__FOMS_STAGE_OVERRIDE_BOUND = true;
    document.addEventListener('DOMContentLoaded', boot);
    document.addEventListener('foms:main-content-swapped', boot);
    document.addEventListener('foms:erp-shell-fragment-swapped', boot);
  }
  boot();
})();
