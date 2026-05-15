# WDPlanner V2 Production-Grade Remediation Plan
> 작성일: 2026-05-15 | 상태: 🔴 작성중

## 0. GDM Truth Summary

### 0.1 현재 판정

`/wdplanner-v2`는 React/R3F 설계 편집기 shell, 도면 업로드 UI, 일부 Gemini 호출, 일부 학습/규칙/사례 UI가 존재한다. 그러나 계획서가 요구한 제품급 핵심 루프는 아직 연결되지 않았다.

현재 실제 동작은 다음과 같다.

```text
도면 업로드
  -> drawings.py가 gemini_provider.extract_from_image_path 직접 호출
  -> 화면에 extraction 표시
  -> 후보 build는 in-memory _CANDIDATE_STORE
  -> 3D load는 postMessage로 프론트 로컬 graph 생성 시도
  -> 학습 저장은 DesignerCorrection에 lightweight 저장
  -> DesignCaseMemory / RAG / Archetype / 승인 설계 사례로 이어지지 않음
```

계획서상 의도된 동작은 다음이어야 한다.

```text
Raw artifact 저장
  -> template classification
  -> model_router
  -> PII redaction
  -> Gemini multimodal extraction
  -> DesignerDrawingExtraction persist
  -> DesignerExtractionCandidate persist
  -> review workspace correction
  -> validator
  -> human approve
  -> project version
  -> DesignCaseMemory
  -> retrieval/RAG/rule/archetype/self-evaluation
```

### 0.2 Root Cause

근본 원인은 “기능 조각은 존재하지만, 계획서의 중앙 제품 파이프라인이 실제 사용자 버튼 경로에 연결되지 않은 것”이다.

하위 원인은 10개다.

1. `/api/designer/drawings/upload-and-extract`가 `model_router.route_and_extract()`를 사용하지 않고 Gemini provider를 직접 호출한다.
2. extraction/candidate DB 모델이 있지만 업로드 경로가 `DesignerDrawingExtraction`, `DesignerExtractionCandidate`를 저장하지 않는다.
3. candidate build가 process-local `_CANDIDATE_STORE`에 의존한다.
4. Review UI는 postMessage shell 수준이고 correction -> candidate rebuild -> approve-and-save 흐름으로 이어지지 않는다.
5. “학습 저장”은 `DesignerCorrection`만 만들고 `DesignerDesignCase`를 만들지 않아 사례/RAG/Archetype이 비어 있다.
6. AI 설계 요청은 Gemini/RAG가 아니라 LUI rule parser 또는 placeholder/no-op graph로 끝난다.
7. `save-learning-sample`이 모든 샘플에 동일한 `candidate_rule_hint="learning_upload"`를 저장하고, rule clustering은 이 hint로 그룹핑하므로 단순 업로드 3건이 rule evidence처럼 오염될 수 있다.
8. PDF multi-page는 실제 페이지별 추출/검수가 아니라 1페이지만 추출하고 `is_multipage=true`만 표시한다.
9. PII redaction은 추출된 text/dict payload 마스킹만 다루며, Gemini에 전송되는 원본 이미지/PDF 내부 텍스트 PII는 제거하지 못한다.
10. `candidate.can_apply()`는 human approved까지 요구하므로, 승인 전 3D preview 가능 여부를 판단하는 UI 계약으로 쓰면 안 된다.

### 0.3 실제 감사 증거

| 증거 | 결과 |
|---|---|
| `.codex/wdplanner-v2-audit-output/results.json` | 원격 `/wdplanner-v2` 로그인, 탭/버튼, 업로드, 3D load, 학습 저장, 규칙/Archetype/사례 버튼 검증 |
| `.codex/wdplanner-v2-audit-output/ai-results.json` | 오른쪽 AI 설계 요청과 하단 AI 실행 검증 |
| 브라우저 콘솔 | `loadCandidateGraph failed: Unknown furniture type: custom_storage` |
| 업로드 API 응답 | Gemini 호출은 성공했지만 W/H/D null, parts empty, raw PII가 응답에 포함됨 |
| `save-learning-sample` 응답 | `learning_record_id`만 생성, 설계 사례 목록은 0건 유지 |
| AI 실행 응답 | no-op patch `{}`인데 `succeeded` 및 project version 저장 |

## 1. What - 무엇을 고치는가

### 1.1 최종 결과물

`/wdplanner-v2`에서 사용자가 보는 모든 주요 버튼이 계획서의 제품급 흐름과 일치해야 한다.

- 도면 업로드는 raw artifact, extraction, candidate를 DB에 남긴다.
- Gemini 호출은 model router와 PII redaction을 반드시 통과한다.
- 검수 UI에서 수정한 값은 `CorrectionDelta`로 저장되고 candidate에 반영된다.
- 미확인 필드나 validator error가 있으면 3D load, 승인, 저장을 막는다.
- 승인된 설계만 project version과 Design Case Memory로 저장된다.
- 설계 사례 탭은 실제 `DesignerDesignCase`를 검색하고 3D 편집기로 불러온다.
- Archetype/Rule 후보는 실제 승인 사례와 correction evidence를 기반으로만 생성된다.
- AI 설계 요청은 Gemini/RAG/LUI 결과를 명확히 구분하고, no-op 성공 저장을 금지한다.

### 1.2 사용자 기능 요구사항

1. 도면 업로드
   - 일반 학습 업로드와 fixture 업로드 모두 같은 intake pipeline을 사용한다.
   - 업로드 성공 시 artifact id, extraction id, candidate id, routing metadata, metrics가 응답된다.
   - Gemini 실패는 명시적으로 실패 처리한다. silent fallback 금지.

2. Gemini 분석
   - template classifier와 model router를 경유한다.
   - 외부 Gemini payload에는 고객명/전화/주소 원문을 보내지 않는다.
   - 도면 이미지/PDF 안에 인쇄되거나 적힌 고객명/전화/주소는 OCR-then-mask, image redaction, 또는 명시적 차단 정책을 거친 뒤에만 Gemini로 전송한다.
   - Gemini raw request/response log에도 원본 PII를 남기지 않는다.
   - W/H/D, parts, customer meta, drawing meta, unresolved fields를 schema로 정규화한다.

3. 도면 검수
   - 원본 도면/preview와 추출 필드 테이블을 같은 review workspace에서 보여준다.
   - 사용자가 수정한 필드는 `DesignerCorrection`에 before/after/reason/source_candidate_id로 저장한다.
   - 수정 후 candidate를 rebuild하고 validator 결과를 즉시 표시한다.

4. 3D 로드
   - 3D preview/load 가능 여부는 `candidate.can_apply()`가 아니라 `ui_state.can_preview_3d`로 판단한다.
   - `ui_state.can_preview_3d`는 human approval 전에도 validator valid, unresolved field 없음, frontend factory supported type이면 true가 될 수 있다.
   - unsupported type이면 버튼을 숨기거나 명확한 오류를 표시한다.
   - 성공 toast는 실제 iframe graph load 성공 ack를 받은 뒤에만 표시한다.

5. 승인/저장
   - 승인 버튼은 validator pass + human review complete 상태에서만 활성화된다.
   - 승인 시 project version을 만들고 같은 transaction 또는 보상 가능한 순서로 `DesignerDesignCase`를 생성한다.
   - invalid design version 저장률은 0이어야 한다.

6. 학습/사례/Archetype
   - “학습 저장”은 단순 correction 저장이 아니라 학습 샘플 상태를 명확히 분리한다.
   - raw learning sample에는 rule candidate grouping hint를 부여하지 않는다.
   - `candidate_rule_hint="learning_upload"` 단일 값으로 correction cluster가 생성되는 경로를 금지한다.
   - 승인 설계 사례 탭은 `DesignerDesignCase`만 보여준다.
   - Archetype discovery는 3개 이상 approved design case evidence가 없으면 후보를 만들지 않는다.
   - Rule candidate는 3개 이상 독립 correction evidence와 replay 결과가 없으면 승인/승격되지 않는다.

7. AI 설계 요청
   - 오른쪽 `AI 설계 요청` 패널은 Gemini/RAG 기반 자동 설계와 LUI command edit를 분리한다.
   - 하단 `AI 설계 보조`는 placeholder/no-op을 성공으로 저장하지 않는다.
   - patch가 비어 있으면 project version 생성 금지.
   - 사용자가 “가로 폭 2700mm”처럼 명령하면 실제 command preview/apply 결과가 바뀌어야 한다.

### 1.3 하지 않을 것

- 기존 `/wdplanner` 삭제 금지.
- Gemini 실패 시 fake provider로 조용히 대체 금지.
- unresolved field가 있는데 3D load 성공처럼 표시 금지.
- no-op patch를 성공 version으로 저장 금지.
- UI 문구만 바꿔서 “학습된 것처럼” 보이게 하는 수정 금지.
- production ontology/rule/archetype 자동 승격 금지.

## 2. How - 어떻게 고치는가

### 2.1 수정 대상 파일

| 파일 | 변경 내용 |
|---|---|
| `foms/api/designer/drawings.py` | upload/extract를 model router 경유로 전환, extraction/candidate DB 저장, in-memory candidate 의존 제거, approve-and-save 후 design case 생성 |
| `foms/services/designer/model_router.py` | missing key fallback 금지 정합, route metadata 표준화, PII redaction 호출 위치 확정 |
| `foms/services/designer/gemini_provider.py` | provider는 순수 호출/parse만 담당, raw PII logging 방지 테스트 보강 |
| `foms/services/designer/pii_redactor.py` | image/text payload redaction context와 response re-link 계약 확정 |
| `foms/services/designer/ontology_mapper.py` | unsupported `custom_storage` 처리 정책 확정, can_apply 산정 강화 |
| `foms/services/designer/design_case_memory.py` | approve flow에서 호출 가능한 저장 contract 확정, 중복 저장 방지 |
| `foms/api/designer/learning_ui.py` | cases/archetype API가 빈 배열을 success로 삼키는 경로 축소, evidence 부족 사유 반환 |
| `foms/services/designer/product_archetype_learning.py` | 3개 이상 approved case evidence gate 강화 |
| `foms/services/designer/correction_clusterer.py` / `evolution.py` | 3개 이상 독립 correction evidence, QA seed candidate 승격 차단 |
| `foms/services/designer/langgraph_workflows.py` | real mode placeholder 제거 또는 명시 실패, no-op patch persist 금지 |
| `foms/api/designer/lui.py` | parse 결과와 자동 설계 candidate 결과를 분리해 반환 |
| `templates/designer/wdplanner_v2.html` | 버튼 활성 조건, ack 기반 성공 toast, extraction/candidate id 보관, review/save flow 연결 |
| `Add In Program/FOMSBrainDesigner/src/App.tsx` | postMessage ack, review/candidate load 실패 응답, unsupported type 처리 |
| `Add In Program/FOMSBrainDesigner/src/ui/DrawingReviewWorkspace.tsx` | 실제 candidate correct/approve API 연결, overlay/field edit 상태 관리 |
| `Add In Program/FOMSBrainDesigner/src/ui/ExtractionTablePanel.tsx` | 수정 저장, unresolved 표시, validator 결과 표시 |
| `Add In Program/FOMSBrainDesigner/src/ui/AIDesignPanel.tsx` | Gemini/RAG 자동 설계와 LUI 편집 명령 경로 분리 |
| `Add In Program/FOMSBrainDesigner/src/ui/AIPanel.tsx` | no-op 결과 표시/차단, review interrupt UX 정합 |
| `tests/domains/test_designer_*` | router, upload, PII, candidate persist, approve/design case, no-op AI, learning gates 회귀 테스트 |
| `.codex/wdplanner-v2-audit*.spec.js` | 감사 스크립트를 회귀 QA로 정리하거나 tests/support로 이동 검토 |

### 2.2 아키텍처 방향

기존 결정은 유지한다.

- `/wdplanner-v2` 병행 add-in 유지.
- Flask modular monolith + static React/Vite/R3F add-in 유지.
- PostgreSQL/SQLAlchemy persistence를 source of truth로 사용.
- Gemini는 외부 모델 provider, FOMS 내부 DB가 학습/기억/승인 source of truth다.

새로 추가할 핵심 계약은 하나다.

```text
DrawingPipelineResult
  artifact_id
  extraction_id
  candidate_id
  routing
  redaction_report
  extraction
  candidate
  metrics
  ui_state
    can_review
    can_preview_3d
    can_approve
    can_save_design_case
    blocking_reasons[]
```

모든 버튼은 이 상태만 보고 활성/비활성을 결정한다.

`candidate.can_apply()`는 approved + validator valid + unresolved 없음까지 만족한 최종 적용/저장 계약이다. 따라서 3D 검수 preview 버튼에는 직접 사용하지 않는다.

- `ui_state.can_preview_3d`: validator valid + unresolved 없음 + frontend supported type.
- `ui_state.can_approve`: human review complete + validator valid + unresolved 없음 + supported type.
- `ui_state.can_save_design_case`: approved + validator valid + persisted project version 가능 + PII-free design case payload.
- `candidate.can_apply()`: approval 이후 저장/적용 단계의 최종 guard로 유지.

### 2.3 DB/마이그레이션 영향

기존 모델이 충분한지 먼저 확인한다.

- `DesignerDrawingArtifact`
- `DesignerDrawingExtraction`
- `DesignerExtractionCandidate`
- `DesignerCorrection`
- `DesignerDesignCase`
- `DesignerAIRun`
- `DesignerRuleCandidate`

필드가 부족하면 새 migration을 만든다. 예상 추가 후보:

- `designer_drawing_extractions.routing_json`
- `designer_drawing_extractions.redaction_report_json`
- `designer_drawing_extractions.provider_payload_hash`
- `designer_extraction_candidates.status`
- `designer_extraction_candidates.can_preview_3d`
- `designer_extraction_candidates.can_approve`
- `designer_extraction_candidates.can_save_design_case`
- `designer_extraction_candidates.blocking_reasons_json`
- `designer_design_cases.source_candidate_id`

마이그레이션은 실제 모델 확인 후 최소화한다.

## 3. Steps - 실행 단계

### Batch R0 - 감사 기준 고정

- [ ] `.codex/wdplanner-v2-audit-output/results.json`과 `ai-results.json`에서 실패 증거를 plan/run-record에 요약한다.
- [ ] 현재 dev DB의 QA seed 데이터와 이번 감사 데이터가 테스트 결과에 영향을 주지 않도록 회귀 테스트는 독립 fixture/transaction으로 구성한다.
- [ ] `docs/plans/2026-05-14-foms-brain-production-grade-product-plan.md`의 “done/partial” 표와 실제 경로 차이를 별도 gap 표로 고정한다.

GDM review gate:
- R1 spec: 실패 증거와 root cause가 증상 나열이 아니라 코드 경로로 연결됐는가.
- R2 workspace: `.codex` 감사 산출물이 실수로 release scope에 들어가지 않는가.
- R3 code plan: 첫 코드 batch가 router/persistence root cause를 직접 겨냥하는가.
- R4 proof: 브라우저 회귀 기준이 false-green을 만들지 않는가.

### Batch R1 - Upload/Extract Pipeline SSOT

- [ ] `drawings.py`의 direct `extract_from_image_path` 호출을 pipeline service로 분리한다.
- [ ] pipeline service는 artifact save -> page classification -> image/OCR PII policy -> template classify -> model route -> Gemini call -> normalized extraction 순서로 실행한다.
- [ ] missing `GEMINI_API_KEY`는 503 explicit error로 유지한다.
- [ ] `model_router.route_and_extract()`의 fake fallback은 production path에서 제거하거나 test-only branch로 잠근다.
- [ ] provider metrics와 routing metadata를 extraction response에 포함한다.
- [ ] PDF multi-page는 page별 artifact/extraction 후보를 만들거나, product scope에서 명시적으로 unsupported/blocking reason을 반환한다.
- [ ] `_enqueue_extraction_job` 동기/비동기 경로는 upload pipeline SSOT로 통합하거나 dead code로 제거한다.

Acceptance:
- `DESIGNER_FAKE_VISION=0` + no key면 fake fallback 없이 실패한다.
- key가 있으면 route metadata provider=`gemini`가 응답된다.
- upload route 코드에서 `extract_from_image_path` 직접 호출이 사라진다.
- multi-page PDF가 page=1만 추출된 채 성공 처리되지 않는다. 페이지별 처리 또는 명확한 blocking reason이 응답된다.
- 이미지/PDF 내부 텍스트 PII 처리 정책이 Gemini 전송 전에 실행되며, 처리 불가 시 명시적으로 차단된다.

### Batch R2 - Extraction/Candidate Persistence

- [ ] 업로드 시 raw artifact/page/extraction/candidate를 DB에 저장한다.
- [ ] `_CANDIDATE_STORE` 의존을 제거하거나 test-only로 격리한다.
- [ ] candidate id는 DB id 또는 stable UUID로 반환한다.
- [ ] candidate `can_preview_3d`, `can_approve`, `can_save_design_case`, `blocking_reasons`를 backend에서 각각 계산한다.
- [ ] unresolved W/H/D, unsupported type, validator error가 있으면 `can_preview_3d=false`와 blocking reason이 된다.
- [ ] `candidate.can_apply()`는 approval 이후 최종 저장/적용 guard로만 사용한다.

Acceptance:
- 업로드 응답에 `extraction_id`, `candidate_id`, `ui_state.can_preview_3d`, `ui_state.can_approve`, `ui_state.can_save_design_case`, `blocking_reasons`가 있다.
- process restart 후에도 candidate correct/approve가 동작 가능한 구조다.
- unresolved field가 있는데 3D load 가능 상태가 되지 않는다.

### Batch R3 - Review/Correction Workspace

- [ ] `openReview()`는 extraction/candidate id를 전달한다.
- [ ] React review workspace는 API에서 persisted candidate를 다시 조회한다.
- [ ] field edit는 `POST /candidates/<id>/correct`로 저장한다.
- [ ] correction 저장 후 candidate rebuild/validator를 실행한다.
- [ ] reject는 raw artifact/extraction/candidate history를 보존하고 rejected status만 남긴다.
- [ ] extraction/candidate에 `pending_review`, `corrected`, `rejected`, `approved` 같은 status enum이 필요한지 migration으로 확정한다.

Acceptance:
- 검수 화면에서 W/H/D 수정 후 reload해도 수정 내역이 유지된다.
- `DesignerCorrection`에 before/after/source candidate/reason이 남는다.
- correction 후 unresolved count가 줄어든다.
- rejected candidate는 history가 보존되고 3D load/approve/save가 차단된다.

### Batch R4 - 3D Preview/Load Contract

- [ ] 3D load 버튼은 `ui_state.can_preview_3d=true`일 때만 활성화한다.
- [ ] approve/save 버튼은 각각 `ui_state.can_approve`, `ui_state.can_save_design_case`로 분리한다.
- [ ] iframe `FOMS_LOAD_CANDIDATE`는 성공/실패 ack를 parent에 postMessage로 돌려준다.
- [ ] `App.tsx`의 `loadCandidateGraph`는 try/catch로 감싸고 `FOMS_LOAD_CANDIDATE_RESULT {ok, reason}`을 parent에 반환한다.
- [ ] parent toast는 ack success일 때만 성공으로 표시한다.
- [ ] `custom_storage` 등 frontend factory 미지원 type은 backend blocking reason으로 막는다.
- [ ] supported type mapping은 backend/frontend factory registry가 공유 가능한 enum으로 고정한다.

Acceptance:
- unsupported type 로드 시 콘솔 error 대신 UI blocking reason이 보인다.
- `loadCandidateGraph failed`가 회귀 테스트에서 0건이다.
- 성공 toast가 실제 3D graph load 이후에만 뜬다.
- approval 전 valid candidate는 3D preview가 가능하지만, `can_approve=false`이면 승인/저장은 막힌다.

### Batch R5 - Approval/Design Case Memory

- [ ] `approve-and-save`가 persisted candidate를 기준으로 validator를 다시 실행한다.
- [ ] 승인 성공 시 project version 생성 후 `save_design_case()`를 호출한다.
- [ ] design case에는 source extraction/candidate/project version id가 연결된다.
- [ ] cases API는 `DesignerDesignCase`를 반환하고, 실패를 빈 success로 삼키지 않는다.
- [ ] learning UI API의 `/cases`, `/archetypes/summary`, `/archetypes/discover`는 동일한 error envelope을 사용한다.
- [ ] fixture corpus approve와 일반 learning approve의 경계를 문서화한다.

Acceptance:
- 승인된 설계 1건 생성 후 “설계 사례” 탭에 즉시 표시된다.
- 사례의 `3D 편집` 버튼이 실제 3D graph를 로드한다.
- invalid/unresolved candidate는 project version과 design case를 만들 수 없다.

### Batch R6 - Learning Gates: Rule/Archetype/RAG

- [ ] `save-learning-sample`의 의미를 “raw learning sample”로 명확히 하거나 승인 flow로 통합한다.
- [ ] raw learning sample 저장 시 `candidate_rule_hint="learning_upload"`를 넣지 않는다.
- [ ] `correction_clusterer`는 source-only generic hint(`learning_upload`, `qa_test`, `generic`)로는 cluster/rule candidate를 만들 수 없다.
- [ ] rule clustering은 3개 이상 독립 correction evidence가 없으면 후보 생성 금지.
- [ ] QA seed candidate가 promoted 상태로 보이는 문제를 정리한다.
- [ ] Archetype discovery는 3개 이상 approved design case evidence가 없으면 후보 생성 금지와 사유를 반환한다.
- [ ] retrieval context builder가 approved design case만 사용하도록 UI/API 경로를 연결한다.

Acceptance:
- evidence 0인 `qa_test_rule` 같은 promoted 후보가 새로 생성되지 않는다.
- 단순 learning upload 3건만으로 `learning_upload` rule candidate가 생성되지 않는다.
- design case 0건이면 Archetype discover 결과는 0건과 명확한 사유를 반환한다.
- approved design case를 만든 뒤 retrieval context에 해당 case id가 포함된다.

### Batch R7 - AI Design/LUI Integration

- [ ] `AIDesignPanel`에서 “자동 설계 생성”과 “현재 설계 편집 명령”을 UI/endpoint 수준에서 분리한다.
- [ ] 자동 설계는 Gemini/RAG route를 사용한다.
- [ ] 편집 명령은 LUI parser -> DesignCommand preview/apply route를 사용한다.
- [ ] `langgraph_workflows.py` real mode placeholder/no-op 성공 저장을 제거한다.
- [ ] patch가 비어 있으면 version 저장 금지 및 “변경 없음” 상태를 반환한다.
- [ ] “가로 폭 2700mm로 변경”은 실제 width 변경 command로 preview/apply되어야 한다.

Acceptance:
- right AI design request가 `clarification_needed`이면 client fallback으로 성공 처리하지 않는다.
- AI run output patch가 `{}`이면 project version이 생성되지 않는다.
- 성공한 AI command는 changed field와 version id를 함께 반환한다.

### Batch R8 - Browser QA + Release Gate

- [ ] `.codex/wdplanner-v2-audit.spec.js`를 회귀 가능한 QA 스크립트로 정리한다.
- [ ] `.codex/wdplanner-v2-audit*.spec.js`와 감사 산출물은 release staging/commit scope에 포함하지 않는다.
- [ ] 브라우저 QA는 synthetic no-PII fixture만 사용한다.
- [ ] smoke flow:
  - login
  - upload synthetic drawing
  - Gemini 호출 전 이미지/PDF 내부 PII fixture가 OCR/image redaction 또는 explicit block 경로를 통과했는지 확인
  - extraction persisted 확인
  - unresolved이면 3D load disabled 확인
  - review correction으로 W/H/D 입력
  - validator pass 확인
  - approve-and-save
  - design case appears
  - case load to 3D
  - AI no-op save blocked
- [ ] `APP_OK`, focused pytest, frontend typecheck/build, browser QA를 모두 통과해야 closeout한다.

Acceptance:
- 원격 dev에서 콘솔 error 0건.
- `Unknown furniture type` error 0건.
- no-op AI version 생성 0건.
- raw PII Gemini payload/log 노출 0건.

## 4. 검증 기준

### 4.1 로컬 단위/통합 테스트

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `pytest tests/domains/test_designer_model_router.py -q`
- [ ] `pytest tests/domains/test_designer_gemini_provider.py -q`
- [ ] `pytest tests/domains/test_designer_drawing_intake.py -q`
- [ ] `pytest tests/domains/test_designer_drawing_review_contract.py -q`
- [ ] `pytest tests/domains/test_designer_design_case_memory.py -q`
- [ ] `pytest tests/domains/test_designer_design_retrieval.py -q`
- [ ] `pytest tests/domains/test_designer_product_archetype_learning.py -q`
- [ ] `pytest tests/domains/test_designer_learning_loop_product.py -q`
- [ ] `pytest tests/domains/test_designer_ai_runs.py -q`
- [ ] `pytest tests/domains/test_designer_frontend_product_contract.py -q`

### 4.2 프론트엔드 검증

- [ ] `Set-Location "Add In Program\\FOMSBrainDesigner"; npm run typecheck`
- [ ] `Set-Location "Add In Program\\FOMSBrainDesigner"; npm run build`
- [ ] built asset가 `static/designer/index.html`에 반영된다.

### 4.3 브라우저 검증

- [ ] `/wdplanner-v2` login smoke
- [ ] 도면 업로드 후 API 응답에 `routing`, `extraction_id`, `candidate_id`가 있다.
- [ ] unresolved candidate는 3D load disabled다.
- [ ] 검수 correction 후 candidate가 `can_preview_3d=true`, `can_approve` 판정 가능 상태로 전환된다.
- [ ] approval 전 preview 가능 상태와 approval/save 가능 상태가 분리되어 표시된다.
- [ ] 3D load 성공 ack 후에만 toast가 뜬다.
- [ ] approve 후 설계 사례 탭에 노출된다.
- [ ] AI no-op prompt는 version을 만들지 않는다.

### 4.4 보안/PII 검증

- [ ] Gemini 전송 payload에 raw customer/phone/address가 없다.
- [ ] 도면 이미지/PDF 내부 텍스트 PII는 Gemini 전송 전 OCR/image redaction 또는 explicit block 정책을 통과한다.
- [ ] provider log에 raw PII가 없다.
- [ ] response는 권한 있는 FOMS 내부 UI에서만 raw PII를 보여줄 수 있고, model payload와 분리된다.

## 5. Stop Rules

다음 중 하나라도 발생하면 다음 batch로 넘어가지 않는다.

- Gemini 실패를 fake/fallback으로 숨기는 코드가 production path에 남음.
- unresolved candidate를 3D load/approve/save할 수 있음.
- `candidate.can_apply()` 하나로 3D preview, approve, save를 모두 판단함.
- no-op AI patch가 project version을 생성함.
- `DesignerDesignCase` 생성 없이 “설계 사례/Archetype/RAG 완료”로 표시함.
- raw PII가 Gemini payload/log로 전송될 가능성이 남음.
- raw learning upload만 3건 쌓여 rule candidate가 생성될 가능성이 남음.
- 브라우저 QA에서 console error가 재현됨.

## 6. GDM Review Loop

각 batch 뒤에는 다음 4단계 감리를 수행한다.

1. R1 Spec Review
   - 계획서의 acceptance와 실제 diff가 같은 문제를 겨냥하는지 확인.
2. R2 Workspace Review
   - dirty worktree, local `.codex` 산출물, run record, archive index scope를 확인.
3. R3 Code Review
   - workaround, silent swallow, fake fallback, no-op success, UI-only fix 여부를 확인.
4. R4 Proof Review
   - 테스트와 브라우저 QA가 실제 제품 흐름을 검증하는지 확인.

Closeout은 R1~R4 결과를 요약한 run record를 남긴 뒤에만 가능하다.

## 7. 우선순위

P0:
- upload pipeline SSOT
- text payload PII redaction + image/PDF 내부 PII before-Gemini policy
- extraction/candidate persistence
- preview/approve/save UI state 분리
- unresolved/unsupported 3D preview/load 차단
- `learning_upload` 단일 hint 기반 rule candidate 오염 차단
- no-op AI version 저장 차단

P1:
- review correction workspace
- approve -> design case memory
- cases tab real load
- learning UI error contract 통일

P2:
- rule/archetype evidence gates 고도화
- Gemini/RAG automatic design integration
- browser QA script 정식화

## 8. 참고 자료

- 관련 결정: `docs/harness/policy/DECISIONS.md`의 `2026-05-13 FOMS Brain AX Designer add-in stack boundary`
- 원 계획: `docs/plans/2026-05-14-foms-brain-production-grade-product-plan.md`
- 감사 증거: `.codex/wdplanner-v2-audit-output/results.json`
- AI 감사 증거: `.codex/wdplanner-v2-audit-output/ai-results.json`
- 관련 런레코드: `docs/plans/2026-05-14-foms-brain-production-grade-run-record.md`
