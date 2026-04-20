# Wave 6 GDM 하드 감리 보고서 (계획서 §5 — 배치 1:1 대조)

> **감리 유형:** 전수 정합 (계획 `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.1–§5.8 ↔ run record ↔ repo)  
> **기준선 SPEC:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (§1.2.16 `business_calendar` 게이트)  
> **감리 실행일:** 2026-04-13 (본 문서 작성 세션)  
> **결론:** **PASS** (불일치 0건 — 아래 검증 범위 내)

---

## 1. 감리 범위

| 구분 | 내용 |
|------|------|
| 포함 | §5에 정의된 배치 ID(`W6-B0`…`W6-B7`), 각 배치의 **단일 authoritative run record 경로**, §6 Verification Matrix, §1.3 freeze, §5.4/§5.6 code-batch 검증·import smoke |
| 제외 | 과거 세션의 “문서만 요약 감리”, Codex/Claude 병렬 커맨드 정의 전수 (별도 감리 대상) |

---

## 2. 배치별 §5 ↔ run record ↔ 저장소

| Batch | 계획 §5 요구 run record (단일 경로) | 파일 존재 | 계획 대비 요약 |
|-------|-------------------------------------|-----------|----------------|
| W6-B0 | `docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md` | 예 | **Branch A** 채택, first/second pilot 잠금, import debt 중심 `services.business_calendar` — §5.1 분기 표와 다음 legal batch 문구 일치 |
| W6-B1 | `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md` | 예 | root shim registry + README; Branch A full `W6-B1` (§5.2 Branch C 최소 변형 **미해당**) |
| W6-B2 | `docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md` | 예 | docs-only; frozen export `emit_erp_notification_to_users` |
| W6-B3 | `docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md` | 예 | §5.4 허용 경로·검증·concrete import smoke 기록 |
| W6-B4 | `docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md` | 예 | docs-only; `storage` pilot 제외 명시; smoke 심볼 `allowed_file` 고정 |
| W6-B5 | `docs/plans/2026-04-14-wave6-batch5-files-helper-pilot-run-record.md` | 예 | §5.6 허용 경로·검증·import smoke 기록 |
| W6-B6 | `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md` | 예 | §5.7: pilot/precedent/exception/defer 분리, `erp_policy` wrapper vs follow-up 별도 행 |
| W6-B7 | `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md` | 예 | full closeout; dedicated `W6-B6` 인용 (surrogate 불필요) |

**Branch B/C 전용 run record 부재:** 계획 §6에 따라 스킵된 배치는 빈 파일을 만들지 않으며, **해당 없음(Branch A)** — 불일치 아님.

---

## 3. 코드베이스 스포트 체크 (계획 §1.1·§2.3·§5.4·§5.6)

| 계획 기대 | 확인 |
|-----------|------|
| `foms/services/notifications/realtime_notifications.py` + `__init__.py` | 존재 |
| `foms/services/files/file_utils.py` + `__init__.py` | 존재 |
| `business_calendar` package pilot 금지 | `foms/services/common/business_calendar.py` **미생성**; 루트 `services/business_calendar.py` + `from services.business_calendar` 호출부 유지 (explicit exception 경로와 정합) |
| `storage`를 files helper pilot에 혼입하지 않음 | `foms/services/files/`에 `storage` 모듈 **없음**; defer 행만 `W6-B6`에 기록 |
| §1.3 freeze (`app.py`, `foms/platform/blueprints.py`, `run.py`, `start.sh`, `Procfile`, `Dockerfile`, `alembic.ini`, `railway*.toml`) | `git diff HEAD --` 상기 경로 **변경 없음** (빈 diff) |

---

## 4. §6 Verification Matrix — 감리 시점 재실행

감리 세션에서 **동일 워크스페이스** 기준으로 재실행:

| 검증 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `python -m pytest tests/test_realtime_notifications.py tests/test_file_utils.py tests/test_foms_namespace_imports.py -q` | **147 passed** |
| Import smoke (§5.4 / `W6-B3` run record) | `W6_NOTIFICATIONS_NS_OK` |
| Import smoke (§5.6 / `W6-B5` run record) | `W6_FILE_UTILS_NS_OK` |

**참고(메모):** `W6-B3`/`W6-B5` run record에 적힌 pytest 건수(142/144)와 현재 합산 건수는 `test_foms_namespace_imports.py` 등 후속 추가로 달라질 수 있음. **실패가 아니라 스위트 성장에 따른 차이**로 보며, 감리 시점 합산은 모두 통과.

---

## 5. 불일치·오픈 이슈

| ID | 심각도 | 내용 |
|----|--------|------|
| — | — | **불일치 0건** (본 보고서 범위) |

---

## 6. 최종 판정

**PASS** — `2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5에 정의된 배치·산출물·검증·분기(Branch A)와 저장소·run record가 **1:1로 정합**하며, §1.3 freeze 위반 및 scope drift 징후 없음.

후속 권고(필수 아님): Wave 7/8 착수 전 `tests/test_foms_namespace_imports.py` 변경이 늘어날 경우, run record의 pytest 건수는 “스냅샷”으로만 보고 **실제 명령+PASS**를 진실원으로 유지할 것.
