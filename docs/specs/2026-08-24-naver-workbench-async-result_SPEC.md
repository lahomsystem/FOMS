# 네이버 워크벤치 — 불가역 3종 결과 즉시 반영 (2026-08-24)

상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§0 절대 규칙 6개가 판정 기준).
진행 원장: `docs/plans/2026-08-24-naver-workbench-async-result-ledger.md`.
작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`).

## 1. 현상과 진짜 원인

사용자 지적: **발주확인·발송처리·취소처리를 눌러도 새로고침해야 결과가 보인다.**

원인은 "새로고침이 없어서"가 아니다 — 발송처리·취소·주문 만들기는 이미
`window.location.reload()` 를 한다. **워커가 끝나기 전에** 새로고침해서 낡은 값을 다시
그리는 것이다. web 라우트는 큐에 넣고 `{"queued": true}` 만 돌려주고(커머스API 호출 IP
3슬롯 계약 — 네이버 HTTP 는 WORKER 단일 출구), 실제 상태는 워커가
`triage_state['fulfillment']` 에 쓴다.

발주확인만 다르다: `loadPane()` + "잠시 뒤 반영됩니다" 문구. 이것도 워커보다 빠르다.

**실패는 더 나쁘다.** 워커가 남기는 `last_error` 는 전체 렌더의 `#wb-result` 띠에만 있어
새로고침 전에는 아무 데도 안 보인다. 되돌릴 수 없는 조작에서 "보냈다"만 보이고 거절은
안 보이는 상태다.

## 2. 설계 결정과 근거

### D1. 워커 계약을 건드리지 않는다 — 가벼운 상태 조회로 "뒤집힘"을 본다
`enqueue_naver_fulfillment` 는 bool 만 돌려준다(job id 없음). job id 를 만들려면 큐 계약과
워커 계약을 함께 고쳐야 한다. 대신 **집의 fulfillment 상태 지문(rev)** 을 묻는 읽기 전용
GET 을 하나 만든다. 워커·큐 계약 무변경.

### D2. 판정을 두 벌로 만들지 않는다 (v3 리뷰 H1 재발 방지)
새 엔드포인트는 **`can_confirm`·`can_dispatch` 같은 화면 판정을 하지 않는다.** 집 정의는
`_group_of_link`(주문번호 + `household_key`) 를 **그대로 재사용**하고, 돌려주는 것은 워커가
쓴 원시 표식뿐이다:

```
{"link_id", "total", "confirmed", "dispatched", "canceled",
 "last_error", "last_error_at", "last_error_action", "rev"}
```

화면 판정 SSOT 는 여전히 `_pane_context` 하나다. `rev` 는 변화 감지용 지문일 뿐이다.

### D3. `rev` = 집 멤버의 처리 표식 지문
멤버 링크를 id 순으로 정렬해 `(id, place_confirmed_at, dispatched_at, canceled_at,
last_error_at)` 를 이어 붙이고 sha1 앞 16자. 성공도 실패도 표식을 바꾸므로 **한 규칙으로
3종 + 실패를 모두 감지**한다(워커는 성공 시 `last_error*` 를 지운다 — 그것도 변화다).

`hash()` 를 쓰지 않는다(PYTHONHASHSEED 로 프로세스마다 달라진다).

### D4. 기준 `rev` 는 enqueue **직전**에 서버가 계산해 POST 응답에 실어 보낸다
클라이언트가 POST 전에 GET 을 한 번 더 하면 그 사이 레이스가 생기고 왕복도 는다.
enqueue **후**에 잡으면 워커가 이미 끝났을 수 있어 뒤집힘을 영원히 못 본다.
레이스가 없는 유일한 지점이 enqueue 직전이다.

### D5. 뒤집히면 **화면 전체를 조용히 다시 받는다**(soft refresh) — pane 만 갈지 않는다
pane 만 갈면 왼쪽 목록 행의 `발주확인 전` 배지·칩 숫자·탭 숫자가 낡은 채 남는다. 한
화면이 두 말을 하는 상태(이 프로젝트가 반복해서 고쳐 온 결함 부류)다.

`fetch(window.location.href)` 로 지금 주소를 다시 받아 `.naver-workbench` 를 통째로
교체한다. 이 화면의 배선은 **전부 document 위임**(JS 규율 ①)이라 하위 트리를 통째로
바꿔도 죽는 핸들러가 없다. `location.reload()` 대비 자산 재다운로드·스크롤 손실·깜빡임이
없고, 목록 밖 판정(`selected_offlist`)은 오히려 서버가 다시 정확히 내려준다.

교체 후 복구할 것: 글자 배율(`--wb-fs` 인라인 스타일) 재적용, 벌크 바 동기화,
`paneOfflist` 재읽기, 교체 전 `teardownModals`(모달이 pane 파셜 안에 있다).
조각이 아닌 응답(로그인 리다이렉트·오류)이면 `location.reload()` 로 폴백한다.

### D6. 폴링은 반드시 끝이 있다
2초 간격, 최대 25초(13회). 타임아웃이면 **한 번 soft refresh 하고** "네이버 응답이
늦습니다 — 잠시 뒤 다시 확인하세요" 로 접고 멈춘다. 무한 폴링 금지.

타임아웃 후 버튼이 서버 판정대로 다시 열리는 것은 안전하다 — 워커 서비스가 멱등을
지킨다(`place_confirmed_at` 가드 / `dispatched_at` todo 필터 / `canceled_at` 필터).

### D7. 경합 차단 2중
`pollToken`(늦게 온 폴링이 새 조작을 덮지 않게) + 시작 시점 `paneToken` 캡처(사용자가 다른
집을 열면 즉시 중단). 늦게 온 응답이 새 선택을 덮으면 화면과 조작 대상이 갈린다.

폴링 중에는 pane 의 불가역 버튼 4종(`#wb-confirm`·`#wb-dispatch`·`#wb-cancel`·`#wb-create`)을
잠근다 — 응답 대기 중 재클릭이 그 자체로 사고 경로다.

### D8. 벌크는 폴링하지 않는다
집마다 폴링하면 33집 × 13회 × 조회 2회 = 858 조회다. nav 뱃지 부하 측정(승격 게이트 1번)이
끝나지 않은 상태에서 그 부하를 얹지 않는다. 대신 벌크 바에 "보내는 중" 문구를 남기고
**15초 뒤 soft refresh 1회**. 결과는 목록에서 본다.

### D9. 폴링 엔드포인트 비용
집 하나에 대해 조회 2회(주문번호로 링크 + 그 링크들의 주문). `_group_of_link` 를
`_household_of_link(db, link) -> (group, rows)` 로 쪼개 이미 읽은 링크 행을 재사용한다
(3회 → 2회). 그루핑 규칙은 여전히 `_group_queue` 한 곳.

## 3. 변경 범위

| 파일 | 변경 |
|---|---|
| `foms/web/admin/naver_ingest.py` | `_household_of_link` 분리 · `_fulfillment_state` · GET `/admin/naver-ingest/triage/fulfillment-state` · fulfillment/cancel 라우트 응답에 `rev` |
| `static/js/admin/naver-workbench.js` | `softRefresh` · `watchFulfillment` · 단건 3종 배선 · 벌크 지연 갱신 |
| `templates/admin/naver_workbench.html` | 벌크 바 상태 문구 `#wb-bulk-note` · 자산 `?v` 범프 |
| `tests/domains/test_naver_workbench_*.py` | 회귀 |

**손대지 않는 것**: 워커(`fulfillment.py`)·큐(`queue.py`)·게이트 OFF 경로
(`templates/admin/naver_triage.html`)·모달 재진술 건수 계산(계약 §0-2)·`#wb-pane` 의
`position:sticky` 금지.

## 4. 완료 기준

1. `pytest tests/domains/test_naver_workbench_v3.py tests/domains/test_naver_*.py` 전수 green.
2. 새 엔드포인트: 게이트 OFF → 404 · `link_id` 누락 → 400 · 없는 링크 → 404 ·
   응답에 판정 키(`can_*`) 없음 · 형제 전부를 센다 · 표식이 바뀌면 `rev` 가 바뀐다.
3. fulfillment·cancel POST 응답 `data.rev` 가 enqueue 직전 상태와 같다.
4. JS 계약: 폴링 상한 상수 존재 · `while(true)`·무한 재귀 없음 · `paneToken` 검사 존재.
5. `python -c "import app; print('APP_OK')"` 성공, `scripts/ops/pre_push_smoke.ps1` exit 0.
6. 스테이징에 가짜 링크(`CLAUDE-TEST-`) 1건을 심어 발주확인 → 네이버 거절 → **폴링이
   실패 사유를 새로고침 없이 화면에 띄우는 것**을 눈으로 확인 → 가짜 링크 삭제.
   실고객 주문의 불가역 버튼은 누르지 않는다.
