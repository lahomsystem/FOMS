# 네이버 커머스 연동 아키텍처 지도 — 정산 파이프라인 설계용 (2026-09-02)

## 결론 요약 (10줄)

1. **인증**: `NaverCommerceClient` (`foms/services/integrations/naver_commerce/client.py:279`) — bcrypt 서명(`build_signature`, client.py:179) + 토큰 캐시(Redis 우선/메모리 폴백, `default_token_cache`, client.py:165) + TTL은 `expires_in`에서 갱신 마진(300초)을 뺀 값(client.py:348). 캐시 없이 매 호출 재발급 안 함.
2. **제네릭 GET 없음**: 공개 헬퍼는 없고 엔드포인트마다 전용 public 메서드(`get_last_changed_statuses`, `get_product_orders` 등)가 내부 공통 헬퍼 `self._request(method, path, params=..., json_body=...)` (client.py:786)를 호출하는 구조. `_request`는 이미 재시도·백오프·401 복구·rate-limit 로깅을 다 갖춘 **사실상의 제네릭 GET**이라, 정산 API도 같은 패턴(전용 public 메서드 + `_request` 재사용)으로 붙이면 된다.
3. **워커 단일 출구 — 확정, 반례 없음**: web 코드는 `foms/services/jobs/queue.py`의 `enqueue_naver_*` 함수로 rq에 넣기만 하고(예: `enqueue_naver_order_sync`, queue.py:456), 실제 `NaverCommerceClient()` 인스턴스화·HTTP 호출은 `foms/services/jobs/tasks.py`(워커 프로세스, 예: tasks.py:396)와 `scripts/maintenance/run_naver_*.py`(start.sh가 기동)에서만 일어난다. web에서 web 프로세스가 직접 네이버를 호출하는 코드 경로는 저장소 전체에 없음(IP 화이트리스트 3=3 제약, client.py 헤더 주석).
4. **계정**: 스토어는 **라홈 하나**(`DEFAULT_ORDERER_NAME = "라홈"`, constants.py:49). 하우드는 별개 발주사(비네이버 주문용)이지 두 번째 네이버 스토어가 아님. `accounts.py`는 네이버 스토어 계정이 아니라 **FOMS 내부 시스템 사용자**(수집봇·미배정 owner) 관리 모듈. → 정산 API도 단일 계정·단일 client_id/secret으로 충분.
5. **자격증명**: env `NAVER_COMMERCE_CLIENT_ID` / `NAVER_COMMERCE_CLIENT_SECRET`만 존재(client.py:310-313). 값은 절대 로그·리포트에 남기지 않음(본 문서도 값 미기재).
6. **영속화 패턴**: 원본 스냅샷은 `ExternalOrderLink.raw_snapshot`(JSONB, models.py:3533)에 그대로 저장 + 필터 전용 사본 컬럼(부분 인덱스) 병행. 마이그레이션명 컨벤션 `<slug>_00_<설명>.py`, revision id = 파일 slug(예: `naver_link_00`). alembic 단일 head 게이트(`tests/domains/test_alembic_single_head.py`) 존재, 현재 HEAD = `wizsend_00`.
7. **워터마크/백필 재사용 가능**: `watermark.py`(SystemSetting 행 1개, 성공 구간만 전진) + `backfill.py`(90일 상한, 하루 창씩 순회, 별도 SystemSetting 키) 패턴은 정산 일별 동기화에 그대로 재사용 가능한 설계.
8. **스케줄링 2종 패턴 존재**: (a) interval 루프(`run_naver_order_sync.py --loop --interval`), (b) 하루 1회 시각 창(`run_naver_auto_dispatch.py --loop --at 16:50 --window 10`, DB로 "오늘 이미 실행" 멱등 보장). 정산은 (b) 쪽이 자연스러움(전일 마감 데이터라 하루 1회 조회).
9. **테스트 규율**: 토큰 캐싱 클라이언트는 `tests/contracts/test_external_token_client_discipline.py`에 등재 필수(R1: expires_in 기반 TTL, R2: 401 재발급 1회). 정산이 **같은 client.py 파일**에 메서드를 추가하면 등재는 이미 돼 있어 추가 작업 불필요 — 별도 클라이언트 파일을 새로 만들면 그때 등재해야 함.
10. **화면**: 기존 정산 대시보드 스펙(`docs/specs/2026-08-31-settlement-dashboard_SPEC.md:318-319`)이 "채널 수수료 대사"·"반품 환불액 동기화"를 **v1 비목표, 후속 스펙 필요**로 명시적으로 남겨둠 — 이번 작업이 그 후속. `structured_data.naver.payment.expected_settlement_amount`(mapping.py:1074)는 주문 상세의 **예정 정산액 추정치**일 뿐 실제 정산 API 데이터가 아님(용도 다름, 혼동 금지).

---

## 1. `client.py` — 인증·전송·페이징

### 1.1 인증 (client.py:179-373)

- **서명**: `build_signature(client_id, client_secret, timestamp_ms)` (client.py:179). `client_secret` 자체가 bcrypt salt이고 `bcrypt.hashpw(f"{client_id}_{timestamp_ms}".encode(), client_secret.encode())`를 base64 인코딩(client.py:207-209). secret이 `$2`로 시작하지 않으면 `NaverCommerceConfigError`로 즉시 실패(client.py:201-206) — PowerShell 큰따옴표가 `$2a`를 변수 치환하는 사고를 막기 위한 방어.
- **토큰 발급**: `_issue_token()` (client.py:352-373)이 `POST /v1/oauth2/token`을 form-urlencoded로 호출, `grant_type=client_credentials, type=SELF`. 응답에 `access_token` 없으면 `NaverCommerceAuthError`.
- **토큰 캐시**: `get_access_token(force_refresh=False)` (client.py:330-350). 캐시 히트면 재발급 안 함. TTL = `max(60, expires_in - TOKEN_REFRESH_MARGIN_SECONDS)`(300초 마진, client.py:53, 348). 실측 `expires_in`=10799초(3시간)(client.py:10 docstring).
- **캐시 저장소**: `TokenCache` Protocol(client.py:101) → `RedisTokenCache`(client.py:137, REDIS_URL 있을 때, 모든 Redis 예외를 캐시 미스로 강등 = fail-open) 또는 `MemoryTokenCache`(client.py:111, 폴백). `default_token_cache()`(client.py:165)가 자동 선택. 캐시 키는 `client_id`를 SHA256 해시해 원문을 Redis에 남기지 않음(client.py:326-328, `foms:naver_commerce:token:<16자>`).
- **401 복구**: `_request` 내부에서 401 + `authenticated=True` + 아직 재시도 안 했으면 `get_access_token(force_refresh=True)` 후 **1회만** 재시도(client.py:835-839). 재시도 소진 로직과는 분리된 카운터(`token_retried`).

### 1.2 베이스 URL·상수

- `BASE_URL = "https://api.commerce.naver.com/external"` (client.py:34).
- `MAX_WINDOW = 23시간59분` — 변경분 조회 구간 상한(client.py:39, API 24h 제약에 1분 여유).
- `DETAIL_BATCH_SIZE = 100` (client.py:42, 문서 상한 300보다 보수적).
- `LAST_CHANGED_LIMIT = 300`, `LAST_CHANGED_MAX_PAGES = 50` (client.py:46-50).
- `RETRYABLE_STATUS = {429, 500, 502, 503, 504}` (client.py:56).
- `DEFAULT_TIMEOUT_SECONDS = 30`, `DEFAULT_MAX_RETRIES = 3`, 지수 백오프 base 1.0s/cap 30.0s (client.py:72-76).
- Rate limit 헤더(2 RPS 고정, 앱당·API당): `GNCP-GW-RateLimit-Replenish-Rate` / `-Remaining` / `-Burst-Capacity` (client.py:65-67) — **관측 전용**, 호출 동작을 바꾸지 않고 로그만 남김(`_log_rate_limit`, client.py:848-882). 429거나 남은 호출 ≤1이면 warning, 아니면 debug.

### 1.3 요청 헬퍼 — "사실상의 제네릭 GET"

`_request(method, path, *, params=None, data=None, json_body=None, headers=None, authenticated=True, retry=True)` (client.py:786-846)가 전체 클라이언트의 유일한 HTTP 진입점:

- 429/5xx/네트워크 예외 → 지수 백오프 재시도(최대 `max_retries`).
- 401 → 토큰 강제 재발급 1회.
- `retry=False` 옵션 — **불가역 클레임 호출 전용**(취소/반품 승인·거부). 타임아웃이 "안 나갔다"를 의미하지 않기 때문에 맹목 재전송 금지(client.py:795-802).
- 2xx → `_parse_json`으로 dict 반환. 그 외 → `NaverCommerceHTTPError(status, body, url)`.

**공개된 제네릭 `get(path, params)` 메서드는 없다.** 대신 각 엔드포인트가 얇은 public 메서드로 `_request`를 감싼다:
- `get_last_changed_statuses(start, end)` (client.py:377) — GET, 페이징 내장.
- `get_product_orders(product_order_ids)` (client.py:447) — POST(배치 조회), `DETAIL_BATCH_SIZE`로 자동 분할.
- 쓰기 계열(`confirm_place_orders`, `dispatch_product_orders`, `request_cancel_product_order` 등, client.py:472-774) — 전부 같은 `_request` 재사용.

**정산 API 5종에 대한 권장 패턴**: 새 public 메서드(`get_settle_case`, `get_settle_daily`, `get_settle_commission_details`, `get_vat_case`, `get_vat_daily`)를 `client.py`에 추가하고 내부에서 `self._request("GET", "/v1/pay-settle/...", params=params)` 호출. 기존 컨벤션과 일치하며, 토큰 캐시·재시도·rate-limit 로깅을 공짜로 얻는다. 별도 클라이언트 클래스나 파일을 새로 만들 필요 없음(§6의 토큰 규율 계약도 그대로 유지됨).

### 1.4 페이징 패턴 (재사용 대상)

- **시간창 분할**: `iter_time_windows(start, end, max_window=MAX_WINDOW)` (client.py:212-233) — 구간을 API 상한 이하 조각으로 잘라 제너레이터로 순회. `backfill.py:219`에서 하루 단위 백필에 그대로 재사용됨. 정산 daily API도 조회 상한(문서 확인 필요)이 있다면 이 함수를 그대로 쓸 수 있음.
- **`more` 이어받기**: `_changed_window` (client.py:400-445)가 응답의 `data.more.moreFrom`/`moreSequence`를 다음 요청 파라미터에 실어 페이지를 이어받는다. 진척 없는 `more`(빈 chunk)는 멈추고(client.py:430-433), 쪽수 상한(`LAST_CHANGED_MAX_PAGES`) 도달 시 경고 로그(client.py:441-444, for-else). 정산 case/daily API도 페이지네이션이 있다면 같은 골격(paginate-until-no-more, 상한 가드, 진척 없음 가드) 재사용 권장.

---

## 2. 계정·설정 — `accounts.py` / `constants.py` / env

### 2.1 계정 구조 — **단일 스토어**

- `foms/services/integrations/naver_commerce/constants.py:49` — `DEFAULT_ORDERER_NAME = "라홈"`, 주석: "네이버 스마트스토어가 라홈 스토어라 발주사는 항상 라홈이다."
- `CHANNEL = "NAVER"` (constants.py:12) — v1은 네이버 하나뿐(주석: "채널 확장을 막지 않는다"이지만 실제 다중 채널 구현은 없음).
- 하우드(HAWOOD) 언급은 `mapping.py:14-15,1100`, `bulk_dispatch.py:980`에 있으나 **비네이버 발주사**(ERP 직접 접수 건의 발주처 구분) 문맥. 두 번째 네이버 스토어 계정이 아님 — `grep "store_id\|storeId\|STORE_ID"` 결과 0건(naver_commerce 디렉토리 전체).
- **결론**: 정산 API도 단일 client_id/secret로 전 계정 데이터를 조회하면 된다. per-account 반복 호출 설계는 불필요.

### 2.2 `accounts.py`의 실체 — FOMS 내부 사용자 계정 (스토어 계정 아님)

`foms/services/integrations/naver_commerce/accounts.py`는 네이버 자격증명이 아니라 **FOMS `User` 테이블의 시스템 계정 2개**를 관리한다(accounts.py:29-45):
- `naver_ingest_bot` (ACTOR_USERNAME, constants.py:34) — 수집 이벤트의 author.
- `naver_unassigned` (OWNER_USERNAME, constants.py:38) — 미배정 보류함 owner(활성 SALES 계약 충족용).

로그인 잠금은 `is_active=False`가 아니라 아무도 모르는 난수 비밀번호 해시로(accounts.py:48-50) — owner 계약(`create_order`가 활성 SALES 요구)을 깨지 않으면서 로그인 경로를 막음. **정산 파이프라인은 주문을 만들지 않으므로 이 모듈에 의존할 필요 없음** — 새 정산 sync job이 `log_access`에 남길 actor는 기존 `naver_ingest_bot` user id를 재사용하거나(감사 일관성), 없으면 `None`으로 둬도 무방(정산 sync는 주문 생성 계약과 무관).

### 2.3 환경변수

- `NAVER_COMMERCE_CLIENT_ID` / `NAVER_COMMERCE_CLIENT_SECRET` (client.py:310-313) — 인증. 값 미기재(정책).
- `NAVER_COMMERCE_APP_EXPIRES_ON` (app_expiry.py:27) — 앱 인증 만료일 수동 기록(만료 임박 알림용, `foms/services/integrations/naver_commerce/app_expiry.py`).
- `REDIS_URL` — 있으면 토큰 캐시가 Redis, 없으면 메모리(client.py:167-176).
- 기능 스위치 전부 `FOMS_NAVER_*_ENABLED` 컨벤션(start.sh, foms/services/feature_flags.py): `FOMS_NAVER_SYNC_ENABLED`, `FOMS_NAVER_SYNC_INTERVAL_SECONDS`, `FOMS_NAVER_AUTO_DISPATCH_ENABLED`/`_AT`/`_WINDOW_MINUTES`, `FOMS_NAVER_BULK_DISPATCH_ENABLED`, `FOMS_NAVER_CANCEL_APPROVE_ENABLED`, `FOMS_NAVER_RETURN_APPROVE_ENABLED`, `FOMS_NAVER_RETURN_REJECT_ENABLED`, `FOMS_NAVER_WORKBENCH_ENABLED`/`_COHORT`. → 정산 sync도 `FOMS_NAVER_SETTLE_SYNC_ENABLED`(가칭) 패턴을 따르는 것이 컨벤션 일치.

---

## 3. 워커 단일 출구 제약 — 증거와 판정

### 3.1 직접 증거

- **client.py 클래스 docstring** (client.py:279-284): "WORKER 프로세스에서만 인스턴스화한다(§3.1 IP 제약)."
- **ingest.py 모듈 docstring** (ingest.py:11-12): "WORKER 프로세스 전용이다. web 에서 부르면 커머스API센터에 등록되지 않은 IP 라 차단된다(IP 슬롯 3개를 WORKER 가 전부 쓴다). web 의 '지금 수집' 은 rq enqueue 만 한다."
- **naver_ingest.py (admin web) 모듈 docstring** (foms/web/admin/naver_ingest.py:10-12): "'지금 수집' 은 rq enqueue 만 한다. 네이버 HTTP 는 WORKER 에서만 나가야 한다 — 커머스API센터 호출 IP 한도(3)와 Railway static outbound IP(3)가 같아 여유가 0이라, web 에서 부르면 등록되지 않은 IP 라 차단된다. 취향이 아니라 제약이다."
- **backfill.py** (backfill.py:30): "WORKER 프로세스 전용이다 — 네이버 HTTP 는 등록된 IP 가 WORKER 것뿐이다. web 은 enqueue 만 한다."
- **run_naver_order_sync.py** (scripts/maintenance/run_naver_order_sync.py:3-5): "이 스크립트는 WORKER 서비스에서만 돈다. 커머스API센터 애플리케이션의 호출 IP 한도는 3개고 Railway static outbound IP 도 서비스당 3개다. 정확히 3=3이라 여유가 없어..."
- **queue.py의 모든 `enqueue_naver_*` 함수**(foms/services/jobs/queue.py:209-474)는 `q.enqueue(f"{_TASK_PATH_PREFIX}.run_naver_*_task", ...)`만 하고 큐가 없으면 `False` 반환 — **동기 폴백이 아예 없음**(예: geocode/thumbnail은 다른 서비스라 폴백이 있지만 naver 계열은 "조용히 성공한 척하지 않는다"는 설계 원칙으로 폴백 자체를 배제, queue.py:212-213, 233-234).

### 3.2 코드 경로 확인 — web에 직접 호출 없음

`grep -rn "NaverCommerceClient(" foms/` 결과, 인스턴스화 지점은:
- `foms/services/jobs/tasks.py:397` (`run_naver_fulfillment_task`, 워커 태스크)
- `foms/services/integrations/naver_commerce/ingest.py:503`, `backfill.py:204`(둘 다 함수 내부 지연 import, 호출자는 워커 스크립트/태스크)
- `scripts/maintenance/run_naver_*.py` 각 스크립트

`foms/web/`, `foms/api/` 트리에는 `NaverCommerceClient` import/인스턴스화가 없음(naver_ingest.py는 `enqueue_naver_*`만 import, foms/web/admin/naver_ingest.py:44-45).

### 3.3 흐름 — enqueue → worker → DB → web 읽기

1. **web**: 관리자가 "지금 수집" 클릭 → `POST /admin/naver-ingest/run` (foms/web/admin/naver_ingest.py:5575 `naver_ingest_run_now`) → `get_rq_runtime_status()`로 워커 생존 확인(0대 확실하면 503 즉시 거절, 워커 수를 "못 셌다"와 "0대"를 구분해서 판정, naver_ingest.py:5601-5610) → `enqueue_naver_order_sync(dry_run=False)`(queue.py:456) → 큐잉 성공 시 `{"queued": True, "rev": base_rev}` 반환.
2. **worker**: `rq worker default`(start.sh 마지막 줄)가 `run_naver_order_sync_task`(tasks.py:560)를 꺼내 실행 → `NaverCommerceClient()` 생성 → `run_sweep()`(ingest.py:483) → 네이버 HTTP 호출 → `ExternalOrderLink` INSERT + 워터마크(SystemSetting) 갱신 → commit.
3. **web 폴링**: `GET /admin/naver-ingest/run-state`(naver_ingest.py:5649 `naver_ingest_run_state`) — **읽기 전용 GET, mutation 아님**(감사 라벨·write manifest 불요, naver_ingest.py:5660-5663) — 워터마크의 `rev`(지문, `_watermark_rev`, naver_ingest.py:191)가 바뀌면 수집 완료로 판정. 화면이 이 엔드포인트를 짧은 간격으로 폴링.
4. **web 최종 표시**: 모든 화면(대시보드·워크벤치)은 `ExternalOrderLink`/`Order` 등 **DB만** 읽는다.

### 3.4 정기 스케줄 배선 (start.sh)

`start.sh`에서 `USE_RQ_WORKER=1`일 때만 도는 백그라운드 서브셸 3종(현재):
- 알림 escalation 스윕(`run_notification_escalation.py --loop`)
- 네이버 수집(`run_naver_order_sync.py --loop --interval 300`, `FOMS_NAVER_SYNC_ENABLED=1`일 때만, 기본 off)
- 네이버 자동 발송처리(`run_naver_auto_dispatch.py --loop --at 16:50 --window 10`, `FOMS_NAVER_AUTO_DISPATCH_ENABLED=1`일 때만)
- 좌표 스윕(`run_geocode_sweep.py --loop`)

모두 "**FOMS는 in-process 스케줄러가 없고 새 인프라 의존성(rq-scheduler·외부 cron) 추가는 금지**"라는 명시적 설계 제약 하에, `rq worker` 프로세스 안에서 `&`로 백그라운드 서브셸을 띄우는 방식(start.sh:29-31 주석). 스윕 실패가 `rq worker` 본체를 안 죽이게 격리.

### 3.5 판정: web 실시간 동기 호출 가능한가

**불가능. 확정.** Railway static egress IP 3개(web 2대 + worker 1대가 아니라, **서비스당 3개 슬롯이 정확히 IP 3개와 일치**하는 구조 — 메모리 노트 `project_railway_egress_ip_shared_by_region.md`)이고, 네이버 커머스API센터에는 WORKER 서비스의 IP만 등록돼 있다(client.py, ingest.py, naver_ingest.py 세 곳이 동일한 근거를 반복 명시). web에서 "실시간 조회" 버튼을 눌러 그 자리에서 네이버 API를 때리는 UI는 **설계상 불가능** — 반드시 enqueue → worker 처리 → DB 저장 → web이 DB를 읽는 비동기 경로만 가능하다. §8에서 이 판정이 파이프라인 형태 선택에 미치는 함의를 정리한다.

---

## 4. 영속화 패턴

### 4.1 기존 모델 — `ExternalOrderLink` (models.py:3500-3606)

- `channel`(String20, 기본 'NAVER') + `external_id`(String64) 조합에 `UniqueConstraint('channel','external_id')`(models.py:3579) — 멱등 정본.
- `raw_snapshot = Column(JSONColumn, nullable=True)`(models.py:3533) — 원본 응답 그대로. `JSONColumn = JSON().with_variant(JSONB, 'postgresql')`(models.py:17) — SQLite 테스트 레인은 JSON, 운영 PostgreSQL은 JSONB로 자동 분기.
- 필터 전용 **사본 컬럼**(정본은 JSONB, 이 컬럼들은 인덱스를 위한 복제): `sync_status`, `place_order_status`, `group_key`, `recipient_name`, `recipient_phone_digits`, `orderer_phone_digits`(models.py:3550-3568) — "JSONB 안에 있으면 SQL이 못 좁힌다"는 반복되는 설계 원칙(models.py:3554-3558 주석, 45집 vs 43집 실사고 인용).
- 인덱스는 전부 **부분 인덱스**(`postgresql_where=text(...)`)로 활성 데이터만 커버(models.py:3591-3599, 예: 미연결 행만 인덱싱).

### 4.2 상태 저장 — `SystemSetting` 재사용 패턴 (전용 테이블 안 만듦)

- 워터마크(`watermark.py:24` `SETTING_KEY = "naver_sync_watermark"`)와 백필 진행상태(`backfill.py:55` `SETTING_KEY = "naver_backfill_state"`) 둘 다 **새 테이블을 안 만들고** 기존 `SystemSetting`(단일 행, JSONB `setting_value`, `version` optimistic lock)을 키만 다르게 재사용. 정산 동기화의 "마지막 성공 구간"도 같은 패턴(`naver_settle_sync_watermark` 같은 새 키)으로 충분 — 전용 워터마크 테이블 불필요.
- 쓰기는 `_write(session, state)`(watermark.py:115-126) 같은 upsert 헬퍼 하나로 통일, `row.version += 1`로 낙관적 락.

### 4.3 마이그레이션 컨벤션

- 파일명 = `<slug>_00_<설명>.py`, `revision = '<slug>_00'`(예: `naver_link_00_external_order_links.py`, revision `naver_link_00`, migrations/versions/naver_link_00_external_order_links.py:29).
- **마이그레이션 상수 동결 원칙**: `models.py`를 마이그레이션에서 import하지 않고 테이블/제약명을 리터럴로 반복(naver_link_00 파일:19-20 주석) — 과거 마이그레이션이 `models`의 현재 상태로 소급 오염되는 것을 막기 위함(메모리 노트 `project_migration_constant_freeze.md`).
- **단일 head 게이트**: `tests/domains/test_alembic_single_head.py`(pre_push_smoke 포함)가 `ScriptDirectory.get_heads()` 길이 1을 강제. 현재 HEAD = `wizsend_00`(본 세션 실측, `alembic.script.ScriptDirectory`). 새 정산 마이그레이션은 `down_revision = 'wizsend_00'`에서 시작해야 함(단, 다른 세션이 동시에 마이그레이션을 추가하면 merge 리비전 필요 — `merge_*_heads.py` 관례가 이미 2건 존재: `merge_drawqueue_naverfail_heads.py`, `merge_naverbf_sharehist_heads.py`).
- `downgrade()`는 인덱스→테이블 역순 필수(naver_link_00 파일 컨벤션).

### 4.4 인덱스 설계 관행

기존 `ExternalOrderLink` 인덱스는 전부 "화면이 실제로 SQL로 좁혀야 하는 축"만 컬럼화하고 나머지는 JSONB에 둔다. 정산 테이블도 같은 원칙 적용 권장: `settlement_date`, `product_order_id`(또는 정산 API의 식별자), `settle_type` 등 조회·정렬 축만 컬럼, 상세 금액 breakdown은 JSONB `raw_snapshot`으로.

---

## 5. Admin/워크벤치 UI — 노출 패턴

### 5.1 `foms/web/admin/naver_ingest.py` (5875줄, 관리자 전용)

- 인증: `@login_required` + `@role_required(["ADMIN"])`(naver_ingest.py:5577-5578 등 모든 mutation 라우트 공통).
- **"지금 수집" 흐름**은 §3.3에 상술. 핵심 UX 패턴: enqueue 전에 워커 생존을 먼저 확인하고, "0대 확실"과 "못 셌음"을 구분해 오판을 막음(naver_ingest.py:5598-5610, 2026-08-26 CEO 지적 반영).
- 워터마크 뷰(`_watermark_view`, naver_ingest.py:178), 만료 뷰(`_expiry_view`, naver_ingest.py:240) — 모두 DB(SystemSetting) 읽기만, 네이버 실시간 호출 없음.
- 자격증명·시크릿 값은 화면에 노출되지 않음(`grep`으로 시크릿 렌더링 코드 없음 확인). `NAVER_COMMERCE_APP_EXPIRES_ON`만 만료일(날짜)을 사람이 수동 입력해 알림에 사용(app_expiry.py).

### 5.2 정산·정산 관련 기존 언급 (전수 grep 결과)

`grep -rniE "정산|pay-settle|settle" foms/ templates/ static/ scripts/ docs/plans docs/specs`:

| 파일 | 내용 |
|---|---|
| `foms/api/cs/dashboard.py`(정산 발행/이슈, `structured_data.settlement`) | **네이버와 무관** — CS 부서의 비용 청구/차감 이벤트 기록 기능. 이름만 "정산"이지 회계·네이버 정산 API와 다른 도메인. |
| `foms/api/personal_board.py:245-261` | 위와 같은 `structured_data.settlement` 읽기(개인 보드 알림 카운트). |
| `templates/cs/partials/settlement_operations_body.html:87` | 정산 대시보드 "실무" 탭의 채널 필터 칩 하나 — `data-settlement-ops-value="NAVER"` 텍스트 "네이버". **이미 채널 필터 UI 자리가 있다** — 네이버 정산 데이터를 얹을 때 이 필터와 자연 결합 가능. |
| `docs/specs/2026-08-31-settlement-dashboard_SPEC.md:108-109, 302, 318-319` | §3.4 "채널 판정 = ExternalOrderLink"(LEFT JOIN으로 NAVER/일반 구분), §10 Q2(naver.source 전수성 미검증), **§11 로드맵**: "채널 수수료 대사 — `naver.payment.expected_settlement_amount` 정형화 + 수수료율 마스터"·"반품 환불액 — 네이버 클레임 금액 동기화, NAVER-INGEST-01 v1 비목표, **후속 스펙 필요**"를 **v1 비목표로 명시적으로 로드맵에 적어둠**. 이번 작업이 그 후속 스펙에 해당. |
| `docs/plans/2026-08-13-naver-order-ingest-ledger.md:477` | "정산예정액" — `build_payment_info`가 뽑는 필드 나열 중 하나(§5.2 참고). |
| `static/css/orders/erp-naver-dock.css`, `static/js/orders/erp-naver-dock.js` | 파일명에 "naver-dock"이 들어가 grep에 걸렸을 뿐, 정산과 무관(주문 편집 옆 네이버 원본 도크 UI). |

**결론**: 네이버 정산 API 데이터를 다루는 코드·화면·스펙은 저장소에 전무. 완전 신규 영역. 단, 기존 정산 대시보드가 이미 "네이버" 채널 필터 UI(§5.2 표 3행)와 채널 판정 SSOT(`ExternalOrderLink` LEFT JOIN)를 갖추고 있어 접점은 명확하다.

### 5.3 `expected_settlement_amount`와의 관계 (혼동 주의)

`mapping.py:1074` — `build_payment_info()`가 주문 상세 응답(`product-orders/query`)에서 `expectedSettlementAmount` 필드를 뽑아 `structured_data.naver.payment.expected_settlement_amount`에 저장(이미 수집 중, 매 주문마다). 이것은 **주문 시점 네이버 측 예측값**이며, `/v1/pay-settle/settle/*` API가 주는 **확정 정산액**과는 다른 데이터(시점·확정 여부가 다름). 정산 대시보드 설계 시 이 필드를 "이미 있는 근사치", 신규 정산 API 데이터를 "확정치"로 구분해서 문서화할 것.

---

## 6. 테스트·계약

### 6.1 `naver_commerce` 테스트 위치

- 단위: `tests/services/integrations/test_naver_*.py` (다수, 예: `test_naver_commerce_client.py`, `test_naver_backfill.py`, `test_naver_admin_surface.py`).
- PG 레인: `tests/postgres/test_naver_*_pg.py`.
- 계약: `tests/contracts/test_external_token_client_discipline.py`, `tests/contracts/runtime/test_ptc_physical_exactness.py`.

### 6.2 클라이언트 모킹 패턴 (`test_naver_commerce_client.py`)

`FakeResponse`(status_code/json()/text/headers 최소 계약)와 `FakeTransport`(경로별 응답 큐, `request(method, url, **kwargs)`)를 client 생성자의 `transport=` 인자에 주입 — **네트워크 전혀 안 탐**. `sleep=` 인자에 가짜 sleep도 주입해 백오프 대기를 실시간으로 안 기다림. 정산 메서드 추가 시 같은 fixture 클래스를 그대로 재사용해 `routes={"/v1/pay-settle/settle/daily": [...]}` 식으로 확장하면 됨.

### 6.3 토큰 클라이언트 규율 계약 (EXT-TOKEN-01)

`tests/contracts/test_external_token_client_discipline.py:42-51` — `client.py`는 이미 등재부(`_TOKEN_CLIENT_CONTRACTS`)에 올라 있고, 요구 테스트(`test_token_cache_ttl_shrinks_by_refresh_margin`, `test_unauthorized_refreshes_token_once_then_succeeds`, `test_persistent_unauthorized_raises_auth_error_without_loop`)가 `test_naver_commerce_client.py`에 이미 존재. **정산 메서드를 client.py에 추가하는 한 이 계약은 자동으로 계속 충족** — 새 클라이언트 파일을 따로 만들 경우에만 신규 등재가 필요하다(`_discover_token_caching_modules`가 `access_token`/`token_cache` 패턴을 소스 스캔으로 자동 탐지하므로 등재 누락은 CI red로 잡힘, test_external_token_client_discipline.py:58-87).

### 6.4 PTC(Physical Tree Convergence) 닫힌집합 계약

`tests/contracts/runtime/test_ptc_physical_exactness.py` — 저장소 **루트**(`_PTC_ROOT_ALLOWLIST`, 파일:20-67), `static/js/runtime/`(파일:71-88), `foms/services/common/`(파일:91-111)만 정확 일치 allowlist로 잠겨 있음. **`foms/services/integrations/naver_commerce/` 디렉토리 자체는 닫힌집합 대상이 아님** — 새 파일(`settle.py` 등)을 자유롭게 추가 가능. 단 `foms/web/*`, `foms/api/*` 최상위 신규 디렉토리 생성은 별도 닫힌집합 계약에 걸릴 수 있다는 메모리 노트(`project_namespace_closed_set_dirs.md`)가 있으므로, 정산 API 라우트는 기존 `foms/api/cs/` 또는 `foms/web/admin/` 트리 안에 새 파일로 추가하는 편이 안전(신규 최상위 서브패키지 생성은 별도 확인 필요 — R1-api-spec 담당 영역).

### 6.5 감사 로깅 컨벤션

`log_access(action_message, user_id=None, additional_data=None, auto_commit=True, *, action=None, target_type=None, target_id=None, detail=None, db=None)`(foms/web/auth/routes.py:69-70) — **두 번째 위치 인자가 행위자(actor) user_id**. 메모리 노트(`project_naver_ingest_audit_actor_gap.md`)가 경고하듯 naver_ingest.py에서 이 인자를 누락한 사례가 19곳 있었음(2026-08-27 이후 수정됨, 현재 `naver_ingest_run_now`는 `session.get("user_id")`를 정확히 전달 — naver_ingest.py:5610, 5622). **정산은 읽기 전용(GET) API라 mutation이 아니므로 write manifest·감사 라벨 의무는 없음**(§3.3의 `run-state` 엔드포인트가 "읽기 전용 GET이라 감사 라벨 없음"이라고 명시한 것과 동일 논리, naver_ingest.py:5660-5663). 다만 "지금 정산 조회" 같은 수동 트리거 버튼을 만든다면 그 enqueue 액션 자체는 `NAVER_INGEST_RUN_NOW`처럼 `log_access`로 남기는 것이 컨벤션 일치.

---

## 7. 스케줄링

### 7.1 두 가지 기존 배선 패턴

1. **짧은 interval 폴링형** — `run_naver_order_sync.py --loop --interval 300`(scripts/maintenance/run_naver_order_sync.py:78-91). 앱 1회 부팅 후 `while True: sweep(); sleep(interval)`. 스윕 1회 실패는 `traceback.print_exc()`로 로그만 남기고 루프는 죽지 않음(파일:87-90).
2. **하루 1회 시각창형** — `run_naver_auto_dispatch.py --loop --at 16:50 --window 10`(scripts/maintenance/run_naver_auto_dispatch.py 헤더:6-13). 짧은 틱(기본 60초)으로 깨어나 "지금이 그 시각 창 안인가"만 판정하고, 실행 여부는 DB 상태로 하루 1회를 보장(러너가 여러 번 깨어나도 중복 실행 없음).

**정산 sync 권장**: 네이버 정산 데이터는 전일 마감 기준 데이터라(패턴 2 적합), `run_naver_settle_sync.py --loop --at <시각> --window <N>` 형태로 새 스크립트를 만들고 `start.sh`에 `FOMS_NAVER_SETTLE_SYNC_ENABLED=1`일 때만 백그라운드 서브셸로 추가하는 것이 기존 컨벤션과 가장 잘 맞는다(§3.4의 4개 서브셸과 동일한 배선 방식).

### 7.2 워커 재배포가 큐를 멈추는 함정

메모리 노트(`project_worker_redeploy_stalls_queue.md`)와 코드 근거(`tools/ops/check_worker_redeploy_safe.py:1-13`) — **운영 worker는 1대**(네이버 API 호출 IP 계약상 단일 서비스 강제)라서, worker를 재배포하면 `rq worker`가 내려갔다 올라오는 동안 **큐 전체가 정지**한다(작업 유실은 없지만 지연). 2026-08-31 실사례로 사용자가 넣은 요청이 14분(852초) 밀린 전례가 있음. **정산 sync 기능을 추가·수정할 때마다 worker를 재배포하게 되므로**, 배포 타이밍에 `check_worker_redeploy_safe.py`로 안전 여부를 확인하는 운영 관행을 그대로 따를 것 — 이는 새 기능이 아니라 기존 배포 절차의 반복 리스크.

### 7.3 CALL_INTERVAL / RPS 준수

`backfill.py:63` — `CALL_INTERVAL_SECONDS = 0.5`(2 RPS 고정 제약의 절반, 워커 동시성 1 전제). 정산 API도 같은 앱의 같은 rate limit(2 RPS)을 공유하므로, 일별 배치로 여러 날짜를 순회 조회할 경우 같은 간격 상수를 재사용해야 함.

---

## 8. 파이프라인 형태 권고

### 8.1 왜 "라이브 프록시"는 불가능한가 (§3.5 재확인)

web 프로세스는 네이버 API를 호출할 등록된 IP가 없다(3=3 슬롯, 전부 WORKER). "실시간 조회" 버튼을 눌러 그 자리에서 정산 데이터를 네이버에서 즉시 가져와 보여주는 UI는 **인프라 제약상 물리적으로 불가능**하다 — 우회하려면 (a) WORKER가 그 자리에서 동기 호출 후 결과를 rq job 결과로 web에 반환(가능하지만 UX상 폴링이 필요해 "실시간"이 아님), 또는 (b) 새 Railway 서비스를 만들어 IP 슬롯을 늘림(스펙 밖, 비용·복잡도 증가, 기존 3=3 계약을 깨는 결정이라 사용자 승인 필요). 현재 시스템의 다른 모든 네이버 상호작용(발주확인·발송처리·취소·반품)이 전부 이 제약 하에 "enqueue → 워커 처리 → DB 반영 → 화면 폴링/새로고침" 패턴을 쓰고 있으므로, 정산도 예외를 만들 이유가 없다.

### 8.2 권장 아키텍처

```
[일별 스케줄 job — WORKER]                     [web]
run_naver_settle_sync.py --loop --at HH:MM
  → NaverCommerceClient (client.py 확장)
    → GET /v1/pay-settle/settle/case
    → GET /v1/pay-settle/settle/commission-details
    → GET /v1/pay-settle/settle/daily
    → GET /v1/pay-settle/vat/case
    → GET /v1/pay-settle/vat/daily
  → 원본 스냅샷 + 필터 사본 컬럼으로 DB 저장          기존 정산 대시보드(§ SPEC)
  → SystemSetting 워터마크 전진(성공 구간만)   ←────  가 이 테이블을 LEFT JOIN/UNION
                                                    (channel='NAVER' 축)으로 흡수,
[web 관리 화면 — "지금 정산 조회" 버튼]              또는 별도 "네이버 정산" 탭에서
  POST /admin/.../settle-run                        직접 조회 (탭 배치는 R2 담당)
  → enqueue_naver_settle_sync() (queue.py 확장)
  → GET .../settle-run-state 로 rev 폴링
```

**테이블 후보**(브리프에 나열된 이름 그대로, JSONB `raw_snapshot` + 조회축 컬럼화 원칙 적용):
- `naver_settle_daily` — 일별 정산 요약. 조회축 컬럼: `settle_date`, `settle_type`(입금/보류 등, API 응답 확인 필요).
- `naver_settle_case` — 건별 정산. 조회축: `product_order_id` 또는 정산 API의 `settleCaseId`(문서명 확인 필요) + `settle_date`, `order_id`(FK, `ExternalOrderLink.external_id`와 조인 가능하도록).
- `naver_vat_daily` / `naver_vat_case` — 부가세 대응 테이블, 같은 축.
- `naver_commission_detail` — 수수료 상세(쿠폰 부담 비율 등 — `mapping.py:1036-1038`이 이미 다루는 "네이버 부담 vs 셀러 부담" 개념과 연결 지점).
- 모두 `channel`(향후 확장 대비, 지금은 'NAVER' 고정) + 멱등 키 `UNIQUE` 제약 + `naver_settle_00_*` 슬롭의 마이그레이션.
- `ExternalOrderLink.external_id`(productOrderId)를 정산 API의 상품주문 식별자와 매칭시키면 "주문 단위 정산 상세"를 만들 수 있음 — 단, 정산 API 응답의 식별자 필드명이 `productOrderId`와 동일한지는 API 응답 실측 필요(NOT IN DOCS면 안전측으로 별도 매핑 테이블 고려).

### 8.3 "실시간 조회" UI에 대한 함의

- 사용자에게 보여줄 수 있는 것은 **"마지막 동기화 시각"이 찍힌 DB 스냅샷**뿐이다. 기존 워크벤치의 워터마크 표시(`_watermark_view`, naver_ingest.py:178) 및 "지금 수집" 버튼 + rev 폴링(§3.3) 패턴을 그대로 정산 화면에 이식하면, 사용자는 "지금 정산 다시 불러오기" 버튼을 눌러 최대 몇 분 내 최신화를 체감할 수 있다 — 이것이 이 시스템에서 낼 수 있는 "실시간"의 상한이다.
- 대시보드 문구는 "실시간 조회"가 아니라 "마지막 동기화: HH:MM (N분 전)" 같은 정직한 표현을 권장(다른 네이버 연동 화면들의 기존 관행과 일치, 예: 워터마크 뷰의 `last_run_at` 노출).
- 정산 API 자체가 원래 **전일/전전일 마감 데이터**를 주는 배치성 API일 가능성이 높으므로(정산은 결제 마감 사이클을 갖는 게 일반적), 하루 1회 동기화로도 실사용 요구를 충분히 만족시킬 가능성이 크다 — 다만 이는 브리프의 API 문서(`apicenter.commerce.naver.com/llms/get-v1-pay-settle-*.md`)로 확정해야 할 사실이며 본 조사(코드 기반)로는 "확인 필요"로 남긴다.

---

## 참고 — 확인이 필요한 미지 항목 (코드로 검증 불가, API 문서 확인 필요)

- 정산 API 5종의 정확한 요청 파라미터(날짜 범위 상한, 페이지네이션 방식 — `more` 이어받기 방식인지 `page`/`size` 방식인지)와 응답 스키마 — client.py의 재사용 가능 패턴(§1.4)은 확정이나, 구체 파라미터명은 `apicenter.commerce.naver.com/llms/get-v1-pay-settle-*.md` 원문 확인 필요(브리프 §"알려진 제약" 규칙: "질의 창구 없음 → 모르면 NOT IN DOCS + 안전측").
- 정산 API가 별도 OAuth scope/권한 신청을 요구하는지(브리프상 "승인 완료"라고 되어 있어 이미 해결된 것으로 보이나 코드로는 검증 불가).
