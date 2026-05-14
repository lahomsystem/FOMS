/**
 * FOMS Brain Enhancement — DesignerCanvas with ViewCube + view presets.
 */

import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
import { Suspense, useEffect } from 'react'
import { CabinetScene } from './CabinetScene'
import { useDesignerStore } from '../stores/designerStore'
import { ViewCube } from '../ui/ViewCube'

type ViewMode = '3d' | 'front' | 'side' | 'top'

function LoadingFallback() {
  return (
    <mesh>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#667eea" wireframe />
    </mesh>
  )
}

function CameraController({
  view,
  target,
  camDist,
}: {
  view: ViewMode
  target: [number, number, number]
  camDist: number
}) {
  const { camera } = useThree()
  useEffect(() => {
    const [tx, ty, tz] = target
    switch (view) {
      case 'front': camera.position.set(tx, ty, tz + camDist * 1.8); break
      case 'side':  camera.position.set(tx + camDist * 1.8, ty, tz); break
      case 'top':   camera.position.set(tx, ty + camDist * 2.0, tz); break
      default:      camera.position.set(tx + camDist * 0.8, ty + camDist * 0.6, tz + camDist * 1.2)
    }
    camera.lookAt(tx, ty, tz)
  }, [view, camDist, target[0], target[1], target[2]])  // eslint-disable-line
  return null
}

/** Main 3D canvas for the designer. */
export function DesignerCanvas({
  viewMode = '3d',
  onViewModeChange,
}: {
  viewMode?: ViewMode
  onViewModeChange?: (v: ViewMode) => void
}) {
  const design = useDesignerStore((s) => s.design)
  const asm = design.assembly
  const w = asm.dimensions.width * 0.001
  const h = asm.dimensions.height * 0.001
  const d = asm.dimensions.depth * 0.001
  const camDist = Math.max(w, h) * 2.2
  const target: [number, number, number] = [w / 2, h / 2, d / 2]

  return (
    <div style={{ width: '100%', height: '100%', background: '#f0f0f0', position: 'relative' as const }}>
      <Canvas
        camera={{
          position: [w / 2 + camDist * 0.8, h / 2 + camDist * 0.6, d / 2 + camDist * 1.2],
          fov: 45,
          near: 0.01,
          far: 100,
        }}
        shadows
        gl={{ antialias: true }}
        style={{ width: '100%', height: '100%' }}
      >
        <color attach="background" args={['#f0f0f0']} />
        <ambientLight intensity={0.5} />
        <directionalLight
          position={[5, 10, 5]}
          intensity={1.2}
          castShadow
          shadow-mapSize={[2048, 2048]}
        />
        <pointLight position={[-3, 8, -3]} intensity={0.4} color="#667eea" />

        <Suspense fallback={<LoadingFallback />}>
          <CabinetScene />
          <Environment preset="apartment" />
        </Suspense>

        <CameraController view={viewMode} target={target} camDist={camDist} />

        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          target={target}
          minDistance={0.1}
          maxDistance={20}
        />
      </Canvas>

      {/* ViewCube HTML overlay */}
      <ViewCube
        currentView={viewMode}
        onViewChange={(v) => onViewModeChange?.(v as ViewMode)}
      />
    </div>
  )
}
