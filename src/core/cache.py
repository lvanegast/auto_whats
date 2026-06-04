import os
import logging
from redis.asyncio import Redis, from_url

logger = logging.getLogger("auto-whats-cache")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Cliente de conexión único (Lazy Initialization)
# NOTA: Usamos decode_responses=True para que devuelva strings de Python (str) en lugar de bytes
redis_client: Redis = from_url(REDIS_URL, decode_responses=True)


async def get_cached_state(chat_id: str) -> str | None:
    """
    Busca en Redis el estado actual del chat de forma asíncrona.
    Devuelve None si el estado no está cacheado o si hay un error de conexión con Redis.
    """
    try:
        state = await redis_client.get(f"session:{chat_id}")
        if state:
            logger.info(
                f"⚡ [Redis Cache HIT] Estado recuperado para {chat_id}: '{state}'"
            )
        else:
            logger.info(f"🔍 [Redis Cache MISS] No hay estado en caché para {chat_id}")
        return state
    except Exception as e:
        logger.error(f"⚠️ [Redis Error] No se pudo leer de Redis para {chat_id}: {e}")
        return None


async def set_cached_state(
    chat_id: str, state: str, expire_seconds: int = 86400
) -> bool:
    """
    Guarda el estado del chat en Redis de forma asíncrona con expiración automática (default 24h).
    Devuelve True si la operación fue exitosa, False en caso contrario.
    """
    try:
        await redis_client.set(f"session:{chat_id}", state, ex=expire_seconds)
        logger.info(
            f"💾 [Redis Cache SET] Guardado estado '{state}' para {chat_id} (expira en {expire_seconds}s)"
        )
        return True
    except Exception as e:
        logger.error(
            f"⚠️ [Redis Error] No se pudo escribir en Redis para {chat_id}: {e}"
        )
        return False
