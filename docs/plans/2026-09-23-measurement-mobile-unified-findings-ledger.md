# 실측 모바일 통합 화면 — 리뷰 findings 원장 (2026-09-23)

> 스펙: `docs/specs/2026-09-23-measurement-mobile-unified-list_SPEC.md`. 받는 즉시 전량 기록. 상태는 총괄이 확인 후 갱신.

## 리뷰 A — 정확성·회귀

| # | 등급 | 위치 | 내용 | 제안 | 상태 |
|---|---|---|---|---|---|
| A1 | P1 | erp-shell.js:927, mobile-glance-sheet.js:266 | 시트 연 채 카드 안 셸 링크(도면 창구 등)로 이동 → 뒤로 가기 때 `fomsShellKeep` 표식 기록에 도착해 셸이 건너뜀 → 주소만 /erp/measurement, 화면은 그대로. 한 번 더 눌러도 헛돎 | 셸이 마지막 렌더 키 기억, `fomsShellKeep && getCacheKey(location.href)===lastRenderedKey` 일 때만 건너뜀 | 수정 — erp-shell.js:408-417 lastRenderedKey·shouldKeepOnPop, :426 렌더 커밋 때 갱신, :945 표식+같은 키일 때만 건너뜀, :1132 syncRenderedUrl 노출(탭 ?mgr=·focus_order 제거가 호출). 계약 테스트 test_erp_shell_keep_requires_same_rendered_page |
| A2 | P3 | mobile-glance-sheet.js:280 | 시트 연 채 새로 읽으면 앞 기록 표식·시트 기록이 남아 뒤로 가기 한 번 헛돎 | measSheet 가 있으면 시트 복원 또는 기록 정리 | 수정 — sheet.js:264-269 새로고침 뒤 measSheet 기록 위면 시트 복원(줄 없으면 기록 정리). 브라우저 확인: 새로고침→시트 복원→뒤로 가기로 닫힘 |
| A3 | P2 | mobile-glance-tabs.js:192,276 / sheet.js:285 | `FomsMeasGlance.restoredOrderId` 가 안 지워져 이후 같은 문서의 `?focus_order` 시트가 영영 안 열림 | init 에서 읽은 즉시 delete | 수정 — sheet.js:271-272 읽은 즉시 delete |
| A4 | P3 | tabs.js:170 | 다른 화면이 남긴 `__fomsQuestApproveRestore` 를 30초 안 셸 이동 시 실측이 사용 | detail 에 path 넣고 같을 때만 | 수정 — erp-quest-approve.js:119 detail.path, tabs.js:178 같은 주소일 때만 |
| A5 | P2 | mobile-glance.js:84,139 | 시트에서 체크 저장 실패 시 안내가 시트 뒤 목록에 떠 안 보임 | 시트 열림이면 fomsFlashToast | 수정 — mobile-glance.js:84-90 시트 열림이면 fomsFlashToast(있을 때만) |
| A6 | P3 | sheet.js:235 | Esc 한 번에 사진 미리보기+시트 같이 닫힘 | 시트 keydown 캡처 + 미리보기 열림이면 무시 | 수정 — sheet.js:218-224 keydown 캡처 단계 + 미리보기 열림이면 무시. 브라우저 확인: Esc 1회=미리보기만, 2회=시트 |
| A7 | P3 | sheet.js siblingsOf/close | 같은 담당 두 묶음 경계 넘어 이전·다음 후 닫으면 초점·위치 사라짐 | close 에서 reveal(id,{scroll:false}) 후 focus | 수정 — sheet.js:158-165 닫을 때 reveal(id,{scroll:false}) → focus → scrollIntoView(nearest) |
| A8 | P3 | mobile-queue-focus.js | 시트 안 카드에 table-info 강조·scrollIntoView | 보이는 것만 — 확인 | 보류(지시: 기록만) — 시트 안 카드 강조는 확인 필요 |
| A9 | P3 | mobile_list.html:11-17 | 예전 foms-visit-summary 가 새 머리 숫자와 겹침 | 사용자 결정 | 수정 — B2 로 처리(요약 줄 삭제) |
| A10 | P3 | tabs.js | 영문 이름 대소문자만 다르면 탭 둘로 갈림 | 키로 합치기 | 보류(지시: 기록만) — 영문 대소문자 이름 합치기 |
| A11 | P3 | tabs.js localStorage | 날짜만으로 구분 → 여러 사람 같은 기기 섞임, 범위 모드 한 벌 | 키에 사용자 id | 보류(지시: 기록만) — localStorage 키 사용자 구분 |
| A12 | P2 | sheet.js open(focus) | `focus_order` 소비 뒤 주소에서 안 지워 재진입·뒤로 가기마다 시트 재오픈·앞 기록 잘림 | open 직후 replaceState 로 focus_order 제거 | 수정 — sheet-parts.js:121 dropFocusParam(주소에서 focus_order 제거+셸 syncRenderedUrl), sheet.js:277 시트 열기 전 호출 |
| A13 | P3 | tabs.js swipe | 터치 밀기 뒤 suppressUntil 400ms 가 다음 정상 탭을 먹음 | pointerdown 에서 0 으로 초기화 | 수정 — tabs.js:247 pointerdown 에서 suppressUntil=0 |
| A14 | P2 | tests | 새 JS 테스트가 글자 존재만 확인 — A1·A3·A12 못 잡음. 한 담당 두 묶음 렌더 테스트 없음 | 셸 건너뛰기 조건 계약 테스트 + 두 묶음 렌더 테스트 | 수정 — test_measurement_mobile_unified.py: 셸 건너뛰기 조건 계약, 한 담당 두 묶음 파셜 렌더(탭 1개·합산 1/2·내 묶음 둘 다 펼침·mine 전부 펼침), A2·A3·A4·A5·A6·A7·A12·A13 순서 계약 |

## 리뷰 B — 화면·목업 일치 (390×844 실렌더, 스크린샷 scratchpad/ux/shots/)

| # | 등급 | 위치 | 내용 | 제안 | 상태 |
|---|---|---|---|---|---|
| B1 | P2 | measurement-mobile-glance.css ~776 | 이전·다음마다 시트 높이가 바뀌어 단추가 손가락 밑에서 움직임(윗단 y 250→360→220) | `.foms-meas-sheet__panel` 고정 height(=max-height) + body flex:1 | 수정 — CSS 953-961 패널 고정 height + body flex:1/min-height:0. 브라우저 확인: 이전·다음 3회 윗단 y=84 고정 |
| B2 | P2 | mobile_list.html:3-19 | 옛 `foms-visit-summary`("완료"=넘김)와 새 머리("실측"=체크) 뜻 다른 숫자 두 벌, 목업에 없음 | 삭제 + 테스트를 "없어야 한다"로 | 수정 — mobile_list.html:5 요약 줄 삭제(빈 목록 분기는 무관), 테스트를 '없어야 한다'로 뒤집음 |
| B3 | P2 | mobile-glance-sheet.js show/close | aria-modal 만 있고 뒤 화면 inert 없음 → Tab 이 뒤로 샘 | 열 때 목록·셸 본문·하단 탭 inert, 미리보기 모달 제외 | 수정 — sheet-parts.js:72-95 시트→body 형제 inert(미리보기·오프캔버스·모달·토스트 제외, 품은 상자는 안으로 내려감), sheet.js:126/157. 브라우저 확인: 하단 탭·목록·셸 머리 inert, 미리보기·타임라인 시트는 제외 |
| B4 | P2 | 시트 안 카드 meta 링크 | 주소 166×35, 연락처 100×16, 담당 36×16 — 44px 미달 | `.foms-meas-sheet__slot` 범위 CSS 로 min-height 44px | 수정 — CSS 962-967 시트 범위 meta 링크 min-height 44px. 브라우저 확인: 44px |
| B5 | P3 | sheet.js:116-118 | 사진 칸 제목 "실측 사진 · 사진 n" 없음, 위치가 목업(주소·연락처 아래)과 다름 | meta 뒤로 옮기고 제목 추가 | 수정 — sheet-parts.js:37-55 사진 칸을 meta 아래로 옮기고 '실측 사진 · 사진 n' 제목, CSS 968-996 |
| B6 | P3 | 시트 넘긴 주문 | "실측 완료" 알약이 ERP 편집 아래 따로 | 단추 줄 자리로 | 수정 — sheet-parts.js:57-61 '실측 완료' 표시를 카드 footer 로, CSS 997-1006 |
| B7 | P3 | CSS 531-532 | FAB 가 목록 오른쪽 아래 시간 칩·📷 가림 | 목록 padding-bottom ≈88px | 수정 — CSS 1007-1010 목록 padding-bottom 88px |
| B8 | P3 | 기존 규칙 | 이미지 저장 단추 38px | 통합 modifier 로 min-height 44px | 수정 — CSS 1011-1014 이미지 저장 min-height 44px(통합 modifier 범위) |
| B9 | P3 | mobile_list.html:63 | "펼침" 숫자 서버에서 1 고정 | 렌더 루프에서 셈 | 수정 — mobile_list.html:15,22 렌더 루프에서 펼친 담당 이름 수를 셈 |
| B10 | P3 | 실기기 | iOS 16 미만 스크롤 잠금, 글자 확대 시 고정 탭 높이 70px | 스테이징 실기기 확인 | 보류(지시: 기록만) — 스테이징 실기기 확인 항목 |
