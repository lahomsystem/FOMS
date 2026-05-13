import { useEffect, useState } from 'react'
import { DesignerCanvas } from './canvas/DesignerCanvas'
import { InspectorPanel } from './ui/InspectorPanel'
import { AIPanel } from './ui/AIPanel'
import { ValidationPanel } from './ui/ValidationPanel'
import { useDesignerStore } from './stores/designerStore'
import { designerApi } from './api/client'
import type { DesignerProject } from './domain/designTypes'

type InitStatus = 'loading' | 'ready' | 'error'

/** Root application component. */
export default function App() {
  const showAIPanel = useDesignerStore((s) => s.showAIPanel)
  const toggleAI = useDesignerStore((s) => s.toggleAIPanel)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const project = useDesignerStore((s) => s.project)
  const setProject = useDesignerStore((s) => s.setProject)
  const setDesign = useDesignerStore((s) => s.setDesign)
  const design = useDesignerStore((s) => s.design)
  const markSaved = useDesignerStore((s) => s.markSaved)

  const [initStatus, setInitStatus] = useState<InitStatus>('loading')
  const [initError, setInitError] = useState<string | null>(null)

  // ─── Auto-initialize project on mount ────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function init() {
      try {
        // 1. Fetch existing projects for this user
        const listResp = await designerApi.listProjects()
        if (cancelled) return

        if (listResp.success && Array.isArray(listResp.data) && listResp.data.length > 0) {
          // Load the most recent project
          const latest = listResp.data[0] as DesignerProject
          setProject(latest)

          // Load latest version design if available
          if (latest.current_version_id) {
            const projResp = await designerApi.getProject(latest.id)
            if (!cancelled && projResp.success && projResp.data) {
              const p = projResp.data as DesignerProject & { current_version?: { design_json: unknown } }
              if (p.current_version?.design_json) {
                setDesign(p.current_version.design_json as typeof design)
                markSaved()
              }
            }
          }
        } else {
          // No projects yet – create a default one
          const createResp = await designerApi.createProject('새 설계 프로젝트')
          if (cancelled) return
          if (createResp.success && createResp.data) {
            setProject(createResp.data as DesignerProject)
            markSaved()
          } else {
            throw new Error(createResp.error?.message ?? '프로젝트 생성 실패')
          }
        }

        if (!cancelled) setInitStatus('ready')
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err)
          // Likely unauthenticated (FOMS session expired)
          if (msg.includes('JSON') || msg.includes('SyntaxError')) {
            setInitError('FOMS 로그인이 필요합니다. 페이지를 새로고침해 주세요.')
          } else {
            setInitError(msg)
          }
          setInitStatus('error')
        }
      }
    }

    init()
    return () => { cancelled = true }
  }, [])

  // ─── Loading / error screen ───────────────────────────────────────────────
  if (initStatus === 'loading') {
    return (
      <div style={styles.centerScreen}>
        <div style={styles.spinner} />
        <p style={styles.centerMsg}>프로젝트 초기화 중...</p>
      </div>
    )
  }

  if (initStatus === 'error') {
    return (
      <div style={styles.centerScreen}>
        <div style={styles.errorIcon}>⚠️</div>
        <p style={styles.centerMsg}>{initError}</p>
        <button style={styles.reloadBtn} onClick={() => window.location.reload()}>
          새로고침
        </button>
      </div>
    )
  }

  // ─── Main layout ─────────────────────────────────────────────────────────
  return (
    <div style={styles.root}>
      {/* Top toolbar */}
      <div style={styles.toolbar}>
        <div style={styles.brand}>
          <span style={styles.brandIcon}>🧠</span>
          <span style={styles.brandName}>FOMS Brain AX Designer</span>
          <span style={styles.version}>v2 MVP</span>
        </div>
        <div style={styles.toolbarCenter}>
          <span style={styles.dimLabel}>
            {design.cabinet.width} × {design.cabinet.height} × {design.cabinet.depth} mm
          </span>
        </div>
        <div style={styles.toolbarActions}>
          {project && (
            <span style={styles.projectBadge} title={`프로젝트 ID: ${project.id}`}>
              📁 {project.name}
            </span>
          )}
          {isDirty
            ? <span style={styles.dirtyBadge}>● 미저장</span>
            : <span style={styles.savedBadge}>✓ 저장됨</span>
          }
          <button
            onClick={toggleAI}
            style={{ ...styles.toolBtn, background: showAIPanel ? '#667eea' : '#2d3748' }}
            title="AI 설계 보조"
          >
            🤖 AI
          </button>
        </div>
      </div>

      {/* Main area */}
      <div style={styles.main}>
        {/* Left sidebar: Inspector (top) + Validation (bottom, always visible) */}
        <div style={styles.leftSidebar}>
          <div style={styles.inspectorWrap}>
            <InspectorPanel />
          </div>
          <ValidationPanel />
        </div>

        {/* Center: 3D Canvas */}
        <div style={styles.canvasWrap}>
          <DesignerCanvas />
        </div>

        {/* Right: AI Panel (collapsible) */}
        {showAIPanel && <AIPanel />}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    width: '100vw', height: '100vh',
    display: 'flex', flexDirection: 'column',
    background: '#1a1a2e',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  toolbar: {
    height: 44, background: '#16213e',
    borderBottom: '1px solid #2d3748',
    display: 'flex', alignItems: 'center',
    padding: '0 12px', gap: 12, flexShrink: 0,
  },
  brand: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 },
  brandIcon: { fontSize: 18 },
  brandName: { color: '#e2e8f0', fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap' },
  version: {
    color: '#4a5568', fontSize: 10, fontWeight: 600,
    background: '#2d3748', padding: '1px 6px', borderRadius: 10,
  },
  toolbarCenter: { flex: 1, display: 'flex', justifyContent: 'center' },
  dimLabel: { color: '#718096', fontSize: 12 },
  toolbarActions: { display: 'flex', alignItems: 'center', gap: 8 },
  projectBadge: {
    color: '#a0aec0', fontSize: 11, maxWidth: 160,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  dirtyBadge: { color: '#ed8936', fontSize: 11 },
  savedBadge: { color: '#48bb78', fontSize: 11 },
  toolBtn: {
    padding: '5px 12px', border: 'none', borderRadius: 5,
    color: '#e2e8f0', fontSize: 12, cursor: 'pointer', fontWeight: 600,
  },
  main: { flex: 1, display: 'flex', overflow: 'hidden' },
  leftSidebar: {
    width: 220, display: 'flex', flexDirection: 'column',
    background: '#16213e', borderRight: '1px solid #2d3748', flexShrink: 0,
  },
  inspectorWrap: { flex: 1, overflowY: 'auto' },
  canvasWrap: { flex: 1, position: 'relative', overflow: 'hidden' },
  centerScreen: {
    width: '100vw', height: '100vh',
    display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center',
    background: '#1a1a2e', gap: 16,
  },
  spinner: {
    width: 36, height: 36, borderRadius: '50%',
    border: '3px solid #2d3748', borderTopColor: '#667eea',
    animation: 'spin 0.8s linear infinite',
  },
  centerMsg: { color: '#a0aec0', fontSize: 14 },
  errorIcon: { fontSize: 36 },
  reloadBtn: {
    padding: '8px 20px', background: '#667eea', border: 'none',
    borderRadius: 6, color: '#fff', fontSize: 13, cursor: 'pointer', fontWeight: 600,
  },
}
