/**
 * SelectionGizmo — 선택된 부재 위에 표시되는 3D 하이라이트 기즈모.
 * DK-B5: schema v2 Component 기반으로 업데이트.
 * UUID/kind/role/dimensions를 표시.
 */

import * as THREE from 'three'
import { Html } from '@react-three/drei'
import type { Component } from '../domain/ontologyTypes'

const MM = 0.001

interface SelectionGizmoProps {
  component: Component
}

/** Animated bounding-box gizmo drawn around the selected component. */
export function SelectionGizmo({ component: c }: SelectionGizmoProps) {
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

      {/* Label overlay: UUID/kind/role/dimensions */}
      <Html
        position={[0, eh / 2 + 0.04, 0]}
        center
        occlude={false}
        style={{ pointerEvents: 'none' }}
      >
        <div style={labelStyle}>
          <div style={nameStyle}>{c.name}</div>
          <div style={roleStyle}>{c.kind} / {c.role}</div>
          <div style={dimStyle}>
            {c.dimensions.width} × {c.dimensions.height} × {c.dimensions.depth} mm
          </div>
          <div style={uuidStyle} title={c.id}>
            UUID: {c.id.slice(0, 8)}…
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
  marginTop: 2,
}
