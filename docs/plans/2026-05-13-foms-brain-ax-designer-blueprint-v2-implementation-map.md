# FOMS Brain AX Designer V2 Implementation Map
> 작성일: 2026-05-13 | 상태: 🟡 승인대기 | 성격: cold-start LLM 실행 지도

## 0. 실행 결론

WDPlanner 대체 제품을 **FOMS Brain AX Designer**로 만든다.

구현 방식은 고정한다.

```text
Frontend add-in: Add In Program/FOMSBrainDesigner
Built assets:    static/designer
FOMS route:      /wdplanner-v2
FOMS web owner:  foms/web/designer
FOMS API owner:  foms/api/designer
AI owner:        foms/services/designer/langgraph_workflows.py
DB owner:        foms/persistence/designer + Alembic migration
Vector memory:   PostgreSQL pgvector, external vector DB 금지
```

V1 문서는 판단 근거다. 이 V2 문서가 실제 구현 순서의 기준이다.

## 1. Cold-Start Truth

다음 LLM은 아래 사실을 다시 토론하지 않는다. 구현 전 파일 존재 여부만 확인한다.

- FOMS 본체는 Flask modular monolith다.
- Next.js `src/app` 방식으로 구현하지 않는다.
- Supabase Auth/DB를 도입하지 않는다.
- LangGraph는 필수이며 backend/worker 계층에서 실행한다.
- React/R3F/Drei/Zustand는 3D 설계 add-in에 사용한다.
- AI가 production ontology rule을 바로 바꾸는 구조는 금지한다.
- hard rule validation 없이 BOM/도면 truth 저장은 금지한다.
- 기존 `/wdplanner`는 즉시 제거하지 않는다. V2는 `/wdplanner-v2`로 병행 운영한다.

현재 참고 surface:

```text
foms/web/wdcalculator/planner.py          # 기존 WDPlanner add-in route 패턴
templates/wdcalculator/wdplanner.html     # iframe wrapper 패턴
static/wdplanner/                         # 기존 WDPlanner built asset 위치
foms/platform/blueprints.py               # Blueprint 등록 허브
templates/partials/shared/layout_nav.html # 도구 메뉴
```

## 2. Product Contract

첫 제품은 "붙박이장/수납장 3D 설계 + AI 설계 보조 + 검증 저장"이다.

MVP에서 반드시 되는 것:

- FOMS 메뉴에서 `/wdplanner-v2` 진입
- 로그인 사용자만 접근
- React canvas가 nonblank 렌더링
- 기본 cabinet model 생성
- 부재 선택
- 폭/높이/깊이 수치 변경
- 실시간 치수선 표시
- FOMS API로 project 저장/조회
- AI run 생성/상태 조회
- LangGraph Design Assist Graph 최소 실행
- validator 실패 시 저장 차단
- correction log 저장

MVP에서 하지 않는 것:

- 기존 `/wdplanner` 제거
- Next.js 도입
- Supabase 도입
- production ontology 자동 승격
- PDF/JPG 도면 vision extraction 완성
- CNC/DXF 완성

## 3. Target File Map

### 3.1 Frontend Add-in

```text
Add In Program/FOMSBrainDesigner/
  package.json
  index.html
  vite.config.ts
  tsconfig.json
  src/
    main.tsx
    App.tsx
    api/client.ts
    canvas/DesignerCanvas.tsx
    canvas/CabinetScene.tsx
    canvas/DimensionLines.tsx
    canvas/SelectionGizmo.tsx
    domain/designTypes.ts
    domain/defaultCabinet.ts
    stores/designerStore.ts
    ui/InspectorPanel.tsx
    ui/AIPanel.tsx
    ui/ValidationPanel.tsx
```

### 3.2 Built Assets

```text
static/designer/
  index.html
  assets/*
```

### 3.3 FOMS Web

```text
foms/web/designer/
  __init__.py
  routes.py

templates/designer/
  wdplanner_v2.html
  wdplanner_v2_setup.html
```

### 3.4 FOMS API

```text
foms/api/designer/
  __init__.py
  projects.py
  ai_runs.py
  validation.py
  ontology.py
```

### 3.5 FOMS Services

```text
foms/services/designer/
  __init__.py
  schemas.py
  defaults.py
  validator.py
  bom.py
  corrections.py
  vector_memory.py
  langgraph_workflows.py
  evolution.py
```

### 3.6 Persistence

```text
foms/persistence/designer/
  __init__.py
  models.py
  repositories.py

migrations/versions/*_designer_ax_initial.py
```

### 3.7 Tests

```text
tests/domains/test_designer_routes.py
tests/domains/test_designer_projects_api.py
tests/domains/test_designer_validator.py
tests/domains/test_designer_ai_runs.py
tests/contracts/runtime/test_designer_blueprint_registration.py
```

## 4. Data Contract

초기 DB는 작게 시작한다. JSONB를 적극 사용하되 version 재현성을 깨지 않는다.

### 4.1 Tables

```text
designer_projects
  id
  order_id nullable
  name
  current_version_id nullable
  created_by_user_id nullable
  created_at
  updated_at

designer_project_versions
  id
  project_id
  version_no
  ontology_version_id nullable
  design_json jsonb
  validation_json jsonb
  bom_json jsonb
  created_by_user_id nullable
  created_at

designer_ontology_versions
  id
  version_key unique
  status active|draft|retired
  rules_json jsonb
  created_at

designer_corrections
  id
  project_id nullable
  project_version_id nullable
  ai_run_id nullable
  before_json jsonb
  after_json jsonb
  reason_text nullable
  created_by_user_id nullable
  created_at

designer_ai_runs
  id
  graph_name
  graph_version
  thread_id
  status queued|running|interrupt|succeeded|failed|cancelled
  input_json jsonb
  state_json jsonb
  output_json jsonb nullable
  error_text nullable
  created_by_user_id nullable
  created_at
  updated_at

designer_rule_candidates
  id
  source_correction_ids jsonb
  candidate_json jsonb
  replay_report_json jsonb nullable
  status draft|approved|rejected|promoted
  created_at

designer_embeddings
  id
  owner_type
  owner_id
  text
  embedding vector nullable
  metadata_json jsonb
  created_at
```

### 4.2 Initial Design JSON Shape

```json
{
  "schema_version": 1,
  "unit": "mm",
  "cabinet": {
    "width": 2400,
    "height": 2200,
    "depth": 600
  },
  "components": [
    {
      "id": "left-side",
      "type": "panel",
      "name": "좌측판",
      "width": 18,
      "height": 2200,
      "depth": 600,
      "position": {"x": 0, "y": 0, "z": 0}
    }
  ],
  "relations": []
}
```

## 5. API Contract

초기 endpoint는 아래만 구현한다.

```text
GET  /api/designer/projects
POST /api/designer/projects
GET  /api/designer/projects/<project_id>
POST /api/designer/projects/<project_id>/versions

POST /api/designer/validate

POST /api/designer/ai-runs
GET  /api/designer/ai-runs/<run_id>
POST /api/designer/ai-runs/<run_id>/resume

GET  /api/designer/ontology/current
```

### 5.1 Response Shape

모든 신규 API는 아래 envelope를 따른다.

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

실패:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "설계 규칙 검증 실패",
    "details": {}
  }
}
```

## 6. LangGraph MVP Contract

초기에는 graph를 완성형 AI로 만들지 않는다. 실행 가능한 뼈대를 먼저 고정한다.

### 6.1 Design Assist Graph

```text
START
  -> load_context
  -> parse_intent
  -> propose_design_patch
  -> run_validator
  -> maybe_interrupt_for_review
  -> persist_result
END
```

### 6.2 Node 책임

```text
load_context
  - current design_json
  - current ontology rules
  - optional order/measurement context

parse_intent
  - user prompt를 structured command로 변환
  - LLM unavailable이면 deterministic placeholder command 반환

propose_design_patch
  - design_json patch 후보 생성
  - MVP에서는 width/height/depth 변경만 허용

run_validator
  - foms/services/designer/validator.py 호출
  - errors가 있으면 persist_result 금지

maybe_interrupt_for_review
  - risky change 또는 validator warning이면 interrupt 상태 저장
  - human resume API로 approve/reject 받음

persist_result
  - approved + valid인 경우에만 project version 저장
  - correction log 저장
```

### 6.3 No-LLM Fallback

초기 구현은 LLM key가 없어도 테스트 가능해야 한다.

규칙:

- `DESIGNER_AI_FAKE=1`이면 LLM 호출 없이 deterministic graph 실행
- fake mode도 `designer_ai_runs` 기록을 남긴다
- fake mode도 validator를 통과해야 저장 가능하다

## 7. Validator MVP

초기 validator는 아래만 검증한다.

```text
cabinet.width  > 0
cabinet.height > 0
cabinet.depth  > 0
cabinet.width  <= 10000
cabinet.height <= 4000
cabinet.depth  <= 1200
component id 중복 금지
panel 두께 0 이하 금지
```

반환 shape:

```json
{
  "valid": false,
  "errors": [
    {"code": "WIDTH_TOO_LARGE", "message": "폭은 6000mm 이하만 허용됩니다.", "path": "cabinet.width"}
  ],
  "warnings": []
}
```

## 8. Batch Execution Order

각 batch는 독립적으로 검증 가능해야 한다. batch를 건너뛰지 않는다.

### B0 — Current Surface Freeze

읽기 전용.

- [x] `foms/web/wdcalculator/planner.py` 확인
- [x] `templates/wdcalculator/wdplanner.html` 확인
- [x] `static/wdplanner/index.html` 확인
- [x] `foms/platform/blueprints.py` 등록 패턴 확인
- [x] `templates/partials/shared/layout_nav.html` 메뉴 패턴 확인

완료 기준:

- [x] 다음 배치에서 복제할 route/menu/static-hosting 패턴을 확정

### B1 — Backend Skeleton

쓰기 범위:

```text
foms/web/designer/*
templates/designer/*
foms/platform/blueprints.py
templates/partials/shared/layout_nav.html
tests/domains/test_designer_routes.py
tests/contracts/runtime/test_designer_blueprint_registration.py
```

작업:

- [x] `/wdplanner-v2` wrapper route 추가
- [x] `/wdplanner-v2/app` static app route 추가
- [x] `/wdplanner-v2/app/<path:filename>` asset route 추가
- [x] `static/designer/index.html` 없으면 setup 안내 페이지 표시
- [x] navigation 도구 메뉴에 `FOMS Brain` 추가

검증:

- [x] `python -c "import app; print('APP_OK')"`
- [x] `/wdplanner-v2` route test 200
- [x] setup fallback test

### B2 — Frontend Add-in Shell

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/*
static/designer/*
```

작업:

- [x] Vite React TypeScript 프로젝트 생성
- [x] R3F canvas 생성
- [x] 기본 cabinet box 렌더링
- [x] Zustand store 생성
- [x] Inspector panel에서 width/height/depth 변경
- [x] build output을 `static/designer`로 복사하는 script 추가 (vite.config.ts outDir 방식)

검증:

- [x] `npm run build`
- [x] `static/designer/index.html` 존재
- [x] `/wdplanner-v2/app` asset 200
- [x] canvas nonblank 수동/브라우저 smoke

### B3 — Persistence + Project API

쓰기 범위:

```text
foms/persistence/designer/*
foms/api/designer/*
foms/services/designer/schemas.py
foms/services/designer/defaults.py
migrations/versions/*_designer_ax_initial.py
foms/platform/blueprints.py
tests/domains/test_designer_projects_api.py
```

작업:

- [x] initial tables migration
- [x] project create/list/get
- [x] project version create
- [x] default design JSON 생성
- [x] API envelope 고정

검증:

- [x] migration import 검증
- [x] project API focused pytest
- [x] 기존 APP_OK 유지

### B4 — Validator + Save Gate

쓰기 범위:

```text
foms/services/designer/validator.py
foms/api/designer/validation.py
foms/api/designer/projects.py
tests/domains/test_designer_validator.py
tests/domains/test_designer_projects_api.py
```

작업:

- [x] validator MVP 구현
- [x] `POST /api/designer/validate`
- [x] invalid design version 저장 차단
- [x] validation_json 저장

검증:

- [x] invalid width 저장 실패
- [x] duplicate component id 실패
- [x] valid default design 저장 성공

### B5 — LangGraph MVP

쓰기 범위:

```text
foms/services/designer/langgraph_workflows.py
foms/services/designer/corrections.py
foms/api/designer/ai_runs.py
foms/api/designer/projects.py
tests/domains/test_designer_ai_runs.py
```

작업:

- [x] fake-mode 가능한 Design Assist Graph
- [x] `POST /api/designer/ai-runs`
- [x] `GET /api/designer/ai-runs/<id>`
- [x] `POST /api/designer/ai-runs/<id>/resume`
- [x] validator 통과 시에만 version 저장
- [x] correction log 저장

검증:

- [x] `DESIGNER_AI_FAKE=1` 테스트
- [x] run status transition test
- [x] validator fail run은 version 저장 안 됨
- [x] approve resume 후 version 저장

### B6 — Frontend API Wiring

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/api/*
Add In Program/FOMSBrainDesigner/src/ui/*
Add In Program/FOMSBrainDesigner/src/stores/*
static/designer/*
```

작업:

- [x] project create/load/save 연결
- [x] validate 버튼/자동검증 연결
- [x] AI prompt panel 연결
- [x] AI run status polling
- [x] interrupt approve/reject UI
- [x] build 산출물 갱신

검증:

- [x] UI에서 project 저장 가능
- [x] invalid 값 입력 시 저장 차단 표시
- [x] fake AI run 실행/승인 가능

### B7 — Vector Memory Stub + pgvector Gate

쓰기 범위:

```text
foms/services/designer/vector_memory.py
foms/api/designer/ontology.py
migrations/versions/*_designer_pgvector.py
tests/domains/test_designer_ai_runs.py
```

작업:

- [x] pgvector extension migration 작성
- [x] extension unavailable fallback을 명시적으로 fail 또는 disabled 상태로 기록
- [x] embedding 저장 service stub
- [x] fake embedding mode
- [x] ontology current endpoint

검증:

- [x] pgvector available 환경에서는 migration 가능
- [x] unavailable 환경에서는 조용히 성공 처리하지 않음
- [x] fake embedding 저장 path test

### B8 — Closeout + Handoff

쓰기 범위:

```text
docs/plans/*run-record*.md
docs/ARCHIVE_INDEX.md
docs/AI_STATUS.md
```

작업:

- [x] 구현 파일 inventory 기록
- [x] 검증 명령/결과 기록
- [x] 남은 작업: vision extraction, BOM 고도화, ontology evolution 분리
- [x] 기존 `/wdplanner` 교체 조건 정의

검증:

- [x] APP_OK
- [x] focused pytest
- [x] add-in build
- [x] route smoke

## 9. Commands

Windows PowerShell 기준.

```powershell
python -c "import app; print('APP_OK')"
pytest tests/domains/test_designer_routes.py -q
pytest tests/domains/test_designer_projects_api.py -q
pytest tests/domains/test_designer_validator.py -q
pytest tests/domains/test_designer_ai_runs.py -q
```

Frontend:

```powershell
Set-Location "Add In Program\FOMSBrainDesigner"
npm install
npm run build
```

주의:

- network install이 sandbox/network 제한으로 실패하면 승인 요청 후 재실행한다.
- `npm install` 전에는 기존 `Add In Program/WDPlanner/package.json` dependency를 참고한다.

## 10. Stop Rules

즉시 중단하고 사용자에게 보고한다.

- `/wdplanner`를 제거해야만 진행 가능한 경우
- Next.js/Supabase 도입 없이는 구현 불가능하다고 판단되는 경우
- FOMS main DB와 별도 DB를 source of truth로 만들려는 경우
- LangGraph run이 validator 없이 version 저장하는 경우
- invalid design이 저장되는 경우
- pgvector migration이 실패했는데 조용히 통과시키는 경우
- existing ERP/order route regression이 생기는 경우

## 11. Acceptance

V2 MVP 완료 조건:

- [x] `/wdplanner-v2` 메뉴 진입 가능
- [x] React/R3F canvas 표시
- [x] 기본 cabinet 치수 편집 가능
- [x] project 저장/조회 가능
- [x] validator가 invalid 저장 차단
- [x] fake LangGraph run 생성/조회/resume 가능
- [x] approved AI patch가 새 project version으로 저장
- [x] correction log 저장
- [x] APP_OK 통과
- [x] designer focused pytest 통과
- [x] add-in build 통과

## 12. Next-Agent Prompt

다음 LLM에게 그대로 전달할 시작 프롬프트:

```text
FOMS repo에서 docs/plans/2026-05-13-foms-brain-ax-designer-blueprint-v2-implementation-map.md 를 기준으로 FOMS Brain AX Designer를 구현하라.

반드시 B0부터 순서대로 진행한다.
현재 목표는 /wdplanner-v2 병행 운영 MVP다.
Next.js/Supabase는 도입하지 않는다.
LangGraph는 필수지만 B5에서 fake-mode 가능한 backend workflow부터 구현한다.
invalid design 저장은 절대 허용하지 않는다.
각 batch 후 APP_OK 또는 focused pytest로 검증하고, blocker가 없으면 다음 batch로 진행한다.
```
