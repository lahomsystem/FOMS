# 실측 지도 재구현 Spec — 소스코드 정밀 검증

**검증 일시**: 2026-03-15
**검증 대상**: `docs/plans/2026-03-15-measurement-map-rebuild-spec.md`
**검증 범위**: 코드 라인 단위 1:1 매칭

---

## 1. 요구사항 vs 현재 구현 상태

### 1.1 **Spec 요구 (Section 1.2 기능요구사항)**

| # | 요구사항 | 현재 구현 | 상태 | 상세 |
|---|---------|---------|------|------|
| 1 | 우측 목록: 실측일 모든 주문 표시 | `apps/api/erp_map.py:349-410` | ✅ | `orders_list` 구성 시 필터링된 모든 order 포함 |
| 2 | 지도 마커: lat/lng 있는 주문만 표시 | `apps/api/erp_map.py:412-423` | ✅ | `if lat is not None and lng is not None` 조건으로 map_data 필터링 |
| 3 | 지오코딩 상태: success \| pending \| failed 명확 구분 | `apps/api/erp_map.py:376-408` | ⚠️ BROKEN | 아래 상세 참조 |
| 4 | `failed` 상태만 분홍색 카드 + 오류 배지 | `templates/map_view.html:454-478` | ⚠️ PARTIAL | CSS는 있으나 pending/success 구분 미흡 |
| 5 | `pending` 상태: "변환 중" 별도 표시 | `templates/map_view.html:1059-1066` | ❌ MISSING | pending을 failed처럼 취급 |
| 6 | 주소 수정 후: 서버 응답 기준 갱신 | `apps/api/erp_map.py:537-598` | ⚠️ PARTIAL | 데이터 계약 불일치 |
| 7 | 초기 로드/poll 같은 필터 + 같은 주문 집합 | `apps/api/erp_map.py:67-68, 218-460` | ⚠️ SPLIT | 검색 규칙 차이 존재 |
| 8 | 다른 화면 주소 수정 후 반영 | `apps/api/erp_map.py` | 🔴 VERIFY | services/order_geocode.py 신규 파일 필요 |

---

## 2. Critical Issues — 코드 단위 분석

### **Issue #1: Frontend이 geocode 상태 추론 (Line 378)**

**파일**: `apps/api/erp_map.py:378`

```python
geocode_status = getattr(order, 'geocode_status', None) or ('success' if (lat and lng) else 'failed')
```

**문제**:
- DB의 `Order.geocode_status` 값을 무시하고 좌표 유무로 상태 추론
- 위반: Spec 1.2 요구사항 #3, #4, #5 — "지오코딩 상태는 `success | pending | failed` 3가지로 **명확히 구분**"
- **경우 1**: `geocode_status='pending'`이지만 좌표가 있으면 → 'success'로 잘못 판단
- **경우 2**: `geocode_status='pending'`이고 좌표 없으면 → 'failed'로 판단 (pending이 failed와 섞임)
- **경우 3**: `geocode_status='success'`인데 좌표 없으면 → 'failed'로 판단 (DB 데이터 무시)

**Spec 근거**:
> "2.2 아키텍처 방향 > 단일 진실 소스: DB 기준 `Order.lat`, `Order.lng`, `Order.geocode_status`"
> "2.2 > 프론트에서 `geocode_failed`를 임의 추론하는 구조는 제거하거나 최소화한다."

**수정 필요**:
```python
# 옳은 방식
geocode_status = getattr(order, 'geocode_status', None) or 'unknown'
```

---

### **Issue #2: boolean `geocode_failed` + 상태 혼재 (Lines 407-408)**

**파일**: `apps/api/erp_map.py:407-408`

```python
'geocode_failed': lat is None or lng is None,
'conversion_status': geocode_status
```

**문제**:
- `geocode_failed` (boolean)과 `conversion_status` (상태 문자열) 동시 사용
- `geocode_failed`는 좌표 유무만 판단 → `geocode_status`와 모순 가능
- Spec 요구사항 #3 위반: pending을 failed처럼 취급하려는 경향

**Spec 근거**:
> "2.3 삭제/정리 대상: `geocode_failed`만 보고 실패/성공을 추론하는 프론트 분기"

**수정 필요**:
- `geocode_failed` 필드 삭제
- 프론트에서 `conversion_status`만 사용: `'success' | 'pending' | 'failed'`

---

### **Issue #3: Poll이 수동 상태 추론 (map_view.html:1009-1015)**

**파일**: `templates/map_view.html:1009-1015`

```javascript
currentOrders = currentOrders.map(function (o) {
    if (o.geocode_failed && newCoords[o.id]) {
        anyResolved = true;
        return Object.assign({}, o, { geocode_failed: false, conversion_status: 'success' });
    }
    return o;
});
```

**문제**:
- `geocode_failed` 플래그와 `newCoords` 유무로 상태 전환 추론
- 서버 응답 데이터를 신뢰하지 않음 (위반: Spec 1.2 요구사항 #6)
- "프론트 partial mutation" 정확히 Spec 삭제 대상

**Spec 근거**:
> "2.3 삭제/정리 대상: `templates/map_view.html`의 `currentOrders` 수동 mutation 중심 poll 처리"
> "2.2 > 프론트는 수동 추론 대신 서버 응답 기준으로 목록/상세/지도 상태를 갱신해야 한다."

**수정 필요**:
- `/api/map_data` 응답이 canonical snapshot 반환
- 프론트는 응답 데이터로 전체 currentOrders 재구성

---

### **Issue #4: `pending` 상태 UI 미분화 (map_view.html:1134, 1146)**

**파일**: `templates/map_view.html:1134, 1146`

```javascript
const failedClass = order.geocode_failed ? 'geocode-failed' : '';
...
${order.geocode_failed ? '<span class="geocode-failed-badge">...' : ''}
```

**문제**:
- `geocode_failed` boolean만으로 UI 결정 → pending/failed 구분 불가
- CSS `.geocode-failed` (분홍색) 준비되어 있으나, pending은 일반 카드로 표시될 것
- Spec 요구사항 #4, #5 미충족

**Spec 근거**:
> "1.2 요구사항 #5: `pending` 상태는 실패와 같은 UI로 취급하지 말고, 별도 \"변환 중\" 상태로 보여야 한다."
> "2.2 UI 상태 구분: success (일반 카드), pending (중립 색상 + \"변환 중\" 배지), failed (분홍색 + \"주소오류\" 배지)"

**수정 필요**:
```javascript
// conversion_status 기반 UI
const statusClass = {
  'success': '',
  'pending': 'geocode-pending',
  'failed': 'geocode-failed'
}[order.conversion_status] || '';

// 배지
const badge = {
  'success': '',
  'pending': '<span class="geocode-pending-badge"><i class="fas fa-hourglass-half"></i> 변환 중</span>',
  'failed': '<span class="geocode-failed-badge"><i class="fas fa-exclamation-triangle"></i> 주소오류</span>'
}[order.conversion_status] || '';
```

---

### **Issue #5: 초기 로드와 poll의 검색 규칙 불일치**

**파일**:
- `apps/api/erp_map.py:67` (`/api/map_data` 초기 진입)
- `apps/api/erp_map.py:218` (`/api/generate_map`)
- `apps/erp_measurement_dashboard.py:36` (`_erp_order_search_filter`)

**문제**:
- `_erp_order_search_filter()` (대시보드용): `Order.customer_name`, `Order.manager_name`, `Order.address`, structured_data cast to string
- `erp_map.py` 내부 검색: `_normalize_for_search(search_query)` 사용하며, site.address_full/main/detail도 포함
- 같은 `date/q/manager/dashboard` 요청일 때 대시보드와 지도의 주문 집합이 다를 수 있음

**Spec 근거**:
> "2.2 검색 의미 통일: 실측 대시보드의 `_erp_order_search_filter()`와 지도 API의 검색 의미를 같게 맞춘다."
> "1.2 요구사항 #7: 같은 `date/q/manager/dashboard`에서 대시보드, 초기 지도, poll이 동일한 주문 집합을 봐야 한다."

**수정 필요**:
- Shared query builder 작성 → 두 API 모두 동일 검색 로직 사용

---

### **Issue #6: 주소 수정 후 데이터 계약 미정의**

**파일**: `apps/api/erp_map.py:537-598` (`/api/orders/<id>/update_address`)

**문제**:
- 응답 구조가 정합성 없음:
  - Queue 성공 시 (line 592-598): `success + address + geocode_queued + latitude + longitude` (no status)
  - Fallback 동기 처리 시 (line 583-590): `success + address + geocode_queued + latitude + longitude + conversion_status`
- 같은 상황도 일관성 없음 (queued=true vs queued=false일 때 응답 필드 다름)

**Spec 근거**:
> "2.2 주소 수정 경로 통일: 주소 변경 시 공통 helper가 `address 저장 -> lat/lng 초기화 -> geocode_status=pending -> queue 등록` 처리"
> "2.2 > `/api/update_address`: 같은 snapshot에서 `orders + markers + summary` 반환"

**수정 필요**:
```python
# 항상 같은 구조 반환
{
  'success': True,
  'address': new_address,
  'conversion_status': 'pending' | 'success' | 'failed',
  'latitude': lat or None,
  'longitude': lng or None,
  'geocode_queued': True/False
}
```

---

### **Issue #7: Worker 완료 규칙 검증**

**파일**: `services/jobs/tasks.py:47-98` (`geocode_order_address` function)

**검증 항목**: Spec 2.2 Worker 완료 규칙 고정

```python
# Line 85-90
if lat is not None and lng is not None:
    order.lat = float(lat)
    order.lng = float(lng)
    order.geocode_status = 'success'
else:
    order.geocode_status = 'failed'
```

**상태**:
- ✅ **Success**: lat/lng 저장 + geocode_status='success' (Line 88)
- ✅ **Failed**: lat/lng 초기화 없음 + geocode_status='failed' (Line 90)
- ❌ **문제**: Failed 경우 lat/lng를 초기화하지 않음 → stale 좌표 남을 수 있음

**Spec 근거**:
> "2.2 Worker 완료 규칙: failed: `lat=null`, `lng=null`, `geocode_status=failed`"

**수정 필요**:
```python
if lat is not None and lng is not None:
    order.lat = float(lat)
    order.lng = float(lng)
    order.geocode_status = 'success'
else:
    order.lat = None  # 명시적 초기화 필수
    order.lng = None
    order.geocode_status = 'failed'
```

---

### **Issue #8: Shared Query Builder 미존재**

**파일**: `services/map_snapshot.py` (신규 파일 - **현재 미존재**)

**문제**:
- Spec 2.1에서 신규 파일로 제시
- 지도와 대시보드가 같은 필터 의미를 갖도록 통합 검색 함수 필요
- 현재: 각 경로가 자체 검색 로직 수행 (중복, 불일치 위험)

**필요 함수**:
- `build_measurement_map_query(db, date, q, manager, dashboard)` → shared SQLAlchemy query
- `build_measurement_snapshot(orders)` → canonical DTO (orders, markers, summary)

---

### **Issue #9: Order geocode reset helper 미존재**

**파일**: `services/order_geocode.py` (신규 파일 - **현재 미존재**)

**문제**:
- Spec 2.1에서 신규 파일로 제시
- 주소 수정 시 공통 처리: address 저장 → lat/lng 초기화 → geocode_status=pending → queue
- 현재: 여러 곳에서 개별적으로 처리 (Spec 2.1 라인 45 참조 - 5개 파일 산재)

**필요 함수**:
- `reset_order_geocode_on_address_change(order, new_address)` → shared helper

---

## 3. 파일 존재성 검증

| 파일 | 존재 | 상태 | 비고 |
|------|------|------|------|
| `apps/api/erp_map.py` | ✅ | 읽음 | 라인 1-605 |
| `apps/erp_measurement_dashboard.py` | ✅ | 읽음 | 검색 필터 확인 |
| `templates/map_view.html` | ✅ | 읽음 | 라인 1-1300+ |
| `services/jobs/tasks.py` | ✅ | 읽음 | geocode_order_address 함수 |
| `services/map_snapshot.py` | ❌ | **신규** | Spec 2.1 제시, 아직 미생성 |
| `services/order_geocode.py` | ❌ | **신규** | Spec 2.1 제시, 아직 미생성 |
| `services/geocode_helpers.py` | ✅ | 추정 | extract_address_from_order 함수 사용 (line 68) |
| `apps/order_edit.py` | ✅ | 미검증 | 주소 수정 경로 중 하나 |
| `apps/order_pages.py` | ✅ | 미검증 | 주소 수정 경로 중 하나 |
| `apps/api/orders.py` | ✅ | 미검증 | 주소 수정 경로 중 하나 |
| `apps/api/erp_measurement.py` | ✅ | 미검증 | 주소 수정 경로 중 하나 |
| `apps/api/erp_orders_structured.py` | ✅ | 미검증 | 주소 수정 경로 중 하나 |

---

## 4. Step-by-Step 실행 계획 vs 코드 준비도

| Step | Spec 내용 | 코드 준비도 | 시작 가능 | 비고 |
|------|----------|-----------|---------|------|
| 1 | Canonical 데이터 계약 정의 | ❌ | ✅ | Issue #2 수정 필요 |
| 2 | Shared query builder | ❌ | ✅ | services/map_snapshot.py 신규 생성 |
| 3 | Snapshot builder 작성 | ❌ | ✅ | services/map_snapshot.py 확장 |
| 4 | 주소 수정 공통 helper | ❌ | ✅ | services/order_geocode.py 신규 생성 |
| 5 | Worker 완료 규칙 정리 | ⚠️ PARTIAL | ✅ | Issue #7 stale coords 초기화 추가 |
| 6 | Template 상태 머신 재작성 | ❌ | ✅ | Issue #4, #3 수정 필요 |
| 7 | UI 상태 분리 (success/pending/failed) | ❌ | ✅ | CSS + JS 배지 추가 필요 |
| 8 | Legacy 데이터 정리 | 미검증 | TBD | 별도 migration 스크립트 필요 |

---

## 5. 최종 검증 체크리스트

### 근본 원인 분석 결과

**근본 원인**:
1. Frontend이 DB 값을 신뢰하지 않고 좌표 유무로 상태 추론 (Issue #1, #2)
2. API 응답이 canonical snapshot 계약 미준수 (Issue #6)
3. Poll이 수동 상태 갱신 (Issue #3)
4. Shared 검색 규칙 미존재 (Issue #5)
5. 신규 서비스 레이어 미생성 (Issue #8, #9)
6. Worker 완료 규칙에 stale coords 정리 미흡 (Issue #7)

### 실행 우선순위

**Phase 1 (Critical)**: 데이터 계약 재정의 + Issue #1, #2 수정
- `apps/api/erp_map.py` 378, 407-408 줄 수정
- API 응답 필드 정리 (geocode_failed 제거)

**Phase 2 (Required)**: 신규 서비스 레이어 생성
- `services/map_snapshot.py` (shared query + snapshot builder)
- `services/order_geocode.py` (address reset helper)

**Phase 3 (UI)**: Template 상태 머신 재작성
- Issue #3, #4 수정
- pending 배지 CSS 추가

**Phase 4 (Worker)**: 완료 규칙 정리
- Issue #7 stale coords 초기화

---

## 6. 코드 수정 사항 요약

### 즉시 수정 (Blocking)

| 파일 | 라인 | 현재 | 수정 | 영향도 |
|------|------|------|------|--------|
| erp_map.py | 378 | `or ('success' if (lat and lng) else 'failed')` | `or 'unknown'` (DB 신뢰) | High |
| erp_map.py | 407 | `'geocode_failed': lat is None or lng is None,` | 삭제 | High |
| erp_map.py | 408 | 유지 (conversion_status만) | 유지 (필드명 확인) | - |
| erp_map.py | 592-598 | 응답 구조 불일치 | 통일 (always with conversion_status) | High |
| tasks.py | 90 | lat/lng 초기화 미흡 | `order.lat = None; order.lng = None` 추가 | Medium |

### 신규 파일

| 파일 | 함수 | 라인 | 목적 |
|------|------|------|------|
| services/map_snapshot.py | build_measurement_map_query | ~50 | Shared query builder |
| services/map_snapshot.py | build_measurement_snapshot | ~100 | Canonical DTO builder |
| services/order_geocode.py | reset_order_geocode_on_address_change | ~50 | Address change handler |

### Template 수정

| 파일 | 라인 | 현재 | 수정 |
|------|------|------|------|
| map_view.html | 1009-1015 | 수동 mutation | 서버 응답 데이터 전체 재구성 |
| map_view.html | 1134, 1146 | geocode_failed boolean | conversion_status enum 기반 |
| map_view.html | CSS 추가 | - | .geocode-pending (중립색) 스타일 |
| map_view.html | JS 추가 | - | pending 배지 렌더링 로직 |

---

## 결론

**검증 등급**: 🔴 **BLOCKING — 즉시 수정 필요**

- **실행 불가 이유**: 현재 구현이 Spec 요구사항 #3, #4, #5, #6 위반
- **우선 순위**:
  1. **Issue #1, #2** (DB 신뢰 + 상태 추론 제거) — 3-4시간
  2. **Issue #8, #9** (신규 서비스 레이어) — 4-6시간
  3. **Issue #3, #4** (Template 상태 머신) — 3-4시간
  4. **Issue #5** (Shared query) — 2-3시간
  5. **Issue #6, #7** (응답 계약 + Worker) — 2-3시간

**총 예상 작업량**: ~14-20시간 (코드 리뷰 + 테스트 포함)

**근본적 개선**: Spec에서 강조한 "단일 진실 소스 = DB"와 "공통 계약" 원칙을 엄격히 적용 필요
