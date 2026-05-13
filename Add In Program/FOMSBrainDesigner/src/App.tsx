/**
 * FOMS Brain AX Designer — Root App Component
 * DK-B5/B6: schema v2 기반 UI. ModulePanel, ComponentTreePanel, CommandPanel 추가.
 */

import { useEffect, useState } from 'react'
import { DesignerCanvas } from './canvas/DesignerCanvas'
import { InspectorPanel } from './ui/InspectorPanel'
import { ModulePanel } from './ui/ModulePanel'
import { ComponentTreePanel } from './ui/ComponentTreePanel'
import { CommandPanel } from './ui/CommandPanel'
import { ValidationPanel } from './ui/ValidationPanel'
import { AIPanel } from './ui/AIPanel'
import { useDesignerStore } from './stores/designerStore'
import { designerApi } from './api/client'
import type { DesignerProject } from './domain/designTypes'
import type { DesignGraph } from './domain/ontologyTypes'
import { normalize_to_v2_client } from './domain/legacyCompat'

type InitStatus = 'loading' | 'ready' | 'error'
type RightTab = 'inspector' | 'command'

export default function App() {
  const showAIPanel = useDesignerStore((s) => s.showAIPanel)
  const showComponentTree = useDesignerStore((s) => s.showComponentTree)
  const toggleAI = useDesignerStore((s) => s.toggleAIPanel)
  const toggleComponentTree = useDesignerStore((s) => s.toggleComponentTree)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const project = useDesignerStore((s) => s.project)
  const setProject = useDesignerStore((s) => s.setProject)
  const setDesign = useDesignerStore((s) => s.setDesign)
  const design = useDesignerStore((s) => s.design)
  const markSaved = useDesignerStore((s) => s.markSaved)
  const constraintResult = useDesignerStore((s) => s.constraintResult)

  const [initStatus, setInitStatus] = useState<InitStatus>('loading')
  const [initError, setInitError] = useState<string | null>(null)
  const [rightTab, setRightTab] = useState<RightTab>('inspector')

  useEffect(() => {
    let cancelled = false
    async function init() {
      try {
        const listResp = await designerApi.listProjects()
        if (cancelled) return

        if (listResp.success && Array.isArray(listResp.data) && listResp.data.length > 0) {
          const latest = listResp.data[0] as DesignerProject
          setProject(latest)
          if (latest.current_version_id) {
            const projResp = await designerApi.getProject(latest.id)
            if (!cancelled && projResp.success && projResp.data) {
              const p = projResp.data as DesignerProject & { current_version?: { design_json: unknown } }
              if (p.current_version?.design_json) {
                const loaded = p.current_version.design_json as Record<string, unknown>
                // DK-B9: normalize v1 → v2 on load
                const v2 = normalize_to_v2_client(loaded)
                setDesign(v2 as DesignGraph)
                markSaved()
              }
            }
          }
        } else {
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
          setInitError(msg.includes('JSON') || msg.includes('SyntaxError')
            ? 'FOMS 로그인이 필요합니다. 페이지를 새로고침해 주세요.'
            : msg,
          )
          setInitStatus('error')
        }
      }
    }
    init()
    return () => { cancelled = true }
  }, [])

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
        <button style={styles.reloadBtn} onClick={() => window.location.reload()}>새로고침</button>
      </div>
    )
  }

  const isValid = constraintResult?.valid ?? true
  const asm = design.assembly

  return (
    <div style={styles.root}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <div style={styles.brand}>
          <span style={styles.brandIcon}>🧠</span>
          <span style={styles.brandName}>FOMS Brain AX Designer</span>
          <span style={styles.version}>Design Kernel V1</span>
        </div>
        <div style={styles.toolbarCenter}>
          <span style={styles.dimLabel}>
            {asm.dimensions.width} × {asm.dimensions.height} × {asm.dimensions.depth} mm
          </span>
          <span style={styles.dimSep}>|</span>
          <span style={styles.dimLabel}>{asm.module_count}통 {asm.door_type}</span>
          <span style={styles.dimSep}>|</span>
          <span style={{ ...styles.statusDot, color: isValid ? '#68d391' : '#fc8181' }}>
            {isValid ? '✓ 유효' : `✗ 오류 ${constraintResult?.errorCount}`}
          </span>
        </div>
        <div style={styles.toolbarActions}>
          {project && (
            <span style={styles.projectBadge} title={`ID: ${project.id}`}>
              📁 {project.name}
            </span>
          )}
          {isDirty
            ? <span style={styles.dirtyBadge}>● 미저장</span>
            : <span style={styles.savedBadge}>✓ 저장됨</span>
          }
          <button onClick={toggleComponentTree} style={{ ...styles.toolBtn, background: showComponentTree ? '#667eea' : '#2d3748' }}>
            🗂️ 목록
          </button>
          <button onClick={toggleAI} style={{ ...styles.toolBtn, background: showAIPanel ? '#667eea' : '#2d3748' }}>
            🤖 AI
          </button>
        </div>
      </div>

      {/* Main layout */}
      <div style={styles.main}>
        {/* Left: Module settings */}
        <div style={styles.leftSidebar}>
          <ModulePanel />
          <ValidationPanel />
        </div>

        {/* Center: 3D Canvas */}
        <div style={styles.canvasWrap}>
          <DesignerCanvas />
        </div>

        {/* Right: Component tree (collapsible) */}
        {showComponentTree && (
          <div style={styles.rightSidebar}>
            <ComponentTreePanel />
          </div>
        )}

        {/* Far right: Inspector + Command tabs */}
        <div style={styles.inspectorSidebar}>
          <div style={styles.tabs}>
            <button
              onClick={() => setRightTab('inspector')}
              style={{ ...styles.tab, background: rightTab === 'inspector' ? '#2d3748' : 'transparent' }}
            >
              Inspector
            </button>
            <button
              onClick={() => setRightTab('command')}
              style={{ ...styles.tab, background: rightTab === 'command' ? '#2d3748' : 'transparent' }}
            >
              Command
            </button>
          </div>
          <div style={styles.tabContent}>
            {rightTab === 'inspector' && <InspectorPanel />}
            {rightTab === 'command' && <CommandPanel />}
          </div>
        </div>

        {/* AI Panel */}
        {showAIPanel && <AIPanel />}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: { width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: '#1a1a2e', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  toolbar: { height: 44, background: '#16213e', borderBottom: '1px solid #2d3748', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 12, flexShrink: 0 },
  brand: { display: 'flex', alignItems: 'center', gap: 6 },
  brandIcon: { fontSize: 18 },
  brandName: { color: '#e2e8f0', fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap' },
  version: { color: '#4a5568', fontSize: 10, fontWeight: 600, background: '#2d3748', padding: '1px 6px', borderRadius: 10 },
  toolbarCenter: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 },
  dimLabel: { color: '#718096', fontSize: 12 },
  dimSep: { color: '#2d3748' },
  statusDot: { fontSize: 11, fontWeight: 700 },
  toolbarActions: { display: 'flex', alignItems: 'center', gap: 8 },
  projectBadge: { color: '#a0aec0', fontSize: 11, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  dirtyBadge: { color: '#ed8936', fontSize: 11 },
  savedBadge: { color: '#68d391', fontSize: 11 },
  toolBtn: { padding: '5px 10px', border: 'none', borderRadius: 5, color: '#e2e8f0', fontSize: 12, cursor: 'pointer', fontWeight: 600 },
  main: { flex: 1, display: 'flex', overflow: 'hidden' },
  leftSidebar: { width: 200, display: 'flex', flexDirection: 'column', background: '#16213e', borderRight: '1px solid #2d3748', flexShrink: 0, overflowY: 'auto' },
  canvasWrap: { flex: 1, position: 'relative', overflow: 'hidden' },
  rightSidebar: { width: 180, background: '#16213e', borderLeft: '1px solid #2d3748', flexShrink: 0, overflowY: 'auto' },
  inspectorSidebar: { width: 220, display: 'flex', flexDirection: 'column', background: '#16213e', borderLeft: '1px solid #2d3748', flexShrink: 0 },
  tabs: { display: 'flex', borderBottom: '1px solid #2d3748', flexShrink: 0 },
  tab: { flex: 1, padding: '6px 0', border: 'none', color: '#a0aec0', fontSize: 11, cursor: 'pointer', fontWeight: 600 },
  tabContent: { flex: 1, overflowY: 'auto' },
  centerScreen: { width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#1a1a2e', gap: 16 },
  spinner: { width: 36, height: 36, borderRadius: '50%', border: '3px solid #2d3748', borderTopColor: '#667eea' },
  centerMsg: { color: '#a0aec0', fontSize: 14 },
  errorIcon: { fontSize: 36 },
  reloadBtn: { padding: '8px 20px', background: '#667eea', border: 'none', borderRadius: 6, color: '#fff', fontSize: 13, cursor: 'pointer', fontWeight: 600 },
}
