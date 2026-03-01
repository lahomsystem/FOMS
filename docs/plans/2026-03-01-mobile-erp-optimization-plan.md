# FOMS 모바일 ERP 최적화 — 상세 구축 계획서

> **작성일**: 2026-03-01
> **최종 검증일**: 2026-03-01 12:00 (실제 소스 코드 교차검증 완료)
> **실행 환경**: Cursor IDE (메인) + Antigravity (보조)
> **대상 범위**: ERP 대시보드 전체 (접수~시공) + WDCalculator + 채팅
> **기준 문헌**: 2025-2026 ERP Mobile UX 트렌드 분석 결과 반영
> **현재 브랜치**: deploy
> **Bootstrap 버전**: 5.3.0-alpha1 (`modal-fullscreen-md-down` 지원 확인됨)

---

## 0. 배경 및 목적

### 0.1 현재 문제

FOMS는 일반 웹사이트가 아닌 **가구 ERP 시스템**으로, 한 화면에 표시해야 할 정보가 매우 많고 다양합니다:
- 주문 목록: 16개 컬럼 (번호, 접수일, 고객, 주소, 제품, 옵션, 비고, 결제금액, 실측일 ...)
- ERP 대시보드: 경보 타일 + 프로세스 맵 + 필터 패널 + 작업 큐 테이블 + 상세 패널
- 발송/도면/실측/시공: 각각 고유한 복합 레이아웃

이런 **고밀도 정보(High-Density Data)**를 모바일(360~414px)에 그대로 표시하면:

```
┌─────────────────────────────────────────────────────────┐
│  문제 1: 텍스트 세로 줄바꿈                              │
│  → 한 행의 높이가 100px+ 로 폭발, 스크롤 끝없음         │
│                                                         │
│  문제 2: 가로 스크롤 지옥                                │
│  → 16컬럼 × min-width = 2,400px → 360px 화면의 6.7배    │
│                                                         │
│  문제 3: 상세 패널 잘림                                  │
│  → 우측 30% 고정 → 모바일에서 108px ≈ 내용 확인 불가     │
│                                                         │
│  문제 4: 터치 불가                                       │
│  → 버튼/셀렉트 높이 28~32px → 모바일 최소 44px 미달      │
└─────────────────────────────────────────────────────────┘
```

### 0.2 목표: "ERP급 정보 밀도 + 모바일 사용성" 양립

최신 ERP 모바일 트렌드(SAP Fiori, Oracle Cloud ERP, FanRuan 등)를 분석한 결과,
**"정보를 줄이는 것이 아니라, 정보의 표현 방식을 바꾸는 것"**이 핵심입니다:

| 기법 | 설명 | FOMS 적용 |
|---|---|---|
| **Progressive Disclosure** | 핵심 요약 먼저 → 탭/펼치기로 상세 | 주문 카드: 고객·상태·금액만 표시 → 누르면 상세 |
| **Bento Grid** | 관련 정보를 카드로 그룹핑 | 경보/프로세스/필터를 독립 카드로 묶기 |
| **Component Replacement** | PC 컴포넌트를 모바일 전용으로 교체 | 테이블 → 카드 리스트, 탭바 → 바텀 네비 |
| **Role-Based View** | 역할별 필요한 정보만 표시 | 담당자별 작업 큐 자동 필터 |
| **Thumb-Zone Design** | 한 손 조작 최적화, 44px+ 터치 타겟 | 하단 고정 액션바, 큰 버튼 |

### 0.3 이 계획서의 사용 방법

1. Cursor IDE에서 이 파일을 열고 GDM에게:
   > "@이 계획서 Phase 1부터 실행해 줘"
2. 각 Phase의 작업 항목에는 `⬜ 미완료 / ✅ 완료` 표시가 있습니다.
3. Phase 완료 시마다 **모바일 브라우저로 실제 확인** 후 다음 진행.

---

## 1. 대상 파일 현황 분석 (AS-IS)

### 1.1 전체 뼈대 및 핵심 페이지 (AS-IS 추가)

```
layout.html (79KB, 전체 레이아웃 뼈대)
├── @media 0개, <body>에 overflow-x: hidden 강제
└── 반응형 네비게이션 디테일 부족

index.html (41KB, 핵심 주문 목록)
├── 16개 컬럼 테이블, min-width 총합 2400px
└── 모바일 숨김/전환 로직 전혀 없음
```

### 1.2 ERP 대시보드 계층 구조

```
erp_dashboard.html (20KB, 접수 대시보드 — 진입점)
├── partials/erp_dashboard_styles.html    (44KB, 🟢 모바일 대응 양호)
├── partials/erp_dashboard_filters.html   (5KB, 🟡 필터 UI)
├── partials/erp_dashboard_grid.html      (25KB, 🟡 작업 큐 테이블)
├── partials/erp_dashboard_modals.html    (7KB, 🔴 모달 미대응)
├── partials/erp_dashboard_scripts_*.html (×7, 스크립트)
├── partials/erp_beta_tab.html            (23KB, 🔴 주문 상세 탭)
└── partials/erp_beta_js.html             (93KB, 스크립트)

erp_shipment_dashboard.html (91KB, 발송 대시보드)
├── 자체 <style> 블록                     (🟡 부분 대응, 7개 @media)
└── 모달/상세 패널                         (🔴 미대응)

erp_measurement_dashboard.html (34KB, 실측 대시보드)
├── 자체 <style> 블록                     (🟡 부분 대응, 3개 @media)
└── 상세 패널                              (🔴 미대응)

erp_drawing_workbench_dashboard.html (36KB, 도면 대시보드)
├── 자체 <style> 블록                     (🟡 부분 대응, 1개 @media)
└── erp_drawing_workbench_detail.html     (77KB, 🔴 도면 뷰어 — 별도 페이지)

erp_production_dashboard.html (5KB, 생산 대시보드)
├── partials/erp_production_styles.html   (35KB, 🟢 모바일 대응 양호)
├── partials/erp_production_filters_grid.html (15KB)
├── partials/erp_production_modals.html   (3KB)
└── partials/erp_production_scripts.html  (55KB)

erp_construction_dashboard.html (5KB, 시공 대시보드)
├── partials/erp_construction_styles.html (35KB, 🟢 모바일 대응 양호)
├── partials/erp_construction_filters_grid.html (20KB)
├── partials/erp_construction_modals.html (10KB)
└── partials/erp_construction_scripts.html (80KB)

erp_as_dashboard.html (48KB, AS/CS 대시보드)
└── 자체 <style> 블록                     (🔴 모바일 미대응)
```

### 1.2 기타 대상

```
wdcalculator/
├── calculator.html           (370B, 래퍼)
├── product_settings.html     (93KB, 🟡 table-responsive만, @media 없음)
└── partials/
    ├── wdcalculator_styles.html   (모바일 스타일?)
    └── wdcalculator_scripts.html

chat.html (13KB, 🔴 자체 모바일 미대응)
└── partials/chat_styles.html     (26KB, 🔴 @media 0개 — 모바일 대응 없음)
```

### 1.3 기존 모바일 패턴 분석 (확산 적용 가능)

**`erp_dashboard_styles.html`에 이미 구현된 양호한 패턴들:**

| 패턴 | 구현 라인 | 내용 |
|---|:---:|---|
| Grid → 1fr 전환 | 87~113 | `≤ 992px: grid-template-columns: 1fr` |
| 카드형 제품 항목 | 115~158 | `.erp-product-items-grid` 카드 그리드 |
| 상세 패널 풀스크린 | 763+ | `≤ 992px: table-responsive overflow visible` |
| 경보/프로세스 축소 | 774~800 | 폰트/패딩 축소 |
| 제품 항목 카드 전환 | 1084~1145 | `display: block, td::before { content: attr(data-label) }` |

이 패턴들을 **미대응 페이지에 그대로 확산 적용**합니다.

---

## 2. 구현 계획 상세

---

### Phase 1: 전체 레이아웃 (layout.html) 및 모바일 기반 강화 ✅

> **목표**: 기초 뼈대인 layout.html의 뷰포트/네비게이션/헤더 버그 수정 및 erp-pro.css 모바일 규칙 추가

#### 작업 1-0: `templates/layout.html` 모바일 최적화 ✅

- **수정 파일**: `templates/layout.html`
- **목적**: 모바일에서 가로 스크롤을 막는 전역 `<body>` 속성 수정 및 헤더/네비바 개선
- **상세**:
  1. `<body>` 인라인 스타일에서 `overflow-x: hidden` 제거 (가로 스크롤 허용 또는 `.table-responsive` 내에서만 허용되도록 일관성 확보)
  2. 네비게이션 바(`.navbar-collapse`) 내부에 여백(padding) 조정 (모바일에서 메뉴 항목 터치 타겟 44px)
  3. **[추가] 헤더 영역 반응형**: `<header>` 내 제목 `h1.h3` + 알림/유저 드롭다운이 모바일에서 넘치지 않도록 축소
     - h1 타이틀: 모바일에서 `font-size: 1rem` 또는 숨김
     - 알림 패널: `width: 420px` → `max-width: min(420px, calc(100vw - 24px))` (이미 인라인에 일부 있지만 재확인)
  4. **[추가] `navbar-expand-lg` → `navbar-expand-md` 검토**: 현재 lg(992px) 전환인데, 태블릿에서 메뉴가 넘칠 수 있음

#### 작업 1-1: `static/css/erp-pro.css` 모바일 핵심 규칙 추가 ✅

- **수정 파일**: `static/css/erp-pro.css`
- **목적**: 모든 ERP 페이지에 공통 적용되는 모바일 기반 규칙
- **상세**: 파일 끝에 아래 섹션 추가

```css
/* ============================================================
   MOBILE ERP OPTIMIZATION (2026-03 추가)
   최신 ERP 트렌드: Progressive Disclosure + Bento Grid
   ============================================================ */

/* --- Breakpoint 체계 ---
   ≤ 576px : 스마트폰 세로 (xs)
   ≤ 768px : 스마트폰 가로 & 소형 태블릿 (sm)
   ≤ 992px : 태블릿 세로 (md) — 주요 전환점
   ≤ 1200px: 태블릿 가로 (lg)
*/

/* 1. 터치 타겟 보장: 44px 최소 높이 */
@media (max-width: 992px) {
  .erp-pro .form-control,
  .erp-pro .form-select,
  .erp-pro .btn {
    min-height: 44px;
    font-size: 1rem;
  }

  /* 모달: 모바일 풀스크린 */
  .modal-dialog {
    max-width: 100vw !important;
    margin: 0 !important;
    min-height: 100vh;
  }
  .modal-content {
    border-radius: 0 !important;
    min-height: 100vh;
  }

  /* 상세 패널: 모바일 풀오버레이 */
  .erp-detail-panel {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    max-height: 100vh !important;
    z-index: 1050 !important;
    background: #fff !important;
    overflow-y: auto !important;
    padding: 1rem !important;
  }
}

/* 2. 테이블 → 카드 전환 공통 패턴 */
@media (max-width: 992px) {
  .erp-mobile-card-table thead { display: none; }
  .erp-mobile-card-table tbody tr {
    display: block;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    margin-bottom: 0.75rem;
    padding: 0.75rem;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
  }
  .erp-mobile-card-table tbody td {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0;
    border: none;
    border-bottom: 1px solid #f5f5f5;
    font-size: 0.95rem;
  }
  .erp-mobile-card-table tbody td:last-child {
    border-bottom: none;
  }
  .erp-mobile-card-table tbody td::before {
    content: attr(data-label);
    font-weight: 600;
    color: #6c757d;
    flex: 0 0 auto;
    margin-right: 8px;
    font-size: 0.85rem;
  }
}

/* 3. 스마트폰 세로 추가 최적화 */
@media (max-width: 576px) {
  .erp-pro .form-control,
  .erp-pro .form-select {
    font-size: 16px !important; /* iOS 줌 방지 */
  }
  .erp-alert-col {
    flex: 0 0 50% !important;
    max-width: 50% !important;
  }
  .erp-process-col {
    min-width: 72px;
  }
}
```

- **핵심 설계**:
  1. **터치 타겟 44px**: Apple HIG + Google Material Design 표준
  2. **모달 풀스크린**: SAP Fiori Mobile 패턴 (작은 화면에서 모달 = 새 화면)
  3. **테이블 → 카드 공통 클래스**: `erp-mobile-card-table` 클래스만 추가하면 자동 전환
  4. **iOS 줌 방지**: `font-size: 16px` (16px 미만이면 iOS가 자동 줌)

---

#### 작업 1-2: `style-pro-max.css` 모바일 섹션 추가 ✅

- **수정 파일**: `static/css/style-pro-max.css`
- **목적**: 프리미엄 디자인 시스템에 모바일 타이포/스페이싱 추가
- **상세**: 파일 끝에 추가

```css
/* MOBILE RESPONSIVE (2026-03) */
@media (max-width: 992px) {
  :root {
    --space-5: 16px;
    --space-6: 24px;
  }
  .container-premium { padding: var(--space-3); }
  .grid-dashboard {
    grid-template-columns: 1fr;
    gap: var(--space-3);
  }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.2rem; }
  h3 { font-size: 1.1rem; }
}

@media (max-width: 576px) {
  :root {
    --space-5: 12px;
  }
  .grid-dashboard { gap: var(--space-2); }
  h1 { font-size: 1.25rem; }
}
```

---

### Phase 2: ERP 접수 대시보드 (erp_dashboard) 정밀 최적화 (진행 중)

> **목표**: 가장 많이 사용되는 접수 대시보드와 메인 주문 목록(index.html) 최적화

#### 작업 2-0: `templates/index.html` 주문 목록 모바일 최적화 ✅

- **수정 파일**: `templates/index.html`
- **변경 사항**: 2400px 폭의 16컬럼 테이블에 Progressive Disclosure 패턴 적용
- **상세**:
  1. PC에서 불필요한 인라인 `min-width` 속성(200px~280px)을 CSS 클래스로 분리
  2. 모바일(≤ 992px)에서 테이블을 `erp-mobile-card-table`로 전환하여 카드형 UI로 표시
  3. 카드뷰에서 고객, 연락처, 기한, 제품만 표시하고 나머지는 숨김(또는 펼치기)
  4. 상단 컨트롤 패널(검색, 엑셀 다운, 새 주문) 터치 타겟 44px 및 모바일 스택 정렬

#### 작업 2-1: 작업 큐 테이블 `data-label` 검증 ✅ (이미 완료)

- **파일**: `templates/partials/erp_dashboard_grid.html`
- **검증 결과**: ✅ 13개 컬럼 모두 `data-label` 이미 부여됨
  - L56: `data-label="경보"`, L83: `data-label="단계"`, L85: `data-label="퀘스트"`
  - L291: `data-label="고객"`, L293: `data-label="연락처"`, L294: `data-label="주소"`
  - L296: `data-label="제품"`, L307: `data-label="실측일"`, L309: `data-label="시공일"`
  - L311: `data-label="담당"`, L312: `data-label="첨부"`, L323: `data-label="상세"`, L335: `data-label="열기"`
- **추가 확인 필요**: JS에서 동적 생성(Ajax)되는 행에도 `data-label`이 붙는지 스크립트 확인

---

#### 작업 2-2: `erp_dashboard_styles.html` 기존 카드 전환 CSS 미세 보정 ⬜

- **수정 파일**: `templates/partials/erp_dashboard_styles.html`
- **현황**: ⚠️ **카드 전환 CSS는 이미 800줄 이상 구현되어 있음** (L815~1620)
  - `erp-main-row` 기반 카드 레이아웃, `data-label` 활용 `::before` 라벨, 576px 추가 축소 구현 완료
- **변경 사항 (미세 보정만)**:
  1. 576px 이하에서 폰트 `0.78rem`(약 12.5px)이 너무 작지 않은지 확인 → 13~14px로 상향 검토
  2. `.erp-dashboard .btn` 터치 타겟이 44px 이하인 항목 보정 (현재 L855~858에서 `font-size: 0.78rem` 강제)
  3. 동적 Ajax 로딩 시 `erp-main-row` 클래스와 `data-label`이 정상 부여되는지 JS 확인
  4. 기존 `display: none` 처리가 없는 컬럼 중 모바일에서 불필요한 것 추가 숨기기 검토

- **⚠️ 금지 사항**: 기존 CSS를 덮어쓰는 새 규칙 추가 금지. 반드시 기존 코드를 수정하는 방식으로.

---

#### 작업 2-3: 필터 패널 모바일 아코디언화 ✅

- **수정 파일**: `templates/partials/erp_dashboard_filters.html`
- **변경 사항**: 모바일에서 필터를 접히는 아코디언으로 전환
- **상세**: 
  - 992px 이하: 필터 카드를 `collapse`로 감싸고 토글 버튼 추가
  - 기본 접힘 → "필터" 라벨 탭하면 펼쳐짐

---

#### 작업 2-4: 모달 모바일 풀스크린 적용 ✅

- **수정 파일**: `templates/partials/erp_dashboard_modals.html`
- **변경 사항**: 4개 모달에 `.modal-fullscreen-md-down` Bootstrap 클래스 추가
- **상세**: Bootstrap 5.3의 내장 반응형 모달 활용

실제 모달 현황 (수정 대상):
```html
<!-- 1. 첨부파일 모달 (L3) -->
<div class="modal-dialog modal-dialog-centered modal-xl">
→ <div class="modal-dialog modal-dialog-centered modal-xl modal-fullscreen-md-down">

<!-- 2. 도면 담당자 지정 (L26) -->
<div class="modal-dialog modal-dialog-centered">
→ <div class="modal-dialog modal-dialog-centered modal-fullscreen-md-down">

<!-- 3. 도면 수정 요청 (L48) -->
<div class="modal-dialog modal-dialog-centered">
→ <div class="modal-dialog modal-dialog-centered modal-fullscreen-md-down">

<!-- 4. 도면 전달 (L89) -->
<div class="modal-dialog modal-dialog-centered">
→ <div class="modal-dialog modal-dialog-centered modal-fullscreen-md-down">
```

---

#### 작업 2-5: ERP 서브 네비게이션 모바일 최적화 ✅ (누락 보강)

- **수정 파일**: `templates/partials/erp_sub_nav.html` + `static/css/erp-pro.css`
- **현황**: `.erp-pro-nav`에 `overflow-x: auto` 있으나, 7개 탭이 모바일에서 가려짐
- **변경 사항**:
  1. 모바일에서 스와이프 힌트 추가 (우측 그래디언트 fade)
  2. `.erp-pro-nav-item` 터치 타겟 44px 확보
  3. 활성 탭에 시각적 강조 (현재 있으나 모바일에서 잘 안 보일 수 있음)

#### 작업 2-6: `erp_beta_tab.html` 주문 상세 탭 모바일 ✅ (누락 보강)

- **수정 파일**: `templates/partials/erp_beta_tab.html` (23KB)
- **현황**: 주문 상세 정보를 탭으로 표시. 모바일 대응 없음
- **변경 사항**:
  1. 탭 헤더: 수평 스크롤 (`.nav-tabs` → `overflow-x: auto; flex-wrap: nowrap`)
  2. 상세 정보 그리드: 모바일에서 1열 스택
  3. 폼 입력 필드 터치 타겟 44px

---

### Phase 3: ERP 서브 대시보드 확산 적용 ⬜

> **목표**: Phase 2에서 확립한 패턴을 발송, 실측, 도면, 생산, 시공, AS에 확산

#### 작업 3-1: 발송 대시보드 (`erp_shipment_dashboard.html`) ✅

- **수정 파일**: `templates/erp_shipment_dashboard.html`
- **변경 사항**:
  1. 발송 목록 테이블 `<td>`에 `data-label` 속성 추가
  2. 발송 카드 전환 CSS 추가 (자체 `<style>` 블록의 `@media ≤ 992px`)
  3. 이미지 내보내기 모달에 `.modal-fullscreen-md-down` 추가
  4. 상세 탭(발송 정보, 제품, 결제) 모바일 수직 스택

핵심 개선 포인트:
- 현재 가로 2분할 레이아웃 → 모바일에서 수직 스택
- 발송 그룹 카드: PC는 그리드 → 모바일은 세로 리스트

---

#### 작업 3-2: 실측 대시보드 (`erp_measurement_dashboard.html`) ✅

- **수정 파일**: `templates/erp_measurement_dashboard.html`
- **변경 사항**:
  1. 실측 목록 `<td>`에 `data-label` 추가
  2. 실측 카드 전환 CSS
  3. 캘린더 뷰: 모바일에서 리스트 뷰 기본 전환
  4. 담당자 지정 모달 풀스크린

---

#### 작업 3-3: 도면 대시보드 (`erp_drawing_workbench_dashboard.html`) ✅

- **수정 파일**: `templates/erp_drawing_workbench_dashboard.html`
- **변경 사항**:
  1. 도면 목록 카드 전환
  2. 도면 상세(`erp_drawing_workbench_detail.html`) 모바일 레이아웃
     - 도면 뷰어: 가로 스크롤 허용 + 핀치 줌
     - 제품 정보: 수직 스택
     - 첨부파일 그리드: 2열 → 1열

---

#### 작업 3-4: 생산/시공 대시보드 (이미 양호 — 미세 조정) ✅

- **대상**: `erp_production_styles.html`, `erp_construction_styles.html`
- **변경**: 이미 카드 전환이 있으므로 미세 조정만
  1. 터치 타겟 44px 확인 및 보정
  2. 모달 `.modal-fullscreen-md-down` 추가
  3. 576px 이하 추가 최적화 (아직 없는 경우)

---

#### 작업 3-5: AS 대시보드 (`erp_as_dashboard.html`) ✅

- **수정 파일**: `templates/erp_as_dashboard.html`
- **변경 사항**:
  1. 48KB 파일 내 `<style>` 블록에 `@media` 추가
  2. AS 접수/처리 테이블 카드 전환
  3. 모달 풀스크린
  4. 사진 첨부 그리드 모바일 대응

---

### Phase 4: WDCalculator + 채팅 최적화 ✅

> **목표**: 특수 UI (계산기, 채팅)의 모바일 최적화

#### 작업 4-1: WDCalculator 모바일 최적화 ✅

- **대상 파일**: 
  - `templates/wdcalculator/product_settings.html` (93KB)
  - `templates/wdcalculator/partials/wdcalculator_styles.html`

- **현황**: 
  - `table-responsive` 사용 중이나 `@media` 없음
  - 설정 테이블(카테고리, 제품, 옵션)이 PC 가로 고정

- **변경 사항**:
  1. 설정 테이블 카드 전환 (카테고리 목록, 제품 목록, 옵션 목록)
  2. 모달(제품 추가, 옵션 편집) 풀스크린
  3. 가격 입력 필드 터치 최적화 (숫자 키보드 자동 표시)
  4. 탭 네비게이션 → 모바일 수평 스크롤 탭

가격 입력 최적화:
```html
<!-- 현재 -->
<input type="text" class="form-control" value="50000">

<!-- 변경: 모바일 숫자 키패드 자동 표시 -->
<input type="text" inputmode="numeric" pattern="[0-9]*" class="form-control" value="50000">
```

---

#### 작업 4-2: 채팅 모바일 최적화 ✅

- **대상 파일**: 
  - `templates/chat.html` (13KB)
  - `templates/partials/chat_styles.html` (26KB)

- **현황**: 
  - ⚠️ `chat_styles.html`에 `@media` **0개** (이전 계획서에서 🟢으로 오판됨)
  - `chat.html` 자체에도 @media 없음
  - **두 파일 모두 모바일 대응이 전혀 없으므로 작업량 상향 필요**

- **변경 사항**:
  1. 채팅방 목록 / 메시지 영역: 모바일에서 전환형 (목록 → 메시지) 
     - 현재: 좌측 목록 + 우측 메시지 동시 표시
     - 변경: 🔀 목록 모드 ↔ 메시지 모드 토글 (WhatsApp 패턴)
  2. 파일 업로드 모달 풀스크린
  3. 메시지 입력영역 하단 고정 (position: sticky bottom)
  4. 이미지/파일 미리보기 터치 최적화
  5. **[추가] chat_styles.html에 @media 규칙 신규 작성** (모바일 레이아웃 처음부터 구현)

---

### Phase 5: 검증 및 마무리 ✅

#### 작업 5-1: 크로스 디바이스 테스트 ✅

| 디바이스 | 뷰포트 | 테스트 항목 |
|---|:---:|---|
| iPhone SE | 375×667 | 최소 뷰포트 기준, 카드 전환 확인 |
| iPhone 14 Pro | 393×852 | 표준 스마트폰 세로 |
| Galaxy S24 | 360×780 | Android 표준 |
| iPad Mini | 768×1024 | 태블릿 세로 — 전환 경계점 |
| iPad Air | 820×1180 | 태블릿 — 하이브리드 뷰 |

테스트 방법: Chrome DevTools → Device Toolbar 사용

#### 작업 5-2: git commit + push ✅

- 커밋 메시지: `feat: 모바일 ERP 최적화 — 카드 전환, 풀스크린 모달, Progressive Disclosure`
- deploy 브랜치에 push

---

## 3. 완료 검증 체크리스트

### Phase 1 (공통 기반)
- [ ] `layout.html`의 `<body>` 폭풍 수정 (overflow-x 이슈) 확인
- [ ] `erp-pro.css`에 `@media (max-width: 992px)` 섹션 존재
- [ ] 터치 타겟 44px 규칙 적용 확인
- [ ] 모달 풀스크린 공통 규칙 적용 확인
- [ ] `style-pro-max.css`에 모바일 타이포 존재

### Phase 2 (주문 목록 & 접수 대시보드)
- [ ] `index.html` 모바일 접속 시 카드형 주문 목록으로 변환 확인
- [ ] `#erp-grid` 모든 `<td>`에 `data-label` 존재
- [ ] 992px 이하에서 테이블 → 카드 전환 확인
- [ ] 576px 이하에서 컬럼 숨기기 동작 확인
- [ ] 필터 패널 모바일 아코디언 동작 확인
- [ ] 모달 풀스크린 동작 확인

### Phase 3 (서브 대시보드)
- [ ] 발송 대시보드 모바일 카드 확인
- [ ] 실측 대시보드 모바일 카드 확인
- [ ] 도면 대시보드 모바일 카드 확인
- [ ] 생산/시공 기존 모바일 패턴 미세 조정 확인
- [ ] AS 대시보드 모바일 카드 확인

### Phase 4 (WDCalculator + 채팅)
- [ ] WDCalculator 설정 테이블 모바일 카드 확인
- [ ] WDCalculator 숫자 입력 키보드 확인
- [ ] 채팅 목록/메시지 전환 모드 동작 확인
- [ ] 채팅 입력 영역 하단 고정 확인

### Phase 5 (검증)
- [ ] iPhone SE (375px) 테스트 통과
- [ ] iPad Mini (768px) 테스트 통과
- [ ] git commit + push 완료

---

## 4. 위험 분석 및 대응

| # | 위험 | 영향도 | 확률 | 대응 방안 |
|:---:|---|:---:|:---:|---|
| R1 | 카드 전환 시 `data-label` 누락 → 라벨 빈칸 | 중 | 높 | Jinja2 for 루프에서 td 생성 시 자동 추가되도록 패턴화 |
| R2 | 모바일 숨김 컬럼에 중요 정보 포함 → 사용자 불만 | 높 | 중 | 숨김 컬럼은 카드 탭 시 상세에서 반드시 확인 가능하게 |
| R3 | iOS input 자동 줌 | 중 | 높 | font-size: 16px 강제 (이미 Phase 1에 포함) |
| R4 | 기존 PC 레이아웃 깨짐 | 높 | 낮 | 모든 CSS는 `@media (max-width)` 내에서만 적용 — PC 영향 없음 |
| R5 | 발송 대시보드(91KB) 수정 범위 과다 | 중 | 중 | 자체 style 블록 수정으로 최소 침투. 기존 로직 변경 없음 |
| R6 | 채팅 WhatsApp 패턴 전환 시 JS 개발 필요 | 중 | 높 | CSS `display:none` + show/hide 토글로 최소 JS 구현 |

---

## 5. 적용할 최신 트렌드 요약

| 트렌드 | 출처 | FOMS 적용 방식 |
|---|---|---|
| **Progressive Disclosure** | SAP Fiori, FanRuan | 카드 리스트에서 핵심 3~4개만 표시, 탭 시 상세 |
| **Bento Grid** | Apple Design, Wishket 2025 | 경보 2×2, 프로세스 가로 스크롤, 필터 아코디언 |
| **Component Replacement** | SAP, Oracle | 테이블 → 카드, 탭바 → 바텀 네비, 사이드바 → 오버레이 |
| **Touch-First (44px)** | Apple HIG, Material Design | 모든 버튼/입력 최소 44px |
| **Minimalist Data Viz** | FanRuan, DataSense | 핵심 KPI만 상단, 나머지 접기 |
| **Dark Mode Ready** | UITop 2025 | CSS 변수 활용 (이미 `style-pro-max.css`에 기반 있음) |

---

## 6. 실행 지시

```
Phase 1 (공통 기반):     작업 1-0 → 1-1 → 1-2
Phase 2 (접수 대시보드):  작업 2-0 → 2-1(검증) → 2-2(미세보정) → 2-3 → 2-4 → 2-5 → 2-6
Phase 3 (서브 대시보드):  작업 3-1 → 3-2 → 3-3 → 3-4 → 3-5
Phase 4 (WDCalc + 채팅): 작업 4-1 → 4-2(채팅은 처음부터 구현)
Phase 5 (검증/배포):     작업 5-1 → 5-2
```

> **예상 소요**: Phase별 30분~1.5시간, 총 5~7시간
> **수정 파일**: 약 18개
> **PC 영향**: 없음 (모든 변경은 `@media (max-width)` 내)
> **⚠️ 주의**: 작업 2-1, 2-2는 기존 구현이 있으므로 절대 덮어쓰기 금지, 미세 보정만 수행
