# 실측 지도 재구현 Spec
> 작성일: 2026-03-15 | 상태: 🟢 **바로 실행 가능 — 구현 전제/문서 모순 정리 완료**
> 최종 검증: 2026-03-15 | 검증 상세: `docs/guides/validation/2026-03-15-measurement-map-rebuild-spec-validation.md`

---

## 0. 실행 준비도 (2026-03-15)

### 현재 구현 상태 분석

**검증 등급**: 🟢 **EXECUTABLE** — 현재 코드의 문제는 구현 대상이지만, 계획서 자체는 바로 착수 가능한 수준으로 정리됨

### 이번 정리에서 확정한 실행 규칙

1. 상태 모델은 `success | pending | failed` 3개만 사용한다. `unknown` 같은 4번째 상태는 도입하지 않는다.
2. 실측 지도의 shared query builder는 검색 함수만 복제하는 것이 아니라, 실측 대시보드의 **전체 주문 집합 규칙**을 맞춘다.
3. 주소 변경 helper는 **order mutation만 담당**하고, `commit()`과 `enqueue_geocode_order_address()`는 caller가 성공 경계에서 처리한다.
4. 실측 지도 진입 경로는 backend redirect뿐 아니라 `templates/erp_measurement_dashboard.html`의 직접 링크까지 함께 고친다.
5. `dashboard=measurement` 모드에서는 상태 필터를 `ALL`로 고정하고, UI에서도 숨기거나 비활성화한다.

### 현재 코드 이슈 (우선순위순)

#### Issue #1: Frontend이 DB 값을 무시하고 상태 추론 (우선도: 극상)
- **파일/라인**: `apps/api/erp_map.py:378`
- **현재 코드**: `geocode_status = getattr(order, 'geocode_status', None) or ('success' if (lat and lng) else 'failed')`
- **문제**: DB의 `geocode_status` 값을 좌표 유무로 덮어씀 → pending이 failed로 오분류될 수 있음
- **스펙 위반**: 1.2 요구사항 #3, 1.3 "단일 진실 소스"
- **수정방안**: 상태 정규화는 `success | pending | failed` 3상태만 반환하도록 canonical snapshot builder에서 처리하고, route 본문에서는 임의의 4번째 상태를 만들지 않는다.
- **소요시간**: 10분

#### Issue #2: Boolean geocode_failed + 상태 문자열 혼재 (우선도: 극상)
- **파일/라인**: `apps/api/erp_map.py:407-408`
- **현재 코드**: `'geocode_failed': lat is None or lng is None, 'conversion_status': geocode_status`
- **문제**: 두 필드의 의미 충돌 → pending/failed 구분 불가능
- **스펙 위반**: 2.3 "삭제 대상: geocode_failed만 보고 실패/성공을 추론하는 프론트 분기"
- **수정방안**: `geocode_failed` 필드 제거, API 응답에서 `conversion_status`만 사용
- **소요시간**: 15분 (+ frontend 수정)

#### Issue #3: Template poll이 수동 상태 추론 (우선도: 극상)
- **파일/라인**: `templates/map_view.html:1009-1015`
- **현재 코드**: `currentOrders` 배열의 수동 mutation 기반 상태 갱신
- **문제**: 서버 응답을 신뢰하지 않고 프론트에서 상태 결정
- **스펙 위반**: 1.2 요구사항 #6 "프론트는 수동 추론 대신 서버 응답 기준으로 갱신"
- **수정방안**: 서버 응답 데이터로 `currentOrders` 전체 재구성
- **소요시간**: 30분

#### Issue #4: Pending 상태 UI 미분화 (우선도: 상)
- **파일/라인**: `templates/map_view.html:1134, 1146`
- **현재 코드**: `geocode_failed` boolean만으로 UI 클래스 결정
- **문제**: pending과 failed를 구분할 수 없음
- **스펙 위반**: 1.2 요구사항 #4, #5
- **수정방안**: `conversion_status` enum 기반 UI (`success/pending/failed` 각각 다른 스타일)
- **소요시간**: 20분

#### Issue #5: 초기 로드 vs poll 검색 규칙 불일치 (우선도: 상)
- **파일/라인**: `apps/api/erp_map.py:67, 218` vs `apps/erp_measurement_dashboard.py:36`
- **문제**: `/api/generate_map`, `/api/map_data`, 대시보드가 다른 검색 로직 사용
- **스펙 위반**: 1.2 요구사항 #7 "같은 필터에서 동일한 주문 집합"
- **수정방안**: `services/map_snapshot.py` 신규 생성 — shared query builder
- **소요시간**: 2-3시간

#### Issue #6: 주소 수정 API 응답 계약 불일치 (우선도: 상)
- **파일/라인**: `apps/api/erp_map.py:537-598` (queue 경로 vs fallback 경로)
- **현재 상태**: queue 성공 시와 fallback 시 응답 구조 다름
- **문제**: 클라이언트가 일관성 있는 데이터 계약 기대 불가
- **스펙 위반**: 1.2 요구사항 #6, 2.2 "공통 Snapshot 계약"
- **수정방안**: 항상 `{success, address, conversion_status, latitude, longitude, geocode_queued}` 반환
- **소요시간**: 20분

#### Issue #7: Worker stale coords 미정리 (우선도: 중)
- **파일/라인**: `services/jobs/tasks.py:85-90`
- **현재 코드**: 실패 시 `order.lat`, `order.lng` 명시적 초기화 없음
- **문제**: 이전 좌표가 남아있을 수 있음
- **스펙 위반**: 2.2 "Worker 완료 규칙: failed는 `lat=null`, `lng=null`"
- **수정방안**: `order.lat = None; order.lng = None` 명시적 설정
- **소요시간**: 5분

#### Issue #8: services/map_snapshot.py 신규 파일 미존재 (우선도: 중)
- **파일**: `services/map_snapshot.py` (신규 생성 필요)
- **필요 함수**:
  - `build_measurement_map_query(db, date, q, manager, dashboard)` — shared query
  - `build_measurement_snapshot(orders)` — canonical DTO (orders, markers, summary)
- **소요시간**: 3-4시간

#### Issue #9: services/order_geocode.py 신규 파일 미존재 (우선도: 중)
- **파일**: `services/order_geocode.py` (신규 생성 필요)
- **필요 함수**:
  - `reset_order_geocode_on_address_change(order, new_address)` — 공통 helper
- **소요시간**: 1-2시간

### 실행 메모

**현재 코드에는 Spec 요구사항 #3, #4, #5, #6을 직접 위반하는 지점이 남아 있다.** 다만 아래 순서대로 구현하면 바로 착수 가능하다:

1. ✅ **Issue #1, #2** 수정 — DB 신뢰, 상태 추론 제거
2. ✅ **Issue #5, #8, #9** 수정 — 신규 서비스 레이어 생성
3. ✅ **Issue #3, #4** 수정 — Template 상태 머신 재작성
4. ✅ **Issue #6, #7** 수정 — 응답 계약 + Worker 규칙

### 예상 작업량

| Phase | 항목 | 예상시간 | 순서 |
|-------|------|---------|------|
| 1 | Issue #1, #2 수정 | 3-4h | 1순위 |
| 2 | Issue #5, #8, #9 (신규 services/) | 4-6h | 2순위 |
| 3 | Issue #3, #4 (Template 상태머신) | 3-4h | 3순위 |
| 4 | Issue #6, #7 (응답계약 + Worker) | 2-3h | 4순위 |
| — | 테스트 + 리뷰 | 2-3h | 병렬 |
| **총합** | | **14-20h** | |

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
실측 대시보드의 지도 화면(``/erp/measurement?...open_map=1`` → ``/map_view?dashboard=measurement``)을 다시 정리해,

- 해당 실측일 주문은 **주소 변환 성공/실패와 무관하게 우측 목록에 모두 표시**
- **좌표 변환 실패건만** 파스텔 분홍색으로 표시
- 주소 수정 후에는 **목록 주소 / 상세 주소 / 지도 마커 상태가 같은 규칙으로 함께 갱신**
- 초기 지도, 자동 poll, 주소 수정 후 상태 반영이 **같은 데이터 계약**을 사용

하도록 재구현한다.

### 1.2 기능 요구사항
1. 실측 지도 우측 목록은 선택한 실측일의 모든 주문을 표시해야 한다.
2. 지도 마커는 `lat/lng`가 있는 주문만 표시해야 한다.
3. 지오코딩 상태는 `success | pending | failed` 3가지로 명확히 구분해야 한다.
4. `failed` 상태만 분홍색 카드와 오류 배지를 사용해야 한다.
5. `pending` 상태는 실패와 같은 UI로 취급하지 말고, 별도 "변환 중" 상태로 보여야 한다.
6. 주소 수정 후 서버는 권위 있는 최신 주문 상태를 반환해야 하며, 프론트는 수동 추론 대신 서버 응답 기준으로 목록/상세/지도 상태를 갱신해야 한다.
7. 초기 로드(`/api/generate_map`)와 poll(`/api/map_data`)는 같은 필터와 같은 주문 집합을 기준으로 응답해야 한다.
8. 다른 화면에서 주소가 수정되어도 실측 지도에서 동일한 기준으로 반영되어야 한다.

### 1.3 예외/제약 조건
- 이번 작업에서는 **Folium 기반 지도**는 유지한다. 지도 엔진 교체는 범위 외다.
- GET 기반 지도 조회 API는 같은 입력에 대해 같은 주문 집합을 반환해야 한다.
- 지오코딩 성공 여부의 단일 진실 소스는 `Order.lat`, `Order.lng`, `Order.geocode_status`다.
- 프론트에서 `geocode_failed`를 임의 추론하는 구조는 제거하거나 최소화한다.
- 실측 지도 모드에서는 "해당 실측일 전체 주문" 의미가 흐려지지 않도록 상태 필터 의미를 단순화한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `apps/erp_measurement_dashboard.py` | 실측 대시보드 → 지도 진입 redirect 의미 고정 (`date`, `dashboard=measurement`, 검색어 유지, status는 ALL) |
| `templates/erp_measurement_dashboard.html` | 직접 지도 링크(`/map_view?...status=MEASURE...`)를 실측 지도 규칙에 맞게 정리 |
| `apps/api/erp_map.py` | 실측 지도용 shared query builder, canonical snapshot builder, 주소 수정 응답 계약 재설계 |
| `templates/map_view.html` | 목록/상세/지도/poll 상태 머신 재작성, 실패/대기/성공 UI 분리 |
| `services/jobs/tasks.py` | worker 성공/실패 시 좌표/상태 정합성 보장 (stale coords 제거) |
| `services/map_snapshot.py` (신규) | 지도/목록 공통 snapshot, shared query builder, canonical DTO 조립 |
| `services/order_geocode.py` (신규) | 주소 변경 시 geocode reset / enqueue 공통 helper |
| `services/geocode_helpers.py` | 주소 추출 공통 로직 재사용 |
| `apps/order_edit.py` / `apps/order_pages.py` / `apps/api/orders.py` / `apps/api/erp_measurement.py` / `apps/api/erp_orders_structured.py` | 주소 수정 시 공통 geocode reset helper 사용하도록 정리 |

### 2.2 아키텍처 방향
- **단일 진실 소스**
  - DB 기준: `Order.lat`, `Order.lng`, `Order.geocode_status`
  - API 기준: `conversion_status = success | pending | failed`
- **검색 의미 통일**
  - 실측 대시보드의 `_erp_order_search_filter()`만 복제하지 않는다.
  - `active_filter()`, 실측 대상 필터, `OrderScheduleDate.kind == 'measurement'`, 날짜 필터, `self_measurement_four_checks_done()` 제외까지 포함한 **실측 지도용 전체 주문 집합 규칙**을 공통화한다.
  - 같은 `date/q/manager/dashboard`에서 대시보드, 초기 지도, poll이 동일한 주문 집합을 봐야 한다.
- **measurement 모드 상태 필터 고정**
  - `dashboard=measurement`일 때는 backend에서 status를 `ALL`로 고정한다.
  - frontend는 status selector를 숨기거나 disabled 처리하고, 측정 지도에서 상태 필터 의미를 노출하지 않는다.
- **공통 Snapshot 계약**
  - `orders[]`: 우측 목록/상세 갱신용 canonical order DTO
  - `markers[]`: 지도 마커용 좌표 DTO
  - `summary`: `total_orders`, `marker_count`, `pending_count`, `failed_count`
- **초기 로드와 poll 통일**
  - `/api/generate_map`: `snapshot + map_html`
  - `/api/map_data`: 같은 snapshot에서 `orders + markers + summary` 반환
  - 두 API 모두 같은 shared query builder 사용
- **주소 수정 경로 통일**
  - 주소 변경 helper는 `address 저장 -> lat/lng 초기화 -> geocode_status=pending -> flag_modified(필요 시)`까지만 담당한다.
  - `db.commit()`과 `enqueue_geocode_order_address()`는 caller가 성공 경계에서 수행한다.
- **Worker 완료 규칙 고정**
  - success: `lat/lng 저장`, `geocode_status=success`
  - failed: `lat=null`, `lng=null`, `geocode_status=failed`
  - 주소 없음: `lat=null`, `lng=null`, `geocode_status=failed`
- **UI 상태 구분**
  - `success`: 일반 카드
  - `pending`: 중립 색상 + "변환 중" 배지
  - `failed`: 파스텔 분홍색 + "주소오류" 배지

### 2.3 삭제/정리 대상
- `apps/api/erp_map.py` 내부의 중복된 주문 조회/DTO 조립 로직
- `templates/map_view.html`의 `currentOrders` 수동 mutation 중심 poll 처리
- `geocode_failed`만 보고 실패/성공을 추론하는 프론트 분기
- 주소 수정 후 목록만 부분 갱신하고 상세/지도는 따로 노는 현재 구조

### 2.4 의존성 및 영향 범위
- DB 마이그레이션은 신규 컬럼 추가가 아니라 **기존 컬럼 의미 정리**가 핵심이다.
- 단, 기존 데이터 중 `geocode_status`와 `lat/lng`가 어긋난 행은 1회 정리 스크립트가 필요할 수 있다.
- Worker, Redis, Railway Web/Worker 설정은 유지하되, worker 실패 시 stale 좌표를 남기지 않도록 job 동작을 보강한다.

## 3. Steps — 실행 단계 (정밀검증 기반 갱신)

### **Phase 1: 데이터 계약 재정의 (우선도: 1, 예상: 3-4h)**

- [ ] **Step 1-1**: `apps/api/erp_map.py:378` 수정 — DB 신뢰 원칙 적용
  - 현재: `geocode_status = getattr(order, 'geocode_status', None) or ('success' if (lat and lng) else 'failed')`
  - 수정: route 내부의 임의 상태 추론을 제거하고, `build_measurement_snapshot()`가 `success | pending | failed` 3상태만 반환하도록 canonicalize
  - 검증: pending 상태가 failed로 오분류되지 않고, `unknown` 같은 추가 상태가 생기지 않는다.

- [ ] **Step 1-2**: `apps/api/erp_map.py:407-408` 수정 — boolean 필드 제거
  - 현재: `'geocode_failed': lat is None or lng is None, 'conversion_status': geocode_status`
  - 수정: `'conversion_status': geocode_status` (geocode_failed 제거)
  - 영향도: template/js 수정 필요 (Step 3 참조)
  - 검증: API 응답에 conversion_status만 있고, success/pending/failed 명확히 구분된다.

- [ ] **Step 1-3**: `apps/api/erp_map.py:592-598` 수정 — 응답 계약 통일
  - 현재: queue 경로와 fallback 경로의 응답 필드 다름
  - 수정: 항상 `{success, address, conversion_status, latitude, longitude, geocode_queued}` 반환
  - 검증: 어떤 경로든 같은 구조 응답

### **Phase 2: 신규 서비스 레이어 생성 (우선도: 2, 예상: 4-6h)**

- [ ] **Step 2-1**: `services/map_snapshot.py` 신규 파일 생성
  - **함수 1**: `build_measurement_map_query(db, date, q, manager, dashboard)`
    - 목적: 지도/대시보드 검색 규칙 통일 (Issue #5 해결)
    - 로직: `apps/erp_measurement_dashboard.py`의 실측 지도 관련 전체 규칙을 반영
      1. `Order.active_filter()`
      2. 실측 대상 필터 (`is_regional`, `SELF_MEASUREMENT`, `is_self_measurement`)
      3. `OrderScheduleDate.kind == 'measurement'` + 선택 날짜 필터
      4. 대시보드와 동일한 검색 의미 (`_erp_order_search_filter()` 기준)
      5. `manager` 필터
      6. `self_measurement_four_checks_done()` 제외 규칙
      7. `dashboard=measurement`일 때 status는 강제로 `ALL`
    - 입력: 날짜, 검색어, 담당자, dashboard 파라미터
    - 출력: SQLAlchemy query object
  - **함수 2**: `build_measurement_snapshot(orders, markers_only=False)`
    - 목적: canonical DTO 조립 (목록 + 지도 마커)
    - 구조:
      ```python
      {
        'orders': [
          {
            'id': int,
            'customer_name': str,
            'phone': str,
            'address': str,
            'product': str,
            'status': str,
            'received_date': str,
            'measurement_date': str,
            'scheduled_date': str,
            'completion_date': str,
            'manager_name': str,
            'notes': str,
            'conversion_status': 'success' | 'pending' | 'failed',
            'latitude': float or None,
            'longitude': float or None
          }
        ],
        'markers': [  # lat/lng 있는 주문만
          {
            'id': int,
            'customer_name': str,
            'latitude': float,
            'longitude': float,
            'address': str
          }
        ],
        'summary': {
          'total_orders': int,
          'marker_count': int,
          'pending_count': int,
          'failed_count': int,
          'success_count': int
        }
      }
      ```
    - 검증: 목록 카드 수 = total_orders, 마커 수 = marker_count, success/pending/failed 합 = total_orders

- [ ] **Step 2-2**: `services/order_geocode.py` 신규 파일 생성
  - **함수**: `reset_order_geocode_on_address_change(order, new_address)`
    - 목적: 주소 수정 경로 통일 (여러 파일에 산재된 로직 수렴)
    - 로직:
      1. ERP Beta 여부에 따라 address 저장 (order.address 또는 structured_data.site.address_full)
      2. `order.lat = None`, `order.lng = None` 명시적 초기화
      3. `order.geocode_status = 'pending'` 설정
      4. structured_data 변경 시 `flag_modified(order, 'structured_data')`
      5. 필요하면 정규화된 주소 문자열 반환
    - **중요**:
      - helper 내부에서 `db.commit()` 하지 않는다.
      - helper 내부에서 `enqueue_geocode_order_address()` 호출하지 않는다.
      - commit/queue는 각 caller가 기존 트랜잭션을 유지한 채 성공 경계에서 처리한다.
    - 적용 대상 파일 (Step 2-3 참조):
      - `apps/order_edit.py`
      - `apps/order_pages.py`
      - `apps/api/orders.py`
      - `apps/api/erp_measurement.py`
      - `apps/api/erp_orders_structured.py`
  - 검증: 어느 파일을 통해 수정하든 geocode_status='pending', lat/lng=None이 동일

- [ ] **Step 2-3**: `apps/api/erp_map.py:537-540` 수정 — helper 적용
  - 현재: erp_map.py 내부에 직접 구현
  - 수정: `from services.order_geocode import reset_order_geocode_on_address_change` 후 helper로 order mutation 수행 → caller에서 `db.commit()` → 성공 시 `enqueue_geocode_order_address(order_id)`
  - 검증: 주소 수정 직후 DB 상태 일관성 + 기존 트랜잭션 경계 유지

### **Phase 3: Template 상태 머신 재작성 (우선도: 3, 예상: 3-4h)**

- [ ] **Step 3-1**: `templates/map_view.html:1009-1015` 수정 — 수동 mutation 제거
  - 현재: `currentOrders` 배열에 부분 갱신 (geocode_failed와 좌표 기반 상태 추론)
  - 수정: 서버 응답 데이터로 `currentOrders` 전체 재구성
  - 로직:
    ```javascript
    fetch('/api/map_data?...')
      .then(r => r.json())
      .then(data => {
        if (data.success && Array.isArray(data.orders)) {
          currentOrders = data.orders;  // 전체 교체
          updateOrderList(currentOrders);
        }
      })
    ```
  - 검증: poll 응답만으로 목록이 완전히 갱신됨

- [ ] **Step 3-2**: `templates/map_view.html:1134, 1146` 수정 — UI 상태 분화
  - 현재: `geocode_failed` boolean으로만 판단 → pending/failed 구분 불가
  - 수정: `conversion_status` enum 기반 UI 클래스 + 배지
  - 코드:
    ```javascript
    // UI 클래스 결정
    const failedClass = order.conversion_status === 'failed' ? 'geocode-failed'
                      : order.conversion_status === 'pending' ? 'geocode-pending'
                      : '';

    // 배지 렌더링
    const badge = order.conversion_status === 'pending'
      ? '<span class="geocode-pending-badge"><i class="fas fa-hourglass-half"></i> 변환 중</span>'
      : order.conversion_status === 'failed'
      ? '<span class="geocode-failed-badge"><i class="fas fa-exclamation-triangle"></i> 주소오류</span>'
      : '';
    ```
  - 검증: pending은 중립색 + "변환 중", failed는 분홍색 + "주소오류"로 표시

- [ ] **Step 3-3**: `templates/map_view.html` CSS 추가 — pending 스타일
  - 신규 스타일:
    ```css
    .order-item.geocode-pending {
      background-color: #fff8e1;  /* 옅은 노란색 */
      border-left: 4px solid #ffc107;
    }
    .geocode-pending-badge {
      background-color: #ffc107;
      color: #000;
      /* ... */
    }
    ```
  - 검증: pending 상태가 시각적으로 failed와 구분됨

### **Phase 4: 검색 규칙 통일 (우선도: 4, 예상: 2-3h)**

- [ ] **Step 4-1**: `apps/api/erp_map.py:67-68, 218-460` 수정 — map_snapshot 사용
  - 현재: 자체 검색 로직 구현
  - 수정:
    ```python
    from services.map_snapshot import build_measurement_map_query, build_measurement_snapshot

    # /api/generate_map
    orders = build_measurement_map_query(db, date, q, manager, 'measurement').all()
    snapshot = build_measurement_snapshot(orders)

    # /api/map_data
    orders = build_measurement_map_query(db, date, q, manager, 'measurement').all()
    snapshot = build_measurement_snapshot(orders)
    ```
  - 검증: 대시보드/초기 로드/poll이 같은 날짜+검색어에서 동일한 주문 ID 집합 반환

- [ ] **Step 4-2**: `templates/erp_measurement_dashboard.html:728` 수정 — 직접 지도 링크 정리
  - 현재: `/map_view?date=...&status=MEASURE&dashboard=measurement` 직접 진입
  - 수정: measurement 모드 규칙에 맞게 `status=ALL` 또는 status 파라미터 제거
  - 검증: 어떤 버튼으로 진입해도 measurement 모드의 주문 집합이 동일

- [ ] **Step 4-3**: `templates/map_view.html` 수정 — measurement 모드 status filter 잠금
  - 현재: `dashboard=measurement`여도 status selector가 그대로 노출됨
  - 수정: measurement 모드에서 status selector를 숨기거나 disabled 처리하고, 요청 파라미터에서도 `ALL`만 사용
  - 검증: measurement 지도에서 status 변경으로 주문 집합이 흔들리지 않음

### **Phase 5: Worker 규칙 정리 (우선도: 5, 예상: 1-2h)**

- [ ] **Step 5-1**: `services/jobs/tasks.py:85-90` 수정 — stale coords 제거
  - 현재: failed 시 좌표 초기화 없음
  - 수정:
    ```python
    if lat is not None and lng is not None:
        order.lat = float(lat)
        order.lng = float(lng)
        order.geocode_status = 'success'
    else:
        order.lat = None       # 명시적 초기화
        order.lng = None
        order.geocode_status = 'failed'
    ```
  - 검증: worker 실패 후 좌표가 명확히 None으로 설정됨

### **Phase 6: Legacy 데이터 정리 및 검증 (우선도: 6, 예상: 2-3h)**

- [ ] **Step 6-1**: Migration 스크립트 작성 — 모순 데이터 정리
  - 목적: `geocode_status='failed'`인데 lat/lng 있거나, `success`인데 좌표 없는 행 정리
  - 쿼리: 모순 주문 수 집계 및 정리
  - 검증: 모순 주문이 0이거나 정리 대상이 명확히 집계됨

- [ ] **Step 6-2**: 회귀 검증 시나리오
  - 테스트 케이스:
    1. 신규 주문 생성 → 지도 목록 표시 확인
    2. 주소 없는 주문 → pending 상태 표시 확인
    3. Geocode 성공 → 마커 표시 + success 상태 확인
    4. Geocode 실패 → pending → failed 상태 변화 확인
    5. 다른 화면에서 주소 수정 → 지도에 반영 확인
    6. 필터(날짜/담당자/검색) 적용 → 대시보드와 지도 결과 일치 확인

## 4. 검증 기준 (정밀검증 반영)

### Phase별 검증

#### Phase 1 검증 (데이터 계약)
- [ ] `python -c "import app; print('APP_OK')"` 통과 — Syntax 오류 없음
- [ ] API 응답에 `geocode_failed` 필드 없고 `conversion_status` 만 있음
- [ ] 같은 주문의 `conversion_status`와 `lat/lng` 상태가 일관성 있음 (pending은 좌표 없음, success는 좌표 있음)

#### Phase 2 검증 (신규 서비스)
- [ ] `/api/generate_map?date=YYYY-MM-DD` 응답에 `snapshot` 포함
  - `orders[]` 길이 = `summary.total_orders`
  - `markers[]` 길이 = `summary.marker_count` = conversion_status='success'인 주문 수
  - `summary.pending_count + summary.failed_count + summary.success_count = total_orders`
- [ ] 같은 날짜 기준으로 대시보드 주문 수와 지도 우측 목록 주문 수가 정확히 일치 (검색어/담당자 필터도 포함)
- [ ] Shared query builder 적용 후 `/api/generate_map` 와 `/api/map_data` 가 같은 주문 ID 배열 반환

#### Phase 3 검증 (UI 상태 머신)
- [ ] `failed` 상태 주문만 분홍색(#fff0f3) 카드 + "주소오류" 배지로 표시
- [ ] `pending` 상태 주문은 노란색(#fff8e1) 카드 + "변환 중" 배지로 표시 (분홍색 아님)
- [ ] `success` 상태 주문은 일반 카드(#fff) + 배지 없음으로 표시
- [ ] Poll 응답(`/api/map_data`)만으로 목록이 완전히 재렌더되고, 프론트 수동 mutation 없음

#### Phase 4 검증 (검색 규칙)
- [ ] 검색(`q`), 담당자(`manager`) 필터 적용 시:
  - 실측 대시보드 주문 목록 = 초기 지도 로드(`/api/generate_map`) 주문 목록 = poll(`/api/map_data`) 주문 목록
  - 세 화면의 order ID 집합이 정확히 일치
- [ ] `dashboard=measurement` 모드에서는 status selector가 숨김/비활성화되고, backend도 `ALL`만 사용

#### Phase 5 검증 (Worker)
- [ ] Worker 성공 후:
  - 해당 주문의 `lat/lng` 저장 ✓
  - `geocode_status='success'` 저장 ✓
  - 지도에 마커 표시 ✓
- [ ] Worker 실패 후:
  - 해당 주문의 `lat=None, lng=None` 명시적 초기화 ✓
  - `geocode_status='failed'` 저장 ✓
  - 주문은 목록에 남되 분홍색 실패 상태로 표시 ✓

#### Phase 6 검증 (Legacy 데이터)
- [ ] 마이그레이션 실행 후:
  - `geocode_status='success'`인데 `lat IS NULL OR lng IS NULL` 인 행: 0개
  - `geocode_status='failed'`인데 `lat IS NOT NULL AND lng IS NOT NULL` 인 행: 0개
  - 모순된 데이터가 없거나 정리 대상이 명확히 집계됨

#### 통합 검증 (E2E)
- [ ] `/erp/measurement?date=YYYY-MM-DD&open_map=1` 진입 시 `/map_view?...dashboard=measurement` 로 302 redirect 후 최종 200 OK
- [ ] 사용자 시나리오 전체 재현 및 통과:
  1. 신규 주문 생성 후 지도 진입 → "변환 중" 상태 표시
  2. Worker 완료 대기 → 자동 poll로 "변환 중" → 성공 또는 "주소오류" 상태 변화 확인
  3. "주소오류" 주문의 주소 수정 → 목록/상세/지도 모두 반영
  4. 담당자 필터 적용 → 대시보드와 지도 결과 일치
- [ ] 브라우저 콘솔에 SyntaxError, TypeError 없음
- [ ] 네트워크 탭에서 API 응답 구조가 스펙과 일치

## 5. 수정 파일 체크리스트 (라인 단위 정확성)

### 즉시 수정 필요 (Blocking)

| 파일 | 라인 | 변경 | 우선도 | 예상시간 |
|------|------|------|--------|---------|
| `apps/api/erp_map.py` | 378 | 상태 추론 제거 (Issue #1) | 극상 | 10min |
| `apps/api/erp_map.py` | 407-408 | geocode_failed 필드 제거 (Issue #2) | 극상 | 15min |
| `apps/api/erp_map.py` | 592-598 | 응답 계약 통일 (Issue #6) | 상 | 20min |
| `services/jobs/tasks.py` | 85-90 | stale coords 초기화 (Issue #7) | 중 | 5min |
| `templates/erp_measurement_dashboard.html` | 728 | 직접 지도 링크 status 정리 (measurement 모드 고정) | 상 | 10min |
| `templates/map_view.html` | 1009-1015 | 수동 mutation 제거 (Issue #3) | 극상 | 30min |
| `templates/map_view.html` | 715, 882-889, 987-999 | measurement 모드 status filter 잠금 | 상 | 20min |
| `templates/map_view.html` | 1134, 1146 | UI 상태 분화 (Issue #4) | 상 | 20min |

### 신규 파일 생성 (Required)

| 파일 | 함수 | 라인수 | 예상시간 | 우선도 |
|------|------|--------|---------|--------|
| `services/map_snapshot.py` | `build_measurement_map_query()` | ~70 | 2-3h | 중상 |
| `services/map_snapshot.py` | `build_measurement_snapshot()` | ~100 | 1-2h | 중상 |
| `services/order_geocode.py` | `reset_order_geocode_on_address_change()` | ~40 | 1-2h | 중 |

### 기존 파일 정리 (Integration)

| 파일 | 변경 사항 | 예상시간 |
|------|---------|---------|
| `apps/order_edit.py` | geocode reset helper 적용 | 20min |
| `apps/order_pages.py` | geocode reset helper 적용 | 20min |
| `apps/api/orders.py` | geocode reset helper 적용 | 20min |
| `apps/api/erp_measurement.py` | geocode reset helper 적용 | 20min |
| `apps/api/erp_orders_structured.py` | geocode reset helper 적용 | 20min |

### 추가 작업

| 항목 | 설명 | 예상시간 |
|------|------|---------|
| DB Migration | Legacy 데이터 정리 스크립트 작성 | 1-2h |
| CSS 추가 | `.geocode-pending` 스타일 추가 | 15min |
| 테스트 작성 | E2E 시나리오 6개 검증 | 2-3h |
| 코드 리뷰 | 모든 변경사항 검증 | 1-2h |

---

## 5. 참고 자료
- 관련 결정: `docs/context/DECISIONS.md`
  - 2026-02-27 `지도 Auto-poll 방식 변경`
  - 2026-02-22 `Railway Worker + Geocode 컬럼`
- 관련 인시던트:
  - `docs/incidents/2026-02-22-map-geocode-not-running.md`
  - `docs/incidents/2026-02-22-remote-geocode-diagnosis.md`
- 관련 설계:
  - `docs/plans/2026-02-22-phase-c-map-design.md`
  - `docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md`

## 6. 구현 전 확정할 가정 및 실행 게이트

### 가정

- `measurement` 지도 모드에서는 **실측일 전체 주문**이 목표이므로 status는 `ALL`로 고정하고, UI에서도 상태 필터를 노출하지 않는다.
- 분홍색은 `failed` 전용으로 사용하고, `pending`은 중립 색상으로 분리한다.
- 이번 단계에서는 Folium 유지, correctness 우선으로 구현한다.
- 신규 공통 로직은 `erp_map.py` 내부 임시 함수가 아니라 `services/` 레이어로 분리해 중복 재발을 막는다.

### 실행 게이트 ✅ (정밀검증 완료)

**현 상태**: 🟢 **READY TO EXECUTE** — 아래 체크리스트를 구현 시작 체크리스트로 사용

#### Pre-implementation Checklist

- [ ] **Issue #1-#7 영향 범위 파악**
  - [ ] `/api/map_data` 응답을 사용하는 모든 클라이언트 (template/js) 확인
  - [ ] `geocode_failed` boolean 사용처 전수 조사 (grep 필수)
  - [ ] Poll 메커니즘의 timeout/retry 로직 검토

- [ ] **신규 서비스 레이어 설계 승인**
  - [ ] `build_measurement_map_query()` 함수 시그니처 확정
  - [ ] Snapshot 구조 JSON 스키마 확정
  - [ ] Helper 함수의 예외 처리 정책 확정

- [ ] **모든 테스트 데이터 준비**
  - [ ] success/pending/failed 상태 주문 각 1건 (최소)
  - [ ] Shared query 검증용: 같은 필터 조건의 예상 주문 ID 집합

- [ ] **검증 리포트 승인**
  - [ ] `docs/guides/validation/2026-03-15-measurement-map-rebuild-spec-validation.md` 검토
  - [ ] 모든 Issue가 실제 코드에서 재현되었는지 확인
  - [ ] 예상 소요시간 14-20시간 수용 여부 확인

#### 구현 시작 조건

✅ 모든 핵심 이슈 파악 완료
✅ 수정 범위와 예상 시간 합의 완료
✅ Phase별 구현 순서 확정 완료
✅ 예상 테스트 시나리오 6개 준비 완료

→ **이 조건 충족 후 "실행" 버튼을 누를 수 있습니다.**
