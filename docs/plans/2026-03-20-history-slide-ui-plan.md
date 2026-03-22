# 과거 이력 검색 상세 슬라이드 UI 적용 계획서 (Phase 1)

## 1. 개요
현재 실측 대시보드에서 제공하는 "주문 상세 하단 슬라이드(제품 정보 + 첨부 이미지)" 기능을 과거 이력 검색(`/erp/history/`)에도 동일하게 적용합니다. 이를 통해 페이지 이동 없이 검색 결과에서 즉시 상세 내역을 확인할 수 있습니다.

## 2. 부하 이슈 분석 및 권장 해결책
- **이슈:** 50건의 주문에 대해 제품 항목과 첨부파일(이미지, 동영상 등)을 모두 미리 로드하면 DB 쿼리(N+1 문제) 및 브라우저 메모리 부하(수백 개의 이미지 동시 로드)가 발생할 수 있습니다.
- **해결책 (권장 방식):** 
  1. **서버 사이드 (DB 쿼리 최적화):** `services.erp_product_items`의 `build_product_items_for_orders` 함수를 사용하여 50개 주문의 첨부파일을 **단 1번의 쿼리**로 가져옵니다. (N+1 문제 원천 차단)
  2. **클라이언트 사이드 (지연 로딩):** 이미지는 `<img data-src="...">` 형태로 렌더링하여 초기 로딩 시 네트워크 요청을 막고, 사용자가 **꺾쇠(Chevron)를 클릭해 슬라이드를 열 때만 `src`로 변환**하여 이미지를 로드합니다. 동영상의 경우 썸네일을 표시하거나 `preload="none"`으로 설정합니다.

## 3. 구현 단계
**Step 1: 백엔드 (`apps/erp_history_page.py`) 수정**
- `build_product_items_for_orders`를 import 하여, 페이지에 표시될 50개의 `orders` 배열에 대해 제품 항목과 첨부 파일 정보를 매핑.
- 템플릿 렌더링 시 이 정보를 넘길 수 있도록 컨텍스트에 포함 (`display_o.product_items` 로 매핑).

**Step 2: 프론트엔드 (`templates/erp_history_dashboard.html`) 수정**
- 검색 결과 테이블 행(`<tr>`)의 ID 열이나 끝 열에 토글용 꺾쇠 아이콘(`<i class="fas fa-chevron-down measurement-chevron">`) 추가.
- 각 행 바로 밑에 숨겨진(hidden) 상세 행(`<tr class="measurement-detail-row" style="display:none;">`) 추가.
- 내부에 제품 정보, 규격, 색상, 실측 첨부 이미지 등 렌더링. (`erp_measurement_dashboard.html`의 UI 카드 구조 차용)

**Step 3: 스크립트 수정/추가**
- `measurement.js`에 있는 꺾쇠 토글 및 `data-src` 지연 로딩 스크립트 로직을 이력 대시보드 템플릿 하단에 스크립트로 추가. (단, 공통 스크립트로 분리하기엔 영향도가 있으므로 해당 페이지내 script 블록으로 추가)

## 4. 검증 계획
- `build_product_items_for_orders`가 1번만 실행되는지 확인.
- 초기 로드 시 이미지 네트워크 요청이 발생하지 않음을 검증 (개발자 도구).
- 슬라이드 오픈 시 이미지 렌더링 확인.
