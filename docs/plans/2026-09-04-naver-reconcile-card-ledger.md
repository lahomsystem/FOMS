# 원장 — 네이버 워크벤치 '정리 계획' 카드 정직화·정책 동기화 (2026-09-04)

사용자 제보: "재결제·추가결제 시 이 안내 문구가 의미가 있나? 어차피 선택할 수 있는 옵션이 없는데."

## 근본 원인 (조사 결과)
2026-09-02 사용자 결정 커밋 `549a801fb` 가 공용 상수 `DISCARDABLE_STATUSES` 의 뜻을
"못 접는 목록"에서 "**사유 없이** 접히는 목록"으로 바꿨다. 유령 주문 띠는
`ghost_orders.py:187-190` 에서 그 새 뜻을 쓴다(단계 밖은 관리자+사유로 접힌다).
그런데 `repay_reconcile.discard_gate`(87-105)는 그 커밋에서 손대지 않아 옛 뜻(목록 밖이면
완전 잠금)으로 남았다. `discard_gate` docstring 은 "유령 주문 띠와 **같은 상수**를 쓴다 —
두 화면이 서로 다른 단계를 열어 주면 담당자가 어느 쪽을 믿어야 할지 알 수 없다"고 선언해
놓았으므로 **그 선언이 지금 거짓이다.**

조사 중 추가 발견(사용자 제보 밖):
- 후보 표는 `all_done` 일 때 "재결제 신호"라 적는데 버튼은 **추가결제가 먼저·강조색**이다
  (`naver_workbench_pane.html:950` vs `992-999`). 눈이 가는 쪽이 권고와 반대라
  관계 오선택 → 예약금 '바꾸기'/'더하기'가 갈려 고객 청구액이 틀어진다.
- 카드의 취소 처리에는 **네이버 확정 관문이 없다**(`repay_reconcile.py:222-227` 은 단계만 본다).
  유령 띠 라우트는 `claim_phase == "done"` 을 이중 검사한다(`naver_ingest.py:4596-4600`).
  드리프트가 양방향이다 — 단계축 과잉, 돈축 미비.

## 사용자 결정 (2026-09-04)
1. 정리 계획 카드에서도 **이유를 적으면** 실측 뒤 주문을 접을 수 있게 한다(유령 목록과 동일 규칙).
2. 네이버가 취소를 확정하기 전에는 **정리 실행을 막는다**(경고만으로 두지 않는다).
3. 3단계 전부 진행.

## 뒤집지 않는 것
- D-1: 예약금은 시스템이 넣지 않는다(안내만).
- D-2: DISCARD 는 붙이지 않는다(휴지통 주문에 새 집을 묶으면 '주문 만들기'가 막힌다).
- 2026-08-25: 네이버 판매자 직접취소는 이 흐름에서 제외(불가역).
- 기각: 라디오 강제 활성화 · 비활성 갈래 완전 숨김 · 운영 데이터 백필 · 확인창 전면 제거.

## 함정 (조사로 확인)
- `?v=20260904a` 를 **4개 테스트가 `count == 2`** 로 고정한다:
  `test_naver_backfill_route.py:168` · `test_naver_fulfillment_err_at.py:62` ·
  `test_naver_origin_cleanup.py:535` · `test_naver_workbench_async_result.py:412`.
  CSS·JS 를 고치면 핀 2개와 이 4곳을 함께 올린다.
- `test_naver_repay_reconcile_card.py` L109·L125·L138 이 라디오 2개·`disabled`·"MEASURE"·
  "시스템이 넣지 않는다" 를 리터럴로 고정한다.
- 신규 mutation 라우트가 아니라 기존 `/reconcile` 파라미터 확장으로 간다 —
  신규 라우트를 만들면 manifest 2종 + 감사 라벨 등재가 따라온다.

## task 원장

| task | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | 권장 관계 SSOT + 후보 버튼 순서·강조 일치 + 2번 칸 태그·제목 갈래 수 분기 + 잠금 사유 사람말 | card 7 passed(신규 `test_attach_buttons_follow_the_signal_the_table_prints`·`test_plan_card_says_there_is_nothing_to_choose_when_the_fork_is_one`) | **DONE** |
| T2 | 확정 전(`all_pending`/`all_mixed`) 정리 실행 차단 — 계획(`can_run`/`run_block`)·서버(`run_reconcile`)·라우트 이중 검사·화면 버튼 비활성 | `run_gate` 테스트 6건 · 통합 스위트 1648 passed | **DONE** |
| T3 | 취소 처리 갈래를 유령 띠와 같은 규칙으로 — 확정 필수 + 단계 밖은 관리자+사유. 라우트 `reason` 파라미터 확장, 화면 사유 칸 | route 12 passed(사유 없음 400 · 사유 있으면 200 + 감사 원문 · MANAGER 거절) | **DONE** |
| T4 | 자산 핀 범프 + 핀 계약 4곳 동반 갱신 · pre_push_smoke | 핀 `20260904a`→`b`(템플릿 2 + 테스트 4). smoke 서브셋 376 passed · **1 failed 는 내 변경 밖**: 이전 세션이 남긴 미추적 `tests/visual/test_tmp_as_sort_smoke.py` 가 visual 등재 계약에 걸린다(남의 파일이라 안 지움) | **DONE(선행 실패 1건 남음)** |

## 구현 결과 (2026-09-04)

- `order_candidates.py`: `RELATION_BY_CLAIM_CODE` + `recommended_relation()` 신설,
  `_order_view` 에 `recommended_relation` 실음. 신호 문구와 버튼 강조가 **같은 함수**를 읽는다.
- `repay_reconcile.py`: `discard_gate` → `discard_policy(status, claim_code)` 로 교체.
  잠금 축이 **단계 → 옛 결제 확정 여부**로 옮겨졌고, 단계는 `needs_reason` 축으로 분리됐다.
  `run_gate(claim_code)` 신설(갈래 무관 공통 관문). `run_reconcile` 이 `claim_code` ·
  `discard_reason` · `actor_is_admin` 를 받고 유령 띠와 같은 관문을 건다.
- `naver_ingest.py` 라우트: `reason` 파라미터, `run_gate` 이중 검사, 감사 detail 에
  `discard_reason` · `naver_claim_code` 추가. **신규 라우트 아님** — manifest·감사 라벨 무변경.
- 템플릿: 버튼 순서·강조 신호 연동 · 2번 칸 태그(`골라 주세요`/`자동 결정`)·제목 분기 ·
  사유 칸(갈래 라벨 **밖**, 중첩 label 회피) · 확정 전이면 실행 버튼 비활성.
- JS: `reason` 전송 + 사유 미입력 선차단, 확인창이 **관계를 가장 먼저** 다시 말한다.
- CSS: `.wb-fork__reason`.

### CEO 권고에서 의도적으로 벗어난 것 1건
CEO 는 "SUCCEED 단독이면 `window.confirm` 을 없애고 버튼 라벨을 동사화" 하라고 했다.
**따르지 않았다** — 그 확인창이 저장 직전에 **관계(재결제/추가결제)를 다시 말하는 유일한
자리**다. 관계 오선택이 이 화면의 P1 위험이므로, 없애는 대신 확인창 첫 줄을 관계로 바꿨다.
