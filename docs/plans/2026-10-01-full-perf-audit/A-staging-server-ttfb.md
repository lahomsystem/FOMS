# 트랙 A 보고 — 스테이징 서버 응답 속도 전수 측정 (2026-10-01)

> 실측 = 이 문서의 표 숫자(스테이징 lahom-dev, 직렬 5회). **추정** 표시가 붙은 것은 코드 읽기로 낸 가설이며 측정으로 확인하지 않았다.
> 코드 위치(경로:행)는 스테이징이 도는 **origin/deploy `51a8858fe`** 기준(로컬 HEAD `7c02059a9` 는 뒤처져 있고 `naver_ingest.py` 등은 다른 세션의 미커밋 수정이 있어 행이 2~3줄 다르다). `/__build` 는 `20260215-uxfix-03` 고정값이라 실제 배포 커밋 확인에는 못 썼다.

## 요약

1. **압도적 1위는 네이버 수집 작업대**: `/admin/naver-ingest/triage` Δ657ms(render 625), `?tab=all` Δ586ms(render 559). 둘 다 전역 render 예산 500ms 초과(게이트 대상 아님). 원인 구간 `wb_work_groups` 472/550ms(`wg_sibling` 172~242 · `wg_fetch` 146~148 · `wg_group_queue` 106~108).
   - 09-11 스테이징 실측(`docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md` §10.3): 이력 탭 `wb_work_groups` 308~355(`wg_fetch` 93~100 · `wg_sibling` 110~133 · `wg_group_queue` 62~80) → 지금 550. 집 수 214 → 319(처리 233 + 잠김 86). **데이터 증가에 거의 비례해 느려지고 있다.**
   - 같은 계산이 nav 배지 API `/admin/naver-ingest/triage/pending-count`(전체 페이지마다 로드 직후 호출)의 캐시 miss 때 돈다: 콜드 757·748·674ms vs 웜 119~123ms. 2026-08-24 주석 기준 콜드 113ms(73집) → **약 5.5배**. 캐시는 프로세스 메모리 30초(gunicorn gevent -w 2 → 워커마다 따로 miss).
2. **실측 날짜칩 첫 클릭 콜드 비용**: 처음 여는 날짜 801·886·807·873·842ms vs 웜 160~175ms(5/5 재현). 계측 헤더가 없어 구간 분해 불가. 코드상 패널 캐시 키에 `selected_date` 가 들어가 날짜마다 miss(아래 개선안 2).
3. **정산 화면 진입 시 자동 호출 `/api/settlement/aggregates` Δ228ms**(rows 탭 `/api/settlement/rows` Δ202ms). 둘 다 모집단 전량 `structured_data` 를 읽고 파이썬에서 거른다.
4. 9개 ERP fragment(게이트 대상)는 **전부 예산 PASS, 09-11 대비 Δ ±10ms(노이즈)** — 최근 회귀 없음. 07-05 대비로는 completion +58, measurement +33, dashboard +19, production +16ms(두 계측 없는 화면 포함, 원인 판정 불가).
5. 104경로 중 85경로는 render 헤더가 없다(9 primary 중 measurement·drawing-workbench·completion 포함). 대시보드는 헤더가 있어도 `_t0` 이후 렌더만 재서 Δ103 중 ~85ms가 미계측.

# 트랙 A — 스테이징 서버 응답 전수 측정 (2026-10-01, lahom-dev)

- 측정 창: 2026-10-01T14:14:24 ~ 2026-10-01T14:20:51 (KST, 로컬 PC → Railway 싱가포르). 직렬, 경로당 5회(0.4s 간격), 경로 사이 0.6s.
- 계정 claude_master(스테이징), 로그인 POST 1회 외 전부 GET. 쿠키·헤더: `tools/harness/ept_b8_staging_session_from_login.py` 로그인 재사용, 데스크톱 Chrome UA, `Accept-Encoding: gzip, br`, 페르소나 쿠키 `foms_scr=1920; foms_ptr=fine; foms_vw=wide`(게이트와 동일). 모바일 행은 iPhone Safari UA + `foms_scr=852; foms_ptr=coarse; foms_vw=narrow`.
- fragment 행은 게이트와 같은 `X-FOMS-ERP-SHELL: 1` + `Accept: text/html`. 리다이렉트는 따라가지 않음(`allow_redirects=False`).
- **값 정의**: `r1` = 1회째(웜업, Jinja 첫 컴파일·캐시 miss 섞일 수 있음). `min/med` = 2~5회째 **본문까지 받은 시간**(게이트 `ttfb_ms` 와 같은 방식: requests 가 본문까지 읽은 뒤 시각). `hdr min` = 응답 헤더 도착 시각(순수 TTFB). `Δ` = min − healthz min(서버+페이로드 델타, 게이트 판정값과 같은 정의).
- healthz min(본문 포함): 시작 120.4 / 중간 117.9 / 끝 122.8 ms → 앞 절반은 min(시작,중간), 뒷 절반은 min(중간,끝)을 기준선으로 사용.
- 원자료: `raw_142051.json`(전 표본·헤더), `summary_142051.json`, 콜드 재현 `probe_cold.json`. 스크립트 `measure.py`·`analyze.py`·`probe_cold.py`.

## 1. 전체 표 (측정 104경로)

| # | 그룹 | 기기 | 경로 | 상태 | r1 | min | med | hdr min | Δ | render min | wire B | 해압 B | phases 상위(중앙값 ms) | 예산 대비 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | fragment | pc | `/erp/dashboard?view=fragment` | 200 | 263 | 221 | 229 | 206 | **103** | 12.0 | 22254 | 355256 | row_dtos=5 | PASS Δ103/167 B22254/26827 |
| 1 | fragment | pc | `/erp/measurement?view=fragment` | 200 | 177 | 175 | 178 | 162 | **57** | 없음 | 13095 | 67975 | - | PASS Δ57/140 B13095/17485 |
| 2 | fragment | pc | `/erp/drawing-workbench?view=fragment` | 200 | 158 | 160 | 178 | 154 | **42** | 없음 | 11297 | 79810 | - | PASS Δ42/124 B11297/17497 |
| 3 | fragment | pc | `/erp/production/dashboard?view=fragment` | 200 | 195 | 191 | 198 | 175 | **73** | 5.4 | 33815 | 239662 | - | PASS Δ73/133 B33815/47960 |
| 4 | fragment | pc | `/erp/shipment?view=fragment` | 200 | 145 | 152 | 157 | 149 | **34** | 2.6 | 8582 | 48620 | - | PASS Δ34/291 B8582/11648 |
| 5 | fragment | pc | `/erp/as?view=fragment` | 200 | 260 | 219 | 225 | 204 | **102** | 14.5 | 37046 | 549784 | row_display=24, list_query=18, tab_counts=15, rd_loop=11 | PASS Δ102/168 B37046/46032 |
| 6 | fragment | pc | `/erp/construction/dashboard?view=fragment` | 200 | 207 | 176 | 186 | 172 | **58** | 5.1 | 16363 | 175203 | list_query=30, mobile_enrich=5, row_dtos=4, summary_slice=3 | PASS Δ58/147 B16363/23812 |
| 7 | fragment | pc | `/erp/completion?view=fragment` | 200 | 169 | 180 | 192 | 175 | **62** | 없음 | 9894 | 40788 | - | PASS Δ62/107 B9894/12507 |
| 8 | fragment | pc | `/erp/history/?view=fragment` | 200 | 147 | 123 | 126 | 121 | **5** | 1.6 | 7472 | 29694 | - | PASS Δ5/99 B7472/9330 |
| 9 | fragment-date | pc | `/erp/measurement?date=2026-10-01&view=fragment` | 200 | 200 | 170 | 176 | 157 | **52** | 없음 | 13104 | 67995 | - | PASS Δ52/200 B13104/50000 |
| 10 | fragment-date | pc | `/erp/measurement?date=2026-10-02&view=fragment` | 200 | 801 | 165 | 172 | 160 | **47** | 없음 | 13118 | 67995 | - | PASS Δ47/200 B13118/50000 |
| 11 | fragment-date | pc | `/erp/measurement?date=2026-10-03&view=fragment` | 200 | 886 | 175 | 181 | 170 | **57** | 없음 | 13111 | 67995 | - | PASS Δ57/200 B13111/50000 |
| 12 | page-primary | pc | `/erp/dashboard` | 200 | 253 | 226 | 229 | 207 | **108** | 13.6 | 53691 | 504164 | row_dtos=5 | - |
| 13 | page-primary | pc | `/erp/measurement` | 200 | 175 | 180 | 182 | 167 | **62** | 없음 | 42574 | 211065 | - | - |
| 14 | page-primary | pc | `/erp/drawing-workbench` | 200 | 299 | 159 | 174 | 147 | **41** | 없음 | 40988 | 222548 | - | - |
| 15 | page-primary | pc | `/erp/production/dashboard` | 200 | 222 | 203 | 211 | 186 | **85** | 8.1 | 62704 | 382550 | - | - |
| 16 | page-primary | pc | `/erp/shipment` | 200 | 156 | 175 | 180 | 165 | **57** | 5.8 | 39082 | 193673 | - | - |
| 17 | page-primary | pc | `/erp/as` | 200 | 255 | 226 | 230 | 207 | **108** | 16.6 | 67092 | 693180 | row_display=22, list_query=18, tab_counts=17, rd_loop=12 | - |
| 18 | page-primary | pc | `/erp/construction/dashboard` | 200 | 220 | 210 | 214 | 198 | **92** | 8.2 | 46139 | 318349 | list_query=34, mobile_enrich=5, row_dtos=4, summary_slice=3 | - |
| 19 | page-primary | pc | `/erp/completion` | 200 | 199 | 182 | 187 | 172 | **64** | 없음 | 39455 | 183677 | - | - |
| 20 | page-primary | pc | `/erp/history/` | 200 | 149 | 137 | 140 | 127 | **19** | 4.1 | 37136 | 172589 | - | - |
| 21 | page | pc | `/` | 200 | 987 | 203 | 260 | 190 | **85** | 없음 | 55325 | 430997 | - | - |
| 22 | page | pc | `/add` | 200 | 196 | 150 | 153 | 138 | **32** | 없음 | 53241 | 244882 | - | - |
| 23 | page | pc | `/admin` | 200 | 138 | 150 | 168 | 140 | **32** | 없음 | 32392 | 145877 | - | - |
| 24 | page | pc | `/admin/alimtalk-failures` | 200 | 162 | 135 | 146 | 128 | **18** | 없음 | 30697 | 139142 | - | - |
| 25 | page | pc | `/admin/backup-status` | 200 | 149 | 144 | 154 | 133 | **26** | 없음 | 30830 | 138931 | - | - |
| 26 | page | pc | `/admin/change-reasons` | 200 | 136 | 142 | 146 | 126 | **24** | 없음 | 30619 | 138805 | - | - |
| 27 | page | pc | `/admin/file-access-logs` | 200 | 170 | 149 | 157 | 142 | **32** | 없음 | 33442 | 174178 | - | - |
| 28 | page | pc | `/admin/naver-ingest` → /admin/naver-ingest/triage?tab=all | 302 | 122 | 120 | 131 | 120 | **2** | 없음 | 0 | 0 | - | - |
| 29 | page | pc | `/admin/naver-ingest/triage` | 200 | 945 | 775 | 784 | 760 | **657** | 625.0 | 59700 | 600873 | wb_work_groups=472, wg_sibling=172, wg_fetch=148, wg_group_queue=108 | - |
| 30 | page | pc | `/admin/naver-ingest/triage?tab=all` | 200 | 754 | 704 | 818 | 695 | **586** | 558.9 | 39036 | 234755 | wb_work_groups=550, wg_sibling=242, wg_fetch=146, wg_group_queue=106 | - |
| 31 | page | pc | `/admin/notifications` | 200 | 155 | 138 | 147 | 130 | **20** | 없음 | 32356 | 145483 | - | - |
| 32 | page | pc | `/admin/users` | 200 | 225 | 149 | 159 | 139 | **31** | 없음 | 32813 | 182601 | - | - |
| 33 | page | pc | `/admin/users/add` | 200 | 138 | 133 | 146 | 126 | **15** | 없음 | 30873 | 140222 | - | - |
| 34 | page | pc | `/change-logs` | 200 | 153 | 135 | 155 | 127 | **17** | 없음 | 33382 | 149523 | - | - |
| 35 | page | pc | `/chat` | 200 | 153 | 139 | 148 | 130 | **21** | 없음 | 37807 | 177624 | - | - |
| 36 | page | pc | `/erp/dashboard/field-ops` | 200 | 213 | 178 | 181 | 178 | **60** | 없음 | 279 | 385 | - | - |
| 37 | page | pc | `/erp/settlement` | 200 | 179 | 137 | 147 | 127 | **19** | 없음 | 36800 | 169880 | - | - |
| 38 | page | pc | `/erp/shipment-settings` | 200 | 166 | 151 | 155 | 141 | **33** | 없음 | 36229 | 186178 | - | - |
| 39 | page | pc | `/map_view` | 200 | 152 | 130 | 136 | 127 | **12** | 없음 | 30355 | 132773 | - | - |
| 40 | page | pc | `/metropolitan_dashboard` | 200 | 452 | 288 | 290 | 275 | **170** | 없음 | 55900 | 436856 | - | - |
| 41 | page | pc | `/regional_dashboard` | 200 | 159 | 157 | 165 | 144 | **39** | 없음 | 54597 | 415640 | - | - |
| 42 | page | pc | `/self_measurement_dashboard` | 200 | 162 | 157 | 160 | 147 | **39** | 없음 | 51177 | 491424 | - | - |
| 43 | page | pc | `/profile` | 200 | 152 | 144 | 149 | 134 | **26** | 없음 | 30970 | 141203 | - | - |
| 44 | page | pc | `/security_logs` | 200 | 212 | 175 | 186 | 167 | **57** | 없음 | 34915 | 178402 | - | - |
| 45 | page | pc | `/storage_dashboard` | 200 | 155 | 149 | 155 | 140 | **31** | 없음 | 36599 | 186936 | - | - |
| 46 | page | pc | `/trash` | 200 | 248 | 248 | 333 | 233 | **130** | 없음 | 58815 | 420213 | - | - |
| 47 | page | pc | `/wdcalculator` | 200 | 208 | 149 | 157 | 137 | **31** | 없음 | 42191 | 203145 | - | - |
| 48 | page | pc | `/wdcalculator/product-settings` | 200 | 189 | 152 | 164 | 142 | **34** | 없음 | 40318 | 242245 | - | - |
| 49 | page | pc | `/orders` → / | 302 | 119 | 121 | 127 | 121 | **3** | 없음 | 0 | 0 | - | - |
| 50 | page-order | pc | `/edit/4385` | 200 | 238 | 160 | 166 | 141 | **43** | 없음 | 68285 | 348701 | - | - |
| 51 | page-order | pc | `/erp/drawing-workbench/4385` | 200 | 147 | 155 | 164 | 146 | **37** | 없음 | 55680 | 255789 | - | - |
| 52 | page-order | pc | `/erp/drawing-workbench/4385/wizard` | 200 | 126 | 123 | 125 | 122 | **5** | 없음 | 8192 | 33570 | - | - |
| 53 | page-order | pc | `/erp/orders/4385/label` | 200 | 127 | 126 | 140 | 126 | **8** | 없음 | 505 | 1085 | - | - |
| 54 | page-order | pc | `/erp/dashboard/tablet-sheet/4385` | 200 | 145 | 132 | 145 | 132 | **14** | 없음 | 658 | 1700 | - | - |
| 55 | page-order | pc | `/erp/production/tablet-sheet/4069` | 200 | 149 | 128 | 136 | 128 | **10** | 없음 | 1090 | 3619 | - | - |
| 56 | page-order | pc | `/erp/drawing-workbench/tablet-sheet/4385` | 200 | 141 | 129 | 137 | 129 | **11** | 없음 | 646 | 2013 | - | - |
| 57 | page-order | pc | `/erp/shipment/tablet-sheet/4385` | 200 | 155 | 130 | 139 | 130 | **12** | 없음 | 860 | 5502 | - | - |
| 58 | page-order | pc | `/erp/completion/tablet-sheet/4385` | 200 | 137 | 140 | 144 | 140 | **22** | 없음 | 902 | 3086 | - | - |
| 59 | page-order | pc | `/erp/history/tablet-sheet/4385` | 200 | 153 | 125 | 132 | 125 | **7** | 없음 | 704 | 1941 | - | - |
| 60 | page-order | pc | `/erp/as/card-detail/4388` | 200 | 186 | 129 | 150 | 128 | **11** | 없음 | 2991 | 15518 | - | - |
| 61 | page-order | pc | `/erp/as/timeline/4388` | 200 | 134 | 128 | 141 | 128 | **10** | 없음 | 2774 | 14712 | - | - |
| 62 | page-order | pc | `/api/foms/fragment/order/4385/edit` | 200 | 146 | 140 | 152 | 134 | **22** | 없음 | 24515 | 130716 | - | - |
| 63 | page-order | pc | `/api/foms/fragment/order/4385/timeline` | 200 | 139 | 129 | 130 | 129 | **11** | 없음 | 837 | 5135 | - | - |
| 64 | page-order | pc | `/admin/naver-ingest/triage/pane?link_id=2804` | 200 | 160 | 150 | 162 | 148 | **32** | 없음 | 4104 | 12777 | - | - |
| 65 | page-order | pc | `/admin/naver-ingest/triage/detail?link_id=2804` | 200 | 153 | 135 | 144 | 135 | **17** | 없음 | 1231 | 3132 | - | - |
| 66 | mobile | mobile | `/erp/dashboard` | 200 | 738 | 216 | 225 | 200 | **98** | 11.8 | 48100 | 276963 | row_dtos=6 | - |
| 67 | mobile | mobile | `/erp/dashboard?view=fragment` | 200 | 217 | 205 | 214 | 200 | **87** | 10.4 | 16753 | 128055 | row_dtos=5 | - |
| 68 | mobile | mobile | `/erp/measurement` | 200 | 209 | 179 | 187 | 165 | **61** | 없음 | 43589 | 221494 | - | - |
| 69 | mobile | mobile | `/erp/production/dashboard` | 200 | 308 | 211 | 218 | 196 | **93** | 17.8 | 77786 | 566685 | - | - |
| 70 | mobile | mobile | `/erp/construction/dashboard` | 200 | 255 | 207 | 211 | 194 | **89** | 17.8 | 60168 | 598201 | list_query=32, mobile_enrich=4, summary_slice=3, attachment_slice=3 | - |
| 71 | mobile | mobile | `/erp/as` | 200 | 238 | 232 | 236 | 218 | **114** | 25.3 | 81568 | 975027 | row_display=22, list_query=18, tab_counts=15, rd_loop=12 | - |
| 72 | mobile | mobile | `/erp/orders/4385/mobile` | 200 | 218 | 158 | 170 | 149 | **40** | 없음 | 37703 | 185664 | - | - |
| 73 | mobile | mobile | `/add` | 200 | 152 | 137 | 145 | 130 | **19** | 없음 | 35606 | 164567 | - | - |
| 74 | mobile | mobile | `/edit/4385` | 200 | 158 | 154 | 156 | 141 | **37** | 없음 | 68285 | 348701 | - | - |
| 75 | api | pc | `/erp/api/notifications/badge` | 200 | 134 | 118 | 122 | 118 | **0** | 없음 | 29 | 29 | - | - |
| 76 | api | pc | `/erp/api/notifications/pending-interrupts` | 200 | 128 | 127 | 132 | 127 | **10** | 없음 | 50 | 50 | - | - |
| 77 | api | pc | `/admin/naver-ingest/triage/pending-count` | 200 | 757 | 121 | 127 | 121 | **4** | 없음 | 51 | 51 | - | - |
| 78 | api | pc | `/erp/api/notifications?limit=30` | 200 | 133 | 130 | 133 | 130 | **12** | 없음 | 2101 | 34353 | - | - |
| 79 | api | pc | `/erp/api/notifications/mobile-state` | 200 | 125 | 128 | 133 | 128 | **10** | 없음 | 121 | 121 | - | - |
| 80 | api | pc | `/erp/api/notifications/push/vapid-public-key` | 200 | 129 | 125 | 127 | 125 | **7** | 없음 | 129 | 129 | - | - |
| 81 | api | pc | `/api/erp/measurement/undated` | 200 | 203 | 203 | 283 | 203 | **85** | 없음 | 3134 | 16723 | - | - |
| 82 | api | pc | `/api/erp/measurement/summary` | 200 | 135 | 134 | 136 | 134 | **16** | 없음 | 262 | 2335 | - | - |
| 83 | api | pc | `/erp/api/users` | 200 | 135 | 130 | 142 | 130 | **12** | 없음 | 616 | 2023 | - | - |
| 84 | api | pc | `/api/orders/4385/drawing-wizard` | 200 | 138 | 134 | 138 | 134 | **16** | 없음 | 537 | 1060 | - | - |
| 85 | api | pc | `/api/orders/4385/drawing-wizard/pending` | 200 | 135 | 130 | 137 | 130 | **12** | 없음 | 39 | 39 | - | - |
| 86 | api | pc | `/api/orders/drawing-wizard/presets` | 200 | 129 | 131 | 136 | 131 | **13** | 없음 | 51 | 51 | - | - |
| 87 | api | pc | `/api/orders/4385/drawing-wizard/versions` | 200 | 132 | 126 | 129 | 126 | **8** | 없음 | 40 | 40 | - | - |
| 88 | api | pc | `/api/orders/4385/detail-payload` | 200 | 127 | 126 | 133 | 126 | **8** | 없음 | 1124 | 2770 | - | - |
| 89 | api | pc | `/api/orders/4385/structured` | 200 | 128 | 125 | 139 | 125 | **7** | 없음 | 1399 | 3318 | - | - |
| 90 | api | pc | `/api/orders/4385/quest` | 200 | 146 | 125 | 131 | 124 | **7** | 없음 | 196 | 196 | - | - |
| 91 | api | pc | `/api/orders/4385/attachments` | 200 | 131 | 131 | 132 | 131 | **13** | 없음 | 34 | 34 | - | - |
| 92 | api | pc | `/api/orders/4385/change-events` | 200 | 138 | 134 | 152 | 133 | **16** | 없음 | 1138 | 7346 | - | - |
| 93 | api | pc | `/api/orders/4385/blueprint` | 200 | 135 | 126 | 135 | 126 | **8** | 없음 | 28 | 28 | - | - |
| 94 | api | pc | `/admin/naver-ingest/run-state` | 200 | 129 | 126 | 134 | 126 | **8** | 없음 | 211 | 211 | - | - |
| 95 | api | pc | `/admin/naver-ingest/backfill-state` | 200 | 146 | 131 | 133 | 130 | **13** | 없음 | 277 | 496 | - | - |
| 96 | api | pc | `/admin/naver-ingest/triage/refresh-running` | 200 | 144 | 126 | 135 | 126 | **8** | 없음 | 55 | 55 | - | - |
| 97 | api | pc | `/admin/naver-ingest/bulk-dispatch/state` | 200 | 140 | 140 | 148 | 140 | **22** | 없음 | 240 | 409 | - | - |
| 98 | api | pc | `/api/settlement/aggregates` | 200 | 410 | 346 | 359 | 346 | **228** | 없음 | 1581 | 9668 | - | - |
| 99 | api | pc | `/api/settlement/rows` | 200 | 309 | 320 | 394 | 320 | **202** | 없음 | 1751 | 27658 | - | - |
| 100 | api | pc | `/api/settlement/channel` | 200 | 212 | 184 | 192 | 182 | **67** | 없음 | 10818 | 151014 | - | - |
| 101 | api | pc | `/api/chat/rooms` | 200 | 143 | 139 | 141 | 138 | **21** | 없음 | 38 | 38 | - | - |
| 102 | api | pc | `/api/me/change-events` | 200 | 175 | 167 | 170 | 167 | **49** | 없음 | 4151 | 83640 | - | - |
| 103 | api | pc | `/api/orders/change-reason-codes` | 200 | 130 | 124 | 127 | 124 | **6** | 없음 | 227 | 455 | - | - |

## 2. 느린 화면 순위 (Δ = 서버+페이로드, 실측)

| 순위 | 경로 | 기기 | Δ ms | min / med ms | render min | 계측 |
|---|---|---|---|---|---|---|
| 1 | `/admin/naver-ingest/triage` | pc | 657 | 775 / 784 | 625.0 | 있음 |
| 2 | `/admin/naver-ingest/triage?tab=all` | pc | 586 | 704 / 818 | 558.9 | 있음 |
| 3 | `/api/settlement/aggregates` | pc | 228 | 346 / 359 | - | 없음 |
| 4 | `/api/settlement/rows` | pc | 202 | 320 / 394 | - | 없음 |
| 5 | `/metropolitan_dashboard` | pc | 170 | 288 / 290 | - | 없음 |
| 6 | `/trash` | pc | 130 | 248 / 333 | - | 없음 |
| 7 | `/erp/as` | mobile | 114 | 232 / 236 | 25.3 | 있음 |
| 8 | `/erp/dashboard` | pc | 108 | 226 / 229 | 13.6 | 있음 |
| 9 | `/erp/as` | pc | 108 | 226 / 230 | 16.6 | 있음 |
| 10 | `/erp/dashboard?view=fragment` | pc | 103 | 221 / 229 | 12.0 | 있음 |
| 11 | `/erp/as?view=fragment` | pc | 102 | 219 / 225 | 14.5 | 있음 |
| 12 | `/erp/dashboard` | mobile | 98 | 216 / 225 | 11.8 | 있음 |
| 13 | `/erp/production/dashboard` | mobile | 93 | 211 / 218 | 17.8 | 있음 |
| 14 | `/erp/construction/dashboard` | pc | 92 | 210 / 214 | 8.2 | 있음 |
| 15 | `/erp/construction/dashboard` | mobile | 89 | 207 / 211 | 17.8 | 있음 |
| 16 | `/erp/dashboard?view=fragment` | mobile | 87 | 205 / 214 | 10.4 | 있음 |
| 17 | `/` | pc | 85 | 203 / 260 | - | 없음 |
| 18 | `/erp/production/dashboard` | pc | 85 | 203 / 211 | 8.1 | 있음 |
| 19 | `/api/erp/measurement/undated` | pc | 85 | 203 / 283 | - | 없음 |
| 20 | `/erp/production/dashboard?view=fragment` | pc | 73 | 191 / 198 | 5.4 | 있음 |

## 3. 콜드(캐시 miss) 비용 — 웜 값만 보면 안 보이는 것 (실측)

| 경로 | 콜드 표본(ms) | 웜 표본(ms) | 판정 |
|---|---|---|---|
| `/admin/naver-ingest/triage/pending-count` (모든 전체 페이지가 로드 직후 호출) | 757, 748, 674 | 119, 123, 121, 120 | 프로세스별 30s 캐시 miss 때 `_work_groups(display=False)` 1회 ≈ 550~640ms 서버 |
| `/erp/measurement?date=<처음 여는 날짜>&view=fragment` | 801, 886, 807, 873, 842 | 160, 164, 168 (본 측정 warm min 165~175) | 날짜별 캐시 miss ≈ 640~720ms 추가. 계측 헤더 없음 |
| `/` (주문 목록) | 987 (본 측정 r1) | 203~264 | 1회성 — 35초 간격 3회 재현 안 됨. Jinja 첫 컴파일 추정(계측 없어 판정 불가) |
| `/erp/dashboard` (모바일) | 738 (r1, render 281) | 216~225 (render 12) | render 구간만 269ms 증가 → Jinja 첫 컴파일(기규명 사실과 일치) |
| `/erp/dashboard?view=fragment`, `/erp/as?view=fragment` | 207~238 (35s 뒤 첫 요청) | 208~393 | 콜드 비용 없음(간헐 393/364 는 tail) |

## 4. 예전 대비 (9 primary fragment + 날짜칩) — 게이트 증거와 같은 정의

과거 증거: `docs/harness/evidence/perf-gate-*.json`. 07-05 는 페르소나 쿠키 없음(전 표면 렌더, 바이트 미기록), 09-11 16:23·16:26 은 pc-wide-fine(지금과 같은 페르소나).

| 경로 | 07-05 Δ | 09-11 Δ (2회) | 지금 Δ | 예산 Δ | 09-11 wire | 지금 wire | 예산 wire | render min 09-11 → 지금 |
|---|---|---|---|---|---|---|---|---|
| `/erp/dashboard?view=fragment` | 84 | 109, 107 | **103** | 167 | 20636 | 22254 | 26827 | 16, 17 → 12.0 |
| `/erp/measurement?view=fragment` | 24 | 51, 47 | **57** | 140 | 13450 | 13095 | 17485 | None → 없음 |
| `/erp/drawing-workbench?view=fragment` | 48 | 42, 39 | **42** | 124 | 13459 | 11297 | 17497 | None → 없음 |
| `/erp/production/dashboard?view=fragment` | 57 | 75, 74 | **73** | 133 | 36892 | 33815 | 47960 | 9 → 5.4 |
| `/erp/shipment?view=fragment` | 30 | 33, 30 | **34** | 291 | 8960 | 8582 | 11648 | 3 → 2.6 |
| `/erp/as?view=fragment` | 93 | 106, 105 | **102** | 168 | 35409 | 37046 | 46032 | 16, 17 → 14.5 |
| `/erp/construction/dashboard?view=fragment` | 66 | 67, 69 | **58** | 147 | 18317 | 16363 | 23812 | 9 → 5.1 |
| `/erp/completion?view=fragment` | 4 | 59, 63 | **62** | 107 | 9621 | 9894 | 12507 | None → 없음 |
| `/erp/history/?view=fragment` | - | 10, 9 | **5** | 99 | 7177 | 7472 | 9330 | 1, 2 → 1.6 |
| `/erp/measurement?date=2026-10-01&view=fragment` | - | 48, 46, 46, 48, 48, 47 | **52** | 200 | 13465, 13473, 13474 | 13104 | 50000 | None → 없음 |
| `/erp/measurement?date=2026-10-02&view=fragment` | - | 48, 46, 46, 48, 48, 47 | **47** | 200 | 13465, 13473, 13474 | 13118 | 50000 | None → 없음 |
| `/erp/measurement?date=2026-10-03&view=fragment` | - | 48, 46, 46, 48, 48, 47 | **57** | 200 | 13465, 13473, 13474 | 13111 | 50000 | None → 없음 |

9개 fragment 는 전부 예산 PASS, 09-11 대비 Δ 변화 ±10ms 이내(노이즈 범위). 조건부 304(ETag 재검증)는 9개 모두 304 확인.
304 왕복(본문 포함) ms: /erp/dashboard=221, /erp/measurement=174, /erp/drawing-workbench=149, /erp/production/dashboard=187, /erp/shipment=154, /erp/as=207, /erp/construction/dashboard=196, /erp/completion=180, /erp/history/=135

## 5. 계측 헤더(`X-FOMS-EPT-B7-RENDER-MS`) 없는 화면 — 서버 느림 판정 불가

총 85개 / 104개. DASH-SLICES 헤더는 시공 대시보드에만 있다.

- **fragment**: `/erp/measurement?view=fragment`(Δ57), `/erp/drawing-workbench?view=fragment`(Δ42), `/erp/completion?view=fragment`(Δ62)
- **fragment-date**: `/erp/measurement?date=2026-10-01&view=fragment`(Δ52), `/erp/measurement?date=2026-10-02&view=fragment`(Δ47), `/erp/measurement?date=2026-10-03&view=fragment`(Δ57)
- **page-primary**: `/erp/measurement`(Δ62), `/erp/drawing-workbench`(Δ41), `/erp/completion`(Δ64)
- **page**: `/`(Δ85), `/add`(Δ32), `/admin`(Δ32), `/admin/alimtalk-failures`(Δ18), `/admin/backup-status`(Δ26), `/admin/change-reasons`(Δ24), `/admin/file-access-logs`(Δ32), `/admin/naver-ingest`(Δ2), `/admin/notifications`(Δ20), `/admin/users`(Δ31), `/admin/users/add`(Δ15), `/change-logs`(Δ17), `/chat`(Δ21), `/erp/dashboard/field-ops`(Δ60), `/erp/settlement`(Δ19), `/erp/shipment-settings`(Δ33), `/map_view`(Δ12), `/metropolitan_dashboard`(Δ170), `/regional_dashboard`(Δ39), `/self_measurement_dashboard`(Δ39), `/profile`(Δ26), `/security_logs`(Δ57), `/storage_dashboard`(Δ31), `/trash`(Δ130), `/wdcalculator`(Δ31), `/wdcalculator/product-settings`(Δ34), `/orders`(Δ3)
- **page-order**: `/edit/4385`(Δ43), `/erp/drawing-workbench/4385`(Δ37), `/erp/drawing-workbench/4385/wizard`(Δ5), `/erp/orders/4385/label`(Δ8), `/erp/dashboard/tablet-sheet/4385`(Δ14), `/erp/production/tablet-sheet/4069`(Δ10), `/erp/drawing-workbench/tablet-sheet/4385`(Δ11), `/erp/shipment/tablet-sheet/4385`(Δ12), `/erp/completion/tablet-sheet/4385`(Δ22), `/erp/history/tablet-sheet/4385`(Δ7), `/erp/as/card-detail/4388`(Δ11), `/erp/as/timeline/4388`(Δ10), `/api/foms/fragment/order/4385/edit`(Δ22), `/api/foms/fragment/order/4385/timeline`(Δ11), `/admin/naver-ingest/triage/pane?link_id=2804`(Δ32), `/admin/naver-ingest/triage/detail?link_id=2804`(Δ17)
- **mobile**: `/erp/measurement`(Δ61), `/erp/orders/4385/mobile`(Δ40), `/add`(Δ19), `/edit/4385`(Δ37)
- **api**: `/erp/api/notifications/badge`(Δ0), `/erp/api/notifications/pending-interrupts`(Δ10), `/admin/naver-ingest/triage/pending-count`(Δ4), `/erp/api/notifications?limit=30`(Δ12), `/erp/api/notifications/mobile-state`(Δ10), `/erp/api/notifications/push/vapid-public-key`(Δ7), `/api/erp/measurement/undated`(Δ85), `/api/erp/measurement/summary`(Δ16), `/erp/api/users`(Δ12), `/api/orders/4385/drawing-wizard`(Δ16), `/api/orders/4385/drawing-wizard/pending`(Δ12), `/api/orders/drawing-wizard/presets`(Δ13), `/api/orders/4385/drawing-wizard/versions`(Δ8), `/api/orders/4385/detail-payload`(Δ8), `/api/orders/4385/structured`(Δ7), `/api/orders/4385/quest`(Δ7), `/api/orders/4385/attachments`(Δ13), `/api/orders/4385/change-events`(Δ16), `/api/orders/4385/blueprint`(Δ8), `/admin/naver-ingest/run-state`(Δ8), `/admin/naver-ingest/backfill-state`(Δ13), `/admin/naver-ingest/triage/refresh-running`(Δ8), `/admin/naver-ingest/bulk-dispatch/state`(Δ22), `/api/settlement/aggregates`(Δ228), `/api/settlement/rows`(Δ202), `/api/settlement/channel`(Δ67), `/api/chat/rooms`(Δ21), `/api/me/change-events`(Δ49), `/api/orders/change-reason-codes`(Δ6)

## 6. 구간 분해 (계측 있는 느린 경로)

- `/erp/dashboard?view=fragment` (pc) Δ103, render min 12.0: row_dtos=5
- `/erp/as?view=fragment` (pc) Δ102, render min 14.5: row_display=24; list_query=18; tab_counts=15; rd_loop=11; rd_timeline=10; rd_drift=4; rd_attach_q=2; rd_normalize=2
- `/erp/construction/dashboard?view=fragment` (pc) Δ58, render min 5.1: list_query=30; mobile_enrich=5; row_dtos=4; summary_slice=3; attachment_slice=3
  - DASH-SLICES: ['summary_counts=hit:0;attachment_counts=miss:4', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0']
- `/erp/dashboard` (pc) Δ108, render min 13.6: row_dtos=5; shell_nav=2
- `/erp/production/dashboard` (pc) Δ85, render min 8.1: shell_nav=2
- `/erp/shipment` (pc) Δ57, render min 5.8: shell_nav=2
- `/erp/as` (pc) Δ108, render min 16.6: row_display=22; list_query=18; tab_counts=17; rd_loop=12; rd_timeline=10; rd_attach_q=2; rd_normalize=2; rd_drift=2; shell_nav=2
- `/erp/construction/dashboard` (pc) Δ92, render min 8.2: list_query=34; mobile_enrich=5; row_dtos=4; summary_slice=3; attachment_slice=3; shell_nav=2
  - DASH-SLICES: ['summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0']
- `/admin/naver-ingest/triage` (pc) Δ657, render min 625.0: wb_work_groups=472; wg_sibling=172; wg_fetch=148; wg_group_queue=108; wb_ghosts=68; wb_pane_ctx=26; wb_template=24; work_rows=19; wb_refresh=16; wb_bulk_dispatch=12; wg_orders=4; wb_origin_cleanup=4; wb_failures=3; wb_partial_claims=2; shell_nav=2; wg_row_view=1; wb_head_region=1
- `/admin/naver-ingest/triage?tab=all` (pc) Δ586, render min 558.9: wb_work_groups=550; wg_sibling=242; wg_fetch=146; wg_group_queue=106; wb_history=58; wb_pane_ctx=26; wb_refresh=16; wb_template=10; hist_rows=4; wg_orders=4; wb_failures=2; shell_nav=2; wg_row_view=1
- `/erp/dashboard` (mobile) Δ98, render min 11.8: row_dtos=6; shell_nav=2
- `/erp/dashboard?view=fragment` (mobile) Δ87, render min 10.4: row_dtos=5
- `/erp/production/dashboard` (mobile) Δ93, render min 17.8: shell_nav=2
- `/erp/construction/dashboard` (mobile) Δ89, render min 17.8: list_query=32; mobile_enrich=4; summary_slice=3; attachment_slice=3; row_dtos=3; shell_nav=2
  - DASH-SLICES: ['summary_counts=miss:16;attachment_counts=miss:4', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0', 'summary_counts=hit:0;attachment_counts=hit:0']
- `/erp/as` (mobile) Δ114, render min 25.3: row_display=22; list_query=18; tab_counts=15; rd_loop=12; rd_timeline=10; rd_attach_q=3; rd_normalize=2; rd_drift=2; shell_nav=2

## 7. 원인 후보와 개선안 (수정하지 않음 — 위치만)

| # | 대상(경로:행) | 근거(실측) | 개선안 | 예상 효과(추정) | 위험 | 난이도 |
|---|---|---|---|---|---|---|
| 1 | `foms/web/admin/naver_ingest.py:2509-2510` — 이력 탭에서도 `_work_groups(display=True)` 전체 계산 | tab=all `wb_work_groups`=550 / render 559 | 이력 탭은 목록·칩을 안 그린다(`templates/admin/naver_workbench.html:775` `{% if active_tab == 'work' %}`). 탭 배지 수는 nav 배지와 같은 정의라 `get_triage_pending_count(db, workbench=True)`(30s 캐시) 재사용 | 이력 탭 render 559 → 약 100~150ms | `_pane_context(..., visible=visible)`(2558) 가 visible 에 의존 — 이력 탭 pane 동작 확인 필요. 배지 30s 지연 허용 여부 | 중 |
| 2 | `naver_ingest.py:3586-3587` → `_build_sibling_index` `3902`, 조회 `3924-3928` | `wg_sibling` 172~242 (09-11: 110~133) | 형제 조회가 `wg_fetch` 로 이미 읽은 행까지 JSONB 통째로 다시 읽는다(`display=True` = ORM 전체 컬럼). 이미 가진 id 는 제외하고 합치거나, 형제 판정에 필요한 열만 projection | `wg_sibling` 절반 이하(추정) | display 두 모드 동치 계약(3563 docstring·회귀 테스트) 유지 필요 | 중 |
| 3 | `foms/services/integrations/naver_commerce/triage_count.py:29,33,134` + `static/js/foms/foms-nav-triage-badge.js:45,64-67` | 배지 콜드 674~757ms, 웜 ~120 | 캐시를 프로세스 메모리 → Redis(공유)로, 링크 변경 시 무효화. 혹은 TTL 연장 | 워커 2개 → miss 절반 이하, gevent 워커가 ~0.6s 묶이는 빈도 감소 | 배지 신선도. CPU 구간이 gevent 루프를 막는다는 가설은 **미검증** | 하~중 |
| 4 | `foms/web/measurement/dashboard.py:257-266` (`_panel_fp` 의 `"selected_date"`) | 새 날짜칩 콜드 801~886ms vs 웜 ~165 | 패널 창은 오늘~+14일로 날짜와 무관(`foms/services/measurement_dashboard_filters.py:86-87`), `selected_date` 는 `is_selected` 표시에만 쓰인다(`foms/services/measurement_read_model.py:355`). 키에서 빼고 표시만 캐시 밖에서 칠한다 | 패널 slice miss 제거. main_rows(297)·product_items(373) 는 여전히 날짜별 miss라 **감소 폭은 계측 후 판정** | 낮음 | 하 |
| 5 | `foms/services/settlement_aggregation.py:528-538`, `foms/services/settlement_rows.py:384-386` | aggregates Δ228, rows Δ202 (rows 는 med 394) | 모집단 전량 `structured_data` 로드 후 파이썬 기간 필터·페이지. 기간 술어를 SQL(평면 날짜 열)로, JSONB 는 필요한 경로만 projection | 50~70% 감소(추정), 데이터 증가에 둔감해짐 | 정산 날짜가 JSONB 파생 — 술어 동치 증명 필요 | 중 |
| 6 | `foms/web/orders/trash.py:264-276` | Δ130, med 333 | 삭제 주문 전량 ORM `.all()`(페이지 없음) → 페이지네이션 + `load_only` | Δ 대부분 제거(추정) | 낮음(ADMIN/MANAGER 전용) | 하 |
| 7 | `foms/web/measurement/dashboard.py:816-999` `/metropolitan_dashboard` | Δ170 | 전체 ORM 쿼리 7벌 + 파이썬 날짜 필터. nav 링크를 못 찾음(템플릿 자기 자신만) — 사용 여부 확인 후 은퇴 검토 | 사용 안 하면 0 | 낮음 | 하 |
| 8 | 계측 공백: `foms/web/orders/dashboard.py:175,179,202,332,367,381`(`_t0`=433 앞 구간), `foms/web/measurement/dashboard.py:178~556`, `foms/web/drawing/workbench.py:565~999`, `foms/web/cs/completion_dashboard.py:537` | 대시보드 Δ103 중 render 12 + row_dtos 5 만 보임 | `phase()` + `apply_ept_b7_render_headers` + `format_slice_observations()`(DASH-SLICES) 배선 | 속도 효과 0, 대신 위 2·4번과 07-05 대비 증가분 판정 가능 | 없음 | 하 |

## 8. 측정 못 한 것과 이유

- production: 지시상 로그인 금지.
- 쓰기(POST/PUT/DELETE) 전부: 금지. 따라서 저장·전이·업로드 응답 시간은 없음.
- `/admin/test-r2`: R2 연결 테스트(외부 호출·객체 작업 가능성) — 부작용 우려로 제외.
- `/login`·`/register`·`/password-reset/request`: 비로그인 화면(로그인 세션에선 리다이렉트) — 생략.
- `/s/<token>`·`/w/<token>`·`/channel/wam/`·`/api/files/*`·`/api/chat/download|preview`: 토큰 필요 또는 접근 로그 쓰기·R2 프록시 — 제외.
- `*.csv` export, `/api/generate_map`, `/admin/ops/approvals/<id>`, `/admin/users/edit/<id>`: 무거운 다운로드·대상 id 없음 — 제외.
- coarse(태블릿) 페르소나 전체 페이지: 게이트 coarse 패스가 바이트만 본다. 이번엔 모바일 9경로만.
- 동시 부하: 직렬 측정이라 경합(gevent 루프 블로킹 가설) 미측정.
- 계측 없는 85경로의 r1 스파이크(예 `/` 987ms)는 Jinja 첫 컴파일인지 캐시 miss 인지 분리 불가.
- 대표 주문은 1건(4385, AS 4388, 생산 4069, 네이버 링크 2804) — 주문 크기에 따른 편차는 미측정.
