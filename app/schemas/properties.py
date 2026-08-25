from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums (deben coincidir exactamente con los ENUM creados en Supabase - Bloque 1)
# ---------------------------------------------------------------------------

class PropertyType(str, Enum):
    casa = "casa"
    departamento = "departamento"
    terreno = "terreno"
    local = "local"
    oficina = "oficina"


class PropertyStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    paused = "paused"
    expired = "expired"
    deleted = "deleted"
    rejected = "rejected"


class Currency(str, Enum):
    BOB = "BOB"
    USD = "USD"


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
    tipo: PropertyType
    titulo: str
    descripcion: str
    precio: Decimal
    moneda: Currency
    zona: str
    direccion: str
    habitaciones: int = Field(ge=0)
    banos: int = Field(ge=0)
    m2: float
    garaje: bool
    antiguedad: int = Field(ge=0)
    es_preventa: bool = False
    ideal_inversion: bool = False
    rentabilidad_estimada: Optional[float] = None
    whatsapp_contacto: Optional[str] = None

    @field_validator("titulo")
    @classmethod
    def titulo_length(cls, v: str) -> str:
        v = v.strip()
        if not (10 <= len(v) <= 100):
            raise ValueError("El título debe tener entre 10 y 100 caracteres.")
        return v

    @field_validator("precio")
    @classmethod
    def precio_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("El precio debe ser mayor a 0.")
        return v

    @field_validator("m2")
    @classmethod
    def m2_positivo(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Los m2 deben ser mayores a 0.")
        return v

    @model_validator(mode="after")
    def rentabilidad_coherente(self) -> "PropertyCreate":
        if (
            (self.es_preventa or self.ideal_inversion)
            and self.rentabilidad_estimada is not None
            and self.rentabilidad_estimada < 0
        ):
            raise ValueError(
                "Si la propiedad es preventa o ideal para inversión, "
                "la rentabilidad estimada no puede ser negativa."
            )
        return self


class PropertyUpdate(BaseModel):
    tipo: Optional[PropertyType] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[Decimal] = None
    moneda: Optional[Currency] = None
    zona: Optional[str] = None
    direccion: Optional[str] = None
    habitaciones: Optional[int] = Field(default=None, ge=0)
    banos: Optional[int] = Field(default=None, ge=0)
    m2: Optional[float] = None
    garaje: Optional[bool] = None
    antiguedad: Optional[int] = Field(default=None, ge=0)
    es_preventa: Optional[bool] = None
    ideal_inversion: Optional[bool] = None
    rentabilidad_estimada: Optional[float] = None
    whatsapp_contacto: Optional[str] = None

    @field_validator("titulo")
    @classmethod
    def titulo_length(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not (10 <= len(v) <= 100):
            raise ValueError("El título debe tener entre 10 y 100 caracteres.")
        return v

    @field_validator("precio")
    @classmethod
    def precio_positivo(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("El precio debe ser mayor a 0.")
        return v

    @field_validator("m2")
    @classmethod
    def m2_positivo(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Los m2 deben ser mayores a 0.")
        return v

    @model_validator(mode="after")
    def rentabilidad_coherente(self) -> "PropertyUpdate":
        # Ojo: esto solo valida coherencia entre campos presentes en ESTE PATCH.
        # Si en un PATCH separado se cambia ideal_inversion sin tocar
        # rentabilidad_estimada, la coherencia contra el valor ya guardado en
        # la fila debe validarse en property_service.py (Bloque 4).
        if (
            (self.es_preventa or self.ideal_inversion)
            and self.rentabilidad_estimada is not None
            and self.rentabilidad_estimada < 0
        ):
            raise ValueError(
                "Si la propiedad es preventa o ideal para inversión, "
                "la rentabilidad estimada no puede ser negativa."
            )
        return self


class PropertyStatusUpdate(BaseModel):
    nuevo_estado: PropertyStatus
    motivo: Optional[str] = None

    @field_validator("motivo")
    @classmethod
    def motivo_limpio(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None


class PropertyImageCreate(BaseModel):
    url: HttpUrl
    order_index: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Salida: respuestas al frontend
# ---------------------------------------------------------------------------

class PropertyResponse(BaseModel):
    id: str
    tipo: PropertyType
    titulo: str
    descripcion: str
    precio: Decimal
    moneda: Currency
    zona: str
    direccion: str
    habitaciones: int
    banos: int
    m2: float
    garaje: bool
    antiguedad: int
    es_preventa: bool
    ideal_inversion: bool
    rentabilidad_estimada: Optional[float] = None
    whatsapp_contacto: Optional[str] = None
    publisher_id: str
    estado: PropertyStatus
    created_at: datetime
    updated_at: datetime
    imagenes: List[PropertyImageResponse] = []
    publisher: Optional[PropertyPublisherInfo] = None


class PropertyListItem(BaseModel):
    id: str
    foto_principal: Optional[HttpUrl] = None
    tipo: PropertyType
    precio: Decimal
    moneda: Currency
    zona: str
    habitaciones: int
    m2: float
    etiquetas: List[str] = []