# Spec: 주문 추가 시 발주사별 워크플로우 단계 기본값

> 작성일: 2026-03-04 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 대상 화면
- **URL**: `/add?open=erp-beta` (주문 추가, ERP Beta 탭)
- **출처**: https://lahom-production.up.railway.app/add?open=erp-beta

### 1.2 관련 UI 요소
| 요소 | ID | 설명 |
|------|-----|------|
| 발주사 | `erp-orderer-select` | 드롭다운: 라홈, 하우드 + 직접입력 토글 |
| 워크플로우 단계 | `erp-workflow-stage` | RECEIVED, MEASURE, DRAWING, CONFIRM, PRODUCTION, CONSTRUCTION, CS, AS_RECEIVED, AS_COMPLETED, COMPLETED, AS |

### 1.3 기능 요구사항
- **발주사 = '라홈'** → 워크플로우 단계 기본값 변경 없음 (현재 동작 유지)
- **발주사 ≠ '라홈'** (하우드, 직접입력 포함) → 워크플로우 단계를 **'실측'(MEASURE)** 으로 자동 설정

### 1.4 예외/제약
- 발주사 변경 시에만 기본값 적용 (초기 로드 시 + 발주사 변경 시)
- 사용자가 이미 단계를 수동 선택한 경우, 발주사 변경 시 MEASURE로 덮어씀 (요구사항에 따름)

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `templates/partials/erp_beta_js.html` | 발주사 변경/초기화 시 `erp-orderer-select` 값에 따라 `erp-workflow-stage`를 MEASURE로 설정하는 로직 추가 |

### 2.2 구현 방향
- `erp-orderer-select` change 이벤트 + 초기 로드 시 값 확인
- `selectEl.value === '라홈'` → 무시
- 그 외(하우드, 직접입력 시 `erp-orderer` input 값) → `erp-workflow-stage` value = `MEASURE`

### 2.3 의존성 및 영향 범위
- ERP Beta 주문 추가 폼만 영향
- DB/API 변경 없음

## 3. Steps — 실행 단계
- [x] Step 1: `erp-orderer-select` change 핸들러에 워크플로우 기본값 로직 추가
- [x] Step 2: 직접입력 토글 시(`erp-orderer` input 사용 시)에도 동일 규칙 적용
- [x] Step 3: ERP Beta 탭 초기 로드 시 발주사/워크플로우 기본값 동기화

## 4. 검증 기준
- [x] 발주사 '라홈' 선택 시 워크플로우 단계 변경 없음
- [x] 발주사 '하우드' 선택 시 워크플로우 단계 '실측'(MEASURE) 자동 선택
- [x] 발주사 직접입력 시 워크플로우 단계 '실측'(MEASURE) 자동 선택

## 5. 참고
- 관련 템플릿: `templates/partials/erp_beta_tab.html`, `erp_beta_js.html`
- 발주사·워크플로우 연동 기존 로직: `erp_beta_js.html` L34, L42, L451, L465, L632, L736, L1830
