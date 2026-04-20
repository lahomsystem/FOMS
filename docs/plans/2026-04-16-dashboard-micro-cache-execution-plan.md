# Dashboard Micro-Cache Execution Plan
> 작성일: 2026-04-16 | 상태: 🟢 구현·검증 동기화 (DMC-F 2026-04-16)

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
Railway 배포 환경에서 체감이 가장 느린 서버 렌더링 대시보드(`orders`, `measurement`, `shipment`)에 대해, 비즈니스 의미를 바꾸지 않는 **Redis 기반 micro-cache layer**를 도입한다.  
이 캐시는 전체 HTML을 통째로 저장하지 않고, 각 페이지의 느린 **read-model slice**만 짧은 TTL로 저장해 첫 렌더와 반복 방문 모두를 빠르게 만든다.

### 1.2 기능 요구사항
1. `foms/web/orders/dashboard.py`의 느린 집계/보조 조회를 **slice cache**로 분리한다.
2. `foms/web/measurement/dashboard.py`의 panel/fallback/부가 payload 계산을 **slice cache**로 분리한다.
3. `foms/web/shipment/dashboard.py`의 panel/fallback/부가 payload 계산을 **slice cache**로 분리한다.
4. 캐시는 `REDIS_URL`이 있으면 Redis를 사용하고, 없으면 무해한 no-op/fallback 동작을 해야 한다.
5. 캐시는 **전체 HTML**이 아니라 다음과 같은 read-model만 저장해야 한다.
   - KPI/summary counts
   - panel rows / panel stats
   - attachment count map
   - assignee/options lookup map
   - expensive payload assembly 결과
6. 캐시 key는 **사용자/팀 권한 + 필터 파라미터 + 페이지 유형**을 반영해야 한다.
7. 쓰기 작업 없이도 일관성이 깨지지 않도록 **짧은 TTL(30~60초)** 을 기본값으로 사용한다.
8. event-based invalidation은 가능한 범위에서 추가하되, **TTL only로도 안전하게 동작**해야 한다.
9. hit/miss/compute time을 로그나 경량 메트릭으로 남겨, 실제 Railway에서 효과를 추적할 수 있어야 한다.

### 1.3 예외/제약 조건
- 전체 페이지 HTML 캐시는 금지한다. 사용자별 플래시 메시지/권한/템플릿 상태를 오염시키기 쉽다.
- 검색 의미를 바꾸는 쿼리 단순화는 이번 batch 범위가 아니다.
- `structured_data::text ILIKE` 자체를 제거하는 검색/인덱스 개선은 별도 tranche로 둔다.
- cache miss 시 결과는 **항상 기존 계산 경로와 동일**해야 한다.
- Redis 장애 시 페이지가 실패하면 안 된다. cache bypass + warning log로 내려와야 한다.
- **기능/권한/UI/정렬/필터 의미/페이지네이션 의미를 바꾸는 수정은 금지**한다.
- **DB schema 변경, migration 추가, index 추가, template 구조 변경은 이번 tranche 비대상**이다.
- 이번 tranche는 성능 범주 중에서도 **server-side page load latency**만 줄이는 작업이다.

## 2. Why — 왜 이 방식이 필요한가

### 2.1 현재 병목
- `start.sh`와 `app.py`의 cold-start 비용은 첫 요청/재배포 지연에 영향을 주지만, **대시보드 반복 방문** 자체를 빠르게 만들지는 못한다.
- 현재 느린 체감은 각 요청마다 반복되는 무거운 read query와 후처리에서 나온다.
- 대표 병목:
  - `foms/web/orders/dashboard.py`
    - `count()` + page query + candidate queries + attachment aggregation + assignee 조회 + payload assembly
  - `foms/web/measurement/dashboard.py`
    - `limit(500)` / `limit(1500)` fallback query + product item build + panel assembly
  - `foms/web/shipment/dashboard.py`
    - panel query + selectinload + payload 계산

### 2.2 왜 micro-cache인가
- 현재 페이지는 “조금 오래돼도 되는 read model”이 많다.
- 운영 사용자는 30~60초 이내의 panel count / dashboard summary stale tolerance를 대체로 받아들일 수 있다.
- Redis는 이미 Socket.IO, jobs, limiter 등에서 사용 중이므로 별도 인프라 추가 없이 도입할 수 있다.
- HTML cache보다 안전하고, query rewrite보다 빠르게 효과를 낼 수 있다.

## 3. How — 어떻게 만드는가

### 3.1 캐시 전략

#### 3.1.1 캐시 대상
1. Orders dashboard
   - summary counts
   - stage candidate order id sets
   - attachment count map
   - assignee/user option map
   - order detail payload assembly 결과
2. Measurement dashboard
   - panel rows
   - panel summary/stat card data
   - fallback row list
   - product items build 결과
3. Shipment dashboard
   - panel rows
   - panel summary/stat card data
   - fallback row list
   - attachment/product/date derived payload

#### 3.1.2 캐시 대상 제외
- 사용자별 flash message
- CSRF token
- template render 결과 전체
- 쓰기 endpoint 응답
- 권한 검사가 완료되기 전의 raw query object
- SQLAlchemy ORM 객체 자체
- request / session / current_user에 직접 연결된 mutable object

#### 3.1.3 TTL 정책
| 대상 | 기본 TTL | 비고 |
|------|----------|------|
| summary / counts | 30초 | 가장 안전한 기본 slice |
| panel rows | 30초 | 필터별 key 분리 필수 |
| attachment count map | 45초 | 업로드 직후 최대 45초 stale 허용 |
| assignee/options lookup | 60초 | 비교적 변동 적음 |
| payload assembly | 30초 | source row hash/ids 기반 key |

### 3.2 캐시 키 설계
- key prefix: `foms:dashcache:v1:<page>:<slice>:...`
- 포함 요소:
  - page name (`orders`, `measurement`, `shipment`)
  - current user id
  - role/team visibility fingerprint
  - query string normalized fingerprint
  - page number / tab / filter set
  - optional source ids hash
- key 생성 규칙:
  - 파라미터 정렬 후 canonical JSON 직렬화
  - hash는 SHA-256 앞부분 16~24자 사용
  - 텍스트 전체를 key에 직접 붙이지 않는다
  - key version(`v1`)은 payload schema가 바뀌면 명시적으로 올린다

### 3.3 기능 보존 계약
- cache hit / miss 여부와 무관하게 최종 template context의 **의미적 결과**는 동일해야 한다.
- 허용되는 차이:
  - 로그 라인
  - 캐시 hit/miss 메트릭
  - 최대 TTL 범위 안의 짧은 stale read
- 허용되지 않는 차이:
  - 노출 주문 수
  - 필터 결과
  - stage/panel count
  - assignee 표시 이름
  - attachment count
  - 정렬 순서
  - 페이지네이션 결과
  - 권한별 노출 범위

### 3.4 feature flag / fallback 계약
- env flag: `FOMS_DASHBOARD_MICRO_CACHE_ENABLED`
- 기본값:
  - `REDIS_URL` 있음 + flag truthy -> cache on
  - 그 외 -> cache bypass
- Redis read/write/deserialize 실패 시:
  - request는 실패시키지 않는다
  - warning log를 남긴다
  - uncached compute path로 즉시 fallback 한다
- **로그 없는 fail-open 금지**

### 3.5 무효화(invalidation) 전략

#### 3.5.1 1차 구현
- short TTL only
- event invalidation은 선택적 보강

#### 3.5.2 2차 보강
- 다음 변경 시 page family prefix invalidation helper 호출:
  - 주문 생성/수정/삭제
  - stage/status 이동
  - schedule date 변경
  - attachment 추가/삭제
  - assignee 변경
- invalidation 호출은 **성공적인 commit 이후** 경계에서만 수행한다.
- commit 전 invalidate는 금지한다.

#### 3.5.3 무효화 단위
- `orders` family
- `measurement` family
- `shipment` family
- 필요 시 `order:<id>` leaf bucket을 둘 수 있지만, 첫 batch에서는 family TTL 우선

#### 3.5.4 1차 write-path 후보
- attachment 변경 후보:
  - `foms/api/files/direct_upload.py`
  - `foms/api/files/order_routes.py`
  - `foms/api/drawing/erp_orders_drawing.py`
  - `foms/api/drawing/erp_orders_draftsman.py`
- order/stage/quest/date 변경 후보:
  - `foms/api/erp_orders_structured.py`
  - `foms/api/quest.py`
  - `foms/services/order_date_sync.py`
- 원칙:
  - 1차 pilot에서는 **read-path cache 도입이 먼저**다.
  - write-path invalidation은 read-path differential test가 green인 뒤에만 연다.

### 3.6 아키텍처 방향
- 새 공통 helper를 `foms/services/common/` 아래 추가한다.
- 권장 파일:
  - `foms/services/common/dashboard_cache.py`
- helper 역할:
  - Redis client resolve
  - JSON serialize/deserialize
  - cache key canonicalization
  - `get_or_compute()`
  - family invalidate
  - safe fallback logging
- 기존 Redis 사용 패턴 참고:
  - `foms/services/jobs/queue.py`
  - `foms/services/channel_security.py`
  - `foms/services/rate_limit.py`
- 기존 in-process TTL cache 패턴 참고:
  - `foms/api/notifications/__init__.py`
  - `foms/services/common/address_converter.py`
- helper는 **JSON-serializable DTO(dict/list/primitive)** 만 저장한다.
- helper 안에서 ORM object pickle/cache는 금지한다.

### 3.7 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/services/common/dashboard_cache.py` | 신규 공통 micro-cache helper 추가 |
| `foms/web/orders/dashboard.py` | 느린 slice를 helper 경유로 분리 |
| `foms/web/measurement/dashboard.py` | panel/fallback/payload slice cache 적용 |
| `foms/web/shipment/dashboard.py` | panel/fallback/payload slice cache 적용 |
| `foms/api/files/direct_upload.py` | attachment write 후 invalidate 보강 후보 |
| `foms/api/files/order_routes.py` | attachment 생성/삭제 후 invalidate 보강 후보 |
| `foms/api/drawing/erp_orders_drawing.py` | drawing attachment/status write 후 invalidate 보강 후보 |
| `foms/api/drawing/erp_orders_draftsman.py` | assignee/drawing receipt write 후 invalidate 보강 후보 |
| `foms/api/erp_orders_structured.py` | order/stage/structured_data write 후 invalidate 보강 후보 |
| `foms/api/quest.py` | quest/stage approval write 후 invalidate 보강 후보 |
| `foms/services/order_date_sync.py` | schedule/date sync 경유 invalidate 보강 후보 |
| `tests/` 하위 관련 모듈 | cache key/fallback/bypass/unit test 추가 |

### 3.8 비목표(Non-goal)
- `run_auto_init()` 부팅 경로 분리
- `layout_head`/`layout_scripts` 전역 자산 분리
- `structured_data::text ILIKE` 제거
- WDPlanner 번들 분할
- CDN/region 이전
- SQL rewrite / business rule rewrite
- pagination / filter UX 변경
- template 구조 개편
- migration / index 신설

### 3.9 Stop Rule
- 아래 중 하나라도 발생하면 batch를 멈추고 설계를 다시 연다.
  - cache 적용 전후 response context 의미가 달라짐
  - 권한/필터 범위가 섞일 가능성이 생김
  - DTO가 아닌 ORM/session object를 cache하려고 함
  - commit 이전 invalidation이 필요해짐
  - Redis 부재 시 graceful bypass가 불가능함
  - template/UI 수정 없이는 구현이 안 된다고 판명됨

## 4. Steps — 실행 단계

### 4.1 설계/계약 고정
- [x] `dashboard_cache.py` public API를 먼저 고정한다.
- [x] key canonicalization / TTL / fallback contract를 테스트로 잠근다.
- [x] `REDIS_URL` 부재/장애 시 bypass contract를 명시한다.
- [x] `FOMS_DASHBOARD_MICRO_CACHE_ENABLED` flag on/off contract를 고정한다.
- [x] cached/uncached 결과 동등성(differential) 테스트 전략을 먼저 만든다.

### 4.2 Orders pilot
- [x] `orders` dashboard에서 가장 비싼 slice 2~3개(summary, attachment map, assignee map)를 먼저 분리한다.
- [x] hit/miss/time log를 붙인다. (`compute_ms` 포함, §1.2.9)
- [x] 기능 결과가 기존과 동일한지 focused regression을 추가한다.
- [x] template 수정 없이 route/service 레벨에서만 pilot을 끝낸다.
- [x] `order_detail_payload_assembly` slice (`build_order_detail_payload_map`) 추가.

### 4.3 Measurement/Shipment 확장
- [x] `measurement` panel/fallback/product item slice cache를 붙인다. (`measurement_panel_assembly`, `measurement_product_items_build` + 명시 DTO 키)
- [x] `shipment` panel/fallback/payload slice cache를 붙인다. (`panel_aggregates` + `shipment_panel_derived_template_payloads`)
- [x] 각 페이지별 stale tolerance와 key fingerprint를 검증한다.
- [x] DTO 직렬화 경계가 불명확한 slice는 cache 대상에서 제외한다. (ORM 테이블 rows는 §3.1.2대로 비캐시)

### 4.4 Invalidation 보강
- [x] order/attachment/date write path에서 family invalidate hook을 추가한다.
- [x] event invalidation이 없는 경로에서도 TTL only로 안전한지 확인한다.
- [x] invalidate는 commit success 이후에만 실행되도록 증거를 남긴다.

### 4.5 실측 검증
- [ ] Railway 프로덕션에서 before/after 서버 응답 시간·p50/p95 스냅샷 첨부 (운영 메모 권장). **미첨부 시 본 tranche의 “운영 실측 closeout”은 선언하지 않는다.**
- [x] hit/miss/`compute_ms` 로그 샘플 — 로컬 pytest `test_get_or_compute_logs_compute_ms_hit_and_miss` + `docs/plans/2026-04-16-dmc-f7-local-evidence.md` 참고.
- [ ] 효과가 큰 페이지부터 다음 tranche 후보를 선정한다. (운영 지표 수집 후)
- [x] cache off 대비 cache on 기능 diff가 0인지 확인한다.

## 5. 검증 기준
- [x] `python -c "import app; print('APP_OK')"` 통과
- [x] `python tools/harness/verify_result.py --json` 통과
- [x] cache helper focused pytest 통과
- [x] dashboard focused pytest 통과
- [x] cache off / cache on differential test 통과
- [x] Redis 없는 환경에서 page 200 OK
- [x] Redis 있는 환경에서 hit/miss log 확인 (FakeRedis + `compute_ms` 로그)
- [ ] Orders dashboard before/after 서버 처리 시간 개선 확인 (Railway·prod 스냅샷 권장; 미수집 시 **[ ]** 유지)
- [ ] Measurement dashboard before/after 서버 처리 시간 개선 확인 (동일)
- [ ] Shipment dashboard before/after 서버 처리 시간 개선 확인 (동일)
- [x] migration / schema / template diff 없음

## 6. 구현 원칙
- Root cause fix only: HTML cache나 template shortcut으로 증상을 덮지 않는다.
- slice cache는 **읽기 모델 최적화**여야 한다.
- 결과 의미를 바꾸는 query filter simplification은 금지한다.
- cache layer는 제거 가능하고, business logic을 오염시키지 않는 얇은 보조 계층이어야 한다.
- cache hit 때문에 권한/필터가 섞이면 안 된다.
- 기능을 바꾸지 않고 속도만 개선해야 하므로, **semantic-preserving refactor + cache layer** 외 접근은 금지한다.
- stale tolerance는 TTL 범위 안의 읽기 시점 차이만 허용한다. business rule 변화는 허용하지 않는다.

## 7. 후속 우선순위
1. boot path 분리 (`start.sh` migration / `run_auto_init`)
2. global asset loading split (`layout_head`, `layout_scripts`)
3. search/index tranche (`structured_data` 검색용 평면 컬럼/GIN/trigram)
4. WDPlanner bundle split

## 8. 참고 자료
- `docs/plans/2026-04-16-dmc-f-run-record.md` — DMC-F 구현·검증 요약 (현재 truth)
- `docs/plans/2026-04-16-dmc-f7-local-evidence.md` — 로컬 hit/miss/`compute_ms` 동등 증거
- `docs/plans/2026-04-16-dmc-f7-railway-evidence.md` — Railway·prod 운영 로그·latency **붙여넣기 전용** (미첨부 시 §4.5 Railway 행은 [ ] 유지)
- `docs/plans/2026-04-16-dmc-c-closeout-run-record.md` — DMC-C 최종 마감 시도 (local verify + Railway blocker 기록)
- `docs/plans/performance-optimization-plan.md`
- `docs/plans/performance-optimization-plan-v2.md`
- `docs/plans/2026-03-19-performance-master-plan.md`
- `foms/web/orders/dashboard.py`
- `foms/web/measurement/dashboard.py`
- `foms/web/shipment/dashboard.py`
- `foms/services/app_init.py`
- `foms/platform/app_factory.py`
