# FOMS WAM Starter Spec
작성일: 2026-03-27
상태: 승인 / 코딩시작직전
범위: `tokens.css`, `layout.html`, `index.html`, `_macros.html`의 스타터 초안 규격
연관 문서:
- `docs/plans/2026-03-27-wam-detailed-order-view-master-plan.md`
- `docs/plans/2026-03-27-wam-design-system-spec.md`
- `docs/plans/2026-03-27-wam-file-skeleton-spec.md`

## 1. 한 줄 결론

이 문서는 WAM 상세뷰 구현을 시작할 때 가장 먼저 손대야 하는 4개 파일의 기준을 고정한다.

- `static/css/wam/tokens.css`
- `templates/channel_wam/layout.html`
- `templates/channel_wam/index.html`
- `templates/channel_wam/_macros.html`

이 4개를 잘못 시작하면 뒤의 section partial, JS, attachments lazy-load가 전부 흔들린다.

## 2. 구현 우선순위

1. `tokens.css`
2. `layout.html`
3. `_macros.html`
4. `index.html`

이 순서를 지키는 이유:

- 토큰이 먼저 닫혀야 CSS가 흔들리지 않는다.
- layout이 먼저 있어야 asset, bootstrap, body state 계약이 정해진다.
- macros가 먼저 있어야 section partial 반복이 줄어든다.
- index는 그 위에서 조립만 해야 한다.

## 3. `tokens.css` Starter Spec

### 3.1 목적

- WAM 전용 토큰의 source of truth
- reference / semantic / component layer 정의
- 다른 CSS 파일이 직접 값을 만들지 못하게 하는 기준 파일

### 3.2 금지

- class selector
- element selector
- layout rule
- component rule
- semantic/component layer에 raw hex, px, rgba 직접 입력
- `--erp-*` 직접 참조

### 3.3 권장 파일 헤더

```css
/* ==========================================================================
   WAM Tokens
   File: static/css/wam/tokens.css

   Rules
   - selectors 금지 (:root, @media 안의 :root만 허용)
   - naming:
     --wam-ref-*  = raw reference
     --wam-sys-*  = semantic/system
     --wam-comp-* = component-scoped token
   - raw value는 reference layer만 허용
   - deprecated bridge는 파일 맨 아래에만 둔다
   ========================================================================== */
```

### 3.4 권장 블록 순서

1. `Reference Tokens: Color`
2. `Reference Tokens: Typography`
3. `Reference Tokens: Spacing / Radius / Shadow / Size`
4. `System Tokens: Page / Surface / Text / Border`
5. `System Tokens: Status / Feedback`
6. `System Tokens: Motion / Z / Breakpoint`
7. `Component Tokens`
8. `Responsive Root Overrides`
9. `Bridge / Deprecated Alias`

### 3.5 스타터 예시

```css
:root {
  --wam-ref-neutral-0: #ffffff;
  --wam-ref-neutral-50: #f7f9fc;
  --wam-ref-neutral-100: #eef2f7;
  --wam-ref-neutral-200: #e2e8f0;
  --wam-ref-neutral-500: #64748b;
  --wam-ref-neutral-700: #334155;
  --wam-ref-neutral-900: #0f172a;

  --wam-ref-brand-500: #2563eb;
  --wam-ref-brand-600: #1d4ed8;
  --wam-ref-brand-700: #1e40af;

  --wam-ref-status-info-bg: #eff6ff;
  --wam-ref-status-info-fg: #1d4ed8;
  --wam-ref-status-success-bg: #dcfce7;
  --wam-ref-status-success-fg: #166534;
  --wam-ref-status-warning-bg: #fef3c7;
  --wam-ref-status-warning-fg: #92400e;
  --wam-ref-status-danger-bg: #fee2e2;
  --wam-ref-status-danger-fg: #991b1b;
}

:root {
  --wam-ref-font-sans: "Segoe UI Variable Text", "Segoe UI", "Noto Sans KR", system-ui, sans-serif;
  --wam-ref-text-xs: 12px;
  --wam-ref-text-sm: 13px;
  --wam-ref-text-md: 14px;
  --wam-ref-text-lg: 16px;
  --wam-ref-text-xl: 20px;
}

:root {
  --wam-ref-space-1: 4px;
  --wam-ref-space-2: 8px;
  --wam-ref-space-3: 12px;
  --wam-ref-space-4: 16px;
  --wam-ref-space-5: 20px;
  --wam-ref-space-6: 24px;
  --wam-ref-space-8: 32px;

  --wam-ref-radius-sm: 10px;
  --wam-ref-radius-md: 14px;
  --wam-ref-radius-lg: 18px;
  --wam-ref-radius-xl: 24px;

  --wam-ref-shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
  --wam-ref-shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
  --wam-ref-shadow-lg: 0 20px 48px rgba(15, 23, 42, 0.12);
}

:root {
  --wam-sys-bg-page: var(--wam-ref-neutral-50);
  --wam-sys-surface-card: var(--wam-ref-neutral-0);
  --wam-sys-surface-subtle: var(--wam-ref-neutral-100);
  --wam-sys-text-primary: var(--wam-ref-neutral-900);
  --wam-sys-text-secondary: var(--wam-ref-neutral-700);
  --wam-sys-border-subtle: var(--wam-ref-neutral-200);
  --wam-sys-border-strong: var(--wam-ref-neutral-500);
  --wam-sys-action-primary: var(--wam-ref-brand-600);
}

:root {
  --wam-sys-status-info-bg: var(--wam-ref-status-info-bg);
  --wam-sys-status-info-fg: var(--wam-ref-status-info-fg);
  --wam-sys-status-success-bg: var(--wam-ref-status-success-bg);
  --wam-sys-status-success-fg: var(--wam-ref-status-success-fg);
  --wam-sys-status-warning-bg: var(--wam-ref-status-warning-bg);
  --wam-sys-status-warning-fg: var(--wam-ref-status-warning-fg);
  --wam-sys-status-danger-bg: var(--wam-ref-status-danger-bg);
  --wam-sys-status-danger-fg: var(--wam-ref-status-danger-fg);
}

:root {
  --wam-comp-header-bg: var(--wam-sys-surface-card);
  --wam-comp-section-bg: var(--wam-sys-surface-card);
  --wam-comp-summary-gap: var(--wam-ref-space-3);
  --wam-comp-badge-radius: var(--wam-ref-radius-sm);
  --wam-ref-size-action-height: 44px;
  --wam-comp-action-height: var(--wam-ref-size-action-height);
}

:root {
  --wam-sys-motion-fast: 140ms ease-out;
  --wam-sys-motion-base: 220ms ease;
  --wam-sys-bp-md: 768px;
  --wam-sys-state-error-bg: var(--wam-ref-status-danger-bg);
  --wam-sys-state-error-fg: var(--wam-ref-status-danger-fg);
}
```

### 3.6 Acceptance

- `tokens.css`는 토큰만 정의한다.
- semantic은 `var(--wam-ref-*)`만 참조한다.
- component는 `var(--wam-ref-*)` 또는 `var(--wam-sys-*)`만 참조한다.
- `status`, `state`, `motion`, `breakpoint`, `fixed size` 세트가 빠지지 않는다.

## 4. `layout.html` Starter Spec

### 4.1 목적

- WAM 전용 HTML shell
- asset loading order 고정
- bootstrap JSON 주입
- body state class / data attribute 고정

### 4.2 금지

- 주문 상세 section 마크업
- inline script
- inline style
- page-specific 데이터 가공

### 4.3 block 구조

권장 block:

1. `html_class`
2. `meta`
3. `title`
4. `head_assets`
5. `body_class`
6. `body_view_key`
7. `body`
8. `shell`
9. `bootstrap_json`
10. `page_scripts`

### 4.4 스타터 예시

```jinja2
<!doctype html>
<html lang="ko" class="{% block html_class %}wam-html{% endblock %}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light">
  {% block meta %}{% endblock %}

  <title>{% block title %}FOMS WAM{% endblock %}</title>

  <link rel="stylesheet" href="{{ url_for('static', filename='css/erp-pro.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/wam/tokens.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/wam/base.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/wam/layout.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/wam/components.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/wam/order-detail.css') }}">
  {% block head_assets %}{% endblock %}
</head>
<body
  class="{% block body_class %}wam-page wam-page--order-detail is-readonly{% endblock %}"
  data-view-key="{% block body_view_key %}order-detail{% endblock %}"
  data-page-state="{{ page_vm.page_state if page_vm is defined else 'unknown' }}"
>
  {% block body %}
  <div class="wam-shell" id="wam-shell">
    {% block shell %}{% endblock %}
  </div>
  {% endblock %}

  {% block bootstrap_json %}
  <script id="wam-bootstrap" type="application/json">
    {{ bootstrap_payload|tojson }}
  </script>
  {% endblock %}

  <script defer src="{{ url_for('static', filename='js/wam/core.js') }}"></script>
  <script defer src="{{ url_for('static', filename='js/wam/telemetry.js') }}"></script>
  <script defer src="{{ url_for('static', filename='js/wam/attachments.js') }}"></script>
  <script defer src="{{ url_for('static', filename='js/wam/order-detail.js') }}"></script>
  {% block page_scripts %}{% endblock %}
</body>
</html>
```

### 4.5 Acceptance

- asset order가 문서와 동일하다.
- bootstrap JSON은 `<script type="application/json">`으로만 주입한다.
- body class는 style state만, JS 판단값은 `data-*`로 넣는다.
- section 마크업은 이 파일에 없다.

## 5. `_macros.html` Starter Spec

### 5.1 목적

- 반복 마크업 제거
- section shell / kv row / badge / state block 재사용

### 5.2 필수 macro

- `badge(label, tone='default')`
- `kv_row(label, value, tone='default')`
- `empty_block(message='...')`
- `error_block(message='...')`
- `section_shell(section)`

### 5.3 스타터 예시

```jinja2
{% macro badge(label, tone='default') -%}
<span class="wam-badge wam-badge--{{ tone }}">{{ label }}</span>
{%- endmacro %}

{% macro kv_row(label, value, tone='default') -%}
<div class="wam-kv-row wam-kv-row--{{ tone }}">
  <dt class="wam-kv-row__label">{{ label }}</dt>
  <dd class="wam-kv-row__value">{{ value or '-' }}</dd>
</div>
{%- endmacro %}

{% macro empty_block(message='표시할 정보가 없습니다.') -%}
<div class="wam-empty-state">{{ message }}</div>
{%- endmacro %}

{% macro error_block(message='정보를 불러오지 못했습니다.') -%}
<div class="wam-error-state">{{ message }}</div>
{%- endmacro %}

{% macro section_shell(section) -%}
<section
  class="wam-section wam-section--{{ section.key }} is-{{ section.state }}"
  id="section-{{ section.key }}"
  data-section-key="{{ section.key }}"
  data-section-state="{{ section.state }}"
>
  <header class="wam-section__header">
    <h2 class="wam-section__title">{{ section.title }}</h2>
  </header>
  <div class="wam-section__body">
    {% if section.state == 'empty' %}
      {{ empty_block(section.empty_message or '표시할 정보가 없습니다.') }}
    {% elif section.state == 'error' %}
      {{ error_block(section.error_message or '정보를 불러오지 못했습니다.') }}
    {% elif section.state != 'hidden' %}
      {{ caller() }}
    {% endif %}
  </div>
</section>
{%- endmacro %}
```

### 5.4 Acceptance

- macro는 표시 helper만 담당한다.
- DB/권한/flag 판단 금지
- section shell은 `ready|empty|error|hidden` 계약을 가진다.

## 6. `index.html` Starter Spec

### 6.1 목적

- `page_vm` 하나로 WAM 상세 화면을 조립
- header / summary / section stack / sticky action bar 배치

### 6.2 금지

- raw dict 탐색
- section payload 직접 보정
- 템플릿 이름을 payload에서 직접 받기
- 비즈니스 if/else

### 6.3 DOM 우선순위

권장 DOM 순서:

1. skip link
2. header
3. summary strip
4. primary sections
5. folded sections
6. sticky action bar

원칙:

- `schedule`, `site`, `people`는 기본 펼침
- `items`, `attachments`, `timeline`은 heavy section으로 기본 접힘
- heavy section은 한 번에 하나만 펼침
- `header`, `summary_strip`, `sticky_action_bar`는 top/bottom slot 전용이며 `page_vm.sections` 반복 대상에 포함하지 않는다.

### 6.4 section key allowlist

| section key | partial |
|-------------|---------|
| `header` | `sections/_header.html` |
| `summary_strip` | `sections/_summary_strip.html` |
| `customer` | `sections/_customer.html` |
| `site` | `sections/_site.html` |
| `schedule` | `sections/_schedule.html` |
| `people` | `sections/_people.html` |
| `items` | `sections/_items.html` |
| `attachments` | `sections/_attachments.html` |
| `timeline` | `sections/_timeline.html` |
| `sticky_action_bar` | `sections/_sticky_action_bar.html` |

### 6.5 스타터 예시

```jinja2
{% extends "channel_wam/layout.html" %}
{% import "channel_wam/_macros.html" as wam %}

{% block title %}
주문 #{{ page_vm.header.order_id }} | FOMS WAM
{% endblock %}

{% block shell %}
<a class="wam-skip-link" href="#wam-main">본문으로 건너뛰기</a>

<main id="wam-main" class="wam-main">
  {% if page_vm.page_state == 'error' %}
    {% include "channel_wam/states/_error.html" %}
  {% elif page_vm.page_state == 'empty' %}
    {% include "channel_wam/states/_empty.html" %}
  {% else %}
    {% include "channel_wam/sections/_header.html" %}
    {% include "channel_wam/sections/_summary_strip.html" %}

    {% set section_templates = {
      'customer': 'channel_wam/sections/_customer.html',
      'site': 'channel_wam/sections/_site.html',
      'schedule': 'channel_wam/sections/_schedule.html',
      'people': 'channel_wam/sections/_people.html',
      'items': 'channel_wam/sections/_items.html',
      'attachments': 'channel_wam/sections/_attachments.html',
      'timeline': 'channel_wam/sections/_timeline.html'
    } %}

    <div class="wam-section-stack" id="wam-section-stack">
      {% for section in page_vm.sections %}
        {% set template_name = section_templates.get(section.key) %}
        {% if template_name %}
          {% call wam.section_shell(section) %}
            {% include template_name %}
          {% endcall %}
        {% endif %}
      {% endfor %}
    </div>

    {% if page_vm.sticky_action_bar and page_vm.sticky_action_bar.state != 'hidden' %}
      {% include "channel_wam/sections/_sticky_action_bar.html" %}
    {% endif %}
  {% endif %}
</main>
{% endblock %}
```

### 6.6 Acceptance

- `page_vm` 하나만 소비한다.
- include 대상은 allowlist 기반이다.
- header와 summary strip은 top slot 고정이다.
- sticky action bar는 DOM상 마지막이다.
- hidden section은 렌더하지 않는다.

## 7. 공통 금지사항

- `tokens.css`에 selector 넣기
- `layout.html`에 주문 상세 콘텐츠 넣기
- `index.html`에서 raw `structured_data` 읽기
- inline style / inline JS
- `--erp-*` 직접 사용
- section 이름을 payload가 결정하게 두기
- empty / hidden / error를 같은 UI로 처리하기

## 8. 공통 Acceptance

- first paint `1.5초`
- 주문 식별 `1초`
- 핵심 정보 인지 `3초`
- 첨부 탐색 시작 `5초`
- iPhone Safari WebView / Android Chrome WebView 기준 통과

## 9. 바로 다음 작업

1. `tokens.css` 실제 파일 생성
2. `layout.html` 실제 파일 생성
3. `_macros.html` 실제 파일 생성
4. `index.html` 실제 파일 생성
5. `_header.html`, `_summary_strip.html`부터 순차 생성
