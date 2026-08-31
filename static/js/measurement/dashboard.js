(function () {
    function initMeasurementDashboard() {
        const container = document.querySelector('.erp-pro');
        if (!container) return;

        window.measurementManualRowsPersist = window.measurementManualRowsPersist || function () {};
        window.measurementManualRowsRecomputeAnchors = window.measurementManualRowsRecomputeAnchors || function () {};

        const erpActiveRaw = container.dataset.erpOrderActive || container.dataset.erpActive;
        const config = {
            erpOrderActive: erpActiveRaw === 'true',
            todayDate: container.dataset.todayDate,
            selectedDate: container.dataset.selectedDate,
            managerFilter: container.dataset.managerFilter || ''
        };

        if (!config.erpOrderActive) return;

        const tbody = document.querySelector('.measurement-table tbody');
        if (!tbody) return;

        const MANAGER_FALLBACK_COLORS = [
            '#FADADD', '#DCEBFF', '#FFF1BF', '#DDF4E4', '#E8DDF8',
            '#D9F3F0', '#FFE6CC', '#F9D9EC', '#E5F5D2', '#FDE2E4'
        ];
        const DEFAULT_MANAGER_BG_COLOR = '#CCCCCC';
        const DEFAULT_MANAGER_TEXT_COLOR = '#000000';

        let _measurementManagerList = [];
        let _managerSortOrderMap = {};
        let _managerListLoaded = false;
        let _activeManagerDropdown = null;

        // ── 공통 헬퍼 ──

        function getManagerCell(tr) {
            return tr.querySelector('td.manager-cell');
        }

        function shouldUseServerManagerColor(cell) {
            if (!cell || !cell.dataset.bg) return false;
            if (cell.dataset.bgSource === 'fallback') return false;
            return true;
        }

        function getManagerFromRow(tr) {
            const cell = getManagerCell(tr);
            return (cell && (cell.textContent || '').trim()) || '';
        }

        function normalizeManagerKey(name) {
            return (name && name !== '-') ? name.toLowerCase() : '';
        }

        function managerSortOrder(tr) {
            var name = getManagerFromRow(tr);
            var key = normalizeManagerKey(name);
            if (!key) return 999;
            return _managerSortOrderMap[key] != null ? _managerSortOrderMap[key] : 999;
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
                const cell = getManagerCell(tr);
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
                var sA = managerSortOrder(a.main);
                var sB = managerSortOrder(b.main);
                if (sA !== sB) return sA - sB;
                var nA = normalizeManagerKey(getManagerFromRow(a.main)) || 'zzz';
                var nB = normalizeManagerKey(getManagerFromRow(b.main)) || 'zzz';
                if (nA !== nB) return nA.localeCompare(nB);
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

        function buildManagerColorMap(rows, managerIndex) {
            const colorMap = {};

            rows.forEach(function (tr) {
                const cell = getManagerCell(tr);
                if (!cell) return;
                const key = normalizeManagerKey(getManagerFromRow(tr));
                if (!key || colorMap[key] || !shouldUseServerManagerColor(cell)) return;

                colorMap[key] = {
                    background: cell.dataset.bg,
                    text: cell.dataset.color || DEFAULT_MANAGER_TEXT_COLOR
                };
            });

            managerIndex.forEach(function (key, index) {
                if (colorMap[key]) return;
                colorMap[key] = {
                    background: MANAGER_FALLBACK_COLORS[index % MANAGER_FALLBACK_COLORS.length],
                    text: DEFAULT_MANAGER_TEXT_COLOR
                };
            });

            return colorMap;
        }

        function applyManagerColors(rows, managerColors) {
            rows.forEach(function (tr) {
                const cell = getManagerCell(tr);
                if (!cell) return;
                const managerName = getManagerFromRow(tr);
                const key = normalizeManagerKey(managerName);
                const colorSet = key ? managerColors[key] : null;
                const background = colorSet ? colorSet.background : DEFAULT_MANAGER_BG_COLOR;
                const textColor = colorSet ? colorSet.text : DEFAULT_MANAGER_TEXT_COLOR;

                cell.setAttribute('data-manager-bg-color', background);
                cell.style.setProperty('--manager-bg-color', background);
                cell.style.setProperty('background-color', background, 'important');
                cell.style.setProperty('color', textColor, 'important');
                tr.dataset.manager = managerName || '';
            });
        }

        function focusEditedMeasurementRow(tr) {
            if (!tr || !tr.isConnected) return;
            window.requestAnimationFrame(function () {
                if (!tr.isConnected) return;
                tr.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            });
        }

        function applyMeasurementManagerSortAndColors(options) {
            const mainRows = Array.from(tbody.querySelectorAll('tr.measurement-row'));
            if (!mainRows.length) return;

            restoreServerColors(mainRows);

            const pairs = buildSortedPairs(mainRows);
            pairs.forEach(function (p) {
                tbody.appendChild(p.main);
                if (p.detail) tbody.appendChild(p.detail);
            });

            const managerIndex = buildManagerIndex(mainRows);
            const managerColors = buildManagerColorMap(mainRows, managerIndex);
            applyManagerColors(mainRows, managerColors);
            window.measurementManualRowsRecomputeAnchors();
            window.measurementManualRowsPersist();

            if (options && options.focusRow) {
                focusEditedMeasurementRow(options.focusRow);
            }
        }

        function scheduleApplyMeasurementManagerSortAndColors(options) {
            setTimeout(function () {
                applyMeasurementManagerSortAndColors(options);
            }, 0);
        }

        window.applyMeasurementManagerSortAndColors = applyMeasurementManagerSortAndColors;
        window.scheduleApplyMeasurementManagerSortAndColors = scheduleApplyMeasurementManagerSortAndColors;

        // ── 1. Scroll to today ──

        const todayEl =
            document.querySelector('[data-measurement-date-chip="' + config.todayDate + '"]') ||
            document.getElementById('date-' + config.todayDate);
        if (todayEl) todayEl.scrollIntoView({ block: 'center' });

        // ── 2. 초기 색상 적용 ──

        applyMeasurementManagerSortAndColors();

        // ── 2.5 저장 복귀 딥링크: ?focus_order=<주문id> 행으로 정렬 ──
        // 편집 저장 후 실측 대시보드 복귀가 today 자동 스크롤로 작업 위치를 잃던
        // 문제의 근본 수정(주문 대시보드 focus_order 와 동일 UX). today 스크롤·정렬
        // 뒤에 실행해 우선하며, 행이 없으면(필터 밖) 아무것도 하지 않는다.
        (function () {
            var focusOrder = new URLSearchParams(window.location.search).get('focus_order');
            if (!focusOrder || !/^\d+$/.test(focusOrder)) return;
            var tr = document.querySelector('tr.measurement-row[data-order-id="' + focusOrder + '"]')
                || document.querySelector('tr[data-order-id="' + focusOrder + '"]');
            if (!tr) return;
            setTimeout(function () {
                if (!tr.isConnected) return;
                tr.scrollIntoView({ block: 'center' });
                tr.classList.add('table-info');
                setTimeout(function () { tr.classList.remove('table-info'); }, 2500);
            }, 300);
        })();

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

        const routeTriggers = Array.from(
            document.querySelectorAll('#btn-route-plan, [data-route-plan-trigger="measurement"]')
        ).filter(function (element, index, list) {
            return list.indexOf(element) === index;
        });
        const routeModalEl = document.getElementById('routePlanModal');

        if (routeTriggers.length && routeModalEl && typeof bootstrap !== 'undefined') {
            const routeModal = new bootstrap.Modal(routeModalEl);
            const ERPUtils = window.ERPUtils || {
                escapeHtml: function(t) { return t; },
                setVisible: function() {},
                setText: function() {}
            };
            const { escapeHtml, setVisible, setText } = ERPUtils;

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

                    // ROUTE-01: \uACBD\uB85C \uACC4\uD68D \uBAA8\uB2EC\uC740 \uCD5C\uADFC\uC811 \uC774\uC6C3(NN) \uCD5C\uC801 \uB3D9\uC120 \uC804\uC6A9 \uD544\uB4DC\uB97C \uC4F4\uB2E4
                    // (data.route \uB294 \uC608\uC57D \uC21C\uC11C SSOT \u2014 hero/'\uB2E4\uC74C \uBC29\uBB38' \uD310\uC815\uC6A9\uC774\uB77C \uC5EC\uAE30 \uC4F0\uC9C0 \uC54A\uB294\uB2E4).
                    const list = document.getElementById('route-plan-list');
                    list.innerHTML = '';
                    (data.optimized_route || []).forEach(function (p) {
                        const li = document.createElement('li');
                        const time = p.measurement_time ? '(' + p.measurement_time + ') ' : '';
                        li.innerHTML = time + '<a href="/edit/' + p.id + '">\uC8FC\uBB38 #' + p.id + '</a> - ' + escapeHtml(String(p.customer_name || '-')) + ' / ' + escapeHtml(String(p.address || '-'));
                        list.appendChild(li);
                    });

                    const dur = data.total_duration_min ? ' / \uCD1D \uC2DC\uAC04: ' + data.total_duration_min + '\uBD84' : '';
                    setText('route-plan-distance', '\uCD1D \uAC70\uB9AC: ' + (data.optimized_total_distance_km || 0) + ' km' + dur + ' / \uC9C0\uC810: ' + (data.total_points || 0));
                    setText('route-plan-note', data.note || '');
                    setVisible('route-plan-loading', false);
                    setVisible('route-plan-result', true);
                } catch (e) {
                    setVisible('route-plan-loading', false);
                    setText('route-plan-error', String(e && e.message ? e.message : e));
                    setVisible('route-plan-error', true);
                }
            }

            routeTriggers.forEach(function (trigger) {
                trigger.addEventListener('click', function () {
                    routeModal.show();
                    loadRoutePlan();
                });
            });
        }

        // ── 4-1. 실측일 미정 ──
        // 실측일(정규화된 YYYY-MM-DD)이 하나도 없는 미완료 주문을 모달로 보여준다.
        // '추후통보'·'미정' 같은 텍스트 건도 서버에서 정규화 실패 → 여기 포함된다.

        const undatedTriggers = Array.from(
            document.querySelectorAll('#btn-undated-measurement, [data-undated-trigger="measurement"]')
        ).filter(function (element, index, list) {
            return list.indexOf(element) === index;
        });
        const undatedModalEl = document.getElementById('undatedMeasurementModal');

        if (undatedTriggers.length && undatedModalEl && typeof bootstrap !== 'undefined') {
            const undatedModal = new bootstrap.Modal(undatedModalEl);

            // ERPUtils.setVisible 은 style.display 를 직접 건드리므로(인라인 스타일 금지)
            // 이 블록은 부트스트랩 d-none 클래스만 토글한다.
            function undatedShow(id, visible) {
                const el = document.getElementById(id);
                if (el) el.classList.toggle('d-none', !visible);
            }

            function undatedText(id, text) {
                const el = document.getElementById(id);
                if (el) el.textContent = text;
            }

            function undatedCell(tr, value) {
                const td = document.createElement('td');
                td.textContent = String(value == null || value === '' ? '-' : value);
                tr.appendChild(td);
                return td;
            }

            function undatedBadge(td, label, className) {
                const span = document.createElement('span');
                span.className = 'badge ' + className + ' ms-1';
                span.textContent = label;
                td.appendChild(span);
            }

            /** 응답 payload 를 표로 렌더한다. 값은 전부 textContent (저장형 XSS 차단). */
            function renderUndated(payload) {
                const rows = Array.isArray(payload.rows) ? payload.rows : [];
                // 절단된 경우 뱃지는 실제 전체 건수를 말한다(표시 건수만 보이면 축소가 조용해진다).
                const badgeTotal = payload.total != null ? payload.total : (payload.count || 0);
                undatedText('undated-count-badge', String(badgeTotal) + '건');

                let truncMsg = '';
                if (payload.truncated) {
                    truncMsg = '전체 ' + payload.total + '건 중 ' + payload.display_cap
                        + '건만 표시됩니다. 검색어나 담당자로 범위를 줄여 주세요.';
                }
                if (payload.scan_capped) {
                    truncMsg += ' (조회 대상이 많아 일부만 검사했습니다.)';
                }
                undatedText('undated-truncated', truncMsg.trim());
                undatedShow('undated-truncated', !!truncMsg);

                const tbody = document.getElementById('undated-tbody');
                if (tbody) tbody.textContent = '';

                if (!rows.length) {
                    undatedShow('undated-result', false);
                    undatedShow('undated-empty', true);
                    return;
                }
                undatedShow('undated-empty', false);

                rows.forEach(function (row) {
                    const tr = document.createElement('tr');

                    const idTd = document.createElement('td');
                    idTd.textContent = '#' + row.id;
                    tr.appendChild(idTd);

                    undatedCell(tr, row.customer_name);
                    undatedCell(tr, row.phone);
                    undatedCell(tr, row.address);
                    undatedCell(tr, row.manager_name);

                    const statusTd = undatedCell(tr, row.status_label);
                    if (row.is_regional) undatedBadge(statusTd, '지방', 'bg-success text-white');
                    if (row.is_self_measurement) undatedBadge(statusTd, '자가실측', 'bg-info text-white');

                    undatedCell(tr, row.received_date);
                    undatedCell(tr, row.product);

                    const editTd = document.createElement('td');
                    if (row.edit_url) {
                        // edit_url 은 서버가 url_for 로 만든 값 — 클라이언트에서 조립하지 않는다.
                        const link = document.createElement('a');
                        link.href = row.edit_url;
                        link.target = '_blank';
                        link.rel = 'noopener';
                        link.className = 'btn btn-sm btn-outline-primary';
                        link.title = '주문 수정 (새 탭)';
                        const icon = document.createElement('i');
                        icon.className = 'fas fa-edit';
                        link.appendChild(icon);
                        editTd.appendChild(link);
                    } else {
                        editTd.textContent = '-';
                    }
                    tr.appendChild(editTd);

                    if (tbody) tbody.appendChild(tr);
                });

                undatedShow('undated-result', true);
            }

            /** 현재 조회 조건(검색어·담당자·mine)으로 실측일 미정 목록을 불러온다. */
            async function loadUndated() {
                undatedShow('undated-error', false);
                undatedShow('undated-result', false);
                undatedShow('undated-empty', false);
                undatedShow('undated-truncated', false);
                undatedShow('undated-loading', true);
                undatedText('undated-count-badge', '…');

                const trigger = undatedTriggers[0];
                const params = new URLSearchParams();
                const q = (trigger && trigger.dataset.undatedQ) || '';
                if (q) params.set('q', q);
                if (config.managerFilter) params.set('manager_filter', config.managerFilter);
                // mine 은 URL 에 명시된 경우에만 전달 — 없으면 서버가 쿠키 기준으로 화면과 동일하게 판정한다.
                const mineParam = new URLSearchParams(window.location.search).get('mine');
                if (mineParam !== null) params.set('mine', mineParam);

                undatedText('undated-meta', '조회 조건: 검색어 ' + (q || '-') + ' / 담당자 ' + (config.managerFilter || '-'));

                try {
                    const res = await fetch('/api/erp/measurement/undated?' + params.toString());
                    if (!res.ok) {
                        // 세션 만료 시 로그인 HTML 이 와서 JSON 파서 메시지가 그대로 노출되던 문제.
                        throw new Error(res.status === 401 || res.status === 403
                            ? '로그인이 만료되었습니다. 새로고침 후 다시 시도해 주세요.'
                            : '실측일 미정 목록을 불러오지 못했습니다. (HTTP ' + res.status + ')');
                    }
                    let data;
                    try {
                        data = await res.json();
                    } catch (parseError) {
                        console.error('[undated] 응답 파싱 실패', parseError);
                        throw new Error('실측일 미정 목록 응답을 읽지 못했습니다. 새로고침 후 다시 시도해 주세요.');
                    }
                    if (!data.success) throw new Error(data.error || '실측일 미정 목록을 불러오지 못했습니다.');
                    undatedShow('undated-loading', false);
                    renderUndated(data.data || {});
                } catch (e) {
                    undatedShow('undated-loading', false);
                    undatedText('undated-count-badge', '-');
                    undatedText('undated-error', String(e && e.message ? e.message : e));
                    undatedShow('undated-error', true);
                }
            }

            undatedTriggers.forEach(function (trigger) {
                trigger.addEventListener('click', function () {
                    undatedModal.show();
                    loadUndated();
                });
            });
        }

        // ── 5. 담당자 목록 로드 ──

        fetch('/api/erp/shipment-settings')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.success && data.settings && Array.isArray(data.settings.measurement_manager)) {
                    var rawList = data.settings.measurement_manager;
                    _measurementManagerList = [];
                    _managerSortOrderMap = {};
                    rawList.forEach(function (item) {
                        var name = typeof item === 'string' ? item : (item.name || '');
                        var sortOrder = typeof item === 'object' && item.sort_order != null ? item.sort_order : 999;
                        if (name) {
                            _measurementManagerList.push(name);
                            _managerSortOrderMap[name.toLowerCase()] = sortOrder;
                        }
                    });
                    scheduleApplyMeasurementManagerSortAndColors();
                }
                _managerListLoaded = true;
            })
            .catch(function (err) {
                console.warn('\uC2E4\uCE21 \uB2F4\uB2F9\uC790 \uBAA9\uB85D \uB85C\uB4DC \uC2E4\uD328:', err);
                _managerListLoaded = true;
            });

        // ── 6. 담당자 드롭다운 ──

        function positionDropdown(div, anchorEl, editingContainer) {
            const viewportPadding = 8;
            const anchorRect = anchorEl.getBoundingClientRect();
            const containerRect = (editingContainer || anchorEl).getBoundingClientRect();
            const viewportWidth = Math.max(window.innerWidth || 0, 320);
            const viewportHeight = Math.max(window.innerHeight || 0, 320);
            const preferredWidth = Math.max(Math.round(containerRect.width), 180);
            const maxWidth = Math.max(180, viewportWidth - (viewportPadding * 2));

            div.style.top = '';
            div.style.bottom = '';
            div.style.width = Math.min(preferredWidth, maxWidth) + 'px';
            div.style.maxWidth = maxWidth + 'px';

            const dropdownRect = div.getBoundingClientRect();
            const clampedLeft = Math.max(
                viewportPadding,
                Math.min(containerRect.left, viewportWidth - dropdownRect.width - viewportPadding)
            );
            div.style.left = Math.round(clampedLeft) + 'px';

            const dropdownHeight = Math.min(dropdownRect.height || 0, 240);
            const spaceBelow = viewportHeight - anchorRect.bottom - viewportPadding;
            const openUpward = spaceBelow < dropdownHeight && anchorRect.top > dropdownHeight;

            if (openUpward) {
                div.style.bottom = Math.round(viewportHeight - anchorRect.top + 2) + 'px';
            } else {
                div.style.top = Math.round(anchorRect.bottom + 2) + 'px';
            }
        }

        function closeManagerDropdown(options) {
            const state = _activeManagerDropdown;
            if (!state) return;

            _activeManagerDropdown = null;
            if (state.abortController) {
                state.abortController.abort();
            }
            if (state.element && state.element.parentNode) {
                state.element.remove();
            }
            if (options && options.invokeDismiss && typeof state.onDismiss === 'function') {
                state.onDismiss();
            }
        }

        function showManagerDropdown(anchorEl, editingContainer, onSelect, onDismiss) {
            closeManagerDropdown();

            if (!_measurementManagerList.length) {
                if (_managerListLoaded) {
                    alert('\uC800\uC7A5\uB41C \uB2F4\uB2F9\uC790 \uBAA9\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uCD9C\uACE0 \uC124\uC815\uC5D0\uC11C \uCD94\uAC00\uD574 \uC8FC\uC138\uC694.');
                }
                return;
            }

            const div = document.createElement('div');
            div.id = 'measurement-manager-dropdown';
            div.className = 'dropdown-menu show';
            div.style.cssText = 'position:fixed;z-index:9999;max-height:240px;overflow-y:auto;overflow-x:hidden;';

            const ac = new AbortController();
            _activeManagerDropdown = {
                element: div,
                abortController: ac,
                onDismiss: onDismiss
            };

            _measurementManagerList.forEach(function (item) {
                var name = typeof item === 'string' ? item : (item && item.name ? item.name : String(item));
                const a = document.createElement('a');
                a.className = 'dropdown-item';
                a.href = '#';
                a.style.cssText = 'padding:8px 16px;font-size:0.95rem;';
                a.textContent = name;
                a.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    closeManagerDropdown();
                    onSelect(name);
                });
                div.appendChild(a);
            });

            document.body.appendChild(div);
            positionDropdown(div, anchorEl, editingContainer);

            window.requestAnimationFrame(function () {
                const repositionDropdown = function () {
                    if (!_activeManagerDropdown || _activeManagerDropdown.element !== div) return;
                    positionDropdown(div, anchorEl, editingContainer);
                };

                window.addEventListener('resize', repositionDropdown, { signal: ac.signal });
                window.addEventListener('scroll', repositionDropdown, { capture: true, passive: true, signal: ac.signal });
                document.addEventListener('pointerdown', function (e) {
                    if (div.contains(e.target) || anchorEl.contains(e.target)) return;
                    const shouldDismiss = editingContainer && !editingContainer.contains(e.target);
                    closeManagerDropdown();
                    if (shouldDismiss && onDismiss) {
                        onDismiss();
                    }
                }, { capture: true, signal: ac.signal });
            });
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
        window.MeasurementDashboardApi = window.MeasurementDashboardApi || {};
        window.MeasurementDashboardApi.buildSavePayload = buildSavePayload;

        function syncManagerDisplay(tr, newValue) {
            tr.dataset.manager = newValue || '';
        }

        function handleSaveResult(cell, tr, field, currentValue, newValue, data) {
            if (data.success) {
                cell.textContent = newValue || '-';
                if (field === 'manager') {
                    syncManagerDisplay(tr, newValue);
                    scheduleApplyMeasurementManagerSortAndColors({ focusRow: tr });
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
                    syncManagerDisplay(tr, newValue);
                    scheduleApplyMeasurementManagerSortAndColors({ focusRow: tr });
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
            wrap.className = 'measurement-manager-editor';
            wrap.appendChild(input);

            function bindEditorActionButton(button, handler) {
                let handledByPointer = false;

                button.addEventListener('pointerdown', function (evt) {
                    handledByPointer = true;
                    handler(evt);
                });
                button.addEventListener('click', function (evt) {
                    if (handledByPointer) {
                        handledByPointer = false;
                        return;
                    }
                    handler(evt);
                });
            }

            const clearBtn = document.createElement('button');
            clearBtn.type = 'button';
            clearBtn.className = 'measurement-manager-editor__icon-btn';
            clearBtn.title = '\uB2F4\uB2F9\uC790 \uC9C0\uC6B0\uAE30';
            clearBtn.setAttribute('data-manager-action', 'clear');
            clearBtn.innerHTML = '<i class="fas fa-times"></i>';

            function syncClearButtonState() {
                clearBtn.disabled = !input.value.trim();
            }

            function commitExplicitValue(nextValue) {
                if (blurState.timerId) {
                    clearTimeout(blurState.timerId);
                    blurState.timerId = null;
                }
                blurState.dropdownOpen = false;
                input.value = nextValue;
                doCommit(nextValue);
            }

            function clearCurrentManager(e) {
                e.preventDefault();
                e.stopPropagation();
                commitExplicitValue('');
            }

            bindEditorActionButton(clearBtn, clearCurrentManager);
            wrap.appendChild(clearBtn);

            const loadBtn = document.createElement('button');
            loadBtn.type = 'button';
            loadBtn.className = 'measurement-manager-editor__icon-btn';
            loadBtn.title = '\uC800\uC7A5\uB41C \uB2F4\uB2F9\uC790 \uBD88\uB7EC\uC624\uAE30';
            loadBtn.innerHTML = '<i class="fas fa-list"></i>';

            function openDropdown(e) {
                e.preventDefault();
                e.stopPropagation();
                if (blurState.timerId) { clearTimeout(blurState.timerId); blurState.timerId = null; }
                blurState.dropdownOpen = true;
                showManagerDropdown(loadBtn, wrap, function (name) {
                    blurState.dropdownOpen = false;
                    commitExplicitValue(name);
                }, function () {
                    blurState.dropdownOpen = false;
                    if (!blurState.committed) doCommit(input.value.trim());
                });
            }
            bindEditorActionButton(loadBtn, openDropdown);

            wrap.appendChild(loadBtn);
            cell.appendChild(wrap);
            syncClearButtonState();
            input.addEventListener('input', syncClearButtonState);
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
            input.className = 'measurement-manager-editor__input';

            const originalContent = cell.innerHTML;
            cell.innerHTML = '';
            const blurState = { committed: false, timerId: null, dropdownOpen: false };

            function cancelEdit() {
                if (blurState.committed) return;
                blurState.committed = true;
                if (blurState.timerId) {
                    clearTimeout(blurState.timerId);
                    blurState.timerId = null;
                }
                blurState.dropdownOpen = false;
                closeManagerDropdown();
                cell.innerHTML = originalContent;
            }

            function doCommit(val) {
                if (blurState.committed) return;
                blurState.committed = true;
                if (blurState.timerId) { clearTimeout(blurState.timerId); blurState.timerId = null; }
                blurState.dropdownOpen = false;
                closeManagerDropdown();
                commitCellValue(cell, tr, field, orderId, isErpBeta, isManual, currentValue, originalContent, val);
            }

            if (field === 'manager') {
                startManagerEdit(cell, input, doCommit, blurState);
            } else {
                cell.appendChild(input);
            }
            input.focus();
            input.select();

            input.addEventListener('keydown', function (evt) {
                if (evt.key === 'Enter') {
                    evt.preventDefault();
                    doCommit(input.value.trim());
                    return;
                }
                if (evt.key === 'Escape') {
                    evt.preventDefault();
                    cancelEdit();
                }
            });

            input.addEventListener('blur', function () {
                blurState.timerId = setTimeout(function () {
                    blurState.timerId = null;
                    if (blurState.committed || blurState.dropdownOpen) return;
                    doCommit(input.value.trim());
                }, 200);
            });
        });
    }

    // 최초 로드: entry 경유 동적 로드라 이미 DOM ready 인 경우가 많음 → readyState 분기.
    // fragment 스왑: #main-content HTML 교체 후 새 테이블 DOM 에 재초기화. 모든 리스너는
    // per-DOM(tbody/chevron/route) 또는 dropdown AbortController 로 자기정리라 재실행이 안전.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMeasurementDashboard);
    } else {
        initMeasurementDashboard();
    }
    if (!window.__FOMS_MEAS_DASHBOARD_BOUND) {
        window.__FOMS_MEAS_DASHBOARD_BOUND = true;
        document.addEventListener('foms:erp-shell-fragment-swapped', initMeasurementDashboard);
    }
})();
