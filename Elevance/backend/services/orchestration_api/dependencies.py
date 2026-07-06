from fastapi import Depends, HTTPException, Header
from typing import Optional, List
from shared.auth import get_user_from_token, Persona

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = authorization.replace("Bearer ", "")
    try:
        return get_user_from_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_roles(allowed_roles: List[Persona]):
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden: Insufficient privileges")
        return user
    return role_checker

# Pre-defined dependencies based on security-compliance.md
require_intake = require_roles([Persona.INTAKE_ASSOCIATE])
require_clinical_read = require_roles([Persona.NURSE_REVIEWER, Persona.MEDICAL_DIRECTOR, Persona.AUDITOR])
require_clinical_write = require_roles([Persona.NURSE_REVIEWER, Persona.MEDICAL_DIRECTOR])
require_audit = require_roles([Persona.AUDITOR])
