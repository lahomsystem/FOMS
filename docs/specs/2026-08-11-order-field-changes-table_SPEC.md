# 주문 변경 원장 정규화 테이블 (ORDER-DIFF-01) — 2안 스펙

- 작성: 2026-08-11
- 상태: **승인 대기** (1안 배포 완료 후속)
- 선행: ORDER-DIFF-00 1안 (`docs/specs/2026-08-11-order-change-diff-audit_SPEC.md`, deploy `cbee4639`)
- 결정 전제(사용자, 2026-08-11): PII 원문 기록 / 품목 포함 / production 승격은 보류 중

## 1. 왜 2안이 필요한가

1안으로 **행 단위** 조회는 된다("이 저장에서 무엇이 바뀌었나" = `security_logs.detail.changes`).
안 되는 것이 세 가지다:

1. **필드 기준 질의 불가** — "최근 한 달에 실측일이 바뀐 주문 전부", "출고가를 내린 사람"을
   물으려면 JSONB 배열을 풀어야 한다. 감사 원장의 핵심 질문이 인덱스를 못 탄다.
2. **40건 상한** — 대량 변경 저장은 목록이 잘리고 개수만 남는다(기록 자체가 없다).
3. **주문별 이력 화면 불가** — 주문 하나의 변경 역사를 시간순으로 모으려면 `security_logs`
   전체를 훑어야 한다.

SAP 가 `CDHDR`(헤더) / `CDPOS`(항목)로 나눈 이유와 같다. 1안은 헤더에 항목을 JSON 으로 접어
넣은 상태이고, 2안은 항목을 **질의 가능한 행**으로 편다.

## 2. 목표 / 비목표

**목표**
1. 저장 1회의 필드 변경을 `order_field_changes` 행으로 남긴다(상한 없음).
2. "어떤 필드가 언제 누구에 의해 어떻게 바뀌었나"를 **인덱스로** 조회한다.
3. 감사 화면에 변경 필드 필터를 얹는다.
4. 1안이 이미 쌓은 `detail.changes` 를 같은 테이블로 백필한다.

**비목표 (후속)**
- 품목 안정 UUID(ITEM-ID-00) — 중간 삽입 오탐은 2안에서도 그대로다(§8).
- 주문 상세의 변경이력 탭 / 되돌리기 / 변경 사유 입력
- 보존(retention) 자동 삭제 정책 — 테이블은 삭제가 싸게 되도록만 설계한다.

## 3. 스키마

신규 마이그레이션 `orderdiff_01_order_field_changes` (down_revision = 현재 head `seclog_time_00`).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BigInteger PK | 볼륨 상 32bit 로는 부족할 여지를 두지 않는다 |
| `change_set_id` | String(36) NOT NULL | 저장 1회 = 1 change set(UUID4). 헤더 `security_logs.detail.change_set` 과 같은 값 |
| `order_id` | Integer NOT NULL | **FK 없음** |
| `path` | String(120) NOT NULL | `schedule.measurement.date` · `items.2.price` |
| `path_template` | String(120) NOT NULL | 품목 인덱스를 지운 질의 키(`items.*.price`). 스칼라는 `path` 와 동일 |
| `item_index` | Integer NULL | 품목 경로면 인덱스(문자열 파싱 없이 질의) |
| `item_name` | String(120) NULL | 저장 시점 품목명 |
| `op` | String(8) NOT NULL | `set`·`add`·`clear`·`remove` |
| `before_value` | Text NULL | 1안과 같은 정규화·절단(120자) 값 |
| `after_value` | Text NULL | 〃 |
| `actor_user_id` | Integer NULL | 행위자 |
| `created_at` | DateTime NOT NULL | `now_utc_naive` (naive=UTC 규약) |

인덱스 3종:
- `ix_order_field_changes_template_time` (`path_template`, `created_at`) — "실측일 바뀐 것 전부"
- `ix_order_field_changes_order_time` (`order_id`, `created_at`) — 주문별 이력
- `ix_order_field_changes_change_set` (`change_set_id`) — 헤더↔항목 연결

**FK 를 걸지 않는 이유**: `OrderEvent` 와 같다(AUDIT-LOG T9 / `auditlife_00`). 감사 원장이 감사
대상과 생명주기를 공유하면 주문 hard purge 가 그 주문의 이력까지 지운다. `models.py` 의
`__table_args__` 와 마이그레이션의 인덱스 이름·컬럼 순서는 **완전히 같아야** 한다(create_all
레인과 alembic 레인 정합 — PG 레인 왕복 테스트가 강제). 마이그레이션은 `models` 를 import
하지 않는다(상수 동결 원칙).

## 4. 쓰기 배선

- 1안이 이미 만든 `DiffResult` 를 그대로 쓴다. **differ 는 재사용, 두 번 계산하지 않는다.**
- 저장 트랜잭션과 **같은 세션**에 `bulk_save_objects` 로 삽입한다(부분 성공 없음).
- `change_set_id` 는 저장 경로에서 UUID4 로 만들어 (a) 테이블 행 전부와 (b)
  `security_logs.detail['change_set']` 양쪽에 넣는다 — FK 없이 헤더와 항목이 이어진다.
- **상한 없음**: `detail.changes` 는 화면용이라 40건 캡을 유지하고, 테이블에는 전량 기록한다.
  1안의 `truncated` 표시 문구는 "테이블에 전량 있음"으로 바꾼다.
- 실패 정책: 원 저장을 죽이지 않는다(`log_access` 와 같은 fail-open) — 단 `logger.warning`
  + 스택 필수. 조용한 무시 금지(프로젝트 훅 규약).

## 5. 조회

**감사 화면**(`/security_logs`)에 필터 2개 추가:
- `changed_field` — `path_template` 동등 비교. 후보는 최근 N행에서 뽑아 datalist 로(기존
  `action` 필터와 같은 방식, `SELECT DISTINCT` 풀스캔 금지).
- `changed_value` — `before_value`/`after_value` ILIKE. 값 검색은 보조 수단이며 기본은 필드 필터다.

두 필터가 걸리면 `security_logs` 조회에 `change_set_id IN (…)` 서브쿼리로 좁힌다
(선행 인덱스는 `path_template`).

주문별 이력 API/탭은 이 스펙 범위 밖(테이블이 생기면 조회 1줄로 가능해진다 — 후속).

## 6. 백필

`security_logs.detail->'changes'` 가 있는 행 → 테이블. 규모가 작다(1안 배포 후 며칠분).
- 멱등: 같은 `change_set_id` 가 이미 있으면 건너뛴다. 1안 시기 행에는 `change_set` 이 없으므로
  `"seclog:{id}"` 를 change set id 로 쓴다(결정적 → 재실행 안전).
- `scripts/ops/` 하위 일회성 스크립트 + `--dry-run` 기본.

## 7. 볼륨 근거

운영 `/security_logs` 최근 50행(2026-08-11 13:49~15:36, 1.79시간) 실측:
- `ORDER_STRUCTURED_SAVED` 25건 → **시간당 14건**(주간 피크 구간)
- 1안 실측 평균 변경 7건/저장

피크를 24시간으로 늘려 잡은 상한이 **일 2.3k행 / 연 860k행**. 실제 일평균은 이보다 낮다
(피크 구간 외삽). 인덱스 3개짜리 좁은 행이라 PostgreSQL 에서 문제되는 규모가 아니며,
`created_at` 인덱스로 기간 삭제가 싸다. 보존 정책은 후속에서 숫자를 보고 정한다.

## 8. 유지되는 한계 (숨기지 않는다)

품목 배열에 안정 identity 가 없어(ITEM-ID-00 진행 중) **중간 삽입/순서 변경은 여러 품목이
바뀐 것으로 기록된다.** 2안은 이 값을 테이블로 옮길 뿐 정확도를 올리지 않는다. `item_name` 을
컬럼으로 두는 이유가 이것이다 — 읽는 사람이 인덱스가 아니라 이름으로 판별한다.
근본 해결은 `structured_data['items'][].item_uid` 도입(별도 패킷: 폼·JS·projection allowlist·
백필까지 얽힌다).

## 9. 완료 기준 (구현 반영)

1. `tests/domains/test_order_field_changes_ledger.py` (6건)
   - `path_template` 이 품목 인덱스를 지운다
   - 저장이 원장을 채우고 `change_set` 으로 헤더와 이어진다
   - 40건 초과 저장: `detail.changes` 는 40, **원장은 전량**
   - `changed_field` 필터가 해당 저장만 남긴다 / 조건 불일치는 빈 목록(조용한 무시 금지)
   - 원장 쓰기 실패해도 저장은 200(fail-open), 헤더는 정상
2. `tests/domains/test_order_field_changes_backfill.py` (3건)
   - dry-run 은 아무 것도 쓰지 않는다 / `--apply` 는 원 감사 시각으로 옮긴다 / 재실행 멱등
3. `tests/postgres/test_order_field_changes_pg.py` (3건)
   - alembic upgrade→downgrade→upgrade 왕복
   - `create_all` 스키마와 alembic 스키마의 컬럼·인덱스 이름·컬럼 순서 일치
   - `path_template` 동등 비교가 **Seq Scan 이 아님**(EXPLAIN)
4. `tests/domains/test_alembic_single_head.py` green (head 단일 유지)
5. `import app` APP_OK + `scripts/ops/pre_push_smoke.ps1` exit 0 + 인벤토리 3종 재생성
6. PG 레인 전체(`tests/postgres`) green — 새 모델이 create_all 부트스트랩을 깨지 않는지

## 10. 리스크

| 리스크 | 완화 |
|---|---|
| create_all↔alembic 스키마 불일치 | 인덱스 이름·순서 고정 + PG 레인 왕복 테스트(완료 기준 3) |
| 저장 지연 증가 | 삽입 1회 bulk, differ 재사용(추가 계산 0). 저장 경로 latency 로그로 전후 비교 |
| 테이블 급증 | 좁은 행 + `created_at` 인덱스로 기간 삭제 대비, 실측 연 860k 상한 |
| 백필 중복 | 결정적 change set id(`seclog:{id}`) + 존재 검사 |
| 감사 쓰기 실패가 저장을 죽임 | fail-open + 경고 로그(조용한 무시 금지) |
