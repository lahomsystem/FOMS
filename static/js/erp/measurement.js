(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const container = document.querySelector('.erp-pro');
        if (!container) return;

        // measurement-manual-rows.js가 덮어씀 (로드 순서 대비 noop)
        window.measurementManualRowsPersist = window.measurementManualRowsPersist || function () {};
        window.measurementManualRowsRecomputeAnchors = window.measurementManualRowsRecomputeAnchors || function () {};

        // Config from data attributes
        const erpActiveRaw = container.dataset.erpBetaActive ?? container.dataset.erpActive;
        const config = {
            erpBetaActive: erpActiveRaw === 'true',
            todayDate: container.dataset.todayDate,
            selectedDate: container.dataset.selectedDate,
            managerFilter: container.dataset.managerFilter || ''
        };

        if (!config.erpBetaActive) return;

        const tbody = document.querySelector('.measurement-table tbody');
        if (!tbody) return;

        const MEASUREMENT_MANAGER_COLORS = ['#FF0000', '#0080FF', '#FFFF00', '#00FF00', '#FF00FF', '#00FFFF', '#FF8000', '#FF1493', '#00FF80', '#FF69B4'];

        function getManagerFromRow(tr) {
            const cell = tr.querySelector('td.manager-cell');
            return (cell && (cell.textContent || '').trim()) || '';
        }
        function managerKeyForSort(tr) {
            const m = getManagerFromRow(tr);
            if (!m || m === '-') return 'ZZZ';
            return m.toLowerCase();
        }
        function rowTieBreak(tr) {
            if (tr.classList.contains('measurement-row-manual')) {
                return 100000000 + (parseInt(tr.dataset.manualSeq, 10) || 0);
            }
            return parseInt(tr.dataset.orderId, 10) || 0;
        }
        function applyMeasurementManagerSortAndColors() {
            const mainRows = Array.from(tbody.querySelectorAll('tr.measurement-row'));
            if (!mainRows.length) return;
            // 서버 렌더링 색 — 수동 행은 제외(JS만 적용)
            mainRows.forEach(function (tr) {
                if (tr.classList.contains('measurement-row-manual')) return;
                const cell = tr.querySelector('td.manager-cell');
                if (!cell) return;
                const bg = cell.dataset.bg;
                const color = cell.dataset.color;
                if (bg) cell.style.setProperty('background-color', bg, 'important');
                if (color) cell.style.setProperty('color', color, 'important');
            });
            const pairs = mainRows.map(function (tr) {
                const orderId = tr.dataset.orderId || '';
                const next = tr.nextElementSibling;
                const isManual = tr.classList.contains('measurement-row-manual');
                const detailRow =
                    !isManual &&
                    next &&
                    next.classList &&
                    next.classList.contains('measurement-detail-row') &&
                    (next.dataset.orderId === orderId || next.id === 'detail-' + orderId)
                        ? next
                        : null;
                return { main: tr, detail: detailRow };
            });
            pairs.sort(function (a, b) {
                const mA = managerKeyForSort(a.main);
                const mB = managerKeyForSort(b.main);
                if (mA !== mB) return mA.localeCompare(mB);
                return rowTieBreak(a.main) - rowTieBreak(b.main);
            });
            pairs.forEach(function (p) {
                tbody.appendChild(p.main);
                if (p.detail) tbody.appendChild(p.detail);
            });
            const managerList = [];
            mainRows.forEach(function (tr) {
                const m = getManagerFromRow(tr);
                const key = (m && m !== '-') ? m.toLowerCase() : '';
                if (key && managerList.indexOf(key) === -1) managerList.push(key);
            });
            mainRows.forEach(function (tr) {
                const cell = tr.querySelector('td.manager-cell');
                if (!cell) return;
                const m = getManagerFromRow(tr);
                const key = (m && m !== '-') ? m.toLowerCase() : '';
                const idx = key ? managerList.indexOf(key) : -1;
                const color = idx >= 0 ? MEASUREMENT_MANAGER_COLORS[idx % MEASUREMENT_MANAGER_COLORS.length] : '#CCCCCC';
                cell.setAttribute('data-manager-bg-color', color);
                cell.style.setProperty('--manager-bg-color', color);
                cell.style.setProperty('background-color', color, 'important');
                cell.style.setProperty('color', '#000000', 'important');
                tr.dataset.manager = m || '';
            });
            window.measurementManualRowsRecomputeAnchors();
            window.measurementManualRowsPersist();
        }
        function scheduleApplyMeasurementManagerSortAndColors() {
            setTimeout(applyMeasurementManagerSortAndColors, 0);
        }

        window.applyMeasurementManagerSortAndColors = applyMeasurementManagerSortAndColors;
        window.scheduleApplyMeasurementManagerSortAndColors = scheduleApplyMeasurementManagerSortAndColors;

        // 1. Scroll to today
        const todayId = 'date-' + config.todayDate;
        const todayEl = document.getElementById(todayId);
        const panelList = document.querySelector('.measurement-panel-list');
        if (todayEl && panelList) {
            todayEl.scrollIntoView({ block: 'center' });
        }

        // 2. Manager Cell Colors
        applyMeasurementManagerSortAndColors();

        // 2b. 주문 상세 chevron 토글
        document.querySelectorAll('.measurement-chevron').forEach(function (chevron) {
            chevron.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                var orderId = this.dataset.orderId;
                var detailRow = orderId ? document.getElementById('detail-' + orderId) : null;
                if (!detailRow) return;
                var isOpen = this.getAttribute('aria-expanded') === 'true';
                if (isOpen) {
                    detailRow.style.display = 'none';
                    detailRow.setAttribute('aria-hidden', 'true');
                    this.setAttribute('aria-expanded', 'false');
                    this.classList.remove('is-open');
                } else {
                    detailRow.style.display = 'table-row';
                    detailRow.setAttribute('aria-hidden', 'false');
                    this.setAttribute('aria-expanded', 'true');
                    this.classList.add('is-open');
                    detailRow.querySelectorAll('img.lazy-detail-img[data-src]').forEach(function (img) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    });
                }
            });
        });

        // 3. Route Plan
        const btn = document.getElementById('btn-route-plan');
        const modalEl = document.getElementById('routePlanModal');

        if (btn && modalEl && typeof bootstrap !== 'undefined') {
            const modal = new bootstrap.Modal(modalEl);
            const { escapeHtml, setVisible, setText } = window.ERPUtils;

            async function loadRoutePlan() {
                setVisible('route-plan-error', false);
                setVisible('route-plan-result', false);
                setVisible('route-plan-loading', true);

                const dateStr = config.selectedDate;
                const managerFilterStr = config.managerFilter;

                setText('route-plan-meta', `기준일: ${dateStr} / 담당자: ${managerFilterStr || '-'} / 방식: 근사(직선거리)`);

                try {
                    const qs = new URLSearchParams({ date: dateStr, manager: managerFilterStr, limit: '20', use_kakao: '1', kakao_max_legs: '12' });
                    const res = await fetch(`/api/erp/measurement/route?${qs.toString()}`);
                    const data = await res.json();
                    if (!data.success) throw new Error(data.message || '동선 계산 실패');

                    const list = document.getElementById('route-plan-list');
                    list.innerHTML = '';

                    (data.route || []).forEach((p, idx) => {
                        const li = document.createElement('li');
                        const time = p.measurement_time ? `(${p.measurement_time}) ` : '';
                        li.innerHTML = `${time}<a href="/edit/${p.id}">주문 #${p.id}</a> - ${escapeHtml(String(p.customer_name || '-'))} / ${escapeHtml(String(p.address || '-'))}`;
                        list.appendChild(li);
                    });

                    const dur = data.total_duration_min ? ` / 총 시간: ${data.total_duration_min}분` : '';
                    setText('route-plan-distance', `총 거리: ${data.total_distance_km || 0} km${dur} / 지점: ${data.total_points || 0}`);
                    setText('route-plan-note', data.note || '');

                    setVisible('route-plan-loading', false);
                    setVisible('route-plan-result', true);
                } catch (e) {
                    setVisible('route-plan-loading', false);
                    setText('route-plan-error', String(e?.message || e));
                    setVisible('route-plan-error', true);
                }
            }

            btn.addEventListener('click', function () {
                modal.show();
                loadRoutePlan();
            });
        }

        // 담당자 목록 설정: 서버에서 로드 → 드롭다운에 사용
        let _measurementManagerList = [];
        fetch('/api/erp/shipment-settings')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.success && data.settings && Array.isArray(data.settings.measurement_manager)) {
                    _measurementManagerList = data.settings.measurement_manager;
                }
            })
            .catch(function (err) { console.warn('실측 담당자 목록 로드 실패:', err); });

        function showManagerDropdown(anchorEl, onSelect) {
            const existing = document.getElementById('measurement-manager-dropdown');
            if (existing) existing.remove();

            if (!_measurementManagerList.length) return;

            const rect = anchorEl.getBoundingClientRect();
            const div = document.createElement('div');
            div.id = 'measurement-manager-dropdown';
            div.className = 'dropdown-menu show';
            div.style.cssText = 'position:fixed;z-index:9999;max-height:240px;overflow-y:auto;min-width:120px;';
            div.style.left = rect.left + 'px';

            const spaceBelow = window.innerHeight - rect.bottom;
            if (spaceBelow < 250) {
                div.style.bottom = (window.innerHeight - rect.top + 2) + 'px';
            } else {
                div.style.top = (rect.bottom + 2) + 'px';
            }

            const ac = new AbortController();
            function cleanup() {
                ac.abort();
                if (div.parentNode) div.remove();
            }

            _measurementManagerList.forEach(function (name) {
                const a = document.createElement('a');
                a.className = 'dropdown-item';
                a.href = '#';
                a.textContent = name;
                a.addEventListener('click', function (e) {
                    e.preventDefault();
                    cleanup();
                    onSelect(name);
                });
                div.appendChild(a);
            });

            document.body.appendChild(div);

            setTimeout(function () {
                document.addEventListener('click', function (e) {
                    if (!div.contains(e.target) && !anchorEl.contains(e.target)) {
                        cleanup();
                    }
                }, { capture: true, signal: ac.signal });
            }, 100);
        }

        // 4. Inline Edit (위임: 수동 행은 로컬만 저장)
        async function commitCellValue(cell, tr, field, orderId, isErpBeta, isManual, currentValue, originalContent, newValue) {
            if (newValue === (currentValue === '-' ? '' : currentValue)) {
                cell.innerHTML = originalContent;
                return;
            }
            if (isManual) {
                cell.textContent = newValue || '-';
                window.measurementManualRowsPersist();
                if (field === 'manager') {
                    tr.dataset.manager = newValue || '';
                    scheduleApplyMeasurementManagerSortAndColors();
                }
                return;
            }
            cell.textContent = '저장 중...';
            const controller = new AbortController();
            const timeoutId = setTimeout(function () { controller.abort(); }, 45000);
            try {
                let res;
                if (field === 'manager' && !isErpBeta) {
                    res = await fetch('/api/update_order_field', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        signal: controller.signal,
                        body: JSON.stringify({ order_id: parseInt(orderId, 10), field: 'manager_name', value: newValue })
                    });
                } else {
                    res = await fetch('/api/erp/measurement/update/' + orderId, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        signal: controller.signal,
                        body: JSON.stringify({ field: field, value: newValue })
                    });
                }
                const ct = res.headers.get('Content-Type') || '';
                const data = ct.includes('application/json') ? await res.json() : { success: false, error: res.status === 404 ? 'API 경로를 확인해 주세요.' : '저장 실패' };
                if (data.success) {
                    cell.textContent = newValue || '-';
                    if (field === 'manager') {
                        tr.dataset.manager = newValue || '';
                        scheduleApplyMeasurementManagerSortAndColors();
                    }
                } else {
                    cell.textContent = currentValue || '-';
                    if (data.message || data.error) console.warn('저장 실패:', data.message || data.error);
                }
            } catch (err) {
                cell.innerHTML = originalContent;
                if (err && err.name === 'AbortError') {
                    alert('저장 요청 시간이 초과되었습니다. 네트워크 또는 서버 상태를 확인해 주세요.');
                } else {
                    console.warn('저장 중 오류:', err);
                }
            } finally {
                clearTimeout(timeoutId);
            }
        }

        tbody.addEventListener('click', function (e) {
            const cell = e.target.closest('td.editable-cell');
            if (!cell || !tbody.contains(cell)) return;
            if (e.target.closest('input, button, a')) return;
            const tr = cell.closest('tr');
            if (!tr || !tr.classList.contains('measurement-row')) return;
            if (cell.querySelector('input')) return;

            const orderId = tr.dataset.orderId;
            const isErpBeta = tr.dataset.isErp === 'true';
            const isManual = tr.dataset.manualRow === 'true';
            const field = cell.dataset.field;
            const currentValue = cell.textContent.trim();

            if (!isManual && !isErpBeta && field !== 'manager') return;

            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentValue === '-' ? '' : currentValue;
            input.className = 'form-control form-control-sm';

            const originalContent = cell.innerHTML;
            cell.innerHTML = '';
            let _committed = false;
            let _blurTimerId = null;

            function doCommit(val) {
                if (_committed) return;
                _committed = true;
                if (_blurTimerId) { clearTimeout(_blurTimerId); _blurTimerId = null; }
                const dropdown = document.getElementById('measurement-manager-dropdown');
                if (dropdown) dropdown.remove();
                commitCellValue(cell, tr, field, orderId, isErpBeta, isManual, currentValue, originalContent, val);
            }

            if (field === 'manager') {
                const wrap = document.createElement('div');
                wrap.style.cssText = 'display:flex;gap:4px;align-items:center;width:100%;';
                input.style.flex = '1';
                input.style.minWidth = '0';
                wrap.appendChild(input);

                const loadBtn = document.createElement('button');
                loadBtn.type = 'button';
                loadBtn.className = 'btn btn-sm btn-outline-secondary';
                loadBtn.style.cssText = 'flex-shrink:0;padding:2px 6px;';
                loadBtn.title = '저장된 담당자 불러오기';
                loadBtn.innerHTML = '<i class="fas fa-list"></i>';
                loadBtn.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (_blurTimerId) { clearTimeout(_blurTimerId); _blurTimerId = null; }
                    showManagerDropdown(loadBtn, function (name) {
                        input.value = name;
                        doCommit(name);
                    });
                });
                wrap.appendChild(loadBtn);
                cell.appendChild(wrap);
            } else {
                cell.appendChild(input);
            }
            input.focus();

            input.addEventListener('blur', function () {
                _blurTimerId = setTimeout(function () {
                    _blurTimerId = null;
                    if (_committed) return;
                    doCommit(input.value.trim());
                }, 150);
            });
        });
    });
})();
