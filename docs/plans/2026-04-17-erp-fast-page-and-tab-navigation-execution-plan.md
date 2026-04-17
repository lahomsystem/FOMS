# ERP Fast Page + Tab Navigation Execution Plan
> 작성일: 2026-04-17 | 상태: 🟢 GDM 감리 완료, 실행 준비
>
> **재개 동결 (EPT-R0)**: 저장소 대비 잠금판 갭·라우트 인벤토리·다음 배치 순서 — `docs/plans/2026-04-17-ept-r0-resume-audit-freeze-run-record.md`

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
ERP 메인 shell에 속한 모든 primary page와 그 하위 subordinate page/subpage를 오갈 때,

- 첫 진입 페이지는 지금보다 훨씬 가벼운 **ERP 공통 셸 + 선택 탭의 critical fragment**만 먼저 보여주고
- 탭 전환은 **full reload 없이 partial HTML fetch + browser-side tab cache + idle prefetch**로 처리하며
- 깊은 링크, 새로고침, 북마크, 뒤로가기/앞으로가기는 기존 URL 그대로 유지하는

하이브리드 ERP 네비게이션 구조를 만든다.

이 tranche의 최종 목표는 둘 다 만족하는 것이다.

1. **빠른 페이지**  
   첫 진입 시 서버 응답과 초기 렌더의 체감 지연을 줄인다.
2. **빠른 탭 전환**  
   ERP 내부 탭 이동은 로컬 앱처럼 즉각적으로 느껴지게 만든다.

### 1.2 기능 요구사항
1. 기존 ERP primary page URL은 그대로 canonical deep-link로 유지한다.
2. direct visit / 새로고침 / JS off 환경에서는 기존처럼 각 URL이 독립적으로 동작해야 한다.
3. JS on 환경에서는 ERP 공통 셸이 primary page 이동을 가로채고, **본문만 partial HTML로 교체**해야 한다.
4. primary page 클릭 시 기본 동작은 full reload가 아니라 in-page swap이어야 한다.
5. subordinate page/subpage는 shell 위에서 열리거나, 최소한 shell과 자연스럽게 왕복되는 동일 네비게이션 contract를 가져야 한다.
6. 현재 페이지 로드 후 idle 시점에 다음 유력 ERP page를 prefetch 해야 한다.
7. browser-side tab/page cache는 **현재 사용자 + 현재 URL + 현재 필터 fingerprint** 기준으로 분리되어야 한다.
8. ERP primary page는 **critical fragment**와 **heavy fragment**를 분리할 수 있어야 한다.
9. `dashboard`와 `as`의 초기 entry HTML/raw fragment 크기는 현재 staging 실측(약 1.0MB, 1.1MB)보다 명확히 작아져야 한다.
10. 현재 micro-cache는 유지하고, partial navigation 구조 위에서 계속 사용해야 한다.
11. 탭 전환/페이지 진입 성능은 local-only 주장이 아니라 Railway staging/prod-like 실측으로 증명해야 한다.
12. primary page 내부의 GET 기반 필터/페이지네이션/정렬 변화도 shell 안에서 처리 가능한 동일 contract를 가져야 한다.
13. ERP shell 범위는 최소 아래 primary surface를 포함해야 한다.
   - `/erp/dashboard`
   - `/erp/measurement`
   - `/erp/drawing-workbench`
   - `/erp/production/dashboard`
   - `/erp/shipment`
   - `/erp/as`
   - `/erp/construction/dashboard`
   - `/erp/completion`
   - `/erp/history/`
14. subordinate surface는 최소 아래 대표 경로를 포함해야 한다.
   - `/erp/drawing-workbench/<order_id>`
   - `/erp/orders/<order_id>` (legacy redirect contract)
   - `/edit/<order_id>?open=erp-beta`

### 1.3 예외/제약 조건
- 기존 권한, 필터, 정렬, 페이지네이션, KPI 의미를 바꾸면 안 된다.
- 전체 HTML cache는 금지한다.
- SPA 프레임워크 신규 도입은 이번 tranche 비대상이다.
- DB schema 변경, migration 추가, index 추가는 기본 범위에서 제외한다.
- 다만 shipment/as profiling 결과가 **query 병목 없이는 목표 수치 달성이 불가능**하다고 판명되면, 별도 후속 tranche로 분리해 연다.
- 현재 micro-cache를 롤백하는 것은 기본 전략이 아니다.
- 기능 의미를 바꾸지 못하는 범위에서만 shell/partial/prefetch를 적용한다.
- 사용자가 보는 결과가 줄어들거나 덜 정확해지는 방식의 “속도 개선”은 금지한다.
- 이 문서에서 말하는 성능 개선은 **기능 축소 없는 로딩 방식 최적화**만 의미한다.

## 2. Why — 왜 이 방식이 필요한가

### 2.1 현재 staging 실측
로그인 후 staging에서 같은 쿠키로 반복 GET한 결과다. 현재 실측 로그는 core 4개에 먼저 모여 있지만, **이번 계획의 구현/closeout 범위는 ERP read-navigation surface 전체**다:

| URL | 1회차 total | 2회차 total | 1회차 starttransfer | 2회차 starttransfer | 응답 크기 |
|-----|-------------|-------------|---------------------|---------------------|-----------|
| `/erp/dashboard` | 3.79s | 2.34s | 3.43s | 1.97s | 1,007,853 bytes |
| `/erp/measurement` | 3.38s | 1.91s | 3.18s | 1.89s | 168,798 bytes |
| `/erp/shipment` | 2.09s | 2.06s | 1.95s | 2.00s | 216,120 bytes |
| `/erp/as` | 2.71s | 2.46s | 2.32s | 2.32s | 1,102,349 bytes |

반면 로그인 페이지와 정적 CSS는 0.1~0.3초대였다.  
즉, 플랫폼 baseline보다 **인증 후 ERP 페이지 내부 비용**이 훨씬 크다.

### 2.2 현재 병목 해석
- `dashboard`, `measurement`는 micro-cache 효과가 보이지만, full reload와 큰 HTML 때문에 체감이 제한된다.
- `shipment`, `as`는 현재 micro-cache만으로는 체감이 거의 안 난다.
- 특히 `dashboard`와 `as`는 응답 HTML이 1MB를 넘어서, 서버 시간 감소만으로는 “즉각성”이 나오기 어렵다.
- 따라서 **서버 compute 최적화**와 함께 **네비게이션 모델 자체**를 바꿔야 한다.

### 2.3 왜 shell + partial + prefetch인가
- 지금 앱은 Flask + Jinja 기반이고, full SPA rewrite는 과하다.
- partial HTML fetch는 현재 서버 렌더 구조를 재사용하면서도, full reload 비용을 없앨 수 있다.
- prefetch는 사용자가 자주 오가는 ERP 탭 체감 속도를 크게 줄인다.
- micro-cache는 partial fragment를 더 빨리 만드는 보조 계층으로 계속 가치가 있다.

## 3. How — 어떻게 만드는가

### 3.1 최종 아키텍처

#### 3.1.0 ERP surface taxonomy
이번 tranche에서 다루는 ERP surface는 **ERP read-navigation surface 전체**를 기준으로 세 층으로 나눈다.

1. **Primary shell pages**
   - `/erp/dashboard`
   - `/erp/measurement`
   - `/erp/drawing-workbench`
   - `/erp/production/dashboard`
   - `/erp/shipment`
   - `/erp/as`
   - `/erp/construction/dashboard`
   - `/erp/completion`
   - `/erp/history/`
2. **Subordinate detail/work pages**
   - `/erp/drawing-workbench/<order_id>`
   - `/edit/<order_id>?open=erp-beta`
   - `/erp/orders/<order_id>` → edit ERP redirect contract
3. **Shell-linked descendant pages/subpages**
   - 위 1, 2에서 링크/redirect/deep-link로 도달 가능한 ERP HTML GET page
   - B1 inventory freeze에서 발견되는 shell-linked descendant는 explicit exclusion 없이 모두 범위에 포함한다

원칙:
- 위 1, 2, 3은 이번 tranche 범위다.
- “메인 4탭만 먼저”로 축소 closeout하는 것은 금지한다.
- `대표 subordinate 몇 개만 맞추고 closeout`하는 것도 금지한다.
- write-only endpoint나 modal-only API는 범위가 아니지만, **사용자가 브라우저에서 직접 열고 이동하는 ERP page/subpage는 전부 범위**다.

#### 3.1.1 ERP 공통 셸
- 기존 ERP primary page는 공통 shell 위에서 동작한다.
- shell 책임:
  - ERP sub nav/공통 nav 유지
  - active tab 표시
  - body mount point 제공
  - skeleton/loading state
  - browser-side page cache
  - prefetch orchestration
  - history push/replace + popstate 복원
  - subordinate page에서 primary page로의 자연스러운 복귀

#### 3.1.2 Dual-mode route contract
각 canonical ERP primary route는 두 모드로 동작한다.

1. **full page mode**
   - direct visit
   - 새로고침
   - JS off
   - fallback
2. **fragment mode**
   - shell 내부 fetch 요청
   - page body만 반환
   - 필요 시 critical/heavy fragment 분리

권장 판별 기준:
- request header: `X-FOMS-ERP-SHELL: 1`
- query flag: `view=fragment` 또는 `view=critical`

원칙:
- canonical URL은 유지한다.
- fragment용 별도 공개 URL을 무분별하게 늘리지 않는다.
- full/fragment의 business semantics는 반드시 동일해야 한다.
- full mode는 독립 truth를 따로 가지지 않고, **동일 fragment renderer를 조합해 만든다.**

#### 3.1.3 Subordinate page contract
subordinate page/subpage는 두 가지 중 하나로 구현한다.

1. **shell-contained mode**
   - shell 위에서 detail/work area를 교체
   - back/forward 시 primary ↔ subordinate 자연스럽게 오간다
2. **shell-aware full mode**
   - full page로 열리되 ERP shell과 동일한 nav state/return contract를 가진다
   - primary page로 돌아갈 때 state 복원이 가능해야 한다

원칙:
- subordinate page는 “이번 tranche 범위 밖”으로 빠질 수 없다.
- 단, 모든 subordinate page를 in-place swap으로 만들 필요는 없다.
- 중요한 것은 **primary ↔ subordinate 왕복 체감과 semantic consistency**다.

#### 3.1.4 Fragment layering
각 탭은 최소 두 레이어로 분리한다.

1. **critical fragment**
   - 현재 탭을 이해하는 데 필요한 상단 요약/KPI/핵심 필터/첫 화면
   - 초기 진입과 탭 swap에 먼저 사용
   - 접힌 상세 row / 대형 hidden block / 하위 미디어 목록은 포함하지 않는다
2. **heavy fragment**
   - 큰 테이블
   - 접힌 상세 목록
   - 미리 렌더할 필요 없는 숨김 영역
   - detail drawer/modal payload

heavy fragment는 아래 중 하나로 지연한다.
- shell 이후 즉시 background fetch
- 사용자 scroll / expand / click 시 on-demand fetch

### 3.2 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/web/orders/dashboard.py` | full/fragment dual-mode, orders dashboard critical/heavy split, shell fetch contract |
| `foms/web/measurement/dashboard.py` | full/fragment dual-mode, measurement dashboard critical/heavy split |
| `foms/web/drawing/workbench.py` | drawing workbench dashboard/detail shell contract, subordinate detail strategy |
| `foms/web/production/dashboard.py` | production dashboard full/fragment dual-mode |
| `foms/web/shipment/dashboard.py` | full/fragment dual-mode, shipment dashboard critical/heavy split |
| `foms/web/cs/as_dashboard.py` | full/fragment dual-mode, AS dashboard critical/heavy split |
| `foms/web/construction/dashboard.py` | construction dashboard full/fragment dual-mode |
| `foms/web/cs/completion_dashboard.py` | completion dashboard shell participation |
| `foms/web/orders/history.py` | ERP history dashboard shell participation |
| `foms/web/orders/edit.py` | ERP order detail/edit subordinate page contract, return-state contract |
| `foms/services/common/dashboard_cache.py` | shell/fragment 구조에 맞는 cached slice 재사용, tracing 보강 |
| `templates/orders/dashboard.html` | full-page shell host로 slim화 |
| `templates/measurement/dashboard.html` | full-page shell host로 slim화 |
| `templates/drawing/workbench_dashboard.html` | shell host + fragment split |
| `templates/drawing/workbench_detail.html` | subordinate detail shell-aware rendering |
| `templates/production/dashboard.html` | full-page shell host로 slim화 |
| `templates/shipment/dashboard.html` | full-page shell host로 slim화 |
| `templates/cs/as_dashboard.html` | full-page shell host로 slim화 |
| `templates/construction/dashboard.html` | full-page shell host로 slim화 |
| `templates/cs/completion_dashboard.html` | shell participation 정렬 |
| `templates/orders/history_dashboard.html` | shell participation 정렬 |
| `templates/orders/edit_order.html` | ERP mode subordinate page contract 정렬 |
| `templates/orders/partials/*` | orders critical/heavy fragment 분리 |
| `templates/measurement/partials/*` | measurement critical/heavy fragment 분리 |
| `templates/drawing/partials/*` 또는 drawing 하위 partial | drawing dashboard/detail fragment 분리 |
| `templates/production/partials/*` | production critical/heavy fragment 분리 |
| `templates/shipment/partials/*` | shipment critical/heavy fragment 분리 |
| `templates/cs/partials/*` 또는 `templates/cs/as_partials/*` | AS critical/heavy fragment 분리 |
| `templates/construction/partials/*` | construction critical/heavy fragment 분리 |
| `templates/partials/shared/layout_nav.html` | ERP 탭 anchor/data attribute 정렬 |
| `templates/partials/shared/erp_sub_nav.html` | ERP 전체 surface nav/shell contract 정렬 |
| `templates/partials/shared/erp_mobile_shell.html` | mobile ERP shell 대상 surface 정렬 |
| `templates/partials/shared/layout_scripts.html` | shell bootstrap hook만 남기고 탭별 대형 로직은 page-scoped로 이관 |
| `static/js/erp/runtime-shell.js` | 신규: shell navigation, cache, prefetch, history, swap controller |
| `static/js/orders/*` | orders heavy fragment/client hook 분리 필요 시 보강 |
| `static/js/measurement/*` | measurement heavy fragment/client hook 보강 |
| `static/js/drawing/*` 또는 ERP shell 하위 JS | drawing/detail interaction 보강 |
| `static/js/production/*` | production page hook 보강 |
| `static/js/shipment/*` | shipment heavy fragment/client hook 보강 |
| `static/js/cs/*` 또는 `static/js/as/*` | AS heavy fragment/client hook 보강 |
| `tests/` 하위 ERP route/browser/contract 테스트 | shell/full parity, fragment parity, subordinate page parity, prefetch, back/forward, JS fallback |

### 3.3 구현 원칙

#### 3.3.1 micro-cache 유지
- 현재 `dashboard_cache.py`와 slice cache는 유지한다.
- shell/fragment 구조는 micro-cache를 대체하는 것이 아니라, **micro-cache가 실질 체감으로 이어지게 하는 상위 구조**다.

#### 3.3.2 HTML-first, not SPA rewrite
- 1차는 JSON API 대전환이 아니라 Jinja partial HTML 반환이 기본이다.
- 이유:
  - 기존 템플릿/권한/필터 의미를 재사용하기 쉽다
  - diff 위험이 낮다
  - 서버 truth를 유지하기 쉽다

#### 3.3.3 Progressive enhancement
- JS 실패 시에도 canonical route는 full page로 동작해야 한다.
- shell은 enhancement layer이지, 단일 진입 의존점이 아니다.

#### 3.3.4 Browser-side cache boundary
- key = canonical URL + normalized query + active user fingerprint + tab id
- 캐시는 메모리 우선, 필요 시 sessionStorage는 후속 검토
- 권한/필터가 다르면 재사용하면 안 된다.
- GET 필터/정렬/페이지네이션 요청도 같은 key 규칙을 사용한다.

#### 3.3.5 Semantic-preserving contract
이번 tranche는 기능 의미를 바꾸는 최적화가 아니라, **동일한 결과를 더 빠르게 전달하는 구조 변경**이다.

아래는 반드시 **동일**해야 한다.

1. 권한별 노출 범위
2. 탭별 주문/행 포함 여부
3. 필터 결과
4. 정렬 순서
5. 페이지네이션 결과
6. KPI/summary/stat 값
7. attachment/media count
8. stage/status/date 판정 결과
9. URL/deep-link/back-forward 동작
10. write path side-effect 및 후속 read visibility

아래는 허용된다.

1. full page 대신 shell + fragment로 그리는 방식
2. 먼저 보이는 영역과 나중에 붙는 heavy 영역의 전달 순서
3. 짧은 TTL 범위 안의 read-model stale
4. hit/miss/prefetch/logging/trace 추가

아래는 금지된다.

1. 숨겨진 탭/행/상세를 아예 제거해 HTML만 줄이는 방식
2. 느린 계산을 빼기 위해 KPI/집계 정의를 단순화하는 방식
3. 첫 화면만 빠르게 보이게 하고 실제 데이터 정확도를 늦추거나 누락시키는 방식
4. shell mode에서만 다른 필터/정렬/페이지네이션 규칙을 쓰는 방식
5. JS on/off에 따라 business result가 달라지는 방식

### 3.4 성능 목표와 예산

#### 3.4.1 정량 목표
최종 목표는 아래 두 가지다.

1. **첫 진입 속도**
   - ERP primary page entry에서 shell/critical fragment 기준 first meaningful content가 지금보다 명확히 빨라야 한다.
2. **탭 전환 속도**
   - primary page 간 warm navigation은 “즉각적으로 느껴질 수준”으로 내려와야 한다.
3. **하위 페이지 왕복 속도**
   - primary ↔ subordinate 왕복도 지금보다 명확히 가벼워져야 한다.

#### 3.4.2 수치 acceptance
- `/erp/dashboard`, `/erp/as`의 **initial document raw size**는 현재 1MB대에서 대폭 감소해야 한다.
- 1차 목표:
  - shell 문서 raw size: `<= 220KB`
  - active tab critical fragment raw size: `<= 160KB`
- warm tab switch:
  - click → body swap 체감 목표 `<= 250ms`
- cold tab switch:
  - click → critical content 표시 목표 `<= 1.0s`
- primary ↔ subordinate warm return:
  - click → meaningful content 복귀 목표 `<= 500ms`
- browser 측정 기준:
  - click → first primary content paint
  - click → heavy fragment settled
- 서버 측정 기준:
  - route total
  - starttransfer
  - fragment render time

주의:
- 위 수치는 UX acceptance 목표다.
- final closeout은 Railway/prod-like evidence로 확인한다.

### 3.5 탭 prefetch 전략
- 최초 active primary page 렌더 후 idle 시점에 인접 ERP primary page를 prefetch 한다.
- 우선순위:
  1. 현재 사용 패턴상 가장 자주 왕복하는 탭
  2. hover/focus된 탭
  3. back/forward 직전 탭
- prefetch는 다음 경우 생략:
  - Data Saver
  - recent error
  - auth/permission mismatch
  - same URL variant already cached
- prefetch는 active navigation을 지연시키면 안 된다.

### 3.6 HTML 다이어트 규칙
- 접힌 상세 영역은 초기 HTML에 포함하지 않는다.
- 테이블 row detail, attachment preview, hidden panel body는 on-demand로 이동한다.
- large inline JSON/HTML blob은 금지한다.
- 각 탭은 critical first, heavy later 원칙을 따른다.

### 3.7 shipment / as profiling 전용 lane
- `shipment`, `as`는 현재 micro-cache 효과가 약하다.
- 이 둘은 shell/fragment 전환과 별개로 병목을 분리 측정한다.
- 측정 대상:
  - query time
  - Python payload assembly
  - Jinja render time
  - fragment size
- 이 lane에서 query rewrite 필요성이 드러나면 별도 follow-up plan으로 분리한다.

### 3.8 관측/증거 계약
- 로컬/pytest만으로 closeout하지 않는다.
- 최소 증거:
  - shell/full parity test
  - fragment/fallback parity test
  - GET filter/pagination shell parity test
  - primary ↔ subordinate return-state parity test
  - back/forward test
  - prefetch hit evidence
  - Railway staging before/after
  - warm tab switch evidence
  - ERP primary surface 전체 route-level evidence
  - ERP subordinate/descendant authoritative inventory 전체 route-level evidence
  - browser-side performance evidence

### 3.9 Stop Rule
- 아래 중 하나라도 발생하면 batch를 멈추고 설계를 다시 연다.
  - full mode와 fragment mode의 의미가 달라짐
  - JS off fallback이 깨짐
  - browser cache key 경계가 불명확해 권한/필터가 섞일 위험이 생김
  - shell 도입 때문에 기존 deep-link/back/forward가 깨짐
  - template 중복이 생겨 full/fragment를 따로 관리해야 하는 상태가 됨
  - GET filter/pagination이 shell 바깥 full reload 강제 경로로 남아 UX가 split-brain이 됨
  - subordinate page가 shell/return-state contract 없이 고립된 full page로 남아 ERP flow가 끊김
  - large HTML이 shell 전환 후에도 실질적으로 줄지 않음
  - shipment/as가 profiling 없이 “느려도 유지” 상태로 넘어가려 함
  - 속도를 위해 KPI/행/상세/필터 결과를 줄이거나 지연 누락시키려 함
  - `semantic-preserving` 대신 `good enough rendering` 논리로 축소를 정당화하려 함

## 4. Steps — 실행 단계

### 4.1 EPT-B1 Baseline + contract freeze
- [x] 현재 Railway staging 기준 ERP primary surface 전체 baseline을 다시 고정한다. *(9행 표 스키마 + 기존 4 URL 실측 유지 + 5 URL `PENDING` — `2026-04-17-ept-b1-baseline-contract-run-record.md` §2)*
- [x] shell mode / fragment mode / heavy fragment mode contract를 문서와 테스트로 동결한다. *(기존 SPEC·`erp_navigation_contract`·`test_erp_shell_fragment_contract` 유지)*
- [x] 기존 micro-cache를 유지한다는 결정을 명시적으로 잠근다. *(SPEC §7 + `MICRO_CACHE_READ_SLICES_RETAINED`)*
- [x] route/query/history/canonical URL matrix를 정의한다. *(SPEC + B1 run record inventory v2)*
- [x] GET filter/pagination interception 범위와 non-JS fallback 경계를 정의한다. *(SPEC §5)*
- [x] primary / subordinate / descendant surface inventory를 authoritative set으로 동결한다. *(B1 §8 inventory v2)*
- [x] `브라우저에서 직접 열 수 있는 ERP HTML GET page/subpage는 전부 범위`라는 계약을 문서/테스트에 잠근다. *(SPEC §9 + B1 §8; 임의 제외 없음)*

### 4.2 EPT-B2 ERP shell 도입 (안전 네비 — PRIMARY_NAV vs FRAGMENT_READY)
- [x] `static/js/erp/runtime-shell.js` — shell 클라이언트; **fetch+swap은 `FRAGMENT_READY`만** (`isFragmentReadyPath`). **EPT-B4 이후** `FRAGMENT_READY` = **9 path** (PRIMARY_NAV와 동일 순서). `window.FOMS_ERP_SHELL.{PRIMARY_NAV,FRAGMENT_READY}_PATHS` 노출.
- [x] `foms/services/common/erp_navigation_contract.py` — `ERP_PRIMARY_NAV_PATHS`(9), **`ERP_FRAGMENT_READY_PATHS`(9, B4)**, `ERP_CANONICAL_TAB_PATHS` = **FRAGMENT_READY와 동일 튜플 객체**(SPEC §2).
- [x] ERP 동일 출처 링크: fragment-ready면 shell fetch; 그 외 primary/하위는 **브라우저 기본 네비**(이중 GET 방지). *(run record: `2026-04-17-ept-b2-erp-shell-safe-nav-run-record.md`)*
- [x] history `pushState` / `popstate` — fragment 경로에서만 shell 경로 유지; 그 외는 기존 동작.
- [x] JS off / fragment 미구현 탭: full document GET 유지 (fetch 가드 밖).
- [x] EPT-B3(코어 4) + **EPT-B4(secondary 5)** 서버 fragment·dual-mode 완료 후 `FRAGMENT_READY` = **9 primary** (`2026-04-17-ept-b4-secondary-primary-shell-fragment-run-record.md`).

### 4.3 EPT-B3 Core ERP page fragmentization
- [x] `dashboard`, `measurement`, `shipment`, `as` — full/fragment dual-mode를 `erp_shell_http`로 정렬 (`get_erp_shell_view_mode`, `wants_erp_shell_tab_body`, `apply_erp_shell_fragment_headers`). *(run record: `2026-04-17-ept-b3-core-fragment-dual-mode-run-record.md`)*
- [x] `view=critical|heavy` 계약 명시; **B3**에서는 **fragment와 동일 partial·동일 컨텍스트** + `X-FOMS-ERP-FRAGMENT-TIER`로만 구분 (템플릿 물리 분리는 후속).
- [x] micro-cache slice는 핸들러 단일 조립 경로 유지 (tier 미포함).
- [ ] first paint·Railway 재측정은 **B8/B9·운영 실측** 계열 (본 배치 closeout 주장 안 함).

### 4.4 EPT-B4 Secondary ERP page fragmentization
- [x] `drawing-workbench`, `production/dashboard`, `construction/dashboard`, `completion`, `history/` 다섯 primary를 `erp_shell_http` dual-mode + body partial single-truth로 편입; 도면 **detail**은 B5.
- [x] `ERP_FRAGMENT_READY_PATHS`·`runtime-shell.js` `FRAGMENT_READY_PATHS`를 **9 primary 전부**와 순서 정합 (PRIMARY_NAV 동일).
- [x] B3와 동일: `critical`/`heavy`는 fragment와 **동일 본문** + `X-FOMS-ERP-FRAGMENT-TIER`만 구분; 운영 재측정은 B8 범주.

### 4.5 EPT-B5 Subordinate page/subpage integration
- [x] `drawing-workbench/<order_id>` detail을 subordinate shell contract로 정렬한다. *(body partial + `workbench_detail` / `workbench_detail_fragment`; `foms/web/drawing/workbench.py` dual-mode)*
- [x] `edit/<order_id>?open=erp-beta`를 ERP subordinate page contract로 정렬한다. *(GET: `edit_order` / `edit_order_fragment` + headers; POST/redirect/XHR 불변)*
- [x] `/erp/orders/<order_id>` legacy redirect도 ERP flow 안에서 자연스럽게 이어지게 만든다. *(302 → `/edit/<id>?…open=erp-beta`; pytest)*
- [x] B1 inventory descendant 정렬: `/erp/shipment-settings` dual-mode + body partial; `/map_view`는 full document·헤더 계약 미적용(run record 판정)·pytest로 고정.
- [x] primary ↔ subordinate 서버 계약(헤더·본문 parity·JS-off full GET): `tests/domains/test_erp_shell_fragment_contract.py` EPT-B5 케이스. **런타임 history/스크롤 복원 스모크**는 B6+.

### 4.6 EPT-B6 Prefetch + warm navigation
- [x] idle prefetch를 붙인다. *(run record: `2026-04-17-ept-b6-prefetch-warm-nav-run-record.md`; `runtime-shell.js` idle stagger)*
- [x] hover/focus prefetch를 붙인다. *(mouseover·focusin delegation, debounced)*
- [x] primary page warm navigation latency를 계측한다. *(클라이언트 LRU·warm hit 경로; ms·Performance API·Railway 실측 증거는 §4.8/B8)*
- [x] primary ↔ subordinate 왕복 latency도 계측한다. *(동일; `popstate`·scroll memory로 의미 보존 복원)*
- [x] cache hit 시 즉각 body swap 또는 meaningful restore가 되는지 확인한다.

### 4.7 EPT-B7 HTML diet + page-scoped assets + profiling
- [x] `dashboard`, `as`의 initial document/fragment size를 크게 줄인다. *(inline CSS/JS → static; run record: `2026-04-17-ept-b7-html-diet-page-assets-profiling-run-record.md`)*
- [ ] 숨김 영역, 상세 row, heavy panel을 on-demand로 이동한다. *(B7에서는 데이터 지연 없이 자산만 분리; DOM/행 단위 on-demand는 후속 배치·register — 동일 run record §Deferred)*
- [x] 탭별 큰 스크립트는 page-scoped로 지연한다. *(orders 알림: `defer` + 본문 partial 전용 JS 경로)*
- [x] global layout에 항상 실리지 않아도 되는 코드를 분리한다. *(본문 partial에서 `<link>`/`<script>` — fragment와 동일)*
- [x] `shipment`, `as`는 cache 밖 병목을 profiling으로 분리한다. *(서버: `render_template` ms 헤더·로그; query rewrite는 B7 범위 밖)*
- [x] profiling 결과 query rewrite가 필요하면 후속 register에 명시한다. *(B7 구현 없음; 필요 시 별도 register)*

### 4.8 EPT-B8 Verification + Railway evidence
- [x] APP_OK / verify_result / focused pytest (로컬 — `docs/plans/2026-04-17-ept-b8-verification-railway-evidence-run-record.md` §3; fragment + runtime-shell + `test_ept_b7_profile` 포함 시 **47 passed**).
- [ ] browser-like regression: **staging/prod-like**에서 Performance API·Network·primary 9 스모크 등 **운영 증거** (로컬 pytest만으로는 이 항목 완료 불가).
- [ ] staging/prod-like에서 ERP primary surface 전체 before/after evidence를 수집한다.
- [ ] ERP subordinate/descendant authoritative inventory 전체 before/after evidence를 수집한다.
- [ ] full reload, cold navigation, warm navigation, primary ↔ subordinate 왕복을 모두 비교한다.
- [ ] browser Performance API 또는 동등 수단으로 click-to-paint를 수집한다.
- [ ] 목표 미달 시 원인을 `HTML`, `query`, `render`, `asset`, `prefetch miss`로 분류한다.

### 4.9 EPT-B9 Final GDM audit closeout
- [ ] plan vs code
- [ ] code vs tests
- [ ] tests vs run record
- [ ] run record vs Railway evidence
- [ ] semantic diff 0 matrix
- [ ] “빠른 페이지”, “빠른 탭 전환”, “하위 페이지 왕복 속도”까지 충족했는지 최종 판정

## 5. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python tools/harness/verify_result.py --json` 통과
- [ ] ERP primary surface full mode / fragment mode parity tests 통과
- [ ] JS off fallback tests 통과
- [ ] GET filter/pagination shell parity tests 통과
- [ ] primary ↔ subordinate return-state parity tests 통과
- [ ] history/back-forward tests 통과
- [ ] prefetch hit tests 통과
- [ ] semantic diff 0 검증 통과
- [ ] `/erp/dashboard` before/after evidence
- [ ] `/erp/measurement` before/after evidence
- [ ] `/erp/drawing-workbench` before/after evidence
- [ ] `/erp/production/dashboard` before/after evidence
- [ ] `/erp/shipment` before/after evidence
- [ ] `/erp/as` before/after evidence
- [ ] `/erp/construction/dashboard` before/after evidence
- [ ] `/erp/completion` before/after evidence
- [ ] `/erp/history/` before/after evidence
- [ ] ERP subordinate/descendant surface authoritative inventory evidence
- [ ] authoritative inventory에 포함된 subordinate/descendant page/subpage 전체 before/after evidence
- [ ] warm tab switch evidence
- [ ] primary ↔ subordinate 왕복 evidence
- [ ] browser click-to-paint evidence
- [ ] initial document/critical fragment size budget 증거
- [ ] migration / schema / business semantics diff 없음

## 6. GDM 초정밀 감리 포인트

### 6.1 CEO/Growth 축
- “빠른 탭 전환”만 만족하고 “첫 진입이 여전히 무거운” half-fix 금지
- 메인 4탭만 빨라지고 나머지 ERP surface는 그대로 느린 상태의 partial closeout 금지
- ERP primary surface 전체와 subordinate/descendant surface 전체에서 체감 개선이 보여야 함

### 6.2 Eng 축
- duplicate template truth 금지
- fragment/full dual-mode drift 금지
- shell state와 URL state 불일치 금지
- optimization을 이유로 business payload를 축소하는 hidden regression 금지

### 6.3 UX 축
- skeleton만 빠르고 실제 내용은 느린 fake-fast 금지
- active tab, filter, scroll, browser history가 자연스럽게 유지돼야 함
- primary ↔ subordinate 왕복 시 사용자가 길을 잃지 않아야 함

### 6.4 Ops 축
- staging 실측 없이 closeout 금지
- Railway evidence 없는 “체감 빨라졌다” 서술 금지

### 6.5 Semantic 축
- 기능 축소를 성능 개선으로 포장하는 것 금지
- shell/fragment/heavy layering 때문에 결과가 늦게 보일 수는 있어도, 최종 결과 의미는 full mode와 완전히 같아야 한다
- 최종 감리에서는 반드시 `권한/필터/정렬/페이지네이션/KPI/media count` diff 0 표를 남긴다

## 7. 후속 defer register
아래는 이번 tranche 비목표지만, profiling 결과에 따라 후속으로 연다.

1. shipment/as query rewrite
2. `structured_data::text ILIKE` 제거
3. boot path 분리
4. broader asset pipeline split

## 8. 참고 자료
- `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md`
- `docs/plans/2026-04-16-dmc-f-run-record.md`
- `docs/plans/2026-04-16-dmc-f7-railway-evidence.md`
- `foms/web/orders/dashboard.py`
- `foms/web/measurement/dashboard.py`
- `foms/web/drawing/workbench.py`
- `foms/web/production/dashboard.py`
- `foms/web/shipment/dashboard.py`
- `foms/web/cs/as_dashboard.py`
- `foms/web/construction/dashboard.py`
- `foms/web/cs/completion_dashboard.py`
- `foms/web/orders/history.py`
- `foms/web/orders/edit.py`
- `templates/orders/dashboard.html`
- `templates/measurement/dashboard.html`
- `templates/drawing/workbench_dashboard.html`
- `templates/drawing/workbench_detail.html`
- `templates/production/dashboard.html`
- `templates/shipment/dashboard.html`
- `templates/cs/as_dashboard.html`
- `templates/construction/dashboard.html`
- `templates/cs/completion_dashboard.html`
- `templates/orders/history_dashboard.html`
- `templates/orders/edit_order.html`
