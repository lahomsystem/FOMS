# ERP 모바일 구현 1:1 감리 (2026-04-03)

## 범위

- 사용자 요청:
  - 모바일에서 전역 메뉴(`캘린더` ~ `휴지통`)를 완전히 숨길 것
  - 모바일 출고 페이지 파손 여부를 계획서 기준으로 재검토하고 수정할 것
  - 계획서와 실제 구현을 세부적으로 1:1 감리할 것
- 기준 문서:
  - `docs/context/analysis/erp-mobile-implementation-plan-2026-04-01.md`
  - `docs/context/analysis/erp-mobile-plan-source-audit-2026-04-02.md`

## 결론

- 판정: `부분 드리프트` 상태였고, 이번 수정으로 사용자 요청 범위는 `통과`로 정리했다.
- 데스크톱 UI 영향: 없음
  - `templates/layout.html` 수정은 `erp_mobile_v2_enabled` + `/erp` 경로 + `max-width: 992px`에서만 적용된다.
  - `templates/erp_shipment_dashboard.html` 수정도 `max-width: 992px`에서만 적용된다.

## 근본 원인

### 1. 전역 메뉴 섹션

- 계획서 의도:
  - ERP 모바일 셸이 활성화된 화면에서는 모바일 정보 구조가 ERP 전용 셸 중심이어야 한다.
  - ERP 화면의 모바일 상단 정보는 `shell header + page header + bottom nav`로 정리돼야 한다.
- 실제 코드:
  - `templates/layout.html`의 전역 메뉴 `nav`가 ERP 모바일 V2와 무관하게 렌더됐다.
  - 따라서 ERP 모바일 셸 위에 레거시 전역 메뉴가 한 번 더 나타나 모바일 세로 공간을 소비했다.
- 근본 원인:
  - ERP 모바일 설계가 페이지 내부(`.erp-mobile-shell`)까지만 적용됐고, 공통 레이아웃(`layout.html`)의 모바일 노출 조건은 정리되지 않았다.

### 2. 출고 페이지 모바일 파손

- 계획서 의도:
  - Phase 5에서 출고는 `CSS Cardified Table Family`로 유지하되, 모바일 셸과 충돌하지 않아야 한다.
  - 감리 기준 9.1에 따라 모바일에서 가로 스크롤 없이 읽을 수 있어야 한다.
- 실제 코드:
  - 출고 테이블은 `erp-mobile-card-table` 공통 규칙을 탔지만, 동시에 데스크톱용 `colgroup + table-layout: fixed + column-resize` 체계를 그대로 유지했다.
  - 브라우저 실측에서:
    - wrapper 폭: `388px`
    - table 폭: `1124px`
    - 첫 번째 모바일 row 폭: `60px`
- 근본 원인:
  - 모바일 카드화를 `tr display:block` 수준에서만 적용했고, 출고 전용 데스크톱 열 폭 시스템(`colgroup`)을 모바일에서 해제하지 않았다.
  - 그 결과 카드 row가 전체 폭이 아니라 첫 번째 컬럼 폭에 갇혀 세로 문자열처럼 붕괴했다.

## 수정 내용

### 1. 전역 메뉴 모바일 숨김

- 파일: `templates/layout.html`
- 반영:
  - ERP 모바일 V2 페이지 전용 body class 추가:
    - `erp-mobile-v2-layout`
  - 전역 메뉴 nav에 식별 class 추가:
    - `layout-global-nav`
  - 모바일(`max-width: 992px`) + ERP 모바일 V2 페이지에서만 전역 메뉴 숨김

### 2. 출고 모바일 카드 붕괴 수정

- 파일: `templates/erp_shipment_dashboard.html`
- 반영:
  - 모바일에서 `#shipment-dashboard-table`를 table formatting context에서 분리
  - `colgroup`, `col`을 모바일에서 비활성화
  - `tbody`, `tr`, `td`를 출고 전용 카드 블록 흐름으로 재정렬
  - `td::before` 라벨은 상단 label, 값은 하단 block으로 고정
  - `shipment-spec-line` 줄바꿈 허용
  - 복합 편집 블록(`shipment-edit-list`, `shipment-text-row`, `shipment-address-block`) 폭 100% 보장

## 1:1 대조 판정

### Phase 0. 공통 셸

- 기준:
  - 모바일 셸이 기존 레이아웃과 충돌하지 않아야 한다.
- 수정 전:
  - `layout.html` 전역 메뉴가 ERP 모바일 셸 위에 남아 충돌
- 수정 후:
  - 모바일 ERP 페이지에서 전역 메뉴 숨김
- 판정: 통과

### Phase 5. 출고

- 기준:
  - `erp-mobile-card-table` 유지
  - 필터/액션 우선 정리
  - 모바일 셸과 충돌하지 않아야 함
  - 가로 스크롤/붕괴 없이 읽혀야 함
- 수정 전:
  - `erp-mobile-card-table` 자체는 유지됐지만, 데스크톱 `colgroup` 제약이 남아 실제 카드가 붕괴
  - 계획서의 “유지”가 “공통 규칙 그대로 적용”으로 오해돼 specialized 처리 부족
- 수정 후:
  - 카드화 전략은 유지하되, 출고 전용 모바일 override로 데스크톱 폭 시스템을 해제
  - 필터/summary/action 구조는 기존 유지
- 판정: 통과

## 검증

### 테스트

- 실행:
  - `python -m pytest tests\\test_erp_mobile_layout_and_shipment.py tests\\test_erp_measurement_mobile_render.py tests\\test_user_delete.py -q`
- 결과:
  - `5 passed`

### 실브라우저

- 아티팩트:
  - `docs/context/analysis/browser_audit_2026-04-03_menu_shipment_fix/results.json`
  - `docs/context/analysis/browser_audit_2026-04-03_menu_shipment_fix/screenshots/`
- 판정:
  - phone `/erp/dashboard`
    - `bodyClass = erp-mobile-v2-layout`
    - 전역 메뉴 DOM 미노출
    - 가로 오버플로 `0`
  - tablet `/erp/dashboard`
    - `bodyClass = erp-mobile-v2-layout`
    - 전역 메뉴 DOM 미노출
    - 가로 오버플로 `0`
  - phone `/erp/shipment`
    - 첫 row 폭 `388px`
    - 가로 오버플로 `0`
  - tablet `/erp/shipment`
    - 첫 row 폭 `818px`
    - 가로 오버플로 `0`

## 남은 리스크

- 이번 수정은 사용자 요청 범위인 `전역 메뉴`와 `출고 모바일 붕괴`를 닫는 데 집중했다.
- 다른 ERP 화면의 카드 밀도나 정보 우선순위 개선 여지는 남아 있지만, 현재 확인된 blocker는 아니다.
