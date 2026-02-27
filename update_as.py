import os

def update_as_dashboard():
    path = "templates/erp_as_dashboard.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    start_tag = "        asUploadInput.addEventListener('change', async function () {"
    end_tag = "        });\n      }\n    })();\n\n    // AS 방문일 자동 저장"
    
    if start_tag not in content or end_tag not in content:
        print("Could not find targets in AS dashboard")
        return

    before = content.split(start_tag)[0]
    after = content.split(end_tag)[1]

    new_logic = """        asUploadInput.addEventListener('change', async function () {
          var orderId = __currentAsModalOrderId;
          var files = this.files ? Array.from(this.files) : [];
          this.value = '';
          if (!orderId || files.length === 0) return;
          asUploadBtn.disabled = true;

          // --- Optimistic UI Start ---
          var galleryEl = document.getElementById('erp-attachments-category-gallery');
          if (galleryEl) {
              const emptyText = galleryEl.querySelector('.text-muted');
              if (emptyText && emptyText.textContent.includes('없습니다')) {
                  const emptyPanel = emptyText.closest('.col-12');
                  if (emptyPanel) emptyPanel.remove();
              }

              files.forEach((f, fi) => {
                  const uniqueId = 'opt-ul-as-' + Date.now() + '-' + fi;
                  f._optId = uniqueId;
                  const name = typeof escapeHtml === 'function' ? escapeHtml(f.name) : f.name;
                  let previewUrl = '';
                  try { previewUrl = URL.createObjectURL(f); } catch (e) { }

                  const placeholderHtml = `
  <div id="${uniqueId}" class="col-md-4 col-sm-6 col-12 opacity-75">
      <div class="card h-100 bg-light border-dashed">
          <div class="card-body p-2 d-flex flex-column align-items-center justify-content-center position-relative" style="height: 180px;">
              <img src="${previewUrl}" class="rounded mb-2" style="width:100%;height:100px;object-fit:cover;filter:grayscale(80%);">
              <div class="spinner-border text-primary position-absolute" style="top:50%;left:50%;margin-top:-1rem;margin-left:-1rem;" role="status"></div>
              <div class="small text-truncate w-100 text-center" title="${name}">${name}</div>
              <div class="small text-primary fw-bold mt-1 opt-pct">0%</div>
          </div>
      </div>
  </div>`;
                  galleryEl.insertAdjacentHTML('afterbegin', placeholderHtml);
              });
          }
          // --- Optimistic UI End ---

          if (asUploadStatus) {
            asUploadStatus.style.display = 'block';
            asUploadStatus.textContent = '업로드 중... (0/' + files.length + ')';
          }
          
          var ok = 0;
          var category = 'as';
          var folder = 'orders/' + orderId + '/attachments';

          let sessionMap = {};
          try {
              const bRes = await fetch('/api/upload/session/batch', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      files: files.map(f => ({ filename: f.name, size: f.size })),
                      folder: folder,
                      category: category
                  })
              });
              const bData = await bRes.json();
              if (bData.success && bData.sessions) {
                  for (let s of bData.sessions) s.success = true;
                  for (let s of bData.sessions) sessionMap[s.filename] = s;
              }
          } catch (e) { }

          const CONCURRENCY = 10;
          for (let start = 0; start < files.length; start += CONCURRENCY) {
              const chunk = files.slice(start, start + CONCURRENCY);
              const results = await Promise.all(chunk.map(async function (originalFile) {
                  let file = originalFile;
                  if (typeof window.compressImageFile === 'function') {
                      try { file = await window.compressImageFile(originalFile, { quality: 0.8 }); } catch (e) { }
                  }

                  let sess = sessionMap[file.name];
                  if (!sess || !sess.success || !sess.upload_url) {
                      const sessRes = await fetch('/api/upload/session', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ filename: file.name, size: file.size, folder: folder, category: category })
                      });
                      sess = await sessRes.json();
                  }

                  const fallbackForm = async () => {
                      const fd = new FormData();
                      fd.append('file', file);
                      fd.append('category', category);
                      const res = await fetch(`/api/orders/${orderId}/attachments`, { method: 'POST', body: fd });
                      const d = await res.json();
                      return d.success ? { success: true } : d;
                  };

                  if (!sess || !sess.upload_url) return await fallbackForm();

                  let putRes;
                  try {
                      putRes = await fetch(sess.upload_url, {
                          method: 'PUT',
                          headers: { 'Content-Type': file.type || 'application/octet-stream' },
                          body: file
                      });
                  } catch (_) { return await fallbackForm(); }
                  
                  if (!putRes.ok) return await fallbackForm();
                  
                  const completeRes = await fetch(`/api/orders/${orderId}/attachments/complete`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ key: sess.key, filename: file.name, category: category, size: file.size })
                  });
                  return await completeRes.json();
              }));

              for (let i = 0; i < results.length; i++) {
                  if (results[i] && results[i].success) ok++;
              }
              
              const done = Math.min(start + chunk.length, files.length);
              if (asUploadStatus) asUploadStatus.textContent = '업로드 중... (' + done + '/' + files.length + ')';
              
              chunk.forEach(f => {
                  const el = document.getElementById(f._optId);
                  if (el) {
                      const pctSpan = el.querySelector('.opt-pct');
                      if (pctSpan) pctSpan.textContent = '완료';
                  }
              });
          }

          if (asUploadStatus) {
            asUploadStatus.textContent = ok === files.length ? '업로드 완료.' : '업로드 완료 (' + ok + '/' + files.length + ').';
            setTimeout(function () { asUploadStatus.style.display = 'none'; }, 2000);
          }
          asUploadBtn.disabled = false;
          if (ok > 0) await refreshAsModalAttachments();
          if (ok > 0 && typeof showFeedback === 'function') showFeedback('AS 사진 ' + ok + '개가 추가되었습니다.');
"""
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(before + start_tag + "\n" + new_logic[65:] + "\n        });\n      }\n    })();\n\n    // AS 방문일 자동 저장" + after)
    print("Updated AS dashboard upload logic")

update_as_dashboard()
