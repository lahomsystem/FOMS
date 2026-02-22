# 2026-02-22 지도 주소 변환 미동작 (Worker online 후에도)

> GDM 조사 결과: 원인 및 해결안.

---

## 1. 현상

- **Worker**: `rq worker default` online 정상 기동
- **지도 화면** (`/map_view?date=2026-02-23&status=MEASURED`): 모든 주문에 "▲ 주소오류" 표시
- 좌표(lat/lng)가 NULL인 기존 주문이 변환되지 않음

---

## 2. 원인 분석

### 2.1 Geocode 트리거 지점

| 지점 | 동작 | 기존 주문 영향 |
|------|------|----------------|
| `api_update_order_address` (주소 수정) | `enqueue_geocode_order_address` 또는 동기 fallback | 주소 **수정 시에만** 실행 |
| `api_generate_map` (지도 로드) | 주문 목록 반환만 함 | **geocode enqueue 없음** |
| `geocode_backfill.py` | lat/lng NULL 건 일괄 enqueue | **Railway에서 미실행** |

### 2.2 핵심 원인

1. **기존 주문에 대한 geocode가 enqueue되지 않음**
   - `geocode_backfill.py`는 Railway에서 한 번도 실행되지 않음
   - `api_generate_map`은 주문 목록만 반환하고, lat/lng 없는 주문에 대해 enqueue를 하지 않음

2. **지도 로드 시 geocode 트리거 부재**
   - 주소 **수정 시에만** geocode가 실행됨
   - lat/lng가 없는 기존 주문은 사용자가 직접 주소를 수정하지 않는 한 변환되지 않음

3. **환경변수 의존**
   - FOMS 웹에 `USE_RQ_WORKER=1` + `REDIS_URL` 있으면 enqueue 가능
   - `USE_RQ_WORKER=0`(또는 미설정)이면 enqueue 실패 → 동기 fallback만 사용(주소 수정 시에만)

---

## 3. 해결안

### 3.1 Lazy Geocode Enqueue (권장·구현 완료)

`api_generate_map`에서 **geocode_failed 주문을 반환할 때 geocode job을 enqueue**하도록 변경.

- **동작**: 지도 로드 시 lat/lng 없는 주문 중 주소가 있으면 `enqueue_geocode_order_address(order_id)` 호출
- **중복 방지**: `geocode_status == 'pending'`이면 enqueue 스킵
- **효과**: 첫 로드에서 enqueue → Worker 처리 → 새로고침 시 좌표 표시

### 3.2 수동 geocode_backfill (선택)

Railway에서 `geocode_backfill.py`를 한 번 실행하려면:

1. 로컬에서 Railway DB/Redis 연결 후 실행
2. 또는 별도 "job" 서비스를 한 번 배포해 스크립트 실행 후 종료

---

## 4. 환경 설정 확인

Lazy enqueue가 동작하려면 **FOMS 웹 서비스**에 다음이 필요:

| 변수 | 값 | 비고 |
|------|-----|------|
| REDIS_URL | Redis 연결 URL | 프로젝트/Redis 서비스에서 공유 |
| USE_RQ_WORKER | 1 | FOMS에서 enqueue 가능하게 함 |

> **참고**: Worker offline 시에는 `docs/incidents/2026-02-22-railway-worker-map-utils.md` 대로 FOMS에 `USE_RQ_WORKER=0`을 두고 동기 fallback을 사용함. Worker online이면 `USE_RQ_WORKER=1`로 두어 enqueue 방식 사용 권장.

---

## 5. 참조

- `apps/api/erp_map.py`: `api_generate_map`, `api_update_order_address`
- `services/jobs/queue.py`: `enqueue_geocode_order_address`, `get_rq_queue`
- `scripts/geocode_backfill.py`: 일괄 enqueue 스크립트
- `docs/incidents/2026-02-22-railway-worker-map-utils.md`: Worker offline 시 대응
