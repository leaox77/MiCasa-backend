from fastapi import APIRouter, status, Depends
from app.schemas.auth import (
    RegisterRequest, RegisterResponse,
    LoginRequest, LoginResponse,
    VerifyOTPRequest, ResendOTPRequest,
    ForgotPasswordRequest,
)
from app.services import auth_service
from app.dependencies import get_current_user
from app.core.supabase import get_supabase_admin
from app.core.config import get_settings
from twilio.rest import Client as TwilioClient
from fastapi import HTTPException
import random, string

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest):
    user = auth_service.register_user(data)
    return {
        "user": user,
        "message": "Cuenta creada. Revisá tu email para verificarla.",
    }


@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest):
    return auth_service.login_user(data.email, data.password)


@router.post("/verify-otp")
def verify_otp(
    data: VerifyOTPRequest,
    current_user: dict = Depends(get_current_user),
):
    """Verifica el OTP SMS del celular del publicador."""
    admin = get_supabase_admin()

    # Buscar OTP almacenado
    result = admin.table("otp_attempts").select("*").eq("user_id", current_user["id"]).eq("phone", data.phone).eq("verified", False).order("created_at", desc=True).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=400, detail="Código no encontrado o ya usado.")

    record = result.data[0]

    from datetime import datetime, timezone
    created_at = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    minutes_passed = (now - created_at).total_seconds() / 60

    if minutes_passed > 10:
        raise HTTPException(status_code=400, detail="El código expiró. Solicitá uno nuevo.")

    if record["code"] != data.otp:
        raise HTTPException(status_code=400, detail="Código incorrecto.")

    # Marcar OTP como usado y verificar celular
    admin.table("otp_attempts").update({"verified": True}).eq("id", record["id"]).execute()
    admin.table("profiles").update({"phone_verified": True, "phone": data.phone}).eq("id", current_user["id"]).execute()

    return {"phone_verified": True, "message": "Celular verificado. Ya podés publicar propiedades."}


@router.post("/resend-otp")
def resend_otp(
    data: ResendOTPRequest,
    current_user: dict = Depends(get_current_user),
):
    """Envía un nuevo OTP SMS al celular del publicador."""
    admin = get_supabase_admin()

    # Verificar intentos recientes (máx 3 por hora)
    from datetime import datetime, timezone, timedelta
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent = admin.table("otp_attempts").select("id", count="exact").eq("user_id", current_user["id"]).gte("created_at", one_hour_ago).execute()

    if (recent.count or 0) >= 3:
        raise HTTPException(status_code=429, detail="Límite de reenvíos alcanzado. Esperá 1 hora.")

    # Generar y guardar OTP
    otp_code = "".join(random.choices(string.digits, k=6))
    admin.table("otp_attempts").insert({
        "user_id": current_user["id"],
        "phone": data.phone,
        "code": otp_code,
        "verified": False,
    }).execute()

    # Enviar SMS vía Twilio
    try:
        twilio = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        twilio.messages.create(
            body=f"Tu código de verificación Mi Casa es: {otp_code}. Válido por 10 minutos.",
            from_=settings.twilio_phone_number,
            to=data.phone,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error al enviar el SMS. Intentá de nuevo.")

    return {"message": f"Código enviado a {data.phone}"}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    admin = get_supabase_admin()
    try:
        admin.auth.reset_password_email(data.email)
    except Exception:
        pass  # No revelar si el email existe o no
    return {"message": "Si el email existe en nuestra plataforma, recibirás instrucciones."}


@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    return {"message": "Sesión cerrada."}