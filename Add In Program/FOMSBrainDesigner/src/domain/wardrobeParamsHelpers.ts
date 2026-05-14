/**
 * Build WardrobeParams from current DesignGraph assembly for regenerateWardrobe calls.
 * Keeps ModulePanel / keyboard split / LEGO split in sync.
 */

import type { DesignGraph } from './ontologyTypes'
import type { DoorType } from './ontologyTypes'
import type { WardrobeParams } from './assemblyFactories'

/** Parameters for createWardrobeAssembly / regenerateWardrobe from live assembly. */
export function wardrobeParamsFromDesign(design: DesignGraph): WardrobeParams {
  const asm = design.assembly
  return {
    width: asm.dimensions.width,
    height: asm.dimensions.height,
    depth: asm.dimensions.depth,
    moduleCount: asm.module_count,
    doorType: asm.door_type as DoorType,
    epLeft: asm.ep_left,
    epRight: asm.ep_right,
    epTop: asm.ep_top,
    baseHeight: asm.base_height,
    topSr: asm.top_sr,
  }
}

/** Clamp module count to valid LEGO/ModulePanel range. */
export function clampModuleCount(n: number): number {
  return Math.max(1, Math.min(5, n))
}

export function wardrobeParamsWithModuleCount(design: DesignGraph, moduleCount: number): WardrobeParams {
  return {
    ...wardrobeParamsFromDesign(design),
    moduleCount: clampModuleCount(moduleCount),
  }
}
