/**
 * estimate-preview.js
 * 견적서(계약서) 프리뷰 탭 — ERP Order 서브탭용
 */
(function () {
    'use strict';

    let _estimateCacheLoaded = false;
    let _dirty = true; // 첫 진입 시 항상 새로 로드
    let _paymentInfoVariants = null;
    let _companyInfoVariants = null;
    let _lastIsLahom = false;
    let _lastFactory2 = false;
    var _EST_EXPORT_WIDTH = 700;
    var _EST_DOC_WIDTH = 700;
    var _MOBILE_ESTIMATE_MQ = '(max-width: 991.98px)';
    var _MOBILE_CANVAS_MAX_SIDE = 4096;
    var _MOBILE_CANVAS_MAX_PIXELS = 16000000;
    var _HTML2CANVAS_LOAD_TIMEOUT_MS = 10000;
    var _HTML2CANVAS_RENDER_TIMEOUT_MS = 10000;

    var _mobilePreviewBound = false;
    var _mobilePreviewDataUrl = '';
    var _mobilePreviewCapturePromise = null;
    var _mobilePreviewFallbackActive = false;
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

    function _setMobilePreviewUrl(url) {
        if (
            _mobilePreviewDataUrl
            && _mobilePreviewDataUrl.indexOf('blob:') === 0
            && typeof URL !== 'undefined'
            && typeof URL.revokeObjectURL === 'function'
        ) {
            URL.revokeObjectURL(_mobilePreviewDataUrl);
        }
        _mobilePreviewDataUrl = url || '';
    }

    function _isMobileEstimateView() {
        return typeof window.matchMedia === 'function'
            && window.matchMedia(_MOBILE_ESTIMATE_MQ).matches;
    }

    /**
     * iOS(아이폰·아이패드) Safari 계열 여부.
     * iOS Safari는 a[download] 속성을 무시(동일 탭 인라인 표시)하고, 비동기 캡처
     * 이후의 link.click()은 transient activation을 잃어 다운로드가 트리거되지 않는다.
     * → iOS는 캡처 이미지를 모달 <img>로 띄워 "길게 눌러 사진에 저장" 경로로 안내한다.
     * iPadOS 13+는 UA가 Mac으로 위장하므로 maxTouchPoints로 보강 판별한다.
     */
    function _isIosLike() {
        var ua = navigator.userAgent || '';
        if (/iPad|iPhone|iPod/.test(ua)) return true;
        return navigator.platform === 'MacIntel'
            && typeof navigator.maxTouchPoints === 'number'
            && navigator.maxTouchPoints > 1;
    }

    function _withTimeout(promise, timeoutMs, message) {
        return new Promise(function (resolve, reject) {
            var settled = false;
            var timer = window.setTimeout(function () {
                if (settled) return;
                settled = true;
                reject(new Error(message));
            }, timeoutMs);

            Promise.resolve(promise).then(function (value) {
                if (settled) return;
                settled = true;
                window.clearTimeout(timer);
                resolve(value);
            }).catch(function (err) {
                if (settled) return;
                settled = true;
                window.clearTimeout(timer);
                reject(err);
            });
        });
    }

    function _withEagerLazyMedia(run) {
        if (!_isIosLike()) {
            return Promise.resolve().then(run);
        }

        // html2canvas 1.4.1 can hang forever on iOS Safari when any lazy image
        // exists in the cloned document. Flip only images, not lazy iframes, to
        // avoid waking unrelated embedded tools during an estimate save.
        var changed = Array.from(document.querySelectorAll('img[loading="lazy"]'));
        changed.forEach(function (el) {
            el.setAttribute('data-est-prev-loading', 'lazy');
            el.setAttribute('loading', 'eager');
        });

        return Promise.resolve()
            .then(run)
            .finally(function () {
                changed.forEach(function (el) {
                    if (el.getAttribute('data-est-prev-loading') === 'lazy') {
                        el.setAttribute('loading', 'lazy');
                    }
                    el.removeAttribute('data-est-prev-loading');
                });
            });
    }

    function _setMobileCaptureFallback(active, message) {
        var fallbackMsg = document.getElementById('est-mobile-preview-fallback-msg');
        if (fallbackMsg && message) {
            fallbackMsg.textContent = message;
        }

        _mobilePreviewFallbackActive = !!active;
        if (!_isMobileEstimateView()) {
            _hideSection('est-mobile-preview-fallback');
            return;
        }

        if (_mobilePreviewFallbackActive) {
            _hideSection('est-mobile-preview');
            _showSection('est-mobile-preview-fallback');
            _showSection('est-viewport');
        } else {
            _hideSection('est-mobile-preview-fallback');
            if (!_isIosLike()) {
                _hideSection('est-viewport');
            }
        }
    }

    function _applyEstimateViewMode() {
        if (_isMobileEstimateView()) {
            if (_mobilePreviewFallbackActive || _isIosLike()) {
                _showSection('est-mobile-preview-fallback');
                _showSection('est-viewport');
                if (!_mobilePreviewFallbackActive) {
                    _hideSection('est-mobile-preview-fallback');
                }
            } else {
                _hideSection('est-mobile-preview-fallback');
                _hideSection('est-viewport');
            }
        } else {
            _hideSection('est-mobile-preview');
            _hideSection('est-mobile-preview-fallback');
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
            var settled = false;
            var timer = window.setTimeout(function () {
                if (settled) return;
                settled = true;
                _html2canvasPromise = null;
                reject(new Error('html2canvas load timed out'));
            }, _HTML2CANVAS_LOAD_TIMEOUT_MS);
            function finish(ok, err) {
                if (settled) return;
                settled = true;
                window.clearTimeout(timer);
                if (ok) {
                    resolve();
                    return;
                }
                _html2canvasPromise = null;
                reject(err);
            }
            var s = document.createElement('script');
            s.src = _HTML2CANVAS_SRC;
            s.async = true;
            s.onload = function () {
                if (typeof window.html2canvas === 'function') {
                    finish(true);
                } else {
                    finish(false, new Error('html2canvas loaded but global missing'));
                }
            };
            s.onerror = function () {
                finish(false, new Error('html2canvas load failed'));
            };
            document.head.appendChild(s);
        });
        return _html2canvasPromise;
    }

    function _getEstimateCaptureMetrics(exportEl) {
        var width = _EST_EXPORT_WIDTH;
        var height = Math.max(
            1,
            Math.ceil(exportEl.scrollHeight || exportEl.offsetHeight || exportEl.getBoundingClientRect().height || 1)
        );
        var scale = 2;

        if (_isMobileEstimateView()) {
            var maxBySide = Math.min(_MOBILE_CANVAS_MAX_SIDE / width, _MOBILE_CANVAS_MAX_SIDE / height);
            var maxByArea = Math.sqrt(_MOBILE_CANVAS_MAX_PIXELS / (width * height));
            scale = Math.min(scale, maxBySide, maxByArea);
            if (!Number.isFinite(scale) || scale < 0.5) {
                throw new Error('estimate document too tall for mobile canvas');
            }
            scale = Math.max(0.5, Math.floor(scale * 100) / 100);
        }

        return {
            width: width,
            height: height,
            scale: scale
        };
    }

    function _waitForEstimateImages(exportEl) {
        var images = Array.from(exportEl.querySelectorAll('img'));
        if (images.length === 0) return Promise.resolve();

        return Promise.all(images.map(function (img) {
            if (img.complete) return Promise.resolve();
            if (typeof img.decode === 'function') {
                return Promise.race([
                    img.decode().catch(function () {}),
                    new Promise(function (resolve) {
                        window.setTimeout(resolve, 4000);
                    })
                ]);
            }
            return new Promise(function (resolve) {
                function done() {
                    window.clearTimeout(timer);
                    resolve();
                }
                var timer = window.setTimeout(done, 4000);
                img.onload = done;
                img.onerror = done;
            });
        })).then(function () {});
    }

    function _waitForPreviewImageReady(img, url) {
        return new Promise(function (resolve) {
            if (!img || !url) {
                resolve(false);
                return;
            }

            var settled = false;
            var timer = null;
            function finish(ok) {
                if (settled) return;
                settled = true;
                window.clearTimeout(timer);
                img.removeEventListener('load', onLoad);
                img.removeEventListener('error', onError);
                resolve(ok);
            }
            function onLoad() {
                finish(!!img.naturalWidth);
            }
            function onError() {
                finish(false);
            }

            img.addEventListener('load', onLoad);
            img.addEventListener('error', onError);
            timer = window.setTimeout(function () {
                finish(false);
            }, 4000);
            img.src = url;

            if (img.complete) {
                window.setTimeout(function () {
                    finish(!!img.naturalWidth);
                }, 0);
            }
        });
    }

    function _canvasToImageUrl(canvas, preferBlobUrl) {
        if (!canvas || !canvas.width || !canvas.height) {
            return Promise.reject(new Error('empty canvas'));
        }

        if (
            preferBlobUrl
            && typeof canvas.toBlob === 'function'
            && typeof URL !== 'undefined'
            && typeof URL.createObjectURL === 'function'
        ) {
            return new Promise(function (resolve, reject) {
                var settled = false;
                var timer = window.setTimeout(function () {
                    if (settled) return;
                    settled = true;
                    reject(new Error('canvas toBlob timed out'));
                }, 4000);

                canvas.toBlob(function (blob) {
                    if (settled) return;
                    settled = true;
                    window.clearTimeout(timer);
                    if (!blob) {
                        reject(new Error('canvas toBlob returned empty image'));
                        return;
                    }
                    resolve(URL.createObjectURL(blob));
                }, 'image/png');
            });
        }

        var dataUrl = canvas.toDataURL('image/png');
        if (!dataUrl || dataUrl === 'data:,') {
            return Promise.reject(new Error('canvas toDataURL returned empty image'));
        }
        return Promise.resolve(dataUrl);
    }

    function _captureEstimateDataUrl(options) {
        var docEl = document.getElementById('est-document');
        if (!docEl) return Promise.resolve('');
        var preferBlobUrl = !!(options && options.preferBlobUrl);

        return _withEstimateExportMode(function () {
            var exportEl = _buildExportClone(docEl);
            return _ensureHtml2canvas().then(function () {
                return _waitForEstimateImages(exportEl);
            }).then(function () {
                var metrics = _getEstimateCaptureMetrics(exportEl);
                return _withEagerLazyMedia(function () {
                    return _withTimeout(html2canvas(exportEl, {
                        scale: metrics.scale,
                        useCORS: true,
                        imageTimeout: 8000,
                        logging: false,
                        backgroundColor: '#ffffff',
                        width: metrics.width,
                        height: metrics.height,
                        windowWidth: metrics.width,
                        windowHeight: metrics.height
                    }), _HTML2CANVAS_RENDER_TIMEOUT_MS, 'html2canvas render timed out');
                }).then(function (canvas) {
                    return _canvasToImageUrl(canvas, preferBlobUrl);
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
        _setMobileCaptureFallback(false);
        _setMobilePreviewUrl('');

        if (_isIosLike()) {
            _showSection('est-viewport');
            return Promise.resolve();
        }

        if (_mobilePreviewCapturePromise) return _mobilePreviewCapturePromise;

        _mobilePreviewCapturePromise = _captureEstimateDataUrl({ preferBlobUrl: true }).then(function (dataUrl) {
            if (!dataUrl) {
                _setMobileCaptureFallback(true, 'iPhone/Safari에서 이미지 미리보기를 만들 수 없어 원본 견적서를 표시합니다.');
                return;
            }
            _setMobilePreviewUrl(dataUrl);
            img.alt = '견적서 미리보기';
            return _waitForPreviewImageReady(img, dataUrl).then(function (ready) {
                if (!ready) {
                    _setMobilePreviewUrl('');
                    _setMobileCaptureFallback(true, '이미지 미리보기 표시 중 오류가 발생하여 원본 견적서를 표시합니다.');
                    return;
                }
                _showSection('est-mobile-preview');
            });
        }).catch(function (err) {
            console.error('[estimate-preview] mobile capture error:', err);
            _setMobileCaptureFallback(true, '이미지 미리보기 생성 중 오류가 발생하여 원본 견적서를 표시합니다.');
        }).finally(function () {
            _mobilePreviewCapturePromise = null;
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

    function _openEstimatePreviewModal(opts) {
        opts = opts || {};
        var modalEl = document.getElementById('erpEstimatePreviewModal');
        var body = document.getElementById('erp-estimate-preview-body');
        if (!modalEl || !body) return;

        function showModal(dataUrl) {
            if (!dataUrl) return;
            var hintHtml = opts.hint
                ? '<p class="text-muted small text-center mb-2">' + opts.hint + '</p>'
                : '';
            body.innerHTML = hintHtml
                + '<img src="' + dataUrl + '" alt="견적서" class="img-fluid rounded erp-attachment-preview-img" draggable="false">';
            _bindEstimatePreviewImageZoom(body);
            _ensureEstimatePreviewModalZoomReset();
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }

        if (opts.dataUrl) {
            showModal(opts.dataUrl);
            return;
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
        _setMobilePreviewUrl('');
        _mobilePreviewFallbackActive = false;
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

    function _normalizeLogoOpts(logoOpts) {
        if (typeof logoOpts === 'boolean') {
            return { isLahom: logoOpts, factory2: false };
        }
        return {
            isLahom: !!(logoOpts && logoOpts.isLahom),
            factory2: !!(logoOpts && logoOpts.factory2),
        };
    }

    function _applyEstimateLogo(logoOpts) {
        const opts = _normalizeLogoOpts(logoOpts);
        const logoEl = document.getElementById('est-logo-img');
        if (!logoEl) {
            return;
        }
        const factory2Src = logoEl.dataset.factory2Src;
        const lahomSrc = logoEl.dataset.lahomSrc;
        const haudSrc = logoEl.dataset.haudSrc;

        if (opts.factory2 && factory2Src) {
            logoEl.src = factory2Src;
            logoEl.classList.remove('erp-est-logo--haud');
            logoEl.classList.add('erp-est-logo--lahom');
            return;
        }
        if (opts.isLahom) {
            logoEl.src = lahomSrc;
            logoEl.classList.remove('erp-est-logo--haud');
            logoEl.classList.add('erp-est-logo--lahom');
            return;
        }
        logoEl.src = haudSrc || lahomSrc;
        logoEl.classList.remove('erp-est-logo--lahom');
        logoEl.classList.add('erp-est-logo--haud');
    }

    function _applyEstimateStamp(logoOpts) {
        const opts = _normalizeLogoOpts(logoOpts);
        const stampEl = document.getElementById('est-stamp-img');
        if (!stampEl) {
            return;
        }
        const factory2Src = stampEl.dataset.factory2Src;
        const defaultSrc = stampEl.dataset.defaultSrc || stampEl.src;

        if (opts.factory2 && factory2Src) {
            stampEl.src = factory2Src;
            stampEl.classList.add('erp-est-stamp--factory2');
        } else {
            stampEl.src = defaultSrc;
            stampEl.classList.remove('erp-est-stamp--factory2');
        }
        stampEl.classList.remove('erp-est-hidden');
    }

    function _applyCompanyInfo(ci, logoOpts) {
        _setText('est-company-name', ci.name);
        _setText('est-company-ceo', ci.ceo);
        _setText('est-company-biznum', ci.business_number);
        _setText('est-company-address', ci.address);
        _setText('est-company-industry', ci.industry);
        _setText('est-company-phone', ci.phone);
        _setText('est-company-center', ci.customer_center);

        _applyEstimateLogo(logoOpts);
        _applyEstimateStamp(logoOpts);
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

    function _renderFreeInputRows(lines) {
        var wrap = document.getElementById('est-free-input-rows');
        if (!wrap) return;
        wrap.innerHTML = '';
        var list = Array.isArray(lines) ? lines : [];
        list.forEach(function (row) {
            if (!row) return;
            var amount = Number(row.amount) || 0;
            if (amount <= 0) return;
            var lineEl = document.createElement('div');
            lineEl.className = 'erp-est-sum-row erp-est-sum-free-input';
            var labelEl = document.createElement('span');
            labelEl.className = 'erp-est-sum-label';
            labelEl.textContent = String(row.label || '추가');
            var valueEl = document.createElement('span');
            valueEl.className = 'erp-est-sum-value erp-est-sum-free-input-val';
            valueEl.textContent = _fmtMoney(amount);
            lineEl.appendChild(labelEl);
            lineEl.appendChild(valueEl);
            wrap.appendChild(lineEl);
        });
    }

    function _applyPaymentInfo(d, pi) {
        var itemsSubtotal = d.items_subtotal;
        if (itemsSubtotal == null || itemsSubtotal === '') {
            itemsSubtotal = Math.max(0, Number(d.total_amount || 0) - Number(d.free_input_amount || 0));
        }
        _setText('est-total-amount', _fmtMoney(itemsSubtotal));
        _renderFreeInputRows(d.free_input_lines);

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

    function _applyPaymentAccountsOnly(pi) {
        var accountsWrap = document.getElementById('est-pay-accounts');
        if (accountsWrap) {
            _renderPaymentAccounts(accountsWrap, pi);
        }
        _setText('est-pay-notice', pi && pi.notice);
    }

    window.erpApplyEstimateFactory2Variant = function (factory2) {
        _lastFactory2 = !!factory2;
        var logoOpts = { isLahom: _lastIsLahom, factory2: _lastFactory2 };
        if (_companyInfoVariants) {
            var ci = factory2 ? _companyInfoVariants.factory2 : _companyInfoVariants.default;
            if (ci) {
                _applyCompanyInfo(ci, logoOpts);
            } else {
                _applyEstimateLogo(logoOpts);
                _applyEstimateStamp(logoOpts);
            }
        } else {
            _applyEstimateLogo(logoOpts);
            _applyEstimateStamp(logoOpts);
        }
        if (_paymentInfoVariants) {
            var pi = factory2 ? _paymentInfoVariants.factory2 : _paymentInfoVariants.default;
            if (pi) {
                _applyPaymentAccountsOnly(pi);
            }
        }
    };

    // 하위 호환: 결제정보만 전환하던 기존 호출부
    window.erpApplyEstimatePaymentVariant = window.erpApplyEstimateFactory2Variant;

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
            _hideSection('est-mobile-preview-fallback');
            _showSection('est-empty');
            return;
        }

        if (_estimateCacheLoaded) return;

        _hideSection('est-empty');
        _hideSection('est-viewport');
        _hideSection('est-mobile-preview');
        _hideSection('est-mobile-preview-fallback');
        _mobilePreviewFallbackActive = false;
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
            _lastIsLahom = !!d.is_lahom;
            _lastFactory2 = !!d.factory2;
            _companyInfoVariants = d.company_info_variants || null;
            _paymentInfoVariants = d.payment_info_variants || null;
            _applyCompanyInfo(d.company_info || {}, { isLahom: _lastIsLahom, factory2: _lastFactory2 });
            _applyCustomerInfo(d);
            _renderItems(d.items, d.estimate_preview || {});
            _applyPaymentInfo(d, d.payment_info || {});

            _estimateCacheLoaded = true;
            _dirty = false;
            _setMobilePreviewUrl('');

            const toolbar = document.getElementById('est-toolbar');
            const exportBtn = document.getElementById('btn-est-export');
            const channelPushBtn = document.getElementById('btn-est-channel-push');
            if (toolbar) toolbar.classList.remove('erp-est-hidden');
            if (exportBtn) exportBtn.disabled = false;
            if (channelPushBtn) channelPushBtn.disabled = false;

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
        _paymentInfoVariants = null;
        _companyInfoVariants = null;
        _setMobilePreviewUrl('');
        _mobilePreviewFallbackActive = false;
    };

    // 견적서 캡처 결과를 실제 PNG Blob으로 얻는다(blob: URL 경유로 base64 확장 회피).
    async function _captureEstimateBlob() {
        var url = await _captureEstimateDataUrl({ preferBlobUrl: true });
        if (!url) return null;
        try {
            var resp = await fetch(url);
            var blob = await resp.blob();
            return { blob: blob, url: url };
        } catch (err) {
            if (
                url.indexOf('blob:') === 0
                && typeof URL !== 'undefined'
                && typeof URL.revokeObjectURL === 'function'
            ) {
                URL.revokeObjectURL(url);
            }
            throw err;
        }
    }

    // 견적서 이미지를 채널톡 견적서 방으로 전송한다.
    // 재전송(이전 전송 이력) 시 변경 내용 입력 후 전송하며, 서버 400(재전송 note 필수)
    // 응답 시 클라 상태 동기화 후 modal 1회 재시도(영발/발주 PUSH와 동일 UX).
    async function _runEstimateChannelPush(btn, resendState) {
        const retryState = resendState || { resendRecoveryUsed: false };

        const orderId = _getOrderId();
        // 영발/발주 PUSH와 동일하게 미저장 draft 주문에서는 전송을 막는다.
        // (라이브 DOM 캡처가 저장 데이터와 어긋난 채 채널톡에 전송되는 것을 방지)
        if (
            !orderId
            || (typeof window.erpIsDraftBackedOrder === 'function' && window.erpIsDraftBackedOrder())
        ) {
            if (typeof window.erpCanUsePersistedOrderAction === 'function') {
                window.erpCanUsePersistedOrderAction('견적서 전송은');
            } else {
                alert('주문을 먼저 저장한 후 견적서를 전송할 수 있습니다.');
            }
            return;
        }
        if (!document.getElementById('est-document')) {
            alert('견적서가 로드되지 않았습니다.');
            return;
        }

        let changeNote = retryState.changeNote || null;
        if (
            !changeNote
            && typeof window.erpHasPriorChannelPush === 'function'
            && window.erpHasPriorChannelPush('estimate')
        ) {
            if (typeof window.erpPromptChannelPushResendNote !== 'function') return;
            changeNote = await window.erpPromptChannelPushResendNote('estimate');
            if (!changeNote) return;
        }

        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 전송중...';

        let captured = null;
        try {
            captured = await _captureEstimateBlob();
            if (!captured || !captured.blob || !captured.blob.size) {
                throw new Error('견적서 이미지 생성 실패');
            }

            const form = new FormData();
            form.append('order_id', String(orderId));
            form.append('image', captured.blob, 'estimate.png');
            if (changeNote) form.append('change_note', changeNote);

            const resp = await fetch('/api/channel/push-estimate', { method: 'POST', body: form });
            const data = await resp.json();

            if (data.success) {
                if (typeof window.erpMarkChannelPushSent === 'function') {
                    window.erpMarkChannelPushSent('estimate');
                }
                btn.innerHTML = '<i class="fas fa-check"></i> 전송완료';
                btn.classList.replace('erp-pro-btn--primary', 'erp-pro-btn--success');
                window.setTimeout(function () {
                    btn.innerHTML = originalHtml;
                    btn.classList.replace('erp-pro-btn--success', 'erp-pro-btn--primary');
                    btn.disabled = false;
                }, 3000);
                return;
            }

            const errMsg = data.error || data.message || '알 수 없는 오류';
            if (
                !retryState.resendRecoveryUsed
                && typeof window.erpIsChannelPushResendNoteRequired === 'function'
                && window.erpIsChannelPushResendNoteRequired(errMsg)
            ) {
                if (typeof window.erpMarkChannelPushSent === 'function') {
                    window.erpMarkChannelPushSent('estimate');
                }
                btn.innerHTML = originalHtml;
                btn.disabled = false;
                if (typeof window.erpPromptChannelPushResendNote !== 'function') return;
                const recoveryNote = await window.erpPromptChannelPushResendNote('estimate');
                if (!recoveryNote) return;
                return _runEstimateChannelPush(btn, {
                    resendRecoveryUsed: true,
                    changeNote: recoveryNote,
                });
            }

            alert('채널톡 전송 실패:\n' + errMsg);
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        } catch (err) {
            console.error('[estimate-preview] 견적서 채널톡 전송 실패:', err);
            alert('견적서 전송 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : String(err)));
            btn.innerHTML = originalHtml;
            btn.disabled = false;
        } finally {
            if (
                captured
                && captured.url
                && captured.url.indexOf('blob:') === 0
                && typeof URL !== 'undefined'
                && typeof URL.revokeObjectURL === 'function'
            ) {
                window.setTimeout(function () {
                    URL.revokeObjectURL(captured.url);
                }, 1000);
            }
        }
    }

    function _bindChannelPushBtn() {
        const btn = document.getElementById('btn-est-channel-push');
        if (!btn || btn.dataset.chPushBound === '1') return;
        btn.dataset.chPushBound = '1';
        btn.addEventListener('click', function () {
            _runEstimateChannelPush(btn);
        });
    }

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

                // iOS Safari는 a[download]를 무시하므로(비동기 후 click은 활성화도 소실)
                // 캡처 이미지를 모달로 띄워 길게 눌러 사진에 저장하도록 안내한다.
                if (_isIosLike()) {
                    const imgUrl = await _captureEstimateDataUrl({ preferBlobUrl: false });
                    if (!imgUrl) {
                        throw new Error('이미지 생성 실패');
                    }
                    _openEstimatePreviewModal({
                        dataUrl: imgUrl,
                        hint: '이미지를 길게 눌러 \u0027사진에 저장\u0027을 선택하세요.'
                    });
                    return;
                }

                const dataUrl = await _captureEstimateDataUrl({ preferBlobUrl: true });
                if (!dataUrl) {
                    throw new Error('이미지 생성 실패');
                }

                const link = document.createElement('a');
                link.download = filename;
                link.href = dataUrl;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                if (
                    dataUrl.indexOf('blob:') === 0
                    && typeof URL !== 'undefined'
                    && typeof URL.revokeObjectURL === 'function'
                ) {
                    window.setTimeout(function () {
                        URL.revokeObjectURL(dataUrl);
                    }, 1000);
                }

            } catch (err) {
                console.error('[estimate-preview] 이미지 저장 실패:', err);
                if (_isIosLike()) {
                    _setMobileCaptureFallback(
                        true,
                        'iPhone/Safari에서 이미지 저장용 캡처가 지연되어 원본 견적서를 표시합니다. 화면 캡처 또는 다시 시도를 이용해 주세요.'
                    );
                    return;
                }
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
        _bindChannelPushBtn();
        _bindManualRows();
        _bindEstimateMobilePreview();
        _bindEstimateViewModeListener();

        document.addEventListener('input', function (e) {
            var target = e.target;
            if (!target) return;
            var isErpField = target.dataset && 'erp' in target.dataset;
            var isFreeInputField = target.id === 'erp-free-input-text' || target.id === 'erp-free-input-amount';
            if (isErpField || isFreeInputField) {
                _dirty = true;
                _setMobilePreviewUrl('');
                _mobilePreviewFallbackActive = false;
            }
        }, true);

        tab.addEventListener('shown.bs.tab', async function () {
            if (!_dirty && _estimateCacheLoaded) {
                await _afterEstimateRendered();
                return;
            }

            _estimateCacheLoaded = false;
            _setMobilePreviewUrl('');
            _mobilePreviewFallbackActive = false;
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
