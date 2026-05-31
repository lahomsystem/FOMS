# FOMS 모바일·태블릿 디자인 시스템

> 작성: 2026-05-28 | 버전: 1.0 | 짝 문서: `MOBILE_TABLET_REDESIGN_PLAN.md`
> 토큰 네임스페이스: `--foms-*` (단일)

이 문서는 FOMS 전역에서 사용할 디자인 토큰·타이포·간격·색상·모션·아이콘 시스템을 정의한다. 모든 컴포넌트는 본 시스템의 토큰만 참조해야 한다. 하드코딩된 색·간격·폰트 값은 PR 리뷰에서 reject 대상.

---

## 1. 토큰 단일화 원칙

기존 3종 토큰 (`erp-pro`·`erp-mobile-*`·`channel/wam`) → 단일 `--foms-*`로 통합.

마이그레이션 표:

| 기존 토큰 | 신규 토큰 | 비고 |
|---|---|---|
| `--erp-primary` | `--foms-color-primary-500` | |
| `--erp-success` | `--foms-color-success-500` | |
| `--erp-danger` | `--foms-color-danger-500` | |
| `--erp-warning` | `--foms-color-warning-500` | |
| `--erp-shadow-sm` | `--foms-shadow-sm` | |
| `--erp-radius-sm/md/lg` | `--foms-radius-sm/md/lg` | |
| `--erp-space-1..8` | `--foms-space-1..12` | 4pt grid 재정의 |
| `--erp-mobile-nav-height` | `--foms-shell-bottom-nav-h` | |
| `--wam-bg` / `--wam-fg` | `--foms-surface-base` / `--foms-text-primary` | |

자동 마이그레이션 스크립트: `tools/design/migrate-tokens.py` (P1 작업).

---

## 2. 컬러 토큰

### 2.1 Primitive Scale (브랜드 + Semantic)

각 색상은 50/100/200/300/400/500/600/700/800/900의 10단계.

```css
:root {
  /* Brand Purple — FOMS Identity */
  --foms-color-brand-50:  #f3f4ff;
  --foms-color-brand-100: #e6e8ff;
  --foms-color-brand-200: #c5c9ff;
  --foms-color-brand-300: #9ea4ff;
  --foms-color-brand-400: #7882f0;
  --foms-color-brand-500: #5a67d8;  /* Primary */
  --foms-color-brand-600: #4a55b8;
  --foms-color-brand-700: #3a4490;
  --foms-color-brand-800: #2c356b;
  --foms-color-brand-900: #1f2649;

  /* Success — Green */
  --foms-color-success-50:  #ecfdf5;
  --foms-color-success-100: #d1fae5;
  --foms-color-success-500: #10b981;
  --foms-color-success-600: #059669;
  --foms-color-success-700: #047857;

  /* Warning — Amber */
  --foms-color-warning-50:  #fffbeb;
  --foms-color-warning-100: #fef3c7;
  --foms-color-warning-500: #f59e0b;
  --foms-color-warning-600: #d97706;
  --foms-color-warning-700: #b45309;

  /* Danger — Red */
  --foms-color-danger-50:  #fef2f2;
  --foms-color-danger-100: #fee2e2;
  --foms-color-danger-500: #ef4444;
  --foms-color-danger-600: #dc2626;
  --foms-color-danger-700: #b91c1c;

  /* Info — Blue */
  --foms-color-info-50:  #eff6ff;
  --foms-color-info-100: #dbeafe;
  --foms-color-info-500: #3b82f6;
  --foms-color-info-600: #2563eb;

  /* Neutral — Gray (Slate-warm) */
  --foms-color-neutral-0:    #ffffff;
  --foms-color-neutral-50:   #f7f8fa;
  --foms-color-neutral-100:  #eef0f3;
  --foms-color-neutral-200:  #dde1e6;
  --foms-color-neutral-300:  #c1c7d0;
  --foms-color-neutral-400:  #9aa3af;
  --foms-color-neutral-500:  #6b7380;
  --foms-color-neutral-600:  #4b525d;
  --foms-color-neutral-700:  #353a44;
  --foms-color-neutral-800:  #22262e;
  --foms-color-neutral-900:  #14171c;
  --foms-color-neutral-1000: #0a0c10;

  /* Workflow Stage Colors (가구 ERP 특화 — 단계별 식별) */
  --foms-stage-received:     #6b7380;  /* neutral */
  --foms-stage-happycall:    #06b6d4;  /* cyan */
  --foms-stage-measure:      #3b82f6;  /* info blue */
  --foms-stage-drawing:      #8b5cf6;  /* violet */
  --foms-stage-confirm:      #5a67d8;  /* brand */
  --foms-stage-production:   #f59e0b;  /* warning amber */
  --foms-stage-shipment:     #ec4899;  /* pink */
  --foms-stage-construction: #10b981;  /* success green */
  --foms-stage-cs:           #ef4444;  /* danger red */
  --foms-stage-completed:    #4b525d;  /* dim */
}
```

### 2.2 Semantic Aliases (Light Theme)

```css
:root,
[data-theme="light"] {
  /* Surface (배경 3단계) */
  --foms-surface-base:    var(--foms-color-neutral-0);   /* 페이지 배경 */
  --foms-surface-raised:  var(--foms-color-neutral-50);  /* 카드 1단계 */
  --foms-surface-overlay: var(--foms-color-neutral-100); /* 카드 2단계 / sticky bar */
  --foms-surface-inverse: var(--foms-color-neutral-900);

  /* Border */
  --foms-border-subtle:   var(--foms-color-neutral-200);
  --foms-border-default:  var(--foms-color-neutral-300);
  --foms-border-strong:   var(--foms-color-neutral-500);
  --foms-border-focus:    var(--foms-color-brand-500);

  /* Text */
  --foms-text-primary:    var(--foms-color-neutral-900);
  --foms-text-secondary:  var(--foms-color-neutral-600);
  --foms-text-tertiary:   var(--foms-color-neutral-500);
  --foms-text-inverse:    var(--foms-color-neutral-0);
  --foms-text-link:       var(--foms-color-brand-600);
  --foms-text-link-hover: var(--foms-color-brand-700);
  --foms-text-disabled:   var(--foms-color-neutral-400);

  /* Interactive */
  --foms-interactive-primary:        var(--foms-color-brand-500);
  --foms-interactive-primary-hover:  var(--foms-color-brand-600);
  --foms-interactive-primary-active: var(--foms-color-brand-700);
  --foms-interactive-secondary:        var(--foms-color-neutral-100);
  --foms-interactive-secondary-hover:  var(--foms-color-neutral-200);
  --foms-interactive-danger:        var(--foms-color-danger-500);
  --foms-interactive-danger-hover:  var(--foms-color-danger-600);
}
```

### 2.3 Dark Theme

```css
[data-theme="dark"] {
  --foms-surface-base:    var(--foms-color-neutral-1000);
  --foms-surface-raised:  var(--foms-color-neutral-900);
  --foms-surface-overlay: var(--foms-color-neutral-800);
  --foms-surface-inverse: var(--foms-color-neutral-50);

  --foms-border-subtle:   var(--foms-color-neutral-800);
  --foms-border-default:  var(--foms-color-neutral-700);
  --foms-border-strong:   var(--foms-color-neutral-500);

  --foms-text-primary:    var(--foms-color-neutral-50);
  --foms-text-secondary:  var(--foms-color-neutral-300);
  --foms-text-tertiary:   var(--foms-color-neutral-400);
  --foms-text-inverse:    var(--foms-color-neutral-900);
  --foms-text-link:       var(--foms-color-brand-300);
  --foms-text-link-hover: var(--foms-color-brand-200);
  --foms-text-disabled:   var(--foms-color-neutral-600);

  /* Stage colors slightly desaturated for dark */
  --foms-stage-received:     #9aa3af;
  --foms-stage-happycall:    #22d3ee;
  --foms-stage-measure:      #60a5fa;
  --foms-stage-drawing:      #a78bfa;
  --foms-stage-confirm:      #7882f0;
  --foms-stage-production:   #fbbf24;
  --foms-stage-shipment:     #f472b6;
  --foms-stage-construction: #34d399;
  --foms-stage-cs:           #f87171;
  --foms-stage-completed:    #6b7380;
}
```

### 2.4 컬러 사용 규칙

- **Primary**는 1차 CTA·활성 상태·링크에만. 한 화면 5% 미만.
- **Danger**는 파괴적 액션·치명적 오류·시간 초과에만. 단계 색과 혼동 금지.
- **Stage colors**는 워크플로우 단계 배지·타임라인·상태 인디케이터에만.
- 본문 텍스트는 `--foms-text-primary`만. `--foms-text-secondary`는 메타·라벨.
- 비활성: `--foms-text-disabled` + opacity 미사용 (대비 위반).

---

## 3. 타이포그래피

### 3.1 Font Stack

```css
:root {
  --foms-font-sans: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont,
                    'Apple SD Gothic Neo', 'Segoe UI', 'Noto Sans KR', 'Malgun Gothic',
                    sans-serif;
  --foms-font-mono: ui-monospace, SFMono-Regular, 'JetBrains Mono', 'Cascadia Code',
                    Menlo, Monaco, Consolas, monospace;
  --foms-font-display: 'Pretendard Variable', Pretendard, sans-serif;
}
```

Pretendard Variable 로컬 호스팅 (CDN 의존 금지):
- `/static/fonts/Pretendard-Variable.woff2` (45KB)
- `font-display: swap`

### 3.2 Type Scale

| Token | Size | Line | Weight | 용도 |
|---|---|---|---|---|
| `--foms-text-xs` | 12px (0.75rem) | 1.5 | 400 | caption, meta, badge |
| `--foms-text-sm` | 14px (0.875rem) | 1.5 | 400 | secondary text, label |
| `--foms-text-base` | 16px (1rem) | 1.55 | 400 | **body — 모바일 기본** |
| `--foms-text-lg` | 18px (1.125rem) | 1.5 | 500 | section title, list item |
| `--foms-text-xl` | 20px (1.25rem) | 1.4 | 600 | card title, modal title |
| `--foms-text-2xl` | 24px (1.5rem) | 1.3 | 600 | page title |
| `--foms-text-3xl` | 30px (1.875rem) | 1.25 | 700 | hero title |
| `--foms-text-4xl` | 36px (2.25rem) | 1.2 | 700 | display |

```css
:root {
  --foms-font-size-xs:   0.75rem;
  --foms-font-size-sm:   0.875rem;
  --foms-font-size-base: 1rem;
  --foms-font-size-lg:   1.125rem;
  --foms-font-size-xl:   1.25rem;
  --foms-font-size-2xl:  1.5rem;
  --foms-font-size-3xl:  1.875rem;
  --foms-font-size-4xl:  2.25rem;

  --foms-line-height-tight:   1.25;
  --foms-line-height-snug:    1.4;
  --foms-line-height-normal:  1.55;
  --foms-line-height-relaxed: 1.7;

  --foms-font-weight-normal:   400;
  --foms-font-weight-medium:   500;
  --foms-font-weight-semibold: 600;
  --foms-font-weight-bold:     700;
}
```

### 3.3 모바일 base = 16px (iOS 줌 방지)

iOS Safari는 `<input>` font-size < 16px일 때 포커스 시 강제 줌. **모든 input·textarea·select에 최소 16px 강제.**

```css
input, textarea, select {
  font-size: max(16px, var(--foms-font-size-base));
}
```

### 3.4 Tabular Numbers

금액·일정 등 숫자 정렬이 중요한 곳:

```css
.foms-tabular {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}
```

---

## 4. 간격 (Spacing) — 4pt Grid

```css
:root {
  --foms-space-0:   0;
  --foms-space-1:   0.25rem;   /* 4px */
  --foms-space-2:   0.5rem;    /* 8px */
  --foms-space-3:   0.75rem;   /* 12px */
  --foms-space-4:   1rem;      /* 16px */
  --foms-space-5:   1.25rem;   /* 20px */
  --foms-space-6:   1.5rem;    /* 24px */
  --foms-space-8:   2rem;      /* 32px */
  --foms-space-10:  2.5rem;    /* 40px */
  --foms-space-12:  3rem;      /* 48px */
  --foms-space-16:  4rem;      /* 64px */
  --foms-space-20:  5rem;      /* 80px */
  --foms-space-24:  6rem;      /* 96px */
}
```

### 사용 가이드

| 위치 | 값 |
|---|---|
| 아이콘과 텍스트 사이 | `--foms-space-2` (8) |
| 카드 내부 패딩 (모바일) | `--foms-space-3` (12) |
| 카드 내부 패딩 (태블릿+) | `--foms-space-4` (16) |
| 카드 간 세로 간격 (모바일) | `--foms-space-3` (12) |
| 카드 간 세로 간격 (태블릿) | `--foms-space-4` (16) |
| 섹션 간 간격 (모바일) | `--foms-space-4` (16) |
| 섹션 간 간격 (태블릿) | `--foms-space-6` (24) |
| 페이지 좌우 여백 (모바일) | `--foms-space-4` (16) |
| 페이지 좌우 여백 (태블릿) | `--foms-space-6` (24) |

---

## 5. 라운드 (Radius)

```css
:root {
  --foms-radius-none: 0;
  --foms-radius-xs:   2px;
  --foms-radius-sm:   4px;   /* badge, chip */
  --foms-radius-md:   8px;   /* button, input, small card */
  --foms-radius-lg:   12px;  /* card, modal */
  --foms-radius-xl:   16px;  /* dialog */
  --foms-radius-2xl:  24px;
  --foms-radius-full: 9999px; /* pill, avatar */
}
```

| 컴포넌트 | 라운드 |
|---|---|
| Input·Select·Button | `--foms-radius-md` (8) |
| Card·Modal | `--foms-radius-lg` (12) |
| Badge·Chip | `--foms-radius-full` (pill) 또는 `--foms-radius-sm` (rectangular) |
| FAB | `--foms-radius-full` |
| Bottom nav 활성 indicator | `--foms-radius-md` |
| Image thumbnail | `--foms-radius-sm` |

---

## 6. 그림자 (Shadow / Elevation)

```css
:root {
  /* Light theme — soft, layered */
  --foms-shadow-xs:  0 1px 1px rgba(15, 17, 21, 0.04);
  --foms-shadow-sm:  0 1px 3px rgba(15, 17, 21, 0.06), 0 1px 2px rgba(15, 17, 21, 0.04);
  --foms-shadow-md:  0 4px 12px rgba(15, 17, 21, 0.08), 0 2px 4px rgba(15, 17, 21, 0.04);
  --foms-shadow-lg:  0 8px 24px rgba(15, 17, 21, 0.10), 0 4px 8px rgba(15, 17, 21, 0.06);
  --foms-shadow-xl:  0 16px 48px rgba(15, 17, 21, 0.14), 0 8px 16px rgba(15, 17, 21, 0.08);

  /* Inset for input focused / pressed state */
  --foms-shadow-inset-sm: inset 0 1px 2px rgba(15, 17, 21, 0.06);

  /* Focus ring */
  --foms-shadow-focus-ring: 0 0 0 3px rgba(90, 103, 216, 0.35);
  --foms-shadow-focus-ring-danger: 0 0 0 3px rgba(239, 68, 68, 0.35);
}

[data-theme="dark"] {
  --foms-shadow-xs: 0 1px 1px rgba(0, 0, 0, 0.5);
  --foms-shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.6), 0 1px 2px rgba(0, 0, 0, 0.4);
  --foms-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.6), 0 2px 4px rgba(0, 0, 0, 0.3);
  --foms-shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.6), 0 4px 8px rgba(0, 0, 0, 0.3);
  --foms-shadow-xl: 0 16px 48px rgba(0, 0, 0, 0.7), 0 8px 16px rgba(0, 0, 0, 0.4);
}
```

| 컴포넌트 | 그림자 |
|---|---|
| Card resting | `--foms-shadow-sm` |
| Card hovered/lifted | `--foms-shadow-md` |
| Bottom nav | `--foms-shadow-md` (역방향, 위로) |
| Modal·Drawer | `--foms-shadow-xl` |
| FAB | `--foms-shadow-lg` |
| Sticky action bar | `--foms-shadow-md` (위 방향) |
| Focused input | `--foms-shadow-focus-ring` (outline 대체) |

---

## 7. 모션 (Motion)

```css
:root {
  /* Duration */
  --foms-duration-instant:   0ms;
  --foms-duration-fast:      120ms;
  --foms-duration-default:   200ms;
  --foms-duration-slow:      320ms;
  --foms-duration-very-slow: 500ms;

  /* Easing (M3 emphasized) */
  --foms-ease-standard:    cubic-bezier(0.2, 0, 0, 1);
  --foms-ease-emphasized:  cubic-bezier(0.2, 0, 0, 1);
  --foms-ease-decel:       cubic-bezier(0, 0, 0, 1);
  --foms-ease-accel:       cubic-bezier(0.3, 0, 1, 1);
  --foms-ease-spring:      cubic-bezier(0.34, 1.56, 0.64, 1);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --foms-duration-fast: 0ms;
    --foms-duration-default: 0ms;
    --foms-duration-slow: 0ms;
    --foms-duration-very-slow: 0ms;
  }
}
```

| 인터랙션 | duration | easing |
|---|---|---|
| Hover state | `fast` (120) | `standard` |
| Button press | `fast` (120) | `accel` |
| Modal open | `default` (200) | `decel` |
| Modal close | `fast` (120) | `accel` |
| Drawer slide | `default` (200) | `emphasized` |
| Card swipe action | `slow` (320) | `spring` |
| Page transition | `default` (200) | `standard` |
| Toast appear | `default` (200) | `decel` |
| Toast disappear | `fast` (120) | `accel` |

### Page Transition (HTMX hx-boost)

```css
.foms-fragment-enter {
  opacity: 0;
  transform: translateY(8px);
}
.foms-fragment-enter-active {
  transition:
    opacity var(--foms-duration-default) var(--foms-ease-decel),
    transform var(--foms-duration-default) var(--foms-ease-decel);
  opacity: 1;
  transform: translateY(0);
}
```

---

## 8. Breakpoint

```css
:root {
  --foms-bp-sm: 576px;   /* 스마트폰 가로 */
  --foms-bp-md: 768px;   /* 태블릿 세로 시작 */
  --foms-bp-lg: 1024px;  /* 태블릿 가로 / split-view */
  --foms-bp-xl: 1280px;  /* 작은 데스크톱 */
  --foms-bp-2xl: 1536px; /* 큰 데스크톱 */
}
```

**사용 규칙**:
- Mobile-first 전략. 기본 스타일은 모바일.
- `@media (min-width: 768px)` 형식만 사용. `max-width` 금지 (예외: 기능 비활성화).
- 컴포넌트 내부 적응은 Container Query 우선.

### Container Query 활용 (2026 표준)

```css
.foms-queue-card {
  container-type: inline-size;
}

@container (min-width: 480px) {
  .foms-queue-card__layout {
    grid-template-columns: 1fr 1fr;
  }
}
```

---

## 9. Z-Index 레이어

```css
:root {
  --foms-z-base:        0;
  --foms-z-raised:      10;
  --foms-z-dropdown:    1000;
  --foms-z-sticky:      1020;  /* sticky header, filter */
  --foms-z-bottom-nav:  1030;  /* bottom nav */
  --foms-z-action-bar:  1040;  /* sticky CTA bar */
  --foms-z-fab:         1050;
  --foms-z-overlay:     1060;  /* backdrop */
  --foms-z-modal:       1070;
  --foms-z-toast:       1080;
  --foms-z-tooltip:     1090;
  --foms-z-max:         9999;
}
```

---

## 10. Safe Area & 셸 치수

```css
:root {
  /* Safe area inset (iPhone notch / 홈 인디케이터) */
  --foms-safe-area-top:    env(safe-area-inset-top, 0px);
  --foms-safe-area-bottom: env(safe-area-inset-bottom, 0px);
  --foms-safe-area-left:   env(safe-area-inset-left, 0px);
  --foms-safe-area-right:  env(safe-area-inset-right, 0px);

  /* Shell dimensions */
  --foms-shell-header-h:        48px;  /* 모바일 */
  --foms-shell-header-h-tablet: 56px;
  --foms-shell-bottom-nav-h:    60px;
  --foms-shell-side-tab-w:      72px;  /* 태블릿 가로 측면 탭 */
  --foms-shell-master-list-w:   360px; /* split-view 좌측 */
  --foms-shell-action-bar-h:    72px;
  --foms-shell-fab-size:        56px;
  --foms-shell-fab-offset:      var(--foms-space-4);

  /* Content max width */
  --foms-content-max-mobile:    600px;
  --foms-content-max-tablet:    900px;
  --foms-content-max-desktop:   1280px;
}
```

**Viewport meta (모든 페이지 적용)**:
```html
<meta name="viewport"
  content="width=device-width, initial-scale=1.0, viewport-fit=cover">
```

---

## 11. 터치 타깃

```css
:root {
  --foms-touch-target-min: 48px;   /* M3 권장 (HIG 44pt 초과) */
  --foms-touch-target-comfort: 56px;
  --foms-touch-target-large: 64px;
}

button, .foms-btn, .foms-tap-target {
  min-height: var(--foms-touch-target-min);
  min-width: var(--foms-touch-target-min);
}

/* 아이콘 전용 버튼은 44px 허용 */
.foms-icon-btn {
  min-height: 44px;
  min-width: 44px;
}
```

**터치 영역 확장** (시각 크기는 그대로, 터치는 크게):
```css
.foms-tap-extend::before {
  content: '';
  position: absolute;
  inset: -8px;
}
```

---

## 12. 아이콘 시스템

- **소스**: Lucide Icons (open source, MIT) — `https://lucide.dev`
- **크기**: 16 / 20 / 24 / 28 / 32px
- **두께**: 기본 1.75px (stroke-width)
- **렌더링**: 인라인 SVG (lazy-load 회피)
- **컬러**: `currentColor` 상속

```css
.foms-icon {
  display: inline-block;
  width: 1em;
  height: 1em;
  stroke-width: 1.75;
  stroke: currentColor;
  fill: none;
  vertical-align: -0.125em;
}
.foms-icon--sm { font-size: 16px; }
.foms-icon--md { font-size: 20px; }
.foms-icon--lg { font-size: 24px; }
.foms-icon--xl { font-size: 32px; }
```

---

## 13. 단계 배지 (Workflow Stage Badge)

```css
.foms-stage-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--foms-space-1);
  padding: 2px 8px;
  font-size: var(--foms-font-size-xs);
  font-weight: var(--foms-font-weight-semibold);
  border-radius: var(--foms-radius-sm);
  color: var(--foms-color-neutral-0);
  letter-spacing: -0.01em;
}
.foms-stage-badge--received     { background: var(--foms-stage-received); }
.foms-stage-badge--happycall    { background: var(--foms-stage-happycall); }
.foms-stage-badge--measure      { background: var(--foms-stage-measure); }
.foms-stage-badge--drawing      { background: var(--foms-stage-drawing); }
.foms-stage-badge--confirm      { background: var(--foms-stage-confirm); }
.foms-stage-badge--production   { background: var(--foms-stage-production); }
.foms-stage-badge--shipment     { background: var(--foms-stage-shipment); }
.foms-stage-badge--construction { background: var(--foms-stage-construction); }
.foms-stage-badge--cs           { background: var(--foms-stage-cs); }
.foms-stage-badge--completed    { background: var(--foms-stage-completed); }
```

---

## 14. 포커스 / 상태 표현

```css
:focus-visible {
  outline: none;
  box-shadow: var(--foms-shadow-focus-ring);
  border-radius: var(--foms-radius-md);
}

:disabled,
[aria-disabled="true"] {
  opacity: 1;  /* opacity 사용 금지 */
  color: var(--foms-text-disabled);
  background: var(--foms-color-neutral-100);
  cursor: not-allowed;
}
```

---

## 15. 토큰 적용 우선순위

CSS 작성 시 다음 순서로 값 검색:

1. `--foms-*` 시맨틱 토큰 (예: `--foms-text-primary`)
2. `--foms-*` 프리미티브 토큰 (예: `--foms-color-brand-500`)
3. 컴포넌트 로컬 변수 (`--card-padding`)
4. 하드코드 ❌ (PR reject)

```css
/* ✅ 좋은 예 */
.foms-card {
  background: var(--foms-surface-raised);
  color: var(--foms-text-primary);
  padding: var(--foms-space-3);
  border-radius: var(--foms-radius-lg);
  box-shadow: var(--foms-shadow-sm);
}

/* ❌ 나쁜 예 */
.foms-card {
  background: #f5f5f5;
  color: #1a1a1a;
  padding: 12px;
  border-radius: 12px;
}
```

---

## 16. 토큰 마이그레이션 체크리스트

P1 작업 시 다음 자동 검증:

- [ ] `static/css/foundation/foms-tokens.css` 단일 파일 생성
- [ ] 기존 `--erp-*` / `--wam-*` / `--erp-mobile-*` 사용처 grep → `--foms-*` 치환
- [ ] 하드코드 hex 색상 grep → 토큰 치환 (90% 이상)
- [ ] `!important` 사용 30% 이상 감소
- [ ] 다크모드 토큰 자동 적용 확인 (스크린샷 라이트/다크 diff)
- [ ] Lighthouse contrast audit 통과
- [ ] `data-theme="dark"` 속성 토글로 전체 화면 정상 표시

---

> 본 문서는 사용 가능한 모든 화면이 단일 토큰 시스템을 따른다는 가정 하에 작성된다. 마이그레이션 완료 전까지는 신규 코드만 본 시스템 강제, 기존 코드는 P1 작업에서 일괄 변환한다.
