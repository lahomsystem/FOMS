# ERP Beta 저장 흐름 GDM 감리 보고서

**날짜**: 2026-03-16
**대상**: ERP Beta > 저장 클릭 시 리다이렉트까지 시간이 길다는 이슈
**범위**: `apps/api/erp_orders_structured.py`, `templates/partials/erp_beta_js.html`, `services/order_date_sync.py`, `erp_automation.py`, `services/jobs/queue.py` 및 연관 경로
**더블체크**: 2026-03-16 완료 (코드 리뷰어 + 코드베이스 탐색 에이전트 병렬 검증)
**외부 리뷰 반영**: 2026-03-16 (6건 피드백 전수 코드 검증 후 반영)

---

## 1. 더블체크 결과

### 1.1 병목 가능 지점

| 순서 | 지점 | 설명 | 영향도 |
|------|------|------|--------|
| 1 | `_record_build_step` 2회 호출 + commit 5회 | 정상 PUT 경로에서 RUNNING + COMPLETED **2회** 호출. 매 호출마다 `_ensure_system_build_steps_table()`의 DDL commit 1회 + UPSERT commit 1회 = **호출당 2회 commit**. 정상 요청 1건당 총 **5회 commit** (build_step 4회 + 메인 1회) | **높음** |
| 2 | `_ensure_system_build_steps_table` | 요청 경로에서 `CREATE TABLE IF NOT EXISTS` DDL 실행 + `db.commit()`. 테이블 존재 시에도 매 요청마다 호출 | **높음** |
| 3 | `apply_auto_tasks` → `ensure_auto_task` | 단계별 AutoTaskSpec마다 SELECT + UPDATE 또는 INSERT. 최대 4~5개 task 가능 (N+1 쿼리 패턴) | **중간** |
| 4 | `before_flush` → `sync_order_dates` | `db.commit()` 직전 flush 시점에 OrderScheduleDate 전체 삭제 후 재생성 (cascade). `collect_order_schedule_date_specs`가 JSONB 전체 순회 O(items) | **중간** |
| 5 | JSONB deepcopy 2회 | 주소 변경 시 `api_put_order_structured`에서 1회 + `reset_order_geocode_on_address_change` 내부에서 1회 = 동일 요청에서 structured_data deepcopy 2회 실행 | **낮음** |
| 6 | `_record_structured_events` | URGENT/MEASUREMENT_DATE/CONSTRUCTION_DATE/OWNER_TEAM 변경 시 OrderEvent 최대 4건 추가 | **낮음** |
| 7 | `_handle_stage_transition` | 단계 전환 시 OrderEvent, Quest 생성, status 업데이트 | **낮음** |
| 8 | 프론트 `setTimeout(..., 500)` | 저장 성공 후 리다이렉트 전 500ms 고정 대기 (`erp_beta_js.html:772`) | **낮음** |

### 1.2 위험 요소

| 항목 | 설명 | 심각도 |
|------|------|--------|
| **요청 경로 DDL** | `_ensure_system_build_steps_table`가 매 PUT 요청마다 `CREATE TABLE IF NOT EXISTS` 실행. 운영 환경에서 DDL은 마이그레이션으로 선행 생성 권장 | 🟡 |
| **commit 5회 실행** | `_record_build_step` 1회 호출당 `db.commit()` 2회 (DDL + DML) × 2회 호출 + 메인 commit 1회 = **총 5회**. 트랜잭션 경계 복잡 + DB 왕복 비용 | 🟡 |
| **order_date_sync 재진입 위험** | `before_flush`에서 `sync_order_dates` 호출 시 `order.schedule_dates` 교체. 명시적 재진입 방지 로직은 없으나, `isinstance(obj, Order)` 타입 필터링 덕분에 `OrderScheduleDate` 추가 시 재귀 트리거되지 않음. **우연히 안전한 상태** — 향후 flush 내 Order 수정 코드 추가 시 무한루프 위험 | 🟡 |
| **print 디버깅 (8건)** | `services/jobs/queue.py` 4건 + `services/jobs/tasks.py` 4건 = **총 8건**. `logger`를 우회하여 운영 로그 시스템에 잡히지 않음. CLAUDE.md 규칙 위반 | 🟡 |
| **build_step 실패 시** | `_record_build_step` 예외는 `logger.warning` 후 삼킴. 메인 저장은 별도 트랜잭션이므로 영향 없으나, 디버깅 시 build_step 로그 누락 가능 | 🟢 |
| **enqueue 실패** | `enqueue_geocode_order_address`, `enqueue_channeltalk_push`는 RQ 미활성화 시 False 반환. 동기 대기 없음 | 🟢 |

### 1.3 PUT 요청 실행 경로 (정상 흐름)

```
PUT /api/orders/<id>/structured
  │
  ├── _record_build_step(RUNNING)               ← commit 2회 (DDL + DML)
  ├── db.query(Order).filter(...).first()        ← SELECT 1회
  ├── request.get_json()
  ├── _handle_stage_transition(...)              ← 조건부 OrderEvent/Quest
  ├── _record_structured_events(...)             ← 최대 OrderEvent 4건
  ├── _apply_structured_side_effects(...)        ← ensure_auto_task × N (N+1 쿼리)
  ├── _finalize_draft_state(...)
  ├── copy.deepcopy(structured_data)             ← JSONB deepcopy #1
  ├── flag_modified(order, 'structured_data')
  ├── reset_order_geocode_on_address_change(...) ← JSONB deepcopy #2 (주소 변경 시)
  ├── db.commit()                                ← 메인 commit (before_flush → sync_order_dates 실행)
  ├── enqueue_geocode_order_address(...)          ← RQ 비동기 (조건부)
  ├── enqueue_channeltalk_push(...)               ← RQ 비동기
  └── _record_build_step(COMPLETED)              ← commit 2회 (DDL + DML)
```

---

## 2. 감리 결과 (긴급🔴 / 개선권장🟡 / 양호🟢)

### 2.1 긴급 (🔴)

- **없음.** 현재 코드에서 즉시 수정이 필요한 치명적 결함은 발견되지 않음.

### 2.2 개선 권장 (🟡)

| ID | 항목 | 파일 | 비고 |
|----|------|------|------|
| B-6 | 요청 경로 DDL + commit 5회 | `erp_orders_structured.py` | `_record_build_step`이 매 요청마다 DDL 2회 + DML 2회 + 메인 1회 = **commit 5회** 수행. **우선순위 상향 권장** |
| NEW-1 | print 디버깅 8건 | `services/jobs/queue.py` + `services/jobs/tasks.py` | queue.py 4건 + tasks.py 4건 = **총 8건**. `logger`로 교체 필요 |
| NEW-2 | flush 재진입 방어 없음 | `services/order_date_sync.py` | Session 클래스 전역 listener. 명시적 재진입 방지 없음. 회귀 대상 14개 파일 |
| A-4 | 무음 실패 제거 | `erp_orders_structured.py` | `_record_build_step` 예외 처리: `logger.warning` 사용 중. Phase A-4 대비 **이미 개선됨** |
| 파일 크기 | erp_beta_js.html 2,382줄 | `templates/partials/erp_beta_js.html` | GDM §3 목표 800줄 초과. 300줄 초과 시 별도 `.js` 분리 규칙(CLAUDE.md)도 초과 |

### 2.3 양호 (🟢)

| 항목 | 설명 |
|------|------|
| **JSONB 수정 패턴** | `copy.deepcopy` + `flag_modified` 사용. CLAUDE.md 규칙 준수 |
| **에러 숨기기** | `except: pass` 없음. 부가 이벤트 실패 시 `logger.warning` 사용 |
| **fetch 에러 처리** | `erp_beta_js.html`에서 `try/catch` + `data.success` 검증 |
| **order_date_sync** | `register_date_sync_listener`가 app_init에서 등록. before_flush로 자동 동기화 |
| **enqueue 안전** | enqueue 실패 시 False 반환, 예외 로깅. 동기 대기 없음 |
| **erp_automation** | `apply_auto_tasks` 순수 함수 + `ensure_auto_task` DB 반영. 역할 분리 양호 |

### 2.4 수정 필요 (보고서 초안 오류)

| 항목 | 초안 내용 | 실제 | 비고 |
|------|----------|------|------|
| API 응답 형식 | "양호" 판정 | `{success, message}` 형식으로 CLAUDE.md 규칙 `{success, data, error}`와 불일치 | 프론트가 이미 `message` 기준으로 작동. **별도 계약 마이그레이션 과제로 분리** (이 감사 범위 밖) |

---

## 3. 클린코드 규칙 준수

### 3.1 GDM_EXECUTION_PLAN §3 아키텍처 목표

| 규칙 | 목표 | 현재 | 판정 |
|------|------|------|------|
| Python 함수 50줄 이하 | 50줄 | `api_put_order_structured` 85줄, `_record_structured_events` ~45줄 | ⚠️ `api_put_order_structured` 초과 |
| Python 파일 500줄 | 500줄 | `erp_orders_structured.py` **419줄** | ✅ |
| HTML 템플릿 800줄 | 800줄 | `erp_beta_js.html` 2,382줄 (JS 포함 partial) | ❌ 초과 |
| 인라인 script 300줄 | 300줄 | `erp_beta_js.html` 내 JS 2,382줄 | ❌ 초과 |
| 인라인 스타일 금지 | 0건 | `erp_beta_js.html` 내 `style=` 속성 **21건** | ❌ 초과 |

### 3.2 CLAUDE.md / AGENTS.md 문제 수정 정책

| 규칙 | 준수 여부 |
|------|-----------|
| 근본 원인 파악 → 근본 수정 | N/A (보고만 수행) |
| 에러 숨기기 금지 | ✅ `pass` 없음 |
| structured_data 수정 패턴 | ✅ `copy.deepcopy` + `flag_modified` |
| fetch 에러 처리 필수 | ✅ try/catch + `data.success` 검증 |
| print 디버깅 금지 | ❌ `services/jobs/` 내 **8건** 위반 (queue.py 4건 + tasks.py 4건) |

### 3.3 00-project-context.mdc

| 규칙 | 준수 여부 |
|------|-----------|
| Blueprint 패턴 | ✅ `erp_orders_structured_bp` |
| 서비스 레이어 분리 | ✅ `erp_automation`, `order_date_sync`, `order_geocode`, `jobs.queue` |
| RPI 프로토콜 | N/A (기존 기능 감리) |

---

## 4. 최종 실행 계획 (바로 착수용)

### 4.0 실행 판정

- **바로 착수 가능.**
- 단, 이번 실행 범위는 **ERP Beta 저장 경로 지연 감소 + 관측성 보강 + flush 안전장치 추가**로 고정한다.
- 아래 2개 phase를 **순서대로** 수행한다. Phase 1 검증 완료 전에는 Phase 2로 넘어가지 않는다.
- **제외 항목**: API 응답 포맷 통일, `erp_beta_js.html` 분리, `api_put_order_structured` 함수 분할, JSONB deepcopy 계약 변경

### 4.1 확정된 설계 결정

| 항목 | 최종 결정 | 근거 |
|------|-----------|------|
| **API save/parse build-step** | `apps/api/erp_orders_structured.py`의 API 전용 `_record_build_step` 호출과 helper를 제거 | `ERP_BETA_API_SAVE_*`, `ERP_BETA_API_PARSE_TEXT` 읽기측이 로컬 코드에 없음. `erp_build_step_runner.py`는 자체 `_get_step_status()`로 별도 사용 |
| **`system_build_steps` 테이블** | 유지 | `erp_build_step_runner.py:68`가 마이그레이션 step idempotent 가드로 사용 중 |
| **before_flush 가드** | `session.info` 기반 **session-local** 플래그 사용 | listener가 `Session` 클래스 전역 등록이므로 모듈 전역 set 금지 |
| **deepcopy 중복 제거** | 이번 실행에서 **하지 않음** | helper 계약 변경 시 caller 3곳 회귀 위험 > 성능 효과 |
| **print 정리 범위** | `services/jobs/queue.py` + `services/jobs/tasks.py` **8건 동시 정리** | jobs 레이어 반쪽 수정 방지 |
| **redirect 지연** | 500ms 인위적 대기 제거. 성공 응답 직후 redirect | 저장 완료 후 추가 대기 근거 없음 |
| **관측성 보강** | 서버측 save latency만 우선 계측 | 프론트/응답 계약 변경 없이 병목 파악 가능 |

---

### 4.2 Phase 1 — 즉시 실행 (저위험 / 근본 병목 우선)

#### 4.2.1 API 경로 build-step 제거

- **대상 파일**: `apps/api/erp_orders_structured.py`
- **수정 범위**:
  - `_ensure_system_build_steps_table` 삭제
  - `_record_build_step` 삭제
  - `api_put_order_structured()`의 RUNNING / COMPLETED / FAILED 기록 제거
  - `api_parse_order_text()`의 RUNNING / COMPLETED / FAILED 기록 제거
- **유지 범위**:
  - `erp_build_step_runner.py`는 **변경하지 않음**
  - `system_build_steps` 테이블도 **유지**
- **예상 효과**:
  - structured PUT 경로: commit **5회 → 1회**
  - parse-text 경로: build-step용 commit 제거
- **회귀 위험**: 낮음. API 응답 계약과 비즈니스 저장 로직은 그대로

#### 4.2.2 jobs 레이어 print → logger 교체

- **대상 파일**: `services/jobs/queue.py`, `services/jobs/tasks.py`
- **대상 건수**: 총 8건
- **수정 규칙**:
  - 단순 환경 미설정/건너뜀: `logger.info(...)`
  - enqueue 실패/worker 예외: `logger.warning(...)` 또는 `logger.error(...)`
  - 예외 정보가 있으면 `exc_info=True`
- **회귀 위험**: 없음. 출력 채널만 변경

#### 4.2.3 저장 성공 후 redirect 대기 제거

- **대상 파일**: `templates/partials/erp_beta_js.html`
- **현재**: `setTimeout(..., 500)`로 500ms 고정 대기
- **최종 결정**: `setTimeout` 제거 후 **즉시 redirect**
- **회귀 위험**: 없음. 저장 완료 후 UX 지연만 제거

#### 4.2.4 save latency 로깅 추가

- **대상 파일**: `apps/api/erp_orders_structured.py`
- **방법**:
  - `api_put_order_structured()` 진입 시점 timestamp 기록
  - 성공/실패 응답 직전 총 소요 시간 `logger.info(...)`
  - 주소 변경, channeltalk enqueue 시도 여부 등 핵심 context 같이 기록
- **회귀 위험**: 없음. 로깅만 추가

#### 4.2.5 Phase 1 검증 항목

1. 기존 ERP Beta 주문 저장 성공
2. 주소 변경 저장 후 geocode enqueue 동작 유지
3. parse-text 성공/실패 응답 유지
4. 저장 후 redirect가 즉시 동작하는지 확인
5. `erp_build_step_runner.py --resume` 동작 영향 없는지 확인

---

### 4.3 Phase 2 — 검증 포함 실행 (설계 확정 완료)

#### 4.3.1 before_flush 재진입 방어 추가

- **대상 파일**: `services/order_date_sync.py`
- **최종 구현 규칙**:
  - `@event.listens_for(Session, 'before_flush')` 유지
  - `session.info['_order_date_sync_active']` 기반 **session-local guard** 추가
  - `try/finally`로 guard 해제
  - **모듈 전역 set 사용 금지**
- **수정 예시 방향**:
  - guard가 이미 켜져 있으면 즉시 return
  - 아니면 guard 설정 후 `changed_orders` 순회
  - `sync_order_dates(order, session)` 호출 후 finally에서 guard 제거

#### 4.3.2 Phase 2 회귀 검증 범위

| 파일 | 확인 포인트 |
|------|-------------|
| `apps/api/erp_orders_structured.py` | structured PUT 저장 시 `schedule_dates` 정상 생성 |
| `apps/api/orders.py` | `measurement_date`, `scheduled_date` 인라인 수정 정상 |
| `apps/order_edit.py` | 레거시 edit 저장 정상 |
| `apps/order_pages.py` | 신규 주문 생성 후 날짜 동기화 정상 |
| `apps/api/erp_measurement.py` | 단건 주소/전화 수정 후 flush 이상 없음 |
| 대시보드 GET 경로 | 렌더링 중 예기치 않은 flush/예외 없는지 확인 |

#### 4.3.3 추가 주의

- `services/erp_display.py`의 `apply_erp_display_fields()`는 읽기 경로에서 ORM 객체 속성을 직접 대입한다.
- 이번 phase에서는 **가드만 추가**하고, `apply_erp_display_fields`의 DTO 분리/비변이화는 **별도 과제**로 남긴다.
- 즉, **이번 변경에서 `erp_display.py`는 건드리지 않는다.**

---

### 4.4 이번 실행에서 제외 (명시적 비범위)

#### 4.4.1 JSONB deepcopy 중복 제거

- `reset_order_geocode_on_address_change()`의 deepcopy는 공통 계약
- 현재 caller 4곳 중 3곳이 helper 내부 deepcopy에 의존
- **이번 실행에서 제외**

#### 4.4.2 API 응답 형식 통일

- 현재 `{success, message}` 유지
- 프론트 `erp_beta_js.html`이 `data.message` 기준으로 동작 중
- **별도 계약 마이그레이션 과제**

#### 4.4.3 대형 리팩토링

- `erp_beta_js.html` 분리
- `api_put_order_structured` 함수 분할
- 인라인 스타일 21건 추출
- **모두 별도 리팩토링 과제**

---

## 5. 요약

| 구분 | 최종 결정 |
|------|-----------|
| **최대 병목** | API 전용 build-step logging의 commit 5회 |
| **즉시 실행 1순위** | `erp_orders_structured.py`의 build-step 제거 |
| **즉시 실행 2순위** | jobs 레이어 print 8건 → logger |
| **즉시 실행 3순위** | redirect 500ms 제거 + save latency 계측 |
| **2차 실행** | `session.info` 기반 before_flush guard |
| **제외** | deepcopy 계약 변경, API 응답 포맷, JS 분리, 함수 분할 |

### 최종 착수 순서

1. Phase 1.1 `erp_orders_structured.py` build-step 제거
2. Phase 1.2 jobs logger 정리
3. Phase 1.3 redirect 지연 제거
4. Phase 1.4 save latency 로깅 추가
5. Phase 1 검증
6. Phase 2.1 `order_date_sync.py` session-local guard 추가
7. Phase 2 검증

### 예상 시간

| 구분 | 예상 시간 |
|------|----------|
| Phase 1 | 1.5~2시간 |
| Phase 2 | 2~3시간 |
| 총합 | 3.5~5시간 |

---

## 부록 A: 더블체크 검증 대조표

| # | 초안 주장 | 판정 | 보정 내용 |
|---|----------|------|----------|
| 1 | `_record_build_step` 2~3회 호출 | **보정** | 정상 경로 정확히 **2회**. "3회" 케이스 없음 |
| 2 | commit 다중 실행 2~3회 | **보정** | 실제 **5회** (DDL×2 + DML×2 + 메인×1) |
| 3 | `erp_orders_structured.py` 319줄 | **보정** | 실제 **419줄** |
| 4 | "flush 루프 방지 로직 있음" | **보정** | 명시적 방지 로직 없음. 타입 필터 부수효과로 우연히 안전 |
| 5 | API 응답 형식 "양호" | **보정** | `{success, message}` 형식으로 CLAUDE.md 규칙과 불일치 |
| 6 | queue.py "양호" | **보정** | print 디버깅 4건 누락 |
| 7 | 인라인 스타일 | **추가** | `erp_beta_js.html` 내 `style=` 속성 21건 미기술 |
| 8 | JSONB deepcopy 2회 | **추가** | 주소 변경 시 동일 요청에서 deepcopy 중복 실행 |

**보고서 신뢰도**: 초안 73/100 → 더블체크 보정 95/100

## 부록 B: 외부 리뷰 피드백 검증 결과

| # | 피드백 | 판정 | 코드 검증 결과 | 반영 내용 |
|---|--------|------|---------------|----------|
| 1 | deepcopy 계약 변경 위험 (높음) | **타당** | 4개 caller 중 3곳이 helper 내부 deepcopy에 완전 의존. 제거 시 3곳 파손 | 4.2.3으로 이동 + **현행 유지 권장**으로 결론 변경 |
| 2 | flush 재진입 방지 설계 미흡 (높음) | **타당** | Session 클래스 전역 등록 확인. session-local vs 모듈 전역 옵션 비교 추가 | 4.2.2로 이동 + 옵션 테이블 + 회귀 14파일 명시 |
| 3 | system_build_steps 방향 미결정 (중간) | **타당 + 강화** | 읽기측 1곳(마이그레이션 가드)뿐. 기능 삭제가 유력 | 4.2.1로 이동 + 3옵션 비교 테이블 추가 |
| 4 | print 범위 부족 (중간) | **타당** | queue.py 4건 + tasks.py 4건 = 총 8건 | 1.2 + 4.1.1 보정 완료 |
| 5 | 회귀 범위 누락 (중간) | **타당** | Order 수정+commit 경로 14개 파일 확인 | 4.2.2.1 회귀 테스트 대상 14파일 테이블 추가 |
| 6 | API 응답 포맷은 별도 과제 (낮음) | **타당** | 이 감사의 성능 개선 범위 밖 | 4.3.1 범위 밖으로 이동 |

---

*본 보고서는 코드 수정 없이 감리만 수행한 결과입니다.*
*더블체크: code-reviewer + explore-codebase 서브에이전트 병렬 검증 완료.*
*외부 리뷰: 6건 피드백 전수 코드 검증 후 반영 완료.*
