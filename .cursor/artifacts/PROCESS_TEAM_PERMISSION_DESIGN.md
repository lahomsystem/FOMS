# 프로세스별 수정 권한 설계 (관련팀 + 엄격 담당제)

**기준 문서**: [FOMS_PROCESS_BLUEPRINT_V3.md](./FOMS_PROCESS_BLUEPRINT_V3.md)  
**연관 문서**: [ASSIGNEE_AND_CHANGE_LOG_DESIGN_V2.md](./ASSIGNEE_AND_CHANGE_LOG_DESIGN_V2.md) (담당자/로그 상세)  
**설계 원칙**: 책임소지 명확화를 위해, 일반 단계는 팀 기반, 핵심 단계(영업/도면)는 지정 담당자 기반으로 운영한다.

---

## 1. 핵심 정책

### 1.1 권한 모델

- **ADMIN**: 전체 수정 가능.
- **MANAGER**: 기본은 일반 사용자와 동일. 단, `긴급 오버라이드` 플래그 + 사유 입력 시에만 우회 가능(모든 우회는 강제 로그).
- **STAFF**: 정책에 따라 허용된 범위 내에서만 수정 가능.

### 1.2 단계별 권한 방식

| 영역 | 권한 방식 | 목적 |
|------|-----------|------|
| CS / PRODUCTION / CONSTRUCTION / AS | 팀 기반 | 운영 유연성 |
| **SALES(영업)** | **지정 인원만 변경 가능 (엄격 담당제)** | 책임소지 명확화 |
| **DRAWING(도면)** | **지정 인원만 변경 가능 (엄격 담당제)** | 책임소지 명확화 |

---

## 2. 현재 구조(As-Is)에서의 문제

- 대부분 `@role_required(['ADMIN','MANAGER','STAFF'])`로 열려 있어 팀/담당자 경계가 약함.
- `drawing_assignees`는 일부 API에서만 쓰이고, 영업 담당은 이름 기반이라 일관성이 낮음.
- 핵심 변경 API(생산/시공/CS/AS/도면 등)에 책임 추적용 표준 변경 로그가 누락된 지점이 있음.

---

## 3. 변경 설계(To-Be)

### 3.1 엄격 담당제 대상 정의

- **영업 도메인(SALES_DOMAIN)** 예시:
  - `MEASURE`, `CONFIRM` 단계의 승인/상태 변경
  - 도면 수령 확인(영업 확인)
- **도면 도메인(DRAWING_DOMAIN)** 예시:
  - 도면 전달/재전달/수정요청 처리
  - 도면 리비전 완료

> 위 도메인은 팀 전체가 아니라 **해당 주문에 지정된 담당자만** 변경 가능.

### 3.2 담당자 데이터 표준화

- `structured_data.assignments` 하위에 표준 키 사용:
  - `sales_assignee_user_ids: number[]` (영업 지정 인원)
  - `drawing_assignee_user_ids: number[]` (도면 지정 인원)
  - 기존 `drawing_assignees`는 호환 유지(마이그레이션용 읽기 지원)
- 주문 담당(이름 기반)만으로 권한 판단하지 않도록, 가능하면 id 기반으로 전환.

### 3.3 권한 판정 규칙

```python
def can_modify(user, order, domain, emergency_override=False, override_reason=None):
    if user.role == 'ADMIN':
        return True

    if domain in ('SALES_DOMAIN', 'DRAWING_DOMAIN'):
        assignees = get_assignee_ids(order, domain)
        if user.id in assignees:
            return True
        if user.role == 'MANAGER' and emergency_override and override_reason:
            return True
        return False

    # 일반 도메인: 팀 기반
    allowed_teams = get_allowed_teams_for_current_stage(order)
    if user.team in allowed_teams:
        return True

    if user.role == 'MANAGER' and emergency_override and override_reason:
        return True

    return False
```

### 3.4 API 적용 방향

- `app.py`
  - `api_order_quest_approve`, `api_order_quest_update_status`, `edit_order` stage 변경 시 `domain`별 권한 검사 적용.
- `apps/erp_beta.py`
  - 도면/영업 관련 API는 **엄격 담당제** 검사.
  - 생산/시공/CS/AS API는 팀 기반 + (MANAGER emergency override) 검사.

---

## 4. 예외 처리(긴급 오버라이드)

- 허용 대상: `MANAGER`, `ADMIN`.
- 조건: `override_reason` 필수, UI에서 확인 다이얼로그 필수.
- 로그: 일반 변경 로그와 별도로 `is_override=true`, `override_reason` 저장.

---

## 5. 구현 순서

1. `assignments.sales_assignee_user_ids`, `assignments.drawing_assignee_user_ids` 도입.
2. 공통 권한 유틸 `can_modify()` 구현.
3. 영업/도면 API부터 엄격 담당제 적용.
4. 그 외 단계(API) 팀 기반 검사 정리.
5. UI에서 권한 없는 버튼 비활성 + 안내 메시지.

---

## 6. 기대 효과

- 영업/도면 변경 책임자 명확화.
- 변경 권한 오남용 감소.
- 문제 발생 시 변경 주체 추적 정확도 향상.
