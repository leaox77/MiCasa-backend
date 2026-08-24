from fastapi import APIRouter, Depends
from app.schemas.users import ProfileUpdate, ProfileResponse, PublicProfileResponse
from app.services import user_service
from app.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=ProfileResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return user_service.get_profile(current_user["id"])


@router.patch("/me", response_model=ProfileResponse)
def update_me(data: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    return user_service.update_profile(current_user["id"], data)


@router.get("/{publisher_id}/profile", response_model=PublicProfileResponse)
def get_public_profile(publisher_id: str):
    return user_service.get_public_profile(publisher_id)