# 고객 공유 채널 Phase A — 구현 플랜 (v1)

> 스펙: `docs/specs/2026-08-11-customer-share-phase-a-design.md` (v3, USER-DECIDED)
> 원장: `docs/plans/2026-08-11-customer-share-phase-a-ledger.md`
> 작업 트리: `c:/tmp/foms-alimtalk-reapply` (브랜치 `alimtalk-reapply`, 알림톡 T0~T5 커밋 위에 이어서)
> 병행 원장: `docs/plans/2026-07-29-kakao-alimtalk-v1-ledger.md` (알림톡 T6은 발신번호·심사 완료 시 별도 진행)

## 0. 전역 경계 (모든 task 공통)

- **worktree에서 alembic 업그레이드 실행 금지** — 마이그레이션은 파일만 작성, `migration_chain` 게이트(단일 head)로 검증.
- **models.py 드리프트 3건(read_receipt_id 등) 불가침** — 신규 모델·컬럼 추가만, 기존 정의 수정 금지.
- 기존 JS 파일 수정 시 **?v 범프 + 핀 전수 grep** (SW staticCacheFirst).
- 인라인 스타일 금지(erp-pro.css 체계), 신규 함수 docstring+타입 힌트, API 응답 `{'success': ...}` 통일.
- structured_data 수정 시 deepcopy+flag_modified 패턴 (본 기능은 sd 쓰기 없음 — 읽기만).
- 커밋: UTF-8 파일 `git commit -F <msg파일> -- <경로들>` (경로 한정 — 동시 세션 staged 오염 방지).
- WORKER_OFF 환경(알림톡 T0.decision 계승) — side effect는 동기 폴백 경로.

## 1. 플랜 단계 확정 사항 (스펙이 위임한 2건)

- **스냅샷 64KB 캡 (스펙 §6)**: drawing_wizard 64KB 캡 선례 채택. 직렬화 후 65,536 bytes 초과 시 create API가 `400 {'success': False, 'error': '견적 항목이 너무 많아 공유 스냅샷을 만들 수 없습니다'}` — 절단·축약 없음(금액 문서 부분 동결 금지).
- **send-sms 멱등 정확 규칙 (스펙 §3.3, 반증 HIGH-4)**: ① 클라 버튼 잠금(발송 중 disabled) ② 서버: 동일 share_id의 `SHARE_SMS_SENT` 감사 기록이 최근 5초 내 존재하면 `409` 거절 ③ 발송 이력 앵커 = OrderEvent(알림톡 T2 앵커 패턴 재사용), `enqueue_side_effect(effect_type='SHARE_SMS', dedupe_key=f"share_sms:{share_id}:{event_id}")` — event_id 포함으로 재발송(의도적 2회차)은 허용, 더블클릭만 차단.

## 2. Task 목록

### Stage-1 — 도면 공유 (T1~T5, 먼저 스테이징 배포)

**T1 (파일럿). 토큰 모델·마이그레이션·서비스 코어**
- 대상: `models.py`(OrderShareToken 신규), `migrations/versions/share_token_00_*.py`(신규, 현 head 뒤 단일 연결, downgrade 포함), `foms/services/order_share.py`(신규 — create_token/verify_token/revoke_token/record_view), `tests/domains/test_order_share_service.py`(신규)
- 내용: 스펙 §3.1 스키마 그대로(kind·token_hash UNIQUE·snapshot JSONB nullable·expires_at=+`FOMS_SHARE_TOKEN_DAYS`(기본 30)d·now_utc_naive). 토큰 원문 `secrets.token_urlsafe(32)`, 저장은 sha256 해시만.
- 완료 기준: `pytest tests/domains/test_order_share_service.py tests/schema/test_migration_chain*.py -q` PASS(생성/검증/만료/회수/해시 수명주기) + `APP_OK`
- 경계: alembic 실행 금지. estimate snapshot 저장 로직은 T6(컬럼만 선반영).

**T2. 비로그인 열람 라우트 `GET /s/<token>`**
- 대상: `foms/api/share.py`(신규 flat 모듈 — 열람용 별도 Blueprint), `foms/platform/blueprints.py`(등재), `templates/` 열람 페이지(drawing_mobile_v2_gallery.html 재사용 셸), `tests/domains/test_order_share_view.py`(신규)
- 내용: 검증 체인(해시→만료→회수→`Order.active_filter()`+draft 제외, 실패=wam_error.html 410/404). drawing 수집 = `OrderAttachment(category='drawing')` + sd `drawing_current_files`의 `_is_drawing_key(order_id, key)` **allow-list만**(주문 격리). 파일 URL=`get_download_url(key, expires_in=300)`, storage r2/s3 아니면 **fail-closed**. 헤더 `X-Robots-Tag: noindex, nofollow`+`Referrer-Policy: no-referrer`. 열람 기록=view_count·last_viewed_at+access_logs FILE_VIEW(share_id, PII 무). rate limit 보조(fail-open 인지).
- 완료 기준: `pytest tests/domains/test_order_share_view.py -q` PASS — 타 주문 키 격리·draft·만료 410·회수 410·fail-closed·헤더 2종 assert + `APP_OK`
- 경계: estimate 분기는 T7(kind='estimate'면 이 시점엔 404).

**T3. 직원 API create/revoke + manifest·감사**
- 대상: `foms/api/share.py`(같은 모듈 — `POST /api/share/create/<order_id>`·`POST /api/share/revoke/<share_id>`), `docs/harness/foms_write_guard_manifest.json`·`foms_order_mutation_policy_manifest.json`(등재), 감사 라벨(`foms/services/audit_message_display.py` ACTION_LABELS + `log_access` `SHARE_LINK_CREATED`/`SHARE_LINK_REVOKED`), `tests/domains/test_order_share_api.py`(신규)
- 내용: 권한 `role_required(['ADMIN','MANAGER','STAFF'])`. create body kind — Stage-1은 'drawing'만 허용('estimate'는 T6까지 400). 응답에 토큰 원문 1회 노출+공유 URL. 알림톡 T4 커밋(cb58edb6) 등재 패턴 미러.
- 완료 기준: `pytest tests/domains/test_order_share_api.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit_coverage 인벤토리 재생성 커밋 동반 + `APP_OK`
- 경계: send-sms는 T8.

**T4. 공유 UI (PC·모바일 공용 모달)**
- 대상: `templates/orders/partials/erp_share_modal.html`(신규), `static/js/orders/erp-share.js`(신규), `erp_order_tab.html`·`erp_order_tab_mobile.html`·`erp_order_js.html`(버튼·모달 배선), CSS는 기존 `erp-channel-push.css` 계열 추가, `tests/visual/test_share_ui_contract.py`(신규)
- 내용: 알림톡 T5 커밋(baa0fee8) 패턴 미러 — [링크 복사]+[카톡 공유 sendDefault(feed), SDK lazy 로드, 버튼≤2]+최근 발급 링크 목록·revoke 버튼. kind 선택 UI는 도면만 활성(견적서는 T7에서 해금). 수정하는 기존 JS/템플릿은 ?v 범프+핀 전수.
- 완료 기준: 계약 테스트 PASS + `test_erp_order_shared_form_scripts.py` PASS + gstack browse PC·모바일 2뷰포트 스모크(모달 열림·링크 복사) + `APP_OK`
- 경계: 태블릿은 T9. 견적서 옵션 비활성 상태로만.

**T5. Stage-1 통합 검증·스테이징 배포**
- 대상: 코드 신규 없음 — `pre_push_smoke` → deploy push → CI → 스테이징 E2E
- 완료 기준: `scripts/ops/pre_push_smoke.ps1` exit 0 + push 후 `gh run list --branch deploy` **전 워크플로 green** + 스테이징 E2E 기록(링크 생성→시크릿 창 열람→lightbox→revoke 즉시 410→만료는 DB 조작으로 검증). 카톡 실공유는 카카오 도메인 등록(사용자 액션) 후 — 미완이면 BLOCKED 기록 후 전진.
- 경계: production 승격 아님(스테이징까지).

### Stage-2 — 견적서·문자·태블릿 (T6~T10)

**T6. 견적 스냅샷 빌더 (D5 화이트리스트 + D6 동결)**
- 대상: `foms/services/order_share.py`(build_estimate_snapshot 추가), create API kind='estimate' 해금, `tests/domains/test_order_share_estimate.py`(신규)
- 내용: 화이트리스트 렌더 데이터 — 품목·규격·수량·금액·할인액·합계·예약금·잔금(출고가=grand total 규칙 준수)·**해당 브랜드 계좌만**(발주사 판정 재사용)·담당자 이름/연락처·고객센터. 차단 필드(타 브랜드 계좌·factory2·내부 라우팅)는 키 존재 자체가 없어야 함. 64KB 캡(§1) 적용.
- 완료 기준: `pytest tests/domains/test_order_share_estimate.py -q` PASS — 타 브랜드 계좌 문자열 부재 assert·차단 키 부재 assert·주문 수정 후 snapshot 불변 assert·64KB 초과 400 + `APP_OK`

**T7. 견적 열람 렌더**
- 대상: `templates/orders/share_estimate_view.html`(신규 — estimate_pane.html 마크업 발췌, 모바일 우선), `foms/api/share.py` estimate 분기(스냅샷만 렌더, 라이브 재조회 없음), T2 테스트 확장
- 완료 기준: `pytest tests/domains/test_order_share_view.py -q` PASS(estimate 분기 포함) + gstack browse 모바일 뷰포트 렌더 확인 + `APP_OK`

**T8. 문자 발송 (D2 하이브리드 발신)**
- 대상: `models.py`(User.sender_phone nullable)+마이그레이션(신규, downgrade 포함), `/admin/users` 표면 필드 추가, `foms/services/kakao_alimtalk.py`의 `_env`·`_classify_error`·`_mask_phone` 재사용하는 `_solapi_send_text`(LMS, KakaoOption 없음 — 배치는 order_share.py 또는 kakao_alimtalk.py 내 플랜 시점 판단), `POST /api/share/send-sms/<share_id>`+manifest·`SHARE_SMS_SENT` 감사, `tests/domains/test_order_share_sms.py`(신규)
- 내용: 발신=sender_phone 있으면 개인 명의(솔라피 미등록이면 벤더 오류 "발신번호 미등록" 표면화), 없으면 `SOLAPI_SENDER_PHONE` 폴백. 본문=고정 문구+자사 도메인 URL(단축 금지, `[Web 발신]` 전제). 멱등=§1 규칙.
- 완료 기준: `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py -q` PASS(폴백 분기·5초 중복 409·감사 기록) + `APP_OK`. 실발신은 T10.

**T9. 태블릿 실측 폼 공유 버튼 (D4)**
- 대상: `static/js/foms/tablet-measure-form.js`(+~100줄, 알림톡 선례 미러 주석 규약), 관련 ?v 범프+핀 전수
- 완료 기준: 태블릿 계약 테스트 PASS + gstack browse coarse 에뮬 스모크 + `APP_OK`
- 경계: 핫파일(태블릿 계약테스트) — 공유 트리 규칙 확인 후 진행.

**T10. Stage-2 통합 검증·스테이징 E2E**
- 완료 기준: pre_push_smoke exit 0 + push 후 전 워크플로 green + E2E 기록(견적 스냅샷 불변 실검증·문자 3사 실수신 — 개인·회사 폴백 각 1회·카톡 공유 실기기). 발신번호 미등록이면 문자 실수신만 BLOCKED 기록 후 전진.

## 3. 외부 의존 (사용자 액션 — 코드와 병행)

- 카카오 개발자 앱 도메인 2종 등록(+지도 앱과 동일 앱 여부 회신) — T5 카톡 E2E 전제
- 문자 쓰는 영업 인원 Solapi 발신번호 등록 → 번호 목록 전달 — T10 실수신 전제
