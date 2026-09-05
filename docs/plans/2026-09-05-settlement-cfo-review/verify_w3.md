# verify_w3 — 워커 W3(축 D 존재·권리 · E 통제·감사 추적) 반박 검증

- 검증자: vw3 · 2026-09-05 02:20~02:30 UTC · 워크트리 `C:/tmp/foms-s-settle-cfo`(HEAD 7100e2aa1, pwd 확인) · OUT = `…/scratchpad/cfo`
- 접속: 스테이징 API 로그인 세션 1(GET 만, export·sync 미호출) · 스테이징 DB readonly 2회(`vw3_staging_probe.py`, `vw3_match_diff.py`) · **운영 DB readonly 배치 1회**(`vw3_production_batch.py`, 02:22:39~02:22:44 UTC, 재실행 없음)
- 규율: 워크트리 무편집 · 운영 쓰기 0 · [지금 동기화]/[받아오기] 미클릭 · 비밀·계좌 원문 미기록(해시 대조 True/False, 계좌는 숫자→9 치환 형태만)
- 계약 테스트: `PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_settlement_channel_access.py tests/domains/test_settlement_channel_api.py tests/domains/test_settlement_channel_export_api.py tests/domains/test_settlement_channel_strip.py -q -p no:cacheprovider` → `148 passed in 2.03s`

## 1. 판정 요약

| ID | 워커 심각도 | 판정 | 재무 영향 종류 | 심각도 조정 |
|---|---|---|---|---|
| W3-D-01 | WARN | **CONFIRMED** | measured(운영 재현 일치) | 유지 |
| W3-D-02 | WARN | **CONFIRMED**(정밀도 보정 3건) | none(현재 잘림 0, 구조) | 유지 |
| W3-D-03 | WARN | **CONFIRMED**(전제 보정: 설계 결정이라 '결정 재고' 성격) | measured(스테이징 1건, 운영 미측) | 유지 |
| W3-E-02 | WARN | **CONFIRMED** | none | 유지 |
| W3-E-05 | WARN | **CONFIRMED** | none(통제) | 유지 |

새 발견 2건: **VW3-D-04**(요약 스트립·탭 배지 "예외 N건" = 잘린 목록 길이) · **VW3-E-06**(CSV 내보내기 감사 행에 type/q 조건 미기록).

## 2. 반박 시도 상세

### W3-D-01 미매칭 정산 채권이 화면에 금액으로 없다 — CONFIRMED
- **코드 재독**: `foms/services/settlement_channel.py:609~650 _build_case_stats` 는 `count(id)`·`sum(pay_settle_amount)` 를 status×링크로 group-by 하지만 status 별 금액은 `stats` 에 넣지 않고 `pay_settle` 하나로 합친다. `:653~681 _kpi_block` 반환 키에 미매칭 금액 키 없음(`unmatched_count`·`unmatched_pending_count`·`unmatched_unlinked_count` 건수 3개). 커널 전체 grep `unmatched` × `amount|sum|expect` = 0건. 스트립 `:1311~1318` 도 `unmatched_count` 만. 프론트 `static/js/settlement/channel.js:1993~1997` 문구도 건수만.
- **운영 재현(`vw3_production.json`, 독립 SQL)**: `p_status_all` UNMATCHED 4,257행/4,227건 expect **1,480,447,006** · 완료분 **1,471,504,974** — 워커 수치와 원 단위 일치. `p_status_linked` 링크 없음 2,911행 978,573,922 · 링크 있음 1,346행 501,873,084 일치. aging(기준 09-04) 90+ 2,917행 **981,133,199** 일치, 기준일을 09-05 로 옮겨도 90+ 는 그대로(`p_aging_0905`)이고 <30/30-59/60-89 만 이동(경계 민감도 확인).
- **구성 확인**: `p_unmatched_by_type` — NORMAL_SETTLE_ORIGINAL 4,225행 1,494,944,259 + NORMAL_SETTLE_AFTER_CANCEL 32행 **-14,497,253** = 1,480,447,006. 즉 14.8억은 취소 행이 부호 그대로 상계된 **원값 부호합**(D-4 재계산 금지 규약과 일치). 회계팀에 낼 때 "취소 32행 -1,450만 포함" 을 같이 말해야 한다.
- **음성 대조군(새로 추가)**: `p_link_has_order_but_unmatched` = 0행/0링크(운영), 스테이징 `s_link_has_order_but_unmatched` = 0 — 링크에 주문이 붙었는데 case 가 UNMATCHED 로 남은 행이 없으므로 미매칭 금액이 "매칭 갱신 누락" 이 아니라 실제 미연결이다. `p_matched_null_order` = 0.
- 판정: CONFIRMED. 재무 영향 measured. 심각도 WARN 적정(화면이 틀린 숫자를 내는 게 아니라 필요한 숫자를 안 낸다).

### W3-D-02 예외 큐 상한(50) 잘림을 화면·API 가 말하지 않는다 — CONFIRMED(정밀도 보정)
- **코드 재독**: `_EXCEPTION_CAP = 50`(`settlement_channel.py:112`). `_daily_exceptions :883~898` 는 HOLDBACK·LIMIT·NEGATIVE 를 한 리스트에 모아 `found[:_EXCEPTION_CAP]`. `_unmatched_rows :901~912` 갈래별 `limit(50)`. `_build_exceptions :1161~1183` 세 목록을 잇기만 하고 총수·잘림 표식 없음. 응답 최상위 키 17개(`vw3_api_probe.json` `top_level_keys`)에 truncation 키 없음.
- **보정 1**: 워커 "HOLDBACK 만 `holdback.count`" → `_build_holdback :551~589` 의 `count` 는 `pay_holdback_amount<>0 OR settlement_limit_amount<>0` 인 **일별 행 수**라 HOLDBACK+LIMIT 를 합친 행 수다(kind 별 아님). NEGATIVE 총수는 어디에도 없다는 결론은 그대로.
- **보정 2**: `_run_exceptions :945~952` 의 RETRO 도 `[:_EXCEPTION_CAP]` 로 잘린다(워커 미기재). 네 갈래 모두 잘림 표식 0.
- **보정 3(화면 근거 확보)**: 워커가 "OUT 에 없다" 고 한 `w4_exceptions_header.png`·`w4_exceptions_text.txt` 가 10:58 에 생성돼 있다. `w4_exceptions_text.txt:277` 실화면 문구 = "FOMS 미연결 4,265건 = 워크벤치 대기 1,386건(…) + 수집 전 주문 2,879건(…). 표에는 갈래마다 최근 것부터 상한까지만 실립니다." 뒤에 표 125행 — "N건 중 50건" 도, 상한 숫자도 없음. 코드 독해 판정이 아니라 실화면 판정으로 격상 가능.
- **재현(스테이징 API 같은 순간, `vw3_api_probe.json`)**: 창 01-01~09-18 exceptions 125 = UNMATCHED 50 + UNLINKED 50 + HOLDBACK 25 vs KPI pending 1,386 · unlinked 2,879(DB `s_wide_window_population` 1,386/2,879/25 일치). 창 08-05~09-18: 65 = UNMATCHED 50 + HOLDBACK 15 vs KPI 511(DB 511/0/15). 좁은 창 음성 대조군은 워커 `w3_api_exceptions_narrow.json`(42=42) 그대로.
- **현재 재무 영향**: 일별 3종 합 25 < 50 이라 지금 잘리는 것은 UNMATCHED/UNLINKED 뿐이고 그 총수는 KPI 가 말한다 → 금액 영향 0(구조 결함). 워커 판정과 같다.
- 판정: CONFIRMED, WARN 유지.

### W3-D-03 매칭 건 정산액≠출고가를 화면이 예외로 내지 않는다 — CONFIRMED(전제 보정)
- **재현(`vw3_match_diff.py` → `vw3_match_diff_staging.json`, 독립 작성)**: 매칭 2주문 — #4242 출고가 0 vs pay 2,830,000 / expect 2,698,971(NEQ, 취소 없음, 상태 DRAWING) · #4461 출고가 12,680 = pay 12,680(EQ). `neq_abs_sum` 2,830,000 일치.
- **보정(중요)**: 실무 탭 행 API 는 `shipping_price`(`settlement_rows.py:332`) 와 `naver_settlement.amount`(expect 원값 합, `:149~207`·`:349`) 를 **같은 행에 이미 싣는다**(재현: #4242 행 `rows_api_naver_settlement.amount=2698971`). 못 보는 이유는 프론트가 **일부러** 금액을 안 그리기 때문 — `static/js/settlement/operations.js:466~467` "**금액은 그리지 않는다** — 노출 최소화 원칙이고, 서버도 화면에 쓰라고 준 값이 아니다", CSV 도 상태 문구만(`:776~777`). 따라서 이 발견은 "기능 부재" 보다 "설계 결정(노출 최소화) 대 회계 대사 요구" 의 충돌이라 워커 §6 '결정 재고' 로 다루는 게 맞다. 채널 탭 예외 kind 7종에 금액차 없음(`settlement_channel.py:883~968`) 은 사실.
- **재무 영향 성격**: 스테이징 실표본 1건 2,830,000 은 measured 이나 스테이징 데이터이고, #4242 의 차이는 "품목 미입력(출고가 0)" 이라 정산 불일치가 아니라 주문 입력 공백이다. 운영 매칭 3주문은 출고가 대조 미실시(워커 규율 동일) — 운영 노출액은 **미측**.
- 판정: CONFIRMED(현상), WARN 유지. 권고는 '결정 재고' 절로.

### W3-E-02 동기화 요청 감사 행에 실효 구간·run 연결키 없음 — CONFIRMED
- **코드 재독**: `foms/api/cs/settlement_channel.py:316~324` detail = `{queued, backfill_from, channel}`. 실효 창은 워커가 run 시작 시 계산(`naver_settle_sync_runs.scope` 키 = backfill_from·channel·from·to·trigger, `vw3_production.json` `p_runs_scope_keys`), 감사 행 id 나 job id 는 scope 에 없음. 최신 run 3행 `actor_user_id` NULL(새벽 루프) — 수동 요청과의 연결은 시각뿐.
- **실측**: 스테이징 `s_sync_detail_keys` = backfill_from 3·channel 3·queued 3, 운영 `p_sync_detail_keys` 동일(4행). 라벨 등재 `audit_message_display.py:174~175` 확인.
- 판정: CONFIRMED, WARN 유지(추적성, 금액 0).

### W3-E-05 운영 claude_master 비밀번호 미로테이션 — CONFIRMED
- **재현(운영 배치)**: `e5_user` id 57 · ADMIN · is_active **false** · pbkdf2:sha256:600000 · `matches_secret` **True** · 음성 대조군(앞에 'x' 붙인 문자열) False. 비밀번호·재설정 계열 감사 행 2026-08-25 이후 0(`e5_pw_actions_since_0825`, RESET 패턴 추가해도 0). 마지막 LOGIN_OK 2026-09-03 00:32 UTC.
- 판정: CONFIRMED, WARN 유지(잠금이 완화 요인, 해제 창마다 노출본 그대로).

## 3. PASS 축 거짓 초록 검사(pass_probes)

| 축 | 찔러본 표본 | 결과 |
|---|---|---|
| E-1 권한 | 정산 표면 라우트 전수: `/erp/settlement`(web 89~103), `/api/settlement/aggregates`(104)·`/rows`(151·157), `/api/settlement/channel` GET(221)·POST /sync(311)·export(408) — 6곳 전부 `is_accounting_or_admin` 계열 호출. 그 밖에 "settlement" 라우트는 `foms/api/cs/dashboard.py:262 /orders/<id>/settlement/issue`(완료 주문 비용 청구, CONSTRUCTION 팀 deny) 하나 — 채널 정산과 다른 도메인이라 범위 밖 | PASS 유지 |
| E-1 권한 | 엔진 순서 `order_mutation_policy.py:337~339` gate 판정이 `:353~356` ADMIN/MANAGER override 앞. 템플릿 `policy_can`(`:634~636`) 도 `user_can` 경유라 UI 은닉도 같은 답. 직접 문자열 비교 `== 'ACCOUNTING'` grep foms/·app.py·apps/ = 0건(재확인). 계약 148 passed | PASS 유지 |
| E-3 마스킹 | **워커 음성 대조군이 무효였다**: 저장된 계좌 형태가 `999*******9999`(14자, 숫자 7개 — 네이버가 이미 가운데 7자리를 가려서 준다, `vw3_staging_probe.json` `s_account_shape`). 그래서 워커의 "앞 6자리 검색 0건" 은 앞 6자리가 존재하지 않아 아무것도 검출할 수 없는 검사였다. 저장 문자열 **그대로(verbatim)** 스캔으로 대체: `naver_settle_sync_runs` scope/stats/error 0 · `security_logs` detail/message 0 · `naver_settle_case.raw_snapshot` 0 · **`naver_settle_daily.raw_snapshot` 200행(>0, 대조군 성립)**. `mask_account_no :300~314` 는 알파넘만 남겨 뒤 4자리 → `****4011`. 운영은 배치 1회 규율로 verbatim 재스캔 못 함(형태 14자·1계좌 동일, 워커 `e3_daily_account_shape`) | PASS 유지(대조군 교체) |
| E-4 쓰기 경로 | 커널·API·export·rows·aggregation·페이지 7파일에서 `commit()/.add(/.flush()/.merge(/.delete(/.update(/set_setting` grep = 0건(`SystemSetting` 은 `session.get` 읽기, `seen.add` 는 set). `_backfill_arg :244~266` 하한 오늘-400·상한 오늘, `enqueue_naver_settle_sync` job_id 고정+in-flight 중복 차단(`queue.py:512~542`). 소급 변경 dict 는 table/date/old_total/new_total 만(`settle_sync.py:350~384`) — API `ref` 로 나가도 원문 없음 | PASS 유지 |
| D 매칭 상태 신선도(추가) | 링크에 `order_id` 가 붙었는데 case 가 UNMATCHED 인 행 = 운영 0 · 스테이징 0. MATCHED 인데 `foms_order_id` NULL = 0 | 통과 |

## 4. 새 발견

### VW3-D-04 · WARN · 표시/완전성 · 요약 스트립·채널 탭 배지의 "예외 N건" 이 잘린 목록 길이다
- **코드**: `settlement_channel.py:1316` `"exception_count": len(exceptions)` — `_build_exceptions` 의 상한 적용 뒤 길이. 프론트 `channel.js:2343` 요약 스트립 `'예외 ' + fmtCount(strip.exception_count) + '건'`, `:1541` 채널 탭 예외 버튼 배지 `(data.exceptions || []).length`. 계약 테스트가 이 정의를 핀으로 박아 둔 상태(`tests/domains/test_settlement_channel_strip.py:204·215·325` `strip["exception_count"] == len(full["exceptions"])`).
- **실측(스테이징 같은 순간, `vw3_api_probe.json`)**: 기본 창 strip `exception_count` **65** vs 같은 응답 `unmatched_count` **511**(+보류 15 = 실제 예외 526) → 8배 축소. 창 01-01~09-18: **125** vs 4,265+25 = 4,290 → 34배 축소. DB 대조 `vw3_staging_probe.json` `s_default_window_population` 511/0/15 · `s_wide_window_population` 1,386/2,879/25. 운영 기본 창 모집단 `vw3_production.json` `p_default_window_population` 500+3+15 = 518(운영 스트립은 화면 조작 금지라 미호출, 커널 동일).
- **화면**: `w4_exceptions_text.txt:124` 요약 스트립 "예외64건"(같은 창 KPI 미연결 482~511건), `:271` 채널 탭 배지 "예외 125"(KPI 4,265건). 요약 탭에는 KPI 타일이 없어 회계팀은 65건이 전부라고 읽는다.
- **재무 영향**: 금액 없음 — "회계팀 오해 가능"(예외 규모 8~34배 과소 표시). W3-D-02 와 뿌리는 같지만 표면이 다르다(D-02 는 표의 잘림 미표시, 이것은 **머리 숫자 자체가 잘린 값**).
- **권고(근본)**: `exception_count` 를 상한 적용 전 모집단으로 정의 — 이미 있는 `case_stats["unmatched"]` + 일별 3종 미절단 건수 + run 예외 수(추가 질의 0). 스트립 테스트 3곳의 핀을 "== 잘린 길이" 에서 "== 모집단" 으로 바꾼다. 노력 **S**.

### VW3-E-06 · WARN · 완전성(추적) · CSV 내보내기 감사 행에 유형·검색 조건(type·q)이 없다
- **코드**: `foms/api/cs/settlement_channel.py:417~418` 은 `filters=_export_filters()` 로 커널에 type·q 를 넘기는데 `:421` `_log_export(user, kind, channel, date_from, date_to, basis)` 는 조건을 받지 않는다. `_log_export :355~381` detail = kind·channel·from·to·basis. 조건이 뜻을 갖는 종류는 settle_case·commission·vat_case·settle_case_sheet(`settlement_channel_export.py:147~157 FILTER_FIELDS`). `_log_export` 자신의 docstring(`:370~372`)이 "요청값을 적으면 … 같은 파일을 다시 만들려는 사람이 다른 행 집합을 받는다" 며 실효 축을 남기는 이유를 말하는데, 같은 논리가 조건에는 적용되지 않았다.
- **실측**: 스테이징 export 감사 33행의 detail 키 집합 = basis·channel·from·to·kind(`s_export_detail_keys`), type/q 를 가진 행 **0/33**(`s_export_rows_with_filter_keys`). 운영 5행 동일(`p_export_detail_keys`). 계약 테스트 `test_settlement_channel_export_api.py:321~337` 도 kind·from·to·channel 만 단정.
- **음성 대조군**: 조건을 받지 않는 daily 는 400 으로 거절되므로(`w3_export_400.json`) 감사 행 자체가 없다 — 조건 없는 내보내기는 이 결함과 무관.
- **재무 영향**: 없음(추적성). `type=NORMAL_SETTLE_AFTER_CANCEL` 만 받아 간 파일과 전량 파일이 감사상 구별되지 않는다.
- **권고(근본)**: `_log_export` 에 `filters` 를 받아 detail 에 `type`·`q` 를 그대로(빈 값은 키 생략) 기록, 계약 테스트에 조건 있는 다운로드 1행 추가. 노력 **S**.

## 5. 정밀도 메모(결함 아님)
- 워커 W3-D-01 의 1,480,447,006원은 취소 행 32행(-14,497,253) 이 상계된 부호합이다. 보고서에는 "취소 상계 포함 원값 합" 으로 적는 편이 회계팀 오해를 줄인다.
- 워커 E-3 의 "앞 6자리 0건" 대조군은 데이터 형태상 무효(§3). PASS 결론은 verbatim 스캔으로 유지.
- 워커 D-02 의 "화면 근거 없음" 은 W4 산출물 생성 시각 차이(10:58) — 이제 실화면 근거가 있다.
- 워커 D-03 은 설계 의도가 소스에 명시돼 있어(operations.js:467) '결정 재고' 절에 두는 것이 맞다.

## 6. 확인 못 한 것
- 운영 매칭 3주문의 출고가 대조(운영 배치 1회 규율 — 워커와 동일 사유).
- 운영 요약 스트립 실화면(운영 화면 조작 금지) — 커널이 동일하므로 스테이징 실측으로 갈음.
- 운영 `raw_snapshot`·`security_logs` verbatim 계좌 스캔(운영 배치에는 숫자만 스캔이 들어가 있었고 그 스캔은 형태상 무효) — 스테이징 verbatim 결과와 저장 형태 동일(14자·1계좌)로 갈음.

## 7. 산출물
- 본 파일 `verify_w3.md`
- 운영 1회: `vw3_production_batch.py` → `vw3_production.json`
- 스테이징 DB: `vw3_staging_probe.py` → `vw3_staging_probe.json`, `vw3_match_diff.py` → `vw3_match_diff_staging.json`
- 스테이징 API: `vw3_staging_api.py` → `vw3_api_probe.json`, `vw3_api_full_default.json`, `vw3_api_full_wide.json`
