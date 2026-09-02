from fastapi import APIRouter, Depends, status
from app.dependencies import get_current_user
from app.services import interest_service
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/interest", tags=["Interest"])


class InterestRequest(BaseModel):
    message: Optional[str] = None


@router.post("/{property_id}", status_code=status.HTTP_201_CREATED)
def express_interest(
    property_id: str,
    data: InterestRequest,
    current_user: dict = Depends(get_current_user),
):
    return interest_service.express_interest(
        property_id=property_id,
        buyer=current_user,
        message=data.message,
    )


@router.get("/received")
def get_received_interests(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "publisher":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Solo publicadores.")
    return interest_service.get_received_interests(current_user["id"])