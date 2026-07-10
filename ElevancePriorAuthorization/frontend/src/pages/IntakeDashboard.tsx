/**
 * frontend/src/pages/IntakeDashboard.tsx
 *
 * Intake Dashboard — combines two forms:
 *   1. Admin Policy Upload — uploads a policy PDF and displays extracted requirements.
 *   2. Case Submission — collects case metadata + evidence documents and submits a PA case.
 *
 * US1: Admin Policy Ingestion
 * US2: Case Submission & Completeness Check (intake step)
 */
import { useState, useRef } from 'react'
import { ingestPolicy, createCase, PolicyRequirement, PolicyIngestResponse } from '../services/api'
import './IntakeDashboard.css'

// ---------------------------------------------------------------------------
// Sub-component: Policy Upload Panel
// ---------------------------------------------------------------------------

interface PolicyUploadPanelProps {
  onPolicyIngested: (policy: PolicyIngestResponse) => void
}

function PolicyUploadPanel({ onPolicyIngested }: PolicyUploadPanelProps) {
  const [title, setTitle] = useState('')
  const [serviceLineCode, setServiceLineCode] = useState('')
  const [version, setVersion] = useState('')
  const [slaHours, setSlaHours] = useState<string>('')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) { setError('Please select a policy PDF.'); return }
    setLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('title', title)
      form.append('service_line_code', serviceLineCode)
      form.append('version', version)
      if (slaHours) form.append('sla_hours', slaHours)
      form.append('document', file)
      const result = await ingestPolicy(form)
      onPolicyIngested(result)
      setTitle(''); setServiceLineCode(''); setVersion(''); setSlaHours(''); setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Policy ingestion failed. Is the backend and Ollama running?'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel" id="policy-upload-panel">
      <h2>Upload Policy Document</h2>
      <p className="panel-description">
        Upload a payer policy PDF to extract the required evidence checklist using the local AI agent.
      </p>
      <form onSubmit={handleSubmit} className="intake-form" id="policy-upload-form">
        <div className="form-group">
          <label htmlFor="policy-title">Policy Title</label>
          <input
            id="policy-title"
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="e.g. MRI Lumbar Spine PA Policy"
            required
          />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="service-line-code">Service Line Code</label>
            <input
              id="service-line-code"
              type="text"
              value={serviceLineCode}
              onChange={e => setServiceLineCode(e.target.value)}
              placeholder="e.g. MRI_LUMBAR"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="policy-version">Version</label>
            <input
              id="policy-version"
              type="text"
              value={version}
              onChange={e => setVersion(e.target.value)}
              placeholder="e.g. 2024-Q1"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="sla-hours">SLA Hours (optional)</label>
            <input
              id="sla-hours"
              type="number"
              min={1}
              value={slaHours}
              onChange={e => setSlaHours(e.target.value)}
              placeholder="e.g. 48"
            />
          </div>
        </div>
        <div className="form-group">
          <label htmlFor="policy-file">Policy PDF</label>
          <div className="file-drop-zone" onClick={() => fileRef.current?.click()}>
            {file ? (
              <span className="file-name">📄 {file.name}</span>
            ) : (
              <span className="file-placeholder">Click to select a PDF policy document</span>
            )}
          </div>
          <input
            id="policy-file"
            ref={fileRef}
            type="file"
            accept="application/pdf"
            style={{ display: 'none' }}
            onChange={e => setFile(e.target.files?.[0] ?? null)}
            required
          />
        </div>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button id="policy-submit-btn" type="submit" className="btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : null}
          {loading ? 'Extracting requirements…' : 'Upload & Extract Requirements'}
        </button>
      </form>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Sub-component: Requirements Result
// ---------------------------------------------------------------------------

function RequirementsResult({ policy }: { policy: PolicyIngestResponse }) {
  return (
    <section className="panel result-panel" id="policy-result-panel">
      <h3>✅ Policy Ingested Successfully</h3>
      <div className="policy-meta">
        <span className="badge">{policy.service_line_code}</span>
        <span className="badge secondary">{policy.version}</span>
        <code className="uuid">ID: {policy.policy_id}</code>
      </div>
      <h4>{policy.requirements.length} Requirement{policy.requirements.length !== 1 ? 's' : ''} Extracted</h4>
      <ul className="requirements-list" id="extracted-requirements-list">
        {policy.requirements.map((req, i) => (
          <li key={req.id} className="requirement-item" id={`req-${req.id}`}>
            <span className="req-index">{i + 1}</span>
            <span className="req-description">{req.description}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Sub-component: Case Submission Panel
// ---------------------------------------------------------------------------

interface CaseSubmissionPanelProps {
  defaultPolicyId?: string
}

function CaseSubmissionPanel({ defaultPolicyId }: CaseSubmissionPanelProps) {
  const [memberId, setMemberId] = useState('')
  const [providerId, setProviderId] = useState('')
  const [cptCode, setCptCode] = useState('')
  const [icd10Code, setIcd10Code] = useState('')
  const [serviceType, setServiceType] = useState('')
  const [requestedDate, setRequestedDate] = useState('')
  const [policyId, setPolicyId] = useState(defaultPolicyId ?? '')
  const [files, setFiles] = useState<FileList | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submittedCaseId, setSubmittedCaseId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!files || files.length === 0) { setError('Please upload at least one evidence document.'); return }
    setLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('member_id', memberId)
      form.append('provider_id', providerId)
      form.append('cpt_code', cptCode)
      form.append('icd10_code', icd10Code)
      form.append('service_type', serviceType)
      form.append('requested_date', new Date(requestedDate).toISOString())
      form.append('policy_id', policyId)
      for (let i = 0; i < files.length; i++) {
        form.append('documents', files[i])
      }
      const result = await createCase(form)
      setSubmittedCaseId(result.case_id)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Case submission failed. Is the backend and MinIO running?'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (submittedCaseId) {
    return (
      <section className="panel result-panel" id="case-result-panel">
        <h3>✅ Case Submitted</h3>
        <p>Status: <strong>pending_verification</strong></p>
        <code className="uuid" id="submitted-case-id">Case ID: {submittedCaseId}</code>
        <p className="hint">The completeness pipeline will run automatically once RAG services are available.</p>
        <button className="btn-secondary" onClick={() => setSubmittedCaseId(null)}>
          Submit Another Case
        </button>
      </section>
    )
  }

  return (
    <section className="panel" id="case-submission-panel">
      <h2>Submit Prior Authorization Case</h2>
      <p className="panel-description">
        Submit case metadata and supporting documents. Evidence is stored locally — no external network egress.
      </p>
      <form onSubmit={handleSubmit} className="intake-form" id="case-submission-form">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="member-id">Member ID</label>
            <input id="member-id" type="text" value={memberId} onChange={e => setMemberId(e.target.value)} required />
          </div>
          <div className="form-group">
            <label htmlFor="provider-id">Provider ID</label>
            <input id="provider-id" type="text" value={providerId} onChange={e => setProviderId(e.target.value)} required />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="cpt-code">CPT Code</label>
            <input id="cpt-code" type="text" value={cptCode} onChange={e => setCptCode(e.target.value)} placeholder="e.g. 72148" required />
          </div>
          <div className="form-group">
            <label htmlFor="icd10-code">ICD-10 Code</label>
            <input id="icd10-code" type="text" value={icd10Code} onChange={e => setIcd10Code(e.target.value)} placeholder="e.g. M54.5" required />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="service-type">Service Type</label>
            <input id="service-type" type="text" value={serviceType} onChange={e => setServiceType(e.target.value)} placeholder="e.g. Diagnostic Imaging" required />
          </div>
          <div className="form-group">
            <label htmlFor="requested-date">Requested Date</label>
            <input id="requested-date" type="datetime-local" value={requestedDate} onChange={e => setRequestedDate(e.target.value)} required />
          </div>
        </div>
        <div className="form-group">
          <label htmlFor="case-policy-id">Policy ID (UUID)</label>
          <input
            id="case-policy-id"
            type="text"
            value={policyId}
            onChange={e => setPolicyId(e.target.value)}
            placeholder="Paste the Policy UUID from the upload result above"
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="evidence-documents">Evidence Documents</label>
          <div className="file-drop-zone" onClick={() => fileRef.current?.click()}>
            {files && files.length > 0 ? (
              <span className="file-name">
                {files.length === 1 ? `📄 ${files[0].name}` : `📁 ${files.length} files selected`}
              </span>
            ) : (
              <span className="file-placeholder">Click to select PDFs, scans, or faxes</span>
            )}
          </div>
          <input
            id="evidence-documents"
            ref={fileRef}
            type="file"
            accept="application/pdf,image/tiff,image/png,image/jpeg"
            multiple
            style={{ display: 'none' }}
            onChange={e => setFiles(e.target.files)}
            required
          />
        </div>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button id="case-submit-btn" type="submit" className="btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : null}
          {loading ? 'Submitting case…' : 'Submit Case'}
        </button>
      </form>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function IntakeDashboard() {
  const [ingestedPolicy, setIngestedPolicy] = useState<PolicyIngestResponse | null>(null)

  return (
    <main className="intake-dashboard" id="intake-dashboard">
      <header className="dashboard-header">
        <h1>PA Evidence Assistant — Intake Dashboard</h1>
        <p className="dashboard-subtitle">
          Elevance Health · Prior Authorization · All processing is local and on-premise
        </p>
        <div className="locality-badge" title="No external API calls — Constitution §II">
          🔒 On-Premise Only
        </div>
      </header>

      <div className="dashboard-columns">
        <div className="column-left">
          <PolicyUploadPanel onPolicyIngested={setIngestedPolicy} />
          {ingestedPolicy && <RequirementsResult policy={ingestedPolicy} />}
        </div>
        <div className="column-right">
          <CaseSubmissionPanel defaultPolicyId={ingestedPolicy?.policy_id} />
        </div>
      </div>
    </main>
  )
}
