# perf-gate (Claude Code)

배포된 스테이징(lahom-dev)에 로그인 → 9개 primary fragment 경로를 반복 측정 →
커밋된 예산(`tools/perf/perf_budgets.json`)과 **warm 중앙값·바이트**로 비교해 초과 시
exit 1 로 승격을 차단한다(p95/tail 은 정보용 — 네트워크 tail 오탐 방지).

```
FOMS_STAGING_USERNAME=... FOMS_STAGING_PASSWORD=... \
  python tools/perf/staging_perf_gate.py [--base URL] [--seed] [--json]
```

- `--seed`: 현 측정값 + 30% 마진으로 budgets 갱신(의도된 성능 변화 때만, diff 리뷰 대상).
- exit: 0=PASS · 1=FAIL(예산 초과, 승격 차단) · 2=크리덴셜 부재/로그인 실패(SKIP≠실패).

**규칙**: deploy 배포 완료 후 / production 승격 직전 필수 실행. 상세 판정 철학:
`docs/guides/PERFORMANCE_GUARDRAILS.md` "스테이징 성능 게이트".

PowerShell(저장소 표준):
```powershell
$env:FOMS_STAGING_USERNAME="..."; $env:FOMS_STAGING_PASSWORD="..."
python tools/perf/staging_perf_gate.py
```
