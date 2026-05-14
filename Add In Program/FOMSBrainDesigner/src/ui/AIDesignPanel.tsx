/**
 * FOMS Brain PG-Enhancement — AI 자동 설계 제안 패널.
 *
 * 사용자가 자연어로 설계를 요청하면:
 *   1. 텍스트를 Flask LUI API로 전송
 *   2. Gemini + RAG가 factory params 추출
 *   3. candidate graph 자동 생성 → 3D 워크벤치로 로드
 *
 * 예: "W2400 H2200 D620 붙박이장 3칸 슬라이딩 도어"
 *     "이 공간에 맞는 주방 하부장 설계해줘"
 */

import { useState } from 'react'
import { useDesignerStore } from '../stores/designerStore'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import { designerApi } from '../api/client'

const EXAMPLE_PROMPTS = [
  'W2400 H2200 D620 붙박이장 3칸',
  'W900 H1200 신발장 4단',
  'W2400 주방 하부장 3칸 여닫이',
  '이 공간에 맞는 붙박이장 설계해줘',
]

export function AIDesignPanel() {
  const loadCandidateGraph = useDesignerStore((s) => s.loadCandidateGraph)
  const currentFurnitureType = useDesignerStore((s) => s.currentFurnitureType)

  const [prompt, setPrompt] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [lastResult, setLastResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleGenerate() {
    if (!prompt.trim()) return
    setIsRunning(true)
    setError(null)
    setLastResult(null)

    try {
      // Call LUI parser API
      const resp = await fetch(`${(window as Window & typeof globalThis & { parent: Window }).parent?.location?.origin || ''}/api/designer/lui/parse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ text: prompt, context_furniture_type: currentFurnitureType }),
      })

      if (!resp.ok) throw new Error(`API ${resp.status}`)

      const json = await resp.json()
      if (!json.success) throw new Error(json.error || '파싱 실패')

      const candidate = json.data?.candidate || json.data
      if (candidate?.furniture_type) {
        loadCandidateGraph({
          furniture_type: candidate.furniture_type,
          factory_params: candidate.factory_params || {},
        })
        setLastResult(
          `✅ 생성 완료: ${candidate.furniture_type} `
          + `W${candidate.factory_params?.width || '?'} `
          + `H${candidate.factory_params?.height || '?'} `
          + `D${candidate.factory_params?.depth || '?'}mm`
        )
      } else {
        // Fallback: parse dimensions from text client-side
        const fallback = parsePromptFallback(prompt)
        loadCandidateGraph(fallback)
        setLastResult(`✅ 기본 설계 생성 (API 미연결 시 fallback): ${fallback.furniture_type}`)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      // Offline fallback
      const fallback = parsePromptFallback(prompt)
      loadCandidateGraph(fallback)
      setLastResult(`⚠️ API 오류(${msg.slice(0, 30)}) → 텍스트 파싱 fallback 적용`)
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div style={{ padding: 10, fontFamily: TYPOGRAPHY.fontFamily }}>
      <div style={{ fontSize: TYPOGRAPHY.sizeXS, fontWeight: TYPOGRAPHY.weightBold, color: COLORS.textMuted, textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 6 }}>
        AI 설계 요청
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="예: W2400 H2200 붙박이장 3칸&#10;자연어로 설계를 요청하세요"
        rows={3}
        style={{
          width: '100%',
          border: `1px solid ${COLORS.panelBorder}`,
          borderRadius: 5,
          padding: '6px 8px',
          fontSize: TYPOGRAPHY.sizeSM,
          fontFamily: TYPOGRAPHY.fontFamily,
          resize: 'vertical' as const,
          outline: 'none',
          background: COLORS.surfaceWhite,
          color: COLORS.textPrimary,
          boxSizing: 'border-box' as const,
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = COLORS.accent }}
        onBlur={(e) => { e.currentTarget.style.borderColor = COLORS.panelBorder }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleGenerate()
        }}
      />

      <button
        onClick={handleGenerate}
        disabled={isRunning || !prompt.trim()}
        style={{
          width: '100%',
          marginTop: 6,
          padding: '6px 0',
          background: isRunning || !prompt.trim() ? '#e2e8f0' : COLORS.accent,
          border: 'none',
          borderRadius: 5,
          color: isRunning || !prompt.trim() ? COLORS.textMuted : '#fff',
          fontSize: TYPOGRAPHY.sizeSM,
          fontWeight: TYPOGRAPHY.weightSemibold,
          cursor: isRunning || !prompt.trim() ? 'default' : 'pointer',
          fontFamily: TYPOGRAPHY.fontFamily,
        }}
      >
        {isRunning ? '⏳ 설계 중...' : '🤖 설계 생성 (Ctrl+Enter)'}
      </button>

      {lastResult && (
        <div style={{ marginTop: 6, padding: '4px 8px', background: '#f0fff4', border: '1px solid #9ae6b4', borderRadius: 4, fontSize: TYPOGRAPHY.sizeXS, color: '#276749' }}>
          {lastResult}
        </div>
      )}

      {/* Example prompts */}
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: TYPOGRAPHY.sizeXS, color: COLORS.textMuted, marginBottom: 3 }}>예시 요청:</div>
        {EXAMPLE_PROMPTS.map((ex) => (
          <button
            key={ex}
            onClick={() => setPrompt(ex)}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left' as const,
              background: 'transparent',
              border: 'none',
              padding: '2px 0',
              fontSize: TYPOGRAPHY.sizeXS,
              color: COLORS.accent,
              cursor: 'pointer',
              fontFamily: TYPOGRAPHY.fontFamily,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap' as const,
            }}
          >
            → {ex}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Client-side fallback: parse W/H/D from prompt text. */
function parsePromptFallback(text: string) {
  const lower = text.toLowerCase()
  let furniture_type = 'wardrobe'
  if (lower.includes('신발') || lower.includes('shoe')) furniture_type = 'shoe_rack'
  else if (lower.includes('주방') || lower.includes('싱크') || lower.includes('kitchen')) furniture_type = 'kitchen_base'
  else if (lower.includes('상부')) furniture_type = 'kitchen_wall'

  const wMatch = text.match(/[wW]\s*(\d{3,5})/)
  const hMatch = text.match(/[hH]\s*(\d{3,5})/)
  const dMatch = text.match(/[dD]\s*(\d{3,4})/)
  const mMatch = text.match(/(\d)\s*칸/)

  return {
    furniture_type,
    factory_params: {
      width: wMatch ? parseInt(wMatch[1]) : (furniture_type === 'shoe_rack' ? 900 : 2400),
      height: hMatch ? parseInt(hMatch[1]) : (furniture_type === 'shoe_rack' ? 1200 : 2200),
      depth: dMatch ? parseInt(dMatch[1]) : (furniture_type === 'shoe_rack' ? 350 : 620),
      module_count: mMatch ? parseInt(mMatch[1]) : 3,
    },
  }
}
