/**
 * 시공(출고) 대시보드 일정표 PNG 저장.
 * 파일명·표 제목: YYYY-MM-DD 시공 일정
 *
 * fragment 스왑마다 재실행되지 않도록 shipment-entry.js 가 1회만 로드하고,
 * foms:erp-shell-fragment-swapped 로 재초기화한다(전역 리스너는 __FOMS_SHIP_EXPORT_BOUND 로 1회).
 * 버튼 바인딩은 dataset 가드로 멱등.
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

    function localDateIso() {
        const d = new Date();
        return [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, '0'),
            String(d.getDate()).padStart(2, '0')
        ].join('-');
    }

    function initShipmentImageExport() {
        const exportBtn = document.getElementById('btn-export-image');
        if (!exportBtn || exportBtn.dataset.fomsExportBound === '1') return;
        exportBtn.dataset.fomsExportBound = '1';

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

                await ensureHtml2canvas();

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
    }

    // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(버튼은 dataset 가드로 멱등).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShipmentImageExport);
    } else {
        initShipmentImageExport();
    }
    if (!window.__FOMS_SHIP_EXPORT_BOUND) {
        window.__FOMS_SHIP_EXPORT_BOUND = true;
        document.addEventListener('foms:erp-shell-fragment-swapped', initShipmentImageExport);
    }
})();
