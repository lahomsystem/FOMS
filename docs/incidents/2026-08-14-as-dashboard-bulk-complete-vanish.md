# 2026-08-14 일괄 완료처리로 AS 대시보드에서 55건 증발

> 유형: 데이터 사고  ·  상태: 종결
> 작성 2026-09-07. 사후 등재 문서 — 사고 당시 기록이 아니라 저장소 근거로 재구성했다.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 데이터 사고 — 파생 사본(`orders.status`) 덮어쓰기로 목록 증발 |
| 원인 축 | AS 정본은 `as_lifecycle` 인데 **목록 술어가 파생값 `orders.status` 단독**이라, AS 와 무관한 일괄 write 가 그 컬럼을 덮자 목록이 통째로 사라졌다(`docs/AI_CHANGELOG.md:50`, `docs/guides/DATA_INCIDENT_RECOVERY.md:3-5`) |
| 복구 | 운영 DB 직접 복구 **55/55**. 근거는 감사행 `before` 35건 + AS 이벤트 유도 20건(`docs/AI_CHANGELOG.md:50`, `docs/guides/DATA_INCIDENT_RECOVERY.md:9-10`) |
| 구조 변경 여부 | 있음(2층). 즉시 = `as_overlay_status()` SSOT + 일괄 경로 2종 AS 기본 제외 + 감사행 신설(2026-08-15). 구조적 원인 제거 = AS-AXIS-01 축 투영 도입(2026-08-18, `docs/AI_CHANGELOG.md:49`) |
| 재발 여부 | **재발했다.** 같은 축이 2026-09-03 에 ERP 게이트 이탈로 다시 증발(운영 3건) — `docs/incidents/2026-09-03-as-axis-projection-escape.md` |

## 2. 증상

AS 접수/완료 주문 **55건**의 `status` 가 `COMPLETED` 로 덮이면서 **AS 대시보드에서 사라졌다**
(`docs/guides/DATA_INCIDENT_RECOVERY.md:3-4`).

- **기록은 무손상이었다.** 사라진 것은 목록에 뜨는 조건뿐이다
  (`docs/AI_CHANGELOG.md:50` "기록은 무손상, 목록 술어가 `Order.status` 단독",
  `docs/guides/DATA_INCIDENT_RECOVERY.md:4` "기록은 살아 있었고 … 생긴 증발").
- 이 사고를 `stage` 로는 잡을 수 없다 — **AS 주문의 `workflow.stage` 는 `MEASURE` 로 남는다**
  (`docs/AI_CHANGELOG.md:50`).
- 누가 언제 증발을 발견했는지(발견 시각·발견 경로) — `미상(근거 없음)`.

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| 2026-08-14 06:29~06:34 UTC | 운영 일괄 완료처리 — 주문 일괄 상태변경 **239건** + 단계 강제 변경 **314건** | `docs/AI_CHANGELOG.md:50` |
| 같은 창 | 그중 AS 접수/완료 주문 **55건**의 `status` 가 `COMPLETED` 로 덮여 AS 대시보드에서 증발 | `docs/AI_CHANGELOG.md:50`, `docs/guides/DATA_INCIDENT_RECOVERY.md:3-4` |
| `미상(근거 없음)` | 증발 발견 | — |
| 2026-08-15 | 운영 DB 직접 복구 55/55 + 재발 방지 + 복구 도구화. 스테이징 실브라우저 실측 후 운영 승격 PR #112(`63737e91` 배포 SUCCESS) | `docs/AI_CHANGELOG.md:50` |
| 2026-08-18 | 구조적 원인 제거 — AS-AXIS-01(축 투영 `as_axis_status` 도입, 술어 교체 4곳) | `docs/AI_CHANGELOG.md:49` |

사고 창(06:29~06:34 UTC)은 `docs/AI_CHANGELOG.md:50` 이 단정한 값이다. 그 밖의 시각은 없다.

## 4. 근본 원인

**정본과 목록 술어가 갈라져 있었다.**

- AS 상태의 정본은 `as_lifecycle` 인데, AS 목록이 실제로 조회하는 것은 파생 사본
  `orders.status` **단독**이었다(`docs/AI_CHANGELOG.md:49-50`).
- `orders.status` 는 여러 축을 겹쳐 놓은 **overlay projection** 이라, AS 와 아무 상관 없는
  쓰기 경로(여기서는 일괄 완료처리)도 그 값을 덮을 수 있었다
  (`models.py:109-111` — "status 컬럼은 overlay projection 이라 외부 write 로 덮이면 AS 목록이
  증발했다(2026-08-14 사고)").
- 그래서 데이터는 하나도 잃지 않았는데 **화면에서만 55건이 사라지는** 모양이 됐다.

부차 원인 하나가 복구를 어렵게 만들었다: **덮어쓰기 이전 값을 남기는 감사 경로가 부족했다.**
55건 중 감사행에 이전값이 있던 것은 35건뿐이고, 나머지 20건은 AS 이벤트 이력으로 **추론**해
맞췄다(`docs/guides/DATA_INCIDENT_RECOVERY.md:9-10`).

## 5. 복구

- **운영 DB 직접 복구 55/55**(`docs/AI_CHANGELOG.md:50`).
- 근거 3층(`docs/guides/DATA_INCIDENT_RECOVERY.md:9-16`):
  - 감사행 `before` — `security_logs.detail.before` · `order_events.payload.from_status` 로 **35건**
  - AS 이벤트 이력 유도 — **20건**
  - 시점 복구(Railway 볼륨 백업 + PITR fork)는 **보존 6일**
- **통짜 시점 복원은 쓰지 않았다.** 사고 시점으로 DB를 통째 되돌리면 그 뒤 정상 업무가 전부
  사라지고, 이 사고는 **직전 스냅샷이 17시간 전**이었다
  (`docs/guides/DATA_INCIDENT_RECOVERY.md:18-20`). 정본 절차는 *별도 서비스로 fork → 그 사본에서
  해당 행만 읽어 운영에 선별 반영* 이다.
- 스냅샷·감사행·롤백 스크립트를 보존했다(`docs/AI_CHANGELOG.md:50`).

## 6. 구조 변경

**즉시(2026-08-15, 커밋 `b7c85bb8`·`fbeb07b8`, 운영 승격 PR #112 `63737e91`)**
— `docs/AI_CHANGELOG.md:50`

- `as_overlay_status()` **SSOT** 신설. 판정 축은 **status 기준** — AS 주문의 `workflow.stage` 는
  `MEASURE` 로 남아 stage 로는 못 잡기 때문이다.
- 일괄 경로 **2종에서 AS 기본 제외** + 제외 목록·경고 반환. `include_as: true` opt-in 만 포함하고,
  단건 조작은 종전대로.
- `STAGE_OVERRIDE` payload 에 `from_status`·`as_overlay_cleared` 추가, `ORDER_STATUS_CHANGED`
  감사행 신설 — **복구 근거 공백을 메우는 변경**이다(이번 복구에서 20건을 추론으로 맞춰야 했던 자리).
- 프런트 제외 고지 alert, 자산 핀 `?v 20260814d`.
- 복구 절차 도구화: `tools/ops/data_doctor.py`(inspect→plan→apply→rollback, confidence 4층
  exact>logged>event>inferred, 기본 dry-run·현재값 불일치 행 skip·상한 500),
  `tools/ops/railway_pitr.py`(백업 조회·시점 fork·drop, 운영 볼륨 덮어쓰기 미구현),
  `docs/guides/DATA_INCIDENT_RECOVERY.md` 신설.
- 검증: 스테이징 실브라우저 실측(API 2종 차단 + UI 실조작 시 AS완료 유지).

**구조적 원인 제거(2026-08-18, AS-AXIS-01)** — `docs/AI_CHANGELOG.md:49`

목록 술어를 파생값 `orders.status` 에서 **AS 축 투영 `as_axis_status`** 로 옮겼다(플랫 투영 +
부분 인덱스, 마이그레이션 `asaxis_00`, 유도 SSOT `derive_as_axis_status`, 술어 교체 4곳).
이 결정은 본 문서와 함께 `docs/harness/policy/DECISIONS.md` 의 `[2026-08-18] AS-AXIS-01` 항목에 등재했다.

## 7. 재발 여부·남은 것

- **재발했다.** AS-AXIS-01 이 만든 그 사본이 2026-09-03 에 `is_erp_order` 게이트 안에만 들어가
  비ERP AS 주문의 축이 옛 값으로 동결됐고, 같은 "AS가 화면에서 사라진다" 증상이 운영 3건에 다시 났다
  (`docs/AI_STATUS.md:18`, `docs/AI_CHANGELOG.md:10`,
  `docs/incidents/2026-09-03-as-axis-projection-escape.md`).
- 검토 보고서의 판정: 08-14 → 사본 하나 더 → 09-03 그 사본 이탈 → 봉인 가드. **매 수정이
  '가드 하나 더' 였고 사본 구조는 그대로다**(`docs/plans/2026-09-06-foms-system-review-report.md:107`,
  `:37` R1).
- 남은 것 ①: 사본을 맞추는 주체가 생성 컬럼·트리거가 아니라 `sync_erp_flat_columns` **호출 규약**
  (27곳/19파일)이다 — 쓰기 경로가 늘 때마다 '부른 경로' 와 '안 부른 경로' 가 갈린다
  (`docs/plans/2026-09-06-foms-system-review-report.md:37`).
- 남은 것 ②: 드리프트 감사 도구(`tools/ops/audit_as_axis_drift.py`·`audit_erp_flat_columns.py`)는
  있으나 **자동 실행 배선이 0**이었다(`docs/plans/2026-09-06-foms-system-review-report.md:37` —
  워크플로·`start.sh`·`predeploy.sh` grep 0건). 그 배선은 별 task 로 진행 중이다.

## 8. 근거 앵커

- `docs/guides/DATA_INCIDENT_RECOVERY.md:3-5` — 작성 계기(55건 `status` 덮임·목록 술어 status 단독)
- `docs/guides/DATA_INCIDENT_RECOVERY.md:9-10` — 55건 중 감사행 35건 · AS 이벤트 유도 20건
- `docs/guides/DATA_INCIDENT_RECOVERY.md:12-16` — 복구 3층 표(백업 보존 6일 · 감사 · data_doctor)
- `docs/guides/DATA_INCIDENT_RECOVERY.md:18-20` — 통짜 시점 복원 금지 · 직전 스냅샷 17시간 전
- `docs/AI_CHANGELOG.md:50` — 사고 창 06:29~06:34 UTC · 239건/314건 · 55건 증발 · 복구 55/55 · 가드 전량 · PR #112 `63737e91` · 커밋 `b7c85bb8`·`fbeb07b8`
- `docs/AI_CHANGELOG.md:49` — AS-AXIS-01(구조적 원인 제거, 2026-08-18)
- `models.py:109-112` — `as_axis_status` 컬럼 주석이 이 사고를 직접 기록
- `docs/AI_STATUS.md:18` · `docs/AI_CHANGELOG.md:10` — 2026-09-03 재발
- `docs/plans/2026-09-06-foms-system-review-report.md:37` · `:107` — R1·R8, 사본 구조 잔존과 반복 판정
