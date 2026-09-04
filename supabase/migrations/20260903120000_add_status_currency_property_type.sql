-- ============================================================
-- Migración: reintroduce status, currency y property_type en
-- properties. Alinea la BD real con lo que espera el código de
-- la rama Edgar (Parte 2 del audit).
-- ============================================================

-- 1. Tipos ENUM nuevos
create type public.property_status as enum (
  'draft', 'pending_review', 'published', 'paused', 'expired', 'deleted', 'rejected'
);

create type public.currency_type as enum ('BOB', 'USD');

create type public.property_type as enum ('casa', 'departamento', 'terreno', 'local', 'oficina');

-- 2. property_type: sin default natural posible, se agrega nullable,
-- se rellenan las 10 filas existentes según su título, y recién
-- después se pone NOT NULL. (data.sql NO se toca, esto es un UPDATE
-- sobre la BD, no una edición del dump.)
alter table public.properties
  add column property_type public.property_type;

update public.properties set property_type = 'casa'::public.property_type
  where id in (
    '0fdfa3fa-03b4-4d49-b469-161d190715eb', -- Casa moderna en Urubó con piscina
    '43932be3-5e2f-415b-aa85-2494800ef67c', -- Casa en condominio Los Jardines 4 dorms
    '7942cfc0-9de8-4650-935f-3583b40e0934', -- Casa económica 3 dorms zona norte
    '765162bf-7679-45ba-bbfa-dfa6010e4631'  -- Casa en construcción zona Hamacas
  );

update public.properties set property_type = 'departamento'::public.property_type
  where id in (
    '65d32b6d-5bc4-4538-8464-2d9cc71149e3', -- Departamento céntrico piso 8
    '43a8a5e5-5552-4d3c-a41f-3c5d4f6cbf37', -- Preventa departamento Torre Azul piso 12
    'fd9c92ba-efbf-4e04-9582-f988721fa66a'  -- Departamento 1 dorm zona universitaria
  );

update public.properties set property_type = 'terreno'::public.property_type
  where id in (
    '39c60883-02d1-487b-87b4-f367fc0b48b9', -- Lote plano urbanizado en La Guardia
    '530f4bcb-07df-4436-b252-a8635e2989b8', -- Terreno agrícola 5 hectáreas
    'f933fc63-7fdd-450b-86be-c1d735add930'  -- Lote comercial sobre 4to anillo
  );

alter table public.properties
  alter column property_type set not null;

-- 3. currency: sí tiene default natural (BOB), el backfill de las
-- 10 filas existentes es automático al agregar la columna.
alter table public.properties
  add column currency public.currency_type not null default 'BOB';

-- 4. status: default 'draft' para inserts nuevos. Las 10 filas
-- existentes no son borradores al azar — si ya tenían published_at
-- seteado, el flujo viejo las consideraba publicadas. Backfill según
-- ese dato real.
alter table public.properties
  add column status public.property_status not null default 'draft';

update public.properties
  set status = 'published'
  where published_at is not null;

-- 5. notification_type: falta el valor que usa
-- notify_admin_new_property_pending (Bug 3 del audit). Sin esto ese
-- insert revienta con "invalid input value for enum notification_type".
alter type public.notification_type add value if not exists 'property_pending_review';

-- 6. property_price_history: le agrego currency. Está vacía hoy
-- (el trigger nunca estuvo conectado), backfill trivial.
alter table public.property_price_history
  add column currency public.currency_type not null default 'BOB';

-- 7. Índices para los filtros nuevos y para que "listado público"
-- (status = 'published') no escanee toda la tabla en cada request.
create index if not exists idx_properties_status on public.properties using btree (status);
create index if not exists idx_properties_type on public.properties using btree (property_type);
create index if not exists idx_properties_currency on public.properties using btree (currency);

-- ============================================================
-- NOTA sobre handle_price_change: existe como función pero JAMÁS
-- se adjuntó como trigger (código muerto), y además está rota (usa
-- una columna "currency" en property_price_history que no existía
-- antes de este archivo, y usa NEW.publisher_id como "changed_by",
-- incorrecto si algún día un admin edita precios). Decisión: NO se
-- adjunta. El registro de historial de precio se hace a mano en
-- property_service.update_property, donde sí se sabe quién hizo el
-- cambio de verdad.
-- ============================================================