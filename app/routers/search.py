from fastapi import APIRouter

from app.services import search_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/zones")
def zones():
    return search_service.get_zones()


@router.get("/stats")
def stats():
    return search_service.get_stats()
