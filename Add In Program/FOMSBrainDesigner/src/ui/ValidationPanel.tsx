import { useState } from 'react'
import { useDesignerStore } from '../stores/designerStore'
import { designerApi } from '../api/client'
import type { ValidationResult } from '../domain/designTypes'

/** Validation panel – always visible at the bottom of the left sidebar. */
export function ValidationPanel() {
  const validation = useDesignerStore((s) => s.validation)
  const design = useDesignerStore((s) => s.design)
  const setValidation = useDesignerStore((s) => s.setValidation)
  const projectId = useDesignerStore((s) => s.projectId)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const markSaved = useDesignerStore((s) => s.markSaved)

  const [loading, setLoading] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  async function handleValidate() {
    setLoading(true)
    setSaveMsg(null)
    try {
      const resp = await designerApi.validate(design)
      if (resp.success && resp.data) {
        setValidation(resp.data as ValidationResult)
      } else {
        setSaveMsg(resp.error?.message ?? '검증 요청 실패')
      }
    } catch {
      setSaveMsg('네트워크 오류')
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!projectId) {
      setSaveMsg('프로젝트가 초기화 중입니다. 잠시 후 다시 시도하세요.')
      return
    }
    setLoading(true)
    setSaveMsg(null)
    try {
      // Always validate before save
      const vResp = await designerApi.validate(design)
      if (!vResp.success || !vResp.data) {
        setSaveMsg('검증 요청 실패')
        return
      }
      const v = vResp.data as ValidationResult
      setValidation(v)
      if (!v.valid) {
        setSaveMsg(`오류 ${v.errors.length}개 수정 후 저장하세요.`)
        return
      }
      const resp = await designerApi.createVersion(projectId, design)
      if (resp.success) {
        markSaved()
        setSaveMsg('✓ 저장 완료')
        setTimeout(() => setSaveMsg(null), 3000)
      } else {
        setSaveMsg(resp.error?.message ?? '저장 실패')
      }
    } catch {
      setSaveMsg('네트워크 오류')
    } finally {
      setLoading(false)
    }
  }

  const isValid = validation?.valid ?? null
  const errors = validation?.errors ?? []
  const warnings = validation?.warnings ?? []

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.icon}>✅</span>
        <span style={styles.title}>검증 / 저장</span>
      </div>

      <div style={styles.btnRow}>
        <button
          onClick={handleValidate}
          disabled={loading}
          style={{ ...styles.btn, background: '#2b6cb0', opacity: loading ? 0.6 : 1 }}
        >
          {loading ? '...' : '검증'}
        </button>
        <button
          onClick={handleSave}
          disabled={loading || !isDirty}
          style={{
            ...styles.btn,
            background: isDirty ? '#276749' : '#374151',
            opacity: loading || !isDirty ? 0.6 : 1,
            cursor: !isDirty ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '...' : '저장'}
        </button>
      </div>

      {/* Feedback message */}
      {saveMsg && (
        <div style={{
          ...styles.feedbackMsg,
          color: saveMsg.startsWith('✓') ? '#48bb78' : '#fc8181',
        }}>
          {saveMsg}
        </div>
      )}

      {/* Validation result */}
      {validation && !saveMsg && (
        <div style={styles.result}>
          <div style={{
            color: isValid ? '#48bb78' : '#fc8181',
            fontWeight: 600, fontSize: 11, marginBottom: 4,
          }}>
            {isValid ? '✅ 검증 통과' : `❌ 오류 ${errors.length}개`}
          </div>
          {errors.map((e) => (
            <div key={e.code} style={styles.errorItem}>
              <span style={styles.code}>{e.code}</span>
              <span style={styles.msg}>{e.message}</span>
            </div>
          ))}
          {warnings.map((w) => (
            <div key={w.code} style={{ ...styles.errorItem, background: '#744210' }}>
              <span style={styles.code}>{w.code}</span>
              <span style={{ ...styles.msg, color: '#fbd38d' }}>{w.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    background: '#16213e',
    borderTop: '1px solid #2d3748',
    padding: '10px 12px',
    flexShrink: 0,
  },
  header: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 },
  icon: { fontSize: 14 },
  title: { color: '#a0aec0', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' },
  btnRow: { display: 'flex', gap: 8, marginBottom: 6 },
  btn: {
    flex: 1, padding: '7px 0', border: 'none', borderRadius: 5,
    color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer',
    transition: 'opacity 0.15s',
  },
  feedbackMsg: { fontSize: 11, padding: '4px 0', textAlign: 'center' as const },
  result: { maxHeight: 100, overflowY: 'auto' },
  errorItem: {
    background: '#742a2a', borderRadius: 4,
    padding: '3px 6px', marginBottom: 3,
    display: 'flex', flexDirection: 'column',
  },
  code: { color: '#fc8181', fontSize: 9, fontWeight: 700 },
  msg: { color: '#feb2b2', fontSize: 10 },
}
