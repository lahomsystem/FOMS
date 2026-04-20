# FOMS Compact Checkpoint

업데이트: 2026-04-13
브랜치: `deploy`

## 최종 목표
- FOMS를 안전한 modular monolith로 진화한다.

## 이번 세션 합의
- 최종 목표는 그대로 유지한다.
- WDCalculator는 더 이상 thin host shell 1개씩 늘리는 미세 분해로 진행하지 않는다.
- 다음부터는 유지보수 편의성이 실제로 올라가는 의미 있는 chunk 단위로 자른다.
- 파일 수만 늘어나는 wrapper-only 배치는 중단한다.

## 현재 상태 요약
- `/wdcalculator`는 contract freeze와 주요 static JS 분리가 상당 부분 끝났다.
- 최근 완료 지점은 `coupon-search-render-host-bootstrap.js`와 `totals-startup-terminal-host-bootstrap.js`까지다.
- 기능 차단 이슈는 없고, 남은 핵심 리스크는 과분해에 따른 파일 수, 테스트 수, 인지부하 증가다.
- `wdcalculator_scripts_config.html`의 Jinja inline script는 여전히 JS lint false-positive를 낸다. 신규 실제 lint 이슈는 없다.

## 다음 세션에서 먼저 볼 파일
1. `docs/context/COMPACT_CHECKPOINT.md`
2. `docs/AI_STATUS.md`
3. `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`
4. `templates/wdcalculator/partials/wdcalculator_scripts.html`

## 다음 세션 첫 작업
1. WDCalculator 남은 구조 작업을 `유지`, `통합`, `종결` 3개 축으로 다시 분류한다.
2. `estimate-mutation-bridge-host-bootstrap` 같은 micro-batch는 바로 진행하지 말고 보류 상태로 둔다.
3. 남은 구조 작업을 3~5개의 의미 있는 덩어리로 재편한다.
4. 각 덩어리는 "파일 수 감소 또는 ownership 명확화"가 있어야만 진행한다.

## 금지 사항
- `*-host-bootstrap.js`를 1개 더 만드는 것만으로 배치를 닫지 않는다.
- 테스트/문서 증가에 비해 유지보수 이득이 작은 wrapper-only 분해는 하지 않는다.
- 최종 목표를 바꾸지 않는다.

## 새 세션 프롬프트
```text
최종 목표는 그대로 modular monolith다. 다만 WDCalculator는 더 이상 micro thin-host-shell 배치로 쪼개지 말고, 유지보수 편의성이 실제로 올라가는 의미 있는 chunk 기준으로 재기준선해줘. 먼저 `docs/context/COMPACT_CHECKPOINT.md`, `docs/AI_STATUS.md`, `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`를 읽고, 다음 작업을 3~5개 chunk로 재설계한 뒤 그중 첫 chunk만 실행 계획으로 제안해줘.
```

## 참고
- 직전 micro 후보는 `estimate-mutation-bridge host bootstrap`이었지만 이번 결정으로 우선 보류한다.
- 핵심은 "더 잘게"가 아니라 "더 유지보수 가능하게"다.
