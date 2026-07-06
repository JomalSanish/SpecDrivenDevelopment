from fastapi import FastAPI
from services.agent_intake.classifier import classify_case

app = FastAPI(
    title="Intake & Classification Agent",
    description="Automates completeness checks and missing document detection."
)

@app.post("/internal/classify/{case_id}")
def classify_endpoint(case_id: str):
    """
    Internal endpoint to trigger classification for a specific case.
    In a real event-driven system, this might consume from a queue.
    """
    result = classify_case(case_id)
    return {"case_id": case_id, "classification": result}

@app.get("/health")
def health_check():
    return {"status": "ok"}
