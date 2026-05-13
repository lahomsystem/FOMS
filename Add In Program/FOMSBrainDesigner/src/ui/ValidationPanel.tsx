/**
 * ValidationPanel — 제약 규칙 결과 표시 + 저장 버튼.
 * DK-B6: constraintResult를 실시간으로 표시.
 * invalid design은 저장 버튼을 차단.
 */

import { useState } from 'react'
import { useDesignerStore } from '../stores/designerStore'
import { designerApi } from '../api/client'

export function ValidationPanel() {
  const design = useDesignerStore((s) => s.design)
  const constraintResult = useDesignerStore((s) => s.constraintResult)
  const projectId = useDesignerStore((s) => s.projectId)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const markSaved = useDesignerStore((s) => s.markSaved)

  const [loading, setLoading] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  const isValid = constraintResult?.valid ?? true
  const errorCount = constraintResult?.errorCount ?? 0
  const warningCount = constraintResult?.warningCount ?? 0

  const errors = constraintResult?.violations.filter(v => v.severity === 'error') ?? []
  const warnings = constraintResult?.violations.filter(v => v.severity === 'warning') ?? []

  async function handleSave() {
    if (!projectId) {
      setSaveMsg('프로젝트가 초기화 중입니다.')
      return
    }
    if (!isValid) {
      setSaveMsg(`오류 ${errorCount}개 수정 후 저장하세요.`)
      return
    }
    setLoading(true)
    setSaveMsg(null)
    try {
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

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.title}>검증 / 저장</span>
        <div style={styles.badges}>
          {errorCount > 0 && <span style={styles.errBadge}>오류 {errorCount}</span>}
          {warningCount > 0 && <span style={styles.warnBadge}>경고 {warningCount}</span>}
          {isValid && errorCount === 0 && <span style={styles.okBadge}>✓</span>}
        </div>
      </div>

      {/* Save button */}
      <button
        onClick={handleSave}
        disabled={loading || !isDirty || !isValid}
        style={{
          ...styles.saveBtn,
          background: (!isDirty || !isValid) ? '#374151' : '#276749',
          cursor: (!isDirty || !isValid) ? 'not-allowed' : 'pointer',
          opacity: (loading || !isDirty || !isValid) ? 0.6 : 1,
        }}
      >
        {loading ? '저장 중...' : !isValid ? '오류 수정 필요' : isDirty ? '저장' : '저장됨'}
      </button>

      {saveMsg && (
        <div style={{ ...styles.feedbackMsg, color: saveMsg.startsWith('✓') ? '#68d391' : '#fc8181' }}>
          {saveMsg}
        </div>
      )}

      {/* Constraint violations */}
      {(errors.length > 0 || warnings.length > 0) && (
        <div style={styles.violations}>
          {errors.slice(0, 5).map((v, i) => (
            <div key={i} style={styles.errorItem}>
              <span style={styles.code}>{v.code}</span>
              <span style={styles.msg}>{v.message}</span>
            </div>
          ))}
          {warnings.slice(0, 3).map((v, i) => (
            <div key={i} style={{ ...styles.errorItem, background: '#744210' }}>
              <span style={styles.code}>{v.code}</span>
              <span style={{ ...styles.msg, color: '#fbd38d' }}>{v.message}</span>
            </div>
          ))}
          {errors.length > 5 && (
            <div style={styles.more}>+ {errors.length - 5}개 더…</div>
          )}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { background: '#16213e', borderTop: '1px solid #2d3748', padding: '10px 12px', flexShrink: 0 },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  title: { color: '#a0aec0', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' },
  badges: { display: 'flex', gap: 4 },
  errBadge: { background: '#742a2a', color: '#fc8181', borderRadius: 4, padding: '1px 6px', fontSize: 10, fontWeight: 700 },
  warnBadge: { background: '#744210', color: '#f6e05e', borderRadius: 4, padding: '1px 6px', fontSize: 10, fontWeight: 700 },
  okBadge: { background: '#1c4532', color: '#68d391', borderRadius: 4, padding: '1px 6px', fontSize: 10, fontWeight: 700 },
  saveBtn: {
    width: '100%',
    padding: '7px 0',
    border: 'none',
    borderRadius: 5,
    color: '#fff',
    fontSize: 12,
    fontWeight: 700,
    transition: 'opacity 0.15s',
    marginBottom: 6,
  },
  feedbackMsg: { fontSize: 11, padding: '2px 0', textAlign: 'center' },
  violations: { maxHeight: 120, overflowY: 'auto', marginTop: 6 },
  errorItem: { background: '#742a2a', borderRadius: 4, padding: '3px 6px', marginBottom: 3, display: 'flex', flexDirection: 'column' },
  code: { color: '#fc8181', fontSize: 9, fontWeight: 700 },
  msg: { color: '#feb2b2', fontSize: 10 },
  more: { color: '#718096', fontSize: 10, textAlign: 'center', padding: 2 },
}
