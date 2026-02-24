# GDM 코드 리뷰: ERP Beta 발주사 드롭다운 + 직접입력

**일자:** 2026-02-23  
**기준:** `.cursor/agents/grand-develop-master.md`  
**계획:** `docs/memory/PLAN_ERP_ORDERER_DROPDOWN.md`

---

## 변경 요약

- 발주사 필드를 **드롭다운(라홈/하우드)** + **직접입력** 체크박스로 변경.
- 발주사 라벨 옆에 "직접입력" 체크 시 텍스트 입력란 표시, 미체크 시 드롭다운만 사용.
- 저장 구조 `parties.orderer.name` 유지, 기존 정책(라홈 포함 시 라홈팀 등) 그대로 동작.

---

## 마무리 코드 리뷰

### 1. 템플릿 `templates/partials/erp_beta_tab.html`

| 항목 | 내용 | 판정 |
|------|------|------|
| 라벨 | "발주사" + 같은 줄에 체크박스 "직접입력" (form-check-inline) | ✅ |
| 드롭다운 | `id="erp-orderer-select"`, 옵션 라홈, 하우드 | ✅ |
| 직접입력란 | `id="erp-orderer"`, 초기 `d-none`, placeholder | ✅ |
| Bootstrap | form-label, form-select, form-control, form-check 사용 | ✅ |

### 2. JS `templates/partials/erp_beta_js.html`

| 항목 | 내용 | 판정 |
|------|------|------|
| getOrdererValue() | 직접입력 체크 시 input 값, 아니면 select 값 반환 | ✅ |
| toggleOrdererUI() | 체크 시 select 숨김/input 표시, 해제 시 반대 | ✅ |
| DOMContentLoaded | erp-orderer-direct change → toggleOrdererUI, 초기 1회 호출 | ✅ |
| 로드(erpLoadStructured) | orderer가 라홈/하우드면 select·체크 해제, 아니면 input·체크 | ✅ |
| 저장(erpCollectStructured) | orderer.name = getOrdererValue() | ✅ |
| 텍스트 변환 | getOrdererValue() 사용, 빈 값 시 기본 '라홈' | ✅ |

### 3. 일관성·호환

- 대시보드/정책에서 사용하는 `parties.orderer.name` 문자열 그대로 사용.
- 기존 '라홈' 포함 시 라홈팀(CS) 등 로직은 값만 바뀌어도 동일 적용.

---

## 수정 파일

| 파일 | 변경 |
|------|------|
| `templates/partials/erp_beta_tab.html` | 발주사: 라벨+직접입력 체크, select(라홈/하우드), input(d-none) |
| `templates/partials/erp_beta_js.html` | getOrdererValue, toggleOrdererUI, 로드/저장/텍스트변환 반영, 체크박스 바인딩 |

---

## 검증 제안

- 드롭다운에서 라홈/하우드 선택 후 저장 → 해당 값이 parties.orderer.name에 저장되는지 확인.
- 직접입력 체크 후 텍스트 입력·저장 → 입력한 문자열이 저장되는지 확인.
- 기존 주문(라홈/하우드) 로드 시 드롭다운 선택·체크 해제 상태인지 확인.
- 기존 주문(그 외 발주사명) 로드 시 직접입력 체크·입력란에 값 표시되는지 확인.
