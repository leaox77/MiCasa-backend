"""
Script de seed para poblar `properties` con datos ficticios en estado
'published', para probar paginación y filtros (Bloque 6) en staging.

Uso:
    python -m scripts.seed_properties --publisher-id <uuid-de-un-publisher-verificado>
    python -m scripts.seed_properties --publisher-id <uuid> --count 60
    python -m scripts.seed_properties --publisher-id <uuid> --force

El publisher_id tiene que ser el id de un perfil YA EXISTENTE en `profiles`
con role='publisher' — properties.publisher_id es FK a profiles.id, no se
puede insertar un publisher inventado.

Todos los títulos generados arrancan con "[SEED]", así el script detecta si
ya corrió antes sin necesitar una tabla de control aparte.
"""

import argparse
import random
import sys

from app.core.supabase import get_supabase_admin

SEED_PREFIX = "[SEED]"

TIPOS = ["casa", "departamento", "terreno", "local", "oficina"]
MONEDAS = ["BOB", "USD"]
ZONAS = [
    "Equipetrol", "Las Palmas", "Urbari", "Zona Norte", "Barrio Sirari",
    "Segundo Anillo", "Tercer Anillo", "Av. Banzer", "La Guardia",
    "Warnes", "Villa 1ro de Mayo", "Radial 10", "Cotoca", "El Trompillo",
]
TITULOS_BASE = [
    "amplia y luminosa en zona residencial",
    "a estrenar con acabados de lujo",
    "ideal para inversión, alta plusvalía",
    "cerca de colegios y áreas verdes",
    "con vista panorámica y gran jardín",
    "moderna, lista para habitar",
    "en condominio cerrado con seguridad 24hs",
    "con terraza y parrillero",
]


def _fake_property(index: int, publisher_id: str) -> dict:
    tipo = random.choice(TIPOS)
    zona = random.choice(ZONAS)
    moneda = random.choice(MONEDAS)
    habitaciones = random.randint(1, 6) if tipo in ("casa", "departamento") else 0
    banos = max(1, habitaciones - random.randint(0, 1)) if habitaciones else random.randint(1, 3)
    m2 = round(random.uniform(45, 600), 2)
    precio_base = random.uniform(20000, 450000)
    precio = round(precio_base if moneda == "USD" else precio_base * 6.96, 2)
    ideal_inversion = random.random() < 0.25
    es_preventa = random.random() < 0.15

    return {
        "publisher_id": publisher_id,
        "tipo": tipo,
        "titulo": f"{SEED_PREFIX} {tipo.capitalize()} {random.choice(TITULOS_BASE)} #{index}",
        "descripcion": (
            f"Propiedad de prueba generada por el script de seed. Ubicada en "
            f"{zona}, Santa Cruz de la Sierra. Para probar filtros del Bloque 6."
        ),
        "precio": precio,
        "moneda": moneda,
        "zona": zona,
        "direccion": f"Calle {random.randint(1, 40)} #{random.randint(100, 999)}, {zona}",
        "habitaciones": habitaciones,
        "banos": banos,
        "m2": m2,
        "garaje": random.random() < 0.7,
        "antiguedad": random.randint(0, 30),
        "es_preventa": es_preventa,
        "ideal_inversion": ideal_inversion,
        "rentabilidad_estimada": round(random.uniform(4, 12), 2) if ideal_inversion else None,
        "whatsapp_contacto": "+59170000000",
        "estado": "published",
    }


def seed(publisher_id: str, count: int, force: bool) -> None:
    admin = get_supabase_admin()

    publisher = (
        admin.table("profiles")
        .select("id, role")
        .eq("id", publisher_id)
        .maybe_single()
        .execute()
    )
    if not publisher.data:
        print(f"ERROR: no existe un perfil con id={publisher_id}.")
        sys.exit(1)
    if publisher.data.get("role") != "publisher":
        print(f"ERROR: el perfil {publisher_id} no tiene role='publisher'.")
        sys.exit(1)

    existing = (
        admin.table("properties")
        .select("id", count="exact")
        .like("titulo", f"{SEED_PREFIX}%")
        .execute()
    )
    existing_count = existing.count or 0

    if existing_count > 0 and not force:
        print(
            f"Ya hay {existing_count} propiedades de seed (prefijo '{SEED_PREFIX}'). "
            "No se insertó nada. Corré con --force para borrarlas y regenerarlas."
        )
        return

    if existing_count > 0 and force:
        print(f"--force: borrando {existing_count} propiedades de seed anteriores...")
        admin.table("properties").delete().like("titulo", f"{SEED_PREFIX}%").execute()

    rows = [_fake_property(i, publisher_id) for i in range(1, count + 1)]

    batch_size = 20
    inserted = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        result = admin.table("properties").insert(batch).execute()
        inserted += len(result.data or [])

    print(f"Listo: {inserted} propiedades de seed insertadas en estado 'published'.")


def main():
    parser = argparse.ArgumentParser(description="Seed de propiedades ficticias para Mi Casa.")
    parser.add_argument("--publisher-id", required=True, help="id de un perfil existente con role='publisher'")
    parser.add_argument("--count", type=int, default=55)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    seed(args.publisher_id, args.count, args.force)


if __name__ == "__main__":
    main()