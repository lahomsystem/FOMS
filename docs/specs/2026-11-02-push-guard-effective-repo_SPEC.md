# 푸시가 느린 원인 고치기 — 푸시 안전장치·커밋 원장·확인 도구가 "실제 작업 폴더"를 보게 한다

- 날짜: 2026-11-02
- 범위: 하네스(코어). 순서는 Spec → 승인 → 구현.
- 정본 계측: 이 문서 §1. 메모리 `project_push_slowness_guard_main_checkout`.

## 1. 무엇이 느렸나 (계측)

오늘 한 건(공지 사진 칸 수정, 스테이징 d367926c → 운영 PR #704)은 처음부터 끝까지 66분이 걸렸다.

| 구간 | 걸린 시간 | 성격 |
| --- | --- | --- |
| 코드 고치기 | 3.5분 | 작업 |
| 로컬 pre_push_smoke (15,723개, 워커 4) | 5분 | 기계 |
| **푸시 안전장치 승인 대기** | **18분** | **고장** |
| deploy CI (가장 긴 FOMS CI) | 6분 | 기계 |
| Railway 스테이징 배포 | 74초 | 기계 (CI 와 동시) |
| 운영 PR CI | 7분 | 기계 |
| Railway 운영 배포 | 50초 | 기계 |
| **운영 반영 확인 헛대기** | **21분** | **고장** |

기계가 실제로 쓴 시간은 약 17분이다. 나머지 39분은 아래 두 고장에서 나왔다.

지난 30일 기록(대화 기록 77개)을 보면 다음과 같다.
- deploy 푸시 때 안전장치가 사람 승인을 물은 횟수는 468번이다(타 세션 242 · 원장 없음 226).
- 한 번 기다린 시간의 중간값은 4~6분이고, 10분 넘게 기다린 것이 170번이다.
- CI 자체는 문제가 아니다. 최근 200번 중간값은 스테이징 푸시 4.6분, PR 5.5분이고, 실패는 1번과 5번이다. 09-22에 고친 것은 smoke 범위(목록에서 전체 스위트로)였고, 아래 고장은 그때 손대지 않았다.

## 2. 원인

### 2.1 푸시 안전장치가 메인 폴더를 보고 판정한다

- `tools/harness/guard_policy.py` 의 `_classify_git` 는 `_classify_git_push(..., project_root=_ctx_project_root)` 를 부른다.
- `_ctx_project_root` 는 `.claude/hooks/shared_utils.get_project_root()` 가 준 **훅 파일 위치**다. 언제나 `C:\DEV\FOMS` 다.
- 명령 앞의 `cd <워크트리>`, `git -C <dir>`, 훅 입력의 `cwd` 는 보지 않는다. `cd` 힌트(`_ctx_cwd_hint`)는 이미 있지만, reset·checkout 면제에만 쓴다.
- 메인 체크아웃의 로컬 `deploy` 는 10-22부터 멈춰 있다. origin/deploy 보다 304개 뒤처져 있고, 앞선 커밋 8개 중 7개는 이미 올라간 rebase 사본이다.
- 그래서 어느 창의 워크트리에서 `cd /c/tmp/foms-s-… && git push origin HEAD:deploy` 를 쳐도 "타 세션 커밋 포함 7/8"이 뜬다.

### 2.2 커밋 원장이 메인 HEAD 를 적는다

- `.claude/hooks/record_commit_ledger.py` 는 `record_git_commit_ledger.record_head_commit(project_root=메인, …)` 를 부른다.
- 이 함수는 `git rev-parse HEAD` 를 메인에서 실행한다. 그래서 워크트리에서 만든 커밋 대신 메인 HEAD(남의 커밋)가 이 세션 몫으로 적힌다. 실례로 이 세션 원장에는 `b6164e59b` 가 들어 있다.
- 워크트리 원장(`<wt>/docs/harness/runtime/session_commit_ledger.json`)은 비어 있다. 설계(07-28 Phase 1)는 "워크트리 폴더에서 Claude 창을 새로 연다"를 전제했지만, 실제 세션들은 메인 창에서 `cd` 로 워크트리에 들어간다.
- 위험: `promote_own_to_production.py --session-id` 는 원장으로 커밋을 고른다. 그래서 남의 커밋을 운영에 올릴 수 있다. 지금까지 `--shas` 를 직접 줘서 피했을 뿐이다.

### 2.3 확인 도구가 최신 기록을 받지 않는다

- `tools/ops/check_deploy_drift.py` 는 fetch 하지 않는다. 로컬 origin/production 이 낡은 상태에서 그 커밋 배포가 더 새 배포로 바뀌면(REMOVED) "[누락] 브랜치 X 인데 배포는 X — 0커밋 뒤"로 판정한다. `check()` 의 첫 일치 분기가 REMOVED 를 LIVE·IN_FLIGHT 로 보지 않기 때문이다. 오늘 운영 반영은 50초 만에 끝났는데, 이 판정 때문에 21분을 기다렸다.
- `tools/harness/ci_watch.py` 는 받아 오지 않은 SHA(머지 커밋)를 주면 "ref 해석 실패"로 바로 끝난다.

## 3. 고칠 것

### F1. 안전장치는 명령의 실효 폴더로 판정한다

- 실효 폴더는 아래 순서로 정한다.
  1. 같은 git 명령의 `-C <dir>`
  2. 같은 명령 줄에서 그보다 앞선 마지막 `cd <dir>` / `pushd <dir>`
  3. 훅 입력 JSON 의 `cwd`(Claude Code PreToolUse 입력에 들어 있다)
  4. 지금처럼 훅 위치(메인)
- 상대 경로는 3번(없으면 4번) 기준으로 절대 경로로 바꾼다.
- 정한 폴더를 `git rev-parse --show-toplevel` 로 저장소 루트로 바꾼 뒤 `classify_deploy_scope(그 루트, session_id)` 를 부른다.
- 이렇게 판정할 수 없으면 묻는다(fail-closed 그대로).
  - `cd -`, `$VAR`·`~`·`$(…)` 이 든 경로, `popd`
  - 존재하지 않는 폴더, git 저장소가 아닌 폴더
  - 실효 루트의 `origin` 이 FOMS 저장소와 다를 때
- `guard_shell.py` 는 payload 의 `cwd` 를 `classify_command(..., cwd=...)` 로 넘긴다. 키가 없으면 지금과 같다.
- 바꾸지 않는 것: production 푸시 확인, 강제 푸시 확인, reset·checkout·DB·Railway 판정.

### F2. 커밋 원장은 커밋한 폴더의 HEAD 를 적는다

- `record_commit_ledger.py` 는 F1 과 같은 규칙(`-C` → 앞선 `cd` → payload `cwd` → 메인)으로 커밋 폴더를 정한다. 같은 도우미 함수를 쓴다.
- 그 폴더 저장소에서 `rev-parse HEAD` 를 한다.
- 원장 기록 위치:
  - 그 저장소 원장에 적는다. 세션 워크트리라면 `deploy_push_scope` 가 union 으로 읽는 곳이다.
  - 그 저장소가 메인이 아니면 메인 원장의 같은 세션 키에도 적는다. 승격 도구가 어디서 돌든 찾게 하기 위해서다.
- 판정 불가면 지금처럼 기록하지 않고 hook_log 만 남긴다(fail-open, 기록 훅이라 막지 않는다).
- 이미 잘못 적힌 기록은 자동으로 지우지 않는다. 고친 날 이전 기록이 든 세션 키로 승격할 때는 `--session-id` 대신 `--shas` 를 쓴다(이 문서 §2.2 가 근거).

### F3. 확인 도구는 먼저 받아 온다

- `check_deploy_drift.py`
  - 판정 전에 `git fetch -q origin deploy production` 을 한다. 실패하면 판정 불가(exit 2)이고, 초록으로 뭉개지 않는다.
  - 브랜치 머리와 같은 커밋 배포가 REMOVED 이고, 지금 LIVE 배포 커밋이 그 머리의 후손이면(`merge-base --is-ancestor`) 일치로 본다. 메모는 "더 새 배포가 덮음"으로 남긴다.
- `ci_watch.py`
  - ref 해석에 실패하면 `git fetch -q origin <branch>` 를 한 번 하고 다시 해석한다. 그래도 안 되면 지금처럼 게이트 불가로 끝낸다.
- 푸시 뒤 안내(`post_bash` 의 CI-GATE 문구)
  - production 푸시라면 "production 은 push CI 가 없다 — `check_deploy_drift.py --target production`"을 먼저 권한다.

### F4. CI 본 스위트를 3조각으로 나눠 동시에 돈다 (사용자 추가 승인 2026-11-02)

- `tests/conftest.py` 의 `pytest_collection_modifyitems` 는 `FOMS_TEST_SHARD=i/N` 이면 테스트 파일 경로의 crc32 % N == i-1 인 파일만 남긴다. 파일 단위라 `--dist loadfile` 과 같은 이유로 모듈 fixture 가 갈리지 않는다. 새 패키지는 없다.
- `.github/workflows/ci.yml` 의 `test` 잡은 `matrix.shard: [1, 2, 3]`(fail-fast: false)로 돈다. 디자인 lint·문서 계약·Redis·UI 구조 스텝은 1번 조각만 맡는다.
- 조각별 테스트 수(2026-11-02 수집): 5,198 · 5,255 · 6,049 = 16,502(전체와 같음).
- 계약: `tests/domains/test_ci_shard_contract.py` 가 조각 수와 N 이 같은지, 1번 전용 스텝, 빈 조각 없음을 확인한다.
- 고르게 나누기(11-03, 사용자 선택): crc32 로 나누니 무거운 파일이 몰려 기록 시간이 174·232·174초였고, CI 에서도 2번 조각이 가장 늦었다(173초 대 149·120초). 이제 `tests/ci_shard_durations.json`(파일별 초, `tools/harness/refresh_ci_shard_durations.py` 로 갱신)으로 큰 파일부터 가장 덜 찬 조각에 넣는다. 1번 조각은 추가 스텝 몫으로 15초를 먼저 찬 것으로 친다. 기록에 없는 새 파일은 중간값이다. 계약 시험은 가장 무거운 조각이 평균의 115% 이하인지, 기록이 파일의 60% 이상을 덮는지 본다.

### F5. 훅은 메인 체크아웃의 파일로 돈다 — 메인을 갱신해야 효과가 난다

- 훅 명령은 `python "${CLAUDE_PROJECT_DIR}/.claude/hooks/…"` 이고, 가드는 같은 폴더의 `tools/harness` 를 읽는다.
- 메인 체크아웃(C:\DEV\FOMS)의 로컬 deploy 는 10-21 기준이다. 그 뒤 deploy 에 올라간 하네스 수정(11파일, 약 1,000줄)이 훅에 반영되지 않고 있다.
- 이 설계의 수정도 deploy 에 올린 뒤 메인 체크아웃을 origin/deploy 로 맞춰야 실제 훅에 적용된다.
- 메인에는 남의 미커밋 변경(10-22·10-30 날짜)과 고유 커밋 1개(`e4674d528`)가 있다. 그래서 맞추는 방법은 사용자와 따로 정한다.
- 옛 guard_policy 와 함께 돌아도 깨지지 않게 했다. `guard_shell.py` 는 `cwd` 인자 TypeError 를, `record_commit_ledger.py` 는 도우미 ImportError 를 예전 동작으로 받는다.

### F6. 세션 시작에 메인 체크아웃 낡음을 알린다 (사용자 선택 2026-11-03)

- 11-03 에 메인 체크아웃을 origin/deploy 로 맞췄다. 맞추기 전 상태는 로컬 브랜치 `backup/main-deploy-20261103`·`backup/main-wip-20261103` 와 `c:/tmp/main_backup_20261103/main_wip.patch` 에 남겼다.
- 다시 뒤처지는 것을 막으려고 `.claude/hooks/session_start.py` 가 startup·resume 때 알린다. 조건은 `origin/deploy...HEAD` 에서 뒤처짐이 1 이상이고, 하네스·세션 규칙 경로(`.claude`, `CLAUDE.md`, `AGENTS.md`, `tools/harness`, `tools/ops`, `scripts/ops`)가 다를 때다.
- 모델에게는 `[MAIN-STALE]` 를, 사용자에게는 `systemMessage` 를 보낸다. 앱 코드만 다르면 알리지 않는다.
- 앞섬 0 이면 `merge --ff-only` 를 권하고, 갈라졌으면 백업 뒤 사용자에게 묻게 한다. 자동으로 맞추지는 않는다(다른 창이 메인에서 일하는 중일 수 있다).
- 시험: `tests/harness/test_session_start_main_stale.py`.

## 4. 하지 않는 것 (따로 정할 일)

- 로컬 smoke 를 줄이고 Railway "Wait for CI" 켜기. 09-22 결정(목록 smoke 가 red 를 놓침)과 부딪혀서 따로 판단한다.
- 운영 PR 자동 병합(`allow_auto_merge` + 필수 검사). 저장소 설정을 바꾸는 일이다.

## 5. 완료 기준 (검증 명령)

1. `tests/harness/test_guard_policy.py` 에 임시 git 저장소 시험을 더한다. 메인 흉내는 origin/deploy 보다 앞선 남의 커밋을 갖고, 워크트리 흉내는 basename `foms-s-x` 에 자기 커밋 1개와 원장을 갖는다.
   - `cd <wt> && git push origin HEAD:deploy` → allow
   - payload `cwd=<wt>` 만 주고 `git push origin HEAD:deploy` → allow
   - 메인에서 같은 명령 → ask("타 세션")
   - `git -C <main> push origin HEAD:deploy`(cd 는 wt) → ask
   - `cd "$X" && git push …` / `cd - && git push …` / 없는 폴더 → ask
   - `cd <wt> && git push origin HEAD:production` → ask(그대로)
2. `tests/harness/test_session_commit_ledger.py`:
   - `cd <wt> && git commit …` 페이로드 → wt HEAD 가 wt 원장과 메인 원장 둘 다에 적힌다.
   - 메인 커밋 → 메인 원장에만 적힌다.
3. `tests/harness/test_check_deploy_drift.py` (drift·ci_watch 단위 시험):
   - REMOVED 머리와 LIVE 후손 → 일치
   - REMOVED 머리인데 LIVE 가 후손이 아님 → 누락
   - fetch 실패 → exit 2
   - ci_watch 해석 실패 뒤 fetch 하고 다시 시도
4. `tests/domains/test_ci_shard_contract.py` green. `python -m pytest tests/harness -q -n 2` 와 `pre_push_smoke.ps1` 은 exit 0, deploy CI 4종은 green 이어야 한다.
5. 실측:
   - 이 세션에서 워크트리 커밋 → `cd <wt> && git push origin HEAD:deploy` 를 하면 승인 질문이 없어야 한다. SHELL_GUARD_LOG 에도 그 시각 ask 줄이 없어야 한다.
   - 메인에서 같은 푸시를 `--dry-run` 없이 시험하지 않는다(실제 푸시가 된다). 메인 판정은 1번 단위 시험으로 대신한다.
6. `docs/harness/policy/DECISIONS.md` 에 결정을 기록한다.

## 6. 위험과 막는 법

- **`cd` 를 적어서 안전장치를 비켜 가기:** 명령에 적힌 `cd` 는 셸이 실제로 그 폴더에서 push 를 실행한다는 뜻이다. 그래서 판정 기준으로 맞다. 해석이 애매한 형태(§3 F1 목록)는 전부 묻는다.
- **서브셸·세미콜론 순서:** `(cd A && …); git push` 처럼 괄호 안 cd 는 바깥에 영향이 없다. 괄호 안 cd 는 힌트로 쓰지 않는다. 판정할 수 없으면 묻는다.
- **원장 이중 기록:** union·세션 판정은 "있으면 내 것"이라 중복은 무해하다. 원장 파일 쓰기는 지금처럼 tmp 파일에 쓴 뒤 교체한다.
- **훅 지연:** `rev-parse --show-toplevel` 1회와 `git log` 1회가 더해진다. 지금 판정도 git 을 2번 부르므로 비슷하다.

## 7. 기대 효과

- 워크트리에서 하는 deploy 푸시는 사람 승인 없이 통과한다. 지난 30일 기준 승인 요청 468번 중 대부분이 사라진다. 남의 커밋이 진짜로 섞이면 지금처럼 묻는다.
- 운영 반영 확인이 거짓 '누락' 없이 1~2분 안에 끝난다.
- 오늘 사례로 보면 66분이 약 27분이 된다. 기계 17분, 작업, 사용자 확인만 남는다.
