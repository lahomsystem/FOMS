/** API가 HTML(401/404/500)을 돌려주면 r.json()이 SyntaxError를 던짐. JSON일 때만 파싱 */
        async function safeJsonFetch(url, fallback) {
          const r = await fetch(url);
          const ct = r.headers.get('content-type') || '';
          if (!r.ok || !ct.includes('application/json')) {
            if (!r.ok) console.warn('Order detail API non-OK:', url, r.status);
            return fallback;
          }
          try {
            return await r.json();
          } catch (e) {
            console.error('JSON parse error for', url, e);
            return fallback;
          }
        }

        var __orderDetailPayloadCache = {};

        function getPreloadedOrderDetailPayload(orderId) {
          if (__orderDetailPayloadCache[orderId]) {
            return __orderDetailPayloadCache[orderId];
          }

          const payloadEl = document.getElementById(`order-detail-preload-${orderId}`);
          if (!payloadEl) {
            return null;
          }

          try {
            const payload = JSON.parse(payloadEl.textContent || '{}');
            __orderDetailPayloadCache[orderId] = payload;
            return payload;
          } catch (e) {
            console.warn('Order detail preload parse error:', orderId, e);
            return null;
          }
        }

        async function loadOrderDetail(orderId) {
          const container = document.getElementById(`order-detail-content-${orderId}`);
          if (!container) return;
          /** 2단 첨부까지 반영 완료 */
          if (container.dataset.loaded === '1') return;
          /** 1단 셸만 있고 첨부 API 진행 중이면 중복 페인트 방지 */
          if (container.dataset.shellLoaded === '1' && container.dataset.attachPhase === 'loading') return;
          /** 셸은 이미 있고 첨부만 에러 상태 → 셸/폼 상태를 보존한 채 첨부만 재시도 */
          if (container.dataset.shellLoaded === '1' && container.dataset.attachPhase === 'error') {
            const retryGen = (__orderDetailLoadGen[orderId] || 0) + 1;
            __orderDetailLoadGen[orderId] = retryGen;
            try {
              performance.mark('erp-detail-load-start:' + orderId);
              // 재시도 시 셸은 이미 렌더된 상태이므로 동일 시점 mark 로 shell-time 기준을 맞춘다.
              performance.mark('erp-detail-shell:' + orderId);
            } catch (e) {}
            container.dataset.attachPhase = 'loading';
            delete container.dataset.attachError;
            const itemCountStr = container.dataset.itemCount || '0';
            await patchOrderDetailAttachments(orderId, Number(itemCountStr), retryGen);
            return;
          }

          /** 가드 통과 후에만 세대 번호 증가: early return 경로는 건드리지 않음 */
          const gen = (__orderDetailLoadGen[orderId] || 0) + 1;
          __orderDetailLoadGen[orderId] = gen;
          try { performance.mark('erp-detail-load-start:' + orderId); } catch (e) {}

          try {
            const preloaded = getPreloadedOrderDetailPayload(orderId);
            let structured = null;
            /** true면 2단에서 GET /attachments 로 패치 */
            let attachmentsPending = true;
            let preloadedAttachmentsPayload = null;

            if (preloaded && preloaded.success) {
              structured = preloaded;
              if (preloaded.attachments !== undefined) {
                attachmentsPending = false;
                preloadedAttachmentsPayload = preloaded.attachments;
              }
            } else {
              container.innerHTML = '<div class="text-muted small">로딩 중...</div>';
              structured = await safeJsonFetch(`/api/orders/${orderId}/structured`, { success: false, structured_data: {} });
            }

            if (!structured || !structured.success) {
              container.innerHTML = '<div class="text-danger small">상세 정보를 불러올 수 없습니다. 새로고침 후 다시 시도하세요.</div>';
              return;
            }

            const sd = (structured && structured.structured_data) || {};
            const customer = (((sd.parties || {}).customer || {}).name) || '-';
            const orderer = (((sd.parties || {}).orderer || {}).name) || '-';
            const phone = (((sd.parties || {}).customer || {}).phone) || '-';
            // 주소: address_full 우선, 없으면 address_main + address_detail 조합, 없으면 address_main만
            const site = sd.site || {};
            const addressFull = site.address_full || '';
            const addressMain = site.address_main || '';
            const addressDetail = site.address_detail || '';
            const address = addressFull || (addressMain && addressDetail ? `${addressMain} ${addressDetail}`.trim() : addressMain) || addressDetail || '-';
            // 특이사항: notes 객체에서 읽기 (erpbeta 저장 경로와 일치)
            const notes = sd.notes || {};
            const addressNote = (notes.address_note || '').trim();
            const phoneNote = (notes.phone_note || '').trim();
            const measureNote = (notes.measurement_note || '').trim();
            const measure = formatScheduleDateTimeDisplay(
              (((sd.schedule || {}).measurement || {}).date) || '',
              (((sd.schedule || {}).measurement || {}).time) || ''
            );
            const construct = formatScheduleDateTimeDisplay(
              (((sd.schedule || {}).construction || {}).date) || '',
              (((sd.schedule || {}).construction || {}).time) || ''
            );
            const manager = (((sd.parties || {}).manager || {}).name) || '-';
            const stage = (((sd.workflow || {}).stage)) || '-';
            const urgent = ((sd.flags || {}).urgent) || false;
            __drawingCurrentFilesByOrder[orderId] = Array.isArray(sd.drawing_current_files) ? sd.drawing_current_files : [];

            // 담당팀: 현재 단계의 담당팀으로 자동 계산
            const STAGE_TO_TEAM = {
              'RECEIVED': 'CS',
              'MEASURE': 'SALES',
              'DRAWING': 'DRAWING',
              'CONFIRM': 'SALES',
              'PRODUCTION': 'PRODUCTION',
              'CONSTRUCTION': 'CONSTRUCTION',
              'CS': 'CS',
              'COMPLETED': 'CS',
              'AS': 'CS'
            };
            let ownerTeam = STAGE_TO_TEAM[stage] || '-';
            // 실측/고객컨펌에서 발주사에 '라홈' 포함 시 라홈팀(CS)으로 변경
            if (stage === 'MEASURE' || stage === 'CONFIRM') {
              const ordererName = (((sd.parties || {}).orderer || {}).name || '').trim();
              if (ordererName && ordererName.includes('라홈')) {
                ownerTeam = 'CS';
              }
            }

            // 첨부: 2단에서 채움. 프리로드에 attachments 가 있으면 즉시 파싱
            let aList = [];
            if (!attachmentsPending && preloadedAttachmentsPayload !== null) {
              aList = parseAttachmentsPayload(
                Array.isArray(preloadedAttachmentsPayload)
                  ? { success: true, attachments: preloadedAttachmentsPayload }
                  : preloadedAttachmentsPayload
              );
            }
            __attachmentsCache[orderId] = attachmentsPending ? [] : aList;
            if (!attachmentsPending) __attachmentsCacheAt[orderId] = Date.now();

            // 제품 항목: dw-product-main-card 구조 (헤더 + 폼 + 첨부 패널)
            const items = (sd.items || []) || [];
            let itemsHtml = '';
            const safeValue = (val) => {
              if (val === null || val === undefined || val === '') return '';
              return String(val).trim();
            };
            if (items.length > 0) {
              if (typeof __orderDetailImageGroups === 'undefined') window.__orderDetailImageGroups = {};
              __orderDetailImageGroups[orderId] = [];
              let gridHtml = '<div class="mt-3">';
              items.forEach((item, idx) => {
                let specW = item.spec_width || '';
                let specD = item.spec_depth || '';
                let specH = item.spec_height || '';
                if (!specW && !specD && !specH && item.spec) {
                  const specStr = String(item.spec || '').trim();
                  const parts = specStr.split(/[xX*×]/).map(s => s.trim());
                  if (parts.length >= 3) { specW = parts[0]; specD = parts[1]; specH = parts[2]; }
                  else if (parts.length === 2) { specW = parts[0]; specD = parts[1]; }
                  else if (parts.length === 1) { specW = parts[0]; }
                }
                const priceVal = item.price != null && item.price !== '' ? (Number(item.price) ? Number(item.price).toLocaleString('ko-KR') : String(item.price)) : '';
                const productName = escapeHtml(safeValue(item.product_name || item.name) || '-');
                const itemAtts = aList.filter(a => Number(a.item_index) === idx);
                let attachPanelHtml;
                if (attachmentsPending) {
                  __orderDetailImageGroups[orderId][idx] = [];
                  attachPanelHtml = '<div class="dw-attach-panel dw-attach-panel--loading" id="order-detail-item-attach-' + orderId + '-' + idx + '"><div class="small fw-semibold text-muted mb-2"><i class="fas fa-image"></i> 실측 첨부 파일</div><div class="text-muted small py-1"><span class="spinner-border spinner-border-sm me-1" role="status"></span><span class="visually-hidden">불러오는 중</span>불러오는 중…</div></div>';
                } else {
                  const imageAtts = itemAtts.filter(orderDetailIsImageFile);
                  __orderDetailImageGroups[orderId][idx] = imageAtts;
                  attachPanelHtml = buildDwAttachPanelHtml(orderId, idx, itemAtts);
                }

                gridHtml += `
            <div class="dw-product-main-card">
              <div class="dw-product-main-head">
                <div class="dw-product-main-name">${productName}</div>
                <div class="d-flex align-items-center gap-1">
                  <span class="badge bg-light text-dark border">항목 ${idx + 1}</span>
                </div>
              </div>
              <div class="dw-product-split">
                <div class="dw-product-info-form">
                  <div class="row g-2">
                    <div class="col-12">
                      <label class="form-label mb-1 small text-primary">제품명</label>
                      <input class="form-control form-control-sm" value="${productName}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-3">
                      <label class="form-label mb-1 small text-primary">규격 W(폭)</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(specW) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-3">
                      <label class="form-label mb-1 small text-primary">규격 D(깊이)</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(specD) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-3">
                      <label class="form-label mb-1 small text-primary">규격 H(높이)</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(specH) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-6">
                      <label class="form-label mb-1 small text-primary">내부</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.internal) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-6">
                      <label class="form-label mb-1 small text-primary">색상</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.color) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-6">
                      <label class="form-label mb-1 small text-primary">옵션</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.option_detail || item.options) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-6">
                      <label class="form-label mb-1 small text-primary">손잡이</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.handle) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-6">
                      <label class="form-label mb-1 small text-primary">기타 / 설치위치</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.misc) || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-md-6">
                      <label class="form-label mb-1 small text-primary">항목 금액(원)</label>
                      <input class="form-control form-control-sm" value="${escapeHtml(priceVal || '-')}" readonly title="클릭하면 값이 복사됩니다.">
                    </div>
                    <div class="col-12">
                      <label class="form-label mb-1 small text-primary">추가 입력</label>
                      <textarea class="form-control form-control-sm" rows="3" readonly title="클릭하면 값이 복사됩니다.">${escapeHtml(safeValue(item.extra_input))}</textarea>
                    </div>
                  </div>
                  <div class="d-flex flex-column align-items-end gap-2 mt-2 erp-amount-block">
                    <div class="d-flex justify-content-between justify-content-md-end align-items-center gap-2 w-100" style="max-width: 16rem;">
                      <span class="fw-bold text-nowrap">출고가</span>
                      <div class="badge bg-primary text-end erp-amount-value" id="erp-items-total-${orderId}-${idx}">0원</div>
                    </div>
                    <div id="erp-deposit-section-${orderId}-${idx}" class="d-flex justify-content-between justify-content-md-end align-items-center gap-2 w-100" style="max-width: 16rem;">
                      <label for="erp-deposit-amount-${orderId}-${idx}" class="form-label mb-0 fw-bold text-nowrap">예약금(선금)</label>
                      <input type="text" id="erp-deposit-amount-${orderId}-${idx}" inputmode="numeric" placeholder="0원" maxlength="24" readonly class="erp-amount-value erp-amount-value--deposit" title="숫자 입력 시 1,000단위 쉼표가 적용됩니다.">
                    </div>
                    <div id="erp-discount-section-${orderId}-${idx}" class="d-flex justify-content-between justify-content-md-end align-items-center gap-2 w-100" style="max-width: 16rem; display: none;">
                      <label for="erp-discount-amount-${orderId}-${idx}" class="form-label mb-0 fw-bold text-nowrap">할인</label>
                      <input type="text" id="erp-discount-amount-${orderId}-${idx}" inputmode="numeric" placeholder="0원" maxlength="24" readonly class="erp-amount-value erp-amount-value--discount" title="숫자 입력 시 1,000단위 쉼표가 적용됩니다.">
                    </div>
                    <div id="erp-remaining-section-${orderId}-${idx}" class="d-flex justify-content-between justify-content-md-end align-items-center gap-2 w-100" style="max-width: 16rem; display: none;">
                      <label class="form-label mb-0 fw-bold text-nowrap">잔금</label>
                      <div class="erp-amount-value erp-amount-value--balance text-end" id="erp-remaining-amount-${orderId}-${idx}">0원</div>
                    </div>
                  </div>
                </div>
                ${attachPanelHtml}
              </div>
            </div>`;
              });
              gridHtml += '</div>';
              itemsHtml = gridHtml;
            } else {
              itemsHtml = '<div class="text-muted mt-3" style="font-size: 1rem;">제품 항목 없음</div>';
            }

            let attachmentsHtml = '';
            if (attachmentsPending) {
              attachmentsHtml = '<div class="order-detail-attach-loading gap-2 text-muted small py-2"><span class="spinner-border spinner-border-sm" role="status"></span><span class="visually-hidden">불러오는 중</span>불러오는 중…</div>';
            } else if (aList.length > 0) {
              attachmentsHtml = buildMainAttachThumbsHtml(orderId, aList);
            } else {
              attachmentsHtml = '<div class="text-muted small mt-2">첨부 없음</div>';
            }

            // 모바일 여부 확인 (992px 이하)
            const isMobile = window.innerWidth <= 992;

            const basicInfoHtml = isMobile ? '' : `
            <div class="col-md-6">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title fw-bold"><i class="fas fa-info-circle text-primary"></i> 기본 정보</h5>
                  <div class="erp-detail-text">
                    <div class="mb-3"><strong class="erp-detail-label">고객명:</strong> <span class="erp-detail-value">${escapeHtml(customer)}</span></div>
                    <div class="mb-3"><strong class="erp-detail-label">발주사:</strong> <span class="erp-detail-value">${escapeHtml(orderer)}</span></div>
                    <div class="mb-3"><strong class="erp-detail-label">연락처:</strong> <span class="erp-detail-value">${escapeHtml(phone)}</span></div>
                    <div class="mb-3"><strong class="erp-detail-label">주소:</strong> <span class="erp-detail-value">${escapeHtml(address)}</span></div>
                  </div>
                </div>
              </div>
            </div>`;

            const notesHtml = [
              phoneNote && `<div class="mb-3"><strong class="erp-detail-label">연락특이:</strong> <span class="erp-detail-value">${escapeHtml(phoneNote)}</span></div>`,
              addressNote && `<div class="mb-3"><strong class="erp-detail-label">주소특이:</strong> <span class="erp-detail-value">${escapeHtml(addressNote)}</span></div>`,
              measureNote && `<div class="mb-3"><strong class="erp-detail-label">실측특이:</strong> <span class="erp-detail-value">${escapeHtml(measureNote)}</span></div>`
            ].filter(Boolean).join('');

            const scheduleHtml = `
            <div class="${isMobile ? 'col-12' : 'col-md-6'}">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title fw-bold"><i class="fas fa-calendar text-primary"></i> 일정 및 특이사항</h5>
                  <div class="erp-detail-text">
                    ${isMobile ? '' : `<div class="mb-3"><strong class="erp-detail-label">실측일:</strong> <span class="erp-detail-value">${escapeHtml(measure)}</span></div>
                    <div class="mb-3"><strong class="erp-detail-label">시공일:</strong> <span class="erp-detail-value">${escapeHtml(construct)}</span></div>`}
                    ${notesHtml}
                  </div>
                </div>
              </div>
            </div>`;

            const roleAssigneesHtml = buildOrderRoleAssigneesHtml(
              resolveOrderRoleAssignees(structured, preloaded)
            );

            // 도면 전달 버튼 (DRAWING 단계일 때만)
            let actionHtml = '';
            if (stage === 'DRAWING') {
              const canEdit = typeof CAN_EDIT_ERP !== 'undefined' && CAN_EDIT_ERP;
              const drawingStatus = sd.drawing_status || 'PENDING'; // PENDING, TRANSFERRED, CONFIRMED
              const assignees = Array.isArray(sd.drawing_assignees) ? sd.drawing_assignees : [];
              const assignments = sd.assignments || {};
              const assigneeIds = Array.isArray(assignments.drawing_assignee_user_ids)
                ? assignments.drawing_assignee_user_ids.map(x => Number(x)).filter(x => Number.isFinite(x))
                : [];
              const hasAssignee = assignees.length > 0 || assigneeIds.length > 0;
              const myIdNum = Number(MY_ID);
              const isAssigned = assignees.some(u => Number(u.id) === myIdNum) || assigneeIds.includes(myIdNum);
              const isDrawingTeam = (MY_TEAM === 'DRAWING');
              const isSalesTeam = (MY_TEAM === 'SALES');
              // Manager matches current user name? or admin
              const isManager = (manager === MY_NAME);
              const isAdmin = (MY_ROLE === 'ADMIN');
              const canDrawingAssign = canEdit || isDrawingTeam || isAdmin;
              const canDrawingWork = (isDrawingTeam || isAssigned || isAdmin) && hasAssignee;
              const canToggleRevisionCheck = isDrawingTeam || isAssigned || isAdmin;

              const assigneeNames = assignees.map(u => u.name).filter(Boolean).join(', ') || (assigneeIds.length ? `${assigneeIds.length}명 지정` : '');

              const drawHistory = Array.isArray(sd.drawing_transfer_history) ? sd.drawing_transfer_history : [];
              const revisionRequests = drawHistory
                .filter(h => h && h.action === 'REQUEST_REVISION')
                .slice()
                .reverse();
              const uncheckedRequestCount = revisionRequests.filter((h) => {
                const rc = (h && h.review_check && typeof h.review_check === 'object') ? h.review_check : {};
                return !rc.checked;
              }).length;

              // 1. 도면 담당자 지정 버튼 (수정 권한 + 영업/담당자/관리자/도면팀)
              let assignBtn = '';

              if (canDrawingAssign && (isSalesTeam || isManager || isAdmin || isDrawingTeam)) {
                assignBtn = '<button class="btn btn-outline-primary btn-sm" onclick="openDraftsmanAssignModal(' + orderId + ')"><i class="fas fa-user-plus"></' + 'i> 담당자 지정</' + 'button>';
              }

              let statusBadge = '';
              let mainBtn = '';


              // --- [수정] 상태별 버튼 로직 강화 ---

              if (drawingStatus === 'TRANSFERRED') {
                statusBadge = '<span class="badge bg-warning text-dark ms-2">확정 대기중</span>';
                if (canEdit && (isSalesTeam || isManager || isAdmin)) {
                  mainBtn = '<div class="d-flex gap-2"><button class="btn btn-success flex-grow-1" onclick="confirmDrawingReceipt(' + orderId + ')"><i class="fas fa-check-double"></' + 'i> 수령 확정</' + 'button><button class="btn btn-warning" onclick="openRevisionRequestModal(' + orderId + ')"><i class="fas fa-undo"></' + 'i> 수정 요청</' + 'button></div>';
                } else {
                  if (canDrawingWork) {
                    mainBtn = '<div class="d-flex gap-2"><button class="btn btn-primary flex-grow-1" onclick="openTransferDrawingModal(' + orderId + ', true)"><i class="fas fa-sync"></' + 'i> 재전송</' + 'button><button class="btn btn-outline-danger" onclick="cancelDrawingTransfer(' + orderId + ')"><i class="fas fa-times"></' + 'i> 전달 취소</' + 'button></div><div class="text-muted small mt-1"><i class="fas fa-info-circle"></' + 'i> 재전송 시 <span class="text-danger fw-bold">기존 파일이 삭제</span>되고 새 파일로 대체됩니다.</div>';
                  } else {
                    mainBtn = '<button class="btn btn-secondary" disabled>확정 대기중</button>';
                  }
                }
              } else if (drawingStatus === 'RETURNED') {
                statusBadge = '<span class="badge bg-danger ms-2">수정 요청됨</span>';
                // 수정 요청 상태: 미반영 요청이 없을 때만 수정본 전달 가능
                if (canDrawingWork) {
                  if (uncheckedRequestCount > 0) {
                    mainBtn = '<button class="btn btn-primary" disabled title="요청사항에서 모든 수정 요청을 반영 완료한 뒤 전달할 수 있습니다."><i class="fas fa-paper-plane"></' + 'i> 수정본 전달 (재전송)</' + 'button><div class="text-danger small mt-1"><i class="fas fa-exclamation-triangle"></' + 'i> 미반영 요청이 있어 전달할 수 없습니다. 작업대 요청사항에서 반영 완료를 먼저 눌러주세요.</div>';
                  } else {
                    mainBtn = '<button class="btn btn-primary" onclick="openTransferDrawingModal(' + orderId + ', true)"><i class="fas fa-paper-plane"></' + 'i> 수정본 전달 (재전송)</' + 'button><div class="text-danger small mt-1"><i class="fas fa-exclamation-triangle"></' + 'i> 수정 요청 사항을 확인 후 다시 전달해주세요.</div>';
                  }
                } else {
                  mainBtn = '<button class="btn btn-secondary" disabled>수정 작업 대기중</button>';
                }
              } else {
                statusBadge = '<span class="badge bg-secondary ms-2">작업중</span>';
                if (canDrawingWork) {
                  mainBtn = '<button class="btn btn-primary" onclick="openTransferDrawingModal(' + orderId + ', false)"><i class="fas fa-paper-plane"></' + 'i> 도면 전달</' + 'button>';
                } else {
                  // 담당자 미지정이면 도면 전달 불가
                  if (!hasAssignee) {
                    mainBtn = `<small class="text-muted">도면 작업 대기중 (담당자 미지정)</small>`;
                  } else {
                    mainBtn = `<button class="btn btn-secondary" disabled>작업 관리는 담당자만 가능</button>`;
                  }
                }
              }
              const gatewayHistoryHtml = renderDrawingGatewayTimeline(drawHistory);
              const requestTabHtml = revisionRequests.length
                ? revisionRequests.slice(0, 8).map((h, idx) => {
                  const when = escapeHtml(h.transferred_at || h.at || '-');
                  const requestAtRaw = String(h.at || h.transferred_at || '');
                  const requestAtEnc = encodeURIComponent(requestAtRaw);
                  const by = escapeHtml(h.by_user_name || '-');
                  const byUserId = Number(h.by_user_id || 0) || '';
                  const note = escapeHtml(h.note || '요청 메모 없음');
                  const targetNo = Number(h.target_drawing_number || 0);
                  const targetBadge = targetNo > 0 ? '<span class="badge bg-info text-dark ms-1">' + targetNo + '번 대상</span>' : '';
                  const reviewCheck = (h.review_check && typeof h.review_check === 'object') ? h.review_check : {};
                  const isChecked = !!reviewCheck.checked;
                  const checkedBy = escapeHtml(reviewCheck.checked_by_name || '-');
                  const checkedAt = escapeHtml(reviewCheck.checked_at || '-');
                  const pinBadge = idx === 0 ? '<span class="badge bg-danger ms-1">최신 요청</span>' : '';
                  const checkBadge = isChecked
                    ? '<span class="badge bg-success ms-1">반영 완료</span>'
                    : '<span class="badge bg-secondary ms-1">미완료</span>';
                  const onclickToggle = 'toggleRevisionChecklist(' + orderId + ', \'' + requestAtEnc + '\', \'' + String(byUserId) + '\', ' + (isChecked ? 'false' : 'true') + ')';
                  const toggleBtn = canToggleRevisionCheck
                    ? ('<button class="btn btn-sm ' + (isChecked ? 'btn-outline-secondary' : 'btn-outline-success') + ' mt-2" onclick="' + onclickToggle + '"><i class="fas ' + (isChecked ? 'fa-rotate-left' : 'fa-check') + '"></' + 'i>' + (isChecked ? '완료 해제' : '반영 완료') + '</' + 'button>')
                    : '';
                  const checkMeta = isChecked
                    ? '<div class="small text-success mt-1"><i class="fas fa-user-check"></' + 'i> ' + checkedBy + ' · ' + checkedAt + '</div>'
                    : '';
                  return '<div class="border rounded p-2 mb-2 bg-white"><div class="small text-muted mb-1">' + when + ' · ' + by + ' ' + pinBadge + ' ' + checkBadge + ' ' + targetBadge + '</div><div class="small dw-revision-note-text">' + note + '</div>' + checkMeta + toggleBtn + '</div>';
                }).join('')
                : '<div class="text-muted small">수정 요청 이력이 없습니다.</div>';

              const transferEvents = drawHistory.filter(h => h && h.action === 'TRANSFER');
              const latestTransfer = transferEvents.length ? transferEvents[transferEvents.length - 1] : null;
              const prevTransfer = transferEvents.length > 1 ? transferEvents[transferEvents.length - 2] : null;
              const latestFiles = Array.isArray((latestTransfer || {}).files) ? latestTransfer.files : [];
              const prevFiles = Array.isArray((prevTransfer || {}).files) ? prevTransfer.files : [];
              const compareFilesHtml = '<div class="row g-2"><div class="col-md-6"><div class="border rounded p-2 h-100 bg-light">' +
                '<div class="fw-semibold small mb-1">이전본 ' + (prevTransfer ? '' : '(없음)') + '</div>' +
                '<div class="small text-muted mb-2">' + (prevTransfer ? escapeHtml(prevTransfer.transferred_at || '-') : '-') + '</div>' +
                (prevTransfer ? renderGatewayFiles(prevFiles, 'wb_prev_' + orderId) : '<div class="text-muted small">비교할 이전 전달본이 없습니다.</div>') +
                '</div></div><div class="col-md-6"><div class="border rounded p-2 h-100 bg-light">' +
                '<div class="fw-semibold small mb-1">최신본 ' + (latestTransfer ? '' : '(없음)') + '</div>' +
                '<div class="small text-muted mb-2">' + (latestTransfer ? escapeHtml(latestTransfer.transferred_at || '-') : '-') + '</div>' +
                (latestTransfer ? renderGatewayFiles(latestFiles, 'wb_latest_' + orderId) : '<div class="text-muted small">최신 전달본이 없습니다.</div>') +
                '</div></div></div>';

              let currentTaskText = '도면 담당자가 도면 전달을 진행해 주세요.';
              if (!hasAssignee) currentTaskText = '도면 담당자를 먼저 지정해야 합니다.';
              else if (drawingStatus === 'TRANSFERRED') currentTaskText = '주문 담당자가 수령 확정 또는 수정 요청을 선택해야 합니다.';
              else if (drawingStatus === 'RETURNED') currentTaskText = '도면 담당자가 요청사항 반영 후 수정본을 전달해야 합니다.';
              else if (drawingStatus === 'CONFIRMED') currentTaskText = '도면 수령 확정 완료. 다음 단계 진행을 확인해 주세요.';
              const checklist = [
                { label: '도면 담당자 지정', ok: hasAssignee },
                { label: '최신 전달본 확인', ok: latestFiles.length > 0 || (Array.isArray(sd.drawing_current_files) && sd.drawing_current_files.length > 0) },
                { label: '요청사항 검토', ok: drawingStatus !== 'RETURNED' || uncheckedRequestCount === 0 },
              ];
              const checklistHtml = '<div class="bg-white border rounded p-2 mb-2"><div class="small fw-semibold mb-1"><i class="fas fa-list-check text-primary"></' + 'i> 작업 체크리스트</div>' + checklist.map(function (item) {
                return '<div class="small ' + (item.ok ? 'text-success' : 'text-secondary') + '"><i class="fas ' + (item.ok ? 'fa-check-circle' : 'fa-circle') + '"></' + 'i> ' + escapeHtml(item.label) + '</div>';
              }).join('') + '</div>';

              const latestEvent = drawHistory.length ? drawHistory[drawHistory.length - 1] : null;
              const latestAction = (latestEvent && latestEvent.action) || '';
              const latestActionLabel = latestAction === 'TRANSFER'
                ? '도면 전달'
                : (latestAction === 'REQUEST_REVISION'
                  ? '수정 요청'
                  : (latestAction === 'CANCEL_TRANSFER' ? '전달 취소' : '이력 없음'));
              const latestWho = latestEvent ? escapeHtml(latestEvent.by_user_name || '-') : '-';
              const latestWhen = latestEvent ? escapeHtml(latestEvent.transferred_at || latestEvent.at || '-') : '-';
              const requestSummary = uncheckedRequestCount > 0
                ? `미완료 요청 ${uncheckedRequestCount}건`
                : '미완료 요청 없음';
              const workbenchTab = drawingStatus === 'RETURNED' ? 'requests' : 'timeline';
              const workbenchUrl = `/erp/drawing-workbench/${orderId}?tab=${encodeURIComponent(workbenchTab)}`;

              actionHtml = `
            <div class="col-12">
              <div class="card bg-light border-primary">
                <div class="card-body">
                  <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
                    <h5 class="card-title fw-bold text-primary mb-1">
                      <i class="fas fa-drafting-compass"></i> 도면 창구 요약
                      ${statusBadge}
                    </h5>
                    <p class="mb-0 text-muted small">
                      도면 담당: <strong>${assigneeNames || '미지정'}</strong>
                      ${assignBtn}
                      ${!canDrawingAssign ? '<span class="text-muted small ms-1">(수정 권한 없음)</span>' : ''}
                    </p>
                  </div>
                  <div class="bg-white border rounded p-2 mb-2">
                    <div class="small fw-semibold mb-1"><i class="fas fa-bolt text-primary"></i> 지금 필요한 작업</div>
                    <div class="small text-dark">${escapeHtml(currentTaskText)}</div>
                  </div>
                  <div class="bg-white border rounded p-2 mb-2">
                    <div class="small text-muted mb-1">최근 이벤트</div>
                    <div class="small fw-semibold">${latestActionLabel} · ${latestWho}</div>
                    <div class="small text-muted">${latestWhen}</div>
                    <div class="small mt-1"><span class="badge bg-light text-dark border">${requestSummary}</span></div>
                  </div>
                  <div class="d-flex flex-wrap gap-2">
                    <a class="btn btn-primary" href="${workbenchUrl}">
                      <i class="fas fa-comments"></i> 별도 작업실 열기
                    </a>
                    ${drawingStatus === 'RETURNED'
                      ? `<a class="btn btn-outline-danger" href="/erp/drawing-workbench/${orderId}?tab=requests">
                          <i class="fas fa-list-check"></i> 요청사항 바로보기
                        </a>`
                      : ''}
                  </div>
                    </div>
                </div>
              </div>
            </div>`;
            }

            container.innerHTML = `
          <div class="row g-3 erp-order-detail">
            ${basicInfoHtml}
            ${scheduleHtml}
            ${roleAssigneesHtml}
            ${actionHtml}
            <div class="col-12">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title fw-bold mb-3"><i class="fas fa-box text-primary"></i> 제품 항목</h5>
                  ${itemsHtml}
                </div>
              </div>
            </div>
            <div class="col-12">
              <div class="card">
                <div class="card-body">
                  <h5 class="card-title fw-bold mb-3"><i class="fas fa-paperclip text-primary"></i> 첨부 파일 <span class="badge bg-secondary" style="font-size: 1rem;" id="order-detail-attachments-count-${orderId}">${attachmentsPending ? '…' : (aList.length + '개')}</span></h5>
                  <div id="order-detail-attachments-slot-${orderId}">${attachmentsHtml}</div>
                </div>
              </div>
            </div>
            <div class="col-12">
              <div class="card border-danger">
                <div class="card-body py-2">
                  <div class="d-flex align-items-center gap-2 flex-wrap">
                    <span class="fw-semibold text-danger" style="font-size:0.85rem"><i class="fas fa-bell"></i> 동료 호출</span>
                    <div class="d-none d-lg-flex align-items-center gap-2 flex-wrap">
                      <select class="form-select form-select-sm" id="mention-target-${orderId}" style="max-width:180px">
                        <option value="">-- 대상 선택 --</option>
                      </select>
                      <input type="text" class="form-control form-control-sm" id="mention-msg-${orderId}" placeholder="메시지 (선택)" style="max-width:220px">
                      <button class="btn btn-danger btn-sm" type="button" data-order-id="${orderId}">
                        <i class="fas fa-paper-plane"></i> 긴급 호출
                      </button>
                    </div>
                    <button class="btn btn-danger btn-sm d-lg-none" type="button" data-foms-urgent-call data-order-id="${orderId}">
                      <i class="fas fa-bolt"></i> 긴급 호출
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        `;
            try { performance.mark('erp-detail-shell:' + orderId); } catch (e) {}
            /** 재시도 경로에서 items를 다시 알기 위해 행 개수를 컨테이너에 기록 */
            container.dataset.itemCount = String(items.length);

            // 출고가 / 예약금 / 잔금 금액 주입 (sd에서 계산)
            (() => {
              const coerceAmount = (value) => {
                if (value == null) return 0;
                if (typeof value === 'object') return coerceAmount(value.amount || value.raw || 0);
                if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
                const digits = String(value || '').replace(/[^0-9]/g, '');
                return digits ? parseInt(digits, 10) : 0;
              };
              const sumFreeInputFromText = (text) => {
                const raw = String(text || '').trim();
                if (!raw) return 0;
                let sum = 0;
                raw.replace(/\r\n/g, '\n').split('\n').forEach((line) => {
                  const trimmed = line.trim();
                  if (!trimmed) return;
                  let amountPart = trimmed;
                  const m = trimmed.match(/^[^:：]+[:：]\s*(.+)$/);
                  if (m) amountPart = m[1].trim();
                  const n = coerceAmount(amountPart);
                  if (n > 0) sum += n;
                });
                return sum;
              };
              const totals = sd.totals || {};
              const itemsTotal = Number(totals.items_total) || items.reduce((s, it) => s + (Number(it.price) || 0), 0);
              const depositAmt = coerceAmount((sd.payment || {}).deposit) || coerceAmount((sd.payments || {}).deposit);
              const discountAmt = coerceAmount((sd.payment || {}).discount) || coerceAmount((sd.totals || {}).discount_amount);
              const freeInputRaw = (sd.payment || {}).free_input
                || (sd.payments || {}).free_input?.value
                || (sd.payments || {}).free_input?.raw
                || '';
              const freeInputAmt = coerceAmount(totals.free_input_amount) || sumFreeInputFromText(freeInputRaw);
              let remainAmt = coerceAmount(totals.final_amount) || coerceAmount(totals.balance_amount);
              if (!remainAmt) {
                remainAmt = Math.max(0, itemsTotal + freeInputAmt - depositAmt - discountAmt);
              }
              const fmtKRW = (n) => n > 0 ? n.toLocaleString('ko-KR') + '원' : '0원';
              items.forEach((_, i) => {
                const totalEl = document.getElementById(`erp-items-total-${orderId}-${i}`);
                const depositEl = document.getElementById(`erp-deposit-amount-${orderId}-${i}`);
                const discountEl = document.getElementById(`erp-discount-amount-${orderId}-${i}`);
                const remainEl = document.getElementById(`erp-remaining-amount-${orderId}-${i}`);
                const discountSection = document.getElementById(`erp-discount-section-${orderId}-${i}`);
                const remainSection = document.getElementById(`erp-remaining-section-${orderId}-${i}`);
                if (totalEl) totalEl.textContent = fmtKRW(itemsTotal);
                if (depositEl) depositEl.value = depositAmt > 0 ? fmtKRW(depositAmt) : '';
                if (discountEl) discountEl.value = discountAmt > 0 ? fmtKRW(discountAmt) : '';
                if (remainEl) remainEl.textContent = fmtKRW(remainAmt);
                if (discountSection) discountSection.style.display = discountAmt > 0 ? 'flex' : 'none';
                if (remainSection) remainSection.style.display = itemsTotal > 0 ? 'flex' : 'none';
              });
            })();

            // 이미지 뷰어용 그룹 등록 (첨부 2단 완료 후 다시 호출됨)
            registerOrderDetailDrawingViewerGroups(orderId);

            // 긴급 호출 버튼 클릭 바인딩 (inline onclick 대신 data-order-id + 리스너로 린터 회피)
            var mentionBtn = container.querySelector('button[data-order-id]');
            if (mentionBtn) {
              mentionBtn.addEventListener('click', function() {
                sendUrgentMention(parseInt(mentionBtn.getAttribute('data-order-id'), 10));
              });
            }
            // 동료 호출 대상 사용자 목록 로드
            const mentionSelect = document.getElementById(`mention-target-${orderId}`);
            if (mentionSelect && !mentionSelect.dataset.loaded) {
              fetch('/erp/api/orders/' + orderId + '/urgent-targets', { credentials: 'same-origin' })
                .then(function(r) { return r.json(); })
                .then(function(d) {
                  if (!d.success || !d.targets) return;
                  d.targets.forEach(function(u) {
                    var o = document.createElement('option');
                    o.value = u.id;
                    o.textContent = u.name + (u.team ? ' (' + u.team + ')' : '');
                    mentionSelect.appendChild(o);
                  });
                  mentionSelect.dataset.loaded = '1';
                })
                .catch(function(e) { console.warn('mention urgent-targets fetch 실패:', e); });
            }

            if (attachmentsPending) {
              container.dataset.shellLoaded = '1';
              container.dataset.attachPhase = 'loading';
              await patchOrderDetailAttachments(orderId, items.length, gen);
            } else {
              container.dataset.loaded = '1';
              container.dataset.attachPhase = 'done';
            }

          } catch (err) {
            console.error('주문 상세 로드 실패:', err);
            container.innerHTML = '<div class="text-danger small">로드 실패: ' + escapeHtml(err.message) + '</div>';
          }
        }

        function sendUrgentMention(orderId) {
          var sel = document.getElementById('mention-target-' + orderId);
          var msgInput = document.getElementById('mention-msg-' + orderId);
          if (!sel) return;
          var targetId = sel.value;
          if (!targetId) { alert('호출 대상을 선택해주세요.'); return; }
          var msg = msgInput ? msgInput.value.trim() : '';

          if (!confirm('선택한 동료에게 긴급 호출을 보내시겠습니까?')) return;

          window.FOMSNotificationWrite.fetch('/erp/api/orders/' + orderId + '/urgent-mention', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ target_user_id: parseInt(targetId), message: msg })
          })
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (data.success) {
              alert(data.message || '긴급 멘션을 보냈습니다.');
              sel.value = '';
              if (msgInput) msgInput.value = '';
            } else {
              alert(data.message || '발송 실패');
            }
          })
          .catch(function() { alert('긴급 멘션 발송 중 오류가 발생했습니다.'); });
        }

        function initErpDashboardBoundaryResize() {
          const table = document.querySelector('#erp-grid.erp-dashboard-grid-resizable');
          if (!table) return;
          if (!window.ERPGridBoundaryResize || typeof window.ERPGridBoundaryResize.init !== 'function') return;

          window.ERPGridBoundaryResize.init({
            tableSelector: table,
            resetButtonSelector: '#erp-grid-reset-column-widths',
            storageKey: 'foms:erp-dashboard:boundary-widths:v2'
          });
        }

        function fomsErpDashboardInitMain() {
          if (typeof window.fomsSyncErpDashboardUserGlobals === 'function') {
            window.fomsSyncErpDashboardUserGlobals();
          }
          initErpDashboardBoundaryResize();
          // URL 파라미터로 특정 주문 하이라이트 및 퀘스트 확장 (도면 수령확정 후 이동 등)
          (() => {
            const urlParams = new URLSearchParams(window.location.search);
            const focusOrder = urlParams.get('focus_order');
            const openQuest = urlParams.get('open_quest') === 'true';

            if (focusOrder) {
              setTimeout(() => {
                const row = document.querySelector(`.erp-main-row[data-order-id="${focusOrder}"]`);
                if (row) {
                  row.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                  });
                  row.classList.add('table-info'); // Bootstrap highlight
                  setTimeout(() => row.classList.remove('table-info'), 2500);

                  if (openQuest) {
                    const questCollapse = document.getElementById(`quest-collapse-${focusOrder}`);
                    if (questCollapse) {
                      const bsCollapse = new bootstrap.Collapse(questCollapse, {
                        toggle: false
                      });
                      bsCollapse.show();
                    }
                  }
                }
              }, 500); // 렌더링 지연 고려
            }
          })();

          // 필터 폼 제출 시 텍스트 검색(q)이 있으면 stage, team 초기화 (항상 전체 검색)
          // 및 alert_type 파라미터 유지
          const form = document.getElementById('erp-filters-form');
          if (form) {
            form.addEventListener('submit', function (e) {
              const qInput = this.querySelector('input[name="q"]');
              if (qInput && qInput.value.trim() !== '') {
                const stageSelect = this.querySelector('select[name="stage"]');
                if (stageSelect) stageSelect.value = '';
                const teamSelect = this.querySelector('select[name="team"]');
                if (teamSelect) teamSelect.value = '';
              }

              const url = new URL(window.location.href);
              const currentAlertType = url.searchParams.get('alert_type');
              if (currentAlertType) {
                let alertTypeInput = this.querySelector('input[name="alert_type"]');
                if (!alertTypeInput) {
                  alertTypeInput = document.createElement('input');
                  alertTypeInput.type = 'hidden';
                  alertTypeInput.name = 'alert_type';
                  this.appendChild(alertTypeInput);
                }
                alertTypeInput.value = currentAlertType;
              }
            });
          }

          // 주문 상세 collapse: 애니메이션 시작과 동시에 DOM 빌드 → 로딩 지연 제거
          document.querySelectorAll('.collapse[id^="order-detail-collapse-"]').forEach(collapseEl => {
            // show 시점(애니메이션 시작)에 바로 DOM 빌드 — preloaded payload 사용 시 즉각 완료
            collapseEl.addEventListener('show.bs.collapse', function () {
              const orderId = this.id.replace('order-detail-collapse-', '');
              loadOrderDetail(parseInt(orderId, 10));
            });

            // shown 시점(애니메이션 완료)에 스크롤 정렬
            collapseEl.addEventListener('shown.bs.collapse', function () {
              const orderId = this.id.replace('order-detail-collapse-', '');
              const alignDetailUnderNavbar = () => {
                const nav = document.querySelector('nav.navbar');
                const navHeight = nav ? nav.offsetHeight : 56;
                const titleEl = this.querySelector('.erp-order-detail-title') || this;
                const targetTop = window.scrollY + titleEl.getBoundingClientRect().top - navHeight - 8;
                window.scrollTo({ top: Math.max(0, targetTop), behavior: 'auto' });
              };
              alignDetailUnderNavbar();
              setTimeout(alignDetailUnderNavbar, 120);
            });
          });

          // 딥링크 포커스: 도면 창구는 별도 작업실로 단일 진입
          (() => {
            try {
              const url = new URL(window.location.href);
              const focus = (url.searchParams.get('focus') || '').toLowerCase();
              const orderId = String(url.searchParams.get('order_id') || '').trim();
              const tabRaw = (url.searchParams.get('tab') || 'timeline').toLowerCase();
              const tabKey = (tabRaw === 'request' || tabRaw === 'requests')
                ? 'requests'
                : (tabRaw === 'file' || tabRaw === 'files' || tabRaw === 'compare' ? 'compare' : 'timeline');
              if (focus !== 'drawing-gateway' || !orderId) return;
              const targetUrl = `/erp/drawing-workbench/${orderId}?tab=${encodeURIComponent(tabKey)}`;
              window.location.href = targetUrl;
            } catch (_) { }
          })();

          // 프로세스 맵 & 알림 타일 클릭 → "해당 필터만" URL 파라미터 적용 후 리로드
          const applyFilter = (name, value) => {
            const singleFilterNames = ['stage', 'alert_type', 'urgent', 'has_alert', 'team', 'q'];
            const url = new URL(window.location.href);
            const params = url.searchParams;

            // 기존 단일 필터 전부 제거
            singleFilterNames.forEach((fieldName) => params.delete(fieldName));

            // 클릭한 필터만 설정
            if (value) {
              params.set(name, value);
            }

            // URL 이동 (GET)
            window.location.href = `${url.pathname}?${params.toString()}`;
          };

          // 프로세스 맵 (Pipeline Stages)
          document.querySelectorAll('.erp-pro-pipeline__stage[data-stage]').forEach(el => {
            const handler = () => applyFilter('stage', el.dataset.stage || '');
            el.addEventListener('click', handler);
            el.addEventListener('keydown', (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handler();
              }
            });
          });

          // 알림 타일 (Alert Tiles)
          document.querySelectorAll('.erp-pro-alert[data-alert-type]').forEach(el => {
            const handler = () => applyFilter('alert_type', el.dataset.alertType || '');
            el.addEventListener('click', handler);
            el.addEventListener('keydown', (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handler();
              }
            });
          });

          // 이벤트 위임: 퀘스트 승인, 첨부 미리보기 등 (document.body에 1회만)
          if (!window.__fomsErpDashboardBodyClickBound) {
            window.__fomsErpDashboardBodyClickBound = true;
            document.body.addEventListener('click', function (e) {
            const targetCard = e.target.closest('.drawing-target-card');
            if (targetCard) {
              const role = String(targetCard.getAttribute('data-role') || '');
              const rawKey = String(targetCard.getAttribute('data-key') || '');
              const key = rawKey ? decodeURIComponent(rawKey) : '';
              selectDrawingTargetByCard(role, key);
              return;
            }

            // 승인 버튼
            const approveBtn = e.target.closest('.erp-btn-approve-team');
            if (approveBtn) {
              const orderId = approveBtn.dataset.orderId;
              const team = approveBtn.dataset.team;
              if (typeof approveQuestTeam === 'function') {
                approveQuestTeam(Number(orderId), team);
              } else {
                console.warn('approveQuestTeam is not defined');
              }
            }

            const approveAssigneeBtn = e.target.closest('.erp-btn-approve-assignee');
            if (approveAssigneeBtn) {
              const orderId = Number(approveAssigneeBtn.dataset.orderId);
              if (typeof approveQuestAssignee === 'function') {
                approveQuestAssignee(orderId);
              }
            }

            const drawingThumb = e.target.closest('.erp-drawing-gateway-thumb');
            if (drawingThumb) {
              const viewUrl = drawingThumb.dataset.viewUrl || '#';
              const downloadUrl = drawingThumb.dataset.downloadUrl || viewUrl;
              const filename = drawingThumb.dataset.filename || '';
              const fileType = drawingThumb.dataset.fileType || 'image';
              if (typeof openAttachmentPreviewModal === 'function') {
                openAttachmentPreviewModal(0, viewUrl, downloadUrl, filename, fileType);
              }
            }

            const openDrawingAttBtn = e.target.closest('.erp-btn-open-drawing-attachments');
            if (openDrawingAttBtn) {
              const orderId = Number(openDrawingAttBtn.dataset.orderId);
              if (typeof openAttachmentsPreview === 'function') {
                openAttachmentsPreview(orderId, 'drawing');
              }
            }

            const confirmReceiptBtn = e.target.closest('.erp-btn-confirm-drawing-receipt');
            if (confirmReceiptBtn) {
              const orderId = Number(confirmReceiptBtn.dataset.orderId);
              if (typeof confirmDrawingReceipt === 'function') {
                confirmDrawingReceipt(orderId);
              }
            }

            const revisionReqBtn = e.target.closest('.erp-btn-open-revision-request');
            if (revisionReqBtn) {
              const orderId = Number(revisionReqBtn.dataset.orderId);
              if (typeof openRevisionRequestModal === 'function') {
                openRevisionRequestModal(orderId);
              }
            }

            const cancelTransferBtn = e.target.closest('.erp-btn-cancel-drawing-transfer');
            if (cancelTransferBtn) {
              const orderId = Number(cancelTransferBtn.dataset.orderId);
              if (typeof cancelDrawingTransfer === 'function') {
                cancelDrawingTransfer(orderId);
              }
            }

            const openTransferBtn = e.target.closest('.erp-btn-open-transfer-drawing');
            if (openTransferBtn) {
              const orderId = Number(openTransferBtn.dataset.orderId);
              const isRetransfer = String(openTransferBtn.dataset.retransfer || 'false') === 'true';
              if (typeof openTransferDrawingModal === 'function') {
                openTransferDrawingModal(orderId, isRetransfer);
              }
            }

            // 첨부파일 미리보기 버튼
            const attBtn = e.target.closest('.erp-btn-attachments-preview');
            if (attBtn) {
              const orderId = attBtn.dataset.orderId;
              if (typeof openAttachmentsPreview === 'function') {
                openAttachmentsPreview(Number(orderId));
              }
            }
          });
          }

          // 도면 수정 창구 이미지 뷰어 초기화 (프래그먼트 재스왑 시 DOM 새로 바인딩)
          window.__fomsDrawingGatewayViewerBound = false;
          initDrawingGatewayImageViewer();

          // 작업 큐: 다중 선택 후 상태 일괄 변경
          (function () {
            const bulkBar = document.getElementById('erp-grid-bulk-bar');
            const countEl = document.getElementById('erp-grid-selected-count');
            const selectEl = document.getElementById('erp-grid-bulk-status');
            const applyBtn = document.getElementById('erp-grid-bulk-apply');
            const selectAll = document.getElementById('erp-grid-select-all');
            const grid = document.getElementById('erp-grid');
            if (!grid || !bulkBar || !countEl || !selectEl || !applyBtn) return;

            function updateSelectedCount() {
              const checks = grid.querySelectorAll('.erp-grid-order-check:checked');
              const n = checks.length;
              countEl.textContent = n;
              if (n > 0) {
                bulkBar.classList.remove('d-none');
                bulkBar.classList.add('d-flex');
              } else {
                bulkBar.classList.add('d-none');
                bulkBar.classList.remove('d-flex');
              }
              if (selectAll) selectAll.checked = n > 0 && grid.querySelectorAll('.erp-grid-order-check').length === n;
            }

            if (selectAll) {
              selectAll.addEventListener('change', function () {
                grid.querySelectorAll('.erp-grid-order-check').forEach(cb => { cb.checked = selectAll.checked; });
                updateSelectedCount();
              });
            }
            grid.addEventListener('change', function (e) {
              if (e.target.classList.contains('erp-grid-order-check')) updateSelectedCount();
            });

            grid.addEventListener('click', function (e) {
              if (e.target.closest('.erp-grid-order-check')) return;
              if (e.target.closest('a, button, select, textarea, label')) return;
              const cell = e.target.closest('td[data-label="경보"]');
              if (!cell || !grid.contains(cell)) return;
              const cb = cell.querySelector('.erp-grid-order-check');
              if (!cb) return;
              cb.checked = !cb.checked;
              updateSelectedCount();
            });

            applyBtn.addEventListener('click', function () {
              const status = (selectEl.value || '').trim();
              if (!status) {
                alert('변경할 상태를 선택하세요.');
                return;
              }
              const orderIds = Array.from(grid.querySelectorAll('.erp-grid-order-check:checked'))
                .map(cb => cb.getAttribute('data-order-id'))
                .filter(Boolean);
              if (orderIds.length === 0) {
                alert('주문을 선택하세요.');
                return;
              }
              applyBtn.disabled = true;
              fetch('/api/bulk_update_order_status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ order_ids: orderIds, status: status })
              })
                .then(r => r.json())
                .then(data => {
                  if (data.success) {
                    window.location.reload();
                  } else {
                    alert(data.message || '상태 변경에 실패했습니다.');
                  }
                })
                .catch(() => alert('요청 중 오류가 발생했습니다.'))
                .finally(() => { applyBtn.disabled = false; });
            });
          })();

          // 실측일/시공일 인라인 편집: 변경 시 확인 후 API 저장 (오입력 방지)
          var fieldLabelByField = { 'measurement_date': '실측일', 'scheduled_date': '시공일' };
          document.querySelectorAll('.erp-dashboard-date-input').forEach(function (input) {
            input.addEventListener('change', function () {
              var orderId = this.getAttribute('data-order-id');
              var field = this.getAttribute('data-field');
              var value = (this.value || '').trim();
              if (!orderId || !field) return;
              var prevValue = this.getAttribute('data-prev-value') || '';
              var label = fieldLabelByField[field] || field;
              var msg = value
                ? label + '을(를) ' + value + '(으)로 변경하시겠습니까?'
                : label + '을(를) 비우시겠습니까?';
              if (!window.confirm(msg)) {
                this.value = prevValue || '';
                return;
              }
              fetch('/api/update_order_field', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ order_id: parseInt(orderId, 10), field: field, value: value })
              })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                  if (data.success) {
                    input.setAttribute('data-prev-value', value);
                  } else {
                    alert(data.message || '저장에 실패했습니다.');
                    input.value = prevValue || '';
                  }
                })
                .catch(function () {
                  alert('요청 중 오류가 발생했습니다.');
                  input.value = prevValue || '';
                });
            });
            input.setAttribute('data-prev-value', input.value || '');
          });
        }

        function fomsErpDashboardScheduleMainInit() {
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fomsErpDashboardInitMain);
          } else {
            fomsErpDashboardInitMain();
          }
        }
        fomsErpDashboardScheduleMainInit();

        document.addEventListener('foms:erp-shell-fragment-swapped', function () {
          if (document.querySelector('#main-content .erp-dashboard')) {
            fomsErpDashboardInitMain();
          }
        });
