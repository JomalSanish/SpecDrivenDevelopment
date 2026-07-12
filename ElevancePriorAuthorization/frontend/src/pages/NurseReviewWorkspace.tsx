/**
 * frontend/src/pages/NurseReviewWorkspace.tsx
 *
 * T025 — Nurse Review Workspace — Human-in-the-loop case review UI.
 *
 * Three-panel layout (per ui-spec.md):
 *   Left   : Case Summary (member/provider metadata, policy, status, claim button)
 *   Center : DocumentViewer (T026) — in-app PDF viewer, citation-navigable
 *   Right  : CompletenessChecklist (T027) — Present/Absent/Unclear with overrides
 *
 * Action Footer:
 *   Accept — sets review_status = 'accepted' (constitution §I, no automated decision)
 *   Reject — opens modal with structured reason code + mandatory notes field
 *             maps to review_status = 'returned_to_provider'
 *
 * Endpoints consumed:
 *   GET  /api/v1/review/cases          — worklist
 *   GET  /api/v1/review/cases/:id      — case detail
 *   POST /api/v1/review/cases/:id/claim
 *   POST /api/v1/review/cases/:id/decision
 */

import { useState, useEffect, useCallback } from 'react'
import DocumentViewer, { DocumentMeta } from '../components/DocumentViewer'
import CompletenessChecklist, { ChecklistItem } from '../components/CompletenessChecklist'
import './NurseReviewWorkspace.css'

// ─── Types ───────────────────────────────────────────────────────────────────

interface CaseListItem {
  id: string
  member_id: string
  provider_id: string
  cpt_code: string
  icd10_code: string
  service_type: string
  requested_date: string
  policy_id: string
  policy_title?: string
  review_status: string
  assigned_queue: string
  claimed_by_id?: string
  entered_review_at?: string
  created_at: string
}

interface CaseDetail extends CaseListItem {
  decision_reason?: string
  decision_at?: string
  decided_by_id?: string
  documents: Array<{
    id: string
    document_type: string
    storage_path: string
    uploaded_at: string
  }>
  completeness_report: ChecklistItem[]
}

const REASON_CODES = [
  'MISSING_CLINICAL_NOTES',
  'MISSING_LAB_RESULTS',
  'MISSING_REFERRAL',
  'MISSING_PRIOR_AUTH_HISTORY',
  'DOCUMENTATION_INCOMPLETE',
  'CRITERIA_NOT_MET',
  'POLICY_NOT_APPLICABLE',
  'DUPLICATE_REQUEST',
  'OTHER',
]

// Stable demo nurse ID for local dev (real auth will inject this via session)
const DEV_NURSE_ID = '00000000-0000-0000-0000-000000000001'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusPill({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    in_nurse_review: 'pill--review',
    pending_verification: 'pill--pending',
    accepted: 'pill--accepted',
    returned_to_provider: 'pill--returned',
  }
  return (
    <span className={`status-pill ${colorMap[status] ?? ''}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function NurseReviewWorkspace() {
  const [cases, setCases] = useState<CaseListItem[]>([])
  const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  // Claim state
  const [claiming, setClaiming] = useState(false)
  const [claimError, setClaimError] = useState<string | null>(null)

  // Decision modal
  const [showDecisionModal, setShowDecisionModal] = useState(false)
  const [decisionAction, setDecisionAction] = useState<'Accept' | 'Reject' | null>(null)
  const [reasonCode, setReasonCode] = useState(REASON_CODES[0])
  const [notes, setNotes] = useState('')
  const [submittingDecision, setSubmittingDecision] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)

  // Citation navigation
  const [activeDocId, setActiveDocId] = useState<string | undefined>(undefined)

  // ─── Load worklist ────────────────────────────────────────────────────────

  const loadCases = useCallback(async () => {
    setLoadingList(true)
    setListError(null)
    try {
      const resp = await fetch('/api/v1/review/cases')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: CaseListItem[] = await resp.json()
      setCases(data)
    } catch (e: unknown) {
      setListError(e instanceof Error ? e.message : 'Failed to load cases')
    } finally {
      setLoadingList(false)
    }
  }, [])

  useEffect(() => { loadCases() }, [loadCases])

  // ─── Load case detail ─────────────────────────────────────────────────────

  const loadDetail = useCallback(async (caseId: string) => {
    setLoadingDetail(true)
    setDetailError(null)
    setClaimError(null)
    setActiveDocId(undefined)
    try {
      const resp = await fetch(`/api/v1/review/cases/${caseId}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data: CaseDetail = await resp.json()
      setSelectedCase(data)
    } catch (e: unknown) {
      setDetailError(e instanceof Error ? e.message : 'Failed to load case detail')
    } finally {
      setLoadingDetail(false)
    }
  }, [])

  // ─── Claim lock ───────────────────────────────────────────────────────────

  const handleClaim = async () => {
    if (!selectedCase) return
    setClaiming(true)
    setClaimError(null)
    try {
      const resp = await fetch(
        `/api/v1/review/cases/${selectedCase.id}/claim?nurse_id=${DEV_NURSE_ID}`,
        { method: 'POST' }
      )
      if (resp.status === 409) {
        const err = await resp.json()
        throw new Error(
          err?.detail?.message ?? 'Case already claimed by another nurse.'
        )
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      // Refresh detail to get updated claimed_by_id
      await loadDetail(selectedCase.id)
    } catch (e: unknown) {
      setClaimError(e instanceof Error ? e.message : 'Claim failed')
    } finally {
      setClaiming(false)
    }
  }

  // ─── Decision ─────────────────────────────────────────────────────────────

  const openDecisionModal = (action: 'Accept' | 'Reject') => {
    setDecisionAction(action)
    setReasonCode(REASON_CODES[0])
    setNotes('')
    setDecisionError(null)
    setShowDecisionModal(true)
  }

  const submitDecision = async () => {
    if (!selectedCase || !decisionAction) return
    if (decisionAction === 'Reject' && !notes.trim()) {
      setDecisionError('Notes are required for Reject decisions.')
      return
    }
    setSubmittingDecision(true)
    setDecisionError(null)
    try {
      const resp = await fetch(
        `/api/v1/review/cases/${selectedCase.id}/decision`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            nurse_id: DEV_NURSE_ID,
            action: decisionAction,
            reason_code: reasonCode,
            notes: notes.trim() || null,
          }),
        }
      )
      if (resp.status === 403) {
        throw new Error('You do not hold the claim lock for this case.')
      }
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err?.detail ?? `HTTP ${resp.status}`)
      }
      setShowDecisionModal(false)
      setSelectedCase(null)
      await loadCases()
    } catch (e: unknown) {
      setDecisionError(e instanceof Error ? e.message : 'Decision submission failed')
    } finally {
      setSubmittingDecision(false)
    }
  }

  // ─── Derived state ────────────────────────────────────────────────────────

  const isMyCase = selectedCase?.claimed_by_id === DEV_NURSE_ID
  const isClaimed = !!selectedCase?.claimed_by_id
  const canDecide = isMyCase
  const documents: DocumentMeta[] = (selectedCase?.documents ?? []).map((d) => ({
    id: d.id,
    document_type: d.document_type,
    storage_path: d.storage_path,
    uploaded_at: d.uploaded_at,
  }))

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="nurse-workspace" id="nurse-review-workspace">
      {/* ── Sidebar: worklist ── */}
      <aside className="workspace-sidebar" id="nurse-worklist">
        <div className="workspace-sidebar__header">
          <div>
            <h1 className="workspace-sidebar__title">Nurse Review</h1>
            <p className="workspace-sidebar__subtitle">Prior Authorization Queue</p>
          </div>
          <button
            id="worklist-refresh-btn"
            className="workspace-sidebar__refresh"
            onClick={loadCases}
            title="Refresh worklist"
            aria-label="Refresh worklist"
          >
            ↻
          </button>
        </div>

        {listError && (
          <div className="workspace-sidebar__error" role="alert">
            {listError}
          </div>
        )}

        {loadingList ? (
          <div className="workspace-sidebar__loading">
            <div className="spinner" />
          </div>
        ) : cases.length === 0 ? (
          <div className="workspace-sidebar__empty">
            No cases in nurse review queue.
          </div>
        ) : (
          <ul className="worklist" aria-label="Cases awaiting nurse review">
            {cases.map((c) => (
              <li
                key={c.id}
                id={`worklist-item-${c.id}`}
                className={`worklist__item ${selectedCase?.id === c.id ? 'worklist__item--active' : ''}`}
                onClick={() => loadDetail(c.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && loadDetail(c.id)}
                aria-selected={selectedCase?.id === c.id}
              >
                <div className="worklist__row">
                  <span className="worklist__member">{c.member_id}</span>
                  {c.claimed_by_id && (
                    <span className="worklist__locked" title="Claimed by a nurse">🔒</span>
                  )}
                </div>
                <div className="worklist__meta">
                  <span className="worklist__cpt">CPT {c.cpt_code}</span>
                  <span className="worklist__dot">·</span>
                  <span className="worklist__queue">{c.assigned_queue.replace(/_/g, ' ')}</span>
                </div>
                {c.policy_title && (
                  <span className="worklist__policy">{c.policy_title}</span>
                )}
                {c.entered_review_at && (
                  <span className="worklist__date">{formatDate(c.entered_review_at)}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </aside>

      {/* ── Main area ── */}
      <main className="workspace-main">
        {!selectedCase && !loadingDetail && (
          <div className="workspace-main__placeholder">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
              <path d="M9 11l3 3L22 4"/>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
            </svg>
            <p>Select a case from the worklist to begin review.</p>
          </div>
        )}

        {loadingDetail && (
          <div className="workspace-main__loading">
            <div className="spinner spinner--large" />
            <span>Loading case…</span>
          </div>
        )}

        {detailError && (
          <div className="workspace-main__error" role="alert">
            {detailError}
          </div>
        )}

        {selectedCase && !loadingDetail && (
          <div className="workspace-layout">
            {/* ── Left: Case Summary ── */}
            <section className="ws-panel ws-panel--summary" id="case-summary-panel" aria-label="Case summary">
              <div className="ws-panel__header">
                <h2 className="ws-panel__title">Case Summary</h2>
                <StatusPill status={selectedCase.review_status} />
              </div>

              <dl className="case-meta">
                <div className="case-meta__row">
                  <dt>Member ID</dt>
                  <dd id="case-member-id">{selectedCase.member_id}</dd>
                </div>
                <div className="case-meta__row">
                  <dt>Provider ID</dt>
                  <dd id="case-provider-id">{selectedCase.provider_id}</dd>
                </div>
                <div className="case-meta__row">
                  <dt>CPT Code</dt>
                  <dd id="case-cpt-code">{selectedCase.cpt_code}</dd>
                </div>
                <div className="case-meta__row">
                  <dt>ICD-10</dt>
                  <dd id="case-icd10">{selectedCase.icd10_code}</dd>
                </div>
                <div className="case-meta__row">
                  <dt>Service Type</dt>
                  <dd>{selectedCase.service_type}</dd>
                </div>
                <div className="case-meta__row">
                  <dt>Requested</dt>
                  <dd>{formatDate(selectedCase.requested_date)}</dd>
                </div>
                <div className="case-meta__row">
                  <dt>Queue</dt>
                  <dd>{selectedCase.assigned_queue.replace(/_/g, ' ')}</dd>
                </div>
                {selectedCase.policy_title && (
                  <div className="case-meta__row">
                    <dt>Policy</dt>
                    <dd id="case-policy-title">{selectedCase.policy_title}</dd>
                  </div>
                )}
                {selectedCase.entered_review_at && (
                  <div className="case-meta__row">
                    <dt>In Review Since</dt>
                    <dd>{formatDate(selectedCase.entered_review_at)}</dd>
                  </div>
                )}
              </dl>

              {/* Claim section */}
              <div className="ws-claim-section">
                {isClaimed && !isMyCase && (
                  <div className="ws-claim-section__claimed">
                    🔒 Claimed by another nurse
                  </div>
                )}
                {isMyCase && (
                  <div className="ws-claim-section__mine">
                    ✅ You hold the lock
                  </div>
                )}
                {!isClaimed && (
                  <button
                    id="claim-case-btn"
                    className="btn-primary ws-claim-section__btn"
                    onClick={handleClaim}
                    disabled={claiming}
                    aria-label="Claim case for review"
                  >
                    {claiming ? <span className="spinner" /> : '🔒 Claim Case'}
                  </button>
                )}
                {claimError && (
                  <div className="ws-claim-section__error" role="alert">
                    {claimError}
                  </div>
                )}
              </div>

              {/* Action footer */}
              {canDecide && (
                <div className="ws-action-footer">
                  <button
                    id="accept-case-btn"
                    className="ws-action-footer__btn ws-action-footer__btn--accept"
                    onClick={() => openDecisionModal('Accept')}
                    aria-label="Accept case"
                  >
                    ✓ Accept
                  </button>
                  <button
                    id="reject-case-btn"
                    className="ws-action-footer__btn ws-action-footer__btn--reject"
                    onClick={() => openDecisionModal('Reject')}
                    aria-label="Reject case — returns to provider"
                  >
                    ✗ Reject
                  </button>
                </div>
              )}

              {/* Case UUID */}
              <code className="case-uuid" title="Case UUID">
                {selectedCase.id}
              </code>
            </section>

            {/* ── Center: Document Viewer ── */}
            <section className="ws-panel ws-panel--viewer" id="document-viewer-panel" aria-label="Document viewer">
              <div className="ws-panel__header">
                <h2 className="ws-panel__title">Documents</h2>
                <span className="ws-panel__count">{documents.length} file{documents.length !== 1 ? 's' : ''}</span>
              </div>
              <DocumentViewer
                documents={documents}
                activeDocumentId={activeDocId}
                onDocumentSelect={(id) => setActiveDocId(id)}
              />
            </section>

            {/* ── Right: Completeness Checklist ── */}
            <section className="ws-panel ws-panel--checklist" id="completeness-panel" aria-label="Completeness checklist">
              <div className="ws-panel__header">
                <h2 className="ws-panel__title">Completeness</h2>
                <span className="ws-panel__count">
                  {selectedCase.completeness_report.length} item{selectedCase.completeness_report.length !== 1 ? 's' : ''}
                </span>
              </div>
              <CompletenessChecklist
                caseId={selectedCase.id}
                nurseId={DEV_NURSE_ID}
                items={selectedCase.completeness_report}
                onCitationClick={(docId) => setActiveDocId(docId)}
                onOverrideApplied={() => {
                  /* optimistic update handled inside component */
                }}
              />
            </section>
          </div>
        )}
      </main>

      {/* ── Decision Modal ── */}
      {showDecisionModal && decisionAction && (
        <div
          className="decision-modal-overlay"
          id="decision-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="decision-modal-title"
          onClick={(e) => { if (e.target === e.currentTarget) setShowDecisionModal(false) }}
        >
          <div className="decision-modal">
            <div className="decision-modal__header">
              <h2 id="decision-modal-title" className={`decision-modal__title ${decisionAction === 'Accept' ? 'decision-modal__title--accept' : 'decision-modal__title--reject'}`}>
                {decisionAction === 'Accept' ? '✓ Accept Case' : '✗ Reject Case'}
              </h2>
              {decisionAction === 'Reject' && (
                <p className="decision-modal__subtitle">
                  Rejecting returns this case to the provider for additional documentation.
                  There is no terminal denial — the provider can resubmit.
                </p>
              )}
              {decisionAction === 'Accept' && (
                <p className="decision-modal__subtitle">
                  This decision is irreversible once submitted.
                </p>
              )}
            </div>

            <div className="decision-modal__form">
              <div className="form-group">
                <label htmlFor="decision-reason-code">Reason Code *</label>
                <select
                  id="decision-reason-code"
                  className="decision-modal__select"
                  value={reasonCode}
                  onChange={(e) => setReasonCode(e.target.value)}
                >
                  {REASON_CODES.map((c) => (
                    <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="decision-notes">
                  Notes {decisionAction === 'Reject' ? '*' : '(optional)'}
                </label>
                <textarea
                  id="decision-notes"
                  className="decision-modal__textarea"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder={
                    decisionAction === 'Reject'
                      ? 'Explain what documentation is missing or what criteria were not met…'
                      : 'Optional approval notes…'
                  }
                  rows={4}
                />
              </div>

              {decisionError && (
                <div className="decision-modal__error" role="alert">
                  {decisionError}
                </div>
              )}
            </div>

            <div className="decision-modal__actions">
              <button
                id="decision-cancel-btn"
                className="btn-secondary"
                onClick={() => setShowDecisionModal(false)}
                disabled={submittingDecision}
              >
                Cancel
              </button>
              <button
                id="decision-submit-btn"
                className={`btn-primary ${decisionAction === 'Accept' ? 'btn-primary--accept' : 'btn-primary--reject'}`}
                onClick={submitDecision}
                disabled={submittingDecision}
              >
                {submittingDecision ? (
                  <span className="spinner" />
                ) : decisionAction === 'Accept' ? (
                  'Confirm Accept'
                ) : (
                  'Confirm Reject'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
