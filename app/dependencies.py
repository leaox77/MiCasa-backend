from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_jwt
from app.core.supabase import get_supabase_admin

bearer_scheme = HTTPBearer()
bearer_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Extrae y valida el JWT. Devuelve el perfil del usuario."""
    token = credentials.credentials
    payload = decode_jwt(token)
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin usuario.",
        )

    admin = get_supabase_admin()
    result = admin.table("profiles").select("*").eq("id", user_id).single().execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )

    profile = result.data

    if not profile.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta suspendida. Contactá al soporte.",
        )

    return profile


def require_role(*roles: str):
    """Factory que genera una dependencia que exige uno de los roles dados."""
    async def role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        if current_user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Rol requerido: {', '.join(roles)}.",
            )
        return current_user
    return role_checker


def require_verified_publisher(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Exige publicador con celular verificado."""
    if current_user["role"] != "publisher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo publicadores pueden realizar esta acción.",
        )
    if not current_user.get("phone_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debés verificar tu número de celular antes de publicar.",
        )
    return current_user

async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
) -> dict | None:
    """Igual que get_current_user pero no exige login: devuelve None si no
    hay token o si es inválido, en vez de lanzar 401. Para endpoints donde
    el comportamiento cambia si hay usuario pero no es obligatorio (ej.
    GET /properties/{id})."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None