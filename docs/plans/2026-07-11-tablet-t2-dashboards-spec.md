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

## T4 완결 — split 퇴출·fragment 레일 동기 (2026-07-12, deploy f4942486·a796f23f)

T3 배포 후에도 사용자가 "생산 빼고 태블릿 모드 안 보임"+/erp/dashboard 이중 레일 스크린샷 보고. 근본 2중:
1. **fragment fast-tab ↔ 레일 미통합**: erp-shell.js는 pathname 화이트리스트(FRAGMENT_READY_PATHS)로 임의 `a[href]`를 가로채 `#main-content`만 스왑 — 레일 9링크가 그 목록과 바이트 동일이라 전부 인터셉트. 레일은 layout 소속(#main-content 밖)이라 스왑에 잔존(active stale) 또는 부재(dashboard 첫 진입 후 이동 시 전 페이지 레일 0 = PC UI). fragment body 자체는 full과 동일(생산 칸반 포함 — "생산만 보임"의 이유).
2. **split 마크업↔CSS 게이트 불일치**: split CSS(foms-split-view.css, base 은닉 포함)는 v2 전용 surfaces 번들로만 로드되는데 마크업은 v2∪v3에 렌더 → v3(스테이징 기본)에서 비스타일 split(사이드탭+카드)이 전 폭에 그대로 흐름(이중 레일 스크린샷의 "둘째 레일" 정체).

수정: ① split-show를 fine/none 992–1365.98 2열거로 축소(landscape·≥1366 coarse arm 제거 — orientation 토큰 소멸), foms-shell 미러·bridge 동기 → **태블릿 coarse landscape = 전 페이지(dashboard 포함) legacy PC + 전역 레일 통일**(목업 v5 "카드 마스터 폐기" 최종 반영) ② `foms_split_enabled`를 shell_variant=='v2' 전용으로(주입부+orders 라우트) ③ 레일 전역화: dashboard 제외 삭제, /wdcalculator 추가(번들 게이트·active 매핑), 레일 표시/크롬 숨김 셀렉터 body 클래스 의존 제거(계산기 미부착) ④ `tablet-rail-nav.js` 신규 — `foms:erp-shell-fragment-swapped`+popstate에서 세그먼트 최장 접두로 active 재부여(pushState→이벤트 순서 검증) ⑤ AS·이력 시트/터치(이력 본행 data-order-id+history-main-row, chevron 무변경, 인터랙티브 가드 확장) ⑥ 출고 1365.98 자체 게이트 → 매트릭스 통합(모바일 UI=폰+태블릿 세로만).

staging 2차 전수: 풀로드 10페이지(9탭+계산기) 전량 = 크롬 3종 none·레일 flex·pad 72px·active 정확·split 0·hscroll 무 + fragment 체인 8연쇄 = 레일 1개 유지·active 동기·split 0·크롬 숨김 유지. 검증 함정: 헤드리스=진짜 fine → fine-band 규칙 정당 매치로 split 오판 가능, split 검증은 fine/none arm을 `not all`로 끄는 2단 에뮬 필요.

## T5 — 탭별 목업 전용 표면 (2026-07-12, deploy eb354b29~aa63d491, staging 1180 작동 검증)

사용자 "도대체 뭐가 됐다는거야"(공통 크롬만으론 체감 불가) → 목업 v7/v8 persona 표면 구현. Opus 4기 병렬:
- **도면** = 시트 썸네일 갤러리(`tablet_gallery_body.html`+`foms-tablet-drawing-gallery.css`, rows 기존 thumbnail_url 재사용·쿼리 0, 카드=워크벤치 상세 앵커)
- **완료** = 8컬럼 금액 그리드(`tablet_completion_grid_body.html`, 출고가=erp_shipping_price_from_structured·잔금=출고가−예약금, 서버렌더+최근 60행 캡, 행 탭=시트)
- **AS** = 접수/조치후 사진 대조(`tablet_as_compare_body.html`, OrderAttachment created_at vs as_completed_date 매핑·배치 1쿼리, lightbox→GlobalImageViewer 재사용)
- **시트 파이프라인** = 8단계(STAGE_SEQUENCE SSOT→`data-foms-stage-catalog`+행 `data-stage`, JS 하드코딩 금지, 비대상 행 우아한 생략) + **계산기 표피**(`tablet-skin.css`, 구조·엔진 무변경)
- 시공 "작업 모드"는 동시 세션(시공 템플릿 수정 중) 충돌로 **보류** — 착수 시 타임라인 300px+도면 대형 뷰어.

작동 체크(f12 디바이스 에뮬 요구)가 잡은 결함 3건: ① tablet-side-sheet.js 내용 변경 후 script ?v 미범프 → 브라우저 1h 캐시 구버전(JS도 캐시 체인 대상) ② 완료 행 role="button"(a11y)이 시트 인터랙티브 가드 [role=button]에 자충돌 → `interactive !== row` ③ 완료 fragment 166K(예산 56K) → 60행 캡+예산 재시드(120K), AS 862K→900K, history dTTFB 276→290(내 변경 전부터 CI 드리프트 277~279).
실측 노하우 추가: browse 탭 뷰포트 확인 필수(`viewport 1180x820` — 390 폰 크기로 바뀌어 있던 오측정), 시트 JS 게이트=matchMedia라 CSSOM 재작성 외 MediaQueryList.prototype.matches 패치 병행, 연속 push 시 이전 커밋 perf-gate는 배포 추월로 구조적 타임아웃(최신 HEAD 런만 정본).

## T6 — 목업 프레임 완전체 + 작업방식 교정 (2026-07-13, deploy 9213f7aa~2ee1fa16)

사용자 지적("니 마음대로 작업하고 다 됐다고 한다") → **작업방식 교정**: 목업 프레임별 전 컴포넌트·기능 인벤토리(에이전트 추출)를 유일한 완료 기준으로 고정, 워커 보고는 인벤토리 체크표(✓/✗+사유) 강제, 검증 = staging 스크린샷 vs 목업 병치 대조, 전 항목 ✓ 전 "완료" 보고 금지.

구현(Opus 5기 병렬): 공용 시트 URL 계약(`data-foms-sheet-url`→전용 fragment, resolveSheetUrl)·밀도 토글 40/48/56·탭별 전용 시트 6종(대시보드 mini-quest/요약/첨부/퀘스트 승인, 도면 관리(시트PNG 썸네일·자동채움·버전 이력·시트 전달), 생산(총자수·spec_rows 미니표·특이사항·전달본·생산완료 API), 출고 배정(팀 라디오+잔여 capacity·시간 chips→shipment/update, 403 분기), 완료 정산(잔금 hl-tile·비용청구 폼→settlement/issue·발행 후 dim), 시공 워크모드 3열(오늘 타임라인 300px+전달본 대형 뷰어+완료 게이트 SSOT 재사용))·전 탭 KPI 타일/필터바·완료 CSV export·도면 크기 토글.

병치 대조가 적발한 통합 결함 4건(전부 봉합): ① 정산 폼 속성 미스매치(템플릿 data-foms-settlement-form vs JS data-foms-settlement-issue) ② 출고 본행 ROW_SELECTOR 누락 ③ 도면 카드(<a>)가 erp-shell 화이트리스트에 걸려 시트 대신 fragment 이동(→data-foms-erp-no-shell) ④ cfcard row flex가 세로 스택 콘텐츠를 min-content로 수축시켜 세로 글자 붕괴(→column).

미구현(사유 명시): 생산 '보류' 동작(상태/API 부재 — disabled), 현금영수증 발행 액션(API 부재 — 요청 상태 표기만). 백로그: long-press 벌크 선택 모드+contextual bar(프레임 12), 계산기 split pane 하이브리드 게이트(프레임 13), 레일 하단 알림·아바타, 상주형(고정) 320px 시트(현행 슬라이드 유지), 실측 마스터 chips 세분(주간/미확정)·지도로 보기.

## T7 — 잔여 PC 크롬 소거 + 미구현 전량 (2026-07-13, deploy c6a278f6·4e37eb66)

사용자 실기기 4지적(대시보드/출고/시공/계산기 "아직 PC", 마법사 나가기 부재, 저장견적 접힘 요구, 미구현 구현) 전량 반영 — Opus 5기 병렬 + Advisor 직접 재검.
- 대시보드(01): 프로세스맵 밴드·파이프라인·작업큐 헤더·erp-pro-header 태블릿 은닉, 목업형 pcbar(제목·N건·날짜·밀도 토글·주문 생성)+KPI 5타일(`tablet_dashboard_topbar.html`). **재검 적발**: 은닉이 Bootstrap `d-flex`(!important)에 패배 → `!important` 봉합(워커 "✓" 보고와 실화면 불일치 — 병치 대조 필수 재확인).
- 시공(07): 프로세스맵·파이프라인·필터 은닉 — 워크모드 전체 소유. 출고(06): 저우선 컬럼(`data-col-key`) 숨김·자수 우측정렬·행 48px·팀 파스텔 행 승격·주소는 배정 시트로.
- 계산기: 저장된 견적 기본 접힘(48px 레일 토글+오버레이+localStorage, `tablet-skin.js`) — 엔진·DOM 계약 무변경. 마법사: 나가기 버튼(dirty 가드 재사용, 목업 04 대조 잔여 0).
- 신규 API: `POST production/hold`(sd.production.hold 플래그, 전이 없음)·`POST cash-receipt/issue`(settlement.cash_receipt, 409/403) — deepcopy+flag_modified. 레일 하단 알림 벨(`data-foms-notif-open`+배지 SSOT, renderBadge querySelectorAll 근본수정)+아바타(프로필).
- 프레임 12: `tablet-bulk-select.js`(long-press 500ms→선택 모드+contextual bar, 기존 PC 벌크 재사용, capture-phase stopPropagation으로 시트 충돌 차단, erp-dashboard-entry CHAIN 배선). 프레임 13: split pane 실사 결과 이미 992+ 동작 — coarse arm 명시+44px 보정만.
- 에뮬 한계 기록: 페이지 스크립트의 matchMedia 인스턴스에는 외부 change 발화 불가 → 로드시점 게이트 JS는 CSS 클래스 수동 부여로 시각 검증+계약 테스트로 잠금.

## 백로그 (잔여 페이지 — 조사 완료, 착수 판단 대기)

시트/터치 그리드 계약(`#erp-grid tr.erp-main-row[data-order-id]`) 미충족 6페이지 실사 결과:
1. **AS**: 셀렉터 확장으로 가능(`.erp-pro-table-wrapper tbody tr[data-order-id]`) — 최소 확장 후보 1순위.
2. **출고**: data-order-id 있으나 자체 폭 게이트(1365.98 모바일 UI)가 992–1365를 선점 — T2 게이트 통합과 함께.
3. **이력**: 본행에 data-order-id 자체가 없음(속성 추가 필요) + 기존 chevron 확장 행과 상호작용 설계 필요.
4. **도면 워크벤치**: data-href 행 내비게이션과 충돌 — 별도 UX 판단(dw-* 클래스 패밀리, 타일도 미적용).
5. **완료**: 카드 리스트(비그리드) — 시트 부적용, 현행 유지.
6. 실측은 T2-γ 특수형이 대체(기존 chevron 확장은 desktop 표면에 잔존 — coarse에선 특수형이 소유).
+ 페이지네이션 특성상 칸반은 현재 페이지 범위만 표시(무한스크롤 비범위) · 칸반 낙관 갱신 비범위 · /erp/dashboard split 카드 마스터의 그리드 전환 여부는 실사용 피드백 후 결정.
