// WDC 제품설정 모듈 (Batch 6: product_settings.html inline → static 이동, verbatim).
// 데이터는 #initial-products/#initial-categories/#initial-notes-categories/#initial-spec-presets JSON 블록에서 읽는다.
// 표준 단독 페이지(ERP shell fragment 아님) — defer로 1회 실행.
document.addEventListener('DOMContentLoaded', function() {
    function safeParseJson(elId) {
        try {
            const el = document.getElementById(elId);
            if (!el) return [];
            return JSON.parse(el.textContent || '[]') || [];
        } catch (err) {
            console.error('JSON parse error from', elId, err);
            showToast && showToast('데이터를 불러오는 중 오류가 발생했습니다. 새로고침 후 다시 시도해주세요.', false);
            return [];
        }
    }

    const products = safeParseJson('initial-products');
    let editingProductId = null;

    // ---- 금액 천단위 콤마 (이 페이지는 shared.js 미로드 — 자체 최소 구현) ----
    function stripComma(v) {
        return String(v == null ? '' : v).replace(/,/g, '');
    }
    function fmtComma(v) {
        var digits = String(v == null ? '' : v).replace(/[^\d]/g, '');
        return digits ? parseInt(digits, 10).toLocaleString('ko-KR') : '';
    }
    // 정수 금액 4필드만 자동포맷. #couponValue 는 % 소수(step 0.1) 가능 → 제외(파싱만 콤마 내성).
    var AMOUNT_IDS = ['price1m', 'price30cm', 'price1cm', 'additionalOptionPrice'];
    document.addEventListener('input', function (e) {
        var t = e.target;
        if (!t || e.isComposing === true || AMOUNT_IDS.indexOf(t.id) === -1) return;
        var raw = String(t.value || '');
        var formatted = fmtComma(raw);
        if (formatted === raw) return;
        var caret = t.selectionStart == null ? raw.length : t.selectionStart;
        var fromEnd = raw.length - caret;
        t.value = formatted;
        var pos = Math.max(0, formatted.length - fromEnd);
        try { t.setSelectionRange(pos, pos); } catch (err) { /* caret 복원 실패 무해 */ }
    });
    
    const toastElement = document.getElementById('status-toast');
    const toastBody = toastElement.querySelector('.toast-body');
    const toast = new bootstrap.Toast(toastElement);
    
    function showToast(message, isSuccess = true) {
        toastBody.textContent = message;
        toastElement.classList.remove('bg-danger', 'bg-success', 'text-white');
        if (isSuccess) {
            toastElement.classList.add('bg-success', 'text-white');
        } else {
            toastElement.classList.add('bg-danger', 'text-white');
        }
        toast.show();
    }
    
    // 가격 옵션 선택에 따른 입력 필드 표시/숨김
    document.getElementById('pricingType').addEventListener('change', function() {
        const pricingType = this.value;
        document.getElementById('price1mGroup').classList.remove('show');
        document.getElementById('price30cmGroup').classList.remove('show');
        
        if (pricingType === '1m') {
            document.getElementById('price1mGroup').classList.add('show');
            document.getElementById('price1m').required = true;
            document.getElementById('price30cm').required = false;
            document.getElementById('price1cm').required = false;
        } else if (pricingType === '30cm') {
            document.getElementById('price30cmGroup').classList.add('show');
            document.getElementById('price1m').required = false;
            document.getElementById('price30cm').required = true;
            document.getElementById('price1cm').required = true;
        } else {
            document.getElementById('price1m').required = false;
            document.getElementById('price30cm').required = false;
            document.getElementById('price1cm').required = false;
        }
    });
    
    // 폼 제출
    document.getElementById('productForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = {
            id: editingProductId || null,
            name: document.getElementById('productName').value,
            category: document.getElementById('productCategory').value.trim(),
            pricing_type: document.getElementById('pricingType').value,
            additional_options: [],  // 추가 옵션은 더 이상 제품에 연결되지 않음
            coupon_type: document.getElementById('couponType').value,
            coupon_value: parseFloat(stripComma(document.getElementById('couponValue').value)) || 0
        };

        // 가격 정보 추가 (콤마 내성 파싱 — 저장 값은 항상 클린 숫자)
        if (formData.pricing_type === '1m') {
            formData.price_1m = parseInt(stripComma(document.getElementById('price1m').value), 10) || 0;
        } else if (formData.pricing_type === '30cm') {
            formData.price_30cm = parseInt(stripComma(document.getElementById('price30cm').value), 10) || 0;
            formData.price_1cm = parseInt(stripComma(document.getElementById('price1cm').value), 10) || 0;
        }
        
        // API 호출
        fetch('/api/wdcalculator/products', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast(data.message, true);
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                showToast(data.message, false);
            }
        })
        .catch(error => {
            showToast('서버 통신 중 오류가 발생했습니다.', false);
        });
    });
    
    // 폼 초기화
    document.getElementById('resetFormBtn').addEventListener('click', function() {
        document.getElementById('productForm').reset();
        document.getElementById('productId').value = '';
        document.getElementById('productCategory').value = '';
        editingProductId = null;
        document.getElementById('price1mGroup').classList.remove('show');
        document.getElementById('price30cmGroup').classList.remove('show');
    });
    
    // 제품 수정
    document.querySelectorAll('.edit-product-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const productId = parseInt(this.dataset.productId);
            const product = products.find(p => p.id === productId);
            
            if (product) {
                editingProductId = productId;
                document.getElementById('productId').value = productId;
                document.getElementById('productName').value = product.name;
                document.getElementById('productCategory').value = product.category || '';
                document.getElementById('pricingType').value = product.pricing_type;
                document.getElementById('pricingType').dispatchEvent(new Event('change'));
                
                if (product.pricing_type === '1m') {
                    document.getElementById('price1m').value = fmtComma(product.price_1m) || 0;
                } else if (product.pricing_type === '30cm') {
                    document.getElementById('price30cm').value = fmtComma(product.price_30cm) || 0;
                    document.getElementById('price1cm').value = fmtComma(product.price_1cm) || 0;
                }
                
                document.getElementById('couponType').value = product.coupon_type || 'percentage';
                document.getElementById('couponValue').value = product.coupon_value || 0;
                
                // 스크롤 to form
                document.getElementById('productForm').scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
    
    // 제품 삭제
    document.querySelectorAll('.delete-product-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const productIdStr = this.dataset.productId;
            const productRow = this.closest('tr');
            const productName = productRow ? productRow.querySelector('td:nth-child(2) strong')?.textContent || '이 제품' : '이 제품';
            
            if (!confirm(`정말 "${productName}" 제품을 삭제하시겠습니까?\n삭제된 제품은 복구할 수 없습니다.`)) {
                return;
            }
            
            if (!productIdStr || productIdStr === 'None') {
                showToast('제품 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
                return;
            }
            
            const productId = parseInt(productIdStr);
            
            if (isNaN(productId)) {
                showToast('제품 정보가 올바르지 않습니다.', false);
                return;
            }
            
            // 삭제 중 표시
            const deleteBtn = this;
            const originalHtml = deleteBtn.innerHTML;
            deleteBtn.disabled = true;
            deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 삭제 중...';
            
            fetch(`/api/wdcalculator/products/${productId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast(data.message || '제품이 삭제되었습니다.', true);
                    setTimeout(() => {
                        location.reload();
                    }, 1000);
                } else {
                    showToast(data.message || '제품 삭제에 실패했습니다.', false);
                    deleteBtn.disabled = false;
                    deleteBtn.innerHTML = originalHtml;
                }
            })
            .catch(error => {
                showToast('서버 통신 중 오류가 발생했습니다.', false);
                deleteBtn.disabled = false;
                deleteBtn.innerHTML = originalHtml;
            });
        });
    });

    // ==================== 추가 옵션 관리 ====================
    const categories = safeParseJson('initial-categories');
    let editingAdditionalOptionId = null;
    let editingAdditionalOptionCategoryId = null;
    
    // ==================== 비고 카테고리 관리 ====================
    let notesCategories = safeParseJson('initial-notes-categories');
    let editingNotesOptionId = null;
    let editingNotesCategoryId = null;
    
    // 비고 카테고리 목록 새로고침 함수
    function refreshNotesCategoriesList() {
        console.log('비고 카테고리 목록 새로고침 시작...');
        fetch('/api/wdcalculator/notes/categories')
            .then(response => {
                console.log('API 응답 상태:', response.status);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('API 응답 데이터:', data);
                if (data.success) {
                    notesCategories = data.categories || [];
                    console.log('로드된 카테고리 수:', notesCategories.length);
                    renderNotesCategoriesList();
                } else {
                    console.error('비고 카테고리 목록 로드 실패:', data.message);
                    showToast('목록을 불러오는 중 오류가 발생했습니다: ' + (data.message || '알 수 없는 오류'), false);
                }
            })
            .catch(error => {
                console.error('비고 카테고리 목록 로드 중 오류:', error);
                showToast('목록을 불러오는 중 오류가 발생했습니다: ' + error.message, false);
            });
    }
    
    // 비고 카테고리 목록 렌더링 함수
    function renderNotesCategoriesList() {
        console.log('renderNotesCategoriesList 호출됨, 카테고리 수:', notesCategories ? notesCategories.length : 0);
        const container = document.getElementById('notesCategoriesListContainer');
        if (!container) {
            console.error('notesCategoriesListContainer를 찾을 수 없습니다.');
            return;
        }
        
        // 옵션이 있는지 확인
        let hasOptions = false;
        let totalOptions = 0;
        if (notesCategories && Array.isArray(notesCategories)) {
            notesCategories.forEach(category => {
                if (category && category.options && Array.isArray(category.options)) {
                    category.options.forEach(option => {
                        if (option && option.id) {
                            hasOptions = true;
                            totalOptions++;
                        }
                    });
                }
            });
        }
        
        console.log('옵션 존재 여부:', hasOptions, '총 옵션 수:', totalOptions);
        
        const tbody = document.getElementById('notesCategoriesTableBody');
        const noNotesCategories = document.getElementById('noNotesCategories');
        const table = document.getElementById('notesCategoriesTable');
        const tableResponsive = table ? table.closest('.table-responsive') : null;
        
        if (!hasOptions) {
            // 목록이 없을 때
            console.log('옵션이 없어서 빈 메시지 표시');
            if (table && tableResponsive) {
                tableResponsive.style.display = 'none';
            }
            if (noNotesCategories) {
                noNotesCategories.style.display = 'block';
            } else {
                container.innerHTML = `
                    <div class="text-center py-4" id="noNotesCategories">
                        <i class="fas fa-sticky-note text-muted fa-3x mb-3"></i>
                        <h5 class="text-muted">등록된 비고 카테고리가 없습니다.</h5>
                        <p class="text-muted">위 폼을 사용하여 비고 카테고리를 추가해주세요.</p>
                    </div>
                `;
            }
            return;
        }
        
        // 목록이 있을 때
        console.log('옵션이 있어서 테이블 표시');
        if (noNotesCategories) {
            noNotesCategories.style.display = 'none';
        }
        
        // 테이블이 없으면 생성
        if (!tbody || !table) {
            console.log('테이블이 없어서 새로 생성');
            container.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-bordered table-hover wdcalc-mobile-card-table" id="notesCategoriesTable">
                        <thead class="table-light">
                            <tr>
                                <th style="width: 60px;">ID</th>
                                <th>카테고리명</th>
                                <th>옵션명</th>
                                <th style="width: 180px;">작업</th>
                            </tr>
                        </thead>
                        <tbody id="notesCategoriesTableBody">
                        </tbody>
                    </table>
                </div>
            `;
        } else {
            // 테이블이 있으면 보이게 설정
            console.log('기존 테이블 사용, 표시 설정');
            if (tableResponsive) {
                tableResponsive.style.display = 'block';
                tableResponsive.style.visibility = 'visible';
            }
            if (table) {
                table.style.display = 'table';
                table.style.visibility = 'visible';
            }
        }
        
        const newTbody = document.getElementById('notesCategoriesTableBody');
        if (!newTbody) {
            console.error('notesCategoriesTableBody를 찾을 수 없습니다.');
            return;
        }
        
        let html = '';
        let rowNumber = 1;
        notesCategories.forEach(category => {
            if (category && category.options && Array.isArray(category.options)) {
                category.options.forEach((option, optionIndex) => {
                    if (option && option.name) {
                        const displayId = rowNumber;
                        html += `
                            <tr data-category-id="${category.id}" data-option-id="${option.id || ''}" data-option-name="${escapeHtml(option.name || '')}" data-option-index="${optionIndex}">
                                <td data-label="ID">${displayId}</td>
                                <td data-label="카테고리명"><strong>${escapeHtml(category.name || '')}</strong></td>
                                <td data-label="옵션명">${escapeHtml(option.name || '')}</td>
                                <td data-label="작업">
                                    <div class="d-flex gap-1">
                                        <button class="btn btn-sm btn-outline-primary edit-notes-option-btn" data-category-id="${category.id}" data-option-id="${option.id || ''}" data-option-name="${escapeHtml(option.name || '')}" data-option-index="${optionIndex}" data-category-name="${escapeHtml(category.name || '')}" title="수정">
                                            <i class="fas fa-edit"></i> 수정
                                        </button>
                                        <button class="btn btn-sm btn-outline-danger delete-notes-option-btn" data-category-id="${category.id}" data-option-id="${option.id || ''}" data-option-name="${escapeHtml(option.name || '')}" data-option-index="${optionIndex}" title="삭제">
                                            <i class="fas fa-trash"></i> 삭제
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `;
                        rowNumber++;
                    }
                });
            }
        });
        
        newTbody.innerHTML = html;
        console.log('비고 카테고리 목록 렌더링 완료, 행 수:', html.split('</tr>').length - 1);
        
        // 테이블이 보이도록 강제 설정
        const finalTable = document.getElementById('notesCategoriesTable');
        const finalTableResponsive = finalTable ? finalTable.closest('.table-responsive') : null;
        if (finalTableResponsive) {
            finalTableResponsive.style.display = 'block';
            finalTableResponsive.style.visibility = 'visible';
            finalTableResponsive.style.opacity = '1';
        }
        if (finalTable) {
            finalTable.style.display = 'table';
            finalTable.style.visibility = 'visible';
        }
        
        // 이벤트 리스너 재등록
        attachNotesCategoryEventListeners();
    }
    
    // 비고 카테고리 이벤트 리스너 등록 함수
    function attachNotesCategoryEventListeners() {
        // 수정 버튼 이벤트
        document.querySelectorAll('.edit-notes-option-btn').forEach(btn => {
            btn.removeEventListener('click', handleEditNotesOption);
            btn.addEventListener('click', handleEditNotesOption);
        });
        
        // 삭제 버튼 이벤트
        document.querySelectorAll('.delete-notes-option-btn').forEach(btn => {
            btn.removeEventListener('click', handleDeleteNotesOption);
            btn.addEventListener('click', handleDeleteNotesOption);
        });
    }
    
    // 수정 버튼 핸들러
    function handleEditNotesOption(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const categoryIdStr = this.dataset.categoryId;
        const optionIdStr = this.dataset.optionId;
        const optionName = this.dataset.optionName;
        // optionIndex 파싱 버그 수정: 0도 유효한 값이므로 || -1 대신 명시적 체크
        const optionIndexStr = this.dataset.optionIndex;
        const optionIndex = (optionIndexStr !== undefined && optionIndexStr !== '') 
            ? parseInt(optionIndexStr) 
            : -1;
        const categoryName = this.dataset.categoryName;
        
        if (!categoryIdStr || categoryIdStr === 'None') {
            showToast('옵션 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
            return;
        }
        
        const categoryId = parseInt(categoryIdStr);
        if (isNaN(categoryId)) {
            showToast('옵션 정보가 올바르지 않습니다.', false);
            return;
        }
        
        // 타입 안전한 비교를 위해 숫자로 변환
        const category = notesCategories.find(c => {
            if (!c) return false;
            const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
            return cId === categoryId;
        });
        
        if (!category || !category.options || !Array.isArray(category.options)) {
            showToast('카테고리를 찾을 수 없습니다.', false);
            return;
        }
        
        // 옵션 찾기: ID를 최우선으로 사용 (고유 식별자)
        let option = null;
        
        // 1순위: ID로 찾기 (가장 신뢰할 수 있음)
        if (optionIdStr && optionIdStr !== '' && optionIdStr !== 'None') {
            const optionId = parseInt(optionIdStr);
            if (!isNaN(optionId)) {
                option = category.options.find(o => {
                    if (!o) return false;
                    const oId = typeof o.id === 'string' ? parseInt(o.id) : o.id;
                    return oId === optionId;
                });
                if (option) {
                    console.log('옵션을 ID로 찾음:', option.id, option.name);
                }
            }
        }
        
        // 2순위: 인덱스로 찾기 (ID가 없거나 찾지 못했을 때)
        if (!option && optionIndex >= 0 && optionIndex < category.options.length) {
            option = category.options[optionIndex];
            // 인덱스로 찾은 옵션이 이름도 일치하는지 확인
            if (optionName && option && option.name !== optionName) {
                console.warn('인덱스로 찾은 옵션의 이름이 일치하지 않음:', {
                    found: option.name,
                    expected: optionName,
                    optionIndex
                });
                // 이름이 다르면 null로 설정 (다음 단계로)
                option = null;
            } else if (option) {
                console.log('옵션을 인덱스로 찾음:', optionIndex, option.id, option.name);
            }
        }
        
        // 3순위: 이름으로 찾기 (ID와 인덱스 모두 실패했을 때만, 경고 표시)
        if (!option && optionName) {
            const foundOptions = category.options.filter(o => o && o.name === optionName);
            if (foundOptions.length > 1) {
                console.warn('같은 이름의 옵션이 여러 개 있습니다:', foundOptions.length, '개');
                console.warn('옵션 ID를 사용하는 것을 권장합니다.');
            }
            option = foundOptions[0]; // 첫 번째 것만 사용
            if (option) {
                console.log('옵션을 이름으로 찾음 (경고: 같은 이름이 여러 개일 수 있음):', option.id, option.name);
            }
        }
        
        if (!option) {
            showToast('옵션을 찾을 수 없습니다.', false);
            return;
        }
        
        document.getElementById('notesCategoryName').value = categoryName || category.name;
        document.getElementById('notesOptionName').value = option.name;
        document.getElementById('notesCategoryId').value = option.id || '';
        document.getElementById('notesCategoryCategoryId').value = categoryId;
        editingNotesOptionId = option.id;
        editingNotesCategoryId = categoryId;
        
        document.getElementById('notesCategoryForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    
    // 삭제 버튼 핸들러
    function handleDeleteNotesOption(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const categoryIdStr = this.dataset.categoryId;
        const optionIdStr = this.dataset.optionId;
        const optionName = this.dataset.optionName;
        // optionIndex 파싱 버그 수정: 0도 유효한 값이므로 || -1 대신 명시적 체크
        const optionIndexStr = this.dataset.optionIndex;
        const optionIndex = (optionIndexStr !== undefined && optionIndexStr !== '') 
            ? parseInt(optionIndexStr) 
            : -1;
        
        if (!categoryIdStr || categoryIdStr === 'None') {
            showToast('옵션 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
            return;
        }
        
        const categoryId = parseInt(categoryIdStr);
        if (isNaN(categoryId)) {
            showToast('옵션 정보가 올바르지 않습니다.', false);
            return;
        }
        
        // 타입 안전한 비교를 위해 숫자로 변환
        const category = notesCategories.find(c => {
            if (!c) return false;
            const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
            return cId === categoryId;
        });
        
        if (!category || !category.options || !Array.isArray(category.options)) {
            console.error('카테고리를 찾을 수 없습니다:', { categoryId, notesCategories });
            showToast('카테고리를 찾을 수 없습니다. 페이지를 새로고침해주세요.', false);
            return;
        }
        
        // 옵션 찾기: 인덱스를 우선 사용 (가장 안정적)
        let option = null;
        if (optionIndex >= 0 && optionIndex < category.options.length) {
            option = category.options[optionIndex];
            // 인덱스로 찾은 옵션이 이름도 일치하는지 확인
            if (optionName && option && option.name !== optionName) {
                // 이름이 다르면 이름으로 다시 찾기
                option = category.options.find(o => o && o.name === optionName);
            }
        } else if (optionName) {
            // 인덱스가 유효하지 않으면 이름으로 찾기
            option = category.options.find(o => o && o.name === optionName);
        } else if (optionIdStr && optionIdStr !== '' && optionIdStr !== 'None') {
            // ID로 찾기
            const optionId = parseInt(optionIdStr);
            if (!isNaN(optionId)) {
                option = category.options.find(o => {
                    if (!o) return false;
                    const oId = typeof o.id === 'string' ? parseInt(o.id) : o.id;
                    return oId === optionId;
                });
            }
        }
        
        if (!option) {
            console.error('옵션을 찾을 수 없습니다:', { 
                categoryId, 
                optionIdStr, 
                optionName, 
                optionIndex,
                categoryOptions: category.options 
            });
            showToast('옵션을 찾을 수 없습니다. 페이지를 새로고침해주세요.', false);
            return;
        }
        
        // 옵션 ID 확인 및 할당
        let optionId = option.id;
        // option.id가 null이나 undefined이면 인덱스 사용 (0은 유효한 ID이므로 제외)
        if ((optionId === null || optionId === undefined) && optionIndex >= 0) {
            optionId = optionIndex;
        }
        
        // 최종 검증: null, undefined, NaN 체크
        if (optionId === null || optionId === undefined || isNaN(Number(optionId))) {
            console.error('옵션 ID가 유효하지 않습니다:', { 
                optionId, 
                option, 
                optionIndex,
                optionIdType: typeof optionId,
                dataset: {
                    categoryId: this.dataset.categoryId,
                    optionId: this.dataset.optionId,
                    optionName: this.dataset.optionName,
                    optionIndex: this.dataset.optionIndex
                }
            });
            showToast('옵션 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
            return;
        }
        
        deleteOptionWithId(categoryId, optionId, option.name);
    }
    
    // 삭제 함수 분리
    function deleteOptionWithId(categoryId, optionId, optionName) {
        const confirmMessage = optionName 
            ? `정말 "${optionName}" 비고 옵션을 삭제하시겠습니까?\n삭제된 옵션은 복구할 수 없습니다.`
            : '정말 이 비고 옵션을 삭제하시겠습니까?\n삭제된 옵션은 복구할 수 없습니다.';
        
        if (!confirm(confirmMessage)) {
            return;
        }
        
        // 삭제 버튼 찾기 및 상태 업데이트
        const deleteBtn = document.querySelector(`.delete-notes-option-btn[data-category-id="${categoryId}"][data-option-id="${optionId}"], .delete-notes-option-btn[data-category-id="${categoryId}"][data-option-index="${optionId}"]`);
        const originalHtml = deleteBtn ? deleteBtn.innerHTML : null;
        if (deleteBtn) {
            deleteBtn.disabled = true;
            deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 삭제 중...';
        }
        
        fetch(`/api/wdcalculator/notes/categories/${categoryId}/options/${optionId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast(data.message || '비고 옵션이 삭제되었습니다.', true);
                refreshNotesCategoriesList();
            } else {
                showToast(data.message || '비고 옵션 삭제에 실패했습니다.', false);
                if (deleteBtn && originalHtml) {
                    deleteBtn.disabled = false;
                    deleteBtn.innerHTML = originalHtml;
                }
            }
        })
        .catch(error => {
            console.error('삭제 중 오류:', error);
            showToast('서버 통신 중 오류가 발생했습니다.', false);
            if (deleteBtn && originalHtml) {
                deleteBtn.disabled = false;
                deleteBtn.innerHTML = originalHtml;
            }
        });
    }
    
    // HTML 이스케이프 함수
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 추가 옵션 폼 제출
    document.getElementById('additionalOptionForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const categoryName = document.getElementById('additionalOptionCategoryName').value.trim();
        const optionName = document.getElementById('additionalOptionName').value.trim();
        const optionPrice = parseInt(stripComma(document.getElementById('additionalOptionPrice').value), 10) || 0;
        
        // 0원 옵션도 허용(예: 기본 구성). 음수만 거부.
        if (!categoryName || !optionName || optionPrice < 0) {
            showToast('카테고리·옵션명을 입력하고 가격은 0원 이상으로 입력해주세요.', false);
            return;
        }
        
        // 수정 모드인지 확인
        const editingOptionId = editingAdditionalOptionId;
        const editingCategoryId = editingAdditionalOptionCategoryId;
        
        if (editingCategoryId && editingOptionId) {
            // 수정 모드: 카테고리명과 옵션명 모두 확인
            console.log('=== 추가 옵션 수정 모드 ===');
            console.log('카테고리명:', categoryName);
            console.log('옵션명:', optionName);
            console.log('가격:', optionPrice);
            console.log('editingCategoryId:', editingCategoryId);
            console.log('editingOptionId:', editingOptionId);
            console.log('현재 categories:', categories);
            
            // 현재 카테고리 정보 가져오기
            const currentCategory = categories.find(c => {
                if (!c) return false;
                const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
                return cId === editingCategoryId;
            });
            
            if (!currentCategory) {
                showToast('카테고리를 찾을 수 없습니다.', false);
                return;
            }
            
            // 카테고리명이 변경되었는지 확인
            const categoryNameChanged = currentCategory.name !== categoryName;
            
            // 옵션 데이터 준비
            const optionData = {
                id: editingOptionId,
                name: optionName,
                price: optionPrice
            };
            
            // 옵션 수정 함수
            const updateAdditionalOption = (categoryId, optionId, optionData) => {
                fetch(`/api/wdcalculator/additional-options/categories/${categoryId}/options`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(optionData)
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast(data.message, true);
                        setTimeout(() => {
                            location.reload();
                        }, 1000);
                    } else {
                        showToast(data.message, false);
                    }
                })
                .catch(error => {
                    showToast('서버 통신 중 오류가 발생했습니다.', false);
                });
            };
            
            // 카테고리명이 변경되었으면 먼저 카테고리 수정 API 호출
            if (categoryNameChanged) {
                console.log('카테고리명 변경 감지, 카테고리 수정 API 호출');
                // 카테고리명만 변경하므로 options는 보내지 않음 (백엔드에서 기존 옵션 유지)
                const categoryData = {
                    id: editingCategoryId,
                    name: categoryName
                };
                
                fetch('/api/wdcalculator/additional-options/categories', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(categoryData)
                })
                .then(response => {
                    console.log('카테고리 수정 API 응답 상태:', response.status);
                    if (!response.ok) {
                        return response.json().then(err => {
                            throw new Error(err.message || `HTTP ${response.status}: ${response.statusText}`);
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('카테고리 수정 API 응답 데이터:', data);
                    if (data.success) {
                        // 카테고리 수정 성공 후 categories 배열 업데이트
                        const categoryIndex = categories.findIndex(c => {
                            if (!c) return false;
                            const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
                            return cId === editingCategoryId;
                        });
                        if (categoryIndex !== -1) {
                            categories[categoryIndex].name = categoryName;
                            console.log('categories 배열 업데이트 완료:', categoryName);
                        } else {
                            console.warn('카테고리를 categories 배열에서 찾을 수 없음');
                        }
                        // 카테고리 수정 성공 후 옵션 수정 진행
                        updateAdditionalOption(editingCategoryId, editingOptionId, optionData);
                    } else {
                        showToast(data.message, false);
                    }
                })
                .catch(error => {
                    console.error('카테고리 수정 중 오류:', error);
                    showToast('카테고리 수정 중 오류가 발생했습니다: ' + error.message, false);
                });
            } else {
                // 카테고리명이 변경되지 않았으면 옵션만 수정
                updateAdditionalOption(editingCategoryId, editingOptionId, optionData);
            }
        } else {
            // 추가 모드: 기존 로직 유지
        // 카테고리 찾기 또는 생성
        let category = categories.find(c => c.name === categoryName);
        let categoryId = editingAdditionalOptionCategoryId;
        
        // 수정 모드가 아니면 카테고리명으로 검색
        if (!categoryId && category) {
            categoryId = category.id;
        }
        
        // 카테고리를 찾지 못했으면 새로 생성
        if (!categoryId && !category) {
            categoryId = null; // 새로 생성할 카테고리
        }
        
        // 옵션 데이터 준비
        const optionData = {
            id: editingAdditionalOptionId || null,
            name: optionName,
            price: optionPrice
        };
        
        // 카테고리가 있으면 옵션만 추가/수정, 없으면 카테고리와 옵션 함께 생성
        if (categoryId) {
            // 기존 카테고리에 옵션 추가/수정
            fetch(`/api/wdcalculator/additional-options/categories/${categoryId}/options`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(optionData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast(data.message, true);
                    setTimeout(() => {
                        location.reload();
                    }, 1000);
                } else {
                    showToast(data.message, false);
                }
            })
            .catch(error => {
                showToast('서버 통신 중 오류가 발생했습니다.', false);
            });
        } else {
            // 새 카테고리와 옵션 함께 생성
            const categoryData = {
                name: categoryName,
                options: [optionData]
            };
            
            fetch('/api/wdcalculator/additional-options/categories', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(categoryData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast(data.message, true);
                    setTimeout(() => {
                        location.reload();
                    }, 1000);
                } else {
                    showToast(data.message, false);
                }
            })
            .catch(error => {
                showToast('서버 통신 중 오류가 발생했습니다.', false);
            });
            }
        }
    });

    // 추가 옵션 폼 초기화
    document.getElementById('resetAdditionalOptionFormBtn').addEventListener('click', function() {
        document.getElementById('additionalOptionForm').reset();
        document.getElementById('additionalOptionId').value = '';
        document.getElementById('additionalOptionCategoryId').value = '';
        editingAdditionalOptionId = null;
        editingAdditionalOptionCategoryId = null;
    });

    // 추가 옵션 수정
    document.querySelectorAll('.edit-additional-option-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const categoryIdStr = this.dataset.categoryId;
            const optionIdStr = this.dataset.optionId;
            const categoryName = this.dataset.categoryName;
            
            // None 값 처리
            if (!categoryIdStr || categoryIdStr === 'None' || !optionIdStr || optionIdStr === 'None') {
                showToast('옵션 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
                return;
            }
            
            const categoryId = parseInt(categoryIdStr);
            const optionId = parseInt(optionIdStr);
            
            if (isNaN(categoryId) || isNaN(optionId)) {
                showToast('옵션 정보가 올바르지 않습니다.', false);
                return;
            }
            
            const category = categories.find(c => c && c.id === categoryId);
            
            if (!category) {
                showToast('카테고리를 찾을 수 없습니다.', false);
                return;
            }
            
            if (!category.options || !Array.isArray(category.options)) {
                showToast('옵션 목록을 찾을 수 없습니다.', false);
                return;
            }
            
            const option = category.options.find(o => o && o.id === optionId);
            
            if (!option) {
                showToast('옵션을 찾을 수 없습니다.', false);
                return;
            }
            
            // 폼에 값 설정
            editingAdditionalOptionId = optionId;
            editingAdditionalOptionCategoryId = categoryId;
            
            document.getElementById('additionalOptionId').value = optionId;
            document.getElementById('additionalOptionCategoryId').value = categoryId;
            document.getElementById('additionalOptionCategoryName').value = categoryName || category.name;
            document.getElementById('additionalOptionName').value = option.name || '';
            document.getElementById('additionalOptionPrice').value = fmtComma(option.price) || 0;
            
            // 폼으로 스크롤
            document.getElementById('additionalOptionForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    // 추가 옵션 삭제
    document.querySelectorAll('.delete-additional-option-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const categoryIdStr = this.dataset.categoryId;
            const optionIdStr = this.dataset.optionId;
            
            // None 값 처리
            if (!categoryIdStr || categoryIdStr === 'None' || !optionIdStr || optionIdStr === 'None') {
                showToast('옵션 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
                return;
            }
            
            const categoryId = parseInt(categoryIdStr);
            const optionId = parseInt(optionIdStr);
            
            if (isNaN(categoryId) || isNaN(optionId)) {
                showToast('옵션 정보가 올바르지 않습니다.', false);
                return;
            }
            
            // 옵션 정보 가져오기
            const optionRow = this.closest('tr');
            const categoryName = optionRow ? optionRow.querySelector('td:nth-child(2) strong')?.textContent || '' : '';
            const optionName = optionRow ? optionRow.querySelector('td:nth-child(3)')?.textContent || '' : '';
            
            const confirmMessage = categoryName && optionName 
                ? `정말 "${categoryName} > ${optionName}" 옵션을 삭제하시겠습니까?\n삭제된 옵션은 복구할 수 없습니다.`
                : '정말 이 옵션을 삭제하시겠습니까?\n삭제된 옵션은 복구할 수 없습니다.';
            
            if (!confirm(confirmMessage)) {
                return;
            }
            
            // 삭제 중 표시
            const deleteBtn = this;
            const originalHtml = deleteBtn.innerHTML;
            deleteBtn.disabled = true;
            deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 삭제 중...';
            
            fetch(`/api/wdcalculator/additional-options/categories/${categoryId}/options/${optionId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast(data.message || '옵션이 삭제되었습니다.', true);
                    setTimeout(() => {
                        location.reload();
                    }, 1000);
                } else {
                    showToast(data.message || '옵션 삭제에 실패했습니다.', false);
                    deleteBtn.disabled = false;
                    deleteBtn.innerHTML = originalHtml;
                }
            })
            .catch(error => {
                showToast('서버 통신 중 오류가 발생했습니다.', false);
                deleteBtn.disabled = false;
                deleteBtn.innerHTML = originalHtml;
            });
        });
    });

    // 옵션 수정 함수 분리
    function updateNotesOption(categoryId, optionId, optionName) {
            const optionData = {
            id: optionId,
                name: optionName
            };
            
        fetch(`/api/wdcalculator/notes/categories/${categoryId}/options`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(optionData)
            })
            .then(response => {
                console.log('옵션 수정 API 응답 상태:', response.status);
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.message || `HTTP ${response.status}: ${response.statusText}`);
                    });
                }
                return response.json();
            })
                .then(data => {
                    console.log('옵션 수정 API 응답 데이터:', data);
                    if (data.success) {
                        showToast(data.message, true);
                        // 저장 후 API로 최신 데이터 가져오기
                        fetch('/api/wdcalculator/notes/categories')
                            .then(response => response.json())
                            .then(apiData => {
                                console.log('저장 후 최신 데이터:', apiData);
                                if (apiData.success) {
                                    notesCategories = apiData.categories || [];
                                    // 1초 후 페이지 새로고침
                                    setTimeout(() => {
                                        location.reload();
                                    }, 1000);
                                } else {
                                    showToast('목록을 불러오는 중 오류가 발생했습니다.', false);
                                }
                            })
                            .catch(error => {
                                console.error('최신 데이터 로드 중 오류:', error);
                                setTimeout(() => {
                                    location.reload();
                                }, 1000);
                            });
                    } else {
                        showToast(data.message, false);
                    }
                })
            .catch(error => {
                console.error('옵션 수정 중 오류:', error);
                console.error('에러 상세:', error.message, error.stack);
                showToast('서버 통신 중 오류가 발생했습니다: ' + error.message, false);
            });
    }

    // 비고 카테고리 폼 제출
    document.getElementById('notesCategoryForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const categoryName = document.getElementById('notesCategoryName').value.trim();
        const optionName = document.getElementById('notesOptionName').value.trim();
        
        if (!categoryName || !optionName) {
            showToast('모든 필드를 올바르게 입력해주세요.', false);
            return;
        }
        
        console.log('=== 비고 카테고리 저장 시작 ===');
        console.log('카테고리명:', categoryName);
        console.log('옵션명:', optionName);
        console.log('editingNotesCategoryId:', editingNotesCategoryId);
        console.log('editingNotesOptionId:', editingNotesOptionId);
        console.log('현재 notesCategories:', notesCategories);
        
        // 수정 모드인지 확인
        const editingOptionId = editingNotesOptionId;
        const editingCategoryId = editingNotesCategoryId;
        
        if (editingCategoryId && editingOptionId) {
            // 수정 모드: 카테고리명과 옵션명 모두 확인
            console.log('수정 모드: 카테고리명 및 옵션명 수정');
            
            // 현재 카테고리 정보 가져오기
            const currentCategory = notesCategories.find(c => {
                if (!c) return false;
                const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
                return cId === editingCategoryId;
            });
            
            if (!currentCategory) {
                showToast('카테고리를 찾을 수 없습니다.', false);
                return;
            }
            
            // 카테고리명이 변경되었는지 확인
            const categoryNameChanged = currentCategory.name !== categoryName;
            
            // 카테고리명이 변경되었으면 먼저 카테고리 수정 API 호출
            if (categoryNameChanged) {
                console.log('카테고리명 변경 감지, 카테고리 수정 API 호출');
                // 카테고리명만 변경하므로 options는 보내지 않음 (백엔드에서 기존 옵션 유지)
                const categoryData = {
                    id: editingCategoryId,
                    name: categoryName
                };
                
                fetch('/api/wdcalculator/notes/categories', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(categoryData)
                })
                .then(response => {
                    console.log('카테고리 수정 API 응답 상태:', response.status);
                    if (!response.ok) {
                        return response.json().then(err => {
                            throw new Error(err.message || `HTTP ${response.status}: ${response.statusText}`);
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('카테고리 수정 API 응답 데이터:', data);
                    if (data.success) {
                        // 카테고리 수정 성공 후 notesCategories 배열 업데이트
                        if (data.category) {
                            const categoryIndex = notesCategories.findIndex(c => {
                                if (!c) return false;
                                const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
                                return cId === editingCategoryId;
                            });
                            if (categoryIndex !== -1) {
                                notesCategories[categoryIndex] = data.category;
                                console.log('notesCategories 배열 업데이트 완료:', data.category);
                            } else {
                                console.warn('카테고리를 notesCategories 배열에서 찾을 수 없음');
                            }
                        }
                        // 카테고리 수정 성공 후 옵션 수정 진행
                        updateNotesOption(editingCategoryId, editingOptionId, optionName);
                    } else {
                        showToast(data.message, false);
                    }
                })
                .catch(error => {
                    console.error('카테고리 수정 중 오류:', error);
                    showToast('카테고리 수정 중 오류가 발생했습니다: ' + error.message, false);
                });
            } else {
                // 카테고리명이 변경되지 않았으면 옵션만 수정
                updateNotesOption(editingCategoryId, editingOptionId, optionName);
            }
        } else {
            // 추가 모드: 기존 카테고리 찾기 또는 새로 생성
            let category = notesCategories.find(c => c && c.name === categoryName);
            let categoryId = category ? category.id : null;
            
            console.log('추가 모드: 기존 카테고리 찾기 결과:', category);
            console.log('categoryId:', categoryId);
            
            if (categoryId) {
                // 기존 카테고리에 옵션 추가
                console.log('기존 카테고리에 옵션 추가');
                const optionData = {
                    id: null,
                    name: optionName
                };
                
                fetch(`/api/wdcalculator/notes/categories/${categoryId}/options`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(optionData)
                })
            .then(response => {
                console.log('옵션 추가 API 응답 상태:', response.status);
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.message || `HTTP ${response.status}: ${response.statusText}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                console.log('옵션 추가 API 응답 데이터:', data);
                if (data.success) {
                        showToast(data.message, true);
                        // 저장 후 API로 최신 데이터 가져오기
                        fetch('/api/wdcalculator/notes/categories')
                            .then(response => response.json())
                            .then(apiData => {
                                console.log('저장 후 최신 데이터:', apiData);
                                if (apiData.success) {
                                    notesCategories = apiData.categories || [];
                                    // 1초 후 페이지 새로고침
                                    setTimeout(() => {
                                        location.reload();
                                    }, 1000);
                                } else {
                                    showToast('목록을 불러오는 중 오류가 발생했습니다.', false);
                                }
                            })
                            .catch(error => {
                                console.error('최신 데이터 로드 중 오류:', error);
                                setTimeout(() => {
                                    location.reload();
                                }, 1000);
                            });
                    } else {
                        showToast(data.message, false);
                    }
                })
                .catch(error => {
                    console.error('옵션 추가 중 오류:', error);
                    console.error('에러 상세:', error.message, error.stack);
                    showToast('서버 통신 중 오류가 발생했습니다: ' + error.message, false);
                });
            } else {
                // 새 카테고리와 옵션 함께 생성
                console.log('새 카테고리와 옵션 함께 생성');
                const categoryData = {
                    name: categoryName,
                    options: [{
                        id: null,
                        name: optionName
                    }]
                };
                
                fetch('/api/wdcalculator/notes/categories', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(categoryData)
                })
                .then(response => {
                    console.log('카테고리 생성 API 응답 상태:', response.status);
                    return response.json();
                })
                .then(data => {
                    console.log('카테고리 생성 API 응답 데이터:', data);
                    if (data.success) {
                        showToast(data.message, true);
                        // 저장 후 API로 최신 데이터 가져오기
                        fetch('/api/wdcalculator/notes/categories')
                            .then(response => response.json())
                            .then(apiData => {
                                console.log('저장 후 최신 데이터:', apiData);
                                if (apiData.success) {
                                    notesCategories = apiData.categories || [];
                                    // 1초 후 페이지 새로고침
                                    setTimeout(() => {
                                        location.reload();
                                    }, 1000);
                                } else {
                                    showToast('목록을 불러오는 중 오류가 발생했습니다.', false);
                                }
                            })
                            .catch(error => {
                                console.error('최신 데이터 로드 중 오류:', error);
                                setTimeout(() => {
                                    location.reload();
                                }, 1000);
                            });
                    } else {
                        showToast(data.message, false);
                    }
                })
                .catch(error => {
                    console.error('카테고리 생성 중 오류:', error);
                    console.error('에러 상세:', error.message, error.stack);
                    showToast('서버 통신 중 오류가 발생했습니다: ' + error.message, false);
                });
            }
        }
    });

    // 비고 카테고리 폼 초기화
    document.getElementById('resetNotesCategoryFormBtn').addEventListener('click', function() {
        document.getElementById('notesCategoryForm').reset();
        document.getElementById('notesCategoryId').value = '';
        document.getElementById('notesCategoryCategoryId').value = '';
        editingNotesOptionId = null;
        editingNotesCategoryId = null;
    });

    // 비고 옵션 수정 및 삭제 (이벤트 위임 사용)
    document.addEventListener('click', function(e) {
        // 수정 버튼 처리
        const editBtn = e.target.closest('.edit-notes-option-btn');
        if (editBtn) {
            e.preventDefault();
            e.stopPropagation();
            
            const categoryIdStr = editBtn.dataset.categoryId;
            const optionIdStr = editBtn.dataset.optionId;
            const optionName = editBtn.dataset.optionName;
            // optionIndex 파싱 버그 수정: 0도 유효한 값이므로 || -1 대신 명시적 체크
            const optionIndexStr = editBtn.dataset.optionIndex;
            const optionIndex = (optionIndexStr !== undefined && optionIndexStr !== '') 
                ? parseInt(optionIndexStr) 
                : -1;
            const categoryName = editBtn.dataset.categoryName;
            
            if (!categoryIdStr || categoryIdStr === 'None') {
                showToast('옵션 정보를 불러올 수 없습니다. 페이지를 새로고침해주세요.', false);
                return;
            }
            
            const categoryId = parseInt(categoryIdStr);
            if (isNaN(categoryId)) {
                showToast('옵션 정보가 올바르지 않습니다.', false);
                return;
            }
            
            // 타입 안전한 비교를 위해 숫자로 변환
            const category = notesCategories.find(c => {
                if (!c) return false;
                const cId = typeof c.id === 'string' ? parseInt(c.id) : c.id;
                return cId === categoryId;
            });
            
            if (!category || !category.options || !Array.isArray(category.options)) {
                showToast('카테고리를 찾을 수 없습니다.', false);
                return;
            }
            
            // 옵션 찾기: ID를 최우선으로 사용 (고유 식별자)
            let option = null;
            
            // 1순위: ID로 찾기 (가장 신뢰할 수 있음)
            if (optionIdStr && optionIdStr !== '' && optionIdStr !== 'None') {
                const optionId = parseInt(optionIdStr);
                if (!isNaN(optionId)) {
                    option = category.options.find(o => {
                        if (!o) return false;
                        const oId = typeof o.id === 'string' ? parseInt(o.id) : o.id;
                        return oId === optionId;
                    });
                    if (option) {
                        console.log('옵션을 ID로 찾음:', option.id, option.name);
                    }
                }
            }
            
            // 2순위: 인덱스로 찾기 (ID가 없거나 찾지 못했을 때)
            if (!option && optionIndex >= 0 && optionIndex < category.options.length) {
                option = category.options[optionIndex];
                // 인덱스로 찾은 옵션이 이름도 일치하는지 확인
                if (optionName && option && option.name !== optionName) {
                    console.warn('인덱스로 찾은 옵션의 이름이 일치하지 않음:', {
                        found: option.name,
                        expected: optionName,
                        optionIndex
                    });
                    // 이름이 다르면 null로 설정 (다음 단계로)
                    option = null;
                } else if (option) {
                    console.log('옵션을 인덱스로 찾음:', optionIndex, option.id, option.name);
                }
            }
            
            // 3순위: 이름으로 찾기 (ID와 인덱스 모두 실패했을 때만, 경고 표시)
            if (!option && optionName) {
                const foundOptions = category.options.filter(o => o && o.name === optionName);
                if (foundOptions.length > 1) {
                    console.warn('같은 이름의 옵션이 여러 개 있습니다:', foundOptions.length, '개');
                    console.warn('옵션 ID를 사용하는 것을 권장합니다.');
                }
                option = foundOptions[0]; // 첫 번째 것만 사용
                if (option) {
                    console.log('옵션을 이름으로 찾음 (경고: 같은 이름이 여러 개일 수 있음):', option.id, option.name);
                }
            }
            
            if (!option) {
                showToast('옵션을 찾을 수 없습니다.', false);
                return;
            }
            
            editingNotesOptionId = option.id;
            editingNotesCategoryId = categoryId;
            
            document.getElementById('notesCategoryId').value = option.id || '';
            document.getElementById('notesCategoryCategoryId').value = categoryId;
            document.getElementById('notesCategoryName').value = categoryName || category.name;
            document.getElementById('notesOptionName').value = option.name || '';
            
            document.getElementById('notesCategoryForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
            return;
        }
        
        // 삭제 버튼 처리
        const deleteBtn = e.target.closest('.delete-notes-option-btn');
        if (deleteBtn) {
            handleDeleteNotesOption.call(deleteBtn, e);
        }
    });

    // 비고 카테고리 초기 이벤트 리스너 등록 (서버 사이드 렌더링된 테이블용 - 안전장치)
    // 이벤트 위임 방식이 있지만, 초기 로드 시에도 확실하게 작동하도록 등록
    attachNotesCategoryEventListeners();
});
