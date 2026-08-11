# 카카오 알림톡 v1 — Progress Ledger

> 플랜: `docs/plans/2026-07-29-kakao-alimtalk-v1-plan.md` / 스펙: `docs/specs/2026-07-29-kakao-alimtalk-v1-design.md`
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 검증 명령 exit 0 + 커밋 SHA 기록 후 DONE. compaction 후 재개 시 이 파일이 정본.

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T0 | 선결 확인 (sidefx worker·solapi 의존) | `SOLAPI_OK` + T0.decision 기록 | DONE | 0e373534 | T0.decision: **WORKER_OFF** (2026-08-11 railway status — 서비스 web·WORKER·FOMS-cron·Postgres·Redis뿐, sidefx 미가동 → 동기 폴백 경로). SOLAPI_OK 확인. 키는 로컬 .env(gitignore) 저장 |
| T1 | 변수 빌더·자격 판정 | `pytest tests/domains/test_kakao_alimtalk_service.py -q` PASS + APP_OK | DONE | 1e84ce58 | 24 passed 오케스트레이터 재검증. 멱등키=`alimtalk:measure:` 포맷으로 스펙 정정. 전화=첫 유효 토큰. 길이 가드 2단(축약+절단) |
| T2 | Solapi 발송·이력 기록 | `pytest tests/domains/test_kakao_alimtalk_send.py -q` PASS + APP_OK | DONE | 9f9f5c86 | 47 passed+회귀 208 재검증. WORKER_OFF 동기 경로, D3 브랜드 분기, 앵커 이벤트 승격 패턴, 슬롯 미소진 스킵(원인 해소 후 자동 재개) |
| T3 | 자동 트리거 3경로 배선 | `pytest tests/domains/test_kakao_alimtalk_trigger.py tests/domains/test_erp_orders_structured*.py -q` PASS | DONE | 377934fa | 배선 3곳(PUT :1159·PATCH :849·field_update :597 measurement_date 가드)+MEASUREMENT_TIME_CHANGED 이벤트. 재검증 74 passed. red 확인 완료 |
| T4 | 수동 API + manifest 등재 | `pytest tests/domains/test_kakao_alimtalk_api.py tests/domains/test_write_guard.py -q` PASS | DONE | e50e4366 | 45 passed 재검증. preview GET+send-manual POST, manifest 2종 등재, body 전면 무시. 후속 후보: _ineligible_reason public 승격 |
| T5 | UI 3표면 | 계약 테스트 PASS + gstack browse 3뷰포트 스모크 | DONE | (T5 커밋) | 117 passed 재검증(게이트 포함). 태블릿=자체 흐름(선례 준수), 상태 한 줄+모달. browse 스모크는 T6에 통합 실행 예정 |
| T6 | 통합 검증·스테이징 | pre_push_smoke exit 0 + CI green + E2E 기록 | PENDING | | env 등록은 Solapi 키 발급 후 |

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
