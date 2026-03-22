# 생산 대시보드 헤더 고정 (Sticky Header) 적용 계획서

## 1. 목적
생산 대시보드(`/erp/production/dashboard`) 테이블의 헤더가 스크롤 시 고정되지 않고 둥둥 떠보이는 문제(배경 투명화 및 테두리 소실 현상)를 해결하고, 메인 대시보드(`/erp/dashboard`)와 동일한 수준의 고정(Sticky) 헤더 UI를 적용합니다.

## 2. 현상 분석
- **문제점:** 현재 `templates/partials/erp_production_styles.html` 내에 `position: sticky; top: 0;`가 정의되어 있으나, 스크롤 다운 시 테이블 데이터와 겹치며 배경이 투명해지거나 경계선이 사라지는(floating) 현상이 발생.
- **원인:** `th` 요소의 `background` 속성 우선순위 문제(인라인 스타일 또는 `!important` 누락)와 `border-collapse` 상태에서 `box-shadow`를 이용한 경계선 처리가 없기 때문.

## 3. 수정 방안
**Step 1: CSS 스타일 동기화 (`erp_production_styles.html`)**
- `#erp-grid` 에 `border-collapse: separate; border-spacing: 0;` 속성 추가.
- `#erp-grid thead th` 에 다음 속성들 일괄 적용 (메인 대시보드 `erp_dashboard_styles.html`과 동일)
  - `position: sticky !important;`
  - `background: #f8f9fa !important;`
  - `background-clip: padding-box;` (배경 번짐 방지)
  - `box-shadow: inset 0 -1px 0 #dee2e6, 0 2px 6px rgba(15, 23, 42, 0.06);` (스크롤 시 입체감 있는 경계선 유지)

**Step 2: HTML 구조 동기화 (`erp_production_filters_grid.html`)**
- `table` 태그에 `erp-dashboard-grid-resizable` 클래스 추가.
- 사용자가 제시한 예시처럼 각 `th` 내부에 리사이즈를 위한 `<div class="erp-col-resizer"></div>`를 추가하여 메인 대시보드와 UI/UX 통일.

## 4. 검증 체크리스트
- [x] 생산 대시보드에서 하단 스크롤 시 헤더가 상단에 고정되는지 확인
- [x] 스크롤 시 헤더의 배경색이 유지되고 데이터와 겹치지 않는지 확인
- [x] 헤더 하단 그림자(`box-shadow`)가 정상적으로 표시되는지 확인
