import re

def update_drawing():
    path = "templates/partials/erp_dashboard_scripts_drawing.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(r'async function uploadRevisionGatewayFiles\(orderId, files\) \{.*?(?=async function loadRevisionHistory)', re.DOTALL)
    
    new_logic = """async function uploadRevisionGatewayFiles(orderId, files) {
  const fileArray = Array.from(files);
  const fallbackFormData = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`/api/orders/${orderId}/drawing-gateway-upload`, { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.success || !data.file) throw new Error(file.name + ' 업로드 실패: ' + (data.message || '알 수 없는 오류'));
    return data.file;
  };

  let sessionMap = {};
  if (USE_DIRECT_UPLOAD) {
      try {
          const folder = `orders/${orderId}/drawing_gateway/revisions`;
          const bRes = await fetch('/api/upload/session/batch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  files: fileArray.map(f => ({ filename: f.name, size: f.size })),
                  folder: folder,
                  category: 'drawing'
              })
          });
          const bData = await bRes.json();
          if (bData.success && bData.sessions) {
              for (let s of bData.sessions) s.success = true;
              for (let s of bData.sessions) sessionMap[s.filename] = s;
          }
      } catch (e) { }
  }

  const uploadOne = async (originalFile) => {
    let file = originalFile;
    if (typeof window.compressImageFile === 'function') {
      try { file = await window.compressImageFile(originalFile, { quality: 0.8 }); } catch (e) {}
    }
    if (USE_DIRECT_UPLOAD) {
      const folder = `orders/${orderId}/drawing_gateway/revisions`;
      let sess = sessionMap[file.name];
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
    const CONCURRENCY = 10;
    for (let start = 0; start < fileArray.length; start += CONCURRENCY) {
        const chunk = fileArray.slice(start, start + CONCURRENCY);
        const results = await Promise.all(chunk.map(f => uploadOne(f)));
        uploadedFiles.push(...results);
    }
    return uploadedFiles;
  } catch (err) {
    throw err;
  }
}

"""
    updated_content = pattern.sub(new_logic, content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated_content)
    print("Updated drawing dashboard uploads")

update_drawing()
