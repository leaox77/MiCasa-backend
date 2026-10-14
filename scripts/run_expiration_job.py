"""Corre el job diario de expiración (RN-011/012) fuera de la API.

Pensado para un programador de tareas (cron en Linux, Programador de tareas de
Windows, GitHub Actions, etc.), una vez al día:

    python scripts/run_expiration_job.py

Usa las credenciales del .env, igual que la API. También se puede lanzar a
mano desde la API con POST /api/v1/admin/jobs/expiration (token de admin)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.expiration_service import run_daily_job  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(run_daily_job(), ensure_ascii=False))
