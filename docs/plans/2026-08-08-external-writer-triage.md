# EXTERNAL mutation writer 22곳 트리아지 (C3-a, 2026-08-08)

상위 계획: `docs/plans/2026-08-08-audit-carryover-plan.md` §C3.
대상 인벤토리: `docs/harness/foms_order_mutation_writer_inventory.json`
(`baselines.external = 22`, 기준 커밋 `origin/deploy` = `3c5f54dd`).

## 판정 기준

인벤토리 생성기(`tools/harness/order_mutation_writer_scan.py`)의 분류는 **경로 단위**다 —
allowlist 에 없는 파일의 모든 write 사이트가 일괄 `EXTERNAL` 이 된다. 그래서 "이 사이트가
정말 미보호인가"는 사이트가 아니라 **호출자의 트랜잭션 문맥**을 봐야 알 수 있다.

| 판정 | 뜻 | 조치 |
|---|---|---|
| **A** | 진짜 미보호 — 라우트가 lock/version/If-Match 없이 직접 쓴다 | `execute_order_mutation` 전환(C3-c) |
| **B** | canonical 트랜잭션 **내부** helper — 호출자가 이미 `execute_order_mutation`/`transition_order` 로 row lock + version bump 를 잡았다 | 분류 오류 → allowlist 등재(C3-b) |
| **C** | 오프라인 배치 — 드리프트 지문·run token 하네스를 거친다 | `AUDITED_RECOVERY` 재분류(C3-b) |
| **D** | 사문 — 프로덕션 호출자 0 | 제거 또는 배선 결정 필요 |

## 판정표 (22/22)

### A — 진짜 미보호 mutation (17곳)

| # | 사이트 | 함수 | 근거 |
|---|---|---|---|
| 1 | `foms/api/cs/confirm.py:65` | `api_customer_confirm` | POST 라우트, `first()` 후 직접 write → commit. lock·version 없음 |
| 2 | `foms/api/cs/dashboard.py:348` | `api_settlement_issue` | 정산 차감 항목 append. 동시 2건이면 한쪽 유실(lost update) |
| 3 | `foms/api/cs/dashboard.py:434` | `api_cash_receipt_issue` | "이미 발행" 409 검사가 read-then-write TOCTOU — lock 없으면 이중 발행 가능 |
| 4 | `foms/api/drawing/erp_orders_draftsman.py:106` | `api_orders_batch_assign_draftsman` | 일괄 지정, 다건 write 무lock |
| 5 | `foms/api/drawing/erp_orders_draftsman.py:244` | `api_order_assign_draftsman` | 단건 담당자 지정 |
| 6 | `foms/api/drawing/erp_orders_draftsman.py:390` | `api_order_confirm_drawing_receipt` | `order.status` 까지 직접 전이 |
| 7 | `foms/api/drawing/erp_orders_revision.py:118` | `api_order_request_revision` | `drawing_transfer_history` append |
| 8 | `foms/api/drawing/erp_orders_revision.py:332` | `api_order_cancel_revision_request` | 같은 이력 배열 수정 |
| 9 | `foms/api/drawing/erp_orders_revision.py:477` | `api_order_request_revision_check` | 같은 이력 배열 수정 |
| 10 | `foms/api/events.py:418` | `api_compensate_change_event` | 보상 트랜잭션이 직접 sd 되돌림 |
| 11 | `foms/api/orders/field_update.py:576` | `update_order_field_response` | 같은 함수의 `apply_canonical_main_stage`(:365)는 **status 분기 전용** — 이 사이트는 비-status 필드 legacy 경로다 |
| 12 | `foms/api/orders/status.py:216` | `_sync_erp_stage` | 호출자(:273·:487)가 `should_canonicalize_main_status` 가 거짓일 때 타는 **의도적 legacy 분기**(물류/AS/overlay). 전환하려면 canonical 을 overlay 타깃까지 확장해야 한다 |
| 13 | `foms/api/quest.py:417` | `api_order_quest_approve` | quest 승인 bookkeeping 직접 write |
| 14 | `foms/api/wdcalculator/blueprint.py:1174` | `_clear_wdc_estimate_meta_link` | 호출자(:1209·:1221)가 라우트이고 `except Exception: log` 로 감싼다 — 실패가 조용히 삼켜진다 |
| 15 | `foms/services/notifications/drawing_order_change.py:1019` | `ack_drawing_order_change` | 호출자 `erp_orders_revision.py:514` 라우트, lock 없음. 이력 배열 동시 ack 유실 가능 |
| 16 | `foms/web/orders/edit.py:257` | `edit_order` | legacy 폼 POST. `order_geocode` helper 를 무lock 문맥에서 부르는 유일한 호출자이기도 하다 |
| 17 | `foms/services/orders/blueprint_projection.py:137` | `_write_current` | **호출자별로 갈린다**(아래 주 참조) |

> **17번은 경로 단위 재분류가 불가능하다.** `_write_current` 의 호출자는 세 종류다:
> * `set_current_blueprint`(:220) ← `foms/api/erp_orders_blueprint.py:150` 라우트 — **무lock(A)**
> * `clear_current_blueprint`(:257) ← `erp_orders_blueprint.py:204` `_mutate` 내부 — **B**
> * `apply_blueprint_backfill`(:381)·`remove_backfill_projection`(:426) — **C**
>
> 따라서 고칠 자리는 helper 가 아니라 **`erp_orders_blueprint.py:150` 라우트**다.
> 이 파일을 allowlist 에 넣으면 A 경로까지 함께 면제되므로 넣지 않는다.

### B — canonical 트랜잭션 내부 helper (3곳)

| # | 사이트 | 근거 |
|---|---|---|
| 18 | `foms/services/order_geocode.py:87` | 호출자 4곳 중 3곳(`erp_map.py:793`·`erp_orders_structured.py:1074`·`measurement/routes.py:245`)이 모두 `execute_order_mutation` 의 `_mutate` 콜러블 **내부**다 — FOR UPDATE + version bump 아래. 나머지 1곳(`web/orders/edit.py`)은 위 16번으로 별도 계수 |
| 19 | `foms/api/cs/complete.py:147` | 호출자 `:204` 가 `transition_order`(→ `execute_order_mutation`) **직후 같은 트랜잭션**에서 부수효과를 쓴다. row lock 이 commit 까지 유지되고 version 은 이미 bump 됐다 |
| 20 | `foms/services/orders/quest_transition_service.py:142` | `_append_next_stage_quest` 는 `transition_order(...)` 반환 직후(:227) 같은 tx 에서 호출된다 |

### C — 오프라인 배치 (1곳)

| # | 사이트 | 근거 |
|---|---|---|
| 21 | `foms/services/orders/backfill_order_quests.py:145` | `_apply_batch_write` 는 `runs.write_batch(...)`(:219)에 `batch_business_write=` 로 주입된다. 기대/실측 fingerprint 비교 + run token + checkpoint 하네스를 거치므로 생성기 정의상 `AUDITED_RECOVERY`(OPS-APPROVAL offline apply)다 |

### D — 사문 (1곳)

| # | 사이트 | 근거 |
|---|---|---|
| 22 | `foms/services/orders/quest_transition_service.py:294` | `complete_confirm_quest` 의 프로덕션 호출자가 **0** 이다. 저장소 전체에서 참조는 자기 모듈 docstring·`__all__`·`tests/domains/test_state_quest.py:217` 뿐이다. docstring 은 "호출자(STATE-DRAWING-01 `CUSTOMER_CONFIRM`) 소유"라고 적혀 있는데 그 호출자가 존재하지 않는다 — 배선이 빠졌거나 설계가 바뀐 뒤 남은 것이다 |

## 집계

| 판정 | 곳 |
|---|---|
| A (전환 대상) | 17 |
| B (분류 오류) | 3 |
| C (재분류) | 1 |
| D (사문) | 1 |
| **계** | **22** |

## C3-b 로 실제로 낮출 수 있는 수

생성기 분류가 **경로 단위**이므로 allowlist 등재는 그 파일의 **모든** 사이트를 면제한다.
그래서 안전하게 등재할 수 있는 것은 "그 파일의 EXTERNAL 사이트가 전부 B/C 인 경우"뿐이다:

| 파일 | 사이트 | 등재 분류 | 가능? |
|---|---|---|---|
| `foms/services/order_geocode.py` | 18번 1곳 | `CANONICAL` | 가능 |
| `foms/api/cs/complete.py` | 19번 1곳 | `CANONICAL` | 가능 |
| `foms/services/orders/backfill_order_quests.py` | 21번 1곳 | `AUDITED_RECOVERY` | 가능 |
| `foms/services/orders/quest_transition_service.py` | 20번(B) + 22번(D) | — | **불가** — 사문(22번) 처리 결정 전까지 보류 |
| `foms/services/orders/blueprint_projection.py` | 17번(혼재) | — | **불가** — A 경로가 섞여 있다 |

→ **EXTERNAL 22 → 19**. 나머지 2건은 각각 "사문 제거 결정"과 "라우트 쪽 수정"이 선행 조건이다.

## C3-c 권장 순서 (별건 승인 대상)

위험이 낮고 표면이 좁은 것부터:

1. `EVENT-REVERT-01`(10번, 1곳) — 이미 보상 트랜잭션 문맥이라 의미가 가장 가깝다
2. `WDC-LINK-01`(14번, 1곳) — 실패가 삼켜지는 구조부터 드러내야 한다
3. `BLUEPRINT-01`(17번) — 고칠 자리는 `erp_orders_blueprint.py:150` 라우트
4. `STATE-CONST-CS-01`(1·2·3번) — 이중 발행 TOCTOU 가 있는 3번이 실질 우선순위
5. `DRAWING-REVISION-BACKFILL-00`(7·8·9번) — 같은 이력 배열 3라우트, 한 묶음
6. `STATE-DRAWING-01`(4·5·6·15번)
7. `STATE-QUEST-01`(13·20번) / `ORDER-CREATE-01`(16번)
8. `STATE-LEGACY-01`(11·12번) — canonical 을 overlay 타깃까지 확장해야 해서 가장 크다

각 패킷은 If-Match 계약(409/428)이 생기므로 **프론트 호출부 동반 수정**이 필요할 수 있다.
