/**
 * frontend/src/pages/OperationsDashboard.tsx
 *
 * T032 — Operations Dashboard — Real-time queue monitoring & audit trail viewer.
 *
 * Layout:
 *   Top row:  Five queue stat cards (Unassigned, Claimed, Escalated,
 *             Pending Verification, Total Active)
 *   Left:     Case search/filter table (member_id, cpt_code search)
 *             → clicking a row loads its audit trail
 *   Right:    Audit trail timeline for the selected case
 *
 * Endpoints consumed:
 *   GET /api/v1/ops/queues                     — queue stats
 *   GET /api/v1/ops/cases?member_id=&cpt_code= — case search
 *   GET /api/v1/audit/cases/{case_id}          — audit trail
 */

import { useState, useEffect, useCallback } from 'react'
import './OperationsDashboard.css'

// ─── Types ────────────────────────────────────────────────────────────────────

interface QueueStats {
  unassigned: number
  claimed: number
  escalated: number
  pending_verification: number
  total_active: number
}

interface OpsCaseItem {
  id: string
  member_id: string
  provider_id: string
  cpt_code: string
  icd10_code: string
  service_type: string
  requested_date: string
  review_status: string
  assigned_queue: string
  claimed_by_id: string | null
  entered_review_at: string | null
  created_at: string
}

interface AuditLogEntry {
  id: string
  case_id: string
  actor_id: string
  action_type: string
  details: Record<string, unknown>
  timestamp: string
}

interface AuditTrail {
  case_id: string
  total_events: number
  events: AuditLogEntry[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function actionBadgeClass(action: string): string {
  const map: Record<string, string> = {
    llm_completion: 'badge--llm',
    rag_retrieval: 'badge--rag',
    checklist_override: 'badge--override',
    case_claimed: 'badge--claimed',
    case_decision: 'badge--decision',
    sla_escalation: 'badge--escalation',
    policy_ingested: 'badge--policy',
    case_submitted: 'badge--submitted',
  }
  return `audit-badge ${map[action] ?? 'badge--default'}`
}

function actionIcon(action: string): string {
  const map: Record<string, string> = {
    llm_completion: '🤖',
    rag_retrieval: '🔍',
    checklist_override: '✏️',
    case_claimed: '🔒',
    case_decision: '⚖️',
    sla_escalation: '🚨',
    policy_ingested: '📋',
    case_submitted: '📨',
  }
  return map[action] ?? '📌'
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: number
  variant: 'blue' | 'teal' | 'amber' | 'red' | 'emerald'
  icon: string
}

function StatCard({ label, value, variant, icon }: StatCardProps) {
  return (
    <div className={`stat-card stat-card--${variant}`} id={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="stat-card__icon">{icon}</div>
      <div className="stat-card__body">
        <span className="stat-card__value">{value.toLocaleString()}</span>
        <span className="stat-card__label">{label}</span>
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function OperationsDashboard() {
  const [stats, setStats] = useState<QueueStats | null>(null)
  const [statsError, setStatsError] = useState<string | null>(null)

  const [cases, setCases] = useState<OpsCaseItem[]>([])
  const [casesError, setCasesError] = useState<string | null>(null)
  const [loadingCases, setLoadingCases] = useState(false)

  const [memberFilter, setMemberFilter] = useState('')
  const [cptFilter, setCptFilter] = useState('')

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [auditTrail, setAuditTrail] = useState<AuditTrail | null>(null)
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [auditError, setAuditError] = useState<string | null>(null)

  // ─── Load queue stats ──────────────────────────────────────────────────────

  const loadStats = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/ops/queues')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setStats(await r.json())
      setStatsError(null)
    } catch (e: unknown) {
      setStatsError(e instanceof Error ? e.message : 'Failed to load stats')
    }
  }, [])

  useEffect(() => {
    loadStats()
    // Auto-refresh stats every 30s
    const interval = setInterval(loadStats, 30_000)
    return () => clearInterval(interval)
  }, [loadStats])

  // ─── Search cases ──────────────────────────────────────────────────────────

  const searchCases = useCallback(async () => {
    setLoadingCases(true)
    setCasesError(null)
    try {
      const params = new URLSearchParams()
      if (memberFilter.trim()) params.set('member_id', memberFilter.trim())
      if (cptFilter.trim()) params.set('cpt_code', cptFilter.trim())
      const r = await fetch(`/api/v1/ops/cases?${params}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setCases(await r.json())
    } catch (e: unknown) {
      setCasesError(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setLoadingCases(false)
    }
  }, [memberFilter, cptFilter])

  useEffect(() => { searchCases() }, [searchCases])

  // ─── Load audit trail ──────────────────────────────────────────────────────

  const loadAudit = useCallback(async (caseId: string) => {
    setSelectedCaseId(caseId)
    setLoadingAudit(true)
    setAuditError(null)
    try {
      const r = await fetch(`/api/v1/audit/cases/${caseId}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setAuditTrail(await r.json())
    } catch (e: unknown) {
      setAuditError(e instanceof Error ? e.message : 'Failed to load audit trail')
    } finally {
      setLoadingAudit(false)
    }
  }, [])

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="ops-dashboard" id="ops-dashboard">
      {/* Header */}
      <header className="ops-header">
        <div>
          <h1 className="ops-header__title">Operations Dashboard</h1>
          <p className="ops-header__subtitle">Real-time queue monitoring & compliance audit trail</p>
        </div>
        <button
          id="ops-refresh-btn"
          className="ops-header__refresh"
          onClick={() => { loadStats(); searchCases() }}
          title="Refresh all data"
        >
          ↻ Refresh
        </button>
      </header>

      {/* Queue stat cards */}
      <section className="ops-stats" aria-label="Queue statistics">
        {statsError && (
          <div className="ops-error" role="alert">Stats: {statsError}</div>
        )}
        {stats ? (
          <>
            <StatCard label="Unassigned" value={stats.unassigned} variant="blue" icon="👤" />
            <StatCard label="Claimed" value={stats.claimed} variant="teal" icon="🔒" />
            <StatCard label="Escalated" value={stats.escalated} variant="red" icon="🚨" />
            <StatCard label="Pending Verification" value={stats.pending_verification} variant="amber" icon="⏳" />
            <StatCard label="Total Active" value={stats.total_active} variant="emerald" icon="📊" />
          </>
        ) : (
          <div className="ops-stats__loading">
            <div className="ops-spinner" /> Loading stats…
          </div>
        )}
      </section>

      {/* Main two-panel layout */}
      <div className="ops-main">
        {/* Left: Case search table */}
        <section className="ops-panel ops-panel--cases" id="ops-cases-panel" aria-label="Case search">
          <div className="ops-panel__header">
            <h2 className="ops-panel__title">Cases</h2>
            <span className="ops-panel__count">{cases.length} result{cases.length !== 1 ? 's' : ''}</span>
          </div>

          {/* Filters */}
          <div className="ops-filters" id="ops-filters">
            <input
              id="ops-member-filter"
              className="ops-input"
              type="text"
              placeholder="Filter by Member ID…"
              value={memberFilter}
              onChange={e => setMemberFilter(e.target.value)}
              aria-label="Member ID filter"
            />
            <input
              id="ops-cpt-filter"
              className="ops-input"
              type="text"
              placeholder="CPT Code (exact)…"
              value={cptFilter}
              onChange={e => setCptFilter(e.target.value)}
              aria-label="CPT code filter"
            />
          </div>

          {casesError && (
            <div className="ops-error" role="alert">{casesError}</div>
          )}

          {loadingCases ? (
            <div className="ops-panel__loading"><div className="ops-spinner" /></div>
          ) : cases.length === 0 ? (
            <div className="ops-panel__empty">No cases found.</div>
          ) : (
            <div className="ops-table-wrap">
              <table className="ops-table" aria-label="Cases">
                <thead>
                  <tr>
                    <th>Member</th>
                    <th>CPT</th>
                    <th>Status</th>
                    <th>Queue</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map(c => (
                    <tr
                      key={c.id}
                      id={`ops-case-row-${c.id}`}
                      className={`ops-table__row ${selectedCaseId === c.id ? 'ops-table__row--selected' : ''}`}
                      onClick={() => loadAudit(c.id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={e => e.key === 'Enter' && loadAudit(c.id)}
                      aria-selected={selectedCaseId === c.id}
                    >
                      <td className="ops-table__member">{c.member_id}</td>
                      <td>
                        <span className="ops-cpt-badge">{c.cpt_code}</span>
                      </td>
                      <td>
                        <span className={`ops-status-pill ops-status-pill--${c.review_status}`}>
                          {c.review_status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="ops-table__queue">
                        {c.assigned_queue === 'escalation_manager'
                          ? <span className="ops-escalated-badge">🚨 Escalated</span>
                          : c.assigned_queue.replace(/_/g, ' ')}
                      </td>
                      <td className="ops-table__date">{formatDate(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Right: Audit trail */}
        <section className="ops-panel ops-panel--audit" id="ops-audit-panel" aria-label="Audit trail">
          <div className="ops-panel__header">
            <h2 className="ops-panel__title">Audit Trail</h2>
            {auditTrail && (
              <span className="ops-panel__count">{auditTrail.total_events} event{auditTrail.total_events !== 1 ? 's' : ''}</span>
            )}
          </div>

          {!selectedCaseId && (
            <div className="ops-panel__empty">
              Select a case from the table to view its audit trail.
            </div>
          )}

          {loadingAudit && (
            <div className="ops-panel__loading"><div className="ops-spinner" /></div>
          )}

          {auditError && (
            <div className="ops-error" role="alert">{auditError}</div>
          )}

          {auditTrail && !loadingAudit && (
            <>
              <p className="audit-case-id">Case: <code>{auditTrail.case_id}</code></p>
              <div className="audit-timeline" id="audit-timeline">
                {auditTrail.events.length === 0 ? (
                  <div className="ops-panel__empty">No audit events recorded yet.</div>
                ) : (
                  auditTrail.events.map((evt, idx) => (
                    <div
                      key={evt.id}
                      id={`audit-event-${evt.id}`}
                      className="audit-event"
                      aria-label={`Audit event: ${evt.action_type}`}
                    >
                      {/* Timeline line */}
                      <div className="audit-event__line">
                        <div className="audit-event__dot" />
                        {idx < auditTrail.events.length - 1 && (
                          <div className="audit-event__connector" />
                        )}
                      </div>

                      <div className="audit-event__card">
                        <div className="audit-event__row">
                          <span className={actionBadgeClass(evt.action_type)}>
                            {actionIcon(evt.action_type)}{' '}
                            {evt.action_type.replace(/_/g, ' ')}
                          </span>
                          <span className="audit-event__time">{formatDate(evt.timestamp)}</span>
                        </div>
                        <div className="audit-event__actor">
                          actor: <code>{evt.actor_id}</code>
                        </div>
                        {Object.keys(evt.details).length > 0 && (
                          <details className="audit-event__details">
                            <summary>Details</summary>
                            <pre className="audit-event__json">
                              {JSON.stringify(evt.details, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
