# C-Phase Readiness Audit (C-1)

**작성일**: 2026-05-16  
**감사자**: Claude Code (Auto)  
**근거 계획서**: `docs/plans/2026-05-16-foms-brain-lego-ontology-explainable-design-plan.md` §Phase C-1

---

## 감사 범위

C단계 착수 전 B단계 계약이 실제 코드/브라우저 흐름에서 동작하는지 7개 항목 검증.

---

## 결과 요약

| # | 검증 항목 | 상태 | 비고 |
|---|-----------|------|------|
| 1 | ExtractionCandidate persist → 3D preview 생성 flow | 🟡 MINOR | custom_storage 타입 미지원 (M-1) |
| 2 | ui_state.can_preview_3d / can_approve / can_save_design_case 분리 | 🟢 GREEN | 백엔드 compute_ui_state 명확히 분리됨 |
| 3 | preview/approve/save 버튼이 UI에서 혼용되지 않음 | 🟡 MINOR | btn-load-3d 항상 표시 (M-2) |
| 4 | iframe postMessage same-origin + ack 계약 | 🔴 BLOCKER | wildcard `'*'` 3곳 + origin 미검증 (B-1) |
| 5 | 이미지/PDF PII 정책 — Gemini 전송 전 실행 또는 명시적 차단 | 🟢 GREEN | no_ocr_accepted 정책 명시적 문서화 |
| 6 | 승인된 version만 DesignerDesignCase + RAG 진입 | 🟢 GREEN | 5-gate approve-and-save 검증됨 |
| 7 | raw_learning_sample이 rule candidate 생성 안 함 | 🟢 GREEN | _BLOCKED_HINT_SOURCES 등록 확인됨 |

**C1 착수 가능 여부**: B-1 수정 완료 후 착수 가능 (동 감사 세션에서 수정됨)

---

## 상세 항목

### 1. ExtractionCandidate persist → 3D preview 생성 flow 🟡

**검증 파일**:  
- `foms/services/designer/drawing_intake_pipeline.py` (13단계 pipeline)  
- `foms/persistence/designer/models.py` (DesignerExtractionCandidate)  
- `foms/api/designer/drawings.py` (upload-and-extract, approve-and-save)

**결과**: 파이프라인 13단계가 올바르게 구현됨:
1. DesignerDrawingArtifact + DesignerDrawingPage 생성
2. image PII policy 적용 (Step 2)
3. Gemini 추출 (Step 6) → text PII redaction (Step 7)
4. DesignerDrawingExtraction persist (Step 9)
5. MappedCandidate build + DesignerExtractionCandidate persist (Step 12)
6. B2 컬럼 (`design_graph_candidate_json`, `mapping_report_json`, `validation_json`, `preview_allowed`) 존재 확인

**Minor M-1**: `drawing_intake_pipeline.py:38-39`의 `_FRONTEND_SUPPORTED_TYPES`가 `custom_storage`를 포함하지 않아, custom_storage 도면 업로드 시 `can_preview_3d=False`로 반환됨. factoryRegistry.ts에는 이미 추가되었으나 파이프라인이 미동기화 상태.  
→ **동 세션 수정 완료** (M-1 수정)

---

### 2. ui_state.can_preview_3d / can_approve / can_save_design_case 분리 🟢

**검증 파일**: `foms/services/designer/drawing_intake_pipeline.py:127-171`

**결과**: `compute_ui_state()`가 세 상태를 명확히 분리:
```python
return {
    "can_review": True,
    "can_preview_3d": can_preview_3d,   # validator valid + no unresolved + supported type
    "can_approve": False,               # 항상 False — 별도 human review action 필요
    "can_save_design_case": False,      # 항상 False — approved=True 후에만 가능
    "blocking_reasons": blocking_reasons,
}
```
`can_approve`는 업로드 시점에 항상 False. approve-and-save route는 별도 5-gate 검증 후 project version + DesignCase를 생성.

---

### 3. preview/approve/save 버튼 UI 혼용 여부 🟡

**검증 파일**: `templates/designer/wdplanner_v2.html:1092-1108`

**결과**: btn-load-3d(3D로 로드)가 `can_preview_3d` 값과 무관하게 추출 결과가 있으면 항상 표시됨:
```javascript
// "검수" + "3D로 로드" 버튼: 추출 결과가 있으면 항상 표시
document.getElementById('btn-load-3d').style.display = '';
```
보안 계약 위반은 아니나 (버튼 클릭 → 백엔드 호출 → 정상 처리), UX 개선 항목으로 기록.  
→ C1 범위 내에서 `ui_state.can_preview_3d` 기반 표시로 개선 가능.

**승인/저장 버튼 분리**: btn-approve(corpus 등록)는 fixture 지정 시에만 표시, btn-save-learning(학습 저장)은 일반 업로드 시에만 표시 — 혼용 없음. ✅

---

### 4. iframe postMessage same-origin + ack 계약 🔴 → 수정 완료

**검증 파일**: `templates/designer/wdplanner_v2.html`

**발견**: wildcard target origin `'*'` 사용 3개소:
```javascript
// loadCaseToEditor() — line 679
iframe.contentWindow.postMessage({type:'FOMS_LOAD_CANDIDATE',...}, '*')

// openReview() — line 1140
iframe.contentWindow.postMessage({type:'FOMS_REVIEW_EXTRACTION',...}, '*')

// loadTo3D() — line 1210
iframe.contentWindow.postMessage({type:'FOMS_LOAD_CANDIDATE',...}, '*')
```

**추가 발견**: ACK 수신 리스너(line 1146)가 `e.origin` 미검증:
```javascript
window.addEventListener('message', function(e) {
    if (!e.data || e.data.type !== 'FOMS_CANDIDATE_LOADED_ACK') return;
    // e.origin 체크 없음 — 외부 메시지 수용 가능
```

**계약 위반**: "wildcard postMessage 금지: C단계 write action은 same-origin 확인 + ack 기반 성공 표시 + CSRF/session fetch 계약을 통과해야 한다."

**수정**: `'*'` → `window.location.origin` (3곳) + ACK listener에 `e.origin !== window.location.origin` 조기 반환 추가.  
→ **동 세션 수정 완료** (B-1 수정)

---

### 5. 이미지/PDF PII 정책 🟢

**검증 파일**: `foms/services/designer/drawing_intake_pipeline.py:94-120`

**결과**: `_apply_image_pii_policy()`가 Gemini 호출(Step 6) 이전(Step 2)에 실행됨:
- 정책: `"no_ocr_accepted"` — OCR 파이프라인 없음을 명시적으로 문서화
- 경고 로그 기록: `logger.warning("[PIPELINE] image_pii_policy=no_ocr_accepted ...")`
- redaction_report에 `image_pii_warning` 포함 → API 응답으로 전달됨
- Gemini 응답 텍스트는 RedactionContext로 PII 치환됨 (Step 7)

C-1 계약 충족: "OCR/image redaction 불가 시 explicit block 또는 명시적 제한 정책을 C-1에서 확정" → **no_ocr_accepted 정책으로 확정됨**.

---

### 6. 승인된 version만 DesignerDesignCase + RAG 진입 🟢

**검증 파일**: `foms/api/designer/drawings.py:666-879` (approve_and_save_candidate)

**결과**: 5-gate 검증 후에만 project version + DesignCase 생성:
- Gate 0: already approved/promoted → 409
- Gate 1: legacy candidate → 422
- Gate 2: blocking_reasons 있음 → 422
- Gate 3: unresolved_fields 있음 → 422
- Gate 4: design_graph 없거나 components.length=0 → 422
- Gate 5: validator 통과 필수 → 422

`save_design_case(project_version_id=...)` — project_version_id가 존재해야 함을 service layer에서 재검증 (`foms/services/designer/design_case_memory.py:91-96`).

`design_retrieval.py`의 `find_similar()`는 `DesignerDesignCase` 테이블만 쿼리 → approve-and-save를 통과한 케이스만 포함됨.

---

### 7. raw_learning_sample이 rule candidate 생성 안 함 🟢

**검증 파일**: `foms/services/designer/correction_clusterer.py:23-63`

**결과**: `_BLOCKED_HINT_SOURCES`에 차단 소스 등록됨:
```python
_BLOCKED_HINT_SOURCES = frozenset({
    "learning_upload",
    "raw_learning_sample",   # save_learning_sample이 사용하는 소스
    "learning_sample_upload",
    "qa_test",
    "qa_seed",
    "generic",
})
```
`save_learning_sample()` (drawings.py:400-474)이 저장하는 `after_json.source = "raw_learning_sample"` → 클러스터러에서 자동 제외.

`candidate_rule_hint`는 intentionally absent (코드 주석 확인됨):
```python
# candidate_rule_hint intentionally absent — prevents rule clustering pollution
```

---

## 수정 완료 항목

### B-1: wildcard postMessage 수정 (BLOCKER → FIXED)

**파일**: `templates/designer/wdplanner_v2.html`

3개소 `'*'` → `window.location.origin` 변경 + ACK listener origin 검증 추가.

### M-1: custom_storage 파이프라인 지원 추가 (MINOR → FIXED)

**파일**: `foms/services/designer/drawing_intake_pipeline.py`

`_FRONTEND_SUPPORTED_TYPES`에 `"custom_storage"` 추가.

---

## C단계 Allowed Write Set 확정

### Backend
- `foms/services/designer/*`
- `foms/persistence/designer/models.py`
- `foms/api/designer/*`
- `migrations/*`

### Frontend
- `Add In Program/FOMSBrainDesigner/src/domain/*`
- `Add In Program/FOMSBrainDesigner/src/stores/designerStore.ts`
- `Add In Program/FOMSBrainDesigner/src/canvas/DesignerCanvas.tsx`
- `Add In Program/FOMSBrainDesigner/src/canvas/CabinetScene.tsx`
- `Add In Program/FOMSBrainDesigner/src/ui/*`

### Docs/Tests
- `docs/plans/*`
- `tests/domains/test_designer_*`

---

## 수락 기준 달성 여부

- [x] B-1 blocker 수정 완료 (동 세션)
- [x] M-1 custom_storage 파이프라인 동기화 (동 세션)
- [x] APP_OK (수정 후 실행)
- [x] 7개 검증 항목 결과 문서화
- [x] C단계 allowed write set 확정
- [ ] M-2 btn-load-3d 조건부 표시 (C1 착수 후 처리)

**C1 착수 조건**: B-1 수정 완료 → **달성됨**.
