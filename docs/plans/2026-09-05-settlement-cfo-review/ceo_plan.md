# 정산탭 CFO 감사 — CEO 설계서 (2026-09-04)

> 근거 파일: 프롬프트 `docs/plans/2026-09-04-settlement-tab-cfo-review-prompt.md`, 브리프 `docs/plans/2026-09-04-settlement-cfo-review-brief.md`.
> 코드 라인은 전부 워크트리 `C:/tmp/foms-s-settle-cfo`(base origin/deploy 7100e2aa1) 기준.
> OUT = `C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo`

## 0. 설계 전 확인한 사실(워커가 다시 읽지 않아도 되는 것)

### 0.1 커널 `foms/services/settlement_channel.py` (1,320줄)
| 함수 | 줄 | 의미 |
|---|---|---|
| 상수 `STALE_AFTER_HOURS=36`·`FINAL_BEFORE_DAYS=30`·`BASES=(expect,complete,basis,pay)`·`GRANULARITIES=(day,week,month)`·`LEDGER_KINDS=(case,commission,vat_case)`·`MAX_RANGE_DAYS=400`·`MAX_PER_PAGE=200`·`_EXCEPTION_CAP=50` | 80~112 | |
| `_LEDGER_BASES` case=(expect,complete,basis,pay) / commission=(expect,complete,basis) / vat_case=(basis,) | 149~153 | 되돌림 규칙 |
| `_WATERFALL_STEPS` 7단: pay_settle·commission·benefit·deduction_restore·holdback·minus_charge·settle_amount, 방향 전부 +1 | 172~180 | difference_settle·return_care·preferential_commission·normal·quick 은 워터폴에 없음 |
| `_DAILY_SUMS` normal·quick·deduction_restore·commission·benefit·minus_charge·pay_settle·settle_amount | 183~192 | |
| `mask_account_no` | 300 | `****`+뒤4 |
| `_previous_range` = (from−span, from−1) **일수 동일, 달력 월 아님** | 322 | |
| `_bucket_key` month=`day.replace(day=1)`, week=월요일 — Date 컬럼이라 TZ 없음 | 344 | |
| `_hours_since` naive UTC 비교 · `_build_sync` stale=(not never) and (age None or age>36) | 398·412 | |
| `_daily_rows` 창 = `settle_expect_date BETWEEN from AND to` (ix_nsd_channel_expect) | 457 | |
| `_holdback_of` = pay_holdback_amount + settlement_limit_amount | 479 | |
| `_build_daily` 빈 버킷은 0 으로 채움(rows 가 하나라도 있으면), rows 0 이면 `[]` | 484 | B-1 "빈 날 구분" 판정 근거 |
| `_daily_totals` settled=Σsettle_amount(complete NOT NULL), expected=Σsettle_amount(complete NULL), pay_settle=Σpay_settle_amount, commission=Σcommission_settle_amount | 529 | |
| `_case_scope` = `coalesce(settle_expect_date, search_date) BETWEEN` | 598 | Seq Scan 후보 |
| `_build_case_stats` group by match_status, link_id IS NOT NULL | 609 | |
| `_kpi_block` commission_rate=abs(commission)/pay_settle, match_rate=matched/prod_orders | 653 | |
| `_build_reconcile` diff = daily pay_settle − case pay_settle, **허용 오차 없음(Decimal 정확 비교)** | 734 | |
| `_build_vat` ceiling=min(to, 전월 말일) | 810 | |
| `_daily_exceptions` HOLDBACK/LIMIT/NEGATIVE → `found[:50]` **세 종류 합쳐 50** | 883 | D-2 |
| `_unmatched_rows` 갈래별 `limit(50)` | 901 | D-2 |
| `_run_exceptions` RETRO·COUNT_MISMATCH 만 — **FAILED run 자체는 예외 큐에 안 실림** | 945 | F-3 |
| `_ledger_axis` / `_axis_gap_counts`(조건부 집계 1쿼리) | 971·1011 | H-1 |
| `_core` 일별 2회 + 건별 group-by 2회 | 1185 | |
| `build_channel_dashboard` | 1213 | |
| `build_channel_strip` 질의 6개 선언 | 1271 | H-1 |

### 0.2 API `foms/api/cs/settlement_channel.py`
- `_range_args` 108: 기본 오늘−30 ~ 오늘+14 (2026-09-04 기준 **2026-08-05 ~ 2026-09-18**). `_view_arg` 139 (full|strip, 오타는 400). `_basis_arg` 160 (CSV 전용; full 뷰는 `_full_view` 168 이 request.args 직접 읽음). `_export_filters` 336 (type·q 빈 값은 키째 제거).
- `POST /sync` 297: 게이트 재검사 → `_backfill_arg`(오늘−400 하한) → `_enqueue`(rq, job_id 고정 `naver_settle_sync`, 중복이면 queued=False) → `log_access("네이버 정산 동기화 요청", user.id, action=NAVER_SETTLE_SYNC_REQUEST, target_type="settlement_channel", detail={queued, backfill_from, channel})`.
- `_log_export` 355: `log_access("네이버 정산 CSV 내보내기", user.id, action=NAVER_SETTLE_EXPORT_CSV, target_type="naver_settle_export", detail={kind, channel, from, to, basis=effective_basis})` — **응답 만들기 전** 기록.
- `GET /export.csv` 384: kind 필수(daily·case·sheet 별칭), 403 은 JSON, 헤더 `Cache-Control: no-store`.
- 감사 라벨 두 코드 모두 `foms/services/audit_message_display.py:174~175` 등재 확인.

### 0.3 동기화 `foms/services/integrations/naver_commerce/settle_sync.py`
- 상수 66~92: `DEFAULT_ROLLING_DAYS=30`·`DEFAULT_FUTURE_DAYS=14`·`FINALIZED_AFTER_DAYS=30`·`BACKFILL_WINDOW_DAYS=30`·`DAILY_RANGE_MAX_DAYS=28`·`VAT_FINAL_DAY=10`.
- `parse_settle_date` 270: `date.fromisoformat(text[:10])` — 시각·TZ 를 버린다(원문에 시각이 붙어 있으면 그 날짜 그대로).
- `replace_partition` 350: `(channel, axis)` DELETE 후 INSERT, 교체 전 합계와 다르면 retro dict.
- `_SyncContext.skip_day` 442: 백필이 아니면 `day+30 < today` 인 날은 **건너뜀**(과거 정정은 백필 없이는 영원히 안 들어옴).
- `split_windows` 564: `cursor..min(cursor+size−1, end)`, 끝 포함, 다음 창은 finish+1.
- `_sync_settle_daily` 630: 28일 창으로 받아 `settle_expect_date` 별 파티션 교체, 응답에 없는 날도 비움(`iter_days(start,end) ∪ grouped`).
- `_drive` 786: 창 순차 → 예외를 삼켜 `FAILED`/`ABORTED_QUOTA`. `_sync_window` 805: **창마다 commit**. `_finish` 830: FAILED 여도 `_close_run`+`_write_watermark` 뒤 `commit()`(실패 창의 미커밋 파티션이 함께 커밋됨).
- `_write_watermark` 865: OK 일 때만 `last_ok_at`·coverage 합집합(min/max) 전진. FAILED 는 `last_status`·`last_error` 만.

### 0.4 모델 (`models.py` 3671~3960)
- `naver_settle_daily`: settle_basis_start_date, settle_basis_end_date, **settle_expect_date NOT NULL**, settle_complete_date, settle_amount, pay_settle_amount, commission_settle_amount, benefit_settle_amount, deduction_restore_settle_amount, pay_holdback_amount, minus_charge_amount, difference_settle_amount, return_care_settle_amount, normal_settle_amount, quick_settle_amount, preferential_commission_amount, settlement_limit_amount, settle_method_type, bank_type, depositor_name, account_no, merchant_id, merchant_name, raw_snapshot(JSONB), synced_at, sync_run_id. 인덱스 `ix_nsd_channel_expect(channel, settle_expect_date)`.
- `naver_settle_case`: search_date NOT NULL, period_type, settle_basis_date, settle_expect_date, settle_complete_date, pay_date, order_id, product_order_id, product_order_type, settle_type, product_id, product_name, purchaser_name, pay_settle_amount, total_pay_commission_amount, free_installment_commission_amount, selling_interlock_commission_amount, benefit_settle_amount, settle_expect_amount, merchant_id, merchant_name, contract_no, foms_order_id, link_id, match_status('MATCHED'|'UNMATCHED'|'NA'), raw_snapshot, synced_at, sync_run_id. 인덱스 `ix_nsc_channel_search(channel,search_date)`·`ix_nsc_product_order`·부분 `ix_nsc_unmatched`·부분 `ix_nsc_foms_order`(naversettle_01). **pay_date·settle_complete_date·settle_basis_date 인덱스 없음.**
- `naver_settle_commission`: search_date, period_type, order_no, product_order_id, product_order_type, product_id, product_name, merchant_*, purchaser_name, settle_type, settle_basis_date, settle_expect_date, settle_complete_date, tax_return_date, commission_basis_amount, commission_type, pay_means_type, commission_amount, maximum_selling_interlock_commission_amount.
- `naver_vat_daily`: settle_basis_date NOT NULL, total_sales_amount, taxation_sales_amount, tax_exemption_sales_amount, credit_card_amount, cash_income_deduction_amount, cash_outgoing_evidence_amount, cash_exclusion_issuance_amount, other_amount, merchant_*, is_final. **세액·공급가액 컬럼 없음.**
- `naver_vat_case`: settle_basis_date, order_id, product_order_id, product_order_type, detail_type, status, product_name, 금액 8종 동일.
- `naver_settle_sync_runs`: started_at, finished_at, status(RUNNING|OK|FAILED|ABORTED_QUOTA), trigger(SCHEDULE|MANUAL|BACKFILL), actor_user_id, scope(JSONB {from,to,backfill_from,trigger,channel}), stats(JSONB {calls,rows,retro_changes,partitions,skipped_no_axis,last_dates,vat_month}), error, dry_run.
- 워터마크: `system_settings` 행 `setting_key='naver_settle_sync_state'` (`setting_value` JSONB: rev,last_run_at,last_ok_at,last_status,last_error,coverage_from,coverage_to,rolling_days,future_days,vat_final_month,per_endpoint).
- 감사: `security_logs(id,timestamp,user_id,message,action,target_type,target_id,detail)`. 링크: `external_order_links(id,channel,external_id,order_id,external_order_no,raw_snapshot,sync_status,...)`. 사용자: `users(username,password(해시),role,team,is_active)`. 주문 출고가는 `orders.structured_data` 파생(`foms/services/erp_display.py:297 erp_shipping_price_from_structured`).

### 0.5 내보내기 `foms/services/settlement_channel_export.py`
- BOM `\ufeff` 1회 + CRLF(334~335), `_fmt_money` 359: 콤마·통화기호·괄호 없음, 정수는 정수 문자열, 음수는 `-` 부호. 날짜 ISO 10자. `_ACCOUNT` 태그 열 "계좌번호(마스킹)".
- 시트 7열(`_SETTLE_CASE_SHEET_COLUMNS` 316~324): 구매자명·결제일·정산완료일·정산기준금액(pay_settle_amount)·Npay 수수료·매출 연동 수수료 합계·정산예정금액. **거래처·공급가·세액·계정 열 없음**(2026-09-03 사용자 확정 7열).

### 0.6 프론트 `static/js/settlement/channel.js` (2,557줄)
- 폴링 74~77: 10초 × 6회(60초) / 백필 60회(10분), 만료 문구 2176 `'N분 안에 반영되지 않았습니다. 워커가 밀렸을 수 있으니 잠시 뒤 새로고침하세요.'`.
- 동기화 헤더 985~1010: never/stale/ok 세 모드. ok 모드 부제 = `'상태 ' + sync.status` (FAILED 면 "상태 FAILED"), stale 문구 `'36시간 넘게 갱신되지 않았습니다 — 아래 숫자는 그 시점의 값입니다.'`. **RUNNING(진행 중) 표시는 없음**(워터마크에 RUNNING 이 안 써진다).
- 대사 1495~1516: 둘 다 0 이면 "대사 대상 없음", 아니면 `'대사 일치' : '대사 불일치'`.
- 백필 배너 2118~2145: `from < sync.coverage_from` 일 때만.
- 축 문구 파셜 `templates/cs/partials/settlement_channel_body.html:74` `정산 예정일 기준 · 매출 인식(완료일)과 다릅니다`, 셀렉트 109 `aria-label="원장 표 날짜 축"`.
- 핀: 셸 `templates/cs/partials/settlement_dashboard_body.html:20,21,423,424` = `20260903d`(4줄 동일값), 채널 22·425 = `20260903i`, `tests/domains/test_settlement_channel_render.py:72 _CHANNEL_PIN="20260903i"`(476 에서 단정).
- `pre_push_smoke.ps1` 214~241 서브셋에 `test_settlement_*` **없음**(`-Full` 스위치일 때만 전체). CI `ci.yml:109` 는 전체 스위트.

### 0.7 권한
- SSOT `foms/services/settlement_channel_access.py:is_accounting_or_admin` (ADMIN 또는 role∈{MANAGER,STAFF} ∧ normalize_team(team)=='ACCOUNTING', VIEWER·비활성·None deny). 정책 `order_mutation_policy.py:135~143` 세 정책에 `gate="...:is_accounting_or_admin"`, 엔진 336~338 이 gate 를 role override(352~355)보다 먼저 판정. 페이지 `foms/web/cs/settlement_dashboard.py:102 abort(403)`.
- 테스트: `tests/domains/test_settlement_channel_access.py`(gate matrix·MANAGER 외부팀 deny·정책 등재), `test_settlement_channel_api.py:171~205`(200/403/anonymous/sync 403), 312 `test_account_no_never_leaves_the_server`.

## 1. 공통 규칙(shared_notes 와 동일)
(StructuredOutput shared_notes 참조 — 이 파일의 §5)

## 2. W1 — A(정확성) + C(기간 귀속)
(StructuredOutput workers[w1].checklist 전문 — §6.1)

## 3. W2 — B(완전성) + F(운영 신뢰성)
(§6.2)

## 4. W3 — D(존재·권리) + E(통제·감사)
(§6.3)

## 5. W4 — G(표시·내보내기) + H(성능·부채) + pytest
(§6.4)

---
(§5·§6 본문은 StructuredOutput 에 실은 것과 같은 내용을 아래에 그대로 둔다.)

## 5. 공통 규칙 (shared_notes)

1. **겹침 방지 — 자원 소유권**
   - 헤드리스 브라우저(gstack browse 데몬은 1개)는 **W4 만** 쓴다. W1·W3 의 스테이징 접근은 파이썬 `requests.Session`(desktop UA, `POST {base}/login` form → 302) 로 한다. W2 는 스테이징 API 를 `?view=strip` 1회만 부른다.
   - 스테이징 API full 뷰(KPI·원장·CSV)는 W1 소유(창 2026-08-05~09-18·8월·9월·2월). W3 는 예외 큐(창 2026-01-01~09-18)·권한(403)·감사 목적의 호출만, W4 는 TTFB 측정과 8월 창 CSV 형식 검사만(응답 본문 숫자로 판정하지 않는다).
   - 스테이징 DB: W1 = 창 합계·8월 3축·부가세 합·원문 날짜 대조, W2 = 월별 분포·날짜 구멍·보류 짝·sync_runs·워터마크, W3 = 미매칭·매칭 금액·감사 행·해시 대조, W4 = EXPLAIN·질의 수. 같은 SQL 을 두 워커가 던지지 않는다 — 다른 워커 축의 숫자가 필요하면 자기 축에 맞는 다른 절단면으로 묻는다.
   - `[지금 동기화]`·`[받아오기]`·`POST /sync` 는 아무도 호출하지 않는다. F-2 는 코드 `channel.js:2065~2183` + 테스트 계약으로만 판정하고 "화면 결함"으로 쓰지 않는다.
2. **운영 DB 1회 배치 규율(W2·W3 만)**: 스테이징 DB 에서 SQL 을 먼저 완성·검증한 뒤, 운영은 `OUT/w2_production_batch.py` / `OUT/w3_production_batch.py` **한 스크립트 한 번 실행**으로 끝낸다(연결 1개, `execution_options(postgresql_readonly=True)`, 모든 SELECT 를 한 트랜잭션 안에서 순차 실행, 결과는 `OUT/w2_production.json` / `OUT/w3_production.json` 에 숫자만). 실패하면 원인 고친 뒤 재실행 1회까지만 허용하고 findings 에 재실행 사실을 적는다. 운영 URL 은 `OUT/production_db_url.txt` 에서 읽기만 하고 로그·stdout·findings 어디에도 출력하지 않는다. 운영 웹 로그인·화면 조작 금지. 운영 배치는 작업 60분 지점(스테이징 검증 완료 뒤)에 1회.
3. **읽기 전용 강제**: 모든 DB 연결은 `create_engine(url).connect().execution_options(postgresql_readonly=True)`; ORM 이 필요하면 `Session(bind=conn)`. 워크트리 import 는 `sys.path.insert(0, "C:/tmp/foms-s-settle-cfo")` + `PYTHONDONTWRITEBYTECODE=1`. pytest 는 `-p no:cacheprovider`. 워크트리에 파일을 만들지 않는다(스크립트·JSON·PNG 전부 OUT).
4. **날짜 고정**: KST 오늘 = 2026-09-04. 기본 창 = 2026-08-05 ~ 2026-09-18. API 호출은 항상 `from`·`to` 를 명시한다(자정을 넘기면 기본 창이 밀린다). 전월 말일 = 2026-08-31, 확정 경계(final_before) = 2026-08-05.
5. **근거 규율**: FAIL/WARN 마다 `파일:라인` 또는 재현 명령(정확한 URL·SQL) 또는 실측 파일 경로(`OUT/wN_*.json`). 화면 결함은 W4 스크린샷만 근거가 된다. "이미 결정된 사항"(재계산 금지·부호 규약·축 셀렉트 위치·xlsx 금지·매칭률 0% 원인·RUNNING 잔류·coverage 합집합·403 해소·"예정" 스캔 예외·F9/F10 수정분)은 결함으로 쓰지 않고, 뒤집을 근거가 있으면 `결정 재고` 절에 따로 적는다.
6. **음성 대조군 규율**: PASS 를 쓰려면 "발동해야 하는 표본이 발동함" + "발동하면 안 되는 표본이 발동 안 함" 두 줄을 같이 적는다. 대조군은 술어가 닿는 모집단 안에서 고른다(창 밖 행·다른 채널 행은 대조군이 아니다).
7. **시간 배분(워커당 약 90분)**: 각 축 30~40분, findings 파일은 축 하나 끝날 때마다 즉시 저장. 마지막 10분은 "확인 못 한 항목" 정리. pytest(W4)는 시작 직후 백그라운드로(922 passed 기준선).
8. **비밀 취급**: 비밀번호·토큰·DB URL·계좌 원문·구매자 전화 원문을 findings·JSON·stdout 에 적지 않는다. 해시 대조는 True/False 만.
9. **브리프 §6 함정 요약**: `get_today_kst()` 는 date · naive=UTC · MANAGER role override 는 `Policy.gate` 로 우회됨(엔진 336행) · 회계팀 alias ACCOUNTING→CS · RUNNING 잔류는 결정됨(B-4 의 "빈 구간" 만 별개) · `log_access` 두 번째 위치 인자가 행위자 · 프래그먼트 측정은 `X-FOMS-ERP-SHELL` 헤더 · CSV 레지스트리 2종 · 워커엔 세션 훅 없음 · `.alert` 5초 자동 닫힘 · 셸 프리페치 `ERR_ABORTED`·`mobile-push.js` 는 잡음.

## 6. 워커별 검사 목록

### 6.1 W1 — A(정확성 3중 대사) + C(기간 귀속)
산출: `OUT/findings_w1.md`, `OUT/w1_*.json`, `OUT/w1_*.csv`(받은 CSV 원본), 스크립트 `OUT/w1_*.py`.
접속: 스테이징 API(requests 세션) + 스테이징 DB(readonly). 브라우저 사용 금지.

준비
- P1. 로그인 헬퍼 `OUT/w1_client.py`: secrets 파일 `staging.base/password` + 최상위 `username`, `POST {base}/login` form, desktop UA, 302 확인. 이후 모든 GET 은 `?from=&to=` 명시.
- P2. DB 헬퍼: `OUT/staging_db_url.txt` → `create_engine(...).connect().execution_options(postgresql_readonly=True)`. 모든 합계는 `Decimal` 로 받아 원 단위 정확 비교(허용 오차 0).

A-1 3중 대사(창 2026-08-05~2026-09-18, channel='NAVER')
- 1) API: `GET /api/settlement/channel?from=2026-08-05&to=2026-09-18&granularity=day&ledger=case&basis=expect&per_page=200` → `OUT/w1_api_default.json`. 기록: kpi.settled_amount·expected_amount·expected_account_amount·expected_charge_amount·commission_total·holdback_amount·case_count·unmatched_count, reconcile.daily_total·case_total·diff, Σwaterfall, Σdaily[*].settle_amount, Σledger.groups[*].amount(기간 전체 settle_expect_amount 합).
- 2) DB 일별:
  ```sql
  SELECT SUM(CASE WHEN settle_complete_date IS NOT NULL THEN settle_amount ELSE 0 END) AS settled,
         SUM(CASE WHEN settle_complete_date IS NULL THEN settle_amount ELSE 0 END) AS expected,
         SUM(CASE WHEN settle_complete_date IS NULL AND upper(settle_method_type)='ACCOUNT' THEN settle_amount ELSE 0 END) AS expected_account,
         SUM(CASE WHEN settle_complete_date IS NULL AND upper(settle_method_type)='CHARGE_AMT' THEN settle_amount ELSE 0 END) AS expected_charge,
         SUM(commission_settle_amount) AS commission, SUM(pay_holdback_amount)+SUM(settlement_limit_amount) AS holdback,
         SUM(pay_settle_amount) AS pay_settle, SUM(settle_amount) AS settle_amount, COUNT(*) AS n
  FROM naver_settle_daily WHERE channel='NAVER' AND settle_expect_date BETWEEN '2026-08-05' AND '2026-09-18';
  ```
- 3) DB 건별(커널 `_case_scope` 598 과 같은 술어):
  ```sql
  SELECT COUNT(*) AS case_count, SUM(pay_settle_amount) AS pay_settle, SUM(settle_expect_amount) AS expect_amt,
         COUNT(*) FILTER (WHERE match_status='UNMATCHED') AS unmatched
  FROM naver_settle_case WHERE channel='NAVER'
    AND COALESCE(settle_expect_date, search_date) BETWEEN '2026-08-05' AND '2026-09-18';
  ```
- 4) CSV: `GET /api/settlement/channel/export.csv?kind=daily&from=2026-08-05&to=2026-09-18` → `OUT/w1_daily.csv`; `kind=case&basis=expect` → `OUT/w1_case.csv`; `kind=sheet&basis=expect` → `OUT/w1_sheet.csv`. 파이썬 `csv`(encoding utf-8-sig) 로 읽어 "정산 금액"(완료일 유무로 갈라)·"결제 정산 금액"·시트 "정산기준금액" 합을 Decimal 로.
- 통과 기준: ①=②=④(daily) 원 단위 동일, reconcile.daily_total=②pay_settle, reconcile.case_total=③pay_settle=④(case)=④(sheet 정산기준금액 합), case_count 동일, Σledger.groups.amount=③expect_amt. 하나라도 다르면 어느 층(API/DB/CSV)이 어긋나는지 특정하고 그 행을 `product_order_id` 단위로 좁혀 적는다.
- 음성 대조군: `to=2026-09-17` 로 하루 줄여 재조회 → 차이 = `settle_expect_date='2026-09-18'` 행의 합과 정확히 같은지(창 술어가 끝 포함인지). 또 `SELECT channel, COUNT(*) FROM naver_settle_daily GROUP BY 1` 로 NAVER 외 채널 0건(대조군이 모집단 안임을 보이기).
- 함정: CSV 는 BOM 첫 줄. 시트 CSV 는 `EXPORT_KINDS` 밖 별도 레지스트리라 `kind=sheet` 별칭. per_page 상한 200 이라 원장 합은 `ledger.groups` 합(기간 전체)으로 본다.

A-2 워터폴·대사
- 5) `OUT/w1_api_default.json` 의 waterfall 7단: Σ(1~6단) 과 7단(settle_amount) 차이를 계산. 차이가 0 이 아니면 그 잔차가 워터폴에 없는 컬럼 합과 같은지 DB 로 확인:
  ```sql
  SELECT SUM(difference_settle_amount), SUM(return_care_settle_amount), SUM(preferential_commission_amount),
         SUM(normal_settle_amount), SUM(quick_settle_amount) FROM naver_settle_daily
  WHERE channel='NAVER' AND settle_expect_date BETWEEN '2026-08-05' AND '2026-09-18';
  ```
  7단 settle_amount 가 "정산 완료액" KPI(settled_amount)와 같은지, settled+expected 인지 명시. 워터폴 마지막 단이 KPI 타일 어느 것과도 같지 않으면 Presentation WARN.
- 6) `_build_reconcile` 734~749 인용해 허용 오차 0 임을 확인(코드 근거). 스테이징 실측에서 diff≠0 이면 `exceptions` 에 `COUNT_MISMATCH` 1건이 있는지(945~968), diff=0 이면 없는지(음성 대조군).
- 통과 기준: 오차 0 코드 확인 + 실측 diff 값과 예외 큐 상태 일치.

A-3 이전 기간 길이
- 7) API 3회: (a) `from=2026-08-01&to=2026-08-31&granularity=month`, (b) `from=2026-09-01&to=2026-09-30&granularity=month`, (c) `from=2026-02-01&to=2026-02-28&granularity=month`. 각 응답의 `daily_prev` 버킷 키와 `kpi.prev` 기록. `_previous_range` 322 는 일수 동일 규칙 → (b) 직전 = 08-02~08-31(30일, 8/1 제외), (c) 직전 = 01-04~01-31. DB 로 8/1 하루 합계를 구해 `kpi.prev.settled_amount+expected_amount` 가 8월 전체 합과 정확히 그만큼 다른지 증명.
- 통과 기준: `channel.js` 에서 `prev`·`전기`·`직전`·`전월` grep — "전월" 로 읽히는 라벨이면 Cut-off WARN, "직전 같은 길이" 로 표기돼 있으면 PASS(문구 인용).
- 음성 대조군: (a) 31일 vs 7월 31일은 길이가 같아 달력 월과 일치함을 보인다.

A-4 취소·환급 행 부호
- 8) 표본:
  ```sql
  SELECT id, search_date, settle_expect_date, product_order_id, settle_type, pay_settle_amount, settle_expect_amount
  FROM naver_settle_case WHERE channel='NAVER'
    AND settle_type IN ('NORMAL_SETTLE_AFTER_CANCEL','NORMAL_SETTLE_BEFORE_CANCEL','QUICK_SETTLE_CANCEL','QUANTITY_CANCEL_RESTORE')
    AND COALESCE(settle_expect_date, search_date) BETWEEN '2026-08-05' AND '2026-09-18'
  ORDER BY settle_expect_date DESC LIMIT 5;
  ```
  하나를 골라 (i) API `ledger=case&q=<product_order_id>` 행의 `pay_settle_amount` 부호·`settle_type_label`, (ii) `OUT/w1_case.csv` 의 같은 행, (iii) 그 예정일 하루 `SUM(pay_settle_amount)`(case) vs 같은 날 `naver_settle_daily.pay_settle_amount` 동일 여부. 같은 날 daily 행에 `settle_amount<0` 이 있으면 `exceptions` 에 `NEGATIVE` 항목으로 나오는지.
- 음성 대조군: `settle_type='NORMAL_SETTLE_ORIGINAL'` 양수 행 1건이 세 층에서 양수로 같은지.
- 통과 기준: 세 층 모두 부호·금액 동일, 상계·절대값 없음.

A-5 부가세
- 9) 관계 검사:
  ```sql
  SELECT date_trunc('month', settle_basis_date) m, SUM(total_sales_amount) ts, SUM(taxation_sales_amount) tx, SUM(tax_exemption_sales_amount) te,
         SUM(credit_card_amount)+SUM(cash_income_deduction_amount)+SUM(cash_outgoing_evidence_amount)+SUM(cash_exclusion_issuance_amount)+SUM(other_amount) AS by_evidence,
         BOOL_AND(is_final) all_final, COUNT(*) n
  FROM naver_vat_daily WHERE channel='NAVER' GROUP BY 1 ORDER BY 1;
  SELECT d.settle_basis_date, d.total_sales_amount, c.s FROM naver_vat_daily d
  LEFT JOIN (SELECT settle_basis_date, SUM(total_sales_amount) s FROM naver_vat_case WHERE channel='NAVER' GROUP BY 1) c USING (settle_basis_date)
  WHERE d.channel='NAVER' AND d.total_sales_amount <> COALESCE(c.s,0) LIMIT 20;
  SELECT date_trunc('month', settle_basis_date) m, SUM(pay_settle_amount) FROM naver_settle_case WHERE channel='NAVER' GROUP BY 1 ORDER BY 1;
  ```
  API `ledger=vat_case&from=2026-08-01&to=2026-08-31` 의 `vat.total`·`vat.final`·`vat.available_to` 기록.
- 판정: ts=tx+te, ts=by_evidence 성립 여부, 세액·공급가액 컬럼 부재(모델 3851~3880) → 회계팀이 과세매출/세액 전표를 만들려면 `taxation_sales×10/110` 을 손으로 계산해야 함. 네이버 API 형상이므로 결함이 아니라 `결정 재고` 후보("파생 세액 표시 허용 여부")로 적는다.

C-1 8월 정산액 3축
- 10) 예정일 8월: API `from=2026-08-01&to=2026-08-31` kpi.settled_amount+expected_amount 와 DB `SUM(settle_amount)`(예정일 창). 완료일 8월: `SELECT SUM(settle_amount), COUNT(*) FROM naver_settle_daily WHERE channel='NAVER' AND settle_complete_date BETWEEN '2026-08-01' AND '2026-08-31'`. 결제일 8월(건별): `SELECT SUM(pay_settle_amount), SUM(settle_expect_amount), COUNT(*) FROM naver_settle_case WHERE channel='NAVER' AND pay_date BETWEEN '2026-08-01' AND '2026-08-31'`. 기준일 8월: `settle_basis_date` 로 동일. 원장 축으로도 교차: API `ledger=case&basis=complete|pay|basis` 의 `Σledger.groups.amount` 와 `ledger.axis.excluded/shifted_out` 기록.
- 11) 회계팀 조작 경로를 문장으로: "8월 정산액(예정일)" = 상단 KPI, "완료일 8월" = 원장 축 전환 후 그룹 합을 손으로 더해야 함(KPI 없음). 설명 문구는 파셜 74행 한 줄뿐. 판정은 "CFO 가 세 숫자를 한 화면에서 얻을 수 있는가"(권고는 KPI 재집계가 아니라 **원장 축별 합계 한 줄** 또는 문구 수준으로 한정).
- 음성 대조군: 예정일 8월 합과 완료일 8월 합이 다름을 숫자로 보이되, 교집합(`settle_expect_date BETWEEN … AND settle_complete_date BETWEEN …`) 합은 양쪽에 동일하게 들어감을 보인다.

C-2 월 경계 KST/UTC
- 12) 컬럼은 `Date`(TZ 없음, 모델 3676~3679), 파서 `parse_settle_date` 270 이 `text[:10]`. 원문 대조(raw 키 이름은 `SELECT jsonb_object_keys(raw_snapshot) FROM naver_settle_daily LIMIT 1` 로 먼저 확인):
  ```sql
  SELECT settle_expect_date, raw_snapshot->>'settleExpectDate' raw_expect, raw_snapshot->>'settleCompleteDate' raw_complete
  FROM naver_settle_daily WHERE channel='NAVER' AND settle_expect_date IN ('2026-07-31','2026-08-01','2026-08-31','2026-09-01');
  SELECT COUNT(*) FROM naver_settle_daily WHERE channel='NAVER' AND left(raw_snapshot->>'settleExpectDate',10) <> settle_expect_date::text;
  SELECT COUNT(*) FROM naver_settle_case WHERE channel='NAVER' AND left(raw_snapshot->>'payDate',10) <> pay_date::text;
  SELECT COUNT(*) FROM naver_settle_daily WHERE channel='NAVER' AND raw_snapshot->>'settleExpectDate' ~ 'T';
  ```
- 13) `_bucket_key` 344 + API `granularity=month&from=2026-08-31&to=2026-09-01` → daily 버킷이 `2026-08-01`·`2026-09-01` 두 개이고 각각 그 하루 합과 같은지.
- 통과 기준: 불일치 0건 + 원문에 시각 없음(있으면 KST 날짜인지 판단). 음성 대조군: 원문과 컬럼이 같은 행 수(전체 n)를 같이 적는다.

C-3 시차 지표
- 14) 화면·API 에 "지급 소요일" 류 지표 없음을 `channel.js`·커널 grep(`소요`·`lag`·`days_to`)으로 확인. 최소 형태 계산:
  ```sql
  SELECT COUNT(*) n, AVG(settle_complete_date - pay_date) avg_days, percentile_cont(0.5) WITHIN GROUP (ORDER BY settle_complete_date - pay_date) med, MAX(settle_complete_date - pay_date) mx
  FROM naver_settle_case WHERE channel='NAVER' AND pay_date IS NOT NULL AND settle_complete_date IS NOT NULL AND settle_type='NORMAL_SETTLE_ORIGINAL';
  SELECT AVG(settle_complete_date - settle_expect_date), COUNT(*) FILTER (WHERE settle_complete_date > settle_expect_date) late FROM naver_settle_daily WHERE channel='NAVER' AND settle_complete_date IS NOT NULL;
  ```
  제안: "평균 지급 소요일(결제일→완료일)" 타일 1개 — 날짜 차이는 금액 재계산이 아니므로 D-4 와 충돌 없음. 심각도 WARN 이하(제안).

### 6.2 W2 — B(완전성) + F(운영 신뢰성)
산출: `OUT/findings_w2.md`, `OUT/w2_*.json`, `OUT/w2_staging_batch.py`, `OUT/w2_production_batch.py`, `OUT/w2_production.json`.
접속: 스테이징 DB(readonly, 여러 번 가능) + **운영 DB 1회 배치** + 스테이징 API `?view=strip` 1회. 브라우저·full API 금지.

B-1 날짜 구멍
- 1) 스테이징:
  ```sql
  WITH days AS (SELECT d::date AS d FROM generate_series('2026-01-01'::date, '2026-09-04'::date, '1 day') d),
       have AS (SELECT settle_expect_date d, COUNT(*) n, SUM(settle_amount) s FROM naver_settle_daily WHERE channel='NAVER' GROUP BY 1)
  SELECT days.d, EXTRACT(dow FROM days.d) dow, COALESCE(have.n,0) n, have.s FROM days LEFT JOIN have USING (d) ORDER BY 1;
  ```
  구멍(n=0)을 요일별로 집계, 평일 구멍 목록 별도(2026 공휴일 표를 스크립트에 넣어 분류). 평일 구멍이 있으면 어느 run 의 scope 안이었는지 `naver_settle_sync_runs.scope->>'from'/'to'` 로 교차.
- 2) 화면이 구멍을 말하는가: `_build_daily` 484~519 — 창 안에 행이 하나라도 있으면 빈 날은 0 으로 채움, 행이 0 이면 `[]`. "정산 없음" 과 "적재 실패" 를 일별 차트가 구분하지 못함을 코드 근거로 적고, 구분 신호가 `sync.coverage_*`·`last_ok_at` 뿐임을 명시(구조 결함으로 분류, 화면 결함으로 쓰지 않음).
- 통과 기준: 평일 구멍 0건이면 PASS(대조군: 주말 구멍 수 N 을 같이 적어 술어가 살아 있음을 보인다).

B-2 30일 창 밖 소급·보류 해제 짝
- 3) 코드 근거: `skip_day` 442~444 + `is_finalized` 544, `replace_partition` 350. 문서: `docs/plans/2026-09-02-naver-settlement-contracts.md`·`-v1.1-contracts.md` 에서 `확정`·`FINALIZED`·`30일` grep — 리스크가 문서에 있는지, 화면엔 `final_before`("확정 구간 ~", channel.js 1010 부근) 한 줄뿐인지.
- 4) 보류-해제 짝(스테이징):
  ```sql
  WITH h AS (SELECT id, settle_expect_date d, pay_holdback_amount a, settle_method_type FROM naver_settle_daily WHERE channel='NAVER' AND pay_holdback_amount <> 0)
  SELECT neg.d, neg.a, (SELECT MIN(pos.d) FROM h pos WHERE pos.a = -neg.a AND pos.d > neg.d) AS released_on
  FROM h neg WHERE neg.a < 0 ORDER BY neg.d;
  ```
  집계: 보류 음수 행 수·합, 해제 짝 있는 수·합, **짝 없는 수·합**, 짝 없는 것 중 `d < '2026-08-05'` 수·합, 최장 보류 기간. 짝은 파이썬으로 1:1 소비(같은 금액 중복 매칭 방지). `settlement_limit_amount<>0` 행 수가 0 임을 확인만(결정 사항).
- 5) `SELECT id, started_at, status, trigger, jsonb_array_length(COALESCE(stats->'retro_changes','[]')) FROM naver_settle_sync_runs ORDER BY started_at DESC LIMIT 30` — retro_changes 의 date 가 전부 run 시점 −30일 이내인지(창 밖은 안 본다는 증거).
- 통과 기준: 짝 없는 보류 합이 0 이면 PASS, 아니면 금액 실측 + Completeness WARN(원인 구분 불가 사실을 적는다). 음성 대조군: 짝이 있는 표본(6/19↔8/27 류) 1건 인용.

B-3 창 경계
- 6) `OUT/w2_windows_test.py`: 워크트리 import 로 `split_windows`·`iter_days` — (a) 2026-01-01~2026-09-18 을 30·28일로 나눈 합집합 = `iter_days`, 교집합 0(집합 비교), (b) 경계: 길이 28·29·56·57, 시작=끝, 끝<시작(→`[]`), size=1·0(`max(1,…)`), (c) 무작위 200 구간 property. `_sync_settle_daily` 630~660 이 `set(iter_days)|set(grouped)` 로 응답 밖 날짜도 비우는지, `client.get_settle_daily` 825~848 의 startDate/endDate 끝 포함 여부(`docs/research/2026-09-02-naver-settlement/01-naver-settle-api-spec.md` 인용).
- 음성 대조군: 잘못된 입력(end<start)이 빈 목록, size 0 이 자기 보호.
- 통과 기준: 중복 0·누락 0·경계 케이스 통과.

B-4 배너 사각(잘린 백필의 빈 구간)
- 7) 스테이징 월별 분포:
  ```sql
  SELECT to_char(settle_expect_date,'YYYY-MM') m, COUNT(*) n, COUNT(DISTINCT settle_expect_date) days, SUM(settle_amount) s, MIN(synced_at), MAX(synced_at) FROM naver_settle_daily WHERE channel='NAVER' GROUP BY 1 ORDER BY 1;
  SELECT to_char(search_date,'YYYY-MM') m, COUNT(*) n, COUNT(DISTINCT search_date) days FROM naver_settle_case WHERE channel='NAVER' GROUP BY 1 ORDER BY 1;
  SELECT to_char(search_date,'YYYY-MM') m, COUNT(*) n FROM naver_settle_commission WHERE channel='NAVER' GROUP BY 1 ORDER BY 1;
  SELECT to_char(settle_basis_date,'YYYY-MM') m, COUNT(*) n, BOOL_AND(is_final) FROM naver_vat_daily WHERE channel='NAVER' GROUP BY 1 ORDER BY 1;
  SELECT setting_value FROM system_settings WHERE setting_key='naver_settle_sync_state';
  SELECT id, started_at, finished_at, status, trigger, scope, stats->'rows' rows, left(error,80) err FROM naver_settle_sync_runs ORDER BY started_at DESC LIMIT 40;
  ```
  판정: `coverage_from` 이후 달 중 daily days < 그 달 평일 수의 절반 또는 case 0 인 달 = 배너가 못 잡는 빈 구간. RUNNING 잔류 run 의 scope 가 그 달을 덮는지 교차(RUNNING 자체는 재보고 금지).
- 8) `channel.js:2128` 배너 술어 `from < sync.coverage_from` 인용 → 빈 구간에 `from` 을 두면 배너가 안 뜸(구조 결함).
- 9) **운영 DB 1회 배치** `OUT/w2_production_batch.py`: 7)의 6개 SQL + 1)의 날짜 구멍 요약 + 4)의 보류 짝 집계(수·합만) + `SELECT status, COUNT(*) FROM naver_settle_sync_runs GROUP BY 1`. 결과 `OUT/w2_production.json`(숫자·날짜만, error 는 앞 80자·URL/토큰 마스킹).
- 통과 기준: 스테이징·운영 모두 coverage 안 빈 달 0 이면 PASS. 음성 대조군: coverage_from 이전 달에 행 0 이고 그 구간은 배너 술어가 참.

F-1 신선도
- 10) API `?view=strip&from=2026-08-05&to=2026-09-18` 1회 → `sync` 블록 `OUT/w2_strip.json`. 코드 `_build_sync` 412~441(stale 36h, never), `channel.js` 985~1010(세 모드 문구), `sync.status`=워터마크 `last_status` — RUNNING 은 워터마크에 안 쓰여 **진행 중 표시 없음**. 워커 사망 시나리오 계산: 05:30 KST OK 뒤 다음 날 05:30 누락 → 36h 경과는 이틀째 17:30 KST → 하루치 누락이 최대 약 36시간 "정상" 으로 보임(시간 수치로 기록). 판정: 일 1회 스케줄 대비 임계값 크기(회계팀 관점 WARN 후보).
- 음성 대조군: `test_settlement_channel_api.py:443`·433 인용(실행은 W4).

F-2 재배포 중 [지금 동기화]
- 11) 코드만: `queue.py:512~549`, API 297~333(queued=False 도 200, 큐 부재 503), `channel.js:2077~2093`('이미 대기 중…'), `startRevPoll` 2150~2183(60초/10분 뒤 '반영되지 않았습니다…' 경고). 세 문구 인용 + "폴링 종료 뒤 처리돼도 화면은 다시 알리지 않는다" 기록. 근거 `test_sync_reports_already_queued_without_lying` 550. 버튼·POST 금지.

F-3 실패 경로
- 12) `_drive` 786~803 모든 Exception→FAILED(403/429/5xx 가 예외로 오르는지 `client.py _request` 확인 — 429 재시도 분기 유무). `_sync_window` 805~816 창마다 commit. `_finish` 830~849 FAILED 에서도 `commit()` → 실패 창의 미커밋 파티션(daily 창 전체 교체 완료·case 는 실패 전 날짜까지)이 함께 커밋 → 다음 OK 까지 daily↔case 불일치 가능. `_run_exceptions` 945~968 은 RETRO·COUNT_MISMATCH 만 → **FAILED run 은 예외 큐에 안 실림**, 헤더 부제 "상태 FAILED"(ok 모드일 때만) 뿐 → 코드 근거 WARN. 스테이징 `SELECT status, COUNT(*), MAX(started_at) FROM naver_settle_sync_runs GROUP BY 1` + FAILED error 앞 80자.
- 음성 대조군: OK run 뒤 워터마크 `last_status='OK'`·`last_error` null.

F-4 워커 적재 뒤 웹 캐시
- 13) strip 응답 헤더(`Cache-Control`·`ETag`·`Vary`). 코드: API 에 캐시 데코레이터·ETag 없음(export 만 no-store), 프래그먼트는 `apply_erp_shell_fragment_headers`(`settlement_dashboard.py:121`) 지만 값은 API. 서비스워커 `static/sw.js`(또는 `static/js/sw*.js`) 에서 `/api/` 캐시 분기 grep. 워커 `tasks.py:600~650` 세션 훅 없음 → 이 API 가 `table_version`·`cache_version` 을 읽는지 grep(안 읽으면 영향 0).
- 통과 기준: API 캐시 없음 + SW 가 `/api/settlement` 미캐시. 음성 대조군: SW 가 캐시하는 정적 경로 분기 인용.

### 6.3 W3 — D(존재·권리) + E(통제·감사 추적)
산출: `OUT/findings_w3.md`, `OUT/w3_*.json`, `OUT/w3_staging_batch.py`, `OUT/w3_production_batch.py`, `OUT/w3_production.json`, `OUT/w3_match_diff.py`.
접속: 스테이징 API(requests, 로그인/비로그인 두 세션) + 스테이징 DB(readonly, ORM 허용) + **운영 DB 1회 배치**. 브라우저 금지.

D-1 미매칭 채권 금액·aging·붙일 수 있는 비율
- 1) 스테이징에서 SQL 완성(운영 배치 초안):
  ```sql
  SELECT match_status, (link_id IS NOT NULL) linked, COUNT(DISTINCT product_order_id) po, COUNT(*) rows,
         SUM(pay_settle_amount) pay, SUM(settle_expect_amount) expect,
         SUM(CASE WHEN settle_complete_date IS NOT NULL THEN settle_expect_amount ELSE 0 END) completed
  FROM naver_settle_case WHERE channel='NAVER' AND product_order_type='PROD_ORDER' GROUP BY 1,2;
  SELECT CASE WHEN '2026-09-04'::date - COALESCE(settle_expect_date,search_date) < 30 THEN '<30'
              WHEN '2026-09-04'::date - COALESCE(settle_expect_date,search_date) < 60 THEN '30-59'
              WHEN '2026-09-04'::date - COALESCE(settle_expect_date,search_date) < 90 THEN '60-89' ELSE '90+' END bucket,
         COUNT(DISTINCT product_order_id) po, SUM(settle_expect_amount) amt
  FROM naver_settle_case WHERE channel='NAVER' AND match_status='UNMATCHED' GROUP BY 1 ORDER BY 1;
  ```
- 2) 붙일 수 있는 비율: `SELECT jsonb_object_keys(raw_snapshot) FROM external_order_links WHERE channel='NAVER' LIMIT 1` 로 수령인·전화 키 경로 확정 후:
  ```sql
  WITH u AS (SELECT DISTINCT c.product_order_id, c.link_id, c.purchaser_name, l.raw_snapshot r
             FROM naver_settle_case c LEFT JOIN external_order_links l ON l.id=c.link_id
             WHERE c.channel='NAVER' AND c.match_status='UNMATCHED')
  SELECT COUNT(*) total, COUNT(*) FILTER (WHERE r IS NOT NULL) has_link,
         COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM orders o WHERE regexp_replace(o.phone,'[^0-9]','','g') = regexp_replace(u.r#>>'{<전화키>}','[^0-9]','','g'))) phone_hit,
         COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_name = COALESCE(u.r#>>'{<수령인키>}', u.purchaser_name))) name_hit
  FROM u;
  ```
  (orders 의 전화·이름·삭제 플래그 컬럼명은 `models.py` Order 클래스에서 먼저 확인.) 결과는 비율만.
- 3) 화면 KPI 는 건수만(`unmatched_pending_count`·`unmatched_unlinked_count`, 커널 653~681) 이고 금액 타일 없음 → 채권 관리 관점 WARN 후보(권고: 예외 큐 금액 합계 줄 — `settle_expect_amount` 원값 합, 재집계 아님).
- 4) **운영 DB 1회 배치** `OUT/w3_production_batch.py`: 1)·2)·3) + D-3 6)의 SQL 부분 + E-5 해시 1행 을 한 연결·한 트랜잭션. 출력 숫자만.
- 음성 대조군: `match_status='MATCHED'` 행에 같은 전화 술어 → hit 율 ≈100%; `product_order_type<>'PROD_ORDER'` 는 전부 `NA`.

D-2 예외 큐 상한
- 5) 로그인 세션 `GET /api/settlement/channel?from=2026-01-01&to=2026-09-18&ledger=case` → `exceptions` kind 별 수(UNMATCHED·UNLINKED·HOLDBACK·LIMIT·NEGATIVE·RETRO·COUNT_MISMATCH) vs KPI 전체 수(`unmatched_pending_count`·`unmatched_unlinked_count`·`holdback.count`). 코드: `_unmatched_rows` 901~912 갈래별 50, `_daily_exceptions` 883~899 **세 종류 합쳐 50** — NEGATIVE·LIMIT 전체 건수는 API 어디에도 없음. `channel.js` 에서 `중`·`표시`·`상한`·`50` grep 으로 "N건 중 M건" 문구 유무(스크린샷은 W4 `OUT/w4_exceptions_header.png` 가 있으면 참조, 없어도 판정 성립).
- 음성 대조군: `from=2026-09-01&to=2026-09-18` 로 좁혀 50 미만인 kind 의 수 = KPI 수.
- 통과 기준: 모든 kind 에 전체 수를 말할 수 있으면 PASS, 아니면 Completeness WARN(침묵 kind 명시).

D-3 매칭 건 정산액 ≠ 출고가
- 6) `OUT/w3_match_diff.py`(워크트리 import, 스테이징 readonly ORM): `SELECT foms_order_id, SUM(pay_settle_amount) pay, SUM(settle_expect_amount) expect, COUNT(*) n, BOOL_OR(settle_type<>'NORMAL_SETTLE_ORIGINAL') has_cancel FROM naver_settle_case WHERE channel='NAVER' AND match_status='MATCHED' GROUP BY 1` → 각 주문 `structured_data` 로 `erp_shipping_price_from_structured(sd)`(`foms/services/erp_display.py:297`) 출고가 산출 → `pay`·`expect` 와 비교. 집계: 주문 수, 일치, 불일치 수·차액(절대합·부호합), 불일치 중 취소 포함 비율, 출고가 None 수. 운영 배치엔 SQL 집계(주문 수·합)만 넣고 출고가 대조는 스테이징 결과로 판정(표본 차이 명시).
- 7) 화면 예외 kind 에 금액 차이 없음(883~968). `foms/services/settlement_rows.py:149 _naver_settle_map`·210 `_naver_settlement_cell` 이 출고가 대비 차이를 표시하는지(필드 인용). 없으면 Existence/Accuracy WARN(차액 표시 여부는 `결정 재고`).
- 음성 대조군: 일치 표본 1건 + 부분 취소 불일치 표본 1건.

E-1 권한
- 8) 실측 2행: (a) 로그인 세션 → `GET /erp/settlement` 200 + 본문 `data-settlement-ch-root`, `GET /api/settlement/channel?view=strip&from=2026-08-05&to=2026-09-18` 200, `GET /api/settlement/channel/export.csv?kind=daily&from=2026-08-05&to=2026-09-18` 200 text/csv(이 1건이 E-2 양성 표본). `POST /sync` 호출 금지(코드 297~333 인용). (b) 비로그인 세션 → 페이지·API·export 응답 코드(`test_anonymous_is_not_served` 188 계약과 대조). 계약 매트릭스: `settlement_channel_access.py:44~66` + `test_settlement_channel_access.py:76` 파라미터 목록 + 83 + `order_mutation_policy.py:336~338`(gate 가 352~355 override 보다 먼저). 추가: `grep -rn "team == 'ACCOUNTING'\|team == \"ACCOUNTING\"\|== 'ACCOUNTING'" foms/` 로 `normalize_team` 을 안 거치는 직접 비교 게이트 유무.
- 음성 대조군: 로그인 200 응답이 `data.strip.tab_key=='channel'` 을 담음.
- 통과 기준: 실측 2행 + 계약 매트릭스 전 조합 SSOT 일치.

E-2 감사 로그
- 9) 코드: `POST /sync` 316~324 행위자 O, detail={queued, backfill_from, channel} — **실효 창(from/to)·run_id 없음**. `_log_export` 355~381 행위자·kind·channel·from·to·basis(실효) O, 행수 X(의도). 라벨 `audit_message_display.py:174~175`.
  ```sql
  SELECT action, COUNT(*), MAX(timestamp), COUNT(*) FILTER (WHERE user_id IS NULL) no_actor FROM security_logs WHERE action IN ('NAVER_SETTLE_SYNC_REQUEST','NAVER_SETTLE_EXPORT_CSV') GROUP BY 1;
  SELECT timestamp, user_id, detail FROM security_logs WHERE action='NAVER_SETTLE_EXPORT_CSV' ORDER BY timestamp DESC LIMIT 5;
  ```
  8)(a) 의 export 1건이 `user_id=58`·kind='settle_daily'·basis='expect' 로 남았는지.
- 음성 대조군: 조회 GET 은 감사 행을 남기지 않음(조회 직후 최신 행 불변).
- 판정: sync 감사 행에 구간·run 연결키 없음 → 추적성 WARN 후보.

E-3 계좌번호 마스킹
- 10) (a) API full(`OUT/w3_api_full.json`, 창 2026-08-05~09-18): `deposit_channels[*].account_no_masked` 형식 `^\*{4}.{4}$`, 응답 전체 문자열에 `\d{10,}` 및 DB 에서 메모리로만 가져온 실계좌 앞부분 검색 0건. 원장 `raw`(1082행) 는 case/commission/vat_case — `naver_settle_case.raw_snapshot` 키에 계좌 없음 확인. (b) CSV daily "계좌번호(마스킹)" 열 전 행 형식. (c) 화면은 API 값이라 (a) 로 갈음. (d) 새는 경로 음성 대조군: `security_logs.detail::text ~ '<뒤4자리>'` 0건, export 400 본문(`kind=daily&type=X`) 값 없음, `CSV_COLUMNS` 304~309 에 raw 열 없음.
- 통과 기준: 원문 노출 경로 0.

E-4 쓰기 경로
- 11) `grep -rn "replace_partition\|run_settle_sync\|settle_sync import" foms/ app.py scripts/` → 호출자가 `settle_sync.py`·`jobs/tasks.py:629`·`scripts/maintenance/run_naver_settle_sync.py` 뿐인지. 웹에서 `foms.services.jobs.tasks` import 위치와 정산 태스크 직접 호출 여부. route manifest 에 `/api/settlement/channel` 하위 mutation 이 `POST /sync` 하나인지(`grep -rn "settlement_channel" foms/services/*manifest*.py tools/harness/*.py`). `is_naver_settle_sync_enabled`(`feature_flags.py:431`) 가 막는 쪽.
- 통과 기준: 웹 프로세스 파티션 쓰기 경로 0 + POST 는 enqueue+감사뿐.

E-5 비밀번호 로테이션(해시 대조)
- 12) 스테이징 `SELECT username, password, role, is_active FROM users WHERE username='claude_master'` → `werkzeug.security.check_password_hash(row.password, secrets.staging.password)` True/False 만. `security_logs` 에서 2026-09-01~04 해당 user_id 의 비밀번호·USER_UPDATE 류 action. 운영은 4)의 배치 안에서 같은 1행을 가져와 secrets.production 과 대조 → True/False + `is_active`.
  판정: 노출 시점(2026-09-02) 비밀번호와 여전히 일치(True)면 "미로테이션" WARN.
- 음성 대조군: 틀린 문자열로 `check_password_hash` False 1회.

### 6.4 W4 — G(표시·내보내기) + H(성능·구조 부채) + pytest
산출: `OUT/findings_w4.md`, `OUT/w4_*.json`, `OUT/w4_*.png`, `OUT/w4_pytest.txt`, `OUT/w4_explain_*.txt`.
접속: gstack browse(유일 사용자), 스테이징 API(TTFB·8월 창 CSV 형식만), 스테이징 DB(EXPLAIN·질의 수), 워크트리 pytest.

- 0) 시작 즉시 백그라운드: `cd C:/tmp/foms-s-settle-cfo && pwd && PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/domains -k settlement -q -p no:cacheprovider > "$OUT/w4_pytest.txt" 2>&1` — 첫 줄·마지막 줄 원문. 기준선 922 passed. 실패는 이름·assert 원문(수정 금지).

G-1 라벨 전수 → 전표 매핑
- 1) 라벨 원천 3곳: KPI·워터폴·대사·보류(`channel.js` 의 `label:`·`'정산 완료액'`·`'정산 예정액'` grep + 커널 `_WATERFALL_STEPS` 172~180·`BASIS_LABELS`), CSV 헤더(`settlement_channel_export.py` 191~314), 시트 7열(316~324). 각 라벨에 전표 계정 한 줄. 막히는 라벨 후보: "정산 완료액"(확정액 vs 실입금액, CHARGE_AMT 상계 포함 — `_daily_totals` 529), "보류·한도"(당기 순증감이지 잔액 아님, 551~596), "정산 금액"/"결제 정산 금액"/"정산기준금액"(시트가 pay_settle_amount 를 '정산기준금액' 이라 부름), 건별 "정산 예정 금액" vs KPI "정산 예정액".
- 스크린샷 `OUT/w4_kpi.png`(로그인 → `/erp/settlement` → `data-settlement-tab="channel"` 클릭, 로드 직후 `$B text`), `$B console`·`$B network` → `OUT/w4_console_kpi.txt`(잡음 2종 제외 오류 0).
- 판정: 전표 한 줄을 못 쓰는 라벨 1개 이상 → Presentation WARN(라벨별).

G-2 CSV 형식
- 2) `OUT/w4_csv_check.py`: **8월 창(2026-08-01~08-31)** 으로 `kind=daily`·`case`·`sheet`·`vat_daily`·`commission` 바이트 저장 → 첫 3바이트 `EF BB BF`, `\r\n`, 금액 `^-?\d+(\.\d+)?$`, 날짜 `^\d{4}-\d{2}-\d{2}$`, `Content-Disposition` 파일명(case `basis=complete` 슬러그, `sheet&basis=pay` 슬러그, vat 무슬러그), 헤더 순서 = `CSV_COLUMNS`/`SHEET_COLUMNS`.
- 3) 시트 7열 vs 최소 열(거래일·거래처·공급가·세액·합계·계정) 있음/없음 표. 부재 열은 네이버 원본 부재(세액) 또는 사용자 확정 7열 → `결정 재고`("거래처=NAVER 상수 열·계정 열 추가"). 음수 `-389000` 형식 근거 `_fmt_money` 359.
- 음성 대조군: `kind=daily&type=X` → 400 JSON, 비로그인 export → JSON 401/403(파일 아님).

G-3 150% SVG 라벨 겹침(실화면)
- 4) `$B viewport 1440x900` → 채널 탭 → 조절기(`data-settlement-fs*`) `+` 로 150% → `OUT/w4_150_chart.png`·`OUT/w4_150_waterfall.png`. JS: `$B js` 로 각 `svg text` 의 `getBoundingClientRect()` 교차 쌍 수 → `OUT/w4_150_overlap.json`. 100% 복귀 후 같은 측정(음성 대조군: 0). 가로 스크롤(`scrollWidth>clientWidth`).
- 판정: 150% 교차 >0 이면 수용 리스크 재확인 결과(원장 F6 후속에 기록됨) — 새 결함 격상 금지, 읽을 수 없는 수준이면 Presentation WARN.

G-4 다크 테마
- 5) `settlement-channel.css:20` 주석 + `grep -n "prefers-color-scheme\|data-theme\|\.dark" static/css/foundation/erp-pro.css static/css/settlement/*.css`. 셸에 다크 토큰이 있으면 `$B js` 로 토글 후 `OUT/w4_dark.png`; 없으면 "요약 대시보드 v1 미결과 동일 범위" 로 기록. 채널 CSS 하드코딩 색(`#fff`·`#000`·`rgb(`) 수 = 부채 지표.

H-1 성능
- 6) `OUT/w4_query_count.py`: 워크트리 import + 스테이징 readonly `Session`, `event.listen(engine,"before_cursor_execute",…)` 로 문장 수: `build_channel_strip(date_from=2026-08-05, date_to=2026-09-18, today=2026-09-04)`(예산 6, 1271 docstring), `build_channel_dashboard(… ledger='case', basis='expect')`, `basis='pay'`, `ledger='commission'`. 문장 목록 `OUT/w4_queries.sql`.
- 7) `EXPLAIN (ANALYZE, BUFFERS)`(스테이징, readonly 트랜잭션에서 SELECT 허용):
  - `SELECT * FROM naver_settle_daily WHERE channel='NAVER' AND settle_expect_date BETWEEN '2026-08-05' AND '2026-09-18' ORDER BY settle_expect_date, id`
  - `SELECT match_status, link_id IS NOT NULL, COUNT(id), SUM(pay_settle_amount) FROM naver_settle_case WHERE channel='NAVER' AND COALESCE(settle_expect_date, search_date) BETWEEN '2026-08-05' AND '2026-09-18' GROUP BY 1,2`
  - `SELECT * FROM naver_settle_case WHERE channel='NAVER' AND COALESCE(settle_expect_date, search_date) BETWEEN '2026-08-05' AND '2026-09-18' AND match_status='UNMATCHED' AND link_id IS NOT NULL ORDER BY settle_expect_date DESC, id DESC LIMIT 50`
  - `SELECT COUNT(CASE WHEN pay_date IS NULL THEN id END), COUNT(CASE WHEN pay_date IS NOT NULL AND (pay_date < '2026-08-05' OR pay_date > '2026-09-18') THEN id END) FROM naver_settle_case WHERE channel='NAVER' AND COALESCE(settle_expect_date, search_date) BETWEEN '2026-08-05' AND '2026-09-18'`
  - `SELECT settle_complete_date, COUNT(id), SUM(settle_expect_amount) FROM naver_settle_case WHERE channel='NAVER' AND settle_complete_date BETWEEN '2026-08-05' AND '2026-09-18' GROUP BY 1 ORDER BY 1 DESC`
  - 위 다섯을 1년 창(2025-10-01~2026-09-18)으로 재실행. 노드·rows·ms → `OUT/w4_explain_<name>.txt`, `pg_relation_size`·행수 병기.
- 8) TTFB(requests, 각 3회 중앙값): `GET /api/settlement/channel?from=2026-08-05&to=2026-09-18`, 1년 창 `from=2025-10-01&to=2026-09-18`, `?view=strip`, 프래그먼트 `GET /erp/settlement` + `X-FOMS-ERP-SHELL: 1` → `OUT/w4_ttfb.json`. 판정선 30일 창 <1s, 1년 창 <3s.
- 음성 대조군: `ix_nsd_channel_expect` 질의가 Index/Bitmap Scan 임을 보여 EXPLAIN 판독이 살아 있음을 증명.

H-2 함수 길이·리터럴 계약
- 9) `OUT/w4_fn_len.py`: `ast` 로 커널·export·settle_sync·API 의 함수별 줄 수(docstring 포함/제외) → 50줄 초과 목록. `channel.js` 는 `function name(`/`async function` 휴리스틱으로 상위 15개.
- 10) 리터럴 단정: `grep -n "_CHANNEL_PIN\|20260903\|function applyFontScale(\|FONT_KEY" tests/domains/test_settlement_channel_render.py tests/domains/test_settlement_font_scale.py tests/domains/test_settlement_dashboard_render.py | wc -l` + 대표 5건 인용, 정성 판정.

H-3 핀 사슬
- 11) 셸 4줄(`settlement_dashboard_body.html:20,21,423,424`=20260903d)·채널 2줄(22·425=20260903i)·`_CHANNEL_PIN`(render 72) 값 표. 잡는 테스트: render 467~476(채널 2줄), 셸 4줄 동일값은 `grep -n "20260903d\|pins ==" tests/domains/test_settlement_dashboard_render.py tests/domains/test_settlement_operations_render.py`. **`pre_push_smoke.ps1:214~241` 서브셋에 `test_settlement_*` 없음, `-Full` 만 전체** → CI(`ci.yml:109`)가 잡음. 판정: 로컬 게이트 사각 WARN, CI PASS.
- 음성 대조군: 단정식 `assert pins == {_CHANNEL_PIN}` 인용(편집 금지, 실행은 워크트리 밖 복사본에서만).

화면 공통(W3 D-2 지원, 의존 아님)
- 12) 예외 뷰(`data-settlement-ch-ledger="exceptions"`) from/to 를 2026-01-01~2026-09-18 로 입력 후 헤더·행 수 `OUT/w4_exceptions_header.png` + `OUT/w4_exceptions_text.txt`. 부가세 뷰 `vat.final=false` 표시 문구 `OUT/w4_vat.png`.
