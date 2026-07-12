/**
 * frontend/src/components/DocumentViewer.tsx
 *
 * T026 — In-app PDF Document Viewer for the Nurse Review Workspace.
 *
 * Uses the browser's native PDF renderer (via <iframe>) — zero external
 * dependency.  Documents are loaded from MinIO via their storage_path key;
 * in production the backend provides a presigned URL.  Here the component
 * accepts a direct URL prop for flexibility.
 *
 * Features:
 *   - Zoom controls (50% – 200%)
 *   - Page navigation (via URL fragment #page=N)
 *   - Highlight indicator when a citation chunk is active
 *   - Loading / error states
 */

import { useState, useCallback, useEffect, FC, CSSProperties } from 'react'
import './DocumentViewer.css'

export interface DocumentMeta {
  id: string
  document_type: string
  storage_path: string
  uploaded_at: string
  /** Pre-signed or direct URL to fetch the document bytes */
  url?: string
}

interface DocumentViewerProps {
  /** List of documents for this case */
  documents: DocumentMeta[]
  /** ID of the document currently navigated to by citation click */
  activeDocumentId?: string
  /** Page to jump to when a citation is activated (1-indexed) */
  activePage?: number
  onDocumentSelect?: (id: string) => void
}

const ZOOM_STEPS = [50, 75, 100, 125, 150, 175, 200]

function buildViewerUrl(doc: DocumentMeta, page: number, zoom: number): string {
  // For MinIO objects we'll use a relative proxy path. The backend should
  // expose GET /api/v1/documents/{id}/stream for presigned proxying.
  // In local dev we hit the MinIO endpoint directly via storage_path.
  const base = doc.url ?? `/api/v1/documents/${doc.id}/stream`
  return `${base}#page=${page}&zoom=${zoom}`
}

const DocumentViewer: FC<DocumentViewerProps> = ({
  documents,
  activeDocumentId,
  activePage = 1,
  onDocumentSelect,
}) => {
  const [selectedId, setSelectedId] = useState<string>(
    activeDocumentId ?? documents[0]?.id ?? ''
  )
  const [zoom, setZoom] = useState<number>(100)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [hasError, setHasError] = useState<boolean>(false)

  // Sync external activeDocumentId prop
  useEffect(() => {
    if (activeDocumentId && activeDocumentId !== selectedId) {
      setSelectedId(activeDocumentId)
      setIsLoading(true)
      setHasError(false)
    }
  }, [activeDocumentId])

  const selectedDoc = documents.find((d) => d.id === selectedId)

  const zoomIn = useCallback(() => {
    setZoom((z) => {
      const next = ZOOM_STEPS.find((s) => s > z)
      return next ?? z
    })
  }, [])

  const zoomOut = useCallback(() => {
    setZoom((z) => {
      const prev = [...ZOOM_STEPS].reverse().find((s) => s < z)
      return prev ?? z
    })
  }, [])

  const handleSelect = (id: string) => {
    setSelectedId(id)
    setIsLoading(true)
    setHasError(false)
    onDocumentSelect?.(id)
  }

  if (documents.length === 0) {
    return (
      <div className="doc-viewer doc-viewer--empty" id="document-viewer">
        <div className="doc-viewer__empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          <p>No documents uploaded for this case.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="doc-viewer" id="document-viewer">
      {/* Document tab bar */}
      <div className="doc-viewer__tabs" role="tablist" aria-label="Case documents">
        {documents.map((doc) => (
          <button
            key={doc.id}
            id={`doc-tab-${doc.id}`}
            role="tab"
            aria-selected={doc.id === selectedId}
            className={`doc-viewer__tab ${doc.id === selectedId ? 'doc-viewer__tab--active' : ''}`}
            onClick={() => handleSelect(doc.id)}
            title={doc.storage_path}
          >
            <span className="doc-viewer__tab-icon">
              {doc.document_type === 'PDF' ? '📄' : doc.document_type === 'Fax' ? '📠' : '🖼'}
            </span>
            <span className="doc-viewer__tab-label">
              {doc.storage_path.split('/').pop() ?? doc.document_type}
            </span>
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className="doc-viewer__toolbar">
        <div className="doc-viewer__doc-info">
          <span className="doc-viewer__doc-badge">{selectedDoc?.document_type}</span>
          <span className="doc-viewer__doc-path">
            {selectedDoc?.storage_path.split('/').pop()}
          </span>
          {activePage > 1 && (
            <span className="doc-viewer__page-indicator">
              → page {activePage}
            </span>
          )}
        </div>
        <div className="doc-viewer__zoom-controls" aria-label="Zoom controls">
          <button
            id="doc-viewer-zoom-out"
            className="doc-viewer__zoom-btn"
            onClick={zoomOut}
            disabled={zoom <= ZOOM_STEPS[0]}
            aria-label="Zoom out"
            title="Zoom out"
          >
            −
          </button>
          <span className="doc-viewer__zoom-label" aria-live="polite">{zoom}%</span>
          <button
            id="doc-viewer-zoom-in"
            className="doc-viewer__zoom-btn"
            onClick={zoomIn}
            disabled={zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}
            aria-label="Zoom in"
            title="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      {/* PDF frame */}
      <div className="doc-viewer__frame-wrap" style={{ '--zoom': zoom / 100 } as CSSProperties}>
        {isLoading && !hasError && (
          <div className="doc-viewer__loading">
            <div className="doc-viewer__spinner" />
            <span>Loading document…</span>
          </div>
        )}
        {hasError && (
          <div className="doc-viewer__error">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <p>Unable to load document.</p>
            <p className="doc-viewer__error-hint">
              Ensure the document is accessible via the configured MinIO endpoint.
            </p>
          </div>
        )}
        {selectedDoc && (
          <iframe
            id={`doc-viewer-iframe-${selectedId}`}
            key={`${selectedId}-p${activePage}`}
            src={buildViewerUrl(selectedDoc, activePage, zoom)}
            title={`Document: ${selectedDoc.storage_path}`}
            className={`doc-viewer__iframe ${isLoading ? 'doc-viewer__iframe--hidden' : ''}`}
            onLoad={() => setIsLoading(false)}
            onError={() => { setIsLoading(false); setHasError(true) }}
            aria-label="PDF document viewer"
          />
        )}
      </div>
    </div>
  )
}

export default DocumentViewer
