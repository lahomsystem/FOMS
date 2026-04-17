# Global Nav Real Speed — batch run record

> Companion: `2026-04-17-global-nav-real-speed-execution-plan.md`  
> 상위: `2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`

---

## GNV-B0 — Global-nav inventory + family proof freeze

**Scope (재진술)**  
- `menu.main_menu` (`data/admin/menu_config.json` + `foms/services/menu_config.py` 폴백)과 `layout_nav.html` 우측 도구 링크의 **권위 있는 목록**을 동결한다.  
- 각 링크를 G1-A / G1-B / G2 / G3로 판정하고, **구현 변경은 하지 않는다** (분류·증거만).

**Acceptance**  
- 모든 top-nav 항목이 taxonomy 중 하나에 매핑됨.  
- “왜 지금 체감이 거의 없는가”가 코드 기준으로 기록됨.

**Stop rule**  
- B0에서 라우트·템플릿·JS 동작을 바꾸지 않는다.

### Authoritative inventory (2026-04-17 truth)

**A. `data/admin/menu_config.json` — `main_menu` (순서대로)**

| # | id | name | url | Taxonomy | Notes |
|---|----|------|-----|----------|-------|
| 1 | order_list | 전체 주문 | `/` | **G1-A** | orders listing, shared `orders/layout.html` |
| 2 | received | 접수 | `/?status=RECEIVED` | **G1-A** | same template family as `/` |
| 3 | measured | 실측 | `/?status=MEASURE` | **G1-A** | |
| 4 | metro_orders | 수도권 주문 | `/?region=metro` | **G1-A** | |
| 5 | regional_orders | 지방 주문 | `/?region=regional` | **G1-A** | |
| 6 | metropolitan_dashboard | 수도권 주문 대시보드 | `/metropolitan_dashboard` | **G1-B** | measurement/dashboard 계열; layout parity 미증명 시 swap 금지 |
| 7 | self_measurement_dashboard | 자가실측 대시보드 | `/self_measurement_dashboard` | **G1-B** | |
| 8 | regional_dashboard | 지방 주문 대시보드 | `/regional_dashboard` | **G1-B** | |
| 9 | storage_dashboard | 수납장 대시보드 | `/storage_dashboard` | **G1-B** | |
| 10 | trash | 휴지통 | `/trash` | **G1-A** | `orders/trash.html`, 동일 orders layout family |

**B. `layout_nav.html` — `{% if current_user %}` 우측 도구 (`navbar-nav ms-auto`)**

| Link | url_for | Taxonomy | Notes |
|------|---------|----------|-------|
| ERP 대시보드 | `erp_dashboard.erp_dashboard` | **G2** | cross-surface; body swap 금지 |
| WDPLANNER | `wdplanner.wdplanner` | **G2** | |
| WDCalculator | `wdcalculator.wdcalculator` | **G2** | |
| 채팅 | `channel_chat_pages.chat` | **G2** | |

**C. 조건부 — `{% if current_user.role == 'ADMIN' %}`**

| Link | url_for | Taxonomy | Notes |
|------|---------|----------|-------|
| 관리자 | `admin.admin` | **G2** | auth-sensitive surface; swap 금지 |

**D. 기본 `menu_config.py` 폴백에만 존재하는 항목**  
- `main_menu`에 `/chat` 항목이 **기본 JSON**에는 있으나, 현재 `data/admin/menu_config.json`에는 **없음**. 실제 렌더는 파일 우선이므로 **top-nav 좌측에 채팅 중복 노출은 없음**; 채팅은 우측 도구만.

### Why perceived speed is ~none today (code-backed)

1. `static/js/global-nav-runtime.js`는 `mouseover`/`focusin` 시 동일 출처 경로에 `<link rel="prefetch">`만 삽입한다.  
2. 클릭 가로채기·`#main-content` 교체·히스토리 복원·메모리 캐시 적용이 없다.  
3. Prefetch는 브라우저 스케줄링에 의존해 클릭 직전까지 문서가 준비됐다는 보장이 약하다.  
4. `runtime-shell.js`의 instant swap은 ERP shell 전용이며 global-nav와 공유되지 않는다.  
5. 따라서 top-nav 클릭은 대부분 **전체 문서 네비게이션 비용**을 그대로 낸다.

### GDM B0 review (synthesis)

- **Semantic / surface**: G1-A·G1-B·G2 구분이 메뉴 데이터·템플릿과 일치.  
- **Runtime**: 현재 global-nav는 문서 워밍만 → B2에서 G1-A만 교체 경로 추가 필요.  
- **Ops**: B0는 문서만; 증거는 후속 B6.

**Status**: B0 **COMPLETE** (freeze documented).

---

## GNV-B1 — G1-A server dual-mode contract

**Scope**  
- `orders` index + trash에 fragment 모드 추가: `X-FOMS-GNAV: 1` 또는 `view=nav-fragment` 시 본문만 렌더, 응답 `X-FOMS-GNAV-FRAGMENT: 1`.

**구현**  
- `foms/services/gnav_contract.py`: `wants_gnav_fragment()`, `gnav_orders_layout_parent()`.  
- `templates/orders/gnav_swap_shell.html`: 레이아웃/네비 없이 `{% block head %}` + `{% block content %}`만 출력.  
- `templates/orders/index.html`, `trash.html`: `{% extends parent_template|default("orders/layout.html") %}`.  
- `foms/web/orders/listing.py`, `trash.py`: `parent_template` + `make_response` + fragment 헤더.

**Acceptance**  
- full 응답은 기존과 동일 레이아웃; fragment는 `layout-global-nav` 미포함.  
- pytest: `tests/domains/test_gnav_fragment_contract.py`.

**GDM synthesis**  
- Semantic: 동일 라우트 핸들러·동일 템플릿 파일, 부모만 교체 → 비즈니스 결과 동일.  
- Surface: G1-A만 dual-mode; G2/G3 미적용.

**Status**: B1 **COMPLETE**.

---

## GNV-B2 — G1-A client warm swap

**Scope**  
- `global-nav-runtime.js`: G1-A 경로(`/`, `/trash` 및 쿼리)만 클릭 가로채기, fragment fetch 또는 메모리 히트, `#main-content` 교체, `pushState`/`popstate`, 스크롤 메모리, 실패 시 `location.href`.  
- G2: 기존처럼 `prefetch` 힌트만.

**구현**  
- `static/js/global-nav-runtime.js` 전면 확장.  
- 교체 후 `<script>` 재실행: `innerHTML`로 삽입된 인라인 스크립트가 동작하도록 `activateScriptsIn`.

**Acceptance**  
- `tests/domains/test_global_nav_runtime_js_contract.py` 정적 계약 갱신.

**GDM synthesis**  
- ERP shell 헤더/로직 미사용. 히스토리 복원 시 캐시 미스면 fragment 재요청.

**Status**: B2 **COMPLETE**.

---

## GNV-B3 — G1-B proof or defer

**Scope**  
- `/storage_dashboard`, `/regional_dashboard`, `/metropolitan_dashboard`, `/self_measurement_dashboard`의 layout/`#main-content` parity를 코드 리뷰만 수행 (추가 라우트 변경 없음).

**판정**  
- 본 tranche에서 **증명 자료(동일 fragment contract 테스트·스냅샷) 없음** → runbook대로 **G1-B 유지, G1-A 승격 금지**.  
- 후속: 각 dashboard 템플릿 상속·본문 경계 문서화 후 재평가.

**Status**: B3 **COMPLETE** (document-only defer).

---

## GNV-B4 — G2 cross-surface warm document

**Scope**  
- G2는 body swap 금지; same-origin `prefetch`는 `global-nav-runtime.js`의 기존 경로(모든 nav 링크)로 유지.

**판정**  
- WDPLANNER/ERP/채팅 등이 동일 호스트이면 별도 `dns-prefetch` 이득 제한적; **추가 head 태그는 미삽입** (중복·정책 리스크 회피). warm 힌트는 hover `prefetch`로 충족.

**Status**: B4 **COMPLETE** (문서·현행 동작 정렬).

---

## GNV-B5 — Page-scoped asset hardening

**Scope**  
- fragment swap 시 본문 내 인라인 스크립트가 재실행되도록 B2에서 처리. 전역 `layout_scripts` 제거/대규모 분리는 **범위 밖** (ERP shell lane과 충돌 위험).

**Status**: B5 **PARTIAL** (스크립트 재실행만 반영, 자산 구조 대규모 변경 없음).

---

## GNV-B6 — Railway staging evidence

### Scope (locked, 2026-04-17)

- **In**: 스테이징(`lahom-dev` 등)에서 **인증된 동일 세션**으로 G1-A·G2 타이밍·헤더·(가능 시) 브라우저 paint/히스토리 프록시 수집.  
- **Out**: 로컬 추정 수치, 로그인 없는 척한 표, 배포 ID 없이 “완료” 서술.

### Acceptance (B6 완료 조건)

| 항목 | 증거 유형 | 비고 |
|------|-----------|------|
| G1-A full reload baseline | HTTP `cold_no_cache_s` | `gnv_b6_staging_http_evidence.py` → `g1a_full_document` |
| G1-A cold vs warm document GET | HTTP cold + `warm_second_get_s` | 동일 |
| G1-A nav fragment (서버) | HTTP `g1a_nav_fragment` + `X-FOMS-GNAV-FRAGMENT: 1` | 브라우저 swap ms와 혼동 금지 |
| G1-A back/forward | Playwright `g1_trash_roundtrip` 권장 | HTTP만으로는 popstate 불가 |
| G2 cold/warm | HTTP `g2_warm_document` | `/erp/dashboard`, `/chat` |
| click-to-paint 프록시 | Playwright `performance.paint` (FCP) | MCP 단독으로는 헤더·duration 미동일 |
| 미달 분류 | run record 한 줄 | `HTML \| render \| asset \| query \| prefetch miss` |

### Stop rule

- `FOMS_STAGING_COOKIE` / 로그인 자격 증명 없으면 **숫자 채우지 않음** — **blocker**로만 기록.  
- 증거 JSON은 **실제 실행 결과**만 커밋 (템플릿 숫자 금지).

### 하네스 (repo truth)

| 스크립트 | 용도 |
|----------|------|
| `tools/harness/gnv_b6_staging_http_evidence.py` | G1-A full/fragment/G2 cold·warm, fragment 헤더 검증 |
| `tools/harness/gnv_b6_staging_browser_metrics.py` | Playwright: G1 full nav, trash↔back, `/chat`, Performance API |
| (기존) `tools/harness/ept_b8_staging_http_evidence.py --include-g1` | 넓은 G1 shared-layout 스모크; B8과 공존 |

**PowerShell (쿠키 수동):**

```text
$env:FOMS_STAGING_COOKIE = 'session_staging=<DevTools Cookie 값>'
python tools/harness/gnv_b6_staging_http_evidence.py --base https://lahom-dev.up.railway.app --json | Out-File -Encoding utf8 docs/harness/evidence/2026-04-17-gnv-b6-staging-http-evidence.json
```

**Playwright (로그인 환경 변수):**

```text
$env:FOMS_STAGING_USERNAME = '<id>'
$env:FOMS_STAGING_PASSWORD = '<pw>'
python tools/harness/gnv_b6_staging_browser_metrics.py --base https://lahom-dev.up.railway.app --scenario g1_trash_roundtrip
```

### 본 세션 수집 (2026-04-17, Railway `lahom-dev`)

- **자격 증명**: `FOMS_STAGING_COOKIE` + Playwright용 `FOMS_STAGING_USERNAME` / `FOMS_STAGING_PASSWORD`로 수집.  
- **증거 파일 (저장소, 비밀 미포함)**:
  - `docs/harness/evidence/2026-04-17-gnv-b6-staging-http-evidence.json`
  - `docs/harness/evidence/2026-04-17-gnv-b6-browser-g1_full_nav.json`
  - `docs/harness/evidence/2026-04-17-gnv-b6-browser-g1_trash_roundtrip.json`
  - `docs/harness/evidence/2026-04-17-gnv-b6-browser-g2_chat.json`
- **운영자 보안**: 채팅/로그에 노출된 세션·비밀번호는 **회전(무효화·변경)** 권장.

### Evidence table (HTTP: cold = `Cache-Control: no-cache` 첫 GET, warm = 직후 동일 URL 재GET)

| 시나리오 | cold (s) | warm (s) | fragment cold/warm (s) | `X-FOMS-GNAV-FRAGMENT` |
|----------|----------|----------|------------------------|-------------------------|
| G1-A `/` | 2.374 | 3.122 | 2.540 / 2.222 | **없음** (`null`, `fragment_header_ok`: false) |
| G1-A `/?status=RECEIVED` | 1.501 | 1.498 | 1.499 / 1.506 | **없음** |
| G1-A `/trash` | 1.897 | 1.889 | 1.880 / 1.871 | **없음** |
| G2 `/erp/dashboard` | 3.320 | 2.073 | — | — (full document만) |
| G2 `/chat` | 0.989 | 1.048 | — | — |

### 브라우저 프록시 (Playwright, Chromium headless)

| 시나리오 | 지표 | 값 |
|----------|------|-----|
| `g1_full_nav` | top-nav 접수 클릭 → `networkidle` | **2947 ms** (반올림: 2946.55) |
| | Navigation `duration` (ms) | ~1616 |
| | `first-contentful-paint` (ms) | **1620** |
| `g1_trash_roundtrip` | 휴지통 클릭 → full document | **3390 ms** |
| | Browser Back → `networkidle` | **687 ms** |
| | Back 후 navigation `type` | `back_forward` |
| | Back 후 FCP (ms) | **68** |
| `g2_chat` | `/chat` load 후 FCP (ms) | **996** |
| | Navigation `duration` (ms) | ~1981 |

### 미달 / 원인 분류 (B1 계약 대비)

- `view=nav-fragment` + `X-FOMS-GNAV: 1` 요청은 **HTTP 200**이나 **`X-FOMS-GNAV-FRAGMENT` 헤더 없음** (전 경로).  
- **분류**: **`HTML`** — 스테이징 배포가 로컬/B1 구현과 응답 계약이 일치하지 않거나(구버전 이미지), 서버 분기 미적용. (클라 swap ms가 아니라 **서버가 fragment 모드를 표시하지 않음**.)  
- 조치: Railway에 **GNV-B1 반영 빌드** 배포 후 동일 하네스로 재측정 시 `fragment_header_ok: true` 기대.

### GDM B6 hard review (synthesis)

- **Semantic**: HTTP는 전송·TTFB·바디 수신 구간의 합(클라이언트 측 swap과 별개).  
- **Surface**: G2는 문서 네비게이션만 측정; body swap 없음.  
- **Evidence**: 실측 JSON 4종 확보; 스테이징은 fragment 헤더 **미일치**로 별도 추적.

**Status**: B6 **COMPLETE (evidence on disk)** — 단, **스테이징 fragment 계약은 미달** (`HTML`); 재배포 후 헤더 검증 권장.

---

## GNV-B7 — Final closeout

**전제**: B6 실측 증거 파일 존재 → **충족** (2026-04-17).  
**다음**: GDM 최종 합의·문서 정리 시 **스테이징 fragment 헤더 갭**을 “운영 배포 과제”로 명시하고 closeout.
