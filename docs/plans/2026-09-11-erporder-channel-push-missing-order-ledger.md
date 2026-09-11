# 원장 — ERP 채널톡 푸시 후 주문 미저장 건 판정 (2026-09-11)

브리프: `docs/plans/2026-09-11-erporder-channel-push-missing-order-brief.md`
조사: 멀티 에이전트 워크플로 9명(CEO 설계 → 워커 4 병렬 → 통합 → 적대적 리뷰 2 → CEO 판정), 약 107만 토큰·42분.
검증: 아래 "총괄 직접 재확인" 항목은 총괄이 운영 DB 읽기 전용으로 직접 재조회했다.

## 판정

**주문은 사라진 것이 아니라 만들어진 적이 없다.** 초안 단계 채널톡 실측 푸시는 설계상 `Order` 를
만들지 않으며(`foms/api/erp_order_draft_send.py:1-15` 설계 D1), 그 뒤 등록(`/api/erp/order-draft/submit`)
요청이 서버에 도달하지 않았다. 확신도 매우 높음.

## 총괄 직접 재확인한 증거 (운영 DB, readonly)

| 확인 | 결과 |
|---|---|
| `order_drafts.id=355` | 생존. user_id 53, order_id NULL, step 4, key `new.ff7475d50b3a42ac`, created 2026-09-10 01:34:50 UTC, expires 2026-09-17 01:40:59 UTC |
| `send_history` | `channeltalk_push_measure_room: {pushed:true, sent_at:2026-09-10T01:40:55.444651, group_id:229923, message_id:6aa20aa758391459d556}` |
| `security_logs` 해당 draft_key | 1행뿐 — id=37443 `CHANNEL_PUSH_DRAFT_SENT` (sent=true, error=null, files_count=2) |
| `ORDER_DRAFT_SUBMITTED` 해당 key | **0건(전 기간)** |
| message_id 로 orders 전수(삭제 포함) | **0건** |
| 이광일 orders 전수 | 5253(`ERP Order`/DRAFT/`created_via=ADD_ORDER_AUTOSAVE`, 껍데기), 5255(`이광일`/MEASURE, 2026-09-10 23:02:26 UTC = KST 09-11 08:02, 다음날 재입력분) |
| 푸시 감사행 총계 | 54건. 등록으로 이어지지 않은 것 **3건**: 9/2 user 38(`new.921841fe…`), 9/3 user 21(`new.e05ce29b…`), 9/10 user 53(이번 건) |

코드 재확인: `static/js/foms/wizard.js:1176-1185` 등록 클릭 핸들러는 `.then` 만 있고 `.catch` 가 없다.
대조 `static/js/foms/wizard-send.js:388-391` 은 발송 실패 시 "네트워크 오류" 를 띄운다.

## 워커/리뷰어가 세운 배제

- 서버 오류: 사건 배포(8422569c) KST 10:30~11:09 전 2,902줄 — 5xx 0, Traceback 0, `WORKER TIMEOUT`/`SIGKILL` 0,
  API 302 0. 음성 대조군으로 배포 시작 시 워커 기동 줄 2벌(복제본 2개)이 같은 조회에 보인다.
- 하루 전수: 9/10 운영 web 배포 8개를 배포 ID 지정해 훑어 `order-draft/submit` 접속 10줄 = DB
  `ORDER_DRAFT_SUBMITTED` 10행 = 생성 주문 10건 (1:1 일치 → 로그가 새지 않았다는 증거). 이번 키는 그 10건에 없다.
- 크론 삭제: `tools/cron/cleanup_order_drafts.py:21` `ERP_DRAFT_STALE_HOURS=48`(변수 미설정). 사건은 15.4시간 — 대상 불가.
  그날 밤 삭제분은 orders 5195(한울디자인)로 무관.

## 남은 불확실성 (원리상 관측 불가)

"등록을 눌렀는데 휴대폰에서 요청이 안 나갔다"는 어떤 표에도 흔적이 없다. `static/js` 전체에
`window.onerror`/`unhandledrejection` 0건, RUM 은 성능 payload 전용(`foms/api/foms_rum.py`).
따라서 (a)안 눌렀다 / (b)눌렀지만 무음 실패 는 서버 증거로 가를 수 없다. 다만 (b)를 지지하는 증거는 0이다.

## 브리프 정정 (다음 조사용)

- `channel_delivery_logs` 는 **죽은 표다**. 마지막 행 2026-06-18, 생성자 호출 0건,
  `foms/services/channel_delivery.py:127` 이 폐기를 명시. 실제 감사 원장은 `security_logs`(컬럼은 `detail`, `details` 아님).
- 초안 TTL 은 키 접두사별로 다르다: `new.*` 7일, `edit.*` 24시간(`foms/services/order_draft_service.py:70-75`).
- 중간 보고의 "429 377건" 은 오탐이었다(캐시 키 문자열 `key_suffix=429f…`). 재집계 결과 429 는 0건.
- `railway logs` 함정: `-S/-U` 만 주면 500줄에서 잘리고 구간 뒤쪽만 나온다. 과거 구간은 그때 살아 있던 배포 ID 를 넘겨야 한다.

## 후속 제안 (미착수, 코드 변경 없음)

1. 푸시만 하고 이탈하는 것을 막는 안전장치 — 발송 완료 문구를 "아직 주문 등록 전입니다"로 바꾸고,
   발송 이력이 있는데 등록 없이 닫기를 누르면 확인창.
   `static/js/foms/wizard-send.js:371-377`, `static/js/foms/wizard.js:1205-1213`
2. 등록 버튼 무음 실패 제거 — `submitOrder()` 호출에 `.catch` 추가, 클릭 즉시 버튼 잠금 + "등록 중" 표시.
   `static/js/foms/wizard.js:1176-1185`, `static/js/foms/draft.js:284-296`
3. 살아 있는 초안 목록 노출 — 초안 목록 API 가 없어(`foms/api/erp_order_draft.py:263-547`) 화면을 떠나면
   사용자가 스스로 찾을 길이 없다. 진입 링크 `/add?key=<draft_key>&wizard=1` 은 이미 지원
   (`foms/web/orders/listing.py:502-506`).

## 별건 (이번 원인 아님, 실재하는 구멍)

`log_access` 가 예외를 삼키면서 호출자 트랜잭션 전체를 `db.rollback()` 한다
(`foms/web/auth/routes.py:97-116`). submit 은 그 직후 `erp_order_draft.py:677` 에서 commit 하고
200 + order_id 를 돌려준다 → 감사 한 줄 실패가 주문 생성을 통째로 되감으면서 화면엔 성공으로 보인다.
9/10 운영 로그에 `[LOG ERROR] SecurityLog 기록 실패` 는 0건이라 이번 건의 원인은 아니다.

## 후속 처리 결과 (2026-09-11)

제안 1·2 를 구현해 운영까지 반영했다. 제안 3(초안 목록 화면)은 미착수다.

| 단계 | 결과 |
|---|---|
| 작업 트리 | `/c/tmp/wizpend` (`origin/deploy` 기준) — 메인 체크아웃 로컬 `deploy` 는 44 ahead·189 behind 로 영구 분기 상태라 거기서 푸시하지 않았다 |
| 커밋 | `188516ecc` 본체(7 files, +363 −14) · `315dc780c` 후속 수정 |
| deploy CI | `315dc780c` ALL GREEN |
| 승격 | PR #349 (`promote/own-1789087471-6012` → production), 검사 4종 pass 후 머지 |
| production | `708b15efd` → `02eee54489` |

### 구현 내용

1. 발송 성공 시 상태 문구를 "발송 완료 — 아직 주문 등록 전입니다"로 바꾸고 등록 버튼에
   `is-pending-submit` 을 걸어 강조한다. 두 파일이 별개 IIFE 라 `window.FomsWizardHasPendingSend`
   로 상태를 공유한다(`static/js/foms/wizard-send.js`).
2. 그 상태로 닫기(X)를 누르면 확인창이 막는다(`static/js/foms/wizard.js` 닫기 핸들러).
3. 등록 실패를 무음에서 꺼냈다 — `submitOrderWithFeedback()` 이 `.catch` 로 통신 실패까지
   알리고, 누르는 즉시 버튼을 잠그고 "등록 중…"을 띄운 뒤 실패하면 되돌린다.
4. 회귀 계약 7건(`tests/domains/test_wizard_pending_submit_guard.py`).

### 이번에 얻은 함정

- **JS 를 고쳤으면 `node --check` 를 바로 걸어라.** 첫 푸시가 CI red 였다 — 패치 스크립트에서
  `\n` 이 실제 줄바꿈으로 들어가 문자열 리터럴이 끊겼는데(`Invalid or unexpected token`),
  `pre_push_smoke.ps1` 의 32개 타깃에 `tests/domains/test_static_js_syntax.py` 가 **없어서**
  로컬 smoke 는 green 이었다. 로컬에 node 가 있으니 그 테스트를 직접 지정해 돌리면 잡힌다.
- **승격 완전성 검사의 "missing baseline deps" 는 오탐일 수 있다.** 이번 `d774ff77` 은 내용이
  이미 운영에 있었고(건드리는 파일 4개가 `origin/production` 과 바이트 동일) 승격 때
  cherry-pick 으로 SHA 가 재작성돼 검사기가 못 찾은 것이다. 판정은 커밋 SHA 가 아니라
  **파일 내용 대조**로 한다. 우회(`--allow-incomplete`)는 사용자 승인 뒤에만.
