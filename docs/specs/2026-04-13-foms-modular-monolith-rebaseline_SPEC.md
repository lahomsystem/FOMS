# FOMS Modular Monolith Rebaseline Spec
> 작성일: 2026-04-13 | 상태: 🟢 승인됨 (2026-04-13 사용자 승인 반영)
> 상위 거버넌스: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 관련 거버넌스: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
FOMS 저장소 전체를 앞으로 어떤 기준으로 정리할지에 대한 **새 상위 구조 기준선**을 정의한다.

이 기준선의 목적은 단순히 파일을 옮기거나 더 잘게 쪼개는 것이 아니다. 최종 목표는 다음과 같다.

- FOMS를 **단일 Flask 기반 modular monolith**로 유지한다.
- `foms/`를 중심으로 **명확한 canonical product structure**를 만든다.
- `apps/`, 루트 `services/`, 루트 persistence, legacy template/static path는 전환기 bridge로만 다루고, 새 진실(source of truth)은 한 경로에만 둔다.
- 파일 분해 기준을 "작게 나누기"가 아니라 **의미 있는 chunk 단위**로 재정의한다.
- 저장소 루트와 상위 폴더 체계를 정리해 **제품 코드 / 전환기 코드 / 문서 / 하네스 / 비제품 자산**의 경계를 명확히 한다.
- WDCalculator를 포함한 대형 프론트엔드/템플릿 자산은 더 이상 thin wrapper 증가 방식으로 분해하지 않고, 유지보수성이 실제로 올라가는 chunk 기준으로 재편한다.

판단이 갈릴 때는 아래 우선순위로 해석한다.

1. single modular monolith + single source of truth를 더 선명하게 만드는가
2. 더 작은 파일이 아니라 **더 큰 유지보수 가능 chunk**를 남기는가
3. 새 파일 추가보다 제거/통합/병합을 우선했는가
4. 사람과 AI agent가 더 적은 탐색으로 구조를 이해할 수 있는가
5. non-product / quarantine 자산이 product tree를 더럽히지 않는가

### 1.2 기능 요구사항
1. FOMS는 앞으로도 **하나의 deployable Flask modular monolith**로 유지되어야 한다.
2. `app.py`, `app:app`, `start.sh`, `Procfile`, `railway*.toml`, `alembic`, worker, pytest 기준 경로는 구조 개편 중에도 보존되어야 하며, `app.py`는 bootstrap/inventory contract로만 유지하고 새 domain route/business logic의 기본 위치가 되어서는 안 된다.
3. 한 도메인의 **source of truth는 한 경로**에만 있어야 하며, 나머지 경로는 shim/adapter/wrapper만 허용한다.
4. `foms/`는 canonical runtime namespace로 유지하고, 신규 장기 코드의 기본 위치는 `foms/` 아래여야 한다.
5. `apps/`는 전환기 Flask wrapper/alias layer로 축소해야 하며, 신규 장기 비즈니스 로직의 기본 위치가 되어서는 안 된다.
6. 루트 `services/`는 전환기 shim 또는 명시적으로 승인된 예외 모듈만 허용한다.
7. `templates/`와 `static/`는 루트 자산 경로를 유지하되, 내부 구조는 **context 기준**으로 정리해야 한다.
8. 대형 파일 분해는 파일 수를 무한히 늘리는 미세 분해가 아니라, **owner가 명확한 chunk 단위 분해**여야 한다.
9. `WDCalculator`는 더 이상 `*-host-bootstrap.js` 같은 wrapper-only 미세 분해로 진행하지 않는다.
10. 구조 배치는 file count, test count, wrapper count의 증가를 허용하려면 그 증가보다 큰 **ownership 명확화 또는 구 파일 제거**가 있어야 한다.
11. 테스트는 구조 분해와 함께 무한 증식해서는 안 되며, 기본 방향은 **chunk-level contract**로 재정리하는 것이다.
12. `db.py`/`models.py`와 `wdcalculator_db.py`/`wdcalculator_models.py`는 서로 다른 lifecycle로 계속 취급한다.
13. `structured_data` JSONB mutation contract(`copy.deepcopy` + `flag_modified`)는 persistence 관련 구조 정리 중에도 유지되어야 한다.
14. `docs/harness/{policy,bundles,runtime,logs}` taxonomy는 유지되어야 하며, `docs/context`는 incident/reference 성격만 허용한다.
15. `src/foms` 전환, packaging-only `pyproject.toml` 도입, template/static root 이동은 이 기준선 안에서 강행하지 않는다.
16. `business_calendar` / `/calendar` 축은 별도 승인 전까지 계속 구조 정리 범위 밖으로 둔다.
17. 구조 개편 PR/배치는 **한 risk axis만** 다뤄야 하며, 구조 변경과 비즈니스 로직 변경을 섞지 않는다.
18. 모든 구조 작업은 최종적으로 "FOMS 폴더가 한눈에 이해되는가?"라는 관점에서 folder taxonomy를 더 선명하게 만들어야 한다.
19. 모든 structure batch의 기본 의사결정 순서는 **delete -> merge -> extend existing chunk -> add new file** 이어야 하며, 새 파일을 추가한다면 왜 기존 chunk가 흡수할 수 없었는지 같은 batch 계획/기록에 남겨야 한다.
20. 하나의 bounded context가 runtime module 3개 이상이거나 `web/api/services` 두 레이어 이상에 걸치면, 그 context에는 정확히 하나의 local `README.md`를 두고 목적, 주요 모듈, 읽기 순서, 금지 의존성을 적어 AI/human entrypoint로 유지해야 한다.
21. 새로운 shim/wrapper/bridge를 추가할 때는 같은 batch 계획 또는 run record 안에 canonical target, retirement wave, removal condition을 반드시 적어야 하며, 제거 시점이 없는 wrapper는 금지한다.
22. root allowlist 밖의 top-level code directory 또는 runtime contract가 아닌 root standalone script는 구조 부채로 간주하며, Wave 1에서 분류하거나 `scripts/`/`tools/`로 수렴시켜야 한다. 분류되지 않은 상태로 증식시키는 것은 금지한다.
23. 같은 범위의 구조 기준을 보강하는 작업이라면 sibling spec/plan을 계속 늘리지 말고, 우선 기존 controlling spec/plan을 갱신하는 방향을 택한다.
24. 이 spec 승인 이후의 batch부터 본 규칙을 기본값으로 적용한다. 기존 micro asset은 migration debt이지, 앞으로 복제할 precedent가 아니다.

### 1.3 예외/제약 조건
- 이번 spec은 구현 batch가 아니라 **상위 실행 기준선**이다.
- 이 spec만으로 `src/foms`, full packaging, template/static root 이동을 자동 허용하지 않는다.
- DB schema 변경, Alembic revision, persistence lifecycle 통합은 구조 작업과 같은 batch에 섞지 않는다.
- root runtime contract 파일의 경로 이동은 별도 승인 없이는 금지한다.
- WDCalculator, ERP Beta JS, CSS monolith 같은 대형 파일 분해도 **structure-only first**를 지켜야 한다.
- 개별 large-file 실행 순서, inventory, thin wrapper 허용 범위는 `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`를 우선한다.
- "잘게 쪼개는 것 자체"는 성과로 인정하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 적용 대상 파일/경로
| 경로 | 방향 |
|------|------|
| `app.py`, `run.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `alembic.ini`, `migrations/` | root runtime contract로 유지, 경로 이동 금지 |
| `db.py`, `models.py` | main persistence root contract 유지 |
| `wdcalculator_db.py`, `wdcalculator_models.py` | WDCalculator persistence root contract 유지 |
| `foms/platform/` | bootstrap/registration/HTTP/realtime의 단일 canonical owner |
| `foms/web/` | HTML/Jinja page Blueprint의 canonical 위치 |
| `foms/api/` | JSON/API/webhook route의 canonical 위치 |
| `foms/services/` | 도메인 정책/오케스트레이션/service helper의 canonical 위치 |
| `foms/persistence/` | persistence adapter와 향후 package 정렬 포인트 |
| `apps/` | legacy Flask wrapper/alias/adaptor only |
| `services/` | legacy shim + 승인된 예외 only |
| `templates/` | root 유지, 내부는 context + shared partial 기준으로 정리 |
| `static/js/` | root 유지, 내부는 context + bootstrap/state/ui/domain 기준으로 정리 |
| `static/css/` | root 유지, 내부는 foundation/layout/component/context 기준으로 정리 |
| `tests/` | chunk-level contract와 domain regression 중심으로 정리 |
| `docs/` | spec/plan/evolution/harness taxonomy 유지 |
| `Add In Program/`, `SCheduler/` | non-product / side-project / legacy-lab zone으로 취급. 신규 product source 금지 |

### 2.2 목표 디렉터리 구조
이 절은 **최종형(final-form)** 관점에서 본 FOMS 저장소의 목표 구조를 정의한다.

- 아래 `2.2.1`은 **끝 상태의 canonical tree**다.
- 아래 `2.2.2`는 끝 상태에서도 일시적으로만 남을 수 있는 **transition overlay**다.
- 즉, `apps/`와 루트 `services/`를 canonical product tree 안에 영구 구성원처럼 그리지 않는다.

#### 2.2.1 Final canonical tree (end-state view)
```text
repo root
  # Runtime / deploy contract (frozen paths)
  app.py
  run.py
  start.sh
  Procfile
  railway.toml
  railway-worker.toml
  Dockerfile
  alembic.ini
  requirements*.txt
  db.py
  models.py
  wdcalculator_db.py
  wdcalculator_models.py

  # Canonical product tree
  foms/
    README.md
    platform/
    web/
      orders/
      measurement/
      shipment/
      drawing/
      production/
      construction/
      cs/
      wdcalculator/
      admin/
      auth/
    api/
      orders/
      measurement/
      shipment/
      drawing/
      production/
      construction/
      cs/
      wdcalculator/
      channel/
      files/
      notifications/
      admin/
      auth/
    services/
      common/
      admin/
      orders/
      measurement/
      shipment/
      drawing/
      production/
      construction/
      cs/
      wdcalculator/
      channel/
      files/
      notifications/
      auth/
      jobs/
    persistence/
      main/
      wdcalculator/

  templates/
    partials/
      shared/
    orders/
    measurement/
    shipment/
    drawing/
    production/
    construction/
    cs/
    wdcalculator/
    admin/
    auth/
    # channel, files, notifications are API-first; add matching template roots only when a page exists

  static/
    js/
      runtime/
      orders/
      measurement/
      shipment/
      drawing/
      production/
      construction/
      cs/
      wdcalculator/
      channel/
      admin/
      auth/
    css/
      foundation/
      layout/
      components/
      contexts/

  migrations/

  tests/
    contracts/
    domains/
    harness/
    fixtures/
    support/

  scripts/
    ops/
    maintenance/
    migrations/

  tools/
    harness/
    smoke/
    research_center/

  data/

  docs/
    specs/
    plans/
    evolution/
    guides/
      validation/
    incidents/
    harness/
      policy/
      bundles/
      runtime/
      logs/
    context/
      analysis/
      manual-artifacts/

  README.md
  AGENTS.md
  CLAUDE.md

  .cursor/
  .claude/
  .agents/
  .github/
  .vscode/

  Add In Program/
  SCheduler/
```

#### 2.2.2 Transition overlay (explicitly not final)
```text
transition overlay
  apps/                # thin Flask wrapper / alias / import bridge only
  services/            # shim / explicit exception only
  root standalone helper scripts
                       # migrate_*.py, *_automation.py, *_generator.py 등은 scripts/ 또는 tools/로 수렴
  ambiguous top-level code roots
                       # 예: src/ 는 product/tooling/quarantine 중 하나로 분류되기 전까지 성장 금지
```

보충 규칙:
- `apps/`와 루트 `services/`는 **transition overlay**일 뿐, 최종 canonical product tree의 일부가 아니다.
- 루트 `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py`는 **compatibility surface**이고, 장기 구현 정렬 지점은 `foms/persistence/main`, `foms/persistence/wdcalculator`다.
- `templates/partials/shared/`는 **cross-context partial**만 허용한다. context 전용 partial은 해당 `templates/<context>/` 아래에 둔다.
- `static/js/runtime/`은 **cross-context runtime primitive**만 허용한다. domain logic, screen orchestration, context policy는 각 context 폴더에 둔다.
- `foms/services/common/`은 **cross-context, domain-neutral helper**만 허용한다. 특정 도메인 언어가 드러나는 코드는 해당 context package로 보낸다.
- `channel`, `files`, `notifications`는 기본적으로 API-first context다. 나중에 human-facing page가 생기면 generic bucket을 만들지 말고 matching `foms/web/<context>`, `templates/<context>`, `static/js/<context>`를 만든다.
- `foms/services/files/` 안의 leaf 이름으로 `storage.py` 같은 모듈을 둘 수는 있지만, 별도의 sibling context package `foms/services/storage/`를 새 canonical 경로로 만들지는 않는다.
- `foms/services/notifications/` 안의 leaf 이름으로 `realtime_notifications.py` 같은 모듈을 둘 수는 있지만, 최종 context package 이름은 `notifications`로 고정한다.
- Alembic revision의 source of truth는 `migrations/`뿐이다. `scripts/migrations/`는 one-off operational helper나 data/backfill script만 허용한다.
- `src/`는 final canonical tree의 일부가 아니다. Wave 1에서 tooling, 별도 non-product track, 또는 quarantine 중 하나로 분류되지 않으면 더 이상 성장시킬 수 없다.
- `data/`는 versioned non-secret config/seed/reference만 허용한다. dump, SQLite, migration scratch DB, browser QA DB 등 **런타임 산출물은 repo `data/` 안에 두지 않는다.** 로컬 운영자 산출물의 정본 루트는 **`FOMS_RUNTIME_OUTPUT_ROOT`** 이며, 미설정 시 기본값은 **`%USERPROFILE%\FOMS-runtime`** (Windows). 하위 경로 계약은 `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` §3.4와 동일하다. 로컬 백업·덤프 출력 정본 또한 `${FOMS_RUNTIME_OUTPUT_ROOT}/dumps/...` (예: `foms.dump`, `order_schedule_dates-*.json`)이며, repo 루트에 별도 `backups/` 트리를 두지 않는다 (`docs/specs/2026-06-05-backup-feature-retirement_SPEC.md`).
- 루트 허용 파일/폴더의 **정본 목록**은 `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` **§2.6.1 Final root allowlist (exact set; dual-spec lock)** 와 단일하다. 본 절 §2.2.1 final-form tree는 그 목록을 도식화한 것이며, 충돌 시 **§2.6.1 텍스트가 우선**한다.
- `Add In Program/`, `SCheduler/`는 저장소 taxonomy의 일부로는 인정하지만, 끝까지 product source of truth가 될 수 없다.

#### 2.2.3 FR20 — local `README.md` authoritative home (PTC dual-spec lock)

§1.2.20의 요구를 다음 **정본 위치**로 고정한다. context당 **정확히 하나**만 허용한다.

| 구분 | Context | Authoritative home |
|------|---------|-------------------|
| page-first | `orders`, `measurement`, `shipment`, `drawing`, `production`, `construction`, `cs`, `wdcalculator`, `admin`, `auth` | `foms/web/<context>/README.md` |
| API-first | `channel`, `files`, `notifications` | `foms/api/<context>/README.md` |

금지: `templates/`·`static/`에 canonical entrypoint로서의 context README. 이행·현재→목표 표는 `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` §4.2.

### 2.3 Bounded Context 기준선
향후 구조 작업은 "파일 종류"보다 "도메인/화면/유스케이스" 기준으로 움직인다.

| 도메인 | Canonical target | 전환기 bridge |
|------|------|------|
| Orders | `foms/web/orders`, `foms/api/orders`, `foms/services/orders` | `apps/order_*`, `apps/api/erp_orders_*`, `apps/api/orders`(thin adapter **선례**), 기타 legacy API/page overlay |
| Measurement | `foms/web/measurement`, `foms/api/measurement`, `foms/services/measurement` | 기존 legacy template/static mirror/wrapper |
| Shipment | `foms/web/shipment`, `foms/api/shipment`, `foms/services/shipment` | `apps/erp_shipment_page.py`, 관련 legacy API |
| Drawing | `foms/web/drawing`, `foms/api/drawing`, `foms/services/drawing` | `apps/erp_drawing_workbench.py`, 관련 legacy API |
| Production / Construction / CS | 각 context별 `foms/web/*`, `foms/api/*`, `foms/services/*` | `apps/erp_*_page.py`, legacy API |
| WDCalculator | `foms/web/wdcalculator`, `foms/api/wdcalculator`, `foms/services/wdcalculator`, `foms/persistence/wdcalculator` | 현재 `apps/api/wdcalculator.py`, `templates/wdcalculator/*`, `static/js/wdcalculator/*`, root WD persistence |
| Channel / Notifications | `foms/api/channel`, `foms/api/notifications`, `foms/services/channel`, `foms/services/notifications` | `apps/api/channel_*`, legacy helpers |
| Files / Storage | `foms/api/files`, `foms/services/files` | legacy file/attachment routes |
| Auth / Admin | `foms/web/auth`, `foms/web/admin`, `foms/api/auth`, `foms/api/admin`, `foms/services/auth`, `foms/services/admin` | legacy `apps/auth.py`, `apps/admin.py` |

원칙:
- 한 context 안에서 `web`, `api`, `services`는 같은 도메인 언어를 써야 한다.
- route naming, template path, JS namespace도 가능하면 context 이름과 맞춘다.
- context 경계가 먼저이고, 그 안에서 file split은 두 번째다.
- `foms/services/jobs/`는 cross-cutting background job orchestration owner다. worker/bootstrap registration은 `foms/platform`에 두고, domain policy는 jobs 안이 아니라 각 domain service에 둔다.

#### 2.3.1 핵심 용어 정의
- **owner**: 해당 파일/chunk의 변경 이유를 한 문장으로 설명할 수 있는 책임 단위
- **meaningful chunk**: 하나의 bounded context 안에서 하나의 user journey, API resource cluster, UI region, orchestration phase, policy cluster 중 하나를 주 책임으로 소유하는 덩어리
- **chunk-level contract**: 하나의 chunk가 하나의 주된 regression surface로 검증될 수 있는 상태
- **split-brain**: 같은 도메인의 실질 구현이 canonical path와 bridge path에 동시에 남아 있어, 새 변경 시 둘 다 읽어야 하는 상태
- **merge-back candidate**: owner, lifecycle, contract surface가 같은 인접 module로서, 새 sibling file을 추가하기 전에 먼저 병합 여부를 검토해야 하는 대상

#### 2.3.2 Live registry reconciliation (Wave 2, 2026-04-13)
- **Domain-level 표(위 §2.3 표)**는 방향성을 유지한다. **개별 blueprint 모듈 단위의 live owner, bridge debt, 선행 선례(Measurement / Orders API)**는 `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md` 및 `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md`의 기록을 우선한다.
- §2.3 Orders 행의 bridge 열은 **요약**이다. `apps.api.orders`는 `foms.api.orders` helper로 위임하는 **thin adapter 선례**로 확인되었으나, `apps.api.erp_orders_*`, `apps.order_*`, `apps.calendar_page` 등은 동일 선례로 자동 승격되지 않으며 **대부분 legacy owner**다.
- 이후 Wave에서 말하는 "`apps/`는 thin adapter role"은 **신규 구조 작업의 운영 기본값**(신규 route는 `foms/web`·`foms/api` 우선)을 뜻하며, **기존 `apps/*` 전체가 이미 thin adapter라는 주장이 아니다.**

### 2.4 레이어별 경계 규칙
| 레이어 | 소유 | 허용 | 금지 |
|------|------|------|------|
| `foms/platform` | app factory, blueprint registry, HTTP/realtime bootstrap | `foms/web`, `foms/api` 등록, shared extension wiring | 비즈니스 로직, 도메인 정책 |
| `foms/web` | HTML page routes, template context assembly | `foms/services` 호출 | 직접 SQL/ORM 중심 로직 누적 |
| `foms/api` | JSON/API/webhook routes | `foms/services` 호출 | 정책 중복, persistence 직접 소유 |
| `foms/services` | 비즈니스 로직, policy, orchestration | `foms/persistence`, 다른 service helper | Flask request context 의존, template rendering, blueprint import |
| `foms/persistence` | DB access helper, model/session adapter | SQLAlchemy / DB helper | web/api/platform import |
| `apps/` | legacy Flask wrapper, decorator, import bridge | `foms/web`, `foms/api`, `foms/services` 호출 | 신규 장기 비즈니스 로직 |
| 루트 `services/` | shim, explicit exception | `from foms.services...` re-export | 새 canonical 구현 추가 |
| `templates/` / `static/` | Flask asset root | context 내부 namespace 정리 | root 물리 이동, wrapper-only 세분화 |

### 2.5 루트와 폴더 체계 정책
루트는 아래 일곱 범주만 허용한다.

1. runtime contract
   - `app.py`, `run.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `alembic.ini`, `requirements*.txt`, `db.py`, `models.py`, `wdcalculator_*.py`
2. canonical product tree
   - `foms/`, `templates/`, `static/`, `migrations/`
3. transition overlay
   - `apps/`, `services/`, `src/`(있는 경우 역할 분류 전까지), root standalone helper scripts
4. verification / tooling / ops
   - `tests/`, `scripts/`, `tools/`, `data/`
5. docs / governance
   - `docs/`, `README.md`, `AGENTS.md`, `CLAUDE.md`
6. IDE / agent / automation supply chain
   - `.cursor/`, `.claude/`, `.agents/`, `.github/`, `.vscode/`
7. quarantine / non-product
   - `Add In Program/`, `SCheduler/`

**PTC dual-spec lock:** 위 일곱 범주는 **분류 언어**다. **최종 committed tree에서 허용되는 루트 엔트리의 정확한 집합**은 `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` **§2.6.1** 과 `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` **§4.1** 과 단일하다. PTC 최종 closeout에서는 **`apps/`·루트 `services/`·`src/`가 루트에 없어야** 하며(§4.1·§8), 전환기 오버레이는 수렴 전까지만 본 절 §2.2.2에서 규율한다.

루트 및 canonical product tree에서 금지하는 것:
- scratch HTML/JS/MD
- dump/log/temp output
- 비교용 임시 산출물
- duplicated runtime files
- 비제품 실험 코드를 product source와 같은 수준에서 늘리는 것

비제품 구역 규칙:
- `Add In Program/`, `SCheduler/`는 FOMS canonical source가 될 수 없다.
- product tree에서 quarantine / non-product tree로의 runtime import가 발생하면 안 된다.
- 향후 정리 시에는 하나의 quarantine namespace로 통합할 수 있으나, 그 전까지는 "새 product code 금지"만 먼저 강제한다.
- 분류되지 않은 top-level code directory(예: `src/`처럼 product/tooling/quarantine 중 어디인지 모호한 경우)는 Wave 1에서 역할을 명시해야 하며, 역할이 정해지기 전까지 product source 확장의 근거가 될 수 없다.
- runtime contract를 제외한 root standalone helper script는 touch 시점에 `scripts/` 또는 `tools/`로 수렴시키는 것을 기본값으로 한다.
- transition overlay는 물리적으로 존재할 수 있지만, 새 장기 코드의 기본 위치가 되어서는 안 된다.

### 2.6 Chunk-first 분해 규칙
이번 재기준선의 핵심은 "미세 분해 금지, 의미 있는 chunk 우선"이다.

#### 2.6.1 기본 원칙
- 먼저 묻는 질문은 "더 작게 쪼갤 수 있나?"가 아니라 **"한 덩어리의 owner를 더 명확하게 만들 수 있나?"**다.
- split의 1차 목적은 line count가 아니라 **유지보수 단위 정리**다.
- 새 파일은 가능한 한 **한 use case / 한 UI region / 한 orchestration phase / 한 policy cluster**를 소유해야 한다.
- 기본 행동 순서는 **삭제 -> 병합 -> 기존 chunk 확장 -> 새 파일 추가**다.
- 같은 owner/lifecycle/contract를 공유하는 peer module이 이미 여러 개라면, 새 sibling file을 만들기 전에 merge-back candidate를 먼저 검토한다.
- 같은 concern에서 네 번째 peer file을 추가하려면, 왜 기존 peer들을 접거나 합칠 수 없는지 구조 기록에 남겨야 한다.
- context에 local `README.md`가 필요한 상태가 되었는데 갱신되지 않았다면, 그 batch는 구조 정리가 덜 끝난 것으로 본다.

#### 2.6.2 허용되는 좋은 chunk 예시
- Orders: `regional`, `status`, `field_update`처럼 **resource/use-case 기준**으로 나눈 API handler chunk
- Measurement: page/API/helper를 하나의 **vertical slice**로 묶는 구조
- WDCalculator: `composition`, `primary form`, `estimate lifecycle`, `pricing core` 같은 **owner chunk**
- CSS: `foundation`, `layout`, `component`, `context` 같은 **logical styling chunk**

#### 2.6.3 금지되는 나쁜 split 예시
- `bootstrap.js`가 있는데 같은 역할의 `host-bootstrap.js`를 하나 더 만드는 경우
- 10~30줄짜리 pass-through wrapper만 별도 파일로 떼는 경우
- getter/setter forwarding만 위해 state file과 support test를 한 쌍 더 만드는 경우
- 한 화면의 하나의 lifecycle을 3~5개 shell file로 나누는 경우
- 파일 수와 테스트 수는 늘었는데 owner가 더 명확해지지 않는 경우

#### 2.6.4 파일 크기와 split 트리거
기존 거버넌스의 hard threshold는 유지하되, preferred split 기준은 더 굵게 잡는다.

| artifact | hard threshold | preferred chunk 기준 |
|------|------|------|
| Python module | large-file 후보 500줄+ | 1 owner 기준 200~500줄 정도면 유지 가능 |
| JS module | large-file 후보 300줄+ | 1 screen flow / 1 domain flow 기준으로 150~400줄 정도면 유지 가능 |
| Jinja template | large-file 후보 800줄+ | 1 page + 명확한 region partial 기준으로 유지 |
| CSS | large-file 후보 500줄+ | foundation/layout/component/context 분리 기준으로 유지 |

보충:
- threshold를 넘었다고 자동 split하지 않는다.
- threshold 미만이어도 owner가 2개 이상 섞이면 split할 수 있다.
- split 후 file count가 증가한다면, 증가 이유와 제거될 구파일 목록을 같은 batch에 명시해야 한다.
- preferred chunk 범위는 "가능하면 그 안에서 유지"가 아니라, 특별한 이유가 없다면 **기존 chunk를 최대한 그 범위의 상단까지 유지**하라는 뜻이다.
- owner, lifecycle, contract가 같은 file들이 preferred 범위 안에 머무른다면 split보다 merge/유지가 기본값이다.

#### 2.6.5 테스트 분해 규칙
- 기본 원칙은 **1 chunk = 1 contract surface**다.
- tiny helper마다 pytest + support JS pair를 추가하지 않는다.
- structure-only batch에서는 기존 contract를 유지하는 방향으로 테스트를 합치거나 재사용한다.
- `tests/support/*` + `test_*_contract_node.py` pair는 복제 기본값이 아니다. 새 pair를 추가한다면 왜 기존 chunk contract로 흡수할 수 없는지 남겨야 한다.
- structure batch는 product/wrapper/test 중 최소 한 축에서 순감 또는 최소 동결을 목표로 해야 하며, 순증가가 필요한 경우에는 같은 batch 계획/기록 안에 제거 대상, 제거 wave, 증가 이유를 함께 적어야 한다.
- decomposition batch run record에는 최소한 다음 delta를 기록한다.
  - product file delta
  - wrapper file delta
  - test file delta
  - canonical target
  - removal/merge target
  - new shim retirement wave (있다면)
  - local `README.md` update 여부

### 2.7 WDCalculator 특별 규칙
WDCalculator는 이번 spec에서 별도 예외가 아니라, **과분해를 멈추는 대표 사례**로 본다.

#### 유지할 것
- `/wdcalculator` public/runtime contract
- Jinja config contract
- save/load/sidebar/query param/DOM contract
- existing persistence separation
- `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`의 public surface 유지 목적 thin wrapper/shim 허용 원칙 자체는 유지

#### 중단할 것
- 새로운 `*-host-bootstrap.js`
- wrapper-only batch
- 미세한 configure/init forwarding 테스트 증식

해석:
- 본 금지는 **WDCalculator 트랙의 anti-pattern 회귀 방지 규칙**이다.
- 다른 large-file candidate에서 public path 유지 목적의 thin wrapper/template shell은 `2026-04-10` spec에 따라 계속 허용될 수 있다.
- 단, 기존에 만들어진 micro asset은 앞으로의 설계 precedent가 아니라 정리 대상 debt로 본다.

#### 앞으로의 canonical chunk 방향
1. `composition`
   - giant inline composition root 단순화
   - load order / lifecycle band 정리
2. `primary form`
   - base components, notes, coupon display, additional options, product catalog
3. `estimate lifecycle`
   - list/search/load/edit/save/refresh/sidebar/url
4. `pricing core`
   - current estimate math, aggregate totals, orchestration contract

WDCalculator batch 승인 조건:
- file count가 순감하거나 최소 동결이어야 한다.
- wrapper count는 반드시 줄어야 한다.
- test count는 chunk 기준으로 유지되거나 줄어야 한다.

### 2.8 구조 작업의 배치 규칙
- 한 batch는 한 boundary만 다룬다.
- structure-only first, behavior later 원칙을 지킨다.
- blueprint / API / template / JS / CSS / persistence를 한 batch에서 동시에 크게 건드리지 않는다.
- 각 batch는 "무엇을 canonical로 만들고, 무엇을 shim으로 남기는지"를 한 줄로 말할 수 있어야 한다.
- post-audit 없이 다음 batch로 넘어가지 않는다.

#### 2.8.1 Direction Lock 질문
각 structure batch는 승인 전에 아래 질문에 짧게라도 답해야 한다.

1. 이번 batch는 single source of truth를 더 선명하게 만드는가
2. split-brain을 줄이는가, 아니면 임시로 늘린다면 언제 다시 줄일 것인가
3. 새 파일 추가 전에 delete/merge/extend를 실제로 검토했는가
4. 새 파일이 있다면 그것이 **가장 큰 유지보수 가능 chunk**인가
5. product/wrapper/test file 수는 순감 또는 최소 동결인가
6. 순증가라면 어떤 파일을 언제 없앨지 이미 적혀 있는가
7. local `README.md` 또는 동등한 AI entrypoint가 이번 변경 범위를 반영하는가
8. 이 패턴이 10번 반복돼도 FOMS 폴더가 더 깔끔해질 것 같은가
9. product / bridge / tooling / docs / quarantine 경계가 더 선명해졌는가
10. 지금 이 batch가 구조 작업인지, 아니면 슬쩍 기능 변경을 섞고 있는지 명확한가

### 2.9 Migration Waves
이 spec 이후의 구조 작업은 아래 큰 wave를 따라간다.

#### Wave 0 — 기준선 고정
- 이 spec을 승인한다.
- context owner map과 root/quarantine policy를 기준선으로 고정한다.

#### Wave 1 — Root / folder hygiene
- `2026-04-07` Step 2 closeout 이후의 **지속적** 루트/taxonomy 정렬을 수행한다.
- non-product zones(`Add In Program/`, `SCheduler/`)를 quarantine로 명시한다.
- product tree 밖으로 새로운 source of truth가 생기지 않도록 차단한다.
- root allowlist inventory를 만들고, runtime contract가 아닌 root standalone script는 `scripts/`/`tools/`로 수렴시키는 방향을 우선 적용한다.
- `src/` 등 모호한 top-level code directory는 product/tooling/quarantine 중 하나로 역할을 고정한다.
- product tree가 quarantine/non-product tree를 import하지 않도록 차단 규칙을 먼저 둔다.

#### Wave 2 — Bounded context map과 blueprint clarity
- `foms/platform/blueprints.py` 기준으로 현재 blueprint를 domain map으로 문서화한다.
- 신규 route는 `foms/web` / `foms/api`로 우선 배치한다.
- `apps/`는 thin adapter role로 고정한다.

#### Wave 3 — API canonicalization
- Orders에서 이미 검증한 thin wrapper + canonical helper 패턴을 다른 API context에 확장한다.
- 우선순위는 read-heavy / low-risk context부터 시작한다.
- hidden side effect contract를 먼저 freeze한다.

#### Wave 4 — Web / page slice migration
- Measurement precedent를 따르되, shipment / drawing / production / construction / CS 등 page slice를 하나씩 정리한다.
- template path와 JS path는 wrapper/mirror로 안정화한다.

#### Wave 5 — Large front-end island rebaseline
- WDCalculator를 chunk-first 기준으로 재편한다.
- `erp_beta_js.html`, layout-level giant JS, regional dashboard giant template/CSS도 같은 기준으로 다룬다.
- thin wrapper 증가를 성과로 보지 않는다.
- 개별 파일의 실행 순서, inventory, wave priority, batch boundary는 `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md` §8·§9를 우선한다.

#### Wave 6 — Service namespace rationalization
- `foms/services`를 context package 기준으로 정리한다.
- flat module은 touch 시점에만 context package로 옮긴다.
- 루트 `services/`는 shim 또는 explicit exception만 남긴다.
- 루트 `services/`에 남는 shim은 canonical target과 retirement condition이 없는 상태로 방치하지 않는다.
- batch order, branch/stop semantics, pilot/defer register, Wave 7/8 handoff는 `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`를 authoritative execution runbook으로 따른다.

#### Wave 7 — Test / contract rationalization
- domain contract, chunk contract, harness contract의 레벨을 정리한다.
- micro support file 증식 패턴을 줄인다.
- split마다 test count가 기하급수적으로 늘지 않게 관리한다.
- 새 chunk를 만들 때 테스트도 새 micro pair를 복제하는 대신, 가능한 한 기존 chunk contract로 접는 것을 기본값으로 삼는다.
- batch order, branch/stop semantics, runtime-anchor/WDCalculator pilot boundary, status/defer register, Wave 8 handoff는 `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md`를 authoritative execution runbook으로 따른다.

#### Wave 8 — Legacy bridge retirement
- `apps/`와 루트 `services/`의 잔여 bridge를 context 단위로 정리한다.
- 어떤 shim을 언제 없앨지 명시한다.
- Wave 3~7에서 남긴 removal/merge target을 여기서 닫지 못하면, 해당 context는 "정리 중"이 아니라 "bridge 고착" 상태로 본다.
- batch order, branch/stop semantics, service-compat/direct-import pilot boundary, status/defer register, continuation handoff는 `docs/plans/2026-04-14-wave8-legacy-bridge-retirement-execution-plan.md`를 authoritative execution runbook으로 따른다.

#### Wave 9 — Packaging reopen review
- Step 8에서 defer한 조건이 충족됐는지 별도 ADR/plan로 다시 검토한다.
- `src/foms`와 packaging-only hardening은 이 wave 이전에는 다시 열지 않는다.
- batch order, readiness/meta-closeout boundary, Option A/B/C matrix, implementation-handoff-only rule, audit-loop hard-stop은 `docs/plans/2026-04-14-wave9-packaging-reopen-review-execution-plan.md`를 authoritative execution runbook으로 따른다.
- **실행 상태 (2026-04-14):** W9-B0~B4를 docs-only mainline으로 완료. Step 8 reopen gate 5항은 live truth 기준 **미충족**으로 확인되어 packaging verdict는 **`Option A` (explicit defer closeout)**. `Option B`/`Option C` 구현·handoff는 본 wave에서 생성하지 않음(전용 구현 트랙에서만). 실행 기록은 §5 Wave 9 실행 기록 목록을 참고한다.
- **추가 실행 상태 (2026-04-15):** post-Wave9 endgame Program 1~4를 완료했다. `WR-P1`/`WR-O1`/`WR-S2`는 executable row로 닫혔고, `WR-J1`/`WR-H1`는 continuation 조건을 명시한 채 closeout되었다. overlay minimization과 final checklist 문서화까지 완료했으며, packaging reopen은 계속 열지 않았다.

## 3. Steps — 실행 단계
- [x] Step 0: 이 spec을 승인하고, 이후 구조 작업의 상위 기준선으로 채택한다.
- [x] Step 1: FOMS top-level을 `runtime / product / tooling / docs / quarantine` 다섯 축으로 재정의하고, 비제품 구역의 신규 source 생성 금지 규칙을 적용한다.
- [x] Step 2: 현재 blueprint와 API/page를 bounded context map으로 문서화하고, 신규 코드는 `foms/*` 우선 원칙을 적용한다.
- [x] Step 3: large-file decomposition은 `meaningful chunk` 기준으로만 진행하고, batch별 file/test/wrapper delta를 기록한다.
- [x] Step 4: WDCalculator는 chunk merge 방향으로 재설계하고, wrapper-only 분해를 종료한다.
- [x] Step 5: Orders/Measurement precedent를 기준으로 다른 context도 `thin wrapper + canonical slice` 패턴으로 확장한다.
- [x] Step 6: root `services/`와 `apps/`의 legacy bridge를 context 단위로 줄이고, split-brain을 계속 좁힌다.
- [x] Step 7: Step 8 reopen 조건이 충족되기 전까지 packaging과 root contract relocation을 다시 열지 않는다.

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python tools/harness/verify_result.py --json` 또는 승인된 shared baseline 통과
- [ ] 해당 batch의 focused pytest 통과
- [ ] runtime contract를 건드린 경우 web + worker parity smoke 확인
- [ ] template/static decomposition의 경우 manual smoke checklist 또는 equivalent regression evidence 포함
- [ ] structure batch run record에 아래 delta가 포함됨
  - [ ] product file delta
  - [ ] wrapper file delta
  - [ ] test file delta
  - [ ] canonical target
  - [ ] removal/merge target
  - [ ] new shim retirement wave (있다면)
  - [ ] local `README.md` update 여부
- [ ] 한 batch 안에서 새 Alembic revision, schema 변경, persistence lifecycle 변경이 섞이지 않음
- [ ] root/runtime contract file이 무단 이동되지 않음
- [ ] `git status` 기준으로 root scratch/log/temp/generated clutter가 새로 생기지 않음
- [ ] context가 3개 이상 runtime module 또는 다층 구조라면 local `README.md`가 존재하고 최신 변경을 반영함
- [ ] root allowlist 밖의 top-level code directory 또는 root standalone script가 새로 늘어나지 않음
- [ ] product tree에서 quarantine/non-product tree로의 runtime import가 생기지 않음
- [ ] file/test/wrapper가 순증가한 경우 제거 대상과 제거 wave가 같은 기록 안에 포함됨
- [ ] Direction Lock 질문에 대한 답이 batch 문서 또는 run record에 남아 있음

## 5. 참고 자료
- 관련 상태 문서: `docs/AI_STATUS.md`
- 관련 결정: `docs/harness/policy/DECISIONS.md`
- 관련 인덱스: `docs/ARCHIVE_INDEX.md`
- 상위 거버넌스: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- large-file 거버넌스: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
- vertical slice 선례: `docs/plans/2026-04-10-step5-measurement-vertical-slice-plan.md`
- orders 경계 선례: `docs/plans/2026-04-11-orders-boundary-decomposition-plan.md`
- packaging defer 선례: `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`
- Wave 1 실행 계획: `docs/plans/2026-04-13-wave1-root-folder-hygiene-execution-plan.md`
- Wave 2 실행 계획: `docs/plans/2026-04-13-wave2-bounded-context-map-blueprint-clarity-execution-plan.md`
- Wave 3 실행 계획: `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md`
- Wave 4 실행 계획: `docs/plans/2026-04-13-wave4-web-page-slice-migration-execution-plan.md`
- Wave 5 실행 계획: `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
- Post-Wave9 endgame master order: `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md`
- Wave 5 실행 기록 (large front-end island: readiness / wdcalculator contract freeze / four-chunk canonicalization / shared ERP pilot lock+freeze+rebaseline / closeout):
  - `docs/plans/2026-04-14-wave5-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch1-wdcalculator-contract-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch2-wdcalculator-composition-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch3-wdcalculator-primary-form-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch4-wdcalculator-estimate-lifecycle-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch5-wdcalculator-pricing-core-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch6-shared-erp-island-lock-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch7-erp-beta-contract-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch8-erp-beta-rebaseline-run-record.md`
  - `docs/plans/2026-04-14-wave5-batch9-closeout-run-record.md`
- Wave 6 실행 계획: `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md`
- Wave 7 실행 계획: `docs/plans/2026-04-14-wave7-test-contract-rationalization-execution-plan.md`
- Wave 8 실행 계획: `docs/plans/2026-04-14-wave8-legacy-bridge-retirement-execution-plan.md`
- Wave 8 사전 GDM 핸드오프 (Wave 7 closeout 확인·W8-B0 진입 전 체크리스트): `docs/plans/2026-04-14-wave8-pre-execution-gdm-handoff.md`
- Wave 7 실행 기록 (test / contract rationalization: readiness / taxonomy / runtime-anchor freeze+rationalization / wdcalculator chunk freeze+rationalization / status register / closeout):
  - `docs/plans/2026-04-14-wave7-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch1-test-taxonomy-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch2-runtime-anchor-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch3-runtime-anchor-rationalization-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch4-wdcalculator-chunk-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch5-wdcalculator-chunk-contracts-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch6-status-register-run-record.md`
  - `docs/plans/2026-04-14-wave7-batch7-closeout-run-record.md`
- Wave 8 실행 기록 (legacy bridge retirement: readiness / taxonomy / service-compat freeze+retirement / direct-import freeze+retirement / status register / closeout):
  - `docs/plans/2026-04-14-wave8-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch1-bridge-taxonomy-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch2-service-compat-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch3-service-compat-retirement-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch4-direct-import-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch5-direct-import-retirement-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md`
  - `docs/plans/2026-04-14-wave8-batch7-closeout-run-record.md`
- Post-Wave9 endgame continuation / closeout 기록:
  - `docs/plans/2026-04-15-wr-p1-personal-board-adapter-shell-run-record.md`
  - `docs/plans/2026-04-15-wr-o1-orders-adapter-shell-run-record.md`
  - `docs/plans/2026-04-15-wr-j1-jobs-runtime-string-contract-run-record.md`
  - `docs/plans/2026-04-15-wr-s2-storage-singleton-init-adjacent-run-record.md`
  - `docs/plans/2026-04-15-wr-h1-high-risk-cluster-continuation-lock-run-record.md`
  - `docs/plans/2026-04-15-post-wave9-program3-overlay-minimization-closeout-run-record.md`
  - `docs/plans/2026-04-15-post-wave9-program4-final-checklist-closeout-run-record.md`
- Wave 9 실행 기록 (packaging reopen review: readiness / packaging surface freeze / option matrix freeze / decision freeze / closeout):
  - `docs/plans/2026-04-14-wave9-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-14-wave9-batch1-packaging-surface-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave9-batch2-option-matrix-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave9-batch3-packaging-decision-run-record.md`
  - `docs/plans/2026-04-14-wave9-batch4-closeout-run-record.md`
- Wave 6 실행 기록 (service namespace rationalization: readiness / shim registry / contract freeze / package pilot / status register / closeout):
  - `docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch5-files-helper-pilot-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md`
  - `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md`
- Wave 2 실행 기록 (bounded context / spec reconcile / registry / adapter / README / closeout):
  - `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md`
  - `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md`
  - `docs/plans/2026-04-13-wave2-batch3-blueprint-registry-clarity-run-record.md`
  - `docs/plans/2026-04-13-wave2-batch4-apps-thin-adapter-contract-run-record.md`
  - `docs/plans/2026-04-13-wave2-batch5-readme-coverage-run-record.md`
  - `docs/plans/2026-04-13-wave2-batch6-closeout-run-record.md`
- Wave 3 실행 기록 (API canonicalization: readiness / files / address / aggregate lock / personal_board / closeout):
  - `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-13-wave3-batch1-files-contract-freeze-run-record.md`
  - `docs/plans/2026-04-13-wave3-batch2-files-canonicalization-run-record.md`
  - `docs/plans/2026-04-13-wave3-batch3-address-canonicalization-run-record.md`
  - `docs/plans/2026-04-13-wave3-batch4-aggregate-read-lock-run-record.md`
  - `docs/plans/2026-04-13-wave3-batch5-aggregate-read-canonicalization-run-record.md`
  - `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md`
- Wave 4 실행 기록 (web / page slice: readiness / pilot freeze / cs owner+template / dashboard lock / production owner+template / closeout):
  - `docs/plans/2026-04-13-wave4-batch0-readiness-gate-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch1-pilot-contract-freeze-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch2-pilot-page-owner-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch3-pilot-template-namespace-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch4-dashboard-family-lock-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch5-dashboard-page-owner-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch6-dashboard-template-namespace-run-record.md`
  - `docs/plans/2026-04-13-wave4-batch7-closeout-run-record.md`
- WDCalculator 현행 기준선: `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`
- handoff 기준: `docs/context/COMPACT_CHECKPOINT.md`

보충:
- `docs/context/*`는 `docs/harness/policy/DECISIONS.md` 기준으로 incident/reference 성격을 유지한다.
- `COMPACT_CHECKPOINT.md`는 현재 handoff reference로 사용하되, 향후 성격이 runtime state 쪽으로 기울면 `docs/harness/runtime/`로 재배치 여부를 검토한다.

## 6. 승인 게이트 및 중단 조건
다음 중 하나라도 충족되면 구조 작업을 즉시 중단하고 별도 spec/ADR로 분리한다.

- packaging 또는 `src/foms` 전환이 슬쩍 다시 섞이기 시작할 때
- main persistence와 WDCalculator persistence를 같은 batch에서 건드리게 될 때
- template/static root 이동이 필요해질 때
- `apps/`와 `foms/` 양쪽에 같은 도메인의 실질 구현이 다시 생길 때
- WDCalculator 분해가 다시 wrapper-only micro batch로 회귀할 때
- file count/test count는 늘었는데 owner가 더 명확해지지 않을 때
- structure-only batch가 pricing/API/permission/business logic 변경을 같이 포함하게 될 때
- 새 file/shim/wrapper를 추가했는데 removal target과 retirement wave가 비어 있을 때
- root allowlist 밖의 code directory 또는 root standalone script가 새로 생길 때
- 같은 concern에서 peer file만 계속 늘고 merge-back review가 빠질 때
- local `README.md`가 필요한 context인데 갱신 없이 file 수만 늘어날 때

## 7. 해석
이 spec은 기존 거버넌스를 뒤집는 문서가 아니다.

- `2026-04-07` spec이 **무엇을 함부로 건드리면 안 되는지**를 정한 문서라면,
- `2026-04-10` large-file spec은 **대형 파일을 어떤 규칙으로 분해해야 하는지**를 정한 문서이고,
- 이 문서는 그 위에서 **FOMS 전체를 어떤 폴더 체계와 어떤 chunk 기준으로 정리할지**를 다시 기준선화한 문서다.

핵심은 세 가지다.

1. FOMS는 하나의 modular monolith로 더 선명해져야 한다.
2. 파일 분해는 더 작게가 아니라 더 명확하게여야 한다.
3. FOMS 폴더 전체는 product / bridge / tooling / docs / quarantine가 한눈에 구분되는 구조여야 한다.

추가 해석:
- 이 spec 승인 이후의 구조 batch는 "기존에 있던 미세 파일도 있었으니 이번에도 비슷하게 만들자"라는 논리를 사용할 수 없다.
- `2026-04-10` spec의 thin wrapper 허용을 적용해야 한다면, 같은 batch 기록 안에 왜 wrapper가 임시로 필요한지와 언제 제거할지를 같이 적어야 한다.
