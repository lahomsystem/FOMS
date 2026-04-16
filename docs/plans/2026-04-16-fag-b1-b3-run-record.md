# FAG-B1 / FAG-B2 / FAG-B3 — Run Record

> 작성일: 2026-04-16
> 상위 계획: `docs/plans/2026-04-16-strict-final-canonical-tree-final-audit-gap-closure-plan.md`
> HEAD: `891c1a68` (FAG-B2 커밋)
> pytest: **607 passed**
> Historical note: 이 문서는 `FAG-B1`–`FAG-B3` 시점 기록이다. 최종 current truth는 `docs/plans/2026-04-16-fag-b4-run-record.md`를 따른다.

## FAG-B1 — FR20 README uniqueness closure

### 작업 내역

| 작업 | 결과 |
|------|------|
| `static/js/wdcalculator/README.md` 내용을 `docs/context/wdcalculator-static-js-chunk-map.md`로 이동 | 완료 (git rename으로 추적) |
| `static/js/wdcalculator/README.md` 제거 | 완료 (`git rm`) |
| `foms/web/wdcalculator/README.md` 읽기 순서 line 4 chunk-map 경로로 갱신 | 완료 |
| `test_ptc_physical_exactness.py`에 FAG-B1 uniqueness gate 2개 추가 | 완료 |
| docs/plans/2026-04-16-strict-final-canonical-tree-final-audit-gap-closure-plan.md 커밋 | 완료 |

### 검증

| Gate | 결과 |
|------|------|
| `pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q` | **7 passed** |
| `python -c "import app; print('APP_OK')"` | **APP_OK** |
| `static/js/wdcalculator/README.md` 부재 확인 | ✓ |
| `docs/context/wdcalculator-static-js-chunk-map.md` 존재 확인 | ✓ |
| `foms/web/wdcalculator/README.md` sole authoritative home | ✓ |

### 커밋

`366c000e` feat: FAG-B1 FR20 README uniqueness closure — static/js/wdcalculator/README.md 제거

---

## FAG-B2 — Workspace hygiene closure

### 작업 내역

| 작업 | 결과 |
|------|------|
| `data/ops_browser_qa.db` 제거 (workspace, gitignored) | 완료 |
| `ptc_workspace_cleanup.ps1 -RecursePyCache` 실행 | 완료 (전 `__pycache__` 제거) |
| `ptc_workspace_cleanup.ps1` — `.claude/` 제외 추가 | 완료 (root cause fix) |
| `ptc_workspace_hygiene_probe.ps1` — `.claude/` 제외 추가 | 완료 (root cause fix) |

**Root cause 설명:**
`.claude/hooks/`는 Claude Code 툴체인 훅 디렉터리다. 세션 중 `track_edits.py`·`session_stop.py` 등 훅이 자동 실행되면서 `__pycache__`를 지속적으로 재생성한다. `.git/`, `venv/`, `node_modules/`를 제외하는 것과 동일한 원칙으로 `.claude/`를 재귀 스캔 대상에서 제외하는 것이 올바른 근본 수정이다.

### 검증

| Gate | 결과 |
|------|------|
| `ptc_workspace_cleanup.ps1 -RecursePyCache` | **OK** (잔류 없음) |
| `ptc_workspace_hygiene_probe.ps1 -RecursePyCache` | **OK** |
| `data/ops_browser_qa.db` 부재 | ✓ |
| `git status --short --ignored` | `.agents/skills/gstack-*` gitignored만 (외부 툴체인) |

### 커밋

`891c1a68` feat: FAG-B2 Workspace hygiene closure — .claude/ 제외 및 probe green

---

## FAG-B3 — Evidence/document sync closure

### 작업 내역

| 작업 | 결과 |
|------|------|
| `docs/plans/2026-04-16-ptc-b7-run-record.md` — stale HEAD lag warning 제거 | 완료 |
| `docs/AI_STATUS.md` top summary — FAG closeout truth(`891c1a68`, 607 passed)로 교체 | 완료 |
| `docs/ARCHIVE_INDEX.md` — FAG-B1~B3 run record 포인터 추가 | 완료 |
| 본 run record 생성 | 완료 |

### 동기화 확인

| 축 | 값 |
|---|----|
| current HEAD | `891c1a68` |
| `pytest tests -q` | **607 passed** |
| `ptc_workspace_hygiene_probe.ps1` | **OK** |
| AI_STATUS top summary | FAG closeout truth (`891c1a68`, 607 passed) |
| PTC-B7 run record | HEAD lag warning 제거, FAG evidence 추가 |
| ARCHIVE_INDEX | FAG-B1~B3 run record 항목 추가 |

**5개 축 1:1 일치 확인:** current HEAD / pytest count / workspace hygiene / AI_STATUS / run record ✓

---

## Historical handoff (superseded by FAG-B4)

- 당시 다음 단계는 `strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest` 재실행과 final GDM 1:1 audit이었다.
- 최종 closeout은 이후 `docs/plans/2026-04-16-fag-b4-run-record.md`에서 current `HEAD` `4c3aaffb` 기준으로 완료됐다.
