# deploy → production 전체 승격 릴리스 플랜

> **에이전트 작업자에게:** 이 플랜은 코드 구현이 아니라 **운영 릴리스 런북**이다. task 순서를 지키고, 각 task의 완료 기준(실제 명령 출력)을 확인한 뒤 다음으로 넘어간다. 되돌리기 어려운 단계(T6 머지)에는 사용자 승인 게이트가 있다.

**Goal:** `origin/deploy`를 `origin/production`으로 전량 승격해, 채널톡 푸시 유실 게이트·ERP 저장 낙관 잠금(If-Match)·Quest dirty 가드를 포함한 342커밋을 운영에 반영한다.

**Architecture:** production 기반 브랜치에서 `git read-tree`로 트리를 deploy와 완전 동일하게 치환한 머지 커밋을 만들고 PR로 올린다(2026-07-01 `e75d739b`, 2026-07-22 `221d0df3` 전례 2회, 트리 해시 일치 검증됨). 마이그레이션은 Railway `preDeployCommand`가 배포당 1회 자동 실행한다(`set -e` fail-closed).

**Tech Stack:** Git / GitHub CLI / Railway CLI / Alembic / PostgreSQL 17.10 / PowerShell 5.x

---

## Global Constraints

- **production 직접 push 금지.** GitHub branch protection이 PR을 강제한다(`enforce_admins: true`). 이 플랜의 모든 반영은 PR 경유다.
- **force-push·reset 금지.** 로컬 harness guard가 `deny`, GitHub이 `allow_force_pushes: false`. 롤백은 revert PR이 유일한 정규 경로다.
- **DB 롤백 런북은 저장소에 없다.** 정본 백업은 Railway PostgreSQL 스냅샷(콘솔 작업)이며, 마이그레이션 #18 이후로는 alembic downgrade가 불가능하다(§확정 리스크 2).
- **작업은 공유 워킹트리(`C:\DEV\FOMS`)가 아니라 `c:/tmp` 격리 worktree에서 한다.** 동시 세션이 상시 커밋 중이다.
- 한글 커밋은 UTF-8 파일 + `git commit -F` (Win11 인코딩).
- 세션 worktree(`foms-s-*`)에서 alembic 실행은 코드 레벨로 차단돼 있다(`migrations/env.py:10-17`).

---

## 실측 사실 (전부 직접 검증 완료, 2026-07-30)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| deploy HEAD | `c300f94f` (플랜 작성 시점, T1에서 재고정) | `git rev-parse origin/deploy` |
| production HEAD | `8e40e0e3` (2026-07-27) | `git rev-parse origin/production` |
| 승격 커밋 수 | **342** | `git rev-list --count origin/production..origin/deploy` |
| 파일 변경 | 821파일 +124,280 / −44,206 | `git diff --stat` |
| 미적용 마이그레이션 | **29개** (`ops_approval_00` ~ `wiz_pending_00`) | `alembic history -r phase_0a_notif_user_states:head` |
| 신규 테이블 | **39개** | 운영 DB 45 vs deploy 모델 62 대조 |
| 기존 테이블 추가 컬럼 | **18개** (NOT NULL 4개) | information_schema 대조 |
| 운영 PostgreSQL | **17.10** | `SELECT current_setting('server_version')` |
| 운영 DB 크기 | **90 MB** (`orders` 3,606행 / 39 MB) | `pg_database_size` |
| 신규 파이썬 패키지 | **0** | `git diff -- requirements.txt` → 빈 diff |
| `SECRET_KEY` | len=86, 알려진 기본값 아님 → **부팅 통과** | Railway 변수 실측 |
| `KAKAO_REST_API_KEY` | **이미 설정됨** (len=32) | Railway 변수 실측 |
| Railway 서비스 | `web`·`WORKER`·`FOMS-cron`·`Redis`·`Postgres` 전부 존재 | `railway status` |
| production PR CI | **`perf-gate` 1개뿐** | `.github/workflows/*.yml` 트리거 전수 |
| perf-gate 강제력 | `required_status_checks: **null**` → **GitHub이 강제하지 않음** | `gh api .../branches/production/protection` |

---

## 확정된 리스크 3개

### 리스크 1 — `orders` ACCESS EXCLUSIVE 락이 마이그레이션 #2~#18 구간 유지

`migrations/env.py:127`의 `context.configure(...)`에 `transaction_per_migration`이 없다(alembic 기본값 `False`) → 29개가 **단일 트랜잭션**에서 돈다.

- #2 `rev_00_order_mutation`이 `ALTER TABLE orders ADD COLUMN mutation_version`으로 `orders`에 ACCESS EXCLUSIVE를 잡는다.
- 첫 COMMIT은 #18 `startup_schema_00`의 `_run_concurrently()`에서야 난다.
  (#14 `index_ops_00`의 조건부 COMMIT은 **발동하지 않는다** — 운영 `designer_sketchup_parse_jobs`의 unique 제약이 0개임을 실측 확인.)
- 그 구간 동안 구 replica의 `orders` **SELECT 포함 모든 쿼리가 락 대기**한다.

**완화 근거**: PG 17이라 `server_default=text('1')` 상수 default는 테이블 재작성이 없다(카탈로그만 갱신). #3~#17은 대부분 빈 신규 테이블 CREATE이고, 비-CONCURRENTLY 인덱스 대상도 `order_attachments` 2,343행 / `order_schedule_dates` 6,594행 / `order_tasks` 5,775행으로 전부 소형이다. 90MB DB 기준 락 구간은 **수 초** 규모로 예상된다.

**대응**: 업무 시간 외 실행(T6 승인 게이트에서 시각 확인). `transaction_per_migration=True`로 바꾸는 방안은 **채택하지 않는다** — 락 구간은 줄지만 부분 적용 지점이 1개에서 29개로 늘어 롤백 계획이 더 어려워지고, 릴리스 직전에 마이그레이션 인프라를 건드리는 변경 자체가 위험하다.

### 리스크 2 — #18 이후 alembic 롤백 불가 (실질적 비가역 지점)

`migrations/versions/startup_schema_00_ensure_orders_flat_and_indexes.py:115` — `downgrade()`가 명시적 `pass`다(주석: "additive downgrade destructive 금지"). 29개 중 downgrade 미구현은 이 1건뿐이지만, 체인 중간이라 **이 지점 아래로 되돌릴 수 없다**.

→ **T4의 Railway 스냅샷이 유일한 DB 되돌리기 수단이다. 건너뛰지 말 것.**

부수 위험: `startup_schema_00`은 `CREATE INDEX CONCURRENTLY` 12개(GIN trgm 2개 포함)를 만든다. 실패 시 `indisvalid=false` 인덱스가 남고, 모든 문이 `IF NOT EXISTS`라 **재실행해도 자동 복구되지 않는다**(이름이 존재해 스킵됨). 현재 운영 INVALID 인덱스는 0개(실측) — 깨끗한 baseline이다.

### 리스크 3 — perf 예산 파일 분기 → 승격 PR의 perf-gate 실패 예상

`tools/perf/perf_budgets.json`이 두 브랜치에서 갈라져 있다:

| 경로 | production | deploy |
|---|---|---|
| `/erp/production/dashboard?view=fragment` → `body_bytes_max` | **78218** | **60021** |

production 커밋 `676939c8`("데이터 드리프트 60021→78218")이 deploy로 역병합되지 않았다. 전체 승격은 트리를 deploy로 치환하므로 이 재시드가 되돌아간다. 승격 PR의 perf-gate는 이 예산으로 스테이징을 측정하므로 **해당 경로에서 실패가 예상된다**(재시드 당시 관측 60168 > 60021).

→ T3에서 **승격 브랜치 위에 이 값을 복원하는 커밋을 미리 얹는다.**

---

## Task 1: 정본 갱신 · 승격 범위 고정 · 상위집합 확인

**Files:** 없음 (읽기 전용 확인)

- [ ] **Step 1: 정본 fetch 후 HEAD 고정**

```bash
cd c:/DEV/FOMS
git fetch origin deploy production
git rev-parse origin/deploy origin/production
git rev-list --count origin/production..origin/deploy
```

출력된 deploy SHA를 이 플랜의 `<DEPLOY_SHA>`로 쓴다(이후 모든 단계에서 동일 값 사용). 커밋 수가 342에서 크게 늘었으면 타 세션이 계속 밀어넣는 중이므로 T2로 넘어가기 전에 사용자에게 보고한다.

- [ ] **Step 2: production 전용 파일 분류**

```bash
git diff --name-only --diff-filter=D origin/production origin/deploy > /tmp/prod_only.txt
wc -l /tmp/prod_only.txt
grep -civ designer /tmp/prod_only.txt
grep -vi designer /tmp/prod_only.txt
```

기대: 총 132개, designer 관련 119개(별도 앱 분리로 의도적 제거), 나머지 13개는 아래와 정확히 일치해야 한다.

```
foms/api/backup.py
foms/api/foms_queue_actions.py
foms/services/admin/backup_service.py
foms/services/orders/mobile_queue_action.py
scripts/maintenance/🚨_간단_백업.bat
scripts/migrations/web_migration.py
static/js/foms/swipe-actions.js
templates/admin/migration_result.html
templates/admin/migration_upload.html
templates/orders/partials/dashboard_mobile_queue.html
templates/partials/shared/erp_mobile_queue_card.html
tests/domains/test_as_toolbar_hydrate.py
tests/qa_deploy_test.py
```

**목록에 없는 파일이 나오면 중단하고 사용자에게 보고한다.** 전체 승격은 그 파일을 운영에서 삭제한다.

- [ ] **Step 3: production 전용 커밋 중 내용이 되돌아가는 것 확인**

```bash
git log --oneline origin/deploy..origin/production
git diff origin/production origin/deploy -- tools/perf/perf_budgets.json
```

기대: perf 예산 1건 차이(리스크 3). **다른 파일 차이가 추가로 나오면 중단하고 보고한다.**

**완료 기준:** `<DEPLOY_SHA>` 확정, production 전용 파일이 위 132개와 일치, 되돌아가는 내용이 perf 예산 1건뿐.

---

## Task 2: staging CI green 확인

**Files:** 없음

- [ ] **Step 1: deploy HEAD의 전 워크플로 상태 조회**

```bash
cd c:/DEV/FOMS
gh run list --branch deploy --limit 12 --json workflowName,status,conclusion,headSha \
  --jq '.[] | "\(.conclusion // .status)\t\(.workflowName)\t\(.headSha[0:8])"'
```

`<DEPLOY_SHA>`에 대해 **`FOMS CI`·`Harness CI`·`FOMS PostgreSQL Lane`·`perf-gate (staging)` 4개가 전부 `success`** 여야 한다.

`ci_watch.py`만으로 판단하지 말 것 — perf-gate 등 일부 워크플로를 놓치는 사각이 있다.

- [ ] **Step 2: 실패가 있으면 중단**

하나라도 red면 승격하지 않는다. 근본 수정 → deploy 재푸시 → green 확인 후 T1부터 다시 시작한다.

**완료 기준:** 4개 워크플로 전부 `success`.

---

## Task 3: 승격 브랜치 생성 (read-tree 트리동일 머지 + perf 예산 복원)

**Files:**
- Modify: `tools/perf/perf_budgets.json` (승격 브랜치에서만)

- [ ] **Step 1: 격리 worktree에 production 기반 브랜치 생성**

```bash
cd c:/DEV/FOMS
git worktree add -B promote/full-deploy-<DEPLOY_SHA> c:/tmp/foms-prod-full origin/production
cd c:/tmp/foms-prod-full
git log --oneline -1
```

기대: `8e40e0e3 Merge pull request #33 ...`

- [ ] **Step 2: 트리를 deploy와 완전 동일하게 치환**

```bash
git merge --no-commit --strategy=ours origin/deploy
git read-tree -u --reset origin/deploy
git status --short | head
```

`--strategy=ours`는 MERGE_HEAD만 deploy로 잡고 트리는 production을 유지한다. 그 다음 `read-tree -u --reset`이 워킹트리+인덱스를 deploy 트리로 통째 치환한다. **hunk 단위 충돌 해결을 하지 말 것** — 이 패턴의 요점은 수동 병합을 하지 않는 것이다.

- [ ] **Step 3: 트리 동일성 검증 (커밋 전 필수)**

```bash
git write-tree
git rev-parse origin/deploy^{tree}
```

두 해시가 **완전히 같아야 한다.** 다르면 중단하고 보고한다.

- [ ] **Step 4: 머지 커밋 생성**

커밋 메시지를 UTF-8 파일로 저장한 뒤(`git commit -m "한글"` 금지):

```
merge: deploy 전체 승격 → production (deploy HEAD <DEPLOY_SHA>, 342커밋)

사용자 명시 "전체 승격" 지시로 deploy HEAD를 production으로 전량 반영.
승격 방식: production 기반 머지 커밋, 트리를 origin/deploy와 동일하게 재설정
(2026-07-01 e75d739b · 2026-07-22 221d0df3 전례와 동일 패턴).

포함 핵심:
- 채널톡 푸시 전 미저장 변경 저장 게이트 (주문 4414 유실 사고 근본수정)
- ERP 저장 낙관 잠금(If-Match) 배선 — 동시편집 lost update 차단
- Quest 자동전환 dirty 가드
- REV-00 order mutation 엔진 + 마이그레이션 29개(신규 테이블 39개)

deploy HEAD CI 전부 green(FOMS CI·Harness CI·PostgreSQL Lane·perf-gate staging).
```

```bash
git commit -F <메시지파일경로>
git show --stat --oneline HEAD | head -3
```

- [ ] **Step 5: perf 예산 재시드 복원 (리스크 3 대응)**

예산 파일 구조는 `{"_comment": ..., "_global": {...}, "paths": {"<경로>": {...}}}` 다(확인함). 인라인 `python -c`는 따옴표 중첩으로 깨지므로 스크립트 파일로 실행한다.

`c:/tmp/restore_budget.py` 로 저장:

```python
import json

KEY = "/erp/production/dashboard?view=fragment"

prod = json.load(open("c:/tmp/prod_budgets.json", encoding="utf-8"))
cur = json.load(open("tools/perf/perf_budgets.json", encoding="utf-8"))

old = cur["paths"][KEY]["body_bytes_max"]
new = prod["paths"][KEY]["body_bytes_max"]
assert new > old, f"운영 값이 더 크지 않다: {old} -> {new}"
cur["paths"][KEY]["body_bytes_max"] = new

with open("tools/perf/perf_budgets.json", "w", encoding="utf-8") as f:
    json.dump(cur, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"{KEY}: {old} -> {new}")
```

```bash
git show origin/production:tools/perf/perf_budgets.json > c:/tmp/prod_budgets.json
python c:/tmp/restore_budget.py
git diff --stat tools/perf/perf_budgets.json
```

기대 출력: `/erp/production/dashboard?view=fragment: 60021 -> 78218`, 1파일 변경.

⚠️ `json.dump`가 파일 전체를 재직렬화하므로 들여쓰기·키 순서가 원본과 달라질 수 있다. `git diff`로 **`body_bytes_max` 한 줄만 바뀌었는지 반드시 확인**하고, 다른 줄이 대량으로 바뀌었으면 되돌린 뒤 해당 한 줄만 손으로 고친다.

커밋 메시지(UTF-8 파일):
```
chore(perf): production 대시보드 wire 예산 재시드 복원 (60021→78218)

production 브랜치의 676939c8이 데이터 드리프트로 재시드한 값이 deploy로
역병합되지 않아, 전체 승격의 트리 치환으로 되돌아갔다. 승격 PR의 perf-gate가
이 경로에서 실패하므로(당시 관측 60168 > 60021) 운영 정본 값을 복원한다.
```

```bash
git add tools/perf/perf_budgets.json
git commit -F <메시지파일경로>
```

**완료 기준:** `git write-tree` 결과가 Step 5 이전에 `origin/deploy^{tree}`와 일치했고, 브랜치에 커밋 2개(머지 + 예산 복원)가 있다.

---

## Task 4: Railway PostgreSQL 스냅샷 (DB 되돌리기 유일 수단)

**Files:** 없음 (Railway 콘솔 작업)

리스크 2에 따라 **마이그레이션 #18 이후로는 alembic 롤백이 불가능하다.** 이 단계를 건너뛰면 DB를 되돌릴 방법이 없다.

- [ ] **Step 1: 스냅샷 생성**

Railway 대시보드 → `FOMS-PRODUCTION` → `Postgres` 서비스 → Backups → 수동 스냅샷 생성.
(저장소에 스크립트화된 백업 도구는 없다. `DECISIONS.md` 2026-06-05 기준 정본 백업 = Railway 자체 스냅샷.)

- [ ] **Step 2: 스냅샷 시각·ID 기록**

생성 완료된 스냅샷의 타임스탬프를 이 플랜 실행 로그에 적는다. T6 이후 문제 발생 시 복원 기준점이다.

- [ ] **Step 3: 현재 alembic 리비전 기록**

```bash
cd "<scratch>/prodlink"   # DATABASE_PUBLIC_URL이 dsn.txt에 있는 디렉토리
python q.py av.sql        # SELECT version_num FROM alembic_version
```

기대: `phase_0a_notif_user_states`. 이 값이 롤백 목표 리비전이지만, #18의 `downgrade()`가 `pass`라 alembic으로는 도달할 수 없다 — 스냅샷 복원이 실제 경로다.

**완료 기준:** 스냅샷 존재 확인 + 시각 기록 + 현재 리비전 `phase_0a_notif_user_states` 확인.

---

## Task 5: PR 생성 · perf-gate 통과

**Files:** 없음

- [ ] **Step 1: 브랜치 push**

```bash
cd c:/tmp/foms-prod-full
git push -u origin HEAD:refs/heads/promote/full-deploy-<DEPLOY_SHA>
```

- [ ] **Step 2: PR 생성**

```bash
gh pr create --base production --head promote/full-deploy-<DEPLOY_SHA> \
  --title "merge: deploy 전체 승격 → production (HEAD <DEPLOY_SHA>, 342커밋)" \
  --body-file <본문파일>
```

PR 본문에 반드시 포함할 것: 승격 커밋 수·파일 수, 마이그레이션 29개와 신규 테이블 39개, 확정 리스크 3개(락 구간·비가역 지점·예산 분기와 그 대응), T4 스냅샷 시각, T2의 CI green 근거.

- [ ] **Step 3: perf-gate 결과 확인**

```bash
gh pr checks <PR번호>
```

`perf-gate (staging)`가 유일한 체크다(ci.yml·harness-ci.yml·postgres-lane.yml은 `production`을 트리거에 넣지 않는다).

**red일 경우**: 예산 파일 헤더 주석 규칙(`--seed`는 의도된 성능 변화 때만, diff 리뷰 필수)에 따라 판단한다. 데이터 가변 탭의 드리프트면 관측×1.3 재시드, 코드성 회귀면 근본 수정. **TTFB 예산 완화로 회귀를 덮는 것은 금지**(정책 위반으로 되돌려진 이력 있음).

- [ ] **Step 4: PR #34 정리**

deploy에 이미 `7be8dbe7`(푸시 게이트)이 포함돼 있으므로 전체 승격이 PR #34를 포함한다. 중복 반영을 막기 위해 #34를 닫는다.

```bash
gh pr close 34 --comment "전체 승격 PR #<번호>에 포함되어 중복이므로 닫습니다."
```

**완료 기준:** PR 생성됨, `perf-gate` green, PR #34 closed.

---

## Task 6: 머지 (⛔ 사용자 승인 게이트)

**Files:** 없음

**이 단계부터 되돌리기가 어렵다.** 진행 전 사용자에게 다음을 보고하고 명시 승인을 받는다:

- 현재 시각이 업무 시간 외인가 (리스크 1의 `orders` 락 구간 때문)
- T4 스냅샷이 존재하는가
- perf-gate가 green인가
- **타 세션 작업 포함 확인**: 342커밋에는 이 세션이 만들지 않은 다른 작업 창의 커밋이 다수 포함된다(AS 일정 매칭 링크, 출고 AS 추천, 실측 대시보드 개편 등). 그 작업들이 운영에 나갈 준비가 됐는지는 이 세션이 판단할 수 없다.

- [ ] **Step 1: 승인 후 머지**

```bash
gh pr merge <PR번호> --merge
```

`--squash`/`--rebase` 금지 — 트리동일 머지 커밋 구조를 보존해야 전례와 동일한 형태가 된다.

- [ ] **Step 2: production HEAD 확인**

```bash
cd c:/DEV/FOMS
git fetch origin production
git log --oneline -2 origin/production
git diff --stat origin/production origin/deploy | tail -1
```

기대: 마지막 diff가 perf 예산 1줄 차이만 남거나 빈 출력.

**완료 기준:** 머지 완료, production HEAD가 승격 커밋.

---

## Task 7: 마이그레이션 실행 확인

**Files:** 없음

마이그레이션은 Railway `preDeployCommand`(`railway.toml:12` → `predeploy.sh`)가 **배포당 1회, replica 기동 전** 자동 실행한다. 수동 트리거는 필요 없다. `predeploy.sh`는 `set -e`라 실패 시 새 배포가 라이브되지 않는다(fail-closed).

- [ ] **Step 1: Railway 배포 로그에서 마이그레이션 완료 확인**

Railway 대시보드 → `FOMS-PRODUCTION` → `web` → Deployments → 최신 배포의 preDeploy 로그.

기대 문자열: `[predeploy] Migrations complete.`

**실패 시**: 배포가 라이브되지 않으므로 운영은 구버전으로 계속 동작한다(안전측). 로그의 실패 마이그레이션을 확인하고 T10 롤백 판단으로 간다.

- [ ] **Step 2: alembic 리비전 전진 확인**

```bash
cd "<scratch>/prodlink"
python q.py av.sql
```

기대: `wiz_pending_00`

- [ ] **Step 3: 신규 테이블·컬럼 생성 확인**

```sql
SELECT count(*) FROM information_schema.tables
 WHERE table_schema='public' AND table_type='BASE TABLE';
SELECT count(*) FROM information_schema.columns
 WHERE table_name='orders' AND column_name='mutation_version';
```

기대: 테이블 45 → **84** (45 + 39), `mutation_version` 컬럼 1개.

- [ ] **Step 4: INVALID 인덱스 확인 (리스크 2 부수 위험)**

```sql
SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
 WHERE NOT i.indisvalid;
```

기대: **0행**. 행이 나오면 `CREATE INDEX CONCURRENTLY` 실패 잔재다 — `IF NOT EXISTS`라 재배포로 자동 복구되지 않으므로, 해당 인덱스를 수동 `DROP INDEX` 후 재생성해야 한다.

**완료 기준:** 리비전 `wiz_pending_00`, 테이블 84개, `mutation_version` 존재, INVALID 인덱스 0개.

---

## Task 8: 배포 후 스모크

**Files:** 없음

- [ ] **Step 1: CI 감시 (논블로킹)**

```bash
cd c:/DEV/FOMS
python tools/harness/ci_watch.py $(git rev-parse origin/production) production
```

production 브랜치는 코드 CI 워크플로 트리거가 없으므로 "green by absence"가 정상이다. perf-gate만 확인된다.

- [ ] **Step 2: 기본 스모크**

```powershell
powershell -NoProfile -File scripts/ops/incident_smoke.ps1 `
  -BaseUrl https://lahom-production.up.railway.app `
  -Username <운영계정> -Password <비밀번호>
```

검증: `/debug-redirect`, `/login`, `/debug-db`, 로그인 후 `/`가 주문 목록인지.

- [ ] **Step 3: cron 서비스 확인**

```powershell
powershell -NoProfile -File scripts/ops/verify_foms_cron_prod.ps1
```

읽기 전용 dry-run이다. cron이 gunicorn을 띄우는 오설정이 아닌지 확인한다.

**완료 기준:** 스모크 전 항목 통과, cron 정상.

---

## Task 9: 사고 원인 실동작 확인 (이번 릴리스의 목적)

**Files:** 없음 (운영 브라우저 확인)

- [ ] **Step 1: 서빙 중인 JS에 게이트가 들어갔는지**

```bash
curl -s https://lahom-production.up.railway.app/static/js/orders/erp-order-shared.js \
  | grep -c "fomsErpAutosave.isDirty()"
```

기대: 2 이상(푸시 게이트 + 탭 복귀 가드).

- [ ] **Step 2: 캐시 핀 반영 확인**

```bash
curl -s -H "Cookie: <세션쿠키>" https://lahom-production.up.railway.app/edit/4414 \
  | grep -o "erp-order-shared.js?v=[0-9a-z]*"
```

기대: `?v=20260730c` (T3 시점 deploy 값). 구 핀이면 SW 캐시 문제이므로 실기기에서 강제 새로고침 후 재확인한다.

- [ ] **Step 3: 푸시 게이트 실동작 (수동)**

운영에서 테스트 주문 하나를 열고 → 아무 필드를 수정 → **저장하지 않고** 채널톡 푸시 버튼 클릭 → **"저장되지 않은 변경이 있습니다" 확인창이 뜨는지** 확인. 취소를 누르면 푸시가 나가지 않아야 한다.

⚠️ 실제 채널톡 발송이 일어나므로 **실주문이 아닌 테스트 주문**으로 하고, 확인창에서 **취소**를 눌러 발송을 막는다.

- [ ] **Step 4: If-Match 실동작 (수동)**

같은 주문을 브라우저 탭 2개로 연다 → 탭 A에서 필드 수정 후 저장 → 탭 B에서 다른 필드 수정 후 저장 → **"다른 사용자가 이 주문을 먼저 수정했습니다" 확인창**이 뜨고, 취소 시 탭 B의 입력이 화면에 그대로 남는지 확인한다.

- [ ] **Step 5: 주문 4414 데이터 복구**

채널톡 원문 기준으로 누락분을 재입력한다: **항목견적 1,828,560 / 할인 11,060 / 주소 `(공실)`**. 저장 후 `structured_data`에 반영됐는지 DB로 확인한다.

**완료 기준:** Step 1~2 자동 확인 통과, Step 3~4 확인창 동작, 4414 복구 완료.

---

## Task 10: 신규 운영 서비스 등록 (릴리스 후, 선택이나 권장)

**Files:** 없음 (Railway 대시보드 작업)

두 파일 모두 주석에 "서비스 provisioning/등록은 오케스트레이터 몫"이라고 명시돼 있다 — **자동 활성화되지 않는다.**

- [ ] **Step 1: receipt purge cron 등록**

Railway → `FOMS-PRODUCTION` → New Service → Settings → Config Path = `railway-cron-receipt-purge.toml`
(`order_mutation_receipts` 7일 보존 정리, UTC 17:30 = KST 02:30)

**미등록 시**: 즉각 장애는 아니고 `order_mutation_receipts` 테이블이 무기한 누적된다. If-Match를 켠 이번 릴리스에서 이 테이블에 매 저장마다 행이 쌓이므로 방치하면 서서히 커진다.

- [ ] **Step 2: side-effect outbox 워커 등록**

Railway → New Service → Config Path = `railway-domain-sidefx.toml`

**미등록 시**: `domain_side_effect_outbox`에 PENDING 행이 누적된다. 현재 설계상 legacy 경로로 실효과는 계속 발생하므로 즉각 장애는 아니지만(코드 주석 근거, 오너 확인 미완), 누적은 정리되지 않는다.

- [ ] **Step 3: 누적 모니터링 기준선 기록**

```sql
SELECT count(*) FROM order_mutation_receipts;
SELECT count(*) FROM domain_side_effect_outbox;
```

등록을 미루기로 했다면 이 값을 기록하고 주기적으로 재확인한다.

**완료 기준:** 두 서비스 등록 완료, 또는 미등록 결정 + 기준선 기록.

---

## 롤백

### 코드 롤백
force-push·reset은 로컬 guard(`deny`)와 GitHub(`allow_force_pushes: false`)로 이중 차단돼 있다. **revert PR이 유일한 정규 경로다.**

```bash
cd c:/DEV/FOMS
git fetch origin production
git worktree add -B revert/full-deploy c:/tmp/foms-revert origin/production
cd c:/tmp/foms-revert
git revert -m 1 <머지커밋SHA> --no-commit
git commit -F <메시지파일>
git push -u origin HEAD:refs/heads/revert/full-deploy
gh pr create --base production --head revert/full-deploy --title "revert: deploy 전체 승격 되돌리기" --body-file <본문>
```

⚠️ **코드만 되돌아가고 DB 스키마는 그대로 남는다.** 구 코드가 신규 컬럼·테이블을 모르는 것은 문제없지만(additive), `orders.mutation_version`은 NOT NULL에 server_default가 있어 구 코드의 INSERT도 통과한다. 즉 **코드 revert만으로 대부분의 상황이 수습된다.**

### DB 롤백
- alembic downgrade는 **#18 `startup_schema_00`에서 막힌다**(`downgrade()` = `pass`). 그 아래로 되돌릴 수 없다.
- 실제 경로는 **T4에서 만든 Railway 스냅샷 복원**이다. 복원하면 스냅샷 시각 이후의 **모든 운영 데이터가 유실**되므로, 데이터 손상이 아닌 한 코드 revert를 먼저 시도한다.
- 저장소에 스크립트화된 DB 롤백 런북은 없다.

---

## 미확인 / 사람 결정 필요

| 항목 | 상태 |
|---|---|
| 백필 7종 실행 수단 부재 | `item_id_00`·`task_backfill_00`·`production_backfill_00`·`as_backfill_00`·`construction_backfill_00`·`drawing_revision_00`·`wdc_link_backfill_00`이 스키마만 만들고, 대응 CLI가 `tools/ops/`에 없으며 모듈에 `__main__`도 없다(확인함). 신규 테이블이 **빈 채로 남는다**. dev도 같은 상태로 동작 중이라 graceful degradation으로 보이지만 **오너 확인 필요**. |
| `item_id_00` / `task_backfill_00`의 NOT NULL 승격 마이그레이션 | 아직 존재하지 않는다(각 파일이 `can_enforce_not_null` 게이트를 언급). 이번 릴리스 범위 밖. |
| SIDEFX outbox pre-cutover 정책 | 워커 미기동 시 legacy 경로로 실효과가 유지된다는 판단은 코드 주석 근거이며 오너 확인 미완. |
| perf-gate를 GitHub required status check로 승격할지 | 현재 `required_status_checks: null`이라 red여도 머지 가능하다. 저장소 설정 변경 사항이라 사람 판단. |
| 역할·권한 회귀 검증 절차 | 승격 후 role/permission 회귀를 검증할 표준 체크리스트가 저장소에 없다. 현재는 `scripts/ops/check_admin.py`(admin 계정만). |
| `FOMS_TRUSTED_PROXY_HOPS` | 미설정(기본 `"1"` = 현행과 byte-identical). 코드 주석이 실측 홉 수 설정을 권고하나 회귀는 없다. |
