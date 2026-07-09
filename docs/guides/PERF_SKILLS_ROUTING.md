# FOMS perf skills — 중복 제거 유지

SSOT: `.cursor/skills/perf-guard/` · `perf-audit/` (git 추적)

| 도구 | 사용법 |
|------|--------|
| Cursor | `/perf-guard` · `/perf-audit` (workspace skill) |
| Claude Code | `/perf-guard` · `/perf-audit` → SSOT SKILL JiT |
| Codex | FOMS repo에서 `.cursor/skills/perf-*/SKILL.md` 읽기 또는 `perf_scan.py` |

**금지:** `~/.codex/skills/perf-guard` · `perf-audit` 복제 — Cursor+Codex 메뉴 2중 노출.

복제 accidentally 생기면:

```powershell
powershell -NoProfile -File docs/context/archive/oneoff-scripts/prune_duplicate_perf_skills.ps1
```
