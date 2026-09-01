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

## 후속 T7 — 실패한 집 재시도 (2026-09-01)

착수 전 사실 확인에서 **원장의 '재시도 버튼이 없다'가 틀렸음**이 드러났다: 실패한 집은
`eligible` 로 남아 띠의 기본 버튼이 이미 다시 보내고 있었다(실측: `failed:1 eligible:1`).
진짜 빈 자리는 '**그 집 하나만**' 보내는 길이었다 — 기본 버튼은 아직 안 보낸 집까지 함께
보내고, 단건 재시도는 워크벤치에서 집을 열어야만 됐다(실측 대시보드엔 길이 없었다).

- 줄마다 '이 집 다시 보내기' — 기존 단건 라우트 `POST /<link_id>/fulfillment {action:'dispatch'}`
  재사용. **새 라우트·매니페스트 등재 0건.**
- **막힘이 실패를 이긴다**(state 우선순위 `sent > blocked > failed > pending`). 둘 다인 집을
  '실패'로 부르면 화면이 못 나갈 재시도를 권하고, 그 재시도는 서버 가드에 그대로 막힌다.
  이 순서 덕에 `state == 'failed'` 인 집은 **항상** 보낼 수 있는 집이다.
- 폴링을 `watch(plan, …)` 로 일반화해 일괄·단건이 같은 배선을 쓴다. 재시도 뒤 그 집이
  또 실패하면 버튼을 **다시 그린다**(폴링이 칸을 갈아 끼우므로 안 그리면 두 번째 길이 사라진다).
- 검증: bulk_dispatch 관련 70 passed(신규 8), CI 본 레인 7231 passed, pre_push_smoke exit 0.
  red-check: 우선순위를 되돌리면 막힘/재시도 계약 2개가 빨개진다(확인함).

## 운영 승격 (2026-09-01)

- PR #219 머지 — production `376362c3`. 검사 4종(test·pg-lane·harness·perf-gate) 전부 SUCCESS,
  mergeStateStatus=CLEAN.
- 승격 트리에서 **본 스위트 직접 실행 7232 passed**(승격 PR 이 안 도는 관문) + pre_push_smoke exit 0.
- completeness 는 `INCOMPLETE: missing baseline deps=84` 로 멈췄다. 운영이 cherry-pick 으로 받아
  SHA 만 다른 잔재라, **내 diff 가 기대는 것들을 내용으로 확인**하고 `--allow-incomplete` 로 진행했다:
  `bulk_dispatch.py` 존재 · `naver_ingest_bulk_dispatch` 라우트 1 · `is_naver_bulk_dispatch_enabled` 1 ·
  두 템플릿 파셜 존재.
- 승격 충돌 3건(전부 docs 계보): `AI_STATUS`(운영 계보 진행 중 목록은 그대로 두고 머리말만 한 칸 밀었다 —
  상단 40줄 예산이 3985/4000 이라 새 줄이 안 들어간다), `AI_CHANGELOG`(이번 승격분 한 줄만),
  `foms_failopen_inventory.json`(운영본 기준 재생성).
- 운영 킬스위치는 이미 켜져 있어(`FOMS_NAVER_BULK_DISPATCH_ENABLED=1`) 배포 즉시 화면에 반영된다.
- **여전히 미검증**: 실브라우저 폴링·진행 문구. 다음 일괄 때 화면 확인이 남는다.

## 후속 T8 — 안 붙은 수집분을 화면이 짚는다 (2026-09-01)

운영 실사용에서 사용자가 잡았다: 오늘 실측인 **천화진(#5054)이 발송 대상에 없다.**
운영 DB 읽기 전용 조회 결과 원인은 발송 선별이 아니라 **붙이기 누락**이었다 —
수집분 5행(묶음 `2026082810288661`, 08-28 10:00 수집)이 `order_id IS NULL` 로 떠 있었다.
발송 대상 판정의 유일한 축이 링크 존재라서, 안 붙은 집은 **화면 어디에도 안 나타난다.**

전수 확인(이름 + 전화 뒷 8자리 두 축): 오늘 실측 15건 중 링크 없는 10건 가운데 미연결
수집분과 매칭되는 것은 천화진 하나뿐. 나머지 9건은 네이버 유래가 아니다.

운영 잔량: 미연결 수집분 **76행 / 21묶음**(08-25~08-31). 그중 17묶음은 ERP 주문이 이미
있어 붙이기만 빠졌고, 4묶음은 주문 자체가 없다(임은비 2건·김민진·차유헌). 대부분
실측일이 이미 지났다 — **지나간 날 발송 대상에서도 통째로 빠졌다.**

- `find_unlinked_matches(session, on_date)` 신설 — 오늘 실측인데 링크 없는 주문과
  `order_id IS NULL` 수집분을 대조. 축은 **전화 + 네이버 수령인명**(사용자 확정 2026-09-01:
  "수집 및 ERP 입력된 주문건은 무조건 네이버 수령인명 기준"). **주문자명은 축이 아니다** —
  운영 실데이터에 `문기범/문유주`·`김유리/김병준` 처럼 갈리는 집이 있고 ERP 에 들어간 이름은
  수령인명 쪽이었다. 어느 축으로 걸렸는지 `reason` 으로 함께 보여준다(전화 > 이름).
  키 뽑기는 붙이기 후보 화면과 같은 `_snapshot_keys`·`normalize_phone_digits` 재사용.
- 훑는 범위 60일·상한 300행, 상한에 닿으면 로그로 말한다.
- 두 띠에 '붙이면 대상이 되는 집 N' 줄 + 수집분→주문 링크. **대상이 0인 날에도 띠가 뜬다**
  (`state='none'`) — 오늘 네이버 집이 0인 이유가 바로 그것일 수 있다.
- **자동으로 붙이지 않는다.** 붙이기는 사람이 워크벤치 후보 화면에서 고른다.
- 검증: 신규 9 + bulk_dispatch 80 passed, CI 본 레인 7240 passed, pre_push_smoke exit 0.
  red-check: 판정 축을 전화→이름으로 바꾸면 4개가 빨개진다(확인함).
- 자산 핀 `?v=20260901a`(CSS·JS 동반, 계약 2곳).

- 수령인명 축 추가 후 운영 재대조(읽기 전용): 오늘 실측·링크없는 10건 중 여전히 **천화진 하나뿐** —
  앞선 전수 결론이 유지된다. 나머지 9건은 두 축 모두 어긋난다.
