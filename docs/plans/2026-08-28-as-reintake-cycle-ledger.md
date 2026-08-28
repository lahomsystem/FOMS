# AS 재접수 회차·방문일 리셋 수정 원장 (2026-08-28)

## 증상 (사용자 보고, production /erp/as)
1. AS 재접수를 해도 배지가 `1차 · 진행 중` 으로 뜬다. 다음 회차(2차)로 표기되고 이전 건은 종결로 보여야 한다.
2. 재접수해도 기존 AS 방문일이 그대로 남아 있다. 새 건이면 방문일이 리셋되어야 한다.

## 근거 (production 실데이터, 읽기 전용 조회)
- 주문 #4434: `as_lifecycle.cycles` 2건. cycles[0] 2026-08-27 완료(유상 200,000 봉인),
  cycles[1] 2026-08-28 접수 = current. `current_cycle_ordinal(sd) == 2` — **백엔드 데이터는 정상**.
- 같은 sd 로 `build_as_round_chart_view` 실행 결과:
  - `current_round == 1`
  - 현재 건 그룹: ordinal=2, rounds=[(no=1, open=True)] → 템플릿이 `1차 · 진행 중` 출력
  - 종결 건 그룹: ordinal=1, rounds=[(no=1, open=False)] → `1차`
- 즉 화면의 `N차` 는 AS 건 순번이 아니라 **한 건 안의 판정 회차**(`current_as_round` =
  1 + 미결 verdict 수, `foms/services/orders/as_log.py:173-195`, cycle 필터 없음)다.
  재접수는 미결 판정을 만들지 않으므로 차수가 전진하지 않는다.
- 방문일: `_issue_new_cycle`(`as_cycle_service.py:406-447`)은 billing 만 봉인하고
  `schedule.as_visit` 를 건드리지 않는다. `complete_as_cycle` 도 방문일을 지우지 않는다
  (`as_cycle_service.py:617-629`). → 새 건이 직전 건 방문일을 그대로 물려받는다.
  `order_schedule_dates(kind='as_visit')` 는 sd 파생이라 sd 만 고치면 따라온다.

## 결정 (CEO)
- **T1 표기**: `N차` 를 주문 전체의 처리 시도 순번(= 건 순서 × 건 안의 회차 순서)으로 **표시 전용**
  재번호(`display_no`)한다. 스탬프(`as_log[].round`)와 `data-round` 계약은 건드리지 않는다.
  종결 건의 회차에는 `· 종결` 을 붙인다.
- **T2 방문일**: 새 cycle 발급 시 `schedule.as_visit.date/time` 을 비우고 schedule_link 를 해제한다.
  `availability`(가능시간)는 주문 속성이라 유지 — 사용자 요청 범위 밖.
- 열린 건 재접수(`_apply_reregistration`, 지방 AS 재상차)는 **그대로 둔다** — 새 건이 아니므로
  차수·방문일 리셋 대상이 아니다(test_state_as.py:173, test_as_billing.py:582 이 고정).

## Task 원장
| Task | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | 회차 표시 재번호 + 종결 표기 | 신규 테스트 red→green, `tests/domains/test_as_round_chart.py` 전체 green | PENDING |
| T2 | 새 cycle 발급 시 방문일/시각/링크 리셋 | 신규 테스트 red→green, `tests/domains/test_state_as.py`·`test_as_schedule_link*.py` green | PENDING |
| T3 | 교차 리뷰 + 회귀 스위트 | AS 도메인 테스트 전량 green + `import app` APP_OK | PENDING |
| T4 | deploy push + CI green | pre_push_smoke exit 0, CI 전 워크플로 green | PENDING |
| T5 | 브라우저 실동작 확인 | 스테이징에서 재접수 → 2차 표기 + 방문일 비움 확인 | PENDING |
| T6 | production 승격 | 자기 세션 커밋 cherry-pick | PENDING |
