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

    // T15 과도기 힌트 배너 — "AS 내용"이 타임라인으로 바뀐 것을 1회만 알린다.
    // 싱글톤 가드를 쓰지 않는 이유: 배너는 fragment swap 마다 새 엘리먼트로 다시 렌더되므로
    // 리스너도 그 엘리먼트에 새로 붙어야 한다(전역 리스너가 아니라 누수도 없다).
    // 서버는 d-none 으로 렌더한다 — 이미 닫은 사용자에게 한 프레임 깜빡이지 않게 하려고.
    // localStorage 접근은 사생활 모드/서드파티 쿠키 차단에서 SecurityError 를 던진다. 여기가
    // initAsDashboard 최상단이라 예외가 새면 대시보드 JS 전체(토스트·날짜 저장·quick-add·
    // 프리셋)가 죽는다. 아래 catch 는 에러 숨기기가 아니라 **예상된 브라우저 상태의 폴백**이다:
    //   읽기 실패 → "아직 안 닫음"으로 보고 배너를 띄운다(안내 누락보다 재노출이 낫다)
    //   쓰기 실패 → 저장만 포기하고 세션 내 제거는 유지한다(다음 방문에 다시 뜬다)
    (function () {
      const banner = document.getElementById('as-timeline-hint');
      if (!banner) return;
      let dismissed = false;
      try {
        dismissed = localStorage.getItem('foms_as_timeline_hint_dismissed') === '1';
      } catch (storageErr) {
        dismissed = false; // 저장소 차단 — 미닫힘으로 폴백
      }
      if (dismissed) { banner.remove(); return; }
      banner.classList.remove('d-none');
      const dismiss = banner.querySelector('.as-timeline-hint__dismiss');
      if (dismiss) dismiss.addEventListener('click', function () {
        try {
          localStorage.setItem('foms_as_timeline_hint_dismissed', '1');
        } catch (storageErr) {
          console.warn('[as-dashboard] 힌트 확인 저장 실패 — 다음 방문에 다시 표시됨', storageErr);
        }
        banner.remove(); // 저장 성공 여부와 무관하게 이번 세션에서는 사라진다
      });
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

    // ── 방문 가능시간 팝오버 (칩 클릭 편집) ─────────────────────────────
    // 서버 SSOT: foms/services/orders/as_availability.py (라벨·허용값 동기 필수)
    (function initAsAvailabilityPopover() {
      if (window.__asAvailPopoverWired) return; // fragment 재실행 가드
      window.__asAvailPopoverWired = true;
      const DAY_OPTS = [['any', '무관'], ['weekday', '평일'], ['weekend', '주말']];
      const TIME_OPTS = [['any', '무관'], ['am', '오전'], ['pm', '오후'], ['evening', '저녁']];
      const DAY_LABELS = { any: '요일무관', weekday: '평일', weekend: '주말' };
      const TIME_LABELS = { any: '시간무관', am: '오전', pm: '오후', evening: '저녁' };
      let pop = null;

      function availLabel(v) {
        if (!v) return '';
        const parts = [DAY_LABELS[v.days] || '', TIME_LABELS[v.time] || ''].filter(Boolean);
        let label = parts.join('·');
        if (v.note) label = label ? `${label} (${v.note})` : `(${v.note})`;
        return label;
      }

      function closePop() {
        if (pop) { pop.remove(); pop = null; }
      }

      function segmentHtml(name, opts, current) {
        return opts.map(([val, label]) =>
          `<button type="button" class="erp-as-avail-pop__opt${val === current ? ' is-active' : ''}"
             data-seg="${name}" data-val="${val}">${label}</button>`).join('');
      }

      function applyChipState(orderId, value) {
        document.querySelectorAll(`.erp-as-avail-chip[data-order-id="${orderId}"]`).forEach((chip) => {
          chip.dataset.availDays = value ? value.days : '';
          chip.dataset.availTime = value ? value.time : '';
          chip.dataset.availNote = value && value.note ? value.note : '';
          chip.classList.toggle('erp-as-avail-chip--set', !!value);
          const labelEl = chip.querySelector('.erp-as-avail-chip__label');
          if (labelEl) labelEl.textContent = value ? availLabel(value) : '가능시간';
        });
      }

      async function saveAvailability(orderId, value) {
        const res = await fetch('/api/update_order_field', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ order_id: orderId, field: 'as_visit_availability', value })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.message || '가능시간 저장 실패');
        return data;
      }

      function openPop(chip) {
        closePop();
        const orderId = chip.dataset.orderId;
        const state = {
          days: chip.dataset.availDays || 'any',
          time: chip.dataset.availTime || 'any',
          note: chip.dataset.availNote || ''
        };
        pop = document.createElement('div');
        pop.className = 'erp-as-avail-pop';
        pop.innerHTML =
          `<div class="erp-as-avail-pop__row"><span class="erp-as-avail-pop__label">요일</span>
             <div class="erp-as-avail-pop__seg">${segmentHtml('days', DAY_OPTS, state.days)}</div></div>
           <div class="erp-as-avail-pop__row"><span class="erp-as-avail-pop__label">시간</span>
             <div class="erp-as-avail-pop__seg">${segmentHtml('time', TIME_OPTS, state.time)}</div></div>
           <input type="text" class="erp-pro-input erp-as-avail-pop__note" maxlength="80"
             placeholder="메모 (예: 3시 이후, 경비실 경유)">
           <div class="erp-as-avail-pop__actions">
             <button type="button" class="erp-pro-btn erp-pro-btn--ghost" data-act="clear">초기화</button>
             <button type="button" class="erp-pro-btn erp-pro-btn--primary" data-act="save">저장</button>
           </div>`;
        pop.querySelector('.erp-as-avail-pop__note').value = state.note;
        document.body.appendChild(pop);
        const rect = chip.getBoundingClientRect();
        const popW = pop.offsetWidth || 240;
        const left = Math.max(8, Math.min(window.scrollX + rect.left, window.scrollX + window.innerWidth - popW - 8));
        pop.style.top = `${window.scrollY + rect.bottom + 4}px`;
        pop.style.left = `${left}px`;

        pop.addEventListener('click', async (e) => {
          const seg = e.target.closest('[data-seg]');
          if (seg) {
            state[seg.dataset.seg] = seg.dataset.val;
            seg.parentElement.querySelectorAll('.erp-as-avail-pop__opt').forEach((b) =>
              b.classList.toggle('is-active', b === seg));
            return;
          }
          const act = e.target.closest('[data-act]');
          if (!act) return;
          const isClear = act.dataset.act === 'clear';
          const value = isClear ? null : {
            days: state.days,
            time: state.time,
            note: pop.querySelector('.erp-as-avail-pop__note').value.trim()
          };
          try {
            const data = await saveAvailability(orderId, value);
            // 서버 에코 키는 normalized_value (초기화면 "")
            const saved = (data.normalized_value && typeof data.normalized_value === 'object')
              ? data.normalized_value : null;
            applyChipState(orderId, saved);
            // 회차 차트가 열려 있으면 상태 카드 현재값·이력(system 로그)도 함께 갱신.
            if (typeof window.__fomsRefreshRoundChart === 'function') {
              window.__fomsRefreshRoundChart(orderId);
            }
            showFeedback(isClear ? '가능시간을 초기화했습니다.' : '가능시간을 저장했습니다.');
          } catch (err) {
            showFeedback(err.message || '가능시간 저장 실패', true);
          }
          closePop();
        });
      }

      document.addEventListener('click', (e) => {
        const chip = e.target.closest('.erp-as-avail-chip');
        if (chip) {
          e.preventDefault();
          e.stopPropagation();
          if (pop && pop.dataset.forOrder === chip.dataset.orderId) { closePop(); return; }
          openPop(chip);
          if (pop) pop.dataset.forOrder = chip.dataset.orderId;
          return;
        }
        if (pop && !pop.contains(e.target)) closePop();
      });
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePop(); });
    })();

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
          // ver7 차트 세그먼트 '마지막 유형 기억'. typeof 가드: 함수는 타임라인 위임
          // 가드 블록 안에 선언돼 있어(중복 등록 방지) 스코프 정책에 따라 안 보일 수 있다.
          if (typeof applyChartTypeMemory === 'function') {
            applyChartTypeMemory(placeholder.querySelector('.as-rchart'));
          }
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

      // 상태 셀 비용 배지 클릭 → 그 비용 상태로 목록 필터. "비용 필터가 있는 줄 몰랐다"는
      // 실사용 피드백의 발견성 보강이다(필터 select 자체는 이미 동작 — 스테이징 실측 확인).
      // 문서 위임인 이유: 같은 배지를 판정 변경 API 응답(updateAsBillingBadge)도 꽂아 넣는데,
      // 그 마크업엔 현재 탭·검색어 컨텍스트가 없다. 여기서 현재 URL로 조립하면 두 경로가 같아진다.
      function applyBillingFilterFromBadge(badge) {
        const kind = badge.dataset.billingFilter;
        if (!kind) return;
        // 같은 값 재클릭 = 해제(토글). buildAsDashboardUrl은 빈 값이면 파라미터를 지운다.
        const current = new URLSearchParams(window.location.search).get('billing') || '';
        window.location.href = buildAsDashboardUrl({ billing: current === kind ? '' : kind });
      }

      document.addEventListener('click', function (e) {
        const badge = e.target.closest && e.target.closest('.erp-as-billing-badge[data-billing-filter]');
        if (badge) applyBillingFilterFromBadge(badge);
      });

      // role="button"은 Enter/Space 동작을 공짜로 주지 않는다(네이티브 button이 아니므로).
      document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const badge = e.target.closest && e.target.closest('.erp-as-billing-badge[data-billing-filter]');
        if (!badge) return;
        e.preventDefault();
        applyBillingFilterFromBadge(badge);
      });

      // PC 내용 셀 클릭 → 아래에 full-width 행을 만들어 타임라인 fragment를 lazy fetch(재클릭=닫기).
      // 히트 영역은 버튼이 아니라 **셀 전체**(.as-tl-cell)다 — 앵커 줄·최근 줄 텍스트를 눌러도
      // 열린다(스펙 §5.2 "셀 클릭 시 확장"). 기록 0건 셀도 같은 경로로 열려야 quick-add로
      // 첫 기록을 남길 수 있는데, .as-tl-cell__empty 가 그 셀 안에 있으므로 자동으로 포함된다.
      // closest 가드: 셀 안의 다른 인터랙티브 요소(링크·입력·향후 추가될 버튼)는 가로채지 않는다.
      document.addEventListener('click', function (e) {
        if (!e.target.closest) return;
        const cell = e.target.closest('.as-tl-cell');
        if (!cell) return;
        if (e.target.closest('a, input, select, textarea')) return;
        const otherBtn = e.target.closest('button');
        if (otherBtn && !otherBtn.matches('.as-tl-cell__expand, .as-tl-cell__empty')) return;
        const orderId = cell.dataset.orderId;
        const row = cell.closest('tr[data-order-id]');
        if (!row || !orderId) return;
        const next = row.nextElementSibling;
        if (next && next.classList.contains('as-tl-expand-row')) { next.remove(); return; } // 토글
        const tr = document.createElement('tr');
        tr.className = 'as-tl-expand-row';
        tr.dataset.orderId = orderId;
        tr.innerHTML = '<td colspan="12"><div class="as-tl-expand-body" data-loading="1">'
          + '<div class="text-muted small py-2">불러오는 중...</div></div></td>';
        row.after(tr);
        // 가용폭 SSOT = 가로 스크롤 컨테이너(wrapper)의 실측 가시폭. CSS 100vw 기반 상한은
        // 셸 레이아웃·사이드 패널·줌·OS 배율에서 실제 가용폭보다 넓게 계산돼 확장 박스
        // 우측이 잘렸다(T15f 실보고 3회). sticky right:0 기준도 이 wrapper 스크롤포트라
        // clientWidth 가 유일하게 정확한 값이다. 인라인 지정은 동적 기하 계산이라 CSS 로
        // 표현 불가한 예외(resize 는 재열기로 회복 — 상시 리스너는 과설계).
        const wrap = row.closest('.erp-pro-table-wrapper');
        if (wrap && wrap.clientWidth) {
          tr.querySelector('.as-tl-expand-body').style.maxWidth =
            Math.min(720, wrap.clientWidth - 24) + 'px';
        }
        fetch('/erp/as/timeline/' + encodeURIComponent(orderId), {
          headers: { Accept: 'text/html' }, credentials: 'same-origin',
        }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
          .then((html) => {
            const body = tr.querySelector('.as-tl-expand-body');
            body.innerHTML = html;
            body.dataset.loading = '';
            applyChartTypeMemory(body.querySelector('.as-rchart')); // ver7 마지막 유형 기억
            highlightTimelineStatic(body);
          })
          .catch(() => { tr.querySelector('.as-tl-expand-body').innerHTML =
            '<div class="text-danger small py-2">타임라인을 불러오지 못했습니다.</div>'; });
      });

      /**
       * 쓰기 API 응답을 JSON으로 읽는다.
       *
       * res.ok로 먼저 끊지 않는 이유: 400/403도 body에 사용자에게 보여줄 message를 싣는다.
       * 대신 비-JSON 본문(로그인 리다이렉트 HTML·프록시 502 등)이 오면 파싱 예외를
       * "Unexpected token '<'" 그대로 노출하지 않고 사람이 읽을 문구로 바꾼다.
       */
      async function readTimelineJson(res) {
        try {
          return await res.json();
        } catch (parseErr) {
          throw new Error(res.status === 401 || res.status === 403
            ? '권한이 없거나 세션이 만료되었습니다. 새로고침 후 다시 시도해주세요.'
            : '세션이 만료되었거나 서버 오류가 발생했습니다(HTTP ' + res.status + '). 새로고침 후 다시 시도해주세요.');
        }
      }

      /**
       * 접힘 셀 요약(.as-tl-cell)을 쓰기 응답 html로 로컬 갱신한다(재조회 없음).
       *
       * 확장 행/모바일 상세에서 기록을 추가·수정해도 같은 행의 요약 셀은 서버 렌더값
       * 그대로라, 접는 순간 옛 최근줄과 실제보다 작은 배지 숫자만 남는다(T10 U1).
       * 서버 요약(as_dashboard_display._timeline_cell_text)은 블록 태그를 개행으로 바꾼 뒤
       * 공백으로 접는다. 여기서도 같은 순서로 흉내낸다 — textContent만 읽으면
       * `<div>앞</div><div>뒤</div>`가 "앞뒤"로 붙어 접기 전후로 요약이 갈린다.
       * (같은 코드가 아니라 미러다. 서버 파서와 완전 동치는 아니고, 두 표면이 눈에 띄게
       *  갈리는 블록 경계 케이스를 맞춘다.)
       *
       * @param {string} orderId 대상 주문 id
       * @param {string} html 쓰기 API 응답 항목 html(목록과 같은 서버 매크로 렌더)
       * @param {{line: string, countDelta: number}} opts line='recent'|'anchor', 배지 증감
       */
      function updateAsCellSummary(orderId, html, opts) {
        const cell = document.querySelector('.as-tl-cell[data-order-id="' + orderId + '"]');
        if (!cell) return; // 모바일 카드·상세 표면에는 요약 셀이 없다
        const parsed = document.createElement('div');
        parsed.innerHTML = html;
        const bodyEl = parsed.querySelector('.as-tl-item__body');
        // 블록 경계를 공백으로 살린 뒤 접는다(서버 as_content_html_to_text와 같은 순서).
        if (bodyEl) bodyEl.querySelectorAll('div, p, li, br').forEach((el) => el.after(' '));
        const text = bodyEl ? bodyEl.textContent.replace(/\s+/g, ' ').trim() : '';
        const isAnchor = opts.line === 'anchor';
        const klass = isAnchor ? 'as-tl-cell__anchor' : 'as-tl-cell__recent';
        let line = cell.querySelector('.' + klass);
        if (!line) {
          line = document.createElement('div');
          line.className = klass + ' text-truncate';
          const anchorEl = cell.querySelector('.as-tl-cell__anchor');
          if (!isAnchor && anchorEl) anchorEl.after(line); else cell.prepend(line);
        }
        line.textContent = '';
        // 시스템 항목은 칩 대신 아이콘 — 서버 매크로 분기를 재구현하지 않고 응답에서 옮겨 온다.
        const chip = isAnchor ? null : parsed.querySelector('.as-tl-chip, .as-tl-item__sysicon');
        if (chip) line.append(chip, ' ');
        line.append(text); // 문자열 append = 텍스트 노드(마크업 주입 경로 아님)
        // applyStaticHighlight는 dataset 가드로 재적용을 막는다 — 내용이 바뀌었으니 풀어준다.
        delete line.dataset.highlightApplied;
        highlightTimelineStatic(cell);
        if (!opts.countDelta) return;
        // 기록 0건 셀(.as-tl-cell__empty)은 첫 기록과 함께 확장 버튼으로 승격한다.
        // ponytail: '타임라인 N' 서식이 매크로와 여기 두 곳 — 계약 테스트가 문구 드리프트를 잡는다.
        const badge = cell.querySelector('.as-tl-cell__expand, .as-tl-cell__empty');
        if (!badge) return;
        const prev = badge.classList.contains('as-tl-cell__expand')
          ? parseInt(badge.textContent.replace(/[^0-9]/g, ''), 10) || 0
          : 0;
        badge.className = 'as-tl-cell__expand';
        badge.textContent = '타임라인 ' + (prev + opts.countDelta);
      }

      /**
       * 삭제 응답의 셀 요약 HTML로 접힘 셀(.as-tl-cell)을 통째로 교체한다.
       *
       * 증분 갱신(updateAsCellSummary)을 쓰지 않는 이유 — 방금 지운 기록이 '최근 1줄'이었다면
       * 남은 기록 중 무엇이 새 최근인지 클라가 알 수 없다(스트림 전체를 갖고 있지 않다).
       * 서버가 목록과 같은 매크로로 다시 그린 마크업을 그대로 끼운다.
       *
       * @param {string} orderId 대상 주문 id
       * @param {string} html 서버 렌더 .as-tl-cell 마크업
       */
      function replaceAsCellSummary(orderId, html) {
        const sel = '.as-tl-cell[data-order-id="' + orderId + '"]';
        const cell = document.querySelector(sel);
        if (!cell || !html) return; // 모바일 상세 표면에는 요약 셀이 없다
        cell.outerHTML = html;
        const fresh = document.querySelector(sel);
        if (fresh) highlightTimelineStatic(fresh);
      }

      /**
       * ver7 회차 차트(T15c): 저장된 마지막 유형을 세그먼트 + 숨김 select 에 적용.
       * ver7 확정 사양 "마지막 선택 기억" — fragment 재조회로 차트가 통째 교체될 때마다
       * 다시 발라야 하므로 함수로 뺀다(초기 삽입·refresh 공용).
       */
      function applyChartTypeMemory(chart) {
        if (!chart) return;
        let saved = '';
        try { saved = window.localStorage.getItem('fomsAsRchartType') || ''; } catch (err) { /* 프라이버시 모드 */ }
        const btn = saved && chart.querySelector('.as-rchart-seg__btn[data-type="' + saved + '"]');
        if (!btn) return;
        chart.querySelectorAll('.as-rchart-seg__btn').forEach((b) => b.classList.toggle('is-on', b === btn));
        const typeEl = chart.querySelector('.as-timeline__type');
        if (typeEl) typeEl.value = saved;
      }

      /**
       * 차트 표면 쓰기 성공 후 fragment 재조회로 통째 갱신.
       *
       * 구 타임라인은 항목 1건 낙관 삽입으로 충분했지만, 차트는 쓰기 한 번에 슬롯 칩·
       * 회차 요약·상태 카드 이력·판정 버튼 노출이 함께 변한다 — 부분 갱신을 미러링하면
       * 서버 파생 로직(as_round_chart)이 클라에 두 벌 생긴다. 저장은 이미 성공했으므로
       * 재조회 실패는 조용히 삼킨다(다음 열기에서 회복).
       */
      async function refreshRoundChart(orderId) {
        const chart = document.querySelector('.as-rchart[data-order-id="' + orderId + '"]');
        if (!chart) return;
        try {
          const res = await fetch('/erp/as/timeline/' + encodeURIComponent(orderId), {
            headers: { Accept: 'text/html' }, credentials: 'same-origin' });
          if (!res.ok) return;
          const holder = document.createElement('div');
          holder.innerHTML = await res.text();
          const fresh = holder.querySelector('.as-rchart');
          if (!fresh) return;
          chart.replaceWith(fresh);
          applyChartTypeMemory(fresh);
          highlightTimelineStatic(fresh);
        } catch (err) { /* 네트워크 오류 — 저장 자체는 완료 */ }
      }
      // 가능시간 팝오버 IIFE 등 이 가드 블록 밖 스코프에서도 차트 재조회를 부를 수 있게 노출.
      window.__fomsRefreshRoundChart = refreshRoundChart;

      // 세그먼트 유형 토글(ver7 [C]) — 숨김 select 가 값 SSOT, localStorage 가 기억 SSOT.
      document.addEventListener('click', function (e) {
        const seg = e.target.closest && e.target.closest('.as-rchart-seg__btn');
        if (!seg) return;
        e.preventDefault();
        const chart = seg.closest('.as-rchart');
        if (!chart) return;
        chart.querySelectorAll('.as-rchart-seg__btn').forEach((b) => b.classList.toggle('is-on', b === seg));
        const typeEl = chart.querySelector('.as-timeline__type');
        if (typeEl) typeEl.value = seg.dataset.type || 'memo';
        try { window.localStorage.setItem('fomsAsRchartType', seg.dataset.type || 'memo'); } catch (err) { /* no-op */ }
        const textEl = chart.querySelector('.as-timeline__text');
        if (textEl) textEl.focus();
      });

      // 회차 판정(완결/미결) — 전용 API. prompt 취소(null)=판정 중단(오클릭이 영구 기록이 되지 않게).
      document.addEventListener('click', async function (e) {
        const btn = e.target.closest && e.target.closest('.as-rchart-verdict-btn');
        if (!btn || btn.dataset.busy === '1') return;
        const orderId = btn.dataset.orderId;
        const verdict = btn.dataset.verdict;
        if (!orderId || !verdict) return;
        const label = verdict === 'resolved' ? '완결' : '미결(다음 회차 시작)';
        const reason = window.prompt('회차 판정: ' + label + '\n판정 사유를 입력하세요(비워도 됩니다). 취소를 누르면 판정하지 않습니다.', '');
        if (reason === null) return;
        btn.dataset.busy = '1';
        btn.disabled = true;
        try {
          const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/verdict', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ verdict: verdict, text: reason.trim() }),
          });
          const data = await readTimelineJson(res);
          if (!data.success) throw new Error(data.message || '판정 저장 실패');
          updateAsCellSummary(orderId, data.html, { line: 'recent', countDelta: 1 });
          await refreshRoundChart(orderId); // 회차 구조가 통으로 변한다(미결=새 회차 개시)
        } catch (err) {
          window.alert(String(err && err.message || err || '판정 저장 중 오류'));
        } finally {
          btn.dataset.busy = '';
          btn.disabled = false; // 재조회로 교체됐다면 detached 노드 — 무해한 no-op
        }
      });

      /** 기록 소프트 삭제: confirm 1회 → POST → 항목 DOM 제거 + 셀 요약 교체. */
      document.addEventListener('click', async function (e) {
        const btn = e.target.closest && e.target.closest('.as-tl-item__delete');
        if (!btn || btn.dataset.busy === '1') return;
        const item = btn.closest('.as-tl-item');
        const timeline = btn.closest('.as-timeline, .as-rchart');
        const logId = item && item.dataset.logId;
        const orderId = timeline && timeline.dataset.orderId;
        if (!item || !logId || !orderId) return;
        if (!window.confirm('이 기록을 삭제할까요? 목록에서 사라집니다.')) return;
        btn.dataset.busy = '1';
        btn.disabled = true;
        try {
          const res = await fetch(
            '/api/orders/' + encodeURIComponent(orderId)
            + '/as/log/' + encodeURIComponent(logId) + '/delete',
            { method: 'POST', credentials: 'same-origin' });
          const data = await readTimelineJson(res);
          if (!data.success) throw new Error(data.message || '삭제하지 못했습니다.');
          item.remove(); // btn도 함께 사라지므로 아래 finally의 복구는 무해한 no-op
          replaceAsCellSummary(orderId, data.cell_html);
          // 차트 표면: 삭제가 슬롯/요약에도 반영되도록 재조회(즉시 제거는 위에서 이미 끝).
          if (timeline.classList.contains('as-rchart')) refreshRoundChart(orderId);
        } catch (err) {
          window.alert(err.message || '삭제하지 못했습니다.');
        } finally {
          btn.dataset.busy = '';
          btn.disabled = false;
        }
      });

      /** quick-add 폼 1건 전송 → 성공 시 응답 html을 스트림 맨 앞에 낙관적 삽입. */
      async function submitQuickAdd(form) {
        // 재진입 가드: 버튼 disabled는 키보드 단축키 경로를 막지 못한다. as_log는 append-only라
        // 연타 한 번이 중복 기록을 남긴다(삭제는 소프트 삭제여서 감춰질 뿐 되돌려지지 않는다).
        if (!form || form.dataset.busy === '1') return;
        const orderId = form.dataset.orderId;
        const textEl = form.querySelector('.as-timeline__text');
        const typeEl = form.querySelector('.as-timeline__type');
        const text = (textEl && textEl.value || '').trim();
        if (!orderId || !text) return;
        const chart = form.closest('.as-rchart'); // ver7 차트 표면 분기(T15c)
        const stream = form.parentElement.querySelector('.as-timeline__stream');
        const submitBtn = form.querySelector('.as-timeline__submit');
        form.dataset.busy = '1';
        if (submitBtn) submitBtn.disabled = true;
        try {
          const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/log', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ type: (typeEl && typeEl.value) || 'memo', text: text }),
          });
          const data = await readTimelineJson(res);
          if (!data.success) throw new Error(data.message || '기록 추가 실패');
          if (stream) {
            stream.insertAdjacentHTML('afterbegin', data.html); // optimistic prepend
            highlightTimelineStatic(stream);
            // 첫 기록이면 "기록 없음" 안내가 새 항목 옆에 남는다 — 서버 재렌더 없이 치운다.
            const empty = form.parentElement.querySelector('.as-timeline__empty');
            if (empty) empty.remove();
          }
          // 접힘 셀 요약도 같이 민다 — 확장 행을 닫는 순간 옛 요약만 남으면 안 된다.
          updateAsCellSummary(orderId, data.html, { line: 'recent', countDelta: 1 });
          textEl.value = '';
          if (chart) {
            // 차트: 슬롯 칩·회차 표가 함께 변한다 — 재조회 1회로 정합(유형은 기억 유지).
            await refreshRoundChart(orderId);
          } else if (typeEl) {
            typeEl.value = 'memo'; // 구 표면: 저장 후 memo 리셋(스펙 5.5)
          }
        } catch (err) {
          // 입력 텍스트는 지우지 않는다 — 재시도 가능해야 한다.
          alert(String(err && err.message || err || '기록 추가 중 오류'));
        } finally {
          form.dataset.busy = '';
          if (submitBtn) submitBtn.disabled = false;
        }
      }

      /** 항목 수정 폼 전송 → PATCH 성공 시 해당 항목만 응답 html로 교체((수정됨) 표식 포함). */
      async function submitLogEdit(form) {
        if (!form || form.dataset.busy === '1') return;  // quick-add와 동일한 재진입 가드
        const item = form.closest('.as-tl-item');
        const timeline = form.closest('.as-timeline, .as-rchart');
        const logId = item && item.dataset.logId;
        const orderId = timeline && timeline.dataset.orderId;
        const textEl = form.querySelector('.as-timeline__text');
        const text = (textEl && textEl.value || '').trim();
        if (!logId || !orderId || !text) return;
        const submitBtn = form.querySelector('.as-timeline__submit');
        form.dataset.busy = '1';
        if (submitBtn) submitBtn.disabled = true;
        try {
          const res = await fetch('/api/orders/' + encodeURIComponent(orderId)
            + '/as/log/' + encodeURIComponent(logId), {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ text: text }),
          });
          const data = await readTimelineJson(res);
          if (!data.success) throw new Error(data.message || '기록 수정 실패');
          if (timeline.classList.contains('as-rchart')) {
            // 차트: 응답 html 은 구 타임라인 마크업이라 행에 못 끼운다 — 재조회로 통째 갱신.
            await refreshRoundChart(orderId);
            return;
          }
          const parent = item.parentElement;
          // 셀 요약이 비추는 항목(앵커 = 접수/legacy, 최근 1건 = 스트림 첫 항목)을 고쳤을 때만
          // 셀을 민다. 판정은 교체 전에 — outerHTML 이후 item 참조는 DOM에서 떨어진다.
          const stream = item.closest('.as-timeline__stream');
          const cellLine = item.closest('.as-timeline__anchor') ? 'anchor'
            : (stream && stream.firstElementChild === item ? 'recent' : '');
          item.outerHTML = data.html;
          highlightTimelineStatic(parent);
          if (cellLine) updateAsCellSummary(orderId, data.html, { line: cellLine, countDelta: 0 });
        } catch (err) {
          // 400(캡 초과)·403(타인 기록)에서 입력 원문을 잃지 않는다 — 폼을 연 채로 둔다.
          alert(String(err && err.message || err || '기록 수정 중 오류'));
        } finally {
          form.dataset.busy = '';
          if (submitBtn) submitBtn.disabled = false;
        }
      }

      /** 상태 셀의 비용 배지를 서버 렌더 html로 교체(무배지면 제거). PC 표면 전용. */
      function updateAsBillingBadge(orderId, html) {
        const cell = document.querySelector('.erp-as-status-cell[data-order-id="' + orderId + '"]');
        if (!cell) return; // 모바일 카드에는 상태 셀이 없다
        const old = cell.querySelector('.erp-as-billing-badge');
        if (old) old.remove();
        if (html) cell.insertAdjacentHTML('beforeend', html);
      }

      /**
       * 비용 판정 폼 전송 → 판정 표기·상태 배지·타임라인·셀 요약을 응답으로 갱신(재조회 없음).
       *
       * 전환 사유 필수 판정은 서버(400)가 소유한다 — 클라가 미리 막으면 규칙이 두 곳에 산다.
       */
      async function submitBillingDecision(form) {
        if (!form || form.dataset.busy === '1') return; // quick-add와 동일한 재진입 가드
        const timeline = form.closest('.as-timeline, .as-rchart');
        const orderId = timeline && timeline.dataset.orderId;
        const typeEl = form.querySelector('.as-billing-type');
        const amountEl = form.querySelector('.as-billing-amount');
        const reasonEl = form.querySelector('.as-billing-reason');
        if (!orderId || !typeEl) return;
        const payload = { type: typeEl.value, reason: (reasonEl && reasonEl.value || '').trim() };
        const amountRaw = (amountEl && amountEl.value || '').trim();
        // 빈 금액을 실어 보내면 서버가 "명시적 삭제"로 읽어 확정 청구액을 지운다 —
        // 값이 있을 때만 키를 넣어 기존 금액 보존 경로를 탄다.
        if (payload.type === 'paid' && amountRaw !== '') payload.amount = Number(amountRaw);
        const submitBtn = form.querySelector('.as-timeline__submit');
        form.dataset.busy = '1';
        if (submitBtn) submitBtn.disabled = true;
        try {
          const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/billing', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify(payload),
          });
          const data = await readTimelineJson(res);
          if (!data.success) throw new Error(data.message || '판정 저장 실패');
          const state = timeline.querySelector('.as-billing-state');
          if (state) {
            state.textContent = '비용 ' + (data.state_text || '');
            state.dataset.billingType = payload.type;
          }
          updateAsBillingBadge(orderId, data.badge_html);
          // 판정 이벤트가 실제로 기록됐을 때만(동일 유형 재확정은 html이 빈 문자열) 스트림·셀 갱신.
          if (data.html) {
            const stream = timeline.querySelector('.as-timeline__stream');
            if (stream) {
              stream.insertAdjacentHTML('afterbegin', data.html);
              highlightTimelineStatic(stream);
              const empty = timeline.querySelector('.as-timeline__empty');
              if (empty) empty.remove();
            }
            updateAsCellSummary(orderId, data.html, { line: 'recent', countDelta: 1 });
          }
          form.remove();
          // 차트: 비용 이벤트는 상태 카드 이력으로 흡수된다(스트림 없음) — 재조회로 반영.
          if (timeline.classList.contains('as-rchart')) await refreshRoundChart(orderId);
        } catch (err) {
          // 400(사유 누락·금액 오류)·403에서 입력을 잃지 않는다 — 폼을 연 채로 둔다.
          alert(String(err && err.message || err || '판정 저장 중 오류'));
        } finally {
          form.dataset.busy = '';
          if (submitBtn) submitBtn.disabled = false;
        }
      }

      // 판정 변경 버튼 → 헤더 아래 인라인 폼(멱등). 접수 모달이 안내하는 "AS 대시보드에서 변경".
      document.addEventListener('click', function (e) {
        const btn = e.target.closest && e.target.closest('.as-billing-edit');
        if (!btn) return;
        const timeline = btn.closest('.as-timeline, .as-rchart');
        const header = btn.closest('.as-timeline__header, .as-rchart-head');
        if (!timeline || !header || timeline.querySelector('.as-billing-form')) return;
        const state = timeline.querySelector('.as-billing-state');
        const current = (state && state.dataset.billingType) || 'free';
        const form = document.createElement('form');
        form.className = 'as-billing-form';
        form.setAttribute('data-foms-erp-no-shell', ''); // 셸 GET submit 가로채기 회피
        form.innerHTML = '<select class="as-billing-type erp-pro-select" aria-label="비용 판정">'
          + '<option value="free">무상</option><option value="paid">유상</option>'
          + '<option value="undecided">미정</option></select>'
          + '<input type="number" min="0" step="1000" class="as-billing-amount erp-pro-input" placeholder="금액(원)" aria-label="유상 금액">'
          + '<input type="text" class="as-billing-reason erp-pro-input" placeholder="사유 (확정 후 전환 시 필수)" aria-label="판정 사유">'
          + '<button type="submit" class="btn btn-sm btn-primary as-timeline__submit">저장</button>'
          + '<button type="button" class="btn btn-sm btn-link as-billing-cancel">취소</button>';
        const typeEl = form.querySelector('.as-billing-type');
        const amountEl = form.querySelector('.as-billing-amount');
        typeEl.value = current;
        amountEl.hidden = current !== 'paid';
        typeEl.addEventListener('change', function () { amountEl.hidden = typeEl.value !== 'paid'; });
        header.after(form);
        typeEl.focus();
      });

      document.addEventListener('click', function (e) {
        const cancel = e.target.closest && e.target.closest('.as-billing-cancel');
        if (cancel) cancel.closest('.as-billing-form').remove();
      });

      // 수정 버튼 → 본문 자리에 인라인 폼(멱등: 이미 열려 있으면 무시).
      document.addEventListener('click', function (e) {
        const btn = e.target.closest && e.target.closest('.as-tl-item__edit');
        if (!btn) return;
        const item = btn.closest('.as-tl-item');
        const body = item && item.querySelector('.as-tl-item__body');
        if (!body || item.querySelector('.as-tl-item__edit-form')) return;
        const form = document.createElement('form');
        form.className = 'as-tl-item__edit-form';
        form.setAttribute('data-foms-erp-no-shell', '');  // erp-shell GET submit 가로채기 회피
        form.innerHTML = '<textarea class="as-timeline__text erp-pro-input" rows="2" aria-label="기록 내용 수정"></textarea>'
          + '<button type="submit" class="btn btn-sm btn-primary as-timeline__submit">저장</button>'
          + '<button type="button" class="btn btn-sm btn-link as-tl-item__edit-cancel">취소</button>';
        // innerHTML로 채운다: 본문은 서버 sanitize를 통과한 rich HTML이고 재저장 시 같은
        // sanitizer를 다시 타므로 왕복이 안정적이다. textContent면 서식(<b>/색)이 조용히 사라진다.
        // 단 검색 하이라이트가 실제로 삽입한 <mark class="as-search-highlight">는 화면 장식이지
        // 기록 본문이 아니다 — 사본에서 벗겨낸 뒤 시드해야 사용자가 정체불명 태그를 편집하지 않고
        // 저장 시 <mark>가 본문으로 굳지 않는다(sanitizer는 mark를 unwrap하지만 그 전에 노출된다).
        const seed = body.cloneNode(true);
        seed.querySelectorAll('mark.as-search-highlight')
          .forEach((mark) => mark.replaceWith(...mark.childNodes));
        const textEl = form.querySelector('.as-timeline__text');
        textEl.value = seed.innerHTML.trim();
        body.hidden = true;
        body.after(form);
        textEl.focus();
      });

      document.addEventListener('click', function (e) {
        const cancel = e.target.closest && e.target.closest('.as-tl-item__edit-cancel');
        if (!cancel) return;
        const item = cancel.closest('.as-tl-item');
        const form = item && item.querySelector('.as-tl-item__edit-form');
        if (!form) return;
        form.remove();
        const body = item.querySelector('.as-tl-item__body');
        if (body) body.hidden = false;
      });

      document.addEventListener('submit', function (e) {
        const quickAdd = e.target.closest && e.target.closest('.as-timeline__quick-add');
        if (quickAdd) { e.preventDefault(); submitQuickAdd(quickAdd); return; }
        const editForm = e.target.closest && e.target.closest('.as-tl-item__edit-form');
        if (editForm) { e.preventDefault(); submitLogEdit(editForm); return; }
        const billingForm = e.target.closest && e.target.closest('.as-billing-form');
        if (billingForm) { e.preventDefault(); submitBillingDecision(billingForm); }
      });

      // Ctrl/⌘+Enter 단축키. 한글 IME 조합 확정 Enter가 전송으로 새지 않도록 isComposing·229 가드.
      document.addEventListener('keydown', function (e) {
        const textEl = e.target.closest && e.target.closest('.as-timeline__text');
        if (!textEl) return;
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
          e.preventDefault();
          const quickAdd = textEl.closest('.as-timeline__quick-add');
          if (quickAdd) { submitQuickAdd(quickAdd); return; }
          submitLogEdit(textEl.closest('.as-tl-item__edit-form'));
        }
      });

      // T15 원탭 프리셋: 초안 주입 + 유형 설정 + focus 까지만. **자동 전송 금지** —
      // as_log 는 append-only(삭제 API 없음)라 오탭 한 번이 영구 기록이 된다. 사람이 문장을
      // 다듬고 스스로 전송하는 것이 이 기능의 본체이고, 프리셋은 타이핑만 줄인다.
      document.addEventListener('click', function (e) {
        const preset = e.target.closest && e.target.closest('.as-tl-preset');
        if (!preset) return;
        const timeline = preset.closest('.as-timeline');
        const form = timeline && timeline.querySelector('.as-timeline__quick-add');
        if (!form) return;
        const textEl = form.querySelector('.as-timeline__text');
        const typeEl = form.querySelector('.as-timeline__type');
        if (typeEl) typeEl.value = preset.dataset.type || 'memo';
        if (textEl) {
          // 비파괴 주입: 타이핑 중이던 원고를 덮지 않고 뒤에 잇는다(입력 손실 0).
          // value 대입은 undo 스택을 어차피 끊으므로, 최소한 글자는 잃지 않게 한다.
          const prev = textEl.value.trim();
          textEl.value = prev
            ? prev + ' ' + (preset.dataset.text || '')
            : (preset.dataset.text || '');
          textEl.focus(); // 수기 수정 후 저장 — 전송은 사람이 한다
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
        // 수정 폼은 JS가 만든 것이라 재렌더로 복원할 수 없다 — 편집 중 원고가 있으면 먼저 확인받는다.
        // ponytail: 확인 1회로 끝낸다. 편집 원고까지 자동 보존하려면 log-id로 폼을 재개설해야 하는데
        // 흔치 않은 동선(수정 열어둔 채 더보기)에 비해 비싸다.
        if (body.querySelector('.as-tl-item__edit-form')
            && !window.confirm('수정 중인 기록이 있습니다. 이전 기록을 더 불러오면 수정 내용이 사라집니다. 계속할까요?')) {
          return;
        }
        // innerHTML 교체는 미전송 초안을 지운다 — quick-add 입력값을 보존했다 되돌린다.
        const draftEl = body.querySelector('.as-timeline__quick-add .as-timeline__text');
        const draft = draftEl ? draftEl.value : '';
        fetch('/erp/as/timeline/' + encodeURIComponent(orderId) + '?full=1',
              { headers: { Accept: 'text/html' }, credentials: 'same-origin' })
          .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
          .then((html) => {
            body.innerHTML = html;
            const nextDraftEl = body.querySelector('.as-timeline__quick-add .as-timeline__text');
            if (nextDraftEl && draft) nextDraftEl.value = draft;
            highlightTimelineStatic(body);
          })
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

    // ───────── 기준 일정 매칭 링크(schedule_link) 공용 배선 ─────────
    // 스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md §5·§6.
    // T3(모달 '이 일정에 매칭')과 T5(행 재적용/무시/해제)가 같은 POST를 쓰므로 헬퍼는 여기 하나.
    // CSRF 헤더는 layout_head.html의 전역 fetch 인터셉터가 붙인다(여기서 수동 부착 금지 — 중복).

    /**
     * 응답 본문을 텍스트로 받아 방어적으로 JSON 파싱한다(선례: shipment-dashboard.js).
     *
     * 세션 만료 리다이렉트는 HTML을 200/302로 돌려준다 — res.json()을 바로 쓰면
     * SyntaxError가 나고, .catch가 없으면 버튼이 아무 반응 없이 죽는다(무음 실패).
     * 파싱 실패는 상태코드를 담은 실패 객체로 접어 호출부가 항상 메시지를 낼 수 있게 한다.
     */
    function parseJsonResponse(r) {
      return r.text().then(function (text) {
        var data = null;
        try {
          data = text ? JSON.parse(text) : null;
        } catch (e) {
          data = null;
        }
        if (!data || typeof data !== 'object') {
          data = { success: false, message: '서버 응답 오류 (' + r.status + ')' };
        }
        return { ok: r.ok, status: r.status, data: data };
      });
    }

    /** POST /api/orders/<id>/as/schedule-link — body는 {action, ref_order_id?, ref_date?}. */
    function postScheduleLink(asOrderId, body) {
      return fetch('/api/orders/' + encodeURIComponent(asOrderId) + '/as/schedule-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      }).then(parseJsonResponse);
    }

    /** 링크 API 응답에서 사람이 읽을 실패 사유를 뽑는다(없으면 기본 문구). */
    function scheduleLinkErrorText(res, fallback) {
      var d = (res && res.data) || {};
      return String(d.message || d.error || fallback);
    }

    /**
     * 재적용 1단계 — 기존 날짜 저장 경로(saveDateField)를 그대로 태운다.
     *
     * 새 날짜 쓰기 엔드포인트/포맷을 만들지 않는 이유: as_visit_date 쓰기는
     * POST /api/update_order_field 하나가 SSOT고, 그 경로가 as_log에 '방문일 확정'
     * system 항목까지 남긴다. 여기서 직접 fetch하면 그 부수효과와 화면 동기화가 갈라진다.
     * saveDateField는 실패 시 입력값을 원래대로 되돌리고 throw한다(silent=토스트만 억제).
     */
    async function applyRefDateToAsVisit(orderId, refCurrentDate) {
      const input = getDateInputsForOrder(orderId, 'as_visit_date')[0];
      if (!input) throw new Error('방문일 입력을 찾을 수 없습니다. 새로고침 후 다시 시도해주세요.');
      // 순서 주의: 저장 상태는 첫 조회 시점의 input.value 로 savedValue 를 굳힌다.
      // 값을 먼저 바꾸면 savedValue == value 가 되어 saveDateField 가 skipped 로 빠지고
      // 요청이 아예 안 나간다(무음 no-op). 그래서 상태를 먼저 깨운다.
      getDateFieldSaveState(input);
      input.value = refCurrentDate;
      return saveDateField(input, { silent: true });
    }

    // 행 액션 3종(재적용/무시/연결 해제). 성공 후 목록 재조회는 이 파일의 기존 방식
    // (buildAsDashboardUrl + focus_order)을 그대로 쓴다 — 배지 문구·배너 카운트의 SSOT가
    // 서버(as_dashboard_display)라 클라에서 라벨을 다시 조립하면 두 구현으로 갈라진다.
    addAsDashboardListener(document.body, 'click', async function (e) {
      const btn = e.target.closest('.js-as-drift-relink, .js-as-drift-ack, .js-as-drift-unlink');
      if (!btn) return;
      e.stopPropagation();
      e.preventDefault();
      const orderId = btn.dataset.asOrderId;
      if (!orderId) return;
      const refCurrentDate = btn.dataset.refCurrentDate || '';
      const isRelink = btn.classList.contains('js-as-drift-relink');
      const isUnlink = btn.classList.contains('js-as-drift-unlink');
      if (isUnlink && !window.confirm('기준 일정 연결을 해제할까요? AS 방문일은 그대로 둡니다.')) return;
      // both_moved = 방문일도 손으로 따로 바뀐 상태 — 재적용은 그 값을 덮어쓴다(스펙 §4).
      if (isRelink && btn.dataset.driftState === 'both_moved'
        && !window.confirm('AS 방문일이 따로 변경돼 있습니다. 기준 주문의 새 일정(' + refCurrentDate + ')으로 덮어쓸까요?')) return;
      const action = isRelink ? 'relink' : (isUnlink ? 'unlink' : 'ack');
      btn.disabled = true;
      try {
        if (isRelink) {
          if (!refCurrentDate) throw new Error('기준 주문의 새 일정을 알 수 없습니다.');
          await applyRefDateToAsVisit(orderId, refCurrentDate);
        }
        const res = await postScheduleLink(orderId, { action: action });
        if (!res.ok || res.data.success !== true) {
          throw new Error(scheduleLinkErrorText(res, '기준 일정 처리에 실패했습니다.'));
        }
        window.location.href = buildAsDashboardUrl({ focus_order: orderId });
      } catch (err) {
        btn.disabled = false;
        showFeedback(String((err && err.message) || err || '기준 일정 처리 중 오류가 발생했습니다.'), true);
      }
    });

    // ───────── 가까운 일정 찾기 ─────────
    (function () {
      // 탭별 pre-computed 리스트 (백엔드에서 각각 계산해 내려줌)
      let _lists = { distance: [], date: [], combined: [] };
      // 재검색 시 사용할 현재 주문 컨텍스트.
      // linkedRefId = 이 AS 건에 이미 걸려 있는 기준 주문 id(서버 렌더 data-linked-ref-order-id).
      // /api/orders/nearby 는 링크를 모르므로 이 값이 없으면 모달을 다시 열 때마다
      // 이미 매칭된 후보가 미매칭('이 일정에 매칭')으로 그려진다.
      let _searchState = { excludeId: null, lat: null, lng: null, linkedRefId: '' };
      // 일정찾기 성공 응답 기준 좌표 (지도 모달 출발점)
      let _refLat = null;
      let _refLng = null;
      let _refAddress = '';

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
          // '이 일정에 매칭'(T3) — 기준 AS id는 모달을 연 버튼이 남긴 _searchState.excludeId.
          // 없으면(주소 재검색 등으로 컨텍스트 유실) 버튼 자체를 렌더하지 않는다: 대상 없는
          // 버튼이 눌리면 어디에도 못 쓰고 조용히 실패한다.
          const linkBtnHtml = _searchState.excludeId
            ? `<button type="button" class="btn btn-sm btn-outline-primary js-as-schedule-link"
                data-ref-order-id="${esc(item.id)}" data-ref-date="${esc(item.date)}">
                <i class="fas fa-link"></i> 이 일정에 매칭
              </button>`
            : '';
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
              <span class="as-schedule-result__btns">${mapBtnHtml}${linkBtnHtml}</span>
              <small class="text-primary fw-bold"><i class="fas fa-external-link-alt"></i> 바로가기</small>
            </div>
            ${linkBtnHtml ? '<div class="as-schedule-link-msg text-danger small mt-1" role="alert"></div>' : ''}`;
          resList.appendChild(el);
        });
        // 기존 링크 표시는 매칭 직후와 **같은 함수**를 탄다 — 라벨/비활성/클래스를 여기서
        // 따로 조립하면 두 구현이 반드시 갈라진다(모달 재오픈 시 '매칭됨' 소실 회귀).
        // 링크는 있는데 후보 목록에 그 주문이 없으면 activeBtn=null → 전부 '매칭 변경'(정확한 표시).
        if (_searchState.linkedRefId) {
          markScheduleLinkApplied(
            Array.from(resList.querySelectorAll('.js-as-schedule-link'))
              .find((b) => b.dataset.refOrderId === _searchState.linkedRefId) || null
          );
        }
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
        _searchState = {
          excludeId: orderId,
          lat: btnLat,
          lng: btnLng,
          linkedRefId: String(btn.dataset.linkedRefOrderId || ''),
        };
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

      /**
       * 매칭 상태 표시의 단일 경로 — 누른/이미 걸린 버튼은 '매칭됨'(비활성),
       * 나머지는 '매칭 변경'(1 AS = 1 링크). 매칭 직후와 모달 최초 렌더가 이 함수를
       * 공유한다(renderResults 말미 호출). activeBtn=null 이면 전부 '매칭 변경'.
       */
      function markScheduleLinkApplied(activeBtn) {
        const resList = document.getElementById('scheduleSearchResults');
        if (!resList) return;
        resList.querySelectorAll('.js-as-schedule-link').forEach(function (b) {
          const isActive = b === activeBtn;
          b.textContent = isActive ? '매칭됨' : '매칭 변경';
          b.disabled = isActive;
          b.classList.toggle('btn-outline-primary', !isActive);
          b.classList.toggle('btn-success', isActive);
        });
      }

      /**
       * 매칭 직후 AS 방문일을 기준 주문 시공일로 채운다(기존 날짜 저장 경로 재사용).
       *
       * 링크는 이미 저장된 뒤에 호출된다 — 여기서 실패해도 매칭 자체는 유효하므로
       * 버튼 상태를 되돌리지 않고 안내만 남긴다(무음 실패 금지).
       *
       * @param {string} asOrderId 대상 AS 주문 id.
       * @param {string} refDate 서버가 확정한 기준 주문 시공일(link.ref_date).
       * @param {(text: string) => void} notify 사용자에게 보이는 안내 출력.
       * @returns {Promise<boolean>} 목록 재조회로 진행해도 되는지(안내만 남겼으면 false).
       */
      async function writeAsVisitDateFromLink(asOrderId, refDate, notify) {
        if (!refDate) {
          notify('매칭은 저장됐지만 기준 일정 날짜가 비어 있어 방문일을 채우지 못했습니다.');
          return false;
        }
        // 방문일 입력은 모달 뒤 대시보드 DOM에 있다. 없으면(다른 표면에서 연 모달 등)
        // 링크만 남기고 사람이 직접 넣도록 안내한다 — 액션 전체를 실패시키지 않는다.
        const input = getDateInputsForOrder(asOrderId, 'as_visit_date')[0];
        if (!input) {
          notify('매칭은 저장됐습니다. 다만 방문일 입력을 찾지 못해 ' + refDate + ' 자동 입력에 실패했습니다 — 새로고침 후 직접 입력해주세요.');
          return false;
        }
        const current = input.value || '';
        if (current && current !== refDate
          && !window.confirm('AS 방문일이 ' + current + '로 지정돼 있습니다. 기준 일정(' + refDate + ')으로 바꿀까요?')) {
          return true;
        }
        // 같은 날짜면 saveDateField 가 skipped 로 no-op 한다(요청 자체가 안 나간다).
        await applyRefDateToAsVisit(asOrderId, refDate);
        return true;
      }

      // 결과 행 전체가 <a href="/edit/...">라 stopPropagation+preventDefault가 첫 줄이어야 한다
      // (지도 버튼 선례). 없으면 요청은 날아가지만 화면이 편집 페이지로 이탈해 결과를 못 본다.
      addAsDashboardListener(document.body, 'click', async function (e) {
        const btn = e.target.closest('.js-as-schedule-link');
        if (!btn) return;
        e.stopPropagation();
        e.preventDefault();
        const asOrderId = _searchState.excludeId;
        if (!asOrderId) return;
        const row = btn.closest('.list-group-item');
        const msgEl = row ? row.querySelector('.as-schedule-link-msg') : null;
        function notify(text) {
          if (msgEl) msgEl.textContent = text;
          else showFeedback(text, true);
        }
        if (msgEl) msgEl.textContent = '';
        btn.disabled = true;
        let refDate = '';
        try {
          const res = await postScheduleLink(asOrderId, {
            action: 'link',
            ref_order_id: parseInt(btn.dataset.refOrderId, 10),
            ref_date: btn.dataset.refDate || '',
          });
          if (!res.ok || res.data.success !== true) {
            throw new Error(scheduleLinkErrorText(res, '매칭에 실패했습니다.'));
          }
          // 서버가 기준 주문에서 다시 읽은 값이 정본(스펙 §6, 모달 stale 방지).
          refDate = String((res.data.link && res.data.link.ref_date) || '');
        } catch (err) {
          // 라벨은 손대지 않는다 — 실패 시 되돌리면 아이콘(<i>)까지 지워진다.
          btn.disabled = false;
          notify(String((err && err.message) || err || '매칭 중 오류가 발생했습니다.'));
          return;
        }
        // 여기부터 링크는 저장 완료 — 이후 실패는 '매칭됨' 표시를 되돌리지 않는다.
        _searchState.linkedRefId = String(btn.dataset.refOrderId || '');
        markScheduleLinkApplied(btn);
        try {
          if (!await writeAsVisitDateFromLink(asOrderId, refDate, notify)) return;
        } catch (err) {
          notify('매칭은 저장됐지만 방문일 저장에 실패했습니다: '
            + String((err && err.message) || err || '알 수 없는 오류'));
          return;
        }
        // 배지·배너 문구의 SSOT 는 서버(as_dashboard_display) — 행 액션과 같은 방식으로
        // 목록을 다시 받아 재계산시킨다. 모달 작업(링크+방문일)이 끝난 뒤에만 이동한다.
        window.location.href = buildAsDashboardUrl({ focus_order: asOrderId });
      });

      // 지도 렌더·SDK 주입·경로 조회·정리는 공용 모듈 static/js/common/foms-schedule-map.js 소관
      // (출고 대시보드와 공유). 여기서는 기준 좌표 + 버튼 data-* 만 넘긴다.
      addAsDashboardListener(document.body, 'click', function (e) {
        const btn = e.target.closest('.schedule-map-btn');
        if (!btn) return;
        e.stopPropagation();
        e.preventDefault();
        const modalEl = document.getElementById('scheduleMapModal');
        if (!modalEl || !window.FOMS_SCHEDULE_MAP) return;
        const targetLat = parseFloat(btn.dataset.lat);
        const targetLng = parseFloat(btn.dataset.lng);
        if (!_refLat || !_refLng) return;
        if (!Number.isFinite(targetLat) || !Number.isFinite(targetLng)) return;
        window.FOMS_SCHEDULE_MAP.open({
          modalEl: modalEl,
          ref: { lat: _refLat, lng: _refLng, address: _refAddress },
          target: {
            lat: targetLat,
            lng: targetLng,
            address: btn.dataset.address || '',
            name: btn.dataset.name || ''
          },
          scoreText: btn.dataset.scoreText || ''
        });
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

      // AS PUSH: 본문은 서버가 저장된 주문으로 조립한다(SSOT) — 이 화면에는 주문 폼이 없다.
      // 재전송(이미 보낸 이력 있음)이면 서버가 400 으로 변경 내용을 요구하므로 prompt 후 1회 재시도.
      var asChannelPushBtn = document.getElementById('as-modal-channel-push-btn');
      if (asChannelPushBtn) {
        addAsDashboardListener(asChannelPushBtn, 'click', async function () {
          var orderId = __currentAsModalOrderId;
          if (!orderId) return;
          if (!confirm('AS 접수 내용과 AS 첨부를 채널톡 AS방으로 전송할까요?')) return;

          async function send(changeNote) {
            var payload = { order_id: Number(orderId), push_kind: 'as' };
            if (changeNote) payload.change_note = changeNote;
            var resp = await fetch('/api/channel/push-manual', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            return resp.json();
          }

          asChannelPushBtn.disabled = true;
          var originalHtml = asChannelPushBtn.innerHTML;
          asChannelPushBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 전송중...';
          try {
            var data = await send(null);
            if (!data.success) {
              var msg = data.error || data.message || '알 수 없는 오류';
              if (msg.indexOf('재전송 시 변경 내용') >= 0) {
                var note = (window.prompt('이미 전송한 주문입니다. 변경 내용을 입력해주세요.') || '').trim();
                if (!note) return;
                data = await send(note);
              }
            }
            if (data.success) {
              showFeedback('AS방으로 전송했습니다. (첨부 ' + (data.files_count || 0) + '건)');
            } else {
              showFeedback('전송 실패: ' + (data.error || data.message || '알 수 없는 오류'), true);
            }
          } catch (err) {
            showFeedback('네트워크 오류: ' + String((err && err.message) || err || ''), true);
          } finally {
            asChannelPushBtn.disabled = false;
            asChannelPushBtn.innerHTML = originalHtml;
          }
        });
      }

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
    //   → DOMContentLoaded까지 대기해야 bootstrap/flatpickr 등 전역이 모두 준비된다.
    // - erp-shell fragment swap: 페이지가 이미 'complete' → 즉시 init(스왑마다 재실행, AbortController로 idempotent).
    if (document.readyState === 'complete') {
      initAsDashboard();
    } else {
      document.addEventListener('DOMContentLoaded', initAsDashboard, { once: true });
    }
  })();
