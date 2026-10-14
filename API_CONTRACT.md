# Contrato de la API — Mi Casa

Documentación para el frontend. Los nombres de campos, parámetros y rutas están en **inglés** (igual que la base de datos). Los mensajes de error y los textos que se muestran al usuario vienen en **español**.

- Base URL local: `http://localhost:8000/api/v1`
- Swagger (solo fuera de producción): `http://localhost:8000/docs`
- Autenticación: cabecera `Authorization: Bearer <access_token>` (el token sale de `POST /auth/login`, dura 1 hora).

## Niveles de acceso

| Nivel | Qué exige |
|-------|-----------|
| Público | Nada |
| Usuario | Token válido de cualquier rol |
| Publicador | Rol `publisher` **y** celular verificado (`phone_verified = true`) |
| Admin | Rol `admin` |

Roles: `buyer` (comprador), `publisher` (publicador), `admin`. Categoría del publicador (`publisher_type`): `agente_independiente`, `inmobiliaria`, `propietario_particular`.

## Errores

Todos los errores tienen la forma `{ "detail": ... }`. `detail` es un texto en español, salvo en los errores de validación (422 y los 400 de búsqueda), donde es una lista `[{ "loc": [...], "msg": "..." }]`. Mostrar `detail` (o `detail[0].msg`) al usuario.

| Código | Cuándo |
|--------|--------|
| 400 | Regla de negocio incumplida o combinación inconsistente (por ejemplo `price_min > price_max`, transición de estado inválida, propiedad sin fotos al enviar a revisión) |
| 401 | Falta el token, es inválido o expiró; credenciales incorrectas |
| 403 | Sin permiso: rol incorrecto, no es el dueño, email sin verificar, cuenta suspendida, celular sin verificar |
| 404 | El recurso no existe (o no es visible para quien consulta) |
| 409 | Duplicado: ya expresaste interés, ya es favorito, ya denunciaste |
| 413 | Foto mayor a 5 MB |
| 422 | Tipo o formato inválido (validación automática) |
| 429 | Demasiadas solicitudes (login, registro y reenvío de OTP: máximo 10 por minuto por IP). Cabecera `Retry-After` |

Todas las respuestas incluyen las cabeceras `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy: strict-origin-when-cross-origin`.

## Estados de una propiedad

`draft` → `pending_review` → `published` ⇄ `paused`; `published` → `expired` (automático a los 60 días) → `published` (renovar); `pending_review` → `rejected` (admin, con motivo) → `pending_review` (corregir y reenviar). Desde `draft`, `published`, `paused`, `expired` y `rejected` se puede pasar a `deleted` (eliminación suave: la fila no se borra).

| Desde | Hacia | Quién | Cómo |
|-------|-------|-------|------|
| draft | pending_review | Publicador | `POST /properties/{id}/submit` (requiere ≥ 1 foto) |
| pending_review | draft | Publicador | `PATCH /properties/{id}/status` |
| pending_review | published / rejected | Admin | `POST /admin/properties/{id}/approve` / `reject` |
| rejected | pending_review | Publicador | `POST /properties/{id}/submit` |
| published | paused | Publicador | `PATCH /properties/{id}/status` |
| paused | published | Publicador | `PATCH /properties/{id}/status` |
| published | expired | Sistema | Job diario (`expires_at` vencido) |
| expired / published | published | Publicador | `POST /properties/{id}/renew` (+60 días, sin revisión) |
| draft / published / paused / expired / rejected | deleted | Publicador o Admin | `DELETE /properties/{id}` |

Si el publicador edita el **título, la descripción o el precio** de una propiedad `published`, vuelve a `pending_review` (RN-021; se desactiva con `REVIEW_ON_EDIT=false`). Un admin puede además pausar/reactivar y eliminar cualquier propiedad por `PATCH /status` y `DELETE`.

---

## Auth

| Método y ruta | Acceso | Descripción |
|---------------|--------|-------------|
| `POST /auth/register` | Público (límite 10/min) | Crea la cuenta. Body: `email`, `password` (≥ 8), `full_name` (≥ 2), `role` (`buyer` o `publisher`), `terms_accepted` (debe ser `true`); si es publicador además `publisher_type` y `phone`. Respuesta 201: `{ "user": { id, email, role, full_name }, "message": "..." }`. 400 si el email ya existe. |
| `POST /auth/login` | Público (límite 10/min) | Body: `email`, `password`. Respuesta 200: `{ access_token, token_type, expires_in, user: { id, email, role, full_name } }`. 401 credenciales incorrectas (mensaje genérico), 403 email sin verificar o cuenta suspendida. |
| `POST /auth/resend-otp` | Usuario (límite 10/min) | Envía un código SMS de 6 dígitos al celular. Máximo 3 por hora (429). |
| `POST /auth/verify-otp` | Usuario | Body: `phone`, `otp`. Marca `phone_verified = true`. El código vence a los 10 minutos. |
| `POST /auth/forgot-password` | Público | Body: `email`. Siempre responde igual, exista o no el email. |
| `POST /auth/logout` | Usuario | Cierra sesión. |

## Perfil

| Método y ruta | Acceso | Descripción |
|---------------|--------|-------------|
| `GET /users/me` | Usuario | Perfil propio. |
| `PATCH /users/me` | Usuario | Actualiza datos del perfil (por ejemplo `full_name`). |
| `GET /users/{publisher_id}/profile` | Público | Perfil público de un publicador. |

## Propiedades

### `GET /properties` — búsqueda pública

Solo devuelve propiedades `published`. Todos los filtros son opcionales y se combinan con AND. Para que la búsqueda sea compartible, el frontend debe reflejar estos parámetros, con estos nombres exactos, en la URL.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `property_type` | `casa`, `departamento`, `terreno`, `local`, `oficina` | Tipo |
| `price_min`, `price_max` | decimal ≥ 0 | Rango de precio |
| `currency` | `BOB`, `USD` | Moneda |
| `zone` | texto | Coincidencia parcial, sin distinguir mayúsculas |
| `city` | texto | Coincidencia parcial |
| `bedrooms` | entero ≥ 0 | Cantidad exacta |
| `area_m2_min`, `area_m2_max` | número ≥ 0 | Superficie |
| `has_garage` | `true`/`false` | Con o sin garaje |
| `age_years` | entero ≥ 0 | Antigüedad **máxima** |
| `is_presale` | `true`/`false` | Preventa |
| `page` | entero ≥ 1 (def. 1) | Página |
| `page_size` | 1 a 50 (def. 20) | Resultados por página |
| `order` | `recent`, `price_asc`, `price_desc` (def. `recent`) | Orden |

Ejemplo: `GET /properties?property_type=casa&price_max=100000&zone=equipetrol&bedrooms=3&order=price_asc&page=1&page_size=20`

Respuesta 200:

```json
{
  "results": [
    {
      "id": "3f2a9e7e-1234-4c1a-9f0a-abc123456789",
      "main_photo": "https://.../property-images/....jpg",
      "price": "185000.0",
      "currency": "USD",
      "property_type": "casa",
      "zone": "Equipetrol",
      "city": "Santa Cruz de la Sierra",
      "bedrooms": 3,
      "area_m2": 280.0,
      "tags": ["presale", "investment"]
    }
  ],
  "total": 47,
  "page": 1,
  "page_size": 20
}
```

`main_photo` es `null` si no hay fotos. `bedrooms` y `area_m2` pueden ser `null` (terrenos). `tags` puede contener `presale` e `investment`. `total` es el total sin paginar (páginas = `ceil(total / page_size)`). Errores: 422 por tipo inválido, 400 por rangos inconsistentes.

### Resto de endpoints

| Método y ruta | Acceso | Descripción |
|---------------|--------|-------------|
| `GET /properties/{id}` | Público (token opcional) | Ficha completa con `images` y `publisher`. `address_private` es `null` sin token. Una propiedad no publicada solo la ve su dueño o un admin (para el resto, 404). |
| `POST /properties` | Publicador | Crea en estado `draft` (201). Campos: `property_type`, `title` (10–120), `description` (≥ 30), `price` (> 0), `currency` (def. `BOB`), `zone`, `bedrooms`, `bathrooms`, `area_m2` (> 0), `has_garage`, `age_years`; opcionales `city`, `address_private`, `latitude`, `longitude`, `is_presale`, `is_investment`, `estimated_yield`, `contact_whatsapp`. El HTML se elimina de los textos. |
| `PATCH /properties/{id}` | Publicador dueño | Edita campos (no `property_type` ni `status`). Si cambia el precio queda en el historial y se avisa a quienes la tienen en favoritos. |
| `POST /properties/{id}/submit` | Publicador dueño | Envía a revisión. 400 si no tiene fotos o el estado no lo permite. |
| `PATCH /properties/{id}/status` | Dueño o admin | Body `{ "new_status": "paused" \| "published" \| "draft" \| "pending_review" \| "deleted", "rejection_reason"? }` según la tabla de transiciones. |
| `DELETE /properties/{id}` | Dueño o admin | Eliminación suave. 204. |
| `POST /properties/{id}/renew` | Publicador dueño | Renueva 60 días desde hoy. Válido para `published` y `expired`. También disponible como `POST /publisher/properties/{id}/renew`. |
| `POST /properties/{id}/images` | Publicador dueño | `multipart/form-data`, campo `file`. JPG, PNG o WEBP, máx. 5 MB (413), máx. 15 fotos por propiedad. Se comprime y se guarda con nombre UUID. 201. |
| `DELETE /properties/{id}/images/{image_id}` | Publicador dueño | Elimina la foto. 204. |
| `PATCH /properties/{id}/images/reorder` | Publicador dueño | Body `{ "image_ids": [...] }` en el orden deseado. |
| `POST /properties/{id}/view` | Público (token opcional) | Registra una vista única. Cabecera `X-Session-ID` para anónimos. 204. Repetirla no suma. |

## Búsqueda auxiliar (públicas)

| Ruta | Respuesta |
|------|-----------|
| `GET /search/zones` | `[ { "zone": "Equipetrol", "count": 24 }, ... ]` (de más a menos propiedades) |
| `GET /search/stats` | `{ "total_properties": 0, "total_publishers": 0, "zones_count": 0 }` |

## Favoritos, interés y denuncias

| Método y ruta | Acceso | Descripción |
|---------------|--------|-------------|
| `GET /favorites` | Usuario | `{ "data": [...] }` |
| `POST /favorites/{property_id}` | Usuario | 201; 409 si ya existe. |
| `DELETE /favorites/{property_id}` | Usuario | 204. |
| `POST /interest/{property_id}` | Usuario | Body opcional `{ "message" }`. 201 `{ id, message }`; 409 si ya lo hiciste. Avisa al publicador por email. |
| `GET /interest/received` | Publicador | Interesados en sus propiedades. |
| `POST /reports/properties/{property_id}` | Usuario | Body `{ "reason", "description"? }` con `reason` ∈ `fraude`, `informacion_falsa`, `contenido_inapropiado`, `duplicado`, `otro`. 201; 409 si ya denunciaste. |

## Panel del publicador

| Método y ruta | Descripción |
|---------------|-------------|
| `GET /publisher/properties?status=&page=&page_size=` | Sus propiedades con métricas (`view_count`, `interest_count`, `expires_at`). |
| `GET /publisher/metrics` | `{ total_published, total_views, total_interests, active_properties, expiring_soon }` |

## Notificaciones

| Método y ruta | Descripción |
|---------------|-------------|
| `GET /notifications` | `{ "data": [...], "unread_count": N }` (las 50 más recientes) |
| `PATCH /notifications/{id}/read` | Marca una como leída. |
| `PATCH /notifications/read-all` | Marca todas como leídas. |

Tipos (`type`): `property_approved`, `property_rejected`, `property_pending_review` (admin), `property_expiring_soon`, `property_expired`, `new_interest`, `interest_sent`, `favorite_price_change`, `favorite_status_change`, `new_report` (admin), `report_received`.

## Admin

| Método y ruta | Descripción |
|---------------|-------------|
| `GET /admin/properties/pending` | Cola de revisión. |
| `POST /admin/properties/{id}/approve` | Publica (vigencia 60 días) y notifica al publicador. |
| `POST /admin/properties/{id}/reject` | Body `{ "reason" }` obligatorio. Notifica con el motivo. |
| `GET /admin/users?q=&role=&page=&page_size=` | Usuarios paginados; `q` busca por nombre, `role` filtra por rol. |
| `POST /admin/users/{id}/suspend` | Body `{ "reason" }`. Bloquea el login, pausa sus propiedades publicadas y le avisa por email. 400 si es un admin (incluido uno mismo). |
| `POST /admin/users/{id}/reactivate` | Reactiva la cuenta. |
| `GET /admin/reports` | Denuncias pendientes. |
| `POST /admin/reports/{id}/resolve` | Body `{ "resolution_note"? }`. |
| `POST /admin/jobs/expiration` | Ejecuta a mano el job diario (ver README). |

Todas las acciones de admin quedan registradas en `admin_audit_log`.
