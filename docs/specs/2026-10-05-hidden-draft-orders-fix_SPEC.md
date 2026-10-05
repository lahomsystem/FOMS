# 숨은 초안 주문 고치기 SPEC (초안 표식 규칙 · 휴지통 복원 · 운영 7건 정리)

- 작성: 2026-10-05 · 상태: **승인 대기 (설계만 — 코드·데이터 변경 없음)**
- 등급: 코어 변경(API·상태 전이·운영 데이터) → Spec → 승인 → 구현. 운영 데이터 정리는 **별도 명시 승인**.
- 기준 코드: `origin/deploy` `8fdd26372`. 아래 경로는 `origin/production` `73718aee0` 와 내용이 같다(`git diff` 0줄).
- 선행 문서
  - 원인 조사: `docs/plans/2026-10-05-hidden-draft-flag-orders-investigation.md` (이하 "조사서")
  - 초안 술어 성능: `docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md` 결정 2·3, 승인 단계 A-4
- 운영 읽기 R1~R9: 사용자 승인으로 메인 세션이 2026-10-05 에 1회 실행했다(시각은 UTC). 이 설계서는 그 결과만 옮겨 적는다.
- 이 설계서를 쓰는 동안 한 일: 스테이징 DB 를 **읽기 전용**으로 3번 읽었다(§5.1 중복 점검 시범, 필수값 점검 시범, 첨부 수). 주문 번호·상태·참거짓·건수만 골랐고 이름·전화·주소는 출력하지 않았다. 운영 DB 에는 접속하지 않았다.

## 0. 먼저 결론

1. **원인은 확정됐다.** 5078 은 "새 주문 화면에서 버린 초안을 휴지통에서 복원"해서 숨었다(§1). 나머지 6건은 2026-08-03 에 고친 자동저장 경합이 고치기 전에 남긴 행이다. 그 경합은 지금 닫혀 있다(R6=0). 단계 쓰기로 생긴 것은 없다(R7=0).
2. **규칙 하나를 세운다:** "`meta.draft` 가 참인 ERP 주문의 status 는 DRAFT 또는 DELETED 뿐이다." 초안을 실제 주문으로 바꾸는 길은 명시 저장(승격) 하나만 남긴다(§2).
3. **휴지통 복원은 (가) "초안으로 되돌리고, 바로 그 초안의 편집 화면으로 보낸다"를 추천한다(§3).** 직원 38 이 00:22 에 원한 것은 "방금 쓰던 주문을 되찾아 마저 등록하기"다. 편집 화면에서 저장을 누르면 기존 승격 경로(필수값 검사·`ORDER_CREATED`·실측 자동 전진·알림톡 자격 판정)가 그대로 돈다. 승격 경로를 하나 더 만들지 않는다. 복원 기록에는 주문 번호를 남긴다.
4. **안전장치 두 개(§4):** 단계를 쓰는 5개 길이 초안이면 409 로 거절한다. 그리고 규칙을 어긴 행 수를 매일 밤 읽기만 해서 세고, 0 이 아니면 실패로 남긴다.
5. **운영 7건은 되살리기 전에 중복부터 본다(§5).** 스테이징(운영 07-14 무렵 사본)에서 시범으로 돌려 보니, 같은 번호의 숨은 4건 모두 **같은 고객 주문이 몇 분~하루 뒤에 다시 입력돼 있었다**(4237→4252, 4266→4267, 4301→4303, 4308→4309). 직원이 주문이 사라진 것을 보고 다시 넣은 것이다. 되살리면 중복 주문이 생긴다. 그래서 기본안은 "중복이 있으면 휴지통으로(초안 상태로), 없으면 편집 화면 저장으로 되살리기"다. 주문마다 사용자가 정한다.

## 1. 확정된 원인 (운영 읽기 결과)

| 읽기 | 결과 | 뜻 |
|---|---|---|
| R1 | 7건 모두 `meta.draft='true'`, `created_via=ADD_ORDER_AUTOSAVE`, `finalized_at` 없음, `mutation_version=1`, `structured_updated_at = autosaved_at`, `erp_stage_code = status`(MEASURE 또는 RECEIVED), 강제 변경 표식 없음, 삭제 메타 없음. 대조군 4608 은 표식 거짓·`finalized_at` 있음 | 마지막으로 쓴 쪽은 자동저장이고, 승격은 한 번도 안 됐다. 4608 은 누군가 편집 화면에서 저장해 정상 승격된 선례다 |
| R2 | 5078: `ORDER_DRAFT_CREATED` 2026-09-01 00:16:56(직원 38), `ATTACHMENT_ADDED` 2건 00:18. `ORDER_CREATED` 없음. 나머지 6건은 이벤트 없음(이벤트 표는 08-05 부터) | 5078 은 초안인 채로 끝났다 |
| R3 | 5078: `FILE_UPLOADED` 2건 00:18 만 | 저장·상태 변경 기록 없음 |
| R4 | 휴지통 복원 "주문 1개 복원"(직원 38): 08-20 00:10:59, **09-01 00:22:46**, 09-02 07:22:34, 10-01 06:04:40 | 5078 을 만든 같은 직원이 6분 뒤 1건을 복원했다 |
| R6 | 0행 | 승격된 주문의 표식이 되살아난 일 없음 — 자동저장 경합은 닫혀 있다 |
| R7 | 0행 | 초안에 걸린 단계 쓰기 없음 |
| R8 | 휴지통의 표식 참 행: original_status 없음 20 · DRAFT 15 · RECEIVED 14 · AS_RECEIVED 2 · DELETED 1 | 지금 복원하면 34건 이상이 또 숨는다(아래) |
| R9 | 최근 30일 실측 알림톡 자동 발송 0건 | 자동 발송은 꺼져 있는 것으로 보인다(정리 직전에 다시 확인, §5.4) |

5078 의 순서: 새 주문 화면 진입(초안 생성 00:16:56) → 사진 2장 첨부(00:18) → 화면을 다시 열자 "저장하지 않은 작성 내용이 있습니다 [이어쓰기][버리기]" 띠가 떴고 "버리기"를 눌렀다(`static/js/orders/erp-order-autosave.js:521-540` → `foms/api/erp_orders_structured.py:2428`). 버리기는 `status='DELETED'` 만 쓰고 `original_status` 를 비워 두며 이벤트·감사 기록을 남기지 않는다(`:2442-2445`). → 00:22:46 휴지통에서 복원. 복원은 `status = original_status or "RECEIVED"` 로 바꾸고 표식은 보지 않는다(`foms/web/orders/trash.py:349-351`). → status RECEIVED + 표식 참 = 모든 화면에서 빠진다(`models.py:224-244`). 이 복원 갈래는 이벤트도 버전 증가도 남기지 않아 R2 에 흔적이 없다.

R8 을 지금 복원하면: 없음 20 + RECEIVED 14 → RECEIVED + 표식 참(숨음), AS_RECEIVED 2 → 숨음, DELETED 1 → `status='DELETED'`·`deleted_at` 없음(휴지통에도 화면에도 없는 다른 유령), DRAFT 15 → DRAFT(초안으로 남지만 아무도 이어 쓸 수 없고 다음 밤 정리 크론이 다시 지운다).

## 2. 규칙 — "표식이 참이면 status 는 DRAFT 또는 DELETED"

- 대상: `is_erp_order` 인 모든 행(휴지통 포함). 판정 도우미는 이미 있다: `foms/services/erp_order_flags.py:27` `is_erp_order_draft()`, `:19` `is_erp_draft_structured_data()`.
- 표식이 참인 행이 실제 주문이 되는 길은 **승격 함수 하나**다: `foms/api/erp_orders_structured.py:965` `_finalize_draft_state`(표식 끔·`finalized_at`·status 를 `workflow.stage` 로·평면 칸·`ORDER_CREATED` 1건). 이 함수를 부르는 곳은 명시 저장 PUT(`:1624`)과 AS 접수(`foms/api/cs/as_orders.py:574-576`)뿐이고, 둘 다 그대로 둔다.
- 그 밖의 status 쓰기는 초안을 만나면 (1) 거절하거나(§4.1) (2) DRAFT 로 쓴다(휴지통 복원, §3).
- 지금 데이터로 본 규칙 위반: 운영 7건(살아 있는 행). 스테이징은 4건이고, 휴지통 안의 표식 참 행 35건은 모두 `status='DELETED'` 라 위반이 없다(이번 읽기 [실측]).

## 3. 휴지통 복원 고치기

### 3.1 지금 동작

`foms/web/orders/trash.py:323-364` `restore_orders()`:

- `status == 'DELETED'` 인 행(옛 일괄 삭제·정리 크론·새 주문 "버리기")은 `status = original_status or "RECEIVED"`, `original_status=None`, `deleted_at=None` (`:344-351`). 이벤트·버전 증가 없음.
- 그 밖의 행은 정본 `restore_order`(`foms/services/orders/soft_delete.py:273`)로 삭제 축만 푼다. status 는 그대로다.
- 두 갈래 모두 표식을 보지 않는다. 감사 행은 "주문 N개 복원" 한 줄이고 주문 번호가 없다(`:359`).
- 휴지통 목록은 "원래 상태" 칸에 `original_status` 를 보여 줘서, 버린 초안은 "알 수 없음"으로 나온다(`templates/orders/trash.html:135`). 직원은 그 행이 작성 중 초안이었는지 알 수 없다.

### 3.2 세 가지 안

| | (가) 초안으로 되돌리기 + 편집 화면으로 | (나) 복원 = 정식 승격 | (다) 초안은 복원 목록에서 빼기 |
|---|---|---|---|
| 하는 일 | status 를 DRAFT 로, 표식 유지, 정리 크론 시계를 다시 시작, 그 초안의 편집 화면(`/edit/<id>`)으로 보낸다. 저장을 누르면 기존 승격 | 복원하면서 필수값 검사 → 통과하면 승격(표식 끔·`ORDER_CREATED`), 실패하면 복원 거절 | 휴지통에서 초안을 복원할 수 없게 한다 |
| 직원 38 이 원한 것과 | **맞다.** 쓰던 내용과 사진을 그대로 다시 보고, 빠진 칸을 채워 저장하면 주문이 된다 | 필수값이 다 있으면 맞지만, 쓰던 도중이라 빠진 칸이 있으면 **되찾을 길이 없다.** 다 있어도 직원이 보지 못한 채 주문이 생긴다 | **틀리다.** 되찾으려던 내용을 잃는다 |
| 새 승격 경로 | 없음(저장 PUT 그대로) | 휴지통 안에 두 번째 승격 경로가 생긴다. PUT 이 커밋 뒤 하는 일(실측 자동 전진 `:1783-1800`, 대시보드 캐시, 도면·생산 알림, 위치 변환, 알림톡 `:1833`)을 다시 짜 맞추거나 빠뜨린다 | 없음 |
| 규칙(§2) | 지킨다 | 지킨다 | 지킨다 |
| 크기 | 작음(복원 갈래 + 이동 + 문구) | 큼 | 가장 작음 |

**"초안으로만 되돌리기"는 그것만으로는 답이 아니다.** 초안 이어쓰기는 세션에 묶여 있다 — 서버는 `session['erp_draft_order_id']` 또는 그 페이지가 만든 토큰으로만 초안을 찾고(`foms/api/erp_orders_structured.py:2092-2115`), 토큰은 페이지를 열 때마다 새로 만들며(`static/js/orders/erp-order-shared.js:601-613`), 버리기는 세션 번호를 지운다(`:2447`). "내 초안 목록" 같은 화면도 없다. 그래서 status 만 DRAFT 로 바꾸면 아무도 그 초안에 닿을 수 없고, 정리 크론이 `structured_updated_at` 기준 48시간이 지난 초안을 다음 밤에 다시 휴지통으로 보낸다(`tools/cron/cleanup_order_drafts.py:144-147`). (가) 는 그래서 **편집 화면으로 보내기**와 **크론 시계 다시 시작**을 한 묶음으로 한다. 초안의 편집 화면은 이미 쓰는 길이다 — 새 주문 화면의 "편집 화면 열기" 단추가 초안 번호로 `/edit/<id>` 를 연다(`templates/orders/partials/erp_order_tab.html:49-58`, `static/js/orders/erp-order-shared.js:616-627`). 편집 화면은 삭제 여부만 보고 연다(`foms/web/orders/edit.py:247`). 4608 이 이 길로 승격된 운영 선례다(R1).

### 3.3 추천: (가)

- 직원 38 은 버린 지 몇 분 만에 복원했다. "주문을 다시 보고 싶다"는 뜻이고, 그 주문은 아직 저장(등록)한 적이 없는 작성 중 주문이었다. (가) 는 그 사람을 정확히 "저장 직전"으로 돌려보낸다. 저장 버튼 하나로 정식 주문이 되고, 필수값이 비어 있으면 평소처럼 "필수 항목을 입력해주세요"가 뜬다(`:1474-1480`).
- 승격 판단(필수값·단계·알림톡 자격)이 저장 PUT 한 곳에만 남는다. 휴지통이 두 번째 승격 경로가 되지 않는다.
- 저장하지 않고 떠나면 초안은 초안으로 남고(화면에는 안 보인다 — 초안이 원래 그렇다), 48시간 뒤 크론이 휴지통으로 되돌린다. 복원 안내 문구가 이것을 말해 준다. 숨은 주문은 생기지 않는다.

### 3.4 설계 (승인 후 구현)

1. **새 서비스 함수** `restore_trashed_draft(session, *, order_id, actor_user_id, now=None)` — 새 모듈 `foms/services/orders/draft_lifecycle.py`(가칭). `soft_delete.py` 는 "status 를 절대 쓰지 않는다"가 계약이라(`foms/services/orders/soft_delete.py:13`) 거기에 넣지 않는다.
   - 정본 `restore_order(session, order_id=…, actor_user_id=…, reason='초안으로 복원')` 로 삭제 축을 푼다 → `ORDER_RESTORED` 이벤트·버전 증가·영수증이 정본 경로로 남는다(지금 옛 갈래는 셋 다 없다).
   - 같은 트랜잭션·같은 행 잠금 아래에서: `status='DRAFT'`, `original_status=None`, 표식이 없던 행(`original_status='DRAFT'` 만 있는 옛 행)은 `copy.deepcopy` → `meta['draft']=True` → 재대입 → `flag_modified`, 그리고 `structured_updated_at = now` (크론 48시간 다시 시작).
   - 고객 데이터·`workflow`·첨부는 건드리지 않는다. 승격하지 않는다.
2. **`restore_orders()` 갈래 순서 바꾸기** (`foms/web/orders/trash.py:343-355`): 먼저 "초안 행인가"를 본다 — `is_erp_order_record(order)` 이고 (`is_erp_draft_structured_data(sd)` 또는 `original_status == 'DRAFT'` 또는 `status == 'DRAFT'`). 맞으면 1번 함수. **두 갈래(status DELETED 옛 행·정본 삭제 행) 모두에 적용한다** — 정본 삭제로 status 를 보존한 채 휴지통에 들어간 초안도 같은 함수를 지나야 한다(§5 정리에서 휴지통으로 보내는 행이 이 경우다). 초안이 아니면 지금과 똑같다.
3. **복원 뒤 이동:** 복원한 것이 초안 1건뿐이면 `/edit/<id>` 로 보낸다. 안내: "작성 중이던 초안이라 초안으로 되살렸습니다. 빠진 칸을 채우고 '저장'을 누르면 주문으로 등록됩니다. 저장하지 않으면 48시간 뒤 다시 휴지통으로 갑니다." 여러 건이면 휴지통에 머물고, 초안 번호마다 편집 화면 링크를 안내에 싣는다.
4. **휴지통 목록 표시:** 초안 행은 "원래 상태" 칸에 "작성 중 초안"으로 보인다(`templates/orders/trash.html:135`, 판정은 2번과 같은 술어를 표시 행에 미리 계산해 싣는다 — `foms/web/orders/trash.py:94` `_build_trash_display_orders`). 인라인 스타일은 쓰지 않는다.
5. **새 주문 화면 "버리기" 보강** (`foms/api/erp_orders_structured.py:2441-2446`): `original_status='DRAFT'` 를 함께 쓴다(정리 크론 `tools/cron/cleanup_order_drafts.py:163` 과 같은 모양). 그리고 같은 트랜잭션에 `ORDER_DRAFT_DISCARDED` 이벤트 1건(주체·`via='erp_draft'`). 이번 조사에서 버린 시각을 알 수 없었던 빈칸을 메운다.
6. **복원 기록에 주문 번호** (`foms/web/orders/trash.py:359`): 주문마다 `log_access(…, action='ORDER_RESTORED', target_type='order', target_id=<id>, detail={'as_draft': 참거짓, 'from_status': …, 'to_status': …, 'original_status': …})` 를 남긴다(`:266-276` 삭제 기록과 같은 모양). 요약 줄 "주문 N개 복원"은 문구를 그대로 두고(옛 조회 R4 와 호환) `detail` 에 `order_ids`·`draft_order_ids` 를 더한다. 감사 문장에 고객 이름은 넣지 않는다.
7. 표시 이름: `foms/services/order_event_display.py:231-232` 옆에 `ORDER_DRAFT_DISCARDED` "임시 주문 버림", `ORDER_RESTORED` "휴지통에서 복원"(지금 이름 없음)을 더한다.

## 4. 안전장치

### 4.1 단계 쓰기는 초안을 거절한다 (409)

공통 예외: `foms/services/orders/order_transition_service.py:60` 의 `TransitionError` 계열에 `DraftNotPromotedError` 를 하나 더 둔다 — `status_code=409`, `error_code='DRAFT_NOT_PROMOTED'`, 문구 "아직 저장(등록)하지 않은 초안입니다. 먼저 주문을 저장한 뒤 단계를 바꿀 수 있습니다." 상태 쓰기 쪽은 이미 `TransitionError` 를 `status_code` 로 응답에 옮긴다(`foms/api/orders/status.py:173`, `foms/api/quest.py:310`). 판정은 `is_erp_order_draft()` 하나만 쓴다.

| # | 경로 | 넣을 곳 | 동작 |
|---|---|---|---|
| 1 | 정본 전이 `transition_order` | `foms/services/orders/order_transition_service.py:391-395` (잠근 행의 상태 읽기 바로 다음) | 초안이면 `DraftNotPromotedError`. 일반 상태 변경·퀘스트 승인·PUT 뒤 실측 자동 전진이 모두 지난다. 자동 전진은 승격 커밋 뒤라 걸리지 않는다 |
| 2 | 단계 강제 변경(단건) | `foms/api/orders/stage_override.py:116-118` 삭제 검사 바로 다음(AS·삭제·완료 목표로 가르기 전) + 백스톱 `foms/services/orders/stage_override.py:368` 앞 | 409. 라우트의 `except ValueError → 400`(`:178-181`) 앞에 이 예외를 409 로 받는 갈래를 둔다(`ValueError` 를 상속하지 않으므로 섞이지 않는다) |
| 2b | 단계 강제 변경(일괄) | `foms/api/orders/stage_override.py:431` `found_map` 에서 삭제 행처럼 초안을 빼고 응답에 `skipped_draft` 번호 목록 | 일괄 전체를 깨지 않는다. 잠금 아래 백스톱(2번)이 터지면 일괄 전체 409 |
| 3 | 일반 상태 변경 `update_order_status`(단건) | `foms/api/orders/status.py:326-328` 주문 조회 직후 | 409. 이 주문은 초안이라 `should_canonicalize_main_status` 가 거짓이 되어 옛 갈래 `order.status = new_status`(`:417`)로 떨어지던 것이 조사서 재현의 원인이다 |
| 3b | 일반 상태 변경(일괄) | `foms/api/orders/status.py:614` 반복 첫머리 | `blocked_unpromoted_draft` 목록에 넣고 건너뛴다(같은 파일의 `blocked_command_required` 와 같은 모양, `:590`·`:704-726`) |
| 4 | 칸 수정 `update_order_field` 의 `field='status'` | `foms/api/orders/field_update.py:611` 갈래 첫머리 | 409. **조사서 표에 없던 길이다** — 같은 `setattr(order, 'status', …)` 로 숨은 모양을 만들 수 있다 |
| 5 | 퀘스트 승인 | `foms/api/quest.py:333` 행 잠금 직후 | 409. 전이 전에 퀘스트 승인 기록부터 초안 sd 에 쓰므로 1번 백스톱만으로는 늦다 |

- **관리자 뚫기(admin override)로도 못 뚫는다.** 초안은 업무 게이트가 아니라 "아직 주문이 아님"이다. 뚫는 길은 저장(승격)뿐이다.
- 초안은 목록에 안 나오므로 화면에서 이 409 를 볼 일은 거의 없다. 새 주문 화면의 단계 강제 변경은 이미 클라이언트가 막는다(`static/js/orders/erp-stage-override.js:226-229`).
- 하지 않는 것: 자동저장·버리기·명시 저장·AS 접수(승격 경로)·칸 수정의 status 외 칸(초안 작성 중 날짜 등)은 그대로다.

### 4.2 감시 — 규칙을 어긴 행을 매일 밤 센다 (읽기만, 고치지 않음)

- 새 도구 `tools/ops/check_draft_flag_invariant.py`(가칭). Flask 앱을 띄우지 않고(`tools/cron/cleanup_order_drafts.py` 머리말과 같은 이유) 읽기 전용 트랜잭션(`default_transaction_read_only=on`)으로 한 번 센다.
- 조건(부분 인덱스 `ix_orders_meta_draft_true` 와 같은 글자라 그 작은 인덱스만 읽는다, `models.py:25-26`·`:188-208`):

  ```sql
  SELECT o.id, o.status, (o.deleted_at IS NOT NULL) AS trashed, o.created_at::date AS created_day
  FROM orders o
  WHERE o.is_erp_order IS TRUE
    AND o.status NOT IN ('DRAFT', 'DELETED')
    AND o.id IN (SELECT d.id FROM orders d
                 WHERE CAST((d.structured_data #>> '{meta, draft}') AS BOOLEAN) IS true)
  ORDER BY o.id;
  ```

- 출력은 번호·상태·휴지통 여부·만든 날짜만. 0건이면 종료 코드 0, 1건 이상이면 3(다른 실패와 구별).
- `tools/cron/nightly.py:46` `NIGHTLY_STEPS` 에 `cleanup_order_drafts` 다음 단계로 넣는다. 밤 실행 요약 줄에 단계별 결과가 따로 찍히므로(`:80-85`) 다른 정리와 섞이지 않는다.
- 스테이징 [실측]: 같은 뜻의 조건으로 4건(4237 MEASURE · 4266 MEASURE · 4301 RECEIVED · 4308 MEASURE).
- 운영에는 §5 정리를 마친 뒤 켠다. 먼저 켜면 매일 밤 7건으로 실패한다(그 자체가 알림이긴 하다 — 결정 3).
- 자동으로 고치지 않는다. 원인을 가리는 땜질이 되기 때문이다.

## 5. 운영 7건 정리 계획 — **별도 명시 승인 필요(A-4)**

대상: 4237 · 4266 · 4301 · 4308 · 4409 · 4600 (경합 잔재) · 5078 (휴지통 복원).

### 5.1 새로 생각할 점 — 직원이 이미 다시 입력했을 수 있다

이 주문들은 만든 직원 눈앞에서 사라졌다. 직원은 같은 고객을 새 주문으로 다시 넣었을 가능성이 높다. 그 상태에서 숨은 쪽을 되살리면 같은 고객 주문이 둘이 된다(실측·도면·생산이 두 갈래로 돈다).

스테이징 시범 [실측] — 아래 §5.2 D1 과 같은 SQL 을 스테이징의 같은 번호 4건에 돌렸다. 4237·4266·4301·4308 은 운영 사본 시점(07-14 무렵) 이전에 만든 주문이라, 짝으로 나온 주문도 운영에 같은 번호로 있다.

| 숨은 주문 | 같은 고객 주문(일치 축) | 그 주문 상태 | 숨은 쪽 마지막 자동저장 뒤 | 첨부 수(숨은 쪽 / 짝) |
|---|---|---|---|---|
| 4237 | 4252 (전화·이름·주소) | DRAWING | 약 23시간 뒤 | 0 / 2 |
| 4266 | 4267 (전화·이름·주소) | MEASURE | 2.8분 뒤 | 0 / 1 |
| 4301 | 4303 (전화·이름·주소), 4235 (전화·이름, 주소 다름) | 4303 휴지통 · 4235 MEASURE(4일 먼저 만듦) | 4303 은 12.1분 뒤 | 0 / 0 · 6 |
| 4308 | 4309 (전화·이름·주소) | AS_COMPLETED | 0.9분 뒤 | 0 / 2 |

(4237 은 오래전 완료 주문 3877 과 전화·이름도 맞는다 — 재주문 고객이다. 이런 짝은 중복이 아니므로 "만든 시각"과 상태로 가른다.)

네 건 모두 다시 입력한 주문이 그 뒤 실제로 진행됐다. 운영에서도 같을 가능성이 매우 높다. 4409·4600·5078 은 운영에서만 확인할 수 있다.

### 5.2 1단계: 운영 읽기 (읽기만 · 사용자 승인 1회 · 고객 정보 출력 금지)

모든 SQL 은 이름·전화·주소를 **비교만** 하고 결과에는 번호·상태·참거짓·날짜 차이만 고른다. 연결은 읽기 전용으로 연다.

```sql
-- D1. 같은 고객 주문 찾기 (전화 숫자 일치, 또는 이름+주소 일치). 스테이징에서 0.16초.
WITH keyed AS (
  SELECT o.id, o.status, o.created_at, o.deleted_at,
         (o.is_erp_order IS TRUE AND (o.status = 'DRAFT'
            OR (o.structured_data #>> '{meta,draft}') = 'true')) AS is_draft,
         NULLIF(regexp_replace(COALESCE(o.structured_data #>> '{parties,customer,phone}', o.phone, ''),
                               '[^0-9]', '', 'g'), '') AS phone_d,
         NULLIF(lower(regexp_replace(COALESCE(o.structured_data #>> '{parties,customer,name}', o.customer_name, ''),
                                     '\s', '', 'g')), '') AS name_n,
         NULLIF(regexp_replace(COALESCE(NULLIF(o.structured_data #>> '{site,address_main}', ''),
                                        NULLIF(o.structured_data #>> '{site,address_full}', ''),
                                        o.address, ''),
                               '[^0-9A-Za-z가-힣]', '', 'g'), '') AS addr_n
  FROM orders o
),
clean AS (   -- 자리표시자(000-0000-0000, 'ERP Order', '-')는 비교에서 뺀다
  SELECT k.id, k.status, k.created_at, k.deleted_at, k.is_draft,
         CASE WHEN length(k.phone_d) >= 9 AND k.phone_d !~ '^0+$' THEN k.phone_d END AS phone_d,
         CASE WHEN k.name_n <> 'erporder' THEN k.name_n END AS name_n,
         CASE WHEN length(k.addr_n) >= 8 THEN k.addr_n END AS addr_n
  FROM keyed k
),
hidden AS (SELECT * FROM clean WHERE id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078))
SELECT h.id AS hidden_id, c.id AS other_id, c.status AS other_status,
       c.is_draft AS other_is_draft, (c.deleted_at IS NOT NULL) AS other_trashed,
       (c.created_at > h.created_at) AS other_newer,
       (c.created_at::date - h.created_at::date) AS day_gap,
       (h.phone_d IS NOT NULL AND c.phone_d = h.phone_d) AS phone_match,
       (h.name_n IS NOT NULL AND c.name_n = h.name_n) AS name_match,
       (h.addr_n IS NOT NULL AND c.addr_n IS NOT NULL
        AND (starts_with(c.addr_n, h.addr_n) OR starts_with(h.addr_n, c.addr_n))) AS addr_match
FROM hidden h
JOIN clean c ON c.id <> h.id
WHERE (h.phone_d IS NOT NULL AND c.phone_d = h.phone_d)
   OR (h.name_n IS NOT NULL AND c.name_n = h.name_n
       AND h.addr_n IS NOT NULL AND c.addr_n IS NOT NULL
       AND (starts_with(c.addr_n, h.addr_n) OR starts_with(h.addr_n, c.addr_n)))
ORDER BY h.id, c.created_at;

-- D2. 5078 복원 직후 직원 38 이 만든 주문(번호·종류·시각만)
SELECT e.order_id, e.event_type, e.created_at, o.status, (o.deleted_at IS NOT NULL) AS trashed
FROM order_events e JOIN orders o ON o.id = e.order_id
WHERE e.created_by_user_id = 38
  AND e.event_type IN ('ORDER_DRAFT_CREATED', 'ORDER_CREATED')
  AND e.created_at BETWEEN '2026-09-01 00:00' AND '2026-09-01 03:00'
ORDER BY e.created_at;

-- D3. 되살릴 때 저장이 통과할지(필수값)·실측 자동 전진·알림톡 자격에 쓸 값 (참거짓만)
--     필수값 판정은 foms/api/erp_orders_structured.py:168 과 같은 뜻이다.
SELECT o.id, o.status, o.structured_data #>> '{workflow,stage}' AS wf_stage,
       COALESCE(btrim(o.structured_data #>> '{parties,customer,name}'), '') NOT IN ('', 'ERP Order') AS has_name,
       COALESCE(btrim(o.structured_data #>> '{parties,customer,phone}'), '') NOT IN ('', '000-0000-0000') AS has_phone,
       COALESCE(NULLIF(btrim(o.structured_data #>> '{site,address_full}'), ''),
                NULLIF(btrim(o.structured_data #>> '{site,address_main}'), ''), '-') <> '-' AS has_address,
       COALESCE(NULLIF(btrim(o.structured_data #>> '{items,0,product_name}'), ''),
                NULLIF(btrim(o.structured_data #>> '{items,0,name}'), ''), 'ERP Order') <> 'ERP Order' AS has_product,
       NULLIF(btrim(o.structured_data #>> '{schedule,measurement,date}'), '') IS NOT NULL AS has_measure_date,
       CASE WHEN NULLIF(btrim(o.structured_data #>> '{schedule,measurement,date}'), '') IS NOT NULL
            THEN left(btrim(o.structured_data #>> '{schedule,measurement,date}'), 10)
                 < to_char(now() AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD') END AS measure_date_past
FROM orders o
WHERE o.id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078)
ORDER BY o.id;

-- D4. 첨부 수 (숨은 7건 + D1 이 찾은 짝 번호)
SELECT o.id, count(a.id) AS attachments
FROM orders o LEFT JOIN order_attachments a ON a.order_id = o.id
WHERE o.id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078 /* + D1 의 other_id */)
GROUP BY o.id ORDER BY o.id;
```

주의: R1 의 `has_measure_date` 는 빈 글자도 "있음"으로 셌다. 스테이징 4301·4308 은 실측일 칸이 빈 글자였다 [실측]. D3 은 빈 글자를 뺀다. 실측 자동 전진과 알림톡 자격은 D3 값으로 판단한다.

### 5.3 2단계: 주문마다 정하기 (사용자 결정)

| D1·D3 결과 | 추천 | 이유 |
|---|---|---|
| 뒤에 만든 같은 고객 주문이 살아 있다(휴지통 아님) | **휴지통으로(초안 상태로)** | 되살리면 중복. 직원은 이미 새 주문으로 일하고 있다 |
| 같은 고객 주문이 휴지통에만 있다(예: 4301 의 4303) 또는 먼저 만든 다른 현장 주문만 있다 | **담당 직원에게 묻기** — 기본은 휴지통 | 일부러 지운 주문일 수 있다. 사람만 안다 |
| 같은 고객 주문이 없고 필수값이 다 있다 | **되살리기**(편집 화면 저장) | 실제로 진행돼야 했던 주문이 빠져 있을 수 있다. 되살린 뒤 담당 직원에게 알린다 |
| 같은 고객 주문이 없는데 필수값이 비었다 | 담당 직원과 내용 확인 뒤 채워서 저장, 또는 휴지통 | 저장은 400 으로 막힌다(`:1474-1480`) |
| 그대로 두기 | **잠깐만** 허용(직원 확인을 기다릴 때) | §4.2 감시가 매일 이 행을 센다. 오래 두지 않는다 |

첨부: 숨은 쪽에만 첨부가 있고(D4, 예: 5078 의 사진 2장) 휴지통으로 보낼 때는, 보내기 **전에** 직원이 숨은 쪽 편집 화면(`/edit/<id>` — 숨은 주문도 열린다)에서 사진을 받아 새 주문에 다시 올릴지 정한다. 휴지통으로 간 뒤에도 행과 첨부는 남는다(물리 삭제는 보존 기간 정책만 한다, `foms/web/orders/trash.py:367-369`).

### 5.4 3단계: 실행 직전 점검 (그날 다시)

1. **실측 알림톡 자동 발송 스위치.** R9 는 0건이었지만 실행 직전에 다시 본다. 운영 Railway 4개 서비스(web · WORKER · FOMS-cron · SIDEFX)의 변수 중 `FOMS_ALIMTALK_AUTO_ENABLED` 하나만 읽는다(다른 값은 출력하지 않는다). 생산자 게이트는 web 이다(`foms/services/kakao_alimtalk.py:1086`, 호출은 저장 PUT `foms/api/erp_orders_structured.py:1833` 과 칸 수정 `foms/api/orders/field_update.py:936-938`). 운영 기록상 web 은 꺼져 있다(`docs/runbooks/sidefx-worker-ops.md:22-24`). R9 같은 조건의 outbox 건수도 다시 센다.
   - 켜져 있으면: 실측일이 있는(D3 `has_measure_date`) 주문은 **되살리기를 멈추고 사용자에게 묻는다.** 자격 판정은 지난 날짜를 거르지 않는다(`:143-157`, `:524-549`) — 7월·9월 실측 안내가 지금 고객에게 나간다. 표식을 끄는 순간 초안 판정(`:499-503`)이 풀리기 때문이다.
2. **실측 자동 전진.** 되살릴 주문이 RECEIVED 이고 실측일이 있으면(D3), 저장 직후 MEASURE 로 한 칸 간다(`foms/api/erp_orders_structured.py:1783-1800`, `:404-444`). 원래 저장했을 때 일어났을 일이라 맞는 결과다. 실측일이 지났으면 실측 화면에 "지난 실측"으로 보일 수 있다 — 담당 직원에게 미리 알린다.
3. **스냅샷.** 실행 직전 7건의 번호·status·original_status·deleted_at·`mutation_version`·`erp_stage_code`·`structured_data->'meta'`·`structured_data->'workflow'` 를 로컬 JSON 으로 남긴다(고객 정보 없음, 세션 scratchpad).

### 5.5 4단계: 실행

- **되살리기 = 편집 화면 저장 1번.** 사람(사용자 또는 담당 직원)이 `/edit/<id>` 를 열고, 내용을 확인하고, "저장"을 누른다. 정식 경로가 그대로 돈다: 행 잠금·버전·영수증(`execute_order_mutation`) → 승격(`_finalize_draft_state`: 표식 끔·`finalized_at`·status·평면 칸·`ORDER_CREATED`) → `ORDER_STRUCTURED_SAVED` 감사 + 변경 원장 → 실측 자동 전진 → 대시보드 캐시 무효화 → 알림톡 자격 판정. Claude 는 운영 실데이터를 저장하지 않는다(운영 측정 계정은 측정만, `docs/guides/REAL_SERVER_TEST_ACCOUNT.md`).
- **휴지통으로 = 정리 도구 1개** `tools/ops/repair_hidden_draft_orders.py`(가칭, 이번 코드 묶음에 포함). 숨은 주문은 일반 삭제 단추로 지울 수 없다(`foms/web/orders/trash.py:219` 가 `active_filter` 로 찾아 "찾을 수 없음"이 된다).
  - 기본은 미리보기(쓰기 없음). `--execute --ids <번호들> --actor-user-id <id> --reason "<사유>"` 를 줄 때만 쓴다. 번호는 명시한 것만, 한 번에 7건 이하.
  - 주문마다 한 트랜잭션: 잠근 행이 살아 있는(`deleted_at` 없음) §4.2 모양(표식 참·status 가 DRAFT/DELETED 아님)인지 다시 확인 — **아니면 거절하고 아무것도 안 쓴다.** 맞으면 `status='DRAFT'` 로 맞춘 뒤 정본 `soft_delete_order(reason=…)`(`foms/services/orders/soft_delete.py:234`)로 휴지통에 넣는다(`ORDER_SOFT_DELETED` 이벤트·버전·영수증). 감사 `log_access(action='ORDER_DRAFT_FLAG_REPAIRED', target_type='order', target_id=…, detail={'action': 'trash', 'duplicate_of': <짝 번호 또는 None>})`. 커밋 뒤 대시보드 캐시 무효화.
  - 결과로 휴지통에는 "status DRAFT + 표식 참" 행이 남는다. 나중에 누가 복원하면 §3 수정으로 **초안**으로 돌아오고 편집 화면이 열린다 — 다시 숨지 않는다.
  - 출력은 번호·상태·버전만.
- **그대로 두기:** 아무것도 하지 않는다. 결정 기록만 남긴다.

### 5.6 확인과 되돌리기

확인(읽기만):

- §4.2 감시 SQL → 0건(그대로 두기로 한 번호만 남음).
- 휴지통으로 보낸 번호: `deleted_at` 있음, status DRAFT, 표식 참, `ORDER_SOFT_DELETED` 1건(사유 포함), 감사 `ORDER_DRAFT_FLAG_REPAIRED` 1건.
- 되살린 번호: 표식 거짓, `finalized_at` 있음, status = `workflow.stage`(또는 자동 전진한 MEASURE), `ORDER_CREATED` 정확히 1건, `ORDER_STRUCTURED_SAVED` 1건.
- R9 조건 + `dedupe_key LIKE 'alimtalk:measure:<번호>:%'` 로 이 번호들의 새 알림톡 outbox 행이 없음.
- 화면 확인은 사용자가 주문 번호로 검색해서 한다(운영 측정 계정은 요청 1건당 1회).

되돌리기(정리 자체가 문제를 만들었을 때만):

- 휴지통으로 보낸 것: 휴지통에서 복원 → 초안으로 돌아와 편집 화면이 열린다 → 저장하면 되살리기. 숨은 상태로 되돌리지는 않는다(그게 고치려던 문제다).
- 되살린 것: 3번 스냅샷으로 status·`meta.draft`·`meta.finalized_at` 만 `jsonb_set` 으로 되돌리고 그 `ORDER_CREATED` 를 번호로 지운다(조사서 §7(c) 와 같다). `structured_data` 전체를 되돌리지 않는다 — 그 뒤 사람이 고친 내용이 날아간다. 되살린 주문으로 이미 일이 진행됐으면 되돌리지 말고 휴지통 도구를 쓴다.

## 6. 시험 (음성 대조군 포함)

모두 지금 코드에서는 **실패해야 한다**(조사서 §4 재현 값이 실패 값이다). PR 설명에 수정 전 실패·수정 후 통과를 함께 적는다.

### 6.1 휴지통 복원 — 새 파일 `tests/domains/test_trash_restore_draft.py`(가칭)

| 시험 | 준비 → 행동 | 기대 |
|---|---|---|
| 버린 초안 복원 | 자동저장 초안 → 버리기 → 복원 | `('DRAFT', 표식 참)`, `deleted_at` 없음, `original_status` 없음, `active_filter` 0건 **그리고** `erp_draft_filter` 1건, 응답 302 의 위치 `/edit/<id>`, `ORDER_RESTORED` 1건, 감사 행 `target_id=<id>`·`as_draft=True`, 크론 미리보기(`run_erp_draft_orders(execute=False)`)가 이 행을 세지 않음 |
| 복원한 초안 저장 | 위 다음 필수값 넣어 PUT | 표식 거짓, status = `workflow.stage`, `active_filter` 1건, `ORDER_CREATED` 정확히 1건 |
| 크론이 지운 초안 | `status='DELETED'`, `original_status='DRAFT'` → 복원 | 첫 시험과 같음 |
| 정본 삭제된 표식 참 행 | status MEASURE·표식 참·`deleted_at` 있음(§5.5 결과 모양 대신 정본 삭제만 한 행) → 복원 | status DRAFT(MEASURE 아님) — 두 번째 갈래도 막혔다는 증거 |
| original_status 가 DELETED 인 초안 | → 복원 | status DRAFT (지금은 `status='DELETED'`·`deleted_at` 없음 유령) |
| **음성 대조군 1** 일반 주문 옛 갈래 | 표식 없음, `status='DELETED'`, `original_status='MEASURE'` → 복원 | MEASURE, `active_filter` 1건, `ORDER_CREATED` 추가 없음, 휴지통 화면으로 돌아감 |
| **음성 대조군 2** 일반 주문 정본 갈래 | 정본 삭제된 DRAWING 주문 → 복원 | DRAWING 그대로, 화면에 보임 |
| 섞어서 복원 | 초안 1 + 일반 1 | 휴지통에 머묾, 안내에 초안 편집 링크, 일반 주문은 보임, 요약 감사 `order_ids` 2개·`draft_order_ids` 1개 |
| 버리기 기록 | 버리기 | `original_status='DRAFT'`, `ORDER_DRAFT_DISCARDED` 1건 |
| 휴지통 목록 표시 | 버린 초안 1 + 일반 1 | 초안 행만 "작성 중 초안" |

### 6.2 단계 쓰기 거절 — 새 파일 `tests/domains/test_erp_draft_flag_invariant.py`(가칭)

| 시험 | 기대 (초안) | **음성 대조군** (같은 내용을 PUT 으로 승격한 주문) |
|---|---|---|
| 단계 강제 변경 단건 | 409 `DRAFT_NOT_PROMOTED`, DB `('DRAFT', 참)` 그대로, `STAGE_OVERRIDE` 이벤트 없음 | 200, 단계 바뀜 |
| 단계 강제 변경 일괄 [초안, 승격 주문] | 승격 주문만 바뀜, 응답 `skipped_draft=[초안]` | — |
| 단계 강제 변경 AS·완료 목표 | 409 (갈래 전에 막힘) | 기존 동작 |
| `update_order_status` 단건 | 409, `('DRAFT', 참)` | 200 |
| `update_order_status` 단건 + 관리자 뚫기 | 409 (뚫기 무시) | — |
| `bulk_update_order_status` | `blocked_unpromoted_draft=[초안]`, 다른 주문은 바뀜 | — |
| `update_order_field` `field='status'` | 409 | 200 |
| `update_order_field` `field='notes'` (초안) | 지금처럼 200 — 거절 범위가 status 만이라는 대조군 | — |
| 퀘스트 승인 | 409, 퀘스트 승인 기록 안 생김 | 기존 동작 |
| `transition_order` 직접 호출 | `DraftNotPromotedError` | 성공 |
| 규칙 훑기 | 위 쓰기를 차례로 부른 뒤 매번 "표식 참이면 status 는 DRAFT·DELETED" 위반 0 | — |

### 6.3 감시·정리 도구

- 감시: 숨은 모양 1행 + 대조군(정상 초안 · 승격 주문 · 휴지통 초안 · 정본 삭제된 초안 DRAFT) → 정확히 1건, 종료 코드 3. 대조군만 있으면 0건·종료 코드 0. 출력에 시험용 고객 이름 글자가 **없음**을 단언. `NIGHTLY_STEPS` 에 단계가 들어 있음을 단언(`tools/cron/nightly.py` 계약 시험 옆).
- 정리 도구: 미리보기는 아무것도 안 씀(버전·이벤트 수 불변). 실행하면 휴지통 모양(§5.6). **대조군:** 숨은 모양이 아닌 번호(정상 주문·정상 초안)를 주면 거절하고 그 행은 그대로. 출력에 고객 이름 없음.
- 선택(PG 레인 `tests/postgres/`): 두 연결로 "승격 PUT 이 잠근 동안 단계 강제 변경이 기다렸다가, 승격 커밋 뒤에는 통과" — 잠금 아래 판정이라는 증거.

### 6.4 검증 명령

```bash
python -m pytest tests/domains/test_trash_restore_draft.py tests/domains/test_erp_draft_flag_invariant.py \
  tests/domains/test_delete_trash.py tests/domains/test_erp_add_order_autosave.py \
  tests/domains/test_erp_draft_order_events.py tests/domains/test_admin_override_status_routes.py -q
python -m pytest tests/harness -q -x -n auto
python -c "import app; print('APP_OK')"
powershell -File scripts/ops/pre_push_smoke.ps1   # push 직전, exit 0 확인
```

## 7. 반영 순서

1. 이 설계 승인(§8 결정 1~3).
2. 코드 묶음 1개: 휴지통 복원(§3) · 버리기 보강 · 단계 쓰기 거절(§4.1) · 감시 도구(§4.2, 운영 nightly 등록은 7번까지 보류할지 결정 3) · 정리 도구(§5.5) · 시험(§6). → `deploy` 푸시 → CI green.
3. **스테이징 리허설 — 숨은 4건(4237·4266·4301·4308)으로 먼저.**
   - 스테이징 web 의 `FOMS_ALIMTALK_AUTO_ENABLED` 부터 본다. 스테이징 데이터에는 실제 고객 전화가 들어 있다. 켜져 있으면 실측일 있는 행의 되살리기 리허설은 하지 않는다.
   - D1~D4 를 스테이징에 돌린다(§5.1 이 이미 한 번 돈 결과).
   - 4237·4266·4308: 정리 도구 미리보기 → 실행(휴지통). 감시 → 1건(4301)만 남는지.
   - 4301: 되살리기 리허설(스테이징 한정 — 운영 4301 의 결정과는 무관하다). 짝 4303 이 휴지통이고 실측일이 비어 있어 알림톡 자격도 자동 전진도 없다 [실측]. `claude_master` 로 `/edit/4301` 을 열어 저장 → 표식 거짓·RECEIVED·`ORDER_CREATED` 1건, 대시보드·검색에 보이는지, outbox 행이 없는지 본다. (스테이징은 측정 계정 자유 사용 범위다.)
   - 휴지통 목록에서 4237·4266·4308 이 "작성 중 초안"으로 보이는지만 본다(실제 고객 행은 복원하지 않는다).
   - 복원 → 편집 화면 넘김은 **가상 주문**으로 본다: `claude_master` 로 새 주문 화면에서 `CLAUDE-TEST-` 이름·직원 본인 번호로 초안을 만들고 → 띠의 "버리기" → 휴지통에서 복원 → `/edit/<id>` 로 넘어가는지, 대시보드에는 안 나오는지 → 저장 → 정상 주문으로 보이는지 → 평소처럼 삭제.
   - 감시 → 0건.
4. 운영 읽기 D1~D4 + 알림톡 스위치 확인(사용자 승인 1회).
5. 사용자가 주문마다 결정(§5.3).
6. production 승격(사용자 명시 요청 — 이 세션 커밋만 cherry-pick + PR).
7. 운영 정리 실행(**별도 명시 승인**): 그날 §5.4 점검 → 스냅샷 → 휴지통 대상은 도구로, 되살리기 대상은 사람이 편집 화면 저장 → §5.6 확인 → 감시를 운영 nightly 에 켬.
8. 마친 뒤에만: 초안 술어 성능 설계서 결정 3(status 하나로 초안 판정)을 다시 볼 수 있다. 이번 범위 밖이다.

## 8. 사용자가 정할 것

1. **휴지통 복원 방식** — (가) 초안으로 되돌리고 그 초안의 편집 화면으로 보내기 **(추천)** / (나) 복원 = 정식 승격 / (다) 초안은 복원 금지.
2. **단계 쓰기 거절 범위** — §4.1 의 5개 길 모두, 관리자 뚫기로도 못 뚫게 **(추천)**.
3. **감시 방법** — 매일 밤 단계로 세고 0 이 아니면 실패로 남기기 **(추천)**. 운영에는 정리를 마친 뒤 켤지(추천), 바로 켜서 7건이 매일 실패로 보이게 할지.
4. **운영 읽기 D1~D4 + 알림톡 스위치 확인** 승인(읽기만, 1회).
5. **주문 7건 각각** — 되살리기 / 휴지통(초안 상태로) / 잠깐 그대로. 기본 추천: 뒤에 만든 같은 고객 주문이 살아 있으면 휴지통(스테이징 기준 4237·4266·4308 이 여기에 해당할 가능성이 높다), 4301 처럼 짝이 휴지통이면 담당 직원에게 묻기, 짝이 없고 필수값이 있으면 되살리기.
6. **되살리기 저장을 누를 사람** — 사용자 본인 또는 담당 직원(Claude 는 운영 실데이터를 저장하지 않는다). 5078 은 직원 38 이 하는 것이 자연스럽다(쓰던 사람·사진 2장).
7. **운영 정리 실행 승인**(A-4, 별도 명시).

## 9. 범위

- 바뀌는 파일(승인 후): `foms/web/orders/trash.py`, `templates/orders/trash.html`, `foms/api/erp_orders_structured.py`(버리기만), 새 `foms/services/orders/draft_lifecycle.py`, `foms/services/orders/order_transition_service.py`, `foms/services/orders/stage_override.py`, `foms/api/orders/stage_override.py`, `foms/api/orders/status.py`, `foms/api/orders/field_update.py`, `foms/api/quest.py`, `foms/services/order_event_display.py`, 새 `tools/ops/check_draft_flag_invariant.py`, 새 `tools/ops/repair_hidden_draft_orders.py`, `tools/cron/nightly.py`, 새 시험 2~3개. 마이그레이션 없음.
- 하지 않는 것: 자동저장·승격 PUT·AS 접수 판정 변경, 초안 술어(`models.py:224`) 변경, 휴지통의 지운 초안 52건 정리(지운 상태라 맞다 — 복원해도 이제 숨지 않는다), `_finalize_draft_state` 를 서비스로 옮기기(조사서 (a)-1, 이번에는 휴지통이 승격하지 않으므로 필요 없다 — 따로 정리 후보).
- 이 설계서 밖 발견: 칸 수정 `update_order_field` 의 status 쓰기(§4.1 4번)는 조사서 표에 없던 경로다. 같은 규칙 안으로 넣었다.
