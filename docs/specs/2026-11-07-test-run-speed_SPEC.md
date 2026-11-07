판정: 승인(2026-11-07 사용자 '이대로 만들기')

# 시험 속도 — 큰 시험 줄 서기 · 문서만 바뀐 푸시의 빠른 길 · 전체 시험 한 번만 (2026-11-07)

## 1. 왜

On 2026-11-07 the user asked: "세션마다 테스트가 너무 오래 걸리는 이유를 점검해봐."

These measurements were taken on this PC (12 cores, 32GB RAM, `PYTEST_XDIST_AUTO_NUM_WORKERS=4` set as a user environment variable).

- **Smoke alone takes 4 min 13 s.** That is 38 s of setup (APP 7 s, verify 6 s, inventories 18 s), 189 s for the full suite (17,646 tests) and 25 s for tests/visual.
- **Overlapping runs are 5 times slower.** In the same session the same full run took 230–280 s alone and 1,257–1,365 s when two runs overlapped. Two other sessions were running smoke at the same time.
- **Memory runs out.** Each xdist worker imports the app and collects every test, which takes about 1 GB of private memory. When runs overlap, the commit charge runs out and smoke dies with `MemoryError`; it happened again on 2026-11-07. The rerun was then cancelled.
- **A doc-only push pays for the full suite.** Changing one line of `docs/AI_STATUS.md` still runs the whole suite. On 2026-11-07 that took over 20 minutes when overlapping with other sessions, and the push was given up.
- **Sessions run duplicate full suites.** A session ran the full suite once before smoke and once more on the promote branch, so each change ran three full suites locally. PR CI runs the promote branch anyway.

## 2. 무엇을 바꾸나

### 2.1 큰 시험 줄 서기 (모든 세션 · 모든 도구 공통, 코드로 강제)

`tests/conftest.py` gets a `pytest_configure` and `pytest_unconfigure` pair that holds a machine-wide named mutex `Local\FOMS_PYTEST_BIG_RUN` while a big run is in progress. The logic lives in a new `tests/_big_run_lock.py`.

- **What counts as a big run:** Windows only, the xdist master (not a worker), and `numprocesses >= 2`. A single-process run of a few files is not locked.
- **CI is unchanged:** Linux is a no-op.
- **While waiting** it prints, every 30 s, "다른 창의 큰 시험이 끝나기를 기다립니다". The holder writes its PID, folder and start time to `%TEMP%\foms_pytest_big_run.json`, and the waiting message shows them.
- **If the holder dies,** Windows marks the mutex abandoned, and the waiting run takes it over at once. No stale lock file can remain.
- **Upper bound on waiting:** after 30 minutes the run gives up waiting, prints a warning and proceeds. This avoids blocking forever behind a hung run.
- **Off switch:** `FOMS_PYTEST_NO_LOCK=1`.
- **Coverage:** it applies to smoke, to full suites a session runs by hand, and to Codex and Cursor alike, because every run goes through pytest.

### 2.2 문서만 바뀐 푸시의 빠른 길 (`scripts/ops/pre_push_smoke.ps1`)

- **When it applies:** every path in `git diff --name-only origin/deploy...HEAD` matches `docs/**/*.md`, and neither `-Full` nor `-Visual` is set.
- **What it runs instead of the full suite:**
  - The new `tools/harness/smoke_docs_only.py` lists the test files under `tests/` that name both a docs path and `.md` (about 200 on 2026-11-07, 17% of test files). A wide net is safer: tests that sweep all of docs (links, canonical paths, budgets) never name the changed file.
  - Only those files run, with `-n auto`.
  - The screen prints "[FAST] 문서만 바뀜 — 문서를 읽는 시험 N개 파일만".
- **Why there is no fixed list:** the file list is found by searching the test sources every time, so it does not go stale. That was the lesson of 2026-09-22.
- **Safety net:** after the push, CI still runs the full suite.

### 2.3 전체 시험은 한 번만 (작업 습관 — 문서 규칙)

- **The rule:**
  - The full suite runs once per change, as the `pre_push_smoke` run.
  - Before smoke, run only the tests that touch the changed files, found with `grep -rl <파일 이름> tests`.
  - On the promote branch (cherry-pick from production), leave it to PR CI. Run the related tests only if the cherry-pick had a conflict or it skipped commits.
- **Where it goes:** the `push 직전 pre_push_smoke` sentence in `CLAUDE.md` § Git (edited in place, no new line), plus one sentence in the matching paragraph of `AGENTS.md` (read by Codex and Cursor).

## 3. 하지 않는 것

- **Raising the worker count** (from 4): only after a remeasure, once the queue is in place.
- **Impact-based test selection for code changes:** it would bring back the stale-list problem of 2026-09-22.
- **Lazy import of anthropic and folium** (2.4 s off app import): a separate task.

## 4. 검증

- **The lock decision function** (`should_lock(platform, is_worker, numprocesses, env)`): unit tests for Linux, worker, single process and the env switch.
- **The lock on a real run:** start two `-n 2` runs at the same time. The second one must print the waiting message and start only after the first ends. The decisive line is reported verbatim.
- **The doc-only check:** unit tests for these cases:
  - docs only gives fast
  - docs plus code gives full
  - `docs/harness/*.json` gives full
  - an empty change gives full
- **Smoke:**
  - one run on a docs-only commit (expect the fast path)
  - one run on a commit that includes code (expect the full suite)
- **Existing harness tests:** `tests/harness` green, including the CLAUDE.md line budget of 45 lines.
