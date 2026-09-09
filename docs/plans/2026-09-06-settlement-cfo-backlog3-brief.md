# 정산탭 CFO 감사 후속 — 백로그 3차(승인분 4건) 멀티 에이전트 브리프 (2026-09-06)

> 워크플로 에이전트(CEO·워커 3·통합 검증자·리뷰어 2·수정자)에게 건네는 **유일한 컨텍스트 원본**이다.
> 스펙 원문은 감사 보고서 `docs/plans/2026-09-05-settlement-cfo-review-report.md` §3(F-02·H-01·D-03·B-01)·§6(결정 재고 5번 = D-03 근거). 1차 5건은 운영(PR #298), 2차 10건은 `2026-09-06-settlement-cfo-backlog2-brief.md` 로 먼저 반영된다 — **2차가 만든 키·kind(SYNC_FAILED 8키·holdback.window/balance·범례 등)를 전제로 한다.**
> **사용자 승인(2026-09-06)**: F-02 동기화 버튼 정직화(API 503 계약 변경) · H-01 인덱스 마이그레이션 · D-03 정산금≠출고가 경고(기존 "금액은 그리지 않는다" 설계 뒤집기) · B-01 월초 자동 백필 옵션. 넷 다 승인됐으므로 설계 단계에서 다시 묻지 않는다.

## 0. 환경 (절대 규칙) — 1·2차 브리프와 동일

- 워크트리 `C:/tmp/foms-s-settle-cfo` · 브랜치 `session/settle-cfo`. **모든 명령을 이 디렉토리에서**(`cd C:/tmp/foms-s-settle-cfo && pwd && ...`). `C:/DEV/FOMS` 금지.
- bash · `PYTHONIOENCODING=utf-8` · CRLF 유지 · **git 금지** · 근본 원인만 · 함수 50줄(실행 줄)·docstring·타입 힌트 · 인라인 style·jQuery 금지 · **재계산 금지(D-4)** — D-03 의 "차이" 는 두 원값을 **나란히** 두고 같지 않음만 판정한다(차액을 새 저장값으로 만들지 않는다).
- 산출 폴더 `OUT4 = C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo_fix3`.
- 라인 번호는 2차 반영 전 기준 — **CEO 가 현재 소스로 재확정**한다.

## 1. 수정 4건 (완료 기준 포함)

| # | 항목 | 요지 | 완료 기준 |
|---|---|---|---|
| F-02 | 동기화 버튼 정직화 | `foms/services/jobs/queue.py::enqueue_naver_settle_sync` 가 큐 부재·enqueue 실패·중복을 같은 `False` 로 접는다. **이 함수만** 3상태로: 반환 `"queued" \| "duplicate" \| "unavailable"`(다른 `enqueue_*` 는 그대로). API `POST /api/settlement/channel/sync`: unavailable → **503** `{'success': False, 'error': '지금은 동기화할 수 없습니다. 잠시 뒤 다시 시도하세요.'}`, duplicate → 200 `queued=False`(기존), queued → 200 `queued=True` + `job_id`. 감사 detail 에 `reason`(queued/duplicate/unavailable). JS: 503 이면 헤더 상태줄에 "지금은 동기화할 수 없습니다(큐 연결 불가)" — "이미 대기 중" 문구는 duplicate 에만. `queue.py` docstring·API docstring·JS 문구 셋을 같은 뜻으로. | queue 테스트 3상태(Redis 없음 → unavailable, 같은 job 있음 → duplicate, 정상 → queued) · API 테스트 503/200/200 + 감사 detail reason · 렌더 문구 계약 2개 |
| H-01 | COALESCE 창 술어 인덱스 | `naver_settle_case`·`naver_settle_commission` 에 식 인덱스 `(channel, COALESCE(settle_expect_date, search_date))` — 이름 `ix_nsc_channel_expect_axis`·`ix_nscm_channel_expect_axis`. **models.py `__table_args__`** 에 `Index(..., 'channel', func.coalesce(...))` 로 선언(create_all 베이스라인이 models 라 모델에도 있어야 PG 레인 왕복이 산다) **+ alembic 리비전 `naversettle_02`**(`down_revision='naversettle_01'`, `upgrade` 는 `op.create_index(..., [sa.text('channel'), sa.text('COALESCE(settle_expect_date, search_date)')])` 류, `downgrade` 는 drop 2개). 마이그레이션 안에서 models 를 import 하지 않는다(상수 동결 원칙). 커널의 `_case_scope`·commission scope 술어는 그대로(식이 인덱스 식과 **문자 그대로 일치**해야 플래너가 탄다 — `func.coalesce(NaverSettleCase.settle_expect_date, NaverSettleCase.search_date)` 순서 유지). | `alembic heads` 단일(`naversettle_02`) · 마이그레이션 왕복 테스트(있는 체인 테스트에 편입) · 로컬 PG 가 있으면 `tests/postgres` 전수, 없으면 CI PG Lane 을 관문으로 명시 · 스테이징 반영 뒤 `EXPLAIN` 으로 Index Scan 채택 확인은 **총괄** 몫 |
| D-03 | 정산금≠출고가 경고 | ① 커널: 예외 kind **`AMOUNT_DIFF`**(→ `_EXCEPTION_KINDS` 9키, `exception_totals` 9키+total). 조회 창 안 `match_status='MATCHED'`(foms_order_id NOT NULL) 건별 행을 FOMS 주문별로 묶어 Σ`pay_settle_amount`(원값 합) 와 주문 출고가(`erp_shipping_price_from_structured(sd)`, `foms/services/settlement_rows.py:43` 와 같은 함수)를 나란히 두고, 둘이 다르면 예외 1행(text "정산액≠출고가", ref 에 `order_id`·`pay_settle_total`·`shipping_price`·`case_count`·취소 행 포함 여부). 출고가 None(품목 미입력)도 예외(ref `shipping_price: null`). 질의: 매칭 건별 1 + 주문 1(`in_(ids)` 배치, N+1 금지), **대시보드만**(스트립 질의 예산 불변 — 스트립 totals 의 AMOUNT_DIFF 는 0 으로 두고 키만 유지, 또는 스트립에선 계산 안 함을 계약에 명시). 상한 `_EXCEPTION_CAP`. ② 실무 탭 행 API `foms/services/settlement_rows.py::_naver_settlement_cell`: `amount`(Σpay_settle_amount 원값) 추가, `operations.js:466~467` 의 "금액은 그리지 않는다" 를 **사용자 결정으로 뒤집어** 셀에 "정산 ₩X · 출고가 ₩Y" 두 원값 병기 + 다르면 `.s-ops-naver--diff` 강조. 주석의 이유를 "회계 대사 요구(2026-09-06 사용자 결정, 감사 D-03)" 로 바꾼다. | API 테스트: 매칭 2주문 픽스처(일치 1·불일치 1·출고가 None 1) → AMOUNT_DIFF 2행·totals 2, 음성(전부 일치 → 0) · rows API 테스트 `amount` 키 · 렌더 계약(operations.js 문구·클래스, channel.js `excKindClass` AMOUNT_DIFF) |
| B-01 | 확정 구간 밖 정정 | ① `docs/plans/2026-09-02-naver-settlement-contracts.md` 에 "확정 구간(예정일+30일)은 FOMS 가정, 네이버 정정은 백필 없이는 반영 안 됨 + 월 마감 전 전월 1일부터 [받아오기]" 절 추가. ② `channel.js` 헤더 "확정 구간 ~YYYY-MM-DD" 줄에 부제 "(이 날짜 이전 정정은 [이 구간 받아오기]로만 반영 · 매월 1일 자동 백필)". ③ 워커 `run_naver_settle_sync.py`: KST **매월 1일** 첫 실행은 `backfill_from = 전월 1일` 로 돈다(순수 함수 `monthly_backfill_from(today) -> Optional[date]`, 1일이 아니면 None). 스위치 `FOMS_NAVER_SETTLE_MONTHLY_BACKFILL`(기본 `1`, `0` 이면 끔). trigger 는 `BACKFILL`(기존 값 재사용, scope.backfill_from 으로 구분). coverage 합집합 규칙은 이미 있다. | 순수 함수 테스트(1일 → 전월 1일·1월 1일 → 전년 12월 1일·2일 → None·스위치 0 → None) · `_run_loop` 소스 계약(monthly 판정이 `_sync_once` 호출 앞) · 렌더 문구 계약 · 문서 절 존재(문서 읽는 테스트는 만들지 않는다 — ci.yml 등재 의무) |

핀: 채널 CSS/JS 2줄 `20260906a → 20260906b`, `_CHANNEL_PIN = "20260906b"`. **operations.js 를 고치므로 셸 4줄도 함께** `20260903d → 20260906b`(요약 css·실무 css·dashboard.js·operations.js 4줄 **같은 값** 계약 — `test_settlement_operations_render.py`·`test_settlement_dashboard_render.py` 둘 다 green 이어야 한다). 요약/실무 자산에 "예정" 리터럴 금지("정산 예정일"만 예외).

## 2. 파일 소유권 (겹치면 결과 폐기)

| 워커 | 편집 허용 파일 |
|---|---|
| **BE-A**(커널·API·큐·행 API) | `foms/services/settlement_channel.py` · `foms/api/cs/settlement_channel.py` · `foms/services/jobs/queue.py`(`enqueue_naver_settle_sync` 만) · `foms/services/settlement_rows.py` · `tests/domains/test_settlement_channel_api.py` · `tests/domains/test_settlement_channel_strip.py` · `tests/domains/test_settlement_rows_api.py` · 큐 테스트 파일(CEO 가 지정) |
| **BE-B**(워커·마이그레이션·모델·문서) | `scripts/maintenance/run_naver_settle_sync.py` · `alembic/versions/naversettle_02_*.py`(신규) · `models.py`(두 `__table_args__` 만) · `tests/services/integrations/test_naver_settle_sync_loop.py` · 마이그레이션 체인 테스트(CEO 가 지정) · `docs/plans/2026-09-02-naver-settlement-contracts.md`(B-01 ①) |
| **FE** | `static/js/settlement/channel.js` · `static/js/settlement/operations.js` · `static/css/settlement/settlement-channel.css` · `static/css/settlement/settlement-operations.css` · `templates/cs/partials/settlement_dashboard_body.html`(핀 6줄만) · `tests/domains/test_settlement_channel_render.py` · `tests/domains/test_settlement_operations_render.py` · `tests/domains/test_settlement_dashboard_render.py`(핀 계약이 필요할 때만) |
| CEO | `OUT4/fix3_design.md` 만 · 통합 검증자: 위 전부(통합 결함 수리만) · 리뷰어 2: 편집 금지 · 총괄: 원장·AI_STATUS·커밋·push·QA·EXPLAIN |

## 3. 게이트 (통합 검증자 전량 실행, `OUT4/gates_N.md`)

```
cd C:/tmp/foms-s-settle-cfo && pwd
python -c "import app; print('APP_OK')"
python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"   # ['naversettle_02'] 하나
PYTHONIOENCODING=utf-8 python -m pytest tests/domains -k settlement -q -p no:cacheprovider     # 기준선 = 2차 반영 후 수(gates_2.md 의 값)보다 줄면 red
PYTHONIOENCODING=utf-8 python -m pytest tests/services/integrations/test_naver_settle_sync.py tests/services/integrations/test_naver_settle_sync_loop.py -q -p no:cacheprovider
PYTHONIOENCODING=utf-8 python -m pytest tests/contracts tests/domains/test_foms_namespace_imports.py tests/performance/test_perf_regression_guard.py tests/harness/test_hook_log_hygiene.py -q -p no:cacheprovider
PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_settlement_rows_api.py tests/domains/test_settlement_operations_render.py tests/domains/test_settlement_dashboard_render.py -q -p no:cacheprovider
node --check static/js/settlement/channel.js && node --check static/js/settlement/operations.js
git diff --name-only | xargs -I{} sh -c 'file "{}" | grep -q CRLF || echo "LF-ONLY {}"'
grep -n "예정" templates/cs/partials/settlement_dashboard_body.html templates/cs/partials/settlement_operations_body.html static/js/settlement/dashboard.js static/js/settlement/operations.js | grep -v "정산 예정일" | grep -v "{#"
```
로컬 PG 레인이 있으면 `tests/postgres` 도(없으면 gates 에 "CI PG Lane 관문" 으로 명시). pre_push_smoke·push·EXPLAIN 은 총괄.

## 4. 함정

- `enqueue_*` 함수들이 같은 `(conn None → False)` 패턴을 공유한다 — settle 함수 하나만 바꾸고 나머지는 건드리지 않는다(다른 호출자 계약).
- `_SETTLE_SYNC_JOB_ID` 고정 job id 로 중복을 막는다(API `_enqueue` 참조) — duplicate 판정은 큐에 그 id 가 살아 있을 때.
- 마이그레이션 상수 동결: 리비전 파일에서 models import 금지. `down_revision` 은 `naversettle_01`. 이중 head 가 되면 운영 부팅이 죽는다(승격 직전 총괄이 `alembic heads` 재확인).
- SQLite(단위 테스트)도 식 인덱스를 지원하지만 `COALESCE` 대소문자·인자 순서가 PG 와 같아야 한다. 인덱스 이름 63자 이하.
- `erp_shipping_price_from_structured` 는 sd(JSONB dict)를 받는다 — 주문 조회는 `Order.id.in_(ids)` 배치 1회.
- 실무 탭 행 API 는 `include_naver_settlement=True` 일 때만 `naver_settlement` 키가 생긴다 — 새 `amount` 도 그 안에.
- `.alert` 5초 자동 닫힘 — 503 문구는 헤더 상태줄(`data-settlement-ch-sync-state`)에.
- 렌더 계약: document 리스너 3개 고정 · 인라인 style 0 · 핀 사슬 3개(셸 4줄 동일값 / 채널 2줄 / `_CHANNEL_PIN`).
- 워크트리 cwd 는 턴 경계에서 리셋 — 매 명령 `cd && pwd`.

## 5. 반환 계약

전부 StructuredOutput(스크립트 스키마). 리뷰어 스펙(A)/품질(B) 분리, user_visible MINOR 는 승격 전 고침. CEO 는 ship / fix(1회) / block.
