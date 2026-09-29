# FOMS 언어·프레임워크 이전 필요성 정밀 분석 — 에이전트 지시서 (2026-09-28, 검수 반영판)

> FOMS 총괄 개발자가 분석 에이전트에게 건네는 지시서다. 이 파일만 읽고 시작한다. 세션 히스토리·개인 메모리는 붙이지 않는다. 경로는 저장소 루트 `C:/DEV/FOMS` 기준 상대 경로다.

## 0. 이 문서를 받는 에이전트에게

- 답할 질문 하나: **FOMS 를 지금의 언어(Python)·웹 프레임워크(Flask)·화면 방식(Jinja + Vanilla JS)에서 다른 언어나 프레임워크로 옮겨야 하는가.** 옮긴다면 어느 경계(백엔드·프런트·워커)를, 무엇으로, 언제. 옮기지 않는다면 무엇이 그 판정을 뒤집는가.
- 만들 것: 판정 보고서 1개 + 진행 원장 1개. 보고서 `docs/plans/2026-09-28-foms-language-migration-assessment-report.md`, 원장 `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md`. 둘 다 총괄만 쓴다. 이 문서가 곧 플랜이다(§7).
- 출발점: 2026-09-06 시스템 검토 보고서 `docs/plans/2026-09-06-foms-system-review-report.md` ⑤(276행부터)가 이미 "조건부 유지" 판정을 냈다. **그 판정은 이 분석의 결론이 아니라 반증할 가설이다**(§5). 그 보고서는 8차원 전체를 봤고 언어 교체는 한 절로만 다뤘다. 이 분석은 언어·프레임워크 한 축만 깊게 판다.
- 기준 커밋: 사실 카드(§2)는 deploy `fbb391bee` 기준이다. 시작할 때 `cd C:/DEV/FOMS && git log --oneline -1` 로 HEAD 를 원장에 적는다. 다시 잰 값이 다르면 "재측정: 값 — 명령" 으로 병기한다. 표본 명령은 끝점을 `fbb391bee` 로 고정했으니 HEAD 가 움직여도 같은 결과가 나와야 한다.
- `docs/AI_STATUS.md` 상단 40줄은 읽되 **갱신하지 않는다**(쓰기는 위 2파일뿐). 커밋 단계는 없다 — 커밋 여부는 사용자가 정한다.

### 0.1 새 세션 시작 프롬프트(복붙용)

새 세션(저장소 `C:/DEV/FOMS`, deploy 브랜치)의 첫 메시지로 아래를 그대로 붙인다.

```text
**B FOMS 언어·프레임워크 이전 필요성 정밀 분석을 실행해.
유일한 컨텍스트 = docs/plans/2026-09-28-foms-language-migration-assessment-prompt.md — 먼저 전부 읽어. 세션 히스토리·메모리는 붙이지 마.
플랜 = 그 문서 §7, 원장 = docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md. 이 메시지로 플랜 승인을 갈음한다. 커밋 단계는 없다.
실행 = 워커 4개(W1~W4)를 Agent 도구로 한 메시지에서 병렬 호출, 너는 총괄(통합·판정). 통합 초안이 나오면 리뷰어 2개(반대 심문·사실 검증)를 병렬로.
결과물 = docs/plans/2026-09-28-foms-language-migration-assessment-report.md + 원장.
완료 기준 = 프롬프트 §8 전부.
규칙 = 읽기 전용(코드 수정·패키지 설치·git 변경·push 금지), 운영 수치 추정 금지, 버전·지원 종료 같은 외부 사실은 출처 URL + 확인 날짜, 한글·한자 금지.
끝나면 §8 을 직접 다시 돌리고 표본 앵커 5곳을 열어 확인한 뒤, 경계별 판정·뒤집힘 조건·열린 질문을 한글로 보고해.
```

## 1. 페르소나·임무

너는 **FOMS 수석 아키텍트이자 그 판정의 반대 심문관**이다. 제품은 가구 주문 관리 ERP 로, 워크플로 9단계(RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED)를 현장(실측·시공 태블릿, 아이폰 사파리·웹뷰)과 사무실(PC ERP)이 함께 돌린다. 네이버 커머스·카카오 알림톡(solapi)·채널톡·지오코딩·웹푸시가 외부 채널로 붙는다. 개발은 **사람 1명 + AI 코딩 에이전트**가 한 달에 600커밋 넘게 내는 속도다(§2.1).

범위: PostgreSQL(JSONB)·Cloudflare R2·Railway·Cloudflare 엣지는 **고정 조건**이다. 후보가 이것들을 바꾸도록 강제하면 그 비용을 후보 비용에 넣는다.

판단 기준은 "어느 언어가 더 좋은가" 가 아니다. **"FOMS 가 겪는 실제 문제 중 언어·프레임워크 때문인 것이 있는가, 있다면 옮기는 것이 같은 언어 안에서 고치는 것보다 싼가"** 다.

임무:
1. 문제 귀속: 사고·결함·성능·수명(보안 패치)·에이전트 재작업 문제를 원인별로 갈라, 언어·런타임·프레임워크에 귀속되는 몫을 수치로 낸다.
2. 후보 평가: §4.2 후보 전부를 같은 결정 규칙(§4.3)으로 판정한다. C0·C1 도 예외 없이 같은 수지표를 채운다. 이전 후보마다 **가장 강한 찬성론을 먼저 쓰고** 그다음 반박한다.
3. 경계별 판정: 백엔드·프런트·워커(백그라운드 루프)를 따로 판정한다. 한 경계만 옮기는 답도 정답일 수 있다.
4. 뒤집힘 조건: 판정을 바꿀 측정 가능한 조건(지표·측정 방법·임계값·재평가 시점)을 낸다.

## 2. 사실 카드 (HEAD `fbb391bee`, 2026-09-28 총괄 측정 + 검수자 재측정)

다시 재지 말고 인용한다. 워커가 다시 잰 값이 다르면 병기한다.

### 2.1 제품·팀·변경 속도
- 커밋(병합 제외): 2026-06-01 이후 2,979건(`git log --since=2026-06-01 --no-merges --oneline fbb391bee | wc -l`), 그중 제목이 `fix` 로 시작하는 커밋 1,073건(36%). 2026-09-01 이후 646건(병합 포함).
- 8주(2026-08-03 ~ 09-27) 경계별 변경 줄 합(추가+삭제, `--numstat`): `foms/` 83,020 · `static/` 51,835 · `templates/` 23,326.
- 사고 기록 `docs/incidents/` 15건. 9-06 보고서 시점(`062723348`)에는 5건이었고 이후 10건이 늘었는데, 그중 7건(08-03~09-03 날짜)은 **9-06 이후 소급 등재**다. 증가율로 쓰지 말고, 무엇을 등재할지 고른 선별 편향이 있는 모집단으로 다룬다.
- Railway 서비스 4종(web·WORKER·FOMS-cron·SIDEFX, 환경변수가 서비스마다 다름), 리전은 싱가포르(`docs/guides/NETWORK_EDGE_TAIL_FIX.md:5-7`).

### 2.2 런타임 스택과 핀
- `requirements.txt`(139줄): `alembic==1.16.1`(2행) · `Flask==2.3.3`(31행) · Flask 확장 핀 5종(32-36행, Flask-Session 0.5.0 등) · `Jinja2==3.1.2`(49행) · `psycopg2-binary==2.9.9`(67행) · `pydantic>=2.9.0,<3.0.0`(70행) · `SQLAlchemy==2.0.23`(95행) · `Werkzeug>=2.3.5,<3`(106행) · `flask-socketio>=5.3.6`(113행) · `gevent>=24.10.1`(115행) · `rq>=1.15.0`(126행).
- 파이썬 표기 3갈래: `.python-version` 3.11.9 / `Dockerfile:3` python:3.12-slim / `.github/workflows/ci.yml:54` 3.12.
- 서버: `start.sh:127` `gunicorn -k gevent -w 2 --timeout 120`. 워커 컨테이너는 RQ 소비자 + 백그라운드 서브셸 루프.
- Werkzeug 비공개 함수 몽키패치 `app.py:22-36`(`_hash_internal`, import 는 20행 — 9-06 인용과 같은 위치). 테스트는 `tests/conftest.py:26-28` 에서 `DEFAULT_PBKDF2_ITERATIONS` 를 바꾼다. LimitedStream 은 `foms/platform/request_limits.py:248` 에서 쓴다(import 46행, 9-06 인용 225행에서 밀림).
- 9-06 권고의 이행 상태(부분 이행): 이행 = 방향 래칫 `2b090b565` · 무감독 루프 하트비트·워커 Sentry `41df23606` · 로그인 한도·잠금 `40d25bb1b` · 드리프트 기준선 래칫 `9e51b2e73`(모두 2026-09-06). 미이행 = 잠금 파일·`pyproject.toml`·`requirements.in`·`.github/dependabot.yml`·mypy/ruff 설정·자산 해시 매니페스트(`ls pyproject.toml requirements.in .github/dependabot.yml mypy.ini ruff.toml static/asset-manifest.json` → 전부 No such file).
- `requirements.txt` 의 fastapi·starlette·uvicorn 은 2026-01-16 pip freeze 잔재이며 foms import 0 이다(9-06 보고서 ⑤ 근거 6번째 줄). "이미 이행 중" 으로 읽지 마라.

### 2.3 코드 규모 (`git ls-files <dir>` 중 .py·.html·.js·.css 파일 수 / 줄 합)
- `foms/` 490파일 157,831줄 · `templates/` 283파일 59,659줄 · `static/` 316파일 142,181줄(JS 90,007 — vendor 압축본 alpine·htmx·konva 포함, CSS 52,174) · `tests/` 915파일 249,547줄(test_*.py 825) · `tools/` 123파일 23,164줄 · `scripts/` 45파일 7,392줄 · `migrations/` 98파일 7,897줄 · `models.py` 4,015줄.
- 템플릿 안 JS: `templates/orders/partials/erp_order_js.html` 같은 `*_js.html` 은 확장자가 html 이지만 JS 다(06-01 이후 변경 220회).
- 격리 트리 `Add In Program/` 98파일(React/TS 애드인, 런타임 import 0). 마지막 실질 변경 2026-05-17(08-28 커밋은 인코딩 일괄 수정) — 현역 TS 운영 경험이라기보다 휴면 자산이다.

### 2.4 이전 표면(갈아엎을 때 다시 써야 하는 것)
- 라우트 데코레이터 383 · `render_template(` 110 · `url_for(` 937(foms+templates) · `Column(` 950(models.py + wdcalculator_models.py) · `.query(` 748 vs `select(` 8 · Socket.IO `.emit(` 7.
```bash
cd C:/DEV/FOMS && echo "route: $(grep -rnE '@[a-z_]+\.(route|get|post|put|delete|patch)\(' foms --include=*.py | wc -l)"; echo "render_template: $(grep -rn 'render_template(' foms --include=*.py | wc -l)"; echo "url_for: $(grep -rn 'url_for(' foms templates --include=*.py --include=*.html | wc -l)"; echo "Column(: $(grep -c 'Column(' models.py wdcalculator_models.py | awk -F: '{s+=$2} END{print s}')"; echo ".query( $(grep -rn '\.query(' foms models.py --include=*.py | wc -l) / select( $(grep -rnE '\bselect\(' foms --include=*.py | wc -l)"
```
- 결합: Flask 테스트 클라이언트를 쓰는 테스트 파일 320(`grep -rlE 'test_client\(|\bclient\.(get|post|put|delete|patch)\(' tests --include=test_*.py | wc -l`) · 소스를 문자열로 읽는 계약 테스트 파일 264(`grep -rl 'read_text' tests --include=test_*.py | wc -l`) · `flag_modified` 175곳(`grep -rn 'flag_modified' foms --include=*.py | wc -l`).
- 타입 힌트: `foms/` 함수 4,614개 중 반환 타입 표기 3,753개(81.3%). 타입 검사기는 설정도 CI 잡도 없다. 명령(한 줄 grep 은 여러 줄 시그니처를 놓치므로 ast 로):
```bash
cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python -c "import ast,subprocess;fs=[f for f in subprocess.run(['git','ls-files','foms'],capture_output=True,text=True).stdout.split() if f.endswith('.py')];ns=[n for f in fs for n in ast.walk(ast.parse(open(f,encoding='utf-8').read())) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))];a=sum(n.returns is not None for n in ns);print('FUNCS',len(ns),'RETURN_ANN',a)"
```
- 하네스도 파이썬이다: `tools/` 123파일, `.claude/hooks/` 파이썬 가드, 파이썬·Jinja 소스를 파싱하는 smoke(`scripts/ops/pre_push_smoke.ps1`). 언어를 바꾸면 이것도 이중 유지 또는 재작성 대상이다.

### 2.5 성능 증거(범위가 다르다 — W2 가 화해시킬 것)
- `docs/harness/evidence/stress-tail-rca-construction-history-2026-07-02.json`: `meta.scope` = 시공·이력 대시보드 **2화면 한정** 꼬리 지연 분석. `verdict.bottleneck_layer` = `app_db_compute`, `network_tail` = false, 동시에 `deploy_infra_amplifier` = true(스테이징 증폭)·`sw_client_masking` = true.
- 다음 날 `docs/guides/NETWORK_EDGE_TAIL_FIX.md:5-6`(2026-07-03): "탭 로딩 간헐 2-9초 스파이크 = 한국 사용자 ↔ Railway 싱가포르 왕복 경로. 코드/서버/DB 아님", 근거는 서버 렌더 헤더 `X-FOMS-EPT-B7-RENDER-MS` 11-260ms(`foms/services/common/ept_b7_profile.py:20-21`).
- 성능 도구: `tools/perf/`(README), 예산 `tools/perf/perf_budgets.json`, CI `.github/workflows/perf-gate.yml`, 증거 JSON 추적 37개(`git ls-files docs/harness/evidence | grep -c '\.json$'`).

### 2.6 타입 오류가 원인인 사고 실례(찬성론 재료)
- `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md:11` — `int(stats.get("calls") or 0)` 에 dict 가 들어와 `TypeError`, 루프 `try` 밖이라 프로세스 종료. 정적 타입 언어면 막혔을 후보다. 단, 같은 언어의 타입 검사기(mypy strict)로도 막혔는지, 감독자 부재(운영 설계)가 진짜 원인인지까지 갈라야 한다.

## 3. 절대 규칙

1. **읽기 전용**: 워커·리뷰어는 파일을 편집하지 않는다. 총괄만 §0 의 보고서·원장 2개를 쓴다. 다른 창이 같은 워킹트리를 쓴다. 임시 파일은 **세션 스크래치패드 절대 경로**(시스템 프롬프트에 적힌 경로)에만 — `/tmp` 는 Git Bash 와 파이썬이 서로 다른 폴더를 가리키므로 쓰지 않는다.
2. **앵커 의무**: 모든 관측에 백틱으로 감싼 `경로:행`, 또는 실행한 명령과 그 결정적 출력 한 줄. 앵커 없는 관측은 `[가설]` 로만 적고 확인됨으로 올리지 않는다. 공백이 든 경로(`Add In Program/`)는 앵커 대신 명령 출력으로 근거를 댄다.
3. **외부 사실 규칙**: 버전 지원 종료일·보안 패치 정책·SDK 존재 여부·채용 시장·언어별 AI 코딩 성능 같은 저장소 밖 사실은 context7 MCP 또는 WebSearch/WebFetch 로 확인하고 `[외부: URL · 확인 2026-MM-DD]` 를 단다. 학습 지식에서 꺼낸 날짜·버전은 쓰지 않는다. 확인 못 하면 "확인 필요".
4. **과대광고 금지**: "Go 는 N배 빠르다" 류 일반 벤치마크는 FOMS 에서 측정된 병목 구간과 연결될 때만 근거가 된다. 연결 안 되면 [가설].
5. **매몰 비용 금지**: "이미 많이 짰으니 유지" 는 근거가 아니다. 비용은 앞으로 드는 것만 센다. 반대로 "새 언어가 현대적" 도 근거가 아니다. **증거 부재는 어느 쪽의 근거도 아니다** — `미확정` 으로 적는다.
6. **운영 수치 추정 금지**: 사용자 수·주문량·트래픽·비용·기기 수는 "확인 필요" 로 ⑨ 에 보낸다. postgres MCP 는 로컬 dev DB 이며 읽기 질의만, 결과에 "로컬 dev" 라고 적는다.
7. **실서버 측정**: 워커는 실서버에 접속하지 않는다. W2 가 필요한 스테이징 측정 명령을 반환하면 **총괄이** 스테이징 측정 계정(`docs/guides/REAL_SERVER_TEST_ACCOUNT.md`, 크리덴셜 읽는 곳 `tools/perf/staging_perf_gate.py:807-808`)으로 로그인 1회 + 읽기 요청 측정 1회만 직접 실행한다. 쓰기 요청 금지. production 접근 금지.
8. **설치 금지**: `pip install`·`npm install`·`npx` 금지. 없는 도구(mypy·pyright·tsc 등)는 "없음" 으로 적는다.
9. **git 변경 금지**: `log`·`show`·`blame`·`ls-files`·`ls-tree`·`diff` 조회만. push 는 절대 하지 않는다.
10. **전체 pytest 금지**: 허용은 `--collect-only`, 단일 파일, `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"`. 300초 넘으면 끊고 적는다.
11. **명령 형식**: `cd C:/DEV/FOMS && ...` 로 시작하는 bash, python 앞에 `PYTHONIOENCODING=utf-8`, grep 은 `--include=*.py` 등으로 `__pycache__` 를 뺀다, 긴 명령은 `timeout N`.
12. **한글 출력, 한자 금지**(코드·API·고유명사 예외).
13. **권고 규율**: 권고가 프로젝트 규칙(인라인 스타일 금지·jQuery 금지·`static/css/foundation/erp-pro.css` SSOT·structured_data 는 `copy.deepcopy` → `flag_modified`·근본 원인 수정)을 어기게 만들면 안 된다.

## 4. 분석 틀

### 4.1 분석 축 7개

축마다 핵심 질문 → 볼 곳 → 방법 → 함정. 결론은 핵심 질문에 답하는 형태로만.

**L1 수명·보안 패치·보안 자세**
- 질문: ① 지금 조합(파이썬 3.11/3.12 · Flask 2.3 + 확장 5종 · Werkzeug 2.x · Jinja2 3.1.2 · SQLAlchemy 2.0.23 · gevent · psycopg2)이 24개월 뒤에도 보안 패치를 받는가. 못 받는다면 같은 언어 안 상향(Flask 3·Werkzeug 3·파이썬 3.13+·psycopg3)으로 해결되는가. ② 인증·세션·CSRF·템플릿 이스케이프·SQL 주입 방어를 프레임워크가 얼마나 대신해 주고, 후보 언어로 옮기면 그 방어를 다시 세워야 하는가.
- 볼 곳: `requirements.txt:31-36` · `requirements.txt:106` · `app.py:22-36` · `tests/conftest.py:26-28` · `foms/platform/request_limits.py:248` · `start.sh:127` · `Dockerfile` · 9-06 보고서 ⑤ 첫 근거(상향 차단 4곳).
- 방법: 패키지마다 지원 종료일·마지막 보안 릴리스를 외부 확인. 상향 차단 요소 전수: `cd C:/DEV/FOMS && grep -rn --include=*.py -E "werkzeug|_hash_internal|gevent|psycogreen" foms app.py tests/conftest.py; grep -n -E "gevent|psycogreen" start.sh`. Flask 확장 핀 전부를 차단 후보로 센다.
- 함정: "Flask 3 가 나왔다" 는 일반론이 아니라 FOMS 코드의 구체 차단 줄로 말하라.

**L2 성능·동시성 — 병목이 언어 탓인가**
- 질문: 사용자가 느끼는 지연 중 파이썬 실행 시간(CPU)이 차지하는 몫은 얼마이고, 나머지(네트워크 경로·DB·클라이언트·캐시)는 얼마인가. 더 빠른 언어로 옮겼을 때 줄어들 수 있는 상한은.
- 볼 곳: §2.5 두 문서 · `foms/services/common/ept_b7_profile.py` · `tools/perf/perf_budgets.json` · `.github/workflows/perf-gate.yml` · 추적된 증거 JSON · CPU 를 쓰는 후보(지도 생성 folium·이미지 Pillow·엑셀·rapidfuzz 매칭).
- 방법: 증거 JSON 에서 구간(네트워크·서버 렌더·DB)별 수치를 뽑아 표로. 두 문서는 범위가 다르다(2화면 한정 대 전역 탭 로딩) — 충돌인지 범위 차이인지부터 가른다. 동시성은 gevent 모델이 외부 API 대기(네이버·solapi)에 맞는지, 네이버 호출 IP 한도가 워커 1개를 강제하는지(`start.sh` 주석) 확인 — 그건 언어 제약이 아니라 외부 제약이다. 스테이징 측정이 필요하면 명령만 반환(§3.7).
- 함정: 응답 시간 차분으로 추정하지 말고 구간 계측 값만 쓴다. 증거가 없으면 "미계측" 으로 적고 필요한 측정을 ⑦·⑨ 에 적는다.

**L3 결함·사고 — 다른 언어라면 막혔을까**
- 질문: 사고 15건 전부와 fix 커밋 표본에서, 언어 이전만이 주는 고유 이득은 얼마인가.
- 표본(끝점 고정 — HEAD 가 움직여도 같은 82건, 앞 80건 사용):
```bash
cd C:/DEV/FOMS && git log --since=2026-06-01 --no-merges --format='%H %s' fbb391bee | grep -E '^[0-9a-f]+ fix' | awk 'NR % 13 == 0' | head -80
```
  표본 각 커밋은 `git show --stat <sha>` 와 diff 핵심 줄로 판정한다. 모집단 한계(제목이 `fix` 로 시작하지 않는 결함 수정은 빠진다)를 보고서에 적는다.
- 판정(겹치지 않는 4값, 커밋·사고마다 하나): **A** = 같은 언어에 도구만 더해도 막혔다(mypy/pyright strict·JSDoc+`checkJs`·린트·계약 테스트) · **B** = 정적 타입 다른 언어로 옮겨야만 막혔다(A 로는 안 됨) · **C** = 언어와 무관(업무 규칙·데이터 사본 동기·캐시·배포·운영 감독·CSS·외부 규격) · **U** = 판정 불가. **언어 이전의 고유 이득 = B 비율.** A 는 C1 의 이득이다.
- 보조 분류(원인 유형, 고정): `type` · `concurrency` · `domain` · `data-sync` · `cache-deploy` · `ui-css` · `integration` · `ops`. 보고서에 판정(A·B·C·U) × 유형 교차표를 낸다.
- 함정: 양성 후보만 세지 마라. 표본 전부를 판정해 4값 합이 표본 수와 같아야 한다. 파일 언어는 확장자가 아니라 내용으로 — `*_js.html` 은 JS 로 센다.

**L4 AI 에이전트 개발 적합성**
- 질문: 사람 1명 + 에이전트 체제에서 언어·프레임워크가 에이전트 실수율과 재작업에 영향을 주는가. 언어별(파이썬·JS·Jinja·CSS) fix 비율 = (fix 커밋이 건드린 횟수) ÷ (전체 커밋이 건드린 횟수).
- 방법: 분모와 분자를 같은 방식으로 센다.
```bash
cd C:/DEV/FOMS && git log --since=2026-06-01 --no-merges --format= --name-only fbb391bee | grep -vE '^$' | sed -E 's/.*_js\.html$/JS/; s/.*\.py$/PY/; s/.*\.js$/JS/; s/.*\.html$/HTML/; s/.*\.css$/CSS/' | grep -E '^(PY|JS|HTML|CSS)$' | sort | uniq -c
cd C:/DEV/FOMS && git log --since=2026-06-01 --no-merges --format='@@%s' --name-only fbb391bee | awk '/^@@/{f=($0 ~ /^@@fix/); next} f && NF' | sed -E 's/.*_js\.html$/JS/; s/.*\.py$/PY/; s/.*\.js$/JS/; s/.*\.html$/HTML/; s/.*\.css$/CSS/' | grep -E '^(PY|JS|HTML|CSS)$' | sort | uniq -c
```
  fix 가 몰린 상위 파일(`static/js/orders/erp-order-shared.js` 등)은 크기·셸 미러 구조와 함께 본다. 외부 연구(언어별 LLM 코딩 성능)는 출처가 있을 때만.
- 함정: "파이썬은 AI 가 잘 짠다" 류 통념은 [가설]. 저장소 수치가 우선. fix 비율 차이가 언어 탓인지 구조(대형 파일·미러 3벌) 탓인지 가르기 전에는 결론 금지.

**L5 이전 비용·위험 (정량)**
- 질문: 후보별로 다시 써야 하는 표면(§2.4)·다시 검증해야 하는 계약·데이터 계층(JSONB `flag_modified` 패턴, alembic 98파일, 두 번째 엔진 `wdcalculator_db.py`)·인증·세션·CSRF·Socket.IO·외부 통합 SDK·**하네스**(§2.4 끝)를 옮기는 비용은. **움직이는 과녁**: 8주에 foms 83k·static 52k·templates 23k 줄이 바뀌는 코드를 옮기는 동안의 기능 동결 또는 이중 구현 비용은.
- 방법: 테스트 자산을 둘로 가른다 — HTTP 경계만 두드리는 블랙박스 테스트(언어를 바꿔도 요청·응답 단언은 재사용 가능)와 내부 모듈·Jinja 소스·SQLAlchemy 세션에 묶인 테스트(재작성 필요). 경계별 주당 변경량은 `git log --since=<주 시작> --until=<주 끝> --no-merges --numstat --format= fbb391bee -- <foms/|static/|templates/>` 을 경계마다 따로, 최근 8주 각각. 비용 단위는 "개발 주(사람 1명 + 에이전트)" 로, 낙관·기준·비관 세 값과 산정식.
- 함정: 9-06 보고서의 "12~24개월" 을 그대로 쓰지 마라 — 산정식이 없다. 다시 산정한다.

**L6 프런트 경계(별도 판정)**
- 질문: JS 약 90k 줄(vendor 포함) + CSS 52k 줄 + Jinja 템플릿 283파일이 언어 이전 논의에서 가장 강한 후보인가. 현장 태블릿·아이폰 웹뷰·서비스 워커(`static/sw.js`)·셸 3벌 제약에서 C1-F·C5a·C5b·C5c(§4.2) 각각의 비용과 이득.
- 볼 곳: `static/js/` 대형 파일 · `static/sw.js` · `tests/contracts/wdcalculator/_node_runner.py`(JS 를 node 로 실행하는 전례) · `Add In Program/`(휴면 TS 자산).
- 함정: Railway 빌드에 node 단계를 넣을 수 있는지는 미확정이다. 가능 여부에 따라 C5a·C5c 비용이 갈린다고 적어라.

**L7 생태계·인력·운영**
- 질문: 후보 언어마다 FOMS 외부 통합(네이버 커머스 REST·solapi·채널톡·Web Push VAPID·Cloudflare R2 S3 호환·Sentry)의 공식 SDK 가 있는가. 두 번째 개발자를 뽑을 때 언어가 제약인가(한국 시장 — 외부 근거 없으면 확인 필요). Railway 배포·관측 도구가 후보 언어를 똑같이 지원하는가.
- 함정: SDK 존재는 외부 확인, 개인 인상 금지.

### 4.2 평가 후보

| 키 | 후보 | 경계 | 판정 등급 |
|---|---|---|---|
| C0 | 현상 유지 + 9-06 미이행 거버넌스(잠금·dependabot·해시 매니페스트 등) 이행 | 전체 | 유지 |
| C1-B | 같은 언어 현대화: Flask 3 · Werkzeug 3 · 파이썬 3.13+ · psycopg3 · SQLAlchemy `select()` 전환 · mypy/pyright 래칫 | 백엔드·워커 | 같은 언어 현대화 |
| C1-F | 같은 언어 현대화: JSDoc + `tsc --checkJs` 래칫(.js 그대로, 번들 없음) · 대형 파일 분해 · node 실행 계약 확대 | 프런트 | 같은 언어 현대화 |
| C2 | 같은 언어 프레임워크 교체: FastAPI(+Jinja) / Django / Quart | 백엔드 | 프레임워크 이전 |
| C3 | 다른 언어 백엔드 전면 이전: TypeScript(Node — NestJS·Fastify·Hono 중 하나) / Go / Kotlin·Java(Spring Boot) / C#(.NET) | 백엔드 | 전면 언어 이전 |
| C4 | 부분 이전(교살자 방식): 워커·네이버 통합·실시간 중 한 경계만 다른 런타임 | 워커·통합 | 부분 언어 이전 |
| C5a | TypeScript 소스 전환(.ts + 빌드 단계, 파일 단위 점진) | 프런트 | 부분 언어 이전 |
| C5b | htmx 확대(서버 렌더 조각으로 JS 축소) | 프런트 | 프레임워크 이전 |
| C5c | SPA(React·Vue 등) 재작성 | 프런트 | 전면 언어 이전 |

- 위 후보는 빼거나 합치지 않는다. 워커는 증거가 있으면 후보를 **추가 제안**할 수 있다(예: PHP Laravel·Ruby Rails·Elixir Phoenix LiveView). 추가하지 않은 주요 대안은 보고서 ⑤ 끝에 "제외 후보와 이유" 로 한 줄씩 적는다.

### 4.3 결정 규칙 — 세 관문 + 수지표(후보 × 경계마다)

**모든 후보(C0·C1 포함)가 같은 수지표를 채운다**: 24개월 비용, 24개월 이득, 순이득(낙관·기준·비관), 36개월 민감도 한 줄. C0·C1 의 비용·이득은 9-06 권고의 실제 이행 실적(§2.2 — 3주 동안 무엇이 이행됐고 무엇이 안 됐나)으로 할인한다. "권고했지만 안 한 것" 은 계획된 이득이 아니라 실적 없는 약속으로 센다.

이전 후보(C2~C5c)는 아래 세 관문을 **모두** 통과할 때만 권고한다.
- **G1 원인 관문**: 해결하려는 문제가 언어·런타임·프레임워크에 귀속된다는 저장소 또는 외부 증거가 있다. 증거 출처는 L1(패치 수명·보안 자세)·L2(지연)·L3(B 비율)·L4(언어별 fix 비율 차이)·L7(SDK·인력) 전부 인정한다.
- **G2 대체 관문**: 그 문제를 같은 언어 안 대안(C0·C1-B·C1-F)으로는 막을 수 없거나, 막는 비용(기준값)이 이전 비용(기준값)의 절반을 넘는다. L3 의 A 는 C1 로 막히는 몫이므로 이전 근거가 아니다.
- **G3 수지 관문**: 이전 후보의 기준값 순이득이 C0·C1 중 더 나은 쪽의 기준값 순이득보다 크다. 이득 산정식의 뼈대:
  - 결함: (L3 의 B 비율) × (24개월 예상 fix 커밋 수 — 최근 3개월 추세) × (fix 1건당 평균 비용 — 가정값과 근거를 적는다)
  - 패치 수명: (현 조합이 보안 패치 창 밖에 머무는 개월 수, L1 외부 근거) × (같은 언어 상향 비용 대비 차액)
  - 에이전트 재작업: (L4 언어별 fix 비율 차이 중 언어에 귀속된 몫) × (해당 경계 변경량)
  - 지연: L2 에서 언어에 귀속된 지연 절감(측정된 것만)
- 관문을 막는 증거도 통과시키는 증거도 없으면 그 칸은 `미확정` 이다. 미확정이 하나라도 있는 이전 후보는 권고하지 않되, ⑦ 에 그 칸을 가를 측정을 반드시 적는다.
- 모든 이전 후보가 떨어지면 C0 와 C1(경계별 B·F) 중 **기준값 순이득이 큰 쪽**을 고른다.

## 5. 사전 가설(검증·반증 대상 — 결론으로 쓰지 마라)

각 가설에 `확인됨` / `반박됨` / `부분` / `미확정` 과 앵커를 단다.
- **H1** "사고의 원인은 스택이 아니라 거버넌스 공백이다"(9-06 보고서 ⑤ 근거 2번째, 사고 5건 기준). 지금 15건 전부를 L3 판정(A·B·C·U)으로 다시 가른다. 소급 등재 7건의 선별 편향을 적는다.
- **H2** "Flask 3 상향 차단 요소는 4곳뿐"(9-06 ⑤ 근거 1번째). L1 전수 명령과 Flask 확장 핀 5종으로 다시 센다.
- **H3** "교체 비용 12~24개월"(9-06 ⑤ '교체 시 비용'). 산정식이 없다. L5 로 다시 산정.
- **H4** "지연의 주범은 네트워크 경로다"(`docs/guides/NETWORK_EDGE_TAIL_FIX.md:5`) 대 "병목은 앱·DB 계산이다"(2026-07-02 RCA JSON, 2화면 한정). 범위 차이인지 모순인지, 지금은 어느 쪽인지.
- **H5** "타입 오류 사고(§2.6)는 정적 타입 언어의 이득을 보여준다". A(mypy 로도 막힘)인지 B 인지, 감독자 부재가 더 큰 원인인지.
- **H6** "JS 대형 공용 파일의 높은 fix 비율은 언어(타입 없음) 탓이다" 대 "구조(6천 줄·셸 3벌 미러) 탓이다".
- **H7** "SQLAlchemy `.query(` 748 대 `select(` 8 은 이전 위험이다". SQLAlchemy 2.x 에서 레거시 Query API 의 지원 상태를 외부 확인.
- **H8** "9-06 판정 구조는 반증 불가능하다" — 9-06 은 "조건 미이행이면 부적합으로 넘어가지만 그때도 답은 교체가 아니라 조건 이행" 이라고 했다. 먼저 9-06 ④ 권고별 이행표(SHA 또는 `ls` 근거, §2.2 에서 출발)를 만들고, 그다음 어떤 증거가 나오면 9-06 논리로도 이전이 답이 되는지 적어라. 그런 증거를 하나도 정의할 수 없으면 H8 확인됨.

## 6. 보고서 형식

`docs/plans/2026-09-28-foms-language-migration-assessment-report.md`, 500줄 이하. 최상위 제목(`## `)은 아래 9개뿐이며 이 순서, 제목 첫 글자는 원문자 ①~⑨.
- **## ① 판정** — 경계별(백엔드·프런트·워커) 등급 한 줄씩 + 한 문단 결론. 9-06 판정과 같은지 다른지 명시.
- **## ② 세 관문과 수지표** — 행 = 후보(C0~C5c) × 경계, 열 = G1·G2·G3·순이득(기준)·36개월 민감도·최종. 행은 `| C0 |` 처럼 후보 키로 시작한다. 칸마다 한 줄 근거 + 앵커.
- **## ③ 문제 귀속** — L1·L2·L7 요약. L2 는 구간별 수치 표(출처 JSON 경로 포함).
- **## ④ 결함·사고 판정** — 표본 명령과 건수, A·B·C·U × 유형 교차표, 사고 15건 각 한 줄, B 비율, L4 언어별 fix 비율 표.
- **## ⑤ 후보별 찬성론과 반박** — C2~C5c 마다 가장 강한 찬성론(근거 포함) → 반박. 찬성론이 이긴 경우도 그대로 적는다. 끝에 "제외 후보와 이유".
- **## ⑥ 비용 모델** — 재측정 명령 + 출력 원문 + 산정식 + 낙관·기준·비관.
- **## ⑦ 뒤집힘 조건** — 표: 지표 · 측정 방법(명령 또는 도구) · 임계값 · 넘으면 바뀌는 판정 · 재평가 시점. 5개 이상, 경계마다 1개 이상, `미확정` 칸마다 1개.
- **## ⑧ 권고와 첫 걸음** — 판정에 맞는 다음 수 3개 이내. 각각 첫 걸음(한 세션 크기) + 검증 명령. 이전 판정이면 파일럿 경계 1개와 중단 조건.
- **## ⑨ 열린 질문과 가설 판정** — "운영 데이터 필요" 와 "사용자 결정 필요" 두 묶음 + 가설 표(행은 `| H1 |` ~ `| H8 |`).
- 모든 문장형 주장에 `[확인됨: 앵커]`, `[외부: URL · 확인 날짜]`, `[가설]` 중 하나.

## 7. 실행 절차

### 7.1 단계
1. 총괄: HEAD 기록, 이 문서 전부 읽기, `cd C:/DEV/FOMS && git status --porcelain > <스크래치패드>/status_before.txt` 로 시작 상태 저장, 원장 파일 생성(HEAD·시작 시각·워커 배치·시작 상태 줄 수).
2. 워커 4개를 **한 메시지에서** Agent 도구로 병렬 호출. 브리프에는 이 문서 경로, 담당 축·가설, §3 규칙, §7.2 반환 형식만 넣는다.
   - **W1 수명·생태계** — L1 · L7 · H2 · H7. 외부 확인 담당(context7·WebSearch).
   - **W2 성능·동시성** — L2 · H4. 스테이징 측정은 명령만 반환.
   - **W3 결함·사고·에이전트** — L3 · L4 · H1 · H5 · H6. 표본 80건과 사고 15건 전량 판정.
   - **W4 비용·경로·프런트** — L5 · L6 · H3 · H8. 후보별 비용 세 값과 C0·C1 이행 실적.
3. 워커 결과가 오면 **받는 즉시 원장에 요약·앵커·명령 출력을 옮긴다**(세션이 죽어도 남게). 워커 보고는 주장이다 — 총괄이 워커마다 앵커 2곳 이상을 직접 열어 대조한 뒤 통합한다. W2 가 스테이징 측정을 요청했으면 §3.7 대로 총괄이 실행.
4. 총괄이 보고서 초안 작성(§6).
5. 리뷰어 2개를 병렬 호출(편집 금지, 발견만 반환):
   - **R1 반대 심문** — 초안의 판정을 뒤집는 것이 임무. 이전 찬성 쪽에서 가장 강한 논거를 찾아 초안이 공정하게 다뤘는지, 세 관문·수지표에 논리 구멍(증거 없이 통과·차단, C0·C1 을 실적보다 후하게 셈)이 있는지.
   - **R2 사실 검증** — 앵커 10개 무작위 대조, 외부 인용 URL 5개 재확인, §2.4·L3·L4 명령 재실행해 수치 일치 확인, §8 기계 검사 실행.
6. 총괄이 리뷰 발견을 **원장에 전량 기록한 뒤** 반영(1회). 반영 못 한 것은 사유와 함께 ⑨ 에.
7. §8 완료 검증 실행 → 보고.

### 7.2 워커 반환 형식(텍스트, 이 순서)
- `axis_answers`: 담당 축 핵심 질문별 답 + 앵커
- `hypotheses`: 담당 가설별 판정 + 앵커
- `gate_inputs`: 후보 × 경계별 G1·G2·G3 판단 재료와 수지표 재료(수치·앵커)
- `external_facts`: 외부 사실 목록(URL · 확인 날짜)
- `open_questions`: 측정 못 한 것(운영 데이터 / 사용자 결정 구분)
- `commands_run`: 실행한 명령과 결정적 출력 한 줄씩

## 8. 완료 기준·검증 명령

완료 = 전부 통과. 셸 상태는 호출 사이에 이어지지 않으므로 1·2·4·5·6 은 아래 한 덩어리로 실행한다.
```bash
cd C:/DEV/FOMS && R=docs/plans/2026-09-28-foms-language-migration-assessment-report.md && \
test -s $R && echo REPORT_OK; \
echo "SECTIONS $(grep -E '^## ' $R | cut -c4-6 | tr -d '\n')"; \
echo "EXTERNAL $(grep -c '\[외부: http' $R)"; \
echo "CAND_ROWS $(grep -cE '^\| *C(0|1-B|1-F|2|3|4|5a|5b|5c) *\|' $R) HYP_ROWS $(grep -cE '^\| *H[1-8] *\|' $R)"; \
PYTHONIOENCODING=utf-8 python -c "import io,sys;L=[len(l) for l in io.open(sys.argv[1],encoding='utf-8')];print('LINES',len(L),'MAX_LINE',max(L))" $R
```
1. `REPORT_OK` 출력.
2. `SECTIONS ①②③④⑤⑥⑦⑧⑨`(최상위 제목 9개가 이 순서, 그 밖의 `## ` 제목 없음).
3. 앵커 실존·한자 0: 아래 스니펫 → `MATCHED` 20 이상 · `ANCHOR_BAD 0` · `HANJA 0`. 실패 앵커는 고치거나 `[가설]` 로 내린다.
4. `EXTERNAL` 5 이상.
5. `CAND_ROWS` 9 이상 · `HYP_ROWS` 8.
6. `LINES` 500 이하.
7. 저장소 무변경(다른 창 변경과 분리): `cd C:/DEV/FOMS && git status --porcelain | diff <스크래치패드>/status_before.txt - | grep '^>' | grep -v language-migration-assessment || echo ONLY_REPORT_FILES_ADDED` — 늘어난 줄이 보고서·원장뿐이어야 한다. 다른 창이 만든 변경이 보이면 사실만 적고 손대지 않는다.

앵커 실존 검사 스니펫(글자 그대로):
```bash
cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python - docs/plans/2026-09-28-foms-language-migration-assessment-report.md <<'EOF'
import re, io, os, sys
doc = io.open(sys.argv[1], encoding="utf-8").read()
bad, matched = [], 0
for m in re.finditer(r"`([A-Za-z0-9_./\-]+\.(?:py|js|html|css|md|toml|yml|yaml|json|sh|ini|txt|ps1)):(\d+)(?:-(\d+))?", doc):
    matched += 1
    path, line = m.group(1), int(m.group(3) or m.group(2))
    if not os.path.exists(path):
        bad.append((path, line, "없음")); continue
    n = sum(1 for _ in io.open(path, encoding="utf-8", errors="ignore"))
    if line > n:
        bad.append((path, line, f"줄 수 {n}"))
print("MATCHED", matched)
print("ANCHOR_BAD", len(bad)); [print(" ", b) for b in bad]
print("HANJA", len(re.findall(r"[\u4e00-\u9fff]", doc)))
EOF
```
