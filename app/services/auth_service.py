from fastapi import HTTPException, status
from supabase import create_client
from app.core.supabase import get_supabase_admin
from app.core.config import get_settings
from app.schemas.auth import RegisterRequest

settings = get_settings()


def register_user(data: RegisterRequest) -> dict:
    """Registra un usuario en Supabase Auth y actualiza su perfil."""
    if not data.terms_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debés aceptar los términos y condiciones para registrarte.",
        )

    # Validar que publicador tiene tipo
    if data.role == "publisher" and not data.publisher_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los publicadores deben indicar su categoría (publisher_type).",
        )

    admin = get_supabase_admin()

    # Crear usuario en Supabase Auth
    try:
        auth_response = admin.auth.admin.create_user({
            "email": data.email,
            "password": data.password,
            "email_confirm": False,
            "user_metadata": {
                "full_name": data.full_name,
                "role": data.role,
            },
            "app_metadata": {}
        })
    except Exception as e:
        error_msg = str(e).lower()
        if "already registered" in error_msg or "already been registered" in error_msg or "already exists" in error_msg or "user already" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este email ya está registrado.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la cuenta. Intentá de nuevo.",
        )

    user_id = auth_response.user.id

    # Actualizar perfil (el trigger ya lo creó con datos básicos)
    update_data: dict = {
        "role": data.role,
        "full_name": data.full_name,
    }

    if data.role == "publisher":
        update_data["publisher_type"] = data.publisher_type.value
        if data.phone:
            update_data["phone"] = data.phone

    admin.table("profiles").update(update_data).eq("id", user_id).execute()

    # Enviar email de verificación
    try:
        admin.auth.admin.generate_link({
            "type": "signup",
            "email": data.email,
        })
    except Exception:
        pass  # No bloquear el registro si el email falla

    return {
        "id": user_id,
        "email": data.email,
        "role": data.role,
        "full_name": data.full_name,
    }


def login_user(email: str, password: str) -> dict:
    """Autentica al usuario y devuelve el JWT."""
    admin = get_supabase_admin()
    # Cliente descartable: sign_in_with_password guarda la sesión del usuario
    # en el cliente, y si fuera el admin cacheado todas las queries siguientes
    # correrían con el JWT del usuario en vez de la service role (RLS).
    auth_client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    try:
        auth_response = auth_client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except Exception as e:
        # Supabase rechaza el login de cuentas sin confirmar antes de devolver la sesión.
        if "email not confirmed" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debés verificar tu email antes de iniciar sesión.",
            )
        # Mensaje genérico — no revelar si el email o la contraseña son incorrectos
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
        )

    user = auth_response.user
    session = auth_response.session

    if not user.email_confirmed_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debés verificar tu email antes de iniciar sesión.",
        )

    # Obtener perfil completo
    profile = admin.table("profiles").select("*").eq("id", user.id).single().execute()

    if not profile.data or not profile.data.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta suspendida. Contactá al soporte.",
        )

    return {
        "access_token": session.access_token,
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": profile.data["role"],
            "full_name": profile.data["full_name"],
        }
    }