# 로드맵 — 네이버 체인 전량 승격 (production `57cc536d` ← deploy `b8921291`)

- **상태**: 설계 확정 대기(사용자 승인 필요 — §9)
- **작성 시각**: 2026-08-25 KST
- **작성 워크트리**: `c:/tmp/foms-road` (detached HEAD = `origin/production` tip)
- **이 문서의 범위**: **종합·설계뿐이다.** 코드를 고치지 않았고 커밋·푸시·머지·cherry-pick 을
  하지 않았다. 운영 DB 에 읽기조차 하지 않았다(자격증명 미사용). 이 세션의 파일 변경은
  **이 문서 1개**이며, 병합 검증은 워킹트리를 건드리지 않는 `git merge-tree --write-tree`
  (가상 머지)로만 했다. 작업 종료 시 `git status --porcelain` = 0 줄.
- **입력**: 6개 그룹 조사 보고(G1~G6) + 적대 검증 3건 + 위험 CEO 판정 + 실행 CEO 판정.
  **두 CEO 는 일부러 반대 방향으로 보게 한 산출물이다.** 이 문서는 그 둘을 대조해
  충돌을 판정한 결과이며, 어느 한쪽의 결론을 그대로 승계하지 않았다.

---

## 0. 한 문단 요약

지금 운영을 막고 있는 것은 **충돌 25개가 아니다.** 3자 집합을 직접 계산한 결과
production 이 병합에 기여하는 신규 내용은 **한 줄도 없고**(PROD-NEW = 0), production 에만
있는 파일도 **0개**다 — 따라서 올바른 병합 결과는 이미 CI 전량 green 인 `origin/deploy`
트리와 **바이트 동일**해야 하고, 충돌 해소는 "잘 섞기"가 아니라 "deploy 와 같아졌음을
증명하기" 문제로 바뀐다. 실제로 막고 있는 것은 두 가지다. 첫째, `orders.as_axis_status`
컬럼이 운영에 **존재하지만 전 행 NULL** 인데(운영 코드에 이 컬럼을 쓰는 자리가 0건, 마이그레이션도
백필하지 않는다) deploy 코드는 AS 대시보드·AS 지도의 모집단 술어를 그 컬럼의
`IS NOT NULL` 로 바꾼다 — 코드가 라이브되는 순간 **AS 목록과 AS 지도가 통째로 빈다.**
둘째, 가상 머지 실측 결과 충돌이 **안 난** 파일 하나(`tests/domains/test_as_timeline_wiring.py`)에서
git 이 양쪽을 다 살려 **함수 정의가 중복 생성**되는데, 이 저장소 CI 에는 파이썬 린터가 없어
**아무 게이트도 이것을 잡지 못한다.** 두 문제 모두 해법이 확정돼 있다 — 코드 승격 **전에**
운영 DB 에 백필 스크립트를 1회 돌리고(현 운영 코드가 그 컬럼을 안 읽으므로 채워도 화면 무변동),
충돌 25개 + 조용한 중복 1개 = **26개 파일을 전부 deploy 판으로 채택한 뒤 트리가 deploy 와
동일함을 증명**하면 열린다.

---

## 1. 실측값 (전부 이 워크트리에서 직접 실행한 명령의 출력)

### 1.1 규모

| 항목 | 명령 | 실측 |
|---|---|---|
| `origin/production` | `git ls-remote origin refs/heads/production` | `57cc536d` (브리프와 일치) |
| `origin/deploy` | `git ls-remote origin refs/heads/deploy` | `b8921291` (브리프와 일치) |
| 미승격 커밋 | `git rev-list --count origin/production..origin/deploy` | **485** |
| 운영 전용 커밋 | `git rev-list --count origin/deploy..origin/production` | **74** |
| └ 머지 커밋 | `--merges` | 28 |
| └ 내용 커밋 | `--no-merges` | **46** |
| └ 고유 내용을 가진 머지(evil merge) | `git show --cc` 28건 전수 | **0** |
| 전체 diff | `git diff --shortstat origin/production origin/deploy` | **262 files, 48866 insertions(+), 761 deletions(-)** |

### 1.2 3자 집합 — 이 승격의 성격을 결정하는 표

merge-base = `63737e91`.

| 측정 | 명령 | 실측 | 뜻 |
|---|---|---|---|
| production 쪽만 변경된 파일 | `comm -23` (prod변경 126 · deploy변경 347) | **0** | 운영이 단독으로 고친 파일이 없다 |
| production 쪽 삭제 파일 | `git diff --diff-filter=D --name-only $MB origin/production` | **0** | 운영이 지운 파일이 없다 |
| production 트리에만 있는 파일 | `comm -23` (ls-tree) | **0** (2962 ⊂ 3117) | 파일이 통째로 사라지는 경로 없음 |
| deploy 트리에만 있는 파일 | `comm -13` | 155 | 전량 머지로만 안전하게 착지 |
| prod↔deploy 내용이 다른 파일 | `git diff --name-only` | 262 | |
| └ 양쪽 변경 + 差異 | `comm -12` | 41 | |
| └ 충돌 25개 제외한 **무등급 사각** | `comm -23` | **16** | 아무도 등급을 안 매긴 구간 |
| 그 16개의 production 고유 신규 줄 | merge-base 3자 대조 | **PROD-NEW = 0** (MB-leftover 25) | 운영 핫픽스 소실 후보 0 |

> **이 표가 로드맵 전체의 근거다.** production 이 병합에 기여하는 신규 내용이 0 이므로,
> 올바른 병합 결과는 `origin/deploy` 트리와 동일하다. 그 트리는 이미 CI green 이다(§1.4).

### 1.3 판정 등급 집계

충돌 25개에 대한 G1~G6 등급(내가 표본 재검증한 값):

| 등급 | 건수 | 승격 처리 |
|---|---|---|
| `SUPERSET` | **19** | deploy 채택 안전 |
| `REGENERATE` | **4** | deploy 채택 후 `--check` 로 무드리프트 확인 |
| `TRIVIAL` | **2** | deploy 채택(주석·docstring뿐) |
| `PRODUCTION_ONLY` | **0** | — |
| `UNKNOWN` | **0** | — |
| 커밋 매핑 | 내용 커밋 46건 중 mapped **46 / unmapped 0** | |

여기에 **이 문서가 새로 추가한 1건**(§2.4):

| 등급 | 건수 | 비고 |
|---|---|---|
| 비충돌·조용한 keep-both 중복 | **1** | `tests/domains/test_as_timeline_wiring.py` — 어떤 게이트도 못 잡음 |

→ **승격 시 deploy 판으로 채택해야 하는 파일은 25개가 아니라 26개다.**

### 1.4 deploy tip 의 CI 상태 (등가성 전략의 근거)

```
gh run list --branch deploy --limit 15 --json workflowName,conclusion,headSha
```

| SHA | 워크플로 | 결과 |
|---|---|---|
| `b8921291` | FOMS CI | **success** |
| `b8921291` | Harness CI | **success** |
| `b8921291` | FOMS PostgreSQL Lane | **success** |
| `5d8db32b` | perf-gate (staging) | **success** |

`b8921291` 에 perf-gate 가 없는 이유는 `paths-ignore`(docs/**·**/*.md) 다. 실측으로
`git diff --name-only 5d8db32b b8921291 | grep -vE "^docs/|\.md$"` → **무출력(exit 1)** =
마지막 perf-gate 실행(`5d8db32b`) 이후 **코드가 한 줄도 안 바뀌었다.** 따라서 perf-gate green
도 `b8921291` 의 코드에 유효하다.

### 1.5 CI 트리거 사각 (YAML 실측)

| 워크플로 | production PR 에서 | 근거 |
|---|---|---|
| FOMS CI (전체 pytest) | **안 돎** | `branches: [ "main", "deploy" ]` |
| Harness CI | **안 돎** | `branches: ["main", "deploy"]` |
| FOMS PostgreSQL Lane | 돎 | `branches: [ "main", "deploy", "production" ]` |
| perf-gate (staging) | 돎(**블로킹**) | `pull_request: branches: [production]` |

→ 승격 PR 은 4개 중 **2개만** 돈다. 기능 스위트 전량은 **로컬에서 대신 돌리는 것이 안전선**이다.

### 1.6 alembic 계보 — G6 의 이견 해소

| 항목 | 명령 | 실측 |
|---|---|---|
| production 트리 head | `ScriptDirectory.get_heads()` (워킹트리=production tip) | **`['merge_drawq_naverfail']`** 단일 |
| production 트리 리비전 수 | `walk_revisions()` | **85** |
| deploy 트리 | 파일집합 `diff` | **production 과 완전 동일** (파일명 집합 diff 무출력) |
| migrations 差異 | `git diff --stat -- migrations/` | 2파일, **docstring 뿐**(assort_00 +1 / notifrole_00 +1-8) |
| dangling parent | 그래프 전수 파싱 | **0** |

> **G6 의 open question 은 해소됐다.** G6 는 "운영 = `merge_prod_drawq` 라는 기록이 있다"고
> 이견을 남겼는데, 그 기록의 출처인 `2026-08-24-naver-production-promotion-chain_SPEC.md` 는
> **08-24 19:34 작성 = 스키마 선행 승격(`57cc536d`) 이전**이다. 지금 운영 트리의 권위 있는
> head 는 `merge_drawq_naverfail` 이고 브리프가 옳다. 단 **운영 DB 의 `alembic_version` 실값은
> 이 조사에서 확인하지 못했다**(DB 미접속) — S0 에서 사람이 1회 조회해야 한다.

### 1.7 인프라 파일 안전성

| 파일 | prod↔deploy |
|---|---|
| `requirements.txt` | **IDENTICAL** (과거 solapi 유형 사고 재발 없음) |
| `predeploy.sh` · `Procfile` · `railway.toml` · `app.py` · `static/sw.js` | **IDENTICAL** |
| `start.sh` | **DIFFERS** — 네이버 수집 루프 추가, `if [ "$FOMS_NAVER_SYNC_ENABLED" = "1" ]` 가드 + worker 서비스 안. 기본 off |

---

## 2. 두 CEO 판정 대조 — 충돌 지점과 판정

**충돌은 6건 있었다.** 아래는 각 충돌의 자리, 어느 쪽이 옳은지, 그 근거다.

### 2.1 【충돌 1 — 결정적】 `as_axis_status` 백필

| | 주장 |
|---|---|
| **위험 CEO** | R-1 차단급. 코드 승격 **전에** 운영 백필 필수. 안 하면 AS 대시보드·지도가 0건 = 8/14 증발 사고와 화면상 구분 불가 |
| **실행 CEO** | **백필이 계획 어디에도 없다.** S0 사전조건은 `alembic_version` 확인뿐이고, 4단계 어디에도 데이터 전제 항목이 없다 |

**판정: 위험 CEO 가 옳다.** 내가 직접 확인한 증거 4개:

1. **마이그레이션이 백필하지 않는다** — `asaxis_00_as_axis_status.py` docstring 원문:
   *"백필은 이 리비전이 아니라 ``tools/ops/backfill_as_axis_status.py`` 가 맡는다"*.
   `upgrade()` 본문은 `op.add_column` + `op.create_index` 뿐, UPDATE 0.
2. **운영 코드가 이 컬럼을 쓰지 않는다** —
   `git grep -nE "as_axis_status" origin/production -- foms/ tools/ scripts/` → **exit 1(무출력)**.
   대조군 `git grep -cE "as_axis_status" origin/production -- models.py` → **2** (매치 정상 발생).
   즉 무출력은 grep 오작동이 아니라 진짜 부재이며, 운영에는 값을 채우는 코드가 없다 → **전 행 NULL**.
3. **`predeploy.sh` 도 안 채운다** — `tools/ops/ensure_schema.py` 에 `as_axis_status` grep → exit 1.
4. **deploy 술어에 폴백이 없다** — `foms/services/as_dashboard_helpers.py:276-286`
   `def erp_as_scope_condition(): return Order.as_axis_status.isnot(None)`.

**영향 범위**(deploy 기준 호출부 전수):

| 파일 | 라인 | 화면 |
|---|---|---|
| `foms/web/cs/as_dashboard.py` | 171 · 212 · 263 | AS 대시보드 탭·카운트 |
| `foms/services/as_dashboard_read_model.py` | 61 · 65 | AS 읽기 모델 |
| `foms/services/map_snapshot.py` | 218 | **AS 미완료 지도** |

`map_snapshot.py` diff 는 `- query.filter(Order.status.in_(['AS','AS_RECEIVED','AS_COMPLETED']))`
→ `+ query.filter(erp_as_scope_condition())` 로 **모집단 술어 자체가 교체**된다.
규모는 `asaxis_00` docstring 기준 **3,551행 중 AS 566행**.

> **왜 실행 CEO 가 놓쳤나(구조적 이유 — 재발 방지용으로 남긴다).** 실행 CEO 의 전략은
> "트리가 deploy 와 같으면 deploy 의 CI green 이 그대로 이 트리의 green"이다. 그 추론은
> **코드 정합성에는 참이지만 데이터 전제에는 침묵한다.** CI 는 시드된 테스트 DB 위에서 돌고,
> 거기서는 `_fill_as_axis_status_on_insert` before_insert 훅이 INSERT 시점에 컬럼을 채우므로
> **deploy 의 green 은 이 결함을 구조적으로 드러낼 수 없다.** 등가성 논증의 사각이 정확히
> 여기이며, 그래서 등가성 게이트로 백필 조건을 대체할 수 없다.

**해소**: §5 S1(코드 승격 **전**, 별도 승인 필요).

### 2.2 【충돌 2】 인벤토리 — 재생성이냐 `--check` 냐

| | 주장 |
|---|---|
| **위험 CEO** | C5: 인벤토리 4종 **재생성** 후 커밋. `swallow_by_control_flow ≤ 180` 실측(R-9: 합본은 미측정) |
| **실행 CEO** | 재생성은 "고치는 단계"가 아니라 "검증 단계". `--check` 4종이 전부 exit 0 이어야 정상 |

**판정: 실행 CEO 가 옳다 — 단 순서 조건부.** 트리가 deploy 와 동일하면 커밋된 인벤토리 =
deploy 의 인벤토리 = 새 스캔 결과다(deploy 에서 `test_inventory_matches_fresh_scan` 이 green 이므로).
따라서 재생성은 **정의상 no-op** 이고, `--check` 는 더 강한 진술이다 — **드리프트가 나오면
등가성이 깨졌다는 신호**이므로 조용히 고치는 대신 중단해야 한다. 재생성은 그 신호를 덮어버린다.

이 판정은 **위험 CEO 의 R-9(swallow baseline 180 초과 미측정)도 함께 해소한다**: 합본 트리 =
deploy 트리이므로 `swallow_by_control_flow` 는 deploy 의 값(180)이지 새 값이 아니다.

**단서**: 이 논증은 **등가성이 증명된 뒤에만** 성립한다. 그래서 §5 는 등가성 증명(S2.4)을
`--check`(S2.5)보다 **앞에** 둔다. 도구 실측: 4종 전부 `--check` 플래그 보유
(`failopen_scan`·`audit_coverage_scan`·`order_mutation_writer_scan`·`state_writer_scan` 각 1건).
`foms_write_guard_manifest.json`·`foms_order_mutation_policy_manifest.json` 2종은 **생성물이 아니라
수기 정본**이므로 스캐너를 돌리지 않는다(양 CEO 및 G2 일치).

### 2.3 【충돌 3】 충돌 해소 방식 — 실은 충돌이 아니다

위험 CEO C4 = "충돌 25개는 전량 deploy 채택 + 머지 결과 ≡ origin/deploy 증명".
실행 CEO = 동일. **두 CEO 는 여기서 수렴한다.**

진짜 충돌은 **두 CEO ↔ G1~G6 그룹 보고** 사이에 있다. 그룹 보고는 파일마다 `grep` 확인 명령을
지정했는데, 적대 검증이 그중 **2개가 항상 실패하는 명령**임을 증명했고(§11), 나도 세 번째를
찾았다(§2.6). **파일별 grep 프로토콜은 폐기하고 등가성 게이트 1개로 대체한다** — 이것이
두 CEO 의 공통 결론이며 나도 동의한다.

### 2.4 【충돌 4 — 내가 새로 찾은 것】 등가성 게이트의 통과 기준이 틀렸다

| | 주장 |
|---|---|
| **실행 CEO** | 충돌 25개를 `--theirs` 로 풀면 `git diff --stat b8921291` 이 **무출력**이어야 한다. 아니면 중단 |
| **위험 CEO** | R-2: 3-way 머지는 비충돌 파일에서 양쪽을 다 채택해 조용한 중복을 만든다(근거로 `foms/web/admin/__init__.py` 이중 import 제시) |

**판정: 둘 다 절반씩 맞다. 실측으로 확정했다.**

워킹트리를 건드리지 않는 가상 머지를 돌렸다:

```bash
git merge-tree --write-tree --name-only origin/production origin/deploy
```

- 충돌 파일 목록 = **25개, 브리프의 25개 목록과 exact match**(`diff` 무출력). 브리프 수치 독립 확인.
- 산출된 머지 트리 `0513b16c` 를 deploy 트리와 비교:
  `git diff --name-only 0513b16c origin/deploy^{tree}` → **26개 파일**.
- 그중 충돌 25개를 뺀 나머지 = **1개: `tests/domains/test_as_timeline_wiring.py`**

그 파일의 실제 내용:

```
merged tree: def test_as_attachment_order_script_is_version_pinned_and_deferred()  → 933행, 942행 (2회)
origin/deploy:  같은 grep → 1
origin/production: 같은 grep → 1
```

**양쪽에 1개씩 있던 동일 함수가 서로 다른 위치에 있어 머지가 둘 다 살렸다.** 위험 CEO 의
R-2 메커니즘이 실제로 발현한 자리다.

**이것이 왜 위험한가 — 어떤 게이트도 못 잡는다:**

- 파이썬은 중복 정의를 에러로 보지 않는다(뒤 정의가 앞을 가린다). 두 정의가 **동일 본문**이라
  테스트 결과도 안 바뀐다 → **pytest 로 안 잡힌다.**
- CI 에 파이썬 린터가 없다(F811 미검출). `ci.yml` 의 lint 는 `tools/design/ssot_lint.py docs/design`
  **하나뿐**이고, `pre_push_smoke.ps1` 도 동일한 design SSOT lint 뿐이다.
- 즉 이 중복은 **조용히 운영 저장소에 착지한다.**

**두 CEO 판정에 대한 귀결:**

1. 위험 CEO R-2 는 **실재한다**(추상적 우려가 아니었다). 다만 제시한 근거였던
   `foms/web/admin/__init__.py` 이중 import 는 **이미 `origin/deploy` 자체에 있는 선재 결함**이다
   (deploy 5·6행에 2회, CI green 상태로 존재) — 머지가 만드는 것이 아니다. 근거는 빗나갔고
   결론은 옳았다.
2. 실행 CEO 의 통과 기준 "무출력"은 **그대로는 달성 불가능**하다. 자기 중단 조건에 걸려
   S1.4 에서 멈추거나, 더 나쁘게는 작업자가 "설명되는 차이"로 치부하고 넘어간다.
3. **수정된 기준**: 충돌 25개 + 이 1개 = **26개를 deploy 판으로 채택**하면 그때 무출력이 된다.
   그 파일은 `PROD-NEW = 0`(고유 4줄 전부 merge-base 유래)이라 deploy 채택으로 잃는 것이 없다.

### 2.5 【충돌 5】 롤백 순서

| | 주장 |
|---|---|
| **위험 CEO** | 1차 = Railway 이전 배포 되돌리기, 2차 = `git revert -m 1`. **revert-of-revert 함정**을 사전 합의하라 |
| **실행 CEO** | `git revert -m 1 <머지SHA>` push, force-push 금지. Railway·revert-of-revert 언급 없음 |

**판정: 위험 CEO 가 더 완전하다. 채택한다.** Railway 이전 배포는 git 이력을 건드리지 않아
가장 빠르고 부작용이 없다. `git revert -m 1` 을 쓰면 이후 재승격 시 git 이 "이미 머지됨"으로
보아 **아무 파일도 안 들어오는 조용한 실패**가 나므로, 그 경우 revert 를 다시 revert 해야 한다.
실행 CEO 의 "force-push 금지"는 유지한다(보호 브랜치 강제푸시는 `guard_policy.py` 훅이 차단).

### 2.6 【충돌 6】 실행 CEO 가 인용한 CI 확인 명령이 작동하지 않는다

실행 CEO 는 `gh run list --commit b8921291` 의 출력으로 3개 green 을 제시했다.
**결론은 맞지만 명령은 이 환경에서 작동하지 않는다:**

```
gh run list --commit b8921291 --limit 20 --json ...   → []      (빈 배열)
gh run list --commit 5d8db32b --limit 5               → (무출력)  ← 대조군도 빈다 = 플래그 자체가 불가용
gh auth status                                        → ✓ Logged in (lahomsystem)
```

인증은 정상이므로 `--commit` 플래그가 이 gh 버전에서 무용이다. **대체 명령**(실측으로 green
확인에 성공한 것)은 `gh run list --branch deploy --limit 15 --json workflowName,conclusion,headSha`
후 headSha 로 거르는 방식이다. 이는 적대 검증이 잡은 G3·G5 의 깨진 명령에 이은 **세 번째
"항상 빈 결과를 내는 검증 명령"** 이다 — §7 의 게이트는 전부 이 관점에서 다시 썼다.

### 2.7 충돌하지 않은 것 (대조 후 확인)

| 항목 | 두 CEO |
|---|---|
| CI 트리거 사각(production PR 은 2개만) | **일치** — 로컬 전량 실행이 안전선 |
| 충돌 25개 전량 deploy 채택 | **일치** |
| `Running upgrade` 0줄이 정상 | **일치** |
| deploy tip 이동 레이스 / SHA 고정 | **일치**(위험 C3 = 실행 §4) |
| 매니페스트 2종은 스캐너 금지 | **일치** |
| 네이버는 env 부재로 호출 0 | **일치** |

---

## 3. 차단 사유

### 3.1 형식 등급으로는 차단 0건

`PRODUCTION_ONLY` = **0**, `UNKNOWN` = **0**. 충돌 25개 전부 deploy 채택으로 해소되고,
내용 커밋 46건이 전부 deploy 에 대응물을 가진다(mapped 46 / unmapped 0).
**전량 승격으로 잃는 것의 총량은 문서 문구 약 12줄 + 한글 주석 9줄이며 전부 런타임 0 이다.**

### 3.2 그러나 실질 차단은 2건이다

등급 체계는 "충돌 파일의 내용 소실"만 본다. 아래 둘은 그 체계 밖에 있고, 둘 다 **차단급**이다.

| # | 차단 사유 | 성격 | 왜 등급 체계가 못 잡나 | 해소 |
|---|---|---|---|---|
| **B-1** | `orders.as_axis_status` 전 행 NULL 위에 새 모집단 술어가 얹힌다 → AS 대시보드 탭·AS 미완료 지도 **0건** | **데이터 전제** | 충돌 파일이 아니고, 코드 대조로는 보이지 않는다. deploy CI 는 시드 DB + before_insert 훅이라 구조적으로 재현 불가 | §5 **S1** — 코드 승격 **전** 백필 1회(+승격 직후 1회 더). 현 운영 코드가 이 컬럼을 안 읽으므로 미리 채워도 화면 무변동 |
| **B-2** | 비충돌 파일 `tests/domains/test_as_timeline_wiring.py` 에 머지가 함수 정의를 **중복 생성** | **머지 아티팩트** | 충돌 목록 25개 밖. pytest·CI 린트 어느 쪽도 검출 못 함(파이썬 린터 부재) | §5 **S2.3** — 이 파일도 deploy 판으로 명시 채택(총 26개). §7 등가성 게이트가 재발 감시 |

### 3.3 차단은 아니지만 승인 시 인지해야 할 것

| # | 내용 | 근거 |
|---|---|---|
| A-1 | **변경 사유 모달이 전 사용자에게 첫날부터** 뜬다(플래그 없음) — `foms/services/orders/change_reason.py` 에 `getenv`·`feature_flag` 0건. 단 사유는 저장 **후** 24시간 창에 붙이는 구조라 **저장은 막히지 않는다** | grep 실측 |
| A-2 | nav 에 "네이버 수집" 탭 + 확인 대기 배지가 뜬다. 트리아지 화면은 `role_required(["ADMIN","MANAGER","STAFF"])` 로 STAFF 까지 열리고, 워크벤치 게이트 off 이면 **옛 화면이 빈 큐로 렌더**된다(에러 아님). "지금 수집"은 `role_required(["ADMIN"])` 이라 STAFF 는 누를 수 없다 — 위험 CEO 의 "STAFF 가 버튼 누르면 에러"는 **과장이다** | `naver_ingest.py:379`(ADMIN) · `:718`(STAFF+) · `feature_flags.py:308` |
| A-3 | `layout_scripts.html` 이 **전 페이지 공통** 전역 스크립트 3종을 새로 싣는다 → 로드 그래프 변화 | G5 |
| A-4 | 승격 대상의 상당수가 **당일(08-24 20:57~22:27) 코드**다. 스테이징 육안 확인만 거쳤다 | 위험 CEO R-4, `git log` |
| A-5 | `models.py` deploy 채택으로 `_fill_as_axis_status_on_insert` before_insert 훅이 켜져 **모든 신규 Order INSERT** 가 유도 함수를 한 번 더 탄다. 값 명시 시 조기 return, before_update 미부착 | G6 |

---

## 4. 충돌 파일 처리표 (25 + 1 = **26**)

**전부 deploy 판 채택.** "잃을 수 있는 것"은 G1~G6 이 근거를 붙여 확인한 것만 적었다.

| # | 경로 | 판정 | 처리 | 잃을 수 있는 것 |
|---|---|---|---|---|
| 1 | `docs/AI_CHANGELOG.md` | TRIVIAL | deploy 채택 | 운영 NOTIF-ROLE 행 1줄(`운영 계보 기준 부모는 assort_00` — 승격 후 **거짓이 되는 서술**), 07-23 보일러플레이트 2행, 검증 수치 1행. 같은 사실이 AI_STATUS·ledger 에 생존 → 저장소 정보 손실 0 |
| 2 | `docs/AI_STATUS.md` | SUPERSET | deploy 채택 · **keep-both 절대 금지** | 운영 L3·L11 2줄. keep-both 시 head40 = **4187자 > 4000** 계약 위반 → `test_hook_log_hygiene` red(실측) |
| 3 | `docs/harness/foms_audit_coverage_inventory.json` | REGENERATE | deploy 채택 후 `--check` | 없음(ONLY-IN-PROD = 0) |
| 4 | `docs/harness/foms_failopen_inventory.json` | REGENERATE | deploy 채택 후 `--check` | 없음(FEWER-in-deploy 0건) |
| 5 | `docs/harness/foms_order_mutation_policy_manifest.json` | SUPERSET | deploy 채택 · **스캐너 금지(수기 정본)** | 없음(prod 전용 route 키 0, 값 차이 0) |
| 6 | `docs/harness/foms_order_mutation_writer_inventory.json` | REGENERATE | deploy 채택 후 `--check` | 없음 |
| 7 | `docs/harness/foms_state_writer_inventory.json` | REGENERATE | deploy 채택 후 `--check` | 없음(lineno 제외 시 양쪽 완전 동일) |
| 8 | `docs/harness/foms_write_guard_manifest.json` | SUPERSET | deploy 채택 · **스캐너 금지(수기 정본)** | 없음 |
| 9 | `docs/plans/2026-08-20-notifrole-progress-ledger.md` | SUPERSET | deploy 채택 | T-G `PENDING` 행 1줄 — deploy 에서 `DONE` 으로 갱신된 같은 행. 되살리면 끝난 승격이 PENDING 으로 되돌아가는 **오기록** |
| 10 | `foms/api/erp_orders_structured.py` | SUPERSET | deploy 채택 | 없음(삭제 6줄 전부 확장 치환) |
| 11 | `foms/api/files/common.py` | SUPERSET | deploy 채택 | 없음(**삭제 0줄**) |
| 12 | `foms/api/files/direct_upload.py` | SUPERSET | deploy 채택 | 없음(삭제 3줄 = 함수명 교체) |
| 13 | `foms/api/files/order_routes.py` | SUPERSET | deploy 채택 | 없음(삭제 3줄 = 이름 교체) |
| 14 | `migrations/versions/assort_00_attachment_sort_order.py` | SUPERSET | deploy 채택 | 없음(docstring 1줄 추가, `revision`/`down_revision` 양쪽 동일) |
| 15 | `migrations/versions/notifrole_00_notification_target_role.py` | TRIVIAL | deploy 채택 | docstring 7줄(`부모는 브랜치별로 다르다` — **이미 거짓**) |
| 16 | `models.py` | SUPERSET | deploy 채택 | 한글 주석 2줄(`승격 주의…` — 전량 승격 후 거짓이 됨). 선언·제약·인덱스 소실 0(집합차분 확인) |
| 17 | `static/css/components/foms-as-attachment-order.css` | SUPERSET | deploy 채택 | 없음(**삭제 0줄**, 운영 89줄이 deploy 260줄의 바이트 동일 접두) |
| 18 | `static/js/cs/as-dashboard.js` | SUPERSET | deploy 채택 | 없음(-251줄은 `as-push-confirm.js` 로 **이동**, 24/24 토큰 대응 확인) |
| 19 | `templates/cs/partials/as_dashboard_body.html` | SUPERSET | deploy 채택 | 없음(핀도 deploy 가 최신 `20260820a` > 운영 `20260819a/b`) |
| 20 | `templates/orders/partials/erp_order_js.html` | SUPERSET | deploy 채택 — **관례 예외** | 없음. 저장소 관례("운영 목록 유지 + 내 핀만 범프")를 **적용하지 마라**: `comm -23`(prod−deploy) 무출력 = deploy 가 상위집합이라 손수 병합하면 신규 자산 5종이 누락된다 |
| 21 | `templates/partials/shared/layout_scripts.html` | SUPERSET | deploy 채택 · **수동 편집 금지**(계약이 인라인 강제) | 없음. 인라인 `<script>` 블록 prod 3 = deploy 3(외부화 회귀 없음) |
| 22 | `tests/domains/test_as_dashboard_attachment_modal.py` | SUPERSET | deploy 채택 | 없음(단언 전수 재조준 확인) |
| 23 | `tests/domains/test_erp_mobile_order_display.py` | SUPERSET | deploy 채택 | 없음(**삭제 0줄**, 순수 append) |
| 24 | `tests/domains/test_erp_order_shared_form_scripts.py` | SUPERSET | deploy 채택 | 없음(삭제 3줄 = 핀 assert 구버전) |
| 25 | `tests/visual/test_alimtalk_ui_contract.py` | SUPERSET | deploy 채택 | 없음(**삭제 0줄**) |
| **26** | **`tests/domains/test_as_timeline_wiring.py`** | **비충돌 · keep-both 중복** | **deploy 판 명시 채택** | 없음(`PROD-NEW = 0`). **방치 시** 함수 정의 2개 잔존 — 어떤 게이트도 검출 못 함 |

### 4.1 결합 제약 (한쪽만 운영 판으로 남기면 깨지는 묶음)

전량 deploy 채택이면 자동 충족되지만, **부분 cherry-pick 으로 방식이 바뀌면 이 표가 되살아난다.**

| 묶음 | 구성 | 깨질 때 증상 |
|---|---|---|
| 핀 계약 3+3 | #20 `erp_order_js.html` · #21 `layout_scripts.html` · #24 `test_erp_order_shared_form_scripts.py` **+** `erp_order_tab.html` · `erp_order_tab_mobile.html` · `erp_alimtalk_trace_modal.html` | 핀 assert CI red · ERP AS PUSH 런타임 불능. **뒤 3개는 G5 원보고에 빠져 있었고 적대 검증이 추가한 것** |
| AS 업로드 앵커 | #11 `common.py` · `foms/api/cs/as_orders.py` · `foms/services/orders/as_upload_anchor.py` | `import app` 은 통과하고 **AS 첨부 업로드만 런타임 500** |
| 변경 사유 | #10 `erp_orders_structured.py` · `foms/services/orders/change_reason.py` | 모듈 최상단 import → **부팅 파산** |
| AS PUSH 확인창 | #18 · #19 · `as-push-confirm.js` · `as_push_confirm_modal.html` | ERP 주문 편집 화면 **TemplateNotFound 500** |

---

## 5. 단계별 실행 순서

**코드는 쪼개지 않는다 — 전량 1커밋.** §4.1 의 하드 의존 때문에 파일 단위 분할은 파산한다.
대신 시간축으로 5단계로 나누고 커밋은 2개(코드 / 문서)로만 쪼갠다.

---

### S0 — 사전조건 (읽기 전용, 5분)

**무엇을**: 이 로드맵의 전제 4개가 아직 참인지 확인한다.

```bash
cd /c/tmp/foms-road && git fetch origin --quiet
git ls-remote origin refs/heads/production refs/heads/deploy
# 기대: production = 57cc536d… / deploy = b8921291…

gh run list --branch deploy --limit 10 --json workflowName,conclusion,headSha
# 기대: b8921291 의 FOMS CI · Harness CI · PG Lane 이 전부 success
# (--commit 플래그는 이 환경에서 항상 빈 결과다 — 쓰지 마라, §2.6)
```

운영 DB(읽기 전용, 사용자 승인 하에):

```sql
SELECT version_num FROM alembic_version;                        -- 기대: merge_drawq_naverfail 단일 행
SELECT count(*) FROM orders;                                    -- 기록해 둘 것
SELECT count(*) AS filled FROM orders WHERE as_axis_status IS NOT NULL;   -- 기대: 0 (백필 전)
SELECT to_regclass('public.external_order_links'), to_regclass('public.order_change_reasons');
```

**완료 판정**: 네 값이 전부 기대와 일치. `filled` 값을 **기록**(S4 대조용).
**롤백**: 해당 없음(읽기 전용). 불일치 시 **진입 거부** → §8.

---

### S1 — `as_axis_status` 백필 (운영 DB 쓰기, **별도 승인 필요**, 15분)

**무엇을**: B-1 해소. **코드 승격 전에** 한다 — 현 운영 코드는 이 컬럼을 읽지 않으므로
(§2.1 증거 2) 채워도 **운영 화면이 전혀 바뀌지 않는다.** 즉 이 단계는 되돌릴 필요조차 없다.

스크립트가 `foms.services.orders.state_axes` 를 import 하므로 **deploy 코드가 있는 워크트리에서**
실행해야 한다(S2 에서 만드는 승격 워크트리, 또는 `c:/tmp/foms-s-naver-ingest` 가 아닌 별도 트리).

```bash
# 1) dry-run — 무엇을 몇 건 바꿀지만 출력 (기본값이 dry-run 이다)
python tools/ops/backfill_as_axis_status.py --dsn "$PROD_DSN"

# 2) 적용
python tools/ops/backfill_as_axis_status.py --dsn "$PROD_DSN" --apply

# 3) 드리프트 0 확인
python tools/ops/audit_as_axis_drift.py --dsn "$PROD_DSN" --json
```

CLI 계약(실측): `--dsn` 필수 · `--apply` 없으면 dry-run · `--batch` 기본 200 배치 커밋 ·
`audit_as_axis_drift` 는 `--dsn` 필수 · `--json` 선택.

**완료 판정**
- dry-run 이 보고한 건수 ≈ AS 행 규모(참고: `asaxis_00` docstring 은 3,551행 중 AS 566행)
- `--apply` 후 `SELECT count(*) FROM orders WHERE as_axis_status IS NOT NULL` 이 **수백 건**
- `audit_as_axis_drift` **드리프트 0**
- **운영 AS 미완료/완료 탭 건수를 지금 기록**(승격 후 대조용 — 이 숫자가 S5 의 합격선이다)

**롤백**: 불필요. 옛 코드가 이 컬럼을 읽지 않으므로 값이 남아 있어도 무해하다.
(굳이 지우려면 `UPDATE orders SET as_axis_status = NULL` 이지만 **권장하지 않는다**.)

> **멱등이므로 S4 배포 직후 1회 더 돌린다** — S1~S4 사이에 발생한 AS 활동분을 덮기 위해.

---

### S2 — 병합 · 등가 증명 (로컬만, 원격 무영향, 25분)

**무엇을**: 승격 워크트리에서 병합하고, 결과 트리가 `b8921291` 트리와 **동일함을 증명**한다.

```bash
# 2.1 승격 전용 워크트리 (c:/tmp 짧은 경로. 공유 트리 C:\DEV\FOMS 오염 금지)
cd /c/tmp && git -C /c/DEV/FOMS fetch origin
git clone --shared /c/DEV/FOMS /c/tmp/foms-promote
cd /c/tmp/foms-promote && pwd          # ← 반드시 눈으로 확인
git checkout -B promote/full-20260825 57cc536d

export MSYS_NO_PATHCONV=1              # 없으면 origin/deploy:.github/... 경로가 깨진다(실측)

# 2.2 SHA 로 못박아 병합 (브랜치명 금지 — 타 세션 push 시 게이트가 조용히 거짓말한다)
git merge --no-ff b8921291

# 2.3 충돌 25개 + 조용한 중복 1개 = 26개를 deploy 판으로
git checkout --theirs -- $(git diff --name-only --diff-filter=U)
git checkout b8921291 -- tests/domains/test_as_timeline_wiring.py    # ← B-2 (§2.4)
git add -A

# 2.4 ★ 유일한 판정 게이트 ★
git diff --stat b8921291
```

**완료 판정**: **2.4 가 무출력.** 한 줄이라도 나오면 그 줄을 **전부 설명하기 전까지 전진 금지**.

> 이 게이트 하나가 파일별 grep 20여 개(그중 3개는 항상 빈 결과를 내는 깨진 명령이었다)를
> 대체하고, 3-way 머지의 keep-both 중복까지 잡는다. 실제로 이 조사에서 **그 방식으로만
> B-2 를 찾았다.**

```bash
# 2.5 인벤토리 무드리프트 확인 (재생성 아님 — 드리프트가 나오면 등가성이 깨진 것)
python tools/harness/failopen_scan.py --check
python tools/harness/audit_coverage_scan.py --check
python tools/harness/order_mutation_writer_scan.py --check
python tools/harness/state_writer_scan.py --check
# 매니페스트 2종(write_guard·order_mutation_policy)은 수기 정본 — 스캐너를 돌리지 마라

# 2.6 커밋 ① 코드 (한글 메시지는 UTF-8 파일로)
git commit -F /c/tmp/promote_msg.txt
```

**롤백**: `cd /c/tmp && rm -rf foms-promote` — 원격·공유 트리 무영향.

---

### S3 — 로컬 전량 게이트 (40~60분, 지배적 구간)

**무엇을**: production PR 이 **안 돌리는** FOMS CI · Harness CI 를 로컬에서 대신 돌린다(§1.5).

```bash
cd /c/tmp/foms-promote && pwd
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_alembic_single_head.py -q
python -m pytest tests/domains/test_auth_enforcement.py tests/domains/test_write_guard.py -q
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Full
python -m pytest tests/postgres -q
```

`-Full` 실측 확인: `pre_push_smoke.ps1:44 [switch]$Full`, `:205-206` 이 전체 pytest 를 돈다.
`test_auth_enforcement.py` 는 `pre_push_smoke` 에 **없어서** 따로 적었다(G2 확인, 로컬 green →
CI red 가 반복된 유형).

**완료 판정**: 전부 exit 0, `APP_OK` 출력, alembic heads 1개.
**롤백**: 워크트리 삭제(S2 와 동일).

---

### S4 — 운영 승격 (50분)

```bash
git push -u origin promote/full-20260825
gh pr create --base production --head promote/full-20260825 --title "..." --body-file <UTF-8 파일>
gh run list --branch promote/full-20260825 --limit 10 --json workflowName,conclusion,headSha
```

**완료 판정**
- PG Lane · perf-gate(**블로킹**) green — **전 워크플로를 나열해 확인**(`ci_watch` 는 1개만 본다)
- PR 머지 후 Railway predeploy 로그에 **`Running upgrade` 0줄**
- 배포 직후 **백필 1회 더**(S1 명령 재실행, 멱등)

**롤백**(사전 합의 필요 — §9)
1. **1차: Railway 이전 배포로 되돌리기.** 가장 빠르고 git 이력 무변경.
2. 2차: `git revert -m 1 <머지SHA>` → push. **force-push 금지.**
   ⚠️ revert 를 쓰면 재승격 시 git 이 "이미 머지됨"으로 보아 **아무 파일도 안 들어오는 조용한
   실패**가 난다 → revert 를 다시 revert 해야 한다.
3. 스키마는 되돌릴 필요 없다(이미 head, 이번 승격은 마이그레이션을 실행하지 않는다).
4. **되돌려도 남는 것**: `order_field_changes`·`order_change_reasons` 행,
   `structured_data` 의 `parties.buyer`/`source`/`naver`/`pricing` 키.
   운영 현행 저장 경로는 `parties` 를 통째 대입하므로 **롤백 후 첫 저장에서 그 사이 쌓인
   buyer 정보가 소실될 수 있다**(G3 evidence).
5. **불가역 외부 행위**는 전부 사람이 누르는 경로다(알림톡·채널톡 PUSH·공유링크 문자).
   새로 도는 자동 발송 루프 0건. → 관찰 창(15분) 동안 **발송 자제 공지**로 실질 0.

---

### S5 — 운영 확인 · 기록 (25분)

`claude_master` **해제 → 측정 → 재잠금**(요청 1건당 1회, 실데이터 불가침).

| 확인 | 합격선 |
|---|---|
| **AS 미완료/완료 탭 건수** | **S1 에서 기록한 값과 일치** ← B-1 의 최종 판정 |
| **AS 미완료 지도 건수** | 탭 건수와 일치 |
| ERP 주문 저장 1건 | 변경 사유 모달 정상, 저장 성공 |
| 알림톡 1건 · AS PUSH 1건 | 발송 성공(첨부 순서 유지) |
| 대표 7개 화면 | 200 · 콘솔 에러 0 |

문서 커밋 ②: `docs/AI_STATUS.md` + `docs/AI_CHANGELOG.md`.
⚠️ AI_STATUS 는 deploy 채택 후 head40 여유가 **78자뿐**이다 → 새 줄을 넣으려면 기존 한 줄을
`## 기록 보관` 으로 **반드시 강등**해야 한다.

```bash
python -m pytest tests/harness/test_hook_log_hygiene.py -q     # head budget + dead-task
```

**롤백**: 문서만 revert.

---

### 시간 예산

| 단계 | 추정 |
|---|---|
| S0 사전조건 | 5분 |
| S1 백필(승인 대기 제외) | 15분 |
| S2 병합·등가증명 | 25분 |
| S3 로컬 전량 게이트 | **40~60분** |
| S4 승격·CI·배포 | 50분 |
| S5 운영 확인·기록 | 25분 |
| **합계** | **2시간 40분 ~ 3시간 20분** — 한 세션 완주 가능 |

---

## 6. 승격하지 않았을 때의 비용 (공평하게 — 위험 CEO 정리를 채택)

1. **지금 운영이 가장 불안정한 중간 상태다.** 스키마만 올라가 있고 코드가 없다.
   `as_axis_status` 는 **아무도 채우지 않고 아무도 읽지 않는 죽은 컬럼**이며,
   `models.py` 에는 스키마 정합용 임시 선언(`1b74e0da`)과 "승격 주의" 주석이 떠 있다.
2. **8/14 AS 증발 사고의 구조적 원인이 운영에 그대로 있다** — 운영 AS 술어는 여전히
   `Order.status`(overlay 컬럼)라 외부 write 한 번에 목록이 또 사라질 수 있다.
   승격은 이 위험을 **제거하는 쪽**이다(단 B-1 백필이 전제).
3. **격차가 매일 커진다**(74 vs 485). 오늘 미루면 다음 시도는 더 크고 더 어렵다.
4. **롤백 가능성이 지금 최대다.** 485커밋을 더 쌓은 뒤의 사고는 이분 탐색이 사실상 불가능하다.

---

## 7. 검증 게이트 (복사해 붙일 수 있는 것만)

```bash
# ── 전제 재확인 ────────────────────────────────────────────────
git ls-remote origin refs/heads/production refs/heads/deploy
gh run list --branch deploy --limit 10 --json workflowName,conclusion,headSha
#   ⚠️ gh run list --commit <sha> 는 이 환경에서 항상 빈 결과다(§2.6)

# ── 등가 증명 (이 승격의 유일한 판정 게이트) ──────────────────
git diff --stat b8921291            # 무출력이어야 한다

# ── 인벤토리 무드리프트 (재생성 아님) ─────────────────────────
python tools/harness/failopen_scan.py --check
python tools/harness/audit_coverage_scan.py --check
python tools/harness/order_mutation_writer_scan.py --check
python tools/harness/state_writer_scan.py --check

# ── 코드 게이트 ───────────────────────────────────────────────
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_alembic_single_head.py -q
python -m pytest tests/domains/test_auth_enforcement.py tests/domains/test_write_guard.py -q
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Full
python -m pytest tests/postgres -q
python -m pytest tests/harness/test_hook_log_hygiene.py -q

# ── 데이터 게이트 (B-1) ───────────────────────────────────────
python tools/ops/backfill_as_axis_status.py --dsn "$PROD_DSN"
python tools/ops/backfill_as_axis_status.py --dsn "$PROD_DSN" --apply
python tools/ops/audit_as_axis_drift.py     --dsn "$PROD_DSN" --json

# ── 워킹트리를 안 건드리는 사전 리허설 (선택, 강력 추천) ──────
git merge-tree --write-tree --name-only origin/production origin/deploy
#   1행 = 머지 트리 OID, 이후 = 충돌 파일 목록(기대: 25개)
TREE=<위 1행>
git diff --name-only $TREE origin/deploy^{tree}     # 기대: 26개 (25 + test_as_timeline_wiring.py)
```

---

## 8. 중단 조건 (보는 즉시 멈추고 사용자에게 묻는다)

| 신호 | 뜻 |
|---|---|
| `origin/production` ≠ `57cc536d` | merge-base 가 바뀌어 **이 조사 전체가 무효** → 3자 집합 재계산부터 |
| 운영 `alembic_version` ≠ `merge_drawq_naverfail` | 브리프 전제 붕괴(G6 가 이 값에 이견을 남겼다 — §1.6) |
| S1 dry-run 대상 건수가 **0** | 백필이 이미 됐거나 **다른 DB 를 보고 있다.** 둘의 구분 전까지 전진 금지 |
| `git diff --stat b8921291` 이 **설명되지 않는** 출력 | keep-both 중복 등 미지의 병합 아티팩트 |
| 스캐너 `--check` 4종 중 하나라도 드리프트 | 등가성이 깨졌다는 신호. **재생성으로 덮지 마라** |
| `swallow_by_control_flow` > 180 | baseline **상향 금지** — 원인 handler 를 찾아라 |
| alembic heads ≠ 1 | 이중 head → 부팅 파산 경로 |
| `pre_push_smoke -Full` 또는 `tests/postgres` exit ≠ 0 | — |
| predeploy 로그에 **`Running upgrade` 가 나타남** | 스키마가 이미 head 여야 한다. 배포 성패와 무관하게 **즉시 중단·재조사** |
| perf-gate 블로킹 fail | — |
| S5 에서 AS 탭 건수 ≠ S1 기록값 | **B-1 미해소.** 즉시 롤백 판단 |
| 새 `PRODUCTION_ONLY` 판정 출현 | — |

---

## 9. 사용자가 결정해야 하는 것

| # | 결정 | 왜 사람이 정해야 하나 |
|---|---|---|
| 1 | **전량 머지 자체의 승인** | 프로젝트 절대 규칙은 "승격 = 자기 커밋 cherry-pick, 전체 머지는 사용자 명시 시에만". 이 계획은 그 **예외**를 전제한다 — 명시 승인 없이는 S2 도 시작 금지 |
| 2 | **S1 운영 DB 백필 승인** | 운영 DB **쓰기**다. 화면 무변동임을 확인했지만 실데이터 변경 |
| 3 | **`claude_master` 운영 해제 승인** | 요청 1건당 1회, 측정만, 재잠금 |
| 4 | **승격 시간대** | 가구 ERP 운영 중 배포 창 |
| 5 | **롤백 경로 사전 합의** | 특히 `git revert -m 1` 채택 시 **revert-of-revert 필요**를 미리 합의(§5 S4) |
| 6 | **네이버 기능을 켤 것인가** | env 부재로 승격해도 호출 0. 켜는 것은 **별건 결정** |
| 7 | **AI_STATUS 어느 줄을 `## 기록 보관` 으로 내릴지** | 여유 78자. 후보: `⚠️ [2026-08-23] 로컬 dev DB 행 소실(로컬 한정)` 또는 `⚠️ [2026-08-20] deploy FOMS CI red = 타 세션 몫` |
| 8 | **AI_CHANGELOG 운영 L7 행을 되살릴지** | 되살리면 `부모는 assort_00` 서술이 승격 즉시 거짓이 된다. 이 파일엔 문자 예산 계약이 없어 기술적으로는 둘 다 안전 |
| 9 | **A-1 · A-2 · A-3 사용자 고지 범위** | 변경 사유 모달·삭제 사유·nav "네이버 수집" 탭이 **전 사용자에게 첫날부터** 보인다(플래그 없음, 저장은 안 막힘) |
| 10 | **A-4 당일 코드 수용** | 승격분 상당수가 08-24 밤 코드, 스테이징 육안 확인만 거쳤다 |

---

## 10. 이 로드맵이 낡는 조건

| 조건 | 영향 | 대응 |
|---|---|---|
| **`origin/production` 이 움직임** | merge-base 변경 → §1.2 3자 집합·§4 처리표·§2.4 등가 기준 **전부 무효** | **전면 재조사** |
| **`origin/deploy` 가 움직임** | 새 tip 은 CI green 이 미확인 상태 | 핀 SHA `b8921291` 로 계속 진행(권장) 또는 새 tip 의 CI green 재확인 후 재계산 |
| **운영 DB `alembic_version` 이 다름** | §1.6 전제 붕괴 | S0 에서 중단 |
| **S1 백필 후 시간이 오래 지남** | 그 사이 AS 활동분이 NULL | 배포 직후 재실행(멱등) |
| **승격 방식이 전량 머지 → 부분 cherry-pick 으로 바뀜** | §4.1 결합 제약이 **전부 되살아난다**. 등가성 게이트도 성립하지 않는다 | §4.1 표부터 재검토 |
| **다른 세션(R1-dock·R2-link·R3-events)이 deploy 에 push** | S2 병합 대상이 검증한 트리와 달라짐 | SHA 고정으로 방어. 승격 중 deploy push 동결 권장 |
| **2026-08-25 를 넘김** | 이 저장소는 "승격 체인 재배열은 하루면 낡는다"는 실사고 기록이 있다(운영 alembic head 전제가 타 세션 승격으로 깨져 #113·#121 연속 무효) | 당일 완주 또는 §1 전량 재실측 |

---

## 11. 조사에서 틀렸던 것 (적대 검증이 뒤집은 것 + 이 문서가 추가로 뒤집은 것)

기록해 두는 이유: **틀린 검증 명령이 승격 중 거짓 경보를 내면, 작업자가 멀쩡한 승격을
중단하거나 "수동 편집 금지" 파일을 손대게 된다.** 실제로 이 저장소는 그 유형으로 사고가 났다.

| # | 원 주장 | 실제 | 출처 |
|---|---|---|---|
| 1 | G3: `git ls-tree HEAD foms/services/orders/change_reason.py` 가 무출력이면 **부팅 파산** | 머지 중 HEAD 는 production 이라 **정상 승격에서도 항상 무출력**. 거짓 경보 → `git ls-files --` 또는 `test -f` 로 교체 | 적대 검증 |
| 2 | G5: `grep -c 'foms-mobile-select.js?v=20260824a'` 로 iOS 피커 핀 확인 | 원문이 `…js') }}?v=20260824a` 라 **항상 0**. 이 오판으로 "수동 편집 금지" 핫파일을 건드리게 된다 → `grep -cE "foms-mobile-select.*20260824a"` | 적대 검증 |
| 3 | 실행 CEO: `gh run list --commit b8921291` 로 CI green 확인 | **이 환경에서 항상 빈 결과**(대조군 `5d8db32b` 도 빈다, gh 인증은 정상). 결론은 참이나 명령은 불가용 → `--branch deploy` + headSha | **이 문서(§2.6)** |
| 4 | 실행 CEO: 충돌 25개를 풀면 `git diff --stat b8921291` **무출력** | **26개를 풀어야 무출력**이다. 비충돌 파일 `test_as_timeline_wiring.py` 가 keep-both 중복을 만든다 | **이 문서(§2.4)** |
| 5 | 위험 CEO R-2 근거: `foms/web/admin/__init__.py` 이중 import 가 머지 keep-both 흔적 | 그 이중 import 는 **`origin/deploy` 자체에 선재**한다(5·6행, CI green 상태). 머지가 만드는 것이 아니다. **결론(R-2 는 실재)은 옳고 근거만 빗나갔다** | **이 문서(§2.4)** |
| 6 | 위험 CEO R-7: "STAFF 가 빈 화면에서 버튼을 누르면 에러" | "지금 수집"은 `role_required(["ADMIN"])`(`naver_ingest.py:379`)이라 **STAFF 는 누를 수 없다**. 트리아지는 게이트 off 시 옛 화면을 빈 큐로 정상 렌더 | **이 문서(§3.3 A-2)** |
| 7 | G6 open question: 운영 alembic head 가 `merge_prod_drawq` 일 수 있다 | 출처 SPEC 이 **스키마 승격 이전(08-24 19:34)** 기록. 운영 트리의 권위 있는 head 는 `merge_drawq_naverfail`(alembic resolver, 85 리비전) | **이 문서(§1.6)** |
| 8 | G4: 특징 문자열 대조 "prod 27매치 → push-confirm 24매치" | 실측 **24 ↔ 24 완전 대응**. 27 은 오기이며, 그대로 실리면 재현자가 "3건 소실"로 오판 | 적대 검증 |
| 9 | G4: 커밋 패치가 "바이트 동일(IDENTICAL PATCH)" | 커밋 헤더·`# Conflicts:` 4줄 때문에 그대로는 불일치. 헤더 제거 후에만 성립 | 적대 검증 |
| 10 | G4: `fallbackFormUpload` 는 저장소 전체에 정의 1건 | 저장소 전체로는 **3건/2파일**(`upload-progress.js` 의 동명 함수는 살아 있다). as-dashboard.js 안에서 죽은 코드라는 결론만 유효 | 적대 검증 |
| 11 | G5: `erp_order_js.html` 운영 전용 커밋 "15개" | 실측 **14개**(배열 자체는 14건으로 정확, 산문 숫자만 오기) | 적대 검증 |
| 12 | G5: 핀 계약 결합은 "3점 세트" | `erp_order_tab.html`·`erp_order_tab_mobile.html`·`erp_alimtalk_trace_modal.html` **3개가 빠졌다**(총 6개) | 적대 검증 |

---

## 12. 이 조사에서 확인하지 못한 것 (정직하게)

브리프 규율("확인 못 한 것은 확인 못 했다고 적어라")에 따라 명시한다.

1. **운영 DB 를 조회하지 않았다.** `alembic_version` 실값, `as_axis_status` 의 실제 NULL 건수,
   AS 탭 실건수는 전부 **미확인**이다. B-1 의 논증은 *"운영 코드에 그 컬럼을 쓰는 자리가 0건이고
   마이그레이션도 백필하지 않는다"*는 **코드 근거**에서 나온 것이며, 누군가 수동으로 백필을
   돌렸다면 전제가 바뀐다 → **S0 의 `filled` 조회가 그 판정을 대신한다**(0 이면 B-1 확정,
   수백 건이면 이미 해소).
2. **테스트를 한 줄도 실행하지 않았다.** §7 의 게이트는 전부 **미실행**이다.
3. **실제 머지를 하지 않았다.** §2.4 의 결과는 `git merge-tree --write-tree` 가상 머지이며,
   실제 `git merge` 의 rename 처리·`.gitattributes` 병합 드라이버 적용 결과가 미세하게 다를
   여지가 이론적으로 남는다. 그래서 §5 S2.4 를 **실제 트리에서 다시 돌리게** 했다.
4. **Railway 서비스 설정을 확인하지 않았다.** `railway.toml` 의 `preDeployCommand` 가 대시보드에서
   덮어써져 있지 않은지는 **사람이 눈으로 확인**해야 한다(선행 SPEC §1.2 가 같은 경고를 남겼다).
   덮어써져 있으면 fail-closed 전제가 무너진다.
5. **비충돌 237개 파일 중 무등급 16개만** 3자 대조했다. 나머지는 production 이 손대지 않아
   (prod-only-changed = 0) 구조적으로 안전하지만, 개별 내용 검토는 하지 않았다.
6. **운영에서 `a5758256`(AS 첨부 순서)이 실제로 동작 중인지 실측하지 않았다.** 코드 대조로는
   deploy 가 상위집합이지만, 승격 후 실전송 1건으로만 확정된다(S5).

---

## 13. 주 세션 독립 재확인 (2026-08-24 밤, §12 미확인 항목 일부 해소)

조사·CEO 보고를 그대로 쓰지 않았다. 아래는 **주 세션이 직접 명령을 돌려 확인한 것**이다.

### 13.1 B-1 확정 — 운영 DB 실조회로 닫았다 (§12-1 해소)

`§12-1` 이 "운영 DB 미조회, S0 의 `filled` 조회가 판정을 대신한다"고 남긴 항목을
읽기 전용 1회 조회로 **미리 닫았다**:

```
전체 주문                       3,975
as_axis_status 채워진 행            0      <- 전 행 NULL 확정
status 로 본 AS 주문(참고)         598
```

**B-1 은 실재하며 심각도가 확정됐다.** 지금 코드를 승격하면 AS 대시보드·AS 미완료 지도가
**598건을 0건으로** 보여준다. 이 저장소는 이미 같은 계열 사고를 겪었다
(2026-08-14 일괄 완료처리 AS 증발). **S1 백필은 선택이 아니라 필수다.**

코드 근거도 대조했다:
- deploy `foms/services/as_dashboard_helpers.py:285` → `return Order.as_axis_status.isnot(None)`
- 운영 코드에서 이 컬럼을 읽는 자리 **0건**(`models.py` 선언 2줄과 마이그레이션 docstring 뿐).
  대조군으로 `git grep` 도구 자체는 정상 동작함을 확인(운영 `models.py` 2매치).
- 백필 스크립트 `tools/ops/backfill_as_axis_status.py` 는 deploy 에 **존재**하고,
  기본 dry-run·`--apply` 필요·배치 커밋으로 **멱등**이다(docstring 실독).

### 13.2 §12-4 해소 — Railway `preDeployCommand` 는 덮어써져 있지 않다

`railway status --json` 의 `serviceManifest.deploy` 를 서비스별로 읽었다(GraphQL 은 403):

```
web     : preDeployCommand = ['sh predeploy.sh'] · startCommand = 'sh start.sh'
WORKER  : preDeployCommand = ['sh predeploy.sh'] (predeploy.sh 가 USE_RQ_WORKER=1 이면 즉시 exit 0)
Postgres/Redis/FOMS-cron : preDeployCommand 없음(정상)
```

**fail-closed 전제는 유효하다** — 마이그레이션이 실패하면 배포가 라이브되지 않는다.

### 13.3 B-2 를 일반화해 전수 스캔했다 (조사가 안 한 것)

`test_as_timeline_wiring.py` 하나만의 문제인지 확인하려고, 머지 트리 전체의 `.py` 에서
**같은 파일 안 중복 top-level `def`/`class`** 를 스캔했다.

```
중복 심볼이 있는 파일: 2
  models.py                              -> ['OrderChangeReason']
  tests/domains/test_as_timeline_wiring.py -> ['test_as_attachment_order_...']
```

- `models.py` 는 **충돌 상태(`UU`)라 충돌 마커 6개 때문에 중복으로 보인 것**이다
  (병합 시 해소되므로 문제 아님).
- `test_as_timeline_wiring.py` 는 마커 **0개**인 자동 병합 결과다 → **진짜 중복 확정**.
  두 정의(933·942행)는 **바이트 단위로 동일**해 pytest 는 통과한다.

**결론: 이 부류의 조용한 아티팩트는 저장소 전체에서 1건뿐이다.** B-2 의 실질 피해는
작지만, 교훈은 그대로다 — **`git status` 가 깨끗한 것은 병합이 옳다는 증거가 아니다.**

### 13.4 PROD-NEW = 0 을 다른 방법으로 재확인했다

로드맵의 핵심 전제(운영이 병합에 기여하는 신규 내용 0)를 **커밋 단위**로 독립 검증했다.

```
운영 전용 74 = 머지 커밋 28 + 내용 커밋 46
git cherry origin/deploy origin/production  ->  + 26건 (patch-id 대응물 없음) / - 20건
production 에만 있는 파일  ->  0개
requirements.txt 양쪽 diff ->  무출력 (solapi 양쪽 모두 존재)
```

`+` 26건은 patch-id 가 안 맞을 뿐이므로 **전부 개별 확인**했다:

| 분류 | 건수 | 확인 방법 |
|---|---|---|
| deploy 에 **동일 제목** 커밋 존재 | 20 | `git log --fixed-strings --grep` 로 deploy SHA 대응 확인 |
| 승격 트리 인벤토리 재생성(`7ad13126`) | 1 | 생성물 — REGENERATE 부류 |
| solapi 의존(`4c740a95`) | 1 | `requirements.txt` 양쪽 **동일**, solapi 양쪽 존재 |
| 계보 병합 리비전(`c5659963`) | 1 | deploy 에 `da7c0f9e` 로 **파일 복원됨**(E1) |
| target_role 승격(`0fe42d24`) | 1 | 운영 9파일 vs deploy **12파일** — deploy 가 상위집합 |
| 내 스키마 승격(`01953e09`·`1b74e0da`) | 2 | deploy 에 마이그레이션·모델 선언 모두 존재 |

**26/26 전부 내용이 deploy 에 있다.** 커밋 매핑 에이전트의 `unmapped = 0` 이
**다른 방법으로도 재현됐다.**

### 13.5 아직 남은 미확인 (§12 중 안 닫힌 것)

- §12-2 테스트 미실행 — S3 가 그 자리다.
- §12-3 실제 머지 미수행(가상 머지 결과) — S2.4 가 실제 트리에서 재확인한다.
- §12-5 비충돌 237개 중 221개 개별 미검토 — `production 에만 있는 파일 0개` ·
  `PROD-NEW = 0` 으로 구조적으로는 안전하나, 개별 내용 검토는 하지 않았다.
- §12-6 운영에서 AS 첨부 순서 실동작 미실측 — S5 실전송 1건으로만 확정된다.

---

## 14. S0 · S1 실행 기록 (2026-08-25, 사용자 승인 하에)

사용자 결정: **S0·S1 까지만 먼저.** 롤백 경로는 **Railway 재배포 우선**으로 사전 합의.

### S0 — 사전조건 (통과)

| # | 항목 | 실측 | 판정 |
|---|---|---|---|
| 1 | `alembic_version` | `['merge_drawq_naverfail']` 단일 행 | OK |
| 2 | 전체 주문 | 3,975 | 기록 |
| 3 | `filled`(as_axis_status IS NOT NULL) | **0** | OK(백필 전) |
| 4 | 신규 테이블 2종 | `external_order_links` · `order_change_reasons` 존재 | OK |

**S5 대조 기준선** (status 기준 AS 분포, `deleted_at IS NULL`):

```
AS_COMPLETED   541
AS_RECEIVED     57
합계           598
```

> **전제 하나가 움직였다**: `origin/deploy` 가 `b8921291` → **`1e112fe7`** 로 갔다.
> 이 로드맵 문서 커밋(문서 전용, 코드 무변경)이다. S2 의 등가 증명 대상 tip 은
> **`1e112fe7`** 로 읽어라(§10 의 "낡는 조건" 에 해당하지 않는 종류의 이동이다 —
> 코드 트리는 그대로다). `origin/production` 은 `57cc536d` 불변.

### S1 — 백필 (완료)

```
[dry-run] 후보 621건 / 변경 598건   (NULL→COMPLETED 541 · NULL→RECEIVED 57)
[적용]    후보 621건 / 변경 598건   (동일)
```

dry-run 이 예고한 598 이 **S0 에서 잰 status 분포 598 과 정확히 일치**했다 —
스크립트가 유도 규칙(`derive_as_axis_status`)을 그대로 쓴다는 것의 실증이다.

**드리프트 감사** (`audit_as_axis_drift --json`):

```json
{"checked": 617, "mismatch": 0, "missing_projection": 0, "legacy_only": 0, "samples": []}
```

**완료 판정 — 두 술어가 같은 수를 낸다**:

```
구 술어(status IN AS 계열)        598
신 술어(as_axis_status IS NOT NULL) 598
```

→ **B-1 해소.** 코드가 승격돼 AS 모집단 술어가 컬럼 기반으로 바뀌어도 AS 대시보드·
AS 미완료 지도가 **598건을 그대로 본다**.

**운영 무영향 확인**: `healthz` 200 ×3 · `login` 200. 현 운영 코드는 이 컬럼을 읽지
않으므로(§2.1) 화면 변화 없음 — 롤백 불필요.

### 다음에 이어서 할 때

- **S1 을 S4 직후 1회 더 돌린다**(멱등). S1~S4 사이의 AS 활동분을 덮기 위해서다.
- 재개 전 **S0 을 다시 돌려라.** `filled` 가 598 근처면 정상(백필 완료 상태),
  `alembic_version`·운영 tip 이 바뀌었으면 §10 의 낡음 조건을 먼저 판정한다.
- 남은 단계: **S2 병합·등가 증명 → S3 로컬 전량 게이트 → S4 승격 → S5 확인.**
  착수 전 필요한 사용자 결정은 **전량 머지 승인** 하나다(백필 승인·롤백 합의는 완료).

---

## 15. S2 · S3 실행 기록 (2026-08-25)

사용자 결정: **전량 머지 승인 · 로컬 검사 전부 · 승격 후 네이버 켜기**(켜기는 별건으로 분리).

### 승격 대상 SHA 고정

deploy tip 이 계속 움직여서 **CI 전량 green 인 최신 SHA 로 못박았다**: **`77fc7cb4`**
(= 이 세션의 S0·S1 기록 커밋. FOMS CI · Harness CI · PG Lane **3/3 success** 확인).
브랜치명으로 병합하면 타 세션 push 시 게이트가 조용히 거짓말한다 — SHA 로만 병합했다.

### S2 — 병합 · 등가 증명 (통과)

승격 워크트리 `c:/tmp/foms-promote`, 브랜치 `promote/full-20260825`, 기점 `57cc536d`.

```
충돌 25개  ->  전부 deploy 판 채택(--theirs)
+ 조용한 중복 1개(tests/domains/test_as_timeline_wiring.py)  ->  deploy 판으로 덮음
```

**판정 게이트 — 통과:**

```
git diff --stat 77fc7cb4   ->  무출력
머지 트리   = 2539be20fea7454c5399695156e32acb0674fd0f
deploy 트리 = 2539be20fea7454c5399695156e32acb0674fd0f      <- 완전 일치
충돌 잔재 0 · 충돌 마커 0
```

커밋: `3edddbb8`.

**인벤토리 드리프트 — 1건은 거짓 경보였다(기록):**

| 스캐너 | `--check` |
|---|---|
| `failopen_scan` · `order_mutation_writer_scan` · `state_writer_scan` | 드리프트 0 |
| `audit_coverage_scan` | **`drift=YES`** |

그런데 `audit_coverage_scan --check` 는 **CI green 인 세션 트리에서도 똑같이 `drift=YES`**
를 내고(`total=193` vs 승격 트리 `total=194`, 둘 다 `unaudited=0 coverage=100%`),
**CI·`pre_push_smoke` 어디서도 이 스캐너를 `--check` 로 돌리지 않는다**(워크플로·smoke 전수 그렙).
→ 병합이 만든 것이 아니라 **선재 상태**다. 실제 게이트인 계약 테스트
`test_audit_coverage_inventory` + `test_failopen_inventory` 는 **24 passed**.

로드맵 §11 이 경고한 "틀린 검증 명령의 거짓 경보" 부류가 S2.5 에서 그대로 재현됐다.
**다음 승격에서는 S2.5 를 계약 테스트로 대체해야 한다.**

### S3 — 로컬 전량 게이트

| 게이트 | 결과 |
|---|---|
| `import app` | **APP_OK** |
| `test_alembic_single_head` | 1 passed |
| `test_auth_enforcement` + `test_write_guard` | 37 passed |
| `tests/postgres` 전수 | **747 passed** |
| `pre_push_smoke.ps1 -Full` | **FAIL** (전량 pytest 단계) — 원인 조사 중 |

전량 pytest 실패는 **트리가 CI green 인 deploy 와 바이트 동일한데 로컬만 실패**하는
형태다. 환경 기인(로컬 DB 드리프트·Redis 부재 등) 가능성이 높지만 **추정하지 않고
실패 목록을 직접 뽑아 판정한다**. 판정 전까지 S4 진입 금지.

---

## 16. S4 · S5 실행 기록 — **전량 승격 완료** (2026-08-25)

### S3 최종 판정 — 통과 (실패 6건은 전부 환경 기인)

전량 pytest: **6,247 passed / 6 failed**. 6건 전부 `tests/harness/` 였고 근거 셋으로 확정:

1. 같은 6건이 **CI green 인 세션 트리에서도 동일하게** 실패한다.
2. **`PYTHONIOENCODING=utf-8` 을 빼니 5건이 사라진다** → `tests/harness` **361 passed / 1 failed**.
   실패 형태가 `TypeError: argument of type 'NoneType' is not iterable`(서브프로세스
   `stdout` 이 `None`)로, 원장에 기록된 **가짜 red 함정** 그대로다.
3. 남은 `test_deploy_push_allows_when_scope_empty` 는 **가드가 정상 동작한 결과**다 —
   승격 워크트리에서 deploy 로 푸시하면 75커밋이 딸려가니 `ask` 를 낸다(워크트리 git 상태
   의존). CI 는 깨끗한 클론이라 `allow` 이고, **Harness CI 가 같은 트리로
   `pytest tests/harness` 를 돌려 green** 이다.

> **다음 승격 지침**: `pre_push_smoke -Full` 은 `PYTHONIOENCODING` 를 **설정하지 않은**
> 셸에서 돌려라. 설정하면 harness 5건이 가짜 red 로 뜬다.

### S4 — 운영 승격 (완료)

PR **#145** (`promote/full-20260825` → `production`). 체크 **perf-gate pass · pg-lane pass**.
병합 전 운영 tip 이 기점 `57cc536d` 에서 안 움직인 것을 확인하고 머지.

```
운영 머지 커밋 : 39fa919d
운영 트리      = 2539be20fea7454c5399695156e32acb0674fd0f
deploy(77fc7cb4) = 2539be20fea7454c5399695156e32acb0674fd0f      <- 바이트 동일
```

**배포 중 스키마 감시**(30초 간격 12회, 읽기 전용): `alembic_version` 이
`merge_drawq_naverfail` 로 **불변**, `as_axis_status filled` 598 **불변**.
→ 예상대로 이번 배포는 마이그레이션을 실행하지 않았다(스키마는 이미 head).

**배포 후 백필 재실행**(멱등 — 로드맵이 지시한 대로):

```
[적용] 후보 623건 / 변경 3건        (NULL→RECEIVED 2 · COMPLETED→RECEIVED 1)
드리프트 감사: checked 619 / mismatch 0 / missing_projection 0 / legacy_only 0
```

S1~S4 사이에 실제로 AS 활동 3건이 있었다 — **재실행 지시가 값을 했다.**

### S5 — 운영 확인 (완료)

`claude_master` 해제 → 측정 → **재잠금**(`is_active = False` 확인). 실데이터 변경 0.

**B-1 최종 판정 — 통과:**

```
신 술어(as_axis_status IS NOT NULL) 600  ==  구 술어(status IN AS 계열) 600
AS 대시보드 실렌더 행(data-order-id)      570      <- 비어 있지 않다
```

| 화면 | 결과 |
|---|---|
| 홈 · 주문 목록 | 200 · 736ms |
| ERP 대시보드 | 200 · 978ms |
| **AS 대시보드** | 200 · 730ms · **570행 렌더** |
| 실측 · 출고 · 시공 대시보드 | 200 |
| **AS 미완료 지도** | 200 · 마커 렌더됨(빈 화면 아님) |
| 주문 상세 #4968 | 200 |

전 화면에서 `does not exist` · `UndefinedColumn` · `Traceback` **0건**.

> **정직하게**: AS 미완료 지도는 마커를 비동기로 싣기 때문에 HTML 만으로 **건수 일치까지는
> 확인하지 못했다**. 확인한 것은 "비어 있지 않다"이며, B-1 의 실패 모드(통째로 빔)는 배제됐다.

### 남은 것

- **운영 네이버 환경변수 미투입** — `NAVER_COMMERCE_CLIENT_ID`/`SECRET`·
  `FOMS_NAVER_SYNC_ENABLED`·`FOMS_NAVER_WORKBENCH_ENABLED` 없음.
  네이버로 나가는 호출 0, 실주문 자동 생성 0. **켜는 것은 열쇠가 필요한 별건이다.**
- `docs/AI_STATUS.md`·`docs/AI_CHANGELOG.md` 미갱신(병렬 세션 충돌 회피). 기록은 이 문서와
  `2026-08-24-naver-d1-repay-revision-ledger.md` 가 갖고 있다.
  ⚠️ AI_STATUS 는 head40 여유가 **78자뿐** — 새 줄을 넣으려면 기존 한 줄을 `## 기록 보관`
  으로 강등해야 한다.

---

## 17. 네이버 운영 개방 (2026-08-25) — 승격 범위 밖이던 것을 켰다

사용자 결정: **스테이징 열쇠를 그대로 사용 · 전부 켜기(화면+수집, 전 직원) ·
스테이징 수집도 계속 유지 · 즉시 재배포.**

### 17.1 "운영 네이버수집이 이전 버전" 신고 — 배포 실패가 아니었다

사용자가 옛 트리아지 화면(`수집 주문 확인` · `확인 대기 — 한 집이 한 줄`)을 보고 신고했다.

**원인**: `FOMS_NAVER_WORKBENCH_ENABLED` 가 운영에 없어서 **게이트 OFF 경로**
(`templates/admin/naver_triage.html`)가 렌더된 것이다. 계약이 그 파일을 "손대지 않는
롤백 경로"로 지정해 뒀다. 운영 트리는 deploy 와 바이트 동일(`2539be20`)이라 **코드는 새
버전이 맞았고 플래그만 꺼져 있었다.**

> 교훈: 승격 후 "옛 화면이 보인다"는 신고는 **배포 실패가 아니라 게이트 미설정**일 수 있다.
> 트리 해시가 같으면 코드는 갔다 — 다음은 플래그를 봐라.

### 17.2 열쇠 이관 중 사고 1건 — `eval` 이 secret 을 잘랐다

스테이징 `worker` 의 열쇠 3종을 운영 `WORKER` 로 옮기면서 `eval railway variables --set ...`
을 썼더니 **`CLIENT_SECRET` 이 29자 → 27자로 잘렸다.** 값이 `$2a$…` 로 시작하는데 셸이
`$2` 를 위치 매개변수로 확장해 먹은 것이다.

**화면에 값을 안 찍었기 때문에 눈으로는 못 잡았다 — 길이·SHA 대조가 잡았다:**

```
NAVER_COMMERCE_APP_EXPIRES_ON   OK   len 10->10  sha 57b41a84 -> 57b41a84
NAVER_COMMERCE_CLIENT_ID        OK   len 22->22  sha fc0253f0 -> fc0253f0
NAVER_COMMERCE_CLIENT_SECRET    불일치! len 29->27  sha a666551e -> 04b3d92f   <- 잘림
```

수정: `eval` 을 버리고 변수 확장으로 넣었다(**변수 값 안의 `$` 는 재확장되지 않는다**).
재대조에서 3종 전부 해시 일치. 임시 파일 삭제.

> **다음에도 반드시 지켜라**: 비밀값을 셸로 옮길 때 `eval` 금지, 넣은 뒤 **길이+해시 대조**.
> 값을 안 찍는 규율은 옳지만, 그 규율 때문에 잘림을 눈으로 못 잡는다 — 대조가 유일한 그물이다.

### 17.3 넣은 설정 (서비스 배치가 계약이다)

| 서비스 | 변수 |
|---|---|
| **WORKER** | `NAVER_COMMERCE_CLIENT_ID` · `CLIENT_SECRET` · `APP_EXPIRES_ON` + `FOMS_NAVER_SYNC_ENABLED=1` + `FOMS_NAVER_SYNC_INTERVAL_SECONDS=300` |
| **web** | `FOMS_NAVER_WORKBENCH_ENABLED=1` + `FOMS_NAVER_WORKBENCH_COHORT=all` |

- **네이버로 나가는 HTTP 는 WORKER 단독**이다. 커머스API IP 한도 3 = Railway static IP 3 이라
  여유가 없다(`start.sh:31-36` 주석). 그래서 web 에는 열쇠를 넣지 않았다.
- `COHORT=all` 이 필요하다 — `is_enabled_for_user` 는 **cohort 가 비면 플래그가 켜져도
  꺼진 것으로 판정**한다(`feature_flags.py:112-134`).

### 17.4 적용·검증

`--skip-deploys` 로 변수만 넣고, dev/prod 혼동 가드(프로젝트명 확인) 후 `web`·`WORKER`
재배포 → **둘 다 SUCCESS**.

| 확인 | 결과 |
|---|---|
| `healthz` | 200 ×3 |
| **수집 실동작** | `external_order_links` **16행**, 최근 수집 `2026-08-25 00:44:19` |
| **워크벤치 v3 렌더** | `wb-tabs` · `wb-detail` · `data-filter="rel"` **있음** / 옛 화면 문구 **없음** |

`지금 닫기` 라벨이 없는 것도 **정상**이다 — 오늘 D1 개정으로 그 버튼은 **추가결제(ADDON)
집에만** 뜨는데 현재 그런 집이 없다.

`claude_master` 는 해제 → 측정 → **재잠금**(`is_active = False` 확인). 실데이터 변경 0.

### 17.5 남은 위험 (사용자 인지 후 유지 결정)

**스테이징 수집도 계속 돈다.** 같은 네이버 계정이라 같은 주문을 양쪽이 각자 보관하고,
**발주확인·발송처리 같은 불가역 버튼이 양쪽 화면에 동시에 살아 있다.** 스테이징에서
누르면 진짜 네이버로 나간다. 끄려면 스테이징 `worker` 의 `FOMS_NAVER_SYNC_ENABLED` 만
내리면 된다(화면은 그대로 남는다).


---

## 18. 개방 후 안정화 (2026-08-25 오후)

사용자 결정 4건: 운영 실화면은 **사용자가 직접 확인**(claude_master production 미사용) ·
재결제 화면 판정은 **스테이징에서** · 스테이징 수집 **유지** · 미결 4건 전부 처리.

### 18.1 운영 수집은 건강하다 (읽기전용 DB 조회, 계정 미사용)

```
watermark last_run_at 2026-08-25T10:15:54+09:00   last_error: None
external_order_links 20건  전부 COLLECTED · 실패 0 · failure_reason 0
관계축 NEW 20 / REPAY 0 / ADDON 0     집(group_key distinct) 7
reviewed_at 있는 건 0 · 생성된 주문 0
```

운영에 REPAY·ADDON 이 0 이라 **재결제 화면 판정은 운영 데이터로 불가능**하다.
스테이징에는 REPAY 6 · ADDON 2 가 있다(265 links · 81집) — 판정은 거기서 한다.

### 18.2 운영 사고 — `주문 만들기` 가 막혀 있었다 (T0 ① 미실행)

사용자 신고: 운영 워크벤치에서 `주문 만들기` → `수집 actor 계정이 없다:
naver_ingest_bot (T0 선행 작업)`.

**원인**: 승격·개방은 코드와 플래그만 다뤘고, `NAVER_INGEST_SETUP.md` 운영 체크리스트
**①(시스템 계정 2개 생성)이 한 번도 안 돌았다.** 운영 `users` 에 두 행 모두 없었다
(스테이징에는 id 62·63 으로 있다).

**조치**: `create_naver_ingest_accounts.py` 를 운영 DB 로 dry-run → 사용자 승인 → 1회 적용.
`naver_ingest_bot`(id 61, MANAGER/CS) · `naver_unassigned`(id 62, STAFF/SALES) 생성.
기존 행 변경 0. 검증은 **에러를 내던 그 함수**로 했다 —
`resolve_ingest_account_ids(운영세션) -> (61, 62)`.

> **교훈**: 수집이 돌고 목록이 보여도 **처리 경로는 따로 막힐 수 있다.** 개방 체크리스트는
> "수집이 들어오는가" 로 끝나면 안 되고 **담당자가 누르는 버튼까지** 밟아야 한다.
> 이 결함은 사람이 첫 `주문 만들기` 를 누르기 전까지 어떤 로그도 내지 않는다.

### 18.3 워크벤치 두 줄 머리가 안 붙어 보이던 결함

사용자 신고: "이 nav bar 도 sticky 로". **코드는 이미 sticky 였다** — 전역 nav
(`.layout-global-nav`)가 `sticky · top:0 · z-index:1000` 이라 `top:0 · z-index:3` 인
머리줄이 **그 밑에 깔린** 것이다. 고정 오프셋도 못 쓴다: nav 높이가 폭에 따라
**67 → 97 → 121 → 169px**(1920/992/900/768 실측)로 변한다.

수정: JS 가 실측해 `--wb-nav-h` 로 흘리고 CSS 네 자리(머리줄·도구줄·상세 sticky top·
max-height)가 그 변수를 문다. `resize` + `ResizeObserver`(메뉴 펼침) 재측정.

> 같은 부류의 신고가 또 오면 **먼저 z-index 를 의심해라.** "sticky 인데 안 붙는다" 의
> 절반은 붙어 있는데 다른 sticky 밑에 깔린 것이다.

### 18.4 도크 머리말 ≠ 링크가 여는 집 (U-1 과 같은 뿌리)

U-1 실조회로 확정: 링크 264~269 = **REPAY**, 주문 4485. 같은 주문에 집이 하나 더
있다(링크 58~61, NEW). 그래서 머리말(첫 집)과 `워크벤치에서 열기`(나중 집)가 어긋난다.

수정: 머리말이 집 번호를 **전부** 말하고, 링크가 여는 집만 무게로 지목한다.
`workbench_order_no` 는 주소를 만드는 `rows[-1]` 에서 끌어온다(출처 하나로 못박음).

### 18.5 붙이기 중복 이벤트 — 정책 확정

**주문 변경 이력은 "무엇이 바뀌었나" 를 말하는 자리다.** 같은 버튼을 두 번 눌러도
두 번째는 아무것도 안 바꾼다(금액은 원래 멱등) → 이력에 안 쌓는다. 판정은 횟수가 아니라
**상태**다: 되돌린 뒤 다시 붙이면 그때는 다시 남는다. 누가 몇 번 눌렀는가는
`log_access` 감사가 전량 보관한다(감사 축 불변).

### 18.6 검증 준비

스테이징 워크벤치 코호트에 `claude_master`(id 58)를 더했다(`38` → `38,58`).
화면 판정을 계정 하나로 반복하기 위해서다 — 운영 코호트(`all`)는 손대지 않았다.


### 18.7 쿠폰 표기 (사용자 요구, 2026-08-25)

**"쿠폰 썼는지 안 썼는지 알 수 있게 표기"** — 지금까지 쿠폰 할인은 `할인` 합계에 녹아
있어 화면 어디서도 구분되지 않았다(워크벤치 v3 상세는 할인 표시 자체가 없었다).

실데이터가 정한 설계: 스테이징 281건 중 **50건에 쿠폰**이 붙고 **부담 주체가 다른 두
종류가 섞여 온다** — `NMP_PRD_DCNT`(naverBurdenRatio 100 · 네이버가 문다) ·
`NMP_PRD_DUP_DCNT`(0 · 우리가 문다). 그래서 장수·할인액만으로는 부족하고 **판매자
부담분**을 따로 낸다.

규율 둘: ① **안 쓴 집도 말한다**(침묵하면 "없음"과 "모름"이 구분 안 된다).
② 부담 비율이 없으면 부담액은 **모름(None)** 이다 — 0 으로 채우면 "우리 부담 없음"이 된다.

스테이징 실화면 확인: 워크벤치 `쿠폰 2장 사용 −21,000원 · 판매자 부담 11,000원` /
도크 `쿠폰 2장 −10,000원 (전액 네이버 부담)`.

필드 인벤토리는 `docs/guides/NAVER_FIELD_INVENTORY.md` 로 분리했다 — 281건 전수 기준
"오는 것 · 쓰는 것 · 안 쓰는 것".


---

## 19. 재결제 정리 R-1·R-2 (2026-08-25 오후)

설계 `docs/specs/2026-08-25-naver-repay-reconcile_SPEC.md` · 목업 2판 ·
다음 세션 프롬프트 `docs/plans/2026-08-25-naver-repay-reconcile-next-session.md`.

**R-1 — 후보 표 판정 근거 2열** (`7daaa4fd`). 재결제/추가결제를 가르는 결정 신호는
"그 주문에 붙은 네이버 결제가 취소됐는가" 인데 화면은 링크 개수만 냈다. 금액은 **집
전체끼리** 견준다(대표 1건끼리 견주면 항상 작다: 1,022,900 vs 실제 1,610,780).

**R-2 — 유령 주문 띠** (`7ac7abb8`). 네이버 결제가 전부 취소됐는데 살아 있는 ERP 주문을
처리 탭 위 접힌 띠로 낸다. 스테이징 실화면에서 **3건 확인**:

```
#4467 원주현 2,451,500원  취소 완료 4건 전부  RECEIVED  짝 없음  [주문 취소 처리]
#4462 박선미   579,200원  취소 완료 4건 전부  MEASURE   짝 대기  취소 처리 잠김
#4466 강재상   497,490원  반품 완료 3건 전부  RECEIVED  짝 대기  [주문 취소 처리]
```

`주문 취소 처리` 는 soft delete 다(휴지통 복구). **접수 단계에서만** 열리고 실측 이후는
화면·서버 양쪽에서 잠근다. 신규 mutation 라우트라 계약 4종 등재 + 인벤토리 2종 재생성.

**R-4(네이버 판매자 직접취소)는 사라졌다** — 정리를 ERP 안에서 끝내기로 한 결정의 결과다.
그 대가로 얻은 것이 크다: 불가역 0 · 한 트랜잭션 · 반쪽 상태 원천 차단.
