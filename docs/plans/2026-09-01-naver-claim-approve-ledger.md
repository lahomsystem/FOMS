# 원장 — 네이버 클레임 승인 (T9)

> 2026-09-01 · 워크트리 `C:\tmp\nvclaimapv` · 브랜치 `session/nvclaimapv` (base `ffcc47ba3` = origin/deploy)
> 스펙: `docs/specs/2026-09-01-naver-claim-approve_SPEC.md`

## 왜 이 작업이 열렸나

사용자 요청(2026-09-01): "여기서 취소, 반품 승인을 실제로 할 수 있게 변경 해. 지금은 취소만
알아차릴 수 있고 실제 취소는 네이버에서 해야 돼."

착수 전 원장·메모리는 **반품 승인·거부가 착수 불가**라고 적고 있었다. 그 판정은 이미 뒤집혔다
— 반품 승인은 2026-08-31 운영 배포(PR #213 `c462bdb9`), 반품 거부는 2026-09-01 운영 ON
(PR #229 `7976fb2c`). 남아 있던 진짜 구멍은 둘이었다:

1. **취소 요청 승인** — `claim/cancel/approve` 가 저장소 전체 0건. 스펙 문서도 없었다.
2. **반품 승인 독립 경로** — `_approve_returns` 가 `request_return` 안에서만 불려,
   **고객이 먼저 낸 반품**은 승인할 방법이 화면에 없었다(거부 버튼만 있었다).

## 착수 전 사고 1건 — 낡은 워킹트리

`C:\DEV\FOMS` 가 `origin/deploy` 보다 **1432 커밋 뒤**(8/31 17:09 vs 9/1 17:05)였다. 첫 조사
3갈래가 그 트리를 읽고 "deploy 에 네이버 수집 코드가 아예 없다"는 결론을 냈다 — 전부 폐기하고
`origin/deploy` 에서 새 워크트리를 파 다시 조사했다. **조사 시작 전에 `git status -sb` 로
ahead/behind 를 본다**가 이 사고의 교훈이다.

## 규격 (공식 문서 원문, 2026-09-01)

`https://apicenter.commerce.naver.com/llms/llms.txt` + endpoint `.md` +
`wiki-주문-주문-상태-변경-흐름도.md`. 로그인·JS 없이 HTTP 200.

| 기능 | 엔드포인트 | body | 출발 상태 |
|---|---|---|---|
| 취소 승인 | `POST .../claim/cancel/approve` | **없음** | `CANCEL_REQUEST` · `CANCELING` |
| 반품 승인 | `POST .../claim/return/approve` | **없음** | 흐름도 R-1 = `COLLECT_DONE` |
| 반품 거부 | `POST .../claim/return/reject` | `rejectReturnReason` | `RETURN_REQUEST` · `COLLECTING` |

- **`claim/cancel/reject` 는 존재하지 않는다.** 취소 철회는 구매자만 한다(흐름도 분기 C).
- 응답은 셋 다 `successProductOrderIds` / `failProductOrderInfos`, idempotent.

## 사용자 결정 (2026-09-01)

- 범위: **취소 승인 + 반품 승인 둘 다** 만든다.
- 권한: **ADMIN·MANAGER 만**(반품 거부와 같은 층).
- ERP 휴지통 축(`DISCARDABLE_STATUSES = ("RECEIVED",)`)은 **이번에 건드리지 않는다** — 별건.

## CEO 판정 요약 (조건부 진행)

- 화면의 "취소 처리 잠김"은 **ERP 휴지통 잠금**이지 네이버 승인 잠금이 아니다. 두 축이 겹쳐
  있었고, 승인해도 접수 단계를 지난 주문은 계속 잠긴다.
- 진행 근거: "거부만 먼저 나가 있는 지금 상태가 아무것도 없는 것보다 나쁘다." 고객 반품 앞에서
  화면이 내주는 불가역 버튼이 거부 하나뿐인 비대칭을 방치할 수 없다.
- 자른 것: 일괄 승인 · 승인 후 ERP 자동 폐기 · **유령 띠 버튼**.
- 더한 것: 승인도 **OrderEvent** 로 주문 이력에 남긴다(거부는 남는데 환불이 안 남는 장부 금지) ·
  모달은 건수가 아니라 **상품주문번호+금액 목록**을 재진술 · 게이트를 **2개로 분리**해 단계 점등.

## 적대 검수에서 나온 것 중 실제로 고친 자리

| # | 결함 | 조치 |
|---|---|---|
| D4 | `_approve_returns` 에 대상 판정이 없다(접수 성공분 전제) | `is_return_approvable` 신설, 래퍼가 선별 |
| D5 | `return_awaiting_approval` 은 **우리가 접수한 건**만 담는다 → 독립 버튼의 주 대상이 통째로 빠진다 | 버튼을 `is_return_approvable` 카운트에 걸었다 |
| D6 | `NAVER_INGEST_RETURN_APPROVE_ENQUEUE` 를 접수+승인이 **이미 쓴다** | 신규는 `..._RETURN_APPROVE_ONLY_ENQUEUE` |
| H1 | `REFRESH_AFTER_ACTIONS` 값을 못박은 테스트 존재 | `test_naver_refresh_after_action.py:124` 함께 갱신 |
| H2 | 승인 실패가 `last_error` 에 안 들어가 화면이 "완료"라고 거짓말 | 두 진입점 모두 `_mark_failures` 호출 |
| H3 | 미등재 action 은 `naver_ingest.py:534-535` 폴백으로 **"발주확인 실패"** 로 읽힌다 | `FULFILLMENT_ACTION_LABELS` 에 승인 2종 + 기존 구멍이던 `return-reject` 등재 |
| H4 | 폴링 지문이 승인·거부 표식을 안 본다 → 타임아웃까지 "기다리는 중" | `_fulfillment_state` marks 에 `at_claim` 추가 |
| M8 | 표식 이름 `cancel_approved_at` 이 네이버 **읽기** 필드와 충돌 | `triage_state['cancel']['approved_at']` 로 분리 |
| D1·D2·D3·M4 | 유령 띠에 `link_id` 부재 · 주문 vs 집 단위 불일치 · 버튼 id 중복 | 띠에 버튼을 두지 않는다(CEO 판정). `lead_link_id` 로 **pane 링크**만 낸다 |

## Task 원장

| T | 내용 | 상태 | 완료 기준 |
|---|---|---|---|
| T1 | `client.approve_cancel_product_order` (body 없음) | DONE | AST 계약 + `import app` |
| T2 | 술어 2종·공개 진입점 2종·표식 축 분리 | DONE | `_approve_returns` 시그니처 무변경 |
| T3 | 큐 2종·워커 action 2종·`REFRESH_AFTER_ACTIONS`·action 라벨·폴링 지문 | DONE | `test_naver_refresh_after_action.py` green |
| T4 | 라우트 2종·게이트 2종·감사 2종·OrderEvent 2종·manifest 3곳 | DONE | `test_write_guard`·`test_auth_enforcement`·`test_audit_coverage_inventory` green |
| T5 | pane 버튼·모달(목록 재진술)·유령 띠 pane 링크·자산 핀 범프 | DONE | jinja parse + `tests/services/integrations` 1308 green |
| T6 | 신규 계약 테스트 `test_naver_claim_approve.py` | 진행 중 | 신규 파일 green + 회귀 0 |
| T7 | 문서·원장·AI_STATUS·커밋 | 진행 중 | pre_push_smoke exit 0 |

## 운영 켜기 절차 (단계 점등)

1. 게이트 **꺼진 채** deploy → production 승격.
2. 진짜 클레임 1건이 올 때 `web` 에만 `FOMS_NAVER_CANCEL_APPROVE_ENABLED=1` + 재배포.
   **worker 에 넣지 마라** — worker 1대라 재배포가 큐를 전면 정지시킨다.
3. 취소 승인 1건 성공 확인(감사 로그 + `triage_state['cancel']['approved_at']`).
4. 그 다음에 `FOMS_NAVER_RETURN_APPROVE_ENABLED=1`.

변수만 넣으면 안 켜진다 — 재배포 컨테이너의 부팅 시각이 변수 등록보다 뒤인지 확인한 뒤에만
"켜졌다"고 말한다.

## 후속 T8 — ERP 휴지통 잠금 (사용자 결정 2026-09-02)

착수 시점에는 범위 밖으로 뒀으나 사용자가 이어서 고치기로 했다.

- **결정**: 단계 제한을 없앤다. 접수 이후 단계는 **관리자가 사유 문장을 적어야** 접힌다.
  재결제 짝이 있어도 접을 수 있다(짝은 표시 정보일 뿐 잠금이 아니었다).
- **안 바뀐 것**: 네이버가 취소를 **확정한 건만** 접는다. 확정 전에 접으면 취소가
  거부됐을 때 살아 있어야 할 주문이 휴지통에 있다. 이건 돈의 문제라 유지한다.
- `can_discard = claim_phase == "done"` 로 바꾸고 `discard_needs_reason` 을 새로 낸다.
  `DISCARDABLE_STATUSES` 는 "사유 없이 바로" 목록으로 의미가 바뀌었다(값은 그대로).
- 라우트가 사유 없는 접수 이후 단계를 400, MANAGER 를 403 으로 막는다. 화면 버튼의
  `data-needs-reason` 과 같은 조건이다 — 한쪽만 좁히면 열린 버튼이 400 을 받는다.
- 사유 원문과 단계는 soft delete 사유와 감사 원장 양쪽에 남는다.
- 계약 테스트 4종 추가·2종 수정(`test_naver_ghost_orders.py` 13종 green).

## 미해결

- **실호출 0회.** 2026-09-01 운영 스냅샷은 승인 대상 0건(없음 185 / `RETURN_DONE` 25 /
  `CANCEL_DONE` 18)이라 스테이징에서도 눈으로 볼 것이 없다. 거부 때와 같은 자리다.
- ~~ERP 휴지통 축~~ — 2026-09-02 해소(위 후속 T8).
- `FULFILLMENT_ACTION_LABELS` 폴백이 `"confirm"` 인 것 자체(`naver_ingest.py:534-535`)는
  그대로 뒀다 — 화면 문구 회귀 범위가 넓다. 별건.
