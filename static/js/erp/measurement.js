
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

        // 1. Scroll to today
        const todayId = "date-" + config.todayDate;
        const todayEl = document.getElementById(todayId);
        const panelList = document.querySelector('.measurement-panel-list');
        if (todayEl && panelList) {
            todayEl.scrollIntoView({ block: 'center' });
        }

        // 2. Manager Cell Colors
        const colorList = ['#FF0000', '#0080FF', '#FFFF00', '#00FF00', '#FF00FF', '#00FFFF', '#FF8000', '#FF1493', '#00FF80', '#FF69B4'];
        const managerCells = document.querySelectorAll('td.manager-cell');
        const managerColorMap = {};
        let colorIndex = 0;

        managerCells.forEach(cell => {
            const managerName = (cell.textContent || '').trim();
            if (managerName && managerName !== '-' && !managerColorMap[managerName]) {
                managerColorMap[managerName] = colorList[colorIndex % colorList.length];
                colorIndex++;
            }
        });

        managerCells.forEach(cell => {
            const managerName = (cell.textContent || '').trim();
            if (managerName && managerName !== '-') {
                const bgColor = managerColorMap[managerName] || '#CCCCCC';
                cell.setAttribute('data-manager-bg-color', bgColor);
                cell.style.setProperty('--manager-bg-color', bgColor);
                cell.style.setProperty('background-color', bgColor, 'important');
                cell.style.setProperty('background', bgColor, 'important');
                cell.style.setProperty('color', '#000000', 'important');
            }
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

        // 4. Inline Edit
        const editableCells = document.querySelectorAll('.editable-cell');
        editableCells.forEach(cell => {
            cell.addEventListener('click', async function () {
                const tr = this.closest('tr');
                const orderId = tr.dataset.orderId;
                const isErpBeta = tr.dataset.isErpBeta === 'true';
                const field = this.dataset.field;
                const currentValue = this.textContent.trim();

                if (!isErpBeta) return;
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
                        const res = await fetch(`/api/erp/measurement/update/${orderId}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ field, value: newValue })
                        });
                        const data = await res.json();
                        this.textContent = data.success ? (newValue || '-') : (currentValue || '-');
                    } catch (e) {
                        this.innerHTML = originalContent;
                    }
                });
            });
        });

    });
})();
