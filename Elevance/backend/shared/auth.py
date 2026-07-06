from enum import Enum
from typing import Dict, Any

class Persona(str, Enum):
    INTAKE_ASSOCIATE = "Intake Associate"
    NURSE_REVIEWER = "Nurse Reviewer"
    MEDICAL_DIRECTOR = "Medical Director"
    PROVIDER_RELATIONS = "Provider Relations"
    OPERATIONS_MANAGER = "Operations Manager"
    AUDITOR = "Auditor"
    QA_TEST_ENGINEER = "QA/Test Engineer"

# Mock users for MVP
MOCK_USERS: Dict[str, Dict[str, Any]] = {
    "token_intake": {"user_id": "u1", "role": Persona.INTAKE_ASSOCIATE},
    "token_nurse": {"user_id": "u2", "role": Persona.NURSE_REVIEWER},
    "token_md": {"user_id": "u3", "role": Persona.MEDICAL_DIRECTOR},
    "token_pr": {"user_id": "u4", "role": Persona.PROVIDER_RELATIONS},
    "token_ops": {"user_id": "u5", "role": Persona.OPERATIONS_MANAGER},
    "token_audit": {"user_id": "u6", "role": Persona.AUDITOR},
    "token_qa": {"user_id": "u7", "role": Persona.QA_TEST_ENGINEER},
}

def get_user_from_token(token: str) -> Dict[str, Any]:
    if token not in MOCK_USERS:
        raise ValueError("Invalid token")
    return MOCK_USERS[token]
