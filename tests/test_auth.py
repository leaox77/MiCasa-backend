from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_registro_exitoso_comprador(client):
    fake_admin = MagicMock()
    fake_admin.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-buyer-1")
    )
    fake_admin.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{}])
    )

    with patch("app.services.auth_service.get_supabase_admin", return_value=fake_admin):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "comprador@example.com",
                "password": "password123",
                "full_name": "Juan Pérez",
                "role": "buyer",
                "terms_accepted": True,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "comprador@example.com"
    assert body["user"]["role"] == "buyer"
    fake_admin.auth.admin.create_user.assert_called_once()


def test_registro_exitoso_publisher_con_publisher_type(client):
    fake_admin = MagicMock()
    fake_admin.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-publisher-1")
    )
    fake_admin.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{}])
    )

    with patch("app.services.auth_service.get_supabase_admin", return_value=fake_admin):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "publisher@example.com",
                "password": "password123",
                "full_name": "María Gómez",
                "role": "publisher",
                "publisher_type": "agente_independiente",
                "phone": "+59170000000",
                "terms_accepted": True,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == "publisher"


def test_registro_falla_sin_terms_accepted(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "sinterminos@example.com",
            "password": "password123",
            "full_name": "Sin Terminos",
            "role": "buyer",
            "terms_accepted": False,
        },
    )

    # Se rechaza en la validación de Pydantic (RegisterRequest), antes de
    # llegar al service — por eso no hace falta mockear Supabase acá.
    assert response.status_code == 422


def test_login_falla_email_no_verificado(client):
    fake_admin = MagicMock()
    fake_admin.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-no-verificado",
            email="noverificado@example.com",
            email_confirmed_at=None,
        ),
        session=SimpleNamespace(access_token="fake-token"),
    )

    with patch("app.services.auth_service.get_supabase_admin", return_value=fake_admin):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "noverificado@example.com", "password": "password123"},
        )

    assert response.status_code == 403
    assert "verificar tu email" in response.json()["detail"].lower()


def test_login_falla_credenciales_incorrectas(client):
    fake_admin = MagicMock()
    fake_admin.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    with patch("app.services.auth_service.get_supabase_admin", return_value=fake_admin):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "cualquiera@example.com", "password": "incorrecta"},
        )

    assert response.status_code == 401
    # Mensaje genérico: no debe distinguir si falló el email o la contraseña
    assert response.json()["detail"] == "Credenciales incorrectas."