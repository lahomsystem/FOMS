# 진행 원장 — 일괄 발송처리 결과 UI (NAVER-BULKDISPATCH-02)

- 계획서: `docs/plans/2026-08-31-naver-bulk-dispatch-result-ui.md`
- 선행 설계: `docs/specs/2026-08-31-naver-bulk-dispatch_SPEC.md`
- 워크트리: `c:\tmp\foms-s-s0831-085306` (session/s0831-085306, origin/deploy 기준)
- 시작 HEAD: `78a5bb2d`

## 설계 요약 (착수 시점 확정)

띠를 지우지 않고 **상태를 바꾼다.** 서버가 오늘 실측 네이버 링크 **전체**(발송 전/후 모두)를
집 단위로 접어 상태를 계산하고, 화면 두 곳이 같은 값을 렌더한다.

키 계약: `build_preview` 는 기존 키(`date`/`count`/`eligible`/`blocked`/`rows`)의 **뜻을
바꾸지 않는다** — 그 넷은 지금도 앞으로도 "지금 보낼 대상"이다. 결과 표시는 **새 키**로 온다
(`day_total`/`sent`/`failed`/`last_sent_at`/`state`/`day_rows`/`show`).

발송 판정 신호는 **두 벌**(우리 표식 `triage_state.fulfillment.dispatched_at` + 네이버 원본
`delivery.sendDate`). 판매자센터 수동 발송분을 "남음"으로 세지 않는다.

## Task

| task | 상태 | 완료 기준 |
|---|---|---|
| **T1** `build_day_summary` 신설 + `select_targets`/`build_preview` 재배치 | DONE | 기존 select/execute/preview/strip 테스트 4파일 green + 신규 day-summary 테스트(전부 발송·수동 발송분·일부 발송·실패 표식·대상 0) green |
| **T2** 진행 조회 GET 라우트 | DONE | ADMIN/MANAGER 200 + 띠와 **같은 함수** 값, STAFF 차단, 쓰기 0 |
| **T3** 워크벤치 띠 상태화 | DONE | 완료/부분/실패/대기 4상태가 화면 문구로 갈린다 + 대상 0 이면 띠 없음 |
| **T4** 실측 대시보드 띠 상태화 | DONE | 같은 4상태, v3 풀페이지 버튼 0개 유지 |
| **T5** 버튼 직후 진행 표시(alert 제거) + 폴링 | DONE | 새로고침 없이 "N집 발송 완료"까지 바뀐다 |
| **T6** 게이트·푸시 | DONE | `pre_push_smoke` exit 0 + smoke 사각 3종(policy manifest·ACTION_LABELS·docs-scope) 직접 실행 + deploy push 후 `gh run list` 전 워크플로 green |

## 기록

- 2026-08-31 착수. 워크트리 기존 것 재사용.
- T1 DONE: `build_day_summary`/`_build_target` 신설, `select_targets` 는 그 위 얇은 필터로 재배치.
  발송 판정은 두 신호(우리 표식 + `extract_delivery.send_date`) — 워커 멱등 판정과 같은 자리를 읽는다.
  신규 `test_naver_bulk_dispatch_day_summary.py` 15개 + 기존 4파일 34개 = 49 passed.
  red-check: `_is_dispatched` 의 네이버 신호를 끄면 수동 발송분 테스트 2개가 빨개진다(확인함).
- T2 DONE: `GET /admin/naver-ingest/bulk-dispatch/state` (ADMIN·MANAGER, 읽기 전용, `build_preview` 그대로).
  매니페스트 2종은 POST/PUT/PATCH/DELETE 만 등재 대상이고 감사 스캐너도 GET 을 제외한다 — 확인함.
- T3/T4 DONE: 두 띠 모두 `show`+`state` 로 갈라 렌더. 완료=초록 배지·부분=두 수 병기·실패=빨간 줄·대기=종전 문구.
  표는 `day_rows`(오늘 전체)로 바꿔 발송된 집이 시각과 함께 남는다. 워크벤치 자산 핀 `?v=20260831e`(CSS·JS 동반).
- T5 DONE: 성공 경로 `window.alert` 제거 — 띠 안 `[data-naver-bulk-dispatch-status]` 진행 문구 + 3초 간격
  최대 20회 폴링. 종료 조건은 `eligible === 0`(남은 집 수로 재면 막힌 집이 있는 날 안 끝난다).
- 검증: bulk_dispatch 관련 63개 + 워크벤치 325개 + 등재 계약 240개 + measurement 244개 green.
  red-check 2건: 띠 게이트를 `count` 로 되돌리면 완료 상태 테스트 2개가 빨개진다(확인함).
- T6 DONE: `pre_push_smoke` exit 0(352 passed) · smoke 사각 3종 직접 실행 green ·
  CI 본 레인 로컬 전수 7223 passed. deploy push = `18df627a`·`e204565d`·`43f4024d`
  (자기 커밋만 cherry-pick — `push_own_session_commits.py`).
  CI 전 워크플로 green(head `43f4024d`): FOMS CI · Harness CI · FOMS PostgreSQL Lane ·
  perf-gate (staging) 4/4 success.
- 도중에 잡힌 CI 사각 1건: 워크벤치 템플릿 `?v=` 핀을 **두 계약 파일**이 각각 못박고
  있어(async_result·origin_cleanup) 한쪽만 고치면 pre_push_smoke 는 통과하고 CI 만 빨개진다.
- **미검증**: 폴링·진행 문구의 실브라우저 동작. 누르는 순간이 불가역이라 실호출을 하지
  않았다 — 다음 운영 일괄(오후 5시) 화면 확인이 남는다.
