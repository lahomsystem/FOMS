# Phase C GDM 감리 보고서

**감리일**: 2026-03-15  
**감리자**: code-reviewer (FOMS Code Reviewer Agent)  
**대상**: Phase C 쿼리 기준/인덱스 정렬 실행 결과  
**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md  
**실행 보고서**: docs/evolution/PHASE_C_EXECUTION_REPORT_2026-03-15.md  
**코드 리뷰**: docs/evolution/PHASE_C_CODE_REVIEW_2026-03-15.md  

---

## 1. 무엇을 발견했는가 (What was found)

### C-0: soft-delete 기준 통일 — ✅ 통과

| 검증 항목 | 결과 | 근거 |
|-----------|------|------|
| active_filter 정의 | ✅ | `models.py` — `status != 'DELETED' AND deleted_at.is_(None)` |
| apps/* 적용 | ✅ | grep 기준 `Order.status != 'DELETED'` / `deleted_at.is_(None)` 단독 사용 제거 |
| __table_args__ Index | ✅ | `deleted_at.is_(None)` 포함 |
| db_indexes.py | ✅ | raw SQL에 `deleted_at IS NULL` 포함 |
| order_trash | ✅ | 휴지통은 `status == 'DELETED'`, active는 `active_filter()` |

### C-1, C-2: CONCURRENTLY 마이그레이션 — ⚠️ 검증 필요

| 검증 항목 | 결과 | 근거 |
|-----------|------|------|
| COMMIT 후 DDL | ✅ | `_run_concurrently()` 패턴 |
| C-1 ix_orders_active_id | ✅ | WHERE 조건 포함 |
| C-2 ix_orders_structured_data_gin | ⚠️ | partial 조건 없음 (계획서 C-2는 전체 JSONB 대상) |
| env.py 트랜잭션 | ⚠️ | 수동 COMMIT과 `begin_transaction()` 상호작용 실제 환경 검증 필요 |

### 코드 리뷰 Findings 반영

| Finding | 조치 |
|---------|------|
| personal_board._recent_work active_filter 미적용 | ✅ `Order.active_filter()` 추가 반영 |
| CONCURRENTLY 트랜잭션 전략 | ⏸️ 실제 마이그레이션 실행으로 검증 예정 |
| C-2 GIN partial 조건 | ⏸️ 쿼리 패턴 분석 후 필요 시 별도 마이그레이션 검토 |

---

## 2. 무엇을 작업/수정했는가 (What was changed)

- **본 감리**: 읽기 전용. 코드 수정은 실행 에이전트가 수행.
- **추가 수정**: code-reviewer Finding에 따라 `personal_board._recent_work()`에 `Order.active_filter()` 적용.

---

## 3. 왜 그런 결정을 내렸는가 (Why)

- **C-0**: 계획서 권장 기준 `status != 'DELETED' AND deleted_at IS NULL` 통일. helper `Order.active_filter()`로 추출하여 유지보수성 확보.
- **C-1, C-2**: PostgreSQL `CREATE INDEX CONCURRENTLY`는 트랜잭션 외부 실행 필수. `COMMIT` 후 DDL 실행 전략 채택. `transaction_per_migration=False` 또는 수동 DDL은 운영 절차 복잡도 증가로 현행 유지, 실제 실행 시 검증.
- **C-3**: 계획서 443행 — "검색 필드 범위를 먼저 고정" 전제 미충족으로 보류.
- **_recent_work**: 삭제된 주문이 브리핑 보드 최근 작업에 노출되는 것은 UX 일관성상 부적절. active_filter 적용.

---

## 4. Residual Risks

1. **CONCURRENTLY 마이그레이션**: Railway/운영 환경에서 `alembic upgrade head` 실행 시 트랜잭션 경계 이슈 가능. 실패 시 `transaction_per_migration=False` 또는 수동 DDL 전략 전환.
2. **인덱스 중복**: `db_indexes.py`의 `idx_order_*`와 `ix_orders_active_id` 역할 구분. `ix_orders_active_id`는 범용 active 주문용, `idx_order_erp_beta` 등은 도메인별 partial index.
3. **C-2 GIN**: JSONB containment 쿼리가 대부분 active 전용이면 partial index 전환 검토. 현행은 계획서 C-2 정의대로 전체 테이블 GIN 유지.
