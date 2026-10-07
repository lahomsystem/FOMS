# "내 주문" 조건 — 범위 있는 화면 7곳 빠르게 (설계서)

- 날짜: 2026-10-07 · 상태: 승인됨 — 스테이징 구현 · 선행: `docs/specs/2026-10-06-nav-badge-count-query_SPEC.md` §8·§9
- 측정: 스테이징 DB 읽기 전용(`default_transaction_read_only=on`), EXPLAIN ANALYZE 3회 최솟값, 기준 커밋 `8bc5fc8c9`
- 측정 스크립트(저장소 밖): `scratchpad/mscope/m1.py`, 결과 원문 `scratchpad/mscope/out1.txt` (2회 실행, 수치 안정 확인)

## 1. 문제

배지·실측·이력·검색·도면 작업대는 `mine_membership_clause(conds)`(조건마다 `orders_mine` 별칭에서 id 를 뽑아 UNION → `Order.id IN (...)`)로 바꿔 운영 배지가 691→221ms 로 줄었다.
그러나 아래 7곳은 바깥에 "최근 60일·단계·상태" 같은 범위 조건이 있다. 지금의 `or_(*conds)` 는 범위 안의 몇백 행만 검사하지만,
UNION 갈래는 범위 밖 전체 주문을 훑는다. 특히 도면 담당 조건 중 "문서 전체 ILIKE + 최상위 drawing_assignees 토큰" 갈래가
전체 문서를 읽어 도면팀·관리자가 +38~+198ms 느려졌다. 그래서 7곳은 OR 로 되돌려 두었다.

## 2. 화면별 바깥 범위표

| # | 화면 | 위치 | 바깥 범위(“내 주문” 앞에 붙는 조건) |
|---|------|------|------------------------------|
| 1 | CS 완료 큐 | `foms/api/cs/dashboard.py:57` `_apply_mine_filter` | `active_filter()` + `is_erp_order` + `status IN TARGET_STATUSES`(완료·AS 계열) (`_completion_base_query`, 81행) |
| 2 | 타워 기본(시공팀 강제) | `foms/services/orders/dashboard_control_tower.py:191` `_tower_base_query` | `dashboard_active_filter(days=60)` + `is_erp_order` |
| 3 | 타워 내 담당 진행중 수 | 같은 파일 598행 `_mine_open_count` | 2번 범위(+ `_apply_mine_only` 적용 시 그 조건) + `erp_stage_code IS NULL OR NOT IN ('COMPLETED','AS_COMPLETED')` |
| 4 | 타워 "내작업" 토글 | 같은 파일 610행 `_apply_mine_only` | 2번 범위 |
| 5 | 주문 대시보드 | `foms/services/orders/dashboard_read_model.py:88` | `dashboard_active_filter(60)` + `is_erp_order` (+ 검색어 있으면 고객 연락처 검색 술어) |
| 6 | 생산 대시보드 | `foms/services/production_read_model.py:104` | `active_filter()` + `is_erp_order` + `erp_stage_code IN PRODUCTION_BASE_STAGE_CODES` (+ 단계·검색어) |
| 7 | 시공 대시보드 | `foms/web/construction/dashboard.py:85` | `dashboard_active_filter(60)` + `is_erp_order` |
| 8 | AS 대시보드 | `foms/web/cs/as_dashboard.py:275` | `active_filter()` + `erp_as_scope_condition()` (+ 상태 필터) |

(타워 3곳을 하나로 세어 "7곳". `dashboard_active_filter` 는 활성 + "완료 단계면 단계/구조/생성 시각 중 하나가 60일 안" 조건이다.)

## 3. 비교한 안

- **OR(현재)**: `or_(*conds)`.
- **UNION(되돌린 것)**: `mine_membership_clause(conds)` — 범위 없음.
- **SCOPED**: 바깥 범위 술어(`query.whereclause`)를 별칭으로 옮겨 각 UNION 갈래에도 넣음.
- **HYBRID**: 가벼운 갈래(이름·id 경로 토큰)는 SCOPED UNION, 무거운 갈래(도면 문서 전체 ILIKE `and_(...)`)만 바깥 `OR` 에 그대로 둠 → `Order.id IN (범위 UNION) OR 무거운조건`.
- **CTE**: 범위를 `MATERIALIZED` CTE 로 먼저 만든 뒤 그 안에서 OR 판정.

## 4. 실측표 (스테이징, 사용자 17명: SALES 3·CONSTRUCTION 3·DRAWING 3·ADMIN 3·CS 3·ACCOUNTING 2, 단위 ms)

화면별 전체 중앙값 / 최악 (2회차 원문 기준)

| 화면 | OR 중앙/최악 | UNION 최악 | SCOPED 최악 | **HYBRID 중앙/최악** | CTE 최악 | HYBRID 최대 악화 | 동일 |
|------|-----------|-----------|------------|-----------------|---------|--------------|------|
| CS 완료 큐 | 74.6 / 309.2 | 245.4 | 167.4 | **7.0 / 156.6** | 354.0 | +2.9 (시공) | 17/17 |
| 타워 기본·내작업 | 1.8 / 142.0 | 244.2 | 211.8 | **7.2 / 70.6** | 132.2 | +5.8 (영업 1명) | 17/17 |
| 타워 내 담당 진행중 | 1.8 / 131.5 | 222.5 | 66.3 | **6.8 / 68.1** | 111.7 | +5.6 | 17/17 |
| 주문 대시보드 | 1.6 / 146.9 | 238.8 | 216.4 | **7.2 / 68.2** | 152.8 | +5.9 | 17/17 |
| 생산 대시보드 | 6.5 / 25.4 | 211.6 | 13.3 | **1.1 / 14.2** | 1332.5 | −2.1 (악화 없음) | 17/17 |
| 시공 대시보드 | 2.6 / 139.8 | 231.2 | 209.4 | **7.0 / 76.1** | 132.1 | +5.0 | 17/17 |
| AS 대시보드 | 1.4 / 101.9 | 223.0 | 50.4 | **1.8 / 50.6** | 89.0 | +1.2 | 17/17 |

사용자군별 최악(1회차, 주문 대시보드 예): 관리자 OR 158.2 → HYBRID 68.9, 도면 93.9 → 67.4, 영업 36.6 → 7.5, 시공 1.3 → 3.6, CS·회계 0.3 → 0.5.

판정(규칙: 어떤 군도 +10ms 초과 악화 없음 + 최악 감소)
- UNION: 도면·관리자 +130~+198ms → 탈락.
- SCOPED: 60일 범위 화면(타워·주문·시공)에서 도면 +107~+116ms → 탈락. 무거운 갈래가 범위 안에서도 trgm 비트맵으로 전체를 먼저 훑기 때문.
- CTE: 회계·CS 등 거의 빈 사용자도 범위 물질화 비용(+25~+123ms), 생산에서 관리자 1.3초 → 탈락.
- **HYBRID: 7곳 모두 +10ms 초과 0건, 최악 −44%~−54%(CS 309→157, 대시보드 147→68, AS 102→51, 생산 25→14), 동일성 119/119.**
- 중앙값은 1.6→7.2ms 로 약 +5ms 오른다(대부분 영업·시공 사용자: 가벼운 갈래 UNION 고정비). 규칙 안(+10ms 이하)이지만 위험 항목에 적는다.

## 5. 추천안: HYBRID (범위 넣은 UNION + 무거운 갈래만 OR)

```
Order.id IN (
    SELECT om.id FROM orders AS orders_mine om WHERE <범위(별칭)> AND <가벼운조건1>
    UNION SELECT ... <가벼운조건k>
)
OR <무거운 조건(도면 문서 전체 ILIKE AND 최상위 drawing_assignees 토큰)>
```

바깥 쿼리에 범위가 이미 있으므로 무거운 조건은 범위 안 행에서만 평가된다(현재 OR 과 같은 비용). 가벼운 갈래는 범위 + 경로 trgm 인덱스로 작은 집합에서 시작한다.

## 6. 코드 변경 지점

1. `foms/services/erp_permissions.py` `mine_membership_clause(conds, scope_conds=None)`
   - `scope_conds` 가 None 이면 지금과 같다(배지·검색 등 기존 호출부 무변화).
   - 있으면: `ClauseAdapter(orders_mine)` 로 범위와 가벼운 조건을 각 갈래 `where` 에 함께 넣고, 무거운 조건은 원본 그대로 `or_` 로 붙인다.
   - 무거운 조건 판별: 구조 추측 대신 `build_mine_sql_filter` 가 만들 때 표시한다. 예: 모듈 집합 `_DOC_SCAN_CONDS`(WeakSet) 에 그 `and_(...)` 객체를 등록하거나, 조건 생성 함수 `_drawing_top_level_cond` 반환값을 판별 함수 `is_doc_scan_mine_cond(c)` 로 확인. 실측 스크립트는 "`and_` 복합 = 무거운 갈래" 로 판별했다(현재 목록에서 `and_` 는 그것 하나뿐).
2. 호출부 7곳: `q.filter(or_(*conds))` → `q.filter(mine_membership_clause(conds, scope_conds=[q.whereclause]))`.
   - 범위는 **mine 직전의 `whereclause`** 를 그대로 넘긴다(검색어·단계·상태 필터 포함 → 더 좁아질 뿐 결과 같음).
   - `foms/api/cs/dashboard.py:57`, `dashboard_control_tower.py:191·598·610`, `dashboard_read_model.py:88`, `production_read_model.py:104`, `foms/web/construction/dashboard.py:85`, `foms/web/cs/as_dashboard.py:275`.
   - 빈 조건(`conds == []`) 처리는 각 호출부 현재 분기(`id == -1`, 0 반환, 무필터) 그대로.
3. `_mine_open_count` 는 단계 조건이 mine 뒤에 붙으므로, 단계 조건까지 먼저 붙인 쿼리의 `whereclause` 를 범위로 넘긴다(실측은 이 모양으로 쟀다).

## 7. 동일성

- 집합 논리: 범위 R, 조건 c1..cn 에 대해 `R ∧ (c1 ∨ … ∨ cn)` = `R ∧ (id ∈ ⋃(R ∧ ci_가벼움) ∨ c_무거움)`. 바깥에 R 이 있으므로 갈래 안 R 은 결과를 바꾸지 않고 줄이기만 한다.
- 실측: 7곳 × 17명, 반환 주문 id 정렬 목록(타워 진행중은 개수) 이 OR 과 **119/119 일치**. `dashboard_active_filter` 안의 `_meta_draft_order_ids()` 부속 질의도 별칭 옮김 후 같았다.
- 주의: `datetime.now()` 를 쓰는 60일 기준은 바깥과 갈래가 같은 식 객체를 공유하므로 같은 값으로 묶인다(같은 `whereclause` 를 넘기기 때문).

## 8. 테스트

- 단위(SQLite·PG 레인): `mine_membership_clause(conds, scope_conds=[R])` 결과 집합 = `R ∧ or_(*conds)` — 사용자 이름·username·id 조합, 도면 최상위 배정만 있는 주문, 범위 밖 내 주문(제외되어야 함) 고정 시드.
- 계약: 무거운 조건 판별 함수가 `build_mine_sql_filter(scope="all"/"drawing")` 에서 정확히 이름당 1개를 고른다(위치-고정 계약 테스트, 심볼 이동 방지).
- 7곳 호출부: 컴파일 SQL 에 `orders_mine` 와 바깥 무거운 ILIKE 가 함께 있는지 확인하는 형태 테스트.
- 성능 회귀: 측정 스크립트를 스테이징에서 다시 돌려 "+10ms 초과 0건·동일 119/119" 확인 후 push. 반영 뒤 운영은 RUM/구간 계측으로 대시보드·CS 완료 큐 서버 시간 전후 비교.

## 9. 되돌리기

- 호출부 7곳만 `or_(*conds)` 로 되돌리면 끝(헬퍼 새 인자는 기본값 None 이라 남겨도 무해). 화면 단위로 따로 되돌릴 수 있다. 데이터·스키마 변경 없음.

## 10. 반영 순서

1. 헬퍼 `scope_conds` + 무거운 조건 표시 + 단위·계약 테스트.
2. 효과 큰 순서로 호출부 교체: CS 완료 큐 → 주문·시공 대시보드 → 타워 3곳 → AS → 생산.
3. 스테이징 재측정(위 스크립트) → deploy push → 하루 운영 계측 후 production 승격(사용자 명시 요청 시).

## 11. 위험

- 중앙값 약 +5ms(영업·시공 등 적은 건 사용자): 가벼운 갈래 UNION 고정비. 규칙 한도 안이나 영업 사용자 1명이 +5.9ms 로 가장 큰 악화.
- 스테이징 행 수는 운영보다 적다. 운영 분포에서 관리자·도면 최악이 더 클 수 있어 반영 후 운영 계측 필수.
- 무거운 조건 판별이 구조 추측이면 `build_mine_sql_filter` 수정 때 조용히 깨진다 → 6-1 의 명시 표시 + 계약 테스트로 막는다.
- 검색어(`q`)가 있는 대시보드 경우는 범위가 더 좁아져 유리한 쪽이라 따로 재지 않았다.

## 12. 구현 실측 (2026-10-07, 승인 "추천안으로 스테이징까지")

- 구현: `mine_membership_clause(conds, scope_conds=None)` + 무거운 조건 명시 표시(`_mark_doc_scan_cond` → `_DOC_SCAN_CONDS` WeakSet, 판별 `is_doc_scan_mine_cond`). 구조 추측(`and_` 복합) 판별은 쓰지 않는다. 7곳은 mine 직전 `whereclause` 를 범위로 넘긴다(`_mine_open_count` 는 단계 조건 뒤).
- 측정: `scratchpad/mscope/m2.py`(m1 과 같은 틀, 비교 대상 = **실제 구현 함수가 그린 SQL**: 완료 큐 `_apply_mine_filter`, 타워 `_apply_mine_only`, 생산 `build_production_orders_query(erp_mine_only=True)`, 나머지는 같은 범위 + 헬퍼), 스테이징 읽기 전용, 결과 `scratchpad/mscope/out2.txt`.

| 화면 | OR 중앙/최악 | 구현 중앙/최악 | 최대 악화 | +10ms 초과 | 동일 |
|------|-----------|------------|--------|---------|------|
| CS 완료 큐 | 72.1 / 315.0 | 6.7 / 150.8 | +2.4 (시공) | 0 | 17/17 |
| 타워 기본·내작업 | 2.1 / 145.1 | 7.5 / 68.9 | +5.3 (영업) | 0 | 17/17 |
| 타워 내 담당 진행중 | 2.1 / 118.3 | 6.6 / 59.6 | +4.5 | 0 | 17/17 |
| 주문 대시보드 | 1.7 / 152.4 | 6.7 / 73.7 | +5.0 | 0 | 17/17 |
| 생산 대시보드 | 6.6 / 22.1 | 1.2 / 12.3 | −2.5 | 0 | 17/17 |
| 시공 대시보드 | 2.3 / 147.7 | 7.1 / 74.5 | +5.8 | 0 | 17/17 |
| AS 대시보드 | 1.2 / 106.4 | 1.8 / 50.1 | +1.0 | 0 | 17/17 |

- 설계 수치(§4 HYBRID)와 같은 범위: 최악 −45%~−53%, 중앙 약 +5ms, 동일 119/119.
- 테스트: `tests/domains/test_mine_filter_scoped_screens.py`(표시 계약 + 표시 제거 음성 대조, HYBRID 모양, 7곳 소스 모양, 범위 밖 내 주문·최상위 도면 배정 포함 동일성).
