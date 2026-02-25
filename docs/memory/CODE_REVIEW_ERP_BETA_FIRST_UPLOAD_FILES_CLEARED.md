# 코드 리뷰: 새로고침 후 첫 업로드 시 선택 파일 소실

**일자**: 2026-02-25  
**증상**: 브라우저 새로고침 후 파일 선택 → 업로드 버튼 클릭 시 선택한 파일이 전부 사라지고 업로드 안 됨. 두 번째 시도부터는 정상.  
**참조**: `.cursor/agents/grand-develop-master.md`

---

## 1) 원인 (GDM §4 시간 차원)

- **실행 순서**: `erpUploadSelectedAttachments()` 안에서 **먼저** `if (!ORDER_ID)` → `await erpRequireOrderIdOrWarn(...)` 호출.
- **드래프트 모드**: 새로고침 직후(add_order 또는 draft)에는 `ORDER_ID`가 0/null → `erpRequireOrderIdOrWarn` → `erpEnsureDraftOrderId()` → 서버에 draft 생성 → `erpSetOrderId(data.order_id)` 호출.
- **파일 소실**: `erpSetOrderId()` 내부에서 `oldOrderId !== ORDER_ID`일 때 **의도적으로** `document.getElementById('erp-attachments-input').value = ''` 로 파일 input 초기화(다른 주문으로 바뀌었을 때 이전 선택 제거용).  
  이때 `ORDER_ID`가 0 → 새 주문 ID로 바뀌므로 조건이 참이 되어, **await 직후** 파일 input이 비워짐.
- **결과**: 그 다음 줄에서 `input.files.length === 0`이 되어 "업로드할 파일을 선택하세요"만 표시되고 함수 종료.

두 번째부터는 `ORDER_ID`가 이미 있어서 `erpRequireOrderIdOrWarn`/`erpSetOrderId`가 호출되지 않아 input이 비워지지 않음.

---

## 2) 수정 내용

- **파일**: `templates/partials/erp_beta_js.html` — `erpUploadSelectedAttachments()`.
- **변경**: **파일 목록을 먼저 읽어 배열로 보관한 뒤** ORDER_ID 확인.
  - `const input = ...`, `if (!input.files || input.files.length === 0) return`, `const files = Array.from(input.files)` 를 **ORDER_ID 체크/await 보다 앞**으로 이동.
  - 이후 `if (!ORDER_ID) { await erpRequireOrderIdOrWarn(...); if (!ok) return; }` 실행.
- **효과**: `erpSetOrderId()`로 input이 비워져도, 이미 `files` 배열에 복사된 File 목록으로 업로드 진행.

---

## 3) 참조 코드 위치

| 항목 | 파일: 라인 |
|------|------------|
| 파일 input 초기화(ORDER_ID 변경 시) | `erp_beta_js.html`: `erpSetOrderId()` 내부 `fileInput.value = ''` |
| 업로드 버튼 클릭 핸들러 | `erp_beta_js.html`: `erpUploadSelectedAttachments` |
| 수정 구간 | `erpUploadSelectedAttachments` 상단: input/files 읽기 → 그 다음 ORDER_ID 확인 |
