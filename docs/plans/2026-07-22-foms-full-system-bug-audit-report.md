# FOMS 전수 버그 감사 · Persona 검증 · 수정 마스터 계획

> 최초 작성: 2026-07-22
> 마스터 개정: 2026-07-23 v9
> 검증 기준: `deploy@3c3288370aebf6a9fd0372c35db9287c675671e8`
> 상태: **READY TO IMPLEMENT — 코드 수정 완료나 production 승인이라는 뜻은 아님**
> 실행 원칙: 한 경계·한 PR, 근본 원인 수정, deploy와 production 분리, persona 클릭·응답·DB 불변성으로 완료 판정

---

## 0. CEO 판정

v5는 “사실 감사”로는 강했지만 구현 마스터 계획으로는 불완전했다. 기준 SHA가 낡았고, 실제 사용자에게 가장 치명적인 권한 역전과 모바일 런타임 결함이 빠졌으며, 상태·JSONB 소유권·upload·offline 계획에 구현자가 다시 선택해야 하는 문장이 남아 있었다.

v6도 1차 persona/engineering 반대감사에서 상태축·revision 선행순서·AS·upload consumer·PG test lane의 구현 결정을 남긴 것으로 판정됐다. v7/v8은 다시 persona/packet/adversarial 감사에서 PR 소유권 충돌, tablet 오분류, item/schedule identity, backfill·worker·rollback 실행성, cache destination miss, 오류 정보 노출과 debug route 결함이 발견됐다. v9의 답은 다음과 같다.

| 질문 | 최종 판정 |
|---|---|
| 제기한 문제는 정확한가? | **대부분 정확하다.** P0/P1의 코드 결함은 유지된다. 다만 일부 운영 장애 주장은 운영 미재현이며, 기준 SHA와 WDC line reference가 stale했다. |
| 수정 계획은 정확한가? | **v5~v8 계획 그대로는 부정확했다.** 권한·상태·revision·upload·item identity·worker·data repair·cache freshness·error containment·persona·PR 순서를 v9에서 다시 잠갔다. |
| 틀린 내용은 없었나? | **있었다.** `payment-confirm과 대칭인 모든 STAFF 허용`, construction 상태 SSOT 미결정, exact prefix만으로 upload 종료, `app.py`만의 startup 수정, 현재 HEAD 테스트 결과 표기가 잘못됐다. |

### 새로 확정된 실사용자 결함

1. `STAFF/PRODUCTION` 사용자는 mobile에서 `제작 완료` 버튼을 보지만 실제 POST가 `403`이고 화면에 명확한 실패가 남지 않는다. tablet surface도 같은 command 계약을 쓰므로 수정 후 별도 고정 device 검증이 필요하다.
2. `VIEWER` 사용자는 완료 화면에서 `비용 청구` 버튼을 보고 실제 POST `200`으로 주문 정산을 변경할 수 있다.
3. `STAFF/CONSTRUCTION` 사용자의 정상 UI 흐름은 시공 완료를 곧바로 `COMPLETED`로 저장한다. 저장소의 상태 정본은 `CONSTRUCTION → CS → COMPLETED`다.
4. 시공팀 모바일 shell에서 `/erp/api/notifications/mobile-state`와 badge 요청이 `302` HTML로 바뀌어 push JS가 JSON parse error를 낸다.
5. VIEWER read-only 위반은 정산 두 API에 한정되지 않는다. team-first helper, drawing participant, packing, direct upload, WDC mutation까지 endpoint inventory가 필요하다.
6. Service Worker는 사용자별 PII queue 응답을 origin 공용 CacheStorage에 넣을 수 있어 공유 브라우저 계정 전환 시 교차 사용자 노출 위험이 있다.
7. 1024×1366 coarse portrait에서 CSS는 mobile shell을 선택하지만 form-selection JS는 desktop으로 판정해 mobile form/secnav를 제거한다.
8. API 다수가 unexpected exception의 `str(e)`·traceback을 응답/표준출력에 노출하고, broad exception을 조용히 삼키는 경로도 있어 장애·보안 실패를 숨긴다.
9. 무인증 `GET /debug-db`가 deployed environment에도 등록돼 table name, User count, DB env 존재 여부를 노출하고 실패 시 raw exception과 traceback까지 반환한다.
10. 공유 WAM link/token의 telemetry POST가 body·schema·rate 제한 없이 arbitrary 값을 JSON log로 직렬화해 memory/log DoS와 로그 오염이 가능하다.
11. 비로그인 공격자가 hostile username으로 login 실패 SecurityLog를 저장하면 ADMIN 로그 화면의 `Markup`+`safe` sink에서 stored XSS가 실행될 수 있다.
12. 주문 편집자가 저장한 `online_options_summary`와 product/spec 값도 주문 목록의 raw `safe`/newline replace sink를 통해 다른 직원·ADMIN 브라우저에서 stored XSS가 된다.
13. self-edit 가능한 `User.name`이 도면 담당자 picker/detail 3곳의 raw `innerHTML`에 들어가 동료 계정에서 stored XSS가 된다.
14. app global request cap이 500MiB이고 form memory/part·route body class가 없어 public login/JSON/telemetry가 parse 전 memory/tempfile DoS를 받을 수 있다.
15. deployed staging은 known Flask fallback secret로, WAM token은 별도 known fallback secret로 기동할 수 있어 session/token 위조 위험이 있다.
16. 개인 변경이력에 persisted/API 값이 raw `innerHTML`·inline `onclick`에 들어가고, 도면 담당자 picker에는 추가 `User.name/team` sink가 있어 기존 XSS 범위가 과소 집계됐다. (Designer 화면 XSS는 FOMS Brain이 삭제 예정이라 DESIGNER-RETIRE-01 표면 제거로 소멸 — 이 감사 범위서 제외.)
17. Admin 사용자 hard-delete route가 User row와 과거 주문·배정·감사 주체 보존 계약을 깨뜨리며, 비활성화 command와 충돌한다.
18. ChannelTalk Function은 공식 `PUT + hex-decoded key HMAC-SHA256 + Base64 X-Signature`인데 현재는 `POST + raw UTF-8 key + hex digest`라 실제 provider가 405/401을 받을 수 있다. 표준 Webhook은 별도 `POST ?token=` 계약인데 같은 Function signature decorator를 재사용해 정상 webhook을 401로 거부할 수 있다.

### “완벽”의 정확한 의미

- **이 문서는 구현자가 제품 결정을 다시 묻지 않고 PR 단위로 시작할 수 있는 수준으로 완료한다.**
- **FOMS 코드가 완벽히 수정됐다는 뜻은 아니다.** 각 PR의 실패 테스트가 먼저 red가 되고, 수정 후 green, deploy persona smoke, CI green을 통과해야 수정 완료다.
- production DB, Railway env, Kakao 콘솔, 실제 운영 계정은 이번 문서 개정에서 변경하거나 검증하지 않았다. 이것들은 명시된 운영 preflight다.

---

## 1. 검증 기준과 증거 규칙

### 1.1 증거 등급

| 등급 | 의미 |
|---|---|
| **RB-L-R** | 격리 SQLite와 synthetic 계정을 사용한 실제 로컬 브라우저 render/navigation 확인 |
| **RB-L-M** | 같은 환경에서 실제 mutation 클릭·network status·DB 전후를 함께 확인 |
| **RB-S** | staging 공개 경계의 read-only 브라우저 확인 |
| **R** | parser, Flask client 또는 명령으로 직접 재현 |
| **T** | 명시된 SHA에서 pytest로 실행한 결과 |
| **C** | 현재 HEAD 코드가 동작 또는 검사 부재를 직접 보여줌 |
| **P** | 저장소 정책·설계 정본과 런타임 코드의 충돌 |
| **I** | 코드로부터 도출한 위험. 런타임 발생은 미확인 |
| **U** | 운영 환경·외부 콘솔·실데이터에서 확인하지 않음 |
| **DEC** | 이 마스터 계획이 구현 계약으로 잠근 결정 |

### 1.2 2026-07-23 persona 브라우저 증거

모든 mutation은 임시 SQLite DB와 synthetic 사용자·주문에서만 수행했다. staging에서는 자격증명을 사용하지 않았고 mutation을 보내지 않았다.

| Persona / 화면 | 관찰 | network·DB 결과 | 판정 |
|---|---|---|---|
| staging 비로그인, 390×844 | `/erp/dashboard`가 `/login?next=/erp/dashboard`로 이동, console error 없음 | TTFB 109 ms, load 약 936 ms | RB-S. 공개 auth boundary만 확인 |
| `STAFF/SALES`, 1280×800 | `/erp/dashboard?order=5`에서 결제·단계·업로드·저장 UI 확인 | local render 성공 | RB-L-R. happy surface 관찰; stale 두 탭은 미실행 |
| `VIEWER`, desktop 1280×800 | 주문 목록에 새 주문·Excel·bulk action·edit/delete UI, 완료 화면에 `비용 청구` 버튼 노출 | `79c2d9a2` 실제 click `POST /api/orders/5/settlement/issue → 200`; settlement·event·log 변경; current까지 writer diff 0 | RB-L-M. read-only 정책 직접 위반 |
| `STAFF/PRODUCTION`, mobile 390×844 | 제작중 카드에 `제작 완료` 버튼 노출 | `79c2d9a2` click `POST /api/orders/3/production/complete → 403`; DB `PRODUCTION` 유지; 명확한 실패 UI 없음; current까지 writer diff 0 | RB-L-M. 생산팀 핵심 dead action. 이전 768×1024 관찰을 tablet로 부르지 않음 |
| `STAFF/CONSTRUCTION`, mobile 390×844 | 허용 탭은 출고·시공·완료·이력. 시공 시작 후 완료 모달 실행 | `79c2d9a2` start `200`, complete `200`; DB `CONSTRUCTION → COMPLETED`; notification state/badge `302`; current까지 writer diff 0 | RB-L-M+P. CS 단계 건너뜀과 API redirect 확인 |
| `STAFF/DRAWING`, 390×844 | 작업실 카드·수령 확인·마법사·담당자 UI 렌더 | workbench render 성공 | RB-L-R. wizard 저장/전달은 미실행 |
| `STAFF/SALES`, order edit 390×844 | `31f05379`에서는 `접수` click 뒤 secnav top `-1758`로 이탈했으나 current `3c328837`은 initial 196..248, deep scroll 뒤 48..100 fixed | current 실제 click `scrollY=1946`, target top `345.84`, active=true, width/docWidth=390, console error 0 | RB-L-R. current sticky 동선 복구 확인; P1-27 cohort mismatch와 회귀 geometry는 SURFACE-GATE에 유지 |

로컬 단순 Flask 서버의 Socket.IO `Invalid frame header`는 gevent가 없는 감사 harness 산물로 분리했다. 제품 결함으로 집계하지 않는다.

### 1.3 현재 SHA 정합 규칙

1. 보고서 기준 SHA, line-reference audit SHA, targeted test SHA는 반드시 같다.
2. HEAD가 바뀌면 `git diff <문서SHA>..HEAD -- <관련 파일>`을 먼저 검토한다.
3. line number는 보조 정보다. 구현자는 파일+함수/상수 이름으로 다시 찾는다.
4. 이전 v5의 `221 passed`는 `e550f9f92360` 근거이므로 현재 사실에서 제거한다.
5. gstack run 횟수처럼 artifact가 없는 자기선언은 증거로 사용하지 않는다.

### 1.4 현재 SHA 재검증 결과

| 검증 | 결과 | 해석 |
|---|---|---|
| current `3c328837` 변경 영향 5개 domain/visual test file | **`210 passed, 1 skipped, 1 warning`** | `31f05379`의 brittle CSS comment false-positive와 sticky parent trap을 수정한 current local gate green. warning은 SQLite에서 PostgreSQL DISTINCT ON 무시 예정 경고 |
| current `3c328837` 권한·structured PUT·wizard·production·construction·notification·copy 7-file targeted pytest | `180 passed, 9 warnings` | `31f05379..3c328837`이 order surface/test 10개 파일만 변경하고 해당 writer diff 0이므로 직전 current run 증거 유지. 신규 negative 계약을 대신하지 않음 |
| current `3c328837` GitHub CI quick | **ALL GREEN** | local 5-file changed-suite도 green. CI green은 신규 auth/provider/persona negative 계약을 대신하지 않음 |
| `2b86c689` app import + `2b86c689..3c328837` startup source diff 0 | `APP_OK`, 그러나 import 중 schema init·WDCalculator init·최근 ERP flat backfill·Admin 존재 검사를 실제 실행 | STARTUP finding은 current source에서도 유지. 운영 DB가 아닌 local configured DB |
| 이전 broader run의 Playwright 7건 | visual fixture가 `sqlite:///:memory:`를 거부해 setup error 7건 | 제품 실패로 세지 않으며 current HEAD 증거로도 세지 않는다. packet gate는 file-backed SQLite 명령으로 교정 |
| `node --check static/js/foms/erp-attachment-preview-open.js` | line 205 `SyntaxError` | P0-6 현재 재현 |
| gstack browser local persona | `79c2d9a2` VIEWER mutation 200, PRODUCTION 403, construction direct COMPLETED; `79c2d9a2..3c328837` 해당 auth/state writer diff 0 | mutation은 pre-drift 증거, current source 결함 유지. 각 packet이 current SHA red test를 다시 소유 |
| `2b86c689..3c328837` diff audit | order form/secnav CSS·JS/template/tests 중심, auth/state/data/wizard writer 변화 0 | current changed tests와 390×844 실제 click green. P1-32는 current resolved, P1-27 predicate mismatch는 유지 |

> **baseline drift 주:** 이 표의 `3c328837` 수치는 문서 baseline 기준이다. 현재 deploy HEAD는 `a8e3b168`로 1커밋(모바일 ERP 섹션 이동 단일 좌표 스크롤, UI-only) 앞서 있다. `git diff 3c328837..a8e3b168`는 secnav JS(`erp-order-shared.js`)/CSS(`foms-form-field.css`)·mobile 템플릿·visual 테스트(`test_erp_order_edit_mobile_form.py` 등)와 `?v=` 범프만 바꾸고 **auth/state/data/wizard writer diff는 0**이다. 따라서 코어 P0/P1 finding의 line-reference는 재고정 불필요하다. 단 `210 passed`·GitHub CI green·`390×844 secnav 48..100 fixed`·P1-32 `current resolved`는 `3c328837` 기준 수치이므로, SURFACE-GATE-01/DATA-01은 BASE-00에서 HEAD `a8e3b168` 기준으로 5-file visual suite 재실행+실브라우저 geometry 재관찰로 재확립한다.

기존 test/CI green은 결함 부재를 뜻하지 않는다. 위 미구현 persona 실패 계약은 packet별 red test로 추가하고 current green을 유지한 뒤에만 해당 packet을 완료한다.

### 1.5 외부 provider 공식 계약 교차검증

- ChannelTalk 공식 [Function 문서](https://developers.channel.io/en/articles/Function-77250b17)는 Function Endpoint method를 PUT으로, `X-Signature`를 signing key의 hex-decoded bytes와 exact UTF-8 raw body의 HMAC-SHA256 digest를 Base64 인코딩한 값으로 정의한다.
- 공식 [Getting Started Tutorial](https://developers.channel.io/en/articles/Getting-Started-Tutorial-516161ed)은 유효하게 인증된 Function의 domain error도 `{error:{type,message}}`와 HTTP 200으로 interface에 돌려주고, signed `context.channel`을 특정 configured channel과 대조하라고 명시한다.
- 표준 Webhook 공식 [Getting started 문서](https://developers.channel.io/en/articles/Getting-started-f2a30b58)는 `POST https://.../PATH?token=TOKEN_VALUE`를 사용하며, 4xx/5xx가 연속 100회면 webhook이 block된다고 명시한다. Function HMAC을 Webhook에 추정 적용하지 않는다.
- 공식 [Webhook events 문서](https://developers.channel.io/en/articles/Webhook-events-7bd9b8e2)는 common envelope를 `event,type,entity,refers`로 정의하고 message/userChat/user event별 필드 위치가 다름을 보여준다. current invented `eventId/ref/entity.message` fixture를 정본으로 사용하지 않는다.
- Railway 공식 [Public API 문서](https://docs.railway.com/integrations/api)는 token-auth GraphQL endpoint를, [Variables Reference](https://docs.railway.com/variables/reference)는 runtime에서 제공되는 project/environment/service/deployment/replica/region/commit 식별자를 정의한다. 배포 증거 collector는 이 공식 API와 runtime heartbeat를 서로 대조하고, provider가 제공하지 않는 desired inventory는 추정하지 않는다.
- 현재 구성된 PostgreSQL MCP의 read-only schema 조회에서는 `public.orders`와 `wdcalculator.estimate_order_matches`가 동일 database `furniture_orders`에 존재했다. 이는 **현재 연결 대상의 topology 증거**일 뿐 production 불변 가정이 아니므로, WDC packet은 환경마다 `SAME_DATABASE|SEPARATE_DATABASE`를 다시 산출한다.

---

## 2. 제품·보안·데이터 결정 — 구현 중 재해석 금지

### 2.1 역할·팀 권한 정본

평가 순서는 반드시 다음과 같다.

```text
authentication
  → role hard deny
  → domain/team capability
  → order assignment/participation
  → command-specific state predicate
  → ADMIN/MANAGER emergency override(reason + application append-only audit)
```

| 주체 | 허용 mutation | 명시적 금지 |
|---|---|---|
| `ADMIN` / `MANAGER` | 운영·관리 command. cross-domain override는 사유 필수 | 사유 없는 stage/approval override |
| `STAFF/SALES`, `STAFF/CS` | 주문 form/finance/estimate, 기존 production oversight command, packing | 도면·시공 assignment 전용 command의 무사유 대행 |
| `STAFF/DRAWING` | 참여 주문의 drawing wizard, pending, transfer, revision | 일반 structured form, 금융, 생산·시공 command |
| `STAFF/PRODUCTION` | production start/complete/steps/defect/hold/change-ack | 일반 structured form, 금융, 시공 command |
| `STAFF/CONSTRUCTION` | 배정 주문의 packing, construction start/evidence/complete/fail | 일반 structured form, 금융, 생산 command |
| `STAFF/SHIPMENT` | 팀 전체 packing, 출고·물류 일정/milestone command | 금융·일반 form·main-stage·AS command |
| `VIEWER` | GET/HEAD 조회, 서버 상태를 바꾸지 않는 pure calculation, 아래 actor-owned ancillary allowlist | **team·assignment와 무관하게 모든 Order/finance/workflow/master/business mutation** |

추가 계약:

- legacy pseudo-team `MEASURE`(실측)는 실제 `User.team` 값으로 존재할 수 있다. **현재 코드는 team=MEASURE를 ERP 쓰기 권한에서 제외한다**: `foms/services/erp_permissions.py`의 `ERP_EDIT_ALLOWED_TEAMS=("CS","SALES")`와 `can_edit_erp`(:295)는 MEASURE를 허용하지 않고, MEASURE/CONFIRM stage quest 승인(`foms/api/quest.py:193`)은 SALES_DOMAIN assignee override 또는 **manager 이름 폴백**으로만 team=MEASURE를 통과시킨다. (`_MINE_SCOPE_BY_TEAM["MEASURE"]="sales"`는 '내 항목' 리스트 **필터 스코프**일 뿐 쓰기 capability가 아니다 — 이전 판본이 이를 capability 근거로 잘못 인용했다.) AUTH-01은 이 이름 폴백을 제거하므로(command-group 표 '이름 비교 금지'), team=MEASURE를 그대로 두면 실측 quest 승인이 회귀한다. 따라서 §7.1 preflight로 active `User.team=MEASURE` 건수와 최근 실측 quest 승인 이력을 실측해 분기한다: **(a) 실측 업무를 실제로 하는 active MEASURE 계정이 있으면** team=MEASURE를 SALES capability set에 **신규 추가**(권한 확대 결정)하고 quest required-team 매칭에서 SALES로 정규화한다; **(b) active MEASURE가 0이거나 실측 이력이 없으면** pseudo-team으로 문서화만 하고 확대하지 않는다. 어느 분기든 새 role/team 표가 MEASURE를 무권한(조회전용)으로 **방치**하지 않는다.
- HTML page 권한 실패는 사용자용 redirect가 가능하다. `/api/*`, `/erp/api/*`는 redirect하지 않고 JSON `401/403`을 반환한다.
- UI control은 같은 policy ID를 사용해 숨긴다. UI 은닉은 backend 권한을 대체하지 않는다.
- 모든 state-changing route는 `policy_id` metadata를 가져야 한다. 예외는 서명 검증 webhook과 상태 불변 pure calculation만 명시 allowlist한다. login/register/logout도 account policy ID를 가진다.
- 모든 cookie-auth state-changing route는 `write_guard=CSRF_TOKEN+ORIGIN` metadata와 공용 guard를 사용한다. HTML form은 session-bound token, JSON은 `X-CSRF-Token`+same-origin Origin을 요구한다. login/register는 anonymous session token+trusted-IP/username rate policy, signed webhook과 anonymous validated RUM은 signature/ingest policy로만 명시 exempt한다. logout/switch/switch-back도 POST이며 GET은 405다. CORS/SameSite는 보조 방어이고 guard를 대체하지 않는다.
- 금융 mutation의 확정 허용자는 `ADMIN/MANAGER` 또는 `STAFF+CS/SALES`다. 기존 payment-confirm도 같은 matrix로 교정한다.
- WDC calculate는 로그인 사용자에게 허용하되 DB를 변경하지 않는다. estimate save/match는 `ADMIN/MANAGER` 또는 `STAFF+CS/SALES`, product/category/spec preset master mutation은 `ADMIN/MANAGER`, VIEWER는 조회만 허용한다.
- role hard deny의 exact ancillary 예외는 `MARK_OWN_NOTIFICATION_READ|ARCHIVE_OWN_NOTIFICATION|ACK_OWN_NOTIFICATION|CREATE_OWN_PUSH_SUBSCRIPTION|DELETE_OWN_PUSH_SUBSCRIPTION|MARK_ROOM_READ|SEND_CHAT_MESSAGE|UPLOAD_CHAT_ATTACHMENT|SEND_URGENT_CALL`이다. VIEWER도 자기 notification/subscription, active member room, read-scope Order의 urgent call에만 이 allowlist를 사용할 수 있다. `SEND_URGENT_CALL`은 아래 participant/target/rate policy를 추가로 통과해야 한다. 타 사용자 notification, room lifecycle/member 변경, Order business mutation/link/master/Channel action은 금지한다. 각 route는 owner/membership/order scope를 재검사하고 child receipt/row version, rate/size 제한과 audit를 쓰며 Order/version을 변경하지 않는다.
- chat room lifecycle은 `CREATE_CHAT_ROOM {name,description?,order_id?,member_user_ids}`, `UPDATE_CHAT_ROOM`, `ADD_CHAT_MEMBERS`, `REMOVE_CHAT_MEMBER`, `LEAVE_CHAT_ROOM`, `CLOSE_CHAT_ROOM {reason}`로 제한한다. ADMIN/MANAGER 또는 STAFF만 room을 만들고, linked order는 creator의 read scope가 필수다. active user IDs만 받고 room+creator membership+members를 한 transaction에 commit한다. creator 또는 ADMIN/MANAGER만 metadata/member를 관리하며 일반 member는 자기 leave/mark-read만 가능하다. creator는 ownership transfer 또는 close 전 leave할 수 없다. room row version/If-Match, receipt/idempotency, `(room_id,user_id)` unique, soft close/audit를 사용하고 hard delete와 row별 commit을 제거한다. `SEND_CHAT_MESSAGE`는 CHAT-MESSAGE-01이 text와 UPLOAD-CHAT ticket attachment claim을 한 transaction으로 소유한다.
- `SEND_URGENT_CALL {order_id,target_user_id,message}`는 Order read scope/participant인 authenticated actor에게 허용하므로 관련 주문을 조회할 수 있는 VIEWER도 쓸 수 있다. target은 active FOMS user, message trim 1..500, actor+order당 5회/시간이며 same key retry는 한 호출이다. notification, recipient urgent state, urgent-call `NotificationEvent`, source_domain=NOTIFICATION_EVENT side-effect row를 한 transaction에 commit하고 Order version은 바꾸지 않는다. target list도 같은 order read scope를 요구하며 send/ack PC+390px UI는 role policy로 control을 표시한다. 타 주문/비활성 target/rate 초과는 403/422/429와 child 변화 0이다.

command-group별 assignment 계약:

| command group | STAFF capability | assignment | ADMIN/MANAGER |
|---|---|---|---|
| order form·finance·estimate | `CS`/`SALES` team-wide | 없음 | 정상 state predicate 안에서는 reason 없이 허용 |
| production | `CS`/`SALES`/`PRODUCTION` team-wide(현 정상 workflow 보존) | 없음 | 정상 expected-stage면 reason 없이 허용 |
| shipment/logistics·crew scheduling | `CS`/`SALES`/`SHIPMENT` team-wide; assigned `CONSTRUCTION`은 자기 주문 packing | construction app write는 user ID assignment, 외주 crew 표시는 별도 crew ID | 정상 logistics predicate면 reason 없이 허용 |
| drawing claim | `DRAWING` team-wide read, 미배정 주문 claim | claim이 actor를 ID로 원자 배정 | claim 대행은 reason 필요 |
| drawing wizard/transfer/revision | `DRAWING` + explicit assignee ID | 필수. 이름 비교 금지 | assignment bypass는 reason 필요 |
| construction/packing/evidence | `CONSTRUCTION` + explicit assignee ID | 필수. legacy name은 preflight backfill 대상 | assignment bypass는 reason 필요 |
| CS complete·AS processing | `CS` team-wide | 없음 | 정상 predicate면 reason 없이 허용 |
| quest approval | 요청 team과 current quest required team 일치 | drawing/construction command는 위 assignment도 적용 | 타 team 대행은 reason 필요 |

assignment 정본은 신규 `order_assignments(id,order_id,domain,user_id,source,active,assigned_at,assigned_by_user_id,released_at,released_by_user_id,release_reason)`다. `domain=SALES|DRAWING|CONSTRUCTION`, `source=SELF_CLAIM|TEAM_REPLACE|INITIAL_OWNER|BACKFILL`; PostgreSQL partial unique index는 `(order_id,domain,user_id) WHERE active=true`이고 SALES에는 추가로 `(order_id) WHERE active=true AND domain='SALES'` unique를 둔다. release 이력은 보존한다. 권한 판정은 이 user ID row만 사용하고 JSONB 이름 배열은 server-owned 표시 projection이다. 아래 registry에서 STAFF team만 열거한 정상 command도 ADMIN/MANAGER는 같은 state predicate에서 reason 없이 실행할 수 있다. assignment/team/edge를 우회할 때만 emergency override reason이 필수다.

- `CLAIM_DRAWING {}`: STAFF/DRAWING이 DRAWING stage의 active drawing assignment 0건인 주문을 자기 ID로 claim. event `DRAWING_ASSIGNED`; 같은 key replay, 새 key 재claim 409.
- `SET_SALES_ASSIGNEE {user_id,reason}`: SALES-domain order owner 한 명을 지정/교체한다. target은 active STAFF의 `SALES|CS`; 생성 후 교체는 현재 SALES owner, STAFF+CS 또는 ADMIN/MANAGER가 실행하고 교체 reason 1..500이 필수다. event `SALES_ASSIGNEE_SET`; revision request/receipt/customer confirm 권한의 정본이다. STAFF/SALES|CS 생성자는 자기 ID를 default로 쓸 수 있지만 ADMIN/MANAGER 생성자는 active STAFF/SALES|CS owner ID를 picker에서 반드시 명시해야 하며 누락은 422다. ADMIN/MANAGER role 자체를 SALES owner로 저장하지 않는다.
- `SET_DRAWING_ASSIGNEES {user_ids:[...],reason}`: STAFF/DRAWING team-wide 또는 ADMIN/MANAGER가 1..20명의 active DRAWING user로 replace; 빠진 row release+추가 row assign을 한 tx, event `DRAWING_ASSIGNMENTS_REPLACED`. cross-domain ADMIN/MANAGER만 reason 필수다.
- `BATCH_SET_DRAWING_ASSIGNEES {orders:[{order_id,mutation_version}],user_ids:[...],reason}`: PC workbench의 일괄 지정 정본이다. 단건과 같은 target/policy를 쓰고 Order ID 정렬 lock, all-or-none, order별 resulting version과 한 event를 receipt에 반환한다. 누락·stale·invalid order가 한 건이면 전체 `409/422`, assignment/version/event 변화 0이며 row별 예외를 삼키지 않는다.
- `SET_CONSTRUCTION_ASSIGNEES {user_ids:[...],reason}`: ADMIN/MANAGER 또는 STAFF+CS/SALES가 앱에 로그인해 construction command를 실행할 active CONSTRUCTION user 1..20명으로 replace. event `CONSTRUCTION_ASSIGNMENTS_REPLACED`; 이 ID만 authorization에 사용한다.
- `RELEASE_ASSIGNMENT {domain,user_id,reason}`: drawing actor는 transfer 전 `source=SELF_CLAIM AND user_id=actor_id`인 자기 claim만 release한다. `TEAM_REPLACE`로 자기에게 배정된 row는 DRAWING team replace 또는 ADMIN/MANAGER command로만 해제한다. CS/SALES는 construction assignment만 release, ADMIN/MANAGER는 둘 다 가능하다. reason 1..500 필수다. target User가 inactive여도 active assignment row는 release 가능하며, assignment가 없거나 이미 inactive면 409다.

외주 기사와 앱 authorization을 섞지 않는다. 신규 `installation_workers(id,display_name,phone_hash nullable,active,linked_user_id nullable,created_at,created_by_user_id,updated_at)`와 `order_installation_assignments(id,order_id,worker_id,active,assigned_at,assigned_by_user_id,released_at,released_by_user_id,release_reason)`가 일정/표시 정본이다. 후자는 `(order_id,worker_id) WHERE active=true` partial unique와 `(order_id,active)`, `(worker_id,active)` index를 가진다. `SET_INSTALLATION_CREW {worker_ids:[...],reason}`는 STAFF+CS/SALES/SHIPMENT 또는 ADMIN/MANAGER가 active worker **0..20명**으로 replace하고 event `INSTALLATION_CREW_REPLACED`; 빈 배열은 전원 release하며 이력을 지우지 않는다. linked user가 있어도 이 row 자체는 auth 근거가 아니다. `shipment.construction_workers`는 crew 표시명 projection이다.

crew master는 `CREATE_INSTALLATION_WORKER {display_name,phone?,linked_user_id?}`, `UPDATE_INSTALLATION_WORKER {worker_id,display_name,phone?,linked_user_id?}`, `DEACTIVATE_INSTALLATION_WORKER {worker_id,reason}`만 변경한다. STAFF/SHIPMENT 또는 ADMIN/MANAGER, 이름 1..100, normalized phone hash unique, linked user는 active CONSTRUCTION user 0/1명이다. active order crew row가 남은 worker 비활성화는 `409 WORKER_IN_USE`; 먼저 각 주문에서 replace/clear해야 한다. 같은 key replay는 한 worker만 만들고 모든 변경은 append-only audit를 남긴다. 기존 shipment settings의 `construction_time|drawing_manager|drawing_manager_en|measurement_manager|site_extra` reference list는 `UPDATE_SHIPMENT_REFERENCE_LISTS`가 보존하되 free-name `construction_workers` master write는 제거한다.

`UPDATE_SHIPMENT_REFERENCE_LISTS {settings_version,construction_time,drawing_managers,measurement_managers,site_extra}`는 STAFF/SHIPMENT 또는 ADMIN/MANAGER만 실행하는 별도 SystemSetting command다. exact schema는 construction time 최대 50개 trim string 1..50, drawing manager 최대 100개 `{name:1..100,english_name:0..100}`, measurement manager 최대 100개 `{name:1..100,phone:0..50,sort_order:int 0..9999}`, site extra 최대 100개 trim string 1..500이며 중복 normalized entry는 422다. old `drawing_manager`+`drawing_manager_en`은 한 object array로 safe backfill하고 `construction_workers` key는 request에서 400이다. SystemSetting row lock/version+If-Match, collection receipt/idempotency, SecurityLog를 한 transaction에 쓰고 stale은 409다.

account command는 validation-before-write다. `UPDATE_OWN_PROFILE {name,current_password?,new_password?,confirm_password?}`에서 name-only는 authenticated session+CSRF로 허용한다. password 관련 field가 하나라도 있으면 current/new/confirm 세 값이 모두 필수이며 current password·name 1..100·new password strength/confirmation을 전부 검증한 뒤 이름/비밀번호를 한 transaction에 commit한다. 새/reset password는 mode와 무관하게 Unicode 12..128 code point, leading/trailing whitespace·control/NUL·username/name 동일·versioned local common-password denylist를 거부하며 조합문자 강제는 하지 않는다. 기존 hash algorithm은 성공 login에서 현재 Werkzeug scrypt로 rehash하되 원래 password strength를 알 수 없으므로 이것만으로 `password_policy_version`을 올리지 않는다. `FOMS_PASSWORD_POLICY_MODE=WARN`에서는 legacy account도 로그인/업무가 가능하고 persistent banner와 변경 UI를 보인다. `ENFORCED`는 active legacy-policy account 0이라는 read-only audit와 사용자/ADMIN rotation 100% 후에만 켜며, 그 뒤 낮은 policy version은 read+logout+password-change만 `PASSWORD_CHANGE_REQUIRED`로 허용한다. cutover 후 rollback `DISABLED`는 새/reset 약한 password를 허용하지 않고 legacy-policy login/business mutation을 503+지원 안내로 닫는다. 갑작스런 전 계정 write lock은 금지한다. 실패는 모든 user field/session 변화 0과 error 한 개다. ADMIN user command는 `ADMIN_CREATE_USER {username,name,role,team,password,is_active}`, `ADMIN_UPDATE_USER {user_id,name,role,team}`, `ADMIN_RESET_USER_PASSWORD {user_id,new_password}`, `ADMIN_SET_USER_ACTIVE {user_id,is_active,new_password?,reason}` 네 개뿐이다. username/name/role-team/password/active 조합을 command별 전부 검증한 뒤 한 transaction을 시작하고 하나라도 invalid면 변화 0이다. SET_ACTIVE의 reason은 활성·비활성 모두 trim 1..500이 필수다. new_password는 ENFORCED/DISABLED에서 legacy target을 활성화할 때만 필수이며 같은 tx reset에 사용한다; 그 밖의 active toggle body에 password가 오면 422다. self password change는 target=actor의 policy version과 session_version을 올려 다른 actor session을 revoke하고 **그 요청의 현재 session만** 새 version으로 재발급한다. ADMIN의 target password reset은 target policy/session version을 올려 target 전 session을 revoke하고 target session 발급 0, Admin actor session은 유지한다. target role/team/is_active 변경도 target session_version을 올려 전 session을 revoke하며 Admin은 자기 role/deactivate를 web에서 실행할 수 없다. ENFORCED/DISABLED에서 inactive legacy-policy user의 `false→true`는 같은 transaction의 strong password reset이 없으면 `409 PASSWORD_RESET_REQUIRED`와 변화 0이다. ADMIN user list는 `password_policy_status=LEGACY|CURRENT` 필터와 reset action만 제공하고 hash/원문/export는 0이다.

이 문서의 `session_version` 정본은 User 임의 column이 아니라 `OPS-APPROVAL-00`이 먼저 만드는 `security_principal_versions(user_id PK,version,updated_at)`다. existing User는 version1로 seed하고 PostgreSQL trigger가 `password_hash|role|team|is_active` 변경 transaction에서 정확히1 증가시킨다. application이 별도 increment하지 않으며 AUTH-ACCOUNT-01은 trigger가 반환한 새 version으로 현재 session만 재발급한다.

login limiter의 정본은 Redis가 아니라 PostgreSQL `auth_rate_limit_key_state(id=1,mode=EMPTY|READY|CURRENT_ONLY|ROTATION_READY|ROTATING,generation,shadow_epoch,active_key_id,pending_key_id,previous_key_id,previous_not_after,shadow_started_at,shadow_coverage_reset_at,row_version,prepared_consumer_sha,prepared_rollout_artifact_sha256,prepared_at,activated_at,updated_at,updated_by_admin_user_id)`, `auth_rate_limit_shadow_heartbeats(deployment_id,replica_id,boot_id,shadow_epoch,coverage_started_at,last_success_at,last_seen_at,dirty_recovered_at,PRIMARY KEY(deployment_id,replica_id,boot_id))`, `auth_rate_limit_buckets(scope,key_generation,key_hash,window_started_at,attempt_count,expires_at,updated_at,PRIMARY KEY(scope,key_generation,key_hash))`다. `FOMS_AUTH_RATE_LIMIT_KEY_CURRENT`는 session signing과 독립인 padding 없는 base64url exact32 bytes다. `scope=ACCOUNT|CLIENT_IP|ACCOUNT_IP` preimage는 ACCOUNT=`ACCOUNT\0<NFKC+casefold account>`, CLIENT_IP=`CLIENT_IP\0<trusted canonical IP 또는 UNKNOWN sentinel>`, ACCOUNT_IP=`ACCOUNT_IP\0<account>\0<IP/sentinel>` exact bytes다. active dedicated key HMAC-SHA256로 저장하며 raw account/IP는 저장·로그하지 않는다.

initial bootstrap은 additive `EMPTY,generation=0,shadow_epoch=0` schema→CURRENT key inject→`inspect_auth_rate_limit_key_slot.py --slot CURRENT --output <redacted-key-artifact.json>`→`prepare_auth_rate_limit_bootstrap.py --current-key-artifact <path> --expected-consumer-sha <sha> --expected-version 0 --approval-token-file <path> --apply`의 deadline-null `EMPTY→READY`→bridge all-serving 순서다. READY bridge는 기존 limiter를 유일한 reject authority로 호출하면서 모든 login attempt를 PG에 shadow-consume한다. 각 replica는 random boot ID를 만들고, boot/restart 또는 local dirty latch 뒤 첫 DB reconnect transaction에서 state를 FOR UPDATE해 `shadow_epoch+1,shadow_coverage_reset_at=DB now`와 자기 `coverage_started_at`을 기록하기 전 auth serving을 재개하지 않는다. shadow tx 실패 즉시 readiness red+process-memory dirty latch이며 legacy login은 계속 가능하지만 activation proof는 끊긴다. DB outage 중 죽은 replica도 stale heartbeat/desired inventory mismatch와 replacement boot ID 때문에 coverage0부터 다시 시작한다. 10초 periodic DB heartbeat와 각 shadow success가 `last_success_at/last_seen_at`을 갱신한다.

`check_auth_rate_limit_bootstrap_rollout.py --deployment-artifact <path> --require-shadow-seconds 900 --max-heartbeat-gap-seconds 15 --output <rollout-artifact.json>`은 current desired serving replica 전부가 같은 latest epoch, current boot ID, all-serving consumer SHA/key ID, fresh heartbeat, 900초 연속 coverage이고 dirty/restart/gap0임을 증명한다. artifact exact schema는 `{schema_version,state_version,shadow_epoch,coverage_started_at,required_seconds,services,replica_boots,consumer_sha,key_id,captured_at,canonical_sha256}`다. 그 뒤 별도 `activate_auth_rate_limit_bootstrap.py --rollout-artifact <path> --expected-version <n> --approval-token-file <path> --apply`만 active=CURRENT,generation=1,CURRENT_ONLY로 바꾼다. CURRENT_ONLY부터 CURRENT key missing/default는 fail-start이고 old/non-state-aware rollback은 STOP이다.

CURRENT_ONLY/ROTATING에서는 credential 조회 전에 account10/15분, trusted client-IP60/15분, account+IP5/5분의 세 bucket을 `(scope,generation,key_hash)` 정렬 순으로 한 transaction에서 DB `clock_timestamp()` 기반 atomic UPSERT한다. **공유 egress 완화:** §7.1 preflight가 사무실이 단일 공인 IP(공유 NAT)를 쓴다고 실측하면, CLIENT_IP bucket 한도를 고정 60이 아니라 `max(60, ceil(active_account_count × 계정당 여유))`로 상향(환경변수 `FOMS_AUTH_RATE_LIMIT_CLIENT_IP_MAX`로 주입, 계정별 account/account+IP bucket은 불변)하거나 primary throttle을 account+IP로 두어 아침 로그인 러시가 정답 첫 시도까지 429로 잠그지 않게 한다. 공유 IP가 아니면 기본 60을 유지한다. normal rotation은 (1) NEXT inject/inspect, (2) prepare가 pending+generation을 deadline 없이 `CURRENT_ONLY→ROTATION_READY`, (3) old active+NEXT bridge all-serving; ROTATION_READY에서는 old active만 소비, (4) artifact 뒤 separate activation이 active=new, previous=old, deadline=DB now+15분, ROTATING, (5) **CURRENT=new, PREVIOUS=old, NEXT unset** all-serving 후 deadline 뒤 PREVIOUS 제거/CURRENT_ONLY다. ROTATING 동안 동일 preimage의 active+previous 6 row를 정렬 lock/upsert하고 어느 generation이든 초과면 거부한다. activation 뒤 old/non-state-aware rollback은 STOP이다. 만료 row는 count1/window reset, 미만료는+1이다. limit은 password 조회 전 generic429 즉시 반환하고 server sleep/busy/async delay0, `Retry-After`와 JSON `retry_after_seconds`는 blocking row의 가장 늦은 `expires_at-DB now` ceil을1..900초로 clamp한 동일 값이다. 성공도 reset하지 않는다. PG unavailable은 credential/session0과 503 `AUTH_RATE_LIMIT_UNAVAILABLE`; Redis는 bootstrap READY의 legacy authority 또는 CURRENT_ONLY 이후 optional early reject일 뿐 PG fallback/정본이 아니다. expiry index와 bounded purge가 만료24시간 뒤 row만 지운다. PG N-worker는 bootstrap mixed replica+900초 shadow, 10/60/5, rotation mixed replica/overlap/old rollback, signing rotation 불변, delay0, 100 concurrent perf를 검증한다.

실사용 login은 1280×800/390×844/1024×768 모두 같은 계약이다. 429는 account 존재 여부와 무관한 고정 문구, `Retry-After` 기반 초 단위 남은 시간과 local-time 재시도 시각, enabled submit 1개를 표시하고 password만 clear하며 username은 사용자가 입력한 값을 local form에 보존하되 server response/log에 echo하지 않는다. countdown은 자동 request를 만들지 않는다. PG503은 `인증 서비스를 일시적으로 사용할 수 없습니다`+request_id+수동 재시도만 표시하고 invalid-credential 문구를 쓰지 않으며 password clear/session0이다. EMPTY/READY/outage→restart→reconnect→900초 재대기/CURRENT_ONLY 전 과정에서 UI 의미와 legacy quota가 연속임을 browser+PG로 검증한다.

운영 command는 `inspect_auth_rate_limit_key_slot.py --slot NEXT --output <redacted.json>`→`prepare_auth_rate_limit_key_rotation.py --pending-key-artifact <path> --expected-consumer-sha <sha> --expected-version <n> --approval-token-file <path> --apply`→bridge deploy→`check_auth_rate_limit_consumer_rollout.py --output <artifact>`→`activate_auth_rate_limit_key_rotation.py --rollout-artifact <path> --expected-version <n> --approval-token-file <path> --apply`→cleanup releases→`finalize_auth_rate_limit_key_rotation.py --rollout-artifact <current-only-artifact> --expected-version <n> --approval-token-file <path> --apply` exact 순서다. 각 state transition은 별도 operation-bound token을 쓴다. inspect는 key ID/encoding만, state-changing CLI는 dry-run 기본이고 key bytes를 argv/artifact/log에 쓰지 않는다.

사용자 계정은 웹/API에서 hard delete하지 않는다. 현재 `/admin/users/delete/<id>` route와 `templates/auth/user_list.html` 삭제 control은 제거해 모든 role에서 GET/POST 모두 404로 만들고, 퇴사·접근 차단은 `ADMIN_SET_USER_ACTIVE {is_active:false,reason}`만 쓴다. 비활성화 transaction은 User row·username·과거 assignment/OrderEvent/SecurityLog의 참조를 보존하고 target session을 전부 revoke하며 audit에 actor/target/reason을 남긴다. 개인정보 보유기간 만료에 따른 익명화/삭제는 웹 command가 아니라 법무·보존정책 승인을 받은 별도 spec과 maintenance CLI로만 설계한다. 이 roadmap은 승인되지 않은 ad-hoc SQL/user row delete를 허용하지 않는다.

고위험 ops CLI의 `--approved-by-admin-user-id` 입력은 승인 증거가 아니므로 전부 폐기한다. `ops_approval_requests(id UUID PK,operation_type,scope_sha256,artifact_sha256,expected_version,expected_generation,nonce_hash,expires_at,state=PENDING|APPROVED|RESERVED|CONSUMED|EXPIRED|REVOKED,approved_by_user_id,approved_principal_version,approved_at,reservation_id,reserved_at,reservation_expires_at,consumed_at,operator_identity_hash,result_sha256,row_version,created_at)`가 정본이다. operator는 `create_ops_approval_request.py --operation <exact-enum> --scope-file <canonical-redacted.json> --expires-in-seconds 900 --output <protected-token.json>`으로 PENDING row와 random256-bit one-time token을 만들 수 있지만 approver를 지정할 수 없다. active ADMIN이 공용 WRITE-GUARD 뒤 `/admin/ops/approvals/<opaque-id>`에 자기 session+current password 재인증+CSRF/Origin으로 들어가 operation, artifact/state hash, expected version/generation, expiry를 확인해야 APPROVED가 된다. 값/secret/PII는 masked detail만 보이고 approver identity와 principal version은 session/DB에서만 취한다.

approval manifest에 등록된 모든 **고위험 state-changing CLI**는 `--approval-token-file <protected-token.json>`만 받고 exact operation/scope/artifact/version/generation을 재계산한다. manifest 밖 routine worker/정책 스캔은 token을 요구하지 않으며, 고위험 mutation CLI가 manifest에 없으면 startup/readiness가 red다. same DB면 approval row와 principal row를 `FOR UPDATE`해 active ADMIN+동일 version을 확인하고 one-time consume와 target mutation/audit를 같은 transaction에 commit한다. cross-DB control은 primary에서 같은 검증 뒤 5분 RESERVED를 commit한다. **RESERVED는 취소 불가 exact authorization snapshot**이므로 이후 role/deactivate/password change는 신규 reservation만 막는다. target DB audit의 unique `(approval_id,reservation_id,operation_scope_sha256)`와 target mutation을 한 tx로 commit한 뒤 primary를 CONSUMED로 finalize한다. 5분 내 target commit0이면 EXPIRED/mutation0; crash retry는 target audit가 있으면 result hash 대조 뒤 finalize만 하고, target0이면 lease 뒤 같은 token/operation만 resume한다. APPROVED→RESERVED 전 만료/비활성 approver/role·principal-version 변경/nonce 재사용/동시 consume는 mutation0이다. `reconcile_ops_approval_reservations.py`는 양쪽 read-only 대조로 finalize 또는 alert하며 임의 rollback하지 않는다.

`docs/harness/foms_ops_approval_operations.json`은 `{schema_version,operations:{operation_id:{owner_packet,cli,scope_schema,artifact_source,expected_version_source,expected_generation_source,db_mode=SAME|TARGET_RESERVED,consume_strategy}}}` exact SSOT이고 CLI AST inventory와 양방향 비교한다. scope는 RFC 8785 JCS object `{schema_version,operation_id,packet_id,target_ids_or_family,phase,artifact_sha256,expected_version,expected_generation}` exact fields다. 해당 없는 값은 explicit `null`, identifiers는 정렬·중복0, PII/secret0이다. **seed+append 규정(`foms_bugfix_packet_tests.json`과 동일):** OPS-APPROVAL-00이 아래 owner 표의 모든 `operation_id`를 `cli=null`로 seed하고, 각 소비 packet은 자기 `owner_packet`인 operation의 `cli`/`scope_schema`만 원자적으로 채운다. 타 행 수정·신규 operation 무단 추가는 test가 red로 거부하며, manifest↔CLI 양방향 불일치는 RELEASE-GATE-00과 해당 packet PR에서 강제한다.

| owner | exact operation IDs | exact scope source |
|---|---|---|
| BACKFILL-ARTIFACT-00 | `BACKFILL_APPLY,BACKFILL_REAUTHORIZE,BACKFILL_ARTIFACT_PURGE` | packet+phase+manifest+mapping+composite/run version |
| CUTOVER-MODE-01 | `CUTOVER_DRAIN_BEGIN,CUTOVER_DRAIN_ABORT,CUTOVER_MARK` | family+readiness artifact+fence version+generation |
| SESSION-SIGNING-STATE-00 | `SIGNING_CUTOVER_PREPARE,SIGNING_ROTATION_PREPARE,SIGNING_RECOVERY_PREPARE` | key-ID artifact+consumer SHA+state version/generation |
| SESSION-SIGNING-SECRET-01 | `SIGNING_FORCE_ENTER,SIGNING_CUTOVER_ACTIVATE,SIGNING_FORCE_EXIT,SIGNING_LEGACY_FINALIZE,SIGNING_ROTATION_ACTIVATE,SIGNING_ROTATION_FINALIZE,SIGNING_COMPROMISE_ACTIVATE,SIGNING_RESCUE_ROLLFORWARD` | rollout/quiescence/smoke/diagnosis artifact+state version/generation |
| AUTH-ACCOUNT-01 | `AUTH_RATE_BOOTSTRAP_PREPARE,AUTH_RATE_BOOTSTRAP_ACTIVATE,AUTH_RATE_ROTATION_PREPARE,AUTH_RATE_ROTATION_ACTIVATE,AUTH_RATE_ROTATION_FINALIZE` | auth key/rollout artifact+state version/generation |
| CHANNEL-INBOUND-ORDER-01 | `CHANNEL_CREATE_ENABLE,CHANNEL_CREATE_DISABLE,CHANNEL_RECOVERY_CREATE,CHANNEL_RECOVERY_IGNORE,CHANNEL_RETENTION_EXTEND,CHANNEL_KEY_ROTATION_PREPARE,CHANNEL_KEY_ROTATION_ACTIVATE,CHANNEL_KEY_ROTATION_FINALIZE` | receipt/global state+key/readiness artifact+version/generation |
| WDC-LINK-FENCE-00 | `WDC_LINK_FREEZE,WDC_LINK_ABORT,WDC_LINK_CANONICAL` | topology+fingerprint/rollout+state version/generation; SEPARATE만 `TARGET_RESERVED` |
| DELETE-RETENTION-01 | `DELETE_RETENTION_APPLY` | exact order-ID file hash+before+dependency/export artifact+expected count hash |
| OFFLINE-01 | `OFFLINE_LOCAL_RECOVERY_APPROVE` | inventory hash+schema+order-ID hash |

`FOMS_OPS_CONTROL_ROOT`는 repo/worktree/profile/OneDrive·동기화·network share·reparse-point 밖 absolute path다. Windows inheritance off+exact operator SID/SYSTEM ACL만 지원하고 다른 OS는 fail-closed한다. token schema는 `{schema_version,approval_id,one_time_secret_b64url,operation_id,scope_sha256,expires_at}`이며 root 아래 random filename으로 atomic create한다. raw token은 backup/artifact/git/log0, consume/expire/revoke 뒤 directory entry를 제거한다. 삭제 실패는 access-deny quarantine+CRITICAL alert이며 secure erase를 과장하지 않는다.

signing secret는 `foms/services/security/signing_keys.py` 한 provider와 custom `RotatingSessionInterface`만 사용한다. current root env 변수명은 `FOMS_SIGNING_KEY_CURRENT`이고(NEXT 슬롯 `FOMS_SIGNING_KEY_NEXT`, legacy raw는 `FOMS_SIGNING_LEGACY_FLASK_RAW_B64URL`/`FOMS_SIGNING_LEGACY_WAM_RAW_B64URL`와 구별), `inspect_signing_key_slot.py --slot CURRENT`가 읽는 env가 이것이다. root env 값은 padding 없는 base64url을 strict decode한 **exact 32 bytes**다. `HKDF-SHA256(salt=b"FOMS_SIGNING_V1",length=32)`의 versioned info label은 `flask-session`, `wam-launch-token`, `wam-entry-token`, `wam-short-link`, `wam-session-token` exact 5개이며 중복/미등록 label은 startup 실패다. key ID는 `base64url(SHA256(b"FOMS_KEY_ID_V1\0"+root)[:16])`이고 root/subkey는 log·artifact에0, key ID만 허용한다. golden vector가 env decode, 5개 derived bytes와 key ID를 고정한다. ACTIVE/ROTATING/CURRENT_ONLY에서 새 artifact는 DB `active_key_id`에 해당하는 derived key로만 sign한다. session/WAM root·legacy raw key·auth-rate-limit key를 서로 또는 Channel의 비밀 없는 stable hash domain에 재사용하지 않는다.

`security_signing_state(id=1,mode=EMPTY|READY|ACTIVE|CURRENT_ONLY|ROTATION_READY|ROTATING,maintenance_mode=OFF|AUTH_ONLY,maintenance_started_at,generation,session_epoch,wam_not_before,active_key_id,previous_key_id,pending_key_id,previous_not_after,legacy_cutover_mode=BRIDGE|FORCE_REAUTH,legacy_flask_not_after,legacy_wam_not_after,grace_seconds,row_version,prepared_consumer_sha,prepared_key_artifact_sha256,prepared_rollout_artifact_sha256,rescue_deployment_sha,prepared_at,activated_at,updated_at,updated_by_admin_user_id)` singleton과 `wam_entry_nonces(nonce_hash PRIMARY KEY,subject_hash,expires_at,consumed_at,created_at)`가 multi-replica 정본이다. 이 schema/model, pure `signing_key_format.py`(decode/key-ID only), legacy/key-slot inspect artifact와 prepare CLI만 **SESSION-SIGNING-STATE-00** additive expand PR이 먼저 배포한다. 기존 runtime은 새 table/env를 읽지 않고 migration은 `mode=EMPTY,maintenance_mode=OFF,generation=0` seed 외 cookie/token 의미를 바꾸지 않는다.

최초 전환은 `audit_legacy_signing_material.py`가 실제 Flask `SECRET_KEY`와 WAM module-import key를 **별도로** fingerprint해 env provenance, decoded length와 known defaults(`dev-secret-key-CHANGE-IN-PRODUCTION`, `dev-foms-secret-key-123`)를 값 없이 판정한다. 두 key가 모두 random≥32-byte이고 known/compromised가 아닐 때만 global `legacy_cutover_mode=BRIDGE`다. 둘 중 하나라도 absent/default/short/compromised면 두 domain 모두 `FORCE_REAUTH`로 묶어 mixed-mode rolling 의미를 만들지 않는다. BRIDGE raw bytes는 각각 `FOMS_SIGNING_LEGACY_FLASK_RAW_B64URL`/`FOMS_SIGNING_LEGACY_WAM_RAW_B64URL`로만 전달한다. FORCE_REAUTH는 두 legacy env/grace 0이며 정상 legacy와 forged artifact를 구분할 수 있다고 주장하지 않는다.

BRIDGE zero-downtime 순서는 (1) `SESSION-SIGNING-STATE-00` 배포, (2) legacy audit, (3) Railway에 current root(`FOMS_SIGNING_KEY_CURRENT`)와 두 허용 raw env를 secure inject하되 old runtime은 이를 무시, (4) `inspect_signing_key_slot.py --slot CURRENT --output <redacted.json>`이 key ID/encoding only artifact를 만들고 `prepare_signing_key_cutover.py --pending-key-artifact <path> --expected-consumer-sha <sha> --legacy-audit <artifact> --expected-version <n> --approval-token-file <path> --apply`가 CLI env의 CURRENT key ID와 artifact를 대조해 pending ID/artifact hash/global mode/grace/expected SHA를 기록한 deadline-null `EMPTY→READY`만 수행, (5) READY bridge consumer를 모든 serving replica에 배포한다. READY+BRIDGE는 Flask/WAM 모두 기존 raw 방식으로만 sign/verify하므로 mixed replica도 호환되고 current-derived artifact는0이다. `check_signing_consumer_rollout.py`가 serving SHA100%, READY capability/key IDs/health를 검증해 artifact hash를 DB에 기록하며 old replica/traffic가 남으면 STOP한다. (6) `activate_signing_key_cutover.py --mode bridge --rollout-artifact <path> --expected-version <n> --approval-token-file <path> --apply`가 artifact/SHA/key ID를 lock 재검증하고 DB clock에서 legacy deadlines, active=pending, READY→ACTIVE를 한 commit에 쓴다. 모든 replica는 요청마다 state를 읽어 즉시 current-sign/legacy-verify-only다. bridge deploy 실패는 READY/deadline 불변이라 old rollback 가능하고 ACTIVE 뒤 non-state-aware rollback은 STOP/roll-forward only다.

FORCE_REAUTH는 raw env/grace0이지만 **AUTH_ONLY 전** 복구 image를 먼저 검증한다. READY+FORCE-capable consumer를 `maintenance_mode=OFF`로 all-replica 배포하면 legacy serving 의미는 유지하되 private synthetic route에서 pending-key cookie/WAM round-trip, nonce, DB outage fail-closed를 실행하고 실제 사용자용 current artifact는0이다. `check_signing_consumer_rollout.py --phase FORCE_PREPARED`가 exact serving/rescue deployment SHA100%, key IDs, synthetic smoke를 artifact와 DB에 기록한다. 실패는 아직 traffic/DB 의미가 바뀌지 않아 old image rollback 가능하다.

그 다음 사용자 공지→`enter_signing_force_maintenance.py --rescue-rollout-artifact <path> --expected-version <n> --approval-token-file <path> --apply`로 `maintenance_mode=AUTH_ONLY`→`capture_signing_quiescence.py --deployment-artifact <path> --stability-seconds 30 --output <quiescence.json>` 순서다. AUTH_ONLY consumer는 health/private readiness와 PII-free/no-store maintenance HTML(ETA+request_id)만 정상이고 public auth/session/WAM issue·verify는503이다. maintenance page request는 허용하지만 `signing_runtime_quiescence(deployment_id,replica_id,auth_issue_inflight,session_verify_inflight,wam_issue_inflight,wam_verify_inflight,last_seen_at)`의 모든 counter0+fresh replica100%가 30초 유지돼야 한다. artifact schema는 `{schema_version,state_version,deployment_ids,replicas,counter_maxima,stability_started_at,captured_at,canonical_sha256}`이고 raw request/user0이다. `activate_signing_key_cutover.py --mode force-reauth --rollout-artifact <path> --quiescence-artifact <path> --expected-version <n> --approval-token-file <path> --apply`가 deadlines=DB now,epoch+1,wam_not_before=now,active=pending,READY→ACTIVE를 commit하되 maintenance는 유지한다. private current-key cookie/WAM smoke 뒤 `exit_signing_force_maintenance.py --smoke-artifact <path> --expected-version <n> --approval-token-file <path> --apply`로 OFF를 만든 다음 정상 업무를 복구한다.

post-activation smoke 실패는 AUTH_ONLY를 유지하고 same rescue deployment를 정확히1회 재배포한다. 다시 실패하면 `diagnose_signing_smoke_failure.py --state-version <n> --smoke-artifact <path> --output <redacted-diagnosis.json>`가 `CONSUMER_IMAGE|KEY_MATERIAL`만 분류한다. CONSUMER_IMAGE는 current key를 지원하는 state-aware descendant fixed rescue image를 all-serving으로 배포하고 `check_signing_consumer_rollout.py --phase ACTIVE_RESCUE`+private smoke가 green일 때만 exit한다. KEY_MATERIAL은 `prepare_signing_emergency_recovery.py --next-key-artifact <path> --expected-version <n> --approval-token-file <path> --apply`→active+fresh NEXT rescue all-serving/pending smoke→`activate_compromised_signing_key_rotation.py`→old absent release/current smoke 순서다. 분류/roll-forward도 실패하면 5분 warning/10분 incident를 계속 유지하고 OFF 금지다. known/legacy key나 old image는 다시 열지 않는다.

ACTIVE runtime에서 Flask session은 epoch, 모든 신규 WAM token은 `iat`/nonce를 가진다. auth/WAM query는 singleton epoch/key ID/cutoff를 process cache 없이 검증한다. 신규 entry issue는 nonce row를 insert하고 exchange는 `UPDATE ... WHERE consumed_at IS NULL AND expires_at>clock_timestamp() RETURNING` 한 건만 성공한다. DB unavailable은 `503 AUTH_DEPENDENCY_UNAVAILABLE`, session/WAM 발급 0이며 Redis/process-local replay fallback은 금지한다. BRIDGE verifier는 Flask 2.3.3 exact `salt=cookie-session,key_derivation=hmac,digest=SHA1,TaggedJSON`과 WAM four salts, itsdangerous `key_derivation=django-concat,digest=SHA1`만 쓰고 signed timestamp의 route TTL와 domain DB deadline을 모두 통과해야 한다. 성공한 legacy session/token은 current-derived artifact로 즉시 교환한다. ACTIVE 이후 raw/previous/pending key로 신규 sign하지 않는다.

FORCE cutoff 뒤 old session/WAM link는 401 loop나 raw signature error가 아니라 1280×800/390×844/1024×768에서 PII-free/no-store `WAM_LINK_EXPIRED` 화면을 보인다. `다시 로그인`과 `새 링크 요청`만 제공하고 return target은 server allowlist의 same-origin route name+opaque ID로만 보존한다. current smoke green 전에는 이 화면에서도 신규 link를 발급하지 않는다.

최초 grace 종료는 `finalize_signing_legacy_cutover.py --rollout-artifact <current-only-artifact> --expected-version <n> --approval-token-file <path> --apply`가 두 deadline 경과+legacy env 제거/all-serving을 확인해 `ACTIVE→CURRENT_ONLY`로 전이한다. 정상 rotation은 (1) CURRENT_ONLY/previous slots empty에서 `FOMS_SIGNING_KEY_NEXT`를 먼저 inject, (2) `inspect_signing_key_slot.py --slot NEXT --output <artifact>`와 expected bridge SHA를 `prepare_signing_key_rotation.py --pending-key-artifact <path> --expected-consumer-sha <sha> --expected-version <n> --approval-token-file <path> --apply`가 env와 대조해 pending ID/generation+1을 기록하고 deadline-null ROTATION_READY, (3) active CURRENT old+NEXT new bridge를 all-replica deploy하되 DB active old로만 sign하고 pending signature는 거부, (4) `check_signing_consumer_rollout.py --phase ROTATION_READY --output <artifact>`의 SHA/key-ID100% 뒤 `activate_signing_key_rotation.py --rollout-artifact <path> --expected-version <n> --approval-token-file <path> --apply`가 previous=old, active=new, pending null, previous deadline=DB now+grace, ROTATING을 commit한다. 이어 cleanup release는 **CURRENT=new, PREVIOUS=old, NEXT unset**으로 all-replica 배포해 artifact를 남긴다. deadline 뒤 PREVIOUS를 제거한 release가100% serving일 때만 `finalize_signing_key_rotation.py --rollout-artifact <current-only-artifact> --approval-token-file <path> --apply`가 `ROTATING→CURRENT_ONLY`; 따라서 다음 rotation의 NEXT는 비어 있다. deadline 내 bridge/cleanup rollback은 key-ID mapping으로 호환되지만 activation 뒤 old/non-state-aware image는 STOP이다. overlap/pending slot/SHA 불일치나 deadline 선기록은409다.

active root compromise는 key 제거 한 줄로 처리하지 않는다. emergency FORCE rotation은 AUTH_ONLY→fresh NEXT inspect/prepare→active+NEXT rescue all-serving/private pending smoke→30초 quiescence artifact→`activate_compromised_signing_key_rotation.py --rollout-artifact <path> --quiescence-artifact <path> --approval-token-file <path> --apply`가 active=new,previous/pending=null,old deadlines=now,epoch+1,WAM cutoff=now commit→CURRENT=new/old·NEXT absent release→private current smoke→CURRENT_ONLY/OFF 순서다. 실패는 위 diagnosis/fixed-image 또는 fresh-key roll-forward branch를 쓰며 compromised verify/old rollback0이다.

active ADMIN은 항상 1명 이상이다. 신규 `system_invariants(key PK,version)`의 singleton `active_admin` row를 migration에서 seed하고, ADMIN create/role change/is_active change와 bootstrap CLI가 모두 이를 `SELECT ... FOR UPDATE`한 뒤 proposed active ADMIN count≥1을 검증한다. 자기 deactivate는 금지하고 두 ADMIN의 concurrent deactivate는 한 건만 성공, 다른 건 `409 LAST_ACTIVE_ADMIN`이며 실패 transaction의 field/session/audit 변화 0이다. public `/register` GET/POST는 staging/production을 포함한 모든 deployed env에서 404와 mutation 0이며 local도 명시 test-only opt-in 없이는 disabled다. user 생성은 ADMIN UI/command만 허용하고 최초 ADMIN은 STARTUP-ADMIN-01 CLI가 같은 invariant row+advisory lock+bootstrap marker로 정확히 한 명만 생성한다.

기존 Order의 `CLAIM_DRAWING`, SALES/DRAWING/CONSTRUCTION assignment set/release/batch와 `SET_INSTALLATION_CREW`만 Order If-Match+idempotency, sorted Order row lock, version+event를 사용한다. 신규 Order 생성 transaction 안의 initial SALES owner는 생성 idempotency receipt로 보호하고 `mutation_version=1`과 assignment를 함께 commit하므로 If-Match 예외다. 생성 후 이 Order-scoped SET/replace는 예외 없이 If-Match를 요구한다. crew master는 worker row revision, shipment reference는 SystemSetting revision, account/chat/task 등은 각 절에 선언한 child/account revision domain을 사용하며 Order version/event를 만들지 않는다. legacy worker name은 active User exact 1명일 때도 authorization assignment로 자동 승격하지 않고 crew master로만 safe backfill한다. 실제 app assignee는 SecurityLog/history가 단일 user를 지지할 때만 별도 mapping하며, 0명/복수/외주는 manual CSV+ADMIN/MANAGER reason 없이는 AUTH-01 enforcement를 켜지 않는다.

emergency override는 등록된 정상 command의 role/team/assignment 또는 허용 edge를 우회할 때만 쓴다. 정상 expected-stage command를 ADMIN/MANAGER가 실행하는 것은 override가 아니다. `OrderEvent`는 normal runtime에서 update/delete하지 않는 **application append-only** 기록이다. cryptographic/DB immutable이라고 표현하지 않으며, web permanent delete는 제거하고 retention maintenance CLI만 명시적 예외로 둔다.

### 2.2 persisted 상태 정본

```text
RECEIVED → MEASURE → DRAWING → CONFIRM
         → PRODUCTION → CONSTRUCTION → CS → COMPLETED
```

- `data/erp_quest_templates.json`, `foms/services/order_timeline_v3.py`, `foms/services/orders/stage_override.py`, archived process blueprint가 이 8단계를 지지한다.
- main-stage 정본은 `structured_data.workflow.stage`와 indexed mirror `orders.erp_stage_code`다.
- `orders.status`는 현재 main stage·물류·hold·AS·delete가 섞인 legacy display projection이며 정본이 아니다. 항상 workflow와 같다고 가정하거나 모든 mismatch를 repair하지 않는다.
- projection 우선순위는 `DELETED > ON_HOLD > AS_* > logistics_status > main stage`다. migration 동안만 dual-write하고 신규 query는 각 canonical axis를 읽는다.
- `shipment.logistics_status` enum은 `NONE|MEASURED|REGIONAL_MEASURED|SCHEDULED|SHIPPED_PENDING`만 허용하고 `SET_LOGISTICS_STATUS`가 변경한다. `ON_HOLD`는 별도 `workflow.hold`다. legacy `HAPPYCALL`/`SHIPMENT`는 현재 writer가 없는 display alias라 신규 canonical 값이나 command로 만들지 않는다. workflow 정본이 함께 있으면 그 stage를 유지하고 server-owned `structured_data.meta.legacy_status_code` enum `HAPPYCALL|SHIPMENT`에 backfill-only로 보존한다. migration dual-read 동안 기존 `order.status` alias는 유지하지만 모든 consumer 이관 뒤 projection은 alias를 새로 emit하지 않는다. workflow가 없거나 history와 충돌하면 state manual CSV `axis=LEGACY_ALIAS` 없이는 enforce를 중단한다.
- AS는 current cycle transition에서 계산한 `as_lifecycle.current_status = NONE|RECEIVED|IN_PROGRESS|COMPLETED` read projection인 별도 overlay다. `AS_RECEIVED/AS/AS_COMPLETED`를 main stage로 쓰지 않는다.
- 시공 완료는 `CS`로만 전이한다. CS 완료만 `COMPLETED`로 전이한다.
- 삭제는 stage가 아니라 orthogonal soft-delete command다.
- 일반 advance command는 인접 전이만 가능하다. construction rework는 별도 정상 command로 `drawing_error→DRAWING`, `measurement_error→MEASURE`, `product_defect→PRODUCTION`, `site_issue→CONSTRUCTION` edge만 허용한다.
- 그 밖의 비인접 전이는 ADMIN/MANAGER emergency override + reason + application append-only event가 필수다.

### 2.2.1 orthogonal state command

| 축 | canonical path/column | command·계약 |
|---|---|---|
| main stage | `workflow.stage` + `erp_stage_code` | STATE service만 변경 |
| logistics | `shipment.logistics_status` | `NONE|MEASURED|REGIONAL_MEASURED|SCHEDULED|SHIPPED_PENDING`, `SET_LOGISTICS_STATUS`, main stage 불변 |
| hold | `workflow.hold.{active,held_at,held_by,reason}` | hold/release, main stage 불변 |
| AS | `as_lifecycle.cycles[]` + `current_cycle_id` | cycle은 append-only ID history, 아래 AS command registry, 기존 주문 main stage 불변 |
| production run | `production.runs[]` + `current_run_id` | status `IN_PROGRESS|COMPLETED|SUPERSEDED`; start/product-defect rework마다 UUID run, step/defect/quest scope 보존 |
| construction run | `construction.attempts[]` + `current_attempt_id` | attempt status `IN_PROGRESS|READY|COMPLETED|REWORKED`; terminal attempt 이력 보존, attempt 없음이 not-started |
| delete | `deleted_at` + soft-delete metadata | delete/restore service, main stage 불변 |
| legacy projection | `order.status` | 위 축에서 계산; 직접 쓰기 금지 |

AS command registry:

| command | from→to | actor | main stage·event |
|---|---|---|---|
| `CREATE_AS_ORDER` | Order DRAFT + AS child draft, body `{draft_id,as_content,shipping_scheduled_date?}` | STAFF/CS/SALES 또는 ADMIN/MANAGER | Order를 main `CS`로 finalize + AS RECEIVED cycle/evidence + initial version/events 한 tx. 일반 AS_REGISTER와 별도 |
| `AS_REGISTER` | NONE 또는 이전 cycle COMPLETED→새 RECEIVED, body `{draft_id,as_content,shipping_scheduled_date?}` | assigned CONSTRUCTION 또는 STAFF/CS/SALES, ADMIN/MANAGER; main stage `CS|COMPLETED` | 새 incident/cycle ID, content max 5000, ISO shipping date optional, evidence claim, `AS_REGISTERED`; 중복 409 |
| `AS_SCHEDULE` | current RECEIVED/IN_PROGRESS, body `{cycle_id,visit_date,visit_time?}` | STAFF/CS/SALES, ADMIN/MANAGER | ISO date 필수, visit_time은 `HH:MM` 또는 생략/null, exact current cycle, `AS_SCHEDULED`, main 불변. 기존 date-only PC/mobile 입력을 보존 |
| `AS_UNSCHEDULE` | current RECEIVED/IN_PROGRESS, body `{cycle_id,reason}` | STAFF/CS/SALES, ADMIN/MANAGER | reason 1..500, visit date/time을 명시적 transition으로 clear, `AS_UNSCHEDULED`, main 불변. UI의 빈 날짜 저장은 이 command를 호출 |
| `AS_START` | current RECEIVED→IN_PROGRESS, body `{cycle_id,reason,description}` 각 1..500/5000자 | STAFF/CS/SALES, ADMIN/MANAGER | cycle에 reason/description, `AS_STARTED` |
| `AS_COMPLETE` | current IN_PROGRESS→COMPLETED, body `{cycle_id,note}` note 최대 5000자 | STAFF/CS/SALES, ADMIN/MANAGER | 같은 cycle, note+`as_completed_date`, `AS_COMPLETED` |
| `AS_REOPEN` | current cycle COMPLETED→RECEIVED, body `{cycle_id,reason}` reason 1..500 | STAFF/CS/SALES, ADMIN/MANAGER; main stage `CS|COMPLETED` | 오완료 되돌리기. **같은 cycle ID** 유지, `AS_REOPENED` |

cycle schema는 `{cycle_id,opened_at,opened_by,initial_content,initial_shipping_date,transitions[]}`다. core는 immutable이고 schedule/start/complete/reopen은 `{seq,command,from,to,payload,actor_id,at}` transition을 append한다. status/visit/reason/note/completed_at은 마지막 유효 transition에서 계산한 read projection이며 임의 in-place rewrite가 아니다. 새 `AS_REGISTER`만 cycle을 append하고 `current_cycle_id`를 교체하므로 과거 content/schedule/note/evidence가 보존된다. `foms/api/cs/as_orders.py`와 `field_update.py`의 AS direct writes는 이 registry로 이관하고 `as_completed_date` generic field write는 제거한다. 기존 AS row는 `order.status`, history, as_info로 **자동 추정·수정하지 않고** read-only audit 결과가 단일 해석인 건만 backfill한다. 모호한 건은 manual mapping CSV+reason이 없으면 STATE-AS-01을 중단한다.

Construction run registry:

| command | predicate·body | 결과 |
|---|---|---|
| `CONSTRUCTION_START` | main=`CONSTRUCTION`, assigned actor, current attempt 없음 또는 previous current가 terminal `REWORKED|COMPLETED` | 새 UUID attempt를 append하고 current ID 교체, `IN_PROGRESS`, started actor/time, `CONSTRUCTION_STARTED`; 같은 key replay, active attempt 중 새 key 409 |
| `REGISTER_CONSTRUCTION_EVIDENCE` | body `{attempt_id,attachment_id,kind}`; kind=`before|after|signature`; attachment의 purpose/order/attempt/kind가 current attempt와 exact match, 미claim, assigned actor | attachment claim + evidence ref + version + event 한 tx. after≥2/signature≥1가 되면 attempt `IN_PROGRESS→READY` |
| `CONSTRUCTION_COMPLETE` | attempt=`READY`, required construction quest complete, hold inactive | attempt COMPLETED + main CS + fresh CS quest, transition/event/outbox 한 tx. 미충족은 409, 불변 |
| `CONSTRUCTION_REWORK` | current attempt=`IN_PROGRESS|READY`, reason enum | current를 `REWORKED`로 종결하고 이력 보존 + 표 2.2 reason edge로 main 이동. 이후 main이 CONSTRUCTION으로 재진입하면 새 attempt만 시작 가능 |

rework reset registry:

| reason→target | quest/run reset | drawing confirmation·assignment·queue |
|---|---|---|
| `measurement_error→MEASURE` | target 이후 active quest를 SUPERSEDED history로 남기고 fresh MEASURE quest; current production run도 SUPERSEDED | current drawing revision은 STALE history, receipt/customer confirmation invalidate; 모든 ID assignment 보존; SALES measurement queue 1건 |
| `drawing_error→DRAWING` | downstream active quest SUPERSEDED; DRAWING quest는 만들지 않음 | current revision RETURNED+system rework reason, receipt/customer confirmation invalidate; assignment 보존; assigned DRAWING queue 1건 |
| `product_defect→PRODUCTION` | downstream quest SUPERSEDED, fresh PRODUCTION quest와 UUID production run append; step/defect projection은 새 run에서 빈 값 | drawing receipt/customer confirmation 보존; assignment 보존; production queue 1건 |
| `site_issue→CONSTRUCTION` | downstream quest SUPERSEDED, fresh CONSTRUCTION quest; REWORKED attempt는 history로 두고 active attempt 없음 | drawing/production confirmation 보존; assignment 보존; assigned construction queue 1건, 새 START 필수 |

SUPERSEDED quest/run은 update/delete하지 않고 `{superseded_at,reason,source_attempt_id}` terminal transition을 append한다. stale quest approval, old production run step, old construction evidence는 409와 변화 0이다.

Quest 정본은 `structured_data.quests[]`와 `structured_data.workflow.current_quest_id`다. immutable core는 `{quest_id UUID,stage,required_team,created_at,created_by,source_command,transitions[]}`이고 approval/status/supersede는 `{seq,command,actor_id,team,payload,at}` transition append로만 기록한다. 한 주문에 current ID는 0/1개이며 그 ID가 가리키는 non-terminal quest만 current다. 새 stage 진입/rework/receipt는 이전 current를 필요 시 SUPERSEDED로 종결하고 fresh UUID로 current를 교체한다. 모든 approve와 quest-gated command body는 `quest_id`를 요구하며 current ID 불일치는 `409 STALE_QUEST`, 변화 0이다. stage 문자열로 첫 quest를 고르는 fallback과 GET lazy create는 제거한다.

Quest의 최종 approval transaction만 internal `REQUEST_MEASUREMENT` 또는 `COMPLETE_MEASUREMENT`를 호출해 `RECEIVED→MEASURE`, `MEASURE→DRAWING`을 수행한다. 별도 public stage endpoint는 없다. DRAWING quest는 현 제품 흐름처럼 비활성화하고 transfer command가 도면 작업 완료의 정본이다. CONFIRM quest는 별도 approval endpoint로 완료할 수 없고 `CUSTOMER_CONFIRM` transaction이 dynamic `required_team=SALES|CS`의 실제 actor approval을 원자 기록·완료한다. PRODUCTION/CONSTRUCTION/CS quest 승인은 prerequisite만 기록하고 stage를 쓰지 않으며 각 전용 command만 전이한다. quest로 전용 gate를 우회하면 `409 STAGE_COMMAND_REQUIRED`, Order/version/event 변화 0이다.

Drawing revision 정본은 `structured_data.drawing.revisions[]`와 `current_revision_id`, `receipt_revision_id`, `customer_confirmed_revision_id`, `customer_confirmation_quest_id`, `current_revision_request_id` projection이다. final revision immutable core는 `{revision_id UUID,parent_revision_id nullable,source=WIZARD_PENDING|UPLOAD_DRAFT,attachment_ids[],created_at,created_by,transitions[]}`이고 DRAFT resource는 2.7 child table에만 존재하다 final transfer transaction에서 attachments와 함께 정확히 한 final UUID revision으로 claim된다. transition은 `{seq,command,from,to,request_id?,actor_id,payload,at}`이며 status enum은 `TRANSFERRED|RECEIPT_CONFIRMED|RETURNED|CANCELLED|STALE`; core/files/과거 transition은 update/delete하지 않는다. partial unique-equivalent invariant는 current revision 0/1, open revision request 0/1, receipt/customer-confirm IDs가 current revision과 일치하고 linked customer confirmation quest가 COMPLETE일 때만 production gate true다.

Main-stage handoff registry:

> team 정규화: 아래 "current quest required team과 actor.team 일치" 판정에서, §2.1 (a) 분기(active MEASURE 계정 존재)일 때 actor의 `team=MEASURE`는 `SALES`로 정규화해 `required_team=SALES`인 measurement quest를 승인할 수 있다. (b) 분기(active MEASURE 0)면 정규화가 없고 measurement quest는 SALES/CS actor가 승인한다. 이름 폴백은 AUTH-01이 제거하므로 정규화 없이 문자열 동등비교만 하면 STAFF/MEASURE의 measurement 승인이 403된다.

| command | actor·predicate | transition/result |
|---|---|---|
| internal `REQUEST_MEASUREMENT` | current quest required team과 actor.team 일치(team=MEASURE는 §2.1 (a)에서 SALES 정규화), main RECEIVED, 최종 quest approve tx | RECEIVED→MEASURE, fresh MEASURE quest, `MEASUREMENT_REQUESTED` |
| internal `COMPLETE_MEASUREMENT` | current quest required team과 actor.team 일치(team=MEASURE는 §2.1 (a)에서 SALES 정규화), main MEASURE, measurement quest complete | MEASURE→DRAWING, DRAWING quest 미생성, `MEASUREMENT_COMPLETED` |
| `TRANSFER_DRAWING_REVISION` | explicit DRAWING assignee, current DRAWING | current revision ID/file/event 생성, drawing status TRANSFERRED, stage 유지; 기존 customer confirmation invalidate |
| `SET_DRAWING_REVISION_REQUEST_CHECK` | explicit DRAWING assignee, current status RETURNED, body `{revision_request_id,checked}` | exact open request의 checklist를 boolean transition으로 기록; stale 409. retransfer는 current request `checked=true` 필수 |
| `ACK_DRAWING_ORDER_CHANGE` | explicit DRAWING assignee 또는 현재 revision participant, body `{change_token}` | exact current token 첫 ack만 drawing ack transition+Order version/event 1; 같은 token replay는 저장 receipt 반환, version/event 0 |
| `REQUEST_DRAWING_REVISION` | explicit SALES-domain assignee, exact current revision/file IDs. status TRANSFERRED+main DRAWING 또는 CONFIRMED+main CONFIRM | TRANSFERRED면 stage 유지, CONFIRMED면 origin stage/status를 저장하고 CONFIRM→DRAWING. 둘 다 status RETURNED, customer confirmation invalidate, `DRAWING_REVISION_REQUESTED` |
| `CANCEL_DRAWING_REVISION` | request actor 또는 ADMIN/MANAGER, current status RETURNED, exact request/origin revision, request 뒤 신규 transfer 없음 | 저장된 exact origin stage/status/receipt/customer confirmation을 복원하고 quest 규칙대로 fresh current quest를 생성, `DRAWING_REVISION_REQUEST_CANCELLED`; 신규 transfer/stale request면 409 불변 |
| `CANCEL_DRAWING_TRANSFER` | explicit DRAWING assignee 또는 해당 transfer actor; ADMIN/MANAGER assignment bypass는 reason 필수. body `{revision_id,reason}` | exact current TRANSFERRED revision, receipt/customer confirmation/후속 revision·request가 없어야 함. revision에 CANCELLED append, previous non-cancelled revision/status를 current projection으로 복원. final revision attachment/object는 감사 retention 동안 보존하고 runtime delete outbox를 만들지 않는다. 한 tx/version/event, stale 409 |
| `CONFIRM_DRAWING_RECEIPT` | explicit SALES-domain assignee, current transferred revision | drawing status CONFIRMED, DRAWING→CONFIRM, fresh CONFIRM quest, `receipt_revision_id`와 confirmed actor/time 기록 |
| `CUSTOMER_CONFIRM` | body `{current_drawing_revision_id}`, receipt revision 일치. current CONFIRM quest `required_team=SALES`면 explicit SALES-domain assignee, `required_team=CS`면 active `STAFF/CS` team-wide가 actor다. 반대 team은 403; ADMIN/MANAGER가 대신하면 emergency override reason 필수 | stage CONFIRM/status CONFIRMED 유지, `customer_confirmed_revision_id`와 실제 required-team actor approval/completion을 한 tx; receipt actor/SALES assignment는 보존 |
| `PRODUCTION_START` | STAFF/CS/SALES/PRODUCTION, main CONFIRM, drawing status CONFIRMED, current revision receipt+customer confirmation exact, CONFIRM quest complete | UUID production run+fresh PRODUCTION quest, CONFIRM→PRODUCTION; confirmation/quest 누락·stale면 409 |
| `PRODUCTION_COMPLETE` | body `{run_id}`, STAFF/CS/SALES/PRODUCTION, main PRODUCTION, exact current run IN_PROGRESS, production quest complete, hold inactive | run COMPLETED + PRODUCTION→CONSTRUCTION + fresh CONSTRUCTION quest, `PRODUCTION_COMPLETED`; 5-step/defect는 신규 hard gate 아님, old/stale run은 409 |
| `CS_COMPLETE` | STAFF/CS, main CS, CS quest complete, hold inactive, AS cycle NONE/COMPLETED | CS→COMPLETED, `CS_COMPLETED` |

revision request는 origin `{stage,status,receipt_revision_id,customer_confirmed_revision_id,customer_confirmation_quest_id,quest_state,quest_transition_snapshot}`을 request core에 저장하고 기존 open CONFIRM quest를 SUPERSEDED로 종결한다. cancel은 과거 quest를 재활성화하지 않는다. origin customer confirmation이 있었으면 fresh quest ID에 restored approval+COMPLETE transition을 append하고 `customer_confirmation_quest_id`가 이를 가리키며 `workflow.current_quest_id=null`이다. origin이 receipt-only/pending이면 fresh OPEN CONFIRM quest를 만들고 current ID가 이를 가리킨다. `CUSTOMER_CONFIRM`도 quest를 COMPLETE로 종결한 뒤 current ID를 null로 하고 linked confirmation quest ID를 저장한다. 새 transfer는 returned request를 terminal REPLACED로 남기고 old quest는 superseded 상태를 유지하며, receipt 때만 fresh OPEN CONFIRM quest를 만든다. revision request/new drawing transfer는 기존 customer confirmation을 원자 invalidate한다. stale revision/request/quest로 CUSTOMER_CONFIRM 또는 PRODUCTION_START를 호출하면 409, DB/event 변화 0이다.

Production subcommand registry:

- `SET_PRODUCTION_STEP {run_id,key,done}`: key=`cut|edge|paint|assemble|inspect`, STAFF/CS/SALES/PRODUCTION, main PRODUCTION, exact current run, Order If-Match/version/idempotency, event `PRODUCTION_STEP_CHECKED`.
- `REPORT_PRODUCTION_DEFECT {run_id,reason}`: reason=`자재 불량|가공 오류|파손|기타`, STAFF/CS/SALES/PRODUCTION, main PRODUCTION, exact current run, cap 20, Order If-Match/version/idempotency, event `PRODUCTION_DEFECT_REPORTED`.
- 기존 `/production/hold`는 제거하고 STATE-OVERLAY-01의 `HOLD_ORDER/RELEASE_HOLD`가 `workflow.hold`를 소유한다. main PRODUCTION에서는 STAFF/PRODUCTION이 실행할 수 있고 `production.hold`는 backfill 후 read projection만 남긴다.
- `ACK_PRODUCTION_CHANGE {change_token}`: STAFF/CS/SALES/PRODUCTION, 현재 read-model token 일치. Order row/JSON은 바꾸지 않고 idempotency receipt+`PRODUCTION_CHANGE_ACK`만 기록하며 같은 token 중복 event 0이다.

Shipment writer registry:

- `UPDATE_SHIPMENT_SETTINGS {site_extra,construction_time,vehicle,trip}`: STAFF/CS/SALES/SHIPMENT 또는 ADMIN/MANAGER. `site_extra` 최대 20개 exact `{text,color}`, text 500자, color는 `black|red|blue|green|orange|purple|brown|navy`만 허용하고 invalid는 전체 422, 나머지 string 200자. drawing/construction names는 이 body에서 금지하고 각각 assignment/crew command를 쓴다.
- `APPLY_AS_RECOMMENDATION {shipment_order_id,shipment_version,as_order_id,as_version,cycle_id,force}`: STAFF/CS/SALES/SHIPMENT 또는 ADMIN/MANAGER. 두 Order를 ID 순으로 lock하고 source construction date와 active crew IDs를 재계산한다. public `AS_SCHEDULE` 권한은 넓히지 않고, 이 orchestrator만 호출 가능한 internal policy `AS_SCHEDULE_FROM_SHIPMENT`가 SHIPMENT actor를 허용한다. exact current cycle에 source=`SHIPMENT_RECOMMENDATION` transition과 `SET_INSTALLATION_CREW`를 한 transaction에서 실행한다. 기존 수동 일정이 있고 force=false면 409; force=true면 overwritten value도 transition payload에 보존한다.
- `CANCEL_AS_RECOMMENDATION {shipment_order_id,shipment_version,as_order_id,as_version,cycle_id,recommendation_transition_id}`: 위 actor. 해당 recommendation 뒤 수동 schedule/crew 변경이 없을 때만 이전 schedule/crew snapshot을 typed compensation transition으로 복원한다. 후속 변경이 있으면 409 불변이다.
- recommendation preview/prewarm은 pure read/cache warm이며 Order mutation/version을 바꾸지 않는다.

### 2.3 transition service 원자 계약

신규 `foms/services/orders/order_transition_service.py`를 상태 변경의 유일한 경로로 만든다.

```python
transition_order(
    db, *, order_id, target_stage, expected_stage,
    actor, policy_id, source_screen, reason=None,
    idempotency_key, emergency_override=False,
)
```

한 DB transaction에서 다음을 수행한다.

1. auth 후 receipt key `(actor_id, policy_id, idempotency_key)`와 canonical request hash를 계산한다. hash 입력은 method, route template, 정렬된 resource IDs, canonical JSON body다.
2. `INSERT ... state=PENDING ON CONFLICT DO NOTHING RETURNING id`로 receipt 소유권을 먼저 잡는다. 동시 loser는 unique transaction 완료를 기다린 뒤 committed receipt를 읽는다. SUCCESS+same hash는 **If-Match/stage 검사 전에** 저장된 status/body/ETag를 `200` replay하고, same key+different hash는 `409 IDEMPOTENCY_KEY_REUSED`다. owner transaction rollback 시 PENDING insert도 함께 rollback되며 loser는 bounded retry로 소유권을 다시 시도한다. committed orphan PENDING은 생성되지 않는다.
3. receipt owner만 resource ID 정렬 순으로 `SELECT ... FOR UPDATE` Order row lock을 잡는다.
4. If-Match와 active order·`expected_stage` 검증. 불일치는 `409 REVISION_CONFLICT` 또는 `409 STAGE_CONFLICT`.
5. role/team/assignment/quest/command predicate 검증.
6. 전이 내부 `_set_main_stage`만 `workflow.stage`, `erp_stage_code`, stage metadata/history를 함께 기록하고 legacy `order.status` projection을 재계산한다. orthogonal state는 덮지 않는다.
7. 실제 DB 값의 `before`와 target `after`로 registry가 지정한 legacy-compatible OrderEvent를 생성한다.
8. SecurityLog, mutation version, receipt SUCCESS+response와 필요한 `domain_side_effect_outbox` 행을 같은 transaction에서 commit한다. 일부 commit 금지.

클라이언트 command 계약:

- dashboard/detail 응답은 order별 `mutation_version`을 DOM data와 JSON에 제공한다.
- 한 번의 사용자 intent마다 UUID idempotency key를 만들고 terminal 응답까지 같은 key를 재사용한다.
- timeout/network retry는 같은 key와 같은 If-Match를 보낸다. 성공 replay는 원 성공 결과를 `200`으로 반환한다.
- terminal 성공 뒤 control을 제거하거나 최신 stage로 갱신한다. 새 화면·새 key로 이미 지난 전이를 요청하면 `409 STAGE_CONFLICT`다.
- double click은 in-flight 동안 request 1개만 전송한다. 실패하면 카드 위치를 유지하고 control을 다시 활성화한다.

command registry는 `policy_id`, allowed from/to, assignment mode, legacy event type/payload schema, quest creation, cache invalidation families, notification/outbox, response schema를 포함한다. `domain_side_effect_outbox(id,source_domain,order_event_id?,notification_event_id?,address_learning_request_id?,wizard_pending_id?,upload_ticket_id?,upload_draft_id?,chat_attachment_id?,order_import_artifact_id?,effect_type,payload,dedupe_key,state,attempts,next_at,lease_owner,lease_token,lease_expires_at,last_error,created_at,completed_at,dead_at)`는 source transaction 안에 INSERT한다. `source_domain=ORDER_EVENT|NOTIFICATION_EVENT|ADDRESS_LEARNING|WIZARD_PENDING|UPLOAD_TICKET|UPLOAD_DRAFT|CHAT_ATTACHMENT|ORDER_IMPORT_ARTIFACT`와 nullable FK 중 정확히 하나만 non-null이고 domain과 일치해야 하는 DB CHECK/FK를 둔다. effect matrix는 Order command notification/cache/geocode→ORDER_EVENT, urgent push/realtime→NOTIFICATION_EVENT, address learning geocode→ADDRESS_LEARNING, pending/ticket/draft/chat/import artifact storage delete→동명 child source다. mismatched/orphan source insert는 DB/contract test에서 거부한다. DB unique `(effect_type,dedupe_key)`로 중복을 막고 `side_effect_worker_heartbeats`가 readiness 정본이다. dedicated worker가 `FOR UPDATE SKIP LOCKED`, 60초 lease·expired reclaim·최대 10회 후 DEAD를 적용한다. 5초 delivery loop와 같은 process의 300초 bounded upload ticket/draft/import-artifact expiry scan이 새 child-source STORAGE_DELETE row를 만들며 advisory lock/limit/progress/scan lag metric을 쓴다. success 30일, DEAD 180일, heartbeat <30초/oldest lag <60초/expiry scan lag <360초/DEAD=0이 deploy gate다. request post-commit nudge는 latency 최적화일 뿐 delivery 보장이 아니다. 기존 퇴역 Channel outbox와 혼합하지 않는다.

migration ownership은 final schema와 분리한다. SIDEFX-00이 source registry와 초기 7-domain one-of schema를 만들고, ORDER-IMPORT-01이 `order_import_artifacts` table과 `order_import_artifact_id`/`ORDER_IMPORT_ARTIFACT` CHECK/FK를 **한 additive migration**으로 등록한다. 그 migration 전에는 import source insert가 불가능하며, SIDEFX-00이나 worker가 import business table을 선행 생성하지 않는다.

runtime dependency는 registry의 `readiness_class`로 다음처럼 고정한다. 어떤 class든 source transaction의 outbox INSERT 자체가 실패하면 business transaction도 rollback한다. env flag를 request가 자동 변경하지 않고, 표의 capability만 effective-disabled로 계산해 UI를 숨기고 typed 503을 반환한다.

| readiness class | exact effect/command | unhealthy runtime 계약 | owning mode·불변성 |
|---|---|---|---|
| `REQUIRE_DELIVERY` | URGENT-CALL-01의 `NOTIFICATION_EVENT` realtime/push | heartbeat≥30s, oldest lag≥60s 또는 DEAD>0이면 send 전 `503 DEPENDENCY_UNAVAILABLE` | `FOMS_NOTIFICATION_DELIVERY_MODE`; notification/event/outbox 0 |
| `REQUIRE_EXPIRY_SCAN` | order/chat upload ticket issue, `UPLOAD_DRAFT` create, wizard pending create, import source/error artifact create | heartbeat≥30s 또는 expiry scan lag≥360s이면 create/issue 전 503 | order/chat=`FOMS_UPLOAD_MODE`, wizard pending=`FOMS_DRAWING_REVISION_MODE`, import=`FOMS_ORDER_MUTATION_MODE`의 해당 capability만; child/object/outbox 0 |
| `DEGRADED_OK` | ordinary Order notification/cache/geocode, address-learning 202, Channel side effect, terminal/rejected `STORAGE_DELETE` | outbox insert 가능하면 commit/202+`delivery_state=PENDING`, warning+degraded metric; cache는 mutation receipt로 fresh read | main owning mode 유지; app read는 terminal child/object를 즉시 숨김, worker 복구 후 idempotent delivery/delete |

deploy gate는 세 class 모두 worker green을 요구하지만, 배포 후 일시 장애가 이미 성공한 core order mutation을 거꾸로 실패시키지 않도록 위 runtime 차이를 지킨다.

read-after-write와 cross-actor handoff를 분리하되 둘 다 worker poll에 의존하지 않는다. `order_mutation_receipts` parent는 random 128-bit opaque UUID `read_receipt_id` UNIQUE, actor, policy, `read_expires_at=commit+2분`을 갖고 `(actor_user_id,read_expires_at)` cleanup index를 둔다. `order_mutation_read_resources(read_receipt_id,order_id,resulting_version,changed_cache_families_json,PRIMARY KEY(read_receipt_id,order_id))` child가 단건·batch·copy·import 최대 1000건을 정규화하며 `(order_id,read_receipt_id)` index를 둔다. response는 `{mutation_receipt,resources:[{order_id,resulting_version,changed_cache_families}]}`와 `Cache-Control: private, no-store`다. 단건 client도 `resources[0]`을 사용하고 singular alias는 REV-99 뒤 제거한다.

changed family는 각 resource마다 `{ORDER_DETAIL:<id>,ORDERS_INDEX,STAGE:<before>,STAGE:<after>} ∪ registry.extras`로 계산하고 before/after가 없으면 해당 원소만 생략한다. bulk delete/copy/import/2-Order orchestration은 모든 resource의 union을 만든다. `cache_family_generations(family_key PRIMARY KEY,generation BIGINT,updated_at)`를 두고 business transaction이 family key 정렬 순으로 row를 lock/upsert해 generation을 증가시킨 뒤 child receipt와 outbox를 같은 commit에 쓴다. cache entry는 생성 시 family generation vector를 저장하고 모든 family/list/detail read는 relevant key를 한 indexed query로 읽어 하나라도 다르면 cache에 Order row가 없어도 DB read model을 재생성한다. 이 DB barrier가 별도 PRODUCTION/CONSTRUCTION actor와 Redis eviction 실패에도 source old card 0/destination new card 1을 보장한다. global stage row lock wait·generation query/refresh TTFB를 production-like perf test하고 p95 lock wait 50ms 또는 기존 TTFB budget을 넘으면 merge를 중단해 측정 기반 sharding spec을 먼저 낸다.

initiator client는 다음 fragment/API fetch에 `X-FOMS-Mutation-Receipt`를 보내고 header는 access/RUM log에서 redact한다. full-page navigation은 command response의 `__Host-FOMS-Mutation-Receipt` Secure+HttpOnly+SameSite=Lax+Path=/+Max-Age=120 cookie를 쓴다. cookie는 최근 parent UUID 최대 4개만 서명해 담고 URL/referrer/JS에 노출하지 않으며 logout/actor switch에서 폐기한다. server는 actor/TTL/resource membership을 한 indexed join으로 검증한다. explicit header actor mismatch는 403, invalid/expired cookie는 제거 후 normal generation-barrier read를 수행한다. 임의 client family/version/cache-bust는 거부한다. Redis family eviction은 commit 직후 best-effort로 실행하고 실패는 warning+durable outbox retry지만 DB generation 때문에 stale read를 허용하지 않는다. PostgreSQL race/browser gate는 cache preload 후 worker pause+Redis eviction 강제 실패 상태에서 단건, batch assignment, copy/import, 2-Order orchestration을 각각 실행해 initiator와 별도 destination actor 모두 source 0/destination 1, resources/version exact, duplicate 0을 확인한다.

정적 guard allowlist는 canonical `_set_main_stage`, legacy projection, hold/logistics/AS/delete service와 신규 order/draft constructor의 initial stage, predeploy backfill helper뿐이다. 그 밖의 직접 `workflow["stage"]`/`erp_stage_code`/`order.status` assignment를 금지한다. 현 `sync_erp_flat_columns`에서는 stage mirror write를 제거하고 flat form 동기화가 stage를 건드리지 않는 것을 회귀 테스트한다.

### 2.4 주문 mutation revision

초 단위 `structured_updated_at`은 동시 저장을 구분하지 못한다. 선행 `REV-00`에서 Alembic으로 `orders.mutation_version INTEGER NOT NULL DEFAULT 1`, `order_mutation_receipts`와 공용 lock/receipt helper를 추가한다.

- GET 응답: `ETag: "order-{id}-v{mutation_version}"`와 JSON `mutation_version`.
- 각 **Order row/scalar/structured JSONB/main·orthogonal state** mutation PR은 touched endpoint와 client에 If-Match, Order version increment, idempotency를 함께 적용한다. attachment/chat/revision-DRAFT child-only mutation은 2.7의 자체 row/collection revision을 쓴다. WDC order-estimate link는 WDC DB의 match collection revision/receipt domain이며 Order JSONB를 쓰지 않는다.
- 모든 writer와 consumer 100% 이관 후 `REV-99`가 미분류 writer를 정적 검사하고 전역 428 enforcement를 켠다. 중간 단계에서 미이관 endpoint에 428을 일괄 적용하지 않는다.
- 최종 Order-row/JSONB/state mutation은 If-Match 필수. 누락 `428 PRECONDITION_REQUIRED`, stale `409 REVISION_CONFLICT`와 최신 version 반환.
- 신규 draft 생성은 If-Match 예외. 생성 응답의 version부터 이후 요청에 사용한다.
- receipt unique key는 `(actor_user_id, policy_id, idempotency_key)`이고 scope hash, request hash, response status/body, resulting resource versions, created/expires를 저장한다. key는 UUID, 최대 64자다. replay window 24시간 뒤 동일 key는 `409 IDEMPOTENCY_KEY_EXPIRED`. REV-00은 expiry 의미와 `(expires_at,id)` index만 소유하고 delete tool/schedule은 만들지 않는다. `expires_at+6일` retention purge CLI·schedule·dry-run/limit/progress/nonzero exit는 **REV-CLEANUP-01만** 소유한다.
- bulk는 `orders:[{id,mutation_version}]`를 받고 row ID 순으로 lock한다. 하나라도 불일치면 전체 rollback한다.
- PostgreSQL 동시성 테스트가 정본이다. SQLite 테스트만으로 완료 판정하지 않는다. simultaneous same-key/same-hash 요청은 둘 다 동일 success body/version을 받고 business write/event는 1개, same-key/different-hash는 한쪽만 성공하고 다른 쪽은 409여야 한다.

#### 2.4.1 Order constructor와 복사

모든 신규 일반 주문은 `CREATE_ORDER {draft_id?,structured_data,form_columns,sales_owner_user_id?}` 한 constructor를 사용한다. STAFF/SALES|CS 생성자는 자기 ID를 default owner로 쓸 수 있고 active STAFF/SALES|CS target을 명시할 수 있다. ADMIN/MANAGER는 `sales_owner_user_id`가 필수이며 누락/ADMIN target은 422다. 그 밖의 STAFF와 VIEWER는 403이다. `/erp/orders/add`, JSON create, draft finalize는 이 service를 호출하고 독자적으로 `Order(...)`를 만들지 않는다. 한 transaction에서 validated item identity, main RECEIVED, `mutation_version=1`, `source=INITIAL_OWNER` SALES assignment, fresh RECEIVED quest, constructor event/receipt, geocode outbox를 commit한다. AS 전용 constructor는 `CREATE_AS_ORDER`만 main CS+AS cycle을 같은 transaction으로 요청할 수 있다.

`COPY_ORDER {orders:[{id,mutation_version}],sales_owner_user_id?}`는 ADMIN/MANAGER 또는 STAFF/CS|SALES만 실행한다. source rows를 ID 순으로 lock하고 all-or-none이며, 같은 key replay는 같은 새 Order ID 목록을 반환한다. 복사 allowlist는 form-owned customer/site/orderer/manager/notes, item product/spec/options, validated pricing mode/input/manual reason, 명시 form flags뿐이다. `received_date/time`은 복사 시각으로 새로 만들고 모든 measurement/construction schedule·actual payment confirmation/deposit settlement/cash receipt/calls·workflow/quests/assignments/crew/shipment/hold/AS·drawing/wizard/files/attachments·production runs/defects·construction attempts/evidence·delete metadata·WDC links·receipt/meta IDs는 복사하지 않는다. 모든 item UUID와 registry row를 새로 만들고 attachment/schedule item link는 0개다. 결과는 각각 main RECEIVED, version 1, fresh RECEIVED quest, initial SALES owner와 geocode outbox를 가진다. legacy `/bulk_action` copy와 `/api/orders/copy`는 이 service 하나를 호출하며 row별 commit/부분 성공/전체 column clone은 제거한다.

`IMPORT_ORDER_WORKBOOK {file,sales_owner_user_id}`는 ADMIN/MANAGER 전용이다. `.xlsx`, 최대 10 MiB/1000 data rows, exact template columns는 2.5 form-owned customer/site/orderer/manager/notes/item/spec/pricing/manual-reason/form flags뿐이고 status/AS/payment confirmation/settlement/quest/assignment/meta/ID column은 422다. active STAFF/SALES|CS owner ID는 upload 단위 필수다. workbook 전체를 먼저 schema/formula/type/length 검증하고 오류가 하나면 Order 0개와 row-numbered downloadable error report를 반환한다. 성공은 normalized file SHA-256+actor receipt로 idempotent all-or-none constructor batch를 실행하며 각 row fresh item IDs/quest/version/owner/geocode outbox를 가진다. `order_import_artifacts(id,actor_user_id,file_hash,object_key,kind=SOURCE|ERROR_REPORT,state=AVAILABLE|DELETE_PENDING|DELETED|QUARANTINED,expires_at,created_at)`는 server-derived private object key만 저장한다. source와 오류 report는 최대 24시간 뒤 scan provider가 DELETE_PENDING+`source_domain=ORDER_IMPORT_ARTIFACT` STORAGE_DELETE를 만들고 공용 worker가 삭제한다. import request는 expiry scan ready가 아니면 parse/upload 전 503이며 path/payload를 log하지 않는다.

Channel Function과 표준 Webhook은 이름이 비슷해도 transport/auth 계약을 공유하지 않는다. Function은 `PUT /api/channel/functions`만 허용하고 POST/GET은 405다. `CHANNEL_FUNCTION_ENABLED=true`인 deployed env는 `CHANNEL_FUNCTION_SIGNING_KEY_HEX`가 even-length valid hex이고 decode≥32 bytes, `CHANNEL_FUNCTION_CHANNEL_ID`가 nonempty가 아니면 fail-start한다. `CHANNEL_FUNCTION_ENABLED=false`면 Function blueprint 자체를 등록하지 않아 PUT/POST/GET 모두 404이며 secret의 존재만으로 route를 열지 않는다. false 전환은 ChannelTalk console의 Function 등록/호출을 먼저 disable한 redacted artifact와 provider error-rate 0을 preflight해야 하고, provider가 계속 호출 중이면 STOP한다. signature helper는 JSON parse 전에 exact raw body에 `HMAC-SHA256(bytes.fromhex(key),raw_body)`를 계산해 Base64 standard encoding한 값과 `X-Signature`를 constant-time 비교한다. missing/invalid signature는 401, invalid JSON/content type은 400이다. 검증된 body는 official common envelope `method,params,context.channel,context.caller`를 먼저 검사하고 configured channel ID와 active canonical User mapping을 확인한다. `params`는 Function method별 DTO이므로 `docs/harness/channel_function_methods.json`의 exact JSON Schema와 ChannelTalk sandbox에서 token/PII를 제거한 `tests/fixtures/channeltalk/function_<method>_provider.json`이 정본이다. 현재 top-level caller/channel+`params.text` fixture는 공식 common envelope와 달라 retired한다. 실제 registered `foms` method fixture/schema가 없으면 domain parser PR은 STOP하고 transport/signature tests만 진행하며, `params.inputs|input|trigger.attributes` 중 하나를 추정하거나 compatibility로 모두 허용하지 않는다. 성공은 HTTP 200 `{"result":object|array}`, 서명은 유효하지만 unknown method/invalid params/missing mapping/policy-denied/nonexistent Order인 domain failure는 존재·권한을 구분하지 않는 HTTP 200 `{"error":{"type":string,"message":generic}}`다. trusted context와 manager ID도 signature+channel match 뒤에만 사용한다.

표준 Webhook은 `POST /api/channel/webhooks?token=...`만 허용하고 Function `X-Signature` helper를 호출하지 않는다. `CHANNEL_INBOUND_ENABLED=true`인 deployed env는 random≥32-byte `CHANNEL_WEBHOOK_TOKEN_CURRENT`, exact `CHANNEL_WEBHOOK_CHANNEL_ID`, registered event-type manifest가 없거나 invalid하면 fail-start/readiness red다. `CHANNEL_INBOUND_ENABLED=false`면 Webhook blueprint 자체를 등록하지 않아 POST/GET 모두 404이며, false 전환은 ChannelTalk console의 Webhook 등록을 먼저 disable한 redacted artifact와 provider block/error-rate 0을 요구한다. provider가 계속 호출 중이면 STOP한다. group `Message`를 `CREATE_ORDER`로 등록한 경우에만 nonempty exact `CHANNEL_ALLOWED_GROUP_IDS`도 필수다. query token은 current와 rotation 중 `CHANNEL_WEBHOOK_TOKEN_PREVIOUS`를 timing-safe 비교하되 `CHANNEL_WEBHOOK_TOKEN_PREVIOUS_NOT_AFTER` UTC 10분 deadline 뒤 자동 거부하고 env 제거를 readiness가 강제한다. access/application/proxy log는 query string을 출력하지 않는 path-only format과 token redaction filter를 사용하며 canary request 뒤 current/previous token substring 0을 preflight한다. missing/wrong token은 401이다. 인증 후 tenant channel과 event/type별 source rule을 확인하기 전에 business payload를 parse/store하지 않는다. `message+push+chatType=group`은 exact channel+group allowlist, `message+push+chatType=userChat`과 `userChat|user` event는 exact channel+registered action을 쓰며 dynamic chat ID는 receipt/creation identity이지 global allowlist가 아니다. 그 외 Message chatType 또는 live fixture에 canonical channel field가 없는 type은 `CREATE_ORDER`를 금지하고 QUARANTINE한다. `docs/harness/channel_webhook_events.json`은 registered `event+type+chatType`별 fixture, identity/version/source/text field, action=`CREATE_ORDER|IGNORE|QUARANTINE`를 선언한다. 공식 common envelope `event,type,entity,refers`와 live redacted provider fixture만 허용하고, invented top-level `eventId`, `ref`, `entity.message` fixture는 retired한다. cross-channel/disallowed/unknown source 또는 schema는 아래 versioned stable hash+reason만 durable rejection audit로 남기고 raw payload/PII 0, provider retry를 막는 200 generic no-op을 반환한다.

Webhook durable receipt 정본은 `(provider,event,type,identity_hash_version,identity_hash)` unique, `payload_hash_version,payload_hash`, bounded masked metadata, `acceptance_class=CREATE_ACCEPTED|SOAK_IGNORED|REJECTED`, `canonical_input_envelope`, `input_key_id`, `accepted_at`, `recovery_not_after`, `legal_hold_approval_id`, `input_cleared_at`, state=`RECEIVED|PROCESSING|PAUSED_ACCEPTED|RECOVERY_REQUIRED|SUCCEEDED|QUARANTINED|IGNORED|RETENTION_EXPIRED`, error_code, created/updated timestamp와 created Order link를 가진다. `channel_inbound_jobs(receipt_id PRIMARY KEY FK,intent_hash_version,intent_hash,state=PENDING|PAUSED|PROCESSING|RECOVERY_REQUIRED|DONE|IGNORED|RETENTION_EXPIRED,lease_owner,lease_expires_at,attempt_count,last_error_code,created_at,updated_at)`가 receipt와 같은 transaction에 insert되는 ID-only queue다. CREATE_ACCEPTED에는 job이 정확히1개 있고 DEAD state는 없다. manifest는 event별 `receipt_identity_fields`, `creation_identity_fields`, `cross_event_correlation_fields`를 따로 선언하고 canonical fields만 쓴다. 모든 ID scalar는 NFC UTF-8, control/NUL 거부, byte length bound 뒤 8-byte big-endian length prefix로 연결한다. `identity_hash=SHA256(b"FOMS_CHANNEL_RECEIPT_V1\0" + LP(provider,event,type,chatType?,identity/version fields))`, `intent_hash=SHA256(b"FOMS_CHANNEL_INTENT_V1\0" + LP(provider,channel_id,creation_kind,creation_id))` exact v1이며 secret/session/signing key와 delimiter concat을 쓰지 않는다. `payload_hash`는 schema-validated registered payload projection의 RFC 8785 JCS UTF-8 bytes SHA-256 v1이고 query token/raw transport bytes는 제외한다.

예컨대 message push receipt는 message entity ID/version, userChat push receipt는 entity ID/version, user upsert receipt는 entity ID+version/updatedAt을 사용한다. order 생성 의도는 별도 `channel_order_creation_intents(provider,channel_id,intent_hash_version,intent_hash,state=RESERVED|SUCCEEDED|QUARANTINED,created_order_id,lease_owner,lease_expires_at,attempt_count,last_error_code,created_at,updated_at,PRIMARY KEY(provider,channel_id,intent_hash_version,intent_hash))`로 dedupe한다. userChat `refers.message.id`와 Message `entity.id`가 같은 첫 메시지를 가리키면 두 event 모두 같은 v1 intent로 수렴해 receipts2/Order1이다. correlation ID가 fixture에서 확인되지 않으면 exactly one event type만 `CREATE_ORDER`, 겹치는 type은 `IGNORE|QUARANTINE`이며 둘 다 추정 생성하지 않는다. group chat ID 자체를 intent key로 쓰지 않아 같은 group의 서로 다른 message2는 Order2, 같은 message retry는 Order1이다. first claimant만 intent lease를 잡고 canonical constructor+intent SUCCEEDED+receipt link를 한 tx에 commit하며 crash는 bounded job+intent lease reclaim/max-attempt terminal quarantine, paired/retry receipt는 완료 intent의 같은 Order link를 참조하거나 manifest IGNORE다.

stable receipt identity/version이 없으면 QUARANTINE하고 order0이다. `createdAt` type/plausibility는 검증하지만 오래된 valid event를 freshness gate로 거부하지 않는다. 동일 identity+동일 hash retry는 no-op200이고 다른 hash conflict는 original을 바꾸지 않는 PII-free append-only alert다. allowed CREATE는 raw provider JSON 대신 `{schema_version,event_type,channel_id,source_id,message_id,user_chat_id?,text}` allowlist를 RFC8785 JCS bytes로 만든다. `FOMS_CHANNEL_RECOVERY_KEY_CURRENT|PREVIOUS|NEXT`는 signing/auth와 독립인 padding 없는 base64url exact32 bytes다. envelope exact schema는 `{version=1,key_id,nonce_b64url,ciphertext_b64url,aad_sha256}`이고 nonce12 random bytes, AAD=`FOMS_CHANNEL_INPUT_V1\0+LP(receipt_id,identity_hash_version,identity_hash,payload_hash_version,payload_hash,schema_version)`다. AES-256-GCM decrypt는 AAD/hash/schema를 다시 검증한다. text는 UTF-8 1..8192 bytes, NUL/control 거부다. create-enabled acceptance transaction은 `accepted_at=DB now,recovery_not_after=accepted_at+30 days`, CREATE_ACCEPTED receipt+envelope+ID-only job을 함께 commit한 뒤에만2xx다. API/export/log에는 ciphertext/text/key0이다.

`channel_recovery_key_state(id=1,mode=CURRENT_ONLY|ROTATION_READY|ROTATING,generation,active_key_id,pending_key_id,previous_key_id,previous_not_after,row_version,prepared_consumer_sha,rewrap_checkpoint_receipt_id,updated_at)`가 key 정본이다. rotation은 NEXT inspect→`prepare_channel_recovery_key_rotation.py` deadline-null ROTATION_READY→current+NEXT all-serving(구 current encrypt, 둘 decrypt)→rollout artifact 뒤 `activate_channel_recovery_key_rotation.py`가 active=new/previous=old/ROTATING→신규는 new encrypt→`rewrap_channel_recovery_inputs.py --batch-size 500`이 nonterminal receipt를 ID 순 lock해 old AAD decrypt/new nonce+same AAD re-encrypt하고 checkpoint를 같은 tx에 commit→old-key live reference0+all-serving CURRENT=new/PREVIOUS=old/NEXT unset→PREVIOUS 없는 release100% 뒤 finalize/CURRENT_ONLY다. decrypt fault는 clear0, receipt/job RECOVERY_REQUIRED+CRITICAL alert다. referenced old key/env 제거 금지다.

7일/24시간/6시간 전 alert를 보내고 earliest unresolved deadline 24시간 전부터 provider CREATE intake와 global create를 false로 닫는다. 24시간 alert는 on-call ACK1시간을 release blocker로 요구한다. deadline 전 terminal CREATE/IGNORE 또는 `extend_channel_recovery_retention.py --receipt-id <id> --days 7 --legal-basis-code <enum> --approval-token-file <path> --apply`의 legal hold만 허용하고 cumulative extension은90일까지다. deadline에 둘 다 없으면 pre-approved 30-day privacy policy가 receipt/job을 `RETENTION_EXPIRED`, wrapped input envelope clear, visible CRITICAL incident/audit로 한 tx에 만든다. 이는 silent clear가 아니라 명시적 Order-loss terminal이며 release/readiness는 incident ACK+root-cause 전 red다. 90일 이상은 별도 legal spec 없이는 불가다.

`resolve_channel_inbound_recovery.py --receipt-id <id> --decision CREATE|IGNORE --reason <1..500> --approval-token-file <path> --apply`는 global/provider create=false여도 exact receipt 한 건만 처리하는 recovery executor다. CREATE는 receipt+intent를 lock하고 decrypt/constructor/intent success/Order link/job DONE/input clear를 한 tx에 commit한다. 일반 worker/global flag를 우회하지 않는다. IGNORE는 append-only reason+job IGNORED+input clear를 한 tx에 쓴다. invariant SQL은 CREATE_ACCEPTED 각 row가 정확히 하나의 partition인지를 검사한다: `SUCCEEDED+created_order`, `IGNORED+approval/reason`, `RETENTION_EXPIRED+incident_id`, 또는 live `PENDING|PAUSED|PROCESSING|RECOVERY_REQUIRED`+ciphertext. 합계가 accepted count와 다르면 readiness red다. SOAK_IGNORED는 분모가 아니다.

Channel inbound 자동 생성은 `CREATE_ORDER_FROM_CHANNEL {receipt_id,intent_hash}` internal command만 쓴다. worker는 DB receipt를 lock해 authenticated decrypt한 validated canonical input과 exact intent hash를 로드하고 queue/raw request를 신뢰하지 않는다. verified source, job+intent lease/reclaim/max10 attempts가 필수다. max10/owner missing/decrypt fault는 receipt+job을 RECOVERY_REQUIRED(또는 disable이면 receipt PAUSED_ACCEPTED+job PAUSED)로 같은 tx에 두고 envelope를 유지한다. ADMIN 대체/DEAD/auto quarantine0이다. canonical constructor, intent SUCCEEDED/created_order_id, paired links, job DONE, input clear와 masked result를 한 tx에 commit한다.

`channel_inbound_runtime_state(id=1,create_enabled,generation,updated_at,updated_by_admin_user_id)`가 create capability의 DB 정본이고 env는 desired state다. worker는 claim 전 일반 read, constructor transaction 시작 시 singleton `SELECT ... FOR KEY SHARE`로 env+DB가 모두 true인지 재검증하고 commit까지 유지한다. KEY SHARE는 worker끼리 병렬이지만 control CLI의 `SELECT ... FOR UPDATE`와 충돌하므로 disable이 기존 constructor 종료를 기다린 뒤 `create_enabled=false,generation+1`을 commit한다.

exact command는 `python tools/ops/set_channel_inbound_create_state.py --state enable|disable --expected-generation <n> --approval-token-file <path> --batch-size 1000 --apply`이고 dry-run이 기본이다. disable은 FOR UPDATE cutoff 뒤 PENDING/lease-reclaimed PROCESSING을 receipt PAUSED_ACCEPTED+job PAUSED/lease null로 bounded same-tx batches에 바꾼다. crash하면 worker도 DB false를 보고 동일 protocol을 끝낸다. PENDING/PROCESSING0일 때만 exit0이므로 성공 시점 뒤 global worker Order commit0이다. enable은 env flags, owner, dedicated service, key state/old-reference, heartbeat/lag/lease/recovery-scan, conservation, unresolved deadline/incident0을 검증해 eligible PAUSED만 resume한다. receipt-specific approved recovery는 enable gate와 별도다. invalid `inbound=false,create=true`는 effective false/readiness nonzero이고 provider disable→DB disable→pause0→blueprint404 순서다.

`CHANNEL_INBOUND_ENABLED=true`이면서 effective create=false인 planned soak는 auth/source/schema 뒤 masked SOAK_IGNORED receipt만200으로 남기고 intent/job/Order/input0이다. Channel job은 `railway-channel-inbound.toml` 전용 service만 처리한다. create=true readiness는 heartbeat≤15s, oldest PENDING≤60s, expired lease0, recovery scan≤360s, owner active, key reference/decrypt sample green, conservation exact, unresolved 24h/deadline/retention incident0이다. create=false의 PAUSED accepted는 backlog lag에서만 제외하고 recovery SLA/alerts에서는 제외하지 않는다.

#### 2.4.2 ERP 주문 견적

`foms/api/erp_estimates.py`의 main ERP estimate는 WDC와 다른 order child domain이다. `CREATE_ORDER_ESTIMATE`, `UPDATE_ORDER_ESTIMATE`, `DELETE_DRAFT_ORDER_ESTIMATE`, `CANCEL_ORDER_ESTIMATE {reason}`를 등록한다. ADMIN/MANAGER 또는 STAFF/CS|SALES만 parent Order read scope와 mutation policy를 모두 통과하며 VIEWER/타 주문 ID는 403이다. 모든 command는 parent Order를 먼저 lock하고 Order If-Match/idempotency/version/event를 사용한다. DRAFT만 child hard-delete할 수 있으나 `ORDER_ESTIMATE_DRAFT_DELETED` audit/event가 남고, ISSUED는 삭제하지 않고 reason 1..500의 CANCELLED transition을 append한다. estimate ID는 parent order와 exact match해야 하며 stale/mismatch/replay에서 child·Order version/event 불변 계약을 테스트한다.

### 2.5 Structured PUT 소유권

`PUT /api/orders/<id>/structured`는 incoming JSONB 교체가 아니라 fresh server snapshot에 아래 form path만 projection한다.

request envelope의 exact keys는 `{structured_data, received_date, received_time, notes, is_self_measurement, is_regional, construction_type, removed_item_dispositions}`다. `removed_item_dispositions`는 optional object `{<old item UUID>:'MOVE_TO_COMMON'}`이고 key는 old−new items 집합에만 허용한다. form은 clear intent도 보존하도록 날짜·시간·text 빈 문자열을 생략하지 않는다. outer `raw_order_text`, `structured_schema_version`, `structured_confidence`, `draft_token`은 이 endpoint에서 server-owned이며 client가 보내면 `400 UNKNOWN_FIELD`; `raw_order_text`는 별도 parse/import command만 변경한다. 현 `erp-order-shared.js`의 outer raw/schema/confidence 전송은 제거하고 기존 provenance가 보존되는 regression test를 둔다.

| 소유자 | path |
|---|---|
| Form | `parties.customer.{name,phone}`, `parties.orderer.name`, `parties.manager.name` |
| Form | `site.{address_main,address_detail,address_full}` |
| Form | `schedule.measurement.{date,time}`, `schedule.construction.{raw,date,time}` |
| Form | `notes.{phone_note,address_note,measurement_note}` |
| Form | `flags.{urgent,urgent_reason,factory2}` |
| Form | `payment.{deposit,discount,free_input,cash_receipt,balance_note}` |
| Form | validated `items` |
| Form columns | `received_date`, `received_time`, `notes`, `is_self_measurement`, `is_regional`, `construction_type` |
| Server calculated | `totals`, item `pricing`, normalized flat columns |
| Server owned | `entity_type`, `schema_version`, `confidence`, `totals`, `workflow`, `quests`, `assignments`, `settlement`, `calls`, `production`, `drawing_wizard`, `drawing`, `blueprint`, `drawing_status`, `drawing_transferred`, `drawing_confirmed_at`, `drawing_confirmed_by`, `drawing_current_files`, `drawing_transfer_history`, `last_drawing_transfer`, `drawing_assignees`, `construction`, `construction_fail_history`, `as_info`, `as_lifecycle`, `meta`, `estimate_preview`, `channeltalk_push`, `channeltalk_push_drawing`, `channeltalk_push_estimate`, `shipment` 전체, payment의 `deposit_confirmed`, `deposit_confirmed_at`, `deposit_confirmed_by`, `deposit_confirmed_by_user_id`, `balance_confirmed`, `balance_confirmed_at`, `balance_confirmed_by`, `balance_confirmed_by_user_id` |

전체 form body는 `schemas/erp_structured_form_v1.json`, item `$defs`는 `schemas/erp_order_item_v1.json`으로 구현하며 둘 다 `additionalProperties=false`다.

- `structured_data`는 required object다. 아래 form object/path는 optional이고, 생략은 fresh server snapshot 보존, 명시적 빈 string/빈 array는 clear다. object를 제공하면 표의 descendant 외 key는 거부한다.
- 모든 nullable form string은 `null` 대신 trim된 string으로 정규화한다. 이름 200자, 전화 50자, 주소 각 500자, note 5000자, 날짜 `YYYY-MM-DD` 또는 빈 문자열, 시간 `HH:MM` 또는 빈 문자열, `free_input` 10000자, `cash_receipt`/`balance_note` 2000자다.
- `payment.deposit`/`discount`는 integer `0..1_000_000_000_000`; client의 comma string은 전송 전 integer로 바꾼다. `schedule.construction.raw`는 1000자다.
- `flags.urgent`/`flags.factory2`, `is_self_measurement`/`is_regional`은 boolean만 허용한다. `urgent_reason`은 1000자이고 `urgent=false`면 빈 문자열로 저장한다.
- `received_date`는 `YYYY-MM-DD`, `received_time`은 `HH:MM`, top-level `notes`는 5000자다. `construction_type`은 `is_regional=true`일 때만 `하우드 시공|협력사 시공`, 아니면 null이다.
- `shipment.construction_workers`는 CREW-00 이후 form-writable이 아니다. active `order_installation_assignments`에서 만든 중복 없는 crew 표시명 projection(최대 20개·각 100자)이며 `SET_INSTALLATION_CREW`만 변경한다. authorization용 `order_assignments(CONSTRUCTION)`과 독립이다. DATA-01 client는 이 path 전송을 제거한다.

- `items`: array, 최대 100개. 각 item은 object이고 additionalProperties=false. `item_id` UUID v4, `product_name`, 정규화된 integer `price`, `pricing_mode=MANUAL|CATALOG`가 required다. `order_item_identities(item_id UUID PK,order_id,state ACTIVE|RETIRED,created_at,retired_at)`가 identity/tombstone 정본이고 attachment/schedule item_id는 이를 참조한다. client는 새 행 생성 때 UUID를 만들고, 서버는 Order lock 아래 registry insert/retire와 JSON projection을 한 tx로 처리한다. 한 번 저장된 ID는 immutable하고 reorder에도 유지하며 retired ID 재사용과 타 주문 ID를 거부한다. duplicate는 422, immutable/reuse/cross-order 위반은 409이며 item/attachment/schedule/version 변화 0이다. 완전히 빈 신규 행은 전송 전 제거하고, product_name만/price만 있는 partial 행은 inline validation 후 요청을 보내지 않는다.
- string keys: `product_name`(200), `spec`(1000), `spec_width/spec_depth/spec_height`(500), `internal/color/option_detail/handle/misc`(2000), `extra_input`(5000), `measurement_date/construction_date`(ISO 날짜 CSV 최대 10개).
- `price`: integer `0..1_000_000_000_000`.
- `spec_rows`: 최대 20개, exact keys `spec_width/spec_depth/spec_height`, 각 string 500자.
- `pricing_mode=CATALOG`: `pricing_input` exact keys는 `product_id` positive int, `width_mm` int `0..100000`, `options` 최대 100개, `manual_override` bool, `manual_override_reason` 최대 500자다. option은 exact `{category_id,option_id,quantity}` positive int이고 서버가 membership/current price를 lookup한다. override=true면 authorized actor와 1..500자 reason 필수; false면 reason은 없거나 빈 문자열이다.
- `pricing_mode=MANUAL`: `pricing_input`/product_id/options는 금지하고 `price`와 `manual_price_reason` 1..500자가 필수다. ADMIN/MANAGER 또는 STAFF+SALES/CS만 저장할 수 있다. 기존 catalog ID 없는 legacy item은 ITEM-ID-00 backfill에서 MANUAL+server-only reserved reason `legacy_import`로 시작한다. unchanged price read/save만 그 reason을 보존할 수 있고 신규 MANUAL item 또는 가격 변경은 사용자가 입력한 새 reason과 old/new price audit가 필수다.
- incoming `pricing`, `computed`, option price, `computed_at`은 server-owned다. CATALOG는 WDC `calculate_estimate` shared service로 재계산한다. actor·catalog 계산가·override가·reason 또는 MANUAL price/reason을 audit payload에 남긴다. unauthorized manual/override는 403; non-override CATALOG form price가 계산가와 다르면 409다.
- item/spec/pricing nested unknown key 또는 type/length 위반은 전체 요청 `422 SCHEMA_VALIDATION_FAILED`다.

오류 계약:

- exact outer envelope 밖의 `raw_order_text`, `structured_schema_version`, `structured_confidence`, `draft_token`과 unknown top-level key는 값이 같아도 항상 `400 UNKNOWN_FIELD`다.
- `structured_data` 안의 표 2.5 server-owned known path는 서버값과 같으면 호환 목적으로 제거하고 저장하지 않으며, 다르면 전체 요청을 `409 SERVER_OWNED_FIELD_CONFLICT`로 거부한다.
- 알려지지 않은 top-level/path는 `400 UNKNOWN_FIELD`.
- `totals`는 client 값을 무시하고 서버가 items와 payment form path에서 다시 계산한다.
- API request의 금액은 schema가 integer/range를 먼저 검증하며 음수·비수치·소수는 `422`다. `coerce_krw_amount`는 검증된 integer의 내부 계산과 legacy read/client display 정규화에만 쓰고 invalid request를 0으로 조용히 바꾸지 않는다. `free_input`은 `:`/`：` 뒤 금액과 숫자-only 줄을 합산하되 malformed/범위 초과 입력은 inline 차단 및 422다. `items_total=sum(item.price)`, `contract_total=items_total+free_input_amount`, `balance=max(0,contract_total-deposit-discount)`, `shipping_price=max(0,contract_total-discount)`로 고정한다. 현 JS의 `-100→100` digits-only 동작은 제거하고 Python/Node fixture를 동일하게 만든다.
- 신규 `foms/services/orders/structured_form_projection.py`가 projection, KRW coercion, totals를 소유하고 Python/Node shared fixture로 JS parity를 검증한다.
- `workflow.stage`는 structured body에서 제거한다. UI stage selector는 transition command를 사용한다.
- 성공 응답은 새 ETag/version과 적용된 form path를 반환한다.

#### 2.5.1 Measurement·AS 분류·창고 typed field

- `UPDATE_MEASUREMENT_CONTACT {address_main,address_detail,manager_name,phone}`: ADMIN/MANAGER 또는 STAFF/CS|SALES, field별 명시 clear와 2.5 length/schema, Order If-Match/idempotency/version/event. `foms/api/measurement/routes.py`와 `foms/api/erp_map.py::api_update_order_address`는 같은 projection service를 호출하고 주소가 바뀔 때 geocode outbox를 같은 transaction에 넣는다.
- `SET_REGIONAL_CHECK {field,value}`: ADMIN/MANAGER 또는 STAFF/CS|SALES, order가 `is_regional=true` 또는 `is_self_measurement=true`여야 한다. field는 `measurement_completed|regional_sales_order_upload|regional_blueprint_sent|regional_order_upload|regional_cargo_sent|regional_construction_info_sent`, value는 JSON boolean만 허용한다. `SET_REGIONAL_MEMO {memo}`는 같은 predicate에서 trim string 최대 5000자다. 둘 다 If-Match/idempotency/version/event를 쓰며 truthy string coercion과 모든-STAFF generic route를 제거한다.
- `ADD_ADDRESS_LEARNING {original_address,corrected_address}`는 Order writer가 아닌 별도 address-learning collection command다. ADMIN/MANAGER 또는 STAFF/CS|SALES만, 두 주소 trim 1..500자, 동일값/unknown key 422, actor당 60회/시간 rate limit, collection idempotency receipt와 SecurityLog를 사용한다. transaction은 `address_learning_requests(id,original,corrected,state=PENDING|ACTIVE|FAILED,actor_id,attempts,last_error,created_at,completed_at)` PENDING과 `ADDRESS_LEARNING_GEOCODE` outbox를 넣고 202를 반환한다. worker만 corrected address를 server-side geocode하고 finite timeout/retry 후 lat/lng 범위와 normalized result를 검증해 ACTIVE learning row를 한 transaction에 만든다. 최종 실패는 FAILED이며 usable learning row 0이다. client 좌표/외부 응답 주입과 request thread 외부 호출은 금지하고 Order/version은 변경하지 않는다.
- `SET_AS_CLASSIFICATION {cycle_id,field,value}`는 current AS cycle에서 ADMIN/MANAGER 또는 STAFF/CS|SALES가 실행한다. field는 `as_pending|as_blueprint|sales_delivery`, value는 JSON boolean이며 `shipment`의 server-owned read projection과 filter tab을 갱신한다. main stage와 AS lifecycle status/schedule은 불변이고 한 version/event만 기록한다. 새 cycle은 세 값을 false로 시작하며 schedule/unschedule/complete가 classification을 묵시적으로 바꾸지 않는다.
- `SET_CABINET_STATUS {status}`는 `is_cabinet=true` 주문에 ADMIN/MANAGER 또는 STAFF/PRODUCTION|SHIPMENT가 `RECEIVED|IN_PRODUCTION|SHIPPED`만 저장한다. `SET_SHIPPING_FEE {amount}`는 ADMIN/MANAGER 또는 STAFF/CS|SALES만 integer `0..1_000_000_000_000`을 저장한다. 둘 다 main/logistics/finance confirmation과 독립인 typed Order command로 If-Match/idempotency/version/event를 쓰며 generic field update와 digit coercion을 제거한다.

#### 2.5.2 OrderTask child domain

`order_tasks`에 `task_uuid`, `row_version`, `source=MANUAL|AUTOMATION|LEGACY`, `auto_key nullable`, `created_by_user_id`, `legacy_provenance`, `cancelled_at/by/reason`을 추가하고 status를 `OPEN|IN_PROGRESS|DONE|CANCELLED`로 제한한다. PostgreSQL partial UNIQUE `(order_id,auto_key) WHERE auto_key IS NOT NULL AND status IN ('OPEN','IN_PROGRESS')`와 lookup index를 두고 terminal history는 여러 행 보존한다. 신규 MANUAL/AUTOMATION creator는 NOT NULL, backfill한 LEGACY만 creator nullable을 허용하고 이름/시간으로 추정하지 않는다. title 1..255, due date ISO/null, owner team은 `CS|SALES|DRAWING|PRODUCTION|CONSTRUCTION|SHIPMENT`, owner user는 active하고 명시 team과 일치해야 한다. legacy pseudo-team `MEASURE`는 real User team을 새로 만들지 않고 canonical `SALES`로 이관한다. existing MEASURE task가 명시 owner user와 충돌하면 manual CSV 전에는 enforcement를 중단한다. automation/template도 measurement task owner를 SALES로 바꾸고 enum drift static test를 둔다. client가 arbitrary `meta`를 쓰지 못하고 manual meta는 exact `{note}` 최대 2000자만 허용한다.

- `CREATE_ORDER_TASK`, `UPDATE_ORDER_TASK`, `CANCEL_ORDER_TASK`는 parent Order read scope를 먼저 확인한다. 생성/재배정은 ADMIN/MANAGER 또는 STAFF/CS|SALES, 현재 owner user는 자기 task의 title/due/status를 변경할 수 있다. VIEWER와 unrelated STAFF는 403이다. delete는 reason 1..500의 CANCELLED transition으로 대체한다.
- command는 task If-Match+child idempotency receipt+row lock+TaskEvent/SecurityLog를 한 transaction에 쓰며 Order version은 바꾸지 않는다. stale/cross-order/invalid owner는 변화 0이다.
- automation은 public route가 아니라 typed internal `UPSERT_AUTO_TASK {order_id,auto_key,spec}` adapter다. parent Order business transaction 안에서 위 active-status partial unique를 기준으로 upsert하고 structured save와 같은 commit/rollback을 사용한다. 동시 동일 auto_key는 active task 1개, terminal 뒤 재발행은 새 history row 1개여야 한다. raw SQL/post-commit task write는 제거하고 system-owned title/team/meta는 manual API가 덮지 못한다.

### 2.6 Wizard·storage 소유권

- client-owned wizard state: `v`, `sheets`만.
- server-owned: pending child rows, version snapshot rows, updated actor/time, transfer metadata.
- `SAVE_WIZARD_STATE`, `CREATE_WIZARD_ASSET`, `IMPORT_ORDER_ATTACHMENT_TO_WIZARD`, `CREATE_WIZARD_SHEET_EXPORT`, `CREATE_WIZARD_TRANSFER_PENDING`은 explicit DRAWING assignee만 실행한다. 앞의 네 Order projection mutator는 Order row lock+If-Match+version/event를 사용하고, transfer-pending은 `drawing_wizard_pending(id,order_id,owner_user_id,object_key,state=READY|CLAIMED|DELETE_PENDING|DELETED|QUARANTINED,row_version,created_at,expires_at)` child row와 collection ETag를 사용한다. import source attachment는 exact same order/read scope여야 하고 object key는 server-derived prefix만 허용한다.
- incoming server-owned field가 있으면 `400 WIZARD_SERVER_FIELD`.
- sheet PNG는 서버가 생성한 exact prefix `orders/{order_id}/drawing_wizard/exports/`만 허용한다.
- 기존 invalid pending은 삭제하지 않고 quarantine 목록과 SecurityLog에 남긴다.
- 현재 transfer는 기존 object key를 참조하므로 `prepare_drawing_transfer(..., commit=False)`가 exact READY pending row와 현재 wizard state를 lock해 attachment materialization과 immutable `drawing_wizard_versions(id,order_id,revision_id,wizard_state_json,object_keys,created_at,created_by)` insert 준비를 반환한다. STATE-DRAWING-01이 pending CLAIMED, final revision, attachments, snapshot row, version/event/log를 **한 DB transaction**에 commit한다. client의 별도 `/version-snapshot`와 transfer 후 R2 write는 제거하며 snapshot은 기존 canonical object key만 참조한다.
- push/cache/realtime side-effect outbox 행은 transfer business transaction 안에 만들고, commit 후에는 worker nudge만 한다. worker 실패는 transfer DB 결과를 rollback하지 않으며 dedupe key로 retry한다.
- pending delete의 실제 object 삭제는 SIDEFX-00의 `STORAGE_DELETE` effect를 쓴다: business tx에서 child pending을 DELETE_PENDING으로 표시하고 outbox insert→공용 sweeper idempotent delete→child row DELETED. worker는 Order JSON을 쓰거나 Order version/event를 만들지 않는다. 실패는 lease retry/DEAD이며 object가 남아도 다른 주문에 attach할 수 없다.
- global preset은 `SAVE_WIZARD_PRESET {preset_id?,name,payload,settings_version}`/`DELETE_WIZARD_PRESET` 별도 SystemSetting domain이다. STAFF/DRAWING 또는 ADMIN/MANAGER, schema/length 검증, optimistic settings version, idempotency와 SecurityLog를 쓰며 Order version·assignment를 변경하지 않는다.

### 2.7 Direct upload ticket

client가 `folder`나 완성 key를 정하지 않는다. wizard export는 server-generated이므로 ticket 대상이 아니다.

| purpose | resource·completion target | 허용자 |
|---|---|---|
| `ORDER_ATTACHMENT` | order + category(`measurement|drawing|construction|as`) + optional committed `item_id`; OrderAttachment | ADMIN/MANAGER, STAFF/SALES/CS, explicit DRAWING assignee는 drawing category |
| `ORDER_BLUEPRINT` | order; unclaimed blueprint attachment, 이후 typed replace | ADMIN/MANAGER, STAFF/SALES/CS 또는 explicit DRAWING assignee |
| `DRAWING_GATEWAY_REVISION` | order + drawing revision DRAFT ID; gateway revision file | ADMIN/MANAGER 또는 explicit drawing assignee |
| `CONSTRUCTION_EVIDENCE` | order + current attempt ID + evidence kind; construction attachment | ADMIN/MANAGER 또는 assigned STAFF/CONSTRUCTION |
| `AS_EVIDENCE` | order + AS cycle DRAFT ID; AS attachment | ADMIN/MANAGER, STAFF/CS/SALES 또는 assigned STAFF/CONSTRUCTION |
| `CHAT_ATTACHMENT` | room ID; chat message attachment | active room member만. order ticket과 별도 namespace |

- VIEWER는 모든 purpose를 거부한다.
- 서버가 `order_id`, purpose, filename을 받아 권한·assignment를 확인한 뒤 exact key를 생성한다. ticket complete에서도 현재 authentication, purpose policy, active order/room, assignment, target resource state를 다시 검사한다. logout·role revoke·reassignment·soft-delete·draft finalize 뒤 complete는 consume/link 0으로 거부하고 orphan object cleanup을 예약한다.
- `order_upload_tickets`는 opaque token hash, user, order/room, purpose, category, immutable item_id, resource ID, completion target, exact key, content type, max bytes, expiry, state, resulting resource ID를 저장한다.
- complete는 ticket row lock, owner/order/purpose/key/expiry 검증, storage HEAD의 size/type 확인, attachment 연결과 consume을 한 transaction으로 처리한다.
- 같은 ticket retry는 purpose별 저장된 resulting resource/status/response body를 반환하는 idempotent success다.
- expiry는 900초, batch는 file마다 ticket 1개다. size/type은 `get_erp_media_max_size`와 `allowed_erp_attachment_file`을 재사용한다.
- 만료·포기 object cleanup job과 `(state,expires_at)` index를 migration에 포함한다.
- revision domain은 분리한다. `orders.mutation_version`은 Order scalar/structured/main·orthogonal state에만 적용한다. `OrderAttachment`, chat attachment, gateway revision file은 ticket idempotency와 자체 row version을 쓰며 form save의 Order version을 바꾸지 않는다. ORDER_BLUEPRINT complete도 unclaimed canonical `OrderAttachment(category=blueprint)`만 만들고 legacy blueprint JSON/column은 read projection으로만 유지한다. `REPLACE_ORDER_BLUEPRINT {attachment_id}`/`DELETE_ORDER_BLUEPRINT {reason}`가 ADMIN/MANAGER, STAFF/CS|SALES 또는 explicit DRAWING assignee 정책에서 Order If-Match/idempotency/version/event와 `STORAGE_DELETE` outbox로 current scalar projection을 바꾼다. attachment list 응답은 별도 collection ETag를 반환한다.
- drawing gateway와 AS UI는 파일보다 먼저 child draft를 만든다. idempotent `CREATE_DRAWING_REVISION_DRAFT`와 `CREATE_AS_CYCLE_DRAFT`가 각각 owner/order/purpose/24h expiry를 가진 DRAFT resource ID를 반환한다. ticket은 그 ID에만 발급한다. final drawing command 또는 `AS_REGISTER`가 Order If-Match를 받아 Order+draft를 lock하고 DRAFT attachment를 claim한 뒤 Order version을 한 번만 증가시킨다. 취소·만료 draft와 object는 cleanup job이 제거한다. DRAFT는 queue/read model에 노출하지 않는다.
- ORDER_ATTACHMENT/ORDER_BLUEPRINT/CONSTRUCTION_EVIDENCE upload complete는 child attachment 생성까지만 하며 Order If-Match가 없다. evidence ticket과 attachment는 exact `{order_id,current_attempt_id,kind,purpose}`를 저장하고 construction UI는 이어서 `REGISTER_CONSTRUCTION_EVIDENCE`를 Order If-Match로 호출해야 gate count에 포함된다. generic/old/terminal-attempt attachment claim은 409이고 과거 attempt evidence는 이력 조회만 가능하다. DRAWING_GATEWAY_REVISION/AS_EVIDENCE는 draft child complete 뒤 final command에서만 Order If-Match를 쓴다. CHAT_ATTACHMENT는 room membership과 chat row version domain이다.
- attachment와 `OrderScheduleDate`는 `item_index`를 정본으로 쓰지 않고 nullable `item_id` FK-like UUID를 저장한다. item 삭제에 attachment가 있으면 PUT은 `409 ITEM_HAS_ATTACHMENTS` details `{item_ids,current_version}`를 반환하고, UI가 outer `removed_item_dispositions`를 명시한 재요청에서만 old−new items 검증, attachment row lock, item 변경+attachment `item_id=null`을 같은 Order transaction으로 처리한다. 삭제 option은 제공하지 않는다. 해당 item의 `OrderScheduleDate`는 common으로 이동하지 않고 삭제 후 surviving item 날짜에서 같은 transaction으로 rebuild한다. ITEM-ID-00은 attachment와 schedule의 valid legacy index를 UUID에 매핑하고 out-of-range/ambiguous index는 quarantine CSV 수동 mapping 전 자동 수정하지 않는다.
- item-bound ticket complete와 structured item retire는 공통 lock order `Order → order_item_identities(item_id) → ticket/attachments`를 사용한다. complete 시 active same-order item을 다시 검사하며 ticket 발급 뒤 item이 RETIRED되었으면 `409 ITEM_RETIRED`, resulting attachment/claim 0, ticket REJECTED+orphan `STORAGE_DELETE` outbox 1이다. DATA-01과 UPLOAD-02의 PostgreSQL race test는 complete와 retire를 동시에 실행해 retired item link 0, deadlock 0, loser의 명시 오류와 cleanup 1을 고정한다.
- legacy arbitrary-key view/download는 별도 FILE-01에서 namespace·attachment ownership으로 막는다.
- 활성화 순서는 `UPLOAD-01 auth/server-derived key → FILE-01 raw-key read 차단 → UPLOAD-INTENT-01 child draft → UPLOAD-02 ticket/consumer`다. safe rollback은 direct upload OFF + 권한 적용 multipart이며 arbitrary folder fallback은 아니다.

### 2.8 실측 경로 의미

- `scheduled_route`: appointment time 순. hero와 `다음 방문`의 유일한 정본.
- `optimized_route`: nearest-neighbor 추천 순. 별도 `추천 동선` 화면·라벨에서만 표시하고 예약시간과 다를 수 있음을 명시.
- API는 `sequence=appointment|distance`를 요구한다. client의 묵시적 재정렬을 금지한다.
- 같은 번호를 두 의미에 재사용하지 않는다.

### 2.9 Offline·Service Worker

- remediation 완료 전 `FOMS_OFFLINE_SW_MODE=DISABLED`, mutation queue 제거가 안전 기본값이다. privacy persona 뒤 read cache만 `READ_ONLY`로 올릴 수 있다.
- `/api/foms/offline/queue` 등 인증 PII API는 CacheStorage에 저장하지 않고 `Cache-Control: private, no-store`를 사용한다.
- read-only offline을 다시 켤 때 IDB를 authenticated subject+schema로 partition하고 logout/subject change에서 즉시 purge한다.
- network timeout은 cache miss에서도 5초 안에 명시적 offline response로 settle한다.
- 이 roadmap은 offline mutation을 재활성화하지 않는다. OFFLINE-01은 `erp-order-autosave.js`, `draft.js`, `inline-edit.js`, `foms-write.js`의 generic queue registration과 `/api/erp/order-draft`, `/api/orders/erp/draft/autosave`, structured autosave/inline-edit queue 호출을 전수 제거한다. offline/network 실패는 local mutation을 쌓지 않고 `503 OFFLINE_MUTATION_DISABLED`와 visible retry UI를 반환한다. read-only offline만 지원한다. 향후 재활성화는 exact endpoint allowlist, queued `{subject_id,order_id,resource_version,if_match,idempotency_key,created_at}`, per-order FIFO, 403/409/428 terminal 처리와 receipt/business same-tx를 다루는 별도 spec+사용자 승인이 필요하다.
- 기존 설치본 정리는 **A0 browser service-worker update fetch→local recovery/purge→controller proof→A1 업무 UI/protocol2→B marker** 순서다. `/` scope에서 “SW가 가로채지 않는 navigation”을 가정하지 않는다. current deployed caller는 `register('/static/sw.js',{scope:'/'})`이므로 UA update가 실제 재요청하는 exact script URL `/static/sw.js`에서 OFFLINE_CLEAN_V2 bytes를 제공한다. query URL은 A0 진입 경로가 아니며 새 controller 이후에도 stable `/static/sw.js` registration을 유지한다. registration은 `updateViaCache:'none'`, response는 `Cache-Control:no-store`; UA-controlled `Sec-Fetch-Dest: serviceworker` credentialed request에만 session-bound 256-bit one-time upgrade nonce를 embed하고 ordinary fetch에는 주지 않는다. `docs/harness/foms_legacy_service_workers.json`은 production에 배포된 모든 exact content hash/scriptURL/scope/cache/IDB row schema/registration caller를 열거하며 최소 current `/static/sw.js`를 포함한다. 각 historical exact URL의 real old worker가 update→OFFLINE_CLEAN_V2 install/skipWaiting에 도달하지 못하면 STOP한다.

- OFFLINE_CLEAN_V2는 queue/replay code0이고 먼저 legacy IDB를 삭제하지 않은 채 max1000 records/10MiB의 `count,schema_id,subject_binding_present,method+route hash,created_at range,canonical record hash`만 inventory한다. 실제 current `legacy-v1-subjectless` row는 `{url,method,headers,body,createdAt}`이고 subject/CSRF proof가 없음을 manifest fixture로 고정한다. future subject-bound schema만 exact subject match로 local read-only recovery한다. legacy-v1은 locally exact registered method/route/body schema에서 order ID를 추출할 수 있고, 현재 사용자가 current password reauth를 통과하며 서버 canonical read+write scope를 가진 exact order IDs이고, **다른 active ADMIN**이 inventory hash+schema+order-ID hash에 이중 승인한 경우에만 value를 현재 사용자에게 local render해 manual re-entry 또는 encrypted export를 허용한다. 이 이중 승인의 transport는 새로 발명하지 않고 `OPS-APPROVAL-00` approval flow를 재사용한다(operation `OFFLINE_LOCAL_RECOVERY_APPROVE`, scope=inventory hash+schema+order-ID hash; 다른 ADMIN이 화면 재인증+CSRF/Origin으로 승인, one-time consume). 따라서 OFFLINE-01은 `OPS-APPROVAL-00`을 의존한다. server에는 body/value/text를 보내지 않는다. identity 추출 불가, scope deny, unknown/cross-subject/oversized는 value render/export0이고 secure support 또는 Admin-approved DISCARD만 허용한다. unrecoverable nonzero면 affected count+사용자 통지+product-owner unavoidable-loss 승인이 없이는 A0/B를 STOP한다. auto replay/server mutation/silent discard0이다.

- `.foms-recovery` exact JSON envelope는 `{format:'FOMS_RECOVERY',version:1,kdf:{name:'PBKDF2-HMAC-SHA256',iterations:600000,salt_b64url},cipher:{name:'AES-256-GCM',nonce_b64url},binding:{inventory_sha256,subject_binding_sha256,schema_id},ciphertext_b64url}`다. salt≥16 random bytes, nonce12 random bytes, AAD는 binding 포함 envelope header의 RFC8785 JCS bytes다. passphrase는 14..128 code points, memory-only/log0이고 plaintext≤10MiB/ciphertext envelope≤14MiB다. Blob download는 완성된 ciphertext 뒤 한 번만 시작한다. OFFLINE-01은 future-compatible local read-only viewer/importer를 함께 제공하되 server write/replay0이다. wrong passphrase/tamper/cross-subject는 동일 generic error+PII0이고 1280/390/1024 export→fresh browser decrypt→manual re-entry round trip을 검증한다.

- recovery resolved 뒤에만 exact `foms-p2-v*-api` cache와 `foms-offline-v1/pending-writes`를 삭제한다. 모든 old DB handle은 `versionchange=>close`, controller는 same-origin client에 `FOMS_OFFLINE_PURGE_REQUIRED`를 보내고 recovery shell은 `다른 FOMS 탭/PWA 닫기` 단계, PII 없는 acknowledged client count, explicit Retry, current step/last_error_code/request_id와 support escalation을 보인다. blocked 5초 뒤 자동 삭제하지 않는다. Retry 성공→purge→A1이 acceptance이며 permanent browser policy/IDB fault는 clean browser profile에서 DISABLED mode 업무를 안내하되 원 queue bytes는 dual approval 없이 삭제0이다. purge 후 new SW가 embedded nonce를 `/api/offline/client-generation/complete`로 직접 POST하고 서버가 stored hash/session/generation/expiry/one-time을 검증해 `client_protocol_generation=2`를 발급한다. MessageChannel은 UI 전달뿐 trust root가 아니다. proof 없는 cookie mutation은409/DB0이고 proof 뒤에만 A1 UI/protocol2를 emit한다.

- A1은 server-issued `client_protocol_generation=2` session에만 protocol2를 emit하고 서버는 protocol1/2를 임시 병행 수용하되, **generation proof 없는 cookie mutation은 계속 모두 409**다. 모든 writer/client inventory와 REV-99가 green이고 all-serving compatibility generation artifact가 나온 뒤 `python tools/ops/check_offline_sw_rollout.py --environment deploy --required-compatibility-generation <n> --output <artifact>`를 실행한다. 그 artifact와 operation-bound token으로만 `python tools/ops/mark_feature_cutover.py --family OFFLINE_SW --artifact <artifact> --approval-token-file <path> --expected-version <n> --apply`를 실행해 phase B를 시작한다. **OFFLINE-01 코드 packet의 완료 정의는 phase A(A0/A1)와 all-serving compatibility generation artifact까지다.** phase B marker cutover는 §8.2 OFFLINE_SW family cutover 운영 절차(CUTOVER-MODE-01 메커니즘+OPS-APPROVAL-00 token)로 REV-99 green과 all-serving 이후 RELEASE-GATE-00 뒤 deploy gate 단계에서 실행하며, OFFLINE-01 packet 완료 정의의 일부가 아니다. 따라서 `REV-99.depends_on`의 `OFFLINE-01`은 phase A 완료를 뜻하고 phase B가 REV-99 후행이어도 순환이 없다. B에서는 route type에 맞는 protocol2 값과 server-issued generation2가 모두 없는 구 mutation을 409/DB0으로 거부한다. old queued JSON/form replay, old tab, protocol2를 흉내 낸 구 generic queue도 통과하지 못한다. marker 뒤 protocol1/queued-writer image rollback은 compatibility generation/startup/readiness/request gate에서 막고 roll-forward만 허용한다.

### 2.10 Startup·migration

- Railway schema owner는 기존 `railway.toml preDeployCommand → predeploy.sh`다.
- Alembic/`ensure_schema.py`의 **스키마 확장(DDL, expand-only)**만 Railway predeploy로 실행하고 실패 시 fail-closed한다. **데이터 backfill(STARTUP-BACKFILL-01 등 BACKFILL-ARTIFACT-00 consumer)은 predeploy에서 실행하지 않는다.** §7.3의 DPAPI 보호 artifact 프로토콜은 Windows operator maintenance command 전용이고 Linux/Railway는 별도 KEK spec 전 fail-closed하므로, 데이터 backfill은 배포 파이프라인이 아니라 operator가 별도 실행하는 maintenance 단계다. predeploy는 스키마만 확장하고, 그 스키마가 요구하는 backfill이 아직 미완이면 관련 mode는 LEGACY/DISABLED로 유지한다.
- admin bootstrap은 별도 명시 CLI다.
- `register_date_sync_listener` 같은 runtime listener 등록만 app factory에 남긴다.
- `app.py` import와 `run.py` dev startup은 DDL/DML을 실행하지 않는다. dev도 migration 실패 후 계속 시작하지 않는다.
- 최종 계약은 `python -c "import app; print('APP_OK')"` 동안 SQL write/DDL 0건이다.

### 2.11 FOMS Brain Designer — 삭제 예정 (수정 범위 제외)

**FOMS Brain(Designer, `/wdplanner-v2`)은 제거 확정 기능이므로 이 감사·수정 계획은 Designer를 "고치지" 않고 "삭제"한다.** 따라서 앞선 판본의 Designer authorization 재설계(canonical actor·member scope·null-owner backfill·global approval policy)는 폐기하고, 단일 봉쇄 packet **DESIGNER-RETIRE-01**이 Designer 전 표면을 제거한다.

- 대상: `foms/api/designer/*` blueprint·라우트, `templates/designer/wdplanner_v2.html`·`wdplanner_v2_setup.html`, designer 전용 JS/CSS, 관련 테스트, 그리고 **nav 링크**. nav 링크는 리터럴 `/wdplanner-v2`가 아니라 `templates/partials/shared/layout_nav.html:163`의 `href="{{ url_for('designer.wdplanner_v2') }}"`와 `wdplanner_v2_setup.html:30`의 동일 `url_for`다. blueprint만 제거하고 이 `url_for` 줄을 남기면 nav를 렌더하는 **모든 페이지가 werkzeug `BuildError`로 500**나며 `import app; APP_OK`로는 잡히지 않으므로, `url_for('designer.wdplanner_v2')` 참조를 grep으로 전수 제거하고 완료 검증을 nav 포함 페이지 실렌더(§6.2 DESIGNER retire 행)로 확정한다.
- 삭제가 P0-13(project/run/candidate IDOR·무인증·null actor)과 P0-24(Designer 화면 stored/DOM XSS)를 **근본 제거**한다. 두 finding은 별도 auth/XSS 수정이 아니라 표면 삭제로 소멸한다.
- DB `designer_*` 테이블·데이터는 이 packet에서 건드리지 않는다(코드/UI만 제거). 데이터 폐기는 법무·보존정책 승인을 받은 별도 retention spec으로만 설계한다.
- 완료 기준: 모든 designer route/nav가 GET·POST 404, 템플릿·정적자산·blueprint 등록 0, `url_for('designer.*')` 참조 0, **nav 포함 페이지 실렌더에서 `BuildError`/500 0**, `import app; APP_OK` 회귀 0, 잔존 Designer UI 진입점 0.

---

## 3. 확정 finding registry

### 3.1 P0

| ID | 확정 사실 | 현재 근거 | 마스터 수술 |
|---|---|---|---|
| P0-1 | 웹 migration reset은 원본 사전검증 전 WDC/main 삭제를 각각 commit | `foms/web/admin/routes.py::admin_migration`, `scripts/migrations/web_migration.py` | MIG-WEB-RETIRE-01: route/template과 위험 helper 삭제; 필요 시 새 CLI는 별도 spec |
| P0-2 | Kakao REST secret literal이 source와 Scheduler에 중복 | `foms/services/common/geocode_config.py`, `SCheduler/config.py` | SECRET-01: env-only, 외부 rotate, 기능별 fail-fast |
| P0-3 | VIEWER가 settlement/cash를 변경하고 mutation surface가 더 넓음 | `foms/api/cs/dashboard.py:262-445`; RB-L-M `settlement/issue 200` | AUTH-01 + AUTH-FINANCE-01 + URL-map inventory |
| P0-4 | wizard full PUT이 pending을 소실·주입 가능 | `foms/api/drawing/wizard.py::api_put_drawing_wizard` | WIZ-01 row lock+projection |
| P0-5 | 검색어를 JS string에 `safe`로 넣는 XSS sink 3곳 | measurement regional/metropolitan/self templates | FE-XSS `tojson` + hostile browser test |
| P0-6 | attachment gallery JS의 Python `#` 주석으로 parser 실패 | `static/js/foms/erp-attachment-preview-open.js:205`; `node --check` | FE-SYNTAX + parser CI |
| P0-7 | Quest 요청 team을 actor/required team과 대조하지 않음 | `foms/api/quest.py`, `foms/services/orders/erp_policy_quests.py` | AUTH-QUEST-01 + STATE-QUEST-01 |
| P0-8 | structured full PUT이 운영 blob·돈 상태와 outer raw/schema/confidence provenance를 소실/회귀 | `foms/api/erp_orders_structured.py`, `static/js/orders/erp-order-shared.js` | DATA-01 exact envelope+projection+version |
| P0-9 | 생산팀 핵심 start/complete는 `erp_edit_required` 때문에 거부되나 UI는 노출 | `foms/api/production/orders.py:99-207`, `erp_permissions.py:289-295`; RB-L-M 403 | AUTH-01 + STATE-PROD-01 + ERR-UX-01 |
| P0-10 | main ERP OrderEstimate create/update/delete가 login-only이고 parent order scope도 일관되게 확인하지 않음 | `foms/api/erp_estimates.py::create_order_estimate`(POST `/orders/<id>/estimates`)·`update_estimate_api`(PUT `/estimates/<id>`)·`delete_estimate`(DELETE `/estimates/<id>`) 셋 다 `@login_required`만 있고 parent order read-scope·CS/SALES 정책 없음 | ERP-ESTIMATE-01 parent scope+CS/SALES policy+revision/audit |
| P0-11 | legacy blueprint upload/delete가 login-only이며 complete key를 substring으로 검사 | `foms/api/erp_orders_blueprint.py` | UPLOAD-01/02 + BLUEPRINT-01 exact ticket/typed replace/delete |
| P0-12 | order copy가 모든 STAFF에 열리고 광범위한 server-owned 상태와 item identity를 복제·부분 commit할 수 있음 | `foms/api/orders/copy.py`, `foms/services/order_copy.py`, `foms/web/orders/listing.py` | ORDER-COPY-01 allowlist clone+fresh identity+all-or-none |
| P0-13 | FOMS Brain project/version/run/candidate/global ontology mutation이 login-only 또는 same-origin만 검사하고 project IDOR/null actor 위험 | `foms/api/designer/projects.py`, `ai_runs.py`, `drawings.py`, `evolution_api.py`, `security.py`; `g.user_id` canonical bootstrap 없음 | **DESIGNER-RETIRE-01** — Brain 삭제 예정이라 auth 재설계 대신 표면 제거로 근본 소멸 (§2.11) |
| P0-14 | chat Socket.IO join/typing/send가 room membership을 검사하지 않고 message를 room+user room으로 중복 broadcast | `foms/api/channel/socketio_handlers.py` | CHAT-SOCKET-AUTH-01 membership+canonical send+recipient별 1회 |
| P0-15 | Excel import가 raw Order에 server-owned status/payment/AS를 넣고 canonical owner/item/quest/version 없이 생성 | `foms/web/admin/excel_import.py` | ORDER-IMPORT-01 strict workbook+constructor batch |
| P0-16 | Channel inbound가 raw Order와 source log를 두 번 commit해 orphan/duplicate 가능 | `foms/services/channel_inbound.py` | CHANNEL-WEBHOOK-AUTH-01 provider receipt→CHANNEL-INBOUND-ORDER-01 constructor one tx |
| P0-17 | profile/admin user edit가 password 검증 전 일부 field를 commit해 실패 응답에도 변경되고 cookie mutation 공용 CSRF guard가 없음 | `foms/web/auth/routes.py`, state-changing route inventory | WRITE-GUARD-01 + AUTH-ACCOUNT-01 validation one tx/session revoke |
| P0-18 | 무인증 `/debug-db`가 deployed env에서 schema/count/env/traceback을, Channel health가 feature/secret 존재/worker·queue metric과 raw exception을 노출 | `foms/api/debug.py`, `foms/platform/blueprints.py`, `foms/api/channel/channel_integration.py::api_channel_health` | OPS-ROUTE-01 public ops surface 최소화+private readiness auth |
| P0-19 | public login의 hostile username이 SecurityLog.message에 저장되고 ADMIN log의 `order_link_filter→Markup`+template `safe`로 stored XSS 실행 가능 | `foms/web/auth/routes.py`, `foms/web/orders/listing.py::order_link_filter`, `templates/admin/security_logs.html` | STORED-XSS-01 escape-first token link+producer bound |
| P0-20 | order editor가 저장한 options/product/spec 문자열이 목록 summary의 `safe`와 newline→`<br>` 후 `safe`에서 실행 가능 | `foms/web/orders/edit.py`, `templates/orders/index.html:872-976` | STORED-XSS-01 autoescape+CSS multiline, hostile cross-persona browser test |
| P0-21 | self-edit `User.name`이 drawing workbench/dashboard/detail과 workbench 담당자 picker의 template string `innerHTML`에 들어가 cross-user stored XSS 가능 | `workbench-dashboard.js`, `erp-dashboard-drawing.js`, `erp-dashboard-detail-dom.js`, `templates/drawing/partials/workbench_detail_body.html:2885-2912` | STORED-XSS-01 DOM node/textContent rendering+integer ID validation |
| P0-22 | Railway non-production deployed env와 WAM signer가 missing secret에서 known hardcoded key로 기동 | `app_factory.py`, `channel_security.py` | SESSION-SIGNING-SECRET-01 deployed fail-fast+shared derived keyring |
| P0-23 | 일반 사용자에게도 열린 개인 변경이력이 현재 Order의 hostile `customer_name`을 API에서 받아 raw `innerHTML`과 inline `onclick` JS string으로 렌더 | `templates/admin/change_logs.html:176-221`, `foms/api/events.py:179-239` | STORED-XSS-01 card DOM/textContent+addEventListener; EVENT-REVERT-01 generic revert 제거 |
| P0-24 | Designer 화면이 persisted/AI/API의 archetype/case/rule/fixture 문자열과 JSON을 raw `innerHTML`·inline `onclick`에 삽입해 authorized cross-project/global victim에게 stored/DOM XSS 가능 | `templates/designer/wdplanner_v2.html:589-818` | **DESIGNER-RETIRE-01** — Brain 화면 삭제로 sink 소멸 (§2.11). STORED-XSS-01은 개인 변경이력 등 non-Designer sink만 담당 |
| P0-25 | ChannelTalk Function endpoint가 공식 PUT 대신 POST만 받고, signing key hex bytes+Base64 signature 대신 raw UTF-8 key+hex digest를 비교해 provider request가 405/401 | `channel_functions.py:14`, `channel_security.py:155-165`, stale function fixture/spec | CHANNEL-FUNCTION-CONTRACT-01 provider-exact transport/signature/envelope |
| P0-26 | 표준 ChannelTalk Webhook POST `?token=`에 Function X-Signature를 요구하고, deployed empty group allowlist를 allow-all 처리해 정상 provider 401 또는 cross-group raw payload 수집 가능 | `channel_webhooks.py:8-24`, `channel_inbound.py:108-129`, stale policy docs | CHANNEL-WEBHOOK-AUTH-01 separate token/auth/source allowlist+log redaction |

### 3.2 P1

> 번호 주: `P1-3`은 `P1-3A`/`P1-3B`로 분할됐고 `P1-9`는 이전 개정에서 다른 finding에 흡수되어 **의도적으로 결번**이다(registry hole 아님). finding↔packet 정합 점검은 이 결번을 정상으로 취급한다.

| ID | 확정 사실 | 수술 |
|---|---|---|
| P1-1 | Structured PUT ownership/동시성 없음 | DATA-01 |
| P1-2 | construction complete가 stage predicate 없이 바로 COMPLETED | STATE-CONST-CS-01: CONSTRUCTION→CS |
| P1-3A | production start/complete expected-stage·idempotency 없음 | STATE-PROD-01 |
| P1-3B | PRODUCTION role 권한 역전·silent failure | AUTH-01 + production UI error contract |
| P1-4 | bulk API는 STAFF가 DELETED를 쓸 수 있으나 단건 정책은 MANAGER+ | DELETE-BULK-01 |
| P1-5 | push sender는 `data.notification_id/deep_link`, SW는 top-level을 읽음 | PUSH-01: nested 우선+legacy fallback |
| P1-6 | appointment hero/map과 NN strip이 서로 다른 `다음 방문`을 말할 수 있음 | ROUTE-01 dual sequence |
| P1-7 | soft-delete, switch-user/back이 GET | DELETE-TRASH-01 + AUTH-IMPERSONATION-01 |
| P1-8 | Channel quick action이 manager id 누락 때 fail-open하고, active mapping만 확인한 뒤 canonical Order read scope 없이 customer/phone/address/schedule/assignee PII를 반환 | `channel_quick_actions.py:123-149`, `channel_identity.py:44-55` | CHANNEL-AUTH-01 active User resolve+same Order read policy+indistinguishable deny |
| P1-10 | wizard transfer/delete가 client key를 신뢰 | WIZ-01/WIZ-TRANSFER-01/WIZ-DELETE-01 |
| P1-11 | packing submit과 shell capture listener가 경합 | PACK-01 no-shell+one-POST browser test |
| P1-12 | WDC 저장 고객/제품 문자열이 HTML string sink로 들어감 | WDC-XSS-01; backend current search endpoints `blueprint.py:1078-1090,1321-1346` |
| P1-13 | page nav 제한과 API 권한이 분리되고 `/erp/api`는 redirect될 수 있음 | AUTH-01; RB-L-M notification 302 |
| P1-14 | upload session arbitrary folder, complete substring check, multipart login-only | UPLOAD-01→FILE-01→UPLOAD-02 |
| P1-15 | shell navigation에 generation/abort/stale commit guard 없음 | SHELL-01 |
| P1-16 | mobile history JS가 DOMContentLoaded-only | HISTORY-01 idempotent fragment init |
| P1-17 | `app.py`와 `run.py`가 startup DB mutation을 수행 | STARTUP-SCHEMA-01 + STARTUP-BACKFILL-01 + STARTUP-ADMIN-01 + STARTUP-PURE-01 |
| P1-18 | construction mobile notification state가 302 HTML로 JSON parser를 깨뜨림 | AUTH-01 API namespace contract |
| P1-19 | SW offline queue CacheStorage가 user-scoped가 아님 | SW-01 privacy boundary |
| P1-20 | `GET /api/orders/<id>/quest`가 quest가 없으면 JSONB를 만들고 commit | AUTH-QUEST-READ-01: GET pure read; creation은 mutation path만, STATE-QUEST-01에서 transition tx로 이관 |
| P1-21 | drawing batch assignment가 row별 예외를 삼켜 부분 성공할 수 있음 | ASSIGNMENT-00 `BATCH_SET_DRAWING_ASSIGNEES` all-or-none |
| P1-22 | regional/self-measure checklist·memo가 모든 STAFF direct commit | DATA-MEASUREMENT-01 typed field registry+policy+revision |
| P1-23 | OrderTask가 any STAFF create/update/hard-delete와 automation raw SQL로 이중 write | TASK-01 child revision+manual/automation ownership+cancel audit |
| P1-24 | VIEWER hard deny를 Order 밖 actor-owned notification/chat/push에도 일괄 적용하면 정상 개인 기능 회귀 | ACTOR-STATE-01 exact ancillary allowlist+owner/membership test |
| P1-25 | urgent call이 notification/realtime/push를 다중 commit하고 VIEWER participant 정책이 미분류 | URGENT-CALL-01 scoped communication command+outbox |
| P1-26 | anonymous RUM ingest가 arbitrary/oversize/non-finite payload를 log하고 unexpected error를 조용히 삼키며 report days가 unbounded | `foms/api/foms_rum.py` | RUM-INGEST-01 2KiB schema/rate/warning+days bound |
| P1-27 | 1024px coarse portrait에서 CSS/JS predicate가 다르고 load-time 반대 form 삭제로 회전·keyboard cohort 변화 시 form 소실 가능 | `foms-detail-hero.css`, `edit_order_body.html` | SURFACE-GATE-01 shared cohort controller+dirty-safe rotation persona |
| P1-28 | 다수 API가 unexpected exception의 `str(e)`·traceback·내부 path를 사용자 응답/stdout에 노출 | `foms/api/**` 500 handler inventory | API-ERROR-01 generic envelope+structured server logging+leak guard |
| P1-29 | production source에 broad exception+단일 `pass`가 정확히 45개/25 files 있어 auth/storage/audit/cache/telemetry 실패를 분류 없이 은폐 | current `foms/**`+root runtime Python AST inventory | FAILOPEN-01 owner/disposition manifest+release static gate |
| P1-30 | WAM telemetry가 body cap/rate/exact schema 없이 unknown·arbitrary nested 값을 log해 memory/log DoS·오염 가능 | `channel_wam.py::wam_telemetry`, `channel_wam_telemetry.py` | WAM-TELEMETRY-01 bounded scoped ingest |
| P1-31 | global body 500MiB, form memory/parts와 route별 pre-parse cap 부재로 public control-plane memory/tempfile DoS 가능 | `foms/platform/app_factory.py` request config | REQUEST-LIMIT-01 route manifest+WSGI pre-parse limiter |
| P1-32 | `31f05379`의 390×844 sticky secnav가 deep `접수` click 후 top=-1758로 사라졌으나 `3c328837`에서 48..100 fixed로 복구 | 두 SHA gstack browser, `foms-form-field.css`, mobile template | current resolved; SURFACE-GATE-01 persistent geometry regression gate 유지 |
| P1-33 | WAM entry nonce가 Redis 실패 시 process-local set으로 fail-open해 multi-worker에서 같은 token을 worker별 재사용 가능 | `foms/services/channel_security.py` nonce consume | SESSION-SIGNING-SECRET-01 PostgreSQL single-use nonce+fail-closed |
| P1-34 | Admin 사용자 삭제 route/UI가 User row를 hard delete해 주문·배정·감사 이력의 주체 보존 계약과 네-command account API를 깨뜨림 | `foms/web/auth/routes.py:479-501`, `templates/auth/user_list.html:72` | AUTH-ACCOUNT-01 hard-delete surface 404+reasoned deactivate/session revoke |

### 3.3 상태 writer 전체 inventory

STATE 계열 PR은 production/construction 두 파일만 고치고 끝내면 실패다.

| Writer | 현재 경로 | 이관 규칙 |
|---|---|---|
| Structured PUT | `foms/api/erp_orders_structured.py::_handle_stage_transition` | stage 제거; command 호출 |
| Quest approval | `foms/api/quest.py` | 승인 tx 뒤 service 호출 |
| Drawing handoff | `foms/api/drawing/erp_orders_draftsman.py` | expected DRAWING/CONFIRM 계약 |
| CS complete | `foms/api/cs/complete.py` | CS→COMPLETED |
| AS routes | `foms/api/cs/as_orders.py` | 별도 AS transition table |
| Generic status | `foms/api/orders/status.py` | 일반 stage 쓰기 제거; delete command 분리 |
| Field update | `foms/api/orders/field_update.py` | stage/status field 금지 |
| Legacy edit | `foms/web/orders/edit.py` | ERP status 직접 변경 제거, command 사용 |
| Listing/bulk/create/copy | `foms/web/orders/listing.py`, `foms/api/orders/copy.py`, `foms/services/order_copy.py` | ORDER-CREATE-01 constructor, ORDER-COPY-01 allowlist/all-or-none; raw column clone 금지 |
| Excel import | `foms/web/admin/excel_import.py` | ORDER-IMPORT-01 strict form schema+constructor all-or-none |
| Channel inbound create | `foms/services/channel_inbound.py` | CHANNEL-WEBHOOK-AUTH-01 verified token/source receipt→CHANNEL-INBOUND-ORDER-01 configured SALES owner+constructor/source link one tx |
| Draft create/discard | `foms/api/erp_order_draft.py` 등 | ORDER-CREATE-01 constructor만 호출, discard는 lifecycle command |
| Orphan mobile queue swipe | `foms_queue_actions.py`, `mobile_queue_action.py`, old `erp_mobile_queue_card.html`, global `swipe-actions.js` | active v2 card render reference 0을 BASE에서 재확인하고 route/service/old macro/global load 제거; active production/tablet hold control만 HOLD_ORDER 사용 |
| Trash delete/restore | `foms/web/orders/trash.py` | orthogonal delete service, main stage 불변 |
| Logistics status | `status_constants.py`를 쓰는 field/bulk writer | `shipment.logistics_status` command, main stage 불변 |
| Shipment settings | `foms/api/shipment/settings.py` | construction worker key 제거→assignment command; 나머지 exact shipment-form command |
| Shipment AS recommendation | `foms/api/shipment/recommendations.py` | current cycle ID의 schedule/compensating cancel + construction ID assignment를 한 orchestration tx |
| Measurement/map inline | `foms/api/measurement/routes.py`, `foms/api/erp_map.py::api_update_order_address/api_add_address_learning`, `order_geocode.py` | DATA projection의 exact address/manager/phone command+geocode outbox; address learning은 별도 scoped child command |
| Regional/self-measure | `foms/api/orders/regional.py` | 6 boolean checklist field enum+memo command, CS/SALES policy, version/receipt/event |
| Call log | `foms/api/orders/call_log.py` | calls append + optional measurement date command, version/receipt 한 tx |
| Channel push metadata | `foms/api/channel/channel_integration.py` | message send 결과와 metadata command/outbox, same-key 중복 0 |
| WDC match/unmatch | `foms/api/wdcalculator/blueprint.py` | topology preflight; same DB면 `EstimateOrderLinkV2`+receipt와 legacy projection을 한 tx, separate DB면 freeze 뒤 V2-only tx; Order meta runtime write 제거 |
| Finance | `foms/api/cs/dashboard.py` | AUTH-FINANCE-01 command/receipt/version |
| Packing | `foms/api/shipment/packing.py` | PACK-01 command/receipt/version |
| OrderTask/manual automation | `foms/api/tasks.py`, `foms/services/orders/erp_automation.py` | TASK-01 parent scope, child revision, typed automation same tx, hard delete 제거 |
| Actor-owned notification/push | notification mark/archive/ack, push subscription | ACTOR-STATE-01 exact actor-owned child mutation; Order business mutation과 분리 |
| Chat room/message/upload/file/socket | room lifecycle; mark-read/send; upload ticket; attachment ID read; realtime events | CHAT-ROOM-01 / CHAT-MESSAGE-01 / UPLOAD-CHAT-01 / CHAT-FILE-01 / CHAT-SOCKET-AUTH-01 각각 단일 owner |
| Drawing change ack | `foms/api/drawing/erp_orders_revision.py::ack_order_change`, `foms/services/notifications/drawing_order_change.py` | STATE-DRAWING-01 `ACK_DRAWING_ORDER_CHANGE`; production ACK와 분리 |
| Drawing revision checklist/cancel | `foms/api/drawing/erp_orders_revision.py::request_revision_check`, `foms/api/drawing/erp_orders_drawing.py::cancel_transfer` | STATE-DRAWING-01 exact request ID/check/retransfer/cancel transfer |
| Drawing batch assignment | `foms/api/drawing/erp_orders_draftsman.py::batch_assign_draftsman` | ASSIGNMENT-00 sorted lock+all-or-none |
| Wizard asset/import/export/pending/version/preset | `foms/api/drawing/wizard.py` | WIZ-01 child/Order commands, WIZ-TRANSFER transaction snapshot, WIZ-PRESET-01 settings domain |
| ERP OrderEstimate | `foms/api/erp_estimates.py` | ERP-ESTIMATE-01 parent scope+typed create/update/draft-delete/cancel |
| Order blueprint | `foms/api/erp_orders_blueprint.py` | BLUEPRINT-01 ticket attachment+typed current projection/delete |
| Generic event revert | `foms/api/events.py::api_revert_change_event` | generic JSON-path revert route/control 제거; command별 typed compensation만 허용 |
| Production | `foms/api/production/orders.py` | CONFIRM→PRODUCTION→CONSTRUCTION |
| Construction | `foms/api/construction/orders.py` | CONSTRUCTION→CS, fail/rework event |
| Drawing draftsman/revision | `foms/api/drawing/erp_orders_draftsman.py` 등 | 실제 before+event |
| Admin override | `foms/services/orders/stage_override.py` | service의 emergency path만 |

WDC topology를 추정하지 않는다. `inspect_wdc_db_topology.py --output <redacted.json>`가 FOMS/WDC DSN을 값 없이 canonical server+database identity로 비교하고 `SAME_DATABASE|SEPARATE_DATABASE`를 산출한다. 현재 code/default는 `DATABASE_URL`의 `public`+`wdcalculator` schema를 쓰고 optional `WD_CALCULATOR_DATABASE_URL`일 때만 분리된다. 현재 연결된 PostgreSQL MCP에서도 `public.orders`와 `wdcalculator.estimate_order_matches`가 한 database에 존재한다. 각 deploy/production artifact에서 topology를 다시 증명하고 바뀌면 re-audit한다. 신규 canonical 정본은 legacy runtime이 전혀 읽지 않는 `wdcalculator.estimate_order_links_v2`(`EstimateOrderLinkV2`)와 WDC-domain receipt다.

`SAME_DATABASE`는 한 SQLAlchemy transaction이 정답이다. expand 뒤 기존 match/unmatch를 모든 replica에서 동일 database session으로 이관해 legacy `EstimateOrderMatch`/Order meta projection과 V2 link+receipt를 원자적으로 dual-write한다. marker 전 read는 legacy, V2는 shadow다. dual-write all-serving 뒤 online backfill/checkpoint가 V2를 채우고 source/target equivalence를 검증한다. canonical reader image를 all-serving으로 배포해도 marker 전에는 legacy만 읽는다. generic WDC_LINK family fence가 in-flight transaction을 drain한 뒤 marker를 insert하면 같은 image가 다음 transaction부터 V2만 읽고 쓴다. dual-write/rollout 실패는 marker 전 old read로 복귀할 수 있고 V2 shadow row는 사용자에게 보이지 않는다. cross-DB freeze/maintenance/abort CLI는 이 topology에서 실행 금지다.

`SEPARATE_DATABASE`에서만 WDC DB에 `wdc_link_runtime_state(id=1,mode=LEGACY|FROZEN|CANONICAL,generation,row_version,prepared_consumer_generation,frozen_at,freeze_source_fingerprint,freeze_rollout_artifact_sha256,updated_at,updated_by_admin_user_id)`를 seed하고 2PC를 흉내 내지 않는다. legacy match/unmatch writer는 모든 replica에서 WDC singleton을 `SELECT ... FOR KEY SHARE`해 LEGACY를 확인하고 Order DB legacy meta commit까지 보유한다. freeze CLI는 `FOR UPDATE`로 in-flight를 drain해 FROZEN을 commit하고 crash-resume로 Order legacy source fingerprint를 기록한다. FROZEN 중 V2 shadow backfill/checkpoint와 canonical image all-serving을 끝내며 controls/API는503·두 DB0이다. artifact+checkpoint 뒤 primary WDC_LINK marker→WDC state CANONICAL 순서이고 두 commit 사이도 write0이다. 이후 V2+receipt만 WDC DB 한 tx로 쓴다.

SEPARATE marker 전 audit/manual/backfill/rollout 실패는 `abort_wdc_link_cutover.py --expected-generation <n> --approval-token-file <path> --apply`로 복구한다. CLI는 marker 없음, V2 runtime receipt0, fence all-serving/in-flight0, current legacy-meta fingerprint=freeze fingerprint를 검증해 `FROZEN→LEGACY`, generation+1과 immutable audit를 commit한다. V2 shadow는 legacy `EstimateOrderMatch`/Channel room consumer가 읽지 않으므로 inert하고 다음 audit가 reconcile한다. source drift·marker·V2 runtime write가 있으면 abort STOP/roll-forward only다. PC/mobile control은 LEGACY 다음 요청부터 복구된다. legacy meta/V1 table cleanup은 marker+CANONICAL 뒤 별도 packet이다.

AUTH-01의 URL-map manifest는 모든 state-changing route에 `route_template,method,policy_id,revision_domain,owner_packet,client_ids`를 1:1로 기록한다. 위 표뿐 아니라 `flag_modified`, Order scalar assignment, bulk update, raw SQL writer를 정적 scan하고 미분류 route/symbol이 하나라도 있으면 BASE/REV-99가 실패한다.

### 3.4 P2/Ops

| 항목 | 판정 | 처리 |
|---|---|---|
| IDB delete-after-async | transaction lifetime 위험 C+I | OFFLINE-01에서 queued mutation 경로 자체 제거; 이 roadmap에서 재활성화하지 않음 |
| SW cold miss | Promise가 settle되지 않는 경로 C | SW-01 finite 5s |
| SW cross-user PII | origin cache 공유 C+I | SW-01 API no-cache+subject purge |
| AS trigram | query expression과 index expression 불일치 C+I | SCALE-AS-01; EXPLAIN 효과 없으면 무변경 종료 |
| Channel worker stuck | processing commit 뒤 lease/reaper 부재 C+I | CHANNEL-INBOUND-ORDER-01 functional lease/reclaim/max-attempt; SCALE-CHANNEL-01은 index/load만 |
| SketchUp reclaim | max attempts/expired-running 경계 불완전 C+I | SCALE-SKETCHUP-01 |
| duplicate indexes | local DB exact duplicate와 covered 후보가 섞임 DB-L | INDEX-OPS-01 production catalog+constraint+EXPLAIN 후만 제거 |
| backup password/process env | 퇴역 정책과 코드 충돌 C+P | BACKUP-01 사용처 확인 후 제거 |
| XFF limiter | untrusted XFF를 key로 사용할 수 있음 C | PROXY-01 trusted proxy only |
| raw file key presign | login-only arbitrary storage key C | FILE-01 attachment namespace |
| deploy QA literal credential | tracked literal C, 유효성 U | SECRET-02 rotate+secret store |

---

## 4. 목표 구조

```text
Browser control
  └─ policy_id-rendered UI
      └─ API policy guard (role → team → assignment → state)
          └─ domain command
              ├─ Order row lock + mutation_version
              ├─ transition service or form projection
              ├─ business rows / JSONB
              ├─ OrderEvent + SecurityLog
              └─ one commit

Upload client
  └─ purpose request → server-derived exact key + DB ticket
      └─ object upload → HEAD verify → ticket consume + attachment commit

Deploy
  └─ predeploy.sh: migration / bounded maintenance, fail-closed
      └─ start.sh: read-only app import + gunicorn
```

### 실패 응답 표준

| 상황 | HTTP | code |
|---|---:|---|
| 비로그인 API | 401 | `AUTH_REQUIRED` |
| 역할·팀·assignment 거부 | 403 | `FORBIDDEN` |
| If-Match 없음 | 428 | `PRECONDITION_REQUIRED` |
| stale revision | 409 | `REVISION_CONFLICT` |
| 잘못된 stage | 409 | `STAGE_CONFLICT` |
| 전용 command를 generic writer로 우회 | 409 | `STAGE_COMMAND_REQUIRED`, details `{required_command,current_stage,current_version}` |
| item에 attachment가 있는데 disposition 없음 | 409 | `ITEM_HAS_ATTACHMENTS`, details `{item_ids,current_version}` |
| assignment target/domain/schema 위반 | 422 | `ASSIGNMENT_VALIDATION_FAILED` |
| assignment state/중복·stale 충돌 | 409 | `ASSIGNMENT_CONFLICT` |
| child draft state/expiry 충돌 | 409 | `DRAFT_STATE_CONFLICT` |
| construction evidence의 order/attempt/kind 불일치 | 409 | `EVIDENCE_MISMATCH` |
| idempotency key 재사용+다른 hash | 409 | `IDEMPOTENCY_KEY_REUSED` |
| server-owned 변경 시도 | 409 | `SERVER_OWNED_FIELD_CONFLICT` |
| unknown path | 400 | `UNKNOWN_FIELD` |
| structured schema/type/length 위반 | 422 | `SCHEMA_VALIDATION_FAILED` |
| wizard server-owned field 전송 | 400 | `WIZARD_SERVER_FIELD` |
| ticket 변조·소유 불일치 | 403 | `UPLOAD_TICKET_FORBIDDEN` |
| ticket 만료 | 410 | `UPLOAD_TICKET_EXPIRED` |
| body/file/part 수 상한 초과 | 413 | `REQUEST_BODY_TOO_LARGE` |
| control-plane 압축 body | 415 | `UNSUPPORTED_CONTENT_ENCODING` |
| cutover 뒤 구 mutation client | 409 | `CLIENT_UPGRADE_REQUIRED` |
| unexpected server exception | 500 | `INTERNAL_ERROR` |

최종 API 오류는 `{success:false,error:{code,message,details?,request_id}}` JSON이다. 이관 중에는 기존 client 파손을 막기 위해 동일 문자열의 top-level `message`도 함께 반환하고, ERR-UX-01이 모든 등록 client를 새 envelope로 옮긴 뒤 REV-99에서 URL-map consumer 100% 증거와 함께 legacy `message` 제거를 허용한다. UI는 message를 toast/inline alert로 표시하고 낙관적 DOM 이동을 rollback한다.

expected domain error는 등록된 exception→status/code/message mapping만 사용한다. unexpected exception은 status `500`, code `INTERNAL_ERROR`, 고정 사용자 문구 `요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.`, opaque `request_id`만 반환하고 `details`와 legacy top-level message에는 내부 exception을 넣지 않는다. JSON namespace의 공용 handler와 HTML generic 500 page가 이를 강제한다. server는 access-controlled central logger의 `logger.exception`에 request_id, route template, actor ID, policy ID와 protected stack을 한 번 남기되 raw request/body, credential, DB URL, SQL value, filesystem/object key는 redaction filter로 제거한다. traceback은 사용자 response/SecurityLog/client telemetry에 절대 노출하지 않는다. `str(e)` response, `traceback` JSON, `print(traceback...)`/`traceback.print_exc()`는 API-ERROR-01 static guard에서 0이고 protected logger stack만 허용한다. DB/storage fault persona는 response의 secret/path/SQL/stack 문자열 0, protected server log의 동일 request_id 정확히 1을 확인한다.

`except Exception: pass`와 동등한 silent broad catch는 FAILOPEN-01 inventory에 `path,symbol,owner_packet,disposition=NARROW|LOG_AND_NEUTRAL|FAIL_CLOSED,expected_exception,reason,test`를 모두 등록한다. auth/ownership/audit/transaction/storage integrity는 fail-closed, best-effort cache/telemetry는 request_id와 비민감 domain ID로 warning 후 검증된 neutral result만 허용한다. `(TypeError, ValueError)` 같은 parser 무시는 exact input·neutral-result test와 allowlist reason이 있을 때만 가능하다. 신규 unclassified broad catch 0을 모든 PR에서, unresolved inventory와 silent broad pass 0을 RELEASE-GATE-00에서 AST로 강제한다.

public operational surface는 `/healthz`의 `{status,commit}`과 constant-time 200/503뿐이다. `/debug-db` route/module은 deployed registration 0으로 제거한다. 사람용 detail은 public app의 `/admin/ops/channel-readiness`에 ADMIN session 정책을 적용한다. machine detail은 별도 minimal `foms/ops_app.py`+`railway-ops-readiness.toml` service의 `/internal/ops/channel-readiness`에만 등록하고 그 Railway service에는 public domain을 만들지 않는다. private DNS 요청도 `FOMS_OPS_READINESS_TOKEN`(random≥32 bytes, missing fail-start)을 timing-safe 비교하며 token rotation은 `FOMS_OPS_READINESS_TOKEN`/`FOMS_OPS_READINESS_TOKEN_PREVIOUS` 10분 overlap 뒤 previous 제거, 모든 log redaction을 쓴다. public app blueprint에는 `/internal/ops/*` 등록 0이고 public `/api/channel/health`는 404다. 외부 GET response에는 schema/table/user count, env·secret name/presence, feature flag, worker/backlog/delivery/replay metric, raw exception/traceback이 0이어야 한다. ADMIN detail은 `Cache-Control: private, no-store`, `Pragma: no-cache`, `Vary: Cookie`를 반환하고 ETag/Last-Modified를 만들지 않으며 `pageshow.persisted` 복귀 시 인증 재검증 reload를 수행한다. machine detail은 `Cache-Control: no-store`, `Vary: Authorization`, ETag/Last-Modified 0이다. logout→Back과 bearer current→previous→폐기 전환에서 브라우저·shared proxy가 이전 metric body를 한 byte도 재사용하지 않는다.

control-plane request는 `docs/harness/foms_request_body_classes.json`의 method+route template→class가 정본이며 각 class는 `max_files,max_file_bytes,max_total_file_bytes,max_body_bytes`를 별도 필드로 가진다. `RequestLimitsMiddleware`가 Flask request/JSON/form parser 전에 `PATH_INFO`+method를 longest-static-template-first로 매칭해 Content-Length를 검사하고, length 없음/chunked body는 hard byte-counting `wsgi.input` wrapper가 `max_body_bytes+1` read에서 `RequestEntityTooLarge`를 발생시킨다. control-plane의 non-identity `Content-Encoding`은 parse 전 415 `UNSUPPORTED_CONTENT_ENCODING`으로 거부한다. exact Flask 2.3.3/Werkzeug 2.3.8에서 `FomsRequest(flask.Request)`는 `max_form_memory_size=1MiB`, `max_form_parts=1000`과 `make_form_data_parser()` override를 사용한다. custom `FormDataParser`/`MultiPartParser.start_file_streaming`이 request-scoped file counter와 shared total-file byte budget을 만들고, 각 `SpooledTemporaryFile` sink를 cap+1 write에서 즉시 실패하는 limited sink로 감싼다. part의 declared Content-Length는 early reject에만 쓰고 신뢰하지 않으며 실제 streamed bytes가 개별/합계 cap의 정본이다. 413/parse exception은 request가 연 모든 partial sink를 `finally`에서 close하고 named tempfile이면 unlink한 뒤 filename/path를 log하지 않는다.

cap은 telemetry body 2KiB, login/account body 16KiB, normal JSON/form body 1MiB, Excel은 file 1개·file/total≤10MiB·body≤10MiB+64KiB, 승인된 legacy multipart는 purpose별 file 수/개별/합계 manifest를 가지되 합계≤50MiB·body≤50MiB+256KiB, unknown mutation body 1MiB fail-closed다. app global body ceiling은 `50MiB+256KiB`이며 multipart boundary/header overhead도 이 안에서 유한하게 제한한다. file 수/개별/합계/body/field-memory/part 수 중 하나라도 초과하면 handler/service/DB 전에 413 `REQUEST_BODY_TOO_LARGE` JSON envelope+request_id다. middleware/parser-generated 413/415에서 application handler 진입 0이다. 대용량 file data plane은 server-derived presigned upload만 사용한다. parser tests는 declared length 없는 chunked file/aggregate cap+1, 거짓 part length, body/file/total cap+1, boundary overhead 정상/초과, field 1MiB+1, part1001, 모든 partial temp close/unlink와 dependency golden version을 검증한다.

호환 기간의 공용 `readApiError(response, data)`는 새 `error.message`를 우선하고 legacy `data.message`, string `data.error`, non-JSON body를 차례로 처리한다. production desktop/tablet/mobile, construction, quest, finance command가 이 adapter를 사용한다. timeout, malformed JSON, 401/403/409/428에서 visible error, reload 0, DOM 이동 0, control re-enable, DB/event 변화 0을 browser test한다.

---

## 5. PR 그래프와 실행 순서

```text
BASE-00
 ├─ PACKET-HARNESS-00
 ├─ OPS-ROUTE-01
 ├─ API-ERROR-01 → FAILOPEN-01
 ├─ API-ERROR-01 → REQUEST-LIMIT-01
 ├─ PROXY-01 + REQUEST-LIMIT-01 → WRITE-GUARD-01
 ├─ PGTEST-00 → REV-00
 │              └─ PGTEST-00 + WRITE-GUARD-01 → OPS-APPROVAL-00
 │                 ├─ CUTOVER-MODE-01
 │                 └─ BACKFILL-ARTIFACT-00
 │   ├─ REV-CLEANUP-01
  │   ├─ SIDEFX-00 → SIDEFX-WORKER-01 → SIDEFX-RETENTION-01
 │   ├─ ASSIGNMENT-00 + SESSION-SIGNING-SECRET-01 + WRITE-GUARD-01 → AUTH-01
 │   │   ├─ AUTH-QUEST-READ-01
 │   │   └─ CHANNEL-AUTH-01
 │   └─ ITEM-ID-00
 │   └─ CREW-00
 ├─ STATE-MODEL-00 → STATE-AXES-REPAIR-00
 │                 ├─ PRODUCTION-BACKFILL-00
 │                 └─ QUEST-BACKFILL-00
 │                 └─ AS-BACKFILL-00
 ├─ MIG-WEB-RETIRE-01
 ├─ SECRET-01 → SECRET-02
 │             └─ SECRET-02 + PGTEST-00 + OPS-APPROVAL-00 + CUTOVER-MODE-01 → SESSION-SIGNING-STATE-00 → SESSION-SIGNING-SECRET-01
 ├─ FE-SYNTAX
 ├─ FE-XSS
 ├─ STORED-XSS-01
 ├─ PUSH-01
 ├─ SURFACE-GATE-01
 ├─ DESIGNER-RETIRE-01
 ├─ TASK-BACKFILL-00
 └─ (reserved for independent containment packets)

REV-00 + SIDEFX-00 + SIDEFX-WORKER-01 + AUTH-01 + STATE-MODEL-00
  └─ STATE-CORE-00
      ├─ PRODUCTION-BACKFILL-00 → STATE-PROD-01 → STATE-PROD-ACTIONS-01
      ├─ AUTH-QUEST-01 + QUEST-BACKFILL-00 → STATE-QUEST-01
      ├─ ITEM-ID-00 + TASK-01 → DATA-01 → STATE-FORM-01
      └─ STATE-OVERLAY-01
REV-00 + API-ERROR-01 → ERR-UX-01
WRITE-GUARD-01 + REQUEST-LIMIT-01 + OPS-APPROVAL-00 → AUTH-ACCOUNT-01 → PASSWORD-POLICY-01
WRITE-GUARD-01 → AUTH-IMPERSONATION-01

REV-00 + AUTH-01 + STATE-MODEL-00
  └─ DELETE-CORE-00
      ├─ DELETE-BULK-01
      └─ DELETE-TRASH-01
      └─ OPS-APPROVAL-00 + DELETE-RETENTION-01
DATA-01 + REV-00 + AUTH-01 + SIDEFX-00 + SIDEFX-WORKER-01 → DATA-MEASUREMENT-01
STATE-QUEST-01 + ASSIGNMENT-00 + ITEM-ID-00 + DATA-01 + DATA-MEASUREMENT-01 + STATE-MODEL-00 → ORDER-CREATE-01
ORDER-CREATE-01 + SIDEFX-WORKER-01 → DRAFT-LIFECYCLE-01
ORDER-CREATE-01 + STATE-QUEST-01 + ASSIGNMENT-00 → ORDER-COPY-01
ORDER-CREATE-01 + SIDEFX-WORKER-01 → ORDER-IMPORT-01
ORDER-CREATE-01 + SIDEFX-WORKER-01 + CHANNEL-WEBHOOK-AUTH-01 + OPS-APPROVAL-00 → CHANNEL-INBOUND-ORDER-01
REV-00 + AUTH-01 + STATE-CORE-00 → STATE-LEGACY-01

REV-00 + AUTH-01
  ├─ AUTH-FINANCE-01
  ├─ AUTH-QUEST-READ-01 → AUTH-QUEST-01
  ├─ CHANNEL-AUTH-01
  │   ├─ REQUEST-LIMIT-01 + API-ERROR-01 → CHANNEL-FUNCTION-CONTRACT-01
  │   └─ SIDEFX-WORKER-01 → CHANNEL-WRITER-01
  ├─ ACTOR-STATE-01 → CHAT-ROOM-01
  ├─ SIDEFX-WORKER-01 + ACTOR-STATE-01 → URGENT-CALL-01
  ├─ TASK-BACKFILL-00 → TASK-01
  ├─ WDC-XSS-01
  ├─ WDC-AUTH-01 + PGTEST-00 + OPS-APPROVAL-00 + BACKFILL-ARTIFACT-00 → WDC-LINK-FENCE-00 → WDC-LINK-BACKFILL-00 → WDC-LINK-01
  ├─ ERP-ESTIMATE-01
  ├─ CALL-LOG-01
  ├─ EVENT-REVERT-01
  ├─ PACK-01
  ├─ STORAGE-WRITER-01
  ├─ WIZ-PRESET-01
  ├─ CREW-00 → SHIPMENT-REFERENCE-01
  ├─ ITEM-ID-00 → WIZ-01
  │   ├─ SIDEFX-00 + SIDEFX-WORKER-01 + WIZ-01 → WIZ-TRANSFER-01
  │   └─ SIDEFX-00 + SIDEFX-WORKER-01 + WIZ-01 → WIZ-DELETE-01
  └─ UPLOAD-01 → FILE-LEGACY-AUDIT-00 → FILE-LEGACY-BACKFILL-01 → FILE-01
                                                              └─ UPLOAD-INTENT-01
ITEM-ID-00 + FILE-01 + UPLOAD-INTENT-01 + SIDEFX-WORKER-01 → UPLOAD-02 → UPLOAD-CHAT-01
UPLOAD-CHAT-01 + CHAT-ROOM-01 → CHAT-MESSAGE-01 → CHAT-FILE-01
CHAT-MESSAGE-01 → CHAT-SOCKET-AUTH-01
WDC-LINK-01 + CUTOVER-MODE-01 → WDC-LINK-CLEANUP-01
UPLOAD-02 + FILE-LEGACY-BACKFILL-01 + STATE-CORE-00 → BLUEPRINT-01
STATE-MODEL-00 + FILE-LEGACY-BACKFILL-01 → DRAWING-REVISION-BACKFILL-00

STATE-CORE-00 + STATE-QUEST-01 + DRAWING-REVISION-BACKFILL-00 + WIZ-TRANSFER-01 + UPLOAD-02 → STATE-DRAWING-01
STATE-MODEL-00 + ASSIGNMENT-00 + UPLOAD-02 → CONSTRUCTION-BACKFILL-00
STATE-CORE-00 + CONSTRUCTION-BACKFILL-00 → STATE-CONST-CS-01
STATE-CORE-00 + DRAFT-LIFECYCLE-01 + UPLOAD-INTENT-01 + UPLOAD-02 + AS-BACKFILL-00 → STATE-AS-01
STATE-AS-01 + ASSIGNMENT-00 + CREW-00 + REV-00 + AUTH-01 → SHIPMENT-WRITER-01

DELETE-TRASH-01 + STATE-AS-01 + STATE-OVERLAY-01 → STATE-CONTROLS-01
STATE-PROD-01 + STATE-PROD-ACTIONS-01 + STATE-CONST-CS-01 + STATE-DRAWING-01 + STATE-AS-01 + STATE-QUEST-01 + STATE-FORM-01 + STATE-OVERLAY-01 + STATE-CONTROLS-01 + STATE-AXES-REPAIR-00 + DELETE-CORE-00 + DELETE-BULK-01 + DELETE-TRASH-01 + DELETE-RETENTION-01 + ORDER-CREATE-01 + ORDER-COPY-01 + ORDER-IMPORT-01 + CHANNEL-INBOUND-ORDER-01 + DRAFT-LIFECYCLE-01 + STATE-LEGACY-01 + ERP-ESTIMATE-01 + STORAGE-WRITER-01 + BLUEPRINT-01 + EVENT-REVERT-01 완료
  → STATE-GUARD-01

SHELL-01, HISTORY-01, ROUTE-01
SW-01 + CUTOVER-MODE-01 + WRITE-GUARD-01 + OPS-APPROVAL-00 → OFFLINE-01

REV-99 depends_on exact:
  OPS-ROUTE-01, API-ERROR-01, FAILOPEN-01, REQUEST-LIMIT-01, PGTEST-00, OPS-APPROVAL-00, CUTOVER-MODE-01, BACKFILL-ARTIFACT-00, REV-00, REV-CLEANUP-01
  SIDEFX-00, SIDEFX-WORKER-01, SIDEFX-RETENTION-01, ASSIGNMENT-00, CREW-00, SHIPMENT-REFERENCE-01, ITEM-ID-00, MIG-WEB-RETIRE-01
  SECRET-01, SECRET-02, SESSION-SIGNING-STATE-00, SESSION-SIGNING-SECRET-01, FE-SYNTAX, FE-XSS, STORED-XSS-01, SURFACE-GATE-01, DESIGNER-RETIRE-01
  PUSH-01, PACK-01, ERR-UX-01, AUTH-01, WRITE-GUARD-01, AUTH-ACCOUNT-01, PASSWORD-POLICY-01
  AUTH-FINANCE-01, AUTH-QUEST-READ-01, AUTH-QUEST-01, CHANNEL-AUTH-01, CHANNEL-FUNCTION-CONTRACT-01, CHANNEL-WEBHOOK-AUTH-01, CHANNEL-WRITER-01, DELETE-CORE-00, DELETE-BULK-01, DELETE-TRASH-01
  DELETE-RETENTION-01, AUTH-IMPERSONATION-01, ACTOR-STATE-01, CHAT-ROOM-01, CHAT-MESSAGE-01, CHAT-SOCKET-AUTH-01, URGENT-CALL-01, TASK-BACKFILL-00
  TASK-01, WDC-XSS-01, WDC-AUTH-01, WDC-LINK-FENCE-00, WDC-LINK-BACKFILL-00, WDC-LINK-01, WDC-LINK-CLEANUP-01, ERP-ESTIMATE-01, CALL-LOG-01
  EVENT-REVERT-01, STATE-MODEL-00, STATE-AXES-REPAIR-00, PRODUCTION-BACKFILL-00, QUEST-BACKFILL-00, AS-BACKFILL-00, STATE-CORE-00, STATE-PROD-01
  STATE-PROD-ACTIONS-01, CONSTRUCTION-BACKFILL-00, STATE-CONST-CS-01, STATE-DRAWING-01, DRAWING-REVISION-BACKFILL-00, STATE-AS-01, STATE-QUEST-01, DATA-01
  DATA-MEASUREMENT-01, SHIPMENT-WRITER-01, ORDER-CREATE-01, ORDER-COPY-01, ORDER-IMPORT-01, CHANNEL-INBOUND-ORDER-01, STATE-FORM-01, STATE-OVERLAY-01
  DRAFT-LIFECYCLE-01, STORAGE-WRITER-01, STATE-LEGACY-01, STATE-CONTROLS-01, STATE-GUARD-01, WIZ-01, WIZ-PRESET-01, WIZ-TRANSFER-01
  WIZ-DELETE-01, UPLOAD-01, FILE-LEGACY-AUDIT-00, FILE-LEGACY-BACKFILL-01, FILE-01, UPLOAD-INTENT-01, UPLOAD-02, BLUEPRINT-01
  UPLOAD-CHAT-01, CHAT-FILE-01, SHELL-01, HISTORY-01, ROUTE-01, SW-01, OFFLINE-01, PROXY-01, RUM-INGEST-01, WAM-TELEMETRY-01

STARTUP-PURE-01 depends_on exact: STARTUP-SCHEMA-01, STARTUP-BACKFILL-01, STARTUP-ADMIN-01
AUTH-ACCOUNT-01 → STARTUP-ADMIN-01
RELEASE-GATE-00 depends_on exact:
  REV-99, STARTUP-SCHEMA-01, STARTUP-BACKFILL-01, STARTUP-ADMIN-01, STARTUP-PURE-01,
  SCALE-AS-01, SCALE-CHANNEL-01, SCALE-SKETCHUP-01, BACKUP-01, INDEX-OPS-01

SCALE-AS-01 / SCALE-SKETCHUP-01 / BACKUP-01 / INDEX-OPS-01
  → main remediation과 독립, production-like 측정·ops 승인 뒤 실행
PROXY-01은 late/independent packet이 아니며 Railway proxy-chain evidence를 확보한 뒤 WRITE-GUARD-01보다 먼저 완료한다. WRITE-GUARD-01은 OPS approval UI보다 먼저 배포되므로 bootstrap cookie-mutation 예외가 없다.
CHANNEL-INBOUND-ORDER-01 → SCALE-CHANNEL-01 (전용 service provision 뒤 production-like capacity gate)
PROXY-01 + REQUEST-LIMIT-01 → RUM-INGEST-01
PROXY-01 + REQUEST-LIMIT-01 + API-ERROR-01 + SESSION-SIGNING-SECRET-01 → WAM-TELEMETRY-01
PGTEST-00 + REQUEST-LIMIT-01 + API-ERROR-01 → CHANNEL-WEBHOOK-AUTH-01
```

`BACKFILL-ARTIFACT-00` direct consumer exact set은 `ASSIGNMENT-00,CREW-00,ITEM-ID-00,TASK-BACKFILL-00,WDC-LINK-BACKFILL-00,WDC-LINK-CLEANUP-01,STATE-MODEL-00,STATE-AXES-REPAIR-00,PRODUCTION-BACKFILL-00,QUEST-BACKFILL-00,AS-BACKFILL-00,CONSTRUCTION-BACKFILL-00,DRAWING-REVISION-BACKFILL-00,FILE-LEGACY-AUDIT-00,FILE-LEGACY-BACKFILL-01,BLUEPRINT-01,CHAT-FILE-01,STARTUP-BACKFILL-01` 18개다(DESIGNER-OWNER-BACKFILL-00은 Brain 삭제로 제외). WDC V2 phase는 WDC DB, cleanup phase는 primary DB checkpoint를 쓴다. ID 이름 heuristic은 금지한다.

`OPS-APPROVAL-00` direct consumers exact set은 `BACKFILL-ARTIFACT-00,CUTOVER-MODE-01,SESSION-SIGNING-STATE-00,SESSION-SIGNING-SECRET-01,AUTH-ACCOUNT-01,CHANNEL-INBOUND-ORDER-01,WDC-LINK-FENCE-00,DELETE-RETENTION-01,OFFLINE-01` 9개다. routine policy retention worker는 이 set이 아니며, 승인 필수 operation exact enum은 approval manifest가 검증한다.

사용자-facing command 연결은 `ERR-UX-01` 이후에 merge한다. BASE-00은 direct bootstrap, PACKET-HARNESS-00은 BASE-00만 의존한다. 그 밖의 모든 packet은 `dependency_classes.packet_harness=true`라 PACKET-HARNESS-00 effective edge를 가진다. `backfill_artifact=true`는 위 18개 exact set과 일치해야 한다. `write_guard=true`는 packet이 소유한 URL-map의 cookie-auth mutation route가 하나 이상일 때이고 Function/Webhook/RUM/pure calculation은 false다. `postgres=true`는 migration, row/advisory lock, SKIP LOCKED, concurrency invariant 중 하나라도 소유할 때다. test는 URL-map/created migration+PG test manifest와 각 boolean을 양방향 비교해 false 누락과 false-positive를 모두 red로 만든다. ASCII는 explicit `depends_on`만 표시하고, machine manifest의 effective edge는 `explicit ∪ dependency_classes` 공식으로 계산한다. 따라서 graph exact 비교는 explicit끼리, class exact 비교는 각 machine inventory끼리 별도로 한다. `TRANSFER_DRAWING_REVISION`과 `CUSTOMER_CONFIRM`은 STATE-DRAWING-01만 소유하고 선행 adapters가 한 transaction/version/event로 조립된다.

### 5.1 공통 PR 계약

모든 PR description은 다음을 반드시 포함한다.

1. 기준 SHA와 finding ID.
2. 변경 파일·함수와 변경하지 않을 경계.
3. 먼저 추가한 실패 테스트와 수정 후 결과.
4. persona, viewport, 클릭, network status, DB/event invariant.
5. 데이터 사전감사·repair 필요 여부.
6. rollback 방식. 보안 취약 경로 재활성화 rollback은 금지.
7. perf guard와 server TTFB 영향.
8. audit/backfill packet이면 `BACKFILL-ARTIFACT-00`과 7.3의 `--artifact-dir` payload-only manifest/sha/safe+manual/active-ADMIN approval/DB checkpoint/completed-after+pending-before composite/row-lock drift 계약과 stale artifact STOP evidence.

### 5.2 PR packet

> 근거 주: 대부분 packet은 §3 P0/P1 finding에 앵커되지만, 일부(`CALL-LOG-01`·`STORAGE-WRITER-01`·`CHANNEL-WRITER-01`·`SHIPMENT-REFERENCE-01` 등 writer-migration packet과 `BASE-00`·`PACKET-HARNESS-00`·backfill류 bootstrap)는 재현된 결함이 아니라 §2 제품 결정과 §3.3 writer inventory 불변식(모든 writer가 version/receipt/policy를 경유)이 근거다. 이들의 "먼저 실패 테스트"(§5.1-3)는 결함 재현이 아니라 architectural invariant test(무경유 writer 존재=red)로 충족한다. gold-plating이 아니라 REV-99 불변식의 구성요소다.

| PR | 변경 경계·파일 | 완료 조건 | rollback / 금지 혼합 |
|---|---|---|---|
| BASE-00 | 이 문서, 관련 line/symbol inventory test | HEAD drift 0, current targeted tests 기록 | 문서만. 기능 수정 금지 |
| PACKET-HARNESS-00 | packet/deploy runners+manifests, completion/reissue/promotion evidence, Railway/GitHub collector, build-compat verifier, harness tests/CI | explicit/class exact; own-entry append; trigger별 canonical SHA, historical entry hash, ephemeral artifact reissue; cherry-pick patch-id mapping; pre-CUTOVER provider bootstrap/post-CUTOVER heartbeat; hash/freshness/env | harness/schema/CI만; future check preseed·artifact 영구원장 주장·PR merge SHA 오사용·repo ledger·eval 금지 |
| OPS-ROUTE-01 | `foms/api/debug.py`, public blueprint, `foms/ops_app.py`, `railway-ops-readiness.toml`, Channel readiness, `/healthz`, token rotation/cache runbook/test | deployed `/debug-db`·public Channel detail·public-app `/internal/ops/*` 404; `/healthz` status+commit만; ADMIN detail은 session+private/no-store/Vary Cookie, machine detail은 no-public-domain Railway ops service+random≥32-byte bearer+no-store/Vary Authorization; ETag/Last-Modified 0; logout/Back·bearer rotation cache reuse 0; anon/VIEWER/STAFF/MANAGER/invalid bearer 403/404와 metric 차등 0 | public debug/detail route 복구·health에 DB/schema/secret 정보 추가·민감 detail cache 허용 금지 |
| API-ERROR-01 | JSON/HTML exception handlers, request-id protected logger/redaction filter, leak inventory/static guard | unexpected 500=`INTERNAL_ERROR`+고정 문구+request_id; response/SecurityLog/client telemetry의 exception/traceback/secret/path/SQL 0; raw print/print_exc 0; protected structured exception+stack 1; expected domain mappings 유지 | exception 문자열 client 전달·central logger 외 traceback·raw request/credential/object key log 금지 |
| FAILOPEN-01 | Python AST scanner, `docs/harness/foms_failopen_inventory.json`, shared logging/fail-closed helpers | current broad/silent catches 100% owner+disposition+test 분류, 신규 unclassified 0; release mode에서 unresolved/silent broad pass 0 | blanket catch 삭제로 기능 의미 변경·무근거 allowlist·lint disable 금지 |
| REQUEST-LIMIT-01 | pre-Flask WSGI hard body stream, `FomsRequest.make_form_data_parser`, custom multipart parser/limited temp sink, 4-field route manifest, Railway smoke | exact Flask2.3/Werkzeug2.3; telemetry2KiB/login16KiB/normal1MiB, Excel files1/file+total10MiB/body+64KiB, legacy purpose별 file-count/file/total≤50MiB/body+256KiB, global body50MiB+256KiB; declared/chunked/file/aggregate/overhead cap+1 pre-handler413, encoded415, streamed bytes authoritative, form memory1MiB/parts1000, every partial tempfile close/unlink, presigned 제외 | default parser가 file cap을 준다고 가정·file cap=body cap·global500MiB·parse 뒤 검사·upload app-memory proxy·API HTML error 금지 |
| PGTEST-00 | `tests/postgres/conftest.py`, `tools/tests/run_postgres_concurrency.ps1`, CI PostgreSQL service, smoke test | PostgreSQL lane 자체 green; host localhost/127.0.0.1·DB `foms_test_*`만, public/Railway 즉시 fail | 테스트 인프라만; 미래 mutation test 생성 금지 |
| OPS-APPROVAL-00 | principal-version table/trigger, approval request model/UI/CLI, exact operation manifest, protected control-root/token, reservation/reconciler, PG/cross-DB tests | WRITE-GUARD 선행; operator가 approver ID 지정 불가; Admin password reauth+principal version이 exact operation/scope/artifact/version/generation/15분 nonce를 승인; same-DB atomic; cross-DB는 valid reservation snapshot 뒤 target unique audit+crash finalize; manifest↔CLI exact; token lifecycle; expiry/pre-reservation role/version/replay/race mutation0 | business operation 구현·raw token/PII log·ID 입력 승인·범용 token·RESERVED 사후 취소 주장 금지 |
| BACKFILL-ARTIFACT-00 | protected encrypted artifact I/O, manifest/manual editor, run/checkpoint/append-approval models, reauthorize/purge CLI, PG tests | repo/sync/weak-ACL root fail; ciphertext payload/self-hash0; run ID=packet+phase+manifest+mapping; target write+checkpoint same tx; completed-after/pending-before; Admin succession CAS/business0; WDC V2 checkpoint=WDC DB, cleanup=primary DB; TTL key destruction | plaintext/temp/cloud-sync·business mapper·phase conflation·file-only approval·artifact git add 금지 |
| CUTOVER-MODE-01 | fences/markers+replica-heartbeat migration, transactional mode, `foms/build_compatibility.json`+Docker/startup, DRAIN/COMPATIBLE CLIs/manifest, PG/provider/perf | 15 family; image generation CI bind; desired-replica heartbeat; mutation KEY SHARE through outbox insert; mark FOR UPDATE drain; DRAIN blocks new writer then jobs/leases/provider0, COMPATIBLE versioned effect; mark 뒤 legacy business/outbox0; abort-drain; DB fault503; old generation fail | external I/O 중 DB lock·marker-only read·SHA order·cache·provider signature 추정·marker delete/downgrade 금지 |
| REV-00 | Order version+parent receipt/resources+cache family generation models/Alembic, mutation service/client, PG/perf/browser tests | same-key race write1; resources[] single/batch≤1000 exact; sorted family generation increment in business tx; worker/Redis fail에도 absent source/destination cache cross-actor fresh; cookie/header scope/TTL; lock-wait+TTFB gate | client family/version 신뢰·actor receipt만으로 cross-actor 보장 주장·endpoint cutover 전 MODE=ENFORCED 금지 |
| REV-CLEANUP-01 | `tools/ops/purge_order_mutation_receipts.py`, scheduler config, ops test | daily `--retention-days 7 --batch-size 1000 --apply`, dry-run/advisory/resume/progress/nonzero; parent delete가 expired read-resource child cascade, active 24h/replay와 family generation rows 불변 | active receipt/resource·cache family generation 삭제 금지 |
| SIDEFX-00 | typed-domain outbox/heartbeat model+migration+repository | exact source-domain/FK CHECK one-of matrix, mismatched/orphan reject, unique dedupe and queue/lease indexes, tx insert, retention | schema/repository만; worker/command endpoint 혼합 금지; legacy Channel outbox 재사용 금지 |
| SIDEFX-WORKER-01 | `tools/ops/run_domain_side_effect_outbox.py`, `tools/ops/check_sidefx_readiness.py`, `railway-domain-sidefx.toml`, ops runbook | `SKIP LOCKED`, lease/reclaim/max10, 5s delivery; 300s bounded upload/draft/import-artifact expiry scan+advisory; heartbeat<30, delivery lag<60, scan lag<360, DEAD0; REQUIRE_DELIVERY/EXPIRY/DEGRADED_OK matrix contract tests | unhealthy urgent send와 ticket/draft/pending create만 precommit 503; ordinary effect는 outbox tx+PENDING. request nudge/postcommit queue를 정본으로 사용 금지 |
| SIDEFX-RETENTION-01 | `tools/ops/purge_domain_side_effect_outbox.py`, 공용 worker daily provider, retention runbook/test | dry-run default; SUCCESS completed_at>30일, DEAD dead_at>180일만 ID batch1000+advisory lock로 purge; PENDING/PROCESSING 0; daily retention heartbeat, lag<90000s, resume/progress/nonzero; worker가 86400s마다 호출 | 별도 scheduler/worker·source business row 삭제·broad date delete 금지 |
| REV-99 | mutation policy/writer/consumer architecture tests, enforcement flag | 모든 order/JSONB writer가 version bump+If-Match/idempotency metadata, 모든 consumer 새 error envelope, offline queued writer 0; 이후 428 ON | 누락 writer/consumer가 있으면 merge 금지 |
| RELEASE-GATE-00 | `tools/ops/check_foms_remediation_readiness.py`, final manifest/browser/failopen artifact verifier, ops runbook | packet/CI/data coverage/flags/worker/persona artifact, API leak 0, unresolved/silent broad catch 0을 값 노출 없이 확인; exit 0=ready·1=data·2=service·3=artifact/config 오류 | application mutation 금지; 실패 항목이 있으면 deploy 중단 |
| ASSIGNMENT-00 | `order_assignments` model/Alembic, claim/single+batch assign/release service, ID picker, legacy name audit/backfill | source enum, active uniques, ID-only auth, release history, sorted-lock batch all-or-none, row lock+version+event, inactive release, ambiguous manual CSV+reason | JSONB name authorization·row별 batch commit 금지; ambiguous row에서 AUTH enforcement 금지 |
| CREW-00 | `installation_workers`, `order_installation_assignments`, worker CRUD, crew picker/audit/backfill | external worker ID lifecycle, 0..20 replace/release history, partial unique/concurrency, linked user validation, in-use deactivate 409, display projection; auth 영향 0 | free-name worker master write·crew row authorization 사용 금지 |
| SHIPMENT-REFERENCE-01 | shipment settings page/API, SystemSetting migration | exact four-list schema, SHIPMENT/Admin policy, settings If-Match/version/receipt/audit, old drawing fields safe normalize, desktop persona | construction worker master·per-order shipment write 혼합 금지 |
| ITEM-ID-00 | `order_item_identities` UUID registry/tombstone, `OrderAttachment.item_id`, `OrderScheduleDate.item_id`, model/date-sync/read-model migration+audit/backfill | DB-global unique, order binding, immutable/no-reuse; attachment/schedule index exact backfill, ambiguous CSV 0건 전 enforcement | JSONB-only identity·index positional auth/link 금지; schedule을 common으로 이동 금지 |
| MIG-WEB-RETIRE-01 | `foms/web/admin/routes.py`, admin nav/template, `scripts/migrations/web_migration.py` | 모든 역할 `/admin/migration` 404, web reset route/control/helper symbol 0 | route/helper 재활성화 금지. legacy import CLI 신설은 실제 요구 확인 후 별도 spec |
| SECRET-01 | geocode config, Scheduler config, address/map clients, `docs/ops/foms_secret_rotation.md`, `check_foms_secret_config.py` | REST literal 0; env name/source/consumer inventory, redacted preflight, new env→deploy smoke→old key revoke 순서; 누락은 해당 API만 503, public JS key domain smoke | secret 값 출력·구 REST key 폐기 후 literal rollback 금지 |
| SECRET-02 | `tests/qa_deploy_test.py`, secret store/env | literal 0, 누락 credential fail-fast | credential 값을 log/문서에 기록 금지 |
| SESSION-SIGNING-STATE-00 | additive signing-state/WAM-nonce migration+models, pure key-format/slot inspect, legacy material audit, prepare CLI | old runtime compatibility; EMPTY seed; Flask/WAM raw fingerprint별 BRIDGE vs FORCE_REAUTH; key-ID-only artifact와 env 대조 후 pending key ID/generation/grace/expected consumer SHA를 deadline null로 EMPTY→READY; rotation prepare CURRENT_ONLY→ROTATION_READY; migration/audit/inspect/prepare separate deploy | provider/session interface·READY consumer·ACTIVE/ROTATING/deadline·cookie/token 의미 변경·consumer와 한 PR/deploy 금지 |
| SESSION-SIGNING-SECRET-01 | versioned provider/session, FORCE rescue, maintenance/WAM-expired pages, quiescence/smoke/diagnosis, rotation/emergency runbook | BRIDGE; FORCE rescue predeploy→AUTH_ONLY→30s counters0→activate→smoke; failed smoke fixed descendant/fresh NEXT; old WAM recovery; 5/10m alert; compromised ACTIVE; N-worker | AUTH_ONLY 뒤 첫 image·smoke 전 OFF·known rollback·pending sign·local fallback·secret 출력 금지 |
| FE-SYNTAX | `erp-attachment-preview-open.js`, parser test | `node --check` green; mobile 2+ images click/swipe/Enter | 독립 revert 가능 |
| FE-XSS | measurement 3 templates, render tests | quote/`</script>`/U+2028 payload 실행 0 | route/order 변경 금지 |
| STORED-XSS-01 | SecurityLog producer/filter/admin template, order edit/list, 3 drawing JS, `workbench_detail_body.html`, `admin/change_logs.html`, `docs/harness/foms_untrusted_dom_sinks.json`, static gate/browser tests (Designer `wdplanner_v2.html` sink는 DESIGNER-RETIRE-01 삭제로 제외) | manifest가 persisted/API/model→HTML/JS sink의 path/symbol/source field/disposition/test를 100% 열거. log는 escape 후 `주문 #digits`만 server-built link; option/product/spec는 autoescape+CSS pre-line; User.name/team은 DOM node+textContent, user ID integer allowlist; change cards는 createElement/textContent+addEventListener/data binding, inline onclick/JSON attribute 0; dynamic untrusted innerHTML 0. 기존 hostile rows/profile/event에서 script/network 0과 기능 유지 | 입력 HTML 금지로 대체·blanket escapeHtml/Markup·기존 hostile data 삭제 금지 |
| SURFACE-GATE-01 | shared order-edit cohort controller, form chooser, mobile shell/detail CSS, contract/browser test | predicate `max-width:991.98px OR min-width:992px+coarse+physical portrait` 한 함수. MQL/screen-orientation change: pristine은 section 보존 reload/re-render로 반대 form 생성 후 정확히 1개, dirty는 current cohort class를 동결+값 보존+non-dismiss banner 후 save 성공 때 새 cohort reload. visualViewport keyboard resize만으로 flip 0; 390×844와 1024×1366↔1366×1024 양방향 pristine/dirty, keyboard open/close; 모든 section click 후 navTop≥headerBottom·targetTop≥navBottom, overlap/overflow 0; current brittle CSS comment test를 declaration parser로 교정 | 반대 form 영구 삭제 후 무대응·dirty 자동 reload/data loss·business form·tablet production kanban 변경 금지 |
| DESIGNER-RETIRE-01 | FOMS Brain 전 표면 삭제: `foms/api/designer/*` blueprint·라우트, `templates/designer/wdplanner_v2.html`, `/wdplanner-v2` 라우트+nav 링크, designer 전용 JS/CSS, 관련 테스트 (독립 즉시 봉쇄, BASE-00만 의존) | 모든 designer route/nav GET·POST 404, 템플릿·정적자산·blueprint 등록 0, 잔존 UI 진입점 0; `import app; APP_OK` 회귀 0; 삭제로 P0-13·P0-24 재현 불가 확인 | DB `designer_*` 테이블/데이터 변경 금지(별도 retention spec); Designer 기능 재활성화·auth 재설계로 대체 금지 |
| PUSH-01 | `push_sender.py`, `static/sw.js`, push contract tests | nested `data.notification_id/deep_link` 우선, top-level fallback, same-origin sanitize | subscription/auth 수정 혼합 금지 |
| PACK-01 | packing API+template, `foms-packing.js`, `erp-shell.js` fixture | policy+If-Match+receipt+version/event, submit 1회=POST 1, shell GET 0 | logistics/state·shell navigation 본수술 혼합 금지 |
| ERR-UX-01 | `static/js/foms/foms-write.js`, production scripts, tablet production JS, construction complete JS | 공용 error parser; timeout/malformed JSON/403/409/428에서 visible error·reload 0·DOM rollback·button re-enable | API policy/state 의미 변경 금지 |
| AUTH-01 | 신규 `order_mutation_policy.py`, JSON/page guards, UI policy context, URL-map inventory, packing read/write 분리 | VIEWER mutation 403, production team-wide, construction/drawing ID assignment, `/api` redirect 0, unclassified route fail | ASSIGNMENT-00+backfill gate 선행; business state 변경 금지 |
| WRITE-GUARD-01 | 공용 CSRF token+Origin guard 정본 `request_write_guard.py`(신규/확장)와 client, route/socket manifest `write_guard` field | cookie mutation JSON/form cross-origin 403 DB0, GET logout/switch 405, provider-authenticated Function/Webhook와 RUM exact exempt, missing metadata static fail | SameSite/header-only·route별 ad hoc token 금지 |
| AUTH-ACCOUNT-01 | account/session/Admin invariant, rate-key state/buckets+replica boot/epoch heartbeat, exact bootstrap/rotation CLIs, login UX | legacy authority bridge; shadow failure dirty, reconnect-before-serve epoch bump, desired boot heartbeat 900s→CURRENT_ONLY; HMAC10/60/5; rotation; 3-viewport429/PG503; principal trigger session revoke; ops approval | READY PG authority·stale gap proof·server sleep·Redis authority·hard delete/partial/raw identity 금지 |
| PASSWORD-POLICY-01 | `users.password_policy_version`, ADMIN legacy-status filter, audit/banner/change/reset, audit/readiness+interactive rotation CLI | WARN legacy 업무 유지+390/1024/fragment persistent banner; 새/reset always strong; role별 count+Admin in-app LEGACY filter, hash/export0; secure prompt CLI; reset마다 count 감소, active count0 후 ENFORCED | hash rehash로 strength version 추정·WARN 업무 차단·inactive legacy blind reactivate·weak rollback·password argv/env/log 금지 |
| AUTH-FINANCE-01 | settlement/cash/payment-confirm endpoint+UI | ADMIN/MANAGER·STAFF/CS/SALES만; 거부 DB/event/log 0 | login-only rollback 금지; `test_cash_receipt_issue_api.py`+신규 matrix |
| AUTH-QUEST-READ-01 | `quest.py` GET | quest 없는 반복 GET도 JSONB/version/event 변화 0; creation은 기존 mutation path에만 남기고 STATE-QUEST-01에서 transition tx로 이관 | GET에서 commit 복구 금지 |
| AUTH-QUEST-01 | quest approve policy | actor team=current required team; DRAWING/CONFIRM standalone approval은 command-required 409; construction assignment; override reason | transition은 STATE-QUEST-01 전 직접 쓰기 금지 |
| CHANNEL-AUTH-01 | `channel_quick_actions.py`, `channel_identity.py`, canonical Order read-scope helper | missing/inactive/unmapped/DB error deny; manager id→canonical active User resolve 뒤 일반 Order detail과 같은 read policy를 customer/phone/address/schedule/assignee 조회 전에 적용; deny/nonexistent는 동일 no-data domain result와 PII 0, transport status/envelope는 provider adapter 소유; read-only라 receipt 없음 | active mapping만으로 모든 Order 허용·raw manager id auth·fail-open rollback 금지 |
| CHANNEL-FUNCTION-CONTRACT-01 | `channel_functions.py`, Function 전용 signature/config helper, provider fixture+method schema manifest, `signature-validation-spec.md`, current implementation guide | disabled blueprint404+provider-first disable gate; enabled official PUT/POST405; hex-decode≥32-byte key→raw body HMAC-SHA256→Base64 constant-time; missing/bad401, invalid JSON400; signed context channel/caller exact. redacted live registered method fixture/schema 필수; stale fixture retired; success/error 모두 provider200 `{result|error}`, deny/nonexistent generic 동일, PII/mutation0; key/channel missing fail-start | provider 호출 중 flag false·Webhook token/helper 재사용·raw UTF-8 key/hex digest·params DTO 추정/accept-all compatibility·direct response body 금지 |
| CHANNEL-WEBHOOK-AUTH-01 | Webhook token/config, typed live fixtures, receipt/conflict/intent/job migration, stable hash/JCS+versioned AES-GCM envelope, log redaction | disabled404+provider-first; official POST token; exact source/schema/hash; acceptance tx가 accepted_at+30d/envelope/ID-job 뒤만2xx; bad401, DB/job failure non2xx; soak masked only; actual Order0 | provider 호출 중 false·freshness auth·plaintext/raw/PII/token log·Function signature·receipt 전2xx 금지 |
| CHANNEL-WRITER-01 | `channel_integration.py` drawing/estimate push metadata | send result+metadata typed command, Order version/receipt, side-effect dedupe; retry history/event 1 | auth/transport provider 변경 금지 |
| DELETE-CORE-00 | canonical soft-delete/restore service, delete metadata/projection fixture | main/overlay axes 보존, deleted projection만 set/clear, row lock+version+event | status string 직접 저장·hard delete 금지 |
| DELETE-BULK-01 | orders bulk status/UI | body별 version, all-or-none; STAFF/VIEWER delete 403 | trash route 혼합 금지 |
| DELETE-TRASH-01 | trash delete/restore/permanent-delete route/UI (WRITE-GUARD-01의 `request_write_guard.py`를 **소비**만, 소유 아님) | GET 405, POST+CSRF/Origin; restore overlay 보존; web hard-delete 제거 | draft discard·generic control 제거 혼합·공용 guard 파일 재정의 금지 |
| DELETE-RETENTION-01 | `tools/ops/purge_soft_deleted_orders.py`, `docs/ops/order_retention.md`, approval manifest | web hard-delete 대체; default dry-run, 최소 deleted 365일, exact order-ID file+`--before`+artifact/version에 묶인 `--approval-token-file`+`--apply`, same-tx consume, dependency/export report, advisory lock, row count/result hash와 operator/approver audit | CLI approver-ID·web/API 노출·broad range/no-ID purge·token 재사용·OrderEvent 개별 수정 금지 |
| AUTH-IMPERSONATION-01 | switch-user/back route/UI | POST+existing write guard; original actor/target/back audit | delete 변경 금지 |
| ACTOR-STATE-01 | notification mark/archive/ack와 push subscription | exact actor owner allowlist, child receipt/version, rate/audit; VIEWER own-resource positive와 cross-user 403 | chat endpoint/Order/business mutation 허용 금지 |
| CHAT-ROOM-01 | `channel/rooms.py` room/member lifecycle and UI | STAFF/Admin create with optional order scope, room+members one tx, creator/Admin manage, self leave, version/receipt, member unique, soft close/audit | VIEWER admin·orphan room·arbitrary order/user·hard delete 금지 |
| CHAT-MESSAGE-01 | HTTP message send/mark-read service+client | active member, text schema/rate, child receipt/version; UPLOAD-CHAT `commit=False` attachment claim+message one tx, retry message 1 | upload ticket 재구현·two commit·non-member send/read 금지 |
| CHAT-SOCKET-AUTH-01 | `socketio_handlers.py`, socket event manifest/static guard | active session+room membership on join/leave/typing/send/read, removed/closed room forced leave, canonical message service only; message_id별 recipient user-room emit 1회·sender echo 1회, reconnect member 1회, cross-user/removed receive 0 | HTTP policy만 신뢰·direct socket writer·room+user double broadcast 금지 |
| URGENT-CALL-01 | urgent target/send API와 desktop/mobile/drawing send controls | order read participant incl. VIEWER send, active target, 500 chars, rate 5/h, child receipt, notification+NotificationEvent+`source_domain=NOTIFICATION_EVENT` domain side-effect row one tx, 390px send; ack는 ACTOR-STATE existing regression/persona로만 소비 | 별도 notification outbox/worker·ack route 재구현·Order outbox/mutation·multi-commit delivery·cross-order target list 금지 |
| TASK-BACKFILL-00 | OrderTask expand schema, `audit_order_tasks.py`, `backfill_order_tasks.py` | UUID/version safe seed, LEGACY provenance, orphan/status/date/team/user/auto_key audit, MEASURE→SALES safe mapping, auto collisions 0, ambiguous quarantine/manual, coverage 100% | creator 추정·ambiguous active task enforcement 금지 |
| TASK-01 | `OrderTask` API, personal board, templates/`erp_automation.py` | parent scope, manual role/owner, exact team enum, task version/receipt/event, cancel history, typed auto upsert same tx, unique auto key | any-STAFF/arbitrary meta/hard delete/raw SQL postcommit 금지 |
| WDC-XSS-01 | `estimate-lifecycle.js` DOM construction | hostile strings text node, script 실행 0 | auth 변경 금지 |
| WDC-AUTH-01 | WDC blueprint policy registry | calculate pure; estimate CS/SALES; master MANAGER+; VIEWER read | calculate 금지 rollback 금지 |
| WDC-LINK-FENCE-00 | topology inspector/artifact, V2 state, SAME atomic dual-writer, SEPARATE runtime fence+freeze/canonical/abort, PG topology races | SAME uses one DB tx/no freeze; SEPARATE fence all-serving→drain/fingerprint/FROZEN503, approved abort only marker/write0+same fingerprint; topology drift STOP; V2 shadow legacy-inert | topology 추정·SAME cross-DB protocol·SEPARATE 2PC·marker 뒤 abort·V1 backfill 금지 |
| WDC-LINK-BACKFILL-00 | `EstimateOrderLinkV2` schema, topology-aware audit/backfill, V2_BACKFILL checkpoint | SAME online atomic dual-write/backfill; SEPARATE FROZEN backfill; unique pair, encrypted artifact/manual, phase run ID, source-target equivalence; V1/meta cleanup0 | legacy-visible V1 row 변경·SEPARATE unfrozen apply·phase conflation 금지 |
| WDC-LINK-01 | topology-aware canonical reader/writer+receipt, rollout checker | SAME marker 전 legacy read/dual write, marker 뒤 V2 one tx; SEPARATE FROZEN all-serving→marker→CANONICAL 뒤 V2 one tx; same-key1, PC/mobile | marker 전 canonical read/enable·Order meta runtime write·topology 바뀐 artifact 소비 금지 |
| WDC-LINK-CLEANUP-01 | primary-DB cleanup audit/LEGACY_CLEANUP run, marker/deploy/static guard | V2 checkpoint+marker+canonical effective 확인, separate encrypted artifact/run/checkpoint로 Order meta와 later V1 retirement만 batch verify; old generation nonzero | V2 DB 변경·V2 artifact/run 재사용·marker/state 전 cleanup·ambiguous 제거 금지 |
| ERP-ESTIMATE-01 | `foms/api/erp_estimates.py`, OrderEstimate service/client | parent scope, CS/SALES/Admin policy, create/update/draft-delete/issued-cancel, Order If-Match/receipt/version/event; VIEWER/cross-order/stale 불변 | WDC estimate와 혼합·issued hard-delete 금지 |
| CALL-LOG-01 | `orders/call_log.py` — command `CALL_LOGGED`(actor=`STAFF/CS`·`STAFF/SALES` 또는 ADMIN/MANAGER, policy_id, cookie-auth라 write_guard 필수) call append+optional measurement date | exact schema, policy, version/receipt/event one tx; `sd.calls` append 1, main/logistics/hold/AS/delete axes 불변(orthogonal write); same-key call 1 | generic structured PUT·quest/main-stage 변경 금지 |
| EVENT-REVERT-01 | `events.py` generic revert route/control | arbitrary target route/control symbol 0, direct POST 404; 필요한 undo는 registered typed compensation만 | JSON-path/name-based revert 복구 금지 |
| STATE-MODEL-00 | status constants/read models, `audit_order_state_axes.py` | main/logistics/hold/AS/delete/construction axes와 production run/quest/drawing revision registry target, legacy alias path와 projection fixture; ambiguous report | data mutation/자동 repair 금지 |
| STATE-AXES-REPAIR-00 | `repair_order_state_axes.py`, state manual CSV verifier | dry-run/apply/verify, `LEGACY_ALIAS` 포함, coverage 100%, ambiguous 승인 전 enforcement 0 | command endpoint 변경 금지 |
| PRODUCTION-BACKFILL-00 | production run schema, `audit_production_runs.py`, `backfill_production_runs.py` | flat steps/defects/history를 UUID run으로 보존; in-flight PRODUCTION current IN_PROGRESS 100%; ambiguous manual CSV | command flag ON·flat history 삭제 금지 |
| QUEST-BACKFILL-00 | `audit_order_quests.py`, `backfill_order_quests.py` | RECEIVED/MEASURE/CONFIRM/PRODUCTION/CONSTRUCTION/CS current quest 단일성, dynamic required team, 기존 approval 보존, coverage 100% | GET/approve lazy create 복구·모호 approval 자동 선택 금지 |
| AS-BACKFILL-00 | AS cycle schema, `audit_as_cycles.py`, `backfill_as_cycles.py` | status/history/as_info의 cycle/transition/schedule/completion/classification safe map; current cycle 0/1, ambiguous manual CSV, coverage 100% | inferred stage rewrite·ambiguous cycle auto-select 금지 |
| STATE-CORE-00 | `order_transition_service.py`, command registry, side-effect fixtures | row lock, receipt, expected-from, actual-before, legacy event parity, tx내 outbox | endpoint 이관 없음; worker/schema 재구현·Channel outbox 재사용 금지 |
| STATE-PROD-01 | production start/complete | CONFIRM→PRODUCTION→CONSTRUCTION, production quest gate, team-wide, same-key replay | 5-step hard gate·기존 `erp_edit_required` 복구 금지 |
| STATE-PROD-ACTIONS-01 | production step/defect/change-ack routes+clients | step/defect는 Order version+event; production ACK는 Order 불변, receipt+event only, same token event 0; hold는 overlay service | start/complete/hold·drawing ack 혼합 금지 |
| CONSTRUCTION-BACKFILL-00 | attempt schema migration, `audit_construction_attempts.py`, `backfill_construction_attempts.py` | attempts history/current ID, exact evidence audit, dry-run/apply/verify 100%; ambiguous manual CSV | command flag ON·direct COMPLETED 추론 금지 |
| STATE-CONST-CS-01 | construction attempt/evidence/complete/rework, CS complete | 새 UUID attempts, old evidence 격리, IN_PROGRESS→READY→CS, CS quest+AS gate→COMPLETED; rework/new attempt | direct CONSTRUCTION→COMPLETED·generic upload count·rework override 금지 |
| STATE-DRAWING-01 | drawing claim/transfer/receipt/customer-confirm/revision return+check+cancel, drawing change ack canonical endpoints | explicit assignment; source adapter 조립 한 tx/version/event; request checklist before retransfer, exact origin/quest restore, transfer cancel/outbox, ack token idempotency, legacy parity | WIZ/upload source 재구현·production ACK 혼합·team-only write 금지 |
| DRAWING-REVISION-BACKFILL-00 | drawing revision/request/receipt/customer-confirm registry schema, audit/backfill tools | transfer history+attachments+request/check+receipt events를 UUID revision/request로 safe map; current/request/receipt/customer IDs; missing/duplicate open request 0, ambiguous manual CSV, coverage 100% | timestamp/file 추정으로 production gate ON·attachment 삭제 금지 |
| STATE-AS-01 | AS create/register/schedule/unschedule/start/complete/reopen/classification, `field_update` AS fields 이관 | immutable cycle core+append transition history, optional visit time/date clear, current cycle projection, CREATE draft finalize, classification main/lifecycle 불변 | generic controls 제거는 STATE-CONTROLS, AS main stage 복구·classification implicit toggle 금지 |
| STATE-QUEST-01 | quest transition/orchestration | RECEIVED/MEASURE final approval 전이; CUSTOMER_CONFIRM이 CONFIRM quest를 한 tx 완료; 나머지는 prerequisite only | HTTP route 호출/request monkeypatch·standalone DRAWING/CONFIRM stage advance 금지 |
| DATA-01 | `structured_form_projection.py`, JSON schema, structured API+client | exact outer envelope/path/item schema, raw/schema/confidence 보존, clear intent, server pricing/totals, stale tab, PG race | partial allowlist·client provenance overwrite 금지 |
| DATA-MEASUREMENT-01 | measurement routes+`erp_map.py`+`regional.py`+`order_geocode.py` | address/manager/phone projection+geocode outbox; regional 6-bool/memo; address-learning child policy/rate/audit; version/receipt/event and unrelated path invariant | generic field update·all-STAFF writer·postcommit geocode fallback 금지 |
| SHIPMENT-WRITER-01 | per-order shipment settings + AS recommendation apply/cancel | exact non-assignment shipment schema/color enum; crew IDs via command; recommendation locks exact current AS cycle and calls schedule/typed cancel+crew replace, version/receipt/events one tx | global reference master·name-array/auth assignment/AS info direct write·force blind overwrite 금지 |
| ORDER-CREATE-01 | canonical Order constructor, legacy `/add`/JSON create adapters | STAFF CS/SALES self default, Admin/Manager explicit active SALES owner, item IDs+RECEIVED quest+version1+assignment+event+geocode outbox one tx | raw `Order(...)` endpoint constructor·admin owner·other STAFF create 금지 |
| ORDER-COPY-01 | API+legacy bulk copy and `order_copy.py` | explicit form allowlist, server-owned reset, fresh item IDs/owner/quest/version, sorted batch all-or-none, same-key IDs, geocode outbox | column/blob clone·partial commit·attachment/schedule copy 금지 |
| ORDER-IMPORT-01 | admin Excel import/template, `order_import_artifacts` migration+outbox source/scan provider, error download | Admin/Manager, strict 10MiB/1000-row schema, explicit owner, full validate, constructor batch all-or-none/file-hash receipt+resources[]; private source/error artifact 24h, scan ready precondition, ORDER_IMPORT_ARTIFACT delete+heartbeat | local/public temp path·server-owned columns·row commit·raw Order constructor·별도 cleanup scheduler 금지 |
| CHANNEL-INBOUND-ORDER-01 | recovery key state/rotation+rewrap, receipt-specific recovery/retention/create-state CLIs, dedicated worker/heartbeat/readiness/service | cutoff가 receipt PAUSED_ACCEPTED+job PAUSED; max10→RECOVERY_REQUIRED; key rotation old-reference0 전 제거0; 7d/24h/6h alerts, approved CREATE/IGNORE/legal hold, deadline RETENTION_EXPIRED visible incident; exact conservation; owner absence pause; day0→rotate/crash→day29 create1; SALES 1280/390/1024 duplicate0 | accepted silent clear/DEAD·unapproved indefinite retention·plaintext·default Admin·global flag 우회 worker·two commit 금지 |
| STATE-FORM-01 | structured stage selector/client | stage body 제거, command API 사용, `_handle_stage_transition` 제거 | DATA-01+STATE-CORE-00 선행 |
| STATE-OVERLAY-01 | active logistics/hold writers와 production/tablet hold controls | role-gated HOLD_ORDER/logistics command, audit outcome same tx, replay 1; unauthorized/wrong-stage 실패 DB0, main 불변 | orphan swipe route 복구·direct commit·generic controls·delete/AS 혼합 금지 |
| DRAFT-LIFECYCLE-01 | `erp_order_draft.py` create/finalize/discard/delete | create idempotency, finalize one tx, discard child cleanup/outbox, hard-delete scope test | finalized Order delete/status와 혼합 금지 |
| STORAGE-WRITER-01 | storage dashboard + generic field adapters | cabinet enum Production/Shipment policy, shipping fee finance policy/integer, If-Match/receipt/version/event, desktop persona | main/logistics/settlement 변경·generic field coercion 금지 |
| STATE-LEGACY-01 | web order edit, generic status/field, admin override legacy writers | 정상 mutation은 canonical command/projection, emergency override만 reason+event; direct stage assignment 0 | 새 generic stage endpoint 금지 |
| STATE-CONTROLS-01 | measurement/order/listing status selectors와 command controls; orphan queue swipe route/macro/JS | generic `COMPLETED/AS_*/DELETED` option 0, role+predicate 전용 controls; old queue macro include 0 재확인 후 `/api/foms/queue/*`+mock/direct writer+global swipe load 0 | dead swipe UI 부활·DELETE/AS/overlay backend 의미 변경 금지 |
| STATE-GUARD-01 | 모든 status/field/override/edit/listing/draft/delete/direct-writer static guard | canonical helpers, constructor initial stage, audited backfill 외 main/overlay assignment 0 | 선행 writer 하나라도 남으면 merge 금지 |
| WIZ-01 | wizard state/asset/import/sheet export/pending child rows | route registry 100%; projection+Order version for state mutators, child ETag for pending, server key/order scope, pending 보존 | transfer/final revision/event·upload ticket 혼합 금지 |
| WIZ-PRESET-01 | wizard global preset routes/SystemSetting | DRAWING/Admin policy, schema, settings version/idempotency/SecurityLog | Order mutation·silent global overwrite 금지 |
| WIZ-TRANSFER-01 | drawing transfer source helpers | pending snapshot/attachment materialization을 `commit=False`로 반환, DB commit/version/event/outbox 0 | endpoint/transaction/event 소유 금지; STATE-DRAWING이 조립 |
| WIZ-DELETE-01 | pending delete business command | child row DELETE_PENDING+SIDEFX `STORAGE_DELETE` insert 한 tx; 공용 worker가 child만 DELETED, Order JSON/version/event 0; retry/cleanup | 별도 delete worker·worker의 Order write·synchronous external delete 금지 |
| UPLOAD-01 | direct/multipart order upload auth+server key | VIEWER 403, purpose matrix, arbitrary folder 0 | prefix-only로 종료 금지 |
| FILE-LEGACY-AUDIT-00 | legacy attachment/key read-only audit tool | exact row/order/purpose/key mapping CSV, ambiguous quarantine CSV, mutation 0 | 추정 backfill·delete 금지 |
| FILE-LEGACY-BACKFILL-01 | audited legacy attachment ownership backfill | safe rows만 dry-run/apply/verify, ambiguous 수동 CSV+reason, coverage 100% | ambiguous 자동 매핑 금지 |
| FILE-01 | presign/view/download routes | attachment row+order read scope, raw key 직접 요청 거부, legacy coverage gate | upload PR과 분리 |
| UPLOAD-INTENT-01 | drawing revision/AS cycle DRAFT model+idempotent create/cancel | 파일 전 DRAFT ID 발급, 24h, queue 비노출, cancel marks terminal; final command만 Order version 1회 bump | scheduler/object cleanup·ticket/storage 변경 금지 |
| UPLOAD-02 | ticket model/service/order consumers, `upload_cleanup.py` bounded scan provider | 900s, per-file ticket, issue+complete auth/resource/item active 재검사, tamper/expiry/type/size, retry idempotent; SIDEFX worker가 provider를 300s마다 호출해 expired ticket/draft claim+`STORAGE_DELETE`, item-retire PG race, scan heartbeat/lag | 별도 scheduler/cleanup loop 금지; ITEM-ID-00+FILE-01+UPLOAD-INTENT-01+worker 선행; safe rollback direct OFF |
| BLUEPRINT-01 | legacy blueprint route/scalar migration + typed replace/delete client | `ORDER_BLUEPRINT` ticket attachment, exact order policy, current projection version/event, delete outbox; legacy URL safe backfill 100% | login-only/substr key/scalar direct write·ambiguous URL auto-map 금지 |
| UPLOAD-CHAT-01 | chat upload session/complete | room membership ticket, order namespace와 분리 | order ticket 재사용 금지 |
| CHAT-FILE-01 | ChatAttachment row/read routes, legacy chat-key audit/backfill | attachment ID→message→room active membership, raw key route 0, short-TTL signed redirect, outsider/removed member 404, legacy coverage 100% | login-only raw key presign·Order FILE namespace 혼합 금지 |
| SHELL-01 | `erp-shell.js` | A→B rapid nav에서 A commit 0; AbortController+generation | history init 혼합 금지 |
| HISTORY-01 | 두 history mobile JS | direct load+fragment swap 모두 1회 bind, focus expand | shared shell 변경 금지 |
| ROUTE-01 | `measurement_route.py`, map API/strip/map JS | scheduled hero와 next 일치; optimized 별도 label·sequence | DB stage 수정 금지 |
| SW-01 | `static/sw.js`, offline API headers, logout/session messaging | PII API CacheStorage 0, subject change purge, cold miss ≤5s | offline mutation은 계속 OFF |
| OFFLINE-01 | exact historical `/static/sw.js` update, real legacy row inventory, dual-approved local recovery, versioned encrypted export/viewer, blocked-IDB support shell, nonce proof/protocol gate | every historical exact URL→A0; current subjectless-v1은 order identity+current scope+password+other Admin approval만 local manual/export; unknown/cross/unsafe value0; PBKDF2/AES envelope roundtrip; versionchange close→Retry→purge/A1, permanent fault clean-profile DISABLED+bytes preserve; **완료 정의=phase A(A0/A1)+all-serving generation까지** (phase B marker는 §8.2 OFFLINE_SW cutover 운영단계로 REV-99·all-serving 후 RELEASE-GATE-00 뒤 실행, OFFLINE-01 완료 밖) | query URL 가정·silent loss/replay·unapproved subjectless/cross render·blocked 영구 무안내·A0 전 protocol2·queued-writer rollback 금지 |
| STARTUP-SCHEMA-01 | runtime ensure helpers→Alembic/`predeploy.sh` | fail-closed schema, web replica start DDL 0 | additive migration downgrade 금지 |
| STARTUP-BACKFILL-01 | `audit_erp_flat_columns.py`, `backfill_erp_flat_columns.py`, common encrypted artifact/run/checkpoint protocol | protected-root audit→phase `STARTUP_FLAT` dry-run/apply, batch500, DB checkpoint resume, operation-bound approval, before/after verify, progress/nonzero | bare `--apply`·repo/profile plaintext artifact·startup fallback 금지 |
| STARTUP-ADMIN-01 | `tools/ops/bootstrap_admin.py` | explicit only, password output 0, existing admin idempotent | auto bootstrap 금지 |
| STARTUP-PURE-01 | `app.py`, `app_init.py`, `run.py`, app factory | import write/DDL 0; date listener 유지; dev fail-closed | zero-pending 뒤, auto-init 복구 금지 |
| SCALE-AS-01 | AS query/index migration | production-like EXPLAIN+TTFB 개선. 효과 없으면 무변경 종료 | 측정 전 index 금지 |
| SCALE-CHANNEL-01 | Channel receipt/intent/job production index·capacity·load artifact | prior7-day valid ingress의 5분 peak(없으면 STOP); `max(1 job/s,2×peak)` 15분 N-worker, p95 receipt→DONE≤10s, oldest PENDING≤60s, 종료60s backlog0, expired lease/RECOVERY_REQUIRED/duplicate Order0, heartbeat≤15s, EXPLAIN index hit; PII0 artifact | window/rate 축소·lease/state/max-attempt·auth/provider/constructor 변경 금지 |
| SCALE-SKETCHUP-01 | parse job claim/reclaim | expired running reclaim, max attempts terminal | designer 기능 변경 금지 |
| BACKUP-01 | deprecated backup service | 호출처 0 확인 후 제거; 운영 restore runbook 존재 | password subprocess 복구 금지 |
| PROXY-01 | `foms/platform/app_factory.py`의 `ProxyFix`/trusted-proxy 설정과 `foms/services/rate_limit.py`의 limiter key-func(XFF 소비 지점) | trusted proxy hop 수만큼만 XFF 신뢰, 그 밖 XFF는 무시; canonical client IP만 rate/limit key로; spoof test | rollback=직전 proxy/XFF 설정으로 config revert(취약한 XFF-as-key 재활성화 금지); Railway proxy chain hop 수를 실측/확인하기 전 merge 금지 |
| RUM-INGEST-01 | `foms_rum.py`, client contract, rate config/report | anonymous POST max 2KiB exact keys; metric `LCP|INP|LOAD|SWAP`, finite value 0..120000, relative path≤500 no query/fragment, viewport `WxH` 1..10000, bool; 120/min trusted client, Redis error warning/no raw payload; admin report JSON 401/403, days 1..35 | raw payload/PII log·silent except·untrusted XFF rate·unbounded days 금지 |
| WAM-TELEMETRY-01 | WAM telemetry route/service/client, scoped limiter/test | scope token 선검사; raw body≤2KiB before JSON; exact canonical keys `event_name,view_key,page_state,section_count,attachment_count,latency_ms,key`; existing 7-event enum, strings≤64, counts 0..1000, latency int 0..120000; token+order and trusted-IP 각 120/min; valid 204, invalid 413/422, limit 429 | unknown/raw/nested payload log·alias 무기한 허용·untrusted XFF·telemetry failure로 page failure 금지 |
| INDEX-OPS-01 | 운영 catalog/constraint/EXPLAIN | exact duplicate만 제거, rollback DDL 준비 | local DB 결과만으로 실행 금지 |

---

## 6. Persona acceptance — 버튼 존재가 아니라 실제 업무 완료

### 6.1 최소 계정 세트

`ADMIN primary`, `ADMIN secondary`, `MANAGER`, `STAFF/SALES owner`, `STAFF/SALES non-owner`, `STAFF/CS`, `STAFF/MEASURE(legacy team)`, `STAFF/DRAWING assigned`, `STAFF/DRAWING unassigned`, `STAFF/PRODUCTION`, `STAFF/CONSTRUCTION assigned`, `STAFF/CONSTRUCTION unassigned`, `STAFF/SHIPMENT`, `VIEWER/no-team`, `VIEWER/CS`, `inactive target user`, `legacy-password target user`를 별도 세션/fixture로 만든다. `STAFF/MEASURE`는 §2.1 (a) 분기(active MEASURE 계정 존재)에서 SALES 정규화로 실측 요청/완료 흐름이 실제로 도는지 검증하고, (b) 분기(active MEASURE 0)면 이 fixture를 만들지 않는다(preflight가 확대 불필요를 확정). 두 ADMIN은 last-active-admin 동시성/승인과 actor session 보존을, target users는 reset/deactivate/revoke를 검증한다. 같은 브라우저의 role switch로 대체하지 않고 쿠키 jar와 actor ID를 분리한다.

고정 device 계약:

| surface | viewport·input | 필수 runtime evidence |
|---|---|---|
| desktop | 1280×800, pointer fine | `innerWidth/innerHeight`, `matchMedia('(pointer:fine)')`, feature flags |
| mobile | 390×844 portrait, touch/coarse | orientation, `maxTouchPoints>0`, `matchMedia('(pointer:coarse)')`, mobile flags |
| tablet order edit portrait | 1024×1366 portrait, touch/coarse | shared mobile predicate true, form 1개, fixed header/secnav/action/bottom-nav 비중첩, 모든 section chip click target이 secnav 아래 |
| tablet order edit landscape | 1366×1024 landscape, touch/coarse | desktop predicate/form 1개; portrait와 양방향 회전 시 pristine reload 또는 dirty cohort lock 계약 |
| tablet production | 1024×768 landscape, touch/coarse | `innerWidth>=992`, landscape, coarse pointer, tablet-production flag와 kanban media query 모두 true |

`79c2d9a2`의 실제 mutation 클릭 증거는 desktop VIEWER 정산이 200으로 성공, mobile PRODUCTION 완료가 403 후 명확한 오류가 없음, mobile CONSTRUCTION 완료가 CS를 건너뛰고 COMPLETED가 된 것까지이며 해당 writer는 current `2b86c689`까지 diff 0이다. current SHA에서는 390×844 order-edit secnav 실제 click/geometry를 다시 확인했다. 768×1024 관찰은 tablet 증거가 아니다. 1024×1366 coarse portrait는 source predicate mismatch가 확정됐고, 1024×768 landscape와 함께 수정 후 실제-device release 증적이 필요하다.

### 6.2 acceptance matrix

| Persona | 실제 사용자 시나리오 | network 기대 | DB·감사 기대 |
|---|---|---|---|
| SALES/CS desktop | 탭 A payment confirm/settlement, 탭 B 일반 필드 저장 | stale B `409 REVISION_CONFLICT`; reload 후 save 200 | payment/settlement/calls/wizard 불변; form path만 변경 |
| SALES/CS route | 시간 다른 3건에서 기본/추천 전환 | scheduled와 optimized 각각 200, 명시 sequence | hero next=scheduled[0] |
| ASSIGNMENT PC/mobile | STAFF CS/SALES self-owner create, Admin explicit owner create, DRAWING self-claim/team+batch replace/release, CS/SALES가 app CONSTRUCTION user replace; SHIPMENT가 worker CRUD와 external crew 0..20 replace | 허용 2xx; Admin owner 누락·invalid target 422; unassigned DRAWING은 claim/team replace만 허용하고 wizard/transfer/check/ack는 403; unassigned CONSTRUCTION command 403; stale/batch 한 건 오류 전체 409 | auth assignment와 crew set 분리, source/release history, batch all-or-none, empty crew release, in-use worker deactivate 409, 거부 version/event 0 |
| DRAWING desktop assigned | desktop wizard save→sheet PNG→pending→일반 save→refresh | 2xx; stale version 409 | save 직후 pending/object 1, attachment/event 0; wizard와 pending 보존 |
| DRAWING mobile assigned/unassigned | pending/upload draft→transfer; drawing change ack; SALES receipt; 일반 주문(required SALES)은 SALES owner, 라홈 dynamic 주문(required CS)은 STAFF/CS가 customer confirm; revision return→check→retransfer, request/transfer cancel | assigned/정확 team 2xx; SALES가 CS quest 또는 CS가 SALES quest confirm은403; unchecked retransfer·stale revision/request/token409; unassigned wizard/transfer/check/ack403 | 두 seed 모두 CONFIRM→production→construction→CS→COMPLETED 완주; receipt actor/SALES assignment 보존, confirmation은 actual required-team actor; request/quest origin exact, 취소/재전달 이력 보존 |
| PRODUCTION desktop/tablet/mobile | CONFIRM start→PRODUCTION complete; same-key transport retry; 새 key 재클릭; quest/confirmation/wrong-stage bypass | 정상 200/200; same key replay 200; 새 key·bypass 409 | CONFIRM→PRODUCTION→CONSTRUCTION, actual-before event 각 1, 5-step은 hard gate 아님 |
| PRODUCTION actions | step check, defect report, change ack, hold/release | 허용 2xx; invalid token/reason 409/422 | subcommand event/version exact; ack same token event 0; hold는 main 불변 |
| CONSTRUCTION mobile | assigned start→ticket upload after 2+signature 1→각 evidence register→current construction quest approve→complete; stale attempt/wrong kind/unassigned | start/upload/register/quest/complete 2xx; 미충족·mismatch 409; unassigned 403 | attempt IN_PROGRESS→READY→COMPLETED, attachment 3/evidence event 3, quest exact, main target CS, 거부 불변 |
| CS desktop | CS quest 완료 후 CS complete; AS active 중 시도 | 정상 200; quest 미완료/AS active 409; non-CS STAFF 403 | CS→COMPLETED event 1; 거부 main/version/event 0 |
| SHIPMENT PC/mobile | packing 1회, logistics 갱신, crew picker, AS recommendation apply/cancel; assigned app construction packing | 허용 2xx; VIEWER/unassigned construction 403; 후속 수동 일정 뒤 cancel 409 | packing 중복 0, external crew projection, auth assignment 불변, typed AS schedule/compensation, CS/SALES 기능 보존 |
| FINANCE SALES/CS | payment confirm, settlement, cash receipt 발행; same-key retry; 새 key 재발행 | 정상 2xx; replay 200 same body; 두 번째 새 key 409; VIEWER 403 | amount/receipt/event 각 1, 거부 DB/version/event/log 0 |
| AS CS/SALES | CREATE_AS_ORDER 또는 기존 주문 REGISTER→date-only SCHEDULE→UNSCHEDULE→time optional SCHEDULE→START→COMPLETE→REOPEN; 미결/AS도면/영업·택배 classification 토글; 완료 뒤 새 REGISTER | 각 단계 2xx; wrong cycle/stage 409; PC/mobile blank date는 UNSCHEDULE | main 불변(신규 AS order는 CS), classification과 lifecycle 독립, same cycle reopen, 새 register만 new cycle, 과거 보존, 단계별 event/version 1 |
| AS assigned CONSTRUCTION | AS child draft/evidence upload→REGISTER; schedule/start/complete 직접 POST | register/evidence 2xx; lifecycle processing 403; unassigned 403 | 새 cycle/evidence 1, 403에서 cycle/main/version/event 불변 |
| DRAFT/COPY SALES/CS/Admin | 신규 draft create/autosave/finalize, Admin explicit owner, allowlist single/bulk copy, AS draft cancel, expired cleanup | create는 If-Match 없이 idempotent 2xx, Admin owner 누락 422, copy stale 한 건 전체 409 | initial owner+version1+fresh quest/item IDs, copied server-owned/attachment/schedule 0, geocode outbox, discard child/outbox 1 |
| ITEM SALES/CS | item add/save/upload/reorder; attachment item 제거 1차 실패→MOVE_TO_COMMON 재요청 | invalid/duplicate 422, attachment 있음 409 details, 명시 disposition 후 200 | item_id reorder 불변, attachment common 이동, removed schedule 삭제/rebuild, cross-order link 0 |
| VIEWER/no-team + VIEWER/CS | dashboard/detail/history/search/attachment 조회 후 Order/business mutation inventory; 자기 notification read/archive/urgent ack, push subscription, member chat send/read | business GET 200·control 0·mutation 403; ancillary own 2xx; 타 사용자/비회원 403/404 | Order/JSONB/version/event/attachment/WDC 변화 0; own child row만 1회 변경 |
| ADMIN/MANAGER override | 비인접 emergency override | reason 없음 400, reason 있음 200 | original actor, from/to, reason, source application append-only event |
| ADMIN/MANAGER ops | migration, bulk delete, switch-user/back, Excel download | migration 404; delete GET 405·POST+CSRF 200; switch POST; Excel role matrix | delete/event 1, impersonation 원사용자·대상·복귀 audit; VIEWER/STAFF 불변 |
| ADMIN/MANAGER import | valid 2-row workbook, one invalid row workbook, same-file retry, explicit SALES owner | valid 2xx; invalid 422+error report; retry same IDs; missing owner 422 | all-or-none, each fresh item/quest/owner/version, server-owned input 0, temp cleanup scheduled |
| ACCOUNT/Admin | 두 ADMIN+targets; 3-scope N-worker; EMPTY→READY bridge에서 PG outage→legacy login→replica restart/reconnect→all desired same epoch 900초; rotation; 1280/390/1024 login threshold429와 PG503; **공유 NAT 러시**(단일 공인 IP에서 다수 계정 아침 동시 로그인+오타 재시도) | outage/boot gap이면 coverage0; activation 전 PG authority0; 10/60/5 연속; 429 same generic+countdown/retry time, password clear/username local preserve/button enabled/request1; PG503 temporary+request_id/invalid-credential0/session0; **공유 IP 완화(§2.1) 적용 시 정답 첫 시도가 CLIENT_IP 한도로 429되지 않음, 개별 account/account+IP bucket은 불변** | principal trigger/version one tx, active Admin≥1, raw identity/key0, public register404/mutation0 |
| CHANGE HISTORY | 자기 event의 generic `revert` control/API 시도, 이후 typed cancel command | generic control 0·direct POST 404; registered cancel만 2xx | arbitrary JSON path 변화 0; typed compensation event/version 1 |
| WDC | hostile customer/product render, save/master mutation | script 실행 0; role matrix 403/200 | unauthorized WDC row 변화 0 |
| WDC LINK topology | SALES/CS가 ERP detail+WDC match를 1280×800/390×844/1024×768에서 사용; SAME concurrent dual-write/backfill/marker; SEPARATE stale tab click→freeze UI→safe abort 또는 marker/CANONICAL; topology drift | SAME maintenance/banner0·link1 atomic; SEPARATE reload control disabled+reason/ETA, stale click visible `WDC_LINK_MAINTENANCE`, optimistic 변화0/button re-enable/request1; safe abort 뒤 기존 link/control 즉시 동일; CANONICAL 뒤 link/unlink+Channel view 동일 | 각 실패 duplicate/link/meta/event0; V2 shadow marker 전 사용자0, cleanup separate primary phase, marker 뒤 abort0 |
| ERP ESTIMATE | create/update draft delete, issued cancel, cross-order ID | CS/SALES/Admin 2xx; VIEWER/cross-order 403/404; stale 409 | parent Order version/event exact, issued history 보존, 거부 child/Order 불변 |
| ORDER TASK | CS/SALES create/reassign, owner personal-board update, cancel, structured auto-task | 허용 2xx; VIEWER/unrelated/cross-order 403; stale row 409 | child version/event, CANCELLED history, auto unique, Order version 독립, rollback 같이 동작 |
| STORAGE | Production/Shipment cabinet enum, CS/SALES shipping fee | 허용 2xx; wrong team 403; enum/금액 invalid 422 | typed field/version/event 1, main/logistics/settlement 불변 |
| DOMAIN WRITERS | measurement/map address, regional 6 checks/memo, address learning 202, call log, Channel push, topology-aware WDC link, shipment reference/per-order settings/AS recommendation | exact command 2xx/202; stale409, missing If-Match428, VIEWER403; retry same | each write/event/version1; WDC SAME atomic/SEPARATE V2-only; learning ACTIVE after worker; unrelated state 불변 |
| BLUEPRINT | purpose ticket complete→typed replace→delete | authorized 2xx; VIEWER/wrong order/key 403/409 | unclaimed attachment then Order projection event 1; delete outbox 1; legacy scalar direct write 0 |
| ITEM/UPLOAD RACE | item ticket issue→다른 탭 item retire와 complete 동시 | 한쪽 2xx, loser `409 ITEM_RETIRED`; deadlock 0 | retired item attachment 0, ticket rejected, orphan cleanup 1 |
| DESIGNER retire (삭제 확인) | `/wdplanner-v2`·designer route/nav·정적자산 접근, blueprint 등록 확인 | 모든 designer route/nav GET·POST 404; nav 링크·UI 진입점 0; `APP_OK` 회귀 0 | designer_* 테이블/데이터 무변경(코드/UI만 제거) |
| SHIPMENT settings | worker create/update/deactivate, global reference list save, empty order crew | SHIPMENT/Admin 2xx; duplicate/in-use/stale 409; other STAFF 403 | worker/assignment history, SystemSetting version/audit, construction worker free-name key 0 |
| CHAT member/outsider | room create+member add, text+attachment send, raw-key read, socket join/typing/send, member removal/reconnect | member 2xx/receive 1; outsider/raw key 404; removed receive 0; VIEWER room admin 403 | room/message/attachment one tx, recipient message_id 1, duplicate membership/message 0, close history |
| URGENT CALL participant | PC+390px target→send→recipient ack; retry/rate/cross-order | send/ack 2xx; replay same; 6th 429; cross-order 403 | notification/state/event+NOTIFICATION_EVENT domain side-effect row 한 tx 각 1, Order version 0, ack event ACTOR-STATE 1 |
| FIELD MOBILE | packing submit, history fragment, rapid nav | POST 1/GET 0; handler 1회; stale response commit 0 | 중복 packing/event 0 |
| MEASUREMENT desktop/mobile | map/self/regional status control에서 완료·AS·삭제 시도 | generic `COMPLETED/AS_*/DELETED` option 0; 허용 role에만 명시 command 표시 | logistics command는 main/AS/delete axes 불변, 거부 mutation 0 |
| PUSH | nested payload notification 클릭 | same-origin deep-link로 1회 이동 | opened event 1 |
| MOBILE NOTIFICATION | 로그인/비로그인으로 mobile-state와 badge 호출 | 로그인 JSON 200, 비로그인 JSON 401, redirect 0, parse error 0 | 조회 요청이 DB를 바꾸지 않음 |
| ERROR UX | 403/409/428/500, malformed JSON, fetch reject, timeout, double click | visible error, reload 0, request 1, 실패 뒤 button enabled | DOM stage 이동 0, DB/event 변화 0 |
| ERROR/OPS outsider | malformed DB/storage fault; `/debug-db`/public Channel/internal path; anon·VIEWER·STAFF·MANAGER admin detail; no/invalid bearer와 public-network machine request; ADMIN logout→Back, bearer A→B→A 폐기 cache 재요청 | unexpected 500 generic+request_id; public/internal detail 404, non-Admin 403/404; ADMIN detail과 private-DNS+valid-token machine만 200; Back/폐기 token은 이전 body 0 | Admin private/no-store/Vary Cookie, machine no-store/Vary Authorization, ETag/Last-Modified 0; response 차등/metric leak 0, response/SecurityLog/client telemetry secret/path/SQL/schema/traceback 0, protected server request_id+stack log 1, mutation 0 |
| REQUEST LIMIT outsider | public JSON/WAM/RUM/Excel/legacy multipart에 body·file·aggregate cap+1, no-length chunk, 거짓 part length, 정상/초과 boundary, parts1001, encoded body | 정상 cap 유지; 초과 pre-handler413 code exact, encoded415; Excel +64KiB/legacy +256KiB overhead 정상 | streamed byte counter authoritative, handler/DB0, 열린 partial tempfile 전부 close/unlink/path log0 |
| BACKFILL resume/operator | unsafe root/DPAPI wrong account/host/plaintext; 2-batch batch1 뒤 crash/lease expiry; `inspect_backfill_run`; completed rollback/pending drift/checkpoint tamper; Admin principal change/reauthorize race | unsafe면 audit0; status RUNNING→expired→RESUME, PAUSED_APPROVAL→REAUTHORIZE, drift→STOPPED_DRIFT/REAUDIT; completed=after+pending=before만 batch2; append seq/CAS 한 건 | versioned AES envelope/AAD+mapping JCS hash, batch+checkpoint+counter same tx, raw lease/key0, DONE은 verify100%, key destruction |
| CUTOVER live replicas | 두 serving replica를 marker 전 연결해 legacy mutation 후 family mark; 한 replica generation 미달/state-unaware, marker DB outage, 이미 실행 중 replica 재요청 | all-serving artifact 미달이면 mark nonzero; valid mark 뒤 재시작 없이 두 replica next request가 post-cutover mode/legacy0; DB fault503; generation 미달 startup/readiness nonzero | marker row1 immutable, old writer/side-effect0, SHA는 provenance만, request-scoped DB read perf budget green |
| SIGNING STATE expand/operator | old runtime 중 additive deploy/EMPTY; Flask/WAM legacy fingerprint audit, safe BRIDGE와 known/default FORCE_REAUTH prepare, bad SHA/version/artifact·race; rotation prepare | old runtime 무변화; valid prepare만 READY/ROTATION_READY, deadline null; invalid/race mutation0 | key/env/token 발급/ACTIVE0, value log0, manifest SHA exact |
| SIGNING bridge/activation/WAM replay | safe BRIDGE; known/default는 FORCE rescue predeploy→세 viewport AUTH_ONLY→replica quiescence30s→activate; current smoke success/forced failure; same rescue retry→CONSUMER fixed descendant 또는 KEY fresh NEXT emergency; old WAM/session; ACTIVE compromise/normal rotation/N-worker | maintenance PII-free/no-store; counters0; current smoke 전 OFF0; old artifact는 `WAM_LINK_EXPIRED`+login/new-link/safe return; failure branch 끝에 new login/WAM green; 5/10분 incident, replay1, DB503 issuance0 | exact vectors/state, secret0, diagnosis artifact, only state-aware roll-forward, 무기한 무경고 maintenance0 |
| STORED XSS editor/Admin | preseed hostile SecurityLog row+신규 hostile login; hostile option/product/spec; self hostile name과 Admin/legacy-seeded hostile team; hostile change-event customer 후 Admin·다른 authorized persona가 order list/detail, drawing 4 surfaces, change history를 열기 (Designer sink는 DESIGNER-RETIRE-01 삭제로 제외) | 신규 login은 generic message+keyed identity hash만 저장하고 raw username 0; 모든 page 200, order link·multiline·picker/change card 정상 | script/dialog/navigation/network 0; inline onclick/untrusted innerHTML 0; 기존 rows/order/name은 삭제 없이 escaped text로 보존; user ID는 integer allowlist |
| CHANNEL quick-action domain | active mapped User로 canonical read-scope 허용 Order summary/schedule/manager 조회; mapped VIEWER/STAFF의 policy-denied Order, nonexistent Order, missing/unmapped/inactive manager, DB fault | allowed는 method별 exact allowlisted bounded domain data; 모든 deny는 존재 여부를 구분하지 않는 동일 no-data domain result | allowed만 schema field; deny/nonexistent/mapping/DB fault PII0, SecurityLog/raw exception0, Order/child/audit mutation0; HTTP mapping은 Function packet만 소유 |
| CHANNEL Function provider | provider console disabled 뒤 flag false 및 provider가 아직 호출 중인 잘못된 false 전환; enabled에서 redacted live registered method fixture의 exact raw bytes를 official hex key로 sign해 authorized summary/schedule/manager PUT; POST, bad/missing signature, malformed JSON; signed wrong channel/unknown method/schema/missing mapping/policy-denied/nonexistent Order | disabled route404/provider error0; provider 호출 중 false는 preflight STOP; enabled success200 `{result}`와 exact allowlisted fields, POST405, signature401, malformed400; signed domain deny 동일200 `{error:{type,message}}` | stale fixture 소비0; channel/caller/schema exact; allowed만 schema field, deny/nonexistent/mapping/DB fault PII0; Order mutation0, secret/raw body log0 |
| CHANNEL Webhook intake provider | provider disable/false gate; live group/userChat Message/UserChat/User; token/source/schema/retry/conflict; v1 identity/intent/JCS golden vectors; create-disabled soak | disabled404/unsafe false STOP; enabled status exact; create-enabled CREATE_ACCEPTED receipt+AES-GCM canonical-input ciphertext+ID-only job same tx 뒤만2xx, disabled masked receipt only | packet Order0; hash stable across signing rotation/restart, delimiter collision0, plaintext/raw/token/PII log0, accepted conservation |
| CHANNEL inbound worker | service/key/lease; day0 accepted→day10 key ROTATION_READY/activate/rewrap crash-resume→day29; disable mid-processing; owner/max10/decrypt fault; 7d/24h/6h alerts; global false에서 receipt-specific CREATE/IGNORE; day30 no-hold, approved7d hold, terminal cases | pause는 receipt PAUSED_ACCEPTED+job PAUSED; old ref0 전 key 제거0; day29 CREATE→Order1/input clear; IGNORE reason; day30 no-hold→RETENTION_EXPIRED+incident/Order0, hold는 new deadline; conservation exact | SALES 1280/390/1024 duplicate0; web/SIDEFX/general worker bypass0; default Admin0; provider-first false |
| WAM link telemetry | valid scoped link로 정상 event, 2KiB 초과, unknown/nested/type/길이, 121회 burst, 다른 order/token | valid 204; oversize 413; invalid 422; limit 429; wrong scope 403/404 | valid bounded scalar log 1, invalid/raw payload log 0, page/bootstrap 기능 영향 0 |
| ORDER EDIT surface boundary | SALES가 390×844와 1024×1366↔1366×1024 coarse 양방향 회전에서 pristine/dirty, 모든 section chip, keyboard open/close | portrait mobile form 1, landscape desktop form 1; pristine section 보존 reload, dirty current form 유지+banner, save 뒤 새 cohort | header/secnav/action/footer overlap 0, target top≥secnav bottom, horizontal overflow 0, keyboard-only flip 0, form data 손실 0 |
| QUEST BYPASS | generic status/field, URL 직접 POST, 타 team approval로 전용 edge 시도 | `409 STAGE_COMMAND_REQUIRED` 또는 403, visible error | quest/stage/version/event 모두 0 |
| OFFLINE old→new upgrade | 1280/390/1024에서 current `/static/sw.js` old worker와 empty, real subjectless-v1, subject-bound, unknown/cross/oversized, blocked DB fixtures; A0→dual-approved local manual/export→fresh-browser decrypt→purge/nonce/A1; wrong pass/tamper; tabs open→close+Retry; permanent fault | every exact URL update 도달; subjectless는 exact order+current scope+password+other Admin만 value 보임; unknown/cross value0; export roundtrip, tamper generic; blocked close/Retry→A1, permanent fault clean profile+old bytes preserved; B old queue409 | silent loss/replay/server body0, PII server leak0, unavoidable-loss approval 없으면 STOP, all-serving roll-forward |

### 6.3 필수 E2E 인계 script

동일한 seed를 `CONFIRM required_team=SALES` 일반 주문과 dynamic `required_team=CS` 라홈 주문 두 개로 만들어 아래 순서를 actor/click/network/DB snapshot과 함께 끝까지 실행한다. 각 단계는 직전 응답 ETag와 새 UUID key를 사용하고, 성공 뒤 같은 key replay도 한 번 수행한다.

1. `CS`가 required team=CS인 final RECEIVED quest의 `측정 요청`을 승인하여 internal `REQUEST_MEASUREMENT`: RECEIVED→MEASURE. SALES owner 직접 승인은 403 불변이다.
2. current MEASURE quest required team과 일치하는 `SALES owner` 또는 dynamic-rule `CS owner`가 `측정 완료`를 승인하여 internal `COMPLETE_MEASUREMENT`: MEASURE→DRAWING. §2.1 (a) 분기(active MEASURE 계정 존재)면 `STAFF/MEASURE` persona가 SALES 정규화(§2.2.1)로 이 `측정 완료`를 승인하는 단계도 실행하고, (b) 분기면 이 단계를 생략한다.
3. `DRAWING`이 `도면 담당하기`로 `CLAIM_DRAWING`, desktop wizard save/sheet PNG로 pending을 만든다.
4. 같은 DRAWING actor가 mobile/desktop `도면 전달`로 `TRANSFER_DRAWING_REVISION(source=WIZARD_PENDING)`을 실행한다.
5. `SALES owner`가 두 주문 모두 `도면 수령 확인`→`CONFIRM_DRAWING_RECEIPT`를 실행한다. 이어 일반 주문은 같은 explicit SALES owner, 라홈 주문은 active `STAFF/CS`가 `고객 확정`→`CUSTOMER_CONFIRM(current_revision_id)`을 실행한다. SALES→CS quest와 CS→SALES quest 호출은 각각 403/DB 불변이다.
6. revision branch는 SALES owner가 `수정 요청`→`REQUEST_DRAWING_REVISION`, DRAWING이 `SET_DRAWING_REVISION_REQUEST_CHECK(true)` 후 재전달, SALES owner가 다시 수령한다. 고객확정은 일반 seed=SALES owner, 라홈 seed=STAFF/CS로 5번 분기를 반복한다. unchecked 재전달과 신규 전달 뒤 이전 request cancel은 409다. 별도 seed에서 receipt 전 `CANCEL_DRAWING_TRANSFER` 시 final files는 보존되고 previous projection만 복원된다.
7. `CS|SALES|PRODUCTION`이 `제작 시작`→`PRODUCTION_START`, production quest 완료 뒤 `제작 완료`→`PRODUCTION_COMPLETE`를 실행한다.
8. `CS|SALES`가 app actor picker로 `SET_CONSTRUCTION_ASSIGNEES`; `CS|SALES|SHIPMENT`가 crew picker로 `SET_INSTALLATION_CREW`와 logistics를 갱신한다. external crew는 queue를 볼 수 없고 assigned app actor만 다음 command를 실행한다.
9. assigned CONSTRUCTION이 `시공 시작`→`CONSTRUCTION_START`, purpose-bound after 2장/signature 1장을 upload complete 후 각각 `REGISTER_CONSTRUCTION_EVIDENCE`, current construction `quest_id` 승인, `시공 완료`→`CONSTRUCTION_COMPLETE`를 실행한다.
10. `CS`가 CS quest를 완료하고 AS cycle이 NONE/COMPLETED임을 확인한 뒤 `최종 완료`→`CS_COMPLETE`를 실행한다.

rework branch는 별도 seed 또는 step 9 전 snapshot에서 네 reason을 각각 실행한다. target queue 1건, fresh quest/run/attempt reset 표와 confirmation invalidation 표가 정확한지 확인하고 old quest/run/evidence 직접 POST가 모두 409인지 확인한다.

추가로 same-stage handoff 두 지점을 통합 script에 포함한다: (a) RECEIVED 직후 `CS`가 해피콜 결과를 `CALL_LOGGED`로 append(POST 1, `sd.calls` append 1, main/logistics/hold/AS/delete axes 불변, duplicate 0), (b) step 7 생산 완료 직후 `SHIPMENT`가 packing submit(POST 1/GET 0, PACK-01 policy+If-Match+receipt/version 1, shell capture listener 경합 0, duplicate event 0). 둘 다 main-stage를 바꾸지 않는 orthogonal write이므로 이전/다음 queue 노출은 불변이어야 한다.

main-stage 전이에서만 이전 queue 소멸/다음 queue 단 1회 노출을 확인한다. same-stage claim/assignment/transfer/customer-confirm/start/evidence/crew/classification/call-log/packing은 같은 queue의 card state/control만 갱신되고 duplicate card 0이어야 한다. 두 종류 모두 새로고침·fragment swap 뒤 persisted state, registry가 version을 요구하는 command의 event 1/version 단조 증가를 확인한다. customer-confirm stale revision/quest, production quest 미완료, construction evidence·quest 미충족, CS quest/AS gate 미충족의 negative branch는 모두 409와 DB/event 불변을 별도 실행한다.

### 6.4 브라우저 증거 형식

각 시나리오는 다음 6개를 release artifact에 남긴다.

1. persona role/team/assignment와 seed order ID.
2. viewport, 시작 URL, orientation, touch/pointer `matchMedia`, feature flags.
3. 클릭 전·후 screenshot.
4. mutation request URL, method, status, response error code.
5. console error. harness artifact는 별도 표기.
6. 전후 DB snapshot: status/stage/version, 관련 JSON path, event/log/attachment count.

---

## 7. 데이터 사전감사·repair

### 7.1 deploy 전 read-only audit

- `workflow.stage != erp_stage_code`인 **canonical mirror mismatch**와 history.
- 각 canonical axis에서 계산한 expected legacy projection과 `order.status`가 다른 **projection mismatch**. 정상 overlay divergence 자체는 repair 대상이 아니다.
- `order.status`를 main/logistics/hold/AS/delete projection으로 분류했을 때 둘 이상 해석되거나 어느 축에도 매핑되지 않는 **overlay source ambiguity**. `LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE`는 정상 divergence로 별도 집계한다.
- CONSTRUCTION에서 직접 COMPLETED된 최근 건과 CS 후속처리 유무.
- wizard pending 중 exact order prefix 위반·존재하지 않는 object·중복 transfer.
- direct-upload attachment 중 order namespace 불일치.
- legacy chat `file_info`/object key의 message→room→attachment ID safe/ambiguous mapping과 removed-member exposure.
- (Designer owner audit 제거 — FOMS Brain은 DESIGNER-RETIRE-01로 삭제 예정.)
- VIEWER/role-team 비정상 조합과 최근 mutation SecurityLog.
- active `User.team=MEASURE`(legacy pseudo-team) 건수**와 최근 실측 quest 승인 이력** 두 신호. 이 둘로 §2.1 (a)/(b) 분기 판정을 수행한다(단순 count≠0이 곧 SALES capability 확대는 아니며, 계정이 있어도 실측 이력이 없으면 (b)). 어느 분기든 무권한 회귀를 막는다.
- 실제 사무실 network egress(공유 NAT/공인 IP 여부)와 피크 시간대 동시 로그인 인원. 다수가 한 공인 IP를 공유하면 §2.1의 trusted client-IP 60회/15분 bucket이 아침 로그인 러시에 사무실 전체를 429로 잠글 수 있으므로, 공유 IP면 CLIENT_IP bucket을 계정수 기반으로 상향하거나 primary throttle을 `account+IP`로 두는 완화를 §2.1에 반영한다.
- startup backfill pending row 수.
- offline flag와 mutation endpoint 사용량.
- attachment와 `OrderScheduleDate`의 item index→UUID 매핑 가능/모호/범위 밖 건수.
- production run, current quest, AS current cycle/classification, drawing final revision/open request/receipt/customer-confirm link의 safe/ambiguous/missing 건수.
- main CONSTRUCTION 주문의 start history, evidence purpose/attempt/kind, direct COMPLETED 이력으로 attempt backfill 가능/모호 건수.
- side-effect worker service/config-path/heartbeat와 outbox lag/DEAD 수. secret 값은 출력하지 않는다.

### 7.2 repair 원칙

- 자동 stage 역변경 금지. canonical mirror mismatch, projection mismatch, overlay source ambiguity를 분리 보고한다. `workflow.stage`가 단일 history와 일치하는 canonical mirror mismatch만 `erp_stage_code` dry-run mapping을 만들고, projection mismatch는 canonical axes로 재계산할 수 있는 행만 projection을 고친다. 정상 overlay divergence는 수정하지 않는다. canonical 자체가 모호한 건은 ADMIN/MANAGER manual mapping+reason 없이는 수정하지 않는다.
- invalid wizard key는 quarantine하고 삭제하지 않는다.
- upload ticket 도입 전 legacy attachment는 attachment row와 실제 order를 매핑할 수 있을 때만 grandfather read scope를 부여한다.
- `mutation_version` backfill은 모든 기존 주문을 1로 시작한다. deploy 전 열린 stale client는 강제 reload한다.
- P0-3로 VIEWER가 만든 실제 정산이 있는지 운영 SecurityLog/OrderEvent로 식별하되 자동 삭제하지 않는다.

### 7.3 실행 가능한 audit/backfill runbook

모든 도구는 기본 read-only/dry-run, `--apply` 전 mutation0, batch+resume, PostgreSQL advisory lock, row별 before/after/reason, nonzero exit를 구현한다. 공통 구현은 `BACKFILL-ARTIFACT-00` 한 library만 사용한다. `FOMS_REMEDIATION_ARTIFACT_ROOT`는 필수 absolute path이며 repo/worktree, user profile, OneDrive/Dropbox/Google Drive known folder, network share, reparse-point 하위면 fail-closed한다. 이 plan의 exact provider는 **Windows DPAPI CurrentUser v1**뿐이다. inheritance off+exact operator SID/SYSTEM ACL을 요구하고 동일 Windows account/host에서만 resume한다. Linux/Railway/다른 host는 별도 KEK spec 전 fail-closed한다. run별 random32-byte AES data key는 `CryptProtectData` CurrentUser로 wrap하고 `key-envelope.json={version:1,provider:'WINDOWS_DPAPI_CURRENT_USER_V1',key_id,wrapped_data_key_b64url,entropy_sha256,created_at}`에 저장한다. optional entropy는 `SHA256(FOMS_BACKFILL_KEY_WRAP_V1\0+LP(packet_id,phase,db_instance_id,artifact_dir_id))` exact bytes다. weak ACL/sync/unwrap/provider mismatch면 audit도 시작하지 않는다.

logical artifact dir는 `<protected-artifact-root>/3c3288370aebf6a9fd0372c35db9287c675671e8/<domain>`이다. audit는 REPEATABLE READ에서 non-PII `summary.json`과 `safe.csv.enc,ambiguous.csv.enc,unmapped.csv.enc`를 만든다. 각 `.enc` exact JSON envelope는 `{version:1,alg:'AES-256-GCM',key_id,nonce_b64url,aad_sha256,ciphertext_b64url}`이고 nonce12 random bytes다. AAD는 `FOMS_BACKFILL_PAYLOAD_V1\0+LP(packet_id,phase,relative_path,db_instance_id,source_fingerprint,column_schema_sha256)`다. `edit_backfill_manual.py`만 terminal/in-memory editor로 `manual.csv.enc`를 만들며 plaintext temp/editor argv0이다. hash 대상은 summary와 audit ciphertext raw bytes뿐이고 manifest/sha/manual/approval receipt/local checkpoint/export는 payload hash 목록에서 제외해 자기참조0이다.

`manifest.json`은 schema/tool version, report baseline SHA, audit 실행 SHA, tool/model/schema content fingerprint, DB-instance keyed ID, migration head, snapshot time, source identity/version/relevant-field canonical fingerprint, encrypted payload relative path/ciphertext SHA/row count/column schema/key ID를 가진다. `sha.txt`는 manifest raw bytes lowercase SHA-256+LF다. report baseline은 current HEAD ancestor여야 하고 audit SHA는 provenance다. 열거 content/migration이 같으면 unrelated later commit만 허용한다.

backfill은 `--artifact-dir <dir> --phase <packet-defined-literal>`만 받는다. exact input은 decrypted-in-memory safe 전부+manual 합집합이고 manual은 ambiguous∪unmapped identity마다 한 decision, duplicate/extra/missing/safe override0이다. `mapping_sha256=SHA256(RFC8785_JCS([{identity_fields,decision,target_ids,reason_code}] sorted by UTF-8 identity tuple))`; display text/PII는 mapping object에0이다. `approval-scope.json` exact schema는 `{schema_version:1,operation_id:'BACKFILL_APPLY',packet_id,phase,manifest_sha256,mapping_sha256,db_instance_id,source_composite_sha256,expected_run_row_version,masked_counts}`다. authority는 OPS DB record이며 Admin UI는 이 값만 본다. artifact/DB/content fingerprint가 다르면 write 전 STOP한다.

resume run ID는 `SHA256(LP(packet_id,phase,manifest_sha256,mapping_sha256))`다. target DB의 `maintenance_backfill_runs(run_id PK,packet_id,phase,db_instance_id,manifest_sha256,mapping_sha256,current_approval_seq,state=PENDING|RUNNING|PAUSED_APPROVAL|STOPPED_DRIFT|VERIFYING|DONE,lease_owner_hash,lease_token_hash,lease_expires_at,heartbeat_at,total_rows,completed_rows,last_error_code,started_at,completed_at,row_version)`와 checkpoint/append-only approval tables가 정본이다. lease token은 raw 저장0, 60초 lease/10초 heartbeat이며 expired lease만 same artifact/mapping/active approval로 reclaim한다. 각 batch business write+checkpoint+completed_rows+heartbeat는 target DB same tx다. WDC V2 checkpoint는 WDC DB, WDC cleanup은 primary DB에 따로 두고 cleanup은 V2 checkpoint hash+marker+CANONICAL과 자체 before/after manifest를 bind한다.

resume은 completed=current expected-after, pending=current expected-before composite 전체가 일치할 때만 진행한다. drift/checkpoint tamper는 state STOPPED_DRIFT, batch mutation0이며 local checkpoint는 authority0이다. `inspect_backfill_run.py --run-id <id> --output <status.json>`은 PII-free counts/lease/heartbeat/state/last_error와 exact `next_action=START|WAIT_LEASE|RESUME|REAUTHORIZE|REAUDIT|VERIFY|NONE`을 read-only 출력한다. approval Admin principal version이 바뀌면 다음 batch 전 PAUSED_APPROVAL이다. 다른 active ADMIN은 동일 manifest/mapping+current composite+previous seq+reason의 BACKFILL_REAUTHORIZE 뒤 append seq/run CAS만 갱신한다. crash→expired lease reclaim, reauthorize race 한 건, drift stop, VERIFYING→coverage100%→DONE을 PG+console acceptance로 검증한다.

manual 완성 뒤 operator는 `create_ops_approval_request.py --operation BACKFILL_APPLY --scope-file <artifact-dir>/approval-scope.json --expires-in-seconds 900 --output <protected-token.json>`을 실행하고 active ADMIN이 web에서 재인증 승인한다. 최초 apply는 `--approval-token-file`을 소비해 approval seq1을 만든다. 완료/중단 artifact는 기본7일, 법정 필요시 최대30일 TTL이며 `purge_foms_remediation_artifacts.py --artifact-dir <dir> --approval-token-file <path> --apply`가 wrapped data key를 먼저 파기하고 ciphertext/temporary file 부재를 검증해 DB tombstone hash를 남긴다. 기한 전 24h/6h alert, key 파기 후 복호화 불가를 test하며 raw path/PII log0이다.

```powershell
python tools/ops/check_remediation_artifact_root.py --root $env:FOMS_REMEDIATION_ARTIFACT_ROOT
$artifactRoot = Join-Path $env:FOMS_REMEDIATION_ARTIFACT_ROOT "3c3288370aebf6a9fd0372c35db9287c675671e8"

python tools/ops/audit_password_policy.py --output-dir "$artifactRoot/password-policy"
# password 변경은 사용자 self-service 또는 ADMIN_RESET_USER_PASSWORD web command만 사용. 범용 CLI/argv/env/file 입력 금지
python tools/ops/check_password_policy_readiness.py --artifact-dir "$artifactRoot/password-policy" --require-active-legacy 0

python tools/ops/audit_order_assignments.py --output-dir "$artifactRoot/assignments"
python tools/ops/backfill_order_assignments.py --artifact-dir "$artifactRoot/assignments" --phase ASSIGNMENT --dry-run
python tools/ops/backfill_order_assignments.py --artifact-dir "$artifactRoot/assignments" --phase ASSIGNMENT --approval-token-file <path> --apply --verify

python tools/ops/audit_installation_crews.py --output-dir "$artifactRoot/crews"
python tools/ops/backfill_installation_crews.py --artifact-dir "$artifactRoot/crews" --phase CREW --dry-run
python tools/ops/backfill_installation_crews.py --artifact-dir "$artifactRoot/crews" --phase CREW --approval-token-file <path> --apply --verify

python tools/ops/audit_order_state_axes.py --output-dir "$artifactRoot/state"
python tools/ops/repair_order_state_axes.py --artifact-dir "$artifactRoot/state" --phase STATE_AXES --dry-run
python tools/ops/repair_order_state_axes.py --artifact-dir "$artifactRoot/state" --phase STATE_AXES --approval-token-file <path> --apply --verify

python tools/ops/audit_production_runs.py --output-dir "$artifactRoot/production-runs"
python tools/ops/backfill_production_runs.py --artifact-dir "$artifactRoot/production-runs" --phase PRODUCTION_RUN --dry-run
python tools/ops/backfill_production_runs.py --artifact-dir "$artifactRoot/production-runs" --phase PRODUCTION_RUN --approval-token-file <path> --apply --verify

python tools/ops/audit_order_quests.py --output-dir "$artifactRoot/quests"
python tools/ops/backfill_order_quests.py --artifact-dir "$artifactRoot/quests" --phase QUEST --dry-run
python tools/ops/backfill_order_quests.py --artifact-dir "$artifactRoot/quests" --phase QUEST --approval-token-file <path> --apply --verify

python tools/ops/audit_as_cycles.py --output-dir "$artifactRoot/as-cycles"
python tools/ops/backfill_as_cycles.py --artifact-dir "$artifactRoot/as-cycles" --phase AS_CYCLE --dry-run
python tools/ops/backfill_as_cycles.py --artifact-dir "$artifactRoot/as-cycles" --phase AS_CYCLE --approval-token-file <path> --apply --verify

python tools/ops/audit_order_item_ids.py --output-dir "$artifactRoot/items"
python tools/ops/backfill_order_item_ids.py --artifact-dir "$artifactRoot/items" --phase ITEM_ID --dry-run
python tools/ops/backfill_order_item_ids.py --artifact-dir "$artifactRoot/items" --phase ITEM_ID --approval-token-file <path> --apply --verify

python tools/ops/audit_legacy_order_files.py --output-dir "$artifactRoot/files"
python tools/ops/backfill_legacy_order_files.py --artifact-dir "$artifactRoot/files" --phase ORDER_FILE --dry-run
python tools/ops/backfill_legacy_order_files.py --artifact-dir "$artifactRoot/files" --phase ORDER_FILE --approval-token-file <path> --apply --verify

python tools/ops/audit_legacy_chat_files.py --output-dir "$artifactRoot/chat-files"
python tools/ops/backfill_legacy_chat_files.py --artifact-dir "$artifactRoot/chat-files" --phase CHAT_FILE --dry-run
python tools/ops/backfill_legacy_chat_files.py --artifact-dir "$artifactRoot/chat-files" --phase CHAT_FILE --approval-token-file <path> --apply --verify

# (Designer ownership audit/backfill 제거 — FOMS Brain은 DESIGNER-RETIRE-01로 삭제 예정이라 owner backfill 불필요)

python tools/ops/audit_order_tasks.py --output-dir "$artifactRoot/tasks"
python tools/ops/backfill_order_tasks.py --artifact-dir "$artifactRoot/tasks" --phase ORDER_TASK --dry-run
python tools/ops/backfill_order_tasks.py --artifact-dir "$artifactRoot/tasks" --phase ORDER_TASK --approval-token-file <path> --apply --verify

python tools/ops/audit_drawing_revisions.py --output-dir "$artifactRoot/drawing-revisions"
python tools/ops/backfill_drawing_revisions.py --artifact-dir "$artifactRoot/drawing-revisions" --phase DRAWING_REVISION --dry-run
python tools/ops/backfill_drawing_revisions.py --artifact-dir "$artifactRoot/drawing-revisions" --phase DRAWING_REVISION --approval-token-file <path> --apply --verify

python tools/ops/audit_construction_attempts.py --output-dir "$artifactRoot/construction"
python tools/ops/backfill_construction_attempts.py --artifact-dir "$artifactRoot/construction" --phase CONSTRUCTION_ATTEMPT --dry-run
python tools/ops/backfill_construction_attempts.py --artifact-dir "$artifactRoot/construction" --phase CONSTRUCTION_ATTEMPT --approval-token-file <path> --apply --verify

```

WDC는 topology artifact를 읽고 아래 둘 중 **정확히 한 block만** 실행한다.

```powershell
python tools/ops/inspect_wdc_db_topology.py --output "$artifactRoot/wdc-links/topology.json"
```

`SAME_DATABASE` happy path — freeze/abort/runtime-state CLI는 실행 금지:

```powershell
python tools/ops/audit_wdc_order_links.py --topology-artifact "$artifactRoot/wdc-links/topology.json" --output-dir "$artifactRoot/wdc-links"
python tools/ops/backfill_wdc_order_links_v2.py --artifact-dir "$artifactRoot/wdc-links" --phase V2_BACKFILL --dry-run
python tools/ops/backfill_wdc_order_links_v2.py --artifact-dir "$artifactRoot/wdc-links" --phase V2_BACKFILL --approval-token-file <path> --apply --verify
python tools/ops/emit_wdc_order_link_checkpoint.py --run-id <run-id> --phase V2_BACKFILL --topology-artifact "$artifactRoot/wdc-links/topology.json" --output "$artifactRoot/wdc-links/checkpoint.json"
python tools/ops/check_wdc_link_consumer_rollout.py --topology-artifact "$artifactRoot/wdc-links/topology.json" --required-compatibility-generation <n> --output "$artifactRoot/wdc-links/consumer-rollout.json"
python tools/ops/mark_feature_cutover.py --family WDC_LINK --artifact "$artifactRoot/wdc-links/consumer-rollout.json" --approval-token-file <path> --expected-version <n> --apply
```

`SEPARATE_DATABASE` happy path — 반드시 freeze가 audit/backfill보다 먼저다:

```powershell
python tools/ops/set_wdc_link_runtime_state.py --state freeze --expected-generation <n> --approval-token-file <path> --apply
python tools/ops/audit_wdc_order_links.py --topology-artifact "$artifactRoot/wdc-links/topology.json" --output-dir "$artifactRoot/wdc-links"
python tools/ops/backfill_wdc_order_links_v2.py --artifact-dir "$artifactRoot/wdc-links" --phase V2_BACKFILL --dry-run
python tools/ops/backfill_wdc_order_links_v2.py --artifact-dir "$artifactRoot/wdc-links" --phase V2_BACKFILL --approval-token-file <path> --apply --verify
python tools/ops/emit_wdc_order_link_checkpoint.py --run-id <run-id> --phase V2_BACKFILL --topology-artifact "$artifactRoot/wdc-links/topology.json" --output "$artifactRoot/wdc-links/checkpoint.json"
python tools/ops/check_wdc_link_consumer_rollout.py --topology-artifact "$artifactRoot/wdc-links/topology.json" --required-compatibility-generation <n> --output "$artifactRoot/wdc-links/consumer-rollout.json"
python tools/ops/mark_feature_cutover.py --family WDC_LINK --artifact "$artifactRoot/wdc-links/consumer-rollout.json" --approval-token-file <path> --expected-version <n> --apply
python tools/ops/set_wdc_link_runtime_state.py --state canonical --expected-generation <n> --approval-token-file <path> --apply
```

다음은 **SEPARATE marker 전 failure-only** 복구다. happy path에서 실행 금지하며 marker/V2 runtime write/source fingerprint 조건 중 하나라도 다르면 command 자체가 nonzero다.

```powershell
python tools/ops/abort_wdc_link_cutover.py --expected-generation <n> --approval-token-file <path> --apply
```

두 topology 모두 canonical 뒤 cleanup은 primary DB의 별도 LEGACY_CLEANUP run/checkpoint다. `checkpoint.json`은 local 진행 파일이 아니라 위 emitter가 target DB run/checkpoint를 재조회해 canonical hash한 read-only export다.

```powershell
python tools/ops/audit_legacy_wdc_order_meta.py --wdc-checkpoint "$artifactRoot/wdc-links/checkpoint.json" --output-dir "$artifactRoot/wdc-links-cleanup"
python tools/ops/cleanup_legacy_wdc_order_meta.py --artifact-dir "$artifactRoot/wdc-links-cleanup" --phase LEGACY_CLEANUP --dry-run
python tools/ops/cleanup_legacy_wdc_order_meta.py --artifact-dir "$artifactRoot/wdc-links-cleanup" --phase LEGACY_CLEANUP --approval-token-file <path> --apply --verify

python tools/ops/audit_erp_flat_columns.py --output-dir "$artifactRoot/startup-flat"
python tools/ops/backfill_erp_flat_columns.py --artifact-dir "$artifactRoot/startup-flat" --phase STARTUP_FLAT --dry-run --batch-size 500
python tools/ops/backfill_erp_flat_columns.py --artifact-dir "$artifactRoot/startup-flat" --phase STARTUP_FLAT --approval-token-file <path> --apply --batch-size 500 --verify
```

`manual.csv.enc` 내부 plaintext를 in-memory editor에서만 다루는 exact schema:

- assignments: `order_id,domain,legacy_value,target_user_id,decision,reason,approved_by_user_id`; decision=`MAP|RELEASE|QUARANTINE`.
- crews: `order_id,legacy_worker_name,target_worker_id,linked_user_id,decision,reason,approved_by_user_id`; decision=`CREATE|MAP|RELEASE|QUARANTINE`.
- state: `order_id,axis,current_value,target_value,decision,reason,approved_by_user_id`; axis=`MAIN|LOGISTICS|HOLD|AS|DELETE|LEGACY_ALIAS`.
- production runs: `order_id,legacy_started_at,legacy_steps_json,legacy_defects_json,target_run_id,target_status,decision,reason,approved_by_user_id`.
- quests: `order_id,stage,source_quest_indexes,target_quest_id,required_team,decision,reason,approved_by_user_id`.
- AS cycles: `order_id,source_as_info_index,source_history_ids,target_cycle_id,target_status,visit_date,visit_time,completed_at,as_pending,as_blueprint,sales_delivery,decision,reason,approved_by_user_id`.
- items: `order_id,source_type,source_row_id,legacy_item_index,target_item_id,decision,reason,approved_by_user_id`; source=`ATTACHMENT|SCHEDULE_DATE`.
- files: `source_row_id,object_key,target_order_id,purpose,target_item_id,decision,reason,approved_by_user_id`; decision=`MAP|QUARANTINE`.
- chat files: `message_id,room_id,object_key,target_attachment_id,decision,reason,approved_by_user_id`; exact message/room object만 MAP, 나머지는 QUARANTINE.
- tasks: `task_id,order_id,current_status,current_team,current_owner_user_id,auto_key,target_task_uuid,target_source,target_team,decision,reason,approved_by_user_id`; decision=`MAP|QUARANTINE|CANCEL`.
- drawing revisions/requests: `order_id,transfer_history_index,attachment_ids,target_revision_id,request_history_index,target_request_id,request_status,checklist_checked,receipt_event_id,customer_confirm_event_id,target_confirmation_quest_id,decision,reason,approved_by_user_id`.
- construction: `order_id,history_start_id,attempt_id,status,evidence_attachment_ids,decision,reason,approved_by_user_id`.
- WDC links: `order_id,legacy_estimate_id,target_estimate_id,decision,reason,approved_by_user_id`; decision=`MAP|REMOVE_META|QUARANTINE`.

각 audit artifact/approval/apply는 위 manifest protocol을 공통 library와 golden fixture로 사용한다. password audit는 계정 식별값 없이 active/inactive·role별 legacy/current count만 만들고 rotation 대상 원문은 DB 밖 artifact에 내보내지 않는다. verify는 source 전체 coverage100%, active legacy password-policy account0(ENFORCED 시), duplicate active assignment/item ID0, mirror/projection unexpected mismatch0, unsafe order/chat file·drawing revision mapping0, missing current production run/quest0, missing/duplicate current AS cycle0, missing/duplicate open drawing request0, ambiguous construction attempt0일 때만 exit0이다. main PRODUCTION은 단일 start/step/defect history만 current IN_PROGRESS run으로, active stage의 quest 누락은 template+dynamic rule이 단일 해석일 때만 fresh current quest로, drawing revision/request는 exact transfer files+request/check+receipt event가 단일 연결일 때만 backfill한다. AS는 status/history/as_info가 한 cycle/transition 순서를 지지할 때만 safe map한다. Chat file은 exact message/room/key만 safe map한다. main CONSTRUCTION의 단일 start history와 exact evidence가 있으면 IN_PROGRESS/READY로, start가 없으면 attempt 없음으로 backfill한다. 직접 COMPLETED·복수 start·generic evidence·복수 receipt/customer candidate·AS 순서 충돌은 자동 추론하지 않고 manual CSV로 보낸다.

---

## 8. 검증 명령과 release gate

### 8.1 PR 로컬 게이트

```powershell
git diff --check
python tools/design/ssot_lint.py docs/design
python tools/perf/perf_scan.py --guard
```

bootstrap 두 packet은 runner가 아직 없으므로 아래 direct literal command를 쓴다.

```powershell
# BASE-00
git rev-parse HEAD
git status --short
python -m pytest -q tests/domains/test_erp_permissions.py tests/domains/test_erp_orders_structured_put.py tests/domains/test_drawing_wizard_api.py tests/domains/test_production_steps_api.py tests/domains/test_construction_gate_api.py tests/domains/test_notification_ownership.py tests/domains/test_order_copy_api.py

# PACKET-HARNESS-00 (이 packet이 test 파일을 먼저 생성한 뒤 실행)
python -m pytest -q tests/harness/test_run_packet_manifest.py
```

그 뒤의 모든 packet은 공통 명령 후 아래 literal 명령 하나를 실행한다.

```powershell
powershell -NoProfile -File tools/tests/run_packet.ps1 -PacketId <literal-PR-ID>
```

`PACKET-HARNESS-00`이 만드는 `docs/harness/foms_bugfix_packet_tests.json`은 모든 5.2 packet ID를 exact key로 갖는 machine SSOT다. entry는 `depends_on`, `dependency_classes:{packet_harness,backfill_artifact,write_guard,postgres}`, `commands`, `existing_regressions`, `created_tests:[{path,owner_packet}]`, `browser_scenarios`, `deploy_check_ids`, `deployment_evidence_mode=PROVIDER_BOOTSTRAP|HEARTBEAT` exact schema다. effective dependency는 5절 공식으로 계산한다. `run_packet.ps1`은 local tree/diff/test만 실행하고 deploy 상태를 추측하지 않는다. test는 table ID, explicit ASCII edge, class inventories, transitive completion을 각각 exact 비교하고 unknown/cycle/path/owner를 거부한다.

배포 check 정본은 `docs/harness/foms_deploy_checks.json`의 `{id,owner_packet,command_template}`다. PACKET-HARNESS-00은 두 manifest의 schema/seed/runner만 소유한다. 이후 각 packet은 자기 PR에서 **자기 packet entry의 test/deploy_check_ids와 owner_packet이 자기인 신규 registry rows만 atomically append/update**할 수 있고 다른 packet entry/row 수정은 test가 거부한다. future owner row 선등록, duplicate/rewrite/delete, arbitrary condition/expression/eval0이다. 조기 packet은 자신/완료 dependency가 실제 제공한 check만 가진다. RELEASE-GATE-00은 final applicable IDs를 모두 열거한다.

packet completion은 repo ledger가 아니다. one packet은 parent 대비 exact implementation commit 한 개로 squash하고 commit message에 `FOMS-Packet: <literal-ID>` trailer가 한 번 있어야 한다. pull_request workflow의 canonical commit은 `GITHUB_SHA`가 아니라 event payload의 `pull_request.head.sha`, push는 `GITHUB_SHA`, manual reissue는 explicit immutable commit input이다. job은 그 commit을 checkout해 entry와 required check green 뒤 `{schema_version,packet_id,implementation_commit_sha,parent_sha,tree_sha,packet_entry_sha256,historical_manifest_blob_sha256,workflow_run_id,check_run_ids,conclusion:'success',completed_at,supersedes_commit_sha?,reissued_from_run_id?}` canonical JSON+SHA256을 content-addressed Actions artifact로 올린다. collector는 `git show <implementation>:docs/harness/foms_bugfix_packet_tests.json`의 historical blob/entry hash와 workflow commit/conclusion을 재검증하며 **current 전체 manifest hash와 비교하지 않는다**.

Actions artifact는 삭제/만료 가능한 cache다. 부재 시 `reissue_packet_completion_evidence.yml`을 exact implementation commit+packet ID로 실행해 해당 commit의 historical workflow/manifest entry와 동일 required checks를 다시 수행하고 `reissued_from_run_id` evidence를 만든다. commit/tree/entry/check가 달라지면 reissue 실패다. artifact 삭제 자체를 packet 완료 취소나 immutable storage라고 표현하지 않는다. deploy branch에서 같은 packet supersession은 descendant+exact `supersedes_commit_sha`만 허용한다.

FOMS production 기본 cherry-pick은 별도 `equivalent_promotion_of` mapping을 쓴다. promotion commit은 `FOMS-Promotion-Of: <source-implementation-sha>` trailer를 가지며 production CI가 source/target single-commit `git patch-id --stable`, touched-path exact set, source packet entry hash, `promote_completeness.py`, target required checks를 검증해 `{source_packet_id,source_commit_sha,target_commit_sha,stable_patch_id,touched_paths_sha256,production_workflow_run_id,check_run_ids,conclusion:'success'}` evidence를 만든다. squash/rebase/충돌 수동해결은 동등 mapping 금지다. serving commit은 source implementation의 descendant이거나 verified target promotion commit의 descendant여야 한다.

family 통합 gate는 해당 family의 모든 packet이 완료된 뒤에만 별도 실행한다. 이는 개별 packet 완료 명령이 아니다.

| 완료 family | integration gate |
|---|---|
| auth/finance/quest/channel/delete | `pytest -q tests/domains/test_erp_permissions.py tests/domains/test_cash_receipt_issue_api.py tests/domains/test_notification_ownership.py tests/domains/test_order_attachment_permissions.py tests/architecture/test_mutation_policy_inventory.py tests/domains/test_mutation_policy_matrix.py tests/domains/test_assignment_contract.py` |
| revision/state/data/side-effect | `powershell -NoProfile -File tools/tests/run_postgres_concurrency.ps1` 후 family가 생성한 transition/outbox/structured test와 기존 production/construction/drawing tests |
| wizard/upload/file | 기존 drawing/construction/attachment tests와 family가 생성한 intent/ticket/file-scope tests |
| shell/history/route/push/offline | `pytest -q tests/domains/test_packing_api.py tests/domains/test_history_read_model.py tests/domains/test_measurement_route_inline.py tests/domains/test_measurement_route_eta.py tests/domains/test_notification_ownership.py` 및 family 신규 offline privacy test |
| startup | `pytest -q tests/domains/test_run_startup_logging.py tests/domains/test_sqlite_startup_compat.py`와 신규 import-purity test, `python -c "import app; print('APP_OK')"` |
| template/UI touched | `$env:DATABASE_URL='sqlite:///tests/visual/foms_test_visual.sqlite'`; `pytest -q tests/visual/test_p1_mockup_structure.py tests/visual/test_erp_order_edit_mobile_form.py`; 해당 persona browser scenario |

integration gate가 참조하는 **신규 테스트 파일의 생성 소유 packet**은 각 packet의 `created_tests[{path,owner_packet}]`에 exact path로 pin한다: `tests/architecture/test_mutation_policy_inventory.py`·`tests/domains/test_mutation_policy_matrix.py`는 AUTH-01, `tests/domains/test_assignment_contract.py`는 ASSIGNMENT-00이 소유한다. gate 명령은 소유 packet이 완료돼 해당 파일이 존재할 때만 green이며, 부재 상태 실행은 collection error로 red다.

코어 권한·상태·DB 변경은 packet manifest에서 PostgreSQL을 필수로 표시한다. UI/CSS/template 변경은 구조 테스트와 실제 browser persona를 함께 실행한다. integration gate는 `pytest-xdist` 또는 CI shard로만 병렬화하고 test를 생략하지 않는다.

### 8.2 deploy gate

1. HEAD drift와 unrelated dirty file 혼입 검사.
2. 데이터 read-only preflight와 필요한 migration dry-run.
3. secret/env preflight. 값은 출력하지 않는다.
4. deploy 전 local runner는 deploy 상태를 판정하지 않는다. approved deploy 뒤 Railway deployment artifact를 받아 별도 `run_deploy_checks.ps1`로 **현재 packet과 이미 배포된 prerequisite가 소유한 check ID만** 확인한다. 아직 생성되지 않은 future script/service를 조기 expand deploy에 요구하지 않는다.
5. `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1`.
6. push 승인 전에는 isolated local commit과 local gate evidence까지만 만든다. 사용자가 deploy push를 명시한 경우에만 session-own commit으로 push한다.
7. push가 실제 발생한 경우에만 `python tools/harness/ci_watch.py --quick`을 실행한다. upstream PR이 remote CI green이 되기 전 dependent PR의 merge/deploy는 금지하되, 독립 local 분석은 계속할 수 있다.
8. approved deploy 반영 후 최소 persona matrix를 실제 클릭한다.

per-packet local preflight:

```powershell
powershell -NoProfile -File tools/tests/run_packet.ps1 -PacketId <literal-PR-ID>
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1
```

Railway provider signature를 가정하지 않는다. CUTOVER-MODE-01이 `runtime_replica_heartbeats(service_id,deployment_id,replica_id,region,commit_sha,compatibility_generation,state_aware_families_json,boot_nonce_hash,started_at,last_seen_at,PRIMARY KEY(deployment_id,replica_id))`를 만들고 각 web/worker/ops replica가 Railway-provided `RAILWAY_SERVICE_ID,RAILWAY_DEPLOYMENT_ID,RAILWAY_REPLICA_ID,RAILWAY_REPLICA_REGION,RAILWAY_GIT_COMMIT_SHA`와 in-image compatibility manifest를 10초마다 upsert한다. env missing/format mismatch는 readiness red이고 raw env/token은 log0이다.

CUTOVER-MODE-01 completion 전 packet manifest는 `deployment_evidence_mode=PROVIDER_BOOTSTRAP`만 허용한다. collector는 Railway GraphQL의 desired services/deployments/replica count/regions/status와 packet completion을 30초 stable 확인하지만 runtime heartbeat를 주장하지 않으며 irreversible marker/key activation/data enforcement0이다. CUTOVER-MODE-01 자체와 그 뒤 모든 packet은 `deployment_evidence_mode=HEARTBEAT`이고 provider inventory+DB heartbeat exact cardinality를 요구한다. CUTOVER 완료 뒤 PROVIDER_BOOTSTRAP은 금지된다.

approved deploy 뒤 `collect_foms_deployment_evidence.py --packet-id <ID> --environment <deploy|production> --evidence-mode <provider-bootstrap|heartbeat> --freshness-seconds 60 --stability-seconds 30 --output <protected.json>`을 실행한다. schema는 `{schema_version,evidence_mode,environment,captured_at,expires_at,railway_query_sha256,services:[{service_id,desired_replicas,serving_deployments}],replicas:[...],packet_completion,promotion_equivalence?,canonical_sha256}`다. HEARTBEAT는 desired count만큼 같은 deployment/commit의 fresh distinct replica와 generation/family를 요구한다. GraphQL desired inventory가 없거나 rolling old deployment가 traffic이면 추정하지 않고 nonzero다. token/raw response는 저장0이다.

`run_deploy_checks.ps1`은 canonical hash, freshness≤60초, desired inventory/status, mode별 heartbeat cardinality/region, packet evidence historical entry를 재검증한다. deploy는 source implementation ancestry, production은 source ancestry 또는 verified promotion-target ancestry를 검사한다. HEARTBEAT에서 한 replica라도 owner/generation/family 불일치면 nonzero다. environment enum과 resolved protected path만 허용하며 eval0이다.

```powershell
python tools/ops/collect_foms_deployment_evidence.py --packet-id <literal-PR-ID> --environment deploy --evidence-mode <provider-bootstrap|heartbeat> --freshness-seconds 60 --stability-seconds 30 --output "<protected-deployment-artifact.json>"
powershell -NoProfile -File tools/tests/run_deploy_checks.ps1 -PacketId <literal-PR-ID> -Environment deploy -DeploymentArtifact "<protected-deployment-artifact.json>"
```

registry command template의 고정 예시는 다음과 같다.

```powershell
# SIDEFX-WORKER-01 배포 뒤 sidefx producer/consumer packet
python tools/ops/check_sidefx_readiness.py --max-heartbeat-age 30 --max-oldest-pending-lag 60 --max-expiry-scan-lag 360 --max-retention-scan-lag 90000 --max-dead 0
# CHANNEL-INBOUND-ORDER-01 service provision 뒤 create-enabled packet
python tools/ops/check_channel_inbound_readiness.py --max-heartbeat-age 15 --max-oldest-pending-lag 60 --max-recovery-scan-lag 360 --max-expired-leases 0 --max-key-reference-mismatches 0 --max-unacked-24h-alerts 0 --max-unresolved-deadline-breaches 0 --max-retention-incidents 0
# CUTOVER-MODE-01 배포 뒤 mode/marker affected packet
python tools/ops/check_feature_cutover_modes.py --manifest docs/harness/foms_feature_mode_matrix.json
# SECRET-01/SECRET-02가 소유하는 third-party secret consumer만
python tools/ops/check_foms_secret_config.py --scope <literal-scope> --require-env --redact
# SESSION-SIGNING-STATE-00/SESSION-SIGNING-SECRET-01 단계별 audit/READY/ACTIVE/rotation check만
python tools/ops/check_foms_signing_secret.py --phase <STATE_EXPANDED|READY|ACTIVE|ROTATING|CURRENT_ONLY> --redact
```

`RELEASE-GATE-00`이 배포된 최종 통합 release에서만 위 applicable check 전부와 아래 full checker를 실행한다. 조기 STATE/schema/containment deploy는 이 final checker가 아직 없다는 이유로 미루지 않는다.

```powershell
python tools/ops/check_foms_remediation_readiness.py --artifact-root "$env:FOMS_REMEDIATION_ARTIFACT_ROOT/3c3288370aebf6a9fd0372c35db9287c675671e8"
```

#### 8.2.1 expand→audit→enforce와 fail-closed rollback

| family mode | ENFORCED/TICKET prerequisite | DISABLED rollback 계약 |
|---|---|---|
| `FOMS_ASSIGNMENT_MODE=LEGACY|ENFORCED|DISABLED` | assignment audit/backfill verify 100%, AUTH matrix green | JSON name auth로 복귀하지 않고 assignment-required mutation 503; read-only 가능 |
| `FOMS_ORDER_MUTATION_MODE=LEGACY|ENFORCED|DISABLED` | writer/consumer inventory 100%, REV-99 green | legacy writer를 열지 않고 affected mutation 503; additive version/receipt schema 유지 |
| `FOMS_STATE_COMMAND_MODE=LEGACY|ENFORCED|DISABLED` | state/production/quest/AS/drawing audit, all writer packets+guard green | direct status writer를 열지 않고 state mutation 503; read model 유지 |
| `FOMS_QUEST_MODE=LEGACY|ENFORCED|DISABLED` | current quest audit/backfill 100%, dynamic team persona, GET lazy-create 0 | quest-gated mutation 503; GET read-only, lazy create 복구 금지 |
| `FOMS_PRODUCTION_RUN_MODE=LEGACY|ENFORCED|DISABLED` | run backfill 100%, in-flight current run 누락 0, persona green | production command 503; flat writer 복구 금지 |
| `FOMS_AS_CYCLE_MODE=LEGACY|ENFORCED|DISABLED` | AS cycle/classification backfill 100%, current cycle ambiguity 0 | AS command 503; generic field writer 복구 금지 |
| `FOMS_DRAWING_REVISION_MODE=LEGACY|ENFORCED|DISABLED` | revision/request/receipt/customer/quest ID backfill 100%, E2E green; wizard pending create는 expiry scan ready | cutover rollback은 transfer/receipt/confirm/production-start 503; runtime scan 장애는 wizard pending create capability만 503; 추정 fallback 금지 |
| `FOMS_UPLOAD_MODE=LEGACY|TICKET|DISABLED` | item/order+chat file backfill 100%, worker delivery+expiry scan ready | ticket/UPLOAD_DRAFT issue capability 503, existing valid completion은 typed policy대로 처리; arbitrary folder를 열지 않음. authorized multipart fallback은 별도 검증 route만 |
| `FOMS_CONSTRUCTION_MODE=LEGACY|ENFORCED|DISABLED` | attempt backfill 100%, purpose evidence, persona green | direct COMPLETED를 열지 않고 start/evidence/complete 503 |
| `FOMS_CHAT_SCOPE_MODE=LEGACY|ENFORCED|DISABLED` | room/file backfill, HTTP/socket membership persona green | chat mutation/file read 503, raw key/socket join 복구 금지 |
| `FOMS_NOTIFICATION_DELIVERY_MODE=LEGACY|ENFORCED|DISABLED` | domain SIDEFX worker delivery ready, ACTOR-STATE+urgent send/ack persona green | REQUIRE_DELIVERY인 urgent send/control만 503/hidden, 기존 notification read와 DEGRADED_OK ordinary business mutation 유지; 별도/legacy notification worker 복구 금지 |
| `FOMS_TASK_MODE=LEGACY|ENFORCED|DISABLED` | task backfill coverage 100%, auto-key collision 0, personal-board persona green | task mutation 503/read-only, hard-delete/raw automation 복구 금지 |
| `FOMS_PASSWORD_POLICY_MODE=WARN|ENFORCED|DISABLED` | WARN에서 active legacy-policy role별 count·사용자 공지/banner; 새/reset strong; active count 0+Admin 승인 뒤 ENFORCED | cutover 후 legacy-policy login/business 503+지원 안내; weak password 허용이나 policy version 추정 금지 |
| `FOMS_OFFLINE_SW_MODE=READ_ONLY|DISABLED` | A0 historical-SW-backed update fetch+legacy inventory/recovery/purge+server nonce completion, A1 protocol2 inventory+REV-99, all-serving generation, JSON/form/provider persona green; offline mutation 항상 없음 | marker 뒤 protocol1/queued writer를 열지 않고 old mutation409; update/recovery/read cache 장애는 PII-free support shell 또는 DISABLED, queued writer 재활성화 금지 |
| `FOMS_WDC_LINK_MODE=LEGACY|CANONICAL|DISABLED` | topology artifact; SAME atomic dual-write+online V2 checkpoint+all-serving→marker, SEPARATE fence/FROZEN+checkpoint+all-serving→marker→state CANONICAL; persona green | SAME legacy read/dual writer 또는 SEPARATE FROZEN 유지, match/unmatch503; marker 뒤 legacy meta/V1 read-write 복구 금지 |

모든 schema migration은 expand-only다. Git SHA에는 순서가 없으므로 in-image 정본은 Docker context에 포함되는 tracked `foms/build_compatibility.json`의 `{schema_version,generation,supersedes_generation,state_aware_families}`다. `docs/` excluded 파일에 의존하지 않는다. `Dockerfile`은 이 파일을 `/app/foms/build_compatibility.json`으로 explicit COPY하고, `tools/harness/verify_build_compatibility.py --commit-sha <sha> --merge-base <sha>`가 generation 양의 정수/증가, supersedes exact, family enum, incompatible change 때 generation bump를 검증한다. CI built-image smoke가 container 내부 파일을 읽고 GitHub packet completion evidence에 generation/families를 넣어 commit과 외부적으로 bind한다. runtime은 파일+`RAILWAY_GIT_COMMIT_SHA`를 읽어 heartbeat에 pair로 기록하고 missing/mismatch fail-start한다. SHA는 provenance/ancestry용일 뿐 크기 비교0이다.

`feature_cutover_fences(family PRIMARY KEY,mode=OPEN|DRAINING|CUTOVER,generation,row_version,updated_at)`를 15 family 모두 additive pre-seed하고 `feature_cutover_markers(family PRIMARY KEY,cutover_at,cutover_sha,cutover_generation,minimum_compatibility_generation,readiness_artifact_sha256,ops_approval_id,approved_by_admin_user_id,row_version,created_at)`를 irreversible 정본으로 둔다. `approved_by_admin_user_id`는 CLI 입력이 아니라 consumed approval row에서 복사한다. family는 `ASSIGNMENT|ORDER_MUTATION|STATE_COMMAND|QUEST|PRODUCTION_RUN|AS_CYCLE|DRAWING_REVISION|UPLOAD|CONSTRUCTION|CHAT_SCOPE|NOTIFICATION_DELIVERY|TASK|PASSWORD_POLICY|OFFLINE_SW|WDC_LINK` 15개다(DESIGNER_AUTH는 Brain 삭제로 제외). `mark_feature_cutover.py --family <literal> --artifact <path> --approval-token-file <path> --expected-version <n> --apply`만 최초 insert하며 all-serving state-aware generation, operation-bound Admin approval, readiness를 검증한다. update/delete/downgrade0이다.

각 affected business mutation은 tx 시작 직후 fence `FOR KEY SHARE`, 같은 tx marker read/effective mode 뒤 business·receipt·event·outbox commit까지 lock을 유지한다(process cache0). DB fault는 시작 전503/변화0이다. external provider I/O 중 DB lock을 잡지 않는다. mode manifest는 family별 `pre_cutover_effect_policy=DRAIN|COMPATIBLE`를 exact 선언한다. COMPATIBLE은 pre-marker outbox payload에 schema_version, source generation, provider idempotency key가 있고 post-marker worker가 같은 의미로 처리 가능하다는 golden test가 있을 때만 허용하며 marker 뒤 delivery가 완료될 수 있음을 명시한다.

DRAIN family는 `begin_feature_cutover_drain.py --family <literal> --artifact <all-serving> --approval-token-file <path> --apply`가 fence FOR UPDATE로 in-flight business tx를 기다린 뒤 `OPEN→DRAINING`을 commit한다. 이후 새 affected business mutation/control은503/hidden이라 새 outbox0이고 worker는 기존 PENDING/PROCESSING만 idempotent 처리한다. readiness가 PENDING0/PROCESSING0/expired lease0/provider reconciliation0을 stable window로 증명하며 mark CLI가 같은 값을 fence FOR UPDATE transaction 안에서 다시 확인한 뒤 marker insert+`DRAINING→CUTOVER`를 commit한다. marker 전 실패는 `abort_feature_cutover_drain.py ... --approval-token-file`이 marker0, source state unchanged, unresolved effect0을 검증해 OPEN으로 복구한다. COMPATIBLE family mark는 FOR UPDATE로 in-flight business tx를 drain한 뒤 same-tx insert/CUTOVER한다. 따라서 mark 반환 뒤 legacy **business commit/outbox insert**0이고 외부 effect는 선언한 policy대로만 남는다.

| family | policy | stability seconds | effect source / exact deploy check ID |
|---|---:|---:|---|
| ASSIGNMENT | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| ORDER_MUTATION | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| STATE_COMMAND | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| QUEST | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| PRODUCTION_RUN | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| AS_CYCLE | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| DRAWING_REVISION | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| UPLOAD | DRAIN | 120 | `STORAGE_DELETE_V1 / CUTOVER_STORAGE_DRAIN` |
| CONSTRUCTION | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| CHAT_SCOPE | COMPATIBLE | 30 | `NONE / CUTOVER_NONE_QUIET` |
| NOTIFICATION_DELIVERY | DRAIN | 120 | `NOTIFICATION_PROVIDER_V1 / CUTOVER_NOTIFICATION_DRAIN` |
| TASK | COMPATIBLE | 30 | `DOMAIN_SIDEFX_V1 / CUTOVER_SIDEFX_COMPAT` |
| PASSWORD_POLICY | COMPATIBLE | 30 | `NONE / CUTOVER_NONE_QUIET` |
| OFFLINE_SW | COMPATIBLE | 30 | `NONE / CUTOVER_NONE_QUIET` |
| WDC_LINK | COMPATIBLE | 30 | `NONE / CUTOVER_NONE_QUIET` |

`CUTOVER_SIDEFX_COMPAT`은 schema_version+source_generation+provider idempotency key golden vectors와 old/new worker 동일 effect를 검증한다. `CUTOVER_NONE_QUIET`은 해당 family outbox/provider call0을 30초 확인한다. CHAT_SCOPE는 실시간 전송이 CHAT-SOCKET-AUTH-01의 동기 socket emit(canonical send+recipient별 1회)이고 fan-out은 NOTIFICATION_DELIVERY family가 별도 소유하므로 자체 async outbox effect가 없어 `NONE / CUTOVER_NONE_QUIET`이다. 두 DRAIN check는 family-scoped PENDING0/PROCESSING0/expired lease0와 provider reconciliation mismatch0을 120초 연속 요구한다. UPLOAD는 storage delete object-state HEAD/result, NOTIFICATION은 provider idempotency receipt와 delivery row를 대조한다. checker unavailable/unknown status는 nonzero다.

두 live replica test는 A legacy shared-lock tx→B mark blocked→A commit→mark→A/B new legacy mutation0, DRAIN provider call/lease timing과 abort, COMPATIBLE post-marker idempotent delivery, mark crash atomic0을 검증한다. perf는 fence read/lock TTFB budget을 잠근다. `check_feature_cutover_modes.py`는 env mode·image generation·DB marker/fence를 비교해 post-cutover legacy/WARN/generation 미달을 fail-closed한다. manifest entry는 `family,env_var,allowed_pre_cutover_modes,allowed_post_cutover_modes,minimum_compatibility_generation,pre_cutover_effect_policy,stability_seconds,effect_source,provider_reconciliation_check_id,prerequisite_packet_ids,affected_control_ids,runtime_readiness_class,incompatible_modes` exact literal이고 위 15-row inventory와 양방향 비교한다. UI는 effective post-cutover mode+readiness 아니면 control을 숨긴다. rollback은 DISABLED read-only/503이며 legacy writer0이다.

construction은 staging ENFORCED/production LEGACY로 시작한다. 순서는 schema expand→read-only audit→safe row backfill→dual-read projection 비교→100% verify→staging ENFORCED→persona/24시간 지표→production 승인 후 ENFORCED다. in-flight main CONSTRUCTION에서 단일 start history+exact evidence는 IN_PROGRESS/READY, start 없음은 attempt 없음, 복수 start/direct COMPLETED/generic evidence는 manual CSV다. cutover 후 rollback은 DISABLED로 complete를 503으로 닫으며 CONSTRUCTION→COMPLETED legacy writer를 절대 되살리지 않는다.

SIDEFX-WORKER-01 배포는 파일 추가로 끝나지 않는다. Railway에 Config Path `railway-domain-sidefx.toml`, start command `python tools/ops/run_domain_side_effect_outbox.py --loop --interval 5 --expiry-scan-interval 300 --retention-scan-interval 86400`인 별도 service를 만들고 delivery+expiry+retention heartbeat/readiness를 확인한다. service/env provisioning 전 관련 mode는 ENFORCED/TICKET이 될 수 없다. cutover 뒤 장애 시 2.3의 `REQUIRE_DELIVERY`와 `REQUIRE_EXPIRY_SCAN` capability만 typed 503/hidden으로 닫고 `DEGRADED_OK` command는 outbox insert+DB cache generation barrier가 성공하는 한 commit한다. env mode를 request가 자동 변경하거나 ordinary cache/geocode/storage-delete 때문에 전체 order writer를 DISABLED로 닫지 않는다.

CHANNEL-INBOUND-ORDER-01도 파일 추가로 끝나지 않는다. create=false/DB false 상태에서 Railway 별도 service를 Config Path `railway-channel-inbound.toml`, start command `python tools/ops/run_channel_inbound_worker.py --loop --interval 2 --lease-seconds 60 --max-attempts 10 --recovery-scan-interval 300`으로 provision한다. web와 SIDEFX service에는 이 command/import 등록이 0이어야 한다. service/env/encryption-key/heartbeat/owner/recovery scan·unresolved-deadline alert와 SCALE-CHANNEL artifact·accepted conservation invariant 전에는 `set_channel_inbound_create_state.py --state enable ... --approval-token-file <path> --apply`를 실행하지 않는다. runtime 장애/rollback은 별도 operation-bound token을 쓴 같은 CLI의 `--state disable` 성공(PENDING/PROCESSING0)으로 cutoff를 증명한 뒤 service를 복구한다. Webhook intake를 함께 끌 때만 provider disable artifact 뒤 inbound blueprint를 내린다.

#### 8.2.2 Channel provider flag cutover

| flag 조합 | runtime 계약 | 전환 gate |
|---|---|---|
| `CHANNEL_FUNCTION_ENABLED=false` | Function blueprint 미등록, 모든 method 404 | ChannelTalk Function 등록/호출을 먼저 disable한 redacted console artifact, provider error0. 호출 중이면 STOP |
| `CHANNEL_FUNCTION_ENABLED=true` | PUT만 provider contract, POST/GET405; signing key/channel/fixture/schema readiness 필수 | live redacted method fixture+schema와 sandbox signature persona green |
| 두 inbound flag 모두 `false` | Webhook blueprint404, DB create false; accepted-before-cutoff job은 encrypted PAUSED_ACCEPTED/recovery SLA 유지 | provider disable→DB disable cutoff→PENDING/PROCESSING0→blueprint off, accepted conservation green |
| inbound `false`, create `true` | invalid config, startup/readiness nonzero, effective create false/Order0 | create를 먼저 DB+env false로 내리기 전 inbound false 금지 |
| inbound `true`, create `false` | planned soak: auth/source/schema 후 masked `SOAK_IGNORED` receipt200; 신규 input/intent/job/Order0, 기존 accepted job PAUSED | provider configuration이 soak를 의도한 artifact, recovery alert green; deadline breach면 CREATE event 503/provider disable |
| 두 inbound flag 모두 `true` | encrypted canonical input+ID job 후 dedicated worker constructor | owner/worker/key/readiness, DB enable token, live fixture, accepted conservation, pause/resume/recovery와 SALES 3-cohort persona green |

Channel provider flag는 `feature_cutover_markers`의 irreversible business family가 아니다. 그러나 false 전환의 provider-first 순서와 true 전환의 readiness artifact는 `check_foms_remediation_readiness.py`가 검증하고, request/worker가 env를 자동 변경하지 않는다.

### 8.3 production gate

- 사용자가 production 승격을 명시 승인하기 전 push/PR 생성 금지.
- 이 세션/작업의 검증된 commit만 `promote_completeness.py`로 dependency 확인 후 production PR.
- geocode/provider 등 third-party secret 신규값 주입·폐기는 `SECRET-01`; application session/WAM root·legacy/next key 전환은 `SESSION-SIGNING-STATE-00`+`SESSION-SIGNING-SECRET-01` runbook만 따른다.
- auth/state/data PR은 deploy persona·DB invariance evidence가 없으면 승격 금지.

---

## 9. 전역 STOP 조건

다음 중 하나면 구현자는 추측하지 않고 해당 PR을 중단해 evidence와 질문을 보고한다.

1. 기준 SHA 또는 touched file이 계획과 달라졌다.
2. URL-map mutation inventory에 policy 미분류 endpoint가 남았다.
3. form writable path 또는 stage writer inventory가 완전하지 않다.
4. 8-stage 정본과 실제 운영 데이터가 충돌하고 자동 repair가 데이터 의미를 바꾼다.
5. upload legacy key를 order/purpose에 안전하게 매핑할 수 없다.
6. predeploy가 모든 web service에 1회 적용됨을 확인하지 못했다.
7. PostgreSQL 동시성 테스트 없이 SQLite만 green이다.
8. browser persona negative test 또는 DB 불변성이 실패한다.
9. 보안 rollback이 취약한 legacy route/helper를 다시 연다.
10. deploy CI가 green이 아니다.
11. unrelated dirty worktree 변경이 PR diff에 섞였다.
12. production 작업인데 사용자 명시 승격 승인이 없다.
13. side-effect outbox를 쓰는 command인데 dedicated worker heartbeat/lag/DEAD readiness가 기준을 통과하지 않는다.
14. 실제 ChannelTalk console/traffic과 redacted Function method·Webhook registration/event/action/tenant artifact가 누락·불일치하거나, 해당 provider가 아직 호출 중인데 Function/Webhook enable flag를 false로 바꾸려 한다.
15. `SESSION-SIGNING-STATE-00`의 state/key ID/SHA/artifact/env가 불일치하거나 READY/ROTATION_READY에서 all-serving replica100% 전 activation을 시도하거나, `SESSION-SIGNING-STATE-00`과 `SESSION-SIGNING-SECRET-01`을 한 PR/deploy로 합치거나, ACTIVE 뒤 non-state-aware image로 rollback하려 한다.
16. audit/backfill의 Windows DPAPI provider/ACL/envelope·mapping JCS hash·operation approval·packet+phase run ID·lease/state/status·completed-after+pending-before가 누락/변조/stale이거나 wrong account/host/plaintext/source drift다.
17. OFFLINE_SW/WDC_LINK 등 irreversible marker 뒤 `minimum_compatibility_generation` 미만 또는 해당 family 비-state-aware image를 deploy/rollback하거나 legacy queued writer/meta reader를 다시 연다.
18. Channel create=true인데 worker/owner/key-reference/decrypt sample/heartbeat/lag/lease/recovery-scan/24h ACK/deadline/retention-incident readiness 또는 accepted partition conservation이 실패하거나 invalid `inbound=false,create=true` 조합이다.
19. signing legacy key가 known/default/short/compromised인데 BRIDGE를 선택하거나, FORCE에서 AUTH_ONLY 전 rescue all-serving+pending smoke, replica quiescence, PII-free maintenance/WAM-expired UX, private current smoke 또는 failed-smoke roll-forward branch가 없다.
20. auth bootstrap desired replica boot/epoch heartbeat에 gap/restart/dirty가 있거나 900초 연속 proof 전 activation하거나, rotation all-serving 전 activation/old-key rollback을 시도한다.
21. WDC topology artifact와 명령 branch가 다르거나, SAME atomic dual-write/equivalence 또는 SEPARATE fence100%+FROZEN/in-flight0 없이 V2 backfill/marker를 하거나, V2 checkpoint/all-serving/marker/effective CANONICAL 없이 cleanup한다.
22. cutover affected mutation consumer가 DB marker를 live request에서 읽지 않거나 marker DB 장애 때 legacy/취약 writer로 fail-open한다.
23. operation manifest-listed CLI가 token 없이 실행되거나 operator가 approver를 지정하거나, APPROVED→RESERVED 전 principal/scope/artifact/version/generation/race 검증이 실패한다. RESERVED 뒤 취소 가능하다고 가정하는 구현도 STOP한다.
24. artifact/control root가 unsafe이거나 Windows exact ACL/DPAPI provider를 증명하지 못하거나 payload/manual/PII가 plaintext disk/temp/log에 있다.
25. deployment evidence가 trigger별 canonical commit/historical entry, provider inventory, mode별 heartbeat, ephemeral artifact reissue 또는 production promotion mapping을 검증하지 못하거나 commit/generation/family를 추정한다.
26. historical exact scriptURL update가 A0에 도달하지 않거나, real subjectless-v1을 proof 없이 render/export/discard하거나, blocked-IDB Retry/support/bytes-preserve 또는 recovery envelope roundtrip이 없다.
27. Channel old-key live reference가 남은 채 key/env를 제거하거나, accepted partition이 conservation SQL에서 빠지거나, deadline terminal/legal hold/visible RETENTION_EXPIRED 중 하나가 아니다.
28. cutover family policy/stability/effect source/check ID가 15-row inventory와 다르거나 DRAIN checker가 120초 PENDING/PROCESSING/lease/reconciliation0을 증명하지 못한다.

---

## 10. Definition of Done

### 문서 단계

- [x] 현재 HEAD로 기준 갱신
- [x] 기존 finding의 과장·오류·stale reference 교정
- [x] 실제 desktop/mobile defect click evidence 반영; 1024×1366↔1366×1024 order-edit 회전과 1024×768 production tablet을 별도 release 계약으로 분리
- [x] 역할·상태·ownership·upload·offline·startup 결정 잠금
- [x] writer/endpoint 범위와 one-boundary PR graph 작성
- [x] persona, DB invariant, stop/rollback/deploy gate 작성
- [x] cold-start executor handoff 포함
- [x] 1024×1366 coarse portrait form predicate, source/destination cache receipt, password staged rollout 계약 잠금
- [x] public debug/ops 정보 노출, unexpected 500, broad silent catch를 owner packet+release static gate로 포함
- [x] ChannelTalk 공식 Function/Webhook transport·auth·payload schema를 current code와 교차검증하고 별도 packet/persona로 잠금

### 시스템 수정 단계

- [ ] 모든 PR에 red→green regression test
- [ ] URL-map mutation policy coverage 100%
- [ ] canonical service 밖 stage write 0
- [ ] VIEWER mutation 0, PRODUCTION 정상 command 성공
- [ ] stale full PUT 데이터 손실 0
- [ ] foreign/expired upload action 0
- [ ] user-crossing offline cache 0
- [ ] import-time DDL/DML 0
- [x] current `3c328837` changed-suite 210 passed·390px sticky nav 48..100 복구 (문서 baseline 기준; HEAD `a8e3b168`이면 BASE-00에서 재확립 — §1.4 baseline drift 주)
- [ ] SURFACE-GATE의 남은 1024 coarse portrait cohort/rotation/dirty-form 계약 green
- [ ] stored XSS sink·public debug/ops detail·known signing fallback·unexpected exception leak 0
- [ ] unclassified/silent broad catch 0, route-class body cap 100%
- [ ] single/batch cross-actor cache generation persona green
- [ ] password WARN rotation→count0→ENFORCED와 target session revoke green
- [ ] Channel live redacted Function/Webhook registration fixture, official signature/token, typed receipt/creation identity, token/raw payload log 0 green
- [ ] deploy persona matrix green
- [ ] CI green
- [ ] 사용자 승인 후에만 production 승격·검증

---

## 11. 다음 구현 에이전트용 cold-start handoff

```text
FOMS 수정 총괄 실행.

필수 시작:
1) cwd의 AGENTS.md를 완독한다.
2) docs/plans/2026-07-22-foms-full-system-bug-audit-report.md v9을 완독한다.
3) git rev-parse HEAD가 문서 기준 SHA와 같은지 확인한다. 다르면 관련 diff와 line/symbol audit부터 하고 문서 기준을 갱신한다.
4) unrelated dirty worktree는 절대 수정·stage하지 않는다.

실행 방식:
- PR graph에서 의존성이 충족된 가장 앞의 PR 하나만 선택한다.
- 그 PR의 finding을 현재 코드/브라우저에서 재현하고 실패 테스트를 먼저 추가한다.
- 문서에 잠긴 제품 계약을 임의 변경하지 않는다.
- 변경 경계, positive/negative test, persona click, DB/event invariant, perf, rollback을 모두 충족한다.
- git diff --check, 관련 pytest, perf guard를 실행한다.
- dependent PR의 구현은 현재 PR local evidence 뒤, merge/deploy는 사용자 승인 push와 remote CI green 뒤에만 진행한다. push 전에는 독립 PR의 local 분석만 허용한다.

중단:
- 문서 9절 STOP 조건이 하나라도 발생하면 추측하지 말고 evidence와 필요한 한 가지 결정만 보고한다.
- deploy push는 사용자 요청이 있을 때만 한다.
- production push/PR은 사용자 명시 승인 전 금지한다.

첫 작업:
- BASE-00으로 HEAD/current test/symbol inventory를 확인한다.
- 다음 PACKET-HARNESS-00을 먼저 끝내고 모든 후속 packet을 literal ID gate에 등록한다. API-ERROR-01→REQUEST-LIMIT-01(및 FAILOPEN-01), PROXY-01+REQUEST-LIMIT-01→WRITE-GUARD-01→PGTEST-00+OPS-APPROVAL-00 순서로 bootstrap 보안 경계를 닫는다(정확한 순서는 §5 그래프와 `foms_bugfix_packet_tests.json`의 `depends_on`이 SSOT이고 이 프로즈는 요약이다). OPS UI를 WRITE-GUARD 예외로 만들지 않고 CLI approver-ID 입력도 만들지 않는다.
- current `3c328837` local changed-suite 210 green과 browser sticky-nav 복구를 baseline으로 보존하되, **HEAD가 `a8e3b168`(문서 baseline보다 1 UI 커밋 앞)이면 BASE-00에서 5-file visual suite와 secnav geometry를 HEAD 기준으로 재확립**한 뒤(§1.4 baseline drift 주) SURFACE-GATE-01은 남은 1024 coarse portrait cohort/rotation/dirty-form red test부터 시작한다.
- 그 다음 즉시 봉쇄 PR 중 독립 가능한 MIG-WEB-RETIRE-01, FE-SYNTAX, FE-XSS, STORED-XSS-01, OPS-ROUTE-01을 하나씩 처리한다. 서명은 CUTOVER-MODE-01+SECRET-02+PGTEST-00+OPS-APPROVAL-00 뒤 STATE additive/legacy audit/READY prepare, 별도 SECRET consumer 배포 순서다. safe legacy만 BRIDGE다. known/default/short/compromised는 rescue+pending smoke를 AUTH_ONLY 전에 all-serving으로 증명한 뒤 AUTH_ONLY→30초 replica quiescence→activate→private current smoke→OFF한다. smoke 실패는 diagnosis 뒤 fixed descendant 또는 fresh NEXT roll-forward만 허용한다.
- CHANNEL-FUNCTION-CONTRACT-01은 CHANNEL-AUTH-01+REQUEST-LIMIT-01+API-ERROR-01과 redacted live method fixture 뒤, CHANNEL-WEBHOOK-AUTH-01은 PGTEST-00+REQUEST-LIMIT-01+API-ERROR-01과 redacted live registration/event fixture 뒤에만 시작한다. fixture가 없으면 DTO/event identity를 추정하지 말고 STOP한다.
- AUTH-01 이전에는 finance/state/upload endpoint를 개별 decorator로 임시 봉합하지 않는다.
- one packet=one implementation commit으로 local evidence를 만들고, PR workflow는 head SHA, production cherry-pick은 verified promotion mapping을 사용한다. Actions artifact가 없으면 exact commit reissue를 먼저 실행한다.
```

---

## 12. GSTACK REVIEW REPORT

| Review | 결과 | 반영 |
|---|---|---|
| CEO/product | 과도한 “완벽” 선언 제거, 실제 업무 손실 기준으로 우선순위 재편 | 완료 |
| Engineering | 상태 writer, permission surface, full PUT, upload, startup 범위 확대 | 완료 |
| Persona browser | SALES/DRAWING render와 VIEWER/PRODUCTION/CONSTRUCTION mutation을 격리 local에서 부분 확인 | 부분 증거 반영 완료. 전체 handoff·운영 인증 persona는 각 PR/deploy gate |
| Adversarial review | stale SHA, 잘못된 STAFF 권고, WDC line drift, offline privacy, run.py 누락 발견 | 완료 |
| Design review | 시각 디자인 변경 계획이 아니므로 별도 미실행 | 해당 없음 |
| v9 재감사 4-lens (2026-07-24, adversarial-contract·implementability·persona-journey·codebase-reality) | BLOCKER 1(OFFLINE-01↔REV-99 순환), MAJOR 3(§2.10 backfill predeploy 충돌, CHAT_SCOPE 미정의 effect_source, MEASURE 팀 누락), MINOR 다수(request_write_guard 소유 중복, signing current env 무명, ops approval seed 규정 부재, PROXY-01 파일 미지정, §8.1 신규 test owner 무pin, baseline SHA drift, P1-9 결번, 공유 NAT 로그인 러시, finding-less packet 근거, REQUEST-LIMIT 부모 모호). codebase-reality는 코어 P0/P1 line-reference 사실 오류 0 확인(baseline writer diff 0) | **전부 문서에 흡수 완료.** machine 정합 재확인: packet 124·REV-99 dep 111·cutover family 15·fence 짝수·sentinel 1 |
| 사용자 지시 (2026-07-24) | FOMS Brain(Designer/`wdplanner-v2`)은 삭제 예정 → 수정 범위 제외 | DESIGNER-AUTH-01+DESIGNER-OWNER-BACKFILL-00을 삭제 봉쇄 packet **DESIGNER-RETIRE-01**로 대체(P0-13·P0-24 근본 소멸), §2.11·§7·§8.2·persona·graph 전반 반영 |

**최종 판정:** v5~v8은 완벽하지 않았다. v9은 구현자가 다시 정책을 발명하지 않도록 제품 결정, 다축 상태 정본, 원자성, 권한, revision/idempotency, cache freshness, error/fail-open containment, PR 의존성, persona acceptance, rollback과 STOP gate를 잠갔다. **v9.1(2026-07-24)은 중단됐던 최종 재감사 루프를 4-lens로 재개해 BLOCKER 1·MAJOR 3·MINOR 다수를 흡수하고, 사용자 지시로 FOMS Brain을 수정 대상에서 삭제 대상(DESIGNER-RETIRE-01)으로 전환했다.** machine 정합(packet 124·REV-99 dep 111·cutover family 15·fence 짝수·sentinel 1)을 재확인했다. 따라서 **마스터 계획은 ready-to-go**다. 시스템 수정 완료 판정은 아직 아니다.

**남은 것은 미결정이 아니라 실행 preflight다:** 운영 secret/env 주입, 운영 데이터 read-only audit, deploy persona 계정, CI, 사용자 production 승인. 결과가 계약과 충돌하면 STOP gate가 작동한다.

NO UNRESOLVED DECISIONS
