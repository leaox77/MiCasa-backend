from fastapi import APIRouter, Depends, status
from app.dependencies import get_current_user
from app.services import favorites_service

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.get("")
def list_favorites(current_user: dict = Depends(get_current_user)):
    return favorites_service.list_favorites(current_user["id"])


@router.post("/{property_id}", status_code=status.HTTP_201_CREATED)
def add_favorite(property_id: str, current_user: dict = Depends(get_current_user)):
    return favorites_service.add_favorite(current_user["id"], property_id)


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(property_id: str, current_user: dict = Depends(get_current_user)):
    favorites_service.remove_favorite(current_user["id"], property_id)