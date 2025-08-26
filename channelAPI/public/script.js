// Socket.IO 연결
const socket = io();

// DOM 요소들
const elements = {
    // 상태 표시
    connectionIndicator: document.getElementById('connection-indicator'),
    
    // 검색 폼
    startDateInput: document.getElementById('start-date'),
    maxChatsInput: document.getElementById('max-chats'),
    
    // 버튼들
    searchMeasurementsBtn: document.getElementById('search-measurements-btn'),
    searchConstructionsBtn: document.getElementById('search-constructions-btn'),
    cancelSearchBtn: document.getElementById('cancel-search-btn'),
    newSearchBtn: document.getElementById('new-search-btn'),
    exportResultsBtn: document.getElementById('export-results-btn'),
    
    // 탭 버튼들
    tabListBtn: document.getElementById('tab-list'),
    tabDashboardBtn: document.getElementById('tab-dashboard'),
    
    // 섹션들
    progressSection: document.getElementById('progress-section'),
    resultsSection: document.getElementById('results-section'),
    
    // 진행 상황
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    progressDetails: document.getElementById('progress-details'),
    
    // 결과
    resultsSummary: document.getElementById('results-summary'),
    resultsContainer: document.getElementById('results-container'),
    dashboardContainer: document.getElementById('dashboard-container'),
    
    // 토스트 컨테이너
    toastContainer: document.getElementById('toast-container')
};

// 전역 변수
let currentSearchResults = [];
let isSearching = false;

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // 오늘 날짜를 기본값으로 설정
    const today = new Date().toISOString().split('T')[0];
    elements.startDateInput.value = today;
    
    // 이벤트 리스너 등록
    setupEventListeners();
}

function setupEventListeners() {
    // 검색 버튼들
    elements.searchMeasurementsBtn.addEventListener('click', startMeasurementSearch);
    elements.searchConstructionsBtn.addEventListener('click', startConstructionSearch);
    elements.cancelSearchBtn.addEventListener('click', cancelSearch);
    elements.newSearchBtn.addEventListener('click', resetSearch);
    elements.exportResultsBtn.addEventListener('click', exportResults);
    
    // 탭 버튼들
    elements.tabListBtn.addEventListener('click', () => switchTab('list'));
    elements.tabDashboardBtn.addEventListener('click', () => switchTab('dashboard'));
    
    // Socket.IO 이벤트 리스너
    setupSocketListeners();
}

function setupSocketListeners() {
    socket.on('connect', function() {
        updateConnectionStatus('connected', '연결됨');
    });
    
    socket.on('disconnect', function() {
        updateConnectionStatus('disconnected', '연결 끊김');
    });
    
    socket.on('search-progress', function(data) {
        updateSearchProgress(data);
    });
    
    socket.on('measurement-search-complete', function(data) {
        completeMeasurementSearch(data);
    });
    
    socket.on('construction-search-complete', function(data) {
        completeConstructionSearch(data);
    });
    
    socket.on('search-error', function(data) {
        showToast('검색 중 오류가 발생했습니다: ' + data.message, 'error');
        resetSearch();
    });
}

// 연결 상태 업데이트
function updateConnectionStatus(status, message) {
    elements.connectionIndicator.className = `status-indicator ${status}`;
    elements.connectionIndicator.innerHTML = `<i class="fas fa-circle"></i> ${message}`;
}



// 실측스케쥴 그룹 검색 시작
function startMeasurementSearch() {
    const searchData = {
        startDate: elements.startDateInput.value,
        maxMessages: parseInt(elements.maxChatsInput.value) || 500 // 기본값을 500으로 증가
    };
    
    showProgressSection();
    isSearching = true;
    
    // 진행 메시지 업데이트
    elements.progressText.textContent = '실측스케쥴 그룹에서 검색을 준비하는 중...';
    
    // 버튼 상태 업데이트
    updateButtonStates(true);
    
    // Socket.IO로 실측스케쥴 그룹 검색 시작
    socket.emit('search-measurements', searchData);
}

// 시공일 검색 시작 (발주 관련 그룹들)
function startConstructionSearch() {
    const searchData = {
        startDate: elements.startDateInput.value,
        maxMessages: parseInt(elements.maxChatsInput.value) || 500,
        groupType: 'all' // 모든 발주 관련 그룹 검색
    };
    
    showProgressSection();
    isSearching = true;
    
    // 진행 메시지 업데이트
    elements.progressText.textContent = '발주 관련 그룹에서 시공일 정보를 검색하는 중...';
    
    // 버튼 상태 업데이트
    updateButtonStates(true);
    
    // Socket.IO로 시공일 검색 시작
    socket.emit('search-constructions', searchData);
}



// 검색 진행상황 업데이트
function updateSearchProgress(data) {
    elements.progressText.textContent = data.message;
    
    if (data.totalChats && data.currentChat) {
        const progress = (data.currentChat / data.totalChats) * 100;
        elements.progressFill.style.width = progress + '%';
    }
    
    // 진행 상세 정보 추가
    if (data.status === 'found' && data.result) {
        const detail = document.createElement('div');
        detail.innerHTML = `
            <strong>발견!</strong> 채팅 ${data.result.userChatId}에서 ${data.result.totalMessages}개 메시지 찾음
        `;
        detail.style.marginBottom = '8px';
        detail.style.color = '#22543d';
        detail.style.fontWeight = '500';
        elements.progressDetails.appendChild(detail);
        elements.progressDetails.scrollTop = elements.progressDetails.scrollHeight;
    }
}



// 실측 검색 완료
function completeMeasurementSearch(data) {
    currentSearchResults = data.results;
    isSearching = false;
    
    hideProgressSection();
    showResultsSection();
    updateButtonStates(false);
    
    displayMeasurementResults(data.results);
    showToast(`실측 검색이 완료되었습니다! 총 ${data.results.summary.totalMeasurements}개의 실측 정보를 찾았습니다.`, 'success');
}

// 시공일 검색 완료
function completeConstructionSearch(data) {
    // 서버에서 전송된 데이터 구조에 맞게 처리
    const results = data.results || data;
    currentSearchResults = results;
    isSearching = false;
    
    hideProgressSection();
    showResultsSection();
    updateButtonStates(false);
    
    displayConstructionResults(results);
    showToast(`시공일 검색이 완료되었습니다! 총 ${results.summary.totalConstructions}개의 시공일 정보를 찾았습니다.`, 'success');
}



// 실측 결과 표시
function displayMeasurementResults(data) {
    const { summary, measurements, statistics } = data;
    
    // 요약 정보
    elements.resultsSummary.innerHTML = `
        <h3><i class="fas fa-ruler-combined"></i> 실측 스케쥴 검색 요약</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px;">
            <div>
                <strong>검색된 채팅:</strong> ${summary.totalChatsSearched}개<br>
                <strong>실측 정보:</strong> ${summary.totalMeasurements}개<br>
                <strong>성공 채팅:</strong> ${summary.chatsWithMeasurements}개
            </div>
            <div>
                <strong>실패 채팅:</strong> ${summary.chatsWithErrors}개<br>
                <strong>검색 날짜:</strong> ${data.searchInfo.startDate || '전체'} 이후<br>
                <strong>라홈 제외:</strong> 필터링 적용됨
            </div>
        </div>
        ${statistics.vendors ? `
        <div style="margin-top: 15px;">
            <strong>발주사별 통계:</strong>
            ${Object.entries(statistics.vendors).map(([vendor, count]) => 
                `<span style="margin-right: 15px; padding: 4px 8px; background: #e2e8f0; border-radius: 4px; font-size: 0.9rem;">
                    ${vendor}: ${count}개
                </span>`
            ).join('')}
        </div>
        ` : ''}
    `;
    
    // 결과 목록
    elements.resultsContainer.innerHTML = '';
    
    if (measurements.length === 0) {
        elements.resultsContainer.innerHTML = `
            <div class="result-item">
                <div style="text-align: center; color: #718096;">
                    <i class="fas fa-ruler-combined" style="font-size: 3rem; margin-bottom: 15px; opacity: 0.5;"></i>
                    <h3>실측 정보가 없습니다</h3>
                    <p>다른 날짜 범위로 다시 시도해보거나, 더 많은 채팅을 검색해보세요.</p>
                </div>
            </div>
        `;
        return;
    }
    
    measurements.forEach(measurement => {
        const measurementElement = createMeasurementElement(measurement);
        elements.resultsContainer.appendChild(measurementElement);
    });
}

// 실측 정보 요소 생성
function createMeasurementElement(measurement) {
    const div = document.createElement('div');
    div.className = 'result-item measurement-item';
    
    const data = measurement.parsedData;
    
    div.innerHTML = `
        <div class="result-header">
            <span class="result-chat-id">
                <i class="fas fa-calendar"></i> ${data.measurementDate || 'N/A'}
            </span>
            <span class="result-count measurement-badge">실측정보</span>
        </div>
        
        <div class="measurement-details">
            <div class="measurement-grid">
                <div class="measurement-field">
                    <strong><i class="fas fa-user"></i> 고객명:</strong>
                    <span>${data.customerName || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-building"></i> 발주사:</strong>
                    <span class="vendor-name">${data.vendor || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-hammer"></i> 시공일:</strong>
                    <span>${data.constructionDate || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-map-marker-alt"></i> 주소:</strong>
                    <span>${data.address || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-phone"></i> 연락처:</strong>
                    <span>${data.contact || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-box"></i> 제품명:</strong>
                    <span>${data.productName || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-ruler"></i> 규격:</strong>
                    <span>${data.specification || 'N/A'}</span>
                </div>
                <div class="measurement-field">
                    <strong><i class="fas fa-palette"></i> 색상:</strong>
                    <span>${data.color || 'N/A'}</span>
                </div>
            </div>
            
            ${data.option && data.option !== '상담' ? `
                <div class="measurement-field">
                    <strong><i class="fas fa-cog"></i> 옵션:</strong>
                    <span>${data.option}</span>
                </div>
            ` : ''}
            
            ${data.handle && data.handle !== '상담' ? `
                <div class="measurement-field">
                    <strong><i class="fas fa-hand-paper"></i> 손잡이:</strong>
                    <span>${data.handle}</span>
                </div>
            ` : ''}
            
            ${data.etc && data.etc !== '상담' ? `
                <div class="measurement-field">
                    <strong><i class="fas fa-sticky-note"></i> 기타:</strong>
                    <span>${data.etc}</span>
                </div>
            ` : ''}
        </div>
        
        <div class="measurement-meta">
            <small>
                <i class="fas fa-clock"></i> 메시지 생성: ${formatDate(measurement.createdAt)} | 
                <i class="fas fa-user-tie"></i> 매니저: ${measurement.manager} |
                <i class="fas fa-id-badge"></i> 메시지 ID: ${measurement.messageId}
            </small>
        </div>
    `;
    
    return div;
}



// 날짜 포맷
function formatDate(dateString) {
    const date = new Date(parseInt(dateString));
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 검색 취소
function cancelSearch() {
    if (isSearching) {
        socket.disconnect();
        socket.connect();
        resetSearch();
        showToast('검색이 취소되었습니다.', 'info');
    }
}

// 검색 초기화
function resetSearch() {
    isSearching = false;
    hideProgressSection();
    hideResultsSection();
    updateButtonStates(false);
    
    // 진행 상황 초기화
    elements.progressFill.style.width = '0%';
    elements.progressText.textContent = '검색을 준비하는 중...';
    elements.progressDetails.innerHTML = '';
}

// 결과 내보내기
function exportResults() {
    if (currentSearchResults.length === 0) {
        showToast('내보낼 결과가 없습니다.', 'warning');
        return;
    }
    
    const exportData = {
        searchInfo: {
            keyword: elements.keywordInput.value,
            startDate: elements.startDateInput.value,
            searchTime: new Date().toISOString(),
            totalResults: currentSearchResults.reduce((sum, r) => sum + r.totalMessages, 0)
        },
        results: currentSearchResults.filter(r => r.totalMessages > 0)
    };
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `channel_search_results_${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showToast('결과가 JSON 파일로 다운로드되었습니다.', 'success');
}

// 시공일 결과 표시
function displayConstructionResults(data) {
    const { searchInfo, summary, constructions, statistics, groupResults } = data;
    
    // 요약 정보 표시
    let summaryHtml = `
        <div class="search-summary">
            <h3><i class="fas fa-hard-hat"></i> 시공일 정보 검색 결과</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <span class="summary-label">검색 기준일:</span>
                    <span class="summary-value">${searchInfo.startDate || '전체'}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">검색된 메시지:</span>
                    <span class="summary-value">${summary.filteredMessages || summary.totalMessages}개</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">시공일 정보:</span>
                    <span class="summary-value">${constructions.length}개</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">검색 그룹:</span>
                    <span class="summary-value">${groupResults ? '영업팀_발주정보, 발주방' : '발주 관련 그룹'}</span>
                </div>
            </div>
        </div>
    `;

    // 그룹별 결과 요약 (다중 그룹 검색인 경우)
    if (groupResults && groupResults.length > 1) {
        summaryHtml += `
            <div class="group-statistics">
                <h4><i class="fas fa-layer-group"></i> 그룹별 결과</h4>
                <div class="group-grid">
        `;
        
        groupResults.forEach(group => {
            summaryHtml += `
                <div class="group-item">
                    <span class="group-name">${group.groupName}</span>
                    <span class="group-count">${group.constructions.length}건</span>
                </div>
            `;
        });
        
        summaryHtml += `
                </div>
            </div>
        `;
    }

    // 발주사별 통계
    if (statistics.vendorStats && Object.keys(statistics.vendorStats).length > 0) {
        summaryHtml += `
            <div class="vendor-statistics">
                <h4><i class="fas fa-building"></i> 발주사별 통계</h4>
                <div class="vendor-grid">
        `;
        
        Object.entries(statistics.vendorStats).forEach(([vendor, count]) => {
            summaryHtml += `
                <div class="vendor-item">
                    <span class="vendor-name">${vendor}</span>
                    <span class="vendor-count">${count}건</span>
                </div>
            `;
        });
        
        summaryHtml += `
                </div>
            </div>
        `;
    }

    // 시공일 정보 목록
    let constructionsHtml = '';
    if (constructions.length > 0) {
        constructionsHtml = `
            <div class="constructions-list">
                <h4><i class="fas fa-list"></i> 시공일 정보 목록</h4>
                <div class="constructions-grid">
        `;
        
        constructions.forEach((construction, index) => {
            constructionsHtml += createConstructionElement(construction, index);
        });
        
        constructionsHtml += `
                </div>
            </div>
        `;
    } else {
        constructionsHtml = `
            <div class="no-results">
                <i class="fas fa-search"></i>
                <p>검색 조건에 맞는 시공일 정보를 찾을 수 없습니다.</p>
            </div>
        `;
    }

    elements.resultsSummary.innerHTML = summaryHtml;
    elements.resultsContainer.innerHTML = constructionsHtml;
}

// 시공일 카드 요소 생성
function createConstructionElement(construction, index) {
    const data = construction.parsedData;
    const createdAt = new Date(construction.createdAt).toLocaleString('ko-KR');
    
    return `
        <div class="construction-item" data-index="${index}">
            <div class="construction-header">
                <span class="construction-badge">#${index + 1}</span>
                <span class="construction-date">${createdAt}</span>
                <span class="construction-manager">${construction.groupId || 'Unknown'}</span>
            </div>
            
            <div class="construction-details">
                <div class="construction-grid">
                    ${data.constructionDate ? `
                        <div class="construction-field">
                            <strong>시공일:</strong> ${data.constructionDate}
                        </div>
                    ` : ''}
                    ${data.customerName ? `
                        <div class="construction-field">
                            <strong>고객명:</strong> ${data.customerName}
                        </div>
                    ` : ''}
                    ${data.vendor ? `
                        <div class="construction-field">
                            <strong>발주사:</strong> <span class="vendor-name">${data.vendor}</span>
                        </div>
                    ` : ''}
                    ${data.address ? `
                        <div class="construction-field">
                            <strong>주소:</strong> ${data.address}
                        </div>
                    ` : ''}
                    ${data.contact ? `
                        <div class="construction-field">
                            <strong>연락처:</strong> ${data.contact}
                        </div>
                    ` : ''}
                    ${data.productName ? `
                        <div class="construction-field">
                            <strong>제품명:</strong> ${data.productName}
                        </div>
                    ` : ''}
                    ${data.size ? `
                        <div class="construction-field">
                            <strong>규격:</strong> ${data.size}
                        </div>
                    ` : ''}
                    ${data.color ? `
                        <div class="construction-field">
                            <strong>색상:</strong> ${data.color}
                        </div>
                    ` : ''}
                </div>
                
                <div class="construction-meta">
                    <small>
                        <strong>메시지 ID:</strong> ${construction.messageId || 'N/A'} | 
                        <strong>그룹 ID:</strong> ${construction.groupId || 'N/A'}
                    </small>
                </div>
                
                ${construction.plainText ? `
                    <div class="construction-raw">
                        <details>
                            <summary>원본 메시지 보기</summary>
                            <div class="raw-content">${construction.plainText}</div>
                        </details>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
}



// 유틸리티 함수들
function showProgressSection() {
    elements.progressSection.style.display = 'block';
    elements.resultsSection.style.display = 'none';
}

function hideProgressSection() {
    elements.progressSection.style.display = 'none';
}

function showResultsSection() {
    elements.resultsSection.style.display = 'block';
}

function hideResultsSection() {
    elements.resultsSection.style.display = 'none';
}

function updateButtonStates(searching) {
    const buttons = [
        elements.searchMeasurementsBtn,
        elements.searchConstructionsBtn
    ];
    
    buttons.forEach(btn => {
        btn.disabled = searching;
    });
    
    elements.cancelSearchBtn.disabled = !searching;
}



function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div style="display: flex; align-items: center;">
            <i class="fas fa-${getToastIcon(type)}" style="margin-right: 10px;"></i>
            <span>${message}</span>
        </div>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 4000);
}

function getToastIcon(type) {
    switch (type) {
        case 'success': return 'check-circle';
        case 'error': return 'exclamation-circle';
        case 'warning': return 'exclamation-triangle';
        case 'info': return 'info-circle';
        default: return 'info-circle';
    }
}

// 탭 전환 함수
function switchTab(tab) {
    if (tab === 'list') {
        elements.tabListBtn.classList.add('active');
        elements.tabDashboardBtn.classList.remove('active');
        elements.resultsContainer.style.display = 'block';
        elements.dashboardContainer.style.display = 'none';
    } else if (tab === 'dashboard') {
        elements.tabListBtn.classList.remove('active');
        elements.tabDashboardBtn.classList.add('active');
        elements.resultsContainer.style.display = 'none';
        elements.dashboardContainer.style.display = 'block';
        
        // 대시보드 데이터가 있으면 표시
        if (currentSearchResults && currentSearchResults.measurements) {
            displayMeasurementDashboard(currentSearchResults);
        } else if (currentSearchResults && currentSearchResults.constructions) {
            displayConstructionDashboard(currentSearchResults);
        }
    }
}

// 실측 대시보드 표시
function displayMeasurementDashboard(data) {
    const { measurements, statistics } = data;
    
    if (!measurements || measurements.length === 0) {
        elements.dashboardContainer.innerHTML = `
            <div class="empty-dashboard">
                <i class="fas fa-chart-bar"></i>
                <h3>대시보드 데이터가 없습니다</h3>
                <p>실측 정보를 검색한 후 대시보드를 확인할 수 있습니다.</p>
            </div>
        `;
        return;
    }
    
    // 날짜별 그룹화
    const groupedByDate = groupMeasurementsByDate(measurements);
    
    // 통계 생성
    const stats = generateMeasurementStats(measurements);
    
    const dashboardHtml = `
        <div class="dashboard-section">
            <div class="dashboard-title">
                <i class="fas fa-chart-bar"></i>
                실측 스케쥴 대시보드
            </div>
            
            <div class="stats-grid">
                <div class="stat-card measurement">
                    <div class="stat-value">${stats.total}</div>
                    <div class="stat-label">총 실측 건수</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${stats.uniqueDates}</div>
                    <div class="stat-label">실측 예정일</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${stats.uniqueVendors}</div>
                    <div class="stat-label">발주사 수</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${stats.todayCount}</div>
                    <div class="stat-label">오늘 실측</div>
                </div>
            </div>
            
            ${Object.keys(groupedByDate).map(date => createDateGroup(date, groupedByDate[date], 'measurement')).join('')}
        </div>
    `;
    
    elements.dashboardContainer.innerHTML = dashboardHtml;
}

// 시공일 대시보드 표시
function displayConstructionDashboard(data) {
    const { constructions } = data;
    
    if (!constructions || constructions.length === 0) {
        elements.dashboardContainer.innerHTML = `
            <div class="empty-dashboard">
                <i class="fas fa-chart-bar"></i>
                <h3>대시보드 데이터가 없습니다</h3>
                <p>시공일 정보를 검색한 후 대시보드를 확인할 수 있습니다.</p>
            </div>
        `;
        return;
    }
    
    console.log(`🔍 대시보드 표시: ${constructions.length}개 시공일 정보`);
    
    // 날짜별 그룹화된 대시보드 생성
    const dashboardHtml = generateConstructionDashboard(constructions, {});
    
    elements.dashboardContainer.innerHTML = dashboardHtml;
}

// 날짜에서 시간 정보 제거하여 순수 날짜만 추출
function extractDateOnly(dateStr) {
    if (!dateStr || dateStr === 'N/A' || dateStr === '날짜 미상') return dateStr;
    
    // "8월 22일 오후 3시" -> "8월 22일"
    // "8월 22일 9시~10시" -> "8월 22일"  
    const match = dateStr.match(/(\d+월\s*\d+일)/);
    return match ? match[1] : dateStr;
}

// 실측 정보를 날짜별로 그룹화
function groupMeasurementsByDate(measurements) {
    const grouped = {};
    
    measurements.forEach(measurement => {
        const data = measurement.parsedData;
        const rawDate = data.measurementDate || '날짜 미상';
        const date = extractDateOnly(rawDate); // 순수 날짜만 추출
        
        if (!grouped[date]) {
            grouped[date] = [];
        }
        grouped[date].push(measurement);
    });
    
    // 날짜순 정렬
    const sortedGrouped = {};
    Object.keys(grouped).sort().forEach(key => {
        sortedGrouped[key] = grouped[key];
    });
    
    return sortedGrouped;
}

// 시공일 정보를 날짜별로 그룹화
function groupConstructionsByDate(constructions) {
    const grouped = {};
    
    constructions.forEach(construction => {
        const data = construction.parsedData;
        const rawDate = data.constructionDate || '날짜 미상';
        const date = extractDateOnly(rawDate); // 순수 날짜만 추출
        
        if (!grouped[date]) {
            grouped[date] = [];
        }
        grouped[date].push(construction);
    });
    
    // 날짜순 정렬
    const sortedGrouped = {};
    Object.keys(grouped).sort().forEach(key => {
        sortedGrouped[key] = grouped[key];
    });
    
    return sortedGrouped;
}

// 날짜 그룹 HTML 생성
function createDateGroup(date, items, type) {
    const typeIcon = type === 'measurement' ? 'fa-ruler-combined' : 'fa-hard-hat';
    const typeColor = type === 'measurement' ? '#e53e3e' : '#38b2ac';
    
    return `
        <div class="date-group">
            <div class="date-header" style="background: linear-gradient(135deg, ${typeColor}, ${typeColor}cc);">
                <span><i class="fas ${typeIcon}"></i> ${date}</span>
                <span class="date-count">${items.length}건</span>
            </div>
            <div class="date-items">
                ${items.map(item => createDateItem(item, type)).join('')}
            </div>
        </div>
    `;
}

// 날짜 아이템 HTML 생성 (이미지 형태로 변경: 이름/주소/전화번호/실측시간/제품내용)
function createDateItem(item, type) {
    const data = item.parsedData;
    const time = getTimeFromMeasurementDate(data.measurementDate || data.constructionDate) || 'N/A';
    
    if (type === 'measurement') {
        return `
            <div class="measurement-card">
                <div class="customer-info">
                    <div class="customer-name">${data.customerName || 'N/A'}</div>
                    <div class="customer-vendor">${data.vendor || 'N/A'}</div>
                </div>
                
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-map-marker-alt"></i></span>
                        <span class="info-label">주소:</span>
                        <span class="info-value">${data.address || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-phone"></i></span>
                        <span class="info-label">연락처:</span>
                        <span class="info-value">${data.contact || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-clock"></i></span>
                        <span class="info-label">실측시간:</span>
                        <span class="info-value">${time}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-box"></i></span>
                        <span class="info-label">제품:</span>
                        <span class="info-value">${data.productName || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-hammer"></i></span>
                        <span class="info-label">시공일:</span>
                        <span class="info-value">${data.constructionDate || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-ruler"></i></span>
                        <span class="info-label">규격:</span>
                        <span class="info-value">${data.specification || 'N/A'}</span>
                    </div>
                </div>
            </div>
        `;
    } else {
        return `
            <div class="construction-card">
                <div class="customer-info">
                    <div class="customer-name">${data.customerName || 'N/A'}</div>
                    <div class="customer-vendor">${data.vendor || 'N/A'}</div>
                </div>
                
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-map-marker-alt"></i></span>
                        <span class="info-label">주소:</span>
                        <span class="info-value">${data.address || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-phone"></i></span>
                        <span class="info-label">연락처:</span>
                        <span class="info-value">${data.contact || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-clock"></i></span>
                        <span class="info-label">시공시간:</span>
                        <span class="info-value">${time}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-box"></i></span>
                        <span class="info-label">제품:</span>
                        <span class="info-value">${data.productName || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-hammer"></i></span>
                        <span class="info-label">시공일:</span>
                        <span class="info-value">${data.constructionDate || 'N/A'}</span>
                    </div>
                    
                    <div class="info-item">
                        <span class="info-icon"><i class="fas fa-ruler"></i></span>
                        <span class="info-label">규격:</span>
                        <span class="info-value">${data.specification || 'N/A'}</span>
                    </div>
                </div>
            </div>
        `;
    }
}

// 실측/시공일에서 시간 정보 추출
function getTimeFromMeasurementDate(dateStr) {
    if (!dateStr || dateStr === 'N/A') return '';
    
    // 시간 관련 패턴 추출
    const timePatterns = [
        /(\d+시\s*\d*분?)/,           // 3시, 3시30분
        /(\d+:\d+)/,                  // 15:30
        /(오전|오후)/,                // 오전, 오후
        /(\d+시\s*이후)/,             // 10시이후
        /(\d+시~\d+시)/,             // 9시~10시
        /(제일\s*빠른\s*시간)/,       // 제일 빠른 시간
        /(상담)/                      // 상담
    ];
    
    for (const pattern of timePatterns) {
        const match = dateStr.match(pattern);
        if (match) {
            return match[1];
        }
    }
    
    return dateStr; // 매치되지 않으면 전체 문자열 반환
}

// 실측 통계 생성
function generateMeasurementStats(measurements) {
    const today = new Date().toISOString().split('T')[0];
    const todayKorean = formatDateToKorean(today);
    
    const stats = {
        total: measurements.length,
        uniqueDates: new Set(measurements.map(m => m.parsedData.measurementDate).filter(d => d)).size,
        uniqueVendors: new Set(measurements.map(m => m.parsedData.vendor).filter(v => v)).size,
        todayCount: measurements.filter(m => m.parsedData.measurementDate && 
                                       m.parsedData.measurementDate.includes(todayKorean)).length
    };
    
    return stats;
}

// 시공일 통계 생성
function generateConstructionStats(constructions) {
    const today = new Date().toISOString().split('T')[0];
    const todayKorean = formatDateToKorean(today);
    
    const stats = {
        total: constructions.length,
        uniqueDates: new Set(constructions.map(c => c.parsedData.constructionDate).filter(d => d)).size,
        uniqueVendors: new Set(constructions.map(c => c.parsedData.vendor).filter(v => v)).size,
        todayCount: constructions.filter(c => c.parsedData.constructionDate && 
                                         c.parsedData.constructionDate.includes(todayKorean)).length
    };
    
    return stats;
}

// 날짜를 한국어 형식으로 변환
function formatDateToKorean(dateStr) {
    const date = new Date(dateStr);
    const month = date.getMonth() + 1;
    const day = date.getDate();
    return `${month}월 ${day}일`;
}

// 날짜에서 시간 정보 추출
function getTimeFromDate(dateStr) {
    if (!dateStr || dateStr === 'N/A') return '';
    
    // 시간 관련 키워드 추출
    const timePatterns = [
        /(\d+시\d*분?)/,
        /(\d+:\d+)/,
        /(오전|오후)/,
        /(\d+시\s*이후)/,
        /(\d+시~\d+시)/,
        /(제일\s*빠른\s*시간)/
    ];
    
    for (const pattern of timePatterns) {
        const match = dateStr.match(pattern);
        if (match) {
            return match[1];
        }
    }
    
    return '';
}

// 실측 대시보드 생성
function generateMeasurementDashboard(measurements) {
    // 날짜별로 그룹핑 (한국어 날짜 형식 처리)
    const groupedByDate = {};
    
    measurements.forEach(measurement => {
        const data = measurement.parsedData;
        let date = data.measurementDate || '날짜 미정';
        
        // 한국어 날짜를 정규화 (예: "8월 22일 오후 3시" -> "8월 22일")
        if (date !== '날짜 미정') {
            // 시간 정보 제거하고 날짜만 추출
            const dateMatch = date.match(/(\d+월\s*\d+일)/);
            if (dateMatch) {
                date = dateMatch[1].replace(/\s+/g, ' '); // 공백 정규화
            }
        }
        
        if (!groupedByDate[date]) {
            groupedByDate[date] = [];
        }
        groupedByDate[date].push(measurement);
    });

    // 날짜순으로 정렬 (한국어 날짜 처리)
    const sortedDates = Object.keys(groupedByDate).sort((a, b) => {
        if (a === '날짜 미정') return 1;
        if (b === '날짜 미정') return -1;
        
        // 한국어 날짜를 Date 객체로 변환하여 비교
        const parseKoreanDate = (dateStr) => {
            const match = dateStr.match(/(\d+)월\s*(\d+)일/);
            if (match) {
                const month = parseInt(match[1]);
                const day = parseInt(match[2]);
                const year = new Date().getFullYear(); // 현재 연도 사용
                return new Date(year, month - 1, day);
            }
            return new Date(0); // 파싱 실패시 기본값
        };
        
        return parseKoreanDate(a) - parseKoreanDate(b);
    });

    return `
        <div class="dashboard-section">
            <h3><i class="fas fa-chart-line"></i> 실측 스케쥴 대시보드</h3>
            
            <div class="dashboard-stats">
                <div class="stat-card">
                    <div class="stat-number">${measurements.length}</div>
                    <div class="stat-label">총 실측 건수</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${Object.keys(groupedByDate).length}</div>
                    <div class="stat-label">실측 예정일</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${new Set(measurements.map(m => m.parsedData.vendor)).size}</div>
                    <div class="stat-label">발주사 수</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">0</div>
                    <div class="stat-label">오늘 실측</div>
                </div>
            </div>

            ${sortedDates.map(date => `
                <div class="date-group">
                    <div class="date-header">
                        <i class="fas fa-calendar-day"></i> ${date}
                        <span class="item-count">${groupedByDate[date].length}건</span>
                    </div>
                    ${groupedByDate[date].map(measurement => {
                        const data = measurement.parsedData;
                        return `
                        <div class="measurement-card">
                            <div class="card-main">
                                <div class="card-header">
                                    <span class="customer-name">${data.customerName || 'N/A'}</span>
                                    <span class="measurement-time">${getTimeFromDate(data.measurementDate)}</span>
                                </div>
                                <div class="card-body">
                                    <div class="card-row">
                                        <div class="card-field">
                                            <span class="field-label">주소</span>
                                            <span class="field-value">${data.address || 'N/A'}</span>
                                        </div>
                                        <div class="card-field">
                                            <span class="field-label">연락처</span>
                                            <span class="field-value">${data.contact || 'N/A'}</span>
                                        </div>
                                    </div>
                                    <div class="card-row">
                                        <div class="card-field">
                                            <span class="field-label">제품명</span>
                                            <span class="field-value">${data.productName || 'N/A'}</span>
                                        </div>
                                        <div class="card-field">
                                            <span class="field-label">발주사</span>
                                            <span class="field-value vendor-badge">${data.vendor || 'N/A'}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `}).join('')}
                </div>
            `).join('')}
        </div>
    `;
}

// 시공일 대시보드 생성  
function generateConstructionDashboard(constructions, groupStats) {
    console.log('🔍 [DEBUG] 대시보드 생성 시작:', constructions.length, '개 항목');
    
    // 날짜별로 그룹핑 (공백 무시, 추가 정보 별도 표기)
    const groupedByDate = {};
    
    constructions.forEach((construction, index) => {
        const data = construction.parsedData;
        let originalDate = data.constructionDate || '날짜 미정';
        
        console.log(`🔍 [DEBUG] 항목 ${index + 1}:`, {
            customerName: data.customerName,
            originalDate: originalDate
        });
        
        // 날짜 파싱 및 정규화
        let date = '날짜 미정';
        let additionalInfo = '';
        
        if (originalDate !== '날짜 미정' && originalDate !== '상담') {
            // 한국어 날짜 패턴 매칭 (공백 무시)
            const dateMatch = originalDate.match(/(\d+월\s*\d+일)/);
            if (dateMatch) {
                date = dateMatch[1].replace(/\s+/g, ' '); // 공백 정규화
                
                // 추가 정보 추출 (날짜 이후의 모든 텍스트)
                const additionalMatch = originalDate.match(/(\d+월\s*\d+일)\s*(.+)/);
                if (additionalMatch && additionalMatch[2]) {
                    additionalInfo = additionalMatch[2].trim();
                }
            } else {
                // 날짜 패턴이 아닌 경우 (상담, 일반 텍스트 등)
                date = '기타';
                additionalInfo = originalDate;
            }
        } else if (originalDate === '상담') {
            date = '상담';
        }
        
        if (!groupedByDate[date]) {
            groupedByDate[date] = [];
        }
        groupedByDate[date].push({
            ...construction,
            additionalInfo: additionalInfo
        });
        
        console.log(`✅ [DEBUG] 그룹화 완료: ${date} 그룹에 추가됨`);
    });

    console.log('🔍 [DEBUG] 그룹화 결과:', Object.keys(groupedByDate));
    console.log('🔍 [DEBUG] 각 그룹별 항목 수:', Object.fromEntries(
        Object.entries(groupedByDate).map(([date, items]) => [date, items.length])
    ));
    
    // 날짜순으로 정렬 (공백 무시, 특수 그룹 우선)
    const sortedDates = Object.keys(groupedByDate).sort((a, b) => {
        // 특수 그룹 우선순위: 상담 > 기타 > 날짜 미정 > 날짜순
        const getPriority = (dateStr) => {
            if (dateStr === '상담') return 1;
            if (dateStr === '기타') return 2;
            if (dateStr === '날짜 미정') return 3;
            return 4; // 일반 날짜
        };
        
        const priorityA = getPriority(a);
        const priorityB = getPriority(b);
        
        if (priorityA !== priorityB) {
            return priorityA - priorityB;
        }
        
        // 같은 우선순위 내에서는 날짜순 정렬
        if (priorityA === 4) {
            const parseKoreanDate = (dateStr) => {
                const match = dateStr.match(/(\d+)월\s*(\d+)일/);
                if (match) {
                    const month = parseInt(match[1]);
                    const day = parseInt(match[2]);
                    const year = new Date().getFullYear();
                    return new Date(year, month - 1, day);
                }
                return new Date(0);
            };
            return parseKoreanDate(a) - parseKoreanDate(b);
        }
        
        return 0;
    });

    return `
        <div class="dashboard-section">
            <h3><i class="fas fa-hard-hat"></i> 시공일 대시보드</h3>
            
            <div class="dashboard-stats">
                <div class="stat-card">
                    <div class="stat-number">${constructions.length}</div>
                    <div class="stat-label">총 시공 건수</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${Object.keys(groupedByDate).length}</div>
                    <div class="stat-label">시공 예정일</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${new Set(constructions.map(c => c.parsedData.vendor)).size}</div>
                    <div class="stat-label">발주사 수</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">0</div>
                    <div class="stat-label">오늘 시공</div>
                </div>
            </div>

            ${sortedDates.map(date => `
                <div class="date-group">
                    <div class="date-header">
                        <i class="fas fa-calendar-day"></i> ${date}
                        <span class="item-count">${groupedByDate[date].length}건</span>
                    </div>
                    <div class="date-items">
                        ${groupedByDate[date].map((construction, index) => {
                            const data = construction.parsedData;
                            return `
                            <div class="construction-card">
                                <div class="card-main">
                                    <div class="card-header">
                                        <span class="customer-name">${data.customerName || 'N/A'}</span>
                                        <span class="construction-time">
                                            ${getTimeFromDate(data.constructionDate)}
                                            ${construction.additionalInfo ? `<span class="additional-info">(${construction.additionalInfo})</span>` : ''}
                                        </span>
                                    </div>
                                <div class="card-body">
                                    <div class="card-row">
                                        <div class="card-field">
                                            <span class="field-label">주소</span>
                                            <span class="field-value">${data.address || 'N/A'}</span>
                                        </div>
                                        <div class="card-field">
                                            <span class="field-label">연락처</span>
                                            <span class="field-value">${data.contact || 'N/A'}</span>
                                        </div>
                                    </div>
                                    <div class="card-row">
                                        <div class="card-field">
                                            <span class="field-label">제품명</span>
                                            <span class="field-value">${data.productName || 'N/A'}</span>
                                        </div>
                                        <div class="card-field">
                                            <span class="field-label">발주사</span>
                                            <span class="field-value vendor-badge">${data.vendor || 'N/A'}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `}).join('')}
                </div>
            `).join('')}
        </div>
    `;
}


