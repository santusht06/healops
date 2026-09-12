"""Redis Cache Cluster Health & Invalidation Tool for HealOps Layer 2."""

from typing import Dict, Any
from strands import tool
from brain.session import get_redis_client


@tool
def inspect_redis_memory() -> Dict[str, Any]:
    """Inspects Redis memory consumption, total keys, and eviction stats."""
    client = get_redis_client()
    if client is None:
        return {
            "status": "UNAVAILABLE",
            "message": "Redis cluster is currently unreachable."
        }

    try:
        info_mem = client.info("memory")
        info_stats = client.info("stats")
        dbsize = client.dbsize()

        used_memory_mb = round(info_mem.get("used_memory", 0) / (1024 * 1024), 2)
        peak_memory_mb = round(info_mem.get("used_memory_peak", 0) / (1024 * 1024), 2)
        fragmentation_ratio = info_mem.get("mem_fragmentation_ratio", 1.0)
        evicted_keys = info_stats.get("evicted_keys", 0)

        # Health assessment
        status = "HEALTHY"
        if evicted_keys > 1000:
            status = "WARNING: Key evictions detected (OOM risk)"

        return {
            "status": status,
            "used_memory_mb": used_memory_mb,
            "peak_memory_mb": peak_memory_mb,
            "fragmentation_ratio": fragmentation_ratio,
            "total_keys": dbsize,
            "evicted_keys": evicted_keys,
            "maxmemory_policy": info_mem.get("maxmemory_policy", "unknown")
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


@tool
def flush_cache_namespace(namespace_prefix: str = "healops:cache") -> Dict[str, Any]:
    """Cleans up stale or corrupted cache keys matching a namespace prefix.
    
    Args:
        namespace_prefix: Key pattern to delete (e.g. 'healops:cache*' or 'sessions:*').
    """
    client = get_redis_client()
    if client is None:
        return {"status": "FAILED", "message": "Redis is unreachable."}

    try:
        pattern = f"{namespace_prefix}*" if not namespace_prefix.endswith("*") else namespace_prefix
        keys = client.keys(pattern)
        if keys:
            count = client.delete(*keys)
            return {
                "status": "SUCCESS",
                "pattern": pattern,
                "deleted_keys_count": count
            }
        return {
            "status": "NOOP",
            "pattern": pattern,
            "message": "No keys matched pattern."
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}
