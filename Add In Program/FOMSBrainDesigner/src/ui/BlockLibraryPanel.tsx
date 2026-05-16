/**
 * FOMS Brain Phase C4 — Block Library Panel
 *
 * 백엔드 /api/designer/blocks/ API에서 블록 목록을 fetch하여
 * 카테고리별 탭으로 표시하고, "추가" 버튼으로 캔버스에 인스턴스를 추가한다.
 */

import { useState, useEffect, useCallback } from 'react'
import { useDesignerStore } from '../stores/designerStore'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import type { Component } from '../domain/ontologyTypes'

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

type BlockCategory = 'all' | 'panel' | 'module' | 'assembly' | 'hardware' | 'other'

interface BlockDef {
  id: number
  label_ko: string
  label_en?: string
  category: string
  description?: string
  is_draft?: boolean
}

interface BlockLibraryPanelProps {
  onClose?: () => void
}

// ──────────────────────────────────────────────────────────
// Category tab config
// ──────────────────────────────────────────────────────────

const CATEGORY_TABS: { key: BlockCategory; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'panel', label: '판넬' },
  { key: 'module', label: '모듈' },
  { key: 'assembly', label: '조립' },
  { key: 'hardware', label: '하드웨어' },
  { key: 'other', label: '기타' },
]

const CATEGORY_BADGE_COLORS: Record<string, { bg: string; text: string }> = {
  panel: { bg: '#e9ecef', text: '#495057' },
  module: { bg: '#d1ecf1', text: '#0c5460' },
  assembly: { bg: '#d4edda', text: '#155724' },
  hardware: { bg: '#fff3cd', text: '#856404' },
  other: { bg: '#f8d7da', text: '#721c24' },
}

function getCategoryBadge(category: string) {
  return CATEGORY_BADGE_COLORS[category] ?? { bg: '#e2e8f0', text: '#4a5568' }
}

// ──────────────────────────────────────────────────────────
// BlockLibraryPanel
// ──────────────────────────────────────────────────────────

export function BlockLibraryPanel({ onClose }: BlockLibraryPanelProps) {
  const addComponent = useDesignerStore((s) => s.addComponent)

  const [blocks, setBlocks] = useState<BlockDef[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeCategory, setActiveCategory] = useState<BlockCategory>('all')
  const [instantiatingId, setInstantiatingId] = useState<number | null>(null)

  // ── Fetch block list ─────────────────────────────────────

  const fetchBlocks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/designer/blocks/?include_drafts=false', {
        credentials: 'same-origin',
      })
      if (!res.ok) {
        setError(`서버 오류: ${res.status}`)
        return
      }
      const data = await res.json()
      if (!data.success) {
        setError(data.error ?? '블록 목록을 불러오지 못했습니다.')
        return
      }
      setBlocks(data.data ?? [])
    } catch {
      setError('네트워크 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBlocks()
  }, [fetchBlocks])

  // ── Instantiate block ────────────────────────────────────

  async function handleAdd(block: BlockDef) {
    if (instantiatingId !== null) return
    setInstantiatingId(block.id)
    try {
      const res = await fetch(`/api/designer/blocks/${block.id}/instantiate`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (!data.success) {
        setError(data.error ?? '블록 추가에 실패했습니다.')
        return
      }
      const component = data.data as Component
      addComponent(component)
    } catch {
      setError('네트워크 오류가 발생했습니다.')
    } finally {
      setInstantiatingId(null)
    }
  }

  // ── Filtered blocks ──────────────────────────────────────

  const filteredBlocks = activeCategory === 'all'
    ? blocks
    : blocks.filter((b) => b.category === activeCategory)

  // ── Render ───────────────────────────────────────────────

  return (
    <div style={panelStyles.container}>
      {/* Header */}
      <div style={panelStyles.header}>
        <span style={panelStyles.title}>블록 라이브러리</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button
            onClick={fetchBlocks}
            title="새로고침"
            style={panelStyles.iconBtn}
            disabled={loading}
          >
            ↻
          </button>
          {onClose && (
            <button
              onClick={onClose}
              title="닫기"
              style={panelStyles.iconBtn}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Category tabs */}
      <div style={panelStyles.tabBar}>
        {CATEGORY_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveCategory(tab.key)}
            style={{
              ...panelStyles.tab,
              ...(activeCategory === tab.key ? panelStyles.tabActive : {}),
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error banner */}
      {error && (
        <div style={panelStyles.errorBanner}>
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#721c24', fontWeight: 700 }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Content */}
      <div style={panelStyles.listArea}>
        {loading ? (
          <div style={panelStyles.stateMsg}>블록 목록 로딩 중...</div>
        ) : filteredBlocks.length === 0 ? (
          <div style={panelStyles.stateMsg}>
            {blocks.length === 0
              ? '등록된 블록이 없습니다.'
              : '해당 카테고리에 블록이 없습니다.'}
          </div>
        ) : (
          filteredBlocks.map((block) => {
            const badge = getCategoryBadge(block.category)
            const isAdding = instantiatingId === block.id
            return (
              <div key={block.id} style={panelStyles.card}>
                <div style={panelStyles.cardBody}>
                  <div style={panelStyles.cardLabel}>{block.label_ko}</div>
                  {block.description && (
                    <div style={panelStyles.cardDesc}>{block.description}</div>
                  )}
                  <span style={{ ...panelStyles.badge, background: badge.bg, color: badge.text }}>
                    {block.category}
                  </span>
                </div>
                <button
                  onClick={() => handleAdd(block)}
                  disabled={isAdding || instantiatingId !== null}
                  title={`${block.label_ko} 추가`}
                  style={{
                    ...panelStyles.addBtn,
                    ...(isAdding ? panelStyles.addBtnDisabled : {}),
                  }}
                >
                  {isAdding ? '...' : '추가'}
                </button>
              </div>
            )
          })
        )}
      </div>

      {/* Footer count */}
      {!loading && (
        <div style={panelStyles.footer}>
          {filteredBlocks.length}/{blocks.length}개 표시
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────
// Styles (inline, dark-panel 테마 — InspectorPanel 동일)
// ──────────────────────────────────────────────────────────

const panelStyles: Record<string, React.CSSProperties> = {
  container: {
    background: COLORS.panelBg,
    border: `1px solid ${COLORS.panelBorder}`,
    borderRadius: 6,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    fontFamily: TYPOGRAPHY.fontFamily,
    fontSize: TYPOGRAPHY.sizeSM,
    minWidth: 220,
    maxWidth: 280,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 10px',
    borderBottom: `1px solid ${COLORS.panelBorder}`,
    background: COLORS.toolbarBg,
    flexShrink: 0,
  },
  title: {
    fontWeight: TYPOGRAPHY.weightBold,
    fontSize: TYPOGRAPHY.sizeLG,
    color: COLORS.textPrimary,
  },
  iconBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: 14,
    color: COLORS.textSecondary,
    padding: '2px 4px',
    borderRadius: 3,
  },
  tabBar: {
    display: 'flex',
    gap: 2,
    padding: '6px 8px 4px',
    borderBottom: `1px solid ${COLORS.panelBorder}`,
    flexWrap: 'wrap' as const,
    flexShrink: 0,
    background: COLORS.panelBg,
  },
  tab: {
    padding: '2px 7px',
    border: `1px solid ${COLORS.panelBorder}`,
    borderRadius: 10,
    background: COLORS.surfaceWhite,
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textSecondary,
    fontFamily: TYPOGRAPHY.fontFamily,
    fontWeight: TYPOGRAPHY.weightNormal,
  },
  tabActive: {
    background: COLORS.accent,
    borderColor: COLORS.accent,
    color: '#fff',
    fontWeight: TYPOGRAPHY.weightSemibold,
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    background: '#f8d7da',
    color: '#721c24',
    padding: '6px 10px',
    fontSize: TYPOGRAPHY.sizeXS,
    flexShrink: 0,
  },
  listArea: {
    flex: 1,
    overflowY: 'auto',
    padding: 6,
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  stateMsg: {
    color: COLORS.textMuted,
    fontSize: TYPOGRAPHY.sizeXS,
    textAlign: 'center',
    padding: '16px 8px',
  },
  card: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    background: COLORS.surfaceWhite,
    border: `1px solid ${COLORS.panelBorder}`,
    borderRadius: 5,
    padding: '6px 8px',
  },
  cardBody: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  cardLabel: {
    fontWeight: TYPOGRAPHY.weightSemibold,
    fontSize: TYPOGRAPHY.sizeMD,
    color: COLORS.textPrimary,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  cardDesc: {
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textMuted,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  badge: {
    display: 'inline-block',
    borderRadius: 8,
    padding: '1px 6px',
    fontSize: TYPOGRAPHY.sizeXS,
    fontWeight: TYPOGRAPHY.weightSemibold,
    marginTop: 2,
  },
  addBtn: {
    padding: '4px 10px',
    background: COLORS.accent,
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeXS,
    fontWeight: TYPOGRAPHY.weightSemibold,
    fontFamily: TYPOGRAPHY.fontFamily,
    flexShrink: 0,
  },
  addBtnDisabled: {
    background: COLORS.textMuted,
    cursor: 'not-allowed',
  },
  footer: {
    padding: '4px 10px',
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textMuted,
    borderTop: `1px solid ${COLORS.panelBorder}`,
    textAlign: 'right',
    flexShrink: 0,
  },
}
