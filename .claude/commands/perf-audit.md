# FOMS ERP Slowdown Radar — perf-audit

**North Star:** latent perf mines + staging proof before production. guard=신규 diff, audit=전체 baseline.

## Workflow

1. `python tools/perf/perf_scan.py --audit [--json]`
2. `python tools/perf/perf_scan.py --radar [--json]`
3. 8차원 checklist — `docs/guides/ERP_SLOWDOWN_RADAR.md`, `.cursor/skills/perf-audit/references/`
4. Hot path: TTFB → EXPLAIN → Chrome SW → tab swap (field > lab)

high findings = deploy 리스크 (exit 0 advisory).

## Output

```markdown
## Perf Audit
### 차원별 top (효과×빈도)
- [dimension] finding — fix — 측정 필요?
### deploy 리스크 / staging gap
```

수정 후 perf-guard + smoke. production은 사용자 명시 승인 전 push 금지.
