/**
 * FOMS Brain Designer API client.
 * Communicates with /api/designer/* endpoints on the parent FOMS Flask app.
 * Uses window.parent.location.origin to detect the FOMS host when running inside iframe.
 */

const BASE = (() => {
  try {
    return window.parent.location.origin
  } catch {
    return ''
  }
})()

interface ApiResponse<T = unknown> {
  success: boolean
  data: T | null
  error: { code: string; message: string; details?: unknown } | null
}

async function request<T>(method: string, path: string, body?: unknown): Promise<ApiResponse<T>> {
  const resp = await fetch(`${BASE}/api/designer${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const json: ApiResponse<T> = await resp.json()
  return json
}

export const designerApi = {
  // Projects
  listProjects: () => request<unknown[]>('GET', '/projects'),
  createProject: (name: string) => request<unknown>('POST', '/projects', { name }),
  getProject: (id: number) => request<unknown>('GET', `/projects/${id}`),
  createVersion: (projectId: number, designJson: unknown) =>
    request<unknown>('POST', `/projects/${projectId}/versions`, { design_json: designJson }),

  // Validation
  validate: (designJson: unknown) => request<unknown>('POST', '/validate', { design_json: designJson }),

  // AI runs
  createAIRun: (input: unknown) => request<unknown>('POST', '/ai-runs', input),
  getAIRun: (runId: number) => request<unknown>('GET', `/ai-runs/${runId}`),
  resumeAIRun: (runId: number, decision: 'approve' | 'reject') =>
    request<unknown>('POST', `/ai-runs/${runId}/resume`, { decision }),

  // Ontology
  getCurrentOntology: () => request<unknown>('GET', '/ontology/current'),
}
