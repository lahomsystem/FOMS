# Wave 2 Bounded Context Map / Blueprint Clarity Execution Plan
> 작성일: 2026-04-13 | 상태: 실행 준비 완료 (LLM batch-ready)
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `foms/platform/blueprints.py`
> 앱 bootstrap entry: `foms/platform/app_factory.py`
> 선행 wave: `docs/plans/2026-04-13-wave1-root-folder-hygiene-execution-plan.md`
> 구조 선례: `docs/plans/2026-04-10-step5-measurement-vertical-slice-plan.md`, `docs/plans/2026-04-11-orders-boundary-decomposition-plan.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 2 — Bounded context map과 blueprint clarity**를 바로 실행할 수 있는 LLM용 실행 계획서다.

Wave 2의 목적은 "다음에 어느 context를 옮길 것인가"를 추상적으로 토론하는 것이 아니라, **현재 Flask blueprint registry의 실제 truth**를 먼저 고정하고, 그 truth를 기준으로 이후 Wave 3~4가 재해석 없이 움직일 수 있게 만드는 것이다.

이 계획은 아래 여섯 가지를 닫는다.

1. `foms/platform/blueprints.py`를 기준으로 현재 등록된 blueprint surface를 **bounded context map**으로 고정한다.
2. 각 blueprint surface를 `canonical alias shim / thin adapter / mixed owner / legacy owner` 중 하나로 분류한다.
3. `docs/specs/...rebaseline_SPEC.md` §2.3 canonical/bridge 표와 live registry 사이의 차이를 **문서 우선**으로 reconcile한다.
4. 신규 route는 `foms/web` / `foms/api` 우선, `apps/`는 thin adapter role이라는 운영 규칙을 **실행 문서 수준으로 고정**한다.
5. FR20 local `README.md`를 어디에 하나만 둘지에 대한 **anchor 규칙**을 정한다.
6. 다음 LLM이 `W2-B1`부터 바로 실행할 수 있도록 batch order, freeze, verification, stop condition, run record contract를 제공한다.

### 1.2 기능 요구사항
1. Wave 2의 truth source는 항상 `foms/platform/blueprints.py`다. 추정, 기억, 옛 spec이 아니라 **실제 등록 상태**가 먼저다.
2. 각 registered blueprint 또는 runtime binding은 반드시 하나의 bounded context lane에 속해야 한다.
3. 각 surface는 반드시 아래 네 상태 중 하나로 분류해야 한다.
   - `canonical alias shim`
   - `thin adapter`
   - `mixed owner`
   - `legacy owner`
4. `apps/`에 남아 있는 live route logic을 "이미 thin adapter"라고 과장해서 기록하면 안 된다.
5. 신규 route surface는 기본적으로 `foms/web/*` 또는 `foms/api/*`에서 시작해야 하며, `apps/`는 compatibility / adapter layer로만 다뤄야 한다.
6. Wave 2는 **문서 truth 고정 → registry clarity → adapter contract → README coverage → Wave 3 handoff** 순서를 바꾸지 않는다.
7. blueprint name, `url_prefix`, registration order, root app exported binding(`get_user_by_id`, `register_chat_socketio_handlers`)은 runtime contract로 본다.
8. Wave 2에서는 context map / bridge debt / adapter matrix / README anchor를 기록하되, 불필요한 sibling inventory 문서를 늘리지 않는다. 각 batch 산출물은 **지정된 run record 내부 section**에만 남긴다.
9. 구조 변경과 기능 변경을 섞지 않는다. route behavior, response shape, DB/Alembic, template/static 물리 이동은 Wave 2 범위 밖이다.
10. 이 문서만 읽어도 future LLM이 "지금 어떤 blueprint가 live owner인지, 어떤 것은 이미 canonical slice가 있는지, 어디까지가 Wave 2 허용 범위인지"를 바로 판단할 수 있어야 한다.

### 1.3 Out of scope / freeze
Wave 2에서는 아래를 건드리지 않는다.

- blueprint route behavior 변경
- API response shape 변경
- blueprint rename, `url_prefix` 변경, registration order 변경
- `templates/` / `static/` physical relocation
- DB schema 변경, Alembic revision 추가, persistence lifecycle 재설계
- Measurement / Orders 외 context의 실제 canonical migration 실행
- WDCalculator decomposition / merge 실행
- `app.py`, `run.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `alembic.ini`
- `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py`

Wave 2는 **truth mapping / contract freezing / clarity hardening**까지만 담당한다. 실제 API canonicalization은 Wave 3, page slice migration은 Wave 4, front-end island rebaseline은 Wave 5에서 다룬다.

## 2. Current Registry Truth — 현재 blueprint truth

### 2.1 Live truth source와 registry order 불변 규칙
현재 Flask app의 blueprint 등록 truth source는 `foms/platform/blueprints.py`의 `register_blueprints(app)` 하나다.

Wave 2에서 먼저 고정해야 하는 사실:

1. root app이 실제로 노출해야 하는 runtime binding은 `BlueprintBindings` 두 항목이다.
   - `get_user_by_id`
   - `register_chat_socketio_handlers`
2. `app.register_blueprint(...)` 호출 순서는 현재 runtime order contract다.
3. import 위치와 register 위치는 가독성 향상을 위해 정렬할 수 있어도, **순서 자체는 바꾸지 않는다.**
4. 어떤 context가 이미 `foms/*` canonical slice를 가졌더라도, registry가 여전히 `apps.*` path를 import하면 Wave 2 문서에는 그 사실을 그대로 적어야 한다.

### 2.2 Ownership 상태 분류 모델
Wave 2에서는 모든 blueprint surface를 아래 네 상태 중 하나로만 기록한다.

| 상태 | 정의 | 예시 |
|------|------|------|
| `canonical alias shim` | `apps.*` module이 사실상 `foms.*` canonical implementation만 가리키는 상태. re-export, import alias, module replacement(`sys.modules[...] = canonical`)를 모두 포함한다. | `apps.erp_measurement_dashboard`, `apps.api.erp_measurement` |
| `thin adapter` | blueprint와 route shell은 `apps.*`에 남아 있지만 실제 응답/정책 실행은 canonical `foms.*` helper에 위임하는 상태 | `apps.api.orders` |
| `mixed owner` | route surface는 `apps.*`가 live owner인데, 내부 일부 helper/service delegation 또는 internal subpackage split이 존재하는 상태 | `apps.api.attachments`, 일부 ERP API lane |
| `legacy owner` | route/blueprint contract와 주요 실행 로직이 아직 `apps.*`에 남아 있는 상태 | `apps.auth`, `apps.erp`, `apps.api.channel_*`, `apps.api.wdcalculator` |

보충 규칙:

- `mixed owner`는 "절반 이전 완료"가 아니라 **아직 live owner가 `apps/`인 상태**다.
- `canonical alias shim`과 `thin adapter`만이 Wave 3 확장의 직접 선례가 된다.
- `legacy owner` surface를 문서상에서 억지로 canonical로 승격시키지 않는다.
- module 상단의 import/wrapper 흔적보다 **모듈 전체 실행 후 최종 export되는 effective symbol**이 owner 판정의 기준이다.

#### 2.2.1 Naming normalization rule
Wave 2에서는 아래 세 이름을 항상 함께 기록한다.

- `registry lane`: `blueprints.py` register 순서를 읽기 위한 운영 grouping
- `spec domain`: controlling spec `§2.3` row 이름
- `FR20 context key`: README anchor 판정을 위한 단일 key

기본 규칙:

1. `W2-B1` run record의 각 surface row는 최소 `registry lane -> spec domain -> FR20 context key`를 함께 가진다.
2. lane이 둘 이상이어도 같은 spec domain이면 동일 `FR20 context key`를 공유할 수 있다.
3. README와 bridge debt는 lane이 아니라 **`FR20 context key`** 기준으로 닫는다.
4. 이 매핑이 없으면 B2/B5를 진행하지 않는다.

### 2.3 현재 bounded context registry snapshot
주의:

- 아래 표는 **plan 작성 시점의 illustrative snapshot**이다.
- authoritative source는 언제나 `foms/platform/blueprints.py`이며, **`W2-B1` run record가 이 표를 supersede**한다.
- future LLM은 이 표를 그대로 복사해 inventory처럼 쓰면 안 되고, `W2-B1`에서 다시 line-by-line로 추출해야 한다.
- `W2-B1` run record에는 반드시 **`this plan §2.3 snapshot 대비 변경된 row`**와 **surface별 evidence field**를 남긴다.
- 이 표는 orientation용 historical snapshot이며, W2-B1 이후에도 authoritative live map으로 갱신하지 않는다. authoritative truth는 controlling spec + `W2-B1/B2` run record다.

현재 `register_blueprints(app)`를 context lane 기준으로 다시 읽으면 아래와 같다.

| Context lane | Registered surface | 현재 상태 | Wave 2 해석 | 향후 canonical target |
|------|------|------|------|------|
| Auth / session bootstrap | `apps.auth.auth_bp` + `get_user_by_id` binding | `legacy owner` | auth는 아직 overlay live owner다. binding contract를 먼저 명시한다. | `foms/web/auth`, `foms/api/auth`, `foms/services/auth` |
| ERP shell / landing / history | `apps.erp`, `apps.erp_dashboard`, `apps.erp_history_page` | `legacy owner` | page slice migration 전 단계. registry map에 live owner로 남긴다. | `foms/web/*` matching contexts |
| Measurement page/API | `apps.erp_measurement_dashboard`, `apps.api.erp_measurement` | `canonical alias shim` | Measurement는 현재 가장 명확한 canonical precedent다. | `foms/web/measurement`, `foms/api/measurement`, `foms/services/measurement` |
| Measurement map companion | `apps.api.erp_map` | `legacy owner` | measurement와 인접하지만 아직 live map owner는 `apps.api.erp_map`이다. | `foms/api/measurement_map` or `foms/api/measurement/*` family |
| Orders API | `apps.api.orders` | `thin adapter` | route shell은 overlay, canonical helpers는 `foms.api.orders.*`에 있다. 다만 이 표는 provisional이며 `W2-B1` evidence로 재확인한다. | `foms/api/orders`, 이후 `foms/web/orders`, `foms/services/orders` |
| Orders / calendar / edit / trash / excel | `apps.order_pages`, `apps.order_edit`, `apps.order_trash`, `apps.excel_import`, `apps.calendar_page` | `legacy owner` | page/UI surface는 아직 overlay owner다. Orders 전체 canonicalization이 끝난 상태가 아니다. | `foms/web/orders`, `foms/services/orders` |
| Shipment / Drawing / Production / Construction / AS / Completion pages | `apps.erp_shipment_page`, `apps.erp_drawing_workbench`, `apps.erp_as_page`, `apps.erp_production_page`, `apps.erp_construction_page`, `apps.erp_completion_page` | `legacy owner` | page slice migration 대상군. Wave 2에서는 truth만 고정한다. | 각 context별 `foms/web/*` |
| ERP stage/order mutation APIs | `apps.api.erp_shipment_settings`, `apps.api.erp_orders_*`, `apps.api.personal_board`, `apps.api.erp_estimates` | `legacy owner` or `mixed owner` | service delegation이 있더라도 blueprint/API contract owner는 대부분 `apps.api.*`다. | 각 context별 `foms/api/*`, `foms/services/*` |
| Files / address / notifications | `apps.api.files`, `apps.api.address`, `apps.api.notifications` | `legacy owner` | API-first context지만 아직 overlay live owner다. | `foms/api/files`, `foms/api/address`, `foms/api/notifications` |
| Attachments / tasks / events / quest / backup / debug | `apps.api.attachments`, `apps.api.tasks`, `apps.api.events`, `apps.api.quest`, `apps.api.backup`, `apps.api.debug` | `legacy owner` or `mixed owner` | 특히 `apps.api.attachments`는 internal split 흔적이 있어도 registered blueprint 관점에서는 live owner 판정을 다시 확인해야 한다. | matching `foms/api/*`, `foms/services/*` |
| Admin / user / dashboards / storage / planner | `apps.admin`, `apps.user_pages`, `apps.dashboards`, `apps.storage_dashboard`, `apps.wdplanner_page` | `legacy owner` | page/admin lane는 아직 overlay owner다. | `foms/web/admin`, `foms/web/*` |
| Chat + realtime binding | `apps.api.chat.chat_bp` + `register_chat_socketio_handlers` | `legacy owner` | HTTP blueprint와 realtime binding을 같이 가진 특수 lane이다. | `foms/api/chat`, `foms/platform/realtime` alignment |
| Channel integration / functions / webhooks / WAM | `apps.api.channel_integration`, `apps.api.channel_functions`, `apps.api.channel_webhooks`, `apps.api.channel_wam` (4 modules / 6 register calls, `channel_wam` contributes 3 blueprints) | `legacy owner` or `mixed owner` | service delegation이 많아도 route/API contract owner는 여전히 overlay다. | `foms/api/channel`, `foms/services/channel` |
| WDCalculator | `apps.api.wdcalculator` | `legacy owner` | Wave 5 전까지는 owner truth만 고정한다. | `foms/web/wdcalculator`, `foms/api/wdcalculator`, `foms/services/wdcalculator` |

### 2.4 현재 즉시 잠가야 하는 drift risk
Wave 2에서 먼저 차단해야 하는 drift는 아래와 같다.

1. `apps/` route surface 중 일부만 canonical precedent를 가졌는데, 나머지까지 같은 수준으로 오인하는 것
2. `apps.*` 내부에 internal split 또는 service delegation이 있다고 해서 thin adapter로 잘못 기록하는 것
3. registry order 정리 명목으로 blueprint 호출 순서를 바꾸는 것
4. `blueprint name`, `url_prefix`, root binding export를 문서 없이 바꾸는 것
5. FR20 local `README.md`가 없어서 AI/human entrypoint가 계속 registry 파일과 흩어진 modules를 왕복하게 되는 것
6. top-level shim/import 흔적이 live blueprint owner를 가리는 surface를 `mixed owner`로 과대평가하는 것

## 3. Fixed Execution Pipeline — 고정 실행 순서

Wave 2 **전체**는 아래 순서를 지킨다. 각 batch는 이 순서 중 **자신에게 배정된 subset만** 수행하며, 실제 batch 경계는 `§4`, `§5` runbook이 우선한다.

명시 규칙:

- `W2-B1`이 끝나기 전에는 step 3(spec reconcile) 이후 단계로 넘어가지 않는다.
- `W2-B2`가 끝나기 전에는 registry clarity(`W2-B3`)나 adapter contract freeze(`W2-B4`)를 실행하지 않는다.
- `W2-B5`는 latest Wave 1 `src/` classification을 다시 확인한 뒤에만 진행한다.

1. live registry snapshot 확인
2. surface ownership 상태 분류
3. `spec §2.3`와 live truth reconcile
4. docs truth를 먼저 갱신
5. 필요할 때만 minimal registry clarity code edit
6. `apps/` thin-adapter contract / README anchor 고정
7. verification + run record 작성

추가 규칙:

- 한 batch는 반드시 **한 risk axis만** 다룬다.
- docs batch와 code clarity batch를 섞지 않는다.
- `foms/platform/blueprints.py` 수정 batch에서도 route logic, behavior, naming, order는 바꾸지 않는다.
- live owner가 아닌 척 기록하지 않는다. "아직 `apps/` owner"면 그렇게 적는다.
- 새 route를 추가해야 하는 future feature batch가 생기면, 먼저 `foms/web` / `foms/api`에 넣고, 필요한 compatibility surface만 `apps/`에서 잇는다.
- Wave 2는 새 generic bucket을 만들지 않는다. context 이름이 있으면 그대로 `foms/<layer>/<context>`를 따른다.
- `bridge debt register`와 `adapter matrix`는 별도 sibling 문서가 아니라, 지정된 각 batch run record 안의 단일 section/table로만 남긴다.

## 4. Wave 2 Batch Catalog — LLM 실행 순서

### 4.1 Batch table
| Batch ID | 이름 | Risk axis | 주 결과물 | 선행 조건 | 필수 run record |
|------|------|------|------|------|------|
| W2-B1 | Blueprint truth extraction + bounded context map v1 | docs / owner mapping | live registry 기반 context map v1 | Wave 1 진행 중이어도 독립 실행 가능 | `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` |
| W2-B2 | Spec-live reconciliation + bridge debt register | governance / docs | `spec §2.3` 보정, bridge debt register | W2-B1 | `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md` |
| W2-B3 | Blueprint registry clarity hardening | platform structure clarity | `blueprints.py` section comments / clarity 강화 | W2-B2 | `docs/plans/2026-04-13-wave2-batch3-blueprint-registry-clarity-run-record.md` |
| W2-B4 | `apps/` thin-adapter contract freeze | overlay contract | adapter matrix, module header clarity | W2-B3 | `docs/plans/2026-04-13-wave2-batch4-apps-thin-adapter-contract-run-record.md` |
| W2-B5 | FR20 README coverage pass | AI/human entrypoint docs | README anchor rule + actual coverage 최소 확보 | W2-B4 | `docs/plans/2026-04-13-wave2-batch5-readme-coverage-run-record.md` |
| W2-B6 | Wave 2 closeout + Wave 3 handoff | verification / handoff | 잔여 live owner와 Wave 3 우선순위 고정 | W2-B5 | `docs/plans/2026-04-13-wave2-batch6-closeout-run-record.md` |

### 4.2 Batch별 기본 원칙
- `W2-B1`, `W2-B2`는 **docs-first**다.
- `W2-B3`는 주된 code-touch batch이며, 그 범위는 `foms/platform/blueprints.py` clarity에 한정한다.
- `W2-B4`는 `apps/`를 다 thin adapter로 바꾸는 batch가 아니라, **현재 thin adapter와 아닌 것을 구분해 계약으로 고정하는 batch**다.
- `W2-B4`는 예외적으로 이미 확인된 alias/thin adapter surface에 한해 `apps/*` module top-level docstring 정규화를 허용할 수 있지만, route logic이나 import wiring은 건드리지 않는다.
- `W2-B2`의 bridge debt register는 **migration intent / unblock condition**을 남기는 표이고, `W2-B4`의 adapter matrix는 **현재 contract label freeze**를 남기는 표다. 둘은 역할이 다르며 서로를 대체하지 않는다.
- `W2-B5`는 README를 무한 증식시키는 batch가 아니라, FR20에 맞는 **single-anchor README 규칙**을 적용하는 batch다.
- `W2-B6`는 새 구조 변경 없이 closeout/handoff만 남긴다.

## 5. Batch Runbooks — 각 배치의 실제 실행법

### 5.1 W2-B1 — Blueprint truth extraction + bounded context map v1
**목표**
- 현재 live registry를 bounded context map v1로 고정한다.
- surface별 ownership 상태를 처음으로 explicit하게 분류한다.

**허용 변경**
- `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md`

**금지 변경**
- `foms/platform/blueprints.py`
- `apps/*`, `foms/*` runtime code
- registration order 관련 수정
- controlling spec 수정

**실행 단계**
1. `foms/platform/blueprints.py`를 source of truth로 읽는다.
2. `app.register_blueprint(...)` 순서를 lane 단위로 다시 그룹화한다.
3. 각 surface에 대해 다음 다섯 필드를 기록한다.
   - module path
   - blueprint symbol
   - lane / bounded context
   - spec domain / FR20 context key
   - current owner state
   - future canonical target
4. 각 surface에는 최소 한 줄의 evidence field를 남긴다.
   - alias / module-replacement shim 근거
   - canonical helper delegation 근거
   - live owner 근거
   - 동일 module 안에 같은 blueprint symbol이 여러 번 보이면 최종 export되는 effective symbol 기준 판정
5. `this plan §2.3` illustrative table과 다른 row가 있으면 `this plan §2.3 snapshot 대비 변경된 row` section에 남긴다.
6. `get_user_by_id`, `register_chat_socketio_handlers` 같은 non-blueprint runtime binding도 별도 표로 기록한다.
7. Measurement / Orders를 precedent lane으로 분리 표시한다.
8. 이 문서 안의 `erp_orders_*` 같은 shorthand는 run record에서 반드시 concrete module/symbol로 풀어쓴다.
9. `registry lane -> spec domain -> FR20 context key` normalization이 없는 row는 완료로 간주하지 않는다.
10. 결과를 `W2-B1` run record 하나에 남긴다. 별도 inventory sibling 문서는 만들지 않는다.

**산출물**
- `W2-B1` run record 1개
- context map table
- unresolved surface list
- `this plan §2.3 snapshot 대비 변경된 row` section

**검증**
- docs-only batch인지 확인
- run record 안의 모든 surface가 네 상태 중 하나로 분류됐는지 확인
- 모든 surface row에 evidence field가 있는지 확인
- "Measurement/Orders 외 surface를 thin adapter로 잘못 승격"한 항목이 없는지 확인

### 5.2 W2-B2 — Spec-live reconciliation + bridge debt register
**목표**
- `spec §2.3` canonical/bridge 표와 live registry truth 사이의 차이를 문서상에서 먼저 닫는다.
- bridge debt register를 만든다.

**허용 변경**
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
- `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md`

**금지 변경**
- runtime code
- `foms/platform/blueprints.py`
- route/module move

**실행 단계**
1. `W2-B1` context map과 `spec §2.3`, Wave 2 문구를 나란히 비교한다.
2. spec이 live truth보다 앞서 나간 표현이 있으면, "future canonical target"과 "current bridge/live owner"를 더 정확히 적는다.
3. 특히 controlling spec `§2.3`의 Orders 행은 domain-level 요약이며, registry의 `apps.api.erp_orders_*`, `apps.api.erp_orders_blueprint`, `apps.api.erp_orders_structured` 같은 surface는 같은 도메인이라도 물리 경로 패턴이 다를 수 있다는 점을 명시한다.
4. controlling spec `§2.3`의 Orders 행은 domain-level 요약이고, surface-level 분류는 `W2-B1/B2` bridge debt register가 우선한다는 점을 명시한다.
5. `bridge debt register`를 **`W2-B2` run record 안에만** 만든다. 별도 sibling 문서를 만들지 않는다. 각 row는 최소 아래를 포함한다.
   - surface
   - current owner state
   - canonical target
   - next intended wave
   - why not thin adapter yet
   - unblock condition (필요 시)
6. `apps/` thin adapter role 문구는 유지하되, **현재 thin adapter가 아닌 surface는 debt로 남긴다.**
7. controlling spec의 Wave 2 문구에서 말하는 "`apps/`는 thin adapter role로 고정"은 **existing `apps/*` 전체가 이미 thin adapter라는 주장**이 아니라, 신규 구조 작업의 operational default라는 점을 보강한다.
8. 이 실행 계획서의 `§2.3` illustrative table은 B2에서 최신 live map으로 다시 채우지 않고, authoritative 결과는 controlling spec + `W2-B2` run record에만 남긴다.
9. Wave 2 reference list 연결은 **controlling spec `§5 참고 자료`**를 target으로 한다. `docs/ARCHIVE_INDEX.md` 갱신은 `W2-B6` closeout에서 수행한다.
10. bridge debt register row에는 이후 `W2-B4` adapter matrix가 참조할 row id를 부여한다.

**산출물**
- spec/live reconcile 결과
- `bridge debt register` section inside `W2-B2` run record
- `W2-B2` run record 1개

**검증**
- spec 표현이 live registry를 부정하지 않는지 확인
- 새로운 future canonical target이 기존 controlling spec `§2.3` naming과 충돌하지 않는지 확인
- debt register의 모든 row가 `owner state` 또는 `TBD + 이유 + unblock condition`을 갖는지 확인

### 5.3 W2-B3 — Blueprint registry clarity hardening
**목표**
- `foms/platform/blueprints.py`를 future reader가 lane/context 기준으로 읽기 쉽게 만든다.
- 단, behavior는 절대 바꾸지 않는다.

**허용 변경**
- `foms/platform/blueprints.py`
- `docs/plans/2026-04-13-wave2-batch3-blueprint-registry-clarity-run-record.md`

**금지 변경**
- `app.register_blueprint(...)` 호출 순서 변경
- blueprint import path 변경
- blueprint symbol rename
- `url_prefix`, blueprint name, behavior 변경
- `apps/*` route logic 수정

**실행 단계**
1. 현재 import/register order를 기준선으로 고정한다.
2. 허용 범위는 comment / blank line / section header / docstring clarity 추가뿐이다.
3. import 줄 순서와 register 호출 순서는 유지한 채 lane 또는 context grouping comment/docstring을 추가해 reader가 registry를 위에서 아래로 읽을 수 있게 만든다.
4. `BlueprintBindings`가 왜 runtime contract인지 설명을 보강한다.
5. import/register block이 너무 멀리 떨어져 가독성이 나빠지면, **순서를 유지한 채** comment-only clarity를 먼저 택한다.
6. register order diff가 조금이라도 생기면 batch를 중단한다.

**산출물**
- clearer `foms/platform/blueprints.py`
- `W2-B3` run record 1개

**검증**
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -c "from foms.platform.blueprints import register_blueprints; print('BLUEPRINTS_OK')"`
- diff에서 register order / imported symbol set이 바뀌지 않았는지 확인

### 5.4 W2-B4 — `apps/` thin-adapter contract freeze
**목표**
- 어떤 `apps/*` surface가 실제 thin adapter인지, 어떤 것은 아직 live owner인지 계약으로 고정한다.
- future Wave 3~4가 잘못된 전제를 쓰지 않게 만든다.

**허용 변경**
- `docs/plans/*` run record
- 필요 시 이미 thin adapter 또는 alias shim으로 확인된 `apps/*` module의 top-level docstring 정규화

**금지 변경**
- route logic 이동
- import rewiring
- 새 wrapper 파일 추가
- legacy owner surface를 억지로 thin adapter로 바꾸는 구조 작업

**실행 단계**
1. `W2-B1`, `W2-B2` 결과를 기준으로 adapter matrix를 **`W2-B4` run record 안에만** 만든다.
2. surface를 아래 네 계약 중 하나로 다시 적는다.
   - alias shim
   - thin adapter
   - mixed owner
   - legacy owner
3. 이미 alias shim/thin adapter로 확인된 module만 docstring metadata를 정규화한다.
4. mixed/legacy owner에는 "canonical target"과 "retirement wave"만 남기고, 구조 축소는 Wave 3~4로 미룬다.
5. adapter matrix는 `W2-B2` bridge debt register row id를 참조하고, owner/canonical narrative를 새로 복제하지 않는다.
6. `apps/`에 새 route를 만드는 future batch는 예외 사유와 adapter justification 없이는 진행할 수 없다는 rule을 남긴다.

**산출물**
- adapter matrix section inside `W2-B4` run record
- 선택된 module header clarity 보강
- `W2-B4` run record 1개

**검증**
- touched `apps/*` module이 있다면 `APP_OK` 재검증
- "thin adapter" label을 단 모든 surface가 실제로 canonical helper 또는 alias target을 갖는지 확인
- mixed/legacy owner row가 삭제되지 않았는지 확인

### 5.5 W2-B5 — FR20 README coverage pass
**목표**
- controlling spec FR20, 즉 **runtime module 3개 이상이거나 `web/api/services` 두 레이어 이상에 걸친 context에는 정확히 하나의 local `README.md`를 둔다**는 규칙을 현재 구조에 맞게 실제 적용 가능한 anchor rule로 고정한다.
- AI/human entrypoint를 최소 수준으로라도 확보한다.

**허용 변경**
- `foms/README.md`
- context local `README.md`
- 관련 spec/plan reference
- `W2-B5` run record

**금지 변경**
- 같은 context에 README를 여러 개 만드는 것
- `apps/` 아래에 context README를 증식시키는 것
- README 작성 명목의 구조 이동

**README anchor gate**
1. 먼저 B1/B2 lane과 controlling spec `§2.3` domain row를 기준으로 README candidate context를 적는다.
2. 각 candidate마다 다음 두 조건을 기계적으로 판정한다.
   - runtime module 수가 3개 이상인가
   - `web/api/services` 중 두 레이어 이상에 걸치는가
3. 둘 중 하나라도 만족하면 FR20 candidate다.
4. 둘 다 만족하지 않으면 README를 만들지 않고 defer 이유를 남긴다.

**README anchor ladder**
1. context당 local `README.md`는 정확히 하나만 둔다.
2. 이미 존재하는 `foms/<layer>/<context>/` package directory가 있으면 그 경로를 anchor로 쓴다.
3. 둘 이상의 existing package directory가 candidate면 다음 tie-break를 적용한다.
   - page-first public entry context면 `foms/web/<context>/`
   - API-first public entry context면 `foms/api/<context>/`
   - 그래도 모호하면 생성하지 말고 defer한다.
4. 같은 context의 다른 layer/file module은 그 README에서 sibling surface로 설명한다.
5. anchor 후보 디렉터리가 전혀 없으면, 새 package root를 만들지 말고 `deferred anchor path + reopen wave`를 run record에 남긴다.
6. docs-only batch에서 허용되는 것은 **기존 경로 안의 `README.md` 추가**뿐이며, 새 디렉터리 생성은 허용하지 않는다.

**README 역할 분리**
- root `README.md`: 저장소 전체 onboarding / setup / governance entrypoint
- `foms/README.md`: product namespace / bounded-context navigation entrypoint
- `src/README.md`가 있더라도 Wave 1 분류 결과의 tooling/non-product note로 취급하며, FR20 context anchor 후보로 보지 않는다.

**초기 적용 기본값 (pre-W2-B5에는 아직 존재하지 않는 target anchors)**
- global entrypoint: `foms/README.md`
- Measurement anchor candidate: `foms/web/measurement/README.md`
- Orders anchor candidate: `foms/api/orders/README.md`

**실행 단계**
1. latest Wave 1 closeout 또는 `src/` classification record를 다시 읽어 `src/README.md`가 tooling/non-product note라는 점을 재확인한다.
2. FR20 대상 context를 다시 판정한다.
3. README를 지금 만들 context와 defer할 context를 나눈다.
4. 지금 만들 context는 single-anchor rule로 생성한다.
5. defer context는 anchor path와 reopen wave를 run record에 남긴다.

**산출물**
- `foms/README.md` 및 필요한 최소 local `README.md`
- defer anchor table
- `W2-B5` run record 1개

**검증**
- 한 context에 README가 두 개 생기지 않았는지 확인
- README가 현재 canonical surface와 금지 의존성을 적고 있는지 확인
- docs-only 또는 docs-primary batch 범위를 넘지 않았는지 확인

### 5.6 W2-B6 — Wave 2 closeout + Wave 3 handoff
**목표**
- Wave 2 결과를 요약하고 Wave 3 API canonicalization의 시작점을 닫는다.

**허용 변경**
- closeout run record
- `docs/ARCHIVE_INDEX.md`
- 필요 시 spec/plan reference section

**금지 변경**
- 새 structure change
- runtime code edit

**실행 단계**
1. Wave 2 batch 결과를 요약한다.
2. 남아 있는 `legacy owner` / `mixed owner` surface를 Wave 3 우선순위로 정렬한다.
3. Orders precedent를 어디에 먼저 확장할지 1차 후보를 남긴다. 이 shortlist는 **API lane만** 대상으로 하며, page/template/JS slice는 Wave 4 대상으로 유지한다.
4. README coverage와 unresolved debt를 함께 기록한다.
5. archive/spec reference를 final sync한다.
6. Wave 3는 API canonicalization implementation work, Wave 4는 page/template/JS slice work이며, `W2-B6`은 우선순위와 debt만 남기고 implementation을 시작하지 않는다고 명시한다.

**산출물**
- `W2-B6` closeout run record
- Wave 3 first-target shortlist

**검증**
- 모든 W2 run record가 존재하는지 확인
- spec / archive / execution plan reference가 서로 연결돼 있는지 확인
- 미완료 debt가 숨겨지지 않고 남아 있는지 확인

## 6. Verification Matrix — 검증 기준

### 6.1 Docs-only batch 공통
- runtime code file이 touched되지 않았는지 확인
- spec / plan / run record 간 용어 불일치가 없는지 확인
- context state label이 네 분류 밖으로 새로 생기지 않았는지 확인

### 6.2 Code-touch batch (`W2-B3`, 일부 `W2-B4`)
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `ReadLints`로 touched file diagnostics 확인 (IDE 환경일 때만 보조적으로 사용)
- diff에서 behavior/naming/order drift가 없는지 확인

### 6.3 README batch (`W2-B5`)
- README anchor 중복이 없는지 확인
- README 안에 최소 아래 네 항목이 있는지 확인
  - 목적
  - 주요 모듈
  - 읽기 순서
  - 금지 의존성 / 아직 overlay인 surface

## 7. Run Record Contract — 각 실행 기록에 반드시 남길 것

### 7.1 Run record 최소 필드
모든 Wave 2 run record는 최소 아래를 포함한다.

- batch id
- touched files
- risk axis
- live truth source
- context lanes affected
- state label delta
- evidence summary
- canonical target
- retirement / reopen wave
- verification result
- residual risk

### 7.2 Wave 2 Direction Lock 질문
모든 run record는 아래 질문에 답해야 한다.

1. 이 batch는 `foms/platform/blueprints.py`를 live truth source로 사용했는가?
2. live owner surface를 thin adapter/canonical로 과장하지 않았는가?
3. `apps/`에 새 장기 route logic을 추가하지 않았는가?
4. blueprint name / `url_prefix` / registration order / runtime binding contract를 유지했는가?
5. spec과 live truth가 충돌하면 code보다 docs truth를 먼저 고쳤는가?
6. context별 canonical target이 controlling spec `§2.3` naming과 충돌하지 않는가?
7. README를 만들었다면 context당 하나만 두었는가?
8. README를 미뤘다면 anchor path와 reopen wave를 남겼는가?
9. 다음 LLM이 이 run record만 읽어도 owner state를 오해하지 않겠는가?
10. 이 batch 결과가 Wave 3의 API canonicalization을 더 쉽게 만드는가?

## 8. Stop Conditions — 즉시 중단 조건
다음 중 하나라도 발생하면 Wave 2 구조 작업을 즉시 중단하고 별도 spec/ADR 또는 더 작은 batch로 분리한다.

- `blueprints.py` register order를 바꿔야 한다는 요구가 생길 때
- blueprint rename 또는 `url_prefix` 변경이 필요해질 때
- route behavior/API shape/DB schema 변경이 끼어들 때
- `apps/` live owner surface를 문서상에서 억지로 thin adapter로 승격시키려 할 때
- README anchor를 하나로 못 정해 context당 README가 둘 이상 필요해질 때
- Measurement / Orders precedent를 일반화하는 과정에서 다른 context 실코드 migration이 같이 섞일 때
- product tree와 quarantine / non-product import 문제가 새로 드러날 때

## 9. First LLM Turn — 바로 실행할 다음 배치

다음 batch는 **`W2-B1`**이다.

### 9.1 Scope lock
- 읽을 것: `foms/platform/blueprints.py`, `foms/platform/app_factory.py`, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`, `docs/plans/2026-04-10-step5-measurement-vertical-slice-plan.md`, `docs/plans/2026-04-11-orders-boundary-decomposition-plan.md`
- 수정할 것: `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` 중심 docs only
- 수정하지 말 것: runtime code, registry file, `apps/*`, template/static, DB/Alembic

### 9.2 Prompt-ready contract
아래 조건으로 바로 실행한다.

1. `foms/platform/blueprints.py`를 live registry source of truth로 읽는다.
2. 모든 registered blueprint와 runtime binding을 bounded context lane으로 분류한다.
3. 각 surface를 `canonical alias shim / thin adapter / mixed owner / legacy owner` 중 하나로만 기록한다.
4. Measurement와 Orders만 canonical precedent로 취급하고, 나머지는 실제 상태를 과장하지 않는다.
5. 결과를 `docs/plans/2026-04-13-wave2-batch1-blueprint-truth-map-run-record.md` 하나에 남긴다.
6. 새 sibling inventory 문서는 만들지 않는다.
7. 각 surface row에는 evidence field를 남긴다.
8. `this plan §2.3` illustrative table과 다른 판단이 나오면 `this plan §2.3 snapshot 대비 변경된 row` section에 적는다.
9. 최종 출력에는 `context map summary`, `unresolved surfaces`, `W2-B2에서 reconcile해야 할 spec drift` 세 항목을 포함한다.

## 10. Definition of Done — Wave 2 완료 판정
Wave 2는 아래가 모두 충족될 때 완료다.

- live registry 기준 bounded context map이 존재한다
- `spec §2.3`와 live registry 관계가 과장 없이 다시 적혀 있다
- `apps/` thin-adapter contract가 surface별 상태와 함께 고정됐다
- `blueprints.py`가 future reader 기준으로 lane/context를 읽기 쉬운 상태가 됐다
- FR20 README anchor rule이 정해졌고, 최소 필요한 entrypoint README가 생겼다
- Wave 3 first-target shortlist가 closeout에 남아 있다
- spec / execution plan / archive index가 서로 연결돼 있다
