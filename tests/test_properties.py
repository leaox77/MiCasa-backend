from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException

from app.dependencies import get_current_user
from app.main import app
from app.schemas.properties import PropertySearchParams, PropertyStatus, PropertyType
from app.services import property_service, storage_service
from tests.conftest import FakePostgrestQuery


PROPIEDAD_BODY = {
    "tipo": "casa",
    "titulo": "Casa amplia en zona norte",
    "descripcion": "Descripción de prueba con suficiente longitud.",
    "precio": 100000,
    "moneda": "USD",
    "zona": "Norte",
    "direccion": "Calle Falsa 123",
    "habitaciones": 3,
    "banos": 2,
    "m2": 200.0,
    "garaje": True,
    "antiguedad": 5,
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
        "estado": "draft",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "es_preventa": False,
        "ideal_inversion": False,
        "rentabilidad_estimada": None,
        "whatsapp_contacto": None,
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
    assert response.json()["estado"] == "draft"


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
            current_count=15,  # ya tiene el máximo permitido
        )

    assert exc_info.value.status_code == 400
    assert "máximo" in exc_info.value.detail.lower()


def test_cambio_estado_rol_incorrecto_rechazado():
    existing_property = {
        "id": "prop-1",
        "publisher_id": "pub-1",
        "estado": "pending_review",
        "titulo": "Casa de prueba",
        "precio": 100000,
        "moneda": "USD",
    }

    fake_admin = MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=existing_property)
    )

    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
        with pytest.raises(HTTPException) as exc_info:
            property_service.change_property_status(
                property_id="prop-1",
                actor={"id": "comprador-1", "role": "buyer"},
                new_status=PropertyStatus.published,
                reason=None,
            )

    assert exc_info.value.status_code == 403


def test_busqueda_con_filtros_combinados_devuelve_solo_coincidencias():
    dataset = [
        {  # cumple todos los filtros
            "id": "a1", "tipo": "casa", "precio": 120000, "moneda": "USD",
            "zona": "Equipetrol", "habitaciones": 3, "m2": 200, "estado": "published",
            "es_preventa": False, "ideal_inversion": False,
            "created_at": "2026-01-01T00:00:00Z",
            "property_images": [{"url": "https://cdn.example.com/a1.jpg", "order_index": 0}],
        },
        {  # excluida por precio_max
            "id": "b1", "tipo": "casa", "precio": 180000, "moneda": "USD",
            "zona": "Equipetrol", "habitaciones": 3, "m2": 210, "estado": "published",
            "es_preventa": False, "ideal_inversion": False,
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por tipo
            "id": "c1", "tipo": "departamento", "precio": 100000, "moneda": "USD",
            "zona": "Equipetrol", "habitaciones": 3, "m2": 90, "estado": "published",
            "es_preventa": False, "ideal_inversion": False,
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por habitaciones
            "id": "d1", "tipo": "casa", "precio": 90000, "moneda": "USD",
            "zona": "Norte", "habitaciones": 2, "m2": 150, "estado": "published",
            "es_preventa": False, "ideal_inversion": False,
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por estado (no publicada)
            "id": "e1", "tipo": "casa", "precio": 110000, "moneda": "USD",
            "zona": "Equipetrol", "habitaciones": 3, "m2": 180, "estado": "draft",
            "es_preventa": False, "ideal_inversion": False,
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
    ]

    fake_admin = MagicMock()
    fake_admin.table.return_value = FakePostgrestQuery(dataset)

    params = PropertySearchParams(
        tipo=PropertyType.casa,
        precio_max=150000,
        habitaciones=3,
        zona="equipetrol",
    )

    with patch("app.services.property_service.get_supabase_admin", return_value=fake_admin):
        response = property_service.search_properties(params)

    assert response.total == 1
    assert len(response.results) == 1
    assert response.results[0].id == "a1"