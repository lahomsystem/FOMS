document.addEventListener('DOMContentLoaded', function () {
    const fabBtn = document.getElementById('btn-quick-status-fab');
    if (!fabBtn) return; // 로그인 안 된 경우 등

    const modalEl = document.getElementById('quickStatusModal');
    const modal = new bootstrap.Modal(modalEl);

    const searchBtn = document.getElementById('btn-quick-search');
    const orderIdInput = document.getElementById('quick-order-id');
    const saveBtn = document.getElementById('btn-quick-save');
    const newStatusSelect = document.getElementById('quick-new-status');
    const noteInput = document.getElementById('quick-status-note');

    // UI Elements
    const infoArea = document.getElementById('quick-order-info');
    const formArea = document.getElementById('quick-change-form');
    const customerName = document.getElementById('quick-customer-name');
    const currentStatus = document.getElementById('quick-current-status');
    const orderDetails = document.getElementById('quick-order-details');
    const orderIdBadge = document.getElementById('quick-order-id-badge');

    // FAB Click: Open Modal
    fabBtn.addEventListener('click', function () {
        modal.show();
    });

    // Modal Shown: Focus Input
    modalEl.addEventListener('shown.bs.modal', function () {
        orderIdInput.value = '';
        orderIdInput.focus();
        resetModal();
    });

    // Search Logic
    function performSearch() {
        const id = orderIdInput.value.trim();
        if (!id) return;

        // UI Reset
        resetModal();
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        // erp_beta.py의 라우트가 /api/orders/... 로 정의되어 있음 (url_prefix 없음 가정)
        fetch(`/api/orders/${id}/quick-info`)
            .then(res => {
                if (!res.ok) {
                    // 404 처리
                    if (res.status === 404) throw new Error('주문을 찾을 수 없습니다.');
                    throw new Error('조회 중 오류가 발생했습니다.');
                }
                return res.json();
            })
            .then(data => {
                if (data.success) {
                    showOrderInfo(data.order);
                } else {
                    alert(data.message || '조회 실패');
                    orderIdInput.focus();
                }
            })
            .catch(err => {
                console.error(err);
                alert(err.message);
                orderIdInput.select();
                orderIdInput.focus();
            })
            .finally(() => {
                searchBtn.disabled = false;
                searchBtn.innerHTML = '<i class="fas fa-search"></i> 조회';
            });
    }

    searchBtn.addEventListener('click', performSearch);
    orderIdInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') performSearch(); // 조회 트리거
    });

    function showOrderInfo(order) {
        infoArea.classList.remove('d-none');
        formArea.classList.remove('d-none');
        saveBtn.disabled = false;

        customerName.textContent = order.customer_name;

        // 상태 표시 (영문 코드 -> 한글 매핑은 서버에서 안 오면 그냥 코드 표시하거나, 
        // select option에서 텍스트 찾아서 표시)
        let statusText = order.status;
        // select option에서 text 찾기
        const option = newStatusSelect.querySelector(`option[value="${order.status}"]`);
        if (option) statusText = option.text;

        currentStatus.textContent = statusText;

        orderIdBadge.textContent = `#${order.id}`;
        orderDetails.innerHTML = `
            <div><i class="fas fa-box me-1"></i> ${order.product || '-'}</div>
            <div><i class="fas fa-map-marker-alt me-1"></i> ${order.address || '-'}</div>
            <div><i class="fas fa-user-tie me-1"></i> ${order.manager || '-'}</div>
        `;

        // Select box: 현재 상태 선택
        newStatusSelect.value = order.status;
        noteInput.value = '';

        // Focus on status select
        setTimeout(() => newStatusSelect.focus(), 100);
    }

    function resetModal() {
        infoArea.classList.add('d-none');
        formArea.classList.add('d-none');
        saveBtn.disabled = true;
        customerName.textContent = '';
        currentStatus.textContent = '';
        orderDetails.innerHTML = '';
        orderIdBadge.textContent = '#';
        newStatusSelect.value = '';
        noteInput.value = '';
    }

    // Save Logic
    saveBtn.addEventListener('click', function () {
        const id = orderIdInput.value.trim();
        const status = newStatusSelect.value;
        const note = noteInput.value.trim();

        if (!id || !status) {
            alert('상태를 선택해주세요.');
            return;
        }

        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';

        fetch(`/api/orders/${id}/quick-status`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                status: status,
                note: note
            })
        })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // 성공
                    // 토스트 메시지나 알림
                    const prevHtml = saveBtn.innerHTML;
                    saveBtn.innerHTML = '<i class="fas fa-check"></i> 완료!';
                    saveBtn.classList.remove('btn-primary');
                    saveBtn.classList.add('btn-success');

                    setTimeout(() => {
                        modal.hide();
                        window.location.reload();
                    }, 800);
                } else {
                    alert(data.message || '변경 실패');
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = '<i class="fas fa-check"></i> 변경 저장';
                }
            })
            .catch(err => {
                console.error(err);
                alert('오류 발생: ' + err.message);
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fas fa-check"></i> 변경 저장';
            });
    });
});
