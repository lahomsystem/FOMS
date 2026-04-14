# Wave 6 Batch W6-B6 — Lane status register

> **batch ID:** W6-B6  
> **risk axis:** docs / truth  
> **실행일:** 2026-04-13 (executor session)  
> **Attempt:** 1 — **completed**  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.7  
> **진입 경로:** **Branch A** — `W6-B5` 완료 후 (계획서 §4.1, §5.7)

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record, `foms/services/README.md` status 요약 | runtime 코드, 신규 pilot |

## 2. Inputs consumed

- `W6-B0` … `W6-B5` run records (completed chain)
- `foms/services/README.md` (current)
- 본 계획서 §2.3 queue, §1.2 explicit-exception 규칙

## 3. Status register (authoritative)

| Row id | Lane / surface | row type | execution state | root shim status (해당 시) | future canonical target | retirement wave / removal condition (요약) | Wave 7 / Wave 8 owner |
|--------|----------------|----------|-------------------|----------------------------|-------------------------|---------------------------------------------|------------------------|
| SR-N1 | `notifications` / `foms.services.notifications.realtime_notifications` | pilot lane | **completed** | flat + root = **shim-only** | `foms/services/notifications/realtime_notifications.py` (달성) | flat/root compat → Wave 8 bridge retirement | W8 |
| SR-F1 | `files` helper / `foms.services.files.file_utils` | pilot lane | **completed** | flat + root = **shim-only** | `foms/services/files/file_utils.py` (달성) | 동일 | W8 |
| SR-J1 | `foms/services/jobs/*` + `services/jobs/*` | already packaged precedent | **completed** | shim-only | `foms/services/jobs/*` | N/A (선례) | — |
| SR-E1 | `foms/services/erp_policy.py` + `erp_policy_internal/*` public 패턴 | already packaged precedent | **completed** | wrapper + shims | public wrapper 유지 | 추가 내부 리팩터는 별도 행 | — |
| SR-E2 | `erp_policy` **follow-up** (wrapper 바깥 family) | high-risk defer | not started | — | TBD | Wave 6 본편 제외 (계획서 §5.7 step 9) | W6+ / W8 |
| SR-B1 | `business_calendar` / `/calendar` 축 | explicit exception | not started (승인 게이트) | **explicit exception implementation** @ root | `foms/services/common/business_calendar.py` | controlling spec §1.2.16 승인 후 | 별도 ADR |
| SR-S1 | `storage` | high-risk defer | not started | shim-only | `foms/services/files/storage.py` | singleton/runtime init — Wave 6 pilot 제외 | W6+ |
| SR-C1 | `channel_*` family | high-risk defer | not started | shim-only | `foms/services/channel/*` | multi-module cluster — 전체 one-shot 금지 | W6+ |
| SR-O1 | Orders / ERP helper cluster | high-risk defer | not started | mixed | `foms/services/orders/*` | Tier 3 — 단일 pilot 축소 전 code batch 금지 | W6+ |
| SR-M1 | Measurement helper cluster | high-risk defer | not started | mixed | `foms/services/measurement/*` 등 | 동일 | W6+ |
| SR-P1 | Bootstrap / admin-adjacent (`app_init`, `context_processors`, `rate_limit`, …) | high-risk defer | not started | mixed | explicit exception 또는 `foms/services/admin/*` 후보 | platform-adjacent | W6+ |

## 4. `business_calendar` explicit exception (SR-B1 detail)

| 필드 | 내용 |
|------|------|
| why not now | controlling spec §1.2.16 승인 게이트 |
| required prep | 승인 + `/calendar` 축 영향 분석 |
| suggested restart | 전용 wave 또는 Wave 6+ 승인 후 batch |
| live import debt | `W6-B0` 표 — `services.business_calendar` 중심 (변경 없음 가정) |

## 5. Verification (docs-only)

- 표 완전성: pilot / precedent / exception / defer **분리** (erp_policy wrapper vs follow-up 분리 준수).
- `foms/services/README.md`에 status 요약 반영(§7).

## 6. Direction Lock (§2.6)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | 레인별 execution state가 한 표로 고정됨. |
| 2 | **문서화** | shim 제거는 Wave 8 소관으로 표에 위임. |
| 3 | **Y** | pilot 2건은 FR19 흡수 경로로 완료. |
| 4 | **Y** | defer는 과대 패키지화 방지. |
| 5 | **Y** | B6은 문서만. |
| 6 | **Y** | retirement wave 열 유지. |
| 7 | **Y** | README sync in B6/B7. |
| 8 | **Y** | 반복 시 레지스트리 확장 가능. |
| 9 | **Y** | service vs platform 경계 명시. |
| 10 | **Y** | 상태 기록만. |

## 7. Next legal batch

**`W6-B7`** — Closeout + Wave 7/8 handoff  
**Run record:** `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md`
