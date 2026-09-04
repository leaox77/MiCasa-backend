from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ---------------------------------------------------------------------------
# status/currency/property_type ya existen en la BD real (migración
# 20260903120000_add_status_currency_property_type.sql). Enums abajo.
# ---------------------------------------------------------------------------

class PropertyType(str, Enum):
    casa = "casa"
    departamento = "departamento"
    terreno = "terreno"
    local = "local"
    oficina = "oficina"


class Currency(str, Enum):
    BOB = "BOB"
    USD = "USD"


class PropertyStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    paused = "paused"
    expired = "expired"
    deleted = "deleted"
    rejected = "rejected"


# ---------------------------------------------------------------------------
# Sub-schemas anidados dentro de PropertyResponse
# ---------------------------------------------------------------------------

class PropertyImageResponse(BaseModel):
    id: str
    url: HttpUrl
    order_index: int
    created_at: datetime


class PropertyPublisherInfo(BaseModel):
    id: str
    full_name: str
    publisher_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Entrada: creación y edición
# ---------------------------------------------------------------------------

class PropertyCreate(BaseModel):
    title: str
    description: str
    price: Decimal
    property_type: PropertyType
    currency: Currency = Currency.BOB
    zone: str
    city: Optional[str] = None  # columna real tiene DEFAULT 'Santa Cruz de la Sierra'
    address_private: Optional[str] = None  # solo visible p/ usuarios registrados
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bedrooms: int = Field(ge=0)
    bathrooms: int = Field(ge=0)
    area_m2: float
    has_garage: bool
    age_years: int = Field(ge=0)
    is_presale: bool = False
    is_investment: bool = False
    estimated_yield: Optional[float] = None
    contact_whatsapp: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_length(cls, v: str) -> str:
        v = v.strip()
        if not (10 <= len(v) <= 100):
            raise ValueError("El título debe tener entre 10 y 100 caracteres.")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("El precio debe ser mayor a 0.")
        return v

    @field_validator("area_m2")
    @classmethod
    def area_m2_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Los m2 deben ser mayores a 0.")
        return v

    @model_validator(mode="after")
    def yield_coherente(self) -> "PropertyCreate":
        if (
            (self.is_presale or self.is_investment)
            and self.estimated_yield is not None
            and self.estimated_yield < 0
        ):
            raise ValueError(
                "Si la propiedad es preventa o ideal para inversión, "
                "la rentabilidad estimada no puede ser negativa."
            )
        return self


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    currency: Optional[Currency] = None  # decisión mía: permitir corregir la moneda al editar.
    zone: Optional[str] = None
    city: Optional[str] = None
    address_private: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bedrooms: Optional[int] = Field(default=None, ge=0)
    bathrooms: Optional[int] = Field(default=None, ge=0)
    area_m2: Optional[float] = None
    has_garage: Optional[bool] = None
    age_years: Optional[int] = Field(default=None, ge=0)
    is_presale: Optional[bool] = None
    is_investment: Optional[bool] = None
    estimated_yield: Optional[float] = None
    contact_whatsapp: Optional[str] = None
    # property_type NO es editable: una propiedad no cambia de "casa" a
    # "terreno" a mitad de camino. status tampoco: eso pasa exclusivamente
    # por change_property_status / /admin/approve|reject.

    @field_validator("title")
    @classmethod
    def title_length(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not (10 <= len(v) <= 100):
            raise ValueError("El título debe tener entre 10 y 100 caracteres.")
        return v

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("El precio debe ser mayor a 0.")
        return v

    @field_validator("area_m2")
    @classmethod
    def area_m2_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Los m2 deben ser mayores a 0.")
        return v

    @model_validator(mode="after")
    def yield_coherente(self) -> "PropertyUpdate":
        if (
            (self.is_presale or self.is_investment)
            and self.estimated_yield is not None
            and self.estimated_yield < 0
        ):
            raise ValueError(
                "Si la propiedad es preventa o ideal para inversión, "
                "la rentabilidad estimada no puede ser negativa."
            )
        return self


class PropertyStatusUpdate(BaseModel):
    new_status: PropertyStatus
    rejection_reason: Optional[str] = None

    @model_validator(mode="after")
    def reason_requerido_si_rechaza(self) -> "PropertyStatusUpdate":
        if self.new_status == PropertyStatus.rejected and not (
            self.rejection_reason and self.rejection_reason.strip()
        ):
            raise ValueError("rejection_reason es obligatorio cuando new_status es 'rejected'.")
        return self


class PropertyImageCreate(BaseModel):
    url: HttpUrl
    order_index: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Salida: respuestas al frontend
# ---------------------------------------------------------------------------

class PropertyResponse(BaseModel):
    id: str
    title: str
    description: str
    price: Decimal
    currency: Currency
    property_type: PropertyType
    status: PropertyStatus
    zone: str
    city: str
    address_private: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bedrooms: int
    bathrooms: int
    area_m2: float
    has_garage: bool
    age_years: int
    is_presale: bool
    is_investment: bool
    estimated_yield: Optional[float] = None
    contact_whatsapp: Optional[str] = None
    publisher_id: str
    view_count: int
    interest_count: int
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    renewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    images: List[PropertyImageResponse] = []
    publisher: Optional[PropertyPublisherInfo] = None


class PropertyListItem(BaseModel):
    id: str
    main_photo: Optional[HttpUrl] = None
    price: Decimal
    currency: Currency
    property_type: PropertyType
    zone: str
    city: str
    bedrooms: int
    area_m2: float
    tags: List[str] = []


class OrderBy(str, Enum):
    recent = "recent"
    price_asc = "price_asc"
    price_desc = "price_desc"


class PropertySearchParams(BaseModel):
    price_min: Optional[Decimal] = Field(default=None, ge=0)
    price_max: Optional[Decimal] = Field(default=None, ge=0)
    property_type: Optional[PropertyType] = None
    currency: Optional[Currency] = None
    zone: Optional[str] = None
    city: Optional[str] = None
    bedrooms: Optional[int] = Field(default=None, ge=0)
    area_m2_min: Optional[float] = Field(default=None, ge=0)
    area_m2_max: Optional[float] = Field(default=None, ge=0)
    has_garage: Optional[bool] = None
    age_years: Optional[int] = Field(default=None, ge=0)
    is_presale: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    order: OrderBy = OrderBy.recent

    @model_validator(mode="after")
    def rangos_coherentes(self) -> "PropertySearchParams":
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min no puede ser mayor a price_max.")
        if (
            self.area_m2_min is not None
            and self.area_m2_max is not None
            and self.area_m2_min > self.area_m2_max
        ):
            raise ValueError("area_m2_min no puede ser mayor a area_m2_max.")
        return self


class PropertySearchResponse(BaseModel):
    results: List[PropertyListItem]
    total: int
    page: int
    page_size: int