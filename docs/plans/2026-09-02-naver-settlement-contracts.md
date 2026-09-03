# 네이버 정산 탭 — 구현 계약서 (병렬 구현 에이전트 공용 SSOT, 2026-09-02)

스펙: `docs/specs/2026-09-02-naver-settlement_SPEC.md` (사용자 승인 2026-09-02). 사용자 결정 반영:
- 탭 라벨 **"네이버 정산"**, 힌트 **"정산 예정일 기준"**. 코드 네임스페이스는 채널 중립(`channel`).
- 초기 백필 **최근 90일**(야간 수동). 열람 = **ADMIN + 신설 팀 ACCOUNTING(회계팀)** 만.
- 워크트리 `c:/tmp/foms-s-settle-naver`(브랜치 `session/settle-naver`). 다른 디렉토리로 cd 금지. `git stash` 금지. 커밋은 총괄이 한다(에이전트는 커밋 금지).

## 0. 공통 규칙
- Python: 함수 50줄 이하·docstring·타입힌트. bare except 금지. 네이버 응답 금액은 **재계산 금지**(그대로 저장). 날짜는 `Date` 컬럼(KST 문자열 그대로; DateTime 승격 금지). 새 기록 시각은 `foms.services.datetime_kst.now_utc_naive()`.
- API 응답 `{'success','data','error'}`. 프론트: 인라인 스타일·jQuery·외부 차트 라이브러리 금지, fetch try/catch + `data.success`, Jinja→JS는 `data-*` 속성.
- 상태 노드 접두어 `data-settlement-ch-*`, CSS 접두어 `.s-ch-`, id 접두어 `foms-settle-ch-`.
- **열지 않는 파일**: `static/js/settlement/dashboard.js`·`operations.js`, `static/css/settlement/settlement-dashboard.css`·`settlement-operations.css`, `templates/cs/partials/settlement_operations_body.html`, `foms/services/settlement_aggregation.py`·`settlement_rows.py`, `foms/api/cs/settlement.py`, `tests/domains/test_settlement_operations_render.py`·`test_settlement_aggregation.py`·`test_settlement_rows_api.py`·`test_settlement_dashboard_api.py`.
- 검증은 `pwd`가 워크트리인지 확인하고 실행. 테스트는 `python -m pytest <경로> -q -p no:cacheprovider`. `python -c "import app; print('APP_OK')"` 성공 필수.

## 1. 팀·정책 (담당 A3)
**실측(운영 DB 2026-09-02)**: 회계팀 배정 예정 사용자 고애희(id 41)·강은미(id 54)는 운영에서 role **MANAGER**·team CS(스테이징은 STAFF·CS). MANAGER 는 정책 엔진에서 팀보다 먼저 통과하므로 "관리자와 회계팀만"을 엔진의 `manager_ok` 로는 표현할 수 없다 → **게이트 함수가 정본**, 정책 등록은 manifest/가드용.
- `foms/web/auth/routes.py` `TEAMS` 에 `'ACCOUNTING': '회계팀'` 추가(딕셔너리 마지막). 사용자 관리 화면(add/edit/register/user_list)은 이 SSOT 를 그대로 렌더.
- `foms/services/orders/order_mutation_policy.py`:
  - 기존 `FINANCE_MUTATION`·`SETTLEMENT_DASHBOARD_READ` 의 `teams` 를 `("CS", "SALES", "ACCOUNTING")` 으로 확장(회계팀 STAFF 도 정산 대시보드 페이지·수금 확인을 써야 탭에 닿는다; 두 정책 집합은 계속 동일 — `test_settlement_policy_fields_match_finance` 계약 유지). description 갱신.
  - 추가(SETTLEMENT_DASHBOARD_READ 바로 아래): `"SETTLEMENT_CHANNEL_READ": _p("SETTLEMENT_CHANNEL_READ", teams=("ACCOUNTING",), description="채널(네이버) 정산 탭·API 열람 — 정본 판정은 settlement_channel_access.can_view_channel_settlement (ADMIN, 또는 team=ACCOUNTING 인 MANAGER/STAFF). 엔진 등록은 manifest·가드 전용.")`, `"SETTLEMENT_CHANNEL_SYNC": _p("SETTLEMENT_CHANNEL_SYNC", teams=("ACCOUNTING",), description="채널 정산 '지금 동기화' enqueue — READ 와 같은 판정, 핸들러가 게이트 함수로 재검사.")`. (`manager_ok` 기본 True 유지 — 가드는 pre-filter, 진짜 판정은 핸들러의 게이트 함수.)
- 게이트 SSOT `foms/services/settlement_channel_access.py`(신규, services 루트 플랫):
  ```python
  SETTLEMENT_CHANNEL_POLICY_ID = "SETTLEMENT_CHANNEL_READ"
  SETTLEMENT_CHANNEL_SYNC_POLICY_ID = "SETTLEMENT_CHANNEL_SYNC"
  ACCOUNTING_TEAM = "ACCOUNTING"
  def can_view_channel_settlement(user: Any) -> bool:
      """ADMIN 이거나, role 이 MANAGER/STAFF 이면서 team 이 ACCOUNTING 인 활성 사용자만. VIEWER·미인증·그 외 팀 False."""
  ```
  (`normalize_team` 은 `order_mutation_policy` 의 것을 import. `is_active` False 면 False.)
- `foms/web/cs/settlement_dashboard.py`: 페이지 뷰 컨텍스트에 `can_view_channel_settlement=can_view_channel_settlement(user)` 1 hunk 추가(두 렌더 분기 모두). 그 외 무수정.
- 테스트: `tests/domains/test_auth_finance.py`·`test_auth_enforcement.py`·`test_settlement_dashboard_api.py` 를 돌려 팀 확장으로 red 가 나는 assertion 이 있으면 **의도된 확장으로 갱신**(있는 그대로 보고). 신규 `tests/domains/test_settlement_channel_access.py`: 매트릭스 ADMIN T / MANAGER+ACCOUNTING T / STAFF+ACCOUNTING T / MANAGER+CS F / STAFF+CS F / VIEWER+ACCOUNTING F / 비활성 F / None F.
- 사용자 배정(총괄 수행, 에이전트 금지): 스테이징·운영 users.team → 'ACCOUNTING' (id 41, 54) — 코드 배포 뒤. `team` 변경은 principal-version 트리거로 세션이 무효화되므로 재로그인 안내.

## 2. 클라이언트 (담당 A2) — `foms/services/integrations/naver_commerce/client.py` 클래스 끝에 append
모두 `self._request("GET", path, params=...)` 재사용. 날짜는 `date` → `isoformat()`. `page_size` 최대 1000 초과 시 `ValueError`. 반환 = 파싱된 dict(`elements`, `pagination`) 그대로.
```python
def get_settle_daily(self, start_date: date, end_date: date, *, page: int = 1, page_size: int = 1000) -> dict
def get_settle_cases(self, search_date: date, *, period_type: str = "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
                     settle_type: Optional[str] = None, settle_decision_type: Optional[str] = None,
                     order_id: Optional[str] = None, product_order_id: Optional[str] = None,
                     page: int = 1, page_size: int = 1000) -> dict
def get_settle_commission_details(self, search_date: date, *, period_type: str = "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
                     settle_type: Optional[str] = None, settle_decision_type: Optional[str] = None,
                     order_id: Optional[str] = None, product_order_id: Optional[str] = None,
                     page: int = 1, page_size: int = 1000) -> dict
def get_vat_daily(self, start_date: date, end_date: date, *, page: int = 1, page_size: int = 1000) -> dict
def get_vat_cases(self, start_date: date, end_date: date, *, page: int = 1, page_size: int = 1000) -> dict
```
경로: `/v1/pay-settle/settle/daily`, `/v1/pay-settle/settle/case`, `/v1/pay-settle/settle/commission-details`, `/v1/pay-settle/vat/daily`, `/v1/pay-settle/vat/case`. `None` 파라미터는 보내지 않는다. enum 값은 `settle_enums.py` 의 허용 집합으로 검증(400 예방).
- 신규 `foms/services/integrations/naver_commerce/settle_enums.py`: 문서 원문(`docs/research/2026-09-02-naver-settlement/raw/*.md`)의 enum 전량을 `dict[str, str]`(코드→한글 라벨)로: `PERIOD_TYPES`, `SETTLE_DECISION_TYPES`, `SETTLE_TYPES`, `PRODUCT_ORDER_TYPES`, `COMMISSION_TYPES`, `PAY_MEANS_TYPES`, `SETTLE_METHOD_TYPES`, `BANK_TYPES`, `VAT_DETAIL_TYPES`, `VAT_STATUSES`. 추가로 `NEGATIVE_SETTLE_TYPES = frozenset({NORMAL_SETTLE_AFTER_CANCEL, NORMAL_SETTLE_BEFORE_CANCEL, QUICK_SETTLE_CANCEL, QUANTITY_CANCEL_RESTORE})`(문서 서술 근거, 부호 판정은 값 부호를 신뢰하고 이 집합은 라벨/필터용), `label(mapping, code) -> str`(미등록 코드는 코드 그대로).
- `_request` 가 `gncp-gw-quota-limit` 응답 헤더를 관측하는지 확인(`_log_rate_limit`). 정산 순회 중단용으로 **헤더 값을 예외/반환에 싣지 말고**, `client.last_quota_limit_header: Optional[str]` 속성 1개를 `_request` 성공/실패 경로에서 갱신(기존 동작 무변경, 속성 추가만). 이 속성은 B1 이 읽는다.

## 3. 모델·마이그레이션 (담당 A1)
`models.py` 끝에 클래스 6개 append, 마이그레이션 `migrations/versions/naversettle_00_channel_settlement.py`(revision `naversettle_00`, `down_revision='wizsend_00'`, 상수 리터럴 동결 — models import 금지, `downgrade()` 인덱스→테이블 역순). JSON 컬럼은 기존 `JSONColumn` 관례, Numeric은 `Numeric(16, 2)`. 모든 테이블 공통: `id Integer PK`, `channel String(20) NOT NULL server_default 'NAVER'`, `raw_snapshot JSONColumn NOT NULL`, `synced_at DateTime NOT NULL`, `sync_run_id Integer NULL`.

| 테이블/클래스 | 파티션 축 | 컬럼(네이버 필드 snake_case 그대로) | 인덱스 |
|---|---|---|---|
| `naver_settle_daily` / `NaverSettleDaily` | `settle_expect_date` | settle_basis_start_date Date, settle_basis_end_date Date, settle_expect_date Date NOT NULL, settle_complete_date Date, settle_amount, pay_settle_amount, commission_settle_amount, benefit_settle_amount, deduction_restore_settle_amount, pay_holdback_amount, minus_charge_amount, difference_settle_amount, return_care_settle_amount, normal_settle_amount, quick_settle_amount, preferential_commission_amount, settlement_limit_amount (전부 Numeric NULL), settle_method_type String(20), bank_type String(40), depositor_name String(100), account_no String(60), merchant_id String(40), merchant_name String(100) | `ix_nsd_channel_expect (channel, settle_expect_date)` |
| `naver_settle_case` / `NaverSettleCase` | `search_date` | search_date Date NOT NULL, period_type String(48) NOT NULL, settle_basis_date, settle_expect_date, settle_complete_date, pay_date (Date NULL), order_id String(40), product_order_id String(40), product_order_type String(40), settle_type String(40), product_id String(40), product_name String(300), purchaser_name String(100), pay_settle_amount, total_pay_commission_amount, free_installment_commission_amount, selling_interlock_commission_amount, benefit_settle_amount, settle_expect_amount (Numeric), merchant_id, merchant_name, contract_no String(60), foms_order_id Integer NULL(소프트 참조, FK 없음), link_id Integer NULL, match_status String(20) NOT NULL server_default 'NA' (MATCHED/UNMATCHED/NA) | `ix_nsc_channel_search (channel, search_date)`, `ix_nsc_product_order (product_order_id)`, `ix_nsc_unmatched (channel, search_date) WHERE match_status='UNMATCHED'`(postgresql_where; SQLite에선 일반 인덱스로 폴백 가능) |
| `naver_settle_commission` / `NaverSettleCommission` | `search_date` | search_date Date NOT NULL, period_type String(48) NOT NULL, order_no String(40), product_order_id String(40), product_order_type, product_id, product_name, merchant_id, merchant_name, purchaser_name, settle_type, settle_basis_date, settle_expect_date, settle_complete_date, tax_return_date (Date NULL), commission_basis_amount, commission_type String(40), pay_means_type String(40), commission_amount, maximum_selling_interlock_commission_amount | `ix_nscm_channel_search (channel, search_date)`, `ix_nscm_product_order (product_order_id)` |
| `naver_vat_daily` / `NaverVatDaily` | `settle_basis_date` | settle_basis_date Date NOT NULL, total_sales_amount, taxation_sales_amount, tax_exemption_sales_amount, credit_card_amount, cash_income_deduction_amount, cash_outgoing_evidence_amount, cash_exclusion_issuance_amount, other_amount (Numeric), merchant_id, merchant_name, is_final Boolean NOT NULL server_default false | `ix_nvd_channel_basis (channel, settle_basis_date)` |
| `naver_vat_case` / `NaverVatCase` | `settle_basis_date` | settle_basis_date Date NOT NULL, order_id String(40), product_order_id String(40), product_order_type, detail_type String(50), status String(40), product_name, 8개 금액 컬럼(vat_daily 와 동일 이름), merchant_id, merchant_name | `ix_nvc_channel_basis (channel, settle_basis_date)`, `ix_nvc_product_order (product_order_id)` |
| `naver_settle_sync_runs` / `NaverSettleSyncRun` | — | started_at DateTime NOT NULL, finished_at DateTime NULL, status String(20) NOT NULL (RUNNING/OK/FAILED/ABORTED_QUOTA), trigger String(20) NOT NULL (SCHEDULE/MANUAL/BACKFILL), actor_user_id Integer NULL, scope JSONColumn NOT NULL(요청 구간), stats JSONColumn NULL(엔드포인트별 호출수·행수·retro_changes 목록), error Text NULL, dry_run Boolean NOT NULL server_default false | `ix_nssr_started (started_at)` |
(공통 컬럼 `raw_snapshot`·`synced_at`·`sync_run_id` 는 runs 테이블엔 없음.)

검증: `alembic upgrade head` → `downgrade -1` → `upgrade head` 왕복(로컬 dev DB 또는 `tests/postgres` 레인 문서 참고), 단일 head 유지(`ScriptDirectory.get_heads()` 1개), `import app` OK, 기존 마이그레이션 계약 테스트(`tests/` 에서 `alembic`·`single_head`·`migration` grep) green.

## 4. 동기화 (담당 B1, A1·A2 완료 후) — `foms/services/integrations/naver_commerce/settle_sync.py`
- 워터마크: `SystemSetting` 키 `naver_settle_sync_state`(`watermark.py` 패턴 복제, 전용 함수 `read_settle_state(session)`/`write_settle_state(session, state)`). 값: `{"rev": int, "last_run_at", "last_ok_at", "coverage_from", "coverage_to", "rolling_days": 30, "future_days": 14, "vat_final_month": "YYYY-MM"|None, "last_error": str|None, "per_endpoint": {name: {"last_ok_date", "calls"}}}`. 성공 구간까지만 전진.
- 진입점: `run_settle_sync(session, client, *, today: date, trigger: str, actor_user_id=None, backfill_from: Optional[date]=None, dry_run=False, sleep=time.sleep) -> dict`(runs 행 생성·통계·상태 반환). 구간: 기본 `today-30 .. today+14`; `backfill_from` 지정 시 `backfill_from .. today+14` 를 **30일 창으로 쪼개 순차**(한 job 안에서). 호출 간격 `backfill.py` 의 `CALL_INTERVAL_SECONDS` 재사용(import).
- 적재 = **파티션 통째 교체**: `replace_partition(session, Model, channel, axis_column, axis_value, rows)` — 같은 트랜잭션에서 delete → insert. 교체 전 파티션 합계(`pay_settle_amount` 또는 `settle_amount` 합·행수)를 기록해 새 합계와 다르면 `stats.retro_changes.append({"table","date","old_total","new_total","old_count","new_count"})`.
- settle/daily: `get_settle_daily(from, to)` 페이지 순회 → `settle_expect_date` 별로 그룹 → 날짜마다 교체. case/commission: 날짜마다 `get_settle_cases(d)`/`get_settle_commission_details(d)` 페이지 순회 → `search_date=d` 파티션 교체. **확정 구간 제외**: `settle_expect_date + 30 < today` 인 날짜는 백필이 아닌 한 재조회하지 않는다.
- 매칭: `product_order_type == 'PROD_ORDER'` 행만 `ExternalOrderLink.external_id == product_order_id`(channel 일치)로 조회 → `foms_order_id=link.order_id`, `link_id`, `match_status='MATCHED'`(order_id 있음) / `'UNMATCHED'`(링크 없음 또는 order_id NULL). 그 외 유형은 `'NA'`. 배치 조회(`in_()`), N+1 금지.
- VAT: `today.day >= 10` 이고 `vat_final_month != 전월` 이면 전월 1일~말일 `get_vat_daily`/`get_vat_cases` 적재 후 `is_final=True`, `vat_final_month=전월`. 백필 시엔 `backfill_from` 의 달부터 전월까지 월 단위로.
- quota 중단: 호출 후 `client.last_quota_limit_header` 가 채워지면 run `ABORTED_QUOTA`, 워터마크 미전진, 즉시 반환.
- 실패: 예외는 잡아 runs 행 `FAILED` + `error` 기록 후 re-raise 하지 않고 반환 dict 에 `ok=False`. dry_run 은 호출만 하고 DB 쓰기 0(runs 행도 미생성, 반환 dict 에 통계).
- 큐/태스크/스크립트: `foms/services/jobs/queue.py` 에 `enqueue_naver_settle_sync(actor_user_id=None, *, backfill_from: Optional[str]=None, dry_run: bool=False) -> bool`(기존 `enqueue_naver_order_sync` 복제, 동기 폴백 금지, 중복 enqueue 방지 키 `naver_settle_sync`). `foms/services/jobs/tasks.py` 에 `run_naver_settle_sync_task(...)`. `scripts/maintenance/run_naver_settle_sync.py`(`run_naver_auto_dispatch.py` 복제: `--once|--loop --at 05:30 --window 10 --backfill-from YYYY-MM-DD --dry-run --json`). `start.sh` 에 `FOMS_NAVER_SETTLE_SYNC_ENABLED=1` 가드 블록(기존 블록 복제, 기본 꺼짐). `foms/services/feature_flags.py` 에 헬퍼(있는 컨벤션 그대로).
- 테스트 `tests/services/integrations/test_naver_settle_sync.py`: FakeClient(고정 JSON 픽스처, 문서 필드명 그대로)로 ①멱등 재적재(두 번 돌려도 행수 동일) ②소급 변경 감지(픽스처 금액 바꿔 재실행 → retro_changes 1건) ③PROD_ORDER 만 매칭·DELIVERY 는 NA ④부호 보존(음수 행 그대로) ⑤quota 헤더 중단 ⑥dry_run 무기록 ⑦VAT 익월 10일 규칙.

## 5. 조회 커널 + API (담당 B2, A1·A3 완료 후)
- `foms/services/settlement_channel.py`(services 루트 플랫): `build_channel_dashboard(session, *, channel: str, basis: str, date_from: date, date_to: date, granularity: str, ledger: str, page: int, per_page: int, filters: dict, today: date) -> dict`. `basis ∈ {expect, complete, basis, pay}`(기본 expect; daily 집계는 항상 `settle_expect_date` 축, 원장만 basis 적용). 전기 비교 = 같은 길이 직전 구간. 계좌번호 마스킹 `mask_account_no(s) -> '****1234'`(뒤 4자리). 라벨은 `settle_enums` 사용. 금액은 `Decimal` 합산 후 `int`/`float` 변환은 직렬화 직전 1회.
- 반환 `data` 스키마(키 정확 일치, 계약 테스트 대상):
  ```
  channel, basis, basis_label("정산 예정일 기준" 등), range{from,to}, granularity,
  sync{last_run_at,last_ok_at,status,coverage_from,coverage_to,rolling_days,final_before(=today-30),vat_available_to(전월 말일),rev,stale(bool: last_ok_at 가 36시간 이전),never(bool)},
  kpi{settled_amount, expected_amount, expected_account_amount, expected_charge_amount, commission_total, commission_rate(=commission_total/pay_settle_total, None if 0), holdback_amount(=pay_holdback+settlement_limit), match_rate(None if 0 PROD_ORDER), unmatched_count, case_count, prev{같은 키}},
  daily[{date, normal, quick, deduction_restore, commission, benefit, holdback, minus_charge, pay_settle, settle_amount, completed(bool=settle_complete_date 존재)}],
  daily_prev[같은 구조],
  waterfall[{key,label,amount}] 순서: pay_settle(+), commission(-), benefit(+), deduction_restore(+), holdback(-), minus_charge(-), settle_amount(=),
  deposit_channels[{method,method_label,bank_type,bank_label,depositor_name,account_no_masked,amount,count}],
  reconcile{daily_total, case_total, diff},
  commission{by_type[{type,label,amount,share}], total, max_interlock{amount,cap}},
  vat{available_to, rows[{date,total_sales,taxation_sales,tax_exemption_sales,credit_card,cash_income_deduction,cash_outgoing_evidence,cash_exclusion_issuance,other}], total{같은 8키}, final(bool)},
  exceptions[{kind(UNMATCHED|UNLINKED|HOLDBACK|LIMIT|NEGATIVE|RETRO|COUNT_MISMATCH), label, date, amount, age_days, ref{...}, action_url}],  (v1.2: UNMATCHED=링크 있음·주문 없음(워크벤치 대기), UNLINKED=링크 없음(수집 전 주문); 최상위 `holdback` 블록·kpi `unmatched_pending_count`/`unmatched_unlinked_count` 추가 — 정본은 원장 Phase F)
  ledger{kind(case|commission|vat_case), groups[{date,count,amount}], rows[...원본 필드 snake_case + label 필드 + match_status + foms_order_id + raw], pagination{page,per_page,total,pages}}
  ```
- API `foms/api/cs/settlement_channel.py`: `settlement_channel_api_bp`, `url_prefix='/api/settlement/channel'`. `GET ''` (params `channel=NAVER`, `basis`, `from`, `to`(YYYY-MM-DD, 기본 오늘-30~오늘+14, 최대 폭 400일 → 400), `granularity=day|week|month`, `ledger=case|commission|vat_case`, `page`, `per_page(≤200)`, `type`(settle_type/product_order_type 필터), `q`(주문번호/상품주문번호 부분일치)). 권한: `can_view_channel_settlement` 실패 → 403 JSON `{'success':False,'error':'권한이 없습니다.'}`(기존 `foms/api/cs/settlement.py` 문구 관례 확인 후 동일하게). `POST '/sync'` (json `{backfill_from?: 'YYYY-MM-DD'}`) → `enqueue_naver_settle_sync(actor_user_id=user.id, backfill_from=...)` → `{'success':True,'data':{'queued':bool}}`; policy `SETTLEMENT_CHANNEL_SYNC`; **manifest 2종 등재**(`docs/harness/foms_order_mutation_policy_manifest.json`, `docs/harness/foms_write_guard_manifest.json` — 형식은 기존 naver 항목 복제) + 감사 `log_access(..., user.id, action="NAVER_SETTLE_SYNC_REQUEST", ...)` + 감사 라벨 등재(`audit_message_display` grep). 등록: `foms/api/cs/__init__.py` + `foms/platform/blueprints.py`(기존 `settlement_api_bp` 옆).
- 테스트 `tests/domains/test_settlement_channel_api.py`: 권한 매트릭스(ADMIN 200 / STAFF+ACCOUNTING 200 / MANAGER 403 / STAFF+CS 403 / VIEWER 403 / 미인증 401 또는 로그인 리다이렉트 — 기존 API 테스트 관례 따름), 응답 스키마 키 정확 일치, 400(기간 폭·enum), 마스킹, 부호 보존(음수 픽스처 합계), CHARGE_AMT 분리, VAT `available_to`.

## 6. 템플릿·탭 등록·기존 계약 갱신 (담당 A3)
- `templates/cs/partials/settlement_dashboard_body.html` 4 hunk(append 위치): ① 분석 탭 버튼 뒤 `{% if can_view_channel_settlement %}<button type="button" class="s-tab" role="tab" id="foms-settle-tab-channel" data-settlement-tab="channel" aria-controls="foms-settle-pane-channel" aria-selected="false" tabindex="-1"><span class="s-tab-name">네이버 정산</span><span class="s-tab-hint">정산 예정일 기준</span></button>{% endif %}` ② 분석 pane 뒤 `{% if can_view_channel_settlement %}<div class="s-pane" role="tabpanel" id="foms-settle-pane-channel" data-settlement-pane="channel" aria-labelledby="foms-settle-tab-channel" tabindex="0" hidden>{% include 'cs/partials/settlement_channel_body.html' %}</div>{% endif %}` ③ 기존 `<link>` 2줄 뒤 `settlement-channel.css?v=20260902c`(같은 if) ④ 기존 `<script defer>` 2줄 뒤 `channel.js?v=20260902c`(같은 if). 기존 4핀 무수정.
- 신규 `templates/cs/partials/settlement_channel_body.html`: 루트 `<section class="s-ch" id="foms-settle-channel-root" data-settlement-ch-root data-settlement-ch-api="/api/settlement/channel" data-settlement-ch-sync-api="/api/settlement/channel/sync" data-settlement-ch-channel="NAVER">`. 서버 렌더 앵커(전부 빈 컨테이너 + 상태 노드): `#foms-settle-ch-sync`(S0, 버튼 `data-settlement-ch-sync-btn`), `#foms-settle-ch-bar`(기간·기준일 셀렉트 `data-settlement-ch-basis`, `data-settlement-ch-from`, `data-settlement-ch-to`, `data-settlement-ch-granularity`), `#foms-settle-ch-kpi`, `#foms-settle-ch-daily`, `#foms-settle-ch-waterfall`, `#foms-settle-ch-deposit`, `#foms-settle-ch-reconcile`, `#foms-settle-ch-ledger-switch`(버튼 4개 `data-settlement-ch-ledger="case|commission|vat|exceptions"`), `#foms-settle-ch-ledger`. 상태 노드 `[data-settlement-ch-loading]`, `[data-settlement-ch-error]`, `[data-settlement-ch-empty]` (모두 `hidden`). 상시 라벨 텍스트 "정산 예정일 기준 · 매출 인식(완료일)과 다릅니다" 포함. `.alert` 계열 상시 안내엔 `data-foms-no-autodismiss`.
- `tests/domains/test_settlement_dashboard_render.py` 갱신: `_TABS` 에 `("channel", "foms-settle-tab-channel", "foms-settle-pane-channel", "네이버 정산")` 추가; 3→4 카운트·함수명 갱신; **기본 로그인(ADMIN)은 4탭**, `STAFF+CS` 로그인 시 3탭(채널 탭 없음) 케이스 추가; `_MOCKUP_LEFTOVERS` 의 "예정" 렌더 스캔은 채널 pane(`id="foms-settle-pane-channel"` 블록)을 제외한 HTML 에 적용(소스 스캔 `_TEMPLATE_SOURCES` 는 기존 파일만이라 무변경). 그 외 기존 assertion 은 손대지 않는다.
- 신규 `tests/domains/test_settlement_channel_render.py`(`test_settlement_operations_render.py` 복제 패턴): 자산 실재·`?v=20260902c` 핀(저장소 전역 값 1종)·defer·외부 CDN 0·인라인 style 0·상태노드 `data-settlement-ch-*` 소유·앵커 id 전량·"정산 예정일 기준" 라벨 존재·수식어 없는 `>정산<` 라벨 0·STAFF+CS 렌더에 채널 마크업 0·ADMIN·STAFF+ACCOUNTING 렌더에 존재.
- `static/css/settlement/settlement-channel.css` / `static/js/settlement/channel.js` 는 A4 소유. A3 는 **파일이 없을 때만** 최소 자리(주석 1줄)를 만든다.

## 7. 프론트 (담당 A4) — `static/js/settlement/channel.js` + `static/css/settlement/settlement-channel.css`
- `operations.js` 구조 복제: IIFE, `ROOT_SELECTOR='[data-settlement-ch-root]'`, 싱글톤 `window.__FOMS_SETTLEMENT_CHANNEL_BOUND`, `watchTabActivation`(MutationObserver 로 `data-settlement-active-tab="channel"` 관찰) 첫 활성화 때 로드, fragment 재삽입 대응(위임·싱글톤). 차트는 `dashboard.js` 의 인라인 SVG 함수를 **복제**(전역 의존 금지, 파일 간 import 없음): columnChart(스택 확장: normal/quick/deduction_restore 3계열 + 전기 비교선), sparkSvg, barList/share bar, meter, 신규 waterfall(부동 막대, 단일 축). 숫자 포맷 `₩`+천단위, 축약은 표시 단계만. 음수는 `-` 그대로 + `.s-ch-neg` 클래스.
- 렌더 블록: S0 동기화 헤더(never/stale 문구 구분, [지금 동기화] → POST sync, 결과 토스트, `rev` 폴링 10초×6회 후 재조회), S-bar(basis/from/to/granularity 변경 → 재조회, 기본 오늘-30~오늘+14), S1 KPI 6타일(전기 대비 %·스파크), S2 일별 스택 컬럼, S3 워터폴, S4 입금 채널 카드(CHARGE_AMT 는 "통장 미기록" 배지), S9 대사 배너, 원장 스위처(case/commission/vat/exceptions) — case: 날짜 그룹 `<details>` + 행 표 + 페이저 + 유형 필터·검색; commission: by_type share bar + 랭킹 + 상한 미터; vat: 기간표 + 합계 sticky + "전월 말일까지 제공" 배너; exceptions: 표(0건 vs 미동기화 문구 구분). 행 펼치기 `<details>` 에 `raw` 전 필드 key/value 표.
- CSS: `.foms-settle` 스코프 안 `.s-ch-*` 만, `--s-*` 토큰 재사용, 인라인 style 0, container query(720px 미만 KPI 2열·표→카드), `.foms-settle[data-settlement-active-tab="channel"] .s-filterbar{display:none}`(기존 필터바 숨김 규칙의 채널 판, 새 파일에서), 다크 모드 토큰 상속.
- 검증: `node --check static/js/settlement/channel.js`, 기존 lint 관례(`tests/` 의 JS 정적 검사 grep), 브라우저 QA 는 총괄이 gstack 으로 수행.

## 8. 통합·검증 (총괄)
정산 5스위트 + 신규 3파일 + `tests/contracts` 네임스페이스·인벤토리·auth enforcement + `pre_push_smoke` + ci.yml docs-facing 등재(신규 렌더 테스트) + `import app` + T0 재프로브 → 커밋(task 단위) → deploy push → CI 전 워크플로 → 스테이징 백필 90일(야간) → 화면 QA.
