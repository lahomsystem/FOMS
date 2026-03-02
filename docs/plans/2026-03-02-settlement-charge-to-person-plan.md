# 비용 청구 귀속 인원(개인) 선택 기능 — 수정 계획서

**작성**: 2026-03-02  
**요구**: 영업·도면·시공(및 선택 시 공장) 선택 시 **각 구성원 개인**에 청구할 수 있게  
**기준**: 시공 완료 대시보드 비용 청구 모달·API·structured_data.settlement

---

## 1. 현황 리뷰 요약

### 1.1 비용 청구 흐름 (현재)

| 구간 | 파일 | 내용 |
|------|------|------|
| **UI** | `templates/erp_completion_dashboard.html` | 모달: 귀속 대상(select 5종), 차감 금액, 사유. **개인 선택 없음.** |
| **스크립트** | `templates/partials/erp_completion_scripts.html` | 부서·금액·사유만 수집 → `POST /api/orders/<id>/settlement/issue` |
| **API** | `apps/api/erp_orders_completion.py` | `department`, `amount`, `reason` 검증 → `deductions[]`에 `department`만 저장 |
| **저장** | `Order.structured_data.settlement` | deduction 항목: `id`, `department`, `amount`, `reason`, `created_at`, `created_by` |

### 1.2 사용자·팀 구조 (확인됨)

- **User** (`models.py`): `id`, `name`, `username`, `role`, **`team`**, `is_active`
- **team** 값: `auth.py`의 `TEAMS` — `CS`, `SALES`, `DRAWING`, `PRODUCTION`, `CONSTRUCTION`, `SHIPMENT`
- **기존 API**: `apps/api/erp_map.py` → `GET /erp/api/users?team=<TEAM>`  
  - 응답: `{ success, users: [ { id, name, team } ] }`  
  - `User.is_active == True`, `User.team == team` 필터

### 1.3 요구사항 해석

- **영업(SALES), 도면(DRAWING), 시공(CONSTRUCTION)** → 해당 팀 **구성원 개인** 선택 가능해야 함.
- **공장(PRODUCTION)** → 요청서에는 “영업, 도면, 시공”만 명시되었으나, 동일 패턴 적용 시 **생산팀 구성원**도 선택 가능하게 하는 것이 일관됨.
- **고객(CUSTOMER)** → 외부 귀속이므로 **개인 선택 없음** (부서만 또는 “고객”으로만 저장).

---

## 2. 데이터 구조 확장 (structured_data.settlement)

**기존 deduction 1건**:
```json
{
  "id": "DED-...",
  "department": "DRAWING",
  "amount": -50000,
  "reason": "...",
  "created_at": "...",
  "created_by": "관리자명"
}
```

**확장 후** (하위 호환 유지):
```json
{
  "id": "DED-...",
  "department": "DRAWING",
  "charge_to_user_id": 12,
  "charge_to_name": "홍길동",
  "amount": -50000,
  "reason": "...",
  "created_at": "...",
  "created_by": "관리자명"
}
```

- `charge_to_user_id`: (optional) 귀속 인원 User.id. 없으면 부서 귀속만.
- `charge_to_name`: (optional) 귀속 인원 표시명. 감사·리포트용, User.name과 동기화 권장.

**정책**  
- SALES, DRAWING, PRODUCTION, CONSTRUCTION: `charge_to_user_id`/`charge_to_name` 허용.  
- CUSTOMER: `charge_to_user_id`/`charge_to_name` 사용 안 함(API에서 무시).

---

## 3. 백엔드 수정 계획

### 3.1 API: `POST /api/orders/<id>/settlement/issue`

**파일**: `apps/api/erp_orders_completion.py`

| 항목 | 내용 |
|------|------|
| **요청 body 확장** | `charge_to_user_id` (optional, int) 수신. |
| **검증** | 1) `charge_to_user_id`가 있으면: 해당 User 존재·is_active. 2) 해당 User.team이 요청의 `department`와 일치(대소문자 통일 후 비교). 3) CUSTOMER일 때는 `charge_to_user_id` 있으면 무시하거나 400. |
| **저장** | deduction 항목에 `charge_to_user_id`, `charge_to_name`(User.name) 추가. 없으면 기존처럼 부서만 저장. |
| **OrderEvent.payload** | `charge_to_user_id`, `charge_to_name` 포함 권장(감사). |
| **SecurityLog** | 메시지에 귀속 인원 포함 예: `… DRAWING 홍길동(12) …` |

**팀 매핑**  
- 요청 `department`: `SALES` | `DRAWING` | `PRODUCTION` | `CONSTRUCTION` | `CUSTOMER`  
- DB `User.team`: 동일 값 사용(`erp_map` API와 일치). 팀명 정규화는 한 곳(예: auth.TEAMS 키)만 사용.

### 3.2 구성원 목록 API (기존 활용)

- **사용**: `GET /erp/api/users?team=<SALES|DRAWING|PRODUCTION|CONSTRUCTION>`  
- **변경 없음**. 시공 완료 대시보드에서 부서 선택 시 위 경로로 fetch 후 “귀속 인원” 드롭다운 채움.

---

## 4. 프론트엔드 수정 계획

### 4.1 모달 HTML

**파일**: `templates/erp_completion_dashboard.html`

- **위치**: 귀속 대상(select) **바로 아래**에 “귀속 인원” 영역 추가.
- **구성**:
  - 라벨: “귀속 인원 (선택)”
  - `<select id="erp-settlement-charge-to-user">`  
    - 기본 옵션: `value=""` → “부서만” 또는 “선택 안 함”
    - 나머지 옵션은 JS에서 부서별로 동적 채움 (해당 팀 `/erp/api/users?team=...` 결과).
  - SALES/DRAWING/PRODUCTION/CONSTRUCTION 선택 시에만 이 select 표시; CUSTOMER 선택 시 숨김.

### 4.2 스크립트

**파일**: `templates/partials/erp_completion_scripts.html`

| 항목 | 내용 |
|------|------|
| **부서 변경 시** | `#erp-settlement-department` change 이벤트: 값이 SALES/DRAWING/PRODUCTION/CONSTRUCTION이면 `/erp/api/users?team=<값>` fetch → `#erp-settlement-charge-to-user` 옵션 채우기 및 영역 표시. CUSTOMER면 옵션 비우고 영역 숨김. “부서만” 옵션 유지. |
| **모달 오픈 시** | 부서/귀속 인원 초기화: department='', charge-to-user=''. |
| **제출 시** | `charge_to_user_id`: `#erp-settlement-charge-to-user`의 value가 숫자이면 그대로, 빈값이면 생략. body에 포함. |
| **검증** | 부서·금액·사유만 필수 유지. 귀속 인원은 선택 사항. |

---

## 5. 구현 순서 제안

1. **백엔드**  
   - `api_settlement_issue`에서 `charge_to_user_id` 수신·검증(User 존재, team 일치, CUSTOMER 시 무시).  
   - deduction·OrderEvent·SecurityLog에 `charge_to_user_id`/`charge_to_name` 반영.
2. **프론트**  
   - 모달에 “귀속 인원” select 및 부서별 표시/숨김.  
   - 부서 변경 시 `/erp/api/users?team=...` 호출로 옵션 채우기.  
   - 제출 시 `charge_to_user_id` 포함.
3. **회귀**  
   - 기존처럼 “부서만” 선택 시(charge_to_user_id 없음) 동작·저장 형식 기존과 동일한지 확인.

---

## 6. 요약 체크리스트

| # | 항목 | 담당 |
|---|------|------|
| 1 | deduction 스키마에 `charge_to_user_id`, `charge_to_name` 추가(optional) | API |
| 2 | POST settlement/issue에서 charge_to_user_id 검증(User 존재, team=department) | API |
| 3 | CUSTOMER일 때 charge_to_user_id 무시 | API |
| 4 | OrderEvent.payload / SecurityLog에 귀속 인원 정보 포함 | API |
| 5 | 모달에 “귀속 인원” select 추가, 부서별 표시/숨김 | HTML |
| 6 | 부서 변경 시 `/erp/api/users?team=...`로 옵션 채우기 | JS |
| 7 | 제출 시 charge_to_user_id 전달 | JS |

이 계획서대로 적용 시 **영업·도면·시공(및 공장)** 은 부서 단위 또는 **구성원 개인** 단위로 비용 청구 가능하며, 기존 데이터와 하위 호환이 유지됩니다.

---

## 7. 구현 완료 (2026-03-02)

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 1 | deduction에 charge_to_user_id, charge_to_name 추가 | erp_orders_completion.py | ✅ |
| 2 | charge_to_user_id 검증(User 존재, team=department) | erp_orders_completion.py | ✅ |
| 3 | CUSTOMER 시 charge_to_user_id 무시 | erp_orders_completion.py | ✅ |
| 4 | OrderEvent.payload / SecurityLog 귀속 인원 포함 | erp_orders_completion.py | ✅ |
| 5 | 모달 귀속 인원 select, 부서별 표시/숨김 | erp_completion_dashboard.html | ✅ |
| 6 | 부서 변경 시 /erp/api/users?team=... 옵션 채우기 | erp_completion_scripts.html | ✅ |
| 7 | 제출 시 charge_to_user_id 전달 | erp_completion_scripts.html | ✅ |
