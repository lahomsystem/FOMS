/**
 * Drawing workbench dashboard: batch assign, pipeline filters, row navigation.
 * Idempotent init for ERP shell fragment swap (activateScripts re-runs inline `let` breaks).
 */
(function () {
  'use strict';

  var drawingUsersCache = null;
  var singleAssignOrderId = 0;
  var filterSubmitTimeout = null;
  var initAbortController = null;
  // 전송 모달이 소비할 대상 주문 [{id, pending}]. 테이블 일괄전송·전달 대기함 둘 다 여기에 실어 공유한다.
  var pendingTransferOrders = null;

  function isDrawingWorkbenchDashboard() {
    return !!document.querySelector('#main-content .dw-process-map, .dw-process-map');
  }

  function toggleSelectAll(checkbox) {
    document.querySelectorAll('.order-checkbox').forEach(function (cb) {
      cb.checked = checkbox.checked;
    });
    updateBatchBar();
  }

  function updateBatchBar() {
    var checkboxes = document.querySelectorAll('.order-checkbox:checked');
    var count = checkboxes.length;
    var bar = document.getElementById('batch-action-bar');
    var countSpan = document.getElementById('selected-count');
    if (!bar || !countSpan) {
      return;
    }
    if (count > 0) {
      bar.classList.remove('d-none');
      bar.classList.add('d-flex');
      countSpan.textContent = String(count);
    } else {
      bar.classList.remove('d-flex');
      bar.classList.add('d-none');
      var selectAll = document.getElementById('select-all');
      if (selectAll) {
        selectAll.checked = false;
      }
    }
  }

  function clearAllSelections() {
    document.querySelectorAll('.order-checkbox').forEach(function (cb) {
      cb.checked = false;
    });
    var selectAll = document.getElementById('select-all');
    if (selectAll) {
      selectAll.checked = false;
    }
    updateBatchBar();
  }

  function getSelectedOrderIds() {
    return Array.from(document.querySelectorAll('.order-checkbox:checked')).map(function (cb) {
      return parseInt(cb.value, 10);
    });
  }

  function getSelectedPendingOrders() {
    // 선택된 행 중 전달 대기 도면(data-pending>0)이 있는 주문만. [{id, pending}].
    return Array.from(document.querySelectorAll('.order-checkbox:checked'))
      .map(function (cb) {
        return {
          id: parseInt(cb.value, 10),
          pending: parseInt(cb.dataset.pending || '0', 10) || 0,
        };
      })
      .filter(function (o) {
        return o.pending > 0;
      });
  }

  function collectPendingBoxSelected() {
    // 전달 대기함 카드에서 체크된 주문 [{id, pending}] (pending>0 만).
    return Array.from(document.querySelectorAll('.dw-pending-check:checked'))
      .map(function (cb) {
        return {
          id: parseInt(cb.value, 10),
          pending: parseInt(cb.dataset.pending || '0', 10) || 0,
        };
      })
      .filter(function (o) {
        return o.pending > 0;
      });
  }

  function openTransferModalFor(orders, extraSummary) {
    // 전송 대상 [{id, pending}] 을 실어 공용 전송 모달을 연다. 실행부(runner)는 pendingTransferOrders 를 읽는다.
    if (!orders || orders.length === 0) {
      alert('전달 대기 도면이 있는 주문이 없습니다.');
      return;
    }
    var modalEl = document.getElementById('batchTransferModal');
    if (!modalEl || !window.bootstrap) {
      return;
    }
    pendingTransferOrders = orders;

    var summaryEl = document.getElementById('batch-transfer-summary');
    if (summaryEl) {
      var totalPending = orders.reduce(function (acc, o) {
        return acc + o.pending;
      }, 0);
      var text = '전송 대상 ' + orders.length + '건 (도면 ' + totalPending + '장)';
      if (extraSummary) {
        text += extraSummary;
      }
      summaryEl.textContent = text;
    }

    var progressEl = document.getElementById('batch-transfer-progress');
    if (progressEl) {
      progressEl.classList.add('d-none');
      progressEl.textContent = '';
    }

    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function openBatchTransferModal() {
    var selectedIds = getSelectedOrderIds();
    if (selectedIds.length === 0) {
      alert('주문을 선택해주세요.');
      return;
    }
    var pendingOrders = getSelectedPendingOrders();
    if (pendingOrders.length === 0) {
      alert('선택한 주문 중 전달 대기 도면이 있는 주문이 없습니다.');
      return;
    }
    var skipped = selectedIds.length - pendingOrders.length;
    openTransferModalFor(pendingOrders, skipped > 0 ? ' · 대기 없음 ' + skipped + '건 제외' : '');
  }

  async function openBatchAssignModal() {
    var selectedIds = getSelectedOrderIds();
    if (selectedIds.length === 0) {
      alert('주문을 선택해주세요.');
      return;
    }

    var modalEl = document.getElementById('batchAssignModal');
    var listEl = document.getElementById('batch-draftsman-list');
    if (!modalEl || !listEl || !window.bootstrap) {
      return;
    }
    var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    if (!drawingUsersCache) {
      try {
        var res = await fetch('/erp/api/users?team=DRAWING');
        var data = await res.json();
        if (data.success) {
          drawingUsersCache = data.users;
        }
      } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-danger">사용자 목록 로드 실패</div>';
        return;
      }
    }

    var users = drawingUsersCache || [];
    if (users.length === 0) {
      listEl.innerHTML = '<div class="text-muted text-center">도면팀 사용자가 없습니다.</div>';
    } else {
      listEl.innerHTML = users.map(function (u) {
        return (
          '<label class="list-group-item d-flex gap-2">' +
          '<input class="form-check-input flex-shrink-0" type="checkbox" value="' + u.id + '" name="batch_draftsman_user">' +
          '<span><strong>' + u.name + '</strong> <small class="text-muted ms-1">(' + u.team + ')</small></span>' +
          '</label>'
        );
      }).join('');
    }
  }

  async function openSingleAssignModal(orderId) {
    singleAssignOrderId = orderId;
    var modalEl = document.getElementById('singleAssignModal');
    var listEl = document.getElementById('single-draftsman-list');
    if (!modalEl || !listEl || !window.bootstrap) {
      return;
    }
    listEl.innerHTML = '<div class="text-center text-muted">로딩 중...</div>';
    var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    var currentAssigneeIds = [];
    try {
      var infoRes = await fetch('/api/orders/' + orderId + '/structured');
      if (infoRes.ok) {
        var infoData = await infoRes.json();
        if (infoData.success && infoData.structured_data) {
          var assignments = infoData.structured_data.assignments || {};
          currentAssigneeIds = assignments.drawing_assignee_user_ids || [];
        }
      }
    } catch (e) {
      console.error(e);
    }

    if (!drawingUsersCache) {
      try {
        var res = await fetch('/erp/api/users?team=DRAWING');
        var data = await res.json();
        if (data.success) {
          drawingUsersCache = data.users;
        }
      } catch (e) {
        console.error(e);
        listEl.innerHTML = '<div class="text-danger">사용자 목록 로드 실패</div>';
        return;
      }
    }

    var users = drawingUsersCache || [];
    if (users.length === 0) {
      listEl.innerHTML = '<div class="text-muted text-center">도면팀 사용자가 없습니다.</div>';
    } else {
      listEl.innerHTML = users.map(function (u) {
        var isChecked = currentAssigneeIds.includes(u.id) ? 'checked' : '';
        return (
          '<label class="list-group-item d-flex gap-2">' +
          '<input class="form-check-input flex-shrink-0" type="checkbox" value="' + u.id + '" name="single_draftsman_user" ' + isChecked + '>' +
          '<span><strong>' + u.name + '</strong> <small class="text-muted ms-1">(' + u.team + ')</small></span>' +
          '</label>'
        );
      }).join('');
    }
  }

  function buildSortUrl(field) {
    var params = new URLSearchParams(window.location.search);
    var currentSort = params.get('sort') || '';
    if (currentSort === field) {
      params.set('sort', '-' + field);
    } else if (currentSort === '-' + field) {
      params.delete('sort');
    } else {
      params.set('sort', field);
    }
    params.delete('page');
    return params.toString();
  }

  function buildPageUrl(page) {
    var params = new URLSearchParams(window.location.search);
    if (page > 1) {
      params.set('page', String(page));
    } else {
      params.delete('page');
    }
    return params.toString();
  }

  function navigatePipelineStatus(status) {
    var params = new URLSearchParams(window.location.search);
    var trimmed = (status || '').trim();
    if (trimmed) {
      params.set('status', trimmed);
    } else {
      params.delete('status');
    }
    // Status stage click replaces quick filters (미확인/오늘 마감); do not stack.
    params.delete('unread');
    params.delete('due_today');
    params.delete('page');
    window.location.href = window.location.pathname + '?' + params.toString();
  }

  function navigatePipelineQuickFilter(filterType) {
    var params = new URLSearchParams(window.location.search);
    if (filterType === 'unread') {
      params.set('unread', '1');
    } else if (filterType === 'overdue') {
      params.set('due_today', '1');
    }
    params.delete('page');
    window.location.href = window.location.pathname + '?' + params.toString();
  }

  function bindPipelineDelegationOnce() {
    if (window.__DW_WORKBENCH_PIPELINE_BOUND === '1') {
      return;
    }
    window.__DW_WORKBENCH_PIPELINE_BOUND = '1';

    document.addEventListener('click', function (e) {
      var statusStage = e.target.closest('.dw-process-map .erp-pro-pipeline__stage[data-status]');
      if (statusStage) {
        navigatePipelineStatus(statusStage.dataset.status || '');
        return;
      }
      var filterStage = e.target.closest('.dw-process-map .erp-pro-pipeline__stage[data-filter]');
      if (filterStage) {
        navigatePipelineQuickFilter(filterStage.dataset.filter || '');
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') {
        return;
      }
      var statusStage = e.target.closest('.dw-process-map .erp-pro-pipeline__stage[data-status]');
      if (statusStage) {
        e.preventDefault();
        navigatePipelineStatus(statusStage.dataset.status || '');
        return;
      }
      var filterStage = e.target.closest('.dw-process-map .erp-pro-pipeline__stage[data-filter]');
      if (filterStage) {
        e.preventDefault();
        navigatePipelineQuickFilter(filterStage.dataset.filter || '');
      }
    });
  }

  function bindRowNavigationOnce() {
    if (window.__DW_WORKBENCH_ROW_NAV_BOUND === '1') {
      return;
    }
    window.__DW_WORKBENCH_ROW_NAV_BOUND = '1';

    document.addEventListener('click', function (e) {
      var mobileCard = e.target.closest('.erp-drawing-mobile-card');
      if (mobileCard) {
        if (e.target.closest('a, button, input, select, label, .foms-drawing-queue-card__actions')) {
          return;
        }
        var mobileHref = mobileCard.getAttribute('data-href');
        if (mobileHref) {
          window.location.href = mobileHref;
        }
        return;
      }

      var row = e.target.closest('.erp-workbench-row');
      if (!row) {
        return;
      }
      if (e.target.closest('a, button, input, select, label')) {
        return;
      }
      var href = row.getAttribute('data-href');
      if (href) {
        window.location.href = href;
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') {
        return;
      }
      var mobileCard = e.target.closest('.erp-drawing-mobile-card');
      if (!mobileCard) {
        return;
      }
      if (e.target.closest('a, button, input, select, label')) {
        return;
      }
      e.preventDefault();
      var href = mobileCard.getAttribute('data-href');
      if (href) {
        window.location.href = href;
      }
    });
  }

  function initDrawingWorkbenchDashboard() {
    if (!isDrawingWorkbenchDashboard()) {
      return;
    }

    window.toggleSelectAll = toggleSelectAll;
    window.updateBatchBar = updateBatchBar;
    window.clearAllSelections = clearAllSelections;
    window.openBatchAssignModal = openBatchAssignModal;
    window.openBatchTransferModal = openBatchTransferModal;
    window.openSingleAssignModal = openSingleAssignModal;
    window.build_sort_url = buildSortUrl;
    window.build_page_url = buildPageUrl;

    bindPipelineDelegationOnce();
    bindRowNavigationOnce();

    if (initAbortController) {
      initAbortController.abort();
    }
    initAbortController = new AbortController();
    var signal = initAbortController.signal;

    var batchSaveBtn = document.getElementById('btn-save-batch-assign');
    if (batchSaveBtn) {
      batchSaveBtn.addEventListener('click', async function () {
        var selectedOrders = getSelectedOrderIds();
        var checkboxes = document.querySelectorAll('input[name="batch_draftsman_user"]:checked');
        var userIds = Array.from(checkboxes).map(function (cb) {
          return parseInt(cb.value, 10);
        });

        if (selectedOrders.length === 0) {
          alert('주문을 선택해주세요.');
          return;
        }
        if (userIds.length === 0) {
          alert('최소 한 명 이상의 담당자를 선택해주세요.');
          return;
        }
        if (!confirm('선택한 ' + selectedOrders.length + '건의 주문에 담당자를 일괄 지정하시겠습니까?')) {
          return;
        }

        try {
          var res = await fetch('/api/orders/batch-assign-draftsman', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order_ids: selectedOrders, user_ids: userIds }),
            signal: signal,
          });
          var data = await res.json();
          if (data.success) {
            alert(data.message);
            window.bootstrap.Modal.getInstance(document.getElementById('batchAssignModal')).hide();
            window.location.reload();
          } else {
            alert('오류: ' + data.message);
          }
        } catch (err) {
          if (err && err.name === 'AbortError') {
            return;
          }
          console.error(err);
          alert('저장 중 오류가 발생했습니다.');
        }
      }, { signal: signal });
    }

    var singleSaveBtn = document.getElementById('btn-save-single-assign');
    if (singleSaveBtn) {
      singleSaveBtn.addEventListener('click', async function () {
        if (!singleAssignOrderId) {
          return;
        }
        var checkboxes = document.querySelectorAll('input[name="single_draftsman_user"]:checked');
        var userIds = Array.from(checkboxes).map(function (cb) {
          return parseInt(cb.value, 10);
        });
        if (userIds.length === 0) {
          alert('최소 한 명 이상의 담당자를 선택해주세요.');
          return;
        }
        try {
          var res = await fetch('/api/orders/' + singleAssignOrderId + '/assign-draftsman', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_ids: userIds }),
            signal: signal,
          });
          var data = await res.json();
          if (data.success) {
            alert(data.message);
            window.bootstrap.Modal.getInstance(document.getElementById('singleAssignModal')).hide();
            window.location.reload();
          } else {
            alert('오류: ' + (data.message || '저장 실패'));
          }
        } catch (err) {
          if (err && err.name === 'AbortError') {
            return;
          }
          console.error(err);
          alert('저장 중 오류가 발생했습니다.');
        }
      }, { signal: signal });
    }

    var runTransferBtn = document.getElementById('btn-run-batch-transfer');
    if (runTransferBtn) {
      runTransferBtn.addEventListener('click', async function () {
        // 모달을 연 진입점(테이블 일괄전송 or 전달 대기함)이 실어둔 대상. 없으면 테이블 선택으로 폴백.
        var pendingOrders = pendingTransferOrders || getSelectedPendingOrders();
        if (pendingOrders.length === 0) {
          alert('전달 대기 도면이 있는 주문이 없습니다.');
          return;
        }

        var modeEl = document.getElementById('batch-transfer-mode');
        var noteEl = document.getElementById('batch-transfer-note');
        var progressEl = document.getElementById('batch-transfer-progress');
        var mode = modeEl ? modeEl.value : 'APPEND';
        var note = noteEl ? noteEl.value : '';

        runTransferBtn.disabled = true;
        var total = pendingOrders.length;
        var okCount = 0;
        var failOrders = [];

        for (var i = 0; i < pendingOrders.length; i++) {
          var order = pendingOrders[i];
          if (progressEl) {
            progressEl.classList.remove('d-none');
            progressEl.textContent = (i + 1) + '/' + total + ' 전송 중… (주문 #' + order.id + ')';
          }
          try {
            var res = await fetch('/api/orders/' + order.id + '/drawing-wizard/transfer-pending', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ note: note, mode: mode }),
              signal: signal,
            });
            var data = await res.json();
            if (data && data.success) {
              okCount += 1;
            } else {
              failOrders.push(order.id);
            }
          } catch (err) {
            if (err && err.name === 'AbortError') {
              runTransferBtn.disabled = false;
              return;
            }
            console.error(err);
            failOrders.push(order.id);
          }
        }

        runTransferBtn.disabled = false;
        var summary = total + '건 중 ' + okCount + '건 전송 완료';
        if (failOrders.length > 0) {
          summary += '\n실패 주문: #' + failOrders.join(', #');
        }
        alert(summary);
        var modalInst = window.bootstrap.Modal.getInstance(document.getElementById('batchTransferModal'));
        if (modalInst) {
          modalInst.hide();
        }
        window.location.reload();
      }, { signal: signal });
    }

    var pendingSelectAllBtn = document.getElementById('dw-pending-select-all');
    if (pendingSelectAllBtn) {
      pendingSelectAllBtn.addEventListener('click', function () {
        var checks = document.querySelectorAll('.dw-pending-check');
        var allChecked = checks.length > 0 && Array.from(checks).every(function (cb) {
          return cb.checked;
        });
        checks.forEach(function (cb) {
          cb.checked = !allChecked;
        });
      }, { signal: signal });
    }

    var pendingTransferSelectedBtn = document.getElementById('dw-pending-transfer-selected');
    if (pendingTransferSelectedBtn) {
      pendingTransferSelectedBtn.addEventListener('click', function () {
        var orders = collectPendingBoxSelected();
        if (orders.length === 0) {
          alert('전송할 주문을 선택해주세요.');
          return;
        }
        openTransferModalFor(orders, '');
      }, { signal: signal });
    }

    document.querySelectorAll('.dw-pending-transfer-one').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = parseInt(btn.dataset.orderId, 10);
        var pending = parseInt(btn.dataset.pending || '0', 10) || 0;
        if (!id || pending <= 0) {
          alert('전달 대기 도면이 없습니다.');
          return;
        }
        openTransferModalFor([{ id: id, pending: pending }], '');
      }, { signal: signal });
    });

    document.querySelectorAll('.mobile-order-card[data-href]').forEach(function (card) {
      function navigateToCard() {
        var href = card.getAttribute('data-href');
        if (href) {
          window.location.href = href;
        }
      }
      card.addEventListener('click', function (e) {
        if (e.target.closest('a, button, input, select, label, .foms-drawing-queue-card__actions')) {
          return;
        }
        navigateToCard();
      }, { signal: signal });
      card.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') {
          return;
        }
        if (e.target.closest('a, button, input, select, label, .foms-drawing-queue-card__actions')) {
          return;
        }
        e.preventDefault();
        navigateToCard();
      }, { signal: signal });
    });

    document.querySelectorAll('.auto-submit-checkbox').forEach(function (checkbox) {
      checkbox.addEventListener('change', function () {
        clearTimeout(filterSubmitTimeout);
        filterSubmitTimeout = window.setTimeout(function () {
          var form = checkbox.closest('form');
          if (form) {
            form.submit();
          }
        }, 300);
      }, { signal: signal });
    });

    var statusSelect = document.querySelector('select[name="status"]');
    if (statusSelect) {
      statusSelect.addEventListener('change', function () {
        var form = statusSelect.closest('form');
        if (form) {
          form.submit();
        }
      }, { signal: signal });
    }
  }

  function scheduleInit() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initDrawingWorkbenchDashboard);
    } else {
      initDrawingWorkbenchDashboard();
    }
  }

  scheduleInit();
  document.addEventListener('foms:erp-shell-fragment-swapped', initDrawingWorkbenchDashboard);
})();
