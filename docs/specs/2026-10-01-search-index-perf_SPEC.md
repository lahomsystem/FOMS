# 통합 검색·과거 이력 검색 인덱스 SPEC (성능 P1-3)

- 작성: 2026-10-01 · 상태: **승인(2026-10-01, 추천안 그대로) · 구현 `search_trgm_00`** — 남은 일: 스테이징 EXPLAIN(§9-3)으로 플래너가 trgm 을 고르는지 확인 → 운영
- 원장: `docs/plans/2026-10-01-full-perf-audit-ledger.md` P1-3, P3-9
- 기준: origin/deploy `c959fa637` · 스테이징 alembic head `nvmirror_00` · 스테이징 PostgreSQL 17.11 · 스테이징 주문 3,520행 · 운영 주문 4,517행(원장 2026-10-01 기록)
- 표기: **[실측]** 스테이징 읽기 전용 `EXPLAIN (ANALYZE, BUFFERS)` 3회 중 최솟값 · **[대리 추정]** 아직 없는 인덱스 자리에 기존 trgm 인덱스를 타는 비슷한 식을 끼워 잰 값(계획 모양·시간만 의미, 부록 A) · **[로컬]** 로컬 PG 17.9 격리 클러스터 + 합성 6,000행 · **[운영 로그]** 원장 D 트랙

## 0. 사용자 결정 항목

1. **주문번호 일부로 찾기를 남길까?** 지금은 "123" 을 치면 1234번·4123번도 나온다.
   - 가) 남긴다 (추천). 번호 칸에 찾아보기 표를 하나 더 만든다. 결과는 지금과 같다. 표가 약 0.2MB 늘어난다.
   - 나) 번호를 치면 그 번호 하나만 찾는다. 표가 필요 없다. 대신 "123" 으로 1234번이 안 나온다. 스테이징에서 숫자 30개로 시험하니 모두 합쳐 43건이 빠졌다(대부분 0건, 많으면 12건).
2. **전화번호 숫자 검색은 어떻게 빠르게 할까?**
   - 가) 숫자 칸에 글자 조각 표를 만든다 (추천). 가운데 번호로도 지금처럼 찾는다.
   - 나) 끝자리로만 찾게 바꾼다. 표가 작다. 대신 가운데 번호로 못 찾는다. 9월 29일 "통합 검색은 가운데 자리도 찾게" 결정과 부딪힌다.
3. **출고 대시보드 검색이 주문 정보 전체를 뒤지는 것을 남길까?** 이것 하나 때문에 출고 검색은 표를 다 만들어도 0.25초 그대로다.
   - 가) 이번에는 그대로 둔다 (추천, 따로 정한다).
   - 나) 전체 뒤지기를 빼고 시공자 이름처럼 꼭 필요한 칸만 본다. 0.001초대로 줄어든다(추정). 대신 메모 같은 숨은 값으로는 안 걸린다. 어떤 칸이 필요한지 알려 주셔야 한다.
4. **전화번호 통째·날짜처럼 긴 숫자 검색은 표를 만들어도 안 빨라진다.** (스테이징 0.13~0.17초 그대로)
   - 가) 표 만들기를 운영에 먼저 내고, 효과를 잰 뒤 정한다 (추천).
   - 나) 숫자만 친 검색어는 번호·전화·날짜·주소 칸만 본다. 빨라진다(추정 0.001초). 대신 이름·상품 칸 속 숫자로는 안 걸린다. 한 경우는 여전히 0.08초라 불안정했다.
   - 다) 칸마다 따로 찾아 합친다. 결과는 같고 빠르다(추정 0.001~0.005초). 코드가 많이 바뀌고, 1~2글자 검색에 쓰면 오히려 느려져서 3글자 이상에만 쓴다.
5. **배포 순서.** 표 만들기만 담은 커밋을 먼저 스테이징, 그다음 운영으로 낸다 (추천). 스테이징에만 있는 `131f0c3b4`("과거 이력에 N건 더")는 지금 운영에 가면 대시보드 검색마다 0.18초를 더 쓴다. 표가 운영에 깔린 뒤에 올린다.

참고: 1~2글자 검색(예: "김", "서울")은 글자 조각 표의 원리상 빨라지지 않는다. 지금과 같다.

## 1. 문제와 근거

### 1.1 운영 [운영 로그]
#439(`3038c5276`, 09-29 11:19 KST) 이후 `/api/foms/search/fragment` p50 516→636 · p95 757→984ms, `/erp/history` p50 452→657ms, history `page_rows` 417→611ms(+47%).
#439 는 과거 이력·통합 검색의 술어를 `structured_data` 통째 ILIKE 한 가지에서 `erp_order_dashboard_search_predicate`(`foms/services/erp_dashboard_search.py:127`)로 바꿨다. 가지가 19~20개이고 그중 13개가 JSON 경로다. 바뀌기 전에도 `id::varchar ILIKE` 가 있어 인덱스를 못 탔지만, 행마다 JSON 을 한 번 풀었다. 지금은 열세 번 푼다.

### 1.2 원인 [실측]
OR 의 가지 하나라도 인덱스가 없으면 BitmapOr 를 못 만든다. 그러면 후보 행 전부를 읽으며 가지마다 `structured_data` 를 다시 푼다(TOAST). buffers 가 heap(645 pages)의 약 59배가 된다.

| 쿼리 (스테이징) | 지금 | 막는 가지를 뺐을 때 |
|---|---|---|
| 이력 목록 "박성수" | 184.2ms · 38,142 buf | 0.41ms · 96 buf (BitmapOr, 인덱스 15개) |
| 이력 건수 "박성수" | 182.0 · 38,142 | 0.41 · 96 |
| 통합 검색 "박성수" | 183.6 · 38,076 | 0.57 · 96 |
| 통합 검색 "5678" — 4가지만 뺌 | 164.9 · 38,193 | 129.9 · 30,135 (아직 막힘) |
| 통합 검색 "5678" — 4가지 + 전화 숫자 뺌 | | 0.35 · 107 |
| 이력 "5678" (끝 4자리 정규식 경로, `:258-271`) | 46.8 · 8,703 (Seq Scan) | buyer.phone 뺌: 0.13 · 16 |
| 대시보드 고객 검색 "5678" (`customer_contact_only`) | 70.6 · 14,019 | 전화 숫자 대리: 0.2 · 63 [대리 추정] |

"4가지" = id 가지, buyer.name, buyer.phone, manager `->>`. 전화 숫자 가지(`erp_phone_digits LIKE '%x%'`)는 숫자 검색어에만 붙고, 그때는 다섯 번째로 막는다.

## 2. 막는 가지와 정확한 인덱스 식

### 2.1 가지별 인덱스 (정의 출처: migrations, 존재 확인: 스테이징 `pg_indexes`)

| 가지 | 위치 `erp_dashboard_search.py` | 기존 인덱스 | 쓸 수 있나 |
|---|---|---|---|
| `CAST(id AS VARCHAR) ILIKE` | `:190`, `:61` | 없음 | **신규 (결정 1)** |
| `customer_name`·`phone`·`address`·`product` ILIKE | `:191-194` | `ix_orders_*_trgm` (phase_f) | 예 |
| `manager_name` ILIKE | `:195` | `ix_orders_manager_name_trgm` (phase_d) | 예 |
| `erp_phone_digits LIKE '%x%'` | `:45-46` | `ix_orders_erp_phone_digits` **btree** | 아니오 — 앞뒤 `%` 는 btree 불가. **신규 (결정 2)** |
| SD customer.name·phone, orderer.name, site.address_full·main, items[0].product_name·name, schedule 3칸 | `:172-186` | `ix_orders_sd_*_trgm` 10개 (phase_f) | 예 |
| SD manager.name `->>` | `:174` | `ix_orders_sd_manager_name_trgm` 은 `-> 'name'` (phase_e) | 아니오 — 식이 다르다(`->` 는 따옴표 붙은 JSON 문자열). **신규** |
| SD buyer.name·buyer.phone `->>` | `:178-179` (08-20 `872a670ee`) | 없음 | **신규** |
| SD buyer.phone `~` (이력 4자리) | `:261-262` | 없음 | 위 buyer.phone 신규가 함께 해결 (trgm 은 정규식도 탄다) |
| blob `CAST(structured_data AS VARCHAR) ILIKE` | `:205` | `ix_orders_structured_data_text_trgm` 11MB (phase_d) | 있지만 플래너가 안 고른다 (§5) |

`ix_orders_sd_manager_name_trgm`(`->` 형태)은 지울 수 없다. "내 담당" 필터가 그 식을 쓴다(`foms/services/erp_permissions.py:262`, 스테이징 idx_scan 448).
주석 `# perf-ok: ix_orders_sd_customer_name_trgm` 이 buyer·manager 가지에도 붙어 있어(`:197`), 성능 가드(`tools/perf/perf_scan.py`)가 이 누락을 못 잡았다. `:46` 의 btree 주석, `:190` 의 "cold path" 주석도 지금은 사실이 아니다.

### 2.2 앱이 내는 SQL (컴파일 원문)
`str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))` 결과(`%%` 는 pyformat 이스케이프, 실제로는 `%`):

```
CAST(((orders.structured_data -> 'parties') -> 'buyer') ->> 'name' AS VARCHAR) ILIKE '%%x%%'
CAST(((orders.structured_data -> 'parties') -> 'buyer') ->> 'phone' AS VARCHAR) ILIKE '%%x%%'
CAST(((orders.structured_data -> 'parties') -> 'manager') ->> 'name' AS VARCHAR) ILIKE '%%x%%'
CAST(orders.id AS VARCHAR) ILIKE '%%x%%'
orders.erp_phone_digits LIKE '%%' || '1234' || '%%'
CAST((((orders.structured_data -> 'parties') -> 'buyer') ->> 'phone') AS VARCHAR) ~ '1234($|[^0-9-])'
```

전체 술어 안에서는 괄호가 한 겹 더 붙는다(`CAST((((…) ->> 'name') AS VARCHAR)`). 묶음 괄호라 식은 같다.
운영 드라이버(psycopg `ClientCursor`, `foms/services/db_url_resolver.py:89`)는 키와 값에 캐스트를 붙여 보낸다: `CAST(((orders.structured_data -> 'parties'::TEXT) -> 'buyer'::TEXT) ->> 'name'::TEXT AS VARCHAR) ILIKE '%박성수%'::VARCHAR`. 플래너가 상수 캐스트를 접어 같은 식이 된다. 근거: 같은 모양의 기존 `ix_orders_sd_customer_name_trgm` 을 앱 요청이 실제로 탄다(스테이징 idx_scan 72).

### 2.3 만들 인덱스
식은 2.2 와 글자 단위로 같고, 인덱스 DDL 에 쓸 수 없는 테이블 접두 `orders.` 만 뺐다. 표기는 선례 `phase_f_trgm_search_indexes.py` 와 같다.

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_sd_buyer_name_trgm
  ON orders USING gin ((CAST(((structured_data -> 'parties') -> 'buyer') ->> 'name' AS VARCHAR)) gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_sd_buyer_phone_trgm
  ON orders USING gin ((CAST(((structured_data -> 'parties') -> 'buyer') ->> 'phone' AS VARCHAR)) gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_sd_manager_name_text_trgm
  ON orders USING gin ((CAST(((structured_data -> 'parties') -> 'manager') ->> 'name' AS VARCHAR)) gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_erp_phone_digits_trgm
  ON orders USING gin (erp_phone_digits gin_trgm_ops);                         -- 결정 2-가
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_id_text_trgm
  ON orders USING gin ((CAST(id AS VARCHAR)) gin_trgm_ops);                    -- 결정 1-가
```

PostgreSQL 이 저장하는 정의(`pg_get_indexdef`, [로컬]). 스테이징 `ix_orders_sd_customer_name_trgm` 정의와 키 이름만 다르다:
```
USING gin ((((((structured_data -> 'parties'::text) -> 'buyer'::text) ->> 'name'::text))::character varying) gin_trgm_ops)
USING gin (erp_phone_digits gin_trgm_ops)
USING gin (((id)::character varying) gin_trgm_ops)
```

[로컬] 확인: 앱 경로 그대로(psycopg `ClientCursor.mogrify`) 그린 SQL 을 EXPLAIN 했다. 만들기 전에는 인덱스를 하나도 안 탔다. 만든 뒤에는 "cust123"(19가지)·"5678"(20가지)·"01012345678"·이력 4자리 정규식 모두 BitmapOr 였고, 새 인덱스 5개가 전부 쓰였다. `CAST(id AS VARCHAR)` 인덱스도 문제없이 만들어진다(immutable).

## 3. 주문번호 가지 — 결정 1
- 숫자가 아닌 검색어: id 문자열은 숫자뿐이라 이 가지는 절대 맞지 않는다(지금 `_`·`%` 를 이스케이프하지 않아 그것을 친 경우만 예외). 빼도 결과가 같고, 가지가 줄어 플래너가 BitmapOr 를 고르기 쉬워진다. 어느 쪽을 고르든 같이 하기를 권한다(`:190`·`:61` 두 곳).
- 가) trgm 인덱스: 동작 그대로. 3자리 이상 숫자는 인덱스를 탄다("123" 155→1.1ms [대리 추정]). 1~2자리 숫자는 지금처럼 느리다. 크기 184kB/6,000행 [로컬].
- 나) 숫자면 `Order.id == n`: pkey 를 타므로 인덱스가 필요 없다. 부분 번호로는 안 나온다. 스테이징 숫자 30개(100~4759) [실측]: 빠지는 행 합 43, 중앙값 0, 최대 12. 통합 검색 분류기도 `str(order.id)` 부분 일치로 판정하므로(`foms/services/foms_unified_search.py:244`·`:257`) 같이 고쳐야 화면이 맞는다. 과거 이력의 숫자 4자리 경로는 이미 정확 일치다(`:265`).
- 앞자리 일치(`LIKE 'n%'`)는 인덱스가 따로 필요하고 4123번은 여전히 빠져서 선택지에서 뺐다.

## 4. 전화 숫자 가지 — 결정 2
- 숫자 4자리 이상이고 숫자 비율이 50% 이상이면 붙는다(`foms/services/phone_search.py:41-61`). 통합 검색, 대시보드 고객 검색(`foms/services/orders/dashboard_read_model.py:76`), 채널톡(`foms/api/channel/messages.py:93`), 네이버 후보(`order_candidates.py:1307`) 모두 해당한다.
- 가) trgm: 동작 그대로. 대시보드 고객 검색 "5678" 70.6→0.2ms, "01012345678" 69.1→0.5ms [대리 추정]. 하이픈이 든 "010-1234-5678" 은 68.7ms 그대로(§6). 크기 336kB [로컬]. 기존 btree 는 둔다(idx_scan 521, 정확 일치 조회용).
- 나) 끝자리 전용(뒤집은 문자열 btree): 가운데 번호 검색이 사라진다. 이는 2026-09-29 사용자 결정(`foms_unified_search.py:89-98`)과 충돌한다. 번호가 여럿인 주문(22~23자리)은 앞 번호의 끝자리로 못 찾는다. 추천하지 않는다.

## 5. 통째 문자열 가지(blob) — 결정 3
- `include_structured_data_blob=True` 를 넘기는 곳은 출고 대시보드 하나다: `foms/web/shipment/dashboard.py:129-139` `_erp_order_search_filter`(호출 `:349`). 과거 이력·통합 검색은 #439 이후 쓰지 않는다. 실측 탭의 blob(`erp_measurement_main_search_predicate`, `:80`)은 P1-1 별건이다.
- blob 인덱스가 있어도 플래너가 고르지 않는다. blob 단독 "박성수" 106.7ms Seq Scan [실측].
- 인덱스 5개를 만든 뒤에도 blob 을 남기면 "박성수" 258.7→264.5ms 그대로다. blob 을 시공자 경로(`shipment.construction_workers`, 기존 `ix_orders_sd_construction_workers_trgm` 과 같은 `->` 식)로 바꾸면 0.5~1.5ms다 [대리 추정]. 스테이징에서 시공자 값이 있는 주문은 990건이다.
- 나)를 고르면 시공자 말고 어떤 깊은 칸을 찾는지 확인이 필요하다. 각 칸의 식은 기존 인덱스와 같거나 새 인덱스가 있어야 한다.

## 6. 인덱스만으로 안 빨라지는 검색 — 결정 4
5개를 다 만든 상태를 흉내 냈다 [대리 추정]. 값은 이력 / 통합 순서다.

| 검색어 | 지금 | 인덱스 후 |
|---|---|---|
| 박성수 · 성수동 | 179/158 · 161/162ms | 0.5/0.6 · 0.4/0.6ms |
| 래미안 · 용인시 수지구 | 156/158 · 155/152 | 1.6/1.7 · 1.4/2.0 |
| 123 · 12345 · 5678(통합) | 155/153 · 166/167 · 175 | 1.1/1.3 · 0.5/0.5 · 0.5 |
| 서울 · 김 | 154/129 · 153/127 | 140/137 · 137/128 |
| 010-1234 · 01012345678 | 164/153 · 159/160 | 157/163 · 167/161 |
| 010-1234-5678 · 2026-10-01 | 159/158 · 174/186 | 153/161 · 162/159 |

- 1~2글자: trgm 은 연속 3글자가 있어야 인덱스를 쓴다. 원리상 한계다.
- 7자리 이상 숫자(하이픈 포함): 글자 조각이 많아 가지마다 인덱스 비용 추정이 90~108로 커진다. 그래서 플래너는 "ERP 행을 전부 읽고 거르기"가 더 싸다고 본다. 플래너는 JSON 풀기 비용을 모른다. 대리가 아닌 직접 증거 [실측]: 막는 가지를 다 빼서 남은 15가지가 모두 인덱스를 가진 상태에서도 "01012345678" 은 129.7ms · 30,135 buf 였고 BitmapOr 를 타지 않았다.
- 운영(4,517행)은 스테이징보다 커서 경계가 조금 다를 수 있다. [로컬] 합성 6,000행에서는 "01012345678" 도 BitmapOr 를 골랐다.
- 나) 숫자·하이픈만 친 7자리 이상 검색어는 번호 관련 가지만 본다: 주문번호, 전화 숫자, 전화, SD 고객·구매자 전화, 실측일, 시공일, 주소 3칸. 주소를 빼면 0.3~0.7ms, 넣으면 0.5~1.2ms다. 다만 "010-1234-5678" 통합은 82ms 로 불안정했다 [대리 추정]. 동작 변화 [실측]: 실제 전화·날짜 검색어 75개(결과 130행)에서 빠지는 행은 0이었다. 음성 대조군인 주소 속 숫자 조각(동·호수, 번지) 5개는 주소 칸을 빼면 6행 중 5행이 빠졌다. 그래서 주소 칸은 넣어야 한다.
- 다) 가지별로 따로 찾아 id 로 합친다(`id IN (SELECT … UNION …)`). 결과는 그대로다. 긴 숫자 0.9~4.6ms, 래미안 18.5ms, 1~2글자 257~277ms(지금보다 느림)다 [대리 추정]. 그래서 3글자 이상에만 쓴다. 술어 생성기 구조가 바뀐다.

## 7. 마이그레이션 방식
- 파일 1개(가칭 `migrations/versions/search_trgm_00_visible_field_indexes.py`). `down_revision` 은 구현 시점의 head다(지금 `nvmirror_00`, `python -m alembic heads` 로 다시 확인).
- 선례를 그대로 따른다. `phase_f_trgm_search_indexes.py`(이름→식 사전 + `_run_concurrently`), `index_ops_00_dedup_indexes.py:103-111`(AUTOCOMMIT 연결이면 바로 실행 — PG 레인 테스트용). 먼저 `CREATE EXTENSION IF NOT EXISTS pg_trgm` 을 실행한다. CONCURRENTLY 는 반드시 `op.get_context().autocommit_block()` 안에서 실행한다. 문자열 COMMIT 은 psycopg3 에서 실패하므로 금지다. PostgreSQL 이 아니면 건너뛴다(`add_orders_erp_stage_updated_at.py:31`·`:43` 방식).
- INVALID 처리: `IF NOT EXISTS` 는 실패로 남은 INVALID 인덱스도 "있다"고 보고 건너뛴다. 그래서 만들기 전에 `pg_index.indisvalid = false` 이면 `DROP INDEX CONCURRENTLY IF EXISTS` 를 하고 다시 만든다. 만든 뒤에도 valid 가 아니면 예외를 낸다. 그러면 predeploy `set -e` 때문에 배포가 라이브되지 않고, 옛 버전이 계속 돈다.
- 실행 위치: web 서비스 `preDeployCommand = "sh predeploy.sh"`(`railway.toml:12`) → `alembic upgrade head`(`predeploy.sh:22`). WORKER 는 건너뛴다. 세션 advisory lock(`migrations/env.py:137`)이 동시 실행을 막는다.
- 잠금: CONCURRENTLY 는 읽기·쓰기를 막지 않는다. 대신 그 전에 열린 트랜잭션이 끝날 때까지 기다린다. 마이그레이션에는 lock_timeout 이 없다. 배포 직전 `pg_stat_activity` 에서 오래 열린 트랜잭션이 없는지 본다.
- 소요: 인덱스 하나 22~42ms [로컬]. 운영 4,517행 기준 5개를 합쳐도 대기 시간을 빼면 수 초 이내 [추정].
- 크기 [로컬]: buyer name·phone 각 24kB(값 있는 주문이 적다 — 스테이징 11건), manager 96kB, 전화 숫자 336kB, id 184kB. 합계 약 0.66MB로 orders 인덱스 28MB 의 약 2%다.
- 되돌리기: `downgrade()` 는 역순으로 `DROP INDEX CONCURRENTLY IF EXISTS` 를 한다. 결과는 인덱스 유무와 상관없고 속도만 달라지므로 언제 지워도 안전하다. 긴급할 때는 psql 에서 트랜잭션 밖으로 한 줄씩 지운다.
- PG 레인 왕복 테스트(`tests/postgres/test_migration_chain.py:187`: create_all → stamp → downgrade `index_ops_00` → upgrade)는 인덱스 추가를 허용한다. 처음 상태에는 이 인덱스가 없으므로 downgrade 는 반드시 `IF EXISTS` 여야 한다.

## 8. 쓰기 비용 (원장 P3-9)
- 스테이징 [실측]: orders 인덱스 44개 28MB, 본체 5.2MB, TOAST 2.3MB. 갱신 1,366회 중 HOT 은 251회(non-HOT 81.6%).
- 새 인덱스는 이미 인덱스가 걸린 칸(`structured_data`·`erp_phone_digits`·`id`)만 본다. HOT 여부는 "인덱스 걸린 칸이 바뀌었나"로 정해지므로 HOT 비율은 바뀌지 않는다. 늘어나는 것은 non-HOT 갱신마다 GIN 항목 5개(결정 1-나면 4개, GIN fastupdate 대기 목록에 붙임)와 JSON 경로 계산 3번이다. 저장 요청당 1ms 미만으로 본다 [추정]. 확인 방법은 §9-6.

## 9. 검증 계획
1. 계약 테스트(신규, PG 레인): `erp_order_dashboard_search_predicate`(전체·고객 연락처만)와 `visible_order_search_clause`(4자리 정규식)를 psycopg 방언으로 그린다. `enable_seqscan=off` 로 EXPLAIN 해 BitmapOr 이고 Bitmap Index Scan 수가 가지 수와 같은지 단언한다. `872a670ee` 처럼 인덱스 없는 가지가 다시 들어오면 실패한다. `perf-ok` 주석(`:46`·`:190`·`:197`)도 실제 인덱스 이름으로 고친다.
2. 스테이징 배포 직후: 새 인덱스 전부 `pg_index.indisvalid = true`.
3. 같은 EXPLAIN 묶음을 다시 잰다(§1.2 표, §6 표의 3글자 이상 행). BitmapOr, 3ms 미만, 300 buf 미만이면 합격이다. §6 의 "안 빨라지는 행"은 그대로인 것이 정상이다(오판 방지).
4. 결과 동일성: 스테이징 실데이터 검색어(이름 60·주소 60·전화 60·날짜 15)로 이력·통합·대시보드 결과 id 집합이 인덱스 전후로 같아야 한다. 음성 대조군도 넣는다: 술어를 일부러 바꾼 비교에서 차이를 잡아야 검사가 살아 있는 것이다. 결정 1-나를 고르면 숫자 검색어의 "id 부분 일치로만 걸린 행" 차이만 허용한다.
5. 운영 승격 후 7일: Railway HTTP 로그의 `/api/foms/search/fragment`·`/erp/history` p50/p95, `[DashCache] slice=page_rows compute_ms` 를 #439 이후 값(636/984 · 657 · 611)과 비교한다. 목표는 #439 이전(516/757 · 452 · 417) 이하다. 1~2글자·긴 숫자 검색 비중만큼 덜 내려갈 수 있다(운영 로그에 검색어가 없어 비중은 모른다).
6. 쓰기: `pg_stat_user_tables` HOT 비율과 주문 저장 라우트 p95 를 전후로 비교한다. 변화가 없어야 정상이다. 새 인덱스와 product·items0·meas_date trgm 의 idx_scan 은 늘어야 한다(P3-9 "0회" 해소).

## 10. 승격 순서 — 결정 5
1. 커밋 A: 마이그레이션 + 계약 테스트 + 주석 정정. 결정 1-나·3-나·4-나/다의 코드 변경은 별도 커밋으로 낸다.
2. 스테이징에서 §9-2~4 를 확인한다. 운영 승격은 사용자가 명시 요청할 때만 한다.
3. `131f0c3b4` 주의: 대시보드 검색(1쪽, 결과 있음)마다 `_history_more_link`(`foms/web/orders/dashboard.py:94-104`)가 이력 술어로 count 를 한 번 더 한다. 스테이징 [실측] 182ms · 38,142 buf 다. 커밋 A 가 운영에 깔린 뒤에 올린다.

## 11. 범위
- 바뀌는 파일(승인 후): 새 마이그레이션 1개, `foms/services/erp_dashboard_search.py`(주석·id 가지), 테스트 1~2개. 결정에 따라 `foms_unified_search.py`·`foms/web/shipment/dashboard.py` 가 추가된다.
- 이 설계서 밖:
  - 실측 탭 blob(P1-1 별건).
  - "내 담당" 필터의 도면 가지 blob LIKE(`erp_permissions.py:268`, 측정 안 함).
  - 주문 목록 `foms/web/orders/listing.py:190`: 같은 술어에 `received_date`·`options`·`status` LIKE 같은 인덱스 없는 가지가 더 붙어 있어 이번 인덱스로 안 풀린다.
  - 안 쓰는 인덱스 정리(P3-9).

## 부록 A. 측정 방법
- 스테이징 연결: 읽기 전용을 강제하는 헬퍼(`default_transaction_read_only=on`, 운영 호스트 차단, TESTCLR 가드). 같은 쿼리를 4회 실행해 첫 회는 버리고, 나머지 3회 중 최솟값을 쓴다.
- 원본 SQL: 라우트 캡처(`/erp/history?q=…`, `/api/foms/search?q=…`)와 `erp_order_dashboard_search_predicate` 컴파일(literal binds). 기준 조건(`status != 'DELETED'`, `deleted_at IS NULL`, 초안 제외, 통합은 `is_erp_order`)과 정렬·LIMIT 은 캡처와 같다.
- 대리 인덱스(아직 없는 인덱스 흉내): id → `orders.notes ILIKE`, buyer.name → `orders.regional_memo ILIKE`, buyer.phone → `CAST((structured_data -> 'shipment') -> 'construction_workers' AS VARCHAR) ILIKE`, manager `->>` → 같은 경로의 `->` 식, 전화 숫자 → `orders.measurement_date ILIKE`. 모두 기존 trgm 인덱스가 있는 식이다. 결과 행은 달라지므로 시간·buffers·계획 모양만 의미가 있다.
- 로컬: PG 17.9 격리 클러스터(127.0.0.1, 합성 6,000행)에 스테이징과 같은 trgm 인덱스와 새 인덱스 5개를 만들었다. 앱 경로 그대로 그린 SQL 의 EXPLAIN 으로 사용 여부를 확인했다. 크기·소요 시간도 이 클러스터 값이다.
