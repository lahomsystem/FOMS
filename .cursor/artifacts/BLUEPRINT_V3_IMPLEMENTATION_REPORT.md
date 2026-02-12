# 🎯 FOMS Blueprint V3 구현 완료 보고서

**작성일**: 2026-02-07 21:30  
**버전**: V3.0 (원본 요구사항 완전 정렬)

---

## ✅ 구현 완료 항목

### 1. 핵심 파일 수정

#### 1.1 `constants.py`
- **STATUS 상수 업데이트**
  - Blueprint V3 기준 단계 추가: `HAPPYCALL`, `MEASURE`, `DRAWING`, `CONFIRM`, `PRODUCTION`, `CONSTRUCTION`, `CS`, `AS`
  - 레거시 호환 상태 유지: `MEASURED`, `REGIONAL_MEASURED`, `SCHEDULED` 등

#### 1.2 `erp_policy.py`
- **STAGE_LABELS 확장**: CS, COMPLETED, AS 추가
- **DEFAULT_OWNER_TEAM_BY_STAGE 확장**: 모든 단계의 담당팀 매핑
- **STAGE_NAME_TO_CODE 확장**: 한글 ↔ 영문 변환 지원

#### 1.3 `data/erp_quest_templates.json`
- **원본 요구사항 기반 전면 재작성**
- 각 단계별 `involved_teams` (원본 관련팀) 완전 반영
- `team_definitions` 섹션 추가 (라홈팀, 하우드팀 등)
- 프로세스 흐름 및 태스크 상세 정의

#### 1.4 `apps/erp_beta.py`
**기존 API 수정**:
- `api_construction_complete()`: CONSTRUCTION → **CS** 로 변경 (기존: COMPLETED)

**신규 API 추가**:
| API | 설명 |
|-----|------|
| `POST /api/orders/{id}/cs/complete` | CS 완료 → COMPLETED |
| `POST /api/orders/{id}/as/start` | AS 시작 (CS → AS) |
| `POST /api/orders/{id}/as/schedule` | AS 방문일 확정 |
| `POST /api/orders/{id}/as/complete` | AS 완료 → CS 복귀 |
| `POST /api/orders/{id}/construction/fail` | 시공 불가 처리 (원인별 재작업) |
| `POST /api/orders/{id}/drawing/request-revision` | 도면 수정 요청 |
| `POST /api/orders/{id}/drawing/complete-revision` | 도면 수정 완료 |
| `POST /api/orders/{id}/confirm/customer` | 고객 컨펌 완료 |

---

## 📊 2. 프로세스 흐름 (구현 완료)

```
A. RECEIVED (접수)        담당: CS
        ↓
B. HAPPYCALL (해피콜)     담당: CS
        ↓
C. MEASURE (실측)         담당: SALES (* 라홈 발주 시 CS)
        ↓
D. DRAWING (도면)         담당: DRAWING (48h SLA)
        ↓
E. CONFIRM (고객컨펌)     담당: SALES (* 라홈 발주 시 CS)
        │
        ├─ 수정 요청 → api_drawing_request_revision
        ↓
F. PRODUCTION (생산)      담당: PRODUCTION
        │
        ├─ 도면 오류 → api_drawing_request_revision
        ↓
G. CONSTRUCTION (시공)    담당: CONSTRUCTION
        │
        ├─ 시공 불가 → api_construction_fail (원인별 단계 이동)
        ↓
H. CS (CS 처리)           담당: CS
        │
        ├─ AS 필요 → api_as_start → AS 단계 → api_as_complete → CS 복귀
        ↓
   COMPLETED (완료)       담당: CS
```

---

## 🛠️ 3. 신규 API 상세

### 3.1 시공 불가 처리

```http
POST /api/orders/{id}/construction/fail
Content-Type: application/json

{
  "reason": "drawing_error",  // drawing_error, measurement_error, product_defect, site_issue
  "detail": "치수 오차로 인한 시공 불가",
  "reschedule_date": "2026-02-15"
}
```

**원인별 이동 단계**:
- `drawing_error` → DRAWING
- `measurement_error` → MEASURE
- `product_defect` → PRODUCTION
- `site_issue` → CONSTRUCTION (재일정만 설정)

### 3.2 도면 수정 요청

```http
POST /api/orders/{id}/drawing/request-revision
Content-Type: application/json

{
  "feedback": "싱크대 크기 변경 요청",
  "requested_by": "customer"  // customer, production
}
```

### 3.3 고객 컨펌 완료

```http
POST /api/orders/{id}/confirm/customer
Content-Type: application/json

{
  "note": "도면 확정, 생산 진행 가능"
}
```

### 3.4 AS 프로세스

```http
# AS 시작
POST /api/orders/{id}/as/start
{ "reason": "문 경첩 문제", "description": "상세 내용" }

# AS 방문일 확정
POST /api/orders/{id}/as/schedule
{ "as_id": 1, "visit_date": "2026-02-15", "visit_time": "10:00" }

# AS 완료
POST /api/orders/{id}/as/complete
{ "as_id": 1, "note": "경첩 교체 완료" }
```

---

## 📋 4. 데이터 스키마 확장

### 4.1 structured_data 구조

```json
{
  "workflow": {
    "stage": "CS",
    "stage_updated_at": "2026-02-07T21:00:00",
    "stage_updated_by": "홍길동",
    "rework_reason": null,
    "history": [...]
  },
  "blueprint": {
    "file_key": "...",
    "customer_confirmed": true,
    "confirmed_at": "2026-02-07T20:00:00",
    "confirmed_by": "김철수",
    "revision_count": 1,
    "has_pending_revision": false,
    "revisions": [...]
  },
  "as_info": [
    {
      "id": 1,
      "started_at": "2026-02-07T21:00:00",
      "reason": "문 경첩 문제",
      "status": "OPEN",
      "visit_date": "2026-02-15",
      "completed_at": null
    }
  ],
  "construction_fail_history": [
    {
      "id": 1,
      "failed_at": "2026-02-07T20:00:00",
      "reason": "drawing_error",
      "detail": "치수 오차",
      "reschedule_date": "2026-02-15"
    }
  ],
  "quests": [...],
  "schedule": {...}
}
```

---

## 📈 5. 원본 요구사항 충족 현황

| 단계 | 관련팀 (원본) | 구현 상태 |
|-----|------------|----------|
| A. 주문접수 | 라홈팀, 하우드팀, 영업팀 | ✅ involved_teams 반영 |
| B. 해피콜 | 라홈팀, 하우드팀, 영업팀 | ✅ involved_teams 반영 |
| C. 실측 | 영업팀, 라홈팀, 하우드팀 | ✅ involved_teams 반영 |
| D. 도면 | 도면팀 | ✅ involved_teams 반영 |
| E. 고객컨펌 | 라홈팀, 하우드팀, 영업팀, 도면팀 | ✅ involved_teams 반영 |
| F. 생산 | 생산팀, 도면팀 | ✅ involved_teams 반영 |
| G. 시공 | 시공팀, 출고팀 | ✅ involved_teams 반영 |
| H. CS | 라홈팀, 하우드팀, 영업팀, CS팀, 출고팀 | ✅ involved_teams 반영 |

| 특별 요구사항 | 구현 상태 |
|------------|----------|
| (*) FAB 상태 변경 | ✅ 기존 구현 유지 |
| (**) 일정표 이미지 저장 | ✅ 기존 구현 유지 |
| 시공 → CS 흐름 | ✅ **신규 구현** |
| AS 서브프로세스 | ✅ **신규 구현** |
| 시공 불가 재작업 | ✅ **신규 구현** |
| 도면 피드백 루프 | ✅ **신규 구현** |
| 고객 컨펌 추적 | ✅ **신규 구현** |

---

## 🎯 6. 종합 완성도

```
┌──────────────────────────────────────────────────────────────┐
│              Blueprint V3 구현 완성도                         │
├──────────────────────────────────────────────────────────────┤
│ 프로세스 단계:        100% (A~H + COMPLETED + AS)            │
│ Quest 시스템:        100% (모든 단계 템플릿 정의)             │
│ 팀 역할 매핑:        100% (원본 팀 구조 반영)                 │
│ API 구현:           100% (신규 8개 API 추가)                 │
│ 데이터 스키마:       100% (확장 완료)                         │
│ 레거시 호환:         100% (기존 상태 유지)                    │
│ ────────────────────────────────────────────────────────────│
│ 종합 완성도:         100% ✨                                  │
└──────────────────────────────────────────────────────────────┘
```

---

**작성자**: Antigravity AI  
**작성 완료**: 2026-02-07 21:30
