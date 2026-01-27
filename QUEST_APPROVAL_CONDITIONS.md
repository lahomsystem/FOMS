# 작업 큐 퀘스트 승인 조건 정리

## 📋 개요
작업 큐(ERP Dashboard)에서 퀘스트가 다음 단계로 넘어가기 위한 승인 조건을 정리합니다.

---

## 🔄 퀘스트 상태

### 1. **OPEN** (미승인)
- 새로 생성된 퀘스트의 초기 상태
- 모든 필수 팀이 미승인 상태
- **무조건 미승인으로 처리됨**

### 2. **IN_PROGRESS** (진행중)
- 최소 1개 이상의 필수 팀이 승인 완료
- 아직 모든 팀 승인이 완료되지 않음
- **진행중 상태로 표시**

### 3. **COMPLETED** (완료)
- 모든 필수 승인 팀이 승인 완료
- **무조건 완료로 처리됨**
- 자동으로 다음 단계로 전환

---

## ✅ 승인 완료 조건

### 핵심 조건
1. **모든 필수 팀 승인 필요**
   - 각 단계별로 `required_approvals`에 지정된 모든 팀이 승인해야 함
   - `check_quest_approvals_complete()` 함수가 `True`를 반환해야 함

2. **팀 승인 확인 로직**
   ```python
   # team_approvals 구조:
   {
     "팀명": {
       "approved": True,
       "approved_by": user_id,
       "approved_by_name": "사용자명",
       "approved_at": "2026-01-27T10:00:00"
     }
   }
   ```

3. **승인 완료 판단**
   - `team_approvals`에 모든 필수 팀이 존재해야 함
   - 각 팀의 `approved` 값이 `True`여야 함
   - 하나라도 미승인 팀이 있으면 완료되지 않음

---

## 📊 단계별 필수 승인 팀

| 단계 | 한글명 | 필수 승인 팀 | 특수 규칙 |
|------|--------|-------------|----------|
| **RECEIVED** | 주문접수 | CS | - |
| **HAPPYCALL** | 해피콜 | CS | - |
| **MEASURE** | 실측 | SALES | 발주사에 "라홈" 포함 시 → CS |
| **DRAWING** | 도면 | DRAWING | - |
| **CONFIRM** | 고객컨펌 | SALES | 발주사에 "라홈" 포함 시 → CS |
| **PRODUCTION** | 생산 | PRODUCTION | - |
| **CONSTRUCTION** | 시공 | CONSTRUCTION | - |

### 특수 규칙 상세
- **실측(MEASURE)** 및 **고객컨펌(CONFIRM)** 단계:
  - 발주사(`orderer.name`)에 "라홈" 텍스트가 포함되어 있으면
  - 필수 승인 팀이 **SALES → CS**로 자동 변경됨
  - `create_quest_from_template()` 함수에서 자동 처리
  - **중요**: 변경된 `required_approvals`는 quest 객체에 저장되어 `check_quest_approvals_complete()`에서 사용됨
  - **버그 수정**: quest 객체에 `required_approvals` 필드 저장 추가 (2026-01-27)

---

## 🚀 자동 전환 프로세스

### 1. 승인 프로세스
```
사용자가 "승인" 버튼 클릭
  ↓
/api/orders/{order_id}/quest/approve API 호출
  ↓
해당 팀의 team_approvals 업데이트
  ↓
퀘스트 상태: OPEN → IN_PROGRESS (첫 승인 시)
  ↓
check_quest_approvals_complete() 호출
  ↓
모든 팀 승인 완료 확인
```

### 2. 자동 전환 조건
```python
if is_complete:  # 모든 필수 팀 승인 완료
    # 1. 현재 퀘스트 완료 처리
    current_quest["status"] = "COMPLETED"
    current_quest["completed_at"] = now.isoformat()
    
    # 2. 다음 단계로 자동 전환
    next_stage_code = get_next_stage_for_completed_quest(current_stage_name)
    
    # 3. workflow.stage 업데이트
    workflow["stage"] = next_stage_code
    
    # 4. 다음 단계의 퀘스트 자동 생성
    next_quest = create_quest_from_template(next_stage_name, username, sd)
```

### 3. 단계별 다음 단계
| 현재 단계 | 다음 단계 |
|----------|----------|
| 주문접수 (RECEIVED) | 해피콜 (HAPPYCALL) |
| 해피콜 (HAPPYCALL) | 실측 (MEASURE) |
| 실측 (MEASURE) | 도면 (DRAWING) |
| 도면 (DRAWING) | 고객컨펌 (CONFIRM) |
| 고객컨펌 (CONFIRM) | 생산 (PRODUCTION) |
| 생산 (PRODUCTION) | 시공 (CONSTRUCTION) |
| 시공 (CONSTRUCTION) | 없음 (최종 단계) |

---

## 🔍 승인 확인 로직 상세

### `check_quest_approvals_complete()` 함수 동작

1. **퀘스트 존재 확인**
   - `structured_data.quests`에서 현재 단계의 퀘스트 찾기
   - 퀘스트가 없으면 `(False, required_teams)` 반환

2. **퀘스트 상태 확인**
   - `status == "OPEN"`이고 모든 팀이 미승인 상태면 → `(False, required_teams)`
   - `status == "COMPLETED"`면 → `(True, [])`

3. **팀별 승인 확인**
   ```python
   for team in required_teams:
       approval = team_approvals.get(team)
       
       if approval is None:
           missing_teams.append(team)  # 미승인
       elif isinstance(approval, dict):
           if not approval.get("approved", False):
               missing_teams.append(team)  # 미승인
       else:
           if not bool(approval):
               missing_teams.append(team)  # 미승인
   ```

4. **결과 반환**
   - `(len(missing_teams) == 0, missing_teams)`
   - 모든 팀 승인 완료 시 `(True, [])` 반환

---

## 📝 승인 처리 흐름

### 사용자 액션
1. 작업 큐에서 주문의 퀘스트 섹션 열기
2. 미승인 팀의 "승인" 버튼 클릭
3. `approveQuestTeam(orderId, team)` 함수 호출

### 서버 처리
1. 현재 단계의 퀘스트 찾기 (없으면 생성)
2. 해당 팀의 `team_approvals` 업데이트
3. 퀘스트 상태 업데이트 (OPEN → IN_PROGRESS)
4. 모든 승인 완료 확인
5. 완료 시 다음 단계로 자동 전환 및 이벤트 기록

### 클라이언트 업데이트
1. 퀘스트 상태 새로고침
2. UI 업데이트 (승인 완료 표시)
3. 자동 전환 시 다음 단계 퀘스트 표시

---

## ⚠️ 주의사항

1. **퀘스트 생성 시점**
   - 첫 승인 시도 시 퀘스트가 없으면 자동 생성됨
   - `create_quest_from_template()` 함수로 템플릿 기반 생성
   - **중요**: 퀘스트의 `stage`는 한글 단계명("실측")으로 저장됨

2. **승인 권한**
   - `ADMIN`, `MANAGER`, `STAFF` 역할만 승인 가능
   - 관리자는 모든 퀘스트에 접근 가능

3. **상태 우선순위**
   - `OPEN` 상태는 무조건 미승인으로 처리
   - `COMPLETED` 상태는 무조건 완료로 처리
   - `IN_PROGRESS` 상태는 실제 승인 상태 확인

4. **자동 전환**
   - 모든 승인 완료 시 즉시 다음 단계로 전환
   - 다음 단계의 퀘스트가 자동 생성됨
   - 이벤트 로그에 `STAGE_AUTO_TRANSITIONED` 기록

5. **한글/영문 단계명 처리 (중요)**
   - `workflow.stage`는 영문 코드로 저장됨 (예: "MEASURE")
   - 퀘스트의 `stage`는 한글 단계명으로 저장됨 (예: "실측")
   - `check_quest_approvals_complete()` 함수는 한글/영문 둘 다 지원
   - `api_order_quest_get()` 및 `api_order_quest_approve()` 함수도 한글/영문 둘 다 확인
   - **버그 수정**: `api_order_quest_get()`에서 quest 찾을 때 한글/영문 변환 추가 (2026-01-27)

---

## 🔗 관련 파일

- **템플릿 정의**: `data/erp_quest_templates.json`
- **정책 로직**: `erp_policy.py`
  - `check_quest_approvals_complete()`
  - `create_quest_from_template()`
  - `get_required_approval_teams_for_stage()`
  - `get_next_stage_for_completed_quest()`
- **API 엔드포인트**: `app.py`
  - `/api/orders/<order_id>/quest/approve` (POST)
  - `/api/orders/<order_id>/quest` (GET)
- **UI**: `templates/erp_dashboard.html`

---

## 📌 요약

**퀘스트가 다음 단계로 넘어가기 위한 조건:**
1. ✅ 현재 단계의 모든 필수 승인 팀이 승인 완료
2. ✅ `check_quest_approvals_complete()` 함수가 `True` 반환
3. ✅ 퀘스트 상태가 `COMPLETED`로 변경
4. ✅ 자동으로 다음 단계로 전환 및 다음 단계 퀘스트 생성
