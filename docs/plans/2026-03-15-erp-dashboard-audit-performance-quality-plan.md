# ERP 대시보드 성능 · 품질 종합 개선 계획서 (소스 1:1 재검증판)

- **작성일**: 2026-03-15
- **업데이트일**: 2026-03-15
- **기준 소스**: 현재 작업 트리 기준 직접 대조
- **대상 범위**: ERP 대시보드 전체 (실측/도면/시공/출고/AS/Beta)
- **문서 상태**: 소스 대조 기반 정정 + 즉시 착수 가능 범위/전제 조건 반영 완료

---

## 개요

기존 계획서는 중요한 실제 버그를 잘 잡은 항목도 있었지만, 다음 문제가 함께 섞여 있었다.

- 실제 코드와 맞지 않는 파일/라인/함수명이 포함되어 있었다.
- 현재 동작 의미를 바꾸는 해결 방향이 일부 포함되어 있었다.
- soft-delete 기준과 인덱스 전략이 서로 충돌했다.
- JSONB 검색 최적화 방향이 실제 검색 방식과 맞지 않았다.

이번 문서는 위 문제를 제거하고, **현재 소스와 1:1 대조된 실행 계획**으로 다시 정리한 검증판이다.

## 실행 준비도 요약

**지금 바로 착수 가능**:
- Phase A 중 `A-1`, `A-2`, `A-4`
- Phase B 중 `B-2`, `B-3`, `B-4`

**이미 반영 완료**:
- `A-3` — `apps/api/erp_orders_completion.py`에서 새 세션 롤백 문제가 2026-03-15 기준 수정됨

**착수 전 전제 고정 필요**:
- `B-1` — `mine` 의미를 바꾸지 않는 SQL 하향 범위 확정 필요
- `B-5`, `D-4` — 신규 `common.js`를 만들지 말고, 기존 `static/js/erp/common_utils.js` 기준으로 import/로딩 순서를 먼저 정리
- Phase C 전체 — Alembic 기본 트랜잭션 환경에서 `CREATE INDEX CONCURRENTLY`를 어떻게 적용할지 먼저 정리

우선순위 기준:
1. **Phase A** — 데이터 무결성/트랜잭션 버그
2. **Phase B** — 성능 저하 원인 제거
3. **Phase C** — 인덱스/쿼리 기준 정렬
4. **Phase D** — 품질 개선 및 리팩토링
5. **Phase V** — 회귀 검증 게이트

---

## 이번 업그레이드에서 바로잡은 핵심

- `apps/api/erp_measurement.py` 항목은 `api_erp_measurement_route` 문제가 아니라 `api_erp_measurement_update` 확인 대상이었고, 현재는 `flag_modified()`가 이미 들어가 있으므로 Phase A 대상에서 제외했다.
- 실측 API의 `mine` 필터는 `construction_workers` 배정 여부와 `manager_name`, `structured_data.parties.manager.name`, `workflow.current_quest.owner_person` 조건을 함께 사용하므로, 단순 JSONB `@>` 최적화 계획을 폐기했다.
- `cast(Order.structured_data, String).ilike(...)` 문제는 JSONB GIN 인덱스만으로 해결되지 않으므로, 검색식 재설계와 별도 인덱스 전략으로 분리했다.
- soft-delete 기준은 `status != 'DELETED'`와 `deleted_at IS NULL`가 혼재하므로, 인덱스 추가 전에 기준 통일부터 하도록 순서를 바꿨다.
- `db.query(Order).get()`의 대체는 `filter().first()`가 아니라 `Session.get()` 기반으로 정정했다.
- API 응답 형식 통일은 즉시 `error` 제거가 아니라, 소비 코드 확인 전까지 `message` 추가 + `error` 호환 유지로 정정했다.
- `A-3`는 계획 항목으로 남기되, 현재 코드에는 이미 수정이 반영돼 있으므로 재작업이 아니라 회귀 확인 대상으로 전환했다.

---

## Phase A — 데이터 무결성/트랜잭션 버그 즉시 수정

> 목표: 저장 누락, 잘못된 세션 롤백, 무음 실패를 제거한다.

### A-1. JSONB 변경 감지 누락

**심각도**: CRITICAL

| 파일 | 현재 문제 |
|---|---|
| `apps/api/erp_orders_drawing.py` | `api_order_transfer_drawing`에서 `order.structured_data = s_data` 후 `flag_modified()` 없음 |
| `apps/api/erp_orders_drawing.py` | `api_order_cancel_transfer`에서 deep copy/`flag_modified()` 없음 |
| `apps/api/erp_orders_revision.py` | `api_order_request_revision`에서 `flag_modified()` 없음 |

**정정 메모**:
- `apps/api/erp_measurement.py`의 실측 업데이트는 현재 `flag_modified(order, 'structured_data')`가 이미 존재하므로 이 항목에 포함하지 않는다.

**수정 원칙**:
```python
import copy
from sqlalchemy.orm.attributes import flag_modified

sd = copy.deepcopy(order.structured_data or {})
# ... sd 수정 ...
order.structured_data = sd
flag_modified(order, "structured_data")
db.commit()
```

**검증 포인트**:
- 도면 전달 후 `drawing_transfer_history`가 실제 DB에 남는지 확인
- 전달 취소 후 `drawing_current_files`, `drawing_status`가 복원되는지 확인
- 수정 요청 후 `drawing_transfer_history`가 실제 DB에 남는지 확인

---

### A-2. 팀 권한 검사 키 오류

**심각도**: HIGH

| 파일 | 현재 문제 |
|---|---|
| `services/erp_policy.py` | `workflow.get('current_stage')` 조회, 실제 저장 키는 `stage` |

**수정 방향**:
```python
current_stage = workflow.get("stage")
```

**영향 범위**:
- ADMIN/MANAGER 예외 처리로 겉으로 덜 드러났을 수 있으나
- STAFF 레벨의 도메인 수정 권한 판단은 현재 잘못 동작할 가능성이 높다
- `can_modify_domain()` 일반 도메인 fallback에서 실제로 도달 가능하므로, 단순 저빈도 경로로 낮게 볼 수 없다

**검증 포인트**:
- STAFF 사용자 기준으로 단계별 수정 허용/차단이 정책과 일치하는지 확인

---

### A-3. 잘못된 세션 롤백

**상태**: 완료

**심각도(발견 시점)**: HIGH

| 파일 | 기존 문제 |
|---|---|
| `apps/api/erp_orders_completion.py` | `except`에서 `get_db()`를 다시 호출해 새 세션을 롤백함 |

**반영 내용**:
```python
db = None
try:
    db = get_db()
    ...
except Exception as e:
    if db is not None:
        db.rollback()
    raise
```

**검증 포인트**:
- 실패 유도 시 부분 반영 없이 트랜잭션이 되돌려지는지 확인

**실행 메모**:
- 이 항목은 재구현 대상이 아니라 회귀 확인 대상이다.
- Phase A 착수 시 중복 수정하지 않는다.

---

### A-4. 무음 실패 제거

**심각도**: HIGH

| 파일 | 현재 문제 |
|---|---|
| `apps/api/erp_orders_structured.py` | 이벤트 기록/후처리 경로에서 `except Exception: pass` 다수 존재 |
| `apps/api/erp_orders_blueprint.py` | rollback 실패를 `except: pass`로 은폐 |

**수정 방향**:
- `pass` 제거
- 최소 `warning` 로그 남김
- rollback 실패도 별도 로그 남김

**주의**:
- 여기서는 예외를 모두 다시 터뜨리라는 뜻이 아니다.
- 핵심 저장 흐름과 부가 이벤트 흐름을 구분해서, 부가 이벤트 실패는 로깅 후 계속 진행하되 저장 결과를 왜곡하지 않게 처리한다.

**검증 포인트**:
- 부가 이벤트 실패 시 서버 로그에서 원인 추적 가능해야 함
- 정상 저장이 이벤트 실패 때문에 불필요하게 깨지지 않아야 함

---

## Phase B — 성능 저하 개선

> 목표: 과다 로드, 반복 쿼리, 중복 DOM 작업, 요청 직렬화를 줄인다.

### B-1. 실측 Summary API 과다 로드 + Python 후처리

**심각도**: HIGH

| 파일 | 현재 문제 |
|---|---|
| `apps/api/erp_measurement.py` | `.limit(1500).all()` 후 Python 레벨에서 `mine` 필터 적용 |

**현재 핵심 원인**:
- 먼저 1500건을 읽는다.
- 이후 `is_order_mine_for_user()`를 Python에서 실행한다.
- 이 함수의 의미는 `construction_workers` 배정 여부 또는 `manager_name`, `structured_data.parties.manager.name`, `workflow.current_quest.owner_person` 일치 여부다.

**잘못된 기존 방향**:
- `construction_workers` JSONB 배열만 인덱스로 최적화하는 접근은 현재 실측 `mine` 의미 전체와 맞지 않는다.

**수정 방향**:
1. 날짜 범위와 ERP/상태 조건을 더 앞단에서 줄인다.
2. `mine` 의미를 유지한 채 DB에서 먼저 걸 수 있는 조건은 최대한 SQL로 내린다.
3. SQL로 완전히 내리기 어렵다면, 최소한 후보 건수를 충분히 줄인 뒤 Python 후처리를 수행한다.
4. `is_order_mine_for_user()`를 호출하는 모든 화면에서 의미 불일치가 없는지 먼저 정리한다.

**착수 전 전제**:
- `construction_workers` 조건과 manager/owner 조건 중 무엇을 SQL로 내리고 무엇을 Python 후처리로 남길지 먼저 확정한다.
- 결과 동등성 비교 없이 쿼리 최적화부터 들어가면 의미 변경 위험이 크다.

**검증 포인트**:
- `mine=1` 결과가 수정 전과 동일해야 한다.
- 단순히 빨라졌지만 다른 주문이 보이거나 사라지면 실패다.

---

### B-2. ERP 대시보드 루프 내 User N+1

**심각도**: HIGH

| 파일 | 현재 문제 |
|---|---|
| `apps/erp_dashboard.py` | 주문 루프 안에서 `User.id.in_(user_ids)` 조회 반복 |

**수정 방향**:
1. 루프 전에 모든 assignee `user_id`를 수집
2. 단일 `IN` 조회로 `user_map` 생성
3. 루프에서는 map 참조만 사용

**검증 포인트**:
- 주문 수가 늘어나도 User 조회 쿼리 수가 상수 수준으로 유지되어야 함

---

### B-3. 시공 화면 첨부 삭제 순차 요청

**심각도**: HIGH

| 파일 | 현재 문제 |
|---|---|
| `templates/partials/erp_construction_scripts.html` | 기존 첨부 삭제를 `for ... await fetch(DELETE)`로 직렬 실행 |

**정정 메모**:
- 기존 문서에 적힌 `templates/partials/erp_beta_js.html`의 동일 bulk-delete 패턴은 현재 확인되지 않았다.
- Beta 쪽은 별도 마이크로 감사 후 필요 시 추가한다.

**수정 방향**:
```javascript
await Promise.all(
  attachments.map((att) =>
    fetch(`/api/orders/${orderId}/attachments/${att.id}`, { method: "DELETE" })
  )
);
```

**검증 포인트**:
- 재업로드 시 기존 삭제가 빨라져야 함
- 일부 삭제 실패 시 사용자에게 실패가 보여야 함

---

### B-4. 출고 대시보드 정렬/색상 적용 중복

**심각도**: MEDIUM

| 파일 | 현재 문제 |
|---|---|
| `templates/erp_shipment_dashboard.html` | 초기 로드 경로에서 `applyShipmentWorkerSortAndColors()`가 중복 호출되고, 저장 후 blur 경로에서도 재호출됨 |

**실제 호출 위치 (소스 대조 확인)**:
- 1230행: `applyShipmentWorkerSortAndColors()` — fetch `.then` 안
- 1235행: `applyShipmentWorkerSortAndColors()` — fetch `.catch` 안
- 1238행: `addEventListener('DOMContentLoaded', ...)` 안에서 `setTimeout(...)`
- 1240행: `setTimeout(applyShipmentWorkerSortAndColors, 50)` — `else` 분기
- 1246행: blur 이벤트에서 `scheduleApplyShipmentWorkerSortAndColors()` 경유 재호출
- 1615행: `construction_workers` 저장 성공 후 `scheduleApplyShipmentWorkerSortAndColors()` 재호출

**정정 메모**:
- 초기 문서의 "2회 호출"은 과소평가였다.
- 다만 helper 정의 자체를 호출로 계산하면 과장되므로, 초기 로드 기준으로는 **4개 경로**, 편집 흐름까지 포함하면 **blur 경로 + 저장 성공 경로**가 추가되는 것으로 보는 것이 정확하다.

**수정 방향**:
- fetch 성공 콜백 내 1회만 호출로 통일
- `DOMContentLoaded`, `setTimeout`, `.catch` 경유 중복 호출 제거
- `scheduleApplyShipmentWorkerSortAndColors` 경유 blur 호출은 의미 검토 후 필요 시 유지

**검증 포인트**:
- 정렬/색상 표시 결과는 유지
- 초기 렌더링 중 재배치 횟수만 줄어야 함

---

### B-5. 대형 인라인 스크립트/템플릿 분리

**심각도**: MEDIUM

**확인 대상**:
- `templates/partials/erp_beta_js.html`
- `templates/partials/erp_construction_scripts.html`
- `templates/partials/erp_production_scripts.html`
- `templates/erp_drawing_workbench_detail.html`
- `templates/erp_shipment_dashboard.html`
- `templates/erp_as_dashboard.html`

**수정 방향**:
- 순수 JS는 `static/js/...`로 이동
- 템플릿 데이터는 `data-*` 또는 JSON script block으로 전달
- 공통 유틸은 가능하면 기존 `static/js/erp/common_utils.js`로 흡수하고, 신규 파일 생성은 정말 필요할 때만 검토한다

**주의**:
- 이 항목은 성능뿐 아니라 유지보수성 개선이 목적이다.
- Phase A/B의 버그 수정과 한 커밋에 섞지 않는다.
- `common.js` 신규 도입을 기본값으로 두지 않는다. 이미 존재하는 공용 유틸 파일과 충돌하지 않게 경로를 먼저 정리한다.

---

### B-6. 요청 경로에서 DDL + 별도 commit 실행

**심각도**: MEDIUM

| 파일 | 현재 문제 |
|---|---|
| `apps/api/erp_orders_structured.py` | `_record_build_step()`이 `_ensure_system_build_steps_table()` 호출과 별도 commit을 수행 |

**정정 메모**:
- 이 문제는 `api_put_order_structured`뿐 아니라 parse-text 경로도 포함한다.

**수정 방향**:
1. `system_build_steps`를 마이그레이션으로 생성하거나
2. 기능 자체가 운영 필수가 아니면 제거
3. 최소한 저장 트랜잭션과 build-step 로깅 트랜잭션을 분리해 핵심 저장을 오염시키지 않게 함

**검증 포인트**:
- structured save 실패/성공 여부가 build-step 로깅 실패와 독립적이어야 함

---

### B-7. JSONB 전체 텍스트 `ilike`로 인한 풀스캔

**심각도**: HIGH

| 파일 | 현재 문제 |
|---|---|
| `apps/erp_measurement_dashboard.py` | `cast(Order.structured_data, String).ilike(term)` |
| `apps/erp_shipment_page.py` | 동일 패턴 |
| `apps/erp_as_page.py` | 동일 패턴 |

**기존 문서의 문제점**:
- JSONB GIN 인덱스를 추가해도 `cast(...).ilike()`는 그대로는 해결되지 않는다.
- `customer.name` 하나만 대상으로 바꾸면 현재 검색 의미가 축소된다.

**수정 방향**:
1. 현재 검색이 실제로 커버해야 하는 필드를 먼저 명시한다.
   - 고객명
   - 담당자명
   - 주소
   - 발주사
   - 시공자 등
2. 고빈도 필드는 명시적 컬럼/표현식으로 검색한다.
3. 부분 문자열 검색이 필요하면 `pg_trgm` 기반 표현식 인덱스 또는 별도 정규화 검색 컬럼을 검토한다.
4. JSONB GIN 인덱스는 `@>`, `?`, 경로 존재 검사 같은 containment 계열 쿼리에만 적용한다.

**검증 포인트**:
- 검색 결과 의미가 줄어들면 안 된다.
- 페이지별 검색 결과가 기존 사용자 기대와 동일해야 한다.

---

## Phase C — 쿼리 기준/인덱스 정렬

> 목표: 먼저 기준을 통일하고, 그 다음 인덱스를 추가한다.

**실행 전제**:
- 현재 `migrations/env.py`는 기본 트랜잭션 방식(`context.begin_transaction()`)을 사용한다.
- PostgreSQL의 `CREATE INDEX CONCURRENTLY`는 일반 트랜잭션 revision 본문에 그대로 넣으면 실패하거나 운영 절차가 꼬일 수 있다.
- 따라서 Phase C 착수 전, Alembic autocommit 블록 또는 별도 비트랜잭션 운영 절차를 먼저 정한다.

### C-0. soft-delete 기준 먼저 통일

**현재 문제**:
- 일부 코드는 `status != 'DELETED'`
- 일부 코드는 `deleted_at.is_(None)`
- 일부 코드는 두 기준이 섞여 있다

**권장 기준**:
```python
Order.status != "DELETED"
Order.deleted_at.is_(None)
```

**정책**:
- 마이그레이션/정리 완료 전까지는 active 주문 필터를 위 두 조건의 결합으로 통일한다.
- 이후 helper 함수 또는 공통 query builder로 추출한다.

**이유**:
- soft-delete 시 현재 시스템은 `status='DELETED'`와 `deleted_at`을 함께 기록한다.
- 한쪽만 믿으면 과거 데이터/복원 경로에서 불일치 위험이 남는다.

---

### C-1. active 주문용 partial index

**수정 방향**:
```sql
CREATE INDEX CONCURRENTLY ix_orders_active_id
ON orders (id DESC)
WHERE status <> 'DELETED' AND deleted_at IS NULL;
```

**메모**:
- 기존 문서의 `deleted_at IS NULL` 단독 인덱스보다 현재 시스템 의미와 맞다.
- 다만 `CONCURRENTLY` 사용 시 Alembic revision 구현 방식을 먼저 확정해야 한다.

---

### C-2. JSONB containment 전용 GIN 인덱스

**수정 방향**:
```sql
CREATE INDEX CONCURRENTLY ix_orders_structured_data_gin
ON orders USING gin (structured_data);
```

**적용 대상**:
- `@>`
- `?`
- 경로 존재 검사
- 배열 포함 검사

**비적용 대상**:
- `cast(structured_data as text) ilike '%...%'`

---

### C-3. substring 검색 전용 인덱스 전략

**수정 방향**:
- `pg_trgm` 기반 표현식 인덱스 또는
- 별도 `erp_search_text` 정규화 컬럼 도입 검토

예시:
```sql
CREATE INDEX CONCURRENTLY ix_orders_customer_name_trgm
ON orders
USING gin ((structured_data->'parties'->'customer'->>'name') gin_trgm_ops);
```

**주의**:
- 어떤 표현식 인덱스를 만들지 결정하기 전에 검색 필드 범위를 먼저 고정해야 한다.

---

## Phase D — 코드 품질 및 리팩토링

> 목표: deprecated API, 중복 코드, 응답 계약, 과도한 함수 책임을 정리한다.

### D-1. `query().get()` 제거

**대상 파일**:
- `apps/api/erp_orders_as.py`
- `apps/api/erp_orders_confirm.py`
- `apps/api/erp_orders_construction.py`
- `apps/api/erp_orders_cs.py`
- `apps/api/erp_orders_production.py`
- `apps/api/erp_orders_revision.py`

**정정 방향**:
```python
order = db.get(Order, order_id)
if not order or order.status == "DELETED" or order.deleted_at is not None:
    ...
```

**정정 메모**:
- 기존 문서의 `filter().first()` 대체안은 deprecated 제거의 정답이 아니다.

---

### D-2. `api_put_order_structured` 책임 분리

**현재 문제**:
- 단계 전환
- 이벤트 생성
- auto-task
- draft 처리
- 주소 후처리
- channeltalk enqueue
- build-step 로깅

위 역할이 한 함수에 밀집돼 있다.

**분리 방향**:
- `_handle_stage_transition(...)`
- `_record_structured_events(...)`
- `_apply_structured_side_effects(...)`
- `_finalize_draft_state(...)`
- build-step 로깅은 별도 경계로 분리

---

### D-3. API 응답 형식 점진 통일

**현재 문제**:
- 일부 API는 `error`
- 일부 API는 `message`
- 소비 코드는 `message || error` 혼용

**수정 방향**:
1. 우선 모든 실패 응답에 `message`를 넣는다.
2. 프런트 소비 코드가 모두 이전되기 전까지는 `error`도 병행 유지한다.
3. 소비 코드 정리 완료 후 `error` 제거를 검토한다.

**즉시 제거 금지 이유**:
- 현재 `static/js/erp/measurement.js` 등은 `data.message || data.error`를 이미 사용한다.

---

### D-4. 중복 유틸 통합

**중복 확인 대상**:

| 함수 | 확인 위치 |
|---|---|
| `_ensure_path` | `apps/api/erp_orders_as.py`, `apps/api/erp_orders_completion.py` |
| `escapeHtml` | 명시적 선언 기준 **19곳** 중복 (아래 상세 참조) |
| `safeJsonFetch` | `templates/partials/erp_dashboard_scripts_detail_dom.html`, `templates/partials/erp_construction_scripts.html`, `templates/partials/erp_production_scripts.html` |

**escapeHtml 상세 (소스 대조 확인)**:
- `erp_construction_scripts.html:6` / `erp_production_scripts.html:2` — 파일간 중복
- `erp_production_scripts.html` 내 **같은 파일 2중 선언** (2번째 줄, 1350번째 줄)
- `layout.html` 내 **같은 파일 2중 선언** (764번째 줄, 2188번째 줄)
- 그 외 다수 파일에 동일/유사 구현 산재
- **정정 메모**: 명시적 `function escapeHtml` 선언 검색 기준으로는 현재 **19개**가 확인된다. 유사 구현까지 포함하면 추가 검토 여지가 있다.

**수정 방향**:
- Python 유틸은 `services/erp_utils.py`
- JS 유틸은 우선 기존 `static/js/erp/common_utils.js`를 통합 지점으로 사용
- `escapeHtml`, `safeJsonFetch`는 `static/js/erp/common_utils.js` 1곳으로 통합 후 각 템플릿에서 import
- 같은 파일 내 이중 선언 먼저 제거

**주의**:
- 이미 `static/js/erp/common_utils.js`가 존재하므로, 동일 목적의 `common.js`를 새로 추가하면 공용 유틸 경로가 다시 분산된다.
- 파일명 변경이 필요하면 별도 정리 커밋에서 import 경로 일괄 이전까지 포함해 처리한다.

---

### D-5. 매직 문자열 상수화

**기존 문서 정정**:
- `MANAGER_TEAM_KEYWORDS = {'라홈': 'CS', '하우드': 'HAUDD'}` 는 현재 코드 기준으로 부정확하므로 폐기한다.

**수정 방향 예시**:
```python
ERP_DRAFT_PLACEHOLDER_CUSTOMER = "ERP Beta"
ERP_DRAFT_PLACEHOLDER_PHONE = "000-0000-0000"
ORDERER_NAME_LAHOM = "라홈"
ORDERER_NAME_HAUDD = "하우드"
TEAM_CS = "CS"
```

**원칙**:
- 실제 운영 로직에서 쓰는 상수만 올린다.
- 존재하지 않는 팀 코드나 추정 매핑은 넣지 않는다.

---

### D-6. `import traceback` 함수 내부 인라인 선언 (신규 발견)

**심각도**: LOW — 코드 품질 / 스타일

**현재 문제**:
- `import traceback`이 모듈 최상단이 아닌 `except` 블록 내부에서 반복 선언됨
- Python은 모듈을 캐시하므로 기능 오류는 없으나, 표준 스타일 위반

**실제 발생 규모 (소스 대조 확인)**:

| 파일 | 발생 수 |
|---|---|
| `apps/api/chat/routes.py` | 19곳 (전체 최다) |
| `apps/api/attachments.py` | 7곳 |
| `apps/api/notifications.py` | 3곳 |
| `apps/api/events.py` | 4곳 |
| `apps/api/erp_orders_structured.py` | 5곳 |
| `apps/api/quest.py` | 4곳 |
| `apps/api/erp_orders_revision.py` | 2곳 |
| `apps/api/erp_orders_completion.py` | 2곳 |
| `apps/api/erp_map.py` | 2곳 |
| 기타 다수 | — |

위 표 기준만 합산해도 **48곳**이며, 전체적으로는 그 이상일 수 있다.

**수정 방향**:
- 각 파일 최상단으로 `import traceback` 이동
- 운영 환경에서는 `print(traceback.format_exc())` 대신 `logger.exception(...)` 사용 권장
- Phase D 리팩토링 시 파일 단위로 일괄 정리

---

### D-7. `storage._get_file_type` private 메서드 직접 호출 (신규 발견)

**심각도**: LOW — 구조적 결합 문제

| 파일 | 라인 | 문제 |
|---|---|---|
| `apps/api/erp_orders_drawing.py` | 433, 476 | `storage._get_file_type(filename)` private 메서드 직접 호출 |
| `apps/api/attachments.py` | 322, 477 | 동일 |
| `apps/api/chat/routes.py` | 109, 236 | 동일 |

**실제 코드 패턴**:
```python
# apps/api/erp_orders_drawing.py
file_type = storage._get_file_type(filename) if hasattr(storage, '_get_file_type') else 'file'

# apps/api/attachments.py / apps/api/chat/routes.py
file_type = storage._get_file_type(filename)
```

**문제점**:
- `_` 접두어 메서드는 Python 관례상 private — 외부 직접 호출 금지
- 일부 호출부는 `hasattr` 가드가 존재하고, 일부는 private 메서드를 직접 신뢰해 호출한다
- storage 클래스 내부 구현 변경 시 호환성 깨짐

**수정 방향**:
- `storage` 클래스에 public `get_file_type(filename: str) -> str` 메서드 추가
- 호출부를 `storage.get_file_type(filename)` 으로 교체
- private 메서드 직접 참조와 `hasattr` 방어 코드를 함께 제거

---

### D-8. 인라인 스타일 → CSS 클래스

**대상**:
- `templates/partials/erp_dashboard_scripts_core.html`

**현재 문제**:
- 리사이저 스타일이 JS에서 직접 세팅됨
- 토스트 컨테이너도 JS 생성 흐름과 스타일 책임이 섞여 있음

**수정 방향**:
- `.erp-col-resizer`
- `.erp-toast-container`

로 CSS 책임을 이동한다.

---

## Phase V — 회귀 검증 게이트

> 목표: "수정 후 기존 FOMS 모든 기능이 이전처럼 정상 작동하는가"를 코드 변경 전제로 확인한다.

### V-1. 자동 검증

**필수**:
- `pytest -q`

**현재 한계**:
- 현 테스트는 in-memory SQLite 중심이라 ERP 운영 회귀를 충분히 보장하지 못한다.

### V-2. 쓰기 없는 스모크 검증

다음 화면은 최소 GET/렌더링 확인이 필요하다.

- `/erp/dashboard`
- `/erp/measurement`
- `/erp/shipment`
- `/erp/as`
- `/erp/drawing-workbench`

### V-3. 수동 핵심 시나리오

Phase A 적용 후 반드시 확인:

1. 도면 전달
2. 도면 전달 취소
3. 도면 수정 요청
4. 완료처리 실패 시 rollback
5. structured save 후 이벤트/자동화 부가 로직
6. 시공 첨부 재업로드
7. 실측 `mine=1` 필터 결과 비교
8. ERP/실측/출고/AS 검색 결과 비교

### V-4. 주의 사항

- `tools/smoke/tools_test_structured_events.py`
- `tools/smoke/tools_test_policy_templates.py`
- `tools/smoke/tools_test_erp_attachments.py`

위 스크립트는 실제 주문 데이터에 쓰기를 발생시킬 수 있으므로, 공유 DB에서는 바로 실행하지 않는다.

---

## 실행 순서

1. **Phase A**
   - `A-1`, `A-2`, `A-4` 먼저 수행
   - `A-3`는 이미 반영돼 있으므로 회귀 확인만 수행
   - 바로 수동 검증
2. **Phase B**
   - 즉시 가능: `B-2` → `B-3` → `B-4`
   - 전제 필요: `B-1`
   - 구조 분리는 `B-5`를 별도 커밋으로 분리
3. **전제 고정**
   - `B-1`의 `mine` 의미 보존 범위 확정
   - `B-5`/`D-4`의 import/로딩 순서를 `common_utils.js` 기준으로 정리
   - Phase C용 Alembic `CONCURRENTLY` 적용 방식을 확정
4. **Phase C**
   - soft-delete 기준 통일 후 인덱스 추가
5. **Phase D**
   - deprecated 제거, 유틸 통합, 함수 분리
6. **Phase V**
   - 자동/수동 회귀 검증

---

## 결론

이 문서는 기존 계획서를 단순 보완한 것이 아니라, **실제 소스 기준으로 오기와 잘못된 해결 방향을 제거하고, 즉시 착수 가능 범위와 실행 전제를 명시한 업그레이드판**이다.

핵심 원칙은 다음 세 가지다.

- 현재 동작 의미를 바꾸지 않는 수정만 먼저 한다.
- 이미 반영된 수정은 중복 작업하지 않고 회귀 검증 대상으로 관리한다.
- 인덱스와 리팩토링은 쿼리 기준, 공용 유틸 경로, 마이그레이션 전략을 먼저 정리한 뒤 진행한다.

**다음 실행 단계는 `A-1`부터 시작하고, `A-3`는 체크리스트상 완료 항목으로 유지한다.**
