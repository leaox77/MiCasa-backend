from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    is_read: bool
    related_property_id: Optional[str] = None
    created_at: datetime


class NotificationsListResponse(BaseModel):
    data: List[NotificationResponse]
    unread_count: int