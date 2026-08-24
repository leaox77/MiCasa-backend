from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    whatsapp_number: Optional[str] = None
    website_url: Optional[str] = None
    company_name: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: str
    role: str
    phone: Optional[str] = None
    phone_verified: bool
    publisher_type: Optional[str] = None
    company_name: Optional[str] = None
    bio: Optional[str] = None
    whatsapp_number: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PublicProfileResponse(BaseModel):
    id: str
    full_name: str
    publisher_type: str
    company_name: Optional[str] = None
    bio: Optional[str] = None
    whatsapp_number: Optional[str] = None
    properties_count: int = 0