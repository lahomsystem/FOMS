# 고객 공유 채널 Phase A — Progress Ledger

> 플랜: `docs/plans/2026-08-11-customer-share-phase-a-plan.md` / 스펙: `docs/specs/2026-08-11-customer-share-phase-a-design.md` (v3)
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 검증 명령 exit 0 + 커밋 SHA 기록 후 DONE. compaction 후 재개 시 이 파일이 정본.
> 작업 트리: `c:/tmp/foms-alimtalk-reapply` (브랜치 `alimtalk-reapply`)

## Stage-1 — 도면 공유

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T1 | 토큰 모델·마이그레이션·서비스 코어 (파일럿) | `pytest tests/domains/test_order_share_service.py tests/domains/test_alembic_single_head.py -q` PASS + APP_OK | DONE | 073b89b3 | 14 passed. head=seclog_time_00 뒤 단일 연결. 지문 정합 위해 양쪽 server_default 無, snapshot=JSON+JSONB variant |
| T2 | 비로그인 열람 `GET /s/<token>` (drawing) | `pytest tests/domains/test_order_share_view.py -q` PASS(격리·410·fail-closed 503 표면·헤더·FILE_VIEW 1행) + APP_OK | DONE | 84319e30 | 12 passed + namespace 게이트 358 passed. presign 전멸=503, onerror 새로고침 안내 |
| T3 | 직원 API create/revoke + manifest·감사 | `pytest tests/domains/test_order_share_api.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | DONE | 93b0e142 | 49 passed + audit 게이트 11 passed(coverage 100%). 감사에 토큰·URL 미격납 assert |
| T4 | 공유 UI 모달 (PC·모바일) + list API | 계약 테스트 PASS + browse 2뷰포트 스모크(모달·복사·목록) + APP_OK | DONE | bef517a5 | 110 passed(계약+게이트). browse 스모크는 T5 통합 실행(알림톡 T5 선례). 카톡 키=지도 앱 키 fallback+env 오버라이드 |
| T5 | Stage-1 통합 검증·스테이징 배포 | pre_push_smoke exit 0 + `gh run list` 전 워크플로 green + E2E 기록 | DONE | 1f7999e4 | smoke 0·CI 4/4 green(Harness/PG Lane/perf-gate/FOMS). E2E 13항목 PASS: 로그인→발급→시크릿 열람 200+헤더 2종→열람수 반영→revoke 410→불량토큰 404→estimate 400. 주문 4287 카드·presigned·lightbox 렌더 확인. **주의**: 스테이징 이미지 실바이트는 전 키 NoSuchKey — 스테이징 DB(운영 복제)↔R2 버킷 드리프트(환경 이슈, presign 서명·경로 정상, onerror 안내 표면화). 실객체 검증=T10 업로드 흐름 동반. 카톡 실공유=**BLOCKED**(카카오 도메인 등록 사용자 액션 대기) |

## Stage-2 — 견적서·문자·태블릿

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T6 | 견적 스냅샷 빌더 (화이트리스트+동결+64KB 캡) | `pytest tests/domains/test_order_share_estimate.py -q` PASS(타 브랜드 계좌 부재·불변·400) + APP_OK | DONE | c871807e | 8+14 passed. 브랜드 교차 계좌 유출 0·내부 키 차단·grand total 공식·동결·캡 400 전부 assert |
| T7 | 견적 열람 렌더 + kind UI 해금 | view 테스트 PASS + browse 모바일 렌더(옵션 해금·64KB 400 표시) + APP_OK | DONE | db6f23af | 27 passed. 스냅샷-온리 렌더(수정 미반영 assert)·스냅샷 부재 503·카톡 문구 kind 분기·?v 20260812a 범프+핀 전수. browse는 T10 통합 |
| T8 | 문자 발송 (sender_phone·_solapi_send_text·멱등·버튼 배선) | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | DONE | 6fd32f3c | 64 passed(게이트 포함)·coverage 100%. 선점 insert 멱등=벤더 호출 1회 assert, 감사=수신번호 마스킹·토큰 미격납, 발신 폴백 2분기, senderphone_00 마이그레이션 |
| T9 | 태블릿 공유 버튼 (tablet-measure-form.js) | 태블릿 계약 테스트 PASS + browse coarse 스모크 + APP_OK | DONE | cb9feef1 | 117 passed. 발급→URL 복사→(선택) 문자 confirm 흐름, ?v 20260812a 범프. browse coarse는 T10 통합 |
| T8.1 | 발신번호 3단 우선순위(담당자→브랜드 대표→구 폴백)+②실패 시 브랜드 백업 1회 재시도 | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py tests/domains/test_audit_action_coverage.py tests/domains/test_audit_coverage_inventory.py -q` PASS + APP_OK + CI 전 워크플로 green | DONE | ad6dd47e | 17+63 passed. 구 규칙(버튼 누른 직원) 폐기, resolve_brand SSOT 재사용, 멱등 앵커 1개 유지·payload attempts 2회 기록(마스킹), 감사 sender_source 기록 |
| T10 | Stage-2 통합 검증·스테이징 E2E | pre_push_smoke exit 0 + CI green + E2E(스냅샷 불변·문자 3사·카톡 실기기) | DONE | 59e12874 | smoke 0·CI 4/4 green. E2E 12항목 PASS(주문 4389): 견적 발급→비로그인 열람(계좌·출고가·잔금 렌더·헤더 2종·내부 키 부재)→revoke 410, send-sms 503 not_configured 표면(스테이징 Solapi env 無 — 정상 fail-visible)·토큰 불일치 400. 스냅샷 동결은 pytest 5건이 정본 검증. **BLOCKED 2건**: 문자 3사 실수신(Solapi 발신번호 등록 대기)·도면 이미지 실객체(스테이징 R2 드리프트, T5 참조). 카톡: 도메인 등록 후 스테이징 검증 PASS(2026-08-13 — 버튼 활성·SDK init 성공·콘솔 에러 0·SDK 200, 주문 4389 발급→회수 정리), 실기기 전송만 사용자 확인 잔여 |

## 외부 준비 (사용자 액션)

### 문자 발신번호 확정 (사용자 결정 2026-08-12 — T8.1 발신 규칙의 정본)
- 발신 우선순위: ① 주문 담당자의 등록 개인번호(`users.sender_phone`, 담당자 기준 — 발송 버튼 누른 사람 아님) ② 브랜드 대표번호 ③ ② 벤더 실패 시 브랜드별 백업번호로 같은 요청 내 1회 재시도
- 하우드: 대표 `15660703` / 백업 `01044644260` → env `SOLAPI_SENDER_PHONE_HAUD` / `SOLAPI_SENDER_FALLBACK_HAUD`
- 라홈: 대표 `15660792` / 백업 `01083277282` → env `SOLAPI_SENDER_PHONE_LAHOM` / `SOLAPI_SENDER_FALLBACK_LAHOM`
- 영업 개인번호는 각자 Solapi 등록 후 /admin/users "문자 발신번호"에 입력. 위 4개 번호도 전부 Solapi 발신번호 등록 필요(법인 서류). 구 `SOLAPI_SENDER_PHONE`은 최후 폴백으로 유지.
- [x] Railway env 등록 완료 (2026-08-12, `--skip-deploys` — 다음 배포 때 적용): 스테이징=FOMS-DEV/서비스 `FOMS`, 운영=FOMS-PRODUCTION/서비스 `web`, 각 6종(발신 4 + 회전된 `SOLAPI_API_KEY`/`SECRET`). 로컬 .env도 새 키로 갱신됨. env 잔여 없음 — 실발송 검증 잔여는 Solapi 발신번호 등록(대표2·백업2·개인)과 카카오 도메인 등록뿐.
- [x] 카카오 개발자 앱 도메인 등록 완료 (2026-08-12 사용자) — 카톡 공유 검증 가능
- [x] Solapi 발신번호 등록 (2026-08-13 사용자 확인): 대표 2(`15660703`·`15660792`)·백업 2(`01044644260`·`01083277282`) **전부 활성** (라홈 백업은 반려 후 당일 재승인).
- [x] **문자 실발송 검증 완료** (2026-08-13): 1차 시도는 Solapi API 키 IP 허용 목록이 스테이징 IP(208.77.246.107) 403 차단 — 이때 `brand → brand_fallback` 재시도 로그로 T8.1 ③ 배선 실전 작동 실증. 사용자가 IP 제한 해제(모든 IP 허용) 후 재시도: **2통 발송 성공** — 주문 4404(발주사 無 → HAUD `sent:true, sender_source:brand`)·주문 4405(발주사 라홈 → LAHOM 분기 `sent:true`), 수신 010-8327-7282. 잔여물 정리 완료(share 20~22 회수·주문 4403~4405 soft delete). **수신 확인 완료(2026-08-13 사용자)**: 2통 수신 + 발신번호 1566-0703·1566-0792 육안 일치 — 브랜드 분기 종단 검증 종결. **잔여**: Solapi IP 허용 목록 원복(현재 모든 IP 허용 — 운영 static IP 3개 등록으로 재잠금 권장, 사용자).
- [x] 실측 예약 알림톡 템플릿 2건 **APPROVED** (2026-08-13 카카오 검수 승인 — 라홈 `KA01TP260811082027608jiKgfLV0q0O`·하우드 `KA01TP260811075557060ljaBmPYcckr`). 알림톡 v1 가동 잔여 = PF/템플릿 env 등록 + `FOMS_ALIMTALK_AUTO_ENABLED` 결정.
- [~] **공유 링크 알림톡 템플릿 2건 심사 제출** (2026-08-13 Solapi API로 등록·INSPECTING — 라홈 `KA01TP260813084939252sAF8ck1asOu`·하우드 `KA01TP260813084949809PEw5FMEvNmR`, 카테고리 005003 계약/견적): 변수 고객명·문서종류·유효기간·담당자·담당자연락처·토큰, WL 버튼 `https://lahom-production.up.railway.app/s/#{토큰}` + 상담톡 BC. 채널별 고정 인사말(라홈/하우드입니다)로 브랜드 분기(코드는 resolve_brand로 채널 선택). **승인 후 잔여**: 공유 모달 알림톡 발송 배선 — 반나절. **폴백 규칙(사용자 결정 2026-08-13)**: 알림톡 발송 실패 시 SMS 폴백은 기존 send-sms 경로(T8.1 발신 3단 — ①담당자 sender_phone → ②브랜드 대표 → ③백업) 재사용 = 담당자 지정 시 담당자 번호 발신. 영업 개인번호 Solapi 등록 전까지는 ①이 항상 스킵돼 브랜드 대표로 나감(등록 즉시 자동 전환, 코드 무변경). 템플릿 변수 담당자/연락처 폴백 = "고객센터"/브랜드 대표번호.
- [x] 공유 열람 고객 다운로드 (2026-08-13, `120ce5ca`): 도면 전 파일 attachment presign '내려받기' 섹션(한글 파일명 RFC 5987) + 견적서(계약서) 저장·인쇄(PDF) 버튼. 테스트 16 passed. **운영 승격 완료** — PR #91 머지, production `cee28d4e` (perf-gate·pg-lane pass).
- [x] 공유 링크 알림톡 템플릿 2건 **APPROVED** (2026-08-18 감시 포착 — 심사 5일). 감시 종료.
- [x] **T11 공유 알림톡 발송 배선** (2026-08-18, `28ebc429`): `POST /api/share/send-alimtalk/<id>` — 브랜드별 PF/템플릿 env(`SOLAPI_PF_ID_*`·`SOLAPI_TEMPLATE_SHARE_ID_*`, 스테이징·운영·로컬 .env 등록 완료 `--skip-deploys`)·발신 T8.1 3단(알림톡 실패 시 Solapi failover 가 그 번호로 SMS 대체발송 = 담당자 번호 요구 충족)·변수 6종(담당자 폴백 고객센터/브랜드 대표)·선점 멱등 `share_alimtalk` 버킷·감사 SHARE_ALIMTALK_SENT·manifest 2종·audit 인벤토리 184 재생성·모달 알림톡 버튼(erp-share.js ?v=20260818a). 테스트 10+17+63 passed. **스테이징 검증 완료(2026-08-19)**: Railway 장애(빌드 3연속 실패) 회복 후 감시 포착 → 주문 4471·share 24 로 알림톡 버튼 실발송 — 감사 `sent:true, error:null, sender_source:brand`(HAUD 채널), 수신 010-8327-7282. 잔여물 정리 완료(회수·soft delete·로그아웃). 실수신·문자 대체발송 육안 확인 = 사용자. 운영 승격 대기(T11 커밋 + env는 운영 등록 완료 — 다음 승격 배포 시 적용). **실수신 확인 완료(08-19 사용자)**.
- [x] **T12 알림톡 통합 드롭다운** (2026-08-19): '알림톡' 버튼 하나로 예약 내역(실측 미리보기 모달 재사용)·도면·계약서(견적서) 3항목 — 도면/계약서는 confirm 후 자동 발급+발송(기존 API 연쇄, 신규 라우트 없음). PC·모바일 2표면, erp-share.js ?v=20260819b. UI 계약 76 passed·smoke 0. **스테이징 검증 완료**: 주문 4475 드롭다운 3항목 렌더 + 도면 원클릭 발송 — Solapi 벤더 로그 `COMPLETE·수신 완료`, to=01083277287(사용자 지정), 하우드 채널·변수 정상. 잔여물 정리(share 25 회수·주문 soft delete·로그아웃). 잔여=**운영 승격**(T11+T12 커밋). **주의: 템플릿 WL 버튼이 운영 도메인 고정** — 스테이징 발송 시 버튼 링크는 운영 /s/로 가서 404(스테이징 검증 한계, 발송 성공 여부만 확인).

## production 승격 (2026-08-13 — 완료, PR #89 → production `a59c0d7d`)

- 1차 선행 점검 중단: production 에 `itemuid_00` 부재(체인 `share_token_00→itemuid_00→senderphone_00` 단절) → **사용자 승인 ①** itemuid 포함. 2차 promote_completeness INCOMPLETE: share.py 가 `kakao_alimtalk.py` 하드 의존(production 에 파일 부재) → **사용자 승인 ②** 알림톡 v1 코드 포함(발송은 이중 잠금 — killswitch off·PF/템플릿 env 미설정, 수동 버튼만 노출).
- 세트 21커밋 = 알림톡 v1 8(인벤토리 전용 95c982aa 는 재생성 대체) + 고객 공유 10(T1~T9·T8.1, docs-only T5·merge T10 제외) + itemuid 2 + 정리 2(인벤토리 4종 재생성·`erp-order-shared.js` ?v=20260813d 범프·share_token_00 재부모화 deploy 정본 동기화 — bc810a9a 병합 해결분은 cherry-pick 불가라 파일 동기화).
- 충돌 해소: erp_order_js.html ?v 드리프트(기계적 병합)·models.py OrderFieldChange/OrderShareToken 병치·ledger=승격분·AI_STATUS=production 유지·인벤토리 JSON=재생성. 검증: 단일 head·APP_OK·도메인 82 passed·pre_push_smoke 322 passed·PR 체크 perf-gate/pg-lane pass.
## 결정 기록
- 플랜 확정 3건(CEO 2-agent 리뷰 반영): 스냅샷 64KB 캡=초과 시 400(절단 금지) / send-sms 멱등=**발송 전 앵커 선점 insert**+시간버킷 dedupe_key(`share_sms:{share_id}:{floor(epoch/5)}`) — DB UNIQUE로 동시 중복 차단, 감사 조회식 check-then-act 폐기 / send-sms URL=body 토큰 원문 재해시 검증 후 서버 조립(해시-온리 저장과 충돌 해소, 문자 발송은 발급 직후만)
- CEO 2-agent 리뷰(2026-08-11): HIGH 3건(T1 가짜 테스트 경로·URL 재구성 충돌·멱등 레이스)+MED 6건 플랜 반영 완료, 수용 리스크는 플랜 §4 기록
- 스펙 v3 사용자 결정 D1~D8 준수(풀스코프 v1, 도면 먼저 단계 배포)
