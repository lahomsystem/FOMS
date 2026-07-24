var USE_DIRECT_UPLOAD = (function () {
  if (typeof USE_DIRECT_UPLOAD !== 'undefined') return USE_DIRECT_UPLOAD;
  var el = document.getElementById('erp-dashboard-config');
  var raw = el && el.getAttribute('data-use-direct-upload');
  return raw === 'true' ? true : (raw === 'false' ? false : true);
})();
var __currentTransferOrderId = null;

var __isRetransfer = false;
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
<span class="text-danger fw-bold"><i class="fas fa-exclamation-triangle"></i> 주의: 선택한 번호의 기존 도면만 삭제 후 수정본으로
  교체됩니다.</span><br>
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

const preparedFiles = typeof window.fomsPrepareUploadFiles === 'function'
? await window.fomsPrepareUploadFiles(fileList, {
onPrepareProgress: (info) => {
if (progressBar) {
const p = Math.round((info.done / Math.max(1, info.total)) * 20);
progressBar.style.width = p + '%';
progressBar.textContent = `최적화 ${info.done}/${info.total}`;
}
}
})
: fileList.map((file, index) => ({ clientId: String(index), originalFile: file, file: file }));
const policy = typeof window.fomsGetUploadQueuePolicy === 'function'
? window.fomsGetUploadQueuePolicy()
: { uploadConcurrency: 3 };

const results = await window.fomsRunLimitedQueue(preparedFiles, policy.uploadConcurrency, async (entry, index) => {
let file = entry.file;
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
return { key: att.storage_key, filename: att.filename || file.name, view_url: att.view_url ||
`/api/files/view/${att.storage_key}`, download_url: att.download_url || `/api/files/download/${att.storage_key}` };
}
return null;
}
const upRes = await fetch(`/api/orders/${__currentTransferOrderId}/attachments`, { method: 'POST', body: formData });
const upData = await upRes.json();
if (!upData.success) throw new Error(file.name + ' 업로드 실패: ' + (upData.message || upData.error));
const att = upData.attachment || {};
if (att.storage_key) {
return { key: att.storage_key, filename: att.filename || file.name, view_url: att.view_url ||
`/api/files/view/${att.storage_key}`, download_url: att.download_url || `/api/files/download/${att.storage_key}` };
}
return null;
});

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

async function cancelDrawingRevisionRequest(orderId) {
if (!confirm('수정 요청을 취소하시겠습니까?\n요청 시 첨부한 참고 파일이 함께 삭제되며, 도면 전달 상태로 복귀합니다.')) return;

try {
const res = await fetch(`/api/orders/${orderId}/cancel-revision-request`, { method: 'POST' });
const data = await res.json();
if (data.success) {
showErpToast(data.message || '수정 요청이 취소되었습니다.', 'success');
window.location.reload();
} else {
showErpToast('취소 실패: ' + data.message, 'error');
}
} catch (e) {
console.error(e);
showErpToast('오류가 발생했습니다.', 'error');
}
}

var __currentRevisionOrderId = null;
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
  const fileArray = Array.from(files);
  const fallbackFormData = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`/api/orders/${orderId}/drawing-gateway-upload`, { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.success || !data.file) throw new Error(file.name + ' 업로드 실패: ' + (data.message || '알 수 없는 오류'));
    return data.file;
  };

  let preparedFiles = typeof window.fomsPrepareUploadFiles === 'function'
    ? await window.fomsPrepareUploadFiles(fileArray)
    : fileArray.map((file, index) => ({ clientId: String(index), originalFile: file, file: file }));
  let sessionMap = {};
  if (USE_DIRECT_UPLOAD) {
      try {
          const folder = `orders/${orderId}/drawing_gateway/revisions`;
          const bRes = await fetch('/api/upload/session/batch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  files: preparedFiles.map(entry => ({ client_id: entry.clientId, filename: entry.file.name, size: entry.file.size })),
                  folder: folder,
                  category: 'drawing'
              })
          });
          const bData = await bRes.json();
          if (bData.success && bData.sessions) {
              for (let s of bData.sessions) s.success = true;
              for (let s of bData.sessions) {
                if (s.client_id) sessionMap[s.client_id] = s;
              }
          }
      } catch (e) { }
  }

  const uploadOne = async (entry) => {
    let file = entry.file;
    if (USE_DIRECT_UPLOAD) {
      const folder = `orders/${orderId}/drawing_gateway/revisions`;
      let sess = sessionMap[entry.clientId];
      if (!sess || !sess.success || !sess.upload_url) {
        const sessRes = await fetch('/api/upload/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name, size: file.size, folder: folder })
        });
        sess = await sessRes.json();
      }
      if (!sess || !sess.upload_url) return fallbackFormData(file);

      try {
        const putRes = await fetch(sess.upload_url, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
          body: file
        });
        if (!putRes.ok) return fallbackFormData(file);
      } catch (_) {
        return fallbackFormData(file);
      }
      const completeRes = await fetch(`/api/orders/${orderId}/drawing-gateway/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: sess.key, filename: file.name })
      });
      const data = await completeRes.json();
      if (!data.success || !data.file) throw new Error(file.name + ' 완료 실패: ' + (data.message || '알 수 없는 오류'));
      return data.file;
    }
    return fallbackFormData(file);
  };

  try {
    const uploadedFiles = [];
    const policy = typeof window.fomsGetUploadQueuePolicy === 'function'
      ? window.fomsGetUploadQueuePolicy()
      : { uploadConcurrency: 3 };
    const results = typeof window.fomsRunLimitedQueue === 'function'
      ? await window.fomsRunLimitedQueue(preparedFiles, policy.uploadConcurrency, uploadOne)
      : [];
    uploadedFiles.push(...results);
    return uploadedFiles;
  } catch (err) {
    throw err;
  }
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

var __currentAssignOrderId = null;
var __drawingUsersCache = null;

// P0-21: User.name/team(자기수정 가능) 을 innerHTML 대신 DOM node + textContent 로
// 렌더(cross-user stored XSS 차단). checkbox value 는 정수 id 만 허용.
function renderErpDraftsmanCheckboxList(listEl, users, checkboxName, checkedIds) {
  listEl.replaceChildren();
  (users || []).forEach(u => {
    const uid = Number(u && u.id);
    if (!Number.isInteger(uid)) return;
    const label = document.createElement('label');
    label.className = 'list-group-item d-flex gap-2';
    const input = document.createElement('input');
    input.className = 'form-check-input flex-shrink-0';
    input.type = 'checkbox';
    input.value = String(uid);
    input.name = checkboxName;
    if (checkedIds && checkedIds.includes(u.id)) input.checked = true;
    const span = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = (u && u.name) || '';
    const small = document.createElement('small');
    small.className = 'text-muted ms-1';
    small.textContent = '(' + ((u && u.team) || '') + ')';
    span.append(strong, document.createTextNode(' '), small);
    label.append(input, span);
    listEl.appendChild(label);
  });
}

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
renderErpDraftsmanCheckboxList(listEl, users, 'draftsman_user', currentAssigneeIds);
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
