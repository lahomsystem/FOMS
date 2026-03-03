        // 주문의 첨부 파일 미리보기 (첨부 배지 클릭 시) - 좌우 네비게이션 지원
        async function openAttachmentsPreview(orderId, initialCategory = 'measurement') {
          try {
            // 캐시 확인
            let aList = null;
            if (__attachmentsCache[orderId]) {
              aList = __attachmentsCache[orderId];
            } else {
              const res = await fetch(`/api/orders/${orderId}/attachments`);
              const data = await res.json();
              aList = (data && data.attachments) || [];
              __attachmentsCache[orderId] = aList;
            }

            if (aList.length > 0) {
              __attachmentsByCategory = { measurement: [], drawing: [], construction: [], as: [] };
              aList.forEach((a) => {
                const key = normalizeAttachmentCategory(a.category);
                const normalized = Object.assign({}, a, { category: key });
                if (!__attachmentsByCategory[key]) __attachmentsByCategory[key] = [];
                __attachmentsByCategory[key].push(normalized);
              });

              let targetCategory = normalizeAttachmentCategory(initialCategory);
              const targetList = __attachmentsByCategory[targetCategory] || [];
              if (!targetList.length) {
                if (__attachmentsByCategory.drawing.length) targetCategory = 'drawing';
                else if (__attachmentsByCategory.measurement.length) targetCategory = 'measurement';
                else if (__attachmentsByCategory.construction.length) targetCategory = 'construction';
                else if (__attachmentsByCategory.as && __attachmentsByCategory.as.length) targetCategory = 'as';
              }
              __activeAttachmentCategory = targetCategory;

              renderAttachmentCategoryTabs();
              renderAttachmentCategoryGallery();
              const modalEl = document.getElementById('erpAttachmentsCategoryModal');
              if (modalEl) {
                const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                modal.show();
              }
            } else {
              showErpToast('첨부 파일이 없습니다.', 'info');
            }
          } catch (err) {
            console.error('첨부 파일 로드 실패:', err);
            showErpToast('첨부 파일을 불러올 수 없습니다.', 'error');
          }
        }

        // GlobalImageViewer로 연결하는 레거시 호환 함수
        function openAttachmentPreviewModal(attachmentId, viewUrl, downloadUrl, filename, fileType) {
          if (window.GlobalImageViewer) {
            const singleFile = {
              view_url: viewUrl,
              download_url: downloadUrl,
              filename: filename,
              file_type: fileType
            };

            // 같은 주문의 첨부 캐시가 있으면 이미지 묶음으로 열어 좌우 이동 가능하게 처리
            const orderMatch = String(viewUrl || '').match(/\/orders\/(\d+)\//);
            const orderId = orderMatch ? Number(orderMatch[1]) : 0;
            const cached = orderId ? (__attachmentsCache[orderId] || []) : [];

            const isImage = (a) => {
              if (!a) return false;
              const ft = String(a.file_type || '').toLowerCase();
              if (ft === 'image') return true;
              const probe = String(a.view_url || a.filename || '').toLowerCase();
              return /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif)(\?|$)/.test(probe);
            };

            if (String(fileType || '').toLowerCase() === 'image' && Array.isArray(cached) && cached.length > 1) {
              const imageFiles = cached
                .filter(isImage)
                .map((a) => ({
                  view_url: a.view_url || '',
                  download_url: a.download_url || (a.view_url || ''),
                  filename: a.filename || '이미지',
                  file_type: 'image',
                  key: a.storage_key || ''
                }))
                .filter((a) => !!a.view_url);

              if (imageFiles.length > 1) {
                let startIndex = 0;
                if (attachmentId) {
                  const idxById = cached.filter(isImage).findIndex((a) => Number(a.id || 0) === Number(attachmentId));
                  if (idxById >= 0) startIndex = idxById;
                }
                if (startIndex === 0) {
                  const idxByUrl = imageFiles.findIndex((a) => String(a.view_url) === String(viewUrl));
                  if (idxByUrl >= 0) startIndex = idxByUrl;
                }
                window.GlobalImageViewer.open(imageFiles, startIndex);
                return;
              }
            }

            // 기본: 단일 파일로 열기
            window.GlobalImageViewer.open([singleFile], 0);
          } else {
            console.error('GlobalImageViewer not found');
            alert('이미지 뷰어를 불러올 수 없습니다.');
          }
        }

        // 특정 인덱스의 첨부 파일 표시
        function showAttachmentAtIndex(index) {
          if (!__currentAttachmentList || index < 0 || index >= __currentAttachmentList.length) {
            return;
          }

          __currentAttachmentIndex = index;
          
          if (window.GlobalImageViewer) {
             window.GlobalImageViewer.open(__currentAttachmentList, index);
          } else {
              console.error('GlobalImageViewer not found');
              showErpToast('이미지 뷰어를 불러올 수 없습니다.', 'error');
          }
        }

        function getDrawingCurrentFiles(orderId) {
          const list = __drawingCurrentFilesByOrder[orderId];
          return Array.isArray(list) ? list : [];
        }

        function getDrawingTargetNumber(orderId, key) {
          if (!key) return null;
          const list = getDrawingCurrentFiles(orderId);
          const idx = list.findIndex(f => String((f && f.key) || '') === String(key));
          return idx >= 0 ? (idx + 1) : null;
        }

        function isDrawingImageFile(f) {
          const probe = String((f && f.filename) || (f && f.key) || '').toLowerCase();
          return /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif)(\?|$)/.test(probe);
        }

        function buildDrawingTargetCards(orderId, selectedKey, opts = {}) {
          const files = getDrawingCurrentFiles(orderId);
          const includeNone = !!opts.includeNone;
          const role = opts.role || 'revision';
          const selected = String(selectedKey || '');
          const cards = [];

          if (includeNone) {
            cards.push(`
              <button type="button"
                class="drawing-target-card ${selected ? '' : 'is-active'}"
                data-role="${escapeHtml(role)}"
                data-key="">
                <div class="drawing-target-card-thumb"><i class="fas fa-plus text-secondary"></i></div>
                <div class="drawing-target-card-meta">
                  <span class="num">새 번호 추가</span><br />
                  기존 도면 유지
                </div>
              </button>
            `);
          }

          files.forEach((f, idx) => {
            const key = String((f && f.key) || '');
            const filename = String((f && f.filename) || `도면 ${idx + 1}`);
            const viewUrl = String((f && f.view_url) || (key ? `/api/files/view/${key}` : ''));
            const activeCls = key === selected ? 'is-active' : '';
            const selectedBadge = key === selected ? '<span class="drawing-target-selected-pill">선택됨</span>' : '';
            const thumbHtml = isDrawingImageFile(f)
              ? `<img src="${escapeHtml(viewUrl)}" alt="${escapeHtml(filename)}"${key ? ' data-storage-key="' + escapeHtml(key) + '"' : ''}>`
              : `<i class="fas fa-file-alt text-secondary"></i>`;
            cards.push(`
              <button type="button"
                class="drawing-target-card ${activeCls}"
                data-role="${escapeHtml(role)}"
                data-key="${encodeURIComponent(key)}">
                <div class="drawing-target-card-thumb">${selectedBadge}${thumbHtml}</div>
                <div class="drawing-target-card-meta">
                  <span class="num">${idx + 1}번</span><br />
                  <span title="${escapeHtml(filename)}">${escapeHtml(filename)}</span>
                </div>
              </button>
            `);
          });

          return cards.join('');
        }

        function syncDrawingTargetCardSelection(role, selectedKey) {
          document.querySelectorAll(`.drawing-target-card[data-role="${role}"]`).forEach((el) => {
            const raw = String(el.getAttribute('data-key') || '');
            const key = raw ? decodeURIComponent(raw) : '';
            if (String(selectedKey || '') === key) el.classList.add('is-active');
            else el.classList.remove('is-active');
          });
        }

        function selectDrawingTargetByCard(role, key) {
          const selectedKey = String(key || '');
          if (role === 'revision') {
            const selectEl = document.getElementById('drawing-revision-target-key');
            if (selectEl) selectEl.value = selectedKey;
            syncDrawingTargetCardSelection('revision', selectedKey);
          } else if (role === 'replace') {
            const selectEl = document.getElementById('drawing-transfer-replace-key');
            if (selectEl) selectEl.value = selectedKey;
            syncDrawingTargetCardSelection('replace', selectedKey);
          }
        }

        function renderRevisionTargetSelector(orderId) {
          const cardsEl = document.getElementById('drawing-revision-target-cards');
          const selectEl = document.getElementById('drawing-revision-target-key');
          const helpEl = document.getElementById('drawing-revision-target-help');
          if (!selectEl || !cardsEl) return;
          const files = getDrawingCurrentFiles(orderId);
          let html = '<option value="">도면 선택</option>';
          files.forEach((f, idx) => {
            const key = String((f && f.key) || '');
            const filename = String((f && f.filename) || `도면 ${idx + 1}`);
            html += `<option value="${escapeHtml(key)}">${idx + 1}번 · ${escapeHtml(filename)}</option>`;
          });
          selectEl.innerHTML = html;
          if (files.length === 1) {
            selectEl.value = String((files[0] && files[0].key) || '');
          }
          cardsEl.innerHTML = buildDrawingTargetCards(orderId, selectEl.value, { role: 'revision' });
          syncDrawingTargetCardSelection('revision', selectEl.value);
          if (window.erpReplaceThumbnailsWithPresigned) window.erpReplaceThumbnailsWithPresigned(cardsEl);
          selectEl.onchange = () => syncDrawingTargetCardSelection('revision', selectEl.value);
          if (helpEl) {
            helpEl.textContent = files.length > 1
              ? '여러 장입니다. 수정 요청할 도면 번호를 선택해주세요.'
              : (files.length === 1
                ? '현재 1장입니다. 자동 선택되었습니다.'
                : '현재 전달된 도면이 없습니다.');
          }
        }

        function renderTransferReplaceSelector(orderId, isRetransfer) {
          const wrapEl = document.getElementById('drawing-transfer-replace-wrap');
          const cardsEl = document.getElementById('drawing-transfer-replace-cards');
          const selectEl = document.getElementById('drawing-transfer-replace-key');
          const helpEl = document.getElementById('drawing-transfer-replace-help');
          if (!wrapEl || !selectEl || !cardsEl) return;
          const files = getDrawingCurrentFiles(orderId);
          wrapEl.style.display = files.length ? '' : 'none';
          if (!files.length) {
            selectEl.innerHTML = '<option value="">교체할 도면 없음</option>';
            cardsEl.innerHTML = '';
            return;
          }

          let html = `<option value="">${isRetransfer ? '교체할 도면을 선택하세요' : '선택 안 함 (새 번호로 추가)'}</option>`;
          files.forEach((f, idx) => {
            const key = String((f && f.key) || '');
            const filename = String((f && f.filename) || `도면 ${idx + 1}`);
            html += `<option value="${escapeHtml(key)}">${idx + 1}번 삭제 후 교체 · ${escapeHtml(filename)}</option>`;
          });
          selectEl.innerHTML = html;
          if (isRetransfer && files.length === 1) {
            selectEl.value = String((files[0] && files[0].key) || '');
          } else {
            selectEl.value = '';
          }
          cardsEl.innerHTML = buildDrawingTargetCards(orderId, selectEl.value, { role: 'replace', includeNone: !isRetransfer });
          syncDrawingTargetCardSelection('replace', selectEl.value);
          if (window.erpReplaceThumbnailsWithPresigned) window.erpReplaceThumbnailsWithPresigned(cardsEl);
          selectEl.onchange = () => syncDrawingTargetCardSelection('replace', selectEl.value);
          if (helpEl) {
            helpEl.textContent = isRetransfer
              ? '재전송 시 교체할 번호를 선택하세요. (여러 장이면 필수)'
              : '필요 시 기존 번호를 교체하거나, 선택 안 하면 새 번호로 추가됩니다.';
          }
        }

        function escapeHtml(text) {
          if (!text) return '';
          const div = document.createElement('div');
          div.textContent = String(text);
          return div.innerHTML;
        }

        function showErpToast(message, type = 'info') {
          const id = 'erp-toast-container';
          let container = document.getElementById(id);
          if (!container) {
            container = document.createElement('div');
            container.id = id;
            container.style.position = 'fixed';
            container.style.top = '84px';
            container.style.right = '16px';
            container.style.zIndex = '30000';
            container.style.display = 'grid';
            container.style.gap = '8px';
            container.style.maxWidth = '320px';
            document.body.appendChild(container);
          }
          const palette = {
            success: { bg: '#ecfdf5', bd: '#10b981', fg: '#065f46' },
            error: { bg: '#fef2f2', bd: '#ef4444', fg: '#991b1b' },
            info: { bg: '#eff6ff', bd: '#3b82f6', fg: '#1e3a8a' },
          };
          const p = palette[type] || palette.info;
          const toast = document.createElement('div');
          toast.style.background = p.bg;
          toast.style.border = `1px solid ${p.bd}`;
          toast.style.color = p.fg;
          toast.style.borderRadius = '10px';
          toast.style.padding = '9px 11px';
          toast.style.fontSize = '13px';
          toast.style.boxShadow = '0 6px 16px rgba(0,0,0,0.12)';
          toast.textContent = String(message || '');
          container.appendChild(toast);
          setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.22s ease';
            setTimeout(() => toast.remove(), 240);
          }, 2200);
        }


        // === 표시용 한글 라벨(저장은 영문 코드 유지) ===
        function safeJsonParse(val, fb) { try { var s = String(val || '').trim(); if (!s) return fb || {}; var o = JSON.parse(s); return (o && typeof o === 'object' && !Array.isArray(o)) ? o : (fb || {}); } catch (_) { return fb || {}; } }
        var _cfg = document.getElementById('erp-dashboard-config');
        const TEAM_LABELS = _cfg ? safeJsonParse(_cfg.getAttribute('data-team-labels'), {}) : {};
        const STAGE_LABELS = _cfg ? safeJsonParse(_cfg.getAttribute('data-stage-labels'), {}) : {};
        const CAN_EDIT_ERP_BETA = (document.querySelector('.erp-dashboard')?.dataset?.canEditErpBeta || 'false') === 'true';

        function label(map, code, fallback = '-') {
          if (!code) return fallback;
          return map[code] || code;
        }

        // === 컬럼 폭 조절 (ERPGridBoundaryResize) ===
        window.ERPGridBoundaryResize = (function() {
          let _table = null;
          let _storageKey = null;
          let _resizingColIndex = -1;
          let _startX = 0;
          let _startWidth = 0;
          
          function init(config) {
            const table = config.tableSelector instanceof Element ? config.tableSelector : document.querySelector(config.tableSelector);
            if (!table) return;
            
            _table = table;
            _storageKey = config.storageKey || 'erp-grid-widths';
            
            // 1. 저장된 폭 불러오기
            restoreWidths();
            
            // 2. 리사이저 추가
            addResizers();
            
            // 3. 초기화 버튼 이벤트
            if (config.resetButtonSelector) {
              const btn = document.querySelector(config.resetButtonSelector);
              if (btn) {
                btn.addEventListener('click', resetWidths);
              }
            }
          }
          
          function addResizers() {
            const ths = _table.querySelectorAll('thead th');
            ths.forEach((th, index) => {
              // 마지막 컬럼은 리사이저 제외
              if (index === ths.length - 1) return;
              
              // 이미 리사이저가 있으면 스킵
              if (th.querySelector('.erp-col-resizer')) return;
              
              th.style.position = 'relative';
              
              const resizer = document.createElement('div');
              resizer.className = 'erp-col-resizer';
              resizer.style.position = 'absolute';
              resizer.style.right = '0';
              resizer.style.top = '0';
              resizer.style.bottom = '0';
              resizer.style.width = '5px';
              resizer.style.cursor = 'col-resize';
              resizer.style.zIndex = '100';
              resizer.style.userSelect = 'none';
              
              resizer.addEventListener('mousedown', (e) => startResize(e, th, index));
              // 클릭 이벤트 전파 방지 (정렬 등과 충돌 방지)
              resizer.addEventListener('click', (e) => e.stopPropagation());
              
              th.appendChild(resizer);
            });
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
          }
          
          function startResize(e, th, index) {
            e.preventDefault();
            _resizingColIndex = index;
            _startX = e.pageX;
            _startWidth = th.offsetWidth;
            
            document.body.style.cursor = 'col-resize';
            _table.classList.add('resizing');
          }
          
          function onMouseMove(e) {
            if (_resizingColIndex < 0) return;
            
            const diff = e.pageX - _startX;
            const newWidth = Math.max(50, _startWidth + diff); // 최소 50px
            
            const ths = _table.querySelectorAll('thead th');
            if (ths[_resizingColIndex]) {
              ths[_resizingColIndex].style.width = newWidth + 'px';
              ths[_resizingColIndex].style.minWidth = newWidth + 'px';
              ths[_resizingColIndex].style.maxWidth = newWidth + 'px';
            }
          }
          
          function onMouseUp(e) {
            if (_resizingColIndex >= 0) {
              saveWidths();
              _resizingColIndex = -1;
              document.body.style.cursor = '';
              _table.classList.remove('resizing');
            }
          }
          
          function saveWidths() {
            if (!_storageKey) return;
            const widths = {};
            const ths = _table.querySelectorAll('thead th');
            ths.forEach((th, index) => {
              if (th.style.width) {
                widths[index] = th.style.width;
              }
            });
            try {
              localStorage.setItem(_storageKey, JSON.stringify(widths));
            } catch (e) {
              console.error('컬럼 폭 저장 실패', e);
            }
          }
          
          function restoreWidths() {
            if (!_storageKey) return;
            try {
              const saved = localStorage.getItem(_storageKey);
              if (!saved) return;
              
              const widths = JSON.parse(saved);
              const ths = _table.querySelectorAll('thead th');
              
              Object.keys(widths).forEach(index => {
                if (ths[index]) {
                  const w = widths[index];
                  ths[index].style.width = w;
                  ths[index].style.minWidth = w;
                  ths[index].style.maxWidth = w;
                }
              });
            } catch (e) {
              console.error('컬럼 폭 복원 실패', e);
            }
          }
          
          function resetWidths() {
            if (!_storageKey) return;
            localStorage.removeItem(_storageKey);
            
            const ths = _table.querySelectorAll('thead th');
            ths.forEach(th => {
              th.style.width = '';
              th.style.minWidth = '';
              th.style.maxWidth = '';
            });
            
            // CSS에서 정의된 기본값으로 돌아감 (페이지 리로드 없이 적용됨)
            // 필요하다면 window.location.reload()를 호출할 수도 있음
            showErpToast('컬럼 폭이 초기화되었습니다.', 'success');
          }
          
          return {
            init: init
          };
        })();


        let __selectedOrderId = null;
        let __attachmentsCache = {};
        let __currentAttachmentList = [];
        let __currentAttachmentIndex = 0;
        let __drawingCurrentFilesByOrder = {};
        let __activeAttachmentCategory = 'measurement';
        let __attachmentsByCategory = {
          measurement: [],
          drawing: [],
          construction: [],
          as: []
        };

        const ATTACHMENT_CATEGORY_META = {
          measurement: { label: '실측', icon: 'fa-ruler-combined' },
          drawing: { label: '도면', icon: 'fa-drafting-compass' },
          construction: { label: '시공', icon: 'fa-hammer' },
          as: { label: 'AS', icon: 'fa-wrench' }
        };

        function normalizeAttachmentCategory(category) {
          const c = String(category || '').trim().toLowerCase();
          if (c === 'drawing' || c === 'construction' || c === 'as') return c;
          return 'measurement';
        }

        function getAttachmentCategoryLabel(category) {
          const key = normalizeAttachmentCategory(category);
          return (ATTACHMENT_CATEGORY_META[key] || ATTACHMENT_CATEGORY_META.measurement).label;
        }

        function renderAttachmentCategoryTabs() {
          const tabsEl = document.getElementById('erp-attachments-category-tabs');
          if (!tabsEl) return;
          const keys = ['measurement', 'drawing', 'construction', 'as'];
          tabsEl.innerHTML = keys.map((key) => {
            const meta = ATTACHMENT_CATEGORY_META[key];
            const count = (__attachmentsByCategory[key] || []).length;
            const isActive = key === __activeAttachmentCategory;
            const activeCls = isActive ? 'btn-primary' : 'btn-outline-primary';
            return `
              <button type="button" class="btn btn-sm ${activeCls}" onclick="selectAttachmentCategory('${key}')">
                <i class="fas ${meta.icon}"></i> ${meta.label}
                <span class="badge ${isActive ? 'bg-light text-dark' : 'bg-primary text-white'} ms-1">${count}</span>
              </button>
            `;
          }).join('');
        }

        function renderAttachmentCategoryGallery() {
          const galleryEl = document.getElementById('erp-attachments-category-gallery');
          if (!galleryEl) return;
          const list = __attachmentsByCategory[__activeAttachmentCategory] || [];
          if (!list.length) {
            galleryEl.innerHTML = `
              <div class="col-12">
                <div class="text-muted small p-3 border rounded bg-light">
                  ${getAttachmentCategoryLabel(__activeAttachmentCategory)} 카테고리에 첨부 파일이 없습니다.
                </div>
              </div>
            `;
            return;
          }

          galleryEl.innerHTML = list.map((a, index) => {
            const name = escapeHtml(a.filename || '');
            const type = a.file_type || 'file';
            const thumb = a.thumbnail_view_url || a.view_url || '#';
            const viewUrl = a.view_url || '#';
            const downloadUrl = a.download_url || '#';

            const mediaHtml = (type === 'video')
              ? `<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">
                  <video src="${viewUrl}" controls preload="metadata" style="width:100%;height:100%;"></video>
                </div>`
              : (type === 'image')
                ? `<img src="${thumb}" alt="${name}" class="img-fluid rounded"
                    style="max-height: 180px; object-fit: contain; width:100%; cursor: zoom-in; background:#fff; padding:4px;"
                    onclick="openAttachmentFromCategory('${__activeAttachmentCategory}', ${index})">`
                : `<div class="border rounded d-flex flex-column align-items-center justify-content-center bg-light"
                    style="height: 180px;">
                    <i class="fas fa-file-alt text-secondary mb-2" style="font-size: 2rem;"></i>
                    <div class="small text-muted text-center px-2">문서 파일</div>
                   </div>`;

            return `
              <div class="col-md-4 col-sm-6 col-12">
                <div class="card h-100">
                  <div class="card-body p-2">
                    ${mediaHtml}
                    <div class="d-flex justify-content-between align-items-center mt-2">
                      <div class="small text-truncate" title="${name}" style="max-width: 70%;">${name}</div>
                      <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-secondary" type="button" title="미리보기"
                          onclick="openAttachmentFromCategory('${__activeAttachmentCategory}', ${index})">
                          <i class="fas fa-eye"></i>
                        </button>
                        <a class="btn btn-outline-primary" href="${downloadUrl}" title="다운로드" target="_blank" rel="noopener">
                          <i class="fas fa-download"></i>
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            `;
          }).join('');
        }

        function selectAttachmentCategory(category) {
          __activeAttachmentCategory = normalizeAttachmentCategory(category);
          renderAttachmentCategoryTabs();
          renderAttachmentCategoryGallery();
        }

        function openAttachmentFromCategory(category, index) {
          const key = normalizeAttachmentCategory(category);
          const list = __attachmentsByCategory[key] || [];
          if (!list.length) return;
          __activeAttachmentCategory = key;
          __currentAttachmentList = list;
          showAttachmentAtIndex(index);
        }

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

async function loadOrderDetail(orderId) {
const container = document.getElementById(`order-detail-content-${orderId}`);
if (!container) return;

try {
container.innerHTML = '<div class="text-muted small">로딩 중...</div>';

const [structured, attachments] = await Promise.all([
safeJsonFetch(`/api/orders/${orderId}/structured`, { success: false, structured_data: {} }),
safeJsonFetch(`/api/orders/${orderId}/attachments`, { success: false, attachments: [] }),
]);

if (!structured || !structured.success) {
container.innerHTML = '<div class="text-warning small">상세 정보를 불러올 수 없습니다. 새로고침 후 다시 시도하세요.</div>';
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
const address = addressFull || (addressMain && addressDetail ? `${addressMain} ${addressDetail}`.trim() : addressMain)
|| addressDetail || '-';
// 특이사항: notes 객체에서 읽기 (erpbeta 저장 경로와 일치)
const notes = sd.notes || {};
const addressNote = (notes.address_note || '').trim();
const phoneNote = (notes.phone_note || '').trim();
const measureNote = (notes.measurement_note || '').trim();
const measure = (((sd.schedule || {}).measurement || {}).date) || '-';
const construct = (((sd.schedule || {}).construction || {}).date) || '-';
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

// 첨부 파일 목록 먼저 파싱 (제품 항목별 첨부 패널에서 사용)
let aList = [];
if (attachments) {
if (Array.isArray(attachments)) {
aList = attachments;
} else if (attachments.attachments && Array.isArray(attachments.attachments)) {
aList = attachments.attachments;
} else if (attachments.success !== false && attachments.attachments) {
aList = attachments.attachments;
} else if (attachments.success === false) {
console.warn('Attachments API returned error:', attachments.message || 'Unknown error');
aList = [];
} else {
aList = [];
}
}
__attachmentsCache[orderId] = aList;

// 주문 금액(출고가/예약금/잔금) — 공용 partial과 동일 구조로 템플릿에서 채움
const amountToNum = (v) => (v !== null && v !== undefined && v !== '' &&
Number.isFinite(Number(String(v).replace(/[,원\s]/g, '')))) ? Number(String(v).replace(/[,원\s]/g, '')) : 0;
let orderTotalAmount = 0;
(sd.items || []).forEach((it) => { orderTotalAmount += amountToNum(it.price); });
const payment = (sd.payment && typeof sd.payment === 'object') ? sd.payment : {};
const orderDepositAmount = amountToNum(payment.deposit);
const orderRemainingAmount = Math.max(orderTotalAmount - orderDepositAmount, 0);
const formatAmountKr = (n) => (n !== null && Number.isFinite(n)) ? n.toLocaleString('ko-KR') + '원' : '0원';
let amountBlockHtml = '';
const amountTplEl = document.getElementById('erp-amount-block-tpl');
if (amountTplEl && amountTplEl.textContent) {
amountBlockHtml = amountTplEl.textContent
.replace('__TOTAL__', formatAmountKr(orderTotalAmount))
.replace('__DEPOSIT__', formatAmountKr(orderDepositAmount))
.replace('__REMAINING__', formatAmountKr(orderRemainingAmount));
}

// 제품 항목: dw-product-main-card 구조 (헤더 + 폼 + 첨부 패널)
const items = (sd.items || []) || [];
let itemsHtml = '';
const safeValue = (val) => {
if (val === null || val === undefined || val === '') return '';
return String(val).trim();
};
const isImageFile = (a) => {
const ft = (a.file_type || '').toLowerCase();
if (ft === 'image') return true;
const fn = String(a.filename || '').toLowerCase();
return /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif)(\?|$)/.test(fn);
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
  const priceVal = item.price != null && item.price !== '' ? (Number(item.price) ?
  Number(item.price).toLocaleString('ko-KR') : String(item.price)) : '';
  const productName = escapeHtml(safeValue(item.product_name || item.name) || '-');
  const itemAtts = aList.filter(a => Number(a.item_index) === idx);
  const imageAtts = itemAtts.filter(isImageFile);
  __orderDetailImageGroups[orderId][idx] = imageAtts;

  const groupKey = `order_${orderId}_item_${idx}`;
  let attachPanelHtml = `<div class="dw-attach-panel">
    <div class="small fw-semibold text-muted mb-2"><i class="fas fa-image"></i> 실측 첨부 파일</div>`;
    if (itemAtts.length > 0) {
    const singleClass = itemAtts.length === 1 ? ' dw-attach-grid--single' : '';
    attachPanelHtml += `<div class="dw-attach-grid${singleClass}">`;
      let imageIndex = 0;
      itemAtts.forEach((a) => {
      const name = escapeHtml(a.filename || '');
      const viewUrl = (a.view_url || a.thumbnail_view_url || '#').replace(/'/g, "\\'");
      const downloadUrl = (a.download_url || viewUrl).replace(/'/g, "\\'");
      const fileKey = (a.key || a.storage_key || '').replace(/'/g, "\\'");
      const imgSrc = a.thumbnail_view_url || a.view_url || '#';
      const isImg = isImageFile(a);
      const idxAttr = isImg ? (imageIndex++, imageIndex - 1) : 0;
      const dataAttrs = `data-group-key="${groupKey}" data-index="${idxAttr}" data-view-url="${escapeHtml(a.view_url ||
      '')}" data-download-url="${escapeHtml(a.download_url || '')}" data-filename="${name}"
      data-key="${escapeHtml(fileKey)}"`;
      if (isImg) {
      attachPanelHtml += `<div>
        <div class="dw-attach-thumb" ${dataAttrs}
          onclick="openDrawingGatewayImageViewer(this.dataset.groupKey, Number(this.dataset.index))"><img
            src="${escapeHtml(imgSrc)}" alt="${name}"></div>
        <div class="dw-attach-name">${name}</div>
      </div>`;
      } else {
      attachPanelHtml += `<div>
        <div class="dw-attach-thumb d-flex align-items-center justify-content-center bg-light text-secondary"
          ${dataAttrs}
          onclick="openAttachmentPreviewModal(${a.id || 0}, '${viewUrl}', '${downloadUrl}', '${name.replace(/'/g, "
          \\'")}', '${(a.file_type || ' file')}')"><i class="fas fa-file-alt"></i></div>
        <div class="dw-attach-name">${name}</div>
      </div>`;
      }
      });
      attachPanelHtml += `</div>`;
    } else {
    attachPanelHtml += `<div class="small text-muted">연결된 실측 첨부 파일이 없습니다.</div>`;
    }
    attachPanelHtml += `
  </div>`;

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
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(specW) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-3">
            <label class="form-label mb-1 small text-primary">규격 D(깊이)</label>
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(specD) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-3">
            <label class="form-label mb-1 small text-primary">규격 H(높이)</label>
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(specH) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-6">
            <label class="form-label mb-1 small text-primary">내부</label>
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.internal) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-6">
            <label class="form-label mb-1 small text-primary">색상</label>
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.color) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-6">
            <label class="form-label mb-1 small text-primary">옵션</label>
            <input class="form-control form-control-sm"
              value="${escapeHtml(safeValue(item.option_detail || item.options) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-6">
            <label class="form-label mb-1 small text-primary">손잡이</label>
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.handle) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-6">
            <label class="form-label mb-1 small text-primary">기타 / 설치위치</label>
            <input class="form-control form-control-sm" value="${escapeHtml(safeValue(item.misc) || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-md-6">
            <label class="form-label mb-1 small text-primary">항목 금액(원)</label>
            <input class="form-control form-control-sm" value="${escapeHtml(priceVal || '-')}" readonly
              title="클릭하면 값이 복사됩니다.">
          </div>
          <div class="col-12">
            <label class="form-label mb-1 small text-primary">추가 입력</label>
            <textarea class="form-control form-control-sm" rows="3" readonly
              title="클릭하면 값이 복사됩니다.">${escapeHtml(safeValue(item.extra_input))}</textarea>
          </div>
        </div>
        ${amountBlockHtml}
      </div>
      ${attachPanelHtml}
    </div>
  </div>`;
  });
  gridHtml += '
</div>';
itemsHtml = gridHtml;
} else {
itemsHtml = '<div class="text-muted mt-3" style="font-size: 1rem;">제품 항목 없음</div>';
}

let attachmentsHtml = '';
if (aList.length > 0) {
attachmentsHtml = `<div class="d-flex flex-wrap gap-1 mt-2">`;
  aList.forEach(a => {
  const name = escapeHtml(a.filename || '');
  const viewUrl = a.view_url || '#';
  const thumb = a.thumbnail_view_url || viewUrl;
  const downloadUrl = a.download_url || viewUrl;
  const fileType = a.file_type || 'image';
  if (fileType === 'video') {
  attachmentsHtml += `<div class="position-relative"
    style="width: 80px; height: 60px; cursor: pointer; border: 1px solid #dee2e6; border-radius: 4px; overflow: hidden;"
    onclick="openAttachmentPreviewModal(${a.id}, '${viewUrl.replace(/'/g, " \\'")}', '${downloadUrl.replace(/' /g, "\\'"
    )}', '${name.replace(/' /g, "\\'" )}', 'video' )">
    <div
      style="width: 80px; height: 60px; background: #000; display: flex; align-items: center; justify-content: center;">
      <video src="${viewUrl}" preload="metadata" style="width:100%;height:100%;object-fit:cover;"></video>
    </div>
    <div class="position-absolute top-0 start-0 bg-dark bg-opacity-75 text-white p-1" style="font-size: 10px;"><i
        class="fas fa-play"></i></div>
  </div>`;
  } else if (fileType === 'file') {
  attachmentsHtml += `<div class="position-relative d-flex align-items-center justify-content-center"
    style="width: 80px; height: 60px; cursor: pointer; border: 1px solid #dee2e6; border-radius: 4px; overflow: hidden; background:#f8f9fa;"
    onclick="openAttachmentPreviewModal(${a.id}, '${viewUrl.replace(/'/g, " \\'")}', '${downloadUrl.replace(/' /g, "\\'"
    )}', '${name.replace(/' /g, "\\'" )}', 'file' )">
    <i class="fas fa-file-alt text-secondary"></i>
  </div>`;
  } else {
  attachmentsHtml += `<div class="position-relative"
    style="width: 80px; height: 60px; cursor: pointer; border: 1px solid #dee2e6; border-radius: 4px; overflow: hidden;"
    onclick="openAttachmentPreviewModal(${a.id}, '${viewUrl.replace(/'/g, " \\'")}', '${downloadUrl.replace(/' /g, "\\'"
    )}', '${name.replace(/' /g, "\\'" )}', 'image' )">
    <img src="${thumb}" style="width: 80px; height: 60px; object-fit: cover; background:#fff; display: block;"
      alt="${name}">
  </div>`;
  }
  });
  attachmentsHtml += `</div>`;
} else {
attachmentsHtml = `<div class="text-muted small mt-2">첨부 없음</div>`;
}

// 모바일 여부 확인 (992px 이하)
const isMobile = window.innerWidth <= 992; const basicInfoHtml=isMobile ? '' : ` <div class="col-md-6">
  <div class="card">
    <div class="card-body">
      <h5 class="card-title fw-bold"><i class="fas fa-info-circle text-primary"></i> 기본 정보</h5>
      <div class="erp-detail-text">
        <div class="mb-3"><strong class="erp-detail-label">고객명:</strong> <span
            class="erp-detail-value">${escapeHtml(customer)}</span></div>
        <div class="mb-3"><strong class="erp-detail-label">발주사:</strong> <span
            class="erp-detail-value">${escapeHtml(orderer)}</span></div>
        <div class="mb-3"><strong class="erp-detail-label">연락처:</strong> <span
            class="erp-detail-value">${escapeHtml(phone)}</span></div>
        <div class="mb-3"><strong class="erp-detail-label">주소:</strong> <span
            class="erp-detail-value">${escapeHtml(address)}</span></div>
        <div class="mb-3"><strong class="erp-detail-label">담당자:</strong> <span
            class="erp-detail-value">${escapeHtml(manager)}</span></div>
      </div>
    </div>
  </div>
  </div>`;

  const noteRows = [];
  if (addressNote) {
  noteRows.push(`<div class="mb-3"><strong class="erp-detail-label">주소특이:</strong> <span
      class="erp-detail-value">${escapeHtml(addressNote)}</span></div>`);
  }
  if (phoneNote) {
  noteRows.push(`<div class="mb-3"><strong class="erp-detail-label">연락특이:</strong> <span
      class="erp-detail-value">${escapeHtml(phoneNote)}</span></div>`);
  }
  if (measureNote) {
  noteRows.push(`<div class="mb-3"><strong class="erp-detail-label">실측특이:</strong> <span
      class="erp-detail-value">${escapeHtml(measureNote)}</span></div>`);
  }
  const notesHtml = noteRows.join('');

  const scheduleHtml = `
  <div class="${isMobile ? 'col-12' : 'col-md-6'}">
    <div class="card">
      <div class="card-body">
        <h5 class="card-title fw-bold"><i class="fas fa-calendar text-primary"></i> 일정 및 특이사항</h5>
        <div class="erp-detail-text">
          ${isMobile ? '' : `<div class="mb-3"><strong class="erp-detail-label">실측일:</strong> <span
              class="erp-detail-value">${escapeHtml(measure)}</span></div>
          <div class="mb-3"><strong class="erp-detail-label">시공일:</strong> <span
              class="erp-detail-value">${escapeHtml(construct)}</span></div>`}
          ${notesHtml}
        </div>
      </div>
    </div>
  </div>`;

  // 도면 전달 버튼 (DRAWING 단계일 때만)
  let actionHtml = '';
  if (stage === 'DRAWING') {
  const canEdit = typeof CAN_EDIT_ERP_BETA !== 'undefined' && CAN_EDIT_ERP_BETA;
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

  const assigneeNames = assignees.map(u => u.name).filter(Boolean).join(', ') || (assigneeIds.length ?
  `${assigneeIds.length}명 지정` : '');

  // 1. 도면 담당자 지정 버튼 (수정 권한 + 영업/담당자/관리자/도면팀)
  let assignBtn = '';

  if (canDrawingAssign && (isSalesTeam || isManager || isAdmin || isDrawingTeam)) {
  assignBtn = `
  <button class="btn btn-outline-primary btn-sm" onclick="openDraftsmanAssignModal(${orderId})">
    <i class="fas fa-user-plus"></i> 담당자 지정
  </button>
  `;
  }

  let statusBadge = '';
  let mainBtn = '';


  // --- [수정] 상태별 버튼 로직 강화 ---

  if (drawingStatus === 'TRANSFERRED') {
  statusBadge = `<span class="badge bg-warning text-dark ms-2">확정 대기중</span>`;

  // 1. 영업/담당자/관리자: [수령 확정] OR [수정 요청]
  if (canEdit && (isSalesTeam || isManager || isAdmin)) {
  mainBtn = `
  <div class="d-flex gap-2">
    <button class="btn btn-success flex-grow-1" onclick="confirmDrawingReceipt(${orderId})">
      <i class="fas fa-check-double"></i> 수령 확정
    </button>
    <button class="btn btn-warning" onclick="openRevisionRequestModal(${orderId})">
      <i class="fas fa-undo"></i> 수정 요청
    </button>
  </div>
  `;
  } else {
  // 도면팀인 경우: [재전송] (기존 파일 삭제됨), [전달 취소]
  if (canDrawingWork) {
  mainBtn = `
  <div class="d-flex gap-2">
    <button class="btn btn-primary flex-grow-1" onclick="openTransferDrawingModal(${orderId}, true)">
      <i class="fas fa-sync"></i> 재전송
    </button>
    <button class="btn btn-outline-danger" onclick="cancelDrawingTransfer(${orderId})">
      <i class="fas fa-times"></i> 전달 취소
    </button>
  </div>
  <div class="text-muted small mt-1">
    <i class="fas fa-info-circle"></i> 재전송 시 <span class="text-danger fw-bold">기존 파일이 삭제</span>되고 새 파일로 대체됩니다.
  </div>
  `;
  } else {
  mainBtn = `<button class="btn btn-secondary" disabled>확정 대기중</button>`;
  }
  }
  } else if (drawingStatus === 'RETURNED') {
  statusBadge = `<span class="badge bg-danger ms-2">수정 요청됨</span>`;
  // 수정 요청 상태에서는 도면팀이 다시 재전송(업로드) 해야 함
  if (canDrawingWork) {
  mainBtn = `
  <button class="btn btn-primary" onclick="openTransferDrawingModal(${orderId}, true)">
    <i class="fas fa-paper-plane"></i> 수정본 전달 (재전송)
  </button>
  <div class="text-danger small mt-1">
    <i class="fas fa-exclamation-triangle"></i> 수정 요청 사항을 확인 후 다시 전달해주세요.
  </div>
  `;
  } else {
  mainBtn = `<button class="btn btn-secondary" disabled>수정 작업 대기중</button>`;
  }
  } else {
  // PENDING or WORKING
  statusBadge = `<span class="badge bg-secondary ms-2">작업중</span>`;
  // Only Drawing Team or Assigned Draftsman can transfer (and must have ERP edit permission)
  if (canDrawingWork) {
  mainBtn = `
  <button class="btn btn-primary" onclick="openTransferDrawingModal(${orderId}, false)">
    <i class="fas fa-paper-plane"></i> 도면 전달
  </button>
  `;
  } else {
  // 담당자 미지정이면 도면 전달 불가
  if (!hasAssignee) {
  mainBtn = `<small class="text-muted">도면 작업 대기중 (담당자 미지정)</small>`;
  } else {
  mainBtn = `<button class="btn btn-secondary" disabled>작업 관리는 담당자만 가능</button>`;
  }
  }
  }
  const drawHistory = Array.isArray(sd.drawing_transfer_history) ? sd.drawing_transfer_history : [];
  const gatewayHistoryHtml = renderDrawingGatewayTimeline(drawHistory);
  const revisionRequests = drawHistory
  .filter(h => h && h.action === 'REQUEST_REVISION')
  .slice()
  .reverse();
  const requestTabHtml = revisionRequests.length
  ? revisionRequests.slice(0, 8).map((h, idx) => {
  const when = escapeHtml(h.transferred_at || h.at || '-');
  const requestAtRaw = String(h.at || h.transferred_at || '');
  const requestAtEnc = encodeURIComponent(requestAtRaw);
  const by = escapeHtml(h.by_user_name || '-');
  const byUserId = Number(h.by_user_id || 0) || '';
  const note = escapeHtml(h.note || '요청 메모 없음');
  const targetNo = Number(h.target_drawing_number || 0);
  const targetBadge = targetNo > 0 ? `<span class="badge bg-info text-dark ms-1">${targetNo}번 대상</span>` : '';
  const reviewCheck = (h.review_check && typeof h.review_check === 'object') ? h.review_check : {};
  const isChecked = !!reviewCheck.checked;
  const checkedBy = escapeHtml(reviewCheck.checked_by_name || '-');
  const checkedAt = escapeHtml(reviewCheck.checked_at || '-');
  const pinBadge = idx === 0 ? '<span class="badge bg-danger ms-1">최신 요청</span>' : '';
  const checkBadge = isChecked
  ? `<span class="badge bg-success ms-1">반영 완료</span>`
  : `<span class="badge bg-secondary ms-1">미완료</span>`;
  const toggleBtn = `
  <button class="btn btn-sm ${isChecked ? 'btn-outline-secondary' : 'btn-outline-success'} mt-2"
    onclick="toggleRevisionChecklist(${orderId}, '${requestAtEnc}', '${String(byUserId)}', ${isChecked ? 'false' : 'true'})">
    <i class="fas ${isChecked ? 'fa-rotate-left' : 'fa-check'}"></i>
    ${isChecked ? '완료 해제' : '반영 완료'}
  </button>
  `;
  const checkMeta = isChecked
  ? `<div class="small text-success mt-1"><i class="fas fa-user-check"></i> ${checkedBy} · ${checkedAt}</div>`
  : '';
  return `
  <div class="border rounded p-2 mb-2 bg-white">
    <div class="small text-muted mb-1">${when} · ${by} ${pinBadge} ${checkBadge} ${targetBadge}</div>
    <div class="small">${note}</div>
    ${checkMeta}
    ${toggleBtn}
  </div>
  `;
  }).join('')
  : '<div class="text-muted small">수정 요청 이력이 없습니다.</div>';

  const transferEvents = drawHistory.filter(h => h && h.action === 'TRANSFER');
  const latestTransfer = transferEvents.length ? transferEvents[transferEvents.length - 1] : null;
  const prevTransfer = transferEvents.length > 1 ? transferEvents[transferEvents.length - 2] : null;
  const latestFiles = Array.isArray((latestTransfer || {}).files) ? latestTransfer.files : [];
  const prevFiles = Array.isArray((prevTransfer || {}).files) ? prevTransfer.files : [];
  const compareFilesHtml = `
  <div class="row g-2">
    <div class="col-md-6">
      <div class="border rounded p-2 h-100 bg-light">
        <div class="fw-semibold small mb-1">이전본 ${prevTransfer ? '' : '(없음)'}</div>
        <div class="small text-muted mb-2">${prevTransfer ? escapeHtml(prevTransfer.transferred_at || '-') : '-'}</div>
        ${prevTransfer ? renderGatewayFiles(prevFiles, `wb_prev_${orderId}`) : '<div class="text-muted small">비교할 이전
          전달본이 없습니다.</div>'}
      </div>
    </div>
    <div class="col-md-6">
      <div class="border rounded p-2 h-100 bg-light">
        <div class="fw-semibold small mb-1">최신본 ${latestTransfer ? '' : '(없음)'}</div>
        <div class="small text-muted mb-2">${latestTransfer ? escapeHtml(latestTransfer.transferred_at || '-') : '-'}
        </div>
        ${latestTransfer ? renderGatewayFiles(latestFiles, `wb_latest_${orderId}`) : '<div class="text-muted small">최신
          전달본이 없습니다.</div>'}
      </div>
    </div>
  </div>
  `;

  let currentTaskText = '도면 담당자가 도면 전달을 진행해 주세요.';
  if (!hasAssignee) currentTaskText = '도면 담당자를 먼저 지정해야 합니다.';
  else if (drawingStatus === 'TRANSFERRED') currentTaskText = '주문 담당자가 수령 확정 또는 수정 요청을 선택해야 합니다.';
  else if (drawingStatus === 'RETURNED') currentTaskText = '도면 담당자가 요청사항 반영 후 수정본을 전달해야 합니다.';
  else if (drawingStatus === 'CONFIRMED') currentTaskText = '도면 수령 확정 완료. 다음 단계 진행을 확인해 주세요.';
  const checklist = [
  { label: '도면 담당자 지정', ok: hasAssignee },
  { label: '최신 전달본 확인', ok: latestFiles.length > 0 || (Array.isArray(sd.drawing_current_files) &&
  sd.drawing_current_files.length > 0) },
  { label: '요청사항 검토', ok: drawingStatus !== 'RETURNED' || revisionRequests.length > 0 },
  ];
  const checklistHtml = `
  <div class="bg-white border rounded p-2 mb-2">
    <div class="small fw-semibold mb-1"><i class="fas fa-list-check text-primary"></i> 작업 체크리스트</div>
    ${checklist.map(item => `
    <div class="small ${item.ok ? 'text-success' : 'text-secondary'}">
      <i class="fas ${item.ok ? 'fa-check-circle' : 'fa-circle'}"></i> ${escapeHtml(item.label)}
    </div>
    `).join('')}
  </div>
  `;

  const latestEvent = drawHistory.length ? drawHistory[drawHistory.length - 1] : null;
  const latestAction = (latestEvent && latestEvent.action) || '';
  const latestActionLabel = latestAction === 'TRANSFER'
  ? '도면 전달'
  : (latestAction === 'REQUEST_REVISION'
  ? '수정 요청'
  : (latestAction === 'CANCEL_TRANSFER' ? '전달 취소' : '이력 없음'));
  const latestWho = latestEvent ? escapeHtml(latestEvent.by_user_name || '-') : '-';
  const latestWhen = latestEvent ? escapeHtml(latestEvent.transferred_at || latestEvent.at || '-') : '-';
  const uncheckedRequestCount = revisionRequests.filter((h) => {
  const rc = (h && h.review_check && typeof h.review_check === 'object') ? h.review_check : {};
  return !rc.checked;
  }).length;
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
          <h5 class="card-title fw-bold mb-3"><i class="fas fa-paperclip text-primary"></i> 첨부 파일 <span
              class="badge bg-secondary" style="font-size: 1rem;">${aList.length}개</span></h5>
          ${attachmentsHtml}
        </div>
      </div>
    </div>
  </div>
  `;
  // 이미지 뷰어용 그룹 등록 (openDrawingGatewayImageViewer에서 사용)
  if (typeof __drawingGatewayImageGroups !== 'undefined' && window.__orderDetailImageGroups &&
  window.__orderDetailImageGroups[orderId]) {
  (window.__orderDetailImageGroups[orderId] || []).forEach((imageFiles, idx) => {
  __drawingGatewayImageGroups[`order_${orderId}_item_${idx}`] = imageFiles || [];
  });
  }

  } catch (err) {
  console.error('주문 상세 로드 실패:', err);
  container.innerHTML = '<div class="text-danger small">로드 실패: ' + escapeHtml(err.message) + '</div>';
  }
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

  document.addEventListener('DOMContentLoaded', () => {
  initErpDashboardBoundaryResize();
  // URL 파라미터로 특정 주문 하이라이트 및 퀘스트 확장 (도면 수령확정 후 이동 등)
  (() => {
  const urlParams = new URLSearchParams(window.location.search);
  const focusOrder = urlParams.get('focus_order');
  const openQuest = urlParams.get('open_quest') === 'true';

  if (focusOrder) {
  setTimeout(() => {
document.addEventListener('DOMContentLoaded', function () {

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

// 주문 상세 collapse 오픈 시: 상세 로드 완료 후 navbar 바로 아래로 정렬
document.querySelectorAll('.collapse[id^="order-detail-collapse-"]').forEach(collapseEl => {
collapseEl.addEventListener('shown.bs.collapse', async function () {
const orderId = this.id.replace('order-detail-collapse-', '');

const alignDetailUnderNavbar = () => {
const nav = document.querySelector('nav.navbar');
const navHeight = nav ? nav.offsetHeight : 56;
const titleEl = this.querySelector('.erp-order-detail-title') || this;
const targetTop = window.scrollY + titleEl.getBoundingClientRect().top - navHeight - 8;
window.scrollTo({ top: Math.max(0, targetTop), behavior: 'auto' });
};

// 1차: collapse 오픈 직후 정렬
alignDetailUnderNavbar();

// 2차: 상세 내용 렌더 완료 후 다시 정렬 (높이 변동 보정)
await loadOrderDetail(parseInt(orderId, 10));
requestAnimationFrame(alignDetailUnderNavbar);
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

// 이벤트 위임: 퀘스트 승인, 첨부 미리보기 등
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

// 도면 수정 창구 이미지 뷰어 초기화
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
});
        var USE_DIRECT_UPLOAD = typeof USE_DIRECT_UPLOAD !== 'undefined' ? USE_DIRECT_UPLOAD : "xxx";
        let __currentTransferOrderId = null;

        let __isRetransfer = false;
        function openTransferDrawingModal(orderId, isRetransfer = false) {
          __currentTransferOrderId = orderId;
          __isRetransfer = isRetransfer;

          // Reset Inputs
          document.getElementById('drawing-transfer-files').value = '';
          document.getElementById('drawing-transfer-note').value = '';
          const replaceSelectEl = document.getElementById('drawing-transfer-replace-key');
          if (replaceSelectEl) replaceSelectEl.value = '';

          // Update Modal Title/Text based on mode
          const titleEl = document.querySelector('#erpDrawingTransferModal .modal-title');
          const descEl = document.querySelector('#erpDrawingTransferModal .modal-body p');
          const submitBtn = document.querySelector('#erpDrawingTransferModal .modal-footer .btn-primary');

          if (isRetransfer) {
            titleEl.innerHTML = '<i class="fas fa-sync"></i> 도면 재전송 (수정본)';
            descEl.innerHTML = `
            <span class="text-danger fw-bold"><i class="fas fa-exclamation-triangle"></i> 주의: 선택한 번호의 기존 도면만 삭제 후 수정본으로 교체됩니다.</span><br>
            수정본 파일을 업로드하고 교체할 번호를 선택하세요.
          `;
            submitBtn.innerHTML = '<i class="fas fa-sync"></i> 재전송하기';
            submitBtn.classList.replace('btn-primary', 'btn-warning');
          } else {
            titleEl.innerHTML = '<i class="fas fa-paper-plane"></i> 도면 전달 및 파일 업로드';
            descEl.innerHTML = `
             작업 완료된 도면 파일을 업로드하고 전달 사항을 입력하세요.<br>
             전달 후 상태가 <strong>'확정 대기'</strong>로 변경되며 담당자에게 알림이 전송됩니다.
          `;
            submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 전달하기';
            submitBtn.classList.replace('btn-warning', 'btn-primary');
          }

          renderTransferReplaceSelector(orderId, isRetransfer);

          const modal = new bootstrap.Modal(document.getElementById('erpDrawingTransferModal'));
          modal.show();
        }

        async function submitDrawingTransfer() {
          if (!__currentTransferOrderId) return;

          const noteInput = document.getElementById('drawing-transfer-note');
          const note = noteInput ? noteInput.value.trim() : '';
          const filesInput = document.getElementById('drawing-transfer-files');
          const files = filesInput ? filesInput.files : [];
          const replaceSelectEl = document.getElementById('drawing-transfer-replace-key');
          const replaceTargetKey = (replaceSelectEl && replaceSelectEl.value) ? String(replaceSelectEl.value).trim() : '';
          const currentFiles = getDrawingCurrentFiles(__currentTransferOrderId);
          if (__isRetransfer && currentFiles.length > 1 && !replaceTargetKey) {
            showErpToast('수정본 재전송 시 교체할 도면 번호를 선택해주세요.', 'info');
            return;
          }

          const msg = __isRetransfer
            ? '선택한 기존 도면이 삭제되고 새 파일로 대체됩니다.\n정말 재전송 하시겠습니까?'
            : '도면을 전달하시겠습니까?';

          if (!confirm(msg)) return;

          let createdFiles = [];

          if (files.length > 0) {
            try {
              const progressWrap = document.getElementById('erp-drawing-transfer-progress');
              const progressBar = document.getElementById('erp-drawing-transfer-progress-bar');
              if (progressWrap) progressWrap.classList.remove('d-none');
              const fileList = Array.from(files);
              const totalFiles = fileList.length;

              const uploadPromises = fileList.map(async (file, index) => {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('category', 'drawing');
                formData.append('note', '[도면 전달 첨부] ' + note);

                if (typeof uploadWithProgress !== 'undefined') {
                  const upData = await uploadWithProgress(
                    `/api/orders/${__currentTransferOrderId}/attachments`,
                    formData,
                    {
                      onProgress: (p) => {
                        if (progressBar) {
                          const totalPercent = Math.round(((index + p / 100) / totalFiles) * 100);
                          progressBar.style.width = totalPercent + '%';
                          progressBar.textContent = totalPercent + '%';
                        }
                      }
                    }
                  );
                  if (!upData.success) throw new Error(file.name + ' 업로드 실패: ' + (upData.message || upData.error));
                  const att = upData.attachment || {};
                  if (att.storage_key) {
                    return { key: att.storage_key, filename: att.filename || file.name, view_url: att.view_url || `/api/files/view/${att.storage_key}`, download_url: att.download_url || `/api/files/download/${att.storage_key}` };
                  }
                  return null;
                }
                const upRes = await fetch(`/api/orders/${__currentTransferOrderId}/attachments`, { method: 'POST', body: formData });
                const upData = await upRes.json();
                if (!upData.success) throw new Error(file.name + ' 업로드 실패: ' + (upData.message || upData.error));
                const att = upData.attachment || {};
                if (att.storage_key) {
                  return { key: att.storage_key, filename: att.filename || file.name, view_url: att.view_url || `/api/files/view/${att.storage_key}`, download_url: att.download_url || `/api/files/download/${att.storage_key}` };
                }
                return null;
              });

              const results = await Promise.all(uploadPromises);
              createdFiles = results.filter(r => r !== null);
              if (progressWrap) progressWrap.classList.add('d-none');
              if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }
            } catch (e) {
              const progressWrap = document.getElementById('erp-drawing-transfer-progress');
              const progressBar = document.getElementById('erp-drawing-transfer-progress-bar');
              if (progressWrap) progressWrap.classList.add('d-none');
              if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }
              console.error(e);
              showErpToast(e.message || '파일 업로드 중 오류가 발생했습니다.', 'error');
              return;
            }
          }

          try {
            const bodyData = {
              note: note,
              files: createdFiles,
              is_retransfer: __isRetransfer,
              replace_target_key: replaceTargetKey || null,
              replace_target_number: getDrawingTargetNumber(__currentTransferOrderId, replaceTargetKey),
            };

            const res = await fetch(`/api/orders/${__currentTransferOrderId}/transfer-drawing`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(bodyData)
            });
            const data = await res.json();

            if (data.success) {
              showErpToast(data.message || '도면이 전달되었습니다.', 'success');
              const modalEl = document.getElementById('erpDrawingTransferModal');
              const modal = bootstrap.Modal.getInstance(modalEl);
              if (modal) modal.hide();

              window.location.reload();
            } else {
              showErpToast('오류: ' + data.message, 'error');
            }
          } catch (err) {
            console.error('Drawing transfer error:', err);
            showErpToast('도면 전달 중 오류가 발생했습니다.', 'error');
          }
        }

        async function cancelDrawingTransfer(orderId) {
          if (!confirm('정말 도면 전달을 취소하시겠습니까?\n상태가 [작업중]으로 되돌아가며 최신 전달 파일/이력이 정리됩니다.')) return;

          try {
            const res = await fetch(`/api/orders/${orderId}/cancel-transfer`, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
              showErpToast(data.message || '전달이 취소되었습니다.', 'success');
              window.location.reload();
            } else {
              showErpToast('취소 실패: ' + data.message, 'error');
            }
          } catch (e) {
            console.error(e);
            showErpToast('오류가 발생했습니다.', 'error');
          }
        }

        let __currentRevisionOrderId = null;
        function openRevisionRequestModal(orderId) {
          __currentRevisionOrderId = orderId;
          document.getElementById('drawing-revision-note').value = '';
          const revisionTargetSelect = document.getElementById('drawing-revision-target-key');
          if (revisionTargetSelect) revisionTargetSelect.value = '';
          const revisionFilesInput = document.getElementById('drawing-revision-files');
          if (revisionFilesInput) revisionFilesInput.value = '';
          renderRevisionTargetSelector(orderId);
          const modal = new bootstrap.Modal(document.getElementById('erpDrawingRevisionModal'));
          modal.show();
        }

        async function uploadRevisionGatewayFiles(orderId, files) {
          const fallbackFormData = async (file) => {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch(`/api/orders/${orderId}/drawing-gateway-upload`, {
              method: 'POST',
              body: formData
            });
            const data = await res.json();
            if (!data.success || !data.file) {
              throw new Error(file.name + ' 업로드 실패: ' + (data.message || '알 수 없는 오류'));
            }
            return data.file;
          };
          const uploadOne = async (file) => {
            if (USE_DIRECT_UPLOAD) {
              const folder = `orders/${orderId}/drawing_gateway/revisions`;
              const sessRes = await fetch('/api/upload/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: file.name, size: file.size, folder: folder })
              });
              const sess = await sessRes.json();
              if (!sessRes.ok || !sess.success || !sess.upload_url) {
                return fallbackFormData(file);
              }
              let putRes;
              try {
                putRes = await fetch(sess.upload_url, { method: 'PUT', body: file });
              } catch (_) {
                return fallbackFormData(file);
              }
              if (!putRes.ok) return fallbackFormData(file);
              const completeRes = await fetch(`/api/orders/${orderId}/drawing-gateway/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: sess.key, filename: file.name })
              });
              const data = await completeRes.json();
              if (!data.success || !data.file) {
                throw new Error(file.name + ' 완료 실패: ' + (data.message || '알 수 없는 오류'));
              }
              return data.file;
            }
            return fallbackFormData(file);
          };
          return Promise.all(Array.from(files).map(uploadOne));
        }

        async function submitDrawingRevision() {
          if (!__currentRevisionOrderId) return;
          const note = document.getElementById('drawing-revision-note').value.trim();
          const targetSelect = document.getElementById('drawing-revision-target-key');
          const targetKey = targetSelect ? String(targetSelect.value || '').trim() : '';
          const filesInput = document.getElementById('drawing-revision-files');
          const files = filesInput ? Array.from(filesInput.files || []) : [];
          const currentFiles = getDrawingCurrentFiles(__currentRevisionOrderId);
          if (!note) {
            showErpToast('수정 요청 사항(메모)을 입력해주세요.', 'info');
            return;
          }
          if (currentFiles.length > 1 && !targetKey) {
            showErpToast('수정할 도면 번호를 선택해주세요.', 'info');
            return;
          }

          if (!confirm('수정 요청을 보내시겠습니까? (도면팀에게 알림이 전송됩니다)')) return;

          try {
            let uploadedFiles = [];
            if (files.length > 0) {
              uploadedFiles = await uploadRevisionGatewayFiles(__currentRevisionOrderId, files);
            }

            const res = await fetch(`/api/orders/${__currentRevisionOrderId}/request-revision`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                note: note,
                files: uploadedFiles,
                target_drawing_key: targetKey || null,
                target_drawing_number: getDrawingTargetNumber(__currentRevisionOrderId, targetKey),
              })
            });
            const data = await res.json();
            if (data.success) {
              showErpToast(data.message || '수정 요청이 전송되었습니다.', 'success');
              window.location.reload();
            } else {
              showErpToast('요청 실패: ' + data.message, 'error');
            }
          } catch (e) {
            console.error(e);
            showErpToast('오류가 발생했습니다.', 'error');
          }
        }

        async function confirmDrawingReceipt(orderId) {
          if (!confirm('도면 수령을 확정하고 다음 단계로 진행하시겠습니까?')) return;

          try {
            const res = await fetch(`/api/orders/${orderId}/confirm-drawing-receipt`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({})
            });

            const contentType = (res.headers.get('content-type') || '').toLowerCase();
            const data = contentType.includes('application/json')
              ? await res.json()
              : { success: false, message: await res.text() };

            if (data.success) {
              showErpToast(data.message || '수령 확정되었습니다.', 'success');
              window.location.reload();
            } else {
              showErpToast('오류: ' + (data.message || `HTTP ${res.status}`), 'error');
            }
          } catch (err) {
            console.error('Drawing confirm error:', err);
            showErpToast('도면 확정 중 오류가 발생했습니다.', 'error');
          }
        }

        async function toggleRevisionChecklist(orderId, requestAtEnc, byUserId, nextChecked) {
          try {
            const requestAt = decodeURIComponent(String(requestAtEnc || ''));
            const payload = {
              request_at: requestAt,
              by_user_id: byUserId ? Number(byUserId) : null,
              checked: !!nextChecked,
            };
            const res = await fetch(`/api/orders/${orderId}/request-revision-check`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!data.success) {
              showErpToast(data.message || '요청 반영 체크 저장 실패', 'error');
              return;
            }

            showErpToast(data.message || '요청 반영 체크가 저장되었습니다.', 'success');
            await loadOrderDetail(orderId);
          } catch (e) {
            console.error(e);
            showErpToast('요청 반영 체크 저장 중 오류가 발생했습니다.', 'error');
          }
        }

        let __currentAssignOrderId = null;
        let __drawingUsersCache = null;

        async function openDraftsmanAssignModal(orderId) {
          __currentAssignOrderId = orderId;
          const modalEl = document.getElementById('erpDraftsmanAssignModal');
          const listEl = document.getElementById('erp-draftsman-list');
          const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

          modal.show();

          if (!__drawingUsersCache) {
            try {
              const res = await fetch('/erp/api/users?team=DRAWING');
              const data = await res.json();
              if (data.success) {
                __drawingUsersCache = data.users;
              }
            } catch (e) {
              console.error(e);
              listEl.innerHTML = '<div class="text-danger">사용자 목록 로드 실패</div>';
              return;
            }
          }

          let currentAssigneeIds = [];
          try {
            const infoRes = await fetch(`/api/orders/${orderId}/structured`);
            if (infoRes.ok) {
              const infoData = await infoRes.json();
              if (infoData.success && infoData.structured_data) {
                const assignments = infoData.structured_data.assignments || {};
                currentAssigneeIds = assignments.drawing_assignee_user_ids || [];
              }
            }
          } catch (e) {
            console.error('Failed to fetch current assignees:', e);
          }

          const users = __drawingUsersCache || [];
          if (users.length === 0) {
            listEl.innerHTML = '<div class="text-muted text-center">도면팀 사용자가 없습니다.</div>';
          } else {
            listEl.innerHTML = users.map(u => {
              const isChecked = currentAssigneeIds.includes(u.id) ? 'checked' : '';
              return `
                <label class="list-group-item d-flex gap-2">
                    <input class="form-check-input flex-shrink-0" type="checkbox" value="${u.id}" name="draftsman_user" ${isChecked}>
                    <span>
                        <strong>${u.name}</strong>
                        <small class="text-muted ms-1">(${u.team})</small>
                    </span>
                </label>
              `;
            }).join('');
          }
        }

        async function saveDraftsmanAssignment() {
          if (!__currentAssignOrderId) return;

          const checkboxes = document.querySelectorAll('input[name="draftsman_user"]:checked');
          const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

          if (userIds.length === 0) {
            alert('최소 한 명 이상의 담당자를 선택해주세요.');
            return;
          }

          try {
            const res = await fetch(`/api/orders/${__currentAssignOrderId}/assign-draftsman`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user_ids: userIds })
            });
            const data = await res.json();

            if (data.success) {
              alert(data.message);
              bootstrap.Modal.getInstance(document.getElementById('erpDraftsmanAssignModal')).hide();
              loadOrderDetail(__currentAssignOrderId);
            } else {
              alert('오류: ' + data.message);
            }
          } catch (e) {
            console.error(e);
            alert('저장 중 오류가 발생했습니다.');
          }
        }

        function drawingActionLabel(action) {
          const map = {
            TRANSFER: '도면 전달',
            REQUEST_REVISION: '수정 요청',
            CANCEL_TRANSFER: '전달 취소'
          };
          return map[action] || (action || '기타');
        }

        function drawingTargetLabel(h) {
          if (!h || typeof h !== 'object') return '';
          const n = Number(h.target_drawing_number || h.replace_target_number || 0);
          return n > 0 ? `${n}번 대상` : '';
        }

        let __drawingGatewayImageGroups = {};
        let __drawingGatewayViewerFiles = [];
        let __drawingGatewayViewerIndex = 0;
        let __drawingGatewayViewerScale = 1;
        let __drawingGatewayViewerPanX = 0;
        let __drawingGatewayViewerPanY = 0;
        let __drawingGatewayViewerDragging = false;
        let __drawingGatewayViewerStartX = 0;
        let __drawingGatewayViewerStartY = 0;
        let __drawingGatewayViewerStartPanX = 0;
        let __drawingGatewayViewerStartPanY = 0;
        let __drawingGatewayViewerTouchDistance = 0;
        let __drawingGatewayViewerTouchScale = 1;
        let __drawingGatewayViewerBound = false;

        function gatewayFileName(f) {
          return String((f && f.filename) || '첨부파일');
        }

        function gatewayViewUrl(f) {
          return String((f && f.view_url) || ((f && f.key) ? `/api/files/view/${f.key}` : '#'));
        }

        function gatewayDownloadUrl(f) {
          return String((f && f.download_url) || ((f && f.key) ? `/api/files/download/${f.key}` : '#'));
        }

        function isGatewayImageFile(f) {
          const probe = `${gatewayFileName(f)} ${gatewayViewUrl(f)} ${String((f && f.key) || '')}`.toLowerCase();
          return /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif)(\?|$)/.test(probe);
        }

        function getDrawingGatewayViewerElements() {
          return {
            root: document.getElementById('drawing-gateway-image-viewer'),
            backdrop: document.getElementById('drawing-gateway-viewer-backdrop'),
            closeBtn: document.getElementById('drawing-gateway-viewer-close'),
            prevBtn: document.getElementById('drawing-gateway-viewer-prev'),
            nextBtn: document.getElementById('drawing-gateway-viewer-next'),
            stage: document.getElementById('drawing-gateway-viewer-stage'),
            image: document.getElementById('drawing-gateway-viewer-image'),
            zoomBadge: document.getElementById('drawing-gateway-viewer-zoom-badge'),
            filename: document.getElementById('drawing-gateway-viewer-filename'),
            counter: document.getElementById('drawing-gateway-viewer-counter')
          };
        }

        function applyDrawingGatewayViewerTransform() {
          const { image, zoomBadge } = getDrawingGatewayViewerElements();
          if (!image || !zoomBadge) return;
          image.style.transform = `translate(${__drawingGatewayViewerPanX}px, ${__drawingGatewayViewerPanY}px) scale(${__drawingGatewayViewerScale})`;
          zoomBadge.textContent = `${Math.round(__drawingGatewayViewerScale * 100)}%`;
          zoomBadge.style.display = __drawingGatewayViewerScale === 1 ? 'none' : 'block';
          positionDrawingGatewayViewerNav();
        }

        function positionDrawingGatewayViewerNav() {
          const { root, image, prevBtn, nextBtn } = getDrawingGatewayViewerElements();
          if (!root || !image || !prevBtn || !nextBtn) return;
          if (!root.classList.contains('gateway-has-multiple')) return;

          const rootRect = root.getBoundingClientRect();
          const imgRect = image.getBoundingClientRect();
          if (!imgRect.width || !imgRect.height || !rootRect.width || !rootRect.height) return;

          const navSize = 48;
          const edgePad = 10;
          const minX = 12;
          const maxX = Math.max(minX, rootRect.width - navSize - 12);
          const centerY = Math.max(28, Math.min(rootRect.height - 28, (imgRect.top - rootRect.top) + (imgRect.height / 2)));

          let leftX = (imgRect.left - rootRect.left) + edgePad;
          let rightX = (imgRect.right - rootRect.left) - navSize - edgePad;
          leftX = Math.max(minX, Math.min(maxX, leftX));
          rightX = Math.max(minX, Math.min(maxX, rightX));
          if (rightX - leftX < navSize + 12) {
            leftX = Math.max(minX, leftX - 24);
            rightX = Math.min(maxX, rightX + 24);
          }

          prevBtn.style.left = `${leftX}px`;
          prevBtn.style.right = 'auto';
          prevBtn.style.top = `${centerY}px`;

          nextBtn.style.left = `${rightX}px`;
          nextBtn.style.right = 'auto';
          nextBtn.style.top = `${centerY}px`;
        }

        function resetDrawingGatewayViewerTransform() {
          __drawingGatewayViewerScale = 1;
          __drawingGatewayViewerPanX = 0;
          __drawingGatewayViewerPanY = 0;
          applyDrawingGatewayViewerTransform();
        }

        function zoomDrawingGatewayViewerAt(deltaY, clientX, clientY) {
          const { stage } = getDrawingGatewayViewerElements();
          if (!stage) return;
          const rect = stage.getBoundingClientRect();
          const centerX = rect.left + rect.width / 2;
          const centerY = rect.top + rect.height / 2;
          const x = clientX - centerX;
          const y = clientY - centerY;

          const oldScale = __drawingGatewayViewerScale;
          const zoomFactor = deltaY > 0 ? 0.9 : 1.1;
          __drawingGatewayViewerScale = Math.max(0.5, Math.min(10, __drawingGatewayViewerScale * zoomFactor));

          if (__drawingGatewayViewerScale !== oldScale) {
            const ratio = __drawingGatewayViewerScale / oldScale;
            __drawingGatewayViewerPanX = x - (x - __drawingGatewayViewerPanX) * ratio;
            __drawingGatewayViewerPanY = y - (y - __drawingGatewayViewerPanY) * ratio;
          }
          applyDrawingGatewayViewerTransform();
        }

        function updateDrawingGatewayViewerNav() {
          const { prevBtn, nextBtn, counter, root } = getDrawingGatewayViewerElements();
          const total = __drawingGatewayViewerFiles.length;
          const current = __drawingGatewayViewerIndex + 1;
          const hasMultiple = total > 1;
          if (counter) counter.textContent = `${current} / ${total}`;
          if (prevBtn) prevBtn.style.display = hasMultiple ? 'flex' : 'none';
          if (nextBtn) nextBtn.style.display = hasMultiple ? 'flex' : 'none';
          if (root) {
            root.classList.toggle('gateway-has-multiple', hasMultiple);
            if (!hasMultiple) root.classList.remove('gateway-nav-visible');
          }
          requestAnimationFrame(positionDrawingGatewayViewerNav);
        }

        function renderDrawingGatewayViewerImage() {
          const { image, filename } = getDrawingGatewayViewerElements();
          if (!image || !filename) return;
          const current = __drawingGatewayViewerFiles[__drawingGatewayViewerIndex];
          if (!current) return;
          image.src = gatewayViewUrl(current);
          image.alt = gatewayFileName(current);
          filename.textContent = gatewayFileName(current);
          resetDrawingGatewayViewerTransform();
          updateDrawingGatewayViewerNav();
        }

        function showPrevDrawingGatewayImage() {
          if (!__drawingGatewayViewerFiles.length) return;
          __drawingGatewayViewerIndex = (__drawingGatewayViewerIndex - 1 + __drawingGatewayViewerFiles.length) % __drawingGatewayViewerFiles.length;
          renderDrawingGatewayViewerImage();
        }

        function showNextDrawingGatewayImage() {
          if (!__drawingGatewayViewerFiles.length) return;
          __drawingGatewayViewerIndex = (__drawingGatewayViewerIndex + 1) % __drawingGatewayViewerFiles.length;
          renderDrawingGatewayViewerImage();
        }

        function closeDrawingGatewayImageViewer() {
          const { root } = getDrawingGatewayViewerElements();
          if (!root) return;
          root.classList.remove('gateway-nav-visible');
          root.classList.add('d-none');
          root.setAttribute('aria-hidden', 'true');
          document.body.style.overflow = '';
        }

        function openDrawingGatewayImageViewer(groupKey, index) {
          const files = __drawingGatewayImageGroups[groupKey] || [];
          if (!files.length) return;
          
          if (window.GlobalImageViewer) {
             const viewerFiles = files.map(f => ({
                view_url: gatewayViewUrl(f),
                download_url: gatewayDownloadUrl(f),
                filename: gatewayFileName(f),
                file_type: 'image',
                key: (f && f.key) || ''
             }));
             window.GlobalImageViewer.open(viewerFiles, index || 0);
          } else {
             console.error('GlobalImageViewer not found');
             alert('이미지 뷰어를 불러올 수 없습니다.');
          }
        }

        function initDrawingGatewayImageViewer() {
          if (__drawingGatewayViewerBound) return;
          const { backdrop, closeBtn, prevBtn, nextBtn, stage, root, image } = getDrawingGatewayViewerElements();
          if (!stage || !root || !image) return;
          __drawingGatewayViewerBound = true;

          if (backdrop) backdrop.addEventListener('click', closeDrawingGatewayImageViewer);
          if (closeBtn) closeBtn.addEventListener('click', closeDrawingGatewayImageViewer);
          if (prevBtn) prevBtn.addEventListener('click', showPrevDrawingGatewayImage);
          if (nextBtn) nextBtn.addEventListener('click', showNextDrawingGatewayImage);

          root.addEventListener('mouseenter', () => {
            if (root.classList.contains('gateway-has-multiple')) {
              root.classList.add('gateway-nav-visible');
            }
          });
          root.addEventListener('mousemove', () => {
            if (root.classList.contains('gateway-has-multiple')) {
              root.classList.add('gateway-nav-visible');
            }
          });
          root.addEventListener('mouseleave', () => {
            root.classList.remove('gateway-nav-visible');
          });
          image.addEventListener('load', () => requestAnimationFrame(positionDrawingGatewayViewerNav));
          window.addEventListener('resize', () => {
            if (!root.classList.contains('d-none')) requestAnimationFrame(positionDrawingGatewayViewerNav);
          });

          document.addEventListener('keydown', (e) => {
            if (root.classList.contains('d-none')) return;
            if (e.key === 'Escape') closeDrawingGatewayImageViewer();
            else if (e.key === 'ArrowLeft') showPrevDrawingGatewayImage();
            else if (e.key === 'ArrowRight') showNextDrawingGatewayImage();
          });

          stage.addEventListener('wheel', (e) => {
            if (root.classList.contains('d-none')) return;
            e.preventDefault();
            zoomDrawingGatewayViewerAt(e.deltaY, e.clientX, e.clientY);
          }, { passive: false });

          stage.addEventListener('mousedown', (e) => {
            if (__drawingGatewayViewerScale <= 1) return;
            __drawingGatewayViewerDragging = true;
            stage.style.cursor = 'grabbing';
            __drawingGatewayViewerStartX = e.clientX;
            __drawingGatewayViewerStartY = e.clientY;
            __drawingGatewayViewerStartPanX = __drawingGatewayViewerPanX;
            __drawingGatewayViewerStartPanY = __drawingGatewayViewerPanY;
            e.preventDefault();
          });

          document.addEventListener('mousemove', (e) => {
            if (!__drawingGatewayViewerDragging) return;
            __drawingGatewayViewerPanX = __drawingGatewayViewerStartPanX + (e.clientX - __drawingGatewayViewerStartX);
            __drawingGatewayViewerPanY = __drawingGatewayViewerStartPanY + (e.clientY - __drawingGatewayViewerStartY);
            applyDrawingGatewayViewerTransform();
          });

          document.addEventListener('mouseup', () => {
            if (!__drawingGatewayViewerDragging) return;
            __drawingGatewayViewerDragging = false;
            stage.style.cursor = __drawingGatewayViewerScale > 1 ? 'grab' : 'default';
          });

          stage.addEventListener('dblclick', () => resetDrawingGatewayViewerTransform());

          stage.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
              __drawingGatewayViewerStartX = e.touches[0].clientX;
              __drawingGatewayViewerStartY = e.touches[0].clientY;
              __drawingGatewayViewerStartPanX = __drawingGatewayViewerPanX;
              __drawingGatewayViewerStartPanY = __drawingGatewayViewerPanY;
            } else if (e.touches.length === 2) {
              const t1 = e.touches[0];
              const t2 = e.touches[1];
              __drawingGatewayViewerTouchDistance = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
              __drawingGatewayViewerTouchScale = __drawingGatewayViewerScale;
            }
          }, { passive: true });

          stage.addEventListener('touchmove', (e) => {
            if (root.classList.contains('d-none')) return;
            if (e.touches.length === 1 && __drawingGatewayViewerScale > 1) {
              e.preventDefault();
              const t = e.touches[0];
              __drawingGatewayViewerPanX = __drawingGatewayViewerStartPanX + (t.clientX - __drawingGatewayViewerStartX);
              __drawingGatewayViewerPanY = __drawingGatewayViewerStartPanY + (t.clientY - __drawingGatewayViewerStartY);
              applyDrawingGatewayViewerTransform();
            } else if (e.touches.length === 2) {
              e.preventDefault();
              const t1 = e.touches[0];
              const t2 = e.touches[1];
              const distance = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
              __drawingGatewayViewerScale = Math.max(0.5, Math.min(10, __drawingGatewayViewerTouchScale * (distance / (__drawingGatewayViewerTouchDistance || distance))));
              applyDrawingGatewayViewerTransform();
            }
          }, { passive: false });
        }

        function renderGatewayFiles(files, groupKey) {
          if (!Array.isArray(files) || files.length === 0) return '';

          const imageFiles = files.filter(isGatewayImageFile);
          __drawingGatewayImageGroups[groupKey] = imageFiles;

          const imageItems = imageFiles.map((f, idx) => {
            const name = escapeHtml(gatewayFileName(f));
            const viewUrl = escapeHtml(gatewayViewUrl(f));
            const downloadUrl = escapeHtml(gatewayDownloadUrl(f));
            return `
              <div class="drawing-gateway-thumb-wrap me-2 mb-2">
                <div class="drawing-gateway-thumb" onclick="openDrawingGatewayImageViewer('${groupKey}', ${idx})">
                  <img src="${viewUrl}" alt="${name}">
                </div>
                <div class="small text-truncate mt-1" title="${name}" style="max-width: 110px;">${name}</div>
                <a href="${downloadUrl}" target="_blank" rel="noopener" class="small text-muted">
                  <i class="fas fa-download"></i>
                </a>
              </div>
            `;
          }).join('');

          const fileItems = files.filter(f => !isGatewayImageFile(f)).map((f) => {
            const name = escapeHtml(gatewayFileName(f));
            const viewUrl = escapeHtml(gatewayViewUrl(f));
            const downloadUrl = escapeHtml(gatewayDownloadUrl(f));
            return `
              <div class="d-flex align-items-center gap-1 me-2 mb-1">
                <i class="fas fa-paperclip text-secondary"></i>
                <a href="${viewUrl}" target="_blank" rel="noopener" class="small">${name}</a>
                <a href="${downloadUrl}" target="_blank" rel="noopener" class="small text-muted">
                  <i class="fas fa-download"></i>
                </a>
              </div>
            `;
          }).join('');

          return `
            <div class="d-flex flex-wrap mt-1">
              ${imageItems}
              ${fileItems}
            </div>
          `;
        }


        function renderDrawingGatewayTimeline(history) {
          if (!Array.isArray(history) || history.length === 0) {
            return '<div class="text-muted small">아직 요청/전달 이력이 없습니다.</div>';
          }
          const sorted = [...history].reverse();
          return sorted.map((h, idx) => {
            const action = drawingActionLabel(h.action);
            const byName = escapeHtml(h.by_user_name || '알 수 없음');
            const when = escapeHtml(h.transferred_at || h.at || '');
            const note = escapeHtml(h.note || '');
            const targetLabel = escapeHtml(drawingTargetLabel(h));
            const groupKey = `gateway_${idx}_${String(h.transferred_at || h.at || '').replace(/[^0-9A-Za-z]/g, '')}`;
            const filesHtml = renderGatewayFiles(h.files || [], groupKey);
            const badgeClass = h.action === 'REQUEST_REVISION'
              ? 'bg-danger'
              : (h.action === 'TRANSFER' ? 'bg-primary' : 'bg-secondary');
            return `
              <div class="border rounded p-2 mb-2 bg-white">
                <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                  <div>
                    <span class="badge ${badgeClass}">${action}</span>
                    <span class="small text-muted ms-2">${byName}</span>
                    ${targetLabel ? `<span class="badge bg-info text-dark ms-1">${targetLabel}</span>` : ''}
                  </div>
                  <span class="small text-muted">${when}</span>
                </div>
                ${note ? `<div class="small mt-1">${note}</div>` : ''}
                ${filesHtml}
              </div>
            `;
          }).join('');
        }

        function renderBadges(alerts) {
          const a = alerts || {};
          const out = [];
          if (a.urgent) out.push('<span class="badge bg-danger me-1">긴급</span>');
          if (a.drawing_overdue) out.push('<span class="badge bg-danger me-1">도면48h</span>');
          if (a.measurement_d4) out.push('<span class="badge bg-warning text-dark me-1">실측D-4</span>');
          if (a.construction_d3) out.push('<span class="badge bg-warning text-dark me-1">시공D-3</span>');
          if (a.production_d2) out.push('<span class="badge bg-warning text-dark me-1">생산D-2</span>');
          return out.join('') || '<span class="text-muted small">경보 없음</span>';
        }

        async function approveQuestTeam(orderId, team) {
          try {
            const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ team: team })
            });
            const data = await res.json();

            if (!data.success) {
              alert('승인 실패: ' + (data.message || data.error || '알 수 없는 오류'));
              return;
            }

            if (data.auto_transitioned && data.next_stage) {
              const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
              alert('✅ 모든 팀 승인 완료! 다음 단계(' + nextStageLabel + ')로 자동 전환되었습니다.');
            } else if (data.all_approved) {
              alert('✅ 모든 팀 승인 완료!');
            } else {
              const missingTeams = data.missing_teams.map(t => label(TEAM_LABELS, t, t)).join(', ');
              alert('승인 완료. 남은 팀: ' + missingTeams);
            }

            await loadQuestDetail(orderId);
            window.location.reload();
          } catch (err) {
            console.error('승인 실패:', err);
            alert('승인 중 오류가 발생했습니다.');
          }
        }

        async function approveQuestAssignee(orderId) {
          try {
            const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({})
            });
            const data = await res.json();

            if (!data.success) {
              alert('승인 실패: ' + (data.message || data.error || '알 수 없는 오류'));
              return;
            }

            if (data.auto_transitioned && data.next_stage) {
              const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
              alert('✅ 담당자 승인 완료! 다음 단계(' + nextStageLabel + ')로 자동 전환되었습니다.');
            } else if (data.all_approved) {
              alert('✅ 담당자 승인 완료!');
            }

            window.location.reload();
          } catch (err) {
            console.error('승인 실패:', err);
            alert('승인 중 오류가 발생했습니다.');
          }
        }

        async function loadQuestDetail(orderId) {
          try {
            const res = await fetch(`/api/orders/${orderId}/quest`);
            const data = await res.json();
            if (data.error) {
              console.error('Quest 로드 실패:', data.error);
              return;
            }
            const questContainer = document.querySelector(`#quest-collapse-${orderId} #quest-approvals-${orderId}`);
            if (questContainer) {
              const quest = data.quest || {};
              const requiredTeams = quest.required_approvals || [];
              const teamApprovalsRaw = quest.team_approvals || {};

              let html = '';
              for (const team of requiredTeams) {
                const approvalData = teamApprovalsRaw[team];
                let approved = false;
                if (typeof approvalData === 'object' && approvalData !== null) {
                  approved = approvalData.approved === true;
                } else {
                  approved = Boolean(approvalData);
                }
                const teamLabel = label(TEAM_LABELS, team, team);
                html += `<div class="mb-2">`;
                html += `<span class="fw-semibold" style="font-size: 1rem;">${escapeHtml(teamLabel)}</span>`;
                if (approved) {
                  html += `<span class="badge bg-success ms-2" style="font-size: 1rem; padding: 0.4em 0.7em;">승인완료</span>`;
                } else {
                  html += `<button class="btn btn-primary fw-semibold ms-2" onclick="approveQuestTeam(${orderId}, '${escapeHtml(team)}')" style="font-size: 1rem; padding: 0.4rem 0.75rem;">승인</button>`;
                }
                html += `</div>`;
              }
              questContainer.innerHTML = html;
            }
          } catch (err) {
            console.error('Quest 상세 로드 실패:', err);
          }
        }
