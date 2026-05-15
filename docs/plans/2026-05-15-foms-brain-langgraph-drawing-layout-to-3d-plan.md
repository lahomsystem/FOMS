# FOMS Brain LangGraph Drawing Layout to 3D Plan
> 작성일: 2026-05-15 | 상태: 🟡 계획 수립 | 대상: FOMS-DEV / deploy 우선, production 별도 승인 전 금지

## 0. GDM Truth Summary

### 0.1 현재 판정

현재 FOMS Brain Designer에는 다음 조각이 이미 존재한다.

- Gemini 도면 추출: `design_understanding.layout_graph`, `block_candidates`, `learned_design_category` 추출 프롬프트가 존재한다.
- Design Kernel: `DesignGraph -> Assembly -> Module -> Component -> Constraint` schema v2 온톨로지가 존재한다.
- 3D 편집기: React/R3F가 `DesignGraph.components`를 부재 단위 mesh로 렌더링하고 선택/치수 수정/블록 추가/삭제를 처리한다.
- Command Engine: `DesignCommand -> preview -> validate -> apply` 경로가 존재한다.
- LangGraph MVP: `langgraph_workflows.py`가 AI 직접 mutation을 금지하고 `DesignCommand` preview/apply를 경유하도록 설계되어 있다.
- Learning Memory: 승인된 설계는 `DesignerDesignCase`에 저장되고, tags/archetype 후보 추출 경로가 있다.

그러나 핵심 연결이 아직 빠져 있다.

```text
Gemini design_understanding.layout_graph
  -> 실제 FOMS DesignGraph.components 변환
  -> 3D 편집기에 도면 구조 후보 preview
  -> 사용자의 세부 수정
  -> 승인된 결과를 학습/온톨로지 후보로 누적
```

현재 승인 저장 경로는 주로 `furniture_type + factory_params`로 built-in factory를 다시 호출한다. 이 방식은 기본 붙박이장/신발장/주방장에는 유효하지만, 도면이 가진 세부 칸 구조, 선반 위치, 도어 분할, 재질/텍스처, 커스텀 가구 레이아웃을 그대로 3D 부재로 복원하기에는 부족하다.

### 0.2 Root Cause

근본 원인은 `DrawingUnderstanding`과 `DesignGraph` 사이의 결정적 변환 계층이 없다는 점이다.

하위 원인은 6개다.

1. `ontology_mapper.py`는 추출값을 factory params로 줄이는 경로가 중심이며, `layout_graph`를 `Component[]`로 변환하지 않는다.
2. `DesignerExtractionCandidate`는 DB 후보로 존재하지만, 실제 3D preview용 `design_graph_candidate_json` 계약이 명확하지 않다.
3. `designerStore.loadCandidateGraph()`는 후보 payload의 완성된 `design_graph`보다 `furniture_type/factory_params` 기반 로컬 재생성에 의존한다.
4. LangGraph는 현재 자연어 command 보조 흐름 중심이며, 도면 추출 후보를 3D 후보로 변환하는 별도 graph가 없다.
5. 도면 학습 결과가 `internal_structure_json/tags_json`에 저장되기 시작했지만, 이 정보를 다음 3D 후보 생성에 retrieval 근거로 사용하는 노드가 없다.
6. no-op/placeholder 성공 저장을 차단하는 제품급 게이트가 LangGraph 전체 경로에 일관되게 적용되어야 한다.

### 0.3 목표 판정

LangGraph는 3D 구조를 직접 조작하는 엔진이 아니다. LangGraph는 다음을 오케스트레이션하는 control plane이다.

```text
도면/명령/사례 입력
  -> context + ontology + memory 조회
  -> 후보 생성
  -> deterministic mapper
  -> validator
  -> human review interrupt
  -> project version 저장
  -> design case memory 저장
  -> archetype/rule/ontology candidate 생성
```

AI/Gemini는 후보와 근거를 만든다. FOMS의 deterministic mapper, command engine, validator, replay gate가 실제 저장 가능 여부를 결정한다.

## 1. What - 무엇을 만든다

### 1.1 최종 사용자 흐름

```text
도면 업로드
  -> Gemini가 치수/부품/레이아웃/블록 후보 추출
  -> DesignerDrawingExtraction 저장
  -> DesignerExtractionCandidate 저장
  -> LangGraph drawing_layout_to_3d_graph 실행
  -> 유사 승인 사례 + active ontology 조회
  -> layout_graph_to_design_graph 변환
  -> validator / constraint 검사
  -> 3D 편집기에 후보 graph preview
  -> 사용자가 부재 선택, 치수/위치/재질 수정
  -> 모든 수정은 DesignCommand preview/apply 경유
  -> 승인 시 project version + DesignerDesignCase 저장
  -> tags/archetype/rule candidate 생성
  -> replay + human approval 후 ontology 승격
```

### 1.2 핵심 산출물

1. `layout_graph_to_design_graph.py`
   - Gemini `design_understanding.layout_graph`를 FOMS schema v2 `DesignGraph` 후보로 변환한다.
   - LLM 호출 없이 deterministic 변환만 수행한다.
   - 추정이 필요한 경우 값을 지어내지 않고 `unresolved_fields`와 `mapping_warnings`로 남긴다.

2. `DesignGraphCandidate` DB/API 계약
   - `DesignerExtractionCandidate` 또는 별도 candidate row에 다음 JSON을 저장한다.
   - `design_graph_candidate_json`
   - `mapping_report_json`
   - `validation_json`
   - `preview_allowed`
   - `approve_blocking_reasons`

3. LangGraph workflow
   - 신규 graph name: `drawing_layout_to_3d_graph`
   - 도면 extraction/candidate를 입력으로 받아 3D preview 후보까지 만든다.
   - project version 저장은 human approval 이후에만 수행한다.

4. 3D 편집기 연결
   - iframe/add-in은 candidate payload에 `design_graph`가 있으면 그대로 로드한다.
   - `furniture_type/factory_params` 로컬 재생성은 fallback이 아니라 built-in factory preview 전용 경로로 격리한다.
   - unsupported/custom layout은 실패처럼 보이지 않게 명확한 review 상태로 표시한다.

5. 학습/온톨로지 연결
   - 승인된 3D graph만 `DesignerDesignCase`로 저장한다.
   - correction delta와 repeated design case evidence만 rule/archetype 후보가 된다.
   - production ontology 자동 승격은 금지한다.

## 2. Architecture

### 2.1 책임 분리

| 계층 | 책임 | 금지 |
|---|---|---|
| Gemini Provider | 도면 이해, JSON 후보 생성, 근거 추출 | DB 저장, project version 생성 |
| LangGraph | workflow 상태, memory/ontology 조회, interrupt, 게이트 제어 | 검증 우회, 직접 design_json mutation |
| Layout Mapper | layout_graph -> DesignGraph 후보 변환 | LLM 호출, 임의 추측 |
| Command Engine | 사용자의 편집 command preview/apply | validator 우회 mutation |
| Validator/Constraint | 저장 가능성 판정 | warning/error 숨김 |
| Learning/Evolution | 승인 결과 누적, 후보 생성, replay | production ontology 자동 승격 |

### 2.2 LangGraph 노드 설계

```text
START
  -> load_run_context
  -> load_extraction_candidate
  -> retrieve_design_memory
  -> load_active_ontology
  -> build_layout_mapping_input
  -> map_layout_to_design_graph
  -> validate_design_graph_candidate
  -> decide_preview_or_block
  -> human_review_interrupt
  -> persist_approved_design
  -> save_design_case_memory
  -> propose_learning_candidates
  -> END
```

노드별 계약:

| 노드 | 입력 | 출력 | 실패 정책 |
|---|---|---|---|
| `load_extraction_candidate` | `candidate_id` | extraction, parsed_json, candidate row | 없으면 failed |
| `retrieve_design_memory` | type/tags/dimensions | similar cases | 실패 시 warning, 빈 배열 허용 |
| `build_layout_mapping_input` | parsed_json + memory + ontology | normalized input | 필수 치수 없으면 block |
| `map_layout_to_design_graph` | normalized input | `design_graph_candidate`, report | 추정 필요 시 unresolved |
| `validate_design_graph_candidate` | graph candidate | validation_json | error 있으면 approval block |
| `decide_preview_or_block` | validation + unresolved | preview state | preview 가능/승인 불가 분리 |
| `human_review_interrupt` | graph + report | user decision/corrections | approve/reject/correct |
| `persist_approved_design` | approved graph | project_version_id | invalid/no-op 저장 금지 |
| `save_design_case_memory` | project version + extraction | design_case_id | 실패 시 rollback 또는 명시 failed |
| `propose_learning_candidates` | design case/corrections | archetype/rule candidates | production 승격 금지 |

### 2.3 데이터 계약

#### LayoutMappingInput

```json
{
  "source_extraction_id": 123,
  "source_candidate_id": 456,
  "furniture_type": "custom_storage",
  "site_size": {"width_mm": 3145, "height_mm": 2150, "depth_mm": 600},
  "layout_graph": {
    "overall_structure": "linear_bays",
    "zones": [],
    "relations": []
  },
  "block_candidates": [],
  "parts_table": [],
  "learned_design_category": {},
  "similar_cases": [],
  "ontology_rules": {}
}
```

#### LayoutMappingResult

```json
{
  "design_graph": {
    "schema_version": 2,
    "unit": "mm",
    "assembly": {},
    "components": [],
    "constraints": [],
    "relations": [],
    "metadata": {}
  },
  "mapping_report": {
    "mapped_components": [],
    "unresolved_fields": [],
    "warnings": [],
    "source_evidence": []
  },
  "confidence": 0.0,
  "preview_allowed": false,
  "approval_blocking_reasons": []
}
```

규칙:

- `preview_allowed=true`는 3D 확인 가능을 의미한다.
- `approval_blocking_reasons=[]`일 때만 저장 승인 가능하다.
- preview 가능과 approve 가능을 같은 의미로 쓰지 않는다.
- `confidence`가 낮아도 preview는 가능할 수 있지만, 저장은 unresolved/validator gate를 통과해야 한다.

### 2.4 Checkpoint, Resume, Locking Contract

LangGraph interrupt/resume은 명시적인 영속화 계약을 가져야 한다.

현재 코드 기준 1차 저장소는 `designer_ai_runs`다.

```text
designer_ai_runs
  id
  graph_name
  graph_version
  thread_id
  status              # queued / running / interrupt / succeeded / failed / cancelled
  input_json
  state_json          # checkpoint payload
  output_json
  error_text
  updated_at
```

계약:

- `designer_ai_runs.thread_id`는 LangGraph thread/checkpoint key의 source of truth다.
- `state_json`은 interrupt 직전 전체 graph state를 저장한다.
- `state_json`에는 `candidate_id`, `project_id`, `project_version_id`, `source_extraction_id`, `resume_token`, `interrupt_expires_at`을 포함한다.
- `GET /api/designer/ai-runs/<id>`는 현재 checkpoint 상태를 반환한다.
- `POST /api/designer/ai-runs/<id>/resume`은 `status='interrupt'`이고 TTL이 만료되지 않은 run만 허용한다.
- TTL 기본값은 24시간이다. 만료된 interrupt는 `cancelled` 또는 `failed_expired`에 준하는 명시 상태로 전환하고 재실행을 요구한다.
- 장기적으로 실제 LangGraph PostgreSQL checkpointer를 도입하되, 도입 전에도 `designer_ai_runs.thread_id + state_json`을 checkpoint 계약으로 테스트한다.

동시성 계약:

- 같은 `candidate_id`에 대한 review/approve/persist는 candidate 단위 advisory lock 또는 `SELECT ... FOR UPDATE`로 보호한다.
- `DesignerExtractionCandidate.status` 상태 전이는 다음만 허용한다.

```text
pending_review -> corrected -> approved
pending_review -> rejected
corrected      -> rejected
approved       -> promoted_to_project_version
```

- 이미 `approved` 또는 `promoted_to_project_version` 상태인 candidate를 다시 approve하면 HTTP 409를 반환한다.
- 같은 `project_id`에 두 LangGraph run이 동시에 저장을 시도하면 `DesignerProject.current_version_id` 비교 기반 optimistic swap 또는 project row lock을 사용한다.
- project version 저장은 "현재 version id 확인 -> 새 version 생성 -> current_version_id 갱신"을 하나의 transaction 안에서 처리한다.
- 중복 `DesignerDesignCase` 생성을 막기 위해 `(project_version_id, approved_extraction_id, source_candidate_id)` 조합 중 가능한 키를 idempotency key로 사용한다.

### 2.5 Authorization Contract

Designer API는 로그인 여부만으로 쓰기 권한을 허용하지 않는다. 최소 role 계약은 다음과 같다.

| Surface | Action | Role |
|---|---|---|
| Drawing upload/extract | 본인 프로젝트 또는 접근 가능한 주문에 도면 업로드 | user/designer/admin |
| Candidate preview | 본인이 생성했거나 접근 권한 있는 project candidate 조회 | user/designer/admin |
| Candidate correct | candidate owner 또는 project 접근 권한자 수정 | user/designer/admin |
| Candidate approve-and-save | project 접근 권한자, unresolved/validator 통과 필요 | designer/admin 또는 owner-user |
| AI run create/resume | 해당 project 접근 권한자 | user/designer/admin |
| Ontology draft create/pass/promote | 전역 설계 규칙 변경 | admin |
| Ontology draft edit/replay | 검수/설계 담당자 | designer/admin |

규칙:

- candidate approve는 본인이 업로드한 도면이거나 해당 project/order 접근 권한이 있는 경우만 허용한다.
- ontology promote는 전역 영향이 있으므로 admin only다.
- system role은 내부 worker/LangGraph에서만 사용하고 사용자 세션으로 가장하지 않는다.
- 권한 실패는 `HTTP 403 + {"success": false, "error": "forbidden", "data": {"required_role": ...}}` 형식을 사용한다.

## 3. Ontology Repository and Methodology

### 3.1 현재 온톨로지 저장소

현재 FOMS의 온톨로지 저장소는 PostgreSQL 테이블이다.

```text
designer_ontology_versions
  id
  version_key
  status              # active / draft / retired
  rules_json          # 실제 온톨로지/규칙 JSON 저장소
  created_at
```

코드 위치:

- ORM: `foms/persistence/designer/models.py`의 `DesignerOntologyVersion`
- Repository: `foms/persistence/designer/repositories.py`
- Active 조회 API: `GET /api/designer/ontology/current`
- 승격 경로: `foms/services/designer/evolution.py`
- DB 단일 active 보장: `migrations/versions/designer_active_ontology_unique_index.py`

중요 구분:

- `foms/services/designer/ontology_types.py`와 `Add In Program/FOMSBrainDesigner/src/domain/ontologyTypes.ts`는 DesignGraph shape의 코드 기준이다.
- 실제 운영/버전 저장소는 `designer_ontology_versions.rules_json`이다.
- 현재 API는 active ontology 조회와 rule candidate 승격 중심이다.
- 사용자가 draft ontology를 열어 관계를 직접 수정하는 전용 UI/API는 아직 없다.

### 3.2 검색한 방법론과 채택 기준

확인한 1차/준1차 자료:

- Stanford/Protégé `Ontology Development 101`: domain/scope, reuse, terms, class hierarchy, properties, facets, instances 순서의 실무형 작성 절차.
- METHONTOLOGY: specification, conceptualization, formalization, implementation, maintenance를 포함하는 공학적 lifecycle.
- NeOn Methodology: ontology networks, reuse/reengineering, collaboration, dynamic evolution을 강조하는 scenario-based 방법론.
- W3C OWL 2: class/property/individual/relation 및 reasoning 가능한 표준 표현.
- W3C SHACL: RDF graph validation을 위한 constraint language.

FOMS 가구 설계에는 **NeOn scenario-based methodology를 주 방법론으로 채택**한다.

이유:

- FOMS는 처음부터 완전히 새 ontology를 쓰는 것이 아니라 기존 코드의 `DesignGraph`, 부품표, 도면 fixture, 사용자 수정, 승인 사례를 계속 재사용한다.
- 가구 설계 카테고리는 계속 진화하므로 one-shot taxonomy보다 재사용/재공학/병합/버전 관리가 중요하다.
- 사용자와 AI가 함께 수정하는 협업형 ontology lifecycle이 필요하다.
- 커스텀 가구는 무한하므로 작은 모듈 ontology network를 쌓고, 반복 증거가 쌓인 패턴만 승격해야 한다.

보조 적용:

- Ontology 101은 각 draft를 만들 때 micro-process로 사용한다.
- METHONTOLOGY는 FOMS 내부 lifecycle/checklist 이름으로 사용한다.
- OWL/SHACL은 당장 DB 저장 형식이 아니라 export/validation 호환 목표로 둔다.
- FOMS runtime 저장 형식은 우선 `rules_json`이다. OWL/Turtle export는 별도 B단계에서 추가한다.

### 3.3 FOMS Furniture Ontology Method

FOMS용 제작 절차는 다음으로 고정한다.

```text
1. Scope
   어떤 설계 범위를 다루는지 정의
   예: 붙박이장, TV장, 신발장, 주방 하부장, 커스텀 수납

2. Competency Questions
   이 ontology가 답해야 할 질문 정의
   예: "이 도면의 좌측 세로 구획은 어떤 module인가?"
       "이 선반은 어느 module의 child component인가?"
       "이 도어는 어떤 rail/hardware와 연결되는가?"

3. Term Extraction
   도면, 부품표, design_understanding, 사용자 correction에서 용어 추출
   예: EP, SR, DOOR, 옷봉, 보조목, 선반, 서랍, 열린공간

4. Conceptualization
   Class / Role / Relation / Constraint 후보 생성
   예: Component, Module, Zone, Material, Hardware, supports, contains, adjacent_to

5. Formalization
   FOMS `rules_json` draft ontology로 변환
   예: allowed_component_roles, relation_types, cardinality, validation_shapes

6. Human Review
   사용자가 class/relation/constraint를 직접 확인하고 수정

7. Replay
   기존 fixture/design case에 적용해 validation regression 확인

8. Pass / Promote
   사용자가 pass하면 draft -> active 후보로 승격
   production 승격은 별도 승인 없이는 금지

9. Maintenance
   새 도면/수정/실패 사례를 evidence로 다시 draft 후보 생성
```

### 3.4 Draft Ontology JSON 계약

`rules_json`은 다음 구조를 기본으로 한다.

Source of Truth:

- DB row의 `designer_ontology_versions.version_key`가 ontology version 식별자의 source of truth다.
- `rules_json.version`은 사람이 읽는 payload 내부 버전/작성 이력 값이며, 저장 시 `version_key`와 동일하게 맞추거나 `payload_version`으로 취급한다.
- 불일치가 발견되면 API는 저장을 거부하거나 `rules_json.version = version_key`로 명시적으로 정규화한다.

```json
{
  "version": "furniture-ontology-draft-YYYYMMDD-N",
  "methodology": {
    "primary": "NeOn scenario-based ontology network",
    "micro_process": "Ontology Development 101",
    "lifecycle": "METHONTOLOGY-style specification/conceptualization/formalization/maintenance"
  },
  "scope": {
    "domain": "furniture_design",
    "base_furniture_types": ["wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"],
    "learned_categories": []
  },
  "competency_questions": [],
  "classes": [],
  "component_kinds": [],
  "component_roles": [],
  "materials": [],
  "relations": [],
  "constraints": [],
  "validation_shapes": [],
  "evidence": {
    "source_extraction_ids": [],
    "source_design_case_ids": [],
    "source_correction_ids": [],
    "source_archetype_candidate_ids": []
  },
  "review": {
    "status": "draft",
    "reviewed_by_user_id": null,
    "review_notes": [],
    "change_log": []
  }
}
```

관계 예시:

```json
{
  "relations": [
    {
      "key": "contains_component",
      "label_ko": "포함한다",
      "from_class": "Module",
      "to_class": "Component",
      "inverse": "is_component_of",
      "cardinality": {"min": 1},
      "editable": true
    },
    {
      "key": "adjacent_to",
      "label_ko": "인접한다",
      "from_class": "Component",
      "to_class": "Component",
      "symmetric": true,
      "editable": true
    }
  ]
}
```

### 3.5 AI Draft 생성 흐름

LangGraph에 ontology draft graph를 추가한다.

운영 한도:

- `ontology_draft_graph`는 manual trigger only다.
- 도면 업로드 1건의 기본 Gemini call budget에는 포함하지 않는다.
- 자동 배치로 돌릴 경우 관리자 승인된 maintenance window에서만 실행한다.
- draft 생성은 기존 `DesignerDesignCase`, correction, extraction JSON을 우선 사용하고, Gemini 재호출은 명시적으로 요청된 경우에만 허용한다.

```text
approved design cases / corrections / drawing understanding
  -> extract ontology terms
  -> cluster terms and relations
  -> build draft rules_json
  -> save DesignerOntologyVersion(status='draft')
  -> user review interrupt
  -> user pass OR edit relations/classes/constraints
  -> replay
  -> promote only after human pass + replay success
```

신규 graph name:

```text
ontology_draft_graph
```

필수 노드:

| 노드 | 책임 |
|---|---|
| `load_ontology_sources` | design cases, corrections, extraction understanding 조회 |
| `extract_terms` | 부품/역할/관계/제약 후보 추출 |
| `cluster_concepts` | 동의어/유사 관계 묶기 |
| `build_draft_rules_json` | FOMS ontology JSON 생성 |
| `save_draft_ontology` | `DesignerOntologyVersion(status='draft')` 저장 |
| `human_review_interrupt` | 사용자가 pass/edit/reject |
| `apply_user_ontology_edits` | 관계/클래스/제약 직접 수정 반영 |
| `replay_ontology` | fixture/design case regression |
| `promote_if_passed` | human pass + replay success일 때만 active 후보 승격 |

### 3.6 Draft Ontology Review UI

신규 UI는 `온톨로지 검수` 패널로 둔다.

기능:

- draft ontology 목록 보기
- class tree 보기
- relation graph 보기
- selected relation 편집
  - `from_class`
  - `to_class`
  - `relation_type`
  - inverse relation
  - cardinality
  - required/optional
  - validator severity
- component role mapping 편집
- material/hardware mapping 편집
- AI가 제안한 근거 보기
  - source drawing
  - source design case
  - source correction
- `Pass`
- `Reject`
- `Edit and Save Draft`
- `Replay`
- `Promote` 버튼은 replay success + pass 이후에만 활성화

금지:

- AI가 만든 draft를 자동 active로 승격하지 않는다.
- 사용자가 보지 않은 draft를 production에 반영하지 않는다.
- relation이 불명확한 경우 임의로 required constraint로 만들지 않는다.
- UI에서 관계를 수정해도 replay 전에는 active ontology에 반영하지 않는다.

### 3.7 필요한 API

신규/보강 API:

| Method | Path | 역할 | Role |
|---|---|---|---|
| `GET` | `/api/designer/ontology/current` | active 조회, 기존 유지 | user/designer/admin |
| `GET` | `/api/designer/ontology/drafts` | draft 목록 | designer/admin |
| `POST` | `/api/designer/ontology/drafts/from-cases` | AI 분석 기반 draft 생성 | admin |
| `GET` | `/api/designer/ontology/drafts/<id>` | draft 상세 | designer/admin |
| `PUT` | `/api/designer/ontology/drafts/<id>` | 사용자 직접 수정 저장 | designer/admin |
| `POST` | `/api/designer/ontology/drafts/<id>/replay` | replay 검증 | designer/admin |
| `POST` | `/api/designer/ontology/drafts/<id>/pass` | 사용자 pass | admin |
| `POST` | `/api/designer/ontology/drafts/<id>/reject` | reject | designer/admin |
| `POST` | `/api/designer/ontology/drafts/<id>/promote` | pass + replay success 후 active 승격 | admin |

Role 규칙:

- 일반 user는 active ontology 조회만 가능하다.
- designer는 draft 검수/수정/replay까지 가능하다.
- admin만 draft 생성 trigger, pass, promote를 수행할 수 있다.
- system role은 LangGraph 내부 작업에만 쓰며 public HTTP endpoint 권한으로 노출하지 않는다.

### 3.8 Acceptance

- AI가 분석한 내용은 `DesignerOntologyVersion(status='draft')`로 저장된다.
- 사용자는 draft의 class/relation/constraint를 UI에서 직접 수정할 수 있다.
- pass 전 draft는 active ontology로 쓰이지 않는다.
- replay fail이면 promote가 막힌다.
- active ontology는 DB partial unique index로 하나만 유지된다.
- draft ontology는 source evidence를 보존한다.
- custom furniture category는 `furniture_type` 문자열을 늘리지 않고 `learned_categories`와 relation/constraint 확장으로 표현한다.

## 4. Implementation Batches

### B0 - Contract Freeze and Regression Baseline

B0은 구현 PR이 아니라 선결 contract freeze다. B1/B2/B4 mock 작업 전에 최소 계약과 실패 응답 형식을 고정한다.

대상:

- `foms/services/designer/gemini_provider.py`
- `foms/services/designer/ontology_types.py`
- `foms/services/designer/ontology_mapper.py`
- `Add In Program/FOMSBrainDesigner/src/domain/ontologyTypes.ts`
- `tests/domains/test_designer_*`

작업:

- `layout_graph`, `block_candidates`, `learned_design_category`의 최소 계약을 문서화한다.
- `DesignGraphCandidate`와 `MappedCandidate`의 의미를 분리한다.
- no-op patch 저장 금지 테스트를 먼저 고정한다.
- `custom_storage`는 unsupported가 아니라 generic/custom layout candidate로 다룬다.

검증:

```powershell
python -m pytest tests/domains/test_designer_gemini_provider.py tests/domains/test_designer_ontology_mapper.py tests/domains/test_designer_ai_runs.py -q
```

### B1 - Deterministic Layout Graph Mapper

생성:

- `foms/services/designer/layout_graph_mapper.py`
- `tests/domains/test_designer_layout_graph_mapper.py`

작업:

- `layout_graph.zones`를 `Assembly.modules`와 `Component[]`로 변환한다.
- `block_candidates`를 shelf/door/drawer/hardware/cutout component로 변환한다.
- `parts_table`의 `[SR]`, `[EP]`, `[DOOR]`, 보조목, 옷봉 등을 role/material hint로 반영한다.
- 치수 누락, 겹침, parent 불명확, material 불명확은 unresolved/report에 남긴다.
- mapper는 절대 Gemini를 재호출하지 않는다.

Acceptance:

- 3칸 붙박이장 fixture가 3 modules + panels/shelves/doors로 변환된다.
- TV장/custom_storage fixture가 `assembly.type=custom_storage`와 component mesh로 preview 가능하다.
- 필수 치수 누락 시 저장은 차단되고, preview 가능 여부는 report에 명확히 나온다.
- 모든 component id는 UUID 또는 안정적인 unique id다.
- validator error가 있으면 approve가 막힌다.

### B2 - Candidate Persistence Contract

대상:

- `foms/persistence/designer/models.py`
- `migrations/versions/*`
- `foms/api/designer/drawings.py`
- `foms/services/designer/drawing_intake_pipeline.py`
- `tests/domains/test_designer_drawing_review_contract.py`

작업:

- `DesignerExtractionCandidate`에 preview graph 계약을 추가한다.
  - 권장 컬럼:
    - `design_graph_candidate_json JSON`
    - `mapping_report_json JSON`
    - `validation_json JSON`
    - `preview_allowed BOOLEAN`
- DB migration은 `ADD COLUMN IF NOT EXISTS` 안전 형태와 Alembic revision 정합을 함께 검증한다.
- 기존 candidate row backfill 정책을 migration 또는 startup schema repair에 명시한다.
  - `design_graph_candidate_json = NULL`
  - `mapping_report_json = {"warnings": ["legacy_candidate_requires_reextract"]}`
  - `validation_json = {}`
  - `preview_allowed = false`
  - `approval_blocking_reasons = ["legacy_candidate_requires_reextract"]`
  - legacy row는 3D load/approve를 허용하지 않고 재추출 또는 remap 버튼으로 유도한다.
- upload/extract 후 candidate row가 3D preview에 필요한 payload를 갖게 한다.
- approve-and-save는 `factory_params`가 아니라 승인된 `design_graph_candidate_json`을 우선 사용한다.
- approve endpoint는 candidate row를 lock으로 보호하고 상태 전이를 검증한다.

Acceptance:

- 서버 재시작 후에도 candidate preview/approve가 가능하다.
- process-local candidate store 없이 동작한다.
- unresolved/validator error가 있으면 approve API는 `HTTP 422 + {"success": false, "error": "approve_blocked", "data": {"reasons": [...]}}`를 반환한다.
- legacy candidate row는 `HTTP 422`와 `legacy_candidate_requires_reextract` reason을 반환한다.
- 이미 approve/persist된 candidate 재승인은 `HTTP 409`로 거부된다.

### B3 - LangGraph Drawing Layout Workflow

대상:

- `foms/services/designer/langgraph_workflows.py`
- `foms/api/designer/ai_runs.py`
- `foms/persistence/designer/models.py`
- `tests/domains/test_designer_ai_runs.py`

작업:

- 기존 `design_assist_graph`와 별도로 `drawing_layout_to_3d_graph`를 추가한다.
- `input_json`은 `candidate_id`, `project_id`, optional `target_version_id`를 받는다.
- graph state에 다음 필드를 추가한다.
  - `source_extraction_id`
  - `source_candidate_id`
  - `similar_cases`
  - `layout_mapping_input`
  - `design_graph_candidate`
  - `mapping_report`
  - `preview_allowed`
  - `approval_blocking_reasons`
- `needs_interrupt=true`일 때 3D preview payload와 report를 `state_json`에 저장한다.
- resume approve 시 validator 재검증 후 project version/design case를 저장한다.
- no-op/empty graph는 succeeded가 아니라 failed 또는 blocked가 되어야 한다.
- PostgreSQL checkpointer 전략을 명시한다.
  - Phase 1: `designer_ai_runs.thread_id + state_json`을 checkpoint store로 사용한다.
  - Phase 2: LangGraph PostgreSQL checkpointer를 붙여 `thread_id` 기준으로 native checkpoint를 저장한다.
  - 두 phase 모두 `state_json`에는 resume에 필요한 최소 payload를 중복 저장한다.
- interrupt TTL 기본값은 24시간이며, 만료 후 resume은 `HTTP 409`로 거부한다.
- resume은 `run.status == "interrupt"`이고 `resume_token`이 일치할 때만 가능하다.
- 같은 `project_id/candidate_id`에 대한 persist는 advisory lock 또는 `SELECT FOR UPDATE`로 보호한다.

Acceptance:

- candidate_id 없는 run은 failed.
- valid candidate는 interrupt 상태로 3D preview payload를 가진다.
- reject resume은 cancelled.
- approve resume은 valid graph만 저장한다.
- no-op patch `{}`로 project version이 생성되지 않는다.
- interrupt 상태 run은 서버 재시작 후에도 `GET /api/designer/ai-runs/<id>`로 복구된다.
- TTL 만료 interrupt는 저장 없이 재실행을 요구한다.

### B4 - 3D Editor Candidate Load

대상:

- `Add In Program/FOMSBrainDesigner/src/App.tsx`
- `Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts`
- `Add In Program/FOMSBrainDesigner/src/ui/DrawingReviewWorkspace.tsx`
- `templates/designer/wdplanner_v2.html`
- browser QA/gstack specs

작업:

- `loadCandidateGraph()`가 `candidatePayload.design_graph`를 우선 로드한다.
- `furniture_type/factory_params` 경로는 built-in quick preview로만 유지한다.
- iframe postMessage에는 ack를 요구한다.
- 실패 시 성공 toast 금지.
- mapping report, unresolved, validator result를 review UI에 표시한다.
- `unresolved_fields`는 인라인 편집 폼으로 사용자가 보정할 수 있게 한다.
- 보정 후 `remap` 버튼은 기존 Gemini 재호출 없이 `layout_graph_mapper`를 다시 실행한다.
- 사용자가 3D에서 수정한 내용은 `DesignCommand` 또는 store edit delta로 추적한다.

Acceptance:

- 도면 후보 로드 후 3D scene component 수가 0이면 성공 처리하지 않는다.
- custom_storage 후보도 generic component graph가 있으면 preview된다.
- unsupported/invalid 후보는 왜 막혔는지 UI에 표시된다.
- unresolved 필드를 수동 보정하면 remap 결과가 3D preview에 반영된다.
- 선택한 component의 W/H/D 수정이 graph와 validator에 반영된다.

### B5 - Human Review to Learning Memory

대상:

- `foms/api/designer/drawings.py`
- `foms/services/designer/design_case_memory.py`
- `foms/services/designer/product_archetype_learning.py`
- `foms/services/designer/evolution.py`
- `tests/domains/test_designer_product_archetype_learning.py`

작업:

- 승인된 graph만 `DesignerDesignCase`로 저장한다.
- `internal_structure_json`에는 원본 `design_understanding`과 mapping report를 함께 저장한다.
- `tags_json`에는 learned category, layout signature, material/hardware signature, block keys를 누적한다.
- design case 3건 이상 evidence가 있을 때만 archetype candidate를 생성한다.
- correction evidence 3건 이상 + replay 통과 없이는 rule candidate 승격 금지.

Acceptance:

- 승인 전 extraction/candidate는 learning case가 아니다.
- raw upload sample이 rule evidence로 오염되지 않는다.
- archetype discovery는 supporting_case_ids를 포함한다.
- ontology promotion은 human approval + replay gate 없이는 실패한다.

### B6 - Retrieval Use in New Candidates

대상:

- `foms/services/designer/design_case_memory.py`
- `foms/services/designer/product_archetype_learning.py`
- `foms/services/designer/langgraph_workflows.py`

작업:

- LangGraph `retrieve_design_memory`에서 비슷한 치수/태그/카테고리 사례를 조회한다.
- similar case는 mapper의 보조 근거로만 사용한다.
- similar case가 있어도 도면 evidence 없이 부재를 생성하지 않는다.
- retrieval 결과는 `state_json`에 남겨 감사 가능하게 한다.

Acceptance:

- 동일한 layout_signature가 쌓일수록 candidate confidence가 상승한다.
- retrieval 실패가 silent success가 되지 않고 warning으로 남는다.
- PII-free payload만 LangGraph/Gemini prompt context에 들어간다.

### B7 - Operational Hardening

대상:

- Railway deploy/startup scripts
- Alembic migrations
- `tests/performance/test_designer_product_performance.py`
- QA specs

작업:

- migration advisory lock과 `ADD COLUMN IF NOT EXISTS` 방식을 유지한다.
- candidate mapping은 Gemini 호출 이후 CPU 작업이므로 upload request timeout을 늘리지 않는다.
- 장기 실행 LangGraph는 worker/RQ 전환 계획을 별도로 둔다.
- Gemini call budget을 제한한다.
  - 도면 upload/extract 1건당 Gemini call은 기본 1회, 재시도 포함 최대 2회다.
  - mapping/remap은 Gemini 재호출 없이 deterministic mapper만 사용한다.
  - ontology draft graph는 manual trigger only이며 upload path에서 자동 호출하지 않는다.
  - rate-limit 발생 시 silent fallback 금지, 사용자에게 retry 가능 상태와 원인을 반환한다.
- FOMS-DEV에서 검증 후, production은 별도 요청이 있을 때만 진행한다.

Acceptance:

- command preview p95 < 500ms.
- candidate mapping p95 < 2s for single-page fixture.
- upload/extract는 timeout/error/progress를 명확히 반환한다.
- upload 1건당 Gemini 호출 횟수는 로그/metadata에서 확인 가능하다.
- Railway logs에서 migration/schema check가 성공한다.

## 5. Release KPI and Operational Metrics

릴리스 1주 차에는 기능 성공 여부를 latency만으로 보지 않는다. 다음 지표를 FOMS-DEV와 staging 로그에서 수집한다.

| KPI | 정의 | 목표/판정 |
|---|---|---|
| Candidate approve rate | 3D preview까지 간 candidate 중 승인 저장된 비율 | 초기 목표 40% 이상, 20% 미만이면 mapper 품질 P0 |
| Average manual correction count | candidate 1건 승인 전 사용자가 수정한 필드/부재 수 | 추세 하락이 목표, 급증 시 ontology/mapping review |
| Average review time | 3D preview load부터 approve/reject까지 걸린 시간 | 1장 기준 10분 이하 목표 |
| Mapping warnings per candidate | `mapping_report.warnings` 평균 개수 | fixture별 baseline 대비 증가하면 regression |
| Unresolved fields per candidate | 승인 전 unresolved 필드 평균 개수 | 반복 unresolved는 Gemini prompt 또는 mapper 보강 후보 |
| Gemini calls per upload | upload/extract 1건당 Gemini 호출 수 | 기본 1, retry 포함 최대 2 |
| Legacy candidate block count | backfill된 legacy candidate가 load/approve 차단된 건수 | 발생 시 재추출 UX 확인 |
| Duplicate approve conflict count | HTTP 409 candidate/project lock 충돌 횟수 | 0이 목표, 발생 시 UX 재시도 문구 확인 |
| Ontology draft promotion count | replay+pass 후 active 승격된 draft 수 | admin manual action만 허용 |

로그/저장 위치:

- `DesignerDrawingExtraction.routing_json`: model/cost/rate-limit metadata
- `DesignerExtractionCandidate.mapping_report_json`: warnings/unresolved/mapped components
- `DesignerAIRun.state_json`: interrupt/resume/checkpoint evidence
- `DesignerCorrection`: user edit/correction delta
- `DesignerDesignCase`: approved learning case evidence

## 6. Required Tests

최소 테스트 세트:

```powershell
python -m pytest tests/domains/test_designer_layout_graph_mapper.py -q
python -m pytest tests/domains/test_designer_drawing_review_contract.py -q
python -m pytest tests/domains/test_designer_ai_runs.py -q
python -m pytest tests/domains/test_designer_product_archetype_learning.py -q
python -m pytest tests/domains/test_designer_command_engine.py -q
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
```

브라우저/배포 QA:

```text
/wdplanner-v2
  -> 도면 업로드
  -> candidate 생성
  -> 3D preview load
  -> component 선택
  -> W/H/D 수정
  -> validator 결과 확인
  -> approve-and-save
  -> design case 목록에서 재조회
```

## 7. Stop Rules

다음 중 하나라도 발생하면 구현/배포를 멈추고 원인 분석으로 돌아간다.

- Gemini JSON은 성공했지만 `design_graph_candidate.components.length == 0`인데 성공 처리되는 경우.
- unresolved/validator error가 있는데 approve/save가 되는 경우.
- no-op patch 또는 empty graph로 project version이 생성되는 경우.
- raw upload 또는 fake sample이 rule/archetype evidence로 승격되는 경우.
- `custom_storage`가 단순 unsupported error로 끝나고 review 가능한 generic graph 후보를 만들지 못하는 경우.
- LangGraph가 직접 `design_json`을 mutation하거나 validator를 우회하는 경우.
- production ontology/rule/archetype이 자동 승격되는 경우.
- Railway production push가 별도 명시 없이 필요한 경우.

## 8. File Map

| 파일 | 역할 |
|---|---|
| `foms/services/designer/gemini_provider.py` | 도면 이해 JSON 후보 생성 |
| `foms/services/designer/layout_graph_mapper.py` | 신규 핵심: layout_graph -> DesignGraph |
| `foms/services/designer/ontology_mapper.py` | extraction -> candidate 계약 보강 |
| `foms/services/designer/langgraph_workflows.py` | drawing layout workflow orchestration |
| `foms/services/designer/ontology_types.py` | backend schema v2 ontology |
| `Add In Program/FOMSBrainDesigner/src/domain/ontologyTypes.ts` | frontend schema v2 ontology |
| `foms/api/designer/drawings.py` | upload/candidate/review/approve API |
| `foms/api/designer/ai_runs.py` | LangGraph run/resume API |
| `foms/services/designer/command_engine.py` | 편집 command preview/apply |
| `foms/services/designer/design_case_memory.py` | 승인 설계 사례 저장/조회 |
| `foms/services/designer/product_archetype_learning.py` | 반복 설계 카테고리 후보 |
| `foms/services/designer/evolution.py` | rule/ontology 후보 replay/승격 |
| `Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts` | 3D graph load/edit state |
| `Add In Program/FOMSBrainDesigner/src/canvas/CabinetScene.tsx` | DesignGraph component mesh 렌더링 |

## 9. Acceptance Definition

완료 판정은 다음 조건을 모두 만족해야 한다.

- 도면에서 추출된 칸/선반/도어/부품 구조가 `DesignGraph.components`로 변환된다.
- 3D 편집기에서 변환된 부재를 직접 선택하고 치수/위치/재질을 수정할 수 있다.
- 모든 저장 가능한 수정은 `DesignCommand`, validator, correction delta 경로를 통과한다.
- 승인된 설계만 `DesignerProjectVersion`과 `DesignerDesignCase`로 저장된다.
- 학습된 커스텀 카테고리는 `furniture_type`을 무한 확장하지 않고 `learned_design_category/archetype`으로 누적된다.
- LangGraph run state에는 입력, 근거, 후보 graph, validation, interrupt, approval 결과가 감사 가능하게 남는다.
- FOMS-DEV 배포에서 성공 검증 전 production 배포는 하지 않는다.

## 10. Implementation Order

Implementation DAG:

```text
B0
  -> { B1, B4-mock }
  -> B2
  -> B3
  -> B4-real
  -> { B5, B6 }
  -> B7
```

병렬화 규칙:

- `B1 mapper`와 `B4-mock 3D load UI`는 공통 fixture 계약이 고정되면 병렬 가능하다.
- `B2 persistence`는 B1의 `LayoutMappingResult` 계약을 사용하므로 B1 최소 통과 후 진행한다.
- `B3 LangGraph`는 B2의 candidate persistence와 checkpoint 계약 이후 진행한다.
- `B5/B6`는 approval 저장 계약이 안정되면 병렬 가능하다.

권장 순서:

1. B0 계약 freeze와 실패 응답 테스트를 먼저 고정한다.
2. B1 mapper 테스트부터 작성한다.
3. mapper가 fixture 3개 이상을 `DesignGraph`로 변환하게 만든다.
4. B4-mock에서 fixture graph를 3D 편집기에 직접 로드한다.
5. B2 candidate persistence와 legacy backfill을 붙인다.
6. B3 LangGraph drawing workflow와 checkpoint/resume을 붙인다.
7. B4-real에서 DB candidate -> iframe graph-first load를 완성한다.
8. B5 approval -> design case memory를 강화한다.
9. B6 retrieval을 후보 생성에 반영한다.
10. B7 FOMS-DEV Railway QA를 통과시킨다.

첫 구현 PR/커밋의 최소 범위는 B1+B2 일부까지로 제한한다. LangGraph 전체 연결은 mapper와 persistence 계약이 안정된 뒤 진행한다.
