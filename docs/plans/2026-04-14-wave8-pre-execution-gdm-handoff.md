# Wave 8 사전 실행 GDM 핸드오프 (Pre-W8-B0)

> **성격:** 실행(runbook)이 아니라 **Wave 8 코드 배치에 들어가기 직전**의 감독관 체크리스트다.  
> **작성·봉인:** 2026-04-14  
> **Authoritative Wave 8 runbook:** `docs/plans/2026-04-14-wave8-legacy-bridge-retirement-execution-plan.md`  
> **Controlling spec:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (§ Wave 8)

---

## 1. 선행 웨이브 종료 판정 (GDM)

| 선행 | 상태 | 증거 |
|------|------|------|
| Wave 7 closeout (`W7-B6`, `W7-B7`) | **완료** | `docs/plans/2026-04-14-wave7-batch6-status-register-run-record.md`, `docs/plans/2026-04-14-wave7-batch7-closeout-run-record.md` |
| Wave 7 실행 계획 대비 산출 | **완료** | `tests/README.md` (taxonomy·스냅샷), runtime anchor `tests/contracts/runtime/foms_namespace_surface_tests.py`, WDC chunk suites `tests/contracts/wdcalculator/` |
| `docs/AI_STATUS.md` | **Wave 7 반영됨** | 최근 완료 항목에 Wave 7 기록 |
| `docs/ARCHIVE_INDEX.md` | **Wave 7 batch run record 인덱싱됨** | 설계 계획 표 |

Wave 8 계획서 §2.1의 *“Wave 7 closeout이 없으면 W8-B0에서 equivalent evidence를…”* 조항은 **본 핸드오프 시점에서 closeout 존재로 충족**된다. 별도 equivalent evidence waiver 불필요.

---

## 2. Wave 8 계획서 §2.1 입력 묶음 — 파일 존재 확인

아래는 **저장소에 경로가 존재하는지** 기준으로 사전 점검한 목록이다. 실행 세션에서는 **live tree 재수집**이 여전히 필수다.

| # | 산출물 | 확인 |
|---|--------|------|
| 1 | controlling spec | 예 |
| 2 | Wave 6 plan + W6-B1/B6/B7 run records | 예 |
| 3 | Wave 7 plan + W7-B0~B7 run records | 예 |
| 4 | Wave 2 spec-live-reconcile | 예 |
| 5 | Wave 3 files/address/personal_board closeout 증거 | 예 (계획서 §2.1 나열 경로) |
| 6 | Wave 4 measurement/production 관련 run record | 예 |
| 7 | `foms/web/measurement/README.md` | 실행 전 존재 확인 권장 |
| 8 | `foms/platform/blueprints.py` | live |
| 9 | `services/realtime_notifications.py`, `services/file_utils.py`, `foms/services/` 대응 | live |
| 10 | `apps/api/files.py` 등 계획서 열거 bridge 표면 | live |
| 11 | `tests/contracts/runtime/foms_namespace_surface_tests.py` | 예 |
| 12 | `docs/AI_STATUS.md` | 예 |

---

## 3. 알려진 inherited 부채 (Wave 8이 “고쳐야 하는” 전제 아님)

| 항목 | 내용 | Wave 8 본편과 관계 |
|------|------|---------------------|
| `pytest tests --collect-only` | `tests/test_sqlite_startup_compat.py` → `ModuleNotFoundError: safe_schema_migration` | **별도** 루트 shim/경로 정리 이슈. W8-B0 baseline은 계획서대로 **green / inherited-red** 명시 가능. |
| Wave 5 W5-B4 | estimate-lifecycle 청크 | **Wave 5 제품 축** 연속 작업. Wave 8 mainline과 **혼동 금지** (계획서 pilot-cap). |

---

## 4. 실행 시작의 정의 (혼동 방지)

- **“Wave 8 실행” = `W8-B0` Readiness gate run record 작성 + authoritative bridge queue lock + 분기 판정**부터다.  
- 그 **전에** 코드·`services/`·`apps/`·`foms/`·blueprint import를 바꾸면 **범위 위반**이다.

---

## 5. 권장 첫 명령 (W8-B0 세션 내부)

저장소 루트(PowerShell, `;` 연결):

```powershell
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
python -m pytest tests/test_foms_namespace_imports.py tests/test_app_bootstrap_contract.py -q
```

`tests --collect-only`는 inherited-red 허용 시 **실패 출력을 run record에 그대로 첨부**한다.

---

## 6. GDM 봉인 문구

**Wave 7 선행 조건은 충족되었고, Wave 8은 authoritative runbook에 따라 `W8-B0`부터 순차 실행할 수 있는 준비 상태다.**  
다음 작업은 **새 코드가 아니라 `W8-B0` run record 초안 + live bridge 스냅샷 + branch 판정**이다.
