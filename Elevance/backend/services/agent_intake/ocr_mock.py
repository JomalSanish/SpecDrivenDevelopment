import time
from typing import Dict, Any

def extract_text_from_document(document_id: str, file_path: str) -> str:
    """
    Mocked OCR parsing interface.
    In a real implementation, this would call AWS Textract, GCP Document AI, or similar.
    """
    # Simulate processing time
    time.sleep(0.5)
    
    # Return mock text based on basic rules or document names
    if "clinical" in file_path.lower():
        return "Patient presents with severe back pain. MRI recommended."
    elif "referral" in file_path.lower():
        return "Referral for orthopedic consultation. Diagnosis: M54.5"
    
    return "Generic document content extracted via OCR."

def check_image_quality(file_path: str) -> Dict[str, Any]:
    """
    Mocks an image quality check for uploaded documents.
    """
    return {
        "readable": True,
        "confidence": 0.95,
        "flags": []
    }
