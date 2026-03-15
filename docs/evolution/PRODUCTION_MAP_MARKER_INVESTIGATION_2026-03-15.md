# Production 주소 수정 후 지도 마커 미반영 문제 — 단계별 조사 보고서

**작성일**: 2026-03-15  
**대상**: Railway Production 원격 서버  
**증상**: 주소 수정 후 지도에 마커가 반영되지 않음 (로컬 수정·배포 완료 후에도 동일)

---

## Step 1: Production 환경 확인

### Railway 배포 구조

| 구성요소 | 설정 | 역할 |
|----------|------|------|
| **start.sh** | `USE_RQ_WORKER=1` → rq worker, 아니면 gunicorn | 단일 서비스 시 둘 중 하나만 실행 |
| **Procfile** | `web`: gunicorn / `worker`: rq worker | 다중 서비스 시 web·worker 분리 |
| **Dockerfile** | `CMD ["sh", "start.sh"]` | 단일 컨테이너 빌드 |
| **railway.toml** | `startCommand = "sh start.sh"` | Railway 기본 시작 명령 |

### RQ(REDIS_URL) 사용 여부

- **enqueue 조건**: `get_rq_queue()` → `REDIS_URL`만 있으면 큐 반환 (enqueue 가능)
- **USE_RQ_WORKER**: `start.sh` 전용 — 웹은 gunicorn, Worker만 rq 실행
- **결론**: Web 서비스에 `REDIS_URL`가 있으면 → enqueue 성공 → RQ 경로 사용  
  Web에 `REDIS_URL` 없으면 → enqueue 실패 → 동기 폴백 경로 사용

### RQ Worker 프로세스

- **Procfile worker**: `rq worker default --url $REDIS_URL` (별도 서비스로 기동)
- **railway-worker.toml**: `startCommand = "rq worker default --url $REDIS_URL"`
- **확인 필요**: Railway 대시보드에서 Worker 서비스가 **online**인지 확인

### 진단 포인트

| 상황 | Web REDIS_URL | Worker 상태 | 결과 |
|------|---------------|-------------|------|
| A | 있음 | Online | RQ 경로 → Worker 완료 후 폴링으로 마커 갱신 |
| B | 있음 | **Offline** | RQ 경로 → Job 큐에만 쌓임, 처리 안 됨 → **마커 영원히 미표시** |
| C | 없음 | - | 동기 폴백 → 즉시 geocode → 마커 표시 (수정 적용됨) |

**가장 유력한 원인**: Production Web에 `REDIS_URL`가 설정되어 있고, **Worker 서비스가 Offline**이거나 별도 서비스로 배포되지 않은 경우.

---

## Step 2: 코드 경로 추적

### api_update_order_address 분기 (erp_map.py 437~461행)

```
enqueue_geocode_order_address(order_id)
  ├─ queued=True  → JSON { geocode_queued: true, latitude: null, ... } → loadMap() → 폴링
  └─ queued=False → 동기 geocode_order_address() → order 재조회 → JSON { geocode_queued: false, latitude, longitude } → loadMap() → 즉시 마커
```

### get_rq_queue() (queue.py)

- `REDIS_URL` 없음 → `None` 반환 → `enqueue_geocode_order_address` → `False`
- `REDIS_URL` 있음 → Queue 반환 → enqueue 시도 → 성공 시 `True`

### applyAddressEdit → loadMap 흐름 (map_view.html)

1. `applyAddressEdit()`: `POST /api/orders/<id>/update_address` 호출
2. 성공 시:
   - `data.geocode_queued === true` → `order.geocode_failed = true`, `conversion_status = 'pending'`
   - `data.geocode_queued === false` → `order.geocode_failed`, `conversion_status`를 응답 기준으로 설정
3. `loadMap()` 호출 (인자 없음)
4. `loadMap()`: `GET /api/generate_map` 호출 → `currentOrders` 갱신
5. `hasPending`이면 15초 후 `loadMap(true)` 폴링 시작
6. 폴링: `GET /api/map_data` → `resolvedPending`이면 `loadMap()` 전체 재로드

### api_map_data vs api_generate_map

| API | enqueue_missing | orders 구조 |
|-----|-----------------|-------------|
| /api/map_data | False | `geocode_failed`, `conversion_status` 포함 |
| /api/generate_map | True | 동일 구조 |

둘 다 `_build_map_payload` 사용, `orders` 배열 구조 동일. `dashboard` 파라미터도 둘 다 전달됨.

---

## Step 3: Production 실제 흐름 가설

### 가설 A: RQ 사용 + Worker Offline (가장 유력)

- Web에 `REDIS_URL` 설정 → enqueue 성공
- Worker 서비스 Offline 또는 미배포 → Job 큐에만 쌓이고 처리 안 됨
- 폴링 시 `conversion_status`가 계속 `pending` → `resolvedPending` 미충족
- 5회×15초 후 폴링 종료 → 마커 미표시

### 가설 B: RQ 미사용 + 동기 폴백

- Web에 `REDIS_URL` 없음 → enqueue 실패 → 동기 폴백
- `geocode_order_address()` 실행 후 `order` 재조회 (로컬 수정 반영)
- 이 경로라면 마커가 표시되어야 함 → **Production에서도 미표시면 다른 원인**

### 가설 C: api_map_data / api_generate_map 응답 불일치

- 코드상 두 API 모두 `geocode_failed`, `conversion_status` 반환
- 구조 불일치 가능성은 낮음

### 가설 D: 배포 코드 미반영

- 빌드 캐시, 배포 실패 등으로 최신 코드 미적용
- Railway Deploy 로그에서 빌드·시작 명령 확인 필요

---

## Step 4: 검증 포인트

### 4.1 Railway 대시보드 확인

1. **FOMS Web 서비스**
   - Variables: `REDIS_URL` 존재 여부
   - Variables: `USE_RQ_WORKER` (0 또는 미설정 권장)

2. **Worker 서비스**
   - 상태: Online 여부
   - Variables: `REDIS_URL` (Web과 동일)
   - Variables: `USE_RQ_WORKER=1`
   - Deploy 로그: `rq worker default --url ...` 실행 확인

### 4.2 API 응답 검증

**동기 폴백 시** (`geocode_queued: false`):

```json
{
  "success": true,
  "address": "...",
  "geocode_queued": false,
  "latitude": 37.xxx,
  "longitude": 127.xxx,
  "conversion_status": "success",
  "geocode_failed": false
}
```

**RQ 경로 시** (`geocode_queued: true`):

```json
{
  "success": true,
  "address": "...",
  "geocode_queued": true,
  "latitude": null,
  "longitude": null,
  "conversion_status": "pending",
  "geocode_failed": true
}
```

Production에서 주소 수정 후 위 둘 중 어떤 응답이 오는지 확인.

### 4.3 폴링 로직

- `pendingBefore`: `geocode_failed && conversion_status === 'pending'`인 order id 집합
- `resolvedPending`: `pendingBefore`에 있던 order가 `!geocode_failed`가 되었는지
- Worker가 정상 처리하면 `api_map_data` 응답에서 해당 order의 `geocode_failed`가 `false`로 바뀌어야 함

---

## Step 5: 수정안 도출 (Root Cause Fix Only)

### 시나리오 1: Worker Offline (가설 A)

**조치**: Worker 서비스를 Online으로 전환

1. Railway Worker 서비스 생성/확인
2. `railway-worker.toml` 또는 Procfile worker 사용
3. `REDIS_URL` 설정 (Web과 동일 Redis)
4. Deploy 로그에서 `rq worker` 기동 확인

**임시 대안** (Worker 복구 전): Web 서비스에서 `REDIS_URL` 제거 → 동기 폴백만 사용  
※ Socket.IO 등 Redis 사용 기능이 있으면 Redis는 유지하고, Worker만 복구하는 것이 바람직함.

### 시나리오 2: 동기 폴백인데도 마커 미표시 (가설 B)

**가능 원인**:

- Production에서 geocode API 실패 (할당량, 네트워크 등)
- `db_session.remove()` 후 세션/재조회 이슈 (다른 환경 차이)

**조치**:

1. Production 로그에서 `Fallback geocode error:` 메시지 확인
2. `api_update_order_address`에 디버그 로그 추가 (geocode 성공/실패, 반환 lat/lng)
3. 브라우저 개발자 도구에서 `update_address` 응답의 `latitude`, `longitude` 확인

### 시나리오 3: 배포 코드 미반영 (가설 D)

**조치**:

1. Railway에서 수동 Redeploy (캐시 무시)
2. Deploy 로그에서 `start.sh` 및 gunicorn 실행 확인
3. 필요 시 `railway.toml` / Dockerfile의 CMD 검토

---

## 권장 조치 순서

1. **즉시**: Railway 대시보드에서 Worker 서비스 상태 확인
2. **즉시**: Production에서 주소 수정 후 `update_address` API 응답 확인 (`geocode_queued` 값)
3. **Worker Offline이면**: Worker 기동 또는 Web에서 `REDIS_URL` 제거(임시)
4. **Worker Online인데도 실패하면**: Production 로그·API 응답 기반 추가 진단

---

## Step 6: 4대 증상 Root Cause Fix (2026-03-15 적용)

### 증상 1: SyntaxError at line 5:42

**근본 원인**: 템플릿에 리터럴 `\'` 및 `\n`이 포함되어 JS 파서가 `\'undefined\'`를 잘못 해석.

**수정**: `map_view.html` head 스크립트에서 `\'` → `'`, `\n` → 실제 줄바꿈으로 변경.

### 증상 1 보조: openAddressEdit 주소 문자열 끊김

**근본 원인**: `openAddressEdit(${order.id}, '${escapeHtml(order.address)}')` — `escapeHtml`은 HTML 이스케이프만 수행. 주소에 `'` 포함 시 JS 문자열 끊김 → SyntaxError.

**수정**: `escapeForJsString()` 추가, onclick에서 `escapeForJsString(order.address)` 사용.

### 증상 2: geocode 실패 건 정상 표시

**분석**: `_build_map_payload`는 `lat is None or lng is None`일 때 `geocode_failed: true` 반환. API 응답 구조는 정상. 프론트 `isOrderGeocodeFailed`도 `geocode_failed === true` 또는 `conversion_status === 'failed'|'pending'`으로 판별. 코드상 결함 없음.

**가능 원인**: (1) DB에 `geocode_status` 미설정 구주문, (2) Worker 미처리로 `pending` 유지. 백엔드 로직은 `stored_geocode_status or 'failed'`로 폴백하므로 정상.

### 증상 3: 주소 수정 후 잠시 분홍색

**의도된 동작**: `geocode_queued` 시 `order.geocode_failed = true`, `conversion_status = 'pending'` 설정. Worker 완료 전까지 분홍색 표시는 정상.

### 증상 4: 주소 수정 후 지도 미표시

**근본 원인**: RQ Worker 미기동 또는 Redis 미연결 시 Job이 처리되지 않아 `lat/lng`가 갱신되지 않음. Step 1~5 환경 점검 필요.

**검증**: Production에서 `update_address` 응답의 `geocode_queued` 값 확인. Worker Online 여부 확인.

---

## 참조 파일

- `apps/api/erp_map.py`: api_update_order_address, api_map_data, api_generate_map
- `services/jobs/queue.py`: enqueue_geocode_order_address, get_rq_queue
- `services/jobs/tasks.py`: geocode_order_address
- `templates/map_view.html`: applyAddressEdit, loadMap, 폴링
- `start.sh`, `Procfile`, `Dockerfile`, `railway.toml`
- `docs/incidents/2026-02-22-railway-worker-map-utils.md`
