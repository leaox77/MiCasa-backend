from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from typing import Optional
from app.dependencies import get_current_user
from app.core.supabase import get_supabase_admin
from fastapi import HTTPException

router = APIRouter(prefix="/reports", tags=["Reports"])


class ReportRequest(BaseModel):
    reason: str
    description: Optional[str] = None


VALID_REASONS = {"fraude", "informacion_falsa", "contenido_inapropiado", "duplicado", "otro"}


@router.post("/properties/{property_id}", status_code=status.HTTP_201_CREATED)
def report_property(
    property_id: str,
    data: ReportRequest,
    current_user: dict = Depends(get_current_user),
):
    if data.reason not in VALID_REASONS:
        raise HTTPException(status_code=422, detail=f"Motivo inválido. Opciones: {', '.join(VALID_REASONS)}")

    admin = get_supabase_admin()

    prop = admin.table("properties").select("id").eq("id", property_id).maybe_single().execute()
    if not prop.data:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.")

    existing = (
        admin.table("reports")
        .select("id")
        .eq("property_id", property_id)
        .eq("reporter_id", current_user["id"])
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="Ya denunciaste esta propiedad.")

    result = admin.table("reports").insert({
        "property_id": property_id,
        "reporter_id": current_user["id"],
        "reason": data.reason,
        "description": data.description,
    }).execute()

    return {"id": result.data[0]["id"], "message": "Denuncia recibida. El equipo la revisará a la brevedad."}