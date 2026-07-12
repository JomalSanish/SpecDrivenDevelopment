/**
 * frontend/src/components/CompletenessChecklist.tsx
 *
 * T027 — Completeness Checklist panel for Nurse Review Workspace.
 *
 * Displays the system-generated CompletenessReportItems with:
 *   - Status badges (Present / Absent / Unclear) with confidence scores
 *   - Citation links that navigate the PDF viewer to the matched page
 *   - Override button: opens an inline dropdown to manually change status (CHK009)
 *     Fires POST /api/v1/review/cases/{case_id}/checklist/{item_id}/override
 *
 * Constitution §I: Override only writes overridden_status — the original
 * system-generated status is displayed alongside the override for transparency.
 */

import { useState, FC } from 'react'
import './CompletenessChecklist.css'

export type CompletionStatus = 'Present' | 'Absent' | 'Unclear'

export interface ChecklistItem {
  id: string
  policy_requirement_id: string
  requirement_description?: string
  status: CompletionStatus
  confidence_score: number
  matched_document_id?: string
  matched_chunk_id?: string
  reasoning_log?: string
  overridden_status?: CompletionStatus
  overridden_by_id?: string
  overridden_at?: string
}

interface CompletenessChecklistProps {
  caseId: string
  nurseId: string
  items: ChecklistItem[]
  /** Called when nurse clicks a citation — triggers DocumentViewer navigation */
  onCitationClick?: (documentId: string, page?: number) => void
  onOverrideApplied?: (itemId: string, newStatus: CompletionStatus) => void
}

const STATUS_OPTIONS: CompletionStatus[] = ['Present', 'Absent', 'Unclear']

function StatusBadge({ status, confidence }: { status: CompletionStatus; confidence?: number }) {
  const cls = `cl-badge cl-badge--${status.toLowerCase()}`
  return (
    <span className={cls} aria-label={`Status: ${status}`}>
      {status === 'Present' && '✓ '}
      {status === 'Absent' && '✗ '}
      {status === 'Unclear' && '? '}
      {status}
      {confidence !== undefined && (
        <span className="cl-badge__confidence">
          {' '}
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  )
}

const CompletenessChecklist: FC<CompletenessChecklistProps> = ({
  caseId,
  nurseId,
  items,
  onCitationClick,
  onOverrideApplied,
}) => {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [overrideOpenId, setOverrideOpenId] = useState<string | null>(null)
  const [overridePending, setOverridePending] = useState<string | null>(null)
  const [overrideError, setOverrideError] = useState<string | null>(null)
  /** Local override map: item_id → overridden status (optimistic UI) */
  const [localOverrides, setLocalOverrides] = useState<Record<string, CompletionStatus>>(() => {
    const m: Record<string, CompletionStatus> = {}
    items.forEach((i) => { if (i.overridden_status) m[i.id] = i.overridden_status })
    return m
  })

  const handleCitationClick = (item: ChecklistItem) => {
    if (item.matched_document_id) {
      onCitationClick?.(item.matched_document_id)
    }
  }

  const handleOverrideSelect = async (itemId: string, newStatus: CompletionStatus) => {
    setOverridePending(itemId)
    setOverrideError(null)
    try {
      const resp = await fetch(
        `/api/v1/review/cases/${caseId}/checklist/${itemId}/override`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            overridden_status: newStatus,
            nurse_id: nurseId,
          }),
        }
      )
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err?.detail ?? `HTTP ${resp.status}`)
      }
      setLocalOverrides((prev) => ({ ...prev, [itemId]: newStatus }))
      onOverrideApplied?.(itemId, newStatus)
      setOverrideOpenId(null)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Override failed'
      setOverrideError(msg)
    } finally {
      setOverridePending(null)
    }
  }

  const presentCount = items.filter(
    (i) => (localOverrides[i.id] ?? i.status) === 'Present'
  ).length
  const absentCount = items.filter(
    (i) => (localOverrides[i.id] ?? i.status) === 'Absent'
  ).length
  const unclearCount = items.filter(
    (i) => (localOverrides[i.id] ?? i.status) === 'Unclear'
  ).length

  return (
    <div className="checklist" id="completeness-checklist">
      {/* Summary bar */}
      <div className="checklist__summary">
        <span className="checklist__summary-item checklist__summary-item--present">
          ✓ {presentCount} Present
        </span>
        <span className="checklist__summary-item checklist__summary-item--absent">
          ✗ {absentCount} Absent
        </span>
        <span className="checklist__summary-item checklist__summary-item--unclear">
          ? {unclearCount} Unclear
        </span>
      </div>

      {overrideError && (
        <div className="checklist__error" role="alert">
          Override failed: {overrideError}
        </div>
      )}

      {items.length === 0 && (
        <div className="checklist__empty">
          No completeness report generated yet.
        </div>
      )}

      <ul className="checklist__list" aria-label="Completeness checklist">
        {items.map((item, idx) => {
          const effectiveStatus = localOverrides[item.id] ?? item.status
          const isOverridden = localOverrides[item.id] !== undefined
          const isExpanded = expandedId === item.id
          const isOverrideOpen = overrideOpenId === item.id
          const isPending = overridePending === item.id

          return (
            <li
              key={item.id}
              className={`checklist__item checklist__item--${effectiveStatus.toLowerCase()} ${isOverridden ? 'checklist__item--overridden' : ''}`}
              id={`checklist-item-${item.id}`}
            >
              {/* Row */}
              <div className="checklist__item-row">
                <span className="checklist__item-index">{idx + 1}</span>

                <div className="checklist__item-main">
                  <p className="checklist__item-description">
                    {item.requirement_description ?? `Requirement ${item.policy_requirement_id.slice(0, 8)}…`}
                  </p>
                  <div className="checklist__item-badges">
                    <StatusBadge status={effectiveStatus} confidence={item.confidence_score} />
                    {isOverridden && (
                      <span className="checklist__override-indicator" title={`Original: ${item.status}`}>
                        ✏ Override
                        <span className="checklist__original-status"> (was: {item.status})</span>
                      </span>
                    )}
                  </div>
                </div>

                <div className="checklist__item-actions">
                  {/* Citation link */}
                  {item.matched_document_id && (
                    <button
                      id={`checklist-citation-${item.id}`}
                      className="checklist__btn checklist__btn--citation"
                      onClick={() => handleCitationClick(item)}
                      title="Jump to evidence in document viewer"
                      aria-label="View citation"
                    >
                      🔗 View
                    </button>
                  )}

                  {/* Expand reasoning */}
                  {item.reasoning_log && (
                    <button
                      id={`checklist-expand-${item.id}`}
                      className="checklist__btn checklist__btn--expand"
                      onClick={() => setExpandedId(isExpanded ? null : item.id)}
                      aria-expanded={isExpanded}
                      aria-label={isExpanded ? 'Collapse reasoning' : 'Expand reasoning'}
                    >
                      {isExpanded ? '▲' : '▼'}
                    </button>
                  )}

                  {/* Override toggle */}
                  <div className="checklist__override-wrap">
                    <button
                      id={`checklist-override-${item.id}`}
                      className={`checklist__btn checklist__btn--override ${isOverrideOpen ? 'checklist__btn--override-open' : ''}`}
                      onClick={() => setOverrideOpenId(isOverrideOpen ? null : item.id)}
                      disabled={isPending}
                      aria-label="Override status"
                      aria-expanded={isOverrideOpen}
                      title="Manually override system status"
                    >
                      {isPending ? '…' : '✏ Override'}
                    </button>
                    {isOverrideOpen && (
                      <div className="checklist__override-menu" role="menu">
                        {STATUS_OPTIONS.map((s) => (
                          <button
                            key={s}
                            id={`override-option-${item.id}-${s}`}
                            className={`checklist__override-option checklist__override-option--${s.toLowerCase()} ${effectiveStatus === s ? 'checklist__override-option--current' : ''}`}
                            role="menuitem"
                            onClick={() => handleOverrideSelect(item.id, s)}
                          >
                            {s === 'Present' && '✓ '}
                            {s === 'Absent' && '✗ '}
                            {s === 'Unclear' && '? '}
                            {s}
                          </button>
                        ))}
                        <button
                          id={`override-cancel-${item.id}`}
                          className="checklist__override-option checklist__override-option--cancel"
                          role="menuitem"
                          onClick={() => setOverrideOpenId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Expanded reasoning log */}
              {isExpanded && item.reasoning_log && (
                <div className="checklist__reasoning" role="region" aria-label="Reasoning log">
                  <p className="checklist__reasoning-label">Reasoning</p>
                  <pre className="checklist__reasoning-text">{item.reasoning_log}</pre>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default CompletenessChecklist
