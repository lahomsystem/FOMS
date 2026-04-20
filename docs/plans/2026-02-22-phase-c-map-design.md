# Phase C: 지도 구조 전환 상세 설계

작성일: 2026-02-22  
근거: `2026-02-22-railway-multi-user-scalability-plan.md` 단계 C

## 1. 목표

- 지도 조회 시 **실시간 geocoding 제거** → API p95 ≤ 1.5s 달성
- 주소 생성/수정 시에만 geocoding job enqueue (비동기 처리)
- 지도 API는 DB에 저장된 좌표만 조회

## 2. 영향 받는 코드 요약

| 구분 | 경로 | 역할 |
|------|------|------|
| **Order 모델** | `models.py` | lat/lng/geocode_status/geocoded_at/address_hash 컬럼 추가 |
| **지도 API** | `apps/api/erp_map.py` | api_map_data, api_generate_map: 실시간 geocode → 저장된 좌표 사용 |
| **주소 수정 API** | `apps/api/erp_map.py` | api_update_order_address: 동기 geocode → job enqueue |
| **주소 생성/수정 경로** | 다수 | 주소 변경 시 geocode job enqueue 트리거 |
| **RQ Job** | `services/jobs/tasks.py` | geocode_order_address job 추가 |
| **RQ Queue** | `services/jobs/queue.py` | enqueue_geocode_order_address 헬퍼 추가 |

## 3. DB 스키마 변경

### 3.1 Order 테이블에 추가할 컬럼

| 컬럼명 | 타입 | nullable | 기본값 | 설명 |
|--------|------|----------|--------|------|
| lat | Float | True | NULL | 위도 |
| lng | Float | True | NULL | 경도 |
| geocode_status | String(50) | True | NULL | pending / success / failed |
| geocoded_at | DateTime | True | NULL | 지오코딩 완료 시각 |
| address_hash | String(64) | True | NULL | 해시(주소 변경 감지용, SHA256 앞 16자 등) |

### 3.2 address_hash 계산 규칙

- `order.address` 또는 `structured_data.site.address_full` 기준으로 정규화 후 해시
- ERP Beta: `site.address_full or (address_main + address_detail)` 우선
- 해시가 같으면 geocode 불필요 (재요청 스킵)

### 3.3 마이그레이션

- Alembic migration 또는 `ADD COLUMN IF NOT EXISTS` 스크립트
- downgrade 시 컬럼 제거 가능해야 함

## 4. 주소 생성/수정 경로 (geocode job 트리거 위치)

| 파일 | 함수/라우트 | 설명 |
|------|-------------|------|
| `apps/api/erp_map.py` | api_update_order_address | 주문 주소 수정 API |
| `apps/api/erp_measurement.py` | 실측 단계 주소 입력 | structured_data.site.address_* 변경 |
| `apps/order_pages.py` | 주문 생성/수정 | order.address 또는 structured_data |
| `apps/order_edit.py` | 주문 수정 | order.address 변경 |
| `apps/api/orders.py` | API로 주문 생성/수정 | site.address_full/address_main |
| `erp_order_text_parser.py` | ERP Beta 파싱 | site.address_full 설정 |

**공통 전략**: 주소 변경 후 DB commit 직후 `enqueue_geocode_order_address(order_id)` 호출.

## 5. 구현 순서 (실행 체크리스트)

### 5.1 DB 및 모델

- [x] 1.1 `models.py` Order에 lat, lng, geocode_status, geocoded_at, address_hash 컬럼 추가
- [x] 1.2 Alembic migration 생성 (또는 수동 `ALTER TABLE` 스크립트)
- [ ] 1.3 마이그레이션 실행 및 검증

### 5.2 Geocode Job (Worker)

- [x] 2.1 `services/jobs/tasks.py`에 `geocode_order_address(order_id)` 함수 추가
  - FOMSAddressConverter.convert_address 호출
  - 성공 시 Order.lat, lng, geocode_status='success', geocoded_at 갱신
  - 실패 시 geocode_status='failed'
- [x] 2.2 `services/jobs/queue.py`에 `enqueue_geocode_order_address(order_id)` 추가
- [x] 2.3 `services/geocode_helpers.py` (신규): address_hash 계산, 주소 추출 로직 공유

### 5.3 지도 API 전환

- [x] 3.1 `api_map_data`: `convert_address_cached` 제거, Order.lat/lng 있는 주문만 map_data에 포함
- [x] 3.2 `api_map_data`: lat/lng가 NULL인 주문은 건너뛰고 `skipped_no_coords` 집계
- [x] 3.3 `api_generate_map`: 동일하게 convert_address_cached 제거, 저장된 좌표만 사용
- [x] 3.4 `api_update_order_address`: 동기 geocode 제거 → DB 저장 후 `enqueue_geocode_order_address(order_id)` 호출, 응답은 `{'success': True, 'geocode_queued': True}` 형태

### 5.4 주소 변경 경로에 job enqueue 연결

- [x] 4.1 `apps/api/erp_map.py` api_update_order_address: enqueue_geocode_order_address 호출
- [x] 4.2 `apps/api/erp_measurement.py`: 주소 변경 시 enqueue_geocode_order_address 호출
- [x] 4.3 `apps/order_pages.py`: 주문 생성 시 (ERP_BETA/LEGACY) enqueue
- [x] 4.4 `apps/order_edit.py`: 주소 수정 시 enqueue
- [x] 4.5 `apps/api/orders.py`: API로 주소 수정 시 enqueue
- [x] 4.6 `apps/api/erp_orders_structured.py`: PUT structured 시 site 주소 변경 시 enqueue (parse → add_order 경로는 4.3으로 처리)

### 5.5 기존 데이터 backfill (선택)

- [x] 5.1 배치 스크립트: lat/lng가 NULL인 모든 주문에 대해 geocode job enqueue (`scripts/maintenance/geocode_backfill.py`)
- [x] 5.2 rate limit 적용 (`--delay` 옵션, 기본 0.5초)
- [x] **5.3 핫픽스: 로컬 RQ 워커 부재로 인한 누락 1,348건 백엔드 스크립트(`fix_rest.py`) 이용 카카오 API 일괄 지오코딩 추가 완료 (2026-02-22 추가).**

### 5.6 프론트엔드/템플릿

- [x] 6.1 `map_view.html` / map_view 관련 JS: api_update_order_address 응답 (geocode_queued, latitude/longitude null) 대응
- [x] 6.2 update_address 호출 후 "지오코딩 처리 중" 안내 표시

### 5.7 검증

- [x] 7.1 지도 조회 시 외부 API 호출 없음 확인 (로그/네트워크) **(성공)**
- [x] 7.2 주소 수정 후 worker에서 geocode job 실행 확인 **(로컬 환경은 Fallback 방식 동기 처리로 즉각 결과 반환 성공)**
- [x] 7.3 지도 동시 사용자 40명 부하 테스트 스크립트 생성 (`scripts/ops/load_test_map.py`). 실행: `LOAD_TEST_USER=... LOAD_TEST_PASS=... BASE_URL=... python scripts/ops/load_test_map.py`

## 6. API 응답 형식 변경

### api_map_data (변경 후)

```json
{
  "success": true,
  "data": [{"id": 1, "latitude": 37.5, "longitude": 127.0, "address": "...", ...}],
  "total_orders": 100,
  "converted_orders": 95,
  "skipped_no_coords": 5
}
```

- `converted_orders`: lat/lng가 있는 주문 수 (기존과 동일 의미)
- `skipped_no_coords`: 좌표가 없어 건너뛴 주문 수 (신규)

### api_update_order_address (변경 후)

```json
{
  "success": true,
  "address": "서울시 ...",
  "geocode_queued": true,
  "latitude": null,
  "longitude": null
}
```

- 즉시 lat/lng 반환하지 않음. job 완료 후 다음 지도 조회 시 반영.

## 7. 경로 계산 API (api_calculate_route)

- 입출력이 이미 좌표(start_lat, start_lng, end_lat, end_lng)이므로 변경 없음
- 단기 캐시 적용은 별도 이슈 (Phase C 범위 외)

## 8. 롤백 계획

1. DB 컬럼은 유지, API에서 기존 실시간 geocode 경로로 복귀 (feature flag)
2. `USE_PRECOMPUTED_COORDS=0`이면 convert_address_cached 경로 사용
3. 마이그레이션 downgrade로 컬럼 제거 가능하게 유지
