# 실측 지도 주문 #2670, #2662 미표시 원인 분석

- **작성일**: 2026-03-15
- **대상**: Production 실측 대시보드 > 지도 검색 시 #2670, #2662 미표시
- **참조**: `docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md`, `apps/api/erp_map.py`, `apps/erp_measurement_dashboard.py`

---

## 1. 계획서 변경과의 연관성

### active_filter 변경이 원인인가?

**결론: 원인 아님.**

| 항목 | 내용 |
|------|------|
| 변경 전 | `Order.status != 'DELETED'` |
| 변경 후 | `Order.active_filter()` = `status != 'DELETED' AND deleted_at.is_(None)` |
| 판단 | "각각 검색하면 표시됨"이라면, 두 주문은 **모든 경로에서** active_filter를 통과함. deleted_at이 설정되어 있으면 개별 검색에서도 제외됨. 따라서 **active_filter 변경은 이 이슈의 원인이 아님**. |

---

## 2. 원인 후보 분석

### 2.1 deleted_at (가능성: 낮음)

- 두 주문에 `deleted_at`이 설정되어 있으면 `active_filter`로 제외됨.
- **모순**: "각각 검색하면 표시됨" → 개별 검색 시에도 `active_filter`가 적용되므로, deleted_at이 있으면 개별 검색에서도 미표시되어야 함.
- **진단**: Production DB에서 `deleted_at` 확인 필요.

### 2.2 limit (가능성: 높음)

| API | default_limit | URL 전달 |
|-----|---------------|----------|
| `/api/map_data` | 100 | 없음 |
| `/api/generate_map` | 200 | 없음 |

- 쿼리: `order_by(Order.id.desc()).limit(limit)`
- 2026-03-16 실측일 기준 100건(또는 200건) 초과 시, **ID가 작은 주문(2670, 2662)이 limit으로 잘림**.
- "각각 검색" 시:
  - 검색어(q)로 결과가 줄어들어 해당 주문이 limit 안에 들어오거나,
  - 날짜를 바꾸거나 비워서 전체 결과 수가 줄어들어 포함되거나,
  - 실측 대시보드에서 개별 주문 클릭 시 다른 경로(예: 날짜 없음)로 진입할 수 있음.

### 2.3 OrderScheduleDate (가능성: 중간)

- `dashboard=measurement` + `date=2026-03-16` 시:
  - `OrderScheduleDate` JOIN, `kind='measurement'`, `date='2026-03-16'` 필터 적용.
- 두 주문에 `OrderScheduleDate(kind='measurement', date='2026-03-16')` 레코드가 없으면 **날짜 필터에서 제외**.
- "각각 검색" 시 날짜 없이 검색하면 JOIN/날짜 필터가 달라질 수 있음.

### 2.4 search(q) 파라미터 (가능성: 중간)

- `api_generate_map`에서 `q`는 **SQL이 아니라 Python 후처리**로 적용됨.
- `searchable_parts`: `address`, `customer_name`, `product`, `notes`, `manager_name`, `structured_data.site.*` — **order.id 미포함**.
- 따라서 `q=2670`으로 주문 ID 검색은 **현재 구현으로는 불가**.
- "각각 검색"이 주소/고객명 등으로 검색해 결과 수를 줄이는 경우, limit 영향이 줄어들 수 있음.

---

## 3. 진단용 SQL (Production DB)

Production DB에서 아래 쿼리로 상태·날짜·좌표·순위를 확인한다.

```sql
-- 1) #2670, #2662 기본 상태
SELECT id, status, deleted_at, lat, lng, geocode_status, address
FROM orders
WHERE id IN (2670, 2662);

-- 2) OrderScheduleDate (measurement, 2026-03-16)
SELECT osd.order_id, osd.kind, osd.date, osd.source
FROM order_schedule_dates osd
WHERE osd.order_id IN (2670, 2662)
  AND osd.kind = 'measurement'
  AND osd.date = '2026-03-16';

-- 3) 2026-03-16 실측일 주문 수 (erp_map 쿼리와 동일 조건)
SELECT COUNT(DISTINCT o.id) AS total_count
FROM orders o
JOIN order_schedule_dates osd ON o.id = osd.order_id
WHERE osd.kind = 'measurement'
  AND osd.date = '2026-03-16'
  AND o.status != 'DELETED'
  AND o.deleted_at IS NULL
  AND (o.is_regional IS NOT TRUE OR o.is_self_measurement = TRUE)
  AND o.status NOT IN ('SELF_MEASUREMENT', 'SELF_MEASURED');

-- 4) #2670, #2662가 2026-03-16 실측일 결과에서 몇 번째인지 (id desc 기준)
WITH meas_ranked AS (
  SELECT o.id, ROW_NUMBER() OVER (ORDER BY o.id DESC) AS rn
  FROM orders o
  JOIN order_schedule_dates osd ON o.id = osd.order_id
  WHERE osd.kind = 'measurement'
    AND osd.date = '2026-03-16'
    AND o.status != 'DELETED'
    AND o.deleted_at IS NULL
    AND (o.is_regional IS NOT TRUE OR o.is_self_measurement = TRUE)
    AND o.status NOT IN ('SELF_MEASUREMENT', 'SELF_MEASURED')
)
SELECT id, rn,
  CASE WHEN rn > 100 THEN 'map_data(limit 100)에서 제외' ELSE '포함' END AS map_data,
  CASE WHEN rn > 200 THEN 'generate_map(limit 200)에서 제외' ELSE '포함' END AS generate_map
FROM meas_ranked
WHERE id IN (2670, 2662);
```

---

## 4. 해결 방향 (원인별)

### 4.1 limit이 원인인 경우

| 방안 | 설명 | 비고 |
|------|------|------|
| A. limit 상향 | `ERP_MAP_MAX_LIMIT` 환경변수 또는 기본값 상향 (예: 300) | 메모리·응답 시간 증가 |
| B. measurement 전용 limit | `dashboard=measurement`일 때 limit만 상향 | 실측일 하루 건수에 맞게 조정 |
| C. limit 제거(비권장) | 날짜 필터 시 limit 제거 | 대량 데이터 시 위험 |
| D. 페이지네이션 | offset/limit 기반 페이지네이션 | UI·API 변경 필요 |

**권장**: B. measurement 전용 limit 상향 (예: 300). `erp_map.py`에서 `dashboard=='measurement'`일 때 `default_limit`을 200→300으로 조정.

### 4.2 OrderScheduleDate가 원인인 경우

- 두 주문에 `measurement` + `2026-03-16` 레코드가 없으면, 날짜 정규화/동기화 로직 점검.
- `services/` 또는 주문 생성/수정 시 `OrderScheduleDate` 생성·갱신 경로 확인.

### 4.3 deleted_at이 원인인 경우 (가능성 낮음)

- `deleted_at`이 잘못 설정된 데이터 정정.
- soft-delete 정책과 `active_filter` 정의 재검토.

### 4.4 order.id 검색 지원 (UX 개선)

- `api_generate_map`의 `searchable_parts`에 `str(order.id)` 추가.
- `q=2670` 입력 시 해당 주문이 검색되도록 개선.

---

## 5. 즉시 실행 가능 수정 (limit 가설 기준)

`apps/api/erp_map.py`에서 `dashboard=='measurement'`일 때 limit 기본값 상향:

```python
# api_map_data (라인 74 근처)
limit = _resolve_map_limit(
    request.args.get('limit'),
    default_limit=200 if dashboard == 'measurement' else 100
)

# api_generate_map (라인 228 근처)
limit = _resolve_map_limit(
    request.args.get('limit'),
    default_limit=300 if dashboard == 'measurement' else 200
)
```

- `ERP_MAP_MAX_LIMIT`이 200이면 300은 적용되지 않으므로, 환경변수 또는 `_MAP_MAX_LIMIT_DEFAULT`도 함께 검토 필요.

---

## 6. 검증 절차

1. Production DB에서 위 진단 SQL 실행 → `deleted_at`, `OrderScheduleDate`, 순위 확인.
2. 순위가 100/200 초과이면 limit 원인으로 판단.
3. measurement 전용 limit 상향 적용 후, date=2026-03-16, dashboard=measurement로 #2670, #2662 표시 여부 확인.
4. (선택) order.id 검색 지원 추가 후 `q=2670` 검색 동작 확인.

---

## 7. 적용된 수정 (2026-03-15)

| 항목 | 수정 내용 |
|------|-----------|
| _MAP_MAX_LIMIT_DEFAULT | 200 → 300 |
| api_map_data default_limit | measurement 시 200 (기존 100) |
| api_generate_map default_limit | measurement 시 300 (기존 200) |
| searchable_parts | `str(order.id)` 추가 → q=2670 검색 가능 |
