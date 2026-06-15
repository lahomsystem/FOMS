/**
 * estimate-preview.js
 * 견적서(계약서) 프리뷰 탭 — ERP Order 서브탭용
 */
(function () {
    'use strict';

    let _estimateCacheLoaded = false;
    let _dirty = true; // 첫 진입 시 항상 새로 로드
    var _EST_EXPORT_WIDTH = 700;
    var _EST_DOC_WIDTH = 700;
    var _MOBILE_ESTIMATE_MQ = '(max-width: 991.98px)';

    var _mobilePreviewBound = false;
    var _mobilePreviewDataUrl = '';
    var _mobilePreviewCapturePromise = null;

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

    function _isMobileEstimateView() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia(_MOBILE_ESTIMATE_MQ).matches;
    }

    function _applyEstimateViewMode() {
        if (_isMobileEstimateView()) {
            _hideSection('est-viewport');
        } else {
            _hideSection('est-mobile-preview');
            _showSection('est-viewport');
        }
    }

    /** PC 견적서(700px) 오프스크린 클론 — export/html2canvas용 */
    function _buildExportClone(sourceEl) {
        var clone = sourceEl.cloneNode(true);
        clone.removeAttribute('id');
        clone.querySelectorAll('[id]').forEach(function (node) {
            node.removeAttribute('id');
        });
        clone.classList.add('erp-est-export-clone');
        document.body.appendChild(clone);
        return clone;
    }

    function _removeExportClone(cloneEl) {
        if (cloneEl && cloneEl.parentNode) {
            cloneEl.parentNode.removeChild(cloneEl);
        }
    }

    function _withEstimateExportMode(run) {
        var itemsTable = document.getElementById('erp-estimate-items-table');
        if (typeof window.setEstimateTableExportMode === 'function') {
            window.setEstimateTableExportMode(true);
        } else if (itemsTable) {
            itemsTable.classList.add('erp-est-exporting');
        }

        return Promise.resolve()
            .then(run)
            .finally(function () {
                if (typeof window.setEstimateTableExportMode === 'function') {
                    window.setEstimateTableExportMode(false);
                } else if (itemsTable) {
                    itemsTable.classList.remove('erp-est-exporting');
                }
            });
    }

    function _captureEstimateDataUrl() {
        var docEl = document.getElementById('est-document');
        if (!docEl) return Promise.resolve('');

        return _withEstimateExportMode(function () {
            var exportEl = _buildExportClone(docEl);
            return html2canvas(exportEl, {
                scale: 2,
                useCORS: true,
                logging: false,
                backgroundColor: '#ffffff',
                width: _EST_EXPORT_WIDTH,
                windowWidth: _EST_EXPORT_WIDTH
            }).then(function (canvas) {
                return canvas.toDataURL('image/png');
            }).finally(function () {
                _removeExportClone(exportEl);
            });
        }).catch(function (err) {
            console.error('[estimate-preview] capture error:', err);
            return '';
        });
    }

    function _refreshMobilePreview() {
        if (!_isMobileEstimateView()) return Promise.resolve();

        var card = document.getElementById('est-mobile-preview');
        var img = document.getElementById('est-mobile-preview-img');
        if (!card || !img) return Promise.resolve();

        _hideSection('est-mobile-preview');
        _mobilePreviewDataUrl = '';

        if (_mobilePreviewCapturePromise) return _mobilePreviewCapturePromise;

        _mobilePreviewCapturePromise = _captureEstimateDataUrl().then(function (dataUrl) {
            _mobilePreviewCapturePromise = null;
            if (!dataUrl) return;
            _mobilePreviewDataUrl = dataUrl;
            img.src = dataUrl;
            img.alt = '견적서 미리보기';
            _showSection('est-mobile-preview');
        });

        return _mobilePreviewCapturePromise;
    }

    function _ensureEstimatePreviewModalZoomReset() {
        var modalEl = document.getElementById('erpEstimatePreviewModal');
        if (!modalEl || typeof window.fomsBindAttachmentPreviewModalZoomReset !== 'function') return;
        window.fomsBindAttachmentPreviewModalZoomReset(modalEl, 'erp-estimate-preview-body', {});
    }

    function _bindEstimatePreviewImageZoom(bodyEl) {
        if (typeof window.fomsBindAttachmentPreviewImageZoom !== 'function') return;
        window.fomsBindAttachmentPreviewImageZoom(bodyEl, {
            ensureModalReset: _ensureEstimatePreviewModalZoomReset
        });
    }

    function _openEstimatePreviewModal() {
        var modalEl = document.getElementById('erpEstimatePreviewModal');
        var body = document.getElementById('erp-estimate-preview-body');
        if (!modalEl || !body) return;

        function showModal(dataUrl) {
            if (!dataUrl) return;
            body.innerHTML = '<img src="' + dataUrl + '" alt="견적서" class="img-fluid rounded erp-attachment-preview-img">';
            _bindEstimatePreviewImageZoom(body);
            _ensureEstimatePreviewModalZoomReset();
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }

        if (_mobilePreviewDataUrl) {
            showModal(_mobilePreviewDataUrl);
            return;
        }

        _refreshMobilePreview().then(function () {
            showModal(_mobilePreviewDataUrl);
        });
    }

    function _bindEstimateMobilePreview() {
        if (_mobilePreviewBound) return;
        var card = document.getElementById('est-mobile-preview');
        if (!card) return;

        card.addEventListener('click', function () {
            _openEstimatePreviewModal();
        });
        card.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _openEstimatePreviewModal();
            }
        });

        _mobilePreviewBound = true;
    }

    function _bindEstimateViewModeListener() {
        if (typeof window.matchMedia !== 'function') return;
        var mq = window.matchMedia(_MOBILE_ESTIMATE_MQ);
        if (typeof mq.addEventListener === 'function') {
            mq.addEventListener('change', _handleEstimateViewModeChange);
        } else if (typeof mq.addListener === 'function') {
            mq.addListener(_handleEstimateViewModeChange);
        }
    }

    function _handleEstimateViewModeChange() {
        _applyEstimateViewMode();
        if (_estimateCacheLoaded && _isMobileEstimateView()) {
            _refreshMobilePreview();
        }
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

    async function _afterEstimateRendered() {
        _applyEstimateViewMode();

        if (typeof window.scheduleEstimateColumnRefresh === 'function') {
            window.scheduleEstimateColumnRefresh();
        }

        if (_isMobileEstimateView()) {
            await _refreshMobilePreview();
        }
    }

    async function erpLoadEstimatePreview() {
        if (!_isErpEnabled()) return;
        const orderId = _getOrderId();
        if (!orderId || orderId === 0) {
            _hideSection('est-loading');
            _hideSection('est-viewport');
            _hideSection('est-mobile-preview');
            _showSection('est-empty');
            return;
        }

        if (_estimateCacheLoaded) return;

        _hideSection('est-empty');
        _hideSection('est-viewport');
        _hideSection('est-mobile-preview');
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

            _estimateCacheLoaded = true;
            _dirty = false;
            _mobilePreviewDataUrl = '';

            const toolbar = document.getElementById('est-toolbar');
            const exportBtn = document.getElementById('btn-est-export');
            if (toolbar) toolbar.classList.remove('erp-est-hidden');
            if (exportBtn) exportBtn.disabled = false;

            await _afterEstimateRendered();

        } catch (err) {
            _hideSection('est-loading');
            _showSection('est-empty');
            console.error('[estimate-preview] fetch error:', err);
        }
    }

    window.erpInvalidateEstimateCache = function () {
        _estimateCacheLoaded = false;
        _dirty = true;
        _mobilePreviewDataUrl = '';
    };

    function _bindExportBtn() {
        const btn = document.getElementById('btn-est-export');
        if (!btn) return;

        btn.addEventListener('click', async function () {
            const docEl = document.getElementById('est-document');
            if (!docEl) {
                alert('견적서가 로드되지 않았습니다.');
                return;
            }

            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            btn.disabled = true;

            try {
                const numEl = document.getElementById('est-estimate-number');
                const numText = (numEl && numEl.textContent.trim()) || '견적서';
                const filename = numText + '.png';

                const dataUrl = await _captureEstimateDataUrl();
                if (!dataUrl) {
                    throw new Error('이미지 생성 실패');
                }

                const link = document.createElement('a');
                link.download = filename;
                link.href = dataUrl;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

            } catch (err) {
                console.error('[estimate-preview] 이미지 저장 실패:', err);
                alert('이미지 저장 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : String(err)));
            } finally {
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        });
    }

    function _init() {
        const tab = document.getElementById('erp-estimate-tab');
        if (!tab) return;

        _bindExportBtn();
        _bindEstimateMobilePreview();
        _bindEstimateViewModeListener();

        document.addEventListener('input', function (e) {
            if (e.target && e.target.dataset && 'erp' in e.target.dataset) {
                _dirty = true;
                _mobilePreviewDataUrl = '';
            }
        }, true);

        tab.addEventListener('shown.bs.tab', async function () {
            if (!_dirty && _estimateCacheLoaded) {
                await _afterEstimateRendered();
                return;
            }

            _estimateCacheLoaded = false;
            _mobilePreviewDataUrl = '';
            const orderId = _getOrderId();

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
