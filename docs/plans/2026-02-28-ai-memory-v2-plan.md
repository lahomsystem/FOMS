# FOMS AI 메모리 시스템 v2 — 상세 구축 계획서

> **작성일**: 2026-02-28
> **작성자**: AI Development System
> **실행 환경**: Cursor IDE (메인) + Antigravity (보조 호환)
> **기준 문헌**: `docs/plans/SDD.md`, `docs/plans/Alignment.md`
> **현재 브랜치**: deploy

---

## 0. 배경 및 목적

### 0.1 왜 이 작업이 필요한가

#### 문제 1: Vibe Coding 관성
현재 FOMS 개발 프로세스는 사용자가 "이거 고쳐봐"라고 말하면 AI가 즉시 코딩에 들어가는 방식입니다.
SDD.md에서 지적한 것처럼, 이 **즉흥적 방식(Vibe Coding)**은:
- 동일한 요청이라도 표현에 따라 다른 결과를 초래합니다.
- 수정 요청이 반복될수록 초기 의도에서 벗어납니다.
- AI가 "무엇을 만들지"와 "어떻게 만들지"를 동시에 고려하여 비효율적입니다.

#### 문제 2: Dumb Zone 진입
Alignment.md에서 경고한 것처럼, AI의 기억 공간이 약 40% 이상 차면 성능이 급격히 저하됩니다.
현재 FOMS에는 이를 방지하는 메커니즘이 없어서:
- 복잡한 작업일수록 대화가 길어지고 AI 성능이 떨어집니다.
- 같은 실수를 반복하거나 앞뒤가 맞지 않는 코드를 생성합니다.
- 세션 분리 없이 계속 같은 대화창에서 수정을 반복합니다.

#### 문제 3: 중장기 메모리 사장
`docs/evolution/` (16개 파일), `docs/incidents/` (4개 파일)에 훌륭한 과거 기록이 있지만:
- AI가 새 작업 시작 시 이 파일들을 자발적으로 검색하지 않습니다.
- 같은 유형의 버그가 재발해도 과거 해결 방법을 참조하지 않습니다.
- 인덱싱이 없어 어떤 파일에 어떤 내용이 있는지 알 수 없습니다.

### 0.2 목표

```
┌────────────────────────────────────────────────────────────┐
│  Before: 사용자 "고쳐봐" → AI 즉시 코딩 → 수정 반복       │
│  After:  사용자 "고쳐봐" → 조사 → 계획서 → 승인 → 코딩    │
│                                                            │
│  Before: 과거 장애 기록 → 방치                              │
│  After:  과거 장애 기록 → 인덱싱 → Research 단계에서 참조    │
│                                                            │
│  Before: 긴 대화 → Dumb Zone → 품질 저하                    │
│  After:  세션 분리 권유 → 항상 최적 성능                    │
└────────────────────────────────────────────────────────────┘
```

### 0.3 이 계획서의 사용 방법

1. **Cursor IDE**에서 이 파일을 열고 GDM(또는 다른 에이전트)에게:
   > "@이 계획서 Phase 1부터 실행해 줘"
2. 각 Phase의 작업 항목에는 `⬜ 미완료 / ✅ 완료` 표시가 있습니다.
3. 각 작업마다 **입력 파일**, **출력 파일**, **상세 스펙**이 명시되어 있어 AI가 정확히 무엇을 해야 하는지 알 수 있습니다.
4. Phase 완료 시마다 동기화 체크리스트를 반드시 확인합니다.

---

## 1. 현재 시스템 현황 (AS-IS)

### 1.1 파일 구조 현황

```
docs/
├── AI_STATUS.md          ← ✅ 단기 메모리 (40줄, 오늘 구축)
├── AI_CHANGELOG.md       ← ✅ 작업 이력 FIFO 20개 (오늘 구축)
├── DEPLOY_NOTES.md       ← 기존 유지 (배포 전용)
├── ARCHIVE_INDEX.md      ← ❌ 없음 (Phase 2에서 생성)
├── context/
│   ├── DECISIONS.md      ← ⚠️ 기록만 있고 활용 체계 없음 (48줄, 9개)
│   ├── INCIDENT_TEMPLATE.md ← 기존 유지
│   ├── INCIDENT_*.md     ← 기존 유지 (2건)
│   └── (EDIT_LOG.md, SESSION_LOG.md, COMPACT_CHECKPOINT.md ← Hook 자동 생성)
├── evolution/            ← ⚠️ 16파일, 인덱싱 없음
│   ├── BACKUP_RESTORE_VERIFICATION.md
│   ├── GDM_AUDIT_REPORT_2026-02-22.md
│   ├── GDM_AUDIT_2026-02-18.md
│   ├── GDM_AUDIT_2026-02-19.md
│   ├── GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md
│   ├── GDM_MEASUREMENT_MANAGER_FIX.md
│   ├── GDM_MEASUREMENT_MANAGER_REALTIME.md
│   ├── FOMS_PRODUCTION_SCALABILITY_ANALYSIS.md
│   ├── EVOLUTION_DECISIONS.md
│   ├── EVOLUTION_EXECUTION_REPORT_2026-02-17.md
│   ├── EXPERIMENT_LOG.md
│   ├── HYPOTHESIS_BACKLOG.md
│   ├── RADAR.md
│   └── research/ (3파일)
├── incidents/            ← ⚠️ 4파일, 인덱싱 없음
│   ├── 2026-02-22-map-geocode-not-running.md
│   ├── 2026-02-22-railway-worker-map-utils.md
│   ├── 2026-02-22-remote-geocode-diagnosis.md
│   └── 2026-02-23-503-ssl-unexpected-eof-cloudflare.md
├── guides/               ← ❌ 빈 폴더 (Phase 1에서 활용)
├── plans/                ← 과거 계획서 5개
│   ├── 이 파일 (2026-02-28-ai-memory-v2-plan.md)
│   ├── SDD.md (참고 문헌)
│   ├── Alignment.md (참고 문헌)
│   └── 과거 3개
├── context_bak_merge/    ← ❌ 불필요 잔해 (Phase 4에서 삭제)
└── memory/               ← ❌ 빈 폴더 (Phase 4에서 삭제)

.cursor/
├── hooks/
│   ├── auto_memory.py        ← ✅ AI_STATUS/CHANGELOG 자동 갱신
│   ├── session_start.py      ← ⚠️ AI_STATUS 안내만 있음. RPI 안내 없음
│   ├── session_stop.py       ← ✅ auto_memory 연동 완료
│   ├── track_edits.py        ← ✅ 기존 유지
│   ├── pre_compact.py        ← ✅ 기존 유지
│   ├── guard_shell.py        ← ✅ 기존 유지
│   └── post_task_quality_check.py ← ⚠️ 기계적 검증만. Spec 연동 없음
├── rules/
│   ├── 00-project-context.mdc ← ⚠️ RPI 프로토콜 없음
│   └── 50-win11-shell.mdc    ← ✅ 기존 유지
├── agents/
│   ├── grand-develop-master.md ← ⚠️ Spec/RPI 절차 미반영
│   ├── GDM_EXECUTION_PLAN.md   ← ⚠️ Spec/RPI 절차 미반영
│   ├── context-manager.md      ← ✅ AI_STATUS 반영 완료
│   └── (나머지 10개 에이전트)
└── hooks.json             ← ✅ 6개 Hook 등록 완료

.agents/
└── workflows/
    └── auto-status-update.md ← ✅ Antigravity 호환 완료
```

### 1.2 현재 메모리 계층 요약

| 계층 | 상태 | 파일 | 문제점 |
|:---:|:---:|---|---|
| 단기 | ✅ 완료 | AI_STATUS.md, AI_CHANGELOG.md | 없음 |
| 중기 | ⚠️ 부분 | DECISIONS.md | 활용 체계 없음, 인덱싱 없음 |
| 장기 | ⚠️ 부분 | evolution/ (16), incidents/ (4) | 검색 불가, AI 미참조 |
| 하니스 | ❌ 없음 | — | Spec 템플릿, RPI 워크플로우 전무 |

---

## 2. 구현 계획 상세

---

### Phase 1: 하니스(Harness) 기반 구축

> **목표**: Vibe Coding을 종식시키고, 모든 주요 작업에 "주문서(Spec) 먼저, 코딩 나중" 체계 확립

#### 작업 1-1: Spec 템플릿 생성 ⬜

- **생성 파일**: `docs/guides/SPEC_TEMPLATE.md`
- **목적**: 모든 주요 작업에서 AI가 사용하는 표준 주문서 양식
- **상세 스펙**:

```markdown
# [작업명] Spec
> 작성일: YYYY-MM-DD | 상태: 🔴 작성중 / 🟡 승인대기 / 🟢 승인됨 / ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
(사용자가 보게 될 최종 상태를 구체적으로 기술)

### 1.2 기능 요구사항
1. (기능 1: 구체적 동작 명세)
2. (기능 2: 구체적 동작 명세)
3. ...

### 1.3 예외/제약 조건
- (예외 상황이 어떻게 처리되어야 하는지)
- (하지 않아야 할 것)

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| path/to/file.py | (어떤 함수/로직을 수정) |

### 2.2 아키텍처 방향
- (기존 패턴 준수 / 신규 패턴 도입 여부)
- (참고할 기존 코드: 어떤 파일의 어떤 패턴)

### 2.3 의존성 및 영향 범위
- (이 변경이 영향을 주는 다른 모듈)
- (DB 마이그레이션 필요 여부)

## 3. Steps — 실행 단계
- [ ] Step 1: (구체적 행동)
- [ ] Step 2: (구체적 행동)
- [ ] Step 3: (구체적 행동)

## 4. 검증 기준
- [ ] `python -c "import app"` 통과
- [ ] 해당 페이지 200 OK 확인
- [ ] 기존 테스트 통과 (pytest)
- [ ] (기능별 추가 검증 기준)

## 5. 참고 자료
- 관련 결정: DECISIONS.md 항목 (있으면)
- 관련 인시던트: incidents/ 파일 (있으면)
- 관련 진화 보고: evolution/ 파일 (있으면)
```

- **작성 규칙**:
  - 전체 최대 **30줄** (Dumb Zone 방지)
  - What 섹션은 사용자가, How/Steps 섹션은 AI가 작성 가능
  - 반드시 사용자 승인 후 코딩 시작

---

#### 작업 1-2: RPI 워크플로우 (start-task) ⬜

- **생성 파일**: `.agents/workflows/start-task.md`
- **목적**: 새 작업 시작 시 R→P→I 순서를 강제하는 워크플로우
- **Cursor**: GDM 에이전트가 이 절차를 내재화
- **Antigravity**: `/start-task` 슬래시 커맨드로 실행
- **상세 스펙**:

```yaml
---
description: 새 작업 시작 시 RPI(조사→계획→실행) 순서를 강제하는 워크플로우
---
```

**워크플로우 본문**:

```
# 작업 시작 (RPI 프로토콜)

## 적용 범위
- 🔴 필수: DB 스키마, 권한(Auth), API 응답 규격 등 핵심 코어가 1자라도 변경되거나, 구조적 영향도가 높은 작업
- 🟢 면제: 단순 UI 변경, 타이포, 문서 수정 등 구조적 영향도가 없는 소규모 수정

## Phase R — 조사 (Research)

// turbo-all

1. `docs/AI_STATUS.md`를 읽어 현재 프로젝트 상태를 파악한다.

2. `docs/context/DECISIONS.md`에서 이번 작업과 관련된 과거 결정이 있는지 검색한다.
   - 관련 결정이 있으면: 그 결정의 이유와 영향 범위를 확인한다.
   - 없으면: 넘어간다.

3. `docs/ARCHIVE_INDEX.md`에서 이번 작업과 관련된 과거 인시던트/진화 기록이 있는지 확인한다.
   - 관련 기록이 있으면: 해당 파일을 읽고 과거 교훈을 파악한다.
   - 없으면: 넘어간다.

4. 수정 대상이 될 코드 파일을 직접 읽고 구조를 파악한다.
   - 500줄 이상 파일: Grep/검색으로 관련 구간만 확인
   - 300줄 이하 파일: 전체 읽기 허용

5. 사용자에게 조사 결과를 간결히 보고한다:
   - "현재 상태: ..."
   - "관련 과거 기록: ..."
   - "수정 대상 파일: ..."

## Phase P — 계획 (Plan)

1. `docs/guides/SPEC_TEMPLATE.md`의 양식에 따라 작업 Spec을 작성한다.

2. `docs/specs/` 폴더에 `[기능명]_SPEC.md`로 저장한다.
   - 파일명 예: `drawing-batch-delete_SPEC.md`
   - Spec 전체 최대 30줄

3. 사용자에게 Spec을 제시하고 승인을 요청한다:
   > "위 계획대로 진행할까요? 수정할 부분이 있으면 말씀해 주세요."

4. 🔴 사용자 승인이 올 때까지 코딩하지 않는다.

## Phase I — 실행 (Implement)

1. 사용자 승인 후, Spec의 Steps를 하나씩 실행한다.

2. 각 Step 완료 시마다 Spec의 체크박스를 ✅ 처리한다.

3. 🔴 **스펙 변경(Spec Change) 프로토콜**:
   - 코딩 도중 패키지 충돌이나 예상치 못한 한계로 **How(어떻게 만들지)**를 변경해야 할 경우:
   - 코드를 임의로 우회(Vibe Coding)하지 말고, 즉시 코딩을 멈춘다.
   - `SPEC.md`의 [How] 파트를 업데이트한 후 사용자에게 재승인을 요청한다.

4. 모든 Steps 완료 후:
   a. `/verify-result` 워크플로우 실행 (검증)
   b. `/auto-status-update` 워크플로우 실행 (상태 갱신)
   c. Spec 상단 상태를 `✅ 완료 (날짜)`로 변경
   d. git commit + push

5. 대화가 길어져서 AI 성능이 저하되는 느낌이 들면:
   > "현재까지의 진행 상황을 요약합니다. Dumb Zone을 방지하기 위해 
   > 새 채팅창에서 이어서 작업하시는 것을 권장합니다."
   라고 안내한다.
```

---

#### 작업 1-3: 검증 워크플로우 (verify-result) ⬜

- **생성 파일**: `.agents/workflows/verify-result.md`
- **목적**: 코딩 완료 후 결과물이 Spec 기준을 충족하는지 체계적으로 검증
- **상세 스펙**:

```yaml
---
description: 코딩 완료 후 결과물 품질을 검증하는 워크플로우
---
```

**워크플로우 본문**:

```
# 결과 검증

// turbo-all

1. `python -c "import app; print('OK')"` 실행하여 import 오류가 없는지 확인한다.

2. 현재 작업의 Spec 파일(`docs/specs/*_SPEC.md`)을 읽는다.

3. Spec의 "4. 검증 기준" 섹션의 항목을 하나씩 점검한다.
   - 통과하면 ✅ 표시
   - 실패하면 ❌ 표시 + 원인 기술

4. 수정한 파일에 대해 기본 품질 점검:
   - 에러 처리(try-except): API 엔드포인트에 적절한 에러 처리가 있는가?
   - 하드코딩 변수: 비밀키, DB URL 등이 하드코딩되지 않았는가?
   - SQL Injection: raw SQL 사용 시 파라미터 바인딩이 되었는가?
   - XSS: 사용자 입력이 |safe 없이 렌더링되는가?

5. 모든 항목이 통과하면:
   > "✅ 검증 완료. 모든 기준을 충족합니다."

6. 실패 항목이 있으면:
   > "❌ 검증 실패. 아래 항목을 수정해야 합니다:
   > - [실패 항목 목록]
   > 수정을 진행할까요?"
```

---

#### 작업 1-4: Spec 저장 폴더 생성 ⬜

- **생성 폴더**: `docs/specs/`
- **목적**: 개별 작업의 Spec 파일이 저장되는 전용 폴더
- **규칙**: 
  - 완료된 Spec은 삭제하지 않고 상단에 `✅ 완료` 기록 → 장기 메모리 역할
  - 3개월 이상 된 완료 Spec은 정기적으로 삭제 가능

---

### Phase 2: 장기 메모리 인덱싱

> **목표**: 과거 장애·분석·계획 기록을 AI가 Research 단계에서 빠르게 찾을 수 있게 인덱싱

#### 작업 2-1: 아카이브 인덱스 생성 ⬜

- **생성 파일**: `docs/ARCHIVE_INDEX.md`
- **목적**: evolution/, incidents/, plans/의 전 파일을 1줄 요약으로 인덱싱
- **갱신 규칙**: evolution/incidents/plans에 새 파일 추가 시 이 파일도 함께 갱신
- **상세 스펙**:

```markdown
# 프로젝트 아카이브 인덱스
> AI가 Research 단계에서 관련 과거 기록을 빠르게 찾기 위한 목차.
> 새 파일 추가 시 반드시 이 인덱스도 갱신할 것.

## 장애 기록 (docs/incidents/)
| 파일 | 날짜 | 키워드 | 요약 |
|------|------|--------|------|
| 2026-02-22-map-geocode-not-running.md | 02-22 | 지도, geocode, RQ | geocode 미실행 원인: RQ Worker 미연결, Fallback 동기 처리 추가 |
| 2026-02-22-railway-worker-map-utils.md | 02-22 | Railway, Worker, 지도 | Railway Worker 서비스 지도 유틸 경로 문제 |
| 2026-02-22-remote-geocode-diagnosis.md | 02-22 | geocode, 원격, 진단 | 원격 환경 geocode 실패 진단 (카카오 API, 환경변수) |
| 2026-02-23-503-ssl-unexpected-eof-cloudflare.md | 02-23 | SSL, 503, Cloudflare | Cloudflare SSL EOF 에러, R2 업로드 간헐적 실패 |

## 장애 기록 (docs/context/)
| 파일 | 날짜 | 키워드 | 요약 |
|------|------|--------|------|
| INCIDENT_RAILWAY_GEVENT_SOCKET_2026-02-20.md | 02-20 | Railway, gevent, socket | gevent monkey-patch socket 충돌 |
| INCIDENT_SOCKETIO_CONNECTION_2026-02-20.md | 02-20 | Socket.IO, 연결, 400 | Socket.IO 연결 실패 (400 에러) 분석 |

## 기술 분석 (docs/evolution/)
| 파일 | 키워드 | 요약 |
|------|--------|------|
| GDM_AUDIT_REPORT_2026-02-22.md | 감사, 품질 | 전체 코드 품질 감사 62/100, 긴급 3건 |
| GDM_AUDIT_2026-02-19.md | 감사, 품질 | ERP 분리 후 감사 |
| GDM_AUDIT_2026-02-18.md | 감사, 품질 | ERP 분리 감사 72/100 |
| GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md | 백업, Socket.IO | 백업 시 Socket.IO 콘솔 에러 분석 |
| GDM_MEASUREMENT_MANAGER_FIX.md | 실측, 담당자 | 실측 담당자 지정 버그 수정 |
| GDM_MEASUREMENT_MANAGER_REALTIME.md | 실측, 실시간 | 실측 실시간 업데이트 분석 |
| FOMS_PRODUCTION_SCALABILITY_ANALYSIS.md | 확장성, 성능 | Production 확장성 분석 |
| BACKUP_RESTORE_VERIFICATION.md | 백업, 복원 | 백업/복원 검증 절차 |
| EVOLUTION_DECISIONS.md | 진화, 결정 | 시스템 진화 결정 기록 |
| EVOLUTION_EXECUTION_REPORT_2026-02-17.md | 진화, 실행 | 2/17 진화 실행 보고 |
| HYPOTHESIS_BACKLOG.md | 가설, 백로그 | 기술 가설 백로그 |
| RADAR.md | 기술, 레이더 | 기술 트렌드 레이더 |

## 기술 분석 — 리서치 (docs/evolution/research/)
| 파일 | 키워드 | 요약 |
|------|--------|------|
| CENTER_OPERATING_MODEL.md | 운영, 모델 | 센터 운영 모델 분석 |
| LATEST.md | 최신, 리서치 | 최신 기술 리서치 종합 (11KB) |
| reports/ | 보고서 | 리서치 보고서 하위 폴더 (1파일) |

## 설계 계획 (docs/plans/)
| 파일 | 키워드 | 요약 |
|------|--------|------|
| 2026-02-22-phase-c-map-design.md | 지도, geocode | Phase C 지도 geocode 설계 |
| 2026-02-22-phase-d-direct-upload-design.md | R2, 업로드 | Phase D Direct R2 Upload 설계 |
| 2026-02-22-railway-multi-user-scalability-plan.md | Railway, 확장 | 다중 사용자 확장 계획 |
| SDD.md | SDD, 방법론 | Spec Driven Development 요약 |
| Alignment.md | RPI, Dumb Zone | AI 생산성/Alignment 방법론 |
```

---

#### 작업 2-2: DECISIONS.md 고도화 ⬜

- **수정 파일**: `docs/context/DECISIONS.md`
- **변경 사항**:
  1. 각 결정에 `키워드` 태그 추가 (AI Grep 검색 효율화)
  2. 최대 **15개** 유지 규칙 명시 (초과 시 가장 오래된 것을 evolution/로 이동)
  3. 헤더에 규칙 설명 추가
- **변경 예시**:

현재:
```markdown
### [2026-02-27] 도면 파일 생명주기 설계 확정
- **결정**: 발송 시 R2 물리 삭제 금지, 수령 확정 시 일괄 정리
```

변경 후:
```markdown
### [2026-02-27] 도면 파일 생명주기 설계 확정
- **키워드**: 도면, R2, 파일삭제, 생명주기
- **결정**: 발송 시 R2 물리 삭제 금지, 수령 확정 시 일괄 정리
```

---

### Phase 3: Dumb Zone 방어 메커니즘

> **목표**: AI가 기억 공간 40%를 넘기기 전에 자동으로 세션 분리를 유도하고, RPI 순서를 강제

#### 작업 3-1: 00-project-context.mdc 갱신 ⬜

- **수정 파일**: `.cursor/rules/00-project-context.mdc`
- **변경 사항**: 기존 `## 새 세션 시작 시 (필수)` 섹션(15~18줄)을 **RPI 통합 버전으로 대체(Replace)**
  - ⚠️ "추가"가 아닌 **"대체"** — 기존 섹션과 역할이 겹치므로 하나로 합침
- **변경 전** (15~18줄):
```markdown
## 새 세션 시작 시 (필수)
1. `docs/AI_STATUS.md` 읽기 → **50줄로 전체 상황 파악**
2. 이전 작업 이력 필요 시 → `docs/AI_CHANGELOG.md` 참조
3. 아키텍처 결정 필요 시 → `docs/context/DECISIONS.md` 참조
```
- **변경 후**:
```markdown
## 새 세션 시작 시 + 작업 프로토콜 (RPI — 필수 준수)
1. `docs/AI_STATUS.md` 읽기 → **50줄로 전체 상황 파악**
2. **핵심 코어 변경(DB/Auth/API) 포함 작업** → RPI 프로토콜 필수:
   - Research: `DECISIONS.md` + `ARCHIVE_INDEX.md`에서 관련 과거 기록 조사
   - Plan: `docs/guides/SPEC_TEMPLATE.md` 기반 Spec 작성 → 사용자 승인 대기
   - Implement: 승인 후 코딩 → `/verify-result` → `/auto-status-update` 실행
3. **단순 UI 변경/타이포** → 바로 코딩 허용
4. **대화가 길어지면** → 핵심 요약 후 새 세션 권유 (Dumb Zone 회피)
```

---

#### 작업 3-2: session_start.py 갱신 ⬜

- **수정 파일**: `.cursor/hooks/session_start.py`
- **변경 사항**: agentMessage에 RPI 안내 + Dumb Zone 경고 추가
- **변경할 코드** (71~72번 줄 부근):

현재:
```python
system1_message = "\n[SYSTEM] 새 세션입니다. `docs/AI_STATUS.md`를 읽어 현재 상황을 파악하세요. 이전 작업 이력이 필요하면 `docs/AI_CHANGELOG.md`를 참조하세요."
```

변경 후:
```python
system1_message = """
[SYSTEM] 새 세션입니다.
1. `docs/AI_STATUS.md`를 읽어 현재 상황을 파악하세요.
2. 새 기능/중대형 수정이면 반드시 조사(R)→계획(P)→실행(I) 순서를 따르세요.
   - 조사: DECISIONS.md, ARCHIVE_INDEX.md에서 관련 과거 기록 검색
   - 계획: docs/guides/SPEC_TEMPLATE.md 기반으로 Spec 작성 → 사용자 승인 대기
   - 실행: 승인 후 코딩 시작
3. 대화가 길어지면 핵심을 요약하고 새 세션을 권유하세요 (Dumb Zone 회피).
"""
```

---

#### 작업 3-3: post_task_quality_check.py 갱신 ⬜

- **수정 파일**: `.cursor/hooks/post_task_quality_check.py`
- **변경 사항 1**: Spec 파일이 존재하면 Spec 기준으로 검증하도록 안내 추가
- **변경 사항 2**: `ARCHIVE_INDEX.md` 누락 방지 메시지 안내 추가
- **변경할 코드** (56~67번 줄 부근의 reminder_msg):

현재 reminder_msg에 추가:
```python
# 1. Spec 기반 검증 안내 추가
spec_dir = os.path.join(project_root, "docs", "specs")
if os.path.exists(spec_dir):
    specs = [f for f in os.listdir(spec_dir) if f.endswith("_SPEC.md") and not f.startswith(".")]
    if specs:
        latest_spec = sorted(specs)[-1]
        reminder_msg += f"\n4. 현재 작업의 Spec(`docs/specs/{latest_spec}`)이 존재합니다. Spec의 검증 기준도 확인하세요."

# 2. ARCHIVE_INDEX.md 항목 누락 방지 안내
reminder_msg += "\n5. evolution/ 이나 incidents/ 에 새 파일을 추가했다면, `docs/ARCHIVE_INDEX.md`에도 반드시 인덱싱을 추가하세요."
```

---

### Phase 4: 동기화 및 정리

> **목표**: GDM 에이전트 파일 최종 동기화 + 불필요 파일 정리

#### 작업 4-1: GDM 에이전트 동기화 ⬜

- **수정 파일 1**: `.cursor/agents/grand-develop-master.md`
- **변경 위치**: "오케스트레이션 프로토콜" 섹션 (192번 줄 부근)
- **변경 사항**: System 2 경고에 RPI 절차 추가

현재:
```
**🚨 [SYSTEM 2 경고] 서브에이전트에게 실제 코딩 작업을 분배하기 전에, 무조건 
`docs/AI_STATUS.md` 와 `docs/AI_CHANGELOG.md` 를 읽어 현재 상태를 파악해야 하며, 
작업 계획 수립 후 사용자에게 승인을 요청하고 대기해야 합니다. 승인 전 코딩 절대 금지. 🚨**
```

변경 후:
```
**🚨 [SYSTEM 2 경고] 새 기능/중대형 수정 시 반드시 RPI 프로토콜을 따르세요:
1. Research: `AI_STATUS.md` + `ARCHIVE_INDEX.md` + `DECISIONS.md` 조사
2. Plan: `docs/guides/SPEC_TEMPLATE.md` 기반 Spec 작성 → `docs/specs/` 저장
3. 사용자 승인 대기 (승인 전 코딩 절대 금지)
4. Implement: 승인 후 코딩 → `/verify-result` → `/auto-status-update`
소규모 수정(1~2줄, 타이포)은 바로 진행 가능. 🚨**
```

- **수정 파일 2**: `.cursor/agents/GDM_EXECUTION_PLAN.md`
- **변경 위치**: §1.2.5 System 2 강제 대기 프로토콜 (41~45번 줄)
- **변경 사항**: 기존 항목 1~3 **전체를 교체** (항목 1만이 아님)

현재 (43~45줄, 항목 1~3 전체):
```
1. `docs/AI_STATUS.md`와 `docs/AI_CHANGELOG.md` 확인 후 작업 방향 설정.
2. 문서 작성 후 사용자에게 "**승인 대기 요청**".
3. 사용자가 승인하기 전까지는 절대 코딩 및 서브에이전트 태스크 시작 금지.
```

변경 후 (항목 1~4):
```
1. `docs/AI_STATUS.md` 확인 → `docs/ARCHIVE_INDEX.md`로 관련 과거 기록 조사.
2. `docs/guides/SPEC_TEMPLATE.md` 기반으로 작업 Spec 작성 → `docs/specs/`에 저장.
3. 사용자에게 Spec 제시 후 "**승인 대기 요청**".
4. 사용자가 승인하기 전까지는 절대 코딩 및 서브에이전트 태스크 시작 금지.
```

---

#### 작업 4-2: 불필요 폴더/파일 삭제 ⬜

| 대상 | 이유 |
|------|------|
| `docs/context_bak_merge/` | 과거 백업 잔해. 1파일만 있고 더 이상 참조 없음 |
| `docs/memory/` | 빈 폴더. CONTEXT.md, TODO.md 삭제 후 빈 상태 |

---

#### 작업 4-3: git commit + push ⬜

- 모든 변경사항을 staging
- 커밋 메시지: `feat: AI 메모리 v2 구축 — RPI 워크플로우, Spec 템플릿, 아카이브 인덱스, Dumb Zone 방어`
- deploy 브랜치에 push

---

## 3. 완료 검증 체크리스트

모든 Phase 완료 후 아래 **전부 ✅**여야 완료입니다:

### 파일 존재 검증
- [ ] `docs/guides/SPEC_TEMPLATE.md` 존재
- [ ] `docs/specs/` 폴더 존재 (빈 폴더 OK)
- [ ] `docs/ARCHIVE_INDEX.md` 존재
- [ ] `.agents/workflows/start-task.md` 존재
- [ ] `.agents/workflows/verify-result.md` 존재
- [ ] `.agents/workflows/auto-status-update.md` 존재 (기존)

### 파일 내용 검증
- [ ] `AI_STATUS.md` ≤ 50줄
- [ ] `DECISIONS.md` 각 결정에 키워드 태그 존재
- [ ] `ARCHIVE_INDEX.md`에 evolution/ 전 13파일 + research/ 하위 3파일 인덱싱
- [ ] `ARCHIVE_INDEX.md`에 incidents/ 전 4파일 인덱싱 + context/ 인시던트 2파일
- [ ] `00-project-context.mdc`에 "작업 프로토콜 (RPI)" 섹션 존재
- [ ] `session_start.py` agentMessage에 RPI + Dumb Zone 안내 존재
- [ ] `grand-develop-master.md` System 2에 RPI 프로토콜 포함
- [ ] `GDM_EXECUTION_PLAN.md` §1.2.5에 Spec 절차 포함

### 정리 검증
- [ ] `docs/context_bak_merge/` 삭제됨
- [ ] `docs/memory/` 삭제됨

### 배포 검증
- [ ] git commit 완료
- [ ] git push origin deploy 완료

---

## 4. 위험 분석 및 대응

| # | 위험 | 영향도 | 확률 | 대응 방안 |
|:---:|---|:---:|:---:|---|
| R1 | RPI가 너무 무거워서 소규모 수정에도 Spec 작성 강요 | 높음 | 중 | 파일 개수가 아닌 "핵심 모듈(DB/Auth/API Req-Res) 변경 포함 여부"로 필수 기준 명확화 |
| R2 | Spec 문서가 길어져서 새로운 Dumb Zone 유발 | 중 | 중 | Spec 최대 30줄 제한 명시. 상세 구현은 코드 주석으로 |
| R3 | ARCHIVE_INDEX 갱신 누락 | 중 | 높 | 작업 검증 Hook(`post_task_quality_check.py`)에 갱신 안내 포함시켜 기계적 알림 제공 |
| R4 | Cursor hooks와 Antigravity workflows 내용 불일치 | 낮 | 낮 | Hooks = 자동화 본체, Workflows = 동일 절차의 수동 버전. 핵심 로직은 동일하게 유지 |
| R5 | 사용자가 RPI를 번거로워하여 무시 | 중 | 중 | session_start Hook이 매 세션 안내하여 습관화 유도. 효과 체감 후 자연스럽게 정착할 것으로 기대 |

---

## 5. 기대 효과

| 지표 | AS-IS (현재) | TO-BE (구축 후) |
|---|---|---|
| 새 세션 상황 파악 | AI_STATUS 40줄 읽기 (2초) | AI_STATUS 40줄 + 필요 시 ARCHIVE_INDEX로 과거 검색 (5초) |
| 작업 품질 일관성 | Vibe Coding → 수정 3~5회 반복 | Spec 승인 → 1~2회로 완료 |
| Dumb Zone 진입 빈도 | 장시간 대화에서 빈번 | 세션 분리 유도로 거의 발생 안 함 |
| 과거 장애 재발 | incidents 파일 있으나 AI 미참조 | ARCHIVE_INDEX → Research에서 필수 참조 |
| 사용자-AI 정렬 | 코딩 후 수습 (事後 정렬) | Spec 승인 (事前 정렬, Mental Alignment) |
| 중장기 지식 활용률 | ~10% (우연히 발견 시에만) | ~80% (인덱싱 + Research 의무 조회) |

---

## 6. 실행 지시

이 계획서를 승인하면 다음 순서로 실행합니다:

```
Phase 1 (하니스 구축):     작업 1-1 → 1-2 → 1-3 → 1-4
Phase 2 (장기 메모리):     작업 2-1 → 2-2
Phase 3 (Dumb Zone 방어):  작업 3-1 → 3-2 → 3-3
Phase 4 (동기화/정리):     작업 4-1 → 4-2 → 4-3
```

> **예상 소요**: 약 15~20분
> **생성 파일**: 5개 신규 + 1개 폴더
> **수정 파일**: 5개
> **삭제**: 2개 폴더
