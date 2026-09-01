# 카카오 알림톡 v1 — Progress Ledger

> 플랜: `docs/plans/2026-07-29-kakao-alimtalk-v1-plan.md` / 스펙: `docs/specs/2026-07-29-kakao-alimtalk-v1-design.md`
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 검증 명령 exit 0 + 커밋 SHA 기록 후 DONE. compaction 후 재개 시 이 파일이 정본.

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T0 | 선결 확인 (sidefx worker·solapi 의존) | `SOLAPI_OK` + T0.decision 기록 | DONE | 57ee6e5e | 2026-08-11 **WORKER_OFF**. 2026-09-01 운영 SIDEFX SUCCESS → **WORKER_ON** 승격(자동 발송=handler, 수동=동기 유지). 사용자 확인: Solapi 설정 완료 |
| T1 | 변수 빌더·자격 판정 | `pytest tests/domains/test_kakao_alimtalk_service.py -q` PASS + APP_OK | DONE | 02195c63 | 24 passed 오케스트레이터 재검증. 멱등키=`alimtalk:measure:` 포맷으로 스펙 정정. 전화=첫 유효 토큰. 길이 가드 2단(축약+절단) |
| T2 | Solapi 발송·이력 기록 | `pytest tests/domains/test_kakao_alimtalk_send.py -q` PASS + APP_OK | DONE | 3a97bbfb | 47 passed+회귀 208 재검증. D3 브랜드 분기, 앵커 이벤트 승격, 슬롯 미소진 스킵. 2026-09-01 자동 동기 폴백 제거 → T2b |
| T2b | 자동 발송을 SIDEFX handler 로 | `pytest tests/domains/test_kakao_alimtalk_send.py tests/domains/test_alimtalk_delivery_handler.py -q` PASS + APP_OK | DONE | 42668632b | 저장=예약만, 워커=Solapi. 수동은 동기 유지. SIDEFX 에 SOLAPI_* 복사 필요. 사용자 확인: Solapi 설정 완료 |
| T3 | 자동 트리거 3경로 배선 | `pytest tests/domains/test_kakao_alimtalk_trigger.py tests/domains/test_erp_orders_structured*.py -q` PASS | DONE | 529da0b7 | 배선 3곳(PUT :1159·PATCH :849·field_update :597 measurement_date 가드)+MEASUREMENT_TIME_CHANGED 이벤트. 재검증 74 passed. red 확인 완료 |
| T4 | 수동 API + manifest 등재 | `pytest tests/domains/test_kakao_alimtalk_api.py tests/domains/test_write_guard.py -q` PASS | DONE | cb58edb6 | 45 passed 재검증. preview GET+send-manual POST, manifest 2종 등재, body 전면 무시. 후속 후보: _ineligible_reason public 승격 |
| T5 | UI 3표면 | 계약 테스트 PASS + gstack browse 3뷰포트 스모크 | DONE | baa0fee8 | 117 passed 재검증(게이트 포함). 태블릿=자체 흐름(선례 준수), 상태 한 줄+모달. browse 스모크는 T6에 통합 실행 예정 |
| T0 | 선결 확인 (sidefx worker·solapi 의존) | `SOLAPI_OK` + T0.decision 기록 | DONE | 0e373534 | T0.decision: **WORKER_OFF** (2026-08-11 railway status — 서비스 web·WORKER·FOMS-cron·Postgres·Redis뿐, sidefx 미가동 → 동기 폴백 경로). SOLAPI_OK 확인. 키는 로컬 .env(gitignore) 저장 |
| T1 | 변수 빌더·자격 판정 | `pytest tests/domains/test_kakao_alimtalk_service.py -q` PASS + APP_OK | DONE | 1e84ce58 | 24 passed 오케스트레이터 재검증. 멱등키=`alimtalk:measure:` 포맷으로 스펙 정정. 전화=첫 유효 토큰. 길이 가드 2단(축약+절단) |
| T2 | Solapi 발송·이력 기록 | `pytest tests/domains/test_kakao_alimtalk_send.py -q` PASS + APP_OK | DONE | 9f9f5c86 | 47 passed+회귀 208 재검증. WORKER_OFF 동기 경로, D3 브랜드 분기, 앵커 이벤트 승격 패턴, 슬롯 미소진 스킵(원인 해소 후 자동 재개) |
| T3 | 자동 트리거 3경로 배선 | `pytest tests/domains/test_kakao_alimtalk_trigger.py tests/domains/test_erp_orders_structured*.py -q` PASS | DONE | 377934fa | 배선 3곳(PUT :1159·PATCH :849·field_update :597 measurement_date 가드)+MEASUREMENT_TIME_CHANGED 이벤트. 재검증 74 passed. red 확인 완료 |
| T4 | 수동 API + manifest 등재 | `pytest tests/domains/test_kakao_alimtalk_api.py tests/domains/test_write_guard.py -q` PASS | DONE | e50e4366 | 45 passed 재검증. preview GET+send-manual POST, manifest 2종 등재, body 전면 무시. 후속 후보: _ineligible_reason public 승격 |
| T5 | UI 3표면 | 계약 테스트 PASS + gstack browse 3뷰포트 스모크 | DONE | (T5 커밋) | 117 passed 재검증(게이트 포함). 태블릿=자체 흐름(선례 준수), 상태 한 줄+모달. browse 스모크는 T6에 통합 실행 예정 |
| T6 | 통합 검증·스테이징 | pre_push_smoke exit 0 + CI green + E2E 기록 | DONE | (기록 커밋) | 2026-09-01 스테이징 E2E 완주 — 자동 2통·수동 1통 실제 도착 확인(사용자). 아래 §T6 E2E 증거 |

## 외부 준비 (사용자 액션 — 코드와 병행, 스펙 §4)
- [ ] 채널: 홈 공개 ON + 고객센터 정보 입력 (pfId 발급 전제)
- [x] Solapi 가입 (2026-08-11, API 키 발급 — 로컬 .env 저장, 채팅 노출분이라 운영 전 회전 권장) → 채널 연동·발신프로필 등록은 잔여
- [ ] SMS 발신번호 등록 (failover 전제)
- [ ] 템플릿 심사 제출 (스펙 §5 동결본 + 변수 예시 텍스트) — 2~10영업일
- [ ] 개인정보처리방침 수탁사 추가
- [ ] Solapi 콘솔 잔액 알림 설정
- [ ] Railway env 6종 등록 (키 발급 후 — T6-3)

## 결정 기록
- D0 접근안 A / D1 HOLD SCOPE / D2 수동=확인 후 허용 / 버튼=WL 문의하기(pf.kakao.com chat)
- 3-agent 교차검수 반영: 신규 테이블·RQ task 폐기, diff 트리거 폐기, failover 전제 정정

## T6 스테이징 E2E 증거 (2026-09-01)

환경: FOMS-DEV(lahom-dev.up.railway.app), 계정 `claude_master`, 대상 주문 **id 4716** `CLAUDE-TEST-공유흔적`, 수신 **010-****-7282**(직원 본인 번호).

사전 확인
- FOMS-DEV SIDEFX 서비스 SUCCESS, 로그 `[sidefx-worker] started owner=774ab9a3b83d interval=5s expiry=300s retention=86400s` — 크래시 없음.
- SIDEFX 에 `SOLAPI_*` 16키 + `DATABASE_URL` 존재(웹과 동일 이름). 값 미열람.
- 웹 `FOMS_ALIMTALK_AUTO_ENABLED=1`.

결과
| 항목 | 결과 |
|---|---|
| (a~c) 워커 생존·열쇠·자동 플래그 | PASS |
| (d~e) 실측일 `2026-09-05` 저장 → 자동 발송 | outbox **id 119** PENDING → **DONE ≤5초**, attempts=1, last_error 없음. `alimtalk_measurement.error=null`, `sent_at=2026-09-01T06:53:32`, `message_id=G4V20260901155332G1PF4YAFWVDTZLA`. 폰 도착 확인(사용자) |
| (f) 같은 일정 재저장 | **재발송 없음** — outbox 행 1개 유지, message_id·sent_at 불변(UNIQUE 멱등 작동) |
| (g) 실측일 `2026-09-06` 변경 | 새 dedupe 키로 **outbox id 121** 생성 → DONE ≤5초, `message_id=G4V20260901155839QE0AXBHRTP1KSBN`. 두 번째 통 도착 |
| (h) 수동 버튼 `POST /api/kakao/alimtalk/send-manual/4716` | **200, 1.05초 동기 응답**, `sent=true`, `error=null`, `message_id=G4V20260901155952SZ22GBTOKQDJSHV`. outbox 행 증가 없음 = 수동은 워커를 안 탄다(설계대로) |

정리: 검증 후 주문 4716 을 앱 경로로 다시 휴지통 이동(`deleted_at=2026-09-01 06:59:53`).

### T6 에서 발견한 결함 (별도 승인 대상 — 이번 범위 밖)
**자동 발송 자격 판정에 soft-delete 검사가 없다.** 주문 4716 은 검증 시작 시점에 이미
`deleted_at=2026-09-01 00:47:38` 로 휴지통에 있었는데, `POST /api/update_order_field` 로 실측일을
저장하자 자동 알림톡이 **정상적으로 두 통 나갔다**. 반면 수동 API 는 같은 주문에 404
`order_not_found` 를 돌려준다 — `_load_order` 가 `Order.active_filter()` 를 쓰기 때문이다.
`kakao_alimtalk._ineligible_reason` 은 draft 만 보고 삭제 축을 보지 않는다.
영향: 삭제된 주문을 저장하는 경로(API 직접 호출, 삭제 직전 저장 레이스)에서 손님에게 안내가 나갈 수 있다.
**수정 완료 (2026-09-01, 사용자 승인)**: `_is_deleted_order` 를 추가하고 `_ineligible_reason`
판정 맨 앞(주문 존재 확인 바로 뒤)에 넣었다. 판정은 `Order.not_deleted_filter` 와 동치
(`status=='DELETED'` 또는 `deleted_at` 채워짐). 사유 코드는 수동 API 와 같은
`order_not_found` — 화면 3곳의 사유 문구 맵에 이미 있는 코드라 UI 변경이 없고,
`_RECORDED_SKIP_REASONS` 에 없으므로 이력도 남기지 않고 멱등 슬롯도 쓰지 않는다.
회귀 테스트 2개(soft delete·`status='DELETED'`)를 먼저 red 로 만든 뒤 고쳤다.

## 운영 상태 (2026-09-01 승격 후) — 정본

승격: PR #236 병합, production `4423afe36`. 자기 커밋 5개 cherry-pick(충돌 0), 승격 트리에서
`import app` APP_OK · 알림톡 46 passed · pre_push_smoke exit 0 · CI 본 스위트 7522 passed.
PR 검사 4종(test·pg-lane·harness·perf-gate) 전부 SUCCESS. 배포 후 web·WORKER·SIDEFX SUCCESS,
`GET /login` 200.

**운영 자동 발송은 켜지 않았다(사용자 결정: "자동은 필요없다, 예약 안내 발송을 눌렀을 때만").**

| 발송 경로 | 지금 누가 보내나 | 근거 |
|---|---|---|
| 실측 예약 안내 **자동** | (꺼짐) 켜면 SIDEFX `ALIMTALK_SEND` handler | `foms/services/alimtalk_delivery_handler.py:71` |
| 실측 예약 안내 **수동 버튼** | web 동기 | `foms/api/kakao/__init__.py:119` |
| 공유 링크 **알림톡** | web 동기 (`sync_only`, 이관 불가) | `foms/api/share.py:1444`·`:1433` |
| 공유 링크 **문자(SMS 폴백)** | web 동기 | `foms/api/share.py:1017` |
| 발송 후 채널 확정 조회 | web 동기 | `foms/services/kakao_alimtalk.py:827` |

즉 **지금 운영에서 실제로 나가는 알림톡·문자는 전부 web 이 보낸다.** SIDEFX 알림톡 handler 는
코드만 올라가 대기 상태다. 운영 SIDEFX 에 `SOLAPI_*` 는 복사하지 않았다(불필요).

### 자동 경로를 web 으로 되돌리지 않은 이유 (2026-09-01 재확인)
자동이 꺼진 상태에서 되돌리기의 이득은 0이다 — 그 코드는 실행되지 않는다. 반면 비용은
실재한다: T2b 한 건에 커밋 3개(본 작업 + writer 인벤토리 줄번호 + 순환 import 수리)가 들었고,
나중에 자동을 켤 때 다시 SIDEFX 로 옮겨야 한다(동기 폴백과 handler 는 동시에 둘 수 없다 —
같은 예약을 둘이 소비해 두 통이 나간다). 사용자 확인: **"나중에 쓸 수도 있다"** → 구조 유지.
자동을 영원히 안 쓰기로 바뀌면, 그때의 정리는 '동기 복원'이 아니라 자동 경로(트리거 3곳 +
handler + outbox 예약) 전면 제거이며 별도 계획·승인 대상이다.

### 자동을 켤 때의 선결 (순서 고정)
1. 운영 SIDEFX 에 `SOLAPI_*` 복사 → 2. SIDEFX 재배포 + handler 등록 확인 →
3. 그 다음에야 web `FOMS_ALIMTALK_AUTO_ENABLED=1`.
추가로 닫아야 할 구멍: `_solapi_send` 가 outbox 의 `provider_idempotency_key` 를 벤더로 안
싣는다 — 워커가 발송 성공 직후·커밋 전에 죽으면 lease 만료 회수로 두 통이 나갈 수 있다.
