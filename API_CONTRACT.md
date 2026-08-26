# API Contract — GET /api/v1/properties

Endpoint público de búsqueda de propiedades. No requiere autenticación.
Solo devuelve propiedades en estado `published`.

## Query params

| Param         | Tipo                                              | Obligatorio | Descripción                                                        |
|---------------|----------------------------------------------------|-------------|----------------------------------------------------------------------|
| `tipo`        | enum: `casa`, `departamento`, `terreno`, `local`, `oficina` | No | Filtra por tipo de propiedad                                        |
| `precio_min`  | number (decimal, ≥ 0)                              | No          | Precio mínimo                                                        |
| `precio_max`  | number (decimal, ≥ 0)                              | No          | Precio máximo                                                        |
| `moneda`      | enum: `BOB`, `USD`                                 | No          | Filtra por moneda                                                    |
| `zona`        | string                                              | No          | Coincidencia parcial, sin distinguir mayúsculas/minúsculas          |
| `habitaciones`| integer (≥ 0)                                      | No          | Cantidad exacta de habitaciones                                      |
| `m2_min`      | number (float, ≥ 0)                                | No          | Metros cuadrados mínimos                                              |
| `m2_max`      | number (float, ≥ 0)                                | No          | Metros cuadrados máximos                                              |
| `garaje`      | boolean (`true` / `false`)                         | No          | Con o sin garaje                                                      |
| `antiguedad`  | integer (≥ 0)                                      | No          | Antigüedad **máxima** en años (`antiguedad ≤ valor`)                 |
| `preventa`    | boolean (`true` / `false`)                         | No          | Solo propiedades en preventa                                          |
| `page`        | integer (≥ 1)                                      | No          | Página actual. Default: `1`                                          |
| `page_size`   | integer (1 a 100)                                  | No          | Resultados por página. Default: `20`                                  |
| `orden`       | enum: `reciente`, `precio_asc`, `precio_desc`      | No          | Orden del listado. Default: `reciente`                                |

Todos los filtros son **acumulables** (se combinan con AND). Ninguno es obligatorio; sin filtros, devuelve todas las propiedades `published` ordenadas por más recientes.

## Ejemplo de URL
GET /api/v1/properties?tipo=casa&precio_max=100000&zona=equipetrol&habitaciones=3&orden=precio_asc&page=1&page_size=20


Esta URL es la que el frontend debe reflejar en la barra de direcciones para que la búsqueda sea compartible — los nombres de los params tienen que coincidir exactamente con esta tabla.

## Forma de la respuesta (200 OK)

```json
{
  "results": [
    {
      "id": "3f2a9e7e-1234-4c1a-9f0a-abc123456789",
      "foto_principal": "https://xxxx.supabase.co/storage/v1/object/sign/property-images/....jpg",
      "tipo": "casa",
      "precio": 95000.00,
      "moneda": "USD",
      "zona": "Equipetrol",
      "habitaciones": 3,
      "m2": 220.5,
      "etiquetas": ["preventa"]
    }
  ],
  "total": 47,
  "page": 1,
  "page_size": 20
}
```

- `results`: lista de propiedades para esta página (puede venir vacía si no hay coincidencias, `total` sería `0`).
- `foto_principal` puede ser `null` si la propiedad todavía no tiene fotos cargadas.
- `etiquetas` es un array de strings entre `"preventa"` e `"inversion"`. Puede venir vacío.
- `total`: cantidad total de resultados que matchean los filtros (sin paginar) — úsalo para el texto "X propiedades encontradas" y para calcular la cantidad de páginas (`Math.ceil(total / page_size)`).

## Códigos de error

| Código | Cuándo pasa                                                                                   | Ejemplo                                             |
|--------|------------------------------------------------------------------------------------------------|------------------------------------------------------|
| `422`  | Un param tiene un **tipo o formato inválido** (validación automática de FastAPI)                | `tipo=invalido`, `precio_min=abc`, `garaje=si`       |
| `400`  | Los params son del tipo correcto pero la **combinación es inconsistente**                       | `precio_min=500&precio_max=100`, `m2_min=300&m2_max=100` |
| `500`  | Error inesperado del servidor (no debería pasar en uso normal)                                  | —                                                      |

El body de un error `400` o `422` tiene esta forma (formato estándar de FastAPI/Pydantic):

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["precio_max"],
      "msg": "Value error, precio_min no puede ser mayor a precio_max.",
      "input": "100"
    }
  ]
}
```

El frontend puede mostrar `detail[0].msg` como mensaje de error genérico, o iterar `detail` si hay más de un problema.