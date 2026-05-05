# 출고 대시보드 AS 일정 추천 후속 수정 계획서
> 작성일: 2026-05-05 | 상태: 작성 완료 / 구현 전 정밀 감리 대상

## 0. 현상 요약

출고 대시보드 AS 일정 추천 기능은 1차 구현이 대부분 들어갔지만, 실제 사용 중 아래 문제가 확인됐다.

1. `AS일정 추천` 버튼을 누를 때마다 추천 계산이 완전히 다시 도는 것처럼 느리다.
2. 추천으로 AS 일정을 추가한 뒤 출고 대시보드에는 AS 행이 보이지만, 취소/삭제 버튼이 사용자가 보는 위치에 보이지 않는다.
3. 추천으로 추가한 AS 일정이 AS 대시보드의 `AS 방문일`에 바로 반영되지 않는 것처럼 보인다.

## 1. 현재 구현 리뷰

### 1.1 추천 조회 API

현재 추천 조회는 `POST /api/erp/shipment/as-recommendations`에서 수행된다.

확인한 흐름:
- `foms/api/shipment/recommendations.py`가 요청된 출고 `order_ids`를 다시 로드한다.
- AS 후보는 매 요청마다 `Order.status in ("AS", "AS_RECEIVED")` 조건으로 다시 조회한다. 코드의 `limit(800)`은 안전 상한일 뿐이며, 대상은 항상 조회 시점의 AS 미완료 전체다. 예를 들어 현재 deploy 서버 미완료가 56건이면 그 56건 전체를 매번 다시 읽는다는 뜻이다.
- 후보와 기준 출고건의 주소를 `recommend_nearby_schedules_for_targets()`에 넘긴다.
- `foms/services/schedule_recommendations.py`는 요청 단위로 주소 좌표를 만들고, 직선거리 상위 후보를 뽑은 뒤 Kakao Directions 기반 실제 경로 시간을 계산한다.
- 프론트는 현재 화면 출고건을 5건씩 chunk로 나누어 API를 순차 호출한다.

현재 장점:
- 최종 추천 기준은 직선거리가 아니라 Kakao Directions 응답의 실제 소요시간이다.
- `실제 n km / n분` 문구는 `calculate_route()`의 `summary.distance`, `summary.duration`에서 나온다.
- 추천 적용/취소 API는 이미 별도 endpoint로 있고, DB 변경은 트랜잭션으로 묶여 있다.

현재 한계:
- 추천 조회 결과, 좌표 결과, 실제 경로 결과가 영속 캐시되지 않는다.
- 같은 화면에서 버튼을 다시 눌러도 후보 조회와 외부 API 계산이 다시 수행된다.
- 출고 대시보드 일반 행에는 추천 연결 취소 액션이 없다.
- AS 상태 코드 정합성이 약하다. 추천 후보는 `AS`도 포함하지만 AS 대시보드 기본 조회는 `AS_RECEIVED`, `AS_COMPLETED`만 포함한다.

## 2. 근본 원인 분석

### 2.1 반복 클릭 시 매번 느린 원인

근본 원인:
- 추천 조회 API가 읽기 전용 요청이지만 계산량이 큰 외부 의존 작업을 매번 수행한다.
- 현재 캐시는 대시보드 패널용 `dashboard_cache`만 있고, AS 추천용 route/recommendation cache가 없다.
- `schedule_recommendations.py`의 `geo_map`과 `route_by_pair`는 요청 함수 내부 지역 변수라 요청이 끝나면 사라진다.
- 미완료 AS 후보 pool 자체도 요청마다 새로 구성한다. `56건`은 현재 deploy 서버의 예시 숫자일 뿐이며, 실제 대상은 조회 시점의 `AS`/`AS_RECEIVED` 전체다. 즉 미완료가 56건이면 56건 전체, 120건이면 120건 전체를 매번 다시 읽고 DTO/좌표 후보로 다시 조립한다.
- 프론트는 5건 chunk를 순차 호출하므로, 화면에 출고건이 많으면 버튼 클릭 1회가 여러 번의 외부 경로 계산 묶음으로 늘어난다.

결론:
- API 자체가 매번 새 계산을 하는 구조이므로 체감상 동일하게 느린 것이 정상이다.
- 근본 수정은 `미완료 AS 후보 pool 캐시`, `좌표 캐시`, `경로 캐시`, `날짜/출고건별 추천 결과 캐시`, `사전 계산/프리워밍`을 분리해서 넣는 것이다.

### 2.2 취소 버튼이 안 보이는 원인

근본 원인:
- 취소 API와 모달 내부 `추가된 AS 일정` 렌더링은 존재한다.
- 하지만 사용자가 추가 직후 보는 출고 대시보드 테이블의 AS 행에는 추천 연결 메타데이터 기반 취소 버튼이 없다.
- `refreshShipmentFragment()` 후 화면이 새로 그려지면 모달 내부 연결 목록보다 테이블 행이 더 눈에 띄는데, 테이블 행에서는 삭제 가능 여부를 표현하지 않는다.

결론:
- 기능은 일부 구현됐지만 UX 노출 위치가 사용자의 실제 작업 흐름과 맞지 않는다.
- 추천으로 생성된 AS 행 자체에 `추천 취소` 액션을 노출해야 한다.

### 2.3 AS 방문일 자동 반영이 안 보이는 원인

확인된 저장 흐름:
- `apply` API는 `structured_data.schedule.as_visit.date`에 기준 출고건 시공일을 저장한다.
- `OrderScheduleDate(kind="as_visit")`는 `order_date_sync`의 `before_flush` 리스너가 동기화한다.
- 출고 대시보드는 AS 행 조회 시 `OrderScheduleDate.kind == "as_visit"`를 사용하므로, 출고 대시보드에 AS 행이 나타난다면 일정 동기화 자체는 동작했을 가능성이 높다.

위험 지점:
- AS 대시보드는 기본 조회에서 `Order.status.in_(["AS_RECEIVED", "AS_COMPLETED"])`만 사용한다.
- 추천 후보/적용 API는 `AS_STATUSES = ("AS", "AS_RECEIVED")`로 `AS` 상태도 허용한다.
- 따라서 `AS` 상태 주문은 방문일이 저장되어도 AS 대시보드 기본 목록에서 빠질 수 있다.
- 적용 API 응답에는 `applied_date`가 내려오지만 AS 대시보드 캐시/fragment 갱신을 직접 보장하지 않는다.

결론:
- "방문일이 저장되지 않음"과 "AS 대시보드에서 보이지 않음"을 분리 검증해야 한다.
- 코드상 1차 의심은 상태 코드 불일치다. `AS` 상태 후보를 적용할 때 AS 대시보드가 읽는 상태와 맞추거나, AS 대시보드가 `AS`를 명시적으로 포함해야 한다.

## 3. 수정 목표

### 3.1 성능 목표

사용자가 같은 날짜/같은 화면에서 `AS일정 추천`을 반복 클릭할 때:
- 첫 클릭은 계산이 필요할 수 있다.
- 이후 클릭은 캐시 hit로 빠르게 모달을 띄운다.
- 페이지 로드 후 미완료 AS 일정과 현재 출고건에 대해 가능한 범위에서 미리 계산한다.
- Kakao Directions API 호출은 같은 주소쌍에 대해 반복되지 않도록 줄인다.

### 3.2 UX 목표

추천으로 추가된 AS 일정은:
- 모달의 `추가된 AS 일정` 영역에서 취소 가능해야 한다.
- 출고 대시보드 테이블에 나타난 AS 행에서도 취소 가능해야 한다.
- 취소 시 AS 방문일과 추천 연결 메타데이터가 함께 제거되어야 한다.

### 3.3 데이터 정합성 목표

추천 적용 시:
- 출고 대시보드 해당 일자에 AS 행이 표시된다.
- AS 대시보드 `AS 방문일`에도 같은 날짜가 표시된다.
- `AS` / `AS_RECEIVED` 상태 차이 때문에 사용자가 못 찾는 일이 없어야 한다.

## 4. 수정 설계

### 4.0 구현자용 고정 결정

다른 LLM/개발자가 바로 구현할 수 있도록 아래 결정은 더 이상 열린 선택지로 두지 않는다.

| 항목 | 결정 |
|------|------|
| DB schema | 변경하지 않는다. 캐시는 Redis/process memory TTL만 사용한다. |
| 백그라운드 worker | 이번 수정에서는 추가하지 않는다. 페이지 진입 기반 lazy prewarm endpoint로 해결한다. |
| 실제 거리/시간 | 계속 Kakao Directions `calculate_route()` 결과만 "실제"로 표시한다. 직선거리는 route 후보 선별용이다. |
| AS 상태 정합성 | 추천 적용 시 status를 강제로 바꾸지 않는다. AS 대시보드가 `AS` 상태도 읽게 한다. |
| 캐시 저장 값 | ORM 객체 금지. JSON 직렬화 가능한 DTO만 저장한다. |
| Redis 장애 | warning log 후 계산 경로로 fallback한다. 사용자는 오류를 보지 않는다. |
| 개인정보 key | Redis key에는 주소 원문을 넣지 않는다. 주소/좌표는 hash로만 key화한다. |
| 구현 범위 | candidate pool cache + route cache + target cache + prewarm + 테이블 취소 버튼 + AS 상태 조회 보정까지 한 번에 구현한다. |

### 4.0.1 목표 데이터 흐름

```text
출고 대시보드 fragment 로드
    │
    ├─ JS idle prewarm
    │    │
    │    └─ POST /api/erp/shipment/as-recommendations/prewarm
    │         │
    │         ├─ get_or_compute_candidate_pool()
    │         │    ├─ cache hit  → 미완료 AS 후보 DTO 즉시 반환
    │         │    └─ cache miss → AS/AS_RECEIVED 주문 조회 + 좌표 보강 + DTO cache
    │         │
    │         └─ get_or_compute_target_recommendations()
    │              ├─ target cache hit  → 종료
    │              └─ target cache miss → route_provider()
    │                    ├─ route cache hit  → Kakao 호출 없음
    │                    └─ route cache miss → Kakao Directions 호출 후 route cache 저장
    │
    └─ 사용자가 AS일정 추천 클릭
         │
         └─ POST /api/erp/shipment/as-recommendations
              ├─ candidate pool cache 재사용
              ├─ target recommendation cache 재사용
              └─ 모달 payload 반환

추천 추가/취소/AS 수정
    │
    ├─ DB commit 성공
    ├─ dashboard cache invalidate
    └─ shipment AS recommendation cache invalidate
```

### 4.0.2 수정 파일 목록

| 파일 | 작업 |
|------|------|
| `foms/services/shipment_as_recommendation_cache.py` | 신규. candidate pool, route, target recommendation cache 함수 구현 |
| `foms/services/schedule_recommendations.py` | `route_provider` 선택 인자 추가. 기존 호출 하위 호환 유지 |
| `foms/api/shipment/recommendations.py` | 후보 조회를 cache service로 이동, prewarm endpoint 추가, apply/cancel 후 cache invalidate |
| `foms/web/shipment/dashboard.py` | 추천으로 연결된 AS 행에 `shipment_as_recommendation_link` DTO 부착 |
| `templates/shipment/partials/dashboard_main.html` | AS일정 prewarm JS, 출고 테이블 추천 취소 버튼, cancel handler 전역화 |
| `foms/web/cs/as_dashboard.py` | AS 대시보드 기본 조회/미완료 조건에 `AS` 상태 포함 |
| `foms/api/cs/as_orders.py` | AS start/register/schedule/complete 성공 commit 후 추천 cache invalidate |
| `foms/api/orders/field_update.py` | `as_visit_date`, `status`, `address` 등 추천 영향 필드 commit 후 추천 cache invalidate |
| `tests/domains/test_shipment_as_recommendations.py` | cache/prewarm/apply/cancel 동기화 테스트 보강 |
| `tests/domains/test_erp_mobile_layout_and_shipment.py` | 버튼/JS/템플릿 계약 테스트 보강 |

추가 금지:
- 새 DB table
- Celery/RQ 같은 새 worker
- 외부 API provider 추가
- 추천 적용 시 AS 상태 자동 변경

### 4.1 미완료 AS 후보 pool 사전 계산

신규 파일:
- `foms/services/shipment_as_recommendation_cache.py`

핵심 방향:
- "AS 미완료 전체 후보"는 버튼 클릭 시마다 만들지 않고, 별도 read-model로 미리 만들어 둔다.
- 조회 시점의 미완료 AS 전체를 정규화한 후보 pool로 만들고 Redis/process TTL cache에 저장한다. 현재 deploy 서버의 56건은 예시일 뿐이며 고정값이 아니다.
- 출고 대시보드 날짜별 추천 조회는 이 후보 pool을 즉시 가져와서, 해당 날짜의 출고 row들과 매칭만 수행한다.

미완료 AS 후보 pool DTO:
```json
{
  "pool_version": "hash",
  "computed_at": "2026-05-05T10:00:00",
  "candidates": [
    {
      "order_id": 2440,
      "customer_name": "양의석",
      "address": "송파구 ...",
      "lat": 37.0,
      "lng": 127.0,
      "current_visit_date": "",
      "status": "AS_RECEIVED",
      "sort_date": "2026-03-20",
      "as_info_id": 1,
      "linked_shipment_order_id": null
    }
  ]
}
```

pool fingerprint:
- 후보 AS order id 목록
- status
- 주소/좌표 hash
- 현재 AS 방문일
- `as_info` open 항목 hash
- 추천 연결 메타데이터 hash
- `structured_updated_at`
- `structured_updated_at`이 비어 있으면 `created_at`과 DTO 내용 hash를 함께 사용한다. `Order`에는 일반 `updated_at` 컬럼이 없으므로 `updated_at`을 참조하지 않는다.

갱신 타이밍:
- AS 접수/수정/완료/취소 API commit 후 pool cache invalidate
- 주소/AS 방문일/AS 내용/AS 상태 변경 후 pool cache invalidate
- Redis가 있으면 invalidation 후 다음 요청 또는 prewarm이 재계산
- Redis가 없으면 process-local TTL로 짧게 유지

주의:
- 후보 pool은 "AS 쪽 준비물"일 뿐이다.
- 실제 추천은 출고건 주소/시공일/시공자와의 pair 계산이 필요하므로, AS pool만으로 최종 추천을 완전히 확정할 수는 없다.
- 따라서 구조는 `AS 후보 pool 사전 계산` + `날짜별 출고건 pair 추천 사전 계산`의 2단계가 맞다.

### 4.1.1 cache service 함수 계약

`foms/services/shipment_as_recommendation_cache.py`에 아래 함수를 만든다. class는 만들지 않는다. 이번 기능은 함수형 helper면 충분하다.

```python
KEY_VERSION = "v1"
KEY_PREFIX = f"foms:asrec:{KEY_VERSION}"

TTL_CANDIDATE_POOL_SECONDS = 300
TTL_TARGET_SECONDS = 600
TTL_ROUTE_SUCCESS_SECONDS = 7 * 24 * 60 * 60
TTL_ROUTE_FAILURE_SECONDS = 60
TTL_LOCK_SECONDS = 30

def is_asrec_cache_enabled() -> bool:
    """기본 true. FOMS_SHIPMENT_AS_REC_CACHE_ENABLED=false일 때만 완전 bypass."""

def build_hash(value: Any) -> str:
    """정렬 JSON + SHA256 앞 20자. 주소 원문 key 노출 방지."""

def get_or_compute_candidate_pool(
    db,
    converter,
    *,
    source_value: str,
    as_statuses: tuple[str, ...],
    log_warning=None,
) -> tuple[dict, dict]:
    """
    Return:
      pool = {"pool_version": str, "computed_at": str, "candidates": list, "link_as_to_shipment": dict}
      stats = {"candidate_pool_hit": bool, "candidate_count": int}
    """

def make_route_provider(converter, stats: dict, *, log_warning=None):
    """
    반환 callable:
      route_provider(slat, slng, elat, elng, timeout=None) -> dict
    route cache hit이면 converter.calculate_route() 호출 금지.
    """

def get_cached_target(cache_key: str) -> dict | None:
    """target recommendation cache hit면 target payload 반환."""

def set_cached_target(cache_key: str, target_payload: dict) -> None:
    """JSON DTO만 저장. 실패는 warning 후 무시."""

def build_target_cache_key(target: dict, pool_version: str, rule_version: str) -> str:
    """shipment_order_id + target fingerprint + pool_version + rule_version."""

def invalidate_shipment_as_recommendation_cache(*, reason: str = "") -> int:
    """foms:asrec:v1:* 전체 삭제. Redis/process cache 모두 제거."""
```

Redis 연결:
- `foms.services.common.dashboard_cache.get_dashboard_redis()`를 재사용한다.
- 단, `FOMS_DASHBOARD_MICRO_CACHE_ENABLED` 플래그에는 묶지 않는다. AS 추천 캐시는 별도 기능이므로 `REDIS_URL`이 있으면 사용한다.
- 새 플래그 `FOMS_SHIPMENT_AS_REC_CACHE_ENABLED`만 본다. 값이 `false/0/no/off`면 Redis와 process cache 모두 bypass한다.
- Redis가 없으면 process-local dict + `threading.RLock` + expires_at 방식으로 TTL cache를 사용한다.

lock:
- Redis 사용 가능: `SET key value NX EX 30`으로 candidate pool/target prewarm 중복 계산 방지
- Redis 없음: process-local lock set 사용
- lock 획득 실패 시 stale cache가 있으면 stale 반환, 없으면 현재 요청은 직접 계산한다.

### 4.1.2 candidate pool builder 세부 규칙

`get_or_compute_candidate_pool()`의 cache miss 계산은 현재 `foms/api/shipment/recommendations.py`의 `cand_query` 블록을 서비스 함수로 옮기는 작업이다.

호출 예:
```python
pool, pool_stats = get_or_compute_candidate_pool(
    db,
    converter,
    source_value=SHREC_SOURCE,
    as_statuses=AS_STATUSES,
    log_warning=logger.warning,
)
```

쿼리:
```python
db.query(Order).options(load_only(
    Order.id,
    Order.status,
    Order.deleted_at,
    Order.address,
    Order.is_erp_order,
    Order.structured_data,
    Order.customer_name,
    Order.lat,
    Order.lng,
    Order.geocode_status,
    Order.structured_updated_at,
    Order.created_at,
)).filter(
    Order.status.in_(("AS", "AS_RECEIVED")),
    Order.active_filter(),
).order_by(Order.id.desc()).limit(800)
```

DTO 생성:
- `get_order_display_address(order)`가 빈 값이면 제외
- `get_order_display_customer_name(order)` 사용
- `current_visit_date = structured_data.schedule.as_visit.date`
- `as_info_id`: open AS 항목이 정확히 1개일 때만 id 설정, 여러 개면 `None` + `as_info_ambiguous=True`
- `linked_shipment_order_id`: `structured_data.schedule.as_visit.shipment_recommendation.source == SHREC_SOURCE`일 때 추출
- `cached_lat/cached_lng`: DB 좌표가 success면 사용
- DB 좌표가 없으면 `converter.analyze_address()`로 보강하되 DB에는 쓰지 않는다.

pool output:
```python
{
    "pool_version": build_hash({
        "rule": "candidate_pool_v1",
        "orders": [...candidate fingerprints...],
    }),
    "computed_at": now_iso,
    "candidates": candidates_in,
    "link_as_to_shipment": {"2440": 2052}
}
```

주의:
- `link_as_to_shipment`는 JSON 저장 시 key가 문자열이 될 수 있으므로 API에서 사용할 때 `int(k)`로 정규화한다.
- candidate pool cache가 stale하면 이미 방문일이 바뀐 AS가 추천될 수 있다. 이를 막기 위해 apply API는 기존처럼 현재 DB를 다시 읽고 conflict를 검증한다.

### 4.2 추천 캐시 계층 추가

책임:
- 미완료 AS 후보 pool 조회/저장
- 주소 좌표 캐시 조회/저장
- 실제 경로 결과 캐시 조회/저장
- 날짜/출고건별 추천 결과 캐시 조회/저장
- 캐시 key fingerprint 생성
- 적용/취소/AS 변경 시 무효화 hook 제공

캐시 저장소:
- 1순위: 기존 `dashboard_cache`와 동일한 Redis 연결 사용
- 2순위: Redis 비활성 시 process-local TTL cache
- Redis 장애 시 계산 경로로 fail-open하되 warning log를 남긴다.

캐시 key 설계:
- AS candidate pool cache:
  - `foms:asrec:v1:candidate_pool:<pool_fp>`
  - 별칭 key: `foms:asrec:v1:candidate_pool:latest`
  - TTL: 5분. AS 변경 commit 후 explicit invalidation도 수행한다.
  - value: 미완료 AS 후보 DTO 목록
- route cache:
  - `foms:asrec:v1:route:<origin_coord_hash>:<dest_coord_hash>`
  - TTL: 7일
  - value: `{status, distance_km, duration_min, provider, computed_at}`
- target recommendation cache:
  - `foms:asrec:v1:target:<shipment_order_id>:<target_fp>:<candidate_pool_fp>:<rule_version>`
  - TTL: 10분
  - value: target 1건의 추천 payload
- batch response cache:
  - 구현하지 않는다. 1차 구현에서는 target cache를 조합해 batch 응답을 만든다.

fingerprint 구성:
- 기준 출고건:
  - order id
  - 시공일
  - 정규화 주소 hash
  - 좌표가 있으면 좌표 hash
  - 시공자 목록 hash
- AS 후보 pool:
  - 위 `pool_version`을 그대로 포함한다.
- 추천 rule version:
  - duration limit 30분
  - per target limit 2
  - route 후보 상한

주의:
- 캐시에는 ORM 객체를 저장하지 않고 JSON DTO만 저장한다.
- 외부 API 실패 fallback 결과는 짧은 TTL만 허용한다. 예: 1분.
- 성공 route 결과는 길게 캐시한다.

### 4.3 날짜별 출고건 pair 추천 프리워밍 전략

1차 구현은 DB migration 없이 lazy prewarm으로 간다.

프론트:
- 출고 대시보드 페이지/fragment 로드 후 `requestIdleCallback` 또는 `setTimeout`으로 현재 화면의 일반 출고건 order id를 모은다.
- `POST /api/erp/shipment/as-recommendations/prewarm`를 5건 chunk로 호출한다.
- prewarm은 UI를 막지 않는다.
- prewarm은 먼저 미완료 AS candidate pool cache를 읽고, 없으면 pool부터 계산한다.
- 그 다음 현재 날짜의 출고건별로 route/target recommendation cache를 채운다.
- 사용자가 버튼을 누르면 기존 조회 API를 호출하되, 날짜/출고건별 cache hit가 있으면 즉시 반환된다.

백엔드:
- `prewarm` endpoint는 추천 조회와 같은 권한을 사용한다.
- 응답은 `{success, warmed_targets, candidate_pool_hit, candidate_count, target_hits, target_misses, route_hits, route_misses}`를 반환한다.
- prewarm은 DB를 변경하지 않는다.
- prewarm 중 같은 key가 이미 계산 중이면 중복 계산을 피한다. Redis `SET NX EX` 또는 process lock을 사용한다.

이번 범위 밖:
- AS 접수 등록/주소 변경/방문일 취소 이벤트 후 background worker prewarm
- 운영 DB에 추천 결과 테이블 저장
- 브라우저가 아닌 서버 cron 기반 상시 계산

### 4.4 추천 조회 API 변경

`foms/api/shipment/recommendations.py`

변경 방향:
- `SHREC_SOURCE`, `AS_STATUSES`, `SHIPMENT_AS_ROW_STATUSES`는 이 파일에 유지한다. cache service에는 문자열 값을 직접 import하지 않게 하고, pool builder에는 `source_value=SHREC_SOURCE`, `as_statuses=AS_STATUSES`를 인자로 넘긴다. 이렇게 하면 순환 import를 피한다.
- 후보 AS 조회 로직은 `get_or_compute_candidate_pool()`로 이동한다.
- 추천 조회 API는 매번 DB에서 AS 후보를 직접 조립하지 않고, precomputed candidate pool을 가져온다.
- candidate pool cache miss일 때만 조회 시점의 미완료 AS 전체 pool을 DB에서 다시 읽고 좌표/DTO를 만든다.
- 후보 pool fingerprint를 target recommendation cache key에 포함한다.
- target별로 캐시 조회를 먼저 한다.
- cache miss target만 `recommend_nearby_schedules_for_targets()`에 넘긴다.
- route 계산 시 route cache를 사용할 수 있도록 서비스에 route resolver/callback을 주입한다.
- 응답에 관측 필드를 추가한다.

응답 예:
```json
{
  "success": true,
  "cache": {
    "candidate_pool_hit": true,
    "candidate_count": 56,
    "target_hits": 4,
    "target_misses": 1,
    "route_hits": 8,
    "route_misses": 2,
    "prewarmed": true
  },
  "targets": []
}
```

호환성:
- 기존 프론트가 `targets`, `warnings`, `partial`만 봐도 동작하도록 새 필드는 additive로만 추가한다.

### 4.4.1 API 내부 함수 구조

`api_shipment_as_recommendations()`와 prewarm endpoint가 같은 내부 함수를 호출하게 한다.

```python
def _build_targets_for_order_ids(db, order_ids: list[int]) -> list[dict]:
    """현재 API의 shipment_orders → targets_in 조립 로직 유지."""

def _compute_recommendation_payload(
    *,
    db,
    order_ids: list[int],
    selected_date: str | None,
    return_targets: bool,
) -> dict:
    """
    1. targets 조립
    2. candidate pool get_or_compute
    3. target cache hit/miss 분리
    4. miss targets만 recommend_nearby_schedules_for_targets() 호출
    5. target별 cache 저장
    6. linked_as_schedules 보강
    """
```

target cache 처리:
- `rule_version = "shipment_asrec_target_v1:duration30:limit2:route10"`
- target별 cache key는 `build_target_cache_key(target, pool_version, rule_version)`
- hit target은 그대로 결과에 넣는다.
- miss target이 있으면 miss target 목록만 `recommend_nearby_schedules_for_targets()`에 넘긴다.
- 저장 전 target payload에 `linked_as_schedules`는 넣지 않는다. 연결 목록은 candidate pool의 최신 `link_as_to_shipment` 기준으로 응답 직전에 보강한다.
- cache hit target에도 `_enrich_recommendations()`를 다시 적용한다. AS가 다른 출고에 연결된 상태가 바뀌었을 수 있기 때문이다.

prewarm endpoint:
```python
@erp_shipment_bp.route("/api/erp/shipment/as-recommendations/prewarm", methods=["POST"])
@login_required
@erp_edit_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def api_shipment_as_recommendations_prewarm():
    ...
    payload = _compute_recommendation_payload(..., return_targets=False)
    return jsonify({"success": True, "cache": payload["cache"]})
```

조회 endpoint:
```python
payload = _compute_recommendation_payload(..., return_targets=True)
return jsonify({
    "success": True,
    "per_target_limit": 2,
    "duration_limit_min": 30,
    "partial": payload["partial"],
    "warnings": payload["warnings"],
    "cache": payload["cache"],
    "targets": payload["targets"],
})
```

### 4.5 추천 서비스 변경

`foms/services/schedule_recommendations.py`

변경 방향:
- 현재 함수의 기본 동작은 유지한다.
- 선택적 `route_provider` 파라미터만 추가한다.
- 기본값이 없으면 지금처럼 `converter.calculate_route()`를 직접 호출한다.
- route cache가 있으면 같은 좌표쌍은 외부 API 호출 없이 즉시 재사용한다.

권장 인터페이스:
```python
def recommend_nearby_schedules_for_targets(
    *,
    converter,
    targets,
    candidates,
    route_provider=None,
    ...
):
    ...
```

`route_provider`는 `(slat, slng, elat, elng, timeout) -> dict` 형태로 둔다.

구현 포인트:
- `route_provider` 기본값은 `None`이다.
- `None`이면 기존 코드 그대로 `converter.calculate_route(...)` 호출한다.
- `run_route()` 안에서만 변경한다.

변경 전:
```python
info = converter.calculate_route(slat, slng, elat, elng, timeout=route_timeout_sec)
```

변경 후:
```python
provider = route_provider or converter.calculate_route
info = provider(slat, slng, elat, elng, timeout=route_timeout_sec)
```

테스트 호환:
- 기존 `_StubRouteConverter.calculate_route(..., timeout=None)` 테스트는 그대로 통과해야 한다.
- 새 테스트에서는 `route_provider`를 주입해 provider 호출 횟수를 검증한다.

### 4.6 출고 테이블 취소 버튼 추가

`foms/web/shipment/dashboard.py`

변경 방향:
- rows 후처리 단계에서 AS 행의 `structured_data.schedule.as_visit.shipment_recommendation`을 읽는다.
- `source == "shipment_dashboard_as_recommendation"`이면 `r.shipment_as_recommendation_link` DTO를 붙인다.

DTO 예:
```python
r.shipment_as_recommendation_link = {
    "shipment_order_id": 2052,
    "as_order_id": r.id,
    "as_info_id": 1,
    "applied_date": "2026-05-05",
}
```

`templates/shipment/partials/dashboard_main.html`

변경 방향:
- AS 행의 첫 번째 `상세` 칸에 `추천 취소` 버튼을 표시한다.
- 버튼은 작은 outline-danger icon button으로 둔다.
- 이미 수동 변경된 경우 서버가 409를 반환하므로, 모달 내부 cancel은 inline 오류, 테이블 cancel은 `window.alert()`로 메시지를 표시한다.

권장 위치:
- 첫 번째 `상세` 셀 내부, 주문 상세 버튼 바로 아래
- 모바일 카드에서도 같은 액션이 보이도록 data-label 내부에 포함

JS:
- 모달 내부에만 묶인 cancel click handler를 일반 문서 레벨 handler로 확장한다.
- `.js-shipment-as-rec-cancel` 버튼은 모달/테이블 양쪽에서 같은 API를 호출한다.
- 성공 후 `refreshShipmentFragment({bypassCache:true})`를 호출한다.

현재 JS의 주의 지점:
```javascript
var modalRoot = ev.target.closest && ev.target.closest('#shipmentAsRecommendModal');
if (!modalRoot) return;
...
var cancelBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-cancel');
```

이 구조에서는 테이블 안의 cancel 버튼이 무시된다.

수정 구조:
```javascript
var cancelBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-cancel');
if (cancelBtn) {
  // 모달/테이블 공통 처리
  ...
  return;
}

var modalRoot = ev.target.closest && ev.target.closest('#shipmentAsRecommendModal');
if (!modalRoot) return;

// apply는 모달 안에서만 처리
```

prewarm JS:
- 같은 IIFE 안에 `scheduleShipmentAsRecPrewarm()` 추가
- `collectTargetOrderIds()`를 재사용
- `sessionStorage` key: `shipment-asrec-prewarm:` + `location.pathname + location.search + ":" + ids.join(",")`
- 이미 같은 key를 prewarm 했으면 같은 fragment 생명주기 안에서는 재요청하지 않는다.
- `requestIdleCallback`이 있으면 사용하고, 없으면 `setTimeout(fn, 800)` 사용
- `foms:main-content-swapped` 이벤트 후에도 `scheduleShipmentAsRecPrewarm()` 호출
- 실패는 console warning만 남기고 UI status는 건드리지 않는다.

### 4.7 AS 방문일 표시 정합성 수정

우선 검증:
- 적용 후 DB에서 해당 AS order의 `structured_data.schedule.as_visit.date` 확인
- `OrderScheduleDate(kind="as_visit")` row 확인
- AS 대시보드 query가 해당 order를 포함하는지 확인

고정 수정:
- `foms/web/cs/as_dashboard.py`의 `base_query` 상태 조건을 `["AS", "AS_RECEIVED", "AS_COMPLETED"]`로 확장한다.
- `_erp_as_incomplete_condition()`도 `Order.status.in_(["AS", "AS_RECEIVED"])`를 미완료로 본다.
- `_erp_as_completed_condition()`은 그대로 둔다.
- 추천 적용 대상이 `AS` 상태여도 `AS_RECEIVED`로 승격하지 않는다.
- `as_received_date`를 자동으로 채우지 않는다.

추가 보강:
- apply/cancel commit 후 `invalidate_all_dashboard_slice_caches()`를 명시적으로 호출한다. 기존 `order_date_sync` listener가 있어도 중복 invalidation은 허용한다.
- `apply` 응답에 `as_visit_date`와 `status`를 내려 프론트/테스트에서 명확히 검증한다.

### 4.8 cache invalidation 지도

추천 cache는 stale이어도 apply/cancel에서 DB 재검증을 하므로 데이터 손상 위험은 낮다. 그래도 사용자 체감과 중복 추천을 줄이려면 아래 경로에서 invalidate를 호출한다.

공통 helper:
```python
def _invalidate_asrec_after_commit(reason: str) -> None:
    try:
        invalidate_shipment_as_recommendation_cache(reason=reason)
    except Exception:
        logger.warning("[AS-REC] cache invalidate failed", exc_info=True)
```

호출 위치:
- `foms/api/shipment/recommendations.py`
  - apply `db.commit()` 성공 직후
  - cancel `db.commit()` 성공 직후
- `foms/api/cs/as_orders.py`
  - `api_as_start()` commit 성공 직후
  - `api_as_complete()` commit 성공 직후
  - `api_as_register()` commit 성공 직후
  - `api_as_schedule()` commit 성공 직후
- `foms/api/orders/field_update.py`
  - `field in {"as_visit_date", "status", "address", "manager_name", "as_content", "as_content_2", "sales_delivery"}` 이거나
  - 변경 대상 order의 status가 `AS`/`AS_RECEIVED`/`AS_COMPLETED`였으면 commit 성공 직후
- `foms/api/shipment/settings.py`
  - payload에 `construction_workers`가 포함된 저장 commit 성공 직후 invalidate

원칙:
- invalidate 실패는 저장 실패로 만들지 않는다.
- cache invalidate는 반드시 commit 성공 후 호출한다. rollback되는 변경을 기준으로 cache를 지우지 않는다.

### 4.9 구현 전 확인 명령

구현 시작 직전 다른 LLM은 아래를 먼저 확인한다.

```powershell
git status --short --branch
rg -n "as-recommendations|shipment_recommendation|AS_STATUSES|SHIPMENT_AS_ROW_STATUSES" foms templates tests
rg -n "as_visit_date|_erp_as_incomplete_condition|base_query = db.query\\(Order\\)" foms/web/cs/as_dashboard.py foms/api/orders/field_update.py
```

구현 후 최소 검증:
```powershell
python -m pytest tests/domains/test_shipment_as_recommendations.py -q
python -m pytest tests/domains/test_erp_mobile_layout_and_shipment.py -q
python -m pytest tests/domains/test_dashboard_cache.py -q
```

## 5. 테스트 계획

### 5.0 coverage diagram

```text
CODE PATH COVERAGE TARGET
=========================
[+] foms/services/shipment_as_recommendation_cache.py
    │
    ├── is_asrec_cache_enabled()
    │   ├── [GAP] enabled by default
    │   └── [GAP] false/off env bypasses Redis + local cache
    │
    ├── get_or_compute_candidate_pool()
    │   ├── [GAP] cache miss builds AS/AS_RECEIVED pool from DB
    │   ├── [GAP] cache hit returns without rebuilding DB DTO
    │   ├── [GAP] no address candidate excluded
    │   ├── [GAP] DB cached lat/lng reused
    │   ├── [GAP] missing lat/lng calls analyze_address once and does not write DB
    │   ├── [GAP] linked_shipment_order_id extracted from shipment_recommendation meta
    │   └── [GAP] Redis failure logs warning and computes
    │
    ├── make_route_provider()
    │   ├── [GAP] route cache miss calls converter.calculate_route once and stores result
    │   ├── [GAP] route cache hit does not call Kakao/converter
    │   ├── [GAP] success route TTL is long
    │   └── [GAP] error route TTL is short
    │
    └── target cache helpers
        ├── [GAP] target cache key changes when target workers/date/address changes
        ├── [GAP] target cache key changes when candidate pool version changes
        └── [GAP] invalidation clears Redis + process-local cache

[+] foms/services/schedule_recommendations.py
    │
    └── recommend_nearby_schedules_for_targets(route_provider=None)
        ├── [EXISTING] default converter path keeps current tests passing
        ├── [GAP] injected route_provider is used for all route jobs
        └── [GAP] over-30min and fallback behavior remain unchanged

[+] foms/api/shipment/recommendations.py
    │
    ├── POST /api/erp/shipment/as-recommendations
    │   ├── [EXISTING] auth/role/order_ids validation
    │   ├── [GAP] candidate_pool cache metadata returned
    │   ├── [GAP] target cache hit skips recommendation compute
    │   ├── [GAP] target cache miss computes and stores target payload
    │   └── [GAP] cached target still receives fresh linked_as_schedules enrichment
    │
    ├── POST /api/erp/shipment/as-recommendations/prewarm
    │   ├── [GAP] auth/role/order_ids validation mirrors main endpoint
    │   ├── [GAP] DB write count is zero
    │   └── [GAP] returns cache stats without targets
    │
    ├── apply
    │   ├── [EXISTING] force conflict handling
    │   ├── [GAP] OrderScheduleDate(kind=as_visit) exists after commit
    │   ├── [GAP] response includes as_visit_date/status
    │   └── [GAP] asrec cache invalidated after commit
    │
    └── cancel
        ├── [EXISTING] wrong shipment/manual date/as_info mismatch protected
        ├── [GAP] OrderScheduleDate(kind=as_visit) removed after commit
        └── [GAP] asrec cache invalidated after commit

[+] foms/web/shipment/dashboard.py + templates/shipment/partials/dashboard_main.html
    │
    ├── [GAP] AS row with shipment_recommendation meta renders 추천 취소
    ├── [GAP] AS row without recommendation meta does not render 추천 취소
    ├── [GAP] cancel handler works outside modal
    └── [GAP] prewarm JS is present and uses existing collectTargetOrderIds()

[+] foms/web/cs/as_dashboard.py
    │
    ├── [GAP] AS status appears in incomplete tab
    └── [GAP] AS_COMPLETED completed tab behavior unchanged

USER FLOW COVERAGE TARGET
=========================
[+] Repeated recommendation click
    ├── [GAP] First click/prewarm computes
    ├── [GAP] Second click returns cache hit metadata
    └── [GAP] route provider/converter call count does not repeat

[+] Add recommendation
    ├── [GAP] 출고 대시보드 selected date shows AS row
    ├── [GAP] AS 대시보드 shows AS 방문일
    └── [GAP] table row shows 추천 취소

[+] Cancel recommendation
    ├── [GAP] table 추천 취소 calls cancel API
    ├── [GAP] 출고 대시보드 selected date removes AS row
    └── [GAP] AS 대시보드 AS 방문일 becomes blank
```

### 5.1 단위/도메인 테스트

`tests/domains/test_shipment_as_recommendations.py`

추가/보강:
- `test_candidate_pool_cache_hit_skips_rebuild`
  - AS_RECEIVED 후보 1건 생성
  - 첫 호출은 `candidate_pool_hit=False`
  - 두 번째 호출은 `candidate_pool_hit=True`
  - monkeypatch로 pool builder 호출 횟수 1회 검증
- `test_candidate_pool_includes_as_status`
  - status `AS` 후보와 `AS_RECEIVED` 후보를 만들고 둘 다 pool에 포함되는지 검증
- `test_route_provider_cache_hit_skips_converter`
  - 같은 좌표쌍 route provider 2회 호출
  - converter `calculate_route` 호출 횟수 1회 검증
- `test_route_provider_error_uses_short_ttl`
  - error route 저장 후 stats에 failure 저장이 기록되는지 검증
- `test_target_cache_key_changes_when_workers_change`
  - 같은 order/date/address에서 workers만 바꾸면 target key가 달라지는지 검증
- `test_prewarm_endpoint_returns_cache_stats_without_targets`
  - `POST /api/erp/shipment/as-recommendations/prewarm`
  - `success=True`, `cache` 존재, `targets` 없음
- `test_recommendations_after_prewarm_reports_target_hit`
  - prewarm 호출 후 조회 endpoint 호출
  - `cache.target_hits >= 1`
- `test_cached_target_gets_fresh_linked_schedule_enrichment`
  - target payload를 cache에 저장한 뒤 AS 연결 메타데이터를 바꾸고 조회
  - cached recommendation의 `linked_from_shipment_order_id`/`can_cancel_link`가 최신 link map 기준으로 보정되는지 검증
- `test_apply_creates_order_schedule_date_as_visit`
  - apply 후 `structured_data.schedule.as_visit.date == ship_date`
  - `OrderScheduleDate(kind="as_visit", date=ship_date)` 존재
  - 응답 `as_visit_date == ship_date`, `status` 존재
- `test_apply_invalidates_asrec_cache_after_commit`
  - monkeypatch `invalidate_shipment_as_recommendation_cache`
  - commit 성공 후 1회 호출 검증
- `test_cancel_removes_order_schedule_date_as_visit`
  - apply 후 cancel
  - `structured_data.schedule.as_visit.date == ""`
  - `OrderScheduleDate(kind="as_visit")` 없음
- `test_cancel_invalidates_asrec_cache_after_commit`
  - monkeypatch invalidate
  - commit 성공 후 1회 호출 검증
- `test_as_status_order_is_visible_in_as_dashboard_query`
  - status `AS` + `schedule.as_visit.date` 있는 order 생성
  - `/erp/as?tab=incomplete&q=<id>` 응답 HTML에 해당 order id가 포함되는지 검증

### 5.2 템플릿/DOM 테스트

기존 템플릿 테스트 파일을 보강한다.
- `tests/domains/test_erp_mobile_layout_and_shipment.py`
  - `test_shipment_template_has_as_recommendation_prewarm_endpoint`
    - template text에 `/api/erp/shipment/as-recommendations/prewarm` 존재
  - `test_shipment_template_cancel_handler_is_not_modal_only`
    - `.js-shipment-as-rec-cancel` 처리 코드가 `if (!modalRoot) return`보다 앞에 있는지 텍스트 순서 검증
  - `test_shipment_template_renders_table_cancel_button_for_recommendation_link`
    - `shipment_as_recommendation_link`와 `js-shipment-as-rec-cancel`가 테이블 row 영역에 존재
  - `test_shipment_template_does_not_show_cancel_without_link`
    - 조건문이 `r.shipment_as_recommendation_link` 기반인지 검증
- Flask `render_template` 기반 테스트 1개 추가
  - 추천 메타가 있는 AS row context를 넣고 HTML에 `추천 취소`가 보이는지 확인

### 5.3 수동 QA

데이터 준비:
- 같은 출고일에 일반 출고건 1건
- 인근 미완료 AS `AS_RECEIVED` 1건
- 인근 미완료 AS `AS` 1건

확인:
1. 출고 대시보드 진입 후 2~5초 대기한다.
2. `AS일정 추천` 클릭 시 첫 응답 시간이 개선되는지 확인한다.
3. 같은 버튼을 다시 눌러 cache hit로 더 빠르게 뜨는지 확인한다.
4. 추천 `추가` 클릭 후 출고 대시보드에 AS 행이 생기는지 확인한다.
5. 같은 AS order를 AS 대시보드에서 검색해 `AS 방문일`이 같은 날짜인지 확인한다.
6. 출고 대시보드 AS 행의 `추천 취소` 클릭 후 출고 대시보드에서 행이 사라지는지 확인한다.
7. AS 대시보드에서 `AS 방문일`이 공란으로 돌아가는지 확인한다.

## 6. 구현 순서

1. 캐시 서비스 추가
   - Redis 사용 가능 여부 감지
   - 미완료 AS candidate pool helper 구현
   - route cache, target cache helper 구현
   - JSON DTO only 원칙 적용

2. 추천 API의 AS 후보 조회를 candidate pool cache로 분리
   - 운영 시점의 미완료 AS 전체 후보 pool을 매 클릭마다 직접 조립하지 않게 한다.
   - pool cache miss 때만 DB 조회/DTO 생성/좌표 보강을 수행한다.

3. 추천 서비스에 route provider 주입
   - 기존 호출부 하위 호환 유지
   - route cache hit/miss 카운터 반환 가능하게 정리

4. 추천 조회 API에 target cache 적용
   - cache miss target만 계산
   - 응답 metadata 추가

5. prewarm endpoint 추가
   - 프론트 idle prewarm 연결
   - 중복 계산 lock 추가

6. 출고 테이블 취소 버튼 노출
   - backend row DTO 추가
   - template 버튼 추가
   - JS cancel handler 범위 확장

7. AS 대시보드 상태 범위 보정
   - `AS` 상태를 미완료 탭 조회 범위에 포함
   - status 자동 변경은 하지 않는다.

8. apply/cancel 동기화 테스트 보강
   - structured_data
   - OrderScheduleDate
   - AS dashboard query 포함 여부
   - dashboard cache invalidation

9. 전체 테스트 및 수동 QA
   - `pytest tests/domains/test_shipment_as_recommendations.py -q`
   - 관련 템플릿/DOM 테스트
   - dev 서버 실행이 가능한 환경이면 실제 클릭 QA까지 수행

## 7. 감리 체크리스트

- [ ] 추천 조회 API는 DB를 변경하지 않는다.
- [ ] cache miss 때만 Kakao Directions API를 호출한다.
- [ ] route cache key는 좌표/주소 변동 시 자연스럽게 바뀐다.
- [ ] cache에는 개인정보를 과도하게 넣지 않는다. 주소 원문 대신 hash를 우선한다.
- [ ] Redis 장애 시 warning log 후 계산으로 fallback한다.
- [ ] 적용/취소 API는 기존 트랜잭션 원자성을 유지한다.
- [ ] 수동으로 변경된 AS 방문일은 취소 API가 기존처럼 409로 보호한다.
- [ ] 추천으로 만든 연결만 출고 테이블에서 `추천 취소` 버튼이 보인다.
- [ ] `AS` 상태 주문도 AS 대시보드에서 방문일을 확인할 수 있다.
- [ ] 기존 AS 대시보드 일정찾기, `/api/orders/nearby` 계약을 깨지 않는다.

## 8. 최종 판단

이 후속 수정은 단순 UI 개선이 아니라 성능 캐시, 상태 코드 정합성, 화면 간 일정 동기화까지 묶인 안정화 작업이다.

다만 DB schema 변경 없이도 1차 해결이 가능하다.

권장 구현 범위:
- candidate pool/route/target Redis TTL cache
- idle prewarm endpoint
- 출고 테이블 추천 취소 버튼
- AS 대시보드 `AS` 상태 포함
- apply/cancel 동기화 테스트 보강

비권장:
- 추천 적용 시 `AS` 상태를 즉시 `AS_RECEIVED`로 강제 변경
- 캐시를 DB 테이블로 먼저 설계
- 프론트에서만 취소 버튼을 억지로 추가하고 backend DTO 검증을 생략

## 9. Eng 리뷰 루프 결과

### 9.1 Scope Challenge

결론: 범위는 크지만 과하지 않다.

- 기존 구현이 이미 `recommend_nearby_schedules_for_targets()`, apply/cancel API, 모달 렌더링을 갖고 있으므로 새 추천 엔진을 만들 필요는 없다.
- 새로 필요한 것은 추천 엔진이 아니라 read-model/cache 계층과 UI 노출 보강이다.
- DB schema와 background worker를 제외했으므로 운영 리스크가 낮다.
- 새 파일은 cache service 1개로 제한한다. 나머지는 기존 파일에 국소 수정한다.

### 9.2 Architecture Review

| Finding | Severity | Confidence | Resolution |
|---------|----------|------------|------------|
| candidate pool cache가 없으면 현재 deploy 예시 56건처럼 미완료 AS 전체에 대해 매 클릭마다 DTO/좌표/링크 조립이 반복된다. | P1 | 10/10 | `get_or_compute_candidate_pool()` 고정 |
| route cache가 없으면 같은 주소쌍 Kakao Directions 호출이 반복된다. | P1 | 10/10 | `make_route_provider()` 고정 |
| target cache가 linked state까지 포함하면 stale link가 보일 수 있다. | P1 | 9/10 | cached target에는 `linked_as_schedules` 저장 금지, 응답 직전 fresh enrich |
| AS 상태 `AS`가 AS 대시보드에서 빠질 수 있다. | P1 | 9/10 | AS 대시보드 조회 범위에 `AS` 포함 |
| 테이블 cancel 버튼이 모달 guard 뒤에 있으면 클릭이 무시된다. | P1 | 10/10 | cancel handler를 modal guard 앞으로 이동 |

### 9.3 Code Quality Review

| Finding | Severity | Confidence | Resolution |
|---------|----------|------------|------------|
| cache 로직을 API 함수 안에 직접 넣으면 테스트와 재사용이 어렵다. | P2 | 8/10 | `foms/services/shipment_as_recommendation_cache.py`로 분리 |
| 순환 import 위험이 있다. | P2 | 8/10 | cache service는 API 상수를 import하지 않고 `source_value`, `as_statuses`를 인자로 받음 |
| `Order.updated_at` 참조 위험이 있다. | P2 | 10/10 | `structured_updated_at`, `created_at`, DTO hash만 사용 |
| Redis 장애를 사용자 오류로 노출할 위험이 있다. | P2 | 8/10 | warning log + compute fallback 고정 |

### 9.4 Test Review

결론: 구현 전 테스트 요구가 충분히 구체화됐다.

- cache hit/miss
- route provider call count
- prewarm endpoint
- apply/cancel OrderScheduleDate 동기화
- AS dashboard `AS` status 노출
- table cancel UI와 JS guard 순서

이 테스트들이 모두 통과해야 ready-to-ship이다.

### 9.5 Performance Review

목표:
- 같은 화면에서 첫 클릭 또는 prewarm 이후 두 번째 추천 조회는 Kakao route 호출이 0회여야 한다.
- candidate pool cache hit 시 AS 후보 DB DTO 조립은 생략되어야 한다.
- target cache hit 시 `recommend_nearby_schedules_for_targets()`는 해당 target에 대해 호출되지 않아야 한다.
- Redis가 없는 local/dev 환경에서도 process-local TTL로 반복 클릭 개선이 보여야 한다.

### 9.6 Definition Of Done

구현 완료 조건:

- [ ] `python -m pytest tests/domains/test_shipment_as_recommendations.py -q` 통과
- [ ] `python -m pytest tests/domains/test_erp_mobile_layout_and_shipment.py -q` 통과
- [ ] `python -m pytest tests/domains/test_dashboard_cache.py -q` 통과
- [ ] `node --check static/js/runtime/erp-shell.js` 통과. 이 파일을 수정하지 않았더라도 기존 shell event와 충돌 없음 확인용으로 실행한다.
- [ ] `/api/erp/shipment/as-recommendations/prewarm`가 targets 없이 cache stats만 반환
- [ ] prewarm 후 `/api/erp/shipment/as-recommendations` 응답 `cache.target_hits >= 1`
- [ ] 추천 추가 후 출고 대시보드 AS 행에 `추천 취소` 버튼 표시
- [ ] 추천 추가 후 AS 대시보드 `AS 방문일` 표시
- [ ] 추천 취소 후 출고 대시보드 AS 행 제거
- [ ] 추천 취소 후 AS 대시보드 `AS 방문일` 공란

### 9.7 Ready-To-Go Verdict

READY.

다음 LLM은 이 문서를 기준으로 바로 구현을 시작해도 된다. 구현 중 새 설계 결정을 만들지 말고, 위의 고정 결정과 함수 계약을 따라 최소 수정으로 진행한다.
