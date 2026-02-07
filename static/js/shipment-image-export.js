document.addEventListener('DOMContentLoaded', function () {
    const exportBtn = document.getElementById('btn-export-image');
    if (!exportBtn) return;

    exportBtn.addEventListener('click', async function () {
        try {
            // 버튼 로딩 상태
            const originalText = exportBtn.innerHTML;
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
            exportBtn.disabled = true;

            // 1. 캡처 대상 설정
            // .table-responsive 안에 .shipment-table이 있음.
            // 테이블 전체를 캡처하기 위해 .shipment-table을 타겟으로 잡음.
            const tableElement = document.querySelector('.shipment-table');

            if (!tableElement) {
                alert('캡처할 배송 일정이 없습니다.');
                resetBtn();
                return;
            }

            // 2. 현재 날짜 정보 가져오기
            const dateInput = document.querySelector('input[name="date"]');
            const dateStr = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];

            // 3. html2canvas 실행
            // 테이블이 스크롤되어 일부만 보일 수 있으므로, 전체를 캡처하기 위해 windowWidth/Height 옵션 등을 고려하거나
            // onclone에서 스타일을 강제 조정해야 함.

            await html2canvas(tableElement, {
                scale: 2, // 고해상도
                useCORS: true,
                logging: false,
                backgroundColor: '#ffffff',
                // 캡처 시점에만 적용될 스타일 및 DOM 조작
                onclone: (clonedDoc) => {
                    const clonedTable = clonedDoc.querySelector('.shipment-table');

                    // 부모 요소(responsive div 등)의 제약에서 벗어나게 스타일 조정
                    // (테이블 자체가 캡처 타겟이므로 부모 스타일링 영향 최소화)
                    clonedTable.style.width = 'auto'; // 내용에 맞게 너비 확장
                    clonedTable.style.minWidth = '1100px'; // 최소 너비 유지

                    // 제목 추가를 위한 컨테이너 생성 (테이블 감싸기)
                    const wrapper = clonedDoc.createElement('div');
                    wrapper.style.padding = '20px';
                    wrapper.style.background = '#fff';
                    wrapper.style.display = 'inline-block'; // 내용물 크기에 맞춤

                    // 테이블을 wrapper로 이동 (부모 교체)
                    clonedTable.parentNode.insertBefore(wrapper, clonedTable);
                    wrapper.appendChild(clonedTable);

                    // 제목 요소 생성
                    const title = clonedDoc.createElement('h2');
                    title.textContent = `${dateStr} 시공 일정`;
                    title.style.textAlign = 'center';
                    title.style.marginBottom = '20px';
                    title.style.color = '#333';
                    title.style.fontFamily = "'Noto Sans KR', sans-serif";
                    title.style.fontSize = '24px';
                    title.style.fontWeight = 'bold';

                    // 제목 삽입
                    wrapper.insertBefore(title, clonedTable);

                    // 캡처 대상 변경 (wrapper 전체를 찍어야 제목 포함됨)
                    // html2canvas는 초기 target을 캡처하므로, target을 wrapper로 바꿀 수는 없음.
                    // 대신 onclone 내부에서 target 자체를 조작하는 것이 좋음.
                    // *중요*: html2canvas는 'target' 요소를 캡처함. onclone에서 target의 부모를 캡처하게 할 수는 없음.
                    // 따라서 전략 변경:
                    // 1. target 요소(.shipment-table) 내부에 caption이나 thead 위에 row를 추가하는 방식 사용
                    // 또는 
                    // 2. 아예 target을 .col-xl-10 등 더 큰 컨테이너로 잡고 불필요한 요소를 숨기는 방식 사용.

                    // 전략 2 수정 적용:
                    // 아래쪽에서 target을 .shipment-table로 잡았으므로,
                    // onclone에서는 .shipment-table의 첫 번째 자식으로 제목 row를 삽입하는 것이 안전함.

                    // thead 찾기
                    const thead = clonedTable.querySelector('thead');
                    if (thead) {
                        const titleRow = clonedDoc.createElement('tr');
                        const titleCell = clonedDoc.createElement('th');
                        // colspan 계산 (헤더 셀 개수)
                        const colCount = thead.querySelectorAll('tr:last-child th').length || 9;
                        titleCell.colSpan = colCount;
                        titleCell.style.textAlign = 'center';
                        titleCell.style.padding = '15px';
                        titleCell.style.fontSize = '20px';
                        titleCell.style.background = '#f8f9fa';
                        titleCell.style.borderBottom = '2px solid #dee2e6';
                        titleCell.textContent = `${dateStr} 시공 일정`;

                        titleRow.appendChild(titleCell);
                        thead.insertBefore(titleRow, thead.firstChild);
                    }
                }
            }).then(canvas => {
                // 4. 다운로드
                const link = document.createElement('a');
                link.download = `시공일정_${dateStr}.png`;
                link.href = canvas.toDataURL('image/png');
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            });

            resetBtn();

        } catch (err) {
            console.error('이미지 저장 실패:', err);
            alert('이미지 저장 중 오류가 발생했습니다.\n' + err.message);
            resetBtn();
        }

        function resetBtn() {
            exportBtn.innerHTML = originalText;
            exportBtn.disabled = false;
        }
    });
});
