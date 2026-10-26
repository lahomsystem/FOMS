# 마법사 "빈 초안" 정리 — 설계 (2026-10-26 승인·구현)

> 구현(2026-10-26): D1 `foms/services/order_draft_blank.py` + `upsert_draft` → `None`/`saved:false` ·
> D2 `draft.js` `markBaseline`/`_unchangedSinceOpen`(flush·keepalive) · D3 `erp-order-shared.js`
> `erpIsNewOrderWizardUrl` · D4 `location.replace` 3곳 · 시험 `tests/domains/test_wizard_blank_draft_guard.py`
> (옛 코드에서 11개 red 확인). 자산 핀 `?v=20261026b`.

작성 2026-10-26. 이어받는 곳: `docs/plans/2026-10-26-wizard-unsent-draft-reminder-spec.md` §5 범위 밖
("이름 빈 초안 22개 정리"). 관련: `2026-09-11-draft-list-and-audit-rollback-spec.md`(작성 중 목록),
`2026-10-20-wizard-push-register-safety-spec.md`(등록하고 PUSH). 초안 저장 API 를 바꾸는 코어 변경이라
승인 뒤 구현한다.

## 1. 문제

모바일 주문 마법사를 열었다 닫기만 해도 `order_drafts` 에 아무것도 안 적힌 초안 행이 생긴다. 그 행은 홈
"작성 중인 주문" 띠에 "이름 아직 없음" 카드로 7일 동안 선다. 하우드 공용 계정은 지금 열린 초안 17건 중
13건이 빈 카드다. 이어 써야 할 진짜 초안이 빈 카드 사이에 묻히고, 목록 상한(20건)을 넘기면 오래된 초안부터
목록에서 빠진다 — 2026-09-02·09-03 에 "초안은 있었는데 못 찾아서 만료" 로 잃은 것과 같은 모양이다.

## 2. 운영 실측 (2026-10-26 13:23 KST, 읽기 전용)

DB(`order_drafts`·`security_logs`)와 web HTTP 로그(배포 `63f4dacb`, 10-23~10-26)를 읽었다. 쓰기 없음.

- 미등록 초안 32건(전부 `order_id IS NULL`) = 이름 있음 9 · 이름 빔 23(앞 설계서의 30·22 에서 오늘 하나씩 늘었다).
- 이름 빈 23건은 **값이 있는 칸이 하나도 없다** — 연락처·주소·제품·규격·첨부·일정·메모·체크·금액 전부 비었거나
  화면 기본값(발주사 "라홈", 접수일 = 만든 날, 제품 칸 "상담")이다. 사진만 올린 초안도 0건.
- 21건은 `created_at`→`updated_at` 이 2.4초 안(나머지 24.7초 1건, 37.5초 1건). 22건이 1단계, 807 만 3단계.
- 작성자: 하우드(21) 13 · 백재현(50) 5 · 최진호(47) 2 · 한용희(25)·강민경(27)·정다슬(49) 각 1.
- 규모: 10-19 이후 초안 id 765~839(약 75행) 중 23행이 빈 초안(약 3할). 같은 기간 마법사 등록 47건.

빈 23건은 두 무리로 갈린다.

| 무리 | 건수 | 모양 |
|---|---|---|
| 가. 등록 직후 | 13 | 같은 사용자의 마법사 등록 7~134초 뒤에 생겼다(12건은 38초 안). 12건은 그 사이에 `CHANNEL_PUSH_SENT`·`ORDER_STRUCTURED_SAVED` 가 찍혔다 = "등록하고 실측 PUSH" → 주문 수정 화면 [저장]. 807 은 `ORDER_STRUCTURED_SAVED` 만 |
| 나. 열고 바로 나감 | 10 | 앞 3분 안에 등록이 없다. 마법사를 열고 1~2초 안에 떠났다(잘못 누름·둘러보기) |

HTTP 로그로 본 순서(로그에는 쿼리 문자열이 없다):

```
아이폰   10-25 05:27:24.99 POST /api/erp/order-draft/submit     ← 주문 5835 등록
              05:27:25.88 POST /api/channel/push-manual        ← 실측 PUSH 성공
              05:27:27.28 GET  /edit/5835                       ← (옛 코드) 성공해도 주문 수정 화면으로
              05:27:31.68 PUT  /api/orders/5835/structured      ← 수정 화면 [저장]
              05:27:32.14 GET  /add                             ← 저장 뒤 이전 화면 = 마법사를 새로 읽음
              05:27:32.91 GET  /api/erp/order-draft             ← 새 키라 초안 없음
              05:27:34.87 PUT  /api/erp/order-draft             ← 떠나며 빈 저장 = 초안 832
안드로이드 05:30:24.66 submit(5836) → 25.50 push-manual → 26.89 GET /edit/5836
              → 31.66 PUT structured → 31.84 GET /add → 32.05 GET draft → 34.05 PUT = 초안 834
정다슬   10-26 00:52:15.14 GET /erp/history/ → 15.42 GET /add → 15.80 GET draft
              → 16.66 PUT = 초안 837 → 17.08 GET /erp/dashboard
```

음성 대조군: 같은 안드로이드가 05:28:24.90 에 마법사를 열고 고객 정보를 적은 세션은 첫 PUT 이 6.7초 뒤(입력
디바운스)였다 — **페이지를 여는 것만으로는 PUT 이 나가지 않는다.** 떠날 때는 PUT 이 0.3초 안에 3~4번 겹쳐
나가는 것도 보였다(835: 15.455·15.606·15.769·16.449).

## 3. 원인 — 행이 생기는 정확한 길

### 3.1 열 때는 저장하지 않는다

- `foms/web/orders/listing.py:526` — `?key=` 가 없으면 매번 `new.<uuid16>` 새 키. 서버는 렌더만 하고 행을 만들지 않는다.
- `static/js/foms/draft.js:52-76` `load()` 는 GET 만 한다. `static/js/foms/wizard.js:1148-1345` `init()` 은 리스너만
  걸고 저장을 부르지 않는다. 입력 이벤트를 쏘는 보조 스크립트(`wizard-enrich.js` 주소·연락처·시간 콤보)도 사용자
  동작 때만 쏜다.

### 3.2 떠날 때 내용과 상관없이 저장한다 — 세 갈래

화면 기본값(접수일 오늘·발주사 라홈·제품 칸 "상담")이 담긴 payload 를 **무조건** PUT 한다. 바뀐 게 있는지 보는
곳이 없다.

1. X 닫기 — `wizard.js:1450` `draftClient.flush().finally(...)`.
2. 칸에서 포커스가 빠질 때 — `draft.js:197-202` blur → `flush()`. 안드로이드는 진입 즉시 첫 칸에 포커스를 주므로
   (`wizard.js:1205-1207`, 아이폰 제외) 화면 아무 데나 누르거나 X 를 누르면 blur 가 먼저 PUT 을 쏜다.
3. 화면을 벗어날 때 — `draft.js:206-248` `keepaliveSave` 가 `beforeunload`·`pagehide`·`visibilitychange(hidden)`
   에 걸려 있다. 뒤로 가기·앱 전환·화면 잠금 모두 해당.

디바운스(`draft.js:154-167`)와 5분 대기 저장(`:169-177`)은 입력이 있어야만 걸린다.

### 3.3 서버는 빈 내용도 새 행으로 넣는다

`PUT /api/erp/order-draft`(`foms/api/erp_order_draft.py:361-426`) → `upsert_draft`
(`foms/services/order_draft_service.py:256-306`) → 행이 없으면 `_insert_or_recover_draft`(`:211-253`)가 INSERT.
`validate_draft_payload`(`:97-110`)는 모양(`schema_version`·`step`·`data`)만 본다.

### 3.4 빈 마법사가 다시 열리는 길 (무리 가, 13건)

- 옛 `wizard-send.js` 는 "등록하고 실측 PUSH" 가 성공해도 `/edit/<id>` 로 갔다. 오늘 `5caa688db`(운영 10-26
  12:01 KST)부터 성공은 대시보드로 간다(`static/js/foms/wizard-send.js:491-497`·`:570`). PUSH 실패 두 갈래는
  지금도 `goToOrder` → `/edit/<id>`(`:505-509`·`:578`·`:586`).
- 주문 수정 화면에서 [저장] 하면, ERP 주문은 숨은 `referrer` 칸이 없어
  (`templates/orders/partials/edit_order_body.html:102-108` 은 ERP 가 아닐 때만 그린다) `document.referrer`
  로 돌아간다(`static/js/orders/erp-order-shared.js:3120-3122`). 그 값이 마법사 주소(`/add…`)라서
  `erpNavigateAfterStructuredSave`(`:2628-2667`)가 `history.back()` 이나 `location.href` 로 **마법사를 다시
  연다**. 로그상 마법사 주소를 새로 읽었다(위 표) → 새 키 → 사용자는 영문 모를 빈 마법사를 보고 떠난다 → 3.2 →
  빈 행.
- 모바일 셸 [뒤로] 버튼(`static/js/runtime/erp-mobile-shell.js:57-59` `history.back()`)도 같은 마법사로
  돌아간다(로그 근거는 없고 코드상 같은 결과).

### 3.5 같은 키 되살림 (807)

807 은 방금 등록된 초안과 **같은 키**로 3단계 빈 행이 31초 뒤 다시 생겼다(그 등록은 한 초안이 주문 5814·5815
두 건으로 저장된 건으로, 10-22 `c9078f9da` 에서 고쳤다). 홈 이어쓰기 링크(`/add?key=…&wizard=1&step=3`,
`static/js/foms/draft_resume.js:180-181`)로 들어온 마법사였다고 본다: 수정 화면 저장 → 같은 주소로 돌아감 → 키가
같으니 `load()` 는 비어 있음 → 떠날 때 빈 PUT 이 그 키로 INSERT. 등록 뒤 저장을 끄는 표시(`draft.js:35-40`
`_submitted`)는 새로 읽힌 페이지에는 없다.

### 3.6 (함께 막을 구멍) 이어쓰기 화면에서 [복구] 를 안 누르고 나가면 덮어쓴다

이어쓰기 링크로 들어오면 빈 화면 + "이전에 작성하던 내용이 있습니다 [복구]" 토스트가 뜬다(`wizard.js:1345-1364`).
[복구] 를 누르기 전에 X·뒤로·blur 가 나면 3.2 의 빈 payload 가 서버 행을 **빈 내용으로 덮는다**. `load()` 가
`updatedAt` 을 채워 두므로 `X-If-Match` 도 맞아 충돌 창도 안 뜬다. 운영 빈 23건에는 이 흔적(오래전에 만든 행이
빈 내용으로 바뀐 것)이 없지만 코드상 열려 있는 유실 길이다. 빈 초안을 만드는 것과 같은 저장 길이라 같이 막는다.

## 4. 사용자 눈에 보이는 곳

- 홈 "작성 중인 주문 N건" 띠 — 타워·큐 두 화면 모두(`templates/orders/partials/draft_resume_bar.html` ←
  `dashboard_mobile_tower.html:12`·`dashboard_mobile_v2_body.html:50`). 목록 API
  `GET /api/erp/order-draft/list`(`erp_order_draft.py:340-358`) → `list_open_drafts`(`order_draft_service.py:128-169`)
  는 내용을 보지 않는다. `_draft_list_row`(`erp_order_draft.py:290-337`)가 `customer_name: None` 을 주면 카드는
  "이름 아직 없음 · 단계 1/4 · 10-25 14:27 저장 · 만료까지 6일"(`draft_resume.js:185`·`:193-201`), 건수에도
  들어간다(`:94`). **빈 카드가 실제로 목록에 선다.**
- 목록은 최신순 20건 상한(`order_draft_service.py:132`·`:166`). 하우드는 지금 17건(빈 13). 4건만 더 쌓이면
  상한을 넘고, 그때부터 가장 오래된 초안부터 목록에서 빠진다 — 오래 묵은 진짜 초안이 먼저 안 보이게 된다.
- 빈 카드를 누르면 빈 마법사 + "이전에 작성하던 내용이 있습니다" 토스트가 뜬다(복구해도 빈 칸).
- 관리자 "발송 후 미등록" 화면(`foms/web/admin/sent_unregistered_drafts.py:67-69`)은 발송 기록이 있는 초안만,
  미등록 알림(`foms/services/notifications/draft_send_reminder.py:326-329`)은 이름·연락처가 있는 초안만 본다 —
  빈 초안은 거기에는 안 보인다.

## 5. "비었지만 버리면 안 되는" 초안

지금 운영에는 0건이지만 구조상 생길 수 있다. 이름은 비었어도 아래 중 하나라도 있으면 진짜 작업이다.

- **첨부 사진** — 업로드(`POST /api/erp/order-draft/attachments`, `erp_order_draft.py:522-579`)는 행을 만들지
  않고 R2 에 올린 뒤 `tmp_key` 만 돌려준다. 그 키는 다음 자동저장의 `data.items[].attachments` 에만 적힌다
  (`static/js/foms/wizard-attachments.js:173-177` → `scheduleSave`). 사진부터 찍고 이름은 나중에 적는 흐름이 된다.
- 연락처만, 주소만(주소 검색 결과), 제품명·규격·금액, 일정·담당·메모, 지방/긴급 체크, 계약금.

그래서 판정은 "이름이 있나" 가 아니라 **"값이 하나라도 있나"** 다(§6). 미등록 알림의 "이름+연락처" 기준과는
다르다 — 알림은 사람을 부를 만한가의 기준이고, 이것은 저장할 가치가 있는가의 기준이다.

## 6. "빈 초안" 판정 정의

payload 의 `data` 를 끝까지 훑어 **값이 하나도 없으면** 빈 것이다. 값이란:

- 앞뒤 공백을 뺀 글자가 1자 이상인 문자열 — 단 아래 화면 기본값과 같으면 값이 아니다.
- `true` 인 체크, 0 이 아닌 숫자.
- 첨부 목록의 항목(안의 `tmp_key` 문자열이 값이므로 저절로 걸린다).

기본값 예외는 이것뿐이고 늘리지 않는다.

| 칸 | 값으로 치지 않는 것 | 근거 |
|---|---|---|
| `orderer` | `"라홈"` | `templates/orders/wizard/step1_basic.html:30` 숨은 기본값 |
| `received_date` | 오늘(KST) | `step1_basic.html:44` `value="{{ today }}"` |
| `items[].internal·color·handle·option_detail·misc` | `"상담"` | `step2_products.html:48-66` |
| `deposit` | 숫자만 남겨 0 | 계약금 칸 |

- **모르는 칸**(앞으로 생길 칸 포함)도 같은 규칙: 값이 있으면 빈 것이 아니다. 판정이 칸 목록을 못 따라가도
  **저장하는 쪽으로** 틀린다.
- 제품 카드 수·규격 행 수·단계(`step`)는 보지 않는다. 빈 카드 2장에는 정보가 없다.
- 기본값과 똑같은 글자를 사용자가 직접 적었으면(예: 색상에 "상담") 빈 것으로 본다 — 잃는 정보가 없다.
- 자정 경계: 어제 연 화면을 오늘 저장하면 접수일이 오늘과 달라 값으로 친다 → 빈 행이 드물게 생긴다(안전한 쪽).
- 발송 기록(`send_history`)은 payload 밖 서버 칸이라 판정에 넣지 않는다. 발송하려면 연락처가 있어야 하므로 그
  전에 이미 값이 있다.

## 7. 결정할 것과 제안

### 7.1 안 비교

| | 안 A — 값이 없으면 행을 안 만든다 | 안 B — 만들고 목록에서 숨긴다 | 안 C — 빈 초안만 짧은 수명 |
|---|---|---|---|
| 하는 일 | 서버: 행이 없고 빈 payload 면 INSERT 안 함. 화면: 연 그대로면 PUT 안 함 | `list_open_drafts` 가 빈 초안을 거름 | upsert 때 빈 payload 면 `expires_at` = 1시간 뒤, 값이 생기면 7일 |
| 빈 행 | 안 생김 | 계속 생김(7일) | 생겼다가 다음 정리 때 지워짐 |
| 홈 빈 카드 | 없음 | 없음 | 1시간 동안 보임(B 를 같이 해야 없음) |
| 상한 20 밀어내기 | 없음 | SQL 에서 거르지 않으면 남음(JSON 판정을 SQL 로 — SQLite·PG 차이) | 1시간 동안 남음 |
| 3.6 덮어쓰기 | 화면 가드가 막음 | 못 막음 | 못 막음 |
| 판정이 틀렸을 때 | 그 입력이 저장 안 됨 | 진짜 초안이 목록에서 사라짐 → 못 찾고 만료 | 진짜 초안이 1시간 뒤 지워짐 |
| 바꾸는 곳 | 서비스·API·`draft.js`·`wizard.js` | 서비스(+SQL) | 서비스 |

- B·C 가 틀렸을 때의 모양은 2026-09-02·09-03 유실과 같다(초안은 있었는데 사용자가 못 찾았거나 조용히 사라졌다).
  A 가 틀렸을 때는 "기본값과 같은 글자만 있는 입력이 저장 안 됨" 뿐이고, §6 규칙상 그 입력에는 정보가 없다.
- **거절: 저장 늦추기** — "이름·연락처가 다 차야 저장", "[다음] 누를 때만 저장", "처음 N초는 저장 안 함".
  사진만·주소만 적은 초안, 적다가 전화 받으러 나간 초안이 사라진다. 2026-09 유실 대책(keepalive·목록)을 거꾸로
  되돌리는 일이다.

### 7.2 추천 — 안 A + 되돌아가는 길 막기

D1. **서버 가드(필수)** — `upsert_draft` 는 그 사용자·키의 행이 **없고** payload 가 §6 의 빈 것이면 INSERT 하지
않는다. 응답은 `200 {"success": true, "saved": false, "updated_at": "", "step": n}` — 실패가 아니므로 화면은
오프라인 큐에 넣지 않고, 4단계 발송의 강제 저장(`wizard-send.js` `flushDraft`)도 성공으로 받는다.
**행이 이미 있으면 빈 payload 라도 지금처럼 고친다** — 사용자가 일부러 다 지운 것일 수 있고, 서버가 그 뜻을
뒤집으면 원인 추적이 어려워진다. 폰에 남은 옛 JS(자산 캐시 최대 1일)·오프라인 큐 재전송도 이 가드를 똑같이 탄다.
807 같은 같은 키 되살림(3.5)도 여기서 막힌다.

D2. **화면 가드(필수)** — `draft.js` 는 "마법사를 연 뒤 화면 내용이 그대로이고 [복구] 도 안 눌렀으면" 저장
요청을 보내지 않는다. 기준은 `init()` 끝에서 찍은 `buildPayload().data` 사본과의 비교다(칸별 기본값을 알 필요가
없다). 이 가드가 3.6 덮어쓰기를 막는다. `flush`·`keepaliveSave` 두 진입점에 `_submitted` 가드와 같은 자리로
건다. 건너뛴 `flush` 는 `true` 로 끝낸다(보낼 것이 없음 = 서버와 같음). "✓ 자동저장됨" 은 실제로 저장됐을 때만
띄운다(건너뜀·`saved: false` 면 안 띄움).
- 기준을 찍은 뒤 다른 스크립트가 칸을 바꾸면 "바뀜" 으로 보고 저장한다 — 틀려도 지금 동작(저장)으로 틀린다.
- [복구]·충돌 해결(`applyRemote`)을 거치면 이 가드는 꺼진다.

D3. **수정 화면 저장 뒤 마법사로 돌아가지 않기(필수)** — `erp-order-shared.js:3120-3121` 에서 돌아갈 곳의 경로가
`/add` 이면 `/erp/dashboard`(+`focus_order`)로 바꾼다. 방금 저장한 주문을 두고 "새 주문" 화면으로 돌려보내는 일은
어느 경우에도 맞지 않다. 무리 가 13건의 직접 원인이고, 가드 뒤에도 남는 화면 혼란(등록했는데 빈 새 주문 화면이
다시 뜸)을 없앤다.

D4. **등록이 끝난 마법사는 방문 기록에서 뺀다(권장, 같은 커밋)** — 등록 성공 뒤 이동 3곳(`wizard.js:1133`,
`wizard-send.js:495`·`:507`)을 `location.replace` 로 바꾼다. 셸 [뒤로]·브라우저 뒤로 가기로 끝난 마법사에 다시
들어가지 않는다. 등록 실패 때는 이동이 없으니 그대로다.

D5. **이미 쌓인 빈 초안 23건은 손대지 않는다** — `new.*` 수명 7일이라 가장 늦은 837 도 11-02 에 만료되고 정리
cron 이 지운다. 운영 쓰기가 필요 없다.

## 8. 만들 것

- `foms/services/order_draft_blank.py`(새 파일) — `is_blank_draft_data(data, *, today_kst) -> bool`.
  `order_draft_service.py` 는 이미 420줄이라 여기에 넣으면 파이썬 500줄 래칫
  (`tests/harness/test_file_size_ratchet.py`)에 걸릴 수 있다.
- `order_draft_service.upsert_draft` — 행이 없고 빈 것이면 `None` 을 돌려준다(행 있는 경로·경합 복구 경로는
  그대로). 오늘 날짜는 `get_today_kst()`(CI 는 UTC 라 `date.today()` 금지).
- `erp_order_draft.api_put_order_draft` — `None` 이면 `saved: false` 응답, 저장했으면 `saved: true` 를 함께 준다.
- `static/js/foms/draft.js` — 기준 사본 찍기(`markBaseline()`), `_remoteApplied`, `flush`·`keepaliveSave` 가드,
  `saved === false` 처리. 래칫 기준선 안의 기존 큰 파일이라 새 파일로 쪼개지 않는다.
- `static/js/foms/wizard.js` — `init()` 끝(리스너·기본값 정리 뒤, `load()` 결과 전)에서 `draftClient.markBaseline()`.
  D4 의 `location.replace`.
- `static/js/foms/wizard-send.js` — D4 의 `location.replace` 2곳.
- `static/js/orders/erp-order-shared.js` — D3.
- 자산 핀 올리기: `wizard_shell.html:86·95·96` 의 `?v=`, `erp-order-shared.js` 를 싣는 조각들의 `?v=`.
- 기존 시험 1곳: `tests/domains/test_erp_order_draft_wizard.py:156` 는 빈 payload 로 PUT 한 뒤 지우기를 본다.
  가드 뒤에는 아무것도 안 지우는 시험이 되므로 이름 한 칸을 넣는다(다른 초안 시험은 값을 넣거나 ORM 으로 직접
  만들어 영향 없음).
- 하네스 인벤토리 줄 번호(`docs/harness/*_inventory.json`)가 밀리면 갱신해 같이 커밋한다.

## 9. 테스트

서버(pytest, 새 `tests/domains/test_wizard_blank_draft_guard.py`):

1. 마법사 기본 모양(라홈·오늘·카드 1장 "상담")으로 PUT, 행 없음 → 200·`saved: false`·`order_drafts` 0행·목록 API 0건.
2. 양성 대조(파라미터화) — 고객명·연락처·주소·발주사≠라홈·접수일≠오늘·제품명·규격 가로·색상≠상담·금액·추가 입력·
   첨부 1개·일정 칸 각각·담당 각각·메모·체크 3종·지방 구분·긴급 사유·계약금: **한 칸만** 바꿔도 행이 생긴다.
   칸 목록을 `wizard.js` `collectBasic`·`collectProducts`·`collectSchedule`·`collectFlags` 와 대조해 빠진 칸이
   있으면 red(소스 계약).
3. 모르는 칸 — `data.new_field="x"`, `items[0].new_field="x"` → 행이 생긴다.
4. 행이 있는데 빈 payload → 지금처럼 고쳐진다(가드가 갱신을 막지 않음).
5. 빈 PUT → 값 있는 PUT(같은 키) → 두 번째에 행이 생기고 `updated_at` 이 온다.
6. 빈 PUT 만 한 키로 submit(body payload 에 값) → 주문이 만들어진다(등록은 행과 무관, `erp_order_draft.py:686-694`).
7. 등록 성공 뒤 같은 키로 빈 PUT → 행이 되살아나지 않는다(807 회귀).
8. 접수일 = 어제 → 값으로 쳐서 행이 생긴다(자정 경계, 안전한 쪽을 문서로 남김).
9. 기존 경합 복구 시험(`tests/domains/test_order_draft_model.py:194`)이 그대로 통과.

화면(node 하네스 — `tests/domains/test_wizard_draft_submit_stops_autosave.py` 처럼 fetch 를 센다):

10. 새 마법사, 손대지 않음 → blur·X(`flush`)·`pagehide`·`visibilitychange`·`beforeunload` 모두 PUT 0회.
11. 한 글자 입력 → 1000ms 뒤 PUT 1회(지금과 같은 시점 — 늦어지지 않음).
12. 한 글자 입력 직후(디바운스 전) `pagehide` → keepalive PUT 1회(2026-09 유실 대책 회귀).
13. 사진 첨부 콜백만 → PUT 1회, 본문에 `attachments`.
14. 이어쓰기: `load()` 가 행을 돌려줌, 손대지 않음 → X·`pagehide` PUT 0회(3.6 덮어쓰기 차단).
15. 이어쓰기 + [복구] → 이후 저장이 막히지 않는다. 손대지 않고 발송 강제 저장(`flush()`) → `true`.
16. 건너뛴 `flush()` 는 `true` 로 끝나고 "자동저장됨" 을 띄우지 않는다. 서버 `saved: false` 응답도 같다.
17. 손댔다가 되돌림 — 행 없음이면 저장 안 함, 이미 한 번 저장된 뒤면 저장함.

이동(D3·D4):

18. 수정 화면 저장, referrer `/add`·`/add?key=new.x&wizard=1&step=3` → `/erp/dashboard?focus_order=<id>`.
19. 음성 대조 — referrer `/erp/dashboard?…`·`/erp/measurement` 는 지금처럼(`history.back()`·`focus_order`).
20. 마법사 등록 성공·PUSH 성공·PUSH 실패 이동이 `location.replace` 다(소스 계약).

마무리: `scripts/ops/pre_push_smoke.ps1` exit 0, 고친 JS 4개 `node --check`, `python -c "import app; print('APP_OK')"`.
스테이징 실화면(안드로이드·아이폰): 마법사 열고 X → `order_drafts` 0행 / 이름 한 글자 → 1행 / 이어쓰기 열고
[복구] 없이 X → 행 내용 그대로 / 등록하고 PUSH 실패 → 수정 화면 [저장] → 대시보드.

## 10. 범위 밖

- 이미 쌓인 빈 초안 23건 — D5(수명으로 저절로 지워짐).
- 이어쓰기 링크로 들어오면 토스트 대신 바로 복구하는 화면 변경 — 덮어쓰기만 막고 화면은 그대로 둔다.
- 정리 cron(`tools/cron/cleanup_order_drafts.py:113-116`)은 만료 초안을 지울 때 그 첨부(R2 `order-drafts/…`)를
  안 지운다(목록 [지우기]는 지운다, `erp_order_draft.py:462-489`). 사진만 있는 초안이 만료되면 R2 에 고아 파일이
  남는다 — 별건.
- (발견만) `_draft_list_row` 의 `has_send_history` 식(`erp_order_draft.py:333-336`)은 `and`·`or` 우선순위 때문에
  dict 가 아닌 값이 섞이면 예외가 난다. 지금은 서버만 dict 를 쓰므로 터지지 않는다 — 별건.
- 데스크톱 `/add`(마법사가 아닌 폼) 자동저장이 만드는 `orders.status='DRAFT'` 껍데기 — 다른 체계.

## 11. 위험 — 유실 사고 이력과 견주기

- **저장을 늦추는가 — 아니다.** 디바운스 1초·blur·keepalive·5분 대기 신호는 그대로다. 막는 것은 "보낼 값이 없는
  저장" 뿐이고, 값이 한 글자라도 생기면 지금과 같은 시점에 나간다(시험 11·12).
- **2026-09-02·09-03(초안은 있었는데 못 찾고 만료)** — 안 A 는 목록에서 아무것도 숨기지 않는다. 오히려 빈 카드가
  사라져 진짜 초안이 상한 20 밖으로 밀리는 길이 없어진다. B·C 를 고르지 않은 이유다.
- **2026-09-10(발송 뒤 미등록·등록 실패 무음)** — 등록은 body payload 로 하고 행이 없어도 된다
  (`erp_order_draft.py:686-694`). 발송은 강제 저장 성공을 전제로 하는데, 발송에는 연락처가 있어야 하므로 그 저장은
  가드에 걸리지 않는다. 건너뛴 저장도 `true` 라 발송이 "굳히기 실패" 로 멈추지 않는다(시험 15·16). 등록 실패 알림
  (`wizard.js:1112-1146`)은 건드리지 않는다.
- **판정이 틀릴 위험** — 값 기준·모르는 칸은 값·기본값 예외 4개뿐이라, 틀려도 잃는 것은 기본값과 같은 글자다.
  화면 가드는 기본값 목록 없이 "연 그대로인가" 만 보므로 서버 판정과 어긋나도 저장하는 쪽으로 틀린다.
- **사진만 올린 초안** — 첨부 1개면 값이다. 업로드 콜백이 `scheduleSave` 를 부르는 길은 그대로다. (업로드 뒤
  저장 전에 앱이 죽으면 R2 에만 남는 것은 지금도 같다.)
- **3.6 덮어쓰기** — 지금 열려 있는 유실 길을 이번에 닫는다. 폰에 남은 옛 JS 는 캐시가 바뀔 때까지(최대 1일)
  덮어쓸 수 있다. 빈 행을 새로 만드는 것은 서버 가드가 옛 JS 도 막는다.
- **이동 변경(D3·D4)** — PUSH 실패 때는 여전히 주문 화면으로 간다(다시 보내야 하므로). 바뀌는 것은 저장·뒤로
  가기 뒤 도착지뿐이다.
- 성능: 새 쿼리 없음. 판정은 이미 받은 payload 를 파이썬에서 훑을 뿐이다.
