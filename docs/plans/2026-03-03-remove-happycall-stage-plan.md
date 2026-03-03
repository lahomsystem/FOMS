---
description: ERP 대시보드 및 전체 프로세스 맵에서 불필요해진 '해피콜(HAPPYCALL)' 단계를 완전 제거하기 위한 분석 및 제거 계획서
---

# '해피콜(HAPPYCALL)' 프로세스 단계 제거 계획서

## 1. 개요
*   **목표**: ERP 시스템 내 워크플로우 단계 중 더 이상 사용하지 않는 `해피콜(HAPPYCALL)` 단계를 템플릿 로직, 필터, 권한 설정, 상수 등 전체 코드베이스에서 직관적이고 완전히 제거합니다. 이를 통해 UI 프로세스 맵을 간소화하고 시스템 혼동을 방지합니다.
*   **변경 대상**: Python 상수·설정, `data/*.json` 퀘스트/태스크/정책 템플릿, 대시보드·Beta 템플릿(HTML/JS), 백엔드 라우터·필터, 테스트/스크립트 매핑.

## 2. 현황 분석 (1:1 소스 검증 반영)

`해피콜` 또는 `HAPPYCALL` 키워드가 존재하는 위치와 각 역할을 완벽 분석한 결과입니다.

### 2.1 Backend / Python 핵심 로직 (1:1 라인 검증됨)
1.  **`constants.py`** (L8): `'HAPPYCALL': '해피콜'` — STATUS 치환 상수. 제거.
2.  **`services/erp_policy.py`**:
    *   L25: `STAGE_LABELS` 내 `"HAPPYCALL": "해피콜"` 제거.
    *   L41: `DEFAULT_OWNER_TEAM_BY_STAGE` 내 `"HAPPYCALL": "CS"` 제거.
    *   L57: `STAGE_NAME_TO_CODE` 내 `"해피콜": "HAPPYCALL"` 제거.
    *   L451: `get_quest_template_for_stage` docstring 예시에서 `'해피콜'`, `'HAPPYCALL'` 언급 삭제.
    *   L601: 주석 `# - 주문접수, 해피콜:` → `# - 주문접수:` 로 수정.
3.  **`erp_build_step_runner.py`**:
    *   L494: `default_owner_team_by_stage` 페이로드 내 `"HAPPYCALL": "CS"` 제거.
    *   L548~L550: `erp_task_templates.json` 미존재 시 생성하는 fallback payload 에서 `"HAPPYCALL": [ {...} ]` 블록 전체 삭제.
4.  **`apps/api/personal_board.py`** (L33): `STAGE_DASHBOARD_URL` 에서 `"HAPPYCALL": "/erp/dashboard"` 제거.
5.  **`apps/erp_dashboard.py`**:
    *   L296: `step_stats` 키 목록에서 `'해피콜'` 제거.
    *   L318: `process_steps` 리스트에서 `{'label': '해피콜', **step_stats['해피콜']}` 항목 제거.

### 2.2 Frontend / Templates (1:1 라인 검증됨)
1.  **단계 필터 `<select name="stage">`**  
    *   `templates/partials/erp_dashboard_filters.html` L39: `<option value="해피콜" ...>해피콜</option>` 한 줄 삭제.  
    *   `templates/partials/erp_production_filters_grid.html` L31: 동일 패턴 한 줄 삭제.  
    *   `templates/partials/erp_construction_filters_grid.html` L31: 동일 패턴 한 줄 삭제.
2.  **ERP Beta 단계 선택 UI**  
    *   `templates/partials/erp_beta_tab.html` L121: `<option value="HAPPYCALL">B. 해피콜</option>` 삭제.  
    *   `templates/partials/erp_beta_js.html` L1805: `ERP_STAGE_LABELS` 내 `HAPPYCALL: 'B. 해피콜'` 삭제.
3.  **JS 스테이지/팀 매핑**  
    *   `templates/erp_object.html` L173: `STAGE_LABELS` 객체에서 `HAPPYCALL:'해피콜'` 제거.  
    *   `templates/partials/erp_dashboard_scripts_detail_dom.html` L61: `STAGE_TO_TEAM`(또는 동일 객체) 내 `'HAPPYCALL': 'CS'` 제거.  
    *   `templates/partials/erp_construction_scripts.html` L999: 팀 매핑 객체 내 `'HAPPYCALL': 'CS'` 제거.  
    *   `templates/partials/erp_production_scripts.html` L682: 팀 매핑 내 `'HAPPYCALL': 'CS'` 제거.

### 2.3 Data / JSON (계획서 누락 → 보완)
*   **`data/erp_quest_templates.json`**
    *   `stages.RECEIVED.next_stage`: `"HAPPYCALL"` → `"MEASURE"` 로 변경 (접수 다음 단계를 실측으로 직결).
    *   `stages.RECEIVED.notes`: 해피콜 언급 제거 또는 "접수 후 실측 단계로 진행" 등으로 수정.
    *   `stages.HAPPYCALL`: **키 전체 블록 삭제** (L21~41: code B, title "해피콜 및 일정 확정", tasks, notes 포함).
*   **`data/erp_task_templates.json`**
    *   `stages.HAPPYCALL`: **키와 배열 전체 삭제** (L11~19, `HAPPYCALL_CONTACT` 태스크 포함).
*   **`data/erp_policy.json`**
    *   `teams.default_owner_team_by_stage` 내 `"HAPPYCALL": "CS"` 한 줄 삭제 (L12).

### 2.4 기타 코드 (계획서 누락 → 보완)
*   **`test_scripts.js`** (L674): `STAGE_TO_TEAM` 객체 내 `'HAPPYCALL': 'CS'` 제거.

### 2.5 문서·백업 (수정 제외 또는 선택 반영)
*   **`docs/evolution/BACKUP_RESTORE_VERIFICATION.md`** (L19): 워크플로 설명에 HAPPYCALL 포함. 선택 시 "RECEIVED → MEASURE → …" 로 수정.
*   **`.cursor/artifacts/FOMS_PROCESS_BLUEPRINT_V3.md`**, **`Furniture Process.md`**, **`.cursor/agents/explore-codebase.md`**: 프로세스 설명에 해피콜 단계 언급. **선택** 시 일치하도록 수정 (실행 필수 아님).
*   **`backups/**/*.sql`**: 과거 이벤트/상태 로그에 `HAPPYCALL` 문자열 포함. **백업 파일은 수정하지 않음** (역사 데이터 보존).

## 3. 실행 단계 (Action Plan)

안전하게 제거하기 위해, 기존에 이미 "해피콜" 상태로 남아있는 레거시 데이터가 터지지(크래시되지) 않도록 처리하는 것이 중요합니다 (완전 하드 코딩 삭제 보다는, UI와 신규 생성 프로세스에서의 제거에 초점을 맞춤).

### Step 1: UI / 화면 노출 제거 (Frontend)
1.  **메인/생산/시공 대시보드 필터**: `erp_dashboard_filters.html`, `erp_production_filters_grid.html`, `erp_construction_filters_grid.html` 에서 `<option value="해피콜">` 태그를 통째로 삭제.
2.  **프로세스 맵 (Pipeline 통계)**: `apps/erp_dashboard.py` 의 `all_stages` 리스트와 `pipeline_data` 에서 `해피콜` 을 삭제하여 상단 프로세스 단계 바에서 사라지게 함.
3.  **주문 편집(Beta) 상세 모달 UI**: `erp_beta_tab.html` 에서 `<option value="HAPPYCALL">` 삭제.

### Step 2: 신규 퀘스트(Quest) 자동 생성 중단 (Backend + Data)
1.  **`data/erp_quest_templates.json`**: `stages.HAPPYCALL` 블록 전체 삭제. `stages.RECEIVED.next_stage` 를 `"MEASURE"` 로 변경, notes 에서 해피콜 언급 제거.
2.  **`data/erp_task_templates.json`**: `stages.HAPPYCALL` 키와 배열(`HAPPYCALL_CONTACT` 태스크) 전체 삭제.
3.  **`erp_build_step_runner.py`**: L548~550 fallback payload 에서 `"HAPPYCALL": [ {...} ]` 블록 삭제. L494 `default_owner_team_by_stage` 에서 `"HAPPYCALL": "CS"` 삭제.
4.  *참고*: `create_quest_from_template(stage)` 는 `get_quest_template_for_stage(stage)` → `erp_quest_templates.json` 을 사용하므로, 위 data 수정만으로 신규 해피콜 퀘스트 생성이 중단됨.

### Step 3: 정책·상수·API 라우트 제거 (Backend)
1.  **`constants.py`**: `STATUS` 내 `'HAPPYCALL': '해피콜'` 제거.
2.  **`services/erp_policy.py`**: `STAGE_LABELS`, `DEFAULT_OWNER_TEAM_BY_STAGE`, `STAGE_NAME_TO_CODE` 에서 HAPPYCALL/해피콜 제거. L451 docstring, L601 주석에서 해피콜 언급 삭제.
3.  **`apps/api/personal_board.py`**: `STAGE_DASHBOARD_URL` 에서 `"HAPPYCALL"` 항목 제거.
4.  **`data/erp_policy.json`**: `teams.default_owner_team_by_stage` 내 `"HAPPYCALL": "CS"` 제거.

### Step 4: Frontend JS·테스트 스크립트 매핑 제거
1.  **Frontend JS**: `erp_beta_js.html` (L1805), `erp_object.html` (L173), `erp_dashboard_scripts_detail_dom.html` (L61), `erp_construction_scripts.html` (L999), `erp_production_scripts.html` (L682) 에서 `HAPPYCALL`/해피콜 관련 키·옵션 삭제.
2.  **`test_scripts.js`** (L674): `STAGE_TO_TEAM` 내 `'HAPPYCALL': 'CS'` 제거.

## 4. 리스크 관리 (Fallback Strategy)
*   **과거 데이터 대응**: DB상에 기존 상태값이 `HAPPYCALL`인 주문이 검색될 경우, `constants.STATUS.get(val, val)` 같은 패턴으로 인해 키가 없더라도 `'HAPPYCALL'` 영문 텍스트 그대로 렌더링되게 됨. 화면이 멈추거나 500 에러를 뱉게 하지는 않으므로, 깔끔하게 상수에서 지워도 안전함.

## 5. 완료 기준 (DoD)
*   [x] **수정 대상 18개 파일** (2026-03-03 실행 완료: py/html/js/json grep 0건 확인) (constants, erp_policy, erp_build_step_runner, erp_dashboard, personal_board, erp_dashboard_filters, erp_production_filters_grid, erp_construction_filters_grid, erp_beta_tab, erp_beta_js, erp_object, erp_dashboard_scripts_detail_dom, erp_construction_scripts, erp_production_scripts, erp_quest_templates.json, erp_task_templates.json, erp_policy.json, test_scripts.js) 에서 `해피콜` 및 `HAPPYCALL` 키워드가 **코드·설정** 상 제거됨. (문서용 주석/설명만 남은 경우 해당 라인도 삭제하여 키워드 0건으로 통일)
*   [x] `data/erp_quest_templates.json` 의 `RECEIVED.next_stage` 가 `"MEASURE"` 로 변경되어 있음.
*   [ ] 대시보드 새로고침 시 화면 상단 프로세스 맵에서 "해피콜" 버튼/단계가 보이지 않음. *(수동 확인)*
*   [ ] 신규 주문 생성·접수 시 해피콜 퀘스트/태스크가 생성되지 않음. *(수동 확인)*
*   [x] *(선택)* 문서: `docs/evolution/BACKUP_RESTORE_VERIFICATION.md` 워크플로 설명을 RECEIVED → MEASURE → … 로 반영함.

## 6. 1:1 소스 검증 요약 (Grand-develop-master 더블체크)
*   **검증일**: 계획서 보완 시점. 전체 코드베이스 `해피콜|HAPPYCALL` grep 및 해당 파일 라인 단위 확인 수행.
*   **"FOMS 내 모든 관련 코드 삭제"**: 위 **18개 파일**에 대해 계획대로 수정을 적용하면, **실행 코드·설정(JSON)·템플릿 상에서 해피콜/HAPPYCALL 참조는 0건**이 됨. 즉, 계획서대로 진행 시 관련 코드는 **전부 삭제될 예정이 맞음**.
*   **계획서 누락 보완**: `data/erp_quest_templates.json`, `data/erp_task_templates.json`, `data/erp_policy.json`, `test_scripts.js` 4건을 현황(§2.3, §2.4) 및 실행 단계(Step 2~4)에 반영함.
*   **RECEIVED → MEASURE 직결**: `erp_quest_templates.json` 에서 HAPPYCALL 블록 삭제 시, `RECEIVED.next_stage` 를 `"MEASURE"` 로 변경해야 접수 후 다음 단계가 실측으로 정상 연결됨.
*   **예외(수정 안 함)**: `backups/**/*.sql`(역사 데이터), `docs/plans/...`·`docs/context/COMPACT_CHECKPOINT.md`·`EDIT_LOG.md`(계획/편집 로그). **문서**(docs/evolution, .cursor/artifacts, Furniture Process.md)는 선택 반영 시 전체 검색 0건으로 통일 가능.
