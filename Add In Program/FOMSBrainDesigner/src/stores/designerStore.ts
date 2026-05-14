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
import { commandHistory } from '../domain/commandHistory'
import type { ToolMode } from '../domain/toolMode'

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
  selectedComponentIds: Set<string>       // multi-select
  clipboard: Component[]                  // copy/paste
  showAIPanel: boolean
  showValidationPanel: boolean
  showComponentTree: boolean

  /** Left palette active tool (SketchUp-like). */
  activeTool: ToolMode
  setActiveTool: (tool: ToolMode) => void

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

  // ── PG-B9: LEGO Workbench ────────────────────────────────
  /** Undo last edit. */
  undo: () => void
  /** Redo last undone edit. */
  redo: () => void
  /** Whether undo is available. */
  canUndo: () => boolean
  /** Whether redo is available. */
  canRedo: () => boolean

  /** Add a new component (block) to the design. */
  addComponent: (component: Component) => void
  /** Remove a component by ID. */
  removeComponent: (componentId: string) => void
  /** Remove all selected components (multi-delete). */
  removeSelectedComponents: () => void

  // ── Multi-select (Ctrl+click) ────────────────────────────
  toggleComponentSelection: (id: string) => void
  clearMultiSelection: () => void

  // ── Copy / Paste (Ctrl+C / Ctrl+V) ──────────────────────
  copySelected: () => void
  pasteClipboard: () => void

  /**
   * Load a candidate from AI extraction into editable 3D view.
   * Called when user clicks "3D로 로드" after Gemini extraction.
   */
  loadCandidateGraph: (candidatePayload: {
    furniture_type: string
    factory_params: Record<string, unknown>
  }) => void
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
  selectedComponentIds: new Set<string>(),
  clipboard: [],
  showAIPanel: false,
  showValidationPanel: false,
  showComponentTree: true,
  activeTool: 'select',
  setActiveTool: (tool) => set({ activeTool: tool }),

  setProject: (project) => set({ project, projectId: project.id }),

  switchFurnitureType: (type: FurnitureType) => {
    const newDesign = createDefaultDesign(type)
    const { graph: recalculated } = recalculateGraph(newDesign)
    const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
    set({ design: recalculated, isDirty: true, constraintResult, currentFurnitureType: type, selectedComponentId: null })
  },

  setDesign: (design) => {
    commandHistory.push(get().design)
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
    commandHistory.push(get().design)
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

  // ── PG-B9: Undo / Redo ──────────────────────────────────
  undo: () => {
    const prev = commandHistory.undo(get().design)
    if (!prev) return
    const { graph: recalculated } = recalculateGraph(prev)
    const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
    set({ design: recalculated, isDirty: true, constraintResult })
  },

  redo: () => {
    const next = commandHistory.redo(get().design)
    if (!next) return
    const { graph: recalculated } = recalculateGraph(next)
    const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
    set({ design: recalculated, isDirty: true, constraintResult })
  },

  canUndo: () => commandHistory.canUndo(),
  canRedo: () => commandHistory.canRedo(),

  // ── PG-B9: Add / Remove Component ───────────────────────
  addComponent: (component: Component) => {
    set((state) => {
      commandHistory.push(state.design)
      const newDesign = {
        ...state.design,
        components: [...state.design.components, component],
      }
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return { design: recalculated, isDirty: true, constraintResult }
    })
  },

  removeComponent: (componentId: string) => {
    set((state) => {
      commandHistory.push(state.design)
      const newDesign = {
        ...state.design,
        components: state.design.components.filter(c => c.id !== componentId),
      }
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return {
        design: recalculated,
        isDirty: true,
        constraintResult,
        selectedComponentId: null,
      }
    })
  },

  // ── PG-B9: Load AI Candidate into 3D ────────────────────
  loadCandidateGraph: (candidatePayload) => {
    try {
      const { furniture_type, factory_params } = candidatePayload
      const ft = (furniture_type ?? 'wardrobe') as FurnitureType
      const p = (factory_params ?? {}) as Record<string, number>

      let newDesign: DesignGraph
      // Build wardrobe with extracted params if available, else use factory defaults
      if (ft === 'wardrobe' && (p.width || p.height || p.depth)) {
        const w = p.width || 2400
        const h = p.height || 2200
        const d = p.depth || 620
        const mc = p.module_count || Math.max(1, Math.round(w / 800))
        newDesign = createWardrobeAssembly({
          width: w, height: h, depth: d,
          moduleCount: mc, doorType: 'sliding',
        })
      } else {
        newDesign = createDefaultDesign(ft)
      }

      commandHistory.push(get().design)
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      set({
        design: recalculated,
        isDirty: true,
        constraintResult,
        currentFurnitureType: ft,
        selectedComponentId: null,
      })
    } catch (err) {
      console.error('[loadCandidateGraph] failed:', err)
    }
  },

  removeSelectedComponents: () => {
    const { selectedComponentIds, selectedComponentId } = get()
    const toRemove = new Set(selectedComponentIds)
    if (selectedComponentId) toRemove.add(selectedComponentId)
    if (toRemove.size === 0) return
    commandHistory.push(get().design)
    set((state) => {
      const newDesign = {
        ...state.design,
        components: state.design.components.filter((c) => !toRemove.has(c.id)),
      }
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return {
        design: recalculated, isDirty: true, constraintResult,
        selectedComponentId: null,
        selectedComponentIds: new Set<string>(),
      }
    })
  },

  toggleComponentSelection: (id: string) => {
    set((state) => {
      const next = new Set(state.selectedComponentIds)
      if (next.has(id)) { next.delete(id) } else { next.add(id) }
      return { selectedComponentIds: next, selectedComponentId: id }
    })
  },

  clearMultiSelection: () => set({ selectedComponentIds: new Set<string>() }),

  copySelected: () => {
    const { design, selectedComponentId, selectedComponentIds } = get()
    const ids = new Set(selectedComponentIds)
    if (selectedComponentId) ids.add(selectedComponentId)
    const comps = design.components.filter((c) => ids.has(c.id))
    if (comps.length > 0) set({ clipboard: comps })
  },

  pasteClipboard: () => {
    const { clipboard } = get()
    if (!clipboard.length) return
    commandHistory.push(get().design)
    const OFFSET = 50 // mm offset for pasted components
    const pasted: Component[] = clipboard.map((c) => ({
      ...c,
      id: crypto.randomUUID(),
      position: {
        x: c.position.x + OFFSET,
        y: c.position.y,
        z: c.position.z,
      },
      name: c.name + ' (복사)',
    }))
    set((state) => {
      const newDesign = {
        ...state.design,
        components: [...state.design.components, ...pasted],
      }
      const { graph: recalculated } = recalculateGraph(newDesign)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return { design: recalculated, isDirty: true, constraintResult }
    })
  },

  recalculateAndValidate: () => {
    set((state) => {
      const { graph: recalculated } = recalculateGraph(state.design)
      const constraintResult = toStoreConstraintResult(validateDesignGraph(recalculated))
      return { design: recalculated, constraintResult }
    })
  },
}))
