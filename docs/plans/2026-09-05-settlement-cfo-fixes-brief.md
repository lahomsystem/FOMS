# 정산탭 CFO 감사 후속 — 쉬운 수정 5건 멀티 에이전트 브리프 (2026-09-05)

> 워크플로 에이전트(CEO·BE 워커·FE 워커·통합 검증자·리뷰어 2·수정자)에게 건네는 **유일한 컨텍스트 원본**이다.
> 감사 보고서 `docs/plans/2026-09-05-settlement-cfo-review-report.md` §3(결함)·§4(백로그)·§8(라벨 해석표)이 스펙 원문이다. **먼저 §3 의 해당 항목을 읽는다.**
> 사용자 결정(2026-09-05): 백로그 중 반나절짜리 5건만 고친다. B-02(보류 누적 잔액, M)·F-07 의 RETRO 누적(M)·D-03·H-01 인덱스·나머지는 **범위 밖**.

## 0. 환경 (절대 규칙)

- 워크트리 `C:/tmp/foms-s-settle-cfo` · 브랜치 `session/settle-cfo` · base origin/deploy `7100e2aa1` + 문서 커밋 `8894e4c41`. **모든 명령을 이 디렉토리에서**(`cd C:/tmp/foms-s-settle-cfo && pwd && ...`). `C:/DEV/FOMS` 금지(다른 세션이 같은 탭을 편집 중).
- 셸 bash. pytest 앞에 `PYTHONIOENCODING=utf-8`. 저장소 파일은 **CRLF** — Edit 도구는 그대로, 파이썬으로 통째 다시 쓸 땐 `newline=''` 로 읽고 `\r\n` 유지.
- **git 금지**(commit·stash·checkout·reset 전부). 커밋·push 는 총괄이 한다.
- 문제 수정 정책: 근본 원인만. `try/except: pass`·`# TODO`·증상 덮기 금지. 함수 50줄 이하·docstring·타입 힌트(신규 함수). 인라인 style 금지·jQuery 금지. JS 마크업은 기존처럼 createElement+textContent.
- **재계산 금지(계약 D-4)**: 네이버 금액은 원값 합산·병기·문구만. 새 KPI 는 전부 저장값의 SUM/COUNT 다. 파생은 비율뿐.
- 산출 폴더 `OUT2 = C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo_fix`(이미 존재). 설계·검증 로그·리뷰는 여기.
- 응답은 한글. 코드 주석은 이 저장소 관례대로 **왜(why)** 를 한글로.

## 1. 수정 5건 (완료 기준 포함)

| # | 항목(보고서) | 요지 | 완료 기준 |
|---|---|---|---|
| T1 | D-02 예외 머리 숫자 | `exception_count` 를 상한 적용 **전 모집단**으로(미매칭 총수 + 일별 3종 미절단 건수 + run 예외 수, 추가 질의 0). 응답에 kind 별 총수(`exception_totals`)와 갈래별 상한(`exception_cap`). 예외 표 머리에 "N건 중 M건 표시(갈래별 상한 50)". 요약 스트립·채널 배지는 모집단 수. | strip 테스트 3곳(`test_settlement_channel_strip.py:204·215·325`)을 모집단 의미로 교체 + **상한 초과 픽스처**에서 count > len(exceptions) 확인 + **음성 대조군**(상한 미만이면 count == len) |
| T2 | D-01 미매칭 정산액·aging | `_build_case_stats`(settlement_channel.py:609~650) group-by 에 `sum(settle_expect_amount)` 과 aging CASE(정산 예정일 기준 오늘 대비 <30 / 30~59 / 60~89 / 90+ / 미래)를 붙인다. kpi 에 `unmatched_amount`(원값 부호합)·`unmatched_settled_amount`(완료분)·`unmatched_aging`(구간별 {count, amount}). 화면: 매칭률 타일 부제와 예외 표 머리에 "FOMS 미연결 N건 · X원(90일+ Y원)". | API 계약 `_KPI_SCALARS`(test_settlement_channel_api.py:74) 갱신 + 신규 테스트(미매칭 2건·구간 2개 픽스처, 완료/미완료 분리, 취소 음수 원값 유지) + 스트립 질의 예산 6 유지 |
| T3 | F-07 창당 1회 가드 | `run_naver_settle_sync.py::_run_loop`(165~186) 가 KST 하루에 1회만 `_sync_once` 를 부른다(성공 시 그 날짜 기록, 예외 시 다음 tick 재시도 허용). 판정을 순수 함수(예: `should_run(now, at, window, last_run_day)`)로 빼서 테스트. | 순수 함수 테스트 4건: 창 안 첫 tick 실행 / 같은 창 다음 tick 미실행 / 다음 날 창 실행 / 창 밖 미실행. 비교군 `run_naver_auto_dispatch.py:140~141` 패턴 참고 |
| T4 | 라벨 묶음(A-01·A-03·G-01·G-03·G-04·C-02) | ① 워터폴 캡션/마지막 줄 "정산 금액 = 정산 완료액 + 정산 예정액(미입금)" ② 정산 예정액 타일 세부에 "입금 방식 미정 X원" — 커널 `_daily_totals`(529~550)에 `expected_unassigned`(settle_method_type 없는 미완료 행 합, 원값) → kpi `expected_unassigned_amount` ③ 완료액 부제 → "정산 예정일 창 안 · 완료 처리된 행의 정산 금액(계좌+충전금)" ④ "정산 예정액" 타일 라벨 → "미입금 정산액", 부제 "일별 정산 금액 중 미완료분 · 건별 '정산 예정 금액'과 다름" ⑤ 대사 배너에 "결제 정산 금액(paySettleAmount) 기준" ⑥ 원장 머리에 "이 축·이 기간 합계 N건 · Σ정산 예정 금액 X원" 한 줄 + "원장 금액 = 정산 예정 금액(수수료 차감 후·보류 전), KPI 정산 완료액 = 보류 반영 후 실입금" 한 문장 — 합계는 서버가 `ledger.totals`(같은 필터의 SUM, 원장 종류별 금액 컬럼) 로 내린다. | 렌더 계약(`test_settlement_channel_render.py`)에 문구 6개 리터럴 등재, API 테스트에 `expected_unassigned_amount`·`ledger.totals` 검증(음성: 완료 행만 있으면 0) |
| T5 | C-01 전기 정의 | `_previous_range`(322~335)에 granularity 인자: `month` 이고 조회가 **꽉 찬 달력 월**(from=1일·to=말일)이면 직전 같은 개월수의 달력 월, 아니면 기존 같은 일수. API 응답에 `range.prev = {from, to}`. KPI 델타 라벨 "전기 대비" → "전기(MM-DD~MM-DD) 대비", 차트 범례 "전기 비교(정산 금액)" 도 구간 표기. 집계 탭(`settlement_aggregation.py:275 _previous_month_range`)과 의미가 같아진다. | 테스트: 2월 조회 전기 = 01-01~01-31, 3월 = 02-01~02-28, 2개월(07-01~08-31) = 05-01~06-30, 부분 월(08-06~09-19) = 기존 45일 규칙, `granularity=day` 불변. `_DATA_KEYS`/`range` 계약 갱신 |

핀: 채널 CSS/JS 2줄(`settlement_dashboard_body.html:22·425`) `20260903i → 20260905a`, `tests/domains/test_settlement_channel_render.py:72 _CHANNEL_PIN = "20260905a"`. 셸 4줄(`20260903d`)은 **건드리지 않는다**(dashboard.js·css 변경 없음). 요약/실무 파셜·JS 에 "예정" 리터럴 금지(채널 표면만 허용).

## 2. 파일 소유권 (겹치면 결과 폐기)

| 워커 | 편집 허용 파일 |
|---|---|
| **BE** | `foms/services/settlement_channel.py` · `scripts/maintenance/run_naver_settle_sync.py` · `tests/domains/test_settlement_channel_api.py` · `tests/domains/test_settlement_channel_strip.py` · `tests/services/integrations/test_naver_settle_sync.py`(또는 신규 `tests/services/integrations/test_naver_settle_sync_loop.py`) · `foms/api/cs/settlement_channel.py`(응답 통과에 필요할 때만) |
| **FE** | `static/js/settlement/channel.js` · `static/css/settlement/settlement-channel.css` · `templates/cs/partials/settlement_channel_body.html` · `templates/cs/partials/settlement_dashboard_body.html`(**22·425행 채널 핀 2줄만**) · `tests/domains/test_settlement_channel_render.py` |
| CEO(설계) | `OUT2/fix_design.md` 만 |
| 통합 검증자 | 위 전부(통합 결함 수리만, 새 기능 금지) |
| 리뷰어 2 | 편집 금지 |
| 총괄 | 원장 `docs/plans/2026-09-05-settlement-cfo-fixes-ledger.md`·AI_STATUS·커밋·push·스테이징 QA |

BE↔FE 계약(키 이름·문구·핀 값)은 **CEO 설계가 확정**하고 두 워커는 그 이름을 그대로 쓴다. FE 는 BE 가 끝나기 전에도 설계서의 키 이름으로 구현한다(픽스처는 렌더 테스트 안 가짜 응답).

## 3. 게이트 (통합 검증자가 전부 돌리고 원문 첫·끝 줄을 `OUT2/gates.md` 에 적는다)

```
cd C:/tmp/foms-s-settle-cfo && pwd
python -c "import app; print('APP_OK')"
PYTHONIOENCODING=utf-8 python -m pytest tests/domains -k settlement -q -p no:cacheprovider          # 기준선 922 passed, 줄어들면 red
PYTHONIOENCODING=utf-8 python -m pytest tests/services/integrations/test_naver_settle_sync.py tests/services/integrations/test_naver_settle_sync_loop.py -q -p no:cacheprovider
PYTHONIOENCODING=utf-8 python -m pytest tests/contracts tests/domains/test_foms_namespace_imports.py -q -p no:cacheprovider
PYTHONIOENCODING=utf-8 python -m pytest tests/performance/test_perf_regression_guard.py -q -p no:cacheprovider
node --check static/js/settlement/channel.js
git diff --name-only | xargs -I{} sh -c 'file "{}" | grep -q CRLF || echo "LF-ONLY {}"'   # 편집 파일 CRLF 유지 확인
grep -n "예정" templates/cs/partials/settlement_dashboard_body.html templates/cs/partials/settlement_operations_body.html static/js/settlement/dashboard.js static/js/settlement/operations.js | grep -v "정산 예정일" ; echo "(위 출력 0줄이어야)"
```
pre_push_smoke 와 push 는 총괄 몫.

## 4. 함정 (감사에서 확인된 사실)

- `exception_count` 는 `build_channel_strip`(settlement_channel.py:1316)이 `len(exceptions)` 로 내고, strip 테스트 3곳이 그 정의를 핀으로 박아 둔다 — 테스트 정의부터 바꿔야 red 가 안 난다.
- `_kpi_block` 은 현재·전기 두 번 불린다(전기 블록도 같은 키 집합) → 새 kpi 키는 전기에도 생긴다. `_KPI_SCALARS | {"prev"}` 계약.
- `_build_case_stats` 는 스트립에서도 쓰인다 → 질의 예산 6(`test_settlement_channel_strip.py`)을 지키려면 group-by 확장으로 풀어야지 질의를 더하면 red.
- `get_today_kst()` 는 `date` 반환. aging 기준일은 이것.
- `_MOCKUP_LEFTOVERS` "예정" 스캔: 채널 파셜·channel.js 만 예외. `settlement_dashboard_body.html` 의 채널 앵커 블록에 한글 넣지 말 것.
- `test_settlement_channel_render.py:636` 근처 document 리스너 3개 계약 — 새 전역 리스너 금지.
- `run_naver_settle_sync.py` 는 모듈 import 시 app 을 부팅할 수 있다 — 순수 함수를 테스트하려면 import 부작용을 확인하고, 필요하면 함수를 부작용 없는 위치에 둔다(테스트가 `app` 을 import 하는 것 자체는 다른 테스트도 하므로 허용).
- `.alert` 자동 닫힘 5초 — 상시 안내 문구는 alert 가 아니라 카드 캡션/머리 줄에.
- 워크트리 cwd 는 턴 경계에서 리셋된다 — 매 명령 앞 `cd ... && pwd`.

## 5. 반환 계약

전부 StructuredOutput(스키마는 워크플로 스크립트). 워커는 편집 파일 목록·돌린 테스트 명령과 결과 첫·끝 줄·설계서와 달리한 점을 반환한다. 리뷰어는 스펙 준수(A)와 코드 품질(B)을 **분리** 판정하고 pre-judge 하지 않는다. CEO 는 ship / fix(1회) / block.
