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

## QA 비고 (2026-08-06)
- AABB union 1차 구현은 전국 뷰 사슬 병합(x53) — 그리드 셀 방식으로 교체(`64e64862`), 지역 단위 8클러스터 확인.
- cherry-pick 충돌 1건: as_dashboard_body.html CSS 핀 2줄(타 세션 timeline css 범프 vs 내 body css 범프) — 양쪽 핀 union으로 해소(기계적, 코드 의존 아님).
- 인벤토리 3종(failopen·writer·state)은 원격 tip 기준 worktree에서 재생성 후 동승.
