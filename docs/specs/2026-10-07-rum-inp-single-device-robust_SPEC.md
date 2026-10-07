# RUM 일일 경고가 기기 한 대에 흔들리지 않게 — SPEC (승인 대기)

작성 2026-10-07. 등급: 하네스(감시) 변경 — Spec → 승인 → 구현.

## 1. 무슨 일이 있었나 (운영 실측)

- 2026-10-07 07:30 KST `rum-daily (production)` 가 red: INP recent p95 967ms vs baseline 274ms (x3.53).
- 운영 web 로그(`foms.rum` 한 줄 JSON, 배포 20개분, 10-02~10-07 INP 2,299건)를 화면·기기별로 다시 셌다.
  - 화면 크기 1210x802(mobile_v2=true, 태블릿 추정) **기기 1대**가 10-05 20:21 KST 처음 나타나
    10-06 17:15 KST 까지 90건(주문 수정 55·대시보드 35), 중앙값 464~784ms 로 상시 느렸다.
  - 이 기기를 빼면 일별 정확 p95 는 10-02 448 · 10-05 544 · 10-06 368 · 10-07 248ms — 회귀 없음.
- 경고를 키운 두 번째 원인: **버킷이 거칠다**. 현재 경계 `(100, 300, 800, 2000, 5000)` 에서 p95 가
  800 경계 근처에 있으면, 800 이상 표본 몇 건만으로 보간값이 [800,2000) 칸으로 넘어가 두 배로 튄다.

같은 로그로 계산한 일별 p95(ms):

| 날짜 | 표본 | 정확값 | 지금 버킷 | 촘촘한 버킷(안) |
|---|---:|---:|---:|---:|
| 10-02 | 589 | 448 | 641 | 463 |
| 10-05 | 398 | 920 | 1155 | 942 |
| 10-06 | 1013 | 448 | 549 | 462 |
| 10-07 | 179 | 248 | 286 | 251 |

촘촘한 버킷이면 10-06 은 기준 대비 약 1.0배라 "최근 2일 **모두** 1.5배 초과" 규칙에 걸리지 않는다.

## 2. 바꿀 것

### A. 히스토그램 버킷을 촘촘하게 (본 수정)
- `foms/services/rum_aggregate.py`
  - `BUCKET_UPPER_BOUNDS_MS = (50, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1500, 2000, 5000)`.
  - 버킷 인덱스 의미가 바뀌므로 `KEY_VERSION = "v2"` (키 `foms:rum:v2:<date>:<metric>`). v1 키는 TTL 35일로 자연 소멸.
  - Redis 비용: 요청당 HINCRBY 1회 그대로, 해시 필드 6→14 (무시 가능).
- 전환기: v2 는 빈 상태로 시작한다. `detect_regression` 은 유효 recent 2일 + 유효 baseline 1일만 있으면 판정하므로
  배포 후 4일째 아침부터 판정이 돌지만, 기준이 하루~이틀치뿐이라 흔들린다. 그래서 `build_rum_report` 에
  "유효 baseline 일수 < 3 이면 판정 보류(`regressed=None`)" 를 추가한다 → 배포 후 6일째 아침부터 정상 판정.
  - 대안(채택 안 함): v1 을 읽어 v2 로 변환 — 거친 칸을 잘게 쪼갤 근거가 없어 거짓 정밀도가 된다.

### B. 기기 한 대의 하루 INP 전송 상한 (보조)
- `static/js/foms/rum-baseline.js` `flushInp`: `localStorage` 에 `{date(KST 아님, 기기 로컬 날짜), count}` 를 두고
  하루 **20건** 넘으면 INP 를 보내지 않는다. storage 접근은 try/catch, 실패하면 지금처럼 보낸다(fail-open).
- 근거: 이번 기기는 하루 56건(10-05)·34건(10-06)을 보냈다. 20건 상한이면 하루 약 1,000건 중 2% 이하.
- 화면 크기로 자르는 서버 측 상한은 쓰지 않는다 — 같은 크기의 휴대폰이 많아 시험 계산에서 빠른 표본만 깎여 p95 가 오히려 올랐다(10-06 462→770).
- 캐시 핀(`layout_scripts.html` 의 rum-baseline `?v=`) 갱신.

### 바꾸지 않는 것
- 임계 1.5배·RECENT 2일·BASELINE 5일·MIN_DAY_SAMPLES 30·표본 구성 변화 가드.
- 수신 API 계약(키 5개)·로그 한 줄 형식 — 화면별 진단은 지금처럼 Railway 로그로 한다.

## 3. 검증 (완료 기준)

- `python -m pytest tests/domains/test_rum_aggregate.py tests/domains/test_rum_ingest.py tests/domains/test_foms_rum_baseline.py -q` green.
- 새 테스트
  - 버킷 경계·`KEY_VERSION == "v2"` 고정.
  - 1장 표의 10-06 분포를 재현한 히스토그램에서 p95 가 정확값 ±10% 안.
  - rum-baseline.js 에 하루 상한 상수 20·try/catch 존재(정적 계약).
- `node --check static/js/foms/rum-baseline.js`, `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1` exit 0.
- 배포 후: 스테이징 `/api/foms/rum/report` 에 v2 키로 집계가 쌓이는지 확인.

## 4. 남는 위험

- 전환 후 약 5일은 회귀 경고가 사실상 꺼진다(판정 보류). 그 사이 진짜 회귀는 화면별 로그로만 보인다.
- 느린 태블릿 자체(누구 것인지, 왜 느린지)는 이 수정 범위 밖이다.
