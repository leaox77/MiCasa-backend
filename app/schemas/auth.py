from pydantic import BaseModel, EmailStr, field_validator
from typing import Literal, Optional
from enum import Enum


class PublisherType(str, Enum):
    agente = "agente_independiente"
    inmobiliaria = "inmobiliaria"
    particular = "propietario_particular"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: Literal["buyer", "publisher"] = "buyer"
    phone: Optional[str] = None
    publisher_type: Optional[PublisherType] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v

    @field_validator("full_name")
    @classmethod
    def full_name_not_empty(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        return v.strip()

    @field_validator("publisher_type")
    @classmethod
    def publisher_type_required(cls, v, info) -> Optional[PublisherType]:
        # Se valida en el servicio porque info.data puede no tener 'role' aún
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str

    @field_validator("otp")
    @classmethod
    def otp_format(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("El código debe ser de 6 dígitos numéricos.")
        return v


class ResendOTPRequest(BaseModel):
    phone: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class AuthUserResponse(BaseModel):
    id: str
    email: str
    role: str
    full_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: AuthUserResponse


class RegisterResponse(BaseModel):
    user: AuthUserResponse
    message: str