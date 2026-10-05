# 초안 표식 읽기 비용·DB 관리 SPEC (성능 P2-1, P3-9)

- 작성: 2026-10-05 · 상태: **승인 대기 (설계만, 코드·DB 변경 없음)**
- 원장: `docs/plans/2026-10-01-full-perf-audit-ledger.md` P2-1, P3-9 (P3-1 연결)
- 기준: origin/deploy `e9d2230ff` · alembic head `search_trgm_00` · 스테이징 PostgreSQL 17.11 · 스테이징 주문 3,524행(ERP 2,349) · 운영 주문 4,523행(원장 10-02 기록)
- 표기: **[실측]** 스테이징 읽기 전용 `EXPLAIN (ANALYZE, BUFFERS)` 4회 중 첫 회를 버리고 남은 3회의 최솟값 · **[로컬]** 로컬 PG 17.9 격리 클러스터 + 합성 4,600행(스테이징 orders 인덱스 49개 정의를 그대로 복제) · **[추정]** 계산·코드로 낸 값
- 이 설계서를 쓰는 동안 스테이징 DB 에는 읽기만 했다(`default_transaction_read_only=on`). 운영 DB 에는 접속하지 않았다.

## 0. 사용자 결정 항목

1. **대시보드 공통 필터가 초안 표식을 읽는 방식 (A)**
   - 가) 초안 표식이 켜진 주문 번호만 담는 작은 찾아보기 표(부분 인덱스)를 만들고, 필터는 "그 번호 목록에 있나"만 본다 (추천). 표 만들기는 주문 표를 멈추지 않는다(로컬 37~70ms, 읽기·쓰기 계속). 결과는 지금과 한 행도 다르지 않다. 새 칸이 생기지 않는다.
   - 나) 주문 표에 사본 칸(GENERATED STORED)을 만든다. 효과는 가)와 같다. 대신 만드는 순간 주문 표 전체를 다시 쓰느라 그동안 모든 화면이 주문을 못 읽는다(로컬 2.1~3.0초, 운영은 더 길 수 있다). 한가한 시간에 반영해야 한다.
   - 다) 사본 칸을 DB 방아쇠(trigger)로 채우기, 라) 사본 칸을 앱 저장 훅으로 채우기 — 둘 다 추천하지 않는다(§2 ②·④).
2. **어디에도 안 보이는 주문을 어떻게 할까?** 스테이징에 실제 고객 이름이 든 주문 4건(4237·4266·4301·4308)이 "초안" 표식이 남아 모든 화면에서 빠져 있다. 2026-08-03 고친 "초안 부활 레이스"(`106df4c11`, 운영 7건 보고)와 같은 모양이다.
   - 가) 이번 성능 수정은 결과를 바꾸지 않으니 그대로 둔다. 운영에 같은 주문이 몇 건인지 읽기 전용으로 한 번 세어 보고(승인 필요) 따로 정한다 (추천).
   - 나) 정식 승격 경로로 표식을 끄고 화면에 나오게 한다(데이터 수정, 운영은 승인 필요).
   - 다) 휴지통으로 보낸다.
3. **앞으로 단계 값(status) 하나로만 초안을 가릴까?** 가장 빠르지만 결과가 바뀐다. 스테이징에서 위 4건이 모든 대시보드에 나타나고, 휴지통 포함 화면(네이버 붙이기 후보)에 지운 초안 35건이 나타난다. 수집해 둔 앱 쿼리 53개 중 11개의 결과가 달라졌다.
   - 가) 아니오, 지금 뜻을 그대로 지킨다 (추천).
   - 나) 예. 2번 정리와 "초안 표식이면 status 가 DRAFT 또는 DELETED" 규칙을 먼저 만든 뒤에만 가능하다.
4. **느린 쿼리 집계(pg_stat_statements) 켜기 (B)** — 스테이징 먼저, 운영은 단계마다 승인(§7). 운영도 스테이징처럼 라이브러리가 미리 올라가 있다면 켜는 즉시 지금까지 모인 집계를 읽을 수 있다(이미 수집 중, §5.1).
5. **안 쓰는 인덱스 정리** — 이번에는 후보 목록만 낸다. 운영 통계를 읽어 확인(승인)한 뒤 따로 정한다.

## 1. 문제와 근거 (A, P2-1)

### 1.1 지금 술어
`models.py:184` `Order.erp_draft_predicate()` 와 `:171` `erp_draft_filter()` 가 같은 조건을 쓴다.

```
is_erp_order IS true AND (status = 'DRAFT' OR CAST((structured_data #>> '{meta, draft}') AS BOOLEAN) IS true)
```

`active_filter()`(`:201`)는 이것을 NOT 으로 감싸 모든 운영 화면에 붙는다. 저장소 안 호출은 약 88곳이다(`active_filter`·`active_including_trashed_filter`·`erp_draft_filter`·`erp_draft_predicate`). ERP 주문이고 status 가 DRAFT 가 아닌 행마다 `structured_data` 를 풀어야(압축 풀기·TOAST 읽기) 이 값을 안다. 스테이징 기준 한 번 훑을 때 약 2,000행이다.

### 1.2 비용 [실측]
같은 쿼리에서 초안 표식 가지만 `false` 로 바꾼 것(= status 만 보는 술어)이 "meta 를 전혀 안 읽을 때"의 하한이다. 번호 목록 가지(`orders.id IN (39개)`)는 추천안 가)가 실제로 하는 일(해시 목록 대조)을 흉내 낸다.

| 쿼리 (원장 캡처 SQL) | 지금 | status 만(하한) | 번호 목록 대조 |
|---|---|---|---|
| `/erp/dashboard` [1] | 22.35ms · 3,334 buf | 2.82 · 645 | 2.83 · 645 |
| `/erp/dashboard` [2] | 16.30 · 3,334 | 3.26 · 645 | 3.09 · 645 |
| `/erp/dashboard` [3] | 17.75 · 3,334 | 3.40 · 645 | 3.18 · 645 |
| `/erp/dashboard/field-ops` [2]·[8] | 15.71 · 18.28 | 2.24 · 2.07 | 2.21 · 2.09 |
| `/api/orders/completion` [2] | 14.60 · 2,571 | 0.55 · 450 | 0.52 · 450 |
| `/erp/construction/dashboard` [1]·[2]·[3] | 10.50 · 9.35 · 8.64 | 3.75 · 1.59 · 1.84 | 3.74 · 1.52 · 1.50 |
| `/erp/as` [1]·[2] | 9.28 · 7.53 | 6.04 · 4.55 | 6.29 · 4.57 |
| `/erp/production/dashboard` [3] | 1.38 · 273 | 0.54 · 91 | 0.51 · 91 |
| `/erp/measurement` [6] | 104.07 · 6,023 | 91.91 · 3,334 | 93.24 · 3,334 |
| `/erp/dashboard?q=김` [1]·[2] | 28.63 · 29.72 | 16.38 · 17.38 | 18.28 · 20.07 |

- 대시보드 조각 하나(쿼리 3개)가 56.4 → 9.5ms, 완료 API 14.6 → 0.6ms 다. 원장 값(16~21 → 4~5ms, 20.2 → 6.5ms)과 같은 방향이고 조금 더 줄었다.
- 이 쿼리들은 대시보드 캐시(DashCache)가 비었을 때만 돈다. 체감 효과는 캐시 miss 비율만큼이다.
- 운영은 행이 약 28% 많다(4,523 vs 3,524). 줄어드는 양도 그만큼 커질 것으로 본다 [추정].

### 1.3 초안 표식이 켜진 39행 [실측]
`meta.draft` 값은 전부 JSON 참/거짓(문자열·숫자 0건)이다. status 가 DRAFT 인 행은 0건이다. 그래서 지금 초안으로 빠지는 39행은 전부 "status 는 DRAFT 가 아닌데 meta.draft = true" 다.

| 묶음 | 행 | 특징 |
|---|---|---|
| 지운 초안 | 35 | status DELETED, deleted_at 있음. 고객명 자리표시("ERP Beta…"/"ERP Order…"). 02~04월 17건(옛 삭제 경로) + 06-30 이후 18건(새 주문·자동저장 초안. 11건은 original_status=DRAFT — 정리 크론 `tools/cron/cleanup_order_drafts.py:163` 처럼 status 만 바꾸고 meta.draft 는 그대로 둔 삭제, 7건은 original_status 없음). original_status 전체: DRAFT 11 · RECEIVED 14 · AS_RECEIVED 2 · DELETED 1 · 없음 7 |
| 숨은 실제 주문 | 4 | 4237·4266·4308(MEASURE), 4301(RECEIVED). 실제 고객명·제품, `created_via=ADD_ORDER_AUTOSAVE`, `finalized_at` 없음, 주문 이벤트 0건, 07-01~07-06 생성. 모든 화면에서 빠져 있다 |

숨은 4건은 `106df4c11`(2026-08-03) 커밋 설명과 같은 모양이다: 자동저장이 승격 직후 `meta.draft=True` 를 되살리고 status 는 승격된 값으로 남는다. 그 커밋은 레이스만 막았고 이미 생긴 행은 고치지 않았다(커밋 파일 목록에 데이터 정리 없음). 운영에서 그때 7건이 보고됐다. 지금 몇 건 남았는지는 운영 읽기로만 알 수 있다(§7 A-2).

## 2. 선택지 비교

| | ① GENERATED STORED 칸 | ② 방아쇠로 채우는 칸 | ③-가 식 인덱스만 | ③-나 부분 인덱스 + 번호 목록 술어 (추천) | ④ 앱 저장 훅으로 채우는 칸 |
|---|---|---|---|---|---|
| 쓰기 경로 전부 맞나 | 예(DB 가 계산) | 예(DB 가 계산) | 해당 없음 | 예(DB 가 인덱스 유지) | 아니오 — 날 SQL·psql 수정은 못 봄 |
| 지금 뜻 그대로 | 예(같은 식) | 예(같은 식) | 예 | 예(같은 식, 아래 동치 0건) | 파이썬 흉내라 문자열 값에서 갈림 |
| 반영 때 잠금 | 표 다시 쓰기, 읽기·쓰기 모두 멈춤 로컬 2,098~3,006ms | 칸 추가 1.5~1.9ms + 39행 채우기 | 없음(CONCURRENTLY) | 없음(CONCURRENTLY 37~70ms) | 칸 추가 순간 + 39행 채우기 |
| 효과 | 3.1·2.2ms [로컬] | 2.9·2.5ms [로컬] | **없음** 12.2·12.8ms [로컬] | 3.0·2.7ms [로컬] | ①과 같음 |
| SQLite 레인 | 방언별 식이 따로 필요 | SQLite 용 방아쇠 따로 필요 | 무관 | 그대로 동작(인덱스만 없음) | 그대로 동작 |
| 되돌리기 | 코드 되돌림 + DROP COLUMN(짧은 배타 잠금) | 방아쇠·칸 지우기 | 인덱스 지우기 | 코드 되돌림만으로 끝(인덱스는 남겨도 무해) | 칸 지우기 |
| 바깥에 보이는 변화 | `to_dict()` 에 새 키 | 같음 | 없음 | 없음 | 같음 |

[로컬] 효과 칸은 "최근 50건 목록 · 건수" 두 쿼리, 지금 값은 9.12 · 11.31ms(6,952 buf), status 만 하한은 2.11 · 1.85ms 다.

### ① GENERATED ALWAYS AS (…) STORED
- 맞는가: 식이 같으므로 값이 같다. 날 SQL(`tools/ops/bulk_complete_past_construction_core.py:352·360·409`, `tools/ops/data_doctor.py:486`, `scripts/ops/erp_build_step_runner.py:391`)과 psql 수정까지 DB 가 계산한다. 값이 불(boolean)로 안 바뀌는 문자열이 들어오면 지금은 그 행을 읽는 모든 대시보드가 오류를 내지만, ①에서는 그 저장 하나가 실패한다(더 이른 실패).
- 잠금: PostgreSQL 17 에서 STORED 칸 추가는 표를 통째로 다시 쓴다(로컬에서 파일 번호가 바뀐 것 확인). 그동안 ACCESS EXCLUSIVE 잠금이라 주문을 읽는 모든 요청이 기다린다. 로컬 인덱스는 11MB, 스테이징·운영은 28MB 라 더 길다 — 수 초에서 10초 안팎 [추정]. 앞선 긴 트랜잭션이 있으면 그 뒤에 줄이 생기므로 `lock_timeout` + 재시도가 필요하다.
- SQLite: `Computed` 식이 방언마다 달라야 한다(`#>>` 는 PostgreSQL 전용). 방언별로 그려지는 식 구성을 따로 만들어야 한다.
- ORM: `Computed` 칸은 INSERT·UPDATE 에서 빠지고 저장 뒤 만료된다. 칸 목록을 도는 곳은 `models.py:255` `to_dict()` 하나다 — 응답에 `erp_meta_draft` 키가 붙는다(`foms/api/channel/rooms.py:242·392`).

### ② 방아쇠(trigger)로 채우는 칸
- `ADD COLUMN erp_meta_draft boolean NOT NULL DEFAULT false` 는 PostgreSQL 11 이후 표를 다시 쓰지 않는다. 방아쇠를 먼저 만들고, 39행만 `true` 로 채우면 잠금이 수십 ms 다. (참고: 전 행을 다시 쓰는 채우기는 로컬 3,137~3,424ms, 행 잠금이라 읽기는 안 막는다.)
- 맞는가: ①과 같다. 다만 저장소 첫 방아쇠다(지금 orders 에 방아쇠 0개 [실측]). 숨은 로직이 생긴다.
- SQLite 레인은 방아쇠가 없으면 칸이 늘 false 라 "초안 숨김" 테스트가 깨진다. SQLite 용 방아쇠를 따로 만들어야 하고, 두 방언 동작을 계속 맞춰야 한다.

### ③-가 식 인덱스만
- 식 인덱스는 그 식이 인덱스로 찾을 수 있는 모양(`식 = 값`)일 때만 쓰인다. 지금 조건은 `NOT (… OR 식 IS TRUE)` 라 찾는 조건이 아니라 걸러 내는 조건이다. 플래너는 다른 경로로 행을 읽고, 행마다 식을 다시 계산한다 — 그때 `structured_data` 를 푼다. 인덱스에 든 값을 대신 쓰려면 인덱스만 읽는 스캔이어야 하는데, 쿼리가 다른 칸을 많이 읽으므로 불가능하다.
- [로컬] 확인: 부분 인덱스를 만들어 둔 채 지금 술어를 돌리면 12.2 · 12.8ms 로 그대로다. 얻는 것은 플래너 통계뿐이다.

### ③-나 부분 인덱스 + 번호 목록 술어 (추천)
- 인덱스: `ON orders (id) WHERE (CAST((structured_data #>> '{meta,draft}') AS BOOLEAN)) IS TRUE` — 표식이 켜진 행(스테이징 39)의 id 만 담는다.
- 술어: 초안 가지를 `orders.id IN (SELECT orders_meta_draft.id FROM orders AS orders_meta_draft WHERE CAST((orders_meta_draft.structured_data #>> '{meta, draft}') AS BOOLEAN) IS true)` 로 바꾼다. 안쪽 조건이 인덱스 조건과 같아서 플래너가 그 작은 인덱스만 읽고(Index Only Scan, Heap Fetches 0), 결과를 해시 목록으로 한 번 만든 뒤 바깥 행마다 번호만 대조한다(hashed SubPlan). 바깥 행은 `structured_data` 를 풀지 않는다.
- [로컬] 앱 경로 그대로(psycopg `ClientCursor`) 그린 SQL 의 계획:

```
Seq Scan on orders
  Filter: (... AND ((is_erp_order IS NOT TRUE) OR (((status)::text <> 'DRAFT'::text) AND (NOT (ANY (id = (hashed SubPlan 1).col1))))))
  SubPlan 1
    ->  Index Only Scan using ix_orders_meta_draft_true on orders orders_meta_draft
          Heap Fetches: 0
```

  앱은 경로를 `'{meta, draft}'`(띄어쓰기 있음)로, 인덱스는 `'{meta,draft}'` 로 적어도 상수 정리 뒤 같은 배열이라 인덱스가 맞는다.
- 맞는가: 같은 식을 DB 가 인덱스로 유지하므로 날 SQL·psql 수정·복원까지 맞다. `id` 는 기본 키라 NULL 이 없어 `id IN (…)` 은 참·거짓만 낸다 — 지금의 `IS true`(NULL 을 안 냄)와 세 값 논리까지 같다.
- 잠금: CONCURRENTLY 라 읽기·쓰기를 막지 않는다.
- SQLite: 같은 구문이 `JSON_EXTRACT(…) IS 1` 서브쿼리로 그려지고 그대로 동작한다(인덱스만 없다). 8가지 경우(DRAFT·표식 참/거짓/없음/NULL·지운 행·비ERP·문자열 "true")에서 옛/새 결과가 같았다.
- 약점: (1) 인덱스가 없거나 INVALID 면 안쪽 서브쿼리가 표 전체를 한 번 푼다 — 스테이징 [실측] 17~23ms 로, 작은 쿼리는 지금보다 느려진다(생산 [3] 1.38 → 17.02ms). 그래서 마이그레이션이 valid 를 확인하고 실패하면 배포를 멈추게 한다(§3.2). 새 코드는 predeploy 마이그레이션이 끝난 뒤에만 라이브된다. (2) 안쪽 별칭이 바깥 `orders` 와 같으면 SQLAlchemy 가 상관 서브쿼리로 묶어 효과가 사라진다 — 별칭을 꼭 쓰고 계약 테스트로 묶는다. (3) 지운 초안이 쌓이면 목록이 커진다. 7개월에 35행이라 수천 행까지는 문제가 없다 [추정].

### ④ 앱 저장 훅으로 채우는 칸
- `foms/services/order_date_sync.py:705` 의 전역 before_flush 훅에서 `order.erp_meta_draft` 를 채운다.
- 날 SQL 쓰기는 훅을 못 본다. ORM 우회 쓰기 인벤토리(`docs/harness/foms_orm_bypass_write_inventory.json`)는 46곳이고, 그 밖에 psycopg 로 직접 쓰는 운영 도구 3개가 `structured_data` 를 통째로 다시 쓴다. 지금은 모두 meta 를 그대로 두지만 앞으로도 그렇다는 보장이 없다.
- 뜻 차이: SQL 은 글자 값도 불로 바꿔 읽는다(`'t'`·`'yes'`·`'1'` 도 참). 파이썬 판정 `foms/services/erp_order_flags.py:24` 는 `is True` 만 참이다. 지금 데이터(전부 JSON 참/거짓)에서는 같지만 정확히 같은 뜻이 아니다. 어긋남 감시가 따로 필요하다.

## 3. 추천안 ③-나 설계

### 3.1 코드 (승인 후)
- `models.py`
  - `erp_draft_predicate()`(`:184`)·`erp_draft_filter()`(`:171`)의 `cls.structured_data[("meta", "draft")].as_boolean().is_(True)` 를 `cls.id.in_(cls._meta_draft_order_ids())` 로 바꾼다. 두 곳이 같은 도우미를 쓴다.
  - 새 도우미 `_meta_draft_order_ids()`: `aliased(cls, name="orders_meta_draft")` 별칭으로 `select(별칭.id).where(별칭.structured_data[("meta", "draft")].as_boolean().is_(True))` 를 돌려준다. 독스트링에 "바깥 행이 JSON 을 풀지 않게 하는 번호 목록, 인덱스 `ix_orders_meta_draft_true` 와 식이 같아야 한다"를 적는다.
  - `__table_args__` 에 `Index('ix_orders_meta_draft_true', 'id', postgresql_where=text("(CAST((structured_data #>> '{meta,draft}') AS BOOLEAN)) IS TRUE")).ddl_if(dialect='postgresql')` 를 더한다(검색 trgm 인덱스와 같은 방식, create_all 레인용).
- 파이썬 판정(`erp_order_flags.py`)은 바꾸지 않는다.

### 3.2 마이그레이션 (가칭 `migrations/versions/draftidx_00_meta_draft_partial_index.py`)
- `down_revision` 은 구현 시점 head(지금 `search_trgm_00`, `python -m alembic heads` 로 다시 확인).
- 선례 `search_trgm_00_visible_field_indexes.py` 를 그대로 따른다: PostgreSQL 이 아니면 건너뛰기, `op.get_context().autocommit_block()` 안에서 실행(문자열 COMMIT 금지), models 를 import 하지 않고 리터럴만 쓰기.
- 순서: ① `pg_index.indisvalid = false` 인 같은 이름 인덱스가 있으면 `DROP INDEX CONCURRENTLY IF EXISTS` ② `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_meta_draft_true ON orders (id) WHERE (CAST((structured_data #>> '{meta,draft}') AS BOOLEAN)) IS TRUE` ③ 만든 뒤 valid 가 아니면 예외 → predeploy(`set -e`)가 멈추고 옛 버전이 계속 돈다.
- `downgrade()`: `DROP INDEX CONCURRENTLY IF EXISTS ix_orders_meta_draft_true`. 결과는 인덱스와 무관하므로 언제 지워도 안전하다(단, 새 코드가 돌고 있으면 위 약점 (1)처럼 느려진다 — 코드 되돌림 뒤에 지운다).
- 실행 위치: web `preDeployCommand = "sh predeploy.sh"`(`railway.toml:12`), 다중 실행은 `migrations/env.py:128` 세션 advisory lock 이 막는다. CONCURRENTLY 는 시작 시점에 열린 트랜잭션이 끝날 때까지 기다리므로 배포 직전 `pg_stat_activity` 를 본다(스테이징 지금 1분 넘은 활성 트랜잭션 0건 [실측]).
- 크기·시간: 39행짜리라 16kB 안팎, 로컬 37~70ms.
- 쓰기 비용: `structured_data` 는 이미 인덱스 24개가 보는 칸이라 HOT 비율은 바뀌지 않는다(스테이징 갱신 1,434회 중 HOT 278회). 저장마다 조건 하나를 더 계산한다 — 저장 요청당 1ms 미만 [추정].

### 3.3 동치 시험
1. **스테이징 전 행 [실측, 이미 함]**: 3,524행 전부에서 옛 술어와 새 술어(서브쿼리 형태, 인덱스 없이도 결과는 같다)를 나란히 계산했다. `active_filter` 0건 · `active_including_trashed_filter` 0건 · `erp_draft_filter` 0건 차이, 초안 행 수 39 = 39.
2. **앱 쿼리 단위 [실측, 이미 함]**: 원장 캡처의 초안 술어를 담은 앱 쿼리 53개를 옛/새 술어로 돌려 결과 행 묶음을 비교했다. 53개 모두 같았다.
3. **음성 대조군 [실측, 이미 함]**: 같은 검사에 status 만 술어를 넣으면 행 단위 4건(active)·39건(휴지통 포함), 쿼리 53개 중 11개가 달라졌다. 검사가 차이를 잡는다는 증거다.
4. **PG 레인 계약 테스트(신규, 가칭 `tests/postgres/test_meta_draft_predicate_pg.py`)**: 경우별 행(DRAFT · 표식 참/거짓/없음 · `structured_data` NULL · 지운 초안 · 비ERP)을 넣고 옛 식(테스트 안에 고정)과 새 술어의 id 집합이 세 필터 모두 같은지 본다. 앱 경로(psycopg `ClientCursor`)로 그린 SQL 의 EXPLAIN 에 `hashed SubPlan` 과 `ix_orders_meta_draft_true` 가 있고 바깥 Filter 에 `structured_data` 가 없음을 단언한다.
5. **SQLite 계약 테스트(신규, 가칭 `tests/performance/test_meta_draft_index_contract.py`)**: models 의 인덱스 조건과 마이그레이션 리터럴이 글자 단위로 같은지, 도우미가 별칭을 써서 바깥 `orders` 와 상관되지 않는지(컴파일된 SQL 에 `orders AS orders_meta_draft`) 본다. 기존 초안 숨김 테스트(`tests/domains/test_erp_draft_order_events.py` 등)는 그대로 통과해야 한다.
6. **배포 뒤 스테이징**: 인덱스 `indisvalid = true`, 1번·2번을 다시 돌려 0건, §1.2 표를 다시 재서 "번호 목록 대조" 열과 같은 수준(±1ms)인지 본다.

### 3.4 기대 효과
- 스테이징 [실측] 하한: 대시보드 조각 56.4 → 약 9.5ms, 완료 API 14.6 → 약 0.6ms, 시공 3쿼리 28.5 → 약 7ms. 추천안은 하한보다 쿼리당 0.9ms 안팎 더 든다 [로컬](작은 인덱스 읽기 + 해시 목록 만들기).
- 운영 확인: 승격 뒤 Railway 로그 `[DashCache] … compute_ms`(대시보드·시공·완료 slice)와 `/erp/dashboard`·`/erp/construction/dashboard`·`/api/orders/completion` p50/p95 를 직전 3일과 비교한다(`tools/perf/prod_route_latency_compare.py`).

## 4. 39행 의미 결정 (결정 2·3)
- 추천안은 뜻을 바꾸지 않는다. 그래서 결정 2·3 없이도 반영할 수 있다.
- status 만으로 바꾸면(결정 3-나) 생기는 일 [실측]: 숨은 실제 주문 4건이 모든 대시보드·검색에 나타난다. 지운 초안 35건이 "휴지통까지 보여 주는" 화면(`active_including_trashed_filter`, 네이버 붙이기 후보)에 나타난다. 그러면 원래 그 술어가 막으려던 "승격 전 초안에 무언가를 붙이는" 레이스(`models.py:207-215` 독스트링)가 다시 열린다.
- 숨은 4건을 보이게 하려면(결정 2-나) 표식만 끄지 말고 정식 승격 경로처럼 status·평면 칸·`ORDER_CREATED` 이벤트를 함께 맞춰야 한다. 운영 대상은 읽기 전용으로 먼저 센다:
  `SELECT id, status, created_at FROM orders WHERE is_erp_order AND status NOT IN ('DRAFT','DELETED') AND deleted_at IS NULL AND CAST((structured_data #>> '{meta,draft}') AS BOOLEAN) IS TRUE`

## 5. pg_stat_statements 켜기 (B, P3-9)

### 5.1 지금 상태 [실측, 스테이징]
- `shared_preload_libraries = pg_stat_statements` — 라이브러리는 서버 시작부터 이미 집계를 모으고 있다. 확장은 설치 안 됨(설치된 확장: pg_trgm 1.6 · plpgsql · vector 0.8.2). 쓸 수 있는 판은 1.11, 슈퍼유저 전용(trusted 아님).
- 설정: `pg_stat_statements.max = 5000`(바꾸려면 재시작) · `track = top` · `track_utility = on` · `track_planning = off` · `save = on` · `compute_query_id = auto`. `track_io_timing = off`.
- 서버 시작 2026-08-25 23:48 UTC. `shared_buffers` 128MB, DB 크기 143MB.
- 접속 계정: 앱으로 보이는 연결 12개와 측정 헬퍼 모두 `postgres`(슈퍼유저)다. 운영도 같은지는 확인이 필요하다(§7 B-2).
- 시계 비용: `EXPLAIN ANALYZE` 시간 재기 켬/끔 차이가 200만 행에 256 → 401ms, 행당 약 72ns(시계 약 4회) — 시계 한 번에 수십 ns 다. `track_io_timing` 은 실제 디스크 읽기 한 번에 시계 2회라 부담이 1% 미만이다 [추정].
- 같은 세션 안에서 `SET track_io_timing = on` 은 읽기 전용 연결에서도 된다 — 한 쿼리만 볼 때는 서버 설정을 바꾸지 않고 `EXPLAIN (ANALYZE, BUFFERS)` 에 읽기 시간을 붙일 수 있다.

### 5.2 켜는 절차
1. 스테이징(설계 승인 후): `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` → `ALTER SYSTEM SET track_io_timing = on; SELECT pg_reload_conf();`. 확인: `SELECT count(*) FROM pg_stat_statements`, `SELECT * FROM pg_stat_statements_info`, `SHOW track_io_timing`.
2. 스테이징 하루 관찰: perf-gate 서버 시간·`/healthz/cpu` 가 흔들림 범위 안인지, `pg_stat_statements_info.dealloc` 이 0 인지.
3. 운영 사전 확인(읽기 전용, 승인): 접속 계정 슈퍼유저 여부, `shared_preload_libraries`, `pg_postmaster_start_time()`, 위 설정 값.
4. 운영 반영(승인): 1번과 같은 두 줄.
- 도구: 가칭 `tools/perf/pgss_enable.py`(기본은 확인만, `--apply` 때만 쓰기, 운영 호스트는 `--production --yes` 둘 다 있어야 실행, 전후 상태 출력) — 마이그레이션에 넣지 않는다. 앱이 이 확장에 의존하지 않고, 슈퍼유저가 아니면 배포 자체가 멈추기 때문이다.
- `ALTER SYSTEM` 은 데이터 디렉터리의 `postgresql.auto.conf` 에 남는다(Railway 볼륨, 재시작 뒤에도 유지). 다른 길은 `ALTER DATABASE railway SET track_io_timing = on` 이지만 이미 열린 풀 연결에는 안 먹는다.

### 5.3 권한·위험
- 권한: `CREATE EXTENSION` 과 `ALTER SYSTEM` 은 슈퍼유저만. 집계 보기는 누구나 되지만 다른 계정의 쿼리 글은 슈퍼유저·`pg_read_all_stats` 만 본다. 초기화 함수는 기본으로 슈퍼유저만 실행한다(로컬 PG17 에서 권한 확인).
- 위험이 낮은 이유: 수집은 이미 돌고 있다. 확장 설치는 보기(view)·함수만 만든다 — 앱 표에 잠금이 없고, 메모리는 시작 때 이미 잡혀 있다.
- 남는 위험: (1) 쿼리 글이 DB 볼륨 파일에 남는다. 상수는 `$1` 로 바뀌어 고객 이름·전화는 남지 않는다. 단 `track_utility` 로 잡히는 SET 같은 문장은 글이 그대로 남을 수 있다. (2) 밤 백업(`pg_dump`)에 `CREATE EXTENSION` 한 줄이 들어간다 — 슈퍼유저가 아닌 계정으로 복원하면 그 줄만 오류가 난다. (3) `track_io_timing` 부담은 위 계산상 작지만 스테이징 하루 관찰로 확인한다.
- 되돌리기: `ALTER SYSTEM RESET track_io_timing; SELECT pg_reload_conf();`, `DROP EXTENSION pg_stat_statements;`(수집은 라이브러리가 계속하고, 보기만 사라진다).

### 5.4 P3-1 아침 ctx SQL 대기에 쓰는 법
- 운영도 preload 라면(B-2 로 확인) 서버 시작 뒤 모인 집계를 설치 즉시 읽을 수 있다. 다만 전 시간대 합계라 아침 몰림을 가르려면 구간 차이를 본다.
- 순서(전부 읽기 전용, 운영 DB 읽기 세션 승인 1회): 평일 09:30 KST 스냅샷 S0 → 11:30 KST S1 → 15:00 S2 → 17:00 S3. 가칭 `tools/perf/pgss_snapshot.py` 가 `queryid, query, calls, total_exec_time, max_exec_time, rows, shared_blks_hit, shared_blks_read, shared_blk_read_time, temp_blks_written` 를 JSON 으로 저장하고, 두 스냅샷의 차이를 `queryid` 별로 낸다.
- 판정: 오전 구간(S1−S0)에서 총 시간 상위이면서 오후 구간(S3−S2)보다 평균이 크게 오른 쿼리가 후보다. `shared_blk_read_time` 이 크면 캐시 밖 읽기(디스크) 문제이고, 읽기 시간은 작은데 평균만 크면 잠금 대기나 CPU 다. 같은 시간대에 `pg_stat_activity` 를 2초마다 10분 표본으로 떠서 `wait_event_type`(Lock·IO·LWLock)을 함께 본다.
- 이름 붙이기: 상위 쿼리 글을 context processor(`foms/services/context_processors.py:492-499` 의 8개, 그 밖에 정책·CSRF 2개)의 쿼리 모양과 맞춘다. 첫 후보는 nav 배지(`inject_foms_nav_badges`)다 — 10-05 운영 반영된 PR #496 이 배지 조회를 412 → 103ms(스테이징) 줄였으므로, 반영 뒤 아침 diag 를 먼저 다시 보고 남은 대기만 이 방법으로 찾는다.
- 한계: PostgreSQL 17 은 `IN (…)` 목록 길이가 다르면 다른 항목이 된다. 비슷한 쿼리가 여러 줄로 갈라질 수 있으니 쿼리 글 앞부분으로 묶어 본다.

### 5.5 초기화·한도
- 기본은 **초기화하지 않는다**. 스냅샷 차이로 충분하고, 초기화는 운영 쓰기라 승인이 필요하다.
- 구간 최대값이 꼭 필요하면 PG17 의 `SELECT pg_stat_statements_reset(0, 0, 0, true);`(최소·최대만 초기화, `minmax_stats_since` 갱신)를 승인받아 한 번 쓴다.
- 한도: `max = 5000` 은 재시작이 필요해 두고, `pg_stat_statements_info.dealloc` 이 늘면 `track_utility = off`(재시작 없이 reload)로 칸을 아낀다.

## 6. 인덱스 정리 후보 (P3-9) — 모두 운영 통계 확인 전에는 지우지 않는다

스테이징 통계 구간은 약 2026-08-25(서버 시작, `pg_stat_database.stats_reset` 없음)부터 10-05 까지 약 41일이다. 스테이징은 사람이 적게 쓰므로 "0회"는 "안 쓴다"의 증거가 아니다.

### 6.1 완전 중복 5쌍 [실측]
같은 표·같은 칸·같은 연산자 클래스·같은 조건. 둘 다 0회.

| 표 | 중복 쌍 | 크기 | 지울 쪽 |
|---|---|---|---|
| `public.stage_gate_templates` | `stage_gate_templates_key_key`(UNIQUE 제약) · `ix_stage_gate_templates_key` | 16kB 씩 | `ix_…_key`(제약 쪽은 남긴다) |
| `wdcalculator.estimate_histories` | `ix_estimate_histories_estimate_id` · `ix_wdcalculator_estimate_histories_estimate_id` | 16kB 씩 | 둘 중 하나 |
| `wdcalculator.estimate_order_matches` | `…_estimate_id` 두 개 | 16kB 씩 | 둘 중 하나 |
| `wdcalculator.estimate_order_matches` | `…_order_id` 두 개 | 16kB 씩 | 둘 중 하나 |
| `wdcalculator.estimates` | `ix_estimates_customer_name` · `ix_wdcalculator_estimates_customer_name` | 32kB 씩 | 둘 중 하나 |

이득은 합쳐 약 0.1MB 로 작다. 쓰기마다 같은 일을 두 번 하는 것을 없애는 정리다.

### 6.2 한 번도 안 쓰인 인덱스 [실측]
- 0회 인덱스 228개 중 기본 키·UNIQUE·제약 125개(3.0MB)는 쓰임과 상관없이 필요하므로 뺀다. 남는 **103개, 14.8MB**(public 95개 14.6MB, wdcalculator 8개 0.16MB)가 후보다. 원장의 "116개 17MB"는 10-01 집계이고 셈 방식이 조금 다르다.
- 큰 것부터:

| 인덱스 | 크기 | 판단 |
|---|---|---|
| `security_logs.ix_security_logs_message_trgm` | 10.8MB | **남긴다** — 관리자 감사 검색이 쓴다(`foms/web/admin/audit.py:94`). 스테이징에서 검색을 안 했을 뿐 |
| `naver_settle_commission.ix_nscm_product_order` | 600kB | 운영 확인 |
| `naver_vat_case.ix_nvc_product_order` | 368kB | 운영 확인 |
| `order_schedule_dates.idx_order_schedule_dates_composite` | 328kB | 운영 확인 — models 가 선언(`models.py:294`) |
| `order_attachments.ix_order_attachments_filename_trgm` | 280kB | 운영 확인 |
| `orders.idx_order_schedule_date_trgm` | 184kB | 운영 확인 — 옛 주문 목록 검색(`foms/web/orders/listing.py:201`)이 쓰려 하지만, 같은 OR 에 인덱스 없는 가지가 있어 못 탄다 |
| `notification_events.ix_notification_events_endpoint_created` | 176kB | 운영 확인. 덧붙여 이 표는 seq_scan 10,772 · idx_scan 15 다(별건) |
| `channel_delivery_logs.ix_channel_delivery_source_status` | 120kB | 운영 확인 |
| `orders.ix_orders_erp_owner_team_code` | 72kB | 운영 확인 — 저장소에 이 칸으로 거르는 쿼리가 없다(쓰기만). models 가 `index=True` 로 선언(`models.py:107`) |

- 나머지 94개는 하나에 64kB 미만이다(order_tasks 4, notifications 4, designer_* 여럿 등).

### 6.3 orders 의 거의 안 쓰인 인덱스
- `ix_orders_structured_data_gin`(jsonb 전체 GIN) 6.3MB, 41일에 1회(마지막 08-28). 저장소에 `structured_data` 포함 검색(`@>`·`.contains`)이 없다. 주문 저장마다 JSON 키·값 수만큼 항목을 쓰므로 쓰기 비용이 가장 클 수 있다. **가장 큰 정리 후보지만 운영 통계로 0 에 가까운지 꼭 확인한다.**
- `idx_order_erp_beta` 112kB 2회, `ix_orders_erp_urgent` 72kB 8회 — 운영 확인.
- orders 인덱스는 49개 28MB(본체 5.2MB, TOAST 2.3MB), 갱신 1,434회 중 HOT 278회(비HOT 80.6%)다.

### 6.4 검색 수정 뒤 쓰이기 시작한 trgm [실측]
원장 10-01 에 0회였던 `ix_orders_product_trgm`·`ix_orders_sd_items0_name_trgm`·`ix_orders_sd_items0_product_name_trgm`·`ix_orders_sd_meas_date_trgm` 이 지금 181~238회다. `sd_meas_time`·`sd_orderer_name`·`sd_construction_date`·`sd_site_address_full/main`·`address`·`sd_customer_name/phone` 도 181~316회이고, 새 인덱스 5개(`search_trgm_00`)도 16~40회다. **그러나 마지막 사용 시각이 모두 10-01 15:12 UTC(10-02 00:12 KST, 스테이징 검증 시간대)에 몰려 있다** — 검증 EXPLAIN 이 낸 사용일 수 있다. "BitmapOr 가 이 인덱스들을 고른다"는 증거로는 충분하고, 실제 사용량은 운영 통계로 본다. 이 묶음은 정리 대상에서 뺀다.

### 6.5 지우는 절차 (승인 후, 별도 설계)
1. 운영 `pg_stat_user_indexes`(idx_scan·last_idx_scan)와 `pg_stat_database.stats_reset`·서버 시작 시각을 읽는다(읽기 전용, 승인). 30일 이상 0회이고 6.2 표의 "남긴다"가 아닌 것만 남긴다.
2. 지울 인덱스마다 정의 출처를 같이 지운다: `models.py` 선언(`index=True`·`Index(...)`), 처음 만든 마이그레이션은 그대로 두고 새 마이그레이션에서 `DROP INDEX CONCURRENTLY IF EXISTS`. 안 그러면 create_all 레인과 PG 레인이 다시 만든다. `foms/services/db_indexes.py` 의 `CREATE INDEX IF NOT EXISTS` 줄은 지금 아무도 부르지 않지만(호출처 0) 같이 정리한다.
3. `downgrade()` 는 같은 정의로 `CREATE INDEX CONCURRENTLY IF NOT EXISTS`.

## 7. 사용자 승인이 필요한 단계

이 설계서 작성 중에는 스테이징 읽기만 했고 아래 어느 것도 하지 않았다.

| 번호 | 단계 | 대상 | 쓰기 여부 | 승인 |
|---|---|---|---|---|
| A-1 | 추천안 구현(코드 + CONCURRENTLY 인덱스 마이그레이션) → deploy 푸시 | 스테이징 | 스키마 추가 | 이 설계 승인 |
| A-2 | 숨은 실제 주문·지운 초안 개수, 오래 열린 트랜잭션 확인 | **운영** | 읽기만 | **명시 승인 1회** |
| A-3 | production 승격(마이그레이션 포함) | **운영** | 스키마 추가 | **명시 요청** |
| A-4 | 숨은 주문 보이게 하기 또는 휴지통 보내기(결정 2-나·다) | **운영** 데이터 | 데이터 수정 | **별도 명시 승인** |
| B-1 | 확장 설치 + `track_io_timing` | 스테이징 | 서버 설정 | 이 설계 승인 |
| B-2 | 슈퍼유저·preload·설정·서버 시작 확인 | **운영** | 읽기만 | **명시 승인** |
| B-3 | `CREATE EXTENSION pg_stat_statements` | **운영** | 카탈로그 | **명시 승인** |
| B-4 | `ALTER SYSTEM SET track_io_timing = on` + reload | **운영** | 서버 설정 | **명시 승인** |
| B-5 | 아침·오후 스냅샷 4회 + `pg_stat_activity` 표본 | **운영** | 읽기만 | **명시 승인 1회** |
| B-6 | 집계 초기화(기본은 안 함) | **운영** | 통계 초기화 | **명시 승인** |
| B-7 | 인덱스 통계 읽기 → 지우기 마이그레이션 | **운영** | 읽기 → 스키마 삭제 | **각각 명시 승인** |

B-2·B-3·B-4 는 한 번의 승인으로 묶을 수 있다(확인 → 설치 → 설정 순서, 중간 결과를 보고 멈출 수 있게).

## 8. 검증 계획 요약
- A: §3.3 의 1~6. 반영 뒤 운영 7일 `[DashCache] compute_ms` 와 해당 라우트 p50/p95.
- B: 스테이징 설치 뒤 `pg_stat_statements` 상위 10개가 원장 C 트랙의 느린 쿼리(실측 탭 보충 쿼리 등, 이미 고친 것 포함)와 맞는지 대조 — 집계가 살아 있다는 확인. `track_io_timing` 전후 perf-gate 서버 시간 비교.
- 인덱스: 지운 뒤 `EXPLAIN` 으로 해당 화면 계획이 바뀌지 않았는지, 주문 저장 p95 가 같거나 줄었는지.

## 9. 범위
- 바뀌는 파일(승인 후, A): `models.py`, 새 마이그레이션 1개, 새 테스트 2개. B 는 새 도구 2개(`tools/perf/pgss_enable.py`·`pgss_snapshot.py`, 가칭). 인덱스 정리는 별도 설계.
- 이 설계서 밖(발견만, 고치지 않음):
  - **휴지통 복원이 초안 표식을 안 지운다.** `foms/web/orders/trash.py:316` 은 status 를 `original_status or "RECEIVED"` 로 되돌리지만 `meta.draft` 는 그대로다. 스테이징의 지운 초안 35건 중 original_status 가 DRAFT 가 아닌 24건을 복원하면 숨은 주문 4건과 같은 상태(어디에도 안 보이는 주문)가 된다.
  - 정리 크론(`tools/cron/cleanup_order_drafts.py:163`)이 지운 초안의 `meta.draft` 를 남겨 둔다. 추천안 인덱스는 이 행들도 담는다(지금 35행).
  - SQLite 와 PostgreSQL 은 `meta.draft` 가 글자 `"true"` 일 때 판정이 다르다(SQLite 는 거짓, PostgreSQL 은 참). 지금 데이터에는 그런 값이 없다. 기존 차이이고 이번 변경과 무관하다.
  - `notification_events` 는 seq_scan 10,772 · idx_scan 15 다(스테이징). 따로 볼 만하다.

## 부록 A. 측정 방법
- 스테이징 연결: 읽기 전용 강제 헬퍼(`default_transaction_read_only=on`, 운영 호스트 차단, 스테이징 표식 가드). 접속 정보는 출력·저장하지 않았다.
- §1.2 원본 SQL: 원장 10-01 라우트 캡처(앱이 실제로 낸 SQL). 초안 가지 `CAST((orders.structured_data #>> '{meta, draft}') AS BOOLEAN) IS true` 를 `false`(하한), `orders.id IN (39개 id)`(번호 목록 대조), 서브쿼리 형태(인덱스 없음)로 바꿔 쟀다. 결과 행 수는 네 형태 모두 같았다(행 묶음 비교는 §3.3).
- [로컬]: PG 17.9 격리 클러스터(127.0.0.1, 빈 포트). 스테이징 orders 칸 목록과 인덱스 49개 정의(`pg_indexes`)를 복제하고, 합성 4,600행(ERP 약 67%, `structured_data` 글자 길이 중앙 2.3KB · p90 3.6KB · p99 8.5KB · 최대 19.7KB — 스테이징 2.2 · 3.2 · 8.2 · 19.9KB 와 비슷)을 넣었다. 합성 한글은 압축이 덜 돼 TOAST 가 스테이징보다 크다(8.8MB vs 2.3MB). DDL 시간은 `CREATE DATABASE … TEMPLATE` 로 매번 새 사본에서 3회 쟀다.
- 앱 경로 확인: SQLAlchemy 2.0.23 + psycopg 3.2.9 `ClientCursor` 로 새 술어를 그려 EXPLAIN 했다(§2 ③-나 계획).
