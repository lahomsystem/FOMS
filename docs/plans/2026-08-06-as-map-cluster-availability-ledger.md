# AS 지도 v2 (클러스터+가능시간) — Progress Ledger

스펙: `docs/specs/2026-08-05-as-map-cluster-availability-design.md`
사용자 확정(2026-08-06): 대상=AS 미완료 전체 · 둘 다 진행(클러스터 먼저) · 입력=방문일 옆 미니 버튼 팝오버.
운영 반영은 스테이징 데모 → 사용자 승인 후.

| Task | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | F1 스크린 겹침 클러스터 (map-view-kakao.js, route 모드 제외, 접힘 뷰에서만) + 그룹 팝업 확장(상태 점·fitBounds 펼침) + ?v 범프 | 코드 완료·JS 문법 OK — 실브라우저 검증은 T5 | DONE(코드) |
| T2 | F2-a availability 스키마 + field_update `as_visit_availability` + as_log 기록 + 단위테스트 | test_as_availability.py 4 passed + APP_OK | DONE |
| T3 | F2-b AS 탭 입력 UI — PC 방문일 셀 미니 버튼+팝오버, 모바일 v2 카드 칩 표기 | as_dashboard 계열 102 passed(렌더 포함), 실입력 검증은 T5 | DONE(코드) |
| T4 | F2-c 지도 필터 — build_as_incomplete_map_query availability 파라미터 + 헤더 select(요일/시간) + 마커 주말 도트 + 팝업 행 + 미기입 N건 고지 | 지도·가능시간 테스트 24 passed | DONE |
| T5 | 스테이징 종합 QA(페르소나 시나리오 2종) + deploy push + CI green → **사용자 데모·승인 대기** | DONE — 전국 뷰 55건→지역 클러스터 8개(xN 뱃지)·팝업 53행+상태점·펼침 줌인, 칩 팝오버 저장→새로고침 유지→타임라인 로그, 주말 필터=1건+미기입 54건 고지, 실측(8/5, 2건) 무회귀, 콘솔 0. deploy `ac58a6c4`+`146e27fe`(로컬)→원격 `1bac5aa0`·`1b87eba6`·`f6dc8cb9`, CI green(perf-gate는 후속 push 대체로 cancelled, tip `c50ac9ac`에서 success) | DONE |
| T6 | (사용자 승인 후) production 승격 — cherry-pick PR | PR 체크 green + merge + 운영 신코드 확인 | PENDING(승인 대기) |
| T7 | 데모 피드백 2건 — ① 팝업이 클러스터 뱃지 뒤로 가림(zIndex 60→500 서열 정정) ② PC 필터 스킨 개편(흰 필드+쉐브론·활성 앰버 링·초기화 버튼, body.map-as-mode+≥891px 이중 게이트, 모바일·실측 지도 무변경) | 지도 계열 27+가용성 4 passed·JS 문법 OK·스테이징 실브라우저 QA(팝업 최상단, 필터 스킨·초기화 동작, 콘솔 0)+CI green | DONE — 로컬 `361ec121`→원격 `472dc818`. 스테이징 QA(claude_master·1440px): 팝업 z=500>핀 400 DOM+스크린샷 확인, 앰버 링·초기화(55건 복원) 동작, 실측 지도 회귀 0(콜론 라벨·반투명 유지), 지도 콘솔 에러 0. CI 4 워크플로 green(FOMS CI·PG Lane·Harness·perf-gate) |
| T8 | 데모 피드백 2차 4건 — ① 그룹 팝업 다건 시 내용이 박스 밖 가로 넘침 ② 리스트 스크롤 불가 ③ 팝업 위 휠이 지도 줌으로 전파 ④ 단건 팝업 주소 한 줄 잘림. 근본 원인 2개: 카카오 CustomOverlay 래퍼 white-space:nowrap 상속(①④) + 팝업 이벤트 지도 전파(②③). 수정: .foms-kmap-popup white-space:normal + guardPopupEvents(stopPropagation, preventDefault 없음) + panPopupIntoView(PC, 화면 밖 잘림 픽셀 보정) + mountPopup 공통화, ?v=20260806d | 지도 27 passed·JS OK·스테이징 QA(주소 2줄 랩·행 넘침 0·scrollTop 동작·휠/드래그 전파 0 계측·오토팬 -25→93px·콘솔 무결)+CI green | DONE — 로컬 `40c77472`→원격 `c543a794`, CI green(FOMS CI 완주 확인 후 마감) |

## v3 — AS 정보 중심 개편 (스펙: `docs/specs/2026-08-06-as-map-as-info-design.md`, **2026-08-06 승인**)

사용자 확정: 담당자 행 전체 숨김(지정 버튼+영업 담당 표기) · T6 승격은 v3 완료 후 deploy 테스트부터.
진행 방식 확정(2026-08-06 2차): T9~T12 한번에 완주 · **단 T10 카드는 중간 시안 스크린샷 사용자 확인
게이트 1회**(로컬/스테이징 렌더 캡처 제시 후 진행) · 지난 방문일 = 빨강 "N일 지남" · 새 세션에서 재개.

| Task | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T9 | F1 페이로드 — as 모드 point에 as_bucket(4쿼리 id-set)·as_visit_date/dday·as_content_preview·as_billing·as_received_date 보강 | test_as_map_snapshot 확장(as 필드 계약+measurement 무변경 가드) passed + APP_OK | PENDING |
| T10 | F2 우측 카드 as 분기 — 버킷 배지·AS 내용·방문일 D-day(지남=빨강 "N일 지남")·가능시간 칩·유상 배지, 실측 시간 행/담당자 행 전체 제거 | **중간 시안 스크린샷 사용자 확인 게이트** → 렌더 계약 테스트 + 스테이징 카드 표기 확인 | PENDING |
| T11 | F3+F4 팝업 as 분기(버킷·방문일·내용·유무상·접수일, 좌표/실측시간 제거) + 그룹 행 방문일 표기 + 미정 pill 점선 + ?v 범프 | JS 문법 OK + 스테이징 팝업 표기 확인 | PENDING |
| T12 | 스테이징 종합 QA(페르소나 2 시나리오) + 실측 지도 무회귀 + deploy push + CI green | QA 통과·CI 전 워크플로 green | PENDING |

## QA 비고 (2026-08-06)
- AABB union 1차 구현은 전국 뷰 사슬 병합(x53) — 그리드 셀 방식으로 교체(`64e64862`), 지역 단위 8클러스터 확인.
- cherry-pick 충돌 1건: as_dashboard_body.html CSS 핀 2줄(타 세션 timeline css 범프 vs 내 body css 범프) — 양쪽 핀 union으로 해소(기계적, 코드 의존 아님).
- 인벤토리 3종(failopen·writer·state)은 원격 tip 기준 worktree에서 재생성 후 동승.

## T7 QA 비고 (2026-08-06)
- 스테이징에 `TESTCLR-` 시드 잔존(x26 클러스터·마포) — 지방 대시보드 세션 몫, 본 세션 미정리.
- 분류=미결 0건은 실데이터 상태(visit_confirmed 버킷은 정상 반환 — 파이프라인 무회귀).
- pre_push_smoke 1건 실패는 타 세션 미커밋 AI_STATUS.md 1줄(4015자/4000 예산)이 원인 — 본 커밋 미접촉·push 대상 클린 worktree 미포함, 나머지 306 passed.
