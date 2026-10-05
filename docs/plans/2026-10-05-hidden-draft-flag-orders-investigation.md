# 초안 표식이 남아 어디에도 안 보이는 주문 — 원인 조사 (2026-10-05)

- 범위: 조사만 했다. 코드·데이터는 고치지 않았다. 운영 DB 에는 접속하지 않았다.
- 작업 위치: worktree `c:\tmp\foms-s-perf-hidden` (branch `session/perf-hidden`, origin/deploy 기준).
- 스테이징은 읽기 전용 연결로만 봤다. 고객 이름·전화는 읽지도 적지도 않았다(번호·상태·시각·이벤트 종류만).
- 관련 설계서: `docs/specs/2026-10-05-perf-db-draft-flag-and-stats_SPEC.md` §1.3·§4.

## 0. 결론 먼저

1. **운영 7건 중 6건(4237·4266·4301·4308·4409·4600)은 2026-08-03 에 고친 "초안 부활 레이스"가 고치기 전에 남긴 행이다.** 고친 커밋(`106df4c11`)은 레이스만 막았고 이미 생긴 행은 정리하지 않았다. 스테이징에 같은 번호로 남아 있는 4건의 기록이 그 레이스의 지문과 정확히 맞는다(§5). 확신도: 4건은 높음, 4409·4600 은 날짜상 같은 원인으로 보지만 운영 읽기로 확인이 필요하다(중상).
2. **자동저장 ↔ 승격 레이스 자체는 지금 코드에서 닫혀 있다.** 자동저장이 승격 PUT 과 같은 행 잠금을 잡고, 잠금 뒤 최신 값을 다시 읽고, 이미 승격됐으면 아무것도 쓰지 않는다(§3). 이 수정은 2026-08-03 16:01 에 운영에 들어갔고 그 뒤로 지워진 적이 없다.
3. **9월 1일에 만든 5078 을 설명하는 가장 유력한 길은 "휴지통 복원"이다.** 새 주문 화면의 "버리기"로 지운 초안은 `status='DELETED'`, `original_status` 없음으로 남는다. 휴지통에서 이것을 복원하면 `status` 는 `'RECEIVED'` 가 되고 `meta.draft=true` 는 그대로라, 복원한 주문이 곧바로 모든 화면에서 사라진다. 로컬에서 그대로 재현됐다(§4). 5078 의 상태가 RECEIVED 인 것과도 맞는다. 확신도: 중간 — 운영 읽기(§6)로 확정해야 한다.
4. 그 밖에 **단계 쓰기 경로 3곳이 초안을 거르지 않는다**(단계 강제 변경, 일반 상태 변경, 퀘스트 승인). 서버에 바로 부르면 같은 숨은 모양이 생긴다(재현됨). 다만 새 주문 화면은 강제 변경을 클라이언트에서 막고(주문번호 0), 그 뒤 자동저장이 status 를 DRAFT 로 되돌리므로 실제로 생겼을 가능성은 낮다. 그래도 같은 규칙으로 막아야 한다.
5. 정리 크론은 `status='DRAFT'` 인 행만 지우므로(`tools/cron/cleanup_order_drafts.py:144-146`), 숨은 모양의 행은 아무도 모른 채 영원히 남는다. 5주 동안 아무도 몰랐던 이유다.

## 1. 숨는 원리

- `models.py:184` `Order.erp_draft_predicate()` = ERP 주문이면서 `status == 'DRAFT'` **또는** `structured_data.meta.draft` 가 참.
- `models.py:201` `active_filter()` 와 `:207` `active_including_trashed_filter()` 가 이것을 NOT 으로 감싼다. 운영 화면 전부가 이 필터를 쓴다.
- 그래서 `status` 가 MEASURE·RECEIVED 같은 실제 단계여도 `meta.draft=true` 가 남으면 그 주문은 대시보드·검색·목록 어디에도 나오지 않는다. 편집 화면 주소(`/orders/<id>/edit`)로 직접 들어가면 열린다(`foms/web/orders/edit.py:247` 은 삭제 여부만 본다).
- 판정 도우미 `foms/services/erp_order_flags.py:27` `is_erp_order_draft()` 도 같은 두 갈래를 본다.

## 2. `meta.draft` 를 켜고·끄고·옮기는 모든 경로

`grep` 으로 `meta.draft`·`['draft']`·`"draft":`·`status = ...` 쓰기와 raw SQL 을 전부 훑었다. "숨은 모양"은 `meta.draft=true` 이면서 `status` 가 DRAFT 도 DELETED 도 아닌 살아 있는 행을 뜻한다.

| # | 경로 | 위치 | 하는 일 | 숨은 모양을 만들 수 있나 |
|---|---|---|---|---|
| 1 | 새 주문 초안 만들기 `POST /api/orders/erp/draft` | `foms/api/erp_orders_structured.py:1969`, 표식 `:1999` | `status='DRAFT'` + `meta.draft=true` 로 만든다 | 아니오(둘이 함께 켜진다) |
| 2 | 자동저장이 초안 만들기 | `:2118` `_create_session_draft`, 표식 `:2137` | 1번과 같다 | 아니오 |
| 3 | 자동저장 쓰기 `POST /api/orders/erp/draft/autosave` | `:2301`, 표식 `:2358`, status `:2369` | 화면이 보낸 sd 를 통째로 쓰고 `meta.draft=true`, `status='DRAFT'` 로 맞춘다 | **8-03 전에는 예**(승격 뒤에 늦게 도착하면 표식만 되살리고 status 쓰기는 빠졌다). 지금은 아니오 — §3 |
| 4 | 명시 저장(승격) `PUT /api/orders/<id>/structured` | `:1394`, 승격 `:1624` → `_finalize_draft_state` `:965` (끄기 `:983-984`) | 표식을 끄고 `finalized_at` 을 남기고 `status` 를 단계로 맞추고 `ORDER_CREATED` 1건 | 아니오. 화면이 표식 참을 보내도 여기서 끈다 |
| 5 | AS 접수 | `foms/api/cs/as_orders.py:574-578` | 초안이면 4번과 같은 함수로 먼저 승격 | 아니오 |
| 6 | 초안 버리기 `POST /api/orders/erp/draft/discard` | `:2428`, `:2442-2445` | `status='DELETED'`, `deleted_at` 설정. **`original_status` 는 비워 둔다** | 지운 상태라 그 자체로는 아니오. 하지만 9번의 재료가 된다 |
| 7 | 정리 크론 | `tools/cron/cleanup_order_drafts.py:163-164` | `status='DRAFT'` 인 48시간 지난 행을 `status='DELETED', original_status='DRAFT'` 로. 표식은 그대로 | 아니오(지운 상태). 숨은 모양 행은 대상에서 빠진다 |
| 8 | 단건 소프트 삭제·복구(정본) | `foms/services/orders/soft_delete.py:273` | `status` 를 건드리지 않는다 | 아니오 |
| 9 | **휴지통 복원** `POST /restore_orders` | `foms/web/orders/trash.py:349-351` | `status='DELETED'` 행은 `status = original_status or "RECEIVED"`, `deleted_at=None`. 표식은 안 본다 | **예.** 6번으로 지운 초안을 복원하면 `RECEIVED` + 표식 참. 크론이 지운 초안은 `DRAFT` 로 돌아가 여전히 안 보이고 다음 크론이 다시 지운다 |
| 10 | 단계 강제 변경(단건) `POST /api/orders/<id>/workflow/stage-override` | 라우트 `foms/api/orders/stage_override.py:113`, 쓰기 `foms/services/orders/stage_override.py:368` | `status` 와 `workflow.stage` 만 바꾼다. 초안인지 안 본다 | **예**(서버만 보면). 새 주문 화면에서는 클라이언트가 주문번호 0 으로 막는다(`static/js/orders/erp-stage-override.js:226-229`, `templates/orders/add_order.html:766-767`) |
| 11 | 일반 상태 변경 `POST /api/update_order_status`·일괄 | `foms/api/orders/status.py:326`, `:407-417`, 일괄 `:552` | 정본 전이(`transition_order`) 또는 `order.status = new_status`. 초안 확인 없음 | **예**(서버만 보면). 초안은 목록에 안 나오므로 화면에서 닿기 어렵다 |
| 12 | 퀘스트 승인 `POST /api/orders/<id>/quest/approve` | `foms/api/quest.py:324-333` | 단계 자동 전이. 초안 확인 없음 | 이론상 예. 퀘스트 버튼은 초안이 안 나오는 화면에만 있다 |
| 13 | 인라인 수정 `PATCH .../structured/fields` | `foms/api/erp_orders_structured.py:1102` | 잠근 최신 sd 에 한 칸만 고친다 | 아니오(표식은 있는 그대로 옮겨진다) |
| 14 | 결제 확인 토글 | `:1886` | `active_filter` 로 초안을 거른다 | 아니오 |
| 15 | 주문 복사 | `foms/services/order_copy.py:141` | 새 주문 표식을 거짓으로 | 아니오 |
| 16 | 모바일 마법사 등록·네이버 승격·채널 생성 | `foms/api/erp_order_draft.py:709`, `foms/services/integrations/naver_commerce/promotion.py:222`, `foms/services/security/channel_order/creation.py:129` | `create_order` 로 만든다. 마법사 sd 의 meta 는 `{"wizard_v1": true}` 뿐 | 아니오 |
| 17 | 운영 도구 raw SQL | `tools/ops/bulk_complete_past_construction_core.py:171`(초안 제외), `tools/ops/data_doctor.py:486`·`:578` | status 쓰기. 앞의 것은 초안을 뺀다 | 대상 목록이 초안이 아니면 아니오. 실행 흔적은 `STAGE_OVERRIDE`(mode=restore) 로 남는다 |
| 18 | 마이그레이션 | `migrations/versions/*` | 주문 표식을 쓰는 것 없음 | 아니오 |

읽기만 하는 곳(바꾸지 않음): `foms/services/kakao_alimtalk.py:499`, `foms/services/order_payment_sync.py:159`, `foms/services/order_date_sync.py:346`, `foms/services/notifications/measure_same_day.py:168`, `foms/services/common/dashboard_cache.py:790`.

### 2.1 2026-08-03 ~ 09-01 사이 바뀐 것

`git log --since=2026-08-03 --until=2026-09-02` 로 위 경로를 봤다. 승격·자동저장의 서버 판정을 바꾼 커밋은 없다. 눈여겨본 것만 적는다.

- `846538c79`(08-05): `ORDER_DRAFT_CREATED`·`ORDER_CREATED` 이벤트를 붙였다. 판정은 안 바뀌었다. 덕분에 5078 은 운영에서 생성·승격 기록을 확인할 수 있다.
- `d83854c23`(08-19)·`c4cd6b472`(08-21)·`92f7c9019`(08-24): 알림톡·공유·PUSH 버튼이 "먼저 저장(승격)하고 보낸다". 모두 명시 저장 PUT 을 쓴다(`redirect:false`). 서버 쪽 늦은 자동저장 차단이 그대로 적용된다.
- `6d212ecb9`(08-25): 단계 강제 변경 가드의 기준을 저장된 단계로 바꿨다. 새 주문 화면에서는 여전히 주문번호 0 으로 막힌다.
- 휴지통 복원(`trash.py`)과 버리기(`api_erp_discard_draft`)는 이 기간에 안 바뀌었다(복원 로직은 4월, 버리기는 06-30 `de68c2db9` 부터 그대로). 즉 "버리기 → 복원 = 숨은 주문" 길은 06-30 부터 계속 열려 있었다.

## 3. 자동저장 ↔ 승격 레이스: 지금은 닫혔나

8-03 전 원인(커밋 `106df4c11` 설명): 저장 버튼에서 포커스가 빠질 때 쏜 자동저장이 잠금 없이 초안을 읽어 두고, 승격 PUT 이 커밋한 뒤에 그 옛 상태를 썼다. 이때 `meta.draft=true` 는 다시 쓰였지만 `order.status = 'DRAFT'` 는 세션에 이미 'DRAFT' 로 들고 있던 값과 같아 UPDATE 에서 빠졌다. 그래서 status 는 승격된 값으로, 표식은 참으로 남았다.

지금 코드:

- 자동저장은 대상 행을 `FOR UPDATE` + `populate_existing` 으로 다시 읽는다(`foms/api/erp_orders_structured.py:2043-2064`). 승격 PUT 도 같은 행을 `FOR UPDATE` 로 잡는다(`foms/services/orders/revision.py:346-360`, 잠그기 전에 읽어 둔 깨끗한 객체는 비워서 최신 값으로 다시 채운다).
- 다시 읽은 행이 이미 승격돼 있으면 아무것도 쓰지 않는다(`:2067-2089`, 응답 `skipped='already_promoted'`, `:2325-2333`).
- 세션의 초안 번호가 없을 때 토큰으로 찾는 길도 `status='DRAFT'` 인 행만 찾고, 잠근 뒤 다시 판정한다(`:136-152`, `:2092-2115`). 승격된 행은 절대 고르지 않는다. 최악이면 새 초안 행을 하나 만들 뿐이다(그 행은 status 가 DRAFT 라 숨은 모양이 아니고, 48시간 뒤 크론이 지운다).
- 화면 쪽도 저장 "시작" 순간 자동저장 타이머를 멈춘다(`static/js/orders/erp-order-autosave.js:744-748`). 오프라인 큐로 나중에 다시 보내지는 자동저장(`:353-361`)도 서버의 같은 판정을 거친다.
- 회귀 테스트가 있다: `tests/domains/test_erp_add_order_autosave.py:368` (단, 순서대로 실행하는 테스트이고 두 연결이 겹치는 PG 동시성 테스트는 없다).
- 운영 반영: PR #36 머지 2026-08-03 16:01 (`5e0632821`). `git log origin/production -S'_resolve_draft_for_autosave'` 결과 추가 1건뿐, 지운 적 없음.

판단: 5078(09-01 생성)은 이 레이스로 생겼다고 보기 어렵다. 만약 운영 읽기에서 5078 에 `ORDER_CREATED` 가 있고 그보다 늦은 `meta.autosaved_at` 이 나오면, 이 판단이 틀린 것이므로 레이스를 다시 파야 한다(§6 해석표).

## 4. 로컬 재현 (임시 테스트, 커밋하지 않음)

`tests/domains/` 에 임시 테스트를 만들어 SQLite 테스트 DB 에서 돌리고 바로 지웠다. 결과 표기는 `(status, meta.draft, active_filter 로 보이는 행 수)`.

| 시나리오 | 결과 |
|---|---|
| 자동저장으로 초안 생성 직후 | `('DRAFT', True, 0)` — 정상 초안 |
| 초안에 단계 강제 변경(MANAGER, MEASURE→RECEIVED) | 200 응답, `('RECEIVED', True, 0)` — **숨은 모양** |
| 위 상태에서 자동저장이 한 번 더 옴 | `('DRAFT', True, 0)` — 자동저장이 status 를 DRAFT 로 되돌린다 |
| 초안에 일반 상태 변경 `/api/update_order_status` → DRAWING | 200 응답(`old_status: DRAFT`), `('DRAWING', True, 0)` — **숨은 모양** |
| 초안 버리기 후 | `status=DELETED`, `original_status=None`, `deleted_at` 있음 |
| 그 초안을 휴지통에서 복원 `/restore_orders` | 302, `('RECEIVED', True, 0)` — **숨은 모양** |
| 음성 대조군: 같은 초안을 명시 저장 PUT | 200, `('MEASURE', False, 1)` — 정상 승격, 화면에 보인다 |

## 5. 스테이징 4건 다시 짜 맞추기 (읽기 전용)

스테이징 DB 는 운영을 2026-07-14 무렵 복사한 것이다(그날까지 하루 사용자 5~11명이 찍히다가 07-14 이후 1명으로 줄고, 주문 번호도 운영과 갈라진다). 그래서 4237·4266·4301·4308 의 07월 기록은 운영 기록 그대로다. 시각은 UTC.

| 주문 | 초안 생성 | 마지막 쓰기(=autosaved_at) | 걸린 시간 | status / workflow.stage / erp_stage_code | 실측일 |
|---|---|---|---|---|---|
| 4237 | 07-01 07:25:16 | 07-01 07:26:12.658 | 56초 | MEASURE / MEASURE / MEASURE | 있음 |
| 4266 | 07-03 01:38:12 | 07-03 01:40:13.834 | 2분 1초 | MEASURE / MEASURE / MEASURE | 있음 |
| 4301 | 07-05 23:41:19 | 07-05 23:42:30.982 | 1분 12초 | RECEIVED / RECEIVED / RECEIVED | 있음 |
| 4308 | 07-06 00:19:02 | 07-06 00:21:14.003 | 2분 11초 | MEASURE / MEASURE / MEASURE | 있음 |

네 건 공통:

- `meta` = `draft`·`created_via=ADD_ORDER_AUTOSAVE`·`draft_token`·`autosaved_at` 네 개뿐이다. 승격이 남기는 `finalized_at` 이 없다.
- `structured_updated_at` 이 `meta.autosaved_at` 과 마이크로초까지 같다. 자동저장은 둘을 같은 `now` 로 쓴다(`erp_orders_structured.py:2339`, `:2361`, `:2370`). 즉 **마지막으로 쓴 쪽은 자동저장**이다.
- 그런데 status 는 DRAFT 가 아니다. 자동저장은 항상 `status='DRAFT'` 를 쓰므로, 그 쓰기가 UPDATE 에서 빠졌다는 뜻이다. 8-03 커밋이 설명한 "세션에 이미 DRAFT 로 들고 있어 status 가 빠진" 바로 그 지문이다.
- `order_events` 0건, `security_logs` 0건, `order_field_changes` 0건. 단계 강제 변경·상태 변경 기록이 없다. 같은 날 만든 이웃 주문(4231·4232·4240 등)은 `STAGE_CHANGED`·`MEASUREMENT_DATE_CHANGED` 가 남아 있다.
- 휴지통 복원 기록("주문 N개 복원")이 2026-06-04 다음은 08-10 이다. 07-01~07-14 사이에는 없다. 휴지통 복원으로 생긴 것이 아니다. 게다가 MEASURE 3건은 복원으로는 나올 수 없는 값이다(복원은 RECEIVED 또는 DRAFT 만 만든다).
- 스테이징 전체에서 `payload.from_status='DRAFT'` 인 단계 이벤트는 0건, `ORDER_CREATED` 가 있는데 표식이 참인 주문도 0건이다.

결론: 4건 모두 8-03 전 레이스다. 확신도 높음.

참고로 스테이징의 지운 초안(06-30 이후 18건) 중 7건(4219·4223·4265·4297·4312·4349·4352)은 `original_status` 없이 지워졌다. 이것이 "버리기" 흔적이다(지운 시각이 마지막 자동저장 몇 초 뒤). 이런 행을 휴지통에서 복원하면 바로 숨은 주문이 된다.

## 6. 원인을 확정할 운영 읽기 (실행하지 않았다 — 사용자 승인 1회 필요)

모두 SELECT 만이다. 고객 이름·전화·주소는 고르지 않는다. 감사 문장(`message`)은 이름이 섞이므로 본문을 고르지 않고, 필요한 곳은 일치 여부(참/거짓)나 건수만 고른다. 운영 시각은 모두 UTC 다(컨테이너 시계 기준).

```sql
-- R1. 7건 + 대조군 4608(08-03 커밋이 든 사례, 지금은 안 숨은 것으로 보임)의 모양
SELECT o.id, o.status, o.original_status, o.deleted_at, o.created_at,
       o.structured_updated_at, o.mutation_version, o.erp_stage_code, o.erp_stage_updated_at,
       o.structured_data #>> '{meta,draft}'               AS meta_draft,
       o.structured_data #>> '{meta,created_via}'         AS created_via,
       o.structured_data #>> '{meta,autosaved_at}'        AS autosaved_at,
       o.structured_data #>> '{meta,finalized_at}'        AS finalized_at,
       o.structured_data #>> '{workflow,stage}'           AS wf_stage,
       o.structured_data #>> '{workflow,stage_updated_at}' AS wf_stage_at,
       (o.structured_data -> 'workflow') ? 'stage_override' AS has_override_mark,
       o.structured_data ? 'delete'                        AS has_delete_meta,
       (o.structured_data #>> '{schedule,measurement,date}') IS NOT NULL AS has_measure_date
FROM orders o
WHERE o.id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078, 4608)
ORDER BY o.id;

-- R2. 주문 이벤트(종류·시각·주체 번호·단계 값만)
SELECT e.order_id, e.id, e.event_type, e.created_at, e.created_by_user_id,
       e.payload->>'via' AS via, e.payload->>'created_via' AS created_via,
       e.payload->>'from' AS from_stage, e.payload->>'to' AS to_stage,
       e.payload->>'from_status' AS from_status, e.payload->>'mode' AS mode,
       e.payload->>'status' AS status_in_payload
FROM order_events e
WHERE e.order_id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078, 4608)
ORDER BY e.order_id, e.created_at, e.id;

-- R3. 대상이 적힌 감사 행(저장·상태 변경·강제 변경 모두 target_id 를 남긴다)
SELECT s.target_id, s.id, s.timestamp, s.user_id, s.action,
       s.detail->>'mode' AS mode, s.detail->>'change_set' AS change_set
FROM security_logs s
WHERE s.target_type = 'order'
  AND s.target_id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078, 4608)
ORDER BY s.target_id, s.timestamp;

-- R4. 휴지통 복원 기록(주문 번호가 안 남는다 — 시각·주체·건수만)
SELECT s.id, s.timestamp, s.user_id, s.detail->>'count' AS restored_count
FROM security_logs s
WHERE s.message LIKE '주문 %개 복원' AND s.timestamp >= '2026-06-30'
ORDER BY s.timestamp;

-- R5. 변경 원장(경로·종류만, 값은 고르지 않는다)
SELECT f.order_id, f.created_at, f.change_set_id, f.path, f.op
FROM order_field_changes f
WHERE f.order_id IN (4237, 4266, 4301, 4308, 4409, 4600, 5078, 4608)
ORDER BY f.order_id, f.created_at;

-- R6. 전체에서 "승격했는데 표식이 다시 켜진" 주문(레이스가 아직 열려 있다는 신호, 0 이어야 정상)
SELECT o.id, o.status, e.created_at AS order_created_at,
       o.structured_data #>> '{meta,autosaved_at}' AS autosaved_at
FROM orders o
JOIN order_events e ON e.order_id = o.id AND e.event_type = 'ORDER_CREATED'
WHERE o.is_erp_order IS TRUE AND (o.structured_data #>> '{meta,draft}') = 'true';

-- R7. 전체에서 초안에 걸린 단계 쓰기
SELECT e.order_id, e.event_type, e.created_at, e.payload->>'to' AS to_stage
FROM order_events e
WHERE e.payload->>'from_status' = 'DRAFT'
   OR (e.event_type IN ('STAGE_CHANGED', 'STAGE_AUTO_TRANSITIONED', 'QUEST_APPROVAL_CHANGED')
       AND e.payload->>'from' = 'DRAFT')
ORDER BY e.created_at;

-- R8. 지운 초안 52건의 original_status 분포(복원하면 숨은 주문이 되는 후보 = 없음·RECEIVED 등)
SELECT COALESCE(original_status, '(없음)') AS original_status, count(*)
FROM orders
WHERE is_erp_order IS TRUE AND deleted_at IS NOT NULL
  AND (structured_data #>> '{meta,draft}') = 'true'
GROUP BY 1 ORDER BY 2 DESC;

-- R9. 실측 알림톡 자동 발송이 켜져 있는지(데이터 정리 경로 선택에 필요, §7-c)
SELECT count(*) AS auto_sends_30d, max(created_at) AS last_auto_send
FROM domain_side_effect_outbox
WHERE effect_type = 'ALIMTALK_SEND'
  AND dedupe_key LIKE 'alimtalk:measure:%'
  AND dedupe_key NOT LIKE '%:manual:%'
  AND created_at >= now() - interval '30 days';
```

### 6.1 읽은 결과를 이렇게 판정한다 (5078 기준)

| 보이는 것 | 뜻 |
|---|---|
| R2 에 `ORDER_DRAFT_CREATED` 만 있고 `ORDER_CREATED`·단계 이벤트가 없음. R3 에 저장·상태 변경 행 없음. R1 에 `finalized_at` 없음, `structured_updated_at = autosaved_at`. R4 에 그 뒤 시각의 "주문 1개 복원" 이 있음 | **휴지통 복원**(§2 9번)으로 확정. R1 에서 `wf_stage`·`erp_stage_code` 가 MEASURE 인데 status 만 RECEIVED 면 더 강한 증거다(복원은 status 만 RECEIVED 로 덮는다) |
| R2 에 `STAGE_OVERRIDE`(payload `from_status='DRAFT'`) 또는 `STAGE_CHANGED`(from DRAFT) 가 마지막 쓰기, R1 `has_override_mark` 참 | 단계 쓰기 경로(§2 10·11번) |
| R2 에 `ORDER_CREATED` 가 있고 R1 `autosaved_at` 이 그보다 늦음, R6 이 0 이 아님 | 레이스가 아직 열려 있다 — §3 판단이 틀렸다. 이 경우 요청 로그(같은 초안에 대한 PUT·autosave 응답 시각)를 따로 봐야 한다 |
| R2 에 `QUEST_APPROVAL_CHANGED`·`STAGE_AUTO_TRANSITIONED` | 퀘스트 승인(§2 12번) |

나머지 6건은 §5 와 같은 지문(이벤트 없음, `finalized_at` 없음, 마지막 쓰기 = 자동저장)이면 8-03 전 레이스로 확정한다. 4600 은 날짜(08-01)가 이벤트 도입(08-05) 전이라 R2 가 비어 있는 것이 정상이다. 4608 은 어떻게 다시 보이게 됐는지(누가 편집 화면에서 저장했는지) 참고용이다.

## 7. 고치는 안

### (a) 근본 수정 — 규칙 하나: "표식이 참이면 status 는 DRAFT 또는 DELETED"

초안을 실제 주문으로 만드는 길은 **승격 함수 하나**(`_finalize_draft_state`)만 남기고, 나머지 status 쓰기는 초안을 거절한다.

1. 승격 함수를 서비스로 옮긴다. `foms/api/erp_orders_structured.py:965` `_finalize_draft_state` 와 `:832` `_emit_order_created_event` 를 `foms/services/orders/` 아래 새 모듈로 옮기고, API·AS 접수(`foms/api/cs/as_orders.py:574`)·휴지통이 같은 함수를 부르게 한다. 지금은 AS 접수가 API 모듈을 import 하고 있다.
2. 단계 쓰기에 초안 거절을 넣는다. 잠근 행 기준으로 `is_erp_order_draft(order)` 이면 409 `{'success': False, 'error': 'DRAFT_NOT_PROMOTED', 'message': '먼저 주문을 저장한 뒤 단계를 바꿀 수 있습니다.'}`.
   - `foms/services/orders/stage_override.py:322` `apply_stage_override`(단건·일괄 모두 이 함수를 지난다)
   - `foms/services/orders/order_transition_service.py:309` `transition_order`(정본 전이: 일반 상태 변경·PUT 뒤 실측 자동 전진·퀘스트가 지난다. PUT 뒤 자동 전진은 이미 승격된 뒤라 걸리지 않는다)
   - `foms/api/orders/status.py:417` 의 옛 쓰기 갈래(`order.status = new_status`)
3. 정리 크론 옆에 **감시만 하는** 점검을 하나 둔다. `meta.draft=true AND status NOT IN ('DRAFT','DELETED') AND deleted_at IS NULL` 건수가 0 이 아니면 운영 알림을 보낸다. 자동으로 고치지는 않는다(원인을 가리는 땜질 금지). 이번처럼 5주 동안 아무도 모르는 일을 막는다.

증명 테스트(새 파일, 가칭 `tests/domains/test_erp_draft_flag_invariant.py`):

- `test_stage_override_rejects_unpromoted_draft`: 자동저장으로 초안 생성 → 강제 변경 → 409 `DRAFT_NOT_PROMOTED`, DB 는 `('DRAFT', True)` 그대로. **음성 대조군**: 같은 내용을 PUT 으로 승격한 주문에 같은 요청 → 200, 화면에 보임.
- `test_update_order_status_rejects_unpromoted_draft`: 같은 방식 + 같은 음성 대조군.
- `test_draft_flag_invariant_after_every_writer`: 위 쓰기 경로를 차례로 부른 뒤 매번 "표식 참이면 status 는 DRAFT·DELETED" 를 단언한다.
- 지금 코드에서는 앞의 두 테스트가 실패해야 한다(§4 재현 결과가 그대로 실패 값이다). 그래야 테스트가 결함을 잡는다는 증거가 된다.
- 선택: PG 레인(`tests/postgres/`)에 두 연결로 "PUT 이 잠근 동안 자동저장이 기다렸다가 `already_promoted` 로 빠진다"를 실제 동시성으로 고정하는 테스트. 지금 회귀 테스트는 순서대로만 돈다.

### (b) 휴지통 복원 수정

`foms/web/orders/trash.py:349` 갈래에서 초안(`is_erp_draft_structured_data(order.structured_data)` 또는 `original_status == 'DRAFT'`)을 따로 다룬다. 사용자 결정이 필요하다.

- **b-1 (추천) 복원 = 정식 승격.** PUT 과 같은 필수값 검사(`foms/api/erp_orders_structured.py:168` `_missing_required_structured_fields`)를 통과하면 (a)-1 의 승격 함수로 표식을 끄고 status 를 `workflow.stage` 로 맞추고 `ORDER_CREATED` 를 남긴다. 통과 못 하면 그 행은 복원하지 않고 "작성 중이던 초안이라 필수값(…)이 없어 복원하지 않았습니다" 를 띄운다. 복원한 관리자가 기대하는 것("주문이 다시 보인다")과 결과가 같아진다. 감사 행도 지금의 "주문 N개 복원"(번호 없음, `trash.py:359`)에 주문 번호 목록과 `action='ORDER_RESTORED'`·`target_id` 를 더한다.
- b-2 초안은 복원 대상에서 빼고 휴지통에 "저장 안 된 초안" 표시만 한다. 단순하지만 사람이 입력해 둔 내용을 되살릴 길이 없어진다.

증명 테스트:

- `test_trash_restore_of_discarded_draft_becomes_visible_order`: 필수값 있는 초안 → 버리기 → 복원 → `meta.draft is False`, status = `workflow.stage`, `active_filter` 로 1건, `ORDER_CREATED` 정확히 1건.
- `test_trash_restore_of_incomplete_draft_is_refused`: 필수값 없는 초안 → 복원 → 여전히 삭제 상태, 안내 문구.
- **음성 대조군** `test_trash_restore_of_normal_order_unchanged`: 초안이 아닌 주문(`status='DELETED'`, `original_status='MEASURE'`) → 복원 → `MEASURE`, 화면에 보임, `ORDER_CREATED` 추가 없음. 수정이 일반 복원을 건드리지 않았다는 증거다.
- 크론이 지운 초안(`original_status='DRAFT'`)도 같은 갈래를 타는지 한 건 더.

### (c) 운영 7건 데이터 정리 계획 — **사용자 별도 명시 승인 필요(설계서 A-4)**

무엇을 바꾸나(주문마다): `meta.draft` 거짓, `meta.finalized_at` 기록, `status` 를 `workflow.stage` 와 맞춤(레이스 6건은 이미 같다. 5078 은 R1 로 확인), 평면 칸 동기화, `ORDER_CREATED` 1건, `mutation_version` 1 올림, 저장 감사 행, 대시보드 캐시 무효화. 고객 데이터(이름·품목·금액·일정)는 건드리지 않는다.

어떤 길로:

- **기본안 — 편집 화면 "저장" 1번.** 관리자가 `/orders/<id>/edit` 를 열고(삭제 여부만 보므로 숨은 주문도 열린다, `foms/web/orders/edit.py:247`) 아무것도 바꾸지 않고 저장한다. 그러면 정식 경로 PUT(`foms/api/erp_orders_structured.py:1394`)이 그대로 돈다: 행 잠금·버전·영수증(`execute_order_mutation`) → 승격 함수(표식 끔·`finalized_at`·status·평면 칸·`ORDER_CREATED`) → `ORDER_STRUCTURED_SAVED` 감사 + 변경 원장 → 대시보드 캐시 무효화(`invalidate_dashboard_families_for_order_save`, Redis 공용).
  - 먼저 확인할 것 1: **실측 알림톡 자동 발송.** 저장 뒤 `maybe_send_measure_alimtalk`(`foms/services/kakao_alimtalk.py:1076`)가 돈다. 자격 판정은 지난 날짜를 거르지 않는다(`:143`, `:524`). 이 주문들은 초안이라 한 번도 자동 발송되지 않았으므로, 자동 발송이 켜져 있으면 **7월 실측 일정 안내가 지금 고객에게 나간다.** R9 가 0 이고 운영 web 의 `FOMS_ALIMTALK_AUTO_ENABLED` 가 꺼져 있을 때만 이 길을 쓴다.
  - 먼저 확인할 것 2: 저장 뒤 실측 자동 전진. 실측일이 있는 RECEIVED 주문(4301·4600·5078 중 해당분)은 저장 직후 MEASURE 로 한 칸 간다(`foms/api/erp_orders_structured.py:1783-1800`). 원래 저장했을 때 일어났을 일이라 맞는 결과지만, 사용자에게 미리 알린다.
  - 먼저 확인할 것 3: 필수값이 비어 있으면 400 이 난다. 그 주문은 사용자와 내용을 확인한 뒤 채워서 저장한다.
- 대안 — 자동 발송이 켜져 있으면: 일회성 정리 스크립트(기본 dry-run, `--execute` 와 승인 필요)가 `execute_order_mutation` 안에서 (a)-1 의 같은 승격 함수만 부르고, `log_access(action='ORDER_DRAFT_FLAG_REPAIRED', target_type='order', target_id=…)` 를 남기고, 커밋 뒤 `invalidate_dashboard_families_for_order_save` 로 캐시를 비운다. 알림톡·자동 전진·자동 작업은 부르지 않는다.

순서:

1. 운영 읽기 R1~R9 승인·실행 → 원인 확정, 7건의 필수값·실측일·알림톡 상태 확인.
2. **스테이징 리허설**: 스테이징에 같은 모양으로 남은 4237·4266·4301·4308 에 같은 방법을 먼저 쓴다. `claude_master` 로 대시보드·검색에 나타나는지, 알림톡 outbox 행이 안 생겼는지 본다.
3. 운영 실행 직전 스냅샷(번호·status·`mutation_version`·`structured_data->'meta'`·`structured_data->'workflow'`·`erp_stage_code` 만, 고객 정보 없음)을 로컬 JSON 으로 저장.
4. 운영 실행(7건).

확인:

- `SELECT id, status, structured_data #>> '{meta,draft}', structured_data #>> '{workflow,stage}' FROM orders WHERE id IN (…7건…)` → 표식 false, status = stage.
- 설계서의 개수 쿼리(`status NOT IN ('DRAFT','DELETED') AND deleted_at IS NULL AND 표식 참`) → 0.
- `ORDER_CREATED` 가 주문마다 정확히 1건, `ORDER_STRUCTURED_SAVED`(또는 `ORDER_DRAFT_FLAG_REPAIRED`) 1건.
- R9 와 같은 조건에 이 7개 번호의 새 outbox 행이 없음.
- 화면 확인은 사용자가 주문 번호로 검색해서 본다(운영 측정 계정은 요청 1건당 1회 규칙).

되돌리기(정리 자체가 문제를 만든 경우에만):

- 3번 스냅샷으로 주문마다 `status` 와 `meta.draft`·`meta.finalized_at` 만 되돌린다(`jsonb_set`). `structured_data` 전체를 되돌리지 않는다 — 정리 뒤에 사람이 고친 내용이 날아간다.
- 정리가 만든 `ORDER_CREATED` 이벤트를 그 id 로 지운다.
- 되돌리면 주문은 다시 숨는다(정리 전 상태). 그래서 되돌리기는 "정리가 데이터를 망쳤을 때"만 쓴다.

지운 초안 52건은 그대로 둔다(지운 상태라 맞다). (b) 가 들어가면 그것들을 복원해도 숨은 주문이 되지 않는다. 설계서 결정 3(status 하나로만 초안 판정)은 이 정리와 (a)·(b) 가 끝난 뒤에만 안전하다.

## 8. 사용자가 정할 것

1. 운영 읽기 R1~R9 실행 승인(읽기만, 1회).
2. 휴지통 복원 방식: b-1(복원 = 정식 승격, 추천) 또는 b-2(초안 복원 금지).
3. 데이터 정리 승인과 경로(편집 화면 저장 / 정리 스크립트). 알림톡 자동 발송 상태에 따라 갈린다.
4. (a)·(b) 는 코어 변경(API·상태 전이)이라 Spec → 승인 → 구현 순서를 따른다.
