import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
import { Suspense } from 'react'
import { CabinetScene } from './CabinetScene'
import { useDesignerStore } from '../stores/designerStore'

function LoadingFallback() {
  return (
    <mesh>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#667eea" wireframe />
    </mesh>
  )
}

/** Main 3D canvas for the designer. */
export function DesignerCanvas() {
  const design = useDesignerStore((s) => s.design)
  // DK-B5: schema v2 uses assembly.dimensions
  const asm = design.assembly
  const w = asm.dimensions.width * 0.001
  const h = asm.dimensions.height * 0.001

  const camDist = Math.max(w, h) * 2.2

  return (
    <div style={{ width: '100%', height: '100%', background: '#1a1a2e' }}>
      <Canvas
        camera={{
          position: [camDist * 0.8, camDist * 0.6, camDist * 1.2],
          fov: 45,
          near: 0.01,
          far: 100,
        }}
        shadows
        gl={{ antialias: true }}
        style={{ width: '100%', height: '100%' }}
      >
        <color attach="background" args={['#1a1a2e']} />
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

        <OrbitControls
          enablePan
          enableZoom
          enableRotate
          target={[w / 2, h / 2, asm.dimensions.depth * 0.001 / 2]}
          minDistance={0.1}
          maxDistance={20}
        />
      </Canvas>
    </div>
  )
}
