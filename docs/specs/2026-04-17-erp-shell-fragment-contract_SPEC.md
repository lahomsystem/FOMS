# ERP Shell / Fragment / Heavy — Contract SPEC
> 작성일: 2026-04-17 | 배치: EPT-B1 (freeze), **EPT-B2** (PRIMARY_NAV / FRAGMENT_READY), **EPT-B3** (core 4 dual-mode + tier header), **EPT-B4** (secondary 5 primary fragment — FRAGMENT_READY = 9 primary) | 상위 계획: `docs/plans/2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`

## 1. 목적
- **§2 잠금판 9 primary** 각각에 대해 **full HTML**과 **fragment HTML**(shell 요청 시)이 동일한 비즈니스 결과를 내야 한다는 계약을 고정한다. (코어 4 + secondary 5 — EPT-B3·B4)
- **EPT-B2**: 잠금판 **9 primary** (`ERP_PRIMARY_NAV_PATHS`)와 **fragment fetch 허용 경로** (`ERP_FRAGMENT_READY_PATHS`)를 상수로 둔다. **EPT-B4 이후** 두 튜플은 **동일 9경로·동일 순서**이다. 클라이언트는 **FRAGMENT_READY**에만 `view=fragment` fetch를 시도한다. 상세: `docs/plans/2026-04-17-ept-b2-erp-shell-safe-nav-run-record.md`, B4: `docs/plans/2026-04-17-ept-b4-secondary-primary-shell-fragment-run-record.md`.
- Primary 9개 dual-mode는 EPT-B3·B4에서 반영되었다. Subordinate·prefetch 등은 후속 배치에서 본 SPEC **의미 변경 없이**만 확장한다.

## 2. Canonical URL (변경 금지) — FRAGMENT_READY = 잠금판 9 primary
아래 **9 path**는 **ERP_PRIMARY_NAV_PATHS**, **ERP_FRAGMENT_READY_PATHS**, **ERP_CANONICAL_TAB_PATHS** (동일 순서·동일 튜플 객체)이다. (EPT-B4 closeout)

| Tab id | Path | 비고 |
|--------|------|------|
| dashboard | `/erp/dashboard` | deep-link |
| measurement | `/erp/measurement` | deep-link |
| drawing_workbench | `/erp/drawing-workbench` | list/dashboard; detail은 B5 |
| production | `/erp/production/dashboard` | deep-link |
| shipment | `/erp/shipment` | deep-link |
| as | `/erp/as` | deep-link |
| construction | `/erp/construction/dashboard` | deep-link |
| completion | `/erp/completion` | deep-link |
| history | `/erp/history/` | trailing slash canonical |

- 새로운 공개 fragment 전용 URL을 남발하지 않는다. 동일 path에 dual-mode로 응답한다.
- **Subordinate** 페이지는 본 SPEC §2에 포함되지 않으며 EPT-B5+에서 별도 계약한다.

## 3. 요청 모드 판별
### 3.1 Full page (document)
- 브라우저가 일반 GET으로 요청하고, shell 헤더가 없거나 비활성인 경우.
- `view` 쿼리가 없거나, 알려진 fragment 값이 아닌 경우 → **전체 문서** (기존 JS off / 직접 방문 / 새로고침).

### 3.2 Shell fragment fetch
- 요청 헤더: `X-FOMS-ERP-SHELL: 1` (상수: `foms.services.common.erp_navigation_contract`).
- 권장 쿼리: `view=fragment` | `view=critical` | `view=heavy` (동일 모듈 상수).
- 서버는 동일 라우트 핸들러에서 **동일 컨텍스트·동일 micro-cache 조립**으로 **본문 HTML fragment**를 반환한다 (`foms.services.common.erp_shell_http`).
- 응답 헤더: `X-FOMS-ERP-FRAGMENT: 1` 및 **`X-FOMS-ERP-FRAGMENT-TIER: fragment|critical|heavy`** (EPT-B3). 클라이언트 기본 탭 스왑은 `view=fragment` 유지.

### 3.3 의미 매핑
| view | 용도 |
|------|------|
| (omit) | Full document |
| critical | 탭 이해에 필요한 상단 KPI/핵심 필터/첫 화면 (향후 partial 분리용; **EPT-B3**에서는 코어 4페이지에서 **fragment와 동일 본문** + tier 헤더만 구분) |
| heavy | 대형 테이블·접힌 상세·지연 로드 블록 (동일: **EPT-B3** 동일 본문 + tier 헤더) |
| fragment | 기본 본문 스왑용( critical+heavy 조합 정책은 구현에서 단일화) |

## 4. History / URL
- Shell은 **canonical URL**을 유지한다: `pushState`/`replaceState`는 실제 주소와 검색 파라미터를 반영해야 한다.
- `popstate` 시 shell이 동일 contract로 fragment를 다시 맞춘다.

## 5. GET 필터 / 정렬 / 페이지네이션
- 모든 GET 기반 변화는 **full reload 없이도** shell이 동일 query string으로 fragment fetch 할 수 있어야 한다 (EPT-B2+).
- Non-JS: 기존처럼 `<form method="get">` / 링크가 **전체 문서 네비게이션**으로 동작 — 계약상 유지.

## 6. Browser-side tab cache 키 경계
다음을 모두 포함해 분리한다 (클라이언트 구현; EPT-B5+).
- canonical path
- `normalize_erp_query_for_cache_fingerprint(request.args)`와 동등한 정규화 query
- 활성 사용자 식별(세션과 일치하는 서버측 권한과 동일한 범주)
- tab id (`ERP_TAB_IDS` — 9개, `ERP_PATH_TO_TAB_ID`와 동기화)

## 7. Micro-cache
- Dashboard micro-cache (Redis slice, `foms.services.common.dashboard_cache`)는 **유지**한다 (`MICRO_CACHE_READ_SLICES_RETAINED = True`).
- 전체 HTML 캐시는 금지(상위 계획 §1.3).

## 8. 코드 단일 진실
- 상수·헤더명·view 문자열: `foms/services/common/erp_navigation_contract.py`
- 본 SPEC과 충돌 시 **SPEC + DECISIONS 갱신 후** 상수 변경.

## 9. Authoritative HTML surface inventory (EPT-B1 재동결)
- 브라우저에서 직접 열 수 있는 **ERP 관련 HTML GET** 경로의 **전수 목록(9 primary, subordinate, descendant, 연관 대면)**은 다음 run record에 동결한다:  
  `docs/plans/2026-04-17-ept-b1-baseline-contract-run-record.md` §8 (inventory v2).
- 본 문서 §2의 **9 path**가 **현재 코드·pytest·`erp_navigation_contract`·`runtime-shell.js`**에 반영된 shell/fragment canonical primary이다. **Tier E** 비-`/erp/` 대면은 인벤토리에 포함되며 shell 본문 계약은 별도다. **EPT-B4**에서 secondary 5 primary를 편입해 **FRAGMENT_READY = PRIMARY_NAV (9)**로 정렬하였다.
