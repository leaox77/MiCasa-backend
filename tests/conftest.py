import os
from types import SimpleNamespace

import pytest

# Variables dummy: alcanza con que existan, nunca se usan de verdad porque
# mockeamos get_supabase_admin() en cada test.
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "dummy-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "dummy-jwt-secret")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "dummy-sid")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "dummy-token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+10000000000")
os.environ.setdefault("RESEND_API_KEY", "dummy-resend-key")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


class FakePostgrestQuery:
    """Simula el builder encadenable de postgrest-py (select/eq/gte/.../execute)
    aplicando los filtros sobre una lista de dicts en memoria, en vez de
    pegarle a una base real. Se usa para probar lógica de filtros de verdad,
    no solo verificar que se llamó a algún método."""

    def __init__(self, rows: list[dict]):
        self._rows = list(rows)
        self._order_field = None
        self._order_desc = False
        self._total = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def gte(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) is not None and float(r[field]) >= float(value)]
        return self

    def lte(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) is not None and float(r[field]) <= float(value)]
        return self

    def ilike(self, field, pattern):
        needle = pattern.strip("%").lower()
        self._rows = [r for r in self._rows if needle in str(r.get(field, "")).lower()]
        return self

    def order(self, field, desc=False):
        self._order_field = field
        self._order_desc = desc
        return self

    def range(self, start, end):
        if self._order_field:
            self._rows = sorted(self._rows, key=lambda r: r.get(self._order_field), reverse=self._order_desc)
        self._total = len(self._rows)
        self._rows = self._rows[start:end + 1]
        return self

    def execute(self):
        total = self._total if self._total is not None else len(self._rows)
        return SimpleNamespace(data=self._rows, count=total)