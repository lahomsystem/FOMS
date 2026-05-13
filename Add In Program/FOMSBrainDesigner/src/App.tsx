import { DesignerCanvas } from './canvas/DesignerCanvas'
import { InspectorPanel } from './ui/InspectorPanel'
import { AIPanel } from './ui/AIPanel'
import { ValidationPanel } from './ui/ValidationPanel'
import { useDesignerStore } from './stores/designerStore'

/** Root application component. */
export default function App() {
  const showAIPanel = useDesignerStore((s) => s.showAIPanel)
  const toggleAI = useDesignerStore((s) => s.toggleAIPanel)
  const toggleValidation = useDesignerStore((s) => s.toggleValidationPanel)
  const showValidationPanel = useDesignerStore((s) => s.showValidationPanel)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const design = useDesignerStore((s) => s.design)

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
          {isDirty && <span style={styles.dirtyBadge}>● 미저장</span>}
          <button onClick={toggleValidation} style={styles.toolBtn} title="검증/저장">
            ✅ 검증
          </button>
          <button onClick={toggleAI} style={{ ...styles.toolBtn, background: showAIPanel ? '#667eea' : '#2d3748' }} title="AI 설계 보조">
            🤖 AI
          </button>
        </div>
      </div>

      {/* Main area */}
      <div style={styles.main}>
        {/* Left: Inspector */}
        <InspectorPanel />

        {/* Center: Canvas */}
        <div style={styles.canvasWrap}>
          <DesignerCanvas />
          {showValidationPanel && (
            <div style={styles.validationOverlay}>
              <ValidationPanel />
            </div>
          )}
        </div>

        {/* Right: AI Panel (collapsible) */}
        {showAIPanel && <AIPanel />}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: { width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column', background: '#1a1a2e', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  toolbar: { height: 44, background: '#16213e', borderBottom: '1px solid #2d3748', display: 'flex', alignItems: 'center', padding: '0 12px', gap: 12, flexShrink: 0 },
  brand: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 },
  brandIcon: { fontSize: 18 },
  brandName: { color: '#e2e8f0', fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap' },
  version: { color: '#4a5568', fontSize: 10, fontWeight: 600, background: '#2d3748', padding: '1px 6px', borderRadius: 10 },
  toolbarCenter: { flex: 1, display: 'flex', justifyContent: 'center' },
  dimLabel: { color: '#718096', fontSize: 12 },
  toolbarActions: { display: 'flex', alignItems: 'center', gap: 8 },
  dirtyBadge: { color: '#ed8936', fontSize: 11 },
  toolBtn: { padding: '5px 12px', background: '#2d3748', border: 'none', borderRadius: 5, color: '#e2e8f0', fontSize: 12, cursor: 'pointer', fontWeight: 600 },
  main: { flex: 1, display: 'flex', overflow: 'hidden' },
  canvasWrap: { flex: 1, position: 'relative', overflow: 'hidden' },
  validationOverlay: { position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 10 },
}
