# findings_w3 — 축 D(존재·권리) · E(통제·감사 추적)

- 워커: w3 · 작성 2026-09-05 02:05 UTC(KST 오늘 고정 2026-09-04) · 워크트리 `C:/tmp/foms-s-settle-cfo`(HEAD 7100e2aa1) · OUT = `…/scratchpad/cfo`
- 접속: 스테이징 API(requests, 로그인 세션 1 + 비로그인 세션 1, 2026-09-04 07:42 UTC — 재개 시 재호출 없음) · 스테이징 DB readonly 배치 2회(`w3_staging_batch.py`, `w3_staging_followup.py`) · **운영 DB readonly 배치 1회**(`w3_production_batch.py`, 02:02:07~02:02:47 UTC, 재실행 없음, 문장별 SAVEPOINT 전부 성공)
- 규율: 워크트리 무편집·git 무사용·POST /sync 미호출·[지금 동기화]/[받아오기] 미클릭·비밀 원문 미기록(해시 대조 True/False 만).

## 1. 축별 판정

| 축 | 판정 | 근거 한 줄 |
|---|---|---|
| D 존재·권리 | **WARN** | 운영 미매칭 정산액 **1,480,447,006원**(그중 네이버가 이미 지급 완료 1,471,504,974원·90일 초과 981,133,199원)이 화면 어디에도 금액으로 없다(KPI 는 건수만, 커널 653~681). 예외 큐 상한 50 에 NEGATIVE·LIMIT 총수 침묵(883~898). 매칭 건 정산액≠출고가 대조 기능 0(settlement_rows.py:149·210, 예외 kind 7종에 금액차 없음). |
| E 통제·감사 | **WARN** | 권한(E-1)·마스킹(E-3)·쓰기 경로(E-4) 는 PASS. 그러나 **운영 `claude_master`(id 57) 비밀번호가 2026-09-02 노출본과 여전히 일치(해시 대조 True)** — 잠금(is_active=false)이 완화 요인. 동기화 요청 감사 행에 실효 구간·run 연결키 없음(API 316~324). |

## 2. 발견 목록

### W3-D-01 · WARN · 존재 · 미매칭 정산 채권이 화면에 금액으로 없다(건수만)
- **현상**: KPI 는 `unmatched_count`·`unmatched_pending_count`·`unmatched_unlinked_count` 건수 3개뿐(`foms/services/settlement_channel.py:653~681 _kpi_block`), 예외 큐 문구도 건수(`static/js/settlement/channel.js:1993~1997`). 회계팀은 "붙지 않은 돈이 얼마인가·얼마나 오래됐나"를 화면에서 알 수 없다.
- **실측(운영, `w3_production.json`)**: `d1_status_linked` — UNMATCHED 링크 없음 2,889건/2,911행 expect 978,573,922원(전부 완료), UNMATCHED 링크 있음(워크벤치 대기) 1,338건/1,346행 expect 501,873,084원(완료 492,931,052원). 합계 **1,480,447,006원**(`d1_status_all_types`), 이 중 `settle_complete_date` 있는 행 1,471,504,974원 = 네이버는 지급했는데 FOMS 주문·매출과 대사 불가.
  - aging(정산 예정일, 기준 2026-09-04, `d1_aging_unmatched`): <30일 408건 146,066,928원 · 30~59일 486건 188,744,096원 · 60~89일 440건 164,502,783원 · **90일+ 2,894건 981,133,199원** · 미래 예정 24행 8,942,032원.
  - 기본 창(08-05~09-18) 미매칭 503행/501건 174,032,747원(`d1_unmatched_window_default`) — 화면은 이 창에서 "482건"(API 07:42 UTC) 만 말한다.
  - 붙일 수 있는 비율(`d1_attachable`·`d1_attachable_amount`): 미매칭 4,227건 중 링크 있음 1,338건(31.7%). 전화(수령인·주문자, 활성 주문 `orders.phone`/`erp_phone_digits`) 일치 918건 = 링크 있는 건의 **68.6%**, 전체의 21.7%, 금액 **343,095,791원**(23.2%). 이름 일치 3,130건(74.0%)은 동명이인 오탐 포함이라 근거로 쓰지 않는다. 링크 없는 2,889건은 전화·수령인 정보 자체가 없어(수집 전 주문) 화면만으로는 붙일 수단이 없다.
- **스테이징 대조(`w3_staging_batch.json`)**: UNMATCHED 6,300행 2,096,577,850원, 90일+ 4,916건 1,597,697,768원, 링크 있음 1,378건 중 전화 일치 461건(33.5%) — 분포 형태 동일.
- **음성 대조군**: MATCHED 행에 같은 전화 술어 → 운영 11/11·스테이징 3/3 일치(술어 생존, `d1_attachable_control_matched`). 링크 없는 행의 전화 일치 0건(`unlinked_phone_hit_should_be_0`=0, 술어가 없는 정보를 만들어내지 않음).
- **재무 영향(실측)**: 운영 1,480,447,006원 미대사 채권, 90일 초과 981,133,199원.
- **권고(근본)**: 예외 큐 머리에 "FOMS 미연결 정산액 = settle_expect_amount **원값 합**(완료분/미완료분) + 30/60/90일 구간" 한 줄. 재집계·다른 축 아님(`_build_case_stats` 609 의 group-by 에 `sum(settle_expect_amount)` 와 aging CASE 를 붙이면 질의 추가 0). 노력 **S~M**.

### W3-D-02 · WARN · 완전성 · 예외 큐 상한(50)에 잘린 kind 의 전체 수를 화면·API 가 말하지 않는다
- **코드**: `_daily_exceptions` 883~898 은 HOLDBACK·LIMIT·NEGATIVE 세 종류를 **합쳐** `found[:_EXCEPTION_CAP]`(50, 상수 112) — NEGATIVE·LIMIT 의 전체 건수는 응답 어디에도 없다(HOLDBACK 만 `holdback.count`). `_unmatched_rows` 901~912 는 갈래별 `limit(50)`, 총수는 KPI 가 말한다. 프론트 문구 `channel.js:1997` "표에는 갈래마다 최근 것부터 상한까지만 실립니다." — 상한 숫자(50)도 "N건 중 M건"도 없다. 응답 `exceptions` 원소 키는 `action_url·age_days·amount·date·kind·label·ref` 뿐, 최상위에 총수·잘림 표식 키 없음(`w3_exceptions_kinds.json` `exception_meta_keys`·`top_level_truncation_keys`).
- **실측(스테이징 API, 창 2026-01-01~09-18, `w3_api_exceptions.json` → `w3_exceptions_kinds.json`)**: exceptions 125건 = UNMATCHED 50 + UNLINKED 50 + HOLDBACK 25 vs KPI pending 1,357·unlinked 2,879·holdback.count 25 → 표에는 4,236건 중 100건. 운영 DB 같은 창(`d2_unmatched_counts_wide`) pending 1,346·unlinked 2,911 → 4,257건 중 100건.
- **침묵 kind 현황**: NEGATIVE·LIMIT 는 스테이징·운영 모두 창 안 0건(`daily_exception_kinds_*`, `d2_daily_exception_kinds_wide` = holdback 25·limit 0·negative 0 / 160행), 스테이징 전기간 negative 1건(2025년). 세 종류 합 25 < 50 이라 **지금은 잘리지 않는다** — 구조적 결함, 현재 재무 영향 0.
- **음성 대조군**: 창 09-01~09-18 → UNMATCHED 42 = KPI 42(상한 미발동, `w3_api_exceptions_narrow.json`).
- **화면 근거**: W4 `w4_exceptions_header.png` 는 OUT 에 없음 → 소스(channel.js:1997)+API 로 판정, 화면 결함으로 쓰지 않는다.
- **권고**: 응답에 kind 별 `total`(count 질의 1회, `_case_scope` 재사용) + 문구 "N건 중 50건 표시". 노력 **S**.

### W3-D-03 · WARN · 정확성/존재 · 매칭 건의 정산액≠출고가를 화면이 예외로 내지 않는다
- **코드**: 예외 kind 는 HOLDBACK·LIMIT·NEGATIVE·UNMATCHED·UNLINKED·RETRO·COUNT_MISMATCH 7종(883~968) — 금액 차 kind 없음. `foms/services/settlement_rows.py:149 _naver_settle_map` 반환 필드 `status·settle_expect_date·settle_complete_date·amount(settle_expect_amount 원값 합)`, `:210 _naver_settlement_cell` 도 동일 — 출고가 대비 차이 필드 없음.
- **실측(스테이징, `w3_match_diff.py` → `w3_match_diff_staging.json`, 출고가 = `erp_shipping_price_from_structured`, `foms/services/erp_display.py:297`)**: 매칭 주문 2건 — 일치 표본 #4461 출고가 12,680 = pay 12,680(expect 11,840 은 수수료 차감 후라 정상) · 불일치 표본 #4242 출고가 **0**(품목 미입력·상태 DRAWING) vs pay 2,830,000 / expect 2,698,971 → 차 2,830,000원, 취소 아님(settle_type 전부 NORMAL_SETTLE_ORIGINAL). 회계팀은 이 불일치를 화면에서 알 수 없다.
- **운영(SQL 집계만, `d3_matched_sql`·`d3_matched_orders_exist`)**: 매칭 3주문·11행, pay 2,438,770·expect 2,277,086, 취소 포함 주문 0, 완료 행 있는 주문 1, 주문 존재 3/3·삭제 0. 출고가 대조는 규율상 운영 미실시(표본 차이: 스테이징 2주문 vs 운영 3주문).
- **음성 대조군**: 일치 1건(#4461) 확보. **부분 취소 불일치 표본은 스테이징·운영 모두 0**(has_cancel 0) → 취소 차액 대조군 미확보(확인 못 한 항목).
- **재무 영향(실측)**: 스테이징 불일치 절대합 2,830,000원(1건). 운영은 표본 3건이라 추정 불가 — 매칭이 늘수록 비례.
- **권고**: `결정 재고` 절 참조 — 매칭 행에 `pay_settle_amount` 와 출고가를 **나란히 원값으로** 두고 다르면 예외 kind(예 AMOUNT_DIFF). 재계산 금지(D-4)와 충돌하지 않는다(두 원값 병기, 차는 파생 표시). 노력 **M**.

### W3-E-02 · WARN · 완전성(추적성) · 동기화 요청 감사 행에 실효 구간·run 연결키가 없다
- **코드**: `foms/api/cs/settlement_channel.py:316~324` `log_access("네이버 정산 동기화 요청…", user.id, action=NAVER_SETTLE_SYNC_REQUEST, target_type="settlement_channel", detail={queued, backfill_from, channel})` — 행위자 O, 실효 from/to X, job/run id X. 실행 쪽 `naver_settle_sync_runs.scope{from,to,…}`·`actor_user_id` 와는 시각·행위자로만 느슨히 연결. `_log_export` 355~381 은 행위자·kind·channel·from·to·basis(실효 축) O, 행수 X(의도: 응답 전 기록). 라벨 `foms/services/audit_message_display.py:174~175` 두 코드 등재.
- **실측**: 스테이징 `e2_actions` — EXPORT 22행·SYNC 3행, 행위자 NULL 0. `e2_sync_recent` 3행 user 38, detail `{queued:true, backfill_from:'2025-10-01'|null, channel}`. 운영 `e2_actions` — EXPORT 5행·SYNC 4행, 행위자 NULL 0. 양성 표본: 내 export(07:42:53.318 UTC) = `security_logs.id 26585`, user_id 58, kind settle_daily, basis expect, from 2026-08-05, to 2026-09-18(`w3_staging_batch.json` `e2_rows_after_pre_max`).
- **음성 대조군**: 사전 max id 26582 이후 내 GET 5회(page·strip·full·exceptions×2, 07:42:51~53) 사이 행은 LOGIN_OK(26583·26584) 뿐, export 뒤 strip GET(07:42:53.12) 도 행 없음 → 조회는 감사 행을 남기지 않는다. 400 응답(kind=daily&type=X) 도 행 없음.
- **재무 영향**: 없음(추적성). 권고: sync 감사 detail 에 큐 job id(고정 `naver_settle_sync`)와 요청 시 계산된 기본 창, 또는 워커가 run 시작 시 감사 행 id 를 `sync_runs.scope` 에 역기록. 노력 **S**.

### W3-E-05 · WARN · 존재(통제) · 운영 측정 계정 비밀번호가 노출(2026-09-02) 이후 로테이션되지 않았다
- **실측(운영 배치 `e5_user`)**: `users` 1행 id 57 · role ADMIN · **is_active=false**(기본 잠금 유지) · 해시 pbkdf2:sha256:600000 · `check_password_hash(row.password, secrets.production.password)` = **True** · 틀린 문자열 대조 False(음성 대조군). 비밀번호 관련 action 2026-08-25 이후 0행, 이 사용자를 대상으로 한 감사 행 2026-09-01 이후 0행, LOGIN_OK 20행(측정 세션).
- **스테이징(`e5_user`)**: id 58 · ADMIN · is_active true · 대조 True · 틀린 문자열 False · 비밀번호 변경 행 0(스테이징 비번은 노출 대상이 아니었으므로 참고).
- **완화 요인**: 운영은 잠금 상태라 로그인 자체가 막혀 있다(해제→측정→재잠금 절차). 그러나 해제 창마다 노출본이 그대로 쓰인다.
- **재무 영향**: 직접 금액 없음(운영 ADMIN 자격증명 노출 잔존). 권고: 운영 비번 로테이션 + secrets 파일 갱신 + 로테이션을 감사 행(USER_PASSWORD_CHANGED 류)으로 남기기. 노력 **S**.

## 3. PASS 축 근거(음성 대조군 포함)

### E-1 권한 — PASS
- 실측(a) 로그인 세션(`w3_api_log.json`): `GET /erp/settlement` 200, 본문에 `data-settlement-ch-root`·`data-settlement-tab="channel"` 있음; `GET /api/settlement/channel?view=strip&from=2026-08-05&to=2026-09-18` 200 `data.strip.tab_key=='channel'`(음성 대조군 "권한만 통과하고 빈 응답" 아님); `GET …/export.csv?kind=daily&…` 200 `text/csv; charset=utf-8`, `Cache-Control: no-store`, 파일명 `naver_settle_daily_20260805_20260918.csv`.
- 실측(b) 비로그인(쿠키 없음): 페이지·strip·full·export 전부 **302 → /login?next=…**(200 아님) = `tests/domains/test_settlement_channel_api.py:188 test_anonymous_is_not_served`(301/302/401 허용) 계약과 일치.
- 계약 매트릭스: SSOT `foms/services/settlement_channel_access.py:35~60 is_accounting_or_admin`(None·비활성·VIEWER deny, ADMIN allow, MANAGER/STAFF 는 `normalize_team(team)=='ACCOUNTING'`); `tests/domains/test_settlement_channel_access.py:31~40` 8행(admin·manager+accounting·staff+accounting 통과 / manager+cs·staff+cs·viewer+accounting·inactive-staff+accounting·anonymous 거부), `:83 test_manager_outside_accounting_is_denied_by_gate_and_engine`; API 테스트 `_DENIED_ACTORS` 5조합(MANAGER+CS·STAFF+CS·STAFF+SALES·VIEWER+ACCOUNTING·VIEWER) 403 JSON + sync 403(`test_settlement_channel_api.py:56~59·178~200`). 엔진 `foms/services/orders/order_mutation_policy.py:337~338` gate 판정이 `:353~356` ADMIN/MANAGER override 보다 **먼저** — MANAGER 우회 차단. 정책 등재 `:135~144` 세 정책 모두 `gate="…:is_accounting_or_admin"`. 페이지 `foms/web/cs/settlement_dashboard.py:47~60·102` 같은 함수→`abort(403)`.
- 회계팀 조용한 403 검사: ACCOUNTING 직접 문자열 비교(`== 'ACCOUNTING'` / `== "ACCOUNTING"`) grep → foms/·app.py **0건**; `ACCOUNTING` 리터럴은 팀 라벨 사전(`foms/web/auth/routes.py:69`)·SSOT·정책 등재·docstring 뿐. 직접 문자열 비교 게이트 없음.
- 한계: 계정이 ADMIN 하나라 403 실측은 코드+테스트 계약, 실측은 로그인/비로그인 2행뿐(확인 못 한 항목에 기재).

### E-3 계좌번호 마스킹 — PASS
- (a) API full(`w3_api_full.json`, 창 08-05~09-18): `deposit_channels[0].account_no_masked='****4011'`(정규식 `^\*{4}.{4}$` 일치, 기업은행), `[1]=''`(bank_type None·예금주 `*` = 충전금 상계 채널, 계좌 자체가 없어 `mask_account_no` 300~314 가 빈 문자열 — 결함 아님). 응답 전체에 DB 실계좌 앞 6자리·전체 자릿수·구분자 포함 원문 **0건**(`w3_staging_batch.json` `e3_scan`), `w3_api_exceptions.json`·`w3_api_strip.json`·`w3_page.html`·`w3_export_400.json` 도 0건. 10자리+ 숫자열 465개는 `product_order_id`/`order_id`(16~17자리) — 계좌(14자리)가 아니다. 원장 `ledger.rows[*].raw` 키에 account 계열 0, `naver_settle_case.raw_snapshot` 에 `accountNo` 0행(`e3_case_raw_has_account`), `daily_raw_keys` 에만 `accountNo` 있고 daily 원장은 CSV 에서 `raw_snapshot` 제외(`settlement_channel_export.py:25`).
- (b) CSV daily(`w3_daily.csv`): '계좌번호(마스킹)' 열(index 22) 22행 전부 `****xxxx` 또는 빈값(14 = 충전금 상계 행), 태그 `_ACCOUNT`→`mask_account_no`(`export.py:213·392`).
- (d) 새는 경로 음성 대조군: `security_logs.detail::text`·`message` 에 뒤 4자리 0건·앞 6자리 0건·전체 0건; 400 본문 값 없음; `CSV_COLUMNS` 304~309 에 raw 열 없음. DB 실측 형태: 스테이징 218행/1계좌/14자리/빈 18, 운영 160행/1계좌/14자리/빈 17(`e3_daily_account_shape`).
- 테스트 계약 `test_settlement_channel_api.py:312 test_account_no_never_leaves_the_server`.

### E-4 쓰기 경로 — PASS
- `replace_partition` 호출자: `settle_sync.py` 내부 655·676·696·731 뿐(`__all__` 915 로 노출은 되나 외부 호출 0). `run_settle_sync` 호출자: `foms/services/jobs/tasks.py:629·635`(RQ 태스크 `run_naver_settle_sync_task`)·`scripts/maintenance/run_naver_settle_sync.py:44·141`(워커 루프). 웹 프로세스의 `jobs.tasks` import 는 `foms/api/erp_map.py:407`(geocode) 뿐.
- `POST /sync`(API 297~333): 게이트 재검사 → `_backfill_arg` → `_enqueue` → `enqueue_naver_settle_sync`(`foms/services/jobs/queue.py:512~542`, 518 "동기 폴백은 없다", 535 중복 enqueue 차단) → `log_access` 1행. 도메인 쓰기 0.
- manifest: `docs/harness/foms_order_mutation_policy_manifest.json:918~922` `settlement_channel_api.api_settlement_channel_sync` mode guard·policy SETTLEMENT_CHANNEL_SYNC, `foms_write_guard_manifest.json:745~748` 동일 — `settlement_channel_api.*` 항목 각 **1건**(POST /sync 하나). GET 은 `_WRITE_METHODS`(`order_mutation_policy.py:56·590`) 밖.
- `is_naver_settle_sync_enabled`(`feature_flags.py:431`) 는 `start.sh:56~57` 워커 새벽 루프만 켜고 끈다(수동 enqueue 와 무관 — 문서화된 의도).
- 음성 대조군: 비로그인 export/strip/full 302(위 E-1), 400 경로에서 감사 행·쓰기 없음.

## 4. NOT-A-DEFECT
| 항목 | 이유 |
|---|---|
| 기본 창 미매칭 KPI 482(API 07:42 UTC) vs SQL 511(09-05 02:00 UTC) | 사이에 09-04 20:38 UTC 야간 동기화가 롤링 창 421행을 재적재(`w3_staging_followup.json` `case_synced_after_api_snapshot`) — 시차이지 불일치 아님. |
| `deposit_channels[1].account_no_masked=''` | 충전금 상계 채널(bank_type None·예금주 `*`) — 계좌 없음. `mask_account_no` 빈값→'' 규약. |
| API 응답의 10자리+ 숫자열 465개 | `product_order_id`/`order_id` 16~17자리 식별자, 계좌(14자리) 아님. 실계좌 앞 6자리 검색 0. |
| 매칭 건 expect ≠ pay(#4461 11,840 vs 12,680) | expect = pay − 수수료. 정상. 출고가 대조 축은 `pay_settle_amount`. |
| sync 감사 행 행위자 user 38(upperkill) | 사용자 전환(IMPERSONATE) 뒤 호출. 행위자 기록 자체는 정상. |
| FAILED run 이 예외 큐에 없음·RUNNING 잔류 | W2/F 축·결정 사항 — 재보고 안 함. |
| 매칭률 0%·워크벤치 적체 | 결정 사항 — 금액·aging 만 새로 냈다(W3-D-01). |

## 5. 확인 못 한 항목
| 항목 | 이유 |
|---|---|
| 회계팀(MANAGER/STAFF+ACCOUNTING)·CS 매니저·VIEWER 계정 실측 403 표 | 스테이징 측정 계정이 ADMIN 하나 — 코드(access.py 35~60·엔진 337~356)+테스트 계약(8행+API 5조합)으로 대체. |
| 부분 취소 매칭 건의 차액 표시 대조군 | 스테이징·운영 모두 매칭 건에 취소 행 0(has_cancel 0). 표본 부재. |
| 운영 매칭 건 출고가 대조 | 규율(운영 배치는 SQL 집계만). 운영 3주문·11행 합만 기록. |
| 예외 큐 헤더 실화면 문구 | W4 `w4_exceptions_header.png`·`w4_exceptions_text.txt` 가 OUT 에 없음 — 소스(channel.js:1997)+API 로 판정. |
| `product_order_type<>'PROD_ORDER'` → NA 음성 대조군 | 스테이징·운영 모두 `naver_settle_case` 에 PROD_ORDER 만 존재(모집단 0) — 대조군 성립 불가. |
| 운영 `raw_snapshot`·`security_logs` 계좌 원문 스캔 | 스테이징 결과로 갈음(운영 배치는 계좌 형태 집계만). 스테이징과 계좌 1개·14자리 동일 형태. |
| 이름 일치 3,130건의 진위 | 동명이인 오탐 분리 불가(원문 비교 금지 규율) — 전화 일치만 근거로 사용. |

## 6. 결정 재고
- **D-3 차액 표시(재계산 금지 D-4 와의 관계)**: 매칭 행에 `pay_settle_amount`(원값)와 출고가(원값)를 **나란히** 두고 다르면 예외 kind 로 드러내는 것은 "네이버 금액 재계산"이 아니다(두 원값 병기, 차는 파생·표시 계층). 스테이징 실표본 #4242(출고가 0 vs pay 2,830,000)가 현재 어디에도 안 보인다. 재고 요청.
- **매칭률 0% = 워크벤치 적체(결정 존중)**: 다만 운영 실측 "링크 있는 미매칭 1,338건 중 전화 일치 918건(68.6%)·343,095,791원"은 적체 해소 우선순위 근거로 CEO 판정에 포함 요청. 결정을 뒤집는 것은 아님.

## 7. 산출물 경로(OUT = `C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo`)
- 본 파일 `findings_w3.md`
- 스테이징 API: `w3_staging_api.py` → `w3_api_log.json`(응답 코드·헤더·시각), `w3_api_full.json`, `w3_api_exceptions.json`, `w3_api_exceptions_narrow.json`, `w3_api_strip.json`, `w3_daily.csv`, `w3_export_400.json`, `w3_page.html`
- 스테이징 DB: `w3_explore.py`→`w3_explore.json`, `w3_staging_batch.py`→`w3_staging_batch.json`, `w3_staging_followup.py`→`w3_staging_followup.json`, `w3_match_diff.py`→`w3_match_diff_staging.json`
- 분석: `w3_exceptions_analyze.py`→`w3_exceptions_kinds.json`
- 운영 DB 1회: `w3_production_batch.py`→`w3_production.json`
- 공통: `w3_common.py`
