# ERP Slowdown Radar + Perf Skills Upgrade Spec
> 작성일: 2026-06-30 | 상태: ✅ 완료

## 0. North Star (철학)

**목표:** deploy 직후 “전체 ERP 로딩/체감 느려짐” 재발을 **deploy 전에 거의 확실히 차단**한다.

**근거 사고 (2026-06 실제 사고):**
- 기능·서버 TTFB는 정상인데 deploy 후 전체가 느려짐 (html2canvas + 공유 partial, SW 무 timeout, JSONB ILIKE).
- “느려짐 ≠ 서버 느림” — Amplifier / Masking / Scale cliff 3 클래스.

**전략:** incident-only block **+** ERP 8차원 broad radar **+** fail-closed 4층 gate.

| 스킬 | 역할 | deploy |
|------|------|--------|
| **perf-guard** | 이번 diff가 proven/high-confidence 회귀인가 (veto) | **배포 가능 / 배포 금지** (이진) |
| **perf-audit** | 코드베이스 ERP slowdown 레이더 + hot path 실측 | production 승격 전 필수 |

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물

1. **`docs/guides/ERP_SLOWDOWN_RADAR.md`** (~100줄)  
   ERP 8차원 taxonomy, hot path 정의, severity 정책, 측정 ladder SSOT.

2. **`tools/perf/perf_scan.py` 확장**
   - finding에 `dimension` 필드 (8차원 태그).
   - `--radar`: 차원별 요약 JSON/텍스트 (audit companion).
   - `--audit`: fragment-replayed listener 전체 스캔 (guard와 동일 로직).
   - **B-layer** 정적 규칙 추가 (audit=전체, guard=hot path 신규 high만).

3. **스킬 4-way sync** (각 SKILL/command **≤100줄**, 상세는 `references/` JiT)
   - `~/.codex/skills/perf-guard/` + `perf-audit/`
   - `.claude/commands/perf-guard.md`, `perf-audit.md`
   - (선택) `.cursor/skills/perf-guard/`, `perf-audit/` — repo 공유

4. **`PERFORMANCE_GUARDRAILS.md` 보강**  
   §점검 절차 A/B 첫 줄에 north star + `ERP_SLOWDOWN_RADAR.md` 링크.

5. **`tests/performance/test_perf_scan.py`** (신규)  
   규칙·`--radar`·audit fragment scan 회귀 테스트.

### 1.2 기능 요구사항

#### F1. ERP 8차원 Taxonomy (모든 finding/tag에 적용)

| dimension | 설명 | 대표 탐지 |
|-----------|------|-----------|
| `amplifier` | 공유면 → 전 사용자/전 탭 | shared partial script/CSS |
| `render-block` | TTFB OK, 클라이언트 지연 | sync script, blocking CSS |
| `interaction-debt` | 탭/입력 버벅 | fragment listener, polling |
| `sw-cache` | SW/캐시 전략 | no-cache, networkFirst |
| `query-scale` | N↑ cliff | ilike, .all(), N+1 loop |
| `payload` | 과대 응답/HTML | unbounded query, fat render |
| `hot-compute` | 매요청 집계 | no cache pattern |
| `io-bound` | upload/attachment | sync batch (후순위) |

#### F2. perf-guard (deploy veto)

4층 gate — **한 층이라도 미충족 = 배포 금지:**

```
L1  python tools/perf/perf_scan.py --guard [--base origin/deploy] [--json]
L2  diff blast-radius (trigger matrix) + PERFORMANCE_GUARDRAILS §A 수동 전항
L3  powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1
L4  production 승격 전: perf-audit + staging 실측 (guard만으로 production 금지)
```

- verdict: **`배포 가능` | `배포 금지`** only (WARN=배포 금지+follow-up).
- proven G1–G4 + hot path B-layer **high** → L1 exit 1.

#### F3. perf-audit (ERP Slowdown Radar)

```
L1  python tools/perf/perf_scan.py --audit [--json]
L2  python tools/perf/perf_scan.py --radar [--json]   # 차원별 요약
L3  references/erp-slowdown-radar.md JiT — 8차원 deep checklist
L4  hot path: TTFB → EXPLAIN → Chrome SW → 탭전환 (field > lab)
```

- `--audit` exit 0 유지 (advisory) but **high findings = deploy 리스크** 명시.
- 수정 후 perf-guard + smoke 재실행.

#### F4. perf_scan B-layer 규칙 (1차 구현 범위)

| rule id | severity (audit) | guard (diff+hot) | pattern/로직 |
|---------|------------------|------------------|--------------|
| `general-ilike` | medium | high if hot | `.ilike(` (exclude `# perf-ok`) |
| `loop-db-query` | medium | high if hot | `for` block 내 `.query(` / `db.session` |
| `shell-polling` | medium | high | shell JS `setInterval(` without guard |
| `shared-inline-script` | medium | high | shared partial inline `<script>` >20 lines |
| `sw-network-first-no-timeout` | high | high | SW `networkFirst` without timeout symbol |
| (기존 6 rules) | 유지 | 유지 | G1–G4 매핑 유지 |

**Hot path prefixes:**
`templates/partials/shared/`, `erp_order_js`, `foms_app_shell`, `erp_mobile_shell`,
`static/sw.js`, `services/dashboard`, `services/search`, `foms/api` list/search routes.

**Baseline freeze:** audit 기존 hit는 `tools/perf/baseline_debt.json`에 ID 고정 → guard는 **신규**만 high.

#### F5. `--radar` 출력 (예)

```json
{
  "dimensions": {
    "query-scale": {"high": 2, "medium": 15, "top_files": ["..."]},
    "amplifier": {"medium": 8, "shared_partial_kb": 420}
  },
  "hot_paths_unmeasured": ["/erp/dashboard", "..."],
  "deploy_risk_summary": "..."
}
```

### 1.3 예외/제약

- **guard에 medium 전체 block 금지** — CI/pre_push_smoke 마비 방지.
- **production push** — 사용자 명시 승인 전 금지 (AGENTS.md).
- **헤드리스 SW 검증 금지** — 실 Chrome only.
- **dev 절대 시간 신뢰 금지** — staging TTFB.
- perf 스킬 본문 **100줄 초과 금지** — `references/` 분리.
- `# perf-ok`, allowlist escape는 **사유+리뷰** 필수.

---

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일

| 파일 | 변경 |
|------|------|
| `docs/guides/ERP_SLOWDOWN_RADAR.md` | **신규** SSOT taxonomy + hot path + severity |
| `docs/guides/PERFORMANCE_GUARDRAILS.md` | north star 1문단, radar 링크, §A/B 1줄 보강 |
| `tools/perf/perf_scan.py` | dimension, B-rules, `--radar`, audit fragment scan |
| `tools/perf/baseline_debt.json` | **신규** audit debt freeze IDs |
| `tools/perf/rules/` (optional) | 규칙 YAML 분리 — 1차는 perf_scan.py inline 유지 |
| `tests/performance/test_perf_scan.py` | **신규** scanner unit tests |
| `tests/performance/test_perf_regression_guard.py` | 변경 최소 (SW timeout rule align만) |
| `~/.codex/skills/perf-guard/SKILL.md` | deploy veto 철학 + 4층 gate |
| `~/.codex/skills/perf-guard/references/` | trigger-matrix.md, manual-checklist.md |
| `~/.codex/skills/perf-audit/SKILL.md` | 8차원 radar workflow |
| `~/.codex/skills/perf-audit/references/` | erp-slowdown-radar.md, measurement-ladder.md |
| `.claude/commands/perf-guard.md` | Codex SKILL과 동기화 |
| `.claude/commands/perf-audit.md` | Codex SKILL과 동기화 |
| `.cursor/skills/perf-guard/SKILL.md` | (선택) repo-local Cursor parity |
| `.cursor/skills/perf-audit/SKILL.md` | (선택) repo-local Cursor parity |

### 2.2 아키텍처

- **SSOT:** `PERFORMANCE_GUARDRAILS.md`(incident+gate) + `ERP_SLOWDOWN_RADAR.md`(taxonomy).
- **엔진:** `perf_scan.py` 단일 CLI (도구 무관) — skills는 thin wrapper.
- **강제:** `test_perf_regression_guard.py` = proven G1–G4 only (변경 최소).
- **확장:** B-layer + radar = audit advisory; hot path 신규만 guard high.
- **패턴 준수:** `# perf-ok`, allowlist, singleton `window.__*_BOUND` 기존 convention.

### 2.3 의존성·영향

- DB/API/Auth **변경 없음** — docs + tools + tests + skills only.
- pre_push_smoke subset에 `test_perf_scan.py` **추가 검토** (optional phase 2).
- harness bundle 문서는 SSOT 링크만 (bundle 8곳 전체 sync는 범위 외).

---

## 3. Steps — CEO 순차 구현 (승인 후)

### Phase 0 — Research lock (완료)
- [x] 2026-06 incident 3종 + perf_scan gap 분석
- [x] 8차원 taxonomy + 4층 gate 설계

### Phase 1 — SSOT 문서 (~30min)
- [ ] `ERP_SLOWDOWN_RADAR.md` 작성
- [ ] `PERFORMANCE_GUARDRAILS.md` 링크/north star 보강

### Phase 2 — 엔진 (~2h)
- [ ] `Finding`에 `dimension: str` 추가
- [ ] B-layer 규칙 + hot path helper
- [ ] `audit()` → fragment listener scan 공유 함수 추출
- [ ] `--radar` 구현 + `--json` schema
- [ ] `baseline_debt.json` 생성 (1차 audit 스냅샷에서 seed)

### Phase 3 — 테스트 (~1h)
- [ ] `test_perf_scan.py`: 각 rule smoke, radar JSON keys, audit fragment
- [ ] `test_perf_regression_guard.py` 기존 4 tests green 유지

### Phase 4 — 스킬 (~1h)
- [ ] Codex perf-guard/audit SKILL + references (≤100줄 본문)
- [ ] Claude commands sync
- [ ] (선택) `.cursor/skills/` repo copy

### Phase 5 — 1:1 소스코드 리뷰 (구현 직후)
- [ ] **cavecrew-reviewer** diff review (severity/dimension/tag 정확성)
- [ ] **bugbot** optional — false positive 위험 규칙
- [ ] 수동: guard exit code matrix, audit≠guard parity on fragment scan

### Phase 6 — Full inspection (deploy push 전)
```powershell
python -c "import app; print('APP_OK')"
python tools/perf/perf_scan.py --guard
python tools/perf/perf_scan.py --audit
python tools/perf/perf_scan.py --radar --json
python tools/perf/perf_scan.py --guard   # exit 0
python -m pytest tests/performance/test_perf_scan.py tests/performance/test_perf_regression_guard.py -q
python tools/perf/perf_scan.py --guard   # perf guard on changed files
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1
python tools/harness/verify_result.py --json
```

### Phase 7 — Deploy push (승인 + inspection exit 0 후)
- [ ] UTF-8 commit message file → `git commit -F`
- [ ] **`git push origin deploy`** (스테이징만; production 명시 요청 전 금지)

---

## 4. 검증 기준 (Acceptance)

| # | 기준 | 명령/증거 |
|---|------|-----------|
| A1 | APP import | `python -c "import app; print('APP_OK')"` |
| A2 | guard proven block | 의도적 sync script fixture → exit 1 |
| A3 | audit fragment scan | replayed JS unguarded listener → finding |
| A4 | `--radar` | 8 dimension keys in JSON |
| A5 | B-layer hot path | diff in `services/dashboard` + loop query → guard high |
| A6 | B-layer cold | tests/ loop query → audit only, guard pass |
| A7 | regression guard | 4 existing G tests pass |
| A8 | smoke | `pre_push_smoke.ps1` exit 0 |
| A9 | skill line count | each SKILL.md ≤100 lines |
| A10 | SSOT drift | Claude command ≡ Codex SKILL workflow |

---

## 5. 리스크·롤백

| 리스크 | 완화 | 롤백 |
|--------|------|------|
| B-layer false positive flood | hot path only + baseline_debt | rule severity ↓ 또는 baseline expand |
| guard CI block | proven+hot high only | `--guard` rule revert |
| audit noise | `--radar` summary만 주간 사용 | audit rules off |
| skill token bloat | references/ JiT | 본문 축소 |
| Codex path outside repo | Claude+repo docs SSOT | Codex skill manual copy |

---

## 6. Open Questions (승인 시 확정 필요)

| # | 질문 | 권장 default |
|---|------|--------------|
| Q1 | repo `.cursor/skills/` 추가? | **Yes** — 팀 Cursor parity |
| Q2 | `test_perf_scan.py`를 pre_push_smoke subset 추가? | **Phase 2** — 1차는 local full inspection only |
| Q3 | shared partial **KB budget** (e.g. +50KB block)? | **Phase 2** — 1차는 rule 없이 radar metric only |
| Q4 | `baseline_debt.json` 1차 seed를 지금 audit 전체로? | **Yes** — guard 신규-only 동작 위해 |

---

## 7. 멀티에이전트 배치 (CEO)

| 단계 | 에이전트 | 산출 |
|------|----------|------|
| Plan | (본 spec) | 승인대기 |
| P1–P2 | generalPurpose / cavecrew-builder | docs + perf_scan |
| P3 | shell | pytest |
| P4 | cavecrew-builder | skills 2 files |
| P5 | cavecrew-reviewer + bugbot | finding list |
| P6 | shell | full inspection log |
| P7 | 사용자 승인 후 | deploy push |

---

## 8. Plan Status

**🟡 승인대기**

승인 시 CEO 순서: **Phase 1 → 2 → 3 → 4 → 5 리뷰 → 6 inspection → 7 deploy push**

승인 질문 (1개):

> **Q1–Q4 default 수용하고 Phase 1–7 순차 구현 + full inspection 후 `deploy` push 진행할까요?**

- **Yes** → Plan status `승인됨`, 즉시 Phase 1 시작 (production push 없음)
- **Adjust** → 변경 요청 반영 후 재승인
- **Docs/skills only** → Phase 1+4만 (엔진 `--radar`/B-layer 제외)
