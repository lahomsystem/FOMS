# 다음 세션 프롬프트 — 네이버 (2026-08-24 밤 작성)

아래를 그대로 붙여 넣으면 된다.

---

**C 네이버 — 코드 전량 승격(충돌 25개 파일별 대조).
작업 위치 `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

원장 `docs/plans/2026-08-24-naver-d1-repay-revision-ledger.md` 를 **§13·§14 부터** 읽어라.
계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` §0.
승격 설계: `docs/specs/2026-08-24-naver-production-promotion-chain_SPEC.md`
(**§8 A안의 "cherry-pick 충돌: 없음" 칸은 거짓이었고 실측값으로 교정돼 있다** — 그 칸을 믿지 마라).

## 지금 상태 (2026-08-24 종료 시점)

- **운영에 스키마가 올라가 있다** (`57cc536d`). `alembic_version = merge_drawq_naverfail`,
  `external_order_links`·`order_change_reasons` 생성, `orders.as_axis_status` 존재.
  운영 7개 화면 육안 확인 완료(전부 200, SQL 오류 흔적 0). **치명 1 은 사라졌다.**
- **운영 코드는 아직 안 갔다.** 네이버 환경변수도 안 넣었다 — 네이버 호출 0, 실주문 생성 0.
- deploy 에는 D1 개정·케이스1 스펙·R1·R2·R3·체인 재직렬화가 전부 올라가 CI 4/4 green.

## 1순위 — 코드 전량 승격

**멈춘 이유**: `origin/production` 에서 `origin/deploy` 를 머지하면 **25개 파일 충돌**이다.
승격 방식이 cherry-pick 이라 같은 수정이 양쪽에 다른 SHA 로 있고, git 이 그걸 "양쪽이
각자 고친 것"으로 본다. deploy 에 없는 운영 커밋이 **74개**(PR #130~#143 승격분).

충돌 25개의 성격은 원장 §13 표에 있다. 요약:
- 사소 2 (`assort_00`·`notifrole_00` docstring 한 줄, `Revises:` 는 양쪽 동일)
- 내 것 2 (`models.py`·`erp_order_js.html` — deploy 가 상위집합)
- 재생성 6 (인벤토리 JSON — 승격 트리에서 재생성이 관례)
- **타 세션 것 14** (AS 대시보드·알림톡·파일 업로드·`layout_scripts`·해당 테스트)

**하지 말 것**: `-X theirs` 로 통째 채택. 운영에만 있던 수정이 조용히 되돌아가도
아무도 모른다. 이 저장소에 keep-both 병합으로 한쪽이 통째 소실된 기록이 있다.

**할 것**: 파일 14개마다 `git log origin/production -- <파일>` 로 그 운영 수정이
deploy 에 (다른 SHA 로) 들어 있는지 대조하고, 확인된 것만 deploy 쪽을 채택한다.
확인 안 되는 게 하나라도 나오면 **거기서 멈추고 사용자에게 물어라.**

승격 뒤 확인: predeploy 로그에 `Running upgrade` 가 **없어야** 한다(스키마는 이미 head).
운영 7개 화면 재확인은 `claude_master` 해제→측정→**재잠금**(사용자 명시 요청 1건 필요).

## 2순위 — 스테이징 화면 육안 확인 (코호트 38 이라 `upperkill` 필요)

`claude_master` 로는 안 열린다. 코호트를 잠시 `38,58` 로 넓히려면 **반드시 38 로 원복**.

- 재결제 집 상세: 버튼이 회색 `발송처리` 인가(파란 `지금 닫기` 면 실패) ·
  안내가 "재결제 집이라 발주확인이 먼저입니다" · 배지는 여전히 `재결제`
- 발주확인 뒤 발송처리가 실제로 열리는가(막다른 길 없음)
- 두 줄 머리(수집+탭 / 칩+정렬+찾기)가 스크롤에 겹치지 않는가
- 도크: 재결제 주문에 "재결제 N건 · M원 — 출고가·잔금에 더하지 마세요" 가 뜨는가
- 도크→워크벤치 링크가 ADMIN 에게 보이고 STAFF 에게는 **앵커가 없는가**
- 집이 둘인 주문에서 **머리말 주문번호(첫 집)와 링크 대상(나중 집)이 다르다** — 기존
  표기 결함, 이번에 안 고쳤다. 오해 소지가 크면 그때 고친다.

## 3순위 — 남은 판단

- 붙이기를 여러 번 누르면 이력 이벤트가 그 수만큼 쌓인다(금액 기록은 멱등).
  `log_access` 감사와 같은 성질이라 그대로 뒀다. 중복이 싫으면 정책 결정 필요.
- 케이스1 스펙 §8 미결: **U-1** 주문 4485 링크 264~269 의 실제 `relation`(실데이터 조회
  승인 필요) · **U-2** 도크 링크 STAFF 노출(지금은 ADMIN·MANAGER 한정이 기본값).
- `docs/AI_STATUS.md` 미갱신(병렬 세션 충돌 회피). 기록은 원장이 갖고 있다.

## 함정 (이번에 실제로 걸린 것만)

- **마이그레이션 파일만 승격하면 pg-lane 이 red 다.** 베이스라인이 `models.py` 의
  `create_all` 이라, 모델에 없는 테이블은 안 만들어지고 downgrade 가 없는 인덱스를
  DROP 하려다 터진다. **대응 모델 선언까지 옮기고 기능 코드는 두고 온다.**
- **모델 선언을 옮기면 두 번째 red 가 드러난다.** `blueprint_00` 의 downgrade 가 부르는
  `_legacy_orders` 가 `Order` 전체 컬럼을 SELECT 한다 — 그 리비전보다 나중에 추가된
  컬럼이 섞여 "column does not exist". deploy 는 `load_only` 로 이미 고쳐 뒀다.
- **`railway status --json` 에 서비스별 `serviceManifest.deploy` 가 들어 있다.**
  GraphQL 은 403 이지만 이걸로 `preDeployCommand` 실사용 여부를 확인할 수 있다.
- **perf-gate 1ms 초과는 예산을 건드리지 마라.** 스테이징 실서버를 재는 것이라 PR diff 와
  무관할 수 있다. 재측정만으로 pass 한 실사례가 이번에 또 나왔다.
- 파이썬 heredoc 안의 백슬래시는 삼켜진다 — `chr(92)` 를 써라.
- Git Bash 경로(`/c/tmp/...`)를 Windows python 에 그대로 넘기면 파일을 못 찾는다.
  `C:/tmp/...` 로 줘라.
- 승격 워크트리는 `c:/tmp` 짧은 경로. 작업 디렉토리가 조용히 `C:\DEV\FOMS` 로 돌아가므로
  git 명령 전에 `pwd` 를 확인해라(공유 트리에 커밋하면 사고다).

## 확정 규칙 (다시 묻지 마라)

- **재결제(REPAY)는 `CLOSE_NOW_RELATIONS` 에 없다.** 발주확인이 먼저다(D1 개정 2026-08-24).
  추가결제(ADDON)만 바로 닫는다.
- 상세는 항상 한 집만. 벌크 대상 ⊆ 화면 목록. 이력 탭 행에 액션·`data-link-id` 금지.
- `close_now` 튜플을 손으로 다시 적지 마라 — `fulfillment.CLOSE_NOW_RELATIONS` 를 import 한다.
- production push 는 사용자 명시 요청 시에만. 기본 푸시 대상은 항상 `deploy`.
- 충돌 = 타 세션 의존 신호 → 임의 해결 금지, 사용자 확인.

진행 상황은 나한테 매우 상세히 물어봐.
