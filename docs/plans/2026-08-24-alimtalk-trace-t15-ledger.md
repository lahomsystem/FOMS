# T15 알림톡 발송 흔적(칩) — 플랜 + Progress Ledger

> 상위 원장: `docs/plans/2026-08-11-customer-share-phase-a-ledger.md` (T15 항목이 설계 확정본)
> 시안: artifact `94b3f16e-2205-4fc8-8982-efef511c0be4`
> 작업 트리: `c:/tmp/foms-nvphase` (브랜치 `tmp/nvbadge-phase`, 착수 시점 = origin/deploy `d88814da` 동기)
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 완료 기준 명령 exit 0 + 커밋 SHA 기록 후 DONE.

## 문제

보낸 주문에 "보냈다"가 화면에 남지 않는다. 마지막 발송 이력을 보려면 드롭다운 → 항목 → 모달
대기(2클릭+왕복)라서 아무도 확인하지 않고 누른다. 같은 고객에게 예약 안내가 두 번 나가는 것을
막을 방법이 화면에 없고, 발송 실패는 조용히 지나간다.

## 설계 (사용자 승인 확정본)

### 칩 4상태 — 알림톡 버튼 아래 상시 노출, 추가 요청 0

| 상태 | 문구 | 색 |
|---|---|---|
| 보냄(카톡) | `✓ 예약 안내 보냄 · 08-24 16:58 · 홍길동` | 초록 |
| 보냄(문자 대체) | `✓ 문자로 보냄 · 08-24 16:58 · 홍길동` | 주황 |
| 실패 | `✗ 발송 실패 · 수신 번호가 올바르지 않습니다` | 빨강 |
| 미발송 | `아직 안 보냄` | 점선 회색 |

- 시각은 **월-일 시:분**(KST)까지만. 초·연도 없음.
- 좁은 폭(모바일·태블릿)에서는 보낸 사람 이름을 떨어뜨리고 **상태 + 시각**만 남긴다.
- 자동 발송(`sent_by=null`)은 `자동 발송`으로 표기.
- 데이터는 `sd['alimtalk_measurement']` — 주문 화면이 열릴 때 이미 `window.__erpLastStructuredData`
  로 들어와 있다(PC `erpLoadStructured`, 태블릿 `state.structured`). **서버 왕복 0**.
- 실패 사유 문구는 `window.erpAlimtalkReasonLabel`(erp-alimtalk-send.js) 재사용 — 3벌째 맵 금지.

### 칩 클릭 → 발송 이력 패널

- 범위 = OrderEvent `ALIMTALK_SENT` / `ALIMTALK_FAILED` (실측 예약 안내). 도면·계약서 공유 알림톡은
  감사로그(SecurityLog `SHARE_ALIMTALK_SENT`)에 있고 기존 '공유 링크 관리(이력·회수)' 모달이 이미
  담당하므로 이 패널에 섞지 않는다.
- 행 = `시각 · 종류 · 보낸사람`(+실패면 사유 한 줄). 한글 라벨은 `order_event_display.py` 등재분.

### 채널 확정(카톡 vs 문자 대체발송)

- 접수 시점 `type=ATA` 이고 카톡 실패 시에만 벤더가 `SMS`/`LMS` 로 바꾸므로 발송 직후엔 알 수 없다.
- **발송 1분 뒤 벤더에 한 번 조회**(웹훅 아님, 사용자 결정). Solapi SDK `get_messages(message_id=…)`
  응답의 `type` 이 판별식 — `SMS`/`LMS` 면 문자로 나간 것.
- 실행 위치 = **web 프로세스**. sidefx worker 는 쓰지 않는다 — 근거: `SOLAPI_*` env 는 web
  서비스에만 등록돼 있고(원장 "템플릿 ID 는 web 서비스에만 존재 — worker·cron 없음"),
  등록된 handler 도 `STORAGE_DELETE` 하나뿐이다.
- 트리거 2곳(둘 다 클라이언트, 멱등):
  1. 수동 발송 성공 후 60초 타이머 1회.
  2. 페이지 로드 시 칩이 '채널 미확정 + `sent_at` 60초 경과' 면 1회 (타이머 중 이탈 보정).

## Task

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T15.1 | 이력 레코드 확장 — `_record_history` 에 `sent_by_name`(발송 시점 표시명 denormalize)·`channel`·`channel_checked_at` 자리 추가. 구 기록엔 이름이 없으므로 칩은 이름을 생략(축약형과 동일) | `pytest tests/domains/test_kakao_alimtalk_send.py tests/domains/test_kakao_alimtalk_api.py -q` PASS + APP_OK | DONE | b32eb0e8 | 44 passed. 구 기록엔 이름 없음 → 칩은 이름 생략 |
| T15.2 | 채널 확정 — `_solapi_lookup_channel()` + `POST /api/kakao/alimtalk/confirm-channel/<order_id>`(멱등: 이미 확정이면 no-op, 60초 미경과·message_id 없음·미설정은 표면화). manifest 2종 등재 + 감사 라벨 `ALIMTALK_CHANNEL_CONFIRMED` + audit 인벤토리 재생성 | `pytest tests/domains/test_kakao_alimtalk_channel.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py tests/domains/test_audit_action_coverage.py tests/domains/test_audit_coverage_inventory.py -q` PASS + APP_OK | DONE | 7cbb2265 | 신규 15 + 게이트 100 passed. 벤더 조회 성공하면 결과가 비어도 channel_checked_at 남겨 무한 재조회 차단, 조회 실패는 미기록(재시도 가능) |
| T15.3 | 이력 API — `GET /api/orders/<id>/events` 에 `event_type` 필터 + `created_by_name` + 한글 `label` 추가(읽기 전용·additive) | `pytest tests/domains/test_order_events_api.py -q` PASS(신규 파일) + 기존 events 테스트 PASS + APP_OK | DONE | cd3fd47e | 25 passed. 이름은 id 집합 1회 조회로 붙임(N+1 금지) |
| T15.4 | 칩 UI PC·모바일 — `static/js/orders/erp-alimtalk-trace.js` 신규 + `erp-pro.css` 칩 클래스(인라인 스타일 금지) + PC 액션바/모바일 sticky bar 마운트 + 이력 패널 + `?v` 핀 등록·범프 | `pytest tests/visual/test_alimtalk_ui_contract.py tests/domains/test_erp_order_shared_form_scripts.py -q` PASS + APP_OK | DONE | (이 커밋) | 91 passed. send-manual 응답에 last 추가로 발송 직후 갱신도 추가 조회 0 |
| T15.5 | 태블릿 칩 — `tablet-measure-form.js` 상단 바에 같은 칩(`state.structured` 재사용, 축약형) + 발송 후 갱신 | 태블릿 계약 테스트 PASS + APP_OK | PENDING | | |
| T15.6 | 통합 검증·스테이징 E2E | `scripts/ops/pre_push_smoke.ps1` exit 0 + `gh run list` 전 워크플로 green + 스테이징에서 칩 4상태 육안 확인(발송→칩 즉시 갱신→60초 후 채널 확정) | PENDING | | |

## 경계 (하지 않는 것)

- 공유 링크(도면·계약서) 알림톡 칩은 만들지 않는다 — 이번 칩은 **실측 예약 안내** 한 종류.
- 웹훅 수신 엔드포인트를 만들지 않는다(사용자 결정).
- sidefx worker handler 를 등록하지 않는다(worker 에 벤더 env 없음).
- 문서 공유 링크 템플릿 2종의 `replacements`(문자 대체발송 문구) 등록은 Solapi **콘솔 작업**이라
  코드 범위 밖 — 상위 원장 T15 ① 잔여로 남는다.
