from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException

from app.dependencies import get_current_user
from app.main import app
from app.schemas.properties import PropertySearchParams, PropertyStatus, PropertyStatusUpdate
from app.services import property_service, storage_service
from tests.conftest import FakePostgrestQuery


PROPIEDAD_BODY = {
    "title": "Casa amplia en zona norte",
    "description": "Descripción de prueba con suficiente longitud.",
    "price": 100000,
    "property_type": "casa",
    "currency": "BOB",
    "zone": "Norte",
    "city": "Santa Cruz de la Sierra",
    "address_private": "Calle Falsa 123",
    "bedrooms": 3,
    "bathrooms": 2,
    "area_m2": 200.0,
    "has_garage": True,
    "age_years": 5,
}


def test_crear_propiedad_publisher_verificado(client):
    publisher = {
        "id": "pub-1",
        "role": "publisher",
        "phone_verified": True,
        "is_active": True,
        "full_name": "Publisher Verificado",
    }
    app.dependency_overrides[get_current_user] = lambda: publisher

    created_row = {
        **PROPIEDAD_BODY,
        "id": "prop-1",
        "publisher_id": "pub-1",
        "status": "draft",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "is_presale": False,
        "is_investment": False,
        "estimated_yield": None,
        "contact_whatsapp": None,
        "view_count": 0,
        "interest_count": 0,
        "published_at": None,
        "expires_at": None,
        "renewed_at": None,
        "rejection_reason": None,
        "latitude": None,
        "longitude": None,
    }

    fake_admin = MagicMock()
    fake_admin.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=[created_row]
    )

    try:
        with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
            response = client.post("/api/v1/properties", json=PROPIEDAD_BODY)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == "prop-1"
    assert response.json()["status"] == "draft"


def test_crear_propiedad_con_submit_queda_pending_review(client):
    """submit=true tiene que insertar con status='pending_review' y avisar
    a los admins — no solo cambiar un flag que no se guarda en ningún lado."""
    publisher = {
        "id": "pub-1",
        "role": "publisher",
        "phone_verified": True,
        "is_active": True,
        "full_name": "Publisher Verificado",
    }
    app.dependency_overrides[get_current_user] = lambda: publisher

    created_row = {
        **PROPIEDAD_BODY,
        "id": "prop-2",
        "publisher_id": "pub-1",
        "status": "pending_review",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "is_presale": False,
        "is_investment": False,
        "estimated_yield": None,
        "contact_whatsapp": None,
        "view_count": 0,
        "interest_count": 0,
        "published_at": None,
        "expires_at": None,
        "renewed_at": None,
        "rejection_reason": None,
        "latitude": None,
        "longitude": None,
    }

    fake_admin = MagicMock()
    fake_admin.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=[created_row]
    )

    try:
        with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin), \
             patch("app.services.property_service.notify_admin_new_property_pending") as mock_notify:
            response = client.post("/api/v1/properties?submit=true", json=PROPIEDAD_BODY)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["status"] == "pending_review"
    mock_notify.assert_called_once()


def test_crear_propiedad_falla_si_no_verificado(client):
    publisher_no_verificado = {
        "id": "pub-2",
        "role": "publisher",
        "phone_verified": False,
        "is_active": True,
        "full_name": "Publisher Sin Verificar",
    }
    app.dependency_overrides[get_current_user] = lambda: publisher_no_verificado

    try:
        response = client.post("/api/v1/properties", json=PROPIEDAD_BODY)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert "verificar tu número de celular" in response.json()["detail"].lower()


def test_falla_subir_foto_16_limite_15():
    class FakeUploadFile:
        def __init__(self, content_type, content):
            self.content_type = content_type
            self.file = __import__("io").BytesIO(content)

    fake_file = FakeUploadFile("image/jpeg", b"contenido-de-prueba")

    with pytest.raises(HTTPException) as exc_info:
        storage_service.upload_property_image(
            property_id="prop-1",
            file=fake_file,
            current_count=15,
        )

    assert exc_info.value.status_code == 400
    assert "máximo" in exc_info.value.detail.lower()


def test_publicador_puede_enviar_borrador_a_revision():
    property_row = {"id": "prop-1", "publisher_id": "pub-1", "status": "draft"}
    updated_row = {**property_row, "status": "pending_review"}

    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=property_row)
    )
    fake_admin.table.return_value.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[updated_row]
    )

    actor = {"id": "pub-1", "role": "publisher"}

    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin), \
         patch("app.services.property_service.notify_admin_new_property_pending") as mock_notify:
        result = property_service.change_property_status(
            "prop-1", actor, PropertyStatusUpdate(new_status=PropertyStatus.pending_review)
        )

    assert result["status"] == "pending_review"
    mock_notify.assert_called_once()


def test_publicador_no_puede_saltar_directo_a_publicado():
    """draft -> published no es una transición válida para el publisher —
    tiene que pasar por pending_review y ser aprobada por un admin."""
    property_row = {"id": "prop-1", "publisher_id": "pub-1", "status": "draft"}

    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=property_row)
    )

    actor = {"id": "pub-1", "role": "publisher"}

    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
        with pytest.raises(HTTPException) as exc_info:
            property_service.change_property_status(
                "prop-1", actor, PropertyStatusUpdate(new_status=PropertyStatus.published)
            )

    assert exc_info.value.status_code == 400


def test_otro_publicador_no_puede_cambiar_estado_de_propiedad_ajena():
    property_row = {"id": "prop-1", "publisher_id": "pub-1", "status": "draft"}

    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=property_row)
    )

    actor = {"id": "pub-intruso", "role": "publisher"}

    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
        with pytest.raises(HTTPException) as exc_info:
            property_service.change_property_status(
                "prop-1", actor, PropertyStatusUpdate(new_status=PropertyStatus.pending_review)
            )

    assert exc_info.value.status_code == 403


def test_busqueda_con_filtros_combinados_devuelve_solo_coincidencias():
    dataset = [
        {  # cumple todos los filtros
            "id": "a1", "price": 120000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 200, "is_presale": False, "is_investment": False,
            "status": "published", "property_type": "casa", "currency": "BOB",
            "created_at": "2026-01-01T00:00:00Z",
            "property_images": [{"url": "https://cdn.example.com/a1.jpg", "order_index": 0}],
        },
        {  # excluida por price_max
            "id": "b1", "price": 180000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 210, "is_presale": False, "is_investment": False,
            "status": "published", "property_type": "casa", "currency": "BOB",
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por zone
            "id": "c1", "price": 100000, "zone": "Norte", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 90, "is_presale": False, "is_investment": False,
            "status": "published", "property_type": "casa", "currency": "BOB",
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por bedrooms
            "id": "d1", "price": 90000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 2, "area_m2": 150, "is_presale": False, "is_investment": False,
            "status": "published", "property_type": "casa", "currency": "BOB",
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por status (no publicada), pese a cumplir el resto
            "id": "e1", "price": 130000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 180, "is_presale": False, "is_investment": False,
            "status": "draft", "property_type": "casa", "currency": "BOB",
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
    ]

    fake_admin = MagicMock()
    fake_admin.table.return_value = FakePostgrestQuery(dataset)

    params = PropertySearchParams(
        price_max=150000,
        bedrooms=3,
        zone="equipetrol",
    )

    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
        response = property_service.search_properties(params)

    assert response.total == 1
    assert len(response.results) == 1
    assert response.results[0].id == "a1"