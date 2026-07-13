import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.storage import get_minio_client, get_bucket_name
from src.models.case import Document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.get("/{document_id}/stream")
async def stream_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream the contents of a document directly from MinIO.
    This bypasses presigned URL hostname resolution issues (minio vs localhost).
    """
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    client = get_minio_client()
    bucket = get_bucket_name()
    
    try:
        # get_object returns a urllib3.response.HTTPResponse
        response = client.get_object(bucket, doc.storage_path)
    except Exception as exc:
        logger.error("MinIO error retrieving %s: %s", doc.storage_path, exc)
        raise HTTPException(status_code=404, detail="Document not found in storage")
        
    def iterfile():
        try:
            for chunk in response.stream(32 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()
            
    content_type = "application/pdf"
    if doc.storage_path.lower().endswith(".txt"):
        content_type = "text/plain"
        
    return StreamingResponse(
        iterfile(),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{doc.storage_path.split("/")[-1]}"'}
    )
