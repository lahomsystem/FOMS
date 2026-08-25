# 다음 세션 프롬프트 (2026-08-24 이후) — 네이버 워크벤치 v3 잔여

아래 블록을 그대로 새 세션 프롬프트로 붙여 넣으면 된다.

---

**C 네이버 워크벤치 v3 잔여 — 스테이징 눈 확인 + 남은 리뷰 지적 + 승격 판단.
작업 위치 c:\tmp\foms-s-naver-ingest (브랜치 session/naver-ingest, HEAD 04410805)

원장 `docs/plans/2026-08-23-naver-workbench-v3-ledger.md` 의 맨 아래 세 절부터 읽어라:
"V-8 통합 리뷰 — 품질 렌즈" · "V-8 통합 리뷰 — 불가역 위험 렌즈" · "미처리 지적 후속 처리".
계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§0 절대 규칙 6개가 판정 기준)

## 지금 상태

- v3 deploy 완료. `93fd4a99`(본체, CI 4/4 green) → `a7d82df8`(후속 정리).
  **a7d82df8 의 FOMS CI 가 마지막 확인 시점에 진행 중이었다 — 이것부터 확인해라.**
  나머지 3개(Harness·PG Lane·perf-gate)는 green.
- 한 일: 탭 4→2 + 필터 칩, 상세에 발주확인 단건 버튼, pane 프래그먼트로 부분 갱신
  (`GET /admin/naver-ingest/triage/pane?link_id=N`), `확인 완료` 전 집 복원,
  nav 이름·진입구 4→1 + 뱃지 모집단 일치, 취소·반품 집은 목록에 잠긴 행으로 남긴다.
  셸 973→475줄 + pane 파셜 478줄 신설.
- 검증 끝: 524 passed · APP_OK · pre_push_smoke exit 0 · 실브라우저 18항목 중 17 PASS
  (나머지 1건은 전역 nav popstate 결함, 수정 후 재확인). 네이버 실호출 0건.
- 스테이징 게이트는 여전히 **upperkill 단독**(`FOMS_NAVER_WORKBENCH_COHORT=38`).
  railway 링크 디렉토리는 `/c/tmp/foms-devlink`(FOMS-DEV). **저장소 디렉토리는
  FOMS-PRODUCTION 링크라 거기서 railway 명령 쓰지 마라.**

## 확정 규칙 (다시 묻지 마라)

- 상세는 항상 한 집만. 여러 집 동시 펼침 금지(액션·모달 id 가 문서에 하나 전제).
- 모달 재진술 건수 == 서버가 처리할 건수. pane 은 `_group_of_link`, 벌크는 `household_count`.
- 이력 탭 행에 액션·`data-link-id` 금지. STAFF 응답에 이력 데이터·"전체 이력" 0.
- 벌크 대상 ⊆ 화면 목록. `전부 선택`은 보이는 행만.
- 잠금·선택 판정 SSOT 는 서버 `_attach_row_flags`(= `_group_matches_filter`). 화면은 읽기만.
- `_place_groups` 는 `sync_status IN ('COLLECTED','LINKED')` 만 본다. 발주확인은
  서비스 층 `_broken_collection_guard` 가 한 번 더 막는다.
- 게이트 OFF 경로(`templates/admin/naver_triage.html`)는 손대지 않는다 — 롤백 경로다.
  그래서 `naver_ingest_fulfillment` 라우트에 게이트를 걸지 않는다(리뷰 M-7 기각 근거).

## 할 일

1. **CI 확인이 먼저다**: `gh run list --branch deploy --limit 12` 에서 `a7d82df8` 의 4개
   (FOMS CI · Harness CI · PG Lane · perf-gate) 전부 green 인지. red 면 근본 수정 →
   pre_push_smoke → 재푸시.
2. **스테이징 실데이터 눈 확인** — v3 는 아직 스테이징에서 눈으로 못 봤다(로컬 시드로만 QA).
   코호트를 잠시 `38,58` 로 넓혀 `claude_master` 로 보고 **끝나면 반드시 `38` 로 원복**해라
   (지난 세션에 같은 방식으로 했다). 볼 것: 칩 4종 숫자 == 목록 줄수, 행 클릭 시 문서 요청 0,
   뒤로가기가 전체 리로드가 아닌지, 안내 문구 3종 스타일, 잠긴 행 표시, 벌크 재진술 숫자.
   **불가역 버튼(발주확인·발송처리·취소)은 스테이징에서 누르지 마라 — 실고객 주문이다.**
3. **좌우 패널 밸런스** (사용자가 스테이징 실화면 스크린샷으로 지적, 2026-08-23):
   1440 폭에서 **왼쪽 목록이 잘린다** — 제품명이 중간에서 끊기고(`…푸쉬타입 180`),
   배지가 줄바꿈돼 행 높이가 들쭉날쭉해진다(스크린샷의 '안경필' 행: `주문 만들기`·
   `발주확인 전`·`발송기한` 이 한 줄에 못 들어가 `발주확인 먼저` 가 아래로 밀렸다).
   반대로 **오른쪽 상세는 여백이 남는다**(금액 열이 화면 끝까지 밀려 표가 헐겁다).
   - 현재: `static/css/admin/naver-workbench.css:161`
     `.wb-split { grid-template-columns: minmax(320px, 400px) 1fr; }`
   - 방향(택1 이상): 좌측 상한을 올리거나(`minmax(360px, 480px)`) 비율 기반으로 바꾼다 ·
     상세 표에 `max-width` 를 줘 남는 여백을 좌측에 넘긴다 · 행의 배지 줄을
     `flex-wrap` + `row-gap` 으로 정돈해 높이가 튀지 않게 한다.
   - **지키면서 고칠 것**: 991.98px 이하 1단 전환 · `#wb-pane > .wb-detail` sticky
     (루트로 올리면 모달이 죽는다) · 목록에 `max-height` 재도입 금지.
   - 확인은 스테이징 실데이터 1440/1280/991 세 폭에서. 스크린샷 근거는 원장에 기록.
4. **남은 리뷰 지적** (원장에 전량 등재, 우선순위 순):
   - **M-4 발송 판정 단위 혼재** — pane 의 `dispatched` 만 링크 1건 기준이고 나머지는 집 단위다.
     워커는 상품주문별로 찍어 부분 성공이 가능해서, 어느 상품주문으로 들어왔느냐에 따라
     취소 버튼이 있기도/없기도 한다. 이력 탭 `처리 탭에서 열기`(`pending_link_id`)가 실제로
     갈리는 경로다. `_group_queue` 에 집 단위 `dispatched` 집계를 추가하는 것이 방향.
   - **M-3 `?link_id=` 가 목록 밖 집을 무장 상태로 연다** — 필요한 경로라 막지 말고
     pane 에 "지금 목록에 없는 집입니다" 표시를 넣는 쪽. 계약 테스트가 현재 동작을 못박아 뒀다.
   - **M-2 주문 만들기 모달 과대 진술** — `member_count`(집 전체) vs `promote_link_to_order` 의
     `_group_siblings`(`order_id IS NULL` + COLLECTED/PENDING_REVIEW). 방향은 안전하나
     재진술이 거짓이고 남는 형제를 화면이 안 알린다. promotion 의미론 결정이 필요.
   - L-1(집 키 폴백 2벌 — `_group_queue` 가 `household_key` 를 쓰면 소멸) ·
     L-3(계약 테스트가 속성 순서를 인질로 — 파싱으로 전환) ·
     L-4(`assert "네이버 주문" not in html` 전역 부분문자열).
5. **승격 게이트(전 직원 개방 전 필수)**: nav 뱃지가 COUNT 1회 → `_work_groups` 전체로
   무거워졌다(조회 4~6회 + 스냅샷 JSONB 파싱 수백 건, 30초 전역 캐시). **TTFB 측정 없이
   코호트를 넓히지 마라.** 지금은 upperkill 단독이라 무해하다.
6. 운영 승격은 **별건**이다 — production 에 네이버 코드가 0줄이고 커밋 123개·마이그레이션 8개가
   미승격이다. v3 커밋만 cherry-pick 하면 깨진다. 전체 승격은 별도 스펙·원장이 필요하고
   **사용자 명시 요청 시에만**.

## 함정

- **AI_STATUS 는 승격할 때마다 충돌한다.** 브랜치와 deploy 가 이미 갈라져 있다(승격 트리에서만
  병합했다). 해결법: deploy(HEAD) 쪽을 채택하고 내 v3 줄만 최신 문장으로 교체.
  상단 40줄 4000자 예산이 빡빡해서 낡은 항목을 기록 보관으로 내려야 할 수 있다
  (`tests/harness/test_hook_log_hygiene.py` 로 확인).
- **broad except 를 새로 추가하면 failopen 인벤토리 재생성 필수** —
  `python tools/harness/failopen_scan.py`. pre_push_smoke 가 못 잡아서 CI 에서 터진다.
- JS/CSS 고치면 `templates/admin/naver_workbench.html` 의 `?v` 핀 범프(현재 `20260823b`).
- **`#wb-pane` 루트에 `position:sticky` 를 다시 걸지 마라.** stacking context 가 생겨
  백드롭이 모달을 덮는다 — 데스크톱에서 단건 불가역 액션 4종이 전부 죽고 벌크만 살아
  사람을 벌크로 민다. sticky 는 `#wb-pane > .wb-detail` 에 있어야 한다.
- **테스트 임시 파일을 저장소 루트에 만들지 마라.** `tests/conftest.py` 보다 먼저 `db` 를
  import 하면 엔진이 로컬 Postgres 에 묶인 채 `drop_all` 이 돈다(2026-08-23 로컬 dev DB
  행 데이터 전량 소실). 가드(`assert_engine_not_postgresql`)를 넣어 뒀지만 습관을 지켜라.
- **로컬 dev DB 에 QA 시드가 남아 있다** — 계정 `qa_v3`/`qa_v3_staff`(비번 `qa!2026`),
  11집·링크 16건·주문 3건. 원래 데이터는 없다(위 사고). 지우는 SQL 은 원장에 있다.
- 로컬 PG 레인 클러스터는 `/c/tmp/pglane5441`(포트 5441, PG17 trust).
  `FOMS_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5441/postgres`

진행 상황은 나한테 매우 상세히 물어봐.**
