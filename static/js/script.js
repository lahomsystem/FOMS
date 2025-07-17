/**
 * Common JavaScript functions for the Furniture Order Management System
 */

// Auto-close flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    // Auto close alerts
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // Highlight active menu item
    const currentPath = window.location.pathname;
    const currentSearch = window.location.search;
    const navLinks = document.querySelectorAll('.navbar .nav-link');
    
    navLinks.forEach(function(link) {
        const linkPath = link.getAttribute('href');
        
        if (linkPath === currentPath || 
            linkPath === currentPath + currentSearch || 
            (currentPath.includes('/edit/') && linkPath === '/')) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'page');
        }
    });

    const phoneInputs = document.querySelectorAll('input[name="phone"]');
    const manualPhoneCheckbox = document.getElementById('manual_phone_input');

    phoneInputs.forEach(function(phoneInput) {
        // 페이지 로드 시 초기 포맷팅 적용
        applyConditionalPhoneFormatting(phoneInput);

        // 입력 중 포맷팅 적용
        phoneInput.addEventListener('input', function() {
            applyConditionalPhoneFormatting(this);
        });
    });

    if (manualPhoneCheckbox) {
        // 체크박스 변경 시 포맷팅 재적용
        manualPhoneCheckbox.addEventListener('change', function() {
            phoneInputs.forEach(function(phoneInput) {
                applyConditionalPhoneFormatting(phoneInput);
            });
        });
    }
    
    // 상태 드롭다운 초기 색상 적용
    const statusSelects = document.querySelectorAll('select[data-field="status"]');
    statusSelects.forEach(function(select) {
        applyStatusColor(select);
        
        // 상태 변경 시 색상 업데이트
        select.addEventListener('change', function() {
            applyStatusColor(this);
        });
    });
});

// Phone number formatting logic updated for conditional hyphenation
function applyConditionalPhoneFormatting(phoneInputElement) {
    const manualCheckbox = document.getElementById('manual_phone_input');

    if (manualCheckbox && manualCheckbox.checked) {
        // 수동 입력 모드: 사용자가 입력한 내용 그대로 둠 (아무 작업도 하지 않음)
        // 만약 수동 입력 시에도 숫자 외 문자만 제거하고 싶다면 다음 줄 주석 해제:
        // phoneInputElement.value = phoneInputElement.value.replace(/\D/g, ''); 
        return;
    }

    // 자동 하이픈 추가 모드
    let currentValue = phoneInputElement.value;
    const digitsOnly = currentValue.replace(/\D/g, ''); // 숫자만 추출
    let formattedValue = '';

    if (digitsOnly.length > 0) {
        formattedValue = digitsOnly.substring(0, 3);
        if (digitsOnly.length > 3) {
            formattedValue += '-' + digitsOnly.substring(3, Math.min(7, digitsOnly.length));
        }
        if (digitsOnly.length > 7) {
            formattedValue += '-' + digitsOnly.substring(7, Math.min(11, digitsOnly.length));
        }
    }
    phoneInputElement.value = formattedValue;
}

// Format phone numbers as user types (XXX-XXXX-XXXX)
function formatPhoneNumber(input) {
    // 숫자 이외의 문자 모두 제거
    input.value = input.value.replace(/\D/g, '');
}

// 상태별 색상 클래스 적용 함수
function applyStatusColor(selectElement) {
    const status = selectElement.value;
    
    // 기존 상태 클래스 제거
    selectElement.classList.remove('status-received', 'status-measured', 'status-regional_measured', 
                                  'status-scheduled', 'status-shipped_pending', 'status-completed', 
                                  'status-as_received', 'status-as_completed', 'status-on_hold');
    
    // status-dropdown 클래스 추가 (아직 없다면)
    if (!selectElement.classList.contains('status-dropdown')) {
        selectElement.classList.add('status-dropdown');
    }
    
    // 새로운 상태 클래스 추가
    if (status) {
        selectElement.classList.add('status-' + status.toLowerCase());
    }
}



// Phone input event handler (attach to phone inputs)
/*
const phoneInputs = document.querySelectorAll('input[name="phone"]');
phoneInputs.forEach(function(input) {
    input.addEventListener('input', function() {
        formatPhoneNumber(this);
    });
}); 
*/ 