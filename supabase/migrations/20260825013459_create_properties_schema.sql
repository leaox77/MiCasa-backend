-- ============================================================
-- Migración: esquema de propiedades (Sprint 3 — TECH010)
-- Tablas: properties, property_images, property_status_history
-- RLS: público (published), dueño (publisher_id), admin
-- ============================================================

-- 1. Tipos ENUM
create type property_type as enum ('casa', 'departamento', 'terreno', 'local', 'oficina');

create type property_status as enum (
  'draft', 'pending_review', 'published', 'paused', 'expired', 'deleted', 'rejected'
);

create type currency_type as enum ('BOB', 'USD');

-- 2. Tabla properties
create table public.properties (
  id uuid primary key default gen_random_uuid(),
  publisher_id uuid not null references public.profiles(id) on delete cascade,

  tipo property_type not null,
  titulo text not null check (char_length(titulo) between 10 and 100),
  descripcion text not null,
  precio numeric(14, 2) not null check (precio > 0),
  moneda currency_type not null default 'BOB',

  zona text not null,
  direccion text not null,

  habitaciones smallint not null check (habitaciones >= 0),
  banos smallint not null check (banos >= 0),
  m2 numeric(10, 2) not null check (m2 > 0),
  garaje boolean not null default false,
  antiguedad smallint not null check (antiguedad >= 0),

  es_preventa boolean not null default false,
  ideal_inversion boolean not null default false,
  rentabilidad_estimada numeric(5, 2),

  whatsapp_contacto text,

  estado property_status not null default 'draft',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint chk_rentabilidad_no_negativa_si_inversion check (
    ideal_inversion = false
    or rentabilidad_estimada is null
    or rentabilidad_estimada >= 0
  )
);

comment on table public.properties is 'Propiedades publicadas por publishers en el marketplace.';

-- Trigger para mantener updated_at al día en cada UPDATE
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_properties_updated_at
before update on public.properties
for each row execute function public.set_updated_at();

-- 3. Tabla property_images
create table public.property_images (
  id uuid primary key default gen_random_uuid(),
  property_id uuid not null references public.properties(id) on delete cascade,
  url text not null,
  order_index smallint not null default 0,
  created_at timestamptz not null default now()
);

comment on table public.property_images is 'Fotos asociadas a una propiedad. Máx. 15 por propiedad, validado en el backend (storage_service.py).';

-- 4. Tabla property_status_history
create table public.property_status_history (
  id uuid primary key default gen_random_uuid(),
  property_id uuid not null references public.properties(id) on delete cascade,
  old_status property_status,
  new_status property_status not null,
  old_price numeric(14, 2),
  new_price numeric(14, 2),
  changed_by uuid not null references public.profiles(id),
  changed_at timestamptz not null default now()
);

comment on table public.property_status_history is 'Auditoría de cambios de estado y precio de una propiedad.';

-- 5. Índices — para filtros de búsqueda (Sprint 4)
create index idx_properties_tipo on public.properties(tipo);
create index idx_properties_precio on public.properties(precio);
create index idx_properties_zona on public.properties(zona);
create index idx_properties_habitaciones on public.properties(habitaciones);
create index idx_properties_estado on public.properties(estado);

create index idx_property_images_property_id on public.property_images(property_id);
create index idx_property_status_history_property_id on public.property_status_history(property_id);

-- ============================================================
-- 6. Función auxiliar: is_admin()
-- SECURITY DEFINER para evitar depender de las policies RLS de
-- profiles al chequear el rol desde políticas de OTRAS tablas
-- (si no, se puede caer en recursión o en falsos negativos si
-- profiles tiene su propia RLS restrictiva).
-- ============================================================
create or replace function public.is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

comment on function public.is_admin() is
  'True si el usuario autenticado tiene role=admin en profiles. SECURITY DEFINER: no depende de las policies RLS de profiles.';

-- ============================================================
-- 7. RLS: properties
-- ============================================================
alter table public.properties enable row level security;

create policy "properties_select_published"
on public.properties for select
using (estado = 'published');

create policy "properties_select_own"
on public.properties for select
using (auth.uid() = publisher_id);

create policy "properties_select_admin"
on public.properties for select
using (public.is_admin());

create policy "properties_insert_own"
on public.properties for insert
with check (auth.uid() = publisher_id);

create policy "properties_update_own_or_admin"
on public.properties for update
using (auth.uid() = publisher_id or public.is_admin())
with check (auth.uid() = publisher_id or public.is_admin());

create policy "properties_delete_own_or_admin"
on public.properties for delete
using (auth.uid() = publisher_id or public.is_admin());

-- ============================================================
-- 8. RLS: property_images (hereda el criterio de acceso de su property)
-- ============================================================
alter table public.property_images enable row level security;

create policy "property_images_select"
on public.property_images for select
using (
  exists (
    select 1 from public.properties p
    where p.id = property_images.property_id
      and (p.estado = 'published' or p.publisher_id = auth.uid() or public.is_admin())
  )
);

create policy "property_images_insert"
on public.property_images for insert
with check (
  exists (
    select 1 from public.properties p
    where p.id = property_images.property_id
      and (p.publisher_id = auth.uid() or public.is_admin())
  )
);

create policy "property_images_update"
on public.property_images for update
using (
  exists (
    select 1 from public.properties p
    where p.id = property_images.property_id
      and (p.publisher_id = auth.uid() or public.is_admin())
  )
)
with check (
  exists (
    select 1 from public.properties p
    where p.id = property_images.property_id
      and (p.publisher_id = auth.uid() or public.is_admin())
  )
);

create policy "property_images_delete"
on public.property_images for delete
using (
  exists (
    select 1 from public.properties p
    where p.id = property_images.property_id
      and (p.publisher_id = auth.uid() or public.is_admin())
  )
);

-- ============================================================
-- 9. RLS: property_status_history
--
-- NOTA — esto NO aplica literalmente "mismo criterio que su property":
-- el historial (quién cambió qué precio y cuándo) queda visible SOLO
-- para el dueño y el admin, aunque la propiedad esté publicada.
-- Exponerlo a cualquier visitante anónimo no tiene justificación de
-- producto por ahora. Si más adelante querés un badge tipo "bajó de
-- precio" en tarjetas públicas, se resuelve con un campo calculado en
-- PropertyListItem (Bloque 2), no exponiendo esta tabla entera.
-- ============================================================
alter table public.property_status_history enable row level security;

create policy "property_status_history_select"
on public.property_status_history for select
using (
  exists (
    select 1 from public.properties p
    where p.id = property_status_history.property_id
      and (p.publisher_id = auth.uid() or public.is_admin())
  )
);

-- No hay policies de insert/update/delete para roles autenticados:
-- estos registros solo los escribe el backend vía service role key.