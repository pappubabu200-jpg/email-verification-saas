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


from fastapi import Request

@router.post("/single")
def single_verify(payload: VerifyIn, request: Request, current_user = Depends(get_current_user)):
    # If API key used, override user_id
    user_id = getattr(request.state, "api_user_id", current_user.id if current_user else None)

    result = verify_email_sync(payload.email, user_id=user_id)
    return result
