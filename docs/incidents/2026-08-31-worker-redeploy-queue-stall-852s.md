# 2026-08-31 워커 재배포로 큐 전면 정지 — 전체 다시 읽기 47집이 +852초 밀렸다

> 유형: 운영 사고  ·  상태: 부분 종결
> 작성 2026-09-07. 사후 등재 문서 — 사고 당시 기록이 아니라 저장소 근거로 재구성했다.

상태를 **부분 종결**로 적는 이유: 원인(운영 worker 1대 · 재배포 = 큐 정지)은 그대로 남아 있고,
들어간 조치는 **읽기 전용 질의 도구 1벌**이다. 재배포를 막는 강제 장치는 저장소에 없다
(`tools/ops/check_worker_redeploy_safe.py:1`).

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 운영 사고 — 큐 전면 정지(작업 유실 없음, 지연) |
| 원인 축 | 운영 worker 가 **1대**(네이버 커머스API 호출 IP 계약상 단일 서비스)라 재배포하면 `rq worker` 가 내려갔다 올라오는 동안 큐가 전면 정지한다(`tools/ops/check_worker_redeploy_safe.py:3-4`) |
| 복구 | 별도 복구 조작 없음 — **작업은 유실되지 않는다**(`:4`). 워커 복귀 후 소진되며 밀린 값이 +852초다 |
| 구조 변경 여부 | 부분. `tools/ops/check_worker_redeploy_safe.py` 신설(**읽기 전용** 판정 도구). 재배포 차단·큐 드레인·무중단 교체는 없음 |
| 재발 여부 | `미상(근거 없음)` — 이후 같은 지연을 잰 기록이 저장소에 없다 |

## 2. 증상

**01:34 에 실사용자가 넣은 `전체 다시 읽기` 47집이 첫 스탬프 +852초(약 14분)까지 밀렸다**
(`tools/ops/check_worker_redeploy_safe.py:7-8`).

증상의 성질은 둘로 갈린다(`tools/ops/check_worker_redeploy_safe.py:4-5`).

- **작업은 유실되지 않는다.** 큐에 남아 있다가 워커가 돌아오면 처리된다.
- **화면은 유실된 것처럼 보인다.** 그 사이 사용자 화면의 진행 폴링은 **마감(300초)** 에 걸려
  접힌다. 852초는 300초 마감의 약 2.8배다 — 즉 사용자는 진행 표시가 사라진 상태로 기다렸다.

그리고 그때는 **"돌고 있는지" 를 물어볼 자리가 사람 기억밖에 없었다**
(`tools/ops/check_worker_redeploy_safe.py:8-9`). 이것이 이 사고의 관측 공백이다.

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| 2026-08-31 (HH:MM `미상(근거 없음)`) | 자동 조회 주기 변경을 반영하려고 운영 worker 재배포 | `tools/ops/check_worker_redeploy_safe.py:7` |
| 2026-08-31 01:34 | 실사용자가 `전체 다시 읽기` **47집** 투입 | `tools/ops/check_worker_redeploy_safe.py:7-8` |
| 01:34 +852초 | 첫 스탬프 — 약 14분 지연 | `tools/ops/check_worker_redeploy_safe.py:8` |
| 그 사이 300초 지점 | 화면 진행 폴링이 마감에 걸려 접힘 | `tools/ops/check_worker_redeploy_safe.py:5` |
| `미상(근거 없음)` | 47집 처리 완료 | — |

01:34 와 +852초는 docstring 이 단정한 값이다. 재배포 시각(HH:MM)과 완료 시각은
`미상(근거 없음)`.

배경으로 같은 날짜의 관련 항목이 하나 있다: `docs/AI_CHANGELOG.md:21`(NVREPAY-05)이 자동 조회
주기를 300→1800초로 바꾸며 **스테이징 worker 적용·재배포**를 적고 "운영은 명시 승인 대기" 라고
남겼다. docstring 이 말하는 운영 재배포가 그 승인 이후의 같은 변경인지 다른 재배포인지는 두 줄만으로
갈리지 않는다 — `미상(근거 없음)`.

## 4. 근본 원인

**구조가 원인이다. 조작 실수가 아니다.**

- 운영 worker 는 **1대**다. 네이버 커머스API 호출 IP 계약상 단일 서비스라 복제로 풀 수 없다
  (`tools/ops/check_worker_redeploy_safe.py:3`, `docs/plans/2026-09-06-foms-system-review-report.md:50`).
- 그 1대를 재배포하면 `rq worker` 가 내려갔다 올라오는 동안 **큐가 전면 정지**한다
  (`tools/ops/check_worker_redeploy_safe.py:3-4`). 이 컨테이너에는 무감독 루프 5개
  (에스컬레이션·수집·자동 발송·정산·지오코딩 스윕)가 함께 얹혀 있다
  (`docs/plans/2026-09-06-foms-system-review-report.md:50`).
- 그리고 **재배포 시점에 "지금 돌고 있는 사용자 작업이 있는가" 를 물어볼 자리가 없었다**
  (`tools/ops/check_worker_redeploy_safe.py:8-9`). 사고의 크기를 결정한 것은 정지 자체가 아니라
  하필 사용자가 넣은 47집 작업 위로 정지가 겹쳤다는 사실이고, 그 겹침을 사전에 알 방법이 없었다.

부차 요인: 화면 폴링 마감 300초가 실제 지연(852초)보다 짧아 **진행 표시가 먼저 접힌다**
(`tools/ops/check_worker_redeploy_safe.py:5`). 그래서 "밀렸다" 가 사용자에게 "멈췄다/사라졌다" 로 보인다.

## 5. 복구

- **별도 복구 조작이 없다.** 작업은 유실되지 않으므로(`tools/ops/check_worker_redeploy_safe.py:4`)
  워커가 돌아온 뒤 소진됐고, 그 대가가 +852초 지연이다.
- 사용자에게 어떻게 고지했는지, 재실행이 필요했는지 — `미상(근거 없음)`.

## 6. 구조 변경

**`tools/ops/check_worker_redeploy_safe.py` 신설** — "운영 worker 를 지금 재배포해도 되는지 묻는다
— **읽기 전용**"(`:1`).

설계 규율 하나가 명시돼 있다(`tools/ops/check_worker_redeploy_safe.py:11-12`):
**판정을 두 벌로 만들지 않는다.** 전체 다시 읽기 진행 여부는 화면이 쓰는 것과 **같은 함수**
(`claim_watch.running_refresh_all`)로 묻고, 큐 적체는 rq 에게 직접 묻는다. 화면과 운영 도구가
서로 다른 답을 내는 자리를 애초에 만들지 않는다는 뜻이다.

**들어가지 않은 것**(범위 밖이 아니라 실제로 없는 것):

- 재배포를 **막는** 게이트 — 없음. 도구는 묻기만 한다(`:1` "읽기 전용").
- 큐 드레인·무중단 교체·복제 — 없음(복제는 IP 계약상 불가, `:3`).
- 폴링 마감 300초와 실제 지연의 어긋남에 대한 조치 — `미상(근거 없음)`.

## 7. 재발 여부·남은 것

- 재발 여부 — `미상(근거 없음)`. 이후 같은 재배포 지연을 잰 기록이 저장소에 없다.
- 남은 것 ①: **재배포는 지금도 큐 전면 정지다.** 도구는 그 사실을 바꾸지 않고 알려 줄 뿐이다.
- 남은 것 ②: 워커 정지를 **사람에게 알리는 경로가 없다** — `/healthz` 는 liveness 만,
  `init_sentry` 호출처는 web 한 곳, 워크플로 7개에 알림 0
  (`docs/plans/2026-09-06-foms-system-review-report.md:50`). 같은 공백이 2026-08-07 13시간 정지에서도
  작동했다(`docs/incidents/2026-08-07-worker-redis-boot-race-13h-outage.md`).
- 남은 것 ③: 이 도구가 사람의 절차에 등재됐는지(재배포 전 실행 강제) — `미상(근거 없음)`.
- 남은 것 ④: 검토 보고서가 이 사고를 "원장 밖 운영 사고 4건" 의 하나(852초)로 세었다
  (`docs/plans/2026-09-06-foms-system-review-report.md:134`). 본 등재가 그 자리다.

## 8. 근거 앵커

- `tools/ops/check_worker_redeploy_safe.py:1` — 도구 성격(읽기 전용, NVREPAY-05 후속)
- `tools/ops/check_worker_redeploy_safe.py:3-5` — worker 1대(네이버 IP 계약) · 재배포 = 큐 전면 정지 · 작업 유실 없음 · 폴링 마감 300초
- `tools/ops/check_worker_redeploy_safe.py:7-9` — 2026-08-31 실사례(01:34 · 47집 · 첫 스탬프 +852초 · "물어볼 자리가 사람 기억밖에 없었다")
- `tools/ops/check_worker_redeploy_safe.py:11-12` — 판정 SSOT 규율(`claim_watch.running_refresh_all` + rq 직접 질의)
- `docs/AI_CHANGELOG.md:21` — NVREPAY-05, 자동 조회 주기 300→1800초(스테이징 적용·운영 승인 대기), 진행 표시·소요 시간 예고
- `docs/plans/2026-09-06-foms-system-review-report.md:50` — R3, 단일 워커·무감독 루프 5개·알림 0, 근거에 `tools/ops/check_worker_redeploy_safe.py:1-12` 포함
- `docs/plans/2026-09-06-foms-system-review-report.md:134` — R8, "운영 사고 4건이 사고 원장 밖"(852초 포함)
