# Global Nav Real Speed Execution Plan
> 작성일: 2026-04-17 | 상태: 🟡 **실행 준비 완료 — 상세 설계·배치 순서·stop rule 고정**
>
> **Companion plan**: `docs/plans/2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`
>
> 이 문서는 상위 ERP 네비게이션 계획의 **글로벌 상단 네비 체감 속도 개선 전용 runbook**이다.  
> 현재 구현은 `static/js/global-nav-runtime.js`의 `<link rel="prefetch">` 힌트 수준이므로, 사용자가 느끼는 “즉각성”을 만들기 위한 실제 조치만 따로 잠근다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
상단 `layout-global-nav` 클릭 시,

- **같은 레이아웃/같은 읽기 family**로 이동하는 링크는 full reload 대신 **warm fragment swap 또는 fragment-aware document swap**으로 전환하고
- **다른 app/document surface**로 이동하는 링크는 fake SPA를 만들지 않고 **document warmup / prerender / asset warmup**으로 체감 지연을 줄이며
- canonical URL, history, 권한, 최종 본문 의미는 기존과 100% 동일하게 유지하는

글로벌 네비 전용 fast-path 계층을 만든다.

### 1.2 현재 진단
현재 top-nav 체감이 거의 안 나는 이유는 구조적으로 명확하다.

1. `static/js/global-nav-runtime.js`는 hover/focus 시 `<link rel="prefetch">`만 추가한다.
2. 클릭 interception, body swap, DOM restore, history restore, warm cache hit 적용이 없다.
3. 따라서 클릭 순간에는 여전히 **full document navigation 비용**을 대부분 그대로 낸다.
4. `static/js/erp/runtime-shell.js`의 실제 instant swap은 ERP shell 대상에만 적용된다.
5. top-nav에는 같은 레이아웃 family와 다른 app surface가 섞여 있어, 전부 같은 방식으로 최적화하면 semantic drift 위험이 크다.

결론:
- 지금 구현은 “약한 warm hint”이지 “실제 빠른 이동”이 아니다.
- 체감 개선을 만들려면 **G1 same-family는 실제 swap 경로**, **G2 cross-surface는 실제 document warmup 경로**가 필요하다.

### 1.3 성공 기준
이 계획의 성공은 아래를 동시에 만족할 때만 선언한다.

1. 사용자가 top-nav 클릭 시 “이전보다 확실히 빨라졌다”고 체감할 정도의 warm path를 만든다.
2. 기능/권한/필터/페이지네이션/KPI/URL 의미는 완전히 동일하다.
3. G1과 G2를 섞지 않는다.
4. Railway staging/prod-like evidence로 before/after를 증명한다.

### 1.4 비목표
- top-nav 전체를 SPA처럼 만드는 것
- WDPLANNER / WDCalculator / 채팅 / 관리자 페이지를 body swap으로 갈아끼우는 것
- 느린 화면의 일부 데이터를 빼서 가볍게 보이게 만드는 것
- DB schema / migration / index 변경

## 2. Why — 왜 지금 체감이 안 나는가

### 2.1 현재 구조의 한계
`<link rel="prefetch">`는 브라우저에 “한가하면 미리 받아둬도 좋다”는 힌트일 뿐이다.

- 우선순위가 낮다.
- 실제 클릭 순간 바로 재사용된다는 보장이 약하다.
- warm DOM / warm HTML body / scroll restore를 제공하지 않는다.
- same-layout family에서도 full document parse/boot 비용은 여전히 남는다.

따라서 지금 구조로는 “네트워크 일부를 살짝 데움” 정도의 효과만 기대할 수 있고, 사용자가 느끼는 클릭 즉시성은 거의 생기지 않는다.

### 2.2 실제로 체감을 만들려면
체감이 나려면 아래 중 적어도 하나가 실제로 일어나야 한다.

1. 클릭 순간 **이미 준비된 body HTML**로 즉시 swap
2. 클릭 순간 **이미 warm된 document**로 starttransfer/DOMContentLoaded가 크게 감소
3. history/back/return 시 **기존 DOM 또는 scroll/state를 복원**

지금 global-nav는 셋 다 거의 없다.

## 3. How — 어떻게 만들 것인가

### 3.1 Surface taxonomy
글로벌 네비는 반드시 세 그룹으로 다룬다.

#### 3.1.1 G1-A — swap-eligible shared-layout family
초기 후보:

- `/`
- `/?status=RECEIVED`
- `/?status=MEASURE`
- `/?region=metro`
- `/?region=regional`
- `/trash`

조건:
- 같은 layout family를 사용하고
- 같은 `#main-content` 교체 contract를 가질 수 있으며
- 필터/페이지네이션/권한 의미가 동일하게 보존되는 경우

이 그룹만 **real fast swap** 대상으로 허용한다.

#### 3.1.2 G1-B — shared-layout candidate but contract not yet proven
초기 후보:

- `/storage_dashboard`
- `/regional_dashboard`
- `/metropolitan_dashboard`
- `/self_measurement_dashboard`

이 경로들은 top-nav에서 자주 쓰이지만, B0/B1에서 실제 layout/body/shell parity가 증명되기 전까지는 G1-A로 승급시키지 않는다.

증명 전 허용:
- document warmup
- preconnect / dns-prefetch
- safe document prefetch

증명 전 금지:
- body swap
- shell fragment swap

#### 3.1.3 G2 — cross-surface tool entries
- `/erp/dashboard`
- `/wdplanner`
- WDCalculator canonical web route
- `/chat`
- `/admin`

이 그룹은 **body swap 금지**다.

허용:
- preconnect
- dns-prefetch
- safe document prefetch
- speculationrules prerender (브라우저/세션/권한 제약을 만족할 때만)
- 공통 자산 warmup

#### 3.1.4 G3 — excluded action/write/auth-sensitive paths
- write side-effect가 있거나
- GET이어도 stateful side-effect가 강하거나
- 클릭 전에 speculative fetch가 위험한 경로

이 그룹은 warmup/swap 대상이 아니다.

### 3.2 Runtime architecture

#### 3.2.1 global-nav-runtime의 역할 재정의
`static/js/global-nav-runtime.js`는 현재 prefetch hint 스크립트에서 아래 역할로 진화한다.

1. G1-A 링크 hover/focus 시:
   - debounce 후 `fetch(view=nav-fragment)` 또는 동등 contract로 HTML body를 받아 메모리 캐시에 저장
2. G1-A 링크 click 시:
   - warm hit면 즉시 `#main-content` swap
   - cold면 fragment fetch 후 swap
   - 실패 시 normal navigation fallback
3. G1-B / G2 링크 hover/focus 시:
   - document warmup only
   - 클릭 interception 없음
4. back/forward 시:
   - G1-A 경로는 cached body/scroll restore 시도
   - 실패 시 full navigation fallback

#### 3.2.2 Client cache key
browser-side cache key는 최소 아래를 포함한다.

- canonical pathname
- normalized query string
- active user fingerprint
- optional family id

원칙:
- 다른 사용자/권한/필터 결과가 섞이면 안 된다.
- same URL but different query order는 같은 key로 normalize한다.

#### 3.2.3 History / scroll / restore
G1-A는 ERP shell과 유사하게 아래를 지원해야 한다.

- `pushState`
- `popstate`
- scroll memory
- warm return

단, top-nav 전용 runtime은 ERP shell과 분리된 책임을 가진다.

### 3.3 Server contract

#### 3.3.1 G1-A용 dual-mode
G1-A route는 full document와 nav fragment 두 모드를 가져야 한다.

권장 contract:
- request header: `X-FOMS-GNAV: 1`
- query: `view=nav-fragment`
- response header: `X-FOMS-GNAV-FRAGMENT: 1`
- optional response header: `X-FOMS-GNAV-FAMILY: <family-id>`

원칙:
- full mode와 fragment mode는 동일 business result를 가져야 한다.
- full document는 fragment renderer를 조합해 만드는 single truth 구조여야 한다.

#### 3.3.2 G1-B / G2는 server dual-mode를 강제하지 않음
이 그룹은 우선 document warmup만 한다.

즉:
- body fragment contract가 준비되기 전까지는 클릭 interception 금지
- 문서·자산 warmup으로만 체감 개선

### 3.4 Asset strategy

#### 3.4.1 G1-A
- same-family 문서에서 중복 로딩되는 JS/CSS는 가능한 한 공통화
- fragment swap 시 필요한 스크립트만 재실행
- 항상 필요 없는 page JS는 page-scoped asset으로 지연

#### 3.4.2 G2
- 클릭 전에 아래를 warmup
  - origin preconnect
  - route-adjacent CSS/JS
  - prerender-safe document

### 3.5 Non-negotiable safety line
아래는 절대 금지다.

1. G2 cross-surface body swap
2. G1-B를 증거 없이 G1-A로 승격
3. same-family처럼 보이게 하려고 결과를 줄이거나 감추는 것
4. 클릭 즉시성을 위해 URL/history를 숨기는 것
5. JS off에서 깨지는 구조

## 4. Execution batches

### GNV-B0 — Global-nav inventory + family proof freeze
목표:
- top-nav authoritative inventory 확정
- 각 링크를 G1-A / G1-B / G2 / G3로 동결
- candidate route의 layout/body contract를 실제 코드 기준으로 판정

수정 대상:
- `foms/services/menu_config.py`
- `templates/partials/shared/layout_nav.html`
- `docs/plans/2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`
- 신규 run record

Acceptance:
- top-nav inventory 표 완성
- 각 링크의 family class와 이유 기록
- “왜 지금은 체감이 없는가”를 코드/증거로 문서화

Stop rule:
- 이 배치에서 body swap 구현 금지
- 근거 없이 G1-A 확대 금지

### GNV-B1 — G1-A server contract freeze
목표:
- G1-A route의 full vs nav-fragment single-truth contract를 고정

수정 대상:
- `foms/web/orders/listing.py`
- `foms/web/orders/trash.py`
- 필요한 공통 helper 예: `foms/services/common/global_nav_http.py`
- 관련 템플릿/partial

Acceptance:
- G1-A route가 `view=nav-fragment` 또는 동등 contract를 지원
- `X-FOMS-GNAV-FRAGMENT` 헤더 계약 고정
- full/fragment parity tests green

Stop rule:
- G1-B/G2를 같이 열지 말 것
- ERP shell helper를 무분별하게 재사용해 contract를 섞지 말 것

### GNV-B2 — G1-A client warm swap
목표:
- G1-A 클릭 시 실제로 warm fragment hit → instant swap

수정 대상:
- `static/js/global-nav-runtime.js`
- `templates/partials/shared/layout_scripts.html`
- 관련 tests

Acceptance:
- hover/focus prefetch가 실제 fragment fetch + memory cache로 동작
- click 시 warm hit면 즉시 body swap
- miss면 fetch 후 swap
- 실패 시 full nav fallback
- pushState/popstate/scroll restore 동작

Stop rule:
- G2까지 interception 확대 금지
- body swap으로 인한 의미 차이 발생 금지

### GNV-B3 — G1-B proof or defer
목표:
- `/storage_dashboard`, `/regional_dashboard`, `/metropolitan_dashboard`, `/self_measurement_dashboard`를
  - G1-A로 승격하거나
  - G1-B document-only로 고정

Acceptance:
- 각 경로에 대해 승격/보류 이유가 명확
- 승격한 경로만 fragment-capable list 편입

Stop rule:
- “비슷해 보인다”만으로 승격 금지

### GNV-B4 — G2 cross-surface warm document
목표:
- `/erp/dashboard`, `/wdplanner`, `WDCalculator`, `/chat`, `/admin` 체감 지연 완화

수정 대상:
- `static/js/global-nav-runtime.js`
- `templates/partials/shared/layout_head.html`
- `templates/partials/shared/layout_scripts.html`

Acceptance:
- G2는 클릭 interception 없이 document warmup만 적용
- preconnect/dns-prefetch/prerender-safe warmup 동작
- same-origin / auth-safe / opt-in 규칙 고정

Stop rule:
- G2 body swap 금지
- 타 앱 ownership 침범 금지

### GNV-B5 — Global-nav page-scoped asset hardening
목표:
- global-nav로 자주 이동하는 화면의 공통 자산 재부팅 비용 최소화

Acceptance:
- top-nav 이동에 자주 쓰이는 화면에서 불필요한 global JS/CSS가 page-scoped로 빠짐
- G1/G2 모두 JS off fallback 유지

### GNV-B6 — Railway staging evidence
목표:
- “체감이 빨라졌다”를 실제로 증명

필수 비교:
- G1-A full reload baseline
- G1-A cold click
- G1-A warm click
- G1-A back/forward restore
- G2 cold click
- G2 warm document click
- click-to-first-content-paint
- route total / starttransfer / body swap time

Acceptance:
- before/after 표와 브라우저 증거 존재
- 미달 시 원인 분류: `HTML | render | asset | query | prefetch miss`

### GNV-B7 — Final GDM audit closeout
목표:
- global-nav lane만 따로 final audit

Acceptance:
- High 0 / Medium 0
- 문서/코드/증거 1:1 정합
- 과대주장 없음

## 5. Verification

### 5.1 로컬
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- global-nav focused pytest
- full/fragment parity tests
- JS off fallback tests
- history/back-forward tests

### 5.2 브라우저/운영
- G1-A warm click evidence
- G1-A cold click evidence
- G1-A back/forward restore evidence
- G2 warm document evidence
- top-nav click-to-paint evidence
- Railway staging before/after evidence

## 6. Final closeout gate
아래를 모두 만족할 때만 closeout 가능하다.

1. G1-A는 실제 체감 가능한 warm swap을 제공한다.
2. G1-B는 승격/보류가 명확하다.
3. G2는 fake SPA 없이 warm document 체감 개선을 제공한다.
4. top-nav 최적화가 URL/history/권한/본문 의미를 바꾸지 않는다.
5. Railway evidence가 있다.
6. final GDM review에서 High 0 / Medium 0이다.

## 7. LLM kickoff contract
이 계획서를 집행하는 LLM은 반드시 아래 순서로 시작한다.

1. `AGENTS.md`
2. `docs/harness/policy/DECISIONS.md`
3. `docs/ARCHIVE_INDEX.md`
4. `docs/plans/2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`
5. `docs/plans/2026-04-17-global-nav-real-speed-execution-plan.md`
6. 현재 global-nav 관련 구현 파일

첫 응답 형식:
1. 현재 global-nav 구현이 왜 체감이 없는지 10줄 이내 요약
2. `GNV-B0` scope / acceptance / stop rule 재진술
3. inventory + family proof 방식을 설명
4. 바로 `GNV-B0`부터 시작

Hard stop:
- G2 cross-surface를 body swap으로 처리
- G1-B를 근거 없이 G1-A로 승격
- semantic-preserving을 깨뜨리는 변경
- 운영 증거 없이 “체감 개선 완료” 주장
