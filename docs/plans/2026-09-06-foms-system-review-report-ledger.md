# FOMS 시스템 전체 개발 검토 — 진행 원장 (2026-09-06)

> 검토 프롬프트 `docs/plans/2026-09-06-foms-system-review-prompt.md` §7.1 의 단계별 완료 상태와 통합자가 직접 실행한 검증 원문을 남긴다. 컨텍스트 압축 뒤 같은 단계를 다시 돌리지 않게 하는 것이 이 파일의 목적이다.
> 쓰기 허용 파일은 보고서 `docs/plans/2026-09-06-foms-system-review-report.md` 와 이 원장 2개뿐이다. 저장소의 다른 파일·git 상태는 건드리지 않았다.

**기준 커밋** — HEAD `062723348` (`cd C:/DEV/FOMS && git log --oneline -1`). 프롬프트 통합 시점 `58275b7e5` 대비 문서 커밋 1건, 코드 변경 0.

## 1. 단계별 완료 상태

| task | 상태 | 산출물 | 완료 기준과 확인 |
|---|---|---|---|
| CEO 설계 | 완료 | 차원 8개 키·질문·판정 기준(프롬프트 §4), 리뷰 기준(§7.4) | 프롬프트에 확정 기재됨 — 통합자는 그대로 적용 |
| 워커 D1 스택·의존성 | 완료 | `D1.json` | 판정 조건부 · 스키마 필드 충족 · commands_run 보유 |
| 워커 D2 아키텍처 | 완료 | `D2.json` | 판정 조건부 |
| 워커 D3 데이터·마이그레이션 | 완료 | `D3.json` | 판정 조건부(부적합 경계) |
| 워커 D4 테스트·CI | 완료 | `D4.json` | 판정 조건부 |
| 워커 D5 프론트엔드 | 완료 | `D5.json` | 판정 조건부 |
| 워커 D6 보안·권한·개인정보 | 완료 | `D6.json` | 판정 조건부 |
| 워커 D7 운영·배포·관측 | 완료 | `D7.json` | 판정 조건부(부적합 경계) |
| 워커 D8 개발 시스템 | 완료 | 통합자 브리프에 본문으로 전달(스크래치패드에 파일 없음) | 판정 조건부 |
| 통합 | 완료 | 보고서 451줄 + 이 원장 | §8 기준 통과(3절에 실행 원문) |
| 리뷰 2(스펙·품질) | 완료 | 두 판정이 CEO fix 목록으로 통합자에게 도착 | 편집 금지 규율 지켜짐 — 통합자는 fix 목록만 받았다 |
| CEO 판정 1차 | 완료(fix) | 지적 4건 — 로드맵 검증 명령 1 · 수치 병기 4곳 · 단위 명시 1 · 부록 사실 정정 1 | 6절에 반영 내용과 검증 원문 |
| 통합 수정 라운드 | 완료(1회 — 추가 반영 금지) | 보고서 4개 지적 반영, 그 밖의 본문 무변경 | 6절 · §8 재실행 ANCHOR_BAD 0 · HANJA 0 |
| CEO 재판정 | 대기 | — | 수정 라운드 반영본으로 ship 또는 block |

**통합 단계 특기사항** — 이 통합자가 붙었을 때 보고서 파일이 이미 워킹트리에 있었다(앞선 통합 실행의 산출물, 원장은 없었다). 폐기하지 않고 근거를 통합자가 직접 재검증한 뒤 채택했고, 재현되지 않는 수치 2건만 고쳤다(4절). 보고서 본문의 앵커·수치는 전부 이 통합자가 다시 연 것이다(5절).

## 2. 워커 판정 표(보고서 첫째 절과 일치)

| 차원 | 워커 판정 | 통합자 판정 | 통합자가 다르게 본 곳 |
|---|---|---|---|
| D1 스택·의존성 | 조건부 | 조건부 | 없음 |
| D2 아키텍처 | 조건부 | 조건부 | 없음 |
| D3 데이터·마이그레이션 | 조건부(부적합 경계) | 조건부(부적합 경계) | 없음 — 09-01 원인 줄 잔존을 직접 확인해 경계 표기 유지 |
| D4 테스트·CI | 조건부 | 조건부 | 없음 |
| D5 프론트엔드 | 조건부 | 조건부 | 없음 |
| D6 보안·권한·개인정보 | 조건부 | 조건부 | 없음 |
| D7 운영·배포·관측 | 조건부(부적합 경계) | 조건부(부적합 경계) | 없음 — 사고 문서 2건을 직접 확인해 경계 표기 유지 |
| D8 개발 시스템 | 조건부 | 조건부 | 없음 |

워커 판정을 뒤집은 항목 0, 가설을 확인됨으로 올린 항목 0, §5 의 확인됨 항목을 근거 없이 뒤집은 곳 0.

**중복 관측 병합 방향(프롬프트 §5 규칙 그대로)** — apps 경로 드리프트·런타임 매니페스트 결합·사고 원장 분산은 D8(보고서 R8), 권한 변경 증폭은 D2(R2), 자산 핀·셸 3벌은 D5(R4), 계약 세금은 D4(R5), 워커 감독·재배포는 D7(R3). 각 관측은 한 곳에만 두고 나머지 차원에서는 참조로만 남겼다. `minor_parked` 는 보고서 마지막 절(부록)에만 두었다.

## 3. 검증 실행 원문(통합자 직접 실행)

### 3.1 프롬프트 §8 앵커 실존 스니펫 — 쓰기 전(인자 없음 = 프롬프트 자기 검사)

명령: `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python - <<EOF` + §8 스니펫 본문(글자 그대로).

```
ANCHOR_BAD 0
HANJA 0
```

### 3.2 같은 스니펫 — 쓴 뒤(보고서 경로를 인자로)

명령: `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python - docs/plans/2026-09-06-foms-system-review-report.md <<EOF` + 같은 스니펫 본문.

```
ANCHOR_BAD 0
HANJA 0
```

1회에 통과 — 재시도 0회(허용 3회). 실패 앵커가 없어 `[가설]` 강등 처리도 0건.

### 3.3 섹션 목록과 길이 검사

```
cd C:/DEV/FOMS && grep -nE "^## " docs/plans/2026-09-06-foms-system-review-report.md
18:   시스템 건강 지도
33:   상위 구조 리스크
90:   부족한 것
146:  더 필요한 것(로드맵)
276:  스택 판정
302:  열린 질문
333:  부록(사소한 것)
```
(줄 번호는 수정 라운드 반영 뒤 값이다 — 반영 전에는 18·33·89·145·275·301·332 였고 이름·순서는 같다.)

일곱 절이 프롬프트 §6 이 정한 이름·순서 그대로 있다(보고서 본문의 절 머리 기호는 프롬프트가 요구한 동그라미 숫자 그대로이며, 이 원장에서는 줄 번호와 이름만 옮겨 적었다).

```
cd C:/DEV/FOMS && wc -c docs/plans/2026-09-06-foms-system-review-report.md
94481 (수정 라운드 반영 뒤)

cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python -c "import io;L=[len(l) for l in io.open('docs/plans/2026-09-06-foms-system-review-report.md',encoding='utf-8')];print('LINES',len(L),'MAX_LINE',max(L))"
LINES 451 MAX_LINE 590
```

기준: 600줄 이하 · 한 줄 600자 이하 · 100KB 이하 — 전부 통과.

### 3.4 저장소 무변경 확인

```
cd C:/DEV/FOMS && git status --short | grep -vE "system-review-report"
?? .claude/skills/diagnosing-bugs/
?? .claude/skills/handoff/
?? .claude/skills/wayfinder/
?? .claude/skills/writing-great-skills/
?? .env.bak-20260828
?? docs/plans/2026-09-04-as-legacy-stage-cleanup-plan.md
```

이 6건은 이 검토가 만든 것이 아니라 세션 시작 시점에 이미 있던 다른 창·이전 작업의 미추적 파일이다(프로젝트 스킬 4종·환경 파일 백업·타 세션 계획서). 손대지 않았고 앞으로도 손대지 않는다. 이 검토가 만든 변경은 보고서와 이 원장 2개뿐이며 git 명령은 조회만 썼다.

### 3.5 워커 결과 파일 핸드오프 경로

- `C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/16dad647-a3f9-4175-a837-57f381123b67/scratchpad/D1.json` (51,697바이트)
- 같은 디렉토리의 `D2.json`(48,778) · `D3.json`(47,176) · `D4.json`(46,628) · `D5.json`(47,092) · `D6.json`(41,393) · `D7.json`(40,965)
- D8 은 파일이 아니라 통합자 브리프 본문으로 전달됐다 — 재실행할 때 D8 만 다시 받아야 한다.
- 세션 히스토리는 붙이지 않았다(파일 핸드오프 규율 준수).

## 4. 통합자가 고친 것(재현되지 않는 수치 2건)

| 위치 | 고치기 전 | 고친 뒤 | 사유 |
|---|---|---|---|
| 보고서 머리 재측정 절 | docs/plans 451 | docs/plans 452(이 보고서 포함 — 쓰기 전 451) | 보고서 파일 자체가 목록에 들어가 값이 바뀐다 |
| 보고서 머리 재측정 절 | 08-01 이후 1,482 (`--since=2026-08-01`) | 08-01 이후 1,483 (`--since=2026-08-01T00:00:00+09:00`) + 흔들림 설명 | 시각을 뺀 형식은 git 이 빈 자리를 실행 시각으로 채워 같은 HEAD 에서도 값이 흔들린다(오늘 1,479 · 워커 1,482 관측). 리뷰어가 재실행해도 같은 값이 나오는 결정적 형식으로 교체했다 |

그 외 본문 수정 0. 워커 판정·리스크 목록·권고 문안은 그대로 두었다.

## 5. 앵커 표본 대조(서브에이전트 완료 보고는 주장일 뿐)

통합자가 직접 파일을 열어 줄과 주장을 대조한 앵커: 통합 라운드 **31개** + 수정 라운드 **8개** = **39개**(요구 15개 이상, 차원마다 1개 이상, 보고서 둘째 절 헤드라인 위주). **실존하나 불일치: 0개.** 수정 라운드에서 연 8개는 6절에 명령·출력과 함께 적었다.

- D1 — `requirements.txt:31`(Flask==2.3.3) · `requirements.txt:49`(Jinja2==3.1.2) · `requirements.txt:106`(Werkzeug>=2.3.5,<3) · `app.py:22-36`(몽키패치, pbkdf2/scrypt 원본 위임 주석 실재)
- D2 — `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:315-322`(레이어별 경계 규칙 표) · `foms/services/settlement_aggregation.py:55-60`(web private 함수 역수입) · `foms/persistence/main/models.py:3`(`from models import *`) · `foms/web/auth/routes.py:53`(ROLES 정의)
- D3 — `models.py:89`(structured_data) · `models.py:99-100`(String(10) 날짜 컬럼) · `models.py:111-112`(2026-08-14 사고 주석 + as_axis_status) · `foms/services/erp_sync_columns.py:86-87`(erp_phone_digits 만 갱신) · `foms/services/integrations/naver_commerce/order_candidates.py:822-823`(`Order.phone == digits` 잔존) · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:20-22`
- D4 — `.github/workflows/ci.yml:7-11`(승격 PR 구멍과 사고 3건) · `scripts/ops/pre_push_smoke.ps1:8`(push 시 자동 실행 아님) · `tools/harness/ci_watch.py:404`(런 없음을 green 취급) · `docs/plans/2026-08-26-ci-speed-ledger.md:95-98`(exit 1 인데 푸시가 나감)
- D5 — `static/sw.js:82-86`(staticCacheFirst TTL) · `static/sw.js:10-13`(v9 stale-JS 사고) · `foms/platform/app_factory.py:60-63`(CSS/JS 해시 없음) · `templates/partials/shared/layout_head.html:210-213`(2026-07-12 봉합 주석)
- D6 — `foms/services/orders/order_mutation_policy.py:579-582`(쓰기 before_request 게이트) · `:385-396`(읽기 전역 허용 + order 인자 미사용) · `foms/web/orders/edit.py:237-240`(role_required 3역할) · `foms/platform/http.py:238-242`(인가 경계가 아니라는 자기 기록) · `foms/services/rate_limit.py:58-63`(Fail open 주석)
- D7 — `start.sh:23-26`(루프 1) · `start.sh:72-76`(마지막 `&` + `exec rq worker` + gunicorn 인자) · `foms/api/health.py:7-10`(순수 liveness) · `foms/platform/app_factory.py:168`(init_sentry 유일 호출처) · `docs/incidents/2026-02-22-railway-worker-map-utils.md:12-16`(Worker offline 원인 절) · `scripts/maintenance/run_geocode_sweep.py:4-9`(SIDEFX 워커 미배포)
- D8 — `CLAUDE.md:48-51`(apps/api·services/·constants.py 안내) · `docs/ARCHIVE_INDEX.md:3`(손 갱신 규칙) · `Dockerfile:34-40`(런타임 매니페스트 4종 COPY) · `README.md:38`(DB_USER)·`README.md:46`(migration.py) · `docs/guides/SYSTEM_DOCUMENTATION.md:108`(jQuery)·`:114`(Google Cloud Platform)

### 5.1 재실행한 명령과 결정적 출력(보고서 인용값 대조)

```
cd C:/DEV/FOMS && echo "services->web: $(grep -rlE '^\s*(from|import) foms\.web' foms/services | wc -l)" (이하 같은 꼴로 api/services·핀·CSP·innerHTML·emit·워크플로 경보)
services->web: 8 · api->web: 53 · services->api: 15
핀 리터럴 테스트(?v=2026, tests/test_*.py): 90
CSP/HSTS(foms + app.py): 0 · innerHTML(static/js + templates): 657 · emit(foms): 7
워크플로 경보(slack|webhook|pagerduty|discord): 0
```

```
cd C:/DEV/FOMS && (보고서 스택 판정 절의 교체 비용 명령 원문 그대로)
route: 371 · render_template: 106 · url_for: 863 · 템플릿: 278 · Column(: 945 · test_client 파일: 256 / 672 · .query( 710 / select( 5
```

전부 보고서 인용값과 일치 — 불일치 0. 프롬프트 §6 이 인용을 허용한 route 367·Column 925·test_client 265 는 HEAD 이동·정규식 차이이며 보고서에 그 사실이 적혀 있다.

### 5.2 사실 카드 대비 재측정(통합자 실행)

| 값 | 사실 카드 | 재측정 | 명령 |
|---|---|---|---|
| 추적 파일 | 3,425 | 3,446 | `git ls-files` 줄 수 |
| docs/plans | 441 | 452(이 보고서 포함) | `ls docs/plans` 줄 수 |
| 커밋 2026-06-01 이후 | 2,765 | 2,767 | `git log --since=2026-06-01 --oneline` 줄 수 |
| 커밋 2026-08-01 이후 | 1,473 | 1,483 | `git log --since=2026-08-01T00:00:00+09:00 --oneline` 줄 수 |
| test_ 파일 | 671 | 672 | `git ls-files tests` 에서 `test_*.py` 개수 |
| foms 파이썬 줄 | 142,235 | 142,466 | `git ls-files foms` 의 `.py` 를 `wc -l` |
| 수집 테스트 | 9,879 | 9,913 | `PYTHONIOENCODING=utf-8 timeout 300 python -m pytest --collect-only -q -p no:playwright` |

판정에 영향을 주는 차이 없음(전부 HEAD 이동에 따른 소폭 증가). 운영 수치(사용자 수·주문량·트래픽·비용·기기 대수)는 하나도 추정하지 않았고 전부 보고서 열린 질문 절로 보냈다.

## 6. 수정 라운드 1회(CEO fix 반영 — 프롬프트 §7.1 5단계)

CEO 가 리뷰 두 판정을 합쳐 `fix` 를 냈고 통합자가 **1회** 반영했다(프롬프트 규칙: fix 는 1회, 반영 뒤 재판정 대기). 지적 4건 전부 반영했고 그 밖의 본문·판정·권고 문안은 건드리지 않았다.

### 6.1 지적 1 — 로드맵 '지금' 4번의 검증 명령이 실행 불가

- 고치기 전: `python tools/ops/check_sidefx_readiness.py --kinds NAVER_AUTO_DISPATCH` 가 exit 1 인지 본다.
- 고친 뒤(도구 무관 직접 질의): 스테이징에서 루프가 도는 동안 하트비트 표 `side_effect_worker_heartbeats`(`models.py:2677`)의 `NAVER_AUTO_DISPATCH` 행 `last_heartbeat_at` 이 tick 마다 갱신되고 루프를 kill 하면 60초 넘게 갱신이 멈추는지 + 워커 실패잡 1건이 Sentry 에 environment=staging 이벤트로 잡히는지. 준비 판정 CLI 일반화 자체는 로드맵 12~24개월 23번 항목이라고 명시했다.
- 검증(통합자 실행): `cd C:/DEV/FOMS && sed -n '40,62p' tools/ops/check_sidefx_readiness.py` → 인자는 `--max-heartbeat-age`·`--max-oldest-pending-lag`·`--max-expiry-scan-lag`·`--max-retention-scan-lag`·`--max-dead`·`--json` 여섯 개뿐, kinds 없음.
- 검증: `cd C:/DEV/FOMS && sed -n '43,50p' foms/services/sidefx_worker.py` → 45행 `WORKER_KINDS = (WORKER_KIND_DELIVERY, WORKER_KIND_EXPIRY_SCAN, WORKER_KIND_RETENTION)` 3종 고정; `sed -n '612,618p'` → 615행 `for kind in WORKER_KINDS:` 순회.
- 검증: `cd C:/DEV/FOMS && grep -n "side_effect_worker_heartbeats\|last_heartbeat_at" models.py | head -8` → `2677: __tablename__ = 'side_effect_worker_heartbeats'` · `2680: last_heartbeat_at = Column(...)`.

### 6.2 지적 2 — 갱신·반박한 수치 4곳에 명령·셈법 병기

| 위치 | 값 | 병기한 명령 | 출력 |
|---|---|---|---|
| 둘째 절 R5(및 첫째 절 D4 행) | CI 빨강 표본 20건 중 12건 자가 유발·실제 결함 1건 | `git log --since=2026-08-01 --no-merges --format='%h %s' \| grep -iE 'CI red\|CI 빨강\|red 해소\|red 복구\|\(ci\)\|CI 실패' \| sort -u -k2 \| wc -l` | 30 — 그 30줄에서 perf(ci) 5·docs 3·chore(ci) 1·docs(perf) 1 을 뺀 수정 커밋 20건, 유형 분류는 D4 워커 수작업이라고 적었다. 첫째 절 D4 행은 '표본 추출 명령·셈법은 ② R5' 로 가리킨다 |
| 일곱째 절 D5 | `!important` 2,656 | `grep -rho '!important' static/css templates \| wc -l` | 2656 — §5 의 1,529 는 `grep -rn '!important' static/css \| wc -l` → 1529 로 범위(static/css)가 명시된 값이라, 틀린 서술이던 '범위 미기재' 를 지우고 '줄 수 대 발생 수 셈법 차이' 로 고쳤다 |
| 일곱째 절 D8 | guides 25 중 18 갱신 | `ls docs/guides/*.md \| wc -l` 과 파일별 `git log -1 --format=%ad --date=short -- <파일>` | 25 / 18 — 사실 카드의 27 은 `ls docs/guides \| wc -l`(.md 아닌 항목 포함)로 다른 모집단임을 한 낱말로 밝혔다 |
| 일곱째 절 D4 | 보안 성격 테스트 37 · 33 | `git ls-files tests \| grep -iE 'secur\|auth\|xss\|csrf\|secret\|permission\|policy\|signing\|failopen\|rate_limit\|upload_auth' \| grep -vE '__init__\|geocode_retry\|baseline_policy\|channel_policy' \| wc -l` | 37 유지(명령 병기). D4 의 33 은 명령 원문이 없고 같은 취지 패턴 재실행이 34 라 재현 불가 — (가설) 로 내렸다 |

### 6.3 지적 3 — '인라인 script 64' 단위 명시

로드맵 12~24개월 22번의 래칫 기준선을 '인라인 script 태그 64(템플릿 46 — 래칫 기준선은 태그 수)' 로 고쳤다. 사실 카드·§5 의 '템플릿 43 → 46' 과 모순처럼 읽히던 것이 사라진다(46 은 템플릿 수, 64 는 태그 수).

### 6.4 지적 4 — 부록 D1 의 eventlet 항목 축소

- 고친 뒤: `app.py:64` 경고문과 `docs/guides/DEPLOYMENT_GUIDE.md:66-69` 가 eventlet 세대(실제는 gevent — `start.sh:76`)이고, `requirements.txt:112` 주석은 이미 gevent 로 정정됐다고 적었다.
- 검증: `cd C:/DEV/FOMS && grep -n eventlet requirements.txt app.py` → `app.py:64` 한 줄뿐.
- 검증: `cd C:/DEV/FOMS && sed -n '110,114p' requirements.txt` → 112행 `# 채팅 시스템 (Quest 5) + gunicorn gevent 워커 (배포 필수)`.
- 검증: `cd C:/DEV/FOMS && sed -n '76p' start.sh` → `exec gunicorn -k gevent -w 2 --timeout 120 …`; `sed -n '66,69p' docs/guides/DEPLOYMENT_GUIDE.md` → `--worker-class eventlet -w 1`.

### 6.5 수정 라운드 뒤 §8 재실행 원문

```
cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 python - docs/plans/2026-09-06-foms-system-review-report.md <<EOF (§8 스니펫 본문 글자 그대로)
ANCHOR_BAD 0
HANJA 0
```

1회에 통과 — 재시도 0회(허용 3회), `[가설]` 강등은 지적 2의 '33' 한 건뿐이다.

```
cd C:/DEV/FOMS && git status --short | grep -vE "system-review-report"
?? .claude/skills/diagnosing-bugs/
?? .claude/skills/handoff/
?? .claude/skills/wayfinder/
?? .claude/skills/writing-great-skills/
?? .env.bak-20260828
?? docs/plans/2026-09-04-as-legacy-stage-cleanup-plan.md
```

수정 라운드에서도 같은 6건뿐이다 — 다른 창·이전 작업의 미추적 파일이며 손대지 않았다.

## 7. 다음 단계(재디스패치 방지)

1. 리뷰어 2명(스펙·품질)을 병렬 호출한다 — 편집 금지, 워커 출력을 먼저 보지 말고 보고서와 저장소만 본다(프롬프트 §7.4).
2. CEO 가 두 판정을 합쳐 ship/fix/block 을 낸다. fix 면 수정 목록 파일 경로만 통합자에게 넘겨 **1회** 반영하고 재판정을 기다린다.
3. 통합·검증은 이 원장 3절에 원문이 있으므로 다시 돌리지 않는다. 다시 돌려야 하는 것은 리뷰 2와 CEO 판정뿐이다.
4. 커밋·푸시는 사용자 결정 사항이다 — 이 검토는 git 상태를 바꾸지 않았고 production push 금지 규칙을 지켰다.
