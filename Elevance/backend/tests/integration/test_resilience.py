import pytest
from fastapi.testclient import TestClient
from services.orchestration_api.main import app
from unittest.mock import patch
from sqlalchemy.exc import OperationalError

client = TestClient(app)

def test_corrupted_pdf_upload():
    # Simulate uploading a corrupt PDF
    response = client.post(
        "/cases/case-123/documents",
        files={"file": ("corrupt_file.pdf", b"dummy content", "application/pdf")}
    )
    assert response.status_code == 422
    assert "corrupted or unreadable" in response.json()["detail"]

def test_large_pdf_upload():
    response = client.post(
        "/cases/case-123/documents?page_count=1001",
        files={"file": ("large_file.pdf", b"dummy content", "application/pdf")}
    )
    assert response.status_code == 413
    assert "exceeds 1000 page limit" in response.json()["detail"]

@patch("services.agent_rag.search.hybrid_search", return_value=[])
def test_missing_medical_policy(mock_search):
    # Call evidence endpoint
    response = client.get("/cases/case-123/evidence")
    assert response.status_code == 200
    data = response.json()
    assert len(data["evidence_items"]) == 1
    assert data["evidence_items"][0]["matched_text"] == "Insufficient Evidence"

@patch("services.orchestration_api.routers.cases.Session.commit")
def test_database_unavailability(mock_commit):
    mock_commit.side_effect = OperationalError("statement", "params", "orig")
    
    response = client.post(
        "/cases",
        json={
            "member_id": "m1",
            "provider_id": "p1",
            "request_type": "Advanced Imaging"
        }
    )
    assert response.status_code == 503
    assert "Database is temporarily unavailable" in response.json()["detail"]
