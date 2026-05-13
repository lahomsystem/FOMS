import { Line } from '@react-three/drei'
import type { CabinetDimensions } from '../domain/designTypes'

const MM = 0.001 // mm → meters

interface Props {
  cabinet: CabinetDimensions
}

/** Renders dimension lines around the cabinet bounding box. */
export function DimensionLines({ cabinet }: Props) {
  const w = cabinet.width * MM
  const h = cabinet.height * MM
  const d = cabinet.depth * MM
  const offset = 0.05

  // Width line (bottom front)
  const widthPoints: [number, number, number][] = [
    [0, -offset, 0],
    [w, -offset, 0],
  ]
  // Height line (left side)
  const heightPoints: [number, number, number][] = [
    [-offset, 0, 0],
    [-offset, h, 0],
  ]
  // Depth line (bottom left)
  const depthPoints: [number, number, number][] = [
    [0, -offset, 0],
    [0, -offset, d],
  ]

  return (
    <group>
      <Line points={widthPoints} color="#667eea" lineWidth={1.5} />
      <Line points={heightPoints} color="#48bb78" lineWidth={1.5} />
      <Line points={depthPoints} color="#ed8936" lineWidth={1.5} />
    </group>
  )
}
