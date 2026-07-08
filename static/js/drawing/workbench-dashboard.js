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
