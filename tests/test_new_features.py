from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException

from app.core.rate_limit import reset_rate_limits
from app.core.sanitize import strip_html
from app.schemas.properties import PropertyCreate, PropertyStatus, PropertyStatusUpdate, PropertyUpdate
from app.services import expiration_service, property_service, search_service


def _create_body(**overrides):
    body = {
        "title": "Casa de prueba en Equipetrol",
        "description": "Descripción de prueba con más de treinta caracteres.",
        "price": 100000,
        "property_type": "casa",
        "zone": "Equipetrol",
        "bedrooms": 2,
        "bathrooms": 1,
        "area_m2": 100,
        "has_garage": False,
        "age_years": 1,
    }
    body.update(overrides)
    return body


# --- SEC-011: sanitización -------------------------------------------------

def test_strip_html_removes_tags_and_scripts():
    assert strip_html("<b>Hola</b> <script>alert(1)</script>mundo") == "Hola mundo"


def test_property_title_and_description_are_sanitized():
    data = PropertyCreate(**_create_body(
        title="<i>Casa de prueba en Equipetrol</i>",
        description="<script>x()</script>Descripción de prueba con más de treinta caracteres.",
    ))
    assert data.title == "Casa de prueba en Equipetrol"
    assert "<" not in data.description


def test_description_shorter_than_30_chars_is_rejected():
    with pytest.raises(ValueError):
        PropertyCreate(**_create_body(description="Muy corta"))


def test_title_longer_than_120_chars_is_rejected():
    with pytest.raises(ValueError):
        PropertyCreate(**_create_body(title="x" * 121))


# --- SEC-017: headers de seguridad -----------------------------------------

def test_security_headers_are_present(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


# --- SEC-003: rate limiting -------------------------------------------------

def test_login_is_rate_limited_after_10_requests(client):
    reset_rate_limits()
    fake_admin = MagicMock()
    with patch("app.services.auth_service.get_supabase_admin", return_value=fake_admin), \
         patch("app.services.auth_service.create_client") as fake_client:
        fake_client.return_value.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")
        codes = [
            client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "incorrecta"}).status_code
            for _ in range(11)
        ]
    reset_rate_limits()
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


# --- RN-014/015: foto obligatoria para enviar a revisión ---------------------

def test_submit_without_photo_is_rejected():
    property_row = {"id": "p1", "publisher_id": "pub-1", "status": "draft", "title": "Casa de prueba"}
    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=property_row)
    )
    fake_admin.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
        with pytest.raises(HTTPException) as exc:
            property_service.change_property_status(
                "p1", {"id": "pub-1", "role": "publisher"},
                PropertyStatusUpdate(new_status=PropertyStatus.pending_review),
            )
    assert exc.value.status_code == 400
    assert "foto" in exc.value.detail.lower()


# --- RN-020: eliminación suave por el publicador ------------------------------

@pytest.mark.parametrize("current", ["draft", "published", "paused", "expired", "rejected"])
def test_publisher_can_soft_delete_from_allowed_states(current):
    row = {"id": "p1", "publisher_id": "pub-1", "status": current, "title": "Casa de prueba"}
    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=row)
    )
    fake_admin.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{**row, "status": "deleted"}]
    )
    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin), \
         patch("app.services.property_service.notify_favorites_status_change"):
        result = property_service.change_property_status(
            "p1", {"id": "pub-1", "role": "publisher"}, PropertyStatusUpdate(new_status=PropertyStatus.deleted)
        )
    assert result["status"] == "deleted"


# --- RN-021: reedición de una propiedad publicada vuelve a revisión -----------

def test_editing_price_of_published_property_sends_it_back_to_review():
    row = {
        "id": "p1", "publisher_id": "pub-1", "status": "published", "price": 100000,
        "title": "Casa de prueba", "currency": "USD", "type": "casa",
    }
    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=dict(row))
    )
    fake_admin.table.return_value.update.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{**row, "price": 90000}]),
        SimpleNamespace(data=[{**row, "price": 90000, "status": "pending_review"}]),
    ]
    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin), \
         patch("app.services.property_service.notify_admin_new_property_pending") as notify_admin, \
         patch("app.services.property_service.notify_favorite_price_change"):
        result = property_service.update_property("p1", "pub-1", PropertyUpdate(price=90000))
    assert result["status"] == "pending_review"
    notify_admin.assert_called_once()


# --- RN-011/012: job de expiración ---------------------------------------------

def test_expiration_job_expires_and_warns_once():
    now = datetime.now(timezone.utc)
    expired = [{"id": "e1", "title": "Vencida", "publisher_id": "u1"}]
    soon = [{
        "id": "s1", "title": "Por vencer", "publisher_id": "u2",
        "published_at": (now - timedelta(days=51)).isoformat(), "renewed_at": None,
    }]

    class Chain:
        """Devuelve el resultado que corresponde según la tabla y el filtro usado."""
        def __init__(self, table):
            self.table, self.lt_used, self.gte_used = table, False, False

        def __getattr__(self, name):
            def call(*args, **kwargs):
                if name == "lt":
                    self.lt_used = True
                if name == "gte" and args and args[0] == "expires_at":
                    self.gte_used = True
                return self
            return call

        def execute(self):
            if self.table == "properties" and self.lt_used:
                return SimpleNamespace(data=expired)
            if self.table == "properties" and self.gte_used:
                return SimpleNamespace(data=soon)
            return SimpleNamespace(data=[])

    fake_admin = MagicMock()
    fake_admin.table.side_effect = lambda name: Chain(name)

    with patch("app.services.expiration_service.get_supabase_admin", return_value=fake_admin), \
         patch("app.services.expiration_service._get_user_email", return_value="x@example.com"), \
         patch("app.services.expiration_service.notify_publisher_property_expired") as n_expired, \
         patch("app.services.expiration_service.notify_publisher_property_expiring_soon") as n_soon, \
         patch("app.services.expiration_service.notify_favorites_status_change") as n_fav:
        result = expiration_service.run_daily_job()

    assert result["expired"] == 1 and result["warned"] == 1
    n_expired.assert_called_once()
    n_soon.assert_called_once()
    n_fav.assert_called_once()


# --- Búsqueda: zonas y estadísticas ---------------------------------------------

def test_zones_are_counted_and_sorted():
    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{"zone": "Urubó"}, {"zone": "Equipetrol"}, {"zone": "Equipetrol"}]
    )
    with patch("app.services.search_service.get_supabase_admin", return_value=fake_admin):
        assert search_service.get_zones() == [
            {"zone": "Equipetrol", "count": 2},
            {"zone": "Urubó", "count": 1},
        ]
