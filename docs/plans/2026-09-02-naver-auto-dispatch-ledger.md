# 진행 원장 — 네이버 발송처리 자동 실행 · NAVER-AUTODISPATCH-01

- 계획서: `docs/plans/2026-09-02-naver-auto-dispatch-plan.md`
- 워크트리: `c:\tmp\foms-s-s0902-134229` (session/s0902-134229, origin/deploy 기준)

## Task 상태

| task | 상태 | 완료 기준 |
|---|---|---|
| T1 `run_auto_dispatch()` 서비스 | DONE | 안 나가는 조건 6종 + 나가는 경로 계약 green |
| T2 러너(`--once`/`--loop --at`) | DONE | 시각 창 판정·형식 오류 거절 계약 green |
| T3 `start.sh` 배선 + env 3종 | DONE | WORKER 분기 안·기본 꺼짐·백그라운드(&) 계약 green |
| T4 화면 안내 한 줄 | DONE | 두 띠가 **같은 값**(build_preview `auto`)을 읽는다 |
| T5 게이트·푸시·승격 | DONE | pre_push_smoke exit 0 · CI 전 워크플로 green |

## 사용자 결정 (2026-09-02)

1. **평일 + 공휴일 제외** — 달력은 기존 `business_calendar.is_business_day` 재사용.
2. 대상 판정은 **수동 버튼과 동일**(`select_sendable`) — '실측 완료 표시 없음' 집도 보낸다.
3. **예행 없이 바로 실제 발송**, 수동 버튼 유지. 수동으로 이미 보낸 날은 자동이 보낼 게
   없어 조용히 지나간다.

## 설계 요약

- **실행 자리**: 워커 컨테이너 백그라운드 루프(수집 스윕·escalation 과 같은 관례).
  새 인프라 의존성 없음. 60초마다 깨어나 **시각 창**(기본 16:50 + 10분) 안에서만 실행 —
  워커 재시작으로 정각을 놓쳐도 그날을 잃지 않는다.
- **하루 1회 계약은 러너가 아니라 서비스가 DB 로 지킨다**(`naver_auto_dispatch_state.
  last_run_date`). 창 안에서 여러 번 깨어나도, replica 가 늘어도 두 번 안 나간다.
- **큐가 죽으면 오늘을 닫지 않는다** — `last_run_date` 를 찍지 않아 다음 창에서 재시도한다.
  성공한 척하고 날짜를 닫으면 그날 발송이 통째로 사라진다.
- **감사와 알림**: 보낸 집이 있을 때만 `NAVER_INGEST_BULK_DISPATCH_AUTO` 1건 + 관리자
  ROLE 알림 1건(막힌 집 수 병기). 0집이면 조용히 — 매일 뜨는 알림은 읽히지 않는다.
- **행위자는 `None`** — 사람이 아니라 스케줄이 한 일이다. 봇 계정을 끼워 넣으면 감사가
  "누가 눌렀다"고 거짓말한다.

## 기록

- T1 DONE: `auto_dispatch.py` 신설. 신규 12개. red-check: 영업일·하루1회 가드를 끄면
  3개가 빨개진다(확인함).
- T2 DONE: `scripts/maintenance/run_naver_auto_dispatch.py`(`--once/--force/--json/--loop/
  --at/--window/--tick`). 시각 문자열이 틀리면 **조용히 기본값으로 안 떨어지고** 예외를 낸다
  (적어 둔 시각과 실제가 말없이 갈리는 것이 최악).
- T3 DONE: `start.sh` 워커 분기에 게이트 블록 추가(`FOMS_NAVER_AUTO_DISPATCH_ENABLED`·
  `..._AT`·`..._WINDOW_MINUTES`). 기본 꺼짐.
- T4 DONE: `build_preview` 가 `auto{enabled, at}` 를 실어 두 띠가 같은 문구를 낸다.
- 등재: 감사 라벨 `NAVER_INGEST_BULK_DISPATCH_AUTO` + audit coverage 인벤토리 재생성
  (206/0). **신규 라우트가 없어 write guard·policy manifest 등재는 대상 밖**이다.
- 검증: 신규 20개 · integrations 1,488 passed · 로컬 전수 8,098 passed ·
  pre_push_smoke exit 0.

## 남은 일

1. deploy push → CI 전 워크플로 green.
2. 운영 승격(사용자 승인) — **워커 재배포가 필요하다**(`start.sh` 변경). 워커 1대라
   재배포 = 큐 전면 정지. `tools/ops/check_worker_redeploy_safe.py` 판정 후 16:50 을 피해
   실행한다.
3. 운영 env 3종 투입: `FOMS_NAVER_AUTO_DISPATCH_ENABLED=1`(+ 필요 시 시각·창).
   **변수만 넣으면 안 켜진다** — 새 부팅이 있어야 프로세스가 새 env 를 든다.

## 스테이징 실증 (2026-09-02)

워커 env 3종 투입 + 재배포 후 로그로 확인:

- 기동: `[naver-auto-dispatch] started (at=14:50 window=10m tick=60s)` (검증용으로 시각을
  임박한 14:50 으로 잠깐 두고 관측, 확인 뒤 16:50 으로 되돌림).
- 14:50:18 창에서 실제 판정 실행 → `no_target`(그날 스테이징에 보낼 집 0) → **아무것도
  보내지 않고** 알림·감사도 만들지 않았다(설계대로 조용히).
- 이후 매 tick 은 `2026-09-02 은 이미 실행했다 — 건너뛴다` — **하루 1회 계약이 실환경에서
  작동**함을 확인.
- 상태 행 실측: `{"last_outcome": "no_target", "last_run_date": "2026-09-02",
  "last_run_at": "2026-09-02T14:50:18+09:00", "last_summary": {"queued": 0, "blocked": 0}}`.

**스테이징에서 실제 발송 경로는 일부러 돌리지 않았다** — 스테이징 워커도 같은 커머스
계정을 써서, 시드 주문에 실제 상품주문번호를 붙이면 **진짜 발송처리가 나간다**.

## 운영 반영 완료 (2026-09-02)

- 승격 PR **#270** 머지 — production `51c366e9`. 검사 4종 SUCCESS · CLEAN ·
  승격 트리에서 본 스위트 8,046 passed + pre_push_smoke exit 0.
- 재배포 전 큐 안전 판정: `check_worker_redeploy_safe.py` → **exit 0(지금 재배포해도 된다)**
  — 진행 중 작업 없음 · 큐 비어 있음.
- 운영 WORKER env 투입: `FOMS_NAVER_AUTO_DISPATCH_ENABLED=1` ·
  `FOMS_NAVER_BULK_DISPATCH_ENABLED=1` · `FOMS_NAVER_AUTO_DISPATCH_AT=16:50`.
- **워커 재배포 완료** → 로그 확인:
  `[naver-auto-dispatch] started (at=16:50 window=10m tick=60s)` (escalation·수집 루프도 정상 기동).
  변수만 넣으면 안 켜진다는 함정을 피해, **새 부팅 뒤 로그로** 판정했다.

## 남은 관측

오늘 16:50 첫 실제 실행. 볼 것 셋: ① 워커 로그 `naver auto-dispatch: outcome=...`
② 관리자 알림 1건(보낸 집이 있을 때만) ③ 실측 대시보드 띠가 "발송됨"으로 바뀌는지.
끄는 법은 `FOMS_NAVER_AUTO_DISPATCH_ENABLED=0` + 워커 재배포다.
