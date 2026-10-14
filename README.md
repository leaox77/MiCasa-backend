# Mi Casa — Backend

API del marketplace inmobiliario Mi Casa (Santa Cruz de la Sierra). FastAPI + Pydantic v2 sobre Supabase (Postgres, Auth y Storage), con Twilio (SMS) y Resend (email).

- Contrato para el frontend: [`API_CONTRACT.md`](API_CONTRACT.md)
- Pruebas manuales para el cliente: `../lista de pruebas.txt`
- Reglas de negocio, estados y seguridad: documentos del proyecto (`../MiCasa_*.pdf`, `../files/`)

## Puesta en marcha (PowerShell)

```powershell
python -m venv venv                  # solo la primera vez
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env          # y completar los valores
uvicorn app.main:app --reload
```

La API queda en `http://localhost:8000` (Swagger en `/docs`, desactivado con `APP_ENV=production`). `GET /health` comprueba que está viva.

## Variables de entorno

Los nombres están en `.env.example`. Nunca subas el `.env`. La `SUPABASE_SERVICE_ROLE_KEY` solo vive en el backend.

| Variable | Uso |
|----------|-----|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` | Conexión a Supabase |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` | SMS del código de verificación |
| `RESEND_API_KEY`, `EMAIL_FROM` | Emails transaccionales |
| `APP_ENV`, `FRONTEND_URL`, `ALLOWED_ORIGINS` | Entorno y CORS (orígenes separados por comas) |
| `REVIEW_ON_EDIT` | `true` (por defecto): editar título, descripción o precio de una propiedad publicada la devuelve a revisión (RN-021) |

## Pruebas y calidad

```powershell
python -m pytest -q          # pruebas unitarias (no necesitan .env ni Supabase)
ruff check . --exclude venv  # lint
```

## Job diario de expiración

Cada día hay que correr el job que expira las propiedades vencidas (60 días) y avisa a los publicadores a los 50 días. Es idempotente: se puede correr varias veces sin duplicar avisos.

```powershell
python scripts/run_expiration_job.py
```

Prográmalo una vez al día en el servidor (cron, Programador de tareas de Windows o similar). También se puede lanzar a mano con `POST /api/v1/admin/jobs/expiration` usando un token de admin.

## Estructura

```
app/
  main.py          # app, CORS, headers de seguridad, routers bajo /api/v1
  core/            # config, cliente Supabase, JWT, rate limit, sanitización
  routers/         # capa HTTP
  services/        # lógica de negocio y consultas a Supabase
  schemas/         # modelos Pydantic (validación)
scripts/           # seed de propiedades y job de expiración
supabase/migrations/   # migraciones SQL
tests/             # pytest
```

## Convenciones

- Código y base de datos en inglés; mensajes al usuario y documentación en español.
- Las consultas usan la service role (no pasa por RLS), así que cada endpoint valida el rol y el dueño en Python.
- Los cambios en la base de datos se entregan como SQL para ejecutarlos en el SQL Editor de Supabase.
