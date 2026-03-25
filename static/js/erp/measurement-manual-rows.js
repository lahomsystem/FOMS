/**
 * 실측 대시보드: 주문 행 사이 수동 입력 행(로컬 전용, DB 미저장).
 * 행 사이 클릭은 별도 갭 <tr> 없이 좌표로만 감지(표 간격 유지).
 * localStorage: erpMeasurementManualRows_v1_{기준일}
 */
(function () {
    'use strict';

    var manualSeqCounter = 0;
    var tbodyRef = null;
    var selectedDateRef = '';

    var BOUNDARY_TOL_PX = 6;

    function storageKey(date) {
        return 'erpMeasurementManualRows_v1_' + String(date || 'nodate');
    }

    function removeGapRows(tbody) {
        tbody.querySelectorAll('tr.measurement-gap-row').forEach(function (r) {
            r.remove();
        });
    }

    function findBlockEndForAnchor(tbody, afterOrderId) {
        var oid = String(afterOrderId || '');
        var main = null;
        tbody.querySelectorAll('tr.measurement-row:not(.measurement-row-manual)').forEach(function (tr) {
            if (String(tr.dataset.orderId) === oid) main = tr;
        });
        if (!main) return tbody.lastElementChild;
        var el = main;
        var n = main.nextElementSibling;
        if (n && n.classList.contains('measurement-detail-row') && String(n.dataset.orderId) === oid) {
            el = n;
            n = el.nextElementSibling;
        }
        while (n && n.classList.contains('measurement-row-manual') && String(n.dataset.afterAnchorOrderId) === oid) {
            el = n;
            n = el.nextElementSibling;
        }
        return el;
    }

    function insertAfter(anchor, node) {
        if (!anchor || !anchor.parentNode) return;
        if (anchor.nextSibling) {
            anchor.parentNode.insertBefore(node, anchor.nextSibling);
        } else {
            anchor.parentNode.appendChild(node);
        }
    }

    function scrapeManualRow(tr) {
        function txt(sel) {
            var el = tr.querySelector(sel);
            return el ? (el.textContent || '').trim() : '';
        }
        return {
            customer: txt('td[data-field="customer"]'),
            orderer: txt('td[data-field="orderer"]'),
            address: txt('td[data-field="address"]'),
            phone: txt('td[data-field="phone"]'),
            measDate: txt('td[data-field="meas_date"]'),
            measTime: txt('td[data-field="meas_time"]'),
            product: txt('td[data-field="product"]'),
            manager: txt('td[data-field="manager"]')
        };
    }

    function persistManualRows() {
        if (!tbodyRef) return;
        var rows = [];
        tbodyRef.querySelectorAll('tr.measurement-row-manual').forEach(function (tr) {
            rows.push({
                id: tr.dataset.manualId,
                manualSeq: parseInt(tr.dataset.manualSeq, 10) || 0,
                afterAnchorOrderId: tr.dataset.afterAnchorOrderId || '',
                fields: scrapeManualRow(tr)
            });
        });
        try {
            localStorage.setItem(storageKey(selectedDateRef), JSON.stringify(rows));
        } catch (e) {
            console.warn('수동 행 로컬 저장 실패:', e);
        }
    }

    function recomputeManualAnchors() {
        if (!tbodyRef) return;
        var lastReal = '';
        Array.from(tbodyRef.children).forEach(function (tr) {
            if (tr.classList.contains('measurement-row') && !tr.classList.contains('measurement-row-manual')) {
                lastReal = String(tr.dataset.orderId || '');
            }
            if (tr.classList.contains('measurement-row-manual')) {
                tr.dataset.afterAnchorOrderId = lastReal;
            }
        });
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    function createManualRowElement(fields, manualId, manualSeq, afterAnchorOrderId, selectedDate) {
        var tr = document.createElement('tr');
        tr.className = 'measurement-row measurement-row-manual';
        tr.dataset.manualRow = 'true';
        tr.dataset.manualId =
            manualId ||
            (typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID()
                : String(Date.now()) + '-' + Math.random());
        tr.dataset.manualSeq = String(manualSeq);
        tr.dataset.afterAnchorOrderId = String(afterAnchorOrderId || '');
        tr.dataset.isErp = 'false';
        tr.dataset.orderId = '';
        tr.dataset.manager = '';

        var fv = fields || {};
        var cust = fv.customer != null && fv.customer !== '' ? fv.customer : '-';
        var orderer = fv.orderer != null && fv.orderer !== '' ? fv.orderer : '-';
        var addr = fv.address != null && fv.address !== '' ? fv.address : '-';
        var phone = fv.phone != null && fv.phone !== '' ? fv.phone : '-';
        var mdate = fv.measDate != null && fv.measDate !== '' ? fv.measDate : '-';
        var mtime = fv.measTime != null && fv.measTime !== '' ? fv.measTime : '-';
        var prod = fv.product != null && fv.product !== '' ? fv.product : '-';
        var mgr = fv.manager != null && fv.manager !== '' ? fv.manager : '-';

        var dateCellHtml;
        if (mdate !== '-' && mdate !== '') {
            dateCellHtml = escapeHtml(mdate);
        } else if (selectedDate) {
            dateCellHtml =
                '<span class="badge bg-secondary me-1">' + escapeHtml(String(selectedDate)) + '</span>';
        } else {
            dateCellHtml = '-';
        }

        tr.innerHTML =
            '<td class="text-center" data-label="상세" style="border-right: 1px solid #e0e0e0;">' +
            '<button type="button" class="btn btn-sm btn-outline-danger measurement-manual-delete" title="수동 행 삭제">' +
            '<i class="fas fa-times"></i></button></td>' +
            '<td data-field="customer" data-label="고객" class="editable-cell" style="border-right: 1px solid #e0e0e0; min-width: 140px;">' +
            escapeHtml(cust) +
            '</td>' +
            '<td data-field="orderer" data-label="발주사" class="editable-cell" style="border-right: 1px solid #e0e0e0;">' +
            escapeHtml(orderer) +
            '</td>' +
            '<td data-field="address" data-label="주소" class="editable-cell cell-wrap measurement-address-cell" style="border-right: 1px solid #e0e0e0;">' +
            escapeHtml(addr) +
            '</td>' +
            '<td data-field="phone" data-label="전화번호" class="editable-cell" style="border-right: 1px solid #e0e0e0;">' +
            escapeHtml(phone) +
            '</td>' +
            '<td data-field="meas_date" data-label="실측일" class="measurement-date-cell" style="border-right: 1px solid #e0e0e0;">' +
            dateCellHtml +
            '</td>' +
            '<td data-field="meas_time" data-label="시간" class="editable-cell" style="border-right: 1px solid #e0e0e0;">' +
            escapeHtml(mtime) +
            '</td>' +
            '<td data-field="product" data-label="제품" class="editable-cell cell-wrap measurement-product-cell" style="border-right: 1px solid #e0e0e0;">' +
            escapeHtml(prod) +
            '</td>' +
            '<td data-field="manager" data-label="담당자" class="editable-cell manager-cell" data-bg="#CCCCCC" data-color="#000000">' +
            escapeHtml(mgr) +
            '</td>';

        return tr;
    }

    /** 메인 행 바로 아래 상세 행(같은 주문) — 이 둘 사이는 삽입 금지(정렬 페어 유지). */
    function isMainDetailPair(prev, next) {
        if (!prev.classList.contains('measurement-row') || prev.classList.contains('measurement-row-manual')) {
            return false;
        }
        if (!next.classList.contains('measurement-detail-row')) return false;
        return String(prev.dataset.orderId || '') === String(next.dataset.orderId || '');
    }

    function visibleDataRows(tbody) {
        return Array.from(tbody.children).filter(function (tr) {
            if (tr.tagName !== 'TR') return false;
            if (tr.classList.contains('measurement-gap-row')) return false;
            if (tr.offsetParent === null) return false;
            return true;
        });
    }

    function anchorOrderIdAfterPrev(prevTr) {
        if (prevTr.classList.contains('measurement-row-manual')) {
            return String(prevTr.dataset.afterAnchorOrderId || '');
        }
        return String(prevTr.dataset.orderId || '');
    }

    function tryInsertAtRowBoundaryClick(tbody, clientX, clientY) {
        var table = tbody.closest('table');
        if (!table) return false;
        var tRect = table.getBoundingClientRect();
        if (clientX < tRect.left || clientX > tRect.right) return false;

        var rows = visibleDataRows(tbody);
        if (rows.length < 2) return false;

        for (var i = 0; i < rows.length - 1; i++) {
            var prev = rows[i];
            var next = rows[i + 1];
            if (isMainDetailPair(prev, next)) continue;

            var pr = prev.getBoundingClientRect();
            var nr = next.getBoundingClientRect();
            var lo = pr.bottom;
            var hi = nr.top;
            var mid = (lo + hi) / 2;
            if (hi < lo) mid = lo;

            var ok =
                Math.abs(clientY - mid) <= BOUNDARY_TOL_PX ||
                (clientY >= lo - BOUNDARY_TOL_PX && clientY <= hi + BOUNDARY_TOL_PX);
            if (!ok) continue;

            manualSeqCounter += 1;
            var anchorId = anchorOrderIdAfterPrev(prev);
            var tr = createManualRowElement({}, null, manualSeqCounter, anchorId, selectedDateRef);
            insertAfter(prev, tr);
            return true;
        }
        return false;
    }

    function initManualRows() {
        var container = document.querySelector('.erp-pro');
        if (!container || container.dataset.erpBetaActive !== 'true') return;

        var tbody = document.querySelector('.measurement-table tbody');
        if (!tbody) return;

        tbodyRef = tbody;
        selectedDateRef = container.dataset.selectedDate || '';

        window.measurementManualRowsRemoveGaps = function () {
            removeGapRows(tbody);
        };
        window.measurementManualRowsPersist = function () {
            persistManualRows();
        };
        window.measurementManualRowsRecomputeAnchors = function () {
            recomputeManualAnchors();
        };

        function scheduleFull() {
            if (typeof window.applyMeasurementManagerSortAndColors === 'function') {
                window.applyMeasurementManagerSortAndColors();
            }
        }

        function loadStored() {
            try {
                var raw = localStorage.getItem(storageKey(selectedDateRef));
                return raw ? JSON.parse(raw) : [];
            } catch (e) {
                return [];
            }
        }

        function restoreFromStorage() {
            var list = loadStored();
            if (!list.length) return;
            var maxSeq = 0;
            list.forEach(function (r) {
                if ((r.manualSeq || 0) > maxSeq) maxSeq = r.manualSeq;
            });
            manualSeqCounter = Math.max(manualSeqCounter, maxSeq);

            list.sort(function (a, b) {
                var ao = String(a.afterAnchorOrderId || '');
                var bo = String(b.afterAnchorOrderId || '');
                if (ao !== bo) return ao.localeCompare(bo);
                return (a.manualSeq || 0) - (b.manualSeq || 0);
            });

            list.forEach(function (rec) {
                var f = rec.fields || {};
                var tr = createManualRowElement(f, rec.id, rec.manualSeq, rec.afterAnchorOrderId, selectedDateRef);
                var anchor = findBlockEndForAnchor(tbody, rec.afterAnchorOrderId);
                insertAfter(anchor, tr);
            });
        }

        /* 캡처 단계: 행 경계 클릭이 measurement.js 인라인 편집(버블)보다 먼저 처리되도록 */
        tbody.addEventListener(
            'click',
            function (e) {
                var del = e.target.closest('.measurement-manual-delete');
                if (del) {
                    e.preventDefault();
                    var tr = del.closest('tr.measurement-row-manual');
                    if (!tr) return;
                    if (!window.confirm('이 수동 행을 삭제할까요?')) return;
                    tr.remove();
                    persistManualRows();
                    scheduleFull();
                    return;
                }

                if (e.target.closest('a, button, input, textarea, select, .measurement-chevron')) return;

                if (tryInsertAtRowBoundaryClick(tbody, e.clientX, e.clientY)) {
                    e.preventDefault();
                    e.stopPropagation();
                    persistManualRows();
                    scheduleFull();
                }
            },
            true
        );

        removeGapRows(tbody);
        restoreFromStorage();
        scheduleFull();
    }

    document.addEventListener('DOMContentLoaded', initManualRows);
})();
