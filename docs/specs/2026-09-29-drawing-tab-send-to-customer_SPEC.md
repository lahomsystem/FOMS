# 도면 탭에서 고객에게 바로 보내기 — 구현 SPEC (v2 · 2026-09-29 · 승인 대기)

> 2026-09-29 · 상태: **v2(리뷰 17건 반영) · 사용자 승인 대기** · 등급: 코어 변경(API 입력 계약에 선택 필드 · 도면 확정 흐름 · 고객 발송) → Spec → 승인 → 구현.
> 근거: 목업 v4(확정본, 사용자 확인 — 세션 scratchpad `drawing-send-mockup-v4.html`, 영업·도면팀·PC 흐름과 호환 점검표 C1~C21), 원장 `docs/plans/2026-09-29-drawing-defects-verification-ledger.md`, 2차 설계서 `docs/specs/2026-09-29-drawing-defects-batch2_SPEC.md`(운영 반영 완료, production `9cd99254`).
> 기준 코드: 워크트리 `C:/tmp/foms-s-s0929-115959` HEAD `36dfad8cf`(= deploy·production 코드). 아래 "파일:행"은 이 HEAD 에서 `grep -n` 으로 다시 뽑은 값이다. **행 번호는 밀리므로 브리프에는 행 번호와 함께 앵커(id·함수 이름·클래스)를 같이 적는다** — 앵커가 정본이다.
> 이미 정해진 사용자 결정(이 문서는 바꾸지 않는다): ① 확정과 보내기는 분리 ② 확정 전이어도 언제든 보낸다(1차 초안도) ③ 알림톡 문구는 지금 템플릿 그대로, `#{문서종류}` 값만 회차 이름으로(카카오 새 심사 없음) ④ 고객이 링크에서 직접 승인하는 버튼은 나중 ⑤ 도면팀 화면도 같이(영업→고객 상태 한 줄 · 고객 요청 표시 · 사진) ⑥ PC 도면 작업실 결정 바에도 같은 버튼·같은 조건 ⑦ 2차에서 막은 규칙(고객컨펌 게이트 · 폼 잠금 · 수정요청 files 계약)을 깨지 않는다.

---

## 0. 한눈에

**한 줄**: 새 엔드포인트 **0개**. 고객 발송은 이미 있는 `/api/share/*` 를 도면 탭에서 그대로 부르고, 서버는 **선택 필드 2곳 + 발송 이벤트 표지 + 알림톡 문서 이름 1곳 + 읽기 모델 1개**만 더한다. 나머지는 화면(모바일 도면 방 · PC 결정 바 · 시트 3개)이다.

| 묶음 | 내용 | 서버 | 화면 | 규모(대략) |
|---|---|---|---|---|
| **G0 착수 전 확인**(코드 없음) | 솔라피 읽기 도구로 LAHOM/HAUD 공유 템플릿 원문·버튼 이름 확인 → §10.1 에 적는다. 결과에 따라 §4.3 이름 모양 확정 | — | — | 문서 |
| **S1a 뼈대**(작은 커밋 하나, 먼저 합친다) | `drawing_customer_send.py` 에 회차 함수 `drawing_round_info` + 빈 화면값 `empty_customer_send_view()` · `workbench.py` ctx 에 `customer_send` 기본값 배선 | 새 모듈 1(뼈대) · workbench.py 몇 줄 | 없음 | 파이썬 +약 60줄 |
| **S1 서버·기록** | 수정요청 선택 필드 · 수령 확정 선택 필드 · `#{문서종류}` 회차 이름(환경변수 스위치) · 발송 이벤트 표지(회차·짝 링크·화면 구분) · 발송 흔적 쓰기 앞 행 잠금 · 영업→고객 상태 읽기 모델 · "N차" 표기 파이썬 쪽 · 공유 화면 `share_round_label` 값 | 새 모듈 2 · 라우트 소폭 · workbench.py 배선 | 없음 | 파이썬 +약 380줄, 테스트 +약 550줄 |
| **S2 PC 상세(공용 시트 포함)** | PC 결정 바(서버 목록 순회) · 보내기 시트 · 고객 OK 시트 · 수정요청 시트에 출처·받은 경로 · 전달 취소 경고 · 확정 뒤 머물기 · 새 JS 2개 | 없음 | `workbench_detail_body.html` · 새 JS 2개 | 템플릿 +약 180줄, JS +약 480줄(2파일) |
| **S3 모바일 도면 방 + 고객 화면** | 하단 바(서버 목록 순회) · 회차 기록 줄 · 영업→고객 상태 한 줄 · 스레드 "고객 요청" · 목록 카드 · "N차" 표기 템플릿 쪽 · 공유 화면 제목(Q3) · CSS·핀 | 없음 | `workbench_mobile_handoff.html` · 목록 카드 · 태블릿 갤러리 · 공유 화면 2개 · `foms-drawing-mobile.css` | 템플릿 +약 90줄, CSS +약 80줄 |
| (마무리) | 세 갈래 합친 뒤 인벤토리 재확인 · 핀 자물쇠 · 결정 기록 · 스테이징 390px 캡처 · 첫 운영 발송 확인(Q6) | — | — | 문서 |

**병렬 갈래와 파일 겹침**(겹침은 "약속한 이름"뿐이다)

| 파일 | S1a | S1 | S2 | S3 |
|---|---|---|---|---|
| `foms/services/orders/drawing_customer_send.py`(새) | ●(뼈대) | ●(본문) | | |
| `foms/web/drawing/workbench.py` | ●(ctx 기본값) | ●(값 채우기·N차) | | |
| `foms/services/orders/drawing_revision_source.py`(새) | | ● | | |
| `foms/api/drawing/erp_orders_revision.py` | | ● | | |
| `foms/services/orders/drawing_receipt_command.py` | | ● | | |
| `foms/api/share.py`(이벤트 표지·잠금·이름·`share_round_label` 값) | | ● | | |
| `templates/drawing/partials/workbench_detail_body.html` | | | ● | |
| `static/js/foms/drawing-customer-send.js`(새) · `drawing-customer-ok.js`(새) | | | ● | |
| `tests/performance/test_page_local_defer_contract.py`(두 파일 추가) | | | ● | |
| `templates/drawing/partials/workbench_mobile_handoff.html` | | | | ● |
| `templates/drawing/partials/workbench_mobile_queue_card.html` · `tablet_gallery_body.html` | | | | ● |
| `templates/orders/share_view.html` · `share_bundle_view.html`(제목 + 핀 — **한 갈래로 몬다**, `<title>`:11 과 핀 `<link>`:12 가 이웃 줄이라 두 갈래가 고치면 병합 충돌) | | | | ● |
| `static/css/components/foms-drawing-mobile.css` + 핀 4곳(§6) + `tests/domains/test_drawing_mobile_asset_pin_freshness.py` 자물쇠 | | | | ● |
| 인벤토리 JSON(`docs/harness/*_inventory.json`) | | ●(refresh·커밋) | | (마무리에서 재확인) |

- **약속**(갈래 사이 계약): §4.5 의 화면값 이름(`customer_send.*` · 스레드·요청 항목의 `source_tag` · 목록 행의 `latest_request_is_customer` · `round_text` · 공유 화면 `share_round_label`)과 §3.5 의 시트 id·data 속성(`#dwCustomerSendModal` · `#dwCustomerOkModal` · `#dwRevisionModal[data-revision-source]` · (Q5 가 "넣는다"면) `#dwCancelWarnModal`).
- **합치는 순서**: G0 → **S1a 먼저 합침** → S1 · S2 · S3 는 S1a 위에서 동시에 시작 → S1 → S2 → S3 → 마무리.
  - 이유: Jinja 기본 `Undefined` 에서는 없는 변수의 속성을 읽는 순간 `UndefinedError` 다(`customer_send.bar` → 상세 화면 전체 500). S1a 가 모든 키를 빈 값으로 채운 `customer_send` 를 ctx 에 넣어 두면, S2·S3 워크트리에서도 기존 상세 렌더 테스트가 초록이고 §7.2 게이트를 갈래마다 돌릴 수 있다. 빈 값이면 새 버튼은 안 보인다(새 렌더 테스트만 S1 합친 뒤 초록).
  - 이중 안전: S2·S3 템플릿은 첫 사용 자리에서 `{% set cs = customer_send|default({}) %}` 로 받고 `cs.bar|default([])` 처럼 읽는다. 공유 화면은 `{{ share_round_label|default('') }}`.
- 동시 편집이면 갈래마다 `python tools/harness/session_worktree.py create` 로 워크트리를 나눈다(AGENTS.md).

---

## 1. 목표 / 비목표

### 목표
1. 영업이 **도면 탭 하나**에서 초안 도착 → 고객에게 보내기 → 고객 답(고쳐 달래요 / OK) → 확정 → 고객 컨펌까지 끝낸다. "확정만 하기"를 골랐거나 컨펌이 실패했어도 **도면 탭에서 이어서** 컨펌한다(§3.0 CONFIRMED 줄의 [고객 컨펌하고 생산으로]). ERP 주문 화면으로 가지 않는다.
2. 보내기는 확정과 따로다. 1차 초안부터 언제든(도면이 전달돼 있고 수정 중이 아닐 때) 보낸다.
3. 고객이 한 말은 그대로 도면팀 수정요청이 되고, 도면팀 화면·알림에 **"고객 요청"** 으로 구분돼 보인다(받은 경로 · 사진 포함).
4. 도면팀은 영업이 고객에게 보냈는지·링크가 열렸는지를 **읽기 전용 한 줄**로 본다. 고객에게 이미 보낸 회차를 전달 취소하려 하면 멈추고 경고한다.
5. PC 결정 바와 모바일 하단 바는 **같은 버튼을 같은 조건**으로 보인다(서버가 만든 버튼 목록 하나를 두 표면이 순회).
6. 2차 규칙(고객컨펌 게이트 C21 · 폼 저장 잠금 M1 · 수정요청 files 계약 M5)은 그대로 통과한다 — 새 코드는 기존 라우트를 부를 뿐 우회로를 만들지 않는다.

### 비목표(확정된 것)
- 고객이 링크에서 직접 승인·수정요청하는 버튼(사용자 결정 ④: 나중).
- 새 알림톡 템플릿·문구 변경(결정 ③).
- 같은 링크 재발송(토큰 원문을 저장하지 않는 구조, `foms/services/order_share.py:163`). 대신 모든 링크가 늘 현재 도면을 보여 준다(C3).
- 공유 API 권한 좁히기. 지금 `/api/share/*` 는 ADMIN·MANAGER·STAFF 누구나다(`foms/api/share.py:791` `_SHARE_ROLES`) — 도면 탭은 **화면에서만** 영업 쪽에게 버튼을 보인다. 서버를 좁히면 ERP 주문 화면 동작이 바뀌므로 별건.
- 수정요청 라우트 응답 모양을 `{success, data, error}` 로 바꾸기. 이 라우트는 옛 모양 `{success, message}` 이고 2차 M5 도 옛 모양에 `code`·`error` 만 더했다 — 같은 방식을 따른다.
- 링크 열람에서 직원 열람 빼기(로그인 세션 열람 제외). 이번에는 문구로 알리고(§2.3) 별건으로 남긴다.
- 태블릿 도면 검토·ERP 대시보드에서 보내는 수정요청의 출처 선택(§2.5) — 다음 묶음 후보.

### 목업에 있지만 이번에 뺄지 사용자에게 묻는 것(Q5)
목업 v4 에 있는데 이 SPEC 이 넣지 않은 네 가지. 임의로 빼지 않고 §8 Q5 로 묻는다.
1. 도면팀 PC 결정 바 **긴급 호출**(목업 "새로 — 지금 PC 에 없음"). 긴급 호출 시트(`templates/partials/shared/erp_mobile_urgent_call_panel.html`)는 모바일 셸 안이라 PC 폭에서 안 뜬다 — 시트 이전이 따로 필요하다.
2. 보내기 시트의 **번호 바꾸기**. 지금은 가린 번호 + "번호가 틀리면 주문 화면에서 고쳐요" 링크(폼 잠금 M1 과 겹치지 않게).
3. 도면팀 수정 중 바의 **요청 고치기**. 수정요청을 고치는 API 가 없다(새 엔드포인트 필요). 지금 대안은 [수정요청 취소] 뒤 다시 요청.
4. 전달 취소 시트의 **영업에게 먼저 알리기(긴급 호출)** 버튼. 모바일에서는 기존 `[data-foms-urgent-call]` 위임 처리(`static/js/foms/urgent-call-sheet.js:204`)를 그대로 쓰는 작은 경고 시트로 넣을 수 있다(§3.4).

---

## 2. 지금 기준선 (코드 확인)

### 2.1 ERP 주문 화면이 고객에게 보내는 경로 전부

| 경로 | 화면(JS) | 서버 엔드포인트 | 본문 | 권한 | 발송 기록 | 실패 처리 |
|---|---|---|---|---|---|---|
| 링크 발급 | `static/js/orders/erp-share.js:227 _create` · `:421 _selfSms` · `:488 _quickAlimtalk` | `POST /api/share/create/<order_id>`(`foms/api/share.py:808-871`) | `{kind: drawing\|estimate\|bundle}` | `login_required` + `role_required(_SHARE_ROLES)`(`share.py:791`) | 감사 `SHARE_LINK_CREATED`. 토큰 `created_by_user_id` = 발급자(`share.py:845`). 토큰 원문은 응답에서 1회만(`token`·`url`) + `to_phone`·`sms_text` | 400 `unknown_kind`·스냅샷 초과, 404 |
| 알림톡 | `erp-share.js:539 _sendAlimtalk` · `:488 _quickAlimtalk`(발급 → 곧바로 발송) | `POST /api/share/send-alimtalk/<share_id>`(`share.py:1466-1594`) | `{token}`(재해시 대조) | 같음 | 선점 `OrderEvent(SHARE_ALIMTALK)` + outbox(`share.py:1535-1557`, `dedupe_key share_alimtalk:{row.id}:{5초 버킷}` UNIQUE) → 결과 `status: sent\|failed`·`error`·`sender_source`(`:1569-1571`) · `sd['alimtalk_share']` 한 칸(`ka.record_share_history`) · 감사 `SHARE_ALIMTALK_SENT`(짝 링크 id `pair_ids` 는 **감사 detail 에만**, `:1592`) | 아래 "알림톡 실패의 뜻" |
| 알림톡(묶음 · 통합 템플릿) | 같음(`kind='bundle'`) | 같은 라우트, `use_both = kind=='bundle' and _both_template_id(brand)`(`:1516`) | 같음 | 같음 | **운영은 이 경로다**(2026-08-31 운영 `web` env `SOLAPI_TEMPLATE_SHARE_BOTH_ID_{LAHOM,HAUD}` 등록, `docs/AI_STATUS.md:208`). 고객이 실제로 받는 도면·계약서 링크를 **그 자리에서 새로 발급**(`_issue_pair_tokens`, `:1526`, `created_by_user_id` 없음). 이벤트의 `share_id` 는 고객이 받지 않는 bundle 행 | 같음. 이 템플릿에는 `#{문서종류}` 변수가 없다(`_share_both_variables`, `:1417-1441`) |
| 회사 문자(LMS) | `erp-share.js:368 _sendSms` | `POST /api/share/send-sms/<share_id>`(`share.py:1155-1271`) | `{token}` | 같음 | `OrderEvent(SHARE_SMS)` + outbox + `alimtalk_share`(channel `sms`) + 감사 `SHARE_SMS_SENT` | 같음. 발신번호 3단 + 브랜드 백업 1회 재시도(`share.py:1106-1152`) |
| 내 폰 문자 | `erp-share.js:421 _selfSms` → `sms:` 딥링크(`:466`) | create 만 부른다 | `{kind}` | 같음 | **발급 기록뿐** — "보냈는지"는 남지 않는다(`erp-share.js:413-419` 주석) | 번호 없으면 `no_valid_phone` 안내 |
| 링크 복사 · 카카오 SDK 공유 | `erp-share.js:273 _copy` · `:332 _shareKakao` | create 만 | `{kind}` | 같음 | 발급 기록뿐(내 폰 문자와 같은 칸) | — |
| 회수 | `erp-share.js:570 _revoke` | `POST /api/share/revoke/<share_id>`(`share.py:1597-1629`) | 없음 | 같음 | `revoked_at` + 감사 `SHARE_LINK_REVOKED` | 멱등 |
| 발급 이력 | `erp-share.js:198 _refreshList` | `GET /api/share/list/<order_id>`(`share.py:874-915`) | — | 같음 | 링크마다 `view_count`·`last_viewed_at`·상태, 최신 20건 | — |
| 발송 이력 창 | `static/js/orders/erp-alimtalk-trace.js:509` | `GET /api/orders/<id>/events?event_type=...`(`foms/api/events.py:112-155`) | — | `login_required` | `SHARE_ALIMTALK`·`SHARE_SMS` 전 이력 | — |

**알림톡·회사 문자 실패의 뜻**(v1 서술 정정)
- 발송 전 단계 실패 — 이벤트가 **생기지 않거나 롤백**된다: 400 `token_mismatch`·`no_valid_phone`(`:1509`)·`snapshot_too_large`, 404, 410 죽은 링크, 503 `not_configured`(`:1521`), 409 `duplicate_send`(`:1560`, 롤백).
- 200 + `data.sent=false`·`error` — 벤더 SDK 가 **요청을 예외로 거절**했다(`ka._solapi_send` 는 접수만 확인, `foms/services/kakao_alimtalk.py:424-458`). 접수 자체가 안 됐으니 **문자 대체발송도 없다**. 대체발송은 접수 성공(`sent=true`) 뒤 카카오 배달이 실패할 때만 벤더가 한다.
- 단 `error == 'network'`(`TimeoutError`·`OSError`, `kakao_alimtalk.py:488-490`)는 **실제로는 나갔을 수 있다**. 이때 다시 보내면 두 통이 된다.
- `sent=true` 는 "벤더가 접수함"이지 "고객 폰에 도착함"이 아니다(DECISIONS 에 한 줄).
- 중복 막기(5초 버킷)는 `share_id` 단위다. 도면 탭은 누를 때마다 새 링크(새 `share_id`)를 만들므로 **서버 중복 막기가 효과가 없다** — 남는 방어는 JS 버튼 잠금(§3.6).

- 폼 저장 잠금과의 관계: `alimtalk_share` 는 서버 소유 키로 문서화돼 있고(`foms/api/erp_orders_structured.py:271-273`), 폼 JS 는 PUT 에 싣지 않는다(`static/js/orders/erp-order-shared.js:797-800`). 다만 발송 흔적 쓰기 `record_share_history` 는 `session.refresh(order)`(`kakao_alimtalk.py:697`, `FOR UPDATE` 아님) 뒤 `structured_data` 를 통째로 되쓴다(`:708-710`) — 행 잠금도 버전 올림도 없다. 도면 탭에서 보내기가 늘면 도면 전달·수정요청(행 잠금 + 버전 +1, `erp_orders_revision.py:92`·`:154-162`)과 몇 밀리초 겹칠 여지가 커진다 → **이번에 고친다**(§4.6).
- 고객 링크 화면은 열 때마다 도면을 새로 모은다(`share.py:175-222 _collect_drawing_files`). 교체된 옛 도면은 뺀다(`superseded_drawing_keys`, `share.py:197`) — 목업의 "1차·2차 섞임"(C2)은 이미 없다. 남은 틈: 전달 이력에 오른 적 없는 도면 분류 첨부(첨부 탭 업로드·옛 고아 업로드)는 보인다(`share.py:184-188`, 원장 R1 · 2차 측정 G1: A 2행/1주문 #5356).

### 2.2 도면 탭에서 그대로 부를 수 있는가

- **서버는 그대로 된다.** 네 엔드포인트 모두 주문 id·share id·토큰만 받고, 주문 폼 상태·도면 상태·확정 여부를 보지 않는다(C1).
- **JS 는 그대로 못 쓴다.** `erp-share.js` 는 `window.ORDER_ID`(`:71`)와 ERP 폼 저장 도우미 `window.fomsErpEnsureSavedForSend`(`:220-224`)·ERP 모달 DOM(`#erpShareModal`)에 묶여 있고, 671줄(JS 300 래칫 기준선 파일)이라 더 키우지 않는다. 도면 탭은 폼이 없으니 "먼저 저장" 단계가 필요 없다 → **새 작은 JS**(`drawing-customer-send.js`)가 같은 엔드포인트를 같은 순서로 부른다. 오류 문구 표는 `erp-share.js:26-41` 과 같은 코드 → 같은 문구(서버 코드가 정본).

### 2.3 열람 횟수·발송 기록을 주문 단위로 합쳐 읽는 법

- 열람: `OrderShareToken` 행마다 `view_count`·`last_viewed_at`(`models.py:860-885`). 열람 때 `share_service.record_view(row)`(`share.py:461`, 견적 링크 `:406`)가 **누가 열었는지 구분 없이** 올린다 — 영업이 자기 폰으로 확인하거나 문자 앱이 링크 미리보기를 만들어도 오른다. 그래서 화면 문구는 "고객이 열어 봄"이 아니라 **"링크 열림 N번 · 마지막 16:40"** 으로 쓰고, 시트·PC 한 줄에는 "(직원이 연 것도 셀 수 있어요)"를 붙인다.
- 발송: `sd['alimtalk_share']` 는 **마지막 한 칸**이고 도면·계약서·묶음이 같이 쓴다 — 회차 판정에는 `OrderEvent(event_type in ('SHARE_ALIMTALK','SHARE_SMS'))` 의 `payload` 를 쓴다(`order_id`·`event_type` 인덱스, `models.py:846-852`).
- **회차 경계는 이력 시각이 아니라 발송 순간에 박은 표지로 판정한다**(v1 정정). 전달 취소는 최신 TRANSFER 를 이력에서 **빼기만** 하고(`foms/api/drawing/erp_orders_drawing.py:545-548` `history.pop`) 취소 표시를 이력에 남기지 않는다(파일을 지울 때만 `OrderEvent(DRAWING_TRANSFER_CANCELLED)`, `:626-640`). 시각 비교만 하면 "2차 전달 11:40 → 11:52 알림톡 → 12:00 전달 취소" 뒤에 11:52 발송이 1차 발송으로 잡힌다. → §4.4 의 `round_at` 표지.
- 링크별 열람은 회차를 가를 수 없다(`view_count` 는 링크별 누적). 규칙: **열림 수 = 이번 회차 발송·발급에 쓰인 링크들의 열람 합**, **마지막 열림 = 도면이 보이는 모든 링크 중 가장 늦은 열람**(옛 링크도 현재 도면을 보여 주므로 이번 회차 도착 뒤 열림이면 이번 회차를 본 것). 옛 링크 열림만 있으면 "링크 열림 · 마지막 16:40"(수 없이).

### 2.4 알림톡 `#{문서종류}` 값을 정하는 자리

- `foms/api/share.py:1377-1409 _share_alimtalk_variables` 의 `'#{문서종류}': _SMS_KIND_LABEL.get(kind, '문서')`(`:1399`), 고정 표 `_SMS_KIND_LABEL = {'drawing': '도면', 'estimate': '견적서', 'bundle': '도면·계약서'}`(`:1004`).
- 같은 값을 쓰는 곳: 내 폰 문자 본문 `share_link_message`(`:1274-1317`, 변수 dict 를 그대로 읽음 → 자동 반영) · 회사 문자 본문(`:1208-1214`, `_SMS_KIND_LABEL` 을 **따로** 읽음 → 같이 바꿔야 함).
- 통합 템플릿(`_share_both_variables`, `:1417-1441`)에는 이 변수가 없다 — 운영의 묶음 알림톡은 회차 이름이 안 들어간다(§3.5 가 미리보기에 그대로 알린다).
- 기존 테스트: `tests/domains/test_order_share_alimtalk.py:119`(`'도면'`)·`:151`(`'도면·계약서'`) — 둘 다 전달 이력이 없는 주문이라 새 규칙에서도 값이 같다.

### 2.5 수정요청 라우트(2b 뒤)와 호출자

- `POST /api/orders/<id>/request-revision`(`foms/api/drawing/erp_orders_revision.py:53-245`): 행 잠금으로 첫 조회(`:92`) · 권한 `_can_modify_sales_domain`(`:103`) · files 계약 M5(`:66-80`, 400 `INVALID_REVISION_FILE`) · 도면 2장 이상이면 대상 필수(`:112-113`) · 상태 `TRANSFERRED`·`CONFIRMED` 에서만(`:131-132`) · 이력 항목(`:136-150`) · M16 고객확인 무효(`:151`) · 버전 +1 쓰기(`:154-162`) · 도면팀 알림 `DRAWING_REVISION`(`:172-180`, 제목 `'도면 수정 요청'`) · 생산 변경 알림(`:185-190`) · 실시간 확인창(`'interrupt': True`, `:222`).
- 수정요청 취소(`:260` 이후)는 `REQUEST_REVISION` 항목을 이력에서 **빼고**(`:319` `history.pop`) 끝에 `REVISION_CANCELLED.request` 로 **통째 보존**한다 → 새 필드도 자동으로 남고, 이력의 `REQUEST_REVISION` 수는 "취소 안 된 요청 수"와 같다(§4.3 이 이것을 쓴다).
- 호출자 넷: 도면 탭 PC·모바일(같은 모달 `#dwRevisionModal`) · **ERP 대시보드**(`static/js/orders/dashboard/erp-dashboard-drawing.js:358`) · **태블릿 도면 검토**(고객 앞에서 쓰는 화면, `static/js/foms/tablet-drawing-review.js:413`). 뒤의 둘은 출처를 안 보내 늘 "영업 의견"으로 남는다 — 이번에 바꾸지 않는다(다음 묶음 후보: 태블릿은 고객 앞이라 출처 기본값이 "고객"일 수 있다).
- 화면: PC 요청사항 카드(`templates/drawing/partials/workbench_detail_body.html:1380-1428`, 앵커 `id="request-{{ r.event_key… }}"`) · PC 타임라인(`:1325` `{% for h in history|reverse %}`, 배지 `:1331-1335`) · 모바일 스레드(`workbench_mobile_handoff.html:188-277` `section.foms-drawing-thread`, 스레드 값은 `foms/web/drawing/workbench.py:400 _revision_thread_fields`) · 목록 카드 메모(`workbench_mobile_queue_card.html:42-47`) · 도면팀 알림창 제목(`static/js/foms/foms-drawing-alert.js:173` 이 `data.title` 을 그대로 씀).
- 모바일 수정요청은 PC 와 **같은 모달** `#dwRevisionModal`(`workbench_detail_body.html:1731-1824`)을 연다(`workbench_mobile_handoff.html:305-310`, `data-drawing-handoff-action="revision"`). 제출은 인라인 `async function submitRevision()`(`:2722-2772`), 대상 도면 검사 `:2739-2742`.

### 2.6 "고객 OK · 확정" = 수령 확정 + 고객 컨펌 승인

- 수령 확정 `POST /api/orders/<id>/confirm-drawing-receipt`(`foms/api/drawing/erp_orders_draftsman.py:325-495`): 권한 `can_confirm_drawing_receipt`(`foms/api/drawing/draftsman_receipt_authz.py:34-65`) · `TRANSFERRED` 에서만(`:360-366`) · 도면 단계면 `CONFIRM` 으로 전이(`foms/services/orders/drawing_receipt_command.py:66-88`) · 응답 `new_stage`·`stage_moved`(`:483-489`). 파일 크기 **495줄**(여유 5줄).
- 고객 컨펌 승인 `POST /api/orders/<id>/quest/approve`(`foms/api/quest.py:315`): 행 잠금(`:324`) · 2a-2 게이트 — 단계가 CONFIRM 이면 도면이 `CONFIRMED` 가 아닐 때 409(`:374-386`) · quest 고르기 `find_stage_quest_for_approve`(`:390`, 활성 최신 → 완료 최신, `foms/services/orders/quest_transition_service.py:126-151`) · 이미 넘어간 주문의 재요청은 409 `ALREADY_TRANSITIONED`(`:394-404`) · 권한 `authorize_quest_approve`(`foms/services/orders/quest_approve_authz.py:219-271`, 파일 353줄) · 응답 `all_approved`·`missing_teams`·`auto_transitioned`·`next_stage`(`:681-689`).
- 새 CONFIRM quest 는 담당자 승인 모드라 한 번 승인으로 완료되지만, **옛 데이터는 팀 모드일 수 있다**(`foms/services/orders/erp_policy_quests.py:206-218`) — 그때는 `success=true` 여도 `all_approved=false`(남은 팀)라 생산으로 안 넘어간다.
- **두 권한은 다르다**: 확정은 "이 주문 배정 영업", 컨펌은 "영업/CS 팀이면 누구나". 합친 API 는 없다.
- 순서가 곧 안전장치다: 확정이 먼저 커밋돼야 컨펌 게이트가 열린다. 확정만 성공하고 컨펌이 실패하면 "도면 CONFIRMED · 단계 CONFIRM"에 머문다 — 이 SPEC 은 그 상태에서 **도면 탭 바에 [고객 컨펌하고 생산으로]** 를 보인다(§3.0).
- 지금 화면: PC `#btn-confirm-receipt`(`workbench_detail_body.html:1506-1510`) · 옛 모바일 바 `#btn-confirm-receipt-mobile`(`:1587`) · v2 모바일은 PC 버튼을 대신 누름(`static/js/foms/drawing-handoff.js:72-81` `proxyLegacyAction`) → `async function confirmReceipt()`(`:2774-2793`)가 **ERP 대시보드로 이동**(`:2788`, `open_quest=true`, C14). 등록 `:2909-2910`.

### 2.7 C14 · C11 · C18 · C15 지금 모습

- C14: 위 `:2788` — `/erp/dashboard?focus_order=…&open_quest=true`. 이 링크는 적어도 컨펌 창까지 데려갔다 → 새 흐름은 그 길을 지우는 대신 도면 탭 안 [고객 컨펌하고 생산으로]로 옮긴다.
- C11: 전달 취소 `POST /api/orders/<id>/cancel-transfer`(`erp_orders_drawing.py:456-700`)는 `TRANSFERRED` 에서만, 최신 TRANSFER 이력을 **빼고**(`:545-548`) 현재 도면을 직전으로 되돌린다 → 고객 링크도 곧바로 직전 도면을 보여 준다. 영업에게 "도면 전달 취소" 알림은 **이미 간다**(`:674-704`). 확인창 문구(`workbench_detail_body.html:2796`, `async function cancelTransfer()` `:2795-2810`)에 고객 발송 여부가 없다.
- C18: 도면팀이 영업→고객 상태를 볼 곳이 없다(작업실 ctx `workbench.py:1235-1296` `ctx = dict(` 에 발송·열람 값이 없음).
- C15: 회차 = TRANSFER 이력 개수(`workbench.py:655`·`:1116`·`:323` 루프). 도면팀은 `TRANSFERRED`·`CONFIRMED` 에서도 **수정요청 없이** 추가 전달(APPEND)을 할 수 있다(`perform_drawing_transfer` 는 `RETURNED` 반영 체크 게이트만, `erp_orders_drawing.py:60-141`; 모드 `:249-254`; PC 는 `can_transfer` 면 상태와 상관없이 [도면 전달], `workbench_detail_body.html:1484-1488`). 표기도 섞여 있다 — "도면팀 N차 전달"(`workbench.py:246,259`) · "vN 전달"(`:712`) · 목록 칩 "vN"(`workbench_mobile_queue_card.html:51`) · 태블릿 갤러리 "· vN"(`tablet_gallery_body.html:137`) · "최신 N차 전달본"(`workbench.py:355`).

### 2.8 목업의 "회사 문자" · "내 폰 문자"

- **둘 다 이미 있다.** 회사 문자 = `send-sms`, 내 폰 문자 = create 응답의 `to_phone`·`sms_text` + `sms:` 딥링크 → **이번 범위 안**.
- 남는 차이: 내 폰 문자·링크 복사·카카오 SDK 공유는 보냈는지 기록이 없다. 도면 탭은 "링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요)"까지만 보여 준다(Q1).

---

## 3. 화면별 설계

### 3.0 공통 판정(서버가 한 번 계산한 버튼 목록 `customer_send.bar` 를 두 표면이 순회한다)

"영업 쪽" = `is_admin or (can_sales_domain and not is_drawing_team)` — 지금 수정요청·수령 확정 버튼과 같은 술어(`workbench.py:1067-1072`). "이번 회차"와 "N차"는 §4.3 `drawing_round_info` 하나로 정한다.

| 도면 상태 | 이번 회차 보냄? | 영업 쪽 버튼(모바일 바 = PC 결정 바, 왼쪽부터 · `bar` 키) | 도면팀 |
|---|---|---|---|
| `PENDING`·`IN_PROGRESS`(전달 전) | — | (없음 — 지금처럼 긴급 호출만) | 지금 그대로 |
| `TRANSFERRED` | 아니오 | [내 의견] `rev_sales` · **[고객에게 보내기]** `send`(주) · [확정] `ok_no_customer` · [긴급](모바일만) | 지금 그대로 + 상태 한 줄 "N차 아직 고객에게 안 보냄" |
| `TRANSFERRED` | 예 | [다시 보내기] `resend` · [고객이 고쳐 달래요] `rev_customer` · **[고객 OK · 확정]** `ok`(주) | 상태 한 줄 "N차 고객에게 보냄 11:52 알림톡 · 링크 열림 1번" · 전달 취소 경고 |
| `RETURNED`(도면팀 수정 중) | — | [수정요청 취소] `cancel_revision` · [긴급](모바일만) — 보내기 없음 | 지금 그대로 |
| `CONFIRMED` · 단계 `CONFIRM` · 컨펌 가능 | — | [고객이 또 바꿔 달래요] `rev_post` · [고객에게 보내기] `send`(부) · **[고객 컨펌하고 생산으로]** `approve_confirm`(주) | 지금 그대로 |
| `CONFIRMED` · 그 밖 | — | [고객이 또 바꿔 달래요] `rev_post` · [고객에게 보내기] `send`(부) · [생산 현황 보기] `production` | 지금 그대로 |

- [내 의견]·[고객이 고쳐 달래요]·[고객이 또 바꿔 달래요]는 **같은 수정요청 시트**를 출처만 다르게 연다.
- [확정](보내기 전)과 [고객 OK · 확정](보낸 뒤)은 **같은 고객 OK 시트**를 연다. 보내기 전이면 제목이 "고객 답 없이 확정할까요?"(매장에서 직접 OK 받은 예외용).
- `approve_confirm` 조건 = 도면 `CONFIRMED` + 단계 `CONFIRM` + `can_approve_after_confirm`(§4.4-4). 컨펌 권한이 없으면 `production` 을 두고 그 아래 한 줄 "고객 컨펌은 영업·CS 팀이 해요".
- [고객에게 보내기]는 현재 도면이 1장 이상일 때만(`drawing_current_files`). 번호가 없으면 버튼은 보이되 시트에서 알림톡·회사 문자를 막고 이유를 쓴다.
- 보낸 뒤 바에서 [긴급]이 빠진다(목업 그대로 — 바 버튼 3개). §10.6 확인 항목.
- 확정 버튼 판정은 지금 값 `can_confirm_receipt`(`workbench.py:1068-1071`)를 그대로 쓴다(§10.4 불일치는 그대로).
- **관리자 겸 도면 담당**처럼 도면 쪽 버튼(전달·전달 취소)과 영업 쪽 버튼이 함께 뜨면 모바일 바가 390px 을 넘친다. 규칙: 모바일 바는 **앞의 3개만** 바에 두고 나머지는 [더 보기](Bootstrap `dropup` — 새 JS 없음)에 넣는다. 서버가 `bar` 항목마다 `slot: "main"|"more"` 를 정한다(우선순위: 도면 쪽 주 버튼 → 영업 쪽 주 버튼 → 나머지 순서). PC 결정 바는 세로라 모두 보인다.

### 3.1 영업 · 모바일(도면 방, `workbench_mobile_handoff.html`)

1. **리본**(`:12` `section.foms-drawing-turn` ~ `:47`)은 지금 그대로. 영업 쪽일 때만 부제 자리에 `customer_send.turn_hint` — 예: 안 보냄 "1차 초안 도착 · 고객에게 보여 줄 차례", 보냄 "고객 답 기다리는 중 · 14:03 알림톡 · 링크 열림 2번". 기존 `_build_drawing_turn`(`workbench.py:226-267`)의 label 은 도면팀·목록 카드가 같이 쓰므로 **건드리지 않는다**(회차 숫자만 §4.5 "N차" 통일을 따른다).
2. **회차 기록 줄**: 새 `<section>` 을 만들지 않는다(`tests/domains/test_drawing_mobile_back_to_workbench.py:35` `DETAIL_TOP_BLOCKS = 5`). 주문 요약 칸 `section.foms-drawing-handoff__order`(`:49-55`) 안, "주문 담당 · 도면 담당" 줄(`:54`) 아래에 `<ol class="foms-drawing-send-steps">`. 항목(최대 4): "N차 도착 11:40" ✓ → "고객에게 보냄 11:52 · 알림톡" ✓/지금 → "링크 열림 · 1번 · 마지막 12:30" → "고객 답". 이전 회차는 한 줄 요약 `<p>`("1차 · 보냄 · 고객 요청 1건")(`<details>` 도 블록 수에 들어간다). `LIST_TOP_BLOCKS = 3` 무변경.
3. **하단 바**(`:281-331` `div.foms-drawing-action-bar`): **`customer_send.bar` 를 순회**해 그린다(§3.0 표는 서버 판정, 템플릿에 조건을 따로 쓰지 않는다). 버튼 클래스는 지금 `foms-drawing-action-bar__btn` + 너비·색 변형 CSS(`--slim`·`--wide`·`--mid`·`--success`·`--warn`). 시트를 여는 버튼은 `data-bs-toggle="modal" data-bs-target="#…"`.
   - `send`/`resend`: `data-bs-target="#dwCustomerSendModal"` + `data-customer-send-mode="first|again"`.
   - `rev_customer`/`rev_post`: `data-bs-target="#dwRevisionModal" data-revision-source="customer" data-drawing-handoff-action="revision" data-drawing-key="<선택 도면 key>"`.
   - `rev_sales`: 같은 모달 + `data-revision-source="sales"`.
   - `ok`/`ok_no_customer`: `data-bs-target="#dwCustomerOkModal" data-customer-ok-mode="customer|no_customer"`.
   - `approve_confirm`: `data-customer-approve` 버튼(새 JS `drawing-customer-ok.js` 가 위임 처리, §3.6).
   - `cancel_revision`: 지금처럼 `data-drawing-handoff-action="cancel-revision"`(대신 누르기 → PC `#btn-cancel-revision`). **지금 따로 그리는 수정요청 버튼 블록(`:305-310`)·수정요청 취소 블록(`:311-315`)·수령 확정 블록(`:316-320`)은 지운다** — bar 가 대신 그린다.
   - `production`: 링크 `/erp/dashboard?focus_order=<id>`.
   - 도면 쪽 버튼(전달 `:289-303`·전달 취소 `:322-326`)과 긴급 호출(`:327-330`, `data-foms-urgent-call`)은 지금 블록 그대로 두고, §3.0 의 `slot` 규칙에 따라 넘치는 것만 [더 보기]로.
   - 막힌 이유 줄(`:282-288` `#dw-transfer-gate-reason`)·본문 아래 여백 규칙은 그대로.
4. **스레드**(`:188-277`): 말풍선 태그(`:194` `foms-drawing-thread__tag`)가 `event.source_tag` 가 있으면 "고객 요청 · 1차 · 카톡 답장"(`foms-drawing-thread__tag--customer`), 없으면 지금 "수정 요청". 참고사진(`:206-229`)·반영 체크(`:231-257`)는 지금 그대로.

### 3.2 영업 · PC(결정 바, `workbench_detail_body.html:1480-1528`, 앵커 `결정 바` 제목 `:1481` · `{{ next_action }}` `:1482`)

- "다음 할 일" 아래에 **`customer_send.bar` 를 순회**해 버튼을 세로로 둔다(모바일과 같은 목록, 모양만 PC: `send`/`resend` btn-primary · `rev_customer` btn-outline-warning · `ok` btn-success(`ok_no_customer` 는 라벨 "확정 (고객 답 없이)") · `rev_sales` btn-outline-secondary(라벨 "내 의견으로 수정요청") · `cancel_revision` · `rev_post` · `approve_confirm` btn-success · `production` 링크). 파리티 테스트 §7 이 두 표면의 키 목록을 비교한다.
- **id 유지**: `ok`/`ok_no_customer` 는 `id="btn-confirm-receipt"`, `cancel_revision` 은 `id="btn-cancel-revision"` 으로 그린다(대신 누르기 표 `drawing-handoff.js:73-78` 과 인라인 등록이 이 id 에 기댄다). 그리고 지금 따로 그리는 블록 — [수정 요청](`:1500-1504`)·[수령 확정](`:1506-1510`)·[수정요청 취소](`:1516-1520`) — 은 지운다(두 번 그리지 않게).
- `#btn-confirm-receipt` 는 `data-bs-toggle="modal" data-bs-target="#dwCustomerOkModal"` 로 바꾸고, 인라인 스크립트의 `click → confirmReceipt` 등록(`:2909-2910`)을 지운다. 옛 모바일 바(`:1564-1603`, v2 가 아닌 사용자)의 `#btn-confirm-receipt-mobile`(`:1587`)도 같은 모달을 연다.
- 결정 바 위 "현재 버전" 아래에 **영업→고객 상태 한 줄**(`small text-muted border rounded p-2 bg-light`): `customer_send.status_line` + "(직원이 연 것도 셀 수 있어요)".
- 요청사항 카드(`:1380-1428`)와 타임라인(`:1325-`, 배지 `:1331-1335`) 수정요청 항목에 `source_tag` 배지(`badge text-bg-warning`).
- PC 쪽은 **새 CSS 없음**(부트스트랩 클래스만). 인라인 `<style>`(`:77-931`)에 규칙을 더하지 않고, `style=""` 도 새로 쓰지 않는다.

### 3.3 도면팀 · 모바일

- 주문 요약 칸에 **영업→고객 상태 한 줄**(`<p class="foms-drawing-handoff__send-status">`, 도면팀에게는 기록 줄 대신 이 한 줄만): "영업 → 고객 · 2차 보냄 11:52 알림톡 · 링크 열림 1번" / "영업 → 고객 · 2차 아직 안 보냄". 읽기 전용.
- 스레드의 "고객 요청" 표시 · 사진 · 반영 체크는 3.1 과 같다.
- 하단 바는 지금 그대로. [전달 취소]는 대신 누르기로 PC `#btn-cancel-transfer` 를 누르므로(`drawing-handoff.js:75`) 경고도 PC 확인창으로 같이 바뀐다(3.4). Q5-④ 가 "넣는다"면 경고가 있을 때만 모바일 [전달 취소]가 경고 시트를 연다(3.4).
- 목록 카드(`workbench_mobile_queue_card.html`): 최신 수정요청이 고객 요청이면 칩 줄(`:49-53`)에 기존 칩 클래스로 "고객 요청" 칩 하나. 메모 줄은 그대로.

### 3.4 도면팀 · PC (+ 전달 취소 경고)

- 결정 바 버튼은 지금과 같다. 달라지는 것 셋:
  1. 영업→고객 상태 한 줄(3.2 와 같은 자리·같은 값).
  2. 요청사항 카드·타임라인의 "고객 요청" 배지.
  3. **전달 취소 경고(C11)**: `#btn-cancel-transfer`(`:1512`)에 `data-customer-sent-text="영업이 이 2차 도면을 고객에게 보냈어요(11:52 알림톡 · 링크 열림 1번)"` 를 서버가 **이번 회차 표지와 같은 발송이 있을 때만**(§4.4) 싣는다. 인라인 `cancelTransfer`(`:2795-2810`)는 이 값이 있으면 확인창을 바꾼다 — 막지는 않는다(Q4). 영업 알림은 지금 라우트가 이미 보낸다(`erp_orders_drawing.py:674-704`).
- 확인창 문구는 **표면별로 가른다**(PC 에는 긴급 호출이 없다). 서버가 두 문구를 `#btn-cancel-transfer` 에 싣고(`data-customer-sent-text-pc` · `data-customer-sent-text-mobile`), 인라인 `cancelTransfer` 가 `window.matchMedia('(max-width: 991.98px)').matches`(v2 모바일 셸이 보이는 폭 = `d-lg-none`)면 모바일 문구를, 아니면 PC 문구를 쓴다. 모바일은 대신 누르기로 같은 PC 버튼을 누르므로(`drawing-handoff.js` 는 손대지 않는다) 누른 쪽을 버튼 속성으로 가를 수 없어 폭으로 가른다.
  - PC: "영업이 이 2차 도면을 고객에게 이미 보냈어요(…). 취소하면 고객 화면에서도 2차가 사라지고 1차가 다시 보여요. 영업에게 먼저 연락하려면 [취소]를 누르세요. 그래도 전달을 취소할까요?"
  - 모바일: 같은 문장에서 "영업에게 먼저 연락하려면" → "영업에게 먼저 알리려면 [취소]를 누르고 긴급 호출을 쓰세요".
- (Q5-④ 가 "넣는다"면) 모바일은 확인창 대신 작은 시트 `#dwCancelWarnModal`(`workbench_detail_body.html`, S2): 경고 문장 + [영업에게 먼저 알리기 (긴급 호출)](`data-foms-urgent-call data-order-id` — `urgent-call-sheet.js:204` 위임 처리가 그대로 연다) + [그래도 취소](취소 API 호출 — `drawing-customer-send.js` 가 처리, 확인창 두 번 금지) + [닫기]. 모바일 [전달 취소] 버튼은 경고 문구가 있을 때만 이 시트를 열고(`data-bs-toggle`), 없으면 지금처럼 대신 누르기.

### 3.5 시트(모달) 3개 — PC·모바일 공용

모두 `workbench_detail_body.html` 의 기존 모달 자리(`:1606` `#dwTransferModal` · `:1731` `#dwRevisionModal` 옆)에 둔다. 모바일은 `modal-fullscreen-sm-down`. 인라인 스타일·인라인 핸들러 금지 — 위임 JS 가 `data-*` 로 처리한다. 서버 값은 `data-*` 로만 넘기고 JS 는 `safeJsonParse` 로 읽는다.

**(가) `#dwCustomerSendModal` — 고객에게 보내기** (`data-order-id` · `data-round` · `data-round-label` · `data-has-phone` · `data-phone-masked` · `data-sent-this-round` · `data-sent-text` · `data-doc-label-drawing` · `data-doc-label-bundle` · `data-bundle-both-template`)
- 맨 위 안내(파란 줄): 1차면 "확정 전이어도 보내요. 고객 의견을 받은 뒤 고치거나 확정하면 돼요." / 2차 이상이면 "고객이 예전 링크를 눌러도 이제 N차만 보여요."
- 다시 보내기(`mode=again`)면 노란 줄: "`{sent_text}` — 한 번 더 보낼까요? 새 링크가 가지만 예전 링크도 똑같이 최신 도면을 보여 줘요."
- 받는 분: 가린 번호 + "번호가 틀리면 주문 화면에서 고쳐요" 링크(`order_edit.edit_order`). (Q5-② 가 "넣는다"여도 번호 편집은 주문 화면 쪽이다.)
- 보낼 것: 현재 도면 썸네일 + 칩 [도면만](kind `drawing`) / **[도면+계약서]**(kind `bundle` — 서버 이름 "도면·계약서"·ERP 메뉴 "도면 + 계약서 (한 링크로)"와 맞춤. 목업의 "도면+견적서"는 쓰지 않는다).
- 보내는 방법: [카카오 알림톡](기본) / [회사 문자] / [내 폰 문자](모바일에서만 — 지금 ERP 와 같은 규칙).
- 고객이 받는 모습(문서 이름만, 템플릿 원문은 베끼지 않는다):
  - 도면만 · 알림톡/회사 문자/내 폰 문자: "문서 이름: `{data-doc-label-drawing}`".
  - 도면+계약서 · 회사 문자/내 폰 문자, 또는 알림톡이면서 `data-bundle-both-template="false"`: "문서 이름: `{data-doc-label-bundle}`".
  - **도면+계약서 · 알림톡 · `data-bundle-both-template="true"`**(운영 기본): "버튼 2개(도면 · 계약서) 알림톡으로 가요. 문서 이름은 템플릿에 고정돼 회차가 안 들어가요."
- 큰 버튼: [알림톡 보내기] / [회사 문자 보내기] / [내 문자 앱 열기]. 번호 없음이면 앞의 둘은 비활성 + "고객 휴대폰 번호가 없어요".

**(나) `#dwCustomerOkModal` — 고객 OK · 확정** (`data-order-id` · `data-can-approve` · `data-mode`)
- 제목: `customer` "고객이 N차 도면으로 OK 했나요?" / `no_customer` "고객 답 없이 확정할까요?"
- 어떻게 확인했나요: 칩 [전화로]·[카톡 답장]·[매장 방문](하나, 선택 안 해도 됨).
- 메모(선택, 200자).
- 확정한 뒤: 라디오 [고객 컨펌까지 끝내고 생산으로](기본) / [확정만 하기 — 고객 컨펌은 나중에(도면 탭 바에 [고객 컨펌하고 생산으로]가 남아요)]. `data-can-approve="false"` 면 첫째를 **그리지 않고** "고객 컨펌은 영업·CS 팀이 해요" 한 줄.
- 도면 상태가 `CONFIRMED` 가 아니면서 단계가 생산 이후인 주문(확정 뒤 재수정의 재확정)은 `can_approve=false` 와 같게 둔다(§4.4).
- 큰 버튼 바로 위: "컨펌까지"가 골라져 있으면 노란 줄 **"생산팀에 알림이 가요. 되돌리기 어려워요."**(강제 단계 변경으로 되돌려도 quest 가 COMPLETED 로 남는 막다른 길이 있다 — 메모리 "강제 단계 변경 regress 는 quest 를 안 되돌린다").
- 큰 버튼: [확정하고 생산으로 넘기기] / [도면 확정하기].

**(다) `#dwRevisionModal` — 수정요청(지금 모달에 더함, `:1731-1824`)**
- 맨 위에 "누구 말인가요" 두 칸 라디오 `name="dw-revision-source"` [고객 요청](`customer`) / [내 의견](`sales`). 여는 버튼의 `data-revision-source` 로 미리 고른다(없으면 `sales` — 지금 동작과 같음).
- 고객 요청이면 "어떻게 받았나요" 칩 [전화로]·[카톡 답장]·[매장 방문](`name="dw-revision-via"`, 선택). 제목·메모 라벨이 "고객이 뭐라고 했나요? / 적은 내용이 그대로 도면팀 수정요청이 돼요. 고객에게는 안 나가요."로 바뀐다.
- 도면 상태 `CONFIRMED` 면 맨 위 노란 줄 "이미 확정한 도면이에요. 수정요청하면 도면팀과 생산팀에 변경 알림이 가요."(C13, 서버가 `data-confirmed="true"`).
- 대상 도면·참고 파일·메모 필수 규칙은 지금 그대로(서버 `:112-113`·M5).
- 지금 안내 문구 "선택하지 않으면 자동으로 최신본이 선택됩니다"(`:1786`)는 서버(2장 이상이면 400)·JS(`:2739-2742`)와 다르다 → "도면이 2장 이상이면 꼭 골라요"로 고친다.

### 3.6 JS 흐름(새 파일 2개, 각 300줄 이하 · document 위임 · `window.__…_BOUND` 한 번만)

**싣는 자리**: 두 파일은 `{% if erp_mobile_v2_enabled %}`(`:3049-3051`) **블록 밖**에 `defer` 로 싣는다(안에 넣으면 PC 에서 시트가 동작하지 않는다). `tests/performance/test_page_local_defer_contract.py` 에 두 파일의 defer 단언을 더한다.

**`static/js/foms/drawing-customer-send.js`**(약 250줄)
1. 모달 `show.bs.modal` → 여는 버튼의 `data-customer-send-mode` 로 안내 줄 전환, 칩·방법 초기화, 미리보기 문구(§3.5 가) 전환.
2. [보내기] → **버튼 잠금(응답이 올 때까지 유지, 성공이면 새로고침까지 풀지 않음)** → `fetch POST /api/share/create/<order_id> {kind}` (try/catch, `data.success` 검증).
3. 방법별: 알림톡 `POST /api/share/send-alimtalk/<share_id> {token, source_screen: 'drawing_tab'}` · 회사 문자 `POST /api/share/send-sms/<share_id> {token, source_screen: 'drawing_tab'}` · 내 폰 문자 `location.href = sms:…`(create 응답 값 그대로, `erp-share.js:466-469` 와 같은 구분자 규칙).
4. 결과 처리:
   - 성공(`data.sent === true`) → 토스트 "○○ 고객님께 2차 도면을 보냈어요" → `location.reload()`.
   - **발송 전 단계 실패**(HTTP 400·404·409·410·503) → 곧바로 `POST /api/share/revoke/<share_id>` 로 방금 만든 링크를 회수(실패해도 무시, try/catch) → 시트 안 오류 줄에 `erp-share.js:26-41` 과 같은 문구. 버튼 잠금 해제.
   - 벤더 거절(200 + `sent=false`, `error != 'network'`) → 오류 줄 "알림톡이 접수되지 않았어요 — {사유}". 이벤트가 남아 상태 줄에 실패로 보인다. 회수하지 않는다(고객에게 안 갔으므로 무해하고, 기록은 이벤트가 짝짓는다).
   - `error == 'network'`, 또는 send 요청 자체가 예외(연결 끊김) → "보냈는지 확실하지 않아요 — 잠시 뒤 새로고침해 상태 줄을 확인하세요". **보내기 버튼을 잠근 채 둔다**(바로 재시도 금지 — 두 통 방지). 회수하지 않는다.
   - 토큰 원문은 메모리에만(저장소 금지).
5. (Q5-④ "넣는다"면) `#dwCancelWarnModal` 의 [그래도 취소] → `POST /api/orders/<id>/cancel-transfer` → 성공이면 `/erp/drawing-workbench/<id>?tab=timeline`.

**`static/js/foms/drawing-customer-ok.js`**(약 240줄)
1. 수정요청 모달 `show.bs.modal` → `event.relatedTarget` 의 `data-revision-source` 로 라디오·제목·받은 경로 칸 전환. `window.fomsDrawingRevisionExtras = () => ({source, received_via})` 를 내놓는다.
2. 인라인 `submitRevision`(`:2722`)은 **`typeof window.fomsDrawingRevisionExtras === 'function'` 일 때만** 본문에 두 값을 더하고, 아니면 지금 본문 그대로 보낸다(핀·캐시로 새 JS 가 안 떠도 수정요청이 멈추지 않게).
3. 고객 OK 모달 [확정] →
   - ① `POST /api/orders/<id>/confirm-drawing-receipt {customer_ok_via, customer_ok_note, customer_ok: (mode==='customer')}`. 실패면 사유를 보이고 끝(아무것도 안 바뀜).
   - ② "컨펌까지"를 골랐고 응답 `new_stage === 'CONFIRM'` 일 때만 `approve()`(아래 4).
   - ③ 어느 경우든 **도면 탭에 머문다**: `location.href = /erp/drawing-workbench/<id>?tab=timeline`(C14).
4. `approve()` — 고객 OK 시트 ②와 바의 `[data-customer-approve]`(확인창 "고객 컨펌을 승인하고 생산으로 넘길까요? 생산팀에 알림이 가요.") 둘이 같이 쓴다. `POST /api/orders/<id>/quest/approve {idempotency_key: <이번 클릭 난수>}` 응답 판정:
   - `success && (auto_transitioned || next_stage)` → "생산으로 넘겼어요".
   - `success && all_approved === false` → "승인 기록됨 · 남은 팀: {missing_teams}"(옛 팀 모드 quest).
   - 409 `code === 'ALREADY_TRANSITIONED'` → **성공으로 다룬다**("이미 생산으로 넘어갔어요").
   - 그 밖 실패 → "도면은 확정했어요. 고객 컨펌은 못 했어요 — {사유}. 도면 탭의 [고객 컨펌하고 생산으로]로 다시 할 수 있어요."
5. 관리자 뚫기(`FomsAdminOverride.retry`)는 붙이지 않는다 — 도면 탭의 확정·컨펌은 정식 경로만.

인라인 스크립트에서 바뀌는 것(모두 소폭): `submitRevision` 본문 두 값(typeof 가드) · `confirmReceipt` 함수와 등록 삭제(새 JS 로 이전) · `cancelTransfer` 확인창 문구 분기(§3.4).

---

## 4. 서버 변경 — 새 엔드포인트 0

### 4.1 수정요청 선택 필드(출처 · 받은 경로)

- 본문에 선택 키 두 개: `source`(`"customer"`·`"sales"`) · `received_via`(`"phone"`·`"kakao"`·`"store"`).
- 새 모듈 `foms/services/orders/drawing_revision_source.py`(약 90줄):
  - `parse_revision_source(data) -> tuple[dict, str | None]` — 키가 없거나 `null` 이면 `({}, None)`(지금 화면·태블릿·대시보드는 안 보냄 → 지금과 같은 저장). 값이 목록 밖이면 `({}, "INVALID_REVISION_SOURCE")`. `source="sales"` 면 `received_via` 는 버린다.
  - `revision_source_tag(entry, round_no) -> str` — `source == "customer"` 면 "고객 요청 · N차 · 카톡 답장"(받은 경로 없으면 생략), 아니면 `""`. 옛 항목(키 없음) = 영업.
  - `notification_title(fields)` — 고객 요청이면 `"고객 요청 · 도면 수정"`, 아니면 지금 `"도면 수정 요청"`. 메시지 앞머리 `"[고객 요청 · 카톡 답장] "`.
  - `attach_customer_ok(sd, body)` — 4.2 용.
- 라우트(`erp_orders_revision.py`, 기준선 파일이지만 줄 수를 늘리지 않게 도우미만 부른다):
  - files 계약 검사 바로 뒤(`:80`, 앵커 `INVALID_REVISION_FILE` 반환 다음, **행 잠금·쓰기 전**)에 `source_fields, source_err = parse_revision_source(data)` → 오류면 `400 {'success': False, 'code': 'INVALID_REVISION_SOURCE', 'message': '요청 출처 값이 올바르지 않습니다.', 'error': 'INVALID_REVISION_SOURCE'}`(M5 와 같은 모양).
  - 이력 항목(`:136-150`, 앵커 `'action': 'REQUEST_REVISION'`)에 `**source_fields`. M16·잠금·버전 +1·상태 가드는 순서 그대로.
  - 알림 제목·메시지(`:170-177`)만 `notification_title` 로. 알림 종류 `DRAWING_REVISION`·수신팀·`interrupt` 등급은 그대로.
- 수정요청 취소는 요청 항목을 통째로 보존하므로 새 필드도 남는다(코드 변경 없음).

### 4.2 수령 확정 선택 필드(고객 OK 경로 · 메모)

- 본문에 선택 키: `customer_ok`(bool) · `customer_ok_via`(`phone`·`kakao`·`store`) · `customer_ok_note`(문자열, 200자 자름).
- **라우트 파일(495줄)은 한 줄도 늘리지 않는다.** 라우트는 이미 본문을 `write_receipt_structured(..., body=data)` 로 넘긴다(`erp_orders_draftsman.py:437-438`). `drawing_receipt_command.write_receipt_structured`(`:91-117`)가 `final_sd = copy.deepcopy(s_data)` 직후 `attach_customer_ok(final_sd, body)` 를 불러 **마지막 `CONFIRM_RECEIPT` 이력 항목**에 `customer_ok: {"confirmed_by_customer": bool, "via": ..., "note": ...}` 를 붙인다. 쓰기 자리(REV-99 CANONICAL)는 그대로.
- 값 검증은 너그럽게: 목록 밖 `via` 는 버리고(경고 로그 1줄), 메모는 문자열이 아니면 버린다(설명용 값으로 확정 자체를 막지 않는다).
- 멱등 해시(`receipt_request_hash(body)`)는 본문이 바뀌면 달라진다 — 같은 본문 재시도만 같은 요청(지금과 같은 규칙).

### 4.3 회차 하나의 함수 · 알림톡 `#{문서종류}` 회차 이름

**회차 함수**(`drawing_customer_send.py`, S1a 에서 만든다) — 화면의 모든 "N차"와 고객 이름이 이 함수 하나를 쓴다.

`drawing_round_info(sd) -> RoundInfo(round, round_at, transfer_count, is_append, revisions_before)`
- `transfer_count` = 이력의 `TRANSFER` 수. `round_at` = 마지막 `TRANSFER` 의 `transferred_at`(없으면 `at`, 전달이 없으면 `""`).
- `revisions_before` = 마지막 `TRANSFER` **앞에 있는** `REQUEST_REVISION` 수(취소된 요청은 이력에서 빠져 있으므로 자동 제외, §2.5).
- `round` = 전달이 없으면 0, 있으면 **1 + `revisions_before`** (Q2 추천안 — "수정요청으로 고쳐 온 횟수 + 1"). 수정요청 없이 더 올린 전달(APPEND·REPLACE)은 같은 회차의 추가 전달이다.
- `is_append` = 마지막 TRANSFER 와 그 앞 TRANSFER 사이에 수정요청이 없음(화면 "1차 추가 전달 도착 11:40").
- Q2 가 "전달 횟수"(다른 선택)로 정해지면 `round = transfer_count` 한 줄만 바뀐다.

**고객 이름** `share_doc_label(sd, kind) -> str`
- 환경변수 스위치 `FOMS_SHARE_ROUND_DOC_LABEL`: `"1"` 일 때만 회차 이름, **없거나 다른 값이면 지금 고정 표 그대로**(배포 없이 되돌리기 — Railway `web` env, `variables --set` 은 재배포를 안 걸므로 재배포까지 한 번).
- 켜짐: `drawing` — `round ≤ 1` → `"도면"`, `round ≥ 2` → `"수정 도면(N차)"`. `bundle` — `round ≤ 1` → `"도면·계약서"`, `round ≥ 2` → `"수정 도면(N차)·계약서"`. `estimate` → `"견적서"`. 모르는 종류 `"문서"`. (모양은 G0 의 템플릿 원문 확인으로 확정 — 조사·버튼 이름에 변수가 들어가거나 길이 제한이 있으면 "2차 수정 도면" 등으로 이 함수 한 곳만 바꾼다.)
- `share.py:1399` 를 `share_doc_label(order.structured_data, kind)` 로, 회사 문자 본문 `:1208` 의 `kind_label` 도 같은 함수로. 내 폰 문자 본문은 자동.
- **적용 범위**: 도면 탭뿐 아니라 ERP 주문 화면 발송에도 같은 값(기본안 §9 — 같은 링크가 같은 현재 도면을 보여 주므로 이름도 같아야 맞다).
- 통합 템플릿(버튼 2개)은 변수가 없어 그대로. 시트 미리보기가 이를 알린다(§3.5 가).
- 공유 화면 제목(Q3 "예"면): `view_shared_order`(`share.py:476-491`)가 `share_round_label`(`round ≥ 2` 면 "2차", 아니면 "", 스위치를 따른다)을 넘긴다(S1). 템플릿 `share_view.html:11,18`·`share_bundle_view.html:11,19` 는 S3 가 고친다("2차 도면 확인").

### 4.4 영업→고객 상태 읽기 모델(`drawing_customer_send.py`)

**발송 이벤트 표지**(S1, `share.py` 두 발송 라우트 — 각 선점 이벤트 payload 한 줄):
```
payload={'share_id': row.id, 'kind': row.kind, 'status': 'in_flight', 'sent_by': actor_user_id,
         **send_event_tags(order.structured_data, request_body), **pair_ids}   # 알림톡만 pair_ids
```
- `send_event_tags` → `{'round_at': info.round_at, 'round': info.round, 'source_screen': 'drawing_tab' | None}`(`source_screen` 은 본문 값이 목록 안일 때만, 아니면 키를 안 넣는다).
- 알림톡은 `pair_ids`(`drawing_share_id`·`estimate_share_id`, 이미 `:1532` 에서 만든 값)를 이벤트에도 싣는다(지금은 감사 detail 에만).

`build_customer_send_view(db, order, sd, user, *, drawing_status, can_sales_side, can_confirm_receipt) -> dict`(약 180줄, 조회 2번):

1. `info = drawing_round_info(sd)`.
2. 조회 ① `OrderEvent` — `order_id == id`, `event_type in ('SHARE_ALIMTALK','SHARE_SMS')`, 최신 30건. `payload.kind in ('drawing','bundle')` 만.
   - **이번 회차 발송** = `payload.round_at == info.round_at`. 표지 없는 옛 이벤트만 `created_at ≥ round_at` 시각 비교로 대신한다.
   - `status == 'sent'` → 발송, `'failed'` → 실패(`error` 로 문구), `'in_flight'` → "보내는 중이었음(결과 모름)".
3. 조회 ② `OrderShareToken` — `order_id == id`, `kind in ('drawing','bundle')`, 최신 50건.
   - 이벤트와 짝: 이벤트의 `share_id` **와** `drawing_share_id` 둘 다. 표지 없는 옛 이벤트는 `created_by_user_id IS NULL` 이고 bundle 알림톡 이벤트 ±10초 안에 생긴 drawing 링크를 짝으로 본다.
   - **링크만 만듦** = 이번 회차 도착 뒤 발급 + 짝 이벤트 없음 + `revoked_at IS NULL` + `created_by_user_id IS NOT NULL`. 문구 "14:03 링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요)" — 내 폰 문자·링크 복사·카카오 SDK 공유를 다 덮는다.
   - 열림 합·마지막 열림은 §2.3 규칙(짝 도면 링크 열림도 센다 — 고객이 실제로 받은 링크다).
4. 고객 컨펌 가능 예측 `can_approve_after_confirm`: 지금 단계가 `DRAWING`·`CONFIRM` 이고 `quest_approve_allowed(user, order, 'CONFIRM', find_stage_quest_for_approve(sd, '고객컨펌', 'CONFIRM')[0])` — **승인 라우트와 같은 quest 고르기**(`quest.py:390`). 단계가 그 밖이면 False.
5. 통합 템플릿 여부 `bundle_both_template` = `ka._env('SOLAPI_TEMPLATE_SHARE_BOTH_ID_' + ka.resolve_brand(sd))` 가 비어 있지 않음. 접두 문자열은 `share.py:1409` `_BOTH_TEMPLATE_ENV_PREFIX` 와 같아야 한다(서비스가 api 모듈을 import 하지 않게 상수를 옮기지 않고, 테스트가 두 값의 같음을 단언).
6. 돌려주는 값(§4.5 약속). `empty_customer_send_view()` 는 같은 키를 빈 값으로(S1a).
- 성능: 상세 1회 렌더에 인덱스 조회 2번 추가(반복문 안 조회 없음). `python tools/perf/perf_scan.py --guard` 와 `tests/performance/test_perf_regression_guard.py` 로 확인. 목록(대시보드) 행에는 **추가 조회 없음**.
- 넓은 `except Exception` 금지(failopen 기준값 169 유지) — 좁은 예외만.

### 4.5 작업실 화면값 약속(S1a 가 빈 값으로, S1 이 채우고, S2·S3 가 읽는다)

상세(`erp_drawing_workbench_detail`, `workbench.py:941`) ctx(`:1235 ctx = dict(`)에 추가:

| 이름 | 뜻 |
|---|---|
| `customer_send.round` · `round_text` | §4.3 회차 · "2차"(0 이면 "") |
| `customer_send.arrived_at_text` · `arrival_label` | 지금 회차 마지막 전달 "MM-DD HH:MM"(KST) · "2차 도착" / "1차 추가 전달 도착" |
| `customer_send.can_send` | 영업 쪽 + 상태 `TRANSFERRED`·`CONFIRMED` + 현재 도면 1장 이상 |
| `customer_send.has_phone` · `phone_masked` | `ka.extract_valid_phone` 유무 · `ka._mask_phone` |
| `customer_send.sent_this_round` | 이번 회차 표지와 같은 성공 발송이 있나 |
| `customer_send.sent_text` | "오늘 11:52 알림톡으로 보냈고 링크가 1번 열렸어요" |
| `customer_send.link_only_text` | §4.4-3 문구 또는 "" |
| `customer_send.failed_text` | 이번 회차 마지막 시도가 실패면 "11:50 알림톡 실패 · 번호 오류" / network 면 "11:50 알림톡 결과 확인 안 됨" 또는 "" |
| `customer_send.views` · `last_viewed_text` | §2.3 규칙 |
| `customer_send.status_line` | 도면팀·PC 공용 한 줄 "영업 → 고객 · 2차 보냄 11:52 알림톡 · 링크 열림 1번" |
| `customer_send.turn_hint` | 영업 모바일 리본 부제(3.1) |
| `customer_send.steps` · `prev_summary` | 회차 기록 줄 항목 `[{label, sub, when, state: done\|now\|wait}]`(최대 4) · 이전 회차 한 줄 |
| `customer_send.doc_label_drawing` · `doc_label_bundle` · `bundle_both_template` | §4.3 값 · §4.4-5(시트 미리보기용) |
| `customer_send.can_customer_ok` | = 지금 `can_confirm_receipt` |
| `customer_send.can_approve_after_confirm` | §4.4-4 |
| `customer_send.bar` | 영업 쪽 버튼 목록(§3.0 을 서버가 한 번 판정) `[{"key": "send"\|"resend"\|"rev_customer"\|"rev_sales"\|"ok"\|"ok_no_customer"\|"rev_post"\|"approve_confirm"\|"production"\|"cancel_revision", "label", "tone", "slot": "main"\|"more"}]` |
| `customer_send.cancel_warning_text_pc` · `cancel_warning_text_mobile` | 이번 회차 표지와 같은 성공 발송이 있을 때만 §3.4 문구, 아니면 "" |

- `bar` 를 서버가 만드는 이유: 두 표면이 같은 조건을 **각자 Jinja 로** 쓰면 반드시 한쪽이 어긋난다(2차 M14 사례). 모바일·PC 템플릿은 이 목록을 **순회만** 하고 버튼 모양만 표면별이다(§3.1-3 · §3.2 같은 말).
- 이력 항목(`history`, `workbench.py:963-990`)·요청 항목(`revision_requests`)·스레드 항목(`_build_handoff_thread`, `:439-500`)에 `source_tag`(4.1 의 함수, 회차 = 그 요청 시점의 §4.3 `round` — 이력 순서대로 센다).
- 목록 행(`:763-812`)에 `latest_request_is_customer` 와 `round_text`(이미 읽은 이력에서만).
- **"N차" 통일(C15, 파이썬 쪽, 모두 §4.3 `round`)**: `:655`·`:1116`·`:323` 루프의 TRANSFER 세기를 `drawing_round_info` 로 · `:712` "v{N} 전달" → "{N}차 전달" · `:355` "최신 {N}차 전달본" → "{N}차 전달본" · 리본 "도면팀 {N}차 전달"(`:246,259`)은 숫자만 새 함수. 템플릿 쪽(목록 칩 `v{{ r.transfer_round }}` `:51`, 태블릿 `· v{{ r.transfer_round }}` `:137`)은 S3 가 `r.round_text` 로.

### 4.6 발송 흔적 쓰기 앞 행 잠금(§2.1 위험 정정)

- `share.py` 두 발송 라우트에서 `ka.record_share_history(...)`(`:1256` · `:1578`) 바로 앞에 `lock_order_row(db_session, order.id)`(`foms/services/orders/revision.py:241`, `populate_existing` + `FOR UPDATE`) 한 줄씩. `record_share_history` 안의 `refresh` 는 잠근 최신 행을 다시 읽을 뿐이라 그대로.
- 쓰기 자리는 그대로라 writer 인벤토리 수는 안 바뀐다(줄번호만). `record_share_history` 안을 고치지 않는 이유: 다른 알림톡 경로도 쓰는 공용 함수라 범위가 넓어진다.

---

## 5. 호환 점검표 C1~C21 — 지금 코드로 다시 판정

판정: **맞음** 그대로 됨 · **이번에 고침** 이 SPEC 범위 · **이미 고침** 1·2차로 운영에 있음 · **남음** 범위 밖으로 기록.

| ID | 목업이 가정한 것 | 지금 동작(근거) | 판정 | 이번에 할 일 |
|---|---|---|---|---|
| C1 | 확정 전에 보내기 | 발급·발송이 도면 상태를 안 본다(`share.py:808-871`·`:1466-1594`) | 맞음 | 도면 탭에서 부르기만 |
| C2 | 고객 링크는 지금 회차만 | 교체된 옛 도면을 뺀다(`share.py:175-222`, `:197`). 전달 이력 없는 도면 분류 첨부는 보인다(`:184-188`) | 이미 고침(대부분) · 남음(고아 첨부) | "N차" 제목은 Q3. 고아 첨부는 §10.3 |
| C3 | 같은 링크 다시 보내기 | 보낼 때마다 새 토큰, 원문 미저장(`order_share.py:163-198`) | 맞음(목업 문구 변경대로) | 예전 링크도 최신을 보인다는 안내만 |
| C4 | 고객 열람 횟수 | 링크마다 `view_count`·`last_viewed_at`, 누가 열었는지 구분 없음(`share.py:461`) | 이번에 고침 | 주문 단위 합산 + "링크 열림" 문구(4.4·2.3) |
| C5 | "고객 요청" 표시 | 수정요청 항목에 출처가 없다(`erp_orders_revision.py:136-150`) | 이번에 고침 | 선택 필드 `source`·`received_via`(4.1) |
| C6 | 고객 사진 첨부 | 참고 파일 첨부 + files 계약 M5(`erp_orders_revision.py:66-80`) | 맞음 | 그대로 |
| C7 | 수정요청 대상 도면 | 2장 이상이면 대상 필수 400(`:112-113`) | 맞음 | 모달 안내 문구만 서버와 맞춤 |
| C8 | 확정 뒤에도 고객 사진 남기 | 확정은 아무것도 안 지운다(`drawing_confirm_cleanup.py:277-290`) | 이미 고침(1차) | — |
| C9 | 도면팀 모바일 반영 체크 | 스레드 말풍선에 반영 체크(`workbench_mobile_handoff.html:231-257`) | 이미 고침(1차) | — |
| C10 | 도면팀이 고객 사진 보기 | 참고사진 썸네일 + 크게 보기(`workbench_mobile_handoff.html:206-229`, `workbench.py:388-397`) | 이미 고침(1차 M12·2b) | — |
| C11 | 고객에게 보낸 도면의 전달 취소 | 최신 TRANSFER 를 빼고 직전 도면으로 복원(`erp_orders_drawing.py:545-577`), 취소 표시는 이력에 안 남음. 영업 알림은 이미 감(`:674-704`). 확인창에 발송 여부 없음(`workbench_detail_body.html:2796`) | 이번에 고침 | 발송 표지로 이번 회차 판정 + 표면별 경고(3.4) — 막지 않음(Q4) |
| C12 | 확정 + 고객 컨펌 한 번에 | 합친 API 없음. 권한 다름. 컨펌 게이트는 도면 `CONFIRMED` 요구(`quest.py:374-386`) | 이번에 고침 | 두 요청을 차례로 + 실패·확정만이면 바에 [고객 컨펌하고 생산으로](3.0·3.6) |
| C13 | 확정 뒤 고객이 또 수정 | `CONFIRMED` 에서 수정요청 허용(`erp_orders_revision.py:131`), 생산 변경 알림(`:185-190`) | 맞음 | 시트에 경고 줄 |
| C14 | 확정 뒤 도면 탭에 머물기 | 대시보드로 이동(`workbench_detail_body.html:2788`) | 이번에 고침 | 도면 탭 주소로 + 컨펌은 도면 탭 바에서 |
| C15 | 회차 번호 | TRANSFER 수, 수정요청 없는 추가 전달도 셈, 취소하면 준다. 표기 섞임 | 이번에 고침 | 회차 함수 하나(4.3, Q2) + "N차" 통일 |
| C16 | 알림톡에 회차 넣기 | `#{문서종류}` 는 고정 표(`share.py:1399`, 표 `:1004`). 운영 묶음 알림톡은 변수 없는 통합 템플릿 | 이번에 고침 | 회차 이름 함수 + 스위치(4.3) · 묶음은 미리보기로 알림 |
| C17 | 도면팀에 고객 요청 알림 | 확인해야 닫히는 알림창(`erp_orders_revision.py:210-224`) | 이번에 고침(제목만) | 제목·메시지 앞머리 "고객 요청"(4.1) |
| C18 | 도면팀이 영업→고객 상태 보기 | 없음(`workbench.py:1235-1296` ctx 에 없음) | 이번에 고침 | 읽기 전용 한 줄(3.3·3.4) |
| C19 | PC 에도 같은 버튼 | 영업 PC: 수정 요청·수령 확정·수정요청 취소(`workbench_detail_body.html:1500-1520`) | 이번에 고침 | 서버가 만든 버튼 목록 하나를 두 표면이 순회 · 도면팀 PC 긴급 호출은 Q5 |
| C20 | 말풍선 좌우 | 동작 기준 고정(`workbench.py:468-473`) | 맞음 | 변경 없음 |
| C21 | 고객 컨펌 승인 가드 | 단계 CONFIRM 이면 도면 `CONFIRMED` 아니면 409(`quest.py:374-386`) | 이미 고침(2a-2) | 새 흐름(시트 ②·바 `approve_confirm`)이 이 게이트를 그대로 탄다(테스트로 고정) |

---

## 6. 핫파일 · 래칫 · 핀 · 인벤토리

| 파일 | 지금 | 제약 | 갈래 | 주의 |
|---|---|---|---|---|
| `foms/api/drawing/erp_orders_draftsman.py` | 495줄 | py 500(기준선 밖) | — | **손대지 않는다**(4.2 는 도우미 쪽) |
| `foms/api/drawing/erp_orders_revision.py` | 596줄 | 기준선(크기 자유) | S1 | +약 8줄 |
| `foms/services/orders/drawing_receipt_command.py` | 137줄 | py 500 | S1 | +2줄 |
| `foms/api/share.py` | 1629줄 | 기준선 | S1 | +약 10줄(표지 2 · pair_ids 1 · 잠금 2 · 이름 2 · `share_round_label` 3) |
| `foms/web/drawing/workbench.py` | 1299줄 | 기준선 | S1a·S1 | +약 30줄. 판정 본문은 새 모듈로 |
| 새 `foms/services/orders/drawing_revision_source.py` | — | py 500 | S1 | 약 90줄 |
| 새 `foms/services/orders/drawing_customer_send.py` | — | py 500 | S1a·S1 | 약 260줄. 넘으면 문구 조립을 `drawing_customer_send_text.py` 로 |
| `foms/services/orders/quest_approve_authz.py` · `quest_transition_service.py` | 353줄 · — | py 500 | — | 읽기만(함수 import) |
| `templates/drawing/partials/workbench_detail_body.html` | 3051줄 | 인라인 스크립트 더 키우지 않기 · 인라인 스타일 금지 | S2 | 모달 2개(+Q5-④ 1개) · 결정 바 순회로 교체 · 인라인 스크립트는 순감소 |
| `templates/drawing/partials/workbench_mobile_handoff.html` | 332줄 | `DETAIL_TOP_BLOCKS = 5` · `LIST_TOP_BLOCKS = 3` | S3 | 새 `<section>`·`<details>` 금지 |
| `templates/orders/share_view.html` · `share_bundle_view.html` | — | 핀 연쇄 | S3 | 제목 + 핀을 한 갈래에서 |
| 새 `static/js/foms/drawing-customer-send.js` · `drawing-customer-ok.js` | — | js 300 | S2 | 각 약 240~250줄 |
| `static/js/foms/drawing-handoff.js` | 166줄 | js 300 | — | **손대지 않는다** |
| `static/css/components/foms-drawing-mobile.css` | 814줄 | CSS 래칫 없음 · 핀 연쇄 | S3 | +약 80줄 |

**핀**(같은 날 같은 글자 재사용 금지 — 구현일 날짜 + 다음 글자. 오늘 쓴 글자는 `g`)

| 자산 | 지금 | 가리키는 곳 | 갈래 |
|---|---|---|---|
| `css/components/foms-drawing-mobile.css` | `20260929g` | `static/css/foundation/foms-mobile-surfaces.css:24`(@import) · `templates/orders/share_view.html:12` · `templates/orders/share_bundle_view.html:12` · 자물쇠 `ASSET_PIN_LOCK`(`tests/domains/test_drawing_mobile_asset_pin_freshness.py:118-121`) | S3 |
| 부모 `css/foundation/foms-mobile-surfaces.css` | `20260929g` | `templates/partials/shared/layout_head.html:239` — 자식만 올리면 기기에 안 닿는다(`test_parent_bundle_pin_moves_with_its_child`) | S3 |
| 새 `js/foms/drawing-customer-send.js` · `drawing-customer-ok.js` | — | `workbench_detail_body.html` **`{% if erp_mobile_v2_enabled %}`(`:3049`) 블록 밖** `?v=<구현일>a` defer | S2 |
| `js/foms/drawing-handoff.js` | `20260929g` | `workbench_detail_body.html:3050` | 변경 없음 |

**인벤토리·기준값**(**S1 갈래에서 refresh·커밋, 마무리에서 재확인** — 파이썬을 고치는 갈래는 S1a·S1 뿐)
- failopen `_SWALLOW_BASELINE = 169`(`tests/domains/test_failopen_inventory.py:48`, 정확히 같아야 함) — 새 코드에 넓은 `except Exception` 금지. JS 의 회수 호출 실패 무시는 파이썬 인벤토리 밖.
- order_mutation_writer 인벤토리 `{total: 73, external: 24}`(`docs/harness/foms_order_mutation_writer_inventory.json:6-7`) — 새 `structured_data` 쓰기 자리 없음. 줄번호만 밀림.
- state_writer · audit_coverage · api_error_leak · orm_bypass 인벤토리 — 줄번호만 밀림. **S1 커밋 전 `python tools/harness/refresh_inventories.py`**(줄번호만 바뀐 것은 되쓰지 않으니 필요하면 `tools/harness/*_scan.py` 직접 실행 — 메모리 "미커밋 인벤토리가 smoke 를 속인다"). S2·S3 는 인벤토리를 건드리지 않는다. 마무리에서 합친 트리로 한 번 더 돌려 변화가 없음을 확인.
- 파일 크기 래칫 `tests/harness/test_file_size_ratchet.py`(py 500 · js 300).

---

## 7. 테스트 · 완료 기준

모든 명령은 `cd C:/tmp/foms-s-s0929-115959 && …`(갈래 워크트리면 그 경로). 종료 코드는 파이프 뒤에서 읽지 않는다(`> out.txt 2>&1; echo EXIT=$?`).

### 7.1 새 테스트(갈래별)

**S1a**
- `tests/domains/test_drawing_round_info.py` — 전달 0 → round 0 / 1번 전달 → 1 / **수정요청 없이 두 번 전달(APPEND) → round 1, `is_append`** / 전달 → 수정요청 → 전달 → 2 / 수정요청 취소 뒤 전달 → 1(취소된 요청은 안 셈) / 전달 취소 → 앞 전달의 `round_at` 로 돌아감.
- 기존 상세 렌더 테스트 전부 초록(빈 `customer_send` 로 500 없음).

**S1**
- `tests/domains/test_drawing_revision_source.py` — ① `source=customer, received_via=kakao` 저장 ② 키 없음 = 지금과 같은 항목 ③ 목록 밖 값 400 `INVALID_REVISION_SOURCE` + **아무것도 안 씀** ④ `source=sales` 면 `received_via` 버림 ⑤ 알림 제목 "고객 요청 · 도면 수정"·종류 `DRAWING_REVISION` 그대로 ⑥ files 계약(M5) 400 그대로 ⑦ RETURNED 에서 두 번째 요청 400 그대로 ⑧ 취소 뒤 `REVISION_CANCELLED.request.source` 보존 ⑨ 음성 대조: 도우미를 빼면 ①·③ 빨강.
- `tests/domains/test_drawing_receipt_customer_ok.py` — ① `customer_ok_*` 가 마지막 `CONFIRM_RECEIPT` 에 붙음 ② 빈 본문 = 지금과 같음 ③ 목록 밖 `via` 는 버리고 확정 200 ④ 확정 → 영업 컨펌 승인 → `PRODUCTION` ⑤ **C21 고정**: RETURNED 주문에 컨펌 승인 409 ⑥ 컨펌 권한 없는 사용자: 확정 200 → 승인 403 → 주문 `CONFIRM`·도면 `CONFIRMED` ⑦ 확정 뒤 재수정 주문의 재확정은 `can_approve_after_confirm=False` ⑧ **확정만 → 화면 `bar` 에 `approve_confirm` → 승인 → `PRODUCTION`** ⑨ 옛 팀 모드 CONFIRM quest: 승인 `success=true`·`all_approved=false` ⑩ 같은 승인 두 번 → 둘째 409 `ALREADY_TRANSITIONED` ⑪ 예측이 `find_stage_quest_for_approve` 와 같은 quest 를 고름(같은 단계 quest 둘 — COMPLETED + OPEN — 모집단 안 음성 대조).
- `tests/domains/test_share_round_doc_label.py` — 스위치 꺼짐 = 지금 고정 표(모든 경우) · 켜짐: `share_doc_label` 표(round 0·1·2·3 × drawing·bundle·estimate) · **수정요청 없는 추가 전달 주문은 "도면"** · send-alimtalk 변수 `#{문서종류}` = "수정 도면(2차)" · send-sms 본문 · create `sms_text` · 통합 템플릿 env 켜진 bundle 은 변수 dict 에 `#{문서종류}` 없음(그대로) · 기존 `test_order_share_alimtalk.py:119,151` 초록 · 접두 상수 같음(`_BOTH_TEMPLATE_ENV_PREFIX`).
- `tests/domains/test_drawing_customer_send_status.py` — 발송 없음 / 이번 회차 알림톡 성공 → `sent_this_round` / **보냄 → 전달 취소 → 앞 회차는 보냄 아님**(표지 비교 — 음성 대조: 같은 주문에서 표지를 떼고 시각 비교만 하면 빨강) / 앞 회차에도 보냈으면 취소 뒤 그 발송이 다시 이번 회차 / 표지 없는 옛 이벤트는 시각 비교 / 실패·network·보내는 중 / `estimate` 무시, bundle 셈 / **통합 env 켜진 묶음 알림톡: 짝 도면 링크가 "링크만 만듦"에 안 잡히고 열림은 셈** / 옛 이벤트 짝 짓기(±10초·`created_by` 없음) / **create → 503 → 회수된 링크: `link_only_text == ""`** / 링크만 만듦(회수 안 된 직원 발급) / `cancel_warning_text_*` 는 이번 회차 발송에만 / 이벤트 payload 에 `round_at`·`round`·`source_screen`·`drawing_share_id` / 컨펌 권한 예측(ADMIN·SALES·DRAWING 팀) / 조회 수 2번(쿼리 계수 픽스처).
- `tests/domains/test_share_send_row_lock.py`(정적+동작) — 두 발송 라우트에서 `lock_order_row` 가 `record_share_history` 앞에 있음(소스 순서) · 발송 뒤 `alimtalk_share` 기록과 같은 순간 커밋된 이력 항목이 둘 다 남음(SQLite 레인은 순서 단언만, PG 레인에서 동작).

**S2**
- `tests/domains/test_drawing_tab_send_pc.py`(렌더) — 영업: TRANSFERRED·안 보냄에 [고객에게 보내기]·[확정 (고객 답 없이)]·[내 의견으로 수정요청] / 보냄 뒤 [다시 보내기]·[고객이 고쳐 달래요]·[고객 OK · 확정] / RETURNED 에 보내기 없음 / CONFIRMED·CONFIRM 단계·권한 있음에 [고객 컨펌하고 생산으로], 권한 없음에 [생산 현황 보기] / 도면팀 계정에는 영업 버튼 0개·상태 한 줄 있음 / `#btn-confirm-receipt`·`#btn-cancel-revision` id 가 **한 번씩만** 있음(옛 블록 제거 확인) / `#btn-cancel-transfer` 의 경고 문구는 보낸 회차에만 · PC 문구에 "긴급 호출" 없음 / `#dwCustomerOkModal[data-can-approve="false"]` 면 "컨펌까지" 라디오 없음 · 있으면 "생산팀에 알림이 가요" / 보내기 시트 칩 "도면+계약서" · `data-bundle-both-template` / `#btn-confirm-receipt` 가 모달을 열고 인라인 `confirmReceipt` 등록이 없음.
- `tests/domains/test_drawing_customer_js_contract.py`(정적) — 두 새 JS: `node --check` · jQuery 없음 · 모든 `fetch` 가 try/catch 안 · `data.success` 검증 · 토큰을 저장소에 안 씀 · 발송 전 실패 상태(400·404·409·410·503) 분기에 `/api/share/revoke/` 호출 · `'network'` 분기에 회수 없음·버튼 잠금 유지 · 승인 결과 판정에 `auto_transitioned`·`ALREADY_TRANSITIONED` · 끝 이동 주소가 `/erp/drawing-workbench/` · **C14: `/erp/dashboard?focus_order=` 와 `open_quest` 가 두 새 JS 와 인라인 스크립트 본문에 없음**(템플릿 전체가 아니라 — `production` 링크의 같은 문자열 오탐 방지) · 인라인 `submitRevision` 에 `typeof window.fomsDrawingRevisionExtras === 'function'`.
- `tests/performance/test_page_local_defer_contract.py` — 두 새 파일 defer + v2 조건 블록 밖.

**S3**
- `tests/domains/test_drawing_tab_send_mobile.py`(렌더) — 상태별 바 버튼(§3.0) · **PC·모바일 파리티**: 같은 주문·같은 사용자로 두 표면의 영업 버튼 키 목록이 같다 · 관리자 겸 도면 담당: 바 버튼 3개 + [더 보기] · 회차 기록 줄이 주문 요약 칸 안, 블록 수 그대로 · 스레드 "고객 요청 · 1차 · 카톡 답장" · 목록 카드 "고객 요청" 칩 · "vN" 표기 0건 · 도면팀 상태 한 줄 · 공유 화면 제목 "2차 도면 확인"(스위치 켜짐·round 2)·"도면 확인"(그 밖).
- 기존 갱신: `test_drawing_mobile_asset_pin_freshness.py`(핀·자물쇠) · `test_drawing_batch2_mobile_ui.py`(바 버튼 기대값이 바뀌는 곳만) · `test_drawing_mobile_back_to_workbench.py`(블록 수 **바꾸지 않음**).

### 7.2 공통 게이트(갈래마다, 마무리에서 한 번 더 — S1a 가 합쳐진 뒤라 모든 갈래에서 돌릴 수 있다)

```
python -c "import app; print('APP_OK')"                                          # APP_OK
python tools/harness/refresh_inventories.py > inv.txt 2>&1; echo EXIT=$?         # 0 — S1 갈래에서만 커밋, 다른 갈래는 변화 없음 확인
PYTHONIOENCODING=utf-8 python -m pytest -q -p no:cacheprovider \
  tests/domains/test_drawing_round_info.py \
  tests/domains/test_drawing_revision_source.py tests/domains/test_drawing_receipt_customer_ok.py \
  tests/domains/test_share_round_doc_label.py tests/domains/test_drawing_customer_send_status.py \
  tests/domains/test_share_send_row_lock.py \
  tests/domains/test_drawing_tab_send_pc.py tests/domains/test_drawing_customer_js_contract.py \
  tests/domains/test_drawing_tab_send_mobile.py tests/performance/test_page_local_defer_contract.py \
  tests/domains/test_bugrepro_c21_confirm_quest_while_returned.py tests/domains/test_confirm_drawing_gate.py \
  tests/domains/test_drawing_revision_files_contract.py tests/domains/test_drawing_revision_cancel.py \
  tests/domains/test_order_share_alimtalk.py tests/domains/test_order_share_sms.py tests/domains/test_order_share_api.py \
  tests/domains/test_share_hides_superseded_drawings.py tests/domains/test_drawing_mobile_back_to_workbench.py \
  tests/domains/test_drawing_batch2_mobile_ui.py tests/domains/test_drawing_mobile_asset_pin_freshness.py \
  tests/domains/test_drawing_receipt_sales_owner.py tests/domains/test_confirm_to_production_flow.py \
  > focus.txt 2>&1; echo EXIT=$?                                                 # 0 (갈래에 아직 없는 파일은 빼고)
PYTHONIOENCODING=utf-8 python -m pytest -q -p no:cacheprovider \
  tests/domains/test_failopen_inventory.py tests/domains/test_rev_99.py tests/domains/test_state_guard.py \
  tests/harness/test_file_size_ratchet.py > gate.txt 2>&1; echo EXIT=$?          # 0
node --check static/js/foms/drawing-customer-send.js; echo EXIT=$?               # 0
node --check static/js/foms/drawing-customer-ok.js; echo EXIT=$?                 # 0
python tools/perf/perf_scan.py --guard > perf.txt 2>&1; echo EXIT=$?              # 0
python -m pytest -q --ignore=tests/visual --ignore=tests/harness -p no:playwright \
  -n auto --dist loadfile > lane.txt 2>&1; echo EXIT=$?                          # 0 (CI 본 레인)
python -m pytest tests/harness -q > harness.txt 2>&1; echo EXIT=$?                # 0 (순서대로, xdist 금지)
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 > smoke.txt 2>&1; echo EXIT=$?   # 0 (push 직전)
```

### 7.3 스테이징 확인(deploy push · CI green 뒤, `claude_master` — 스테이징은 자유)

- 가상 주문 `CLAUDE-TEST-` 하나(도면 2장 전달 · **고객 번호 = 사용자가 정해 준 번호**, 실고객 번호 금지). 스테이징에 솔라피 설정이 없으면 503 `not_configured` 문구가 시트에 뜨고 **방금 만든 링크가 회수되는 것**(발급 이력 `revoked`)과 상태 줄에 "링크만 만듦"이 **안 뜨는 것**까지 확인.
- 흐름: ① 영업 폰(390px) 1차 도착 → [고객에게 보내기] → 상태 줄·회차 기록 ② 고객 링크 열기 → 링크 열림 1번 ③ [고객이 고쳐 달래요](카톡 답장 · 사진 1장 · 2번 도면) → 도면팀 폰에 "고객 요청" 알림창·스레드 ④ 도면팀 반영 체크 → 수정본 전달 → 영업 보내기 ⑤ 도면팀 [전달 취소] → 경고(모바일 문구) → 취소 안 함 ⑥ 영업 [고객 OK · 확정] "확정만" → 바에 [고객 컨펌하고 생산으로] → 눌러 생산 · 도면 탭에 머묾 ⑦ 수정요청 없이 추가 전달한 주문은 "2차"가 아니라 "1차 추가 전달"로 보임 ⑧ 컨펌 권한 없는 계정(없으면 생략, 테스트로 대신)으로 "확정만" 경로.
- PC(1280px) 같은 주문에서 결정 바 버튼이 모바일과 같은지 · PC 전달 취소 문구에 "긴급 호출"이 없는지.

### 7.4 390px 실화면 캡처(gstack browse, 상태 단언은 촬영 **전에**)

영업: 1차 도착 바 · 보내기 시트(알림톡/회사 문자/내 폰 문자 · 도면+계약서 선택 시 "버튼 2개" 미리보기) · 다시 보내기 경고 · 보낸 뒤 바+회차 기록 · 고객 요청 시트 · 고객 OK 시트(권한 있음/없음) · 확정만 뒤 바([고객 컨펌하고 생산으로]) · 관리자 계정 [더 보기]. 도면팀: 목록 카드 "고객 요청" · 요청 스레드+상태 한 줄 · 전달 취소 경고. PC 1280px: 영업·도면팀 결정 바. 실데이터 시드(가상 주문)로.

### 7.5 첫 운영 발송 확인(Q6 — 사용자 명시 요청 1건당 1회)

- 배포 직후 운영 `web` env `FOMS_SHARE_ROUND_DOC_LABEL` 은 **꺼 둔 채** 올린다(고객 이름은 지금과 같음, 나머지 기능만 켜짐).
- 사용자가 요청하면: env 켜기 + 재배포 → 운영 `CLAUDE-TEST-` 주문(2차 상태, 사용자가 정해 준 번호)으로 알림톡 **1회** → `mcp__solapi__list_messages`(읽기)로 문서 이름·버튼 이름 확인 → 이상하면 env 끄기 + 재배포(코드 배포 없음).
- 이 확인 전에는 운영 고객이 새 이름의 첫 수신자가 되지 않는다.

### 7.6 출시 뒤 측정(1주 뒤, 운영 읽기 · 사용자 요청 시)

셀 것: 도면 탭 발송 수(`payload.source_screen = 'drawing_tab'`, 알림톡·문자별) · 그 실패 수(`status='failed'`, `error` 별) · 고객 요청 수(`REQUEST_REVISION.source = 'customer'`) · 확정 뒤 같은 분 안에 생산까지 간 주문 수(`CONFIRM_RECEIPT.customer_ok` + quest 완료 시각) · "링크만 만듦" 주문 수. 결과를 `docs/AI_CHANGELOG.md` 에.

### 7.7 완료 선언 조건

push 뒤 CI green 까지(`ci_watch` 는 런 생성 뒤 확인) · 스테이징 7.3 · 캡처 7.4 · `docs/AI_STATUS.md` 상단(4,000자 예산)·`docs/AI_CHANGELOG.md` · `docs/harness/policy/DECISIONS.md`(출처 필드 엄격/확정 필드 너그럽게 · 회차 규칙(Q2) · 문서 이름 스위치 · 전달 취소 경고만 · 내 폰 문자 기록 규칙 · "보냄"은 벤더 접수 · 발송 흔적 쓰기 행 잠금) 갱신. production 반영은 사용자 명시 요청 뒤 `python tools/harness/promote_own_to_production.py --session-id <id>`("deploy 푸쉬"는 production 을 포함하지 않는다).

---

## 8. 사용자 질문 (5개 + 요청 1개)

> **사용자 결정(2026-09-29, 설계서 승인)** — 이 절이 아래 질문·기본안보다 우선한다.
> - Q1 내 폰 문자·링크 복사·카톡 공유는 '보냄'으로 치지 않는다 → '링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요)'.
> - Q2 회차 = 1 + 마지막 전달 앞의 수정요청 수(`drawing_round_info`). 요청 없는 추가 전달은 같은 회차의 '추가 전달'. 도면 탭 N차 표기와 고객 이름이 이 함수 하나를 쓴다.
> - Q3 고객 링크 화면 제목은 2차부터 'N차 도면 확인'(1차는 지금처럼).
> - Q4 고객에게 보낸 회차의 전달 취소는 경고만(막지 않음), 영업에게는 지금처럼 취소 알림.
> - **Q5 목업의 네 가지를 모두 넣는다**: ① 도면팀 PC 결정 바 긴급 호출(PC 에서 뜨는 창 — 모바일 셸 밖) ② 보내기 창 '번호 바꾸기'(이번 발송만 다른 번호 + 선택 시 주문 고객 번호도 저장) ③ 도면팀이 확인하기 전 영업의 '요청 고치기'(마지막 수정요청 내용·사진·출처 수정) ④ 전달 취소 창의 '영업에게 먼저 알리기(긴급 호출)'(PC·모바일).
> - Q6 알림톡 새 문서 이름은 `FOMS_SHARE_ROUND_DOC_LABEL` 기본 꺼짐으로 배포 → 운영 반영 뒤 사용자가 준 번호로 CLAUDE-TEST- 주문에 1회 발송·솔라피 발송 내역 확인 → 켠다(번호는 저장소·문서에 적지 않는다).

**Q1. 영업이 "내 폰 문자"(또는 링크 복사·카톡 공유)로 보낸 것도 "고객에게 보냄"으로 칠까요?**
- 추천: **치지 않는다.** 대신 "링크를 만들었어요(직접 보낸 경우 보냈는지는 기록되지 않아요)"라고 따로 보여 준다.
- 이유: 문자 앱을 열어 줄 뿐이라 영업이 실제로 보냈는지 서버는 모른다. 보냈다고 적었다가 안 보냈으면 모두 "고객이 봤겠지" 하고 기다린다. 알림톡·회사 문자는 회사가 직접 보내 기록된다. 다른 선택: "친다" — 링크를 만든 순간을 보낸 것으로 기록.

**Q2. 고객에게 "수정 도면(2차)"라고 부를 때 "2차"는 무엇을 셀까요?**
- 추천: **고객(또는 영업)이 고쳐 달라고 한 횟수 + 1.** 도면팀이 수정요청 없이 파일을 더 올린 것은 같은 회차의 "추가 전달"로 본다. 도면 탭 안의 "N차" 표기도 같은 규칙 하나로 맞춘다.
- 이유: 지금 코드는 "전달한 횟수"를 센다. 그러면 고객이 고쳐 달라고 한 적이 없는데 첫 알림톡부터 "수정 도면(2차)"를 받을 수 있다(도면팀은 전달된 상태에서도 파일을 더 올릴 수 있다). 운영 규모는 "전달 이력 주문 192건 · 수정요청 역대 8건"이라, 여러 번 전달된 주문 대부분이 수정요청 없는 재전달일 수 있다. 원하시면 출시 전에 운영 읽기로 그런 주문 수를 한 번 셀 수 있다. 다른 선택: 전달 횟수를 그대로 센다(도면팀이 보는 "N차 전달"과 같아지지만 고객에게는 틀린 말이 될 수 있다).

**Q3. 고객이 링크를 열었을 때 맨 위 제목을 "도면 확인" 대신 "2차 도면 확인"처럼 회차를 보여 줄까요?**
- 추천: **보여 준다**(2차부터만, 이름 스위치를 따른다).
- 이유: 알림톡에 "수정 도면(2차)"라고 보냈는데 열어 보니 회차가 안 보이면 "고친 게 맞나?" 싶다. 다른 선택: 그대로 둔다.

**Q4. 영업이 이미 고객에게 보낸 도면을 도면팀이 "전달 취소"하려고 하면 어떻게 할까요?**
- 추천: **경고만 하고 막지는 않는다.** 한 번 더 묻고, 영업에게는 지금처럼 "도면 전달 취소" 알림이 간다.
- 이유: 잘못된 파일을 올렸을 때는 빨리 거둬야 한다. 막으면 영업이 올 때까지 틀린 도면이 고객에게 계속 보인다. 다른 선택: "막는다".

**Q5. 확인하신 목업에 있던 네 가지를 이번에 뺄까요?**
- ① 도면팀 PC 결정 바의 긴급 호출 ② 보내기 시트의 "번호 바꾸기" ③ 도면팀 수정 중 바의 "요청 고치기" ④ 전달 취소 시트의 "영업에게 먼저 알리기(긴급 호출)" 버튼.
- 추천: **①②③은 이번에 빼고 다음 묶음으로, ④는 모바일에만 넣는다.**
- 이유: ① 긴급 호출 창이 모바일 화면 안에만 있어서 PC 에서는 버튼을 달아도 창이 안 뜬다(창을 옮기는 일이 따로 필요). ② 번호 고치기를 도면 탭에 새로 만들면 주문 폼 잠금 규칙과 부딪힌다 — 지금은 "주문 화면에서 고쳐요" 링크로 간다. ③ 수정요청을 고치는 서버 기능이 없어 새로 만들어야 한다 — 지금은 "수정요청 취소 → 다시 요청"으로 된다. ④는 이미 있는 긴급 호출 버튼을 경고 창 안에 하나 더 두면 돼서 작다(PC 는 긴급 호출이 없으니 "영업에게 먼저 연락" 문구만). 다른 선택: 넷 다 넣는다(①③은 새 창·새 서버 기능이 필요해 이번 묶음이 커진다) / 넷 다 뺀다.

**Q6(요청). 배포 뒤 첫 운영 알림톡 확인을 테스트 주문으로 1번 해도 될까요?**
- 추천: **한다.** 새 문서 이름은 기본으로 꺼 둔 채 올리고, 말씀 주시면 운영의 `CLAUDE-TEST-` 주문으로 정해 주신 번호에 1번만 보내 솔라피 발송 내역에서 이름을 확인한 뒤 켠다.
- 이유: 스테이징에는 알림톡 설정이 없을 수 있어, 확인 없이 켜면 실제 고객이 새 이름의 첫 수신자가 된다. 필요한 것: 받을 휴대폰 번호 하나.

---

## 9. 기본안 (말씀이 없으면 이대로 간다)

- 새 엔드포인트 없음. 선택 필드는 수정요청 `source`·`received_via`, 수령 확정 `customer_ok`·`customer_ok_via`·`customer_ok_note`, 발송 본문 `source_screen` 만.
- 수정요청 출처 값이 틀리면 **400**(쓰기 전). 수령 확정의 고객 OK 값이 틀리면 **버리고 확정은 진행**.
- 옛 수정요청(출처 키 없음)은 영업 의견으로 본다. 운영 데이터 보정 없음.
- **(v1 Q2 → 기본안)** 알림톡 문서 이름은 ERP 주문 화면에서 보낼 때도 똑같이 바뀐다(서버 함수 하나 · 같은 링크가 같은 도면을 보여 주므로). 스위치로 켜고 끈다.
- 회차는 Q2 추천(수정요청 기준)으로 만든다.
- [고객에게 보내기]는 영업 쪽에게, 도면 상태 `TRANSFERRED`·`CONFIRMED` 이고 현재 도면이 있을 때만. `RETURNED` 에는 안 보인다.
- 고객 OK 시트의 기본 선택은 "고객 컨펌까지 끝내고 생산으로". 확정만 했거나 컨펌이 실패하면 도면 탭 바에 [고객 컨펌하고 생산으로].
- 확정·컨펌 뒤에는 도면 탭(타임라인)에 머문다.
- 전달 취소는 경고만(Q4), 문구는 표면별. 영업 알림은 지금 라우트 그대로.
- "N차" 표기 통일(목록 카드·태블릿 갤러리·전달 줄·도면 목록 설명).
- 보낸 뒤 모바일 바는 목업대로 버튼 3개(긴급 호출 빠짐). 관리자처럼 버튼이 넘치면 [더 보기].
- 알림톡 미리보기는 템플릿 원문을 베끼지 않고 "문서 이름"만, 통합 템플릿이면 그 사실만.
- 링크 열람 문구는 "링크 열림 N번"(직원 열람 포함 가능 안내).
- 발송 흔적 쓰기 앞에 행 잠금(§4.6).
- **되돌리기**: 새 키는 모두 추가 키라 옛 코드가 무시한다 → 문제가 생기면 이 묶음 커밋을 되돌리면 끝(데이터 보정 없음). 고객 이름만 되돌릴 때는 env `FOMS_SHARE_ROUND_DOC_LABEL` 끄기 + 재배포. 이미 "컨펌까지"로 생산에 넘어간 주문은 강제 단계 변경으로도 quest 가 COMPLETED 로 남는다(알려진 막다른 길) — 그래서 시트에 "생산팀에 알림이 가요"를 둔다.
- 결정은 구현 커밋에서 `docs/harness/policy/DECISIONS.md` 에 한 줄씩.

---

## 10. 확인 필요 (코드·실행으로 확인하지 못한 것)

1. **(G0 — S1 착수 전 게이트) 승인 템플릿 원문**: `#{문서종류}` 가 본문 어디에 어떤 조사와 붙는지, **버튼 이름에도 들어가는지**(목업 미리보기는 버튼을 "수정 도면(2차) 보기"로 그렸다 — 카카오 버튼 이름 14자 제한에 걸릴 수 있다), 변수 길이 제한. 확인: 솔라피 읽기 도구(`mcp__solapi__get_kakao_template`, 템플릿 id 는 Railway `web` env `SOLAPI_TEMPLATE_SHARE_ID_LAHOM/HAUD`). 결과를 이 칸에 적고 §4.3 이름 모양을 확정한다. 확인 전에는 S1 의 이름 함수를 합치지 않는다(다른 S1 부분은 진행 가능).
2. **스테이징 솔라피 설정 유무**: 있으면 가상 주문 번호를 사용자에게 받아야 한다(7.3). 없으면 발송 끝-끝은 테스트 가짜 발송 + 7.5 운영 1회로 확인.
3. **고아 도면 첨부 노출(C2 남은 틈)**: 확정 전 보내기가 흔해지면 전달 이력에 없는 도면 분류 첨부가 고객 링크에 섞여 보일 수 있다(2차 측정 G1: A 2행/1주문 #5356). 출시 전 운영 읽기 측정 1회(사용자 요청 시)로 `TRANSFERRED` 주문 중 그런 행을 센다. 있으면 2차 Q4(R1 정리)를 먼저.
4. **확정 버튼 화면·서버 불일치**: 화면 `can_confirm_receipt`(영업 도메인 권한)와 서버 `can_confirm_drawing_receipt`(배정 영업)가 달라 배정 안 된 영업에게 버튼이 보이고 403 이 날 수 있다(지금도 그렇다). 구현 때 계정별로 재 보고 결정(맞추면 `workbench.py` +2줄).
5. **v2 모바일 셸 사용 범위**: 옛 모바일 바(`dw-mobile-action-bar`, `:1564`)를 쓰는 사용자가 아직 있는지. 없으면 옛 바는 모달만 열게 최소로 고친다.
6. **보낸 뒤 긴급 호출이 바에서 빠지는 것**(목업 그대로): 필요하면 뷰어 도구줄(`workbench_mobile_handoff.html:151-162`)에 작은 버튼으로.
7. **`quest.py` 의 서버 현지 시각**(`datetime.datetime.now()`)과 도면 이력 UTC 가 섞이는 문제 — 회차 판정은 이력 문자열 `round_at` 을 그대로 비교하고(시각 비교는 표지 없는 옛 이벤트만), 발송 이벤트·토큰은 UTC 라 영향 없음을 구현 때 한 번 더 확인.
8. 실기기(아이폰 사파리)에서 `modal-fullscreen-sm-down` 시트 안 메모 칸 포커스 때 자판이 시트를 가리는지 — 캡처 7.4 때 확인.
9. **Q2 규모 측정(선택)**: 운영 읽기로 "TRANSFER 가 2번 이상이면서 마지막 TRANSFER 앞에 REQUEST_REVISION 이 없는 주문 수". Q2 추천안이면 결과와 상관없이 고객 이름은 맞으므로 선택 사항.

---

## 리뷰 반영 기록 (v1 → v2, 2026-09-29 · 조건부 승인 · P2 8건 · P3 9건)

각 지적의 근거를 이 HEAD 코드로 다시 확인했다(확인한 자리 괄호).

1. [P2 회차 경계·전달 취소] **반영** — `history.pop` 만 하고 취소 표시 없음 확인(`erp_orders_drawing.py:545-548`, 이벤트는 파일 삭제 때만 `:626-640`). 발송 이벤트에 `round_at`·`round` 표지(`send_event_tags`, 라우트당 한 줄), 읽기 모델은 표지 같음으로만 이번 회차 판정, 옛 이벤트만 시각 비교(§2.3·§4.4). "보냄 → 전달 취소 → 앞 회차 보냄 아님" 음성 대조 테스트 추가.
2. [P2 통합 템플릿·짝 링크] **반영** — `use_both`(`share.py:1516`)·`_issue_pair_tokens`(`:1526`, `created_by` 없음)·`pair_ids` 는 감사에만(`:1592`)·운영 env 등록(`AI_STATUS.md:208`) 확인. 이벤트에 `pair_ids` 싣기, 읽기 모델은 `share_id`·`drawing_share_id` 둘 다로 짝, 옛 이벤트는 ±10초 짝 규칙, `bundle_both_template` 을 `data-*` 로 내려 미리보기 전환, 통합 env 켠 테스트(§2.1·§3.5·§4.4).
3. [P2 발송 실패 뒤 남는 링크] **반영** — 400(`:1509`)·503(`:1521`)·409(`:1560`)가 이벤트 전·롤백임 확인, 회수 엔드포인트(`:1597`)와 `revoked_at` 확인. 발송 전 실패(400·404·409·410·503)면 JS 가 곧바로 회수, 읽기 모델은 회수·`created_by` 없는 링크 제외, 문구를 "직접 보낸 경우…"로 넓힘, 503 뒤 `link_only_text` 빈 값 테스트(§3.6·§4.4).
4. [P2 N차 = 전달 횟수] **반영(규칙 변경 + 질문)** — TRANSFERRED·CONFIRMED 에서 수정요청 없는 전달이 막히지 않음 확인(`erp_orders_drawing.py:60-141`, PC 버튼 `workbench_detail_body.html:1484-1488`). 회차 함수 `drawing_round_info` 하나(1 + 마지막 전달 앞 수정요청 수)로 화면 "N차"와 고객 이름을 묶고 Q2 로 올림. 운영 측정은 설계 단계에서 하지 않고(사용자 요청 필요) §10.9 선택 항목으로 둠 — 추천 규칙이면 측정 결과와 상관없이 고객 이름이 맞다.
5. [P2 갈래 약속] **반영** — Jinja 기본 `Undefined` 확인(앱에 다른 undefined 설정 없음), 공유 화면 `<title>`:11·핀:12 이웃 줄 확인. S1a 뼈대 커밋(ctx 기본값)을 먼저 합치고 템플릿은 `|default` 로 이중 안전, 공유 화면 두 파일은 S3 한 갈래로, S1 은 `share_round_label` 값만(§0).
6. [P2 목업 누락 4가지] **반영** — 목업 v4 스크립트에서 PC "긴급 호출(새로 — 지금 PC 에 없음)"·"번호 바꾸기"·"요청 고치기"·"영업에게 먼저 알리기 (긴급 호출)" 확인. 넷을 Q5 하나로 묶어 추천·이유와 함께 묻고, v1 Q2 는 기본안으로 내림. 전달 취소 문구는 표면별(PC "영업에게 먼저 연락", 모바일 "긴급 호출")로 가름(§1·§3.4·§8·§9).
7. [P2 확정만 뒤 컨펌 길] **반영** — `:2788` `open_quest=true` 확인. `bar` 키 `approve_confirm`(도면 CONFIRMED + 단계 CONFIRM + 컨펌 가능), 누르면 quest/approve 만(`idempotency_key`, C21 그대로), 실패 문구도 도면 탭으로. "확정만 → 바에 컨펌 → 생산" 테스트(§3.0·§3.6·§7.1).
8. [P2 운영 첫 수신자·되돌리기] **반영** — 템플릿 원문 확인을 G0(S1 착수 전 게이트)으로 올림, 환경변수 스위치 `FOMS_SHARE_ROUND_DOC_LABEL`(꺼짐 = 옛 고정 표, 기본 꺼짐으로 배포), 첫 운영 발송은 `CLAUDE-TEST-` 1회 + 솔라피 발송 내역 확인(Q6·§7.5). G0 은 템플릿 id 가 Railway env 에 있어 이 설계 단계에서는 실행하지 않았다.
9. [P3 중복 막기·대체발송 서술] **반영** — `dedupe_key share_alimtalk:{row.id}:{bucket}`(`:1555`), `_solapi_send` 는 접수만 확인(`kakao_alimtalk.py:424-458`), `network` 분류(`:488-490`) 확인. §2.1 서술 정정, 버튼 잠금 응답까지 유지, `network` 는 "확실하지 않아요" + 재시도 잠금, "보냄 = 벤더 접수"를 DECISIONS 에(§2.1·§3.6·§7.7).
10. [P3 컨펌 예측·응답 판정] **반영** — `find_stage_quest`(`quest_approve_authz.py:42-62`) vs `find_stage_quest_for_approve`(`quest.py:390`), `ALREADY_TRANSITIONED` 409(`:394-404`), 응답 키(`:681-689`) 확인. 예측을 승인 라우트와 같은 함수로, JS 는 `auto_transitioned`/`next_stage`·`all_approved=false`·`ALREADY_TRANSITIONED` 를 가름, 테스트 ⑨~⑪ 추가(§4.4·§3.6·§7.1).
11. [P3 새 JS 싣는 자리] **반영** — `{% if erp_mobile_v2_enabled %}`(`:3049-3051`) 확인. 조건 블록 밖 defer, `submitRevision` 에 typeof 가드, defer 계약 테스트에 두 파일(§3.6·§6·§7.1).
12. [P3 행 번호 어긋남] **반영** — `grep -n` 으로 다시 뽑아 고침(`submitRevision` :2722, 대상 검사 :2739-2742, 주문 요약 :49-55, 스레드 :188-277, 하단 바 :281-331, 막힌 이유 :282-288, 수정요청 버튼 :305-310, 반영 체크 :231-257, 참고사진 :206-229, ctx :1235-1296, `quest_approve_authz.py` 353줄 등). 리뷰가 적은 반영 체크 :233-257 은 실제 주석 시작 :231 이라 :231 로 적음. 앵커(id·함수 이름)를 함께 적는다는 규칙을 머리말에 둠.
13. [P3 bar 와 기존 버튼 겹침·표현·넘침·C14 오탐] **반영** — `#btn-cancel-revision`(`:1517`)·모바일 `cancel-revision`(`:312`)·대신 누르기 표(`drawing-handoff.js:73-78`) 확인. bar 가 그리면 옛 블록은 지우고 id 는 유지, §3.2 를 "서버 목록 순회"로 통일, 모바일 바는 앞 3개 + [더 보기](`slot`), C14 테스트는 새 JS·인라인 스크립트 본문만(§3.0·§3.1·§3.2·§7.1).
14. [P3 발송 흔적 쓰기 잠금] **반영(고침)** — `session.refresh`(`kakao_alimtalk.py:697`, FOR UPDATE 아님)·통째 재대입(`:708-710`) 확인. `share.py` 두 곳에 `lock_order_row` 한 줄씩(§4.6), writer 인벤토리 수 변화 없음, 테스트 추가.
15. [P3 열람 수 과장] **반영** — `record_view` 가 구분 없이 올림 확인(`share.py:461`·`:406`). 문구를 "링크 열림 N번"으로 바꾸고 "(직원이 연 것도 셀 수 있어요)" 덧붙임, 직원 열람 빼기는 비목표·별건(§2.3·§1).
16. [P3 인벤토리 절차·측정·되돌리기] **반영(일부 조정)** — 인벤토리는 "S1 갈래에서 refresh·커밋, 마무리에서 재확인"으로 통일, 발송 본문 `source_screen` 을 이벤트 payload 에, 1주 뒤 측정 항목(§7.6), 되돌리기 한 줄(§9), 고객 OK 시트에 "생산팀에 알림이 가요". 조정: create 는 OrderEvent 를 만들지 않으므로 `source_screen` 은 발송 이벤트에만 싣는다(측정은 발송 수로 충분).
17. [P3 이름 셋·다른 호출자] **반영** — `_SMS_KIND_LABEL` bundle "도면·계약서"(`share.py:1004`), ERP 메뉴 "도면 + 계약서 (한 링크로)"(`erp_order_tab.html:495`), 대시보드(`erp-dashboard-drawing.js:358`)·태블릿(`tablet-drawing-review.js:413`) 호출자 확인. 칩을 "도면+계약서"로, §2.5 에 두 호출자를 적고 태블릿 출처 선택은 다음 묶음 후보로(§3.5·§2.5·§1).
