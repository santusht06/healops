"""Session Management for HealOps Layer 1.

Primary: strands-redis-session-manager (for distributed, persistent session state).
Fallback: FileSessionManager (local disk backup if Redis is unreachable).
"""

import os
import logging
from typing import Optional
import redis
from strands.session import SessionManager, FileSessionManager
from config import settings

logger = logging.getLogger("healops.session")


def get_redis_client() -> Optional[redis.Redis]:
    """Returns an active Redis client or None if unreachable."""
    try:
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            socket_connect_timeout=2.0,
            decode_responses=False
        )
        if client.ping():
            return client
    except Exception as e:
        logger.warning(f"Redis not reachable on {settings.REDIS_HOST}:{settings.REDIS_PORT}: {e}")
    return None


def get_session_manager(session_id: str) -> SessionManager:
    """Instantiate a SessionManager for a specific incident session.
    
    Attempts Redis first; falls back to FileSessionManager if Redis fails.
    """
    redis_client = get_redis_client()

    if redis_client is not None:
        try:
            from redis_session_manager import RedisSessionManager

            logger.info(f"Using RedisSessionManager for session: '{session_id}' (Namespace: {settings.REDIS_NAMESPACE})")
            return RedisSessionManager(
                session_id=session_id,
                redis_client=redis_client,
                namespace=settings.REDIS_NAMESPACE,
                ttl_seconds=settings.SESSION_TTL_SECONDS,
                rolling_ttl=True
            )
        except Exception as e:
            logger.warning(f"Failed to init RedisSessionManager: {e}. Falling back to FileSessionManager.")

    # Fallback: FileSessionManager
    sessions_dir = os.path.join(settings.DATA_DIR, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    logger.info(f"Using FileSessionManager for session: '{session_id}' at {sessions_dir}")
    return FileSessionManager(
        session_id=session_id,
        storage_dir=sessions_dir
    )
