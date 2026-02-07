# 📊 Blueprint vs Audit Report 상세 비교 분석

**작성일**: 2026-02-07 21:00  
**목적**: FOMS_FURNITURE_PROCESS_BLUEPRINT.md와 FOMS_COMPREHENSIVE_AUDIT_REPORT.md 비교 분석  
**근거 자료**: Furniture Process.md (원본 요구사항)

---

## 🔴 1. 심각한 오류 및 불일치

### 1.1 완료도 평가 불일치

| 항목 | Blueprint 평가 | Audit Report 평가 | 실제 상태 | 판정 |
|-----|---------------|------------------|----------|------|
| **전체 완성도** | 80% | 90% | ~75-80% | ❌ Audit 과대평가 |
| **프로세스 단계 구현** | 암묵적 완료 | 100% | ~90% (CS/AS 미완) | ❌ Audit 과대평가 |
| **Quest 시스템** | 언급 없음 | 100% | ~85% (COMPLETED/AS 미정의) | ❌ Audit 과대평가 |
| **Phase 1 완료도** | 미완성 | 부분 구현 | 미구현 | ⚠️ 상이한 평가 |

**분석**:
- **Audit Report가 시스템 완성도를 과대평가**했습니다.
- Blueprint는 "80% 완성도"로 평가했으나, Audit은 "90% Production-Ready"로 평가
- 실제 핵심 기능(FAB, 이미지 저장)이 미구현 상태에서 90%는 과대평가

---

### 1.2 프로세스 단계 불일치

#### Blueprint 정의 (Furniture Process.md 기반)
```
A. 주문접수 → B. 해피콜 → C. 실측 → D. 도면 → E. 고객컨펌 → F. 생산 → G. 시공 → H. CS
```
**총 8단계** (A~H)

#### Audit Report 정의
```
RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → COMPLETED → AS_WAIT
```
**총 9단계** (단, H. CS가 분리되어 COMPLETED + AS_WAIT)

#### erp_quest_templates.json 실제 정의
```json
RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION
```
**총 7단계** (COMPLETED, AS 미정의)

| 문서 | 정의된 단계 수 | 누락 단계 |
|-----|--------------|----------|
| Furniture Process.md | 8단계 (A~H) | - |
| Blueprint | 7단계 + CS 별도 | CS 통합 방식 제안 |
| Audit Report | 9단계 | - (과잉 추정) |
| **실제 구현** | **7단계** | **CS/COMPLETED/AS_WAIT** |

**판정**: ❌ **Audit Report가 미구현 단계를 구현된 것처럼 기술**

---

### 1.3 대시보드 목록 불일치

#### Blueprint 정의 (Section 1.4)
| 대시보드 | Blueprint 상태 |
|---------|---------------|
| ERP 대시보드 | ✅ 존재 |
| 실측 대시보드 | ✅ 존재 |
| 출고 대시보드 | ✅ 존재 |
| AS 대시보드 | ✅ 존재 |
| 지방 대시보드 | ✅ 존재 |
| 수도권 대시보드 | ✅ 존재 |
| 셀프실측 대시보드 | ✅ 존재 |
| 주문 목록 | ✅ 존재 |
| **생산 대시보드** | ❌ 필요 (Phase 2.3) |

#### Audit Report 주장 (Section 1.1)
> "대시보드 구현: 95% - ERP 대시보드, 실측, 출고, 생산, 시공, AS 대시보드 모두 구현"

#### 실제 확인 필요 항목
- **생산 대시보드**: `erp_production_dashboard()` - ✅ 구현됨
- **시공 대시보드**: `erp_construction_dashboard()` - ✅ 구현됨

**판정**: ⚠️ **Blueprint가 업데이트 필요** (생산/시공 대시보드 구현 완료 반영 안됨)

---

## 🟠 2. 중요 누락 사항

### 2.1 Blueprint에서 Audit이 누락한 항목

| Blueprint 항목 | Audit 언급 | 문제점 |
|---------------|-----------|--------|
| **Phase 1.2 시공 일정표 이미지화** (⭐⭐ CRITICAL) | ⚠️ 미구현으로 언급 | Audit에서 우선순위를 낮게 평가 |
| **User.team 필드 추가** | ❌ 미언급 | 팀별 역할 확장의 핵심 DB 변경 |
| **team_required 데코레이터** | ❌ 미언급 | 접근 제어 핵심 기능 |
| **blueprint.sent_at/sent_via 필드** | ❌ 미언급 | 도면 전달 추적 핵심 필드 |
| **리스크 및 주의사항 섹션** | ❌ 완전 누락 | DB 마이그레이션 리스크 등 |

### 2.2 Audit에서 Blueprint이 누락한 항목

| Audit 항목 | Blueprint 언급 | 문제점 |
|-----------|---------------|--------|
| **중복 함수 정의 (4개)** | ❌ 미언급 | 기존 코드 분석 부재 |
| **datetime import 충돌** | ❌ 미언급 | 실제 발생한 버그 |
| **Quest vs Quick Status 충돌** | ❌ 미언급 | 데이터 정합성 위험 |
| **workflow.stage vs Order.status 이원화** | ❌ 미언급 | Legacy 호환성 이슈 |

---

## 🟡 3. 평가 기준 불일치

### 3.1 Phase 진행 상황 비교

#### Phase 1 (긴급 수정)

| 항목 | Blueprint 예상 | Audit 평가 | 실제 상태 | Gap |
|-----|--------------|-----------|----------|-----|
| 1.1 CS 상태 변경 FAB | 1-2일 | "API 구현 완료, UI 필요" | API만 완료 | ⚠️ FAB UI 없음 |
| 1.2 시공 일정표 이미지 | CRITICAL 우선 | "미구현" | 미구현 | ❌ 최우선 항목 미착수 |

**Blueprint 우선순위**: 1.2 이미지화 → 1.1 FAB  
**Audit 우선순위**: 중복 함수 정리 → Quest 동기화 → ...  

**판정**: ❌ **우선순위 충돌 - Blueprint의 CRITICAL 항목을 Audit이 후순위로 밀어냄**

#### Phase 2 (프로세스 정합성)

| 항목 | Blueprint 예상 | Audit 평가 | 실제 상태 |
|-----|--------------|-----------|----------|
| 2.1 도면 전달 추적 | 필드 추가 필요 | "구현 완료" | 부분 구현 |
| 2.2 팀별 역할 확장 | User.team 필요 | "기반 구현" | owner_team만 있음 |
| 2.3 생산 대시보드 | 신규 생성 필요 | "구현 완료" | ✅ 구현됨 |

**분석**:
- 2.1: `api_order_transfer_drawing`이 구현됐지만, `sent_at`, `sent_via`, `customer_confirmed` 필드는 Blueprint 제안대로 구현되지 않음
- 2.2: `User.team` 필드가 DB에 추가되지 않음, `owner_team`은 `structured_data` 내부 필드

#### Phase 3 (고도화)

| 항목 | Blueprint | Audit | 상태 |
|-----|----------|-------|------|
| 3.1 알림 시스템 | Socket.IO 활용 | 미구현 | ❌ |
| 3.2 CS 단계 추가 | Quest 템플릿 확장 | 미구현 | ❌ |
| 3.3 대시보드 통합 뷰 | 팀별 자동 필터링 | 미구현 | ❌ |

**판정**: ✅ **Phase 3은 양쪽 문서 모두 일관되게 미구현으로 평가**

---

## 🔵 4. 기술적 불일치

### 4.1 팀 역할 정의 차이

#### Blueprint 정의 (Furniture Process.md 기반)
```
관련 팀: 라홈팀, 하우드팀, 영업팀, CS팀, 도면팀, 생산팀, 시공팀, 출고팀
```

#### Audit/erp_policy.py 정의
```python
DEFAULT_OWNER_TEAM_BY_STAGE = {
    "RECEIVED": "CS",
    "HAPPYCALL": "CS",
    "MEASURE": "SALES",
    "DRAWING": "DRAWING",
    "CONFIRM": "SALES",
    "PRODUCTION": "PRODUCTION",
    "CONSTRUCTION": "CONSTRUCTION",
}
# 정의된 팀: CS, SALES, DRAWING, PRODUCTION, CONSTRUCTION (5개)
```

| 원본 팀 | 시스템 매핑 | 문제점 |
|--------|-----------|--------|
| 라홈팀 | CS | ⚠️ 통합됨 |
| 하우드팀 | CS | ⚠️ 통합됨 |
| 영업팀 | SALES | ✅ |
| CS팀 | CS | ✅ |
| 도면팀 | DRAWING | ✅ |
| 생산팀 | PRODUCTION | ✅ |
| 시공팀 | CONSTRUCTION | ✅ |
| 출고팀 | ❌ 미정의 | ❌ 누락 |

**판정**: ⚠️ **Blueprint/Audit 모두 "출고팀" 역할을 별도로 정의하지 않음**

### 4.2 도면 전달 추적 스키마 차이

#### Blueprint 제안
```json
{
  "blueprint": {
    "file_key": "...",
    "uploaded_at": "2026-02-07T10:00:00",
    "sent_at": "2026-02-07T11:00:00",
    "sent_via": "channeltalk",
    "customer_confirmed": false,
    "confirmed_at": null
  }
}
```

#### 실제 구현 (`api_order_transfer_drawing`)
```python
# structured_data.blueprint_transfer 구조
{
    "sent_at": "...",
    "sent_via": "...",          # 구현됨
    "sent_by": "...",           # 추가됨 (Blueprint에 없음)
    "note": "..."               # 추가됨 (Blueprint에 없음)
}
# customer_confirmed, confirmed_at: 미구현
```

**판정**: ⚠️ **Blueprint 스키마와 실제 구현이 상이함. 고객 컨펌 추적 미구현**

---

## 📋 5. 체크리스트 동기화 상태

### Blueprint 체크리스트 vs 실제 구현

#### Phase 1 체크리스트
| 항목 | Blueprint | 구현 상태 | Audit 반영 |
|-----|----------|----------|-----------|
| ☐ layout.html에 FAB 추가 | 필요 | ❌ 미구현 | ⚠️ |
| ☐ quick-status-change.js 생성 | 필요 | ❌ 미구현 | ❌ |
| ☐ /api/orders/<id>/quick-status API | 필요 | ✅ 구현됨 | ✅ |
| ☐ html2canvas CDN 추가 | 필요 | ❌ 미구현 | ❌ |
| ☐ shipment-image-export.js 생성 | 필요 | ❌ 미구현 | ❌ |
| ☐ 출고 대시보드 이미지 저장 버튼 | 필요 | ❌ 미구현 | ❌ |

**Phase 1 완료율**: **1/6 (17%)**

#### Phase 2 체크리스트
| 항목 | Blueprint | 구현 상태 | Audit 반영 |
|-----|----------|----------|-----------|
| ☐ structured_data 스키마 문서화 | 필요 | ⚠️ 부분 | ❌ |
| ☐ 도면 전달 UI 추가 | 필요 | ✅ 구현됨 | ✅ |
| ☐ 고객 컨펌 상태 추적 | 필요 | ❌ 미구현 | ❌ |
| ☐ User.team 필드 마이그레이션 | 필요 | ❌ 미구현 | ❌ |
| ☐ 관리자 팀 설정 UI | 필요 | ❌ 미구현 | ❌ |
| ☐ team_required 데코레이터 | 필요 | ❌ 미구현 | ❌ |
| ☐ 생산 대시보드 라우트 | 필요 | ✅ 구현됨 | ✅ |
| ☐ 생산 대시보드 템플릿 | 필요 | ✅ 구현됨 | ✅ |
| ☐ 네비게이션 메뉴 추가 | 필요 | ✅ 구현됨 | ✅ |

**Phase 2 완료율**: **4/9 (44%)**

---

## 🎯 6. 핵심 결론

### 6.1 Blueprint 문서 문제점

| 문제점 | 심각도 | 설명 |
|--------|--------|-----|
| **최신 상태 미반영** | 🟠 HIGH | 생산/시공 대시보드 구현 완료 사실 누락 |
| **기존 코드 분석 부재** | 🟠 HIGH | 중복 함수, datetime 충돌 등 미발견 |
| **Quest 시스템 상세 분석 부재** | 🟡 MEDIUM | erp_quest_templates.json 분석 미흡 |

### 6.2 Audit Report 문제점

| 문제점 | 심각도 | 설명 |
|--------|--------|-----|
| **과대 완성도 평가** | 🔴 CRITICAL | 90%는 과대평가, 실제 75-80% |
| **Blueprint 우선순위 무시** | 🔴 CRITICAL | CRITICAL 항목(이미지 저장)을 후순위로 배치 |
| **미구현 항목 구현 주장** | 🟠 HIGH | COMPLETED/AS 단계를 구현된 것처럼 기술 |
| **Blueprint 스키마 미반영** | 🟡 MEDIUM | customer_confirmed 등 필드 분석 누락 |

### 6.3 두 문서 간 Gap 요약

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Blueprint vs Audit 불일치 요약                    │
├─────────────────────────────────────────────────────────────────────┤
│ 1. 완성도 평가: Blueprint 80% vs Audit 90% (≠10% Gap)               │
│ 2. 우선순위: Blueprint는 이미지화 최우선, Audit은 코드 정리 최우선   │
│ 3. 단계 정의: Blueprint 8단계, Audit 9단계, 실제 7단계              │
│ 4. 팀 역할: 출고팀 양쪽 모두 누락                                   │
│ 5. 스키마: customer_confirmed 필드 Audit에서 누락                   │
│ 6. Phase 1: Blueprint 17% 완료, Audit은 "부분 구현"으로 표현        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📝 7. 권장 조치

### 7.1 즉시 수정 필요

#### Blueprint 업데이트
1. **Section 1.4**: 생산 대시보드, 시공 대시보드 추가
2. **Section 2.1**: 생산/시공 대시보드 구현 완료 상태로 변경
3. **Phase 2.3**: ✅ 완료로 체크

#### Audit Report 수정
1. **Section 1.1**: 완성도 90% → 75-80%로 수정
2. **Section 1.1**: Quest 시스템 100% → 85%로 수정
3. **Section 7.2**: Blueprint CRITICAL 항목(이미지 저장)을 1순위로 변경
4. **Section 4.3.2**: 정확한 미정의 단계 명시 (COMPLETED, AS_WAIT뿐 아니라 CS도)

### 7.2 추가 문서화 필요

1. **통합 체크리스트 문서**: Phase별 완료 상태 실시간 추적
2. **스키마 문서**: structured_data 필드 정의 통합 문서
3. **팀 역할 정의서**: 8개 팀 → 5개 시스템 팀 매핑 명시

---

## 📊 8. 정확한 현재 상태 평가

### 8.1 수정된 완성도

| 항목 | 수정된 평가 |
|-----|-----------|
| **프로세스 단계** | 7/8 단계 (87.5%) - CS 미완성 |
| **대시보드** | 8/8 (100%) - 생산/시공 추가 확인 |
| **Quest 시스템** | 7/10 단계 정의 (70%) |
| **Phase 1** | 1/6 항목 (17%) |
| **Phase 2** | 4/9 항목 (44%) |
| **Phase 3** | 0/6 항목 (0%) |
| **총 체크리스트** | 5/21 항목 (24%) |
| **종합 완성도** | **~75%** |

### 8.2 최종 권장 우선순위 (Blueprint + Audit 통합)

```
1️⃣ [CRITICAL] 시공 일정표 이미지 저장 (Blueprint 1.2)
2️⃣ [CRITICAL] CS 상태 변경 FAB UI 구현 (Blueprint 1.1)
3️⃣ [HIGH] 중복 함수 정리 (Audit 4.1.1)
4️⃣ [HIGH] Quest 템플릿에 COMPLETED/AS 추가 (Audit 4.3.2)
5️⃣ [HIGH] Quest/Quick Status 동기화 (Audit 4.2.2)
6️⃣ [MEDIUM] 고객 컨펌 추적 필드 추가 (Blueprint 2.1)
7️⃣ [MEDIUM] User.team 필드 마이그레이션 (Blueprint 2.2)
```

---

**작성자**: Antigravity AI  
**버전**: v1.0  
**상태**: 분석 완료, 검토 필요
