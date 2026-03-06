# 🛠️ GDM 개발 계획서: ERP Beta 'AS접수' 팝업 연동 구현

> **더블체크 완료** (2026-03-05 11:53 KST)
> 실제 코드베이스 교차검증 결과를 반영한 정밀 계획서입니다.

---

## 1. 개요 및 기획 의도
- **목표:** ERP Beta 주문 편집 화면(`edit_order.html`)에서 "진행단계(`#erp-workflow-stage`)" 셀렉트를 **"AS접수"(`AS_RECEIVED`)**로 바꿀 때, 전용 팝업 모달을 띄워 **AS 내용(텍스트)** + **미디어 파일(사진/동영상/GIF)**을 즉시 입력받습니다.
- **연동 목표:** 팝업에서 입력한 데이터가 기존 **AS 대시보드(`/erp/as`)** 화면의 아래 두 곳에 자동으로 반영되어야 합니다:
  - `textarea.as-content-input` → AS 내용 필드
  - `button.as-photos-btn` → 첨부파일 뷰어(이미지/동영상 모달)

---

## 2. GDM 코드베이스 감사 결과 (더블체크)

### 2-1. 기존 상태 변경 흐름 (현행 구조)
| # | 단계 | 파일 위치 | 핵심 코드 |
|---|------|-----------|-----------|
| 1 | 사용자가 `#erp-workflow-stage` 값 변경 | `partials/erp_beta_tab.html`:L123 | `<select id="erp-workflow-stage">` |
| 2 | "저장" 버튼 클릭 시 `erpSaveStructured()` 호출 | `partials/erp_beta_js.html`:L656 | `erpCollectStructured()` → `workflow.stage` 값을 JSON에 포함 |
| 3 | 서버 API `PUT /api/orders/<id>/structured` | `apps/api/orders.py` | JSON으로 `structured_data.workflow.stage` 저장 |

> ⚠️ **현행 문제:** 상태만 저장되고, AS 내용·사진은 사용자가 별도로 AS 대시보드까지 가서 입력해야 합니다.

### 2-2. AS 내용 저장 경로 (실제 DB 스키마)
코드 교차검증 결과, AS 내용 텍스트의 **정확한 저장 위치**:
```
structured_data → shipment → as_content   (String)
```
- **읽기:** `erp_as_dashboard.html`:L243 → `r.structured_data.get('shipment', {}).get('as_content', '')`
- **쓰기:** `apps/api/orders.py`:L679-682 → `shipment['as_content'] = value`
- **쓰기(AS전용):** `apps/api/erp_orders_as.py`:L194-230 → `api_as_register()` 엔드포인트

### 2-3. AS 첨부파일 업로드 경로 (실제 업로드 메커니즘)
코드 교차검증 결과, AS 첨부파일의 **정확한 업로드 흐름**:
1. **세션 생성:** `POST /api/upload/session/batch` — `folder: 'orders/<id>/attachments'`, `category: 'as'`
2. **S3 Direct Upload:** `PUT <upload_url>` — presigned URL로 직접 전송
3. **완료 등록:** `POST /api/orders/<id>/attachments/complete` — `key`, `filename`, `category: 'as'`, `size`
4. **Fallback:** `POST /api/orders/<id>/attachments` — FormData 멀티파트 업로드
- **뷰어:** `as-photos-btn` 클릭 → `asErpAttachmentsCategoryModal` 모달 → `refreshAsModalAttachments()` 호출

### 2-4. 기존 AS 접수 전용 API
`apps/api/erp_orders_as.py`:L194 에 이미 존재하는 API:
```
POST /api/orders/<id>/as/register
```
- `as_content` 저장 (`structured_data.shipment.as_content`)
- `as_received_date = 오늘` 설정
- `order.status = 'AS_RECEIVED'` 변경
- ✅ **이 API를 그대로 재사용** 가능 (새 API 불필요)

---

## 3. 핵심 조치 계획 (Implementation Plan)

### Phase 1: Frontend — 이벤트 인터셉트 + 모달 UI

**파일:** `partials/erp_beta_js.html`

1. **이벤트 가로채기:**
   - `erpSaveStructured()` 함수 내부(L656)에서, `erpCollectStructured()` 결과의 `workflow.stage` 값이 `'AS_RECEIVED'`인지 검사.
   - 만약 `AS_RECEIVED`이면 기존 저장 흐름을 중단(return)하고, `asReceiveModal`을 표시.

2. **AS 접수 모달 (`asReceiveModal`) 생성:**

**파일:** `templates/partials/erp_beta_tab.html` (하단에 모달 HTML 추가)

```html
<div class="modal fade" id="asReceiveModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title"><i class="fas fa-exclamation-circle text-warning"></i> AS 접수</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="mb-3">
          <label class="form-label fw-bold">AS 내용 <span class="text-danger">*</span></label>
          <textarea id="as-receive-content" class="form-control" rows="5"
            placeholder="예: 슬라이딩 붙박이장 가운데 문이 내려앉음(안닫힘)&#10;금일 오후 4시반~6시반까지 통화 어려우심"></textarea>
        </div>
        <div class="mb-3">
          <label class="form-label fw-bold">사진/동영상 첨부</label>
          <input type="file" id="as-receive-files" class="form-control" 
            multiple accept="image/*,video/*,.gif">
          <div id="as-receive-preview" class="d-flex flex-wrap gap-2 mt-2"></div>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">취소</button>
        <button type="button" class="btn btn-primary" id="as-receive-submit-btn">
          <i class="fas fa-check"></i> AS 접수 확인
        </button>
      </div>
    </div>
  </div>
</div>
```

3. **"확인" 버튼 클릭 시 원자적 전송:**
   - **Step A:** `POST /api/orders/<id>/as/register` 호출 → `as_content` 텍스트 전소 + 상태 `AS_RECEIVED`로 변경
   - **Step B:** 첨부파일이 있으면, 기존 AS 대시보드와 동일한 업로드 흐름 재사용:
     - `POST /api/upload/session/batch` → S3 Direct Upload → `POST /api/orders/<id>/attachments/complete` (category: `'as'`)
   - **Step C:** 성공 시 ERP Beta 화면의 structured_data 리프레시 (`erpLoadStructured()`)

4. **"취소" 시 롤백:**
   - `asReceiveModal`이 `hidden.bs.modal` 이벤트 발생 시, 제출 완료 플래그가 없으면 `#erp-workflow-stage` 값을 이전 값으로 복원.

### Phase 2: Backend — 기존 API 활용 (신규 API 불필요 ✅)

기존 `POST /api/orders/<id>/as/register` (erp_orders_as.py:L194)가 이미 필요한 모든 로직을 갖추고 있습니다:
- `structured_data.shipment.as_content` 저장
- `order.as_received_date = today` 설정
- `order.status = 'AS_RECEIVED'` 변경

**단, 한 가지 보강이 필요합니다:**
현재 이 API는 `@erp_construction_edit_required` 데코레이터를 사용합니다. ERP Beta 편집 화면에서도 호출할 수 있도록 `@erp_edit_required`로 변경하거나, 양쪽 모두 허용하는 로직을 추가해야 합니다.

### Phase 3: AS 대시보드 상호운용성 검증

| 검증 항목 | 대상 코드 | 기대 결과 |
|-----------|-----------|-----------|
| AS 내용 표시 | `erp_as_dashboard.html`:L243 `r.structured_data.get('shipment', {}).get('as_content', '')` | 팝업에서 입력한 텍스트가 그대로 표시 |
| AS 사진 표시 | `as-photos-btn` → `refreshAsModalAttachments()` | 업로드한 이미지/동영상이 뷰어에 노출 |
| AS 접수일 | `order.as_received_date` | 오늘 날짜 자동 세팅 |
| 상태 뱃지 | `erp_as_dashboard.html`:L246-249 | "AS접수" 뱃지 표시 |

---

## 4. 수정 대상 파일 목록

| 파일 | 수정 내용 |
|------|-----------|
| `templates/partials/erp_beta_tab.html` | AS 접수 모달 HTML 추가 |
| `templates/partials/erp_beta_js.html` | `erpSaveStructured()` 인터셉트 + 모달 제어 JS + 파일 업로드 JS |
| `apps/api/erp_orders_as.py` | 권한 데코레이터 확인/조정 (필요 시) |

---

## 5. 예외 케이스 점검 (Edge Cases)
- **동영상 용량 제한:** 클라이언트에서 파일 크기 체크 (10MB 이상 경고)
- **내용 미입력:** textarea 비어있으면 "AS 내용을 입력해주세요" Alert 후 전송 차단
- **중복 클릭 방지:** 제출 버튼 `disabled` 처리 + 스피너 표시
- **Fallback 모드:** presigned URL 실패 시 기존 FormData 멀티파트 업로드 자동 전환 (AS 대시보드와 동일한 로직)
- **기존 AS 내용 보존:** 이미 AS 내용이 있는 경우, textarea에 기존 내용을 prefetch하여 보여주고 덮어쓰기 가능하게
