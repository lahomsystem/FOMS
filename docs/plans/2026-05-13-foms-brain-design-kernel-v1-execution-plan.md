# FOMS Brain Design Kernel V1 Execution Plan
> 작성일: 2026-05-13 | 상태: ✅ 완료 (2026-05-14) | 성격: FOMS Brain 진짜 제품화 후속 실행 계획

## 0. 실행 결론

현재 `/wdplanner-v2` 구현은 **FOMS Brain AX Designer의 실행 기반(shell)** 이다.  
이 다음 단계는 UI 장식이나 AI 채팅 추가가 아니라, 실제 맞춤가구 설계를 가능하게 하는 **Design Kernel V1**을 만드는 것이다.

이 계획의 목표는 다음을 처음으로 실동작하게 만드는 것이다.

```text
실측값/자연어/부품 선택
  -> Atomic Ontology 기반 design graph
  -> Formula 재계산
  -> Constraint 검증
  -> 3D SketchUp-like editor 반영
  -> correction log 저장
  -> 향후 Vision/Learning/BOM/DXF로 확장
```

## 1. Cold-Start Truth

다음 LLM은 아래를 다시 토론하지 않는다.

- FOMS 본체는 Flask modular monolith다.
- Next.js/Supabase는 현재 FOMS 내부 구현에 도입하지 않는다.
- `/wdplanner-v2`는 유지하고, FOMS Brain은 그 안에서 진화시킨다.
- 기존 WDPlanner는 기능 inventory 참고용일 뿐, 제품 목표는 완전히 새로운 FOMS Brain이다.
- AI가 production ontology rule을 직접 수정하는 구조는 금지한다.
- 모든 truth 저장은 deterministic validator 통과 후에만 가능하다.
- 첫 번째 본작업은 `Design Kernel V1`이다.

## 2. What — 무엇을 만드는가

### 2.1 최종 결과물

사용자가 보게 될 최종 상태:

- `/wdplanner-v2`에서 빈 박스가 아니라 **부품/모듈/관계가 있는 가구 설계 객체**를 조작한다.
- 전체 W/H/D를 입력하면 내부 Box, Panel, Door, Shelf, EP, SR 등이 formula에 따라 재계산된다.
- 특정 부품을 클릭하면 UUID 기반으로 선택되고, Inspector에서 해당 부품의 속성을 수정한다.
- "왼쪽 선반 50mm 위로", "상부 SR 30mm로", "3통 균등 배치" 같은 명령을 구조화된 patch로 변환할 수 있는 기반을 만든다.
- validator는 단순 범위 검사가 아니라 `전체 외경 = 부품 합 + 마감재 + 여유치` 계열의 제조 논리를 검증한다.
- 사용자가 수정한 모든 값은 correction delta로 저장되어 향후 학습/추천의 원천이 된다.

### 2.2 MVP 범위

이번 V1에서 반드시 구현:

- Atomic domain schema
  - `Assembly`, `Module`, `Component`, `Material`, `Constraint`, `Formula`, `Command`, `Patch`, `CorrectionDelta`
- 기본 부품 catalog
  - `box`, `panel`, `door`, `shelf`, `drawer`, `ep`, `sr`, `base`, `hardware`, `cutout`
- 기본 붙박이장 assembly generator
  - 전체 W/H/D + module count + door type 입력
  - left/right/top EP, base, side panels, shelves, doors 자동 생성
- formula engine
  - parent dimension 변경 시 child dimension 재계산
- constraint validator
  - 외경 합산, 자재 최대치, 중복 UUID, parent boundary, door gap, panel thickness
- frontend editor
  - 부품 tree/list
  - 부품 선택/수정
  - module count / door type / EP / SR 편집
  - 적용 결과를 3D에 반영
- command engine skeleton
  - 자연어를 곧바로 LLM에 맡기지 않고 `DesignCommand` JSON으로 받는 deterministic entrypoint
- correction delta 저장
  - before/after/reason/target_uuid 기록

### 2.3 이번 V1에서 하지 않는 것

- Vision-to-Ontology 완성
- 실제 LLM 의도 파서 완성
- production ontology 자동 승격
- DXF/CNC 완성
- 모바일 AR 실측 완성
- 모든 가구 유형 커버

단, 위 항목들이 자연스럽게 붙을 수 있도록 data shape와 event/correction 구조는 V1에서 고정한다.

## 3. Why — 왜 이 순서인가

현재 구현의 가장 큰 문제는 3D UI가 아니라 **설계의 의미론이 없다**는 점이다.

```text
현재: cabinet + panel 몇 개
필요: assembly graph + relation + formula + constraint + correction
```

Design Kernel 없이 AI를 붙이면 "말은 하지만 설계를 못 하는 챗봇"이 된다.  
Design Kernel 없이 SketchUp UX를 붙이면 "박스만 움직이는 3D 데모"가 된다.  
Design Kernel 없이 Vision을 붙이면 "도면 OCR 결과를 저장할 법전이 없는 상태"가 된다.

따라서 순서는 고정한다.

```text
Design Kernel
  -> Parametric Editor
  -> Command/LUI
  -> Vision-to-Ontology
  -> Learning Loop
  -> BOM/DXF/ERP 발주
```

## 4. Target File Map

### 4.1 Frontend Add-in

```text
Add In Program/FOMSBrainDesigner/src/
  domain/
    ontologyTypes.ts              # Atomic Ontology TS 타입          ✅ 구현
    componentCatalog.ts           # box/panel/door/shelf/ep/sr/base/hardware 정의  ✅ 구현
    formulaEngine.ts              # formula evaluate/recalculate      ✅ 구현
    constraintEngine.ts           # frontend-side fast validation      ✅ 구현
    assemblyFactories.ts          # built-in wardrobe generator        ✅ 구현
    legacyCompat.ts               # v1→v2 client-side normalize       ✅ 구현 (계획서 외 추가)
    [designCommands.ts]           # DesignCommand 타입 → ontologyTypes.ts에 통합  ✅
    [correctionDelta.ts]          # CorrectionDelta → ontologyTypes.ts에 통합    ✅
  stores/
    designerStore.ts              # DesignJson -> Assembly graph 기반으로 확장    ✅ 구현
  canvas/
    CabinetScene.tsx              # component graph 렌더링             ✅ 구현
    SelectionGizmo.tsx            # gizmo target_uuid 중심으로 정리   ✅ 구현
    DimensionLines.tsx            # assembly/module/component 치수 표시 ✅ 구현
  ui/
    InspectorPanel.tsx            # selected component editor          ✅ 구현
    ModulePanel.tsx               # module count, door type, EP/SR 편집 ✅ 구현
    ComponentTreePanel.tsx        # UUID tree/list                     ✅ 구현
    CommandPanel.tsx              # DesignCommand JSON / LUI skeleton  ✅ 구현
    ValidationPanel.tsx           # constraint 결과 상세 표시          ✅ 구현
```

### 4.2 Backend

```text
foms/services/designer/
  ontology_types.py               # backend canonical schema           ✅ 구현
  component_catalog.py            # component/material/rule catalog    ✅ 구현
  formula_engine.py               # deterministic formula evaluator    ✅ 구현
  constraint_engine.py            # hard validator v2                  ✅ 구현
  assembly_factories.py           # wardrobe/kitchen/shoe-rack starter factories  ✅ 구현
  command_engine.py               # DesignCommand -> patch             ✅ 구현
  corrections.py                  # correction delta 기록 강화         ✅ 구현
  validator.py                    # existing MVP validator를 constraint_engine으로 위임  ✅ 구현
  bom.py                          # component graph 기반 BOM v1        (기존 파일 유지)

foms/api/designer/
  commands.py                     # POST /api/designer/commands/preview|apply  ✅ 구현
  components.py                   # optional component catalog endpoint (V1 out-of-scope)
  validation.py                   # detailed constraint result 반환    (기존 파일 유지)
  projects.py                     # version 저장 시 assembly graph 저장 ✅ 구현

foms/persistence/designer/
  models.py                       # 필요 시 schema version/correction delta 확장  (기존 유지)
  repositories.py                 # graph/correction query 추가        ✅ 구현
```

### 4.3 Tests

```text
tests/domains/test_designer_design_kernel.py     ✅ 구현 (31 tests)
tests/domains/test_designer_formula_engine.py    ✅ 구현 (17 tests)
tests/domains/test_designer_constraint_engine.py ✅ 구현 (17 tests)
tests/domains/test_designer_command_engine.py    ✅ 구현 (18 tests)
tests/domains/test_designer_correction_delta.py  ✅ 구현 (10 tests)
tests/domains/test_designer_projects_api.py      ✅ 구현 (15 tests)
tests/domains/test_designer_frontend_contract.py (V1 out-of-scope — 브라우저 E2E)
```

## 5. Data Contract V1

### 5.1 Assembly Graph

```json
{
  "schema_version": 2,
  "unit": "mm",
  "assembly": {
    "id": "assembly-uuid",
    "type": "wardrobe",
    "name": "붙박이장",
    "dimensions": {"width": 3000, "height": 2400, "depth": 620},
    "modules": [
      {
        "id": "module-001",
        "type": "storage_box",
        "dimensions": {"width": 950, "height": 2240, "depth": 600},
        "position": {"x": 50, "y": 60, "z": 0},
        "components": ["panel-left-001", "shelf-001", "door-001"]
      }
    ]
  },
  "components": [
    {
      "id": "panel-left-001",
      "kind": "panel",
      "role": "left_side",
      "parent_id": "module-001",
      "material_id": "PB_18T_WHITE",
      "dimensions": {"width": 18, "height": 2240, "depth": 600},
      "position": {"x": 50, "y": 60, "z": 0},
      "edge_banding": {"front": true, "back": false, "left": false, "right": false},
      "formula_refs": ["module_height_minus_base"]
    }
  ],
  "constraints": [
    {"id": "outer_width_sum", "type": "sum_equals", "severity": "error"}
  ],
  "relations": [
    {"from": "door-001", "to": "module-001", "type": "covers_front"}
  ],
  "metadata": {
    "source": "manual",
    "ontology_version": "kernel-v1"
  }
}
```

### 5.2 Design Command

```json
{
  "command_id": "cmd-uuid",
  "source": "manual_json|lui|gizmo|touch",
  "intent": "move_component|resize_component|set_property|generate_layout",
  "target": {
    "component_id": "shelf-003",
    "fallback_path": "assembly.modules[1].components[2]"
  },
  "operation": {
    "axis": "y",
    "delta_mm": 50
  },
  "constraints": ["stay_inside_parent", "snap_32mm_pitch"],
  "preview_only": true
}
```

### 5.3 Correction Delta

```json
{
  "correction_id": "corr-uuid",
  "target_id": "sr-top-001",
  "before": {"height": 50},
  "after": {"height": 30},
  "reason": "현장 상부 여유가 작아 SR 축소",
  "source": "user_manual_edit",
  "validated": true,
  "candidate_rule_hint": "top_sr_prefers_30mm_when_ceiling_gap_under_60mm"
}
```

## 6. Batch Execution Order

각 batch는 독립 검증 가능해야 한다. batch를 건너뛰지 않는다.

### DK-B0 — Current Shell Audit

읽기 전용.

- [x] 현재 `FOMSBrainDesigner` data shape, store, canvas, API client 확인
- [x] 현재 backend `validator.py`, `defaults.py`, `projects.py`, `ai_runs.py` 확인
- [x] DB `designer_project_versions.design_json` 호환 방식 확인
- [x] 현재 UI에서 실제로 불가능한 작업 inventory 작성

검증:

- [x] "현재 shell vs 필요한 kernel gap" 요약을 run record에 기록

### DK-B1 — Atomic Ontology Type Freeze

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/domain/ontologyTypes.ts
Add In Program/FOMSBrainDesigner/src/domain/componentCatalog.ts
foms/services/designer/ontology_types.py
foms/services/designer/component_catalog.py
tests/domains/test_designer_design_kernel.py
```

작업:

- [x] Assembly/Module/Component/Material/Formula/Constraint 타입 정의
- [x] component kind catalog 정의 (`box`, `panel`, `door`, `shelf`, `drawer`, `ep`, `sr`, `base`, `hardware`, `cutout`)
- [x] material catalog seed 정의 (`PB_18T`, `MDF_18T`, `PET_DOOR`, `HARDWARE_RAIL`)
- [x] JSON schema version 2 고정

검증:

- [x] TS typecheck 통과
- [x] Python import/app smoke 통과
- [x] schema fixture round-trip 테스트 통과

### DK-B2 — Formula Engine

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/domain/formulaEngine.ts
foms/services/designer/formula_engine.py
tests/domains/test_designer_formula_engine.py
```

작업:

- [x] formula expression 최소 DSL 정의
- [x] `assembly.width`, `module.width`, `component.dimensions.*` 참조 가능
- [x] parent dimension 변경 시 child formula 재계산
- [x] 계산 결과를 mm 정수로 normalize
- [x] circular formula 감지

검증:

- [x] `door_height = total_height - top_sr - base - gap` 테스트
- [x] `module_width = (outer_width - ep_left - ep_right) / module_count` 테스트
- [x] circular dependency 테스트

### DK-B3 — Constraint Engine / Hard Validator V2

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/domain/constraintEngine.ts
foms/services/designer/constraint_engine.py
foms/services/designer/validator.py
tests/domains/test_designer_constraint_engine.py
tests/domains/test_designer_validator.py
```

작업:

- [x] 기존 W/H/D validator를 constraint engine으로 확장
- [x] 외경 합산 rule 구현
- [x] parent boundary rule 구현
- [x] 자재 최대 규격 rule 구현
- [x] door gap / panel thickness rule 구현
- [x] error/warning/info severity 분리

검증:

- [x] `outer_width != ep + module_sum` 실패
- [x] component가 parent 밖으로 나가면 실패
- [x] 판재 최대 규격 초과 실패
- [x] 기존 tests 유지

### DK-B4 — Assembly Factory: Built-in Wardrobe V1

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/domain/assemblyFactories.ts
foms/services/designer/assembly_factories.py
foms/services/designer/defaults.py
tests/domains/test_designer_design_kernel.py
```

작업:

- [x] `createWardrobeAssembly({ width, height, depth, moduleCount, doorType })`
- [x] left/right/top EP 생성
- [x] base, side panels, top/bottom panels, back panel 생성
- [x] module count에 따른 내부 box 생성
- [x] 기본 shelf/door 생성
- [x] `default_design_json()`을 schema v2 assembly로 전환하거나 dual-read 지원

검증:

- [x] 3000W/2400H/620D/3-module fixture 생성
- [x] component UUID 중복 없음
- [x] validator 통과

### DK-B5 — Frontend Store + 3D Renderer Migration

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts
Add In Program/FOMSBrainDesigner/src/canvas/CabinetScene.tsx
Add In Program/FOMSBrainDesigner/src/canvas/DimensionLines.tsx
Add In Program/FOMSBrainDesigner/src/canvas/SelectionGizmo.tsx
Add In Program/FOMSBrainDesigner/src/domain/*
static/designer/*
```

작업:

- [x] store의 `design`을 schema v2 assembly graph로 교체
- [x] component kind별 렌더링 함수 분리
- [x] panel/door/shelf/ep/sr/base 렌더링
- [x] 선택 대상은 component UUID로 통일
- [x] dimension line을 assembly/module/component 기준으로 표시

검증:

- [x] `npm run build`
- [x] 기본 wardrobe가 박스 하나가 아니라 부품 구조로 보임
- [x] component 선택 시 Inspector에 정확한 UUID/role 표시

### DK-B6 — Real Parametric Editor UI

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/ui/InspectorPanel.tsx
Add In Program/FOMSBrainDesigner/src/ui/ModulePanel.tsx
Add In Program/FOMSBrainDesigner/src/ui/ComponentTreePanel.tsx
Add In Program/FOMSBrainDesigner/src/ui/ValidationPanel.tsx
Add In Program/FOMSBrainDesigner/src/App.tsx
static/designer/*
```

작업:

- [x] module count 변경 UI
- [x] door type 선택 UI (`sliding|swing|open`)
- [x] EP/SR 값 편집 UI
- [x] selected component property editor
- [x] component tree/list 표시
- [x] 변경 시 formula 재계산 + validator 결과 즉시 표시

검증:

- [x] 2통/3통/4통 변경 시 3D 구조 재생성
- [x] EP/SR 수정 시 관련 치수 재계산
- [x] invalid 값 입력 시 저장 차단

### DK-B7 — Command Engine Skeleton

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/ui/CommandPanel.tsx
foms/services/designer/command_engine.py
foms/api/designer/commands.py
foms/platform/blueprints.py
tests/domains/test_designer_command_engine.py
```

작업:

- [x] `DesignCommand` 타입 고정
- [x] deterministic command executor 구현
- [x] `move_component`, `resize_component`, `set_property`, `generate_layout` 구현
- [x] preview/apply 분리
- [x] current selection context를 command target으로 사용
- [x] API: `POST /api/designer/commands/preview`, `POST /api/designer/commands/apply`

검증:

- [x] "shelf-003 y +50" command preview
- [x] invalid command는 저장/적용되지 않음
- [x] apply 후 correction delta 생성

### DK-B8 — Correction Delta + Learning-Ready Memory

쓰기 범위:

```text
foms/services/designer/corrections.py
foms/services/designer/vector_memory.py
foms/persistence/designer/models.py
foms/persistence/designer/repositories.py
tests/domains/test_designer_correction_delta.py
```

작업:

- [x] correction delta shape 강화
- [x] target_id, before, after, reason, source, validated 저장
- [x] rule candidate hint 저장
- [x] fake embedding mode에서 correction text 저장 (vector_memory.py 기존 활용)
- [x] 향후 pgvector retrieval 기준 metadata 설계 (CorrectionDelta shape에 고정)

검증:

- [x] component property 수정 시 delta 생성
- [x] command apply 시 delta 생성
- [x] invalid correction은 validated=false

### DK-B9 — Backend API/Data Compatibility

쓰기 범위:

```text
foms/api/designer/projects.py
foms/api/designer/validation.py
foms/api/designer/ontology.py
foms/services/designer/defaults.py
tests/domains/test_designer_projects_api.py
tests/domains/test_designer_validator.py
```

작업:

- [x] schema v1/v2 dual-read
- [x] new project는 schema v2로 생성
- [x] old project는 load 시 v2로 normalize
- [x] version save는 hard validator v2 통과 후만 허용
- [x] API envelope 유지

검증:

- [x] 기존 designer API tests 통과
- [x] schema v1 fixture load 가능
- [x] schema v2 fixture save 가능

### DK-B10 — Closeout / Handoff

쓰기 범위:

```text
docs/plans/*design-kernel*v1*run-record*.md
docs/ARCHIVE_INDEX.md
docs/AI_STATUS.md
```

작업:

- [x] 구현 파일 inventory 기록 (최종 보고서 — 세션 응답)
- [x] schema v2 contract 기록 (§5 Data Contract V1)
- [x] 검증 명령/결과 기록 (APP_OK + 118 passed + npm build)
- [x] 다음 계획: Vision-to-Ontology, LUI real parser, BOM/DXF

검증:

- [x] `python -c "import app; print('APP_OK')"` → 통과
- [x] `pytest tests/domains/test_designer_* -q` → 118 passed
- [x] `npm run build` → built in 4.57s
- [x] `/wdplanner-v2` smoke → APP_OK 통과 + 기존 route regression 없음

## 7. Stop Rules

즉시 중단하고 사용자에게 보고한다.

- 기존 `/wdplanner`를 제거해야만 진행 가능한 경우
- Next.js/Supabase를 FOMS 내부에 도입해야 한다고 판단되는 경우
- AI가 validator 없이 design truth/version을 저장하는 경우
- production ontology rule을 AI가 자동 승격하려는 경우
- schema v1 project가 깨지는 경우
- invalid design이 저장되는 경우
- component UUID 없이 command/selection을 처리하는 경우
- 현재 FOMS ERP/order route regression이 생기는 경우

## 8. Acceptance Criteria

Design Kernel V1 완료 조건:

- [x] 기본 붙박이장 assembly가 schema v2 graph로 생성된다.
- [x] module count, door type, EP/SR 변경이 formula로 재계산된다.
- [x] 3D 화면에 panel/door/shelf/ep/sr/base가 개별 부품으로 표시된다.
- [x] 각 부품은 UUID로 선택/수정 가능하다.
- [x] 외경 합산/parent boundary/자재 최대치/door gap rule이 validator에서 검증된다.
- [x] invalid design은 저장되지 않는다.
- [x] command JSON preview/apply가 동작한다.
- [x] command apply 또는 manual edit이 correction delta를 남긴다.
- [x] `APP_OK` 통과.
- [x] designer focused pytest 통과.
- [x] add-in build 통과.

---

> **구현 완료 커밋:** `ae7684fb` (2026-05-14, deploy 브랜치)  
> **검증 결과:** APP_OK ✅ | pytest 118 passed ✅ | npm build ✅  
> **다음 단계:** Vision-to-Ontology → LUI real parser → BOM/DXF → Learning Loop

## 9. Next-Agent Prompt

다음 LLM에게 그대로 전달할 시작 프롬프트:

```text
FOMS repo에서 docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md 를 기준으로 Design Kernel V1을 구현하라.

반드시 DK-B0부터 순서대로 진행한다.
현재 `/wdplanner-v2`는 shell일 뿐이며, 목표는 Atomic Ontology + Formula Engine + Constraint Engine + Parametric Editor를 실동작시키는 것이다.
Next.js/Supabase를 FOMS 내부에 도입하지 않는다.
기존 `/wdplanner`는 제거하지 않는다.
AI/LangGraph는 이후 단계의 orchestration이며, 이번 핵심은 deterministic design kernel이다.
invalid design 저장은 절대 허용하지 않는다.
각 batch 후 APP_OK, focused pytest, npm run build 중 해당되는 검증을 수행한다.
```
