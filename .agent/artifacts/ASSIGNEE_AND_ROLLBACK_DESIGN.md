# 담당자(Assignee) 권한 + 되돌리기(Rollback) 설계

> 참고: 영업/도면 **지정 인원만 변경 가능** + **관리자/본인 로그 조회** 요구를 반영한 최신 설계는  
> `ASSIGNEE_AND_CHANGE_LOG_DESIGN_V2.md`를 우선 기준으로 사용합니다.

**선행 문서**: [PROCESS_TEAM_PERMISSION_DESIGN.md](./PROCESS_TEAM_PERMISSION_DESIGN.md) (팀 기반 수정 권한)  
**목표**  
1. 주문 건·도면 등 **세부 담당이 지정된 경우**, 해당 **담당자**가 확인/수정할 권리를 갖도록 한다.  
2. **상태를 변경한 사람**이 본인이 한 변경을 **되돌릴 수 있게** 하고, UI/API를 세련되게 구성한다.

---

## Part A. 담당자(Assignee) 기반 권한

### A.1 설계 원칙

- **포괄적 OR (inclusive)**: 아래 중 **하나라도** 해당하면 권한 있음. 담당자 지정은 권한을 **추가**하는 것이지, 팀 권한을 **대체하지 않음**.  
  1. **ADMIN** → 항상 가능.  
  2. **MANAGER** → 팀 무관하게 허용 (감독 역할).  
  3. **해당 영역 담당자(assignee)** → 세부 담당으로 지정되면 해당 영역 권한 있음.  
  4. **해당 팀 소속** → 현재 단계의 owner_team / required_approvals 팀에 속하면 권한 있음.

- **핵심 예시**:  
  - 도면 담당이 A씨로 지정 → A씨 권한 **추가됨**. DRAWING 팀 소속 B씨도 **여전히** 도면 권한 있음.  
  - 주문 건 담당이 C씨(영업팀)로 지정 → C씨는 영업팀이 아닌 단계에서도 해당 주문에 대해 확인 권한 있음.

즉, "팀"이 있어도 **주문 건 담당 / 도면 담당** 등이 지정되면, **그 담당자도** 확인·승인·전환할 수 있어야 한다. (이미 도면은 `drawing_assignees`로 일부 구현됨.)

### A.2 현재 데이터 구조

| 영역 | 저장 위치 | 식별 방식 | 비고 |
|------|------------|-----------|------|
| **주문 건 담당** | `Order.manager_name`, `structured_data.parties.manager.name` | **이름**만 저장 | `manager_user_id` 없음 → 이름 일치로만 판단 |
| **도면 담당** | `structured_data.drawing_assignees` | `[{ id, name, team }]` | **user id**로 지정. 이미 "도면 전달" 권한에 사용 중 |

### A.3 확장 제안 (데이터)

- **주문 건 담당**  
  - **옵션 1 (최소)**: 기존 `parties.manager.name`만 사용 → `user.name == manager_name`.  
  - **옵션 2 (권장)**: `structured_data.assignments.order_manager_id` (user_id) 추가 → id로 비교. 이름 변경에 강함.
- **도면 담당**: 현행 유지 (`drawing_assignees`, id 기반).
- **다른 영역**: 필요 시 `assignments.production_assignee_id` 등 확장. 1차는 "주문 건 담당 + 도면 담당"만.

### A.4 권한 판단 공통 로직 (의사코드)

```python
def can_user_act_on_order_area(user, order, area='order'):
    """
    포괄적 OR: ADMIN / MANAGER / 담당자 / 팀 중 하나라도 해당하면 True.
    담당자 지정이 팀 권한을 대체하지 않음.
    """
    if user.role == 'ADMIN':
        return True
    if user.role == 'MANAGER':
        return True

    sd = order.structured_data or {}
    assignments = sd.get('assignments') or {}

    # --- 영역별 담당자 검사 (있으면 권한 추가) ---
    if area == 'order':
        manager_id = assignments.get('order_manager_id')
        if manager_id and user.id == manager_id:
            return True
        manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
        if manager_name and user.name == manager_name:
            return True

    elif area == 'drawing':
        assignees = sd.get('drawing_assignees') or []
        if user.id in [a.get('id') for a in assignees if a.get('id')]:
            return True

    # --- 팀 검사 (담당자 유무와 무관하게 항상 체크) ---
    current_stage = get_current_stage(sd)
    allowed_teams = get_allowed_teams_for_stage(current_stage)
    if user.team in allowed_teams:
        return True

    return False
```

### A.5 적용 지점 (기존 설계와 연동)

- **PROCESS_TEAM_PERMISSION_DESIGN**에서 "팀만 검사"하던 곳을 다음처럼 확장:  
  - **Quest 승인**: 현재 단계의 `required_approvals` 팀 **또는** "주문 담당·도면 담당" 등 지정 담당자면 승인 가능.  
  - **도면 전달/수령 확인**: 도면 담당자 + 도면팀 + 주문 건 담당 + 관리자.  
  - **단계 전환(Complete API)**: 해당 단계 owner_team **또는** 해당 영역 assignee.
- 구현 시 `can_user_act_on_order_area(user, order, area)` 함수 하나로 팀 + 담당자 검사를 통합.

---

## Part B. 되돌리기(Rollback) — 변경한 사람이 되돌리기

### B.1 요구사항 정리

- **누가**: "변경한 사람" = 해당 상태 변경을 수행한 사용자만 되돌릴 수 있음 (ADMIN은 무조건 가능).  
- **무엇을**: "상태" 변경 — 단계(stage), 긴급 플래그, 일정(실측/시공), 담당팀, (선택) Quest 팀 승인 등.  
- **어디서**: **모든 영역** — edit_order뿐 아니라 Complete API, 도면 전달, Quest 승인 등 포함.  
- **어떻게**: 단일 API·패턴으로 "세련되게" 제공.  
- **시간 제한**: 변경 후 **24시간 이내**만 되돌리기 허용 (설정 가능). 오래된 변경 되돌리기는 위험.

### B.2 현재 이벤트 기록 (OrderEvent) 및 격차 분석

| 변경 지점 | OrderEvent 생성 여부 | 비고 |
|-----------|---------------------|------|
| `edit_order` → stage 변경 | **O** (STAGE_CHANGED) | from/to 있음 |
| Quest 자동 단계 전환 | **O** (STAGE_AUTO_TRANSITIONED) | from/to 있음 |
| 긴급 플래그 변경 | **O** (URGENT_CHANGED) | from/to 있음 |
| 실측일/시공일 변경 | **O** (MEASUREMENT/CONSTRUCTION_DATE_CHANGED) | from/to 있음 |
| 담당팀 변경 | **O** (OWNER_TEAM_CHANGED) | from/to 있음 |
| **생산 완료** (`api_production_complete`) | **X** | SecurityLog만 있음. **OrderEvent 추가 필요** |
| **시공 완료** (`api_construction_complete`) | **X** | **OrderEvent 추가 필요** |
| **CS 완료** (`api_cs_complete`) | **X** | **OrderEvent 추가 필요** |
| **AS 시작/완료** (`api_as_start/complete`) | **X** | **OrderEvent 추가 필요** |
| **도면 전달** (drawing transfer) | **X** | drawing_status 변경. **OrderEvent 추가 필요** |
| **도면 수령 확인** (confirm-drawing) | **X** | stage 변경 포함. **OrderEvent 추가 필요** |
| **Quest 팀 승인** (`api_order_quest_approve`) | **X** | quest 내부에만 기록. **OrderEvent 추가 필요** (2차) |

> **격차**: "모든 영역에서 되돌리기"를 지원하려면, 위 **X** 표시된 API들에 **OrderEvent 기록을 추가**해야 함.  
> 추가할 이벤트 타입: `PRODUCTION_COMPLETED`, `CONSTRUCTION_COMPLETED`, `CS_COMPLETED`, `AS_STARTED`, `AS_COMPLETED`, `DRAWING_STATUS_CHANGED`, `QUEST_TEAM_APPROVED`

### B.3 되돌리기 가능 범위 (수정)

- **1차**  
  - 기존 OrderEvent가 있는 타입: STAGE_CHANGED, URGENT_CHANGED, MEASUREMENT_DATE_CHANGED, CONSTRUCTION_DATE_CHANGED, OWNER_TEAM_CHANGED.  
  - **신규 추가**: Complete API들에 OrderEvent 추가 후, PRODUCTION_COMPLETED, CONSTRUCTION_COMPLETED, CS_COMPLETED, AS_STARTED, AS_COMPLETED도 되돌리기 대상.  
  - **조건**: `event.created_by_user_id == current_user.id` **AND** 변경 후 **24시간 이내** (ADMIN은 시간 제한 없음).  
- **2차**  
  - Quest 팀 승인, 도면 상태 변경 되돌리기.

### B.4 API 설계

- **GET** `/api/orders/<order_id>/my-recent-changes`  
  - **목적**: "내가 이 주문에서 변경한 것" 중 되돌리기 가능한 항목 목록.  
  - **응답**: `created_by_user_id == current_user`, 되돌리기 가능 event_type, 24시간 이내인 이벤트만. 최신순 N개(20).  
  - 각 항목: `event_id`, `event_type`, `payload`, `created_at`, `summary`(한글 요약), `can_revert`(시간·권한·이미 되돌림 여부 반영).

- **POST** `/api/orders/<order_id>/revert`  
  - **Body**: `{ "event_id": 123 }`.  
  - **검증**:  
    - `event.created_by_user_id == current_user.id` (ADMIN은 타인 변경도 가능).  
    - event_type이 revert 가능 목록에 포함.  
    - 변경 후 24시간 이내 (ADMIN은 무제한).  
    - 아직 되돌리지 않은 이벤트 (중복 revert 방지).  
  - **동작**: payload의 `from` 값으로 해당 필드 복원.  
  - **이벤트 기록**: `ORDER_CHANGE_REVERTED` 이벤트 저장.  
  - **응답**: 200 성공 / 403 권한 없음 / 404 이벤트 없음 / 400 이미 되돌림 또는 시간 초과.

### B.5 이벤트 타입별 복원 방법

| event_type | 복원 대상 | 복원 방법 |
|------------|-----------|-----------|
| STAGE_CHANGED | workflow.stage | payload.from → workflow.stage; order.status 동기화 |
| STAGE_AUTO_TRANSITIONED | workflow.stage | payload.from으로 stage 복원 |
| PRODUCTION_COMPLETED | workflow.stage | PRODUCTION → workflow.stage (역전환) |
| CONSTRUCTION_COMPLETED | workflow.stage | CONSTRUCTION → workflow.stage |
| CS_COMPLETED | workflow.stage | CS → workflow.stage |
| AS_STARTED | workflow.stage | payload.from(CS) → workflow.stage |
| AS_COMPLETED | workflow.stage | payload.from(AS) → workflow.stage |
| URGENT_CHANGED | flags.urgent | payload.from → flags.urgent |
| MEASUREMENT_DATE_CHANGED | schedule.measurement.date | payload.from → schedule.measurement.date |
| CONSTRUCTION_DATE_CHANGED | schedule.construction.date | payload.from → schedule.construction.date |
| OWNER_TEAM_CHANGED | assignments.owner_team | payload.from → assignments.owner_team |
| DRAWING_STATUS_CHANGED (2차) | drawing_status 등 | payload.from으로 복원 |
| QUEST_TEAM_APPROVED (2차) | quests[].team_approvals[team] | approved → false |

### B.6 Complete API에 OrderEvent 추가 (구현 전제)

각 Complete API(`api_production_complete`, `api_construction_complete` 등)에서 단계 변경 시:

```python
# 예: api_construction_complete
db.add(OrderEvent(
    order_id=order.id,
    event_type='CONSTRUCTION_COMPLETED',
    payload={'from': old_stage, 'to': 'CS'},
    created_by_user_id=user_id
))
```

이것이 있어야 **되돌리기 API가 해당 변경을 인식**할 수 있음.

### B.7 UI 제안 (세련된 방식)

- **위치**: 주문 상세/ERP 탭에서 "이 주문의 상태를 보는" 화면.  
- **표시 방식 (옵션 B 권장)**: 상태 변경 직후, 화면 하단에 **토스트/스낵바** 형태로 "방금 변경함: 단계 주문접수 → 해피콜 [되돌리기]" 표시. 일정 시간 후 자동 사라짐.  
- **목록 방식**: "내 변경 내역" 드롭다운/접이식 블록에 최근 N건. 각 항목에 "되돌리기" 버튼 (24시간 경과 시 비활성).  
- **확인**: "되돌리기" 클릭 시 확인 다이얼로그 → `POST revert`.  
- **이미 되돌린 항목**: 목록에서 "(되돌림 완료)" 표시 + 버튼 비활성.

### B.8 Quest 승인 되돌리기 (2차)

- Quest 팀 승인 시 `QUEST_TEAM_APPROVED` 이벤트 기록.
- revert 시 해당 팀의 `team_approvals[team]`을 `approved: false`로 복원.
- Quest status가 COMPLETED였으면 IN_PROGRESS로 되돌림.

---

## Part C. 구현 순서 제안

### Phase 1 — 담당자 권한
1. **데이터**: `structured_data.assignments.order_manager_id` 도입 (선택). 기존 `parties.manager.name` 유지.
2. **공통 함수**: `can_user_act_on_order_area(user, order, area)` — ADMIN OR MANAGER OR 담당자 OR 팀 (포괄적 OR).
3. **적용**: Quest 승인, 도면 전달/확정, 단계 전환 Complete API 등.

### Phase 2 — 되돌리기 기반 정비
1. **Complete API들에 OrderEvent 추가**: `PRODUCTION_COMPLETED`, `CONSTRUCTION_COMPLETED`, `CS_COMPLETED`, `AS_STARTED`, `AS_COMPLETED` (from/to 포함).
2. **되돌리기 API**: `GET my-recent-changes`, `POST revert`, `ORDER_CHANGE_REVERTED` 이벤트.
3. **이벤트별 복원 로직** 구현.
4. **UI**: 토스트/스낵바 + 목록 방식 연동.

### Phase 3 (선택) — Quest 승인·도면 상태 되돌리기
1. Quest 승인 시 `QUEST_TEAM_APPROVED`, 도면 전달 시 `DRAWING_STATUS_CHANGED` 이벤트 추가.
2. revert API에 해당 타입 추가.
3. UI에 "내가 승인한 팀 승인 취소" / "도면 상태 되돌리기" 노출.

---

## 요약

| 요구 | 설계 요약 |
|------|------------|
| **1. 담당자 권한** | **포괄적 OR**: ADMIN / MANAGER / 담당자 / 팀 중 하나라도 해당하면 권한. 담당자 지정은 권한을 **추가**, 팀 권한을 **대체하지 않음**. |
| **2. 되돌리기** | **변경한 사람**만 되돌리기 가능 (ADMIN은 모두 가능). **모든 영역** 지원을 위해 Complete API에 OrderEvent 추가. 24시간 제한. `GET my-recent-changes` + `POST revert` + `ORDER_CHANGE_REVERTED` 기록. UI는 토스트 + 목록 방식. |

이 설계대로 진행하면 "팀 + 담당자" 권한과 "내가 한 변경 되돌리기"를 체계적이고 안전하게 도입할 수 있다.
