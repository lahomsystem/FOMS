# 고객 공유 채널 Phase A — 확정 설계 (v2)

> 상태: REVIEWED — 3-agent 교차검수(반증 HIGH4·MED6·LOW3 / 단순화 / 사실검증 5항목) 전량 반영. CEO 리뷰·사용자 승인 대기.
> v1 대비: **범위 = 도면 공유만**(견적서 v1.1로 연기), 문자 발송 삭제, flat 모듈, sendDefault, 보안 3건 보강.

## 1. 목표 (v1)

영업·CS가 고객에게 **도면을 로그인 없이 열람 가능한 링크**로 전달. 전달 = ① 링크 복사(채널톡 상담창 포함 어디든) ② 영업 본인 카톡 공유(Kakao.Share sendDefault — 개인 명의).

## 2. 리뷰 반영 핵심 결정

| # | 결정 | 근거 |
|---|---|---|
| R1 | **견적서 열람 = v1.1 연기** | 도면=기존 부품 3종 재사용(미사용 갤러리 partial 25줄·lightbox.js·`_collect_preview_items`)으로 거의 공짜 vs 견적서=estimate-preview.js 1,475줄 IIFE hoist 리팩터+가격 화이트리스트 정책 미결. 채널톡 push-estimate는 내부 그룹용이라 중복 아님 — 연기지 폐기 아님 |
| R2 | **문자(send-sms) 삭제** | `User.phone` 컬럼 부재(models.py:929-967 확인) — 마이그레이션+관리UI+전원 발신번호 온보딩(재직증명) 전부 유발. 카톡 공유·링크 복사도 동일하게 개인 경로라 문자만 추적하는 일관성 없음. 필요 시 ~10줄로 후일 추가 |
| R3 | **flat 모듈** — `foms/api/share.py`(Blueprint 2개: 비로그인 `/s` + 직원 `/api/share`), 템플릿은 `templates/orders/` | 닫힌집합 게이트 3종(namespace_surface_tests :2229·:2247·:2263)이 디렉토리만 열거 — flat이면 계약 테스트 수정 0 (선례 foms/api/address.py) |
| R4 | **sendCustom → sendDefault(feed)** | 콘솔 템플릿 제작·template_id env·드리프트 제거. 도메인 등록 요건은 동일(사실검증 확인). 버튼 최대 2개. 문구 수정=배포 트레이드오프 수용 |
| R5 | `kind` 컬럼 제거 (v1 도면 전용, v1.1에서 추가) | 단순화 |

## 3. 아키텍처

### 3.1 토큰 (신규 테이블 — 무상태 서명으로 대체 불가: revoke·열람 카운트 요건)
`order_share_tokens`: id, order_id(FK), token_hash(UNIQUE, sha256 — 원문 미저장), created_by_user_id, expires_at(기본 14일, env `FOMS_SHARE_TOKEN_DAYS`), revoked_at, created_at(now_utc_naive), view_count, last_viewed_at. 토큰 원문 = `secrets.token_urlsafe(32)`(256bit — **실질 방어선**). models.py + alembic 마이그레이션 이름 동일(migration_chain 게이트), **worktree에서 alembic 실행 금지 — 파일만**.

### 3.2 열람 `GET /s/<token>` (비로그인)
- 검증: 해시 대조→만료→회수. 실패 = 기존 `templates/channel/wam_error.html` 재사용(존재 계약 테스트 있음), 410/404.
- **도면 수집 = DB 행 스코프 우선**: `OrderAttachment(order_id, category='drawing')` + sd `drawing_current_files`는 **`_is_drawing_key(order_id, key)` allow-list**(drawing_transfer.py:83 — order_id 포함 프리픽스)로만 통과. deny-list(`/attachments/`) 단독 사용 금지 — **주문 격리 안 됨(반증 HIGH-3)**. 렌더 = `drawing_mobile_v2_gallery.html`(25줄 미사용 부품) + `lightbox.js`.
- 파일 URL = `storage.get_download_url(key, expires_in=300)` (presigned, WAM 선례 channel_wam_attachments.py:178). **fail-closed: storage_type이 r2/s3 아니면 파일 링크 발급 거부**(로컬 `/static/uploads` 무서명 폴백 차단 — storage.py:392).
- 응답 헤더: `X-Robots-Tag: noindex, nofollow` + `Referrer-Policy: no-referrer`(토큰 Referer 유출 차단). 외부 리소스 로드 최소화.
- 열람 기록: view_count·last_viewed_at UPDATE + `access_logs` `FILE_VIEW`(share_id 기준, 고객 PII 없음 — AUDIT-LOG T6 취지, 반증 MED-1). rate limit은 **보조**(fail-open 규약 인지 — Redis 다운 시 토큰 엔트로피가 방어).
- 주문 상태 필터: `Order.active_filter()` + draft 제외 (반증 MED-2 계열 — 삭제·draft 주문 링크 차단).

### 3.3 직원 API (`/api/share`, 같은 flat 모듈)
- `POST /api/share/create/<order_id>` — 토큰 발급, URL 반환. `role_required(['ADMIN','MANAGER','STAFF'])`. 감사 `log_access(SHARE_LINK_CREATED)` + `ACTION_LABELS` 등재(하드 계약 — test_admin_audit_screen_readability_3).
- `POST /api/share/revoke/<share_id>` — 회수. `SHARE_LINK_REVOKED` + 라벨.
- manifest: write_guard 2행 + auth-policy(POLICY_REGISTRY 신규 policy_id 또는 STAFF_MUTATION 선례 — 구현 시 test_auth_enforcement.py:125 규약 확인) + audit coverage 재생성. `GET /s/`는 3종 게이트 전부 범위 밖(실측 확인).

### 3.4 공유 UI
- 주문 상세 공유 모달: [링크 복사] [카톡 공유] 2버튼. 알림톡 T5 패턴 — 단 실측 반영: PC·모바일 = 공용 partial+JS, **태블릿은 tablet-measure-form.js 별도 구현(+~100줄) — v1은 PC·모바일만, 태블릿은 사용자 확인 후**(그 표면이 실측 폼이라 공유 버튼 필요성 불명 — 반증 MED-4).
- 카톡 공유: `Kakao.Share.sendDefault({objectType:'feed', content:{title,description,imageUrl,link}, buttons:[≤2]})` — SDK lazy 로드(모달 열 때), 기존 지도 lazy 패턴. **앱 키: 지도 앱과 동일 앱인지 확인 필요(§5) — 같으면 쿼터 공유(일 30,000건, 실사용 대비 무해)**.
- 기존 파일 수정 시 `?v=` 범프 + 핀 전수 규약.

### 3.5 검증
- pytest: 토큰 수명주기·열람(비로그인·만료 410·회수·타 주문 파일 격리·draft/삭제 주문 차단·fail-closed 스토리지)·create/revoke(권한·manifest·감사)·헤더 2종.
- 게이트: write_guard·auth_enforcement·audit_coverage(재생성)·namespace(수정 0 확인)·migration_chain.
- 스테이징 E2E: 링크 생성→시크릿 창 열람→lightbox→만료 조작 410→revoke 즉시 차단, 카톡 공유 실기기 1회.

## 4. v1 제외 (백로그)
견적서 열람(v1.1 — estimate_pane 816줄 재사용 리팩터+가격 화이트리스트 정책 결정 선행) / 문자 발송(~10줄, 발신번호 온보딩 후) / 태블릿 표면 / 계약서(기능 자체 부재 — "계약서" 정의 확인 필요: OrderEstimate docstring이 "견적서(계약서)"로 표기, 반증 MED-3) / 결제링크(Phase C — 이니시스 확인 대기) / 열람 통계 대시보드 / 고객 본인확인.

## 5. 사용자 준비 액션 (1건로 축소)
1. **카카오 개발자 앱**: FOMS 스테이징·운영 도메인을 [JavaScript SDK 도메인] + [제품 링크 관리 > 웹 도메인]에 등록, [카카오링크/메시지] 기능 활성. **지도용 앱(JS 키 geocode_config)과 같은 앱인지 회신** — 다르면 Share용 앱 키 별도 전달.

## 6. 잔여 리스크
- bearer-link 성격(2026-03 채널톡 플랜 :400에서 기제기) — 통제 = 14일 만료+revoke UI 가시성+256bit. 만료 기간은 사용자 조정 가능.
- 견적서 라이브 vs `OrderEstimate` 스냅샷 논점(반증 MED-3)은 v1.1 결정 사항으로 이월.
- law.go.kr 안전조치 기준 §6③ 원문은 교차 일치 확보(직접 fetch 실패) — 인용 시 재확인.
