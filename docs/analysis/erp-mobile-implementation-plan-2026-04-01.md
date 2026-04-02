# FOMS ERP Mobile V2 실행 계획

- 작성일: 2026-04-01
- 개정일: 2026-04-02
- 상태: 감리 반영본 v4
- 근거 문서: `docs/analysis/erp-mobile-ux-research-2026-04-01.md`

## 0. 이 문서의 목적

이 문서는 FOMS ERP의 모바일 전용 UX를 "실제로 구현 가능한 수준"으로 정리한 실행 계획서다.

이전 버전에서 나온 문제를 반영해 아래 4가지를 바로잡았다.

1. 공통 래퍼를 잘못 가정한 설계를 제거했다.
2. 모든 화면을 하나의 카드 컴포넌트로 통일하려는 과한 추상화를 제거했다.
3. 브라우저가 지원하지 않는 CSS 전제를 제거했다.
4. 광역 `git checkout` 기반 롤백을 없애고, feature flag + phase 단위 롤백으로 바꿨다.

### 0.1 스타일 기준선

이번 버전부터 FOMS 모바일 ERP의 시각 기준선은 "최신 ERP 스타일"로 명확히 고정한다.

- 1차 주 레퍼런스: SAP Fiori with Morning Horizon
- 2차 보조 레퍼런스: Oracle Redwood
- 3차 보조 레퍼런스: Microsoft Fluent 2

적용 원칙:

- 시각 언어는 SAP Fiori Morning Horizon을 기본으로 한다.
- 화면 밀도와 작업 중심 구조는 Oracle Redwood의 단순화 방향을 보조로 반영한다.
- 토큰 구조와 시스템화 방식은 Fluent 2를 참고한다.

즉, 이번 계획은 "ERP처럼 보이는 범용 모바일 UI"가 아니라, "실제 최신 ERP 디자인 시스템에 가까운 모바일 셸"을 목표로 한다.

### 0.2 이번 계획에서 말하는 "실제 최신 ERP 스타일"

FOMS Mobile V2의 기본 비주얼은 아래처럼 정의한다.

1. 배경은 흰색 일색이 아니라, 아주 옅은 중성 회색 app background 위에 흰 surface card가 올라가는 구조
2. 주 액센트는 SAP Horizon 계열의 선명한 블루
3. 카드와 컨트롤은 둥근 모서리와 얕은 그림자로 계층을 만든다
4. 헤더와 필터, 카드, 드로어가 한 계층 안에서 조용하고 정제된 톤을 유지한다
5. semantic 상태는 강한 원색 border보다 "연한 배경 + 진한 텍스트" 중심으로 표현한다
6. 아이콘은 line-based에 가깝고, 버튼은 Bootstrap 기본색 느낌보다 더 정제된 엔터프라이즈 톤을 사용한다

### 0.3 이번 계획에서 하지 않을 스타일

아래는 "최신 ERP 스타일"과 거리가 있으므로 금지한다.

- Bootstrap 기본 `btn-primary` 블루를 그대로 노출하는 구성
- 카드마다 강한 drop shadow를 쓰는 SaaS 마케팅형 비주얼
- 보라 계열 위주의 임의 accent
- glassmorphism, neon glow, 과한 gradient
- 카드마다 서로 다른 radius와 border 톤
- 상태 badge를 원색 배경으로만 과다 사용

### 0.4 레퍼런스 우선순위

이번 계획은 "여러 레퍼런스를 섞어 평균적인 UI를 만드는 방식"으로 가지 않는다.

우선순위는 아래처럼 고정한다.

1. 시각 언어: SAP Fiori with Morning Horizon
2. 모바일 페이지 구조: SAP Fiori Dynamic Page / Responsive Table / Object Page
3. 현장 작업 단순화: Oracle Redwood의 간결한 작업 큐, compact header, action grouping
4. 토큰 naming / radius / elevation discipline: Microsoft Fluent 2

충돌 시 우선순위:

- SAP 시각 언어가 항상 우선이다.
- Oracle Redwood는 정보 밀도와 작업 묶음 방식만 보조로 반영한다.
- Fluent 2는 설계 토큰 체계와 접근성 규칙만 참고한다.

즉, FOMS Mobile V2는 "하이브리드 비주얼"이 아니라 "SAP Fiori Morning Horizon 기반 ERP"로 설계한다.

### 0.5 공식 기준 출처

2026-04-02 기준, 아래 공식 문서를 최신 스타일 기준선으로 본다.

- SAP Fiori with Horizon: https://www.sap.com/design-system/fiori-design-web/v1-136/discover/sap-design-system/sap-fiori
- Morning Horizon Colors: https://www.sap.com/design-system/fiori-design-web/v1-136/foundations/visual/colors/morning-horizon
- Typography - Horizon: https://www.sap.com/design-system/fiori-design-web/v1-145/foundations/visual/typography/typography-horizon
- Dynamic Page: https://experience.sap.com/fiori-design-web/dynamic-page-layout/
- Responsive Table: https://experience.sap.com/fiori-design-web/responsive-table/
- Object Page Floorplan: https://experience.sap.com/fiori-design-web/object-page/
- SAP Fiori Android Object Card: https://experience.sap.com/fiori-design-android/object-card/
- Oracle Redwood adoption: https://docs.oracle.com/en/cloud/saas/readiness/redwood-adoption/index.html
- Oracle Redwood theme example: https://docs.oracle.com/en/cloud/saas/field-service/faaca/c-redwoodtheme.html
- Fluent 2 color: https://fluent2.microsoft.design/color
- Fluent 2 typography: https://fluent2.microsoft.design/typography
- Fluent 2 design tokens: https://fluent2.microsoft.design/design-tokens

## 1. 반드시 지켜야 할 원칙

### 1.1 데스크톱 UX는 건드리지 않는다

- 모바일 개선은 `@media (max-width: 991.98px)` 범위 안에서만 적용한다.
- 992px 이상에서는 현재 UI를 그대로 유지한다.
- 기존 `/erp/*` URL 체계는 유지한다.
- 이번 계획에서는 `/m/erp` 같은 별도 라우트 분기는 만들지 않는다.

### 1.2 공통 인프라는 "공통", 화면 로직은 "화면별"로 나눈다

- 공통으로 만들 것
  - 모바일 shell header
  - 모바일 하단 탭
  - 모바일 더보기 드로어
  - 모바일 간격/타이포 토큰
  - 공통 액션 행 스타일
  - 공통 요약 카드 스타일
- 화면별로 유지할 것
  - 실측 편집 구조
  - AS 편집 구조
  - 도면 작업대시 상호작용
  - 출고의 테이블 카드화 패턴

즉, "모든 화면을 하나의 `erp-task-card`로 통일"하지 않는다.

### 1.3 모바일 최소 가독성은 코드 감사로 보장한다

이번 계획에서는 `min-font-size` 같은 비표준 속성을 사용하지 않는다.

대신 아래 방식으로 관리한다.

1. CSS 변수 정의
2. 신규 코드에서 변수만 사용
3. phase별로 하드코딩된 작은 폰트를 치환
4. `rg` 기반 감리로 12px 미만 값이 남지 않았는지 확인

### 1.4 롤백은 feature flag 우선이다

- 1차 롤백 수단은 코드 삭제가 아니라 `ERP_MOBILE_V2_ENABLED=false`다.
- phase별 HTML/CSS는 주석 경계를 두고, 해당 블록만 제거 가능하게 작성한다.
- `templates/` 전체를 되돌리는 식의 광역 롤백은 금지한다.

## 2. 현재 코드베이스 기준 현실 제약

### 2.1 공통 ERP 화면 구조

현재 주요 ERP 화면은 모두 `layout.html`을 상속하고, 각 화면마다 루트 `.erp-pro` 컨테이너를 직접 가진다.

대표 예시:

- `templates/erp_dashboard.html`
- `templates/erp_measurement_dashboard.html`
- `templates/erp_shipment_dashboard.html`

중요한 점:

- `.erp-pro-content`는 CSS에는 정의돼 있지만, 실제 주요 ERP 템플릿의 공통 루트로 사용되지 않는다.
- 따라서 모바일 하단 탭 여백은 `.erp-pro-content`가 아니라 각 화면의 실제 루트 `.erp-pro`에 걸어야 한다.

### 2.2 현재 화면군 분류

실행 계획은 화면을 아래 5개 family로 나눠야 안전하다.

| Family | 화면 | 현재 상태 | 실행 전략 |
|---|---|---|---|
| Queue Family | 대시보드, 생산, 시공 | 넓은 작업 큐 테이블 | 공통 모바일 큐 카드 도입 |
| Editable Schedule Family | 실측, AS | 카드 안에 편집 요소가 많음 | 화면별 모바일 카드 유지/재설계 |
| Specialized Card Family | 도면 작업대시 | 이미 모바일 카드 존재 | 구조 유지, 밀도와 액션만 개선 |
| CSS Cardified Table Family | 출고 | 테이블 기반 모바일 카드화 | 현재 패턴 유지, 액션/필터만 개선 |
| Gallery / Archive Family | 시공완료, 이력 | 비교적 모바일 친화 | 메뉴/타이포/간격 정리 중심 |

이 분류를 무시하고 한 번에 통일하면 회귀 위험이 커진다.

## 3. 목표 IA

### 3.1 모바일 ERP의 기본 진입 철학

모바일 ERP는 "작은 데스크톱"이 아니라 "오늘 처리할 작업 큐"여야 한다.

목표 흐름:

1. 오늘 할 일 확인
2. 내 작업/긴급 건 확인
3. 카드에서 빠른 액션 실행
4. 필요 시 상세 진입

즉, 모바일의 중심은 "전체 컬럼 열람"이 아니라 "업무 처리"다.

### 3.2 모바일 IA 구조

```text
[모바일 ERP]

  홈 = /erp/dashboard
    - 내 작업 요약
    - 긴급 건
    - 오늘 실측 / 오늘 시공
    - 최근 작업
    - 작업 큐 카드

  실측 = /erp/measurement
    - 날짜별 일정
    - 경로/지도
    - 실측 카드

  시공 = /erp/construction/dashboard
    - 오늘/예정 작업
    - 시공 카드

  출고 = /erp/shipment
    - 날짜 기준 출고
    - 카드화 테이블

  더보기
    - 생산
    - 도면 작업대시
    - AS
    - 시공완료
    - 이력
```

### 3.3 역할별 기본 접근

하단 탭은 5칸 고정으로 두되, 2~4번째 탭은 역할별로 바꾼다.

| 역할 | 탭 1 | 탭 2 | 탭 3 | 탭 4 | 탭 5 |
|---|---|---|---|---|---|
| 관리자/영업 | 홈 | 실측 | 시공 | 출고 | 더보기 |
| 도면팀 | 홈 | 도면 | 생산 | 출고 | 더보기 |
| 생산팀 | 홈 | 생산 | 출고 | 시공 | 더보기 |
| 시공팀 | 홈 | 출고 | 시공 | 완료 | 더보기 |

주의:

- 하단 탭에는 5개 이상 넣지 않는다.
- 모든 메뉴 접근은 "더보기" 드로어에서 보장한다.

## 4. 메뉴 구조

### 4.1 모바일 공통 내비게이션

모바일에서는 기존 상단 가로 스크롤 ERP 탭을 숨기고, 아래 3단 구조를 추가한다.

1. 상단 모바일 shell header
2. 하단 고정 workspace tab
3. 더보기 Offcanvas

이 구조는 SAP Fiori의 shell bar + page header 철학을 FOMS 업무 구조에 맞게 단순화한 버전이다.

중요:

- Fiori 원형을 그대로 복제하지는 않는다.
- 대신 "상단에 현재 컨텍스트를 명확히 보여주고, 본문은 작업 큐와 오브젝트 카드, 주요 액션은 손이 닿는 위치에 둔다"는 최신 ERP 원칙을 따른다.

즉, FOMS에서는

- 위쪽: shell header로 현재 화면 컨텍스트 유지
- 아래쪽: 현장 사용성 때문에 workspace tab 제공
- 추가 메뉴: 더보기 드로어에 집약

이 구현은 `erp_sub_nav.html`을 직접 뜯는 방식이 아니라, 각 ERP 화면 상하단에 모바일 전용 partial을 include하는 방식으로 한다.

이유:

- 기존 데스크톱 탭을 안전하게 유지할 수 있다.
- construction 팀 전용 메뉴 분기와 충돌이 적다.
- 공통 partial은 유지하되, 모바일만 새로운 셸을 얹을 수 있다.
- 실제 최신 ERP 스타일의 "상단 컨텍스트 + 작업 중심 본문"을 구현할 수 있다.

### 4.2 추가할 공통 partial

- `templates/partials/erp_mobile_shell_header.html`
- `templates/partials/erp_mobile_bottom_nav.html`
- `templates/partials/erp_mobile_menu_drawer.html`

필요 시 2차 이후:

- `templates/partials/erp_mobile_filter_bar.html`

이번 실행 계획에서는 detail sheet를 공통 infra로 먼저 만들지 않는다.

이유:

- Queue Family에는 유용하지만,
- 실측/AS처럼 편집이 많은 화면에는 공통 detail sheet가 오히려 방해가 된다.

## 5. 와이어프레임

### 5.1 홈 / 대시보드

```text
┌──────────────────────────────┐
│ ← ERP 홈           검색   ⋯  │
│ 오늘 작업 12   긴급 3        │
│ 오늘 실측 4    오늘 시공 2   │
├──────────────────────────────┤
│ [오늘] [긴급] [내 작업]      │
├──────────────────────────────┤
│ 검색...            [필터]    │
├──────────────────────────────┤
│ [긴급] 실측                  │
│ 홍길동 · 04/03 14:00         │
│ 서울 강남구 ...              │
│ 담당: 김실측                 │
│ [열기] [전화] [⋯]            │
├──────────────────────────────┤
│ [일반] 시공                  │
│ 이영희 · 04/03 16:00         │
│ 경기 하남시 ...              │
│ 담당: 박시공                 │
│ [열기] [지도] [⋯]            │
└──────────────────────────────┘

하단 탭: [홈] [실측] [시공] [출고] [더보기]
```

### 5.2 실측

```text
┌──────────────────────────────┐
│ ← 실측             검색  지도 │
│ 2026-04-03 금요일             │
│ 오늘 4건 / 이동 2건           │
├──────────────────────────────┤
│ [오늘] [담당자] [지역] [필터] │
├──────────────────────────────┤
│ 04/03 금요일                 │
│ ┌──────────────────────────┐ │
│ │ 홍길동 / 14:00           │ │
│ │ 서울 강남구 ...          │ │
│ │ 제품: 붙박이장 1식       │ │
│ │ 담당: 김실측             │ │
│ │ [열기] [지도] [⋯]        │ │
│ └──────────────────────────┘ │
└──────────────────────────────┘
```

원칙:

- 실측은 모바일에서 "일정 카드"가 중심이다.
- 편집은 카드 안 최소 조작 + 상세 이동으로 나눈다.
- 카드 1개당 직접 노출 액션은 최대 2개로 제한하고, 나머지는 overflow에 넣는다.

### 5.3 AS

```text
┌──────────────────────────────┐
│ ← AS               검색   ⋯  │
│ [진행중] [오늘] [담당자]     │
├──────────────────────────────┤
│ #1042      진행중            │
│ 고객: 홍길동 / 010-...       │
│ 방문일: [2026-04-04]         │
│ 완료일: [      ]             │
│ 주소: 서울 강남구 ... [일정] │
│ 사진: [보기]   도면: [체크]  │
│ 내용:                        │
│ [기존 리치 에디터 유지]      │
│ [저장] [전화] [⋯]            │
└──────────────────────────────┘
```

원칙:

- AS는 현재 모바일 카드가 이미 존재하므로, 구조를 뒤엎지 않는다.
- 먼저 타이포/간격/액션 배치만 정리한다.

### 5.4 더보기 드로어

```text
┌──────────────────────────────┐
│ ERP 메뉴                 [X] │
│ 작업 공간 / 보조 메뉴        │
├──────────────────────────────┤
│ [대시보드] [실측] [도면]     │
│ [생산]   [출고] [AS]         │
│ [시공]   [완료] [이력]       │
└──────────────────────────────┘
```

### 5.5 실제 최신 ERP 비주얼 키트

모바일 화면은 아래 규칙을 만족해야 "실제 최신 ERP 스타일"에 가깝다.

1. 헤더는 흰색 surface 위에 얇은 divider만 두고, 과한 그림자나 컬러 바를 쓰지 않는다.
2. KPI 요약은 2x2 혹은 가로 스크롤 pill이 아니라, 낮은 높이의 quiet card로 정리한다.
3. 리스트 항목은 "마케팅 카드"가 아니라 Fiori object cell에 가까운 정보 밀도와 정렬을 가져야 한다.
4. 카드 내부 액션은 최대 2개 직접 노출 + overflow 1개만 허용한다.
5. semantic status는 pill 배경을 아주 연하게 쓰고, 텍스트 대비로 상태를 읽게 만든다.
6. 입력 필드는 두꺼운 외곽선이나 강한 inset shadow 대신, 얇은 border와 8px~12px radius를 사용한다.
7. 화면 전체 그림자는 최소화하고, border / background / spacing으로 계층을 만든다.

## 6. 공통 구현 원칙

### 6.1 토큰과 타이포그래피

Phase 0에서 할 일:

- `static/css/erp-pro.css`에 모바일용 토큰 추가
- 신규 모바일 블록에서는 토큰만 사용
- 전역 `body`를 갈아엎지 않고, 모바일 셸과 신규 카드에만 실제 ERP 스타일 토큰을 적용한다

토큰 예시:

```css
:root {
  --erp-mobile-font-family: "72", "72full", "Segoe UI", "Malgun Gothic", Arial, sans-serif;
  --erp-mobile-font-xs: 0.75rem;      /* 12px */
  --erp-mobile-font-sm: 0.8125rem;    /* 13px */
  --erp-mobile-font-base: 0.875rem;   /* 14px */
  --erp-mobile-font-md: 0.9375rem;    /* 15px */
  --erp-mobile-font-lg: 1rem;         /* 16px */
  --erp-mobile-lh-tight: 1.3;
  --erp-mobile-lh-base: 1.45;
  --erp-mobile-touch-min: 44px;
  --erp-mobile-touch-target: 48px;
  --erp-mobile-color-app-bg: #f5f6f7;
  --erp-mobile-color-surface: #ffffff;
  --erp-mobile-color-surface-alt: #f7f7f7;
  --erp-mobile-color-selected: #ebf8ff;
  --erp-mobile-color-border: #d9d9d9;
  --erp-mobile-color-border-soft: #e5e5e5;
  --erp-mobile-color-text: #131e29;
  --erp-mobile-color-text-muted: #556b82;
  --erp-mobile-color-brand: #0070f2;
  --erp-mobile-color-brand-strong: #0057d2;
  --erp-mobile-radius-sm: 0.5rem;
  --erp-mobile-radius-md: 0.75rem;
  --erp-mobile-radius-lg: 1rem;
  --erp-mobile-shadow-1: 0 0.125rem 0.5rem rgba(17, 24, 39, 0.08);
}
```

설명:

- 폰트는 SAP의 72 계열을 우선으로 두고, 로컬 미설치 시 `Segoe UI`와 `Malgun Gothic`으로 자연스럽게 fallback 한다.
- 색상은 Morning Horizon 계열을 직접 난사하지 않고, FOMS용 semantic token으로 1회 매핑한다.
- 그림자는 1단계만 허용한다. 카드마다 다른 shadow scale을 쓰지 않는다.

하지 않을 일:

- `body` 전체를 다른 폰트로 강제 교체
- `min-font-size` 같은 비표준 속성 사용
- 버튼, badge, 카드에 raw hex를 직접 반복 하드코딩

### 6.2 모바일 셸 적용 방식

각 ERP 화면의 실제 루트 `.erp-pro`에 `erp-mobile-shell` 클래스를 추가한다.

예:

```html
<div class="container-fluid erp-dashboard erp-pro erp-mobile-shell">
```

모바일에서는 상단 shell header partial을 루트 직후 include 한다.

공통 CSS:

```css
@media (max-width: 991.98px) {
  .erp-mobile-shell {
    background: var(--erp-mobile-color-app-bg);
    padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));
  }

  .erp-mobile-shell .erp-mobile-shell-header {
    position: sticky;
    top: 0;
    z-index: 40;
    background: var(--erp-mobile-color-surface);
    border-bottom: 1px solid var(--erp-mobile-color-border-soft);
  }

  .erp-mobile-shell .erp-pro-nav {
    display: none;
  }
}
```

이 방식이면 `.erp-pro-content`에 의존하지 않아도 된다.

### 6.3 실제 최신 ERP 카드 규칙

Queue Family 카드와 실측 카드, 도면 카드, 출고 카드 모두 아래 규칙을 따른다.

1. 제목 줄은 "상태 / 단계"와 "오브젝트 이름"을 분리해서 보여준다.
2. 보조 정보는 최대 3줄까지만 기본 노출한다.
3. 직접 노출 액션은 최대 2개까지만 허용한다.
4. 나머지 액션은 overflow 메뉴로 보낸다.
5. 카드 하나 안에 primary filled button은 1개까지만 허용한다.
6. 카드 간 높이 차이는 같은 리스트 안에서 크게 벌어지지 않게 맞춘다.

이 규칙은 SAP Fiori object cell / object card와 Redwood식 work queue를 합친 FOMS 로컬 규칙이다.

### 6.4 카드 추상화 수준

공통화 범위는 아래까지만 허용한다.

허용:

- 큐 카드용 공통 CSS
- 액션 버튼 행 공통 CSS
- 공통 badge/label 스타일

부분 공통화:

- 대시보드/생산/시공은 하나의 큐 카드 partial 사용 가능

공통화 금지:

- 실측과 AS를 동일 카드 markup으로 강제 통일
- 도면/출고까지 하나의 카드 partial로 흡수

## 7. 파일 설계

### 7.1 신규/수정 파일

| 파일 | 작업 |
|---|---|
| `static/css/erp-pro.css` | Fiori 기반 모바일 토큰, shell header, 하단 탭, 드로어, 공통 큐 카드 CSS 추가 |
| `static/js/erp-mobile-shell.js` | 하단 탭 active 처리, header/overflow 보조 로직 |
| `services/context_processors.py` | `ERP_MOBILE_V2_ENABLED` 주입 |
| `templates/partials/erp_mobile_shell_header.html` | 상단 shell header |
| `templates/partials/erp_mobile_bottom_nav.html` | 하단 탭 |
| `templates/partials/erp_mobile_menu_drawer.html` | 더보기 드로어 |
| `templates/partials/erp_mobile_queue_card.html` | Queue Family 공통 카드 |
| `templates/erp_dashboard.html` | 모바일 셸 include |
| `templates/erp_measurement_dashboard.html` | 모바일 셸 include, 이후 실측 카드 도입 |
| `templates/erp_production_dashboard.html` | 모바일 셸 include |
| `templates/erp_construction_dashboard.html` | 모바일 셸 include |
| `templates/erp_shipment_dashboard.html` | 모바일 셸 include |
| `templates/erp_as_dashboard.html` | 모바일 셸 include |
| `templates/erp_drawing_workbench_dashboard.html` | 모바일 셸 include |
| `templates/erp_completion_dashboard.html` | 모바일 셸 include |
| `templates/erp_history_dashboard.html` | 모바일 셸 include |

### 7.2 feature flag

`services/context_processors.py`에 아래 성격의 값 주입이 가능하다.

```python
erp_mobile_v2_enabled = str(os.getenv("ERP_MOBILE_V2_ENABLED", "false")).lower() in ("1", "true", "yes", "on")
```

템플릿에서는:

```jinja2
{% if erp_mobile_v2_enabled %}
  {% include "partials/erp_mobile_shell_header.html" %}
  {% include "partials/erp_mobile_bottom_nav.html" %}
  {% include "partials/erp_mobile_menu_drawer.html" %}
{% endif %}
```

이렇게 두면 1차 롤백은 환경변수만 꺼도 된다.

## 8. 구현 순서

### Phase 0. 공통 인프라

목표:

- 데스크톱을 건드리지 않고 모바일 전용 셸을 안전하게 얹는다.

작업:

1. `services/context_processors.py`
   - `erp_mobile_v2_enabled` 주입
2. `static/css/erp-pro.css`
   - Fiori 기반 모바일 토큰 추가
   - `erp-mobile-shell` 여백 처리
   - shell header 스타일 추가
   - 하단 탭 / 드로어 스타일 추가
3. `static/js/erp-mobile-shell.js`
   - 현재 URL 기준 active tab 보조
   - header overflow 보조
4. 신규 partial 3개 생성
   - `erp_mobile_shell_header.html`
   - `erp_mobile_bottom_nav.html`
   - `erp_mobile_menu_drawer.html`
5. 9개 ERP 템플릿 루트에 `erp-mobile-shell` 클래스 추가
6. 9개 ERP 템플릿 상하단에 모바일 partial include 추가

검증:

- 360px에서 shell header가 sticky로 유지된다.
- 360px에서 하단 탭이 보인다.
- 본문 마지막 카드가 탭에 가리지 않는다.
- 1200px에서는 현재 상단 ERP 탭만 보인다.

롤백:

- `ERP_MOBILE_V2_ENABLED=false`
- 필요 시 phase 0 주석 블록만 제거

### Phase 1. 대시보드 모바일 큐

대상:

- `templates/erp_dashboard.html`
- `templates/partials/erp_dashboard_grid.html`
- `templates/partials/erp_dashboard_filters.html`
- `templates/partials/erp_dashboard_styles.html`
- `templates/partials/erp_mobile_queue_card.html`

이유:

- 대시보드는 모바일 홈 역할을 맡아야 한다.
- Queue Family 중 가장 먼저 검증하기 좋다.
- read-only 비중이 높아 회귀 위험이 실측/AS보다 낮다.

작업:

1. 모바일에서 기존 13컬럼 테이블을 그대로 쓰지 않음
2. 모바일 전용 큐 카드 partial로 렌더
3. 기본 노출 정보 5개만 남김
   - 고객
   - 단계
   - 일정
   - 담당자
   - 주소 요약
4. 직접 액션은 최대 2개만 유지
   - 열기
   - 전화 또는 지도
5. 나머지 액션은 overflow에 배치
6. 필터는 모바일에서 "검색 + 필터 버튼" 구조로 축소

검증:

- 360px에서 가로 스크롤 없음
- 카드에서 상세 이동 가능
- 1200px에서는 기존 13컬럼 테이블 유지

롤백:

- 큐 카드 partial include 제거
- 모바일용 filter bar include 제거
- 데스크톱 템플릿은 손상 없음

### Phase 2. 생산 / 시공

대상:

- 생산, 시공 관련 partial

이유:

- 대시보드와 같은 Queue Family라 재사용성이 높다.
- 대시보드에서 검증된 패턴을 옮기기 좋다.

작업:

1. 대시보드 큐 카드 패턴 재사용
2. 생산/시공 전용 badge와 액션만 추가
3. 기존 overflow 보정 CSS 중 모바일 충돌 부분 정리

검증:

- 생산/시공 모두 360px에서 카드 중심 렌더
- 기존 데스크톱 테이블 동작 유지

### Phase 3. 실측

대상:

- `templates/erp_measurement_dashboard.html`

이유:

- 가장 모바일 니즈가 큰 화면이지만, 편집/일정/지도 의존성이 높아 늦게 들어가는 게 안전하다.

작업:

1. 모바일에서 날짜 그룹 + 일정 카드 구조 도입
2. 기존 `min-width: 1220px` 테이블을 모바일에서 숨김
3. 카드에는 최소 정보만 노출
   - 고객
   - 시간
   - 주소
   - 제품
   - 담당자
4. 카드 액션
   - 열기
   - 지도
5. 일정변경, 배정변경 등 보조 액션은 overflow로 이동
6. 고급 편집은 기존 상세/기존 기능 재사용

검증:

- 360px에서 실측 일정이 카드형으로 읽힌다
- 지도/경로 기능이 깨지지 않는다
- 데스크톱 테이블 유지

### Phase 4. AS

대상:

- `templates/erp_as_dashboard.html`

이유:

- 이미 모바일 카드가 있다
- 지금 필요한 건 구조 교체보다 밀도 조정과 액션 정리다

작업:

1. 기존 `erp-pro-order-card` 유지
2. 타이포, 여백, 버튼 크기, 행 순서만 정리
3. `contenteditable` 영역은 유지
4. 카드 전체 구조는 새 공통 큐 카드로 교체하지 않음

검증:

- 기존 날짜 편집, pending 버튼, 사진 보기, 도면 체크, 리치 에디터 모두 유지

### Phase 5. 도면 / 출고 / 완료 / 이력

대상:

- `templates/erp_drawing_workbench_dashboard.html`
- `templates/erp_shipment_dashboard.html`
- `templates/erp_completion_dashboard.html`
- `templates/erp_history_dashboard.html`

작업:

1. 도면
   - 기존 모바일 카드 유지
   - 텍스트 밀도, 버튼 행, badge 정리
2. 출고
   - 현재 `erp-mobile-card-table` 유지
   - 필터와 액션 버튼 우선 정리
3. 완료
   - 갤러리와 요약 행 타이포 정리
4. 이력
   - 모바일 split/grid 정리

검증:

- 기존 specialized interaction이 유지된다
- 모바일 셸과 충돌하지 않는다

## 9. 감리 기준

### 9.1 공통

- 360px 기준 가로 스크롤이 없어야 한다
  - 단, 출고의 일부 카드화 테이블 내부 수평 스크롤은 예외가 아니라 제거 대상이다
- 44px 미만 터치 타겟이 새 코드에 없어야 한다
- 12px 미만 새 폰트가 없어야 한다
- 992px 이상에서 기존 데스크톱 UI가 유지돼야 한다

### 9.2 코드 감사 명령

```powershell
rg -n "font-size:\\s*0\\.(5|55|6|65|7)rem|font-size:\\s*1[01]px" templates static\css
rg -n "min-width:\\s*(1220|1280|1000)px" templates
rg -n "erp-mobile-shell|erp_mobile_shell_header|erp_mobile_bottom_nav|erp_mobile_menu_drawer|erp_mobile_queue_card" templates static\css services
```

### 9.3 화면별 최소 검증

| 화면 | 반드시 확인할 것 |
|---|---|
| 대시보드 | 카드 렌더, 상세 이동, 필터 버튼 |
| 생산 | 카드 렌더, 상태 badge |
| 시공 | 카드 렌더, 일정/상태 정보 |
| 실측 | 날짜 그룹, 지도, 일정변경 |
| AS | 날짜 편집, 리치 에디터, 사진 버튼 |
| 도면 | 카드 클릭 이동, assign 버튼, unread badge |
| 출고 | 카드화 테이블, 필터, 액션 버튼 |

## 10. 롤백 전략

### 10.1 1차 롤백

- `ERP_MOBILE_V2_ENABLED=false`

효과:

- 신규 모바일 셸 비노출
- 데스크톱/기존 모바일 동작 유지

### 10.2 2차 롤백

- phase별 주석 블록 제거
- 해당 phase에서 추가한 partial include 제거

예:

- Phase 1 문제면 대시보드 관련 파일만 되돌림
- 실측 문제면 실측 파일만 되돌림

금지:

- `templates/` 전체 롤백
- unrelated 변경까지 덮는 광역 복구

## 11. 최종 결정

이 계획의 핵심은 아래다.

1. 모바일 전용 ERP는 만든다.
2. 하지만 URL과 백엔드 로직은 유지한다.
3. 공통 모바일 셸은 얹되, 화면 내부 구조는 family별로 다르게 다룬다.
4. 가장 먼저 바꿀 화면은 대시보드다.
5. 가장 늦게 들어갈 화면은 실측과 AS 같은 편집형 화면이다.

한 줄로 정리하면:

> FOMS 모바일 ERP는 "공통 셸 + 화면군별 점진 재설계"로 가야 하며, "단일 카드 컴포넌트로 전 화면 통일" 방식으로 가면 안 된다.
