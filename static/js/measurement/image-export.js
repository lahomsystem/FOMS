/**
 * 실측 대시보드 일정표 PNG 저장.
 * 파일명·표 제목: YY-MM-DD 실측 일정
 */
(function () {
    var HTML2CANVAS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    var _html2canvasPromise = null;

    /**
     * html2canvas는 PNG 저장 클릭 시에만 필요 → 첫 사용 1회 동적 로드 (perf guard G2).
     * @returns {Promise<void>}
     */
    function ensureHtml2canvas() {
        if (typeof window.html2canvas === 'function') return Promise.resolve();
        if (_html2canvasPromise) return _html2canvasPromise;
        _html2canvasPromise = new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = HTML2CANVAS_SRC;
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

    const EXPORT_TABLE_WIDTH = 1520;
    const EXPORT_TITLE_FONT_SIZE = '38px';
    const EXPORT_HEADER_FONT_SIZE = '15px';
    const EXPORT_BODY_FONT_SIZE = '20px';
    const EXPORT_MIN_COLUMN_WIDTHS = {
        detail: 40,
        customer: 72,
        orderer: 72,
        phone: 124,
        meas_time: 86,
        product: 320,
        manager: 90
    };
    const EXPORT_EXPANDED_COLUMNS = ['address'];
    /** PNG 전용: 담당자 그룹 사이만 넣는 여백(같은 담당자 연속 행 사이에는 없음) */
    const EXPORT_ASSIGNEE_GROUP_GAP_HEIGHT = '14px';

    function localDateIso() {
        const d = new Date();
        return [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, '0'),
            String(d.getDate()).padStart(2, '0')
        ].join('-');
    }

    /**
     * 클론된 행에서 담당자 비교용 키 (measurement.js 의 normalizeManagerKey 와 동일 규칙)
     * @param {HTMLTableRowElement} tr
     * @returns {string}
     */
    function normalizeExportManagerKey(tr) {
        const cell = tr.querySelector('td.manager-cell');
        const raw = cell ? String(cell.textContent || '').trim() : '';
        if (!raw || raw === '-') return '';
        return raw.toLowerCase();
    }

    /**
     * 이미지 저장용: 담당자가 바뀔 때만 얇은 간격 행 삽입. 동일 담당자 사이에는 삽입하지 않음.
     * @param {Document} clonedDoc
     * @param {HTMLTableElement} tableEl
     * @param {number} colSpan
     */
    function insertExportAssigneeGroupGaps(clonedDoc, tableEl, colSpan) {
        const tbody = tableEl.querySelector('tbody');
        if (!tbody) return;
        tbody.querySelectorAll('tr.measurement-export-assignee-gap').forEach(function (r) {
            r.remove();
        });
        const mainRows = Array.from(tbody.querySelectorAll('tr.measurement-row'));
        let prevKey = null;
        mainRows.forEach(function (tr) {
            const key = normalizeExportManagerKey(tr);
            if (prevKey !== null && key !== prevKey) {
                const gap = clonedDoc.createElement('tr');
                gap.className = 'measurement-export-assignee-gap';
                gap.setAttribute('aria-hidden', 'true');
                const td = clonedDoc.createElement('td');
                td.colSpan = colSpan;
                gap.appendChild(td);
                tbody.insertBefore(gap, tr);
            }
            prevKey = key;
        });
    }

    /**
     * @param {string} isoDateStr - YYYY-MM-DD
     * @returns {string} YY-MM-DD
     */
    function toYyMmDd(isoDateStr) {
        const parts = String(isoDateStr || '').trim().split('-');
        if (parts.length !== 3) {
            return toYyMmDd(localDateIso());
        }
        const yy = String(parts[0]).slice(-2);
        return yy + '-' + parts[1] + '-' + parts[2];
    }

    /**
     * @param {string} isoDateStr - YYYY-MM-DD
     * @returns {string} YYYY년 M월 D일
     */
    function toKoreanDateLabel(isoDateStr) {
        const parts = String(isoDateStr || '').trim().split('-');
        if (parts.length !== 3) {
            return toKoreanDateLabel(localDateIso());
        }
        return Number(parts[0]) + '년 ' + Number(parts[1]) + '월 ' + Number(parts[2]) + '일';
    }

    /**
     * @param {Element} tableEl
     * @param {string} colKey
     * @param {number} widthPx
     */
    function setExportColumnWidth(tableEl, colKey, widthPx) {
        const col = tableEl.querySelector('colgroup col[data-col-key="' + colKey + '"]');
        const th = tableEl.querySelector('thead tr:last-child th[data-col-key="' + colKey + '"]');
        const widthValue = Math.round(widthPx) + 'px';

        if (col) {
            col.style.width = widthValue;
        }
        if (th) {
            th.style.width = widthValue;
            th.style.minWidth = widthValue;
            th.style.maxWidth = widthValue;
        }
    }

    /**
     * @param {HTMLTableElement} tableEl
     * @param {string} colKey
     */
    function removeExportColumn(tableEl, colKey) {
        const headerRow = tableEl.querySelector('thead tr:last-child');
        if (!headerRow) return;

        const targetHeader = headerRow.querySelector('th[data-col-key="' + colKey + '"]');
        if (!targetHeader) return;

        const headerCells = Array.from(headerRow.children);
        const columnIndex = headerCells.indexOf(targetHeader);
        if (columnIndex < 0) return;

        const targetCol = tableEl.querySelector('colgroup col[data-col-key="' + colKey + '"]');
        if (targetCol) {
            targetCol.remove();
        }

        targetHeader.remove();

        tableEl.querySelectorAll('tbody tr').forEach(function (row) {
            const cells = row.querySelectorAll('td');
            if (cells[columnIndex]) {
                cells[columnIndex].remove();
            }
        });
    }

    /**
     * @returns {Record<string, number>}
     */
    function buildExportColumnWidths() {
        let fixedWidth = 0;
        Object.keys(EXPORT_MIN_COLUMN_WIDTHS).forEach(function (key) {
            fixedWidth += EXPORT_MIN_COLUMN_WIDTHS[key];
        });

        const remainingWidth = Math.max(760, EXPORT_TABLE_WIDTH - fixedWidth);

        return {
            detail: EXPORT_MIN_COLUMN_WIDTHS.detail,
            customer: EXPORT_MIN_COLUMN_WIDTHS.customer,
            orderer: EXPORT_MIN_COLUMN_WIDTHS.orderer,
            address: remainingWidth,
            phone: EXPORT_MIN_COLUMN_WIDTHS.phone,
            meas_time: EXPORT_MIN_COLUMN_WIDTHS.meas_time,
            product: EXPORT_MIN_COLUMN_WIDTHS.product,
            manager: EXPORT_MIN_COLUMN_WIDTHS.manager
        };
    }

    /**
     * @param {Document} clonedDoc
     * @param {HTMLTableElement} clonedTable
     * @param {string} titleText
     */
    function prepareExportTable(clonedDoc, clonedTable, titleText) {
        clonedDoc
            .querySelectorAll(
                'tr.measurement-gap-row, tr.measurement-detail-row, tr.measurement-manager-group-gap'
            )
            .forEach(function (row) {
                row.remove();
            });

        /* Bootstrap .table 은 캔버스 래스터 시 인접 셀 테두리가 겹쳐 보이거나 흰 틈이 생길 수 있어 제거 */
        clonedTable.classList.remove('table', 'table-sm', 'table-hover', 'align-middle');
        clonedTable.style.width = EXPORT_TABLE_WIDTH + 'px';
        clonedTable.style.minWidth = EXPORT_TABLE_WIDTH + 'px';
        clonedTable.style.maxWidth = EXPORT_TABLE_WIDTH + 'px';
        clonedTable.style.tableLayout = 'fixed';
        clonedTable.style.borderCollapse = 'collapse';
        clonedTable.style.borderSpacing = '0';
        clonedTable.style.backgroundColor = '#ffffff';
        clonedTable.style.border = '2px solid #111827';
        clonedTable.style.fontSize = EXPORT_BODY_FONT_SIZE;
        clonedTable.style.lineHeight = '1.35';

        var headColCount =
            clonedTable.querySelectorAll('thead tr:last-child th').length || 8;
        insertExportAssigneeGroupGaps(clonedDoc, clonedTable, headColCount);

        const exportWidths = buildExportColumnWidths();
        Object.keys(exportWidths).forEach(function (key) {
            setExportColumnWidth(clonedTable, key, exportWidths[key]);
        });

        const thead = clonedTable.querySelector('thead');
        if (thead) {
            const titleRow = clonedDoc.createElement('tr');
            const titleCell = clonedDoc.createElement('th');
            const colCount = thead.querySelectorAll('tr:last-child th').length || 9;

            titleCell.colSpan = colCount;
            titleCell.textContent = titleText;
            titleCell.style.padding = '18px 14px';
            titleCell.style.fontSize = EXPORT_TITLE_FONT_SIZE;
            titleCell.style.fontWeight = '900';
            titleCell.style.letterSpacing = '0.12em';
            titleCell.style.textAlign = 'center';
            titleCell.style.backgroundColor = '#ffffff';
            titleCell.style.border = '2px solid #111827';
            titleCell.style.borderBottom = '0';

            titleRow.appendChild(titleCell);
            thead.insertBefore(titleRow, thead.firstChild);
        }

        const headerCells = clonedTable.querySelectorAll('thead tr:last-child th');
        headerCells.forEach(function (cell) {
            cell.style.backgroundColor = '#f3f4f6';
            cell.style.border = '1px solid #111827';
            cell.style.color = '#111827';
            cell.style.fontSize = EXPORT_HEADER_FONT_SIZE;
            cell.style.fontWeight = '800';
            cell.style.padding = '10px 8px';
            cell.style.textAlign = 'center';
            cell.style.verticalAlign = 'middle';
            cell.style.whiteSpace = 'nowrap';
        });

        const lineColor = '#111827';
        const bodyRows = Array.from(clonedTable.querySelectorAll('tbody tr'));
        var exportDataRowIndex = 0;
        bodyRows.forEach(function (row) {
            if (row.classList.contains('measurement-export-assignee-gap')) {
                row.querySelectorAll('td').forEach(function (cell) {
                    cell.style.height = EXPORT_ASSIGNEE_GROUP_GAP_HEIGHT;
                    cell.style.padding = '0';
                    cell.style.border = 'none';
                    cell.style.borderBottom = '1px solid ' + lineColor;
                    cell.style.backgroundColor = '#ffffff';
                    cell.style.lineHeight = '0';
                });
                return;
            }
            exportDataRowIndex += 1;
            const cells = row.querySelectorAll('td');
            cells.forEach(function (cell, idx) {
                /*
                 * html2canvas 는 td 네 면에 border 를 주면 행 사이에 이중선·흰 간극처럼 보이는 경우가 많다.
                 * 엑셀처럼 한 줄만 보이게: 가로는 bottom 만, 세로는 좌측열에 left + 각 셀 right 로 겹침 최소화.
                 */
                cell.style.border = 'none';
                cell.style.borderBottom = '1px solid ' + lineColor;
                cell.style.borderRight = '1px solid ' + lineColor;
                if (idx === 0) {
                    cell.style.borderLeft = '1px solid ' + lineColor;
                }
                cell.style.padding = '10px 8px';
                cell.style.fontSize = EXPORT_BODY_FONT_SIZE;
                cell.style.fontWeight = '600';
                cell.style.color = cell.style.color || '#111827';
                cell.style.verticalAlign = 'middle';
                cell.style.textAlign = 'center';
                cell.style.whiteSpace = 'nowrap';

                /*
                 * 실측 시간 셀 배경(오전/오후/종일)은 페이지 <style> 의 속성 선택자로 칠해지고
                 * data-daypart 속성은 cloneNode로 그대로 보존된다. 캡처 직전 계산값을 인라인으로
                 * 굳혀 렌더링 경로 차이에 안전하게 대비한다(담당자 셀 data-bg 복원과 동일 취지).
                 * hex 하드코딩 대신 클론 문서 자체의 계산값을 사용해 CSS와 중복 정의하지 않는다.
                 */
                if (cell.classList.contains('meas-time-cell') && cell.dataset.daypart) {
                    const win = clonedDoc.defaultView;
                    const computedBg = win ? win.getComputedStyle(cell).backgroundColor : '';
                    if (computedBg) cell.style.backgroundColor = computedBg;
                }
            });

            const detailCell = cells[0];
            if (detailCell) {
                detailCell.textContent = String(exportDataRowIndex);
                detailCell.style.fontWeight = '700';
            }

            const customerCell = cells[1];
            if (customerCell) {
                customerCell.querySelectorAll('.erp-payment-badge-row, .measurement-chevron').forEach(function (node) {
                    node.remove();
                });
            }
        });

        const detailHeader = clonedTable.querySelector('thead tr:last-child th[data-col-key="detail"]');
        if (detailHeader) {
            detailHeader.textContent = '번호';
        }

        clonedTable.querySelectorAll('.measurement-address-cell').forEach(function (cell) {
            cell.style.textAlign = 'left';
            cell.style.whiteSpace = 'nowrap';
            cell.style.wordBreak = 'normal';
            cell.style.lineHeight = '1.3';
            cell.style.fontSize = EXPORT_BODY_FONT_SIZE;
            cell.style.overflow = 'hidden';
        });

        EXPORT_EXPANDED_COLUMNS.forEach(function (colKey) {
            const header = clonedTable.querySelector('thead tr:last-child th[data-col-key="' + colKey + '"]');
            if (header) {
                header.style.textAlign = 'center';
            }
        });

        clonedTable.querySelectorAll('.measurement-product-cell').forEach(function (cell) {
            cell.style.textAlign = 'left';
            cell.style.whiteSpace = 'normal';
            cell.style.wordBreak = 'keep-all';
            cell.style.lineHeight = '1.35';
            cell.style.fontSize = EXPORT_BODY_FONT_SIZE;
        });

        clonedTable.querySelectorAll('.manager-cell').forEach(function (cell) {
            if (!cell.style.backgroundColor && cell.dataset.bg) {
                cell.style.backgroundColor = cell.dataset.bg;
            }
            if (!cell.style.color && cell.dataset.color) {
                cell.style.color = cell.dataset.color;
            }
            cell.style.fontWeight = '800';
            cell.style.letterSpacing = '0.02em';
            cell.style.fontSize = EXPORT_BODY_FONT_SIZE;
        });
    }

    /** 모바일 2단계 공유: 캡처가 길어 사용자 탭 효력이 끝났을 때(NotAllowedError) 한 번 더 눌러 공유한다. */
    const PENDING_SHARE_TTL_MS = 60000;
    const SHARE_READY_LABEL = '<i class="fas fa-share-from-square" aria-hidden="true"></i> 눌러서 공유';
    var pendingShare = null;

    /**
     * 표 제목·파일명 날짜.
     * - PC: 첫 input[name="date"] 값, 없으면 오늘(기존 규칙 그대로).
     * - 모바일 글랜스: 서버가 표를 그린 날짜(section[data-meas-glance-date]). 필터 서랍에서 바꾸고
     *   아직 적용하지 않은 입력값(.value)을 읽으면 제목·파일명이 표의 행과 어긋난다. 비어 있으면
     *   입력의 서버 렌더 값(defaultValue), 그것도 없으면 오늘.
     * @param {string} mode - 'pc' | 'glance'
     * @returns {{labelYyMmDd: string, titleText: string}}
     */
    function resolveExportDate(mode) {
        const dateInput = document.querySelector('input[name="date"]');
        let dateStr;
        if (mode === 'glance') {
            const panel = document.querySelector('[data-meas-glance]');
            const panelDate = panel ? panel.getAttribute('data-meas-glance-date') : '';
            dateStr = panelDate || (dateInput ? dateInput.defaultValue : '') || localDateIso();
        } else {
            dateStr = dateInput ? dateInput.value : localDateIso();
        }
        return {
            labelYyMmDd: toYyMmDd(dateStr),
            titleText: toKoreanDateLabel(dateStr) + ' 실측 일정'
        };
    }

    /**
     * @param {HTMLCanvasElement} canvas
     * @param {string} filename
     */
    function downloadCanvasPng(canvas, filename) {
        const link = document.createElement('a');
        link.download = filename;
        link.href = canvas.toDataURL('image/png');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    /** @param {File} file */
    function downloadFile(file) {
        const url = URL.createObjectURL(file);
        const link = document.createElement('a');
        link.download = file.name;
        link.href = url;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }

    /** iOS Safari 캔버스 최대 면적(px). */
    const IOS_CANVAS_MAX_AREA = 16777216;

    /**
     * 모바일 캡처 배율: min(2, sqrt(한도 / (w*h))). 크기는 살아 있는 문서가 아니라 버리는 복제본을
     * 화면 밖 호스트에서 prepareExportTable 로 PNG 와 같은 모양으로 만든 뒤 잰다.
     * @param {HTMLTableElement} sourceTable
     * @param {string} titleText
     * @returns {number}
     */
    function measureOffscreenScale(sourceTable, titleText) {
        const probeHost = document.createElement('div');
        probeHost.className = 'foms-meas-export-host erp-pro';
        probeHost.setAttribute('aria-hidden', 'true');
        const probe = sourceTable.cloneNode(true);
        probe.removeAttribute('id');
        probeHost.appendChild(probe);
        document.body.appendChild(probeHost);
        try {
            // prepareExportTable 은 문서 전체에서 행을 지운다 — 살아 있는 문서 대신 호스트로 범위를 좁힌 가짜 문서를 준다.
            const probeDoc = {
                querySelectorAll: function (sel) { return probeHost.querySelectorAll(sel); },
                createElement: function (tag) { return document.createElement(tag); },
                defaultView: window
            };
            prepareExportTable(probeDoc, probe, titleText);
            const rect = probe.getBoundingClientRect();
            const area = Math.max(1, rect.width) * Math.max(1, rect.height);
            return Math.min(2, Math.sqrt(IOS_CANVAS_MAX_AREA / area));
        } catch (err) {
            console.warn('캡처 크기 측정 실패, 배율 1 로 저장:', err);
            return 1;
        } finally {
            if (probeHost.parentNode) probeHost.parentNode.removeChild(probeHost);
        }
    }

    /**
     * 보이는 표(PC)는 그대로, 숨은 표(모바일)는 body 밑 화면 밖 호스트의 복제본을 찍는다.
     * onclone 은 표식(data-meas-export-target)으로 대상을 찾는다.
     * @param {HTMLTableElement} sourceTable
     * @param {string} titleText
     * @returns {Promise<HTMLCanvasElement>}
     */
    async function captureMeasurementTable(sourceTable, titleText) {
        const offscreen = sourceTable.getClientRects().length === 0;
        let target = sourceTable;
        let host = null;
        if (offscreen) {
            host = document.createElement('div');
            host.className = 'foms-meas-export-host erp-pro';
            host.setAttribute('aria-hidden', 'true');
            target = sourceTable.cloneNode(true);
            target.removeAttribute('id');
            host.appendChild(target);
            document.body.appendChild(host);
        }
        target.setAttribute('data-meas-export-target', '1');
        try {
            // PC 공식은 그대로. offscreen(모바일)만 iOS 캔버스 면적 한도(16,777,216px) 안으로 줄인다
            // — 의도된 예외(브리프 §5): 행이 많으면 모바일 PNG 해상도가 PC 보다 낮다.
            const captureScale = offscreen
                ? measureOffscreenScale(sourceTable, titleText)
                : Math.max(2, Math.min(window.devicePixelRatio || 1, 3));
            await ensureHtml2canvas();
            return await html2canvas(target, {
                scale: captureScale,
                useCORS: true,
                logging: false,
                backgroundColor: '#ffffff',
                onclone: function (clonedDoc) {
                    const clonedTable = clonedDoc.querySelector('[data-meas-export-target]');
                    if (!clonedTable) return;
                    const clonedHost = clonedTable.closest('.foms-meas-export-host');
                    if (clonedHost) clonedHost.classList.add('is-capturing');
                    prepareExportTable(clonedDoc, clonedTable, titleText);
                }
            });
        } finally {
            target.removeAttribute('data-meas-export-target');
            if (host && host.parentNode) host.parentNode.removeChild(host);
        }
    }

    /**
     * @param {HTMLElement} btn
     * @param {File} file
     */
    function armPendingShare(btn, file) {
        pendingShare = { btn: btn, file: file, until: Date.now() + PENDING_SHARE_TTL_MS, label: null };
    }

    /**
     * 모바일: 공유창(사진 저장·카카오톡). 취소는 조용히, 탭 효력 만료는 2단계, 그 밖은 다운로드.
     * @returns {Promise<string>} 'armed' | 'done'
     */
    async function shareOrDownloadPng(canvas, filename, btn) {
        const blob = await new Promise(function (resolve) { canvas.toBlob(resolve, 'image/png'); });
        if (!blob) {
            downloadCanvasPng(canvas, filename);
            return 'done';
        }
        const file = new File([blob], filename, { type: 'image/png' });
        if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
            try {
                await navigator.share({ files: [file] });
                return 'done';
            } catch (err) {
                if (err && err.name === 'AbortError') return 'done';
                if (err && err.name === 'NotAllowedError') {
                    armPendingShare(btn, file);
                    return 'armed';
                }
                console.warn('공유 실패, 다운로드로 대체:', err);
            }
        }
        downloadCanvasPng(canvas, filename);
        return 'done';
    }

    /** @param {HTMLElement} btn */
    async function sharePendingFile(btn) {
        const pending = pendingShare;
        pendingShare = null;
        try {
            await navigator.share({ files: [pending.file] });
        } catch (err) {
            if (!(err && err.name === 'AbortError')) downloadFile(pending.file);
        } finally {
            if (pending.label !== null) btn.innerHTML = pending.label;
        }
    }

    /**
     * @param {HTMLElement} btn
     * @param {string} mode - 'pc' | 'glance'
     */
    async function runExport(btn, mode) {
        if (pendingShare && pendingShare.btn === btn) {
            if (Date.now() <= pendingShare.until) {
                await sharePendingFile(btn);
                return;
            }
            if (pendingShare.label !== null) btn.innerHTML = pendingShare.label;
            pendingShare = null;
        }
        const originalText = btn.innerHTML;
        let armed = false;

        try {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            btn.disabled = true;

            const sourceTable = document.querySelector('.measurement-table');

            if (!sourceTable) {
                alert('캡처할 실측 일정이 없습니다.');
                return;
            }
            if (mode === 'glance' && sourceTable.querySelectorAll('tr.measurement-row').length === 0) {
                alert('캡처할 실측 일정이 없습니다.');
                return;
            }

            const exportDate = resolveExportDate(mode);
            const canvas = await captureMeasurementTable(sourceTable, exportDate.titleText);
            const filename = exportDate.labelYyMmDd + ' 실측 일정.png';

            if (mode === 'glance') {
                armed = (await shareOrDownloadPng(canvas, filename, btn)) === 'armed';
            } else {
                downloadCanvasPng(canvas, filename);
            }
        } catch (err) {
            console.error('이미지 저장 실패:', err);
            alert('이미지 저장 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : String(err)));
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
            if (armed && pendingShare && pendingShare.btn === btn) {
                const armedShare = pendingShare;
                armedShare.label = originalText;
                btn.innerHTML = SHARE_READY_LABEL;
                setTimeout(function () {
                    if (pendingShare === armedShare) {
                        pendingShare = null;
                        btn.innerHTML = originalText;
                    }
                }, PENDING_SHARE_TTL_MS);
            }
        }
    }

    function initMeasurementImageExport() {
        const exportBtn = document.getElementById('btn-export-image');
        if (exportBtn && exportBtn.dataset.fomsExportBound !== '1') {
            exportBtn.dataset.fomsExportBound = '1';
            exportBtn.addEventListener('click', function () { runExport(exportBtn, 'pc'); });
        }
        document.querySelectorAll('[data-meas-export-image]').forEach(function (btn) {
            if (btn.dataset.fomsExportBound === '1') return;
            btn.dataset.fomsExportBound = '1';
            btn.addEventListener('click', function () { runExport(btn, 'glance'); });
        });
    }

    // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(표준 이벤트로 통일).
    // 버튼 바인딩은 exportBtn.dataset.fomsExportBound 로 per-DOM 가드(스왑 시 새 버튼이라 재바인딩).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMeasurementImageExport);
    } else {
        initMeasurementImageExport();
    }
    if (!window.__FOMS_MEAS_IMAGE_EXPORT_BOUND) {
        window.__FOMS_MEAS_IMAGE_EXPORT_BOUND = true;
        document.addEventListener('foms:erp-shell-fragment-swapped', initMeasurementImageExport);
    }
})();
