# tools/perf — FOMS 성능 점검

코드 수정이 FOMS를 느리게 만드는지 잡고, 정기 점검으로 성능을 개선하는 도구.

- `perf_scan.py` — 도구 무관 스캐너.
  - `python tools/perf/perf_scan.py --guard` : 변경분 회귀 점검(high면 exit 1, 머지 차단).
  - `python tools/perf/perf_scan.py --audit` : 전체 코드베이스 개선 후보(advisory).
  - `--json` 기계 판독, `--base <ref>` guard 비교 기준.

스킬(에이전트 진입점): Claude `/perf-guard`·`/perf-audit`(`.claude/commands`), Cursor 네이티브 `.cursor/rules/02-performance-guardrails.mdc`, Codex `AGENTS.md`+스크립트 직접 실행.
정책·체크리스트·사유: `docs/guides/PERFORMANCE_GUARDRAILS.md`.
자동 강제(CI/smoke): `tests/performance/test_perf_regression_guard.py`, `test_static_cache_headers.py`.
G4: ERP shell fragment에서 재실행되는 JS의 전역 listener는 singleton guard(`window.__*_BOUND`) 없으면 차단.
