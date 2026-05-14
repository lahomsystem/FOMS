# FOMS Brain Post-V1 — Next LLM Execution Prompt
> 작성일: 2026-05-14 | 용도: 다른 LLM/Cursor Agent가 Post-V1 계획서를 실제 구현하기 위한 실행 프롬프트

아래 프롬프트를 다음 LLM에게 그대로 전달한다.

```text
너는 FOMS 프로젝트의 senior implementation agent다.

목표:
docs/plans/2026-05-14-foms-brain-post-v1-roadmap-plan.md 를 기준으로 FOMS Brain Post-V1을 구현하라.

현재 실제 기준:
- Design Kernel V1은 이미 구현되어 있다.
- 구현 커밋 기준 기능:
  - schema v2 ontology
  - wardrobe assembly factory
  - formula engine
  - constraint engine / hard validator v2
  - component UUID selection
  - parametric editor
  - DesignCommand preview/apply
  - CorrectionDelta seed
- 검증 baseline:
  - APP_OK 통과
  - designer focused pytest 118 passed
  - add-in npm run build 통과

중요:
Post-V1은 V1을 다시 만드는 작업이 아니다.
핵심은 V1 위에 아래 4개 후속 범위를 안전하게 붙이는 것이다.

1. Vision-to-Ontology
   - 사진/도면에서 바로 design truth를 저장하지 않는다.
   - raw image intake -> manual calibration -> fake extractor -> candidate preview -> human approval 순서다.

2. Real LUI Parser
   - 자연어는 design_json을 직접 수정하지 않는다.
   - 반드시 deterministic DesignCommand JSON으로 변환한다.
   - wrong-apply는 0건이어야 한다.

3. Multi Furniture Types
   - wardrobe-only factory를 registry로 확장한다.
   - shoe_rack, kitchen_base, kitchen_wall factory를 추가한다.
   - validator 약화 금지. subtype-specific constraint를 추가한다.

4. Ontology Learning Loop
   - correction delta -> rule candidate -> replay report -> human approval -> ontology promotion 순서다.
   - AI가 production ontology rule을 자동 승격하는 구조는 절대 금지한다.
   - active ontology는 DB-level invariant 또는 repository transaction invariant로 한 개만 존재해야 한다.

절대 규칙:
1. 계획서를 먼저 끝까지 읽고, 실제 소스코드와 1:1 비교하라.
2. “계획서에 있다”와 “코드에 실제로 있다”를 혼동하지 마라.
3. 각 checklist 항목은 실제 파일/함수/API/test 기준으로 검증하라.
4. stub/placeholder/fake는 해당 batch의 의도된 fake mode일 때만 완료로 인정한다.
5. Vision/LUI/learning 결과를 validator 없이 project version으로 저장하지 마라.
6. component UUID 없이 apply를 허용하지 마라.
7. production ontology rule 자동 승격 금지.
8. active ontology 단일성을 코드 관례만으로 보장하지 마라. DB/repository invariant가 필요하다.
9. V1 wardrobe behavior와 schema v1 legacy load를 깨지 마라.
10. Next.js/Supabase를 FOMS 내부에 도입하지 마라.
11. FOMS는 Flask modular monolith다.
12. React/R3F/Drei/Zustand add-in은 Add In Program/FOMSBrainDesigner 안에서 유지한다.
13. Built asset은 static/designer에 둔다.
14. FOMS route는 /wdplanner-v2를 유지한다.
15. 기존 /wdplanner는 제거하지 않는다.
16. ERP/order 기존 route regression이 생기면 즉시 중단하고 원인을 보고하라.

반드시 수행할 절차:

STEP 0 — Readiness / Source Truth 확인
- docs/AI_STATUS.md 읽기
- docs/harness/policy/DECISIONS.md에서 foms-brain 관련 결정 확인
- docs/ARCHIVE_INDEX.md에서 foms-brain 관련 계획/기록 확인
- docs/plans/2026-05-13-foms-brain-design-kernel-v1-execution-plan.md 전체 읽기
- docs/plans/2026-05-14-foms-brain-post-v1-roadmap-plan.md 전체 읽기
- 현재 구현 파일을 실제로 확인:
  - foms/services/designer/ontology_types.py
  - foms/services/designer/assembly_factories.py
  - foms/services/designer/formula_engine.py
  - foms/services/designer/constraint_engine.py
  - foms/services/designer/command_engine.py
  - foms/services/designer/corrections.py
  - foms/services/designer/evolution.py
  - foms/services/designer/vector_memory.py
  - foms/services/designer/langgraph_workflows.py
  - foms/services/designer/schemas.py
  - foms/api/designer/*
  - foms/persistence/designer/*
  - Add In Program/FOMSBrainDesigner/src/domain/*
  - Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts
  - Add In Program/FOMSBrainDesigner/src/ui/*
  - tests/domains/test_designer_*.py

STEP 1 — Gap Matrix 작성
계획서의 PV2-B0~PV2-B10과 Acceptance Criteria를 기준으로 아래 형식의 gap matrix를 작성하라.

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
- 자연어 parser가 command JSON은 만들지만 target UUID ambiguity를 처리하지 못하면 partial
- Vision endpoint가 image를 받지만 candidate preview/human approval이 없으면 partial
- factory가 shape는 만들지만 validator 통과가 안 되면 partial
- rule candidate는 만들지만 replay/promotion invariant가 없으면 partial

STEP 2 — Tranche 단위로 구현

한 번에 PV2-B0~B10을 전부 완료하려 하지 마라.
아래 tranche boundary를 지켜라.

Tranche 1:
- PV2-B0 V1 Stabilization / Contract Freeze
- PV2-B1 Real LUI Parser V1
- PV2-B2 Multi Furniture Factory Registry

Tranche 2:
- PV2-B3 Shoe Rack Factory V1
- PV2-B4 Kitchen Cabinet Factory V1

Tranche 3:
- PV2-B5 Vision-to-Ontology Intake Contract
- PV2-B6 Vision Extraction Candidate Pipeline
- PV2-B7 Human Review / Overlay Correction UI
- PV2-B8 Ontology Learning Candidate Pipeline
- PV2-B9 Rule Replay / Promotion Workflow
- PV2-B10 Closeout / Verification / Handoff

각 tranche는 독립 검증 가능해야 한다.

PV2-B0 — V1 Stabilization / Contract Freeze
구현:
- foms/services/designer/schemas.py
- foms/services/designer/langgraph_workflows.py
- foms/services/designer/command_engine.py
- foms/api/designer/commands.py
- tests/domains/test_designer_*_contract.py

반드시 동작:
- schema v2 Pydantic models 추가
- langgraph_workflows.py가 v1 cabinet shape를 직접 수정하지 않음
- LangGraph output이 DesignCommand preview로만 연결
- generate_layout command가 factory registry를 호출할 수 있는 interface 고정
- active ontology 단일성 보장 방식 결정
  - Postgres: partial unique index 또는 transactional lock
  - SQLite/test: repository-level invariant
- V1 regression baseline 유지

PV2-B1 — Real LUI Parser V1
구현:
- foms/services/designer/lui_parser.py
- foms/api/designer/lui.py
- Add In Program/FOMSBrainDesigner/src/ui/LuiPanel.tsx
- tests/domains/test_designer_lui_parser.py

반드시 동작:
- Korean natural language -> deterministic DesignCommand
- selection context 우선
- selected UUID가 없으면 target candidate/clarification 반환
- ambiguous command apply 금지
- golden command set 50개
- exact intent match >= 90%
- wrong-apply = 0
- ambiguous-to-clarification = 100%

PV2-B2 — Multi Furniture Factory Registry
구현:
- foms/services/designer/factory_registry.py
- foms/services/designer/assembly_factories.py
- Add In Program/FOMSBrainDesigner/src/domain/factoryRegistry.ts
- tests/domains/test_designer_factory_registry.py

반드시 동작:
- FurnitureType: wardrobe, shoe_rack, kitchen_base, kitchen_wall, custom_storage
- create_assembly(type, params)
- validate_params(type, params)
- default_params(type)
- wardrobe factory registry 등록
- generate_layout command가 registry 사용

PV2-B3 — Shoe Rack Factory V1
구현:
- foms/services/designer/factories/shoe_rack.py
- Add In Program/FOMSBrainDesigner/src/domain/factories/shoeRackFactory.ts
- tests/domains/test_designer_shoe_rack_factory.py

반드시 동작:
- createShoeRackAssembly({ width, height, depth, tierCount, doorType, hasBench })
- 800W/1200H/350D/4-tier fixture
- shelf/tier 반복 생성
- shelf pitch min/max constraint
- invalid tier spacing 저장 차단

PV2-B4 — Kitchen Cabinet Factory V1
구현:
- foms/services/designer/factories/kitchen.py
- Add In Program/FOMSBrainDesigner/src/domain/factories/kitchenFactory.ts
- tests/domains/test_designer_kitchen_factory.py

반드시 동작:
- createKitchenBaseAssembly({ width, height, depth, moduleCount, doorType, drawerCount, sinkCutout })
- createKitchenWallAssembly({ width, height, depth, moduleCount, doorType })
- sink/cooktop cutout boundary
- drawer stack height sum
- countertop overhang
- wall cabinet depth max

PV2-B5 — Vision-to-Ontology Intake Contract
구현:
- foms/services/designer/vision_types.py
- foms/api/designer/vision.py
- Add In Program/FOMSBrainDesigner/src/ui/VisionPanel.tsx
- tests/domains/test_designer_vision_intake.py

반드시 동작:
- Vision은 완전 자동 설계 생성이 아니다.
- image_url 또는 attachment id 수집
- manual calibration fields:
  - known_length_mm
  - image_segment_px
  - origin_hint
  - perspective_mode
- raw image artifact만 저장
- intake는 project version을 만들지 않음

PV2-B6 — Vision Extraction Candidate Pipeline
구현:
- foms/services/designer/vision_extractor.py
- foms/services/designer/vision_to_ontology.py
- tests/domains/test_designer_vision_extraction.py

반드시 동작:
- fake deterministic extractor 우선
- test fixture metadata -> candidate 생성
- real provider는 env-gated adapter interface만
- provider unavailable은 명시적 error
- output은 DesignGraphCandidate 또는 DesignCommand[]
- validator preview 포함
- unresolved field가 있으면 apply 금지

PV2-B7 — Human Review / Overlay Correction UI
구현:
- Add In Program/FOMSBrainDesigner/src/ui/VisionReviewPanel.tsx
- Add In Program/FOMSBrainDesigner/src/ui/OverlayAnnotationPanel.tsx
- tests/domains/test_designer_vision_review.py

반드시 동작:
- candidate preview
- image coord ↔ component UUID 매핑
- overlay UI는 main editor와 분리된 panel
- approve 전 project version 저장 금지
- correction delta source=vision_review

PV2-B8 — Ontology Learning Candidate Pipeline
구현:
- foms/services/designer/evolution.py
- foms/services/designer/vector_memory.py
- foms/api/designer/evolution.py
- tests/domains/test_designer_rule_candidate.py

반드시 동작:
- correction clustering query
- candidate_rule_hint 기반 candidate 생성
- embedding/fake embedding retrieval
- AI는 candidate만 생성
- active ontology 변경 금지

PV2-B9 — Rule Replay / Promotion Workflow
구현:
- foms/services/designer/rule_replay.py
- foms/services/designer/evolution.py
- foms/api/designer/evolution.py
- tests/domains/test_designer_rule_replay.py
- tests/domains/test_designer_ontology_promotion.py

반드시 동작:
- rule candidate replay runner
- replay report:
  - pass_count
  - fail_count
  - changed_design_count
  - new_validation_errors
  - affected_furniture_types
- human approval 없이 promote 불가
- promotion creates new DesignerOntologyVersion
- active ontology는 한 개만 존재
- rollback path 검증
- DB-level invariant 또는 repository transaction invariant 검증

PV2-B10 — Closeout / Verification / Handoff
구현:
- docs/plans/*post-v1*run-record*.md
- docs/ARCHIVE_INDEX.md
- docs/AI_STATUS.md

반드시 기록:
- 구현 파일 inventory
- LUI golden set 결과
- factory coverage
- Vision fake extractor evidence
- rule replay report evidence
- verification commands/results
- remaining out-of-scope

STEP 3 — 검증

공통:
python -c "import app; print('APP_OK')"

Backend:
pytest tests/domains/test_designer_* -q

Frontend:
Set-Location "Add In Program\\FOMSBrainDesigner"
npm run build

Focused per tranche:
- Tranche 1:
  pytest tests/domains/test_designer_lui_parser.py tests/domains/test_designer_factory_registry.py -q
- Tranche 2:
  pytest tests/domains/test_designer_shoe_rack_factory.py tests/domains/test_designer_kitchen_factory.py -q
- Tranche 3:
  pytest tests/domains/test_designer_vision_* tests/domains/test_designer_rule_* tests/domains/test_designer_ontology_promotion.py -q

STEP 4 — 완료 판정 조건

아래가 모두 충족되기 전에는 완료라고 말하지 마라.

- 자연어 명령 50개 golden set이 deterministic DesignCommand로 변환된다.
- LUI exact intent match >= 90%.
- LUI wrong-apply = 0.
- ambiguous command는 clarification 상태로 멈춘다.
- wardrobe, shoe_rack, kitchen_base, kitchen_wall factory가 schema v2 graph를 생성한다.
- 모든 factory output이 hard validator를 통과한다.
- Vision intake는 raw image artifact만 저장하고 design truth를 직접 저장하지 않는다.
- Vision fake extractor가 fixture metadata에서 candidate를 만든다.
- Vision candidate는 human review 전 저장되지 않는다.
- correction delta cluster에서 rule candidate가 생성된다.
- rule candidate replay report가 생성된다.
- human approval 없이 ontology promotion이 불가능하다.
- active ontology는 DB-level invariant 또는 repository transaction invariant로 한 개만 존재한다.
- APP_OK 통과.
- designer focused pytest 통과.
- add-in build 통과.
- 계획서 checklist가 실제 구현/검증 근거와 함께 [x] 처리된다.

최종 보고 형식:
1. 구현 요약
2. 계획서 대비 1:1 체크리스트 결과
3. 변경 파일 inventory
4. 검증 명령과 실제 결과
5. 남은 범위
6. 커밋/푸시 여부
```
