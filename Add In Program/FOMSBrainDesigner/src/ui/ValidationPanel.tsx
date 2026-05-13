import { useDesignerStore } from '../stores/designerStore'
import { designerApi } from '../api/client'
import type { ValidationResult } from '../domain/designTypes'

/** Validation panel – shows errors/warnings and triggers save. */
export function ValidationPanel() {
  const validation = useDesignerStore((s) => s.validation)
  const design = useDesignerStore((s) => s.design)
  const setValidation = useDesignerStore((s) => s.setValidation)
  const projectId = useDesignerStore((s) => s.projectId)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const markSaved = useDesignerStore((s) => s.markSaved)

  async function handleValidate() {
    const resp = await designerApi.validate(design)
    if (resp.success && resp.data) {
      setValidation(resp.data as ValidationResult)
    }
  }

  async function handleSave() {
    if (!projectId) return
    // Always validate before save
    const vResp = await designerApi.validate(design)
    if (!vResp.success || !vResp.data) return
    const v = vResp.data as ValidationResult
    setValidation(v)
    if (!v.valid) return // blocked by validator

    const resp = await designerApi.createVersion(projectId, design)
    if (resp.success) {
      markSaved()
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
        <button onClick={handleValidate} style={{ ...styles.btn, background: '#2b6cb0' }}>
          검증
        </button>
        <button
          onClick={handleSave}
          disabled={!isDirty || isValid === false}
          style={{
            ...styles.btn,
            background: isValid === true ? '#276749' : '#4a5568',
            cursor: !isDirty || isValid === false ? 'not-allowed' : 'pointer',
          }}
        >
          저장
        </button>
      </div>

      {validation && (
        <div style={styles.result}>
          <div style={{ color: isValid ? '#48bb78' : '#fc8181', fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
            {isValid ? '✅ 검증 통과' : `❌ 오류 ${errors.length}개`}
          </div>

          {errors.map((e) => (
            <div key={e.code} style={styles.errorItem}>
              <span style={styles.code}>{e.code}</span>
              <span style={styles.msg}>{e.message}</span>
              <span style={styles.path}>{e.path}</span>
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

      {!isDirty && isValid && (
        <div style={styles.savedBadge}>✓ 저장됨</div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { background: '#16213e', borderTop: '1px solid #2d3748', padding: '8px 12px', flexShrink: 0 },
  header: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 },
  icon: { fontSize: 16 },
  title: { color: '#e2e8f0', fontWeight: 600, fontSize: 12 },
  btnRow: { display: 'flex', gap: 8, marginBottom: 8 },
  btn: { padding: '6px 14px', border: 'none', borderRadius: 5, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  result: { maxHeight: 120, overflowY: 'auto' },
  errorItem: { background: '#742a2a', borderRadius: 4, padding: '4px 8px', marginBottom: 4, display: 'flex', flexDirection: 'column' },
  code: { color: '#fc8181', fontSize: 10, fontWeight: 600 },
  msg: { color: '#feb2b2', fontSize: 11 },
  path: { color: '#fc8181', fontSize: 10, fontStyle: 'italic' },
  savedBadge: { color: '#48bb78', fontSize: 11, textAlign: 'center' as const, padding: '4px 0' },
}
