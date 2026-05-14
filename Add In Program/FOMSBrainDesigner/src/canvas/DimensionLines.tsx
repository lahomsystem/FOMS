/**
 * FOMS Brain Enhancement — DimensionLines with mm text labels.
 *
 * Renders dimension lines + Html labels showing W/H/D in mm.
 */

import { Line } from '@react-three/drei'
import { Html } from '@react-three/drei'
import { useDesignerStore } from '../stores/designerStore'

const MM = 0.001

const labelStyle: React.CSSProperties = {
  background: 'rgba(255,255,255,0.88)',
  border: '1px solid',
  borderRadius: 3,
  padding: '1px 5px',
  fontSize: 10,
  fontFamily: 'monospace',
  fontWeight: 700,
  whiteSpace: 'nowrap',
  pointerEvents: 'none',
  userSelect: 'none',
}

interface DimensionLinesProps {
  /** When false, skips rendering (default true for backward compatibility). */
  visible?: boolean
}

/** Renders dimension lines + mm labels around the assembly bounding box. */
export function DimensionLines({ visible = true }: DimensionLinesProps) {
  const design = useDesignerStore((s) => s.design)
  const asm = design.assembly

  if (!visible) return null

  const w = asm.dimensions.width * MM
  const h = asm.dimensions.height * MM
  const d = asm.dimensions.depth * MM
  const offset = 0.06

  return (
    <group>
      {/* Width (X): red */}
      <Line
        points={[[0, -offset, 0], [w, -offset, 0]]}
        color="#e53e3e"
        lineWidth={1.5}
      />
      <Html position={[w / 2, -offset - 0.02, 0]} center occlude={false}>
        <div style={{ ...labelStyle, color: '#e53e3e', borderColor: '#e53e3e' }}>
          W {asm.dimensions.width}
        </div>
      </Html>

      {/* Height (Y): green */}
      <Line
        points={[[-offset, 0, 0], [-offset, h, 0]]}
        color="#38a169"
        lineWidth={1.5}
      />
      <Html position={[-offset - 0.02, h / 2, 0]} center occlude={false}>
        <div style={{ ...labelStyle, color: '#38a169', borderColor: '#38a169' }}>
          H {asm.dimensions.height}
        </div>
      </Html>

      {/* Depth (Z): blue */}
      <Line
        points={[[0, -offset, 0], [0, -offset, d]]}
        color="#3182ce"
        lineWidth={1.5}
      />
      <Html position={[0, -offset - 0.02, d / 2]} center occlude={false}>
        <div style={{ ...labelStyle, color: '#3182ce', borderColor: '#3182ce' }}>
          D {asm.dimensions.depth}
        </div>
      </Html>

      {/* Tick marks at endpoints */}
      {([[0, -offset, 0], [w, -offset, 0]] as [number,number,number][]).map((p, i) => (
        <Line key={`wt${i}`} points={[[p[0], p[1]-0.01, p[2]], [p[0], p[1]+0.01, p[2]]]} color="#e53e3e" lineWidth={1} />
      ))}
      {([[0, -offset, 0], [0, -offset, d]] as [number,number,number][]).map((p, i) => (
        <Line key={`dt${i}`} points={[[p[0]-0.01, p[1], p[2]], [p[0]+0.01, p[1], p[2]]]} color="#3182ce" lineWidth={1} />
      ))}
    </group>
  )
}
