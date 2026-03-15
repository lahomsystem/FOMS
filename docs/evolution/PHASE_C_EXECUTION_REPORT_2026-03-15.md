# Phase C 실행 보고서 (2026-03-15)

**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md  
**실행일**: 2026-03-15

---

## 1. 실행 요약

| 항목 | 상태 | 비고 |
|------|------|------|
| C-0 soft-delete 기준 통일 | ✅ 완료 | `Order.active_filter()` 도입, 25+ 파일 적용 |
| C-1 active 주문 partial index | ✅ 마이그레이션 작성 | `ix_orders_active_id` (CONCURRENTLY) |
| C-2 JSONB GIN 인덱스 | ✅ 마이그레이션 작성 | `ix_orders_structured_data_gin` (CONCURRENTLY) |
| C-3 substring 검색 인덱스 | ⏸️ 보류 | 검색 필드 범위 확정 후 진행 (계획서 443행) |

---

## 2. C-0 상세

### 2.1 Order.active_filter() 정의

```python
# models.py
@classmethod
def active_filter(cls):
    """Phase C-0: active 주문 필터 (soft-delete 제외). status != DELETED AND deleted_at IS NULL."""
    from sqlalchemy import and_
    return and_(cls.status != 'DELETED', cls.deleted_at.is_(None))
```

### 2.2 적용 파일 (25+)

| 영역 | 파일 |
|------|------|
| models | models.py (Index __table_args__ 포함) |
| API | erp_orders_structured, erp_measurement, erp_shipment_settings, erp_orders_completion, orders, channel_integration, personal_board, chat/routes, erp_map |
| 대시보드 | dashboards, storage_dashboard, erp_dashboard, erp_measurement_dashboard, erp_shipment_page, erp_as_page |
| 페이지 | erp_production_page, erp_construction_page, erp_drawing_workbench, order_edit, order_pages, order_trash |
| 기타 | excel_import, db_indexes, geocode_backfill, erp_build_step_runner |

### 2.3 order_trash.py 유지

- 휴지통 조회: `Order.status == 'DELETED'` 유지
- active 조회(delete_order, reset_order_ids): `Order.active_filter()` 사용

---

## 3. C-1, C-2 마이그레이션

**파일**: `migrations/versions/phase_c_indexes_concurrently.py`

- **전략**: `COMMIT` 후 autocommit 모드에서 `CREATE INDEX CONCURRENTLY` 실행
- **C-1**: `ix_orders_active_id` ON orders (id DESC) WHERE status <> 'DELETED' AND deleted_at IS NULL
- **C-2**: `ix_orders_structured_data_gin` ON orders USING gin (structured_data)
- **downgrade**: `DROP INDEX CONCURRENTLY IF EXISTS` 사용

**실행**: `alembic upgrade head` (DATABASE_URL 설정 필요)

---

## 4. 코드 리뷰 반영

- **personal_board._recent_work()**: `Order.active_filter()` 추가 (삭제된 주문 최근 작업 제외)

---

## 5. 미실행/보류

- **C-3**: 계획서 443행 — "어떤 표현식 인덱스를 만들지 결정하기 전에 검색 필드 범위를 먼저 고정해야 한다."
- **마이그레이션 실제 실행**: 로컬 DATABASE_URL 인코딩 이슈로 `alembic current` 실패. Railway/운영 환경에서 `alembic upgrade head` 실행 필요.
