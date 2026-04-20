# Wave 6 Service Namespace Rationalization Execution Plan
> 작성일: 2026-04-14 | 상태: 계획서 확정 (실행은 `W6-B0` readiness gate 통과 후)
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `services/*.py`, `foms/services/*.py`, `tests/test_foms_namespace_imports.py`
> 선행 wave: `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
> 핵심 선례: `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md`, `docs/plans/2026-04-07-step3-batch7-erp-display-run-record.md`, `docs/plans/2026-04-10-step3-batch46-storage-run-record.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 6 — Service namespace rationalization**을 바로 실행할 수 있는 LLM용 runbook이다.

헤더의 `상태`는 plan maturity를 뜻한다. live execution phase(`W6-B0` gating 중, partial closeout, full closeout)는 헤더가 아니라 해당 run record와 closeout 문서가 authoritative truth다.

Wave 6의 목적은 "서비스도 언젠가 context package로 정리하자" 수준의 선언이 아니라, 아래 일곱 가지를 기계적으로 닫는 것이다.

1. 현재 `services/`와 `foms/services/`의 **service namespace queue**를 authoritative truth로 다시 잠근다.
2. 루트 `services/`의 모든 live row에 대해 **queue class**와 **root shim status**를 함께 잠그고, 각 row에 **canonical target / retirement wave / removal condition**을 붙인다.
3. `foms/services/README.md`를 서비스 namespace entrypoint로 만들고, context package map과 금지 의존성을 고정한다.
4. `notifications` lane을 첫 low-risk package pilot으로 잠그고, `foms/services/notifications/realtime_notifications.py` 기준의 package 선례를 만든다.
5. 두 번째 pilot은 `file_utils -> files`로 고정하고, helper-only lane까지만 구조-only로 집행한다.
6. `business_calendar`, `storage`, `channel_*`, `erp_policy` 추가 refactor, `app_init/context_processors/rate_limit` 같은 lane은 억지로 package move하지 않고 **explicit-exception / status register**로 잠근다.
7. Wave 7(test/contract rationalization)과 Wave 8(legacy bridge retirement)이 닫아야 할 잔여 bridge를 명시해, Wave 6이 Step 3의 반복이나 Wave 8의 조기 실행으로 흐르지 않게 한다.

### 1.2 기능 요구사항
1. Wave 6의 authoritative truth는 항상 `services/*.py`, `foms/services/*.py`, `tests/test_foms_namespace_imports.py`, Wave 3~5 handoff evidence다.
2. Wave 6는 **service namespace rationalization**이다. API canonicalization(Wave 3), web/page migration(Wave 4), front-end island rebaseline(Wave 5), test rationalization(Wave 7), bridge retirement(Wave 8)을 본편으로 포함하면 안 된다.
3. 한 batch는 반드시 **한 service lane / 한 risk axis / 한 canonical package target**만 다룬다.
4. 루트 `services/`에는 새 canonical 구현을 추가하지 않는다. Wave 6에서 루트 `services/`는 shim 또는 explicit exception만 허용한다.
5. explicit exception은 "나중에 보자" 상태로 두지 않는다. 같은 batch run record 안에 `why-not-now`, `canonical target`, `retirement wave`, `removal condition`이 없으면 허용하지 않는다.
6. flat `foms/services/*.py`는 touch 시점에만 context package로 이동한다. repo-wide big-bang package move는 금지한다.
7. touched lane의 preferred canonical shape는 기본적으로 `foms/services/<context>/<leaf>.py` + 필요 최소한의 compatibility shim이다.
8. `common/`은 cross-context, domain-neutral helper에만 허용한다. generic dump bucket처럼 쓰면 안 된다.
9. `channel`, `files`, `notifications`는 API-first context로 본다. human-facing page가 없다고 해서 generic helper bucket으로 되돌리지 않는다.
10. `foms/services/jobs/`, `foms/services/erp_policy_internal/`, 그리고 이를 public surface로 노출하는 `foms/services/erp_policy.py` wrapper는 packaged precedent다. Wave 6에서 이 선례/공개 표면을 깨는 방향으로 재구조화하지 않는다.
11. route path, blueprint registration, template/static path, DB schema, worker registration, bootstrap semantics는 기본 freeze다.
12. root `services.*`와 touched flat `foms.services.*` 경로는 compatibility surface다. caller를 바꾸려면 same-batch shim + retirement plan이 필수다.
13. `foms/services/README.md`는 Wave 6의 docs batch 중 `허용 변경`에 README touch가 포함된 batch마다 최신 상태를 반영해야 한다.
14. low-risk pilot은 **existing focused test가 있거나, 최대 1개의 새 contract test 파일만으로 닫을 수 있는 lane**만 허용한다.
15. controlling spec §1.2.16에 따라 `business_calendar` / `/calendar` 축은 별도 승인 전까지 Wave 6 mainline pilot에서 제외하고 explicit exception/승인 게이트로만 다룬다.
16. `storage` lane은 singleton/runtime init 계약 때문에 low-risk pilot이 아니다. `files` context 안의 eventual target만 잠그고, 본편 pilot은 helper-only lane부터 시작한다.
17. `channel_*` family는 multi-module cluster다. Wave 6 mainline에서 package split을 하더라도 one-shot full family move를 기본값으로 삼지 않는다.
18. testing은 Wave 7 본편처럼 재구조화하지 않는다. Wave 6에서는 touched lane의 focused contract만 최소 확장한다.
19. 어떤 batch도 "새 package 디렉터리 추가"를 성과로 주장하지 못한다. package 추가와 함께 caller/test/shim/retirement evidence가 있어야 한다.
20. future LLM은 이 문서의 provisional queue를 복사하지 말고, `W6-B0` run record에서 live evidence로 다시 잠가야 한다.

`controlling SPEC §1.2.16` snapshot(본 계획에서 필요한 최소 뜻)은 다음 한 문장으로 고정한다: `business_calendar` / `/calendar` 축은 Wave 6 mainline에서 package pilot 또는 구조 변경 대상으로 승격하지 않고, 별도 승인 전까지 explicit exception + future target 기록만 허용한다.
이 snapshot과 본 계획이 인용하는 다른 controlling SPEC 규칙은 모두 2026-04-14에 읽은 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` 기준이다. 이후 SPEC wording이 달라졌다면 `W6-B0`에서 snapshot validity를 다시 확인하기 전까지 Wave 6 mainline code batch를 시작하지 않는다.

### 1.2.1 FR / namespace shorthand definitions
- `FR19`: `delete -> merge -> extend -> add` 순서로 판단한다. 새 canonical package/leaf를 추가하기 전에 기존 lane을 더 큰 context package로 흡수할 수 없는지 먼저 적는다.
- `FR20`: local `README.md` gate다. 하나의 context package가 runtime module 3개 이상이거나 2개 이상 layer/consumer 축과 얽히면 local entrypoint를 유지해야 한다.
- `NS-compat`: touched lane의 root shim과 flat `foms.services.*` path는 compatibility surface다. 바뀌면 same-batch bridge + retirement plan이 필수다.
- `NS-package-first`: touched flat module은 특별한 이유가 없다면 `foms/services/<context>/<leaf>.py`로 수렴시킨다. 새 generic bucket package는 `common/` 외에 만들지 않는다.
- `NS-explicit-exception`: root `services/` 구현이 일시적으로 남아도 되지만, run record에 `why-not-now`, `future canonical target`, `retirement wave`, `removal condition`이 없으면 실패다.
- `NS-row-status`: `mainline-pilot`, `already packaged precedent`, `explicit exception`, `high-risk defer`는 queue class다. `shim-only`는 별도 row type이 아니라 root shim status column 값이다.
- `NS-erp-policy-split`: `foms/services/erp_policy.py` public wrapper와 `erp_policy` follow-up refactor는 서로 다른 lane이다. status register/run record에서 한 행으로 합치지 않는다.

#### 1.2.2 Queue class / row type / root shim status mapping
Wave 6 문서에서는 아래 두 축을 섞지 않는다.

| 축 | 값 | 의미 |
|------|------|------|
| `queue class` | `mainline-pilot` | Wave 6 code batch 후보 |
| `queue class` | `already packaged precedent` | reference only |
| `queue class` | `explicit exception` | 승인 게이트 또는 구조적 이유로 root/live 예외 유지 |
| `queue class` | `high-risk defer` | Wave 6 mainline code batch 금지 |
| `status register row type` | `pilot lane` | mainline-pilot lane의 B6/B7 표현 |
| `status register row type` | `already packaged precedent` | reference-only lane의 B6/B7 표현 |
| `status register row type` | `explicit exception` | 승인 게이트/예외 lane의 B6/B7 표현 |
| `status register row type` | `high-risk defer` | defer lane의 B6/B7 표현 |
| `root shim status` | `shim-only` | root `services/` row가 thin shim임 |
| `root shim status` | `explicit exception implementation` | root `services/` row가 아직 live 구현을 가짐 |
| `root shim status` | `not applicable` | root row가 없거나 packaged precedent만 남음 |

추가 규칙:

- `queue class = mainline-pilot`인 lane은 B6/B7 status register에서 `row type = pilot lane`으로 표현한다.
- `pilot lane`의 실제 완료 여부는 `execution state = completed/not started/partial`로 적는다.
- `Tier 3 medium-risk domain cluster`는 Wave 6 문서에서는 기본적으로 `queue class = high-risk defer`로 기록한다. docs batch에서 단일 pilot lane으로 축소·잠기기 전에는 `mainline-pilot`으로 승격하지 않는다.

### 1.3 Out of scope / freeze
Wave 6에서는 아래를 건드리지 않는다.

- `foms/platform/blueprints.py`, `app.py`, `run.py`, `start.sh`, `Procfile`, `Dockerfile`, `alembic.ini`, `railway*.toml`
- route path, blueprint name, API response shape, decorator order
- page/template/static 물리 이동
- DB schema 변경, Alembic revision 추가, persistence lifecycle 재설계
- worker/bootstrap registration 구조 변경
- chat/socketio binding 구조 변경
- front-end island decomposition / merge
- Wave 7 수준의 테스트 재설계
- Wave 8 수준의 root shim 대량 제거
- packaging reopen (`src/foms`, pyproject hardening)

여기서 `root bootstrap 파일`은 `app.py`, `run.py`, `start.sh`, `Procfile`만 뜻한다. `Dockerfile`, `alembic.ini`, `railway*.toml`은 frozen root file이지만 `§8`의 11번에서 말하는 root bootstrap file은 아니다. `services/app_init.py` 같은 service lane helper도 root bootstrap file이 아니라 high-risk defer service module로 취급한다.

Wave 6은 **service queue lock + shim registry + low-risk package pilots + explicit exception/status register**까지만 담당한다.

추가 규칙:

- 어떤 Wave 6 batch라도 `foms/platform/blueprints.py` 또는 root bootstrap 파일 수정이 필요해지는 순간 out-of-scope로 판단하고 즉시 stop/defer한다.
- `business_calendar` 축은 별도 승인 전까지 code pilot로 승격하지 않는다. Wave 6에서는 explicit exception row와 future target만 잠근다.

### 1.4 Scope reconciliation — Step 3 / Wave 7 / Wave 8과의 정합
이 계획은 Step 3의 runtime namespace 도입을 반복하거나, Wave 8 bridge retirement를 조기 실행하는 문서가 아니다. 해석은 아래로 고정한다.

1. Step 3는 `foms/services/*` canonical source 도입과 root `services/*` thin shim을 만든 선례다.
2. Wave 6는 그 선례를 바탕으로 **flat canonical modules를 context package 기준으로 재정렬**하고, root shim/explicit exception registry를 잠그는 단계다.
3. 따라서 Wave 6는 "모든 root shim을 삭제"하는 wave가 아니다. root `services/`는 compatibility surface로 남을 수 있지만, 더 이상 무기한 방치되면 안 된다.
4. Wave 7은 test/contract rationalization이다. Wave 6는 touched lane에 필요한 최소 focused test만 추가하고, large test-suite reorganization은 넘긴다.
5. Wave 8은 bridge retirement다. Wave 6가 남기는 `canonical target / retirement wave / removal condition`은 Wave 8이 닫아야 할 backlog다.
6. controlling spec §1.2.16 때문에 `business_calendar` / `/calendar` 축은 Wave 6 mainline pilot이 아니라 승인 게이트가 있는 explicit exception lane으로 취급한다.
7. Wave 5의 giant front-end lane과 섞이면 안 된다. service namespace 작업 때문에 template/static/page lane이 흔들리면 그것은 scope drift다.
8. `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md`의 Wave 6 boundary note를 포함한 **모든 predecessor closeout/plan/run record**(Wave 3/4/5 plan, Step 3 precedent run record, handoff evidence 묶음 포함) 중 Wave 6를 `service/persistence rationalization`처럼 넓게 부르는 문구가 있더라도, 본 계획이 authoritative override다. Wave 6는 persistence/schema/worker/bootstrap structural change를 포함하지 않는다.
9. 상위 spec의 `Step 6`(legacy bridge 축소 로드맵)와 본 문서의 `Wave 6`(service namespace rationalization)는 다른 번호 체계다. numeric label이 같아도 같은 작업으로 취급하면 안 된다.
10. 이 override는 predecessor plan/closeout/run record wording 전체에 적용된다. controlling SPEC 자체와 충돌이 발견되면 본 계획이 SPEC를 덮어쓰지 않으며, 즉시 stop 후 기준선 정합부터 다시 맞춘다.
11. 이 override는 predecessor artifact 바깥의 binding policy/harness/decision 문서를 자동으로 덮어쓰지 않는다. 그런 문서가 Wave 6 scope를 제한하면 별도 충돌로 기록하고 `W6-B0`에서 정합 판단을 먼저 남긴다.

## 2. Current Service Truth — 현재 service namespace landscape

### 2.1 선행 handoff gate
Wave 6 actual execution은 아래 산출물을 소비한 뒤에만 시작한다.

1. `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` 또는 equivalent Wave 3 closeout evidence
2. `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` 또는 equivalent Wave 4 closeout evidence
3. `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md` + Wave 5 execution-state evidence(closeout 또는 equivalent state memo)
4. `docs/plans/2026-04-10-step3-batch46-storage-run-record.md`
5. `docs/plans/2026-04-07-step3-batch7-erp-display-run-record.md`
6. `tests/test_foms_namespace_imports.py`
7. live `services/*.py`, `services/jobs/*.py`, `foms/services/*.py`, `foms/services/*/__init__.py`

추가 규칙:

- Wave 6 code batch는 predecessor closeout file 또는 아래 equivalent 정의를 충족한 evidence가 있을 때만 시작한다.
- `equivalent closeout evidence`를 쓰려면 최소 아래를 포함해야 한다.
  - 단일 markdown closeout 문서 1개 또는 참조 가능한 run-record 묶음 1세트
  - 실제 완료된 batch와 미실행 batch 목록
  - defer register
  - `why-not-now`, `required prep`, `suggested next wave/batch`
  - 다음 wave로 넘어오는 handoff note
- Wave 4/5 closeout이 실제 파일로 없더라도 본 문서는 drafted plan으로 존재할 수 있다.
- actual execution에서 Wave 4/5 closeout file이 없으면 `W6-B0` run record 안에 `equivalent evidence accepted` 또는 `equivalent evidence rejected`를 명시적으로 남긴다. `W6-B0`은 이 판단을 생략하거나 self-waive할 수 없다.
- Wave 5는 closeout file이 아직 없을 수 있으므로, 최소한 `approved Wave 5 plan file + current execution state memo`가 있어야 equivalent evidence 검토를 시작할 수 있다.
- Wave 5 closeout file이 없을 때 preferred memo pointer는 `docs/plans/2026-04-14-wave5-execution-state-memo.md`다. 다른 경로를 쓰면 `W6-B0` prompt/run record가 exact file path를 명시해야 한다.
- `current execution state memo` 최소 계약:
  - 완료된 batch 목록
  - 현재 in-progress 또는 마지막 시도 batch
  - blockers / stop reason
  - defer 또는 미완 lane 요약
  - verification 상태
  - 다음 wave/batch handoff note와 작성 시점
- memo가 이후 Wave 5 진행을 반영하지 못하거나 현재 batch 범위를 특정하지 못하면 stale로 보고 `equivalent evidence rejected` 처리한다.
- equivalent evidence는 아래 중 하나라도 빠지면 reject한다: 작성 시점, 완료 batch 목록, 현재/마지막 시도 batch, verification 상태, defer/미완 lane 요약, 다음 handoff note.
- `current execution state memo`는 `W6-B0` 실행 시점 기준 최근 7일 이내 작성본이거나, 더 오래됐으면 같은 run record 안에 "왜 아직 유효한지" 근거가 있어야 한다. 없으면 stale로 보고 reject한다.
- predecessor evidence와 live `services/` / `foms/services/` tree가 충돌하면 live tree를 truth로 두고, drift를 `W6-B0` run record에 먼저 적는다.
- `tests/test_foms_namespace_imports.py`는 shim equivalence baseline이지, queue snapshot 문서가 아니다. future LLM은 test import list를 그대로 pilot order로 승격하면 안 된다.
- Wave 3 closeout/run record는 evidence consume용이다. Wave 6에서 API canonicalization, route/page migration, persistence/schema/worker 구조 변경을 재개할 수 없으며, 본 계획의 `§1.2`, `§1.4`가 항상 우선한다.

### 2.2 Risk-tier 판정 규칙
Wave 6는 service namespace lane을 아래 다섯 tier로만 다룬다.

| Tier | 기준 | 허용 방식 |
|------|------|------|
| `Tier 0 packaged precedent` | 이미 package precedent가 검증된 lane (`jobs`, `erp_policy_internal`, public wrapper `erp_policy.py`) | 선례로만 사용, mainline code pilot 금지 |
| `Tier 1 low-risk package pilot` | 구현/공개 표면이 좁고, existing focused test가 있으며 helper-only 또는 single-leaf package로 닫히는 lane | early pilot 대상 |
| `Tier 2 explicit-exception / approval-gated lane` | root explicit exception이지만 상위 spec 승인 게이트가 있거나 mainline pilot으로 즉시 올릴 수 없는 lane | register only |
| `Tier 3 medium-risk domain cluster` | context package 방향은 명확하지만 leaf가 여러 개고 caller fan-in이 넓은 lane | contract/docs 우선, 단일 pilot로 축소될 때만 진행 |
| `Tier 4 high-risk cross-cutting` | singleton/runtime init, worker/bootstrap, webhook/security, multi-module orchestration이 결합된 lane | defer 또는 contract-only |

보조 판정 규칙:

1. flat module이 작아도 caller fan-in이 넓거나 bootstrap/worker와 얽히면 low-risk가 아니다.
2. live non-test code에서 `from services.<x>`가 남아 있는 lane은 explicit exception 또는 common pilot 후보로 먼저 본다.
3. existing focused test가 전혀 없고, 새 테스트 1개로도 계약을 닫을 수 없으면 `Tier 1`이 아니다.
4. context target이 두 개 이상으로 갈릴 수 있는 lane은 `W6-B1` 또는 `W6-B4`에서 먼저 잠그기 전까지 code batch로 올리지 않는다.

### 2.3 현재 queue snapshot
주의:

- 아래 표는 **Wave 6 초안 시점의 provisional service queue snapshot**이다.
- authoritative queue는 `W6-B0` run record가 supersede한다.
- future LLM은 이 표를 inventory처럼 복사하지 말고 `W6-B0`에서 evidence를 다시 적어야 한다.

| Service lane | Representative surface | 현재 관찰 | 초기 tier | expected queue class | Wave 6 처리 원칙 | 미래 canonical target |
|------|------|------|------|------|------|------|
| Packaged precedent / jobs | `foms/services/jobs/*` + `services/jobs/*` | package precedent 검증 완료, root shim도 존재 | `Tier 0 packaged precedent` | `already packaged precedent` | reference only | `foms/services/jobs/*` |
| Packaged precedent / ERP policy internals | `foms/services/erp_policy_internal/*` | package precedent 검증 완료 | `Tier 0 packaged precedent` | `already packaged precedent` | reference only | `foms/services/erp_policy_internal/*` |
| Packaged precedent / ERP policy public wrapper | `foms/services/erp_policy.py` | wrapper public surface 유지, 추가 refactor 대상 아님 | `Tier 0 packaged precedent` | `already packaged precedent` | reference only | `foms/services/erp_policy.py` 유지 |
| ERP policy follow-up refactor | `erp_policy` family beyond public wrapper | public wrapper는 유지하되, 추가 구조 개편은 Wave 6 mainline 대상이 아님 | `Tier 4 high-risk cross-cutting` | `high-risk defer` | defer only | follow-up decision after Wave 6 |
| Notifications | `foms/services/realtime_notifications.py` + `services/realtime_notifications.py` | single-leaf lane, existing focused test 존재, API-first context 이름도 명확 | `Tier 1 low-risk package pilot` | `mainline-pilot` | first code pilot | `foms/services/notifications/realtime_notifications.py` |
| Files helper | `foms/services/file_utils.py` + `services/file_utils.py` | helper-only lane, existing focused test 존재, `files` context target 명확 | `Tier 1 low-risk package pilot` | `mainline-pilot` | second code pilot | `foms/services/files/file_utils.py` |
| Common explicit exception | `services/business_calendar.py` | root implementation이 아직 live이며 canonical→legacy import debt가 남아 있지만 controlling spec 승인 게이트가 있음 | `Tier 2 explicit-exception / approval-gated lane` | `explicit exception` | explicit exception register only | `foms/services/common/business_calendar.py` |
| Files / storage | `foms/services/storage.py` + `services/storage.py` | singleton/runtime init, caller fan-in 넓음 | `Tier 4 high-risk cross-cutting` | `high-risk defer` | queue lock + defer 기본값 | `foms/services/files/storage.py` |
| Channel family | `foms/services/channel_*.py` + root shims | multi-module cluster, webhook/security/WAM/read-model 혼재 | `Tier 4 high-risk cross-cutting` | `high-risk defer` | defer 기본값 | `foms/services/channel/*` |
| Orders / ERP helper cluster | `erp_display.py`, `erp_order_detail.py`, `erp_product_items.py`, `erp_utils.py`, `estimate_service.py`, `order_*` family | context target은 보이지만 leaf가 많고 caller fan-in 큼 | `Tier 3 medium-risk domain cluster` | `high-risk defer` | queue lock only; docs batch에서 단일 pilot lane으로 축소되기 전까지 pilot 금지 | `foms/services/orders/*` |
| Measurement helper cluster | `measurement_dates.py`, `measurement_manager_colors.py`, `map_snapshot.py`, `order_geocode.py`, `geocode_helpers.py` | measurement context와 common/helper 경계가 섞여 있음 | `Tier 3 medium-risk domain cluster` | `high-risk defer` | queue lock only; docs batch에서 단일 pilot lane으로 축소되기 전까지 pilot 금지 | `foms/services/measurement/*` 또는 `foms/services/common/*` 일부 |
| Bootstrap / admin-adjacent helpers | `app_init.py`, `context_processors.py`, `rate_limit.py`, `menu_config.py`, `erp_permissions.py` | bootstrap, request-context, admin/menu policy가 섞인 platform-adjacent lane | `Tier 4 high-risk cross-cutting` | `high-risk defer` | defer 기본값 | default는 explicit exception 유지, `foms/services/admin/*`는 `W6-B1` follow-up 후보 |

### 2.3.1 Live import debt snapshot
Wave 6 초안 시점에서 live non-test code의 `from services.` 의존은 아래로 관찰된다.

| Import debt lane | Current non-test callers | 해석 |
|------|------|------|
| `services.business_calendar` | `apps/erp_shipment_page.py`, `foms/api/measurement.py`, `foms/web/measurement/dashboard.py`, `foms/services/erp_display.py`, `foms/services/erp_policy_internal/tasks.py`, `scripts/ops/erp_build_step_runner.py` | 현재 live canonical→legacy import debt의 사실상 유일한 중심 lane |
| other root `services.*` shims | 대부분 `tests/test_foms_namespace_imports.py` baseline 또는 thin compatibility surface에서만 확인 | Wave 6 mainline은 "root shim 존재 자체"보다 `business_calendar`와 package map ambiguity를 우선 처리해야 함 |

추가 규칙:

- `W6-B0`은 위 import debt table을 live evidence로 다시 계산해야 한다.
- `business_calendar` 외 live root-service import가 새로 발견되면 provisional snapshot을 믿지 말고 `W6-B0` run record에서 재분류한다.
- `expected queue class`는 provisional 기대값이다. `W6-B0`은 각 lane의 최종 `queue class`를 이 열과 비교해 drift를 기록해야 한다.
- `§2.3` 표는 queue snapshot용이므로 provisional `root shim status`를 싣지 않는다. dual-axis 잠금(`queue class` + `root shim status`)은 `W6-B1` shim registry에서 authoritative하게 수행한다.
- bootstrap/admin-adjacent row의 `expected queue class = high-risk defer`는 Wave 6 code batch 금지를 뜻한다. 미래 canonical target 칸의 `default explicit exception 유지`는 target-policy 메모이며, queue class 값과 같은 축이 아니다.

### 2.4 Package target map — provisional
Wave 6는 아래 target map을 provisional 기준으로 잠그고 시작한다.

| Current leaf / cluster | Preferred package target | 비고 |
|------|------|------|
| `jobs/*` family | `foms/services/jobs/*` 유지 | packaged precedent이므로 map에 반복 명시만 하고, Wave 6 mainline move 대상은 아님 |
| `realtime_notifications.py` | `foms/services/notifications/realtime_notifications.py` | `notifications` context 이름은 spec 고정 예시 |
| `file_utils.py` | `foms/services/files/file_utils.py` | helper-only low-risk lane |
| `storage.py` | `foms/services/files/storage.py` | high-risk defer, Wave 6 mainline pilot 아님 |
| `business_calendar.py` | `foms/services/common/business_calendar.py` | explicit exception + approval gate |
| `channel_*` family | `foms/services/channel/*` | full family move 금지, lane lock만 수행 |
| `erp_policy.py` public wrapper | `foms/services/erp_policy.py` 유지 + 내부 `erp_policy_internal/*` precedent 존중 | wrapper public surface는 packaged precedent, 추가 refactor만 defer 대상 |
| `erp_policy` follow-up refactor | follow-up decision after Wave 6 | public wrapper 유지와 별개인 defer lane이며, register에서는 별도 row id로 유지 |
| `erp_display.py`, `erp_order_detail.py`, `erp_product_items.py`, `erp_utils.py`, `estimate_service.py`, `order_*` family | `foms/services/orders/*` | medium-risk domain cluster |
| `measurement_dates.py`, `measurement_manager_colors.py`, `map_snapshot.py`, `order_geocode.py`, `geocode_helpers.py` | `foms/services/measurement/*` 또는 일부 `common/*` | package ambiguity를 docs batch에서 먼저 잠근다 |
| `app_init.py`, `context_processors.py`, `rate_limit.py`, `menu_config.py`, `erp_permissions.py` | default는 explicit exception 유지, `foms/services/admin/*`는 `W6-B1`에서 명시적으로 잠길 때만 follow-up candidate | queue snapshot의 bootstrap/admin-adjacent helper cluster 전체를 포괄하며, Wave 6 mainline code batch 금지 |

추가 규칙:

- 위 target map은 provisional이다. `W6-B1` run record가 authoritative package map으로 supersede한다.
- generic bucket package는 `common/` 외 금지다.
- one leaf를 옮긴다고 해서 같은 context의 나머지 leaf 전체 move를 자동 허용하면 안 된다.

### 2.5 Second pilot rule
Wave 6의 second pilot은 `file_utils -> files`로 고정한다.

추가 규칙:

1. `business_calendar`는 controlling spec §1.2.16 때문에 Wave 6 mainline pilot 경쟁에서 제외한다.
2. `file_utils` lane이 helper-only package pilot로 잠기지 못하면 Wave 6는 `notifications` single-pilot partial closeout 경로로 내려간다.
3. `business_calendar`는 `W6-B6` status register에서 explicit exception + future canonical target만 남긴다.

### 2.6 Direction Lock Questions
모든 batch run record는 아래 10문항에 대해 yes/no + 한 줄 근거를 남긴다.

1. 이번 batch는 service source of truth를 더 선명하게 만드는가
2. root shim 또는 flat canonical 경로를 줄이는가, 아니면 남긴다면 언제 어떻게 줄일 것인가
3. 새 package/leaf 추가 전에 delete/merge/extend를 실제로 검토했는가
4. 새 package가 있다면 그것이 **가장 큰 유지보수 가능 context package**인가
5. product/wrapper/test file 수는 순감 또는 최소 동결인가
6. 순증가라면 어떤 shim/flat path를 언제 없앨지 이미 적혀 있는가
7. `foms/services/README.md` 또는 local entrypoint가 이번 변경 범위를 반영하는가
8. 이 패턴이 10번 반복돼도 `foms/services` 트리가 더 명확해질 것 같은가
9. service / platform / bridge / docs 경계가 더 선명해졌는가
10. 지금 이 batch가 구조 작업인지, 아니면 슬쩍 기능 변경을 섞고 있는지 명확한가

## 3. Fixed Execution Pipeline — 고정 실행 순서

 Wave 6 **전체**는 아래 순서를 지킨다. 단, executor는 항상 `W6-B0`에서 먼저 `Branch A/B/C`를 판정한 뒤 이 순서를 읽는다. `Branch B`는 `W6-B4`~`W6-B5`를 건너뛰고, `Branch C`는 `W6-B2`~`W6-B5`를 건너뛴다. 각 batch는 이 순서 중 자신에게 배정된 subset만 수행하며, 실제 batch 경계는 `§4`, `§5` runbook이 우선한다.

1. predecessor evidence + live service tree consume
2. service queue와 shim registry lock
3. `notifications` contract freeze
4. `notifications` package pilot canonicalization
5. `file_utils` contract freeze
6. `file_utils` package pilot canonicalization
7. explicit exception / high-risk lane status register 정리
8. closeout + Wave 7 / Wave 8 handoff 고정

이 순서는 `Branch A` 기준의 full-mainline 기본형이다. `§5.1`의 `Branch B`가 선택되면 `W6-B4`~`W6-B5`를 건너뛰고, `Branch C`가 선택되면 `W6-B2`~`W6-B5`를 건너뛴다. `§8 Stop Conditions`가 발동한 경우에도 closeout 경로로 바로 내려갈 수 있으며, 이런 branch/stop 상황에서는 `§5.1`, `§8`, `§9.3`가 `§3`보다 우선한다.

추가 규칙:

- 하나의 batch에서 두 context package를 동시에 canonicalize하지 않는다.
- code batch는 항상 `APP_OK`와 `verify_result`를 요구한다.
- code batch 검증이 실패하면 현재 batch 안에서만 `fix-forward` 또는 `revert + documented defer`를 결정한다.
- `W6-B4`가 실패하면 `W6-B5`로 가지 않는다. 이 경로는 `late-file-utils-stop`으로 라벨링하고 곧바로 `W6-B6`/`W6-B7` partial closeout 경로를 따른다.
- code batch가 `revert + documented defer` 또는 `§8.12`로 끝났다면 `W6-B6`/`W6-B7` 전에 fresh `APP_OK` + `verify_result`와 agreed import smoke(또는 그 불가 사유)를 다시 남겨야 한다.
- second pilot이 실패하더라도 `notifications` pilot까지 완료된 상태라면 즉시 `W6-B6` status register와 `W6-B7` partial closeout으로 넘어간다.
- partial closeout은 항상 status-register content를 포함해야 한다. dedicated `W6-B6` 파일 또는 `W6-B7` 내부 merged section 둘 중 하나가 없으면 partial closeout으로 인정하지 않는다.
- code batch가 `§8 Stop Conditions`로 중단되면 다음 legal batch는 `W6-B6` 또는 `W6-B7` docs-only closeout 경로다.
- Wave 6는 run record 안에서만 shim registry와 status register를 관리한다. 새 sibling inventory 문서를 만들지 않는다.

## 4. Wave 6 Batch Catalog — LLM 실행 순서

### 4.1 Batch table
| Batch ID | 이름 | Risk axis | 주 결과물 | 선행 조건 | 필수 run record |
|------|------|------|------|------|------|
| W6-B0 | Readiness gate + service queue lock | docs / truth | authoritative service queue, import debt table, first/second pilot order | Wave 3~5 handoff evidence | `docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md` |
| W6-B1 | Root shim registry + package-map lock | docs / contract | root shim registry, explicit exception rows, `foms/services/README.md`, authoritative package map | W6-B0 | `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md` |
| W6-B2 | Notifications contract freeze | docs / contract | `notifications` public/runtime contract, preferred package shape | W6-B1 | `docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md` |
| W6-B3 | Notifications package pilot canonicalization | code / local pilot | `foms/services/notifications/realtime_notifications.py` canonical target + compatibility shim map | W6-B2 | `docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md` |
| W6-B4 | Files helper contract freeze | docs / truth | `file_utils` public/runtime contract, preferred package shape | W6-B3 | `docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md` |
| W6-B5 | Files helper package pilot canonicalization | code / local pilot | `foms/services/files/file_utils.py` canonical target + caller/test/shim delta | W6-B4 | `docs/plans/2026-04-14-wave6-batch5-files-helper-pilot-run-record.md` |
| W6-B6 | Lane status register | docs / truth | pilot lanes, packaged precedent, `business_calendar` explicit exception, high-risk defer rows | `W6-B0` and `W6-B1` both completed + [Branch A = `W6-B5` 완료, Branch B = `W6-B3` 완료, Branch C = 최소 `W6-B1` 완료, 기타 = `§5.7` entry criteria / `§8` documented stop] | `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md` |
| W6-B7 | Closeout + Wave 7/8 handoff | docs / handoff | full/partial closeout, next continuation order, spec/archive update | dedicated `W6-B6` file 또는 `§5.8` merged status-register section을 허용하는 stop-triggered closeout state | `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md` |

### 4.2 Batch별 기본 원칙
- 본 표에 적힌 batch run record 파일은 아직 scaffold하지 않는다. 해당 batch를 실제 시작할 때 정확한 파일명으로 하나씩 만든다.
- 이미 placeholder/stub run record가 존재하면 새 sibling 파일을 만들지 말고 그 파일을 재사용한다.
- `W6-B0`, `W6-B1`, `W6-B2`, `W6-B4`, `W6-B6`, `W6-B7`는 docs-first다.
- `W6-B3`, `W6-B5`만 code-touch batch다.
- `W6-B3`은 `notifications` lane만 다룬다.
- `W6-B5`는 `file_utils` lane 하나만 다룬다.
- `W6-B4`, `W6-B5`는 mainline/Branch A 전용이다. `Branch B/C`에서는 실행하지 않고 `W6-B6`/`W6-B7` 경로로 내려간다.
- `W6-B2`, `W6-B3`도 `Branch C`에서는 실행하지 않는다.
- `W6-B6`의 legal entry는 세 가지뿐이다: `Branch A`에서 `W6-B5` 이후, `Branch B`에서 `W6-B3` 이후, `Branch C`에서 최소 `W6-B1` 이후. 그 외에는 `§8` stop evidence가 같은 run record chain에 있어야 한다.
- `storage`, `channel_*`, `erp_policy` 추가 refactor, `app_init/context_processors/rate_limit/menu_config/erp_permissions`는 `W6-B6` status register로 먼저 잠그기 전까지 code batch에 넣지 않는다.
- `pilot 단계에서 문서화된 stop`은 `W6-B0`의 `Branch B/C`와 `§8`의 9~10번 조건 때문에 `W6-B3` 또는 `W6-B5` 이전에 closeout 경로로 내려가는 경우를 모두 포함한다.
- `W6-B6`의 상세 진입 경로와 필수 입력 해석은 `§5.7 W6-B6 entry criteria`를 우선 진실원으로 본다.

## 5. Batch Runbooks — 각 배치의 실제 실행법

### 5.1 W6-B0 — Readiness gate + service queue lock
**목표**
- predecessor evidence와 live `services/` / `foms/services/` tree를 소비해 Wave 6 queue를 authoritative하게 잠근다.
- first pilot(`notifications`)과 second pilot(`file_utils`)를 evidence로 다시 잠근다.

**허용 변경**
- `docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md`

**금지 변경**
- product/runtime code
- spec/archive reference wiring
- future batch run record scaffold

**실행 단계**
1. live `services/*.py`, `services/jobs/*.py`, `foms/services/*.py`, `foms/services/*/__init__.py`를 다시 스캔한다.
2. 2026-04-14 controlling SPEC snapshot 이후 Wave 6가 인용하는 규칙이 달라졌는지 먼저 확인한다. `business_calendar`뿐 아니라 scope/freeze/pilot 규칙 drift가 보이면 code batch 전에 stop하고 snapshot validity를 다시 잠근다.
3. `tests/test_foms_namespace_imports.py`의 shim equivalence baseline을 확인하되, 그 import list를 pilot 순서로 복사하지 않는다.
4. `§1.1`의 row taxonomy와 동일하게 모든 lane을 `mainline-pilot`, `explicit exception`, `already packaged precedent`, `high-risk defer` 중 하나로 다시 판정한다. 단, `§7` 항목 15용 스냅샷에는 queue class 명칭을 그대로 쓰지 말고 `§1.2.2`의 status-register row type(`pilot lane`, `explicit exception`, `already packaged precedent`, `high-risk defer`)으로 번역해 적는다.
5. live non-test code의 `from services.` import debt를 다시 계산하고, `business_calendar` 외 새 lane이 보이면 provisional snapshot을 supersede한다.
6. `notifications` first pilot과 `file_utils` second pilot을 다시 적는다.
7. pilot lock 판정은 아래 체크리스트를 모두 만족해야 true로 적는다.
   - single-leaf 또는 helper-only lane으로 닫힌다.
   - existing focused test가 있거나 최대 1개의 새 contract test로 닫을 수 있다.
   - authoritative target context package가 하나로 잠긴다.
   - worker/bootstrap/schema/persistence structural change가 필요하지 않다.
   - `storage`, `channel_*`, `erp_policy` follow-up refactor, bootstrap/admin-adjacent high-risk lane을 끌고 오지 않는다.
   - `business_calendar`는 controlling spec 승인 게이트 때문에 Wave 6 pilot lock 대상이 아니다.
8. `notifications` lane이 package pilot로 잠기지 못하면 stop reason을 적고, `W6-B1` 최소 shim registry/README -> `W6-B6` status register -> `W6-B7` partial closeout 경로로 넘긴다.
9. `file_utils` second pilot이 helper-only package lane으로 잠기지 못하면 `notifications-only partial path`로 표시하고, `W6-B6` status register + `W6-B7` partial closeout 경로로 넘긴다.

**분기 표**

| 분기 | 조건 | 다음 legal batch |
|------|------|------|
| `Branch A` | `notifications` + `file_utils` 둘 다 잠김 | `W6-B1`부터 mainline 계속 |
| `Branch B` | `notifications`만 잠기고 `file_utils`는 실패 | `W6-B1`~`W6-B3` 수행 후 `W6-B6` status register -> `W6-B7` partial closeout |
| `Branch C` | `notifications`도 잠기지 않음 | `W6-B1` 최소 shim registry/README만 수행 -> `W6-B6` status register -> `W6-B7` partial closeout |

**필수 산출물**
- authoritative service queue
- live import debt table
- first/second pilot order
- 확정된 `Branch A/B/C` 판정
- 해당 branch의 다음 legal batch(`§5.1` 분기 표 문구 그대로)
- `§7` 항목 15를 채우기 위한 initial lane execution-state snapshot
- packaged precedent note
- 선택한 repo sanity baseline과 그 우선순위 근거
- Direction Lock 10문항 yes/no + 한 줄 근거

**검증**
- docs-only consistency check
- live import debt lane 누락이 없는지 수동 확인
- `§6`에 정의된 W6-B0 repo sanity baseline 우선순위를 run record에 명시했는지 확인

### 5.2 W6-B1 — Root shim registry + package-map lock
**목표**
- root `services/`를 shim registry로 잠그고, `foms/services`의 authoritative package map을 고정한다.
- `foms/services/README.md`를 Wave 6 entrypoint로 만든다.

`Branch B`에서는 이 batch가 full `W6-B1`이다. `Branch C`만 아래의 최소 변형을 허용하며, `Branch B`는 이를 사용할 수 없다.

**허용 변경**
- `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md`
- `foms/services/README.md` (없으면 생성 가능)

**금지 변경**
- runtime code
- root `services/` behavior change
- new sibling inventory docs

**실행 단계**
1. root `services/*.py`와 `services/jobs/*`의 각 row에 `queue class`와 `root shim status`를 동시에 적는다.
2. 각 row에 `current owner`, `future canonical target`, `retirement wave`, `removal condition`, `why-not-now`를 적는다.
3. `foms/services/README.md`에 최소한 package map, 읽기 순서, explicit exception, 금지 의존성, pilot order를 적는다.
4. `business_calendar`의 future canonical target을 `foms/services/common/business_calendar.py`로 provisional 고정하고, controlling spec §1.2.16 때문에 Wave 6에서는 explicit exception + approval gate로만 남긴다고 적는다.
5. `notifications`, `files`, `common`, `channel`, `orders`, `measurement`, `jobs`, `platform-adjacent explicit exception`의 package map을 고정한다.

**Branch C 최소 변형**
- `W6-B0`에서 `notifications` first pilot이 잠기지 않은 경우, `W6-B1`은 full package-map refinement batch가 아니라 **최소 shim registry/README batch**로 축소한다.
- 최소 범위는 아래만 포함한다.
  - live root `services/` row 전체에 대한 `queue class` + `root shim status` dual-axis registry
  - packaged precedent / explicit exception / high-risk defer 수준의 coarse package map
  - `foms/services/README.md`의 current queue summary + explicit exception note + `no pilot locked yet` 상태
  - `business_calendar` future target / approval gate
- Branch C 최소 변형에서는 `notifications`/`file_utils` pilot-specific contract table이나 package-shape 확정 문장을 만들지 않는다.

**필수 산출물**
- root shim registry table
- explicit exception rows
- authoritative package map (`Branch C` 최소 변형에서는 coarse authoritative map 허용)
- `foms/services/README.md`
- Direction Lock 10문항 yes/no + 한 줄 근거

**검증**
- docs/README consistency check

### 5.3 W6-B2 — Notifications contract freeze
**목표**
- `notifications` lane의 public/runtime contract를 freeze한다.
- preferred package shape를 고정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md`
- `foms/services/README.md`

**금지 변경**
- runtime code
- API behavior change

**실행 단계**
1. `foms/services/realtime_notifications.py`, `services/realtime_notifications.py`, `apps/api/notifications.py`, `apps/api/erp_orders_drawing.py`, `apps/api/erp_orders_revision.py`, `tests/test_realtime_notifications.py`, `tests/test_foms_namespace_imports.py`를 기준으로 public/runtime contract를 freeze한다.
2. public callable, import path, lazy import 위치, compatibility path를 표로 고정한다.
3. preferred shape를 아래로 고정한다.
   - canonical: `foms/services/notifications/realtime_notifications.py`
   - package marker: `foms/services/notifications/__init__.py`
   - flat compat: `foms/services/realtime_notifications.py`
   - root compat: `services/realtime_notifications.py`
4. live callers를 package path로 올릴지, flat compat path로 유지할지 same-batch 기준으로 명시한다.
5. `foms/services/README.md`의 notifications contract note를 최신화한다.

**필수 산출물**
- public callable/import contract table
- preferred package shape
- caller matrix
- focused verification plan
- Direction Lock 10문항 yes/no + 한 줄 근거

**검증**
- docs-only consistency check

### 5.4 W6-B3 — Notifications package pilot canonicalization
**목표**
- `notifications` lane을 context package 선례로 만든다.
- flat/root compatibility surface와 focused tests를 유지한다.

**허용 변경**
- `foms/services/notifications/__init__.py`
- `foms/services/notifications/realtime_notifications.py`
- `foms/services/realtime_notifications.py`
- `services/realtime_notifications.py`
- `apps/api/notifications.py`
- `apps/api/erp_orders_drawing.py`
- `apps/api/erp_orders_revision.py`
- `tests/test_realtime_notifications.py`
- `tests/test_foms_namespace_imports.py`
- `foms/services/README.md`
- `docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md`

**금지 변경**
- route path / response shape 변경
- notification semantics 변경
- new generic package 추가
- `apps/api/*.py` 수정 시 import wiring/shim alignment 외의 HTTP contract 변경(status code, response payload, decorator order, request parsing) 금지

**실행 단계**
1. `W6-B2` contract table을 기준으로 canonical package를 만든다.
2. 구현은 `foms/services/notifications/realtime_notifications.py`로 이동하고, flat/root path는 compatibility shim으로 유지한다.
3. 가능하면 live callers를 package path로 정렬하되, public behavior는 유지한다.
4. `tests/test_realtime_notifications.py`와 `tests/test_foms_namespace_imports.py`를 package path 선례 기준으로 보강한다.
5. `foms/services/README.md`의 notifications lane을 최신화한다.
6. `W6-B2` contract table에서 export 하나를 골라 import-smoke template의 placeholder를 실제 심볼명으로 치환한 concrete 명령을 current run record에 남긴다. 계획서의 placeholder line은 템플릿일 뿐 최종 증거가 아니다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/test_realtime_notifications.py tests/test_foms_namespace_imports.py -q`
- touched file diagnostics/lint (`ReadLints` 또는 동등한 진단 확인)
- `python -c "import services.realtime_notifications as legacy; import foms.services.realtime_notifications as flat; from foms.services.notifications import realtime_notifications as pkg; export_name = '<W6-B2_CONTRACT_EXPORT>'; assert getattr(legacy, export_name) is getattr(pkg, export_name); assert getattr(flat, export_name) is getattr(pkg, export_name); print('W6_NOTIFICATIONS_NS_OK')"`  # replace placeholder with the frozen export name from the W6-B2 contract table / run record
- batch가 revert/defer로 끝나면 closeout 전에 fresh `APP_OK` + `verify_result`와 agreed import smoke(또는 불가 사유)를 같은 run record에 남긴다.

### 5.5 W6-B4 — Files helper contract freeze
**목표**
- `file_utils` lane의 public/runtime contract를 freeze한다.
- `files` helper-only pilot shape를 고정한다.

**허용 변경**
- `docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md`
- `foms/services/README.md`

**금지 변경**
- runtime code
- spec/archive reference wiring

**실행 단계**
1. `foms/services/file_utils.py`, `services/file_utils.py`, `apps/excel_import.py`, `tests/test_file_utils.py`, `tests/test_foms_namespace_imports.py`를 기준으로 public/runtime contract를 freeze한다.
2. preferred shape를 아래로 고정한다.
   - canonical: `foms/services/files/file_utils.py`
   - package marker: `foms/services/files/__init__.py`
   - flat compat: `foms/services/file_utils.py`
   - root compat: `services/file_utils.py`
3. `storage`는 같은 `files` context라도 high-risk lane이므로 이번 pilot에 포함하지 않는다고 명시한다.
4. `foms/services/README.md`의 files helper section을 최신화한다.

**필수 산출물**
- public callable/import contract table
- preferred package shape
- caller matrix
- focused verification plan
- Direction Lock 10문항 yes/no + 한 줄 근거

**검증**
- docs-only consistency check

### 5.6 W6-B5 — Files helper package pilot canonicalization
**목표**
- `file_utils` lane 하나만 structure-only로 canonical package에 수렴시킨다.

**허용 변경**
- `foms/services/files/__init__.py`
- `foms/services/files/file_utils.py`
- `foms/services/file_utils.py`
- `services/file_utils.py`
- `apps/excel_import.py`
- `tests/test_file_utils.py`
- `tests/test_foms_namespace_imports.py`
- `foms/services/README.md`
- `docs/plans/2026-04-14-wave6-batch5-files-helper-pilot-run-record.md`

**금지 변경**
- `business_calendar` lane code touch
- `storage`, `channel_*`, `erp_policy` 추가 refactor, bootstrap lane 변경
- route/page/front-end behavior change
- `apps/excel_import.py` 수정 시 import wiring/shim alignment 외의 callable contract/return shape 변경 금지

**실행 단계**
1. `file_utils` canonical package를 만든다.
2. 구현은 package target으로 이동하고, flat/root compatibility surface는 same-batch shim으로 유지한다.
3. helper-only lane까지만 닫고 `storage`를 섞지 않는다.
4. `tests/test_file_utils.py`와 `tests/test_foms_namespace_imports.py`는 import-surface lock 범위까지만 보강한다. suite-wide rationalization은 Wave 7로 넘긴다.
5. focused tests를 보강하고 `foms/services/README.md`를 최신화한다.
6. `W6-B4` contract table에서 export 하나를 골라 import-smoke template의 placeholder를 실제 심볼명으로 치환한 concrete 명령을 current run record에 남긴다. 계획서의 placeholder line은 템플릿일 뿐 최종 증거가 아니다.

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/test_file_utils.py tests/test_foms_namespace_imports.py -q`
- touched file diagnostics/lint (`ReadLints` 또는 동등한 진단 확인)
- `python -c "import services.file_utils as legacy; import foms.services.file_utils as flat; from foms.services.files import file_utils as pkg; export_name = '<W6-B4_CONTRACT_EXPORT>'; assert getattr(legacy, export_name) is getattr(pkg, export_name); assert getattr(flat, export_name) is getattr(pkg, export_name); print('W6_FILE_UTILS_NS_OK')"`  # replace placeholder with the frozen export name from the W6-B4 contract table / run record
- batch가 revert/defer로 끝나면 closeout 전에 fresh `APP_OK` + `verify_result`와 agreed import smoke(또는 불가 사유)를 같은 run record에 남긴다.

### 5.7 W6-B6 — Lane status register
**목표**
- Wave 6 mainline에서 다룬 lane과 다루지 않은 lane을 authoritative status register로 잠근다.
- Wave 7 / Wave 8 handoff 경계를 만든다.

**W6-B6 entry criteria**
- `Branch A`: `W6-B5` 완료 후 진입
- `Branch B`: `W6-B3` 완료 후 진입
- `Branch C`: 최소 `W6-B1` 완료 후 진입
- `late-file-utils-stop`: failed/partial `W6-B4` 기록을 들고 진입
- `§8.13 docs-freeze stop`: failed/partial `W6-B2` 또는 `W6-B4` 기록을 들고 진입
- 어떤 경로든 `W6-B0` and `W6-B1` both completed는 공통 전제다.

**허용 변경**
- `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md`
- `foms/services/README.md`

**금지 변경**
- runtime code
- new pilot 시작

**실행 단계**
1. `W6-B0`의 authoritative queue/import-debt lock과 `W6-B1`의 shim registry/package map/README를 먼저 입력으로 소비한다. `W6-B6`은 이 둘을 건너뛴 독립 판정 문서가 아니다.
   - 현재 경로에서 이미 완료된 contract/code batch run record(`W6-B2`~`W6-B5` 중 해당하는 것)는 마지막 completed batch까지 모두 함께 소비한다.
   - `§8.13`으로 `W6-B2` 또는 `W6-B4`가 partial/failed 종료된 경우, 그 partial/failed run record도 필수 입력으로 함께 소비한다.
   - `W6-B3` 또는 `W6-B5`가 partial/failed 종료된 경우에도 그 partial/failed run record와 clean-gate evidence(또는 불가 사유)를 필수 입력으로 함께 소비한다.
2. status register를 아래 두 축으로 잠근다.
   - `row type`: `pilot lane`, `already packaged precedent`, `explicit exception`, `high-risk defer`
   - `execution state`: `completed`, `not started`, `partial`
3. `notifications`, `file_utils`, `jobs`, `erp_policy_internal`, `foms/services/erp_policy.py` public wrapper(필요 시 해당 root shim status 포함)는 row type과 execution state를 함께 적는다.
   - 예: `notifications` = `pilot lane/completed` 또는 Branch C면 `pilot lane/not started`
   - 예: `jobs` = `already packaged precedent/completed`
   - 예: `foms/services/erp_policy.py` public wrapper = `already packaged precedent/completed`
4. `business_calendar`는 controlling spec §1.2.16 때문에 `explicit exception` row로 적고, `future canonical target`, `approval gate`, `required prep`을 남긴다.
5. `storage`, `channel_*`, `erp_policy` 추가 refactor, orders cluster, measurement cluster, bootstrap/admin-adjacent helpers는 `high-risk defer` row로 적는다. 여기서 `erp_policy` defer는 public wrapper 유지와 별개인 후속/추가 refactor만 뜻한다.
6. 각 row에 `why not now`, `required prep`, `suggested restart batch`, `future canonical target`, `root shim status`, `Wave 7/Wave 8 owner`, `retirement wave`를 남긴다.
7. shim 제거/bridge retirement 성격의 row는 `retirement wave`를 기본적으로 `Wave 8` 또는 그 이후로 적는다. `Wave 7`은 test/contract rationalization 용도이므로 bridge removal owner로 쓰지 않는다.
8. Branch C 같은 조기 종료 분기에서도 `W6-B6`은 최소 status register를 반드시 남긴다.
9. `foms/services/README.md`에 status register summary를 반영한다.
10. `erp_policy_public_wrapper`와 `erp_policy_followup_refactor`는 반드시 서로 다른 row id/label로 적는다.

**검증**
- docs-only closeout
- status register completeness
- `foms/services/README.md` status register summary 반영 여부 확인
- code batch revert/defer 이후 진입한 경로라면, clean-gate evidence(fresh `APP_OK` + `verify_result` + agreed import smoke 또는 불가 사유)가 입력 체인에 실제로 포함됐는지 확인
- Direction Lock 10문항 yes/no + 한 줄 근거

### 5.8 W6-B7 — Closeout + Wave 7/8 handoff
**목표**
- Wave 6 완료 범위와 미완 범위를 명확히 고정한다.
- Wave 7(test rationalization), Wave 8(bridge retirement) handoff를 남긴다.

**허용 변경**
- `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md`
- `foms/services/README.md`
- controlling spec의 참고 자료 섹션 보강
- `docs/ARCHIVE_INDEX.md`

**금지 변경**
- runtime code
- 새로운 decomposition batch 시작

**실행 단계**
1. full 또는 partial closeout 상태를 판정한다.
2. `W6-B6`이 존재하면 그 status register를 인용하고, 없으면 `W6-B7` 안에 동등한 merged status-register section을 만들어 `pilot lane / already packaged precedent / explicit exception / high-risk defer`와 각 execution state를 분리해 적는다. 이 merged section도 closeout에 필요한 status-register evidence로 간주한다.
   - dedicated `W6-B6` file이 없으면 `W6-B7` header 또는 section 서두에 `acts as W6-B6 surrogate`라고 명시하고, downstream reader가 batch6 부재를 실패로 오해하지 않게 cross-link를 남긴다.
3. Wave 7로 넘길 test debt와 Wave 8로 넘길 shim retirement debt를 표로 남긴다.
4. `foms/services/README.md`가 current truth를 반영하는지 검증하고, 필요하면 여기서 최종 sync한다.
5. controlling spec reference와 archive index를 보강한다.
6. `W6-B7` closeout에는 predecessor wording 정합 메모를 반드시 남긴다. conflicting broad wording을 발견했으면 "this plan supersedes older Wave 3 boundary wording" errata note를 적고, 발견하지 못했으면 `no conflicting predecessor wording found in consumed evidence`라고 명시한다. Wave 6에서 그 predecessor 문서를 재편집하는 것은 필수가 아니다.

**검증**
- docs-only closeout
- handoff completeness
- code-batch revert/defer 경로에서 닫는 경우, clean-gate evidence가 input chain에 실제로 포함됐는지 다시 확인
- Direction Lock 10문항 yes/no + 한 줄 근거

## 6. Verification Matrix — 배치별 필수 검증

| Batch | APP_OK | verify_result | focused automated | import smoke | lint/diagnostics | README/update | Direction Lock |
|------|------|------|------|------|------|------|------|
| W6-B0 | N/A | N/A | docs-only | N/A | N/A | N/A | 필수 |
| W6-B1 | N/A | N/A | docs-only | N/A | N/A | 필수 | 필수 |
| W6-B2 | N/A | N/A | docs-only | N/A | N/A | 필수 | 필수 |
| W6-B3 | 필수 | 필수 | `test_realtime_notifications` + `test_foms_namespace_imports` | 필수 | 필수 | 필수 | 필수 |
| W6-B4 | N/A | N/A | docs-only | N/A | N/A | 필수 | 필수 |
| W6-B5 | 필수 | 필수 | `test_file_utils` + `test_foms_namespace_imports` | 필수 | 필수 | 필수 | 필수 |
| W6-B6 | N/A | N/A | docs-only | N/A | N/A | 필수 | 필수 |
| W6-B7 | N/A | N/A | docs-only | N/A | N/A | 필수(README 검증/최종 sync + spec/archive update) | 필수 |

추가 규칙:

- Branch B/C에서 스킵된 batch 행은 `not executed by path`로 간주한다. 빈 run record를 만들지 않는다.
- Branch B/C에서 스킵된 batch 행은 개별 batch Verification 절을 만들지 않는다. 해당 부재 사유는 `W6-B0`, `W6-B6`, `W6-B7` stop/closeout evidence에서 한 번만 설명하면 된다.
- `focused automated`는 라벨이지 자동으로 해석되는 명령 이름이 아니다. 모든 code batch run record는 실제로 실행할 `pytest`/`python` 명령 또는 대상 파일 집합을 명시해야 한다.
- `§1.3`의 freeze axis는 아래 stop clause로 해석한다: route/blueprint/API response shape drift는 `§8.1`, worker/bootstrap/chat/socketio binding drift는 `§8.2`, template/static/front-end island drift는 `§8.16`, frozen root infra file drift는 `§8.14`, controlling SPEC snapshot conflict와 binding-doc scope conflict는 `§8.15`.
- docs-only batch의 `docs-only consistency check`는 최소 아래 네 가지를 뜻한다.
  - 현재 batch run record의 필수 표/섹션이 모두 존재한다.
  - `foms/services/README.md`, queue/shim/status 표, 그리고 직전 authoritative run record 사이에 현재 batch가 잠그는 row의 `canonical target`/`root shim status`/`execution state` 모순이 없다.
  - 현재 batch가 인용한 predecessor evidence와 latest authoritative run record가 실제로 입력에 포함돼 있다.
  - 현재 경로에서 사용할 repo sanity baseline(직전 성공한 `APP_OK`/`verify_result` 또는 accepted predecessor verification evidence)을 run record에 명시했다.
- `W6-B0`의 repo sanity baseline 우선순위는 다음과 같다: (1) Wave 5 handoff evidence에 적힌 마지막 accepted verification, (2) 동등한 predecessor closeout evidence의 마지막 accepted verification, (3) 둘 다 없으면 현재 브랜치에서 fresh `APP_OK` + `verify_result` 1회를 실행해 baseline으로 채택.
- Wave 5 equivalent evidence가 reject되면 (1)은 사용 불가다. 그 경우 (2)가 있으면 (2)를 채택하고, (2)도 없으면 (3)을 필수로 실행해야만 `W6-B0`를 완료할 수 있다.
- (1)과 (2)가 서로 다른 커밋/환경/명령 세트를 가리켜 충돌하면 fresh (3)을 항상 실행해 새 baseline으로 덮어쓴다. 더 최근/더 구체적인 evidence 비교는 참고 메모로만 남기고 tie-break 자체를 대체하지 않는다.
- `tests/test_foms_namespace_imports.py` 수정은 Wave 6에서는 import-surface lock 범위까지만 허용한다. suite-wide rationalization은 Wave 7로 넘긴다.
- `tests/test_foms_namespace_imports.py`의 구조적 재설계 또는 non-import-surface 수정은 Wave 6가 아니라 Wave 7 소관이다.
- touched file diagnostics/lint는 모든 code batch에 필수다.
- docs-only batch는 새 runtime smoke를 강제하지 않아도 되지만, current path에서 마지막으로 유효한 repo sanity baseline을 반드시 인용한다. `W6-B7` closeout은 최소 하나의 accepted repo sanity baseline 없이 완료로 표시할 수 없다.
- `W6-B6`, `W6-B7`이 code-batch revert/defer 경로에서 열렸다면, matrix상 docs-only라도 clean-gate evidence(fresh `APP_OK` + `verify_result` + agreed import smoke 또는 불가 사유)를 입력 체인에서 추가로 확인해야 한다.
- code batch에서 module path/shim이 바뀌면 최종 `APP_OK`, `verify_result`, import smoke는 fresh Python process 기준으로 다시 실행한다. 이미 떠 있던 dev server/worker/job runner를 smoke에 사용했다면 final verification 전에 재시작하고, 그 사실을 run record에 남긴다.
- stale import cache나 `__pycache__`에 기대는 검증은 증거로 인정하지 않는다. fresh process 재검증 없이 "로컬에서는 이미 import돼 있었음" 같은 상태는 성공 근거가 아니다.

## 7. Run Record Minimum Contract — 각 batch 기록 최소 항목

모든 run record는 최소 아래 항목을 가져야 한다.

1. `Scope lock`
2. `Inputs consumed`
3. `context/package key`
4. `Contract table`
5. `FR19 / NS-package-first decision`
6. `Changes made`
7. `Verification`
8. `Direction Lock answers`
9. `product / wrapper / test delta`
10. `canonical target`
11. `flat compat path`
12. `root shim status`
13. `retirement wave / removal condition`
14. `README update 여부`
15. `row type / execution state`
16. `drift / stop / defer decision`
17. `lint/diagnostics evidence`

추가 규칙:

- `W6-B1`은 root shim registry table과 explicit exception row를 반드시 포함한다.
- `W6-B0`에서 `Contract table`은 queue/import-debt lock table을 뜻한다. `root shim status`의 authoritative dual-axis 잠금은 `W6-B1`에서 수행한다.
- `W6-B0`에서 항목 15(`row type / execution state`)는 `initial lane execution-state snapshot`으로 채운다. 각 lane마다 `§1.2.2`의 row type + execution state 쌍을 함께 적으며, 기본값은 `already packaged precedent/completed`, `pilot lane/not started`, `explicit exception/not started`, `high-risk defer/not started`다. `Branch B/C`가 W6-B0에서 확정되면 해당 partial path를 한 줄 주석으로 덧붙인다.
- `W6-B0`, `W6-B1`, `W6-B6`, `W6-B7`에서 `Contract table`은 lane public/runtime contract 표가 아니라 `queue/shim/status lock table`을 뜻해도 된다.
- docs-only batch의 항목 7(`Verification`)은 `§6`의 repo sanity baseline 선택 결과와 채택 근거를 반드시 포함한다. `W6-B0`/`W6-B1`/`W6-B6`/`W6-B7`은 baseline을 인용만 하는지, fresh 실행으로 갱신했는지까지 적는다.
- `W6-B3`, `W6-B5`는 package import smoke 결과를 반드시 남긴다.
- `W6-B3`, `W6-B5`는 lint/diagnostics 도구명, 대상 경로, 결과를 반드시 남긴다.
- `W6-B3`, `W6-B5`는 검증 시도 횟수, fix-forward/revert 경로, `§8` 12번 stop 조건 해당 여부를 반드시 남긴다.
- `Attempt N`은 code/docs를 다시 수정한 뒤 새로운 verification cycle을 돌리는 순간마다 1씩 증가한다. 메모만 보강하고 검증을 다시 돌리지 않은 경우는 새 Attempt로 세지 않는다.
- 따라서 code batch의 `최대 두 번 fix-forward`는 일반적으로 `Attempt 1` 이후 `Attempt 2`, `Attempt 3`까지만 허용된다는 뜻이다. 그 뒤에도 닫히지 않으면 `§8` 12번으로 stop/defer한다.
- `revert + documented defer`가 선택된 순간 그 batch는 terminal stop이다. Attempt counter를 초기화한 채 같은 batch를 계속 진행할 수 없고, 이후 작업은 `W6-B6`/`W6-B7` 또는 후속 wave/restart batch에서 새로 판단한다.
- code batch가 `revert + documented defer` 또는 `§8` 12번으로 끝나면 `W6-B6`/`W6-B7`을 열기 전에 fresh `APP_OK` + `verify_result`와 agreed import smoke 상태를 다시 확보하거나, 왜 확보할 수 없는지 stop evidence에 적어야 한다.
- 위 문장은 `§3` mainline/closeout 전환 규칙과 `§5.4`/`§5.6` code batch 종료 판단에도 동일하게 적용된다. post-revert closeout으로 넘어갈 때는 이 clean gate를 생략할 수 없다.
- revert가 concrete export freeze 전에 발생했다면 `agreed import smoke`는 placeholder export smoke가 아니라 `tests/test_foms_namespace_imports.py`와 latest accepted predecessor import-surface baseline으로 되돌린다.
- clean revert 자체가 불가능하거나 partial revert 상태에 머무르면, 추가 fix-forward 없이 즉시 stop evidence에 `revert incomplete`를 남기고 `W6-B6`/`W6-B7`에서는 그 사실과 clean-gate 불가 사유를 함께 인용한다.
- docs-only batch는 항목 17을 `not applicable` + 사유로 채워도 된다.
- docs-only batch는 항목 9(`product / wrapper / test delta`)를 `N/A (no code touch)` + 한 줄 사유로 채워도 된다.
- `W6-B0`에서는 항목 10~13을 비워 두지 않는다. queue/import-debt table과 정합한 provisional 값으로 채우고, authoritative dual-axis lock은 `W6-B1`에서 수행된다고 명시한다.
- `W6-B0`에서 항목 5(`FR19 / NS-package-first decision`)는 "이번 batch는 신규 canonical package/leaf 추가 없이 queue/import-debt truth만 재잠금했다"는 점을 기준으로, `delete -> merge -> extend -> add` 검토 결과 또는 `no new package in B0` 근거를 한 줄로 남기면 된다.
- docs-only batch에서 항목 10~13(`canonical target`, `flat compat path`, `root shim status`, `retirement wave / removal condition`)이 이번 batch에서 직접 변하지 않으면 `unchanged from <latest authoritative run record>` 형태로 채울 수 있다.
- `W6-B6`은 각 row의 `row type`(`pilot lane`, `already packaged precedent`, `explicit exception`, `high-risk defer`)과 `execution state`를 반드시 함께 명시한다.
- 각 batch ID는 `§4.1`의 단일 run record 경로 하나만 authoritative file로 가진다. 같은 batch 재시도는 sibling run record를 새로 만들지 않고 같은 파일 안에 `Attempt N` section을 추가하는 방식으로 남긴다.
- 같은 run record 파일 안에서 가장 마지막 `completed` 또는 `partial closeout` attempt section이 authoritative current state다. 이전 attempt section은 history로 유지하되, verification/lint evidence와 stop/defer 판단은 latest authoritative section 기준으로 읽는다.

## 8. Stop Conditions — 중단 조건

다음 중 하나라도 발생하면 해당 batch의 **mainline progression**을 즉시 중단하고 closeout 경로로 전환한다. 단, `W6-B0`에서 9~10번이 발생한 경우에도 `§5.1` Branch 표가 우선이며, `Branch C`는 `W6-B1` 최소 shim-registry 경로를 끝낸 뒤에만 `W6-B6`/`W6-B7`로 내려간다.

해석 고정:

- `§8.9`는 `W6-B0`에서 notifications first pilot을 잠그지 못해 `Branch C`로 떨어지는 경우를 뜻한다.
- `§8.10`은 두 경우를 모두 포함한다: `W6-B0`에서 second pilot을 잠그지 못해 `Branch B`가 되는 경우, 또는 `W6-B4`에서 file-utils contract freeze를 끝내지 못해 `W6-B3` 이후 stop-triggered partial closeout으로 내려가는 경우. 후자는 `late file-utils stop`이며, `W6-B0` 시점의 `Branch B`와 같은 사건으로 합치지 않는다.
- `late file-utils stop`은 branch label이 아니라 stop label이다. 관련 run record와 closeout에서는 `Branch B`로 부르지 않고 `late-file-utils-stop`으로 적는다.

1. API canonicalization 또는 page migration이 먼저 필요해짐
2. DB schema, persistence lifecycle, worker/bootstrap registration, chat/socketio binding 변경이 필요해짐
3. public import path를 same-batch shim 없이 깨야 함
4. root `services/` row에 canonical target / retirement wave / removal condition을 붙일 수 없음
5. touched lane의 target context package가 두 개 이상으로 갈려 `W6-B1` 또는 해당 lane의 pre-code contract batch(`W6-B2`/`W6-B4`)에서 authoritative target을 lock하지 못함
6. 한 batch 안에서 두 context package 또는 두 risk lane을 동시에 건드리게 됨
7. `business_calendar` 축이 controlling spec §1.2.16의 승인 게이트 없이 code pilot로 승격돼야 한다는 결론이 나옴
8. `storage`, `channel_*`, `erp_policy` 추가 refactor, bootstrap lane을 low-risk pilot에 섞어야만 한다는 결론이 나옴
9. `W6-B0`에서 `notifications` first pilot을 lock하지 못함
10. `W6-B0`에서 `file_utils` second pilot helper-only target을 lock하지 못함
11. 어떤 batch라도 `foms/platform/blueprints.py` 또는 `§1.3`에서 닫아 둔 root bootstrap 파일(`app.py`, `run.py`, `start.sh`, `Procfile`) 수정이 필요해짐
12. code batch verification이 같은 batch 안에서 최대 두 번의 fix-forward 시도 또는 한 번의 revert + documented defer로도 닫히지 않음
13. docs-only contract freeze batch(`W6-B2`, `W6-B4`)가 current lane contract table을 끝내지 못함. run record label은 `W6-B2`면 `notifications-docs-freeze-stop`, `W6-B4`면 `late-file-utils-stop`으로 통일한다.
14. 어떤 batch라도 `§1.3`에서 frozen root file로 잠근 `Dockerfile`, `alembic.ini`, `railway*.toml` 수정이 필요해짐
15. controlling SPEC snapshot validity가 깨졌거나 `§1.4.10`/`§1.4.11` 수준의 scope conflict가 새로 확인돼, 현재 queue/branch 판단을 그대로 유지할 수 없음. 이 경우 run record는 `spec-scope-conflict`인지 `binding-doc-scope-conflict`인지 trigger leg를 함께 적는다.
16. page/template/static physical move 또는 front-end island decomposition/rebaseline이 필요해짐
17. packaging reopen(`src/foms`), Wave 7 수준의 suite-wide test redesign, 또는 Wave 8 수준의 mass shim retirement가 필요해짐

## 9. Prompt Contract — Wave 6 실행 첫 프롬프트 규약

### 9.1 W6-B0 Prompt Contract
future LLM이 Wave 6를 실제로 시작할 때 첫 프롬프트는 최소 아래 요구를 만족해야 한다.

1. 입력 문서:
   - `@docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`
   - `@docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
   - `@docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` 또는 equivalent Wave 3 closeout evidence
   - `@docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md` 또는 equivalent Wave 4 closeout evidence
   - `@docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
   - Wave 5 closeout file 또는 `current execution state memo` / equivalent evidence bundle
   - `@docs/plans/2026-04-10-step3-batch46-storage-run-record.md`
   - `@docs/plans/2026-04-07-step3-batch7-erp-display-run-record.md`
   - `@tests/test_foms_namespace_imports.py`
   - `§1.4.11`에 따라 scope를 제한할 수 있는 binding harness/policy/decision 문서가 추가로 보이면 그 exact path도 함께 입력에 포함
2. batch order를 임의 변경하지 않는다고 선언한다.
3. `W6-B0`에서 service queue와 import debt를 live evidence로 다시 잠그겠다고 명시한다.
4. root `services/`는 shim 또는 explicit exception만 남기겠다고 명시한다.
5. future batch run record를 미리 만들지 않겠다고 명시한다.
6. Wave 4/5 closeout file이 없으면 `W6-B0` run record 안에서 equivalent evidence를 명시적으로 accept/reject 하겠다고 적는다.
7. Wave 5 closeout file 대신 `current execution state memo`를 쓰면, 최소 계약(완료 batch, in-progress/last-attempt batch, blockers, defer lane, verification 상태, handoff note)을 함께 점검하겠다고 적는다.
8. Wave 5 `current execution state memo`를 쓸 때는 작성 시각과 커버하는 batch 범위를 함께 검증하겠다고 적는다.
9. resume/handoff 세션이면 적용되는 `§9.3` restart row를 함께 읽고, live tree snapshot 재수집 + branch/pilot revalidation 절차를 따르겠다고 명시한다.

### 9.2 W6-B0 Expected Output
`W6-B0` 결과에는 최소 아래가 있어야 한다.

- authoritative service queue
- live import debt table
- first/second pilot order
- 확정된 `Branch A/B/C` 판정
- 해당 branch의 다음 legal batch
- initial lane execution-state snapshot(`§7` 항목 15용)
- packaged precedent note
- 선택한 repo sanity baseline과 그 우선순위 근거
- Direction Lock 10문항 yes/no + 한 줄 근거

아래 bullet은 핵심 산출물 요약일 뿐이다. 완결된 `W6-B0` run record는 여전히 `§7 Run Record Minimum Contract` 17항 전체를 채워야 하며, `W6-B0`에서는 같은 절의 docs-only/B0 전용 정의(`Contract table = queue/import-debt lock`, item 15 = initial lane execution-state snapshot, item 17 = `not applicable` + 사유)를 따른다.

### 9.3 Batch Restart Minimum Input Set
세션이 batch 중간에 끊기거나 다른 LLM이 이어받을 때는 최소 아래 입력을 다시 준다.

| Batch range | 최소 입력 |
|------|------|
| `W6-B0` | 본 계획서 + predecessor handoff evidence + live `services/` / `foms/services/` tree snapshot + `tests/test_foms_namespace_imports.py` ; docs batch 재시도면 직전 partial run record 초안 + 수동 스캔 메모/로그 + Branch A/B/C 판정 상태 + pilot lock checklist true/false 포함 |
| `W6-B1` | 본 계획서 + `W6-B0` run record + live `services/` / `foms/services/` tree snapshot + `tests/test_foms_namespace_imports.py` ; 동일 batch 재시도면 직전 partial/failed run record + README/shim-registry diff 요약 포함 |
| `W6-B2`~`W6-B3` | 본 계획서 + `W6-B1` run record + notifications lane live files/tests ; Branch C에서는 해당 단계가 없으므로 `W6-B6` 입력 규칙을 따른다 ; `W6-B2` 완료/B3 미시작이면 `W6-B2` run record + contract freeze 산출물 + B3 scope files를 포함한다 ; 동일 batch 재시도면 직전 partial/failed run record + verification/lint 로그 + scope 내 변경 파일 목록 포함 |
| `W6-B4` | 본 계획서 + `W6-B1` run record + `W6-B2`/`W6-B3` run records + file-utils lane live files/tests ; mainline/Branch A 경로에서만 사용 ; Branch B/C에서는 해당 단계가 없으므로 이 행 대신 `W6-B6` 입력 규칙을 따른다 ; 동일 batch 재시도면 직전 partial/failed run record + 수동 consistency 체크 로그 포함 |
| `W6-B5` | 본 계획서 + `W6-B1` run record + `W6-B3`/`W6-B4` run records + file-utils lane live files/tests ; mainline/Branch A 경로에서만 사용 ; 동일 batch 재시도면 직전 partial/failed run record + verification/lint 로그 + scope 내 변경 파일 목록 포함 |
| `W6-B6` | 본 계획서 + `W6-B0`/`W6-B1` run records + 마지막 completed code batch까지의 관련 run records + `foms/services/README.md` ; completed code batch가 전혀 없으면 `W6-B0`/`W6-B1` run records + stop evidence + `foms/services/README.md` ; `§8.13`처럼 docs-only freeze batch가 partial/failed로 멈췄다면 그 partial/failed `W6-B2` 또는 `W6-B4` run record도 필수 입력으로 포함한다 ; `W6-B3`/`W6-B5`가 partial/failed로 멈췄다면 해당 run record와 clean-gate evidence(또는 불가 사유)도 필수 입력으로 포함한다 ; 동일 batch 재시도면 직전 partial/failed run record + status-register draft diff 요약 포함 |
| `W6-B7` | 본 계획서 + `W6-B0`부터 마지막 completed batch까지의 run records + attempted-but-failed code/docs batch run records + all defer/stop evidence + status-register evidence(`W6-B6` file 또는 `§5.8` merged section을 재구성할 수 있는 근거) ; 동일 batch 재시도면 직전 partial/failed closeout draft + spec/archive sync 메모 포함 |

추가 규칙:

- `W6-B2`~`W6-B3` 행의 적용 순서는 `Branch C 여부 -> W6-B2 완료/B3 미시작 여부 -> 동일 batch 재시도 여부` 순서로 읽는다. 앞 조건이 참이면 뒤 조건보다 우선한다.
- 여기서 `Branch C 여부`는 `W6-B2`/`W6-B3`가 한 번도 시작되지 않은 경우에만 적용한다. `W6-B2` 또는 `W6-B3` run record가 이미 존재하면 그것은 Branch C가 아니라 same-batch retry/partial recovery 경로로 읽는다.
- `live tree snapshot`은 재시작 직전에 다시 수집한 경로 목록을 뜻한다. 최소 범위는 `services/*.py`, `services/jobs/*.py`, `foms/services/**/*.py`, `foms/services/*/__init__.py`, 그리고 current batch 관련 test/docs 파일이다.
- 가능하면 snapshot에는 현재 git HEAD(또는 동등한 revision marker)도 함께 남긴다. git 정보를 쓸 수 없으면 그 이유를 같은 restart prompt/run record에 적는다.
- mid-wave resume에서는 snapshot을 다시 수집한 뒤 현재 repo 상태가 기존 `Branch A/B/C` 또는 pilot lock 결론과 모순되지 않는지 먼저 확인한다. 모순이 있으면 해당 batch를 계속하지 말고 `W6-B0`로 올라가 branch/pilot lock을 다시 판정한다.
- resumed code batch(`W6-B3`/`W6-B5`)는 추가 수정 전에 fresh process 기준의 repo sanity baseline을 다시 확인하거나, 방금 재수집한 snapshot과 함께 마지막 accepted baseline이 여전히 유효하다고 명시적으로 재확인해야 한다.
- 각 재시작 프롬프트는 current batch 이전 배치가 정상 종료됐는지 먼저 확인한다고 명시한다.
- current batch 범위 밖 파일을 열어야 하면 이유를 같은 프롬프트에 적는다.
- stop-triggered closeout이면 `partial closeout`이라고 명시한다.

## 10. Completion Criteria — Wave 6 완료 판단

Wave 6는 아래 둘 중 하나일 때만 닫는다.

1. `Branch A` 경로에서 `W6-B0`~`W6-B7`가 순서대로 완료되고, `W6-B7` closeout이 끝난 경우
2. `§5.1 Branch B/C`의 계획된 skip 경로 또는 중간 batch(code/docs gate 포함)의 `§8 Stop Conditions` stop 경로로 내려가 `W6-B7` partial closeout이 끝난 경우

적용 규칙:

- `Branch A`만 `§10.1 Full closeout`을 적용한다.
- `Branch B`, `Branch C`, 그리고 `§8` stop-triggered path는 모두 정상적인 `partial closeout` 경로이며 `§10.2`를 적용한다.
- `Branch B/C`는 "실패해서 멈춤"이 아니라 `W6-B0`에서 문서화된 계획된 skip path다. 다만 closeout 형식은 full이 아니라 partial로 고정한다.

### 10.1 Full closeout 추가 기준
아래는 `W6-B0`~`W6-B7`를 모두 완료한 **full closeout**에만 적용한다.

- `notifications` package pilot run record가 존재해야 한다.
- `file_utils` files-helper pilot run record가 존재해야 한다.
- `foms/services/README.md`와 root shim registry가 최신이어야 한다.
- lane status register가 존재해야 한다.
- spec reference와 archive index가 Wave 6 plan/closeout을 가리켜야 한다.

### 10.2 Partial / planned-skip / stop-triggered closeout 추가 기준
아래는 `§5.1 Branch B/C`의 planned skip path 또는 중간 batch(code/docs gate 포함) stop 이후 `W6-B7`로 닫는 **partial closeout**에 적용한다.

- stop 시점까지 완료된 batch run record만 존재하면 된다.
- 미실행 pilot과 defer lane에는 `not started` 또는 `partial` 상태를 남겨야 한다.
- status-register 증거는 `W6-B6` 전용 run record 또는 `§5.8`의 `W6-B7` merged status-register section 둘 중 하나면 충분하다.
- explicit exception과 high-risk lane에는 `why-not-now`, `required prep`, `suggested restart batch`가 남아야 한다.
- `foms/services/README.md`가 current truth를 반영해야 한다.

## 11. Suggested Review Loop — 감리 반복 규약

이 계획은 아래 반복을 전제로 한다.

1. 초안 작성
2. `code-reviewer` 감리
3. `evolution-architect` 감리
4. `grand-develop-master` 감리
5. HIGH/MEDIUM finding 제거
6. finding이 사라질 때까지 반복

최종 기준:

- 세 감리 모두 HIGH/MEDIUM 없음
- spec drift 없음
- first/second pilot과 explicit exception/status 경계가 동시에 선명함
