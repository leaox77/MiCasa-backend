from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin


def decode_jwt(token: str) -> dict:
    """Valida un JWT de Supabase Auth y devuelve los datos del usuario."""
    try:
        admin = get_supabase_admin()

        response = admin.auth.get_user(token)

        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido o expirado.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = response.user

        return {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "user_metadata": user.user_metadata,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )