# ERP Slowdown Radar (SSOT)

> deploy 직후 “전체 ERP 느려짐” 재발 방지. incident 가드 + 8차원 broad 탐색.
> 상세 incident·G1–G4: [`PERFORMANCE_GUARDRAILS.md`](PERFORMANCE_GUARDRAILS.md)

## North Star

기능·TTFB 정상이어도 deploy 후 체감이 느려질 수 있다. **uncertain = 배포 금지.**

| 실제 사고 (2026-06) | 클래스 |
|---------------------|--------|
| html2canvas + 공유 partial | **Amplifier** |
| SW networkFirst 무 timeout | **Masking** |
| JSONB ILIKE Seq Scan | **Scale cliff** |

## 8차원 Taxonomy

| dimension | ERP 증상 | 정적 탐지 예 |
|-----------|----------|-------------|
| `amplifier` | 한 수정 → 전 탭/전 사용자 | shared partial script/CSS |
| `render-block` | TTFB OK, 첫 화면 늦음 | sync `<script src>` |
| `interaction-debt` | 탭/입력 버벅 | fragment listener, polling |
| `sw-cache` | 스피너, 매번 재다운 | SW no-cache, networkFirst |
| `query-scale` | 사용자↑ cliff | ilike, `.all()`, N+1 loop |
| `payload` | API/HTML 과대 | unbounded list fetch |
| `hot-compute` | 대시보드 매요청 느림 | 집계 without cache |
| `io-bound` | 업로드/첨부 | sync batch (후순위) |

## Hot Path (guard B-layer high 대상)

- `templates/partials/shared/`, `erp_order_js`, `foms_app_shell`, `erp_mobile_shell`
- `static/sw.js`
- `services/dashboard/`, `services/search/`
- `foms/api/` (list/search/filter routes)

## Severity 정책

| severity | perf-guard | perf-audit |
|----------|------------|------------|
| high (proven G1–G4) | **차단** (신규 diff) | deploy 리스크 |
| high (hot B-layer, 신규) | **차단** | deploy 리스크 |
| medium | cold: 통과 / hot 신규: 차단 | 측정·수정 후보 |
| baseline debt | `tools/perf/baseline_debt.json`에 고정 → guard 신규만 |

Escape: `# perf-ok` (사유+리뷰), allowlist (`test_perf_regression_guard.py`).

## 4층 Gate (deploy 전)

```
L1  perf_scan.py --guard [--base origin/deploy]
L2  diff blast-radius + §A 수동 체크 (PERFORMANCE_GUARDRAILS)
L3  scripts/ops/pre_push_smoke.ps1
L4  production 전: perf-audit + --radar + staging TTFB/EXPLAIN/Chrome SW
```

## 측정 Ladder (field > lab)

1. **TTFB** — 서버/프론트/SW 분리 (“느리다=서버” 단정 금지)
2. **EXPLAIN (ANALYZE)** — hot query Seq Scan 없음
3. **Chrome SW** — 헤드리스 금지
4. **탭 전환** — fragment swap 10회 (모바일 shell)

## CLI

```powershell
python tools/perf/perf_scan.py --guard
python tools/perf/perf_scan.py --audit
python tools/perf/perf_scan.py --radar [--json]
```

스킬: perf-guard (veto) · perf-audit (radar). Codex `~/.codex/skills/`, Claude `.claude/commands/`, Cursor `.cursor/skills/`.
