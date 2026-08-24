from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str

    resend_api_key: str
    email_from: str = "noreply@micasa.bo"

    app_env: str = "development"
    frontend_url: str = "http://localhost:5173"
    allowed_origins: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()