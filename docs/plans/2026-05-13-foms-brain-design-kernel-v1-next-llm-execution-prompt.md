# FOMS Brain Design Kernel V1 — Next LLM Execution Prompt
> 작성일: 2026-05-14 | 용도: 다른 LLM/Cursor Agent가 계획서를 1:1 소스코드 대조 후 100% 구현하기 위한 실행 프롬프트

아래 프롬프트를 다음 LLM에게 그대로 전달한다.

```text
너는 FOMS 프로젝트의 senior implementation agent다.

목표:
docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md 를 기준으로 FOMS Brain Design Kernel V1을 100% 구현하라.

중요:
이 작업은 기존 /wdplanner-v2 shell을 조금 꾸미는 일이 아니다.
현재 /wdplanner-v2는 FOMS Brain AX Designer의 실행 기반(shell)일 뿐이다.
이번 작업의 본질은 실제 맞춤가구 설계를 가능하게 하는 Design Kernel V1,
즉 Atomic Ontology + Formula Engine + Constraint Engine + Parametric Editor + Command Engine + Correction Delta를 구현하는 것이다.

절대 규칙:
1. 계획서를 먼저 끝까지 읽고, 그 뒤 실제 소스코드와 1:1 비교하라.
2. “계획서에 있다”와 “코드에 실제로 있다”를 절대 혼동하지 마라.
3. 각 체크리스트 항목을 실제 파일/함수/테스트 기준으로 검증하라.
4. 구현되지 않았거나 stub/placeholder/fake 수준인 것은 미완료로 판정하고 구현하라.
5. 체크리스트를 [x]로 바꾸는 것은 마지막에만 한다. 반드시 코드와 테스트가 먼저다.
6. Next.js/Supabase를 FOMS 내부에 도입하지 않는다.
7. FOMS는 Flask modular monolith다.
8. React/R3F/Drei/Zustand add-in은 Add In Program/FOMSBrainDesigner 안에서 유지한다.
9. Built asset은 static/designer에 둔다.
10. FOMS route는 /wdplanner-v2를 유지한다.
11. 기존 /wdplanner는 제거하지 않는다.
12. 기존 WDPlanner는 참고용일 뿐, FOMS Brain은 완전히 새로운 제품이다.
13. AI가 production ontology rule을 자동 승격하는 구조는 금지한다.
14. hard rule validator 없이 design truth/version/BOM을 저장하지 마라.
15. invalid design 저장은 절대 허용하지 마라.
16. component UUID 없이 selection/command를 처리하지 마라.
17. ERP/order 기존 route regression이 생기면 즉시 중단하고 원인을 보고하라.

반드시 수행할 절차:

STEP 0 — Readiness / Source Truth 확인
- docs/AI_STATUS.md 읽기
- docs/harness/policy/DECISIONS.md에서 foms-brain 관련 결정 확인
- docs/ARCHIVE_INDEX.md에서 foms-brain 관련 계획/기록 확인
- docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md 전체 읽기
- 현재 구현 파일을 실제로 확인:
  - Add In Program/FOMSBrainDesigner/src/domain/*
  - Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts
  - Add In Program/FOMSBrainDesigner/src/canvas/*
  - Add In Program/FOMSBrainDesigner/src/ui/*
  - foms/services/designer/*
  - foms/api/designer/*
  - foms/persistence/designer/*
  - tests/domains/test_designer_*.py

STEP 1 — 1:1 Gap Matrix 작성
계획서의 DK-B0~DK-B10, Data Contract, Acceptance Criteria를 기준으로 다음 형식의 gap matrix를 작성하라.

표 형식:
- 계획서 항목
- 기대 소스 파일
- 실제 존재 여부
- 실제 동작 여부
- 테스트 존재 여부
- 판정: done / partial / missing
- 필요한 조치

중요:
partial은 done이 아니다.
예:
- 타입만 있고 formula 재계산이 없으면 partial
- API endpoint만 있고 validator gate가 없으면 partial
- UI 버튼만 있고 실제 store/API 연결이 없으면 partial
- fake/stub만 있고 deterministic 실행이 없으면 partial

STEP 2 — DK-B0부터 순서대로 구현
절대 batch를 건너뛰지 마라.

DK-B0 — Current Shell Audit
- 현재 shell과 필요한 kernel의 gap을 run record에 기록한다.

DK-B1 — Atomic Ontology Type Freeze
구현:
- Add In Program/FOMSBrainDesigner/src/domain/ontologyTypes.ts
- Add In Program/FOMSBrainDesigner/src/domain/componentCatalog.ts
- foms/services/designer/ontology_types.py
- foms/services/designer/component_catalog.py
- tests/domains/test_designer_design_kernel.py

반드시 포함:
- Assembly
- Module
- Component
- Material
- Formula
- Constraint
- DesignCommand
- DesignPatch
- CorrectionDelta
- component kinds: box, panel, door, shelf, drawer, ep, sr, base, hardware, cutout
- schema_version = 2

DK-B2 — Formula Engine
구현:
- Add In Program/FOMSBrainDesigner/src/domain/formulaEngine.ts
- foms/services/designer/formula_engine.py
- tests/domains/test_designer_formula_engine.py

반드시 동작:
- assembly/module/component dimension 참조
- parent dimension 변경 시 child 재계산
- mm 정수 normalize
- circular formula 감지
- door_height = total_height - top_sr - base - gap
- module_width = (outer_width - ep_left - ep_right) / module_count

DK-B3 — Constraint Engine / Hard Validator V2
구현:
- Add In Program/FOMSBrainDesigner/src/domain/constraintEngine.ts
- foms/services/designer/constraint_engine.py
- foms/services/designer/validator.py
- tests/domains/test_designer_constraint_engine.py
- tests/domains/test_designer_validator.py

반드시 검증:
- outer_width == ep_left + module_sum + ep_right
- component가 parent boundary 안에 있음
- material max size 초과 차단
- door gap rule
- panel thickness rule
- duplicate UUID 차단
- severity: error/warning/info

DK-B4 — Assembly Factory: Built-in Wardrobe V1
구현:
- Add In Program/FOMSBrainDesigner/src/domain/assemblyFactories.ts
- foms/services/designer/assembly_factories.py
- foms/services/designer/defaults.py
- tests/domains/test_designer_design_kernel.py

반드시 동작:
- createWardrobeAssembly({ width, height, depth, moduleCount, doorType })
- left/right/top EP 생성
- base 생성
- side/top/bottom/back panel 생성
- module count 기반 내부 box 생성
- shelf/door 생성
- UUID 중복 없음
- validator 통과

DK-B5 — Frontend Store + 3D Renderer Migration
구현:
- Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts
- Add In Program/FOMSBrainDesigner/src/canvas/CabinetScene.tsx
- Add In Program/FOMSBrainDesigner/src/canvas/DimensionLines.tsx
- Add In Program/FOMSBrainDesigner/src/canvas/SelectionGizmo.tsx
- static/designer/*

반드시 동작:
- store.design이 schema v2 assembly graph를 사용
- panel/door/shelf/ep/sr/base가 각각 개별 3D component로 렌더링
- 선택 대상은 component UUID
- 선택하면 Inspector에 UUID/kind/role/dimensions 표시
- dimension line은 assembly/module/component 기준으로 표시

DK-B6 — Real Parametric Editor UI
구현:
- Add In Program/FOMSBrainDesigner/src/ui/InspectorPanel.tsx
- Add In Program/FOMSBrainDesigner/src/ui/ModulePanel.tsx
- Add In Program/FOMSBrainDesigner/src/ui/ComponentTreePanel.tsx
- Add In Program/FOMSBrainDesigner/src/ui/ValidationPanel.tsx
- Add In Program/FOMSBrainDesigner/src/App.tsx
- static/designer/*

반드시 동작:
- module count 2/3/4 변경
- door type sliding/swing/open 변경
- EP/SR 값 수정
- 선택 부품 속성 수정
- component tree/list 표시
- 변경 즉시 formula 재계산
- invalid 값은 UI와 backend 모두에서 저장 차단

DK-B7 — Command Engine Skeleton
구현:
- Add In Program/FOMSBrainDesigner/src/domain/designCommands.ts
- Add In Program/FOMSBrainDesigner/src/ui/CommandPanel.tsx
- foms/services/designer/command_engine.py
- foms/api/designer/commands.py
- foms/platform/blueprints.py
- tests/domains/test_designer_command_engine.py

반드시 동작:
- DesignCommand JSON 입력
- move_component
- resize_component
- set_property
- generate_layout
- preview/apply 분리
- current selection context를 target으로 사용
- POST /api/designer/commands/preview
- POST /api/designer/commands/apply
- invalid command는 적용/저장 금지

DK-B8 — Correction Delta + Learning-Ready Memory
구현:
- foms/services/designer/corrections.py
- foms/services/designer/vector_memory.py
- foms/persistence/designer/models.py
- foms/persistence/designer/repositories.py
- tests/domains/test_designer_correction_delta.py

반드시 동작:
- manual edit correction delta 생성
- command apply correction delta 생성
- target_id, before, after, reason, source, validated 저장
- rule_candidate_hint 저장
- fake embedding mode에서 correction text 저장
- invalid correction은 validated=false

DK-B9 — Backend API/Data Compatibility
구현:
- foms/api/designer/projects.py
- foms/api/designer/validation.py
- foms/api/designer/ontology.py
- foms/services/designer/defaults.py
- tests/domains/test_designer_projects_api.py
- tests/domains/test_designer_validator.py

반드시 동작:
- schema v1/v2 dual-read
- new project는 schema v2로 생성
- old project는 load 시 v2로 normalize
- version save는 hard validator v2 통과 후만 허용
- API envelope 유지: {success, data, error}

DK-B10 — Closeout / Handoff
구현:
- docs/plans/*design-kernel*v1*run-record*.md
- docs/ARCHIVE_INDEX.md
- docs/AI_STATUS.md
- 계획서 체크리스트 업데이트

반드시 기록:
- 구현 파일 inventory
- schema v2 contract
- 검증 명령/결과
- 남은 작업:
  - Vision-to-Ontology
  - real LUI parser
  - BOM/DXF
  - mobile/touch/field measurement

STEP 3 — 검증
각 batch 후 해당 검증을 실행하라.

공통:
python -c "import app; print('APP_OK')"

Backend:
pytest tests/domains/test_designer_design_kernel.py -q
pytest tests/domains/test_designer_formula_engine.py -q
pytest tests/domains/test_designer_constraint_engine.py -q
pytest tests/domains/test_designer_command_engine.py -q
pytest tests/domains/test_designer_correction_delta.py -q
pytest tests/domains/test_designer_projects_api.py tests/domains/test_designer_validator.py tests/domains/test_designer_ai_runs.py -q

Frontend:
Set-Location "Add In Program\FOMSBrainDesigner"
npm run build

Full designer focused:
pytest tests/domains/test_designer_* -q

STEP 4 — 100% 완료 판정 조건
아래가 모두 충족되기 전에는 완료라고 말하지 마라.

- 기본 붙박이장 assembly가 schema v2 graph로 생성된다.
- module count, door type, EP/SR 변경이 formula로 재계산된다.
- 3D 화면에 panel/door/shelf/ep/sr/base가 개별 부품으로 표시된다.
- 각 부품은 UUID로 선택/수정 가능하다.
- Inspector는 선택 부품의 실제 UUID/kind/role/dimensions를 보여준다.
- ComponentTreePanel에서 부품 계층을 볼 수 있다.
- 외경 합산/parent boundary/자재 최대치/door gap/panel thickness rule이 validator에서 검증된다.
- invalid design은 frontend/backend 모두 저장하지 않는다.
- Command JSON preview/apply가 동작한다.
- command apply 또는 manual edit이 correction delta를 남긴다.
- schema v1 legacy project를 깨지 않고 v2로 normalize한다.
- APP_OK 통과.
- designer focused pytest 통과.
- add-in build 통과.
- 계획서 DK-B0~DK-B10 체크리스트가 실제 구현/검증 근거와 함께 [x] 처리된다.

최종 보고 형식:
1. 구현 요약
2. 계획서 대비 1:1 체크리스트 결과
3. 변경 파일 inventory
4. 검증 명령과 실제 결과
5. 아직 남은 범위(계획서 V1 out-of-scope만)
6. 커밋/푸시 여부

주의:
사용자가 “100% 구현”을 요구했다.
따라서 껍데기, stub, placeholder를 완료로 포장하지 마라.
실제 제품 관점에서 사용자가 가구 설계 객체를 만들고 수정할 수 있어야 한다.
```
