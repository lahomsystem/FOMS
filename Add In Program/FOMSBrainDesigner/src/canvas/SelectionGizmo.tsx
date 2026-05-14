/**
 * FOMS Brain PG-B9/Enhancement — SelectionGizmo.
 * 선택된 부재 위에 표시되는 3D 하이라이트 + 이동 화살표.
 * moveTool: ← → ↑ ↓ 버튼으로 X/Y 축 이동 (10mm 단위, Shift: 100mm).
 */

import * as THREE from 'three'
import { Html } from '@react-three/drei'
import { useDesignerStore } from '../stores/designerStore'
import type { Component } from '../domain/ontologyTypes'

const MM = 0.001

interface SelectionGizmoProps {
  component: Component
}

const MOVE_STEP = 10    // mm per click
const MOVE_BIG = 100   // mm per Shift+click

function snapToAssembly(
  val: number,
  axis: 'x' | 'y' | 'z',
  assemblyDims: { width: number; height: number; depth: number },
): number {
  const maxMap = { x: assemblyDims.width, y: assemblyDims.height, z: assemblyDims.depth }
  const max = maxMap[axis]
  const SNAP_DIST = 15 // mm - snap within 15mm of boundary
  if (Math.abs(val) < SNAP_DIST) return 0
  if (Math.abs(val - max) < SNAP_DIST) return max
  return val
}

/** Animated bounding-box gizmo drawn around the selected component. */
export function SelectionGizmo({ component: c }: SelectionGizmoProps) {
  const updateComponent = useDesignerStore((s) => s.updateComponent)
  const assemblyDims = useDesignerStore((s) => s.design.assembly.dimensions)
  const showMoveControls = useDesignerStore((s) => s.activeTool === 'move')
  const w = c.dimensions.width * MM
  const h = c.dimensions.height * MM
  const d = c.dimensions.depth * MM
  const cx = c.position.x * MM + w / 2
  const cy = c.position.y * MM + h / 2
  const cz = c.position.z * MM + d / 2

  const expand = 0.0015
  const ew = w + expand
  const eh = h + expand
  const ed = d + expand

  const geo = new THREE.BoxGeometry(ew, eh, ed)

  return (
    <group position={[cx, cy, cz]}>
      {/* Glow bounding box edges */}
      <lineSegments>
        <edgesGeometry args={[geo]} />
        <lineBasicMaterial color="#00e5ff" linewidth={2} />
      </lineSegments>

      {/* Corner markers */}
      {[
        [-ew / 2, -eh / 2, -ed / 2],
        [ew / 2, -eh / 2, -ed / 2],
        [-ew / 2, eh / 2, -ed / 2],
        [ew / 2, eh / 2, -ed / 2],
        [-ew / 2, -eh / 2, ed / 2],
        [ew / 2, -eh / 2, ed / 2],
        [-ew / 2, eh / 2, ed / 2],
        [ew / 2, eh / 2, ed / 2],
      ].map(([x, y, z], i) => (
        <mesh key={i} position={[x, y, z]}>
          <sphereGeometry args={[0.004, 6, 6]} />
          <meshBasicMaterial color="#00e5ff" />
        </mesh>
      ))}

      {/* Label + move controls overlay */}
      <Html
        position={[0, eh / 2 + 0.05, 0]}
        center
        occlude={false}
        style={{ pointerEvents: 'auto', userSelect: 'none' }}
      >
        <div style={labelStyle}>
          <div style={nameStyle}>{c.name}</div>
          <div style={roleStyle}>{c.kind} / {c.role}</div>
          <div style={dimStyle}>
            {c.dimensions.width} × {c.dimensions.height} × {c.dimensions.depth} mm
          </div>

          {/* Move arrows (이동 도구일 때만) */}
          {showMoveControls && (
          <div style={{ display: 'flex', gap: 3, marginTop: 5, justifyContent: 'center', flexWrap: 'wrap' }}>
            {([
              { label: '←', dx: -1, dy: 0, dz: 0, title: 'X- (Shift: -100mm)' },
              { label: '→', dx: 1,  dy: 0, dz: 0, title: 'X+ (Shift: +100mm)' },
              { label: '↑', dx: 0,  dy: 1, dz: 0, title: 'Y+ (Shift: +100mm)' },
              { label: '↓', dx: 0,  dy: -1, dz: 0, title: 'Y- (Shift: -100mm)' },
              { label: '◀', dx: 0,  dy: 0, dz: -1, title: 'Z- depth' },
              { label: '▶', dx: 0,  dy: 0, dz: 1, title: 'Z+ depth' },
            ] as const).map(({ label, dx, dy, dz, title }) => (
              <button
                key={label}
                title={title}
                onClick={(e) => {
                  e.stopPropagation()
                  const step = e.shiftKey ? MOVE_BIG : MOVE_STEP
                  const rawX = c.position.x + dx * step
                  const rawY = c.position.y + dy * step
                  const rawZ = c.position.z + dz * step
                  // Alt key: snap to assembly boundary
                  const snap = e.altKey
                  updateComponent(c.id, {
                    position: {
                      x: snap ? snapToAssembly(rawX, 'x', assemblyDims) : rawX,
                      y: snap ? snapToAssembly(rawY, 'y', assemblyDims) : rawY,
                      z: snap ? snapToAssembly(rawZ, 'z', assemblyDims) : rawZ,
                    },
                  })
                }}
                style={arrowBtnStyle}
              >
                {label}
              </button>
            ))}
          </div>
          )}
          <div style={uuidStyle} title={c.id}>
            {c.id.slice(0, 8)}… | Shift:×10 | Alt:스냅
          </div>
        </div>
      </Html>
    </group>
  )
}

const labelStyle: React.CSSProperties = {
  background: 'rgba(0, 229, 255, 0.12)',
  border: '1px solid rgba(0, 229, 255, 0.5)',
  borderRadius: 6,
  padding: '4px 10px',
  backdropFilter: 'blur(4px)',
  whiteSpace: 'nowrap',
  userSelect: 'none',
}

const nameStyle: React.CSSProperties = {
  color: '#00e5ff',
  fontSize: 11,
  fontWeight: 700,
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  textAlign: 'center',
}

const roleStyle: React.CSSProperties = {
  color: 'rgba(180, 240, 255, 0.9)',
  fontSize: 10,
  textAlign: 'center',
  marginTop: 1,
}

const dimStyle: React.CSSProperties = {
  color: 'rgba(0, 229, 255, 0.8)',
  fontSize: 10,
  fontFamily: 'monospace',
  textAlign: 'center',
  marginTop: 1,
}

const uuidStyle: React.CSSProperties = {
  color: 'rgba(0, 229, 255, 0.5)',
  fontSize: 9,
  fontFamily: 'monospace',
  textAlign: 'center',
  marginTop: 4,
}

const arrowBtnStyle: React.CSSProperties = {
  background: 'rgba(0, 229, 255, 0.15)',
  border: '1px solid rgba(0, 229, 255, 0.4)',
  borderRadius: 4,
  color: '#00e5ff',
  fontSize: 11,
  width: 22,
  height: 22,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  padding: 0,
  fontFamily: 'monospace',
}
