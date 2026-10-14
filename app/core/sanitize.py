import re

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]*>")


def strip_html(value: str) -> str:
    """Elimina etiquetas HTML (y el contenido de <script>/<style>) del texto libre
    antes de guardarlo (SEC-011, previene XSS almacenado)."""
    cleaned = _SCRIPT_STYLE.sub("", value)
    cleaned = _TAG.sub("", cleaned)
    return cleaned.strip()
