// AS 대시보드 페이지 모듈 (Batch 5: as_dashboard_body.html inline → static 이동, verbatim).
// erp-shell activateScripts가 fragment swap마다 이 src를 재실행한다(기존 inline과 동일 동작). idempotent(AbortController) 유지.
// Jinja 주입값(compact_search_q/as_tab)은 #as-dashboard-config의 data-* 속성으로 전달받는다.
  (function () {
    function initAsDashboard() {
    // 브리핑 보드 등에서 focus_order 파라미터로 진입 시 해당 주문 행/카드로 스크롤 및 하이라이트
    (function () {
      const urlParams = new URLSearchParams(window.location.search);
      const focusOrder = urlParams.get('focus_order');
      if (!focusOrder) return;
      setTimeout(function () {
        const row = document.querySelector('tr[data-order-id="' + focusOrder + '"]');
        const card = document.querySelector('.erp-pro-order-card[data-order-id="' + focusOrder + '"]');
        const el = row || card;
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('table-info');
          setTimeout(function () { el.classList.remove('table-info'); }, 2500);
        }
      }, 400);
    })();

    const toastEl = document.getElementById('saveToast');
    const toast = new bootstrap.Toast(toastEl, { delay: 2000 });
    const toastMsg = document.getElementById('toastMessage');
    const _asCfgEl = document.getElementById('as-dashboard-config');
    const currentAsTab = (_asCfgEl && _asCfgEl.dataset.currentAsTab) || 'incomplete';

    /**
     * 현재 화면의 검색어(공백제거·소문자)를 config 엘리먼트에서 매번 읽는다.
     *
     * 싱글톤 가드(window.__FOMS_AS_*_BOUND)로 1회만 등록되는 위임 핸들러는 최초 init의
     * 클로저를 계속 쓴다 — 값을 상수로 잡아두면 fragment 스왑으로 검색어가 바뀐 뒤에도
     * 옛 검색어를 칠하게 된다. config 엘리먼트는 스왑마다 새로 렌더되므로 읽기 시점에 조회한다.
     */
    function getSearchQueryCompact() {
      const cfg = document.getElementById('as-dashboard-config');
      return (cfg && cfg.dataset.searchQueryCompact) || '';
    }
    const dateFieldSaveState = new Map();
    const previousAsDashboardController = window.__fomsAsDashboardAbortController;
    if (previousAsDashboardController && typeof previousAsDashboardController.abort === 'function') {
      previousAsDashboardController.abort();
    }
    const asDashboardAbortController = typeof AbortController !== 'undefined'
      ? new AbortController()
      : null;
    window.__fomsAsDashboardAbortController = asDashboardAbortController;

    function addAsDashboardListener(target, type, handler, options) {
      if (!target || !target.addEventListener) return;
      /** Normalize addEventListener 4th arg: boolean useCapture must stay capture when merging AbortSignal. */
      let listenerOptions;
      if (options === true || options === false) {
        listenerOptions = { capture: options };
      } else if (options && typeof options === 'object') {
        listenerOptions = Object.assign({}, options);
      } else {
        listenerOptions = options;
      }
      if (asDashboardAbortController) {
        if (listenerOptions && typeof listenerOptions === 'object') {
          listenerOptions.signal = listenerOptions.signal || asDashboardAbortController.signal;
        } else {
          target.addEventListener(type, handler, { signal: asDashboardAbortController.signal });
          return;
        }
      }
      target.addEventListener(type, handler, listenerOptions);
    }

    function getDateInputsForOrder(orderId, field) {
      if (!orderId || !field) return [];
      return Array.from(document.querySelectorAll(`.editable-date-as[data-order-id="${orderId}"][data-field="${field}"]`));
    }

    let asConstructionWorkerOptions = [];
    let asConstructionWorkerOptionsLoaded = false;
    let activeAsConstructionWorkerMenu = null;

    function normalizeAsConstructionWorkers(value) {
      const rawValues = Array.isArray(value)
        ? value
        : String(value || '').replace(/\n/g, ',').split(',');
      const workers = [];
      rawValues.forEach((item) => {
        const rawName = item && typeof item === 'object'
          ? (item.name || item.text || item.value || '')
          : item;
        const name = String(rawName || '').trim();
        if (name && !workers.includes(name)) workers.push(name);
      });
      return workers;
    }

    function formatAsConstructionWorkers(value) {
      return normalizeAsConstructionWorkers(value).join(', ');
    }

    function constructionWorkersEqual(left, right) {
      const a = normalizeAsConstructionWorkers(left);
      const b = normalizeAsConstructionWorkers(right);
      return a.length === b.length && a.every((value, index) => value === b[index]);
    }

    function escapeAsConstructionWorkerHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function getConstructionWorkerList(node) {
      return node ? node.closest('.as-construction-worker-list') : null;
    }

    function getConstructionWorkerListsForOrder(orderId) {
      if (!orderId) return [];
      return Array.from(document.querySelectorAll(`.as-construction-worker-list[data-order-id="${orderId}"]`));
    }

    function getConstructionWorkerRows(list) {
      return list ? Array.from(list.querySelectorAll('.as-construction-worker-row')) : [];
    }

    function syncConstructionWorkerRowState(row) {
      if (!row) return '';
      const input = row.querySelector('.as-construction-worker-input');
      const view = row.querySelector('.as-construction-worker-view');
      const value = formatAsConstructionWorkers(input ? input.value : '');
      if (view) view.textContent = value;
      if (input) input.value = value;
      row.classList.toggle('has-value', !!value);
      row.classList.toggle('editing', !value);
      return value;
    }

    function getConstructionWorkerValuesFromList(list) {
      return normalizeAsConstructionWorkers(
        getConstructionWorkerRows(list).map((row) => {
          const input = row.querySelector('.as-construction-worker-input');
          const view = row.querySelector('.as-construction-worker-view');
          return input ? input.value : (view ? view.textContent : '');
        })
      );
    }

    function buildAsConstructionWorkerRow(list, value, editing = false) {
      const orderId = list && list.dataset ? (list.dataset.orderId || '') : '';
      const datalistId = list && list.dataset ? (list.dataset.datalistId || '') : '';
      const placeholder = list && list.dataset ? (list.dataset.placeholder || '시공자') : '시공자';
      const normalizedValue = formatAsConstructionWorkers(value);
      const escapedValue = escapeAsConstructionWorkerHtml(normalizedValue);
      const li = document.createElement('li');
      li.className = 'as-construction-worker-row' + (normalizedValue && !editing ? ' has-value' : ' editing');
      li.innerHTML =
        '<span class="as-construction-worker-view">' + escapedValue + '</span>' +
        '<div class="as-construction-worker-edit">' +
        '<input type="text" class="form-control form-control-sm as-construction-worker-input"' +
        ' data-order-id="' + escapeAsConstructionWorkerHtml(orderId) + '"' +
        ' data-field="construction_workers"' +
        ' value="' + escapedValue + '"' +
        ' placeholder="' + escapeAsConstructionWorkerHtml(placeholder) + '"' +
        (datalistId ? ' list="' + escapeAsConstructionWorkerHtml(datalistId) + '"' : '') +
        ' lang="ko">' +
        '<div class="as-construction-worker-action-stack">' +
        '<button type="button" class="btn btn-sm btn-outline-secondary as-btn-load-saved-worker" title="저장된 값 불러오기"><i class="fas fa-list"></i></button>' +
        '<button type="button" class="btn btn-sm btn-outline-danger as-btn-remove-construction-worker" title="삭제">&times;</button>' +
        '</div></div>';
      return li;
    }

    function setConstructionWorkerLists(orderId, workers) {
      const normalizedWorkers = normalizeAsConstructionWorkers(workers);
      const savedText = formatAsConstructionWorkers(normalizedWorkers);
      getConstructionWorkerListsForOrder(orderId).forEach((list) => {
        getConstructionWorkerRows(list).forEach((row) => row.remove());
        const actionsRow = list.querySelector('.as-construction-worker-actions-row');
        normalizedWorkers.forEach((worker) => {
          list.insertBefore(buildAsConstructionWorkerRow(list, worker, false), actionsRow || null);
        });
        list.dataset.savedValue = savedText;
        list.classList.remove('show-add-actions');
      });
    }

    function updateConstructionWorkerDatalist() {
      const datalist = document.getElementById('datalist-construction-workers');
      if (!datalist) return;
      datalist.innerHTML = '';
      asConstructionWorkerOptions.forEach((name) => {
        const option = document.createElement('option');
        option.value = name;
        datalist.appendChild(option);
      });
    }

    async function loadConstructionWorkerOptions() {
      if (asConstructionWorkerOptionsLoaded) return asConstructionWorkerOptions;
      const res = await fetch('/api/erp/shipment-settings', { headers: { Accept: 'application/json' } });
      const data = await res.json();
      if (!data.success) {
        throw new Error(data.message || '저장된 시공자 목록을 불러오지 못했습니다.');
      }
      asConstructionWorkerOptions = normalizeAsConstructionWorkers(
        (data.settings && data.settings.construction_workers) || []
      );
      asConstructionWorkerOptionsLoaded = true;
      updateConstructionWorkerDatalist();
      return asConstructionWorkerOptions;
    }

    async function saveConstructionWorkersList(list) {
      if (!list || !list.dataset.orderId) return { success: false, skipped: true };
      const orderId = list.dataset.orderId;
      const previousWorkers = normalizeAsConstructionWorkers(list.dataset.savedValue || '');
      const nextWorkers = getConstructionWorkerValuesFromList(list);
      if (constructionWorkersEqual(previousWorkers, nextWorkers)) {
        setConstructionWorkerLists(orderId, previousWorkers);
        return { success: true, skipped: true };
      }
      if (previousWorkers.length) {
        const nextLabel = nextWorkers.length ? nextWorkers.join(', ') : '공란';
        const confirmed = window.confirm(
          '현재 출고 대시보드 시공자: ' +
          previousWorkers.join(', ') +
          '. ' +
          nextLabel +
          '(으)로 변경하시겠습니까?'
        );
        if (!confirmed) {
          setConstructionWorkerLists(orderId, previousWorkers);
          return { success: false, cancelled: true };
        }
      }

      const relatedLists = getConstructionWorkerListsForOrder(orderId);
      relatedLists.forEach((targetList) => {
        targetList.querySelectorAll('input, button').forEach((el) => { el.disabled = true; });
      });
      try {
        const data = await saveOrderFieldDirect(orderId, 'construction_workers', nextWorkers);
        const savedWorkers = normalizeAsConstructionWorkers(
          Object.prototype.hasOwnProperty.call(data, 'construction_workers')
            ? data.construction_workers
            : (Object.prototype.hasOwnProperty.call(data, 'normalized_value') ? data.normalized_value : nextWorkers)
        );
        setConstructionWorkerLists(orderId, savedWorkers);
        showFeedback('시공자가 저장되었습니다.');
        return data;
      } catch (err) {
        setConstructionWorkerLists(orderId, previousWorkers);
        showFeedback('저장 실패: ' + String(err?.message || err || ''), true);
        throw err;
      } finally {
        relatedLists.forEach((targetList) => {
          targetList.querySelectorAll('input, button').forEach((el) => { el.disabled = false; });
        });
      }
    }

    function closeAsConstructionWorkerMenu() {
      if (activeAsConstructionWorkerMenu) {
        activeAsConstructionWorkerMenu.remove();
        activeAsConstructionWorkerMenu = null;
      }
    }

    async function openAsConstructionWorkerMenu(button, input) {
      closeAsConstructionWorkerMenu();
      try {
        const options = await loadConstructionWorkerOptions();
        if (!options.length) {
          showFeedback('저장된 시공자가 없습니다.', true);
          return;
        }
        const menu = document.createElement('div');
        menu.className = 'as-construction-worker-menu';
        options.forEach((name) => {
          const item = document.createElement('button');
          item.type = 'button';
          item.className = 'as-construction-worker-menu__item';
          item.textContent = name;
          item.addEventListener('click', function () {
            input.value = name;
            closeAsConstructionWorkerMenu();
            const row = input.closest('.as-construction-worker-row');
            const list = getConstructionWorkerList(input);
            if (row) syncConstructionWorkerRowState(row);
            if (list) saveConstructionWorkersList(list).catch(() => {});
          });
          menu.appendChild(item);
        });
        const wrap = button.closest('.as-construction-worker-edit') || button.parentElement;
        if (!wrap) return;
        wrap.appendChild(menu);
        activeAsConstructionWorkerMenu = menu;
      } catch (err) {
        showFeedback('저장된 값 불러오기 실패: ' + String(err?.message || err || ''), true);
      }
    }

    function closeAsConstructionWorkerAddActions(exceptNode) {
      document.querySelectorAll('.as-construction-worker-list.show-add-actions').forEach((list) => {
        if (exceptNode && list.contains(exceptNode)) return;
        list.classList.remove('show-add-actions');
      });
    }

    function focusAsConstructionWorkerInput(row) {
      const input = row && row.querySelector('.as-construction-worker-input');
      if (!input) return;
      input.focus();
      try {
        input.select();
      } catch (err) {
        // Selection can fail in older browsers while focus still succeeds.
      }
    }

    function getTableRowForOrder(orderId) {
      return orderId ? document.querySelector(`tr[data-order-id="${orderId}"]`) : null;
    }

    function getCardForOrder(orderId) {
      return orderId ? document.querySelector(`.erp-pro-order-card[data-order-id="${orderId}"]`) : null;
    }

    function buildAsDashboardUrl(overrides = {}) {
      const currentParams = new URLSearchParams(window.location.search);
      const params = new URLSearchParams();
      ['tab', 'focus_order', 'sort_dir', 'mine', 'status', 'billing', 'q', 'date'].forEach((key) => {
        const value = currentParams.get(key);
        if (value) {
          params.set(key, value);
        }
      });
      Object.entries(overrides).forEach(([key, value]) => {
        if (value == null || value === '') {
          params.delete(key);
        } else {
          params.set(key, String(value));
        }
      });
      params.delete('page');
      const queryString = params.toString();
      return queryString ? `/erp/as?${queryString}` : '/erp/as';
    }

    function collectHighlightTextNodes(root) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes = [];
      let absoluteStart = 0;
      let currentNode = walker.nextNode();
      while (currentNode) {
        const text = currentNode.nodeValue || '';
        const length = text.length;
        nodes.push({
          node: currentNode,
          text: text,
          start: absoluteStart,
          end: absoluteStart + length,
        });
        absoluteStart += length;
        currentNode = walker.nextNode();
      }
      return nodes;
    }

    function findCompactMatchesInWholeText(text, compactNeedle) {
      const source = String(text || '');
      if (!source || !compactNeedle) return [];
      const compactChars = [];
      const indexMap = [];
      for (let i = 0; i < source.length; i += 1) {
        const ch = source[i];
        if (/\s/.test(ch)) continue;
        compactChars.push(ch.toLowerCase());
        indexMap.push(i);
      }
      const compactSource = compactChars.join('');
      if (!compactSource) return [];
      const matches = [];
      let startAt = 0;
      while (startAt < compactSource.length) {
        const hit = compactSource.indexOf(compactNeedle, startAt);
        if (hit === -1) break;
        const start = indexMap[hit];
        const end = indexMap[hit + compactNeedle.length - 1] + 1;
        matches.push([start, end]);
        startAt = hit + compactNeedle.length;
      }
      return matches;
    }

    function mergeHighlightRanges(ranges) {
      if (!ranges.length) return [];
      const sorted = ranges
        .map(([start, end]) => [start, end])
        .sort((a, b) => a[0] - b[0]);
      const merged = [sorted[0]];
      for (let i = 1; i < sorted.length; i += 1) {
        const current = sorted[i];
        const prev = merged[merged.length - 1];
        if (current[0] <= prev[1]) {
          prev[1] = Math.max(prev[1], current[1]);
        } else {
          merged.push(current);
        }
      }
      return merged;
    }

    function replaceNodeWithHighlightRanges(textNode, text, ranges) {
      if (!textNode || !ranges.length) return false;
      const mergedRanges = mergeHighlightRanges(ranges);
      const frag = document.createDocumentFragment();
      let cursor = 0;
      mergedRanges.forEach(([start, end]) => {
        if (start > cursor) {
          frag.appendChild(document.createTextNode(text.slice(cursor, start)));
        }
        const mark = document.createElement('mark');
        mark.className = 'as-search-highlight';
        mark.textContent = text.slice(start, end);
        frag.appendChild(mark);
        cursor = end;
      });
      if (cursor < text.length) {
        frag.appendChild(document.createTextNode(text.slice(cursor)));
      }
      textNode.parentNode.replaceChild(frag, textNode);
      return true;
    }

    /**
     * 정적 텍스트 요소(타임라인 본문·셀 요약) 안의 검색어를 <mark>로 감싼다.
     *
     * 구 리치에디터 전용 하이라이트에서 편집 가능 전제만 뺀 축약판이다. 정적 DOM은
     * 편집으로 바뀌지 않으므로 "지우고 다시 칠하기"가 필요 없고, 재적용은 dataset 가드로 막는다
     * (중첩 <mark> 방지). 표시 여부(offsetParent) 검사도 뺐다 — PC 표/모바일 카드가 코호트에
     * 따라 CSS로 숨겨질 뿐이라, 숨은 채 칠해 두는 편이 resize 재계산보다 싸다.
     */
    function applyStaticHighlight(el) {
      if (!el || el.dataset.highlightApplied === '1') return;
      const needle = getSearchQueryCompact();
      if (!needle) return;
      const matchRanges = findCompactMatchesInWholeText(el.textContent || '', needle);
      if (!matchRanges.length) return;
      let applied = false;
      collectHighlightTextNodes(el).forEach((item) => {
        if (!item.text) return;
        const localRanges = [];
        matchRanges.forEach(([start, end]) => {
          const overlapStart = Math.max(start, item.start);
          const overlapEnd = Math.min(end, item.end);
          if (overlapStart < overlapEnd) {
            localRanges.push([overlapStart - item.start, overlapEnd - item.start]);
          }
        });
        if (replaceNodeWithHighlightRanges(item.node, item.text, localRanges)) {
          applied = true;
        }
      });
      el.dataset.highlightApplied = applied ? '1' : '0';
    }

    /** 타임라인 정적 텍스트에 검색어 하이라이트 적용(fragment/optimistic 주입 후 재호출). */
    function highlightTimelineStatic(root) {
      if (!getSearchQueryCompact()) return;
      (root || document)
        .querySelectorAll('.as-tl-item__body, .as-tl-cell__anchor, .as-tl-cell__recent')
        .forEach(applyStaticHighlight);
    }

    async function saveOrderFieldDirect(orderId, fieldName, newValue) {
      const res = await fetch('/api/update_order_field', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_id: orderId,
          field_name: fieldName,
          new_value: newValue
        })
      });
      const data = await res.json();
      if (!data.success) {
        throw new Error(data.message || '주문 정보 저장 실패');
      }
      return data;
    }

    function getDateFieldSaveState(input) {
      const key = `${input.dataset.orderId}:${input.dataset.field}`;
      let state = dateFieldSaveState.get(key);
      if (!state) {
        state = {
          savedValue: input.value || '',
          pendingValue: null,
          pendingSavePromise: null,
        };
        dateFieldSaveState.set(key, state);
      }
      return state;
    }

    function hasPendingDateFieldChange(input) {
      if (!input) return false;
      const state = getDateFieldSaveState(input);
      return (input.value || '') !== state.savedValue;
    }

    function setSalesDeliveryButtons(orderId, isActive) {
      document.querySelectorAll(`.as-sales-delivery-btn[data-order-id="${orderId}"]`).forEach((btn) => {
        btn.dataset.salesDeliveryActive = isActive ? '1' : '0';
        btn.textContent = `${isActive ? '☑' : '☐'} 영업/전달`;
        btn.classList.toggle('btn-warning', !!isActive);
        btn.classList.toggle('btn-outline-warning', !isActive);
      });
    }

    function setAsBlueprintCheckboxes(orderId, isChecked) {
      document.querySelectorAll(`.as-blueprint-checkbox[data-order-id="${orderId}"]`).forEach((input) => {
        input.checked = !!isChecked;
      });
    }

    function setAsPendingButtonState(orderId, asPending) {
      document.querySelectorAll(`.as-pending-btn[data-order-id="${orderId}"]`).forEach((btn) => {
        btn.dataset.asPending = asPending ? '1' : '0';
        btn.textContent = asPending ? '미결 해제' : '미결';
        btn.title = asPending ? '미결 표시 해제' : '미결 표시';
        btn.classList.toggle('erp-as-pending-btn--active', !!asPending);
      });
    }

    function syncVisitPendingButtons(orderId, hasVisitDate) {
      [getTableRowForOrder(orderId), getCardForOrder(orderId)].forEach((container) => {
        if (!container) return;
        const visitContainer = container.querySelector('.erp-as-visit-cell');
        if (!visitContainer) return;
        const existingBtn = visitContainer.querySelector('.as-pending-btn');
        if (hasVisitDate && !existingBtn) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'erp-as-pending-btn as-pending-btn';
          btn.dataset.orderId = orderId;
          btn.dataset.asPending = '0';
          btn.title = '미결 표시';
          btn.textContent = '미결';
          visitContainer.appendChild(btn);
        }
        if (!hasVisitDate && existingBtn) {
          existingBtn.remove();
        }
      });
    }

    function syncDateFieldVisuals(orderId, field, value) {
      const hasValue = !!value;
      getDateInputsForOrder(orderId, field).forEach((input) => {
        const cell = input.closest('td');
        const cardRow = input.closest('.erp-pro-order-card__row');
        if (field === 'as_visit_date') {
          if (cell) cell.classList.toggle('erp-as-visit-cell--set', hasValue);
          if (cardRow) cardRow.classList.toggle('erp-as-visit-row--set', hasValue);
        }
        if (field === 'as_completed_date') {
          if (cell) cell.classList.toggle('erp-as-complete-cell--set', hasValue);
          if (cardRow) cardRow.classList.toggle('erp-as-complete-row--set', hasValue);
        }
      });
      if (field === 'as_visit_date') {
        syncVisitPendingButtons(orderId, hasValue);
      }
    }

    function syncDateFieldInputs(orderId, field, value) {
      const normalizedValue = value || '';
      getDateInputsForOrder(orderId, field).forEach((input) => {
        input.value = normalizedValue;
        const state = getDateFieldSaveState(input);
        state.savedValue = normalizedValue;
        if (state.pendingValue === normalizedValue) {
          state.pendingValue = null;
        }
      });
      syncDateFieldVisuals(orderId, field, normalizedValue);
    }

    function applyOrderUiFromResponse(orderId, data = {}, options = {}) {
      const updatedField = options.updatedField || '';
      const row = getTableRowForOrder(orderId);
      const card = getCardForOrder(orderId);
      const asPending = data.as_pending === true;
      const status = data.status || 'AS_RECEIVED';
      const statusLabel = data.status_label || (status === 'AS_COMPLETED' ? 'AS 완료' : 'AS 접수');
      const badgeClass = asPending
        ? 'erp-pro-badge erp-pro-badge--pending'
        : (status === 'AS_COMPLETED' ? 'erp-pro-badge erp-pro-badge--success' : 'erp-pro-badge erp-pro-badge--info');
      const badgeText = asPending ? '미결' : statusLabel;

      const rowBadge = row ? row.querySelector('.erp-as-status-cell .erp-pro-badge') : null;
      const cardBadge = card ? card.querySelector('.erp-as-status-badge') : null;
      const cardStageBadge = card ? card.querySelector('.foms-stage-badge[data-order-id]') : null;
      if (rowBadge) {
        rowBadge.textContent = badgeText;
        rowBadge.className = badgeClass;
      }
      if (cardBadge) {
        if (cardBadge.classList.contains('foms-stage-badge')) {
          cardBadge.textContent = badgeText;
          cardBadge.classList.toggle('foms-stage-badge--cs', asPending);
          cardBadge.classList.toggle('foms-stage-badge--completed', !asPending && status === 'AS_COMPLETED');
        } else {
          cardBadge.textContent = badgeText;
          cardBadge.className = `erp-pro-badge erp-as-status-badge ${badgeClass.replace('erp-pro-badge ', '')}`;
        }
      }
      if (cardStageBadge && cardStageBadge !== cardBadge) {
        cardStageBadge.textContent = badgeText;
      }

      if (row) {
        const customerTd = row.querySelector('td:nth-child(7)');
        if (customerTd) customerTd.classList.toggle('erp-as-customer-cell--pending', asPending);
      }
      if (card) {
        card.classList.toggle('is-pending', asPending);
        const customerRow = card.querySelector('.erp-pro-order-card__body .erp-pro-order-card__row')
          || card.querySelector('.erp-as-mobile-card__head');
        if (customerRow) customerRow.classList.toggle('erp-as-customer-row--pending', asPending);
      }

      // 미결(as_pending)만 바꿀 때는 응답에 포함된 as_visit_date로 동기화하면 안 된다.
      // 서버 flat 컬럼이 비어 있는데 화면 입력에는 방문일이 있는 경우 syncVisitPendingButtons가 미결 버튼을 DOM에서 제거한다.
      if (updatedField !== 'as_pending' && Object.prototype.hasOwnProperty.call(data, 'as_visit_date')) {
        syncDateFieldVisuals(orderId, 'as_visit_date', data.as_visit_date || '');
      }
      if (Object.prototype.hasOwnProperty.call(data, 'as_completed_date')) {
        syncDateFieldVisuals(orderId, 'as_completed_date', data.as_completed_date || '');
      }
      if (Object.prototype.hasOwnProperty.call(data, 'sales_delivery')) {
        setSalesDeliveryButtons(orderId, data.sales_delivery === true);
      }
      if (Object.prototype.hasOwnProperty.call(data, 'as_blueprint')) {
        setAsBlueprintCheckboxes(orderId, data.as_blueprint === true);
      }

      setAsPendingButtonState(orderId, asPending);
    }

    /**
     * 미결 토글 낙관적 UI용 페이로드. 미결 해제 시 배지 문구는 완료일 입력 존재 여부로 추정한다.
     */
    function buildOptimisticAsPendingPayload(orderId, nextPending) {
      if (nextPending) {
        return { as_pending: true };
      }
      var completedInput = getDateInputsForOrder(orderId, 'as_completed_date')[0];
      var hasCompleted = !!(completedInput && completedInput.value);
      if (hasCompleted) {
        return { as_pending: false, status: 'AS_COMPLETED', status_label: 'AS 완료' };
      }
      return { as_pending: false, status: 'AS_RECEIVED', status_label: 'AS 접수' };
    }

    /** 낙관적 적용 후 요청 실패 시 원래 표시로 되돌린다. */
    function revertAsPendingAfterFailedRequest(orderId, originallyPending) {
      if (originallyPending) {
        return { as_pending: true };
      }
      return buildOptimisticAsPendingPayload(orderId, false);
    }

    async function saveDateField(input, options = {}) {
      const silent = options.silent === true;
      const redirectAfterComplete = options.redirectAfterComplete === true;
      const orderId = input.dataset.orderId;
      const fieldName = input.dataset.field;
      const state = getDateFieldSaveState(input);
      const value = input.value || '';
      if (value === state.savedValue) {
        return { success: true, skipped: true };
      }
      if (state.pendingSavePromise && state.pendingValue === value) {
        return state.pendingSavePromise;
      }
      input.style.backgroundColor = '#fff3cd';
      syncDateFieldVisuals(orderId, fieldName, value);
      const requestPromise = fetch('/api/update_order_field', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_id: orderId,
          field_name: fieldName,
          new_value: value
        })
      })
        .then(res => res.json())
        .then(data => {
          if (!data.success) {
            throw new Error(data.message || '날짜 저장 실패');
          }
          syncDateFieldInputs(orderId, fieldName, value);
          applyOrderUiFromResponse(orderId, data, { updatedField: fieldName });
          if (!silent) {
            showFeedback(fieldName === 'as_completed_date' ? '완료일이 저장되었습니다.' : '방문일이 저장되었습니다.');
          }
          if (redirectAfterComplete && fieldName === 'as_completed_date') {
            if (value && currentAsTab === 'sales_delivery') {
              window.location.href = buildAsDashboardUrl({
                tab: 'completed',
                status: 'AS_COMPLETED',
                focus_order: orderId,
              });
            } else if (!value && currentAsTab === 'completed') {
              window.location.href = buildAsDashboardUrl({
                tab: 'incomplete',
                status: 'AS_RECEIVED',
                focus_order: orderId,
              });
            }
          }
          return data;
        })
        .catch(err => {
          if (!silent) {
            const msg = err && err.message ? err.message : '네트워크 오류가 발생했습니다.';
            showFeedback('저장 실패: ' + msg, true);
          }
          syncDateFieldInputs(orderId, fieldName, state.savedValue || '');
          throw err;
        })
        .finally(() => {
          input.style.backgroundColor = '';
          if (state.pendingSavePromise === requestPromise) {
            state.pendingSavePromise = null;
            state.pendingValue = null;
          }
        });
      state.pendingValue = value;
      state.pendingSavePromise = requestPromise;
      return requestPromise;
    }

    async function flushDateFieldIfNeeded(input, options = {}) {
      if (!input || !hasPendingDateFieldChange(input)) {
        return null;
      }
      return saveDateField(input, options);
    }

    // 최초 렌더/프래그먼트 스왑 직후 타임라인 요약 셀에 검색어 하이라이트 적용.
    highlightTimelineStatic(document);

    // ───────── 카드 상세 lazy 렌더 (D1c) ─────────
    // 닫힌 <details> 안 상세(시공자·AS 타임라인)를 서버에서 eager 렌더하지 않고
    // (100행 × 상세 = fragment 비만의 잔여 최대 덩어리), 열릴 때
    // GET /erp/as/card-detail/<id>로 fetch해 placeholder에 주입한다. 멱등: placeholder.dataset.loaded.
    // 주입 후 재배선은 window.__fomsAsRebindLazyCard로 위임한다. 이 함수는 매 init마다
    // 최신 클로저(= 살아있는 AbortController)로 덮어써지므로, 프래그먼트 스왑 뒤 열리는 카드도
    // 죽은(aborted) signal이 아닌 현재 컨트롤러에 바인딩된다(직접 바인딩이 abort-scoped이므로 핵심).
    window.__fomsAsRebindLazyCard = function (scope) {
      if (!scope) return;
      bindAsDateAndWorkerInputs(scope);
      highlightTimelineStatic(scope);
    };

    function loadAsCardDetail(placeholder) {
      if (!placeholder || placeholder.dataset.loading === '1') return;
      const orderId = placeholder.dataset.orderId || '';
      if (!orderId) return;
      placeholder.dataset.loading = '1';
      placeholder.innerHTML = '<div class="erp-as-card-lazy__status text-muted small py-2">불러오는 중...</div>';
      fetch('/erp/as/card-detail/' + encodeURIComponent(orderId), {
        headers: { Accept: 'text/html' },
        credentials: 'same-origin',
      })
        .then((res) => {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          return res.text();
        })
        .then((html) => {
          placeholder.innerHTML = html;
          placeholder.dataset.loaded = '1';
          placeholder.dataset.loading = '';
          if (typeof window.__fomsAsRebindLazyCard === 'function') {
            window.__fomsAsRebindLazyCard(placeholder);
          }
        })
        .catch(() => {
          // 조용한 실패 금지: 에러 표시 + 재시도 버튼.
          placeholder.dataset.loading = '';
          placeholder.innerHTML =
            '<div class="erp-as-card-lazy__status text-danger small py-2">' +
            '내용을 불러오지 못했습니다. ' +
            '<button type="button" class="btn btn-sm btn-link p-0 align-baseline as-card-lazy-retry">재시도</button>' +
            '</div>';
        });
    }

    // document 1회 위임(window 가드). <details> toggle은 버블하지 않으므로 capture 단계로 수신.
    if (!window.__FOMS_AS_CARD_LAZY_BOUND) {
      window.__FOMS_AS_CARD_LAZY_BOUND = true;
      document.addEventListener('toggle', function (e) {
        const details = e.target;
        if (!details || !details.matches || !details.matches('details.erp-as-mobile-card__detail')) return;
        if (!details.open) return;
        const placeholder = details.querySelector('[data-as-card-lazy]');
        if (!placeholder || placeholder.dataset.loaded === '1') return;
        loadAsCardDetail(placeholder);
      }, true);
      document.addEventListener('click', function (e) {
        const retry = e.target && e.target.closest ? e.target.closest('.as-card-lazy-retry') : null;
        if (!retry) return;
        const placeholder = retry.closest('[data-as-card-lazy]');
        if (!placeholder) return;
        placeholder.dataset.loaded = '';
        loadAsCardDetail(placeholder);
      });
    }

    // ───────── AS 타임라인 상호작용(확장 행·quick-add·더보기) ─────────
    // fragment swap마다 이 파일이 재실행되므로 document 위임은 window 가드로 1회만 등록한다(perf G4).
    // 핸들러는 필요한 값(order_id·검색어)을 매번 DOM에서 읽으므로 최초 클로저 재사용이 안전하다.
    // 사용자 피드백에 showFeedback(=최초 init의 toast 인스턴스)을 쓰지 않는 이유도 같다 —
    // 스왑 뒤엔 그 toast 엘리먼트가 DOM에서 사라져 조용히 무동작이 된다.
    if (!window.__FOMS_AS_TIMELINE_BOUND) {
      window.__FOMS_AS_TIMELINE_BOUND = true;

      // PC 내용 셀 클릭 → 아래에 full-width 행을 만들어 타임라인 fragment를 lazy fetch(재클릭=닫기).
      // 기록 0건 셀(.as-tl-cell__empty)도 같은 경로로 열려야 quick-add로 첫 기록을 남길 수 있다.
      document.addEventListener('click', function (e) {
        const btn = e.target.closest && e.target.closest('.as-tl-cell__expand, .as-tl-cell__empty');
        if (!btn) return;
        const orderId = btn.dataset.orderId;
        const row = btn.closest('tr[data-order-id]');
        if (!row || !orderId) return;
        const next = row.nextElementSibling;
        if (next && next.classList.contains('as-tl-expand-row')) { next.remove(); return; } // 토글
        const tr = document.createElement('tr');
        tr.className = 'as-tl-expand-row';
        tr.dataset.orderId = orderId;
        tr.innerHTML = '<td colspan="12"><div class="as-tl-expand-body" data-loading="1">'
          + '<div class="text-muted small py-2">불러오는 중...</div></div></td>';
        row.after(tr);
        fetch('/erp/as/timeline/' + encodeURIComponent(orderId), {
          headers: { Accept: 'text/html' }, credentials: 'same-origin',
        }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
          .then((html) => {
            const body = tr.querySelector('.as-tl-expand-body');
            body.innerHTML = html;
            body.dataset.loading = '';
            highlightTimelineStatic(body);
          })
          .catch(() => { tr.querySelector('.as-tl-expand-body').innerHTML =
            '<div class="text-danger small py-2">타임라인을 불러오지 못했습니다.</div>'; });
      });

      /** quick-add 폼 1건 전송 → 성공 시 응답 html을 스트림 맨 앞에 낙관적 삽입. */
      async function submitQuickAdd(form) {
        if (!form) return;
        const orderId = form.dataset.orderId;
        const textEl = form.querySelector('.as-timeline__text');
        const typeEl = form.querySelector('.as-timeline__type');
        const text = (textEl && textEl.value || '').trim();
        if (!orderId || !text) return;
        const stream = form.parentElement.querySelector('.as-timeline__stream');
        const submitBtn = form.querySelector('.as-timeline__submit');
        if (submitBtn) submitBtn.disabled = true;
        try {
          const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/log', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ type: (typeEl && typeEl.value) || 'memo', text: text }),
          });
          const data = await res.json();
          if (!data.success) throw new Error(data.message || '기록 추가 실패');
          if (stream) {
            stream.insertAdjacentHTML('afterbegin', data.html); // optimistic prepend
            highlightTimelineStatic(stream);
          }
          textEl.value = '';
          if (typeEl) typeEl.value = 'memo'; // 저장 후 memo 리셋(스펙 5.5)
        } catch (err) {
          // 입력 텍스트는 지우지 않는다 — 재시도 가능해야 한다.
          alert(String(err && err.message || err || '기록 추가 중 오류'));
        } finally { if (submitBtn) submitBtn.disabled = false; }
      }

      document.addEventListener('submit', function (e) {
        const form = e.target.closest && e.target.closest('.as-timeline__quick-add');
        if (!form) return;
        e.preventDefault();
        submitQuickAdd(form);
      });

      // Ctrl/⌘+Enter 단축키. 한글 IME 조합 확정 Enter가 전송으로 새지 않도록 isComposing·229 가드.
      document.addEventListener('keydown', function (e) {
        const textEl = e.target.closest && e.target.closest('.as-timeline__text');
        if (!textEl) return;
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
          e.preventDefault();
          submitQuickAdd(textEl.closest('.as-timeline__quick-add'));
        }
      });

      // 더보기: 기본 렌더는 최근 8건이라 ?full=1로 스트림 전량(상한 200)을 다시 받아 통째 교체.
      document.addEventListener('click', function (e) {
        const more = e.target.closest && e.target.closest('.as-timeline__more');
        if (!more) return;
        const orderId = more.dataset.orderId;
        const timeline = more.closest('.as-timeline');
        const body = more.closest('.as-tl-expand-body')
          || more.closest('.erp-as-mobile-card__content')
          || (timeline && timeline.parentElement);
        if (!orderId || !body) return;
        fetch('/erp/as/timeline/' + encodeURIComponent(orderId) + '?full=1',
              { headers: { Accept: 'text/html' }, credentials: 'same-origin' })
          .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
          .then((html) => { body.innerHTML = html; highlightTimelineStatic(body); })
          .catch(() => { more.textContent = '이전 기록을 불러오지 못했습니다.'; });
      });
    }

    addAsDashboardListener(document, 'click', async function (e) {
      const btn = e.target.closest('.as-sales-delivery-btn');
      if (!btn) return;
      e.preventDefault();

      // 토글은 타임라인 헤더 소속이라 구 리치에디터 조상이 없다 — dataset을 직접 읽는다.
      const orderId = btn.dataset.orderId || '';
      if (!orderId) {
        showFeedback('영업/택배 분류 대상을 찾지 못했습니다.', true);
        return;
      }

      const prevDisabled = btn.disabled;
      const wasActive = btn.dataset.salesDeliveryActive === '1';
      // 완료일 입력은 확장 행/상세 밖(행·카드 본문)에 있으므로 order_id로 문서 전역에서 찾는다.
      const completedInput = getDateInputsForOrder(orderId, 'as_completed_date')[0];
      btn.disabled = true;
      try {
        await flushDateFieldIfNeeded(completedInput, { silent: true, redirectAfterComplete: false });
        const baseTab = completedInput && completedInput.value ? 'completed' : 'incomplete';
        const nextActive = !wasActive;
        const targetTab = nextActive ? (baseTab === 'completed' ? 'completed' : 'sales_delivery') : baseTab;
        const data = await saveOrderFieldDirect(orderId, 'sales_delivery', nextActive);
        applyOrderUiFromResponse(orderId, data, { updatedField: 'sales_delivery' });
        window.location.href = buildAsDashboardUrl({
          tab: targetTab,
          status: targetTab === 'completed' ? 'AS_COMPLETED' : null,
          focus_order: orderId,
        });
      } catch (err) {
        btn.disabled = prevDisabled;
        showFeedback(String(err?.message || err || '영업/택배 분류 중 오류가 발생했습니다.'), true);
      }
    });

    // ───────── 가까운 일정 찾기 ─────────
    (function () {
      // 탭별 pre-computed 리스트 (백엔드에서 각각 계산해 내려줌)
      let _lists = { distance: [], date: [], combined: [] };
      // 재검색 시 사용할 현재 주문 컨텍스트
      let _searchState = { excludeId: null, lat: null, lng: null };
      // 일정찾기 성공 응답 기준 좌표 (지도 모달 출발점)
      let _refLat = null;
      let _refLng = null;
      let _refAddress = '';
      const _routeCache = new Map();
      let _scheduleMapModalInstance = null;
      let _scheduleMapLeaflet = null;
      let _scheduleMapGen = 0;

      function _routeCacheKey(lat1, lng1, lat2, lng2) {
        return `${Number(lat1).toFixed(6)},${Number(lng1).toFixed(6)}-${Number(lat2).toFixed(6)},${Number(lng2).toFixed(6)}`;
      }

      function _truncateAddr(s, maxLen) {
        const t = String(s || '').trim();
        if (t.length <= maxLen) return t;
        return t.slice(0, maxLen) + '…';
      }

      function esc(s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
      }

      function fmtDate(d) {
        const m = d && d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        return m ? `${parseInt(m[2])}월 ${parseInt(m[3])}일` : esc(d || '');
      }

      function localDateIso() {
        const d = new Date();
        return [
          d.getFullYear(),
          String(d.getMonth() + 1).padStart(2, '0'),
          String(d.getDate()).padStart(2, '0')
        ].join('-');
      }

      function parseYmdDate(value) {
        const m = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!m) return null;
        return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
      }

      // 정렬은 백엔드 담당 — renderResults는 표시만 수행
      function renderResults(items, sortType) {
        const resList = document.getElementById('scheduleSearchResults');
        if (!resList) return;
        const today = localDateIso();
        resList.innerHTML = '';
        if (!items || items.length === 0) {
          resList.innerHTML = `<div class="text-center py-5 text-muted">
            <i class="fas fa-calendar-times mb-2" style="font-size:2rem;"></i>
            <p>해당 기준으로 조회된 일정이 없습니다.</p></div>`;
          return;
        }
        items.forEach(item => {
          const el = document.createElement('a');
          el.className = 'list-group-item list-group-item-action p-3';
          el.href = `/edit/${esc(item.id)}?open=erp-order`;
          let badgeClass = 'bg-secondary';
          if (item.type === '상차') badgeClass = 'bg-warning text-dark';
          else if (item.type === '시공') badgeClass = 'bg-success';
          let extraBadge = '';
          if (sortType === 'distance' && item.dist_km != null) {
            extraBadge = `<span class="badge bg-info text-dark ms-1">직선 ${esc(item.dist_km)}km</span>`;
          } else if (sortType === 'date' && item.date) {
            const itemDate = parseYmdDate(item.date);
            const todayDate = parseYmdDate(today);
            if (itemDate && todayDate) {
              const days = Math.round((itemDate - todayDate) / 86400000);
              if (days >= 0) extraBadge = `<span class="badge bg-info text-dark ms-1">D+${days}</span>`;
            }
          } else if (sortType === 'combined') {
            extraBadge = `<span class="badge bg-secondary ms-1">거리+날짜 최적</span>`;
          }
          const itemLat = Number(item.lat);
          const itemLng = Number(item.lng);
          const mapBtnHtml = (Number.isFinite(itemLat) && Number.isFinite(itemLng))
            ? `<button type="button" class="btn btn-sm btn-outline-info schedule-map-btn"
                data-lat="${itemLat}" data-lng="${itemLng}"
                data-address="${esc(item.address)}" data-name="${esc(item.customer_name)}"
                data-score-text="${esc(item.score_text || '')}">
                <i class="fas fa-map"></i> 지도
              </button>`
            : '<span></span>';
          el.innerHTML = `
            <div class="d-flex w-100 justify-content-between align-items-center mb-2">
              <div>
                <span class="badge ${badgeClass} me-2">${esc(item.type)}</span>
                <span class="fw-bold">${fmtDate(item.date)}</span>
                <span class="mx-2 text-muted">|</span>
                <span class="fw-semibold">${esc(item.customer_name)}</span>
                ${extraBadge}
              </div>
              <small class="text-muted">#${esc(item.id)}</small>
            </div>
            <p class="mb-1 text-dark">
              <i class="fas fa-map-marker-alt text-danger me-1"></i> ${esc(item.address)}
              ${item.score_text ? `<span class="badge bg-light text-dark border ms-2"><i class="fas fa-car-side me-1"></i>${esc(item.score_text)}</span>` : ''}
            </p>
            <div class="d-flex justify-content-between align-items-end mt-1">
              ${mapBtnHtml}
              <small class="text-primary fw-bold"><i class="fas fa-external-link-alt"></i> 바로가기</small>
            </div>`;
          resList.appendChild(el);
        });
      }

      // API 호출 + 결과 렌더링 — 버튼 클릭/재검색 공통 사용
      async function runSearch(address, excludeId, lat, lng) {
        const tabs = document.getElementById('scheduleSortTabs');
        if (tabs) {
          tabs.style.display = 'none';
          tabs.querySelectorAll('.nav-link').forEach((t, i) => t.classList.toggle('active', i === 0));
        }
        const radiusBadge = document.getElementById('scheduleSearchRadiusBadge');
        if (radiusBadge) radiusBadge.style.display = 'none';
        const mapLink = document.getElementById('scheduleMapLink');
        if (mapLink) mapLink.style.display = 'none';
        const fallbackAlert = document.getElementById('scheduleSearchFallbackAlert');
        if (fallbackAlert) fallbackAlert.style.display = 'none';
        const resList = document.getElementById('scheduleSearchResults');
        if (resList) resList.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><div class="mt-2 text-muted small">주변 일정을 검색 중입니다...</div></div>';

        _refLat = null;
        _refLng = null;
        _refAddress = '';

        try {
          const params = new URLSearchParams({ address });
          if (excludeId) params.append('exclude_id', excludeId);
          if (lat && lng) { params.append('lat', lat); params.append('lng', lng); }
          const res = await fetch(`/api/orders/nearby?${params.toString()}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();

          const hasAny = data.success &&
            ((data.by_distance && data.by_distance.length) ||
             (data.by_date && data.by_date.length) ||
             (data.by_combined && data.by_combined.length));

          if (!hasAny) {
            if (resList) resList.innerHTML = `
              <div class="text-center py-5 text-muted">
                <i class="fas fa-calendar-times mb-2" style="font-size:2rem;"></i>
                <p>30km 반경 내에 예정된 출고/시공 일정이 없습니다.</p>
              </div>`;
            return;
          }

          _lists = {
            distance: data.by_distance || [],
            date:     data.by_date     || [],
            combined: data.by_combined || [],
          };

          if (typeof data.ref_lat === 'number' && Number.isFinite(data.ref_lat) &&
              typeof data.ref_lng === 'number' && Number.isFinite(data.ref_lng)) {
            _refLat = data.ref_lat;
            _refLng = data.ref_lng;
            _refAddress = String(address || '');
          }

          // geocoding 실패(fallback) 시 경고 표시
          if (fallbackAlert) {
            fallbackAlert.style.display = data.search_radius_km ? 'none' : '';
          }
          if (radiusBadge && data.search_radius_km) {
            document.getElementById('scheduleSearchRadiusText').textContent =
              `반경 ${data.search_radius_km}km 내 검색 결과`;
            radiusBadge.style.display = 'block';
          }
          if (mapLink) {
            const kakaoUrl = (data.ref_lat && data.ref_lng)
              ? `https://map.kakao.com/link/to/${encodeURIComponent(address)},${data.ref_lat},${data.ref_lng}`
              : `https://map.kakao.com/?q=${encodeURIComponent(address)}`;
            mapLink.href = kakaoUrl;
            mapLink.style.display = '';
          }
          if (tabs) tabs.style.display = '';
          renderResults(_lists.distance, 'distance');
        } catch (err) {
          console.error(err);
          if (resList) resList.innerHTML = '<div class="text-center py-3 text-danger">오류가 발생했습니다.</div>';
        }
      }

      addAsDashboardListener(document.getElementById('scheduleSortTabs'), 'click', function (e) {
        const tab = e.target.closest('[data-sort]');
        if (!tab) return;
        this.querySelectorAll('.nav-link').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        renderResults(_lists[tab.dataset.sort] || [], tab.dataset.sort);
      });

      addAsDashboardListener(document.body, 'click', async function (e) {
        const btn = e.target.closest('.find-schedule-btn');
        if (!btn) return;
        const addr = btn.dataset.address;
        const orderId = btn.dataset.orderId;
        const btnLat = btn.dataset.lat;
        const btnLng = btn.dataset.lng;
        const modalEl = document.getElementById('scheduleSearchModal');
        if (!modalEl) { alert('페이지를 새로고침(F5) 해주세요.'); location.reload(); return; }

        const addrEl = document.getElementById('scheduleSearchAddr');
        if (addrEl) addrEl.value = addr;
        _searchState = { excludeId: orderId, lat: btnLat, lng: btnLng };
        new bootstrap.Modal(modalEl).show();
        await runSearch(addr, orderId, btnLat, btnLng);
      });

      // 주소 수정 후 재검색 — 잘못된 주소 직접 고쳐서 다시 검색 가능
      const retryBtn = document.getElementById('scheduleSearchRetryBtn');
      if (retryBtn) {
        addAsDashboardListener(retryBtn, 'click', async function () {
          const addrEl = document.getElementById('scheduleSearchAddr');
          const newAddr = addrEl ? addrEl.value.trim() : '';
          if (!newAddr) return;
          // 재검색 시 lat/lng는 초기화 (새 주소 기준 geocoding)
          await runSearch(newAddr, _searchState.excludeId, null, null);
        });
      }

      const scheduleMapModalEl = document.getElementById('scheduleMapModal');
      if (scheduleMapModalEl) {
        addAsDashboardListener(scheduleMapModalEl, 'hidden.bs.modal', function () {
          if (_scheduleMapLeaflet) {
            try {
              _scheduleMapLeaflet.remove();
            } catch (e) { /* ignore */ }
            _scheduleMapLeaflet = null;
          }
        });
      }

      function openScheduleMap(refAddr, refLat, refLng, tgtLat, tgtLng, tgtAddr, tgtName, scoreText) {
        const modalEl = document.getElementById('scheduleMapModal');
        const routeInfoEl = document.getElementById('scheduleMapRouteInfo');
        if (typeof L === 'undefined' || !modalEl || !routeInfoEl) return;

        const myGen = ++_scheduleMapGen;
        routeInfoEl.innerHTML = '<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm me-2" role="status"></div>경로 계산 중...</div>';

        if (!_scheduleMapModalInstance) {
          _scheduleMapModalInstance = new bootstrap.Modal(modalEl);
        }

        const onShown = function () {
          modalEl.removeEventListener('shown.bs.modal', onShown);
          if (myGen !== _scheduleMapGen) return;

          if (_scheduleMapLeaflet) {
            try {
              _scheduleMapLeaflet.remove();
            } catch (e) { /* ignore */ }
            _scheduleMapLeaflet = null;
          }

          const container = document.getElementById('scheduleMapContainer');
          if (!container) return;
          container.replaceChildren();

          const map = L.map(container).setView([refLat, refLng], 11);
          _scheduleMapLeaflet = map;
          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>'
          }).addTo(map);

          L.circleMarker([refLat, refLng], {
            radius: 9,
            color: '#c0392b',
            weight: 2,
            fillColor: '#ff6b6b',
            fillOpacity: 0.95
          }).addTo(map).bindPopup(esc(_truncateAddr(refAddr, 80)));

          L.circleMarker([tgtLat, tgtLng], {
            radius: 9,
            color: '#2e7d32',
            weight: 2,
            fillColor: '#4caf50',
            fillOpacity: 0.95
          }).addTo(map).bindPopup('<strong>' + esc(tgtName) + '</strong><br>' + esc(tgtAddr));

          map.fitBounds(L.latLngBounds([[refLat, refLng], [tgtLat, tgtLng]]), { padding: [50, 50], maxZoom: 14 });

          function bumpMapSize() {
            if (myGen !== _scheduleMapGen || !_scheduleMapLeaflet || _scheduleMapLeaflet !== map) return;
            try {
              map.invalidateSize({ animate: false });
            } catch (e) { /* ignore */ }
          }
          map.whenReady(bumpMapSize);
          requestAnimationFrame(function () {
            bumpMapSize();
            setTimeout(bumpMapSize, 120);
            setTimeout(bumpMapSize, 400);
          });

          (async function loadRoute() {
            const cacheKey = _routeCacheKey(refLat, refLng, tgtLat, tgtLng);
            let routeJson = _routeCache.get(cacheKey);
            try {
              if (!routeJson) {
                const res = await fetch(
                  '/api/calculate_route?start_lat=' + encodeURIComponent(refLat) +
                  '&start_lng=' + encodeURIComponent(refLng) +
                  '&end_lat=' + encodeURIComponent(tgtLat) +
                  '&end_lng=' + encodeURIComponent(tgtLng)
                );
                if (res.status === 429) {
                  throw new Error('RATE_LIMIT');
                }
                routeJson = await res.json();
                if (routeJson && routeJson.success) {
                  _routeCache.set(cacheKey, routeJson);
                }
              }
              if (myGen !== _scheduleMapGen || !_scheduleMapLeaflet || _scheduleMapLeaflet !== map) return;

              if (routeJson && routeJson.success && routeJson.data &&
                  routeJson.data.route_coords && routeJson.data.route_coords.length > 0) {
                const routeData = routeJson.data;
                const line = L.polyline(routeData.route_coords, {
                  color: '#ff4757',
                  weight: 5,
                  opacity: 0.8
                }).addTo(map);
                try {
                  map.fitBounds(line.getBounds(), { padding: [50, 50], maxZoom: 14 });
                } catch (e) { /* ignore */ }
                bumpMapSize();
                setTimeout(bumpMapSize, 200);

                const summ = routeData.summary || {};
                const distT = summ.distance_text != null ? summ.distance_text : (routeData.distance_km + 'km');
                const durT = summ.duration_text != null ? summ.duration_text : ((routeData.duration_min || 0) + '분');
                const tollT = summ.toll_text != null ? summ.toll_text : '—';
                routeInfoEl.innerHTML =
                  '<div class="schedule-map-route-info">' +
                  '<h6><i class="fas fa-car-side me-1"></i> 경로 정보</h6>' +
                  '<div class="mb-1"><strong>출발:</strong> ' + esc(refAddr) + '</div>' +
                  '<div class="mb-1"><strong>도착:</strong> ' + esc(tgtAddr) + '</div>' +
                  '<div class="mb-1"><strong>거리:</strong> ' + esc(distT) + '</div>' +
                  '<div class="mb-1"><strong>소요시간:</strong> ' + esc(durT) + '</div>' +
                  '<div><strong>통행료:</strong> ' + esc(tollT) + '</div>' +
                  '</div>';
              } else {
                throw new Error((routeJson && routeJson.error) ? String(routeJson.error) : 'ROUTE_FAIL');
              }
            } catch (err) {
              if (myGen !== _scheduleMapGen) return;
              const msg = (err && err.message === 'RATE_LIMIT')
                ? '요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.'
                : '자동차 경로를 계산하지 못했습니다. 직선거리를 참고해 주세요.';
              const hint = scoreText
                ? ('<p class="mb-0 small mt-2">직선거리 참고: ' + esc(scoreText) + '</p>')
                : '';
              routeInfoEl.innerHTML =
                '<div class="alert alert-warning mb-0" role="alert">' +
                '<strong>경로 계산 실패</strong>' +
                '<p class="mb-0 small">' + esc(msg) + '</p>' +
                hint +
                '</div>';
            }
          })();
        };

        addAsDashboardListener(modalEl, 'shown.bs.modal', onShown, { once: true });
        _scheduleMapModalInstance.show();
      }

      addAsDashboardListener(document.body, 'click', function (e) {
        const btn = e.target.closest('.schedule-map-btn');
        if (!btn) return;
        e.stopPropagation();
        e.preventDefault();
        const targetLat = parseFloat(btn.dataset.lat);
        const targetLng = parseFloat(btn.dataset.lng);
        const targetAddress = btn.dataset.address || '';
        const targetName = btn.dataset.name || '';
        const scoreText = btn.dataset.scoreText || '';
        if (!_refLat || !_refLng) return;
        if (!Number.isFinite(targetLat) || !Number.isFinite(targetLng)) return;
        openScheduleMap(_refAddress, _refLat, _refLng, targetLat, targetLng, targetAddress, targetName, scoreText);
      });
    })();

    function showFeedback(msg, isError = false) {
      toastMsg.textContent = msg;
      toastEl.classList.remove('bg-success', 'bg-danger');
      toastEl.classList.add(isError ? 'bg-danger' : 'bg-success');
      toast.show();
    }

    // AS 대시보드 첨부 파일 모달 (ERP 첨부 파일 모달과 동일: 4탭 + 카드 갤러리, 미리보기 = GlobalImageViewer)
    (function () {
      function escapeHtml(s) {
        if (s == null) return '';
        var str = String(s);
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
      }
      var ATTACHMENT_CATEGORY_META = {
        measurement: { label: '실측', icon: 'fa-ruler-combined' },
        drawing: { label: '도면', icon: 'fa-drafting-compass' },
        construction: { label: '시공', icon: 'fa-hammer' },
        as: { label: 'AS', icon: 'fa-wrench' }
      };
      function normalizeAttachmentCategory(category) {
        var c = String(category || '').trim().toLowerCase();
        if (c === 'drawing' || c === 'construction' || c === 'as') return c;
        return 'measurement';
      }
      function attachmentCanDelete(a) {
        return !!(a && a.can_delete === true);
      }
      function getAttachmentCategoryLabel(category) {
        var key = normalizeAttachmentCategory(category);
        return (ATTACHMENT_CATEGORY_META[key] || ATTACHMENT_CATEGORY_META.measurement).label;
      }
      var __attachmentsByCategory = { measurement: [], drawing: [], construction: [], as: [] };
      var __activeAttachmentCategory = 'measurement';
      var __currentAttachmentList = [];

      function renderAttachmentCategoryTabs() {
        var tabsEl = document.getElementById('erp-attachments-category-tabs');
        if (!tabsEl) return;
        var keys = ['measurement', 'drawing', 'construction', 'as'];
        tabsEl.innerHTML = keys.map(function (key) {
          var meta = ATTACHMENT_CATEGORY_META[key];
          var count = (__attachmentsByCategory[key] || []).length;
          var isActive = key === __activeAttachmentCategory;
          var activeCls = isActive ? 'btn-primary' : 'btn-outline-primary';
          var badgeCls = isActive ? 'bg-light text-dark' : 'bg-primary text-white';
          return '<button type="button" class="btn btn-sm ' + activeCls + '" onclick="window.selectAttachmentCategoryAs && window.selectAttachmentCategoryAs(\'' + key + '\')">' +
            '<i class="fas ' + meta.icon + '"></i> ' + meta.label +
            ' <span class="badge ' + badgeCls + ' ms-1">' + count + '</span></button>';
        }).join('');
      }
      function renderAttachmentCategoryGallery() {
        var galleryEl = document.getElementById('erp-attachments-category-gallery');
        if (!galleryEl) return;
        var list = __attachmentsByCategory[__activeAttachmentCategory] || [];
        if (!list.length) {
          galleryEl.innerHTML = '<div class="col-12"><div class="text-muted small p-3 border rounded bg-light">' +
            getAttachmentCategoryLabel(__activeAttachmentCategory) + ' 카테고리에 첨부 파일이 없습니다.</div></div>';
          return;
        }
        galleryEl.innerHTML = list.map(function (a, index) {
          var name = escapeHtml(a.filename || '');
          var type = (a.file_type || 'file').toLowerCase();
          var thumb = a.thumbnail_view_url || a.view_url || '#';
          var viewUrl = a.view_url || '#';
          var downloadUrl = a.download_url || '#';
          var attachmentId = a.id ? String(a.id) : '';
          var cat = __activeAttachmentCategory;
          var mediaHtml;
          if (type === 'video') {
            mediaHtml = '<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">' +
              '<video src="' + escapeHtml(viewUrl) + '" controls preload="metadata" style="width:100%;height:100%;"></video></div>';
          } else if (type === 'image') {
            mediaHtml = '<img src="' + escapeHtml(thumb) + '" alt="' + name + '" class="img-fluid rounded" ' +
              'style="max-height: 180px; object-fit: contain; width:100%; cursor: zoom-in; background:#fff; padding:4px;" ' +
              'onclick="window.openAttachmentFromCategoryAs && window.openAttachmentFromCategoryAs(\'' + cat + '\', ' + index + ')">';
          } else {
            mediaHtml = '<div class="border rounded d-flex flex-column align-items-center justify-content-center bg-light" style="height: 180px;">' +
              '<i class="fas fa-file-alt text-secondary mb-2" style="font-size: 2rem;"></i>' +
              '<div class="small text-muted text-center px-2">문서 파일</div></div>';
          }
          return '<div class="col-md-4 col-sm-6 col-12">' +
            '<div class="card h-100">' +
            '<div class="card-body p-2">' + mediaHtml +
            '<div class="d-flex justify-content-between align-items-center mt-2">' +
            '<div class="small text-truncate" title="' + name + '" style="max-width: 70%;">' + name + '</div>' +
            '<div class="btn-group btn-group-sm">' +
            '<button type="button" class="btn btn-outline-secondary" title="미리보기" onclick="window.openAttachmentFromCategoryAs && window.openAttachmentFromCategoryAs(\'' + cat + '\', ' + index + ')">' +
            '<i class="fas fa-eye"></i></button>' +
            '<a class="btn btn-outline-primary" href="' + escapeHtml(downloadUrl) + '" title="다운로드" target="_blank" rel="noopener"><i class="fas fa-download"></i></a>' +
            (attachmentCanDelete(a) ?
            '<button type="button" class="btn btn-outline-danger" title="삭제" onclick="window.deleteAttachmentFromCategoryAs && window.deleteAttachmentFromCategoryAs(\'' + cat + '\', ' + index + ', \'' + escapeHtml(attachmentId) + '\')">' +
            '<i class="fas fa-trash"></i></button>' : '') +
            '</div></div></div></div></div>';
        }).join('');
      }
      function selectAttachmentCategory(category) {
        __activeAttachmentCategory = normalizeAttachmentCategory(category);
        renderAttachmentCategoryTabs();
        renderAttachmentCategoryGallery();
      }
      function showAttachmentAtIndex(index) {
        if (!__currentAttachmentList || index < 0 || index >= __currentAttachmentList.length) return;
        if (window.GlobalImageViewer) {
          window.GlobalImageViewer.open(__currentAttachmentList, index);
        } else {
          showFeedback('이미지 뷰어를 불러올 수 없습니다.', true);
        }
      }
      function openAttachmentFromCategory(category, index) {
        var key = normalizeAttachmentCategory(category);
        var list = __attachmentsByCategory[key] || [];
        if (!list.length) return;
        __activeAttachmentCategory = key;
        __currentAttachmentList = list;
        showAttachmentAtIndex(index);
      }
      async function deleteAttachmentFromCategory(category, index, attachmentId) {
        var orderId = __currentAsModalOrderId;
        var key = normalizeAttachmentCategory(category);
        var list = __attachmentsByCategory[key] || [];
        var attachment = list[index] || {};
        var id = attachmentId || attachment.id;
        if (!orderId || !id) {
          showFeedback('삭제할 첨부 파일을 찾을 수 없습니다.', true);
          return;
        }
        if (!attachmentCanDelete(attachment)) {
          showFeedback('첨부파일 삭제 권한이 없습니다.', true);
          return;
        }
        if (!confirm('첨부 파일을 삭제하시겠습니까?')) return;
        try {
          var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/attachments/' + encodeURIComponent(id), {
            method: 'DELETE'
          });
          var data = await res.json();
          if (!res.ok || !data.success) {
            showFeedback((data && data.message) || '첨부 파일 삭제에 실패했습니다.', true);
            return;
          }
          await refreshAsModalAttachments();
          showFeedback('첨부 파일을 삭제했습니다.');
        } catch (err) {
          showFeedback(err && err.message ? err.message : '첨부 파일 삭제 중 오류가 발생했습니다.', true);
        }
      }
      window.selectAttachmentCategoryAs = selectAttachmentCategory;
      window.openAttachmentFromCategoryAs = openAttachmentFromCategory;
      window.deleteAttachmentFromCategoryAs = deleteAttachmentFromCategory;

      var __currentAsModalOrderId = null;

      async function refreshAsModalAttachments() {
        var orderId = __currentAsModalOrderId;
        var galleryEl = document.getElementById('erp-attachments-category-gallery');
        if (!orderId || !galleryEl) return;
        try {
          var res = await fetch('/api/orders/' + orderId + '/attachments');
          var data = await res.json();
          var rawList = (data && data.attachments) ? data.attachments : [];
          __attachmentsByCategory = { measurement: [], drawing: [], construction: [], as: [] };
          rawList.forEach(function (a) {
            var key = normalizeAttachmentCategory(a.category);
            if (!__attachmentsByCategory[key]) __attachmentsByCategory[key] = [];
            __attachmentsByCategory[key].push(Object.assign({}, a, { category: key }));
          });
          var firstNonEmpty = ['as', 'measurement', 'drawing', 'construction'].filter(function (k) {
            return (__attachmentsByCategory[k] || []).length > 0;
          })[0];
          __activeAttachmentCategory = firstNonEmpty || 'measurement';
          renderAttachmentCategoryTabs();
          renderAttachmentCategoryGallery();
          if (rawList.length === 0) {
            galleryEl.innerHTML = '<div class="col-12"><div class="text-muted small p-3 border rounded bg-light">등록된 첨부 파일이 없습니다.</div></div>';
          }
        } catch (err) {
          galleryEl.innerHTML = '<div class="col-12 text-center py-3 text-danger">불러오기에 실패했습니다.</div>';
        }
      }

      addAsDashboardListener(document.body, 'click', async function (e) {
        var btn = e.target.closest('.as-photos-btn');
        if (!btn) return;
        var orderId = btn.dataset.orderId;
        if (!orderId) return;
        __currentAsModalOrderId = orderId;
        var modalEl = document.getElementById('asErpAttachmentsCategoryModal');
        var tabsEl = document.getElementById('erp-attachments-category-tabs');
        var galleryEl = document.getElementById('erp-attachments-category-gallery');
        if (!modalEl || !tabsEl || !galleryEl) return;
        tabsEl.innerHTML = '';
        galleryEl.innerHTML = '<div class="col-12 text-center py-4"><div class="spinner-border text-primary" role="status"></div><p class="mt-2 mb-0 text-muted small">불러오는 중...</p></div>';
        var modal = new bootstrap.Modal(modalEl);
        modal.show();
        try {
          await refreshAsModalAttachments();
        } catch (err) {
          galleryEl.innerHTML = '<div class="col-12 text-center py-3 text-danger">불러오기에 실패했습니다.</div>';
          showFeedback('첨부 파일을 불러올 수 없습니다.', true);
        }
      });

      var asUploadInput = document.getElementById('as-modal-upload-input');
      var asUploadBtn = document.getElementById('as-modal-upload-btn');
      var asUploadStatus = document.getElementById('as-modal-upload-status');
      if (asUploadBtn && asUploadInput) {
        addAsDashboardListener(asUploadBtn, 'click', function () {
          if (!__currentAsModalOrderId) return;
          asUploadInput.value = '';
          asUploadInput.click();
        });
        addAsDashboardListener(asUploadInput, 'change', async function () {
          var orderId = __currentAsModalOrderId;
          var files = this.files ? Array.from(this.files) : [];
          this.value = '';
          if (!orderId || files.length === 0) return;
          asUploadBtn.disabled = true;
          var ok = 0;
          try {
            // --- Optimistic UI Start ---
            var galleryEl = document.getElementById('erp-attachments-category-gallery');
            if (galleryEl) {
                const emptyText = galleryEl.querySelector('.text-muted');
                if (emptyText && emptyText.textContent.includes('없습니다')) {
                    const emptyPanel = emptyText.closest('.col-12');
                    if (emptyPanel) emptyPanel.remove();
                }

                files.forEach((f, fi) => {
                    const uniqueId = 'opt-ul-as-' + Date.now() + '-' + fi;
                    f._optId = uniqueId;
                    const name = typeof escapeHtml === 'function' ? escapeHtml(f.name) : f.name;
                    let previewUrl = '';
                    try {
                      previewUrl = URL.createObjectURL(f);
                    } catch (e) {
                      console.warn('AS 첨부 미리보기 URL 생성 실패', e);
                    }
                    const previewHtml = previewUrl
                      ? `<img src="${previewUrl}" class="rounded mb-2" style="width:100%;height:100px;object-fit:cover;filter:grayscale(80%);">`
                      : `<div class="w-100 rounded mb-2 d-flex align-items-center justify-content-center bg-white border" style="height:100px; color:#6c757d; font-size:0.8rem;">미리보기 없음</div>`;

                    const placeholderHtml = `
  <div id="${uniqueId}" class="col-md-4 col-sm-6 col-12 opacity-75">
      <div class="card h-100 bg-light border-dashed">
          <div class="card-body p-2 d-flex flex-column align-items-center justify-content-center position-relative" style="height: 180px;">
              ${previewHtml}
              <div class="spinner-border text-primary position-absolute" style="top:50%;left:50%;margin-top:-1rem;margin-left:-1rem;" role="status"></div>
              <div class="small text-truncate w-100 text-center" title="${name}">${name}</div>
              <div class="small text-primary fw-bold mt-1 opt-pct">0%</div>
          </div>
      </div>
  </div>`;
                    galleryEl.insertAdjacentHTML('afterbegin', placeholderHtml);
                });
            }
            // --- Optimistic UI End ---

            if (asUploadStatus) {
              asUploadStatus.style.display = 'block';
              asUploadStatus.textContent = '업로드 중... (0/' + files.length + ')';
            }
            
            var category = 'as';
            var folder = 'orders/' + orderId + '/attachments';
            let sessionMap = {};

            const fallbackFormUpload = async function (file) {
              try {
                const fd = new FormData();
                fd.append('file', file);
                fd.append('category', category);
                const res = await fetch(`/api/orders/${orderId}/attachments`, { method: 'POST', body: fd });
                const data = await res.json();
                return data && data.success ? { success: true } : (data || { success: false, message: '첨부 업로드 실패' });
              } catch (err) {
                return { success: false, message: err && err.message ? err.message : '첨부 업로드 실패' };
              }
            };

            const uploadResult = await window.fomsUploadOrderAttachmentsBatch({
                orderId: orderId,
                files: files,
                folder: folder,
                category: category,
                useDirectUpload: true,
                onPrepareProgress: function (info) {
                    if (asUploadStatus) asUploadStatus.textContent = '이미지 최적화 중... (' + info.done + '/' + info.total + ')';
                },
                onUploadProgress: function (info) {
                    if (asUploadStatus) asUploadStatus.textContent = '업로드 중... (' + Math.round(info.done) + '/' + info.total + ')';
                },
                onFileDone: function (info) {
                    const f = info.entry.originalFile;
                    const result = info.result || { success: false };
                    const el = document.getElementById(f._optId);
                    if (!el) return;
                    el.classList.remove('opacity-75');
                    const spinner = el.querySelector('.spinner-border');
                    if (spinner) spinner.remove();
                    const pctSpan = el.querySelector('.opt-pct');
                    if (pctSpan) {
                      pctSpan.textContent = result.success ? '완료' : '실패';
                      pctSpan.classList.toggle('text-primary', !!result.success);
                      pctSpan.classList.toggle('text-danger', !result.success);
                    }
                    const card = el.querySelector('.card');
                    if (card) {
                      card.classList.toggle('border-danger', !result.success);
                    }
                    if (!result.success && result.message) {
                      el.title = result.message;
                    }
                }
            });
            ok = uploadResult.ok;

            if (asUploadStatus) {
              asUploadStatus.textContent = ok === files.length ? '업로드 완료.' : '업로드 완료 (' + ok + '/' + files.length + ').';
              setTimeout(function () { asUploadStatus.style.display = 'none'; }, 2000);
            }
            if (ok > 0) {
              try {
                await refreshAsModalAttachments();
              } catch (refreshErr) {
                console.warn('AS 첨부 목록 새로고침 실패', refreshErr);
              }
              showFeedback('AS 사진 ' + ok + '개가 추가되었습니다.');
            } else {
              showFeedback('AS 사진 업로드에 실패했습니다.', true);
            }
          } catch (err) {
            console.error(err);
            if (asUploadStatus) {
              asUploadStatus.style.display = 'block';
              asUploadStatus.textContent = '업로드 중 오류가 발생했습니다.';
              setTimeout(function () { asUploadStatus.style.display = 'none'; }, 2500);
            }
            showFeedback(err && err.message ? err.message : 'AS 사진 업로드 중 오류가 발생했습니다.', true);
          } finally {
            asUploadBtn.disabled = false;
          }
        });
      }
    })();

    // AS 방문일/완료일 자동 저장 + 시공자 리스트 초기화
    bindAsDateAndWorkerInputs(document);
    loadConstructionWorkerOptions().catch(() => {});

    addAsDashboardListener(document, 'mousedown', function (e) {
      if (!e.target.closest('.as-btn-remove-construction-worker, .as-btn-load-saved-worker')) return;
      const row = e.target.closest('.as-construction-worker-row');
      if (row) row.dataset.skipBlurSave = '1';
    }, true);

    addAsDashboardListener(document, 'blur', function (e) {
      const input = e.target && e.target.closest('.as-construction-worker-input');
      if (!input) return;
      const row = input.closest('.as-construction-worker-row');
      const list = getConstructionWorkerList(input);
      if (!row || !list) return;
      if (row.dataset.skipBlurSave === '1') {
        row.dataset.skipBlurSave = '';
        return;
      }
      syncConstructionWorkerRowState(row);
      saveConstructionWorkersList(list).catch(() => {});
    }, true);

    addAsDashboardListener(document, 'keydown', function (e) {
      const input = e.target && e.target.closest('.as-construction-worker-input');
      if (!input || e.key !== 'Enter') return;
      e.preventDefault();
      input.blur();
    });

    addAsDashboardListener(document, 'click', function (e) {
      const view = e.target && e.target.closest('.as-construction-worker-view');
      if (view) {
        const row = view.closest('.as-construction-worker-row');
        if (!row) return;
        e.preventDefault();
        e.stopPropagation();
        row.classList.remove('has-value');
        row.classList.add('editing');
        focusAsConstructionWorkerInput(row);
        return;
      }

      const addBtn = e.target && e.target.closest('.as-btn-add-construction-worker');
      if (addBtn) {
        const list = getConstructionWorkerList(addBtn);
        if (!list) return;
        e.preventDefault();
        e.stopPropagation();
        const row = buildAsConstructionWorkerRow(list, '', true);
        const actionsRow = addBtn.closest('.as-construction-worker-actions-row');
        list.insertBefore(row, actionsRow || null);
        list.classList.remove('show-add-actions');
        focusAsConstructionWorkerInput(row);
        return;
      }

      const loadBtn = e.target && e.target.closest('.as-btn-load-saved-worker');
      if (loadBtn) {
        e.preventDefault();
        const wrap = loadBtn.closest('.as-construction-worker-edit');
        const input = wrap ? wrap.querySelector('.as-construction-worker-input') : null;
        if (input) openAsConstructionWorkerMenu(loadBtn, input);
        return;
      }

      const removeBtn = e.target && e.target.closest('.as-btn-remove-construction-worker');
      if (removeBtn) {
        e.preventDefault();
        closeAsConstructionWorkerMenu();
        const list = getConstructionWorkerList(removeBtn);
        const row = removeBtn.closest('.as-construction-worker-row');
        if (!list || !row) return;
        row.remove();
        saveConstructionWorkersList(list).catch(() => {});
        return;
      }

      const list = e.target && e.target.closest('.as-construction-worker-list');
      if (list && !e.target.closest('button, input')) {
        e.preventDefault();
        const isOpen = list.classList.contains('show-add-actions');
        closeAsConstructionWorkerAddActions(list);
        list.classList.toggle('show-add-actions', !isOpen);
        return;
      }

      if (activeAsConstructionWorkerMenu && !e.target.closest('.as-construction-worker-list')) {
        closeAsConstructionWorkerMenu();
      }
      closeAsConstructionWorkerAddActions(e.target);
    });

    // AS 미결 버튼 클릭: 미결 ↔ 미결 해제 토글 (낙관적 UI 후 서버와 동기화)
    addAsDashboardListener(document, 'click', function (e) {
      var btn = e.target && e.target.closest('.as-pending-btn');
      if (!btn || !btn.dataset.orderId) return;
      e.preventDefault();
      var orderId = btn.dataset.orderId;
      var originallyPending = btn.dataset.asPending === '1';
      var nextPending = !originallyPending;
      applyOrderUiFromResponse(orderId, buildOptimisticAsPendingPayload(orderId, nextPending), { updatedField: 'as_pending' });
      btn.disabled = true;
      fetch('/api/update_order_field', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId, field_name: 'as_pending', new_value: nextPending ? '1' : '0' })
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          btn.disabled = false;
          if (data.success) {
            applyOrderUiFromResponse(orderId, data, { updatedField: 'as_pending' });
            showFeedback(originallyPending ? '미결 표시를 해제했습니다.' : '미결로 표시했습니다.');
          } else {
            applyOrderUiFromResponse(orderId, revertAsPendingAfterFailedRequest(orderId, originallyPending), { updatedField: 'as_pending' });
            showFeedback('저장 실패: ' + (data.message || ''), true);
          }
        })
        .catch(function () {
          btn.disabled = false;
          applyOrderUiFromResponse(orderId, revertAsPendingAfterFailedRequest(orderId, originallyPending), { updatedField: 'as_pending' });
          showFeedback('네트워크 오류가 발생했습니다.', true);
        });
    });

    addAsDashboardListener(document, 'change', function (e) {
      const checkbox = e.target && e.target.closest('.as-blueprint-checkbox');
      if (!checkbox || !checkbox.dataset.orderId) return;

      const orderId = checkbox.dataset.orderId;
      const nextChecked = checkbox.checked;
      const relatedCheckboxes = document.querySelectorAll(`.as-blueprint-checkbox[data-order-id="${orderId}"]`);
      const confirmed = window.confirm(
        nextChecked
          ? 'AS도면 확인으로 표시할까요?'
          : 'AS도면 확인을 해제할까요?'
      );
      if (!confirmed) {
        relatedCheckboxes.forEach((input) => {
          input.checked = !nextChecked;
        });
        return;
      }

      relatedCheckboxes.forEach((input) => {
        input.checked = nextChecked;
        input.disabled = true;
      });

      saveOrderFieldDirect(orderId, 'as_blueprint', nextChecked)
        .then((data) => {
          applyOrderUiFromResponse(orderId, data, { updatedField: 'as_blueprint' });
          showFeedback('AS도면 여부가 저장되었습니다.');
        })
        .catch((err) => {
          relatedCheckboxes.forEach((input) => {
            input.checked = !nextChecked;
          });
          showFeedback('저장 실패: ' + String(err?.message || err || ''), true);
        })
        .finally(() => {
          relatedCheckboxes.forEach((input) => {
            input.disabled = false;
          });
        });
    });

    // --- per-card 바인딩 함수 (페이지별 렌더마다 init에서 호출, dataset 가드로 멱등) ---
    function bindAsDateAndWorkerInputs(scope) {
      const root = scope || document;
      root.querySelectorAll('.editable-date-as').forEach(input => {
        if (input.dataset.asDateBound === '1') return;
        input.dataset.asDateBound = '1';
        getDateFieldSaveState(input);
        addAsDashboardListener(input, 'change', function () {
          saveDateField(this, { redirectAfterComplete: true }).catch(() => {});
        });
      });
      root.querySelectorAll('.as-construction-worker-list').forEach(list => {
        if (list.dataset.asWorkerInit === '1') return;
        list.dataset.asWorkerInit = '1';
        list.dataset.savedValue = formatAsConstructionWorkers(list.dataset.savedValue || '');
      });
    }

    }

    // static defer 모듈 부트스트랩:
    // - 최초 풀페이지 로드: defer 실행 시점 readyState는 'interactive'(아직 다른 defer 스크립트(bootstrap.bundle 등) 미실행)
    //   → DOMContentLoaded까지 대기해야 bootstrap/leaflet/flatpickr 등 전역이 모두 준비된다.
    // - erp-shell fragment swap: 페이지가 이미 'complete' → 즉시 init(스왑마다 재실행, AbortController로 idempotent).
    if (document.readyState === 'complete') {
      initAsDashboard();
    } else {
      document.addEventListener('DOMContentLoaded', initAsDashboard, { once: true });
    }
  })();
