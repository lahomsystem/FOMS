# Spec — 시공일 지난 적체 주문 일괄 완료 처리 (2026-09-22)

> 상태: **운영 적용 완료(2026-09-22, 사용자 승인)** — plan 413 = main 299 + as_stage_only 114(제외 draft 1 · stage_not_main 63), applied 413 · stale 0. 실측 858→478 · 도면 101→69 · 완료 1451→1864. AS 지문 `ec71af89e29f8010` 적용 전후 동일, AS 탭 659/46 불변. 행위자 id57(claude_master). 옛 시공일 표식 5건(#4662·#4664·#5299·#5349·#5352) 포함 적용. 스냅샷·plan 사본 `C:/tmp/foms-backlog-complete-20260922/` + 세션 스크래치패드.
> 도구 `tools/ops/bulk_complete_past_construction.py`(CLI) + `_core.py`(판정·행 단위 쓰기, 500줄 래칫 분리) · 테스트 `tests/domains/test_bulk_complete_past_construction_plan.py`(순수 8) + `tests/postgres/test_bulk_complete_past_construction_pg.py`(PG 레인 2).
> 배경: 도면 단계까지 도면팀·영업팀이 실사용을 시작한다. 실측 853·도면 100 타일에
> 이미 끝난 주문이 섞여 있어 "진짜 도면을 만들어야 하는 건"이 안 보인다.

## 0. 확정된 사용자 결정 (2026-09-21~22)

| 항목 | 결정 |
|---|---|
| 판정 기준 | `erp_construction_date` 가 오늘(KST) 기준 **7일 이상 지난** 건 |
| 일반 건 | 본공정 `COMPLETED` + `status = COMPLETED` |
| AS 탭 건(미완료·완료 탭 모두) | **status·as_lifecycle·as_axis_status 불변**. `workflow.stage` 만 `COMPLETED` (선택지 B) |
| 열린 quest | 그대로 둔다(기존 강제 변경 규율과 동일) |
| 시공일 없는 건 | 자동 처리 금지. 검토 목록만 산출 |
| 실행 대상 | 운영(production). 스테이징 리허설 선행 |

## 1. 운영 실측 (2026-09-22, 읽기 전용 1회)

| 단계 타일 | 총 | 시공일 없음 | 시공일 +7일 경과 | 시공일 미래 |
|---|---|---|---|---|
| 실측 | 853 | 306 | 368 | 103 |
| 도면 | 100 | 15 | 32 | 45 |
| 시공 | 2 | 1 | 1 | 0 |
| AS처리(stage=AS_RECEIVED) | 80 | 17 | 63 | 0 |

시공일 +7일 경과 후보 분류:

| 분류 | 실측 | 도면 | 시공 | 처리 |
|---|---|---|---|---|
| 일반(AS 축 없음) | 269 | 19 | 1 | stage+status → COMPLETED |
| AS 완료 탭 건(`as_axis_status=COMPLETED`) | 81 | 13 | – | stage 만 COMPLETED |
| AS 미완료 탭 건(`as_axis_status=RECEIVED`) | 18 | – | – | stage 만 COMPLETED |

- 후보 시공월: 2026-08 232 · 2026-09 154 · 2026-07 9 · 그 이전 5(2022-01, 2025-07/10/11, 2026-04 각 1). 옛 5건은 plan 에 `flag=old_construction_date` 로 표시해 사람 확인.
- 열린 quest 가 남은 후보: 105건(결정: 그대로 둔다).
- `erp_stage_code = AS_RECEIVED` 80건은 이미 AS처리 타일이므로 **대상 밖**.
- 비ERP 옛 주문(`is_erp_order=false`, stage NULL) 1,172건은 파이프라인 타일에 안 잡히므로 대상 밖.

## 2. 왜 기존 「단계 강제 변경」 일괄 API 를 못 쓰나

`foms/services/orders/stage_override.py` 의 `apply_stage_override()` 가 `order.status = to_code` 로 status 를 통째 덮는다.
AS 건에 `include_as=True` 로 태우면 2026-08-14 사고(AS 55건 대시보드 증발)를 재현한다.
그래서 **전용 ops 스크립트** 로 간다. 단계 이력 기록 형식(`OrderEvent STAGE_OVERRIDE`)은 재사용해
`tools/ops/data_doctor.py` 가 그대로 복구 근거로 읽을 수 있게 한다.

## 3. 대상 선별 술어 (plan 단계, SQL)

```sql
SELECT o.id FROM orders o
WHERE o.deleted_at IS NULL AND o.status <> 'DELETED'
  AND o.is_erp_order = true
  AND NOT (o.status = 'DRAFT' OR coalesce(o.structured_data->'meta'->>'draft','') = 'true')
  AND o.erp_stage_code IN ('RECEIVED','MEASURE','DRAWING','CONFIRM','PRODUCTION','CONSTRUCTION','CS',
                            '주문접수','실측','도면','고객컨펌','생산','시공')
  AND o.erp_construction_date ~ '^\d{4}-\d{2}-\d{2}$'
  AND o.erp_construction_date < to_char((now() AT TIME ZONE 'Asia/Seoul') - interval '7 day','YYYY-MM-DD')
  AND o.status NOT IN ('ON_HOLD','SCHEDULED','SHIPPED_PENDING')   -- 보류·물류 진행 중 제외
```

제외 규칙(plan 에 `skipped[reason]` 로 전부 남긴다):

| reason | 조건 |
|---|---|
| `on_hold` | `status = ON_HOLD` |
| `logistics_in_flight` | `status IN (SCHEDULED, SHIPPED_PENDING)` (도면 단계 5건 실측됨) |
| `naver_claim_open` | 네이버 링크 있고 취소·반품 클레임 진행 중(`fulfillment` 술어 재사용) |
| `stage_already_terminal` | stage 가 COMPLETED/AS_COMPLETED/AS_RECEIVED/AS |
| `non_erp` | `is_erp_order = false` |

분류(plan 의 `mode`):

- `main`: `as_axis_status IS NULL` 이고 `status NOT IN (AS, AS_RECEIVED, AS_COMPLETED)`
- `as_stage_only`: 그 외(AS 탭 건). **status 는 읽기만 하고 절대 쓰지 않는다.**

## 4. 쓰기 규칙 (apply 단계)

한 트랜잭션에 최대 500건(청크), 각 행:

1. `sd = copy.deepcopy(order.structured_data)`
2. `sd['workflow']['stage'] = 'COMPLETED'`, `stage_updated_at = now_utc_naive().isoformat()`,
   `stage_override = {at, stage:'COMPLETED', measurement_date, batch:'2026-09-22-backlog'}`
   (자동 전진 되돌림 방지 표식 — 기존 `apply_stage_override` 와 동일)
3. `order.structured_data = sd; flag_modified(order,'structured_data')`
4. `sync_erp_flat_columns(order, sd)` — `erp_stage_code`·`erp_stage_updated_at` 갱신.
   (`as_axis_status` 는 "값 없으면 안 지움" 규약이라 보존됨 — 계약 테스트로 잠금)
5. `mode == 'main'` 일 때만 `order.status = 'COMPLETED'`. `as_stage_only` 는 status 손대지 않음.
6. `OrderEvent(event_type='STAGE_OVERRIDE', payload={from, to:'COMPLETED', mode:'skip', reason, manual:False,
   batch:'2026-09-22-backlog', from_status:<이전 status>, as_axis_status:<이전 값>})`
7. `security_logs` 에 `ORDER_STATUS_CHANGED` 감사행(`detail.before` 포함) — data_doctor 의 `logged` 근거.

부르지 않는 것(의도): `_handle_stage_transition`(퀘스트·알림 부수효과), 알림톡·웹푸시·채널톡 발송,
도면 이관 이력·`drawing_*` 필드, `as_lifecycle`, `mutation_version` 외 다른 스칼라.

행위자: 운영 ADMIN 계정 id(사용자 지정). 사유 문자열 고정 `"2026-09 실측·도면 적체 정리(시공일 경과)"`.

## 5. 도구 인터페이스

`tools/ops/bulk_complete_past_construction.py`

```
plan  --dsn "$DSN" --cutoff-days 7 --out plan.json          # 읽기 전용, 대상·제외·분류 전량 JSON
apply --dsn "$DSN" --plan plan.json --actor <user_id> --yes --snapshot-out snapshot.json
rollback --dsn "$DSN" --snapshot snapshot.json --yes
```

- `apply` 는 각 행의 현재 `erp_stage_code`·`status`·`as_axis_status` 가 plan 시점과 다르면 **건너뛴다**
  (plan 이후 사람이 만진 행 보호 — data_doctor 규율).
- `snapshot.json` 은 행별 `{id, status, erp_stage_code, erp_stage_updated_at, workflow(원본 dict)}`.
- `rollback` 은 workflow dict 통째 복원 + status 복원 + `STAGE_OVERRIDE` 역방향 이벤트.
- DSN 가드: 실행 전 `SELECT count(*) FROM orders WHERE customer_name LIKE 'TESTCLR%'` — 운영이면 0.
  `--expect-env production|staging` 으로 지문 불일치 시 중단.

## 6. 계약 테스트 (`tests/domains/test_bulk_complete_past_construction.py`)

1. `main` 건: stage/status/erp_stage_code 모두 COMPLETED, `erp_stage_updated_at` 갱신, 이벤트 1건.
2. `as_stage_only` 건(RECEIVED·COMPLETED 각 1): stage 만 COMPLETED, **status·as_axis_status·as_lifecycle 바이트 동일**.
3. 제외 5종 각 1건이 plan 의 `skipped` 에 reason 과 함께 있고 apply 가 건드리지 않는다(음성 대조군).
4. 시공일 미래·시공일 없음·시공일 6일 전은 대상 아님(경계값).
5. plan 이후 status 가 바뀐 행은 apply 가 건너뛰고 `skipped[stale]` 로 보고.
6. rollback 후 3열 + workflow dict 가 snapshot 과 동일.
7. AS 대시보드 미완료·완료 탭 술어(`as_dashboard_helpers`)로 적용 전후 모집단 집합이 같다.

## 7. 실행 순서

1. 스크립트+테스트 구현 → `tests/domains` 통과 → deploy 푸시(pre_push_smoke exit 0, CI green).
2. 스테이징 DB 에서 `plan` → `apply` → 대시보드·AS 탭·정산 탭 실화면 확인(gstack browse).
3. 운영: PITR 창 확인(`railway_pitr.py list`) → `plan` JSON 사용자 검토(옛 시공일 5건 포함) → `apply` →
   파이프라인 타일 재측정(기대: 실측 853→약 485, 도면 100→약 68, 완료 381→약 780) → AS 탭 50/655 불변 확인.
4. 시공일 없는 실측 306·도면 15 건은 `plan --list-no-construction` 으로 CSV 산출 → 영업팀 검토(별건).

## 7-1. 스테이징 리허설 결과 (2026-09-22, FOMS-DEV `maglev`)

| 단계 | 결과 |
|---|---|
| plan | 대상 217(main 214 · as_stage_only 3) · 제외 draft 1 · logistics_in_flight 3 · stage_not_main 45 · 표식 옛 시공일 36 · 열린 quest 171 |
| apply | applied=217 · stale 0 · 실측 305→184 · 도면 43→15 · 완료 1163→1380 |
| AS 탭 불변 | `as_axis_status` 분포 RECEIVED 58 · COMPLETED 426 동일 · AS 주문 전량 `status/as_axis_status/as_completed_date` 지문 `a371e973212989c0` 적용 전후 동일 |
| 화면 | `/erp/dashboard` 200(실측 181 · 도면 15 · 완료 269 · AS처리 53) · `/erp/as` 200 |
| rollback | applied=217 · 단계 분포·AS 지문이 적용 전 측정과 **완전 일치**(`BEFORE==ROLLBACK: True`) |

스테이징 모집단은 운영과 다르다(운영 후보 401 = main 289 + as_stage_only 112, §1). 절차 검증이 목적.

## 8. 부수 효과 (미리 알 것)

- 완료 타일이 60일간 커진다(`dashboard_active_filter(days=60)`). 이후 자동으로 빠진다.
- 정산 탭 "단계별 물린 금액"이 완료 계열을 빼므로 줄어든다(`settlement_aggregation.py:939`).
- 개인 보드에 열린 quest 잔재가 남을 수 있다(결정: 그대로).
- 저장소 디렉토리가 Railway FOMS-PRODUCTION 에 링크돼 있다(2026-09-22 확인). 스크립트는 CLI 링크와 무관하게 `--dsn` 만 쓴다.

## 9. 범위 밖

비ERP 옛 주문 1,172건 정리, 시공일 없는 건 자동 판정, AS 탭 건의 status 변경, quest 정리, 고객 알림.
