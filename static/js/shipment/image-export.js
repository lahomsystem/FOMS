/**
 * 시공(출고) 대시보드 일정표 PNG 저장.
 * 파일명·표 제목: YYYY-MM-DD 시공 일정
 */
document.addEventListener('DOMContentLoaded', function () {
    const exportBtn = document.getElementById('btn-export-image');
    if (!exportBtn) return;

    function localDateIso() {
        const d = new Date();
        return [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, '0'),
            String(d.getDate()).padStart(2, '0')
        ].join('-');
    }

    exportBtn.addEventListener('click', async function () {
        const originalText = exportBtn.innerHTML;

        try {
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            exportBtn.disabled = true;

            const tableElement = document.querySelector('.shipment-table');

            if (!tableElement) {
                alert('캡처할 시공 일정이 없습니다.');
                return;
            }

            const captureScale = 2; // 적절한 화질과 속도를 위해 2배수로 고정

            const dateInput = document.querySelector('input[name="date"]');
            const dateStr = dateInput ? dateInput.value : localDateIso();
            const titleText = `${dateStr} 시공 일정`;

            const canvas = await html2canvas(tableElement, {
                scale: captureScale,
                useCORS: true,
                logging: false,
                backgroundColor: '#ffffff',
                onclone: (clonedDoc) => {
                    const clonedTable = clonedDoc.querySelector('.shipment-table');
                    if (!clonedTable) return;

                    clonedTable.style.width = 'auto';
                    clonedTable.style.minWidth = '1100px';

                    const thead = clonedTable.querySelector('thead');
                    if (thead) {
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
                }
            });

            const link = document.createElement('a');
            link.download = `시공일정_${dateStr}.png`;
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
