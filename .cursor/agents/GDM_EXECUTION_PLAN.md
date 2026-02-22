# GDM(Grand Develop Master) 수행 계획표

> **목적**: GDM이 호출될 때 수행할 작업·절차를 명확히 정의  
> **기준일**: 2026-02-19  
> **원칙**: 7대 핵심 역할 기반, 트리거별 실행 순서 명시

---

## 1. 트리거별 수행 계획

### 1.1 `GDM 감사` 호출 시

| 순서 | 작업 | 담당 | 산출물 |
|------|------|------|--------|
| 1 | explore-codebase로 전체 구조 파악 | explore-codebase | 디렉터리·파일 크기·의존성 |
| 2 | code-reviewer로 품질 점검 | code-reviewer | 긴급/권장/양호 목록 |
| 3 | database-specialist로 DB 건강 진단 | database-specialist | 연결/인덱스/쿼리 상태 |
| 4 | postgres MCP로 쿼리 성능·인덱스 분석 | GDM 직접 | EXPLAIN 결과, 무효 인덱스 |
| 5 | 결과 종합 → FOMS 개발 건강 진단 보고서 작성 | GDM | `## 🏥 FOMS 개발 건강 진단 보고서` |
| 6 | 개선 로드맵 제시 (Phase 1~4) | GDM | 비전문가 언어 |

**보고서 필수 섹션**: 전체 점수, 긴급(🔴), 개선 권장(🟡), 양호(🟢)

---

### 1.2 `GDM 스택 리뷰` 호출 시

| 순서 | 작업 | 도구 | 산출물 |
|------|------|------|--------|
| 1 | 현재 스택 전수 조사 (requirements.txt, 패키지 버전) | Read, Grep | 스택 목록 |
| 2 | context7 MCP → Flask/SQLAlchemy 등 최신 문서 조회 | context7 | 호환성·deprecation |
| 3 | web_search → 업계 트렌드·보안 이슈 확인 | web_search | 외부 신호 |
| 4 | MCP 서버 생태계 검색 (self_upgrade_manifest) | Read | MCP 후보 |
| 5 | 대안 비교 매트릭스 작성 | GDM | 확장성·비용·위험도 |
| 6 | 추천안 보고 (비용/이점 포함) | GDM | 비전문가 언어 |

**참조 Skill**: `tech-stack-evaluator/SKILL.md`

---

### 1.2.5 System 2 강제 대기 프로토콜 (최우선 수행)
GDM은 산하 에이전트들에게 코딩 작업 지시를 내리기 전, **무조건** 다음 절차를 거칩니다.
1. `docs/memory/` 경로에 3대 핵심 문서(`PLAN.md`, `CONTEXT.md`, `TODO.md`) 파일 작성 지시.
2. 문서 작성 후 사용자에게 "**승인 대기 요청**".
3. 사용자가 승인하기 전까지는 절대 코딩 및 서브에이전트 태스크 시작 금지.

---

### 1.3 `GDM 방향 제시` 호출 시

| 순서 | 작업 | 도구 | 산출물 |
|------|------|------|--------|
| 1 | 사용자 요구사항 분석 | - | 요구사항 정리 |
| 2 | 현재 아키텍처 영향도 평가 | explore-codebase, Read | 영향 파일·의존성 |
| 3 | sequential-thinking MCP로 3가지+ 구현 방안 도출 | sequential-thinking | 시나리오 A/B/C |
| 4 | 각 방안 비용·시간·위험 비교 | GDM | 표 형식 |
| 5 | 추천안 + 이유 제시 | GDM | 비전문가 언어 |
| 6 | 사용자 승인 후 해당 에이전트에 실행 지시 | python-backend 등 | 작업 분배 |

---

### 1.4 `GDM 진화` 호출 시 (Rule/Skill/Hook/Agent 생성)

| 순서 | 작업 | 참조 | 산출물 |
|------|------|------|--------|
| 1 | 필요 컴포넌트 유형 결정 (Rule/Skill/Hook/Agent/MCP) | - | 대상 타입 |
| 2 | 기존 컴포넌트와 충돌 확인 | Glob, Read | 중복·충돌 여부 |
| 3 | MCP 후보 시 → self_upgrade_manifest 검토 후 등록 | - | manifest 갱신 |
| 4 | 생성 + 검증 (서버 기동, import 확인) | Write, Shell | 새 파일 |
| 5 | docs/CURRENT_STATUS.md 업데이트 | StrReplace | 상태 반영 |
| 6 | docs/context/DECISIONS.md 기록 | StrReplace | 결정 사유 |

**거버넌스**: Rule(alwaysApply)·Hook·Agent·MCP 생성 시 사용자 승인 필수

---

### 1.5 `GDM 보고` 호출 시

| 순서 | 작업 | 참조 | 산출물 |
|------|------|------|--------|
| 1 | docs/CURRENT_STATUS.md 읽기 | Read | 현재 상태 |
| 2 | TASK_REGISTRY, EDIT_LOG로 최근 변경 분석 | Read | 진행 상황 |
| 3 | 기술 부채·파일 크기 현황 정리 | Grep, Shell | 수치 |
| 4 | 비전문가 언어 보고서 작성 | GDM | 요약 + 다음 할 일 |

---

### 1.6 장애 RCA/복구 호출 시

| 순서 | 작업 | 담당 | 산출물 |
|------|------|------|--------|
| 1 | incident-rca로 타임라인/영향 범위/SEV 고정 | incident-rca | INCIDENT_TEMPLATE |
| 2 | 유형별 진단 경로 (런타임/DB/인증/배포 등) | incident-rca | 가설 보드 |
| 3 | 예외 경로·환경 드리프트·데이터 경계 점검 | incident-rca | 진단 결과 |
| 4 | 가설 보드 운영 (지지/반박 증거 병렬) | GDM | 가설별 판정 |
| 5 | Containment vs Permanent Fix 분리 적용 | incident-rca | 수정 패치 |
| 6 | test_client/HTTP/스모크로 검증 후 재발 방지 자산화 | GDM | Rule/Test/Doc |

**참조 Rule**: `14-incident-rca.mdc`

---

### 1.7 원격 서버(Railway) 동작 확인 호출 시

| 순서 | 작업 | 도구 | 산출물 |
|------|------|------|--------|
| 1 | 배포 URL 확보 (`railway domain` 또는 사용자 제공) | Railway CLI, Read | 대상 URL |
| 2 | `/`, `/login`, `/erp/` HTTP 상태 검증 (200/302) | Shell (curl/http) | 상태코드 결과 |
| 3 | 필요 시 배포 로그/브라우저 스냅샷 확인 | `railway logs`, cursor-ide-browser | 원인 단서 |
| 4 | URL·경로·상태코드 기준 결과 보고 | GDM | 원격 동작 확인 보고서 |

---

### 1.8 원격 DB 초기화 후 로컬 완전 복사 요청 시

| 순서 | 작업 | 참조 | 산출물 |
|------|------|------|--------|
| 1 | 절차서·스크립트 존재 확인 및 사용자 안내 | `docs/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `scripts/sync_local_to_railway.ps1` | 실수 없이 진행 가능 |
| 2 | 전제 조건 점검 (로컬 Postgres, Railway link, pg_dump/pg_restore) | 절차서 §1 | 진행 여부 판단 |
| 3 | (선택) 사용자 대신 단계별 실행 시 절차서 §3 순서 엄수 | BACKUP_RESTORE_VERIFICATION (주문·상태 완전 포함) | 원격 = 로컬 100% 일치 |
| 4 | 복원 후 railway_bootstrap.py + 원격 앱 검증 안내 | 절차서 §3.4, §3.5 | 완료 보고 |

**원칙**: 원격 초기화는 `pg_restore --clean --if-exists` 로 **원격에만** 수행. 로컬 Postgres는 **절대 삭제·수정하지 않음**(로컬에는 `pg_dump` 읽기만). 주문·상태·기타 데이터는 `pg_dump` 전체 덤프로 완전 반영.

---

## 2. 주기적(Recurring) 수행 계획

| 주기 | 작업 | 트리거 | 산출물 |
|------|------|--------|--------|
| **세션 시작 시** | COMPACT_CHECKPOINT → CURRENT_STATUS → TASK_REGISTRY 점진 로딩 | 08-context-engineering | 컨텍스트 복원 |
| **감사 요청 시** | 종합 감사 실행 (섹션 1.1) | 사용자 "GDM 감사" | 건강 진단 보고서 |
| **배포 전** | 백업/복원 검증 (주문·상태 완전 저장·복원) | 배포 지시 시 | BACKUP_RESTORE_VERIFICATION 또는 보고서 |
| **배포 후** | 원격 URL HTTP 검증 (`/`, `/login`, `/erp/`) | 배포 완료/점검 요청 시 | 원격 동작 확인 결과 |
| **대형 변경 전** | 아키텍처 검토, 06-safe-changes 준수 확인 | 3파일+ 수정 | 영향 범위·롤백 경로 |
| **주간** | coding-research-center 결과 검토, MCP 신호 수집 | 수동 또는 스케줄 | 적용 큐 갱신 |

---

## 3. 아키텍처 목표·현황 (참조용)

### 3.1 파일 크기 목표 vs 현재 (2026-02-19)

| 파일 | 현재 | 목표 | 상태 |
|------|------|------|------|
| app.py | 321줄 | 300줄 이하 | ⚠️ 근접 (추가 21줄 감축 필요) |
| apps/erp.py | 39줄 | 500줄 이하 | ✅ 달성 (분리 완료) |
| Python 파일(최대) | `tools/research_center/coding_research_center.py` 1,371줄 | 500줄 | ⚠️ 초과 파일 존재 |
| HTML 템플릿(최대) | `templates/wdcalculator/partials/wdcalculator_scripts.html` 3,452줄 | 800줄 | ⚠️ 초과 파일 다수 |
| JS 파일(최대) | `static/js/quick-status-change.js` 227줄 | 300줄 | ✅ 달성 |

### 3.2 app.py 300줄 달성 잔여 후보

| ID | 작업 | 예상 감소 | 비고 |
|----|------|-----------|------|
| GDM-SLIM-A1 | 초기화 설정 블록(압축/화이트노이즈/프록시) 서비스 모듈로 이동 | 8~12줄 | `services/app_init.py`와 책임 정렬 |
| GDM-SLIM-A2 | 중복/미사용 import 정리 및 초기화 주석 축약 | 5~8줄 | 기능 변경 없이 감축 |
| GDM-SLIM-A3 | 블루프린트 등록 루프화(정적 목록 기반) | 6~10줄 | 가독성 유지 조건 |
| GDM-SLIM-A4 | 빌드 정보/헬스 보조 라우트 별도 모듈화 | 3~6줄 | 운영 가시성 유지 |

### 3.3 ERP 분리 완료 후 후속 과제

| 영역 | 현재 상태 | 후속 액션 |
|------|-----------|-----------|
| ERP 진입점 | `apps/erp.py` 39줄 (경량 허브) | 신규 ERP 기능은 전용 Blueprint 파일에 추가 |
| ERP API | `apps/api/erp_*` 다수로 분리 | 공통 validation/response 유틸 재사용률 점검 |
| ERP UI | dashboard/workbench/page 단위 분리 | 800줄+ 템플릿부터 partial 재분할 우선순위화 |

**상세 계획**: `docs/plans/2026-02-17-erp-split-plan.md` (ERP-SLIM-1~12)

---

## 4. 에이전트 오케스트레이션 맵

```
                    ┌─────────────────────┐
                    │  grand-develop-     │
                    │  master (GDM)       │
                    └──────────┬──────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
       ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ explore-     │      │ code-        │      │ database-    │
│ codebase     │      │ reviewer     │      │ specialist   │
│ (구조 파악)   │      │ (품질 검증)   │      │ (DB 건강)    │
└──────────────┘      └──────────────┘      └──────────────┘
       │                       │                       │
       └───────────────────────┼───────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ python-      │      │ frontend-ui  │      │ incident-rca │
│ backend      │      │ (UI 구현)     │      │ (장애 RCA)   │
│ (API 구현)   │      │              │      │              │
└──────────────┘      └──────────────┘      └──────────────┘
       │                       │                       │
       └───────────────────────┼───────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ devops-      │      │ evolution-   │      │ migration-   │
│ deploy       │      │ architect    │      │ executor     │
│ (배포)       │      │ (업그레이드)  │      │ (마이그레이션)│
└──────────────┘      └──────────────┘      └──────────────┘
       │                       │                       │
       └───────────────────────┼───────────────────────┘
                               │
       ┌───────────────────────┴───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ context-     │      │ coding-      │      │ (기타 MCP)   │
│ manager      │      │ research-    │      │ postgres,    │
│ (기억 관리)   │      │ center       │      │ context7 등  │
└──────────────┘      └──────────────┘      └──────────────┘
```

---

## 5. 검증 체크리스트 (매 작업 완료 후)

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `python app.py` → 서버 기동
- [ ] 주요 페이지 수동 접근 (200 OK)
- [ ] ReadLints (수정 파일)
- [ ] docs/CURRENT_STATUS.md 갱신 (상태 변경 시)
- [ ] TASK_REGISTRY 갱신 (신규/완료 작업 시)

---

## 6. 금지 사항 (재확인)

- 사용자 승인 없이 기존 작동 코드 변경
- 검증 없이 기술 스택 변경 실행
- 다른 에이전트 우선 오케스트레이션 (단, 환경 제약 시 직접 수행 후 보고)
- 기술 용어만으로 사용자에게 보고


##  [System 4 규칙] 필수 보고 체계
작업을 완료한 후에는 상위 에이전트(GDM)나 사용자에게 다음 3가지 항목을 포함한 구체적인 보고서를 반드시 제출해야 합니다:
1) 무엇을 발견했는가 (What was found)
2) 무엇을 작업/수정했는가 (What was changed)
3) 왜 그런 결정을 내렸는가 (Why - 근거 및 매뉴얼 준수 여부 포함)
