import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import React from 'react'

jest.mock('../../src/components/DocumentViewer', () => {
  return {
    __esModule: true,
    default: function MockDocumentViewer() {
      return <div data-testid="mock-document-viewer">Document Viewer Mock</div>
    }
  }
})

jest.mock('../../src/components/CompletenessChecklist', () => {
  return {
    __esModule: true,
    default: function MockCompletenessChecklist() {
      return <div data-testid="mock-checklist">Checklist Mock</div>
    }
  }
})

import NurseReviewWorkspace from '../../src/pages/NurseReviewWorkspace'

const mockCaseList = [
  {
    id: 'case-1',
    member_id: 'MEM-123',
    provider_id: 'PROV-456',
    cpt_code: '99214',
    icd10_code: 'J45.909',
    service_type: 'Outpatient',
    requested_date: '2026-07-01T10:00:00Z',
    policy_id: 'pol-1',
    policy_title: 'Asthma Management',
    review_status: 'in_nurse_review',
    assigned_queue: 'standard',
    created_at: '2026-07-01T10:00:00Z',
  },
]

const mockCaseDetail = {
  ...mockCaseList[0],
  documents: [],
  completeness_report: [],
}

const DEV_NURSE_ID = '00000000-0000-0000-0000-000000000001'

describe('NurseReviewWorkspace', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
    jest.clearAllMocks()
  })

  it('renders worklist and loads cases on mount', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => mockCaseList,
    })

    render(<NurseReviewWorkspace />)

    // Should show loading spinner initially, then render cases
    expect(screen.getByRole('heading', { name: 'Nurse Review' })).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('MEM-123')).toBeInTheDocument()
    })
    
    // Check that it calls fetch for the list
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/review/cases')
  })

  it('loads case details when a case is clicked', async () => {
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockCaseList,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockCaseDetail,
      })

    render(<NurseReviewWorkspace />)

    await waitFor(() => {
      expect(screen.getByText('MEM-123')).toBeInTheDocument()
    })

    const caseItem = screen.getByText('MEM-123').closest('li')
    if (caseItem) fireEvent.click(caseItem)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/v1/review/cases/case-1')
      expect(screen.getByTestId('mock-document-viewer')).toBeInTheDocument()
      expect(screen.getByTestId('mock-checklist')).toBeInTheDocument()
    })
  })

  it('allows claiming a case', async () => {
    // 1. Initial list load
    // 2. Case detail load
    // 3. Claim post
    // 4. Case detail reload
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({ ok: true, json: async () => mockCaseList })
      .mockResolvedValueOnce({ ok: true, json: async () => mockCaseDetail })
      .mockResolvedValueOnce({ ok: true }) // POST /claim
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockCaseDetail, claimed_by_id: DEV_NURSE_ID }),
      })

    render(<NurseReviewWorkspace />)

    await waitFor(() => screen.getByText('MEM-123'))
    
    const caseItem = screen.getByText('MEM-123').closest('li')
    if (caseItem) fireEvent.click(caseItem)

    await waitFor(() => screen.getByRole('button', { name: /Claim Case/i }))

    fireEvent.click(screen.getByRole('button', { name: /Claim Case/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        `/api/v1/review/cases/case-1/claim?nurse_id=${DEV_NURSE_ID}`,
        expect.objectContaining({ method: 'POST' })
      )
      // verify the UI updates to show it is claimed by me
      expect(screen.getByText(/You hold the lock/i)).toBeInTheDocument()
    })
  })

  it('submits a decision when holding the claim', async () => {
    const claimedCase = { ...mockCaseDetail, claimed_by_id: DEV_NURSE_ID };
    
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({ ok: true, json: async () => [claimedCase] })
      .mockResolvedValueOnce({ ok: true, json: async () => claimedCase })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) }) // POST /decision
      .mockResolvedValueOnce({ ok: true, json: async () => [] }) // Refresh list after decision

    render(<NurseReviewWorkspace />)

    await waitFor(() => screen.getByText('MEM-123'))
    const caseItem = screen.getByText('MEM-123').closest('li')
    if (caseItem) fireEvent.click(caseItem)

    await waitFor(() => screen.getByRole('button', { name: /Accept/i }))

    fireEvent.click(screen.getByRole('button', { name: /Accept/i }))

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /Accept Case/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Confirm Accept/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/review/cases/case-1/decision',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            nurse_id: DEV_NURSE_ID,
            action: 'Accept',
            reason_code: 'MISSING_CLINICAL_NOTES',
            notes: null
          })
        })
      )
      // Case detail should close, and list should refresh
      expect(screen.queryByTestId('mock-document-viewer')).not.toBeInTheDocument()
    })
  })
})
