# FOMS Production 확장성 분석 보고서

**작성일**: 2026-02-20  
**대상**: 다중 사용자 무지연 운영 상세 계획서 (Railway 기준)  
**분석 주체**: Grand Develop Master (GDM)

---

## 1. 요약 결론

| 항목 | 평가 | 비고 |
|------|------|------|
| **계획서 적합성** | ✅ **전반적으로 FOMS에 맞음** | SLO·단계·롤백 방안이 현실적 |
| **즉시 적용 권장** | 2단계(웹 확장) + 3단계(DB/Redis 튜닝) | 현재 구조로 1~2일 내 가능 |
| **핵심 전환 필요** | 5단계(지도 선계산) + 6단계(Direct Upload) | 코드 변경 큼, 효과도 큼 |
| **현재 병목** | 지도 API 실시간 지오코딩, 앱 서버 경유 업로드 | 계획서 진단과 일치 |

---

## 2. 현재 FOMS 아키텍처 현황

### 2.1 Railway 배포 구성

| 구성요소 | 현재 | 계획서 권장 |
|----------|------|-------------|
| Web Replica | **1개** (추정) | 2개 이상 |
| Gunicorn 워커 | `-k gevent -w 1` (단일) | gevent 2워커/Replica |
| Worker 서비스 | **없음** | 별도 worker 서비스 |
| Redis | Socket.IO + Rate Limit | Socket.IO + Job Queue |
| Postgres | 1개 | 풀 튜닝 필요 |

**현재 설정 출처:**
- `railway.toml`: `gunicorn -k gevent -w 1 --timeout 120`
- `Procfile`: 동일

### 2.2 지도 API (5단계 핵심)

| 항목 | 현재 FOMS | 계획서 권장 |
|------|-----------|-------------|
| 지오코딩 시점 | **요청 시 실시간** (Kakao API) | 주소 변경 시 선계산 |
| lat/lng 저장 | **Order 테이블에 없음** | 별도 컬럼 또는 테이블 저장 |
| 캐시 | 프로세스 인메모리 LRU (`_geocode_cache`) | DB 저장 + Job enqueue |
| 경로 API | Kakao Directions 실시간 호출 | (start,end) 단기 캐시 |

**영향:** 지도 40명 동시 사용 시 Kakao API 호출 폭증 → 타임아웃·5xx 증가 가능성 큼.

### 2.3 파일 업로드 (6단계 핵심)

| 항목 | 현재 FOMS | 계획서 권장 |
|------|-----------|-------------|
| 업로드 경로 | **앱 서버 경유** (Flask → storage → R2) | Presigned URL → 클라이언트 직접 R2 |
| MAX_CONTENT_LENGTH | 500MB | N/A (앱 서버 미경유) |
| 처리 방식 | 동기 (업로드 완료까지 블로킹) | 세션 발급/완료 확인만 |

**영향:** 20건 × 50~500MB 동시 업로드 시 웹 CPU/메모리 부하 극대화.

### 2.4 DB / Redis / Socket.IO

| 항목 | 현재 | 계획서 |
|------|------|--------|
| DB 풀 | pool_size=20, max_overflow=20 (고정) | 환경변수 기반 조정 |
| Redis | REDIS_URL (Socket.IO, rate_limit) | health_check, retry 정책 보강 |
| Socket.IO | gevent + Redis MQ | websocket-only, 폴링 fallback 비활성 |
| 폴링 fallback | `SOCKETIO_ALLOW_POLLING_FALLBACK` (기본 false) | 동일 |

### 2.5 비동기 워커

| 항목 | 현재 FOMS | 계획서 |
|------|-----------|--------|
| 별도 worker | **없음** | Redis Queue 소비 전용 서비스 |
| 썸네일/후처리 | storage 내부 동기 | Job enqueue → worker 처리 |
| 지오코딩 | API 요청 시 동기 | Job enqueue (5단계와 연동) |

---

## 3. 단계별 계획서 vs FOMS 적합성

### 1단계: 기준선 측정 및 경보 체계 (D+1)

| 계획서 요구 | FOMS 현황 | 적합성 |
|-------------|-----------|--------|
| endpoint, duration_ms, status 로그 | 부분적 (일부 API에만) | 🟡 로깅 강화 필요 |
| p95/p99 대시보드 | 없음 | 🟡 신규 구축 |
| Redis/DB 연결 수 알람 | Railway 기본 모니터링 | 🟢 기본만 있으면 단순 알람 추가 |
| Gunicorn 재시작 알람 | Railway 로그 기반 | 🟢 가능 |
| 큐 적체량 | worker 없어 해당 없음 | - |

**결론:** 1단계는 계획서 그대로 적용. 로깅·메트릭 구축부터 선행 권장.

---

### 2단계: Railway 웹 계층 확장 (D+1)

| 계획서 요구 | FOMS 적용 시 | 적합성 |
|-------------|--------------|--------|
| Web Replica 2개 | Railway 대시보드에서 스케일 조정 | ✅ 즉시 적용 가능 |
| gevent 2워커 | `-w 2` 로 변경 | ⚠️ **주의**: Socket.IO sticky session |
| websocket-only, 폴링 비활성 | `SOCKETIO_ALLOW_POLLING_FALLBACK` 이미 false | ✅ 준비됨 |

**FOMS 특이사항:**
- Socket.IO + Redis MQ 사용 중 → **다중 Replica/다중 워커 시 sticky session 불필요** (Redis가 메시지 브로드캐스트)
- `ConcurrentObjectUseError` 이슈는 gevent 단일 모드로 해결된 상태 (app.py 주석 참조)
- **권장:** Replica 2개 + 워커는 1개 유지 후 부하 테스트으로 2개 검증

---

### 3단계: DB/Redis 연결 튜닝 (D+1)

| 계획서 요구 | FOMS 현황 | 적용 방안 |
|-------------|-----------|-----------|
| SQLAlchemy 풀 환경변수화 | db.py 하드코딩 (20/20) | `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` 도입 |
| Postgres 플랜 한도 60~70% | Railway Postgres 플랜 확인 필요 | 연결 상한 계산 후 적용 |
| Redis health_check, timeout, retry | `_augment_redis_url_for_socketio`에 이미 일부 반영 | 정책 문서화·표준화 |

**결론:** db.py 수정으로 풀 설정 환경변수화 즉시 가능. Railway Postgres 플랜에 맞춰 수치 조정.

---

### 4단계: 비동기 워커 서비스 분리 (D+2~3)

| 계획서 분리 대상 | FOMS 해당 기능 | 우선순위 |
|------------------|----------------|----------|
| 이미지/파일 썸네일 | storage.generate_thumbnail (chat 등) | 높음 |
| 대용량 파일 후처리 | 현재 없음 (동기 업로드만) | - |
| 지오코딩 | 5단계와 통합 설계 | 필수 |

**결론:** Worker 서비스 분리는 5단계(지도 선계산)와 함께 설계하는 것이 효율적. RQ 또는 Celery + Redis 조합 권장.

---

### 5단계: 지도 아키텍처 전환 (D+3~5)

| 계획서 요구 | FOMS 적용 | 난이도 |
|-------------|-----------|--------|
| lat/lng/geocode_status/geocoded_at 저장 | Order 또는 site 테이블 확장 | 중 |
| 주소 생성/수정 시 Job enqueue | order 생성/수정 API 훅 | 중 |
| 지도 API 외부 지오코딩 금지 | api_map_data, generate_map 등 수정 | 중 |
| 경로 API (start,end) 캐시 | calculate_route Redis 캐시 | 하 |

**FOMS 현재 구조:**
- Order.structured_data (JSONB) 내 `site.address_full` 등에 주소 저장
- `api_map_data`: 매 요청마다 `convert_address_cached()` → Kakao API
- `Order` 모델에 latitude, longitude 컬럼 **없음**

**권장 마이그레이션:**
1. Order에 `latitude`, `longitude`, `geocode_status`, `geocoded_at`, `address_hash` 추가 (또는 site 정규화)
2. 주소 변경 시점(order 생성/수정/update_address)에 지오코딩 Job enqueue
3. 지도 API는 DB 좌표만 반환 (없으면 "geocode_pending" 등 표시)
4. Worker에서 Job 처리 후 Order 업데이트

---

### 6단계: 파일 업로드 경로 최적화 (D+2~4)

| 계획서 요구 | FOMS 적용 | 난이도 |
|-------------|-----------|--------|
| Presigned URL direct-to-R2 | 신규 API: 업로드 세션 발급 | 중 |
| 앱 서버는 세션 발급/완료 확인만 | 기존 upload 라우트 대체 또는 병행 | 중 |
| 다운로드 서명 URL redirect | files.py에 이미 부분 구현 | 🟢 유지 |

**현재 upload 진입점:**
- `apps/api/attachments.py` (order attachments)
- `apps/api/chat/routes.py` (chat upload)
- `apps/api/erp_orders_drawing.py` (drawing gateway)
- `apps/api/erp_orders_blueprint.py` (blueprint upload)
- `excel_import.py` (엑셀 업로드)

**권장:** 대용량 대상(attachments, drawing, blueprint)부터 Presigned URL 플로우 도입. chat/엑셀은 소용량이라 후순위 가능.

---

### 7단계: 부하 테스트 및 컷오버 (D+2)

계획서 시나리오·통과 기준 그대로 적용. locust 또는 k6 스크립트 작성 권장.

---

## 4. 우선순위 권장 (FOMS 맞춤)

| 순서 | 단계 | 이유 | 예상 소요 |
|------|------|------|-----------|
| 1 | **2 + 3** (웹 확장 + DB/Redis 튜닝) | 즉시 효과, 코드 변경 최소 | 1~2일 |
| 2 | **1** (기준선 측정) | 개선 전/후 비교용, 병행 가능 | 1일 |
| 3 | **4** (비동기 워커) | 5단계와 설계 연계 권장 | 2~3일 |
| 4 | **5** (지도 선계산) | 동시 40명 SLO 핵심 | 3~5일 |
| 5 | **6** (Direct Upload) | 대용량 업로드 SLO 핵심 | 2~4일 |
| 6 | **7** (부하 테스트) | 각 단계 후 점진 검증 | 1~2일 |

---

## 5. 운영 체크리스트 (계획서 대비 FOMS 검증)

| 항목 | 상태 | 비고 |
|------|------|------|
| Socket.IO 폴링 fallback 비활성 | ✅ | `SOCKETIO_ALLOW_POLLING_FALLBACK` 기본 false |
| DB 최대 연결 수와 앱 풀 계산표 | 🟡 | 환경변수화 후 문서화 필요 |
| 큐 적체 알람/재시도 정책 | 🟡 | Worker 도입 후 설정 |
| 지도 API 실시간 외부 지오코딩 금지 | ❌ | **현재 실시간 호출 중** → 5단계 필수 |
| 대용량 업로드 앱 서버 미경유 | ❌ | **현재 앱 경유** → 6단계 필수 |

---

## 6. 롤백 계획 (계획서 준용)

| 상황 | 조치 |
|------|------|
| Replica/워커 수만 원복 | Railway 대시보드 즉시 조정 (코드 롤백 불필요) |
| 비동기 큐 장애 | 해당 기능만 일시 동기 처리 fallback 토글 |
| 지도 전환 장애 | 기존 API로 전환 + 요청 상한(limit) 강제 |
| Direct Upload 장애 | 기존 업로드 라우트로 fallback |

---

## 7. 결론 및 다음 액션

**계획서는 FOMS Production 환경에 적용 가능하며, 진단 방향이 현재 구조와 잘 맞습니다.**

**즉시 착수 권장:**
1. **2단계**: Railway Web Replica 2개, Gunicorn 워커는 1→2 전환 시 부하 테스트으로 검증
2. **3단계**: `db.py` 풀 설정 환경변수화 (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`)
3. **1단계**: 요청 duration_ms 로깅 추가 (Flask `before_request`/`after_request` 또는 미들웨어)

**중기 필수:**
4. **5단계**: 지도 "요청 시 지오코딩" → "주소 변경 시 선계산" 전환
5. **6단계**: 대용량 업로드 Presigned URL direct-to-R2 전환
6. **4단계**: Worker 서비스 (지오코딩·썸네일 등) 분리

이 분석서는 `docs/context/DECISIONS.md`에 참조로 기록하고, 실행 시 `TASK_REGISTRY.md`에 작업 단위를 등록할 것을 권장합니다.
