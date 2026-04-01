/**
 * 실측 대시보드 일정표 PNG 저장.
 * 파일명·표 제목: YY-MM-DD 실측 일정
 */
document.addEventListener('DOMContentLoaded', function () {
    const exportBtn = document.getElementById('btn-export-image');
    if (!exportBtn) return;
    const EXPORT_TABLE_WIDTH = 1500;
    const EXPORT_MIN_COLUMN_WIDTHS = {
        detail: 48,
        customer: 86,
        orderer: 86,
        phone: 126,
        meas_time: 94,
        manager: 110
    };
    const EXPORT_EXPANDED_COLUMNS = ['address', 'product'];
    const EXPORT_GROUP_BORDER_COLOR = '#4b5563';
    const EXPORT_GROUP_BORDER_WIDTH = '3px';

    /**
     * @param {string} isoDateStr - YYYY-MM-DD
     * @returns {string} YY-MM-DD
     */
    function toYyMmDd(isoDateStr) {
        const parts = String(isoDateStr || '').trim().split('-');
        if (parts.length !== 3) {
            const d = new Date();
            const y = String(d.getFullYear()).slice(-2);
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return y + '-' + m + '-' + day;
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
            const d = new Date();
            return d.getFullYear() + '년 ' + (d.getMonth() + 1) + '월 ' + d.getDate() + '일';
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

        const remainingWidth = Math.max(720, EXPORT_TABLE_WIDTH - fixedWidth);
        const addressWidth = Math.round(remainingWidth * 0.46);
        const productWidth = remainingWidth - addressWidth;

        return {
            detail: EXPORT_MIN_COLUMN_WIDTHS.detail,
            customer: EXPORT_MIN_COLUMN_WIDTHS.customer,
            orderer: EXPORT_MIN_COLUMN_WIDTHS.orderer,
            address: addressWidth,
            phone: EXPORT_MIN_COLUMN_WIDTHS.phone,
            meas_time: EXPORT_MIN_COLUMN_WIDTHS.meas_time,
            product: productWidth,
            manager: EXPORT_MIN_COLUMN_WIDTHS.manager
        };
    }

    /**
     * @param {string} text
     * @param {number} rowIndex
     * @returns {string}
     */
    function normalizeManagerGroupKey(text, rowIndex) {
        const value = String(text || '').trim();
        if (!value || value === '-') {
            return '__ungrouped_' + rowIndex;
        }
        return value.toLowerCase();
    }

    /**
     * @param {HTMLTableElement} clonedTable
     */
    function applyManagerGroupStyles(clonedTable) {
        const rows = Array.from(clonedTable.querySelectorAll('tbody tr'));
        if (!rows.length) return;

        let groupStart = 0;

        function paintGroup(startIndex, endIndex) {
            for (let rowIndex = startIndex; rowIndex <= endIndex; rowIndex += 1) {
                const row = rows[rowIndex];
                const cells = Array.from(row.querySelectorAll('td'));
                if (!cells.length) continue;

                const isFirstRow = rowIndex === startIndex;
                const isLastRow = rowIndex === endIndex;
                const firstCell = cells[0];
                const lastCell = cells[cells.length - 1];

                if (firstCell) {
                    firstCell.style.borderLeftWidth = EXPORT_GROUP_BORDER_WIDTH;
                    firstCell.style.borderLeftColor = EXPORT_GROUP_BORDER_COLOR;
                }
                if (lastCell) {
                    lastCell.style.borderRightWidth = EXPORT_GROUP_BORDER_WIDTH;
                    lastCell.style.borderRightColor = EXPORT_GROUP_BORDER_COLOR;
                }

                if (isFirstRow) {
                    cells.forEach(function (cell) {
                        cell.style.borderTopWidth = EXPORT_GROUP_BORDER_WIDTH;
                        cell.style.borderTopColor = EXPORT_GROUP_BORDER_COLOR;
                    });
                }

                if (isLastRow) {
                    cells.forEach(function (cell) {
                        cell.style.borderBottomWidth = EXPORT_GROUP_BORDER_WIDTH;
                        cell.style.borderBottomColor = EXPORT_GROUP_BORDER_COLOR;
                    });
                }
            }
        }

        for (let index = 1; index <= rows.length; index += 1) {
            const prevRow = rows[index - 1];
            const currentRow = rows[index];
            const prevManagerCell = prevRow ? prevRow.querySelector('.manager-cell') : null;
            const currentManagerCell = currentRow ? currentRow.querySelector('.manager-cell') : null;
            const prevKey = normalizeManagerGroupKey(prevManagerCell ? prevManagerCell.textContent : '', index - 1);
            const currentKey = currentRow ? normalizeManagerGroupKey(currentManagerCell ? currentManagerCell.textContent : '', index) : '';

            if (!currentRow || currentKey !== prevKey) {
                paintGroup(groupStart, index - 1);
                groupStart = index;
            }
        }
    }

    /**
     * @param {Document} clonedDoc
     * @param {HTMLTableElement} clonedTable
     * @param {string} titleText
     */
    function prepareExportTable(clonedDoc, clonedTable, titleText) {
        clonedDoc.querySelectorAll('tr.measurement-gap-row, tr.measurement-detail-row').forEach(function (row) {
            row.remove();
        });

        clonedTable.classList.remove('table-sm', 'table-hover');
        clonedTable.style.width = EXPORT_TABLE_WIDTH + 'px';
        clonedTable.style.minWidth = EXPORT_TABLE_WIDTH + 'px';
        clonedTable.style.maxWidth = EXPORT_TABLE_WIDTH + 'px';
        clonedTable.style.tableLayout = 'fixed';
        clonedTable.style.borderCollapse = 'collapse';
        clonedTable.style.backgroundColor = '#ffffff';
        clonedTable.style.border = '2px solid #111827';
        clonedTable.style.fontSize = '15px';
        clonedTable.style.lineHeight = '1.35';

        removeExportColumn(clonedTable, 'measurement_date');

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
            titleCell.style.fontSize = '32px';
            titleCell.style.fontWeight = '800';
            titleCell.style.letterSpacing = '0.18em';
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
            cell.style.fontSize = '15px';
            cell.style.fontWeight = '800';
            cell.style.padding = '10px 8px';
            cell.style.textAlign = 'center';
            cell.style.verticalAlign = 'middle';
            cell.style.whiteSpace = 'nowrap';
        });

        const bodyRows = Array.from(clonedTable.querySelectorAll('tbody tr'));
        bodyRows.forEach(function (row, index) {
            const cells = row.querySelectorAll('td');
            cells.forEach(function (cell) {
                cell.style.border = '1px solid #111827';
                cell.style.padding = '9px 8px';
                cell.style.fontSize = '15px';
                cell.style.fontWeight = '600';
                cell.style.color = cell.style.color || '#111827';
                cell.style.verticalAlign = 'middle';
                cell.style.textAlign = 'center';
                cell.style.whiteSpace = 'nowrap';
                cell.style.backgroundClip = 'padding-box';
            });

            const detailCell = cells[0];
            if (detailCell) {
                detailCell.textContent = String(index + 1);
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

        clonedTable.querySelectorAll('.measurement-address-cell, .measurement-product-cell').forEach(function (cell) {
            cell.style.textAlign = 'left';
            cell.style.whiteSpace = 'normal';
            cell.style.wordBreak = 'keep-all';
            cell.style.lineHeight = '1.4';
        });

        EXPORT_EXPANDED_COLUMNS.forEach(function (colKey) {
            const header = clonedTable.querySelector('thead tr:last-child th[data-col-key="' + colKey + '"]');
            if (header) {
                header.style.textAlign = 'center';
            }
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
        });

        applyManagerGroupStyles(clonedTable);
    }

    exportBtn.addEventListener('click', async function () {
        const originalText = exportBtn.innerHTML;

        try {
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            exportBtn.disabled = true;

            const tableElement = document.querySelector('.measurement-table');

            if (!tableElement) {
                alert('캡처할 실측 일정이 없습니다.');
                return;
            }

            const dateInput = document.querySelector('input[name="date"]');
            const dateStr = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
            const labelYyMmDd = toYyMmDd(dateStr);
            const titleText = toKoreanDateLabel(dateStr) + ' 실측 일정';

            const captureScale = Math.max(2, Math.min(window.devicePixelRatio || 1, 3));

            const canvas = await html2canvas(tableElement, {
                scale: captureScale,
                useCORS: true,
                logging: false,
                backgroundColor: '#ffffff',
                onclone: function (clonedDoc) {
                    const clonedTable = clonedDoc.querySelector('.measurement-table');
                    if (!clonedTable) return;
                    prepareExportTable(clonedDoc, clonedTable, titleText);
                }
            });

            const link = document.createElement('a');
            link.download = labelYyMmDd + ' 실측 일정.png';
            link.href = canvas.toDataURL('image/png');
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (err) {
            console.error('이미지 저장 실패:', err);
            alert('이미지 저장 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : String(err)));
        } finally {
            exportBtn.innerHTML = originalText;
            exportBtn.disabled = false;
        }
    });
});
