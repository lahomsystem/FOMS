# perf-gate 페르소나 쿠키 Spec
> 작성일: 2026-09-11 | 상태: ✅ 완료

## 0. 왜 — 실측으로 드러난 사실

perf-gate 봇은 로그인 세션 쿠키만 싣고 프래그먼트를 받는다
(`tools/perf/staging_perf_gate.py:438` `session.headers["Cookie"] = cookie`).

서버는 브라우저가 pre-paint 에 심는 두 쿠키로 "그 기기가 구조적으로 볼 수 없는 표면"을
렌더에서 뺀다.

| 쿠키 | 판정 함수 | 없을 때 |
|------|-----------|---------|
| `foms_scr` | `wants_wide_only_surfaces` (`foms/services/feature_flags.py:209`) | 안전 폴백 = 전부 렌더 |
| `foms_ptr` | `wants_coarse_pointer_surfaces` (`foms/services/feature_flags.py:168`) | 안전 폴백 = 전부 렌더 |

봇에는 두 쿠키가 없으므로 **데스크톱 작업 큐 + 태블릿 칸반 + 모바일 카드를 전부 받는다**.
실제 브라우저는 셋 중 자기 것만 받는다.

같은 창에서 나란히 측정(`/erp/production/dashboard?view=fragment`, warm 6표본, healthz base 137.1ms):

| 클라이언트 | wire | 서버 렌더 min/중앙 | dTTFB |
|---|---|---|---|
| 게이트 봇(쿠키 없음) | 44,121B | 18.8 / 27.0ms | **106.5ms** |
| 실제 PC 브라우저(`foms_scr=1920`, `foms_ptr=fine`) | 36,893B | 14.3 / 19.2ms | **86.7ms** |
| 차이 | −7,228B (16.4%) | −7.8ms | **−19.8ms** |

즉 게이트는 **실제 사용자보다 약 20ms 무거운 합성 최악값**을 재고, 예산은 그 값에 맞춰 시드돼
있다. 네트워크가 조금만 밀리면 그 20ms 때문에 먼저 터진다(2026-09-10 PR #346 에서 실제 발생).

### 이 경로들에 쿠키 없는 상태는 실제로 존재하지 않는다

두 쿠키는 pre-paint 부트가 심는다. perf-gate 가 재는 `?view=fragment` 는 **셸이 이미 떠 있는
뒤의 탭 전환**이므로, 실제 클라이언트는 이 요청 시점에 항상 두 쿠키를 갖고 있다. 쿠키 없는
첫 요청은 full document 경로이고 이 게이트의 측정 대상이 아니다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
perf-gate 가 실제 PC 브라우저와 동일한 응답을 받아 판정한다. 표에 어떤 페르소나로 쟀는지
한 줄로 드러난다.

### 1.2 기능 요구사항
1. 게이트 세션이 `foms_scr`(광폭)·`foms_ptr=fine` 쿠키를 함께 싣는다.
2. 페르소나 값은 모듈 상수 1곳(SSOT)에 두고 `run_gate` 와 `run_seed` 가 같은 값을 쓴다.
   두 경로가 갈리면 예산과 판정의 기준이 어긋난다.
3. 리포트 헤더에 측정 페르소나를 표기한다.
4. evidence JSON 에 페르소나를 남겨 과거 측정과 비교 가능하게 한다.

### 1.3 예외/제약 조건
- **커버리지 축소를 인정하고 기록한다.** `foms_ptr=fine` 을 보내면 태블릿 칸반(coarse 전용)
  표면이 더 이상 게이트에 안 잡힌다. 지금까지는 쿠키가 없어 "우연히" 함께 재고 있었다.
  이 Spec 범위 밖의 후속 과제로 남긴다(별도 페르소나 패스).
- **예산 재시드는 CI 에서만.** `reconcile_seed_budget` 이 로컬 `--seed` 의 TTFB 예산 갱신을
  막는다(CI 심판석 값 보존). 그래서 이 변경 직후 TTFB 예산은 옛 값(더 큰 값)으로 남고
  게이트는 **일시적으로 느슨해진다**. bytes 예산은 로컬 시드로도 갱신된다.
- 예산을 이 변경과 같은 커밋에서 완화 방향으로 손대지 않는다. 느슨해지는 것은 측정값이
  작아진 결과이지 예산을 낮춘 결과가 아니어야 한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `tools/perf/staging_perf_gate.py` | 페르소나 쿠키 상수 추가, `run_gate`/`run_seed` 세션에 부착, 표·evidence 에 페르소나 표기 |
| `tests/domains/` 또는 `tests/harness/` | 두 경로가 같은 페르소나를 쓰는지, 쿠키가 실제로 실리는지 계약 테스트 |
| `docs/guides/PERFORMANCE_GUARDRAILS.md` | 페르소나 기준과 커버리지 공백 기록 |

### 2.2 아키텍처 방향
- 기존 `FRAGMENT_HEADERS` 상수와 같은 결로 `GATE_PERSONA_COOKIES` 상수를 둔다.
- 세션의 `Cookie` **헤더 문자열에 합친다**(§2.2 보정 참조 — jar 는 전송되지 않는다).

### 2.2-b 보정 — 쿠키 jar 는 안 된다(구현 중 발견)

Spec 초안은 "문자열 병합이 깨지기 쉬우니 jar 에 심는다"고 적었다. **틀렸다.** 이 세션은
로그인 쿠키를 `session.headers['Cookie']` 로 명시하는데, requests 는 명시된 Cookie 헤더가
있으면 jar 를 병합하지 않고 헤더를 그대로 보낸다. jar 방식으로 먼저 구현했을 때
`/erp/production/dashboard` wire 가 44,121B 로 **1바이트도 줄지 않아** 드러났다. 헤더 문자열에
합치는 방식으로 바꾸고, 그 사실을 회귀 가드 테스트로 고정했다.

### 2.3 의존성 및 영향 범위
- 앱 코드 무변경. 측정 도구만 바뀐다.
- perf-gate 워크플로 4곳(PR·deploy·수동) 모두 같은 스크립트를 쓰므로 자동 반영.

## 3. Steps
- [x] Step 1: 봇 vs 실브라우저 실측으로 근거 확보
- [x] Step 2: `GATE_PERSONA_COOKIES` 도입 + `run_gate`/`run_seed` 부착
- [x] Step 3: 표·evidence 페르소나 표기
- [x] Step 4: 계약 테스트 추가 (4종, `tests/performance/test_staging_perf_gate.py`)
- [x] Step 5: 로컬 게이트 실행으로 전 경로 수치 비교(전/후) — 아래 §5
- [x] Step 6: 가이드 문서에 페르소나·커버리지 공백 기록

## 4. 검증 기준
- [x] `python -c "import app; print('APP_OK')"` → APP_OK
- [x] `python tools/perf/staging_perf_gate.py` 가 표 헤더에 페르소나를 찍는다
- [x] 전/후 wire 바이트가 경로별 −10~−39% 내려간다(§5)
- [x] 새 계약 테스트 통과 (41 passed)
- [x] `scripts/ops/pre_push_smoke.ps1` exit 0

## 5. 실측 결과 (2026-09-11, 스테이징, claude_master)

| PATH | wire 전(쿠키 없음) | wire 후(페르소나) | 변화 |
|---|---|---|---|
| /erp/construction/dashboard | 29,984 | 18,323 | **−38.9%** |
| /erp/as | 49,676 | 35,409 | −28.7% |
| /erp/completion | 13,669 | 9,621 | −29.6% |
| /erp/drawing-workbench | 17,062 | 13,515 | −20.8% |
| /erp/production/dashboard | 44,121 | 36,893 | −16.4% |
| /erp/dashboard | 22,964 | 20,557 | −10.5% |

바이트 예산 재시드 결과(모두 **강화** 방향, 완화 0건):

| PATH | body_bytes_max 전 | 후 | 변화 |
|---|---|---|---|
| /erp/construction/dashboard | 98,940 | 23,820 | −75.9% |
| /erp/shipment | 34,405 | 11,648 | −66.1% |
| /erp/measurement | 36,916 | 17,485 | −52.6% |
| /erp/drawing-workbench | 29,745 | 17,570 | −40.9% |
| /erp/production/dashboard | 79,512 | 47,961 | −39.7% |
| /erp/as | 70,668 | 46,032 | −34.9% |
| /erp/completion | 18,466 | 12,507 | −32.3% |
| /erp/dashboard | 34,702 | 26,724 | −23.0% |
| /erp/history/ | 10,174 | 9,330 | −8.3% |

TTFB 예산은 `reconcile_seed_budget` 규칙대로 **CI 심판석 값 보존**(로컬 시드는 bytes 만).
따라서 이 커밋 직후 latency 판정은 옛 예산(더 큰 값) 기준이라 **일시적으로 느슨**하다.
CI 에서 `--seed` 를 한 번 돌려야 조여진다 — 후속 과제.

게이트 최종 실행: `RESULT: PASS`, exit 0.
