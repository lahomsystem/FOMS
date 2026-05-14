/**
 * FOMS Brain AX Designer — Root App Component
 * PG-B1: White SketchUp-Like Workbench Shell
 *
 * Layout:
 *   [TopToolBar]
 *   [LeftToolPalette] [DesignerCanvas] [RightPropertyTray]
 *   [StatusBar]
 */

import { useEffect, useState } from 'react'
import { DesignerCanvas } from './canvas/DesignerCanvas'
import { ModulePanel } from './ui/ModulePanel'
import { ComponentTreePanel } from './ui/ComponentTreePanel'
import { CommandPanel } from './ui/CommandPanel'
import { ValidationPanel } from './ui/ValidationPanel'
import { AIPanel } from './ui/AIPanel'
import { TopToolBar } from './ui/TopToolBar'
import { LeftToolPalette, type ToolMode } from './ui/LeftToolPalette'
import { RightPropertyTray } from './ui/RightPropertyTray'
import { DrawingReviewWorkspace } from './ui/DrawingReviewWorkspace'
import { useDesignerStore } from './stores/designerStore'
import { designerApi } from './api/client'
import { S, COLORS, TYPOGRAPHY, SPACING } from './styles/sketchupTheme'
import type { DesignerProject } from './domain/designTypes'
import type { DesignGraph } from './domain/ontologyTypes'
import { normalize_to_v2_client } from './domain/legacyCompat'

type InitStatus = 'loading' | 'ready' | 'error'
type ViewMode = '3d' | 'front' | 'side' | 'top'

export default function App() {
  const showComponentTree = useDesignerStore((s) => s.showComponentTree)
  const toggleComponentTree = useDesignerStore((s) => s.toggleComponentTree)
  const showAIPanel = useDesignerStore((s) => s.showAIPanel)
  const toggleAI = useDesignerStore((s) => s.toggleAIPanel)
  const project = useDesignerStore((s) => s.project)
  const setProject = useDesignerStore((s) => s.setProject)
  const setDesign = useDesignerStore((s) => s.setDesign)
  const markSaved = useDesignerStore((s) => s.markSaved)

  const undo = useDesignerStore((s) => s.undo)
  const redo = useDesignerStore((s) => s.redo)
  const canUndo = useDesignerStore((s) => s.canUndo)
  const canRedo = useDesignerStore((s) => s.canRedo)
  const removeComponent = useDesignerStore((s) => s.removeComponent)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const loadCandidateGraph = useDesignerStore((s) => s.loadCandidateGraph)

  const [initStatus, setInitStatus] = useState<InitStatus>('loading')
  const [initError, setInitError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('3d')
  const [activeTool, setActiveTool] = useState<ToolMode>('select')
  const [rightTab, setRightTab] = useState<'module' | 'command' | 'tray'>('tray')
  const [appMode, setAppMode] = useState<'editor' | 'review'>('editor')

  // ── Keyboard shortcuts (PG-B9) ──────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      // Don't intercept when typing in inputs
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        if (e.shiftKey) { redo() } else { undo() }
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault()
        redo()
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedId) {
          e.preventDefault()
          removeComponent(selectedId)
        }
      } else if (e.key === 'Escape') {
        useDesignerStore.getState().setSelectedComponent(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo, removeComponent, selectedId])

  // ── postMessage listeners (PG-B8/B9) ────────────────────
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (!e.data) return
      // Load AI candidate into 3D editor (PG-B9)
      if (e.data.type === 'FOMS_LOAD_CANDIDATE' && e.data.candidate) {
        const { furniture_type, factory_params } = e.data.candidate
        loadCandidateGraph({ furniture_type, factory_params: factory_params || {} })
      }
      // Open drawing review workspace (PG-B8)
      if (e.data.type === 'FOMS_REVIEW_EXTRACTION') {
        setAppMode('review')
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [loadCandidateGraph])

  // ── Internal event: load candidate from review workspace ──
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.furniture_type) {
        loadCandidateGraph({
          furniture_type: detail.furniture_type,
          factory_params: detail.factory_params || {},
        })
        setAppMode('editor')
      }
    }
    window.addEventListener('FOMS_LOAD_CANDIDATE_INTERNAL', handler)
    return () => window.removeEventListener('FOMS_LOAD_CANDIDATE_INTERNAL', handler)
  }, [loadCandidateGraph])

  // ── Init ────────────────────────────────────────────────
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
                const v2 = normalize_to_v2_client(p.current_version.design_json as Record<string, unknown>)
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

  // ── Loading / Error screens ─────────────────────────────
  if (initStatus === 'loading') {
    return (
      <div style={{ ...S.root, alignItems: 'center', justifyContent: 'center', gap: 16, background: COLORS.canvasBg }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', border: `3px solid ${COLORS.panelBorder}`, borderTopColor: COLORS.accent, animation: 'spin 0.8s linear infinite' }} />
        <p style={{ color: COLORS.textMuted, fontSize: TYPOGRAPHY.sizeMD }}>프로젝트 초기화 중...</p>
      </div>
    )
  }

  if (initStatus === 'error') {
    return (
      <div style={{ ...S.root, alignItems: 'center', justifyContent: 'center', gap: 16, background: COLORS.canvasBg }}>
        <div style={{ fontSize: 32 }}>⚠️</div>
        <p style={{ color: COLORS.textSecondary, fontSize: TYPOGRAPHY.sizeMD, textAlign: 'center', maxWidth: 320 }}>{initError}</p>
        <button
          style={{ padding: '8px 24px', background: COLORS.accent, border: 'none', borderRadius: 6, color: '#fff', fontSize: TYPOGRAPHY.sizeMD, cursor: 'pointer', fontWeight: TYPOGRAPHY.weightSemibold }}
          onClick={() => window.location.reload()}
        >
          새로고침
        </button>
      </div>
    )
  }

  function handleUploadClick() {
    // Navigate to drawing registration mode in the outer FOMS page
    try {
      window.parent.postMessage({ type: 'FOMS_SWITCH_MODE', mode: 'drawing' }, '*')
    } catch {
      /* cross-origin safe */
    }
  }

  return (
    <div style={S.root}>
      {/* ── App Mode Tab Bar (PG-B8) ── */}
      <div style={{ display: 'flex', background: COLORS.toolbarBg, borderBottom: `1px solid ${COLORS.toolbarBorder}`, padding: '0 8px', height: 30, alignItems: 'center', gap: 4, flexShrink: 0 }}>
        {(['editor', 'review'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => setAppMode(mode)}
            style={{ border: 'none', background: appMode === mode ? COLORS.surfaceWhite : 'transparent', borderRadius: '4px 4px 0 0', padding: '4px 12px', fontSize: TYPOGRAPHY.sizeXS, fontWeight: TYPOGRAPHY.weightSemibold, color: appMode === mode ? COLORS.accent : COLORS.textMuted, cursor: 'pointer', borderBottom: appMode === mode ? `2px solid ${COLORS.accent}` : '2px solid transparent' }}
          >
            {mode === 'editor' ? '🧊 3D 편집기' : '📐 도면 검수'}
          </button>
        ))}
      </div>

      {/* ── Drawing Review Mode (PG-B8) ── */}
      {appMode === 'review' && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <DrawingReviewWorkspace onClose={() => setAppMode('editor')} />
        </div>
      )}

      {/* ── 3D Editor Mode ── */}
      {appMode === 'editor' && (
        <>
      {/* ── Top Toolbar ── */}
      <TopToolBar viewMode={viewMode} onViewModeChange={setViewMode} />

      {/* ── Workspace ── */}
      <div style={S.workspace}>

        {/* Left tool palette */}
        <LeftToolPalette
          activeTool={activeTool}
          onToolChange={setActiveTool}
          onUploadClick={handleUploadClick}
        />

        {/* Module settings panel (collapsible, opens left of canvas) */}
        <div style={{
          width: 200,
          background: COLORS.panelBg,
          borderRight: `1px solid ${COLORS.panelBorder}`,
          flexShrink: 0,
          overflowY: 'auto',
        }}>
          <ModulePanel />
        </div>

        {/* 3D Canvas */}
        <div style={S.canvas}>
          <DesignerCanvas />
        </div>

        {/* Component tree (collapsible) */}
        {showComponentTree && (
          <div style={{
            width: 180,
            background: COLORS.panelBg,
            borderLeft: `1px solid ${COLORS.panelBorder}`,
            flexShrink: 0,
            overflowY: 'auto',
          }}>
            <ComponentTreePanel />
          </div>
        )}

        {/* Right property tray */}
        <div style={{ ...S.tray, flexDirection: 'column' }}>
          {/* Tab selector */}
          <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.panelBorder}`, flexShrink: 0 }}>
            {(['tray', 'command', 'module'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                style={{
                  flex: 1, padding: '5px 0',
                  border: 'none',
                  background: rightTab === tab ? COLORS.surfaceWhite : 'transparent',
                  color: rightTab === tab ? COLORS.textPrimary : COLORS.textMuted,
                  fontSize: TYPOGRAPHY.sizeXS,
                  fontWeight: rightTab === tab ? TYPOGRAPHY.weightSemibold : TYPOGRAPHY.weightNormal,
                  cursor: 'pointer',
                  borderBottom: rightTab === tab ? `2px solid ${COLORS.accent}` : '2px solid transparent',
                }}
              >
                {tab === 'tray' ? '속성' : tab === 'command' ? '명령' : '모듈'}
              </button>
            ))}
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            {rightTab === 'tray' && <RightPropertyTray />}
            {rightTab === 'command' && <CommandPanel />}
            {rightTab === 'module' && <ValidationPanel />}
          </div>
        </div>

        {/* AI Panel (floating) */}
        {showAIPanel && <AIPanel />}
      </div>

      {/* ── Status Bar ── */}
      <div style={S.statusBar}>
        <span>도구: <b style={{ color: COLORS.textPrimary }}>{activeTool}</b></span>
        <span>뷰: <b style={{ color: COLORS.textPrimary }}>{viewMode}</b></span>
        <div style={{ flex: 1 }} />
        <button
          onClick={toggleComponentTree}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: showComponentTree ? COLORS.accent : COLORS.textMuted, fontSize: TYPOGRAPHY.sizeXS }}
        >
          🗂 목록
        </button>
        <button
          onClick={toggleAI}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: showAIPanel ? COLORS.accent : COLORS.textMuted, fontSize: TYPOGRAPHY.sizeXS }}
        >
          🤖 AI
        </button>
        {project && (
          <span style={{ color: COLORS.textMuted, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {project.name}
          </span>
        )}
      </div>
        </>
      )}
    </div>
  )
}
