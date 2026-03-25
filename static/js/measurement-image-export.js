/**
 * 실측 대시보드 일정표 PNG 저장 (출고 shipment-image-export.js와 동일 흐름).
 * 파일명·표 제목: YY-MM-DD 실측 일정
 */
document.addEventListener('DOMContentLoaded', function () {
    const exportBtn = document.getElementById('btn-export-image');
    if (!exportBtn) return;

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

    exportBtn.addEventListener('click', async function () {
        const originalText = exportBtn.innerHTML;

        function resetBtn(restoreText) {
            exportBtn.innerHTML = restoreText !== undefined ? restoreText : originalText;
            exportBtn.disabled = false;
        }

        try {
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            exportBtn.disabled = true;

            const tableElement = document.querySelector('.measurement-table');

            if (!tableElement) {
                alert('캡처할 실측 일정이 없습니다.');
                resetBtn(originalText);
                return;
            }

            const dateInput = document.querySelector('input[name="date"]');
            const dateStr = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];
            const labelYyMmDd = toYyMmDd(dateStr);
            const titleText = labelYyMmDd + ' 실측 일정';
            const downloadBase = titleText;

            if (typeof erpTableExportWaitForImages === 'function') {
                await erpTableExportWaitForImages(tableElement);
            }

            const captureScale =
                typeof erpTableExportCaptureScale === 'function' ? erpTableExportCaptureScale() : 3;

            const canvas = await html2canvas(tableElement, {
                scale: captureScale,
                useCORS: true,
                logging: false,
                backgroundColor: '#ffffff',
                onclone: function (clonedDoc) {
                    const clonedTable = clonedDoc.querySelector('.measurement-table');
                    if (!clonedTable) return;

                    clonedTable.style.width = 'auto';
                    clonedTable.style.minWidth = '1100px';

                    if (typeof erpTableExportStylePaymentIconsInClone === 'function') {
                        erpTableExportStylePaymentIconsInClone(clonedDoc, 80);
                    }

                    const thead = clonedTable.querySelector('thead');
                    if (!thead) return;

                    const titleRow = clonedDoc.createElement('tr');
                    const titleCell = clonedDoc.createElement('th');
                    const colCount = thead.querySelectorAll('tr:last-child th').length || 9;
                    titleCell.colSpan = colCount;
                    titleCell.style.textAlign = 'center';
                    titleCell.style.padding = '15px';
                    titleCell.style.fontSize = '20px';
                    titleCell.style.background = '#f8f9fa';
                    titleCell.style.borderBottom = '2px solid #dee2e6';
                    titleCell.textContent = titleText;

                    titleRow.appendChild(titleCell);
                    thead.insertBefore(titleRow, thead.firstChild);
                }
            });

            const link = document.createElement('a');
            link.download = downloadBase + '.png';
            link.href = canvas.toDataURL('image/png');
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            resetBtn(originalText);
        } catch (err) {
            console.error('이미지 저장 실패:', err);
            alert('이미지 저장 중 오류가 발생했습니다.\n' + err.message);
            resetBtn(originalText);
        }
    });
});
