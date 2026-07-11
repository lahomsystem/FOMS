# 태블릿 셸 T0+T1a 구현 Spec (2026-07-10)

근거: 태블릿 UX 목업 v8 (artifact `1f9d4a9b`, 세션 스크래치패드 `foms-tablet-landscape-mockup.html`) + 사용자 확정 원칙.
배포 안전: 전부 `FOMS_TABLET_SPLIT_VIEW_ENABLED` / `FOMS_V3_SHELL_COHORT` 코호트 뒤. 커밋·푸시는 별도 승인.

## 확정 원칙 (사용자, 목업 v3~v8)
- 태블릿 **가로 = 크기 무관 대형 화면 인터페이스**(split shell), **세로 = 모바일 인터페이스**.
- 좌측 레일 = 더보기 없이 **허가된 전 메뉴 상주** (사무 9탭+계산기, 시공팀 4탭 — 권한 SSOT).
- 데스크톱(fine 포인터) 오분류 방지: FHD@125% 노트북 = 1536px → 폭 단독 분기 금지.
- escape hatch: 수동 "데스크톱 보기" 강제 (localStorage).

## T0-1. 셸 판정 개편 — `static/css/foundation/foms-split-view.css`

현행: 폭 3밴드(<992 모바일 / 992–1365.98 split / ≥1366 desktop), orientation 무관.
변경: 회전축+포인터 판정. **배타성 매트릭스** (모든 조합 → 정확히 1개 셸):

| width | orientation | pointer | 셸 |
|---|---|---|---|
| <992 | * | * | mobile |
| ≥992 | portrait | coarse | mobile (12.9" 세로 1024 포함) |
| 992–1365.98 | landscape | * | split |
| 992–1365.98 | portrait | fine/none | split (세로 모니터 좁은 창 — 현행 유지) |
| ≥1366 | landscape | coarse | split (12.9"/13"/Ultra 가로) |
| ≥1366 | * | fine/none | desktop |
| ≥1366 | portrait | coarse | mobile (실기기 없음, 규칙 일관성) |

권장 쿼리 (worker가 현행 블록 구조에 맞게 적용, `not` 연산 금지 — 열거식):
- mobile 표시: `(max-width: 991.98px), ((pointer: coarse) and (orientation: portrait))`
- split 표시: `((min-width: 992px) and (max-width: 1365.98px) and (orientation: landscape)), ((min-width: 992px) and (max-width: 1365.98px) and (pointer: fine)), ((min-width: 992px) and (max-width: 1365.98px) and (pointer: none)), ((min-width: 1366px) and (orientation: landscape) and (pointer: coarse))`
- desktop 표시: `((min-width: 1366px) and (pointer: fine)), ((min-width: 1366px) and (pointer: none))`
- 검산: 어떤 조합도 2개 셸 동시 표시/동시 숨김 금지 (테스트로 고정).

escape hatch: `html[data-foms-shell="desktop"]` → desktop 강제 표시·나머지 숨김(쿼리보다 우선). `="split"` → split 강제. 신규 boot 스크립트 `static/js/runtime/foms-shell-mode-boot.js`(localStorage `foms_shell_mode` ∈ auto|desktop|split 읽어 attr 부착) — 기존 `foms-theme-boot.js` 로드 패턴 그대로 모방(위치·defer 여부·perf 가드 allowlist 처리 동일).

**함정**: 과거 P2-08 orientation overlay(세로 차단막)는 blank 사고로 제거·재도입 금지 주석 존재(`foms-split-view.css` 상단) — 주석 보존, 오버레이 방식 금지. 이번 변경은 표시 조건 쿼리 교체만.

## T0-2. 퀵윈 2건
1. `static/js/runtime/layout-scripts-core.js` — `fomsIsMobileImageViewer` 게이트 `(max-width: 768px)` → `(max-width: 991.98px), (pointer: coarse)` (태블릿에서 핀치줌 뷰어 활성). GlobalImageViewer.open 존재 조건 유지.
2. `static/js/components/foms-mobile-select.js` — MQ `(max-width: 991.98px)` → `(max-width: 991.98px), (pointer: coarse)` (태블릿에서 시트 피커). opt-in/제외 규칙·계산기 `.form-select` 무충돌 유지.

## T1a. 레일 전 메뉴 — `foms/services/foms_split_view.py` + `templates/partials/shared/foms_split_shell.html`
- `default_split_side_items`(현행 2개: 대시/주문) → **권한 기반 전 메뉴 빌더**: ERP primary 9개(대시보드/실측/도면/생산/출고/AS/시공/완료/이력 — `erp_navigation_contract` SSOT와 동일 경로·라벨) + 계산기(`/wdcalculator`). 시공팀(CONSTRUCTION)은 출고/시공/완료/이력 4개, 계산기 제외 — `erp_mobile_bottom_nav`/`erp_sub_nav`의 기존 권한 분기 로직 재사용(중복 구현 금지, 기존 헬퍼 있으면 호출).
- 아이콘: `erp_mobile_shell.html` nav 카탈로그의 fa 클래스 재사용.
- 템플릿/CSS: 사이드 탭 아이템 52px·아이콘+라벨·현재 탭 active·짧은 화면 레일 내부 스크롤(`overflow-y:auto`).

## 테스트 (신규 계약)
- `tests/`(기존 컨벤션 위치): ① split_view side items 계약 — 일반 사용자 10개·시공팀 4개·href/라벨 정합·active 표시. ② CSS 판정 계약 — 필수 쿼리 문자열 존재, 구 무조건 `min-width: 1366px` desktop 단독 쿼리 제거, 재도입 금지 주석 존치, `data-foms-shell` 훅 존재. ③ 퀵윈 게이트 계약 — 두 JS 파일의 신규 MQ 문자열 존재·구 문자열 부재.
- 기존 관련 테스트 회귀 확인(스켈레톤 split 계약 테스트 존재 시 갱신).

## 검증 (완료 기준)
- `python -c "import app; print('APP_OK')"` → APP_OK
- 신규 계약 테스트 + 기존 split/shell/mobile 관련 pytest green
- `git diff` Advisor 직접 검토

## 비범위 (후속)
- 상세 패널 fragment 배선(T1b), 대시보드 persona 재설계(T2+), 사이드 시트/칸반/갤러리 컴포넌트(T3), 오프라인(T4), 메뉴 드로어 내 셸 모드 토글 UI, 커밋/푸시.

## 경계 (손대면 안 됨)
- 서버 코호트 게이트 로직(`context_processors.py`) 변경 금지 — CSS/JS/템플릿/서비스 빌더만.
- `sw.js`, `erp-shell.js` fragment 인프라, 모바일 큐 마크업 무변경.
- 인라인 스타일 금지, 신규 `<script>`는 기존 boot 패턴 동일 적용.

---

## 실행 결과 (2026-07-11, T0+T1a 완료)

Worker 7기(W1~W7) + 울트라 재검토 2회(적대·회귀)로 구현 완료. 최종: `APP_OK` + 관련 스위트 103 passed, diff +405/−71(14파일) + 신규 3(boot.js·계약 테스트 2). 커밋 대기(사용자 승인).

검수가 색출·봉합한 결함: ① 992–1365 세로 coarse blank(P2-08 재현 경로) ② ≥1366 가로 coarse 이중 chrome(대시보드 그리드) ③ 글로벌 헤더 이중 chrome(13-bridge, 히어로 기기) ④ 워크벤치 태블릿 세로 큐 실종+카드 누출(d-lg 폭 게이트 함정, 중첩 d-lg-none 포함) ⑤ 이미지 뷰어 인라인 정본 미동기(실서빙 경로) ⑥ 캐시버스터 @import 체인.

## staging 실배포 검증 (2026-07-11, 커밋 4건: fdd4a90a·4134275a·f6de1ab5·14e2e38a)

스모크(1180×820 실뷰포트)가 색출·봉합한 배포 결함: ① split blank — base 은닉이 opt-in @media 뒤(캐스케이드 순서, 계약 테스트+순서 잠금 추가) ② 캐시 체인 — @import 자식만 범프 시 부모 URL 불변으로 1h 미반영(**교훈: 자식 범프 = 부모 내용 변경 = 부모도 범프**) ③ split 미배선 7개 대시보드 992+ 가로 blank — legacy 은닉을 `.foms-split-enabled ~` 형제 조건·`:has()` 로 split-존재 시에만 적용(미배선 페이지 = legacy fallback 계약).
최종 실측: /erp/dashboard = split+레일 10탭 ✓, construction·production = legacy 정상 ✓, 세로/폰/PC 매트릭스 ✓.

## 백로그 (후속 착수 순)
0. **[T2] 출고(shipment) 자체 셸 게이트 정리** — `foms-shipment-mobile.css`의 `@media (max-width:1365.98px)`가 T0 매트릭스와 독립적으로 폭 1365 이하 전부 모바일 UI를 강제(!important). 현행 동작 유지 중(유해하지 않음)이나 T2 출고 이식 시 매트릭스로 통합.

1. **[T2 선결·최우선] 워크벤치 상세**(`workbench_detail_body.html`) — 대시보드와 동일 d-lg 함정: 태블릿 세로에서 모바일 handoff 실종 + `.dw-legacy-detail` 누출.
2. **[경미] 태블릿 세로 d-lg 드롭 3건** — shipment 모바일 요약 스트립(`dashboard_main.html:135`), completion FAB(`completion_dashboard_body.html:47`), 주문 상세 액션바 JS(`dashboard_scripts_detail_dom.html:548/557`).
3. **[셸 모드 토글 UI(T2+) 선결]** ① 강제 split 시 자식 스타일 무적용(split-show `@media` 안에만 존재 — base 승격 필요) ② `<992` desktop 강제 시 layout_head 인라인 크리티컬 CSS 은닉 4종 미복원 + hatch 테스트를 인라인 목록과 대조하도록 확장. 현재 `foms_shell_mode` setter 부재로 도달 불가(잠복).
4. **[엣지] CONSTRUCTION 레일 active 기본값** — `/erp/dashboard` 진입 시 active 항목 없음(시공팀은 redirect라 실제 도달 불가).
5. **[검증 한계] 실기기/헤드리스 렌더 스모크** — 계약 테스트는 정적 문자열. gstack browse로 (폰/태블릿 세로/태블릿 가로/PC) × 코호트 ON 4조합 렌더 확인 권장(특히 1366px 가로 = 히어로 기기).
6. T1b(상세 fragment 배선)~T4는 목업 로드맵 그대로.
