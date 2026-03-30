# FOMS WAM 디자인 시스템 상세 명세서
작성일: 2026-03-27
상태: 승인 / 실행기준서
범위: `ChannelTalk -> WAM 상세 주문뷰`의 독립 디자인 토큰 시스템과 구현 가드레일
연관 문서:
- `docs/plans/2026-03-27-wam-detailed-order-view-master-plan.md`
- `docs/plans/2026-03-26-foms-channeltalk-integration-focus-plan.md`
- `docs/plans/2026-03-27-wam-file-skeleton-spec.md`
- `docs/plans/2026-03-27-wam-starter-spec.md`

## 1. 한 줄 결론

WAM 상세 주문뷰는 FOMS ERP 스타일을 그대로 상속하지 않는다.
대신 `세계적 ERP 톤의 독립 디자인 시스템`으로 설계하고, FOMS는 업무 제품군 간 정합성을 맞추는 참고 기준으로만 사용한다.

이 문서의 목적은 3가지다.

1. `토큰 source of truth`를 하나로 고정
2. `컴포넌트별 토큰 사용 규칙`을 고정
3. `acceptance / rollback / versioning`을 미리 문서화

## 2. 디자인 목표

### 2.1 경험 목표

- 채널톡에서 주문 링크를 열었을 때 `1초 안에 내가 보고 싶은 주문이 맞는지` 알 수 있어야 한다.
- `3초 안에 일정, 주소, 담당, 연락처`를 읽을 수 있어야 한다.
- `5초 안에 첨부 또는 최근 변경 탐색`을 시작할 수 있어야 한다.
- 모바일 WebView에서도 읽기 전용 정보가 답답하지 않고, ERP답게 정보 밀도는 높되 과밀하지 않아야 한다.

### 2.2 스타일 목표

- 구조는 `SAP Fiori Object Page`처럼 명확한 정보 위계를 가진다.
- 읽기성은 `Microsoft Fluent 2`처럼 type ramp와 spacing이 선명해야 한다.
- 표면 톤은 `Oracle Redwood`처럼 차분하고 polished해야 한다.
- 결과물은 특정 벤더 복제가 아니라 `vendor-neutral global ERP tone`이어야 한다.

## 3. Source Of Truth

### 3.1 기준 파일

WAM 디자인 시스템의 source of truth는 아래 파일군이다.

- `static/css/wam/tokens.css`
- `static/css/wam/base.css`
- `static/css/wam/layout.css`
- `static/css/wam/components.css`
- `static/css/wam/order-detail.css`

권장 초기 단계에서는 파일 수를 줄여도 되지만, source of truth는 언제나 `WAM 전용 CSS 계층`이어야 한다.

### 3.2 ERP와의 관계

- [`static/css/erp-pro.css`](static/css/erp-pro.css)는 `참고 기준`이다.
- ERP 토큰을 직접 alias해서 WAM의 기본값으로 삼지 않는다.
- ERP와 비슷한 값이 나와도 그것은 `의도된 시각 정합성`이지 상속이 아니다.

### 3.3 금지

- `templates/channel_wam/*`에서 직접 `--erp-*` 토큰 사용 금지
- `components.css`에서 raw hex, px 직접 사용 금지
- 컴포넌트 마크업에서 inline style 사용 금지

## 4. 토큰 아키텍처

### 4.1 3계층 구조

WAM 토큰은 아래 3계층으로 고정한다.

1. `Reference tokens`
- 순수 값만 가진다.
- color, radius, shadow, spacing, type scale, motion, size 값의 저장소다.

2. `Semantic tokens`
- UI 의미를 가진다.
- page, surface, text, border, status, action 같은 역할을 담당한다.

3. `Component tokens`
- 주문뷰 전용 조립값이다.
- compact header, summary strip, section card, attachment rail, sticky action bar 같은 컴포넌트 밀도와 배치를 담당한다.

### 4.2 허용 규칙

- raw 값은 `reference`에만 둔다.
- `semantic`은 반드시 `var(--wam-ref-*)`로만 정의한다.
- `component`는 반드시 `var(--wam-ref-*)` 또는 `var(--wam-sys-*)`로만 정의한다.
- 컴포넌트 CSS는 `--wam-sys-*`, `--wam-comp-*`만 소비한다.

## 5. 네이밍 규칙

### 5.1 Prefix

- reference: `--wam-ref-*`
- semantic: `--wam-sys-*`
- component: `--wam-comp-*`

### 5.2 네이밍 문법

- color family: `--wam-ref-neutral-100`, `--wam-ref-brand-600`
- semantic role: `--wam-sys-text-primary`, `--wam-sys-surface-card`
- component role: `--wam-comp-header-bg`, `--wam-comp-sticky-bar-height`

### 5.3 금지 패턴

- `--wam-primary-blue-final`
- `--wam-card-padding-new`
- `--wam-header-bg-2`
- 의미 없는 숫자 suffix 남발

## 6. 토큰 세트

### 6.1 Reference Layer

필수 그룹:

- neutral
- brand
- success / warning / danger / info
- radius
- shadow
- spacing
- type
- motion
- fixed sizes

초기 권장 값:

```css
:root {
  --wam-ref-neutral-0: #ffffff;
  --wam-ref-neutral-50: #f7f9fc;
  --wam-ref-neutral-100: #eef2f7;
  --wam-ref-neutral-200: #e2e8f0;
  --wam-ref-neutral-300: #cbd5e1;
  --wam-ref-neutral-500: #64748b;
  --wam-ref-neutral-700: #334155;
  --wam-ref-neutral-900: #0f172a;

  --wam-ref-brand-500: #2563eb;
  --wam-ref-brand-600: #1d4ed8;
  --wam-ref-brand-700: #1e40af;

  --wam-ref-green-500: #16a34a;
  --wam-ref-amber-500: #d97706;
  --wam-ref-red-500: #dc2626;
  --wam-ref-sky-500: #0284c7;
  --wam-ref-overlay-glass: rgba(255,255,255,0.88);

  --wam-ref-status-info-bg: #eff6ff;
  --wam-ref-status-info-fg: #1d4ed8;
  --wam-ref-status-success-bg: #dcfce7;
  --wam-ref-status-success-fg: #166534;
  --wam-ref-status-warning-bg: #fef3c7;
  --wam-ref-status-warning-fg: #92400e;
  --wam-ref-status-danger-bg: #fee2e2;
  --wam-ref-status-danger-fg: #991b1b;

  --wam-ref-radius-sm: 10px;
  --wam-ref-radius-md: 14px;
  --wam-ref-radius-lg: 18px;
  --wam-ref-radius-xl: 24px;
  --wam-ref-radius-pill: 999px;

  --wam-ref-shadow-sm: 0 1px 2px rgba(15,23,42,0.06);
  --wam-ref-shadow-md: 0 8px 24px rgba(15,23,42,0.08);
  --wam-ref-shadow-lg: 0 20px 48px rgba(15,23,42,0.12);

  --wam-ref-space-1: 4px;
  --wam-ref-space-2: 8px;
  --wam-ref-space-3: 12px;
  --wam-ref-space-4: 16px;
  --wam-ref-space-5: 20px;
  --wam-ref-space-6: 24px;
  --wam-ref-space-8: 32px;

  --wam-ref-size-attachment-preview: 72px;
  --wam-ref-size-sticky-bar: 72px;
  --wam-ref-size-content-max: 960px;

  --wam-ref-text-xs: 12px/16px;
  --wam-ref-text-sm: 13px/18px;
  --wam-ref-text-md: 14px/20px;
  --wam-ref-text-lg: 16px/22px;
  --wam-ref-text-xl: 20px/28px;
  --wam-ref-text-2xl: 24px/32px;

  --wam-ref-transition-fast: 140ms ease-out;
  --wam-ref-transition-base: 220ms ease;
  --wam-ref-transition-slow: 320ms ease;
}
```

### 6.2 Semantic Layer

최소 필수 semantic 그룹:

- `surface`
- `text`
- `border`
- `status`
- `action`
- `state`

예시:

```css
:root {
  --wam-sys-bg-page: var(--wam-ref-neutral-50);
  --wam-sys-surface-card: var(--wam-ref-neutral-0);
  --wam-sys-surface-subtle: var(--wam-ref-neutral-100);
  --wam-sys-surface-overlay: var(--wam-ref-overlay-glass);

  --wam-sys-border-subtle: var(--wam-ref-neutral-200);
  --wam-sys-border-strong: var(--wam-ref-neutral-300);

  --wam-sys-text-primary: var(--wam-ref-neutral-900);
  --wam-sys-text-secondary: var(--wam-ref-neutral-700);
  --wam-sys-text-tertiary: var(--wam-ref-neutral-500);

  --wam-sys-action-primary: var(--wam-ref-brand-600);
  --wam-sys-action-primary-hover: var(--wam-ref-brand-700);
  --wam-sys-action-secondary: var(--wam-ref-neutral-100);
  --wam-sys-action-disabled-bg: var(--wam-ref-neutral-100);
  --wam-sys-action-disabled-fg: var(--wam-ref-neutral-500);

  --wam-sys-status-info-bg: var(--wam-ref-status-info-bg);
  --wam-sys-status-info-fg: var(--wam-ref-status-info-fg);
  --wam-sys-status-success-bg: var(--wam-ref-status-success-bg);
  --wam-sys-status-success-fg: var(--wam-ref-status-success-fg);
  --wam-sys-status-warning-bg: var(--wam-ref-status-warning-bg);
  --wam-sys-status-warning-fg: var(--wam-ref-status-warning-fg);
  --wam-sys-status-danger-bg: var(--wam-ref-status-danger-bg);
  --wam-sys-status-danger-fg: var(--wam-ref-status-danger-fg);

  --wam-sys-state-error-bg: var(--wam-ref-status-danger-bg);
  --wam-sys-state-error-border: var(--wam-ref-red-500);
  --wam-sys-state-error-fg: var(--wam-ref-status-danger-fg);
}
```

### 6.3 Component Layer

필수 component 그룹:

- header
- summary strip
- card
- badge
- key-value row
- attachment rail
- sticky action bar
- empty / error state

원칙:

- component token은 오직 `밀도`, `간격`, `크기`, `배치`, `특화 표면`만 담당한다.
- 색 역할은 semantic에서 처리하고, component는 semantic을 소비한다.

## 7. 컴포넌트별 토큰 매핑

### 7.1 Compact Header

필수 semantic:

- `--wam-sys-surface-overlay`
- `--wam-sys-border-subtle`
- `--wam-sys-text-primary`
- `--wam-sys-text-secondary`

권장 component:

- `--wam-comp-header-bg`
- `--wam-comp-header-backdrop`
- `--wam-comp-header-min-height`
- `--wam-comp-header-padding-x`
- `--wam-comp-header-padding-y`
- `--wam-comp-header-gap`
- `--wam-comp-header-shadow`
- `--wam-comp-header-title-size`
- `--wam-comp-header-meta-size`
- `--wam-comp-header-badge-gap`

### 7.2 Summary Strip

필수 semantic:

- `--wam-sys-surface-subtle`
- `--wam-sys-border-subtle`
- `--wam-sys-text-primary`
- `--wam-sys-text-secondary`
- `--wam-sys-text-tertiary`

권장 component:

- `--wam-comp-summary-strip-bg`
- `--wam-comp-summary-strip-padding`
- `--wam-comp-summary-grid-gap`
- `--wam-comp-summary-column-min`
- `--wam-comp-summary-label-size`
- `--wam-comp-summary-value-size`
- `--wam-comp-summary-divider-inset`

### 7.3 Section Card

필수 semantic:

- `--wam-sys-surface-card`
- `--wam-sys-border-subtle`
- `--wam-sys-border-strong`
- `--wam-sys-text-primary`
- `--wam-sys-text-secondary`

권장 component:

- `--wam-comp-card-padding`
- `--wam-comp-card-gap`
- `--wam-comp-card-radius`
- `--wam-comp-card-shadow`
- `--wam-comp-card-header-gap`
- `--wam-comp-card-body-gap`
- `--wam-comp-card-section-gap`

### 7.4 Status Badge

필수 semantic:

- `--wam-sys-status-info-bg`
- `--wam-sys-status-info-fg`
- `--wam-sys-status-success-bg`
- `--wam-sys-status-success-fg`
- `--wam-sys-status-warning-bg`
- `--wam-sys-status-warning-fg`
- `--wam-sys-status-danger-bg`
- `--wam-sys-status-danger-fg`

권장 component:

- `--wam-comp-badge-radius`
- `--wam-comp-badge-height`
- `--wam-comp-badge-padding-x`
- `--wam-comp-badge-gap`
- `--wam-comp-badge-font-size`
- `--wam-comp-badge-icon-size`

### 7.5 Key-Value Rows

필수 semantic:

- `--wam-sys-text-primary`
- `--wam-sys-text-tertiary`
- `--wam-sys-border-subtle`
- `--wam-sys-action-primary`

권장 component:

- `--wam-comp-kv-row-padding-y`
- `--wam-comp-kv-row-gap`
- `--wam-comp-kv-label-width`
- `--wam-comp-kv-value-gap`
- `--wam-comp-kv-divider-inset`
- `--wam-comp-kv-stack-breakpoint`

### 7.6 Attachment Rail

필수 semantic:

- `--wam-sys-surface-card`
- `--wam-sys-surface-subtle`
- `--wam-sys-border-subtle`
- `--wam-sys-text-primary`
- `--wam-sys-text-tertiary`
- `--wam-sys-action-primary`

권장 component:

- `--wam-comp-attachment-preview-size`
- `--wam-comp-attachment-radius`
- `--wam-comp-attachment-gap`
- `--wam-comp-attachment-rail-padding`
- `--wam-comp-attachment-meta-gap`
- `--wam-comp-attachment-count-badge-offset`
- `--wam-comp-attachment-skeleton-size`

### 7.7 Sticky Action Bar

필수 semantic:

- `--wam-sys-surface-overlay`
- `--wam-sys-border-strong`
- `--wam-sys-action-primary`
- `--wam-sys-text-primary`
- `--wam-sys-text-secondary`
- `--wam-sys-action-secondary`
- `--wam-sys-action-disabled-bg`
- `--wam-sys-action-disabled-fg`

권장 component:

- `--wam-comp-sticky-bar-height`
- `--wam-comp-sticky-bar-padding-x`
- `--wam-comp-sticky-bar-padding-y`
- `--wam-comp-sticky-bar-gap`
- `--wam-comp-sticky-bar-shadow`
- `--wam-comp-sticky-primary-min-width`
- `--wam-comp-sticky-icon-button-size`
- `--wam-comp-sticky-safe-area-bottom`

### 7.8 Empty / Error State

empty semantic:

- `--wam-sys-surface-subtle`
- `--wam-sys-text-secondary`
- `--wam-sys-text-tertiary`

error semantic:

- `--wam-sys-state-error-bg`
- `--wam-sys-state-error-border`
- `--wam-sys-state-error-fg`
- `--wam-sys-action-primary`

공통 component:

- `--wam-comp-state-padding`
- `--wam-comp-state-gap`
- `--wam-comp-state-icon-size`
- `--wam-comp-state-title-size`
- `--wam-comp-state-body-max-width`
- `--wam-comp-state-action-gap`

### 7.9 Timeline / Read-Only Notice

timeline 원칙:

- timeline은 전용 색 체계를 만들지 않고 `section card + key-value row + status badge` 조합으로 표현한다.
- read-only notice도 전용 카드보다 `summary strip` 또는 `state/info banner` 재사용을 우선한다.
- 새 전용 토큰은 실제로 재사용 이점이 있을 때만 추가한다.

## 8. CSS / 템플릿 구조

### 8.1 파일 구조

```text
templates/channel_wam/
  layout.html
  index.html
  _macros.html
  sections/
    _header.html
    _summary_strip.html
    _customer.html
    _site.html
    _schedule.html
    _people.html
    _items.html
    _attachments.html
    _timeline.html
  states/
    _empty.html
    _error.html

static/css/wam/
  tokens.css
  base.css
  layout.css
  components.css
  order-detail.css

static/js/wam/
  core.js
  telemetry.js
  attachments.js
  order-detail.js
```

### 8.2 CSS 로딩 순서

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/erp-pro.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/wam/tokens.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/wam/base.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/wam/layout.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/wam/components.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/wam/order-detail.css') }}">
```

주의:

- `erp-pro.css`는 참고 배경일 뿐이고, WAM 마크업은 `.wam-*` 클래스만 사용한다.
- `components.css`와 `order-detail.css`는 `--wam-*`만 소비한다.

### 8.3 Jinja 규칙

- `layout.html`은 skeleton만 가진다.
- `index.html`은 `page_vm`만 받아 include를 조합한다.
- section partial은 각자 `section.payload`만 소비한다.
- empty/error는 공통 states partial을 재사용한다.
- bootstrap 데이터는 JSON script tag로 넣고 inline JS를 금지한다.

## 9. 거버넌스

### 9.1 승인 체계

- `프론트 책임자`: 토큰 구조, 컴포넌트 일관성, CSS 구현 승인
- `제품 책임자`: 모바일 UX, 정보 위계, CTA 표현 승인
- `운영 책임자`: rollout / rollback, 실사용성 승인

### 9.2 변경 분류

- `token_add`
- `token_value_change`
- `token_rename`
- `token_deprecate`
- `component_mapping_change`

### 9.3 Deprecation 규칙

- 즉시 삭제 금지
- 대체 토큰 명시 필수
- 최소 1개 릴리스 동안 deprecated bridge 유지

## 10. Acceptance Checklist

### 10.1 토큰 Acceptance

- 새 토큰은 `도입 이유`가 있어야 한다.
- semantic/component layer 직접 raw 값 사용 금지
- 동일 역할 토큰이 중복 정의되지 않아야 한다.
- 1회성 값이면 공용 토큰으로 승격하지 않는다.

### 10.2 UI Acceptance

- iPhone Safari WebView
- Android Chrome WebView
- 긴 고객명 / 긴 주소 / 긴 제품명
- 첨부 0건 / 10건 / 50건
- 최근 변경 0건 / 5건 / 20건
- sticky action bar와 스크롤 충돌 없음

### 10.3 접근성 Acceptance

- 텍스트 대비 기준 충족
- focus-visible이 명확함
- 터치 타깃이 충분함
- sticky/fixed 요소가 핵심 콘텐츠를 가리지 않음

### 10.4 성능 Acceptance

- 첫 paint 목표 훼손 없음
- 토큰/컴포넌트 CSS 추가 후 레이아웃 흔들림 최소
- 큰 첨부 주문에서도 과도한 DOM 증식 없음

## 11. Rollback

### 11.1 범위

- `token value rollback`
- `component token rollback`
- `WAM theme 전체 rollback`

### 11.2 트리거

- 가독성 붕괴
- CTA 가림
- sticky 충돌
- 색 대비 실패
- 모바일 overflow

### 11.3 원칙

- 핵심 화면은 `header -> summary -> sticky bar` 순서로 우선 복구
- 삭제보다 `deprecated bridge` 유지가 우선
- rollback 책임자는 프론트 책임자가 즉시 실행 가능해야 한다.

## 12. 버전 정책

- `WAM token set v1`
- `WAM token set v1.1`
- `WAM token set v2`

권장:

- 토큰 변경은 changelog를 남긴다.
- major는 semantic/component 재구성
- minor는 token add 또는 safe value tuning
- patch는 contrast/shadow/spacing 미세 조정

## 13. 바로 실행할 작업

1. `tokens.css` 초안 작성
2. `layout.html` / `index.html` 스켈레톤 분리
3. `components.css`에 header / card / badge / sticky bar 우선 구현
4. `order-detail.css`는 예외 최소화
5. summary strip과 section card를 기준 컴포넌트로 먼저 고정

## 14. 외부 레퍼런스

- SAP Fiori Object Page: https://experience.sap.com/fiori-design-web/object-page/
- Microsoft Fluent 2 Typography: https://fluent2.microsoft.design/typography
- Oracle Design: https://design.oracle.com/
