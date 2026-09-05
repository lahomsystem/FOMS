# 정산탭 CFO 감사 후속 — 백로그 2차(10건) 멀티 에이전트 브리프 (2026-09-06)

> 워크플로 에이전트(CEO·BE 워커·FE 워커·통합 검증자·리뷰어 2·수정자)에게 건네는 **유일한 컨텍스트 원본**이다.
> 스펙 원문은 감사 보고서 `docs/plans/2026-09-05-settlement-cfo-review-report.md` §3(결함)·§4(백로그)·§8(라벨 해석표). 1차 5건은 운영 반영됐다(PR #298 · production `b51acf6d0`). **먼저 §3 의 해당 항목을 읽는다.**
> 사용자 결정(2026-09-05): "보류 누적 잔액 등 다음 백로그 계속". 총괄이 승인 없이 할 수 있는 범위로 잘랐다 — **범위 밖**: F-02(API 상태코드 200→503 변경 = 계약 변경, 사용자 승인 필요) · H-01(마이그레이션) · D-03(결정 재고 §6-5 대기) · B-01 ③ 자동 백필 옵션(워커 동작 변경) · C-03 새 타일 · H-03/H-04.

## 0. 환경 (절대 규칙) — 1차 브리프와 동일

- 워크트리 `C:/tmp/foms-s-settle-cfo` · 브랜치 `session/settle-cfo`(origin/deploy `969419133` 위). **모든 명령을 이 디렉토리에서**(`cd C:/tmp/foms-s-settle-cfo && pwd && ...`). `C:/DEV/FOMS` 금지.
- bash · `PYTHONIOENCODING=utf-8` · 저장소 파일 **CRLF**(Edit 그대로, 파이썬 통째 쓰기는 `newline=''`+`\r\n`). `.ps1` 은 **UTF-8 BOM 유지**(BOM 없으면 PowerShell 파싱 에러).
- **git 금지**. 근본 원인만. 함수 50줄(실행 줄 기준)·docstring·타입 힌트. 인라인 style·jQuery 금지. **재계산 금지(D-4)** — 새 값은 저장값 SUM/COUNT/부호별 합, 파생은 비율만.
- 산출 폴더 `OUT3 = C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo_fix2`(이미 존재).
- 응답 한글. 주석은 **왜(why)** 를 한글로. 라인 번호는 감사 시점 기준이라 1차 수정 뒤 밀렸다 — **CEO 가 현재 소스로 재확정**한다.

## 1. 수정 10건 (완료 기준 포함)

| # | 항목(보고서) | 요지 | 완료 기준 |
|---|---|---|---|
| B-02 | 지급 보류 KPI 발생·해제 분리 + 누적 잔액 | `_build_holdback`/`_holdback_of`: 창 안 **보류(음수) 합·해제(양수) 합·순증감**을 따로 내고(`holdback.window = {held, released, net}`), **적재 구간 전체 누적 잔액** `holdback.balance = {held, released, net, since, until}`(조회 창 무관, `naver_settle_daily` 전 기간 부호별 SUM — 질의 1개 추가 허용) 을 낸다. 보류 상세 표에 같은 금액(분할 합 포함) 짝 표시는 **하지 않는다**(짝 판정은 추론이라 D-4 경계) — 대신 부호별 합계 줄만. 화면: "보류·한도" 타일 부제 "창 안 보류 −X · 해제 +Y", 상세 패널 머리에 "적재 구간 전체 누적 잔액 −Z(보류 −A · 해제 +B, YYYY-MM-DD~)". | API 테스트: 보류 2행·해제 1행 픽스처에서 window/balance 값, 창 밖 해제가 balance 에만 반영(음성: 창 안 합엔 없음). 렌더 계약 문구 2개. 스트립 질의 예산 불변(스트립은 holdback 안 씀) |
| CRIT-A-01 | RETRO·COUNT_MISMATCH 검출기 테스트 | `tests/domains/test_settlement_channel_api.py` 에 2건: 일별≠건별 픽스처 → 예외 COUNT_MISMATCH 1행·diff 부호·`exception_totals.COUNT_MISMATCH == 1`; run.stats.retro_changes 1건 → RETRO 1행(+51건이면 상한 50 잘림·totals 51). | 테스트 2건 green, 음성 대조군(일치·retro 0 → 0행) |
| F-04 | FAILED 실행 부분 커밋 + SYNC_FAILED | `settle_sync.py::_finish`: FAILED/ABORTED_QUOTA 분기에서 `session.rollback()` 뒤 run 행만 닫는다(창 단위 원자성 — 실패 창의 반쯤 교체된 파티션이 남지 않게). 예외 큐에 kind `SYNC_FAILED`(최신 run 이 FAILED 면 1행, text=오류 요약) 추가 → `_EXCEPTION_KINDS` 8키, `exception_totals` 8키+total, JS `excKindClass` 에 `SYNC_FAILED → 'danger'`. | `tests/services/integrations/test_naver_settle_sync.py` 신규 1건(2일째 예외 → 1일째 파티션도 옛 run 그대로), API 테스트 SYNC_FAILED 1행·음성(OK run → 0), strip 계약 8키 |
| F-01 | stale 임계값 | `STALE_AFTER_HOURS` 36 → **28**(일 1회 05:30 스케줄 + 여유 4h, 재배포·지연 흡수). 문구에 "예정 실행(매일 05:30)을 넘겼습니다" 를 넣어 30시간이 왜 비정상인지 화면이 말한다. | 재현 테스트(27.9h False·28.1h True), 렌더 문구 계약 |
| F-08 | OK 없이 FAILED 만 | `_build_sync`: `last_ok_at` 없고 최신 run FAILED 면 `status="FAILED"`·`stale=False`(stale 문구가 실패를 덮지 않게), JS 헤더 "동기화 실패 — N시간 전 · 오류: …". | API 테스트(OK 0·FAILED 1 픽스처), 렌더 문구 |
| G-06 | CSV 파일명·type 검증 | `export_filename(kind, from, to, basis=, type=, q=)`: type 있으면 `_type-<코드소문자>`, q 있으면 `_q` 슬러그. `_filter_clauses` 가 type 을 `_ENUM_MAPS`(또는 해당 kind 의 허용 집합)와 대조해 밖이면 `ValueError` → API 400 JSON. | export 테스트: 파일명 3케이스, 오타 type 400(음성: 허용 type 200), 감사 detail 파일명 일치 |
| E-06 | export 감사 detail | `_log_export(... filters)` → detail 에 `type`·`q`(빈 값은 키 생략 말고 null). | API 테스트 1건(감사 행 detail 키) |
| E-02 | sync 감사 detail | `POST /sync` 감사 detail 에 큐 job id(`enqueue` 반환값)와 요청 시 계산된 기본 창(`from`·`to`) 추가. | API 테스트 1건 |
| G-08a·G-07 | 150% 가로 스크롤 + 워터폴 라벨 절단 | CSS `.foms-settle .s-ch-group { min-width: 0; }`(grid 아이템 min-content 부풀림 차단). 워터폴 X축 라벨은 6자 절단 대신 **2줄**(`<tspan>` 2개, 공백/`·` 기준 분리) — `shortStepLabel` 제거 또는 약어 표를 `_WATERFALL_STEPS` 데이터로. | 렌더 계약(min-width 규칙 존재·`slice(0, 6)` 부재), font_scale 계약 green |
| H-02 | smoke 서브셋에 정산 핀 테스트 | `scripts/ops/pre_push_smoke.ps1` 서브셋 목록에 `tests/domains/test_settlement_channel_render.py`·`tests/domains/test_settlement_operations_render.py` 추가(BOM·CRLF 유지). | smoke 실행 결과에 두 파일 포함, exit 0 |
| N-02 | 월/주 버킷 부분 완료 | `_daily_bucket`: `completed`(all) 유지 + `settled_amount`·`expected_amount` 합 추가. JS 월/주 라벨 "정산 예정" → 완료·예정이 섞이면 "일부 완료(완료 X · 미입금 Y)". 일 단위 불변. | API 테스트(섞인 버킷 픽스처), 렌더 문구 |
| F-06 | JSON API `Cache-Control: no-store` | `/api/settlement/channel`(full·strip) 응답 헤더. SW PII 게이트가 이 헤더에 의존. | API 테스트 헤더 단정 |

핀: 채널 CSS/JS 2줄 `20260905a → 20260906a`, `_CHANNEL_PIN = "20260906a"`. 셸 4줄(`20260903d`) 불변. 요약/실무 자산에 "예정" 리터럴 금지.

## 2. 파일 소유권 (겹치면 결과 폐기)

| 워커 | 편집 허용 파일 |
|---|---|
| **BE** | `foms/services/settlement_channel.py` · `foms/services/settlement_channel_export.py` · `foms/services/integrations/naver_commerce/settle_sync.py` · `foms/api/cs/settlement_channel.py` · `tests/domains/test_settlement_channel_api.py` · `tests/domains/test_settlement_channel_strip.py` · `tests/domains/test_settlement_channel_export.py` · `tests/domains/test_settlement_channel_export_api.py` · `tests/services/integrations/test_naver_settle_sync.py` |
| **FE** | `static/js/settlement/channel.js` · `static/css/settlement/settlement-channel.css` · `templates/cs/partials/settlement_dashboard_body.html`(채널 핀 2줄만) · `tests/domains/test_settlement_channel_render.py` · `scripts/ops/pre_push_smoke.ps1`(H-02, BOM 유지) |
| CEO | `OUT3/fix2_design.md` 만 |
| 통합 검증자 | 위 전부(통합 결함 수리만) · 리뷰어 2 편집 금지 · 총괄: 원장·AI_STATUS·커밋·push·QA |

## 3. 게이트 (통합 검증자 전량 실행, `OUT3/gates_N.md`)

```
cd C:/tmp/foms-s-settle-cfo && pwd
python -c "import app; print('APP_OK')"
PYTHONIOENCODING=utf-8 python -m pytest tests/domains -k settlement -q -p no:cacheprovider     # 기준선 948 passed
PYTHONIOENCODING=utf-8 python -m pytest tests/services/integrations/test_naver_settle_sync.py tests/services/integrations/test_naver_settle_sync_loop.py -q -p no:cacheprovider   # 기준선 43
PYTHONIOENCODING=utf-8 python -m pytest tests/contracts tests/domains/test_foms_namespace_imports.py tests/performance/test_perf_regression_guard.py tests/harness/test_hook_log_hygiene.py -q -p no:cacheprovider
node --check static/js/settlement/channel.js
git diff --name-only | xargs -I{} sh -c 'file "{}" | grep -q CRLF || echo "LF-ONLY {}"'
head -c 3 scripts/ops/pre_push_smoke.ps1 | xxd | head -1     # ef bb bf 여야 한다(BOM)
grep -n "예정" templates/cs/partials/settlement_dashboard_body.html templates/cs/partials/settlement_operations_body.html static/js/settlement/dashboard.js static/js/settlement/operations.js | grep -v "정산 예정일" | grep -v "{#"
```
pre_push_smoke·push 는 총괄.

## 4. 함정

- 1차에서 `_EXCEPTION_KINDS` 7키를 strip/API 테스트가 고정했다 — F-04 로 8키가 되면 그 계약부터 바꾼다.
- `_build_holdback` 은 현재 조회 창 `rows` 만 받는다. 누적 잔액은 전 기간 SUM 질의 1개(대시보드 전용, 스트립 X). `get_today_kst()` 는 date.
- `settle_sync.py::_drive` 는 `SettleSyncQuotaAborted` 외 모든 예외를 삼켜 FAILED 를 **반환**한다 — rollback 은 `_finish` 안에서 run 행을 닫기 **전에** 한다(run 행 자체는 커밋해야 화면이 실패를 본다 → run 행 갱신은 rollback 뒤 별도 커밋).
- CSV 5종 소진 계약(`test_every_model_column_is_exported`) 과 xlsx 금지 5종은 건드리지 않는다. `export_filename` 시그니처 변경 시 호출자 전부(API·감사 detail) 함께.
- `.alert` 5초 자동 닫힘 — 상시 문구는 카드 안에.
- 렌더 계약은 `document.addEventListener` 3개 고정, 새 전역 리스너 금지.
- 워크트리 cwd 는 턴 경계에서 리셋 — 매 명령 `cd && pwd`.

## 5. 반환 계약

전부 StructuredOutput(스크립트 스키마). 리뷰어는 스펙(A)/품질(B) 분리, user_visible MINOR 는 승격 전 고침. CEO 는 ship / fix(1회) / block.
