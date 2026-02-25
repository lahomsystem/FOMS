
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const container = document.querySelector('.erp-pro');
        if (!container) return;

        // Config from data attributes
        const erpActiveRaw = container.dataset.erpBetaActive ?? container.dataset.erpActive;
        const config = {
            erpBetaActive: erpActiveRaw === 'true',
            todayDate: container.dataset.todayDate,
            selectedDate: container.dataset.selectedDate,
            managerFilter: container.dataset.managerFilter || ''
        };

        if (!config.erpBetaActive) return;

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
        function applyMeasurementManagerSortAndColors() {
            const tbody = document.querySelector('.measurement-table tbody');
            if (!tbody) return;
            const mainRows = Array.from(tbody.querySelectorAll('tr.measurement-row'));
            if (!mainRows.length) return;
            // 주문 행과 그 다음 상세 행(measurement-detail-row)을 쌍으로 유지해 정렬 (상세가 아래로 가도록)
            const pairs = mainRows.map(function (tr) {
                const orderId = tr.dataset.orderId || '';
                const next = tr.nextElementSibling;
                const detailRow = (next && next.classList && next.classList.contains('measurement-detail-row') && (next.dataset.orderId === orderId || next.id === 'detail-' + orderId)) ? next : null;
                return { main: tr, detail: detailRow };
            });
            pairs.sort(function (a, b) {
                const mA = managerKeyForSort(a.main);
                const mB = managerKeyForSort(b.main);
                if (mA !== mB) return mA.localeCompare(mB);
                return (parseInt(a.main.dataset.orderId, 10) || 0) - (parseInt(b.main.dataset.orderId, 10) || 0);
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
        }
        function scheduleApplyMeasurementManagerSortAndColors() {
            setTimeout(applyMeasurementManagerSortAndColors, 0);
        }

        // 1. Scroll to today
        const todayId = "date-" + config.todayDate;
        const todayEl = document.getElementById(todayId);
        const panelList = document.querySelector('.measurement-panel-list');
        if (todayEl && panelList) {
            todayEl.scrollIntoView({ block: 'center' });
        }

        // 2. Manager Cell Colors (초기 적용 후, 담당자 편집 시 scheduleApplyMeasurementManagerSortAndColors로 실시간 재정렬·재색상)
        applyMeasurementManagerSortAndColors();

        // 2b. 주문 상세 chevron 토글 (v 꺽쇠 클릭 시 해당 행 아래 상세 슬라이드)
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

        // 4. Inline Edit (담당자: ERP Beta + 비-ERP 모두, 주소/전화: ERP Beta만)
        const editableCells = document.querySelectorAll('.editable-cell');
        editableCells.forEach(cell => {
            cell.addEventListener('click', async function () {
                const tr = this.closest('tr');
                const orderId = tr.dataset.orderId;
                const isErpBeta = tr.dataset.isErp === 'true';
                const field = this.dataset.field;
                const currentValue = this.textContent.trim();

                if (!isErpBeta && field !== 'manager') return;
                if (this.querySelector('input')) return;

                const input = document.createElement('input');
                input.type = 'text';
                input.value = currentValue === '-' ? '' : currentValue;
                input.className = 'form-control form-control-sm';

                const originalContent = this.innerHTML;
                this.innerHTML = '';
                this.appendChild(input);
                input.focus();

                input.addEventListener('blur', async () => {
                    const newValue = input.value.trim();
                    if (newValue === (currentValue === '-' ? '' : currentValue)) {
                        this.innerHTML = originalContent;
                        return;
                    }
                    this.textContent = '저장 중...';
                    try {
                        let res;
                        if (field === 'manager' && !isErpBeta) {
                            res = await fetch('/api/update_order_field', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                credentials: 'same-origin',
                                body: JSON.stringify({ order_id: parseInt(orderId, 10), field: 'manager_name', value: newValue })
                            });
                        } else {
                            res = await fetch(`/api/erp/measurement/update/${orderId}`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                credentials: 'same-origin',
                                body: JSON.stringify({ field, value: newValue })
                            });
                        }
                        const contentType = res.headers.get('Content-Type') || '';
                        const data = contentType.includes('application/json') ? await res.json() : { success: false, error: res.status === 404 ? 'API 경로를 확인해 주세요.' : '저장 실패' };
                        if (data.success) {
                            this.textContent = newValue || '-';
                            if (field === 'manager') {
                                const tr = this.closest('tr');
                                if (tr) tr.dataset.manager = newValue || '';
                                scheduleApplyMeasurementManagerSortAndColors();
                            }
                        } else {
                            this.textContent = currentValue || '-';
                            if (data.message || data.error) console.warn('담당자 저장 실패:', data.message || data.error);
                        }
                    } catch (e) {
                        this.innerHTML = originalContent;
                        console.warn('담당자 저장 중 오류:', e);
                    }
                });
            });
        });

    });
})();
