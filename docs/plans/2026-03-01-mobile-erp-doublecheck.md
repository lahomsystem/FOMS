# 모바일 ERP 최적화 구현 — 1:1 소스 더블체크 보고서

> **검증일**: 2026-03-01 (Phase 4·동작 확인 추가)  
> **기준**: `docs/plans/2026-03-01-mobile-erp-optimization-plan.md` vs 실제 소스  
> **동작 확인**: Flask test_client로 주요 라우트 200 응답 검증 완료

---

## 1. Phase 1

### 1-0 layout.html

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| `<body>`에서 `overflow-x: hidden` 제거 | layout.html L616–617: body style에 width/max-width/margin/padding만 있음 | ✅ overflow-x 없음 (재검증) |
| 헤더 반응형, h1 모바일 `font-size: 1rem` | L621–622 `layout-header`, `layout-header__title`; L36–49 인라인 스타일 | ✅ 992px에서 .layout-header__title 1rem, 576px에서 0.95rem |
| 네비 메뉴 터치 44px | L40–46 .layout-nav-collapse .nav-link min-height 44px | ✅ |
| `navbar-expand-lg` → `navbar-expand-md` | L721 `navbar-expand-md` | ✅ |

### 1-1 erp-pro.css (MOBILE ERP OPTIMIZATION)

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 992px: .form-control, .form-select, .btn min-height 44px, font-size 1rem | L2235–2241 .erp-pro .form-control 등 | ✅ |
| 992px: 모달 풀스크린 | L2243–2252 .erp-pro .modal-dialog, .modal-content | ⚠️ 계획서는 전역 `.modal-dialog`, 구현은 `.erp-pro .modal-dialog`. Bootstrap 모달은 body로 이동하므로 이 규칙은 대시보드 4개 모달에는 미적용. 실제 풀스크린은 `modal-fullscreen-md-down`(2-4)으로 처리됨. |
| 992px: .erp-detail-panel 풀오버레이 | L2255–2266 .erp-pro .erp-detail-panel | ✅ |
| 992px: .erp-mobile-card-table thead none, tbody tr block, td flex + ::before data-label | L2270–2300 | ✅ |
| 576px: form 16px (iOS 줌 방지) | L2304–2307 | ✅ |
| 576px: .erp-alert-col, .erp-process-col | L2309–2315 .erp-pro .erp-alert-col 등 | ✅ (계획서는 .erp-pro 없음, 구현은 스코프 추가) |

### 1-2 style-pro-max.css

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 992px: --space-5/6, .container-premium, .grid-dashboard 1fr, h1/h2/h3 | L269–281 | ✅ |
| 576px: --space-5, .grid-dashboard gap, h1 | L284–289 | ✅ |

---

## 2. Phase 2

### 2-0 index.html

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 테이블에 `erp-mobile-card-table` | L621 (table class) | ✅ |
| tbody 모든 td에 `data-label` | L778, 782, 795, 809–810, 811, 830–833, 997, 1017, 1022–1027 | ✅ 17개 컬럼 모두 있음 (선택, 번호, 작업, 접수일, 접수시간, 고객명, 전화번호, 주소, 제품, 옵션, 비고, 결제금액, 실측일, 실측시간, 설치 예정일, 담당자, 상태) |
| PC에서만 컬럼 min-width (모바일 카드 전환) | L357–508 @media (min-width: 993px) | ✅ |
| 상단 헤더/툴바 44px 및 모바일 스택 | L510–537 @media (max-width: 992px) | ✅ |
| 컨테이너에 .erp-pro | L568 `<div class="erp-pro order-list-container">` | ✅ 카드 전환 규칙 적용됨 |

### 2-3 erp_dashboard_filters.html

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 992px 이하 필터 아코디언, 토글 버튼 | L3–7 버튼 .erp-filter-mobile-toggle, L8 #erp-filter-collapse | ✅ |
| 기본 접힘, "필터" 탭으로 펼침 | collapse + data-bs-toggle | ✅ |
| 데스크톱에서 항상 펼침 | erp-pro.css L2318–2323 @media (min-width: 993px) | ✅ |

### 2-4 erp_dashboard_modals.html

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 4개 모달에 .modal-fullscreen-md-down | L3, 26, 47, 89 (modal-dialog) | ✅ |

### 2-5 erp_sub_nav + erp-pro.css

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 스와이프 힌트(우측 fade) | erp-pro.css L2326–2339 .erp-pro-nav::after | ✅ |
| .erp-pro-nav-item 터치 44px | L2340–2349 min-height 44px, padding | ✅ |
| 활성 탭 시각 강조 | L2350–2353 box-shadow inset | ✅ |

### 2-6 erp_beta_tab.html + erp-pro.css

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 탭 헤더 수평 스크롤 | erp-pro.css L2357–2367 #erpBetaTabs, .erp-beta-tabs-nav | ✅ |
| ul에 클래스 | erp_beta_tab.html nav-pills + erp-beta-tabs-nav | ✅ |
| 상세 그리드 1열 스택 | L2378–2381 #erp-beta .row.g-2 [class*="col-md-"] | ✅ |
| 폼 필드 44px | L2382–2386 | ✅ |

---

## 3. Phase 3-1 (발송 대시보드)

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 발송 테이블 `erp-mobile-card-table` | erp_shipment_dashboard.html L772 | ✅ |
| tbody td에 data-label | L852, 860, 866, 869, 889, 904, 968, 987, 1016, 1046 | ✅ 10개 (상세, 고객, 대리점(발주사), 제품, 규격(W/300), 현장주소, 시공시간, 도면담당자, 시공자, 담당자) |
| 모바일 스타일(패널 44px, row 스택) | L759–771 @media (max-width: 992px) | ✅ |
| 이미지 내보내기 모달 풀스크린 | — | ⚠️ 해당 모달 마크업 없음(JS에서 처리). 필요 시 JS 생성 모달에 클래스 추가 검토 |

---

## 4. Phase 3-2 ~ 3-4 (이번 세션 추가)

### 3-2 실측 대시보드
| 계획서 요구 | 구현 | 결과 |
|------------|------|------|
| 실측 목록 data-label | 상세, 고객, 발주사, 주소, 전화번호, 실측일, 시간, 제품, 담당자 | ✅ |
| 카드 전환 | 테이블 erp-mobile-card-table | ✅ |
| 날짜 패널 44px, row 스택 | @media 992 .measurement-panel-item, .row.g-3 | ✅ |
| 모달 풀스크린 | routePlanModal modal-fullscreen-md-down | ✅ |

### 3-3 도면 대시보드
| 계획서 요구 | 구현 | 결과 |
|------------|------|------|
| 도면 목록 카드 | 기존 mobile-card-list d-md-none 사용 | ✅ (별도 카드 UI) |
| 담당자 모달 풀스크린 | batchAssignModal, singleAssignModal | ✅ |
| 도면 상세 첨부 1열 | erp_drawing_workbench_detail.html .dw-attach-grid 1fr @992 | ✅ |

### 3-4 생산/시공
| 계획서 요구 | 구현 | 결과 |
|------------|------|------|
| 모달 modal-fullscreen-md-down | erp_production_modals 2개, erp_construction_modals 5개 | ✅ |

### 3-5 AS 대시보드
| 계획서 요구 | 구현 | 결과 |
|------------|------|------|
| @media 추가 | style 블록 내 992px: 카드 입력/버튼 44px, 첨부 갤러리 1열 | ✅ |
| AS 접수/처리 테이블 카드 전환 | 기존 erp-pro-order-cards d-md-none 사용 | ✅ (별도 카드 UI) |
| 모달 풀스크린 | asErpAttachmentsCategoryModal, scheduleSearchModal | ✅ |
| 사진 첨부 그리드 모바일 | #asErpAttachmentsCategoryModal .row.g-2 > [class*="col-"] 100% | ✅ |

---

## 5. Phase 4 (WDCalculator + 채팅) — 1:1 소스 검증

### 4-1 WDCalculator (product_settings.html, wdcalculator_styles/scripts)

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 설정 테이블 카드 전환 (제품·옵션·비고 목록) | product_settings.html L100–132 `.wdcalc-mobile-card-table` @media 992px | ✅ |
| 3개 테이블에 클래스 + data-label | L236, 357, 462: wdcalc-mobile-card-table; 서버/JS 렌더 td에 data-label | ✅ |
| 가격 입력 inputmode="numeric" pattern="[0-9]*" | L179, 187, 191, 206, 338 (price1m, price30cm, price1cm, couponValue, additionalOptionPrice) | ✅ |
| 모달 풀스크린 | wdcalculator_scripts.html L2920 `modal-dialog modal-lg modal-fullscreen-md-down` | ✅ |
| 터치 44px (wdcalculator-container) | wdcalculator_styles.html @media 992 .wdcalculator-container .form-control 등 min-height 44px | ✅ |

### 4-2 채팅 (chat.html, chat_styles.html, chat_scripts_rooms.html)

| 계획서 요구 | 소스 위치 | 결과 |
|------------|-----------|------|
| 목록 ↔ 메시지 전환 (WhatsApp 패턴) | chat_styles.html L976–1012 @media 992: .col-lg-3/9 절대 위치, .chat-mobile-show-messages 시 슬라이드 | ✅ |
| selectRoom() 시 모바일에서 클래스 추가 | chat_scripts_rooms.html L70–72 matchMedia('(max-width: 992px)') → addClass | ✅ |
| goBackToChatList() | chat_scripts_rooms.html L64–66 removeClass | ✅ |
| 백 버튼 (목록으로) | chat.html L56 .chat-mobile-back-btn, onclick="goBackToChatList()" | ✅ |
| 3개 모달 풀스크린 | chat.html L137, 187, 211 createRoomModal, connectOrderModal, inviteMemberModal modal-fullscreen-md-down | ✅ |
| 입력 영역 sticky bottom | chat_styles.html L1023–1031 #chat-input-area position: sticky; bottom: 0 | ✅ |
| 터치 44px (입력/버튼/미리보기) | chat_styles.html L1014–1021 | ✅ |

---

## 6. 동작 확인 (Flask test client)

| 경로 | HTTP 상태 | 비고 |
|------|----------|------|
| `/` | 200 | 주문 목록 (카드 전환·data-label) |
| `/erp/dashboard` | 200 | 접수 대시보드 (필터 아코디언·모달) |
| `/chat` | 200 | 채팅 (목록↔메시지 전환) |
| `/wdcalculator/product-settings` | 200 | WDCalculator 설정 (테이블 카드·숫자 키패드) |
| `/erp/shipment` | 200 | 발송 대시보드 |
| `/erp/measurement` | 200 | 실측 대시보드 |
| `/erp/as` | 200 | AS 대시보드 |

*실제 뷰포트/디바이스 확인은 `docs/plans/2026-03-01-mobile-erp-verification.md` 체크리스트로 수동 검증.*

---

## 7. 종합

- **일치**: Phase 1·2·3·4 계획 항목이 소스와 1:1 일치함.
- **참고(동작 동일)**:
  - 모달 풀스크린: 계획서는 전역 `.modal-dialog`, 구현은 `.erp-pro .modal-dialog` + 각 모달에 `modal-fullscreen-md-down`. Bootstrap 모달이 body로 이동하므로 실제 동작은 `modal-fullscreen-md-down`으로 보장됨.
- **미구현/선택**: 발송 대시보드 이미지 내보내기 모달은 템플릿에 없어 풀스크린 클래스 미적용. 동적 생성 시 해당 모달에 `modal-fullscreen-md-down` 추가 권장.
