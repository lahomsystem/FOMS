import re

def main():
    path = "templates/partials/erp_construction_scripts.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"let ok = 0;[\s\n\r]*const totalFiles = files\.length;[\s\n\r]*try {[\s\n\r]*async function doUploadOne.*?if \(statusEl\) statusEl\.textContent = `업로드 중.*?`;[\s\n\r]*}",
        re.DOTALL
    )

    matches = pattern.findall(content)
    if not matches:
        print("No matches for the 3rd block")
        return
        
    print(f"Found {len(matches)} matches for 3rd block.")

    new_logic = """let ok = 0;
              const totalFiles = files.length;
              try {
              const CONCURRENCY = 10;
              
              let sessionMap = {};
              try {
                  const folder = `orders/${orderId}/attachments`;
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

              async function doUploadOne(originalFile) {
                  let file = originalFile;
                  if (typeof window.compressImageFile === 'function') {
                      try { file = await window.compressImageFile(originalFile, { quality: 0.8 }); } catch (e) {}
                  }
                  try {
                      const folder = `orders/${orderId}/attachments`;
                      let sess = sessionMap[file.name];
                      if (!sess || !sess.success || !sess.upload_url) {
                          const sessRes = await fetch('/api/upload/session', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ filename: file.name, size: file.size, folder: folder, category: category })
                          });
                          sess = await sessRes.json();
                          if (!sess || !sess.success) throw new Error(sess.message || sess.error || '세션 생성 실패');
                      }

                      const putRes = await fetch(sess.upload_url, {
                          method: 'PUT',
                          headers: { 'Content-Type': file.type || 'application/octet-stream' },
                          body: file
                      });
                      if (!putRes.ok) throw new Error('R2 PUT 실패');

                      const completeRes = await fetch(`/api/orders/${orderId}/attachments/complete`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                              key: sess.key,
                              filename: file.name,
                              category: category,
                              item_index: null,
                              size: file.size
                          })
                      });
                      const completeData = await completeRes.json();
                      if (!completeData.success) throw new Error(completeData.message || completeData.error || '첨부 등록 실패');
                      return { success: true };
                  } catch (err) {
                      console.error('Upload error:', err);
                      return { success: false, error: err.message };
                  }
              }

              for (let start = 0; start < files.length; start += CONCURRENCY) {
                  const chunk = files.slice(start, start + CONCURRENCY);
                  const results = await Promise.all(chunk.map(f => doUploadOne(f)));
                  results.forEach(r => { if (r.success) ok++; });

                  const pct = Math.round((Math.min(start + CONCURRENCY, totalFiles) / totalFiles) * 100);
                  if (progressBar) { progressBar.style.width = pct + '%'; progressBar.textContent = pct + '%'; }
                  if (statusEl) statusEl.textContent = `업로드 중... (${Math.min(start + CONCURRENCY, totalFiles)}/${totalFiles})`;
              }"""

    updated_content = pattern.sub(new_logic, content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated_content)
    print("3rd Construction block updated.")

main()
