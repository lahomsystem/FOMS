# 태블릿 T2 — 대시보드 목업 정합 구현 Spec (2026-07-11)

선행: T0+T1a 배포 완료(`2026-07-10-tablet-shell-t0-implementation-spec.md`). 목업 v8 = artifact `1f9d4a9b` (사용자 최종 확정: **태블릿 가로 = PC 인터페이스 최대 반영 + 터치 융합**, 카드형 큐 마스터 폐기).

## 방향 통일 (구현 원칙)

태블릿 가로(코호트, 992+ landscape coarse — fine 포함 992–1365)의 대시보드 = **legacy PC 표면(`.foms-shell-desktop-only`)을 그대로 쓰되 4개 융합 레이어를 얹는다**:
1. **터치 보정 레이어** — 그리드 행 ≥48px, 버튼/입력 ≥44px, 필터 컨트롤 터치화, 체크박스 상시 노출. 순수 CSS(`@media` 매트릭스 조합), 페이지 마크업 무변경.
2. **요약 타일** — 프로세스맵/경보를 목업의 큰 타일 스트립으로(태블릿 조합에서만 스타일 전환, 데이터 동일).
3. **사이드 시트** — 그리드 행 탭 → 우측 380~420px 시트에 기존 모바일 카드 상세/edit fragment 로드(신규 API 없음). 모달·페이지 이동 대체.
4. **특수형 2종** — 실측: 좌 고객 리스트(300px)+우 ERP Order 편집(기존 edit fragment) / 생산: read-model 3버킷 칸반(제작대기/제작중/제작완료).

split shell(카드 마스터, /erp/dashboard)은 당분간 공존 — 잔여 페이지 배선 후 컨트롤타워도 그리드+보정형으로 전환 판단(백로그).

## 실행 단위
- **W9** `static/css/foundation/foms-tablet-landscape.css`(신규): 터치 보정 레이어. 대상 = 9 대시보드의 legacy 표면. 로드 = foms-mobile-surfaces.css @import(+부모 ?v 체인 범프). 조건 = `((min-width:992px) and (orientation:landscape) and (pointer:coarse))` 중심 — fine 992–1365는 split 밴드라 legacy 은닉/fallback 규칙과 정합 검토 후 포함 여부 결정·명기.
- **W10** 사이드 시트: `static/js/foms/tablet-side-sheet.js` + `static/css/components/foms-tablet-side-sheet.css` + 최소 배선(행 클릭 위임 — 컨트롤타워 legacy 그리드·시공·생산 3페이지 우선). 기존 fragment 인프라(`/api/foms/fragment/order/<id>/edit`) 재사용, idempotent 가드(G4), defer(G1).
- **W11** 요약 타일: 프로세스맵 카드의 태블릿 조합 스타일 전환(마크업 무변경 우선, 불가피 시 최소 추가).
- **W12** 실측 특수형 / **W13** 생산 칸반: 페이지 템플릿+CSS+(칸반은 read-model 버킷 소비 — 서버 무변경, display 데이터 재사용).
- 각 단위: 계약 테스트 추가, APP_OK+스위트, 캐시버스터 체인 전체 범프(교훈), Advisor 검증 후 커밋·push·staging 실측.

## 경계
context_processors·서버 라우트·quest 엔진 수정 금지(칸반도 표시 전용). 타 세션(v3 셸) 파일 불가침. `orientation: portrait` 토큰은 foms-split-view.css에서만 금지(가드) — 신규 파일은 표시 opt-in 용도로 사용 가능하나 W5 전례(주석 명기) 따름.

---

## 실행 결과 (2026-07-11 완료, deploy 커밋 4건)

| 커밋 | 단위 |
|---|---|
| `7c5f072d` T2-α | 터치 보정 레이어(foms-tablet-landscape.css) + 사이드 시트(tablet-side-sheet.js/css — 행 탭→400px 비차단 시트, orders·construction·production 공통 그리드) |
| `d63d0211` T2-β | 요약 타일(프로세스맵 카드화·경보 4-타일 그리드, CSS-only) |
| `75496088` T2-γ | 실측 특수형(좌 고객 리스트 300px + 우 ERP Order fragment 상시 패널, rows 재사용) + 생산 칸반(read-model 3버킷 Jinja 그룹핑, 열 이동=start/complete API) + fragment-loader 공용 추출 |
| `e653748e` W14 | 울트라 재검토 결함 7건 봉합 — JS/CSS 게이트 SSOT(`--foms-tablet-ui` 마커 파생), 필터 16px ID 특이도, 시트 col-md 평탄화, 스크립트 src dedupe, 이중 디스패치 제거, 외부클릭 닫기 제거, 데드 규칙 정리 |

staging 검증: 신규 자산 전부 서빙·게이트 마커 ready·콘솔 0·기존 매트릭스 무회귀(1180 fine=split/desktop 정상, 특수형·칸반·시트는 coarse 전용이라 실기기에서 발현). 격리 worktree 스모크 250 passed × 3회. CI green.

## staging 직접 실측 (2026-07-11, coarse 에뮬 우회 — matchMedia 프로토타입 패치 + CSSOM mediaText 교체)

전 항목 실구동 통과: ① 사이드 시트(시공 행 탭 → 380px 고정 시트, fragment 87KB 로드, col-md 단일열 평탄화 371px, 비차단·X/ESC) ② 생산 칸반(3버킷 렌더·카드·상차 D-day 칩·빈 열 "해당 없음") ③ 실측 특수형(좌 고객 리스트+우 패널+빈 상태 안내 — staging에 실측 일정 데이터 0건) ④ 터치 보정 수치(행 78px·버튼 44px·페이지네이션 44px·필터 입력 50px/16px — iOS 줌 방지 실효) ⑤ W11 타일(경보 4-타일+파이프라인 타일 렌더) ⑥ fragment 가드(직접 내비게이션→/edit 302·fetch→200) ⑦ 폰 모바일 큐 무회귀.
측정 노하우: 헤드리스는 pointer:fine — JS 게이트는 `MediaQueryList.prototype.matches` getter 패치(coarse+landscape 쿼리만 true), CSS는 원본 주입 후 `sheet.cssRules[i].media.mediaText='all'` 교체(문자열 치환은 주석 속 "@media" 언급에 파싱 파괴 — 실패 사례).

사소 발견 2건(수정 대기): ① 시트 바디 좌측 라벨 1~2px 클리핑(시트 좌 패딩 보강) ② construction goto 직후 일회성 `/erp/orders/<id>/mobile` 이탈 관찰(비재현 — 모니터링).

## T3 크롬 교체 완결 (2026-07-12, deploy 1c8858fe·6583cfba)

사용자 "여전히 PC UI" 반복 보고의 근본 원인 확정: 크롬 교체(글로벌 헤더·nav 숨김)가 `:has(.foms-split-enabled)` 게이트, 레일이 split 셸 내부 전용이라 **split 배선 페이지(/erp/dashboard 1곳)에만 발동** — 나머지 8페이지는 4단 크롬+레일 0(계약 테스트가 split 페이지만 잠가 코드·테스트는 green인 채 체감 실패 지속).

수정: ① bridge CSS에 coarse-landscape ≥992 arm 추가 — 키=`body:has(.foms-tablet-rail)`(레일 존재=서버 게이트 SSOT, split arm과 소유 배타), layout-header/global-nav/erp-pro-nav 숨김 ② 전역 레일 `foms_tablet_rail.html`+`foms-tablet-rail.css`(기본 hidden, coarse landscape+@supports :has 동거 표시, fixed 72px + `#main-content` padding-left — body/.container-fluid는 인라인 padding:0 !important 잠금이라 불가) ③ layout_nav.html include 게이트(erp_mobile_v2_enabled+/erp, dashboard 제외=이중 레일 방지) ④ `resolve_tablet_rail_active_id`(세그먼트 경계 최장 접두)+`build_tablet_rail_items` — split 빌더 재사용, lazy Jinja 전역(순환 import→지연 import). 부수 봉합: AS 카메라 바 ≥768 숨김이 v2 전용 foms-shell.css 소속이라 v3에서 데스크톱·태블릿 누출 → 셸-독립 as-dashboard-body.css 정본 이전.

검증: 계약 293 passed + staging coarse 에뮬 실측 — 8페이지 전량(as/measurement/drawing/production/construction/completion/history/shipment) 크롬 3종 none·레일 72px·padding 72px·active 정확·hscroll 무, dashboard=split 레일 단독, PC fine 무회귀. 실측 노하우 추가: CSSOM media 재작성 워커는 **CSSImportRule.styleSheet 재귀 필수**(@import 체인 시트는 cssRules로 안 내려감).

## 백로그 (잔여 페이지 — 조사 완료, 착수 판단 대기)

시트/터치 그리드 계약(`#erp-grid tr.erp-main-row[data-order-id]`) 미충족 6페이지 실사 결과:
1. **AS**: 셀렉터 확장으로 가능(`.erp-pro-table-wrapper tbody tr[data-order-id]`) — 최소 확장 후보 1순위.
2. **출고**: data-order-id 있으나 자체 폭 게이트(1365.98 모바일 UI)가 992–1365를 선점 — T2 게이트 통합과 함께.
3. **이력**: 본행에 data-order-id 자체가 없음(속성 추가 필요) + 기존 chevron 확장 행과 상호작용 설계 필요.
4. **도면 워크벤치**: data-href 행 내비게이션과 충돌 — 별도 UX 판단(dw-* 클래스 패밀리, 타일도 미적용).
5. **완료**: 카드 리스트(비그리드) — 시트 부적용, 현행 유지.
6. 실측은 T2-γ 특수형이 대체(기존 chevron 확장은 desktop 표면에 잔존 — coarse에선 특수형이 소유).
+ 페이지네이션 특성상 칸반은 현재 페이지 범위만 표시(무한스크롤 비범위) · 칸반 낙관 갱신 비범위 · /erp/dashboard split 카드 마스터의 그리드 전환 여부는 실사용 피드백 후 결정.
