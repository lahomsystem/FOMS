# 주문 #2662 실측 지도 마커 미표시 — 초정밀 근본 원인 분석

- **작성일**: 2026-03-15
- **대상**: 주문 #2662 — 지오코딩 성공(lat/lng 있음)에도 실측 지도에 마커 미표시
- **분석 범위**: map_snapshot, erp_map, erp_display, OrderScheduleDate, limit

---

## 1. 실행 경로 전체 추적 (코드 레벨)

### 1.1 API 진입점: `/api/map_data`

**조건**: `dashboard=measurement` AND `date` 파라미터 존재

```python
# apps/api/erp_map.py L343-356
if dashboard == 'measurement' and date_filter:
    db = get_db()
    query = build_measurement_map_query(db, date_filter, search_query, manager_filter, dashboard, limit)
    orders = query.all()
    orders = [o for o in orders if not self_measurement_four_checks_done(o)]
    snapshot = build_measurement_snapshot(orders, manager_filter)
    return jsonify({..., 'markers': snapshot['markers'], ...})
```

**limit 결정** (L336-339):
- `default_limit = 300` (measurement)
- `max_limit = min(ERP_MAP_MAX_LIMIT env, _MAP_MAX_LIMIT_DEFAULT=300)`
- 최종 limit: `min(request limit, 300)` → **최대 300건**

---

### 1.2 build_measurement_map_query (map_snapshot.py L30-81)

| 단계 | 조건 | #2662 제외 시점 |
|------|------|-----------------|
| 1 | `Order.active_filter()` | status=DELETED 또는 deleted_at NOT NULL → 제외 |
| 2 | `_measurement_search_filter(query, q)` | q 있으면 customer/manager/address/structured_data에 검색어 없음 → 제외 |
| 3 | dashboard='measurement' | `(is_regional≠True AND status∉[SELF_MEASUREMENT,SELF_MEASURED]) OR is_self_measurement=True` | is_regional=True 이면서 is_self_measurement=False → 제외 |
| 4 | date 있음 | `JOIN OrderScheduleDate`, `kind='measurement'`, `date=date_filter` | **OrderScheduleDate에 (2662, measurement, 선택날짜) 없음 → 제외** |
| 5 | `order_by(Order.id.desc()).limit(limit)` | id 내림차순 상위 limit건만 반환 | **상위 300건 밖이면 → 제외** |

---

### 1.3 self_measurement_four_checks_done (erp_display.py L23-33)

```python
def self_measurement_four_checks_done(order):
    if not getattr(order, 'is_self_measurement', False):
        return False
    return (
        getattr(order, 'measurement_completed', False)
        and getattr(order, 'regional_sales_order_upload', False)
        and getattr(order, 'regional_blueprint_sent', False)
        and getattr(order, 'regional_order_upload', False)
    )
```

- **is_self_measurement=False** → 항상 False (제외 안 됨)
- **is_self_measurement=True** 이고 4체크 모두 True → **제외** (실측 대시보드에서 숨김)

**적용 위치**:
1. `api_map_data` L351: `orders = [o for o in orders if not self_measurement_four_checks_done(o)]`
2. `build_measurement_snapshot` L198: `if self_measurement_four_checks_done(order): continue`

---

### 1.4 build_measurement_snapshot (map_snapshot.py L164-250)

| 단계 | 조건 | #2662 제외 시점 |
|------|------|-----------------|
| 1 | `manager_filter` | manager_filter 있으면 manager_name에 포함 여부 검사 | 담당자 필터에 불일치 → 제외 |
| 2 | `self_measurement_four_checks_done(order)` | 위와 동일 | 4체크 완료 자가실측 → 제외 |
| 3 | 마커 추가 | `lat is not None and lng is not None` | **lat/lng 없으면 마커 미추가** (목록에는 포함 가능) |

**중요**: 사용자 전제 "지오코딩 성공" → lat/lng는 있다고 가정. 따라서 **마커 미표시의 주된 원인은 1~2단계(쿼리/필터)에서 아예 orders에 포함되지 않는 것**일 가능성이 높음.

---

## 2. #2662가 지도에 안 나오는 모든 가능 경로 (체크리스트)

| # | 경로 | 발생 조건 | 진단 방법 |
|---|------|-----------|-----------|
| 1 | **limit 잘림** | id desc 상위 300건 밖 | 아래 SQL 4번으로 순위 확인 |
| 2 | **OrderScheduleDate 없음** | (2662, measurement, 선택날짜) 레코드 없음 | 아래 SQL 2번 |
| 3 | **OrderScheduleDate 날짜 불일치** | 사용자가 선택한 날짜와 osd.date 다름 | 사용자 선택 날짜와 SQL 2번 결과 비교 |
| 4 | **status/is_regional 필터** | is_regional=True & is_self_measurement=False | SQL 1번 |
| 5 | **self_measurement_four_checks_done** | is_self_measurement=True & 4체크 모두 True | SQL 1번 |
| 6 | **manager_filter** | 담당자 필터 적용 시 manager_name 불일치 | UI에서 담당자 필터 사용 여부 확인 |
| 7 | **search(q) 필터** | q 파라미터로 customer/address 등에 검색어 없음 | URL에 q 파라미터 확인 |
| 8 | **lat/lng 없음** | DB에 lat/lng NULL (지오코딩 실패/미실행) | SQL 1번 — 사용자 전제와 상충 시 재확인 |
| 9 | **active_filter** | status=DELETED 또는 deleted_at NOT NULL | SQL 1번 |

---

## 3. Production DB 진단용 SQL

```sql
-- ============================================================
-- 주문 #2662 실측 지도 마커 미표시 진단 (Production DB 실행)
-- ============================================================

-- 1) #2662 기본 상태 (lat, lng, geocode_status, 4체크, status, is_regional)
SELECT
  id,
  status,
  deleted_at,
  is_regional,
  is_self_measurement,
  lat,
  lng,
  geocode_status,
  measurement_completed,
  regional_sales_order_upload,
  regional_blueprint_sent,
  regional_order_upload,
  LEFT(address, 80) AS address_preview
FROM orders
WHERE id = 2662;

-- 2) OrderScheduleDate (measurement kind) — 어떤 날짜에 등록되어 있는지
SELECT order_id, kind, date, source
FROM order_schedule_dates
WHERE order_id = 2662
  AND kind = 'measurement'
ORDER BY date;

-- 3) 사용자가 선택한 실측일(예: 2026-03-16)에 #2662가 포함되는지
--    ※ date_filter 값을 실제 선택한 날짜로 바꿔서 실행
SELECT EXISTS (
  SELECT 1
  FROM order_schedule_dates osd
  WHERE osd.order_id = 2662
    AND osd.kind = 'measurement'
    AND osd.date = '2026-03-16'  -- ← 실제 선택한 날짜로 변경
) AS has_measurement_date;

-- 4) 해당 날짜 기준 id desc 순위 (limit 300 밖인지 확인)
--    ※ date_filter 값을 실제 선택한 날짜로 바꿔서 실행
WITH meas_ranked AS (
  SELECT
    o.id,
    ROW_NUMBER() OVER (ORDER BY o.id DESC) AS rn
  FROM orders o
  JOIN order_schedule_dates osd ON o.id = osd.order_id
  WHERE osd.kind = 'measurement'
    AND osd.date = '2026-03-16'  -- ← 실제 선택한 날짜로 변경
    AND o.status != 'DELETED'
    AND o.deleted_at IS NULL
    AND (
      (o.is_regional IS NOT TRUE AND o.status NOT IN ('SELF_MEASUREMENT', 'SELF_MEASURED'))
      OR o.is_self_measurement = TRUE
    )
)
SELECT
  id,
  rn,
  CASE WHEN rn > 300 THEN 'limit 300으로 제외' ELSE '포함' END AS map_result
FROM meas_ranked
WHERE id = 2662;

-- 5) 해당 날짜 전체 주문 수 (limit 300 초과 여부)
SELECT COUNT(DISTINCT o.id) AS total_for_date
FROM orders o
JOIN order_schedule_dates osd ON o.id = osd.order_id
WHERE osd.kind = 'measurement'
  AND osd.date = '2026-03-16'  -- ← 실제 선택한 날짜로 변경
  AND o.status != 'DELETED'
  AND o.deleted_at IS NULL
  AND (
    (o.is_regional IS NOT TRUE AND o.status NOT IN ('SELF_MEASUREMENT', 'SELF_MEASURED'))
    OR o.is_self_measurement = TRUE
  );
```

---

## 4. 근본 원인별 수정 방안

### 4.1 limit 잘림 (가장 유력)

| 방안 | 설명 | 비고 |
|------|------|------|
| **A. limit 상향** | `_MAP_MAX_LIMIT_DEFAULT` 300 → 500, `ERP_MAP_MAX_LIMIT` env 동일 | 메모리·응답 시간 증가 |
| **B. measurement 전용 limit** | `dashboard=measurement`일 때만 500 등으로 상향 | 실측일 하루 건수에 맞게 |
| **C. 날짜 필터 시 limit 완화** | date 있으면 limit 500 등 | 날짜로 이미 범위 축소됨 |
| **D. 페이지네이션** | offset/limit 기반 | UI·API 변경 필요 |

**권장**: B 또는 C. 실측일 하루당 300건 초과가 빈번하면 limit 500으로 상향.

---

### 4.2 OrderScheduleDate 없음/날짜 불일치

| 원인 | 대응 |
|------|------|
| OrderScheduleDate 레코드 없음 | `sync_order_dates` 호출 경로 확인. 주문 생성/수정 시 `order_date_sync_event` 리스너 또는 명시적 `sync_order_dates` 호출 |
| structured_data.schedule.measurement.date와 osd.date 불일치 | `collect_order_schedule_date_specs`가 `measurement_date`(legacy)와 `structured_data.schedule.measurement.date`(beta) 모두 반영하는지 확인 |
| 날짜 형식 차이 | `order_date_sync`에서 YYYY-MM-DD 정규화 적용 여부 확인 |

**즉시 조치**: 주문 #2662에 대해 `sync_order_dates` 수동 실행 후 OrderScheduleDate 재확인.

```python
# Python REPL 또는 스크립트
from db import get_db
from models import Order
from services.order_date_sync import sync_order_dates

db = get_db()
order = db.query(Order).filter(Order.id == 2662).first()
if order:
    sync_order_dates(order, db)
    db.commit()
```

---

### 4.3 self_measurement_four_checks_done 제외

- 자가실측 주문이고 4체크 완료 시 **의도적으로** 실측 대시보드에서 제외됨.
- #2662가 자가실측이 아니면 이 경로는 해당 없음.
- 자가실측인데 실측 지도에 보여야 한다면, 정책 변경(4체크 완료 주문도 표시) 검토 필요.

---

### 4.4 manager_filter / search(q)

- UI에서 담당자 필터·검색어 사용 시에만 영향.
- 담당자 필터 없이도 미표시면 이 경로는 해당 없음.

---

## 5. 즉시 적용 가능한 수정 제안

### 5.1 limit 상향 (가장 빠른 완화)

```python
# apps/api/erp_map.py
_MAP_MAX_LIMIT_DEFAULT = 500  # 300 → 500 (2026-03-15, #2662 limit 잘림 완화)
```

또는 measurement 전용:

```python
# _resolve_map_limit 호출 시
default_limit = 500 if dashboard == 'measurement' else 300
```

그리고 `_MAP_MAX_LIMIT_DEFAULT`를 500 이상으로 설정.

---

### 5.2 OrderScheduleDate 백필 검증

주문 생성/수정 시 `sync_order_dates`가 호출되는지 확인. `order_date_sync_event` 리스너가 등록되어 있으면 `before_flush`에서 자동 동기화됨. 미등록 시:

- `app.py` 또는 DB 초기화 시 `register_date_sync_listener()` 호출 여부 확인
- 기존 주문에 대해 `scripts/maintenance/backfill_phase4_dates.py` 실행으로 OrderScheduleDate 백필

---

### 5.3 order.id 검색 지원 (UX)

`_measurement_search_filter`에 `Order.id` 검색 추가:

```python
# services/map_snapshot.py _measurement_search_filter
term = f'%{q.strip()}%'
return query.filter(
    or_(
        Order.id.cast(String).ilike(term),  # 주문 ID 검색
        Order.customer_name.ilike(term),
        ...
    )
)
```

---

## 6. 검증 절차

1. Production DB에서 위 진단 SQL 실행 → `lat`/`lng`, `OrderScheduleDate`, 순위 확인
2. **순위 > 300** → limit 원인. limit 상향 후 재검증
3. **OrderScheduleDate 없음** → sync_order_dates/백필 실행 후 재검증
4. **4체크 완료** → 정책 검토 (표시 여부)
5. limit 상향 적용 후 `date=선택날짜`, `dashboard=measurement`로 #2662 표시 여부 확인

---

## 7. 요약

| 가능성 | 원인 | 확인 방법 | 즉시 조치 |
|--------|------|-----------|-----------|
| **높음** | limit 300 잘림 | SQL 4번 순위 확인 | limit 500 상향 |
| **중간** | OrderScheduleDate 없음/날짜 불일치 | SQL 2, 3번 | sync_order_dates, 백필 |
| **낮음** | self_measurement_four_checks_done | SQL 1번 is_self_measurement, 4체크 | 정책 검토 |
| **낮음** | manager_filter / q | UI 사용 패턴 | - |
| **매우 낮음** | lat/lng NULL | SQL 1번 | 사용자 전제와 상충 시 재확인 |

**다음 단계**: Production DB에서 진단 SQL 실행 → 순위·OrderScheduleDate 결과에 따라 위 조치 적용.
