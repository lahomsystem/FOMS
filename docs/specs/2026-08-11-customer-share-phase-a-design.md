# 고객 공유 채널 Phase A — 확정 설계 (v3, 사용자 결정 반영 최종)

> 상태: USER-DECIDED — 3-agent 교차검수(v2) 후 사용자 상세 결정 8건 반영. 플랜 작성 대기.
> 사용자 결정(2026-08-11): **풀스코프 v1**(도면+견적서+문자+태블릿, 리뷰 권고안 축소를 전부 기각) + 도면 먼저 단계 배포.

## 1. 목표·범위 (v1 확정)

고객에게 로그인 없는 열람 링크로 도면·견적서 전달. 전달 수단: ① 링크 복사 ② 영업 본인 카톡 공유(sendDefault) ③ 문자(자동 폴백 발신). 표면: PC·모바일·**태블릿 실측 폼 포함**.
**배포는 단계**: Stage-1 도면(빠름, 기존 부품 재사용) 먼저 스테이징→검증, Stage-2 견적서·문자·태블릿 순차 후속. 범위는 전부 v1.

## 2. 사용자 확정 결정

| # | 결정 |
|---|---|
| D1 | v1 = 도면+**견적서 포함** (v1.1 연기안 기각) |
| D2 | 문자 = **회사 대표번호 + 개인 번호(필요 인원만)** 하이브리드. 발신 선택 = **자동 폴백**(본인 번호 등록 시 개인 명의, 미등록 시 `SOLAPI_SENDER_PHONE`) |
| D3 | 토큰 만료 **30일** (env `FOMS_SHARE_TOKEN_DAYS=30`) |
| D4 | **태블릿 실측 폼에도 공유 버튼** (+별도 구현 ~100줄, tablet-measure-form.js 패턴) |
| D5 | 견적 노출: **계좌 = 해당 브랜드 것만**(발주사 판정 재사용, 타 법인 계좌 차단) + **할인액 표시** + **담당자 연락처 표시** + **예약금/잔금 표시**. 내부 공장 정보(factory2 등)·타 브랜드 정보는 차단 — 화이트리스트 렌더 |
| D6 | 견적 기준 = **발송 시점 스냅샷 고정** (링크 생성 시 렌더 데이터 동결 저장, 수정 시 재발급) |
| D7 | 배포 = 도면 먼저 단계 배포 |
| D8 | (v2 계승) sendDefault(feed)·flat 모듈·30일 외 v2 보안 결정 전부 유지 |

## 3. 아키텍처

### 3.1 토큰·스냅샷
- `order_share_tokens`: id, order_id(FK), **kind('drawing'|'estimate')**, token_hash(UNIQUE sha256), created_by_user_id, expires_at(+30d), revoked_at, created_at(now_utc_naive), view_count, last_viewed_at, **snapshot(JSONB, nullable — estimate만 사용, D6)**.
- estimate 링크 생성 시: 화이트리스트 필터 통과한 렌더 데이터를 snapshot에 동결 저장 → 열람은 스냅샷만 렌더(라이브 재조회 없음). drawing은 snapshot 없이 라이브 수집(도면 자체가 전달 확정본).
- 토큰 원문 `secrets.token_urlsafe(32)` — 실질 방어선. models.py+alembic 이름 동일(migration_chain), worktree에서 alembic 실행 금지(파일만).

### 3.2 열람 `GET /s/<token>` (비로그인, flat `foms/api/share.py` 내 별도 Blueprint)
- 검증: 해시→만료→회수→`Order.active_filter()`+draft 제외. 실패 = wam_error.html 재사용(410/404).
- **drawing**: `OrderAttachment(order_id, category='drawing')` + sd `drawing_current_files`는 `_is_drawing_key(order_id, key)` allow-list만 통과(주문 격리 — deny-list 단독 금지). 렌더 = drawing_mobile_v2_gallery.html(25줄)+lightbox.js. 파일 URL = `get_download_url(key, expires_in=300)` presigned, **storage r2/s3 아니면 fail-closed**.
- **estimate**: snapshot 렌더 전용 신규 템플릿(templates/orders/ 배치, estimate_pane.html 마크업 발췌·모바일 우선). 화이트리스트(D5): 품목·규격·수량·금액·할인액·합계·예약금·잔금·해당 브랜드 계좌·담당자 이름/연락처·고객센터. 차단: 타 브랜드 계좌·factory2·내부 라우팅 필드.
- 헤더: `X-Robots-Tag: noindex, nofollow` + `Referrer-Policy: no-referrer`. 열람 기록 = count·last_viewed_at + access_logs FILE_VIEW(share_id, PII 무). rate limit 보조(fail-open 인지).

### 3.3 직원 API (`/api/share/*`)
- `POST create/<order_id>` (body: kind) / `POST revoke/<share_id>` / `POST send-sms/<share_id>`.
- 권한 `role_required(['ADMIN','MANAGER','STAFF'])`. manifest 3종(write_guard·auth-policy·audit) 등재 + `log_access` 3종(`SHARE_LINK_CREATED`/`SHARE_LINK_REVOKED`/`SHARE_SMS_SENT`) + `ACTION_LABELS` 등재.
- **send-sms (D2)**: `User.sender_phone` 컬럼 신설(nullable, 마이그레이션) + 관리자 편집 UI(기존 /admin/users 표면에 필드 추가). 발신 = sender_phone 있으면 그것(솔라피 등록 전제 — 벤더 오류 표면화 "발신번호 미등록"), 없으면 `SOLAPI_SENDER_PHONE` 폴백. 본문 = 고정 문구+공유 URL(자사 도메인 그대로 — **단축 URL 금지**, `[Web 발신]` 강제 표기 전제 문구 설계). LMS 발송 = 신규 `_solapi_send_text`(kakao_alimtalk의 `_env`·`_classify_error`·`_mask_phone` 재사용, KakaoOption 없음). **멱등: OrderEvent 앵커 + `enqueue_side_effect(effect_type='SHARE_SMS', dedupe_key=share_id+uuid아님—더블클릭 방지용 클라 버튼 잠금+서버 5초 중복 억제)** — 정확 규칙은 플랜 단계 확정(반증 HIGH-4).

### 3.4 공유 UI
- 주문 상세 공유 모달(PC·모바일 공용 partial+JS, 알림톡 T5 패턴): [링크 복사] [카톡 공유] [문자 발송] + kind 선택(도면/견적서) + 최근 발급 링크 목록·revoke 버튼(만료·회수 가시성 — bearer 통제).
- 태블릿(D4): tablet-measure-form.js 자체 구현(+~100줄, 알림톡 선례 미러 주석 규약).
- 카톡: `Kakao.Share.sendDefault(feed)` — SDK lazy 로드, 버튼≤2. 기존 JS 수정 시 ?v 범프+핀 전수.

### 3.5 검증
- pytest: 토큰 수명주기·열람 격리(타 주문·draft·삭제·만료·회수·fail-closed)·견적 화이트리스트(타 브랜드 계좌 부재 assert)·스냅샷 동결(주문 수정 후 렌더 불변)·send-sms 폴백/멱등·manifest·감사 라벨·헤더.
- 게이트: write_guard·auth_enforcement·audit_coverage 재생성·namespace(수정 0)·migration_chain.
- 스테이징 E2E(Stage별): 링크 생성→시크릿 창→lightbox→만료 410→revoke 즉시 차단 / 견적 스냅샷 불변 / 문자 3사 실수신(개인·회사 폴백 각 1회) / 카톡 공유 실기기.

## 4. v1 제외 (백로그)
계약서(기능 부재 — "계약서" 정의 확인 필요: OrderEstimate docstring "견적서(계약서)" 혼용) / 결제링크(Phase C — 이니시스 링크페이 계약 확인 대기) / 열람 통계 대시보드 / 고객 본인확인.

## 5. 사용자 준비 액션
1. 카카오 개발자 앱: 도메인 2종 등록([JS SDK 도메인]+[제품 링크 관리]) + 지도 앱과 동일 앱 여부 회신 (쿼터 일 30,000건 공유 — 실사용 무해)
2. 문자 쓰는 영업 인원: Solapi 발신번호 등록(본인인증+재직증명서) → 등록 번호 목록 전달 (관리자 UI에 입력)

## 6. 잔여 리스크
- bearer 링크 30일(사용자 선택 — 통제: revoke UI 가시성+256bit+noindex/no-referrer). 
- 견적 스냅샷 JSONB 크기(품목 다수) — 64KB 캡 검토(플랜 단계).
- send-sms 멱등 정확 규칙 플랜 단계 확정.
- law.go.kr 안전조치 기준 원문 재확인 항목 유지.
