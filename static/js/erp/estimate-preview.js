/**
 * estimate-preview.js
 * 견적서(계약서) 프리뷰 탭 — ERP Beta 서브탭용
 */
(function () {
    'use strict';

    let _estimateCacheLoaded = false;

    function _getOrderId() {
        if (typeof ORDER_ID !== 'undefined') return ORDER_ID;
        if (typeof window.ORDER_ID !== 'undefined') return window.ORDER_ID;
        const el = document.querySelector('[data-erp-order-id]');
        return el ? parseInt(el.dataset.erpOrderId, 10) || 0 : 0;
    }

    function _isErpEnabled() {
        if (typeof ERP_BETA_ENABLED !== 'undefined') return !!ERP_BETA_ENABLED;
        if (typeof window.ERP_BETA_ENABLED !== 'undefined') return !!window.ERP_BETA_ENABLED;
        return false;
    }

    function _fmtMoney(num) {
        const n = Number(num);
        if (!Number.isFinite(n) || n === 0) return '₩0';
        return '₩' + Math.round(n).toLocaleString('ko-KR');
    }

    function _fmtDate(dateStr) {
        if (!dateStr) return '-';
        const parts = String(dateStr).split('-');
        if (parts.length === 3) {
            return parts[0] + '년 ' + parseInt(parts[1], 10) + '월 ' + parseInt(parts[2], 10) + '일';
        }
        return dateStr;
    }

    function _todayStr() {
        const d = new Date();
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + dd;
    }

    function _setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text || '-';
    }

    function _showSection(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('erp-est-hidden');
    }

    function _hideSection(id) {
        const el = document.getElementById(id);
        if (el) el.classList.add('erp-est-hidden');
    }

    function _renderItems(items) {
        const tbody = document.getElementById('est-items-tbody');
        const emptyRow = document.getElementById('est-items-empty');
        if (!tbody) return;

        if (!items || items.length === 0) {
            if (emptyRow) emptyRow.classList.remove('erp-est-hidden');
            return;
        }
        if (emptyRow) emptyRow.classList.add('erp-est-hidden');

        tbody.querySelectorAll('tr:not(#est-items-empty)').forEach(function (r) { r.remove(); });

        items.forEach(function (item) {
            const tr = document.createElement('tr');

            const tdName = document.createElement('td');
            tdName.textContent = item.product_name || '-';
            tr.appendChild(tdName);

            const tdSpec = document.createElement('td');
            tdSpec.textContent = item.spec || '-';
            tr.appendChild(tdSpec);

            const tdColor = document.createElement('td');
            tdColor.textContent = item.color || '-';
            tr.appendChild(tdColor);

            const tdQty = document.createElement('td');
            tdQty.textContent = item.quantity || 1;
            tr.appendChild(tdQty);

            const tdAmount = document.createElement('td');
            tdAmount.textContent = _fmtMoney(item.amount || item.unit_price || 0);
            tdAmount.className = 'text-end';
            tr.appendChild(tdAmount);

            tbody.appendChild(tr);
        });
    }

    function _applyCompanyInfo(ci) {
        _setText('est-company-name', ci.name);
        _setText('est-company-ceo', ci.ceo);
        _setText('est-company-biznum', ci.business_number);
        _setText('est-company-address', ci.address);
        _setText('est-company-industry', ci.industry);
        _setText('est-company-phone', ci.phone);
        _setText('est-company-center', ci.customer_center);
    }

    function _applyCustomerInfo(d) {
        _setText('est-customer-name', d.customer_name);
        _setText('est-customer-phone', d.customer_phone);
        _setText('est-site-address', d.site_address);
        _setText('est-estimate-date', _fmtDate(_todayStr()));
        _setText('est-construction-date', _fmtDate(d.construction_date));
        _setText('est-manager-name', d.manager_name);
        _setText('est-manager-phone', d.manager_phone);

        const today = _todayStr();
        _setText('est-estimate-number', today.replace(/-/g, '') + '_미리보기');
        _setText('est-created-date', today);
    }

    function _applyPaymentInfo(d, pi) {
        _setText('est-total-amount', _fmtMoney(d.total_amount));
        _setText('est-balance-amount', _fmtMoney(d.balance_amount));
        _setText('est-pay-bank', pi.bank);
        _setText('est-pay-account', pi.account);
        _setText('est-pay-holder', '예금주 : ' + (pi.holder || ''));
        _setText('est-pay-notice', pi.notice);
        _setText('est-legal-notice', d.legal_notice);
    }

    async function erpLoadEstimatePreview() {
        if (!_isErpEnabled()) return;
        const orderId = _getOrderId();
        if (!orderId || orderId === 0) {
            _hideSection('est-loading');
            _hideSection('est-document');
            _showSection('est-empty');
            return;
        }

        if (_estimateCacheLoaded) return;

        _hideSection('est-empty');
        _hideSection('est-document');
        _showSection('est-loading');

        try {
            const res = await fetch('/api/orders/' + orderId + '/estimate-preview');
            _hideSection('est-loading');

            if (!res.ok) {
                _showSection('est-empty');
                return;
            }

            const data = await res.json();

            if (!data.success) {
                _showSection('est-empty');
                const emptyEl = document.getElementById('est-empty');
                if (emptyEl) emptyEl.textContent = data.error || '견적서 데이터를 불러올 수 없습니다.';
                return;
            }

            const d = data.data || {};
            _applyCompanyInfo(d.company_info || {});
            _applyCustomerInfo(d);
            _renderItems(d.items);
            _applyPaymentInfo(d, d.payment_info || {});

            _showSection('est-document');
            _estimateCacheLoaded = true;

        } catch (err) {
            _hideSection('est-loading');
            _showSection('est-empty');
            console.error('[estimate-preview] fetch error:', err);
        }
    }

    window.erpInvalidateEstimateCache = function () {
        _estimateCacheLoaded = false;
    };

    function _init() {
        const tab = document.getElementById('erp-estimate-tab');
        if (!tab) return;

        tab.addEventListener('shown.bs.tab', function () {
            erpLoadEstimatePreview();
        });
        tab.addEventListener('click', function () {
            setTimeout(erpLoadEstimatePreview, 150);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _init);
    } else {
        _init();
    }

})();
