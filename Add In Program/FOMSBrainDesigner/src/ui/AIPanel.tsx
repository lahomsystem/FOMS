import { useState } from 'react'
import { useDesignerStore } from '../stores/designerStore'
import { designerApi } from '../api/client'
import type { AIRun } from '../domain/designTypes'

/** AI Assistant panel – create runs, poll status, approve/reject interrupts. */
export function AIPanel() {
  const aiPrompt = useDesignerStore((s) => s.aiPrompt)
  const setAIPrompt = useDesignerStore((s) => s.setAIPrompt)
  const aiRun = useDesignerStore((s) => s.aiRun)
  const setAIRun = useDesignerStore((s) => s.setAIRun)
  const projectId = useDesignerStore((s) => s.projectId)
  const design = useDesignerStore((s) => s.design)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    if (!aiPrompt.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const resp = await designerApi.createAIRun({
        project_id: projectId,
        prompt: aiPrompt,
        design_json: design,
      })
      if (resp.success && resp.data) {
        const run = resp.data as AIRun
        setAIRun(run)
        pollRun(run.id)
      } else {
        setError(resp.error?.message ?? 'AI 실행 실패')
      }
    } catch (e) {
      setError('네트워크 오류')
    } finally {
      setSubmitting(false)
    }
  }

  function pollRun(runId: number) {
    const interval = setInterval(async () => {
      try {
        const resp = await designerApi.getAIRun(runId)
        if (resp.success && resp.data) {
          const run = resp.data as AIRun
          setAIRun(run)
          if (['succeeded', 'failed', 'cancelled', 'interrupt'].includes(run.status)) {
            clearInterval(interval)
          }
        } else {
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 2000)
  }

  async function handleResume(decision: 'approve' | 'reject') {
    if (!aiRun) return
    try {
      const resp = await designerApi.resumeAIRun(aiRun.id, decision)
      if (resp.success && resp.data) {
        const run = resp.data as AIRun
        setAIRun(run)
        if (run.status === 'running' || run.status === 'queued') {
          pollRun(run.id)
        }
      }
    } catch (e) {
      setError('재개 실패')
    }
  }

  const statusColor: Record<string, string> = {
    queued: '#ed8936',
    running: '#667eea',
    interrupt: '#f6ad55',
    succeeded: '#48bb78',
    failed: '#fc8181',
    cancelled: '#718096',
  }

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.icon}>🤖</span>
        <span style={styles.title}>AI 설계 보조</span>
      </div>

      <div style={styles.inputArea}>
        <textarea
          value={aiPrompt}
          onChange={(e) => setAIPrompt(e.target.value)}
          placeholder="AI에게 설계 요청을 입력하세요&#10;예: 가로 폭을 2700mm로 변경해줘"
          style={styles.textarea}
          rows={4}
          disabled={submitting || aiRun?.status === 'running' || aiRun?.status === 'queued'}
        />
        <button
          onClick={handleSubmit}
          disabled={submitting || !aiPrompt.trim() || aiRun?.status === 'running' || aiRun?.status === 'queued'}
          style={{
            ...styles.btn,
            background: submitting ? '#4a5568' : '#667eea',
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          {submitting ? '실행 중...' : 'AI 실행'}
        </button>
      </div>

      {error && <div style={styles.error}>{error}</div>}

      {aiRun && (
        <div style={styles.runCard}>
          <div style={styles.runHeader}>
            <span style={styles.runId}>Run #{aiRun.id}</span>
            <span style={{ color: statusColor[aiRun.status] ?? '#718096', fontSize: 12, fontWeight: 600 }}>
              {aiRun.status.toUpperCase()}
            </span>
          </div>

          {aiRun.status === 'interrupt' && (
            <div style={styles.interruptBox}>
              <div style={styles.interruptMsg}>AI가 검토를 요청합니다</div>
              <div style={styles.interruptBtns}>
                <button onClick={() => handleResume('approve')} style={{ ...styles.btn, background: '#276749', flex: 1 }}>
                  ✅ 승인
                </button>
                <button onClick={() => handleResume('reject')} style={{ ...styles.btn, background: '#742a2a', flex: 1 }}>
                  ❌ 거부
                </button>
              </div>
            </div>
          )}

          {aiRun.status === 'succeeded' && aiRun.output_json !== null && (
            <div style={styles.outputBox}>
              <div style={styles.outputTitle}>결과</div>
              <pre style={styles.outputPre}>
                {JSON.stringify(aiRun.output_json as object, null, 2)}
              </pre>
            </div>
          )}

          {aiRun.status === 'failed' && aiRun.error_text && (
            <div style={styles.error}>{aiRun.error_text}</div>
          )}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { width: 260, background: '#16213e', borderLeft: '1px solid #2d3748', padding: 12, overflowY: 'auto', flexShrink: 0 },
  header: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid #2d3748' },
  icon: { fontSize: 18 },
  title: { color: '#e2e8f0', fontWeight: 600, fontSize: 13 },
  inputArea: { display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 },
  textarea: { background: '#1a1a2e', border: '1px solid #2d3748', borderRadius: 6, color: '#e2e8f0', padding: 8, fontSize: 12, resize: 'vertical', outline: 'none', fontFamily: 'inherit' },
  btn: { padding: '8px 12px', border: 'none', borderRadius: 6, color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' },
  error: { background: '#742a2a', color: '#fc8181', fontSize: 11, padding: 8, borderRadius: 6, marginBottom: 8 },
  runCard: { background: '#1a1a2e', borderRadius: 8, padding: 10, border: '1px solid #2d3748' },
  runHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  runId: { color: '#718096', fontSize: 12 },
  interruptBox: { display: 'flex', flexDirection: 'column', gap: 8 },
  interruptMsg: { color: '#f6ad55', fontSize: 12 },
  interruptBtns: { display: 'flex', gap: 8 },
  outputBox: { marginTop: 8 },
  outputTitle: { color: '#48bb78', fontSize: 11, fontWeight: 600, marginBottom: 4 },
  outputPre: { color: '#a0aec0', fontSize: 10, overflow: 'auto', maxHeight: 150, whiteSpace: 'pre-wrap' },
}
