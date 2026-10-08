# CS 확인 승인 = 최종 완료 (CS-AUTO-COMPLETE-01)

- 날짜: 2026-10-08 · 상태: 초안(승인 대기)
- 계기: 운영 `/erp/dashboard?stage=CS` 주문 #5450. "CS 확인 완료" 배지가 붙었는데도 CS 탭에 남아 있다.

## 1. 현재 동작 (사실)
- quest 승인 API(`foms/api/quest.py` `api_order_quest_approve`)는 `_STAGE_ADVANCE`
  (`foms/services/orders/quest_transition_service.py:74`)에 있는 RECEIVED·MEASURE·CONFIRM 세 단계만
  다음 단계로 넘긴다. CS 승인은 기록만 남는다. 승인 확인 문구도 "단계는 'CS' 그대로 유지됩니다"라고 쓴다.
- COMPLETED 로 가는 길은 `complete_order_as_cs`(`foms/services/orders/cs_complete_service.py`) 하나뿐이다.
  이 함수를 부르는 버튼(`complete_order_control`)은 실측 대시보드 3곳에만 있고 ERP 대시보드에는 없다.
  그래서 ERP 화면만 쓰는 CS 담당자에게는 이 상태가 막다른 길이다.

## 2. 바꿀 것
1. **최종 승인 → 완료.** `api_order_quest_approve` 에서 `is_complete` 이고 현재 단계가 `CS` 이면,
   같은 트랜잭션 안에서 `complete_order_as_cs(override=None)` 를 부른다. `_STAGE_ADVANCE` 에는 넣지 않는다.
   CS 완료의 정본 경로(attempt 봉인·history·SecurityLog·CS_COMPLETE command)를 그대로 타게 하려는 것이다.
2. **보류·AS 가 있을 때.** 승인 전에 `cs_gate_code` 로 판정한다. quest 게이트는 이 승인으로 풀린다.
   HOLD_ACTIVE·AS_ACTIVE 이면 승인만 기록하고 단계는 CS 로 둔다. 응답에 `completion_blocked: {code, message}` 를 담아 화면이 이유를 보여 준다.
   이것을 실패(409)로 돌려주지는 않는다. 승인 자체는 유효하기 때문이다.
3. **이미 막혀 있는 주문(#5450 같은 경우).** CS quest 가 COMPLETED 인데 단계가 CS 이면, 재전이 경로가
   CS 도 받는다. 그 경우 승인 기록은 건드리지 않고 `complete_order_as_cs` 만 부른다.
   `can_retransition`·CTA 의 `retransition_label` 도 CS 에서 켠다. 그러면 완료 배지 옆에 "CS 확인" 재실행 버튼이 생긴다.
4. **문구.** CS 의 `approve_confirm` 을 "CS 확인을 마치고 완료 단계로 넘길까요?"로 바꾼다. `advances_stage=True`, `next_stage_label='완료'`.
5. **응답·화면.** `auto_transitioned=True`, `next_stage='완료'`. 기존 JS(`erp-dashboard-quest.js`·`erp-quest-approve.js`)는
   이미 auto_transitioned 를 받으면 행을 갱신하거나 화면을 다시 읽는다. 이 부분은 구현 때 확인한다. `completion_blocked` 를 받으면 사유를 띄운다.
6. **멱등.** 승인 요청의 idempotency key 를 CS_COMPLETE 에도 넘긴다. 같은 key 로 다시 오면 replay 한다.

## 3. 바꾸지 않을 것
- `cs/complete` 라우트, 실측 대시보드 완료 버튼, 강제 단계 변경 경로.
- 권한: 누가 CS 승인을 누를 수 있는지(quest_approve_authz)는 지금 규칙 그대로 둔다.
  `cs/complete` 의 `erp_edit_required` 보다 좁거나 같은지는 구현 때 대조하고, 더 넓으면 승인 전에 같은 검사를 추가한다.
- 데이터 마이그레이션 없음. 막힌 주문은 3번 버튼으로 사람이 넘긴다.

## 4. 위험
- 완료 전이는 STAGE_NOTIFICATION(알림)을 낸다. 지금까지 사람이 누르던 "완료"와 같은 알림이고, 새로 생기는 알림은 없다.
- 전이가 실패하면(If-Match·잠금 경합) `complete_order_as_cs` 가 rollback 한다. 그러면 승인 기록도 함께 사라지고 오류가 돌아간다. 사용자는 다시 누르면 된다.

## 5. 검증
- 새 테스트:
  - CS 최종 승인 → COMPLETED, attempt 봉인, history 에 "CS 완료 -> 최종 완료"
  - 보류 중 승인 → 승인만 기록, completion_blocked=HOLD_ACTIVE
  - AS 진행 중 → AS_ACTIVE
  - 완료 quest 이면서 단계 CS → 재전이로 COMPLETED
  - 같은 key 재요청 → replay
- 기존 `tests/domains/test_state_quest.py`·`test_auth_quest_approve.py` 의 "CS 승인은 no-op" 단언을 새 규칙으로 고친다.
- `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1` exit 0.
- 스테이징 실화면: claude_master 로 CS 주문을 승인하고, 완료 탭으로 이동하는지 확인한다.
