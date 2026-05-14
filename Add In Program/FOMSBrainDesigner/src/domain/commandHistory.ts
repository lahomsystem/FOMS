/**
 * FOMS Brain PG-B9 — Snapshot-Based Command History (Undo/Redo).
 *
 * Stores DesignGraph snapshots so any edit can be undone/redone.
 * Snapshot approach: simple, reliable, no complex diff logic needed.
 * Max 50 entries to keep memory bounded.
 */

import type { DesignGraph } from './ontologyTypes'

const MAX_HISTORY = 50

export class CommandHistory {
  private undoStack: DesignGraph[] = []
  private redoStack: DesignGraph[] = []

  /** Call BEFORE applying a mutation. Pushes current state to undo stack. */
  push(currentGraph: DesignGraph): void {
    // Deep clone to decouple snapshot from live state
    this.undoStack.push(JSON.parse(JSON.stringify(currentGraph)) as DesignGraph)
    if (this.undoStack.length > MAX_HISTORY) {
      this.undoStack.shift()
    }
    this.redoStack = [] // new edit clears redo chain
  }

  /** Undo: returns previous state (or null if nothing to undo). */
  undo(currentGraph: DesignGraph): DesignGraph | null {
    const prev = this.undoStack.pop()
    if (!prev) return null
    this.redoStack.push(JSON.parse(JSON.stringify(currentGraph)) as DesignGraph)
    return prev
  }

  /** Redo: returns next state (or null if nothing to redo). */
  redo(currentGraph: DesignGraph): DesignGraph | null {
    const next = this.redoStack.pop()
    if (!next) return null
    this.undoStack.push(JSON.parse(JSON.stringify(currentGraph)) as DesignGraph)
    return next
  }

  canUndo(): boolean { return this.undoStack.length > 0 }
  canRedo(): boolean { return this.redoStack.length > 0 }
  undoCount(): number { return this.undoStack.length }
  redoCount(): number { return this.redoStack.length }

  clear(): void {
    this.undoStack = []
    this.redoStack = []
  }
}

/** Singleton command history shared across the app. */
export const commandHistory = new CommandHistory()
