# ERP Beta 발주사: 드롭다운(라홈/하우드) + 직접입력 체크박스

**일자:** 2026-02-23  
**기준:** GDM 코드 리뷰 → 계획 → 구현 → 마무리 리뷰

---

## 1. 요구사항

- 발주사 필드를 **드롭다운**으로 변경: 옵션 **'라홈', '하우드'**.
- **발주사** 라벨 옆에 **'직접입력'** 체크박스 추가.
- 체크 시 **직접 입력** 가능(텍스트 입력란 표시); 미체크 시 드롭다운만 사용.

---

## 2. 관련 코드 (리뷰 요약)

| 위치 | 용도 |
|------|------|
| `templates/partials/erp_beta_tab.html` | 발주사 라벨 + input#erp-orderer (현재 텍스트 1개) |
| `templates/partials/erp_beta_js.html` | 로드 시 erp-orderer 값 세팅, erpCollectStructured에서 getVal('erp-orderer'), 텍스트 변환 시 기본 '라홈' |

- 저장 구조: `parties.orderer.name` (문자열). 기존과 동일 유지.
- 기존 로직: '라홈' 포함 시 라홈팀(CS) 등 정책 있음 → 값만 드롭다운/직접입력으로 선택되게 하면 됨.

---

## 3. 구현 계획

### 3.1 템플릿 (erp_beta_tab.html)

- **발주사** 라벨 + **직접입력** 체크박스(같은 줄).
- **드롭다운:** `<select id="erp-orderer-select">` 옵션 `라홈`, `하우드`.
- **직접입력란:** `<input id="erp-orderer" ...>` (체크 시에만 표시/사용).
- 초기: 체크 해제 시 드롭다운 표시, 체크 시 입력란 표시. 로드 시 값에 따라 체크/드롭다운/입력 상태 결정.

### 3.2 JS (erp_beta_js.html)

- **토글:** '직접입력' 체크 시 입력란 표시·드롭다운 숨김, 해제 시 드롭다운 표시·입력란 숨김. 페이지 로드 후 한 번 실행 + 체크박스 change 시 실행.
- **로드(erpLoadStructured):** `parties.orderer.name`이 '라홈' 또는 '하우드'이면 select 설정, 체크 해제, 입력란 숨김. 그 외 값이면 입력란에 넣고 체크, 드롭다운 숨김(또는 첫 옵션 유지).
- **저장(erpCollectStructured):** 직접입력 체크 시 `getVal('erp-orderer')`, 아니면 `getVal('erp-orderer-select')` → `parties.orderer.name`.
- **텍스트 변환:** 현재 `getVal('erp-orderer')` 대신 **실제 선택된 발주사 값**(드롭다운 또는 직접입력) 사용하는 공통 헬퍼 사용. (예: `getOrdererValue()`)

---

## 4. 검증

- 드롭다운에서 라홈/하우드 선택 후 저장 → structured_data에 해당 값 저장.
- 직접입력 체크 후 텍스트 입력·저장 → 해당 문자열 저장.
- 기존 주문 로드 시 라홈/하우드면 드롭다운 선택, 그 외면 직접입력 체크 + 입력란에 값 표시.
