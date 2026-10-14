import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

_hits: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def rate_limit(max_calls: int = 10, window_seconds: int = 60):
    """Dependencia que limita las llamadas por IP y ruta (SEC-003).

    Ventana deslizante en memoria: vale para un solo proceso. Si el backend se
    despliega con varios workers, cada uno cuenta por separado y conviene mover
    el contador a un almacén compartido (Redis)."""

    def checker(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{request.url.path}"
        now = time.monotonic()
        with _lock:
            hits = _hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= max_calls:
                retry_after = max(1, int(window_seconds - (now - hits[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Demasiadas solicitudes. Intentá de nuevo en un minuto.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    return checker


def reset_rate_limits() -> None:
    """Solo para tests."""
    with _lock:
        _hits.clear()
