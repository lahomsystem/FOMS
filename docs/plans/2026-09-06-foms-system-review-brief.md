# FOMS 시스템 전체 개발 검토 — 멀티 에이전트 브리프 (2026-09-06)

> 이 파일은 워크플로 에이전트(CEO·차원 워커·통합자·리뷰어·판정)에게 건네는 **유일한 컨텍스트 원본**이다.
> 세션 히스토리는 붙이지 않는다. 경로는 저장소 루트 `C:/DEV/FOMS` 기준 상대 경로다.

## 0. 환경·절대 규칙

- 저장소: `C:/DEV/FOMS` · 브랜치 `deploy` · HEAD `094682d57`. 모든 명령은 `cd C:/DEV/FOMS && ...` 로 시작한다.
- 셸: bash. 파이썬 출력 인코딩: `PYTHONIOENCODING=utf-8` 를 python/pytest 앞에 붙인다(cp949 가짜 red 방지).
- **읽기 전용 작업이다.** 워커·리뷰어는 저장소 파일을 편집하지 않는다. 통합자만 산출물 1개 파일을 새로 쓴다(§7 소유권).
- git: 상태 조회(`git log`·`git ls-files`·`git blame`)만 허용. `commit`·`stash`·`checkout`·`reset` 금지. 다른 창이 같은 워킹트리를 쓰고 있다.
- 패키지 설치 금지(`pip install`·`npm install`). 없는 도구는 "없음"으로 기록하고 대체 수단으로 확인한다.
- DB: 로컬 dev DB 뿐이다(운영 아님). postgres MCP(`localhost`)는 **읽기 전용 질의만**. 운영 수치(사용자 수·주문량·트래픽)는 접근 불가 — **추정 금지**, `확인 필요` 로 표기한다.
- 전체 pytest 실행 금지(CI 기준 14분+). 허용: `pytest --collect-only -q | tail -3`, 단일 파일 실행, `python -c "import app; print('APP_OK')"`.
- 시간 예산: 워커 1인당 탐색은 넓게, 그러나 결론은 **시스템 수준** 으로만. 파일 한두 개 수준의 사소한 발견은 `minor_parked` 로 격리한다.
- 출력 언어: 한글. **한자 금지**(고유명사·코드·API 이름 예외). 압축 지시가 있어도 한국어 낱말을 다른 언어로 바꾸지 않는다.
- **주장이 아니라 근거로 말한다.** 모든 관측은 `경로:행` 앵커 또는 실행한 명령의 결정적 출력 한 줄을 단다. 앵커가 없는 관측은 "가설" 로만 표기한다.
- 사용자 지시 원문 2건:
  1. "FOMS 총괄 개발자 persona로 개발상 어떤게 더 필요 한지, 어떤게 부족하진, 지금 개발 스택이 괜찮은지 체크, 리뷰 할 수 있는, 코딩 에이전트에 지시할 내용 프롬프트 작성 해"
  2. "**사소한 관점이 아닌 시스템 전체 관점에서 접근**"

## 1. 이 워크플로가 만드는 것

**산출물 = 코딩 에이전트에게 건넬 프롬프트 문서 1개**: `docs/plans/2026-09-06-foms-system-review-prompt.md`.

그 프롬프트는 "FOMS 총괄 개발자" 페르소나로 다음 3축을 **시스템 전체 관점**에서 판정하게 만든다.
- **더 필요한 것**: 앞으로 12~24개월 이 시스템이 굴러가려면 무엇을 갖춰야 하는가(구조·도구·운영·프로세스).
- **부족한 것**: 지금 결핍이 사고·속도 저하·비용으로 이미 새고 있는 곳은 어디인가.
- **스택 적합성**: Flask 모놀리스 + Jinja + Vanilla JS + PostgreSQL(JSONB) + Railway 조합이 이 제품·팀 규모에 맞는가. 유지/조건부 유지/교체 후보 판정과 근거.

프롬프트는 **사실 카드 + 사전 관측(가설)** 을 안에 품어, 받는 에이전트가 처음부터 탐색하지 않고 검증·확장부터 시작하게 한다. 사전 관측은 이 워크플로의 워커가 실제 저장소를 읽어 만든다.

"시스템 전체 관점" 의 뜻(판정 기준):
- 헤드라인은 **구조·흐름·거버넌스** 수준이어야 한다. 예: "의존성 거버넌스 부재(잠금 파일 없음·dev/prod 미분리·취약점 스캔 없음)" 는 시스템 수준이고, "pefile 이 불필요하다" 는 그 증거 하나일 뿐이다.
- 각 판정에 **왜 시스템 문제인지**(변경 증폭·사고 반복·단일 장애점·지식 집중·비용)와 **영향 시점**(지금/6개월/2년)을 붙인다.
- 제품·팀 맥락과 연결한다: 가구 주문 ERP, 워크플로 9단계, 현장(태블릿·iOS) 사용, 외부 채널(네이버·카카오·채널톡) 통합, **사람 개발자 1명 + AI 에이전트** 가 3개월에 2,765 커밋을 내는 속도.

## 2. 시스템 사실 카드 (총괄이 잰 것 — 다시 재지 말고 인용한다)

### 2.1 제품·팀
- FOMS = 가구 주문 관리 ERP. 단계: RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED (`CLAUDE.md` 프로젝트 개요).
- 팀 권한 축: SALES·CS·ACCOUNTING·CONSTRUCTION·DRAWING 등(`foms/services/erp_permissions.py`, `docs/AI_STATUS.md` 2026-09-03 회계팀 항목).
- 커밋 속도: 2026-06-01 이후 2,765건(2026-08-01 이후 1,473건). 작성자 nathan 2,653 · lahomsystem 107 · bot 7. 마지막 커밋 2026-09-05.
- 추적 파일 3,425개.

### 2.2 런타임 스택
- Flask 2.3.3 · Werkzeug <3 · Jinja2 3.1.2 · SQLAlchemy 2.0.23 · Flask-SQLAlchemy 3.1.1 · Alembic 1.16.1 · psycopg2-binary 2.9.9 (`requirements.txt`).
- 실시간: Flask-SocketIO + gevent + psycogreen 몽키패치(`app.py:1-17`), Redis MQ(`Procfile:2-3`).
- 서버: gunicorn `-k gevent -w 2 --timeout 120`(`Procfile:3`). `waitress` 도 같이 핀돼 있다.
- 큐: RQ worker(`railway-worker.toml`, `start.sh`). 워커 컨테이너 안에서 백그라운드 서브셸(`&`) 루프 4개(알림 에스컬레이션·네이버 수집·자동 발송·정산 동기화)가 env 플래그로 켜진다(`start.sh:20-60`). 감독 프로세스 없음.
- 저장: PostgreSQL(JSONB `structured_data` 중심, `CLAUDE.md` 코딩 규칙), Cloudflare R2 Presigned PUT(`docs/AI_STATUS.md` 아키텍처 요약), boto3.
- 관측: Sentry(`foms/platform/sentry_setup.py`, `SENTRY_DSN` 없으면 import 안 함), 로깅(`foms/platform/logging_setup.py`), RUM(`foms/api/foms_rum.py`·`foms/services/rum_aggregate.py`·`.github/workflows/rum-daily.yml`), `foms/api/health.py`.
- 외부 통합: 네이버 커머스(`foms/services/integrations/naver_commerce/`, 워커 단일 출구 — `start.sh` 주석 "호출 IP 한도 3"), 카카오 알림톡(solapi), 채널톡, 지오코딩, Web Push(pywebpush), Google GenAI(FOMS Brain).
- 기타 라이브러리: Flask-Limiter+redis, Flask-Compress, whitenoise, holidays, RapidFuzz, folium, Pillow 10.1.0.

### 2.3 파이썬·의존성 위생(사실)
- 파이썬 버전 표기 불일치: `.python-version` = 3.11.9 / `Dockerfile:3` = `python:3.12-slim` / `.github/workflows/ci.yml:48` = 3.12 / 로컬 3.12.10.
- `requirements.txt` 139줄. 런타임과 무관해 보이는 항목 다수: fastapi 0.109.0 · starlette · uvicorn · bottle · cleo · dulwich · keyring · pefile · altgraph · pythonnet · clr_loader · virtualenv · build · installer · pbs-installer · findpython · trove-classifiers · pkginfo · tomlkit · shellingham · crashtest · pywin32-ctypes · python-jose · passlib. `foms/`·`app.py` 에서 `jose`/`passlib` import 0건.
- `pyproject.toml`·잠금 파일(pip-tools/uv/poetry) 없음. dev/prod 의존성 분리 없음. `.github/dependabot.yml` 없음. `pytest-cov`/coverage 설정 없음.
- 린트·타입 도구 설정 파일 0개(ruff/flake8/mypy/pyright/eslint/prettier/pre-commit 전부 없음). CI 워크플로에 린트 잡 없음. `scripts/ops/pre_push_smoke.ps1:200-206` 의 "lint" 는 디자인 SSOT 린트(`tools/design/ssot_lint.py`) 뿐.
- `app.py:24-37` 이 Werkzeug 비공개 함수 `_hash_internal` 을 파이썬 3.12 호환용으로 몽키패치한다. `app.py:73-75` WSGI import 시 `run_auto_init(app)` (DB 자동 초기화) 실행.

### 2.4 코드 규모·구조(사실)
| 트리 | 파일 | 줄 |
|---|---|---|
| `foms/` (api 85 · services 311 · web 36 · platform 9 · persistence 10 py) | 452 | 142,235 |
| `templates/` | 278 | 57,601 |
| `static/` | 289 | 130,529 |
| `tests/` (test_*.py 671개) | 753 | 208,694 |
| `tools/` | 114 | 21,676 |
| `scripts/` | 44 | 6,735 |
| `migrations/` | 95 | 7,732 |
| `models.py` (루트, 클래스 77개) | 1 | 3,963 |
| `app.py` | 1 | 79 |

- 가장 큰 파일: `foms/web/admin/naver_ingest.py` 5,999 · `foms/services/integrations/naver_commerce/fulfillment.py` 2,513 · `foms/api/erp_orders_structured.py` 2,377 · `foms/api/share.py` 1,621 · `foms/api/cs/as_orders.py` 1,580 · `static/js/orders/erp-order-shared.js` 6,085 · `static/js/drawing/wizard.js` 4,271 · `static/js/wdcalculator/estimate-lifecycle.js` 3,657 · `static/js/cs/as-dashboard.js` 3,263 · `static/js/admin/naver-workbench.js` 3,088 · `templates/measurement/map_view.html` 3,079 · `templates/drawing/partials/workbench_detail_body.html` 2,971.
- 루트에 `models.py`·`db.py`·`wdcalculator_db.py`(별도 엔진, `WD_CALCULATOR_DATABASE_URL` 선택 — `wdcalculator_db.py:44`)·`wdcalculator_models.py` 가 `foms/` 밖에 있다.
- 격리(quarantine) 트리가 저장소 안에 추적된다: `Add In Program/` 98파일(React/TS `FOMSBrainDesigner`·`WDPlanner`), `SCheduler/` 6파일. `foms/README.md` 는 이 트리에서 runtime import 금지라고만 적는다. `data/` 12개 JSON 은 정책·설정 데이터(`data/erp_policy.json` 등).
- 아키텍처 정본: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`(703줄). 블루프린트 등록 순서 동결(`foms/platform/blueprints.py`). Step 8 패키징(`src/foms`) 보류(`docs/AI_STATUS.md` 아키텍처 요약). 대형 파일 분해는 "future batch" 로 보류.
- 문서 드리프트: `CLAUDE.md` 디렉토리 구조 절은 `apps/api/`·`services/`·`models.py` 를 말하지만 루트에 `apps/` 디렉토리가 없고 실제 정본은 `foms/api`·`foms/services` 다. `foms/README.md` 도 "레거시 등록 경로는 `apps/`" 라고 적는다.
- 템플릿: `style="` 687곳, 인라인 `<script>` 를 가진 템플릿 43개 — `CLAUDE.md` 는 "인라인 스타일 금지" 를 규칙으로 둔다.
- 자산 캐시: 서비스워커 `static/sw.js`, 정적 자산은 `?v=` 핀을 사람이 올린다(브리프 전례 `docs/plans/2026-09-03-settlement-followup-brief.md` 의 "핀" 항목·계약 테스트가 핀 값을 못 박음).

### 2.5 테스트·CI(사실)
- 워크플로 7개(`.github/workflows/`): `ci.yml`(push main/deploy + PR, test 잡 timeout 25분, 본 레인 `DATABASE_URL=sqlite:///:memory:` + `-n auto --dist loadfile`, 문서 전용 서브셋 22파일, Redis 레인, UI 구조 레인 15파일), `harness-ci.yml`(훅 compileall + `tests/harness` + `verify_result.py`), `postgres-lane.yml`, `perf-gate.yml`(deploy push 만), `rum-daily.yml`(cron), `visual-baseline-linux.yml`(수동), `coding-research-center-weekly.yml`(cron).
- CI 시간의 진범은 테스트당 고정세(PBKDF2 60만 회 = 839초의 73%) — `docs/harness/policy/DECISIONS.md` 2026-08-26 항목.
- 테스트 분류 정본 `tests/README.md`(계약 4계층: runtime anchor / chunk / domain / harness). `tests/security/` 는 `__init__.py` 뿐. `pytest.ini` 는 2026-08-26 에 처음 생김(그 전엔 설정 파일 0개).
- 계약 테스트 관례: 템플릿·JS·CSS 를 문자열/정규식으로 못 박는다(예: `tests/domains/test_settlement_dashboard_render.py` 핀·인라인 style·목업 잔재 검사). 문서를 읽는 테스트는 `ci.yml` 문서 서브셋 등재 의무(`tests/domains/test_docs_facing_registry.py`).
- 알려진 함정(메모리 정본, 재확인 대상): SQLite 본 레인은 FK 미강제라 없는 FK id 가 CI(PG 레인)에서만 터진다 · 로컬 dev DB alembic 체인 drift · 정적 JS 변경 시 `?v` 범프 필수(SW staticCacheFirst).

### 2.6 배포·운영(사실)
- Railway: Web 복제 2 · Worker 1(`docs/AI_STATUS.md` 스택 절). 브랜치 `deploy`(스테이징) → `production`(운영, PR cherry-pick 승격 — `AGENTS.md` 브랜치·푸시 권한).
- `railway.toml`: `startCommand = "sh start.sh"`, `preDeployCommand = "sh predeploy.sh"`(마이그레이션 배포당 1회). healthcheck 는 toml 에 없고 대시보드에서 web 에만 설정. cron 서비스 toml 3개(`railway-cron.toml`·`railway-cron-receipt-purge.toml`·`railway-domain-sidefx.toml`).
- `Dockerfile`: `python:3.12-slim`, pip 설치 5회 재시도 루프, 런타임 매니페스트 4종을 `docs/harness/*.json` 에서 explicit COPY(문서 디렉토리가 런타임 의존성).
- 운영 함정(메모리 정본): 워커 재배포가 큐를 붙잡는다 · Redis 장애 시 레이트리미터 fail-open · Railway 백업 보존 6일 · 프래그먼트 간헐 2~9초는 한국↔싱가포르 경로 · 정산 동기화 실행 행이 재배포에 잘리면 RUNNING 영구 잔류.
- DR·사고 문서: `docs/guides/DISASTER_RECOVERY.md`, `DATA_INCIDENT_RECOVERY.md`, `docs/incidents/` 5건, `docs/runbooks/` 8건. 환경변수 정본 `docs/guides/RAILWAY_ENV_VARS.md` 는 31줄(표 행 0) — `start.sh` 한 파일이 참조하는 `FOMS_*` 플래그만 12개 안팎.

### 2.7 개발 시스템(하네스·문서)
- 정책 SSOT `AGENTS.md`(Cursor·Claude·Codex 공통) + `CLAUDE.md` + `.cursor/rules/` 5개 + `.github/copilot-instructions.md`.
- Claude 훅 10개(`.claude/hooks/`: SessionStart·UserPromptSubmit ctx_gate·PreCompact·PreToolUse guard_shell·PostToolUse track_edits/post_bash·Stop session_stop/quality_check). `tools/harness/` 검증·승격 헬퍼. 스킬 5종(`.claude/skills/`).
- `docs/harness/` 인벤토리·매니페스트 JSON 20개 안팎(쓰기 가드·감사 커버리지·fail-open·비밀 리터럴·XSS 싱크 등) — 일부는 런타임이 읽는다(§2.6 Dockerfile).
- 문서 수: `docs/plans` 441 · `docs/specs` 85 · `docs/evolution` 36 · `docs/guides` 27 · `docs/design` 13 · `docs/context` 12 · `docs/runbooks` 8 · `docs/incidents` 5. `docs/AI_STATUS.md` 상단 40줄 계약 + `docs/AI_CHANGELOG.md`.

## 3. 총괄 1차 관측 (가설 — 워커가 확인·반박·확장한다. 결론 아님)

- H1 **의존성 거버넌스 부재**: 잠금 파일·dev/prod 분리·취약점 스캔·자동 업데이트 전무 + 파이썬 버전 표기 3갈래 + 런타임 무관 패키지 20여 개. (D1)
- H2 **품질 도구 층 공백**: 린트·타입·커버리지 0, 대신 208k 줄 계약 테스트가 그 역할을 문자열 매칭으로 대신한다 — 변경 증폭(핀·계약 갱신) 비용과 보호 효과의 균형이 불명. (D4)
- H3 **모듈러 모놀리스 경계가 절반**: `foms/` 네임스페이스는 잡혔지만 `models.py` 77클래스 단일 파일·루트 DB 모듈 2벌·6k 줄 파일들·격리 트리 추적이 남았다. (D2)
- H4 **JSONB 중심 데이터 모델의 장기 비용**: `structured_data` 가 핵심 도메인을 담아 인덱스·마이그레이션·리포팅이 서비스 코드에 의존한다(hot path ilike 금지 규칙이 생긴 배경). (D3)
- H5 **프론트 자산 파이프라인 부재**: 130k 줄 JS 를 번들러·린트 없이 `?v=` 수동 핀 + 계약 테스트로 관리. 셸 3벌(ERP·모바일 v2·v3) 표면 확산. (D5)
- H6 **보안 검증 표면이 인벤토리 중심**: 가드·허용목록 JSON 은 많으나 `tests/security` 비어 있음, 의존성 CVE 스캔 없음, 레이트리미터 fail-open 정책, 개인정보(전화·주소) 보존·마스킹 정책 문서 여부 불명. (D6)
- H7 **운영 단일 장애점**: 워커 1개가 큐 + 백그라운드 루프 4개를 감독 없이 돌린다, 단일 리전, 백업 6일, 알림/지표 기반 경보 여부 불명. (D7)
- H8 **개발 시스템의 무게**: 사람 1명 + 에이전트 구조에서 하네스(훅 10·규칙 4벌·인벤토리 20)·문서(plans 441)·AI_STATUS 계약이 속도를 내는지 비용인지 — 두 번째 사람이 들어올 때의 온보딩 경로 부재. `CLAUDE.md` 경로 드리프트가 그 증상. (D8)

## 4. 검토 차원(초안 — CEO 가 확정·보강한다. 이름은 고정, 워커가 같은 키를 쓴다)

각 차원은 **시스템 수준 핵심 질문 → 반드시 볼 앵커 → 허용 명령** 순이다. 워커는 핵심 질문에 답하는 형태로만 결론을 낸다.

| 키 | 차원 | 시스템 수준 핵심 질문 | 반드시 볼 앵커 | 허용 명령 예 |
|---|---|---|---|---|
| D1 | 스택·의존성 적합성 | 이 스택이 24개월 뒤에도 유지 가능한가(버전·EOL·업그레이드 경로·거버넌스)? Flask 3/Werkzeug 3/SQLAlchemy 최신/파이썬 3.13 으로 가는 길에 무엇이 막는가? gevent+SocketIO+RQ 조합은 이 규모에 맞는가? | `requirements.txt`, `Dockerfile`, `.python-version`, `app.py`, `Procfile`, `foms/platform/*.py` | `pip list --outdated` (60초 제한, 실패 시 "없음"), `grep -rn "import" foms \| ...` 로 실제 사용 패키지 대조 |
| D2 | 아키텍처·코드 구조 | 경계(web/api/services/platform/persistence)가 실제로 지켜지는가? 변경 1건이 몇 파일을 건드리게 만드는 구조인가(핀·계약·중복)? 거대 파일·루트 모듈·격리 트리·두 DB 엔진이 시스템에 주는 비용은? 외부 통합(네이버·카카오·채널톡)이 어댑터로 격리돼 있는가? | `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`, `foms/platform/blueprints.py`, `foms/README.md`, `models.py`, `db.py`, `wdcalculator_db.py`, `foms/services/integrations/`, `foms/web/admin/naver_ingest.py` | import 그래프 표본(`grep -rn "^from foms\.\|^import " foms/web \| head`), 계층 역방향 import 탐지 |
| D3 | 데이터·마이그레이션 | JSONB 중심 모델이 조회·정합성·리포팅·마이그레이션에 주는 장기 비용은? 스키마 진화가 안전한가(alembic 체인·downgrade·drift)? 백업/복구 RPO·RTO 가 사업 요구에 맞는가? 감사·이벤트 이력이 복구 가능한 수준인가? | `models.py`, `migrations/versions/`, `foms/persistence/`, `foms/services/db_indexes.py`, `docs/guides/DISASTER_RECOVERY.md`, `docs/guides/DATA_INCIDENT_RECOVERY.md` | `PYTHONIOENCODING=utf-8 python -m alembic heads`(60초 제한), `grep -c "def downgrade" migrations/versions/*.py`, postgres MCP 읽기(`analyze_db_health` 는 로컬 DB 임을 명시) |
| D4 | 테스트·CI·품질 시스템 | 208k 줄 테스트가 무엇을 보호하고 무엇을 못 보는가(보안·성능·통합)? 문자열 계약 테스트의 변경 증폭 비용은? SQLite 본 레인/PG 레인 이중 구조의 사각은? CI 14분+ 은 이 커밋 속도에 병목인가? 린트·타입·커버리지 부재가 실제 회귀로 새는가(`docs/incidents`, `docs/AI_CHANGELOG.md` 에서 원인 유형 세기)? | `.github/workflows/*.yml`, `tests/README.md`, `tests/conftest.py`, `pytest.ini`, `scripts/ops/pre_push_smoke.ps1`, `tests/performance/test_perf_regression_guard.py`, `docs/incidents/` | `PYTHONIOENCODING=utf-8 python -m pytest --collect-only -q -p no:playwright \| tail -3`, `grep -rl "assert .* in .*read_text\|re.search" tests \| wc -l` |
| D5 | 프론트엔드·자산 파이프라인 | 번들러·린트 없는 130k 줄 Vanilla JS 가 어디까지 버티는가? 셸 3벌(ERP 데스크톱·모바일 v2·v3)과 프래그먼트 스왑이 만드는 표면 확산은? `?v=` 수동 핀 + SW 캐시 구조의 변경 증폭·사고 이력은? 인라인 스타일 687곳은 규칙 실패인가 규칙 과잉인가? 접근성·오프라인 전략은? | `static/js/orders/erp-order-shared.js`, `static/sw.js`, `templates/partials/shared/layout_head.html`, 도메인별 `templates/*/layout.html`(9벌), `static/css/foundation/erp-pro.css`, `foms/api/fragment.py`, `foms/api/foms_offline.py` | `node --check` 표본, `grep -rn 'style="' templates \| wc -l`, `grep -rn "?v=" templates \| wc -l` |
| D6 | 보안·권한·개인정보 | 인증·세션·권한 모델이 팀 확장에 견디는가? 실패 시 열리는(fail-open) 정책들이 어디에 있고 사업상 감당 가능한가? 의존성 취약점·비밀 관리·업로드·공유 토큰·XSS 싱크의 체계적 방어가 있는가? 고객 개인정보(전화·주소) 보존·마스킹·접근 기록이 법적 요구(개인정보보호법)에 맞는가? | `foms/services/security/`, `foms/services/rate_limit.py`, `foms/platform/request_limits.py`, `foms/api/share.py`, `foms/services/storage.py`, `docs/harness/foms_untrusted_dom_sinks.json`, `foms_secret_literal_allowlist.json`, `foms_api_error_leak_inventory.json`, `models.py`(AccessLog·SecurityLog) | `grep -rn "fail-open\|fail_open\|failopen" foms \| wc -l`, `git ls-files \| grep -i "\.env\|secret\|key"` |
| D7 | 운영·배포·관측·회복력 | 단일 리전·워커 1개·감독 없는 루프 4개·백업 6일이 사업 연속성에 맞는가? 배포(deploy→production cherry-pick)와 롤백이 안전한가? 장애를 사람이 알기까지 얼마나 걸리는가(경보·지표·헬스체크)? 외부 API 한도·토큰 만료·큐 정체를 시스템이 스스로 회복하는가? 비용 구조는? | `start.sh`, `predeploy.sh`, `railway*.toml`, `Dockerfile`, `foms/platform/sentry_setup.py`, `foms/api/health.py`, `foms/services/jobs/`, `foms/services/sidefx_worker.py`, `tools/ops/`, `docs/guides/DEPLOYMENT_GUIDE.md`, `docs/runbooks/` | `grep -n "&$" start.sh`, `ls docs/runbooks docs/incidents` |
| D8 | 개발 시스템(DX·하네스·문서·프로세스) | 사람 1명 + 에이전트 구조가 만든 하네스·문서·계약이 속도를 내는가, 비용인가? 두 번째 개발자가 오면 무엇부터 막히는가? 정책 SSOT 4벌(AGENTS/CLAUDE/cursor/copilot)과 코드 드리프트는? 441개 plans 의 지식이 다시 찾아지는가? 6개월 ablation 주기가 실제로 돌았는가? | `AGENTS.md`, `CLAUDE.md`, `.claude/hooks/`, `.claude/settings.json`, `tools/harness/`, `docs/harness/policy/DECISIONS.md`, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/guides/LONG_TASK_PROMPTS.md` | `ls docs/plans \| wc -l`, `grep -n "apps/" CLAUDE.md foms/README.md`, `python tools/harness/verify_result.py --json`(가능하면) |

## 5. 워커 출력 스키마 (JSON — StructuredOutput 으로 반환)

```json
{
  "dimension": "D1",
  "title": "스택·의존성 적합성",
  "verdict": {"fit": "적합|조건부|부적합", "one_line": "한 문장 판정"},
  "system_risks": [
    {"title": "…", "why_systemic": "변경 증폭/사고 반복/단일 장애점/지식 집중/비용 중 무엇이 왜",
     "severity": "높음|중간|낮음", "horizon": "지금|6개월|2년",
     "evidence": [{"claim": "…", "anchor": "경로:행 또는 명령", "verified_by": "읽음|실행 출력: …"}]}
  ],
  "lacking": [ { "같은 모양": "지금 결핍이 새고 있는 곳" } ],
  "needed": [
    {"title": "…", "what": "무엇을 갖출지", "why": "시스템 수준 이유", "first_step": "첫 한 걸음(작게)", "verify": "됐다는 것을 어떻게 확인"}
  ],
  "stack_questions": ["받는 에이전트가 반드시 다시 확인할 질문 — 운영 데이터가 있어야 답할 것 포함"],
  "minor_parked": ["사소한 발견은 여기로 격리(헤드라인 금지)"],
  "commands_run": [{"cmd": "…", "decisive_line": "…"}]
}
```

규칙: `system_risks`·`lacking` 은 각 3~6개, `needed` 는 3~5개. 앵커 없는 항목은 `verified_by` 에 `"가설"` 이라고 적는다. 총괄 1차 관측(§3)을 반박해도 좋다 — 반박도 앵커를 단다.

## 6. 산출물 프롬프트 계약 (통합자가 지킨다 — 섹션 이름 고정)

파일: `docs/plans/2026-09-06-foms-system-review-prompt.md`. 한글, 한자 없음, 마크다운. 받는 에이전트가 **이 파일만 읽고** 실행할 수 있어야 한다.

0. **이 문서를 받는 에이전트에게** — 무엇을 만들라는 것인지 한 문단, 실행 방식(CEO 1 + 워커 8 병렬 + 리뷰 2 + 판정), 결과물 경로.
1. **페르소나·임무** — FOMS 총괄 개발자. 판정 3축(더 필요한 것/부족한 것/스택 적합성). "시스템 전체 관점" 정의(§1 판정 기준 그대로).
2. **시스템 사실 카드** — §2 를 압축 인용(숫자·앵커 유지).
3. **절대 규칙** — 읽기 전용·앵커 의무·사소한 발견 격리·한글·한자 금지·설치 금지·git 변경 금지·production 금지·운영 수치 추정 금지·문제 수정 정책(근본 원인)·전체 pytest 금지.
4. **검토 차원 8개** — 차원마다: 핵심 질문(시스템 수준), 반드시 볼 앵커, 확인 명령, 판정 기준(적합/조건부/부적합 의 뜻).
5. **사전 관측(가설·검증 필요)** — 워커 8명의 `system_risks`·`lacking`·`needed` 를 차원별로 정리. 각 항목에 `[확인됨: 앵커]` 또는 `[가설]` 표기. `minor_parked` 는 맨 끝 부록으로.
6. **산출물 계약** — 받는 에이전트가 낼 보고서 구조: ① 시스템 건강 지도(차원 × 판정 표) ② 상위 구조 리스크 5~8(영향 시점·근거) ③ 부족한 것 ④ 더 필요한 것(로드맵: 지금/이번 분기/12~24개월, 각각 첫 걸음·검증) ⑤ 스택 판정(유지/조건부/교체 후보 + 근거 + 교체 시 비용) ⑥ 열린 질문(운영 데이터·사용자 결정 필요) ⑦ 부록(사소한 것).
7. **실행 계획(멀티 에이전트)** — CEO 설계 → 워커 병렬(차원별) → 통합 → 리뷰 2판정(스펙/품질 분리, 편집 금지) → CEO 판정(ship/fix/block, fix 1회). 워커 출력 스키마(§5)와 리뷰 기준(§8) 포함. Workflow 도구 없이도 Agent 병렬 호출로 같은 구조를 돌릴 수 있게 적는다.
8. **완료 기준·검증 명령** — 보고서 파일 존재, 섹션 7개 존재, 한자 0(`[\u4e00-\u9fff]` 검색), 앵커 실존 검사(아래 스니펫), 헤드라인에 사소한 항목 0(리뷰어 판정).

앵커 실존 검사 스니펫(통합자가 프롬프트 §8 에 그대로 넣는다):
```bash
cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python - <<'EOF'
import re, io, os, sys
doc = io.open(sys.argv[1] if len(sys.argv) > 1 else "docs/plans/2026-09-06-foms-system-review-prompt.md", encoding="utf-8").read()
bad = []
for m in re.finditer(r"`([A-Za-z0-9_./\-]+\.(?:py|js|html|css|md|toml|yml|yaml|json|sh|ini|txt|ps1)):(\d+)", doc):
    path, line = m.group(1), int(m.group(2))
    if not os.path.exists(path):
        bad.append((path, line, "없음")); continue
    n = sum(1 for _ in io.open(path, encoding="utf-8", errors="ignore"))
    if line > n:
        bad.append((path, line, f"줄 수 {n}"))
print("ANCHOR_BAD", len(bad)); [print(" ", b) for b in bad]
print("HANJA", len(re.findall(r"[\u4e00-\u9fff]", doc)))
EOF
```
통과 기준: `ANCHOR_BAD 0` · `HANJA 0`.

## 7. 파일 소유권 (병렬 충돌 방지 — 절대 규칙)

| 역할 | 쓰기 허용 | 금지 |
|---|---|---|
| CEO 설계·판정 | 없음(구조화 출력만) | 저장소 파일 전부 |
| 차원 워커 D1~D8 | 없음(구조화 출력만) | 저장소 파일 전부, 패키지 설치, git 변경 |
| 통합자 | `docs/plans/2026-09-06-foms-system-review-prompt.md` 신규 1개 | 그 외 전부 |
| 리뷰어 2 | 없음(구조화 출력만) | 저장소 파일 전부 |
| 총괄(세션) | 이 브리프, 원장 `docs/plans/2026-09-06-foms-system-review-ledger.md`, 커밋 | — |

## 8. 리뷰 기준 (2판정 — 리뷰어는 편집하지 않는다)

**스펙 리뷰어(사용자 요청 충족)**
- 판정 3축(더 필요/부족/스택 적합)이 각각 프롬프트의 임무·차원·산출물 계약에 모두 살아 있는가.
- "시스템 전체 관점" 이 규칙·판정 기준·사전 관측 헤드라인에 실제로 적용됐는가(사소한 항목이 헤드라인에 있으면 실패).
- FOMS 총괄 개발자 페르소나가 제품·팀 맥락(§2.1)과 연결돼 있는가.
- 받는 에이전트가 이 파일만으로 CEO+워커 병렬 실행을 재현할 수 있는가(스키마·차원·검증 명령 포함).
- 프로젝트 절대 규칙과 충돌 없음: production push 금지·근본 원인 수정·한글·한자 금지·인라인 스타일 금지 등을 프롬프트가 어기라고 시키지 않는가.

**품질 리뷰어(정확성·실행 가능성)**
- 앵커 표본 15개 이상을 직접 열어 실존·내용 일치 확인(§6 스니펫 실행 + 내용 대조).
- 숫자는 §2 사실 카드와 일치하는가(임의 수치 없음).
- 명령이 bash + Windows 환경에서 실제로 도는가(표본 5개 실행).
- 가설과 확인됨 표기가 섞이지 않았는가.
- 한자 0, 문서 길이가 받는 에이전트의 컨텍스트에 무리하지 않는가(목표 600줄 이하, 부록 포함).

판정: `ship` / `fix`(구체 수정 목록) / `block`(사유). `fix` 는 통합자가 1회 반영 후 CEO 재판정.
