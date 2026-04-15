# SFC-B0 — Readiness gate + strict interpretation lock

> Batch: `SFC-B0`  
> 실행일: 2026-04-15  
> 입력 문서 (exact path):  
> - `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md`  
> - `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (`§2.2.1`, `§2.2.2`)  
> - `docs/plans/2026-04-15-post-wave9-program3-overlay-minimization-closeout-run-record.md` (간접 선행)  
> - `docs/plans/2026-04-15-post-wave9-program4-final-checklist-closeout-run-record.md` (간접 선행)  
> - `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/harness/policy/DECISIONS.md`

## 1. 목표 (§6.1 대응)

- `SF1`~`SF5`를 **execution-grade**로 잠근다 (아래 §2).
- **Closed root allowlist** (`SF1`)를 본 tranche 동안 변경 불가로 선언한다.
- Git이 빈 디렉터리를 추적하지 못할 때 쓸 **empty directory sentinel policy**를 단일 규칙으로 고정한다.
- **Clean-room** 검증은 `git worktree` 기반으로만 최종 판정한다 (`§6.19` PowerShell recipe).

## 2. Strictness definition (재잠금)

| ID | 이름 | 본 tranche에서의 판정 |
|----|------|----------------------|
| `SF1` | `root-exact-match` | 최종적으로 versioned root artifact는 `§2.2.1` root set + **closed repo-control allowlist**만 허용. 임의 shortlist 확장 금지. |
| `SF2` | `directory-node-minimum` | 스펙에 그려진 directory node는 실제 존재해야 하며, 내용물은 해당 subtree 안에만 있어야 함. |
| `SF3` | `transition-overlay-zero` | closeout 시 `apps/`, root `services/`, root standalone helper, root template debt, root code root `src/` 는 **0**. |
| `SF4` | `canonical-import-zero` | `foms/*`, canonical `templates/*`, canonical `static/*`에서 root helper import·root template path **런타임 의존 0**. |
| `SF5` | `clean-room-proof` | 최종 acceptance는 clean worktree / clean-room clone / `git worktree` 검증에서 재현. |

### 2.1 Closed repo-control allowlist (immutable)

다음 다섯 파일만 루트에 **repo-control** 목적으로 허용된다. 이 목록은 **본 strict tranche 나머지 구간에서 변경 불가**다.

**closed root allowlist is immutable for the rest of this tranche.**

- `.gitignore`
- `.gitattributes`
- `.dockerignore`
- `.gcloudignore`
- `.python-version`

`SF1` 의미에서 위 allowlist **바깥**의 루트 추적 산출물은 “승인되면 유지”가 아니라 이동·삭제·별도 spec clarification 중 하나로만 처리한다 (실행 계획 `§1.2`).

### 2.2 Empty directory sentinel policy (고정)

- **단일 정책**: `§2.2.1`에 필요하지만 Git이 빈 폴더를 못 따라가는 경우, **`.gitkeep` 하나**로만 materialize한다.
- 동일 배치에서 `README.md`만 넣는 방식으로 **혼용하지 않는다** (계획서 `§1.2.1` 항 16 및 `§6.1` step 4와 정합).
- 구체적 파일 생성은 `SFC-B8`/`SFC-B9` 등 해당 materialization 배치에서 수행한다. B0는 정책만 고정한다.

### 2.3 Clean-room verification (고정)

- 최종 `SFC-B12` 판정은 **현재 작업 디렉터리의 dirty 상태가 아닌**, `git worktree add`로 만든 **clean tree**에서 실행 계획 `§6.19`의 `Compare-Object` + `APP_OK` + `verify_result.py --json` 절차로만 한다.

## 3. Root artifact 분류 (5-bucket, §6.1 step 2)

실제 `Get-ChildItem` 기준 루트 디렉터리·파일을 아래로 분류한다. **mandatory 처리**는 본 배치가 아니라 후속 `SFC-B1`~`B12`에서 ledger로 닫는다.

| Bucket | 의미 | 예시 (현재 live에서 존재) |
|--------|------|---------------------------|
| `closed allowlist` | `SF1` repo-control 5종 | `.gitignore` 등 |
| `canonical move` | `§2.2.1` 최종 트리 안의 목표 위치로만 수렴 | `foms/`, `templates/`, `static/`, `docs/` … |
| `quarantine/data/docs/scripts move` | 제품 트리 밖 데이터·문서·스크립트 | `*.md` manual, `*.db`, `*.dump`, `scripts/`·`tools/`로의 이동 대상 |
| `delete-after-proof` | consumer 0 증명 후 제거 | 일부 root helper·레거시 산출물 |
| `requires-spec-clarification` | 스펙과 충돌 시 **느슨하게 해석 금지**; 별도 문서화 필요 | shared-shell `layout`/`error_*`의 B6 분기 (계획 `§6.9`) |

**Branch B (`docs-stop`) 판정**: 본 B0 시점에 `SF1` 밖의 **mandatory** 루트 산출물이 “스펙 없이 영구 유지”를 요구하면 **코드 변경 금지** 분기로 올린다. 현재는 실행 계획 `§2.5` ledger + `§2.2.1`이 이미 모든 major debt에 대해 처리 방향을 제시하므로 **Branch A (full path)** 로 진행한다.

## 4. Branch 판정

- **선택**: **Branch A — full path** (`SFC-B0` → `SFC-B12` 전체 실행 가능).
- **미선택**: Branch B (strict 해석 모호 시 docs-only 중단), Branch C (동작 변경 필요 시), Branch D (batch 분리) — 해당 batch에서 별도 판정.

## 5. 금지 범위 준수 (§6.1)

| 항목 | B0 수행 여부 |
|------|----------------|
| Runtime code 변경 | 없음 |
| template/static/file 이동 | 없음 |
| tests 추가/변경 | 없음 |

허용 변경: 본 파일 + 필요 시 `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md` (본 문서와 정합되는 한 줄 수준).

## 6. SG* scoreboard (본 배치)

- **B0는 scoreboard 수치 확정 배치가 아니다.** `SG1`~`SG7` 수치 확정은 **`SFC-B1`**에서 수행한다.
- 계획서 `§3` provisional baseline은 참고용으로만 유지한다.

## 7. 검증

- Docs-only batch: `rg` / pytest / `APP_OK` **불필요** (코드 미변경).
- 본 문서에 **closed root allowlist is immutable for the rest of this tranche** 문구 포함 (§2.1).

## 8. 다음 legal batch

- **`SFC-B1`** — Exact gap inventory + scoreboard freeze (`docs/plans/2026-04-15-strict-final-canonical-tree-batch1-gap-inventory-run-record.md` 예정).

## 9. Blocker / defer

- 없음. `Wave 9 Option A` packaging defer는 유지되며 본 tranche는 root/canonical physical alignment만 다룬다.

## 10. GDM 감리 Round 1 (§10 대응)

| §10.3 질문 | 결과 |
|------------|------|
| 이 plan만 읽고 다음 batch를 바로 실행할 수 있는가 | 예 — B1은 스캔·ledger만 수행 |
| batch 순서가 잠겨 있는가 | 예 — B0 완료 후 B1 |
| clean-room gate가 정의되어 있는가 | 예 — §6.19 |
| overlay·helper·template debt target 0으로 고정되는가 | 예 — 계획 `§3` |
| `apps/api/**`·shared-shell 경로가 닫혀 있는가 | 예 — 계획 `§6.9`~`§6.15` |
| spec 완화로 debt 숨김 구멍 | 없음 — Branch B/C로 차단 |

**판정**: B0 **합격** (substantive gap 없음). Round 2는 다음 배치(B1) 산출물에 대해 substantive patch만 허용한다.
