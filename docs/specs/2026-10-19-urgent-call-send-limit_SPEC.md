# 긴급 호출 보낸 사람 기준 발송 상한 SPEC

- 작성: 2026-10-19 · 등급: `**A`(소형, 코어 API 변경이라 설계서 먼저) · 상태: 구현·로컬 검증 완료, 운영 반영 전 §7 질문 확인 필요
- 선행: `docs/specs/2026-10-01-urgent-call-global_SPEC.md`(§5-1 "주문 없는 호출 횟수 제한 없음"), `docs/specs/2026-10-16-urgent-call-multi-recipient_SPEC.md`(`df048d1e1`, 복수 수신자·사이렌)

## 1. 목적

긴급 호출은 받는 사람 기기에 빨간 전체 화면 + 사이렌(최대 8초) + 웹푸시를 띄운다. 지금은 주문을 고르지 않고 부르면 횟수 상한이 없다. 버튼을 실수로 여러 번 누르거나 화면이 같은 요청을 되풀이해도 현장 기기에 경보가 쏟아지지 않도록, **주문이 있든 없든 보낸 사람 한 명당 같은 상한**을 건다.

이 변경은 2026-10-01 사용자 결정 §5-1("주문 없는 호출은 제한 없음")을 2026-10-19 사용자 요청으로 바꾼다.

## 2. 지금 구조 (조사 결과, 기준 `origin/deploy` 4a967c466)

| 항목 | 지금 | 근거 |
|---|---|---|
| 입구 | `POST /erp/api/urgent-call` (`@login_required` + 쓰기 헤더 가드) → `_urgent_call_response` → `_send_urgent_call` | `foms/api/notifications/__init__.py:1172`·`:1134`·`:1097` |
| 한 번에 받는 사람 | 1~500명, 중복 제거 | 같은 파일 `:1013` |
| 주문 상한 | 보낸 사람+주문당 **시간당 알림 5건**(받는 사람 수로 셈). 주문이 없으면 바로 `False` | `:1005`·`:1037-1047`, 판정 `:1114-1115` |
| 주문 없는 상한 | **없음** | `:1039-1040`, `foms/platform/realtime.py:100-102` 주석 |
| 앱 전체 레이트리밋 | Flask-Limiter 기본값(하루 5000·시간 1200, 사용자 키)만. `/urgent-call` 에 별도 한도 없음 | `foms/services/rate_limit.py:188-240` |
| 기록 | 받는 사람마다 `Notification` 1행(`notification_type="URGENT_MENTION"`, `created_by_user_id`=보낸 사람). `created_at` 은 행마다 파이썬 기본값 | `:1050-1059`, `models.py` `Notification.created_at` |
| 권한 | `SEND_URGENT_CALL`: 모든 팀, 보기 전용 역할(VIEWER)도 허용 | `foms/services/orders/order_mutation_policy.py:231` |
| 화면 | 실패 시 `!res.ok` 면 `d.message || d.error` 를 창 안에 표시. 발송 중 버튼 잠금 | `static/js/foms/urgent-call.js:217` |

결론: 상한 판정은 주문이 있을 때만 돈다. 주문 없이 부르면 한 사람이 같은 사람들에게 끝없이 경보를 보낼 수 있다.

## 3. 변경

### 3.1 상한 값과 근거 — **보낸 사람당 10분에 10회**

- 새 모듈 `foms/services/notifications/urgent_call_limit.py` 에 상수 두 개: `URGENT_CALL_SENDER_LIMIT = 10`, `URGENT_CALL_SENDER_WINDOW_MINUTES = 10`(도메인 모듈 옆 상수, 루트 상수 모듈 없음).
- 세는 단위 = **호출 1회**(요청 1건). 받는 사람 수가 아니다. 한 번에 30명을 불러도 각 기기에는 경보 1번이라, 기기마다 쏟아지는 경보 수를 묶는 것은 호출 횟수다. 받는 사람 수로 세면 팀 전체 호출 1번이 막힌다.
- 10회인 이유: 기존 주문 상한(주문당 5건)이 짧은 시간에 먼저 걸리고, 다른 주문은 따로 센다는 기존 규칙(`tests/domains/test_urgent_call.py::test_rate_limit_is_per_order`, 주문 A 5번 뒤 주문 B 첫 호출 성공)이 그대로 살아야 한다. 5 이하로 잡으면 이 규칙이 보낸 사람 상한에 가려진다. 10 = 주문 두 개 분량.
- 10분인 이유: 실수로 연달아 누르기·화면 반복 호출은 몇 초~몇 분 안에 몰린다. 10분 창이면 폭주가 나도 보낸 사람 한 명당 10분에 10번(시간당 최대 60번)으로 묶인다. 지금은 끝이 없다. 복수 수신자가 붙어(`df048d1e1`) 여러 명을 따로따로 부를 일도 줄었다. 운영 실제 호출 빈도는 이번 작업에서 재지 않았다(실서버 접속 안 함) — §7-2 질문.

### 3.2 판정

- `urgent_sender_limit_exceeded(db, sender_id, now) -> bool`: 보낸 사람의 `URGENT_MENTION` 알림 중 `created_at >= now - 10분` 인 것의 **서로 다른 `created_at` 개수**가 10 이상이면 초과.
- 호출 1회 = `created_at` 1개가 되도록, `_create_urgent_receipts` 가 한 호출의 모든 알림 행에 **같은 발송 시각**(`sent_at`)을 넣는다. 테이블·마이그레이션은 추가하지 않는다(`created_at` 은 이미 색인이 있다).
- 실패한 요청(400·404·422·429·500)은 알림 행을 남기지 않으므로 세지 않는다. 막힌 요청이 막힌 시간을 늘리지 않는다.
- 순서: 입력 검사 → 대상 조회·검사 → 기존 주문 상한 → **새 보낸 사람 상한** → 발송. 기존 주문 상한 판정·문구는 그대로다.
- 넘으면 429 + `{"success": False, "error": 문구, "message": 문구}`. `error` 는 표준 응답 키, `message` 는 같은 엔드포인트의 다른 실패 응답과 화면(`urgent-call.js:217`)이 쓰는 키라 같이 싣는다. 문구: `긴급 호출은 10분에 10번까지만 보낼 수 있습니다. 잠시 뒤 다시 보내 주세요.`

### 3.3 함께 고치는 설명

- `foms/api/notifications/__init__.py` 상수 주석·`api_urgent_call` docstring, `foms/platform/realtime.py:100-102` 주석: "주문 없는 호출은 제한 없음" → 보낸 사람 상한 안내로 바꾼다(줄 수 유지).

### 3.4 고르지 않은 방법

- Flask-Limiter 로 라우트에 `10 per 10 minutes`: 저장소가 `memory://` 로 떨어지면 gunicorn 워커마다 따로 세고(`rate_limit.py` `_report_limiter_storage` 설명), 실패 요청도 세며, 429 응답이 표준 JSON 이 아니다. DB 판정은 기존 주문 상한과 같은 방식이라 워커가 몇 개든 같은 값을 본다.
- 새 컬럼(호출 묶음 id): 마이그레이션이 필요하다. 같은 발송 시각으로 충분하다.

## 4. 테스트

새 파일 `tests/domains/test_urgent_call_sender_limit.py`:
1. 주문 없는 호출 10번은 200, 11번째는 429·`success False`·`error` 문구, 알림 행이 늘지 않는다.
2. 주문 있는 호출과 없는 호출을 합쳐 센다(주문 A 5번 + 주문 B 5번 뒤 주문 없는 호출 429).
3. 다른 사람은 따로 센다(A 가 막혀도 B 는 200).
4. 여러 명에게 한 번 보낸 것은 1회로 센다(2명씩 10번 = 알림 20행, 11번째 429).
5. 10분이 지난 호출은 세지 않는다(기존 행 `created_at` 을 11분 앞으로 옮긴 뒤 200).
6. 한 호출의 알림 행은 모두 같은 `created_at`.

기존 테스트: `tests/domains/test_urgent_call_global.py::test_no_order_has_no_rate_limit` 는 바뀌는 결정(제한 없음)을 고정한 테스트라, "상한 안의 주문 없는 연속 호출은 성공"으로 이름·설명을 바꾼다. 나머지 긴급 호출 테스트(`grep -rln "urgent" tests/domains` 중 `test_urgent_*`)는 수정 없이 통과해야 한다.

검증 명령: 단일 파일 pytest(`-p no:playwright`, 발송 키 비움), `python -c "import app; print('APP_OK')"`, `python -m pytest -q tests/harness`, `scripts/ops/pre_push_smoke.ps1` exit 0.

## 5. 영향

- DB 쓰기·읽기: 발송 1회에 집계 쿼리 1개 추가(`notification_type`·`created_at` 색인, 최근 10분 범위). 마이그레이션·새 패키지 없음.
- 화면 변경 없음(기존 실패 문구 표시 경로 재사용).
- 줄 번호 인벤토리: import 1줄·판정 줄이 늘어 `docs/harness/foms_failopen_inventory.json` 의 `notifications/__init__.py` 항목 줄 번호만 다시 만들었다(`tools/harness/failopen_scan.py`, 분류 변화 없음). `foms_audit_coverage_inventory.json` 은 기준 커밋에서 이미 다른 파일 포함 30여 항목의 줄 번호가 어긋나 있어(`audit_coverage_scan.py --check` 가 기준 커밋에서도 drift=YES) 이번 묶음에서 다시 만들지 않았다.
- 알려진 한계: 같은 사람이 같은 순간에 요청 두 개를 동시에 보내면 둘 다 판정을 통과할 수 있다(기존 주문 상한과 같은 성질, 발송 중 버튼 잠금이 있어 실제로는 드묾). 상한은 보낸 사람별이라 여러 사람이 동시에 부르면 합쳐서 묶지는 않는다.

## 6. 되돌리기

상수 두 개를 크게 올리거나, `_send_urgent_call` 의 판정 두 줄을 빼면 지금 동작으로 돌아간다. 데이터 변화는 없다(같은 발송 시각만 넣는다).

## 7. 사용자에게 물을 것 (이번 변경에서 손대지 않음)

1. **보기 전용 역할(VIEWER)의 긴급 호출 허용 유지?** 지금 `SEND_URGENT_CALL` 은 `viewer=True`(`order_mutation_policy.py:231`), 2026-10-01 결정 §5-2 "⚡ 는 로그인한 모든 직원"과 테스트 `test_no_order_viewer_can_send` 가 이를 고정한다. 바꿀지는 사용자 결정이다.
2. **상한 값 10분 10회가 현장에 맞는지?** 더 조이거나(예: 10분 5회) 운영에서 재배포 없이 바꾸도록 환경변수로 열지 결정이 필요하다. 지금은 코드 상수다.
3. **같은 내용 연타 묶기?** 상한은 폭주를 묶지만 2~3번 연타 자체는 막지 않는다. 같은 사람·같은 대상·같은 사유를 몇 초 안에 다시 보내면 한 번으로 치는 처리가 필요하면 별도 작업으로 한다.

## 8. 검증 기록 (2026-10-19, 로컬 SQLite·발송 키 비움)

- 새 테스트 `tests/domains/test_urgent_call_sender_limit.py`: **6 passed**. 대조군 — 기준 코드(`__init__.py` 원본)로 돌리면 **6개 모두 실패**(5개 상한 없음, 1개 `sent_at` 인자 없음).
- 긴급 관련 기존 테스트 전부(`grep -rln --include=*.py "urgent" tests/domains`, 새 파일 포함): **1062 passed**.
- `python -c "import app; print('APP_OK')"`: APP_OK. `python -m pytest -q tests/harness`: **562 passed**.
- `scripts/ops/pre_push_smoke.ps1`: exit **0**(본체 12731 passed·714 skipped, 화면 구조 174 passed·27 skipped).
- 실서버·스테이징 실화면 확인은 하지 않았다.
