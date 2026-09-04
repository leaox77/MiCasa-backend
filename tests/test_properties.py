from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest  # type: ignore[import-not-found]
from fastapi import HTTPException

from app.dependencies import get_current_user
from app.main import app
from app.schemas.properties import PropertySearchParams
from app.services import property_service, storage_service
from tests.conftest import FakePostgrestQuery


PROPIEDAD_BODY = {
    "title": "Casa amplia en zona norte",
    "description": "Descripción de prueba con suficiente longitud.",
    "price": 100000,
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
    # TODO (pendiente coherencia de schema con Leandro): antes se
    # verificaba response.json()["estado"] == "draft". Sin columna
    # "status" real, ya no hay estado que verificar acá.


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


def test_cambio_estado_deshabilitado_sin_columna_status():
    """TODO (pendiente coherencia de schema con Leandro): este test antes
    verificaba que un comprador no pudiera cambiar el estado de una
    propiedad (403). Como la BD real no tiene columna "status",
    change_property_status quedó deshabilitada por completo (501) para
    cualquier rol, no solo para compradores. Este test verifica ESO —
    hay que reescribirlo de nuevo si se agrega la columna "status"."""
    with pytest.raises(HTTPException) as exc_info:
        property_service.change_property_status()

    assert exc_info.value.status_code == 501


def test_busqueda_con_filtros_combinados_devuelve_solo_coincidencias():
    """TODO (pendiente coherencia de schema con Leandro): el dataset y los
    asserts ya no incluyen "tipo" ni "estado" como filtros (no existen en
    la BD real) — antes había un caso "excluida por estado (no publicada)"
    que ahora SE INCLUIRÍA en los resultados, porque no hay forma de
    filtrar por publicada/borrador. Se ajustó el dataset para reflejar
    solo lo que search_properties puede filtrar hoy: price, zone, bedrooms."""
    dataset = [
        {  # cumple todos los filtros
            "id": "a1", "price": 120000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 200, "is_presale": False, "is_investment": False,
            "created_at": "2026-01-01T00:00:00Z",
            "property_images": [{"url": "https://cdn.example.com/a1.jpg", "order_index": 0}],
        },
        {  # excluida por price_max
            "id": "b1", "price": 180000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 210, "is_presale": False, "is_investment": False,
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por zone
            "id": "c1", "price": 100000, "zone": "Norte", "city": "Santa Cruz de la Sierra",
            "bedrooms": 3, "area_m2": 90, "is_presale": False, "is_investment": False,
            "created_at": "2026-01-01T00:00:00Z", "property_images": [],
        },
        {  # excluida por bedrooms
            "id": "d1", "price": 90000, "zone": "Equipetrol", "city": "Santa Cruz de la Sierra",
            "bedrooms": 2, "area_m2": 150, "is_presale": False, "is_investment": False,
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