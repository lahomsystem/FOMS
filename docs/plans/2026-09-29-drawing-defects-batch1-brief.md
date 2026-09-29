# 도면 결함 1차 묶음 브리프 (2026-09-29, 초안 — CEO 없이 총괄이 씀, 워커가 근거로 반박 가능)

근거 원장: `docs/plans/2026-09-29-drawing-defects-verification-ledger.md` (C8·C8-X·C8(a)·C8(b)·C9·M6·M8·M11·M12·M15).
워크트리: `c:/tmp/foms-s-s0929-115959` (branch `session/s0929-115959`, base origin/deploy `2cea0bf91`).

## 사용자 결정 (2026-09-29, 이 세션)
- **확정할 때 파일을 지우지 않는다.** 첨부 탭 '도면' 업로드도, 교체된 옛 도면도, 수정요청 참고사진도 남긴다. 확정은 `drawing_current_files`(현재 도면 목록)와 `CONFIRM_RECEIPT.files` 만 정한다.
- 1차 묶음 = 설계서 없이 고칠 것: C8 계열 + C8-X + C9 계열(M11·M12 포함). C21·M1·M5·M10·M2·M3·M16 은 2차(설계서) — 이번에 손대지 않는다.

## W1 — 서버: 확정 정리 · 옛 도면 부활 · 고객 링크
1. **C8 (+C8(a)·C8(b)·M6·M8·M15)**: `foms/services/drawing_confirm_cleanup.py` `finalize_drawing_files_on_confirm` 가 스토리지 삭제·OrderAttachment 행 삭제를 **하지 않게** 한다. 반환 튜플 모양(`final_files, deleted_count`)을 호출자(`foms/api/drawing/erp_orders_draftsman.py:431`)가 어떻게 쓰는지 보고, 호출자 수정 없이 끝나는 쪽을 우선(이 파일 494줄 — 500 래칫 6줄 여유, 가능하면 건드리지 말 것). 더 이상 안 쓰는 삭제 함수(`collect_obsolete_drawing_keys`, `delete_drawing_storage_keys`)는 다른 호출자가 없으면 지우고, 있으면 남긴다(grep 전수). failopen 인벤토리(`docs/harness/foms_failopen_inventory.json`, `tests/domains/test_failopen_inventory.py:47 _SWALLOW_BASELINE`)에 `drawing_confirm_cleanup.py:225·240` 항목이 있다 — 지우면 인벤토리·기준값이 바뀐다. `python tools/harness/refresh_inventories.py` 와 해당 테스트로 맞춰라(기준값은 다른 창도 고치는 한 줄 — 바뀐 숫자를 보고에 적어라).
2. **C8-X**: 확정 때 현재본을 이력에서 **다시 계산**하는 `resolve_final_drawing_files`/`apply_transfer_to_drawing_files` 가 전달 API(`foms/api/drawing/erp_orders_drawing.py:140-256`, 특히 대상 없는 재전달 = 1장이면 교체 :176-180, 기록은 mode='REPLACE' 대상 None :238-241)와 다르게 해석해 옛 도면을 되살린다. 근본 원인을 없애라: 후보 ① 확정은 전달 때 이미 맞게 갱신된 `drawing_current_files` 를 그대로 최종본으로 쓴다(재계산 제거 — 왜 재계산이 들어왔는지 git log -S 로 근거 확인, 옛 데이터 보정 목적이면 그 경우를 테스트로 남겨라) ② 재계산 규칙을 전달 API 와 한 함수로 공유. 근거와 함께 고르고 보고. `foms/web/production/dashboard.py:405-425` 생산 시트 썸네일도 같은 함수를 쓴다 — 결과가 같아지게.
3. **고객 링크(필수 동반 수정)**: `foms/api/share.py:172-214 _collect_drawing_files` 는 도면 첨부 전체 + 현재본을 합친다. 지금까지는 확정 때 옛 도면을 지워서 확정 뒤 링크엔 최종본만 남았다 — 1번을 하면 옛 도면이 고객에게 영원히 보인다. **교체된 옛 도면(전달 이력의 TRANSFER files·previous_current_files 에 있었지만 지금 `drawing_current_files` 에 없는 키)은 고객 링크·ZIP·합본 PNG(같은 수집 함수, :522·:731)에서 뺀다.** 전달 이력에 한 번도 안 오른 첨부 탭 '도면' 업로드는 지금처럼 보인다. 이 규칙으로 확정 전 "1차·2차 섞여 보임"(호환 점검표 C2)도 함께 풀린다 — 테스트로 고정.
4. **category='drawing' 첨부를 읽는 다른 곳 전수**(grep `category == 'drawing'`, `category='drawing'`, `"drawing"` 필터): 확정 뒤 옛 도면 행이 남으면서 화면이 바뀌는 곳을 표로 보고(파일:행, 지금 보이는 것, 바뀐 뒤 보이는 것, 고객·생산·시공에게 보이는지). 고객·생산·시공 쪽에 옛 도면이 새로 보이게 되는 곳은 3번과 같은 규칙으로 막는다. 내부 이력 화면(ERP 첨부 탭 등)은 남아 보여도 된다 — 다만 목록이 늘어나는 것을 보고.
5. **테스트**: `tests/domains/test_bugrepro_c8_confirm_cleanup_revision_files.py` 6개를 회귀 테스트로 전환(파일명 `tests/domains/test_drawing_confirm_keeps_files.py` 로 바꾸고 docstring 정리; 단언 뜻이 새 정책과 맞게 — "지우지 않는다"). 기존 `tests/domains/test_drawing_confirm_cleanup.py` 중 삭제를 단언하던 테스트는 새 정책에 맞게 고치고 이유를 docstring 에. 고객 링크 새 규칙 테스트 추가(재전달 뒤 확정 전·확정 뒤 모두 옛 도면 안 보임, 첨부 탭 업로드는 보임, 다른 주문 키 안 보임).
- 편집 허용: `foms/services/drawing_confirm_cleanup.py`, `foms/api/share.py`, `foms/web/production/dashboard.py`(썸네일 줄만), `foms/api/drawing/erp_orders_draftsman.py`(꼭 필요할 때만), 4번에서 막아야 하는 서버 파일, 위 테스트 파일들, `docs/harness/foms_failopen_inventory.json`·`tests/domains/test_failopen_inventory.py` 기준값 한 줄, `refresh_inventories.py` 가 바꾸는 인벤토리 json.

## W2 — 화면: 도면팀 폰 막힘 · 모바일 참고사진 · 전달 취소 노출
1. **C9**: `templates/drawing/partials/workbench_mobile_handoff.html` 의 REQUEST_REVISION 말풍선(스레드 :173-210)에 **반영 완료 체크 버튼**(기존 API `POST /api/orders/<id>/request-revision-check`, `foms/api/drawing/erp_orders_revision.py:414-498` — 요청 본문·요청 식별 방법을 코드로 확인, PC 토글 `workbench_detail_body.html:1400-1410` 과 그 JS 와 같은 계약). 체크 권한 = `can_toggle_revision_check`(workbench.py:953). 체크하면 화면이 갱신되어 막힘이 풀린다(모바일 바 "전달 대기" → "수정본 전달"). 새 엔드포인트 금지.
   - 모바일 바가 막혔을 때 "전달 대기" 아래에 **이유 한 줄**("수정요청 N건 중 M건 반영 체크 필요" 같은 뜻, PC :1479-1484 문구와 맞춤).
2. **M12**: 모바일 스레드에서 수정요청 참고사진을 볼 수 있게(지금 "첨부 N건" 글자뿐, handoff:190). URL 은 이력에 저장된 `view_url` 을 쓰지 말고(무검증 — 2차 M5), **서버가 key 로 만든다**. key 는 `orders/<이 주문 id>/drawing_gateway/` 로 시작하는 것만(다른 key 는 링크 없이 개수만). 파일 보기 라우트의 권한 검사를 확인하고 그 라우트로 연결. 이미지면 작은 썸네일 + 눌러서 크게(GlobalImageViewer 가 있으면 그것).
3. **M11**: '전달 취소' 버튼은 `drawing_status == 'TRANSFERRED'` 일 때만(모바일 handoff:242 는 지금 `!= 'CONFIRMED'`, PC workbench_detail_body.html:1497 은 조건 없음, 서버는 TRANSFERRED 만 허용). 권한 플래그 `can_cancel_transfer`(workbench.py:958-981)에 상태 조건을 넣는 쪽이 한 곳 수정이면 그쪽.
4. **테스트**: `tests/domains/test_bugrepro_c9_drawing_mobile_returned_blocked.py` 를 회귀 테스트로 전환(파일명 `tests/domains/test_drawing_mobile_revision_check.py`, 반박 검증 지적: 전제가 지금 막기 정책을 단언하는 부분은 그대로 두되, "체크 → 전달 가능" 을 끝까지 한 번 밟아라). M11·M12 회귀 테스트 추가(참고 프로브: 저장소 밖 `C:\Users\USER\AppData\Local\Temp\claude\c--DEV-FOMS\a6062928-159f-4527-bec0-97454177ee8e\scratchpad\omis\test_omis_probe.py` :231·:249 — 읽고 저장소 규약에 맞게 새로 써라).
- 모바일 상세 계약: `tests/domains/test_drawing_mobile_back_to_workbench.py:35 DETAIL_TOP_BLOCKS=5` — 새 최상위 section·details 를 만들지 말고 기존 말풍선 안에 넣어라.
- 자산 핀: CSS 를 바꾸면 `foms-drawing-mobile.css` 핀을 `20260929b` 로(오늘 a 사용). 핀은 `foms-mobile-surfaces.css:24` @import, `templates/orders/share_view.html:12`, `templates/orders/share_bundle_view.html:12` 세 곳 + 부모 번들 `templates/partials/shared/layout_head.html` 의 `foms-mobile-surfaces.css?v=` 도 올리고, `grep -rn "20260929a" tests/ templates/ static/` 로 복제 단언 테스트까지 갱신(`test_drawing_mobile_asset_pin_freshness.py` 의 ASSET_PIN_LOCK 포함). JS 를 바꾸면 `drawing-handoff.js?v=` (workbench_detail_body.html:3023) 핀도 올리고 `node --check`. 인라인 style= 금지(ratchet).
- 편집 허용: `templates/drawing/partials/workbench_mobile_handoff.html`, `foms/web/drawing/workbench.py`, `templates/drawing/partials/workbench_detail_body.html`(전달 취소 조건·JS 핀 줄만), `static/js/foms/drawing-handoff.js`, `static/css/components/foms-drawing-mobile.css` + 위 핀 파일들·핀 테스트, 위 테스트 파일들.

## 공통
- 모든 Bash 는 `cd /c/tmp/foms-s-s0929-115959 && ...`. git 쓰기 명령 금지. 메인 트리 금지. CRLF/LF 원래대로(Edit 도구 사용). 운영 접속 금지.
- 서로 소유권 밖 파일 편집 금지. 같은 트리에서 동시에 일한다 — pytest 는 자기 테스트 위주로, 남의 테스트가 잠깐 빨개도 손대지 마라.
- 게이트 exit 는 `; echo EXIT=$?`. 앱 확인 `python -c "import app; print('APP_OK')"`.
- `tests/domains/test_bugrepro_c21_confirm_quest_while_returned.py` 는 2차 몫 — 건드리지 마라(통합 단계에서 strict xfail 로 바꾼다).
