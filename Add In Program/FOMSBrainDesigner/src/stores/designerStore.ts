import { create } from 'zustand'
import type { DesignJson, CabinetDimensions, DesignerProject, AIRun, ValidationResult } from '../domain/designTypes'
import { DEFAULT_DESIGN } from '../domain/defaultCabinet'

interface DesignerState {
  // Project
  project: DesignerProject | null
  projectId: number | null

  // Design
  design: DesignJson
  isDirty: boolean

  // Validation
  validation: ValidationResult | null

  // AI
  aiRunId: number | null
  aiRun: AIRun | null
  aiPrompt: string
  isAiRunning: boolean

  // UI
  selectedComponentId: string | null
  showAIPanel: boolean
  showValidationPanel: boolean

  // Actions
  setProject: (project: DesignerProject) => void
  setDesign: (design: DesignJson) => void
  updateCabinetDimensions: (dims: Partial<CabinetDimensions>) => void
  setValidation: (v: ValidationResult | null) => void
  setAIRun: (run: AIRun | null) => void
  setAIPrompt: (prompt: string) => void
  setSelectedComponent: (id: string | null) => void
  toggleAIPanel: () => void
  toggleValidationPanel: () => void
  markSaved: () => void
}

export const useDesignerStore = create<DesignerState>((set) => ({
  project: null,
  projectId: null,
  design: DEFAULT_DESIGN,
  isDirty: false,
  validation: null,
  aiRunId: null,
  aiRun: null,
  aiPrompt: '',
  isAiRunning: false,
  selectedComponentId: null,
  showAIPanel: false,
  showValidationPanel: false,

  setProject: (project) => set({ project, projectId: project.id }),

  setDesign: (design) => set({ design, isDirty: true }),

  updateCabinetDimensions: (dims) =>
    set((state) => ({
      design: {
        ...state.design,
        cabinet: { ...state.design.cabinet, ...dims },
      },
      isDirty: true,
    })),

  setValidation: (validation) => set({ validation }),

  setAIRun: (aiRun) => set({ aiRun, aiRunId: aiRun?.id ?? null, isAiRunning: aiRun?.status === 'running' || aiRun?.status === 'queued' }),

  setAIPrompt: (aiPrompt) => set({ aiPrompt }),

  setSelectedComponent: (selectedComponentId) => set({ selectedComponentId }),

  toggleAIPanel: () => set((state) => ({ showAIPanel: !state.showAIPanel })),

  toggleValidationPanel: () => set((state) => ({ showValidationPanel: !state.showValidationPanel })),

  markSaved: () => set({ isDirty: false }),
}))
