# Wave 6 Batch W6-B0 — Readiness gate + service queue lock

> **batch ID:** W6-B0  
> **risk axis:** docs / truth  
> **실행일:** 2026-04-13 (executor session)  
> **Attempt:** 1 — **completed** (readiness gate PASS)  
> **live revision:** `git rev-parse HEAD` → `240781907c445669ba320142835a7c297f0ba769`  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record만 생성/갱신 | product/runtime 코드 변경 |
| | spec/archive reference wiring (`W6-B7` 전용 batch에서만 계획서 허용 범위) |
| | `W6-B1`~`W6-B7` run record 선제 스캐폴드 |
| | `foms/platform/blueprints.py`, `app.py`, `run.py`, `start.sh`, `Procfile` 등 계획서 §1.3 freeze |

## 2. Inputs consumed

| # | 문서 / 증거 | 상태 |
|---|-------------|------|
| 1 | `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` | §1.2.16 `business_calendar` 게이트 포함 — Wave 6 mainline code pilot에 반영하지 않음(계획서 §1.2 스냅샷과 정합). |
| 2 | `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` | Wave 3 closeout — handoff 소비. |
| 3 | `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` | Wave 4 **full** closeout — 검증 명령 인용 가능. |
| 4 | `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md` | Wave 5 계획서 — 범위·순서 기준. |
| 5 | `docs/plans/2026-04-14-wave5-execution-state-memo.md` | **없음** (preferred memo path 부재). |
| 6 | **Substitute Wave 5 execution evidence:** `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md`, `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md` | 계획서 §2.1 `current execution state memo` 최소 계약 중 일부(완료 batch, 마지막 시도, verification, handoff)를 **run record 묶음**으로 충족하는지 **equivalent evidence accepted**로 판정(아래 §2.1 판정). |
| 7 | `docs/plans/2026-04-10-step3-batch46-storage-run-record.md` | Step 3 storage 선례. |
| 8 | `docs/plans/2026-04-07-step3-batch7-erp-display-run-record.md` | ERP display 선례. |
| 9 | `tests/test_foms_namespace_imports.py` | shim equivalence baseline — **pilot 순서로 복사하지 않음**(계획서 §2.1). |
| 10 | **Live tree:** `services/**/*.py`, `foms/services/**/*.py` | 아래 §3 스냅샷. |

### 2.1 Wave 4 / Wave 5 equivalent evidence (계획서 §2.1 필수 판정)

| Predecessor | 판정 | 근거 |
|-------------|------|------|
| Wave 4 closeout | **파일 존재 + full closeout** — Wave 6 선행 조건 충족 | `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` |
| Wave 5 closeout 단일 파일 | **없음** | dedicated Wave 5 batch7 closeout은 본 세션에서 확인하지 않음; 계획서는 closeout 없을 수 있음을 허용. |
| Wave 5 equivalent (`plan + execution state`) | **equivalent evidence accepted (substitute bundle)** | Preferred `docs/plans/2026-04-14-wave5-execution-state-memo.md` **부재**. 대체: **승인된 Wave 5 plan**(항목 4) + **W5-B0**(큐·순서·drift) + **W5-B3**(실행일 2026-04-14, `APP_OK` + `verify_result` + focused pytest **PASS**, 다음 배치 `W5-B4` handoff). 작성 시점·완료 batch·verification·defer·handoff가 run record 체인으로 추적 가능. **Gap:** 단일 memo 파일이 없으므로 후속 Wave 6 문서에서 동일 substitute 경로를 인용할 때 본 표를 함께 인용할 것. |
| Wave 5 equivalent가 strict memo만 허용한다고 해석할 경우 | **reject 아님** — 계획서는 closeout 없을 때 `W6-B0`에서 명시적 accept/reject만 요구; substitute가 최소 계약을 덮는다고 판단. | Stale 여부: W5-B3는 7일 이내(2026-04-14) 증거. |

## 3. Live tree snapshot (authoritative for queue lock)

| 경로 | 개수(`.py`) | 메모 |
|------|-------------|------|
| `services/` (루트, `jobs/` 포함) | **50** | `glob **/*.py` 기준 |
| `foms/services/` (`erp_policy_internal/`, `jobs/` 포함) | **56** | `glob **/*.py` 기준 |
| `tests/test_foms_namespace_imports.py` | 1 | shim import 스모크 baseline |

**Predecessor queue 표 vs live:** 계획서 §2.3 provisional queue와 충돌하는 **신규 top-level lane 대량 추가/삭제는 관찰되지 않음**. 세부 파일 목록은 `services/*.py` / `foms/services/*.py` glob으로 재현 가능.

## 4. Controlling SPEC snapshot validity (계획서 §5.1 step 2)

- 본 batch 시점에 **2026-04-14 기준으로 읽은** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`의 Wave 6 관련 규칙(§1.2.16 `business_calendar`, freeze, pilot 경계)과 **본 계획서 §1.2·§1.3** 사이에 **새 scope conflict를 트리거하는 문구 변경은 확인되지 않음** (문서 재비교는 spot; code batch 전 재확인 권장).
- **§8.15 / spec-scope-conflict:** 발동 없음.

## 5. Contract table — queue + live import debt lock (§7: W6-B0 정의)

### 5.1 Live `from services.` import debt (non-test product tree)

`apps/**/*.py`, `foms/**/*.py`, `scripts/**/*.py`에서 `from services.` / `import services.` 검색 결과, **live import debt의 유일 중심 축은 `services.business_calendar`**이다.

| Import debt lane | Non-test callers (경로) |
|------------------|-------------------------|
| `services.business_calendar` | `apps/erp_shipment_page.py`; `foms/api/measurement.py`; `foms/web/measurement/dashboard.py`; `foms/services/erp_display.py`; `foms/services/erp_policy_internal/tasks.py` (지연 import 구간 포함); `scripts/ops/erp_build_step_runner.py` |

**다른 root `services.*` live direct import:** 본 스캔에서 **추가 lane 없음** (provisional §2.3.1 표와 일치).

### 5.2 Authoritative service queue (lane → queue class)

`queue class` 값은 계획서 §2.3·§5.1과 정합되게 **재잠금**. (`expected`와 다르면 drift — 아래 drift 표.)

| Service lane | Representative surface | Final `queue class` | Drift vs provisional §2.3 |
|--------------|------------------------|----------------------|------------------------------|
| Packaged precedent / `jobs` | `foms/services/jobs/*`, `services/jobs/*` | `already packaged precedent` | 없음 |
| Packaged precedent / ERP policy internals | `foms/services/erp_policy_internal/*` | `already packaged precedent` | 없음 |
| Packaged precedent / ERP policy public wrapper | `foms/services/erp_policy.py`, `services/erp_policy.py` | `already packaged precedent` | 없음 |
| ERP policy follow-up refactor | beyond public wrapper | `high-risk defer` | 없음 |
| **Notifications** | `realtime_notifications.py` | **`mainline-pilot`** (first) | 없음 |
| **Files helper** | `file_utils.py` | **`mainline-pilot`** (second) | 없음 |
| Common explicit exception / `business_calendar` | `services/business_calendar.py` | `explicit exception` | 없음 |
| Files / `storage` | `storage.py` | `high-risk defer` | 없음 |
| `channel_*` family | 다수 `channel_*.py` | `high-risk defer` | 없음 |
| Orders / ERP helper cluster | `erp_display`, `erp_order_detail`, … | `high-risk defer` | 없음 |
| Measurement helper cluster | `measurement_*`, `map_snapshot`, … | `high-risk defer` | 없음 |
| Bootstrap / admin-adjacent | `app_init`, `context_processors`, `rate_limit`, … | `high-risk defer` | 없음 |

## 6. First / second pilot lock (계획서 §5.1 steps 6–7)

| Pilot | Canonical target (provisional, §2.4) | Existing focused test | Pilot lock checklist (§5.1-7) | Lock |
|-------|--------------------------------------|-------------------------|--------------------------------|------|
| **First:** `notifications` | `foms/services/notifications/realtime_notifications.py` | `tests/test_realtime_notifications.py` 존재 | single-leaf; 기존 테스트; context=`notifications` 단일; worker/bootstrap/schema 불필요; storage/channel/erp_policy/bootstrap 미혼입; **not** `business_calendar` | **TRUE** |
| **Second:** `file_utils` → `files` | `foms/services/files/file_utils.py` | `tests/test_file_utils.py` 존재 | helper-only; 기존 테스트; context=`files` 단일; 동일 제약 | **TRUE** |

## 7. Branch A / B / C (계획서 §5.1 분기 표 — verbatim next batch)

| 판정 | 조건 | 결과 |
|------|------|------|
| **Branch A** | `notifications` + `file_utils` 둘 다 잠김 | **채택** |

**다음 legal batch (문구 그대로):** **`W6-B1`부터 mainline 계속**

## 8. Packaged precedent note (계획서 §1.1 item 10)

- `foms/services/jobs/`, `services/jobs/` + root shim: **Tier 0 — reference only**, Wave 6 mainline code pilot **아님**.
- `foms/services/erp_policy_internal/`, 공개 `foms/services/erp_policy.py` / `services/erp_policy.py`: **동일** — 추가 refactor는 `high-risk defer` 행에서만 추적.

## 9. Initial lane execution-state snapshot (§7 항목 15 — status-register row type + execution state)

`§1.2.2` 번역: queue class → **row type** / **execution state** (초기값).

| Lane (요약) | Row type | Execution state | 메모 |
|-------------|----------|-----------------|------|
| `jobs`, `erp_policy_internal`, `erp_policy` public wrapper | already packaged precedent | completed | |
| `notifications`, `file_utils` | pilot lane | not started | **Branch A** — full mainline `W6-B1`→… |
| `business_calendar` | explicit exception | not started | code pilot **금지** |
| `storage`, `channel_*`, orders cluster, measurement cluster, bootstrap/admin-adjacent, erp_policy follow-up | high-risk defer | not started | |

**Branch B/C partial path 주석:** **해당 없음** (Branch A).

## 10. FR19 / NS-package-first decision (§7 항목 5)

**`no new package in B0`:** 본 batch는 queue/import-debt·분기·파일럿 순서만 재잠금하였고, **신규 `foms/services/<context>/` 패키지 디렉터리를 추가하지 않음**. `delete → merge → extend → add` 검토는 **후속 `W6-B2`~`W6-B5`에서** FR19 적용.

## 11. Provisional canonical / compat / shim / retirement (§7 항목 10–13) — authoritative dual-axis는 W6-B1

> **주의:** `root shim status` **dual-axis authoritative 잠금**은 **`W6-B1`**에서 수행. 본 절은 queue 표와 정합한 **provisional**만 기록.

| Lane | `canonical target` (provisional) | `flat compat path` | `root shim status` (provisional) | `retirement wave / removal condition` (provisional) |
|------|-----------------------------------|----------------------|-----------------------------------|-----------------------------------------------------|
| `notifications` | `foms/services/notifications/realtime_notifications.py` | `foms/services/realtime_notifications.py`; `services/realtime_notifications.py` | shim-only (현 구조) | Wave 8+ bridge retirement (계획서 §1.4) |
| `file_utils` | `foms/services/files/file_utils.py` | `foms/services/file_utils.py`; `services/file_utils.py` | shim-only (현 구조) | 동일 |
| `business_calendar` | `foms/services/common/business_calendar.py` | (향후) | **explicit exception implementation** (root에 live 구현) | 승인 게이트 + §1.2.16 |
| 기타 | §2.4 package target map | 각 `foms/services/*.py` / `services/*.py` | `W6-B1`에서 확정 | high-risk → defer register |

## 12. Verification (§6 — repo sanity baseline)

### 12.1 Baseline 우선순위 적용 (§6)

| 우선순위 | 후보 | 채택 여부 |
|----------|------|-----------|
| (1) Wave 5 handoff의 마지막 accepted verification | W5-B3 run record에 `APP_OK` + `verify_result` + pytest **PASS** (2026-04-14) | **참조만** — 커밋/트리가 현재 HEAD와 다를 수 있음 |
| (2) Predecessor closeout | Wave 4 closeout에 검증 명령 기재 | 참조 |
| **(3) Fresh** | 현재 브랜치에서 `APP_OK` + `verify_result --json` | **채택 (authoritative W6-B0 baseline)** |

**채택 근거:** 계획서 §6 — Wave 5 단일 memo 부재로 (1) 단독 handoff 문서가 불완전; (1)과 현재 서비스 트리/커밋이 일치함을 가정할 수 없어 **fresh (3)**를 병행 실행하여 Wave 6 service gate의 **단일 명확 baseline**으로 사용.

### 12.2 Executed commands (Attempt 1)

| 단계 | 명령 | 결과 |
|------|------|------|
| Git | `git rev-parse HEAD` | `240781907c445669ba320142835a7c297f0ba769` |
| APP_OK | `python -c "import app; print('APP_OK')"` | **APP_OK** |
| Harness | `python tools/harness/verify_result.py --json` | **success** (`"success": true`) |

### 12.3 기타

- docs-only consistency: 본 문서 표·분기·import debt·**Branch A**가 계획서 §5.1과 모순 없음.
- live import debt lane 누락: **없음** (`business_calendar`만 non-test 중심).

## 13. Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | authoritative queue·import debt·분기가 한 run record에 고정됨 |
| 2 | yes | root shim 축소는 하지 않음; 언제 줄일지는 W6-B1~ 및 Wave 8에 위임 |
| 3 | yes | B0는 패키지 추가 없음; FR19는 후속 batch |
| 4 | N/A | 신규 package 없음 |
| 5 | yes | product/wrapper/test 변경 0 |
| 6 | N/A | 코드 delta 없음 |
| 7 | N/A | `foms/services/README.md`는 **W6-B1** 허용 |
| 8 | yes | 반복 시에도 queue·예외·defer가 문서로만 명확해짐 |
| 9 | yes | service vs platform·Wave 7/8 경계 유지 |
| 10 | yes | 문서·증거만; 기능/라우트 변경 없음 |

## 14. Changes made

- `docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md` 생성 (본 파일)

## 15. product / wrapper / test delta (§7 항목 9)

**N/A (no code touch)** — 코드 변경 없음.

## 16. README update 여부 (§7 항목 14)

- **없음** — `foms/services/README.md`는 **W6-B1**에서 생성/갱신.

## 17. Drift / stop / defer decision (§7 항목 16)

| 항목 | 내용 |
|------|------|
| Drift | provisional §2.3 vs 본 재잠금 **불일치 없음** |
| §8 stop | **발동 없음** (§8.9 notifications lock fail → **해당 없음**; §8.10 file_utils → **해당 없음**) |
| Defer | `storage`, `channel_*`, … 는 **high-risk defer**로만 추적; 본 batch에서 code pilot **시도 없음** |

## 18. lint/diagnostics evidence (§7 항목 17)

**not applicable** — docs-only batch; 코드/설정 파일 미변경.

---

## Outcome

**PASS — Branch A 확정.**  
**Next legal batch:** `W6-B1` (Root shim registry + package-map lock + `foms/services/README.md`), 계획서 §5.2 runbook 준수.

**Gate for W6-B2+:** `W6-B1` 완료 후 계획서 순서대로 진행 (`W6-B2` notifications contract freeze — Branch A 전용).

