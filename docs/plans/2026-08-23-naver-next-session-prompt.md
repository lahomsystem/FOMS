# 다음 세션 프롬프트 (네이버 워크벤치 — 관계 축·취소 이후)

아래 블록을 새 세션 첫 프롬프트로 그대로 붙여넣으면 된다.

---

**C 네이버 워크벤치 — 취소 실호출 확인 + 운영 승격.
작업 위치 `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`).

원장 `docs/plans/2026-08-20-naver-workbench-ledger.md` 의 맨 아래
"### 리뷰 지적 처리 (2026-08-23)" 절부터 읽어라. 스펙은
`docs/specs/2026-08-22-naver-workbench-relation-and-cancel_SPEC.md`(관계 축 + 판매자 직접취소).

## 지금 상태
- 관계 축(추가결제·재결제 배지 / 후보·붙이기·되돌리기 / 발송처리 관계별 분기)과
  **판매자 직접취소**까지 deploy 승격 완료. 커밋 5개: 관계 축 · 취소 · failopen 인벤토리 ·
  place 탭 배지 · 3관점 리뷰 수정.
- 검증 완료: `tests/services/integrations` 466 pass · PG 레인 737 pass · APP_OK ·
  `scripts/ops/pre_push_smoke.ps1` exit 0 · 1440 실브라우저 2회.
- 스테이징 게이트는 그대로 **upperkill 단독**(`FOMS_NAVER_WORKBENCH_COHORT=38`).
  railway 링크 디렉토리는 `/c/tmp/foms-devlink`(Project FOMS-DEV, Service FOMS) —
  저장소 디렉토리는 FOMS-PRODUCTION 에 링크돼 있으니 거기서 railway 명령 쓰지 마라.

## 확정된 업무 규칙 (다시 묻지 마라)
- 발송처리 단독 호출은 **ADDON/REPAY 집에만** 연다(D1). NEW 는 발주확인이 먼저 +
  "실제 출고·시공 시점" 경고(D2).
- 관계 판정은 **집 단위**이고 `close_now` 는 **all**(섞인 집은 발주확인 먼저).
- 취소는 **판매자 직접취소만**(구매자 취소요청 승인은 범위 밖 — 필요해지면 새 스펙).
- 취소한 집은 발주확인·발송처리·주문 만들기를 전부 닫는다(`_cancel_guard`).

## 할 일
1. **취소 실호출 1건** — 사유 코드가 맞는지는 실호출로만 확인된다. 사용자가 취소해도 되는
   실주문 1건을 고르면, 워크벤치에서 취소처리를 보내고 결과(성공/실패 사유)를 확인한다.
   실패하면 `cancelReason` 코드부터 의심하라(문서 2.86.0 기준 7코드).
   apicenter 문서는 클라이언트 렌더라 HTML 만 받으면 비어 있다 — 청크 추출법은 원장
   "진행 기록 (2026-08-22~23)" 에 적어 뒀다.
2. 스테이징 실데이터로 관계 축 눈 확인(ADDON 2건 · NEW 214건): 배지·붙이기·되돌리기·
   '지금 닫기'·취소 모달.
3. 이상 없으면 **운영 승격** — origin/deploy 기반 임시 워크트리에 cherry-pick 하고 거기서
   alembic 단일 head·인벤토리 3종을 다시 확인한 뒤 push(`tools/harness/promote_own_to_production.py`).
   production push 는 사용자 명시 요청 시에만.

## 알아둘 함정
- 로컬 PG 레인 클러스터는 `/c/tmp/pglane5441`(포트 5441, PG17 trust). 기존 5440 은 깨져 있다.
  `FOMS_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5441/postgres`.
- `*_scan.py --check` 는 드리프트 비교가 아니다(카운트만 찍고 0 반환). 게이트 정본은
  `tests/domains/test_*_inventory.py` — pre_push_smoke 가 잡는다.
- 기존 JS/CSS 를 고치면 `templates/admin/naver_workbench.html` 의 `?v=` 핀을 범프해라
  (현재 `20260823a`). 이 화면엔 핀 계약 테스트가 없다 — 잊으면 아무도 안 잡는다.
- 새 mutation 라우트는 manifest 2종 + 감사 라벨 + audit coverage 재생성까지가 한 세트.
- 1440 QA 는 격리 DB 로: `/c/tmp/pglane5441` 의 `wbqa` DB + 시드 스크립트
  (`scratchpad/seed_wb_qa.py` 패턴), 계정 `qa_wb` / `qa1234!`.

## 남은 개선 후보 (미착수, 급하지 않음)
- 취소·반품 탭에서 구매자 취소요청 **승인/거부**(`claim/cancel/approve`) — 별도 스펙 필요.
- `cancel_order`·`dispatch_order` 가 50줄 규칙을 넘었다(82·80줄) — 가드 추출 리팩터.
- 워크벤치 화면 자산 `?v` 핀 계약 테스트 부재.

진행 상황은 나한테 매우 상세히 물어봐.**
