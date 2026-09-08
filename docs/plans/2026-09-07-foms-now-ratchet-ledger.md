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
| T3 | 드리프트 감사 배선 + 09-01 원인 줄 제거 | DONE(부분) — 코드·스테이징 전량 통과, 2주 관측만 대기 | 2026-09-07 |
| T4 | 루프 하트비트 + 워커 Sentry 배선 | DONE(부분) — 코드 완료, 스테이징 검증 대기 | 2026-09-07 |
| T6 | 로그인 한도·잠금 + 레이트리미터 폴백 로그 | DONE(부분) — 코드 완료, 스테이징 검증 대기 | 2026-09-07 |
| T7 | 두 번째 개발자 부팅 경로 | DONE (검증 기준 1건 병기) | 2026-09-07 |
| T8 | 게이트·push·CI·스테이징 QA | DONE — push 3회·전 워크플로 green·스테이징 QA 완료 | 2026-09-07 |

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

- 상태: DONE(부분) — 코드 전량 완료·커밋 `125ad8cc9`. 스테이징 검증과 "2주 연속" 은 push 후/시간 필요
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
### 감사 배선 (2026-09-07)

산출물 5개:
- `foms/api/ops_drift.py` — `GET /api/foms/ops/drift-audit`(admin 전용, 미인증 401 · 비ADMIN 403,
  읽기 후 `session.rollback()`)
- `foms/services/orders/audit_as_axis_drift.py` — AS 축 집계 정본(신규, 아래 §역방향 참조)
- `tools/ops/audit_as_axis_drift.py` — 집계를 서비스에서 import 하는 CLI 껍데기로 축소
  (`--dsn`·`--json`·exit code 무변경)
- `tools/ops/drift_report_http.py` — requests 만, 크리덴셜 env only, step summary,
  exit 0=0건 · 1=드리프트(또는 `truncated`) · 2=크리덴셜 부재 · 3=조회/네트워크 실패
- `.github/workflows/drift-audit-daily.yml` — 18:20 UTC(03:20 KST), `workflow_dispatch` 동반,
  `timeout-minutes: 15`, `permissions: contents: read`

**드리프트로 세는 값**(모듈 docstring 이 정본):

| 감사 | 세는 값 | 안 세는 값 · 이유 |
|---|---|---|
| AS 축 | `mismatch` | `missing_projection`·`legacy_only` 는 둘 다 `mismatch` 의 **부분집합** — 더하면 같은 행을 두세 번 센다 |
| ERP flat | `SAFE + AMBIGUOUS` | 비-ERP·`structured_data is None` 은 `classify_order` 가 None 을 돌려 분모에서 빠진다. `AMBIGUOUS` 는 "자동으로 못 고친다"이지 "안 어긋났다"가 아니라 **센다** — 빼면 사람이 봐야 할 건이 매일 초록으로 덮인다 |

**상한 없음.** 매일 도는 게이트에서 조용한 절단이 가장 나쁜 실패라 상한을 두지 않았다. 대신
응답이 `truncated` 를 **항상** 싣고 조회 도구가 그 값을 명시 확인해 `True` 면 exit 1 로 실패한다.
서버 gunicorn `--timeout 120` 을 넘으면 도구가 exit 3 으로 시끄럽게 죽는다 — 거짓 초록 경로 없음.

### 총괄이 직접 고친 것 2건 (워커 산출물 수용 전)

1. **app → tools 역방향 의존 제거.** 워커가 `foms/api/ops_drift.py` 에서
   `tools.ops.audit_as_axis_drift.audit_session` 을 지연 import 했다(소유권 밖이라 옮기지 못하고
   자진 신고). 웹 런타임이 개발·운영 도구 트리에 묶이는 구조는 **보고서 R8 이 지적한 바로 그
   패턴**(개발 하네스 산출물이 운영 런타임의 부팅 의존성)이라 새로 만들지 않는다. 집계를
   `foms/services/orders/audit_as_axis_drift.py`(기존 `audit_*.py` 관례) 로 옮기고 CLI·엔드포인트가
   둘 다 그쪽을 향하게 했다. `grep -rn "from tools" foms/` → 0건.
2. **이관 중 내가 떨어뜨린 `drift` 키 복구.** 옮기면서 `_as_axis_summary` 가 `drift` 를 안 싣게
   돼 엔드포인트가 500(`KeyError: 'drift'`)이 났다. 워커 결함이 아니라 내 편집 결함이다.
   `{**summary, "drift": summary["mismatch"]}` 로 고치고 왜 `mismatch` 하나인지 docstring 에 적었다.

### 래칫이 이 커밋에서 잡은 것 (설계대로 작동)

```
E       AssertionError: 함수 안 지연 foms import 가 새로 늘었다.
E         새 위반 1건:
E           - foms/platform/blueprints.py::foms.api.ops_drift
```

`foms/platform/blueprints.py` 는 블루프린트 44개를 **전부** 함수 안에서 지연 import 한다
(`grep -c "    from foms"` → 44). 관례를 따른 **의도된 추가**라 기준선에 등재했다. 무조건
재생성하지 않고 diff 를 직접 읽었다:

```
edges  추가: []          edges  제거: []
lazy   추가: ['foms/platform/blueprints.py::foms.api.ops_drift']
lazy   제거: []
(79, 324)
```

### 검증 출력 (감사 배선분, 총괄 직접 실행)

```
$ cd /c/tmp/foms-s-now0907 && pwd && PYTHONIOENCODING=utf-8 python -m pytest \
    tests/contracts/runtime/test_layer_dependency_ratchet.py tests/harness/test_file_size_ratchet.py \
    tests/harness/test_canonical_doc_paths.py tests/domains/test_ops_drift_endpoint.py \
    tests/domains/test_naver_candidate_phone_axis.py tests/domains/test_foms_namespace_imports.py -q
/c/tmp/foms-s-now0907
198 passed in 3.50s

$ PYTHONIOENCODING=utf-8 python tools/ops/audit_as_axis_drift.py --help
usage: audit_as_axis_drift.py [-h] --dsn DSN [--json]
AS 축 투영 드리프트 감사(읽기 전용)

$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
APP_OK

$ url_map
/api/foms/ops/drift-audit ops_drift.drift_audit ['GET']
```

워커가 확인한 엔드투엔드(로컬 앱 + 실제 drift 주문 1건 → HTTP 200 → step summary 왕복):

```
**판정: 🔴 드리프트 발견** (총 2건 / 소요 3ms / 절단 False)
| 감사 | 검사 대상 | 드리프트 | 상세 |
| AS 축 투영(as_axis_status) | 1 | 1 | 투영 누락 0 · legacy 전용 0 |
| ERP flat 컬럼 | 1 | 1 | SAFE 1 · AMBIGUOUS 0 · CLEAN 0 |
```

### ci.yml 등재
**불필요.** `ci.yml:109` 가 `tests/` 전체를 돌려 신규 테스트가 자동 수집되고, `docs/` 를 읽지
않아 CI-DOCSCOPE-01 서브셋 등재 의무도 없다(`test_docs_facing_registry` green 으로 확인).

### 남은 검증 (push 후 / 시간 필요)
- `workflow_dispatch` 1회 green — deploy push 뒤 T8 에서
- 스테이징 09-01 재현 시나리오(전화 변경 1회 뒤 트리아지 자동 매칭) — deploy push 뒤 T8 에서
- **"두 감사 2주 연속 0건"** — 후속 F-2, 재확인 예정일 2026-09-21

### 총괄이 사용자에게 알릴 사항
조회 대상 기본값이 **production** 이다(`DEFAULT_BASE = https://lahom-production.up.railway.app`).
rum-daily 와 같은 전례이고 `FOMS_DRIFT_BASE_URL` 로 override 할 수 있다. 스테이징 크리덴셜
계정이 production 에서 ADMIN 이어야 200 이 난다(rum-daily 가 이미 그 전제로 돈다).

---

## T4. 루프 하트비트 + 워커 Sentry 배선

- 상태: DONE(부분) — 코드 완료·커밋 `41df23606`. 스테이징 검증은 push 후(T8)
- 완료 기준(보고서 원문): 스테이징에서 루프가 도는 동안 하트비트 표
  `side_effect_worker_heartbeats`(`models.py:2677`)의 `NAVER_AUTO_DISPATCH` 행 `last_heartbeat_at` 이
  tick 마다 갱신되고, 루프 프로세스를 kill 하면 60초 넘게 갱신이 멈춘다(도구 무관 직접 질의);
  워커 실패잡 1건이 Sentry 에 environment=staging 이벤트로 잡힘.
- 산출물: `scripts/maintenance/run_naver_auto_dispatch.py`(하트비트) ·
  `foms/services/jobs/tasks.py`(워커 Sentry) · `tests/domains/test_worker_loop_heartbeat.py`(신규 9건)

### 설계 결정과 근거

1. **창 밖 tick 도 하트비트를 갱신한다.** 안 그러면 하루 23시간 50분 동안 하트비트가 낡아 보여
   "루프가 죽었다" 와 "지금은 일할 시각이 아니다" 가 구분되지 않는다 — 그 구분이 이 배선의 목적이다.
2. **하트비트 실패는 본 작업을 막지 않되 삼키지도 않는다.** 되돌릴 수 없는 발송이 관측 배선 때문에
   멈추는 것은 더 나쁜 실패다. `logging.warning(exc_info=True)` + Sentry 로 남기고 tick 은 계속한다.
   `except Exception: pass` 아님. 두 성질을 각각 계약 테스트가 잡는다.
3. **metadata 는 고정 키 5개만**(`in_window`·`outcome`·`queued`·`blocked`·`total`). 결과 dict 가
   나중에 커져도 고객 정보(이름·전화·주소)가 새지 않고, 그 계약을 테스트가 봉인한다.
4. **워커 Sentry 판정 순서**: DSN 없으면 즉시 반환(어떤 모듈도 import 안 함) → 이미 클라이언트가
   붙었으면 반환(web 도 `foms/api/erp_map.py:407` 에서 이 모듈을 지연 import 하므로 이중
   `sentry_sdk.init` 은 앞 클라이언트를 교체해 전송 대기 이벤트를 유실시킨다) → `init_sentry()`.

### 지연 import 근거 — 총괄 직접 재실측

워커가 `foms.platform.sentry_setup` import 를 함수 안으로 미룬 근거를 총괄이 다시 쟀다:

```
# 최상단 import 였다면
$ python -c "from foms.platform.sentry_setup import init_sentry; ..."
modules 1414 app_factory True

# 지금(지연 import)
$ python -c "import foms.services.jobs.tasks; ..."   # SENTRY_DSN 없음
modules 1135 app_factory False sentry_sdk False
```

`foms/platform/__init__.py` 가 app_factory·blueprints 를 통째로 끌어와, DSN 없는 워커까지 web
import 그래프를 지고 뜬다. **의도된 구조 선택**이다. 값 드리프트는 계약 테스트가
`sentry_setup.SENTRY_DSN_ENV` 와 묶어 막는다.

### 래칫이 잡은 것 (설계대로 작동, 2번째)

```
E         새 위반 1건:
E           - foms/services/jobs/tasks.py::foms.platform.sentry_setup
```

재생성 diff 를 직접 읽어 정확히 그 1건뿐임을 확인하고 등재했다(`lazy` 324 → 325, `edges` 변화 0).
워커는 소유권 밖이라 편집하지 않고 **추가할 문자열만 보고**했다 — 규율대로다.

### 검증 출력(총괄 직접 실행)

```
$ cd /c/tmp/foms-s-now0907 && pwd && PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_worker_loop_heartbeat.py -q
/c/tmp/foms-s-now0907
9 passed, 1 warning in 10.06s

$ PYTHONIOENCODING=utf-8 python -m pytest tests/contracts/runtime/test_layer_dependency_ratchet.py \
    tests/harness/test_file_size_ratchet.py tests/harness/test_canonical_doc_paths.py \
    tests/domains/test_worker_loop_heartbeat.py tests/domains/test_ops_drift_endpoint.py \
    tests/domains/test_naver_candidate_phone_axis.py tests/domains/test_foms_namespace_imports.py \
    tests/domains/test_sentry_setup.py tests/domains/test_failopen_inventory.py -q
233 passed, 1 warning in 16.94s

$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
APP_OK
```

워커의 변이 검증(테스트에 이빨이 있는지): `_emit_heartbeat` 호출 제거 → 4건 red · 경고 로그를
`pass` 로 교체 → 1건 red · `_init_worker_sentry()` 호출 제거 → 1건 red. 세 파일 sha256 복구 확인.

### 사실 확인 — Sentry `environment` 가 갈리는 축

`RAILWAY_ENVIRONMENT` 가 **아니라** `RAILWAY_PROJECT_NAME` 이다(`resolve_environment()`):
`FOMS_ENV` 오버라이드 → `*-DEV`=staging / `*-PRODUCTION`=production → `RAILWAY_ENVIRONMENT` 원문
→ `local`. FOMS-DEV 프로젝트의 Railway 환경 이름도 `production` 이라 `RAILWAY_ENVIRONMENT` 만으로는
두 서버 이벤트가 한 태그로 섞이기 때문이다(그 함수 docstring 이 이유를 적어 뒀다).
워커 실측: DSN 있음 + `app.py` 미경유 → `client_active=True environment=staging`.

### 남은 검증 (push 후)
스테이징에서 `side_effect_worker_heartbeats` 의 `NAVER_AUTO_DISPATCH` 행이 tick 마다 갱신되고
루프 kill 시 60초 넘게 멈추는지, 워커 실패잡 1건이 Sentry 에 `environment=staging` 으로 잡히는지.

- 리뷰 findings:

---

## T6. 로그인 한도·잠금 + 레이트리미터 폴백 로그

- 상태: DONE(부분) — 코드 완료·커밋 `40d25bb1b`. 스테이징 11회 시나리오는 push 후(T8)
- 완료 기준(보고서 원문): 스테이징 잘못된 비밀번호 11회 → 429 + security_logs 에 LOGIN_FAIL 10 ·
  LOGIN_LOCKED 1; REDIS_URL 을 도달 불가 주소로 둔 테스트에서 warning 레코드 1건이 caplog 에 잡힘.
- 산출물: `foms/services/security/auth_rate/login_lockout.py`(신규 SSOT) ·
  `foms/services/rate_limit.py`(한도 배선 + 폴백 관측) · `foms/web/auth/routes.py`(잠금 판정·감사) ·
  `foms/services/audit_message_display.py`(`LOGIN_LOCKED` 라벨) ·
  `tests/domains/test_login_rate_limit_lockout.py`(신규 8건)

### 키 설계와 근거

- 키 = **아이디+IP**(`foms-login:<sha256(아이디)[:16]>:<get_remote_address()>`).
  아이디만 → 계정 DoS, IP 만 → 사무실 공용 회선 전원 잠김. 이 회사는 사무실 PC·현장 태블릿·
  iOS 웹뷰가 같은 회선을 쓴다.
- IP 는 ProxyFix 가 세운 `remote_addr` 만. 원시 XFF 파싱 없음(왼쪽 항목 위조 차단).
- **기본 `rate_limit_key` 를 쓰지 않은 이유**: 그 키는 세션 쿠키 hash 를 우선하는데 로그인은
  익명 엔드포인트라 쿠키가 클라이언트 임의 값이고, 쿠키를 갈아 끼우면 버킷이 무한히 회전한다.
- 아이디는 **정규화하지 않는다**. 접으면 서로 다른 계정이 카운터를 공유해 계정 DoS 가 생기고,
  안 접으면 인증에 성공할 수 없는 변형이 자기 카운터만 새로 쓸 뿐이라 공격자가 얻는 게 없다.
- 한도 `FOMS_LOGIN_RATE_LIMIT` 기본 `"10 per minute;100 per hour"`.
  임계 8회 / 창 15분 / 잠금 15분(`FOMS_LOGIN_LOCKOUT_*`). 셋 다 env 로 연다.

### 실제 회귀가 알려 준 설계 1건 — 성공은 한도를 깎지 않는다

한도를 그냥 걸었더니 `tests/services/integrations/test_naver_triage.py` 가 **20 failed** 로 터졌다.
`tests/conftest.py::auth_client`(321회 사용)가 한 프로세스에서 같은 아이디·IP 로 로그인을
반복하기 때문이다. **conftest 를 고치는 우회 대신 한도의 목적에 맞게 설계를 바로잡았다** —
`deduct_when=_login_attempt_failed` 로 성공한 로그인(302)은 버킷을 깎지 않는다. 한도가 막으려는
것은 무차별 대입이고 무차별 대입은 실패를 만든다. 자격증명을 이미 쥔 반복 로그인은 전역 기본
한도가 잡는다. flask-limiter 는 검사를 `test()`(요청 전)·차감을 `hit()`(응답 뒤)로 하므로
임계 초과 판정 시점은 그대로다.

원인 확정 근거(워커 실측): `FOMS_LOGIN_RATE_LIMIT="100000 per hour"` 로 두면 같은 명령이
`34 passed`.

### 잠금 설계

- **잠금 판정이 자격증명을 만지기 전에 온다** — 잠긴 쌍에는 비밀번호 해시 계산도, 계정 존재
  여부도 내주지 않는다.
- 세는 대상은 `unknown_username`·`inactive_account`·`bad_password` 3분기. `pending_approval` 은
  비밀번호가 맞은 시도라 **세지 않고**, 그 시점에 카운터를 지운다.
- `LOGIN_LOCKED` 감사는 replica 가 여럿이어도 **1건**이다 — 잠금 마커를 `storage.incr` 로 세우고
  1 을 돌려받은 요청만 "처음 잠근" 요청으로 본다.
- 저장소는 limiter 가 이미 쥔 것을 재사용(Redis 연결 풀 추가 0, 테스트는 `limiter.reset()` 하나로 격리).
- **fail-open**: 저장소 장애면 `warning(exc_info=True)` 남기고 로그인을 막지 않는다. 잡는 예외는
  저장소가 스스로 밝히는 `Storage.base_exceptions` 뿐이라 우리 쪽 프로그래밍 오류는 시끄럽게 죽는다.
- 비밀번호는 detail 에 없다(T8 규약). detail = `{reason, username, threshold, lock_seconds}`.

### 폴백 관측 — flask-limiter 에 콜백 API 가 없다

설치본 `flask_limiter 4.1.1` 소스를 직접 읽은 결과 폴백 훅/콜백 API 는 **없고** 유일한 노출은
`limiter.logger`(`_extension.py:215`)다. 거기에 핸들러를 단다.

**알림을 1건으로 만든 방법**: 라이브러리가 warning 을 낸 **직후에** `_storage_dead = True` 로
바꾸므로(`_extension.py:1158-1163`), 핸들러가 도는 시점에 그 값이 **아직 False** 인 레코드만이
"이번에 새로 떨어졌다" 다. 상태 플래그를 우리가 따로 들지 않고, 복구 시 라이브러리가 False 로
되돌리므로 **다음 장애에 자동 재무장**된다. 메시지 문자열은 대조하지 않는다(문구가 바뀌어도
알림은 나간다). 로거 이름이 바뀌면 관측이 조용히 죽으므로 계약 테스트가 이름을 고정한다.
저장소 URL 원문은 로그·Sentry 어디에도 안 싣고 scheme 만 싣는다.

### 부수적으로 막은 구멍 1건

`Limiter._check_request_limit` 은 `before_request` **0번**이고 본문 상한 강제는 **1번**이다(실측).
key_func 에서 조건 없이 `request.form` 을 읽으면 `/login` 의 16 KiB pre-parse 상한을 건너뛰고
전역 50 MiB 까지 파싱된다. 그래서 폼 인코딩 + 선언 Content-Length 가 그 라우트 상한 이내일
때만 파싱하고, 그 밖(청크 전송·초과 선언·multipart)은 IP 전용 버킷으로 떨어진다.

### 검증 출력(총괄 직접 실행)

```
$ cd /c/tmp/foms-s-now0907 && pwd && PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_login_rate_limit_lockout.py -q
/c/tmp/foms-s-now0907
8 passed, 1 warning in 6.88s

$ PYTHONIOENCODING=utf-8 python -m pytest tests/services/integrations/test_naver_triage.py \
    tests/domains/test_auth_enforcement.py tests/domains/test_auth_self_service.py \
    tests/domains/test_security_log_structured.py tests/domains/test_rate_limit.py -q
105 passed, 1 warning in 7.09s

$ grep -n "except.*: pass" foms/web/auth/routes.py foms/services/rate_limit.py foms/services/security/auth_rate/login_lockout.py
(docstring 1건 외 0건)

$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
APP_OK
```

**변이 검증(총괄 직접 — 테스트에 이빨이 있는가)**

```
[잠금 판정 무력화]              exit=1 3 failed, 5 passed
[실패 카운터 등록 반전]         exit=1 5 failed, 3 passed
[deduct_when 제거(성공도 차감)] exit=1 1 failed, 7 passed
[복원 후]                       exit=0 8 passed
```
세 파일 모두 sha256 복구 확인.

### 기준선 변화 없음
새 import 3개가 전부 허용 방향 + 최상위라 래칫 항목이 생기지 않았다(web→services,
services→services, services→platform). `test_failopen_inventory` 도 green — 새 `except` 가 전부
구체 예외라 broad-catch 인벤토리를 건드리지 않는다.

### 총괄 메모
- 라우트 한도 배선이 `foms/platform/realtime.py`(기존 `auth.register` 등)와 `init_limiter`(이번)
  두 곳으로 갈렸다. 워커 소유권 밖이라 그렇게 됐고 동작은 동일하다 — 나중에 한쪽으로 모으는
  정리가 가능하다. 후속 F-10.
- 앞으로 로그인 한도를 "성공까지 세는" 쪽으로 바꾸려는 변경이 오면 `tests/conftest.py` 에
  limiter 리셋을 넣어야 한다.

- 리뷰 findings:

---

## T7. 두 번째 개발자 부팅 경로

- 상태: DONE — 커밋 `1d0a4eebd`. 검증 기준 중 파일 수만 보고서 값과 다르다(아래 병기).
- 완료 기준(보고서 원문): 임시 디렉토리 clone 뒤 README 만 따라
  `PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"` 와
  `timeout 300 python -m pytest tests/harness -q` 통과, `git ls-files .claude/skills | wc -l` → 5.
- `.claude/skills` git add 는 **사용자 승인 완료**(2026-09-07, "넣기 — 승인").
- 산출물: `README.md`(전면 재작성) · `.env.example`(신규, 키 이름만 131줄) ·
  `.claude/skills/{diagnosing-bugs,handoff,wayfinder,writing-great-skills}`(신규 10파일)

### 고친 것

기존 README 가 **없는 파일 3개**를 실행하라고 지시했다 — `migration.py` · `reset_db.py` ·
`check_admin_account.py`(실측 전부 MISSING). 접속 정보도 코드가 안 읽는 `DB_USER`/`DB_PASS`/
`DB_NAME`/`DB_HOST` 4종 분리 방식인데 실제 정본은 `DATABASE_URL` 하나다(`db.py:35`).
여기에 GAE 레거시 절, `## test` 14줄, 관리자 기본 비밀번호 원문까지 있었다.

빈 클론에서 실제로 도는 7단계로 다시 썼다. `.env.example` 은 코드가 실제로 읽는 키만 넣었고
(os.environ 스캔 + 상수 정의 확인 — `SENTRY_DSN`·`FOMS_STARTUP_LOG_PATH` 는 상수 정의라
스캔에 안 걸려 따로 확인), 값이 실린 줄이 0인지 기계로 확인했다.

### 검증 출력(총괄 직접 실행 — 임시 클론 `/c/tmp/foms-clone-t7`)

```
$ git clone -q -b session/now0907 /c/tmp/foms-s-now0907 /c/tmp/foms-clone-t7
$ cd /c/tmp/foms-clone-t7 && test -f .env && echo EXISTS || echo NONE
NONE                      ← 클론에 .env 가 없다(진짜 새 개발자 조건)

# README 3단계대로 환경변수를 준 뒤 5단계
$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
[AUTO-INIT] ERP flat-column readiness verified.
APP_OK

# 7단계
$ DATABASE_URL=sqlite:///:memory: PYTHONIOENCODING=utf-8 python -m pytest tests/harness -q
469 passed in 312.17s (0:05:12)
```

### 검증이 실제로 잡은 결함 1건 (README 재정정)

처음 쓴 README 는 3단계에서 준 PostgreSQL `DATABASE_URL` 을 그대로 둔 채 7단계를 실행하라고
적었다. **클론에서 그대로 따라가니 red 였다**:

```
Failed: pytest session (tests/conftest.py): PostgreSQL DATABASE_URL is blocked.
Tests must not connect to, drop, truncate, or reset PostgreSQL.
Unset DATABASE_URL or use sqlite (e.g. sqlite:///:memory: ...)
```

`tests/postgres_guard.py:42` 가 테스트 세션이 실 DB 에 붙는 것을 코드로 막는다. 7단계를
`DATABASE_URL=sqlite:///:memory:` 로 고치고 왜 그런지(테스트가 운영/개발 DB 를 truncate 하는
사고 차단)를 함께 적었다. CI 도 같은 값을 쓴다(`.github/workflows/harness-ci.yml:44`).
**검증 기준이 문서 드리프트를 실제로 한 건 잡았다** — 이 task 의 목적 그대로다.

### 보고서 검증 기준과 다른 값 1건 (병기)

`git ls-files .claude/skills | wc -l` → **11**(보고서 기준값 5).

보고서의 5 는 '스킬 1개 = SKILL.md 1개' 가정에서 나온 값이다. 실제로는 SKILL.md 들이 형제
파일을 **직접 가리킨다** — `writing-great-skills/SKILL.md:9` 가 `GLOSSARY.md` 를,
`diagnosing-bugs/SKILL.md:29`·`:58` 이 `scripts/hitl-loop.template.sh` 를 가리킨다. SKILL.md 만
등재하면 '규칙이 가리키는 도구가 클론에 없다' 는 **같은 실패가 그대로 재발**하므로 형제
파일까지 등재했다(overnight 1 + 신규 10 = 11). 기준값을 임의로 낮추지 않고 병기한다.

커밋 전 10개 파일을 전부 읽어 자격증명·토큰이 없음을 확인했다(매치는 전부 문서 산문).

### 이번 범위 밖으로 남긴 것

- `alembic.ini:87` 에 로컬 개발용 DSN 이 비밀번호와 함께 하드코딩돼 있다. 이번 작업의 원인은
  아니고 고치면 로컬 흐름이 깨질 수 있어 손대지 않았다 — 후속 F-4 로 등재.
- README 4단계(`alembic upgrade head`)는 클론에서 **실행하지 않았다**. 로컬 개발 DB 가
  `drawqueue_00 (branchpoint)` 에 있어 head 까지 올리는 것은 사용자 DB 를 바꾸는 작업이다.
  alembic 이 클론에서 정상 기동해 리비전을 보고하는 것까지만 확인했다.

---

## T8. 게이트·push·CI·스테이징 QA

- 상태: DONE — push 3회(`0e3029e7e`·`4fdee6abe`·`963f369dd`), 전 워크플로 green, 스테이징 QA 완료.
- 완료 기준: `python -c "import app; print('APP_OK')"` → `scripts/ops/pre_push_smoke.ps1` exit 0 →
  `deploy` push(production 금지) → 전 워크플로 나열로 CI green 확인 → 스테이징 QA(T3·T4·T6).

### push 1회차 — `da7d4ab9b..0e3029e7e`

```
$ powershell -File scripts/ops/pre_push_smoke.ps1
=== PRE-PUSH SMOKE PASSED ===
EXIT=0

$ git push origin HEAD:deploy
   da7d4ab9b..0e3029e7e  HEAD -> deploy

$ git ls-remote origin deploy
0e3029e7eaade4f1618dd48614e353d95a115cb3	refs/heads/deploy

$ git rev-parse origin/production      # push 전후 동일 — production 불변
2fce6197c2866d9b3298c1235030bf9b45a6332c
```

범위는 **사용자 결정**(2026-09-07, "8개 전부"): 이번 세션 6건 + 검토 보고서·프롬프트 문서
2건(`46abfa17c`·`cde5d555b`, 코드 변경 0). 로컬 `deploy` 에만 있던 문서라 worktree 로 cherry-pick 해
왔고, 함께 올려야 플랜·원장이 가리키는 보고서가 원격에도 존재한다.

### CI 1회차 — **FOMS CI red 1건**, 나머지 3개 green

전 워크플로 나열로 판정한다(ci_watch 는 1개만 본다):

```
Harness CI           | completed | success
FOMS PostgreSQL Lane | completed | success
perf-gate (staging)  | completed | success
FOMS CI              | completed | failure
```

실패 1건뿐, 나머지는 `1 failed, 8757 passed, 609 skipped in 98.03s`.

```
FAILED tests/contracts/runtime/test_ptc_physical_exactness.py::test_ptc_committed_root_allowlist_exact
E       AssertionError: committed root allowlist drift (see 2026-04-07 §2.6.1):
E           only_in_repo=['.env.example']
E           missing_from_repo=[]
```

**근본 원인**: `_PTC_ROOT_ALLOWLIST` 는 저장소 루트 항목의 **닫힌집합**이라 새 루트 파일이
하나라도 생기면 그 자체로 빨개진다. T7 의 `.env.example` 이 등재 없이 들어갔다.

**왜 로컬에서 안 잡혔나**: `pre_push_smoke` 는 21타깃 서브셋이고 이 계약이 그 안에 없다.
검토 보고서 **R5("'초록' 의 정의가 세 겹으로 갈려 있다")의 실사례**다 — 로컬 초록·CI 빨강이
같은 커밋에서 동시에 성립했다. 후속 F-11 로 등재.

수정: 커밋 `4fdee6abe`, 등재 1줄 + 사유 주석 2줄.

### push 2회차 — `0e3029e7e..4fdee6abe`

```
$ powershell -File scripts/ops/pre_push_smoke.ps1
EXIT=0
$ git push origin HEAD:deploy
   0e3029e7e..4fdee6abe  HEAD -> deploy
$ git rev-parse origin/production
2fce6197c2866d9b3298c1235030bf9b45a6332c      # 여전히 불변
```

### 스테이징 배포 확인

```
$ curl -s https://lahom-dev.up.railway.app/healthz
{"commit":"0e3029e7eaade4f1618dd48614e353d95a115cb3","status":"ok"}

$ 신규 라우트 존재 확인(404 아님)
/api/foms/ops/drift-audit                    401
/api/foms/ops/definitely-not-a-route-xyz     404
```

### 스테이징 T6 — **통과** (보고서 검증 칸)

첫 시도(11회)는 잠기지 않았다. 원인은 **Railway 롤아웃 중 구/신 컨테이너 혼재**로 판단된다 —
직후 재시도에서 임계가 정확히 맞았다. 추측을 남기지 않기 위해 시도 수를 늘려 재현했다:

```
첫 429 = 8번째 시도
  flash: 로그인 시도가 너무 많아 잠시 잠겼습니다. 15분 뒤 다시 시도해주세요.
상태코드: [200, 200, 200, 200, 200, 200, 200, 429]
```

임계 8·잠금 900초가 코드값과 일치한다. 감사 행(스테이징 DB 읽기 전용 조회):

```
=== security_logs 최근 30분 ===
  LOGIN_FAIL     19
  LOGIN_LOCKED   1
  LOGIN_OK       3

=== LOGIN_LOCKED 상세 ===
2026-09-06 08:12:26 LOGIN_LOCKED | 로그인 잠금: 사용자 claude_master (연속 실패 8회)
  | {'reason': 'lockout_threshold', 'username': 'claude_master', 'threshold': 8, 'lock_seconds': 900}
```

`LOGIN_FAIL` 19 = 롤아웃 중 11 + 재현 8. **`LOGIN_LOCKED` 는 1건**(중복 없음 — replica 안전장치가
의도대로 작동). detail 에 비밀번호 없음. 계정은 실서버 측정 전용 `claude_master`(staging, 전 활동
허용)이고 잠금은 15분 뒤 자동 해제된다.

### 스테이징 T4 — **통과** (보고서 검증 칸)

```
=== side_effect_worker_heartbeats ===
  DELIVERY              last=2026-09-06 08:14:53  age=8s   meta=None
  EXPIRY_SCAN           last=2026-09-06 08:14:53  age=8s   meta=None
  NAVER_AUTO_DISPATCH   last=2026-09-06 08:14:38  age=23s  meta={'total': 0, 'queued': 0,
                                                              'blocked': 0, 'outcome': None,
                                                              'in_window': False}
  RETENTION             last=2026-09-06 08:14:53  age=8s   meta=None
```

tick 전진 확인(2회 표본):

```
sample1: 2026-09-06 08:17:38.930966
sample2: 2026-09-06 08:19:00.290133
전진했는가: True | 간격 81.4초
```

`in_window: False` 인데도 갱신된다 — **"창 밖 tick 도 갱신한다" 설계가 실서버에서 그대로
확인됐다.** metadata 는 고정 키 5개뿐이고 고객 정보 없음.

**못 닫은 절반**: "루프 프로세스를 kill 하면 60초 넘게 갱신이 멈춘다". 스테이징 worker 컨테이너를
재시작해야 하는데 그 컨테이너가 `rq worker` 본체를 함께 들고 있어 큐가 멎는다(2026-08-31 재배포
852초 정지 전례). 관측 배선을 확인하려고 운영 큐를 멈추는 것은 비용이 이득보다 크다고 판단해
**하지 않았다**. 갱신 정지 판정은 위 `age` 값으로 사람이 읽을 수 있다.

**Sentry 절반도 못 닫았다**: 스테이징 두 서비스 모두 `SENTRY_DSN` **unset** 이라 `init_sentry()` 가
설계대로 no-op 이다. "워커 실패잡 1건이 Sentry 에 environment=staging 이벤트로 잡힘" 은 DSN 을
넣기 전에는 확인할 수 없다 — **사용자 결정 사항**(후속 F-12).

**F-8 해소**: `RAILWAY_PROJECT_NAME` 이 web·worker **양쪽 모두 `FOMS-DEV`** 로 실측됐다.
`resolve_environment()` 분기(`*-DEV` → `staging`)가 워커에서도 성립한다.

### 스테이징 T3 — 일부 잔여

`workflow_dispatch` 는 **불가능하다**(예상된 제약, 워커가 옮겨 적은 rum-daily 주석 그대로):

```
$ gh workflow run drift-audit-daily.yml --ref deploy
HTTP 404: workflow drift-audit-daily.yml not found on the default branch
```

GitHub 은 `workflow_dispatch` 대상 파일이 **기본 브랜치(production)** 에 있어야 인식한다. production
승격은 이번 범위 밖이므로 이 검증은 승격 후로 넘긴다(후속 F-13). 대신 도구·엔드포인트 왕복을
스테이징으로 직접 확인했다.

### 스테이징 도구 왕복 — 통과, 그리고 게이트 설계 결함 1건 노출

`FOMS_DRIFT_BASE_URL` 을 스테이징으로 두고 `tools/ops/drift_report_http.py` 를 그대로 돌렸다.
로그인 → 엔드포인트 → step summary → exit code 가 전부 왕복했다(소요 681ms, 절단 False).

그런데 결과가 **1,888건**이었다. 절대 0건 기준이면 이 게이트는 **첫날부터 매일 실패**한다.
매일 오는 빨간불은 곧 아무도 안 본다 — 관측 배선이 죽는 가장 흔한 방식이다. 검증이 배선의
설계 결함을 잡은 것이므로 덮지 않고 사용자에게 올렸다.

### 운영 실측 (사용자 결정 "재보기", 2026-09-07)

운영에는 아직 조회 엔드포인트가 없다(승격 전 `2fce6197c`). 그래서 **계정 잠금 해제 없이**
같은 집계 함수를 읽기 전용 DB 직결로 돌렸다 — 정책 §4 "DB 직결은 읽기전용" 준수, 쓰기 0,
HTTP 0, `claude_master` production 행은 잠긴 채 그대로다.

```
=== AS 축 투영 ===
  검사 659 / 불일치 0 / 투영누락 0 / legacy전용 0
=== ERP flat 컬럼 ===
  total 3001 / CLEAN 1251 / SAFE 825 / AMBIGUOUS 925 => 드리프트 1750
  AMBIGUOUS 사유: {'PAYMENT_AMOUNT_DRIFT': 925}
  SAFE 드리프트 컬럼 상위: {'measurement_date': 770, 'scheduled_date': 475,
    'erp_phone_digits': 93, 'erp_drawing_updated_at': 78, 'erp_stage_updated_at': 75,
    'manager_name': 60, 'erp_stage_code': 54, 'erp_measurement_date': 21}
```

**AS 축은 운영에서 이미 0건**이다 — 보고서가 요구한 "2주 연속 0건" 의 출발점이 0 이다.
ERP flat 1,750건은 보고서 R1("사본을 맞추는 주체가 트리거가 아니라 호출 규약")이 숫자로
확인된 것이다.

### 게이트를 기준선 래칫으로 전환 (사용자 결정)

커밋 `9e51b2e73`. 판정을 절대 0건에서 `tools/ops/drift_baseline.json` 대비 **순증**으로 바꿨다.
T1(의존 방향)·T2(파일 크기) 래칫과 같은 방식이다.

- 기준선: AS 축 0(`must_stay_zero` — 이미 목표 상태라 1건도 허용 안 함) / ERP flat 1750.
- **엔드포인트는 그대로 절대값을 돌려준다.** 래칫은 조회 도구에만 있고, 리포트는 절대값·
  기준선·증감을 함께 보여준다 — 1,750이라는 숫자를 숨기지 않는다.
- 기준선 부재·스키마 불일치는 **예외**다. 기본값 폴백 없음 — 0건으로 떨어지면 매일 빨간불,
  무한대로 떨어지면 게이트가 죽는데 어느 쪽도 조용히 일어나면 안 된다.
- 기준선은 **production 전용**이다(워크플로가 production 을 조회한다). 스테이징으로 돌리면
  DB 가 달라 증감이 0 이 아닌 것이 정상이다.

계약 테스트 9건이 판정을 잠근다 — 기준선과 같으면 통과 · 줄면 통과(음성 대조군) · 1건 늘면
실패 · AS 축은 0에서 1건만 늘어도 실패 · 기준선 부재/스키마 불일치는 예외 · 리포트가 절대값과
증감을 함께 낸다.

```
$ PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_drift_ratchet.py -q
9 passed in 0.11s

$ 계약 세트(엔드포인트·래칫·contracts/runtime·문서경로·크기·docs 레지스트리)
39 passed in 3.47s

$ 스테이징 왕복(래칫 적용 후)
**판정: 🔴 기준선 대비 순증** (총 1888건 / 소요 711ms / 절단 False)
| AS 축 투영 | 507  | 0    | 0    | 0       | 투영 누락 0 · legacy 전용 0 |
| ERP flat  | 2313 | 1888 | 1750 | 🔴 +138 | SAFE 886 · AMBIGUOUS 1002 · CLEAN 425 |
```

### 스테이징 09-01 재현 시나리오 — **통과**

보고서 검증 칸: "스테이징에서 전화 변경 1회 뒤 트리아지 자동 매칭이 같은 고객을 찾음".

09-01 사고의 근본 원인은 **읽기 쪽**이었다 — 매칭이 sync 규약 밖 컬럼(`orders.phone`)을 함께
봐서 낡은 값에 걸렸다. 그래서 앱이 실제로 쓰는 두 함수를 그대로 태웠다:
`sync_erp_flat_columns`(쓰기 규약) → `find_order_candidates`(읽기 축).

가상 주문은 `CLAUDE-TEST-` 접두어 + 더미 연락처(`010-0000-000x`)로 만들고 끝나면 지웠다.

```
[준비] 주문 #4727 생성 · phone=010-0000-0001 erp_phone_digits=01000000001
[변경] 새 전화 010-0000-0002 · orders.phone=010-0000-0001 erp_phone_digits=01000000002
       (orders.phone 은 sync 규약 밖이라 낡은 값이 남는다: True)
[매칭] 새 번호로 조회 -> [4727, 4387] / 대상 포함: True
[음성 대조군·이름 다름] 옛 번호로 조회 -> [4386] / 대상 포함: False
[정리] 주문 #4727 삭제 · 잔존: False
```

**기전이 그대로 보인다** — 전화를 한 번 바꾸면 `erp_phone_digits` 는 새 번호로 따라오지만
`orders.phone` 은 낡은 값에 멈춘다(sync 규약 밖). 매칭이 인덱스 컬럼 단독을 보므로 새 번호로
같은 고객을 찾는다.

**음성 대조군 설계 주의**: 처음에는 옛 번호로도 대상이 나왔다. 매칭이 전화 말고 **이름 축**도
점수화하기 때문이지 전화 폴백이 남아서가 아니다. 이름을 다르게 준 두 번째 대조군에서 옛
번호로는 대상이 **안 나온다**. 양성만 보고 통과라 했으면 축을 잘못 짚을 뻔했다.

정리 확인: `SELECT ... WHERE customer_name LIKE 'CLAUDE-%'` 에 이번 세션 주문은 없다.
남아 있는 24건은 2026-08-13~09-01 타 세션 잔여이고 그중 4건은 `deleted_at IS NULL` 이다 —
내 몫이 아니라 손대지 않았다(후속 F-16).

### 최종 CI — 전 워크플로 green (`963f369dd`)

```
Harness CI           | completed | success
FOMS PostgreSQL Lane | completed | success
FOMS CI              | completed | success
perf-gate (staging)  | completed | success
```


---

## 후속 추적 (이번 세션 범위 밖 — 사용자 판단 또는 시간 필요)

| # | 항목 | 근거 | 필요한 것 |
|---|---|---|---|
| F-1 | `DECISIONS.md` 항목 25개 vs 머리말 '최대 15개' | 머리말 4행 · 실측 25 | 가장 오래된 10건을 `docs/evolution/` 로 옮길지, 상한 문구를 개정할지 **사용자 결정** |
| F-2 | T3 '두 감사 2주 연속 0건' | 보고서 ④ 지금 3 검증 칸 | 시간(워크플로 아티팩트 14일). 재확인 예정일 **2026-09-21** |
| F-3 | 읽기 경로 14곳 중 13곳이 아직 `Order.phone` 축 | 보고서 R1 | 이번 T3 은 1건만. 나머지는 '이번 분기' 구간 |
| F-4 | `alembic.ini:87` 에 로컬 DSN 이 비밀번호와 함께 하드코딩 | T7 검증 중 발견 | env 로 옮길지 사용자 결정(로컬 흐름 영향) |
| F-5 | 나머지 루프 4개에 하트비트 0 | T4 조사 | escalation·수집·정산·지오코딩. 지오코딩 스윕은 `app` 미import 라 **Sentry init 자체가 없다** |
| F-6 | `rq worker` 본체에 하트비트 0 | T4 조사 | 큐 소비가 멎어도 표에 안 나타난다 |
| F-7 | `tools/ops/run_domain_side_effect_outbox.py` 에 `init_sentry()` 호출처 없음 | T4 조사 | 하트비트 3종은 있으나 SIDEFX 워커 예외는 아직 아무 데도 안 간다 |
| F-8 | 워커 서비스에 `RAILWAY_PROJECT_NAME` 이 실제로 주입되는지 미확인 | T4 조사 | 안 되면 staging·production 이벤트가 한 태그로 섞인다. 실서버에서 1회 측정 필요 |
| F-9 | `check_sidefx_readiness.py` 가 `WORKER_KINDS` 3종 고정 순회 | T4 조사 | 새 kind `NAVER_AUTO_DISPATCH` 를 쓰기만 하고 아무도 읽지 않는다. 일반화는 보고서 12~24개월 23번 |
| F-10 | 라우트 한도 배선이 `realtime.py` 와 `init_limiter` 두 곳으로 갈림 | T6 | 동작 동일. 한쪽으로 모으는 정리 |
| F-11 | `pre_push_smoke` 21타깃 서브셋에 닫힌집합 계약이 없다 | T8 CI red 실사례 | 로컬 초록·CI 빨강이 같은 커밋에 성립. 보고서 R5 축 |
| F-12 | 스테이징 `SENTRY_DSN` unset | T8 실측 | DSN 을 넣을지 **사용자 결정**. 넣기 전에는 워커 Sentry 배선을 실서버에서 확인할 수 없다 |
| F-13 | `drift-audit-daily` cron·dispatch 는 production 승격 후에만 작동 | T8 실측(HTTP 404) | 승격 시 dispatch 1회로 `elapsed_ms` 실측 권장 |
| F-14 | 운영 `erp_phone_digits` 드리프트 **93건** | 운영 실측 2026-09-07 | T3 이 전화축을 이 컬럼 단독으로 만들었다. 93건은 그 축이 낡은 상태다. `tools/ops/backfill_erp_flat_columns.py`(SAFE 대상 재동기)로 정리 가능 — **운영 쓰기라 사용자 승인 필요** |
| F-15 | 운영 ERP flat 드리프트 1,750건 | 운영 실측 2026-09-07 | 래칫으로 악화는 멈췄다. 줄이는 것은 보고서 ④ '이번 분기'(생성 컬럼·트리거로 사본 규약 대체) 몫 |
| F-16 | 스테이징 `CLAUDE-TEST-` 잔여 24건(그중 4건 `deleted_at IS NULL`) | T3 재현 중 확인 | 2026-08-13~09-01 타 세션 잔여. 내 몫이 아니라 손대지 않았다 |

---

## T9. 운영 ERP flat 백필 (후속 F-14 실행 — 사용자 승인)

- 상태: **IN_PROGRESS** — dry-run 완료·apply 승인 받음. `--approval-token-file` 발급 경로 조사 중.
- 승인 이력(2026-09-07): "정리하기" → "먼저 뭐가 바뀌는지 보기"(표본 제시) → **"적용하기"**.
- 작업 위치: worktree `/c/tmp/foms-s-now0907`, 브랜치 `session/now0907`.

### 준비물 (이미 만들어 둠)

- 보호 artifact root: `C:\tmp\foms-remediation` (ACL 잠금 확인 `_windows_acl_ok` → True)
- 감사 artifact: `C:\tmp\foms-remediation\startup-flat`
  `manifest_sha256=77f605c029a57b6b69a1239cc5eec79a61009037d4fd044c47d0477268941be9`
  `mapping_sha256=7a2d910263071f2a832a6abd4af5f4833d0ceab8c0e9ac943083864a71574c35`
  counts `{total: 3002, safe: 825, ambiguous: 925, clean: 1252}`
  **운영 감사 자료(암호화)라 작업이 끝나면 지운다.**
- 운영 DSN: `<scratchpad>/prod_dsn.txt` (railway FOMS-PRODUCTION Postgres `DATABASE_PUBLIC_URL`)

### dry-run 결과 (데이터 변경 0)

```
$ python tools/ops/audit_erp_flat_columns.py --output-dir <root>/startup-flat --db-instance-id foms-production
{"counts": {"total": 3002, "safe": 825, "ambiguous": 925, "clean": 1252}, ...}
exit = 0

$ python tools/ops/backfill_erp_flat_columns.py --artifact-dir <root>/startup-flat \
    --phase STARTUP_FLAT --db-instance-id foms-production --dry-run --batch-size 500
{"phase": "STARTUP_FLAT", "safe_targets": 825, "drift_before": 825, "mode": "dry-run"}
[DRY-RUN] no rows written; approval + --apply required to resync.
exit = 0
```

### 무엇이 바뀌는지 — 유형별 전수 분류 (읽기 전용 실측)

| 컬럼 | 유형 | 건수 |
|---|---|---:|
| measurement_date | NULL → 값 | 480 |
| scheduled_date | NULL → 값 | 323 |
| measurement_date | NULL → `''` | 290 |
| scheduled_date | NULL → `''` | 150 |
| erp_phone_digits | 값 → 값 | 93 |
| erp_stage_updated_at | NULL → 값 | 75 |
| erp_stage_code | NULL → 값 | 54 |
| manager_name | NULL → `''` | 46 |
| erp_drawing_updated_at | NULL → 값 / 값 → 값 | 41 / 37 |
| erp_measurement_date | NULL → 값 | 21 |
| erp_construction_date | NULL → 값 | 19 |
| manager_name | NULL → 값 | 14 |
| scheduled_date | 값 → 값 | 2 |
| erp_owner_team_code | NULL → 값 | 1 |

실제 값이 바뀌는 것 **1,253개**, `NULL → ''` **486개**. `AMBIGUOUS` 925건(전부
`PAYMENT_AMOUNT_DRIFT`)은 도구가 안 건드린다.

### `NULL → ''` 486건의 안전성 — 읽는 자리 전수 확인

날짜 칸에서 NULL 과 빈 문자열은 쿼리가 다르게 본다. 해당 컬럼을 NULL 로 판정하는 자리를
`foms/`·`tools/`·`scripts/` 전수로 찾았다:

- `measurement_date` 4곳(`foms/web/measurement/dashboard.py:788·798·811·816`) — **전부**
  `!= None` 과 `!= ""` 를 같이 본다
- `scheduled_date` 3곳(`foms/web/measurement/dashboard.py:800·833`,
  `foms/web/shipment/dashboard.py:90`) — **전부** 둘 다 본다
- `manager_name` — NULL 로 거르는 자리 **0곳**

→ 486건은 화면 동작을 바꾸지 않는다.

### 적용 시 눈에 보이는 변화 (사용자에게 미리 알린 내용)

측정일이 비어 있던 480건·시공 예정일이 비어 있던 323건이 날짜를 갖게 되므로 **그 날짜로
거르는 화면에 지금까지 안 보이던 주문이 올라온다**(측정 대시보드 큐·출고/설치 알림·건수 KPI).
잘못 느는 것이 아니라 빠져 있던 것이 돌아오는 것이지만 아침 큐 숫자가 어제와 달라진다.
전화 93건은 네이버 트리아지에서 다시 전화로 찾힌다(T3 이 전화축을 이 칸 단독으로 바꿨다).

### 다음 한 걸음 (여기서 멈춰 있다)

`--apply` 는 `BACKFILL_APPLY` **OPS approval 토큰 파일**을 요구한다. 토큰 없는 `--apply` 는
거부되고 아무것도 안 쓴다(exit 2). 발급·소비 경로 조사 지점:
`foms/services/security/backfill/runs.py:317-420`(approval 소비),
`foms/services/security/backfill/manifest.py:25·144`(`BACKFILL_APPLY_OPERATION_ID`).
발급 자체가 또 하나의 승인 단계일 수 있다 — 확인 후 사용자에게 보고.

적용 후 할 일: 감사 재실행으로 줄어든 수치 확인 → `tools/ops/drift_baseline.json` 의
`erp_flat.drift` 를 새 값으로 **낮춤** → deploy push.

---

## T10. 긴급 — ERP 주문 화면 '첫 AS 접수' 입구 복구 (사용자 제보, 계획 밖)

- 상태: **DONE — production 반영 완료**(`cf6146df5`, PR #302). 커밋 `5175f4296`.
- 제보: "드롭다운 > AS 접수 메뉴가 사라졌어".

### 원인 — 회귀가 아니라 미봉된 절반

AS 접수 입구는 원래 본공정 드롭다운의 `AS_RECEIVED` 옵션이었고, 저장 시
`erp-order-shared.js:2757` 이 `nextStage === 'AS_RECEIVED'` 를 보고 AS 접수 모달을 열었다.
**2026-09-04 `308366961`** 이 그 옵션 3개(`AS_RECEIVED`·`AS`·`AS_COMPLETED`)를 지웠다 — 값을
실제로 쓰면 `workflow.stage` 가 덮여 도면·생산·시공 큐에서 주문이 영구 이탈했기 때문이다
(운영 실측 62건). 판단은 옳았다.

그런데 **그 옵션에만 의존하던 트리거가 그대로 남았다.** 옵션이 없으니 `nextStage` 가
`AS_RECEIVED` 가 될 수 없고, 모달은 영영 안 열린다. 남은 입구는 시공 화면
(`openAsAcceptModal`)과 AS 대시보드 완료 탭 재접수 딥링크(`as_reintake=1`)뿐 — 사무실에서
주문을 보며 AS 를 접수하던 동선이 사라졌다.

### 데이터 축은 어긋나 있지 않다 (읽기 전용 실측)

`erp_as_status_label` 은 레거시 `orders.status` 로 판정한다(보고서 R1 축). 그래서 먼저
`as_axis_status` 는 있는데 `status` 가 AS 계열이 아닌 주문을 셌다:

```
staging   : AS 축 있는 주문 482 중 드롭다운에 AS 안 뜨는 것 0
production: AS 축 있는 주문 641 중 드롭다운에 AS 안 뜨는 것 0
```

즉 이번 증상은 **데이터가 아니라 배선**이다. (표시 축이 파생 사본을 본다는 구조 문제는
그대로 남아 있다 — 후속 F-17.)

### 고친 방법

옵션을 되돌리지 않는다(되돌리면 62건 사고로 회귀). `workflow.stage` 를 건드리지 않는
버튼으로 같은 모달을 연다. 기존 `AS 접수 수정`(AS 열림) 버튼과 `elif` 로 갈라 **둘 중 하나만**
뜬다. PC·모바일 양쪽. `?v` 핀 `20260904c → 20260907a`(SW staticCacheFirst).

### 계약 10건

버튼 존재(PC·모바일) · 재접수와 상호배타 · 저장된 주문 + AS 미개시일 때만 노출 · 버튼이 실제로
모달을 연다 · 입구가 stage 를 건드리지 않는다 · **음성 대조군: 드롭다운에 AS 옵션이 되살아나지
않았는지** · `?v` 핀 전진.

```
$ PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_erp_as_intake_entry.py -q
10 passed in 0.04s

$ 회귀(ERP·AS·JS 문법 스위트)
82 passed
```

핀 리터럴을 못 박은 테스트 1곳(`test_erp_order_shared_form_scripts.py:73`)도 같이 갱신했다 —
보고서 R4 가 지적한 "핀 리터럴 52파일 90곳" 세금의 실사례다.

### 스테이징 실화면 검증 (총괄 직접, 양성+음성)

```
[AS 없는 주문 #4491]  AS접수버튼=True   접수수정버튼=False  드롭다운AS옵션=False  핀=20260907a
[AS 열린 주문 #4389]  AS접수버튼=False  접수수정버튼=True   드롭다운AS옵션=False  핀=20260907a
```

### production 승격 (사용자 지시 "빨리 production 푸쉬")

승격 도구가 "production 에 없는 의존 8건"(그중 `30836696` = AS 옵션 제거 커밋)으로 먼저 막았다.
**그 경고를 우회하기 전에 production 파일을 직접 열어 확인했다** — AS 옵션 제거·
`data-erp-as-active` 배선·핀 `20260904c`·테스트 리터럴이 전부 동일했다. 내용은 이미 들어가
있고 cherry-pick 으로 SHA 만 재작성된 오탐이다(메모리 `project_git_stray_production_refs_trap`
와 같은 축). 근거 확인 뒤 `--allow-incomplete`.

- PR #302 검사 4종 전부 SUCCESS → 머지. production `2fce6197c → cf6146df5`.
- **production 머지 커밋 자체에는 워크플로 런이 0건**이다. `ci_watch` 는 이걸 "런 없음 → green
  취급" 이라고 말하지만 그건 green 의 증거가 아니라 판정 불가다. 근거는 PR 검사 4종이다.
- 배포 확인: `/healthz` → `cf6146df5`, 운영 JS 무인증 조회에서 `data-erp-as-receive-open` 1건 ·
  `erpAsReceiveBound` 2건(HTTP 200).
- 승격 범위는 **AS 수정 1건만**. 나머지 12건은 deploy 에만 있다(특히 로그인 한도·잠금은
  실사용자 동작 변화라 별도 판단).

### 드롭다운 안 'AS 접수' 항목 — 사용자 결정으로 **안 넣는다**(2026-09-07)

사용자가 화면에서 버튼을 확인한 뒤 "그냥 지금 구현된 방식으로 접수하겠다" 로 확정했다.
저장 안 되는 신호값 옵션(고르면 모달 열고 즉시 원복) 설계를 제안했으나 착수 전 중단했다.
되살릴 일이 생기면 그 설계가 출발점이고, 옵션 값을 **실제로 저장하는** 옛 방식으로는 돌아가면
안 된다(62건 큐 이탈).

---

## T11. 매일 드리프트 검사 운영 반영 + 첫 실측 (사용자 지시 "올려서 돌리기")

- 상태: **DONE**. PR #303 머지 → production. 수동 dispatch 1회로 실측 확보.

### 승격 중 충돌 1건 — 사용자 확인 후 처리

`tests/contracts/runtime/layer_dependency_baseline.json` 이 `DU`(운영엔 없는데 이 커밋이 수정)로
충돌했다. 그 파일은 production 에 올리지 않은 T1 래칫 커밋이 만든 것이고 **그것을 읽는 테스트도
production 에 없다**. 사용자 결정("그 파일만 빼기")대로 그 변경만 제외했다 — 임의 병합이 아니다.
승격 worktree 에서 직접 확인: `APP_OK` · 관련 계약 **207 passed** · 래칫 테스트 부재 확인.

### 운영 첫 실행 (run 34072367845)

첫 dispatch 는 **404 로 실패**했다 — 머지 직후라 운영에 엔드포인트가 아직 없었다. 도구가 거짓
초록 대신 `exit 3` 으로 죽은 것은 설계대로다(무음 실패 없음). 배포 확인(엔드포인트 401) 후 재실행:

```
판정: 🟢 순증 없음 (총 924건 / 소요 1072ms / 절단 False)
| AS 축 투영(as_axis_status) |  659 |   0 |    0 |    0 | 투영 누락 0 · legacy 전용 0 |
| ERP flat 컬럼             | 3007 | 924 | 1750 | -826 | SAFE 0 · AMBIGUOUS 924 · CLEAN 2083 |
```

**SAFE 825 → 0.** 같은 날 백필이 고친 것이 게이트 숫자로 확인됐다. 소요 1072ms 라 gunicorn
`--timeout 120` 대비 여유가 크다(F-13 의 elapsed_ms 실측 완료).

기준선을 규칙대로 **1750 → 924** 로 낮췄다(커밋 `93f5ed40c` 계열). 안 낮추면 래칫이 826건만큼
헐거워진 채 남는다. 남은 924는 전부 `PAYMENT_AMOUNT_DRIFT` — 자동으로 못 고친다.

## T12. 좌표 스윕 루프 하트비트·Sentry (후속 F-5 첫 건)

- 상태: **DONE(deploy)**. `run_geocode_sweep.py` + 계약 5건.
- 이 스크립트가 2026-02 워커 offline 사고의 그 스크립트다. `app.py` 를 안 거쳐 `init_sentry`
  호출처가 없었고(예외가 아무 데도 안 감), 하트비트도 없어 멎어도 표에 안 나타났다.
- 라운드가 터져도 하트비트를 남긴다(`outcome` 을 ok/round_failed 로 갈라 "죽었다" 와 "이번
  라운드만 실패" 를 구분). 하트비트 실패는 스윕을 안 막되 warning + Sentry 로 남긴다.
- **변이 검증이 내 테스트의 허점을 잡았다**: 경고 로그를 지우는 변이가 통과했는데, Sentry
  메시지에도 'heartbeat' 가 들어 있어 단언 하나가 두 신호를 같이 세고 있었다. 둘을 갈라
  다시 재니 변이 2종 다 red.

```
[heartbeat call removed] exit=1  3 failed, 2 passed
[warning silenced]       exit=1  1 failed, 4 passed
restore ok: True
```

## 세션 마감 상태 (2026-09-07)

| | |
|---|---|
| production | `f33f1170b` — AS 접수 입구(PR #302) · 드리프트 감사+래칫(PR #303) |
| deploy | `017153194` — CI 전 워크플로 green |
| 운영 데이터 | flat 백필 825건, 게이트 실측 `SAFE 0` |
| 매일 검사 | 03:20 KST cron 작동, 기준선 924 순증 시에만 실패 |

**타 세션과 4회 경합**했다(deploy 가 5커밋 전진). 매번 내 커밋만 rebase 하고 `APP_OK`+계약
재확인 후 push 했다. 남의 커밋은 건드리지 않았다.

**남은 후속 16건** — 큰 것: 운영 AMBIGUOUS 924건(결제금액, 사람이 봐야 함) · 스테이징
`SENTRY_DSN` 미설정 · 나머지 루프 3개 + `rq worker` 본체 하트비트 · 로그인 잠금 승격 판단 ·
`check_sidefx_readiness` 가 새 kind 2종(`NAVER_AUTO_DISPATCH`·`GEOCODE_SWEEP`)을 못 읽음.


---

# 후속 세션 2 (2026-09-08)

시작 시 실측 — 지시 기준값과 어긋나 병기한다(둘 다 조상으로 포함, 되감김 아님):

```
$ git log --oneline -1 && git rev-parse origin/deploy origin/production
d37853ae4 feat(naver): 취소·반품 알림과 유령 목록이 실측 전/후를 말한다
b69afc31b16a04745e55f9d5ac264869019a9e34   (지시 기준 ba3f282f5 → 10커밋 전진)
d2e1d263a4285bc42bdee1c155233facc6d1d1f8   (지시 기준 e3a181bf9 → 11커밋 전진)
```

- 직전 세션 worktree `/c/tmp/foms-s-now0907` 는 이미 없다. 새 worktree `/c/tmp/foms-s-f9kinds`
  (`session/f9kinds`, base `origin/deploy b69afc31b`).
- 메인 트리의 미추적 원장 사본(179줄·전부 PENDING)은 **낡은 초기본**이다. 정본은 커밋된
  1192줄본(`ba3f282f5`). 이번 갱신은 정본에 이어 붙였다.

## T13. F-9 — readiness 가 outbox 밖 loop kind 도 읽는다

- 상태: **DONE(로컬 검증)**
- 근본 원인: 판정부 `evaluate_readiness` 가 `WORKER_KINDS` 3종을 **고정 순회**했다
  (`foms/services/sidefx_worker.py`). CLI 는 101줄 껍데기라 CLI 를 고쳐도 안 됐다 —
  하트비트를 쓰는 kind 가 늘어도 읽는 쪽 목록은 코드에 못 박혀 있었다.
- 고친 방법:
  - kind 등록부 `WORKER_KIND_SPECS`(kind·신선도 예산·scan lag 한도·outbox 소속) 신설.
    `NAVER_AUTO_DISPATCH`·`GEOCODE_SWEEP` 등재(예산 180초 = tick 60초 x 3틱).
  - `evaluate_readiness(..., kinds=None)` — 기본은 outbox 3종 그대로(release gate 의미 불변),
    고른 kind 만 판정. 미등록 kind·빈 선택은 `ValueError`(빈 판정은 무조건 ready = fail-open).
  - PENDING lag·DEAD 는 outbox kind 를 하나라도 골랐을 때만 센다.
  - CLI `--kinds` 추가(파싱 실패·미등록 kind = exit 2, fail-closed).
  - 쓰는 쪽 2개 러너가 리터럴 대신 등록부 상수를 쓴다(이름 드리프트가 F-9 의 형태였다).
- 계약: `tests/domains/test_sidefx_readiness_kinds.py` 13건(PG 불필요, 본 레인에서 돈다).
- 남은 것: **자동 조회는 아직 없다.** 운영 DB 자격증명이 GitHub 에 없어(드리프트 감사가
  admin HTTP 를 쓰는 이유) 매일 자동 판정은 admin 엔드포인트가 있어야 한다 → 후속 F-17.

### 검증 출력

```
$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
[AUTO-INIT] ERP flat-column readiness verified.
APP_OK

$ python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py tests/domains/test_sidefx_readiness_kinds.py -q
20 passed in 0.44s

$ python -m pytest tests/postgres/test_sidefx_worker.py -q -k "readiness and not collect"   # 기존 판정 계약 불변
3 passed, 8 deselected in 0.06s

$ python tools/ops/check_sidefx_readiness.py --help | tail -4
  --kinds KINDS         판정할 worker_kind 쉼표 목록(생략 시 outbox 3종
                        DELIVERY,EXPIRY_SCAN,RETENTION). 등록된 kind: DELIVERY,EX
                        PIRY_SCAN,GEOCODE_SWEEP,NAVER_AUTO_DISPATCH,RETENTION.
```

### 변이 검증 10종 — 방어를 하나씩 없애 red 확인

```
MUT1  kinds 인자 무시(3종 고정 복귀)          4 failed, 7 passed
MUT2  kind별 예산 무시(전부 30초)             2 failed, 9 passed
MUT3  outbox 범위 가드 제거                   1 failed, 10 passed
MUT4  미등록 kind 거부 제거                   1 failed, 10 passed
MUT5  비-scan kind 에도 scan lag 요구         4 failed, 7 passed
MUT6  러너가 리터럴로 되돌아감                1 failed, 10 passed
MUT7  PENDING lag·DEAD 검사 무력화            1 failed, 10 passed   (음성 대조군이 죽는다)
MUT8  새 kind 등록부에서 제거                 5 failed, 6 passed
MUT9  기본 판정에 새 kind 밀어넣기            1 failed, 10 passed
MUT10 빈 선택 방어 제거                       1 failed, 12 passed
복원 후: 13 passed
```

단언 겹침 점검: 모든 테스트가 **자기만 죽는 변이**를 하나씩 갖는다 —
`test_new_kind_has_no_scan_lag_check`=MUT5, `test_..._missing_heartbeat`=MUT1,
`test_non_outbox_selection_skips`=MUT3, `test_unknown_kind`=MUT4, `test_emitter_*`=MUT6,
`test_outbox_selection_still_counts`=MUT7(음성 대조군), `test_default_selection`=MUT9,
`test_empty_selection`=MUT10. 겹쳐서 한쪽을 지워도 통과하는 단언은 없다.

## 후속 추가

| # | 항목 | 필요한 것 |
|---|---|---|
| F-17 | 루프 하트비트 자동 조회 경로 없음 | `--kinds` 판정을 사람이 불러야만 돈다. 매일 자동으로 보려면 드리프트 감사처럼 admin HTTP 엔드포인트 + 워크플로가 필요하다(운영 DB 자격증명은 GitHub 에 두지 않기로 한 결정 때문) |

## T14. F-5/F-6 — 남은 루프 3개 + 큐 소비 본체 하트비트

- 상태: **DONE(로컬 검증)**
- 근본 원인: `start.sh` 가 띄우는 루프 5개 중 2개만 하트비트가 있었고, 마지막 줄
  `exec rq worker` 는 자기 생존을 FOMS 감시 표에 **한 줄도** 남기지 않았다(Redis 쪽 rq
  하트비트는 rq 대시보드 전용이다). 큐 소비가 멎어도 표만 봐서는 알 수 없었다.
- 고친 방법:
  - 공통 헬퍼 `foms/services/loop_heartbeat.py` — `emit_heartbeat`(실패해도 본 작업을 안
    막되 warning + Sentry) · `capture_exception`. 러너마다 같은 25줄을 베끼던 것을 한 곳으로.
  - 루프 3개 배선: escalation · 네이버 수집 · 정산 동기화. **스윕이 터진 tick 도** 하트비트를
    남긴다(`outcome=sweep_failed`) — "죽었다" 와 "이번 스윕만 실패" 를 가른다. 정산은 창 밖
    tick 도 남긴다(안 그러면 하루 대부분이 죽은 것처럼 보인다).
  - F-6: `tools/ops/run_rq_worker.py` 신설 — `rq.Worker.heartbeat()` 를 감싸 같은 자리에서
    `RQ_WORKER` 행을 갱신한다. 별도 스레드를 안 쓴 이유: 스레드는 rq 루프가 멎어도 계속
    뛰어 "살아 있다" 는 거짓 신호를 준다. `start.sh` exec 줄을 이 러너로 교체.
    DB 쓰기는 60초로 조인다(rq 는 잡마다 heartbeat 를 부른다).
  - 등록부에 kind 4종 추가: NOTIFICATION_ESCALATION(180초)·NAVER_ORDER_SYNC(900초, 간격
    300초 x 3)·NAVER_SETTLE_SYNC(180초)·RQ_WORKER(900초, rq 유휴 주기 405초 x 2).
  - `--max-heartbeat-age` 를 주면 대상 kind 전부에 적용(간격을 env 로 늘렸을 때의 탈출구).
- 계약: `tests/domains/test_loop_heartbeat_wiring.py` 19건 + readiness 14건.
  **핵심 방어**: `start.sh` 의 모든 `--loop` 러너가 등록부 상수로 kind 를 선언하는지 본다 —
  하트비트 없는 새 루프를 배선하면 red(F-9 이 정확히 이 드리프트였다).
- 실측 비용: 러너 import 1.87초(맨 rq CLI 0.32초). 워커는 어차피 첫 잡에서 tasks(2.02초)를
  물기 때문에 배포당 1회의 +1.5초다.

### 검증 출력

```
$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
APP_OK

$ python -m pytest tests/domains/test_loop_heartbeat_wiring.py tests/domains/test_sidefx_readiness_kinds.py \
    tests/domains/test_worker_loop_heartbeat.py tests/domains/test_geocode_sweep_heartbeat.py \
    tests/domains/test_geocode_sweep.py tests/contracts/runtime/test_ptc_physical_exactness.py \
    tests/contracts/runtime/test_dockerfile_deploy_contract.py -q
72 passed, 1 warning in 17.64s

$ python -m pytest tests/domains/test_table_version_counter.py tests/domains/test_jobs_queue_redis_lane.py -q
21 passed, 5 skipped in 14.89s
```

### 변이 검증 11종 — 전부 red, 각각 자기만 죽는 테스트를 갖는다

```
MUT1  escalation 하트비트 제거              1 failed, 18 passed
MUT2  수집 루프 하트비트 제거               1 failed, 18 passed
MUT3  정산 루프가 창 안에서만 뛴다          1 failed, 18 passed
MUT4  헬퍼가 실패를 조용히 삼킨다           1 failed, 18 passed
MUT5  start.sh 가 맨 rq worker 로 되돌아감  1 failed, 18 passed
MUT6  rq 하트비트 조임 제거                 1 failed, 18 passed
MUT7  기록 실패해도 조임 시계 전진          1 failed, 18 passed
MUT8  mixin 을 Worker 뒤로                  1 failed, 18 passed
MUT9  escalation kind 등록부에서 빠짐       1 failed, 18 passed
MUT10 metadata 에 고객 이름 추가            1 failed, 18 passed
MUT11 명시 --max-heartbeat-age 무시         1 failed, 13 passed (readiness 쪽)
복원 후: 19 passed / 14 passed
```

### 남은 것 (사용자 판단)

- `start.sh` exec 줄이 바뀌었다 — **운영 워커 기동 경로 변경**이다. deploy(스테이징)에서
  워커가 실제로 뜨는지 확인한 뒤에 승격 판단이 필요하다.
- 하트비트는 여전히 **사람이 불러야 읽힌다**(F-17). SENTRY_DSN 미설정이라 Sentry 경로도
  no-op 이다(F-12).

## T15. F-7 — SIDEFX outbox 워커의 잡은 예외가 Sentry 로 간다

- 상태: **DONE(로컬 검증)**
- 근본 원인: `run_domain_side_effect_outbox.py` 는 `app.py` 를 안 거친다(별도 Railway
  service). `init_sentry` 호출처가 web 한 곳뿐이라 이 프로세스의 예외는 `_safe` 가 로그로만
  찍고 **아무 데도 가지 않았다**. 하트비트 3종은 있었지만 "왜 실패했는지" 는 없었다.
- 고친 방법: 공통 헬퍼에 `init_sentry_once()` 추가(DSN 부재면 `sentry_sdk` 도 `foms.platform`
  도 import 하지 않는다 — 그 `__init__` 이 app_factory 를 통째로 끌어온다). `main()` 이
  부르고, `_safe` 는 로그 뒤 `capture_exception()` 을 부른다.
- 계약 6건 + 변이 5종(MUT12~16) 전부 red.

### 이번에 실제로 물린 함정 — 로컬 초록·CI 빨강 (F-11 의 실사례)

`pre_push_smoke` 23타깃에 계층 래칫이 없어서 스모크는 초록인데 CI 가 빨갰다.

```
FAILED tests/contracts/runtime/test_layer_dependency_ratchet.py::test_no_new_lazy_foms_imports
assert not ['foms/services/loop_heartbeat.py::foms.services.sidefx_worker']
```

- `emit_heartbeat` 안의 지연 import 는 **필요 없는 것**이라 최상단으로 올렸다(테스트도
  `loop_heartbeat.upsert_heartbeat` 를 패치하도록 고쳤다).
- `init_sentry_once` 안의 `foms.platform.sentry_setup` 지연 import 는 **방어 그 자체**라
  기준선에 올렸다(`tasks.py` 의 같은 항목과 나란히). 재생성 결과 새 항목은 딱 1줄.
- 재발 방지: `pre_push_smoke` 서브셋에 계층 래칫 + 닫힌집합(ptc) 2종을 등재했다.

### 검증 출력

```
$ python -m pytest tests/contracts/runtime/test_layer_dependency_ratchet.py \
    tests/contracts/runtime/test_ptc_physical_exactness.py \
    tests/domains/test_loop_heartbeat_wiring.py tests/domains/test_sidefx_readiness_kinds.py \
    tests/domains/test_worker_loop_heartbeat.py -q
58 passed, 1 warning in 17.00s

$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
APP_OK
```

## 후속 세션 2 마감 상태 (2026-09-08)

| | |
|---|---|
| deploy | `7d28a2892` — 전 워크플로 green (Harness CI · FOMS PostgreSQL Lane · perf-gate · FOMS CI) |
| production | `d2e1d263a` — 이번 세션에서 건드리지 않았다 |
| 처리한 후속 | F-9 · F-5 · F-6 · F-7 (+ F-11 실사례 대응: 스모크 서브셋에 계약 2종 등재) |
| 계약 | readiness 14건 + 배선 25건, 변이 16종 전부 red 확인 |

커밋 4개: `328055bf0`(F-9) · `50107e891`(F-5/F-6) · `7d28a2892`(F-7·래칫·스모크) 및 인벤토리
재생성. `50107e891` 은 계층 래칫 위반으로 FOMS CI 가 한 번 빨갰고 다음 커밋에서 고쳤다.

### 사용자 판단이 필요한 것 (그대로 남아 있다)

1. **`start.sh` exec 줄이 바뀌었다** — 운영 워커 기동 경로다. 스테이징에서 워커가 실제로
   뜨고 `RQ_WORKER` 하트비트 행이 생기는지 확인하기 전에는 production 승격 금지.
2. `SENTRY_DSN` 미설정(F-12) — 이번에 붙인 Sentry 배선이 스테이징·운영에서 전부 no-op 이다.
3. 하트비트 자동 조회 경로 없음(F-17) — 사람이 `--kinds` 로 불러야만 읽힌다.
4. 로그인 한도·잠금(T6) production 승격 · 운영 AMBIGUOUS 924건 · F-1 · F-4 — 미결 그대로.

## T16. 스테이징 실측 — 그리고 예산 설계 결함 1건

스테이징(FOMS-DEV worker) 실측으로 배선을 확인했고, 그 자리에서 설계 결함을 하나 찾았다.

### 워커 기동 (railway logs, 2026-09-08)

```
[wait-redis] ready after 1 attempt(s)
[run-rq-worker] started (queues=default heartbeat_interval=60s)
01:16:32 Worker ...: started with PID 1, version 2.12.0
01:16:32 *** Listening on default...
[naver-auto-dispatch] started (at=16:50 window=10m tick=60s)
[naver-sync-loop] started (interval=1800s)
[escalation-loop] started (interval=60s)
[naver-settle-sync] started (at=05:30 window=10m tick=60s monthly_backfill=on)
```

바뀐 `start.sh` 로 워커가 정상 기동한다. 운영 rq 는 2.12.0(로컬 2.5.0)인데 `heartbeat()`
override 가 `*args/**kwargs` 라 그대로 물린다.

### 하트비트 표 (스테이징 DB 직접 질의)

```
DELIVERY                 age=     5s
EXPIRY_SCAN              age=     5s
RETENTION                age=     5s
NAVER_AUTO_DISPATCH      age=     3s  in_window=False
NAVER_ORDER_SYNC         age=   362s  outcome=ok
NAVER_SETTLE_SYNC        age=     3s  ran=False
NOTIFICATION_ESCALATION  age=     3s  outcome=ok
RQ_WORKER                age=   369s  state=STARTED queues=default
총 8 행
```

`RQ_WORKER` age 369초는 rq 유휴 주기(405초)와 맞다 — F-6 이 실환경에서 작동한다.
`GEOCODE_SWEEP` 이 없는 이유는 스테이징에 그 루프 스위치가 없어서다(정상).

### 찾은 결함 — 등록부 고정 예산이 env 를 못 따라간다

스테이징 `FOMS_NAVER_SYNC_INTERVAL_SECONDS=1800` 인데 등록부 예산은 900초였다. 지금은
`READY` 로 나오지만 다음 tick 전에 반드시 900초를 넘겨 **살아 있는 루프를 죽었다고 판정**한다.
`--max-heartbeat-age` 로 덮는 건 운영자가 매번 기억해야 하는 우회다.

근본 수정: **루프가 자기 tick 간격을 하트비트에 신고**하고(`interval_seconds`), 판정은
`max(등록부 값, 신고 x 3)` 을 쓴다. 신고가 없거나 말이 안 되면(0·음수·문자열) 등록부 값으로
떨어진다 — 신고 축이 판정을 무력화하지 못한다. rq 는 자기 `dequeue_timeout`(405초)을 신고한다.

- 계약 추가 6건(신고가 예산을 정한다 / 신고가 예산을 줄이지 못한다 / 신고 없으면 등록부 /
  말 안 되는 신고 5종 / 루프가 실제 간격을 신고한다 / rq 가 주기를 신고한다).
- 변이 MUT17~21 전부 red.

```
MUT17 신고 간격 무시                  1 failed, 48 passed
MUT18 신고가 예산을 줄일 수 있게      1 failed, 48 passed
MUT19 말 안 되는 신고 허용            2 failed, 47 passed
MUT20 루프가 상수를 신고              1 failed, 48 passed
MUT21 rq 가 주기를 신고 안 함         1 failed, 48 passed
복원 후: 49 passed
```

### 확인된 미결

- 스테이징 `SENTRY_DSN` **미설정 재확인**(F-12) — 이번 Sentry 배선은 스테이징에서 no-op 이다.

### 스테이징 실측 — 수정 전 예산이면 실제로 오판했다 (양성 + 음성)

재배포 뒤 신고 값이 실제로 실린다:

```
DELIVERY                 age=     4s  신고간격=None
EXPIRY_SCAN              age=     4s  신고간격=None
RETENTION                age=     4s  신고간격=None
NAVER_AUTO_DISPATCH      age=    49s  신고간격=None   (러너 미변경 — 등록부 180초)
NAVER_ORDER_SYNC         age=   288s  신고간격=1800   → 예산 5400초
NAVER_SETTLE_SYNC        age=    49s  신고간격=60     → 예산 180초
NOTIFICATION_ESCALATION  age=    48s  신고간격=60     → 예산 180초
RQ_WORKER                age=    69s  신고간격=405    → 예산 1215초
```

수집 루프 나이가 옛 고정 예산(900초)을 넘긴 시점에 같은 표를 두 번 판정했다:

```
== NAVER_ORDER_SYNC age=1003s (신고 1800초 x3 = 예산 5400초)
-- 신고 기반 판정(기본):
[sidefx-readiness] READY failures=0
-- 옛 고정 예산(900초)을 강제했을 때:
[sidefx-readiness] NOT-READY failures=1
  - {'check': 'heartbeat_fresh', 'kind': 'NAVER_ORDER_SYNC', 'detail': 1006, 'limit': 900}
```

**음성 대조군이 실제로 빨갛다** — 고치기 전 예산이었다면 살아 있는 수집 루프를 죽었다고
판정했을 것이 실측으로 증명됐다. 신고 축이 그 오판을 없앤다.

미신고 2종(`NAVER_AUTO_DISPATCH`·`GEOCODE_SWEEP`)은 러너를 안 건드려 등록부 값(180초)으로
판정된다. 둘 다 `start.sh` 가 tick/interval 을 60초로 고정해 넘겨 지금은 맞지만, 간격이
env 로 열리면 같은 함정에 빠진다 → 후속 F-18.

| # | 항목 | 필요한 것 |
|---|---|---|
| F-18 | `NAVER_AUTO_DISPATCH`·`GEOCODE_SWEEP` 는 tick 간격을 신고하지 않는다 | **처리 완료(아래 T17)** — 두 러너도 신고한다 |

## T17. F-18 — 남은 러너 2종도 자기 간격을 신고한다

- 상태: **DONE(로컬 검증)**
- 남겨두면 같은 함정이 그대로다: 지금은 `start.sh` 가 60초로 고정해 넘겨 등록부 값과 맞지만,
  간격을 env 로 여는 순간(수집 루프가 실제로 그랬다) 살아 있는 루프를 죽었다고 판정한다.
- `run_naver_auto_dispatch.py` 는 `args.tick`, `run_geocode_sweep.py` 는 라운드 간격을 싣는다.
  기존 계약(정확 집합 단언·스텁 시그니처)도 함께 갱신했다.
- 변이 2종:

```
MUT22 좌표 스윕이 간격을 안 넘김    1 failed, 13 passed
MUT23 자동 발송이 상수를 신고        1 failed, 13 passed
복원 후: 14 passed
```

```
$ python -m pytest tests/domains/test_geocode_sweep_heartbeat.py \
    tests/domains/test_worker_loop_heartbeat.py tests/domains/test_loop_heartbeat_wiring.py \
    tests/domains/test_sidefx_readiness_kinds.py -q
63 passed, 1 warning in 8.97s
```

### T17 스테이징 재확인 (재배포 후)

```
DELIVERY                 age=     8s  신고간격=None   (outbox 워커 — 하트비트 주기 10초 고정)
EXPIRY_SCAN              age=     8s  신고간격=None
RETENTION                age=     8s  신고간격=None
NAVER_AUTO_DISPATCH      age=     5s  신고간격=60     ← T17 로 새로 신고
NAVER_ORDER_SYNC         age=   245s  신고간격=1800
NAVER_SETTLE_SYNC        age=     5s  신고간격=60
NOTIFICATION_ESCALATION  age=     5s  신고간격=60
RQ_WORKER                age=   251s  신고간격=405
```

`GEOCODE_SWEEP` 은 스테이징에 루프 스위치가 없어 행이 없다(정상). outbox 3종은 하트비트
주기가 코드 상수(10초)로 고정이라 신고 축이 필요 없다 — 등록부 30초가 정본이다.

## 후속 세션 2 최종 마감 (2026-09-08)

| | |
|---|---|
| deploy | `c73c00c61` — 전 워크플로 green |
| production | 이번 세션에서 건드리지 않았다 |
| 처리 | F-9 · F-5 · F-6 · F-7 · F-18 (+ F-11 실사례 대응) |
| 계약 | 63건, 변이 23종 전부 red 확인 |
| 실측 | 스테이징 워커 기동·하트비트 8행·예산 오판 양성/음성 대조 |

커밋: `328055bf0`(F-9) · `50107e891`(F-5/F-6) · `7d28a2892`(F-7·래칫·스모크) ·
`1288e99b2`(간격 신고) · `c73c00c61`(F-18) + 인벤토리·원장 커밋.

### 남은 사용자 판단 (그대로)

1. `start.sh` exec 줄 변경의 production 승격 — 스테이징에서는 워커가 정상 기동했다.
2. `SENTRY_DSN` 미설정(F-12) — 이번 Sentry 배선이 스테이징·운영에서 no-op.
3. 하트비트 자동 조회 경로 없음(F-17) — 사람이 `--kinds` 로 불러야 읽힌다.
4. 로그인 한도·잠금(T6) 승격 · 운영 AMBIGUOUS 924건 · F-1 · F-4.

## T18. 워커 감시 축 production 승격 (사용자 지시 "지금 바로 머지")

- 상태: **DONE(운영 반영·실측 확인)**. production `5f0aecb58` (PR #310).
- 승격 방식: 이번 세션 커밋 6개 + **토대가 되는 직전 세션 커밋 2개**(41df2360 루프 하트비트·
  51b14d4c 좌표 스윕)를 cherry-pick 했다. 내 커밋만으로는 앞뒤가 안 맞는다 —
  `promote_completeness` 가 INCOMPLETE(missing=60)로 그것을 먼저 말했다.
- 충돌 3건과 처리 근거:
  - `tests/contracts/runtime/layer_dependency_baseline.json` — 운영에 **계약 테스트 자체가
    없다**(래칫 커밋 2b090b565 미승격). 그 테스트만 읽는 파일이라 없는 상태로 뒀다.
  - 진행 원장 문서 — 세션 기록이라 운영에 불필요. 없는 상태로 뒀다.
  - `docs/harness/foms_failopen_inventory.json` — 타 세션 변경 44건이 섞여 있어 deploy 쪽
    커밋을 안 가져오고 **승격 브랜치 코드로 재생성**했다.
  - 코드 파일 충돌은 0건.

### 승격 브랜치 검증

```
$ PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
APP_OK
$ python -m pytest (하트비트·준비 판정·인벤토리 계약)
76 passed
$ scripts/ops/pre_push_smoke.ps1
648 passed → PASSED (22타깃 — 운영에 없는 래칫 타깃은 자동 제외)
PR #310 checks: test SUCCESS · pg-lane SUCCESS · harness SUCCESS · perf-gate SUCCESS
```

### 운영 실측 (머지 후)

```
[run-rq-worker] started (queues=default heartbeat_interval=60s)
04:29:52 Worker ...: started with PID 1, version 2.12.0
04:29:52 *** Listening on default...
[geocode-sweep] started (interval=60s batch=50 ...)
[naver-auto-dispatch] started (at=16:50 window=10m tick=60s)
[escalation-loop] started (interval=60s)
[naver-sync-loop] started (interval=1800s)
[naver-settle-sync] started (at=05:30 window=10m tick=60s monthly_backfill=on)
```

하트비트 표(운영, 읽기 전용 질의) — **9종 전부**:

```
DELIVERY                 age=  1s  신고간격=None
EXPIRY_SCAN              age=  1s  신고간격=None
RETENTION                age=  1s  신고간격=None
GEOCODE_SWEEP            age= 42s  신고간격=60     ← 운영에만 있는 루프
NAVER_AUTO_DISPATCH      age= 38s  신고간격=60
NAVER_ORDER_SYNC         age= 37s  신고간격=1800
NAVER_SETTLE_SYNC        age= 38s  신고간격=60
NOTIFICATION_ESCALATION  age= 38s  신고간격=60
RQ_WORKER                age= 44s  신고간격=405
```

```
$ check_sidefx_readiness.py --kinds RQ_WORKER,GEOCODE_SWEEP,NAVER_*,NOTIFICATION_ESCALATION
[sidefx-readiness] READY failures=0
```

## T19. 승격한 도구가 곧바로 운영 결함 하나를 찾았다 (F-19)

기본 판정(outbox 3종)을 운영에 돌리자 처음으로 빨간불이 켜졌다:

```
$ check_sidefx_readiness.py
[sidefx-readiness] NOT-READY failures=1
  - {'check': 'dead_count', 'detail': 1344, 'limit': 0}
```

```
outbox 상태별: DEAD 1344 · DONE 924 · PENDING 116

DEAD 유형별:
  CHANNEL_PUSH_RECORDED  1190건  2026-08-03 ~ 2026-09-01   NoHandlerError
  STAGE_NOTIFICATION      154건  2026-08-03 ~ 2026-09-08   NoHandlerError  ← 계속 쌓인다
```

- `CHANNEL_PUSH_RECORDED` 는 09-01 에 멈췄다(SIDEFX-RECORDONLY-01 handler 등록). 과거 잔재다.
- `STAGE_NOTIFICATION` 은 **오늘도 쌓인다**(최근 2일 DEAD 18 · PENDING 1). 등록된 handler 는
  STORAGE_DELETE·GEOCODE·ALIMTALK_SEND·CHANNEL_PUSH_RECORDED 4종뿐이고 이 타입은 없다.
  생산자는 전이 9곳(`order_transition_service.py:409` 등)이다.
- **아직 모르는 것**: 이 행이 CHANNEL_PUSH_RECORDED 처럼 기록·dedupe 전용인지, 아니면 정말
  배달돼야 하는데 아무도 안 하는지. 최근 2일 실제 알림은 17건 생성됐지만(NAVER_ORDER_CLAIMED
  8·SHIPMENT_ORDER_CHANGED 5·ERP_ORDER_CHANGED 3·NAVER_AUTO_DISPATCH 1) 그것이 전이 알림을
  덮는지는 추적하지 않았다. **추측하지 않고 사용자 판단을 기다린다.**

| # | 항목 | 필요한 것 |
|---|---|---|
| F-19 | 운영 outbox DEAD 1,344건 · `STAGE_NOTIFICATION` 154건이 계속 증가 | 전이 알림이 실제로 유실되는지 추적 → 기록 전용이면 handler 등재, 배달 필요면 handler 구현. 어느 쪽이든 **사용자 판단** |

## T20. F-19 조치 — 단계 전이 행이 DEAD 로 쌓이지 않게 (사용자 결정 A)

- 상태: **DONE(로컬 검증)**. deploy 반영 예정.
- 먼저 **유실인지부터 확인했다(사용자 지시)**. 증거 3개가 같은 결론이다:
  1. 운영 `notifications` 에 단계 전이 유형은 **전 기간 0건**(`ILIKE '%STAGE%'`).
  2. 코드에 `STAGE_NOTIFICATION` 소비자가 없다. 단계 변경이 화면에 보이는 경로는 알림이
     아니라 읽기 모델(`production_change_alerts` 가 `OrderEvent` 를 읽는다)이다.
  3. 2026-09-01 원장이 이미 같은 판정을 남겼다 — "기록 전용이 아니라 소비자 미구현,
     회귀가 아니다"(그때 118행, 오늘 154행).
  → **알림 유실 없음.** 단, 하루 약 6건씩 DEAD 가 늘어 `dead_count>0` 이 굳고, 그러면
  준비 판정이 영구히 빨간불이라 **진짜 배달 실패가 묻힌다**(채널톡 1,188행과 같은 문제).
- 조치: `handle_unimplemented_consumer` 신설·등록. **기록 전용과 같은 함수로 뭉치지 않았다** —
  "배달할 것이 원래 없다" 와 "받는 쪽을 아직 안 만들었다" 는 다른 상태이고, 뭉치면 나중에
  소비자를 구현하는 사람이 차이를 못 본다. 로그도 debug 가 아니라 info 로 남긴다.
- 되돌림 안전장치: 등록 목록 **닫힌집합 계약**. 진짜 소비자를 붙이면 그 테스트가 빨개져
  "이 등록을 걷어내라" 는 문장을 다시 읽게 된다.

### 운영 실측 근거

```
DEAD 유형별:  CHANNEL_PUSH_RECORDED 1190 (2026-08-03~09-01, 09-01에 멈춤)
              STAGE_NOTIFICATION     154 (2026-08-03~09-08, 계속 증가)
최근 7일 증가: 09-01 3 · 09-02 6 · 09-03 10 · 09-04 2 · 09-06 1 · 09-07 13 · 09-08 5
180일 경과분: 0건 (가장 오래된 것이 08-03 — 자연 만료는 2027-01-30 이후)
notifications 중 단계 전이 유형: 0건 (전 기간)
```

### 검증 + 변이 4종

```
$ python -m pytest tests/domains/test_sidefx_record_only_effects.py -q
6 passed

MUT24 STAGE_NOTIFICATION 등록 제거        1 failed, 5 passed
MUT25 기록 전용 handler 로 뭉갬            1 failed, 5 passed
MUT26 기존 GEOCODE 배선 제거               2 failed, 4 passed
MUT27 두 handler 를 같은 함수로 별칭       2 failed, 4 passed
복원 후: 6 passed
```

### 남는 것

기존 DEAD 1,344행은 되살리지 않는다(배달할 것이 없다). 다만 retention 이 정리하기 전까지
기본 판정은 계속 `dead_count` 로 빨간불이다 — 운영 감시는 그때까지 `--kinds` 나
`--max-dead` 를 써야 한다. 정리 시점은 **사용자 판단**(F-20).

| # | 항목 | 필요한 것 |
|---|---|---|
| F-20 | 기존 DEAD 1,344행이 2027-01-30 까지 남아 기본 판정을 빨갛게 고정 | 운영 쓰기라 승인 필요 — 정리할지, 만료를 기다릴지 |

## T21. F-19 운영 반영 + F-20 정리 착수 (사용자 결정 "지금 지워서 초록불로")

- 순서를 지켰다: **① 그만 쌓이게 하는 수정을 먼저 운영에** → ② 이미 죽은 행 정리.
  반대로 하면 며칠 만에 다시 빨간불이 된다(하루 약 6건).
- ① PR #314 머지 → production `f17b047ac`. 검사 4개 SUCCESS. 승격 브랜치에서 APP_OK ·
  계약 6건 · pre_push_smoke PASSED. 충돌은 원장 문서 1건(코드 충돌 0).
- **SIDEFX 는 web·worker 와 별도 서비스다**(09-02 함정). 머지 직후 로그에는 여전히
  `NoHandlerError STAGE_NOTIFICATION` 이 찍혔다 — 배포가 끝나기 전이었다.
- ② 정리 도구는 **새로 만들지 않았다**. `tools/ops/purge_domain_side_effect_outbox.py` 가
  이미 dry-run 기본·ID 멤버십 삭제·PENDING/PROCESSING 구조적 제외·advisory lock·배치 커밋
  재개를 갖췄다. `--dead-retention-days 0 --done-retention-days 99999` 로 DEAD 만 겨눈다.

### 운영 dry-run (아무것도 안 지움)

```
[purge_domain_side_effect_outbox] mode=dry-run done_retention_days=99999 dead_retention_days=0
  scanned_done=0 scanned_dead=1345 deleted_done=0 deleted_dead=0 batches=0 elapsed=2.0s
```

`scanned_done=0` — 정상 처리된 쪽지는 한 건도 대상이 아니다.

### 새 handler 가 실제로 붙었는지 판정하는 방법

행 `#2436`(시도 9회, 다음 시도 05:45:43)이 **DONE 이면 새 코드**, DEAD 면 아직 옛 코드다.
로그 문자열이 아니라 이 전이로 판정한다.

### 판정 결과 — SIDEFX 는 9월 2일 코드로 멈춰 있었다 (F-21, 이번 세션 최대 발견)

행 `#2436` 이 **DEAD(시도 10, NoHandlerError)** 로 끝났다. 로그 문자열이 아니라 DB 전이로
판정했다. 이어서 빌드 로그를 보니 이유가 나왔다:

```
$ railway logs --build   (service=SIDEFX, project=FOMS-PRODUCTION)
org.opencontainers.image.created: 2026-09-02T00:44:55Z
```

**SIDEFX 서비스는 2026-09-02 이후 한 번도 다시 빌드되지 않았다.** production 브랜치에
머지해도 이 서비스는 자동 배포되지 않는다(web·WORKER 는 된다). 컨테이너도 그때 뜬
프로세스 그대로다(`owner=9ba6258b9cdc`, 재시작 흔적 없음).

이것이 뜻하는 바:

* 오늘 올린 `STAGE_NOTIFICATION` 수정(PR #314)이 **운영에서 안 돈다**.
* 오늘 올린 F-7(SIDEFX 워커 Sentry 배선, PR #310)도 **안 돈다** — 같은 프로세스 몫이다.
* 9월 2일 수정이 반영된 건 그때 수동 배포를 했기 때문이다.
* 즉 **outbox 워커 쪽은 고쳐도 운영에 안 붙는 경로**였다. F-19 보다 이쪽이 크다.

CLI 로는 못 고친다: `railway redeploy` 는 같은 커밋(9월 2일 이미지)을 다시 돌리고,
`railway up` 은 로컬 폴더를 업로드해 커밋 이력과 어긋난다. 대시보드에서 최신 커밋 배포가
필요하다(사용자 진행 중).

| # | 항목 | 필요한 것 |
|---|---|---|
| F-21 | SIDEFX 서비스가 production 푸시로 자동 배포되지 않는다 | 서비스 설정(감시 경로·브랜치 연결·CI 대기)을 조사해 근본 원인을 찾고, 안 되면 배포 절차 문서에 "SIDEFX 는 수동 배포" 를 못박아야 한다. **지금까지 이 사실이 어디에도 안 적혀 있었다** |

### 근본 원인: Redeploy 는 최신 커밋을 안 가져온다 (F-21 확정)

사용자가 대시보드에서 Redeploy 를 눌렀고, 그 결과가 이것이다:

```
SUCCESS  2026-09-08T06:11:01Z  sha=bbd75e08d  "Merge pull request #253"   ← Redeploy 결과
REMOVED  2026-09-02T00:44:36Z  sha=bbd75e08d  "Merge pull request #253"
```

**Redeploy 는 직전 배포와 같은 커밋을 다시 실행한다.** 대시보드에 그것밖에 없다. 9월 2일
원장이 이미 적어둔 함정인데 이번에 다시 밟았다 — 그때 쓴 방법이 정답이다:

```
mutation { serviceInstanceDeploy(serviceId:"…", environmentId:"…", latestCommit:true) }
```

API 접근 메모(다음 사람 몫): CLI 토큰(`~/.railway/config.json` → `user.token`)을
`Authorization: Bearer` 로 보내되 **`User-Agent: railwayapp/<ver>` 를 반드시 넣는다** —
없으면 403 이다. `serviceInstanceDeployV2` 에는 `latestCommit` 인자가 없다(400).

결과:

```
SUCCESS 2026-09-08T06:13:08Z  f17b047ac  Merge pull request #314   ← 새 코드
REMOVED 2026-09-08T06:11:01Z  bbd75e08d  Merge pull request #253
```

**판정은 로그 문구가 아니라 `meta.commitHash` 로 한다.**

## T22. F-20 실행 — 운영 DEAD 전량 정리 (사용자 승인)

```
$ purge_domain_side_effect_outbox.py --dead-retention-days 0 --done-retention-days 99999 --apply
status=DEAD batch=1 deleted=1000 total=1000
status=DEAD batch=2 deleted=348  total=1348
mode=apply scanned_done=0 scanned_dead=1348 deleted_done=0 deleted_dead=1348 batches=2 elapsed=2.5s
```

`deleted_done=0` — 정상 처리된 쪽지는 한 건도 안 건드렸다. 새 도구를 만들지 않고 기존
SIDEFX-RETENTION-01 CLI 를 그대로 썼다(dry-run 기본·ID 멤버십 삭제·PENDING/PROCESSING
구조적 제외·advisory lock·배치 커밋 재개).

### 정리 후 운영 판정

```
$ check_sidefx_readiness.py
[sidefx-readiness] READY failures=0

outbox 상태별: DONE 944 · PENDING 119   (DEAD 0)
```

**기본 판정이 처음으로 초록불이다.** 이제 dead_count 가 다시 오르면 그건 진짜 배달 실패다.

남은 증명 1건: 다음 단계 전이 쪽지가 DONE 으로 끝나는지(옛 코드면 DEAD). 감시 중.

## T23. F-21 근본 수정 — SIDEFX 에 브랜치 트리거가 없었다

원인은 "자동 배포가 안 된다" 가 아니라 **연결이 처음부터 없었다** 였다.

```
web        triggers=[{branch: production, repository: lahomsystem/FOMS}]
WORKER     triggers=[{branch: production, repository: lahomsystem/FOMS}]
FOMS-cron  triggers=[{branch: production, repository: lahomsystem/FOMS}]
SIDEFX     triggers=[]        ← 아무것도 없었다
```

조치: `serviceConnect(id, {repo:"lahomsystem/FOMS", branch:"production"})` 로 연결.
(`deploymentTriggerCreate` 는 400 "Problem processing request" 로 거부됐다.)

연결 후 확인 — 네 서비스가 같은 모양이 됐고, **SIDEFX 시작 명령이 그대로인지도 확인했다**
(연결이 설정을 덮어쓰면 web 명령으로 뜰 수 있다):

```
SIDEFX  triggers=[{branch: production, repository: lahomsystem/FOMS}]
        start=python tools/ops/run_domain_side_effect_outbox.py --loop --interval 5 ...
```

런북 `docs/runbooks/sidefx-worker-ops.md` 에 "배포(필독)" 절 신설 — Redeploy 함정·GraphQL
강제 배포·`meta.commitHash` 로 판정·User-Agent 403 을 모두 적었다.

남은 검증: **다음 production 머지 때 SIDEFX 가 자동으로 뜨는지** 확인해야 트리거가 실제로
작동한다는 증거가 된다(지금은 설정만 맞춘 상태).

### 최종 증명 — 실환경 end-to-end

```
쪽지 #2469  STAGE_NOTIFICATION  status=DONE  attempts=1  created=2026-09-08 06:51:55
```

정리 이후 처음 생긴 단계 전이 쪽지가 **시도 1회에 DONE** 으로 끝났다. 이전에는 같은 쪽지가
10회 재시도 끝에 DEAD 였다. 운영에서 새 handler 가 실제로 돈다는 직접 증거다.

## 후속 세션 2 최종 마감 v2 (2026-09-08)

| | |
|---|---|
| deploy | 워커 감시 축·간격 신고·단계 전이 handler·런북 (전 워크플로 green) |
| production | `f17b047ac` — PR #310(워커 감시 축) · PR #314(단계 전이 handler) |
| 운영 판정 | `check_sidefx_readiness` **READY failures=0** (DEAD 0, 첫 초록불) |
| 운영 하트비트 | 9종 전부 기록 중 |
| 인프라 | SIDEFX 에 production 브랜치 트리거 연결(6일간 배포 사각) |

처리한 후속: F-5 · F-6 · F-7 · F-9 · F-11(실사례) · F-18 · F-19 · F-20 · F-21.

### 남은 것

| # | 항목 | 상태 |
|---|---|---|
| F-12 | `SENTRY_DSN` 미설정 — Sentry 배선 4곳이 no-op | 사용자 판단 |
| F-17 | 하트비트 자동 조회 경로 없음(사람이 `--kinds` 로 불러야 읽힌다) | 사용자 판단 |
| F-21b | 트리거가 실제로 작동하는지는 **다음 production 머지 때 확인** | 관측 대기 |
| T6 | 로그인 한도·잠금 승격 · 운영 AMBIGUOUS 924건 · F-1 · F-4 | 사용자 판단 |
