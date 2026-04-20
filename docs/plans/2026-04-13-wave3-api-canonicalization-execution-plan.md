# Wave 3 API Canonicalization Execution Plan
> 작성일: 2026-04-13 | 상태: 실행 준비 완료 (LLM batch-ready)
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> live truth source: `foms/platform/blueprints.py`
> 선행 wave: `docs/plans/2026-04-13-wave2-bounded-context-map-blueprint-clarity-execution-plan.md`
> 구조 선례: `docs/plans/2026-04-11-orders-boundary-decomposition-plan.md`, `docs/plans/2026-04-10-step5-measurement-vertical-slice-plan.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
이 문서는 `FOMS Modular Monolith Rebaseline Spec`의 **Wave 3 — API canonicalization**을 바로 실행할 수 있는 LLM용 runbook이다.

Wave 3의 목적은 "API도 언젠가 `foms/`로 옮기자" 수준의 선언이 아니라, 아래 다섯 가지를 기계적으로 닫는 것이다.

1. 현재 `apps/api/*` live owner surface를 **risk-tiered queue**로 잠근다.
2. Orders에서 검증한 `apps/api` thin wrapper + `foms/api/<context>` canonical helper 패턴을 **저위험 API context부터** 확장한다.
3. route path, blueprint name, decorator order, response shape, registration path 같은 **공개 계약**을 먼저 freeze한다.
4. hidden side effect가 있는 surface는 먼저 분리/기록하고, 준비되지 않은 context는 **억지 이전하지 않고 defer**한다.
5. Wave 4(page/template/static)와 Wave 5(WDCalculator giant front-end)로 책임이 새지 않도록 **API-only boundary**를 잠근다.

### 1.2 기능 요구사항
1. Wave 3의 authoritative truth는 항상 `foms/platform/blueprints.py`와 Wave 2 authoritative run record다.
2. Wave 2 plan 본문의 illustrative 표를 다시 truth source로 승격하면 안 된다.
3. 한 batch는 반드시 **한 context / 한 risk axis**만 다룬다.
4. canonical move 전에 반드시 해당 context의 **public contract + hidden side effect inventory**를 먼저 freeze한다.
5. 기본 우선순위는 `read-heavy / low-risk / API-first / no realtime binding` surface다.
6. `apps/api/*`에서 `foms/api/*`로 옮길 때도 route path, methods, blueprint name, `url_prefix`, decorator order, response shape는 기본 freeze다.
7. blueprint registration order, import entry path, root runtime binding은 Wave 3에서 바꾸지 않는다.
8. 새 shim/adapter가 필요하면 같은 batch run record 안에 최소 `canonical target / retirement wave / removal condition`을 남겨야 한다.
9. canonicalization 과정에서 새 sibling inventory 문서를 늘리지 않는다. queue, contract, defer register는 각 batch run record 안의 단일 section/table로만 남긴다.
10. Wave 2 owner state(`legacy owner`, `thin adapter` 등)와 Wave 3 risk tier는 독립 축이다. 동일 context라도 owner와 risk는 별도로 판정한다.
11. service/persistence 정리는 Wave 3의 목적이 아니다. API adapter를 얇게 만들기 위한 최소 import 이동만 허용한다.
12. FR19 기준으로 기본값은 `새 canonical single module -> 필요 시 package`다. 여러 file/package로 나누려면 run record에 merge-back/why-not-single-module 판단을 남겨야 한다.
13. FR20 local `README.md`는 Wave 2 anchor 규칙을 그대로 따른다. Wave 3에서 새 README가 필요하면 `FR20 context key` 기준으로만 하나 둔다.
14. 테스트는 기존 domain/API contract를 확장하는 것을 우선한다. 새 micro test/support pair는 같은 batch justification 없이는 만들지 않는다.
15. `attachments`, `chat`, `channel_*`, `backup`, `quest` 같이 side-effect-heavy surface는 준비 조건이 충족되기 전까지 defer 가능해야 하며, defer 자체가 실패가 아니라 올바른 결과다.

### 1.3 Out of scope / freeze
Wave 3에서는 아래를 건드리지 않는다.

- `foms/platform/blueprints.py`의 registration order, blueprint import path, root runtime binding
- `app.py`, `run.py`, `start.sh`, `Procfile`, `railway*.toml`, `Dockerfile`, `alembic.ini`
- page/template/static 물리 이동
- Jinja include 재구성
- DB schema 변경, Alembic revision 추가, persistence lifecycle 재설계
- Measurement/Orders 기존 precedent의 동작 변경
- WDCalculator front-end decomposition / merge
- chat realtime binding (`register_chat_socketio_handlers`) 구조 변경
- Channel webhook/function/WAM contract 변경

Wave 3은 **API contract freeze + canonical helper extraction + thin wrapper conversion**까지만 담당한다. page/UI slice migration은 Wave 4, WDCalculator giant front-end rebaseline은 Wave 5에서 다룬다.

## 2. Current API Truth — 현재 API landscape

### 2.1 선행 handoff gate
Wave 3는 Wave 2의 아래 산출물을 소비한 뒤에만 시작한다.

1. `W2-B1` truth map run record
2. `W2-B2` spec-live reconcile / bridge debt register
3. `W2-B3` registry clarity hardening run record
4. `W2-B4` adapter matrix
5. `W2-B5` FR20 README coverage run record
6. `W2-B6` closeout / Wave 3 handoff

추가 규칙:

- 위 여섯 산출물 중 하나라도 없으면 `W3-B0`는 stop한다.
- `W2-B6`가 존재하더라도 앞선 Wave 2 batch 완료를 증명하지 못하면 `equivalent evidence missing`으로 간주하고 stop한다.
- Wave 3는 Wave 2 plan 본문을 그대로 믿지 않고, **run record evidence를 우선**한다.
- Wave 2 evidence와 `blueprints.py`가 충돌하면 `blueprints.py`를 live truth로 두고, Wave 2 drift를 먼저 문서화한 뒤 queue를 다시 잠근다.
- Wave 2 owner 분류와 Wave 3 risk tier는 독립 축이며, 최종 queue/tier는 `W3-B0`에서 evidence로 다시 계산한다.

### 2.2 Risk-tier 판정 규칙
Wave 3는 API surface를 아래 네 tier로만 다룬다.

| Tier | 기준 | 허용 방식 |
|------|------|------|
| `Tier 0 precedent` | 이미 canonical alias shim 또는 thin adapter precedent가 검증된 surface | 선례로만 사용, 구조 재해석 금지 |
| `Tier 1 low-risk` | GET 위주, side effect 작음, 단일 blueprint, realtime/background coupling 없음 | early pilot 대상 |
| `Tier 2 medium-risk` | read-heavy지만 aggregation/외부 API/부분 mutation이 섞인 surface | contract freeze 후 제한적으로 진행 |
| `Tier 3 high-risk` | storage write, webhook, realtime, multi-blueprint, multi-step mutation, hidden side effect 다수 | defer 또는 contract-only batch |

보조 판정 규칙:

1. `GET` endpoint라도 presigned URL 발급, 외부 API 호출, session/notification write가 있으면 low-risk로 자동 승격하지 않는다.
2. 하나의 blueprint 안에 read route와 mutation route가 함께 있으면, **read-only 선별 가능성**을 먼저 검토하고 불가능하면 higher tier로 둔다.
3. realtime binding, webhook signature, file storage write, stage transition mutation, background task enqueue가 보이면 기본값은 `Tier 3`다.
4. "코드가 짧다"는 이유만으로 low-risk 판정을 하지 않는다. runtime contract의 폭이 더 중요하다.

### 2.3 현재 queue snapshot
주의:

- 아래 표는 **Wave 3 초안 시점의 provisional queue snapshot**이다.
- authoritative queue는 `W3-B0` run record가 supersede한다.
- future LLM은 이 표를 inventory처럼 복사하지 말고 `W3-B0`에서 evidence를 다시 적어야 한다.

| Context lane | Representative surface | 현재 관찰 | 초기 tier | Wave 3 처리 원칙 | 미래 canonical target |
|------|------|------|------|------|------|
| Precedent / Measurement | `apps.api.erp_measurement` | `apps.*` module replacement alias shim precedent | `Tier 0 precedent` | reference only | `foms/api/measurement` |
| Precedent / Orders | `apps.api.orders` | thin adapter precedent | `Tier 0 precedent` | reference only | `foms/api/orders` |
| Files | `apps.api.files` | 단일 blueprint, GET 위주지만 presigned URL/redirect/storage provider 분기 존재 | `Tier 1 low-risk` | `W3-B0` storage/presigned check 통과 시 first pilot | `foms/api/files` |
| Address | `apps.api.address` | 단일 blueprint, GET search proxy, Kakao external API read path | `Tier 1 low-risk` | second pilot 후보 | `foms/api/address` |
| Personal board | `apps.api.personal_board` | 단일 summary GET, DB aggregation/read-heavy | `Tier 2 medium-risk` | aggregate-read 후보 | `foms/api/personal_board` |
| Events | `apps.api.events` | 다수 GET read route + `POST /change-events/<event_id>/revert` mutation lane 공존 | `Tier 2 medium-risk` | read-only subset 가능성부터 점검, revert lane은 별도 취급 | `foms/api/events` |
| ERP estimates | `apps.api.erp_estimates` | GET/POST/PUT/DELETE 혼재, service delegation 존재 | `Tier 2 medium-risk` | read-vs-mutation split 가능성부터 판단 | `foms/api/erp_estimates` |
| Notifications | `apps.api.notifications` | GET list/badge 외에도 read/send/urgent-mention/bulk-delete 성격의 POST 다수 | `Tier 2 medium-risk` | write/broadcast lane 분리 전까지 backlog 우선 | `foms/api/notifications` |
| Tasks | `apps.api.tasks` | 주문 task full CRUD (`GET/POST/PUT/DELETE`) | `Tier 2 medium-risk` | CRUD contract freeze 후 후보 재평가 | `foms/api/tasks` |
| ERP map | `apps.api.erp_map` | measurement 인접 surface지만 map generation / mutator 성격 혼재 | `Tier 2~3` | read/mutator split 전까지 pilot 금지 | `foms/api/measurement_map` 또는 measurement family |
| ERP measurement mutators | `apps.api.erp_measurement` POST/PUT side | precedent는 있으나 side-effect route는 별도 주의 필요 | `Tier 2~3` | precedent lane과 mutation lane 구분 | `foms/api/measurement` |
| Stage/order mutation APIs | `apps.api.erp_orders_*` | 단계 전환/상태 변경/구조화 데이터 mutation | `Tier 3 high-risk` | Wave 3 후반 또는 defer | `foms/api/orders/*` |
| Attachments | `apps.api.attachments` + `apps.api.attachments_internal/*` | legacy wrapper + internal package가 공존하고 storage/upload/search/thumbnail/legacy auto-migration 경로가 얽힘 | `Tier 3 high-risk` | dedicated prep 없이는 contract-only/defer | `foms/api/attachments` |
| Chat | `apps.api.chat` + realtime binding | HTTP + SocketIO binding 결합 | `Tier 3 high-risk` | Wave 3 mainline에서 직접 이전 금지 | `foms/api/chat`, `foms/platform/realtime` |
| Channel integration family | `apps.api.channel_integration`, `apps.api.channel_functions`, `apps.api.channel_webhooks`, `apps.api.channel_wam` | webhook/function/WAM multi-blueprint lane | `Tier 3 high-risk` | Wave 3 defer 기본값 | `foms/api/channel`, `foms/services/channel` |
| Backup / Quest | `apps.api.backup`, `apps.api.quest` | operational mutation / workflow side effect | `Tier 3 high-risk` | contract-only or defer | `foms/api/backup`, `foms/api/quest` |
| Debug | `apps.api.debug` | operational/debug surface, product canonicalization 대상 아님 | `Tier 3 high-risk` | defer and classify explicitly | `foms/api/debug` or quarantine decision |
| WDCalculator API | `apps.api.wdcalculator` | giant front-end rebaseline와 결합 | `Tier 3 high-risk` | Wave 5 전까지 truth만 유지 | `foms/api/wdcalculator` |

### 2.4 Pilot tie-break rule
Wave 3의 first pilot은 아래 순서로 고른다.

1. `files`
2. `address`
3. `personal_board`
4. `events` read-heavy path

잠금 규칙:

- `files`가 `W3-B0` evidence에서 low-risk 조건을 통과하면 pilot은 무조건 `files`다.
- `files`에서 hidden side effect가 발견되면 `address`로 내려간다.
- `address`도 실패하면 `personal_board`로 넘어가지만, 이 경우 `W3-B4` aggregate-read freeze batch를 먼저 당긴다.
- 이 순서를 바꾸려면 `W3-B0` run record에 **명시적 downgrade/up-rank 근거**를 남겨야 한다.
- `W2-B6` API shortlist와 이 tie-break가 충돌하면 `W3-B0`에 반드시 `drift / override reason / why files-first changed or survived`를 남긴다.

## 3. Fixed Execution Pipeline — 고정 실행 순서

Wave 3 **전체**는 아래 순서를 지킨다. 각 batch는 이 순서 중 자신에게 배정된 subset만 수행하며, 실제 batch 경계는 `§4`, `§5` runbook이 우선한다.

1. Wave 2 authoritative evidence consume
2. 현재 priority queue와 pilot context lock
3. pilot context public contract freeze
4. hidden side effect inventory freeze
5. canonical target shape 결정
6. `foms/api/<context>` helper extraction
7. `apps/api/<context>` thin wrapper preservation
8. verification + run record 작성
9. 다음 context로 이동

추가 규칙:

- 하나의 batch에서 두 context를 동시에 canonicalize하지 않는다.
- contract freeze 없이 code move를 시작하지 않는다.
- `apps/api/*` wrapper를 얇게 만드는 과정에서도 public import path는 유지한다.
- `foms/platform/blueprints.py`와 registration order는 Wave 3 내내 고정이다.
- batch마다 run record 안에 최소 `contract table / hidden side effect table / defer-or-next decision`이 있어야 한다.
- Wave 3에서 새 generic bucket을 만들지 않는다. context 이름이 있으면 그대로 `foms/api/<context>`를 쓴다.
- runtime binding이 blueprint 밖에서 함께 얽힌 lane을 만나면 그 batch는 stop하고 `Tier 3 defer`로 보낸다.

## 4. Wave 3 Batch Catalog — LLM 실행 순서

### 4.1 Batch table
| Batch ID | 이름 | Risk axis | 주 결과물 | 선행 조건 | 필수 run record |
|------|------|------|------|------|------|
| W3-B0 | Readiness gate + priority queue lock | docs / truth | authoritative queue, pilot context lock | W2-B6 | `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md` |
| W3-B1 | Pilot contract freeze (`files`) | low-risk docs / contract | `files` public contract + side effect inventory | W3-B0 | `docs/plans/2026-04-13-wave3-batch1-files-contract-freeze-run-record.md` |
| W3-B2 | Pilot canonicalization (`files`) | low-risk code | `foms/api/files` + `apps/api/files` thin wrapper | W3-B1 | `docs/plans/2026-04-13-wave3-batch2-files-canonicalization-run-record.md` |
| W3-B3 | Second low-risk canonicalization (`address`) | low-risk code | `foms/api/address` + `apps/api/address` thin wrapper | W3-B2 | `docs/plans/2026-04-13-wave3-batch3-address-canonicalization-run-record.md` |
| W3-B4 | Aggregate-read candidate lock (`personal_board` vs `events`) | medium docs / contract | next candidate selection + contract freeze | W3-B3 | `docs/plans/2026-04-13-wave3-batch4-aggregate-read-lock-run-record.md` |
| W3-B5 | Aggregate-read canonicalization (winner only) | medium code | single aggregate-read context canonicalization | W3-B4 | `docs/plans/2026-04-13-wave3-batch5-aggregate-read-canonicalization-run-record.md` |
| W3-B6 | Mixed/high-risk backlog freeze + closeout | docs / handoff | defer register, Wave 4/6/8 boundary, next-wave order | W3-B5 | `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md` |

### 4.2 Batch별 기본 원칙
- `W3-B0`, `W3-B1`, `W3-B4`, `W3-B6`는 docs-first다.
- `W3-B2`, `W3-B3`, `W3-B5`만 code-touch batch다.
- `W3-B2`, `W3-B3`, `W3-B5`는 각자 **한 context만** canonicalize한다.
- `W3-B5`는 `personal_board`와 `events`를 동시에 옮기는 batch가 아니다. `W3-B4`에서 winner 하나만 고른다.
- `erp_estimates`, `notifications`, `tasks`, `erp_map`, `erp_measurement` mutation, `attachments`, `chat`, `channel_*`, `backup`, `quest`는 `W3-B6` defer register에서 선행조건을 잠그기 전까지 code batch에 넣지 않는다.

## 5. Batch Runbooks — 각 배치의 실제 실행법

### 5.1 W3-B0 — Readiness gate + priority queue lock
**목표**
- Wave 2 authoritative evidence를 소비해 Wave 3 queue를 확정한다.
- pilot context를 `files` 기준으로 lock한다.

**허용 변경**
- `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md`

**금지 변경**
- runtime code
- `foms/platform/blueprints.py`
- controlling spec
- 이 문서 자체

**실행 단계**
1. `W2-B1`부터 `W2-B6`까지 run record 존재 여부를 확인한다.
2. `blueprints.py`와 Wave 2 run record evidence를 대조해 API surface list를 다시 적는다.
3. 각 surface에 대해 최소 아래 필드를 남긴다.
   - registry lane
   - spec domain
   - FR20 context key
   - module path
   - blueprint symbol
   - current owner state
   - hidden side effect 요약
   - provisional tier
   - canonical target
   - related Wave 2 evidence (`W2-B1` row / `W2-B4` adapter row / `W2-B6` shortlist reference)
4. `files`가 low-risk 조건을 충족하는지 explicit check를 남긴다.
5. low-risk 조건을 통과하면 pilot context를 `files`로 lock한다.
6. 실패하면 `왜 실패했는지 / 어떤 규칙을 위반했는지 / 다음 후보가 누구인지`를 남기고 `address`로 내린다.
7. `queue snapshot vs this plan §2.3` 차이가 있으면 drift section에 남긴다.

**산출물**
- authoritative queue table
- pilot lock decision
- `this plan §2.3 snapshot 대비 변경 row`
- unresolved surface list

**검증**
- docs-only batch인지 확인
- each surface row에 tier와 hidden side effect field가 있는지 확인
- `W2-B6` shortlist와 tie-break 충돌 시 override 기록이 있는지 확인
- Wave 2 illustrative 표를 truth로 재사용하지 않았는지 확인

### 5.2 W3-B1 — Pilot contract freeze (`files`)
**목표**
- `apps.api.files`의 public contract와 hidden side effect를 먼저 문서로 고정한다.

**허용 변경**
- `docs/plans/2026-04-13-wave3-batch1-files-contract-freeze-run-record.md`

**금지 변경**
- runtime code
- `foms/platform/blueprints.py`
- `apps/api/files.py`
- `foms/api/*`

**실행 단계**
1. `apps/api/files.py`를 line-by-line로 읽는다.
2. route별로 아래 필드를 contract table에 남긴다.
   - route path
   - methods
   - decorator stack
   - auth requirement
   - response shape
   - external dependency (`get_storage`, redirect, send_file)
3. hidden side effect table에는 최소 아래를 남긴다.
   - presigned URL 발급
   - storage provider 분기 (`r2/s3/local`)
   - redirect/download behavior
   - path validation 규칙
4. canonical target이 package인지 module인지 결정하고, 왜 single module로 끝낼 수 없는지 여부까지 함께 남긴다.
5. thin wrapper conversion 후에도 유지해야 하는 import/export path를 freeze한다.

**산출물**
- `files` contract table
- hidden side effect inventory
- canonical target shape decision

**검증**
- docs-only batch인지 확인
- route별 contract field가 비어 있지 않은지 확인
- "simple GET"라고 축약해 presigned/redirect behavior를 누락하지 않았는지 확인

### 5.3 W3-B2 — Pilot canonicalization (`files`)
**목표**
- `files` API를 첫 low-risk precedent로 canonicalize한다.

**허용 변경**
- `apps/api/files.py`
- `foms/api/files` canonical module/package
- 필요 시 `foms/api/__init__.py` import 정리
- `docs/plans/2026-04-13-wave3-batch2-files-canonicalization-run-record.md`

**금지 변경**
- `foms/platform/blueprints.py`
- route path / methods / blueprint name / `url_prefix`
- response shape 변경
- unrelated service/persistence refactor

**실행 단계**
1. `W3-B1` contract table을 reopen하고 drift 없이 유지한다.
2. canonical target `foms/api/files`를 만든다.
3. route logic 또는 helper logic를 canonical target으로 이동한다.
4. `apps/api/files.py`는 thin wrapper 또는 canonical import shim 역할만 남긴다.
5. 기존 public import path와 blueprint symbol은 유지한다.
6. canonical target이 package 또는 3개 이상 runtime module로 커지면 같은 batch에서 FR20 anchor README gate를 함께 확인한다.
7. 필요한 경우 top-level docstring으로 `canonical target / retirement wave / removal condition`을 명시한다.
8. focused verification을 수행한다.

**산출물**
- `foms/api/files` canonical implementation
- 얇아진 `apps/api/files.py`
- run record의 drift/no-drift 결과

**검증**
- import smoke: `python -c "import app; print('APP_OK')"`
- harness smoke: `python tools/harness/verify_result.py --json`
- `W3-B1` contract table에 열거된 전 route의 path/method/decorator/order diff 확인
- 기존 contract test 확장 우선 여부 확인
- 새 lint가 생기지 않았는지 최근 수정 파일 기준으로 확인

### 5.4 W3-B3 — Second low-risk canonicalization (`address`)
**목표**
- 외부 API proxy 성격의 low-risk context를 두 번째 선례로 만든다.

**허용 변경**
- `apps/api/address.py`
- `foms/api/address` canonical module/package
- `docs/plans/2026-04-13-wave3-batch3-address-canonicalization-run-record.md`

**금지 변경**
- `foms/platform/blueprints.py`
- Kakao query/response policy 변경
- response shape 변경
- unrelated infra change

**실행 단계**
1. `apps/api/address.py`의 query preprocessing, Kakao API 호출, 결과 normalize contract를 고정한다.
2. canonical target `foms/api/address`를 만든다.
3. preprocessor/helper와 route logic을 분리하되, external API request semantics는 그대로 유지한다.
4. `apps/api/address.py`는 thin wrapper 또는 canonical import shim만 남긴다.
5. timeout/header/query variant 순서 같은 behavior-sensitive contract는 run record에 명시한다.
6. canonical target이 package 또는 3개 이상 runtime module로 커지면 같은 batch에서 FR20 anchor README gate를 함께 확인한다.

**산출물**
- `foms/api/address`
- 얇아진 `apps/api/address.py`
- query/response contract inventory

**검증**
- import smoke: `APP_OK`
- harness smoke: `python tools/harness/verify_result.py --json`
- query preprocessing helper contract가 drift 없는지 확인
- 기존 contract test 확장 우선 여부 확인
- 최근 수정 파일 lint 확인

### 5.5 W3-B4 — Aggregate-read candidate lock (`personal_board` vs `events`)
**목표**
- 다음 medium-risk 대상은 하나만 고른다.
- read-heavy aggregate context의 contract를 canonicalization 전에 문서로 잠근다.

**허용 변경**
- `docs/plans/2026-04-13-wave3-batch4-aggregate-read-lock-run-record.md`

**금지 변경**
- runtime code
- candidate 두 개 이상 동시 진행
- controlling spec 수정

**실행 단계**
1. `apps/api/personal_board.py`와 `apps/api/events.py`를 비교한다.
2. 각 후보에 대해 아래 필드를 남긴다.
   - route count
   - read vs mutation 비중
   - DB aggregation breadth
   - JSONB mutation/`flag_modified` 관여 여부
   - hidden side effect
   - required service extraction depth
3. winner 한 개만 고른다.
4. winner의 contract table과 hidden side effect inventory를 같은 run record에 남긴다.
5. loser는 defer가 아니라 "next candidate"로 남기되, unblock condition을 적는다.
6. `W2-B6` shortlist와 winner가 다르면 override reason을 남긴다.

**산출물**
- candidate comparison table
- winner lock decision
- winner contract freeze
- loser next-step note

**검증**
- docs-only batch인지 확인
- winner가 truly one-context인지 확인
- medium-risk인데도 high-risk hidden side effect를 누락하지 않았는지 확인

### 5.6 W3-B5 — Aggregate-read canonicalization (winner only)
**목표**
- `W3-B4`에서 고른 aggregate-read context 하나만 canonicalize한다.

**허용 변경**
- `W3-B4` winner context 관련 `apps/api/*`
- 해당 canonical target `foms/api/<winner>`
- 필요 시 winner가 직접 의존하는 최소 helper
- `docs/plans/2026-04-13-wave3-batch5-aggregate-read-canonicalization-run-record.md`

**금지 변경**
- loser candidate code
- `foms/platform/blueprints.py`
- route path / response shape / auth semantics 변경
- unrelated services refactor

**실행 단계**
1. `W3-B4` winner contract freeze를 reopen한다.
2. canonical target을 만든다.
3. aggregate/read logic를 canonical target으로 옮긴다.
4. `apps/api/<winner>`는 thin wrapper만 남긴다.
5. canonical target이 package 또는 3개 이상 runtime module로 커지면 같은 batch에서 FR20 anchor README gate를 함께 확인한다.
6. side effect가 발견되면 즉시 stop하고 `W3-B6` defer register로 보낸다.

**산출물**
- winner canonical target
- thin wrapper conversion
- drift/no-drift 결과

**검증**
- import smoke: `APP_OK`
- harness smoke: `python tools/harness/verify_result.py --json`
- winner endpoint focused check
- 기존 contract test 확장 우선 여부 확인
- 최근 수정 파일 lint 확인

### 5.7 W3-B6 — Mixed/high-risk backlog freeze + closeout
**목표**
- Wave 3에서 바로 다루지 않을 mixed/high-risk API를 backlog/defer register로 잠근다.
- Wave 4, Wave 6, Wave 8과의 경계를 문서화한다.

**허용 변경**
- `docs/plans/2026-04-13-wave3-batch6-closeout-run-record.md`
- 필요 시 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` reference section
- 필요 시 `docs/ARCHIVE_INDEX.md`

**금지 변경**
- runtime code
- 새 API canonicalization 착수
- page/template/static 이동

**실행 단계**
1. 아래 surface를 최소 backlog/defer table에 남긴다.
   - `erp_estimates`
   - `notifications`
   - `tasks`
   - `erp_map`
   - `erp_measurement` mutation lane
   - `erp_orders_*`
   - `attachments`
   - `chat`
   - `channel_*`
   - `backup`
   - `quest`
   - `debug`
   - `wdcalculator`
2. 각 row에 최소 아래를 남긴다.
   - current owner state
   - why not now
   - required prep
   - suggested next wave / next batch type
3. 위 목록은 최소 baseline이며, `W2-B1`/`blueprints.py` 기준으로 누락 API가 없음을 same run record에서 증명한다.
4. Wave 4는 page/template/static slice, Wave 6은 heavier service/persistence rationalization, Wave 8은 legacy bridge retirement라는 boundary를 다시 적는다.
5. Wave 3 완료 범위를 요약한다.

**산출물**
- defer register
- Wave 4 / Wave 6 / Wave 8 boundary note
- Wave 3 done/not-done summary

**검증**
- docs-only closeout인지 확인
- high-risk surface가 빠짐없이 register에 들어갔는지 확인
- "나중에 그냥 옮긴다" 수준이 아니라 required prep가 적혀 있는지 확인

## 6. Verification Matrix — 배치별 검증 기준

| Batch | 최소 검증 | 실패 시 처리 |
|------|------|------|
| `W3-B0` | authoritative source 존재, queue row completeness | source 부족 시 stop |
| `W3-B1` | route contract completeness, hidden side effect completeness | 누락 보완 후 재검토 |
| `W3-B2` | `APP_OK`, `verify_result.py --json`, `files` focused contract check, lint | drift면 wrapper/canonical split 재조정 |
| `W3-B3` | `APP_OK`, `verify_result.py --json`, address query/response contract check, lint | external API semantics drift면 rollback and redesign |
| `W3-B4` | winner one-context rule, medium-risk evidence completeness | candidate 재선정 |
| `W3-B5` | `APP_OK`, `verify_result.py --json`, winner focused contract check, lint | hidden side effect 발견 시 stop + defer |
| `W3-B6` | defer register completeness, wave boundary clarity | 누락 surface 보완 |

## 7. Run Record Contract — 실행 기록 규칙

모든 Wave 3 batch run record는 아래 section을 같은 문서 안에 가져야 한다.

1. `Scope lock`
2. `Inputs consumed`
3. `Wave 2 key normalization (registry lane / spec domain / FR20 context key)`
4. `Contract table`
5. `Hidden side effect inventory`
6. `FR19 decision (merge vs extend vs add)`
7. `Changes made`
8. `Spec §4 delta summary`
9. `Verification`
10. `FR20 / README gate`
11. `Test footprint decision`
12. `Direction Lock answers`
13. `Drift / stop decision`
14. `Next step or defer`

추가 규칙:

- queue table, compare table, defer register는 모두 해당 run record 안에만 둔다.
- 별도 `inventory.md`, `api_map.md`, `side_effects.md` 같은 sibling 문서를 만들지 않는다.
- `Changes made`에는 수정 파일만 적고 장황한 설명은 줄인다.
- `Verification`에는 실제 실행한 command/result만 남긴다.
- `FR19 decision`에는 single module로 끝낼 수 있었는지, package가 필요했다면 왜 그런지 남긴다.
- `Test footprint decision`에는 기존 test 확장 여부와 신규 micro test pair 생성 사유를 남긴다.
- `Spec §4 delta summary`에는 최소 `product file delta / wrapper file delta / test file delta / canonical target / removal or merge target / new shim retirement wave / local README update`를 포함한다.
- `Direction Lock answers`는 controlling spec `§2.8.1`의 질문군에 대해 batch 단위 yes/no + 한 줄 근거로 답한다.

## 8. Stop Conditions — 중단 조건

아래 중 하나라도 맞으면 해당 batch는 중단하고 run record에 남긴다.

1. Wave 2 authoritative run record가 없거나 truth가 모순된다.
2. blueprint registration path를 바꾸지 않고는 canonicalization이 불가능하다.
3. realtime binding, webhook signature, background task, storage write 등 high-risk side effect가 새로 발견된다.
4. 하나의 batch에서 두 context를 동시에 건드려야만 진행 가능해진다.
5. response shape나 auth semantics를 바꾸지 않고는 canonical split이 불가능하다.
6. page/template/static 이동 요구가 끼어든다.
7. DB/Alembic 변경이 필요해진다.

## 9. First Turn Prompt Contract — 다른 LLM용 첫 실행 프롬프트

아래 프롬프트를 다음 창의 LLM 첫 턴에 그대로 넣는다.

```text
Wave 3 Batch W3-B0 only.

You are executing `docs/plans/2026-04-13-wave3-api-canonicalization-execution-plan.md`.
Do not edit the plan file itself.

Scope lock:
- Execute only `W3-B0 Readiness gate + priority queue lock`.
- Authoritative truth must come from:
  1. `foms/platform/blueprints.py`
  2. Wave 2 run records (`W2-B1` through `W2-B6`)
- Do not treat any illustrative table in the Wave 2/3 plan body as truth.
- If `W2-B6` shortlist conflicts with this plan's files-first tie-break, document the override instead of silently choosing one.

Global forbidden areas:
- No runtime code edits
- No `foms/platform/blueprints.py` edits
- No controlling spec edits
- No new sibling inventory docs

Required output:
- Create/update only `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md`
- Include:
  - authoritative queue table
  - pilot lock decision
  - `this plan §2.3 snapshot 대비 변경 row`
  - unresolved surface list
- If Wave 2 authoritative inputs are missing, stop immediately and document the blocker instead of guessing.
```

## 10. Acceptance Outcome — 완료 조건

이 문서가 승인되면 future LLM은 아래를 재해석 없이 수행할 수 있어야 한다.

1. Wave 2 evidence를 소비해 Wave 3 priority queue를 잠근다.
2. `files`를 first pilot로 검증하고 canonicalize한다.
3. `address`를 second low-risk precedent로 확장한다.
4. aggregate-read context는 하나씩만 고른다.
5. mixed/high-risk API는 defer register로 남겨 방향성을 잃지 않는다.
