# 2026-02-22 원격(Railway) 주소변환(지도 표시) 실패 진단

> **증상**: 원격(lahom-dev.up.railway.app) 지도 페이지에서 모든 주문에 "▲ 주소오류" 표시, 지도에 마커 없음  
> **확인 일시**: 2026-02-22  
> **관련 문서**: `2026-02-22-railway-worker-map-utils.md`, `2026-02-22-map-geocode-not-running.md`

---

## 1. 증상 요약

| 항목 | 내용 |
|------|------|
| 화면 | `/map_view?date=2026-02-23&status=MEASURED` |
| 상태 | 모든 주문 카드에 "▲ 주소오류", 지도에 마커 0개 |
| 원인 추정 | geocode job이 큐에 들어가지 않거나, Worker가 처리하지 못함 |

---

## 2. 코드 흐름 (검증됨)

### 2.1 지도 로드 시

1. 사용자가 지도 페이지 로드 → `loadMap()` 호출  
2. `GET /api/generate_map?date=...&status=...` 요청  
3. `api_generate_map` (apps/api/erp_map.py 232행~) 실행  
   - lat/lng 없고 주소 있는 주문마다 `enqueue_geocode_order_address(order.id)` 호출 (396~406행)  
   - `enqueue` 성공 시 `geocode_status = 'pending'` 저장 후 응답  
4. `enqueue_geocode_order_address` (services/jobs/queue.py)  
   - `get_rq_queue()` → `REDIS_URL` 없으면 **None** 반환  
   - 큐 없으면 **False** 반환 → job 미등록  
5. Worker가 job을 처리 → `geocode_order_address` (services/jobs/tasks.py)  
   - 카카오 API로 주소→좌표 변환 후 Order.lat/lng/geocode_status 갱신  
6. 새로고침 시 저장된 좌표로 마커 표시

### 2.2 실패 지점 후보

| 순번 | 지점 | 조건 | 결과 |
|------|------|------|------|
| A | FOMS 웹 `REDIS_URL` 없음 | get_rq_queue() → None | enqueue False → job 미등록 |
| B | Worker Offline | job은 큐에 들어감 | job 처리 안 됨 → 좌표 미저장 |
| C | Web/Worker Redis 분리 | 서로 다른 REDIS_URL | Web은 enqueue, Worker는 다른 Redis 청취 |
| D | Worker `DATABASE_URL` 없음 | DB 연결 실패 | geocode job 실행 중 예외 |
| E | Worker `KAKAO_REST_API_KEY` 없음 | map_config 하드코딩 사용 | 로컬 테스트 기준 동작 (다만 env 우선 권장) |

---

## 3. Railway 설정 점검 체크리스트

### 3.1 FOMS 웹 서비스 (2699f644...)

| 항목 | 확인 | 요구값 |
|------|------|--------|
| REDIS_URL | Variables 탭 | **있어야 함** (Redis 서비스에서 참조) |
| USE_RQ_WORKER | Variables 탭 | **0** 또는 미설정 (gunicorn 실행) |
| DATABASE_URL | Variables 탭 | 있음 (기본) |

- REDIS_URL 없으면 `get_rq_queue()` → None → enqueue 불가 → **지도 변환 전체 실패**

### 3.2 Worker 서비스 (847f6c7c...)

| 항목 | 확인 | 요구값 |
|------|------|--------|
| 상태 | Deployments / Overview | **Online** |
| USE_RQ_WORKER | Variables 탭 | **1** |
| REDIS_URL | Variables 탭 | **FOMS 웹과 동일한 값** |
| DATABASE_URL | Variables 탭 | **있어야 함** (Order 갱신용) |
| Config Path | Settings | `railway-worker.toml` (또는 Procfile worker) |
| Start Command | Deploy 로그 | `rq worker default --url $REDIS_URL` |

- Worker Offline이면 큐에 쌓인 job을 처리할 프로세스 없음 → 좌표 미저장  
- REDIS_URL이 Web과 다르면 Web이 넣은 job을 Worker가 받지 못함

### 3.3 Redis 서비스

| 항목 | 확인 |
|------|------|
| REDIS_URL | Web·Worker 모두 이 서비스의 URL을 참조하는지 확인 |
| 연결 | Railway 대시보드에서 Redis 상태 정상 여부 확인 |

---

## 4. 로그로 확인하는 방법

### 4.1 FOMS 웹 로그 (배포 후)

- `[RQ] get_queue failed: ...` → REDIS_URL 없음 또는 Redis 연결 실패  
- `[RQ] enqueue_geocode_order_address error: ...` → enqueue 시점 예외  

### 4.2 Worker 로그

- `Listening on default...` → RQ worker 정상 기동  
- `[RQ] geocode_order_address error: ...` → job 실행 중 예외 (DB/Kakao API 등)  

---

## 5. 권장 조치 순서

1. **FOMS 웹 Variables**: REDIS_URL 존재 여부 확인, 없으면 Redis 서비스 참조 추가  
2. **Worker 상태**: Online 여부 확인, Offline이면 Settings(Config Path, Variables) 점검 후 재배포  
3. **REDIS_URL 일치**: Web과 Worker가 동일한 REDIS_URL 값을 쓰는지 확인  
4. **Worker DATABASE_URL**: Order 갱신을 위해 필요, Variables에 설정되어 있는지 확인  
5. **지도 재확인**: 설정 반영 후 지도 페이지 새로고침 → 좌표 없는 주문 있으면 수 초 후 재새로고침 → 마커 표시 여부 확인  

---

## 6. UX 개선: 자동 갱신 (2026-02-22)

**문제**: 처음 열면 주소변환이 안 되다가, 시간이 지나 수동 새로고침을 해야 정상 표시됨. Worker가 geocode를 순차 처리(~4.5초/건)하여 8건이면 ~36초 소요.

**조치**: `templates/map_view.html`에서 `conversion_status='pending'` 주문이 있으면 **6초 간격 자동 폴링**(최대 10회)을 수행하여, 사용자가 직접 새로고침할 필요 없이 화면이 갱신되도록 변경.

- 배너: "주소 변환 중... 6초 후 자동 갱신 (N/10)"
- 자동 갱신 시에는 로딩 오버레이를 표시하지 않아 깜빡임 최소화

---

## 7. 참조

- `docs/incidents/2026-02-22-railway-worker-map-utils.md` – queue.py 수정 및 Variables 정리  
- `railway-worker.toml` – Worker Start Command  
- `services/jobs/queue.py` – get_rq_queue, enqueue_geocode_order_address  
- `services/jobs/tasks.py` – geocode_order_address  
- `apps/api/erp_map.py` – api_generate_map (lazy geocode enqueue 396~406행)
