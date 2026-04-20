# SFC-B12 — Clean-room exact-match audit + closeout (run record)

> 입력: `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §**6.19**, `SG1`–`SG7` 정의(동일 문서 §2.5), B1 baseline `docs/plans/2026-04-15-strict-final-canonical-tree-batch1-gap-inventory-run-record.md`

## 1. Family / risk axis

- **Risk axis:** root exact-match (`SF1` / `SG5` / `SG6`) + canonical import surface (`SG2` 일부: 주소 AI 루트 시므).
- **Code family:** 루트 `foms_address_learning.py`, `foms_advanced_address_processor.py` 제거 — 구현 단일 소유는 기존과 같이 `scripts/ops/*.py`.

## 2. 잔여 블로커 (B12 직전)

- PowerShell `§6.19` `$allowedRoot` 대비 **working tree** 실측: `foms_address_learning.py`, `foms_advanced_address_processor.py` **2건만** 초과 (`Compare-Object` `=>`).
- 구현은 이미 `scripts/ops/`에 있었고, 루트 파일은 Wave 1 호환 **시므**였음.

## 3. 수행 변경

| 파일 | 조치 |
|------|------|
| `foms/services/common/address_ai_ops_loader.py` | **신규** — `scripts/ops/foms_address_learning.py`, `foms_advanced_address_processor.py`를 `importlib`로 로드해 `FOMSAddressLearningSystem`, `FOMSAdvancedAddressProcessor` 노출 |
| `foms/services/common/address_converter.py` | 루트 시므 import 제거 → `address_ai_ops_loader`에서 import |
| `foms_address_learning.py` (루트) | **삭제** |
| `foms_advanced_address_processor.py` (루트) | **삭제** |

금지 범위: 새 루트 시므 없음, 제품 동작/라우트/JSON 계약 변경 없음(import 경로만 canonical 측으로 수령).

## 4. SG scoreboard (이번 배치에서 직접 재측정한 항목)

| ID | 측정 | 결과 | 비고 |
|----|------|------|------|
| `SG1` | `Test-Path` `apps`,`services`,`src` | **0** (오버레이 디렉터리 없음) | B11B/C/D 이후 물리 트리와 일치 |
| `SG5` / `SG6` | `§6.19` `$allowedRoot` vs 루트 `Get-ChildItem` (`.git`/로컬 캐시 제외) `Compare-Object` | **0 diff** | 잔여 2파일 제거 후 |
| `SG2`–`SG4`, `SG7` | `pytest tests` 내 strict canonical 계약 | **통과** (전체 586 passed) | `foms_namespace_surface_tests.py` 등으로 B1 이후 축 동결 |

`SG6`는 계획상 “clean-room에서의 exact-match”이므로, **동일 바이트의 재현**은 **`git commit`된 스냅샷**에서 `git worktree add <path> <commit>`로 재실행하는 것이 정식 절차다. 현재 저장소에는 미커밋 변경이 많을 수 있으므로, **CI/릴리스 게이트**는 해당 커밋 기준으로 `§6.19` recipe를 한 번 더 돌릴 것을 권장한다.

## 5. 검증 명령 (실행 시점)

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests -q   → 586 passed
```

## 6. 다음 legal batch / 종료 선언

- **Strict canonical tree tranche**에서 계획서가 요구하는 코드 배치는 **본 기록 시점에서 closeout**으로 간주 가능(계약 테스트 + 루트 allowlist 일치).
- 후속은 **운영 절차**만: 변경분 커밋 후 `git worktree` clean-room에서 `§6.19` 3줄 블록 재실행해 로그 보관.

## 7. 남은 blocker

- **없음** (본 working tree 기준). 미커밋 상태와 `origin/HEAD` 불일치 시 별도 맞춤만 필요.

## 8. Committed HEAD clean-room proof (재현)

- **브랜치:** `feature/modular-monolith-wip`
- **HEAD:** `b7014c74` (직전 대형 스냅샷: `214654c9`, `.vscode` 루트 고정: `b7014c74`)
- **블로커 해소:** 스펙 §2.2.1에 `.vscode/`가 있으나 기존 `.gitignore`가 폴더 전체를 무시해 clean worktree에 `.vscode`가 없었음 → `.vscode/settings.json` 등 공유 파일만 추적하도록 `.gitignore` 조정 후 §6.19 `Compare-Object` zero diff 달성.
- **명령:**

```text
powershell -NoProfile -File tools\harness\strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest
```

- **결과:** `[strict_canonical_b12] Compare-Object: OK` → `APP_OK` → `verify_result.py --json` success → `586 passed` → **`CLEAN_ROOM_OK ref=HEAD`**
- **원격:** `origin/feature/modular-monolith-wip` 에 `b7014c74` 반영됨 (`git push`).
- **문서 갱신 tip:** `b9873290` (batch12 run record §8 + `AI_STATUS`) — 루트 트리 동일·`strict_canonical_b12_clean_room.ps1 -Ref HEAD`(pytest 생략) **`CLEAN_ROOM_OK`** 재확인.
- **최종 tip:** `98e2606f` — §8 tip 한 줄 보강만 추가(루트 트리 불변).

## 9. Plan §12 Completion Signal — final declaration

Authoritative 계획서 `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` **§12 Completion Signal** 중 **항목 8**에 따라, 본 문서를 **final closeout run record**로 둔다.

**선언:**

> **strict physical-tree achieved**

**근거 (§12 1–7과 대응):** `§2.2.1` 디렉터리 노드·`§2.2.2` 오버레이·canonical root-helper·root template debt·`SF1` 비스펙 추적 산출물·clean-room exact-match·루트 plain template 조건은 SFC-B0~B12 실행·계약 테스트·본 문서 §4~§8·`docs/AI_STATUS.md` 기록과 일치한다. SG1~SG7 및 `CLEAN_ROOM_OK` 증거는 §4·§8.

**최종 검증:** 원격 `feature/modular-monolith-wip` **최신 HEAD** (§9 `strict physical-tree achieved` 선언·100% 계획서 §2 closeout 각주가 포함된 커밋 이상; 로컬 확인: `git rev-parse origin/feature/modular-monolith-wip`).
