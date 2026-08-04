/**
 * 주문 상세 2단 렌더 공통 첨부 패치 헬퍼.
 * erp-dashboard-entry.js CHAIN 에서 erp-dashboard-core.js 이후,
 * erp-dashboard-detail-dom.js(소비자) 이전에 로드한다.
 */

function parseAttachmentsPayload(attachments) {
    if (!attachments) return [];
    if (Array.isArray(attachments)) return attachments;
    if (attachments.attachments && Array.isArray(attachments.attachments)) return attachments.attachments;
    if (attachments.success !== false && attachments.attachments) return attachments.attachments;
    if (attachments.success === false) {
        console.warn('Attachments API returned error:', attachments.message || 'Unknown error');
        return [];
    }
    return [];
}

function orderDetailIsImageFile(a) {
    const ft = (a.file_type || '').toLowerCase();
    if (ft === 'image') return true;
    const fn = String(a.filename || '').toLowerCase();
    return /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif)(\?|$)/.test(fn);
}

function sanitizeAttachmentUrl(url) {
    const s = String(url || '').trim();
    if (!s) return '';
    if (s.startsWith('/') || s.startsWith('./') || s.startsWith('../')) return s;
    if (/^https?:\/\//i.test(s)) return s;
    console.warn('Rejected attachment URL scheme:', s);
    return '';
}

function buildDwAttachPanelHtml(orderId, idx, itemAtts) {
    const groupKey = `order_${orderId}_item_${idx}`;
    let attachPanelHtml = '<div class="dw-attach-panel" id="order-detail-item-attach-' + orderId + '-' + idx + '"><div class="small fw-semibold text-muted mb-2"><i class="fas fa-image"></i> 실측 첨부 파일</div>';
    if (itemAtts.length > 0) {
        const singleClass = itemAtts.length === 1 ? ' dw-attach-grid--single' : '';
        attachPanelHtml += '<div class="dw-attach-grid' + singleClass + '">';
        let imageIndex = 0;
        itemAtts.forEach((a) => {
            const name = escapeHtml(a.filename || '');
            const viewUrl = sanitizeAttachmentUrl(a.view_url || a.thumbnail_view_url || '');
            const downloadUrl = sanitizeAttachmentUrl(a.download_url || viewUrl);
            const fileKey = String(a.key || a.storage_key || '');
            const imgSrc = sanitizeAttachmentUrl(a.thumbnail_view_url || a.view_url || '');
            const isImg = orderDetailIsImageFile(a) && !!imgSrc;
            const idxAttr = isImg ? imageIndex++ : 0;
            const safeViewUrl = String(viewUrl).split("'").join("\\'");
            const safeDownloadUrl = String(downloadUrl).split("'").join("\\'");
            const safeFileKey = escapeHtml(fileKey);
            const dataAttrs = 'data-group-key="' + groupKey + '" data-index="' + idxAttr + '" data-view-url="' + escapeHtml(viewUrl) + '" data-download-url="' + escapeHtml(downloadUrl) + '" data-filename="' + name + '" data-key="' + safeFileKey + '"';
            if (isImg) {
                attachPanelHtml += '<div><div class="dw-attach-thumb" ' + dataAttrs + ' onclick="openDrawingGatewayImageViewer(this.dataset.groupKey, Number(this.dataset.index))"><img src="' + escapeHtml(imgSrc) + '" alt="' + name + '"></div><div class="dw-attach-name">' + name + '</div></div>';
            } else {
                const safeNameForModal = String(a.filename || '').split("'").join("\\'");
                const fileTypeForPreview = (a.file_type && String(a.file_type)) ? String(a.file_type) : 'file';
                const q = String.fromCharCode(39);
                const onclickModal = 'openAttachmentPreviewModal(' + (a.id || 0) + ', ' + q + safeViewUrl + q + ', ' + q + safeDownloadUrl + q + ', ' + q + safeNameForModal + q + ', ' + q + fileTypeForPreview + q + ')';
                attachPanelHtml += '<div><div class="dw-attach-thumb d-flex align-items-center justify-content-center bg-light text-secondary" ' + dataAttrs + ' onclick="' + onclickModal + '"><i class="fas fa-file-alt"></' + 'i></div><div class="dw-attach-name">' + name + '</div></div>';
            }
        });
        attachPanelHtml += '</div>';
    } else {
        attachPanelHtml += '<div class="small text-muted">연결된 실측 첨부 파일이 없습니다.</div>';
    }
    attachPanelHtml += '</div>';
    return attachPanelHtml;
}

function buildMainAttachThumbsHtml(orderId, aList) {
    if (aList.length <= 0) {
        return '<div class="text-muted small mt-2">첨부 없음</div>';
    }

    // 갤러리 마커 + data-* 로 형제 목록 컨텍스트 보존 — 클릭 시 이미지·영상 전체를
    // GlobalImageViewer 목록으로 넘겨 좌우 스와이프/화살표 이동이 되게 한다(단일 열림이
    // 대시보드별 "옆으로 안 넘어감"의 근본 원인). 문서 파일은 기존 단일 모달 유지.
    let attachmentsHtml = '<div class="d-flex flex-wrap gap-1 mt-2" data-foms-attach-strip>';
    aList.forEach((a) => {
        const name = escapeHtml(a.filename || '');
        const viewUrl = sanitizeAttachmentUrl(a.view_url || '');
        const thumb = sanitizeAttachmentUrl(a.thumbnail_view_url || viewUrl);
        const downloadUrl = sanitizeAttachmentUrl(a.download_url || viewUrl);
        const fileType = a.file_type || 'image';
        const dataAttrs = ' role="button" tabindex="0" data-att-id="' + Number(a.id || 0) + '"' +
            ' data-view-url="' + escapeHtml(viewUrl) + '"' +
            ' data-download-url="' + escapeHtml(downloadUrl) + '"' +
            ' data-filename="' + name + '"' +
            ' data-file-type="' + escapeHtml(String(fileType)) + '"';
        if (fileType === 'video' && viewUrl) {
            attachmentsHtml += '<div class="erp-attach-thumb"' + dataAttrs + '>' +
                '<div class="erp-attach-thumb-video-bg">' +
                '<video src=\'' + escapeHtml(viewUrl) + '\' preload="metadata" class="erp-attach-thumb-media"></video>' +
                '</div>' +
                '<div class="erp-attach-thumb-play-badge"><i class="fas fa-play"></' + 'i></div>' +
                '</div>';
        } else if (fileType === 'file' || !thumb) {
            attachmentsHtml += '<div class="erp-attach-thumb erp-attach-thumb-file-bg d-flex align-items-center justify-content-center"' + dataAttrs + '>' +
                '<i class="fas fa-file-alt text-secondary"></' + 'i>' +
                '</div>';
        } else {
            attachmentsHtml += '<div class="erp-attach-thumb"' + dataAttrs + '>' +
                '<img src=\'' + escapeHtml(thumb) + '\' class="erp-attach-thumb-img" alt=\'' + name + '\'>' +
                '</div>';
        }
    });
    attachmentsHtml += '</div>';
    return attachmentsHtml;
}

// 첨부 스트립 클릭 위임(1회 바인딩): 이미지·영상 2개 이상이면 형제 전체를 GlobalImageViewer
// 목록으로 열고(스와이프/화살표), 그 외(문서·단일)는 기존 단일 미리보기 경로 유지.
if (!window.__FOMS_MAIN_ATTACH_STRIP_BOUND) {
    window.__FOMS_MAIN_ATTACH_STRIP_BOUND = true;
    document.addEventListener('click', function (e) {
        const thumbEl = e.target.closest('[data-foms-attach-strip] .erp-attach-thumb[data-view-url]');
        if (!thumbEl) return;
        e.preventDefault();
        const strip = thumbEl.closest('[data-foms-attach-strip]');
        const thumbs = Array.prototype.slice.call(
            strip.querySelectorAll('.erp-attach-thumb[data-view-url]')
        );
        const isViewerType = function (el) {
            const t = String(el.getAttribute('data-file-type') || 'image').toLowerCase();
            return t === 'image' || t === 'video';
        };
        const eligible = thumbs.filter(isViewerType);
        if (
            isViewerType(thumbEl) && eligible.length > 1 &&
            window.GlobalImageViewer && window.GlobalImageViewer.open
        ) {
            const files = eligible.map(function (el) {
                return {
                    view_url: el.getAttribute('data-view-url') || '',
                    download_url: el.getAttribute('data-download-url') || el.getAttribute('data-view-url') || '',
                    filename: el.getAttribute('data-filename') || '이미지'
                };
            });
            window.GlobalImageViewer.open(files, Math.max(0, eligible.indexOf(thumbEl)));
            return;
        }
        if (typeof window.openAttachmentPreviewModal === 'function') {
            window.openAttachmentPreviewModal(
                Number(thumbEl.getAttribute('data-att-id') || 0),
                thumbEl.getAttribute('data-view-url') || '',
                thumbEl.getAttribute('data-download-url') || thumbEl.getAttribute('data-view-url') || '',
                thumbEl.getAttribute('data-filename') || '',
                thumbEl.getAttribute('data-file-type') || 'image'
            );
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const thumbEl = e.target.closest && e.target.closest('[data-foms-attach-strip] .erp-attach-thumb[data-view-url]');
        if (!thumbEl) return;
        e.preventDefault();
        thumbEl.click();
    });
}

function registerOrderDetailDrawingViewerGroups(orderId) {
    if (typeof __drawingGatewayImageGroups !== 'undefined' && window.__orderDetailImageGroups && window.__orderDetailImageGroups[orderId]) {
        (window.__orderDetailImageGroups[orderId] || []).forEach((imageFiles, idx) => {
            __drawingGatewayImageGroups['order_' + orderId + '_item_' + idx] = imageFiles || [];
        });
    }
}

function resetOrderDetailContainerState(container) {
    if (!container) return;
    delete container.dataset.loaded;
    delete container.dataset.shellLoaded;
    delete container.dataset.attachPhase;
    delete container.dataset.attachError;
    delete container.dataset.itemCount;
}

function invalidateOrderDetailRuntimeState(orderId, runtime) {
    if (!orderId || !runtime) return;
    if (runtime.cache && typeof runtime.cache === 'object') {
        delete runtime.cache[orderId];
    }
    if (runtime.cacheAt && typeof runtime.cacheAt === 'object') {
        delete runtime.cacheAt[orderId];
    }
    if (runtime.loadGen && typeof runtime.loadGen === 'object') {
        delete runtime.loadGen[orderId];
    }
    const containerPrefix = runtime.containerPrefix || 'order-detail-content-';
    const container = document.getElementById(containerPrefix + orderId);
    if (container) {
        resetOrderDetailContainerState(container);
    }
}
window.invalidateOrderDetailRuntimeState = invalidateOrderDetailRuntimeState;

function erpNormalizeConstructionWorkerNames(value) {
    if (!value) return [];
    const list = Array.isArray(value) ? value : String(value).split(/[,，、]/);
    const workers = [];
    list.forEach(function (item) {
        let name = '';
        if (typeof item === 'string') {
            name = item.trim();
        } else if (item && typeof item === 'object') {
            name = String(item.name || '').trim();
        } else if (item != null) {
            name = String(item).trim();
        }
        if (name && workers.indexOf(name) === -1) workers.push(name);
    });
    return workers;
}

function resolveOrderRoleAssignees(structured, preloadedPayload) {
    if (preloadedPayload && preloadedPayload.role_assignees && typeof preloadedPayload.role_assignees === 'object') {
        return preloadedPayload.role_assignees;
    }
    const sd = (structured && structured.structured_data) || structured || {};
    const assignments = sd.assignments || {};
    const shipment = sd.shipment || {};
    const parties = sd.parties || {};
    const joinNames = function (names) {
        const cleaned = (names || []).map(function (n) { return String(n || '').trim(); }).filter(Boolean);
        return cleaned.length ? cleaned.join(', ') : '-';
    };

    const salesIds = Array.isArray(assignments.sales_assignee_user_ids)
        ? assignments.sales_assignee_user_ids.map(function (x) { return Number(x); }).filter(function (x) { return Number.isFinite(x); })
        : [];
    let measurementNames = [];
    if (salesIds.length) {
        measurementNames = [salesIds.length + '명 지정'];
    } else {
        const manager = String(((parties.manager || {}).name) || '').trim();
        if (manager && manager !== '-') measurementNames = [manager];
    }

    const drawingAssignees = Array.isArray(sd.drawing_assignees) ? sd.drawing_assignees : [];
    let drawingNames = drawingAssignees.map(function (u) { return (u && u.name) || ''; }).filter(Boolean);
    const drawingIds = [];
    if (!drawingNames.length) {
        drawingAssignees.forEach(function (u) {
            const idNum = Number(u && u.id);
            if (Number.isFinite(idNum)) drawingIds.push(idNum);
        });
        (Array.isArray(assignments.drawing_assignee_user_ids) ? assignments.drawing_assignee_user_ids : []).forEach(function (x) {
            const idNum = Number(x);
            if (Number.isFinite(idNum)) drawingIds.push(idNum);
        });
        if (drawingIds.length) drawingNames = [drawingIds.length + '명 지정'];
    }
    if (!drawingNames.length) {
        const drawingManager = String(shipment.drawing_manager || '').trim();
        if (drawingManager) {
            drawingNames = [drawingManager];
        } else {
            drawingNames = (Array.isArray(shipment.drawing_managers) ? shipment.drawing_managers : [])
                .map(function (n) { return String(n || '').trim(); })
                .filter(Boolean);
        }
    }

    const constructionNames = erpNormalizeConstructionWorkerNames(shipment.construction_workers || shipment.construction_worker);

    return {
        measurement_assignee: joinNames(measurementNames),
        drawing_assignee: joinNames(drawingNames),
        construction_assignee: joinNames(constructionNames),
    };
}
window.resolveOrderRoleAssignees = resolveOrderRoleAssignees;

function buildOrderRoleAssigneesHtml(roleAssignees) {
    const roles = roleAssignees || {};
    const esc = typeof escapeHtml === 'function' ? escapeHtml : function (v) { return String(v || ''); };
    return '<div class="col-12">'
        + '<div class="card">'
        + '<div class="card-body">'
        + '<h5 class="card-title fw-bold"><i class="fas fa-user-tag text-primary"></i> 담당</h5>'
        + '<div class="erp-detail-text">'
        + '<div class="mb-3"><strong class="erp-detail-label">실측 담당:</strong> <span class="erp-detail-value">' + esc(roles.measurement_assignee || '-') + '</span></div>'
        + '<div class="mb-3"><strong class="erp-detail-label">도면 담당:</strong> <span class="erp-detail-value">' + esc(roles.drawing_assignee || '-') + '</span></div>'
        + '<div class="mb-0"><strong class="erp-detail-label">시공 담당:</strong> <span class="erp-detail-value">' + esc(roles.construction_assignee || '-') + '</span></div>'
        + '</div>'
        + '</div>'
        + '</div>'
        + '</div>';
}
window.buildOrderRoleAssigneesHtml = buildOrderRoleAssigneesHtml;

async function patchOrderDetailAttachments(orderId, itemCount, gen) {
    const container = document.getElementById('order-detail-content-' + orderId);
    if (!container || !container.isConnected) return;
    try {
        const att = await safeJsonFetch('/api/orders/' + orderId + '/attachments', { success: false, attachments: [] });
        if (__orderDetailLoadGen[orderId] !== gen) return;
        if (!container.isConnected) return;
        const aList2 = parseAttachmentsPayload(att);
        __attachmentsCache[orderId] = aList2;
        __attachmentsCacheAt[orderId] = Date.now();
        const countEl = document.getElementById('order-detail-attachments-count-' + orderId);
        const slotEl = document.getElementById('order-detail-attachments-slot-' + orderId);
        if (countEl && countEl.isConnected) countEl.textContent = aList2.length + '개';
        if (slotEl && slotEl.isConnected) {
            slotEl.innerHTML = aList2.length > 0 ? buildMainAttachThumbsHtml(orderId, aList2) : '<div class="text-muted small mt-2">첨부 없음</div>';
        }
        if (typeof __orderDetailImageGroups === 'undefined') window.__orderDetailImageGroups = {};
        if (!window.__orderDetailImageGroups[orderId]) window.__orderDetailImageGroups[orderId] = [];
        for (let idx = 0; idx < itemCount; idx += 1) {
            const itemAtts = aList2.filter(function(a) { return Number(a.item_index) === idx; });
            const imageAtts = itemAtts.filter(orderDetailIsImageFile);
            __orderDetailImageGroups[orderId][idx] = imageAtts;
            const el = document.getElementById('order-detail-item-attach-' + orderId + '-' + idx);
            if (el && el.isConnected) {
                el.outerHTML = buildDwAttachPanelHtml(orderId, idx, itemAtts);
            }
        }
        registerOrderDetailDrawingViewerGroups(orderId);
        container.dataset.loaded = '1';
        container.dataset.attachPhase = 'done';
        delete container.dataset.shellLoaded;
        delete container.dataset.attachError;
        try {
            performance.mark('erp-detail-attach:' + orderId);
            performance.measure('erp-detail-total', 'erp-detail-load-start:' + orderId, 'erp-detail-attach:' + orderId);
            performance.measure('erp-detail-shell-time', 'erp-detail-load-start:' + orderId, 'erp-detail-shell:' + orderId);
        } catch (e) {}
    } catch (e) {
        if (__orderDetailLoadGen[orderId] !== gen) return;
        console.warn('첨부 로드 실패:', orderId, e);
        const slotErr = document.getElementById('order-detail-attachments-slot-' + orderId);
        if (slotErr && slotErr.isConnected) {
            slotErr.innerHTML = '<div class="text-danger small">첨부를 불러오지 못했습니다. 다시 펼쳐 재시도할 수 있습니다.</div>';
        }
        container.dataset.attachPhase = 'error';
        container.dataset.attachError = '1';
    }
}
