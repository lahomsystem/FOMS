# FOMS deploy veto — perf-guard

**North Star:** deploy 직후 전체 ERP 느려짐 재발 방지. TTFB OK ≠ deploy OK. **uncertain = 배포 금지.**

## 4-Layer Gate

1. `python tools/perf/perf_scan.py --guard [--base origin/deploy] [--json]`
2. Diff trigger + manual — `docs/guides/PERFORMANCE_GUARDRAILS.md` §A, `.cursor/skills/perf-guard/references/`
3. `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1`
4. production 전 perf-audit + staging 실측

## Auto G1–G4

sync script · CDN sync · SW cache/timeout · fragment unguarded listener

Hot B-layer (new diff on hot path): general-ilike, loop-db-query, shell-polling, shared-inline-script

## Output

```markdown
## Perf Guard
- 판정: 배포 가능 | 배포 금지
- exit / incident class / file:line / fix
```

SSOT: `PERFORMANCE_GUARDRAILS.md`, `ERP_SLOWDOWN_RADAR.md`
