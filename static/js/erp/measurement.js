(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const container = document.querySelector('.erp-pro');
        if (!container) return;

        window.measurementManualRowsPersist = window.measurementManualRowsPersist || function () {};
        window.measurementManualRowsRecomputeAnchors = window.measurementManualRowsRecomputeAnchors || function () {};

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

        const MANAGER_COLORS = [
            '#FF0000', '#0080FF', '#FFFF00', '#00FF00', '#FF00FF',
            '#00FFFF', '#FF8000', '#FF1493', '#00FF80', '#FF69B4'
        ];

        // ── 공통 헬퍼 ──

        function getManagerFromRow(tr) {
            const cell = tr.querySelector('td.manager-cell');
            return (cell && (cell.textContent || '').trim()) || '';
        }

        function normalizeManagerKey(name) {
            return (name && name !== '-') ? name.toLowerCase() : '';
        }

        function managerKeyForSort(tr) {
            return normalizeManagerKey(getManagerFromRow(tr)) || 'ZZZ';
        }

        function rowTieBreak(tr) {
            if (tr.classList.contains('measurement-row-manual')) {
                return 100000000 + (parseInt(tr.dataset.manualSeq, 10) || 0);
            }
            return parseInt(tr.dataset.orderId, 10) || 0;
        }

        // ── 담당자 정렬·색상 (책임 분리) ──

        function restoreServerColors(rows) {
            rows.forEach(function (tr) {
                if (tr.classList.contains('measurement-row-manual')) return;
                const cell = tr.querySelector('td.manager-cell');
                if (!cell) return;
                if (cell.dataset.bg) cell.style.setProperty('background-color', cell.dataset.bg, 'important');
                if (cell.dataset.color) cell.style.setProperty('color', cell.dataset.color, 'important');
            });
        }

        function buildSortedPairs(rows) {
            const pairs = rows.map(function (tr) {
                const orderId = tr.dataset.orderId || '';
                const next = tr.nextElementSibling;
                const isManual = tr.classList.contains('measurement-row-manual');
                const detailRow =
                    !isManual && next && next.classList &&
                    next.classList.contains('measurement-detail-row') &&
                    (next.dataset.orderId === orderId || next.id === 'detail-' + orderId)
                        ? next : null;
                return { main: tr, detail: detailRow };
            });
            pairs.sort(function (a, b) {
                const mA = managerKeyForSort(a.main);
                const mB = managerKeyForSort(b.main);
                if (mA !== mB) return mA.localeCompare(mB);
                return rowTieBreak(a.main) - rowTieBreak(b.main);
            });
            return pairs;
        }

        function buildManagerIndex(rows) {
            const list = [];
            rows.forEach(function (tr) {
                const key = normalizeManagerKey(getManagerFromRow(tr));
                if (key && list.indexOf(key) === -1) list.push(key);
            });
            return list;
        }

        function applyManagerColors(rows, managerIndex) {
            rows.forEach(function (tr) {
                const cell = tr.querySelector('td.manager-cell');
                if (!cell) return;
                const m = getManagerFromRow(tr);
                const key = normalizeManagerKey(m);
                const idx = key ? managerIndex.indexOf(key) : -1;
                const color = idx >= 0 ? MANAGER_COLORS[idx % MANAGER_COLORS.length] : '#CCCCCC';
                cell.setAttribute('data-manager-bg-color', color);
                cell.style.setProperty('--manager-bg-color', color);
                cell.style.setProperty('background-color', color, 'important');
                cell.style.setProperty('color', '#000000', 'important');
                tr.dataset.manager = m || '';
            });
        }

        function applyMeasurementManagerSortAndColors() {
            const mainRows = Array.from(tbody.querySelectorAll('tr.measurement-row'));
            if (!mainRows.length) return;

            restoreServerColors(mainRows);

            const pairs = buildSortedPairs(mainRows);
            pairs.forEach(function (p) {
                tbody.appendChild(p.main);
                if (p.detail) tbody.appendChild(p.detail);
            });

            applyManagerColors(mainRows, buildManagerIndex(mainRows));
            window.measurementManualRowsRecomputeAnchors();
            window.measurementManualRowsPersist();
        }

        function scheduleApplyMeasurementManagerSortAndColors() {
            setTimeout(applyMeasurementManagerSortAndColors, 0);
        }

        window.applyMeasurementManagerSortAndColors = applyMeasurementManagerSortAndColors;
        window.scheduleApplyMeasurementManagerSortAndColors = scheduleApplyMeasurementManagerSortAndColors;

        // ── 1. Scroll to today ──

        const todayEl = document.getElementById('date-' + config.todayDate);
        if (todayEl) todayEl.scrollIntoView({ block: 'center' });

        // ── 2. 초기 색상 적용 ──

        applyMeasurementManagerSortAndColors();

        // ── 3. 주문 상세 chevron 토글 ──

        document.querySelectorAll('.measurement-chevron').forEach(function (chevron) {
            chevron.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                const orderId = this.dataset.orderId;
                const detailRow = orderId ? document.getElementById('detail-' + orderId) : null;
                if (!detailRow) return;
                const isOpen = this.getAttribute('aria-expanded') === 'true';
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

        // ── 4. Route Plan ──

        const routeBtn = document.getElementById('btn-route-plan');
        const routeModalEl = document.getElementById('routePlanModal');

        if (routeBtn && routeModalEl && typeof bootstrap !== 'undefined') {
            const routeModal = new bootstrap.Modal(routeModalEl);
            const { escapeHtml, setVisible, setText } = window.ERPUtils;

            async function loadRoutePlan() {
                setVisible('route-plan-error', false);
                setVisible('route-plan-result', false);
                setVisible('route-plan-loading', true);
                setText('route-plan-meta', '\uAE30\uC900\uC77C: ' + config.selectedDate + ' / \uB2F4\uB2F9\uC790: ' + (config.managerFilter || '-') + ' / \uBC29\uC2DD: \uADFC\uC0AC(\uC9C1\uC120\uAC70\uB9AC)');

                try {
                    const qs = new URLSearchParams({ date: config.selectedDate, manager: config.managerFilter, limit: '20', use_kakao: '1', kakao_max_legs: '12' });
                    const res = await fetch('/api/erp/measurement/route?' + qs.toString());
                    const data = await res.json();
                    if (!data.success) throw new Error(data.message || '\uB3D9\uC120 \uACC4\uC0B0 \uC2E4\uD328');

                    const list = document.getElementById('route-plan-list');
                    list.innerHTML = '';
                    (data.route || []).forEach(function (p) {
                        const li = document.createElement('li');
                        const time = p.measurement_time ? '(' + p.measurement_time + ') ' : '';
                        li.innerHTML = time + '<a href="/edit/' + p.id + '">\uC8FC\uBB38 #' + p.id + '</a> - ' + escapeHtml(String(p.customer_name || '-')) + ' / ' + escapeHtml(String(p.address || '-'));
                        list.appendChild(li);
                    });

                    const dur = data.total_duration_min ? ' / \uCD1D \uC2DC\uAC04: ' + data.total_duration_min + '\uBD84' : '';
                    setText('route-plan-distance', '\uCD1D \uAC70\uB9AC: ' + (data.total_distance_km || 0) + ' km' + dur + ' / \uC9C0\uC810: ' + (data.total_points || 0));
                    setText('route-plan-note', data.note || '');
                    setVisible('route-plan-loading', false);
                    setVisible('route-plan-result', true);
                } catch (e) {
                    setVisible('route-plan-loading', false);
                    setText('route-plan-error', String(e && e.message ? e.message : e));
                    setVisible('route-plan-error', true);
                }
            }

            routeBtn.addEventListener('click', function () {
                routeModal.show();
                loadRoutePlan();
            });
        }

        // ── 5. 담당자 목록 로드 ──

        let _measurementManagerList = [];
        let _managerListLoaded = false;

        fetch('/api/erp/shipment-settings')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.success && data.settings && Array.isArray(data.settings.measurement_manager)) {
                    _measurementManagerList = data.settings.measurement_manager;
                }
                _managerListLoaded = true;
            })
            .catch(function (err) {
                console.warn('\uC2E4\uCE21 \uB2F4\uB2F9\uC790 \uBAA9\uB85D \uB85C\uB4DC \uC2E4\uD328:', err);
                _managerListLoaded = true;
            });

        // ── 6. 담당자 드롭다운 ──

        function positionDropdown(div, anchorEl) {
            const rect = anchorEl.getBoundingClientRect();
            div.style.left = rect.left + 'px';
            if (window.innerHeight - rect.bottom < 250) {
                div.style.bottom = (window.innerHeight - rect.top + 2) + 'px';
            } else {
                div.style.top = (rect.bottom + 2) + 'px';
            }
        }

        function showManagerDropdown(anchorEl, editingContainer, onSelect, onDismiss) {
            const existing = document.getElementById('measurement-manager-dropdown');
            if (existing) existing.remove();

            if (!_measurementManagerList.length) {
                if (_managerListLoaded) {
                    alert('\uC800\uC7A5\uB41C \uB2F4\uB2F9\uC790 \uBAA9\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uCD9C\uACE0 \uC124\uC815\uC5D0\uC11C \uCD94\uAC00\uD574 \uC8FC\uC138\uC694.');
                }
                return;
            }

            const div = document.createElement('div');
            div.id = 'measurement-manager-dropdown';
            div.className = 'dropdown-menu show';
            div.style.cssText = 'position:fixed;z-index:9999;max-height:240px;overflow-y:auto;min-width:120px;';
            positionDropdown(div, anchorEl);

            const ac = new AbortController();
            function removeDropdown() {
                ac.abort();
                if (div.parentNode) div.remove();
            }

            _measurementManagerList.forEach(function (name) {
                const a = document.createElement('a');
                a.className = 'dropdown-item';
                a.href = '#';
                a.style.cssText = 'padding:8px 16px;font-size:0.95rem;';
                a.textContent = name;
                a.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    removeDropdown();
                    onSelect(name);
                });
                div.appendChild(a);
            });

            document.body.appendChild(div);

            setTimeout(function () {
                document.addEventListener('click', function (e) {
                    if (div.contains(e.target) || anchorEl.contains(e.target)) return;
                    removeDropdown();
                    if (editingContainer && !editingContainer.contains(e.target)) {
                        if (onDismiss) onDismiss();
                    }
                }, { capture: true, signal: ac.signal });
            }, 150);
        }

        // ── 7. 셀 저장 API ──

        function buildSavePayload(field, orderId, isErpBeta, newValue) {
            if (field === 'manager' && !isErpBeta) {
                return {
                    url: '/api/update_order_field',
                    body: { order_id: parseInt(orderId, 10), field: 'manager_name', value: newValue }
                };
            }
            return {
                url: '/api/erp/measurement/update/' + orderId,
                body: { field: field, value: newValue }
            };
        }

        function handleSaveResult(cell, tr, field, currentValue, newValue, data) {
            if (data.success) {
                cell.textContent = newValue || '-';
                if (field === 'manager') {
                    tr.dataset.manager = newValue || '';
                    scheduleApplyMeasurementManagerSortAndColors();
                }
            } else {
                cell.textContent = currentValue || '-';
                if (data.message || data.error) console.warn('\uC800\uC7A5 \uC2E4\uD328:', data.message || data.error);
            }
        }

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

            cell.textContent = '\uC800\uC7A5 \uC911...';
            const controller = new AbortController();
            const timeoutId = setTimeout(function () { controller.abort(); }, 45000);
            try {
                const payload = buildSavePayload(field, orderId, isErpBeta, newValue);
                const res = await fetch(payload.url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    signal: controller.signal,
                    body: JSON.stringify(payload.body)
                });
                const ct = res.headers.get('Content-Type') || '';
                const data = ct.includes('application/json')
                    ? await res.json()
                    : { success: false, error: res.status === 404 ? 'API \uACBD\uB85C\uB97C \uD655\uC778\uD574 \uC8FC\uC138\uC694.' : '\uC800\uC7A5 \uC2E4\uD328' };
                handleSaveResult(cell, tr, field, currentValue, newValue, data);
            } catch (err) {
                cell.innerHTML = originalContent;
                if (err && err.name === 'AbortError') {
                    alert('\uC800\uC7A5 \uC694\uCCAD \uC2DC\uAC04\uC774 \uCD08\uACFC\uB418\uC5C8\uC2B5\uB2C8\uB2E4. \uB124\uD2B8\uC6CC\uD06C \uB610\uB294 \uC11C\uBC84 \uC0C1\uD0DC\uB97C \uD655\uC778\uD574 \uC8FC\uC138\uC694.');
                } else {
                    console.warn('\uC800\uC7A5 \uC911 \uC624\uB958:', err);
                }
            } finally {
                clearTimeout(timeoutId);
            }
        }

        // ── 8. 인라인 편집: 담당자 필드 ──

        function startManagerEdit(cell, input, doCommit, blurState) {
            const wrap = document.createElement('div');
            wrap.style.cssText = 'display:flex;gap:4px;align-items:center;width:100%;';
            input.style.flex = '1';
            input.style.minWidth = '0';
            wrap.appendChild(input);

            const loadBtn = document.createElement('button');
            loadBtn.type = 'button';
            loadBtn.className = 'btn btn-sm btn-outline-secondary';
            loadBtn.style.cssText = 'flex-shrink:0;padding:6px 10px;font-size:1rem;';
            loadBtn.title = '\uC800\uC7A5\uB41C \uB2F4\uB2F9\uC790 \uBD88\uB7EC\uC624\uAE30';
            loadBtn.innerHTML = '<i class="fas fa-list"></i>';

            function openDropdown(e) {
                e.preventDefault();
                e.stopPropagation();
                if (blurState.timerId) { clearTimeout(blurState.timerId); blurState.timerId = null; }
                blurState.dropdownOpen = true;
                showManagerDropdown(loadBtn, wrap, function (name) {
                    blurState.dropdownOpen = false;
                    input.value = name;
                    doCommit(name);
                }, function () {
                    blurState.dropdownOpen = false;
                    if (!blurState.committed) doCommit(input.value.trim());
                });
            }
            loadBtn.addEventListener('mousedown', openDropdown);
            loadBtn.addEventListener('touchstart', openDropdown, { passive: false });

            wrap.appendChild(loadBtn);
            cell.appendChild(wrap);
        }

        // ── 9. 인라인 편집: tbody 위임 핸들러 ──

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
            const blurState = { committed: false, timerId: null, dropdownOpen: false };

            function doCommit(val) {
                if (blurState.committed) return;
                blurState.committed = true;
                if (blurState.timerId) { clearTimeout(blurState.timerId); blurState.timerId = null; }
                const dropdown = document.getElementById('measurement-manager-dropdown');
                if (dropdown) dropdown.remove();
                commitCellValue(cell, tr, field, orderId, isErpBeta, isManual, currentValue, originalContent, val);
            }

            if (field === 'manager') {
                startManagerEdit(cell, input, doCommit, blurState);
            } else {
                cell.appendChild(input);
            }
            input.focus();

            input.addEventListener('blur', function () {
                blurState.timerId = setTimeout(function () {
                    blurState.timerId = null;
                    if (blurState.committed || blurState.dropdownOpen) return;
                    doCommit(input.value.trim());
                }, 200);
            });
        });
    });
})();
