# 2026-09-02 SIDEFX 에 KAKAO_REST_API_KEY 가 없어 지오코딩이 조용히 실패했고, outbox DEAD 1,188행이 그 추적을 덮었다

> 유형: 운영 사고  ·  상태: 종결
> 작성 2026-09-07. 사후 등재 문서 — 사고 당시 기록이 아니라 저장소 근거로 재구성했다.

**이 문서는 원인 축이 둘인 한 건의 종결을 담는다.** ① 지오코딩 실패의 최초 트리거 =
`SIDEFX` 서비스에만 `KAKAO_REST_API_KEY` 부재. ② outbox `CHANNEL_PUSH_RECORDED` **1,188행 전량 DEAD**.
**둘의 인과 관계를 저장소는 주장하지 않는다** — ②는 ①을 추적하는 동안 헤집게 된 소음이고,
그래서 같은 날 함께 닫혔다(`docs/AI_CHANGELOG.md:16`).

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 운영 사고 — 배포 환경변수 누락(무음 실패) + 관측 소음 |
| 원인 축 | ① `SIDEFX` 서비스에만 `KAKAO_REST_API_KEY` 가 없었다. **조사가 운영 서비스를 3개(web·WORKER·FOMS-cron)만 확인했고 GEOCODE outbox 소비단인 SIDEFX 는 그 뒤 등록돼 목록에서 빠져 있었다**(`docs/AI_CHANGELOG.md:16`) ② `CHANNEL_PUSH_RECORDED` 가 outbox 에 "배달할 일 없음" 으로 등록돼 있지 않아 1,188행이 전량 DEAD 로 남았다(같은 줄) |
| 복구 | 키 설정 + 재배포, 오탐 5건(#5095~#5099) 재변환 **5/5 success**, #2418 좌표 **2,214m** 정정(`docs/AI_STATUS.md:65`) |
| 구조 변경 여부 | 있음. `record_only_effects.py` 신설(기록 전용 effect 명시 등록) + 실패 사유 분리 · 지오코딩 4상태화 + 재시도 SSOT · 동네 중심 좌표 폴백 차단 |
| 재발 여부 | 같은 사고의 재발 기록 없음. 그러나 **env 존재 검사 도구(`tools/ops/check_deploy_secrets.py`)의 호출자가 0** 이라 같은 누락을 기계가 세는 자리는 아직 없다(`docs/plans/2026-09-06-foms-system-review-report.md:135`) |

## 2. 증상

- 지오코딩이 "AI 변환 실패" 로 끝나며 상태가 `failed` 로 남았다(`docs/AI_CHANGELOG.md:16`).
- **배포 후에도 새 `failed` 가 계속 생겼다.** 이것이 추적의 실마리였다 — **신 코드는 `failed` 를
  쓰지 않는다**(`success`/`pending`/`address_error` 뿐). 즉 옛 코드가 도는 서비스가 남아 있다는 신호다
  (`docs/AI_CHANGELOG.md:16`).
- 원장이 관측한 지문: **`attempts=1 · last_error=NULL · DONE`**(`docs/AI_CHANGELOG.md:16`).
  재시도 흔적도 오류 문자열도 없이 끝나 있는 모양이라, 로그만 보면 "정상 처리" 와 구분되지 않는다.
- 별개 축: outbox `CHANNEL_PUSH_RECORDED` **1,188행이 전량 DEAD**(08-03 이후). 같은 기간
  `CHANNELTALK_PUSH` 이벤트 **1,190건**과 수가 맞는다(`docs/AI_CHANGELOG.md:16`).
  **기능 손실은 없다** — 전송은 그 행 이전에 끝나고 이력·이벤트는 같은 트랜잭션이다.
  문제는 그 1,188행이 **진짜 배달 실패를 덮는다**는 것이다(①을 추적할 때 실제로 이 로그를 헤집었다).

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| 2026-08-03 이후 | `CHANNEL_PUSH_RECORDED` outbox 행이 DEAD 로 쌓이기 시작(최종 1,188행) | `docs/AI_CHANGELOG.md:16` |
| 2026-08-31 | `SIDEFX` 워커 서비스 등록·가동(heartbeat 3행 최초 생성, GEOCODE·STORAGE_DELETE 소진 중) | `docs/AI_STATUS.md:68` |
| 2026-09-01 | 지오코딩 조사 — 이 시점에는 트리거 "규명 못 함" 으로 남음 | `docs/AI_CHANGELOG.md:16`("어제 '규명 못 함'으로 남았던 트리거") |
| 2026-09-02 (HH:MM `미상(근거 없음)`) | 배포 후에도 새 `failed` 가 생기는 것을 보고 추적 → **SIDEFX 에만 키 부재** 확정 | `docs/AI_CHANGELOG.md:16` |
| 2026-09-02 | 그 서비스가 그날 찍은 주소 4건을 같은 운영 키로 직접 변환 → **4/4 첫 전략에서 성공**(주소는 무죄) | `docs/AI_CHANGELOG.md:16` |
| 2026-09-02 | 키 설정 + 재배포, 오탐 5건(#5095~#5099) 재변환 **5/5 success** | `docs/AI_CHANGELOG.md:16`, `docs/AI_STATUS.md:65` |
| 2026-09-02 | 운영 반영 완료(production `bbd75e08`, PR #243·#251·#253) | `docs/AI_STATUS.md:65` |

시각(HH:MM)은 어느 칸도 저장소에 없다.

## 4. 근본 원인

### ① 서비스 목록이 조사 범위였다

`SIDEFX` 서비스에만 `KAKAO_REST_API_KEY` 가 없었다. 그 이유가 이 사고의 핵심이다 —
**조사가 운영 서비스를 3개(web·WORKER·FOMS-cron)만 확인했고, GEOCODE outbox 소비단인 SIDEFX 는
그 뒤 등록돼 목록에서 빠져 있었다**(`docs/AI_CHANGELOG.md:16`). SIDEFX 등록은 2026-08-31 이다
(`docs/AI_STATUS.md:68`).

실패가 무음이 된 경로: 키가 없으면 `kakao_rest_headers()` 가 `RuntimeError` →
**(수정 전) 변환기가 그것을 삼켜** "AI 변환 실패" → `failed`(`docs/AI_CHANGELOG.md:16`).
즉 환경 결함(키 부재)이 데이터 결함(주소가 나쁘다)으로 **오분류**돼 나왔고, 그래서 조사가 주소를
의심하는 쪽으로 갔다. 같은 운영 키로 직접 변환하니 4/4 성공한 것이 그 오분류를 깬 실측이다.

### ② "배달할 일 없음" 이 등록돼 있지 않았다

`CHANNEL_PUSH_RECORDED` 는 소비할 배달이 없는 **기록 전용** effect 인데 그 사실이 outbox 에 명시
등록돼 있지 않아, 1,188행이 전량 DEAD 로 남았다(`docs/AI_CHANGELOG.md:16`).
기능 손실은 없지만 **진짜 배달 실패를 덮는 소음**이었고, 실제로 ①을 추적하는 동안 이 로그를 헤집어야 했다.

## 5. 복구

- 운영 `SIDEFX` 에 `KAKAO_REST_API_KEY` 설정 + 재배포(`docs/AI_STATUS.md:65`).
- 오탐 5건(#5095~#5099) 재변환 → **5/5 success**(`docs/AI_CHANGELOG.md:16`).
- 동네 중심 좌표를 성공으로 반환하던 폴백으로 굳은 좌표: 저장 좌표를 동네 중심 좌표와 대조해
  3,784건 중 **4건** 검출. 정체는 동 추출 정규식 `(\w+동)` 이 **구 이름에서 동을 만든 것**
  (`성동구`→`성동`)이고, 그래서 #2418 이 진짜 위치에서 **2,214m** 떨어진 좌표를 `success` 로
  저장하고 있었다. 운영 #2418 좌표 정정(승인 후, 5개 컬럼만·알림 0)(`docs/AI_CHANGELOG.md:16`).
- DEAD 1,188행 자체를 지웠는지 남겼는지 — `미상(근거 없음)`. 기록된 조치는 "기록 전용 effect 등록으로
  소음 제거" 다(`docs/AI_STATUS.md:65`).

## 6. 구조 변경

`docs/AI_STATUS.md:65` 가 여섯 갈래로 요약한다.

1. 실패 사유 분리 — 환경 결함과 데이터 결함이 같은 `failed` 로 뭉치지 않게.
2. 지오코딩 **4상태화 + 재시도 SSOT**(`pending` = 일시 오류 보류).
3. `번길` 절단(426m).
4. 구 이름 치환(3,968m).
5. **동네 중심 좌표 폴백 차단** — 시+구 만으로는 폴백 금지, 그리고 **일시 오류를 겪었으면 폴백 자체 금지**
   (네트워크가 죽은 자리를 동네 중심으로 덮으면 재시도됐어야 할 건이 굳는다)(`docs/AI_CHANGELOG.md:16`).
6. **SIDEFX 기록 전용 effect 등록** — `record_only_effects.py` 신설로 "배달할 일 없음" 을 명시 등록
   (DEAD 1,188행 소음 제거).

반영: PR #243·#251·#253, production `bbd75e08`(`docs/AI_STATUS.md:65`).
커밋 축은 `docs/AI_CHANGELOG.md:16` 이 production `c8492b6b`(PR #243) · `17bc0027`(PR #251) ·
deploy `e31dd8e5` 로 적는다.
검증: 본 스위트 7755 passed, PG 레인 738 passed, `pre_push_smoke exit 0`, CI 4/4 green,
승격 트리 직접 검증(`docs/AI_CHANGELOG.md:16`).

**의도적으로 손대지 않은 것**: `STAGE_NOTIFICATION` **118행**. 소비자가 미구현이고(운영 `notifications`
에 단계 전이 유형이 한 번도 없다) 낼지는 제품 결정이라 사용자 판단으로 보류
(`docs/AI_CHANGELOG.md:16`, `docs/AI_STATUS.md:65`).

## 7. 재발 여부·남은 것

- 같은 사고의 재발 기록은 없다. `docs/AI_STATUS.md:65` 는 "잔여 없음" 으로 이 건을 닫는다
  (`STAGE_NOTIFICATION` 118행은 별건 보류).
- 남은 것 ①: **같은 누락을 기계가 세는 자리가 없다.** 검토 보고서가 확인했다 —
  환경변수 문서는 31줄·표 0행(2026-04-15)인데 코드 env 키는 79, 그리고
  **존재 검사 도구 `tools/ops/check_deploy_secrets.py` 의 호출자가 0** 이다
  (`docs/plans/2026-09-06-foms-system-review-report.md:135`). 이 사고의 트리거였던
  "서비스 하나가 목록에서 빠진다" 는 구조가 그대로 남아 있다.
- 남은 것 ②: 문서가 권하는 부트스트랩이 alembic 소유 원칙과 충돌한다는 별건 지적도 같은 줄에 있다
  (`docs/plans/2026-09-06-foms-system-review-report.md:135`).
- 남은 것 ③: 검토 보고서는 이 사고를 "원장 밖 운영 사고 4건" 의 하나(DEAD 1,188)로 세었다
  (`:134`). 본 등재가 그 자리다.

## 8. 근거 앵커

- `docs/AI_CHANGELOG.md:16` — 트리거 규명 전문(SIDEFX 에만 키 부재 · 조사 서비스 3개 · `kakao_rest_headers()` RuntimeError → `failed` · 지문 `attempts=1 · last_error=NULL · DONE` · 신 코드는 `failed` 미사용 · 4/4 첫 전략 성공 · 오탐 5건 5/5 · 동네 중심 폴백 4건 · `성동구`→`성동` · #2418 2,214m · `CHANNEL_PUSH_RECORDED` 1,188행 DEAD / `CHANNELTALK_PUSH` 1,190건 · `record_only_effects.py` · `STAGE_NOTIFICATION` 118행 · 검증 수치 · 커밋 3벌)
- `docs/AI_STATUS.md:65` — 종결 요약 6갈래 · PR #243·#251·#253 · production `bbd75e08` · 잔여 없음 · 원장 `docs/plans/2026-09-01-geocode-transient-vs-data-error-plan.md`
- `docs/AI_STATUS.md:68` — 2026-08-31 SIDEFX 워커 서비스 등록·가동(키 부재가 성립한 시점 맥락)
- `docs/plans/2026-09-06-foms-system-review-report.md:135` — R8, env 정본 공백 · `check_deploy_secrets.py` 호출자 0
- `docs/plans/2026-09-06-foms-system-review-report.md:134` — R8, "운영 사고 4건이 사고 원장 밖"(DEAD 1,188 포함)
