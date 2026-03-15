# Phase C 코드 리뷰 보고서 (2026-03-15)

**검토자**: code-reviewer (FOMS Code Quality Agent)  
**대상**: Phase C (쿼리 기준/인덱스 정렬) 실행 결과  
**검토 기준**: code-reviewer 체크리스트, GDM 감리 형식

---

## 1. 검토 대상 변경 요약

| 영역 | 변경 내용 |
|------|-----------|
| models.py | `Order.active_filter()` 추가, `__table_args__` Index에 `deleted_at.is_(None)` 포함 |
| apps/* | `Order.status != 'DELETED'` / `Order.deleted_at.is_(None)` → `Order.active_filter()` 통일 |
| services/db_indexes.py | partial index WHERE에 `deleted_at IS NULL` 추가 |
| migrations | `phase_c_indexes_concurrently.py` C-1, C-2 인덱스 (CONCURRENTLY) |

---

## 2. Findings

### [Severity: medium] CONCURRENTLY 마이그레이션 트랜잭션 전략 검증 필요

- **파일**: `migrations/versions/phase_c_indexes_concurrently.py:22-26`
- **근거**: `_run_concurrently()`가 `conn.execute(text("COMMIT"))` 후 DDL을 실행한다. Alembic `env.py`는 `context.begin_transaction()`으로 전체 upgrade를 트랜잭션으로 감싼다. 수동 COMMIT 후 context manager 종료 시 이중 commit/rollback 시도로 예외가 발생할 수 있다.
- **영향**: 마이그레이션 실행 중 `Transaction is already committed` 등 예외로 실패할 수 있음.
- **권장 수정**: `migrations/env.py`에 `context.configure(..., transaction_per_migration=False)` 적용 여부 검토. 또는 CONCURRENTLY 전용 마이그레이션을 `alembic upgrade` 외부에서 `psql -c "CREATE INDEX CONCURRENTLY ..."` 등으로 수동 실행하는 방식 검토.

### [Severity: low] personal_board._recent_work()에 active_filter 미적용

- **파일**: `apps/api/personal_board.py:196-199`
- **근거**: `_recent_work()`가 `OrderEvent`에서 order_id를 가져온 뒤 `Order.id.in_(order_ids)`로만 조회한다. `Order.active_filter()`가 없어 삭제된 주문도 최근 작업 목록에 노출될 수 있다.
- **영향**: 휴지통에 있는 주문이 브리핑 보드 최근 작업에 표시될 수 있음. UX 정책에 따라 의도적일 수 있음.
- **권장 수정**: active 주문만 노출하려면 `.filter(Order.id.in_(order_ids), Order.active_filter())` 추가. 삭제된 주문도 노출하는 것이 의도라면 주석으로 명시.

### [Severity: low] C-2 GIN 인덱스에 partial 조건 없음

- **파일**: `migrations/versions/phase_c_indexes_concurrently.py:37-40`
- **근거**: `ix_orders_structured_data_gin`은 `ON orders USING gin (structured_data)`로 생성되며, `WHERE status <> 'DELETED' AND deleted_at IS NULL` 조건이 없다.
- **영향**: 삭제된 주문의 JSONB도 인덱스에 포함되어 인덱스 크기·유지보수 비용이 증가한다. 완료 대시보드 등 active 전용 쿼리에서는 partial index가 더 효율적일 수 있다.
- **권장 수정**: JSONB containment 쿼리가 대부분 active 주문 대상이라면 `WHERE status <> 'DELETED' AND deleted_at IS NULL` 추가 검토. 전체 주문 대상 쿼리가 많다면 현행 유지.

---

## 3. 검증 포인트별 결과

### C-0: active 주문 필터 통일

| 항목 | 결과 | 비고 |
|------|------|------|
| `Order.active_filter()` 정의 | ✅ | `status != 'DELETED' AND deleted_at.is_(None)` 정확히 구현 |
| apps/* active_filter 사용 | ✅ | grep 결과, `Order.status != 'DELETED'` / `deleted_at.is_(None)` 단독 사용 없음 (backups/docs 제외) |
| models.py __table_args__ | ✅ | `ix_orders_*_active` 인덱스에 `deleted_at.is_(None)` 포함 |
| services/db_indexes.py | ✅ | raw SQL에 `status <> 'DELETED' AND deleted_at IS NULL` 포함 |

### C-1/C-2: CONCURRENTLY 마이그레이션

| 항목 | 결과 | 비고 |
|------|------|------|
| COMMIT 후 DDL 실행 | ✅ | `_run_concurrently`가 COMMIT 후 CREATE INDEX 실행 |
| C-1 ix_orders_active_id | ✅ | `WHERE status <> 'DELETED' AND deleted_at IS NULL` 포함 |
| C-2 ix_orders_structured_data_gin | ⚠️ | partial 조건 없음 (위 Findings 참조) |
| downgrade CONCURRENTLY | ✅ | DROP INDEX CONCURRENTLY 사용 |

### order_trash.py

| 항목 | 결과 | 비고 |
|------|------|------|
| 휴지통 조회 | ✅ | `Order.status == 'DELETED'` 유지 (L96, L124, L172) |
| active 조회 | ✅ | `delete_order`, `reset_order_ids`에서 `Order.active_filter()` 사용 |
| 복원/영구삭제 | ✅ | `Order.status == 'DELETED'` 또는 `Order.id`로 조회 (의도에 맞음) |

### personal_board, erp_orders_completion 등 복합 조건

| 파일 | 사용 패턴 | 결과 |
|------|-----------|------|
| personal_board | `Order.active_filter()` + `Order.status.in_(...)` | ✅ 논리적 |
| erp_orders_completion | `Order.active_filter()` + `Order.is_erp_beta` + `Order.status.in_(TARGET_STATUSES)` | ✅ 논리적 |
| erp_dashboard, erp_production_page 등 | `Order.active_filter()` + `Order.is_erp_beta.is_(True)` | ✅ 논리적 |
| personal_board._recent_work | `Order.id.in_(order_ids)` 만 사용 | ⚠️ active_filter 미적용 (위 Findings) |

---

## 4. Code Reviewer 체크리스트 요약

| 카테고리 | 항목 | 결과 |
|----------|------|------|
| **클린코드** | 함수 50줄 이하, docstring | ✅ active_filter docstring 존재 |
| **클린코드** | 타입 힌트 (신규 함수) | ⚠️ active_filter 반환 타입 미명시 (and_ 객체) |
| **보안** | SQL injection | ✅ ORM/active_filter 사용, raw SQL은 상수 |
| **성능** | N+1 | ✅ 변경 범위 내 N+1 없음 |
| **아키텍처** | Blueprint 패턴 | ✅ 유지 |
| **아키텍처** | API 응답 형식 | ✅ 변경 없음 |

---

## 5. Open Questions

1. **CONCURRENTLY 마이그레이션**: `env.py`의 `context.begin_transaction()`과 수동 COMMIT 조합이 실제 Railway/로컬에서 정상 동작하는지 확인 필요. 실패 시 `transaction_per_migration=False` 또는 수동 DDL 실행 전략 검토.
2. **personal_board._recent_work**: 삭제된 주문을 최근 작업에 노출할지 여부 결정. 노출하지 않으면 `active_filter` 추가 권장.
3. **C-2 GIN 인덱스**: JSONB 쿼리가 active 전용인지, 전체 주문 대상인지에 따라 partial 조건 적용 여부 결정.

---

## 6. Residual Risks

1. **Alembic 트랜잭션 경계**: `COMMIT` 후 context manager 종료 시 동작이 드라이버/버전에 따라 다를 수 있음. 실제 마이그레이션 실행으로 검증 필요.
2. **인덱스 중복**: `db_indexes.py`의 `idx_order_*`와 migration의 `ix_orders_active_id`가 유사한 역할. `idx_order_erp_beta` 등은 `is_erp_beta = true` 등 추가 조건이 있어 구분되나, `ix_orders_active_id`는 `status <> 'DELETED' AND deleted_at IS NULL`만 포함. 기존 partial index와의 충돌 여부 확인 필요.
3. **미검증 영역**: `scripts/geocode_backfill.py`, `erp_build_step_runner.py` 등 스크립트의 `active_filter` 사용은 grep으로 확인했으나, 실제 실행 경로 검증은 수행하지 않음.

---

## 7. 보고 요약 (System 4)

| 항목 | 내용 |
|------|------|
| **What was found** | active_filter 통일은 적절히 적용됨. CONCURRENTLY 마이그레이션 트랜잭션 전략, personal_board._recent_work의 active_filter 미적용, C-2 GIN 인덱스 partial 조건 부재 등 3건 발견. |
| **What was changed** | 변경 없음 (code-reviewer는 읽기 전용). |
| **Why** | CONCURRENTLY는 PostgreSQL에서 트랜잭션 외부 실행이 필수이며, env.py의 기본 트랜잭션 래핑과 충돌 가능성이 있음. _recent_work는 UX 정책에 따라 의도적일 수 있어 수정 여부는 결정 필요. C-2는 쿼리 패턴에 따라 partial 적용 검토 권장. |
