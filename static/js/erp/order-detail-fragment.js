/**
 * 주문 상세 2단 렌더 공통 첨부 패치 헬퍼.
 * dashboard_scripts_core.html 이후, dashboard_scripts_detail_dom.html 이전에 로드한다.
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

    let attachmentsHtml = '<div class="d-flex flex-wrap gap-1 mt-2">';
    aList.forEach((a) => {
        const name = escapeHtml(a.filename || '');
        const viewUrl = sanitizeAttachmentUrl(a.view_url || '');
        const thumb = sanitizeAttachmentUrl(a.thumbnail_view_url || viewUrl);
        const downloadUrl = sanitizeAttachmentUrl(a.download_url || viewUrl);
        const fileType = a.file_type || 'image';
        const safeViewUrl = String(viewUrl).split("'").join("\\'");
        const safeDownloadUrl = String(downloadUrl).split("'").join("\\'");
        const safeName = String(a.filename || '').split("'").join("\\'");
        const q = String.fromCharCode(39);
        const onclickAttach = 'openAttachmentPreviewModal(' + a.id + ', ' + q + safeViewUrl + q + ', ' + q + safeDownloadUrl + q + ', ' + q + safeName + q + ', ' + q + fileType + q + ')';
        if (fileType === 'video' && viewUrl) {
            attachmentsHtml += '<div class="erp-attach-thumb" onclick="' + onclickAttach + '">' +
                '<div class="erp-attach-thumb-video-bg">' +
                '<video src=\'' + escapeHtml(viewUrl) + '\' preload="metadata" class="erp-attach-thumb-media"></video>' +
                '</div>' +
                '<div class="erp-attach-thumb-play-badge"><i class="fas fa-play"></' + 'i></div>' +
                '</div>';
        } else if (fileType === 'file' || !thumb) {
            attachmentsHtml += '<div class="erp-attach-thumb erp-attach-thumb-file-bg d-flex align-items-center justify-content-center" onclick="' + onclickAttach + '">' +
                '<i class="fas fa-file-alt text-secondary"></' + 'i>' +
                '</div>';
        } else {
            attachmentsHtml += '<div class="erp-attach-thumb" onclick="' + onclickAttach + '">' +
                '<img src=\'' + escapeHtml(thumb) + '\' class="erp-attach-thumb-img" alt=\'' + name + '\'>' +
                '</div>';
        }
    });
    attachmentsHtml += '</div>';
    return attachmentsHtml;
}

function registerOrderDetailDrawingViewerGroups(orderId) {
    if (typeof __drawingGatewayImageGroups !== 'undefined' && window.__orderDetailImageGroups && window.__orderDetailImageGroups[orderId]) {
        (window.__orderDetailImageGroups[orderId] || []).forEach((imageFiles, idx) => {
            __drawingGatewayImageGroups['order_' + orderId + '_item_' + idx] = imageFiles || [];
        });
    }
}

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
