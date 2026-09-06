# FOMS 검토 보고서 ④ '지금' 구간 진행 원장 (2026-09-07)

> 플랜: `docs/plans/2026-09-07-foms-now-ratchet-plan.md`
> 정본 입력: `docs/plans/2026-09-06-foms-system-review-report.md` ④ '지금' 1~7.
> 규칙: 서브에이전트 완료 보고는 주장일 뿐이다. **총괄이 diff 를 직접 읽고 검증 명령을 직접
> 실행한 뒤에만** DONE 을 적는다. 각 task 는 검증 **출력 원문**을 그대로 붙인다.

## 상태 요약

| task | 제목 | 상태 | 갱신 |
|---|---|---|---|
| T0 | worktree 준비 + base 확인 | DONE | 2026-09-07 |
| T1 | 의존 방향 래칫 계약 테스트 | DONE | 2026-09-07 |
| T2 | 파일 크기 래칫 + 정본 경로 정정 | DONE | 2026-09-07 |
| T5 | 사고 원장·결정 기록 선등재 | DONE | 2026-09-07 |
| T3 | 드리프트 감사 배선 + 09-01 원인 줄 제거 | IN_PROGRESS (갈래 제거 DONE · 감사 배선 진행) | 2026-09-07 |
| T4 | 루프 하트비트 + 워커 Sentry 배선 | PENDING | - |
| T6 | 로그인 한도·잠금 + 레이트리미터 폴백 로그 | PENDING | - |
| T7 | 두 번째 개발자 부팅 경로 | PENDING | - |
| T8 | 게이트·push·CI·스테이징 QA | PENDING | - |

상태 값: PENDING / IN_PROGRESS / DONE / DONE(부분) / BLOCKED.

## 기준 커밋

- 지시 기준: `0d1e37fa7` (deploy)
- 세션 시작 시 메인 트리 HEAD: `0d1e37fa7` — **일치**
- `origin/deploy`: `da7d4ab9bb55e86750c50560f3a16f1aa7481745` (로컬 deploy 대비 2 ahead / 11 behind)
- 실작업 base(예정): `origin/deploy` + 문서 커밋 2건 cherry-pick — 지시 기준과 어긋나는 점 병기

```
$ git log --oneline -1
0d1e37fa7 docs(review): FOMS 시스템 전체 개발 검토 보고서 + 진행 원장

$ git rev-list --count origin/deploy..HEAD ; git rev-list --count HEAD..origin/deploy
2
11
```

---

## T0. worktree 준비 + base 확인

- 상태: DONE
- 완료 기준: `cd /c/tmp/foms-s-now0907 && pwd && git log --oneline -3` 에 문서 커밋 2건이 보인다.
- 실작업 base: `origin/deploy da7d4ab9b` + 문서 커밋 2건 cherry-pick(SHA 재작성: `46abfa17c`, `cde5d555b`).
  지시 기준 `0d1e37fa7` 과 SHA 는 다르고 내용은 같다(cherry-pick 재작성).
- 검증 출력:

```
$ cd /c/tmp/foms-s-now0907 && pwd && git log --oneline -4
/c/tmp/foms-s-now0907
cde5d555b docs(review): FOMS 시스템 전체 개발 검토 보고서 + 진행 원장
46abfa17c docs(review): FOMS 시스템 전체 개발 검토 프롬프트 + 멀티 에이전트 실행 세트
da7d4ab9b refactor(test): 정산 질의 계수 헬퍼를 한 곳으로 — 대시보드 테스트가 정본, 스트립은 import
144e8a930 docs(status): 정산 탭 CFO 감사 후속 19건 운영 반영 완료 기록(PR #301 · production 2fce6197c)

$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
[AUTO-INIT] ERP flat-column readiness verified.
APP_OK
```

---

## T1. 의존 방향 래칫 계약 테스트

- 상태: DONE — 완료 기준 총괄 직접 재현 통과 + 리뷰 fix 3건 반영·재검증 완료
- 완료 기준(보고서 원문): `foms/services` 아무 파일에 `from foms.web import auth` 한 줄을 넣으면
  그 테스트만 red, 되돌리면 green.
- 산출물: `tests/contracts/runtime/test_layer_dependency_ratchet.py` ·
  `tests/contracts/runtime/layer_dependency_baseline.json` (forbidden_edges 79 · lazy_imports 323)
- 검증 출력(총괄 직접 실행):

```
$ pwd && PYTHONIOENCODING=utf-8 python -m pytest tests/contracts/runtime/test_layer_dependency_ratchet.py -q
/c/tmp/foms-s-now0907
...                                                                      [100%]
3 passed in 2.94s

# from foms.web import auth 를 foms/services/db_indexes.py 끝에 CRLF 로 주입한 뒤
F..                                                                      [100%]
================================== FAILURES ===================================
______________________ test_no_new_forbidden_layer_edges ______________________
        edges, _ = scan_violations()
        added = sorted(set(edges) - set(_load_baseline()["forbidden_edges"]))
>       assert not added, _added_report("레이어 금지 방향 import 가 새로 늘었다.", added)
E       AssertionError: 레이어 금지 방향 import 가 새로 늘었다.
E         기준선 파일: tests/contracts/runtime/layer_dependency_baseline.json
E         새 위반 1건:
E           - foms/services/db_indexes.py::foms.web
E         되돌리는 법: 새 import 를 지우거나, 의도한 구조 변경이면 기준선 JSON 에 항목을 추가하고 리뷰를 받아라.
E       assert not ['foms/services/db_indexes.py::foms.web']
1 failed, 2 passed in 3.34s

# 원본 바이트 복원 후
RESTORE_SAME_HASH True
```

- 기준선 수치 단위 병기(플랜 §2 와 다름 — 결함 아님):
  플랜의 '지연 import 473' 은 **발생 기준**이고, 기준선이 동결한 값은 **고유 (파일, 모듈) 쌍 323** 이다.
  워커 실측: 발생 477 · alias 확장 667 · 고유 쌍 323. 계약이 요구한 '항목 집합 동결' 은 후자다.
- 리뷰 findings(전량 보존, blocker 0):
  1. [major] 기준선 402항목의 **재생성 방법이 코드·주석 어디에도 없다**. 스키마 테스트가 sorted·
     중복없음을 강제하므로 손편집하면 스스로 red 가 된다. → docstring 에 재생성 한 줄 + '재생성
     diff 를 사람이 읽는다' 경고 추가.
  2. [minor] `_imported_modules` 가 `ImportFrom.names` 를 버려 **`from foms import web` /
     `from .. import web` 가 게이트를 그대로 통과**한다(현재 foms/ 안 사용 0건이라 기준선 무영향).
     → alias 확장 후보를 함께 낸다.
  3. [minor] `scan_violations()` 가 테스트마다 foms/ 452파일 재파싱(실측 1.33s x 2회).
     메인 레인 `--dist loadfile` 에서 순수 낭비. → `lru_cache(maxsize=1)`.

### fix 반영 결과 (2026-09-07)

**T1 fix 3건**
1. `_import_from_base()` 를 뽑아 ImportFrom 절대 base 계산을 한 곳에 모으고, **base 가 레이어를
   못 낼 때만**(`_module_layer(base) is None`) alias 확장 후보를 낸다.
   - 워커가 지시(무조건 확장)를 실측 근거로 좁혔고 총괄이 수용했다: 무조건 확장은 판정력이 늘지
     않으면서 기준선만 edges 79→243 · lazy 323→875 로 부푼다(늘어난 716건 전부 같은 import 문의
     심볼 단위 중복, **새로 잡히는 import 문 0건**). 분해 진척 척도를 3배 부풀리지 않는 쪽을 택했다.
   - 무조건 확장이 필요해지면 조건문 한 줄 제거 + 기준선 재생성이면 된다(그때 값 243/875).
2. `regenerate_baseline() -> tuple[int, int]` 헬퍼 + docstring 재생성 한 줄 + '재생성 diff 를 사람이
   읽어라' 경고. 워커가 지시 예시의 `newline=''` 를 거부한 근거가 타당해 수용했다 — 그 예시는
   CRLF 기준선 441줄을 전부 LF 로 바꿔 '재생성해도 안 바뀐다' 확인 자체를 불가능하게 만든다.
   헬퍼는 기존 개행을 감지해 그대로 쓴다. 실행 결과 sha256 무변화(no-op) 확인.
3. `_scan_violations_cached()` `lru_cache(maxsize=1)`. 실측 2회 합계 2.658s → 1.294s.

**T2 fix 6건**
1. `excluded_dirs` 8개 → 5개(`.git`·`__pycache__`·`node_modules`·`.venv`·`venv`). 추적 소스 트리
   `data`·`Add In Program`·`SCheduler` 원복 후 재생성 — **py 177 · js 92 무변화**(그 트리에 임계
   이상 파일이 실제로 0개였음이 실측 확인).
2. `REQUIRED_DOCUMENTS`(4) · `REQUIRED_REMOVED`(3) 코드 상수 + 부분집합 assert.
3. `EXPECTED_EXCLUDED_DIRS` 정확 일치 assert + `test_scan_population_is_not_empty`(모집단 0 차단).
   `iter_source_files()` 로 워크를 공유해 중복 구현 없음.
4. `test_file_size_ratchet.py` docstring 에 재생성 한 줄 + 경고. 실행해 md5 무변화 확인.
5. `find_removed_path_mentions` 판정을 **백틱 토큰 안**으로 좁힘 + 실패 메시지에 '역사 서술이면
   백틱을 벗겨라' 경로 추가. 잔여 한계(워커 자진 신고): ``` 펜스 코드블록 안의 `apps/` 는 이제
   안 잡힌다 — 형제 검사 `extract_path_candidates` 와 판정면이 같아진 결과다. 별건.
6. `foms/README.md` 22행(Orders API 앵커) · 34행(src 트리) 정정 → `known_missing` 7 → 4.
7. `# type: ignore` 11곳 제거, 내장 제네릭 통일.

### 총괄 재검증 (무신뢰 — 워커 보고가 아니라 총괄이 직접 실행)

```
$ cd /c/tmp/foms-s-now0907 && pwd && PYTHONIOENCODING=utf-8 python -m pytest \
    tests/contracts/runtime/test_layer_dependency_ratchet.py \
    tests/harness/test_file_size_ratchet.py tests/harness/test_canonical_doc_paths.py \
    tests/domains/test_naver_candidate_phone_axis.py -q
/c/tmp/foms-s-now0907
............                                                             [100%]
12 passed in 2.34s

$ grep -c 'apps/' CLAUDE.md .cursor/rules/00-project-context.mdc foms/README.md
CLAUDE.md:0
.cursor/rules/00-project-context.mdc:0
foms/README.md:0

$ 기준선 수치
layer edges 79 lazy 323
py 177 js 92 excluded ['.git', '__pycache__', 'node_modules', '.venv', 'venv']
known_missing 4 documents 5
```

**T1 구멍이 실제로 막혔는지 — 주입 3형태(총괄 직접, 음성 대조군 포함)**

```
[T1] 'from foms import web'                        exit=1 1 failed, 2 passed in 1.99s
[T1] 'from .. import web'                          exit=1 1 failed, 2 passed in 2.14s
[T1] 'from foms.services import db_indexes'        exit=0 3 passed in 1.55s   ← 음성 대조군(같은 레이어는 green)
[T1] 복원 sha 일치: True
```
앞 두 형태는 **fix 전에는 통과하던 우회로**다. 세 번째는 통과해야 정상인 대조군이다.


---

## T2. 파일 크기 래칫 + 정본 경로 정정

- 상태: DONE — 완료 기준 총괄 직접 재현 통과 + 리뷰 fix 6건 반영·재검증 완료
- 완료 기준(보고서 원문): `grep -c 'apps/' CLAUDE.md .cursor/rules/00-project-context.mdc foms/README.md`
  전부 0, 없는 경로를 한 줄 넣으면 red.
- 산출물: `tests/harness/test_file_size_ratchet.py` · `tests/harness/file_size_baseline.json`
  (py 177 · js 92) · `tests/harness/test_canonical_doc_paths.py` ·
  `tests/harness/canonical_doc_paths_baseline.json` · 정본 3벌 정정
- 레인 판정: 두 테스트는 `tests/harness/` 라 `test_docs_facing_registry.py` 의 `_OTHER_LANES` 제외
  대상이다 → **ci.yml 문서 서브셋 등재 의무 없음**(CI-DOCSCOPE-01 해당 없음), `harness-ci.yml` 이 전담.
- 검증 출력(총괄 직접 실행):

```
$ cd /c/tmp/foms-s-now0907 && pwd && PYTHONIOENCODING=utf-8 python -m pytest tests/harness/test_file_size_ratchet.py tests/harness/test_canonical_doc_paths.py -q
/c/tmp/foms-s-now0907
.....                                                                    [100%]
5 passed in 0.49s

$ grep -c 'apps/' CLAUDE.md .cursor/rules/00-project-context.mdc foms/README.md
CLAUDE.md:0
.cursor/rules/00-project-context.mdc:0
foms/README.md:0

# CLAUDE.md 끝에 없는 백틱 경로 한 줄(docs/nonexistent_probe_dir/)을 주입한 뒤
E       AssertionError: 정본 문서가 저장소에 없는 경로 1개를 가리킨다:
E           CLAUDE.md: `docs/nonexistent_probe_dir/`
E         되돌리는 법 (둘 중 하나):
E           1) 권장 — 문서의 그 백틱 경로를 실제로 존재하는 경로로 고친다.
E           2) 저장소 밖 대상이라면 기준선의 'known_missing' 에 넣고 오름차순을 유지한다.
E              추출 규칙(extract_path_candidates)에 예외를 덧붙여 숨기지 마라 — 게이트가 죽는다.
1 failed, 1 passed in 0.62s

# 원본 복원 후
..                                                                       [100%]
2 passed in 0.01s
```

- 수치 단위 병기: 플랜의 'MISSING 20' 은 **발생 기준**, 구현 실측은 발생 15 · 고유 쌍 12 다.
- 리뷰 findings(전량 보존, blocker 0):
  1. [major] `assert_baseline_schema` 가 `documents`·`removed_top_level_paths` 의 비어있음을 안 본다
     → **배열을 비우면 두 테스트가 조용히 항상 통과**한다. 같은 구멍이 `excluded_dirs` 에도 있다
     (`foms`/`static` 한 줄이면 스캔이 통째로 빈다). → 코드 상수로 최소 집합 못박기.
  2. [minor→중요] `excluded_dirs` 에 **저장소가 추적하는 소스 트리** `data`(12) ·
     `Add In Program`(98) · `SCheduler`(6)가 승인 없이 들어갔다. 플랜은 스캔 범위 축소를 승인하지
     않았다(현재 그 트리 임계 이상 0건이라 수치 무영향). → 산출물·가상환경 계열만 남기고 재생성.
  3. [major] 기준선 269항목 **재생성 방법 없음**(T1 과 같은 유형).
  4. [minor] `find_removed_path_mentions` 가 백틱 밖 **산문까지** 훑어, 정본 문서가 사라진 트리를
     역사로 인용하면 무조건 red. AGENTS.md·README.md 가 모집단이라 승격 이력 적다가 빨개질 자리.
     → 판정을 백틱 토큰 안으로 좁힌다.
  5. [minor] 정본 3벌 중 `foms/README.md` 22행 `foms/api/orders/README.md` · 34행 `src/` ·
     `src/README.md` 가 여전히 없는 경로를 가리킨 채 `known_missing` 에 동결됐다. → 정정 후 7→4.
  6. [minor] `load_baseline()` 반환형 `Dict[str, object]` 탓에 `# type: ignore` 11곳.
     → `dict[str, Any]` + 내장 제네릭 통일(T1 은 0곳).

---

## T5. 사고 원장·결정 기록 선등재

- 상태: DONE
- 완료 기준(보고서 원문): `ls docs/incidents | grep -c 2026-0[89]` ≥ 4,
  `grep -c 'AS-AXIS' docs/harness/policy/DECISIONS.md` ≥ 1.
- 산출물: 신규 사고 문서 7건 + `docs/harness/policy/DECISIONS.md` 결정 2건(AS-AXIS-01 · ept_b8 정정)
  + 머리말 '규칙 vs 현실' 간극 기록(총괄 직접)
  - `docs/incidents/2026-08-03-rq-failed-jobs-2544-cleanup.md`
  - `docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md`
  - `docs/incidents/2026-08-14-as-dashboard-bulk-complete-vanish.md`
  - `docs/incidents/2026-08-24-structured-data-server-owned-keys-lost-on-save.md`
  - `docs/incidents/2026-08-31-worker-redeploy-queue-stall-852s.md`
  - `docs/incidents/2026-09-02-sidefx-dead-effects-1188-missing-kakao-key.md`
  - `docs/incidents/2026-09-03-as-axis-projection-escape.md`
- 검증 출력(총괄 직접 실행):

```
$ cd /c/tmp/foms-s-now0907 && pwd && ls docs/incidents | grep -c 2026-0[89]
/c/tmp/foms-s-now0907
8

$ grep -c 'AS-AXIS' docs/harness/policy/DECISIONS.md
2
```

- 리뷰 findings(전량 보존, blocker 0):
  1. [minor x2, 리뷰어 2인 공통] `DECISIONS.md` 머리말이 '최대 15개 유지' 를 규정하는데 착수 전
     23개였고 이번 2건으로 **25개**가 됐다. 문서가 자기 규칙을 어긴 채 커밋되면 다음 세션이 그
     규칙 줄 전체를 무시한다.
     → **총괄 처리(2026-09-07)**: 정리(10건 이동)도 상한 개정도 이번 세션 범위 밖이라 머리말에
     '현황: 25개 — 정리 보류(사유)' 를 명시해 간극을 기록으로 남겼다. 정리/개정 판단은 후속 F-1.

---

## T3. 드리프트 감사 배선 + 09-01 원인 줄 제거

- 상태: IN_PROGRESS — 갈래 제거·계약 테스트 DONE(총괄 재검증 완료), 감사 배선 진행 중
- 완료 기준(보고서 원문): 두 감사가 2주 연속 0건(워크플로 아티팩트), 스테이징에서 전화 변경 1회 뒤
  트리아지 자동 매칭이 같은 고객을 찾음(09-01 재현 시나리오).
- 이 세션에서 닫히는 부분: `workflow_dispatch` 1회 green + 로컬 감사 2종 출력 + 매칭 계약 테스트
  green + 스테이징 09-01 재현.
- 이 세션에서 못 닫는 부분: "2주 연속 0건" — 추적 예정일 2026-09-21.
- 산출물(2/2 중 1 완료): `foms/services/integrations/naver_commerce/order_candidates.py`(갈래 제거) ·
  `tests/domains/test_naver_candidate_phone_axis.py`(신규 계약 2)
- 배선 방식 **사용자 결정(2026-09-07)**: rum-daily 패턴 그대로. GitHub 에 등록된 비밀은
  `FOMS_STAGING_USERNAME`/`FOMS_STAGING_PASSWORD` 둘뿐이고 DB DSN 비밀이 없다(실측:
  `grep 'secrets\.' .github/workflows/*.yml`). rum-daily 가 같은 문제를 관리자 전용 조회
  엔드포인트로 풀었으므로(`tools/perf/rum_report_http.py` docstring) 그 구조를 따른다 —
  DB 접속 정보를 GitHub 에 넣지 않는다.
- 검증 출력(갈래 제거분, 총괄 직접 실행):

```
$ cd /c/tmp/foms-s-now0907 && pwd && PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_naver_candidate_phone_axis.py -q
/c/tmp/foms-s-now0907
..                                                                       [100%]
2 passed in 0.26s

$ grep -c 'Order.phone ==' foms/services/integrations/naver_commerce/order_candidates.py
0

# 테스트에 이빨이 있는지 — 소스 갈래를 되돌리면 red 여야 한다(총괄 직접)
[T3] 갈래 되돌린 뒤 exit=1 2 failed in 1.01s
      FAILED tests/domains/test_naver_candidate_phone_axis.py::test_candidate_lookup_uses_indexed_phone_axis_only
      FAILED tests/domains/test_naver_candidate_phone_axis.py::test_phone_column_not_referenced_in_candidate_query
[T3] 복원 sha 일치: True
[T3] 복원 후 exit=0 2 passed in 0.26s
```

- 워커 회귀 확인(단일 파일 실행): naver 계열 6파일 216 passed · `tests/domains --collect-only`
  6748 collected 오류 0.
- `or_` import 는 남겼다 — 같은 파일 `search_orders_for_attach`(1025행)가 여전히 쓴다(미사용 아님).
- 리뷰 findings: (감사 배선분 진행 중)

---

## T4. 루프 하트비트 + 워커 Sentry 배선

- 상태: PENDING
- 완료 기준(보고서 원문): 스테이징에서 루프가 도는 동안 하트비트 표
  `side_effect_worker_heartbeats`(`models.py:2677`)의 `NAVER_AUTO_DISPATCH` 행 `last_heartbeat_at` 이
  tick 마다 갱신되고, 루프 프로세스를 kill 하면 60초 넘게 갱신이 멈춘다(도구 무관 직접 질의);
  워커 실패잡 1건이 Sentry 에 environment=staging 이벤트로 잡힘.
- 산출물:
- 검증 출력:

```
(미실행)
```

- 리뷰 findings:

---

## T6. 로그인 한도·잠금 + 레이트리미터 폴백 로그

- 상태: PENDING
- 완료 기준(보고서 원문): 스테이징 잘못된 비밀번호 11회 → 429 + security_logs 에 LOGIN_FAIL 10 ·
  LOGIN_LOCKED 1; REDIS_URL 을 도달 불가 주소로 둔 테스트에서 warning 레코드 1건이 caplog 에 잡힘.
- 산출물:
- 검증 출력:

```
(미실행)
```

- 리뷰 findings:

---

## T7. 두 번째 개발자 부팅 경로

- 상태: PENDING (`.claude/skills` git add 는 사용자 승인 대기)
- 완료 기준(보고서 원문): 임시 디렉토리 clone 뒤 README 만 따라
  `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"` 와
  `timeout 300 python -m pytest tests/harness -q` 통과, `git ls-files .claude/skills | wc -l` → 5.
- 산출물:
- 검증 출력:

```
(미실행)
```

---

## T8. 게이트·push·CI·스테이징 QA

- 상태: PENDING
- 완료 기준: `python -c "import app; print('APP_OK')"` → `scripts/ops/pre_push_smoke.ps1` exit 0 →
  `deploy` push(production 금지) → 전 워크플로 나열로 CI green 확인 → 스테이징 QA(T3·T4·T6).
- 검증 출력:

```
(미실행)
```

---

## 후속 추적 (이번 세션 범위 밖 — 사용자 판단 또는 시간 필요)

| # | 항목 | 근거 | 필요한 것 |
|---|---|---|---|
| F-1 | `DECISIONS.md` 항목 25개 vs 머리말 '최대 15개' | 머리말 4행 · 실측 25 | 가장 오래된 10건을 `docs/evolution/` 로 옮길지, 상한 문구를 개정할지 **사용자 결정** |
| F-2 | T3 '두 감사 2주 연속 0건' | 보고서 ④ 지금 3 검증 칸 | 시간(워크플로 아티팩트 14일). 재확인 예정일 **2026-09-21** |
| F-3 | 읽기 경로 14곳 중 13곳이 아직 `Order.phone` 축 | 보고서 R1 | 이번 T3 은 1건만. 나머지는 '이번 분기' 구간 |
