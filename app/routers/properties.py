from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ValidationError

from app.dependencies import get_current_user, get_current_user_optional, require_verified_publisher
from app.schemas.properties import (
    OrderBy,
    PropertyCreate,
    PropertyImageResponse,
    PropertyResponse,
    PropertySearchParams,
    PropertySearchResponse,
    PropertyUpdate,
)
from app.services import property_service

router = APIRouter(prefix="/properties", tags=["Properties"])


class ImageReorderRequest(BaseModel):
    """Wrapper del body de PATCH /images/reorder. No es un schema de
    dominio, por eso no está en app/schemas/properties.py."""
    image_ids: list[str]


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
def create_property(
    data: PropertyCreate,
    submit: bool = Query(
        False,
        description="Si es true, envía la propiedad directo a revisión en vez de guardarla como borrador.",
    ),
    current_user: dict = Depends(require_verified_publisher),
):
    return property_service.create_property(current_user["id"], data, submit=submit)


@router.get("", response_model=PropertySearchResponse)
def search_properties(
    price_min: Decimal | None = Query(None, ge=0),
    price_max: Decimal | None = Query(None, ge=0),
    zone: str | None = Query(None),
    city: str | None = Query(None),
    bedrooms: int | None = Query(None, ge=0),
    area_m2_min: float | None = Query(None, ge=0),
    area_m2_max: float | None = Query(None, ge=0),
    has_garage: bool | None = Query(None),
    age_years: int | None = Query(None, ge=0),
    is_presale: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order: OrderBy = Query(OrderBy.recent),
):
    try:
        params = PropertySearchParams(
            price_min=price_min,
            price_max=price_max,
            zone=zone,
            city=city,
            bedrooms=bedrooms,
            area_m2_min=area_m2_min,
            area_m2_max=area_m2_max,
            has_garage=has_garage,
            age_years=age_years,
            is_presale=is_presale,
            page=page,
            page_size=page_size,
            order=order,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.errors())

    return property_service.search_properties(params)

@router.get("/{property_id}", response_model=PropertyResponse)
def get_property(
    property_id: str,
    current_user: dict | None = Depends(get_current_user_optional),
):
    return property_service.get_property(property_id, current_user)


@router.patch("/{property_id}", response_model=PropertyResponse)
def update_property(
    property_id: str,
    data: PropertyUpdate,
    current_user: dict = Depends(get_current_user),
):
    return property_service.update_property(property_id, current_user["id"], data)


@router.patch("/{property_id}/status", response_model=PropertyResponse)
def change_property_status(
    property_id: str,
    current_user: dict = Depends(get_current_user),
):
    # TODO (pendiente coherencia de schema con Leandro): endpoint
    # deshabilitado — property_service.change_property_status ahora
    # devuelve 501 porque no hay columna "status" en la BD real.
    # Se saca el body PropertyStatusUpdate porque ese schema ya no existe.
    return property_service.change_property_status()


@router.post(
    "/{property_id}/images",
    response_model=PropertyImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_property_image(
    property_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_verified_publisher),
):
    return property_service.add_property_image(property_id, current_user["id"], file)


@router.delete("/{property_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property_image(
    property_id: str,
    image_id: str,
    current_user: dict = Depends(require_verified_publisher),
):
    property_service.remove_property_image(property_id, current_user["id"], image_id)


@router.patch("/{property_id}/images/reorder")
def reorder_property_images(
    property_id: str,
    data: ImageReorderRequest,
    current_user: dict = Depends(require_verified_publisher),
):
    property_service.reorder_property_images(property_id, current_user["id"], data.image_ids)
    return {"message": "Orden de fotos actualizado."}