/**
 * CommandPanel — DesignCommand JSON 입력 UI (DK-B7 skeleton).
 * preview/apply 분리. current selection을 target으로 사용.
 */

import { useState } from 'react'
import { useDesignerStore } from '../stores/designerStore'
import { designerApi } from '../api/client'

const DEFAULT_CMD = `{
  "intent": "move_component",
  "source": "manual_json",
  "operation": {
    "axis": "y",
    "delta_mm": 50
  }
}`

export function CommandPanel() {
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const projectId = useDesignerStore((s) => s.projectId)
  const [cmdText, setCmdText] = useState(DEFAULT_CMD)
  const [result, setResult] = useState<string | null>(null)
  const [isError, setIsError] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handlePreview() {
    if (!projectId || !selectedId) {
      setResult('프로젝트 / 선택된 부재가 없습니다.')
      setIsError(true)
      return
    }
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(cmdText)
    } catch {
      setResult('JSON 파싱 오류')
      setIsError(true)
      return
    }
    const cmd = { ...parsed, target: { component_id: selectedId } }
    setLoading(true)
    try {
      const resp = await fetch('/api/designer/commands/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, command: cmd }),
      })
      const data = await resp.json()
      setResult(JSON.stringify(data, null, 2))
      setIsError(!data.success)
    } catch {
      setResult('네트워크 오류')
      setIsError(true)
    } finally {
      setLoading(false)
    }
  }

  async function handleApply() {
    if (!projectId || !selectedId) {
      setResult('프로젝트 / 선택된 부재가 없습니다.')
      setIsError(true)
      return
    }
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(cmdText)
    } catch {
      setResult('JSON 파싱 오류')
      setIsError(true)
      return
    }
    const cmd = { ...parsed, target: { component_id: selectedId }, preview_only: false }
    setLoading(true)
    try {
      const resp = await fetch('/api/designer/commands/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, command: cmd }),
      })
      const data = await resp.json()
      setResult(JSON.stringify(data, null, 2))
      setIsError(!data.success)
    } catch {
      setResult('네트워크 오류')
      setIsError(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.title}>Command JSON</span>
        {selectedId && <span style={styles.targetBadge}>→ {selectedId.slice(0, 8)}…</span>}
      </div>

      <textarea
        value={cmdText}
        onChange={(e) => setCmdText(e.target.value)}
        style={styles.textarea}
        spellCheck={false}
        rows={8}
      />

      <div style={styles.btnRow}>
        <button
          onClick={handlePreview}
          disabled={loading || !selectedId}
          style={{ ...styles.btn, background: '#2b6cb0' }}
        >
          Preview
        </button>
        <button
          onClick={handleApply}
          disabled={loading || !selectedId}
          style={{ ...styles.btn, background: '#276749' }}
        >
          Apply
        </button>
      </div>

      {!selectedId && (
        <div style={styles.hint}>3D 뷰에서 부재를 선택하세요.</div>
      )}

      {result && (
        <pre style={{ ...styles.result, color: isError ? '#fc8181' : '#68d391' }}>
          {result}
        </pre>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { background: '#16213e', padding: 12, overflowY: 'auto', fontSize: 12 },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, borderBottom: '1px solid #2d3748', paddingBottom: 6 },
  title: { color: '#e2e8f0', fontWeight: 700, fontSize: 12 },
  targetBadge: { color: '#667eea', fontSize: 10, background: '#1a1a2e', borderRadius: 4, padding: '1px 6px', fontFamily: 'monospace' },
  textarea: {
    width: '100%',
    background: '#0d1117',
    border: '1px solid #2d3748',
    borderRadius: 4,
    color: '#e2e8f0',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: 8,
    resize: 'vertical',
    outline: 'none',
    boxSizing: 'border-box',
  },
  btnRow: { display: 'flex', gap: 8, margin: '8px 0' },
  btn: { flex: 1, padding: '6px 0', border: 'none', borderRadius: 4, color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer' },
  hint: { color: '#4a5568', fontSize: 11, textAlign: 'center', padding: 4 },
  result: { background: '#0d1117', borderRadius: 4, padding: 8, fontSize: 10, maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginTop: 4 },
}
