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

  var _guardLastOk = '';

  function noteCurrentStage(code) {
    var next = String(code || '').trim();
    if (next) _guardLastOk = next;
  }

  function forceMoveNotice(from, to) {
    var fromLabel = LABELS[from] || from || '현재 단계';
    var toLabel = LABELS[to] || to || '목표 단계';
    return (
      '「' + fromLabel + '」에서 「' + toLabel + '」(으)로는 바로 이동할 수 없습니다.\n' +
      '단계 강제 변경이 필요합니다.'
    );
  }

  function confirmForceMove(from, to) {
    return window.confirm(forceMoveNotice(from, to) + '\n계속할까요?');
  }

  function confirmForceMoveBulk(count, to) {
    var toLabel = LABELS[to] || to || '목표 단계';
    return window.confirm(
      '선택한 ' + count + '건은 「' + toLabel + '」(으)로 바로 이동할 수 없습니다.\n' +
      '단계 강제 변경이 필요합니다.\n계속할까요?'
    );
  }

  function formatFromStages(fromStages) {
    var seen = {};
    var labels = [];
    (fromStages || []).forEach(function (code) {
      var c = String(code || '').trim();
      if (!c || seen[c]) return;
      seen[c] = 1;
      labels.push((LABELS[c] || c) + ' (' + c + ')');
    });
    if (!labels.length) return '—';
    if (labels.length === 1) return labels[0];
    return '여러 단계: ' + labels.join(', ');
  }

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

  var LOGISTICS_CODES = {
    MEASURED: 1,
    REGIONAL_MEASURED: 1,
    SCHEDULED: 1,
    SHIPPED_PENDING: 1,
    COMPLETED: 1,
    AS_RECEIVED: 1,
    AS_COMPLETED: 1,
    AS: 1,
    ON_HOLD: 1,
    DELETED: 1
  };

  function isLogisticsCode(code) {
    return !!LOGISTICS_CODES[String(code || '').trim()];
  }

  function needsOverride(from, to) {
    // 물류↔물류만 보드 confirm 경로. 메인→COMPLETED 등 ERP 폼 스킵은 계속 override.
    if (isLogisticsCode(from) && isLogisticsCode(to)) return false;
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

  // STATE-FORM-01 stale tab 방어: override 는 서버 mutation_version 을 If-Match 로 실어
  // 오래된 탭이 상태를 덮어쓰지 못하게 한다. 폼 GET/저장이 노출한 최신 버전을 재사용하고,
  // 알 수 없으면 헤더를 생략한다(서버는 precondition 없이 진행 — 하위호환).
  function currentMutationVersion() {
    var v = window.__erpLastMutationVersion;
    return typeof v === 'number' && isFinite(v) ? v : null;
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
    var orderIds = [];
    if (opts.orderIds && opts.orderIds.length) {
      opts.orderIds.forEach(function (raw) {
        var n = Number(raw);
        if (n > 0) orderIds.push(n);
      });
    } else {
      var one = resolveOrderId(opts.orderId);
      if (one) orderIds = [one];
    }
    if (!orderIds.length) {
      window.alert('저장 후 주문번호가 생긴 뒤 단계 강제 변경을 사용할 수 있습니다.');
      return Promise.reject(new Error('no-order'));
    }
    var fromStages = (opts.fromStages && opts.fromStages.length)
      ? opts.fromStages
      : [String(opts.fromStage || currentStageFromUi() || '').trim()];
    var from = String(fromStages[0] || '').trim();
    var to = String(opts.toStage || '').trim();

    var fromEl = document.getElementById('erp-stage-override-from');
    var toEl = document.getElementById('erp-stage-override-to');
    var reasonEl = document.getElementById('erp-stage-override-reason');
    var confirmEl = document.getElementById('erp-stage-override-confirm');
    var bulkHint = document.getElementById('erp-stage-override-bulk-hint');
    var modalEl = document.getElementById('erpStageOverrideModal');
    if (!modalEl || !fromEl || !toEl) {
      window.alert('단계 강제 변경 UI를 찾을 수 없습니다.');
      return Promise.reject(new Error('no-ui'));
    }

    fromEl.textContent = formatFromStages(fromStages);
    fromEl.setAttribute('data-stage-code', from);
    if (to && Object.prototype.hasOwnProperty.call(RANK, to)) {
      toEl.value = to;
    }
    if (reasonEl) reasonEl.value = '';
    if (confirmEl) confirmEl.checked = false;
    if (bulkHint) {
      if (orderIds.length > 1) {
        bulkHint.textContent = '선택한 ' + orderIds.length + '건을 같은 사유로 일괄 변경합니다.';
        bulkHint.classList.remove('d-none');
      } else {
        bulkHint.textContent = '';
        bulkHint.classList.add('d-none');
      }
    }
    showError('');
    syncModeHint();

    return new Promise(function (resolve, reject) {
      // 이전 미완료 pending 있으면 취소로 정리(드롭다운 revert)
      settlePendingCancel();
      _pending = {
        orderId: orderIds[0],
        orderIds: orderIds,
        bulk: !!opts.bulk || orderIds.length > 1,
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
    if (!reason) {
      showError('사유를 입력하세요.');
      return;
    }
    if (!confirm) {
      showError('확인 체크가 필요합니다.');
      return;
    }
    var orderIds = (_pending.orderIds && _pending.orderIds.length)
      ? _pending.orderIds
      : [_pending.orderId];
    var isBulk = !!_pending.bulk;
    var btn = document.getElementById('erp-stage-override-submit');
    if (btn) btn.disabled = true;
    showError('');

    var headers = {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    };
    if (!isBulk) {
      var ifMatch = currentMutationVersion();
      if (ifMatch !== null) headers['If-Match'] = String(ifMatch);
    }

    var url = isBulk
      ? '/api/orders/workflow/stage-override/bulk'
      : '/api/orders/' + orderIds[0] + '/workflow/stage-override';
    var body = isBulk
      ? { order_ids: orderIds, to_stage: to, reason: reason, confirm: true }
      : { to_stage: to, reason: reason, confirm: true };

    fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(body)
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, status: r.status, data: data };
        });
      })
      .then(function (res) {
        if (res.status === 409) {
          showError('다른 탭/사용자가 이미 상태를 변경했습니다. 새로고침 후 다시 시도하세요.');
          return;
        }
        if (!res.data || !res.data.success) {
          showError((res.data && (res.data.error || res.data.message)) || '변경 실패');
          return;
        }
        // 최신 mutation_version 을 갱신해 다음 override/저장이 stale 되지 않게 한다.
        if (res.data.data && typeof res.data.data.mutation_version === 'number') {
          window.__erpLastMutationVersion = res.data.data.mutation_version;
        }
        var stageEl = document.getElementById('erp-workflow-stage');
        if (stageEl) stageEl.value = to;
        if (window.__erpLastStructuredData && typeof window.__erpLastStructuredData === 'object') {
          window.__erpLastStructuredData.workflow =
            window.__erpLastStructuredData.workflow || {};
          window.__erpLastStructuredData.workflow.stage = to;
        }
        // AS 접수/완료 주문은 일괄 강제 변경에서 제외된다(AS 대시보드 증발 방지).
        var skippedAs = (res.data.data && res.data.data.skipped_as) || [];
        if (skippedAs.length) {
          alert('AS 상태라 제외한 주문 ' + skippedAs.length + '건: '
            + skippedAs.map(function (it) { return '#' + it.order_id; }).join(', ')
            + '\n' + (res.data.data.warning || ''));
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
      _guardLastOk = stageEl.value;
      stageEl.addEventListener('focus', function () {
        _guardLastOk = stageEl.value;
      });
      stageEl.addEventListener('change', function () {
        var from = _guardLastOk || stageEl.value;
        var next = stageEl.value;
        // AS 경로는 기존 asReceiveModal 이 담당
        if (next === 'AS_RECEIVED' || next === 'AS_COMPLETED' || next === 'AS') {
          _guardLastOk = next;
          return;
        }
        if (needsOverride(from, next)) {
          stageEl.value = from;
          if (!canOverride()) {
            window.alert(forceMoveNotice(from, next) + '\n관리자만 강제 변경할 수 있습니다.');
            return;
          }
          if (!confirmForceMove(from, next)) {
            return;
          }
          openModal({ fromStage: from, toStage: next, skipReload: false });
          return;
        }
        _guardLastOk = next;
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
      window.alert(forceMoveNotice(fromStatus, toStatus) + '\n관리자만 강제 변경할 수 있습니다.');
      if (typeof onDone === 'function') onDone(false);
      return true;
    }
    if (!confirmForceMove(fromStatus, toStatus)) {
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

  /**
   * 그리드 일괄 적용: 역행/스킵 대상은 강제 변경 모달, 인접 전진은 호출측 bulk_update.
   * @returns {boolean} true면 호출측이 일반 bulk_update 를 건너뛴다.
   */
  function interceptBulkStatusChange(items, toStatus, handlers) {
    handlers = handlers || {};
    var to = String(toStatus || '').trim();
    if (!to || !Object.prototype.hasOwnProperty.call(RANK, to)) return false;
    var list = Array.isArray(items) ? items : [];
    var overrideItems = [];
    var normalIds = [];
    list.forEach(function (it) {
      var id = it && it.orderId != null ? String(it.orderId) : '';
      if (!id) return;
      var from = String((it && it.fromStage) || '').trim();
      if (!from || needsOverride(from, to)) overrideItems.push(it);
      else normalIds.push(id);
    });
    if (!overrideItems.length) return false;

    function done(ok) {
      if (typeof handlers.onDone === 'function') handlers.onDone(ok);
    }

    if (!canOverride()) {
      window.alert(forceMoveNotice(overrideItems[0].fromStage, to) + '\n관리자만 강제 변경할 수 있습니다.');
      done(false);
      return true;
    }
    if (!confirmForceMoveBulk(overrideItems.length, to)) {
      done(false);
      return true;
    }
    var overrideIds = overrideItems.map(function (it) { return it.orderId; });
    var fromStages = overrideItems.map(function (it) { return it.fromStage; });
    openModal({
      orderIds: overrideIds,
      fromStages: fromStages,
      toStage: to,
      bulk: true,
      skipReload: true,
      onSuccess: function () {
        if (normalIds.length && typeof handlers.applyNormal === 'function') {
          handlers.applyNormal(normalIds);
        } else {
          done(true);
          window.location.reload();
        }
      },
      onCancel: function () {
        done(false);
      }
    }).catch(function (err) {
      if (err && String(err.message || '') === 'cancelled') return;
      done(false);
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
    interceptBulkStatusChange: interceptBulkStatusChange,
    noteCurrentStage: noteCurrentStage,
    confirmForceMove: confirmForceMove,
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
