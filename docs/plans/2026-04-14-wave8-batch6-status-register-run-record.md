# Wave 8 Batch W8-B6 — Bridge status register

> **batch ID:** W8-B6  
> **risk axis:** docs / truth  
> **실행일:** 2026-04-14 (executor session)  
> **Attempt:** 1 — **completed**  
> **상위 계획:** `docs/plans/2026-04-14-wave8-legacy-bridge-retirement-execution-plan.md` §5.7  
> **진입 경로:** **Branch A** — `W8-B0`~`W8-B5` 완료 후 (service-compat + direct-import mainline pilots executed)

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record, `foms/services/README.md` Wave 8 pointer (이미 sync) | runtime 코드, 신규 pilot, shell collapse |

## 2. Inputs consumed

- `W8-B0` … `W8-B5` run records (completed chain)
- `docs/plans/2026-04-14-wave8-batch4-direct-import-freeze-run-record.md` (B4 candidate lock)
- `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md` (pre-Wave-8 service lanes)
- 본 계획서 §1.2 mainline pilot cap, §2.3 queue snapshot

## 3. Status register (authoritative)

| Row id | Lane / surface | row type | execution state (Wave 8) | bridge mechanism | root shim / bridge status (요약) | future canonical target / removal condition | continuation owner |
|--------|----------------|----------|---------------------------|------------------|-------------------------------------|---------------------------------------------|----------------------|
| WR-S1 | Service compat: `notifications` + `files` (root + flat shims) | mainline pilot | **completed** | compat shim | `services/realtime_notifications.py`, `services/file_utils.py`, `foms/services/realtime_notifications.py`, `foms/services/file_utils.py` **removed** (W8-B3) | `foms/services/notifications/*`, `foms/services/files/*` (달성) | — |
| WR-D1 | Direct-import: `files` / `address` / `erp_measurement` / measurement·production·completion page bridges | mainline pilot | **completed** | direct-canonical import bridge | six `apps/*` modules **removed** (W8-B5); `foms/platform/blueprints.py` uses canonical `foms.*` import sources | `foms/api/files`, `foms/api/address`, `foms/api/measurement`, `foms/web/measurement/dashboard`, `foms/web/production/dashboard`, `foms/web/cs/completion_dashboard` | — |
| WR-P1 | `apps/api/personal_board.py` (Blueprint shell) | adapter-shell defer | **not started** (Wave 8 mainline 제외) | adapter shell | thin shell remains; canonical helper `foms/api/personal_board` exists | shell collapse는 별도 wave / 승인 | W9+ |
| WR-O1 | `apps/api/orders/__init__.py` (route shell) | adapter-shell defer | **not started** | adapter shell | decorator + queue binding shell | 별도 batch | W9+ |
| WR-J1 | `services/jobs/*` + `_TASK_PATH_PREFIX` 문자열 계약 | runtime-string defer | **not started** | runtime-string bridge | 문자열 경로 계약 유지 | runtime contract 정리 선행 | W9+ |
| WR-B1 | `services/business_calendar.py` / `/calendar` | explicit-exception | **not started** | explicit exception implementation | spec §1.2.16 승인 게이트 | controlling spec 승인 후 | 별도 ADR |
| WR-H1 | High-risk cluster: `apps/api/notifications`, `attachments`, `chat/*`, `services/channel_*`, platform-adjacent shims | high-risk cluster defer | **continuation required** | mixed | consumer-side import reroute만 허용됐을 수 있음; owner-surface retirement는 미완 | owner-surface batch | W9+ / dedicated |
| WR-S2 | `storage` singleton / init-adjacent | high-risk defer | **not started** (W6 SR-S1 계승) | shim / defer | Wave 6 pilot 제외 유지 | `foms/services/files/storage.py` 등 | W6+ |

## 4. Bridge count summary (mainline code batches)

| Batch | Delta | Cumulative (mainline pilots) |
|-------|-------|--------------------------------|
| W8-B3 | −4 compat shims | −4 |
| W8-B5 | −6 direct-import bridges | −10 |

## 5. Verification (docs-only)

- 표가 계획서 §1.2 pilot cap·§2.3 스냅샷과 모순 없음.
- `WR-S1`·`WR-D1`은 해당 batch run record와 정합.
- defer 행이 mainline pilot으로 오인되지 않음.

## 6. Direction Lock (§2.6) — B6

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | mainline 완료·defer가 한 표로 고정됨. |
| 2 | **Y** | shell collapse·jobs·business_calendar는 표에 defer. |
| 3 | **Y** | B3/B5에서 bridge 순감 증거 존재. |
| 4 | **Y** | high-risk cluster는 continuation 행만. |
| 5 | **Y** | B6는 문서만. |
| 6 | **Y** | `blueprints.py` 변경은 B5 run record에 한정(순서 보존). |
| 7 | **Y** | sentinel/smoke는 B3/B5 run record에 기록됨. |

## 7. Next legal batch

**`W8-B7`** — Closeout + continuation handoff  
**Run record:** `docs/plans/2026-04-14-wave8-batch7-closeout-run-record.md`
