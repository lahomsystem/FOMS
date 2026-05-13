/**
 * DimensionLines — assembly/module/component 치수 라인 표시.
 * DK-B5: schema v2 기반으로 assembly 치수 사용.
 */

import { Line } from '@react-three/drei'
import { useDesignerStore } from '../stores/designerStore'

const MM = 0.001

/** Renders dimension lines around the assembly bounding box. */
export function DimensionLines() {
  const design = useDesignerStore((s) => s.design)
  const asm = design.assembly

  const w = asm.dimensions.width * MM
  const h = asm.dimensions.height * MM
  const d = asm.dimensions.depth * MM
  const offset = 0.05

  const widthPoints: [number, number, number][] = [
    [0, -offset, 0],
    [w, -offset, 0],
  ]
  const heightPoints: [number, number, number][] = [
    [-offset, 0, 0],
    [-offset, h, 0],
  ]
  const depthPoints: [number, number, number][] = [
    [0, -offset, 0],
    [0, -offset, d],
  ]

  return (
    <group>
      {/* Width: blue */}
      <Line points={widthPoints} color="#667eea" lineWidth={1.5} />
      {/* Height: green */}
      <Line points={heightPoints} color="#48bb78" lineWidth={1.5} />
      {/* Depth: orange */}
      <Line points={depthPoints} color="#ed8936" lineWidth={1.5} />
    </group>
  )
}
