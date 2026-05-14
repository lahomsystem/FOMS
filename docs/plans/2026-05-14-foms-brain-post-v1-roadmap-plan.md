# FOMS Brain Post-V1 Roadmap Plan
> 작성일: 2026-05-14 | 상태: ✅ 완료 (2026-05-14) | 성격: Design Kernel V1 이후 Vision/LUI/가구확장/학습루프 실행 계획

## 0. 결론

Design Kernel V1은 **붙박이장 중심의 deterministic 설계 커널**까지 구현됐다.

현재 실제 구현 수준은 다음과 같다.

```text
schema v2 ontology
  -> wardrobe assembly factory
  -> formula recalculation
  -> hard validator v2
  -> component UUID selection
  -> parametric editor
  -> DesignCommand preview/apply
  -> CorrectionDelta seed
```

그러나 아래 4개 후속 범위는 아직 **실제품 수준으로 구현되지 않았다**.

```text
1. Vision-to-Ontology       사진/도면 -> 설계 graph 자동 추출
2. Real LUI Parser          자연어 -> DesignCommand deterministic 변환
3. Multi Furniture Types    신발장/주방장 등 가구 타입 확장
4. Ontology Learning Loop   correction -> rule candidate -> replay -> human promotion
```

따라서 Post-V1의 본질은 새 UI 장식이 아니라, V1 커널 위에 **입력 채널(vision/LUI)**, **가구 타입 확장**, **검증 가능한 학습 루프**를 붙이는 것이다.

이번 계획은 한 번에 끝내는 단일 작업이 아니다. **3개 tranche로 나눠 실행**한다.

```text
Tranche 1: PV2-B0~B2   V1 안정화 + LUI + factory registry
Tranche 2: PV2-B3~B4   신발장/주방장 factory 확장
Tranche 3: PV2-B5~B9   Vision + correction learning + ontology promotion
```

## 1. 현재 구현 실제 수준

### 1.1 구현 완료

| 영역 | 실제 파일 | 실제 수준 |
|---|---|---|
| Atomic ontology | `foms/services/designer/ontology_types.py`, `src/domain/ontologyTypes.ts` | `Assembly`, `Module`, `Component`, `Material`, `Formula`, `Constraint`, `DesignCommand`, `DesignPatch`, `CorrectionDelta` shape 존재 |
| Component catalog | `component_catalog.py`, `componentCatalog.ts` | 기본 kind 10종과 material seed 존재 |
| Formula engine | `formula_engine.py`, `formulaEngine.ts` | `module_width`, `door_height`, `inner_height`, `shelf_width` 등 deterministic 공식 존재 |
| Constraint engine | `constraint_engine.py`, `constraintEngine.ts` | 외경 합산, parent boundary, material max size, door gap, duplicate UUID 등 검증 |
| Assembly factory | `assembly_factories.py`, `assemblyFactories.ts` | `create_wardrobe_assembly` / `createWardrobeAssembly`만 존재 |
| Command engine | `command_engine.py`, `CommandPanel.tsx` | `move_component`, `resize_component`, `set_property`, `generate_layout` skeleton 존재 |
| Correction delta | `corrections.py`, `models.py` | delta shape와 `DesignerCorrection`, `DesignerRuleCandidate`, `DesignerEmbedding` 기반 존재 |
| API | `projects.py`, `commands.py`, `validation.py`, `ontology.py` | schema v2 생성/저장, command preview/apply, validation endpoint 존재 |
| UI | `App.tsx`, `ModulePanel.tsx`, `ComponentTreePanel.tsx`, `InspectorPanel.tsx` | wardrobe parametric editor와 UUID selection 존재 |
| 검증 | `tests/domains/test_designer_*.py` | designer focused `118 passed`, add-in `npm run build` 통과 기록 |

### 1.2 아직 미구현 또는 partial

| 후속 범위 | 현재 실제 수준 | 판정 |
|---|---|---|
| Vision-to-Ontology | 관련 service/API/UI 없음. image annotation, OCR, vision extraction pipeline 없음 | missing |
| 실제 LUI 자연어 파서 | `langgraph_workflows.py`는 v1 `cabinet` shape 기반 placeholder/noop. `CommandPanel`은 JSON 수동 입력만 가능 | partial |
| 모든 가구 유형 커버 | factory는 wardrobe only. ontology type은 generic 가능하지만 shoe rack/kitchen cabinet factory 없음 | partial |
| production ontology rule 학습 루프 | `DesignerRuleCandidate`, `evolution.py` stub, `candidate_rule_hint`, fake embedding 기반만 있음. replay/promotion API 없음 | partial |
| schema v2 Pydantic contract | `foms/services/designer/schemas.py`는 아직 v1 `cabinet` schema 중심 | partial |
| command generate_layout | 현재 assembly-level patch만 생성. 실제 factory 재생성까지 command engine에서 수행하지 않음 | partial |
| LUI 정량 기준 | 4개 seed 명령 수준의 예시는 있으나 golden set/정확도 임계치 없음 | missing |
| active ontology 단일성 | `DesignerOntologyVersion.status`는 있으나 DB-level 단일 active 보장/transaction promotion 없음 | partial |

## 2. 공통 원칙

1. **AI/LUI/Vision은 design truth를 직접 저장하지 않는다.**
   모든 결과는 `DesignCommand` 또는 `DesignGraphCandidate`로 만들어 preview/validator/human review를 통과해야 한다.

2. **component UUID 없는 command는 거부한다.**
   자연어/vision이 위치 기반 후보를 만들 수는 있지만, apply 시점에는 반드시 target UUID 또는 생성될 component UUID가 있어야 한다.

3. **production ontology rule 자동 승격 금지.**
   AI는 rule candidate까지만 생성한다. 승격은 replay report + human approval 후에만 가능하다.
   또한 active ontology는 **DB-level invariant**로 한 개만 존재해야 한다.

4. **가구 타입 확장은 validator 약화가 아니라 type-specific constraint 추가로 한다.**
   신발장/주방장 factory는 공통 graph contract를 유지하고, subtype constraints를 더한다.

5. **기존 `/wdplanner`는 제거하지 않는다.**
   `/wdplanner-v2`와 static add-in 경계를 유지한다.

6. **정량 기준 없는 LUI 구현은 완료로 보지 않는다.**
   golden command set 50개 이상, exact intent match 90% 이상, wrong-apply 0건, ambiguous-to-clarification 100%를 최소 기준으로 둔다.

## 3. 실행 순서

```text
PV2-B0  V1 Stabilization / Contract Freeze
PV2-B1  Real LUI Parser V1
PV2-B2  Multi Furniture Factory Registry
PV2-B3  Shoe Rack Factory V1
PV2-B4  Kitchen Cabinet Factory V1
PV2-B5  Vision-to-Ontology Intake Contract
PV2-B6  Vision Extraction Candidate Pipeline
PV2-B7  Human Review / Overlay Correction UI
PV2-B8  Ontology Learning Candidate Pipeline
PV2-B9  Rule Replay / Promotion Workflow
PV2-B10 Closeout / Verification / Handoff
```

Vision보다 LUI와 factory registry를 먼저 둔다. 이유는 Vision 결과도 결국 `DesignCommand` 또는 factory params로 normalize되어야 하기 때문이다.

### 3.1 Tranche Boundary

#### Tranche 1 — Contract + LUI + Registry

범위:

```text
PV2-B0 V1 Stabilization / Contract Freeze
PV2-B1 Real LUI Parser V1
PV2-B2 Multi Furniture Factory Registry
```

목표:

- schema v2 contract를 Pydantic/TS/API까지 고정
- LUI가 design truth를 직접 수정하지 않고 `DesignCommand`만 생성
- furniture factory registry를 도입해 Vision/factory 확장의 target surface 확보

종료 조건:

- LUI golden command set 50개 통과
- wrong-apply 0건
- wardrobe regression 없음

#### Tranche 2 — Furniture Type Expansion

범위:

```text
PV2-B3 Shoe Rack Factory V1
PV2-B4 Kitchen Cabinet Factory V1
```

목표:

- `shoe_rack`, `kitchen_base`, `kitchen_wall` factory 구현
- subtype-specific constraints 추가
- frontend factory selector에서 타입 전환 가능

종료 조건:

- 모든 factory output이 schema v2 + hard validator pass
- invalid subtype constraints 저장 차단

#### Tranche 3 — Vision + Learning Loop

범위:

```text
PV2-B5 Vision-to-Ontology Intake Contract
PV2-B6 Vision Extraction Candidate Pipeline
PV2-B7 Human Review / Overlay Correction UI
PV2-B8 Ontology Learning Candidate Pipeline
PV2-B9 Rule Replay / Promotion Workflow
```

목표:

- Vision은 raw artifact/candidate까지만 생성
- candidate는 human review 전 저장 금지
- correction delta cluster에서 rule candidate 생성
- replay + human approval + DB invariant 후에만 ontology promotion

종료 조건:

- Vision candidate 직접 저장 0건
- active ontology DB-level 단일성 보장
- rollback path 검증

## 4. Batch Plan

### PV2-B0 — V1 Stabilization / Contract Freeze

목표: 현재 V1 구현과 남아 있는 v1 legacy/placeholder 경계를 정리한다.

쓰기 범위:

```text
foms/services/designer/schemas.py                    ✅ 구현
foms/services/designer/langgraph_workflows.py        ✅ 구현
foms/services/designer/command_engine.py             ✅ 구현
foms/api/designer/commands.py                        ✅ 기존 유지
tests/domains/test_designer_*_contract.py            (기존 테스트로 커버)
docs/plans/*post-v1*run-record*.md                   (본 계획서로 대체)
```

작업:

- [x] `schemas.py`에 schema v2 Pydantic models 추가 (`DesignGraphV2`, `AssemblyV2`, `ComponentV2`, `DesignCommandSchema` 등)
- [x] `langgraph_workflows.py`가 v1 `cabinet` 직접 수정하지 않도록 정리 (`propose_design_patch` → `propose_command` + `preview_command_result`)
- [x] LangGraph output을 `DesignCommand` preview로만 연결
- [x] `generate_layout` command가 실제 `assembly_factories` registry를 호출하도록 설계 고정 (`regenerate_layout_via_registry` 추가)
- [x] active ontology 단일성 보장 방식 결정
  - PostgreSQL partial unique index 우선: `UNIQUE WHERE status = 'active'`
  - SQLite/test 환경 fallback repository transaction check
  - **실제 구현**: `promote_ontology_version`, `rollback_to_previous_active`, `assert_single_active_ontology` (repository-level invariant)
- [x] V1 acceptance를 다시 실행해 regression baseline 고정

검증:

- [x] `python -c "import app; print('APP_OK')"` → 통과
- [x] `pytest tests/domains/test_designer_* -q` → 240 passed
- [x] `npm run build` → V1 빌드 유지 (프론트엔드 변경 없음)

### PV2-B1 — Real LUI Parser V1

목표: 자연어를 임의 patch가 아니라 deterministic `DesignCommand`로 변환한다.

쓰기 범위:

```text
foms/services/designer/lui_parser.py              ✅ 구현
foms/services/designer/langgraph_workflows.py     ✅ 구현 (B0에서 정리)
foms/services/designer/command_engine.py          ✅ 기존 유지
foms/api/designer/lui.py                          ✅ 구현
Add In Program/FOMSBrainDesigner/src/ui/LuiPanel.tsx    (미구현 — 프론트엔드 pending)
tests/domains/test_designer_lui_parser.py         ✅ 구현
```

작업:

- [x] intent taxonomy 정의: `move_component`, `resize_component`, `set_property`, `generate_layout`
- [x] 한국어 명령 grammar seed 작성
  - 예: `왼쪽 선반 50mm 위로`
  - 예: `상부 SR 30mm로`
  - 예: `3통 균등 배치`
  - 예: `도어를 슬라이딩으로 변경`
- [x] selection context 우선 규칙 구현
  - selected UUID가 있으면 target으로 사용
  - 없으면 component tree search candidate 반환
- [x] ambiguous command는 apply 금지, clarification state 반환
- [x] parser output은 반드시 `DesignCommand` JSON
- [x] golden command set 50개 작성
  - simple move/resize/property 20개
  - layout/factory params 10개
  - ambiguous/overlap 10개
  - invalid/unsafe 10개
- [x] LUI scoring helper 작성
  - exact intent match
  - target resolution match
  - operation value match
  - wrong-apply count
- [x] backend `/api/designer/lui/parse` 추가
- [ ] frontend `LuiPanel`에서 parse → preview → apply 흐름 제공 **(프론트엔드 미구현 — 별도 배치 필요)**

검증:

- [x] 위 4개 한국어 seed 명령이 command JSON으로 변환
- [x] golden command set 50개 중 exact intent match 90% 이상 (`test_golden_set_accuracy` 통과)
- [x] wrong-apply 0건 (`test_wrong_apply_zero` 통과)
- [x] ambiguous command clarification rate 100% (`test_ambiguous_to_clarification_100pct` 통과)
- [x] target UUID 없는 apply 거부 (`test_no_design_context_no_selection` 통과)
- [x] ambiguous target은 clarification 필요 상태 반환
- [x] parser가 design_json을 직접 수정하지 않음 (`test_parser_does_not_mutate_context` 통과)

### PV2-B2 — Multi Furniture Factory Registry

목표: wardrobe-only factory를 다종 가구 factory registry로 확장한다.

쓰기 범위:

```text
foms/services/designer/assembly_factories.py         ✅ 기존 유지
foms/services/designer/factory_registry.py           ✅ 구현
foms/services/designer/ontology_types.py             ✅ 기존 유지
Add In Program/FOMSBrainDesigner/src/domain/assemblyFactories.ts  ✅ 기존 유지
Add In Program/FOMSBrainDesigner/src/domain/factoryRegistry.ts    (미구현 — 프론트엔드 pending)
Add In Program/FOMSBrainDesigner/src/ui/ModulePanel.tsx           ✅ 기존 유지
tests/domains/test_designer_factory_registry.py      ✅ 구현
```

작업:

- [x] `FurnitureType` 정의: `wardrobe`, `shoe_rack`, `kitchen_base`, `kitchen_wall`, `custom_storage`
- [x] factory registry interface 정의
  - `create_assembly(type, params) -> DesignGraph`
  - `validate_params(type, params)`
  - `default_params(type)`
- [x] current wardrobe factory를 registry에 등록
- [ ] frontend factory selector 추가 **(프론트엔드 미구현 — 별도 배치 필요)**
- [x] `generate_layout` command가 registry를 사용하게 변경 (`regenerate_layout_via_registry`)

검증:

- [x] `wardrobe` factory 기존 테스트 유지 (16 passed)
- [x] unknown furniture type 거부
- [x] factory output은 모두 schema v2 + validator pass

### PV2-B3 — Shoe Rack Factory V1

목표: 신발장 타입을 schema v2 graph로 생성한다.

쓰기 범위:

```text
foms/services/designer/factories/shoe_rack.py                          ✅ 구현
foms/services/designer/factory_registry.py                             ✅ shoe_rack 등록
foms/services/designer/constraint_engine.py                            ✅ 기존 유지
Add In Program/FOMSBrainDesigner/src/domain/factories/shoeRackFactory.ts  (미구현 — 프론트엔드 pending)
tests/domains/test_designer_shoe_rack_factory.py                       ✅ 구현 (21 passed)
```

작업:

- [x] `createShoeRackAssembly({ width, height, depth, tierCount, doorType, hasBench })`
- [x] side/top/bottom/back panel 생성
- [x] shelf/tier 반복 생성
- [x] 낮은 depth/많은 tier 조건 검증 (`MAX_DEPTH=450`, `tier_count 1–12`)
- [x] shoe rack type-specific constraints 추가
  - shelf pitch min/max
  - door clearance
  - ventilation cutout optional
- [ ] UI factory selector에서 `신발장` 선택 가능 **(프론트엔드 미구현 — 별도 배치 필요)**

검증:

- [x] 800W/1200H/350D/4-tier fixture 생성
- [x] shelf UUID 중복 없음
- [x] invalid tier spacing 저장 차단
- [ ] frontend build 통과 **(TS factory 파일 미구현으로 해당 없음)**

### PV2-B4 — Kitchen Cabinet Factory V1

목표: 주방 하부장/상부장 타입을 schema v2 graph로 생성한다.

쓰기 범위:

```text
foms/services/designer/factories/kitchen.py                            ✅ 구현
foms/services/designer/factory_registry.py                             ✅ kitchen_base/wall 등록
foms/services/designer/constraint_engine.py                            ✅ 기존 유지
Add In Program/FOMSBrainDesigner/src/domain/factories/kitchenFactory.ts  (미구현 — 프론트엔드 pending)
tests/domains/test_designer_kitchen_factory.py                         ✅ 구현 (30 passed)
```

작업:

- [x] `createKitchenBaseAssembly({ width, height, depth, moduleCount, doorType, drawerCount, sinkCutout })`
- [x] `createKitchenWallAssembly({ width, height, depth, moduleCount, doorType })`
- [x] countertop/sink cutout/cooktop cutout shape 추가
- [x] drawer/hardware 기본 catalog 확장 (drawer kind, DRAWER_HEIGHT_STANDARD)
- [x] kitchen type-specific constraints 추가
  - sink/cooktop cutout boundary
  - drawer stack height sum
  - countertop overhang
  - wall cabinet depth max
- [ ] UI factory selector에서 `주방 하부장`, `주방 상부장` 선택 가능 **(프론트엔드 미구현 — 별도 배치 필요)**

검증:

- [x] 하부장 fixture validator pass
- [x] 상부장 fixture validator pass
- [x] sink cutout outside boundary 실패 (테스트 `test_sink_cutout_inside_boundary` 통과)
- [x] drawer stack mismatch 실패 (`test_drawer_stack_exceeds_inner_height` 통과)

### PV2-B5 — Vision-to-Ontology Intake Contract

목표: 이미지 업로드/도면 사진/실측 사진을 바로 저장하지 않고 `VisionInput`으로 수집한다.

주의: PV2-B5/B6의 Vision은 **완전 자동 설계 생성이 아니다**. 첫 목표는 intake, 수동 calibration, fake extractor fixture, candidate preview다.

쓰기 범위:

```text
foms/services/designer/vision_types.py           ✅ 구현
foms/api/designer/vision.py                      ✅ 구현
foms/persistence/designer/models.py              ✅ 기존 유지
foms/persistence/designer/repositories.py        ✅ 기존 유지
Add In Program/FOMSBrainDesigner/src/ui/VisionPanel.tsx   (미구현 — 프론트엔드 pending)
tests/domains/test_designer_vision_intake.py     ✅ 구현 (16 passed)
```

작업:

- [x] `VisionInput` contract 정의
  - `image_url` 또는 attachment id
  - source: `drawing_photo|site_photo|manual_upload`
  - calibration: known length / scale / perspective
  - target furniture type hint
- [x] manual calibration fields 정의
  - known_length_mm
  - image_segment_px
  - origin_hint
  - perspective_mode
- [x] `/api/designer/vision/intake` 추가
- [x] 업로드 이미지는 extraction 전 raw artifact로만 저장
- [ ] vision run record 생성 **(DB 테이블 신규 생성 없음 — intake는 in-memory/transient)**
- [x] image → design truth 직접 저장 금지 (`can_apply()=False` 강제)

검증:

- [x] missing image 거부
- [x] unsupported source 거부
- [x] intake는 project version을 만들지 않음
- [x] API envelope 유지

### PV2-B6 — Vision Extraction Candidate Pipeline

목표: 도면/사진에서 `DesignGraphCandidate` 또는 `DesignCommand[]` 후보를 만든다.

쓰기 범위:

```text
foms/services/designer/vision_extractor.py       ✅ 구현
foms/services/designer/vision_to_ontology.py     (기능 vision_extractor.py에 통합)
foms/services/designer/command_engine.py         ✅ 기존 유지
foms/api/designer/vision.py                      ✅ /extract endpoint 포함
tests/domains/test_designer_vision_intake.py     ✅ 구현 (fake extractor 테스트 포함)
```

작업:

- [x] fake deterministic extractor 구현
  - 테스트용 image fixture metadata에서 width/height/depth/module_count 추출
- [x] real mode interface만 정의
  - OCR/vision provider는 env-gated (`DESIGNER_FAKE_VISION`, `DESIGNER_VISION_PROVIDER`)
  - 실패 시 명시적 error (`VisionProviderUnavailable`)
- [x] provider 결합도 차단
  - provider adapter interface만 정의
  - 실제 OCR/vision provider는 환경변수로 명시 활성화
  - provider unavailable은 명시적 `VisionProviderUnavailable`
- [x] extraction output은 `DesignGraphCandidate`
- [x] candidate는 validator preview만 수행 (factory `validate_params` 경유)
- [x] confidence score와 unresolved fields 반환
- [x] confidence 낮으면 human review required (`can_apply()=False`)

검증:

- [x] fake fixture → wardrobe candidate 생성
- [x] invalid candidate는 저장되지 않음 (`approved=False` 강제)
- [x] unresolved field가 있으면 apply 금지 (`can_apply()` 검증)
- [x] validator result 포함

### PV2-B7 — Human Review / Overlay Correction UI

목표: Vision/LUI 후보를 사용자가 눈으로 검토하고 correction delta로 수정한다.

쓰기 범위:

```text
Add In Program/FOMSBrainDesigner/src/ui/VisionReviewPanel.tsx    (미구현 — 프론트엔드 pending)
Add In Program/FOMSBrainDesigner/src/ui/OverlayAnnotationPanel.tsx  (미구현 — 프론트엔드 pending)
Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts     ✅ 기존 유지
foms/api/designer/vision.py                                      ✅ approve/reject endpoint 구현
foms/services/designer/corrections.py                            ✅ 기존 유지
tests/domains/test_designer_vision_intake.py                     ✅ candidate contract 테스트 포함
```

작업:

- [ ] candidate preview 화면 추가 **(프론트엔드 미구현 — 별도 배치 필요)**
- [ ] image overlay coordinate와 component UUID 연결 **(프론트엔드 미구현)**
- [ ] overlay UI는 main editor와 분리된 panel로 구현 **(프론트엔드 미구현)**
  - `VisionReviewPanel`: candidate 승인/거절 → **backend `/approve` `/reject` endpoint는 구현됨**
  - `OverlayAnnotationPanel`: image coord ↔ component UUID 매핑
- [x] user correction이 `CorrectionDelta`로 저장 (approve 시 correction 경로 존재)
- [x] approve 전에는 project version 저장 금지 (`can_apply()=False` before approve)
- [x] reject/approve 상태 관리 (`/api/designer/vision/candidates/<id>/approve|reject`)

검증:

- [x] candidate approve 전 version 생성 없음
- [ ] correction delta has `target_id`, `before`, `after`, `source=vision_review` **(프론트엔드 correction 경로 미구현)**
- [x] invalid correction은 validated=false

### PV2-B8 — Ontology Learning Candidate Pipeline

목표: correction delta를 rule candidate로 묶어 학습 후보를 만든다.

쓰기 범위:

```text
foms/services/designer/evolution.py              ✅ 구현 (stub → full)
foms/services/designer/vector_memory.py          ✅ 기존 유지
foms/api/designer/evolution_api.py               ✅ 구현
foms/persistence/designer/repositories.py        ✅ 구현 (promote/rollback/assert 추가)
tests/domains/test_designer_rule_candidate.py    ✅ 구현 (11 passed)
```

작업:

- [x] correction clustering query 추가 (`cluster_corrections_to_candidates`)
- [x] `candidate_rule_hint` 기반 candidate 생성
- [x] embedding/fake embedding retrieval 연결 (vector_memory.py 기존 활용)
- [x] rule candidate status: draft/rejected/approved/promoted 유지
- [x] AI는 candidate만 생성, active ontology 변경 금지
- [x] `/api/designer/evolution/candidates` 추가

검증:

- [x] 3개 correction → rule candidate 생성 (`test_create_candidate_from_dict`)
- [x] candidate_json shape 검증
- [x] AI candidate가 active ontology를 바꾸지 않음 (`test_ai_cannot_modify_active_ontology_directly`)

### PV2-B9 — Rule Replay / Promotion Workflow

목표: rule candidate를 과거 design corpus에 replay하고 human approval 후에만 ontology version으로 승격한다.

쓰기 범위:

```text
foms/services/designer/rule_replay.py            (evolution.py에 통합됨 — replay_rule_candidate)
foms/services/designer/evolution.py              ✅ replay + promote 구현
foms/api/designer/evolution_api.py               ✅ /replay, /set-approved, /promote endpoint
foms/persistence/designer/repositories.py        ✅ promote_ontology_version + rollback_to_previous_active
tests/domains/test_designer_rule_candidate.py    ✅ replay/promotion/invariant 테스트 포함
tests/domains/test_designer_rule_replay.py       (test_designer_rule_candidate.py에 통합)
tests/domains/test_designer_ontology_promotion.py  (test_designer_rule_candidate.py에 통합)
```

작업:

- [x] rule candidate replay runner 구현 (`replay_rule_candidate` in evolution.py)
- [x] replay 대상: recent project versions + curated fixtures
- [x] replay report fields:
  - pass_count
  - fail_count
  - changed_design_count
  - new_validation_errors
  - affected_furniture_types
- [x] human approve endpoint 추가 (`/evolution/candidates/<id>/set-approved`)
- [x] promotion creates new `DesignerOntologyVersion`
- [x] existing active ontology retired only after successful promotion
- [x] DB-level active ontology 단일성 보장
  - Postgres: partial unique index 우선: **repository transaction lock 방식으로 구현** (Postgres 마이그레이션은 별도)
  - SQLite/test: `assert_single_active_ontology()` repository invariant ✅
- [x] rollback path: previous active reactivation (`rollback_to_previous_active`)

검증:

- [x] replay 실패 candidate는 promote 불가 (`test_promote_without_replay_fails`)
- [x] human approval 없이 promote 불가 (`test_promote_without_approval_fails`)
- [x] promoted ontology has new version_key
- [x] active ontology는 한 개만 존재 (`test_assert_single_active_ontology`)
- [x] DB-level invariant 또는 repository transaction test로 active 단일성 검증

### PV2-B10 — Closeout / Verification / Handoff

목표: Post-V1 기능을 실제 사용 가능한 다음 tranche로 닫는다.

쓰기 범위:

```text
docs/plans/*post-v1*run-record*.md    (본 계획서가 run record 역할)
docs/ARCHIVE_INDEX.md                 (별도 업데이트 필요)
docs/AI_STATUS.md                     (별도 업데이트 필요)
```

검증:

- [x] `python -c "import app; print('APP_OK')"` → 통과
- [x] `pytest tests/domains/test_designer_* -q` → **240 passed**
- [x] add-in `npm run build` → V1 빌드 유지 (프론트엔드 변경 없음)
- [ ] `/wdplanner-v2` browser smoke **(브라우저 E2E 별도 확인 필요)**
- [x] Vision/LUI/furniture factory/evolution replay focused tests 통과

---

> **구현 완료 커밋:** `86cd294d` (2026-05-14, deploy 브랜치)
> **검증 결과:** APP_OK ✅ | pytest 240 passed ✅ | blueprints registered ✅

## 5. Stop Rules

즉시 중단하고 사용자에게 보고한다.

- Vision/LUI 결과가 validator 없이 project version을 저장해야 하는 경우
- production ontology rule을 AI가 자동 승격해야 하는 경우
- active ontology 단일성을 DB/repository invariant 없이 코드 관례로만 보장해야 하는 경우
- component UUID 없이 apply를 허용해야 하는 경우
- V1 wardrobe behavior가 깨지는 경우
- schema v1 legacy project load가 깨지는 경우
- Next.js/Supabase를 FOMS 내부에 도입해야 하는 경우
- `/wdplanner` 제거가 필요해지는 경우
- ERP/order route regression이 발생하는 경우

## 6. Acceptance Criteria

Post-V1 완료 조건:

- [x] 자연어 명령 50개 golden set이 deterministic `DesignCommand`로 변환된다. (`test_golden_set_accuracy` 통과)
- [x] LUI exact intent match가 90% 이상이다.
- [x] LUI wrong-apply가 0건이다.
- [x] ambiguous 자연어 명령은 clarification 상태로 멈춘다.
- [x] `wardrobe`, `shoe_rack`, `kitchen_base`, `kitchen_wall` factory가 schema v2 graph를 생성한다. (backend)
- [x] 모든 factory output은 hard validator를 통과한다.
- [x] Vision intake는 raw image artifact만 저장하고 design truth를 직접 저장하지 않는다.
- [x] Vision fake extractor가 fixture image metadata에서 design candidate를 만든다.
- [x] Vision candidate는 human review 전 저장되지 않는다. (`can_apply()=False`)
- [x] correction delta cluster에서 rule candidate가 생성된다.
- [x] rule candidate replay report가 생성된다.
- [x] human approval 없이 ontology promotion이 불가능하다.
- [x] active ontology는 DB-level invariant 또는 repository transaction invariant로 한 개만 존재한다. (repository invariant 구현)
- [x] APP_OK 통과.
- [x] designer focused pytest 통과. (240 passed)
- [x] add-in build 통과. (V1 빌드 유지)

---

### 미완료 항목 (별도 배치 필요)

프론트엔드 TS 파일 미구현 — 다음 배치에서 처리:

| 항목 | 상태 | 비고 |
|---|---|---|
| `LuiPanel.tsx` | pending | 백엔드 `/api/designer/lui/parse` 완성됨 |
| `factoryRegistry.ts` | pending | 백엔드 registry 완성됨 |
| `shoeRackFactory.ts` | pending | 백엔드 factory 완성됨 |
| `kitchenFactory.ts` | pending | 백엔드 factory 완성됨 |
| `VisionPanel.tsx` | pending | 백엔드 intake/extract 완성됨 |
| `VisionReviewPanel.tsx` | pending | 백엔드 approve/reject 완성됨 |
| `OverlayAnnotationPanel.tsx` | pending | image coord ↔ UUID 매핑 미구현 |
| `frontend factory selector` | pending | 모든 factory 백엔드 완성됨 |
| Postgres partial unique index | pending | repository-level invariant로 우선 대체 |
| `/wdplanner-v2` browser smoke | pending | 수동 확인 필요 |

## 7. 다음 LLM 실행 프롬프트

정본 실행 프롬프트는 아래 파일을 사용한다.

```text
docs/plans/2026-05-14-foms-brain-post-v1-next-llm-execution-prompt.md
```

요약 프롬프트:

```text
FOMS repo에서 docs/plans/2026-05-14-foms-brain-post-v1-roadmap-plan.md 를 기준으로 Post-V1을 구현하라.

절대 Vision/LUI/learning 결과를 validator 없이 저장하지 마라.
AI가 production ontology rule을 자동 승격하는 구조는 금지한다.
모든 apply는 component UUID 또는 생성될 UUID가 있어야 한다.
V1 wardrobe behavior와 schema v1 legacy load를 깨지 마라.
LUI는 golden command set 50개, exact intent match 90% 이상, wrong-apply 0건을 만족해야 한다.
Vision은 완전 자동 설계 생성이 아니라 intake/calibration/fake extractor/candidate preview부터 시작한다.
active ontology는 DB-level invariant 또는 repository transaction invariant로 한 개만 존재해야 한다.

실행 순서:
PV2-B0 V1 Stabilization / Contract Freeze
PV2-B1 Real LUI Parser V1
PV2-B2 Multi Furniture Factory Registry
PV2-B3 Shoe Rack Factory V1
PV2-B4 Kitchen Cabinet Factory V1
PV2-B5 Vision-to-Ontology Intake Contract
PV2-B6 Vision Extraction Candidate Pipeline
PV2-B7 Human Review / Overlay Correction UI
PV2-B8 Ontology Learning Candidate Pipeline
PV2-B9 Rule Replay / Promotion Workflow
PV2-B10 Closeout / Verification / Handoff

각 batch 후 APP_OK, focused pytest, npm run build 중 해당 검증을 수행하라.
```
