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

    var _mobileZoomBound = false;
    var _mobileZoomResizeTimer = null;
    var _zoomState = {
        scale: 1,
        fitScale: 1,
        tx: 0,
        ty: 0,
        pinching: false,
        pinchStartDist: 0,
        pinchStartScale: 1,
        panning: false,
        panStartX: 0,
        panStartY: 0,
        panBaseTx: 0,
        panBaseTy: 0
    };

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

    function _showEstimateDocument() {
        _showSection('est-viewport');
    }

    function _hideEstimateDocument() {
        _hideSection('est-viewport');
    }

    /** PC 견적서(700px) 오프스크린 클론 — 모바일 export/html2canvas용 */
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
            _hideEstimateDocument();
            _showSection('est-empty');
            return;
        }

        if (_estimateCacheLoaded) return;

        _hideSection('est-empty');
        _hideEstimateDocument();
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

            _showEstimateDocument();
            _estimateCacheLoaded = true;
            _dirty = false;

            // 저장 버튼 활성화 및 툴바 노출
            const toolbar = document.getElementById('est-toolbar');
            const exportBtn = document.getElementById('btn-est-export');
            if (toolbar) toolbar.classList.remove('erp-est-hidden');
            if (exportBtn) exportBtn.disabled = false;

            if (typeof window.scheduleEstimateColumnRefresh === 'function') {
                window.scheduleEstimateColumnRefresh();
            }
            _scheduleEstimateMobileFitRefresh();

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

    function _isMobileEstimateView() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia(_MOBILE_ESTIMATE_MQ).matches;
    }

    function _getEstimateZoomEls() {
        return {
            viewport: document.getElementById('est-viewport'),
            stage: document.getElementById('est-viewport-stage'),
            inner: document.getElementById('est-viewport-inner'),
            doc: document.getElementById('est-document'),
            hint: document.getElementById('est-mobile-zoom-hint')
        };
    }

    function _touchDistance(a, b) {
        return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
    }

    function _setEstimateGestureTransition(active) {
        var els = _getEstimateZoomEls();
        if (els.inner) {
            els.inner.classList.toggle('is-gesturing', !!active);
        }
    }

    function _applyEstimateTransform() {
        var els = _getEstimateZoomEls();
        if (!els.inner) return;
        if (!_isMobileEstimateView()) {
            els.inner.style.transform = '';
            return;
        }
        els.inner.style.transform = 'translate(' + _zoomState.tx + 'px,' + _zoomState.ty + 'px) scale(' + _zoomState.scale + ')';
    }

    function _computeEstimateFitScale(viewportEl) {
        var pad = 16;
        var available = Math.max(120, (viewportEl ? viewportEl.clientWidth : window.innerWidth) - pad);
        return Math.max(0.2, Math.min(1, available / _EST_DOC_WIDTH));
    }

    function _updateEstimateStageHeight() {
        var els = _getEstimateZoomEls();
        if (!els.stage || !els.doc || !_isMobileEstimateView()) {
            if (els.stage) els.stage.style.height = '';
            if (els.viewport) els.viewport.style.height = '';
            return;
        }
        var docH = els.doc.offsetHeight || 0;
        if (docH <= 0) {
            return;
        }
        var scaledH = docH * _zoomState.scale;
        var maxH = Math.max(240, Math.floor(window.innerHeight * 0.72));
        var stageH = Math.max(120, Math.min(Math.ceil(scaledH), maxH));
        els.stage.style.height = stageH + 'px';
        if (els.viewport) {
            els.viewport.style.height = '';
        }
    }

    function _bindEstimateDocResizeObserver() {
        var els = _getEstimateZoomEls();
        if (!els.doc || typeof ResizeObserver !== 'function') return;
        if (els.doc._estResizeObserved) return;
        var observer = new ResizeObserver(function () {
            var vp = document.getElementById('est-viewport');
            if (!vp || vp.classList.contains('erp-est-hidden')) return;
            _scheduleEstimateMobileFitRefresh();
        });
        observer.observe(els.doc);
        els.doc._estResizeObserved = true;
    }

    function _clampEstimatePan() {
        var els = _getEstimateZoomEls();
        if (!els.stage || !els.doc) return;

        var stageW = els.stage.clientWidth;
        var stageH = els.stage.clientHeight;
        var docH = els.doc.offsetHeight || 0;
        var visualW = _EST_DOC_WIDTH * _zoomState.scale;
        var visualH = docH * _zoomState.scale;

        var minTx;
        var maxTx;
        if (visualW <= stageW) {
            var centeredX = (stageW - visualW) / 2;
            minTx = maxTx = centeredX;
        } else {
            minTx = stageW - visualW;
            maxTx = 0;
        }

        var minTy;
        var maxTy;
        if (visualH <= stageH) {
            var centeredY = (stageH - visualH) / 2;
            minTy = maxTy = centeredY;
        } else {
            minTy = stageH - visualH;
            maxTy = 0;
        }

        _zoomState.tx = Math.max(minTx, Math.min(maxTx, _zoomState.tx));
        _zoomState.ty = Math.max(minTy, Math.min(maxTy, _zoomState.ty));
    }

    function _resetEstimateFitView() {
        var els = _getEstimateZoomEls();
        if (!els.viewport || !els.inner || !els.doc) return;

        if (!_isMobileEstimateView()) {
            _zoomState.scale = 1;
            _zoomState.fitScale = 1;
            _zoomState.tx = 0;
            _zoomState.ty = 0;
            _setEstimateGestureTransition(false);
            _applyEstimateTransform();
            _updateEstimateStageHeight();
            if (els.hint) els.hint.setAttribute('aria-hidden', 'true');
            return;
        }

        _zoomState.fitScale = _computeEstimateFitScale(els.viewport);
        _zoomState.scale = _zoomState.fitScale;
        _zoomState.tx = 0;
        _zoomState.ty = 0;
        _clampEstimatePan();
        _setEstimateGestureTransition(false);
        _applyEstimateTransform();
        _updateEstimateStageHeight();
        if (els.hint) els.hint.setAttribute('aria-hidden', 'false');
    }

    function _refreshEstimateIfActiveTab() {
        var pane = document.getElementById('erp-estimate');
        if (!pane || !pane.classList.contains('active')) return;
        _scheduleEstimateMobileFitRefresh();
    }

    function _scheduleEstimateMobileFitRefresh() {
        window.requestAnimationFrame(function () {
            window.requestAnimationFrame(function () {
                _resetEstimateFitView();
            });
        });
    }

    function _handleEstimateTouchStart(e) {
        if (!_isMobileEstimateView() || !e.touches) return;

        if (e.touches.length === 2) {
            _zoomState.pinching = true;
            _zoomState.panning = false;
            _zoomState.pinchStartDist = _touchDistance(e.touches[0], e.touches[1]);
            _zoomState.pinchStartScale = _zoomState.scale;
            _setEstimateGestureTransition(true);
            return;
        }

        if (e.touches.length === 1 && _zoomState.scale > _zoomState.fitScale + 0.02) {
            var t = e.touches[0];
            _zoomState.panning = true;
            _zoomState.panStartX = t.clientX;
            _zoomState.panStartY = t.clientY;
            _zoomState.panBaseTx = _zoomState.tx;
            _zoomState.panBaseTy = _zoomState.ty;
            _setEstimateGestureTransition(true);
        }
    }

    function _handleEstimateTouchMove(e) {
        if (!_isMobileEstimateView() || !e.touches) return;

        if (_zoomState.pinching && e.touches.length === 2) {
            e.preventDefault();
            var dist = _touchDistance(e.touches[0], e.touches[1]);
            if (_zoomState.pinchStartDist > 0) {
                var next = _zoomState.pinchStartScale * (dist / _zoomState.pinchStartDist);
                var maxScale = Math.max(3, _zoomState.fitScale * 3);
                _zoomState.scale = Math.max(_zoomState.fitScale, Math.min(maxScale, next));
                if (_zoomState.scale <= _zoomState.fitScale + 0.01) {
                    _zoomState.scale = _zoomState.fitScale;
                    _zoomState.tx = 0;
                    _zoomState.ty = 0;
                }
                _clampEstimatePan();
                _applyEstimateTransform();
                _updateEstimateStageHeight();
            }
            return;
        }

        if (_zoomState.panning && e.touches.length === 1) {
            e.preventDefault();
            var touch = e.touches[0];
            _zoomState.tx = _zoomState.panBaseTx + (touch.clientX - _zoomState.panStartX);
            _zoomState.ty = _zoomState.panBaseTy + (touch.clientY - _zoomState.panStartY);
            _clampEstimatePan();
            _applyEstimateTransform();
        }
    }

    function _handleEstimateTouchEnd(e) {
        if (!_isMobileEstimateView()) return;

        var remaining = e && e.touches ? e.touches.length : 0;

        if (_zoomState.pinching && remaining < 2) {
            _zoomState.pinching = false;
            if (_zoomState.scale <= _zoomState.fitScale + 0.03) {
                _resetEstimateFitView();
            } else if (remaining === 1 && e.touches && e.touches[0]) {
                var t = e.touches[0];
                _zoomState.panning = true;
                _zoomState.panStartX = t.clientX;
                _zoomState.panStartY = t.clientY;
                _zoomState.panBaseTx = _zoomState.tx;
                _zoomState.panBaseTy = _zoomState.ty;
            } else {
                _setEstimateGestureTransition(false);
            }
            return;
        }

        if (_zoomState.panning && remaining === 0) {
            _zoomState.panning = false;
            _setEstimateGestureTransition(false);
        }
    }

    function _bindEstimateMobileZoom() {
        if (_mobileZoomBound) return;
        var els = _getEstimateZoomEls();
        if (!els.viewport || !els.stage) return;

        els.viewport.addEventListener('touchstart', _handleEstimateTouchStart, { passive: true });
        els.viewport.addEventListener('touchmove', _handleEstimateTouchMove, { passive: false });
        els.viewport.addEventListener('touchend', _handleEstimateTouchEnd, { passive: true });
        els.viewport.addEventListener('touchcancel', _handleEstimateTouchEnd, { passive: true });

        window.addEventListener('resize', function () {
            clearTimeout(_mobileZoomResizeTimer);
            _mobileZoomResizeTimer = window.setTimeout(function () {
                var vp = document.getElementById('est-viewport');
                if (!vp || vp.classList.contains('erp-est-hidden')) return;
                _resetEstimateFitView();
            }, 150);
        });

        _mobileZoomBound = true;
    }

    // ── 이미지 저장 (실측 대시보드와 동일 방식) ──────────────────────
    function _bindExportBtn() {
        const btn = document.getElementById('btn-est-export');
        if (!btn) return;

        btn.addEventListener('click', async function () {
            const docEl = document.getElementById('est-document');
            const viewportEl = document.getElementById('est-viewport');
            if (!docEl || !viewportEl || viewportEl.classList.contains('erp-est-hidden')) {
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

            var exportEl = null;
            try {
                const numEl = document.getElementById('est-estimate-number');
                const numText = (numEl && numEl.textContent.trim()) || '견적서';
                const filename = numText + '.png';

                exportEl = _buildExportClone(docEl);

                const canvas = await html2canvas(exportEl, {
                    scale: 2,
                    useCORS: true,
                    logging: false,
                    backgroundColor: '#ffffff',
                    width: _EST_EXPORT_WIDTH,
                    windowWidth: _EST_EXPORT_WIDTH
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
                _removeExportClone(exportEl);
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
        _bindEstimateMobileZoom();
        _bindEstimateDocResizeObserver();

        // ERP Order 폼 입력 시 dirty 플래그 설정 (캡처 페이즈로 모든 [data-erp] 입력 감지)
        document.addEventListener('input', function (e) {
            if (e.target && e.target.dataset && 'erp' in e.target.dataset) {
                _dirty = true;
            }
        }, true);

        // 계약서 탭 활성화 시: 변경 없고 캐시 유효하면 즉시 반환 (불필요한 네트워크 요청 차단)
        tab.addEventListener('shown.bs.tab', async function () {
            if (!_dirty && _estimateCacheLoaded) {
                if (typeof window.scheduleEstimateColumnRefresh === 'function') {
                    window.scheduleEstimateColumnRefresh();
                }
                _scheduleEstimateMobileFitRefresh();
                return;
            }

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

        _refreshEstimateIfActiveTab();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _init);
    } else {
        _init();
    }

})();
