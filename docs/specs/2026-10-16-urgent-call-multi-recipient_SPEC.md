# 긴급 호출 수신자 분류·복수 발송·경광등 Spec
> 작성일: 2026-10-16 | 상태: ✅ 구현·로컬 검증 완료 — 사용자 "진행 해", "4번도 진행 해" 승인

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
PC·모바일 공용 긴급 호출 창에서 시스템 계정은 기타로 분리하고 여러 사람을 골라 한 번에 발송한다. 수신자의 빨간 전체 화면에는 종 대신 경찰 경광등 애니메이션을 표시한다. 사용자 추가 승인으로 화면 사용 중 사이렌 재생도 구현한다.

### 1.2 기능 요구사항
1. 네이버 수집봇·미배정(네이버 수집)은 원래 CS/SALES 소속을 바꾸지 않고 긴급 호출 목록에서만 `기타`로 분류한다. 시스템 계정의 식별은 표시 이름의 부분일치가 아니라 기존 `ACTOR_USERNAME`, `OWNER_USERNAME` 상수를 사용한다. 실제 직원의 팀 분류는 유지한다.
2. 사람 버튼은 복수 선택·선택 해제를 지원한다. 팀 탭을 바꿔도 선택을 유지하고 선택한 사람과 인원수를 확인·해제할 수 있다. 창을 새로 열면 선택을 초기화한다.
3. 보내기 버튼은 `구범진에게 보내기` 또는 `구범진 외 2명에게 보내기`처럼 대상을 표시한다. 선택 없음·사유 없음·발송 중에는 잠근다. 사유는 기존처럼 trim 후 1..500자.
4. POST `/erp/api/urgent-call`에 `target_user_ids` 배열을 추가한다. 기존 단일 `target_user_id` 요청도 지원한다. 배열·단일 필드 동시 전달은 모호하므로 400으로 거절한다. 중복 id는 제거하고, 정수가 아닌 값·bool·소수·빈 배열은 400으로 거절한다. 후보 목록과 같은 최대 500명으로 입력을 제한한다.
5. 수신자를 일괄 조회·검증하고 각 수신자별 기존 Notification → receipt → CREATED event → SIDEFX outbox → 감사 로그를 동일 트랜잭션에서 생성한다. 하나라도 실패하면 전부 롤백한다. 커밋 후에만 배지 무효화·실시간 emit을 수행한다. 각 수신자는 자기 알림만 확인한다.
6. 주문 있는 호출은 기존 발송량 제한(발신자+주문당 시간당 알림 5건)을 보존한다. 기존 건수+중복 제거한 새 수신자 수가 5를 넘으면 전부 429로 거절한다. 주문 없는 호출은 기존처럼 시간당 제한이 없다.
7. 수신 화면은 기존 빨간 배경·사유·보낸 사람·확인 버튼을 유지한다. 종의 좌우 흔들림을 외부 이미지/폰트에 의존하지 않는 경찰 경광등과 회전 빛 애니메이션으로 바꾼다. `prefers-reduced-motion`에서는 애니메이션을 끈다.
8. 사용자 클릭·키 입력에서 재사용 AudioContext를 준비한다. 수신 큐의 현재 알림만 사이렌을 최대 8초 재생하며 확인 즉시 정지한다. 호출 창과 수신 화면에 소리 켜기·시험(2초)·재생 상태를 제공한다. 차단/미지원은 화면에 안내하고 실패는 로그로 남긴다. 페이지 종료 시 오디오를 정리한다. 브라우저 종료·휴대폰 잠금 상태의 지정 사이렌 재생은 보장하지 않는다.

### 1.3 예외/제약 조건
- 시스템 계정은 삭제하거나 로그인/팀/주문 담당자 데이터를 변경하지 않는다. 사용자의 요청은 목록에서 기타로 옮기는 것이다.
- 기존 자기 자신 금지·비활성 사용자 422·없는 사용자 404·인증/쓰기 헤더·외부 협력사 범위·주문 read scope를 보존한다. 새 복수 입력에서도 INTERNAL_USERS_ONLY 정책과 발송 검증의 일치 여부를 확인한다.
- 브라우저에서 여러 번 단일 발송 요청을 보내는 방식은 부분 발송을 만들므로 사용하지 않는다.
- 4번은 추가 승인에 따라 화면 내 사이렌까지 구현한다. 네이티브 앱·서비스 워커의 OS 알림음 변경은 범위 밖이다.
- 푸시·운영 배포는 별도 요청 없이 수행하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/api/notifications/__init__.py` | 후보 표시 분류, 단일/복수 입력 정규화, 수신자 일괄 검증, 원자적 복수 발송 |
| `static/js/foms/urgent-call.js` | 복수 선택 상태·팀 간 유지·선택 해제·단일 POST |
| `templates/partials/shared/urgent_call.html` | 복수 선택 안내·선택된 사람 영역 |
| `static/css/foundation/erp-pro.css` | 선택된 사람 표시(기존 긴급 호출 스타일 사용 우선) |
| `static/js/foms/foms-urgent-alert.js`, `urgent-sound.js` | 경광등 DOM, 큐별 유한 사이렌, 제스처 기반 오디오 준비·시험·정리 |
| `static/css/components/foms-urgent-alert.css` | 경광등·회전 빛·reduced-motion |
| `templates/partials/shared/layout_scripts.html`, `layout_head.html`, `templates/drawing/wizard.html`, `templates/measurement/map_view.html` | 변경된 공용 자산 버전 핀 갱신 |
| `tests/domains/test_urgent_call_global.py`, `test_urgent_call_js_behavior.py`, `test_urgent_alert_module.py`, `test_urgent_alert_wiring.py` | 서버·JS·접근성·공용 페이지 회귀 검증 |

### 2.2 아키텍처 방향
새 전송 채널·테이블·워커를 만들지 않는다. 기존 수신자별 알림과 durable outbox를 재사용하고 트랜잭션 경계만 복수 수신자를 감싸도록 확장한다. 신규 helper는 역할별로 나누고 타입 힌트·docstring을 둔다. 후보는 기존 bounded 조회, 발송 대상은 `User.id.in_(ids)`로 조회해 사용자 조회 N+1을 피한다. 수신자별 outbox/감사 행은 기존 계약에 필요한 쓰기다.

```text
여러 팀에서 사람 선택 → 단일 POST(target_user_ids)
  → 전체 입력/대상/발송량 검사
  → [수신자별 알림 + receipt + event + outbox + 감사] → 한 번 commit
  → 수신자별 실시간 표시 + 기존 durable 배달
  → 각 수신자가 자기 알림 확인
```

### 2.3 의존성 및 영향 범위
- DB 마이그레이션·추가 라이브러리 없음.
- 공용 수신 모듈을 쓰는 ERP·도면 마법사·실측 지도에 같은 애니메이션 적용. 자산 핀 갱신이 필요해 템플릿 여러 개에 변경이 걸친다.
- 현재 원인: `_urgent_targets_payload`는 active/internal만 검사하고 실제 직원 여부를 표시하지 않는다. JS `teamKey`는 `team`만 읽는다. `_send_urgent_call`과 JS 상태/본문은 단일 id 전용이다. 수신 아이콘은 `🔔` 문자열과 `foms-urgent-alert-ring` 애니메이션이다.
- gstack Codex wrapper 전제인 `tools/harness/task_classifier.py`, `run_codex.ps1`은 이 checkout에 없다. 실제 존재하는 pytest·perf guard·verify_result와 사용 가능한 브라우저 런타임으로 검증하며 실행하지 못한 검증은 구분해 기록한다.

## 3. Steps — 실행 단계
- [x] Step 1: 정책·기존 Spec·API·공용 창·수신 화면·시스템 계정 정본 조사.
- [x] Step 2: 사이렌 소리의 웹 플랫폼 제약 확인, 이 Spec 작성.
- [x] Step 3: 사용자 승인(1~3번 진행 및 4번 추가 구현).
- [x] Step 4: 분류·복수 입력/발송의 실패 회귀 테스트를 먼저 확인하고 서버 구현.
- [x] Step 5: 복수 선택 UI·경광등·사이렌 구현·자산 핀 동기화.
- [x] Step 6: 변경 줄 검토, 관련 테스트·성능 가드·화면 검증 후 결과 기록.

## 4. 검증 기준
- [x] 안전한 로컬 테스트 환경에서 `python -c "import app; print('APP_OK')"` 통과.
- [x] 시스템 계정은 기타, 같은 팀 실제 직원은 본래 팀에 표시된다. 계정의 DB 소속은 변하지 않는다.
- [x] 2명 이상·다른 팀 선택 유지·해제·창 재개방 초기화·선택 인원수·발송 중 중복 클릭 방지가 동작한다.
- [x] 복수 발송 성공 시 수신자마다 알림/receipt/event/outbox가 생성되고 단일 commit을 사용한다.
- [x] 중복 수신자는 1회만 발송한다. 단일 id 옛 요청도 성공한다.
- [x] 잘못된 id·자기 자신·비활성·미존재·외부 계정·빈 사유·상한 초과·중간 쓰기 실패 시 부분 알림/배달이 없다.
- [x] 주문 시간당 5건 경계를 복수 입력으로 넘을 수 없다. 주문 mutation_version은 변하지 않는다.
- [x] 여러 수신자의 확인 상태는 서로 독립적이다. 기존 큐·재조회·중복 제거·키보드 가둠·확인 실패 처리가 유지된다.
- [x] Chromium PC·모바일 viewport에서 경광등 확인. reduced-motion 정지 규칙·standalone 무폰트 DOM/CSS는 정적 계약 검증.
- [x] 공용 자산 모든 include 버전이 일치한다. 기존 긴급 호출/알림 pytest, 구조 테스트, `python tools/perf/perf_scan.py --guard` 통과.
- [x] 로컬 TTFB·SQLite 쿼리 계획 측정. PostgreSQL·실제 모바일/잠금화면 미검증은 아래 명시.
- [x] `.agents/workflows/verify-result.md` 기준 및 `tools/harness/verify_result.py --require-spec --json` 결과를 기록한다.
- [x] Node 실행으로 제스처 전 컨텍스트 미생성·재사용·8초/2초 상한·ack 시 정지·pending resume 취소·차단/미지원 안내 검증.
- [x] 실제 Chromium AudioContext running 및 파형 peak>0, 확인 후 peak=0, Tab으로 소리 버튼 접근 검증.

## 5. 참고 자료
- `AGENTS.md` 공통 실행 프로토콜: 코어 API 변경은 Spec 사용자 승인 후 구현.
- `docs/harness/policy/DECISIONS.md` 2026-09-30: push enqueue의 durable 동작 유지.
- `docs/ARCHIVE_INDEX.md`: 긴급 알림 미전달 RCA, 알림 패키지 계약 이력 조사.
- `docs/specs/2026-10-01-urgent-call-global_SPEC.md`, `2026-10-02-urgent-alert-everywhere_SPEC.md`.
- `foms/services/integrations/naver_commerce/accounts.py`, `constants.py`: 시스템 계정의 활성 CS/SALES는 수집 계약에 필요.

### 5.1 소리 검토 결과 (2026-10-16 공식 문서 확인)
| 상태 | 검토 결과 |
|------|-----------|
| PC·모바일에서 FOMS를 열어 사용 중 | Web Audio로 경찰 사이렌 합성 가능. 사용자 클릭으로 AudioContext 생성/재개를 허용받고 재사용해야 한다. 탭 음소거·기기 음량·브라우저 정책 때문에 항상 들린다고 보장할 수 없다. |
| PC 다른 탭·모바일 백그라운드 | 페이지 정지/절전/브라우저 정책에 따라 JS·오디오 실행이 제한될 수 있다. 계속 재생을 보장할 수 없다. |
| 브라우저 종료·휴대폰 잠금 상태의 Web Push | 표준 Notifications API에는 커스텀 sound 파일 옵션이 없다. OS 알림음은 기기/알림 권한/집중 모드 등에 달려 있다. 웹푸시만으로 경찰 사이렌을 지정할 수 없다. |
| 승인 전 구현 | 새 알림마다 AudioContext를 생성해 0.3초 전자음을 예약했다. suspended 상태의 사용자 제스처 기반 resume과 컨텍스트 정리가 없었다. |

근거:
- [Chrome autoplay / Web Audio](https://developer.chrome.com/blog/autoplay/): 사용자 제스처 전 AudioContext는 suspended, 제스처에서 resume 필요.
- [WHATWG Notifications API](https://notifications.spec.whatwg.org/#dictdef-notificationoptions): sound 옵션 없음, silent 기본 null은 플랫폼 관례에 따른다.
- [WebKit iOS·iPadOS Web Push](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/): 홈 화면 웹앱 Web Push와 Focus 연동.

추가 승인 후 소리 켜기/시험 재생, 재생 상태 표시, 유한 재생, 확인 시 정지와 자원 해제를 구현했다. 실제 스마트폰 스피커·잠금화면 시험은 수행하지 않았다.

### 5.2 승인 전 기준선 확인
- SQLite 메모리 DB에서 `python -m pytest tests/domains/test_urgent_call_global.py tests/domains/test_urgent_call_js_behavior.py tests/domains/test_urgent_alert_module.py -q --tb=short`: **36 passed**, 기존 경고 5건.
- 이 결과는 기존 동작의 기준선이다. 아직 새 기능 회귀 테스트·구현·브라우저 검증은 수행하지 않았다.
- 코드 변경 없음. 이 Spec만 추가했다.

### 5.3 구현 후 검증 기록
- 새 복수 발송 테스트를 기존 코드에서 먼저 실행: **11 failed, 14 passed**. 기타 분류·복수 발송 미지원 및 비객체 JSON의 500을 재현했다.
- 관련 기능 묶음: **93 passed**. 오디오/경광등/모바일 배선 묶음: **39 passed**.
- 1차 전체(본체+하네스, PostgreSQL/visual 제외): **13008 passed, 2 failed, 5 skipped**. 지연 import 래칫은 의존성 없는 시스템 계정 상수의 top-level import로 수정했다. 나머지는 요청 종료 뒤 만료된 ORM 객체 대신 요청 전 저장한 id로 검증하도록 테스트를 수정했다(소유권·receipt 검증 내용은 유지).
- 최종 본체 전체: `python -m pytest tests --ignore=tests/postgres --ignore=tests/visual --ignore=tests/harness -n 4 --dist loadfile -q --tb=short -p no:playwright` → **12451 passed, 5 skipped** (135.56s).
- 화면 구조: `python -m pytest tests/visual -p no:playwright -n 4 --dist loadfile -q --tb=short` → **174 passed, 27 skipped**. PNG 비교는 정책대로 미실행.
- 레이어/소유권/파일크기/하네스 drift 재검증 → **40 passed**. 오디오·선택 JS·파일크기 재검증 → **19 passed**. 래칫 예외·기준선은 늘리지 않았다.
- `python tools/perf/perf_scan.py --guard`: **high=0, medium=0**. 수신자 SELECT에 검증된 입력 개수만큼 limit을 둔다.
- `verify_result.py --require-spec --spec docs/specs/2026-10-16-urgent-call-multi-recipient_SPEC.md --json`: success=true, APP_OK.
- 변경 줄 검토: 선택은 textContent/aria-pressed, 신규 script는 defer·singleton, 바깥 배경/Esc로 경고를 닫지 않는 계약 유지. 공용 모듈은 300줄 미만, 별도 오디오 모듈은 109줄.
- gstack browse 실제 Chromium: 1280×900·390×844에서 선택/기타/보내기/수신 화면 확인. 한 POST에 `[20,52]` 전송. 새 페이지에서 제스처 전 오디오 미생성·차단 안내, 소리 시험 클릭 후 AudioContext=running·파형 peak=15 확인. 확인 후 overlay 없음·peak=0·본인 ack 1건. 2건 큐의 순차 확인, Tab의 소리 버튼 접근, ack 실패 안내/재시도도 확인. UI 배달은 격리 fixture의 mock API이며 실제 직원에게 발송하지 않았다.
- 별도 **신규 로컬 SQLite 파일 DB**의 실제 Flask HTTP API로 측정(curl time_starttransfer): 목록 17.2/9.0/8.3ms, 1명 발송 21.4ms, 3명 발송 23.7ms(모두 HTTP 200). 사용자 SELECT는 1명/3명 모두 3회. SQLite EXPLAIN은 `SEARCH users USING INTEGER PRIMARY KEY (rowid=?)`. 작은 로컬 표본이며 운영 성능을 증명하지 않는다.
- 로컬 산출물(미추적 `.gstack/urgent-qa/`): PC/모바일 보내기·받기 PNG, 성능 JSON, DB 없는 UI fixture와 임시 DB 측정 스크립트.
- 남은 실제 환경 검증: PostgreSQL EXPLAIN·Redis/SIDEFX worker를 통한 실제 푸시 배달·Android/iOS 스피커 및 잠금화면. 운영 접근·커밋·푸시·배포는 수행하지 않았다.
