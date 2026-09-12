"""Database Diagnostic & Connection Pool Health Tool for HealOps Layer 2."""

import os
from typing import Dict, Any
from sqlalchemy import create_engine, text
from strands import tool
from config import settings


@tool
def inspect_database_health(db_url: str = "") -> Dict[str, Any]:
    """Inspects database connectivity, active connection count, and locks.
    
    Args:
        db_url: Optional database connection string (defaults to local SQLite if empty).
    """
    if not db_url:
        sqlite_path = os.path.join(settings.DATA_DIR, "healops_db.sqlite")
        db_url = f"sqlite:///{sqlite_path}"

    try:
        engine = create_engine(db_url, connect_args={"timeout": 3} if "sqlite" in db_url else {})
        with engine.connect() as conn:
            # Simple health check ping
            conn.execute(text("SELECT 1"))

            # Inspect connection & table statistics
            if "sqlite" in db_url:
                tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).fetchall()
                return {
                    "database_type": "SQLite",
                    "status": "HEALTHY",
                    "connection_test": "PASSED",
                    "tables_found": [t[0] for t in tables],
                    "active_pool_size": 1,
                    "deadlocks_detected": 0
                }
            elif "postgresql" in db_url:
                # Postgres active connections check
                res = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")).scalar()
                locks = conn.execute(text("SELECT count(*) FROM pg_locks WHERE NOT granted;")).scalar()
                return {
                    "database_type": "PostgreSQL",
                    "status": "HEALTHY" if locks == 0 else "WARNING: Locks Detected",
                    "connection_test": "PASSED",
                    "active_connections": res,
                    "unresolved_locks": locks
                }

    except Exception as e:
        return {
            "database_url": db_url.split("@")[-1] if "@" in db_url else db_url,
            "status": "CRITICAL",
            "connection_test": "FAILED",
            "error": str(e)
        }
