# FOMS 시스템 전체 개발 검토 보고서 (2026-09-06)

> 통합자가 워커 8명(D1~D8)의 감사 결과와 검토 프롬프트 §5·부록 A 를 대조해 쓴 보고서다. 판정 3축(더 필요한 것 · 부족한 것 · 스택 적합성)을 ③·④·⑤ 에서 이름 그대로 다루고, ①·② 는 그 3축으로 이어진다. 모든 항목에 `[확인됨: 앵커]` 또는 `[가설]` 을 붙였다. 운영 수치(사용자 수·주문량·트래픽·비용·기기 수)는 추정하지 않고 전부 ⑥ '확인 필요' 로 보냈다. 이 검토는 읽기 전용이며 코드 수정·패키지 설치·git 변경·push 를 하지 않았다.

**기준 커밋** — HEAD `062723348`(`cd C:/DEV/FOMS && git log --oneline -1`). 프롬프트 통합 시점 `58275b7e5` 에서 문서 커밋 1건(`git diff --stat 58275b7e5..HEAD` → `4 files changed, 1013 insertions(+)`, 전부 docs/plans), 코드 변경 0.

**사실 카드 대비 재측정(통합자 직접 실행)**
- 추적 파일 3,446 — `cd C:/DEV/FOMS && git ls-files | wc -l` (사실 카드 3,425)
- docs/plans 452(이 보고서 포함 — 쓰기 전 451) — `cd C:/DEV/FOMS && ls docs/plans | wc -l` (사실 카드 441·통합 시점 449)
- 커밋 2026-06-01 이후 2,767 · 08-01 이후 1,483 — `cd C:/DEV/FOMS && git log --since=2026-06-01 --oneline | wc -l; git log --since=2026-08-01T00:00:00+09:00 --oneline | wc -l` (사실 카드 2,765/1,473). 시각을 뺀 `--since=2026-08-01` 은 git 이 빈 자리를 실행 시각으로 채워 같은 HEAD 에서도 값이 흔들린다(오늘 1,479·워커 1,482 관측) — 결정적 값은 시각을 명시한 위 형식이다.
- test_ 파일 672 — `cd C:/DEV/FOMS && git ls-files tests | grep -c 'test_.*\.py$'` (사실 카드 671)
- foms 파이썬 142,466줄 — `cd C:/DEV/FOMS && git ls-files foms | grep -E '\.py$' | xargs wc -l | tail -1` (사실 카드 142,235)
- 수집 테스트 9,913 — `cd C:/DEV/FOMS && PYTHONIOENCODING=utf-8 timeout 300 python -m pytest --collect-only -q -p no:playwright | tail -1` → `9913 tests collected in 3.95s`
- 판정에 영향을 주는 차이는 없다(전부 HEAD 이동에 따른 소폭 증가).

**한 문단 결론** — 8차원 전부 **조건부**(워커 판정과 일치, 통합자가 뒤집은 판정 0). 시스템을 관통하는 구조는 하나다: *같은 사실의 사본을 사람의 규약으로 맞추고, 그 규약이 깨졌는지를 사고가 난 뒤에야 안다.* 데이터(JSONB 정본 ↔ 플랫 사본), 자산(내용 ↔ 날짜 핀), 정본 문서(정책 4벌 ↔ 코드 트리), 배포(저장소 toml ↔ 대시보드), 권한(쓰기 SSOT ↔ 읽기 세 갈래), 초록(로컬 smoke ↔ CI ↔ perf-gate)이 전부 이 모양이다. 사람 1명 + 에이전트가 3개월 2,767 커밋을 내는 속도에서 이 모양은 사고 반복(두 달 데이터 사고 4건·핀 사고 9일 4건·셸 봉합 12건)과 변경 증폭(커밋당 4.5파일, 핀 커밋 23%, CI 빨강 20건 중 12건 자가 유발)으로 이미 새고 있다. 스택(Flask 모놀리스 + Jinja + Vanilla JS + PostgreSQL JSONB + Railway)은 **조건부 유지** — 교체가 아니라 거버넌스 층(잠금·경계 래칫·해시 매니페스트·감독·읽기 SSOT·정본 1벌)을 이번 분기에 세우는 것이 답이다.

## ① 시스템 건강 지도

| 차원 | 판정 | 한 줄 근거 (통합자 검증 앵커) | 3축 연결 |
|---|---|---|---|
| D1 스택·의존성 | 조건부 | 핀(Flask 2.3.3·Werkzeug<3·Jinja2 3.1.2)이 업스트림 패치 창 밖이고 잠금·dev 분리·스캔·파이썬 정본이 전부 0 이지만, 상향 차단 요소는 4곳뿐이라 재작성 없이 올라갈 수 있다 [확인됨: `requirements.txt:31` · `requirements.txt:106` · `app.py:22-36` · `tests/conftest.py:26-28` · `ls pyproject.toml requirements.in .github/dependabot.yml` → 전부 No such file] | ③ 거버넌스 결핍 · ④ 이번 분기 상향 패킷 · ⑤ 조건부 유지 |
| D2 아키텍처 | 조건부 | 네임스페이스 계약은 테스트로 살아 있으나 계층 방향은 강제되지 않고(services→web 8·api→web 53·services→api 15, 방향 테스트 0) 분해 거버넌스는 2026-04-16 에 멈췄다 [확인됨: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:315-322` · `foms/services/settlement_aggregation.py:55-60` · `foms/persistence/main/models.py:3` · grep 출력 8/53/15] | ③ 변경 증폭 · ④ 방향 래칫 · ⑤ 유지 전제 |
| D3 데이터·마이그레이션 | 조건부(부적합 경계) | 사본 동기화 사고 4건이 같은 유형으로 반복됐고 09-01 원인 줄이 남아 있어 부적합 조건 둘을 채우지만, alembic head 1·downgrade 94/94·쓰기 감사 179/0·오프사이트 백업이 있어 '6일 백업 하나에 매달림' 은 아니다 [확인됨: `models.py:89-112` · `foms/services/erp_sync_columns.py:86-87` · `foms/services/integrations/naver_commerce/order_candidates.py:822-823` · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:20-30`] | ③ 사고 반복 · ④ 조회 축 승격 · ⑤ JSONB 조건 |
| D4 테스트·CI | 조건부 | 계약 테스트가 두텁고 CI 는 2~3분·최근 20런 초록이지만, CI 빨강 표본 20건 중 12건이 등재·핀·인벤토리 계약이 스스로 만든 세금이고(표본 추출 명령·셈법은 ② R5) '초록' 정의가 3겹이다 [확인됨: `.github/workflows/ci.yml:7-11` · `scripts/ops/pre_push_smoke.ps1:8` · `docs/plans/2026-08-26-ci-speed-ledger.md:95-98` · `tools/harness/ci_watch.py:404`] | ③ 세금 실측 · ④ 단일 초록 · ⑤ 계약 자산 |
| D5 프론트엔드 | 조건부 | 캐시 무효화가 사람이 고르는 날짜 핀 하나에 걸려 9일 4번 '같은 핀 다른 자산' 사고, 셸 3벌이 게이트 행렬로 갈라져 봉합 12건 [확인됨: `static/sw.js:82-93` · `static/sw.js:10-17` · `foms/platform/app_factory.py:60-69` · `templates/partials/shared/layout_head.html:210-217` · 커밋 156608706·603a4a92c] | ③ 핀 세금 · ④ 해시 매니페스트 · ⑤ Vanilla JS 조건 |
| D6 보안·권한·개인정보 | 조건부 | 쓰기는 매니페스트 SSOT(209 라우트)로 닫혔지만 읽기는 세 갈래로 흩어져 VIEWER 가 API 로 전 주문 열람, CVE 스캔·CSP·로그인 잠금·PII 정책 0 [확인됨: `foms/services/orders/order_mutation_policy.py:579-600` · `foms/services/orders/order_mutation_policy.py:385-405` · `foms/web/orders/edit.py:237-240` · `foms/services/rate_limit.py:58-70`] | ③ 302 무음 사고 · ④ 읽기 SSOT · ⑤ 유지 전제 |
| D7 운영·배포·관측 | 조건부(부적합 경계) | 워커 1대 안 무감독 루프 5개·web 전용 헬스체크·사람에게 닿는 경보 0·배포 정본 저장소 밖 — '소비자가 안 돈다' 실패가 6개월 간격으로 반복됐고 두 번 다 사용자가 발견했다 [확인됨: `start.sh:23-26` · `start.sh:72-76` · `foms/api/health.py:7-10` · `foms/platform/app_factory.py:168` · `docs/incidents/2026-02-22-railway-worker-map-utils.md:8-15` · `scripts/maintenance/run_geocode_sweep.py:4-9`] | ③ 사고 반복 · ④ 감독·경보 · ⑤ Railway 조건 |
| D8 개발 시스템 | 조건부 | 하네스는 실제로 막고 있으나(셸 가드 deny 70·Stop 게이트 exit 2) 정책 정본이 없는 경로 3개를 살아 있다고 말하고 색인은 2026-06-17 에 멈췄으며 런타임이 docs/harness JSON 을 읽어 스테이징 부팅이 한 번 깨졌다 [확인됨: `CLAUDE.md:48-51` · `ls -d apps services constants.py` → 전부 No such file · `docs/ARCHIVE_INDEX.md:3` · `Dockerfile:34-40` · 커밋 a90a38faf] | ③ 온보딩 결핍 · ④ 정본 1벌 · ⑤ 유지 전제 |

워커 판정과 다른 판정 0. D3·D7 은 워커가 '부적합 경계' 라고 적은 것을 통합자가 앵커로 재확인해 그대로 둔다(D3: 09-01 원인 줄 잔존 확인, D7: 두 사고 문서 확인).

## ② 상위 구조 리스크

각 항목: 제목(구조·흐름·거버넌스 수준) · 왜 시스템 문제인지 · 영향 시점 · 근거 앵커(2개 이상, 통합자가 직접 연 것) · 관련 차원 · 제품·팀 맥락. 파일 한두 개짜리 항목은 ⑦ 로 보냈다.

### R1. 주문 정본(JSONB)과 파생 사본을 DB 가 아니라 애플리케이션 호출 규약으로 동기화한다 — 사고 반복 · 지금 · D3(→ D2 키 레지스트리)
- 왜 시스템 문제인가: 9단계 워크플로·AS 축·네이버 매칭·권한 가시성이 전부 `structured_data` 의 파생값(`erp_stage_code`·`as_axis_status`·`erp_phone_digits`·레거시 `orders.phone`)으로 조회되는데, 사본을 맞추는 주체가 생성 컬럼·트리거가 아니라 `sync_erp_flat_columns` 호출 규약(27곳/19파일)이다. 쓰기 경로가 늘 때마다 '규약을 부른 경로' 와 '안 부른 경로' 가 갈리고, 두 달 안에 같은 유형 사고 4건(08-14 AS 55건·08-24 서버 키 소실·09-01 전화 세 사본·09-03 AS 2건)이 났다. 매 수정이 '가드 하나 더' 였고 사본 구조는 그대로다.
- 영향 시점: 지금 — 09-01 원인 줄이 수정 커밋 뒤에도 남아 있다.
- 근거 [확인됨]: `models.py:89-112`(정본 JSONB + 플랫 사본 9종 + AS 축 투영, 주석이 08-14 사고를 직접 기록) · `foms/services/erp_sync_columns.py:86-87`(sync 함수는 `erp_phone_digits` 만 갱신, `orders.phone` 은 규약 밖) · `foms/services/integrations/naver_commerce/order_candidates.py:822-823`(`Order.phone == digits` 잔존) · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:20-30` · `docs/guides/DATA_INCIDENT_RECOVERY.md:3-4` · `docs/AI_STATUS.md:17-18` · `foms/api/erp_orders_structured.py:231-235`(보존 목록을 사람이 유지)
  드리프트 감사 도구 배선 0(D3 워커 grep: `.github/workflows/*.yml start.sh predeploy.sh` 에 `audit_as_axis_drift|audit_erp_flat_columns` 0건)
- 제품·팀 맥락: 현장 태블릿·iOS 에서 AS 접수·실측이 들어오고 네이버 주문이 전화로 매칭되는 ERP 에서, 사본 어긋남은 화면 오류가 아니라 '주문이 목록에서 사라지는' 사고로 나타난다. 사람 1명 + 에이전트 속도에서 새 쓰기 경로(마법사·네이버·정산·태블릿)는 계속 늘어난다.

### R2. 계층 경계가 디렉토리 이름일 뿐 의존 방향으로 강제되지 않고, 분해 거버넌스는 2026-04-16 에 멈췄다 — 변경 증폭 · 지식 집중 · 지금 · D2(권한 증폭 포함)
- 왜 시스템 문제인가: 정본 스펙이 금지한 services→web(8)·api→web(53)·services→api(15) 이 남아 있고 방향 테스트가 0 이라 에이전트가 하루 30커밋 속도로 역방향을 넣어도 CI 가 잡지 못한다. 함수 안 지연 import 473곳이 순환을 숨긴다. 횡단 관심사(ROLES·TEAMS·login_required)가 web 라우트 모듈에 있어 82파일이 web 을 향하고 회계팀 권한 1건이 22파일로 번졌다. 스펙 임계치 500줄 아래서 `naver_ingest.py` 가 24일 만에 196→5,999줄이 돼 114커밋 중 fix 46 의 반복 수정 지점이 됐다.
- 영향 시점: 지금(변경 증폭 실측: 200커밋 평균 4.54파일, fix 커밋 5.81파일).
- 근거 [확인됨]: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:315-322`(경계 규칙 표) · `foms/services/settlement_aggregation.py:55-60`(services 가 web private 함수 역수입) · `foms/services/integrations/naver_commerce/triage_count.py:118`(통합 패키지가 web 지연 import) · `foms/web/auth/routes.py:53`(ROLES 정의 위치) · `foms/persistence/main/models.py:3`(`from models import *` 껍데기) · `models.py:18-19`(퍼시스턴스→서비스 역방향) · `docs/AI_STATUS.md:39`(분해는 future batch) · `git show --stat d243c8e50` → `22 files changed, 366 insertions(+), 158 deletions(-)` · `git show --stat 0c66f6d61` → `7 files changed`
- 제품·팀 맥락: 팀 축(SALES·CS·ACCOUNTING·CONSTRUCTION·DRAWING)이 9단계마다 다른 범위를 갖는 ERP 에서 팀 하나 추가가 22파일이면, 두 번째 개발자는 한 파일(6k 줄)을 아는 사람 없이는 고칠 수 없다. 네이버 API 규격 변경은 web·services·JS 3벌이 같이 움직인다(114커밋 중 73 동시 변경).

### R3. 사업상 되돌릴 수 없는 작업이 단일 워커의 무감독 루프 5개에 얹혀 있고, 죽어도 사람에게 알리는 경로가 없으며, 배포 정본은 저장소 밖에 있다 — 단일 장애점 · 사고 반복 · 지금 · D7
- 왜 시스템 문제인가: 루프 5개(에스컬레이션·수집·자동 발송·정산·지오코딩 스윕)는 `&` 로 뜨고 셸은 `exec rq worker` 로 대체돼 wait/trap/supervisor 가 0, 하트비트도 0 이다. `/healthz` 는 설계상 liveness 만, `init_sentry` 호출처는 web 한 곳, 워크플로 7개에 알림 0. 그래서 '소비 프로세스가 안 돈다' 실패가 2026-02(워커 offline)와 2026-08-31(SIDEFX 미배포)에 반복됐고 두 번 다 사용자가 지도에서 발견했다. Railway 가 Config as Code 를 폐기해 toml 5벌은 사문이고 워커 시작 명령은 toml(루프 0)과 start.sh(루프 5)로 모순, 서비스 구성은 비공개 저장소에만 있다. 네이버 IP 한도 3 때문에 이 컨테이너가 네이버 HTTP 단일 출구라 복제로 풀 수도 없고, 재배포는 곧 큐 정지(08-31 47집 852초)다.
- 영향 시점: 지금.
- 근거 [확인됨]: `start.sh:23-26` · `start.sh:32-33` · `start.sh:72-76`(`&` 5개 = 25·36·48·59·72행, `exec rq worker`) · `foms/api/health.py:7-10` · `foms/platform/app_factory.py:168`(init_sentry 유일 호출처) · `foms/services/jobs/tasks.py:25-27` · `docs/incidents/2026-02-22-railway-worker-map-utils.md:8-15` · `scripts/maintenance/run_geocode_sweep.py:4-9` · `railway-worker.toml:4-7` vs `start.sh:72-76` · `docs/plans/2026-08-31-geocode-prefetch-restore-ledger.md:392-404` · `tools/ops/check_worker_redeploy_safe.py:1-12` · `tools/ops/wait_for_redis.py:1-12`(13시간 정지)
  `grep -rliE 'slack|webhook|pagerduty|discord' .github/workflows/*.yml | wc -l` → 0
- 제품·팀 맥락: 평일 16:50 네이버 자동 발송처리는 되돌릴 수 없는 작업이고, 실측·시공 일정은 지오코딩 좌표에 걸려 있다. 현장 태블릿·iOS 사용자가 곧 모니터링 장치인 구조다.

### R4. 자산 신선도가 '내용→URL' 매핑을 사람 손에 둔 날짜 핀 규약 하나에 걸려 있고, 셸 3벌이 템플릿 게이트 행렬로 갈라져 같은 기능을 셸마다 따로 배선한다 — 사고 반복 · 변경 증폭 · 지금 · D5
- 왜 시스템 문제인가: SW `staticCacheFirst` 는 URL(=?v 값)을 키로 TTL 5분 안에서 캐시본을 즉시 응답하므로 '내용이 바뀌면 사람이 핀을 올린다' 는 규약이 깨지는 순간 운영이 stale JS 를 서빙한다. 병렬 세션이 같은 날 같은 값을 고르는 구조라 8-27~9-04 사이 4번 '같은 핀 다른 자산' 사고가 났고, 핀 리터럴을 못 박은 테스트 52파일 90곳이 무관 커밋까지 빨갛게 만든다(6월 이후 핀 커밋 643/2,767 = 23%). 자산 로드는 `layout_head.html` if 사슬(`shell_variant`·`erp_mobile_v2_enabled` 조합)에 흩어져 새 기능이 v3 에서 통째로 빠지거나 v2 마크업이 v3 로 누출됐다(봉합 커밋 12건, 8-24 알림톡 칩 재발). 주문 폼은 PC·모바일·태블릿 3벌(태블릿 2,873줄이 '미로드라 자체 구현' 미러 28곳).
- 영향 시점: 지금.
- 근거 [확인됨]: `static/sw.js:82-93` · `static/sw.js:10-17`(v9 사고 기록) · `foms/platform/app_factory.py:60-69`('CSS/JS are NOT hashed') · `templates/partials/shared/layout_head.html:176-180` · `templates/partials/shared/layout_head.html:210-217`(봉합 주석) · `foms/services/context_processors.py:310-316` · `foms/services/feature_flags.py:257-262` · `static/js/foms/tablet-measure-form.js:215` · `docs/AI_CHANGELOG.md:39` · 커밋 156608706(08-27)·6740af20b(09-01)·603a4a92c(09-04)·6dde61f04(07-12) · `grep -rn '?v=2026' tests --include=test_*.py | wc -l` → 90
- 제품·팀 맥락: MEASURE·CONSTRUCTION·CS 단계가 현장 태블릿·iOS 웹뷰에서 돌아가고, 금액·자유입력 로직이 3벌이면 현장과 사무실의 출고가가 어긋날 씨앗이 구조에 있다.

### R5. '초록' 의 정의가 세 겹으로 갈려 있고 계약 테스트 4겹 등재 구조가 기능 1건마다 변경 세금을 부과한다 — 변경 증폭 · 사고 반복 · 지금 · D4
- 왜 시스템 문제인가: AGENTS.md 는 'CI green 까지가 push 완료' 라 하지만 로컬 smoke 는 21타깃 서브셋이고 push 를 막지 않으며(속도 원장이 exit 1 인데 `;` 로 이어 푸시했다고 자백), perf-gate 는 deploy push 에서 권고 전용, ci_watch 는 '런 없음' 을 green 으로 센다. 승격 PR 이 본 스위트를 한 번도 안 돌아 운영만 터진 사고 3건 뒤에야 트리거가 추가됐다. 자산 하나를 고치면 템플릿 핀 → 테스트 핀 리터럴 → docs/harness 인벤토리 → ci.yml 서브셋 등재 최대 4곳을 손으로 맞춰야 하고, 8월 이후 CI 빨강 수정 커밋 20건 중 12건이 이 구조가 만든 것이며 실제 결함은 1건이다. SQLite 본 레인 + 선택 가입 PG 레인 이중 구조라 FK·EXPLAIN 사각이 'CI 에서만 터지는' 빨강 3건을 냈고 PG 레인 켜는 변수는 문서에 0건이다.
- 영향 시점: 지금.
- 근거 [확인됨]: `.github/workflows/ci.yml:7-11`(CI-PROMOTE-01 사고 3건) · `scripts/ops/pre_push_smoke.ps1:8`('Does NOT run on git push automatically') · `docs/plans/2026-08-26-ci-speed-ledger.md:95-98` · `.github/workflows/perf-gate.yml:55-69` · `tools/harness/ci_watch.py:404` · `tests/domains/test_docs_facing_registry.py:1-9` · `scripts/ops/pre_push_smoke.ps1:221-222` · `tests/conftest.py:87-88` · `tests/postgres/conftest.py:142` · 커밋 6740af20b(핀 충돌)·42e9cde89(실제 결함)
  CI 빨강 표본 셈법: `git log --since=2026-08-01 --no-merges --format='%h %s' | grep -iE 'CI red|CI 빨강|red 해소|red 복구|\(ci\)|CI 실패' | sort -u -k2 | wc -l` → 30. 그 30줄에서 perf(ci) 5·docs 3·chore(ci) 1·docs(perf) 1 을 뺀 수정 커밋이 20건이고, 유형 분류(등재 8·핀 3·PG 레인 3·CI 인프라 3·세션 충돌 1·flaky 1·실제 결함 1)는 D4 워커 수작업이다.
- 제품·팀 맥락: 여러 에이전트 세션이 같은 워킹트리에서 하루 수십 커밋을 내는 팀에서 '초록' 이 하나가 아니면 승격 판단이 사람의 해석에 걸린다.

### R6. 의존성·런타임 거버넌스가 0 이라 '재현 가능한 빌드' 가 없고 핵심 프레임워크 핀이 패치 창 밖에 있다 — 사고 반복 · 지식 집중 · 지금(이번 분기) · D1(→ D6 CVE 스캔)
- 왜 시스템 문제인가: 잠금·requirements.in·dev 분리·dependabot·pip-audit 전부 없고 상한 없는 floating 17개라 로컬·CI·Railway 이미지가 서로 다른 버전 집합을 돈다(로컬 Jinja2 3.1.6·holidays 0.99 vs 핀 3.1.2·0.42, pip check 충돌 4). 파이썬 표기 3갈래(.python-version 3.11.9 / Dockerfile 3.12 / CI 3.12)에 패치 버전 차이만으로 AS 본문 텍스트가 조용히 사라진 버그가 났다. Flask 2.3.3·Werkzeug 2.3.8·Jinja2 3.1.2 의 알려진 수정은 전부 3.x 에만 있는데 상한 핀 사유는 커밋 본문 어디에도 없고 몽키패치 13줄은 무동작이다. 의존성 목록은 2026-01-16 데스크톱 pip freeze 덤프에서 굳어 런타임 무관 패키지(fastapi·starlette·python-jose 등)가 CVE 목록을 늘린다.
- 영향 시점: 지금 — 워커 판정 '이번 분기 안에 상향 패킷 + 거버넌스 층을 세우지 않으면 부적합'.
- 근거 [확인됨]: `requirements.txt:31` · `requirements.txt:49` · `requirements.txt:106` · `app.py:22-36` · `tests/conftest.py:26-28` · `.github/workflows/ci.yml:26-28`(CI 주석 스스로 floating 문제 기록) · `git show f40e6a36c -- requirements.txt` → `-Werkzeug==2.3.7 / +Werkzeug>=2.3.5,<3`(본문에 사유 0) · 커밋 777076423(파서 버전 유실)·75b635beb·ede84eeb8(빌드 실패 2건) · `ls pyproject.toml requirements.in .github/dependabot.yml` → 전부 No such file · OSV 조회(D1 워커 실행 출력: Flask 2.3.3 권고 2·Werkzeug 2.3.8 권고 12·Jinja2 3.1.2 권고 10)
- 제품·팀 맥락: 도면·현장 사진 업로드(다중파트)와 템플릿 렌더가 알려진 권고의 직접 표면이고, 영업일·자동 발송 시각 창은 holidays 판 차이로 날짜가 샌다.

### R7. 권한 판정이 쓰기에만 SSOT 이고 읽기는 세 갈래로 흩어졌으며, 고객 개인정보 수명주기 정책은 문서·코드 어디에도 없다 — 변경 증폭 · 비용 · 지금 · D6
- 왜 시스템 문제인가: 쓰기는 매니페스트 209 라우트를 before_request 한 곳에서 판정하지만 읽기는 `login_required`(API 248곳, 실패 시 302 HTML)·`user_can_read_order`(order 인자 미사용, 전 역할 True)·`role_required` 6종 조합으로 갈려 웹 페이지는 VIEWER 를 거부하고 API 는 허용한다. 역할 하나·외주 기사 계정 하나를 늘리면 248개 데코레이터를 손으로 훑어야 하고, 놓친 곳은 '시공팀 벨·푸시 무음' 302 사고로 나타났다. 전화·주소는 주문·감사 로그·발송 로그·공유 견적·R2 사진 다섯 곳에 복제되는데 보존기간 문서 0, 마스킹 헬퍼는 국소 2개, purge 기본값(3년/2년)과 사용자 결정(영구 보존)이 어긋난 채다. fail-open 587 catch 중 무로그 216 에 auth 6·레이트리미터 2 가 포함돼 열림이 관측되지 않는다.
- 영향 시점: 지금.
- 근거 [확인됨]: `foms/services/orders/order_mutation_policy.py:579-600` · `foms/services/orders/order_mutation_policy.py:385-405` · `foms/web/auth/routes.py:247-267` · `foms/web/orders/edit.py:237-240` · `foms/platform/http.py:238-260`('인가 경계가 아니다' + 302 무음 사고 기록) · `foms/services/rate_limit.py:58-70` · `foms/services/rate_limit.py:27` · `foms/api/share.py:7-9` · `tools/ops/purge_audit_logs.py:9-16` vs `docs/plans/2026-08-13-order-change-retention-measurement.md:5-7` · `docs/plans/2026-08-07-audit-retention-analysis.md:338`(masked 필드 30.6% 전화 잔존)
  `foms/services/order_share.py:119-121` · 커밋 73320a30c
- 제품·팀 맥락: 채널톡 퀵액션·현장 태블릿·iOS 웹뷰·사무실 PC 가 같은 주문을 읽고, 정보주체가 늘수록 법적 노출과 처리 비용이 함께 커지는데 결정 지점이 없다.

### R8. 정책 정본 4벌이 없는 경로를 살아 있다고 말하고, 지식 색인은 2026-06-17 에 멈췄으며, 개발 하네스 산출물이 운영 런타임의 부팅 의존성이다 — 지식 집중 · 단일 장애점 · 지금 · D8(문서 드리프트·사고 원장 분산·매니페스트 결합 병합)
- 왜 시스템 문제인가: CLAUDE.md·cursor 정본이 2026-04-12 에 사라진 `apps/`·루트 `services/`·`constants.py` 를 현행 구조로 안내하고, 8월 ablation 재작성도 이를 지나쳤다(정본 갱신에 코드 대조 단계 없음). ARCHIVE_INDEX 는 손 갱신 규칙 아래 7월 이후 plans 134·specs 61 이 색인 0 이고 세션 메모리 159파일이 사용자 홈에만 있다. 데이터 사고 4건 중 incidents 등재는 1건, 운영 사고(13시간 정지·852초·DEAD 1,188·실패잡 2,544)는 도구 docstring·AI_STATUS 에만 있다. 앱이 부팅 시 읽는 매니페스트 4종이 docs/harness 에 살아 .dockerignore 예외 + Dockerfile COPY 로 버티고, 3자 일치 테스트가 없어 2026-07-28 스테이징 부팅이 실제로 깨졌다. README 는 없는 파일을 지시하고 규칙이 가리키는 스킬 4종은 git 미추적이다.
- 영향 시점: 지금(온보딩)·6개월(다음 ablation 2027-02 가 오염된 기록으로 판정).
- 근거 [확인됨]: `CLAUDE.md:48-51` · `.cursor/rules/00-project-context.mdc:31` · `ls -d apps services constants.py` → 전부 No such file · `docs/ARCHIVE_INDEX.md:3` · `git log -1 -- docs/ARCHIVE_INDEX.md` → `9f9e6bdf7 2026-06-17` · `Dockerfile:34-40` · `.dockerignore:27-33` · `foms/services/request_write_guard.py:10` · `foms/services/orders/order_mutation_policy.py:19` · 커밋 a90a38faf(2026-07-28) · `README.md:38` · `README.md:46` · `docs/guides/SYSTEM_DOCUMENTATION.md:108`(jQuery)·`docs/guides/SYSTEM_DOCUMENTATION.md:114`(GCP)
  `docs/harness/policy/DECISIONS.md:35`(ept_b8 'DEAD 삭제') vs `.github/workflows/perf-gate.yml:44`(라이브 의존) · `tools/ops/wait_for_redis.py:1-12` · `git status --short .claude/skills` → `??` 4개
- 제품·팀 맥락: 사람 1명이 에이전트 세션을 갈아타며 개발하는 구조에서 '새 세션' 이 곧 두 번째 개발자다. 정본이 거짓이면 매 세션이 재탐색 비용을 내고, 하네스 변경이 운영 부팅 실패로 번지는 경로가 열려 있다.

## ③ 부족한 것

결핍이 **이미** 사고·속도 저하·비용으로 새고 있는 곳. 항목마다 '새는 증거'(사고 문서·커밋·실측 출력) 앵커를 붙였다. 워커 `lacking` 에서 출발해 중복은 가장 구조적인 차원에 한 번만 두었다.

### D1 스택·의존성
- **의존성 거버넌스 층 0 → 빌드 실패·API 드리프트·권고 누적으로 샘.** 의존성 1건 추가가 Railway 빌드 실패 2건, floating rq 가 2.0 breaking 을 당겨오자 전용 CI 레인 신설, production 승격에서만 터진 사고 3건 중 'solapi 미설치' 가 의존성 유형. [확인됨: 커밋 75b635beb·ede84eeb8('Railway 빌드 실패(ResolutionImpossible)') · `.github/workflows/ci.yml:26-28` · `.github/workflows/ci.yml:7-11` · pip-audit·ruff 없음(`pip-audit: command not found`)]
- **세 환경(로컬·CI·운영) 버전 불일치 → 데이터 유실 버그.** 3.12.10 vs 3.12.13 html.parser 차이로 AS 본문 텍스트가 조용히 사라짐. 로컬 설치판이 핀과 다름(holidays 0.99 vs 0.42). [확인됨: 커밋 777076423 · `requirements.txt:119` · D1 워커 실행 출력 `pip check` 충돌 4건]
- **운영 토폴로지(gunicorn gevent + Socket.IO gevent + Redis)가 로컬·CI 어디서도 실행되지 않아 사고가 운영에서만 보였다.** [확인됨: `docs/context/INCIDENT_RAILWAY_GEVENT_SOCKET_2026-02-20.md:4-16` · `foms/services/jobs/queue.py:47-52`(2026-07-21 Redis 장애 주석) · APP_OK 출력 'Socket.IO initialized in threading mode']
- **스택 결정 기록(ADR) 0 → 무동작 몽키패치·사유 없는 상한 핀·2020년 psycogreen 이 7개월째 그대로.** [확인됨: `app.py:22-36` · `git show f40e6a36c -- requirements.txt` · `docs/harness/policy/DECISIONS.md:27-30`(스택 항목 0) · `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:43`(pyproject 보류)]

### D2 아키텍처
- **변경 증폭 실측.** 2026-08-15 이후 200커밋 평균 4.54파일, fix 68건 평균 5.81파일, 400커밋 중 fix 107(27%); 단계 라벨 1건 7파일, 회계팀 1건 22파일; `erp-order-shared.js` 3개월 121커밋·fix 69·파일명을 읽는 테스트 22파일. [확인됨: `git log --since=2026-08-15 -n 200 --format=%h --shortstat` 집계 → `n=200 avg=4.54` · `git show --stat d243c8e50` → 22 files · `git show --stat 0c66f6d61` → 7 files · `tests/domains/test_erp_order_shared_form_scripts.py:1143`]
- **네이버 web 모듈이 반복 수정 지점.** 114커밋 중 fix 46, 09-02·09-04 이틀에 fix 8건 집중, IP 한도 3 단일 출구 제약이 docstring 에만. [확인됨: `foms/web/admin/naver_ingest.py:10-13` · `git log --oneline -- foms/web/admin/naver_ingest.py | wc -l` → 114 · `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:26-30`]
- **외부 통합 어댑터 부재가 도메인 코드로 샘.** web 이 integrations 정책 상수를 import, api 가 외부 HTTP 직접 호출, common 패키지에 kakao/geocode/order 낱말 94회. [확인됨: `foms/web/admin/naver_ingest.py:36-37` · `foms/api/address.py:132` · `foms/services/integrations/naver_commerce/fulfillment.py:102` · `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:260`]
- 정본 문서가 없는 경로를 가리키는 문제 → R8/D8 참조.

### D3 데이터
- **같은 유형 데이터 사고 4건·원인 잔존.** 08-14(status 덮어쓰기 55건) → AS-AXIS-01 로 사본 하나 더 → 09-03 그 사본 이탈 → 봉인 가드; 08-24 → 보존 목록에 키 추가; 09-01 → 매칭 축 복구, 원인 줄 그대로. incidents 등재는 09-01 한 건, DECISIONS 에 AS 축 결정 0. [확인됨: `docs/AI_CHANGELOG.md:48-50` · `docs/AI_STATUS.md:17-18` · `foms/api/erp_orders_structured.py:262-264` · `foms/services/integrations/naver_commerce/order_candidates.py:822-823` · `ls docs/incidents` → 2026-02 4건·09-01 1건 · D3 워커 실행 출력 `grep -nE 'AS-AXIS|as_axis' DECISIONS.md` → 0]
- **복구 능력이 문서·훈련이 아니라 도구에만.** RPO 24h/RTO 4h 는 2026-03-20 스펙에만, 실제 보존 6일·직전 스냅샷 17시간 전·55건 중 20건 추론 복구, 오프사이트 6회 전패 후 08-19 첫 성공, 리허설 실행 기록 이 저장소 0, data_doctor 는 JSONB 본문 미지원. [확인됨: `docs/specs/2026-03-20-production-backup-and-restore-plan.md:48-50` · `docs/guides/DATA_INCIDENT_RECOVERY.md:104-105` · `docs/AI_CHANGELOG.md:48` · `foms/services/backup_status.py:37` · D3 워커 grep `RPO|RTO|리허설` DR 3문서 → 0]
- **되돌리기 원장이 상태 축에는 있고 본문 축에는 반쪽.** 필드 변경 원장 writer 호출 9파일 vs structured_data 를 커밋하는 파일 약 40, 복구 도구는 그 원장을 읽지 않음. [확인됨: `foms/services/orders/order_field_change_writer.py:1-8` · `models.py:915-921` · D3 워커 실행 출력 data_doctor 원장 참조 0]
- **레거시 컬럼(orders.phone) 읽기 14곳이 남아 정규화 승격이 절반에서 멈춤.** [확인됨: `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:101-108`(수정을 다른 배포로 보류) · `foms/services/erp_dashboard_search.py:47-49`]

### D4 테스트·CI
- **계약 등재·핀 리터럴 세금.** 등재 누락 빨강 4건이 08-27~08-31 닷새에 반복, 등재 목록이 낡아 red 가 2주 반 조용히 살았다, 코드 변경 커밋 146건 중 tests 동반 130(89%). [확인됨: `.github/workflows/ci.yml:155-158` · 커밋 464d4c257·73bd35a37·f665c7415·86e91a1f6(CI-DOCSCOPE-01) · 커밋 781f1bafe · D4 워커 집계 출력 `표본 커밋 300 | 코드 변경 146 | tests 동반 130`]
- **로컬 게이트와 CI 가 같은 것을 보지 않는다.** 시각 계약 충돌·PG 전용 빨강 3건·병렬 순서 의존이 전부 push 뒤 발견, smoke exit 1 이어도 푸시가 나감. [확인됨: 커밋 6740af20b 본문 'pre_push_smoke 서브셋과 로컬 기본 실행이 tests/visual 을 제외해 로컬에서는 초록' · 커밋 9bc598467·569e4c151·80b4945ba · `docs/plans/2026-08-26-ci-speed-ledger.md:95-98` · `AGENTS.md:73`]
- **'테스트는 있었는데 못 잡은' 사고 유형에 커버리지·픽스처 현실성 도구 0.** [확인됨: `docs/incidents/2026-09-01-naver-triage-auto-match-miss.md:101-108` · `docs/guides/DATA_INCIDENT_RECOVERY.md:3-4` · `pip show pytest-cov` → not found]
- **린트·타입 부재 → except 에 삼켜진 NameError 2사례(반복 결함 수준은 아님).** [확인됨: 커밋 c63ef424a·1cd00528d · `tests/domains/test_static_js_syntax.py:1-6`(JS 는 파서 게이트 있음)]
- **'초록' 뜻이 도구마다 달라 승격이 사람 해석에.** PR #223 이 남의 회귀에 막힘. [확인됨: 커밋 6c14d7fc4 · `.github/workflows/perf-gate.yml:3-7` · `tools/harness/ci_watch.py:194-207` vs `.github/workflows/perf-gate.yml:24-26`]

### D5 프론트엔드
- **콘텐츠 해시 매니페스트 부재 → 핀 사고 6건.** 같은 핀 다른 자산 4 + 세션 분리 1 + SW 구버전 2클릭 미반영 1, 핀 없는 로컬 자산 23곳은 매 로드 no-cache. [확인됨: 커밋 156608706·6e8a6f75e·c956fc600·603a4a92c·6740af20b·54b216c2b · `git show -s --format=%b 5d3464018` → '날짜 핀은 여러 세션이 같은 날 같은 값을 고르므로 필연' · `static/sw.js:10-17` · `tests/performance/test_static_cache_headers.py:63-66`]
- **셸 공용 계층 부재 → 같은 유형 봉합 12건, 8월 재발.** [확인됨: 커밋 6dde61f04·fb80ea6a9·ba22a08ac · `templates/partials/shared/layout_head.html:210-217` · `docs/AI_CHANGELOG.md:39` · `static/js/foms/tablet-measure-form.js:215`]
- **JS 실행 계약 부재 → 6k 줄 공용 파일 fix 비율 57%.** node 실행 계약은 wdcalculator 13파일·orders 0. [확인됨: `git log --since=2026-06-01 --format=%s -- static/js/orders/erp-order-shared.js | grep -c '^fix'` → 69/121 · `tests/contracts/wdcalculator/_node_runner.py:1` · `tests/performance/test_perf_regression_guard.py:3-5`(가드가 실제 장애에서 도출됐다는 자기 기록)]
- **인라인 집행 장치 부재 → 공용 파셜 2개가 인라인 부트 1,856줄을 품은 6월 이후 199커밋 핫스팟, 외부화 사본 2파일은 로드 0.** [확인됨: `templates/partials/shared/layout_scripts.html:369` · `templates/partials/shared/layout_head.html:1263-1265` · `grep -rl 'layout-head-init.js' templates | wc -l` → 0 · `tools/design/ssot_lint.py:25-38`(문구 9개만 검사)]

### D6 보안·권한·개인정보
- **읽기 권한 경계 부재 → '페이지 제한' 을 인가로 착각한 302 무음 사고, 회계팀 1건이 팀 게이트 8곳.** [확인됨: `foms/platform/http.py:238-260` · 커밋 73320a30c(2026-08-05) · `docs/AI_STATUS.md:19` · `foms/services/orders/order_mutation_policy.py:49-56`]
- **감사 원장이 개인정보 저장소가 됐다.** 운영 실측(2026-08-07): security_logs 전화 12.6%·주소 11.8%, masked 필드 30.6% 전화 잔존; 모델 docstring 은 'PII 원문 금지' 인데 강제 헬퍼·테스트 0. [확인됨: `docs/plans/2026-08-07-audit-retention-analysis.md:338` · `models.py:1214-1224` · D6 워커 grep `mask|redact|phone` audit_writer.py → 0]
- **무로그 fail-open 이 인증·레이트리밋 경로에 잔존.** 인벤토리 baseline 은 '무성장' 만 고정. [확인됨: `foms/services/rate_limit.py:27` · `foms/services/rate_limit.py:36` · `tests/domains/test_failopen_inventory.py:11-16` · D6 워커 출력 `has_logging False: 216`]
- **브라우저·의존성 경계 방어가 2026-07-24 스냅샷 이후 미갱신.** 싱크 인벤토리 커밋 1건 이후 static/js 269·templates 474 커밋, CSP 0·innerHTML 657. [확인됨: `docs/harness/foms_untrusted_dom_sinks.json:3-5` · `tests/domains/test_stored_xss_sinks.py:181-197` · `grep -rnE 'Content-Security-Policy|Strict-Transport-Security' foms app.py | wc -l` → 0]
- **보안 테스트가 '어디 있는지' 분류 체계가 말해주지 않음.** tests/security 0바이트, 파일명 기준 37파일 산재, DECISIONS 보안 결정 0. [확인됨: `tests/security/__init__.py` 0바이트 · D6 워커 출력 `grep -c AUTH-01 DECISIONS.md` → 0]

### D7 운영·배포
- **'소비자가 안 돈다' 실패 모드가 6개월 간격 반복, 두 번 다 사용자 발견.** [확인됨: `docs/incidents/2026-02-22-railway-worker-map-utils.md:8-15` · `scripts/maintenance/run_geocode_sweep.py:4-9` · `docs/AI_STATUS.md:68`]
- **운영 사고 4건이 사고 원장 밖.** 13시간 정지·852초·DEAD 1,188·실패잡 2,544 가 도구 docstring·AI_STATUS·커밋에만(§5 D8 의 '앵커 없음' 가설은 여기서 해소 — 원장이 아니라 도구 docstring 이 앵커다). [확인됨: `tools/ops/wait_for_redis.py:1-12` · `tools/ops/check_worker_redeploy_safe.py:1-12` · `docs/AI_STATUS.md:65` · `docs/AI_STATUS.md:97-98` · 커밋 e31dd8e51 · `grep -rlE '852|2,544|13시간|1,188' docs/incidents | wc -l` → 0]
- **환경변수 정본 공백이 이미 사고.** 문서 31줄·표 0행(2026-04-15) vs 코드 env 키 79, SIDEFX 에 KAKAO_REST_API_KEY 부재가 DEAD 1,188행 트리거('조사가 서비스 3개만 봤다'), 존재 검사 도구 배선 0, 문서가 권하는 부트스트랩이 alembic 소유 원칙과 충돌. [확인됨: `docs/AI_STATUS.md:65` · `docs/guides/RAILWAY_ENV_VARS.md:29` · `tools/ops/check_deploy_secrets.py:1-12` · `foms/services/app_init.py:154-160` · D7 워커 grep check_deploy_secrets 호출자 → 0]
- **외부 의존 6종(네이버 토큰·정산 쿼터·카카오·Redis·R2·Cloudflare)의 실패 모드가 조각으로만.** 자동 복구 + 사람 절차가 짝으로 갖춰진 것은 Redis 부팅 레이스 하나. [확인됨: `foms/services/integrations/naver_commerce/client.py:369-373` · `foms/services/integrations/naver_commerce/settle_sync.py:446-454` · `foms/services/rate_limit.py:66` · `docs/incidents/2026-02-23-503-ssl-unexpected-eof-cloudflare.md:1`; 정산 403 뒤 사람 절차 위치는 [가설]]
- **재배포에 잘리는 상태 회수 규약 0.** RUNNING 잔류(운영 10·11)·RQ Retry 0·재배포 안전 판정 배선 0. [확인됨: `foms/services/integrations/naver_commerce/settle_sync.py:819-823` · `docs/plans/2026-09-04-settlement-tab-cfo-review-prompt.md:53` · `foms/services/feature_flags.py:443-446` · D7 워커 grep `Retry|retry=` foms/services/jobs → 0]

### D8 개발 시스템
- **두 번째 개발자의 첫 부팅 경로 없음.** README 가 db.py 가 읽지 않는 DB_USER 와 없는 migration.py 를 지시(2026-04-15), 온보딩 문서 0, 루트 .env.example 미추적, 스킬 4종 한 번도 추적된 적 없음. [확인됨: `README.md:38` · `README.md:46` · `grep -c DB_USER db.py` → 0 · `git ls-files .claude/skills` → overnight 1파일 · `git status --short .claude/skills` → `??` 4개]
- **정본 갱신이 코드와 대조되지 않아 세 층(정책·아키텍처 안내·프롬프트 템플릿)에서 낡은 서술이 살아 있다.** 단 드리프트된 경로를 실제로 따른 커밋은 0(apps/ 재생성 0) — 부적합 아님의 근거. [확인됨: `docs/guides/SYSTEM_DOCUMENTATION.md:108` · `docs/guides/SYSTEM_DOCUMENTATION.md:114` · `docs/guides/LONG_TASK_PROMPTS.md:5` · `CLAUDE.md:48-51` · D8 워커 실행 출력 `git log --since=2026-04-13 --diff-filter=A -- 'apps/*' | wc -l` → 0]
- **운영 런타임과 문서 디렉토리 결합이 배포 실패 1회, 배포 점검 매니페스트가 없는 파일 참조.** [확인됨: 커밋 a90a38faf · `docs/harness/foms_deploy_checks.json:6` → `foms_feature_mode_matrix.json` 부재 · `Dockerfile:34-40`]
- **사고·결정이 색인 밖.** 08-14 는 복구 가이드 머리말이 원장, 8~9월 plans 94건(ledger 55) 색인 0, DECISIONS 8월 이후 5건/커밋 1,482. [확인됨: `docs/guides/DATA_INCIDENT_RECOVERY.md:3` · `docs/ARCHIVE_INDEX.md:3` · `git log -1 -- docs/ARCHIVE_INDEX.md` → 2026-06-17 · D8 워커 파일명 대조 출력 `plans since_2026-07 134 in_ARCHIVE_INDEX 0`]
- **훅 로그가 신호를 묻는다.** 300행 중 271행이 루트 밖 편집 스킵, fail-open 태그 0 — 없어서 0 인지 묻혀서 0 인지 구분 불가. [확인됨: D8 워커 집계 `271 [track_edits]` · `CLAUDE.md:90`(워크트리 격리 권장)]

## ④ 더 필요한 것(로드맵)

세 구간(지금 / 이번 분기 / 12~24개월). 항목마다 무엇을 · 왜(시스템 수준) · 첫 걸음(작게) · 검증. 워커 `needed` 와 §5 초안에서 출발했다. **이 검토는 아무것도 실행하지 않았다** — 설치·git 변경·코드 수정은 사용자 승인 뒤 별도 작업이다. 모든 권고는 근본 원인 수정 정책(증상 덮기·우회·에러 숨기기 금지)·인라인 스타일 금지·`static/css/foundation/erp-pro.css` SSOT·production push 금지·훅 fail-open 로그 의무를 전제한다.

### 지금(첫 2~4주 — 악화를 멈추는 래칫과 원장)
1. **의존 방향 래칫 계약 테스트** [D2]
   - 무엇: `tests/contracts/runtime/` 에 표준 라이브러리(ast)만 쓰는 테스트 1개, 현재 위반(services→web 8·api→web 53·services→api 15·persistence→services 1·지연 import 473)을 기준선 JSON 으로 동결해 순증만 red.
   - 왜: 경계가 디렉토리 이름일 뿐이라 에이전트 속도로 역방향이 계속 는다 — 기준선 래칫은 코드를 고치지 않고 오늘부터 악화를 막고 줄어드는 숫자가 분해 진척의 척도가 된다.
   - 첫 걸음: 기준선 JSON 생성 + 테스트 1파일 + ci.yml 계약 레인 등재.
   - 검증: `foms/services` 아무 파일에 `from foms.web import auth` 한 줄을 넣으면 그 테스트만 red, 되돌리면 green.
2. **파일 크기 래칫 + 정본 경로 정정** [D2·D8]
   - 무엇: 500줄+ 파이썬·300줄+ JS 목록을 기준선으로 동결, `CLAUDE.md:48-51`·`.cursor/rules/00-project-context.mdc:31`·`foms/README.md` 의 apps/·services/·constants.py 를 실경로로 고치고 정본·안내서의 백틱 경로 실존 테스트를 tests/harness 에 둔다(문서 읽는 테스트 → ci.yml 서브셋 등재).
   - 왜: 판단 규칙(문서)이 죽고 동결 계약(테스트)만 살아남은 상태 — 규칙을 테스트로 옮겨야 다음 6k 파일이 안 생기고 새 세션이 테스트 실패로 배우지 않는다.
   - 첫 걸음: 기준선 JSON + CLAUDE.md 한 줄 정정 + 경로 실존 스크립트(현재 MISSING 20)를 테스트로.
   - 검증: `grep -c 'apps/' CLAUDE.md .cursor/rules/00-project-context.mdc foms/README.md` 전부 0, 없는 경로를 한 줄 넣으면 red.
3. **드리프트 감사 배선 + 09-01 원인 줄 제거** [D3]
   - 무엇: `tools/ops/audit_erp_flat_columns.py`·`tools/ops/audit_as_axis_drift.py` 를 rum-daily 패턴 워크플로로 매일 실행, `foms/services/integrations/naver_commerce/order_candidates.py:822-823` 의 `Order.phone == digits` 갈래 제거(읽기 14곳을 `erp_phone_digits` 로 옮기는 첫 건).
   - 왜: 사본 구조를 바꾸기 전에도 어긋남을 사람이 아니라 기계가 세야 한다.
   - 첫 걸음: 워크플로 1개 + 갈래 1줄.
   - 검증: 두 감사가 2주 연속 0건(워크플로 아티팩트), 스테이징에서 전화 변경 1회 뒤 트리아지 자동 매칭이 같은 고객을 찾음(09-01 재현 시나리오).
4. **루프 하트비트 1줄 + 워커·SIDEFX Sentry 배선** [D7]
   - 무엇: `scripts/maintenance/run_naver_auto_dispatch.py` tick 끝에 `upsert_heartbeat(engine, 'NAVER_AUTO_DISPATCH', ...)`(전례 `foms/services/sidefx_worker.py:495-520`), `foms/services/jobs/tasks.py` 상단과 루프 진입점에서 `init_sentry()`(DSN 없으면 no-op).
   - 왜: 지금은 사용자 화면이 모니터링 장치다.
   - 첫 걸음: 하트비트 1줄 + 계약 테스트 1개(루프 1회 뒤 heartbeat 행 존재).
   - 검증: 스테이징에서 루프가 도는 동안 하트비트 표 `side_effect_worker_heartbeats`(`models.py:2677`)의 `NAVER_AUTO_DISPATCH` 행 `last_heartbeat_at` 이 tick 마다 갱신되고, 루프 프로세스를 kill 하면 60초 넘게 갱신이 멈춘다(도구 무관 직접 질의 — 기존 CLI `tools/ops/check_sidefx_readiness.py` 에는 kinds 인자가 없고 판정 대상이 `foms/services/sidefx_worker.py:45` 의 3종 고정·`foms/services/sidefx_worker.py:615` 순회라 그대로는 못 쓴다; 준비 판정 일반화는 ④ 12~24개월 23번); 워커 실패잡 1건이 Sentry 에 environment=staging 이벤트로 잡힘.
5. **사고 원장·결정 기록 선등재** [D8·D3·D7]
   - 무엇: 08-14·08-24·09-03(데이터)·08-07 13시간 정지·08-31 852초·DEAD 1,188·실패잡 2,544(운영)를 docs/incidents 에 같은 양식(유형·원인 축·복구·구조 변경 여부·재발 여부)으로, DECISIONS 에 AS-AXIS-01 결정과 ept_b8 복귀 정정 각 1줄.
   - 왜: 같은 유형이 넷인데 등재는 하나라 '반복' 이 시스템에 보이지 않고, 다음 ablation(2027-02)이 오염된 기록으로 판정한다.
   - 첫 걸음: 08-14 문서 1건(`docs/guides/DATA_INCIDENT_RECOVERY.md:3-4` 와 `docs/AI_CHANGELOG.md:50` 을 근거로).
   - 검증: `ls docs/incidents | grep -c 2026-0[89]` ≥ 4, `grep -c 'AS-AXIS' docs/harness/policy/DECISIONS.md` ≥ 1.
6. **로그인 전용 한도 + 실패 잠금 + 레이트리미터 폴백 로그** [D6]
   - 무엇: `foms/web/auth/routes.py:293` 의 login 에 `limiter.limit`(username+IP 키)과 실패 카운터·LOGIN_LOCKED 감사, `foms/services/rate_limit.py:58-70` 뒤 폴백 진입 시 logging.warning + Sentry 이벤트 1건.
   - 왜: 고급 통제는 있는데 가장 흔한 공격면을 막는 층이 0 이고, 열림이 관측되지 않으면 사업 판단 원장이 만들어질 수 없다(훅 fail-open 로그 의무와 같은 원칙).
   - 첫 걸음: 데코레이터 1개 + 계약 테스트 1파일(설치 없이 가능).
   - 검증: 스테이징 잘못된 비밀번호 11회 → 429 + security_logs 에 LOGIN_FAIL 10·LOGIN_LOCKED 1; REDIS_URL 을 도달 불가 주소로 둔 테스트에서 warning 레코드 1건이 caplog 에 잡힘.
7. **두 번째 개발자 부팅 경로** [D8]
   - 무엇: README 를 실제 절차(DATABASE_URL·alembic upgrade·`import app` APP_OK)로 재작성, 루트 `.env.example`(키 이름만) 추적, `.claude/skills` 4종 git add(사용자 승인 뒤).
   - 왜: 규칙이 가리키는 도구가 클론에 없으면 규칙이 거짓이 된다.
   - 첫 걸음: `README.md:37-46` 절 교체.
   - 검증: 임시 디렉토리 clone 뒤 README 만 따라 `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"` 와 `timeout 300 python -m pytest tests/harness -q` 통과, `git ls-files .claude/skills | wc -l` → 5.

### 이번 분기(3개월 — 사본 규약을 기계로 바꾸는 구조 작업)
8. **의존성 거버넌스 층 + 메이저 상향 패킷** [D1·D6]
   - 무엇: `requirements.in`(직접 의존 40개 안팎, 항목마다 사유) → pip-tools 또는 uv 해시 잠금 → `requirements-dev.txt` 분리(pytest·xdist·playwright·gevent·psycogreen) → Dockerfile `--require-hashes` + `.dockerignore` 에 tests/ 실제 제외 → CI 취약점 조회 잡(pip-audit 또는 OSV querybatch, 처음엔 report-only) → dependabot 주 1회. 같은 분기에 한 브랜치로 Werkzeug 상한 제거·`app.py:22-36` 몽키패치 삭제(무동작 확인됨)·`tests/conftest.py:26-28` KDF 재계약·`foms/platform/request_limits.py:225` LimitedStream 재확인·Flask 3.1/Werkzeug 3.1/Jinja2 3.1.6/Pillow 11.
   - 왜: 세 환경이 같은 버전 집합을 돌게 하는 유일한 구조적 수단이고, 지금 핀은 알려진 수정이 전부 3.x 에만 있다 — 차단 요소 4곳뿐이라 지금이 가장 싸다.
   - 첫 걸음: import 0 이 확인된 잔재(fastapi·starlette·uvicorn·bottle·python-jose·passlib·pefile·pythonnet·keyring·dulwich + Flask 확장 7종 + waitress)를 뺀 `requirements.in` 과 잠금 1회 → 스테이징 빌드 1회; 상향은 `tests/domains/test_password_kdf_contract.py` 단일 파일을 먼저 빨강으로 만든다.
   - 검증: 같은 커밋 두 번 빌드 `pip freeze` diff 0 · 컨테이너 `pip check` 0 · 워크플로 7개 green · 스테이징 pbkdf2 계정 로그인 + 도면·사진 업로드 + Socket.IO 핸드셰이크 · OSV 재조회 Flask/Werkzeug/Jinja2 권고 0 · `grep -n "_hash_internal" app.py` 0. 잠금 도구·파이썬 목표(3.12 유지 vs 3.13)는 ⑥ 사용자 결정.
9. **파이썬 런타임 정본 단일화** [D1]
   - 무엇: `.python-version` 을 3.12.x(패치 포함)로, Dockerfile `FROM python:3.12.<patch>-slim` 고정, 워크플로 7개 `python-version-file`, 워커·크론·sidefx 도 같은 Dockerfile, `/healthz` 또는 부팅 로그에 `sys.version`.
   - 왜: 패치 차이만으로 데이터가 유실됐고 워커가 3.11 인지 3.12 인지 코드로 알 수 없다.
   - 첫 걸음: `.python-version` 정정 + `ci.yml` 만 `python-version-file` 로 전환해 CI 1회.
   - 검증: `grep -rn "python-version:" .github/workflows` 리터럴 0, 스테이징 web·worker·sidefx 부팅 로그 `sys.version` 세 값 동일.
10. **조회·권한·매칭 축 승격 + 사본 동기의 DB 강제** [D3]
   - 무엇: `erp_phone_digits`·`as_axis_status`·`erp_stage_code` 를 PostgreSQL 생성 컬럼(GENERATED ALWAYS AS … STORED) 또는 트리거로 파생시켜 호출 규약을 제거, 레거시 `orders.phone` 은 읽기 14곳 이관 뒤 쓰기 전용 격하, 문자열 캐스팅 ILIKE 89곳은 축별 컬럼/tsvector 로 단계적 이관.
   - 왜: 네 사고가 전부 '규약을 안 부른 쓰기 경로' 에서 났다 — DB 가 맞추면 새 쓰기 경로가 늘어도 어긋날 수 없고 권한 필터가 trigram 인덱스 하나에 매달리는 단일 장애점도 사라진다.
   - 첫 걸음: `erp_phone_digits` 생성 컬럼 확장 전용 마이그레이션 1건(새 컬럼 → 백필 검증 → 스왑).
   - 검증: 드리프트 감사 2주 연속 0, `EXPLAIN` 에서 권한 필터가 btree/tsvector 를 타고 Seq Scan 0.
11. **주문 문서 스키마 정본(키 레지스트리 + 버전 승격)** [D3·D2]
   - 무엇: structured_data 최상위 키 전부를 레지스트리 1벌(소유자·읽는 화면·플랫 사본 여부·도입 리비전)로, `_OPERATIONAL_TOP_LEVEL_KEYS` 를 거기서 생성, `structured_schema_version` 1→2 승격 함수 + 저장 시 미등록 키 검증기, lazy 마이그레이션 114곳을 승격 함수로 흡수.
   - 왜: 08-24 유형은 '키를 아는 사람' 이 튜플을 갱신해야만 막힌다.
   - 첫 걸음: `foms/api/erp_orders_structured.py:231` 보존 튜플의 키와 lazy 마이그레이션 키를 표 1장으로 뽑아 레지스트리 모듈 1개로(동작 변화 0).
   - 검증: 미등록 키 저장 요청이 계약 테스트 red, 등록 키(alimtalk·naver_linked·channeltalk)는 폼 PUT 1회 뒤에도 잔존 green.
12. **횡단 관심사(인증·역할·팀·권한) services 이동 + 읽기 권한 SSOT** [D2·D6]
   - 무엇: ROLES·TEAMS·login_required·role_required·get_user_by_id 를 `foms/services/auth`(또는 platform)로 옮기고 web.auth 는 재수출 + 라우트만; AUTH-01 과 같은 모양의 READ 매니페스트(endpoint→read_policy_id)를 GET·프래그먼트·내보내기·presign 에 적용, `user_can_read_order(user, order)` 의 미사용 `order` 인자를 실제로 쓰며, API 302 를 401/403 JSON 으로 통일.
   - 왜: api→web 53 의 대부분이 이 한 패키지를 향하고 읽기 판정이 세 갈래라 역할 추가마다 248개 데코레이터를 훑어야 한다.
   - 첫 걸음: 상수 2개 + get_user_by_id 이동 + 재수출 파리티 테스트(동작 변화 0); 전화·주소를 응답하는 GET 목록화(`grep -rlE "customer_phone" foms/api` 부터) + 읽기 정책 3종 초안.
   - 검증: foms.web.auth 팬인 82 → api·services 에서 0; 테스트 클라이언트 VIEWER 로 주문 구조 GET → 403 JSON, STAFF 본인 배정 건 → 200; 미등재 GET 을 정적 게이트가 red.
13. **콘텐츠 해시 자산 매니페스트(파이썬 빌드) + 계약 다이어트** [D5·D4]
   - 무엇: `tools/assets/build_manifest.py` 가 static/css·js 의 sha256 앞 10자리를 `static/asset-manifest.json` 으로 쓰고 Jinja 헬퍼 `asset_url()` 가 `?v=<hash>` 를 붙인다(erp-pro @import 자식 재작성 포함, `static/css/foundation/erp-pro.css` SSOT 는 그대로), predeploy.sh 에 빌드 1회, pre_push_smoke 에 매니페스트 일치 검사. 핀 리터럴 테스트 90곳과 CACHE_VERSION 리터럴 3파일은 헬퍼 호출 계약으로 대체, ci.yml 문서 서브셋 등재는 스캐너가 생성.
   - 왜: 핀 충돌은 사람 규약 문제가 아니라 '내용→URL' 매핑이 사람 손에 있는 구조 문제다 — 해시로 바꾸면 SW staticCacheFirst 는 그대로 둔 채 phantom 유형이 원천 소멸하고 커밋 23% 세금과 테스트 52파일 동반 수정이 함께 사라진다.
   - 첫 걸음: `templates/orders/partials/erp_order_js.html`(자산 36개) 한 파일만 `asset_url` 로 전환.
   - 검증: 자산 한 바이트 변경 → 매니페스트 해시 변경 → 렌더 URL 변경 단위 테스트; 전환 후 4주간 '같은 핀' 유형 커밋 0; `grep -rn '?v=2026' tests --include=test_*.py | wc -l` 90 → 0.
14. **셸 공용 계층(파이썬 SSOT)** [D5]
   - 무엇: `foms/services/shell_assets.py` 가 (shell_variant, endpoint, team) → css/js 목록·활성 탭·하단 내비를 반환하고 layout_head/layout_scripts 는 루프로만 렌더, v2·v3 활성 탭 elif 사슬은 매크로 1개, 동등성 계약 테스트(ERP 9경로 × 3변형).
   - 왜: 봉합 12건이 전부 '게이트 하나 더' 였다.
   - 첫 걸음: v2(`templates/partials/shared/erp_mobile_shell.html:1-6`)·v3(`templates/partials/v3/foms_app_shell_v3.html:5-10`) 활성 탭 사슬을 매크로 1개로 + 계약 테스트 1개.
   - 검증: 의도적 누락 커밋에서 red 1회 확인, 이후 분기 '셸 누락·누출 봉합' 커밋 0. legacy 셸 폐기는 ⑥ 사용자 결정.
15. **단일 '초록' 정의 + 로컬=CI 동형 게이트** [D4]
   - 무엇: 'push 완료 = 로컬 전체 스위트(-n auto --dist loadfile) + 로컬 PG 있으면 tests/postgres + 등재 계약' 한 문장, pre_push_smoke 기본을 전체 스위트로 바꾸고 성공 시 SHA 스탬프, guard_policy 가 push 앞에 스탬프==HEAD 를 요구해 실패·부재 시 deny(사유는 훅 로그에 기록), ci_watch 는 '런 없음' 을 exit 4(미확정)로, perf-gate advisory 결과는 승격 도구가 읽어 승격 전 노출.
   - 왜: 로컬 43~46초 전체 스위트가 이미 가능한데 게이트는 21타깃이고 push 를 막지 않는다.
   - 첫 걸음: smoke `-Full` 기본화 + 스탬프 파일 + guard_policy 판정 1개.
   - 검증: 스탬프 없이 `git push origin deploy` 시도 시 훅 deny + 로그 1행; 4주간 등재·핀·PG 전용 CI 빨강 0.
16. **배포 정본을 저장소로 + 롤백 런북** [D7]
   - 무엇: 서비스 6개의 시작 명령·헬스체크·cron·복제 수·필수 env 키 이름(값 제외)을 `docs/harness/foms_deploy_topology.json`(또는 Railway IaC `.railway/railway.ts`) 한 파일로, `RAILWAY_ENV_VARS.md` 를 그 파일에서 생성, 사문 toml 5벌 제거 또는 '사문' 헤더, `check_deploy_secrets.py` predeploy 배선, `start.sh` FOMS_ 집합 ⊆ 정본 집합 계약 테스트; `docs/runbooks/rollback.md`(DB 먼저→코드 나중·확장 전용 규칙·재배포 전 안전 판정·PITR fork·cherry-pick 기준 SHA·RTO 목표) + CI-DOCSCOPE 등재.
   - 왜: 저장소를 고쳐도 운영에 반영되지 않는 상태가 '확인 필요' 로 남았고 env 키 누락이 이미 DEAD 1,188 사고를 냈으며 롤백 규칙이 AI_STATUS 한 줄에만 있다.
   - 첫 걸음: `docs/AI_STATUS.md:68` 미해소를 Railway API 읽기 조회로 닫고 DECISIONS 1항목; rollback.md 는 `docs/AI_STATUS.md:97` 한 줄과 `predeploy.sh:15-19` 비대칭을 옮겨 적는 것부터.
   - 검증: 계약 테스트 2개 green, predeploy 에서 필수 키 하나를 빼면 스테이징 배포가 predeploy 단계에서 실패, 분기 1회 스테이징 리허설(downgrade → 이전 커밋 → upgrade) 기록.
17. **런타임 매니페스트 4종을 코드 패키지로 + 3자 일치 테스트** [D8·D7]
   - 무엇: foms/services 가 읽는 JSON 4종을 `foms/policy/` 패키지 데이터로 이동(전례 `Dockerfile:32` foms/build_compatibility.json), 이동 전에는 로더 경로 집합 == Dockerfile COPY 집합 == .dockerignore negation 집합 계약 테스트 + `foms_deploy_checks.json` 참조 실존 검사.
   - 왜: 하네스 변경이 운영 부팅 실패로 번지는 경로(a90a38faf)가 열려 있고 5번째 매니페스트에서 재현된다.
   - 첫 걸음: `tests/contracts/runtime/test_runtime_manifest_triad.py` 1개(현재 4=4=4 green, deploy_checks 참조 red 1건 → 수정).
   - 검증: 로더에 5번째 docs/harness 경로를 추가하면 Dockerfile 미수정 상태에서 red; 이동 완료 후 `grep -c 'docs/harness' Dockerfile .dockerignore` 전부 0 이고 APP_OK.
18. **개인정보 수명주기 정책 1장 + 마스킹 헬퍼 + 계약 테스트** [D6]
   - 무엇: docs/guides 에 주문 PII·현장 사진(R2)·감사 로그·발송 로그·공유 링크·백업 각각의 보존기간·근거·삭제 경로 표 6행, `foms/services/security/pii_mask.py` 공용 헬퍼를 audit_writer·channel_delivery·Sentry scrub·로그 redaction 이 공유, purge 기본값을 정책 값과 일치.
   - 왜: 전화·주소가 5곳에 복제되는데 결정 지점이 없어 감사 원장 30.6% 전화 잔존이 실측됐다.
   - 첫 걸음: `foms/services/kakao_alimtalk.py:353` `_mask_phone` 공용화 + audit_writer detail 작성 지점 1곳 적용 + 'security_logs detail 에 전화 패턴 0' 계약 테스트.
   - 검증: 전화 패턴을 넣으면 red, 마스킹 후 green; purge 기본값 == 정책 표 docs-facing 테스트가 ci.yml 서브셋에 등재. 보존기간 값은 ⑥ 사용자·법무 결정.
19. **지식 색인 자동 생성 + tests/README 현행화** [D8·D4]
   - 무엇: `tools/harness/build_archive_index.py` 가 plans·specs·incidents 머리를 표로 뽑아 ARCHIVE_INDEX 생성, '생성 결과 == 커밋된 색인' docs 서브셋 테스트, 원장 완료 시 DECISIONS 1줄 등재 의무; tests/README 를 레인 7종 대응표(트리거·DB·env·제외·사각)·'핀 바꾸면 어떤 테스트'·'PG 레인 켜는 법(FOMS_TEST_DATABASE_URL)' 으로 다시 쓰고 TEST_GUIDE 는 '화면 QA 절차서' 로 개명, ci.yml 낡은 주석(14.1분·5,329개) 정정.
   - 왜: 색인이 06-17 에 멈춰 3개월치 지식이 저장소 밖에 있고 테스트 체계 지식이 ps1·yml 주석에만 있어 등재 누락 빨강 8건이 났다.
   - 첫 걸음: 생성 스크립트로 현재 손 색인과 diff(134+61 건 추가 예상) + tests/README 상단 레인 대응표 1개.
   - 검증: `build_archive_index.py --check` 미색인 0; 새 세션이 README 만 읽고 '핀 바꾸면 어떤 테스트'·'PG 레인 skip 조건'·'import 1줄이 왜 빨강' 에 경로:행으로 정답.

### 12~24개월(구조 전환 — 앞 항목의 기준선이 있어야 시작 가능)
20. **퍼시스턴스 정렬 — models.py 도메인 분할 + 스키마 경로 단일화** [D2·D3]
   - 무엇: 77 클래스를 `foms/persistence/main/{orders,as,naver,settlement,security,users}.py` 로 옮기고 루트 models.py 를 재수출 껍데기로 뒤집는다(지금과 반대 방향), `models.py:18-19` 의 foms.services import 는 datetime 헬퍼를 persistence 로 내려 제거; `tools/ops/ensure_schema.py:46` raw ALTER·alembic_version UPDATE 를 정식 리비전으로 흡수해 predeploy 에서 제거, base 리비전 스쿼시로 빈 DB 전체 재생을 CI 가 실행, wdcalculator 4테이블 alembic 편입, 워커 기동 시 `alembic current == head` 읽기 확인(닫힘 기본·로그 필수).
   - 왜: 225파일 팬인으로 '전부 아니면 무' 가 된 분해를 재수출 뒤집기로 점진화하고, alembic 이 스키마 정본이 아닌 상태를 끝낸다.
   - 첫 걸음: 보안 로그·사용자 클래스군을 persistence/main/security.py 로 이동 + 재수출(import 무변경) + `tests/postgres/test_migration_chain.py` 에 '빈 DB upgrade head' xfail.
   - 검증: APP_OK · `tests/domains/test_foms_namespace_imports.py` green · alembic autogenerate 빈 diff · predeploy.sh 에 alembic 외 DDL 0 · xfail 이 스쿼시 뒤 xpass. wdcalculator 토폴로지는 ⑥ 사용자 결정.
21. **네이버 web 모듈 3분할 + 통합 어댑터 수렴** [D2]
   - 무엇: `naver_ingest.py` 를 페이지(7 라우트)/JSON API(29 라우트)/읽기 모델로 나누고 정책 상수는 services/orders 로; solapi·pywebpush·카카오 지도·채널톡 HTTP 를 `foms/services/integrations/<이름>/client.py` 뒤로.
   - 왜: 규격 변경마다 3벌이 같이 움직이는 증폭원이자 fix 46 의 반복 지점.
   - 첫 걸음: `foms/services/integrations/naver_commerce/triage_count.py:118` 이 지연 import 하는 두 함수를 services 읽기 모델로 옮겨 방향만 뒤집기(동작 변화 0).
   - 검증: services→web 8 → 7, 네이버 테스트 109파일 green, 이후 3개월 naver 커밋의 JS/템플릿 동시 변경 비율 64% 아래.
22. **주문 폼 코어 추출 + node 실행 계약 + 프론트 래칫** [D5]
   - 무엇: 금액 합계·자유입력 파싱·규격 변환을 셸 무관 `static/js/orders/erp-order-core.js`(전역 1개·DOM 무접촉)로, PC·모바일·태블릿 3벌이 호출, wdcalculator `_node_runner.py` 패턴을 orders 에 복제; `tools/design/frontend_ratchet.py` 로 `style="` 687·인라인 script 태그 64(템플릿 46 — 래칫 기준선은 태그 수)·300줄 초과 12·핀 없는 자산 23 baseline 증가 시 exit 1 + 전 JS `node --check`.
   - 왜: 현장과 사무실 금액 로직이 3벌이면 불일치 씨앗이 구조에 있고, 인라인 규칙은 화면별 assert 22파일로만 존재한다(erp-pro.css SSOT 는 그대로, 인라인으로 고치라는 권고가 아니다).
   - 첫 걸음: `static/js/foms/tablet-measure-form.js:215` 미러 블록 하나를 코어로 + node 계약 1개; `style="` 래칫 하나를 pre_push_smoke Design SSOT lint 옆에.
   - 검증: 미러 주석 28 감소, `tests/contracts/orders/` node 계약 ≥1, 인라인 style 1줄 추가 시 smoke exit 1.
23. **운영 토폴로지 재현 레인 + 루프 5개 감독 통일 + 회수 규약** [D1·D7]
   - 무엇: CI 잡 1개가 `SERVER_SOFTWARE=gunicorn REDIS_URL=… gunicorn -k gevent -w 2 app:app` 을 띄워 `/healthz`·Socket.IO 핸드셰이크·enqueue 1건 스모크; 루프 5개를 SIDEFX 세대(하트비트·닫힘 기본 준비 판정)로 통일하고 시각 창 루프의 cron 이관은 IP 한도 3 제약 확인 뒤; 실행 이력 표에 임대 만료 시각 + 기동 시 `ABORTED_RESTART` 스윕 + RQ `Retry(max=3)`; 시간당 워크플로가 `/healthz`·준비 판정·실패잡·백업 심박을 폴링해 임계 초과 시 job fail(사람에게 닿는 경보 1개).
   - 왜: 운영이 첫 실행 환경이고(2026-02-20·07-21 유형), 재배포마다 RUNNING·실패잡 흔적이 남는다.
   - 첫 걸음: 로컬 `SERVER_SOFTWARE=gunicorn` 으로 `import app` 만 해 몽키패치 경로 출력 확인 스모크 1개; `settle_sync._open_run` 에 `lease_expires_at`(확장 전용 마이그레이션).
   - 검증: 의도적 `SOCKETIO_ASYNC_MODE=threading` 에서 그 레인만 red; 정산 동기화 중 워커 재배포 뒤 RUNNING 이 60초 안에 ABORTED_RESTART, `naver_settle_sync_runs` RUNNING 0행; 스테이징 실패잡 1건 → 1시간 안 GitHub 알림.
24. **복구 훈련 운영화 + 하네스 다이어트 + 스택 ADR** [D3·D8·D1]
   - 무엇: DR 가이드에 RPO/RTO 표(목표=사용자 결정, 실제=6일/24h/오프사이트 주기, wdcalculator 포함 여부), 분기 1회 스테이징 PITR fork 리허설 기록을 docs/runbooks 에; data_doctor 를 `order_field_changes` 원장 기반 본문 복구로 확장하고 writer 를 약 40파일로; Cursor 러너 결정 뒤 훅 1벌 + 공통 정책 모듈, Stop 훅 인벤토리 재생성을 'CI 가 스캐너 돌려 diff 0' 으로, DECISIONS 에 부품별 '막은 사고' 대조표(2027-02 ablation 판정 근거); DECISIONS 에 스택 ADR 1건(유지 판정·교체 비용·gevent/Socket.IO 층·psycogreen 대체 시점·Werkzeug<3 폐기 기록).
   - 왜: 복구는 처음 해보는 날이 사고 날이면 RTO 는 문서와 무관하고, 이중 러너는 가드 변경마다 두 배 봉합이며, 지식 집중을 문서로 푸는 최소 단위가 ADR 이다.
   - 첫 걸음: DR 문서 RPO/RTO 절 1개 + 첫 리허설 1회 소요 시간 기록; DECISIONS 에 ept_b8 정정 1줄 + 스택 ADR 초안.
   - 검증: 리허설 기록 파일 CI-DOCSCOPE 등재, 두 번째 기록에서 RTO 실측이 목표 이내; `grep -nE "Flask|gevent|Werkzeug" docs/harness/policy/DECISIONS.md` ≥ 1; 인벤토리 커밋 비율 13% 에서 감소.

## ⑤ 스택 판정

**판정: 조건부 유지.** Flask 모놀리스 + Jinja + Vanilla JS + PostgreSQL(JSONB) + Railway 조합을 유지하되, ④ 의 '지금'·'이번 분기' 항목(잠금·상향 패킷·방향 래칫·해시 매니페스트·감독·읽기 SSOT·정본 1벌)을 조건으로 건다. 조건이 이번 분기 안에 채워지지 않으면 D1(핀 패치 창 밖)·D3(사본 사고 반복)·D7(사용자 발견형 실패)이 부적합으로 넘어가며, 그때도 답은 교체가 아니라 '조건 이행' 이다.

### 근거
- **프레임워크 계열은 살아 있고 상향 차단 요소가 작다.** 상한 핀 1줄·몽키패치 13줄(무동작)·테스트 상수 1곳·LimitedStream 1곳뿐이고 foms 의 werkzeug import 10건은 전부 공개 API. [확인됨: `requirements.txt:106` · `app.py:22-36` · `tests/conftest.py:26-28` · `foms/platform/request_limits.py:225` · D1 워커 `inspect.getsource(werkzeug.security._hash_internal)` 출력]
- **사고의 원인은 스택이 아니라 거버넌스 공백이다.** 데이터 사고 4건은 JSONB 자체가 아니라 사본 동기 규약(R1), 핀 사고 6건은 Vanilla JS 자체가 아니라 해시 매니페스트 부재(R4), 운영 사고는 Railway 자체가 아니라 감독·경보 부재(R3). docs/incidents 5건 중 의존성 드리프트가 원인인 사고는 0. [확인됨: `ls docs/incidents` · `models.py:89-112` · `static/sw.js:82-93` · `start.sh:23-26`]
- **JSONB 는 조건부로 맞다.** 진짜 가변 부분(주문 구조·마법사 상태)에는 맞지만 조회·권한·매칭 축은 컬럼으로 승격돼야 한다 — 이미 플랫 사본 9종이 그 방향을 가리키고 있고, 부족한 것은 DB 강제(생성 컬럼·트리거)다. [확인됨: `models.py:89-112` · `foms/services/erp_permissions.py:64`(문자열 캐스팅 ILIKE) · `migrations/versions/phase_d_trgm_indexes.py:47-54`]
- **Vanilla JS + Jinja 는 조건부로 맞다.** 번들 없이도 파이썬 빌드 해시 매니페스트·node 계약(`tests/contracts/wdcalculator/_node_runner.py:1` 전례)·래칫으로 버틸 수 있고, 현장 태블릿·iOS 웹뷰가 주 사용면이라 SPA 전환 이득은 확인 필요(⑥). [확인됨: `static/sw.js:82-93` · `tests/performance/test_perf_regression_guard.py:3-5`]
- **Railway + gevent + RQ 는 조건부로 맞다.** 실시간 소비자는 emit 7건뿐이라 gevent 층 유지 이유가 약하고(사용자 결정 ⑥-(b)), RQ 단일 큐 + 워커 1 은 네이버 IP 한도 3 이 강제하는 제약이지 선택이 아니다. [확인됨: `start.sh:32-33` · `foms/services/jobs/queue.py:54` · `foms/platform/realtime.py:204-207` · D1 워커 `grep -rnE "\.emit\(" foms | wc -l` → 7]
- **requirements 의 fastapi·starlette·uvicorn 은 '이행 중' 이 아니라 2026-01-16 pip freeze 덤프 잔재다.** foms·app.py·models.py·db.py import 0. [확인됨: D1 워커 실행 출력 `fastapi: 0 starlette: 0 uvicorn: 0` · `git blame -L 1,2 requirements.txt` → 984169b2c 2026-01-16]

### 교체 시 비용(통합자 재측정, HEAD 062723348)
- 명령(bash 한 줄, 아래는 `; ` 로 이어진 조각을 줄바꿈으로 펼친 것):
```bash
cd C:/DEV/FOMS && echo "route: $(grep -rnE '@[a-z_]+\.(route|get|post|put|delete|patch)\(' foms --include=*.py | wc -l)"; \
echo "render_template: $(grep -rn 'render_template(' foms --include=*.py | wc -l)"; \
echo "url_for: $(grep -rn 'url_for(' foms templates --include=*.py --include=*.html | wc -l)"; \
echo "템플릿: $(git ls-files templates | grep -c '\.html$')"; \
echo "Column(: $(grep -c 'Column(' models.py wdcalculator_models.py | awk -F: '{s+=$2} END{print s}')"; \
echo "test_client 파일: $(grep -rlE 'test_client\(|\bclient\.(get|post|put|delete)\(' tests --include=test_*.py | wc -l) / $(git ls-files tests | grep -c 'test_.*\.py$')"; \
echo ".query( $(grep -rn '\.query(' foms models.py --include=*.py | wc -l) / select( $(grep -rnE '\bselect\(' foms --include=*.py | wc -l)"
```
- 출력: `route: 371 · render_template: 106 · url_for: 863 · 템플릿: 278 · Column(: 945 · test_client 파일: 256 / 672 · .query( 710 / select( 5` (프롬프트 §6 인용값 route 367·Column 925·test_client 265 는 HEAD 이동과 정규식 차이 — D1 워커 재측정 371·945·256 과 일치)
- 뜻: 웹 프레임워크 교체는 라우트 371·템플릿 278·url_for 863·Flask 테스트 클라이언트 파일 256(전체 672 의 38%) 을 다시 쓰는 일이고, ORM 계열 교체는 Column 945·`.query(` 710 을 건드린다. 프론트 SPA 전환은 130k 줄 JS + 셸 3벌 + 계약 테스트 136파일을 다시 짓는 일이다. 사람 1명 + 에이전트 팀에서 이 비용은 12~24개월 전체를 소진하며, 그동안 R1~R8 은 그대로 남는다. 반면 조건 이행 비용은 ④ 항목 1~19 로 이번 분기 안에 끝난다. SQLAlchemy 2.0 → 2.1/3.0 은 `.query(` 710 vs `select(` 5 라 별도 재평가 항목(⑦).

## ⑥ 열린 질문

§6 초안 (a)~(h)/(a)~(l) 에 워커 `stack_questions` 를 병합했다. 답이 나온 것: §5 D8 '13시간 정지·852초 원장 위치' → `tools/ops/wait_for_redis.py:1-12`·`tools/ops/check_worker_redeploy_safe.py:1-12` 에서 확인돼 삭제. 아래는 전부 이 검토가 답하지 못한 것이며 운영 수치는 하나도 추정하지 않았다.

### 운영 데이터 필요(확인 필요)
- (a) Railway 서비스 6개(web·worker·cron 2·SIDEFX·Redis/PG)의 실제 빌더·파이썬 버전(패치까지)·startCommand(워커가 `sh start.sh` 인가 `rq worker` 인가)·healthcheckPath·복제 수·재시작 정책·cron 표현식 — `docs/AI_STATUS.md:68` 미해소, nixpacks 라면 `.python-version` 3.11.9 를 읽고 있는가 [D1·D7]
- (b) 운영 env 실제 값: SOCKETIO_ASYNC_MODE·SOCKETIO_CLIENT_ENABLED·CORS_ALLOWED_ORIGINS·REDIS_URL·FOMS_* 루프 플래그 5종·SENTRY_DSN(worker/SIDEFX 포함 여부)·FOMS_SIGNING_KEY_CURRENT engaged 여부·auth-rate 키·WD_CALCULATOR_DATABASE_URL(SAME/SEPARATE)·셸 코호트 4종·FOMS_TRUSTED_PROXY_HOPS·NAVER_COMMERCE_APP_EXPIRES_ON·FOMS_BACKUP_HEARTBEAT_SECRET [D1·D2·D5·D6·D7]
- (c) 트래픽·부하: 동시 사용자·태블릿/iOS 폴링 주기·gunicorn 2×복제 2 포화·DB 풀(5+5) 대기·RQ 큐 대기 p95(백필 중)·하트비트 재검증(시간당 약 260회/클라이언트)의 web CPU 비중·RUM 셸/기기별 p95(현재 집계는 메트릭×일자뿐 — `foms/services/rum_aggregate.py:358`)·현장 기기 대수·OS·iOS 웹뷰 버전·통신 두절 빈도·Socket.IO 동시 연결·채팅 실사용 [D1·D5]
- (d) 운영 DB: `users.password` 접두어 분포(Werkzeug 3 전 필수)·orders 행수·structured_data 크기·GIN 인덱스 idx_scan·INVALID 유무·`security_logs`·`channel_delivery_logs` 행수와 PII 혼입 비율(2026-08-07 이후)·정보주체 수 추이·`order_field_changes` 본문 커버율·RUNNING 잔류 행 현황·레거시 stage 477건 정리 계획·전화 어긋남 36건 재판정·`designer_*` 데이터 유무·V1 링크 행수·드리프트 감사 2종 최근 결과·`structured_schema_version != 1` 행 유무·로그인 실패 시도량과 계정별 최대 연속 실패 [D1·D2·D3·D6]
- (e) 사고·회귀 실측: 운영 회귀 중 '테스트가 있었는데 못 잡은' 건수 vs '테스트가 없던 자리' 건수·핀 사고 4건의 사용자 노출 시간과 신고 건수·`erp-order-shared.js` fix 69·`naver_ingest.py` fix 46 중 운영 장애 건수·Sentry production 이벤트 수와 워커 유래 이벤트 0 의 이유(오류 없음 vs 배선 없음)·최근 90일 워커 재배포 횟수와 큐 정지 시간·자동 발송 놓친 평일 수·RQ 실패잡 현재 건수·Redis 폴백 발생 여부·production 승격 의존성 사고(solapi 미설치)의 노출 시간 [D2·D4·D5·D6·D7]
- (f) CI·빌드 로그: perf-gate advisory 예산 초과 횟수와 승격 PR 블로킹 횟수(PR #223 외)·cancelled 처리 규칙·pip 재시도 루프 발동 횟수·운영 이미지 실제 `pip freeze`(floating 17개의 해석 버전, 빌드마다 달랐는가)·이미지 크기(Add In Program 98파일·tests/ 포함 비용)·production 배포에서 docs/ 결합 실패 이력·세션이 로컬 PG 레인을 켜는 비율·스캐너 6종 CI 실행 시간·생산 KPI 테스트 flaky 유형(094682d57) [D1·D2·D4·D8]
- (g) 백업·경계: Railway 스냅샷 시각·보존값·PITR 창·오프사이트 최근 30일 성공률과 심박 stale 이력·복원 리허설 실행 이력과 마지막 RTO 실측(비공개 저장소)·pg_dump 가 wdcalculator 스키마를 포함하는지·R2 lifecycle 규칙·Cloudflare 경계의 CSP/WAF/레이트리밋/HSTS(앱 코드 0 이 경계 0 을 뜻하지 않음)·Railway static IP 3개가 worker 에만 붙는지(cron 이관 가능 여부) [D3·D6·D7]
- (h) 네이버·외부: 규격 변경 실제 빈도와 그때 3벌이 함께 바뀐 비율(`docs/plans/2026-08-13-naver-order-ingest-ledger.md` 대조)·정산 쿼터 초과(ABORTED_QUOTA)·403 뒤 사람 절차의 실제 위치·holidays 0.42 의 2026·2027 한국 공휴일(대체공휴일) 포함 여부 [D1·D2·D7]

### 사용자 결정 필요
- (a) 두 번째 개발자의 형태·시점(사람/에이전트, Windows/PowerShell, 한국어) → 온보딩 3문서 우선순위·README 재작성 범위·smoke 기본 모드 [D4·D8]
- (b) Socket.IO/gevent 층 유지 vs 폴링 축소 ADR(입력값: (c) 의 동시 연결·채팅 실사용) [D1]
- (c) 오프라인 쓰기 큐 채택/폐기 — 폐기면 `foms/api/foms_offline.py`·SW 큐·`tests/domains/test_p2_gate.py:173` 고정을 함께 제거 [D5]
- (d) legacy 셸 사용자 잔존 여부 → 셸 2벌 축소 [D5]
- (e) Railway 빌드에 node 단계 허용 여부 → 허용 안 하면 해시 매니페스트는 파이썬 빌드로 고정 [D5]
- (f) `security_logs` 영구 보존 결정 vs purge 1095일 기본값 중 유효 결정, 정보주체 수 기준 법률 판단(조문 단정 없이 열린 질문) [D6]
- (g) 공유 링크 30일·견적 본문의 고객 전화·시공 주소 표시 범위 [D6]
- (h) VIEWER·외부 협력사(외주 시공 기사)·현장 태블릿 공유 계정 정책 → 읽기 최소권한 매니페스트 입력값 [D6]
- (i) Cursor 러너 실사용 여부 → 훅 2벌→1벌(훅 코드는 8월 이후 커밋 0 인데 8~9월 session_stop 90회 실행) [D8]
- (j) 사업이 허용하는 RPO/RTO(하루치 주문·실측·도면·정산 손실 허용치) → DR 문서 목표값 [D3·D7]
- (k) WD_CALCULATOR 별도 DB 토폴로지 유지 여부 → 퍼시스턴스 정렬 순서·백업 단위 [D2·D3]
- (l) 정책 4벌 전수 대조 범위·세션 메모리 159파일 중 docs/context 로 옮길 범위 [D8]
- (m) 잠금 도구(pip-tools vs uv)·파이썬 목표(3.12 유지 vs 3.13 — 후자는 psycopg2-binary·Pillow·numpy·SQLAlchemy 핀 상향 선행)·psycogreen(2020) 대체 시점(psycopg3 또는 sync 워커) [D1]
- (n) pytest-cov·pip-audit 설치 허용 여부(설치 전 이름·이유 보고 규칙) → 사각 레인 3종 중 2종의 전제 [D4]
- (o) 오프사이트 백업·복원 절차 정본(비공개 저장소)을 이 저장소 runbooks 로 얼마나 옮길지 [D3·D7]

## ⑦ 부록(사소한 것)

워커 `minor_parked` 전부 + 부록 A + 본문에 못 들어간 항목. 헤드라인 아님. 앵커 없는 것은 (가설).

### D1
- 도달 불가 핀 — poetry 잔재(cleo·crashtest·dulwich·keyring·pkginfo·tomlkit·findpython·pbs-installer·trove-classifiers·installer·CacheControl·fastjsonschema·jaraco.*·pywin32-ctypes·requests-toolbelt·shellingham)·pyinstaller 잔재(pefile·altgraph)·pywebview 잔재(pythonnet·clr_loader·proxy_tools·bottle)·FastAPI 잔재(fastapi·starlette·uvicorn·python-multipart·python-jose·passlib·ecdsa·aiofiles·msgspec) — import 0 확인 10종(D1 워커 명령 출력), 나머지는 재측정 폐포 61 안(로컬 상한, §5 의 39 는 하한 — 가설)
- Flask-Session·Flask-Caching·Flask-Migrate·Flask-WTF·WTForms·Flask-SQLAlchemy·email_validator·waitress import 0(`db.py` 순수 SQLAlchemy)
- `Dockerfile:21` 미고정 setuptools/wheel 설치 후 `requirements.txt:90` setuptools==79.0.1 로 되돌림(권고 2건)
- et_xmlfile 고아 핀(openpyxl 제거 061730120 뒤) · numpy import 1건(scripts/tools 범위) · python-Levenshtein 이름 불일치
- `foms/services/security/backfill/crypto.py:85-88` win32crypt 미등재 Windows 전용 지연 import(부록 A)
- `app.py:64` 경고문과 `docs/guides/DEPLOYMENT_GUIDE.md:66-69` 가 eventlet 세대(실제는 gevent — `start.sh:76`) · `requirements.txt:112` 주석은 이미 gevent 로 정정됨(`grep -n eventlet requirements.txt app.py` → app.py 64행 한 줄뿐)
- 워커 시작 명령 3벌(`Procfile:5`·`start.sh:74`·`railway-worker.toml:7`) · gunicorn 인자 두 벌(`Procfile:3`·`start.sh:76`)
- 로컬 전역 인터프리터 오염: pip check 충돌 4(fastapi↔starlette·googletrans↔httpx·ortools↔protobuf·thinc↔numpy), `~ywebview` 잘못된 배포판 경고, 설치판이 핀과 다름(Jinja2 3.1.6·cryptography 49.0.0·holidays 0.99·rq 2.5.0·gunicorn 25.0.1) — `pip list --outdated` 는 전역 323패키지 기준이라 판정 근거로 쓰지 않음
- pytest 7.4.3·alembic 1.16.1·holidays 0.42·Pillow 10.1.0(2023-10)·SQLAlchemy 2.0.23(2023-11)·psycopg2-binary 2.9.9(2023-10) 노후 · `.query(` 710 vs `select(` 5(2.0 계열 비용 0, 2.1/3.0 재평가)
- `.github/workflows/coding-research-center-weekly.yml:24` 만 python 3.11 · `.github/workflows/postgres-lane.yml:87` 'safety guard' 는 스캔 도구 아님(grep 오탐)
- `tests/contracts/runtime/test_dockerfile_deploy_contract.py:19-26` 은 pip 명령 문자열·COPY 만 고정(버전·해시·파이썬 패치 사각) · `tests/harness/test_guard_policy.py:83` 이 `pip install -r requirements.txt` allow 를 계약으로 고정
- SOCKETIO_CLIENT_ENABLED 설정만 되고 읽는 곳 0 · `docs/guides/RAILWAY_ENV_VARS.md` 에 SOCKETIO/REDIS/FOMS_* 0 · `requirements.txt:1-2` UTF-16 주장은 반박(첫 바이트 'aiof' UTF-8) — 인코딩 주장은 (가설)
- 부트스트랩 5.3.0-alpha1 CDN·벤더 버전 문자열 없음·package.json 없음(→ D5) · 의존성 커밋 grep 91건은 노이즈, 본문 확인 7건만 채택(부록 A)

### D2
- `foms/api/channel/rooms.py:14-15` 가 루트 wdcalculator_db·wdcalculator_models 직접 import(어댑터 우회) · 루트 직접 import 9파일
- `foms/web/orders/dashboard.py:107` 채널톡 데스크 URL 리터럴 폴백
- `foms/services/common/map_generator.py` 980줄에 kakao/geocod/order 낱말 94회(스펙 `:260` common 규칙 위반) · `foms/services/common/address_converter.py` 카카오 HTTP 직접 호출
- `.dockerignore:35` 는 SCheduler 만 제외 → Add In Program 98파일이 `Dockerfile:43` `COPY . .` 로 이미지 포함(런타임 import 0, 참조는 docs 27파일·테스트 허용목록, 마지막 실질 커밋 2026-05-17) → D7 · 격리 트리는 `tests/contracts/runtime/test_ptc_physical_exactness.py:27` 허용목록에 등재돼 추적이 의도적
- `foms/persistence/designer` 1,515줄 런타임 사용 0, 의도적 보존(`tests/domains/test_designer_retired.py:1-10`); `foms/persistence/designer/repositories.py:339` 가 foms.services.designer 지연 import(persistence→services 유일 건)
- `db.py:38` 로컬 기본 DSN 에 비밀번호 리터럴 → D6 · `app.py` 가 erp_policy 심볼 11개 재수출(부록 A)
- `foms/platform/erp_blueprint.py` 22줄 필터 등록 전용 · `foms/platform/blueprints.py:115` 등록 순서 동결 실재(이유 = url_prefix `/api/orders` 10·`/erp` 9·`/api` 8 공유)
- `foms/persistence/wdcalculator/models.py` 15줄 재수출 어댑터는 정상(명시 `__all__`)
- 정본 스펙 Step 1~7 체크박스 전부 [x] 인데 §4 검증 기준 체크박스 전부 [ ](`docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md:540-550`)
- `docs/AI_STATUS.md:197` SFC-B2 constants 분해는 실행됨(status_constants 존재), HAPPYCALL 리터럴 py 4·tests 10
- `tests/contracts/runtime/foms_namespace_surface_tests.py` 2,573줄이 동결 계약을 한 파일에 — 계약 자체도 지식 집중 → D4
- 카카오 solapi SDK 지연 import 3곳(`foms/services/kakao_alimtalk.py:446,477,910`)이 함수마다 클라이언트를 새로 만든다(성능 영향 확인 필요) · services 플랫 모듈 127/311·api 루트 플랫 20파일(부록 A)

### D3
- `foms/services/db_indexes.py` 런타임 호출자 1(재수출)인데 `tests/domains/test_db_indexes.py`·`test_sqlite_startup_compat.py` 유지 — STARTUP-PURE-01 뒤 죽은 부트스트랩 헬퍼 후보
- `ix_orders_structured_data_gin`(containment) 소비자 0 — 운영 idx_scan 확인 뒤 제거 후보(`migrations/versions/phase_c_indexes_concurrently.py:37-41`) · 로컬 dev 중복 인덱스 10쌍(운영 여부 확인 필요, 부록 A)
- Order 날짜 컬럼 String(10)(`models.py:99-100`) 이라 날짜 범위 조회가 문자열 비교
- 두 엔진 풀 합산(db 5+5, wdcalculator 3+3; `wdcalculator_db.py:70-76` 주석의 '프로세스 4개' 전제는 gunicorn -w 2 × 복제 2 와 대조 필요)
- 병합 노드 `merge_prod_drawqueue_notifrole.py` downgrade pass 1건은 설계상 · 데이터 마이그레이션 phonewide_01 downgrade pass·naver_relation_00 '무손실 아님'(부록 A)
- `tools/ops/ensure_schema.py` 는 designer 테이블 대상인데 designer 런타임은 폐기 — predeploy 에서 매번 도는 죽은 보정
- 감사 purge 기본 보존(security_logs 1095일·access_logs 730일, `tools/ops/purge_audit_logs.py:9-16`)이 RPO·개인정보 정책과 따로 → D6 · security_logs message trigram 인덱스 본문 1B 당 2.06B(부록 A)
- ERP draft 부활 레이스는 코드 주석으로만 봉합(`foms/api/erp_orders_structured.py:1995`·`:2250`) — 재현 테스트 유무 (가설)
- 정산 동기화 RUNNING 회수 코드 0(`foms/services/integrations/naver_commerce/settle_sync.py:819-823`) → D7
- wdcalculator 4테이블 create_all 호출자는 `scripts/ops/db_admin.py:105`·`scripts/ops/init_wdcalculator_db.py:42` 와 격리 트리뿐 — 운영에서 누가 언제 돌리는지 문서 0 (가설)
- `Order.phone` 을 읽는 14곳 중 `foms/web/orders/trash.py:269` 만 `.like`
- CLAUDE.md 의 deepcopy+flag_modified 패턴을 어기면 조용한 미저장 — 실사례 앵커 없음 (가설)
- 로컬 dev DB 는 orders 14행·ERP 12건이라 성능·분포 판단에 쓸 수 없다(로컬 dev, 읽기 질의) · `alembic current` 로컬 = drawqueue_00(branchpoint), head 까지 21 리비전

### D4
- `.github/workflows/ci.yml:19` '실측 median 14.1분' 과 `:8` '5,329개 스위트' 는 낡음(현재 9,913건·2분 50초)
- pytest-playwright 핀 때문에 모든 레인이 `-p no:playwright` 반복(`.github/workflows/ci.yml:109`·`:121`·`:153`·`:181`, `.github/workflows/postgres-lane.yml:94`) — `pytest.ini:8-10` 이 addopts 를 비운 이유
- G4 프래그먼트 리스너 기준선이 파일별 정수 하드코딩(`tests/performance/test_perf_regression_guard.py:88-95`)
- tests/domains 접두 분포 order 35·erp 35·as 26·channel 21·shipment 14·drawing 14·state 13·settlement 13 — 단일 평면 439파일
- `docs/guides/TEST_GUIDE.md` 이름이 테스트 체계 문서로 오인되기 쉬움(실제는 ERP 화면 클릭 절차서)
- harness-ci.yml 은 checkout@v5/setup-python@v6, 나머지 v4/v5 — 액션 버전 정본 없음
- `tests/domains/test_password_kdf_contract.py:28-36` 은 Werkzeug 3(scrypt 기본) 전환 시 먼저 빨강이 되도록 설계됨(→ D1 상향 패킷의 첫 신호)
- `tests/harness/test_ci_watch.py:87-109` 가 perf-gate cancelled 를 실패로 못 박는데 `.github/workflows/perf-gate.yml:24-26` 은 cancel-in-progress: true — `docs/harness/policy/DECISIONS.md:23` '기각' 결정과 워크플로 드리프트(코드 결함 아님)
- CI 는 setup-node 없이 러너 기본 node 로 test_static_js_syntax 실행(node 부재 시 skipif 12파일·assert 파일 혼재)
- 8e7f8c7b4(2026-09-06) 공휴일 캐시 원자 쓰기 — xdist 공유 파일시스템 경합을 'flaky' 로 오인했던 사례가 tests/README 에 없음
- 핀 사고 4건의 발견 경로는 커밋 제목 기반이라 사용자 노출 여부는 (가설) · rev_99 writer 인벤토리의 (path, lineno) 튜플 비교 잔존 (가설, 부록 A)
- tests/harness 23파일 462건 중 tools/harness 밖(AI_STATUS·AI_CHANGELOG·hook_log)을 읽는 파일 4개 — 문서 예산 계약이 테스트 레인에 섞여 있음
- 보안 성격 테스트 셈법: 37 — `git ls-files tests | grep -iE 'secur|auth|xss|csrf|secret|permission|policy|signing|failopen|rate_limit|upload_auth' | grep -vE '__init__|geocode_retry|baseline_policy|channel_policy' | wc -l` → 37(D6 오탐 4 제외 뒤). D4 의 33 은 명령 원문이 없어 재현 불가 — 같은 취지 패턴 `git ls-files tests | grep -iE 'auth|security|xss|csrf|perm|secret|signing|failopen|login|rate_limit|share_token|upload_ticket' | wc -l` → 34 라 33 은 (가설). §5 의 17·74 도 셈법 차이

### D5
- Bootstrap 5.3.0-alpha1 CDN 직링크(`templates/partials/shared/layout_head.html:166`) + `templates/measurement/map_view.html:112` 5.1.3·FA 6.0.0 공존 · flatpickr 미버전 CDN·`integrity` 속성 0(부록 A) → D1
- 핀 없는 로컬 자산 23곳(script.js·global-nav-runtime.js·erp-mine-only.js·style-pro-max.css·`templates/channel/wam/layout.html:11-17`) 매 로드 no-cache — 해시 매니페스트로 자동 해소
- `static/js/runtime/layout-head-init.js`(529줄)·`static/js/runtime/layout-scripts-chat.js`(481줄)는 어떤 템플릿도 로드하지 않는 인라인 부트 사본 — 삭제 후보
- SW 가 htmx·alpine 을 프리캐시(`static/sw.js:31-35`)하지만 실사용은 극소(§5 hx- 6·x-data 2, 미재측정 — 가설)
- CACHE_VERSION 리터럴을 3개 테스트 파일이 각각 고정(`tests/domains/test_erp_runtime_shell_js_contract.py:212`·`tests/domains/test_sw_pii_cache.py:144`·`tests/domains/test_sw_push_contract.py:73`)
- jQuery `$(` 패턴 파일 2개(static/js) — 규칙 위반 여부는 본문 미개봉 (가설)
- `foms/api/foms_offline.py` 죽은 경로를 `tests/domains/test_p2_gate.py:173` 이 고정 — ADR 결정 전까지 코드·테스트·플래그 3중 유지 비용
- `!important` 는 static/css+templates 발생 수 2,656 — `grep -rho '!important' static/css templates | wc -l` → 2656; §5 의 1,529 는 `grep -rn '!important' static/css | wc -l` → 1529 로 범위(static/css)가 명시된 값이며 차이는 줄 수 대 발생 수 셈법이다 · 태블릿 전용 JS 5파일 174,184바이트 전 페이지 defer 로드 · RUM 기본 ON·rum-daily cron 은 production 파일만
- 유지할 긍정 자산: G1~G4 가드(`tests/performance/test_perf_regression_guard.py:3-5`), erp-pro @import 핀 게이트(`tests/performance/test_static_cache_headers.py:63-66`), SW 교차 출처 미개입(`static/sw.js:64-72`)·PII no-store 게이트, fragment top-level 리다이렉트(`foms/api/fragment.py:39-41`), wdcalculator node 계약 13파일
- 메모리 함정 앵커 확인: SW phantom(`docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md:49`·`static/sw.js:10-17`)·페이지 스코프 v3 누락(`docs/AI_CHANGELOG.md:39`)·surfaces 번들 v3 미적재(`templates/partials/shared/layout_head.html:176-180`) · DECISIONS 의 React/Vite 결정은 Add In Program 애드인 스택(D2·D8)
- docs/incidents 5건 중 프론트 자산 사고 문서 0 — 핀 사고 4건은 커밋 제목과 SW 주석으로만 기록 → D8

### D6
- `login_required` 가 API 라우트 248곳에서도 302 HTML 리다이렉트(`foms/web/auth/routes.py:247-267`) — `/api` 401/403 JSON 불변식(P1-13/P1-18)과 어긋남
- `role_required` 리스트 리터럴 6종(따옴표 혼용, 20·19·11·7·3·1) — 역할 집합이 데이터가 아니라 코드 상수
- `foms/services/erp_permissions.py:14-23` 허용 팀 상수(CS·SALES)와 403 메시지 문구 드리프트, 미등록 팀 mine scope 'all' 폴백(`:104-109`), services 층이 `foms.web.auth` import(→ D2)
- `.env.bak-20260828` 이 워킹트리에 있고 `.gitignore` 의 `.env` 정확 매칭에 안 걸림(check-ignore exit 1; 값은 열지 않음)
- 업로드 티켓 issue 가 클라이언트 `size` 를 받는다(`foms/api/files/upload_ticket_routes.py:66-70`) — complete 의 R2 HEAD 대조 여부 (가설)
- SESSION_COOKIE_SECURE·SameSite 는 production/railway 만, 세션 30일 슬라이딩이라 유휴 만료 없음(`foms/platform/app_factory.py:206-212`) · PasswordResetRequest 는 관리자 처리형(`models.py:1230-1238`) · 비밀번호 강도는 길이 8 + 휴리스틱(`foms/services/security/password_policy.py:39-60`)
- `user_can_read_order` 의 `order` 인자 미사용(`foms/services/orders/order_mutation_policy.py:395-396`) — 향후 확장 지점 · share presign 300초·storage 기본 3600초(`foms/services/storage.py:371`)로 수명 상수가 모듈마다 다름
- 감사 커버리지 인벤토리 coverage_percent 100.0·unaudited 0 — 쓰기 라우트 감사는 견고 · 견고한 것: 공유 링크(token_urlsafe(32)·sha256 저장·30일·회수·열람 기록·ZIP 200MB)·업로드 티켓(900초·서버 파생 키·tamper/type/size·권한 재검사)
- §4 D6 명령 3 의 이름 패턴 0건은 정상 · 명령 5 의 513건은 masked_counts 등 비-PII 용법 포함, PII 마스킹 실체는 _mask_phone·mask_account_no 2개(6 호출) · 로컬 dev 표본(security_logs 146·전화 패턴 0)은 운영 대표성 없음

### D7
- `docs/guides/DEPLOYMENT_GUIDE.md:66-69` eventlet `-w 1`·테이블 생성 서술(실제 gevent `-w 2`·alembic) — 문서 폐기 또는 헤더 교체 대상
- `docs/guides/RAILWAY_ENV_VARS.md:29` 의 railway_bootstrap 안내가 STARTUP-PURE-01(`foms/services/app_init.py:154-160`)과 충돌
- `railway-cron-receipt-purge.toml:9-16` `&&` 실패 커플링 1건 — toml 이 사문이라 실제 cron 설정과 대조 필요
- `foms/platform/sentry_setup.py:214-218` 환경 판정이 RAILWAY_PROJECT_NAME 접미사 명명 규약 의존
- `/healthz` 응답(`foms/api/health.py:22-37`)에 부팅 시각·alembic head 없음 — 롤백 뒤 스키마 버전 확인 수단 없음
- `tools/ops/check_deploy_secrets.py:12` 는 SECRET_KEY·KAKAO·DB 만 항상 검사, NAVER·REDIS·SOLAPI·R2 는 조건부거나 미검사
- `tests/contracts/runtime/test_dockerfile_deploy_contract.py:27` 은 CMD 한 줄만 고정 — start.sh 루프 배선은 `tests/services/integrations/test_naver_sync_wiring.py` 등 3파일이 부분 문자열 검사
- 루프 스크립트 4개가 각각 `from app import app` 으로 Flask 앱 전체 부팅(워커 컨테이너에서 최대 5회 초기화, `foms/services/sidefx_worker.py:60-66` 은 bare 엔진으로 회피)
- `tools/ops/wait_for_redis.py:10-12` 예산 초과 시 exit 1 → Railway 재시작 정책 의존(정책 값은 대시보드, 확인 필요)
- `railway.toml:5` 주석 '워커 2로 확장' 계획은 실제 Worker×1(`docs/AI_STATUS.md:9`)과 불일치 · `docs/runbooks/sidefx-worker-ops.md:17-19` 배포 절차가 폐기된 Config Path 방식을 가리킴
- `foms/platform/logging_setup.py:3-14` 로그는 stderr 단일 핸들러 — Railway 로그 뷰 밖으로 배송·보존되는 경로 0(로그 기반 경보 불가)
- 정산 API 403(앱 [정산] 그룹) 사람 절차는 저장소 runbook 앵커 없음(`docs/guides/NAVER_INGEST_SETUP.md:139` 는 IP 대조 1행만) (가설)

### D8
- `tools/harness/manifest.yaml` 은 확장자 yaml 에 내용 JSON, 등록 소스 6개뿐(`:14-20`) — 정본 레지스트리 역할 미달
- `docs/harness/foms_deploy_checks.json:6` 이 없는 `foms_feature_mode_matrix.json` 참조(④-17 에서 처리)
- `docs/AI_CHANGELOG.md:2-3` 헤더가 'Cursor Hook 자동 갱신·20개 유지' 라 하지만 79줄 손 작성
- `.claude/settings.local.json` 이 git 추적됨(개인 permissions allow 목록)
- CLAUDE_HOOK_LOG 300행 중 track_edits 스킵 271행(스크래치패드 63·워크트리 c:/tmp 다수) — 루트 밖 편집은 로그 대상 제외 권고
- `README.md:65-143` 하단 Google App Engine 레거시 절이 절반을 차지
- 브리프 '훅 10개' vs 실측 `.claude/hooks` py 11·배선 6 이벤트 8 커맨드; Cursor 훅 py 11·1,519줄·8 이벤트
- `.cursor/rules/00-project-context.mdc` 의 `/verify-result`·`/auto-status-update` 는 `.agents/workflows/` 의 Cursor 워크플로(verify-result.md·auto-status-update.md·start-task.md 실존), .claude/commands 엔 없음
- `docs/harness/policy/DECISIONS.md:35` 의 ept_b8 'DEAD 삭제' 기록에 복귀(51afc6ea1)·현행 참조 15파일 미반영(④-5 에서 처리)
- `.claude/hooks/session_start.py:40-42` 메모리 경로가 대문자 C--DEV-FOMS(실제 디렉토리 c--DEV-FOMS, Windows 에서만 동작) · MEMORY.md 164줄은 가지치기 임계 160 초과
- DECISIONS 항목은 `### [날짜]` 형식이라 `grep '^## '` 로는 0건(23건은 `^### \[` 로 셈) · AI_STATUS 40줄 계약은 `tests/harness/test_hook_log_hygiene.py:25-26` 이 4,000자 예산으로 강제(실재), AI_STATUS 366줄
- `tools/harness/verify_result.py --json` 은 success true, `import app` 서브프로세스 + 스펙 탐지만(편집·설치 없음, 120초 내 종료)
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` 가 폐기된 docs/harness/bundles·.agents/skills/gstack 경로 11개를 여전히 가리킴(2026-07-08 이후 미갱신) · 정본·안내서 8파일 백틱 경로 89개 중 20개 부재
- docs/plans 셈법: ls 451(미추적 .md 1 + workflow.js 포함) / .md 447 / git ls-files 475 — HEAD 062723348 의 검토 세트 3 .md + workflow.js 는 어느 색인에도 없음
- AGENTS.md 탐색용 브라우저 'Cursor browser MCP' vs CLAUDE.md 'gstack browse' 역할 분담 서술 차이 · guides 25 중 18 이 6월 이후 갱신 — 모집단은 `ls docs/guides/*.md | wc -l` → 25(사실 카드 27 은 `ls docs/guides | wc -l` 로 .md 아닌 항목까지 센 다른 모집단), 갱신 판정은 파일별 `git log -1 --format=%ad --date=short -- <파일>` 이 2026-06-01 뒤인 것 세기 → 18(§5 '안내서 전부 이전' 은 부분 반박, 핵심 4종만 낡음)
- 인라인 style 687곳이 정책 4벌 어긋남(AGENTS.md 인라인 금지 0)의 누적 결과라는 인과 (가설) → D5
- 세션 메모리 재측정 159파일·4,536줄(§5 164·4,610) · HEAD 이동(094682d57 → c38ae6225 → 58275b7e5 → 062723348)은 판정 영향 없음
