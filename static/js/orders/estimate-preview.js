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
    var _estimateItems = [];
    var _estimateManualRows = [];
    var _manualRowsBound = false;
    var _manualRowsSaveTimer = null;
    var _MANUAL_ROWS_SAVE_DELAY_MS = 600;

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

    function _asText(value) {
        return value === null || value === undefined ? '' : String(value);
    }

    function _cloneManualRows(rows) {
        return (rows || []).map(function (row) {
            return {
                id: _asText(row.id),
                after_index: Number.isInteger(Number(row.after_index)) ? Number(row.after_index) : -1,
                product_name: _asText(row.product_name),
                spec: _asText(row.spec),
                color: _asText(row.color),
                quantity: _asText(row.quantity),
                amount: _asText(row.amount),
                affects_total: row.affects_total === true
            };
        });
    }

    function _makeManualRowId() {
        return 'mr_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
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

    // html2canvas는 견적서 내보내기 시에만 필요 → 첫 사용 시 1회 동적 로드.
    // (모든 ERP 페이지에서 CDN 동기 로드로 렌더를 차단하던 문제 제거)
    var _HTML2CANVAS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    var _html2canvasPromise = null;
    function _ensureHtml2canvas() {
        if (typeof window.html2canvas === 'function') return Promise.resolve();
        if (_html2canvasPromise) return _html2canvasPromise;
        _html2canvasPromise = new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = _HTML2CANVAS_SRC;
            s.async = true;
            s.onload = function () {
                if (typeof window.html2canvas === 'function') {
                    resolve();
                } else {
                    _html2canvasPromise = null;
                    reject(new Error('html2canvas loaded but global missing'));
                }
            };
            s.onerror = function () {
                _html2canvasPromise = null;
                reject(new Error('html2canvas load failed'));
            };
            document.head.appendChild(s);
        });
        return _html2canvasPromise;
    }

    function _captureEstimateDataUrl() {
        var docEl = document.getElementById('est-document');
        if (!docEl) return Promise.resolve('');

        return _withEstimateExportMode(function () {
            var exportEl = _buildExportClone(docEl);
            return _ensureHtml2canvas().then(function () {
                return html2canvas(exportEl, {
                    scale: 2,
                    useCORS: true,
                    logging: false,
                    backgroundColor: '#ffffff',
                    width: _EST_EXPORT_WIDTH,
                    windowWidth: _EST_EXPORT_WIDTH
                }).then(function (canvas) {
                    return canvas.toDataURL('image/png');
                });
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

    function _getEstimatePreviewState() {
        if (!window.__erpLastStructuredData || typeof window.__erpLastStructuredData !== 'object') {
            window.__erpLastStructuredData = {};
        }
        if (
            !window.__erpLastStructuredData.estimate_preview
            || typeof window.__erpLastStructuredData.estimate_preview !== 'object'
            || Array.isArray(window.__erpLastStructuredData.estimate_preview)
        ) {
            window.__erpLastStructuredData.estimate_preview = {};
        }
        return window.__erpLastStructuredData.estimate_preview;
    }

    function _syncManualRowsToStructured() {
        var preview = _getEstimatePreviewState();
        preview.manual_rows = _cloneManualRows(_estimateManualRows);
    }

    function _setManualRowsDirty() {
        _dirty = true;
        _mobilePreviewDataUrl = '';
        _syncManualRowsToStructured();
    }

    function _scheduleManualRowsSave() {
        _setManualRowsDirty();
        window.clearTimeout(_manualRowsSaveTimer);
        _manualRowsSaveTimer = window.setTimeout(function () {
            if (typeof window.erpSaveStructured !== 'function') return;
            window.erpSaveStructured({ redirect: false, _skipValidation: true })
                .catch(function (err) {
                    console.error('[estimate-preview] 수동 행 저장 실패:', err);
                });
        }, _MANUAL_ROWS_SAVE_DELAY_MS);
    }

    function _manualRowsFromResponse(items, estimatePreview) {
        if (
            estimatePreview
            && Array.isArray(estimatePreview.manual_rows)
            && estimatePreview.manual_rows.length > 0
        ) {
            return _cloneManualRows(estimatePreview.manual_rows);
        }

        return (items || [])
            .filter(function (item) { return item && item.source === 'manual'; })
            .map(function (item) {
                return {
                    id: _asText(item.manual_row_id || item.id || _makeManualRowId()),
                    after_index: Number.isInteger(Number(item.after_index)) ? Number(item.after_index) : -1,
                    product_name: _asText(item.product_name),
                    spec: _asText(item.spec),
                    color: _asText(item.color),
                    quantity: _asText(item.quantity),
                    amount: _asText(item.amount_raw || item.amount),
                    affects_total: item.affects_total === true
                };
            });
    }

    function _getOriginalEstimateItems(items) {
        return (items || []).filter(function (item) {
            return !item || item.source !== 'manual';
        });
    }

    function _getManualRowsForIndex(afterIndex) {
        return _estimateManualRows.filter(function (row) {
            return Number(row.after_index) === Number(afterIndex);
        });
    }

    function _makeCellInput(row, field, multiline) {
        var el = document.createElement(multiline ? 'textarea' : 'input');
        if (!multiline) {
            el.type = 'text';
        } else {
            el.rows = 1;
        }
        el.className = 'erp-est-manual-input';
        el.value = row[field] || '';
        el.setAttribute('data-est-manual-field', field);
        el.setAttribute('data-est-manual-id', row.id);
        return el;
    }

    function _appendManualCell(tr, row, field, className, multiline) {
        var td = document.createElement('td');
        if (className) td.className = className;
        td.appendChild(_makeCellInput(row, field, multiline));
        tr.appendChild(td);
        return td;
    }

    function _appendManualRow(tbody, row) {
        var tr = document.createElement('tr');
        tr.className = 'erp-est-manual-row';
        tr.setAttribute('data-est-manual-id', row.id);

        var tdName = document.createElement('td');
        var nameWrap = document.createElement('div');
        nameWrap.className = 'erp-est-manual-name-wrap';
        nameWrap.appendChild(_makeCellInput(row, 'product_name', false));

        var deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'erp-est-manual-delete erp-est-edit-control';
        deleteBtn.setAttribute('data-est-delete-manual-id', row.id);
        deleteBtn.setAttribute('title', '행 삭제');
        deleteBtn.setAttribute('aria-label', '수동 행 삭제');
        deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
        nameWrap.appendChild(deleteBtn);

        tdName.appendChild(nameWrap);
        tr.appendChild(tdName);
        _appendManualCell(tr, row, 'spec', 'erp-est-td-spec', true);
        _appendManualCell(tr, row, 'color', '', false);
        _appendManualCell(tr, row, 'quantity', '', false);
        _appendManualCell(tr, row, 'amount', 'text-end', false);
        tbody.appendChild(tr);
    }

    function _appendAddControlRow(tbody, afterIndex) {
        var tr = document.createElement('tr');
        tr.className = 'erp-est-add-row erp-est-edit-control';
        var td = document.createElement('td');
        td.colSpan = 5;

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'erp-est-add-row-btn';
        btn.setAttribute('data-est-add-after-index', String(afterIndex));
        btn.setAttribute('title', '행 추가');
        btn.setAttribute('aria-label', '수동 행 추가');
        btn.innerHTML = '<i class="fas fa-plus"></i>';

        td.appendChild(btn);
        tr.appendChild(td);
        tbody.appendChild(tr);
    }

    function _renderReadOnlyItemRow(tbody, item) {
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
    }

    function _renderManualRowsForIndex(tbody, afterIndex) {
        _getManualRowsForIndex(afterIndex).forEach(function (row) {
            _appendManualRow(tbody, row);
        });
    }

    function _renderItems(items, estimatePreview) {
        const tbody = document.getElementById('est-items-tbody');
        const emptyRow = document.getElementById('est-items-empty');
        if (!tbody) return;

        tbody.querySelectorAll('tr:not(#est-items-empty)').forEach(function (r) { r.remove(); });
        _estimateItems = _getOriginalEstimateItems(items);
        _estimateManualRows = _manualRowsFromResponse(items, estimatePreview);
        _syncManualRowsToStructured();

        if (_estimateItems.length === 0 && _estimateManualRows.length === 0) {
            if (emptyRow) emptyRow.classList.remove('erp-est-hidden');
            _appendAddControlRow(tbody, -1);
            return;
        }
        if (emptyRow) emptyRow.classList.add('erp-est-hidden');

        _renderManualRowsForIndex(tbody, -1);
        if (_estimateItems.length === 0) {
            _appendAddControlRow(tbody, -1);
            return;
        }
        _estimateItems.forEach(function (item, idx) {
            _renderReadOnlyItemRow(tbody, item);
            _renderManualRowsForIndex(tbody, idx);
            _appendAddControlRow(tbody, idx);
        });
    }

    function _addManualRow(afterIndex) {
        _estimateManualRows.push({
            id: _makeManualRowId(),
            after_index: Number.isInteger(Number(afterIndex)) ? Number(afterIndex) : -1,
            product_name: '',
            spec: '',
            color: '',
            quantity: '',
            amount: '',
            affects_total: false
        });
        _renderItems(_estimateItems, { manual_rows: _estimateManualRows });
        _scheduleManualRowsSave();
        if (typeof window.scheduleEstimateColumnRefresh === 'function') {
            window.scheduleEstimateColumnRefresh();
        }
    }

    function _deleteManualRow(rowId) {
        _estimateManualRows = _estimateManualRows.filter(function (row) {
            return row.id !== rowId;
        });
        _renderItems(_estimateItems, { manual_rows: _estimateManualRows });
        _scheduleManualRowsSave();
        if (typeof window.scheduleEstimateColumnRefresh === 'function') {
            window.scheduleEstimateColumnRefresh();
        }
    }

    function _updateManualRow(rowId, field, value) {
        _estimateManualRows.forEach(function (row) {
            if (row.id === rowId) {
                row[field] = value;
            }
        });
        _scheduleManualRowsSave();
    }

    function _bindManualRows() {
        if (_manualRowsBound) return;
        var tbody = document.getElementById('est-items-tbody');
        if (!tbody) return;

        tbody.addEventListener('click', function (e) {
            var addBtn = e.target && e.target.closest('[data-est-add-after-index]');
            if (addBtn) {
                _addManualRow(addBtn.getAttribute('data-est-add-after-index'));
                return;
            }

            var deleteBtn = e.target && e.target.closest('[data-est-delete-manual-id]');
            if (deleteBtn) {
                _deleteManualRow(deleteBtn.getAttribute('data-est-delete-manual-id'));
            }
        });

        tbody.addEventListener('input', function (e) {
            var target = e.target;
            if (!target || !target.matches('[data-est-manual-field][data-est-manual-id]')) return;
            _updateManualRow(
                target.getAttribute('data-est-manual-id'),
                target.getAttribute('data-est-manual-field'),
                target.value || ''
            );
        });

        _manualRowsBound = true;
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

        const discountRow = document.getElementById('est-discount-row');
        if (d.discount_amount && d.discount_amount > 0) {
            _setText('est-discount-amount', _fmtMoney(d.discount_amount));
            if (discountRow) discountRow.classList.remove('erp-est-hidden');
        } else {
            if (discountRow) discountRow.classList.add('erp-est-hidden');
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
            _renderItems(d.items, d.estimate_preview || {});
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
        _bindManualRows();
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
