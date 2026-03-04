# 시공 완료 코멘트 추가 및 대시보드 노출 구현 계획서

## 1. 개요
현재 시공 대시보드에서 시공 완료 처리 시 이미지만 업로드하고 있으나, 완료 시 특이사항이나 코멘트를 남길 수 있도록 입력창을 추가합니다. 작성된 코멘트는 시공완료 대시보드(`erp_completion_dashboard`)에서 사진과 함께 직관적으로 확인할 수 있도록 UI를 개선합니다.

이 계획서는 기존 구조를 최대한 존중하고, 복잡도를 낮추는 오컴의 면도날(Occam's Razor) 원칙을 준수하여 작성되었습니다.

## 2. 작업 상세 내용

### 2.1. 프론트엔드 모달 및 스크립트 수정 (시공 대시보드)
**대상 파일:** 
- `templates/partials/erp_construction_modals.html`
- `templates/partials/erp_construction_scripts.html`

**작업 내용:**
1. **모달 UI 변경:** 
   - `erpConstructionCompleteModal` 내부에 시공 완료 코멘트를 입력할 수 있는 `<textarea>` 요소를 추가합니다.
   - 위치: "시공을 완료하시겠습니까?" 안내 문구와 사진 업로드 입력창 사이.
   - 예시: `<textarea id="erp-cons-complete-note" class="form-control mb-3" rows="2" placeholder="시공 완료 코멘트 (특이사항 등)"></textarea>`
2. **스크립트 변경:**
   - `submitConstructionComplete()` 함수 내에서 `#erp-cons-complete-note`의 값을 읽어옵니다.
   - 기존의 `fetch` API 호출 시 전송하는 JSON payload(현재 빈 body)에 `completion_note` 값을 추가하여 백엔드로 전달합니다.
   - 예시: `body: JSON.stringify({ completion_note: noteValue })`

### 2.2. 백엔드 시공 완료 API 수정 (데이터 수신 및 저장)
**대상 파일:** 
- `apps/api/erp_orders_construction.py`

**작업 내용:**
1. **데이터 수신:** 
   - `api_construction_complete(order_id)` 라우트에서 `request.get_json()`을 통해 `completion_note` 값을 안전하게 읽어옵니다.
2. **데이터 저장:**
   - `order.structured_data` 내 `workflow` 딕셔너리에 `completion_note`를 저장합니다.
   - 구조: `sd['workflow']['completion_note'] = noteValue`
   - (설계 근거: 시공완료 대시보드용 API인 `apps/api/erp_orders_completion.py`에서 이미 `sd.get('workflow').get('completion_note')`를 읽어오도록 구현되어 있으므로, 이 위치에 저장하는 것이 완벽하게 호환되며 추가적인 API 수정 비용을 없앱니다.)
3. **히스토리 기록 보강:**
   - `workflow['history']` 객체에 추가되는 로그의 `note` 속성에도 코멘트 내용 일부를 병합하여("시공 완료 → 완료 | 코멘트: ...") 남김으로써 추적성을 높입니다.

### 2.3. 시공완료 대시보드 UI 수정 (코멘트 표시)
**대상 파일:** 
- `templates/partials/erp_completion_scripts.html`

**작업 내용:**
1. **코멘트 렌더링 변경:**
   - `api_orders_completion` API가 이미 `completion_note`를 반환하고 있으므로(`o.completion_note`), 프론트엔드 목록 렌더링 로직만 수정합니다.
   - 기존에는 뷰어(GlobalImageViewer)의 하단 Footer에만 작게 표시되었으나, 대시보드 목록의 각 항목(`erp-completion-row`) 자체에 사진 갤러리와 함께 코멘트가 즉시 보이도록 HTML 마크업을 주입합니다.
   - 적용 방법: 갤러리 마크업 생성 위/아래에 `<div class="erp-completion-note text-muted small mt-2"><i class="fas fa-comment-dots"></i> ${escapeHtml(o.completion_note)}</div>` 형식으로 삽입.
2. **보안 및 UX 확보:**
   - XSS 방지를 위해 기존에 작성된 `escapeHtml()` 함수를 반드시 거쳐 코멘트를 렌더링합니다.
   - 빈 코멘트일 경우 불필요한 공백 렌더링을 방지하기 위한 조건문을 추가합니다.

## 3. 원칙 및 모범 사례 (AGENTS.md 등) 준수 사항
1. **구조적 의심 및 단순화 우선 (Simplification First):** 
   - 새로운 DB 테이블이나 별도 컬럼을 추가하지 않고, PostgreSQL의 JSONB(`structured_data`)의 이점을 활용하여 기존 필드 경로에 데이터를 저장함으로써 스키마 변경 리스크를 배제합니다.
2. **현대적 방식 및 보안 준수:** 
   - Form Data POST 방식 대신 Fetch API의 JSON 통신을 사용하고, 사용자 입력 텍스트는 프론트엔드 노출 시 철저한 이스케이프(Escape) 처리를 강제하여 XSS 취약점을 예방합니다.
3. **오컴의 면도날 (Occam's Razor):** 
   - 이미 `erp_orders_completion.py`에 `completion_note`를 불러오는 로직이 준비되어 있음을 파악했습니다. 새로운 상태 전달 파이프라인을 만들지 않고 기존 데이터 흐름을 재활용하여 단계(Steps)를 최소화합니다.