# Railway Production 성능 개선 최종 블루프린트

- 작성일: 2026-03-17
- 문서 성격: 착수용 최종본
- GDM 감리: 2026-03-17 완료 (코드 1:1 대조 검증, 보강 5건 반영)
- 기준 소스:
  - `Procfile`
  - `app.py`
  - `requirements.txt`
  - `db.py`
  - `services/db_url_resolver.py`
  - `apps/api/erp_orders_structured.py`
  - `erp_build_step_runner.py`
  - `apps/erp_dashboard.py`
  - `apps/erp_measurement_dashboard.py`
  - `apps/erp_shipment_page.py`
  - `apps/erp_as_page.py`
  - `apps/erp_production_page.py`
  - `services/jobs/queue.py`
  - `services/jobs/tasks.py`
  - `services/erp_display.py`
  - `apps/auth.py`
  - `templates/partials/erp_beta_js.html`
  - `templates/partials/erp_dashboard_scripts_detail_dom.html`

---

## 1. 최종 판정

이 블루프린트는 바로 착수 가능하다.

다만 이번 작업의 핵심은 "Railway가 느리다"는 증상을 넓게 만지는 것이 아니라, 현재 소스 기준으로 확인된 병목을 우선순위대로 제거하는 것이다.

최우선 병목은 아래 5개다.

1. `gunicorn gevent + psycopg2` 조합에서 `psycogreen`이 빠져 있다.
2. `apps/api/erp_orders_structured.py`의 save / parse 경로가 불필요한 `commit()`을 여러 번 발생시킨다.
3. 일부 ERP 페이지가 원격 환경에 불리한 조회 패턴을 사용한다.
4. ERP Beta save 완료 후 `setTimeout 500ms` 고정 대기가 redirect를 지연시킨다.
5. Dashboard bulk apply가 루프 안에서 `log_access()` → `db.commit()`을 N회 반복한다.

반대로 아래 항목은 이번 1차에서 주원인으로 단정하지 않는다.

- 압축/정적 캐시 누락
- DB pool 크기 부족
- geocode / ChannelTalk enqueue가 save를 동기적으로 막는 문제
- "앱-DB public internet RTT"가 save 지연의 핵심이라는 단정

---

## 2. 소스 1:1 대조 확정 사실

### 2.1 배포 / 런타임

- `Procfile`의 web 프로세스는 `gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5`
- `app.py`는 gunicorn/gevent runtime에서 `gevent.monkey.patch_all()` 수행 (app.py:7-8, try 블록)
- `requirements.txt`에는 `psycopg2-binary==2.9.9`(71줄)와 `gevent>=24.10.1`(122줄)가 있지만 `psycogreen`은 없다

이 조합은 동시 요청이 겹칠 때 DB I/O 구간에서 워커 활용률 저하 가능성이 높다.

### 2.2 이미 들어가 있는 최적화

- `app.py:95`에 `Compress(app)`가 이미 있다
- `app.py:100`에 `WhiteNoise(...)`가 이미 있다
- `db.py:56,62-64`에 `pool_pre_ping=True`, `pool_size=20`, `max_overflow=20`, `pool_recycle=1800`이 이미 있다
- `services/db_url_resolver.py`의 네트워크 경로:
  - **Railway 서버(Linux)**: `PGHOST`/`PGPORT` 등 PG* 환경변수로 직접 연결 (internal network)
  - **로컬 개발(Windows)**: `.railway.internal` 호스트 감지 시 `DATABASE_PUBLIC_URL`로 폴백
  - 즉, 서버 환경에서는 앱-DB가 **PG* 직접 연결 경로를 우선 사용**한다. 일반적인 Railway 서버 구성에서는 private/internal network 경로다

즉 아래는 이번 1차 우선순위가 아니다.

- 압축 추가
- 정적 파일 캐시 추가
- DB pool 확대
- 앱-DB public network 병목 가정

### 2.3 저장 병목

`apps/api/erp_orders_structured.py` 기준:

- `_ensure_system_build_steps_table()`가 DDL 후 `db.commit()` 수행 — **호출당 1회**
- `_record_build_step()`가 별도 `db.commit()` 수행 — **호출당 1회**
- `api_put_order_structured()`는 save 시작(RUNNING) + 완료(COMPLETED) 시 `_record_build_step()` **2회** 호출
- main save 로직도 별도 `db.commit()` 수행
- `api_parse_order_text()`도 동일 helper를 사용

정상 PUT 요청 1건당 총 **5회 commit** (DDL commit×2 + DML commit×2 + 메인×1).

### 2.4 읽기 병목

#### 2.4.1 ERP 메인 대시보드 (`apps/erp_dashboard.py`)

- 검색어가 없으면 `limit(300)` (줄 57)
- 검색어가 있으면 `_q.all()` — **상한 없이 전체 스캔**
- **검색 필터링이 Python 레벨**: DB WHERE 절이 아니라 Python 루프에서 문자열 concat + `lower()` 비교로 처리 (실제 필터 루프는 하단 `filtered` 조립 구간)
- 즉, `.all()`로 `is_erp_beta=True` 전체를 메모리에 올린 뒤 Python에서 필터링
- 페이지네이션: **없음**

#### 2.4.2 Production 페이지 (`apps/erp_production_page.py`)

- 검색어 유무와 무관하게 **항상 300건 고정 `.limit(300)`** (줄 50-56)
- 스테이지 필터 + 검색어 필터 **모두 Python 루프에서 처리** (줄 117-127)
- DB 인덱스 효과 없음. 300건 바깥에 있는 결과는 **누락**
- Python 후처리 비중이 **높은 편** (스테이지 분류, 판매 승인, step_stats 등)
- 페이지네이션: **없음**

#### 2.4.3 AS 페이지 (`apps/erp_as_page.py`)

- 항상 `.limit(300)` — 검색어 유무 무관 (줄 92-94)
- `cast(Order.structured_data, String).ilike(term)` **DB 레벨 검색** 사용 (줄 31-33)
- `mine=1` 필터는 `.all()` 후 Python 리스트 컴프리헨션 (줄 98)
- 페이지네이션: **없음**

#### 2.4.4 Measurement / Shipment 대시보드

- `apps/erp_measurement_dashboard.py`, `apps/erp_shipment_page.py`
- 이미 `selectinload(Order.schedule_dates)` + `load_only` 사용 — N+1 방지 적용
- `measurement` 목록: `.limit(500)` + Python `[:300]` 슬라이싱
- `shipment` 목록:
  - 기본 진입: `.limit(500)` + Python `[:300]`
  - 날짜 필터 진입: SQL `limit` 없이 조회 후 Python `[:300]`
- panel 쿼리는 14일 범위 JOIN + `.distinct()`로 범위 제한 (limit 없음)
- panel 계산(날짜 집계, capacity 계산)은 **전부 Python** — DB 집계 함수 미사용
- `cast(Order.structured_data, String).ilike(term)` **DB 레벨 검색** 사용
- 페이지네이션: **없음**

#### 2.4.5 읽기 패턴 비교표

| 항목 | erp_dashboard | erp_production | erp_as | erp_measurement | erp_shipment |
|---|---|---|---|---|---|
| **기본 limit** | 300 | 300 (고정) | 300 (고정) | 500 | 500 (기본 진입) |
| **검색어 시 limit** | **없음 (.all())** | 300 유지 | 300 유지 | 500 유지 | 기본 진입 500 유지 / 날짜필터 시 없음 |
| **검색 위치** | **Python** | **Python** | DB (ilike) | DB (ilike) | DB (ilike) |
| **selectinload** | 없음 | 없음 | 없음 | 있음 + load_only | 있음 + load_only |
| **페이지네이션** | 없음 | 없음 | 없음 | 없음 | 없음 |
| **Python 후처리** | 중간 | **높음** | 낮음 | 중간 | 중간 |

### 2.5 ERP Beta save 후 redirect 대기

`templates/partials/erp_beta_js.html` 기준:

- 줄 750-763: `fetch('/api/orders/${targetId}/structured', { method: 'PUT' })` 호출
- 줄 769: `erpSetStatus('저장 완료! 이동합니다...')`
- 줄 772: `setTimeout(() => { window.location.href = ... }, 500)` — **API 응답 완료 후 고정 500ms 대기**
- 이 500ms는 상태 메시지 노출 목적이지만, Railway 환경에서 API 자체가 느린 상황에서 추가 0.5초는 체감 악화

### 2.6 Dashboard bulk apply 루프 commit

`apps/api/orders.py`의 `bulk_update_order_status()` 기준:

- 줄 862: `db.query(Order).filter(Order.id.in_(valid_ids)).all()` — 1회 쿼리 (정상)
- 줄 864-900: `for order in orders:` 루프
  - 줄 870: `log_access(...)` — 삭제(휴지통) 시 호출
  - 줄 899: `log_access(...)` — 상태변경 시 호출
- `log_access()` (`apps/auth.py:38-49`):
  - 줄 42: `db.add(SecurityLog(...))`
  - 줄 43: `db.commit()` — **호출마다 즉시 commit**
  - 같은 scoped session이므로 주문 변경까지 함께 commit됨
- 줄 901: `db.commit()` — 루프에서 이미 매번 commit했으므로 사실상 중복

결과: 10건 bulk apply 시 총 **11회 commit** (루프 N회 + 최종 1회).

### 2.7 큐 경로

- `services/jobs/queue.py`의 geocode / ChannelTalk enqueue는 큐 등록만 수행
- 큐 미구성 시 `False`를 반환하고 저장 요청은 계속 진행
- `services/jobs/` 내 **print() 8건** (`queue.py` 4건 + `tasks.py` 4건) — `logger`로 교체 필요

따라서 현재 save 체감 지연의 직접 원인으로 보기 어렵다.

### 2.8 `system_build_steps` 유지 여부

- `erp_build_step_runner.py`는 `system_build_steps`를 실제로 읽는다 (`_get_step_status()`, 줄 68-73)
- 반면 API save/parse용 `ERP_BETA_API_SAVE_*`, `ERP_BETA_API_PARSE_TEXT` 읽기 경로는 로컬 코드에서 보이지 않는다

결론:

- `system_build_steps` 테이블은 유지
- API save/parse에서만 쓰는 build-step write는 제거 가능

### 2.9 read-path mutation 위험 (연관 사항)

- `services/erp_display.py`의 `apply_erp_display_fields()`가 대시보드 렌더링(읽기 경로)에서 `order.measurement_date`, `order.scheduled_date`를 **ORM 객체에 직접 대입**
- Session에 살아있는 Order 객체에 속성을 쓰면 SQLAlchemy가 dirty로 마킹
- 같은 request에서 `db.commit()` 발생 시 `before_flush` → `sync_order_dates`가 예상치 못하게 트리거
- 호출처: `dashboards.py`(3곳), `erp_shipment_page.py`, `erp_measurement_dashboard.py`(2곳), `erp_as_page.py`
- **이번 1차에서는 건드리지 않음** — Phase 3 이후 별도 과제

---

## 3. 최종 실행 원칙

1. 먼저 애플리케이션 병목을 제거한다.
2. 그 다음 배포 튜닝을 한다.
3. save 병목과 read 병목을 분리해서 고친다.
4. Measurement / Shipment 같은 비즈니스 규칙 밀집 페이지는 1차에서 과하게 건드리지 않는다.
5. `system_build_steps` 테이블은 유지하고 API 전용 write만 제거한다.
6. worker 수 / 리전 변경은 Phase 1 수치 확인 후 결정한다.
7. **Phase 2 페이지네이션 시 Python 검색을 DB 검색으로 전환하는 설계를 포함한다.**

---

## 4. 최종 실행 계획

### 4.0 실행 판정

바로 착수 가능하다.

실행 순서는 아래 4개 phase로 고정한다.

1. Phase 0: 운영 사실 확인
2. Phase 1: 동시성 / 저장 병목 제거
3. Phase 2: 읽기 경로 1차 최적화
4. Phase 3: 배포 튜닝 및 2차 최적화

---

### 4.1 Phase 0 - 운영 사실 확인

코드 수정과 병행 가능하며, 결정에 필요한 운영 사실만 확인한다.

#### 4.1.1 확인 항목

- web 서비스와 DB가 같은 Railway 프로젝트 / private network를 사용하는지 확인
- `REDIS_URL`이 실제 연결돼 worker가 떠 있는지 확인
- 느린 시간대의 `req_duration` 상위 endpoint를 1회 수집
- web 컨테이너 메모리 사용량 확인

#### 4.1.2 이번 단계에서 하지 않을 것

- 리전 이전
- worker 수 즉시 상향
- gunicorn worker class 교체

이 세 가지는 Phase 1 반영 후 측정값을 보고 결정한다.

---

### 4.2 Phase 1 - 동시성 / 저장 병목 제거

#### 4.2.1 Gevent-PostgreSQL 패치 적용

- 대상 파일: `requirements.txt`, `app.py`
- 작업:
  - `requirements.txt`에 `psycogreen` 추가
  - `app.py`의 gevent patch 구간에 `psycogreen.gevent.patch_psycopg()` 추가
- 구현 원칙:
  - gunicorn/gevent runtime에서만 patch
  - local Windows 실행 경로는 건드리지 않음
  - import 실패를 조용히 숨기지 말고 최소 info/warning 로그 남김

#### 4.2.2 ERP Beta API build-step commit 제거

- 대상 파일: `apps/api/erp_orders_structured.py`
- 작업:
  - `_ensure_system_build_steps_table()` 제거
  - `_record_build_step()` 제거
  - `api_put_order_structured()`의 build-step 호출 제거
  - `api_parse_order_text()`의 build-step 호출 제거
- 유지:
  - `system_build_steps` 테이블 유지
  - `erp_build_step_runner.py` 유지
- 예상 효과:
  - structured PUT 정상 경로: commit **5회 → 1회**
  - parse-text 경로: build-step용 commit 다중 실행 제거

#### 4.2.3 jobs 레이어 print → logger 교체

- 대상 파일: `services/jobs/queue.py`, `services/jobs/tasks.py`
- 대상 건수: **총 8건**
- 수정 규칙:
  - 단순 환경 미설정/건너뜀: `logger.info(...)`
  - enqueue 실패/worker 예외: `logger.warning(...)` 또는 `logger.error(...)`
  - 예외 정보가 있으면 `exc_info=True`
- 상세 위치:

| 파일 | 줄 | 현재 | 교체 |
|------|-----|------|------|
| `queue.py` | 25 | `print(f"[RQ] get_queue failed: {e}")` | `logger.warning(...)` |
| `queue.py` | 46 | `print(f"[RQ] enqueue_thumbnail error: {e}")` | `logger.error(...)` |
| `queue.py` | 66 | `print(f"[RQ] enqueue_geocode_order_address error: {e}")` | `logger.error(...)` |
| `queue.py` | 93 | `print(f"[RQ] enqueue_channeltalk_push error: {e}")` | `logger.error(...)` |
| `tasks.py` | 43 | `print(f"[RQ] create_thumbnail_for_attachment error: {e}")` | `logger.error(...)` |
| `tasks.py` | 101 | `print(f"[RQ] geocode_order_address error: {e}")` | `logger.error(...)` |
| `tasks.py` | 128 | `print("[채널톡] 환경변수 미설정 - 푸시 건너뜀")` | `logger.info(...)` |
| `tasks.py` | 191 | `print(f"[RQ] push_order_to_channeltalk error: {e}")` | `logger.error(...)` |

- 회귀 위험: 없음. 출력 채널만 변경

#### 4.2.4 save / parse latency 계측 추가

- 대상 파일: `apps/api/erp_orders_structured.py`
- 작업:
  - save / parse 시작 시각 기록
  - 주요 구간별 elapsed 로그 추가
    - 주문 조회
    - side effects
    - main commit
    - enqueue
- 원칙:
  - 응답 포맷 변경 금지
  - 계측 로그만 추가

#### 4.2.5 ERP Beta save 후 불필요한 500ms 대기 제거

- 대상 파일: `templates/partials/erp_beta_js.html`
- 현재 문제:
  - 줄 772: `setTimeout(() => { ... }, 500)` — API 응답 완료 후 **고정 500ms 대기** 뒤 redirect 실행
  - 사용자 체감: save 완료 후 0.5초 이상 빈 화면 대기
- 작업:
  - `setTimeout` 500ms 대기 제거 → 응답 성공 즉시 `window.location.href` 실행
  - `erpSetStatus('저장 완료! 이동합니다...')` 메시지는 유지 (redirect 전 잠깐 보임)
- 회귀 위험: 없음. 대기 시간만 제거

#### 4.2.6 Dashboard bulk apply 루프 내 commit 제거

- 대상 파일: `apps/api/orders.py`, `apps/auth.py`
- 현재 문제:
  - `bulk_update_order_status()` (줄 864-901)에서 주문 N건을 루프 처리
  - 루프 안에서 `log_access()` 호출 (줄 870 삭제 시, 줄 899 상태변경 시)
  - `log_access()` (`auth.py:43`)가 `SecurityLog` add 즉시 **`db.commit()`** 실행
  - 10건 선택 시 **10회 개별 commit** + 최종 commit 1회 = 총 **11회 DB round trip**
- 수정 방향:
  - **방안 A (권장)**: `log_access`에 `auto_commit=True` 파라미터 추가. bulk 호출 시 `auto_commit=False`로 호출하여 commit을 루프 밖 1회로 통합
  - **방안 B**: bulk 전용 `log_access_batch(messages)` 함수 추가. SecurityLog를 한번에 add 후 commit 1회
  - 어떤 방안이든 **루프 내 commit을 루프 밖 1회로 통합**하는 것이 핵심
- 예상 효과:
  - 10건 bulk apply: commit **11회 → 1회** (10× DB round trip 절감)
- 회귀 위험:
  - `log_access`는 다른 곳에서도 호출됨 — 기존 단건 호출 동작은 변경 금지
  - SecurityLog 누락 없이 모든 로그가 최종 commit에 포함되는지 검증 필요

#### 4.2.7 Phase 1 검증 기준

1. Railway에서 ERP Beta save p95 감소
2. parse-text 응답 지연 감소
3. `erp_build_step_runner.py --resume` 동작 영향 없음
4. geocode / ChannelTalk enqueue 회귀 없음
5. local smoke 및 기본 save 플로우 회귀 없음
6. **ERP Beta save 후 redirect 체감 지연 감소 (500ms 제거)**
7. **Dashboard bulk apply 10건 이상 상태변경 응답시간 감소**
8. **bulk apply 후 SecurityLog 누락 없음 확인**

---

### 4.3 Phase 2 - 읽기 경로 1차 최적화

#### 4.3.1 ERP 메인 대시보드 search `.all()` 제거 + DB 검색 전환

- 대상 파일: `apps/erp_dashboard.py`, 관련 템플릿
- 현재 문제:
  - 검색어가 있으면 `_q.all()`로 전체 결과를 메모리에 올린다 (줄 57)
  - **검색 필터링이 Python 루프**(하단 `filtered` 조립 구간)에서 수행됨 — DB WHERE 절 아님
  - 단순히 `.all()` → `.limit()` 교체만으로는 Python 검색이 작동하지 않음
- 수정 방향:
  - **1단계**: Python 검색을 DB 레벨 검색(ilike 또는 tsvector)으로 전환
  - **2단계**: 항상 서버 페이지네이션 적용
  - 검색어가 있어도 `all()` 금지
  - 기본 page size는 50 또는 100
  - 기존 필터 쿼리스트링 유지
- 선행 설계 필요:
  - 현재 Python 검색이 `id`, `customer_name`, `phone`, `address`, `manager_name` 문자열 비교 기준으로 동작
  - DB 전환 시 동일 5개 필드를 `OR` + `ilike`로 구현
  - parity 확인 전 `structured_data` 검색은 추가하지 않음

#### 4.3.2 Production 페이지 — DB 검색 전환 + 페이지네이션

- 대상 파일: `apps/erp_production_page.py`, 관련 템플릿
- 현재 문제:
  - 300건 고정 로드 후 **스테이지 필터 + 검색어 모두 Python에서 처리** (줄 117-127)
  - DB 인덱스 효과 없음. 300건 바깥 결과 누락
- 수정 방향:
  - **1단계**: 스테이지 필터를 DB WHERE 절로 이동하되, 현재 의미를 유지하도록 `structured_data.workflow.stage` 기준으로 설계
  - **2단계**: 검색어를 DB `ilike`로 전환하되, 현재와 동일하게 `customer_name`, `phone`, `address` 3개 필드만 대상으로 유지
  - **3단계**: 페이지네이션 전환
  - 기존 정렬/필터 유지
  - `mine` 필터 의미 변경 금지
- 선행 설계 필요:
  - 현재 stage bucket은 `Order.status`가 아니라 `_erp_get_stage()`가 해석한 `workflow.stage` 기반
  - 현재 검색 parity 기준은 `customer_name`, `phone`, `address` 3개 필드다
  - `enriched` 빌드, `step_stats`, `is_sales_approved` 등 Python 후처리가 DB 전환과 어떻게 공존할지 설계

#### 4.3.3 AS 페이지 페이지네이션

- 대상 파일: `apps/erp_as_page.py`, 관련 템플릿
- 현재 상태:
  - 이미 `_erp_order_search_filter`로 **DB 레벨 검색** 사용 (줄 31-33)
  - 300건 `.limit(300)` 고정
- 수정 방향:
  - 페이지네이션만 추가 (검색 전환 불필요)
  - 기존 정렬/필터 유지
  - `mine` 필터는 DB 레벨 전환 검토 (현재 Python 리스트 컴프리헨션, 줄 98)

#### 4.3.4 Measurement / Shipment는 1차에서 구조 변경하지 않음

- 대상 파일: `apps/erp_measurement_dashboard.py`, `apps/erp_shipment_page.py`
- 이유:
  - 이미 `selectinload(Order.schedule_dates)` + `load_only` 사용
  - panel 계산과 비즈니스 규칙이 강하게 결합
  - save / gevent 병목 제거 전 구조를 건드리면 원인 분리가 어려움
- 대신 할 일:
  - `req_duration` 로그로 실제 느린 endpoint 확인
  - `cast(Order.structured_data, String).ilike(term)` 영향만 별도 측정

#### 4.3.5 Phase 2 검증 기준

1. `/erp/dashboard` 검색/필터 응답시간 감소
2. `/erp/production/dashboard`, `/erp/as` 초기 응답시간 감소
3. 페이지네이션 후 기존 필터/정렬 회귀 없음
4. page 이동 시 query param 손실 없음
5. **Python→DB 검색 전환 후 기존 검색 결과와 동일한 결과 반환 확인**

#### 4.3.6 Phase 2 실행 가능성

| 항목 | 판정 | 비고 |
|------|------|------|
| AS 페이지 페이지네이션 | 🟢 바로 실행 | DB 검색 이미 있음. 페이지네이션만 추가 |
| Dashboard `.all()` 제거 | 🟡 설계 선행 | Python 검색 → DB 검색 전환이 필수 전제 |
| Production 페이지네이션 | 🟡 설계 선행 | 스테이지+검색 Python→DB 전환 + 후처리 공존 설계 필요 |

---

### 4.4 Phase 3 - 배포 튜닝 및 2차 최적화

#### 4.4.1 worker 수 조정

- 대상 파일: `Procfile`
- 원칙:
  - Phase 1 반영 후 메모리와 p95 확인 전에는 `-w 2`를 섣불리 바꾸지 않음
  - `-w 3` 또는 `-w 4`는 메모리 여유 확인 후 적용

#### 4.4.2 리전 검토

- 현재 코드상 앱-DB는 서버 환경에서 PG* 환경변수 직접 연결 경로를 우선 사용한다
- 따라서 리전 검토는 주로 **브라우저-앱 RTT** 관점에서 판단
- 한국 사용자 비중이 높고 응답시간이 여전히 크면 AP 리전 검토

#### 4.4.3 Measurement / Shipment 2차 최적화

Phase 1, 2 후에도 느리면 별도 과제로 분리한다.

- `cast(Order.structured_data, String).ilike(term)` 대체 검색 설계
- measurement panel count SQL 집계 전환
- shipment panel capacity 계산용 전용 snapshot/query 분리
- `apply_erp_display_fields()`의 read-path mutation 제거
  - 이 함수가 읽기 경로에서 ORM 객체 속성을 직접 대입하여 dirty 마킹
  - `before_flush` → `sync_order_dates` 예상치 못한 트리거 가능
  - DTO 분리 또는 non-mutating display helper로 전환

---

## 5. 이번 실행에서 제외

### 5.1 gunicorn worker class 전면 교체

- `sync`, `gthread`, `eventlet` 전환은 이번 1차 범위에서 제외

### 5.2 `services/erp_display.py` 대규모 DTO 리팩토링

- mutation 제거는 맞는 방향이지만 1차 범위에서 제외
- `before_flush` 연쇄 트리거 위험은 인지하되, Phase 3 이후 별도 과제로 분리

### 5.3 broad JSONB 검색 제거의 즉시 적용

- Measurement / Shipment / AS 공통 검색 계약이 얽혀 있으므로 1차 범위에서 제외

### 5.4 `system_build_steps` 삭제

- 금지

### 5.5 `before_flush` 재진입 방어 추가

- 별도 문서(`docs/evolution/ERP_BETA_SAVE_FLOW_GDM_AUDIT_2026-03-16.md`) Phase 2에서 관리
- 이 블루프린트와 독립적으로 실행

---

## 6. GDM 감리 결과

### 6.1 코드 대조 검증 (12개 항목)

| # | 블루프린트 주장 | 코드 검증 | 판정 |
|---|---------------|----------|------|
| 1 | Procfile `-k gevent -w 2` | `gunicorn -k gevent -w 2 --timeout 120` | 맞음 |
| 2 | `psycogreen` 미존재 | requirements.txt에 없음 | 맞음 |
| 3 | `monkey.patch_all()` 존재 | app.py:7-8 try 블록 | 맞음 |
| 4 | `Compress(app)` + `WhiteNoise` 적용 | app.py:95, 100 | 맞음 |
| 5 | pool_size=20, max_overflow=20 | db.py:62-63. `pool_recycle=1800` 미언급 | 맞음 (1건 추가) |
| 6 | internal host 우선 사용 | **보정**: 서버는 PG* 직접, 로컬은 public 폴백 | 설명 보정 |
| 7 | 검색 시 `.all()` 무제한 | erp_dashboard.py:57 | 맞음 |
| 8 | `cast(structured_data, String).ilike` 3곳 | as, measurement, shipment | 맞음 |
| 9 | selectinload 적용 (measurement/shipment) | `selectinload + load_only` 양쪽 확인 | 맞음 |
| 10 | build-step commit 다중 실행 | 정확히 **5회** 확인 | 맞음 (수치 보강) |
| 11 | save 후 setTimeout 500ms | `erp_beta_js.html:772` 확인 | 맞음 (신규 추가) |
| 12 | bulk apply 루프 내 N회 commit | `orders.py:870,899` → `auth.py:43` `db.commit()` 확인 | 맞음 (신규 추가) |

### 6.2 보강 사항 (5건)

| # | 항목 | 보강 내용 |
|---|------|----------|
| 1 | dashboard 검색 | Python 레벨 검색이므로 `.all()`→`.limit()` 단순 교체 불가. DB 검색 전환 선행 필요 |
| 2 | production 검색/필터 | 스테이지 필터 + 검색어 모두 Python. 특히 stage는 `Order.status`가 아니라 `workflow.stage` 의미 보존 기준으로 DB 전환 필요 |
| 3 | read-path mutation | `apply_erp_display_fields`가 `before_flush` 연쇄 트리거 가능. Phase 3 연관 사항으로 명시 |
| 4 | save redirect 500ms | `erp_beta_js.html:772`에서 API 응답 후 불필요한 500ms 고정 대기. Phase 1에 제거 추가 |
| 5 | bulk apply 루프 commit | `log_access()` 내부 `db.commit()`이 루프 안에서 N회 발생. Phase 1에 통합 추가 |

### 6.3 원본 문서 대조 기준

이 블루프린트는 아래 기준으로 통과했다.

1. 실제 소스에 없는 병목을 새로 넣지 않았다.
2. 이미 적용된 최적화를 다시 하자고 쓰지 않았다.
3. save 병목과 read 병목을 분리했다.
4. 운영 확인이 필요한 항목과 코드 수정 항목을 섞지 않았다.
5. `system_build_steps` 유지 여부를 소스 기준으로 닫았다.
6. **Phase 2 페이지네이션의 전제 조건(Python→DB 검색 전환)을 명시했다.**
7. **사용자 보고 2건(save redirect 지연, bulk apply 지연)의 근본 원인을 코드 1:1 대조로 확인하고 Phase 1에 포함했다.**

결론: 차단급 불일치는 없다.

---

## 7. 최종 감리 결론

### 7.1 즉시 실행 항목 (Phase 1)

1. `requirements.txt` - `psycogreen` 추가
2. `app.py` - gunicorn/gevent 경로에 `patch_psycopg()` 추가
3. `apps/api/erp_orders_structured.py` - API build-step logging 제거 (commit 5회→1회)
4. `services/jobs/queue.py` + `services/jobs/tasks.py` - print 8건 → logger 교체
5. `apps/api/erp_orders_structured.py` - save / parse latency log 추가
6. `templates/partials/erp_beta_js.html` - save 후 setTimeout 500ms 제거 (즉시 redirect)
7. `apps/api/orders.py` + `apps/auth.py` - bulk apply 루프 내 commit N회 → 1회로 통합

### 7.2 1차 배포 후 바로 확인

1. save / parse p95
2. 동시 요청 시 gevent 워커 hang 체감 감소 여부
3. `req_duration` 상위 endpoint 재수집

### 7.3 그 다음 실행 (Phase 2)

1. `apps/erp_as_page.py` - 페이지네이션 (**🟢 바로 실행**)
2. `apps/erp_dashboard.py` - Python→DB 검색 전환 + `.all()` 제거 + 페이지네이션 (**🟡 설계 선행**)
3. `apps/erp_production_page.py` - Python→DB 필터 전환 + 페이지네이션 (**🟡 설계 선행**)

### 7.4 측정 후 결정 (Phase 3)

1. worker 수 상향
2. region 재배치
3. Measurement / Shipment 2차 쿼리 최적화
4. `apply_erp_display_fields` read-path mutation 제거

---

## 8. 감리상 금지 사항

다음은 이번 실행 중 금지한다.

1. `system_build_steps` 테이블 삭제
2. `erp_build_step_runner.py` 경로까지 같이 건드리기
3. gunicorn worker class를 같은 배포에서 동시에 변경
4. Measurement / Shipment 검색 semantics까지 한 번에 변경
5. 리전 변경만으로 해결될 것처럼 결론 내리기
6. **Phase 2 페이지네이션 전환 시 Python 검색을 DB 검색으로 먼저 전환하지 않고 limit만 걸기**

---

## 9. 최종 실행 순서

1. Phase 0 운영 사실 확인
2. Phase 1.1 `psycogreen` 적용
3. Phase 1.2 API build-step commit 제거 (commit 5회→1회)
4. Phase 1.3 jobs print→logger 8건 교체
5. Phase 1.4 save / parse latency 계측 추가
6. Phase 1.5 ERP Beta save 후 setTimeout 500ms 제거
7. Phase 1.6 Dashboard bulk apply 루프 내 commit 통합 (N+1회→1회)
8. Railway 배포 후 save / parse / bulk apply p95 확인
9. Phase 2.1 `erp_as_page` 페이지네이션 (🟢 바로)
10. Phase 2.2 `erp_dashboard` Python→DB 검색 전환 + 페이지네이션 (🟡 설계 후)
11. Phase 2.3 `erp_production_page` Python→DB 필터 전환 + 페이지네이션 (🟡 설계 후)
12. Railway 로그 재측정
13. 필요 시 Phase 3 착수

---

## 10. 최종 결론

이 문서는 검토용이 아니라 실행용이다.

최종 판정은 아래와 같다.

- 정확도: 높음 (주요 불일치 보정 완료)
- 실행 가능성: Phase 1 즉시 착수 가능. Phase 2는 AS 페이지만 즉시, 나머지 설계 선행
- 즉시 착수 우선순위: 명확
- 남은 위험: 운영값 확인이 필요한 worker / region 결정 + Phase 2 검색 전환 설계

결론: Phase 1부터 바로 실행해도 된다.

---

## 부록: 관련 문서

- `docs/evolution/ERP_BETA_SAVE_FLOW_GDM_AUDIT_2026-03-16.md` — build-step commit 상세 분석, before_flush 재진입 방어 설계
- `docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md` — B-6 항목 동일
