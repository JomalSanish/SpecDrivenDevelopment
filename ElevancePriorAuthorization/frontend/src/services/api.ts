/**
 * frontend/src/services/api.ts
 * Typed HTTP client for the PA Evidence Assistant backend.
 * All calls go to /api/* which is proxied to FastAPI by Vite (vite.config.ts).
 */
import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

export interface PolicyRequirement {
  id: string
  description: string
  matching_criteria?: Record<string, unknown>
}

export interface PolicyIngestResponse {
  policy_id: string
  title: string
  service_line_code: string
  version: string
  requirements: PolicyRequirement[]
}

export interface CaseCreateResponse {
  case_id: string
  status: string
}

// --------------------------------------------------------------------------
// Admin API
// --------------------------------------------------------------------------

export async function ingestPolicy(form: FormData): Promise<PolicyIngestResponse> {
  const res = await client.post<PolicyIngestResponse>('/admin/policies', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

// --------------------------------------------------------------------------
// Intake API
// --------------------------------------------------------------------------

export async function createCase(form: FormData): Promise<CaseCreateResponse> {
  const res = await client.post<CaseCreateResponse>('/intake/cases', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
