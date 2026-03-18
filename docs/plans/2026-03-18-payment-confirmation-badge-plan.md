# 예약금·잔금 입금 확인 뱃지 시스템 구현 계획서 (최종판)

> **작성일**: 2026-03-18
> **작성**: GDM (소스 리뷰 -> 계획 -> 감리 -> 최종)
> **상태**: 최종 승인됨 (바로 착수 가능)

---

## Context

FOMS ERP에서 예약금/잔금 입금 상태를 시각적으로 추적하는 뱃지 시스템이 필요하다.
현재는 ERP Beta 탭에서 예약금 금액만 입력/표시되고, 입금 확인 여부를 추적하는 기능이 없어
실측/프로세스 대시보드에서 입금 상태를 한눈에 파악할 수 없다.

**목표**: 동전(예약금)/지폐(잔금) 아이콘으로 입금 확인 상태를 빨간색(미확인) <-> 파란색(확인) 토글 표시

### 요구사항 요약

| 위치 | 표시 순서 |
|------|-----------|
| 실측 대시보드 | ERP Beta 주문만, 고객 이름 오른쪽 -> 동전(예약금) -> 지폐(잔금) |
| ERP 프로세스 대시보드 | ERP Beta 주문만, 작업 큐 > 고객 이름 아래 줄 -> 동전(예약금) -> 지폐(잔금) |

- **동전(예약금)**: 예약금 금액 > 0일 때만 표시. 빨간색(미확인) -> 체크 시 파란색(확인)
- **지폐(잔금)**: 항상 표시. 빨간색(미확인) -> 잔금 체크 시 파란색(확인)
- 체크 상태는 DB에 저장되어 새로고침 후에도 유지
- **범위 고정**: 이번 기능은 `structured_data.payment` 기반 ERP Beta 주문만 지원한다. legacy/non-Beta 주문은 기존 UI 유지

---

## 1. 데이터 모델 확장

`structured_data.payment` JSONB 키 확장 (Alembic 마이그레이션 불필요):

```json
{
  "deposit": 500000,
  "deposit_confirmed": true,
  "deposit_confirmed_at": "2026-03-18T14:30:00",
  "deposit_confirmed_by": "홍길동",
  "deposit_confirmed_by_user_id": 5,
  "balance_confirmed": true,
  "balance_confirmed_at": "2026-03-18T15:00:00",
  "balance_confirmed_by": "홍길동",
  "balance_confirmed_by_user_id": 5
}
```

- 기존 패턴(`drawing_confirmed_at/by`, `blueprint.confirmed_at/by`)과 일관성 유지
- `confirmed_by`(이름)와 `confirmed_by_user_id`(PK) 병행 저장하여 조인 없이 표시 가능

---

## 2. API: 입금 확인 토글

**파일**: `apps/api/erp_orders_structured.py`  
**엔드포인트**: `POST /api/orders/<int:order_id>/payment-confirm`

```json
Request:
{ "type": "deposit" | "balance", "confirmed": true }

Response:
{
  "success": true,
  "payment": {
    "deposit": 500000,
    "deposit_confirmed": true,
    "deposit_confirmed_at": "2026-03-18T14:30:00",
    "deposit_confirmed_by": "홍길동",
    "deposit_confirmed_by_user_id": 5,
    "balance_confirmed": false,
    "balance_confirmed_at": null,
    "balance_confirmed_by": null,
    "balance_confirmed_by_user_id": null
  }
}
```

- 데코레이터: `@login_required` + `@role_required(['ADMIN', 'MANAGER', 'STAFF'])`
- 패턴: `copy.deepcopy` + `flag_modified` (기존 PUT과 동일)
- `type` 값 화이트리스트 검증 (`deposit`, `balance`만 허용)
- user 정보: `session['user_id']` -> User 조회 -> `user.name` + `user.id` 저장
- **최종 결정**: 토글 API는 단일 필드가 아니라 `payment` 전체 객체를 반환한다
- 이유: 클라이언트가 응답 payload로 `window.__erpLastStructuredData.payment`를 통째로 교체해야 이후 전체 저장에서 `*_confirmed_by_user_id`가 `null`로 덮어써지지 않는다

---

## 3. ERP Beta 탭 UI: 체크 버튼

**파일**: `templates/partials/erp_beta_tab.html`

예약금 행과 잔금 행 각각 왼쪽에 아이콘 체크 버튼 삽입:

```text
[🪙] 예약금(선금)  |  500,000원
[💵] 잔금          |  1,500,000원
```

- 아이콘: `fas fa-coins` (예약금), `fas fa-money-bill-wave` (잔금)
- 빨간색(`--erp-danger`) = 미확인, 파란색(`--erp-primary`) = 확인
- 예약금 입력 UI는 기존 유지, 토글 버튼만 추가

---

## 4. 대시보드 뱃지 표시

### 4-1. 실측 대시보드

**파일**: `templates/erp_measurement_dashboard.html`

- 표시 대상은 `r.is_erp_beta == true`인 주문만
- 고객 이름 오른쪽에 삽입하되, 좁은 폭에서는 같은 셀 안에서 줄바꿈 허용
- 고객 컬럼 폭을 `120px -> 150px`로 확대
- 이름/자가실측/chevron/입금 뱃지를 감싸는 래퍼에 `gap` + `flex-wrap` 적용
- `structured_data`가 `None`이어도 안전해야 함

```jinja
{% set _show_payment_badges = r.is_erp_beta|default(false) %}
{% set _pay = ((r.structured_data or {}).get('payment') or {}) %}
{% set _deposit = _pay.get('deposit', 0) %}
{% if not _deposit %}
  {% set _payments = ((r.structured_data or {}).get('payments') or {}) %}
  {% set _dep_obj = (_payments.get('deposit') or {}) %}
  {% set _deposit = _dep_obj.get('amount', 0) if _dep_obj is mapping else 0 %}
{% endif %}
```

- 동전: `_show_payment_badges and _deposit > 0`일 때만 표시
- 지폐: `_show_payment_badges`일 때만 표시
- 색상: `_pay.get('deposit_confirmed')` / `_pay.get('balance_confirmed')` 여부로 결정
- 비 ERP Beta 주문은 뱃지 미표시

### 4-2. ERP 프로세스 대시보드

**파일**: `templates/partials/erp_dashboard_grid.html`

- 표시 대상은 `o.is_erp_beta`가 참인 주문만
- 고객 이름 아래 별도 줄에 동전/지폐 아이콘 표시
- `o.structured_data`는 enriched dict 기준으로 접근하되, 동일한 `payments -> payment` 폴백 적용

```jinja
{% set _show_payment_badges = o.is_erp_beta|default(false) %}
{% set _pay = ((o.structured_data or {}).get('payment') or {}) %}
```

---

## 5. CSS

**파일**: `static/css/erp-pro.css`

```css
/* Payment Confirmation Badge Icons */
.erp-payment-badge-icon { font-size: 0.85rem; cursor: default; }
.erp-payment-unconfirmed { color: var(--erp-danger); }
.erp-payment-confirmed { color: var(--erp-primary); }

.erp-payment-confirm-btn { background: none; border: 0; font-size: 1.1rem; cursor: pointer; }
.erp-payment-confirm-btn:hover { transform: scale(1.15); }
.erp-payment-icon-unchecked { color: var(--erp-danger); }
.erp-payment-icon-checked { color: var(--erp-primary); }

.erp-payment-badge-row {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}
```

---

## 6. JS 로직

**파일**: `templates/partials/erp_beta_js.html`

### 6-1. 헬퍼 함수

- `_erpNormalizePaymentData(sd)`
  - `sd.payment`를 기본값으로 사용
  - `sd.payments.deposit.amount`만 있는 parser 기반 주문이면 이를 `payment.deposit`로 정규화
  - `deposit_confirmed`, `balance_confirmed`, `*_at`, `*_by`, `*_by_user_id` 기본값까지 채워서 반환
- `_erpUpdatePaymentConfirmUI(type, paymentData)`
  - 버튼 아이콘 색상과 title 갱신

### 6-2. 데이터 로드 시 체크 상태 반영

```js
const paymentData = _erpNormalizePaymentData(sd);
(window.__erpLastStructuredData ||= {}).payment = paymentData;
_erpUpdatePaymentConfirmUI('deposit', paymentData);
_erpUpdatePaymentConfirmUI('balance', paymentData);
```

- **최종 결정**: parser 기반 주문(`structured_data.payments.deposit.amount`)도 ERP Beta 로드시 즉시 `payment.deposit`로 정규화
- 이 정규화 결과를 UI 표시와 전체 저장 보존의 공통 기준으로 사용

### 6-3. `erpCollectStructured()` payment 보존

전체 저장 시 체크 상태가 소실되지 않도록, 정규화된 `__erpLastStructuredData.payment`에서 확인 필드 전체를 복사:

```js
payment: (function () {
    const raw = getVal('erp-deposit-amount');
    const deposit = raw ? parseInt(String(raw).replace(/[^0-9]/g, ''), 10) : 0;
    const prev = _erpNormalizePaymentData(window.__erpLastStructuredData || {});
    return {
        deposit: Number.isFinite(deposit) ? deposit : 0,
        deposit_confirmed: prev.deposit_confirmed || false,
        deposit_confirmed_at: prev.deposit_confirmed_at || null,
        deposit_confirmed_by: prev.deposit_confirmed_by || null,
        deposit_confirmed_by_user_id: prev.deposit_confirmed_by_user_id || null,
        balance_confirmed: prev.balance_confirmed || false,
        balance_confirmed_at: prev.balance_confirmed_at || null,
        balance_confirmed_by: prev.balance_confirmed_by || null,
        balance_confirmed_by_user_id: prev.balance_confirmed_by_user_id || null
    };
})(),
```

### 6-4. 체크 버튼 이벤트 핸들러

- 토글 API 호출 후 응답의 `payment` 전체 객체로 `__erpLastStructuredData.payment`를 즉시 교체
- `_paymentTogglePending` 플래그로 전체 저장과 토글 간 직렬화

```js
let _paymentTogglePending = false;

document.querySelectorAll('.erp-payment-confirm-btn').forEach(btn => {
    btn.addEventListener('click', async function() {
        if (_paymentTogglePending) return;
        _paymentTogglePending = true;
        try {
            const res = await fetch(`/api/orders/${ORDER_ID}/payment-confirm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: this.dataset.paymentType,
                    confirmed: this.dataset.confirmed !== '1'
                })
            });
            const data = await res.json();
            if (data.success && data.payment) {
                const p = _erpNormalizePaymentData({ payment: data.payment });
                ((window.__erpLastStructuredData ||= {}).payment = p);
                _erpUpdatePaymentConfirmUI(this.dataset.paymentType, p);
            }
        } finally {
            _paymentTogglePending = false;
        }
    });
});
```

전체 저장(`erpSaveStructured`)에서도 `_paymentTogglePending`이 내려갈 때까지 대기:

```js
if (_paymentTogglePending) {
    await new Promise(resolve => {
        const iv = setInterval(() => {
            if (!_paymentTogglePending) {
                clearInterval(iv);
                resolve();
            }
        }, 50);
    });
}
```

---

## 7. 감리 지적 사항 반영 요약

| # | 심각도 | 지적 내용 | 대응 |
|---|--------|-----------|------|
| 1 | HIGH | `structured_data`가 `None`이면 대시보드 Jinja에서 예외 가능 | `(structured_data or {})` 가드 적용 |
| 2 | HIGH | `payments`/`payment` 키 불일치로 금액/체크 상태 소실 가능 | `_erpNormalizePaymentData()`로 로드 시 정규화 + 전체 저장 보존 |
| 3 | HIGH | 토글 응답에 `*_confirmed_by_user_id`가 없으면 다음 저장에서 null 덮어쓰기 가능 | 토글 API가 `payment` 전체 객체 반환 |
| 4 | HIGH | 토글과 전체 저장이 동시에 돌면 마지막 write가 상태를 덮어쓸 수 있음 | `_paymentTogglePending` 플래그 + 응답 후 전체 `payment` 교체 |
| 5 | MED | 권한 검증 누락 위험 | `@role_required(['ADMIN', 'MANAGER', 'STAFF'])` 명시 |
| 6 | MED | `confirmed_by`만 저장하면 사용자 식별 안정성이 낮음 | `name` + `user_id` 병행 저장 |
| 7 | MED | legacy/non-Beta 주문까지 뱃지가 노출될 위험 | 표시 대상을 `is_erp_beta` 주문으로 제한 |
| 8 | MED | 실측 대시보드 고객 셀 폭 부족 | 고객 컬럼 150px + `flex-wrap` 래퍼 추가 |

---

## 8. 파일별 변경 범위

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 1 | `static/css/erp-pro.css` | 뱃지/토글 버튼 스타일 + `erp-payment-badge-row` 추가 |
| 2 | `apps/api/erp_orders_structured.py` | payment-confirm 토글 API 추가 |
| 3 | `templates/partials/erp_beta_tab.html` | 예약금/잔금 체크 버튼 삽입 |
| 4 | `templates/partials/erp_beta_js.html` | 정규화 헬퍼, 로드, 수집, 토글 이벤트, 저장 직렬화 추가 |
| 5 | `templates/erp_measurement_dashboard.html` | 고객 컬럼 폭 조정 + ERP Beta 전용 뱃지 Jinja 추가 |
| 6 | `templates/partials/erp_dashboard_grid.html` | ERP Beta 전용 뱃지 Jinja 추가 |

**총 변경량**: 약 190줄 내외, 6개 파일

---

## 9. 구현 순서

1. CSS 추가
2. API 토글 엔드포인트 추가
3. ERP Beta 탭 체크 버튼 HTML 추가
4. JS 정규화 헬퍼 + 로드 + 수집 + 이벤트 핸들러 구현
5. 실측 대시보드 뱃지 추가
6. ERP 프로세스 대시보드 뱃지 추가

---

## 10. 검증 방법

1. **앱 시작 확인**: `python -c "import app; print('APP_OK')"`
2. **토글 API 테스트**: ERP Beta 탭에서 예약금 입력 -> 동전 클릭 -> 빨간색/파란색 전환 -> 새로고침 후 유지 확인
3. **전체 저장 후 상태 유지**: 체크 후 다른 필드 수정 -> 저장 -> 새로고침 -> 체크 상태 유지 확인
4. **실측 대시보드**: ERP Beta 주문에서만 고객 이름 옆 동전/지폐 아이콘 표시 확인
5. **ERP 프로세스 대시보드**: ERP Beta 주문에서만 고객 이름 아래 동전/지폐 아이콘 표시 확인
6. **structured_data = NULL 주문**: 대시보드에서 500 없이 정상 렌더 확인
7. **파서 기반 주문**: `payments.deposit.amount`만 있는 주문도 ERP Beta 로드 시 예약금이 정상 표시되고 저장 후 유지 확인
8. **legacy/non-Beta 주문**: 실측/프로세스 대시보드에서 뱃지 미표시 확인
9. **긴 고객명/좁은 화면**: 실측 대시보드 고객 셀에서 자가실측/chevron/입금 뱃지가 겹치지 않고 자연 줄바꿈되는지 확인

---

## 11. 최종 실행 판정

이 문서는 다음 쟁점을 모두 닫았다.

- 토글 API 응답 계약: `payment` 전체 객체 반환으로 확정
- `payments`/`payment` 불일치: JS 정규화 헬퍼로 해소
- 실측/프로세스 표시 범위: ERP Beta 주문만으로 고정
- 실측 고객 셀 레이아웃: 폭 확대 + `flex-wrap`으로 고정

따라서 **지금 버전은 바로 구현 착수 가능한 최종판**이다.
