/**
 * SelectionGizmo – 선택된 부재 위에 표시되는 3D 하이라이트 기즈모.
 *
 * 역할:
 *  - 선택된 component의 바운딩 박스를 발광 엣지 라인으로 강조
 *  - 부재 위에 이름 라벨 표시 (Html overlay)
 *  - 치수 정보(W×H×D) 툴팁 제공
 */

import * as THREE from 'three'
import { Html } from '@react-three/drei'
import type { DesignComponent } from '../domain/designTypes'

const MM = 0.001

interface SelectionGizmoProps {
  component: DesignComponent
}

/** Animated bounding-box gizmo drawn around the selected component. */
export function SelectionGizmo({ component: c }: SelectionGizmoProps) {
  const w = c.width * MM
  const h = c.height * MM
  const d = c.depth * MM
  const cx = c.position.x * MM + w / 2
  const cy = c.position.y * MM + h / 2
  const cz = c.position.z * MM + d / 2

  // Slight expand so gizmo doesn't z-fight with mesh surface
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

      {/* Corner markers – 8 tiny spheres at each corner */}
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

      {/* Label overlay – component name + dimensions */}
      <Html
        position={[0, eh / 2 + 0.04, 0]}
        center
        occlude={false}
        style={{ pointerEvents: 'none' }}
      >
        <div style={labelStyle}>
          <div style={nameStyle}>{c.name}</div>
          <div style={dimStyle}>
            {c.width} × {c.height} × {c.depth} mm
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
  padding: '3px 8px',
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

const dimStyle: React.CSSProperties = {
  color: 'rgba(0, 229, 255, 0.75)',
  fontSize: 10,
  fontFamily: 'monospace',
  textAlign: 'center',
  marginTop: 1,
}
