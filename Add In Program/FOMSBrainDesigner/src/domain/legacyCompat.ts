/**
 * DK-B9: legacy v1 → v2 normalize (client-side).
 * v1 DesignJson을 v2 DesignGraph로 변환.
 */

import { createWardrobeAssembly } from './assemblyFactories'
import type { DesignGraph } from './ontologyTypes'

export function normalize_to_v2_client(design: Record<string, unknown>): DesignGraph {
  if (design.schema_version === 2) {
    return design as unknown as DesignGraph
  }

  // v1 cabinet dimensions
  const cabinet = (design.cabinet as Record<string, number>) ?? {}
  const width = cabinet.width ?? 2400
  const height = cabinet.height ?? 2200
  const depth = cabinet.depth ?? 600

  const v2 = createWardrobeAssembly({
    width,
    height,
    depth,
    moduleCount: 2,
    doorType: 'sliding',
  })

  v2.metadata = {
    ...v2.metadata,
    source: 'legacy_v1_migration',
  }

  return v2
}
