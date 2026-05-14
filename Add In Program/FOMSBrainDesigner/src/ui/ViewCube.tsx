/**
 * FOMS Brain Enhancement — ViewCube.
 *
 * Corner orientation cube showing current view direction.
 * Clicking a face snaps the camera to that view preset.
 * Positioned as an HTML overlay in the top-right of the canvas.
 */

import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'

type ViewMode = '3d' | 'front' | 'side' | 'top' | 'isometric'

interface ViewCubeProps {
  currentView: ViewMode
  onViewChange: (view: ViewMode) => void
}

const FACES = [
  { view: 'front' as ViewMode,  label: '정면', top: '38%', left: '38%'   },
  { view: 'top' as ViewMode,    label: '상면', top: '5%',  left: '38%'   },
  { view: 'side' as ViewMode,   label: '측면', top: '38%', left: '68%'   },
  { view: '3d' as ViewMode,     label: '3D',   top: '5%',  left: '68%'   },
]

export function ViewCube({ currentView, onViewChange }: ViewCubeProps) {
  return (
    <div
      style={{
        position: 'absolute' as const,
        top: 10,
        right: 10,
        width: 72,
        height: 72,
        zIndex: 10,
        userSelect: 'none',
      }}
    >
      {/* Cube body */}
      <div
        style={{
          width: '100%',
          height: '100%',
          background: 'rgba(255,255,255,0.9)',
          border: `1px solid ${COLORS.toolbarBorder}`,
          borderRadius: 6,
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          position: 'relative' as const,
          overflow: 'hidden',
        }}
      >
        {/* Isometric grid lines decoration */}
        <svg
          style={{ position: 'absolute' as const, width: '100%', height: '100%', opacity: 0.15 }}
          viewBox="0 0 72 72"
        >
          {/* Top face */}
          <polygon points="36,4 68,20 36,36 4,20" fill="#5a67d8" stroke="#4a57c8" strokeWidth="0.5" />
          {/* Left face */}
          <polygon points="4,20 36,36 36,68 4,52" fill="#7b8bde" stroke="#4a57c8" strokeWidth="0.5" />
          {/* Right face */}
          <polygon points="36,36 68,20 68,52 36,68" fill="#9fa8e4" stroke="#4a57c8" strokeWidth="0.5" />
        </svg>

        {/* Clickable face buttons */}
        {FACES.map(({ view, label, top, left }) => (
          <button
            key={view}
            onClick={() => onViewChange(view)}
            title={label}
            style={{
              position: 'absolute' as const,
              top,
              left,
              transform: 'translate(-50%, -50%)',
              background: currentView === view ? COLORS.accent : 'rgba(255,255,255,0.7)',
              border: `1px solid ${currentView === view ? COLORS.accent : COLORS.toolbarBorder}`,
              borderRadius: 3,
              padding: '1px 5px',
              fontSize: 9,
              fontWeight: TYPOGRAPHY.weightBold,
              color: currentView === view ? '#fff' : COLORS.textSecondary,
              cursor: 'pointer',
              fontFamily: TYPOGRAPHY.fontFamily,
              lineHeight: 1.4,
              whiteSpace: 'nowrap' as const,
              zIndex: 2,
            }}
          >
            {label}
          </button>
        ))}

        {/* Axis labels */}
        <div style={{ position: 'absolute' as const, bottom: 2, right: 3, fontSize: 8, color: COLORS.textMuted, fontFamily: 'monospace', lineHeight: 1.3 }}>
          <span style={{ color: '#e53e3e' }}>X</span>
          <span style={{ color: '#38a169' }}>Y</span>
          <span style={{ color: '#3182ce' }}>Z</span>
        </div>
      </div>
    </div>
  )
}
