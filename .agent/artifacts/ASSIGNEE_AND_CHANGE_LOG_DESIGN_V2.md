# 담당자 권한(영업/도면) + 변경 이벤트 로그 설계 V2

**기준**: 사용자 추가 요청(책임소지 명확화)  
1) 영업/도면은 지정 인원만 변경 가능  
2) 변경 로그는 관리자 또는 본인만 조회 가능, 그리고 쉽게 읽혀야 함

---

## 1. 영업/도면 지정 인원 전용 권한

### 1.1 정책 요약

- `SALES_DOMAIN`, `DRAWING_DOMAIN`은 **팀 권한만으로 변경 불가**.
- 해당 주문에 지정된 담당자(`user_id`)만 변경 가능.
- 예외:
  - `ADMIN`: 항상 허용.
  - `MANAGER`: 기본 불가, `emergency_override=true` + 사유 입력 시만 허용(강제 로그).

### 1.2 담당자 저장 구조 (id 기반 표준)

`structured_data.assignments`:

- `sales_assignee_user_ids: number[]`
- `drawing_assignee_user_ids: number[]`

호환:
- 기존 `drawing_assignees`는 읽기만 호환.
- 저장은 위 표준 키로 단일화.

### 1.3 권한 판단 함수 (의사코드)

```python
def can_modify_domain(user, order, domain, emergency_override=False, override_reason=None):
    if user.role == 'ADMIN':
        return True

    assg = ((order.structured_data or {}).get('assignments') or {})

    if domain == 'SALES_DOMAIN':
        allowed_ids = assg.get('sales_assignee_user_ids') or []
        if user.id in allowed_ids:
            return True
        if user.role == 'MANAGER' and emergency_override and override_reason:
            return True
        return False

    if domain == 'DRAWING_DOMAIN':
        allowed_ids = assg.get('drawing_assignee_user_ids') or []
        if user.id in allowed_ids:
            return True
        if user.role == 'MANAGER' and emergency_override and override_reason:
            return True
        return False

    # 일반 도메인은 기존 팀 정책
    return can_modify_by_team_policy(user, order, domain, emergency_override, override_reason)
```

### 1.4 적용 API 범위

- 영업 도메인:
  - 실측/컨펌 단계 관련 상태 변경
  - 도면 수령 확인(영업 확인)
- 도면 도메인:
  - 도면 전달/재전달/수정요청/리비전완료
  - 도면 담당자 변경

---

## 2. 변경 이벤트 로그 설계

### 2.1 요구 충족 기준

- 모든 변경 API에서 이벤트를 생성한다.
- 로그 1건만 봐도 **누가/무엇을/어떻게/언제**를 알 수 있다.
- 조회 권한은 **관리자 전체**, 일반 사용자는 **본인 로그만**.

### 2.2 로그 스키마 (OrderEvent + 표준 payload)

기본 컬럼(`OrderEvent`):
- `id`, `order_id`, `event_type`, `created_by_user_id`, `created_at`

표준 payload:

```json
{
  "domain": "DRAWING_DOMAIN",
  "action": "UPDATE_DRAWING_STATUS",
  "target": "drawing_status",
  "before": "TRANSFERRED",
  "after": "CONFIRMED",
  "change_method": "API",
  "source_screen": "erp_dashboard",
  "reason": "도면 수령 확인",
  "is_override": false,
  "override_reason": null,
  "request_id": "req-uuid"
}
```

설명:
- **누가**: `created_by_user_id` (조회 시 사용자 조인해 이름/팀 표시)
- **무엇을**: `action`, `target`
- **어떻게**: `before -> after`, `change_method`, `reason`
- **언제**: `created_at`

### 2.3 이벤트 타입 표준

- `SALES_ASSIGNEE_SET`
- `DRAWING_ASSIGNEE_SET`
- `SALES_STATUS_CHANGED`
- `DRAWING_STATUS_CHANGED`
- `QUEST_APPROVAL_CHANGED`
- `STAGE_CHANGED`
- `PRODUCTION_COMPLETED`
- `CONSTRUCTION_COMPLETED`
- `CS_COMPLETED`
- `AS_STARTED`
- `AS_COMPLETED`
- `EMERGENCY_OVERRIDE_USED`

---

## 3. 로그 조회 권한 및 API

### 3.1 권한 규칙

- `ADMIN`: 전체 조회 가능
- 비ADMIN: 본인(`created_by_user_id == me`) 로그만 조회 가능
- 비ADMIN이 타인 로그 요청 시 `403`

### 3.2 API

- `GET /api/orders/<order_id>/change-events`
  - ADMIN: 전체
  - 비ADMIN: 본인 로그만 강제 필터

- `GET /api/me/change-events`
  - 본인 로그만(여러 주문 통합)

응답 필드(가공본 포함):
- `when`
- `who_name`, `who_team`
- `what_label`
- `how_text` (`target: before -> after`)
- `reason`
- `is_override`

---

## 4. UI 설계 (아주 쉽게 표현)

### 4.1 고정 컬럼

1. **언제**
2. **누가**
3. **무엇을**
4. **어떻게**

### 4.2 표기 예시

- `2026-02-10 14:32 | 홍길동(영업) | 단계 변경 | workflow.stage: DRAWING -> CONFIRM`
- `2026-02-10 14:35 | 김도면(도면) | 도면 상태 변경 | drawing_status: TRANSFERRED -> CONFIRMED`
- `2026-02-10 14:40 | 관리자 | 긴급 오버라이드 | DRAWING_DOMAIN 변경 (사유: 고객 긴급 요청)`

### 4.3 사용성

- 필터: 기간/이벤트타입/도메인
- 기본 정렬: 최신순
- `OVERRIDE` 배지 강조
- 모바일에서도 한 줄 요약 유지

---

## 5. 구현 순서

1. `assignments.sales_assignee_user_ids`, `assignments.drawing_assignee_user_ids` 도입
2. 영업/도면 API에 엄격 담당 권한 적용
3. 변경 API 전부에 표준 OrderEvent 기록 추가
4. 조회 API를 `ADMIN 전체 / 본인만` 규칙으로 구현
5. UI 로그 화면(누가/무엇을/어떻게/언제) 적용

---

## 요약

| 요구 | 반영 설계 |
|------|-----------|
| 영업/도면 지정 인원만 변경 | SALES/DRAWING 도메인 엄격 담당제(assignee id 기반) |
| 로그 책임소지 명확화 | 표준 이벤트 payload로 누가/무엇을/어떻게/언제 강제 기록 |
| 로그 조회 권한 | ADMIN 전체, 일반 사용자 본인 로그만 |
| 쉬운 표현 | 4컬럼 고정(언제/누가/무엇을/어떻게) + 한 줄 요약 |
