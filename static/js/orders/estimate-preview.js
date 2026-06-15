/**
 * estimate-preview.js
 * 견적서(계약서) 프리뷰 탭 — ERP Order 서브탭용
 */
(function () {
    'use strict';

    let _estimateCacheLoaded = false;
    let _dirty = true; // 첫 진입 시 항상 새로 로드

    function _getOrderId() {
        if (typeof ORDER_ID !== 'undefined') return ORDER_ID;
        if (typeof window.ORDER_ID !== 'undefined') return window.ORDER_ID;
        const el = document.querySelector('[data-erp-order-id]');
        return el ? parseInt(el.dataset.erpOrderId, 10) || 0 : 0;
    }

    function _isErpEnabled() {
        if (typeof ERP_ORDER_ENABLED !== 'undefined') return !!ERP_ORDER_ENABLED;
        if (typeof window.ERP_ORDER_ENABLED !== 'undefined') return !!window.ERP_ORDER_ENABLED;
        const el = document.getElementById('erp-order-config') || document.querySelector('[data-erp-order-enabled]');
        if (el) return String(el.getAttribute('data-erp-order-enabled') || '') === 'true';
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
            tdSpec.className = 'erp-est-td-spec';
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

    function _applyCompanyInfo(ci, isLahom) {
        _setText('est-company-name', ci.name);
        _setText('est-company-ceo', ci.ceo);
        _setText('est-company-biznum', ci.business_number);
        _setText('est-company-address', ci.address);
        _setText('est-company-industry', ci.industry);
        _setText('est-company-phone', ci.phone);
        _setText('est-company-center', ci.customer_center);

        // 발주사별 로고: CSS 클래스로 크기 제어 (인라인 스타일 금지 원칙)
        const logoEl = document.getElementById('est-logo-img');
        if (logoEl) {
            const lahomSrc = logoEl.dataset.lahomSrc;
            const haudSrc = logoEl.dataset.haudSrc;
            if (isLahom) {
                logoEl.src = lahomSrc;
                logoEl.classList.remove('erp-est-logo--haud');
                logoEl.classList.add('erp-est-logo--lahom');
            } else {
                logoEl.src = haudSrc || lahomSrc;
                logoEl.classList.remove('erp-est-logo--lahom');
                logoEl.classList.add('erp-est-logo--haud');
            }
        }

        // 인감 도장 표시
        const stampEl = document.getElementById('est-stamp-img');
        if (stampEl) stampEl.classList.remove('erp-est-hidden');
    }

    function _applyCustomerInfo(d) {
        _setText('est-customer-name', d.customer_name);
        _setText('est-customer-phone', d.customer_phone);
        _setText('est-site-address', d.site_address);
        const today = _todayStr();
        _setText('est-estimate-date', _fmtDate(today));
        _setText('est-construction-date', _fmtDate(d.construction_date));
        _setText('est-manager-name', d.manager_name);
        _setText('est-manager-phone', d.manager_phone);

        const phoneDigits = (d.customer_phone || '').replace(/\D/g, '');
        _setText('est-estimate-number', today.replace(/-/g, '') + '_' + (phoneDigits || '미리보기'));
        _setText('est-created-date', today);
    }

    /** @param {HTMLElement} accountsWrap */
    function _renderPaymentAccounts(accountsWrap, pi) {
        var list = [];
        if (pi && Array.isArray(pi.accounts) && pi.accounts.length > 0) {
            list = pi.accounts;
        } else if (pi && pi.bank) {
            list = [{ bank: pi.bank, account: pi.account, holder: pi.holder }];
        }
        accountsWrap.innerHTML = '';
        list.forEach(function (acc) {
            if (!acc) return;
            var block = document.createElement('div');
            block.className = 'erp-est-pay-account-block';
            var line = document.createElement('div');
            line.className = 'erp-est-bank-line';
            var bSpan = document.createElement('span');
            bSpan.className = 'fw-bold';
            bSpan.textContent = acc.bank || '';
            var sep = document.createElement('span');
            sep.className = 'erp-est-sep';
            sep.textContent = '|';
            var accSpan = document.createElement('span');
            var acct = acc.account;
            accSpan.textContent = Array.isArray(acct) ? (acct[0] || '') : (acct || '');
            line.appendChild(bSpan);
            line.appendChild(sep);
            line.appendChild(accSpan);
            var holder = document.createElement('div');
            holder.className = 'erp-est-pay-holder';
            holder.textContent = '예금주 : ' + (acc.holder || '');
            block.appendChild(line);
            block.appendChild(holder);
            accountsWrap.appendChild(block);
        });
    }

    function _applyPaymentInfo(d, pi) {
        _setText('est-total-amount', _fmtMoney(d.total_amount));

        // 예약금이 있을 때만 행 노출, 없으면 숨김
        const depositRow = document.getElementById('est-deposit-row');
        if (d.deposit_amount && d.deposit_amount > 0) {
            _setText('est-deposit-amount', _fmtMoney(d.deposit_amount));
            if (depositRow) depositRow.classList.remove('erp-est-hidden');
        } else {
            if (depositRow) depositRow.classList.add('erp-est-hidden');
        }

        _setText('est-balance-amount', _fmtMoney(d.balance_amount));

        var accountsWrap = document.getElementById('est-pay-accounts');
        if (accountsWrap) {
            _renderPaymentAccounts(accountsWrap, pi);
        }

        _setText('est-pay-notice', pi && pi.notice);
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
                const emptyMsg = document.getElementById('est-empty-msg');
                if (emptyMsg) emptyMsg.textContent = data.error || '견적서 데이터를 불러올 수 없습니다.';
                return;
            }

            const d = data.data || {};
            _applyCompanyInfo(d.company_info || {}, !!d.is_lahom);
            _applyCustomerInfo(d);
            _renderItems(d.items);
            _applyPaymentInfo(d, d.payment_info || {});

            _showSection('est-document');
            _estimateCacheLoaded = true;
            _dirty = false;

            // 저장 버튼 활성화 및 툴바 노출
            const toolbar = document.getElementById('est-toolbar');
            const exportBtn = document.getElementById('btn-est-export');
            if (toolbar) toolbar.classList.remove('erp-est-hidden');
            if (exportBtn) exportBtn.disabled = false;

        } catch (err) {
            _hideSection('est-loading');
            _showSection('est-empty');
            console.error('[estimate-preview] fetch error:', err);
        }
    }

    window.erpInvalidateEstimateCache = function () {
        _estimateCacheLoaded = false;
        _dirty = true;
    };

    // ── 이미지 저장 (실측 대시보드와 동일 방식) ──────────────────────
    function _bindExportBtn() {
        const btn = document.getElementById('btn-est-export');
        if (!btn) return;

        btn.addEventListener('click', async function () {
            const docEl = document.getElementById('est-document');
            if (!docEl || docEl.classList.contains('erp-est-hidden')) {
                alert('견적서가 로드되지 않았습니다.');
                return;
            }

            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            btn.disabled = true;

            var itemsTable = document.getElementById('erp-estimate-items-table');
            if (typeof window.setEstimateTableExportMode === 'function') {
                window.setEstimateTableExportMode(true);
            } else if (itemsTable) {
                itemsTable.classList.add('erp-est-exporting');
            }

            try {
                const numEl = document.getElementById('est-estimate-number');
                const numText = (numEl && numEl.textContent.trim()) || '견적서';
                const filename = numText + '.png';

                const canvas = await html2canvas(docEl, {
                    scale: 2,
                    useCORS: true,
                    logging: false,
                    backgroundColor: '#ffffff'
                });

                const link = document.createElement('a');
                link.download = filename;
                link.href = canvas.toDataURL('image/png');
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

            } catch (err) {
                console.error('[estimate-preview] 이미지 저장 실패:', err);
                alert('이미지 저장 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : String(err)));
            } finally {
                if (typeof window.setEstimateTableExportMode === 'function') {
                    window.setEstimateTableExportMode(false);
                } else if (itemsTable) {
                    itemsTable.classList.remove('erp-est-exporting');
                }
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        });
    }

    function _init() {
        const tab = document.getElementById('erp-estimate-tab');
        if (!tab) return;

        _bindExportBtn();

        // ERP Order 폼 입력 시 dirty 플래그 설정 (캡처 페이즈로 모든 [data-erp] 입력 감지)
        document.addEventListener('input', function (e) {
            if (e.target && e.target.dataset && 'erp' in e.target.dataset) {
                _dirty = true;
            }
        }, true);

        // 계약서 탭 활성화 시: 변경 없고 캐시 유효하면 즉시 반환 (불필요한 네트워크 요청 차단)
        tab.addEventListener('shown.bs.tab', async function () {
            if (!_dirty && _estimateCacheLoaded) return;

            _estimateCacheLoaded = false;
            const orderId = _getOrderId();

            // 변경된 경우에만 자동 저장 (실시간 반영) — 자동 저장이므로 필수값 검증 생략
            // 단, 고객명이 비어있으면 저장을 스킵 (빈 주문 서버 저장 방지)
            if (_dirty && orderId && orderId > 0 && typeof window.erpSaveStructured === 'function') {
                if (typeof window.erpIsDraftBackedOrder === 'function' && window.erpIsDraftBackedOrder()) {
                    erpLoadEstimatePreview();
                    return;
                }
                const custName = (document.getElementById('erp-customer-name')?.value || '').trim();
                if (!custName) {
                    erpLoadEstimatePreview();
                    return;
                }
                try {
                    await window.erpSaveStructured({ redirect: false, _skipValidation: true });
                } catch (_e) {
                    // 저장 실패 시 기존 서버 데이터로 폴백
                }
            }
            erpLoadEstimatePreview();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _init);
    } else {
        _init();
    }

})();
