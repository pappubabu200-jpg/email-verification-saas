from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from backend.app.utils.security import get_current_user
from backend.app.services.verification_engine import verify_email_sync

router = APIRouter(prefix="/v1/verify", tags=["Verification"])

class VerifyIn(BaseModel):
    email: EmailStr

@router.post("/single")
def single_verify(payload: VerifyIn, current_user = Depends(get_current_user)):
    result = verify_email_sync(payload.email, user_id=getattr(current_user, "id", None))
    return result
