# mine 필터 최상위 drawing_assignees 칸 색인 — SPEC (2026-10-22)

## 목적
사용자 신고(2026-10-22): "운영자 계정으로 mine 필터 켰을 때 느려". 운영 실측(claude_master, PC·모바일):
mine 켬 0.65~0.70초 vs 끔 0.20초, 매 요청. 같은 날 1단계(`57e3fe843`)로 ADMIN mine 조건의 최상위
`drawing_assignees` 갈래에서 문서 전체 ILIKE 선필터를 걷어냈다(운영 62조합 결과 차이 0). 운영 DB 서버 시간은
목록 개수 241→74ms·목록 216→87ms·요약 244→145ms 로 줄었지만, 남은 70~80ms 는 그 갈래가 **색인 없이**
범위 안 행마다 JSONB 를 풀기 때문이다(다른 mine 갈래만 쓰면 5ms). 그 칸 전용 trigram 색인을 더한다.

## 지금 구조
- `foms/services/erp_permissions.py` `build_mine_sql_filter` 의 이름 갈래 중 최상위 배정:
  `CAST(structured_data -> 'drawing_assignees' AS VARCHAR) ILIKE '%"이름"%'` (`_json_string_token_condition`).
- 다른 갈래는 `migrations/versions/phase_e_trgm_perm_indexes.py` 가 같은 모양의 표현식 trigram GIN 색인을 갖고 있다
  (`ix_orders_sd_drawing_assignees_trgm` = `assignments.drawing_assignees`). 최상위 칸만 색인이 없다.
- 운영: orders 4,817행 중 최상위 `drawing_assignees` 가 비어 있지 않은 행 348개(옛 데이터).

## 변경
1. 새 마이그레이션 `mine_toplevel_drawing_idx_00`(down_revision = 현재 head `session_rev_00`):
   `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_sd_toplevel_drawing_assignees_trgm ON orders USING gin
   ((CAST(structured_data -> 'drawing_assignees' AS VARCHAR)) gin_trgm_ops)` — `phase_e` 와 같은
   `autocommit_block` 패턴, downgrade 는 `DROP INDEX CONCURRENTLY IF EXISTS`. 표현식은 SQLAlchemy 생성 SQL 과 바이트 일치시킨다.
2. 코드 변경 없음(조건 모양은 1단계 그대로). 색인을 타는지는 EXPLAIN 으로 확인한다.

## 위험·운영
- CONCURRENTLY 라 쓰기 잠금 없음. 다중 replica 는 `migrations/env.py` 세션 advisory lock 이 직렬화(기존 계약).
- 크기: 348행만 값이 있어 작다. 빌드 시간 수 초 예상(운영 4,817행).
- 되돌리기: downgrade 또는 색인 DROP — 조건은 색인 없이도 같은 결과를 낸다(느릴 뿐).

## 판정
- 운영 DB(읽기 전용) EXPLAIN: ADMIN(upperkill) mine 목록 개수·목록 질의가 새 색인을 타고 서버 시간이 mine 끔 수준
  (한 자릿수 ms)인지. 스테이징에서 먼저 같은 확인.
- 운영 HTTP 재측정(사용자 요청 시): mine 켬 대시보드가 끔과 같은지.

## 테스트
- 마이그레이션 체인 테스트(기존 하네스: head 하나, downgrade 존재) 통과.
- PG 레인: 마이그레이션 적용 후 `pg_indexes` 에 색인 존재 + 같은 표현식으로 만든 질의 EXPLAIN 에 색인 이름이 나오는 테스트.
