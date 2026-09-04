# 취소·반품 끝난 주문 → 집 pane 휴지통 버튼 (진행 원장)

- 등급: `**B` / 브랜치: `deploy` / 시작 HEAD: `0ca451554`
- 설계·승인: 완료(캔버스 6종 `12f79ca4-e032-4598-ae1d-7f102e970213`). 이 원장은 구현 진행만 기록한다.
- 급소: **판정 축은 주문**이다. `find_ghost_orders` 가 `order_id` 로 묶고 `canceled == link_count`
  일 때만 유령으로 친다 — 살아 있는 ADDON 집이 붙어 있으면 그 주문은 모집단에서 자동으로 빠진다.
  pane 이 집 단위로 판정식을 새로 만들면 그 안전이 사라진다. 새 헬퍼는 `find_ghost_orders` 의
  버킷 로직을 **그대로 재사용**한다(조회 범위만 그 주문의 링크로 좁힌다).

## Task

| # | 할 일 | 완료 기준 | 상태 |
|---|-------|-----------|------|
| T1 | `ghost_orders.judge_order_discard()` — 주문 1건 판정(can_discard / needs_reason / discard_block) + 단계 한글 라벨 | 새 단위 테스트 통과, `find_ghost_orders` 기존 테스트 무변경 통과 | DONE |
| T2 | `_pane_context` 주입 (전체 렌더·조각 렌더 자동 동일) | pane 조각 응답에도 버튼이 나온다는 테스트 통과 | DONE |
| T3 | pane 템플릿 — 조건부 버튼 + 경고 띠 6종 | 렌더 테스트(열림/사유/닫힘 3종/재결제 경고) 통과 | DONE |
| T4 | `naver-workbench.js` — pane 분기(확인창 1회 → 기존 라우트 → softRefresh) | 소스 계약 테스트 통과 | DONE |
| T5 | CSS 최소 신설(기존 `.alert`·`.wb-fork__reason` 재사용) | 신규 규칙 5줄 이하 | DONE |
| T6 | 자산 핀 `20260904c` → `20260904d` + count==2 계약 5곳 | grep 전수 0건 잔여 | DONE |
| T7 | 유령 띠·라우트 단계 이름 한글화(STAGE_LABELS) | 띠·라우트 문구에 enum 미노출, 감사 원장은 enum 유지 | DONE |
| T8 | 게이트·푸시 | APP_OK · pytest · pre_push_smoke · CI 전 워크플로 green | DONE |

## 기록

- T1~T7 완료. `python -c "import app"` → `APP_OK`.
- `pytest tests/services/integrations/ tests/domains/ -q` → **8328 passed, 5 skipped**
  (신규 15건: 판정 헬퍼 7 · pane 렌더 7 · 띠 단계 한글 1).
- 회귀 1건 수정: `test_naver_claim_phase.py::test_band_shows_pending_row_without_a_button` 이
  "폐기 버튼 없음"을 `data-order-id` 부재로 재던 것 — 이제 pane 에도 같은 판정의 버튼이
  서므로 두 자리가 안 갈린다. 띠는 버튼 id 부재로, pane 은 `disabled` 로 각각 잰다.
- `scripts/ops/pre_push_smoke.ps1` → **PRE-PUSH SMOKE PASSED**.
- 푸시 직전 origin/deploy 가 타 세션 커밋 2개(정산 내보내기 안내 줄)로 앞서 있어 rebase 후
  smoke 재실행(PASSED). AI_STATUS 는 서로 다른 줄이라 충돌 없음 — 상대 문장 잔존 확인.
- deploy `1fd113d55` push. CI 4/4 success(FOMS CI · PG Lane · Harness · perf-gate).

## 이번에 하지 않은 것(별건)

- 유령 주문 띠가 20건에서 잘리는데 잘렸다고 말하지 않는 것
- 주문 목록(`templates/orders/index.html:857`) 휴지통 버튼에 관문이 없는 것
- 정리 계획 카드(`repay_reconcile.py:301·305`, pane `:1115`)의 단계 enum 노출 — 브리프 범위 밖
  (`test_naver_repay_reconcile_card.py:154` 가 `"MEASURE"` 를 고정한다)
