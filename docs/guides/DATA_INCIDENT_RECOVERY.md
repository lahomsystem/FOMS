# 데이터 사고 복구 절차 (DATA-DOCTOR-01)

작성 계기: 2026-08-14 일괄 완료처리 사고 — AS 접수/완료 주문 55건의 `status` 가 `COMPLETED` 로
덮여 AS 대시보드에서 사라졌다(기록은 살아 있었고 목록 술어가 status 단독이라 생긴 증발).
손으로 복구한 절차를 도구·문서로 굳힌 것이 이 문서다.

## 0. 전제 — 무엇이 100%를 만드는가

로그만으로는 100% 복구가 안 된다. 실제로 그 사고에서 55건 중 35건만 감사행에 이전값이 있었고,
20건은 AS 이벤트 이력으로 **추론**해서 맞췄다. 세 층이 다 있어야 한다.

| 층 | 수단 | 한계 |
|---|---|---|
| 1. 시점 복구 | Railway 볼륨 백업 + PITR fork | **보존 6일**(Daily 스케줄 `retentionSeconds=518400`), 통짜 복원은 사고 후 정상 업무를 지운다 |
| 2. 쓰기 감사 | `security_logs.detail.before` · `order_events.payload.from_status` | 감사 없는 쓰기 경로가 있으면 그만큼 구멍 |
| 3. 복구 도구 | `tools/ops/data_doctor.py` | 대상 선별·dry-run·트랜잭션 적용·롤백 |

**핵심: 통짜 시점 복원은 쓰면 안 된다.** 사고 시점으로 DB를 통째 되돌리면 그 뒤의 정상 업무가
전부 사라진다(2026-08-14 사고는 직전 스냅샷이 17시간 전이었다). 항상 *별도 서비스로 fork →
그 사본에서 해당 행만 읽어 운영에 선별 반영* 이다.

## 1. 사고 감지 직후 (가장 먼저)

보존창이 6일이므로 **발견 즉시 그 시점 사본을 확보**한다. 조사·복구는 그다음이다.

```bash
# 복구 가능 창 확인 (읽기 전용)
python tools/ops/railway_pitr.py list --project FOMS-PRODUCTION

# 사고 직전 시각으로 새 서비스에 복원 (운영 볼륨은 건드리지 않는다)
python tools/ops/railway_pitr.py fork --project FOMS-PRODUCTION \
  --at 2026-08-14T06:25:00Z --name foms-pitr-0814

# 새 서비스가 뜨면 DSN 확보
railway variables --service foms-pitr-0814 --json
```

`volumeInstanceBackupRestore`(운영 볼륨 덮어쓰기)는 도구에 **구현하지 않았다** — 오조작 한 번이
운영 DB 통째 롤백이 되기 때문이다. 필요하면 사람이 대시보드에서 의식적으로 하라.

## 2. 조사

```bash
DSN=$(railway variables --service Postgres --json | jq -r .DATABASE_PUBLIC_URL)

python tools/ops/data_doctor.py inspect --dsn "$DSN" \
  --since 2026-08-14T06:25:00 --until 2026-08-14T07:00:00
```

시각은 DB 저장 규약과 같은 **naive UTC**(KST 아님). 출력은 창 안의 감사행 액션별 건수,
이벤트 종류별 건수, 상태가 건드려진 주문 수다. 행위자를 알면 `--actor <user_id>` 로 좁힌다.

## 3. 복구안 만들기 (쓰기 없음)

```bash
python tools/ops/data_doctor.py plan --dsn "$DSN" \
  --since 2026-08-14T06:25:00 --until 2026-08-14T07:00:00 \
  --actor 38 --only-as \
  --snapshot-dsn "$PITR_DSN" \
  --out plan.json
```

근거 우선순위와 표시되는 `confidence`:

| confidence | 근거 | 신뢰 |
|---|---|---|
| `exact` | PITR fork DB 의 실제 행 | 원본 그대로 |
| `logged` | `security_logs.detail.before` | 높음 |
| `event` | `order_events` `from_status`/`from` | 중간 |
| `inferred` | 직전 AS 이벤트로 유도 | **사람 확인 필요** |

`--only-as` 는 AS overlay 복구만 남긴다. 상한은 기본 500건(`--max-targets`).

## 4. 적용

```bash
python tools/ops/data_doctor.py apply --dsn "$DSN" --plan plan.json \
  --yes --reason "2026-08-14 일괄 완료처리 사고 복구" \
  --snapshot-out snapshot.json
```

- `--yes` 없으면 아무것도 바꾸지 않는다(기본이 안전).
- 적용 직전 현재값이 계획의 `observed_status` 와 다르면 그 행은 **건너뛴다** — 사고 후 사람이
  이미 고친 행을 덮지 않기 위해서다.
- 단일 트랜잭션. 되돌리기용 스냅샷 JSON 을 먼저 남긴다.
- 복구 자체도 `order_events`(STAGE_OVERRIDE mode=restore) + `security_logs`(restore=true)에 남는다.

되돌리려면:

```bash
python tools/ops/data_doctor.py rollback --dsn "$DSN" --snapshot snapshot.json --yes
```

## 5. 조사 끝나면 fork 정리

```bash
python tools/ops/railway_pitr.py drop --project FOMS-PRODUCTION --name foms-pitr-0814 --yes
```

사본을 오래 두면 비용도 비용이고 실데이터 사본이 하나 더 떠 있는 셈이다.

## 6. v1 범위와 한계

- 복구 축은 **주문 상태**(`status` + `erp_stage_code` + `structured_data.workflow.stage`)뿐이다.
- JSONB 본문(품목·비고 등) 되돌리기는 미지원 — 그건 `order_field_changes` 확장 소관.
- 삭제(soft delete) 복구는 휴지통 경로가 따로 있으므로 여기서 다루지 않는다.
- `inferred` 근거는 자동 적용 대상이지만, 표에서 눈으로 확인하고 필요하면 plan.json 을 편집해
  해당 항목을 빼라(파일이 곧 승인 단위다).

## 관련

- 재발 방지 가드: `tests/domains/test_as_bulk_status_guard.py`(AS 주문 일괄 변경 제외 + 이전값 감사)
- 계정·권한: `docs/guides/REAL_SERVER_TEST_ACCOUNT.md`
