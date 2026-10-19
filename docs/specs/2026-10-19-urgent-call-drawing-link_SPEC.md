# 긴급 호출 수신자의 도면 작업실 링크 Spec
> 작성일: 2026-10-19 | 상태: ✅ 구현·로컬 검증 완료 — 구조 조사와 수정 방향 설명 뒤 사용자 “수정 해” 승인

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
영업 직원이 주문을 선택해 도면 직원에게 긴급 호출하면, 도면 직원이 알림 목록을 눌렀을 때 해당 주문의 도면 작업실로 이동한다.

### 1.2 기능 요구사항
1. 현재 알림을 조회하는 수신자가 DRAWING 팀이고 알림 종류가 URGENT_MENTION이며 order_id가 있으면 `deep_link_url=/erp/drawing-workbench/<order_id>`를 반환한다.
2. 수신자 팀을 기준으로 하며 직원 이름·고정 사용자 ID·주문 ID를 하드코딩하지 않는다. 팀 표기는 trim/upper로 정규화한다.
3. CS/영업 등 다른 팀의 긴급 호출·주문 없는 호출·다른 알림 유형의 링크는 기존 동작을 유지한다.
4. 기존에 저장된 알림도 목록을 다시 조회하면 새 링크를 받는다. DB 마이그레이션·알림 재발송은 없다.
5. 주문 수정 권한·도면 담당자 배정·알림 소유권·읽음/확인 정책은 변경하지 않는다.

### 1.3 예외/제약 조건
- 비활성·삭제 주문은 도면 작업실의 기존 검사에 따른다.
- OS 푸시의 포커스/빨간 긴급 창 동작과 사이렌은 범위 밖이다. 이 요청에서 제공된 공용 알림 목록의 클릭 경로를 수정한다.
- production 배포는 이번 “수정 해”에 포함하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/api/notifications/__init__.py` | 링크 계산에 조회 수신자 인자를 추가하고 도면 긴급 호출 링크를 생성 |
| `tests/domains/test_urgent_call_recipient_link.py` | 발송→도면 수신 목록→작업실 GET, 기존 알림·다른 팀·주문 없음·소유권·쿼리 수 회귀 |

### 2.2 아키텍처 방향
목록 API가 이미 확보한 `g.current_user`를 링크 계산 함수에 넘긴다. 목록의 주문 정보는 기존 in_(order_ids) 배치 조회를 유지한다. 새로운 DB 조회는 추가하지 않는다.

현행 PC 상단 벨과 모바일 벨은 모두 `data-foms-notif-open`으로 같은 시트를 열고 `mobile-notification.js`가 `deep_link_url`을 우선한다. 따라서 현재 경로의 JS 수정·캐시 버전 변경은 불필요하다. 이전 조사에서 발견한 `layout-scripts-chat.js`의 옛 PC 패널 구현은 현재 템플릿이 로드하지 않는다. 실제 `layout_scripts.html`은 공용 시트로 위임하고, nav에는 옛 panel 마크업이 없다.

### 2.3 의존성 및 영향 범위
API 응답의 기존 선택 필드만 채운다. 함수의 새 recipient 인자는 기본 None으로 하여 기존 호출·다른 도면 알림 계약을 보존한다. 인증·DB 쓰기·외부 배달 변경 없음.

## 3. Steps — 실행 단계
- [x] Step 1: DECISIONS/ARCHIVE_INDEX·발송/조회/화면/권한 조사 및 가상 계정 재현.
- [x] Step 2: 사용자 수정 승인과 이 Spec으로 범위 확정.
- [x] Step 3: 수정 전 실패하는 실제 API 경로 테스트 실행.
- [x] Step 4: 수신자 기준 링크 생성 구현.
- [x] Step 5: 관련 테스트·성능·브라우저 클릭·변경 줄 검증.

## 4. 검증 기준
- [x] 영업 발송→도면 직원의 긴급 호출 목록 링크가 정확한 주문 작업실을 가리킨다.
- [x] 도면 직원은 해당 작업실 200, 기존 edit 화면 권한 차단은 유지된다.
- [x] 이미 읽거나 확인한 기존 긴급 호출도 올바른 링크를 받는다.
- [x] 다른 팀·주문 없음·다른 알림 유형·본인 아닌 알림 비노출을 보존한다.
- [x] 한 번에 여러 알림을 조회해도 사용자별 추가 SELECT/N+1이 없다.
- [x] PC·모바일 공용 시트의 실제 클릭이 올바른 주소로 이동한다.
- [x] APP_OK, 관련 pytest, perf guard, verify_result 기준 통과.

## 5. 참고 자료
- `AGENTS.md` 공통 실행 프로토콜·권한·성능 가드.
- `docs/harness/policy/DECISIONS.md`, `docs/ARCHIVE_INDEX.md`: 긴급 알림 배달과 기존 도면 권한 결정 확인.
- `docs/specs/2026-10-01-urgent-call-global_SPEC.md`, `2026-10-16-urgent-call-multi-recipient_SPEC.md`.
- `.gstack/urgent-route-research/findings.md`, `test_current_routes.py`: 수정 전 deep_link_url=None, edit 302, workbench 200 재현.

## 6. 검증 기록
- 회귀 테스트를 먼저 실행: **4 failed, 4 passed**. 두 주문 신규 호출·기존 도면 수신자·팀 정규화·여러 알림에서 링크 None 문제를 재현했다.
- 구현 후 회귀: 8 passed. 이미 읽음/확인한 옛 알림 회귀를 추가한 최종 관련 묶음: **183 passed, 39 warnings (5.21s)**. 경고는 기존 Python 3.12 SQLite 날짜 어댑터 deprecation이다.
- `python tools/perf/perf_scan.py --guard`: high=0, medium=0. 20개 알림에서도 사용자 SELECT는 인증 사용자 조회 1회 이하.
- DB 조회문·저장·인덱스 변경 없음. 새 링크 계산은 이미 조회된 사용자/주문 id만 사용한다. 별도 PostgreSQL EXPLAIN은 수행하지 않았다.
- 실제 Flask·신규 임시 SQLite 파일·가상 STAFF/DRAWING 계정으로 gstack browse 검증. PC 1280×900에서 작업실 1 → 상단 벨 → 알림 B 클릭 → 작업실 2, HTTP 200·권한 오류 없음.
- 모바일 코호트·390×844에서 ERP 대시보드 → 모바일 벨 → 같은 알림 B 클릭 → 작업실 2, 모바일 셸 유지·권한 오류 없음. 도면 상세는 집중 화면으로 헤더가 숨겨지므로 모바일 시험 시작점은 대시보드다.
- 로컬 목록 API TTFB 3회: 12.0 / 8.8 / 9.1ms. 작은 가상 데이터 표본이며 운영 성능 증거는 아니다.
- 로컬 Werkzeug Socket.IO에서 `Invalid frame header` 경고 1건을 관측했다. 이번 HTTP 목록/클릭 이동은 정상 완료됐으며 실시간 배달 검증으로 주장하지 않는다.
- `verify_result.py --require-spec --spec docs/specs/2026-10-19-urgent-call-drawing-link_SPEC.md --json`: success=true, APP_OK. `git diff --check` 통과.
- 산출물: `.gstack/urgent-route-research/desktop-after-click.png`, `mobile-after-click.png`, `list-performance.json`, `verify-result.json`.
- 위 로컬 검증까지 실제 운영 계정·실주문은 조회/변경하지 않았다.

## 7. 배포 승인
- 사용자 “staging 배포 이상없으면 production 올려” 승인으로 이번 링크 수정만 staging 검증 후 production 승격한다.
- 다른 세션의 deploy 커밋은 production에 포함하지 않는다. 전체 smoke·CI·실제 배포 SHA·staging 클릭 검증 후 승격한다.
- 최종 배포와 시험 데이터 정리 증거는 별도 배포 보고서에 기록한다.
