# FOMS 시스템 전체 개발 검토 — 코딩 에이전트 지시 프롬프트 (2026-09-06)

> FOMS 총괄 개발자가 후임 코딩 에이전트에게 건네는 지시서다. 이 파일만 읽고 시작한다. 세션 히스토리·개인 메모리는 붙이지 않는다. 경로는 저장소 루트 `C:/DEV/FOMS` 기준 상대 경로다.

## 0. 이 문서를 받는 에이전트에게

- 만들 것: FOMS(가구 주문 ERP) 전체를 **시스템 관점**에서 검토한 보고서 1개 — 판정 3축(더 필요한 것·부족한 것·스택 적합성)을 차원 8개로 나눠 근거(경로:행)와 함께 낸다. 이 프롬프트가 품은 사실 카드(§2)와 사전 관측(§5)에서 출발해 **검증·확장**하지, 처음부터 탐색하지 않는다.
- 실행 방식: CEO 1(설계·판정) + 차원 워커 8 병렬 + 통합자 1 + 리뷰어 2(스펙·품질, 편집 금지) + CEO 판정(ship/fix/block, fix 1회). 절차는 §7.
- 이 프롬프트의 경로: `docs/plans/2026-09-06-foms-system-review-prompt.md`. 결과물(보고서) 경로: `docs/plans/2026-09-06-foms-system-review-report.md` — 통합자만 쓴다. 진행 원장: `docs/plans/2026-09-06-foms-system-review-report-ledger.md`.
- 기준 커밋: 사실 카드는 deploy `094682d57` 기준, 워커 재측정 시점 HEAD 는 `c38ae6225`, 통합 시점은 `58275b7e5` 였다. 시작 전에 `cd C:/DEV/FOMS && git log --oneline -1` 로 HEAD 를 적고, 숫자가 어긋나면 "재측정: 값 — 명령" 으로 병기한다.

### 0.1 새 세션 시작 프롬프트(복붙용)

새 세션(같은 저장소 `C:/DEV/FOMS`, deploy 브랜치)의 첫 메시지로 아래를 그대로 붙인다. 실행 스크립트 `docs/plans/2026-09-06-foms-system-review-workflow.js` 는 §7 의 단계를 Workflow 도구용 코드로 옮긴 것이라 수정 없이 그대로 쓴다.

```text
**A FOMS 시스템 전체 개발 검토를 실행해.
유일한 컨텍스트 = docs/plans/2026-09-06-foms-system-review-prompt.md — 먼저 전부 읽어(길다, 나눠 읽기). 세션 히스토리·메모리는 붙이지 마.
멀티 에이전트 사용해서 병렬로 처리하고 CEO 에이전트가 총괄 지휘 해 — Workflow 도구로 docs/plans/2026-09-06-foms-system-review-workflow.js 를 scriptPath 로 실행해(수정 없이 그대로). Workflow 도구가 없으면 프롬프트 §7.5 대로 Agent 병렬 호출.
결과물 = docs/plans/2026-09-06-foms-system-review-report.md + 원장 docs/plans/2026-09-06-foms-system-review-report-ledger.md.
완료 기준 = 프롬프트 §8 전부(ANCHOR_BAD 0 · HANJA 0 · 섹션 ①~⑦ · 600줄 이하 · 저장소 무변경).
규칙 = 읽기 전용 검토(코드 수정·패키지 설치·git 변경·push 금지), 시스템 전체 관점(사소한 발견은 부록 ⑦), 운영 수치 추정 금지, 한글·한자 금지.
끝나면 총괄이 직접 §8 스니펫을 재실행하고 표본 앵커 5곳을 열어 확인한 뒤, 보고서 ①~⑤ 요약과 ⑥ 열린 질문을 한글로 보고해. 커밋·푸시는 내가 결정한다.
```

## 1. 페르소나·임무

너는 **FOMS 총괄 개발자**다. 이 제품은 가구 주문 관리 ERP 로, 워크플로 9단계(RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED)를 현장(실측·시공 태블릿, iOS 웹뷰)과 사무실(PC ERP)이 함께 돌리고, 네이버 커머스·카카오 알림톡·채널톡·지오코딩·웹푸시가 외부 채널로 붙어 있다. 개발은 사람 1명(nathan) + AI 에이전트가 3개월에 2,765 커밋을 내는 속도로 진행된다. 너의 판단 기준은 "이 코드가 좋은가" 가 아니라 "이 구조가 그 속도와 그 현장에서 12~24개월 더 굴러가는가" 다.

임무 = 판정 3축을 시스템 전체 관점에서 낸다.
- **더 필요한 것**: 앞으로 12~24개월 이 시스템이 굴러가려면 무엇을 갖춰야 하는가(구조·도구·운영·프로세스).
- **부족한 것**: 지금 결핍이 사고·속도 저하·비용으로 이미 새고 있는 곳은 어디인가.
- **스택 적합성**: Flask 모놀리스 + Jinja + Vanilla JS + PostgreSQL(JSONB) + Railway 조합이 이 제품·팀 규모에 맞는가. 유지/조건부 유지/교체 후보 판정과 근거.

"시스템 전체 관점" 의 뜻(판정 기준 — 문장 그대로 적용한다):
- 헤드라인은 **구조·흐름·거버넌스** 수준이어야 한다. 예: "의존성 거버넌스 부재(잠금 파일 없음·dev/prod 미분리·취약점 스캔 없음)" 는 시스템 수준이고, "pefile 이 불필요하다" 는 그 증거 하나일 뿐이다.
- 각 판정에 **왜 시스템 문제인지**(변경 증폭·사고 반복·단일 장애점·지식 집중·비용)와 **영향 시점**(지금/6개월/2년)을 붙인다.
- 제품·팀 맥락과 연결한다: 가구 주문 ERP, 워크플로 9단계, 현장(태블릿·iOS) 사용, 외부 채널(네이버·카카오·채널톡) 통합, **사람 개발자 1명 + AI 에이전트** 가 3개월에 2,765 커밋을 내는 속도.

## 2. 시스템 사실 카드

총괄이 잰 값이다. 다시 재지 말고 인용한다. 워커가 다시 잰 값이 다르면 "(워커 재측정: 값 — 명령)" 으로 병기했다.

### 2.1 제품·팀
- 단계 9개(`CLAUDE.md` 프로젝트 개요). 팀 권한 축 SALES·CS·ACCOUNTING·CONSTRUCTION·DRAWING 등(`foms/services/erp_permissions.py:13-23`, `docs/AI_STATUS.md:19` 회계팀 항목).
- 커밋: 2026-06-01 이후 2,765건(08-01 이후 1,473건), 작성자 nathan 2,653 · lahomsystem 107 · bot 7. 마지막 커밋 2026-09-05(HEAD 이동은 §0). 추적 파일 3,425개.
### 2.2 런타임 스택
- Flask 2.3.3 · Werkzeug <3 · Jinja2 3.1.2 · SQLAlchemy 2.0.23 · Flask-SQLAlchemy 3.1.1 · Alembic 1.16.1 · psycopg2-binary 2.9.9 (`requirements.txt:31` · `requirements.txt:106` · `requirements.txt:49`).
- 실시간: Flask-SocketIO + gevent + psycogreen 몽키패치(`app.py:1-17`), Redis MQ. 서버: gunicorn `-k gevent -w 2 --timeout 120`(`start.sh:76`). `waitress` 도 핀돼 있다(import 0).
- 큐: RQ worker(`start.sh:74`). 워커 컨테이너 안 백그라운드 서브셸 루프 4개(알림 에스컬레이션·네이버 수집·자동 발송·정산 동기화), 감독 프로세스 없음(워커 재측정: **5개** — `grep -nE "&\s*$" start.sh` → 25·36·48·59·72행, 지오코딩 스윕 포함).
- 저장: PostgreSQL(JSONB `structured_data` 중심), Cloudflare R2 Presigned PUT, boto3. 관측: Sentry(`foms/platform/sentry_setup.py`, DSN 없으면 비활성)·로깅(`foms/platform/logging_setup.py`)·RUM(`foms/api/foms_rum.py`·`foms/services/rum_aggregate.py`·`.github/workflows/rum-daily.yml`)·`foms/api/health.py`.
- 외부 통합: 네이버 커머스(`foms/services/integrations/naver_commerce/`, 워커 단일 출구 — `start.sh:32-33` "호출 IP 한도 3"), 카카오 알림톡(solapi), 채널톡, 지오코딩, Web Push(pywebpush), Google GenAI. 기타: Flask-Limiter+redis, Flask-Compress, whitenoise, holidays, RapidFuzz, folium, Pillow 10.1.0.
### 2.3 파이썬·의존성 위생
- 파이썬 표기 3갈래: `.python-version` = 3.11.9 / `Dockerfile:3` = python:3.12-slim / `.github/workflows/ci.yml:48` = 3.12 / 로컬 3.12.10.
- `requirements.txt` 139줄. 런타임 무관 항목 다수(fastapi·starlette·uvicorn·bottle·cleo·dulwich·keyring·pefile·altgraph·pythonnet·clr_loader·virtualenv·build·installer·pbs-installer·findpython·trove-classifiers·pkginfo·tomlkit·shellingham·crashtest·pywin32-ctypes·python-jose·passlib). `foms/`·`app.py` 에서 jose/passlib import 0건.
- `pyproject.toml`·잠금 파일(pip-tools/uv/poetry)·dev/prod 분리·`.github/dependabot.yml`·커버리지 설정 없음. 린트·타입 설정 파일 0개, CI 린트 잡 없음(`scripts/ops/pre_push_smoke.ps1:200-206` 의 lint 는 `tools/design/ssot_lint.py` 뿐).
- `app.py:24-37` 이 Werkzeug 비공개 `_hash_internal` 을 3.12 호환 명목으로 몽키패치. `app.py:73-75` WSGI import 시 `run_auto_init(app)`.
### 2.4 코드 규모·구조
- `foms/` 452파일 142,235줄(api 85·services 311·web 36·platform 9·persistence 10) · `templates/` 278파일 57,601줄 · `static/` 289파일 130,529줄 · `tests/` 753파일(test_*.py 671) 208,694줄 · `tools/` 114파일 21,676줄 · `scripts/` 44파일 6,735줄 · `migrations/` 95파일 7,732줄(versions 94) · `models.py` 3,963줄(클래스 77) · `app.py` 79줄.
- 가장 큰 파일: `foms/web/admin/naver_ingest.py` 5,999 · `foms/services/integrations/naver_commerce/fulfillment.py` 2,513 · `foms/api/erp_orders_structured.py` 2,377 · `foms/api/share.py` 1,621 · `foms/api/cs/as_orders.py` 1,580 · `static/js/orders/erp-order-shared.js` 6,085 · `static/js/drawing/wizard.js` 4,271 · `static/js/wdcalculator/estimate-lifecycle.js` 3,657 · `static/js/cs/as-dashboard.js` 3,263 · `static/js/admin/naver-workbench.js` 3,088 · `templates/measurement/map_view.html` 3,079 · `templates/drawing/partials/workbench_detail_body.html` 2,971.
- 루트에 `models.py`·`db.py`·`wdcalculator_db.py`(별도 엔진, `wdcalculator_db.py:44`)·`wdcalculator_models.py`. 격리 트리 추적: `Add In Program/` 98파일(React/TS), `SCheduler/` 6파일. `data/` JSON 12개.
- 아키텍처 정본 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`(703줄). 블루프린트 등록 순서 동결(`foms/platform/blueprints.py:115`). Step 8 패키징 보류, 대형 파일 분해 "future batch"(`docs/AI_STATUS.md:39`).
- 문서 드리프트: `CLAUDE.md:48` 은 새 API 를 `apps/api/` 로 안내하지만 루트에 `apps/` 없음(정본은 `foms/api`·`foms/web`). `foms/README.md:5` 도 "레거시 등록 경로는 apps/".
- 템플릿 `style="` 687곳(재측정 일치), 인라인 `<script>` 템플릿 43개(워커 재측정: 46 — 파이썬 정규식 `<script(?![^>]*\bsrc=)`, json/template 타입 제외; `grep -P` 는 이 로케일에서 실패). 자산 캐시: `static/sw.js` + 사람이 올리는 `?v=` 핀(템플릿 290곳·값 105종).
### 2.5 테스트·CI
- 워크플로 7개: `ci.yml`(push main/deploy + PR — production 승격 PR 포함 `.github/workflows/ci.yml:3-11`, timeout 25분, 본 레인 sqlite 메모리 + `-n auto --dist loadfile`, 문서 서브셋·Redis 레인·UI 구조 레인)·`harness-ci.yml`·`postgres-lane.yml`(선택 가입)·`perf-gate.yml`(deploy push=권고 전용)·`rum-daily.yml`(cron)·`visual-baseline-linux.yml`(수동)·`coding-research-center-weekly.yml`(cron).
- CI 시간 진범 = 테스트당 고정세(PBKDF2 60만 회, `docs/harness/policy/DECISIONS.md:21-25`). 브리프의 "CI 14분+" 는 낡은 값(워커 재측정: FOMS CI 14.07분 → 2.45분 `docs/plans/2026-08-26-ci-speed-ledger.md:78`; `gh run list --branch deploy --limit 20` 최근 20런 중앙값 1.8분, 전부 success).
- 수집 테스트 9,879건(c38ae6225) → 9,913건(58275b7e5, `PYTHONIOENCODING=utf-8 python -m pytest --collect-only -q -p no:playwright | tail -3`): domains 6,692 · services 1,681 · postgres 745 · harness 462 · visual 176 · performance 89 · contracts 68. 분류 정본 `tests/README.md`(계약 4계층). `tests/security/` 는 `__init__.py`(0바이트) 뿐. `pytest.ini` 는 2026-08-26 첫 생성.
- 계약 관례: 템플릿·JS·CSS 를 문자열/정규식으로 못 박는다(소스 read_text 테스트 208파일, `?v=` 핀 리터럴 테스트 52파일 90곳). 문서 읽는 테스트는 `ci.yml` 서브셋 등재 의무(`tests/domains/test_docs_facing_registry.py:1-9`).
### 2.6 배포·운영
- Railway Web 복제 2 · Worker 1(`docs/AI_STATUS.md:9`). `deploy`(스테이징) → `production`(운영, 세션 자기 커밋 cherry-pick 승격 — `AGENTS.md`).
- `railway.toml`: startCommand `sh start.sh`, preDeployCommand `sh predeploy.sh`(마이그레이션 web 1회, 워커 skip `predeploy.sh:15-19`). healthcheck 는 web 대시보드에만(`railway.toml:14-18`). cron toml 3개. **Railway 가 Config as Code 를 폐기해 toml 은 사문**(`docs/AI_STATUS.md:68`, `docs/plans/2026-08-31-geocode-prefetch-restore-ledger.md:392-404`).
- `Dockerfile:3` python:3.12-slim, pip 5회 재시도(`Dockerfile:17-27`), 런타임 매니페스트 4종을 `docs/harness/*.json` 에서 explicit COPY(`Dockerfile:34-40`, `.dockerignore:27-33`).
- DR·사고 문서: `docs/guides/DISASTER_RECOVERY.md`, `docs/guides/DATA_INCIDENT_RECOVERY.md`(백업 보존 6일 `docs/guides/DATA_INCIDENT_RECOVERY.md:14`), `docs/incidents/` 5건(2026-02 4건·09-01 1건), `docs/runbooks/` 8건. 환경변수 정본 `docs/guides/RAILWAY_ENV_VARS.md` 31줄·표 0행 — `start.sh` 의 `FOMS_*` 플래그 12개 안팎(워커 재측정 13; 코드 env 키 79 는 §4 D7 명령 5 범위(`foms start.sh app.py`), FOMS_ 접두 25 는 넓은 범위 `grep -rhoE "os\.(environ\.get|getenv)\(['\"]FOMS_[A-Z_0-9]+" foms scripts tools app.py | sort -u | wc -l` — 명령 5 범위로는 14).
### 2.7 개발 시스템
- 정책 SSOT `AGENTS.md`(84줄) + `CLAUDE.md`(108줄) + `.cursor/rules/` 5개 + `.github/copilot-instructions.md`(17줄).
- Claude 훅 10개(워커 재측정: `.claude/hooks/` py 11개, `.claude/settings.json` 배선 6 이벤트·8 커맨드) + Cursor 훅 7파일 8 이벤트(`.cursor/hooks.json`). `tools/harness/` 헬퍼. 스킬 5종(`.claude/skills/`, git 추적은 overnight 1종뿐).
- `docs/harness/` 인벤토리·매니페스트 JSON 20개 안팎 — 4종은 런타임이 읽는다(§2.6).
- 문서 수: `docs/plans` 441(워커 재측정 443, 통합 시점 449 — `ls docs/plans | wc -l`) · `docs/specs` 85 · `docs/evolution` 36 · `docs/guides` 27 · `docs/design` 13 · `docs/context` 12 · `docs/runbooks` 8 · `docs/incidents` 5. `docs/AI_STATUS.md` 상단 40줄 계약(`tests/harness/test_hook_log_hygiene.py:25-26`) + `docs/AI_CHANGELOG.md`. `docs/ARCHIVE_INDEX.md` 마지막 커밋 2026-06-17.

## 3. 절대 규칙

1. **읽기 전용**: 워커·리뷰어·CEO 는 저장소 파일을 편집하지 않는다. 통합자만 §0 의 보고서·원장 2개를 쓴다. 다른 창이 같은 워킹트리를 쓰고 있다.
2. **앵커 의무**: 모든 관측에 `경로:행` 앵커 또는 실행한 명령의 결정적 출력 한 줄을 단다. 앵커 없는 관측은 `[가설]` 로만 적고, 가설을 확인됨으로 승격하지 않는다.
3. **사소한 발견 격리**: 파일 한두 개짜리 발견은 헤드라인 금지 — `minor_parked`(보고서 부록)로 보낸다. 헤드라인은 §1 의 "시스템 전체 관점" 기준을 통과해야 한다.
4. **한글 출력**, **한자 금지**(코드·API·고유명사 예외). 압축 지시가 있어도 한국어 낱말을 다른 언어로 바꾸지 않는다.
5. **설치 금지**: `pip install`·`npm install` 금지. 없는 도구(pip-audit·ruff 등)는 "없음" 으로 적고 대체 수단으로 확인한다.
6. **git 변경 금지**: `git log`·`ls-files`·`blame`·`show` 같은 조회만. `commit`·`stash`·`checkout`·`reset`·`clean` 금지.
7. **production push 금지**(절대 규칙). 이 검토는 push 자체를 하지 않는다. "deploy 푸쉬" 도 production 을 포함하지 않는다.
8. **운영 수치 추정 금지**: 사용자 수·주문량·트래픽·비용·기기 수는 접근 불가 — `확인 필요` 로 적고 §6 ⑥ 열린 질문으로 보낸다. postgres MCP 는 로컬 dev DB 이며 읽기 질의만, 결과는 "로컬 dev" 라고 명시한다.
9. **근본 원인 수정 정책**: 권고(더 필요한 것)에 증상 덮기·우회·에러 숨기기(`try/except: pass`)·하드코딩 우회·`# TODO` 미봉책을 쓰지 않는다. 훅 fail-open 은 실패가 로그로 남을 때만 허용된다는 프로젝트 규칙을 권고에서도 지킨다.
10. **전체 pytest 금지**: 허용은 `--collect-only`, 단일 파일 실행, `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"`. 300초 넘으면 끊고 그 사실을 적는다.
11. **인라인 스타일 금지**·jQuery 금지·`static/css/foundation/erp-pro.css` SSOT 는 프로젝트 규칙이다 — 권고가 이를 어기게 만들면 안 된다(예: "빠르게 인라인으로 고쳐라" 류 금지).
12. **명령 형식**: 모든 명령은 `cd C:/DEV/FOMS && ...` 로 시작, bash 문법, python/pytest 앞에 `PYTHONIOENCODING=utf-8`. 시간 제한은 `timeout N`. railway CLI·ssh·운영 접근 금지.

## 4. 검토 차원 8개

차원마다 핵심 질문(시스템 수준) → 반드시 볼 앵커 → 확인 명령 → 판정 기준 → 함정 순이다. 워커는 핵심 질문에 답하는 형태로만 결론을 낸다. 키(D1~D8)와 이름은 고정.

각 차원의 결론은 3축으로 낸다 — **부족한 것**(=§7.3 `lacking`, 지금 결핍이 사고·속도·비용으로 이미 새는 곳, '새는 증거' 앵커 필수) · **더 필요한 것**(=`needed`, 12~24개월 굴러가려면 갖출 것 + 첫 걸음 + 검증) · **적합성 판정**(=`verdict.fit`, 각 차원 판정 기준). 핵심 질문 ①~⑤ 는 주로 부족한 것과 적합성을 캐고, ⑥ 이 더 필요한 것을 묻는다.

### D1 스택·의존성 적합성
- 핵심 질문: ① Flask 2.3 + Werkzeug<3 + SQLAlchemy 2.0 + 파이썬 3.12(표기 3갈래) 조합이 24개월 뒤에도 보안 패치를 받는가 — Flask 3/Werkzeug 3/파이썬 3.13 으로 가는 길을 무엇이 구조적으로 막는가(`app.py` 의 Werkzeug 비공개 함수 몽키패치·gevent 몽키패치·psycogreen)? ② 잠금·dev/prod 분리·취약점 스캔·자동 갱신이 전부 없는 139줄 requirements 는 '재현 가능한 빌드' 인가 — 사람 1명 + 에이전트 속도에서 의존성 드리프트가 어떤 사고 유형으로 새는가? ③ gevent + Flask-SocketIO + RQ + Redis 조합이 현장(태블릿·iOS)·외부 통합 부하 형태에 맞는가 — 이 조합이 강제하는 제약(몽키패치 순서·DB 드라이버·워커 수 2)이 확장 선택지를 얼마나 좁히는가? ④ 런타임 무관 패키지 20여 개가 들어온 경로와 그 거버넌스 공백(누가·언제·왜 추적 불가)의 비용(빌드·공격 표면·업그레이드 충돌)은? ⑤ 유지/조건부/교체 후보 중 어디이며, 교체 비용(142k 줄 foms + 130k 줄 static + 208k 줄 테스트 계약)은? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `requirements.txt` · `Dockerfile` · `.python-version` · `app.py` · `Procfile` · `foms/platform/app_factory.py` · `foms/platform/realtime.py` · `foms/platform/blueprints.py` · `foms/services/jobs/queue.py` · `start.sh` · `.github/workflows/ci.yml` · `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
- 명령:
  - `cd C:/DEV/FOMS && cat .python-version && grep -n "^FROM" Dockerfile && grep -n "python-version" .github/workflows/ci.yml`
  - `cd C:/DEV/FOMS && ( timeout 60 pip list --outdated 2>/dev/null || echo "pip list --outdated 실패·없음" ) | head -40`
  - `cd C:/DEV/FOMS && for p in fastapi starlette uvicorn bottle jose passlib pefile pythonnet keyring dulwich; do echo "$p: $(grep -rlE "^(from|import) $p\b" foms app.py models.py db.py 2>/dev/null | wc -l)"; done`
  - `cd C:/DEV/FOMS && grep -rhoE "^(from|import) [a-zA-Z_][a-zA-Z0-9_]*" foms app.py models.py | awk '{print $2}' | sort | uniq -c | sort -rn | head -60`
  - `cd C:/DEV/FOMS && sed -n 1,40p app.py && sed -n 60,79p app.py`
  - `cd C:/DEV/FOMS && git log --oneline --follow -- requirements.txt | head -20`
- 판정 기준: **적합** = 핵심 프레임워크가 모두 활발히 유지되는 메이저 버전에 있고, 잠금·분리·스캔 중 최소 두 가지가 존재하며, 몽키패치나 비공개 API 의존 없이 다음 메이저로 올라갈 수 있다. **조건부** = 현재 버전은 보안 패치를 받지만 업그레이드 경로에 알려진 차단 요소(비공개 API 몽키패치·핀 충돌·gevent 호환)가 있고 잠금·스캔이 없어 '재현 가능한 빌드' 가 보장되지 않는다 — 12개월 안에 거버넌스 층을 세우면 유지 가능. **부적합** = 핵심 프레임워크가 EOL 이거나 업그레이드가 대규모 재작성 없이 불가능하고, 의존성 드리프트가 이미 사고(docs/incidents·AI_CHANGELOG 의 원인 유형)로 새고 있다.
- 함정: 개별 패키지 발견('pefile 불필요')을 헤드라인으로 올리지 말 것 — 헤드라인은 '의존성 거버넌스 부재' 수준, 개별 패키지는 evidence 또는 minor_parked. `pip list --outdated` 는 60초에서 끊고 '없음' 기록, pip-audit·ruff 는 이 환경에 없다(설치 금지). Flask 3 일반론이 아니라 `app.py:24-37` 몽키패치·Werkzeug<3 핀이 왜 생겼는지 `git log`/`blame` 으로 근거를 대라. 워커 수·복제 수로 처리량을 추정하지 말 것(운영 트래픽은 확인 필요). requirements 의 fastapi 를 '이미 이행 중' 으로 오독하지 말 것 — foms import 0건.

### D2 아키텍처·코드 구조
- 핵심 질문: ① 정본 스펙이 선언한 경계 web/api/services/platform/persistence 가 실제 import 방향에서 지켜지는가 — 역방향 import(services→web, platform→api 등)와 루트 모듈(`models.py`·`db.py`) 전역 의존이 얼마나 남았는가? ② '변경 1건이 몇 파일을 건드리게 만드는가' — 단계 상수·권한·structured_data 한 곳을 바꿀 때 api·web·JS·템플릿·계약 테스트로 번지는 증폭 구조가 무엇이며, 그 증폭이 회귀로 새는가? ③ `models.py` 77클래스 단일 파일, `foms/persistence/main` 4줄 재수출 껍데기, wdcalculator 별도 엔진, 6k 줄 파일은 '보류된 분해' 인가 '구조적 부채' 인가 — 어느 것이 지식 집중(한 파일을 아는 사람만 고칠 수 있음)을 만드는가? ④ 외부 통합(네이버·카카오·채널톡·지오코딩·웹푸시)이 어댑터로 격리돼 있는가 — `foms/services/integrations` 에는 naver_commerce 만 있는데 나머지는 어디에 흩어져 있고, 외부 규격 변경이 도메인 코드까지 번지는가? ⑤ 격리 트리(Add In Program·SCheduler) 추적과 `CLAUDE.md` 의 apps/ 드리프트는 정본이 살아 있다는 신호인가, 죽었다는 신호인가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` · `foms/README.md` · `foms/platform/blueprints.py` · `foms/platform/erp_blueprint.py` · `models.py` · `db.py` · `wdcalculator_db.py` · `foms/persistence/main/models.py` · `foms/services/integrations/naver_commerce/fulfillment.py` · `foms/web/admin/naver_ingest.py` · `foms/api/erp_orders_structured.py` · `foms/services/erp_permissions.py`
- 명령:
  - `cd C:/DEV/FOMS && grep -rnE "^\s*(from|import) foms\.web" foms/services foms/api foms/platform foms/persistence | head -20; echo "services->web 역방향: $(grep -rlE '^\s*(from|import) foms\.web' foms/services | wc -l)"`
  - `cd C:/DEV/FOMS && for layer in web api services platform persistence; do echo "$layer -> models.py 직접 import: $(grep -rlE '^\s*(from|import) models\b' foms/$layer | wc -l)"; done`
  - `cd C:/DEV/FOMS && git ls-files foms | grep -E "\.py$" | xargs wc -l | sort -rn | head -25`
  - `cd C:/DEV/FOMS && grep -rlE "solapi|channeltalk|channel_talk|pywebpush|kakao" foms --include=*.py | sed 's#/[^/]*$##' | sort | uniq -c | sort -rn | head -15`
  - `cd C:/DEV/FOMS && grep -n "apps/" CLAUDE.md foms/README.md; ls -d apps 2>/dev/null || echo "apps/ 디렉토리 없음"`
  - `cd C:/DEV/FOMS && git ls-files "Add In Program" SCheduler | wc -l && git log --oneline -3 -- "Add In Program" SCheduler`
- 판정 기준: **적합** = 선언된 계층 경계가 import 방향으로 실제 강제되고(역방향 0 또는 계약 테스트로 봉쇄), 외부 통합이 어댑터 모듈 뒤에 있고, 거대 파일이 있어도 소유·분해 계획이 정본 문서에 살아 있다. **조건부** = 네임스페이스는 잡혔지만 루트 모듈(`models.py`·`db.py`) 전역 의존과 역방향 import 가 남아 있고, 통합 일부만 격리돼 있으며, 분해가 '미래 배치' 로 보류돼 지식 집중이 몇 파일에 몰려 있다 — 경계 강제 테스트와 단계적 분해로 회복 가능. **부적합** = 경계 선언과 실제 코드가 따로 놀아(드리프트 문서·죽은 스펙) 변경 1건이 예측 불가능하게 번지고, 6k 줄 파일이 사고의 반복 지점으로 이미 나타난다.
- 함정: '파일이 크다' 자체는 헤드라인이 아니다 — 그 파일이 만드는 변경 증폭·지식 집중(누가 건드리며 회귀가 몇 번 났는지, git log)을 붙여야 시스템 수준. import 그래프 전수 계산에 시간을 쓰지 말고 표본 명령으로 결정적 한 줄을 뽑고 나머지는 stack_questions 로. `foms/persistence/main/models.py` 는 내용을 열어 재수출인지 확인(`from models import *` 한 줄이다). 격리 트리를 '삭제하면 됨' 으로 축소하지 말 것 — 런타임 매니페스트·문서·테스트 참조를 grep 한 뒤 판단. '블루프린트 등록 순서 동결' 은 `foms/platform/blueprints.py:115` 에서 실제 줄을 확인.

### D3 데이터·마이그레이션
- 핵심 질문: ① structured_data(JSONB)가 핵심 도메인(주문 구조·AS 축·네이버 연결·도면 마법사 상태)을 담는 모델이 조회·정합성·리포팅·마이그레이션에 주는 장기 비용은 — 스키마가 서비스 코드 안에만 있어 인덱스·백필 스크립트·감사가 계속 사람 손으로 따라붙는 구조인가? ② 스키마 진화가 안전한가 — alembic 체인 head 단일성, downgrade 실장 비율, 로컬 dev DB drift, 배포당 1회 predeploy 마이그레이션이 web 복제 2 + 워커 1 환경에서 순서 보장을 받는가? ③ 백업·복구 RPO/RTO(Railway 보존 6일, DR·데이터 사고 복구 절차)가 주문 원장·정산 데이터 ERP 의 사업 요구에 맞는가 — 복구가 실제로 연습된 기록이 있는가? ④ 감사·이벤트 이력(AccessLog·SecurityLog·as_log·주문 변경 이력)이 '사고 후 되돌리기' 가 가능한 수준인가 — 2026-08-14 AS 증발 같은 사고가 재발하지 않도록 구조가 바뀌었는가, 도구(복구 3층)만 늘었는가? ⑤ wdcalculator 별도 엔진 + 주 DB 의 두 저장소는 정합성·백업 단위에서 어떤 위험을 만드는가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `models.py` · `migrations/env.py` · `alembic.ini` · `foms/services/db_indexes.py` · `foms/persistence/main/db.py` · `db.py` · `wdcalculator_db.py` · `docs/guides/DISASTER_RECOVERY.md` · `docs/guides/DATA_INCIDENT_RECOVERY.md` · `docs/runbooks/backup-restore.md` · `predeploy.sh` · `docs/plans/2026-08-07-audit-retention-analysis.md`
- 명령:
  - `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 timeout 60 python -m alembic heads 2>&1 | tail -5`
  - `cd C:/DEV/FOMS && echo "downgrade 정의: $(grep -l 'def downgrade' migrations/versions/*.py | wc -l) / $(ls migrations/versions/*.py | wc -l)"; echo "downgrade pass 만: $(grep -A2 'def downgrade' migrations/versions/*.py | grep -c '^\S*-\s*pass')"`
  - `cd C:/DEV/FOMS && grep -n "structured_data" models.py | head -10; echo "structured_data 참조 파일 수: $(grep -rl 'structured_data' foms --include=*.py | wc -l)"`
  - `cd C:/DEV/FOMS && grep -nE "JSONB|Index\(|ix_|gin" models.py foms/services/db_indexes.py | head -30`
  - `cd C:/DEV/FOMS && ls tools/ops | grep -E "backfill|audit|purge|retention" | wc -l; ls tools/ops | grep -E "backfill|audit"`
  - `cd C:/DEV/FOMS && grep -nE "RPO|RTO|보존|6일|retention|backup" docs/guides/DISASTER_RECOVERY.md docs/runbooks/backup-restore.md | head -20`
- 판정 기준: **적합** = JSONB 는 진짜 가변 부분에만 쓰이고 핵심 조회 축은 컬럼·인덱스로 승격돼 있으며, alembic head 1개·downgrade 실장·drift 없음, 백업 복구가 연습돼 RPO/RTO 가 문서에 숫자로 있다. **조건부** = JSONB 가 핵심 도메인을 담지만 인덱스·백필 도구·계약 테스트로 버티고 있고, 마이그레이션 체인은 건강하나 복구 연습·RPO 정의·두 엔진 백업 단위가 불명 — 조회 축 승격 로드맵과 복구 훈련으로 유지 가능. **부적합** = 데이터 사고가 반복되고(AS 증발·RUNNING 잔류·draft 부활 레이스) 그 원인이 모델 구조에 있으며, 복구가 6일 백업 하나에 매달려 있다.
- 함정: postgres MCP 는 로컬 dev DB 다 — 테이블 크기·인덱스 결과를 운영 수치로 쓰지 말고 '로컬 dev' 라고 명시. `alembic heads` 가 로컬 drift 로 실패하면 그 실패 원문이 곧 근거(60초 초과 시 끊고 기록). 'JSONB 는 나쁘다' 일반론 금지 — 어떤 조회가 어떤 우회(ilike 금지 규칙·trigram·flat 컬럼 백필)를 낳았는지 앵커로. 데이터 사고 5건을 재확인 없이 인용하지 말 것 — docs/incidents·AI_CHANGELOG·DECISIONS 에서 앵커를 찾은 것만 확인됨. downgrade 존재와 실제 되돌림 가능은 다르다 — pass 만 있는 downgrade 를 따로 센다(현재 1건 = 병합 노드).

### D4 테스트·CI·품질 시스템
- 핵심 질문: ① 208k 줄·671개 테스트 파일이 무엇을 보호하고 무엇을 못 보는가 — 계약 4계층 분포, `tests/security` 가 `__init__` 뿐인 점, 통합·성능·보안 사각을 유형별로 세면 어디가 비어 있는가? ② 문자열·정규식 계약 테스트(핀·인라인 style·목업 잔재 검사)가 만드는 변경 증폭 비용은 — 기능 1건에 계약 테스트 몇 개가 따라 바뀌는지(git log 표본), 그 보호가 실제 회귀를 얼마나 잡았는지(docs/incidents·AI_CHANGELOG 원인 유형)? ③ SQLite 본 레인 + PG 레인 이중 구조의 사각(FK 미강제·JSONB 연산자 차이)이 'CI 에서만 터지는' 사고를 만드는가 — 로컬 pre_push_smoke 와 CI 가 같은 것을 보는가? ④ CI 시간과 워크플로 7개가 이 커밋 속도에서 병목인가 — ci_watch 의 사각, perf-gate 가 deploy push 에서 advisory 인 구조가 '녹색' 의 뜻을 흐리는가? ⑤ 린트·타입·커버리지 0 이 실제 회귀로 새는가, 계약 테스트 + import 게이트가 충분히 대체하는가 — 두 번째 개발자에게 이 체계가 '설명 가능' 한가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `.github/workflows/ci.yml` · `.github/workflows/postgres-lane.yml` · `.github/workflows/perf-gate.yml` · `.github/workflows/harness-ci.yml` · `tests/README.md` · `tests/conftest.py` · `pytest.ini` · `scripts/ops/pre_push_smoke.ps1` · `tests/performance/test_perf_regression_guard.py` · `tests/domains/test_docs_facing_registry.py` · `docs/harness/policy/DECISIONS.md` · `docs/guides/TEST_GUIDE.md`
- 명령:
  - `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 timeout 300 python -m pytest --collect-only -q -p no:playwright 2>&1 | tail -3`
  - `cd C:/DEV/FOMS && for d in tests/*/; do echo "$d $(find $d -name 'test_*.py' | wc -l)"; done; ls tests/security`
  - `cd C:/DEV/FOMS && echo "read_text 계약: $(grep -rlE 'read_text\(|\.read\(\)' tests --include=test_*.py | wc -l)"; echo "re.search 계약: $(grep -rlE 're\.(search|findall|compile)' tests --include=test_*.py | wc -l)"; echo "?v= 핀 검사: $(grep -rl '?v=' tests --include=test_*.py | wc -l)"`
  - `cd C:/DEV/FOMS && grep -nE "timeout-minutes|DATABASE_URL|-n auto|pytest" .github/workflows/ci.yml | head -20`
  - `cd C:/DEV/FOMS && git log --since=2026-08-01 --format=%s | grep -ciE "^(fix|버그|hotfix)" ; git log --since=2026-08-01 --format=%s | grep -iE "CI red|계약|핀|pin" | wc -l`
  - `cd C:/DEV/FOMS && ls docs/incidents; grep -nE "원인|root cause|RCA" docs/incidents/*.md | head -10`
- 판정 기준: **적합** = 테스트 층이 유형별(단위·계약·통합·보안·성능)로 고르게 있고 CI 가 커밋 속도를 막지 않으며(피드백 15분 이내·녹색 정의 단일), 회귀 사고의 원인 유형이 테스트 부재가 아닌 곳에서 난다. **조건부** = 계약 테스트가 두텁고 실제 회귀를 잡지만 보안·통합 사각과 SQLite/PG 이중 레인 사각이 있고, 변경 증폭(핀·계약 동시 갱신) 비용이 커밋 속도에 세금으로 붙는다 — 사각 채우기와 계약 테스트 다이어트로 유지 가능. **부적합** = CI 가 상시 빨강이거나 우회되고, 사고 원인 유형의 다수가 '테스트가 못 보는 곳' 이며, 린트·타입 부재가 반복 결함으로 확인된다.
- 함정: 전체 pytest 절대 금지 — collect-only 와 단일 파일만(300초 초과 시 끊고 기록). '208k 줄은 과잉/부족' 을 숫자만으로 판정하지 말 것 — 사고 원인 유형을 세어 근거를 단다. CI 시간 진범(PBKDF2)은 `docs/harness/policy/DECISIONS.md:21-25` 로 이미 재졌다 — 다시 재지 말고 인용하되 실제 조치를 `tests/conftest.py:26-28` 에서 확인. 메모리 정본(ci_watch 사각·perf-gate 사각)은 `tools/harness/ci_watch.py`·`.github/workflows/perf-gate.yml` 에서 재확인한 것만 확인됨(§5 에 반박 1건 있음). 계약 테스트 파일 수를 '변경 증폭' 그 자체로 단정하지 말 것 — 커밋 표본에서 기능 변경 1건에 함께 바뀐 테스트 파일 수를 보여야 시스템 근거.

### D5 프론트엔드·자산 파이프라인
- 핵심 질문: ① 번들러·린트·타입 없는 130k 줄 Vanilla JS(6k 줄 단일 파일 포함)가 어디까지 버티는가 — 모듈 경계·전역 네임스페이스·로드 순서 의존이 변경 증폭과 지식 집중을 어떻게 만드는가? ② 셸 3벌(ERP 데스크톱·모바일 v2·v3) + 프래그먼트 스왑 + 서비스워커 캐시 구조가 만드는 표면 확산은 — 같은 기능이 셸마다 따로 배선돼(페이지 스코프 스크립트 누락·surfaces 번들 미적재 유형) 회귀가 반복되는가? ③ `?v=` 수동 핀 + SW staticCacheFirst 조합의 변경 증폭·사고 이력(핀 누락 시 stale JS·SW 캐시 phantom)은 얼마나 되며 '빌드 파이프라인 부재' 의 직접 비용인가? ④ 인라인 style 687곳·인라인 script 템플릿 43개는 규칙 실패인가 규칙 과잉인가 — 디자인 SSOT 린트가 실제로 무엇을 막는가? ⑤ 현장(태블릿·iOS 웹뷰)에서 오프라인·접근성·성능(RUM) 전략이 시스템으로 존재하는가, 개별 함정 메모로만 존재하는가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `static/js/orders/erp-order-shared.js` · `static/sw.js` · `templates/partials/shared/layout_head.html` · `templates/partials/shared/layout_scripts.html` · `templates/partials/shared/erp_mobile_shell.html` · `templates/partials/v3/foms_app_shell_v3.html` · `static/js/runtime/erp-shell.js` · `static/js/runtime/erp-mobile-shell.js` · `static/css/foundation/erp-pro.css` · `foms/api/fragment.py` · `foms/api/foms_offline.py` · `tools/design/ssot_lint.py`
- 명령:
  - `cd C:/DEV/FOMS && echo "style=: $(grep -rn 'style=\"' templates | wc -l)"; echo "?v= 핀: $(grep -rn '?v=' templates | wc -l)"`
  - `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python -c "import re,io,glob;R=re.compile(r'<script(?![^>]*\bsrc=)[^>]*>');F=[[x for x in R.findall(io.open(f,encoding='utf-8',errors='ignore').read()) if 'application/json' not in x and 'text/template' not in x] for f in glob.glob('templates/**/*.html',recursive=True)];print('인라인 script 템플릿',sum(1 for m in F if m),'태그',sum(len(m) for m in F))"`
  - `cd C:/DEV/FOMS && git ls-files static/js | grep -E "\.js$" | xargs wc -l | sort -rn | head -15`
  - `cd C:/DEV/FOMS && for f in static/js/orders/erp-order-shared.js static/js/drawing/wizard.js static/js/runtime/erp-shell.js static/sw.js; do node --check "$f" && echo "OK $f"; done`
  - `cd C:/DEV/FOMS && grep -nE "staticCacheFirst|CACHE_VERSION|cache\.|networkFirst" static/sw.js | head -15`
  - `cd C:/DEV/FOMS && git log --since=2026-06-01 --format=%s | grep -icE "\?v|핀|범프|bump|SW 캐시|stale"`
  - `cd C:/DEV/FOMS && grep -rn "window\.[A-Z][A-Za-z]* *=" static/js --include=*.js | wc -l; grep -rn "type=\"module\"" templates | wc -l`
- 판정 기준: **적합** = 자산이 모듈 시스템(ESM 또는 번들)으로 경계를 갖고, 캐시 무효화가 빌드 해시로 자동이며, 셸이 하나의 레이아웃 계약 위에서 갈라지고, 린트가 인라인 규칙을 기계로 막는다. **조건부** = 번들 없이도 계약 테스트·SSOT 린트·수동 핀으로 버티고 있지만 셸 3벌 표면 확산과 핀 누락 사고 유형이 반복돼 변경 증폭 세금이 크다 — 해시 기반 캐시 무효화와 셸 공용 계층 정리로 유지 가능. **부적합** = 전역 네임스페이스 충돌·로드 순서 의존이 사고의 주 원인 유형이고, 같은 기능이 셸마다 3번 배선돼 신규 기능 비용이 선형으로 늘며, 인라인 규칙이 사실상 폐기됐다.
- 함정: 'style 687곳' 은 사실 카드 숫자 — 다시 세되 차이가 나면 명령 원문을 적고, 규칙 실패/과잉 판정은 `tools/design/ssot_lint.py` 가 무엇을 검사하는지 읽은 뒤에(docs/design 문구 9개뿐이다). 6k 줄 JS 한 파일이 헤드라인이 아니다 — 몇 셸이 의존하고 변경이 어떤 계약 테스트로 번지는지가 시스템 근거. npm install·번들러 실험 금지, `node --check` 만 허용(node v24 있음). 메모리 함정(SW phantom·?v 범프·페이지 스코프 v3 누락)은 `static/sw.js`·layout 파셜에서 앵커를 찾은 것만 확인됨(§5 에 앵커 있음). RUM 수치·현장 기기 대수는 운영 데이터 — stack_questions 로. 인라인 script 카운트에 `grep -P` 를 쓰지 말 것(로케일 오류) — 위 파이썬 명령 사용.

### D6 보안·권한·개인정보
- 핵심 질문: ① 인증·세션·권한 모델(역할 4종 × 팀 + erp_permissions + 코호트 게이트)이 팀 확장·외부 협력사·공유 링크에 견디는가 — 권한 판정이 한 곳(SSOT)에 있는가, 화면·API·프래그먼트마다 흩어져 있는가? ② fail-open 정책들이 어디에 있고(`docs/harness/foms_failopen_inventory.json`·레이트리미터 Redis 장애·훅 fail-open) 사업상 감당 가능한가 — 열림이 로그로 관측되는가, 조용히 열리는가? ③ 의존성 CVE 스캔 없음·비밀 관리·업로드 티켓·공유 토큰·XSS 싱크 인벤토리가 '체계적 방어' 인가 '인벤토리 나열' 인가 — `tests/security` 가 비어 있는데 무엇이 회귀를 막는가? ④ 고객 개인정보(전화·주소·현장 사진)의 보존 기간·마스킹·접근 기록·삭제 정책이 문서와 코드로 존재하는가 — 보존 정책 문서가 plans 안 분석 문서뿐인가? ⑤ 고급 통제(서명 키 회전·운영 승인·감사 커버리지)는 있는데 기본 통제(스캔·보안 테스트·PII 정책)가 비어 있는 불균형은 왜 생겼고 어떤 위험을 남기는가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `foms/services/erp_permissions.py` · `foms/services/auth/__init__.py` · `foms/web/auth/routes.py` · `foms/services/security/password_policy.py` · `foms/services/security/ops_approval.py` · `foms/services/security/signing/signing_keys.py` · `foms/services/rate_limit.py` · `foms/platform/request_limits.py` · `foms/api/share.py` · `foms/api/files/upload_ticket_routes.py` · `foms/services/storage.py` · `docs/harness/foms_failopen_inventory.json` · `docs/harness/foms_untrusted_dom_sinks.json` · `docs/harness/foms_secret_literal_allowlist.json` · `docs/harness/foms_api_error_leak_inventory.json` · `docs/plans/2026-08-07-audit-retention-analysis.md`
- 명령:
  - `cd C:/DEV/FOMS && echo "fail-open 언급: $(grep -rniE 'fail[-_ ]?open' foms --include=*.py | wc -l)"; PYTHONIOENCODING=utf-8 python -c "import json;d=json.load(open('docs/harness/foms_failopen_inventory.json',encoding='utf-8'));print(type(d).__name__, len(d) if hasattr(d,'__len__') else '')"`
  - `cd C:/DEV/FOMS && git ls-files | grep -iE "\.env|secret|\.pem|\.key$" | head; ls tests/security`
  - `cd C:/DEV/FOMS && grep -rnE "def (require|check|has)_?(perm|role|permission)" foms --include=*.py | wc -l; grep -rn "erp_permissions" foms --include=*.py | sed 's#:.*##' | sort -u | wc -l`
  - `cd C:/DEV/FOMS && sed -n 1169,1260p models.py`
  - `cd C:/DEV/FOMS && grep -rniE "마스킹|mask|보존|retention|개인정보|pii" foms --include=*.py | wc -l; git ls-files docs | grep -iE "privacy|개인정보|pii|retention"`
  - `cd C:/DEV/FOMS && grep -nE "token|expire|ttl|signed" foms/api/share.py | head -15`
- 판정 기준: **적합** = 권한 판정이 SSOT 한 곳에서 이뤄지고 API·화면·프래그먼트가 그것을 통과하며, fail-open 은 전부 로그로 관측되고 목록이 닫혀 있고, 의존성 스캔·보안 회귀 테스트·PII 보존/마스킹 정책이 문서와 코드로 있다. **조건부** = 고급 통제(서명 키·운영 승인·감사 인벤토리)는 있으나 기본 통제(CVE 스캔·tests/security·PII 정책 문서)가 비어 있고 fail-open 이 사업 판단 없이 기본값으로 남아 있다 — 기본 통제 층을 채우면 유지 가능. **부적합** = 권한 판정이 화면마다 흩어져 우회 경로가 존재하거나, 공유 토큰·업로드에 만료·서명이 없거나, PII 가 무기한 보존되며 접근 기록이 없다.
- 함정: 취약점 세부 익스플로잇 경로를 헤드라인에 쓰지 말 것 — 시스템 수준(통제 층의 공백)으로 말하고 구체 지점은 evidence 앵커로. 인벤토리 항목 수를 '방어 수준' 으로 오독하지 말 것 — 인벤토리는 관측이지 차단이 아니다; 실제로 막는 것(테스트·훅·런타임 가드)을 구분. 레이트리미터 fail-open 은 `foms/services/rate_limit.py:58-70` 에서 확인한 뒤에만 확인됨. 법적 요구를 조문 단위로 단정하지 말 것 — '정책 문서·보존기간 정의가 있는가' 수준으로 판정, 법률 판단은 열린 질문. 비밀값 자체를 출력에 붙이지 말 것 — 경로와 존재 여부만. 위 명령 3의 이름 패턴은 0건이 정상(실제 이름은 `can_edit_erp`·`erp_edit_required`·`evaluate_policy`·`user_can_read_order`·`role_required`), 명령 5의 513건은 `masked_counts` 같은 비-PII 용법을 포함한다.

### D7 운영·배포·관측·회복력
- 핵심 질문: ① 단일 리전·웹 복제 2·워커 1개가 큐 + 감독 없는 백그라운드 루프(재측정 5개)를 돌리는 구조가 사업 연속성(평일 16:50 자동 발송, 네이버 호출 IP 한도 3)에 맞는가 — 워커 재배포·루프 사망·큐 정체를 시스템이 스스로 감지·회복하는가? ② 배포(deploy→production cherry-pick·predeploy 마이그레이션·헬스체크 web 만)와 롤백이 안전한가 — 롤백이 코드·마이그레이션·워커 세 축에서 동시에 가능한지, 훈련 기록이 있는가? ③ 장애를 사람이 알기까지 얼마나 걸리는가 — Sentry·RUM 일간 집계·health·경보 규칙 중 무엇이 실제로 '사람에게 알리는' 경로인가, 사용자가 먼저 발견하는 구조인가? ④ 외부 의존(네이버 토큰·정산 API 403·카카오·Redis·R2·Cloudflare) 각각의 실패 모드가 문서(runbooks 8·incidents 5)에 있고 자동 복구 또는 사람 절차가 있는가 — RUNNING 영구 잔류 같은 '재배포에 잘리는 상태' 유형이 시스템적으로 처리되는가? ⑤ 환경변수 정본(31줄·표 0행) 대 `start.sh` 플래그 — 운영 설정이 코드에만 존재하는 지식 집중이 두 번째 운영자에게 어떤 위험인가? 비용 구조는 무엇으로 확인해야 하는가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `start.sh` · `predeploy.sh` · `railway.toml` · `railway-worker.toml` · `railway-cron.toml` · `Dockerfile` · `Procfile` · `foms/platform/sentry_setup.py` · `foms/platform/logging_setup.py` · `foms/api/health.py` · `foms/services/jobs/queue.py` · `foms/services/jobs/tasks.py` · `foms/services/sidefx_worker.py` · `docs/guides/DEPLOYMENT_GUIDE.md` · `docs/guides/RAILWAY_ENV_VARS.md` · `docs/runbooks/sidefx-worker-ops.md`
- 명령:
  - `cd C:/DEV/FOMS && grep -nE "&\s*$|FOMS_[A-Z_]+" start.sh | head -30; echo "FOMS_ 플래그 종류: $(grep -oE 'FOMS_[A-Z_]+' start.sh | sort -u | wc -l)"`
  - `cd C:/DEV/FOMS && cat railway.toml; echo ---; cat railway-worker.toml; grep -n "healthcheck" railway*.toml || echo "toml healthcheck 없음"`
  - `cd C:/DEV/FOMS && sed -n 1,60p foms/api/health.py; grep -nE "SENTRY_DSN|init\(" foms/platform/sentry_setup.py | head`
  - `cd C:/DEV/FOMS && ls docs/runbooks docs/incidents; grep -lE "롤백|rollback" docs/guides/*.md docs/runbooks/*.md | head`
  - `cd C:/DEV/FOMS && wc -l docs/guides/RAILWAY_ENV_VARS.md; grep -c "^|" docs/guides/RAILWAY_ENV_VARS.md; grep -rhoE "os\.(environ\.get|getenv)\(['\"][A-Z_]+" foms start.sh app.py | grep -oE "[A-Z_]+$" | sort -u | wc -l`
  - `cd C:/DEV/FOMS && grep -rnE "RUNNING|heartbeat|supervis|watchdog|alert" foms/services/jobs foms/services/sidefx_worker.py start.sh | head -15`
- 판정 기준: **적합** = 워커·루프가 감독 프로세스나 큐 기반 스케줄러 아래 있고 죽으면 경보가 사람에게 가며, 배포·롤백이 코드+마이그레이션+워커 세 축에서 문서와 훈련으로 검증됐고, 환경변수 정본이 실제 플래그와 일치한다. **조건부** = 운영은 되고 있으나 감독 없는 루프·web 만 헬스체크·경보 경로 불명·env 정본 공백이 '사람이 보고 있을 때만 안전' 한 상태 — 감독·경보·env 정본 세 가지로 회복 가능. **부적합** = 사고 문서에 같은 실패 모드(루프 사망·RUNNING 잔류·토큰 만료)가 반복되고 감지가 사용자 신고에 의존하며 롤백이 사실상 불가능하다.
- 함정: 운영 비용·트래픽·복제 수 적정성은 운영 데이터 없이 판정 불가 — '확인 필요' 와 stack_questions 로; Railway 대시보드 설정은 사실 카드 인용만. railway CLI·ssh 금지(로컬 파일과 git 만). 백그라운드 루프는 grep 한 줄로 재확인하고, '감독 없음' 을 단정하려면 supervisor·restart 로직 부재를 grep 결과로 보여라. 메모리 함정(워커 재배포 큐 정체·RUNNING 잔류·프래그먼트 2~9초 경로)은 코드·문서 앵커를 찾은 것만 확인됨. 'Sentry 가 켜져 있는가' 는 코드로 알 수 없다(DSN 은 운영 env) — 코드 구조만 판정, 실제 활성은 열린 질문.

### D8 개발 시스템(DX·하네스·문서·프로세스)
- 핵심 질문: ① 사람 1명 + 에이전트가 3개월 2,765 커밋을 내는 구조에서 하네스(훅·규칙 SSOT 4벌·인벤토리 JSON·스킬·tools/harness)와 문서(plans 441·specs 85)가 속도를 내는가, 비용인가 — 무엇이 실제 회귀를 막았고(DECISIONS·incidents 앵커) 무엇이 의식(ritual)으로 남았는가? ② 두 번째 개발자(사람 또는 다른 에이전트)가 들어오면 무엇부터 막히는가 — 온보딩 경로(README·SYSTEM_DOCUMENTATION·AI_STATUS 40줄 계약)가 실재하는지, apps/ 드리프트가 '정본이 코드를 못 따라간다' 는 증상인지? ③ 정책 SSOT 4벌(AGENTS·CLAUDE·.cursor/rules·copilot)이 서로 일치하는가 — 같은 규칙이 몇 번 중복되고 어긋난 곳은 어디인가? ④ plans·specs 의 지식이 다시 찾아지는가 — ARCHIVE_INDEX·DECISIONS 가 색인 역할을 하는지, 세션 메모리에만 남는 지식이 시스템 밖에 있는지? 6개월 ablation 주기(2026-08-03 첫 회)가 실제로 돌았고 무엇을 덜어냈는가? ⑤ 런타임이 `docs/harness` JSON 을 COPY 해 읽는 구조와 훅 fail-open 규칙은 개발 시스템과 운영 시스템의 결합을 만드는가 — 하네스 변경이 배포 실패로 번질 수 있는 경로가 있는가? ⑥ [더 필요한 것] 이 차원이 12~24개월 굴러가려면 무엇을 갖춰야 하고, 첫 걸음과 검증은 무엇인가?
- 앵커: `AGENTS.md` · `CLAUDE.md` · `.cursor/rules/00-project-context.mdc` · `.github/copilot-instructions.md` · `.claude/settings.json` · `.claude/hooks/session_stop.py` · `.claude/hooks/guard_shell.py` · `tools/harness/verify_result.py` · `tools/harness/manifest.yaml` · `docs/harness/policy/DECISIONS.md` · `docs/AI_STATUS.md` · `docs/ARCHIVE_INDEX.md` · `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` · `docs/guides/SYSTEM_DOCUMENTATION.md` · `docs/guides/LONG_TASK_PROMPTS.md` · `Dockerfile`
- 명령:
  - `cd C:/DEV/FOMS && for d in plans specs evolution guides design context runbooks incidents; do echo "docs/$d $(ls docs/$d | wc -l)"; done; ls docs/plans | grep -c "^2026-0[89]"`
  - `cd C:/DEV/FOMS && grep -n "apps/" CLAUDE.md foms/README.md; ls -d apps 2>/dev/null || echo "apps/ 없음"; grep -nE "^## |^### " docs/guides/SYSTEM_DOCUMENTATION.md | head -20`
  - `cd C:/DEV/FOMS && for f in AGENTS.md CLAUDE.md .cursor/rules/*.mdc .github/copilot-instructions.md; do echo "$f $(wc -l < "$f") 줄, 근본원인:$(grep -c '근본' "$f") production:$(grep -c 'production' "$f")"; done`
  - `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 timeout 120 python tools/harness/verify_result.py --json 2>&1 | tail -5`
  - `cd C:/DEV/FOMS && ls .claude/hooks | wc -l; PYTHONIOENCODING=utf-8 python -c "import json;d=json.load(open('.claude/settings.json',encoding='utf-8'));h=d.get('hooks',{});print({k:len(v) for k,v in h.items()})"`
  - `cd C:/DEV/FOMS && grep -nE "COPY .*docs/harness" Dockerfile; grep -nE "ablation|2027-02|덜어|제거" docs/harness/policy/DECISIONS.md | head -10; wc -l docs/AI_STATUS.md docs/harness/policy/DECISIONS.md docs/ARCHIVE_INDEX.md`
- 판정 기준: **적합** = 정책 정본이 1벌(나머지는 참조)이고 코드 구조와 일치하며, 하네스 각 부품이 막은 사고를 근거로 남기고 주기적으로 덜어내며, 새 개발자가 문서 3개 이내로 첫 변경을 안전하게 낼 수 있고, 개발 도구가 운영 런타임과 결합돼 있지 않다. **조건부** = 하네스가 실제 회귀를 막고 있으나 4벌 정책 중복·경로 드리프트·plans 441 의 색인 부재·메모리에만 있는 지식이 온보딩 비용과 정본 불신을 만든다 — 정본 단일화와 지식 색인으로 유지 가능. **부적합** = 하네스가 의식으로 남아 우회되거나(훅 fail-open 남발) 정본이 코드와 어긋나 에이전트가 잘못된 경로를 따르고, 운영 배포가 개발 문서 디렉토리에 의존해 하네스 변경이 배포 실패로 번진 이력이 있다.
- 함정: '문서가 많다' 는 헤드라인이 아니다 — 지식이 '다시 찾아지는가'(색인·검색 경로·정본 지정)가 시스템 질문. 특정 훅 하나의 버그를 헤드라인으로 올리지 말 것 — 부품 목록 대 '막은 사고' 대조표가 시스템 근거. `verify_result.py` 가 편집·설치를 유발하면 즉시 중단(현재는 `import app` 서브프로세스 + 스펙 탐지만), 120초 초과 시 끊고 기록. 메모리 파일(160여 개)의 내용을 시스템 상태로 인용하지 말 것 — 메모리는 세션 밖 지식이며 그것이 저장소 문서에 없다는 사실 자체가 관측. 정책 4벌 대조는 표본(근본 원인·production·한글·인라인 스타일·apps/)으로 결정적 한 줄을 뽑고 전수 대조는 stack_questions 로. DECISIONS 항목은 `### [날짜]` 형식이라 `grep '^## '` 로는 0건이 나온다.

## 5. 사전 관측(가설·검증 필요)

워커 8명이 실제 저장소를 읽어 만든 관측이다. 항목 끝의 `[확인됨: …]` 은 워커가 앵커를 열었거나 명령을 실행해 결정적 출력을 얻은 것, `[가설]` 은 앵커가 없는 것이다. 받는 에이전트는 확인됨을 재검증·확장하고 가설을 확인하거나 반박한다. 워커 간 중복은 가장 구조적인 차원에 한 번만 두고 나머지는 "→ Dn 참조" 로 병합했다. 워커 판정은 8차원 전부 **조건부** 였다. 각 차원 끝의 "더 필요한 것(초안)" 은 워커 `needed` 의 압축이다. 항목 머리의 태그 `[리스크|결핍 · 높음|중간|낮음 · 지금|6개월|2년]` 은 워커 JSON 값 그대로다 — 결핍 = 워커 `lacking`(보고서 ③ 부족한 것 재료, 이미 새는 증거 앵커 포함) · 리스크 = `system_risks`(보고서 ② 재료) · `리스크+결핍` = 두 종류가 병합된 항목(심각도·시점은 주된 쪽 값) · 심각도·시점은 워커 값. '더 필요한 것(초안)' 은 보고서 ④ 의 재료일 뿐 이 검토에서 실행하지 않는다(설치·git 변경 금지 유지).

### 5.0 총괄 가설 H1~H8 판정
| 가설 | 판정 | 근거 앵커 |
|---|---|---|
| H1 의존성 거버넌스 부재 | 확인됨(D1) — 단 '12개월' 이 아니라 이번 분기: 핀 자체가 이미 보안 패치 창 밖 | `requirements.txt:31` · `requirements.txt:106`, OSV 조회 출력(Flask CVE-2026-27205 fixed=3.1.3 등), 잠금·dependabot 파일 없음 |
| H2 품질 도구 층 공백 | 부분 확인(D4) — 린트·타입·커버리지 0 은 확인. 그러나 계약 테스트는 '문자열 매칭만' 이 아니다: 수집 9,879건 중 47% 가 HTTP 경로를 실제로 때린다(워커 파이썬 분류 스크립트 — 셈법 미기재·재측정 필요). 세금은 실재(CI 빨강 표본 19건 중 11건 자가 유발 — 셈법은 D4 첫 항목) | `requirements.txt:74-77` · `scripts/ops/pre_push_smoke.ps1:221-222` · collect-only 분류 출력 |
| H3 모듈러 모놀리스 경계가 절반 | 확인됨(D2) — 경계는 디렉토리 이름일 뿐 방향 강제 0 | `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:315-322` · 계층별 grep 출력(services→web 8·api→web 53) |
| H4 JSONB 장기 비용 | 확인됨(D3) — 두 달 4번 사고가 사본 동기화 구조에서 났다 | `models.py:99-112` · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:20-30` · `docs/AI_STATUS.md:17-18` |
| H5 프론트 자산 파이프라인 부재 | 확인됨(D5) — 9일에 4번 '같은 핀 다른 자산' | `static/sw.js:10-17` · `foms/platform/app_factory.py:60-69` · 커밋 6e8a6f75e·c956fc600·603a4a92c·156608706 |
| H6 보안 검증이 인벤토리 중심 | **부분 확인, 절반 반박**(D6) — 쓰기 권한·CSRF·fail-open 은 인벤토리 + 런타임 게이트 + 정적 테스트 3중이고 인벤토리만 있는 것은 XSS 뿐; `tests/security` 는 비었지만 보안 테스트 74개가 domains 에 산재(워커 셈법: 파일명·본문 보안 키워드 대조 — 셈법 미기재·재측정 필요). 확인된 공백 = CVE 스캔 0·CSP 0·로그인 잠금 0·PII 정책 0·무로그 fail-open | `foms/services/orders/order_mutation_policy.py:579-584` · `tests/domains/test_stored_xss_sinks.py:181-193` · `tests/domains/test_auth_enforcement.py:1-5` |
| H7 운영 단일 장애점 | 확인됨(D7) — 루프는 4개가 아니라 5개, 경보 경로 0 | `start.sh:23-26` · `foms/api/health.py:7-10` · `tools/ops/rq_failed_jobs.py:3-5` |
| H8 개발 시스템의 무게 | 부분 확인(D8) — 온보딩 경로 부재·정본 드리프트·색인 정지는 확인. '의식(ritual)' 은 반박: 셸 가드가 1주일에 deny 70건(production 강제 푸시 33 등)을 실제로 막았고 Stop 게이트는 실동작 | `CLAUDE.md:48` · `docs/ARCHIVE_INDEX.md:3` · `docs/harness/logs/SHELL_GUARD_LOG.md` · `.claude/hooks/quality_check.py:31-38` |

반박된 사실 카드·메모리 값(같은 함정에 빠지지 않게 남긴다): 'CI 14분+' → 2.45분(`docs/plans/2026-08-26-ci-speed-ledger.md:78`) · '루프 4개' → 5개(`start.sh:72`) · 메모리 정본 'ci_watch 는 워크플로 1개만 본다' → 현재 코드는 SHA 기준 전 워크플로(`tools/harness/ci_watch.py:166-185`), 남는 사각은 '런 없음=green'(`tools/harness/ci_watch.py:404`) · `app.py:24-37` 몽키패치는 pbkdf2/scrypt 를 원본에 위임해 현재 해시 전부에 무동작이고 전제 주석도 Werkzeug 2.3.8 원문과 맞지 않는다(`PYTHONIOENCODING=utf-8 python -c "import inspect, werkzeug.security as s; print(inspect.getsource(s._hash_internal))"` 출력) · 인라인 script 템플릿 43 → 46, FOMS_ 플래그 12 → 13, 훅 10 → py 11/커맨드 8, plans 441 → 449.

### D1 스택·의존성 적합성 — 워커 판정: 조건부
한 줄: 프레임워크 계열은 살아 있고 상향 차단 요소가 4곳뿐이라 재작성 없이 올라갈 수 있지만, 현재 핀은 이미 패치 창 밖이고 잠금·분리·스캔·버전 정본이 전부 0 이라 이번 분기 안에 메이저 상향 패킷 1개 + 거버넌스 층이 필요하다.
- [리스크 · 높음 · 지금] 핵심 웹 프레임워크 라인이 업스트림 패치 창 밖 — Flask 2.3.3(37개월)·Werkzeug 2.3.8·Jinja2 3.1.2(53개월)이고 알려진 수정은 전부 3.x 에만 있다. 상향을 막는 것은 상한 핀 1줄·몽키패치 13줄·테스트 상수 1곳·LimitedStream 재검증 1곳뿐인데 3개월간 아무도 올리지 않았고 상한 핀 사유는 커밋 본문 어디에도 없다(f40e6a36c). 도면·사진 업로드(다중파트)와 템플릿 sandbox 계열이 직접 표면. [확인됨: `requirements.txt:106` · `app.py:22-36` · `tests/conftest.py:26-28` · `tests/domains/test_password_kdf_contract.py:29-36` · `foms/platform/request_limits.py:225` · PyPI/OSV 조회 출력(CVE-2024-49767 fixed=3.0.6 · CVE-2025-27516 fixed=3.1.6)]
- [리스크 · 높음 · 6개월] 파이썬 런타임 버전이 저장소에서 결정되지 않는다 — web 은 Dockerfile 3.12(패치 미고정), 워커·크론·sidefx toml 은 nixpacks(`.python-version` 3.11.9)인데 toml 은 사문이라 실제 버전은 대시보드에만 있다. 3.11 보안 지원 종료 2027-10-31 은 24개월 창 안. 패치 버전 차이(로컬 3.12.10 vs CI 3.12.13)만으로 이미 사용자 텍스트 유실 버그(777076423). 코드에 3.12 전용 문법 0 이라 워커가 3.11 이어도 드러나지 않는다. [확인됨: `Dockerfile:3` · `railway-worker.toml:4-7` · `docs/AI_STATUS.md:68` · `.github/workflows/ci.yml:48` · `git show 777076423` 출력 · endoflife 조회 출력]
- [리스크+결핍 · 높음 · 지금] 의존성 목록이 2026-01-16 윈도우 데스크톱 `pip freeze` 덤프(UTF-16)에서 굳었다 — 유효 123 항목 중 도달 불가 39(워커 importlib.metadata 폐포 스크립트 — 저장소 밖, 셈법 미기재·재측정 필요)·상한 없는 핀(floating) 20(재측정 필요)·알려진 권고 보유 핀 24(OSV 조회 출력, 재측정 필요; Pillow 32건·urllib3 12·Werkzeug 12·Jinja2 10), 잠금·requirements-dev·pip-audit·dependabot 전부 없음, 운영 이미지에 pytest·playwright·tests/ 포함, Dockerfile 5회 재시도 루프, 코드 수준 설치 통제는 대체 인덱스만 묻는다. 이미 새는 곳: 의존성 추가 1건이 Railway 빌드 실패 2건(75b635beb·ede84eeb8), rq 2.0 breaking → 전용 CI 레인 신설. [확인됨: `git blame requirements.txt`(984169b2c) · `Dockerfile:17-27` · `.dockerignore:40-42` · `requirements.txt:74-77` · `.github/workflows/ci.yml:26-31` · `tools/harness/guard_policy.py:564-570` · 잠금 파일 10종 ls 없음 출력]
- [리스크 · 중간 · 6개월] gevent 몽키패치 + psycogreen(마지막 릴리스 2020-02) + Socket.IO(gevent 모드)가 프로세스 전체를 그린렛 규율에 묶는데 실시간 소비자는 emit 7건(채팅 6·도면 1)뿐이고 알림 배지는 폴링이다. 이 경로는 로컬(gevent 미설치·`socketio.run` threading)·CI(gunicorn 미기동) 어디서도 실행되지 않아 2026-02-20 모드 불일치 사고(SEV-3)·2026-07-21 Redis 장애가 운영에서만 보였다. 파이썬 3.13 경로는 psycopg2-binary·Pillow·numpy·SQLAlchemy 핀의 cp313 휠 부재에 걸린다. [확인됨: `app.py:3-16` · `foms/platform/realtime.py:204-207` · `docs/context/INCIDENT_RAILWAY_GEVENT_SOCKET_2026-02-20.md:4-16` · `run.py:113` · `db.py:52-55` · `foms/services/rate_limit.py:58-70` · `pip show gevent psycogreen` 미설치 출력]
- [리스크 · 중간 · 6개월] RQ 단일 큐 default + 워커 1(동시성 1)에 네이버(IP 한도 3 = 단일 출구)·채널톡·웹푸시·썸네일·지오코딩이 직렬화되고 2시간 백필 잡이 앞을 막는다(우선순위 큐 없음). 운영 큐 대기시간은 확인 필요. [확인됨: `foms/services/jobs/queue.py:54` · `foms/services/jobs/queue.py:479-480` · `start.sh:32-33`] → 감독·재배포 문제는 D7 참조.
- 더 필요한 것(초안):
  - ① 거버넌스 층 — `requirements.in` + pip-tools/uv 잠금(해시) + `requirements-dev.txt` 분리 + CI pip-audit(또는 OSV 조회) + dependabot 주 1회, Dockerfile `--require-hashes`·tests/ 제외(첫 걸음 = 도달 불가 39개 제거 후 잠금 1회 생성 → 스테이징 빌드; 검증 = 같은 커밋 두 번 빌드 `pip freeze` 동일·`pip check` 0·APP_OK).
  - ② 메이저 상향 패킷 1개(Flask 3.1·Werkzeug 3.1·Jinja2 3.1.6·Pillow 11+·requests/urllib3; 첫 걸음 = 스테이징 브랜치에서 `tests/domains/test_password_kdf_contract.py` 를 먼저 빨강으로 만들고 conftest 를 고친다; 검증 = CI 4 워크플로 green + 스테이징 로그인·업로드·Socket.IO + OSV 재조회 0건).
  - ③ 파이썬 정본 단일화(`.python-version` 3.12.x·Dockerfile 패치 고정·워크플로 `python-version-file`·서비스 6개 같은 이미지·`/healthz` 에 `sys.version`).
  - ④ 운영 토폴로지 재현 레인(CI 에서 `gunicorn -k gevent` + Redis 로 `/healthz`·enqueue 1건).
  - ⑤ 스택 ADR 1건을 `docs/harness/policy/DECISIONS.md` 에(유지 판정·교체 비용 근거: route 367·render_template 106·url_for 863·템플릿 278·Column 925·Flask 테스트 클라이언트 파일 265/672; fastapi 핀은 덤프 잔재).

### D2 아키텍처·코드 구조 — 워커 판정: 조건부
한 줄: 네임스페이스와 동결 계약(apps 금지·루트 허용목록·블루프린트 순서)은 테스트로 살아 있지만 계층 경계는 의존 방향으로 강제되지 않고, 통합은 네이버만 패키지이며 그마저 양방향 누수, 분해 거버넌스는 2026-04-15 에 멈췄다 — 6개월 안에 재가동하지 않으면 부적합 쪽으로 넘어간다.
- [리스크 · 높음 · 지금] 계층 경계가 디렉토리 이름일 뿐 의존 방향으로 강제되지 않는다 — 스펙이 금지한 services→web 이 8파일, api→web 53, services→api 15, services 의 Flask request 의존 19/311, 함수 안 지연 import 473곳(`grep -rnE '^\s{4,}from foms\.' foms --include=*.py | wc -l`; `foms/web/admin/naver_ingest.py` 한 파일 103)으로 순환을 버틴다. 방향을 단언하는 테스트 0(네임스페이스 계약은 apps.* 금지와 재수출 파리티만). [확인됨: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:315-322` · `foms/services/settlement_aggregation.py:55-60` · `tests/contracts/runtime/foms_namespace_surface_tests.py:108-110` · 계층별 grep 출력 8/53/15]
- [리스크 · 높음 · 지금] 횡단 관심사(인증·역할·팀·권한)가 web 계층과 서비스 6모듈·하네스 JSON 에 흩어져 권한 1건 변경이 22파일로 번진다 — ROLES·TEAMS 정의가 라우트 모듈에 있고 `foms.web.auth` 팬인 82파일, 회계팀 정리 커밋 d243c8e50 이 22파일(366+/158-). [확인됨: `foms/web/auth/routes.py:53` · `foms/web/auth/routes.py:60` · `foms/services/erp_permissions.py:13-23` · `git show --stat d243c8e50` 출력 22 files] → 읽기 권한 공백은 D6 참조.
- [리스크 · 높음 · 6개월] 외부 통합 격리가 네이버 하나뿐이고 그마저 web 6k ↔ services 15k ↔ JS·템플릿 6.3k 3벌 정본 분열(split-brain) — integrations 패키지는 '외부 HTTP 경계만' 이라 선언하지만 `fulfillment.py` 가 도메인 정책 상수를 갖고, services 가 web 의 private 함수를 역수입하며, web 모듈은 라우트 36·jsonify 110 으로 API 를 겸한다. 카카오(solapi)는 1,171줄 서비스 안 지연 import, 채널톡·지오코딩은 api 계층에서 requests 직접 호출. [확인됨: `foms/services/integrations/__init__.py:1-5` · `foms/services/integrations/naver_commerce/fulfillment.py:102` · `foms/services/integrations/naver_commerce/triage_count.py:118` · `foms/services/kakao_alimtalk.py:446-447` · `foms/web/orders/dashboard.py:107` · grep 출력 jsonify 110]
- [리스크+결핍 · 높음 · 지금] 분해 거버넌스가 2026-04-15 에 멈춘 채 문서만 남았다 — 스펙 임계치 500줄인데 `naver_ingest.py` 는 2026-08-13 196줄 → 09-06 5,999줄(24일), DECISIONS 6월 이후 31건 중 구조 결정 0, 분해 inventory 6개 중 4개 경로 부재. 동결 계약(테스트)만 살아남고 판단 규칙(문서)은 죽었다. [확인됨: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:392` · `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:546` · `docs/AI_STATUS.md:39` · `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md:28-33` · `git log --diff-filter=A -- foms/web/admin/naver_ingest.py` 출력 5dfbe4bd4] → CLAUDE.md apps/ 드리프트는 D8 참조.
- [리스크 · 중간 · 2년] 루트 `models.py`(77클래스)·`db.py` 가 실제 퍼시스턴스 계층이고 `foms/persistence` 는 4줄 재수출 껍데기 + 런타임 사용 0 인 designer 1,515줄 — web 22·api 50·services 153 파일이 루트 models 를 직접 import 해 모델 이동 시 225파일이 함께 움직인다(Step 8 보류의 실제 원인). `models.py` 자체가 `foms.services` 를 import(퍼시스턴스→서비스 역방향). [확인됨: `foms/persistence/main/models.py:3` · `models.py:18-19` · `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:258` · `tests/domains/test_designer_retired.py:1-10` · 계층별 grep 출력 22/50/153]
- [결핍 · 높음 · 지금] 변경 증폭이 실측으로 새고 있다 — 2026-08-15 이후 200커밋 평균 4.5파일(fix 68건은 5.8; `git log --since=2026-08-15 -n 200 --format=%h --shortstat | grep -E 'files? changed'` 를 awk 로 평균), 최근 400커밋 중 fix 108(27%), 단계 라벨 문구 1건이 7파일(0c66f6d61); `erp-order-shared.js` 6,085줄은 3개월 121커밋·fix 69·window 전역 98·소스를 문자열로 읽는 테스트 51개·작성자 1명. [확인됨: `git log --shortstat` 집계 출력 · `git show --stat 0c66f6d61` 출력 7 files · `tests/domains/test_erp_order_shared_form_scripts.py:1143`] → 핀·셸 3벌은 D5, 계약 세금은 D4 참조.
- 더 필요한 것(초안):
  - ① 의존 방향 래칫(ratchet) 계약 테스트(`tests/contracts/runtime/` 에 신설, 현재 위반을 baseline JSON 으로 동결·순증만 red, 표준 라이브러리만; 검증 = services 에 `from foms.web import x` 를 넣으면 그 테스트만 red).
  - ② ROLES·TEAMS·login_required·role_required 를 `foms/services/auth`(또는 platform)로 이동, 팀→범위 표를 레지스트리 1벌로(첫 걸음 = 상수 2개 이동 + 재수출 파리티 테스트; 검증 = `foms.web.auth` 팬인 82 감소·다음 권한 커밋 ≤5파일).
  - ③ 네이버 web 6k 를 페이지/JSON API/읽기모델 3분할, 정책 상수를 services 로, 카카오·채널톡·지오코딩·웹푸시는 `foms/services/integrations/<이름>/client.py` 로 수렴(첫 걸음 = `foms/services/integrations/naver_commerce/triage_count.py:118` 역수입 2함수 이동, 동작 변화 0).
  - ④ 파일 크기 래칫 + `CLAUDE.md:48`·`foms/README.md` 경로 정정 + inventory 현행화 + 컨텍스트 README 실채움.
  - ⑤ `structured_data` 키 레지스트리·스키마 버전 실사용(→ D3 ① 과 같은 항목).

### D3 데이터·마이그레이션 — 워커 판정: 조건부
한 줄: 주문 정본이 JSONB 한 문서이고 같은 사실의 사본을 호출 규약으로 사람이 동기화하는 구조라 사고가 두 달에 네 번 반복됐지만, alembic 체인(head 1·downgrade 94/94)·쓰기 감사 100%·오프사이트 백업이 갖춰져 있어 조회 축 승격과 복원 훈련이 붙으면 유지 가능 — RPO/RTO 숫자는 6개월 전 스펙에만, 복원 리허설 기록 0.
- [리스크+결핍 · 높음 · 지금] 주문 정본 JSONB + 사본(플랫 컬럼 9·레지스트리 5테이블·레거시 `orders.phone`)을 호출 규약(`sync_erp_flat_columns` 28곳/19파일·`flag_modified` 164곳·structured_data 참조 179파일)으로 동기화 — 쓰기 경로 하나가 규약을 빠뜨리면 목록 모집단에서 주문이 증발하거나 매칭이 실패한다. 실사고: 08-14 일괄 완료처리 AS 55건 증발, 09-03 AS 증발 2건(운영 5건 복구), 09-01 전화 세 사본 불일치로 네이버 자동 매칭 실패(활성 3,811건 중 숫자만인 phone 0), 레거시 stage 오염 477건 잔여. [확인됨: `foms/services/orders/erp_flat_audit.py:3-8` · `models.py:99-112` · `models.py:393-395` · `docs/guides/DATA_INCIDENT_RECOVERY.md:3-4` · `docs/AI_STATUS.md:17-18` · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:20-30` · grep 출력 28/164/179]
- [결핍 · 중간 · 지금] 주문 문서의 키·스키마 버전 정본이 없어 보존 목록과 lazy 마이그레이션을 사람이 서비스 코드 곳곳에서 유지한다 — 폼 저장이 문서 전체를 교체해 서버 소유 키를 지우는 경로가 그 증거: 보존 목록 `_OPERATIONAL_TOP_LEVEL_KEYS` 를 사람이 유지(빠뜨리면 알림톡 이력·네이버 연결 표식 소실 → 08-24 사고, 기록은 코드 주석뿐), `structured_schema_version` 참조 8곳 전부 =1, lazy 마이그레이션 114곳(`grep -rnE "lazy 마이그레이션|lazy migration|legacy_|_migrate_|normalize_legacy|coerce_legacy" foms/services/orders --include=*.py | wc -l`)이 서비스 코드에 산재, 키 레지스트리 상수 없음. [확인됨: `foms/api/erp_orders_structured.py:231-262` · `foms/api/erp_orders_structured.py:1940` · `foms/services/integrations/naver_commerce/promotion.py:378-380` · `foms/services/orders/as_log.py:3-4` · grep 출력 114]
- [결핍 · 중간 · 지금] 검색·권한 가시성 필터가 JSONB 전체를 문자열 캐스팅한 ILIKE + trigram 인덱스 하나에 결합(ilike 89곳·`@>` 0, containment GIN 은 소비자 0) — 인덱스 손실·값 형식 변화가 곧 권한 오류나 전체 스캔. 2026-08-07 운영 실측 문서: orders 3,698행에 heap 8MB·인덱스 28MB. [확인됨: `foms/services/erp_permissions.py:53-64` · `foms/services/erp_dashboard_search.py:79` · `migrations/versions/phase_d_trgm_indexes.py:47-54` · `migrations/versions/phase_c_indexes_concurrently.py:37-41` · `docs/plans/2026-08-07-audit-retention-analysis.md:65`]
- [리스크 · 높음 · 지금] 복구 능력이 문서·훈련이 아니라 도구에만 있다 — RPO 24h/RTO 4h 는 2026-03-20 스펙에만(DR 가이드·런북 0건), 실제 RPO 는 하루 1회 스냅샷(사고 시 17시간 전), 보존 6일, 통짜 복원 금지라 복구 = PITR fork + 선별 반영인데 JSONB 본문 복구 미지원(55건 중 20건 추론 복구), 오프사이트 백업은 6회 전패 후 2026-08-19 첫 성공, 복원 리허설 기록 0, 변경 원장 writer 9파일 vs Order commit 파일 40, 백업 stale 기준 30시간. [확인됨: `docs/specs/2026-03-20-production-backup-and-restore-plan.md:48-50` · `docs/guides/DATA_INCIDENT_RECOVERY.md:14` · `docs/guides/DATA_INCIDENT_RECOVERY.md:18-22` · `docs/guides/DATA_INCIDENT_RECOVERY.md:104-105` · `docs/AI_CHANGELOG.md:48` · `foms/services/backup_status.py:37` · `docs/harness/foms_audit_coverage_inventory.json`(AUDITED 179/EXEMPT 30/UNAUDITED 0)]
- [리스크 · 중간 · 6개월] 스키마 관리 경로가 alembic 밖으로 세 갈래 더 있고(predeploy 뒤 raw ALTER + `alembic_version` 직접 UPDATE, wdcalculator create_all + 수동 ADD COLUMN, raw DDL 러너) base 리비전은 빈 DB 에서 재생되지 않는다(왕복 검증 창 53 리비전); wdcalculator 두 번째 엔진·토폴로지 2종(SAME/SEPARATE)·링크 V1/V2 병행은 DR·복구 문서 3종에 언급 0. [확인됨: `predeploy.sh:22-26` · `tools/ops/ensure_schema.py:46` · `wdcalculator_db.py:44` · `wdcalculator_db.py:125-128` · `tests/postgres/test_migration_chain.py:12-22` · `models.py:2356-2360` · grep 출력 0] (D2 와 겹침 — 여기서만 다룬다)
- [리스크+결핍 · 중간 · 6개월] 환경 간 스키마 동기 보장이 약하다 — 9주에 68 리비전 속도, 마이그레이션은 web predeploy 만(워커 skip → 코드·스키마 순서 보장 없음), 다중 head 로 dev 빌드 2회 실패 → 단일 head 게이트, 계보 분기 병합 노드, 로컬 dev 는 head 보다 21 리비전 뒤·orders GIN 0(pg_trgm 은 설치됨)이라 운영 계획을 재현 못함, 테스트가 로컬 dev DB 를 drop_all 한 사고(08-23). [확인됨: `predeploy.sh:15-19` · `railway-worker.toml:4-7` · `tests/domains/test_alembic_single_head.py:4-7` · `migrations/versions/merge_prod_drawqueue_notifrole.py:6-12` · `migrations/env.py:138-151` · `docs/AI_STATUS.md:25` · `alembic current` 출력 drawqueue_00 (branchpoint)] → 사고 원장 분산은 D8 참조.
- 더 필요한 것(초안):
  - ① 주문 문서 스키마 정본 — 최상위 키 33종 레지스트리(소유자·읽는 화면·플랫 사본 여부), 보존 목록을 레지스트리에서 생성, `structured_schema_version` 1→2 승격 함수 + 저장 검증기(첫 걸음 = 33개 키 표 1장 + `foms/api/erp_orders_structured.py:231` 보존 목록을 생성 상수로 교체; 검증 = 미등록 키 저장 시 계약 red, 저장 1회 후 `naver_linked`·알림톡 이력 잔존 green).
  - ② 조회·권한 축 승격 + 사본 동기의 DB 강제(생성 컬럼/트리거/단일 command 경로; 첫 걸음 = `erp_phone_digits` 생성 컬럼 마이그레이션 + `orders.phone` 비교 읽기 지점 제거; 검증 = `tools/ops/audit_erp_flat_columns.py`·`tools/ops/audit_as_axis_drift.py` 드리프트 0 이 2주 연속, EXPLAIN 에서 권한 필터가 btree/tsvector).
  - ③ 복구 훈련 운영화 — DR 문서에 RPO/RTO 숫자, 분기 1회 스테이징 fork 복원 리허설 기록, data_doctor 를 `order_field_changes` 기반 본문 복구로 확장, FOMS-DEV 도 최소 백업.
  - ④ 스키마 경로 단일화 + base 스쿼시 + 워커 기동 시 head==current 게이트(첫 걸음 = 빈 DB 전체 재생 테스트를 xfail 로 추가).
  - ⑤ 데이터 사고 원장 통합(→ D8 ③).

### D4 테스트·CI·품질 시스템 — 워커 판정: 조건부
한 줄: CI 는 2026-08-26 수술 뒤 전 워크플로 2분 안팎·최근 30런 초록이고 수집 9,879건(58275b7e5 재측정 9,913)의 47%(워커 분류, 셈법 미기재·재측정 필요)가 HTTP 경로를 실제로 때려 커밋 속도를 막지는 않지만, CI 빨강 표본 19건 중 11건이 등재·핀 계약이 스스로 만든 것이고 보안 레인 0·SQLite/PG 사각·'초록' 정의 3겹에 그 함정 지식이 저장소 밖 메모리에만 있어 계약 다이어트와 사각 채우기 없이는 두 번째 개발자 합류 시점에 유지가 어렵다.
- [리스크+결핍 · 높음 · 지금] 계약 테스트가 변경 세금을 구조적으로 부과한다 — 기능 1건이 초록이 되려면 템플릿 핀 → 테스트 안 핀 리터럴(52파일 90곳) → docs/harness 인벤토리 JSON(8월 이후 203커밋) → ci.yml 서브셋 등재까지 최대 4곳. 8월 이후 핀 변경 커밋 254건 중 138건이 테스트 핀도 함께 고침. CI 빨강 표본 19건: 등재 누락 8·핀 계약 3·PG 레인 전용 3·CI 인프라 2·세션 충돌 1·flaky 1·실제 결함 1(42e9cde89) — 표본 추출 `git log --since=2026-08-01 --no-merges --format='%h %s' | grep -iE 'CI red|CI 빨강|red 해소|red 복구|\(ci\)|CI 실패' | sort -u -k2` → 19건, 유형 분류는 워커 수작업. 2026-08-03 조사('18건 중 8건')는 docs 에 없고 ps1 주석에만. [확인됨: `scripts/ops/pre_push_smoke.ps1:221-222` · `docs/AI_CHANGELOG.md:47` · `tests/domains/test_docs_facing_registry.py:1-9` · `git log -G'\?v='` 집계 출력 254/162/138] → 핀 구조 자체는 D5 참조.
- [리스크+결핍 · 높음 · 지금] '초록' 의 뜻이 세 겹 — 로컬 smoke 는 24개 타깃 서브셋(전체 9,879 대비)이고 훅은 push 를 smoke 로 막지 않으며(guard_policy 에 smoke 언급 0, 속도 원장 자백 'exit 1 인데 ; 로 이어 푸시'), perf-gate 는 deploy push 에서 권고 전용(advisory, 예산 초과도 exit 0)·`cancel-in-progress` 와 ci_watch fail-closed 가 공존, ci_watch 는 '런 없음' 을 green 취급. 승격 PR 이 본 스위트를 한 번도 안 돌아 운영만 터진 사고 3건 뒤에야 production PR 트리거 추가. [확인됨: `scripts/ops/pre_push_smoke.ps1:200-206` · `docs/plans/2026-08-26-ci-speed-ledger.md:95-98` · `.github/workflows/perf-gate.yml:3-7` · `.github/workflows/perf-gate.yml:24-26` · `.github/workflows/perf-gate.yml:55-69` · `tools/harness/ci_watch.py:404` · `.github/workflows/ci.yml:7-11`]
- [리스크 · 중간 · 지금] SQLite 본 레인 + 선택 가입(opt-in) PG 레인 이중 구조의 사각 — FK 미강제·JSONB 연산자·EXPLAIN 이 로컬 기본 실행에서 안 보이고(EXPLAIN 테스트 10파일 전부 tests/postgres), PG 레인은 orders·security 만 두텁고 integrations 6·files 2, PG 전용 빨강 3건(9bc598467·569e4c151·80b4945ba). [확인됨: `.github/workflows/ci.yml:101` · `.github/workflows/postgres-lane.yml:3-5` · `tests/postgres/conftest.py:142` · `tests/conftest.py:87-88` · `tests/postgres_guard.py`]
- [리스크+결핍 · 중간 · 6개월] 사각의 유형 분포 — 보안 전용 레인 0(보안 성격 17파일이 domains/postgres 에 산재), playwright visual 5파일은 CI 밖·linux 기준선은 수동 dispatch 뿐(PNG 회귀 게이트 아님), 커버리지 계측 0, 하네스 보호 462건 > 성능 89 + 계약 68; 유일한 8월 이후 사고의 원인은 '테스트는 있었으나 픽스처가 운영 형태가 아니었다'. 정적 도달 대용치: foms 모듈 394 중 19(`foms/services/orders/upload_authz.py` 등)·템플릿 24%·JS 11% 가 테스트 텍스트 미참조(커버리지 도구 없어 확인 불가). [확인됨: `ls tests/security` 출력 · `.github/workflows/visual-baseline-linux.yml:3-4` · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:101-108` · collect-only 분포 출력] → 의존성 스캔 0 은 D1 참조.
- [리스크 · 중간 · 6개월] 테스트 체계 지식이 저장소 밖(개인 메모리·ps1 주석·ci.yml 주석)에 집중 — `tests/README.md` 는 2026-04 Wave 7 용어로 postgres·visual·performance 레인을 말하지 않고, TEST_GUIDE 는 화면 클릭 절차서, PRE_PUSH_SMOKE 에 '사각·서브셋' 언급 0, pytest 설정은 08-26 에 처음 생김. 8월 이후 테스트 파일 +266, tests/domains 단일 평면 439파일. [확인됨: `tests/README.md:9-16` · `docs/guides/TEST_GUIDE.md:1-3` · `pytest.ini:3-10` · `.github/workflows/ci.yml:26-31` · `docs/guides/PRE_PUSH_SMOKE.md` grep 출력 0건]
- 더 필요한 것(초안):
  - ① 단일 '초록' 정의 + 로컬=CI 동형 게이트(smoke 기본을 전체 스위트 `-n auto --dist loadfile` 로, 로컬 PG 있으면 tests/postgres 연속 실행, guard_policy 가 push 앞에 smoke 성공 스탬프 요구, ci_watch 가 '측정 초록' 과 '예산 초록' 구분; 검증 = 4주간 등재·핀·PG 전용 CI red 0, 30런 전 워크플로 success).
  - ② 계약 다이어트 — 핀 리터럴 90곳을 자산 매니페스트 조회로, 인벤토리는 스캐너 산출 대조만, mutation 등재는 데코레이터 자동 등록(첫 걸음 = `erp-pro.css` 핀 하나 파일럿; 검증 = `grep -rn '?v=2026' tests --include=test_*.py | wc -l` 90→0).
  - ③ 사각 레인 3종 — `tests/security` 권한 매트릭스(팀 × 라우트 HTTP 실검증)·pip-audit 권고 전용(→D1)·`--cov=foms` 아티팩트(문턱 없음, pytest-cov 는 설치 전 보고).
  - ④ 실기기·SW·PNG 자동 레인(visual-baseline 을 production PR 트리거로, 배포 후 스테이징 SW 스모크).
  - ⑤ `tests/README.md` 현행화 — 6 레인 대응표 + 사각 + 메모리 함정 3종 이관(검증 = 새 세션이 README 만 읽고 '핀 바꾸면 어떤 테스트', 'import 1줄이 왜 빨강', 'PG 레인 skip 조건' 에 앵커 포함 정답).

### D5 프론트엔드·자산 파이프라인 — 워커 판정: 조건부
한 줄: 번들·모듈·린트 없이 130k 줄 Vanilla JS 를 계약 테스트 136파일·수동 날짜 핀·SW 캐시로 버티고 있으나, 병렬 세션이 같은 날짜 핀을 고르는 사고가 9일에 4번 반복되고 셸 3벌 + 태블릿 레이어가 게이트 행렬로 갈라져 같은 주문 폼이 3벌 배선돼 있다 — 해시 기반 캐시 무효화와 셸 공용 계층 없이는 변경 증폭 세금(커밋 22.6% 가 핀을 건드림)이 커밋 속도와 함께 선형으로 는다.
- [리스크+결핍 · 높음 · 지금] 캐시 무효화가 사람이 고르는 날짜 핀에 묶여 있다 — SW `staticCacheFirst`(URL 키·TTL 5분)와 `?v=` 가 결합돼 '내용이 바뀌면 사람이 핀을 올린다' 는 규약 하나에 운영 신선도가 걸리고, 미들웨어 주석 스스로 'CSS/JS are NOT hashed'. 9일에 4번 '운영이 같은 핀으로 다른 자산을 서빙'(6e8a6f75e·c956fc600·603a4a92c·156608706; 5d3464018 본문 "날짜 핀은 여러 세션이 같은 날 같은 값을 고르므로 필연"), 6월 이후 핀을 건드린 커밋 627/2,773(22.6%), 핀 리터럴 테스트 52파일 90곳(`grep -rn '?v=2026' tests --include=test_*.py | wc -l` · `grep -rl '?v=' tests --include=test_*.py | wc -l`; test_ 접두 없는 파일까지 넓히면 `grep -rn 'v=2026' tests | wc -l` 163 · `grep -rl '?v=' tests | wc -l` 136), `CACHE_VERSION` 도 사람이 올리고 테스트가 리터럴 고정, 핀 갱신 도구 0. [확인됨: `static/sw.js:10-17` · `static/sw.js:82-93` · `foms/platform/app_factory.py:60-69` · `tests/domains/test_erp_runtime_shell_js_contract.py:209-212` · `git show -s 5d3464018` 출력 · grep 출력 627/163]
- [리스크+결핍 · 높음 · 지금] 셸이 하나의 레이아웃 계약이 아니라 게이트 행렬(legacy·v2·v3·태블릿 레이어·독립(standalone) 문서 31개)로 갈라져 같은 기능을 셸마다 따로 배선한다 — 자산 로드는 layout_head if 사슬(템플릿 게이트 `erp_mobile_v2_enabled` 69곳 + `shell_variant` 19곳), 하단 내비·코호트 규칙은 v2·v3 파셜에 사본, 주문 폼 3벌(PC 697줄·모바일 651줄·태블릿 2,873줄이 '이 페이지엔 미로드라 자체 구현' 미러 주석 23곳), 셸 누락·누출 봉합 커밋 12건(6dde61f04 'v3 셸에서 전 기능 미로드 실사고'), v2/v3 자산 동등성 테스트 0, Bootstrap 5.3.0-alpha1 과 5.1.3 공존. [확인됨: `foms/services/feature_flags.py:257-262` · `templates/partials/shared/layout_head.html:176-180` · `templates/partials/shared/layout_head.html:210-217` · `templates/partials/shared/erp_mobile_shell.html:1-6` · `templates/partials/v3/foms_app_shell_v3.html:5-10` · `static/js/foms/tablet-measure-form.js:215` · `docs/AI_CHANGELOG.md:39` · `templates/partials/shared/layout_scripts.html:89-91` · `foms/services/context_processors.py:310-316` · `templates/measurement/map_view.html:112`]
- [리스크+결핍 · 중간 · 6개월] 모듈 시스템 없는 전역 네임스페이스와 로드 순서 의존이 방어 코드를 증식시킨다 — ESM import 0·`type="module"` 0·package.json/eslint 0, `window.*` 전역 467개(`grep -rhoE 'window\.[A-Za-z_$][A-Za-z0-9_$]* *= ' static/js templates --include=*.js --include=*.html | sed -E 's/ *= //' | sort -u | wc -l`; 6k 파일 하나가 108), 프래그먼트 스왑이 스크립트를 재실행해 파일마다 멱등 재정의 214·싱글턴 가드 273·typeof 함수 가드 749(세 수치는 셈법 미기재·재측정 필요)를 손으로 달고 G4 가드가 그 누락을 뒤쫓는다; 전역 충돌 실사례 `USE_DIRECT_UPLOAD`. 6k 파일 보호는 문자열 포함 계약(1,817줄)뿐이고 node 실행 계약은 wdcalculator 57 대 erp/orders 1. [확인됨: `static/js/orders/erp-order-shared.js:1-4` · `static/js/runtime/erp-shell.js:309-312` · `static/js/foms/fragment-loader.js:11-16` · `tests/performance/test_perf_regression_guard.py:9-12` · `templates/partials/shared/layout_head.html:1263-1265` · `tests/contracts/wdcalculator/_node_runner.py:1-5` · grep 출력 0/467/749]
- [리스크+결핍 · 중간 · 6개월] 인라인 규칙이 문서 선언과 국소 테스트로만 존재한다 — `style=` 687(재측정 일치)·인라인 script 템플릿 46·300줄 초과 12개(map_view 1,672·layout_scripts 1,271·edit_order 1,269), ssot_lint 는 docs/design 의 낡은 문구 9개 정규식만 검사, 인라인 금지 assert 는 화면 테스트 11개, 공용 파셜 2개(layout_head 1,266줄·layout_scripts 1,742줄)가 인라인 CSS 약 500줄·JS 1,271줄을 품은 최대 핫스팟(6월 이후 124·75커밋), `!important` 1,529회. 규칙 실패라기보다 집행 장치 부재. [확인됨: `tools/design/ssot_lint.py:25-38` · `scripts/ops/pre_push_smoke.ps1:200-206` · `templates/partials/shared/layout_head.html:251` · `templates/partials/shared/layout_scripts.html:369` · 파이썬 정규식 집계 출력 46/64]
- [리스크+결핍 · 중간 · 6개월] 현장(태블릿·iOS 웹뷰) 전략이 시스템이 아니라 함정 메모와 사후 봉합으로 존재한다 — 오프라인은 설계상 죽은 경로(쓰기 큐 OFF, 스냅샷은 사용자 무관 최신 20건 + PII + `no-store` 라 캐시 불가, 플래그 기본 OFF 를 테스트가 고정), 무스타일 렌더 방어 3겹(SW 재시도 → 실기기 재발 → head 인라인 CSS 재시도), RUM 은 4지표를 메트릭×일자로만 집계해 셸·기기 회귀 구분 불가, a11y 테스트 0, 태블릿 전용 JS 약 170KB 가 데스크톱 포함 전 페이지에 로드, 하트비트가 클라이언트당 시간당 약 260회 재검증. [확인됨: `static/sw.js:24-25` · `foms/api/foms_offline.py:26-32` · `foms/api/foms_offline.py:48` · `foms/services/context_processors.py:319` · `tests/domains/test_p2_gate.py:173` · `foms/services/rum_aggregate.py:358` · `.github/workflows/rum-daily.yml:10-11` · `templates/partials/shared/layout_scripts.html:80-96` · `foms/services/common/fragment_revalidation.py:5-6` · `docs/AI_STATUS.md:21`]
- 더 필요한 것(초안):
  - ① 콘텐츠 해시 자산 매니페스트(파이썬 빌드, npm 불필요: `tools/assets/build_manifest.py` → `static/asset-manifest.json`, Jinja 헬퍼 `asset_url()`, erp-pro @import 자식 재작성, predeploy 1회 실행, smoke 에서 워킹트리 일치 검사; 첫 걸음 = `templates/orders/partials/erp_order_js.html`(자산 32개) 한 파일 전환; 검증 = 한 바이트 변경 → URL 해시 변경 단위 테스트, 4주간 '같은 핀 다른 자산' 커밋 0).
  - ② 셸 공용 계층 — 내비·코호트·변형별 자산 목록을 파이썬 SSOT 1벌로, 템플릿은 variant 인자 매크로 1개, 셸 동등성 테스트(ERP 9경로 × 3변형 자산 집합 대조; 첫 걸음 = v2/v3 내비 중복 블록을 매크로 1개로).
  - ③ 주문 폼 코어 로직(금액 합계·자유입력 파싱·변환 텍스트)을 셸 무관 `static/js/orders/erp-order-core.js` 로 추출 + node 실행 계약(검증 = 태블릿 미러 주석 23 감소, PC/태블릿 출고가·잔금 동일).
  - ④ 프론트 래칫 게이트(`style=`·인라인 script 줄수 baseline 증가 시 실패, 전 JS `node --check`, 이후 eslint; 첫 걸음 = style= 카운트 래칫 하나).
  - ⑤ 현장 전략 결정 — 오프라인 큐 채택/폐기 ADR, RUM 키에 셸·기기 버킷, ERP 3경로 axe 스모크.

### D6 보안·권한·개인정보 — 워커 판정: 조건부
한 줄: 쓰기 권한은 매니페스트 기반 SSOT 게이트로 닫혀 있고 fail-open 목록도 닫혀 있으며 고급 통제(운영 승인·서명 키 회전·감사 커버리지 100%)가 실재하지만, 읽기(고객 개인정보 조회)는 로그인만 하면 전 주문이 보이는 구조에 판정 지점이 4곳 이상 흩어져 있고, CVE 스캔·CSP·로그인 잠금·PII 보존/마스킹 정책이 비어 있으며 레이트리미터 fail-open 이 무로그 기본값이라 기본 통제 층을 채워야 유지 가능하다.
- [리스크+결핍 · 높음 · 지금] 권한 SSOT 가 쓰기(POST/PUT/PATCH/DELETE, 매니페스트 209 라우트)에만 있고 읽기는 로그인 하나로 전 주문 열람 — '내 것' 필터는 `?mine=1` 옵트인, 전역 before_request 는 사용자만 세팅하고 기본 거부 없음, 시공팀 제한 훅은 스스로 '인가 경계가 아니다'(API 302 로 알림·푸시가 무음이던 사고 기록), VIEWER 거부는 코드 전부 쓰기 쪽(읽기 거부 0), `user_can_read_order` 호출 3곳, `switch_user` 는 국소 게이트, 외주 시공 기사는 계정이 아니라 이름 문자열, 정산 게이트는 별도 모듈 — 회계팀 1건이 팀 게이트 8곳. [확인됨: `foms/services/orders/order_mutation_policy.py:56` · `foms/services/orders/order_mutation_policy.py:579-584` · `foms/services/common/erp_mine_filter.py:17-27` · `foms/platform/http.py:214-220` · `foms/platform/http.py:238-248` · `foms/services/erp_permissions.py:294-296` · `foms/web/auth/routes.py:385-390` · `docs/AI_STATUS.md:19` · `docs/harness/foms_order_mutation_policy_manifest.json`(guard 204/exempt 5)] → 권한 변경 증폭은 D2 참조.
- [리스크 · 높음 · 지금] fail-open 이 사업 판단 없이 기본값으로 남아 있고 핵심 지점은 열려도 관측되지 않는다 — Redis 장애 시 레이트리미터 `swallow_errors` + 메모리 폴백(Web 복제 2면 한도가 프로세스별로 쪼개짐, 로그 0), `/login` 전용 한도·잠금·MFA 0(기본 한도 1200/h 만, `limiter.limit` 10곳은 알림·푸시·RUM), 공유 링크는 레이트리밋을 'fail-open 보조 방어선' 으로 선언, 비밀번호 정책은 legacy 잔존 동안 WARN, 인벤토리 587 catch 중 무로그 216(auth 6·platform 5), 서명 키·auth-rate 는 env root 없으면 legacy 경로로 byte-identical(운영 engaged 여부 문서 0). [확인됨: `foms/services/rate_limit.py:22-37` · `foms/services/rate_limit.py:58-70` · `foms/api/share.py:7-9` · `foms/services/security/password_policy.py:11-14` · `foms/services/security/signing/signing_keys.py:6-11` · `docs/harness/foms_failopen_inventory.json` 분포 출력(FAIL_CLOSED 35·INTENTIONAL 17·LOG_AND_CONTINUE 355·SWALLOW 180) · `tests/domains/test_failopen_inventory.py:1-16` 13 passed]
- [리스크 · 높음 · 6개월] 의존성·브라우저 경계에 체계적 방어가 없다 — CSP·HSTS 등 보안 헤더 앱 코드 0, XSS 게이트는 4파일 '같은 줄 innerHTML+사용자 필드' 휴리스틱이고 싱크 인벤토리는 2026-07-24 생성 후 커밋 1건인데 그 뒤 static/js 271·templates 475 커밋, innerHTML 496·`|safe` 28. 반면 웹훅 HMAC·비밀 리터럴 스캔·API 오류 단일 관문·공유 토큰(256bit 해시 저장·30일·회수)·업로드 티켓(900초·서버 파생 키)은 견고. [확인됨: `tests/domains/test_stored_xss_sinks.py:181-193` · `docs/harness/foms_untrusted_dom_sinks.json:3-4` · `docs/harness/foms_secret_literal_allowlist.json:3-6` · `foms/services/orders/upload_ticket.py:9` · `foms/services/security/ops_approval.py:1-6` · grep 출력 CSP 0/innerHTML 496] → CVE 스캔·dependabot 0 은 D1 참조.
- [리스크+결핍 · 높음 · 지금] 개인정보 수명주기 정책이 문서·코드 어디에도 없다 — 고객 PII 컬럼(customer_name·phone·address) 보존·익명화 코드 0, 운영 실측 문서: 감사 `masked_` 필드 30.6% 에 전화 패턴·ADDRESS_CHANGED 에 주소 원문('법적 임계점'), 감사 purge 기본(security_logs 3년·access_logs 2년) vs 사용자 결정 '영구 보존' 드리프트, Sentry·로그 redaction 은 비밀값 키 이름·토큰 패턴만(전화·주소 통과), 공개 공유 견적 본문이 전화·주소 렌더(토큰 30일), R2 사진 lifecycle 언급 0, docs/guides 에 보안·개인정보 가이드 0. 접근 기록 자체는 존재(access_logs 독립 커밋·SecurityLog 130곳). [확인됨: `models.py:27-29` · `docs/plans/2026-08-07-audit-retention-analysis.md:4-6` · `tools/ops/purge_audit_logs.py:9-20` · `docs/plans/2026-08-13-order-change-retention-measurement.md:5-7` · `foms/platform/sentry_setup.py:54-62` · `foms/services/error_logging.py:36-50` · `foms/services/order_share.py:30` · `foms/services/audit_writer.py:383-384` · grep 출력 0]
- [리스크+결핍 · 중간 · 6개월] 보안 지식이 1,699줄 감사 보고서(패킷 60개)와 하네스 JSON 에 집중 — DECISIONS 에 AUTH-01 0건, 운영 env 정본·start.sh 에 서명 키 env 0, `tests/security` 는 Designer 폐기 잔재 0바이트에 보안 테스트 74개 산재(README 분류에 '보안' 없음; 74 는 셈법 미기재·재측정 필요, 파일명 기준은 17 — D4 참조), 인벤토리 파일 하나가 3개월 161커밋. [확인됨: `docs/plans/2026-07-22-foms-full-system-bug-audit-report.md` 1,699줄 · `docs/harness/foms_untrusted_dom_sinks.json:3` · `docs/guides/RAILWAY_ENV_VARS.md` grep 0 · `git log --since=2026-06-01 -- docs/harness/foms_failopen_inventory.json` 161] → 테스트 분류 부재는 D4 참조.
- 더 필요한 것(초안):
  - ① 읽기 권한 SSOT — AUTH-01 과 같은 모양의 READ 매니페스트(endpoint→policy_id)를 GET·프래그먼트·내보내기에 적용, VIEWER 읽기 범위·외부 협력사 역할·'내 것' 기본값을 정책 데이터로(첫 걸음 = 전화·주소를 응답하는 GET 목록화 + 정책 3종 초안; 검증 = 미등재 GET 을 정적 게이트가 red, VIEWER 로 `/api/orders` 403 JSON 계약).
  - ② 기본 통제 층 — CI pip-audit report-only(→D1)·`auth.login` 전용 한도 + 실패 N회 잠금·`Content-Security-Policy-Report-Only`(검증 = 스테이징 잘못된 비밀번호 11회 → 429 + SecurityLog 행).
  - ③ 개인정보 수명주기 정책 1장(docs/guides: 주문 PII·현장 사진·감사 로그·공유 링크·백업 보존기간과 근거) + 감사 detail/message 전화·주소 마스킹 헬퍼 + 계약 테스트 + 공유 본문 최소화 + R2 lifecycle 결정.
  - ④ fail-open 사업 판단 원장 — 인벤토리에 business_impact/observed_by 필드, 무관측 열림 0 목표(첫 걸음 = `foms/services/rate_limit.py` 폴백 시 warning 로그 + Sentry 이벤트 1건).
  - ⑤ 보안 거버넌스 정리 — DECISIONS 에 보안 결정 5건 등재, `tests/README.md` 보안 계층 + 게이트 10개 링크, 위협 모델 1페이지.

### D7 운영·배포·관측·회복력 — 워커 판정: 조건부
한 줄: 운영은 돌아가지만 감독·경보·정본 세 축이 전부 '사람이 보고 있을 때' 에 기대고 있다 — 워커 1대 안의 무감독 루프 5개는 죽어도 신호가 없고, 배포 설정 정본은 저장소 밖(대시보드·비공개 저장소)에 있으며, 롤백은 문서·훈련 없이 AI_STATUS 한 줄에 있다; downgrade 94/94·PITR 도구·Sentry 운영 가동이 있어 감독·경보·env 정본 세 가지를 갖추면 회복 가능.
- [리스크 · 높음 · 지금] 단일 워커 컨테이너에 큐 + 감독 없는 백그라운드 루프 5개가 동거 — 루프는 `&` 로 뜨고 셸은 `exec rq worker` 로 대체돼 감시 주체가 없고(wait/trap/supervisor 0), 각 루프는 `except Exception` 으로만 생존하며 하트비트를 쓰지 않는다. 평일 16:50 자동 발송(되돌릴 수 없음)·5분 주문 수집·정산 동기화·긴급 에스컬레이션이 전부 여기 걸려 있다. 같은 저장소의 SIDEFX 아웃박스는 임대(lease)·하트비트·닫힘 기본(fail-closed) 준비 판정(readiness)을 갖췄지만 지오코딩·스토리지 삭제에만 쓰인다 — 백그라운드 설계가 두 세대로 갈라져 사업상 중요한 쪽이 약한 세대에 있다. [확인됨: `start.sh:23-26` · `start.sh:74` · `scripts/maintenance/run_notification_escalation.py:102-112` · `scripts/maintenance/run_naver_auto_dispatch.py:135-146` · `foms/services/sidefx_worker.py:495-500` · `tools/ops/check_sidefx_readiness.py:1-6` · `docs/AI_STATUS.md:9` · grep 출력 wait_for_redis 1건뿐]
- [리스크+결핍 · 높음 · 지금] 워커 재배포 = 큐 전면 정지이며 되돌릴 수 없는 자동 발송의 '끄기 스위치' 가 바로 그 재배포에 묶여 있다 — 2026-08-31 실사례 47집 852초 지연, 재배포 안전 판정 도구는 있으나 훅·CI 배선 0(수동), 재배포에 잘린 정산 실행 행이 RUNNING 잔류(운영 10·11)인데 회수 코드 0, RQ 실패잡은 자동 재시도 없음(`Retry` 0, 2,544건 정리 이력). [확인됨: `tools/ops/check_worker_redeploy_safe.py:1-12` · `docs/AI_STATUS.md:20` · `docs/AI_STATUS.md:59` · `docs/plans/2026-09-04-settlement-tab-cfo-review-prompt.md:53` · `foms/services/integrations/naver_commerce/settle_sync.py:819-823` · `tools/ops/rq_failed_jobs.py:3-5` · `docs/AI_STATUS.md:98` · `start.sh:32-33`] → 스택 제약 관점은 D1 참조.
- [리스크+결핍 · 높음 · 지금] 배포 설정의 정본이 저장소 밖에 있다 — Railway 가 Config as Code 를 폐기해 toml 3벌은 사문('기존 서비스 확인 필요' 미해소), 워커 시작 명령은 `railway-worker.toml`(루프 0, 2026-02-22 1커밋)과 `start.sh`(루프 5, 14커밋) 두 벌로 모순, healthcheck 는 web 대시보드에만, IaC(`.railway/railway.ts`) 없음, 서비스 구성·env 스냅샷은 비공개 저장소 topology.json. 배포 가이드는 '채팅 시스템 배포 가이드(Quest 14)'·eventlet `-w 1`·init_db 를 말하는 2026-04 이전 세대. [확인됨: `docs/plans/2026-08-31-geocode-prefetch-restore-ledger.md:392-404` · `docs/AI_STATUS.md:68` · `railway-worker.toml:4-7` · `railway.toml:14-18` · `docs/guides/DISASTER_RECOVERY.md:4` · `docs/guides/DISASTER_RECOVERY.md:19-20` · `docs/guides/DEPLOYMENT_GUIDE.md:1` · `docs/guides/DEPLOYMENT_GUIDE.md:66-69` · `git log -- railway-worker.toml start.sh` 출력]
- [리스크 · 높음 · 지금] '사람에게 알리는' 경보 경로가 코드 어디에도 없다 — `/healthz` 는 DB·세션을 일부러 안 건드리는 liveness(워커·Redis·큐 상태 없음), `init_sentry` 호출처는 web app_factory 뿐(워커는 app.py 를 import 하지 않고 잡·도구·루프에 sentry 0), Sentry 알림 규칙은 사용자 잔여, 워크플로 7개에 slack/webhook/alert 0(rum-daily 는 하루 1회 p95 만), 백업 stale 은 화면 표시용, 워커 0대는 사용자가 '지금 수집' 을 누를 때 드러나고, 네이버 앱 만료 알림은 사람이 날짜를 입력해야만(미입력=무알림). Redis 부팅 레이스로 13시간 정지(08-07). [확인됨: `foms/api/health.py:7-10` · `foms/platform/app_factory.py:168` · `foms/services/jobs/tasks.py:25-27` · `docs/AI_STATUS.md:89` · `.github/workflows/rum-daily.yml:3-4` · `foms/services/backup_status.py:37` · `foms/services/integrations/naver_commerce/app_expiry.py:5-7` · `foms/services/integrations/naver_commerce/app_expiry.py:42-45` · `tools/ops/wait_for_redis.py:3-9` · grep 출력 sentry 0/alert 0]
- [리스크+결핍 · 중간 · 6개월] 롤백이 코드·마이그레이션·워커 세 축에서 문서·훈련으로 검증된 적이 없다 — guides·runbooks 의 롤백은 플래그 OFF 2건 + 데이터 복구 1건, '롤백은 DB 먼저→코드 나중(반대면 Can't locate revision 으로 이후 전 배포 파산)' 은 AI_STATUS 완료 기록 한 줄, 마이그레이션은 web predeploy 만이라 코드 롤백 시 web·워커 스키마 버전이 어긋나는 창, PITR 은 fork 만, 복구 리허설은 '분기 수동' 이고 기록은 비공개 저장소, cherry-pick 승격이라 되돌릴 기준점 판별이 사람 몫. [확인됨: `docs/AI_STATUS.md:97` · `docs/AI_STATUS.md:83` · `docs/runbooks/release-gate-readiness.md:91` · `docs/runbooks/mobile-v2-railway-ops.md:91-93` · `predeploy.sh:15-19` · `tools/ops/railway_pitr.py:1-10` · `AGENTS.md`] → 백업 RPO·리허설은 D3 참조.
- [결핍 · 높음 · 지금] 환경변수 정본 공백이 이미 사고를 냈다 — 문서 31줄·표 0행(2026-04-15 이후 미갱신, DATABASE_URL·R2·WD 만) vs 코드 env 키 79(FOMS_ 접두 25 — 두 셈법은 §2.6), SIDEFX 서비스에 `KAKAO_REST_API_KEY` 부재가 DEAD 1,188행 사고 트리거('조사가 서비스 3개만 봤다'), env 존재 검사 도구는 4그룹만 보고 predeploy/start/CI/훅 배선 0, 문서가 권하는 `scripts/ops/railway_bootstrap.py`(create tables)는 alembic 소유 원칙과 충돌, 운영 사고 4건(13시간 정지·852초 지연·DEAD 1,188·실패잡 2,544)이 docs/incidents 밖. [확인됨: `docs/guides/RAILWAY_ENV_VARS.md` 31줄 · `docs/AI_STATUS.md:65` · `tools/ops/check_deploy_secrets.py:1-8` · `foms/services/app_init.py:154-160` · grep 출력 79/25/0] → 사고 원장 분산은 D8 참조.
- 더 필요한 것(초안):
  - ① 루프 5개를 하트비트·준비 판정(readiness) 감독 아래로(SIDEFX 와 같은 세대: 각 tick 에 `upsert_heartbeat` 재사용, 일반화한 준비 판정 CLI 가 하트비트 나이·큐 적체·실패잡·RUNNING 잔류를 닫힘 기본(fail-closed)으로 판정; 시각 창 루프는 Railway cron 서비스 이관 검토. 첫 걸음 = `scripts/maintenance/run_naver_auto_dispatch.py` tick 에 하트비트 1줄; 검증 = 루프 kill 60초 안에 준비 판정 exit 1).
  - ② 사람에게 닿는 경보 경로 1개 — rq 워커에도 `init_sentry`, Sentry 규칙 완료를 DECISIONS 에, rum-daily 패턴의 시간당 워크플로가 `/healthz`·준비 판정·`rq_failed_jobs.py --json`·백업 심박을 폴링해 임계 초과 시 job fail(검증 = 스테이징 실패잡 1건 → 1시간 안 GitHub 알림).
  - ③ 배포 정본을 저장소로 — 서비스별 startCommand·healthcheck·cron·복제·필수 env 키(값 제외)를 한 파일로, 사문 toml 제거 또는 '사문' 헤더, RAILWAY_ENV_VARS 를 그 파일에서 생성, `start.sh` FOMS_ 집합 ⊆ 문서 집합 계약 테스트, `check_deploy_secrets.py` predeploy 배선(첫 걸음 = `docs/AI_STATUS.md:68` 미해소 확인을 Railway API 조회로 닫고 DECISIONS 기록).
  - ④ 롤백 런북 + 분기 스테이징 리허설(DB 먼저→코드 나중, 확장 전용(expand-only) 규칙, 재배포 전 안전 판정 필수, PITR fork 링크, cherry-pick 기준 SHA 찾는 법; CI-DOCSCOPE 등재).
  - ⑤ 재배포·장애에 잘리는 상태의 공통 회수 규약 — 실행 이력에 임대(lease)/하트비트 + 기동 시 회수 스윕(`ABORTED_RESTART`), RQ `Retry` 정책 또는 실패잡 수를 준비 판정 지표로.

### D8 개발 시스템(DX·하네스·문서·프로세스) — 워커 판정: 조건부
한 줄: 하네스는 의식이 아니라 실제로 막고 있으나(1주일 셸 가드 deny 70건·사고 기반 DECISIONS 앵커·Stop 게이트), 정책 정본 4벌이 코드 구조(apps/ 드리프트)와 어긋나고 지식 색인이 2026-06-17 에 멈춰 이후 plans 133·specs 61 이 색인 0 이며, 규칙이 가리키는 스킬 4종이 저장소 밖(untracked)이고 README 부팅 절차가 없는 파일을 가리키며, docs/harness JSON 이 운영 런타임 의존성이라 스테이징 배포 실패가 실증된 상태 — 정본 단일화·색인 자동화·런타임 매니페스트 분리로 유지 가능.
- [리스크+결핍 · 높음 · 지금] 정책 정본이 4벌 + 보조 문서로 퍼져 있고 정본 자체가 코드 구조를 따라가지 못한다 — `CLAUDE.md:48`·`.cursor/rules/00-project-context.mdc`·`foms/README.md` 가 2026-04-12 에 삭제된 `apps/` 를 살아 있는 경로로 말하고, 8월 ablation 이 CLAUDE.md 를 181→108줄로 다시 썼는데도(ba1cb69b3) 살아남았다(정본 갱신에 코드 대조 단계 없음). 표본 대조: 근본 원인 규칙은 4벌 전부, production 금지는 copilot·cursor 0, 인라인 스타일 금지는 정본 AGENTS.md 에 0(CLAUDE 2·cursor 1). SYSTEM_DOCUMENTATION 은 jQuery·Google Cloud 를 스택으로 서술. 정책 소스 레지스트리도 6개만 등재·yaml 안 JSON. [확인됨: `CLAUDE.md:48` · `foms/README.md:5` · `foms/README.md:23` · `AGENTS.md` grep 출력(인라인스타일 0) · `.github/copilot-instructions.md` grep 출력(production 0) · `docs/guides/SYSTEM_DOCUMENTATION.md:108` · `docs/guides/SYSTEM_DOCUMENTATION.md:114` · `tools/harness/manifest.yaml:14-20` · `git log -S'apps/api/' -- CLAUDE.md` 출력] (D2 의 드리프트 항목을 여기로 병합)
- [리스크 · 높음 · 지금] 개발 하네스의 산출물(docs/harness JSON)이 운영 런타임 의존성이다 — 앱이 부팅 시 4종을 읽고 Dockerfile 이 explicit COPY 하며 .dockerignore 는 docs/ 제외 + negation 4줄; 로더 4곳·COPY 4줄·negation 4줄의 3자 일치 계약 테스트 없음(Dockerfile 계약은 pip 재시도·엔트리포인트 2건). 2026-07-28 스테이징 배포가 실제로 FAILED(a90a38faf '.dockerignore 가 docs/ 전체를 제외해 … gunicorn worker boot 파산'), 5번째 매니페스트 추가 시 재현. 런타임 매니페스트 4종은 6월 이후 65커밋에서 바뀜, 배포 점검 매니페스트는 없는 파일을 가리킴. [확인됨: `Dockerfile:34-40` · `.dockerignore:27-33` · `foms/services/request_write_guard.py:10` · `foms/services/security/cutover/mode_manifest.py:3` · `tests/contracts/runtime/test_dockerfile_deploy_contract.py:8` · `tests/contracts/runtime/test_dockerfile_deploy_contract.py:22` · `docs/harness/foms_deploy_checks.json:6` · `git show a90a38faf -s` 출력] (D2 의 매니페스트 결합 항목을 여기로 병합)
- [리스크 · 높음 · 지금] 지식 색인이 2026-06-17 에 멈춰 3개월 2,765 커밋의 지식이 색인 밖이고 저장소 밖 세션 메모리로 흘러간다 — ARCHIVE_INDEX 규칙은 '새 파일 추가 시 반드시 갱신' 인데 손 갱신, 2026-07 이후 plans 133건·specs 61건 등재 0(4개 색인 문서 어디든 언급 32건/11건), DECISIONS 총 23건 중 8월 이후 5건(같은 기간 커밋 1,473), 세션 메모리 164파일 4,610줄(`M=~/.claude/projects/c--DEV-FOMS/memory; ls $M | wc -l; cat $M/*.md | wc -l`)이 사용자 홈에(MEMORY.md 169줄은 훅 가지치기 임계 160 초과), AI_CHANGELOG 는 헤더가 '20개 유지·자동 갱신' 이라 하지만 73행·행당 840자 손 작성 산문(111커밋), docs 만 바꾼 커밋 653/2,773. 데이터 사고 4건(08-14·08-24·09-01·09-03)·운영 사고 4건(13시간 정지·852초·DEAD 1,188·실패잡 2,544)이 docs/incidents(5건, 2026-02 4건) 밖. [확인됨: `docs/ARCHIVE_INDEX.md:3` · `git log -1 -- docs/ARCHIVE_INDEX.md` 2026-06-17 · `.claude/hooks/session_start.py:40-42` · `docs/AI_CHANGELOG.md:2-3` · `ls docs/incidents` 출력 · 파일명 대조 스크립트 출력 133/0·61/0] (D3·D7 의 사고 원장 분산 항목을 여기로 병합)
- [리스크 · 중간 · 6개월] 하네스가 러너 2벌(Claude 훅 py 11·6 이벤트 8 커맨드 / Cursor 훅 7파일 1,519줄·8 이벤트)로 이중 구현돼 가드 변경마다 양쪽 봉합이 필요하고, Stop 훅이 인벤토리 JSON 3종을 매 .py 편집 턴마다 재생성해 8월 이후 커밋 191/1,473(13%) 이 인벤토리를 건드리며 공유 워킹트리 경합(세션 시작 git status 에 타 세션의 미커밋 인벤토리 변경)을 만든다 — DECISIONS 07-09 는 '양 훅 경로' 봉합, 07-16 은 훅 경로 결함 하나가 전 Bash 차단 데드락 P0. Cursor session_stop 기록은 2026-09-03 까지 1,159건(아직 실사용). [확인됨: `.claude/settings.json` 파싱 출력 · `.cursor/hooks.json:1-6` · `docs/harness/policy/DECISIONS.md:59` · `docs/harness/policy/DECISIONS.md:63-68` · `.claude/hooks/quality_check.py:31-38` · `.claude/hooks/quality_check.py:89` · `docs/harness/logs/HOOK_RUNTIME_LOG.txt` 집계 · `git log --since=2026-08-01 -- 'docs/harness/*_inventory.json'` 191]
- [결핍 · 높음 · 지금] 두 번째 개발자의 첫 부팅 경로가 없다 — README 가 `db.py` 가 읽지 않는 `DB_USER` 와 없는 `migration.py` 를 지시(마지막 커밋 2026-04-15), 온보딩 문서 0(검색 6건 전부 설계·플랜), 루트 `.env.example` 미추적, 안내서 전부 2,765 커밋 이전 날짜(TEST_GUIDE·DEPLOYMENT_GUIDE·tests/README 04-15·SPEC_TEMPLATE 02-28·RAILWAY_ENV_VARS 31줄), 규칙이 가리키는 프로젝트 스킬 5종 중 4종(diagnosing-bugs·handoff·wayfinder·writing-great-skills)이 git 미추적 — 클론하면 디버깅 진입점이 사라진다. [확인됨: `README.md:37-44` · `grep -c DB_USER db.py` 0 · `git ls-files .claude/skills` 1파일 · `docs/harness/policy/DECISIONS.md:33-38`('5종 유지' 결정) · `git status --short .claude/skills` 출력 ?? 4개]
- [결핍 · 중간 · 6개월] 결정·사고 포착률이 커밋 속도에 비해 낮고 ablation 판정 기준이 grep 참조 수라 라이브 의존성을 오분류했다 — 커밋 제목에 회귀 37·사고 13·revert 24 인 3개월 동안 DECISIONS 신규 5건, ablation 은 실제로 돌았지만(CLAUDE.md 181→108, 스킬 12→5, 다음 주기 2027-02) DEAD 로 지운 `tools/harness/ept_b8_staging_session_from_login.py` 가 perf-gate 라이브 의존성이라 복귀(51afc6ea1, 참조 13곳)됐는데 DECISIONS 는 '참조 0건 삭제' 그대로. 훅 fail-open 규칙('로그로 남기면 허용')의 로그는 300행 중 280행이 스크래치패드 편집 스킵이라 신호가 묻힌다(최종 벽은 branch protection). [확인됨: `docs/harness/policy/DECISIONS.md:33-38` · `git log -- tools/harness/ept_b8_staging_session_from_login.py` 출력 · `.claude/hooks/guard_shell.py` · `docs/harness/logs/CLAUDE_HOOK_LOG.md` 태그 집계 · `AGENTS.md`]
- 더 필요한 것(초안):
  - ① 정책 정본 1벌(AGENTS.md) + 나머지 포인터화 + '정본이 가리키는 경로는 실존한다' 계약 테스트(첫 걸음 = `CLAUDE.md:48`·`.cursor/rules/00-project-context.mdc`·`foms/README.md` 의 apps/ 를 `foms/api`·`foms/web` 으로 고치고 백틱 경로 실존 테스트 1개를 tests/harness 에 추가(문서 읽는 테스트 → ci.yml 서브셋 등재); 검증 = `grep -c 'apps/'` 전부 0, 없는 경로를 넣으면 red).
  - ② 런타임 매니페스트 4종을 `docs/harness/` 에서 `foms/policy/`(패키지 데이터)로 이동(전례 `foms/build_compatibility.json`) — 이동 전까지 로더 경로 집합 == Dockerfile COPY 집합 == .dockerignore negation 집합 계약 테스트.
  - ③ 지식 색인 자동 생성(plans/specs 머리를 표로 뽑는 스크립트) + '미색인 0' docs-facing 테스트 + 원장 완료 시 DECISIONS 1줄 의무 + 메모리 164 파일의 저장소 부재 함정 이식 + docs/incidents 에 데이터·운영 사고 8건 등재(유형·구조 변경 여부 필드).
  - ④ 온보딩 3문서(README 실제 부팅 절차·DEVELOPER_GUIDE 신규·RAILWAY_ENV_VARS 표) + `git add .claude/skills` + 루트 `.env.example`(검증 = 새 클론에서 문서 3개만 보고 APP_OK 와 `pytest tests/harness -q` 통과).
  - ⑤ 하네스 다이어트 — 인벤토리 재생성을 'CI 가 스캐너 돌려 diff 0 확인' 으로(훅은 경고), Cursor 훅 중복 폐기 → Claude 1벌 + 공통 policy 모듈, 2027-02 ablation 은 실행 의존성 표로 판정.

## 6. 산출물 계약

보고서 `docs/plans/2026-09-06-foms-system-review-report.md` — 한글, 한자 0, 마크다운, 600줄 이하·한 줄 600자 이하·100KB 이하(긴 목록은 줄바꿈 목록으로 펼친다), 섹션 ①~⑦ 이름·순서 고정(`## ①` … `## ⑦` 로 시작). 판정 3축(더 필요한 것/부족한 것/스택 적합성)은 ③·④·⑤ 에서 이름 그대로 살아 있어야 하고 ①·② 는 그 3축으로 이어져야 한다.
- ① **시스템 건강 지도**: 차원 8개 × 판정(적합/조건부/부적합) × 한 줄 근거 표. 워커 판정(§5 전부 조건부)과 다르면 다른 이유를 앵커로.
- ② **상위 구조 리스크 5~8**: 각각 제목(구조·흐름·거버넌스 수준) · 왜 시스템 문제인지(변경 증폭/사고 반복/단일 장애점/지식 집중/비용) · 영향 시점(지금/6개월/2년) · 근거 앵커 2개 이상 · 관련 차원. 파일 한두 개짜리 항목은 여기 금지.
- ③ **부족한 것**: 결핍이 이미 사고·속도 저하·비용으로 새고 있는 곳 — 각 항목에 '새는 증거'(사고 문서·커밋·실측 출력) 앵커.
- ④ **더 필요한 것(로드맵)**: 지금 / 이번 분기 / 12~24개월 세 구간. 각 항목에 무엇을·왜(시스템 수준)·첫 걸음(작게)·검증(됐다는 것을 어떻게 확인). 근본 원인 수정 정책과 인라인 금지·production 금지 규칙에 어긋나는 권고 금지.
- ⑤ **스택 판정**: 유지 / 조건부 유지 / 교체 후보 중 하나 + 근거 + 교체 시 비용(D1 워커 실측: route 367·render_template 106·url_for 863·템플릿 278·Flask 테스트 클라이언트 파일 265/672·Column 925 를 인용하거나 재측정). requirements 의 fastapi 를 '이행 중' 으로 읽지 않는다.
- ⑥ **열린 질문**: 운영 데이터 필요 / 사용자 결정 필요 두 묶음. 아래 초안(워커 stack_questions 병합)에서 출발해 답이 나온 것은 지우고 새로 생긴 것은 더한다.
  - 운영 데이터 필요:
    - (a) Railway 서비스 6개의 실제 빌더·파이썬 버전(패치까지)·startCommand(워커가 `start.sh` 인가 toml 인가)·헬스체크·복제 수·재시작 정책 — `docs/AI_STATUS.md:68` 미해소 [D1·D7].
    - (b) 운영 env 실제 값: SOCKETIO_ASYNC_MODE·SOCKETIO_CLIENT_ENABLED·CORS_ALLOWED_ORIGINS·REDIS_URL·FOMS_* 루프 플래그 5종·SENTRY_DSN(worker/SIDEFX 포함 여부)·FOMS_SIGNING_KEY_CURRENT engaged 여부·WD_CALCULATOR_DATABASE_URL·셸 코호트 4종·FOMS_TRUSTED_PROXY_HOPS [D1·D2·D5·D6·D7].
    - (c) 트래픽·부하: 동시 사용자·태블릿/iOS 폴링 주기·gunicorn 2×복제 2 포화·DB 풀(5+5) 대기·RQ 큐 대기 p95(2h 백필 중)·하트비트 재검증의 web CPU 비중·RUM 셸/기기별 p95·현장 기기 대수·Socket.IO 동시 연결 [D1·D5].
    - (d) 운영 DB: `users.password` 접두어 분포(Werkzeug 3 전 필수)·orders 행수·structured_data 크기·GIN 3종 idx_scan·`security_logs` 행수와 PII 혼입 비율·`order_field_changes` 본문 커버율·RUNNING 잔류 행·레거시 stage 477건 정리 계획·`designer_*` 데이터 유무·V1 링크 행수·`tools/ops/audit_erp_flat_columns.py`·`tools/ops/audit_as_axis_drift.py` 최근 결과 [D1·D2·D3·D6].
    - (e) 사고·회귀 실측: 운영 회귀 중 '테스트가 있었는데 못 잡은' 건수·핀 사고의 사용자 노출 시간·`erp-order-shared.js` fix 69건 중 운영 장애·Sentry production 이벤트 수·최근 90일 워커 재배포 횟수와 큐 정지 시간·자동 발송 놓친 날·RQ 실패잡 현재 건수·Redis 폴백 발생 여부·로그인 실패 시도량 [D2·D4·D5·D6·D7].
    - (f) CI·빌드 로그: perf-gate advisory 예산 초과 횟수와 승격 PR 블로킹 횟수·cancelled 커밋 처리 규칙·pip 재시도 루프 발동 횟수·이미지 크기(Add In Program 98파일 포함 비용)·production 배포에서 docs/ 결합 실패 이력·세션이 로컬 PG 레인을 돌리는 비율·스캐너 6종 CI 실행 시간 [D1·D2·D4·D8].
    - (g) 백업·경계: 'Railway D6+W27+M89' 의 뜻과 현재 보존값·오프사이트 성공률·복원 리허설 실행 이력·RTO 실측·pg_dump 가 wdcalculator 스키마를 포함하는지·R2 lifecycle·Cloudflare 경계의 CSP/WAF/레이트리밋 [D3·D6·D7].
    - (h) 네이버: 규격 변경 빈도와 그때 3벌(web·services·JS)이 함께 바뀌었는지(`docs/plans/2026-08-13-naver-order-ingest-ledger.md`)·앱 인증 만료일 SystemSetting 입력 여부·정산 403 재발과 사람 절차 위치·holidays 0.42 의 2026 공휴일 포함 여부 [D1·D2·D7].
  - 사용자 결정 필요:
    - (a) 두 번째 개발자의 형태·시점(사람/에이전트, Windows/PowerShell, 한국어) → 온보딩 문서 우선순위 [D4·D8].
    - (b) Socket.IO/gevent 층 유지 vs 폴링 축소 ADR [D1].
    - (c) 오프라인 쓰기 큐 채택/폐기 [D5].
    - (d) legacy 셸 사용자 잔존 여부 → 셸 2벌 축소 [D5].
    - (e) Railway 빌드에 node 단계 허용 여부 → 해시 매니페스트를 파이썬으로 할지 [D5].
    - (f) `security_logs` 영구 보존 결정 vs purge 1095일 중 유효 결정·정보주체 5만명 기준 법률 판단(조문 단정 없이 열린 질문으로) [D6].
    - (g) 공유 링크 30일·전화·주소 표시 범위 [D6].
    - (h) VIEWER·외부 협력사·태블릿 공유 계정 정책(읽기 최소권한 입력값) [D6].
    - (i) Cursor 러너 실사용 여부 → 훅 2벌→1벌 [D8].
    - (j) 사업이 허용하는 RPO/RTO(하루치 주문·실측·도면 손실 허용치) [D3·D7].
    - (k) WD_CALCULATOR 별도 DB 토폴로지 유지 여부 [D2·D3].
    - (l) 정책 4벌 전수 대조·메모리 164 파일 전수 이관 범위 [D8].
- ⑦ **부록(사소한 것)**: 워커 `minor_parked` 전부 + 본문에 못 들어간 항목을 차원별 목록으로. 헤드라인 금지.

## 7. 실행 계획(멀티 에이전트)

### 7.1 단계
1. **CEO 설계(1)**: §1~§5 를 읽고 차원 8개(키 D1~D8 고정)의 핵심 질문·앵커·명령·판정 기준·함정을 확정한다(§4 를 그대로 쓰되 HEAD 이동으로 어긋난 숫자만 보강). 리뷰 기준(§7.4)을 확정한다. 저장소 파일은 쓰지 않는다.
2. **워커 8 병렬**: 차원마다 1명. 입력 = 이 파일 경로 + 차원 키. 자기 차원의 핵심 질문에만 답하고 §7.3 스키마로 구조화 출력을 낸다. §3 절대 규칙 전부 적용. 다른 차원과 겹치는 관측은 자기 차원 관점으로만 쓰고 `→ Dn` 표시. §5 의 해당 차원 항목을 하나씩 재검증(확인됨 유지/승격/반박)한다.
3. **통합(1)**: 워커 8 JSON(파일로 핸드오프 — 세션 히스토리 붙이지 않음)과 §5 를 대조해 보고서 ①~⑦ 을 쓴다. 워커 간 중복은 가장 구조적인 차원에 한 번만, `minor_parked` 는 ⑦ 로만. 쓰기 허용 파일 = 보고서 1개 + 원장 1개. 쓰기 전에는 인자 없이(이 프롬프트 자기 검사, 통과 기준 동일), 쓴 뒤에는 보고서 경로를 인자로 §8 스니펫을 돌린다.
4. **리뷰 2 병렬(편집 금지)**: 스펙 리뷰어(사용자 요청 충족)·품질 리뷰어(정확성·실행 가능성)가 §7.4 기준으로 각각 `ship`/`fix`(구체 수정 목록)/`block`(사유)를 낸다. 리뷰어는 pre-judge 하지 않는다 — 워커 출력을 먼저 보지 말고 보고서와 저장소만 본다.
5. **CEO 판정**: 두 판정을 합쳐 `ship`/`fix`/`block`. `fix` 는 통합자가 **1회** 반영 후 CEO 재판정. `block` 은 사용자에게 사유와 함께 돌려보낸다. 판정 결과와 각 단계 완료 상태는 원장에 task 별로 기록한다.
### 7.2 파일 소유권(병렬 충돌 방지 — 절대 규칙)
| 역할 | 쓰기 허용 | 금지 |
|---|---|---|
| CEO 설계·판정 | 없음(구조화 출력만) | 저장소 파일 전부 |
| 워커 D1~D8 | 없음(구조화 출력만) | 저장소 파일 전부, 패키지 설치, git 변경 |
| 통합자 | `docs/plans/2026-09-06-foms-system-review-report.md` · `docs/plans/2026-09-06-foms-system-review-report-ledger.md` | 그 외 전부 |
| 리뷰어 2 | 없음(구조화 출력만) | 저장소 파일 전부 |
### 7.3 워커 출력 스키마(JSON — 구조화 출력으로 반환)
```json
{
  "dimension": "D1",
  "title": "스택·의존성 적합성",
  "verdict": {"fit": "적합|조건부|부적합", "one_line": "한 문장 판정"},
  "system_risks": [
    {"title": "…", "why_systemic": "변경 증폭/사고 반복/단일 장애점/지식 집중/비용 중 무엇이 왜",
     "severity": "높음|중간|낮음", "horizon": "지금|6개월|2년",
     "evidence": [{"claim": "…", "anchor": "경로:행 또는 명령", "verified_by": "읽음|실행 출력: …|가설"}]}
  ],
  "lacking": [
    {"title": "…", "why_systemic": "지금 결핍이 이미 새고 있는 곳 — 사고·속도 저하·비용의 흔적이 무엇인지",
     "severity": "높음|중간|낮음", "horizon": "지금|6개월|2년",
     "evidence": [{"claim": "…", "anchor": "'이미 새는 증거'(사고 문서·커밋·실측 출력) 앵커 1개 이상 필수", "verified_by": "읽음|실행 출력: …|가설"}]}
  ],
  "needed": [
    {"title": "…", "what": "무엇을 갖출지", "why": "시스템 수준 이유", "first_step": "첫 한 걸음(작게)", "verify": "됐다는 것을 어떻게 확인"}
  ],
  "prior_observations": [{"item": "§5 항목 제목", "result": "확인 유지|승격|반박", "anchor": "…"}],
  "stack_questions": ["받는 에이전트가 반드시 다시 확인할 질문 — 운영 데이터가 있어야 답할 것 포함"],
  "minor_parked": ["사소한 발견은 여기로 격리(헤드라인 금지)"],
  "commands_run": [{"cmd": "…", "decisive_line": "…"}]
}
```
규칙: `system_risks`·`lacking` 각 3~6개, `needed` 3~5개. 앵커 없는 항목은 `verified_by` 에 `"가설"`. §5 사전 관측을 반박해도 좋다 — 반박도 앵커를 단다. `commands_run` 에는 실행한 명령과 결정적 출력 한 줄을 남긴다(리뷰어가 재실행한다). 브리프 §5 대비 달라진 점: `prior_observations` 필드 추가(§5 사전 관측 재검증 결과 기록용), `verified_by` 에 `가설` 값 추가 — 그 외 동일.
### 7.4 리뷰 기준(2판정 — 리뷰어는 편집하지 않는다)
스펙 리뷰어: (1) 판정 3축(더 필요한 것/부족한 것/스택 적합성)이 보고서 ③④⑤ 에 이름 그대로 있고 ①② 가 그 3축과 연결되는가 — 한 곳이라도 빠지면 fix. (2) '시스템 전체 관점' 기준(구조·흐름·거버넌스 헤드라인 + 왜 시스템 문제인지 + 영향 시점 + 제품·팀 맥락)이 ② 헤드라인에 실제로 적용됐는가 — 파일 한두 개짜리 항목이 하나라도 있으면 fix 목록에 항목명. (3) 페르소나가 제품·팀 맥락(9단계·현장 태블릿·iOS·네이버·카카오·채널톡·사람 1명 + 에이전트 2,765 커밋)과 문장으로 연결됐는가. (4) 보고서만으로 사용자가 결정을 내릴 수 있는가(④ 각 항목에 첫 걸음·검증, ⑥ 두 묶음). (5) 프로젝트 절대 규칙(production push 금지·근본 원인 수정·한글·한자 금지·인라인 스타일 금지·훅 fail-open 로그 의무)을 어기라고 권하는 문장이 없는가 — 있으면 block. (6) §5 의 확인됨 항목을 근거 없이 뒤집거나 가설을 확인됨으로 올린 곳이 없는가(반박은 앵커와 함께 남아 있어야 한다). (7) 섹션 ①~⑦ 이름·순서 일치.
품질 리뷰어: (1) §8 앵커 실존 스니펫을 보고서에 실행해 `ANCHOR_BAD 0`·`HANJA 0` — 출력 원문을 판정에 적는다. (2) 앵커 표본 15개 이상(차원마다 1개 이상 + ② 위주)을 직접 열어 줄과 주장이 일치하는지 대조 — '실존하나 불일치' 는 따로 센다. (3) 숫자가 §2 사실 카드 또는 재측정 명령 원문과 일치하는가(임의 수치 없음, 재측정 병기는 명령 원문이 있어야 인정). (4) 명령 표본 5개 이상(차원 다르게)을 bash 에서 실행 — `cd`·`PYTHONIOENCODING`·`timeout` 접두, PowerShell 전용 문법 없음. (5) 항목마다 확인됨/가설 표기, 확인됨의 앵커가 (1)(2) 를 통과. (6) 운영 수치를 추정한 문장 0 — 있으면 '확인 필요' 로 바꾸라는 fix. (7) 한자 0(`[\u4e00-\u9fff]`), 한국어 낱말의 타 언어 치환 0, 600줄 이하(초과 시 어느 절을 줄일지 지정). (8) 같은 관측이 두 차원 헤드라인에 반복되지 않고 `minor_parked` 가 ⑦ 에만 있는가. (9) 워커 출력이 §7.3 스키마(필드 이름·개수 3~6/3~5)를 지켰는가.
### 7.5 Workflow 도구가 없을 때
한 메시지에서 Agent 도구를 8번 병렬로 호출한다 — 각 호출의 프롬프트는 "이 파일 경로 + 차원 키 + '§4 의 해당 차원만 조사하고 §7.3 스키마 JSON 만 반환'" 세 줄이면 된다(모델 티어: 워커=표준). 결과 JSON 8개를 스크래치패드에 `D1.json`~`D8.json` 으로 저장하고, 통합자 Agent 1개에 그 경로 목록과 이 파일 경로만 넘긴다(최상위 모델). 통합자가 보고서를 쓰면 리뷰어 Agent 2개를 한 메시지에서 병렬 호출(편집 금지·구조화 판정만, 최상위 모델)하고, 메인 세션이 CEO 역할로 두 판정을 합쳐 ship/fix/block 을 내린다. fix 는 통합자에게 수정 목록 파일 경로만 넘겨 1회 재위임하고, 진행 상태는 원장 파일에 task 별로 기록해 컨텍스트 압축 뒤 재디스패치를 막는다. 서브에이전트의 "완료" 는 주장일 뿐이다 — 통합자는 워커 앵커를 열어 보고, CEO 는 리뷰어 출력의 스니펫 원문을 확인한 뒤에만 ship 한다.

## 8. 완료 기준·검증 명령

완료 = 아래 전부 통과. 명령은 전부 bash.
1. 보고서 파일 존재: `cd C:/DEV/FOMS && test -s docs/plans/2026-09-06-foms-system-review-report.md && echo REPORT_OK`
2. 섹션 7개 존재(①~⑦ 순서): `cd C:/DEV/FOMS && grep -nE "^## " docs/plans/2026-09-06-foms-system-review-report.md` → ①~⑦ 이 이 순서로 7줄.
3. 한자 0 + 앵커 실존: 아래 스니펫을 보고서 경로를 인자로 실행(첫 줄을 `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python - docs/plans/2026-09-06-foms-system-review-report.md <<'EOF'` 로) → `ANCHOR_BAD 0` · `HANJA 0`. 실패한 앵커는 워커 출력을 다시 열어 고치거나 `[가설]` 로 내린다(최대 3회 반복). 인자 없이 실행하면 이 프롬프트 자신을 검사한다(통합 시점 결과: `ANCHOR_BAD 0` · `HANJA 0`).
4. 헤드라인에 사소한 항목 0 — 리뷰어 판정(§7.4 스펙 (2)).
5. 판정 3축·차원 8개·열린 질문 두 묶음이 전부 존재 — 리뷰어 판정.
6. 길이 600줄 이하·한 줄 600자 이하·100KB 이하: `cd C:/DEV/FOMS && wc -c docs/plans/2026-09-06-foms-system-review-report.md; PYTHONIOENCODING=utf-8 python -c "import io;L=[len(l) for l in io.open('docs/plans/2026-09-06-foms-system-review-report.md',encoding='utf-8')];print('LINES',len(L),'MAX_LINE',max(L))"`
7. 저장소 무변경(보고서·원장 2개만 신규): `cd C:/DEV/FOMS && git status --short | grep -vE "system-review-report" || echo CLEAN_EXCEPT_REPORT` — 다른 창의 변경이 섞여 있으면 그 사실만 적고 손대지 않는다.

앵커 실존 검사 스니펫(글자 그대로 사용):
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

## 부록 A. 사소한 발견(헤드라인 금지)

워커 `minor_parked` 전부. 보고서 ⑦ 의 출발점으로만 쓴다. 앵커 없는 것은 (가설) 표시.
- **D1**:
  - 도달 불가 핀 39개 — poetry 잔재(cleo·crashtest·dulwich·keyring·pkginfo·tomlkit·findpython·pbs-installer·trove-classifiers·installer·CacheControl·fastjsonschema·jaraco.context·pywin32-ctypes·requests-toolbelt)·pyinstaller 잔재(pefile·altgraph)·pywebview 잔재(pythonnet·clr_loader·proxy_tools·bottle)·FastAPI 잔재(fastapi·starlette·uvicorn·python-multipart·python-jose·passlib·ecdsa·aiofiles·msgspec)
  - Flask-Session·Flask-Caching·Flask-Migrate·Flask-WTF·WTForms·email_validator·Flask-SQLAlchemy 는 foms import 0(앱은 `db.py` 순수 SQLAlchemy)
  - waitress import 0
  - `Dockerfile:17-27` 미고정 setuptools/wheel 설치 후 핀으로 되돌림
  - et_xmlfile 고아 핀(openpyxl 제거 061730120 뒤)·numpy foms import 0
  - python-Levenshtein 이름 불일치(동작 무관)
  - `foms/services/security/backfill/crypto.py:85-88` win32crypt 미등재 Windows 전용 지연 import
  - pytest 7.4.3(35개월)·alembic 1.16.1·holidays 0.42 노후
  - `.query(` 711 vs `select(` 6(2.0 계열 비용 0, 2.1/3.0 재평가)
  - 워커 시작 명령 3벌(Procfile·start.sh·railway-worker.toml)
  - `docs/guides/DEPLOYMENT_GUIDE.md` 'requirements 자동 읽기' 서술
  - requirements 주석과 app.py 경고문의 eventlet 언급(실제 gevent)
  - 부트스트랩 5.3.0-alpha1 알파를 공용 레이아웃이 CDN 로드
  - CDN 5종·벤더 3종(alpine/htmx 버전 문자열 없음)·package.json 없음
  - 로컬 전역 인터프리터 323패키지·pip check 충돌 4·설치판이 핀과 다름(Jinja2 3.1.6·cryptography 49)
  - `docs/guides/RAILWAY_ENV_VARS.md` 에 SOCKETIO/REDIS/FOMS_* 0
  - SOCKETIO_CLIENT_ENABLED 는 설정만 되고 읽는 곳 0
  - 의존성 커밋 grep 91건은 노이즈, 본문 확인 7건만 채택.
- **D2**:
  - `foms/api/channel/rooms.py` 가 wdcalculator 루트 모듈 직접 import
  - `foms/web/orders/dashboard.py:107` channel.io URL 리터럴 폴백
  - `foms/services/common/map_generator.py` 980줄에 kakao/geocode/order 낱말 94회(common 규칙 위반)
  - `.dockerignore` 는 SCheduler 만 제외 → Add In Program 98파일이 `COPY . .` 로 이미지 포함(런타임 import 0, 참조 docs 뿐)
  - `foms/persistence/designer/repositories.py` 포함 designer 1,515줄 런타임 사용 0(의도적 보존)
  - `db.py` 로컬 기본 DSN 에 비밀번호 리터럴(D6)
  - `app.py` 가 erp_policy 심볼 11개 재수출
  - services 플랫 모듈 127/311·api 루트 플랫 20파일 72라우트
  - url_prefix `/api/orders` 10개·`/erp` 9개·`/api` 8개 공유(등록 순서 동결 이유)
  - `foms/api/erp_orders_structured.py` 가 db·models 직접 import·ORM 23곳·알림톡 발송 트리거
  - `tests/contracts/runtime/foms_namespace_surface_tests.py` 2,573줄이 Wave 8 이전 shim 파리티 계속 검사(D4)
  - `foms/platform/erp_blueprint.py` 22줄(필터 등록만)
  - `foms/services/kakao_alimtalk.py` 1,171줄 플랫(어댑터 분리 첫 대상).
- **D3**:
  - `foms/services/db_indexes.py` 런타임 호출자 0 인데 `tests/domains/test_db_indexes.py` 가 유지
  - `ix_orders_structured_data_gin` 소비자 0(운영 idx_scan 확인 후 제거 후보)
  - 로컬 dev 중복 인덱스 10쌍(운영 여부 확인 필요)
  - Order 날짜 컬럼 String(received_date 등) → trigram 검색
  - 두 엔진 풀 합산(db 5+5, wdcalculator 3+3)
  - 데이터 마이그레이션 6건 중 phonewide_01 downgrade pass(설계상)·naver_relation_00 '무손실 아님'
  - `tools/ops/ensure_schema.py:46` alembic_version 직접 UPDATE
  - 감사 purge 기본 보존이 RPO 문서와 따로
  - security_logs message trigram 인덱스 본문 1B 당 2.06B
  - ERP draft 부활 레이스는 코드 주석으로만 봉합
  - CLAUDE.md 의 deepcopy+flag_modified 패턴 위반 시 조용한 미저장(가설)
  - 감사 본문 개인정보는 D6
  - HEAD 이동(브리프 094682d57 → 워커 c38ae6225 → 통합 58275b7e5)은 판정 영향 없음.
- **D4**:
  - `.github/workflows/ci.yml` 주석의 '실측 median 14.1분'·'5,329/6,000+ 개' 는 낡음(현재 9,913건·1.8분)
  - pytest-playwright 때문에 모든 레인에 `-p no:playwright` 반복
  - G4 리스너 기준선이 파일별 정수 하드코딩
  - tests/domains 접두 분포(order 35·erp 35·as 26·channel 21) 단일 평면
  - `docs/guides/TEST_GUIDE.md` 이름이 테스트 체계 문서로 오인
  - harness-ci 는 checkout@v5/setup-python@v6, 나머지 v4/v5
  - `tests/domains/test_password_kdf_contract.py` 는 Werkzeug 3(scrypt) 전환 시 먼저 빨강(D1)
  - `tests/harness/test_ci_watch.py` 가 perf-gate cancelled 를 실패로 못 박아 `cancel-in-progress` 와 정책 충돌(코드가 아니라 DECISIONS 와 워크플로 사이)
  - node 부재 시 assert 로 죽음(skip 아님, 안전)·CI 는 setup-node 없이 러너 기본 node
  - 세션 시작 스냅샷의 인벤토리 미커밋 변경은 이후 8e7f8c7b4(공휴일 캐시 원자 쓰기 — CI 간헐 JSONDecodeError 진짜 원인)로 해소
  - 핀 사고 4건의 발견 경로는 커밋 제목 기반 추정(가설)
  - rev_99 writer 인벤토리의 (path, lineno) 튜플 비교 잔존(가설).
- **D5**:
  - Bootstrap 5.3.0-alpha1 CDN 직링크(`templates/partials/shared/layout_head.html:166`) + `templates/measurement/map_view.html:112` 5.1.3·FA 6.0.0 공존
  - flatpickr 미버전 CDN·`integrity` 속성 0
  - SW 가 htmx·alpine 프리캐시하지만 사용 hx- 6·x-data 2
  - 핀 없는 로컬 자산 23곳(script.js·global-nav-runtime.js·erp-mine-only.js·style-pro-max.css·`templates/channel/wam/layout.html:11-17`) 매 로드 no-cache
  - `static/js/runtime/layout-head-init.js`(529줄)·`static/js/runtime/layout-scripts-chat.js`(481줄)는 어떤 템플릿도 로드 안 하는 인라인 부트 사본(삭제 후보)
  - `foms/api/foms_offline.py` 죽은 경로를 `tests/domains/test_p2_gate.py:173` 이 고정
  - `templates/partials/shared/layout_head.html:1263-1265` 전역 충돌 실사례
  - `!important` 1,529
  - 태블릿 전용 JS 5파일 전 페이지 로드
  - RUM 기본 ON·rum-daily cron 은 production 파일만
  - 유지할 긍정 자산: 성능 가드 G1~G4, erp-pro @import 핀 게이트(`tests/performance/test_static_cache_headers.py:63-66`), erp-shell 경로 SSOT 대조, SW 교차 출처 미개입·PII no-store 게이트, fragment top-level 리다이렉트(`foms/api/fragment.py:39-41`), wdcalculator node 계약 57
  - 메모리 함정 앵커 확인: SW phantom(`docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:49`·`static/sw.js:10-17`)·페이지 스코프 스크립트 v3 누락(`docs/AI_CHANGELOG.md:39`)·surfaces 번들 v3 미적재(`templates/partials/shared/layout_head.html:176-180`)
  - DECISIONS 의 React/Vite 결정은 Add In Program 애드인 스택(D2·D8).
- **D6**:
  - `foms/services/erp_permissions.py` 허용 팀 상수(CS·SALES)와 403 메시지('라홈팀·하우드팀·영업팀') 드리프트, 미등록 팀은 mine scope 'all' 폴백, services 층이 web.auth import(D2)
  - `.env.bak-20260828` 이 워킹트리에 있고 `.gitignore` 에 안 걸림(check-ignore exit 1, 값 미확인)
  - 업로드 티켓 complete 가 클라이언트 size 를 검사 — R2 HEAD 대조 여부 미확인(가설)
  - `login_required` 가 API 라우트에서도 302(`/api` 401 JSON 불변식과 어긋남)
  - SESSION_COOKIE_SECURE 는 production/railway 만·세션 30일 슬라이딩(유휴 만료 없음)
  - PasswordResetRequest 는 관리자 처리형
  - 로컬 dev 표본(security_logs 146·전화 패턴 0·주문 14·사용자 8)은 운영 대표성 없음
  - §4 D6 명령 3 의 이름 패턴 0건이 정상
  - 명령 5 의 513건은 masked_counts 등 비-PII 용법 포함
  - 견고한 것: 공유 링크(token_urlsafe(32)·sha256 저장·30일·회수·열람 기록·presign 300초·ZIP 200MB), 업로드 티켓(900초·서버 파생 키·tamper/type/size·권한 재검사).
- **D7**:
  - `docs/guides/DEPLOYMENT_GUIDE.md` eventlet 필수 서술(실제 gevent)
  - `docs/guides/RAILWAY_ENV_VARS.md` 의 railway_bootstrap 안내가 alembic 소유 원칙과 충돌(문서 폐기 대상)
  - `railway-cron-receipt-purge.toml:9-16` `&&` 실패 커플링 1건(사문 toml 이라 실제 cron 과 대조 필요)
  - Procfile 과 start.sh 의 gunicorn 인자 두 벌
  - `foms/platform/sentry_setup.py` 환경 판정이 RAILWAY_PROJECT_NAME 접미사 명명 규약 의존
  - `/healthz` 응답에 부팅 시각·마이그레이션 head 없음
  - `tools/ops/check_deploy_secrets.py` 가 NAVER·REDIS·SOLAPI 미검사
  - `tests/contracts/runtime/test_dockerfile_deploy_contract.py` 는 CMD 한 줄만 고정(start.sh 루프 배선 사각)
  - 루프 스크립트 4개가 각각 Flask 앱 전체 부팅(최대 5회 초기화, `foms/services/sidefx_worker.py:60-66` 은 이를 피함)
  - `tools/ops/wait_for_redis.py` 예산 초과 시 재시작 정책 의존
  - `railway.toml` 주석의 '워커 2로 확장' 계획은 실제(1)와 불일치 가능
  - 정산 API 403(앱 [정산] 그룹) 사람 절차는 저장소 runbook 앵커 없음(가설).
- **D8**:
  - `tools/harness/manifest.yaml` 확장자 yaml 내용 JSON·등록 소스 6개뿐
  - `docs/harness/foms_deploy_checks.json:6` 없는 `foms_feature_mode_matrix.json` 참조
  - `docs/AI_CHANGELOG.md:2-3` 헤더 문구 부패
  - `.claude/settings.local.json` 이 git 추적됨
  - CLAUDE_HOOK_LOG 300행 중 280행 스크래치패드 스킵(로그 대상 제외 권고)
  - README 하단 Google App Engine 레거시 절
  - 브리프 '훅 10개' vs py 11·배선 8 커맨드
  - `.cursor/rules/00-project-context.mdc` 의 `/verify-result`·`/auto-status-update` 는 Cursor 워크플로(`.agents/workflows/verify-result.md`, .claude/commands 엔 없음)
  - `docs/harness/policy/DECISIONS.md:33-38` 의 ept_b8 'DEAD 삭제' 기록에 복귀 미반영
  - `.claude/hooks/session_start.py:40-42` 메모리 경로 대문자 `C--DEV-FOMS`(다른 OS 에서 깨짐)
  - DECISIONS 항목은 `### [날짜]` 형식이라 `grep '^## '` 로는 0건
  - AI_STATUS 40줄 계약은 `tests/harness/test_hook_log_hygiene.py:25-26` 이 4,000자 예산으로 강제(실재·통과)
  - `tools/harness/verify_result.py` 는 `import app` 서브프로세스 + 스펙 탐지만(편집·설치 없음, success true)
  - AGENTS.md 탐색용 브라우저 'Cursor browser MCP' vs CLAUDE.md 'gstack browse' 역할 분담
  - docs/plans 셈법(441/443/446/449)은 `ls docs/plans | wc -l` 기준 449(통합 시점)로 고정
  - 인라인 style 687곳이 정책 4벌 어긋남의 누적 결과라는 인과(가설).
