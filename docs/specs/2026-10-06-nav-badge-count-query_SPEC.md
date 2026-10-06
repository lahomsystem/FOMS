# 하단 메뉴 배지 개수 쿼리 SPEC (성능 P3-1 후속)

- 작성: 2026-10-06 · 상태: **승인됨 — 배지(§3, deploy `2a3df97c`)·실측 목록(§8) 스테이징 반영, 운영은 실측 목록과 함께 승인 대기**
- 원장: `docs/plans/2026-10-01-full-perf-audit-ledger.md` P3-1 · 앞선 설계서 `docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md`(초안 표식, PR #499)
- 기준: origin/deploy `562df32d7` · 스테이징 PostgreSQL 17.11 · 스테이징 주문 3,524행(ERP 2,349, ERP·삭제 아님 2,009) · 본표 645블록, TOAST 포함 4,558블록 · `structured_data` 평균 1,582바이트(최대 5,297)
- 표기: **[실측]** 스테이징 읽기 전용 `EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)` 2~3회 중 최솟값 · **[운영]** 10-06 pg_stat_statements 스냅숏(읽기만, 이 작업에서 새로 접속하지 않음) · **[추정]** 계산으로 낸 값
- 이 설계서를 쓰는 동안 스테이징 DB 에는 읽기만 했다(`default_transaction_read_only=on`). 운영 DB 에는 접속하지 않았다. 측정 스크립트는 세션 임시 폴더 `navbadge2/m1.py·m2.py·m3.py`(사용자 이름은 출력하지 않고 번호만 기록).

## 0. 사용자 결정 항목

1. **배지 "내 주문" 조건의 모양** — 가) 조건마다 "번호 목록"을 따로 뽑아 합친 뒤 그 목록에 있는지만 본다(추천, 3.1). 나) 문서를 한 번만 풀어 읽는 울타리(3.2 대안). 다) 그대로 두고 캐시만 넓힌다(3.4 대안).
2. **같은 "내 주문" 조건을 쓰는 다른 화면**(실측 대시보드 목록 — 운영 총시간 1위, 평균 1,109ms)에도 같은 모양을 넓힐지 — 이번 설계서는 배지만 바꾸고, 넓히기는 따로 재서 정한다(추천).

## 1. 문제와 근거

### 1.1 지금 쿼리

`foms/services/dashboard_counts.py` `compute_nav_badge_counts` → `GROUP BY orders.status`.
- 공통: `Order.active_filter()`(삭제 제외 + 초안 제외) AND `is_erp_order IS true`
- `mine_only`(팀 SALES·MEASURE·CONSTRUCTION) 이면 `foms/services/erp_permissions.py` `build_mine_sql_filter(user)` 조건들을 **OR 하나로** 붙인다. SALES 범위 조건 7개:
  - #0 `manager_name ILIKE 이름` · #1 `structured_data->parties->manager->name` 글자 ILIKE · #2 `->workflow->current_quest->owner_person` ILIKE
  - #3~#5 같은 세 개를 아이디(username)로 한 번 더
  - #6 `->assignments->sales_assignee_user_ids` 글자에 ILIKE **6번**(`[50]`, `[50,`, `, 50,` …)
- 조건 하나하나에는 trgm 인덱스가 있다(`ix_orders_manager_name_trgm`, `ix_orders_sd_manager_name_trgm`, `ix_orders_sd_owner_person_trgm`, `ix_orders_sd_sales_ids_trgm`).
- 호출: `foms/services/context_processors.py:404` `inject_foms_nav_badges` — 거의 모든 화면. 캐시는 프로세스 메모리 30초, 키 `(user.id, mine_only)`.

### 1.2 초안 판정(PR #499)은 배지에 적용되어 있다 [실측]

배지 쿼리 계획에 `SubPlan 1 → Index Only Scan using ix_orders_meta_draft_true`(39행, 14블록) 가 보인다. 바깥 행은 초안 표식을 풀어 읽지 않는다. 다만 **운영 pgss 의 696ms 문장은 옛 꼴**이다: 10개 배지 변형 모두 글자가 `… OR C`(= `CAST(structured_data #>> …)`) 로 끝나고, pgss 누적 시작은 2026-08-25 이다. 즉 696ms 는 PR #499 반영(10-05) 전 6주 누적 평균이다. 아래 1.3 에서 보듯 초안 판정은 배지 비용의 작은 몫이라 결론은 바뀌지 않는다.

### 1.3 분해 측정 — SALES 사용자 id 50 (내 주문 308건) [실측]

| 변형 | 시간 | 공유 블록 |
|---|---|---|
| A 지금(mine=True) | **94.0ms** | **23,267** |
| B mine=False | 2.8ms | 659 |
| C A + 옛 초안 판정(운영 pgss 문장 꼴) | 97.1ms | 25,942 |
| D B + 옛 초안 판정 | 16.7ms | 3,334 |
| E A 에서 초안 판정 뺌 | 90.1ms | 23,253 |
| F 조건 #0(manager_name) 만 | 1.3ms | 310 |
| G JSON 조건 6개만(OR) | 3.8ms | 922 |
| H 조건 1개씩(#0~#6) | 0.1~3.8ms | 6~752 |
| I 울타리(3.2) | 24.1ms | 3,348 |

- 초안 판정 몫: A−E = 4ms·14블록. 옛 꼴이어도 +3ms·+2,700블록. **범인이 아니다.**
- 조건 하나씩은 모두 4ms 이하, 합쳐도 약 10ms. 그런데 **OR 로 묶으면 94ms·23,267블록** 이다.

### 1.4 원인 [실측, 계획]

A 의 계획: `Bitmap Index Scan on ix_orders_is_erp_order`(2,490행) → `Bitmap Heap Scan`, OR 묶음 전체가 **Filter** 로 행마다 계산된다(`Rows Removed by Filter: 2,041`). trgm 인덱스는 하나도 안 쓴다. 조건 1개일 때는 `BitmapAnd(ix_orders_sd_manager_name_trgm, ix_orders_is_erp_order)` 로 인덱스를 쓴다.

- 플래너는 ILIKE 7묶음(실제 ILIKE 12개)의 OR 를 BitmapOr 로 만들지 않고 행 필터로 고른다. 비용 모형이 JSONB TOAST 풀기 비용을 모른다.
- 행 필터에서는 `structured_data -> …` 참조마다 TOAST 를 다시 푼다. ERP 행 약 2,350 × JSON 참조 최대 10개(#6 만 6번) = 행당 약 10블록 → 23,000블록. 운영(주문 4,570행, 사용자 이름이 JSON 에 더 많이 걸림)에서는 호출당 약 11만 블록·696ms [운영].
- 즉 원인은 **"내 주문" 조건 OR 묶음이 인덱스를 못 타고 행마다 JSONB 를 여러 번 푸는 것**이다. 초안 판정도, 디스크도 아니다(디스크 읽기 0).

참고(배지 밖): DRAWING·관리자(scope drawing/all)는 `_json_like_condition`(문서 전체 글자 ILIKE)이 들어가 250~400ms 다. 이 팀들은 배지에서 mine_only 가 아니므로(MINE_ONLY_TEAMS 밖) 배지 비용이 아니다. 대시보드 목록 쪽 과제다.

## 2. 선택지 비교 [실측]

같은 사용자들에 대해 시간(공유 블록).

| 사용자(팀·범위·조건 수) | 지금 | ① 번호 목록 UNION (추천) | ② 번호 목록 OR | ③ 울타리 |
|---|---|---|---|---|
| 25 SALES·sales·7 | 123.3 (22,767) | **7.5 (1,860)** | 10.3 (2,145) | 24.0 (3,348) |
| 27 SALES·sales·7 | 92.8 (23,497) | **6.7 (1,781)** | 8.9 (2,056) | 23.3 (3,348) |
| 47 SALES·sales·7 | 94.1 (23,967) | **6.4 (1,536)** | 6.5 (1,536) | 30.9 (3,348) |
| 24 CONSTRUCTION·8 | 0.8 (250) | 3.0 (792) | 3.0 (792) | 23.2 (3,348) |
| 28 CONSTRUCTION·8 | 1.7 (369) | 3.2 (807) | 2.8 (807) | 23.6 (3,348) |
| 20 CS·sales·7 | 0.3 (101) | 0.4 (101) | 2.5 (760) | 22.5 (3,348) |
| 41 ACCOUNTING·sales·7 | 0.3 (121) | 0.5 (121) | 2.9 (780) | 23.0 (3,348) |
| 40 DRAWING·drawing·5 | 252.0 (26,819) | 206.7 (8,038) | 211.6 (8,038) | 174.6 (3,348) |
| 58 ADMIN·all·14 | 397.2 (59,801) | 226.0 (8,037) | 209.6 (8,037) | 185.2 (3,348) |
| mine=False (모든 팀 공통) | 2.8 (659) | 바뀌지 않음 | 바뀌지 않음 | 2.8 (659) |

- ① `orders.id IN (SELECT id FROM orders om WHERE 조건1 UNION SELECT id … WHERE 조건2 …)` — 갈래마다 자기 trgm 인덱스를 탄다. SALES 94→7ms(약 13배), 블록 92% 감소. 이미 빠른 사용자(CONSTRUCTION 1→3ms)는 몇 ms 늘지만 무시할 만하다.
- ② `id IN (…조건1) OR id IN (…조건2) …` — ①과 비슷하나 해시 하위계획이 갈래마다 생겨 빈 결과 사용자에서 조금 더 든다.
- ③ 울타리(`structured_data #> '{}'` + `OFFSET 0`, `foms/services/common/jsonb_projection.py` 선례 방식) — 문서를 행당 1번만 풀지만 ERP 행 전부를 푼다. 하한이 22ms·3,348블록이라 지금 0.3ms 인 사용자를 70배 느리게 만든다. 문서 전체 ILIKE 가 있는 DRAWING/all 에서만 가장 빠르다.
- ④ 전체 GROUP BY 1회 후 파이썬 분류: 필요한 경로 7개만 투영하는 울타리 쿼리 1회 = 19.3ms·3,348블록. 30초에 한 번(사용자 무관) 돌리면 DB 비용은 가장 적다. 하지만 ILIKE·글자 꼴(`", 50,"` 등) 판정을 파이썬에 **두 번째 정의**로 옮겨야 하고(`build_mine_sql_filter` 와 갈라질 위험), 사용자 수와 무관하게 행 2,000여 개를 프로세스마다 들고 있어야 한다. **불가능하지는 않지만 추천하지 않는다.** 동일성은 이번에 재지 않았다.
- ⑤ 캐시 공유(Redis): 쿼리 한 번 값은 그대로이고 횟수만 프로세스 수만큼 준다. 사용자별 키라 효과는 "같은 사용자가 30초 안에 다른 프로세스를 맞는" 경우뿐이다. ①과 함께 쓸 수는 있으나 ① 뒤 7ms 수준이면 필요 없다.
- ⑥ 담당자 사본 칸(정규화 컬럼): 가장 빠르지만 쓰기 경로 전부에 채우기·백필·마이그레이션이 필요하다. ①로 충분하면 하지 않는다.

## 3. 추천안 ① 설계

### 3.1 코드 (승인 후)

- `foms/services/dashboard_counts.py` `_apply_mine_filter` 만 바꾼다. `build_mine_sql_filter(user)` 가 주는 조건 목록은 그대로 쓴다(정의 한 곳 유지).
  - `om = Order.__table__.alias("orders_mine")` 로 별칭을 만들고, 조건마다 `sqlalchemy.sql.util.ClauseAdapter(om).traverse(cond)` 로 별칭에 옮겨 `select(om.c.id).where(…)` 를 만든 뒤 `union(*sels)` 로 묶어 `Order.id.in_(…)` 하나로 붙인다.
  - 별칭을 쓰는 이유는 PR #499 와 같다: 안팎 이름이 겹치지 않아 상관(correlate) 여지가 없고, 그린 SQL 에서 "바깥 `orders.structured_data` 를 읽지 않는다"를 글자로 검사할 수 있다.
  - 조건이 비면 지금처럼 `Order.id == -1`.
- `build_mine_sql_filter` 의 다른 호출(대시보드·검색·실측 등)은 이번에 건드리지 않는다(결정 2).
- `#6`(아이디 배열 6패턴)은 갈래 안에서 OR 로 남는다 — 같은 인덱스 하나라 BitmapOr 가 되거나 작은 행 집합에서 거른다. 따로 손대지 않는다.

### 3.2 대안 ③ 울타리 — 채택하지 않는 이유
위 표 그대로: SALES 는 4배 빨라지나 CS·ACCOUNTING·CONSTRUCTION 은 1ms → 23ms 로 나빠진다.

### 3.3 기대 효과 [추정]
- 스테이징 SALES 94ms → 7ms. 운영은 블록 비율(약 92% 감소)을 그대로 적용하면 호출당 11만 → 약 9천 블록, 696ms → 약 40~60ms(운영이 스테이징보다 행·일치 건수가 많아 갈래당 비용이 더 크다고 보고 넉넉히 잡음).
- ctx≥300ms 요청 457건 전부의 1순위 원인이 이것이었다(재측정 원장). 화면당 약 0.6초 감소 기대.
- 운영 반영 뒤 pgss 의 새 queryid(글자에 `orders_mine` 이 들어간 문장)의 평균으로 확인한다.

## 4. 동일성 검증 [실측]

- 방법: 같은 트랜잭션·같은 사용자로 지금 쿼리와 후보 쿼리를 둘 다 실제로 돌려 `(status, count)` 목록을 정렬해 통째로 비교.
- 대상 14명(SALES 3, CONSTRUCTION 2, DRAWING 2, CS 2, ACCOUNTING 2, ADMIN 3 — 팀 없음/빈 팀 포함; 스테이징에 MEASURE 활성 사용자는 없음) × mine=True: ①·②·③ 모두 **14/14 일치**(SALES 내 주문 293·300·222건, CONSTRUCTION 8·17, DRAWING 33·15, ADMIN 22 등 0 아닌 경우 포함).
- mine=False: 쿼리가 바뀌지 않는다(①은 mine 갈래만 바꿈). ③ 꼴로 바꿔도 총 2,005건, 상태별 일치.
- 이유: `id` 는 기본 키라 NULL 이 없고, "행이 조건 i 를 만족" ⇔ "id 가 조건 i 의 번호 목록에 있다"이므로 OR ⇔ 합집합이다. 세 값 논리도 `IN` 이 참·거짓만 내어 OR 의 NULL(=거짓 취급)과 같다.

## 5. 테스트 계획

1. 기존 `tests/domains/test_foms_nav_badges.py` 전부 그대로 통과(SQLite 레인 — UNION 은 표준 SQL).
2. 새 계약 테스트: 배지 SQL(PostgreSQL 방언으로 그린 글자)에 `orders_mine` 별칭이 있고 바깥 `orders.structured_data` 참조가 없다.
3. 동치 시험(PG 레인): 합성 주문 + 사용자 여러 명(이름이 manager_name 에만 / JSON 경로에만 / 아이디 배열에만 / 아무 데도 / 여러 곳 동시)으로 옛 OR 와 새 UNION 의 `(status, count)` 일치.
4. 앱 import `APP_OK`, `scripts/ops/pre_push_smoke.ps1` exit 0.
5. 스테이징 반영 뒤 이 설계서의 m3 스크립트를 다시 돌려 표 2와 4를 갱신.

## 6. 되돌리기

- 코드 한 함수(`_apply_mine_filter`) 되돌림 커밋 1개. 스키마·데이터 변경이 없어 마이그레이션 되돌림 없음.
- 캐시는 메모리 30초라 배포만으로 비워진다.

## 7. 운영 반영 순서

1. 사용자 승인(결정 1·2).
2. 구현 + 테스트(5절) → deploy 푸시 → CI green.
3. 스테이징에서 m3 재측정(시간·동일성).
4. 사용자 명시 요청 시에만 production 승격(이 세션 커밋만 cherry-pick + PR).
5. 운영 반영 다음 날 pgss 에서 새 queryid 평균·블록 확인(읽기만, 사용자 요청 1건당 1회). 기대: 평균 100ms 이하, 호출당 1만 블록 이하.
6. 결과에 따라 결정 2(대시보드 목록 등 다른 호출부) 별도 설계.

## 8. 실측 목록 확대(2026-10-06 사용자 승인)

**바꾼 것.** 공통 헬퍼 `mine_membership_clause(conds)` 를 `foms/services/erp_permissions.py` 에 두고(빈 목록이면 None, `__all__` 공개), 배지 `_apply_mine_filter` 와 실측 경로 5곳이 같이 쓴다 — 정의 한 곳.
- `foms/web/measurement/dashboard.py` 메인 목록, `foms/services/measurement_read_model.py` 패널·패널 보조·행 보조, `foms/services/measurement_undated.py` 날짜 미정 목록.
- 빈 조건 의미는 호출부 그대로: 실측 경로는 필터 없음, 배지는 0건(`Order.id == -1`). 바깥 쿼리는 모두 `Order`(일정 조인은 `Order.id` 멤버십에 영향 없음).
- 다른 화면(대시보드·이력·시공·도면)은 손대지 않았다.

**스테이징 측정 [실측]** (읽기 전용, 코드가 그리는 SQL·바인딩 그대로, `EXPLAIN (ANALYZE, BUFFERS)` 3회 중 최솟값, ms, SALES 9·CONSTRUCTION 10명 = 19명):

| 경로 | OR 중앙값 / 최대 | UNION 중앙값 / 최대 |
|---|---|---|
| 메인 목록(날짜 미선택, 60일 창) | 0.8 / 42.8 | 3.9 / 8.6 |
| 패널(오늘~14일) | 0.5 / 43.8 | 0.4 / 3.4 |
| 하루 목록 | 0.1 / 0.5 | 0.1 / 0.2 |
| 날짜 미정 목록 | 1.0 / 19.9 | 3.8 / 8.0 |

- 담당 주문이 많은 SALES(250건대)는 메인 37~43 → 7~8ms, 패널 34~44 → 0.1~0.2ms, 미정 18~20 → 7~8ms.
- 담당이 0~2건인 시공 사용자는 0.5~1ms → 3.5~4.5ms 로 몇 ms 늘었다(갈래 고정 비용). 절대값이 작아 수용.
- 스테이징은 일정 행이 적어 하루·패널 목록이 비어 있다 — 운영 큰 값(pgss 평균 1,109ms)의 재현은 아니다. 운영 반영 뒤 pgss 로 다시 잰다.

**동일성 [실측].** mine 조건이 있는 활성 사용자 31명(SALES 9·CONSTRUCTION 10·CS 7·DRAWING 3·ACCOUNTING 2) × 4경로 = 124건 주문 번호 목록 전후 동일(124/124).

**테스트.** `tests/domains/test_measurement_mine_union.py` — 실측 소스에 `or_(*mine)` 잔존 금지, PostgreSQL SQL 의 `orders_mine` 갈래 수, 빈 목록 None, OR 꼴과 번호 집합 동일(양성 매칭 포함).

## 부록 A. 측정 방법

- 쿼리는 SQLAlchemy 로 psycopg2 방언에 그려 바인딩 파라미터로 실행(literal_binds 안 씀). `import foms.platform` 을 먼저 불러 순환 import 를 피했다.
- 사용자는 스테이징 `users` 의 활성 사용자에서 번호로만 골랐다. SALES 대표(id 50)는 내 주문 건수가 가장 많은 사람.
- 계획 확인은 `EXPLAIN (ANALYZE, BUFFERS, SERIALIZE, COSTS OFF)` 의 글자 출력, 리터럴 값은 가렸다.
