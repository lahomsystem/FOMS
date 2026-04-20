# 프로젝트 전체 변화 분석

> 기준 범위: `eb01c5d7` (프로젝트 시작) → `4c3aaffb` (현재 HEAD, FAG-B4 closeout)
> 작성일: 2026-04-16
> 브랜치: `feature/modular-monolith-wip`

---

## 수치 요약

| 항목 | 이전 (`eb01c5d7`) | 현재 (`4c3aaffb`) | 변화 |
|------|------|------|------|
| 커밋 수 (이 브랜치) | — | +44 커밋 | |
| 변경 파일 수 | — | 972개 | 523 추가 / 59 삭제 / 313 이동 / 77 수정 |
| 총 diff | — | +83,769 / −23,399 | |
| 루트 Python 파일 | **27개** | **6개** | −21 |
| 루트 진입 엔트리 전체 | **70+개** | **37개** | −33 |
| `app.py` 줄 수 | **480줄** | **79줄** | −84% |
| `tests/` Python 파일 수 | **32개** | **85개** | +166% |
| pytest 통과 수 | (wave1 기준 545) | **607 passed** | +62 |
| `foms/` 패키지 | **없음** | **47개 디렉터리** | 신규 |
| `apps/` 디렉터리 | **존재 (~50 모듈)** | **없음** | 완전 제거 |
| `services/` 루트 flat 파일 | **50개** | **없음** | 완전 제거 |
| `foms/services/` Python 파일 | — | **81개** | 계층화 |
| `static/js/wdcalculator/*.js` | **0개** (분산 없음) | **7개** (4 canonical chunk) | 정비 |
| `templates/` 루트 `.html` | **40개** | **0개** | 전부 이동 |
| `constants.py` 루트 | **104줄 단일 파일** | **없음, 4개 모듈 분산** | 분해 |

---

## 1. 개선된 것 (확실한 성과)

### A. 루트 오염 제거 — 가장 큰 성과

**이전**: 루트에 `erp_automation.py`, `migrate_*.py`, `foms_address_converter.py`,
`railway_bootstrap.py`, `simple_backup_system.py` 등 **27개 Python 파일**이 난잡하게 위치.
`.docx`, `.bat`, 진단 txt 파일들도 루트에 혼재.

**현재**: 루트 Python 파일 6개만 남음.

```
app.py  db.py  models.py  run.py  wdcalculator_db.py  wdcalculator_models.py
```

나머지는 `scripts/`, `docs/`, `foms/` 등 올바른 위치로 이동.

---

### B. `app.py` 480줄 → 79줄 (thin adapter)

**이전 `app.py`에 직접 있던 것들**:
- `@app.before_request` / `@app.after_request` / `@app.errorhandler`
- Blueprint import + `register_blueprint()` 30+회
- 비즈니스 로직 함수
- gevent 패치, werkzeug 패치, Socket.IO 초기화, WhiteNoise 설정 등 모두 한 파일

**현재 플랫폼 레이어로 분리**:

| 파일 | 역할 |
|------|------|
| `foms/platform/app_factory.py` (96줄) | Flask app 생성·미들웨어·bootstrap 오케스트레이션 |
| `foms/platform/blueprints.py` (162줄) | 전체 Blueprint 등록 단일 진실 |
| `foms/platform/http.py` | request hook·error handler·favicon·`__build` |
| `foms/platform/realtime.py` | Socket.IO·limiter 초기화 |
| `app.py` (79줄) | gevent 패치 + `build_app()` 호출만 |

---

### C. `apps/` 완전 폐기 → `foms/api/` + `foms/web/`

**이전**: `apps/` 아래 50+개 Blueprint 모듈이 비즈니스 로직을 직접 소유.

**현재**:

```
foms/api/   — API Blueprint canonical owner
  channel/, files/, orders/, measurement/, shipment/, ...

foms/web/   — Web page Blueprint canonical owner
  admin/, auth/, construction/, cs/, drawing/,
  measurement/, orders/, production/, shipment/, wdcalculator/
```

`apps/` 디렉터리 **완전 삭제됨.**

---

### D. `services/` flat 50개 → `foms/services/` 계층화 81개

**이전**: `services/channel_delivery.py`, `services/erp_policy.py` 등 flat하게 쌓여 있었음.

**현재**: `foms/services/` 아래 도메인별 서브패키지:

```
admin/      auth/       channel/    common/
files/      jobs/       notifications/   orders/
```

- `erp_policy` → `foms/services/orders/erp_policy_*.py` (flat leaf로 분해)
- `constants.py` (단일 104줄) → `status_constants.py`, `upload_policy.py`,
  `storage_paths.py`, `erp_policy_constants.py` 4개 모듈로 분산

---

### E. `templates/` 루트 HTML 40개 → 0개

**이전**: 루트 `templates/`에 HTML이 난잡하게 쌓여 있었음.

**현재**: context별 폴더로 완전 분류.

```
templates/
  orders/   measurement/   channel/   production/
  construction/   cs/   drawing/   shipment/
  admin/   auth/   wdcalculator/   partials/
```

---

### F. WDCalculator JS — 분산 파일 → 4 canonical chunk

**이전**: `static/js/wdcalculator/` 없음, 대형 inline script.

**현재**: Wave 5에서 56개 micro 파일을 4개로 수렴.

| Chunk | 흡수 모듈 수 |
|-------|------|
| `composition.js` | 22개 bootstrap/host-bootstrap 밴드 |
| `estimate-lifecycle.js` | 18개 lifecycle/state/save 밴드 |
| `primary-form.js` | 7개 input-form 밴드 |
| `pricing-core.js` | 6개 math/totals/orchestration 밴드 |

기술 문서는 `docs/context/wdcalculator-static-js-chunk-map.md`.

---

### G. 테스트 인프라 대폭 강화

**이전**: 32개 Python 테스트, 주로 도메인 smoke test.

**현재**: 85개 파일 + contract test 레이어 추가.

```
tests/contracts/runtime/foms_namespace_surface_tests.py  — 185 gate
tests/contracts/runtime/test_ptc_physical_exactness.py   — 7 gate
tests/contracts/wdcalculator/                            — JS chunk contract 4종
tests/domains/                                           — 기존 도메인 테스트 유지
```

**pytest 통과 수 추이**:

```
프로젝트 시작 (추정)   ~450
Wave 1 closeout       545 passed
SFC/SLG tranche       586 passed
PAC closeout          600 passed
PTC+FAG closeout      607 passed  ← 현재
```

---

### H. 하네스 인프라 완비

**이전**: `.claude/`에 agents/commands만 있었음. hooks 없음.

**현재**:

```
.claude/hooks/
  guard_shell.py      — PreToolUse:Bash 위험 명령 차단
  track_edits.py      — PostToolUse:Edit|Write EDIT_LOG 기록
  session_stop.py     — Stop SESSION_LOG + 임시파일 정리
  quality_check.py    — Stop 품질 체크 리마인더

tools/harness/
  strict_canonical_b12_clean_room.ps1   — HEAD clean-room 검증
  ptc_workspace_cleanup.ps1             — workspace residue 제거
  ptc_workspace_hygiene_probe.ps1       — workspace hygiene 게이트
  run_codex.ps1                         — Codex 4단계 자동 분류
```

---

### I. 문서 체계화

**이전**: 루트에 `.docx`, `DEPLOYMENT_GUIDE.md`, `TEST_GUIDE.md` 등 산재.

**현재**: 명확한 docs 계층 구조.

```
docs/
  AI_STATUS.md        — 프로젝트 현재 상태 (living doc)
  AI_CHANGELOG.md     — 작업 이력
  ARCHIVE_INDEX.md    — 과거 기록 목차
  guides/             — 운영·배포·마이그레이션 가이드
  specs/              — 구현 스펙 문서
  plans/              — 실행 계획·run record
  context/            — 기술 분석·참고 문서
  harness/            — 하네스 정책·로그
  evolution/          — 기술 감사·리서치
```

---

## 2. 잘못된 점 / 남은 문제

### 문제 1: `data/` 런타임 DB 재생성 가능성

`.gitignore`에 `*.db`가 있어 git 추적은 막지만,
운영 중 `data/ops_browser_qa.db`가 workspace에 다시 생성될 수 있음.
`FOMS_RUNTIME_OUTPUT_ROOT` contract(PTC-B5)로 방향을 잡았으나,
실제 도구·가이드에서 완전히 reroute됐는지 지속 모니터링 필요.

### 문제 2: SQLAlchemy LegacyAPIWarning 잔존

```python
# foms/services/channel_inbound.py:209
log = db.query(ChannelInboundEventLog).get(log_id)
```

SQLAlchemy 2.0 기준으로 아래로 교체 필요:

```python
log = db.session.get(ChannelInboundEventLog, log_id)
```

pytest 매 실행마다 warning 3건 출력됨. 즉시 깨지진 않으나 기술 부채.

### 문제 3: `backups/`에 구 `constants.py` import 잔존

```
backups/tier1_primary/system_files/app.py
backups/tier2_secondary/system_files/app.py
```

`from constants import ...` 패턴 잔존. `backups/`는 frozen snapshot이므로
프로덕션 영향 없음. 단, 코드 정확성 기준으로는 낡은 상태.

### 문제 4: `foms_namespace_surface_tests.py`에 `from apps.` 참조 잔존

```
tests/contracts/runtime/foms_namespace_surface_tests.py
```

legacy shim 검증 목적으로 `from apps.` import를 참조하는 부분이 남아있음.
`apps/` 디렉터리가 삭제된 현재 구조에서 이 참조가 shim 경유인지
직접 참조인지 확인 및 정리 필요.

### 문제 5: `wdcalculator_db.py`, `wdcalculator_models.py` 루트 잔존

루트 allowlist에 명시적으로 포함되어 있지만, `foms/` 패키지 밖에 있는 이유가
packaging defer(`Option A`, Wave 9) 때문임. 실질적 기술 부채로 남아있음.
향후 `foms/persistence/wdcalculator`로 이동 필요하나 현재 의도적 defer 상태.

### 문제 6: `foms/api/`에 flat 파일과 패키지 혼재

```
foms/api/address.py     ← flat 파일
foms/api/files/         ← 패키지
foms/api/backup.py      ← flat 파일
foms/api/orders/        ← 패키지
```

Wave 3~4에서 pilot 완료된 contexts(패키지 형태)와
defer된 contexts(flat 파일)가 혼재. 시각적 일관성 낮음.

### 문제 7: `foms/services/erp_policy.py` public surface와 내부 구현 두 레벨 공존

`foms/services/erp_policy.py`가 public surface로 유지되면서
내부 구현은 `foms/services/orders/erp_policy_*.py`로 분산됨.
SLG-B6에서 의도적 설계이나 두 레벨이 공존하는 구조로 가독성 낮음.

---

## 3. 아직 미완성인 것 (의도적 defer)

| 항목 | defer 기록 |
|------|------|
| `notifications/`, `attachments/` high-risk cluster 완전 정리 | WR-H1 |
| `jobs/` runtime-string contract 제거 | WR-J1 |
| packaging: `pyproject.toml` + `src/foms` src-layout | Wave 9 Option A |
| static CSS shell (`erp.css`, layout JS) 분리 | W5-B9 |
| `foms/api/` flat 파일들의 패키지화 | 미지정 |
| SQLAlchemy 2.0 `.get()` → `session.get()` 전환 | 미지정 |

---

## 4. 전체 평가

**구조 개선 달성도**: 매우 높음.

flat 모놀리스(`apps/` + `services/` + 루트 스크립트 난잡) →
계층화된 `foms/platform / api / web / services/` 구조로 전환 완료.

**증명 수준**: 이전에는 검증 체계 자체가 없었음. 현재는 3중 검증 체계 구축.

```
clean-room (strict_canonical_b12_clean_room.ps1)   — HEAD committed snapshot 검증
workspace hygiene probe (ptc_workspace_hygiene_probe.ps1) — 물리 workspace 검증
pytest 607 passed                                  — 런타임 contract 검증
```

**실질적 위험**: SQLAlchemy LegacyAPIWarning(경고 수준, 즉시 깨지지 않음),
`data/` 런타임 DB 생성 패턴(운영 중 재생성 가능), `backups/` 구 코드 참조(비프로덕션).
셋 모두 서비스 중단 수준의 차단 이슈는 아님.
