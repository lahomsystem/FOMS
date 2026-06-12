# FOMS 모바일·태블릿 컴포넌트 라이브러리 (v1.1)

> 작성: 2026-05-28 | **v1.1 갱신: 2026-05-29** | 버전: 1.1
> 짝 문서: `MOBILE_TABLET_REDESIGN_PLAN.md`, `MOBILE_TABLET_DESIGN_SYSTEM.md`

**14개** 핵심 컴포넌트의 사양 (v1.1에서 C14 신규 추가). 각 컴포넌트는 Jinja2 macro 또는 partial로 구현하며, JS 인터랙션은 Vanilla JS + Alpine.js 점진 도입. CSS는 BEM 변형 (`foms-{block}__{element}--{modifier}`).

---

## C01. `<foms-app-shell>` — 통합 앱 셸

### 목적
헤더·바디·바텀탭·드로어·FAB을 하나의 셸 컴포넌트로 묶어 모든 페이지가 동일한 진입점을 갖게 한다. 기존 `erp_mobile_shell` + `channel/wam` 통합.

### 파일
- 템플릿: `templates/partials/shared/foms_app_shell.html`
- CSS: `static/css/foundation/foms-shell.css`
- JS: `static/js/runtime/foms-shell.js`

### Props (Jinja2 context)
| 이름 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `active_tab` | str | `'home'` | bottom nav 활성 탭 (`home`/`measure`/`production`/`construction`/`more`) |
| `page_title` | str | `''` | 상단 헤더 타이틀 |
| `show_search` | bool | `True` | 헤더 검색 아이콘 표시 |
| `show_back` | bool | `False` | 뒤로가기 버튼 |
| `back_url` | str | `''` | 뒤로가기 URL (없으면 history.back) |
| `action_bar_content` | str | `None` | sticky bottom action bar slot |
| `fab_url` | str | `None` | FAB 클릭 시 이동 URL |
| `fab_icon` | str | `'plus'` | FAB 아이콘 |
| `disable_bottom_nav` | bool | `False` | 모달·검색 오버레이에서 |

### 레이아웃
```
┌──────────────────────────────────┐
│  Header (sticky)                 │  ← C01a
├──────────────────────────────────┤
│  Filter chips strip (sticky?)    │  ← optional slot
├──────────────────────────────────┤
│                                  │
│  Body (scrollable)               │  ← block content
│                                  │
├──────────────────────────────────┤
│  Sticky Action Bar               │  ← C08 (optional)
├──────────────────────────────────┤
│  Bottom Nav                      │  ← C02
└──────────────────────────────────┘
                            (+)        ← C-FAB
```

### 반응형

- `≤767px`: 모바일 — 그대로
- `768~1023px`: 태블릿 세로 — 본문 max-width 600px, 중앙 정렬
- `≥1024px`: 태블릿 가로 — Bottom nav → 측면 탭(C03)로 회전, 본문 split-view (C04+상세)
- `≥1280px`: 데스크톱 — 기존 PC 셸 유지 (점진 전환)

### Container Query
```css
.foms-app-shell {
  container-type: inline-size;
  container-name: shell;
}
@container shell (min-width: 1024px) {
  .foms-app-shell__bottom-nav { display: none; }
  .foms-app-shell__side-tab   { display: flex; }
  .foms-app-shell__body       { display: grid; grid-template-columns: 360px 1fr; }
}
```

---

## C02. `<foms-bottom-nav>` — 하단 5탭 + 배지

### 목적
ERP 워크플로우 그룹 5탭 + 미처리 건수 배지. 모바일·태블릿 세로의 primary 네비.

### 파일
- 템플릿: `templates/partials/shared/foms_bottom_nav.html`

### Props
| 이름 | 타입 | 기본값 |
|---|---|---|
| `active` | str | `'home'` |
| `badge_counts` | dict | `{}` |

`badge_counts` 예시 (`context_processor`에서 주입):
```python
{
  'home': 12,        # 미처리 RECEIVED + HAPPYCALL
  'measure': 5,      # 오늘 실측 일정
  'production': 8,   # 출고 임박
  'construction': 3, # 오늘 시공
  'more': 0,         # 알림
}
```

### 마크업
```html
<nav class="foms-bottom-nav" role="navigation" aria-label="주요 메뉴">
  <a href="{{ url_for('erp_dashboard.erp_dashboard') }}"
     class="foms-bottom-nav__item {{ 'is-active' if active == 'home' }}"
     aria-current="{{ 'page' if active == 'home' }}">
    <span class="foms-bottom-nav__icon"><svg>...</svg></span>
    <span class="foms-bottom-nav__label">홈</span>
    {% if badge_counts.get('home', 0) > 0 %}
    <span class="foms-bottom-nav__badge" aria-label="{{ badge_counts['home'] }}건 미처리">
      {{ badge_counts['home'] if badge_counts['home'] < 100 else '99+' }}
    </span>
    {% endif %}
  </a>
  <!-- 나머지 4탭 동일 구조 -->
</nav>
```

### CSS 핵심
```css
.foms-bottom-nav {
  position: fixed;
  inset: auto 0 0 0;
  height: calc(var(--foms-shell-bottom-nav-h) + var(--foms-safe-area-bottom));
  padding-bottom: var(--foms-safe-area-bottom);
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  background: var(--foms-surface-base);
  border-top: 1px solid var(--foms-border-subtle);
  box-shadow: 0 -2px 12px rgba(15, 17, 21, 0.06);
  z-index: var(--foms-z-bottom-nav);
}
.foms-bottom-nav__item {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 4px;
  font-size: var(--foms-font-size-xs);
  color: var(--foms-text-tertiary);
  text-decoration: none;
  position: relative;
  min-height: var(--foms-touch-target-min);
}
.foms-bottom-nav__item.is-active {
  color: var(--foms-interactive-primary);
  font-weight: var(--foms-font-weight-semibold);
}
.foms-bottom-nav__badge {
  position: absolute;
  top: 6px; right: calc(50% - 22px);
  min-width: 18px; height: 18px;
  padding: 0 5px;
  background: var(--foms-color-danger-500);
  color: white;
  font-size: 11px; font-weight: 700;
  border-radius: var(--foms-radius-full);
  display: flex; align-items: center; justify-content: center;
}
```

### Context Processor 추가 (구현)
`foms/services/context_processors.py`:
```python
@app.context_processor
def inject_foms_nav_badges():
    if request.endpoint and request.endpoint.startswith('erp_'):
        return {
            'foms_nav_badges': compute_stage_counts(current_user)
        }
    return {}
```

---

## C03. `<foms-side-tab>` — 태블릿 가로 측면 탭

### 목적
1024px+ 가로 모드에서 Bottom nav 대신 좌측 72px 측면 탭.

### 레이아웃
```
┌────┬─────────────┬────────────────┐
│ 홈 │  Master     │  Detail        │
│ 실 │   List      │                │
│ 생 │   (360)     │                │
│ 시 │             │                │
│ … │             │                │
└────┴─────────────┴────────────────┘
```

### 마크업
```html
<aside class="foms-side-tab" role="navigation" aria-label="주요 메뉴">
  <a href="..." class="foms-side-tab__item is-active">
    <span class="foms-side-tab__icon"><svg>...</svg></span>
    <span class="foms-side-tab__label">홈</span>
    <span class="foms-side-tab__badge">12</span>
  </a>
  ...
</aside>
```

### CSS
```css
.foms-side-tab {
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--foms-shell-side-tab-w);
  padding-top: calc(var(--foms-shell-header-h-tablet) + var(--foms-safe-area-top));
  background: var(--foms-surface-raised);
  border-right: 1px solid var(--foms-border-subtle);
  display: none;  /* container query로 활성화 */
  flex-direction: column;
  z-index: var(--foms-z-bottom-nav);
}
```

---

## C04. `<foms-master-list>` — 가로 split 좌측 360px 리스트

### 목적
태블릿 가로(≥1024px) split-view에서 좌측 360px 마스터 리스트. 카드 선택 시 우측 패널에 상세 로드.

### 마크업
```html
<section class="foms-master-list" data-current-id="{{ current_order_id }}">
  <header class="foms-master-list__header">
    <input type="search" class="foms-search-input" placeholder="검색..." />
    <button class="foms-icon-btn" aria-label="필터">⏷</button>
  </header>
  <div class="foms-master-list__chips">
    <button class="foms-chip is-active">전체</button>
    <button class="foms-chip">오늘</button>
    <button class="foms-chip">미처리</button>
  </div>
  <div class="foms-master-list__items" data-hx-trigger="revealed" data-hx-get="/api/orders/queue">
    {% for order in orders %}
      {% include 'partials/shared/foms_queue_card.html' %}
    {% endfor %}
  </div>
</section>
```

### 인터랙션
- 카드 클릭: HTMX `hx-get="/orders/{id}/detail"` `hx-target="#foms-detail-panel"`
- 키보드: ↑↓로 카드 이동, Enter로 선택, `j/k` Vim 단축키
- 카드 선택 시 `aria-current="true"` + 좌측 4px 보더 강조

---

## C05. `<foms-queue-card>` — 주문 카드 (다목적)

### 목적
모든 워크플로우 단계의 주문을 표현하는 단일 카드 컴포넌트. 컨텍스트(어느 페이지)에 따라 표시 정보를 조정.

### 파일
- 매크로: `templates/partials/shared/foms_queue_card.html`

### Props
| 이름 | 타입 | 기본 |
|---|---|---|
| `order` | Order | required |
| `variant` | str | `'default'` (`'default'`/`'compact'`/`'detail-preview'`) |
| `show_attachments` | bool | True |
| `show_next_action` | bool | True |
| `swipe_actions` | list | `[]` (e.g. `['approve', 'reject']`) |

### 마크업 (default)
```html
<article class="foms-queue-card" data-order-id="{{ order.id }}"
         data-stage="{{ order.stage }}"
         tabindex="0" role="article">
  <header class="foms-queue-card__head">
    <span class="foms-stage-badge foms-stage-badge--{{ order.stage|lower }}">
      {{ order.stage_display }}
    </span>
    {% if order.alerts %}
      <span class="foms-queue-card__alert" aria-label="경보">
        <svg class="foms-icon foms-icon--sm">...</svg>
        {{ order.alerts[0].label }}
      </span>
    {% endif %}
    <time class="foms-queue-card__time">{{ order.next_milestone|format_time }}</time>
  </header>

  <h3 class="foms-queue-card__title">
    {{ order.customer_name }}
    <span class="foms-queue-card__subtitle">{{ order.product_name }}</span>
  </h3>

  <dl class="foms-queue-card__meta">
    <div>
      <dt>주소</dt>
      <dd>
        <a href="https://map.kakao.com/?q={{ order.address|urlencode }}"
           class="foms-deeplink">{{ order.address|truncate(28) }}</a>
      </dd>
    </div>
    <div>
      <dt>연락처</dt>
      <dd><a href="tel:{{ order.phone }}" class="foms-deeplink">{{ order.phone }}</a></dd>
    </div>
    <div>
      <dt>일정</dt>
      <dd class="foms-tabular">{{ order.next_milestone_date|format_kr_date }}</dd>
    </div>
  </dl>

  {% if show_attachments and order.attachments %}
  <div class="foms-queue-card__attachments">
    {% for att in order.attachments[:3] %}
    <button class="foms-queue-card__thumb" data-attachment-id="{{ att.id }}"
            data-zoom="{{ att.url }}">
      <img src="{{ att.thumbnail_url(160) }}" alt="" loading="lazy" />
    </button>
    {% endfor %}
    {% if order.attachments|length > 3 %}
    <span class="foms-queue-card__thumb-more">+{{ order.attachments|length - 3 }}</span>
    {% endif %}
  </div>
  {% endif %}

  {% if show_next_action and order.next_action %}
  <footer class="foms-queue-card__action">
    <a href="{{ order.next_action.url }}" class="foms-btn foms-btn--primary foms-btn--sm">
      {{ order.next_action.label }}
    </a>
  </footer>
  {% endif %}
</article>
```

### CSS 핵심
```css
.foms-queue-card {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--foms-space-2);
  padding: var(--foms-space-3);
  background: var(--foms-surface-raised);
  border-radius: var(--foms-radius-lg);
  box-shadow: var(--foms-shadow-sm);
  transition: box-shadow var(--foms-duration-fast) var(--foms-ease-standard);
  container-type: inline-size;
}
.foms-queue-card:focus-visible,
.foms-queue-card[aria-current="true"] {
  outline: none;
  box-shadow: var(--foms-shadow-focus-ring);
  border-left: 4px solid var(--foms-interactive-primary);
}
.foms-queue-card__head {
  display: flex; align-items: center; gap: var(--foms-space-2);
}
.foms-queue-card__title {
  font-size: var(--foms-font-size-lg);
  font-weight: var(--foms-font-weight-semibold);
  margin: 0;
}
.foms-queue-card__subtitle {
  display: block;
  font-size: var(--foms-font-size-sm);
  font-weight: var(--foms-font-weight-normal);
  color: var(--foms-text-secondary);
}
.foms-queue-card__meta {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--foms-space-1);
  margin: 0;
  font-size: var(--foms-font-size-sm);
}
.foms-queue-card__meta dt {
  font-size: var(--foms-font-size-xs);
  color: var(--foms-text-tertiary);
  margin: 0;
}
.foms-queue-card__meta dd { margin: 0; }
.foms-queue-card__attachments {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--foms-space-2);
}
.foms-queue-card__thumb {
  aspect-ratio: 1;
  border-radius: var(--foms-radius-sm);
  overflow: hidden;
  background: var(--foms-surface-overlay);
}
.foms-queue-card__action {
  display: flex; justify-content: flex-end;
  margin-top: var(--foms-space-2);
}

@container (min-width: 480px) {
  .foms-queue-card__meta {
    grid-template-columns: 1fr 1fr;
  }
}
```

### Swipe Action (P2)
```js
// Hammer.js 또는 자체 구현
import { initSwipeActions } from '/static/js/foms/swipe-actions.js';
initSwipeActions('.foms-queue-card[data-swipe="true"]', {
  left:  { label: '승인', action: approveOrder, color: 'success' },
  right: { label: '반려', action: rejectOrder, color: 'danger' },
});
```

---

## C06. `<foms-kv-row>` — Key-Value 행 (딥링크 통합)

### 목적
주문 상세에서 라벨-값 쌍을 표시하는 단일 컴포넌트. 전화·주소·복사·이메일 딥링크 통합.

### 매크로
```jinja2
{% macro foms_kv_row(label, value, deeplink=None, copyable=False, mono=False) %}
<div class="foms-kv-row">
  <dt class="foms-kv-row__label">{{ label }}</dt>
  <dd class="foms-kv-row__value {{ 'foms-kv-row__value--mono' if mono }}">
    {% if deeplink == 'tel' %}
      <a href="tel:{{ value }}" class="foms-deeplink">{{ value }}</a>
      <button class="foms-icon-btn foms-icon-btn--sm" data-copy="{{ value }}"
              aria-label="번호 복사"><svg>...</svg></button>
    {% elif deeplink == 'map' %}
      <a href="https://map.kakao.com/?q={{ value|urlencode }}" class="foms-deeplink">
        {{ value }}
      </a>
      <button class="foms-icon-btn foms-icon-btn--sm" data-copy="{{ value }}"
              aria-label="주소 복사"><svg>...</svg></button>
    {% elif deeplink == 'mail' %}
      <a href="mailto:{{ value }}" class="foms-deeplink">{{ value }}</a>
    {% elif copyable %}
      {{ value }}
      <button class="foms-icon-btn foms-icon-btn--sm" data-copy="{{ value }}"
              aria-label="복사"><svg>...</svg></button>
    {% else %}
      {{ value }}
    {% endif %}
  </dd>
</div>
{% endmacro %}
```

### CSS
```css
.foms-kv-row {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: var(--foms-space-3);
  padding: var(--foms-space-3) 0;
  border-bottom: 1px solid var(--foms-border-subtle);
  align-items: center;
}
.foms-kv-row__label {
  font-size: var(--foms-font-size-sm);
  color: var(--foms-text-tertiary);
  margin: 0;
}
.foms-kv-row__value {
  font-size: var(--foms-font-size-base);
  color: var(--foms-text-primary);
  margin: 0;
  display: flex; align-items: center; gap: var(--foms-space-2);
}
.foms-kv-row__value--mono { font-family: var(--foms-font-mono); }
.foms-deeplink {
  color: var(--foms-text-link);
  text-decoration: underline;
  text-underline-offset: 2px;
}
```

---

## C07. `<foms-attachment-grid>` — 첨부 그리드 + 라이트박스

### 목적
사진·도면 썸네일 그리드 + pinch-zoom 라이트박스. 사진 = 1급 데이터 원칙.

### 매크로
```jinja2
{% macro foms_attachment_grid(attachments, gallery_id) %}
<div class="foms-attachment-grid" data-gallery-id="{{ gallery_id }}">
  {% for att in attachments %}
  <button class="foms-attachment-grid__item"
          data-zoom-src="{{ att.url }}"
          data-zoom-caption="{{ att.title or att.filename }}"
          data-zoom-meta="{{ att.created_at|format_kr_datetime }}{% if att.location %} · {{ att.location }}{% endif %}">
    <img src="{{ att.thumbnail_url(320) }}"
         srcset="{{ att.thumbnail_url(320) }} 1x,
                 {{ att.thumbnail_url(640) }} 2x"
         alt="{{ att.alt_text or att.filename }}"
         loading="lazy" decoding="async" />
    {% if att.is_video %}
    <span class="foms-attachment-grid__icon"><svg>▶</svg></span>
    {% endif %}
  </button>
  {% endfor %}
  <button class="foms-attachment-grid__add" type="button" data-action="add-attachment">
    <svg class="foms-icon foms-icon--lg">+</svg>
    <span>추가</span>
  </button>
</div>
{% endmacro %}
```

### 라이트박스 JS (`/static/js/foms/lightbox.js`)
```js
// Vanilla, no deps. Pinch-zoom via touch events + CSS transform.
class FOMSLightbox {
  constructor(galleryId) { /* ... */ }
  open(index) { /* ... */ }
  enableZoom() { /* pinch + double-tap + wheel */ }
  enableSwipeNav() { /* swipe left/right between images */ }
}
document.querySelectorAll('[data-gallery-id]').forEach(g => new FOMSLightbox(g.dataset.galleryId));
```

---

## C08. `<foms-sticky-action-bar>` — Sticky CTA Bar

### 목적
모달·폼·상세 페이지 하단에 고정되는 액션 바. 키보드가 올라와도 visible.

### 마크업
```html
<footer class="foms-sticky-action-bar" role="region" aria-label="주요 작업">
  <button type="button" class="foms-btn foms-btn--secondary">취소</button>
  <button type="submit" class="foms-btn foms-btn--primary foms-btn--lg">저장</button>
</footer>
```

### CSS
```css
.foms-sticky-action-bar {
  position: sticky;
  bottom: 0;
  inset-inline: 0;
  display: flex; gap: var(--foms-space-3);
  padding: var(--foms-space-3) var(--foms-space-4)
           calc(var(--foms-space-3) + var(--foms-safe-area-bottom));
  background: var(--foms-surface-base);
  border-top: 1px solid var(--foms-border-subtle);
  box-shadow: 0 -4px 12px rgba(15, 17, 21, 0.06);
  z-index: var(--foms-z-action-bar);
}
.foms-sticky-action-bar > .foms-btn { flex: 1; }
.foms-sticky-action-bar > .foms-btn--primary { flex: 2; }

/* 키보드 visible 시 viewport 변화 대응 */
.foms-sticky-action-bar {
  bottom: env(keyboard-inset-height, 0);
}
```

### Visual Viewport API 통합 (P1)
```js
if ('visualViewport' in window) {
  visualViewport.addEventListener('resize', () => {
    document.documentElement.style.setProperty(
      '--foms-keyboard-h',
      `${innerHeight - visualViewport.height}px`
    );
  });
}
```

---

## C09. `<foms-wizard-stepper>` — 4-step Wizard

### 목적
신규 주문 작성 4단계 마법사. 진행률 + 단계 표시 + 이전/다음.

### 마크업
```html
<div class="foms-wizard" data-current-step="1" data-total-steps="4">
  <header class="foms-wizard__header">
    <button class="foms-icon-btn" data-action="back" aria-label="이전">
      <svg>‹</svg>
    </button>
    <progress class="foms-wizard__progress" max="4" value="1"></progress>
    <span class="foms-wizard__counter">1 / 4</span>
  </header>

  <h1 class="foms-wizard__title">기본 정보</h1>
  <p class="foms-wizard__subtitle">고객님의 기본 정보를 입력해주세요</p>

  <div class="foms-wizard__body">
    <!-- step content -->
  </div>

  <footer class="foms-sticky-action-bar">
    <button type="button" class="foms-btn foms-btn--secondary" data-action="prev"
            disabled>이전</button>
    <button type="button" class="foms-btn foms-btn--primary foms-btn--lg"
            data-action="next">다음</button>
  </footer>
</div>
```

### State Management (Alpine.js)
```html
<div x-data="{
  step: 1,
  total: 4,
  data: { customer_name: '', phone: '', ... },
  next() { if (this.validate()) this.step++ },
  prev() { this.step-- },
  validate() { /* per-step rules */ },
  save() { /* fetch POST */ }
}" class="foms-wizard">
  ...
</div>
```

### 자동저장 (`/static/js/foms/draft.js`)
```js
class FOMSDraft {
  constructor(formId, autoSaveInterval = 5000) { /* ... */ }
  save() { localStorage.setItem(this.key(), JSON.stringify(this.collect())); }
  load() { return JSON.parse(localStorage.getItem(this.key()) || 'null'); }
  prompt() {
    if (this.load()) {
      // 토스트로 "복구하시겠습니까?" UI 표시
    }
  }
}
```

---

## C10. `<foms-filter-drawer>` — offcanvas 필터

### 목적
오프캔버스 슬라이드업 필터. 적용 시 필터 칩(헤더에 sticky)이 활성화 상태 visible.

### 마크업 (Bootstrap 5 offcanvas 활용)
```html
<button class="foms-icon-btn" data-bs-toggle="offcanvas"
        data-bs-target="#foms-filter-drawer" aria-label="필터">
  <svg>⏷</svg>
  {% if active_filter_count > 0 %}
  <span class="foms-icon-btn__dot"></span>
  {% endif %}
</button>

<div class="offcanvas offcanvas-bottom foms-filter-drawer"
     id="foms-filter-drawer" tabindex="-1">
  <div class="offcanvas-header">
    <h2 class="offcanvas-title">필터</h2>
    <button class="btn-close" data-bs-dismiss="offcanvas" aria-label="닫기"></button>
  </div>
  <form class="offcanvas-body" method="get">
    <fieldset>
      <legend>단계</legend>
      <!-- chip group -->
    </fieldset>
    <fieldset>
      <legend>기간</legend>
      <!-- date range -->
    </fieldset>
    <fieldset>
      <legend>담당</legend>
      <!-- multi-select -->
    </fieldset>
  </form>
  <footer class="foms-sticky-action-bar">
    <button type="reset" class="foms-btn foms-btn--secondary">초기화</button>
    <button type="submit" class="foms-btn foms-btn--primary foms-btn--lg">적용</button>
  </footer>
</div>
```

---

## C11. `<foms-search-overlay>` — 풀스크린 검색

### 목적
헤더 검색 아이콘 탭 시 풀스크린 오버레이. 키보드 즉시 포커스 + 자동완성.

### 마크업
```html
<dialog class="foms-search-overlay" id="foms-search">
  <header class="foms-search-overlay__head">
    <button class="foms-icon-btn" data-action="close" aria-label="닫기">‹</button>
    <input type="search" class="foms-search-input"
           placeholder="고객명, 전화번호, 주소, 주문번호..."
           autofocus enterkeyhint="search" />
    <button class="foms-icon-btn" data-action="clear" aria-label="지우기">✕</button>
  </header>

  <div class="foms-search-overlay__body">
    <section class="foms-search-overlay__recent">
      <h3>최근 검색</h3>
      <ul>
        <li><a href="#">고명옥</a></li>
        <li><a href="#">010-2690-2242</a></li>
      </ul>
    </section>
    <section class="foms-search-overlay__results" hidden>
      <nav class="foms-search-overlay__tabs">
        <button class="is-active">전체</button>
        <button>고객</button>
        <button>주문</button>
        <button>도면</button>
      </nav>
      <ul class="foms-search-overlay__items">
        <!-- HTMX hx-trigger="input delay:200ms" -->
      </ul>
    </section>
  </div>
</dialog>
```

### CSS
```css
.foms-search-overlay {
  position: fixed; inset: 0;
  width: 100vw; height: 100dvh;
  margin: 0; padding: 0;
  max-width: none; max-height: none;
  border: none; background: var(--foms-surface-base);
  z-index: var(--foms-z-modal);
}
.foms-search-overlay::backdrop {
  background: rgba(15, 17, 21, 0.4);
}
```

---

## C12. `<foms-photo-capture>` — 사진 캡처 (카메라 우선)

### 목적
AS 접수·사진 첨부의 단일 컴포넌트. 카메라 직접 캡처 우선 + 갤러리 + paste 보조.

### 마크업
```html
<div class="foms-photo-capture" data-target-input="attachments">
  <div class="foms-photo-capture__actions">
    <label class="foms-btn foms-btn--primary foms-btn--lg foms-btn--full">
      <svg class="foms-icon foms-icon--md">📷</svg>
      사진 촬영
      <input type="file" accept="image/*" capture="environment" multiple hidden
             data-action="capture" />
    </label>
    <label class="foms-btn foms-btn--secondary foms-btn--md">
      <svg class="foms-icon foms-icon--sm">🖼</svg>
      갤러리
      <input type="file" accept="image/*,video/*" multiple hidden
             data-action="gallery" />
    </label>
    <button type="button" class="foms-btn foms-btn--secondary foms-btn--md"
            data-action="paste" data-show-on="desktop">
      <svg class="foms-icon foms-icon--sm">📋</svg>
      붙여넣기
    </button>
  </div>

  <div class="foms-photo-capture__preview" data-empty="true">
    <p class="foms-photo-capture__empty-hint">아직 첨부된 파일이 없습니다</p>
    <!-- 첨부 시 동적으로 썸네일 추가 -->
  </div>
</div>
```

### JS (`/static/js/foms/photo-capture.js`)
```js
class FOMSPhotoCapture {
  constructor(root) {
    this.root = root;
    this.input = root.querySelector(`[name="${root.dataset.targetInput}"]`);
    this.preview = root.querySelector('.foms-photo-capture__preview');
    this.files = [];
    this.bindEvents();
  }
  bindEvents() {
    this.root.querySelectorAll('input[type="file"]').forEach(i => {
      i.addEventListener('change', e => this.addFiles(e.target.files));
    });
    // Paste (desktop only)
    if (matchMedia('(pointer: fine)').matches) {
      this.root.addEventListener('paste', e => this.handlePaste(e));
    }
    // Drag & drop (desktop)
    this.root.addEventListener('dragover', e => e.preventDefault());
    this.root.addEventListener('drop', e => {
      e.preventDefault();
      this.addFiles(e.dataTransfer.files);
    });
  }
  addFiles(fileList) { /* preview + collect */ }
  handlePaste(e) {
    const items = e.clipboardData?.items || [];
    const files = [...items].filter(i => i.kind === 'file').map(i => i.getAsFile());
    if (files.length) this.addFiles(files);
  }
}
```

---

## C13. `<foms-status-badge>` — 단계·경보 배지 표준화

### 목적
워크플로우 단계, 알림 종류, 우선순위를 표현하는 단일 배지.

### 마크업
```html
<!-- 워크플로우 단계 -->
<span class="foms-badge foms-badge--stage foms-badge--stage-measure">실측</span>

<!-- 경보 -->
<span class="foms-badge foms-badge--alert foms-badge--alert-overdue">
  <svg class="foms-icon foms-icon--sm">⏰</svg> 지연
</span>

<!-- 우선순위 -->
<span class="foms-badge foms-badge--priority foms-badge--priority-high">긴급</span>

<!-- 숫자 카운트 -->
<span class="foms-badge foms-badge--count">28</span>

<!-- 닷 (상태 표시) -->
<span class="foms-badge foms-badge--dot foms-badge--dot-online" aria-label="온라인"></span>
```

### CSS 기본
```css
.foms-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px;
  font-size: var(--foms-font-size-xs);
  font-weight: var(--foms-font-weight-semibold);
  border-radius: var(--foms-radius-sm);
  letter-spacing: -0.01em;
  line-height: 1.4;
}
.foms-badge--dot {
  width: 8px; height: 8px;
  padding: 0;
  border-radius: var(--foms-radius-full);
}
.foms-badge--count {
  background: var(--foms-color-danger-500);
  color: white;
  min-width: 20px;
  height: 20px;
  border-radius: var(--foms-radius-full);
  justify-content: center;
}
```

---

## C14. `<foms-product-item-accordion>` — 제품 항목 인라인 편집 (v1.1 신규)

### 목적
주문 상세에서 erporder 제품 항목(N개)을 다중 표시하고, CS 부서 등록 후 **실측 시 영업·실측 담당자가 모바일에서 즉시 인라인 편집** 가능하도록 한다. erporder의 12필드 + spec_rows 다중 행을 모바일 친화적으로 표현.

### 파일
- 매크로: `templates/macros/foms_product_item.html`
- CSS: `static/css/components/foms-product-item.css`
- JS: `static/js/foms/product-item.js`
- API: `foms/api/erp_orders_structured.py` (기존 PATCH 활용)

### 사용 시나리오 (S6 — 실측 워크플로우)
1. CS 부서: 고객 정보 + 대략적 제품명 + "상담" 기본값으로 주문 등록
2. 영업·실측 담당: 현장 방문, 실제 W·D·H 측정
3. 모바일에서 주문 상세 → 제품 항목 카드 펼침 → spec_rows 입력
4. blur 시 즉시 PATCH → "✓ 저장됨" 토스트 → 도면팀이 즉시 데이터 활용

### erporder 12필드 매핑
| FOMS field | erporder data-erp attr | UI |
|---|---|---|
| product_name | `data-erp="product_name"` | text input |
| spec_rows[] (W·D·H 분리) | `data-erp="spec_width/depth/height"` | 3분리 input + "+ 행 추가" |
| internal | `data-erp="internal"` | text input (기본 "상담") |
| color | `data-erp="color"` | text input |
| option_detail | `data-erp="option_detail"` | text input |
| handle | `data-erp="handle"` | text input |
| misc | `data-erp="misc"` | text input |
| price | `data-erp="price"` | numeric input (tabular) |
| measurement_date | `data-erp="measurement_date"` | date picker |
| construction_date | `data-erp="construction_date"` | date picker |
| extra_input | `data-erp="extra_input"` | textarea |
| attachments[] | `erp-item-attachments-input` | photo grid + capture |

### Props (Jinja2 매크로)
```jinja2
{% macro foms_product_item(item, idx, order_id, can_edit=true, collapsed=false) %}
  ...
{% endmacro %}
```

| Prop | 타입 | 기본 |
|---|---|---|
| `item` | dict | required (structured_data items[idx]) |
| `idx` | int | required |
| `order_id` | int | required |
| `can_edit` | bool | true (권한 체크) |
| `collapsed` | bool | false (첫 항목 펼침, 나머지 접힘 권장) |

### 마크업 (펼친 상태)
```html
<article class="foms-product-item" data-item-idx="{{ idx }}" data-order-id="{{ order_id }}">
  <header class="foms-product-item__head" role="button" aria-expanded="true">
    <span class="foms-product-item__index">항목 {{ idx + 1 }}</span>
    <span class="foms-product-item__title">{{ item.product_name or '제품명 미입력' }}</span>
    <button class="foms-product-item__expand" aria-label="접기">⌃</button>
  </header>

  <div class="foms-product-item__body">
    <!-- 규격 (W·D·H 다중 행) -->
    <div class="foms-spec-block">
      <span class="foms-spec-block__lbl">규격 (폭·깊이·높이)</span>
      <div class="foms-spec-rows" data-erp-collection="spec_rows">
        {% for sr in item.spec_rows %}
        <div class="foms-spec-row" data-spec-idx="{{ loop.index0 }}">
          <span class="foms-spec-row__num">{{ loop.index }}</span>
          <div class="foms-spec-row__field">
            <span class="foms-spec-row__sublbl">W</span>
            <input class="foms-spec-row__input foms-tabular"
                   inputmode="numeric" value="{{ sr.spec_width }}"
                   data-erp="spec_width" data-spec-row />
          </div>
          <div class="foms-spec-row__field">
            <span class="foms-spec-row__sublbl">D</span>
            <input class="foms-spec-row__input foms-tabular"
                   inputmode="numeric" value="{{ sr.spec_depth }}"
                   data-erp="spec_depth" data-spec-row />
          </div>
          <div class="foms-spec-row__field">
            <span class="foms-spec-row__sublbl">H</span>
            <input class="foms-spec-row__input foms-tabular"
                   inputmode="numeric" value="{{ sr.spec_height }}"
                   data-erp="spec_height" data-spec-row />
          </div>
          {% if item.spec_rows|length > 1 %}
          <button class="foms-icon-btn foms-icon-btn--sm" data-action="remove-spec-row"
                  aria-label="규격 행 삭제">−</button>
          {% endif %}
        </div>
        {% endfor %}
      </div>
      <button class="foms-btn foms-btn--ghost foms-btn--sm" data-action="add-spec-row">
        ＋ 규격 1행 추가
      </button>
    </div>

    <!-- 인라인 KV (8개 필드) -->
    <dl class="foms-product-kv">
      {{ foms_kv_inline(label='내부', value=item.internal, field='internal') }}
      {{ foms_kv_inline(label='색상', value=item.color, field='color') }}
      {{ foms_kv_inline(label='옵션', value=item.option_detail, field='option_detail') }}
      {{ foms_kv_inline(label='손잡이', value=item.handle, field='handle') }}
      {{ foms_kv_inline(label='기타·설치', value=item.misc, field='misc') }}
      {{ foms_kv_inline(label='금액', value=item.price, field='price',
                       critical=true, suffix='원', mono=true) }}
      {{ foms_kv_inline(label='실측일', value=item.measurement_date,
                       field='measurement_date', type='date') }}
      {{ foms_kv_inline(label='시공일', value=item.construction_date,
                       field='construction_date', type='date', critical=true) }}
    </dl>

    <!-- 추가 입력 -->
    <div class="foms-field">
      <label class="foms-field__label">추가 입력</label>
      <textarea class="foms-textarea" data-erp="extra_input" rows="2">{{ item.extra_input }}</textarea>
    </div>

    <!-- 항목별 첨부 -->
    {{ foms_attachment_grid(item.attachments, gallery_id='item-' + idx|string, item_idx=idx) }}

    <!-- 자동저장 인디케이터 -->
    <div class="foms-product-item__autosave" aria-live="polite">
      <span class="foms-product-item__autosave-dot"></span>
      <span class="foms-product-item__autosave-text">실측 변경 즉시 저장됨</span>
    </div>
  </div>
</article>
```

### 마크업 (접힌 상태 — 요약만)
```html
<article class="foms-product-item foms-product-item--collapsed">
  <header class="foms-product-item__head" role="button" aria-expanded="false">
    <span class="foms-product-item__index">항목 {{ idx + 1 }}</span>
    <span class="foms-product-item__title">{{ item.product_name }}</span>
    <button class="foms-product-item__expand" aria-label="펼치기">⌄</button>
  </header>
  <div class="foms-product-item__summary">
    {{ format_spec_summary(item.spec_rows) }} ·
    {{ item.color }} ·
    {{ item.handle }} ·
    <span class="foms-tabular">{{ item.price|format_currency }}원</span>
  </div>
</article>
```

### Critical Field 명시 저장 (D07 v1.1 보정)
- Non-critical (색상·옵션·손잡이·기타·내부·메모): blur 즉시 PATCH + 토스트 "저장됨"
- **Critical** (금액·시공일·실측일·고객 연락처): 명시 "✓ 저장" 버튼 + undo 5초

```js
const CRITICAL_FIELDS = new Set(['price', 'construction_date', 'measurement_date']);

class FOMSProductItem {
  constructor(root) { /* ... */ }
  onFieldBlur(field, value) {
    if (CRITICAL_FIELDS.has(field)) {
      this.showSaveButton(field);
    } else {
      this.patchDebounced(field, value);
    }
  }
  patchDebounced(field, value) {
    clearTimeout(this._patchTimer);
    this._patchTimer = setTimeout(() => this.patch(field, value), 200);
  }
  async patch(field, value) {
    const response = await fetch(`/api/orders/${this.orderId}/erp`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-If-Match': this.lastUpdatedAt,
      },
      body: JSON.stringify({
        items: [{ idx: this.idx, [field]: value }]
      })
    });
    if (response.status === 409) {
      this.showConflictDialog(await response.json());
      return;
    }
    const data = await response.json();
    this.lastUpdatedAt = data.updated_at;
    this.showToast('저장됨');
  }
}
```

### structured_data JSONB 수정 (CLAUDE.md 패턴 준수)

서버 측 PATCH 처리:
```python
import copy
from sqlalchemy.orm.attributes import flag_modified

@bp.patch('/orders/<int:order_id>/erp')
def patch_erp_order(order_id):
    order = Order.query.get_or_404(order_id)
    payload = request.get_json()
    if_match = request.headers.get('X-If-Match')

    if if_match and str(order.updated_at) != if_match:
        return jsonify({
            'success': False, 'error': 'CONFLICT',
            'current': {'updated_at': order.updated_at.isoformat(),
                       'items': order.structured_data.get('items', [])}
        }), 409

    sd = copy.deepcopy(order.structured_data or {})
    items = sd.setdefault('items', [])
    for change in payload.get('items', []):
        idx = change.pop('idx')
        if idx < len(items):
            items[idx].update(change)
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db.session.commit()

    return jsonify({'success': True, 'updated_at': order.updated_at.isoformat()})
```

### CSS 핵심
```css
.foms-product-item {
  background: var(--foms-surface-raised);
  border: 1px solid var(--foms-border-subtle);
  border-radius: var(--foms-radius-lg);
  margin-bottom: var(--foms-space-3);
  overflow: hidden;
}
.foms-product-item__head {
  display: flex; align-items: center; gap: var(--foms-space-2);
  padding: var(--foms-space-3);
  background: var(--foms-surface-base);
  border-bottom: 1px solid var(--foms-border-subtle);
  cursor: pointer;
  min-height: var(--foms-touch-target-min);
}
.foms-product-item--collapsed .foms-product-item__body { display: none; }

.foms-spec-row {
  display: grid;
  grid-template-columns: 20px 1fr 1fr 1fr auto;
  gap: var(--foms-space-2);
  align-items: center;
}
.foms-spec-row__field { position: relative; }
.foms-spec-row__sublbl {
  position: absolute; top: -8px; left: 8px;
  font-size: 9px; font-weight: 700;
  background: var(--foms-surface-raised);
  color: var(--foms-color-brand-600);
  padding: 0 4px;
  border-radius: var(--foms-radius-sm);
  z-index: 1;
}
.foms-spec-row__input {
  min-height: 44px;
  text-align: center;
  font-weight: var(--foms-font-weight-medium);
  font-size: max(16px, var(--foms-font-size-base));
}

.foms-product-item__autosave {
  display: flex; align-items: center; gap: var(--foms-space-2);
  font-size: 11px;
  color: var(--foms-color-success-600);
}
.foms-product-item__autosave-dot {
  width: 6px; height: 6px;
  background: var(--foms-color-success-500);
  border-radius: var(--foms-radius-full);
  animation: foms-pulse-dot 2s infinite;
}
@keyframes foms-pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
```

### Container Query 적응
```css
.foms-product-item { container-type: inline-size; }
@container (min-width: 600px) {
  .foms-product-kv { grid-template-columns: 1fr 1fr; }
  /* 태블릿에서 KV 2열 */
}
```

### 우선순위 (P 단계)
- **P1-04** 인라인 편집 PR에서 본 컴포넌트 신규 구현
- 의존성: C06 KV row (alias `foms_kv_inline`), C07 attachment grid, OrderDraft 충돌 API

---

## 부록 A. 버튼 시스템

```css
.foms-btn {
  display: inline-flex; align-items: center; justify-content: center;
  gap: var(--foms-space-2);
  min-height: var(--foms-touch-target-min);
  padding: 0 var(--foms-space-4);
  font-family: var(--foms-font-sans);
  font-size: var(--foms-font-size-base);
  font-weight: var(--foms-font-weight-semibold);
  border-radius: var(--foms-radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    background-color var(--foms-duration-fast) var(--foms-ease-standard),
    box-shadow var(--foms-duration-fast) var(--foms-ease-standard),
    transform var(--foms-duration-fast) var(--foms-ease-accel);
  -webkit-tap-highlight-color: transparent;
}
.foms-btn:active { transform: scale(0.98); }

/* Variants */
.foms-btn--primary {
  background: var(--foms-interactive-primary);
  color: white;
}
.foms-btn--primary:hover { background: var(--foms-interactive-primary-hover); }
.foms-btn--primary:active { background: var(--foms-interactive-primary-active); }

.foms-btn--secondary {
  background: var(--foms-interactive-secondary);
  color: var(--foms-text-primary);
}
.foms-btn--ghost {
  background: transparent;
  color: var(--foms-text-primary);
}
.foms-btn--danger {
  background: var(--foms-interactive-danger);
  color: white;
}

/* Sizes */
.foms-btn--sm { min-height: 36px; font-size: var(--foms-font-size-sm); padding: 0 var(--foms-space-3); }
.foms-btn--lg { min-height: 56px; font-size: var(--foms-font-size-lg); padding: 0 var(--foms-space-5); }
.foms-btn--full { width: 100%; }
```

---

## 부록 B. Input 시스템

```css
.foms-input,
.foms-textarea,
.foms-select {
  width: 100%;
  min-height: var(--foms-touch-target-min);
  padding: var(--foms-space-2) var(--foms-space-3);
  font-family: inherit;
  font-size: max(16px, var(--foms-font-size-base));  /* iOS 줌 방지 */
  color: var(--foms-text-primary);
  background: var(--foms-surface-base);
  border: 1px solid var(--foms-border-default);
  border-radius: var(--foms-radius-md);
  appearance: none;
  transition: border-color var(--foms-duration-fast),
              box-shadow var(--foms-duration-fast);
}
.foms-input:focus,
.foms-textarea:focus,
.foms-select:focus {
  outline: none;
  border-color: var(--foms-border-focus);
  box-shadow: var(--foms-shadow-focus-ring);
}
.foms-input[aria-invalid="true"] {
  border-color: var(--foms-color-danger-500);
  box-shadow: var(--foms-shadow-focus-ring-danger);
}
.foms-textarea { min-height: 80px; resize: vertical; }
```

---

## 부록 C. FAB

```css
.foms-fab {
  position: fixed;
  bottom: calc(var(--foms-shell-bottom-nav-h)
               + var(--foms-safe-area-bottom)
               + var(--foms-space-4));
  right: var(--foms-space-4);
  width: var(--foms-shell-fab-size);
  height: var(--foms-shell-fab-size);
  border-radius: var(--foms-radius-full);
  background: var(--foms-interactive-primary);
  color: white;
  display: flex; align-items: center; justify-content: center;
  box-shadow: var(--foms-shadow-lg);
  border: none;
  z-index: var(--foms-z-fab);
  transition: transform var(--foms-duration-fast) var(--foms-ease-spring);
}
.foms-fab:hover { transform: scale(1.05); }
.foms-fab:active { transform: scale(0.95); }

/* 태블릿 가로에서는 measurement-list 영역에 정렬 */
@container shell (min-width: 1024px) {
  .foms-fab {
    bottom: var(--foms-space-6);
    right: auto;
    left: calc(var(--foms-shell-side-tab-w)
               + var(--foms-shell-master-list-w)
               - var(--foms-shell-fab-size)
               - var(--foms-space-4));
  }
}
```

---

## 부록 D. 컴포넌트 사용 매트릭스 (페이지별, v1.1)

| 페이지 | Shell | Bottom Nav | Queue Card | KV Row | Attach | Action Bar | Wizard | Filter | Search | Photo Capture | **Product Item (C14)** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 홈 (대시보드) | ✅ | ✅ | ✅ | | | | | ✅ | ✅ | | |
| 도면 작업실 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | | ✅ | ✅ | | |
| AS 대시보드 | ✅ | ✅ | ✅ | ✅ | ✅ | | | ✅ | ✅ | | |
| 시공 대시보드 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | | ✅ | ✅ | | |
| 출고 | ✅ | ✅ | ✅ | ✅ | | ✅ | | ✅ | | | |
| **주문 상세** | ✅ | ✅ | | ✅ | ✅ | ✅ | | | | | **✅** |
| 신규 주문 | ✅ | | | ✅ | ✅ | ✅ | ✅ | | | ✅ | |
| **주문 수정 (실측)** | ✅ | ✅ | | ✅ | ✅ | ✅ | | | | ✅ | **✅** |
| AS 접수 모달 | | | | | ✅ | ✅ | | | | ✅ | |
| 이력 검색 | ✅ | ✅ | ✅ | ✅ | | | | ✅ | ✅ | | |

---

## 부록 E. 구현 우선순위 (P0/P1/P2, v1.1)

| 컴포넌트 | P0 | P1 | P2 |
|---|---|---|---|
| C01 Shell | cohort 활성화 (기본값 false 유지) | 통합 + side-tab | 컨테이너 쿼리 |
| C02 Bottom Nav | 기존 활성화 | 배지 추가 | 햅틱 |
| C03 Side Tab | | 신규 | 자동 회전 감지 |
| C04 Master List | | 신규 (split-view) | 키보드 단축키 |
| C05 Queue Card | 기존 카드 gap patch (thumbnail·필터·배지) | 표준화 + 매크로 통합 | swipe action |
| C06 KV Row | | 매크로 승격 | 인라인 편집 |
| C07 Attachment Grid | capture 부착 | 매크로 승격 + 라이트박스 | pinch-zoom |
| C08 Sticky Action Bar | 폼 sticky 도입 | 매크로 승격 + 키보드 적응 | |
| C09 Wizard | | 신규 (신규 주문, OrderDraft 연동) | 자동저장 |
| C10 Filter Drawer | 기존 유지 | 칩 통합 | |
| C11 Search Overlay | | 신규 | 자동완성 prefetch |
| C12 Photo Capture | AS 모달 재설계 | 신규 컴포넌트 | OCR |
| C13 Status Badge | | 표준화 (도면·AS·시공 카드와 함께) | |
| **C14 Product Item Accordion** | | **신규 (P1-04 인라인 편집)** | OCR 자동 측정값 입력 |

---

> 본 라이브러리는 P0~P1 작업 중 점진적으로 코드화된다. 각 컴포넌트의 첫 사용 시점에 매크로·CSS를 작성하고, 후속 사용 페이지에서 재사용하며 PR로 일관성을 검증한다.
