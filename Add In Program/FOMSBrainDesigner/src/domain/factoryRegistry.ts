/**
 * FOMS Brain PG-B10 — Frontend Factory Registry
 * Maps furniture_type to factory + default params + label.
 */

import type { DesignGraph } from './ontologyTypes'
import { createWardrobeAssembly } from './assemblyFactories'
import { createDefaultShoeRack } from './factories/shoeRackFactory'
import { createDefaultKitchenBase, createDefaultKitchenWall } from './factories/kitchenFactory'

export type FurnitureType =
  | 'wardrobe'
  | 'shoe_rack'
  | 'kitchen_base'
  | 'kitchen_wall'
  | 'custom_storage'

export interface FurnitureTypeMeta {
  type: FurnitureType
  label: string
  labelEn: string
  icon: string
  createDefault: () => DesignGraph
}

export const FURNITURE_TYPE_REGISTRY: FurnitureTypeMeta[] = [
  {
    type: 'wardrobe',
    label: '붙박이장',
    labelEn: 'Wardrobe',
    icon: '🚪',
    createDefault: () => createWardrobeAssembly({
      width: 2400, height: 2200, depth: 600,
      moduleCount: 3, doorType: 'sliding',
    }),
  },
  {
    type: 'shoe_rack',
    label: '신발장',
    labelEn: 'Shoe Rack',
    icon: '👟',
    createDefault: createDefaultShoeRack,
  },
  {
    type: 'kitchen_base',
    label: '주방 하부장',
    labelEn: 'Kitchen Base',
    icon: '🍳',
    createDefault: createDefaultKitchenBase,
  },
  {
    type: 'kitchen_wall',
    label: '주방 상부장',
    labelEn: 'Kitchen Wall',
    icon: '🔼',
    createDefault: createDefaultKitchenWall,
  },
  {
    type: 'custom_storage',
    label: '수납장',
    labelEn: 'Custom Storage',
    icon: '📦',
    createDefault: () => createWardrobeAssembly({
      width: 2400, height: 2200, depth: 600,
      moduleCount: 3, doorType: 'sliding',
    }),
  },
]

export function getFurnitureMeta(type: FurnitureType): FurnitureTypeMeta | undefined {
  return FURNITURE_TYPE_REGISTRY.find(r => r.type === type)
}

export function createDefaultDesign(type: FurnitureType): DesignGraph {
  const meta = getFurnitureMeta(type)
  if (!meta) throw new Error(`Unknown furniture type: ${type}`)
  return meta.createDefault()
}
