# 실측 대시보드 지도 변환 지연 GDM 조사 보고서

**조사일**: 2026-03-15  
**대상**: 실측 대시보드 > 지도 클릭 > 지도 변환(주문→좌표 표시) 느림  
**요청**: Phase 1~3 변경과 연관성 포함 정밀 조사

---

## 1. 현상 요약

| 항목 | 내용 |
|------|------|
| **증상** | 실측 대시보드에서 지도 클릭 후 진입 시, 주문→좌표 변환이 이전보다 매우 느림 |
| **사용자 인상** | "들어가자 마자 주문건이 다 변환이 됐었는데" 지금은 느림 |
| **진입 경로** | `/erp/measurement?date=...&open_map=1` → redirect → `/map_view?date=...&status=ALL&dashboard=measurement` |

---

## 2. 지도 플로우 정리

### 2.1 초기 로드 (최초 진입 / 필터 변경)

```
1. loadMap() → GET /api/generate_map?date=...&status=...&dashboard=measurement
2. api_generate_map (erp_map.py:216~):
   - Order.active_filter() + measurement 필터 + OrderScheduleDate join (date 있으면)
   - query.order_by(Order.id.desc()).limit(limit).all()  (limit 기본 200)
   - dashboard=='measurement' → self_measurement_four_checks_done(o) Python 필터
   - lat/lng 있는 것 → map_data, 없는 것 → to_geocode 수집
   - to_geocode → enqueue_geocode_order_address(order.id) + db.commit
   - Folium HTML 생성 → JSON 응답
3. 프론트: map_html 렌더, orders 목록 표시
4. hasPending이면 15초 후 loadMap(true) 폴링 예약
```

### 2.2 폴링 (pending 있을 때)

```
1. loadMap(true) → GET /api/map_data?date=...&status=...&dashboard=measurement
2. api_map_data (erp_map.py:66~): 동일 쿼리 구조
3. 새로 geocode 완료된 건만 currentOrders에 반영, updateOrderList
4. stillPending && retries < 5 → 15초 후 재폴링
```

### 2.3 "변환" 의미 구분

| 구분 | 설명 | 느림 시 의심 지점 |
|------|------|-------------------|
| **A. 초기 API 응답 지연** | `/api/generate_map` 응답까지 시간 | DB 쿼리, Python 루프, Folium 생성 |
| **B. geocode 대기** | lat/lng 없는 주문이 RQ Worker 처리 후 폴링으로 반영 | enqueue→Worker 지연, 폴링 간격(15초) |

사용자 "들어가자 마자 다 변환됐다" → **대부분 lat/lng가 이미 DB에 있어 초기 응답만으로 표시**되었음을 의미.  
현재 느림은 **(A) 초기 응답 지연** 또는 **(B) pending 증가 + 폴링 간격** 중 하나 또는 둘 다일 수 있음.

---

## 3. Phase 1~3 변경과 erp_map 연관성

### 3.1 Phase A (2026-03-15)

| 항목 | erp_map.py 영향 |
|------|-----------------|
| JSONB flag_modified | erp_map.py는 `api_update_order_address`에서만 flag_modified 사용. generate_map/map_data 경로와 무관 |
| erp_policy stage 키 | 지도 API에서 erp_policy 직접 호출 없음 |
| except pass 제거 | erp_map.py 미수정 |

**결론**: Phase A와 지도 변환 지연 **연관 없음**.

---

### 3.2 Phase B (2026-03-15)

| 항목 | erp_map.py 영향 |
|------|-----------------|
| erp_dashboard User N+1 | erp_dashboard.py만 수정. erp_map.py 미수정 |
| 시공 Promise.all | erp_construction_scripts.html. erp_map 미수정 |
| 출고 정렬 중복 제거 | erp_shipment_dashboard.html. erp_map 미수정 |

**결론**: Phase B와 지도 변환 지연 **연관 없음**.

---

### 3.3 Phase C (2026-03-15)

| 항목 | erp_map.py 적용 |
|------|-----------------|
| Order.active_filter() | **78행**(api_map_data), **230행**(api_generate_map) 적용 |
| 정의 | `status != 'DELETED' AND deleted_at.is_(None)` |

**active_filter()가 쿼리 성능에 미치는 영향**:

- **이전**: erp_map에서 `Order.status != 'DELETED'` 또는 `deleted_at.is_(None)` 단독 사용 여부는 grep으로 확인 불가. Phase C 이전에도 soft-delete 제외는 암묵적으로 적용되었을 가능성 높음.
- **현재**: `and_(cls.status != 'DELETED', cls.deleted_at.is_(None))` — 두 조건 AND.
- **인덱스**: C-1 `ix_orders_active_id` (id DESC, WHERE status <> 'DELETED' AND deleted_at IS NULL) 마이그레이션이 **작성만 됐고, 로컬에서 `alembic upgrade head` 실패**로 **미적용 가능성** 있음 (PHASE_C_EXECUTION_REPORT 71행).
- **영향**: C-1 인덱스가 없으면 `active_filter` 조건이 Seq Scan 또는 기존 인덱스만으로 처리될 수 있음. `deleted_at`이 대부분 NULL이면 선택률 변화는 작을 수 있으나, **인덱스 미적용 시 쿼리 플랜 열화 가능성** 존재.

**결론**: Phase C와 **부분 연관 가능**. `active_filter()` 자체보다는 **C-1 인덱스 미적용**이 성능에 영향을 줄 수 있음.

---

## 4. Phase 1~3 외 변경 이력 (지도 관련)

### 4.1 2026-02-27 지도 Auto-poll 변경 (DECISIONS.md)

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 폴링 대상 | `/api/generate_map` (Folium 전체 재생성) | `/api/map_data` (좌표만 조회) |
| 폴링 간격 | **6초** (incidents/2026-02-22-remote-geocode-diagnosis.md) | **15초** |
| 최대 재시도 | **10회** | **5회** |

- **이유**: iframe 전체 재로드가 "자꾸 refresh된다"는 UX 문제 완화.
- **영향**: pending 주문이 있을 때, **첫 갱신까지 6초 → 15초**, **최대 대기 60초 → 75초**로 변경.

**이 변경이 "느림"의 주요 원인일 가능성이 높음.** Phase 1~3(2026-03-15)보다 **약 3주 앞선** 변경.

### 4.2 2026-02-22 지도 geocode 설계 (Phase C map design)

- 지도 로드 시 lat/lng 없는 주문에 대해 `enqueue_geocode_order_address` 호출 추가.
- 동기 geocode 제거, RQ Worker 비동기 처리로 전환.
- 이 시점부터 "들어가자 마자 다 변환"은 **lat/lng가 이미 DB에 있는 경우**에만 해당.

---

## 5. 조사 포인트별 분석

### 5.1 Phase C Order.active_filter()와 erp_map 쿼리 성능

- **쿼리 구조**: `Order.active_filter()` + measurement 필터 + (date 있으면) `OrderScheduleDate` join + `distinct()` + `order_by(Order.id.desc()).limit(limit)`.
- **인덱스**:
  - `idx_order_schedule_dates_composite` (kind, date, order_id) — OrderScheduleDate join에 유리.
  - `ix_orders_active_id` — **마이그레이션 미적용 시 없음**.
- **검증 방법**: `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` 로 실제 쿼리 플랜 확인. `ix_orders_active_id` 존재 여부 및 사용 여부 확인.

### 5.2 api_generate_map / api_map_data 쿼리 구조

- **limit**: `_resolve_map_limit` → 기본 200 (generate_map), 100 (map_data).
- **scan_limit**: 75행에서 정의되나 **쿼리에 사용되지 않음** (미사용 변수).
- **OrderScheduleDate join**: `date_filter` 있을 때만. 실측 대시보드에서 지도 클릭 시 `date` 있음 → join 수행.
- **Python 후처리**: `self_measurement_four_checks_done(o)` 로 DB에서 가져온 orders를 메모리에서 필터링. limit 200 이하이므로 부하는 제한적.

### 5.3 GEOCODE_POLL_INTERVAL 15초, RQ Worker 지연

- **폴링**: 15초 간격, 최대 5회 (map_view.html:643-644).
- **RQ Worker**: `enqueue_geocode_order_address` → Redis 큐 → Worker가 `geocode_order_address` 실행. Worker 부하/지연 시 첫 좌표 반영까지 시간 증가.
- **incidents 문서**: Worker가 건당 ~4.5초, 8건이면 ~36초 소요 가능.

### 5.4 "변환"이 geocode 대기인지, 초기 API 응답 지연인지

- **초기 API 지연**: Network 탭에서 `/api/generate_map` 응답 시간 확인.
- **geocode 대기**: "주소 변환 중... 15초 후 갱신" 배너 노출 여부. 노출되면 pending 존재 → 폴링 대기 중.

---

## 6. Phase 1~3 연관성 결론

| Phase | 연관성 | 근거 |
|-------|--------|------|
| **Phase A** | 없음 | erp_map.py 미수정 |
| **Phase B** | 없음 | erp_map.py 미수정 |
| **Phase C** | 부분 | active_filter() 적용. C-1 인덱스 미적용 시 쿼리 성능 저하 가능. 다만 2026-02-27 폴링 변경이 더 큰 영향 가능성 |

**종합**: Phase 1~3만으로 지연을 설명하기 어렵고, **2026-02-27 폴링 변경(6초→15초, 10회→5회)** 이 체감 지연의 주요 원인일 가능성이 높음.

---

## 7. 근본 원인 후보 및 검증 방법

### 7.1 후보 1: 폴링 간격·횟수 변경 (2026-02-27) — 가능성 높음

- **내용**: 6초→15초, 10회→5회.
- **검증**: `GEOCODE_POLL_INTERVAL_MS`를 6000으로 되돌리고, `GEOCODE_POLL_MAX_RETRIES`를 10으로 되돌린 뒤 체감 개선 여부 확인.
- **위험**: 2026-02-27 변경 이유(iframe refresh UX)와의 트레이드오프.

### 7.2 후보 2: C-1 인덱스 미적용 (Phase C)

- **내용**: `ix_orders_active_id` 미생성 시 active_filter 조건 처리 비효율.
- **검증**: `SELECT indexname FROM pg_indexes WHERE tablename='orders';` 로 인덱스 목록 확인. `EXPLAIN ANALYZE` 로 Seq Scan 여부 확인.
- **조치**: Railway 등 운영 DB에서 `alembic upgrade head` 실행.

### 7.3 후보 3: RQ Worker 지연

- **내용**: Worker 부하, Redis 지연, geocode job 대기열 증가.
- **검증**: Railway Worker 로그, Redis 큐 길이, geocode job 처리 시간 확인.
- **조치**: Worker 스케일 조정, geocode 병렬 처리 검토.

### 7.4 후보 4: lat/lng 미보유 주문 증가

- **내용**: 신규 주문·주소 변경으로 pending 비율 증가 → 폴링 대기 체감 증가.
- **검증**: `SELECT COUNT(*) FROM orders WHERE ... AND (lat IS NULL OR lng IS NULL) AND address IS NOT NULL AND address != ''` 등으로 pending 비율 확인.

---

## 8. 권장 조치

### 8.1 즉시 검증 (사용자 체감 확인)

1. **Network 탭**: `/api/generate_map` 응답 시간 측정 (2초 이내 정상, 5초 이상이면 API 병목).
2. **폴링 배너**: "주소 변환 중..." 노출 여부. 노출되면 geocode 대기 구간.
3. **폴링 간격 실험**: `GEOCODE_POLL_INTERVAL_MS = 6000`, `GEOCODE_POLL_MAX_RETRIES = 10` 으로 임시 복원 후 체감 비교.

### 8.2 단기 조치

1. **C-1 인덱스 적용**: Railway 등 운영 DB에서 `alembic upgrade head` 실행 후 `ix_orders_active_id` 생성 확인.
2. **폴링 파라미터 조정**: 15초가 체감상 과도하면 10초 등으로 완화. 5회는 유지해도 무방.
3. **scan_limit 활용 검토**: 현재 미사용. 대량 스캔 시 성능 개선에 활용 가능하나, 현재 limit 200 수준에서는 우선순위 낮음.

### 8.3 중기 조치

1. **geocode 선계산**: 실측 대시보드 진입 시점에 미리 geocode enqueue (현재는 지도 진입 시에만 enqueue).
2. **Worker 처리량**: geocode job 병렬 처리 또는 Worker 수 증가 검토.
3. **지도 쿼리 최적화**: `EXPLAIN ANALYZE` 기반으로 인덱스·쿼리 튜닝.

---

## 9. 참조

- `apps/api/erp_map.py` — api_generate_map, api_map_data
- `templates/map_view.html` — loadMap, GEOCODE_POLL_INTERVAL_MS, GEOCODE_POLL_MAX_RETRIES
- `docs/context/DECISIONS.md` — [2026-02-27] 지도 Auto-poll 방식 변경
- `docs/incidents/2026-02-22-remote-geocode-diagnosis.md` — 6초 폴링 도입
- `docs/evolution/PHASE_C_EXECUTION_REPORT_2026-03-15.md` — C-1 인덱스 마이그레이션
- `migrations/versions/phase_c_indexes_concurrently.py` — ix_orders_active_id 정의
