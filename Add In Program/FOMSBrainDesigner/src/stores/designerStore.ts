/**
 * FOMS Brain Design Kernel V1 — Designer Store (DK-B5 migration)
 *
 * Store migrated from schema v1 DesignJson to schema v2 DesignGraph.
 * Includes formula recalculation and constraint validation on every mutation.
 */

import { create } from 'zustand'
import type {
  DesignGraph, Component, Assembly, CorrectionDelta,
} from '../domain/ontologyTypes'
import type { DesignerProject, AIRun, ValidationResult } from '../domain/designTypes'
import { createDefaultWardrobe, createWardrobeAssembly } from '../domain/assemblyFactories'
import { validateDesignGraph } from '../domain/constraintEngine'
import { recalculateGraph } from '../domain/formulaEngine'
import type { WardrobeParams } from '../domain/assemblyFactories'
import { createDefaultDesign, type FurnitureType } from '../domain/factoryRegistry'

// ──────────────────────────────────────────────────────────
// Constraint result (mapped from ConstraintResult)
// ──────────────────────────────────────────────────────────

export interface StoreConstraintResult {
  valid: boolean
  errorCount: number
  warningCount: number
  violations: Array<{
    severity: string
    code: string
    message: string
    path: string
  }>
}

function toStoreConstraintResult(result: ReturnType<typeof validateDesignGraph>): StoreConstraintResult {
  return {
    valid: result.valid,
    errorCount: result.violations.filter(v => v.severity === 'error').length,
    warningCount: result.violations.filter(v => v.severity === 'warning').length,
    violations: result.violations,
  }
}

// ──────────────────────────────────────────────────────────
// Store shape
// ──────────────────────────────────────────────────────────

interface DesignerState {
  // Project
  project: DesignerProject | null
  projectId: number | null

  // Design (schema v2 DesignGraph)
  design: DesignGraph
  isDirty: boolean

  // Constraint validation
  constraintResult: StoreConstraintResult | null

  // AI (legacy, kept for backwards compat)
  aiRunId: number | null
  aiRun: AIRun | null
  aiPrompt: string
  isAiRunning: boolean

  // Furniture type (PG-B10)
  currentFurnitureType: FurnitureType

  // UI
  selectedComponentId: string | null
  showAIPanel: boolean
  showValidationPanel: boolean
  showComponentTree: boolean

  // ── Actions ──────────────────────────────────────────────
  setProject: (project: DesignerProject) => void
  setDesign: (design: DesignGraph) => void

  /** Switch furniture type and regenerate assembly with factory defaults. */
  switchFurnitureType: (type: FurnitureType) => void

  /** Regenerate assembly with new wardrobe parameters and validate. */
  regenerateWardrobe: (params: WardrobeParams) => void

  /** Update a component property and revalidate. */
  updateComponent: (componentId: string, updates: Partial<Component>) => void

  /** Update assembly-level fields (ep_left, ep_right, top_sr, etc.) */
  updateAssembly: (updates: Partial<Assembly>) => void

  setAIRun: (run: AIRun | null) => void
  setAIPrompt: (prompt: string) => void
  setSelectedComponent: (id: string | null) => void
  toggleAIPanel: () => void
  toggleValidationPanel: () => void
  toggleComponentTree: () => void
  markSaved: () => void

  /** Run formula recalculation and constraint validation. */
  recalculateAndValidate: () => void
}

// ──────────────────────────────────────────────────────────
// Initial design
// ──────────────────────────────────────────────────────────

const INITIAL_DESIGN = createDefaultWardrobe()
const INITIAL_CONSTRAINT = toStoreConstraintResult(validateDesignGraph(INITIAL_DESIGN))

// ──────────────────────────────────────────────────────────
// Store
// ──────────────────────────────────────────────────────────

export const useDesignerStore = create<DesignerState>((set, get) => ({
  project: null,
  projectId: null,
  design: INITIAL_DESIGN,
  isDirty: false,
  constraintResult: INITIAL_CONSTRAINT,
  currentFurnitureType: 'wardrobe',
  aiRunId: null,
  aiRun: null,
  aiPrompt: '',
  isAiRunning: false,
  selectedComponentId: null,
  showAIPanel: false,
  showValidationPanel: false,
  showComponentTree: true,

  setProject: (project) => set({ project, projectId: project.id }),

  switchFurnitureType: (type: FurnitureType) => {
    const newDesign = createDefaultDesign(type)
    const { graph: recalculated } = recalculateGraph(newDesign)
    const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
    set({ design: recalculated, isDirty: true, constraintResult, currentFurnitureType: type, selectedComponentId: null })
  },

  setDesign: (design) => {
    const { graph: recalculated } = recalculateGraph(design)
    const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
    set({ design: recalculated, isDirty: true, constraintResult })
  },

  regenerateWardrobe: (params) => {
    const newDesign = createWardrobeAssembly(params)
    const { graph: recalculated } = recalculateGraph(newDesign)
    const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
    set({ design: recalculated, isDirty: true, constraintResult, selectedComponentId: null })
  },

  updateComponent: (componentId, updates) => {
    set((state) => {
      const components = state.design.components.map((comp) =>
        comp.id === componentId
          ? { ...comp, ...updates, dimensions: { ...comp.dimensions, ...(updates.dimensions ?? {}) }, position: { ...comp.position, ...(updates.position ?? {}) } }
          : comp,
      )
      const newDesign = { ...state.design, components }
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return { design: recalculated, isDirty: true, constraintResult }
    })
  },

  updateAssembly: (updates) => {
    set((state) => {
      const newAssembly = { ...state.design.assembly, ...updates }
      const newDesign = { ...state.design, assembly: newAssembly }
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return { design: recalculated, isDirty: true, constraintResult }
    })
  },

  setAIRun: (aiRun) => set({
    aiRun,
    aiRunId: aiRun?.id ?? null,
    isAiRunning: aiRun?.status === 'running' || aiRun?.status === 'queued',
  }),

  setAIPrompt: (aiPrompt) => set({ aiPrompt }),

  setSelectedComponent: (selectedComponentId) => set({ selectedComponentId }),

  toggleAIPanel: () => set((state) => ({ showAIPanel: !state.showAIPanel })),
  toggleValidationPanel: () => set((state) => ({ showValidationPanel: !state.showValidationPanel })),
  toggleComponentTree: () => set((state) => ({ showComponentTree: !state.showComponentTree })),

  markSaved: () => set({ isDirty: false }),

  recalculateAndValidate: () => {
    set((state) => {
      const { graph: recalculated } = recalculateGraph(state.design)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return { design: recalculated, constraintResult }
    })
  },
}))
