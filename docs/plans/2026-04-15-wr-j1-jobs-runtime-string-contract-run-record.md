# WR-J1 — Jobs runtime-string contract decision

> **batch ID:** WR-J1  
> **risk axis:** runtime-string / worker compatibility  
> **실행일:** 2026-04-15  
> **상위 문서:** `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md` Program 2, `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md` WR-J1

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record, live truth 재판독 | `services/jobs/*`, `foms/services/jobs/*`, worker deploy files, queue payload format 변경 |

## 2. Live truth (2026-04-15 strict 재확인)

- **`foms/services/jobs/queue.py`**
  - `_TASK_PATH_PREFIX = "foms.services.jobs.tasks"` — **신규 enqueue**는 이 경로 문자열만 사용한다.
- **`services/jobs/queue.py`**, **`services/jobs/tasks.py`**
  - **thin shim**: `foms.services.jobs.{queue,tasks}` re-export만 담당 (루트에 구현 없음).
- **`foms/services/jobs/tasks.py`**
  - worker 구현 본체; `_REPO_ROOT` 등 패키징 민감 로직은 기존과 동일.
- **레거시 Redis 백로그:** 과거에 큐에 남은 job이 `services.jobs.tasks.*` 문자열을 가리키면, 워커는 루트 shim 모듈을 통해 동일 콜러블을 로드할 수 있다(drain window).
- **`railway-worker.toml`**
  - worker start: `rq worker default --url $REDIS_URL` (변경 없음).
- **`tests/contracts/runtime/foms_namespace_surface_tests.py`**
  - `test_canonical_jobs_queue_uses_namespaced_rq_task_path_prefix` — `_TASK_PATH_PREFIX == "foms.services.jobs.tasks"`.

## 3. Decision

### 3.1 Verdict (strict §2.2.1 정렬)

- **Canonical runtime owner:** `foms/services/jobs/*` (enqueue 문자열 포함).
- **Root `services/jobs/*`:** 구현 금지; **shim-only**로 strict delta lock과 정합.
- 이전 기록의 “`_TASK_PATH_PREFIX = services.jobs.tasks`” 서술은 **구식**이며, 현재 코드는 **foms 접두어**로 이미 전환됨.

### 3.2 유지 조건 (drain / 호환)

1. Redis에 **옛 문자열** job이 남아 있을 수 있으므로 루트 `services/jobs/tasks.py` shim은 drain 완료 전까지 유지한다.
2. **물리 파일 제거**는 큐 drain·스테이징 검증 후 별도 배치에서만 검토한다.

### 3.3 이후 정리 (선택)

- 백로그 만료·drain 증거 후 루트 `services/jobs` 디렉터리를 없앨지 여부는 **운영 게이트**로만 결정한다.

## 4. Bridge delta

- **문서 동기화:** 본 파일 §2·§3을 live truth(`foms` 접두어 enqueue + 루트 shim)에 맞게 갱신 (2026-04-15).
- **코드 변경:** 주석 정확화(`foms/services/jobs/queue.py` NOTE); 동작 변경 없음.

## 5. Supporting evidence

- `docs/plans/2026-04-10-step3-batch50-jobs-caller-cleanup-run-record.md` — 호출부·큐 정리 맥락(과거 문서는 legacy 문자열 호환을 언급할 수 있음).
- `docs/plans/2026-04-14-wave9-batch1-packaging-surface-freeze-run-record.md` — `foms/services/jobs/tasks.py` 패키징 민감도.

## 6. Next legal batch

- **WR-H1** — notifications / attachments / chat / channel cluster → `foms/api`·`foms/services` 수렴 (delta lock §3.3).
