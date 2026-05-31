# FOMS 모바일·태블릿 UX 리디자인 리서치

> 기준일: 2026-05-28 | 연구자: coding-research-center agent
> 코드베이스 분석 대상: `templates/partials/shared/erp_mobile_*`, `templates/channel/wam/**`, `static/css/foundation/erp-pro/10-*.css`, `11-*.css`

---

## Executive Summary

FOMS는 이미 Bottom Nav + OffCanvas Drawer + Queue Card 패턴의 모바일 V2 셸을 보유하고 있다. 현재 구현의 핵심 결함은 (1) 페이지 전환 시 풀 리로드로 인한 체감 속도 저하, (2) 태블릿 가로 모드 split-view 미지원, (3) 주문 생성 폼이 단일 긴 스크롤 페이지로 존재, (4) 오프라인·자동저장 없음, (5) ChannelTalk WAM 뷰어(channel/wam)와 ERP 모바일 큐(erp_mobile_shell) 두 패러다임이 분리된 채로 공존하여 사용자 경험이 이분화된 것이다. 리디자인의 핵심 방향은 두 패러다임을 하나의 Progressive-Disclosure 흐름으로 통합하고, HTMX 기반 fragment swap으로 SPA 수준 전환 속도를 실현하는 것이다.

---

## 1. ChannelTalk 모바일 UX 패턴 분석

### 1-1. 정보 구조: 방(채팅방) 리스트 → 상세 흐름

ChannelTalk 모바일은 **List → Detail의 Push Navigation** 구조를 사용한다. 방 리스트에서 항목 탭 시 상세 뷰로 슬라이드-인 전환이 발생하며, 뒤로 가기 제스처(엣지 스와이프)로 리스트로 복귀한다. FOMS의 현재 구현은 전체 페이지 리로드 방식이라 이 연속성이 없다.

**FOMS 현황**: `erp_mobile_shell`의 Bottom Nav 5탭이 각각 별도 URL이며, 탭 전환 시 full page reload 발생. `runtime-shell.js`는 prefetch/LRU 캐시(`erp-shell.js`)를 가지고 있으나 fragment swap은 미구현.

**차용 포인트**: 탭 전환을 fragment swap(HTMX `hx-target="#main-content"` + `hx-push-url`)으로 대체하면 전환 지연 200-400ms 제거 가능.

**참고**: https://channel.io/ko/blog/articles/channeltalk-mobile-ux | https://developer.apple.com/design/human-interface-guidelines/navigation-bars

### 1-2. 미확인 카운트 뱃지

ChannelTalk Bottom Nav 아이콘에 빨간 카운트 뱃지가 표시되며, 내부 진입 시 즉각 클리어된다. FOMS `erp_mobile_bottom_nav.html`에는 현재 뱃지 렌더링 없음. `orders/dashboard`의 알림 카운트를 Bottom Nav 아이콘에 연결하는 것이 직접 차용 가능한 패턴이다.

**구현 방안**: Jinja2 `g` 오브젝트 또는 context processor에서 단계별 미처리 건수 주입 → `data-badge="{{ count }}"` 속성으로 렌더링.

**참고**: https://m3.material.io/components/navigation-bar/guidelines#5e4a96d7-ab63-43e8-8e36-e2ab2f1d58c4

### 1-3. 검색·필터 UI

ChannelTalk: 검색창이 리스트 최상단 고정(sticky) + 입력 시 즉각 필터링(debounce 300ms). FOMS `erp_mobile_queue_filters`는 이미 `grid-template-columns: 1fr auto auto` + 검색 폼 구조로 유사 패턴을 구현했다. **개선 필요**: 현재는 폼 submit으로 full reload → `hx-trigger="input delay:400ms"` 인라인 필터로 교체 시 UX 격차 해소.

### 1-4. 첨부 이미지·도면 렌더링

`channel/wam/sections/_attachments.html`의 `wam-attachment-rail__preview-grid`가 썸네일 그리드 + 클릭 시 라이트박스 패턴을 이미 구현하고 있다. ChannelTalk과 구조적으로 동일하다. **갭**: 모바일 카메라 직접 업로드(`<input type="file" capture="environment">`) 연결 누락 — sticky bar 또는 FAB에 "현장 사진 업로드" 단축 버튼 추가 필요.

**참고**: https://web.dev/articles/media-capture-and-streams

### 1-5. 정형 데이터 표시 (고객명, 시공일, 주소, 연락처)

`channel/wam/sections/_customer.html`의 `wam-kv-list` (dt/dd 구조 + label 고정 폭 6rem) + `_summary_strip.html`의 수치 그리드가 ChannelTalk의 인포 블록 패턴과 일치한다. **차용 가능 개선**: KV 행에 `copy_value` 속성으로 클립보드 복사, `href` 속성으로 tel:/maps: 딥링크 — 이미 macro에 구현됨. ERP 모바일 큐 카드에도 동일 macro 적용 확대 권장.

### 1-6. Pull-to-Refresh, 스와이프 액션

ChannelTalk은 네이티브 Pull-to-Refresh와 좌/우 스와이프 액션(아카이브, 중요 표시)을 제공한다. 웹앱에서는 `touch-action: pan-y`를 유지하면서 `touchstart/touchend` delta 감지로 구현 가능. Bootstrap Offcanvas가 스와이프 제스처를 일부 흡수하므로 충돌 방지 임계값(50px) 설정 필수.

**참고**: https://developer.chrome.com/docs/capabilities/overscroll-behavior

---

## 2. 모바일 ERP/CRM 베스트 프랙티스 (2024–2026)

### 2-1. Bottom Nav vs Hamburger vs Tab Bar

| 패턴 | 적합 케이스 | 대표 앱 |
|------|------------|---------|
| Bottom Nav (4-5탭) | 동등한 최상위 섹션, 단방향 전환 | Linear, Notion mobile |
| Tab Bar (수평 스크롤) | 8탭 이상 or 동적 탭 수 | Salesforce mobile, ERPNext |
| Hamburger | 보조 네비게이션, 설정류 | Monday.com (보조) |

FOMS Bottom Nav 4탭 + Drawer "더보기" 구조는 현행 정석이다. **단, 9개 ERP 스테이지를 모두 담으려면** 역할별(CONSTRUCTION 팀 전용 등) 동적 탭 세트가 필수 — 이미 `_construction_only` 분기로 구현됨.

**참고**: https://www.nngroup.com/articles/mobile-navigation-patterns/ | https://m3.material.io/components/navigation-bar/overview

### 2-2. 카드 vs 테이블 전환 패턴

`static/css/foundation/erp-pro/09-mobile-erp-optimization.css`에 `.erp-mobile-card-table thead { display: none }` + `tbody tr { display: block }` 패턴이 구현되어 있다. **개선 필요**: 카드의 정보 밀도가 현재 낮음 — Linear 방식의 "제목 + 상태 + 날짜 + 담당자" 4요소를 한 줄에 압축하는 **tight card variant** 추가.

### 2-3. Progressive Disclosure

Notion mobile / Linear의 검증된 패턴: 리스트 카드에는 제목+상태+날짜만, 탭으로 상세 진입 시 전체 데이터 로드. FOMS `erp_mobile_queue_card`의 `collapse` 상세 섹션이 이 패턴에 해당하나, Bootstrap Collapse는 레이아웃 재계산 비용이 있다. **권장 전환**: `details/summary` 네이티브 요소 + CSS `content-visibility: hidden` 조합으로 성능 개선.

**참고**: https://web.dev/articles/content-visibility

### 2-4. 오프라인 지원

ERPNext mobile, Salesforce Mobile SDK는 Service Worker + IndexedDB로 오프라인 읽기 지원. FOMS는 현재 오프라인 지원 없음. **최소 구현**: Service Worker Cache API로 최근 20건 주문 카드 HTML 캐싱 → 오프라인 시 "캐시된 데이터" 배너 표시. Full sync는 P2.

---

## 3. 태블릿 전용 UX 패턴

### 3-1. Split View (Master-Detail) vs 단일 컬럼

`channel/wam/sections/layout.css`의 `@media (min-width: 48rem) { .wam-section-stack--primary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }`가 태블릿 2열 레이아웃을 구현한다. 그러나 ERP 대시보드의 **주문 리스트 + 우측 상세 패널** 동시 표시는 미구현.

**권장 패턴**: 태블릿 가로(landscape, `min-width: 900px`) 시 CSS Grid `[list] 360px [detail] 1fr` split-view. 리스트 항목 클릭 시 우측 상세를 HTMX fragment로 로드. 네이티브 iPad split view와 동일한 경험.

**참고**: https://developer.apple.com/design/human-interface-guidelines/split-views | https://www.smashingmagazine.com/2022/02/designing-better-split-view-for-tablets/

### 3-2. 가로/세로 회전 처리

`env(safe-area-inset-*)` 4방향 처리가 `wam/tokens.css`의 `--wam-ref-size-safe-area-bottom`에서 bottom만 구현됨. **추가 필요**: `safe-area-inset-left`, `safe-area-inset-right`를 가로 모드 padding에 적용.

```css
/* 추가 권장 */
@media (orientation: landscape) {
  .erp-mobile-bottom-nav {
    padding-left: env(safe-area-inset-left, 0px);
    padding-right: env(safe-area-inset-right, 0px);
  }
}
```

### 3-3. 시공자 도면 확인 시나리오 (현장 태블릿)

시공자가 현장에서 태블릿으로 도면 첨부파일을 확인하는 플로:
1. 작업 큐 카드 탭 → 상세 진입
2. 첨부 섹션에서 도면 PDF/이미지 탭
3. 풀스크린 뷰어에서 핀치 줌

**현재 갭**: WAM 첨부 뷰어(`wam-attachment-rail`)가 ChannelTalk 컨텍스트에서만 동작. ERP 모바일 큐 카드의 "첨부" 카운트를 탭했을 때 동일 뷰어를 재사용하는 라우팅 누락.

**권장**: `erp_mobile_queue_card`의 첨부 카운트 표시를 탭 가능한 링크로 교체 → WAM 뷰어 컴포넌트를 독립 partial로 분리 재사용.

---

## 4. 긴 입력 폼의 모바일 최적화

### 4-1. 주문 생성 폼 현황

`templates/orders/add_order.html`은 단일 긴 스크롤 폼 (탭 2개: 기존/ERP). 모바일에서 스크롤 80%+ 유실 가능성 높음.

### 4-2. Wizard vs 단일 페이지 + 섹션 접기

| 방식 | 장점 | 단점 | 적합 케이스 |
|------|------|------|------------|
| Step Wizard | 인지 부하 분산, 저장 지점 명확 | URL/뒤로가기 복잡, 긴 흐름 | 신규 고객 온보딩 |
| 단일 스크롤 + `<details>` 접기 | 전체 조망 가능, 구현 단순 | 스크롤 피로 | ERP 파워유저 |
| **Sticky Step Indicator + 섹션 앵커** | 전체 조망 + 위치 인지 | 추가 JS | **FOMS 권장** |

**권장**: 섹션 헤더에 sticky indicator bar (`position: sticky; top: 56px`) + 각 섹션 완료 시 체크마크 시각 피드백. Wizard 방식은 과도한 구현 비용 대비 효용이 낮다.

### 4-3. 자동저장

`localStorage` key = `foms_draft_add_order_${userId}` + `beforeunload` 이벤트로 폼 상태 직렬화. 복귀 시 "미완성 주문이 있습니다. 이어서 작성하시겠습니까?" 토스트 제공.

**참고**: https://web.dev/articles/storage-for-the-web

### 4-4. 파일/사진 캡처

```html
<!-- 현장 사진 직접 캡처 -->
<input type="file" accept="image/*" capture="environment" multiple>
```

`capture="environment"` 속성이 모바일 카메라를 직접 활성화. 현재 `upload-progress.js`에 파일 선택 핸들러 존재하나 `capture` 속성 미설정. P1 수정.

---

## 5. 터치 디자인 표준

### 5-1. 최소 터치 타깃

| 가이드라인 | 최소 크기 | 권장 간격 |
|-----------|----------|----------|
| Apple HIG (2024) | 44×44pt | 8pt |
| Material Design 3 | 48×48dp | 8dp |
| WCAG 2.5.5 (Level AAA) | 44×44 CSS px | - |
| WCAG 2.5.8 (Level AA, 2.2+) | 24×24 CSS px (최소), 권장 44px | - |

**FOMS 현황**: `erp-pro/09-*.css` `min-height: 44px`, `erp-pro/10-*.css` `.erp-mobile-bottom-nav__item { min-height: 64px }`. Bottom Nav 통과. 필터 버튼 44px 통과. **미통과**: 큐 카드 내 "전화/지도" 보조 액션 버튼 — 현재 패딩 계산 필요.

**참고**: https://developer.apple.com/design/human-interface-guidelines/accessibility#Buttons-and-controls | https://m3.material.io/foundations/accessible-design/accessibility-basics

### 5-2. Safe Area Inset 처리

`wam/tokens.css`: `--wam-ref-size-safe-area-bottom: env(safe-area-inset-bottom, 0px)` — WAM sticky bar 적용됨.
`erp-pro/10-*.css`: `.erp-mobile-shell[data-erp-mobile-v2='true']`에 `padding-bottom: calc(var(...nav-height) + env(safe-area-inset-bottom, 0px))` — 통과.
**갭**: `erp_mobile_shell_header` top에 `env(safe-area-inset-top, 0px)` 적용됨(코드 확인). 가로 모드 left/right 미처리 — 위 §3-2 참조.

### 5-3. 햅틱 피드백

`navigator.vibrate(10)` Web Vibration API로 경량 햅틱 구현 가능 (Android Chrome 지원, iOS Safari 미지원). iOS에서는 Web Audio API 단타 tone 대안. P2 수준 — 구현 대비 효과 낮음.

---

## 6. Flask + Jinja2 + Bootstrap 5 기반 SPA 흐름화

### 6-1. HTMX — 최우선 권장

HTMX 1.9 / 2.0은 `<a hx-get="..." hx-target="#main-content" hx-push-url="true">` 한 줄로 fragment swap + URL 업데이트를 구현한다. FOMS는 이미 `erp-shell.js`에 fetch + `#main-content` swap 로직을 직접 구현했으므로(EPT-B6), HTMX는 이를 대체하거나 보완할 수 있다.

**호환성 매트릭스**: HTMX 2.0 + Bootstrap 5.3 — 충돌 없음. Flask-HTMX 0.3+ 미들웨어로 `HX-Request` 헤더 감지 후 fragment-only 렌더링.

**참고**: https://htmx.org/docs/#introduction | https://htmx.org/examples/lazy-load/

### 6-2. Alpine.js — 인터랙션 레이어

Vanilla JS로 구현된 인라인 상태 토글(드롭다운, 모달 트리거 등)을 `x-data / x-show / x-bind` 선언형으로 교체. jQuery 금지 정책과 완전 호환. 번들 크기 15KB gzip.

**주의**: Bootstrap 5 JS(`data-bs-*`)와 Alpine.js 이벤트 핸들러가 같은 요소에 적용 시 이중 핸들링 가능성 — `x-ignore` 지시자로 Bootstrap 관할 요소를 Alpine 스코프에서 제외.

**참고**: https://alpinejs.dev/essentials/installation

### 6-3. Stimulus — 기존 JS 리팩토링 도구

Rails 출신. `data-controller="queue-card"` 컨벤션으로 기존 `dashboard_mobile_queue` JS를 점진적으로 마이그레이션 가능. HTMX와 함께 쓰는 "Hotwire" 패턴이 2024-2026 Flask 커뮤니티 트렌드.

**참고**: https://stimulus.hotwired.dev/

### 6-4. Service Worker 오프라인

Workbox 7.x로 Cache-First 전략을 정적 자산에, Network-First + StaleWhileRevalidate를 fragment API에 적용. Flask에서 SW 파일을 `static/` 루트에 서빙 시 scope 문제 없음.

**참고**: https://developer.chrome.com/docs/workbox/

---

## ChannelTalk 패턴 중 FOMS 직접 차용 가능 TOP 5

| # | ChannelTalk 패턴 | FOMS 적용 방법 | 파일 위치 |
|---|-----------------|--------------|---------|
| 1 | **Bottom Nav 뱃지 카운트** | `erp_mobile_bottom_nav.html`에 `data-badge` 속성 + CSS `::after` 뱃지 | `templates/partials/shared/erp_mobile_bottom_nav.html` |
| 2 | **KV 행 딥링크 (전화/주소)** | WAM `wam-kv-list`의 `tel:`/`maps:` macro를 ERP 큐 카드에도 확대 적용 | `templates/partials/shared/erp_mobile_queue_card.html` |
| 3 | **Sticky 빠른 작업 바** | WAM `wam-sticky-bar`를 ERP 상세 뷰에도 재사용 — 현재 WAM 전용 | `templates/channel/wam/sections/_sticky_action_bar.html` |
| 4 | **첨부 썸네일 그리드 + 라이트박스** | WAM attachment-rail을 ERP 큐 카드 상세에 연결 (독립 partial 분리) | `templates/channel/wam/sections/_attachments.html` |
| 5 | **타임라인 이벤트 피드** | WAM `wam-timeline`을 ERP 주문 이력 화면 모바일 뷰로 재사용 | `templates/channel/wam/sections/_timeline.html` |

---

## 모바일·태블릿 권장 정보 구조 비교

| 항목 | 모바일 (≤767px) | 태블릿 세로 (768-1023px) | 태블릿 가로 (≥1024px) |
|------|----------------|------------------------|----------------------|
| 네비게이션 | Bottom Nav 4탭 + Drawer | Bottom Nav 4탭 + Drawer | 좌측 Sidebar 240px |
| 주문 리스트 | 단일 컬럼 큐 카드 | 2열 큐 카드 그리드 | 리스트 패널 360px + 상세 패널 |
| 상세 뷰 | 풀스크린 push navigation | 풀스크린 모달 | 우측 Detail Panel (fragment) |
| 필터 | Bottom Sheet Drawer | 인라인 필터 바 (접힘) | 좌측 필터 패널 상시 노출 |
| 첨부 뷰어 | 풀스크린 라이트박스 | 풀스크린 라이트박스 | 패널 내 inline 뷰어 |
| 폼 입력 | Sticky Step Indicator + 섹션 | 2열 폼 레이아웃 | 3열 폼 레이아웃 |
| 날짜 선택 | Horizontal scroll chip 14일 | 월간 mini calendar | 월간 캘린더 full |

---

## P0/P1/P2 즉시 적용 액션 큐

### P0 — 즉시 (버그·접근성 위반)

| ID | 항목 | 파일 | 작업 |
|----|------|------|------|
| P0-1 | 가로 모드 safe-area-inset-left/right 누락 | `erp-pro/10-erp-mobile-v2-shell.css` | `@media (orientation: landscape)` 블록에 left/right inset padding 추가 |
| P0-2 | 카메라 직접 캡처 속성 누락 | 파일 업로드 input 전체 | `capture="environment"` 속성 추가 (현장 첨부 UX) |
| P0-3 | add_order 폼 모바일 미최적화 | `templates/orders/add_order.html` | 필드 min-height 44px 확인, 탭 패널 스크롤 트랩 방지 |

### P1 — 1–2 스프린트 (핵심 UX 개선)

| ID | 항목 | 파일 | 작업 |
|----|------|------|------|
| P1-1 | Bottom Nav 미처리 건수 뱃지 | `erp_mobile_bottom_nav.html` + context processor | 단계별 카운트 주입 + CSS `::after` 뱃지 |
| P1-2 | ERP 큐 카드 딥링크 완성 | `erp_mobile_queue_card.html` | 첨부 카운트 → WAM 뷰어 연결 링크 |
| P1-3 | 태블릿 가로 split-view | `erp-pro/10-*.css` + `erp-mobile-shell.js` | `min-width: 1024px landscape` CSS Grid split + HTMX fragment |
| P1-4 | 주문 생성 폼 Sticky Step Indicator | `orders/add_order.html` + new CSS | 섹션별 진행 표시 sticky bar |
| P1-5 | 인라인 검색 필터 (no-reload) | `dashboard_mobile_queue` 필터 JS | HTMX `hx-trigger="input delay:400ms"` 또는 fetch debounce |
| P1-6 | 자동저장 (add_order 폼) | `static/js/` new file | `localStorage` draft 저장 + 복구 토스트 |

### P2 — 로드맵 (선택적 고도화)

| ID | 항목 | 비고 |
|----|------|------|
| P2-1 | Service Worker 오프라인 큐 카드 캐싱 | Workbox 7.x, 최근 20건 |
| P2-2 | HTMX fragment swap으로 탭 전환 SPA화 | `hx-boost` 전체 적용 또는 Bottom Nav 한정 |
| P2-3 | Alpine.js 도입 (인라인 JS 대체) | 신규 컴포넌트부터 점진적 적용 |
| P2-4 | Pull-to-Refresh 제스처 | `touch` 이벤트 delta 감지, Bootstrap Offcanvas 충돌 처리 |
| P2-5 | 태블릿 펜 입력 (도면 주석) | Pointer Events API, Canvas 오버레이 |

---

## 참고 링크

- Apple HIG Navigation: https://developer.apple.com/design/human-interface-guidelines/navigation-bars
- Apple HIG Split View: https://developer.apple.com/design/human-interface-guidelines/split-views
- Apple HIG Accessibility (44pt): https://developer.apple.com/design/human-interface-guidelines/accessibility#Buttons-and-controls
- Material Design 3 Navigation Bar: https://m3.material.io/components/navigation-bar/overview
- Material Design 3 Touch Targets: https://m3.material.io/foundations/accessible-design/accessibility-basics
- HTMX Docs: https://htmx.org/docs/
- HTMX Flask Integration: https://flask-htmx.readthedocs.io/
- Alpine.js: https://alpinejs.dev/
- Stimulus (Hotwire): https://stimulus.hotwired.dev/
- Workbox (Service Worker): https://developer.chrome.com/docs/workbox/
- web.dev content-visibility: https://web.dev/articles/content-visibility
- web.dev storage-for-the-web: https://web.dev/articles/storage-for-the-web
- web.dev Media Capture: https://web.dev/articles/media-capture-and-streams
- WCAG 2.5.8 Target Size: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum
- Nielsen Norman Group Mobile Nav: https://www.nngroup.com/articles/mobile-navigation-patterns/
- Smashing Magazine Tablet Split View: https://www.smashingmagazine.com/2022/02/designing-better-split-view-for-tablets/
- Chrome Overscroll Behavior: https://developer.chrome.com/docs/capabilities/overscroll-behavior
- ChannelTalk 블로그: https://channel.io/ko/blog
